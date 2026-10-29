"""Témoin du retrait de la route de dev locale (T-01M5PCCHMWXTRCM5QJT8J5KNEH, décisions pilote
S-01M5PCD282N11RGE73BMQK7M70 et S-01M5PV5CWNB6Z64RWFH8SZJ9QN).

CE QU'IL JUGE, ZÉRO LLM, sur l'arbre SUIVI (`git grep`, fichiers suivis seuls) :
  (W-1) ÉGALITÉ LIGNE À LIGNE : chaque ligne qui porte un terme du motif, hors des préfixes
        d'histoire, tombe dans UNE exemption et une seule ;
  (W-3) chaque exemption VIT : une exemption de LIGNE couvre exactement une ligne (0 = décorative,
        2 = ambiguë) ; une entrée de journal REQUISE a son titre gras une fois et couvre au moins une
        ligne (sinon décorative) ;
  (W-2) les 16 chemins retirés ne sont ni suivis ni sur le disque ;
  (W-4) la ligne d'état n'a plus de champ de route : `M | no active task | 0% ctx | $1.50` ;
  (W-5) le marqueur local de la route reste git-ignoré (un fichier resté chez quelqu'un ne se
        commite pas).
NOM ET CORPS SANS AUCUN TERME CHERCHÉ : motif, fragments, titres et chemins se construisent par
concaténation de littéraux, sinon ce fichier se trouverait lui-même. Une exemption de LIGNE est
ancrée sur un fragment, une exemption d'ENTRÉE sur le TITRE GRAS de l'entrée (paragraphe jusqu'à la
première ligne vide) : aucun numéro de ligne, la base peut bouger.
CE QU'IL NE PROUVE PAS : qu'une phrase réécrite SANS terme dise vrai ; ni un fichier non suivi.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: le marqueur du kit ne voyage pas ; son absence déclenche ce skip de module.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
pytestmark = pytest.mark.skipif(not EST_LE_KIT, reason="SAUT ANNONCE : `.agents/IS_THE_KIT` absent (projet adoptant)")

Q = "q" "wen"
MOTIF = "|".join((Q, "dev-" "route", "dev_" "route", "local-" "llm"))
# Histoire, jamais éditée (sous .agents/state/ : jamais gates).
HISTOIRE = tuple(".agents/state/" + d + "/" for d in ("board", "specs", "memory", "events", "index", "local")) + (
    "runs/", "docs/tasks/", "docs/interne/", "retro/", "docs/design/20", "PLAN-ETAT-DETAIL.md")
# Exemptions de LIGNE : (nom, fichier, fragment), exactement une ligne chacune.
LIGNES = (
    ("X1", ".agents/evals/test_charge_poste_fournee_kit.py", '"mcp__local-' 'llm__review_diff"'),
    ("X2", ".agents/evals/test_no_compact_case.py", "`.agents/bin/" + Q + "-dev.sh` compris"),
    ("X3", ".agents/evals/test_docs_only_route_contract.py", '"`.agents/state/local/DEV_' 'ROUTE`", "T-00000750"'),
)
J1 = "**Un dev ou un juge ne joue que les bancs nommés dans son mandat.**"
J2 = "**`/" + Q + "-dev` : un pont plus fiable, et la garde dite exactement.**"
J3 = "**`/" + Q + "-dev` et la route de dev locale sont retirés : le contrat passe en `0.6.0`.**"
KIT, ADOPTANT = "CHANGELOG.md", ".agents/adopter-docs/CHANGELOG.md"
# Exemptions d'ENTRÉE : (nom, fichier, titre gras, requise). J3 n'arrive chez l'adoptant qu'à la coupe.
ENTREES = (
    ("J1", KIT, J1, True), ("J2", KIT, J2, True), ("J3", KIT, J3, True),
    ("J2", ADOPTANT, J2, True), ("J3", ADOPTANT, J3, True),
)
RETIRES = (
    ".agents/bin/" + Q + "-dev.sh", ".claude/hooks/dev-" "route.sh", ".claude/hooks/dev-" "route.test.sh",
    ".agents/ref/" + Q.upper() + "_DEV.md", ".agents/ref/" + Q.upper() + "_DEV_CONVENTIONS.md",
    *(".agents/evals/" + n for n in (
        Q + "_dev_temoin.py", "test_" + Q + "_dev_temoin.py", "test_" + Q + "_dev_worktree.py",
        "test_bancs_" + Q + "_dev.py", "test_" + Q + "_dev_contract.py", "test_" + Q + "_dev_contract_revue.py",
        "test_" + Q + "_dev_pont_1236.py", "test_" + Q + "_dev_pont_1236_securite.py",
        "test_" + Q + "_dev_pont_fiabilite.py")),
    ".claude/commands/" + Q + "-dev.md", ".agents/skills/" + Q + "-dev/SKILL.md",
)
MARQUEUR = ".agents/state/local/DEV_" "ROUTE"


def _git(*args: str) -> subprocess.CompletedProcess:
    if shutil.which("git") is None:
        pytest.skip("SAUT ANNONCE : git absent, l'arbre suivi n'est pas lisible")
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120, check=False)


def occurrences() -> list[tuple[str, int, str]]:
    """(fichier, ligne, texte) de chaque ligne SUIVIE qui porte un terme, hors histoire."""
    exclus = [":(exclude)" + p + ("*" if not p.endswith("/") else "") for p in HISTOIRE]
    out = _git("grep", "-z", "-n", "-I", "-i", "-E", MOTIF, "--", ".", *exclus)
    assert out.returncode in (0, 1), f"git grep rc {out.returncode} : {out.stderr[:300]}"
    hits = []
    for ligne in out.stdout.splitlines():
        chemin, numero, texte = ligne.split("\0", 2)
        hits.append((chemin, int(numero), texte))
    return hits


def paragraphes(lire) -> dict[tuple[str, str], tuple[int, list[range]]]:
    """(fichier, titre) -> (nombre de titres, plages de lignes de chaque paragraphe titré)."""
    vu: dict[tuple[str, str], tuple[int, list[range]]] = {}
    for _nom, fichier, titre, _requise in ENTREES:
        texte = lire(fichier)
        lignes = texte.splitlines() if texte is not None else []
        plages = []
        for i, l in enumerate(lignes, 1):
            if l.strip() == titre:
                fin = i
                while fin < len(lignes) and lignes[fin].strip():
                    fin += 1
                plages.append(range(i, fin + 1))
        vu[(fichier, titre)] = (len(plages), plages)
    return vu


def _lire(fichier: str) -> str | None:
    p = ROOT / fichier
    return p.read_text(encoding="utf-8") if p.is_file() else None


def bilan(hits, paras) -> tuple[list[str], list[str]]:
    """(fautes W-1, fautes W-3) : lignes non ou doublement exemptées ; exemptions mortes ou ambiguës."""
    w1: list[str] = []
    par_ligne = {nom: 0 for nom, _f, _x in LIGNES}
    par_entree = {(nom, f): 0 for nom, f, _t, _r in ENTREES}
    for chemin, numero, texte in hits:
        couvre = [nom for nom, f, frag in LIGNES if f == chemin and frag in texte]
        for nom in couvre:
            par_ligne[nom] += 1
        for nom, f, titre, _r in ENTREES:
            if f == chemin and any(numero in p for p in paras[(f, titre)][1]):
                couvre.append(nom)
                par_entree[(nom, f)] += 1
        if len(couvre) != 1:
            etat = "non exemptée" if not couvre else f"ambiguë {couvre}"
            w1.append(f"{chemin}:{numero} {etat} : {texte.strip()[:160]}")
    w3: list[str] = []
    for nom, f, _x in LIGNES:
        if par_ligne[nom] != 1:
            w3.append(f"{nom} ({f}) : {par_ligne[nom]} ligne(s) — " + ("décorative" if not par_ligne[nom] else "ambiguë"))
    for nom, f, titre, requise in ENTREES:
        n = paras[(f, titre)][0]
        if n > 1:
            w3.append(f"{nom} ({f}) : titre {n} fois — ambiguë")
        elif requise and (n == 0 or par_entree[(nom, f)] == 0):
            w3.append(f"{nom} ({f}) : entrée requise " + ("absente" if n == 0 else "sans ligne qui matche") + " — décorative")
    return w1, w3


def test_w1_chaque_ligne_tombe_dans_une_exemption() -> None:
    w1, _w3 = bilan(occurrences(), paragraphes(_lire))
    assert not w1, f"{len(w1)} ligne(s) hors exemption :\n" + "\n".join(w1[:60])


def test_w3_chaque_exemption_vit() -> None:
    _w1, w3 = bilan(occurrences(), paragraphes(_lire))
    assert not w3, "exemption(s) morte(s) ou ambiguë(s) :\n" + "\n".join(w3)


def test_w2_chemins_retires_absents() -> None:
    assert len(RETIRES) == len(set(RETIRES)) == 16, RETIRES
    suivis = _git("ls-files", "--", *RETIRES).stdout.split()
    sur_disque = [p for p in RETIRES if (ROOT / p).exists()]
    assert not suivis and not sur_disque, f"suivis : {suivis} ; sur le disque : {sur_disque}"


def test_w4_ligne_d_etat_sans_champ_de_route() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("SAUT ANNONCE : bash absent, la ligne d'état n'est pas jouée")
    with tempfile.TemporaryDirectory(prefix="w4-") as racine:
        env = {"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": racine}
        out = subprocess.run([bash, str(ROOT / ".claude" / "statusline.sh")],
                             input='{"model":{"display_name":"M"},"cost":{"total_cost_usd":1.5}}',
                             capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, check=False)
    assert out.returncode == 0, out.stderr[:300]
    assert out.stdout == "M | no active task | 0% ctx | $1.50", repr(out.stdout)


def test_w5_marqueur_local_reste_ignore() -> None:
    out = _git("check-ignore", "-q", MARQUEUR)
    assert out.returncode == 0, f"{MARQUEUR} n'est plus git-ignoré (rc {out.returncode})"
