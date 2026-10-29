"""The quality-gate contract carried by the agent defs and the convention sheets.

WHAT THIS PINS, AND WHY IT TRAVELS. Every subject below is a file that reaches an
adopting project: fifteen host defs (`dev-mono`, `dev-multi`, `plan-critic` on five
hosts) and two convention sheets. So this net is as true there as here, and the
thing it protects is the one that was silently self-contradictory: the pipeline
told the mono-file dev to produce tests and, three lines lower, never to touch one.

TWO RULES OF METHOD, both learned the expensive way, both visible in the shape of
the arms below.

1. AN ABSENCE IS ONLY ASSERTED WHERE THE THING WAS PRESENT. `Never edit tests`
   lived on THREE surfaces — `.claude`, `.gemini`, `.kimi-code` — and on no other.
   Asserting its absence on `.codex` and `.github` would be green from the first
   day and forever, measuring strictly nothing while looking like coverage. Those
   two get POSITIVE arms instead, on what they actually carry.

2. THE COVERAGE FIELD IS ASSERTED IN TWO FAMILIES, NOT ONE. Only six of the ten
   `dev-*` defs carry a `CHECKS:` report block; the other four are prose and have
   no block to extend. One arm over ten files would have forced the same literal
   onto surfaces that cannot hold it. Six get the field, four get the sentence, and
   the split is measured here so it cannot quietly drift back to a single claim.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

HOSTS_MD = (".claude", ".gemini", ".kimi-code")

DEV_MONO = {
    "claude": ROOT / ".claude" / "agents" / "dev-mono.md",
    "gemini": ROOT / ".gemini" / "agents" / "dev-mono.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "dev-mono.md",
    "codex": ROOT / ".codex" / "agents" / "dev-mono.toml",
    "copilot": ROOT / ".github" / "agents" / "dev-mono.agent.md",
}
DEV_MULTI = {
    "claude": ROOT / ".claude" / "agents" / "dev-multi.md",
    "gemini": ROOT / ".gemini" / "agents" / "dev-multi.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "dev-multi.md",
    "codex": ROOT / ".codex" / "agents" / "dev-multi.toml",
    "copilot": ROOT / ".github" / "agents" / "dev-multi.agent.md",
}
PLAN_CRITIC = {
    "claude": ROOT / ".claude" / "agents" / "plan-critic.md",
    "gemini": ROOT / ".gemini" / "agents" / "plan-critic.md",
    "kimi": ROOT / ".kimi-code" / "agents" / "plan-critic.md",
    "codex": ROOT / ".codex" / "agents" / "plan-critic.toml",
    "copilot": ROOT / ".github" / "agents" / "plan-critic.agent.md",
}

# The three hosts that CARRIED the forbidding sentence. The list is explicit rather
# than derived: derivation from "whoever contains it today" would make the absence
# arm below tautological.
HOSTS_THAT_FORBADE_TESTS = ("claude", "gemini", "kimi")
OLD_FORBIDDING_SENTENCE = "Never edit tests"

# The six defs whose report block can hold a field, and the four that are prose.
CHECKS_LINE_DEFS = {
    f"dev-mono/{h}": DEV_MONO[h] for h in ("claude", "gemini", "kimi")
} | {
    f"dev-multi/{h}": DEV_MULTI[h] for h in ("claude", "gemini", "kimi")
}
PROSE_DEFS = {
    "dev-mono/codex": DEV_MONO["codex"],
    "dev-mono/copilot": DEV_MONO["copilot"],
    "dev-multi/codex": DEV_MULTI["codex"],
    "dev-multi/copilot": DEV_MULTI["copilot"],
}

# Anchors, chosen to be punctuation-neutral: the `.codex` TOML deliberately writes
# ASCII hyphens where the markdown hosts write em-dashes, so pinning a span that
# contains one would demand a host rewrite its own house style.
CLAUSE_PRODUCES = "PRODUCES the colocated unit test named by the plan"
CLAUSE_ONE_UNIT = "ONE unit for the mono-file mandate"
CLAUSE_PROTECTS = "NEVER weaken, delete or skip an EXISTING assertion"
AMENDED_ONE_FILE = "the colocated unit test named by the plan is part of that file's unit"
CODEX_PERIMETER_GUARD = "Do not edit files outside the plan"
COPILOT_MANDATE = "AND its colocated unit test"
CRITIC_ANCHOR = "assigns their PRODUCTION to the dev slot"
COVERAGE_FIELD = "coverage="
COVERAGE_PROSE = "Report the measured coverage figure"

SHEETS = (
    ROOT / ".agents" / "ref" / "CONVENTIONS_python.md",
    ROOT / ".agents" / "ref" / "CONVENTIONS_typescript.md",
)
COVERAGE_HEADING = "## Coverage measurement"
# A percentage anywhere in the section is a THRESHOLD by implication, and a
# threshold is a commitment on a codebase this kit has never measured.
PERCENT_FIGURE = re.compile(r"\b\d{1,3}\s?%")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# NON-VACUITY. Every arm below is a substring test over a hand-written list of
# paths. A path that moved would make its arm pass by reading an empty string, or
# fail for the wrong reason; either way the suite would stop measuring what it
# claims. So the population is proven first.
# ---------------------------------------------------------------------------


def test_every_def_this_suite_judges_exists_and_is_not_empty():
    everything = {**{f"dev-mono/{k}": v for k, v in DEV_MONO.items()},
                  **{f"dev-multi/{k}": v for k, v in DEV_MULTI.items()},
                  **{f"plan-critic/{k}": v for k, v in PLAN_CRITIC.items()}}
    assert len(everything) == 15, f"expected 15 defs, the tables list {len(everything)}"
    for name, path in everything.items():
        assert path.is_file(), f"{name}: {path} does not exist — its arms would be vacuous"
        assert read(path).strip(), f"{name}: {path} is empty"


def test_the_two_coverage_families_partition_the_ten_dev_defs():
    """The 6/4 split is the measured fact the two coverage arms rest on. If a host
    ever grows or loses a `CHECKS:` block, this fails FIRST and names it, instead of
    the coverage arms failing in a way that reads like a missing field."""
    assert len(CHECKS_LINE_DEFS) == 6
    assert len(PROSE_DEFS) == 4
    assert set(CHECKS_LINE_DEFS) & set(PROSE_DEFS) == set()
    for name, path in CHECKS_LINE_DEFS.items():
        assert "CHECKS:" in read(path), (
            f"{name} no longer carries a `CHECKS:` block — it belongs in the prose "
            "family now, and the split above must be corrected"
        )
    for name, path in PROSE_DEFS.items():
        assert "CHECKS:" not in read(path), (
            f"{name} has GAINED a `CHECKS:` block — it should carry the field, not "
            "the sentence"
        )


def test_the_convention_sheets_exist():
    for sheet in SHEETS:
        assert sheet.is_file(), f"{sheet} is missing"


# ---------------------------------------------------------------------------
# THE CONTRADICTION THAT WAS CLOSED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", sorted(DEV_MONO))
def test_dev_mono_is_told_to_produce_the_colocated_test(host: str):
    """The clause, on all FIVE mono surfaces. `dev-multi` already reported
    `foo.test.ts +18 / -0` in its own example block, so the contradiction was local
    to mono — which is why this arm is mono-only rather than swept over ten defs.

    MUTATION: delete the clause from any one host -> red, naming that host.
    """
    text = read(DEV_MONO[host])
    for anchor in (CLAUSE_PRODUCES, CLAUSE_ONE_UNIT, CLAUSE_PROTECTS):
        assert anchor in text, f"dev-mono/{host} is missing the clause fragment: {anchor!r}"


@pytest.mark.parametrize("host", HOSTS_THAT_FORBADE_TESTS)
def test_the_old_forbidding_sentence_is_gone_where_it_existed(host: str):
    """ABSENCE, asserted ONLY on the three hosts that carried the sentence.

    `.codex` and `.github` are deliberately absent from this parametrisation: the
    sentence never lived there, so an absence arm on them would be green forever
    and would inflate the apparent coverage of this file by two hosts.

    MUTATION: restore the sentence on any of the three -> red.
    """
    assert OLD_FORBIDDING_SENTENCE not in read(DEV_MONO[host]), (
        f"dev-mono/{host} still forbids editing tests, which now contradicts the "
        "clause three lines above it"
    )


def test_the_absence_arm_is_not_measuring_an_empty_population():
    """L-00000232: a non-zero count does not prove the right population was
    counted. The arm above passes trivially if HOSTS_THAT_FORBADE_TESTS ever
    empties, so the list is pinned to the three hosts that were MEASURED to carry
    the sentence."""
    assert set(HOSTS_THAT_FORBADE_TESTS) == {"claude", "gemini", "kimi"}
    assert all(h in DEV_MONO for h in HOSTS_THAT_FORBADE_TESTS)


@pytest.mark.parametrize("host", HOSTS_THAT_FORBADE_TESTS)
def test_the_one_file_rule_is_amended_not_left_to_contradict_the_clause(host: str):
    """The same three hosts carry `If the change grows beyond ONE file…`, which
    lives in the SAME list as the clause and would contradict it by the plain text:
    a colocated test looks like a second file. It is amended, not deleted — the
    hand-off to `dev-multi` is a live guard.

    MUTATION: revert the amendment (drop the parenthetical) -> red.
    """
    text = read(DEV_MONO[host])
    assert AMENDED_ONE_FILE in text, (
        f"dev-mono/{host}: the `beyond ONE file` rule was not amended, so it still "
        "reads as forbidding the very file the clause requires"
    )
    assert "hand off to `dev-multi`" in text, (
        f"dev-mono/{host}: the hand-off guard was lost while amending the rule — "
        "the amendment must narrow the rule, not remove it"
    )


def test_codex_mono_keeps_its_perimeter_guard():
    """POSITIVE arm for a host that never carried the forbidding sentence.

    `Do not edit files outside the plan` is a LIVE perimeter guard, not the rule
    this lot relaxed; the clause was added BESIDE it. Losing it while editing the
    same list is the plausible accident, so it is pinned.

    MUTATION: delete that bullet -> red.
    """
    text = read(DEV_MONO["codex"])
    assert CODEX_PERIMETER_GUARD in text, "the codex perimeter guard was removed, not preserved"
    assert CLAUSE_PRODUCES in text
    # `Plan lists exactly one implementation file` stays true: a test is not an
    # implementation file, by the sense AND by the word.
    assert "exactly one implementation file" in text


def test_copilot_mono_mandate_names_the_companion_test():
    """POSITIVE arm, second host that never carried the sentence. Its single-line
    mandate said `Edit exactly the approved implementation file`; left alone, the
    def would state the mandate and the clause and contradict itself.

    MUTATION: revert the mandate to its unqualified form -> red.
    """
    text = read(DEV_MONO["copilot"])
    assert COPILOT_MANDATE in text, (
        "the Copilot mono mandate still authorises exactly one file, which "
        "contradicts the clause added in the same paragraph"
    )
    assert CLAUSE_PRODUCES in text


# ---------------------------------------------------------------------------
# THE CRITIC ROW
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", sorted(PLAN_CRITIC))
def test_plan_critic_requires_tests_to_be_assigned_to_the_dev_slot(host: str):
    """`test-adequacy` used to accept a plan that named test cases without ever
    saying who writes them. A plan can name a file::case and still leave its
    production to nobody, which is how "tests later" passes a checklist.

    MUTATION: drop the addition from any host -> red, naming that host.
    """
    assert CRITIC_ANCHOR in read(PLAN_CRITIC[host]), (
        f"plan-critic/{host}: the test-adequacy row no longer requires the plan to "
        "assign test PRODUCTION to the dev slot"
    )


# ---------------------------------------------------------------------------
# COVERAGE — REPORTED, NEVER GATED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CHECKS_LINE_DEFS))
def test_the_six_report_blocks_carry_the_coverage_field(name: str):
    """FAMILY 1. The field must be IN the `CHECKS:` line, not merely somewhere in
    the file — a def that mentions coverage in prose while its report template
    omits it produces reports without the figure.

    MUTATION: move `coverage=` out of the CHECKS line -> red.
    """
    checks = [l for l in read(CHECKS_LINE_DEFS[name]).splitlines() if l.startswith("CHECKS:")]
    assert checks, f"{name}: no `CHECKS:` line found"
    assert any(COVERAGE_FIELD in l for l in checks), (
        f"{name}: the CHECKS line does not carry `{COVERAGE_FIELD}` — the report "
        f"template it fixes has no place for the figure. Found: {checks!r}"
    )


@pytest.mark.parametrize("name", sorted(PROSE_DEFS))
def test_the_four_prose_defs_carry_the_coverage_sentence(name: str):
    """FAMILY 2. These hosts have no report block to extend, so the obligation is a
    sentence. The literal is shared across all four so that a host rewording it
    drifts loudly rather than quietly.

    MUTATION: paraphrase it on one host -> red on that host. (Measured during this
    lot: one of the four HAD been paraphrased, and this arm is what caught it.)
    """
    text = read(PROSE_DEFS[name])
    assert COVERAGE_PROSE in text, (
        f"{name}: missing the literal {COVERAGE_PROSE!r}. A paraphrase reads the "
        "same to a human and is invisible to every machine that checks the contract"
    )
    assert "unmeasured" in text, (
        f"{name}: the sentence must offer the `unmeasured: <reason>` branch, or an "
        "agent with no coverage tool has no honest answer and will omit the field"
    )


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_each_sheet_documents_how_to_measure_coverage(sheet: Path):
    text = read(sheet)
    assert COVERAGE_HEADING in text, f"{sheet.name} has no `{COVERAGE_HEADING}` section"
    assert "--coverage" in text or "coverage run" in text, (
        f"{sheet.name}: the section names no command — a section that says to "
        "measure without saying how is a section nobody can act on"
    )


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_no_sheet_sets_a_coverage_threshold(sheet: Path):
    """THE NEGATIVE ARM, and the one this lot most needs.

    A percentage in this section is a threshold by implication, and a threshold
    here is a commitment made on a codebase the kit has never measured. The
    adopting project writes its own floor into its own tool config, once it HAS a
    measurement.

    MUTATION: write `80 %` (or `80%`) anywhere in the section -> red.
    """
    text = read(sheet)
    section = text.split(COVERAGE_HEADING, 1)[1]
    section = section.split("\n## ", 1)[0]
    found = PERCENT_FIGURE.findall(section)
    assert not found, (
        f"{sheet.name}: the coverage section names a figure {found!r}. Any number "
        "here reads as a threshold, and this kit has never measured the adopting "
        "project's test suite"
    )


def test_the_threshold_arm_can_actually_fire():
    """L-00000057: right logic wired to the wrong anchor passes before AND after
    the defect. The section-slicing above is the fragile part — if the heading
    ever moves, `section` becomes empty and the arm goes green on everything. So
    the slicer is exercised on a payload that MUST match."""
    fake = "intro\n" + COVERAGE_HEADING + "\n- aim for 80 % coverage\n\n## Next\n- 90 %\n"
    section = fake.split(COVERAGE_HEADING, 1)[1].split("\n## ", 1)[0]
    assert PERCENT_FIGURE.findall(section) == ["80 %"], (
        "the slicer/regex pair no longer detects a threshold, or it leaks into the "
        "following section — the negative arm above would be green whatever happens"
    )
