"""Witness of lot S of T-01M5T4NRDNZ0ESYGFR3154RRJM: a plan that is not committed opens no night.

The three skills that travel (kickoff, planning, planning-all) carry the sentences
S1-S3 of the plan, byte for byte, each inside the section that owns it:
- D4: S1 in step 8b of kickoff/SKILL.md, before point 1 (the same string as K1, lot K);
- D4ter: S1ter (closing review F1+F3) the line right after S1 in step 8b;
- D6: S2 in « Le contrat de nuit » of planning/SKILL.md, before the closing door;
- D7: S3 in phase 4 of planning-all/SKILL.md, before « Puis rends la ligne »;
- C13: items 2 and 4 of « Ce qui accompagne la ligne » count a skip by condition 8
  ALONE as approvable once committed, never as a discarded task.
Zero LLM call, stdlib only.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
KICKOFF = SKILLS / "kickoff" / "SKILL.md"
PLANNING = SKILLS / "planning" / "SKILL.md"
PLANNING_ALL = SKILLS / "planning-all" / "SKILL.md"

# S1 — the plan's step 5, extended by closing review n°2 (re-run, NO contract);
# K1 of lot K asserts the same string.
S1 = (
    "PRECONDITION bis (T-01M5T4NRDN): the plan is committed and identical to HEAD — "
    "`git show HEAD:./docs/tasks/T-NNN-plan.md >/dev/null` and "
    "`git diff --quiet HEAD -- docs/tasks/T-NNN-plan.md` both rc 0; otherwise "
    "`git add -- docs/tasks/T-NNN-plan.md` then "
    "`git commit -m \"docs(tasks): plan T-NNN\" -- docs/tasks/T-NNN-plan.md` "
    "(same bytes, same fingerprint), then the contract — re-run both checks first; "
    "still non-zero → NO contract, tell the pilot."
)
# S1ter — closing review F1+F3, then n°2 F2; K3 of test_kickoff_defer_suivi.py asserts the same string.
S1TER = (
    "PRECONDITION ter (T-01M5T4NRDN, the night's own reading): "
    "`git status --porcelain --ignored --untracked-files=all -- docs/tasks/T-NNN-plan.md` "
    "prints NOTHING and `bash .agents/pyrun.sh -c \"import os,sys;p=sys.argv[1];sys.exit(0 if "
    "os.path.realpath(p)==os.path.join(os.path.realpath('.'),os.path.normpath(p)) else 1)\" "
    "docs/tasks/T-NNN-plan.md`, run from the root, is rc 0 (neither the plan nor one of its "
    "directories is a symbolic link). A `MM` line: "
    "`git restore --staged -- docs/tasks/T-NNN-plan.md`; a `!!` line: `git add -f --` "
    "instead of `git add --`; a symbolic link: replace it by the file (a linked directory by "
    "a real one), then the commit of "
    "PRECONDITION bis (a `git commit` rc 1 \"nothing to commit\" after the add is already "
    "clean). Re-read, then the contract."
)
# S2 and S3 — copied byte for byte from the plan's annex, § 8.
S2 = (
    "**Avant `--apply`, le pilote commite le plan** — `git add -- <plan>` puis "
    "`git commit -m \"docs(tasks): plan T-NNNNNNNN\" -- <plan>` : `night_approve.py` "
    "refuse (condition 8) un plan absent de HEAD ou modifié depuis HEAD, et "
    "`/planning` ne commite rien."
)
S3 = (
    "**Un plan non commité sort SAUTÉ par la condition 8** (absent de HEAD, ou modifié "
    "depuis HEAD), la DERNIÈRE évaluée : sauté pour ce seul motif, il est approuvable "
    "une fois commité. La ligne rendue s'ouvre donc par `git add -- <plans>` puis "
    "`git commit -m \"docs(tasks): plans T-… T-…\" -- <plans>`, gestes du pilote — "
    "`/planning-all` ne commite rien."
)
# Reservation C13 (plan-critic 2/8) — items 2 and 4 of « Ce qui accompagne la ligne ».
C13_ITEM2 = (
    "Un plan SAUTÉ par la condition 8 SEULE compte parmi les approuvables une fois "
    "commité : `/planning-all` ne commite jamais, tout plan frais en sort sauté."
)
C13_ITEM4 = (
    "Un saut par la condition 8 SEULE n'est jamais listé parmi les tâches écartées : "
    "il compte au point 2, approuvable une fois commité."
)


def section(text: str, start: str, end: str) -> str:
    """The bytes from the first `start` to the next `end` after it; missing marker = failure."""
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


class SkillsPlanCommiteTests(unittest.TestCase):
    def test_d4_kickoff_8b_carries_s1_before_point_1(self):
        text = KICKOFF.read_text(encoding="utf-8")
        body = section(text, "8b. **`--defer-night`", "\n8c. ")
        line = "\n   " + S1 + "\n"
        self.assertIn(line, body, f"{KICKOFF}: S1 absent from step 8b (3-space indent)")
        self.assertLess(body.index(line), body.index("   1. PRECONDITION (T-00000847)"),
                        f"{KICKOFF}: S1 must precede point 1 of step 8b")

    def test_d4ter_kickoff_8b_carries_s1ter_right_after_s1(self):
        body = section(KICKOFF.read_text(encoding="utf-8"), "8b. **`--defer-night`", "\n8c. ")
        self.assertIn("\n   " + S1 + "\n   " + S1TER + "\n", body,
                      f"{KICKOFF}: S1ter absent from step 8b, or not the line right after S1")

    def test_d6_planning_night_contract_carries_s2(self):
        text = PLANNING.read_text(encoding="utf-8")
        body = section(text, "## Le contrat de nuit reste le geste du PILOTE", "\n## ")
        self.assertIn("\n" + S2 + "\n", body, f"{PLANNING}: S2 absent from « Le contrat de nuit »")
        self.assertLess(body.index(S2), body.index("**Un plan `/planning` non approuvé"),
                        f"{PLANNING}: S2 must precede the closing door")

    def test_d7_planning_all_phase_4_carries_s3(self):
        text = PLANNING_ALL.read_text(encoding="utf-8")
        body = section(text, "### Phase 4 — `--check`", "\n## La ligne rendue")
        self.assertIn("\n" + S3 + "\n", body, f"{PLANNING_ALL}: S3 absent from phase 4")
        self.assertLess(body.index(S3), body.index("Puis rends la ligne"),
                        f"{PLANNING_ALL}: S3 must precede « Puis rends la ligne »")

    def test_c13_condition_8_alone_is_approvable_never_discarded(self):
        text = PLANNING_ALL.read_text(encoding="utf-8")
        body = section(text, "## Ce qui accompagne la ligne", "\n## ")
        item2 = section(body, "\n2. ", "\n3. ")
        item4 = section(body, "\n4. ", "\n5. ")
        self.assertIn(C13_ITEM2, item2, f"{PLANNING_ALL}: item 2 does not count condition 8 alone")
        self.assertIn(C13_ITEM4, item4, f"{PLANNING_ALL}: item 4 lists condition 8 alone as discarded")

    def test_section_bound_reddens_on_a_missing_end(self):
        # negative control: a section whose end marker is absent is a failure, never the whole tail
        with self.assertRaises(ValueError):
            section("## A\ntexte sans fin", "## A", "\n## ")


if __name__ == "__main__":
    unittest.main()
