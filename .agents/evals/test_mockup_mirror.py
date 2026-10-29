"""The mockup rule and its two nuances, pinned in the canonical file AND its
Copilot mirror (T-00000164).

WHY A TEXT NET, SAID PLAINLY. This is deliberately a file-scoped textual net —
the instrument this repo is otherwise wary of, because a net that pins prose
turns every reflow into a false failure. It is the right instrument HERE for one
reason: the defect being closed is a MIRROR THAT DRIFTED. The canonical rule
lives in `AGENTS.md`, the Copilot host reads its own copy, and the copy had the
three closed values without the two nuances that make them honest. Nothing
mechanical connected the two files, so the drift was invisible until someone
read both side by side.

The mitigation for the usual objection is in the SHAPE of the assertions: they
pin SHORT, DISTINCTIVE substrings — never whole sentences. A paragraph can be
rewritten, reordered, translated around them and stay green; what cannot happen
silently is a mirror that loses a value or a nuance.

Measured before writing: `mockup` appeared ZERO times under `.agents/evals/`.
Nothing pinned this rule anywhere.

ONE SOURCE (T-01M4V7R89VZ5SP3NXZ32SNNDZ2). The tokens and the surfaces now live
in `doctrine_registre.py`, rule `REGLE` below, and NOWHERE in this file:
`test_doctrine_registre.py` (4d) refuses a token copied back here as a constant.
The surfaces' MEMBERS stay pinned here (negative control), the tokens get a
floor. The three closed values take their GRAMMAR form (`` `mockup: < ``, not
`mockup:`): the occurrence that DEFINES the value, stricter than the bare word.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402

REGLE = "mockup"
CANON = ROOT / "AGENTS.md"
MIRROR = ROOT / ".github" / "copilot-instructions.md"
# P4 (T-00000341) moved the rule's DETAIL out of the router and into this skill.
# The router now states the invariant and POINTS here.
DETAIL = ROOT / ".agents" / "skills" / "frontend-fidelity" / "SKILL.md"

# WHY THE SURFACES ARE NOW SPLIT INTO TWO ROLES, and why this is STRONGER than
# what it replaces rather than a weakening (the failure mode L-00000253 names: a
# correction that closes the doors it can see and certifies the rest closed).
#
# Before P4 one file carried both the closed values and the nuances, so one list
# of surfaces was enough. P4 thinned the router: `AGENTS.md` keeps the three
# closed values as an INVARIANT and delegates the detail. Demanding the nuances
# from the router would therefore demand that the thinning be undone.
#
# So the net now asserts THREE things where it asserted two, and adds a surface:
#   * the three CLOSED VALUES on every surface that states the rule at all
#     (router, mirror, skill) — unchanged in strength, one surface wider;
#   * the two NUANCES on every surface that states the rule IN DETAIL
#     (mirror, skill) — the router is exempted EXPLICITLY, not silently;
#   * and, the compensating assertion that makes that exemption safe, the router
#     must POINT at the detail surface. Without it, a future edit could drop the
#     pointer and leave the router stating a rule whose nuances live nowhere it
#     names — which is precisely the drift this suite was born to catch, one
#     level up.
# Groups of the registry rule: `enonce` (router, mirror, skill), `detail`
# (mirror, skill), `pointeur` (router). Their members are pinned in the negative
# control below.
STATES_THE_RULE = tuple(ROOT / rel for rel in R.chemins(REGLE, "enonce"))
STATES_THE_DETAIL = tuple(ROOT / rel for rel in R.chemins(REGLE, "detail"))
POINTS_AT_THE_DETAIL = tuple(ROOT / rel for rel in R.chemins(REGLE, "pointeur"))

# The three CLOSED values. A mirror missing one of these does not narrow the
# rule, it deletes an option a plan is entitled to use — most often the third,
# which is the one that keeps the rule survivable when everything cannot be done
# at once.
CLOSED_VALUES = R.jetons(REGLE, "enonce")

# The two nuances, each pinned by the token that carries its MEANING rather than
# by its phrasing. `inventory` is the citation nuance (point at the recorded gap
# instead of asserting an absence); `EXIST on the board` is the debt nuance (a
# named task that does not exist is a wish).
NUANCES = R.jetons(REGLE, "detail")

# What the router must name so that its exemption from the nuances is safe.
POINTERS = R.jetons(REGLE, "pointeur")


@pytest.mark.parametrize("path", list(STATES_THE_RULE), ids=lambda p: p.name)
def test_the_file_exists_and_is_readable(path: Path):
    """NON-VACUITY of everything below: every other arm reads these two files,
    and a renamed or moved file would make them all fail loudly here rather than
    somewhere confusing."""
    assert path.is_file(), f"{path} is missing"
    assert path.read_text(encoding="utf-8").strip(), f"{path} is empty"


@pytest.mark.parametrize("path", list(STATES_THE_RULE), ids=lambda p: p.name)
@pytest.mark.parametrize("value", CLOSED_VALUES)
def test_the_three_closed_values_are_present(path: Path, value: str):
    text = path.read_text(encoding="utf-8")
    assert value in text, (
        f"{path.name} does not carry the closed value `{value}` — a mirror that "
        "drops one of the three deletes an option plans are entitled to use"
    )


@pytest.mark.parametrize("path", list(STATES_THE_DETAIL), ids=lambda p: p.name)
@pytest.mark.parametrize("nuance", NUANCES)
def test_the_two_nuances_travel_with_the_rule(path: Path, nuance: str):
    """THE ARM THAT CLOSES THE MEASURED DEFECT. The Copilot mirror carried the
    three values WITHOUT these two, which turns the rule into something a plan
    can satisfy by writing `no mockup: je ne crois pas qu'il y en ait` and by
    naming a task nobody ever created."""
    text = path.read_text(encoding="utf-8")
    assert nuance in text, (
        f"{path.name} states the mockup rule without the `{nuance}` nuance — "
        "the rule then reads as satisfiable by an unverifiable assertion"
    )


def test_the_mirror_is_not_merely_a_copy_of_the_canonical_file():
    """The other direction, and it keeps this net honest. These two files are
    written for different hosts and MUST differ; an arm suite that only ever
    checked "both contain X" would be satisfied by someone pasting AGENTS.md
    wholesale into the Copilot file, which is not a mirror — it is a second
    canonical file, and the next divergence would then be silent in both."""
    canon = CANON.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    assert canon != mirror
    # The mirror names its own host's paths; the canonical one does not have to.
    assert ".github/agents/" in mirror


def test_the_router_points_at_the_detail_surface():
    """THE COMPENSATING ASSERTION for the router's exemption above (T-00000341).

    The router is allowed to state the rule without its nuances ONLY because it
    names where the nuances live. Drop the pointer and the exemption becomes the
    hole this suite exists to prevent — a surface stating a rule whose honest
    form is nowhere it references.
    """
    for path in POINTS_AT_THE_DETAIL:
        text = path.read_text(encoding="utf-8")
        for rel in POINTERS:
            assert rel in text, (
                f"{path.name} states the mockup rule but no longer points at "
                f"`{rel}`, where its two nuances now live. Either restore the pointer, or "
                "bring the nuances back into the router and add it to the `detail` group."
            )


def test_negative_control_the_nuance_arm_still_bites():
    """A parametrised arm that lost its surfaces would pass vacuously
    (L-00000232). Assert the MEMBERS of each surface group — a count would let a
    surface be swapped for another at equal size — floor the tokens, and assert
    the nuance tokens are not accidentally trivial substrings that match anything.
    """
    assert STATES_THE_RULE == (CANON, MIRROR, DETAIL), (
        "the rule-stating surfaces changed in the registry"
    )
    assert STATES_THE_DETAIL == (MIRROR, DETAIL), (
        "the detail-stating surfaces changed — if the router is back in the detail "
        "group, the exemption comment above is stale and must be rewritten, not left "
        "describing a rule that no longer holds"
    )
    assert POINTS_AT_THE_DETAIL == (CANON,), "the pointing surface changed in the registry"
    assert len(CLOSED_VALUES) >= 3, "the registry lost a closed value"
    assert len(NUANCES) >= 2, "the registry lost a nuance"
    assert len(POINTERS) >= 1, "the registry lost the router's pointer"
    for nuance in NUANCES:
        assert len(nuance) >= 7, f"{nuance!r} is short enough to match by accident"
        assert nuance not in "unrelated prose about mockups and boards", (
            f"{nuance!r} matches generic prose — it would pass on a surface that never "
            "states the rule"
        )
