"""Le board-reporter décrit plusieurs running sans imposer un groupe parallèle.

L'ordre du store suit la chronologie des ids ULID ; la sortie JSON inverse cet
ordre parmi les running, d'où la dernière ligne comme focus d'affichage.

Borne : ce témoin épingle les cinq définitions qui voyagent. Il ne simule pas le
raisonnement d'un agent et ne prouve pas le comportement du CLI à lui seul.
"""

import re
import unicodedata
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SURFACES = {
    "claude": ".claude/agents/board-reporter.md",
    "codex": ".codex/agents/board-reporter.toml",
    "copilot": ".github/agents/board-reporter.agent.md",
    "gemini": ".gemini/agents/board-reporter.md",
    "kimi": ".kimi-code/agents/board-reporter.md",
}
PHRASES_RETIREES = (
    r"only\s+as\s+a\s+(?:declared\s+)?parallel\s+group",
    r"belong\s+to\s+a\s+declared\s+parallel\s+group",
    r"mean\s+a\s+declared\s+parallel\s+group",
    r"owns\s+the\s+running\s+invariant",
    r"proven-disjoint\s+parallel\s+group",
    r"legitimate\s+state,\s+not\s+a\s+corrupt\s+board",
    r"first\s+running\s+row.{0,80}focus",
)


def texte(hote: str) -> str:
    brut = (ROOT / SURFACES[hote]).read_text(encoding="utf-8")
    return " ".join(unicodedata.normalize("NFKC", brut).casefold().split())


@pytest.mark.parametrize("hote", SURFACES)
def test_ancienne_condition_de_groupe_absente(hote: str) -> None:
    surface = texte(hote)
    for phrase in PHRASES_RETIREES:
        assert re.search(phrase, surface) is None, f"{hote}: phrase retirée présente ({phrase})"


@pytest.mark.parametrize("hote", SURFACES)
def test_focus_du_store_et_derniere_ligne_json(hote: str) -> None:
    surface = texte(hote)
    for fragment in (
        "focus_task",
        "oldest `running` task in store order",
        "list --json",
        "running` tasks newest first",
        "last running row",
        "focus.json",
        "board displays do not read it",
    ):
        assert fragment in surface, f"{hote}: règle du focus absente ({fragment})"


@pytest.mark.parametrize("hote", SURFACES)
def test_toutes_les_running_independantes_ou_groupees_sont_visibles(hote: str) -> None:
    surface = texte(hote)
    for fragment in (
        "independent or share a declared `parallel_group`",
        "both are legitimate",
        "one active session per clone",
        "every `running` task",
        "marked independent or with its group",
        "past 12",
        "+n more running",
        "never a silent cut",
    ):
        assert fragment in surface, f"{hote}: affichage multi-running absent ({fragment})"
