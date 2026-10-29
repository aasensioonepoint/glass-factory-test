#!/usr/bin/env python3
"""Tests for migrate_layout.py. Run: python .agents/bin/test_migrate_layout.py

The migration runs ONCE per provisioned project, on data that cannot be
regenerated (the task board, the ledger). So the properties under test are the
destructive ones: never overwrite, never lose a tracked file's history, and be
safe to run twice.
"""
from __future__ import annotations

import ctypes
import errno
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

HERE = Path(__file__).resolve().parent


def load_by_path(name: str, path: Path) -> ModuleType:
    """Load `path` as module `name`, REGISTERED in `sys.modules` BEFORE its body
    runs — the same shape as `build_index.py`'s DB probe (see `PROBE_MODULE`),
    deliberately not a variant of it.

    The registration is not decoration. `dataclasses` resolves
    `sys.modules[cls.__module__]` while building a class, and on a module absent
    from `sys.modules` that resolution yields None: measured on Python 3.14.6,
    `dataclasses.py:814` (`sys.modules.get(cls.__module__).__dict__`) then raises
    `AttributeError: 'NoneType' object has no attribute '__dict__'`. The trip
    wire needs string annotations — which `migrate_layout.py` has, via
    `from __future__ import annotations` — so the unregistered motif this
    replaced was passing only because the module under test happens to carry no
    `@dataclass` YET. Adding one would have broken the test, not the module.

    On a failed exec the name is removed again, so a half-executed module is
    never left behind for the next importer to find.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


mig = load_by_path("migrate_layout", HERE / "migrate_layout.py")

OLD_FILES = [
    "CODEBASE_INDEX.md", "SYMBOLS.md", "SYMBOLS_src.md", "INDEX_DELTA.json",
    "TASKS.json", "LEDGER.json", "AUDIT_LOG", "TASKS.md", "LEDGER.md",
    "RUN_LOG.md", "tasks.py", "ledger.py", "TOKEN_BUDGETS.md",
    "DOCS_REGISTRY.md", "CONVENTIONS_python.md",
]

EXPECTED = {
    ".agents/state/index/CODEBASE_INDEX.md",
    ".agents/state/index/SYMBOLS.md",
    ".agents/state/index/SYMBOLS_src.md",
    ".agents/state/index/INDEX_DELTA.json",
    ".agents/state/board/TASKS.json",
    ".agents/state/memory/LEDGER.json",
    ".agents/state/gates/AUDIT_LOG",
    ".agents/state/local/TASKS.md",
    ".agents/state/local/LEDGER.md",
    ".agents/state/local/RUN_LOG.md",
    ".agents/bin/tasks.py",
    ".agents/bin/ledger.py",
    ".agents/ref/TOKEN_BUDGETS.md",
    ".agents/ref/DOCS_REGISTRY.md",
    ".agents/ref/CONVENTIONS_python.md",
}


def git(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def open_exclusive(path: Path) -> int:
    """A Windows handle with dwShareMode=0 — nobody else may even READ the file.
    MEASURED, and the reason this is not a plain `open()`: under Python's
    `open()` a copy still SUCCEEDS (share read/write is granted), so a normal
    handle cannot interrupt a copy. Only share-0 makes `copy2` fail, with
    WinError 32. Windows-only by construction; callers are skipUnless'd."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p]
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle(ctypes.c_void_p(handle))


class _LayoutFixture:
    """A freshly provisioned project still on the old flat layout. Shared by
    both suites below so they measure the same starting state."""

    def setUp(self):
        # Windows flake: git/AV handles can outlive the test and make cleanup
        # raise PermissionError (ledger L-00000035) — never a regression here.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        old = self.root / ".agents" / "index"
        old.mkdir(parents=True)
        for name in OLD_FILES:
            (old / name).write_text(f"fixture {name}\n", encoding="utf-8")
        (self.root / ".sca-reports").mkdir()
        (self.root / ".sca-reports" / "audit-log.jsonl").write_text("{}\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def files(self) -> set[str]:
        return {p.relative_to(self.root).as_posix()
                for p in self.root.rglob("*") if p.is_file() and ".git/" not in p.as_posix()}


class MigrateLayoutTests(_LayoutFixture, unittest.TestCase):
    def test_every_artefact_lands_in_its_bucket(self):
        self.assertEqual(mig.main(["--root", str(self.root), "--apply"]), 0)
        got = self.files()
        self.assertTrue(EXPECTED <= got, f"missing: {sorted(EXPECTED - got)}")
        self.assertIn(".agents/state/local/sca-reports/audit-log.jsonl", got)
        self.assertFalse((self.root / ".agents" / "index").exists(),
                         "the empty old directory should be removed")

    def test_check_mode_changes_nothing(self):
        before = self.files()
        self.assertEqual(mig.main(["--root", str(self.root), "--check"]), 0)
        self.assertEqual(before, self.files())

    def test_second_run_is_a_no_op(self):
        mig.main(["--root", str(self.root), "--apply"])
        after_first = self.files()
        self.assertEqual(mig.main(["--root", str(self.root), "--apply"]), 0)
        self.assertEqual(after_first, self.files())

    def test_state_collision_is_a_conflict_and_moves_nothing(self):
        dst = self.root / ".agents" / "state" / "board"
        dst.mkdir(parents=True)
        (dst / "TASKS.json").write_text("newer board\n", encoding="utf-8")
        self.assertEqual(mig.main(["--root", str(self.root), "--apply"]), 1)
        self.assertEqual((dst / "TASKS.json").read_text(encoding="utf-8"), "newer board\n",
                         "an existing board must never be overwritten")
        self.assertTrue((self.root / ".agents" / "index" / "TASKS.json").is_file(),
                        "the source must stay put when there is a conflict")

    def test_tooling_already_shipped_by_the_kit_is_reported_not_deleted(self):
        dst = self.root / ".agents" / "bin"
        dst.mkdir(parents=True)
        (dst / "tasks.py").write_text("new kit copy\n", encoding="utf-8")
        self.assertEqual(mig.main(["--root", str(self.root), "--apply"]), 0)
        self.assertEqual((dst / "tasks.py").read_text(encoding="utf-8"), "new kit copy\n")
        self.assertTrue((self.root / ".agents" / "index" / "tasks.py").is_file(),
                        "a stale kit copy is the pilot's call to delete, not the script's")

    def test_tracked_files_move_with_git_so_history_survives(self):
        if git(self.root, "init", "-q", ".").returncode != 0:
            self.skipTest("git unavailable")
        git(self.root, "add", "--", ".agents/index/TASKS.json")
        git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
        self.assertEqual(mig.main(["--root", str(self.root), "--apply"]), 0)
        status = git(self.root, "status", "--porcelain").stdout
        self.assertIn("R  .agents/index/TASKS.json -> .agents/state/board/TASKS.json", status)


@unittest.skipUnless(
    sys.platform == "win32",
    "measures a Windows fact: Python's open() grants no FILE_SHARE_DELETE, so a "
    "held handle makes rename/unlink fail with WinError 32. Nothing to measure "
    "on POSIX, where the same move succeeds with the file open.",
)
class HeldHandleRetryTests(_LayoutFixture, unittest.TestCase):
    """The measured production failure: an AV/indexer handle on a just-created
    file makes shutil.move's copy-then-unlink fallback raise WinError 32 and the
    migration stops HALF DONE (12 files moved, the rest not). Reproduced without
    an antivirus and without a race — holding the file open IS the same lock.
    """

    HOT = Path(".agents") / "index" / "LEDGER.json"
    DST = Path(".agents") / "state" / "memory" / "LEDGER.json"

    def hold(self):
        """A real handle on a file the migration is about to move."""
        return open(self.root / self.HOT, "r", encoding="utf-8")

    def test_a_handle_released_mid_migration_is_ridden_out(self):
        held = self.hold()
        # Released well inside the retry budget (0.05+0.1+0.2+0.4 = 0.75 s before
        # the last attempt), late enough that the first attempt cannot succeed.
        closer = threading.Timer(0.3, held.close)
        closer.start()
        try:
            rc = mig.main(["--root", str(self.root), "--apply"])
        finally:
            closer.join(5)
            held.close()

        self.assertEqual(rc, 0, "a transient handle must not fail the migration")
        self.assertEqual((self.root / self.DST).read_text(encoding="utf-8"),
                         "fixture LEDGER.json\n")
        self.assertFalse((self.root / self.HOT).exists(),
                         "the source must be gone: a retried move still MOVES")
        self.assertTrue(EXPECTED <= self.files(),
                        "the rest of the layout must migrate too — the bug was a "
                        "migration stopping half way, not one lost file")

    def test_a_handle_never_released_still_fails_loudly(self):
        held = self.hold()
        started = time.monotonic()
        try:
            with self.assertRaises(PermissionError) as caught:
                mig.main(["--root", str(self.root), "--apply"])
        finally:
            held.close()  # so the fixture teardown is clean, not merely tolerated
        elapsed = time.monotonic() - started

        self.assertEqual(getattr(caught.exception, "winerror", None), 32,
                         "the ORIGINAL sharing violation must surface untouched")
        self.assertTrue((self.root / self.HOT).is_file(),
                        "a failed move never destroys the source")
        # Returning here at all proves the retry is bounded; the floor proves it
        # actually retried rather than giving up on the first attempt.
        budget = sum(mig._MOVE_BACKOFF_SECONDS[:mig._MOVE_ATTEMPTS - 1])
        self.assertGreaterEqual(elapsed, budget * 0.9)
        self.assertLess(elapsed, 30)

    def test_an_interrupted_directory_copy_never_promotes_a_partial_destination(self):
        """The dangerous half of the bug, on the one directory move the plan has
        (`.sca-reports/`, which the module docstring calls unregenerable).

        The copy fallback only ever runs when rename cannot do the move — i.e.
        cross-volume (a `.sca-reports` on another drive, a junction, a mapped
        share). That condition is simulated for this ONE path because it cannot
        be provoked inside a single tempdir; everything else is real: a genuine
        exclusive handle on one child makes the copy fail for real, mid-tree.

        MEASURED without the fix: copytree copies straight into the FINAL name
        and leaves it holding every child but the held one — a destination that
        looks migrated, is not, and turns the next run into a hand-merge
        conflict. With the fix the partial copy only ever exists under a
        `.part-<pid>` sibling and the final name never appears."""
        reports = self.root / ".sca-reports"
        for name in ("a.jsonl", "b.jsonl", "c.jsonl"):
            (reports / name).write_text(f"payload {name}\n", encoding="utf-8")
        before = {p.name: p.read_text(encoding="utf-8") for p in reports.iterdir()}

        real_rename = os.rename

        def rename_but_not_across_volumes(src, dst, *a, **kw):
            if Path(src) == reports:
                raise OSError(errno.EXDEV, "simulated cross-volume rename")
            return real_rename(src, dst, *a, **kw)

        handle = open_exclusive(reports / "b.jsonl")
        try:
            with mock.patch("os.rename", rename_but_not_across_volumes):
                with self.assertRaises(OSError):
                    mig.main(["--root", str(self.root), "--apply"])
        finally:
            close_handle(handle)

        self.assertEqual({p.name: p.read_text(encoding="utf-8") for p in reports.iterdir()},
                         before, "a copy that failed must leave the SOURCE intact")
        self.assertFalse((self.root / ".agents" / "state" / "local" / "sca-reports").exists(),
                         "a partial copy must never appear under the final name")


TOY_MODULE = '''\
"""Written by the test below, loaded by `load_by_path`, never imported by name.

Shaped like the modules this kit actually loads by path: string annotations plus
`typing` in `sys.modules`, which is the combination that sends `dataclasses`
through `_is_type` and into `sys.modules[cls.__module__]`.
"""
from __future__ import annotations

import sys
import typing  # noqa: F401  — the ClassVar probe in dataclasses needs it present
from dataclasses import dataclass, field

REGISTERED_DURING_EXEC = sys.modules.get(__name__)


@dataclass
class Point:
    x: int
    y: int
    tags: set[str] = field(default_factory=set)
'''


class LoadByPathTests(unittest.TestCase):
    """Guards the loader the whole suite above depends on. `migrate_layout.py`
    carries no `@dataclass` today, so nothing else here can catch the dormant
    trap — this toy module does, on the same helper."""

    def load_toy(self, name: str, source: str) -> ModuleType:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(sys.modules.pop, name, None)  # the suite stays isolated
        path = Path(tmp.name) / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        return load_by_path(name, path)

    def test_a_dataclass_survives_being_loaded_by_path(self):
        toy = self.load_toy("_toy_dataclass_probe", TOY_MODULE)
        # Under the unregistered motif this line is never reached on Python 3.14:
        # building `Point` raises inside exec_module.
        self.assertEqual(toy.Point(1, 2), toy.Point(1, 2, set()))
        # ...and on older Pythons, where that build still succeeds, THIS is what
        # goes red — so the guard measures the fix on every version.
        self.assertIs(toy.REGISTERED_DURING_EXEC, toy,
                      "the module must be in sys.modules while its body runs")

    def test_a_module_that_raises_leaves_no_half_executed_entry_behind(self):
        name = "_toy_exploding_probe"
        with self.assertRaises(ZeroDivisionError):
            self.load_toy(name, "raise ZeroDivisionError('boom')\n")
        self.assertNotIn(name, sys.modules,
                         "a failed load must un-register what it registered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
