#!/usr/bin/env python3
"""THE SEED LINKS OF sync_template.py, judged BEFORE any write — hermetic witnesses.

Run: python -m pytest .agents/bin/test_sync_template_liens.py -q

`do_apply` never writes a seed THROUGH a symbolic link (a parent or the leaf):
`mkdir` and `write_bytes` follow one out of the tree. That judgement used to run
INSIDE the seed loop, AFTER the TAKE checkouts: a refusal returned 18 on a
half-applied tree — taken files staged, a recovery left for the operator to
type. T-00001113 made it a PRE-PASS: 18 all the same, and NOTHING applied.
Judged before the TAKE, the disk alone is not enough: a TAKEn path on a seed's
way may itself be a link once checked out, so the pre-pass refuses that too —
compared CASEFOLDED: on APFS/NTFS a TAKEn `.agents/State` IS `.agents/state`.

A NEW MODULE, NOT AN AMENDMENT: `test_sync_template.py` sits at its ratchet
ceiling. Every case builds its own throw-away repo through `make_repo`
(imported, never re-written), and the tree is compared through git itself,
never walked: nothing here reads or writes the real repository.

Each witness names, in its comment, the mutant it was written to kill; every
mutant was replayed on a throw-away copy of the script and turned it red.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_sync_template as T  # noqa: E402 — needs the path inserted above

st = T.st
_git, make_repo = T._git, T.make_repo
_APPLY_OK = T._APPLY_OK

SRC = ".agents/adopter-seed/gates/"
DST = ".agents/state/gates/"
SEED = DST + "BINOME_REQUIRED"
EXC = "strip: .agents/state/\nstrip: .agents/adopter-seed/\nown: TEMPLATE.md\n"
# A TAKE of each kind besides the seed — README.md overwritten, new_file.txt
# new: what the checkout used to write BEFORE the link was judged.
MAIN = {"README.md": "hello v2\n", "TEMPLATE.md": "t\n", "new_file.txt": "fresh\n",
        SRC + "BINOME_REQUIRED": "# seed binome\n"}
TEMPLATE = {"README.md": "hello\n", "TEMPLATE.md": "t\n"}


def _state(root: Path) -> tuple[str, str, str]:
    """The tree as git sees it — HEAD, every path's status (untracked and
    ignored included) and the index: a refused apply is compared with the tree
    before it, without walking the disk."""
    return (_git(root, "rev-parse", "HEAD").stdout,
            _git(root, "status", "--porcelain", "--untracked-files=all", "--ignored").stdout,
            _git(root, "ls-files", "-s").stdout)


class SeedLinkPrePassTests(T.SyncTemplateTestCase):

    def setUp(self):
        super().setUp()
        self.outside = Path(self._tmp.name) / "outside"
        self.outside.mkdir()
        make_repo(self.root, main_files=MAIN, template_files=TEMPLATE, exclude_text=EXC)
        _git(self.root, "checkout", "-q", "template/starter-kit")

    def _tracked_link(self, rel: str, target: Path, branch: str = "template/starter-kit"):
        """`branch` TRACKS `rel` as a symbolic link to `target`, committed; the
        template is checked out again afterwards, clean."""
        _git(self.root, "checkout", "-q", branch)
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, self.root / rel)
        except (OSError, NotImplementedError) as exc:
            raise unittest.SkipTest(f"no symbolic link here: {exc}") from exc
        _git(self.root, "add", "--", rel)
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "link")
        _git(self.root, "checkout", "-q", "template/starter-kit")

    def _assert_refused_with_nothing_applied(self, component: str) -> None:
        before = _state(self.root)
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, st.EXIT_VERIFY_FAILED, err + out)
        # THE WITNESS: the tree after the refusal IS the tree before it.
        self.assertEqual(_state(self.root), before, err)
        self.assertFalse((self.root / "new_file.txt").exists(), err)
        self.assertEqual(sorted(self.outside.iterdir()), [], err)
        self.assertIn("nothing applied", err)
        self.assertIn(f": {component} is a symbolic link", err)
        self.assertNotIn("Recovery", err)  # nothing to recover from

    def test_L0_without_a_link_the_same_fixture_applies(self):
        # kills MP0 (the pre-pass refusing a TAKE that is NOT on a seed's way):
        # the control that makes L1-L3 mean the LINK
        code, out, err = self.run_main(list(_APPLY_OK))
        self.assertEqual(code, st.EXIT_OK, err + out)
        self.assertEqual((self.root / SEED).read_text(encoding="utf-8"), "# seed binome\n")
        self.assertEqual((self.root / "new_file.txt").read_text(encoding="utf-8"), "fresh\n")

    def test_L1_a_linked_parent_is_refused_before_the_TAKE(self):
        # kills MP1 (the judgement left after the checkouts — the BASE): 18 on a
        # tree where README.md, new_file.txt and .template-exclude were staged
        self._tracked_link(DST.rstrip("/"), self.outside)
        self._assert_refused_with_nothing_applied(DST.rstrip("/"))

    def test_L2_a_linked_leaf_is_refused_before_the_TAKE(self):
        # kills MP2 (the leaf left out of the pre-pass walk): `write_bytes`
        # follows a link at the destination itself
        leaf = Path(self._tmp.name) / "outside.txt"
        leaf.write_text("ORIGINAL\n", encoding="utf-8")
        self._tracked_link(SEED, leaf)
        self._assert_refused_with_nothing_applied(SEED)
        self.assertEqual(leaf.read_text(encoding="utf-8"), "ORIGINAL\n")

    def test_L3_a_TAKEn_link_on_a_seeds_way_is_refused_too(self):
        # kills MP3 (the pre-pass judging the disk only): the SOURCE tracks
        # `.agents/state` as a link — `strip: .agents/state/` does not match the
        # bare name, so it is TAKEn; once checked out, `mkdir` follows it and the
        # seed lands in `outside/` before `git add` refuses the path
        self._tracked_link(".agents/state", self.outside, branch="main")
        self.assertFalse((self.root / ".agents/state").is_symlink())  # not on disk yet
        self._assert_refused_with_nothing_applied(".agents/state")

    def test_L4_a_case_variant_TAKEn_link_is_refused_too(self):
        # kills MP4 (the TAKEn comparison exact, case included — the BASE): the
        # SOURCE tracks `.agents/State` as a link, which no `strip:` covers. The
        # pre-pass compares CASEFOLDED strings, never the disk, so its refusal
        # holds on BOTH disks and MP4 dies on both, by two mechanisms (measured
        # on the transactional script): case-insensitive, `checkout-index`
        # replaces the link in the seed's way by a directory, the verification
        # fails (".agents/State: expected blob …, got None") and the transaction
        # ROLLS BACK — 18, the tree unchanged, "nothing applied" printed by the
        # rollback — so MP4 dies by the ABSENCE of the refusal message alone;
        # case-sensitive, the seed lands in a distinct `.agents/state/`, the
        # apply verifies clean and MP4 dies on rc 0. Never skipped.
        self._tracked_link(".agents/State", self.outside, branch="main")
        self._assert_refused_with_nothing_applied(".agents/state")


if __name__ == "__main__":
    unittest.main()
