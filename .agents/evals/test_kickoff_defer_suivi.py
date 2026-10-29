"""T-01M5T4NRDN, lot K — `/kickoff --defer-night` commits the plan before the contract.

K1: step 4b of the source `commands/kickoff.md` carries the sentence S1 (the plan's
step 5, extended by closing review n°2 with the re-run and its NO contract, and
asserted identically by lot S in the kickoff skill) BEFORE « 1. PRECONDITION (T-00000847) », and the list of conditions `/night`
re-checks names « plan committed and identical to HEAD ».
K2: the same S1 is in step 4b of each of the three renders, and that section is
byte-identical to the source's (a render not replayed after an edit turns red).
K3 (closing review F1+F3): S1ter, the night's own `git status` and symbolic-link
reading, is the line right after S1 in the source and in each render.
ZERO LLM, text shape only.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "commands/kickoff.md"
RENDUS = (
    ".claude/commands/kickoff.md",
    ".cursor/commands/kickoff.md",
    ".agents/skills/source-command-kickoff/SKILL.md",
)
DEBUT = "4b. **`--defer-night`"
FIN = "4c. **Plan par lot"
PRECONDITION = "   1. PRECONDITION (T-00000847)"
LISTE = "`/night` re-checks EVERY one of its conditions"
CONDITION = "plan committed and identical to HEAD"
S1 = (
    "   PRECONDITION bis (T-01M5T4NRDN): the plan is committed and identical to HEAD"
    " — `git show HEAD:./docs/tasks/T-NNN-plan.md >/dev/null` and"
    " `git diff --quiet HEAD -- docs/tasks/T-NNN-plan.md` both rc 0; otherwise"
    " `git add -- docs/tasks/T-NNN-plan.md` then"
    " `git commit -m \"docs(tasks): plan T-NNN\" -- docs/tasks/T-NNN-plan.md`"
    " (same bytes, same fingerprint), then the contract — re-run both checks first;"
    " still non-zero → NO contract, tell the pilot."
)
# S1ter — closing review F1+F3, then n°2 F2 (a linked DIRECTORY, read by realpath):
# the night's own reading. test_skills_plan_commite.py asserts the same string on kickoff/SKILL.md.
S1TER = (
    "   PRECONDITION ter (T-01M5T4NRDN, the night's own reading):"
    " `git status --porcelain --ignored --untracked-files=all -- docs/tasks/T-NNN-plan.md`"
    " prints NOTHING and `bash .agents/pyrun.sh -c \"import os,sys;p=sys.argv[1];sys.exit(0 if"
    " os.path.realpath(p)==os.path.join(os.path.realpath('.'),os.path.normpath(p)) else 1)\""
    " docs/tasks/T-NNN-plan.md`, run from the root, is rc 0 (neither the plan nor one of its"
    " directories is a symbolic link). A `MM` line:"
    " `git restore --staged -- docs/tasks/T-NNN-plan.md`; a `!!` line: `git add -f --`"
    " instead of `git add --`; a symbolic link: replace it by the file (a linked directory by"
    " a real one), then the commit of"
    " PRECONDITION bis (a `git commit` rc 1 \"nothing to commit\" after the add is already"
    " clean). Re-read, then the contract."
)


def section_4b(rel):
    texte = (ROOT / rel).read_text(encoding="utf-8")
    debut = texte.index(DEBUT)
    return texte[debut:texte.index(FIN, debut)]


class KickoffDeferSuiviTests(unittest.TestCase):
    def test_k1_s1_precedes_the_t847_precondition_in_the_source(self):
        section = section_4b(SOURCE)
        lignes = section.split("\n")
        self.assertIn(S1, lignes, f"{SOURCE}: S1 absent of step 4b, or not on its own line")
        self.assertLess(
            section.index(S1), section.index(PRECONDITION),
            f"{SOURCE}: S1 must come before « 1. PRECONDITION (T-00000847) »",
        )

    def test_k3_s1ter_follows_s1_on_its_own_line_in_source_and_renders(self):
        for rel in (SOURCE, *RENDUS):
            with self.subTest(surface=rel):
                lignes = section_4b(rel).split("\n")
                self.assertIn(S1TER, lignes, f"{rel}: S1ter absent of step 4b, or not on its own line")
                self.assertEqual(lignes.index(S1TER), lignes.index(S1) + 1,
                                 f"{rel}: S1ter must be the line right after S1")

    def test_k1_night_recheck_list_names_the_committed_plan(self):
        section = section_4b(SOURCE)
        liste = section[section.index(LISTE):]
        self.assertIn(CONDITION, " ".join(liste.split()), f"{SOURCE}: re-check list omits {CONDITION!r}")

    def test_k2_renders_carry_s1_and_match_the_source(self):
        attendu = section_4b(SOURCE)
        for rel in RENDUS:
            with self.subTest(rendu=rel):
                section = section_4b(rel)
                self.assertIn(S1, section.split("\n"), f"{rel}: S1 absent of step 4b")
                self.assertEqual(section, attendu, f"{rel}: step 4b differs from {SOURCE} (render not replayed?)")


if __name__ == "__main__":
    unittest.main()
