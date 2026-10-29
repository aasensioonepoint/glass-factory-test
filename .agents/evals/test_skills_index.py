"""The router's `## Skills index` matches the skills that actually exist (P5).

WHY THIS NEEDS A TEST AT ALL. The index is a hand-written list inside a file
nobody regenerates. A skill added without an index line is a skill no agent is
told about; an index line whose skill was deleted sends the reader to a path that
does not exist. Neither failure produces an error — the router is prose.

THE TRAP A NAIVE CHECK FALLS INTO, and it is the reason this suite bounds depth
explicitly. `.agents/skills/vendor/` holds THREE `SKILL.md` at depth 2, whose
directory names DUPLICATE three depth-1 skills. An `ls` of `.agents/skills/`
would show `vendor` as an unindexed skill; a `find` with no depth bound would
show three duplicates. Both readings are wrong, and both look plausible. Depth 1
is the only depth discovery actually reaches (AGENTS.md § Skills index), so
depth 1 is what the index claims and what this suite measures.

THE FLOOR COMES BEFORE THE DIFF, NOT AFTER. Two empty sets diff perfectly
(L-00000186, L-00000232): a broken glob and a broken parser would agree, and the
symmetric difference would be empty for the worst possible reason. So the count is
asserted first, against a number written here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from surface_kit import EST_LE_KIT, SKILLS_DU_KIT, workflows_du_kit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "AGENTS.md"
SKILLS_DIR = ROOT / ".agents" / "skills"

# Written here, not derived from either side (L-00000261): a floor that counted
# whatever it found would be satisfied by any number at all.
# 2026-10-18, T-01M52X1W3WPKCWX1DC36NMKJB6 (lot D): 37 -> 38, the skill
# `terraform-deploy`; its router index line lands with AGENTS.md at integration.
# 2026-10-23, T-01M5M66MH1GDW8JRHKEXXN3JPA (lot B): 38 -> 39, the skill
# `jira`; its router index line lands with AGENTS.md at integration.
# 2026-10-22, T-01M5HEJZ9XVXWQ61XMZYGA3YT0 (lot A): 39 -> 40 at the merge, the
# skill `reverse-engineering`; its directory lands with the sister task DEFS.
# 2026-10-23, T-01M5N5FMA6DGVZVQSH6073A58A: 40 -> 41, the skill `setup`
# (with its command `/setup`) and its router index line.
# 2026-10-24, T-01M5PCCHMWXTRCM5QJT8J5KNEH (lot G): 41 -> 40, the local dev
# routing skill removed; its router index line leaves AGENTS.md at integration.
# 2026-10-25, merge of reprise/2026-10-20: T-01M5C1P67FN2YR9T3R0BHV7M3M renders one
# `source-command-*` mirror per command outside Claude Code only, from `commands/` —
# nine more than the three before, `jira` and `setup` included (40 -> 49);
# T-01M5BZC1Y0T36EHTZY9AKZ650F, the skill `seo` (49 -> 50); their router index lines
# land in the same changeset.
EXPECTED_COUNT = 50

COMMANDS_DIR = ROOT / ".claude" / "commands"
HOST_ONLY_COMMANDS = {"night"}

# The index line's shape: `- \`name\` · <trigger>`
INDEX_LINE = re.compile(r"^- `([a-z0-9-]+)` · (.+)$", re.M)

# The plan's bound on the trigger, so the index cannot grow back into prose.
MAX_TRIGGER = 40


def indexed() -> dict[str, str]:
    """Names in the router's index section — extracted from THAT SECTION ONLY.

    Scoping to the section matters: the router is full of backticked names, and a
    file-wide regex would harvest agent names, command names and paths, then
    report a difference that says nothing about the index.
    """
    text = ROUTER.read_text(encoding="utf-8")
    start = text.find("## Skills index")
    assert start >= 0, "the router has no `## Skills index` section"
    nxt = text.find("\n## ", start + 1)
    section = text[start : nxt if nxt > 0 else len(text)]
    return {m.group(1): m.group(2) for m in INDEX_LINE.finditer(section)}


def on_disk() -> set[str]:
    """Skills at DEPTH 1 — `.agents/skills/*/SKILL.md`, never a recursive glob."""
    return {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}


def judged(names: set[str]) -> set[str]:
    """Outside the kit (T-01M54MWW5GH, S-01M54ZQ6WC) a skill the ADOPTER adds is
    not judged: only the kit's skills are. In the kit, everything is."""
    return set(names) if EST_LE_KIT else set(names) & SKILLS_DU_KIT


class SkillsIndexTests:
    def test_floor_before_diff_both_sides_are_non_empty_and_the_expected_size(self) -> None:
        """THE FLOOR, ASSERTED FIRST. Everything below compares two sets; two
        empty sets are identical, so the diff must never be the first thing read.
        """
        disk, idx = on_disk(), indexed()
        assert len(SKILLS_DU_KIT) == EXPECTED_COUNT, len(SKILLS_DU_KIT)
        if not EST_LE_KIT:
            assert SKILLS_DU_KIT <= disk, f"kit skill(s) missing on disk: {sorted(SKILLS_DU_KIT - disk)}"
            assert SKILLS_DU_KIT <= set(idx), f"kit skill(s) missing from the index: {sorted(SKILLS_DU_KIT - set(idx))}"
            return
        assert len(disk) == EXPECTED_COUNT, (
            f"{len(disk)} skills at depth 1, expected {EXPECTED_COUNT}. If a skill was "
            "added or removed deliberately, change EXPECTED_COUNT here IN THE SAME EDIT "
            "as the router's index — that pairing is the point of this assertion."
        )
        assert len(idx) == EXPECTED_COUNT, (
            f"the router's index lists {len(idx)} skills, expected {EXPECTED_COUNT}"
        )

    def test_the_index_and_the_tree_are_in_symmetric_agreement(self) -> None:
        disk, idx = on_disk(), set(indexed())
        missing_from_index = sorted(judged(disk) - idx)
        missing_from_disk = sorted(idx - disk)
        assert not missing_from_index, (
            f"skill(s) on disk but ABSENT from the router's index — no agent is told "
            f"they exist: {missing_from_index}"
        )
        assert not missing_from_disk, (
            f"index line(s) pointing at a skill that does NOT exist at depth 1: "
            f"{missing_from_disk}. If one of these lives under `vendor/`, it is at "
            "depth 2 and invisible to discovery — indexing it would advertise a skill "
            "no host can load."
        )

    def test_shared_command_workflows_have_a_skill_counterpart(self) -> None:
        """Every portable Claude command must be discoverable by skill hosts.

        `night` is deliberately Claude-only because its runtime mechanism
        is host-specific; all other command entries must
        have a depth-1 shared skill with the same name.
        """
        commands = {p.stem for p in COMMANDS_DIR.glob("*.md")}
        portable = commands - HOST_ONLY_COMMANDS
        if not EST_LE_KIT:  # T-01M54MWW5GH : a command the ADOPTER adds is not judged
            portable &= workflows_du_kit()
            assert portable, "no kit command judged: the check would pass on an empty set"
        missing = sorted(portable - on_disk())
        assert not missing, (
            "portable Claude command(s) have no shared skill counterpart: "
            f"{missing}"
        )

    @pytest.mark.parametrize("relative", (
        ".claude/commands/jira.md", ".agents/skills/jira/SKILL.md",
    ))
    def test_jira_agent_steps_only_read_and_configuration_stays_with_pilot(
        self, relative: str,
    ) -> None:
        """Both host entry points expose the same two reads, never an agent write."""
        doc = (ROOT / relative).read_text(encoding="utf-8")
        scripts = re.findall(r"```bash\n(.*?)\n```", doc, re.S)
        assert scripts == [
            "python3 .agents/bin/jira_setup.py status\n"
            "python3 .agents/bin/jira_setup.py verify"
        ]
        pilot = doc.split("## Command for the pilot's terminal\n", 1)
        assert len(pilot) == 2
        # Prose too, not only the bash blocks: the agent section never names
        # `configure` (nor its former name `configurer`, which contains it).
        assert "configure" not in pilot[0]
        assert "```text\npython3 .agents/bin/jira_setup.py configure\n```" in pilot[1]
        assert "The agent never runs `configure`" in pilot[1]

    @pytest.mark.parametrize("relative", (
        ".claude/commands/setup.md", ".agents/skills/setup/SKILL.md",
    ))
    def test_setup_agent_runs_the_setup_and_interactive_steps_stay_with_pilot(
        self, relative: str,
    ) -> None:
        """Both host entry points run the same setup (and its dry run), never an
        interactive step: those go to the pilot's own terminal."""
        doc = (ROOT / relative).read_text(encoding="utf-8")
        scripts = re.findall(r"```bash\n(.*?)\n```", doc, re.S)
        assert scripts == [
            "python3 .agents/bin/setup_projet.py",
            "python3 .agents/bin/setup_projet.py --dry-run",
        ]
        pilot = doc.split("## Questions kept for the pilot's terminal\n", 1)
        assert len(pilot) == 2
        # `configure` also catches the former `configurer`; the merge driver's only
        # flag is `--installer` (`--install` does not exist: rc 2).
        assert "configure" not in pilot[0] and "--install" not in pilot[0]
        assert "core-scripts/setup.sh" in pilot[0]
        assert "```text\npython3 .agents/bin/setup_projet.py\n```" in pilot[1]
        assert "python3 .agents/bin/jira_setup.py configure`" in pilot[1]
        assert "python3 .agents/bin/fusion_enregistrement.py --installer`" in pilot[1]
        assert "The agent never runs\n`configure` nor `--installer`." in pilot[1]

    def test_vendor_is_excluded_and_that_exclusion_is_deliberate(self) -> None:
        """The trap, pinned. `vendor/` must NOT appear as a skill, and the three
        depth-2 files under it must NOT appear in the index — while the suite also
        asserts they still EXIST, so the day someone promotes them to depth 1 this
        test fails and the exclusion comment gets revisited instead of quietly
        becoming false (L-00000111).
        """
        idx = set(indexed())
        assert "vendor" not in idx, "`vendor` is a container, not a skill"
        assert "vendor" not in on_disk(), (
            "`vendor/SKILL.md` now exists at depth 1 — it would be discovered as a "
            "skill, and this suite's exclusion reasoning needs rewriting"
        )
        deep = list(SKILLS_DIR.glob("*/*/SKILL.md"))
        assert deep, (
            "no depth-2 SKILL.md remains under .agents/skills/ — the trap this test "
            "documents is gone, so update the docstring rather than leaving it "
            "describing a hazard that no longer exists"
        )
        for p in deep:
            assert p.parent.name not in idx or p.parent.name in on_disk(), (
                f"{p.parent.name} is indexed but only exists at depth 2 — the index "
                "would advertise a skill discovery cannot reach"
            )

    def test_every_trigger_is_bounded(self) -> None:
        long = {n: t for n, t in indexed().items() if len(t) > MAX_TRIGGER}
        assert not long, (
            f"trigger(s) longer than {MAX_TRIGGER} chars — the index is growing back "
            f"into prose, which is the byte pressure P5 exists to relieve: {long}"
        )

    def test_the_index_header_announces_the_expected_count(self) -> None:
        """THE ANNOUNCED NUMBER IS PAIRED TOO. 2026-10-22, T-01M5HEJZ9XVXWQ61XMZYGA3YT0
        (lot A, exec-critic): mutant M4 put AGENTS.md's `39 skills, profondeur 1`
        back to 38 and every bench of the lot stayed green — only
        `core-scripts/host_sync.test.sh` read that line. Judged in the kit only: an
        adopter who indexes a skill of their own raises the header past the kit's
        count, rightly.
        """
        if not EST_LE_KIT:
            pytest.skip("SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant) "
                        "— l'en-tête de l'index n'est pas jugé ici")
        header = re.search(r"^(\d+) skills, profondeur 1", ROUTER.read_text(encoding="utf-8"), re.M)
        assert header, "AGENTS.md has no `<N> skills, profondeur 1` header above the skills index"
        assert int(header.group(1)) == EXPECTED_COUNT, (
            f"AGENTS.md announces {header.group(1)} skills in its index header, "
            f"EXPECTED_COUNT is {EXPECTED_COUNT} — change both in the same edit"
        )

    def test_negative_control_the_diff_rule_refuses_a_missing_line(self) -> None:
        """POSITIVE CONTROL FOR THE COMPARISON (L-00000057): the rule must be able
        to go RED. Replayed on the same set comparison, with one name withheld.
        """
        disk, idx = judged(on_disk()), judged(set(indexed()))
        assert disk, "nothing judged: the control would bite on an empty set"
        assert disk == idx, "base not green — read the symmetric-agreement test first"
        mutilated = set(list(idx)[:-1])
        assert len(mutilated) == len(idx) - 1, "the mutation removed nothing"
        assert disk - mutilated, (
            "THE DIFF DOES NOT BITE: with one index line removed the comparison still "
            "reported full agreement, so its green measures nothing."
        )

    def test_negative_control_a_recursive_glob_would_have_lied(self) -> None:
        """THE BOUND ITSELF IS MEASURED, not just declared.

        AND THE COMPARISON IS ON PATHS, NEVER ON NAMES — which is the whole shape
        of the trap, discovered by this control failing on its first run. Compared
        by NAME, the recursive glob returns EXACTLY the depth-1 set: the three
        files under `vendor/` sit in directories whose names duplicate three
        depth-1 skills, so the extra files collapse into names already present.
        That is precisely why a naive `find` here does not produce an obvious
        error — it produces a plausible-looking list of duplicates. Compared by
        PATH the difference is visible, and it is three files.

        T-00000387 RELAXES THE COLLAPSE FROM EQUALITY TO SUBSET. The equality held
        while the ONLY depth-2 skills were the three seeds, whose directory names
        duplicate three depth-1 skills. The active GitHub fallback
        (.agents/bin/skills_github_fallback.py install) can now vendor a skill under
        a NEW name at depth 2, which would NOT collapse into a depth-1 name. So the
        invariant is now: the three SEED vendor dirs still collapse (rename one and
        this bites), and any further vendored skill is admitted and listed rather
        than forbidden. A newly vendored name stays out of the index and out of the
        depth-1 set, so the two tests above are unaffected.
        """
        recursive = set(SKILLS_DIR.glob("**/SKILL.md"))
        depth1 = set(SKILLS_DIR.glob("*/SKILL.md"))
        extra = recursive - depth1
        assert extra, (
            "a recursive glob returns no file the depth-1 glob missed, so this suite's "
            "depth bound is measuring nothing — either `vendor/` moved or the hazard is "
            "gone; update the docstring in the same edit"
        )
        # The SEED collapse-by-name IS the hazard, so assert it rather than assume it.
        # Named in hard code so renaming a seed reddens (non-vacuity).
        seed_vendor = {"composition-patterns", "playwright-best-practices", "react-best-practices"}
        vendor_names = {p.parent.name for p in SKILLS_DIR.glob("vendor/*/SKILL.md")}
        depth1_names = {p.parent.name for p in depth1}
        assert seed_vendor <= vendor_names, (
            f"a seed vendor dir was renamed or removed: {sorted(seed_vendor - vendor_names)} — "
            "the collapse-by-name control no longer measures the documented trap"
        )
        assert seed_vendor <= depth1_names, (
            "a seed vendor name no longer duplicates a depth-1 skill — the trap changed "
            "shape and the docstring above now describes something else"
        )
        # Anything else under vendor/ is a fallback install: admitted and listed, and
        # it need NOT duplicate a depth-1 name.
        installed_vendor = sorted(vendor_names - seed_vendor)
        assert all(name for name in installed_vendor), "a vendored dir has an empty name"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
