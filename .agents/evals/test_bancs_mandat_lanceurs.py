"""La liste des bancs portée par les lanceurs (T-01M576S8956DA9FMXY384P7EYF, lot K).

CE QU'IL JUGE, ZÉRO LLM, sur le texte RÉEL :
  (T1) « THE BENCH LIST » présent UNE fois sur chaque surface kickoff (SKILL et commande), identique
       dans les deux (blancs normalisés), hors du paragraphe THE EXEC-CRITIC MANDATE, avec les sept
       noms gardés et ses atomes (EXHAUSTIVE, forme fermée, `aucun`, PROOFS, blocs ```, sortie tracée,
       union des lots pour clôture/intégration/correction, voie directe, racine d'existence, refus
       « câblé » et NON MESURÉ sur un appel réel) ;
  (T2) trois renvois par surface kickoff, chacun DANS son étape : lancement des devs (`fournee`),
       étape qui lance exec-critic, revue de clôture ;
  (T3) la phrase de balayage (`git grep -l <basename>`, « tests that name its files ») ABSENTE des
       deux kickoff, et sa réécriture (C1) présente dans la SKILL ;
  (T4) la phrase « Bancs de nuit » présente UNE fois et identique dans les deux surfaces de nuit ;
  (T5) `.claude/workflows/workflow-fournee.js` (lanceur qui VOYAGE, lot A de
       T-01M57JS1GFPVQ93BGEFGX08FDB) : dans `promptDev`, UNE ligne qui commence par
       `BANCS: ${bancsDe(g)}`, AVANT « À FAIRE » et `${g.consigne}` (C26 : un ``` non clos de la
       consigne avalerait la ligne) ; l'ancienne prose des deux bancs ABSENTE ; ARGS cite `bancs:`
       OBLIGATOIRE ; aucune liste `BANCS_DEFAUT` (l'ancien défaut portait un banc `strip:`, absent chez
       l'adoptant) ; rejoué sous node, `bancsDe` rend la liste TELLE QU'ÉCRITE, sans défaut ajouté, sans
       doublon, sans élément vide sur une virgule finale, rend `aucun | <pourquoi>` TEL QUEL, virgules
       comprises (comme le hook), et rend null (la fournée ne part pas) sur une liste absente, vide ou
       sur plusieurs lignes ;
  (T6) un mutant par atome, chacun prouvé APPLIQUÉ (le texte change), qui fait rougir `fautes` ;
  (T7) PARITÉ (intégration de T-01M57JS1GFPVQ93BGEFGX08FDB) : sur un même corpus de mandats, le
       pré-contrôle du lanceur (`fautesArgs`, qui rejoue `jugeMandat` sur le mandat RENDU) et le VRAI
       hook `.claude/hooks/bancs-mandat.sh` (déf `dev-mono`, racine = ce dépôt) rendent le MÊME verdict —
       ``` refermée par ~~~, clôture à tabulation, `aucun | court`, `aucun` seul, item à espace, raison
       `aucun` à virgule, gabarit, seconde ligne `BANCS:` ou `BANCS-SANS-BORNE:` dans la consigne, borne
       des dix caractères comptée en points de code (9 / 10, astraux), blancs Unicode de bord ou de tête
       (NEL, séparateurs \x1c-\x1f, U+3000) que `str.strip` ôte et `String.trim` non… ;
       l'écart NOMMÉ, seul admis : un banc absent du disque, que le hook refuse et que le lanceur ne peut
       pas voir ; un mutant par règle du juge du lanceur fait apparaître un écart.
Les valeurs attendues sont ÉCRITES ICI, jamais extraites d'une surface (L-00000261).
CE QU'IL NE PROUVE PAS : qu'un lanceur passe la ligne, ni que la liste couvre le dû — la consigne est
de la PROSE ; le hook `bancs-mandat` juge la forme d'un appel, ce banc ne juge que le texte.
SAUTS ANNONCÉS : (T5) saute si le lanceur est absent, et le rejeu node saute sans node, chacun avec
sa raison ; (T7) saute aussi sans bash, sans le hook ou sans l'ancre de `dev-mono` ; le lanceur, le
hook et la déf voyagent, donc (T5) et (T7) jouent aussi chez l'adoptant.
"""
from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SKILL = ".agents/skills/kickoff/SKILL.md"
CMD = ".claude/commands/kickoff.md"
KICKOFF = (SKILL, CMD)
NUIT = (".agents/skills/night/SKILL.md", ".claude/commands/night.md")
JS = ".claude/workflows/workflow-fournee.js"

TITRE = "**THE BENCH LIST (T-01M576S8956DA9FMXY384P7EYF).**"
TITRE_MANDAT = "**THE EXEC-CRITIC MANDATE"
NOMS = ("dev-mono", "dev-multi", "frontend-fidelity", "exec-critic", "critic-opus", "critic-fable",
        "critic-sonnet-max")
ATOMES = ("carries ONE line `BANCS: <exact path>[::<test>], …`", "the plan's `## Tests`",
          "no glob, no directory, no word", "no word — or `BANCS: aucun | <why>`", "if it already exists",
          "a criterion that runs the lot's new witness rides `PROOFS:`", "The list is EXHAUSTIVE",
          "the gate runs the rest", "rides its `PROOFS:`, never `BANCS:`", "never recopied from another report",
          "a line inside a ``` block does not count (~~~ alike)",
          # C4 aussi : le refus de clôture ouverte est câblé, jamais affirmé mesuré.
          "on Claude Code a fence left open, a ```sh diff hunk included, is wired to refuse the call "
          "(`cloture-ouverte`): close every fence",
          "`bancs-mandat` hook", "`BANCS-SANS-BORNE: <why>`", "`hook.warn`",
          # C3 : clôture, intégration et correction ; voie directe ; racine d'existence dite.
          "Closing review, integration exec-critic and correction pass: ONE `BANCS:` line, the deduplicated "
          "union of the delivered lots' items", "rides the mandate's `PROOFS:` line",
          "Direct path (no plan): the existing benches colocated with the write-set, or `BANCS: aucun | <why>`",
          "never in the worktree the mandate works in, which the hook cannot read",
          # C4 : le refus est câblé, jamais affirmé mesuré ; C6 : sortie à côté d'une liste refusée.
          "is wired to refuse (NOT MEASURED on a real Agent call", "refused next to a `BANCS:` line")
RENVOI = re.compile(r"`BANCS:` (?:line of|de) THE BENCH LIST")
DEV = {SKILL: "**`fournee` replaces `start`**", CMD: "**`fournee` remplace `start`**"}
EXEC = "Every exec-critic call of this step carries THE EXEC-CRITIC MANDATE (below)."
CLOTURE = ("closing review — NO TASK IS MARKED DONE WITHOUT A CRITICAL REVIEW", "FIX its findings")
INTERDITS = ("git grep -l <basename>", "tests that name its files")
REECRITE = ("The dev runs the benches of its `BANCS:` line (THE BENCH LIST) before handing back; a bench it "
            "believes owed and not listed is named under FOLLOW-UPS, never run.")
NUIT_PHRASE = ("**Bancs de nuit (T-01M576S8956DA9FMXY384P7EYF)** : chaque appel de dev ou de juge de la nuit "
               "porte la ligne `BANCS:` de « THE BENCH LIST » (`.agents/skills/kickoff/SKILL.md`).")
LIGNE_JS = "BANCS: ${bancsDe(g)}"
ANCIENNE_JS = "puis test_python_file_length.py et test_repo_walk_census.py"
SANS_DEFAUT = "BANCS_DEFAUT"


def plat(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t)).strip()


def lire(c: str) -> str:
    return (ROOT / c).read_text(encoding="utf-8")


def bornes(t: str, titre: str) -> tuple[int, int]:
    i = t.index(titre)
    j = t.find("\n\n", i)
    return i, (len(t) if j < 0 else j)


def etape_dev(t: str, marque: str) -> str:
    """Du point qui porte `marque` au prochain point numéroté de retrait 0-3, ou `#`."""
    lignes = t.split("\n")
    k = next(n for n, l in enumerate(lignes) if marque in l)
    fin = next((n for n in range(k + 1, len(lignes)) if re.match(r"^ {0,3}(\d+[a-z]?\. |#)", lignes[n])),
               len(lignes))
    return "\n".join(lignes[k:fin])


def etape(t: str, marque: str) -> str:
    """L'étape numérotée qui contient `marque` : de sa ligne `<n>. ` à la suivante de même retrait, ou `#`."""
    lignes = t.split("\n")
    k = next(n for n, l in enumerate(lignes) if marque in l)
    debut = next(n for n in range(k, -1, -1) if re.match(r"^(\s*)\d+\. ", lignes[n]))
    retrait = re.match(r"^(\s*)", lignes[debut]).group(1)
    fin = next((n for n in range(debut + 1, len(lignes))
                if re.match(rf"^{retrait}\d+\. ", lignes[n]) or lignes[n].startswith("#")), len(lignes))
    return "\n".join(lignes[debut:fin])


def corps_js(t: str, nom: str) -> str:
    debut = t.find(nom)
    return "" if debut < 0 else t[debut:t.find("\n}\n", debut)]


def fautes(textes: dict[str, str]) -> list[str]:
    f: list[str] = []
    paragraphes = {}
    for c in KICKOFF:
        t = textes[c]
        f += [f"{c} : « {x} » encore présent" for x in INTERDITS if x in plat(t).replace("`", "")]
        if t.count(TITRE) != 1:
            f.append(f"{c} : THE BENCH LIST présent {t.count(TITRE)} fois, attendu 1")
            continue
        i, j = bornes(t, TITRE)
        paragraphes[c] = p = plat(t[i:j])
        if TITRE_MANDAT in t:
            mi, mj = bornes(t, TITRE_MANDAT)
            if mi <= i < mj:
                f.append(f"{c} : THE BENCH LIST dans le paragraphe EXEC-CRITIC MANDATE")
        nommes = set(re.findall(r"\b(?:dev-mono|dev-multi|frontend-fidelity|exec-critic|critic-opus|critic-fable|"
                                r"critic-sonnet-max)\b", p))
        if nommes != set(NOMS):
            f.append(f"{c} : noms gardés {sorted(nommes)} ≠ les sept")
        f += [f"{c} : atome « {a} » absent de THE BENCH LIST" for a in ATOMES if a not in p]
        try:
            zones = {"dev": etape_dev(t, DEV[c]), "exec-critic": etape(t, EXEC)}
            pt = plat(t)
            k = pt.index(CLOTURE[0])
            zones["clôture"] = pt[k:pt.index(CLOTURE[1], k)]
        except (StopIteration, ValueError):
            f.append(f"{c} : étape d'un renvoi introuvable")
            zones = {}
        f += [f"{c} : renvoi THE BENCH LIST absent de l'étape {z}" for z, s in zones.items()
              if not RENVOI.search(plat(s))]
    if len(paragraphes) == 2 and len(set(paragraphes.values())) != 1:
        f.append("THE BENCH LIST diffère entre SKILL et commande")
    if REECRITE not in plat(textes[SKILL]):
        f.append(f"{SKILL} : phrase réécrite (C1) absente")
    for c in NUIT:
        if plat(textes[c]).count(NUIT_PHRASE) != 1:
            f.append(f"{c} : phrase « Bancs de nuit » absente, doublée ou divergente")
    if JS in textes:
        f += fautes_js(textes[JS])
    return f


def fautes_js(t: str) -> list[str]:
    f: list[str] = []
    corps = corps_js(t, "function promptDev(")
    lignes = corps.split("\n")
    bancs = [n for n, l in enumerate(lignes) if l.startswith("BANCS:")]
    if [lignes[n] for n in bancs] != [LIGNE_JS]:
        f.append(f"promptDev : lignes BANCS: {[lignes[n] for n in bancs]}, attendu [{LIGNE_JS!r}]")
    else:
        apres = "\n".join(lignes[bancs[0]:])
        if "À FAIRE :" not in apres or "${g.consigne}" not in apres:
            f.append("promptDev : la ligne BANCS: suit « À FAIRE » ou ${g.consigne} (C26)")
    if ANCIENNE_JS in t:
        f.append("workflow-fournee.js : l'ancienne prose des deux bancs est revenue")
    args = re.search(r"^//\s+bancs: \"[^\n]*", t, re.M)
    if not args:
        f.append("workflow-fournee.js : le commentaire ARGS ne cite pas `bancs:`")
    elif "OBLIGATOIRE" not in args.group(0):
        f.append("workflow-fournee.js : le commentaire ARGS ne dit pas `bancs:` OBLIGATOIRE")
    if SANS_DEFAUT in t:
        f.append("workflow-fournee.js : une liste de bancs par défaut est revenue")
    return f


HARNAIS = r"""
import { readFileSync } from 'node:fs'
const [src, cas] = [readFileSync(process.argv[2], 'utf8'), JSON.parse(readFileSync(process.argv[3], 'utf8'))]
const bancsDe = new Function(src + '\nreturn bancsDe')()
console.log(JSON.stringify(cas.map(g => bancsDe(g))))
"""
CAS = [{"id": "g1"}, {"id": "g2", "bancs": "a/test_x.py, .agents/evals/test_repo_walk_census.py"},
       {"id": "g3", "bancs": "a/test_x.py\nBANCS: b/test_y.py"},
       {"id": "g4", "bancs": "a/test_x.py, ,b/test_y.py,"},
       {"id": "g5", "bancs": " aucun | relecture de doctrine seule "},
       {"id": "g6", "bancs": "a/test_x.py, a/test_x.py"},
       {"id": "g7", "bancs": "aucun | x, a/test_x.py"},
       {"id": "g8", "bancs": " , ,"},
       {"id": "g9", "bancs": "aucun | relecture,, sans code de doctrine"}]
#: null = liste illisible : la fournée ne part pas (validation des ARGS du lanceur). `aucun | …` passe TEL
#: QUEL : le hook lit toute la valeur comme raison (g7, g9) ; sa FORME est jugée par `jugeMandat` (T7).
ATTENDU = [None, "a/test_x.py, .agents/evals/test_repo_walk_census.py", None, "a/test_x.py, b/test_y.py",
           "aucun | relecture de doctrine seule", "a/test_x.py", "aucun | x, a/test_x.py", None,
           "aucun | relecture,, sans code de doctrine"]


def node_bancs(t: str) -> list | None:
    """`bancsDe` rejoué sous node ; None sans node (saut annoncé par l'appelant)."""
    node = shutil.which("node")
    if node is None:
        return None
    src = t[t.find("const DEVS"):t.find("function chemins(")]
    with tempfile.TemporaryDirectory(prefix="bancs-js-") as d:
        for nom, contenu in (("h.mjs", HARNAIS), ("src.js", src), ("cas.json", json.dumps(CAS))):
            (Path(d) / nom).write_text(contenu, encoding="utf-8")
        r = subprocess.run([node, f"{d}/h.mjs", f"{d}/src.js", f"{d}/cas.json"], capture_output=True,
                           text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"harnais node rc={r.returncode} : {r.stderr[-600:]}")
    return json.loads(r.stdout)


def textes_reels(js: bool) -> dict[str, str]:
    out = {c: lire(c) for c in KICKOFF + NUIT}
    if js:
        out[JS] = lire(JS)
    return out


def _js():
    if not (ROOT / JS).is_file():
        pytest.skip(f"{JS} absent : volet workflow (T5) non joué")


def test_lanceurs() -> None:
    assert fautes(textes_reels(js=False)) == []


def test_workflow() -> None:
    _js()
    assert fautes_js(lire(JS)) == []


def test_workflow_node_bancs_ajoutes() -> None:
    _js()
    vu = node_bancs(lire(JS))
    if vu is None:
        pytest.skip("node absent : rejeu de bancsDe (C28) non joué")
    assert vu == ATTENDU


def remplace(t: str, vieux: str, neuf: str) -> str:
    assert t.count(vieux) == 1, f"ancre de mutant ambiguë ou absente : {vieux[:60]!r}"
    return t.replace(vieux, neuf)


def _mutants(b: dict[str, str]) -> dict[str, dict[str, str]]:
    m: dict[str, dict[str, str]] = {}
    i, j = bornes(b[SKILL], TITRE)
    para = b[SKILL][i:j]
    m["liste_une_copie"] = {**b, CMD: remplace(b[CMD], "The list is EXHAUSTIVE", "The list is indicative")}
    for nom, (vieux, neuf) in {"liste_nom_retire": ("critic-fable or ", ""),
                               "liste_atome_retire": (
                                   ", and on Claude Code a fence left open, a ```sh diff hunk included, is wired to "
                                   "refuse the call (`cloture-ouverte`): close every fence", ""),
                               "cloture_affirmee_mesuree": (
                                   "is wired to refuse the call (`cloture-ouverte`)", "refuses the call (`cloture-ouverte`)"),
                               "liste_aucun_retire": (" — or `BANCS: aucun | <why>`", ""),
                               "refus_affirme_mesure": (
                                   "is wired to refuse (NOT MEASURED on a real Agent call, guardrails § `bancs-mandat`)",
                                   "refuses"),
                               "union_retiree": (" the deduplicated union of the delivered lots' items;", ""),
                               "voie_directe_retiree": (
                                   " Direct path (no plan): the existing benches colocated with the write-set, "
                                   "or `BANCS: aucun | <why>`.", "")}.items():
        m[nom] = {**b, **{c: remplace(b[c], vieux, neuf) for c in KICKOFF}}
    m["liste_absente_skill"] = {**b, SKILL: b[SKILL].replace(para + "\n\n", "")}
    m["liste_doublee"] = {**b, CMD: b[CMD] + "\n\n" + para + "\n"}
    m["liste_dans_mandat"] = {**b, **{c: remplace(b[c].replace(para + "\n\n", ""), TITRE_MANDAT,
                                                  TITRE_MANDAT + " " + para.replace("\n", " ")) for c in KICKOFF}}
    renvois = {SKILL: {"dev": (" Each dev\n        mandate carries the `BANCS:` line of THE BENCH LIST (below).", ""),
                       "exec": ("   The exec-critic mandate also carries the `BANCS:` line of THE BENCH LIST (below).\n", ""),
                       "cloture": (" Its mandate carries the `BANCS:` line of THE BENCH LIST\n    (below).", "")},
               CMD: {"dev": ("      Chaque mandat de dev porte la ligne `BANCS:` de THE BENCH LIST (ci-dessous).\n", ""),
                     "exec": ("   The exec-critic mandate also carries the `BANCS:` line of THE BENCH LIST (below).\n", ""),
                     "cloture": ("   Its mandate carries the `BANCS:` line of THE BENCH LIST (below).\n", "")}}
    for c, rs in renvois.items():
        for z, (vieux, neuf) in rs.items():
            m[f"renvoi_{z}_{Path(c).parent.name}"] = {**b, c: remplace(b[c], vieux, neuf)}
    m["phrase_skill_restauree"] = {**b, SKILL: remplace(
        b[SKILL], "The dev runs the benches of its\n`BANCS:` line (THE BENCH LIST) before handing back; a bench it "
        "believes owed and not listed is named\nunder FOLLOW-UPS, never run.",
        "The dev runs the tests that name\nits files (`git grep -l <basename>` under the test and eval directories) "
        "before handing back.")}
    m["balayage_dans_commande"] = {**b, CMD: b[CMD] + "\nThe dev runs `git grep -l <basename>` first.\n"}
    nuit_skill, nuit_cmd = NUIT
    m["nuit_une_copie"] = {**b, nuit_cmd: remplace(b[nuit_cmd], "chaque appel de dev ou de juge",
                                                   "chaque appel de dev")}
    m["nuit_absente_skill"] = {**b, nuit_skill: remplace(b[nuit_skill], "**Bancs de nuit (T-01M576S8956DA9FMXY384P7EYF)**",
                                                         "**Bancs (nuit)**")}
    if JS in b:
        js = b[JS]
        for nom, (vieux, neuf) in {
                "js_ligne_retiree": ("BANCS: ${bancsDe(g)}\n\n", ""),
                "js_ligne_apres_consigne": ("BANCS: ${bancsDe(g)}\n\nÀ FAIRE :\n${g.consigne}\n",
                                            "À FAIRE :\n${g.consigne}\n\nBANCS: ${bancsDe(g)}\n"),
                "js_ligne_doublee": ("À FAIRE :\n${g.consigne}\n", "À FAIRE :\n${g.consigne}\nBANCS: x\n"),
                "js_prose_restauree": ("Témoin : ${g.tests}.", "Tests ciblés : ${g.tests}, " + ANCIENNE_JS + "."),
                "js_args_retire": ("//                bancs: \"<items de la ligne du lot sous ## Tests, OBLIGATOIRE",
                                   "//              } ], \"<items de la ligne du lot sous ## Tests, OBLIGATOIRE"),
                "js_obligatoire_retire": ("sous ## Tests, OBLIGATOIRE :", "sous ## Tests, facultatif :"),
                "js_defaut_reintroduit": ("function bancsDe(g) {\n",
                                          "const BANCS_DEFAUT = ['.agents/evals/test_repo_walk_census.py']\n"
                                          "function bancsDe(g) {\n")}.items():
            m[nom] = {**b, JS: remplace(js, vieux, neuf)}
    return m


def test_mutants() -> None:
    base = textes_reels(js=(ROOT / JS).is_file())
    survivants = []
    for nom, mut in _mutants(base).items():
        assert mut != base, f"mutant {nom} sans effet sur le texte"
        if not fautes(mut):
            survivants.append(nom)
    assert survivants == [], f"mutants SURVIVANTS : {survivants}"


#: Un mutant par règle de `bancsDe` ; le lot A (T-01M57JS1GFPVQ93BGEFGX08FDB) a retiré le défaut ajouté (C28).
MUTANTS_NODE = {
    "element_vide_garde": (".filter(item => item !== '')", ""),
    "aucun_decoupe": ("  if (valeur.startsWith(AUCUN)) return valeur\n", ""),
    "ligne_unique": ("  if (typeof g.bancs !== 'string' || !/^[^\\r\\n]+$/.test(g.bancs.trim())) return null\n",
                     "  if (typeof g.bancs !== 'string') return null\n"),
    "doublon_garde": ("[...new Set(valeur", "[...Array.from(valeur"),
    "defaut_ajoute": ("  return items.length ? items.join(', ') : null\n",
                      "  return ['.agents/evals/test_repo_walk_census.py', ...items].join(', ')\n"),
    "defaut_si_vide": ("items.length ? items.join(', ') : null",
                       "items.length ? items.join(', ') : '.agents/evals/test_repo_walk_census.py'"),
}


@pytest.mark.parametrize("nom", sorted(MUTANTS_NODE))
def test_mutant_node_bancs(nom: str) -> None:
    _js()
    vieux, neuf = MUTANTS_NODE[nom]
    vu = node_bancs(remplace(lire(JS), vieux, neuf))
    if vu is None:
        pytest.skip(f"node absent : mutant {nom} non joué")
    assert vu != ATTENDU, f"mutant SURVIVANT : {nom}"


# --- (T7) parité du pré-contrôle du lanceur avec le VRAI hook bancs-mandat ----------------------------

HOOK = ".claude/hooks/bancs-mandat.sh"
DEF_DEV = ".claude/agents/dev-mono.md"
ANCRE = "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)"
#: Deux bancs qui existent partout où ce fichier tourne : lui-même et le banc du hook.
BANC = ".agents/evals/test_bancs_mandat_lanceurs.py"
BANC_HOOK = ".claude/hooks/bancs-mandat.test.sh"
#: (nom, consigne, bancs) : le lanceur et le hook rendent le MÊME verdict sur le mandat rendu.
PARITE = [
    ("valide", "c", BANC),
    ("deux_bancs", "c", f"{BANC}, {BANC_HOOK}"),
    ("doublon_et_virgule_finale", "c", f"{BANC}, {BANC},"),
    ("item_id_de_test", "c", f"{BANC}::test_lanceurs"),
    ("backticks_refermee_par_tildes", "```sh\nx\n~~~", BANC),
    ("cloture_ouverte_a_tabulation", "\t```\nx", BANC),
    ("cloture_fermee_a_tabulation", "```\nx\n\t```", BANC),
    ("tildes_dans_backticks", "```\n~~~\n```", BANC),
    ("aucun_court", "c", "aucun | court"),
    ("aucun_seul", "c", "aucun"),
    ("item_a_espace", "c", "a b/test_x.py"),
    ("item_a_backtick", "c", f"`{BANC}`"),
    ("aucun_raison_a_virgule", "c", "aucun | relecture de doctrine, sans code"),
    ("aucun_gabarit", "c", "aucun | <pourquoi> à écrire"),
    ("aucun_apres_un_banc", "c", f"{BANC}, aucun | relecture de doctrine"),
    ("pas_un_banc", "c", "README.md"),
    ("segment_point", "c", "./" + BANC),
    ("seconde_ligne_bancs_dans_la_consigne", "x\nBANCS: " + BANC, BANC),
    ("ligne_bancs_dans_une_cloture", "```\nBANCS: " + BANC + "\n```", BANC),
    ("sans_borne_dans_la_consigne", "BANCS-SANS-BORNE: je ne veux pas de liste", BANC),
    # Borne de `aucun | <pourquoi>` (dix caractères = dix points de code) et blancs Unicode : mêmes deux côtés.
    ("aucun_neuf_caracteres", "c", "aucun | 123456789"),
    ("aucun_dix_caracteres", "c", "aucun | 1234567890"),
    ("aucun_cinq_astraux", "c", "aucun | " + "\U0001F600" * 5),
    ("aucun_dix_astraux", "c", "aucun | " + "\U0001F600" * 10),
    ("aucun_bords_nel", "c", "aucun | court" + "\x85" * 5),
    ("aucun_bords_separateurs", "c", "aucun | court\x1c\x1d\x1e\x1f\x1c"),
    ("aucun_bords_ideographiques", "c", "aucun | court" + "　" * 5),
    ("item_bord_nel", "c", "\x85" + BANC + "\x85"),
    ("cloture_ouverte_separateur", "\x1c```\nx", BANC),
    ("cloture_ouverte_ideographique", "　```\nx", BANC),
    ("cloture_ouverte_nel", "\x85~~~\nx", BANC),
    ("sans_borne_cinq_astraux", "BANCS-SANS-BORNE: " + "\U0001F600" * 5, BANC),
    ("sans_borne_dix_astraux", "BANCS-SANS-BORNE: " + "\U0001F600" * 10, BANC),
]
#: L'écart NOMMÉ, le seul admis : l'existence d'un banc sur disque, que le hook lit et un script Workflow non.
ECART_NOMME = ("banc_absent", "c", ".agents/evals/test_absent_du_depot_zz.py")
HARNAIS_PARITE = r"""
import { readFileSync } from 'node:fs'
const src = readFileSync(process.argv[2], 'utf8')
const cas = JSON.parse(readFileSync(process.argv[3], 'utf8'))
const [i, j] = [src.indexOf('const A = args'), src.indexOf('// VALIDATION :')]
if (i < 0 || j < i) throw new Error('bornes du lanceur introuvables')
const AF = Object.getPrototypeOf(async function () {}).constructor
const sorties = []
for (const args of cas) {
  const f = await new AF('args', 'agent', 'phase', 'log', src.slice(i, j) + '\nreturn { fautesArgs, promptDev }')(
    args, null, () => {}, () => {})
  sorties.push({ fautes: f.fautesArgs(args), prompt: f.promptDev(args.grappes[0]) })
}
process.stdout.write(JSON.stringify(sorties))
"""
#: Un mutant par règle du juge du lanceur : chacun doit faire apparaître au moins un écart avec le hook.
MUTANTS_PARITE = {
    "cloture_toute_marque": ("&& marque === (cloture || marque)", ""),
    "blancs_de_tete_ignores": ("[...ligne.replace(BLANCS_DEBUT, '')]", "[...ligne]"),
    "aucun_sans_longueur": ("].length >= 10", "].length >= 1"),
    "gabarit_ignore": ("return gabarit(valeur.slice(AUCUN.length)) ? 'raison-gabarit : aucun' : null", "return null"),
    "item_sans_forme": ("if (item.includes('`') || !ITEM_BANC.test(item)) return", "if (false) return"),
    "segments_libres": ("if (segments.some(s => s === '' || s === '.' || s === '..')) return", "if (false) return"),
    "nom_de_banc_libre": ("if (!(NOM_BANC.test(nom) || rust)) return", "if (false) return"),
    "deux_lignes_admises": ("if (lignes.length !== 1 || !lignes[0])", "if (lignes.length < 1 || !lignes[0])"),
    "ambigu_admis": ("  if (sansBorne.length && visibles.some(l => l.startsWith('BANCS: '))) "
                     "return 'ambigu : BANCS-SANS-BORNE'\n", ""),
    "juge_non_appele": ("const refus = f.length === avant ? jugeMandat(promptDev(g)) : null", "const refus = null"),
    # Blancs Unicode et points de code : chaque règle tombée sur la sémantique JS par défaut fait un écart.
    "bords_trim_js": ("const valeur = lignes[0].replace(BLANCS_BORDS, '')", "const valeur = lignes[0].trim()"),
    "longueur_utf16": ("[...valeur.slice(AUCUN.length)].length >= 10", "valeur.slice(AUCUN.length).length >= 10"),
    "sans_borne_utf16": ("([^\\n]{10,})$/u", "([^\\n]{10,})$/"),
    "blancs_debut_js": ("const BLANCS_DEBUT = new RegExp(`^${BLANCS_PY}+`)", "const BLANCS_DEBUT = /^\\s+/"),
}


def _parite_prete() -> tuple[str, str]:
    _js()
    node, bash = shutil.which("node"), shutil.which("bash")
    if node is None or bash is None:
        pytest.skip("node ou bash absent : parité lanceur/hook (T7) non jouée")
    if not (ROOT / HOOK).is_file() or ANCRE not in (ROOT / DEF_DEV).read_text(encoding="utf-8"):
        pytest.skip(f"{HOOK} absent ou {DEF_DEV} sans l'ancre : parité (T7) non jouée")
    return node, bash


def _args_parite(consigne: str, bancs: str) -> dict:
    return {"base": "b0b0b0b", "label": "BANC", "session": "https://claude.ai/code/session_banc",
            "grappes": [{"id": "T-1", "branche": "wt/T-1", "agentType": "dev-mono", "taches": ["T-1"],
                         "writeset": ["f"], "consigne": consigne, "tests": "python3 -m pytest -q x/test_x.py",
                         "bancs": bancs}]}


def lanceur_parite(source: str) -> list[dict]:
    """`fautesArgs` et `promptDev` du lanceur `source`, sous node, sur PARITE puis ECART_NOMME."""
    node, _ = _parite_prete()
    cas = [_args_parite(c, b) for _, c, b in (*PARITE, ECART_NOMME)]
    with tempfile.TemporaryDirectory(prefix="bancs-parite-") as d:
        for nom, contenu in (("h.mjs", HARNAIS_PARITE), ("src.js", source), ("cas.json", json.dumps(cas))):
            (Path(d) / nom).write_text(contenu, encoding="utf-8")
        r = subprocess.run([node, f"{d}/h.mjs", f"{d}/src.js", f"{d}/cas.json"], capture_output=True,
                           text=True, timeout=60)
    assert r.returncode == 0, f"harnais node rc={r.returncode} : {r.stderr[-600:]}"
    return json.loads(r.stdout)


@functools.lru_cache(maxsize=1)
def hook_parite() -> tuple[bool, ...]:
    """Le VRAI hook sur chaque mandat RENDU par le vrai lanceur : True = admis (rc 0), False = refusé (rc 2)."""
    _, bash = _parite_prete()
    verdicts = []
    with tempfile.TemporaryDirectory(prefix="bancs-parite-ev-") as ev:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "AGENTS_EVENTS_DIR": ev}
        for sortie in lanceur_parite(lire(JS)):
            charge = json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "dev-mono",
                                                                      "prompt": sortie["prompt"]}}).encode()
            r = subprocess.run([bash, str(ROOT / HOOK)], input=charge, capture_output=True, env=env,
                               cwd=str(ROOT), timeout=60)
            assert r.returncode in (0, 2) and b"COVERAGE DEGRADED" not in r.stderr, r.stderr[-400:]
            verdicts.append(r.returncode == 0)
    return tuple(verdicts)


def ecarts_parite(source: str) -> list[str]:
    lance = [not s["fautes"] for s in lanceur_parite(source)]
    hook = hook_parite()
    return [nom for (nom, _, _), l, h in zip(PARITE, lance, hook) if l != h]


def test_parite_hook_lanceur() -> None:
    hook = hook_parite()
    assert True in hook[:len(PARITE)] and False in hook[:len(PARITE)], "corpus vacant : un seul verdict du hook"
    assert ecarts_parite(lire(JS)) == []


def test_parite_ecart_nomme_existence_du_banc() -> None:
    sortie = lanceur_parite(lire(JS))[-1]
    assert sortie["fautes"] == [] and hook_parite()[-1] is False, (
        "l'écart nommé a changé : le lanceur voit-il le disque, ou le hook ne lit-il plus l'existence ?")


@pytest.mark.parametrize("nom", sorted(MUTANTS_PARITE))
def test_parite_mutant(nom: str) -> None:
    _parite_prete()
    vieux, neuf = MUTANTS_PARITE[nom]
    assert ecarts_parite(remplace(lire(JS), vieux, neuf)) != [], f"mutant SURVIVANT : {nom}"
