"""Keep the travelling indexer definitions aligned with the multi-running board.

This checks the board paragraph and the separate Claude/Gemini/Kimi task-board
rule. It checks wording, not the board implementation or undeclared writes.
"""

from pathlib import Path
import re
import unicodedata

import pytest


ROOT = Path(__file__).resolve().parents[2]
SURFACES = {
    "claude": ".claude/agents/indexer.md",
    "copilot": ".github/agents/indexer.agent.md",
    "gemini": ".gemini/agents/indexer.md",
    "kimi": ".kimi-code/agents/indexer.md",
}
OLD_RULES = (
    r"only\s+as\s+a\s+(?:declared\s+)?parallel\s+group",
    r"belong\s+to\s+a\s+declared\s+parallel\s+group",
    r"mean\s+a\s+declared\s+parallel\s+group",
    r"owns\s+the\s+running\s+invariant",
    r"proven-disjoint\s+parallel\s+group",
    r"legitimate\s+state,\s+not\s+a\s+corrupt\s+board",
)
BOARD_RULES = (
    "several tasks can be `running` independently or in declared parallel groups",
    "`start` does not demote other `running` tasks",
    "`tasks.py parallel` proves disjointness of DECLARED writesets before declaring a group",
)


def normalized(value: str) -> str:
    """Fold host-specific line wrapping, case, and Unicode compatibility forms."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def board_paragraph(value: str, host: str) -> str:
    anchor = "`state` is a CLOSED vocabulary" if host != "copilot" else "`CODEBASE_INDEX.md` is generated:"
    matches = [line for line in value.splitlines() if line.startswith(anchor)]
    assert len(matches) == 1, f"{host}: board paragraph missing or duplicated"
    return normalized(matches[0])


@pytest.mark.parametrize("host", SURFACES)
def test_board_paragraph_names_independent_running_and_start(host: str) -> None:
    paragraph = board_paragraph((ROOT / SURFACES[host]).read_text(encoding="utf-8"), host)
    for rule in BOARD_RULES:
        assert normalized(rule) in paragraph, f"{host}: board rule absent ({rule})"


@pytest.mark.parametrize("host", SURFACES)
def test_old_group_only_claims_are_absent(host: str) -> None:
    whole = normalized((ROOT / SURFACES[host]).read_text(encoding="utf-8"))
    for old in OLD_RULES:
        assert re.search(old, whole) is None, f"{host}: phrase retirée présente ({old})"


@pytest.mark.parametrize("host", ("claude", "gemini", "kimi"))
def test_task_board_rule_no_longer_claims_a_running_invariant(host: str) -> None:
    value = (ROOT / SURFACES[host]).read_text(encoding="utf-8")
    start = value.index("5. **Task board**")
    end = value.index("## Output", start)
    rule = normalized(value[start:end])
    assert "owns task state transitions and declared parallel groups" in rule, host
    assert "declared writesets disjoint" in rule, host


def test_task_board_skill_drops_the_single_group_invariant() -> None:
    skill = normalized((ROOT / ".agents/skills/task-board/SKILL.md").read_text(encoding="utf-8"))
    assert "one task, or several inside one declared parallel group" not in skill
    assert "single-running invariant" not in skill
