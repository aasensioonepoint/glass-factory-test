#!/usr/bin/env python3
"""Tests for protected_module.py — the class-3-by-construction probe (T-00000200).

What is at stake in each direction, and why neither is "just a default":
  - exempt too much -> a real, actionable advisory stops gating and nobody is
    told; the gate reports GO on a finding somebody could have fixed.
  - exempt too little -> a consumer gets a permanent NO-GO on vendored code it
    is forbidden to edit, which blocks every use of the kit.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protected_module as pm

GUARD = "protect_paths.py"


class TestProtectedModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        for mod in ("protect_paths",):
            sys.modules.pop(mod, None)

    def install_guard(self, host=".codex/hooks", prefixes=("src/legacy/", "generated/"),
                      extra=()):
        """A stand-in for the canonical guard, with the same two public names."""
        d = self.root / host
        d.mkdir(parents=True, exist_ok=True)
        (d / GUARD).write_text(
            "PROTECTED_PREFIXES = %r\n"
            "def extra_prefixes():\n"
            "    return %r\n" % (tuple(prefixes), tuple(extra)),
            encoding="utf-8")
        sys.modules.pop("protect_paths", None)

    def classify(self, path):
        sys.modules.pop("protect_paths", None)
        return pm.classify(self.root, path)

    # ---- the blocking case this whole mechanism exists for ------------------

    def test_vendored_kit_dir_is_protected(self):
        """`.agents/bin/` is what a consumer's own list protects, and it is
        exactly where an unfixable advisory would land."""
        self.install_guard(extra=(".agents/bin/",))
        self.assertEqual(self.classify(".agents/bin"), pm.PROTECTED)

    def test_ordinary_module_is_not_protected(self):
        self.install_guard(extra=(".agents/bin/",))
        self.assertEqual(self.classify("frontend"), pm.NOT_PROTECTED)

    def test_builtin_prefixes_count_too(self):
        self.install_guard()
        self.assertEqual(self.classify("src/legacy"), pm.PROTECTED)

    # ---- the ways this could go wrong ---------------------------------------

    def test_root_is_never_protected(self):
        """Exempting '.' would exempt the entire project in one step — the exact
        inverse of the intent, and it would be invisible in the report."""
        self.install_guard(extra=("",))     # a stray empty line in a project list
        for spelling in (".", "", "./"):
            self.assertEqual(self.classify(spelling), pm.NOT_PROTECTED, spelling)

    def test_prefix_match_is_not_substring_match(self):
        """`src/legacy-tools/` must NOT inherit `src/legacy/`'s exemption."""
        self.install_guard()
        self.assertEqual(self.classify("src/legacy-tools"), pm.NOT_PROTECTED)

    def test_windows_separators_and_dot_slash(self):
        self.install_guard(extra=(".agents/bin/",))
        for spelling in (r".agents\bin", "./.agents/bin", ".agents/bin/"):
            self.assertEqual(self.classify(spelling), pm.PROTECTED, spelling)

    def test_case_insensitive_like_the_guard(self):
        self.install_guard(extra=(".agents/bin/",))
        self.assertEqual(self.classify(".AGENTS/Bin"), pm.PROTECTED)

    def test_no_guard_anywhere_is_UNKNOWN_not_protected(self):
        """Unreadable must never read as 'exempt': that would silence findings
        wholesale the day the guard file moves."""
        self.assertEqual(self.classify(".agents/bin"), pm.UNKNOWN)

    def test_gemini_copy_is_accepted_when_codex_is_absent(self):
        self.install_guard(host=".gemini/hooks", extra=(".agents/bin/",))
        self.assertEqual(self.classify(".agents/bin"), pm.PROTECTED)

    def test_unimportable_guard_falls_through_to_the_sibling(self):
        d = self.root / ".codex/hooks"
        d.mkdir(parents=True)
        (d / GUARD).write_text("import nonexistent_module_xyz\n", encoding="utf-8")
        self.install_guard(host=".gemini/hooks", extra=(".agents/bin/",))
        self.assertEqual(self.classify(".agents/bin"), pm.PROTECTED)

    def test_broken_project_list_keeps_the_builtins(self):
        """A malformed `.agents/protected-paths.local` must not take the
        built-in prefixes down with it."""
        d = self.root / ".codex/hooks"
        d.mkdir(parents=True)
        (d / GUARD).write_text(
            "PROTECTED_PREFIXES = ('src/legacy/',)\n"
            "def extra_prefixes():\n"
            "    raise OSError('unreadable')\n", encoding="utf-8")
        sys.modules.pop("protect_paths", None)
        self.assertEqual(self.classify("src/legacy"), pm.PROTECTED)
        self.assertEqual(self.classify("frontend"), pm.NOT_PROTECTED)

    def test_exit_codes_are_the_contract_sca_scan_reads(self):
        """sca-scan.sh branches on these three numbers; renaming them silently
        would turn 'protected' into 'not protected' at the call site."""
        self.assertEqual((pm.PROTECTED, pm.NOT_PROTECTED, pm.UNKNOWN), (0, 1, 2))
        self.install_guard(extra=(".agents/bin/",))
        self.assertEqual(pm.main(["--root", str(self.root), ".agents/bin"]), 0)
        self.assertEqual(pm.main(["--root", str(self.root), "frontend"]), 1)


if __name__ == "__main__":
    unittest.main()
