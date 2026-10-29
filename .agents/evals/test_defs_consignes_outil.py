"""CONSIGNES D'OUTIL DES DÉFS DEV — T-01M5PY2DZ8W7744BMDNVHB3FZ6, lot A (R4 de l'audit 2026-10-24).

Clause : chaque déf dev (dev-mono, dev-multi, frontend-fidelity) porte, JUSTE AVANT le titre
« Before you hand back » de son hôte, un bloc « Tool hygiene » de cinq lignes au vocabulaire
de l'hôte ; la puce ÉCONOMIE d'AGENTS.md porte la forme worktree de sa clause (1).

* Les atomes sont cherchés dans le BLOC extrait (de son titre à la PREMIÈRE occurrence de
  « Before you hand back », jamais `rfind` : frontend-fidelity en porte une seconde dans GRID),
  jamais dans le fichier (constat K1 du critic-2).
* Portée (L-00000079) : Claude dit « refused by Claude Code (measured) » ; Codex, Gemini,
  Copilot disent l'hygiène et ne portent jamais « (measured) ». Kimi = Claude à l'octet, jugé
  par `kimi_egale_claude` de test_bancs_bornes_devs.py (SYM-22146), jamais par ses atomes.
* AGENTS.md : les atomes sont cherchés dans le SEGMENT NEUF de la puce (entre « Gemini inerte
  (G0) » et « ; (2) `git sparse-checkout` »), deux d'entre eux étant déjà ailleurs (K2).
* Racine : `CONSIGNES_OUTIL_ROOT` (défaut : le dépôt). Les 16 chemins sont NOMMÉS, sans glob :
  un chemin absent rougit, une racine vide rougit (K5).
* Interdits dans le bloc (K6) : les ancres d'autres bancs (« Before you hand back »,
  « Capture each output whole », « Capture outputs whole », « What you return »).
Borne : le banc juge la présence et la place des atomes, jamais le sens de la paraphrase.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("CONSIGNES_OUTIL_ROOT") or DEPOT)

NOMS = ("dev-mono", "dev-multi", "frontend-fidelity")
CHEMINS = {
    "claude": ".claude/agents/{}.md",
    "codex": ".codex/agents/{}.toml",
    "gemini": ".gemini/agents/{}.md",
    "copilot": ".github/agents/{}.agent.md",
    "kimi": ".kimi-code/agents/{}.md",
}
ROUTEUR = "AGENTS.md"
TITRE = "Tool hygiene"
ANCRE = "Before you hand back"
INTERDITS = (ANCRE, "Capture each output whole", "Capture outputs whole", "What you return")

COMMUNS = (
    "one plain command per call",
    'isolation: "worktree"',
    "git -C /tmp/cadre-",
    "quote every glob",
    "*.tfstate",
    "iac_guard",
    "never route around",
)
PORTEE_CLAUDE = "refused by Claude Code (measured)"
PORTEE_AUTRES = "hygiene here; the refusal is Claude Code's, not measured on this host"
PROPRES = {
    "claude": (PORTEE_CLAUDE, "AGENTS.md § ÉCONOMIE (1)", "Read before Edit: on Claude Code (measured)",
               "File has not been read"),
    "codex": (PORTEE_AUTRES, "AGENTS.md ECONOMIE (1)", "read the lines before apply_patch"),
    "gemini": (PORTEE_AUTRES, "AGENTS.md § ÉCONOMIE (1)", "`read_file` before `replace`"),
    "copilot": (PORTEE_AUTRES, "AGENTS.md § ÉCONOMIE (1)", "`read` before `edit`"),
}
LIGNES_BLOC = 5  # les cinq puces sous le titre

PUCE = "- **ÉCONOMIE DE LA MACHINE"
SEG_DEBUT = "Gemini inerte (G0)"
SEG_FIN = "; (2) `git sparse-checkout`"
ATOMES_ROUTEUR = (
    'isolation: "worktree"',
    "rev-parse --show-toplevel",
    "chemin littéral",
    "checkout -f --detach",
    "DÉCLARATIF",
    "ET SEULEMENT si",
)
# « mesuré » se cherche APRÈS « checkout -f --detach » : le « (mesuré) » du refus de la forme
# composée, plus haut dans le segment, ne vaut pas mesure du checkout (mutant survivant, exec-critic R4).
ATOME_APRES, MESURE = "checkout -f --detach", "mesuré"


def _kimi_egale_claude():
    """`kimi_egale_claude` de test_bancs_bornes_devs.py (SYM-22146), chargé par son chemin."""
    spec = importlib.util.spec_from_file_location(
        "_bancs_bornes_devs", DEPOT / ".agents" / "evals" / "test_bancs_bornes_devs.py"
    )
    module = sys.modules[spec.name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.kimi_egale_claude


KIMI_EGALE_CLAUDE = _kimi_egale_claude()


def bloc(texte: str) -> str | None:
    """Le bloc de son titre à la PREMIÈRE ancre ; None si le titre manque, est doublé, ou suit l'ancre."""
    if texte.count(TITRE) != 1:
        return None
    debut, fin = texte.find(TITRE), texte.find(ANCRE)
    if fin < 0 or debut > fin:
        return None
    return texte[debut:fin]


def fautes_def(hote: str, nom: str, texte: str) -> list[str]:
    """Les fautes d'une déf non Kimi ; liste vide = bloc tenu."""
    seg = bloc(texte)
    if seg is None:
        return [f"{nom} {hote} : position (bloc absent, doublé ou après « {ANCRE} »)"]
    out: list[str] = []
    corps = seg.split("\n", 1)[1] if "\n" in seg else ""  # le titre ne vaut pas atome
    # Le préfixe de l'ancre (`## `, `**`) reste en fin de bloc : seules les puces comptent.
    puces = [ligne for ligne in corps.splitlines() if ligne.strip()]
    if len(puces) - (1 if puces and not puces[-1].startswith("- ") else 0) != LIGNES_BLOC:
        out.append(f"{nom} {hote} : position (bloc de {len(puces)} lignes, {LIGNES_BLOC} attendues)")
    out += [f"{nom} {hote} : {a!r} absent" for a in COMMUNS + PROPRES[hote] if a not in corps]
    if hote != "claude" and "(measured)" in seg:
        out.append(f"{nom} {hote} : portée Claude hors Claude")
    if hote == "codex" and not seg.isascii():
        out.append(f"{nom} {hote} : bloc non ASCII")
    out += [f"{nom} {hote} : ancre d'un autre banc {i!r} dans le bloc" for i in INTERDITS[1:] if i in seg]
    return out


def segment_routeur(texte: str) -> str | None:
    """Le segment neuf de la puce ÉCONOMIE ; None si la puce manque, est doublée, ou sans bornes."""
    lignes = [ligne for ligne in texte.splitlines() if ligne.startswith(PUCE)]
    if len(lignes) != 1:
        return None
    ligne = lignes[0]
    debut, fin = ligne.find(SEG_DEBUT), ligne.find(SEG_FIN)
    if debut < 0 or fin < debut:
        return None
    return ligne[debut + len(SEG_DEBUT):fin]


def fautes(racine: Path) -> list[str]:
    """Toutes les fautes sous `racine` ; liste vide = clause tenue sur les 16 chemins nommés."""
    out: list[str] = []
    textes: dict[tuple[str, str], str] = {}
    for hote, motif in CHEMINS.items():
        for nom in NOMS:
            chemin = racine / motif.format(nom)
            if not chemin.is_file():
                out.append(f"{nom} {hote} : fichier absent ({chemin})")
                continue
            textes[(hote, nom)] = chemin.read_text(encoding="utf-8")
    for (hote, nom), texte in sorted(textes.items()):
        if hote != "kimi":
            out += fautes_def(hote, nom, texte)
    for nom in NOMS:
        kimi, claude = textes.get(("kimi", nom)), textes.get(("claude", nom))
        if kimi is not None and claude is not None and not KIMI_EGALE_CLAUDE(kimi, claude):
            out.append(f"{nom} kimi : diffère de Claude")
    routeur = racine / ROUTEUR
    if not routeur.is_file():
        return out + [f"AGENTS.md : fichier absent ({routeur})"]
    seg = segment_routeur(routeur.read_text(encoding="utf-8"))
    if seg is None:
        return out + ["AGENTS.md : puce ÉCONOMIE ou bornes du segment introuvables"]
    out += [f"AGENTS.md : {a!r} absent du segment worktree" for a in ATOMES_ROUTEUR if a not in seg]
    pos = seg.find(ATOME_APRES)
    if pos >= 0 and MESURE not in seg[pos + len(ATOME_APRES):]:
        out.append(f"AGENTS.md : {MESURE!r} absent après {ATOME_APRES!r} dans le segment worktree")
    return out


# --- la clause, sur la racine jugée --------------------------------------------------------------

def test_la_clause_est_tenue():
    assert fautes(ROOT) == []


# --- mutants, sur une copie sous tmp_path, jamais dans l'arbre ----------------------------------

def _copie(tmp_path: Path) -> Path:
    racine = tmp_path / "r"
    for motif in CHEMINS.values():
        for nom in NOMS:
            cible = racine / motif.format(nom)
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / motif.format(nom), cible)
    shutil.copyfile(ROOT / ROUTEUR, racine / ROUTEUR)
    return racine


def _muter(racine: Path, rel: str, avant: str, apres: str, *, tous: bool = False) -> None:
    chemin = racine / rel
    texte = chemin.read_text(encoding="utf-8")
    assert avant in texte, (rel, avant)
    chemin.write_text(texte.replace(avant, apres, -1 if tous else 1), encoding="utf-8")


def _deplacer_bloc_apres_ancre(racine: Path, rel: str) -> None:
    chemin = racine / rel
    texte = chemin.read_text(encoding="utf-8")
    seg = bloc(texte)
    assert seg is not None
    sans = texte.replace(seg, "", 1)
    fin = sans.find("\n", sans.find(ANCRE))
    chemin.write_text(sans[:fin + 1] + seg + sans[fin + 1:], encoding="utf-8")


def _contient(liste: list[str], aiguille: str) -> bool:
    return any(aiguille in f for f in liste)


def test_mutant_a1_codex_dev_multi_sans_a1_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".codex/agents/dev-multi.toml", "one plain command per call in the shell", "a command")
    assert _contient(fautes(r), "dev-multi codex : 'one plain command per call' absent")


def test_mutant_a2_bloc_apres_l_ancre_rougit(tmp_path):
    r = _copie(tmp_path)
    _deplacer_bloc_apres_ancre(r, ".github/agents/dev-mono.agent.md")
    assert _contient(fautes(r), "dev-mono copilot : position")


def test_mutant_a3_measured_hors_claude_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".gemini/agents/dev-mono.md", "hygiene here;", "hygiene here (measured);")
    assert _contient(fautes(r), "dev-mono gemini : portée Claude hors Claude")


def test_mutant_a4_phrase_routeur_retiree_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ROUTEUR, "chemin littéral", "chemin", tous=True)
    assert _contient(fautes(r), "AGENTS.md : 'chemin littéral' absent")


def test_mutant_a7_mesure_du_checkout_retiree_rougit(tmp_path):
    # Le « (mesuré) » du refus reste dans le segment : seul l'ordre le distingue.
    r = _copie(tmp_path)
    _muter(r, ROUTEUR, "passés, mesuré, T-01M5PY2DZ8", "passés, T-01M5PY2DZ8")
    assert _contient(fautes(r), "AGENTS.md : 'mesuré' absent après 'checkout -f --detach'")


def test_mutant_m2_fausse_phrase_remise_rougit(tmp_path):
    # La phrase retirée par la revue de clôture revient à la place du contrôle DÉCLARATIF.
    r = _copie(tmp_path)
    _muter(r, ROUTEUR, "— contrôle DÉCLARATIF : aucun code n’enchaîne la lecture au `checkout -f` "
           "(durcissement de la garde : T-01M5RCRZ1S)", "— le même contrôle se joue en appels simples")
    assert _contient(fautes(r), "AGENTS.md : 'DÉCLARATIF' absent du segment worktree")


def test_mutant_m3_ordre_du_controle_retire_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ROUTEUR, "D’ABORD `git -C", "`git -C")
    _muter(r, ROUTEUR, "ET SEULEMENT si sa sortie", "si sa sortie")
    assert _contient(fautes(r), "AGENTS.md : 'ET SEULEMENT si' absent du segment worktree")


def test_mutant_a8_portee_du_read_before_edit_retiree_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".claude/agents/dev-multi.md", "Read before Edit: on Claude Code (measured), an", "Read before Edit: an")
    assert _contient(fautes(r), "dev-multi claude : 'Read before Edit: on Claude Code (measured)' absent")


def test_mutant_a5_non_ascii_codex_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".codex/agents/dev-mono.toml", "no bash -c wrapper", "no bash -c wrapper —")
    assert _contient(fautes(r), "dev-mono codex : bloc non ASCII")


def test_mutant_a6_assumed_dans_kimi_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".kimi-code/agents/dev-mono.md", "Claude Code (measured)", "Claude Code (assumed)")
    assert _contient(fautes(r), "dev-mono kimi : diffère de Claude")


def test_mutant_k6_ancre_d_un_autre_banc_dans_le_bloc_rougit(tmp_path):
    r = _copie(tmp_path)
    _muter(r, ".claude/agents/frontend-fidelity.md", "then edit.", "then edit. Capture outputs whole.")
    assert _contient(fautes(r), "frontend-fidelity claude : ancre d'un autre banc")


def test_mutant_k5_racine_vide_rougit(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    out = fautes(vide)
    assert len([f for f in out if "fichier absent" in f]) == 16, out


@pytest.mark.parametrize("hote", sorted(PROPRES))
def test_mutant_atome_propre_retire_rougit(tmp_path, hote):
    r = _copie(tmp_path)
    rel = CHEMINS[hote].format("dev-mono")
    _muter(r, rel, PROPRES[hote][-1], "")
    assert _contient(fautes(r), f"dev-mono {hote} : {PROPRES[hote][-1]!r} absent")
