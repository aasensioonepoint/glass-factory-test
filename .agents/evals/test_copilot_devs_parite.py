"""PARITÉ DES DÉFS DE DEV COPILOT — T-01M5MY17R3S81H10XK2VN8KYT9 (lot F de T-01M5MCXMQVHZ231CW0K2JR76MD).

Clause : un jeton de contrat porté par la déf Claude d'un dev (`.claude/agents/<nom>.md`) est
porté aussi par sa déf Copilot (`.github/agents/<nom>.agent.md`). Décision pilote
S-01M5MCXYV352ZNNW7ZC75T8DJH.

Bornes, dites :
* `CHECKS:` n'est pas un jeton de parité. Les défs Copilot dev-mono et dev-multi sont dans la
  famille PROSE de `test_quality_gate_contract.py` (phrase de couverture, aucun bloc
  `CHECKS:`) : ce banc y exige l'ABSENCE de `CHECKS:`, pour que les deux bancs ne se
  contredisent jamais (décision tracée, option b). frontend-fidelity n'en porte sur aucun
  hôte (mesuré).
* Piège 2 : `test_conventions_par_module_doctrine.py` exige l'absence de `conventions_file` et
  de `test_runner` dans la déf Copilot dev-mono ; ce banc l'exige des deux défs portées.
* Un jeton présent n'en prouve pas le sens : le banc juge la présence, jamais la paraphrase.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / ".claude" / "agents"
COPILOT = ROOT / ".github" / "agents"

DEVS = ("dev-mono", "dev-multi", "frontend-fidelity")
#: Les jetons de contrat dont la présence côté Claude oblige le côté Copilot.
JETONS = (
    "PRECONDITION_FAILED",
    "DOCS_REGISTRY",
    "BANCS-BORNES",
    "Before you hand back",
    "PROOFS:",
    "FOLLOW-UPS",
)
#: Absences exigées : famille PROSE de test_quality_gate_contract, et piège 2.
ABSENTS = {
    "dev-mono": ("CHECKS:", "conventions_file", "test_runner"),
    "dev-multi": ("CHECKS:", "conventions_file", "test_runner"),
}
#: Les sections Claude portées dans les deux défs Copilot condensées.
SECTIONS = ("## Preconditions", "## Process", "## Output format", "## Best-practice bounds")
PORTEES = ("dev-mono", "dev-multi")


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def fautes(claude: dict[str, str], copilot: dict[str, str]) -> list[str]:
    """Chaque faute de parité, `<déf> : <jeton>` ; liste vide = parité tenue."""
    out: list[str] = []
    for nom in DEVS:
        c, g = claude[nom], copilot[nom]
        for jeton in JETONS:
            if jeton in c and jeton not in g:
                out.append(f"{nom} : manque {jeton}")
        for jeton in ABSENTS.get(nom, ()):
            if jeton in g:
                out.append(f"{nom} : porte {jeton}")
        if nom in PORTEES:
            for section in SECTIONS:
                if section in c and section not in g:
                    out.append(f"{nom} : manque {section}")
    return out


def charger() -> tuple[dict[str, str], dict[str, str]]:
    return ({n: lire(CLAUDE / f"{n}.md") for n in DEVS},
            {n: lire(COPILOT / f"{n}.agent.md") for n in DEVS})


def test_population_non_vide() -> None:
    claude, copilot = charger()
    for nom in DEVS:
        assert claude[nom].strip() and copilot[nom].strip(), nom
    # Chaque jeton générique est porté par au moins une déf Claude : sinon la clause est vide.
    for jeton in JETONS:
        assert any(jeton in t for t in claude.values()), f"{jeton} n'est dans aucune déf Claude"


def test_parite_claude_copilot_des_devs() -> None:
    claude, copilot = charger()
    assert fautes(claude, copilot) == []


@pytest.mark.parametrize("nom, jeton", [
    ("dev-mono", "PRECONDITION_FAILED"),
    ("dev-multi", "DOCS_REGISTRY"),
    ("dev-mono", "PROOFS:"),
    ("frontend-fidelity", "BANCS-BORNES"),
])
def test_controle_negatif_jeton_retire_rougit(nom: str, jeton: str) -> None:
    claude, copilot = charger()
    copilot = {**copilot, nom: copilot[nom].replace(jeton, "")}
    assert f"{nom} : manque {jeton}" in fautes(claude, copilot)


@pytest.mark.parametrize("nom, jeton", [
    ("dev-mono", "CHECKS:"),
    ("dev-multi", "CHECKS:"),
    ("dev-mono", "test_runner"),
    ("dev-multi", "conventions_file"),
])
def test_controle_negatif_jeton_interdit_rougit(nom: str, jeton: str) -> None:
    claude, copilot = charger()
    copilot = {**copilot, nom: copilot[nom] + f"\n{jeton}\n"}
    assert f"{nom} : porte {jeton}" in fautes(claude, copilot)


def test_controle_negatif_section_retiree_rougit() -> None:
    claude, copilot = charger()
    copilot = {**copilot, "dev-multi": copilot["dev-multi"].replace("## Output format", "")}
    assert "dev-multi : manque ## Output format" in fautes(claude, copilot)
