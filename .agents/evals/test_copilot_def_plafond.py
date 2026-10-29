#!/usr/bin/env python3
"""LA DÉF COPILOT TIENT SOUS 30 000 CARACTÈRES, SANS PERTE DE RÈGLE — T-01M51XM50EHB610MD4BCHJV17N.

CE QU'IL JUGE.
* (a) Chaque `.github/agents/*.agent.md` tient sous `PLAFOND` en `len()` du fichier ENTIER,
  frontmatter compris — plus strict que le corps seul. La population est DÉRIVÉE du glob ; dans le
  kit elle doit valoir celle de `.claude/agents/*.md` (un glob muté qui ne voit plus rien, ou qui en
  voit moins, rougit) ; aucun cardinal n'est écrit dans ce fichier.
* (b) KIT SEUL (marqueur `.agents/IS_THE_KIT`, précédent `DANS_LE_KIT` de `test_cadre_roster.py`) :
  les atomes de règle du corps de `orchestrator.agent.md` gelés dans
  `fixtures/copilot_orchestrator_regles.json` — identifiants `S-`/`T-`/`L-`, spans de code, spans
  gras — sont comptés en MULTIENSEMBLE : chaque atome garde au moins son nombre d'occurrences gelé,
  moins les retraits listés dans `redites_assumees` (une entrée par atome, chacune avec son
  `pourquoi`, jamais la dernière occurrence). Une phrase retirée dont l'atome survit ailleurs rougit
  donc aussi, sauf redite assumée. Un ajout passe (inclusion, jamais égalité).
  Chez l'adoptant la déf est la sienne : (b) saute en l'annonçant.
* (c) Contrôles négatifs : un fichier à `PLAFOND + 1` rougit, un à `PLAFOND` passe ; un fichier dont
  seul le frontmatter fait passer le plafond rougit ; CHAQUE atome gelé retiré seul d'une copie du
  corps rougit, et CHAQUE occurrence retirée seule d'un atome à son compte exact rougit ; vider la
  liste des redites assumées fait rougir chacune ; une fixture amputée rougit (source, catégorie
  absente ou vide, compte faux, redite sur un atome inconnu, sur la dernière occurrence, sans
  `pourquoi`, en double).
* (d) Le marqueur du kit ne se perd pas en silence : `docs/interne/`, qui ne voyage pas, sans
  `.agents/IS_THE_KIT` est un kit au marqueur perdu — rouge, jamais des sauts verts.

CE QU'IL NE PROUVE PAS (bornes nommées).
* Des atomes identiques ne sont pas des règles identiques : une phrase peut perdre sa portée en
  gardant ses spans, et une phrase sans atome n'est pas vue. La deuxième jambe est faite des bancs
  texte qui épinglent ce fichier, et de la relecture du texte retiré par `exec-critic` et la revue
  de clôture.
* L'unité que GitHub compte (caractères, unités UTF-16 ou octets ; frontmatter compris ou non)
  n'est PAS mesurée : `len()` compte des points de code. L'effet d'un dépassement chez Copilot
  (troncature, refus) n'est pas mesuré non plus.
* Un `pourquoi` est lu comme présent, jamais comme vrai.

RE-GEL (procédure). La fixture est la photographie d'un corps, pas une source. Un retrait voulu
s'écrit de l'une de deux façons, dans le MÊME commit que la modification de la déf, pour que le
diff de la fixture montre au relecteur ce qui est sorti : (1) une redite (l'atome survit ailleurs)
s'ajoute à `redites_assumees` avec son `pourquoi` ; (2) un retrait que le plan approuvé NOMME,
avec sa raison, se re-gèle avec `python3 .agents/evals/test_copilot_def_plafond.py --regeler
<etiquette>` (étiquette : la tâche ou le sha dont le corps est gelé), qui imprime les comptes
RETIRÉS et AJOUTÉS et vide `redites_assumees` (le corps courant devient la base). Ré-geler pour
ÉTENDRE la protection est permis, avec la même discipline. Ne JAMAIS ré-geler ni assumer une redite
pour faire verdir un rouge que le plan ne nomme pas : restaurer la phrase. Une modification du seul
frontmatter (clé `model:`) ne touche aucun atome, mais compte dans (a). Ça empêche d'OUBLIER, pas
de TRICHER : le banc ne vérifie pas que le plan cité existe.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# (b) ne juge que le KIT ; (a), (c) et (d) tournent partout.
# adopting-tree: le marqueur d'identite du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant » : (b) y saute en l'annoncant.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
DANS_LE_KIT = pytest.mark.skipif(
    not EST_LE_KIT,
    reason="SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) — "
           "les atomes de la def orchestrator Copilot ne sont pas juges ici",
)

#: Le plafond annoncé par GitHub pour un agent personnalisé ; compté ici sur le fichier entier.
PLAFOND = 30_000
REPERTOIRE_COPILOT = Path(".github") / "agents"
MOTIF_COPILOT = "*.agent.md"
REPERTOIRE_CLAUDE = Path(".claude") / "agents"
ORCHESTRATEUR = ".github/agents/orchestrator.agent.md"
FIXTURE = ROOT / ".agents" / "evals" / "fixtures" / "copilot_orchestrator_regles.json"
REGELER = "python3 .agents/evals/test_copilot_def_plafond.py --regeler <etiquette>"
#: Catégorie d'atome -> motif ; le groupe 1, s'il existe, est l'atome.
MOTIFS = {
    "S": r"\bS-[0-9A-Z]{8,}\b",
    "T": r"\bT-[0-9A-Z]{8,}\b",
    "L": r"\bL-[0-9A-Z]{8,}\b",
    "code": r"`([^`\n]+)`",
    "gras": r"\*\*(.+?)\*\*",
}


# --- extraction --------------------------------------------------------------------------------
def corps(texte: str) -> str:
    """Le corps d'une def Markdown : tout ce qui suit le frontmatter `---` / ... / `---`."""
    if not texte.startswith("---\n"):
        raise ValueError("def sans frontmatter `---` en ligne 1")
    fin = texte.find("\n---\n", 3)
    if fin < 0:
        raise ValueError("frontmatter non ferme")
    return texte[fin + 5:]


def atomes(texte_corps: str) -> dict[str, Counter]:
    """Les atomes de règle d'un corps, par catégorie, avec leur nombre d'occurrences."""
    return {cat: Counter(re.findall(motif, texte_corps)) for cat, motif in MOTIFS.items()}


def assumees(objet: dict) -> dict[tuple[str, str], int]:
    """(catégorie, atome) -> occurrences dont le retrait est une redite assumée."""
    return {(r["categorie"], r["atome"]): r["retraits"] for r in objet.get("redites_assumees", [])}


def manquants(geles: dict[str, dict[str, int]], courants: dict[str, Counter],
              redites: dict[tuple[str, str], int]) -> list[str]:
    """Chaque atome sous son compte requis (gelé moins redites assumées) : `catégorie: atome — vu < requis`."""
    ecarts = []
    for cat in MOTIFS:
        for atome, n in geles.get(cat, {}).items():
            requis = n - redites.get((cat, atome), 0)
            vu = courants.get(cat, Counter())[atome]
            if vu < requis:
                ecarts.append(f"{cat}: {atome} — {vu} < {requis}")
    return ecarts


def valider_fixture(objet: dict) -> list[str]:
    """Les défauts de FORME d'une fixture ; une fixture vide ou amputée ne passe jamais en silence."""
    defauts = []
    if objet.get("source") != ORCHESTRATEUR:
        defauts.append(f"source {objet.get('source')!r} != {ORCHESTRATEUR!r}")
    geles, comptes = objet.get("atomes"), objet.get("comptes")
    if not isinstance(geles, dict) or not isinstance(comptes, dict):
        return defauts + ["`atomes` ou `comptes` absent"]
    for cat in MOTIFS:
        table = geles.get(cat)
        if not isinstance(table, dict) or not table:
            defauts.append(f"categorie {cat} absente ou vide")
        elif any(not isinstance(n, int) or n < 1 for n in table.values()):
            defauts.append(f"categorie {cat} : un compte d'occurrences n'est pas un entier >= 1")
        elif comptes.get(cat) != len(table):
            defauts.append(f"categorie {cat} : compte {comptes.get(cat)} != {len(table)} atomes")
    redites = objet.get("redites_assumees")
    if not isinstance(redites, list):
        return defauts + ["`redites_assumees` absent"]
    vues = set()
    for r in redites:
        cle = (r.get("categorie"), r.get("atome"))
        gele = geles.get(cle[0], {}).get(cle[1]) if isinstance(geles.get(cle[0]), dict) else None
        if cle in vues:
            defauts.append(f"redite en double : {cle}")
        vues.add(cle)
        if gele is None:
            defauts.append(f"redite sur un atome non gele : {cle}")
        elif not isinstance(r.get("retraits"), int) or not 1 <= r["retraits"] < gele:
            defauts.append(f"redite {cle} : retraits hors de 1..{gele - 1} (jamais la derniere occurrence)")
        if not isinstance(r.get("pourquoi"), str) or not r["pourquoi"].strip():
            defauts.append(f"redite {cle} sans `pourquoi`")
    return defauts


def trop_longs(racine: Path) -> list[str]:
    """Chaque def Copilot de `racine` au-delà de `PLAFOND`, `len()` du fichier entier."""
    ecarts = []
    for chemin in sorted((racine / REPERTOIRE_COPILOT).glob(MOTIF_COPILOT)):
        n = len(chemin.read_text(encoding="utf-8"))
        if n > PLAFOND:
            ecarts.append(f"{chemin.relative_to(racine).as_posix()} : {n} > {PLAFOND}")
    return ecarts


def marqueur_coherent(racine: Path) -> bool:
    """Faux si `docs/interne/` (qui ne voyage pas) est là sans `.agents/IS_THE_KIT` : marqueur perdu."""
    # adopting-tree: docs/interne ne voyage pas ; present sans le marqueur, c'est le kit qui l'a perdu
    return (racine / ".agents" / "IS_THE_KIT").is_file() or not (racine / "docs" / "interne").is_dir()


def serialiser(objet: dict) -> str:
    return json.dumps(objet, ensure_ascii=False, indent=1) + "\n"


def geler(texte: str, etiquette: str) -> dict:
    trouves = atomes(corps(texte))
    tables = {cat: dict(sorted(trouves[cat].items())) for cat in MOTIFS}
    return {"source": ORCHESTRATEUR, "gele_a": etiquette,
            "comptes": {cat: len(t) for cat, t in tables.items()}, "atomes": tables,
            "redites_assumees": []}


# --- (a) le plafond, (d) le marqueur -------------------------------------------------------------
def test_chaque_def_sous_30000() -> None:
    defs = sorted((ROOT / REPERTOIRE_COPILOT).glob(MOTIF_COPILOT))
    assert defs, f"aucune def sous {REPERTOIRE_COPILOT}/{MOTIF_COPILOT} : le banc ne jugerait rien"
    if EST_LE_KIT:
        claude = sorted((ROOT / REPERTOIRE_CLAUDE).glob("*.md"))
        assert len(defs) == len(claude), (
            f"{len(defs)} defs Copilot contre {len(claude)} defs Claude : le glob ne voit pas le roster")
    assert trop_longs(ROOT) == [], "\n".join(trop_longs(ROOT))


def test_le_marqueur_du_kit_ne_se_perd_pas_en_silence() -> None:
    assert marqueur_coherent(ROOT), (
        "docs/interne/ present sans .agents/IS_THE_KIT : marqueur du kit perdu, (b) sauterait en vert")


# --- (b) les atomes ----------------------------------------------------------------------------
def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _courants() -> dict[str, Counter]:
    return atomes(corps((ROOT / ORCHESTRATEUR).read_text(encoding="utf-8")))


@DANS_LE_KIT
def test_atomes_orchestrator_conserves() -> None:
    objet = _fixture()
    assert valider_fixture(objet) == [], valider_fixture(objet)
    perdus = manquants(objet["atomes"], _courants(), assumees(objet))
    assert perdus == [], (
        f"{len(perdus)} atome(s) sous leur compte gele : restaurer la phrase ; une redite s'assume "
        f"dans `redites_assumees`, un retrait nomme par le plan se re-gele (`{REGELER}`)\n" + "\n".join(perdus))


@DANS_LE_KIT
def test_la_fixture_est_sous_sa_forme_canonique() -> None:
    texte = FIXTURE.read_text(encoding="utf-8")
    assert serialiser(json.loads(texte)) == texte, f"fixture editee hors forme canonique : `{REGELER}`"


# --- (c) contrôles négatifs ----------------------------------------------------------------------
def _poser(racine: Path, texte: str) -> None:
    d = racine / REPERTOIRE_COPILOT
    d.mkdir(parents=True)
    with open(d / "x.agent.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(texte)


def test_controles_negatifs_le_plafond_est_trente_mille() -> None:
    assert PLAFOND == 30_000, "plafond GitHub d'un agent personnalise : le relever exige une source"


@pytest.mark.parametrize("taille, rouge", [(PLAFOND + 1, True), (PLAFOND, False)])
def test_controles_negatifs_un_corps_au_dela_du_plafond_rougit(tmp_path, taille, rouge) -> None:
    entete = "---\nname: x\n---\n"
    _poser(tmp_path, entete + "é" * (taille - len(entete)))
    assert bool(trop_longs(tmp_path)) is rouge


def test_controles_negatifs_le_frontmatter_compte(tmp_path) -> None:
    corps_seul = "a" * (PLAFOND - 10)
    entete = "---\nname: x\ndescription: " + "d" * 20 + "\n---\n"
    _poser(tmp_path, entete + corps_seul)
    assert len(corps_seul) < PLAFOND < len(entete + corps_seul)
    assert trop_longs(tmp_path), "un fichier qui ne depasse que par son frontmatter doit rougir"


def test_controles_negatifs_un_marqueur_perdu_rougit(tmp_path) -> None:
    assert marqueur_coherent(tmp_path), "un arbre sans docs/interne/ est un adoptant"
    (tmp_path / "docs" / "interne").mkdir(parents=True)
    assert not marqueur_coherent(tmp_path), "docs/interne/ sans le marqueur doit rougir"
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "IS_THE_KIT").write_text("", encoding="utf-8")
    assert marqueur_coherent(tmp_path)


def _retirer(texte_corps: str, cat: str, atome: str) -> str:
    if cat == "code":
        return texte_corps.replace(f"`{atome}`", atome)
    if cat == "gras":
        return texte_corps.replace(f"**{atome}**", atome)
    return texte_corps.replace(atome, "<retire>")


def _retirer_une(texte_corps: str, cat: str, atome: str) -> str:
    """Retire UNE occurrence de l'atome, repérée par le motif même (jamais une sous-chaîne voisine)."""
    for m in re.finditer(MOTIFS[cat], texte_corps):
        if (m.group(1) if m.groups() else m.group(0)) == atome:
            remplacement = atome if cat in ("code", "gras") else "<retire>"
            return texte_corps[:m.start()] + remplacement + texte_corps[m.end():]
    raise AssertionError(f"{cat}: {atome} introuvable dans le corps")


def _rougit(perdus: list[str], cat: str, atome: str) -> bool:
    return any(p.startswith(f"{cat}: {atome} — ") for p in perdus)


@DANS_LE_KIT
@pytest.mark.parametrize("cat", list(MOTIFS))
def test_controles_negatifs_chaque_atome_retire_rougit(cat) -> None:
    objet = _fixture()
    geles, redites = objet["atomes"], assumees(objet)
    base = corps((ROOT / ORCHESTRATEUR).read_text(encoding="utf-8"))
    assert manquants(geles, atomes(base), redites) == []
    muets = [a for a in geles[cat] if not _rougit(manquants(geles, atomes(_retirer(base, cat, a)), redites), cat, a)]
    assert geles[cat] and muets == [], f"{len(muets)} atome(s) {cat} retire(s) sans rougir : {muets[:5]}"


@DANS_LE_KIT
@pytest.mark.parametrize("cat", list(MOTIFS))
def test_controles_negatifs_chaque_occurrence_retiree_rougit(cat) -> None:
    objet = _fixture()
    geles, redites = objet["atomes"], assumees(objet)
    base = corps((ROOT / ORCHESTRATEUR).read_text(encoding="utf-8"))
    courants = atomes(base)
    serres = [a for a, n in geles[cat].items() if courants[cat][a] == n - redites.get((cat, a), 0)]
    assert serres, f"aucun atome {cat} a son compte exact : le controle ne jugerait rien"
    muets = [a for a in serres
             if not _rougit(manquants(geles, atomes(_retirer_une(base, cat, a)), redites), cat, a)]
    assert muets == [], f"{len(muets)} occurrence(s) {cat} retiree(s) sans rougir : {muets[:5]}"


@DANS_LE_KIT
def test_controles_negatifs_une_redite_non_assumee_rougit() -> None:
    objet = _fixture()
    assert objet["redites_assumees"], "aucune redite assumee : ce controle ne jugerait rien"
    perdus = manquants(objet["atomes"], _courants(), {})
    for r in objet["redites_assumees"]:
        assert _rougit(perdus, r["categorie"], r["atome"]), f"redite {r['atome']!r} retiree de la liste sans rougir"


@pytest.mark.parametrize("geste", [
    "source", "categorie_absente", "categorie_vide", "compte_faux",
    "redite_atome_inconnu", "redite_derniere_occurrence", "redite_sans_pourquoi", "redite_en_double",
])
def test_controles_negatifs_une_fixture_amputee_rougit(geste) -> None:
    objet = geler("---\nname: x\n---\nS-00000001 T-00000001 L-00000001 `c` `c` **g**\n", "synthetique")
    objet["redites_assumees"] = [{"categorie": "code", "atome": "c", "retraits": 1, "pourquoi": "redite"}]
    assert valider_fixture(objet) == []
    redite = objet["redites_assumees"][0]
    if geste == "source":
        objet["source"] = ".github/agents/autre.agent.md"
    elif geste == "categorie_absente":
        del objet["atomes"]["gras"]
    elif geste == "categorie_vide":
        objet["atomes"]["code"] = {}
    elif geste == "compte_faux":
        objet["comptes"]["S"] += 1
    elif geste == "redite_atome_inconnu":
        redite["atome"] = "inconnu"
    elif geste == "redite_derniere_occurrence":
        redite["retraits"] = 2
    elif geste == "redite_sans_pourquoi":
        redite["pourquoi"] = " "
    else:
        objet["redites_assumees"].append(dict(redite))
    assert valider_fixture(objet) != []


def test_controles_negatifs_une_def_sans_frontmatter_est_refusee() -> None:
    with pytest.raises(ValueError):
        corps("pas de frontmatter\n")


# --- re-gel --------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--regeler" or not argv[1].strip():
        print(f"usage : {REGELER}", file=sys.stderr)
        return 2
    neuf = geler((ROOT / ORCHESTRATEUR).read_text(encoding="utf-8"), argv[1].strip())
    ancien = _fixture()["atomes"] if FIXTURE.is_file() else {}
    for cat in MOTIFS:
        avant, apres = Counter(ancien.get(cat, {})), Counter(neuf["atomes"][cat])
        for a in sorted(set(avant) | set(apres)):
            if avant[a] > apres[a]:
                print(f"RETIRE  {cat}: {a} ({avant[a]} -> {apres[a]})")
            elif apres[a] > avant[a]:
                print(f"AJOUTE  {cat}: {a} ({avant[a]} -> {apres[a]})")
    with open(FIXTURE, "w", encoding="utf-8", newline="\n") as f:
        f.write(serialiser(neuf))
    print(f"fixture re-gelee : {FIXTURE.relative_to(ROOT).as_posix()} ({neuf['gele_a']}) ; redites_assumees videe")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
