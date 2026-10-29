"""Le juge et l'auteur d'un plan d'écran portent la ligne INTERACTION (T-01M5NPC8GCA28T1XBWTG456BN0, lot B).

Décision pilote S-01M5N24P2Y0SH6S0W0YNG3TAN6 : un plan d'écran sans le littéral
`INTERACTION:` juste est un NO_GO de `plan-critic` ; « the one UI check that blocks »
devient « one of the two UI checks that block: the mockup line and the INTERACTION
line » ; un composant partagé coupé entre deux lots est un constat ; `planner` écrit la
ligne et découpe les lots d'écran par COMPORTEMENT ; la skill `planning` le dit.

Filet TEXTUEL, assumé : le défaut fermé est une règle d'un hôte qui dérive des autres.
Il épingle des sous-chaînes COURTES et distinctives, sur chacun des cinq hôtes ET sur
chaque rendu du roster (`.agents/vendor/cadre/data/roster/*.json`), pour qu'un hôte qui perd la
clause rougisse SEUL, sous son nom. Le littéral à sept clés est recopié de l'étape 1 du
plan r3 (`plan_preflight.py` en juge la forme, lot A) : la lecture du tuple de clés du
préflight par ce banc est reportée après la fusion des lots (constat C7, annexe r3).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _charger_vendor_paths():
    """Le résolveur `.agents/bin/vendor_paths.py`, chargé PAR CHEMIN : le roster se lit
    au dossier du paquet de l'arbre (`.agents/vendor/cadre`, sinon `src/cadre`)."""
    spec = importlib.util.spec_from_file_location(
        "_vendor_paths_plan_ecran", ROOT / ".agents" / "bin" / "vendor_paths.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # enregistré AVANT exec_module (T-00000134)
    spec.loader.exec_module(module)
    return module


_VP = _charger_vendor_paths()

LITTERAL = (
    "INTERACTION: focus=<…> ; echap=<…> ; modal=<…> ; empilement=<…> ; "
    "wcag=<…> ; largeurs=<…> ; etats=<…>"
)
SANS_OBJET = "INTERACTION: sans objet | <motif>"
DECISION = "S-01M5N24P2Y0SH6S0W0YNG3TAN6"
ANCIENNE_CLAUSE = "the one UI check that blocks"

HOTES = {
    "claude": ".claude/agents/{}.md",
    "codex": ".codex/agents/{}.toml",
    "gemini": ".gemini/agents/{}.md",
    "copilot": ".github/agents/{}.agent.md",
    "kimi": ".kimi-code/agents/{}.md",
}

JETONS = {
    "plan-critic": (
        LITTERAL,
        SANS_OBJET,
        DECISION,
        "one of the two UI checks that block: the mockup line and the INTERACTION line",
        "A screen plan without its INTERACTION line, RIGHT, is a NO_GO",
        "you judge its TRUTH",
        "A SHARED component cut between two lots is a finding",
        "screen lots are split by BEHAVIOUR",
    ),
    "planner": (
        LITTERAL,
        SANS_OBJET,
        DECISION,
        "A screen plan WRITES its INTERACTION line",
        "Screen lots are split by BEHAVIOUR",
        "stay in ONE lot",
    ),
}

SKILL = ROOT / ".agents" / "skills" / "planning" / "SKILL.md"
JETONS_SKILL = (
    LITTERAL,
    SANS_OBJET,
    DECISION,
    "Les lots d'écran se découpent par COMPORTEMENT",
    "coupé\nentre deux lots, c'est un constat de `plan-critic`",
)


def _surfaces() -> list[tuple[str, str, str]]:
    """(def, origine, texte) : chaque déf d'hôte, puis chaque rendu de son roster."""
    sorties: list[tuple[str, str, str]] = []
    for nom in JETONS:
        for hote, gabarit in HOTES.items():
            chemin = gabarit.format(nom)
            sorties.append((nom, chemin, (ROOT / chemin).read_text(encoding="utf-8")))
        roster = json.loads((_VP.exiger(ROOT, "cadre") / "data" / "roster" / f"{nom}.json").read_text(encoding="utf-8"))
        for hote in HOTES:
            corps = "\n".join(roster["rendus"][hote]["corps"])
            sorties.append((nom, f"roster {nom}.json[{hote}]", corps))
    return sorties


SURFACES = _surfaces()


def manquants(texte: str, jetons: tuple[str, ...]) -> list[str]:
    return [j for j in jetons if j not in texte]


@pytest.mark.parametrize("nom, origine, texte", SURFACES, ids=[s[1] for s in SURFACES])
def test_chaque_surface_porte_la_regle_interaction(nom: str, origine: str, texte: str) -> None:
    absents = manquants(texte, JETONS[nom])
    assert not absents, f"{origine} : jetons absents {absents}"


@pytest.mark.parametrize(
    "origine, texte",
    [(o, t) for n, o, t in SURFACES if n == "plan-critic"],
    ids=[o for n, o, _ in SURFACES if n == "plan-critic"],
)
def test_l_ancienne_clause_du_seul_controle_ne_revient_pas(origine: str, texte: str) -> None:
    assert ANCIENNE_CLAUSE not in texte, f"{origine} : « {ANCIENNE_CLAUSE} » est revenue"


def test_la_skill_planning_porte_la_ligne_et_la_decoupe_par_comportement() -> None:
    absents = manquants(SKILL.read_text(encoding="utf-8"), JETONS_SKILL)
    assert not absents, f"{SKILL.relative_to(ROOT)} : jetons absents {absents}"


def test_plancher_dix_defs_et_dix_rendus() -> None:
    assert len(SURFACES) == 2 * 2 * len(HOTES) == 20


@pytest.mark.parametrize("nom", sorted(JETONS))
def test_temoin_negatif_un_jeton_retire_rougit_seul(nom: str) -> None:
    texte = next(t for n, _, t in SURFACES if n == nom)
    for jeton in JETONS[nom]:
        assert manquants(texte.replace(jeton, ""), JETONS[nom]) == [jeton]
