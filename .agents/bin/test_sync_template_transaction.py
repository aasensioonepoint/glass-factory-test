#!/usr/bin/env python3
"""sync_template.py --apply NEVER LEAVES A HALF-APPLIED TREE — hermetic witnesses.

Run: python -m pytest .agents/bin/test_sync_template_transaction.py -q

Pilot decision S-00004031 on T-00001149: (A) a path whose place the template's
tree holds with the other kind (a FILE where a seed needs a directory — measured:
`.agents/state/gates` tracked as a file, `[Errno 17] File exists` — or the
reverse) is REFUSED before any write, 24, nothing applied. (Guarantee, T-00001155)
whatever fails after the pre-pass — a git step, a disk step, the verification or
an error raised inside it, any other exception, an interrupt (SIGINT, SIGTERM,
SIGHUP) — is ROLLED BACK from the journal, and `status --porcelain` / `ls-files
-s` are what they were; an interrupt or an unexpected error is raised again
after it. BOUND, not witnessed here because nothing can be: the journal lives in
memory, so SIGKILL, a power cut or a process killed outright replays nothing.

THE INJECTION (`Crash`) lets the k-th WRITE STEP really run — its effect lands on
the index or the disk — and only then raises; every k of the run is replayed, so
the failure hits the index steps, the `checkout-index` that writes N paths, and
each unlink. A bench that only failed the index preparation would prove nothing.

A NEW MODULE, NOT AN AMENDMENT: `test_sync_template.py` sits at its ratchet
ceiling. Every case builds a THROW-AWAY template repo through `make_repo`
(imported, never re-written) under a mktemp directory, and the tree is compared
through git itself — HEAD, `status --porcelain` (untracked and ignored included)
and `ls-files -s` — never walked: nothing here reads or writes the real repository.

Each witness names the mutant it kills; on the BASE (before T-00001149) every
refusal case below ended 18 "APPLY FAILED mid-way" on a half-applied tree.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_sync_template as T  # noqa: E402 — needs the path inserted above

st = T.st
_git, make_repo = T._git, T.make_repo
_APPLY_OK = T._APPLY_OK

SEED_SRC = ".agents/adopter-seed/gates/BINOME_REQUIRED"
GATES = ".agents/state/gates"
SEED = GATES + "/BINOME_REQUIRED"
EXC = "strip: .agents/state/\nstrip: .agents/adopter-seed/\nown: TEMPLATE.md\n"
# A TAKE of each kind besides the seed — README.md overwritten, new_file.txt new:
# what the base wrote BEFORE it met the conflict.
MAIN = {"README.md": "hello v2\n", "TEMPLATE.md": "t\n", "new_file.txt": "fresh\n",
        SEED_SRC: "# seed binome\n"}
TEMPLATE = {"README.md": "hello\n", "TEMPLATE.md": "t\n"}
# The PUBLISHED number, literal: a renumbering of the constant must turn this red.
EXIT_PATH_CONFLICT = 24


def state(root: Path) -> tuple[str, str, str]:
    """The tree as git sees it: HEAD, every path's status (untracked AND ignored)
    and the index, mode and blob of each entry."""
    return (_git(root, "rev-parse", "HEAD").stdout,
            _git(root, "status", "--porcelain", "--untracked-files=all", "--ignored").stdout,
            _git(root, "ls-files", "-s").stdout)


class Case(T.SyncTemplateTestCase):
    """One throw-away template repo per test, checked out on the template, clean."""

    def repo(self, main: dict[str, str] | None = None, template: dict[str, str] | None = None,
             root: Path | None = None) -> Path:
        root = root or self.root
        root.mkdir(exist_ok=True)
        make_repo(root, main_files={**MAIN, **(main or {})},
                  template_files={**TEMPLATE, **(template or {})}, exclude_text=EXC)
        _git(root, "checkout", "-q", "template/starter-kit")
        return root

    def apply(self, root: Path | None = None) -> tuple[int, str, str]:
        root = root or self.root
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = st.main(["--root", str(root), *_APPLY_OK])
        return code, out.getvalue(), err.getvalue()


class PathConflictPrePassTests(Case):
    """24 BEFORE any write: the tree after the refusal IS the tree before it."""

    def refused(self, blocked: str, why: str) -> None:
        before = state(self.root)
        code, out, err = self.apply()
        self.assertEqual(state(self.root), before, err)  # THE WITNESS
        self.assertEqual(code, EXIT_PATH_CONFLICT, err + out)
        self.assertIn("APPLY REFUSED, nothing applied", err)
        self.assertIn(f"{blocked!r}", err)
        self.assertIn(why, err)
        self.assertNotIn("Recovery", err)  # nothing to recover from

    def test_K0_without_a_conflict_the_same_fixture_applies(self):
        # kills MK0 (a pre-pass refusing a sound tree): the control that makes
        # K1-K6 mean the CONFLICT
        self.repo()
        code, out, err = self.apply()
        self.assertEqual(code, st.EXIT_OK, err + out)
        self.assertEqual((self.root / SEED).read_text(encoding="utf-8"), "# seed binome\n")

    def test_K1_a_tracked_FILE_where_a_seed_needs_a_directory_T1149(self):
        # kills MK1 (no pre-pass — the BASE: [Errno 17] mid-way, README.md,
        # new_file.txt and .template-exclude staged)
        self.repo(template={GATES: "a file, not a directory\n"})
        self.refused(GATES, "holds a FILE there")
        self.assertEqual((self.root / GATES).read_text(encoding="utf-8"), "a file, not a directory\n")

    def test_K2_a_tracked_DIRECTORY_where_a_seed_is_a_file(self):
        # kills MK2 (the leaf left out — the BASE: [Errno 21] Is a directory)
        self.repo(template={SEED + "/inner": "x\n"})
        self.refused(SEED, "holds a DIRECTORY there")

    def test_K3_a_TAKE_under_a_tracked_file(self):
        # kills MK3 (the pre-pass narrowed to the seeds — the BASE: `git rm -- a`
        # refused, `a/b` staged)
        self.repo(main={"a/b": "new\n"}, template={"a": "a file\n"})
        self.refused("a", "holds a FILE there")

    def test_K4_a_TAKE_over_a_tracked_directory(self):
        # kills MK2 and MK3 the other way round (the BASE: `git rm -- a/b`
        # matched nothing once `a` was checked out)
        self.repo(main={"a": "a file now\n"}, template={"a/b": "old\n"})
        self.refused("a", "holds a DIRECTORY there")

    def sparse(self, tracked: str) -> None:
        """`tracked` stays in the index, SKIP-WORKTREE, and leaves the disk — a
        sparse checkout: `status --porcelain` stays clean, so only the TREE can
        say what holds the place (K1-K6 are caught by the disk as well)."""
        _git(self.root, "update-index", "--skip-worktree", "--", tracked)
        (self.root / tracked).unlink()
        self.assertEqual(_git(self.root, "status", "--porcelain").stdout, "")

    def test_K7_a_sparse_tracked_FILE_where_a_seed_needs_a_directory(self):
        # kills MK7 (the tree's blobs not judged, the disk alone)
        self.repo(template={GATES: "a file, not a directory\n"})
        self.sparse(GATES)
        self.refused(GATES, "holds a FILE there")

    def test_K8_a_sparse_tracked_DIRECTORY_where_a_TAKE_is_a_file(self):
        # kills MK8 (the directories the tree implies not judged, the disk alone)
        self.repo(main={"a": "a file now\n"}, template={"a/b": "old\n"})
        self.sparse("a/b")
        (self.root / "a").rmdir()
        self.refused("a", "holds a DIRECTORY there")

    def test_K5_an_IGNORED_file_on_disk_where_a_seed_needs_a_directory(self):
        # kills MK5 (the disk not judged, the tree alone): clean for `status --porcelain`, so 12
        # lets it through; the ignored file survives the refusal byte for byte
        ignore = {".gitignore": f"/{GATES}\n"}
        self.repo(main=ignore, template=ignore)
        (self.root / GATES).parent.mkdir(parents=True, exist_ok=True)
        (self.root / GATES).write_text("MINE\n", encoding="utf-8")
        self.refused(GATES, "holds a FILE there")
        self.assertEqual((self.root / GATES).read_text(encoding="utf-8"), "MINE\n")

    def test_K6_an_IGNORED_directory_on_disk_where_a_seed_is_a_file(self):
        # kills MK6 (the leaf judged against the tree alone)
        ignore = {".gitignore": f"/{SEED}/\n"}
        self.repo(main=ignore, template=ignore)
        (self.root / SEED).mkdir(parents=True)
        (self.root / SEED / "kept").write_text("MINE\n", encoding="utf-8")
        self.refused(SEED, "holds a DIRECTORY there")
        self.assertEqual((self.root / SEED / "kept").read_text(encoding="utf-8"), "MINE\n")

    def test_K9_an_IGNORED_file_where_a_TAKE_is_new_T1155(self):
        # kills MK9 (the third rule left out — the BASE overwrote it at rc 0): the
        # rollback could not bring it back, so it is never written over
        # ignored on the TEMPLATE only: `make_repo` adds with `-A`, which would
        # leave an ignored path out of the source as well
        self.repo(main={".gitignore": "*.tmp\n"}, template={".gitignore": "/new_file.txt\n"})
        (self.root / "new_file.txt").write_text("MINE\n", encoding="utf-8")
        self.refused("new_file.txt", "something holds it on disk")


# The richest plan the apply knows: a TAKE overwrite (README.md) and three new
# (new_file.txt, .template-exclude, and `fresh/dir/f.txt` in directories the run
# CREATES — empty, they are invisible to `git status`), a seed overwritten and one
# new, two DELETEs — one deep, so its emptied parents are pruned — TEMPLATE.md
# frozen, and an IGNORED file of the operator's (`notes.local`) never touched.
RICH_MAIN = {".agents/adopter-seed/gates/PLAN_CHAIN_REQUIRED": "# seed chain\n",
             ".gitignore": "*.local\n", "fresh/dir/f.txt": "in new directories\n"}
RICH_TEMPLATE = {SEED: "# OLD seed bytes\n", "old.txt": "gone\n", "gone/deep/x.txt": "gone too\n",
                 ".gitignore": "*.local\n"}
MUTATING = ("update-index", "checkout-index", "checkout", "add", "rm")


class Crash:
    """ONE failure, injected AFTER the `at`-th write step has REALLY run — a mutating git
    call, an unlink, a `write_bytes` (the base wrote its seeds that way). `at` is a step
    number, a step label (its first occurrence), or None to count without failing.
    `partial`: a stdin-fed git step runs on its FIRST record only (N paths journaled, one
    written). Disarmed once fired: the rollback's own calls pass through."""

    def __init__(self, at: int | str | None = None, partial: bool = False,
                 error: type[BaseException] = OSError):
        self.at, self.partial, self.error = at, partial, error
        self.steps: list[str] = []
        self.fired = False

    def _fires(self, label: str) -> bool:
        if self.fired:
            return False
        self.steps.append(label)
        self.fired = self.at in (len(self.steps), label)
        return self.fired

    @contextlib.contextmanager
    def armed(self):
        real_git, real_unlink, real_write = st.git, Path.unlink, Path.write_bytes

        def git(root, *args, **kw):
            if not (args and args[0] in MUTATING and self._fires("git " + args[0])):
                return real_git(root, *args, **kw)
            if self.partial and kw.get("stdin"):
                kw = {**kw, "stdin": kw["stdin"].split("\0", 1)[0] + "\0"}
            real_git(root, *args, **kw)
            raise (st.GitError if self.error is OSError else self.error)(
                f"injected after a real `git {args[0]}`")

        def unlink(path, *args, **kw):
            fire = self._fires("unlink " + path.name)
            real_unlink(path, *args, **kw)
            if fire:
                raise self.error("injected after a real unlink")

        def write_bytes(path, data):
            fire = self._fires("write " + path.name)
            written = real_write(path, data)
            if fire:
                raise self.error("injected after a real write")
            return written

        with mock.patch.object(st, "git", git), mock.patch.object(Path, "unlink", unlink), \
                mock.patch.object(Path, "write_bytes", write_bytes):
            yield self


class BenchSignal(Exception):
    """What the BENCH's own handler raises: on a script that converts nothing (the base), a
    delivered SIGTERM ends the witness red instead of killing the test runner."""


def bench_handler(signum, _frame):
    raise BenchSignal(signum)


def send(sig: int):
    """An `error` for `Crash`: the signal ITSELF, sent to this process after the real step."""
    def error(_msg: str) -> BaseException:
        os.kill(os.getpid(), sig)
        for _ in range(100):  # an eval-loop sync point, whether or not `os.kill` checks signals
            pass
        return AssertionError(f"signal {sig} sent and nothing raised")
    return error


class DeadTty(io.StringIO):
    """A stderr whose terminal is GONE — an SSH session that drops sends SIGHUP and leaves the
    pty dead, so every write fails with EIO (critic F7 F1, measured)."""

    def write(self, _s):
        raise OSError(5, "Input/output error")


def hang_up(_msg: str) -> BaseException:
    """An `error` for `Crash`: the terminal dies, THEN SIGHUP — the order of a dropped session."""
    sys.stderr = DeadTty()
    return send(signal.SIGHUP)(_msg)


# A FAKE `git` (T-00001163), first on the bench's PATH: every call but `checkout-index` IS the real
# git (`execv`); `checkout-index` takes `<root>/.git/index.lock` as git does and, like git's own
# handler, removes it on SIGTERM before dying. FAKE_GIT_MODE: `signal` sends SIGTERM to the run
# while it holds the lock (`kill -TERM <pid>` during checkout-index), `hang` only sleeps (the run's
# timeout fires), `deaf` signals the run too but ignores SIGTERM — only SIGKILL stops it.
FAKE_GIT = """\
import os, signal, sys, time
args = sys.argv[1:]
if "checkout-index" not in args:
    os.execv(os.environ["FAKE_GIT_REAL"], ["git", *args])
sys.stdin.buffer.read()
lock = os.path.join(args[args.index("-C") + 1], ".git", "index.lock")
mode = os.environ["FAKE_GIT_MODE"]
def term(_signum, _frame):
    if os.path.exists(lock):
        os.unlink(lock)
    os._exit(143)
signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == "deaf" else term)
os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
if mode != "hang":
    os.kill(int(os.environ["FAKE_GIT_RUN"]), signal.SIGTERM)
time.sleep(60)
os._exit(1)
"""


class NthHash:
    """Raises `error` at the n-th `hash_worktree_file` — called by the VERIFICATION only."""

    def __init__(self, n: int, error: BaseException):
        self.n, self.error, self.calls, self.real = n, error, 0, st.hash_worktree_file

    def __call__(self, root, rel_path):
        self.calls += 1
        if self.calls == self.n:
            raise self.error
        return self.real(root, rel_path)


class TransactionTests(Case):
    """Whatever fails after the pre-pass, the tree after the run IS the tree before it."""

    def rich(self, name: str) -> Path:
        root = self.repo(RICH_MAIN, RICH_TEMPLATE, root=Path(self._tmp.name) / name)
        (root / "notes.local").write_text("the operator's own\n", encoding="utf-8")
        return root

    def rolled_back(self, root: Path, before: tuple[str, str, str], run) -> str:
        code, out, err = run
        self.restored(root, before, err)
        self.assertEqual(code, st.EXIT_VERIFY_FAILED, err + out)
        return err

    def restored(self, root: Path, before: tuple[str, str, str], err: str) -> None:
        self.assertEqual(state(root), before, err)  # THE WITNESS
        self.assertIn("ROLLED BACK", err)
        self.assertNotIn("Recovery", err)  # complete: nothing left for the operator
        self.assertEqual((root / "notes.local").read_text(encoding="utf-8"), "the operator's own\n")
        self.assertFalse((root / "fresh").exists(), "a directory the run created is left behind")

    def raised_after_rollback(self, root: Path, expected: type[BaseException]) -> str:
        """The run must RAISE `expected` again — no return code at all, so never 17 — after
        its rollback; returns its stderr, captured in spite of the exception."""
        before, err = state(root), io.StringIO()
        with self.assertRaises(expected), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            st.main(["--root", str(root), *_APPLY_OK])
        self.restored(root, before, err.getvalue())
        return err.getvalue()

    def test_T0_the_rich_plan_applies_clean(self):
        # the control that makes T2 mean the CRASH, and counts its steps
        root, counting = self.rich("count"), Crash()
        with counting.armed():
            code, out, err = self.apply(root)
        self.assertEqual(code, st.EXIT_OK, err + out)
        self.assertFalse((root / "gone").exists(), "emptied parents are pruned, as `git rm` did")
        self.assertGreaterEqual(len(counting.steps), 4, counting.steps)

    def test_T1_the_T1149_tree_failing_in_the_LAST_step_is_rolled_back(self):
        # kills MT1 (no rollback — the BASE, past its pre-pass: [Errno 17] mid-way,
        # README.md, new_file.txt and .template-exclude staged). Pre-pass bypassed;
        # `checkout-index` really writes — it unlinks the FILE `.agents/state/gates`
        # in its way and makes the directory — then fails
        self.repo(template={GATES: "a file, not a directory\n"})
        before = state(self.root)
        with mock.patch.object(st, "_refuse_if_path_conflict", lambda *a, **k: None, create=True), \
                Crash("git checkout-index").armed():
            run = self.apply()
        self.assertEqual(state(self.root), before, run[2])
        self.assertEqual(run[0], st.EXIT_VERIFY_FAILED, run[2])
        self.assertIn("ROLLED BACK", run[2])
        self.assertEqual((self.root / GATES).read_text(encoding="utf-8"), "a file, not a directory\n")

    def test_T1b_the_same_tree_fails_by_itself_on_the_DELETE_and_is_rolled_back(self):
        # no injection at all: past the pre-pass, the DELETE of the FILE
        # `.agents/state/gates` meets the directory `checkout-index` made (EPERM /
        # EISDIR) — pins the order "write, then delete" and its rollback
        self.repo(template={GATES: "a file, not a directory\n"})
        before = state(self.root)
        with mock.patch.object(st, "_refuse_if_path_conflict", lambda *a, **k: None, create=True):
            code, out, err = self.apply()
        self.assertEqual(state(self.root), before, err)
        self.assertEqual(code, st.EXIT_VERIFY_FAILED, err + out)
        self.assertIn("ROLLED BACK", err)

    def test_T2_a_crash_after_ANY_write_step_is_rolled_back(self):
        # kills MT2a (the journal filled AFTER `checkout-index`), MT2b (`created`
        # not unlinked), MT2c (`read-tree HEAD` left out), MT2d (a DELETE not
        # restored), MT2e (the created directories left — `fresh/dir/`)
        counting = Crash()
        with counting.armed():
            self.assertEqual(self.apply(self.rich("count"))[0], st.EXIT_OK)
        for k, step in enumerate(counting.steps, 1):
            for partial in (False, True) if step.startswith("git") else (False,):
                with self.subTest(k=k, step=step, partial=partial):
                    root = self.rich(f"k{k}{'p' if partial else ''}")
                    before = state(root)
                    with Crash(k, partial=partial).armed():
                        run = self.apply(root)
                    self.rolled_back(root, before, run)

    def test_T3_a_failed_verification_is_rolled_back(self):
        # kills MT3 (the verification failure left applied — the BASE)
        root = self.rich("verify")
        before = state(root)
        with mock.patch.object(st, "verify_manifest", return_value=["x: injected mismatch"]):
            err = self.rolled_back(root, before, self.apply(root))
        self.assertIn("VERIFICATION FAILED", err)
        self.assertIn("x: injected mismatch", err)

    def test_T4_an_interrupt_is_rolled_back_then_re_raised(self):
        # kills MT4 (the KeyboardInterrupt branch removed — the BASE: no rollback)
        root = self.rich("interrupt")
        before = state(root)
        with self.assertRaises(KeyboardInterrupt), \
                Crash("git checkout-index", error=KeyboardInterrupt).armed():
            self.apply(root)
        self.assertEqual(state(root), before)

    def test_T4b_an_interrupt_DURING_the_verification_is_rolled_back_then_re_raised(self):
        # kills MT4b (the verification outside the transaction — the BASE: no rollback,
        # the index left loaded, M README.md, A fresh/dir/f.txt, D gone/deep/x.txt)
        root = self.rich("verify-interrupt")
        with mock.patch.object(st, "hash_worktree_file", NthHash(2, KeyboardInterrupt())):
            err = self.raised_after_rollback(root, KeyboardInterrupt)
        self.assertIn("APPLY INTERRUPTED mid-way", err)

    def test_T4c_a_git_error_DURING_the_verification_is_rolled_back_18_never_17(self):
        # kills MT4b as well (the BASE: rc 17 "GIT ERROR", no rollback): a git step of the
        # verification that fails (a timeout is a GitError) is a failed apply, rolled back
        root = self.rich("verify-git-error")
        before = state(root)
        with mock.patch.object(st, "hash_worktree_file", NthHash(2, st.GitError("injected"))):
            err = self.rolled_back(root, before, self.apply(root))
        self.assertIn("APPLY FAILED mid-way: injected", err)
        self.assertNotIn("GIT ERROR", err)

    def test_T8_ANY_exception_is_rolled_back_then_re_raised_never_swallowed(self):
        # kills MT8 (the rollback narrowed to GitError, OSError and KeyboardInterrupt —
        # the BASE: a RuntimeError left the tree half-applied) and MT8b (an exception
        # swallowed into a return code)
        root = self.rich("runtime-error")
        with Crash("git checkout-index", error=RuntimeError).armed():
            err = self.raised_after_rollback(root, RuntimeError)
        self.assertIn("APPLY FAILED mid-way: RuntimeError(", err)

    def test_T9_SIGTERM_and_SIGHUP_are_rolled_back_and_the_handlers_given_back(self):
        # kills MT9 (no conversion — the BASE: the bench's own handler fires, nothing is
        # rolled back), MT9b (the previous handlers not restored) and MT9c (a handler
        # installed OUTSIDE the transaction, seen by the pre-pass)
        if os.name == "nt":
            raise unittest.SkipTest("os.kill on Windows terminates the process outright: no handler runs")
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name)
            with self.subTest(signal=name):
                def bench(signum, _frame):
                    raise BenchSignal(signum)
                self.addCleanup(signal.signal, sig, signal.signal(sig, bench))
                seen, real_prepass = [], st._refuse_if_path_conflict

                def prepass(*a, **k):
                    seen.append(signal.getsignal(sig))
                    return real_prepass(*a, **k)
                root = self.rich(f"signal-{name}")
                with mock.patch.object(st, "_refuse_if_path_conflict", prepass), \
                        Crash("git checkout-index", error=send(sig)).armed():
                    err = self.raised_after_rollback(root, KeyboardInterrupt)
                self.assertIn(f"signal {int(sig)} during --apply", err)
                self.assertIs(signal.getsignal(sig), bench, "the previous handler is not restored")
                self.assertEqual(seen, [bench], "a handler is installed outside the transaction")

    @contextlib.contextmanager
    def fake_git(self, mode: str, **knobs: float):
        """FAKE_GIT first on PATH for the block; `knobs` patch the runner's module
        (`_GIT_TIMEOUT`, `_TERM_GRACE`) — whichever module defines `st.git`."""
        if os.name == "nt" or not shutil.which("git") or any(c.isspace() for c in sys.executable):
            raise unittest.SkipTest("POSIX signals and a shebang to this interpreter are needed")
        bench = Path(self._tmp.name) / "fake-bin"
        bench.mkdir(exist_ok=True)
        (bench / "git").write_text(f"#!{sys.executable}\n{FAKE_GIT}", encoding="utf-8")
        os.chmod(bench / "git", 0o755)
        self.addCleanup(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, bench_handler))
        env = {"PATH": f"{bench}{os.pathsep}{os.environ.get('PATH', '')}", "FAKE_GIT_MODE": mode,
               "FAKE_GIT_REAL": shutil.which("git"), "FAKE_GIT_RUN": str(os.getpid())}
        runner = sys.modules[st.git.__module__]
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, env))
            for name, value in knobs.items():
                stack.enter_context(mock.patch.object(runner, name, value, create=True))
            yield

    def no_lock_and_rolled_back(self, root: Path, before: tuple[str, str, str], err: str) -> None:
        self.assertNotIn("ROLLBACK INCOMPLETE", err)  # THE WITNESS (the BASE: index.lock exists)
        self.assertFalse((root / ".git/index.lock").exists(), "a killed git left its lock behind")
        self.restored(root, before, err)

    def test_T10_SIGTERM_while_git_holds_its_lock_the_child_gets_SIGTERM_rolled_back(self):
        # kills MT10 (`subprocess.run` — the BASE: SIGKILL to git after 0.25 s, `index.lock`
        # left, `read-tree` refused, ROLLBACK INCOMPLETE, M README.md, AD fresh/dir/f.txt) and
        # MT10b (the child stopped by `kill()` directly)
        root = self.rich("lock-signal")
        before, err = state(root), io.StringIO()
        with self.fake_git("signal"), self.assertRaises(KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            st.main(["--root", str(root), *_APPLY_OK])
        self.assertIn(f"signal {int(signal.SIGTERM)} during --apply", err.getvalue())
        self.no_lock_and_rolled_back(root, before, err.getvalue())

    def test_T10b_a_git_TIMEOUT_stops_the_child_by_SIGTERM_a_GitError_rolled_back(self):
        # kills MT10 and MT10b on the timeout branch (the BASE: SIGKILL, lock left,
        # ROLLBACK INCOMPLETE): the timeout is a GitError, so 18 and never 17
        root = self.rich("lock-timeout")
        before = state(root)
        with self.fake_git("hang", _GIT_TIMEOUT=3):
            code, out, err = self.apply(root)
        self.no_lock_and_rolled_back(root, before, err)
        self.assertEqual(code, st.EXIT_VERIFY_FAILED, err + out)
        self.assertIn("timed out after 3 s", err)

    def test_T10c_a_git_deaf_to_SIGTERM_is_killed_after_the_grace_and_the_lock_named(self):
        # kills MT10c (no SIGKILL after the grace: the run waits on git for good) and MT10d
        # (the recovery silent on the lock — the BASE: `git reset` alone, which the lock refuses)
        root, started = self.rich("lock-deaf"), time.monotonic()
        err = io.StringIO()
        with self.fake_git("deaf", _TERM_GRACE=0.5), self.assertRaises(KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            st.main(["--root", str(root), *_APPLY_OK])
        self.assertLess(time.monotonic() - started, 30, "the run waited on a git deaf to SIGTERM")
        self.assertIn("ROLLBACK INCOMPLETE", err.getvalue())  # SIGKILL: the lock IS left
        self.assertIn(".git/index.lock exists and no git is running, remove it", err.getvalue())

    def test_T11_an_IGNORED_signal_stays_ignored_and_the_apply_completes(self):
        # kills MT11 (a handler installed over SIG_IGN — the BASE: `nohup` overridden,
        # KeyboardInterrupt: signal 1 during --apply, the run rolled back)
        if os.name == "nt":
            raise unittest.SkipTest("os.kill on Windows terminates the process outright: no handler runs")
        for name in ("SIGHUP", "SIGTERM"):
            sig = getattr(signal, name)
            with self.subTest(signal=name):
                self.addCleanup(signal.signal, sig, signal.signal(sig, signal.SIG_IGN))
                seen, real_git = [], st.git

                def git(root, *args, **kw):
                    if args[:1] == ("checkout-index",):
                        seen.append(signal.getsignal(sig))
                        os.kill(os.getpid(), sig)
                    return real_git(root, *args, **kw)
                with mock.patch.object(st, "git", git):
                    try:
                        code, out, err = self.apply(self.rich(f"ignored-{name}"))
                    except KeyboardInterrupt as exc:
                        self.fail(f"the ignored {name} interrupted the apply: {exc!r}")
                self.assertEqual(code, st.EXIT_OK, err + out)
                self.assertEqual(seen, [signal.SIG_IGN], "a handler is installed over SIG_IGN")
                self.assertIs(signal.getsignal(sig), signal.SIG_IGN)

    def hung_up(self, root: Path) -> None:
        """`--apply` on `root`, the terminal dying then SIGHUP during `checkout-index`: the run
        must raise the INTERRUPT again — never the OSError of a print to the dead pty."""
        if os.name == "nt":
            raise unittest.SkipTest("no SIGHUP on Windows: os.kill there terminates outright")
        self.addCleanup(signal.signal, signal.SIGHUP, signal.signal(signal.SIGHUP, bench_handler))
        saved = sys.stderr
        try:
            with self.assertRaises(KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()), \
                    Crash("git checkout-index", error=hang_up).armed():
                st.main(["--root", str(root), *_APPLY_OK])
        finally:
            sys.stderr = saved

    def test_T12_SIGHUP_on_a_DEAD_terminal_is_rolled_back_then_re_raised(self):
        # kills MT12 (an UNPROTECTED print before the rollback — a bare `print`, not `_say`: on the
        # dead pty it raises OSError EIO, the rollback never runs, the tree left half-applied) and
        # MT12b (a print after the rollback unguarded: an OSError goes on instead of the interrupt)
        root = self.rich("dead-tty")
        before = state(root)
        self.hung_up(root)
        self.assertEqual(state(root), before)  # THE WITNESS
        self.assertFalse((root / "fresh").exists(), "a directory the run created is left behind")

    def test_T12b_a_FAILED_rollback_on_a_dead_terminal_still_re_raises_the_interrupt(self):
        # kills MT12c (`print_recovery` unguarded: on ROLLBACK INCOMPLETE its first line to the
        # dead pty raises OSError, and the interrupt is lost)
        with mock.patch.object(st, "_rollback", return_value=["x: injected, not undone"]):
            self.hung_up(self.rich("dead-tty-incomplete"))

    def test_T12c_on_a_LIVE_terminal_the_interrupt_is_said_BEFORE_the_rollback(self):
        # kills MT12d (nothing said before the rollback — the tip of the dead-terminal fix: a
        # second Ctrl-C while the rollback runs stops it without a word, where the base before
        # that fix had printed APPLY INTERRUPTED). The spy reads stderr as the rollback STARTS
        root, real, said = self.rich("live-tty"), st._rollback, []

        def spy(*args, **kw):
            said.append(sys.stderr.getvalue())
            return real(*args, **kw)
        with Crash("git checkout-index", error=KeyboardInterrupt).armed(), \
                mock.patch.object(st, "_rollback", spy):
            self.raised_after_rollback(root, KeyboardInterrupt)
        self.assertEqual(len(said), 1, said)
        self.assertIn("APPLY INTERRUPTED mid-way", said[0])  # THE WITNESS
        self.assertIn("ROLLING BACK — wait: a Ctrl-C now stops the rollback", said[0])

    def test_T12d_a_rollback_that_RAISES_leaves_the_headline_and_the_failures_said(self):
        # kills MT12e (the headline or the failures said AFTER the rollback — the tip of the
        # dead-terminal fix: a rollback that raises left VERIFICATION FAILED unsaid, stderr empty)
        root, err = self.rich("rollback-raises"), io.StringIO()
        with mock.patch.object(st, "verify_manifest", return_value=["x: injected mismatch"]), \
                mock.patch.object(st, "_rollback", side_effect=RuntimeError("injected")), \
                self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            st.main(["--root", str(root), *_APPLY_OK])
        self.assertIn("VERIFICATION FAILED", err.getvalue())
        self.assertIn("  ! x: injected mismatch", err.getvalue())
        self.assertIn("ROLLING BACK", err.getvalue())

    def test_T12e_the_failures_said_AFTER_the_rollback_a_Ctrl_C_there_never_stops_it(self):
        # kills MT12f (the failures said BEFORE the rollback, outside the signal window — the tip of
        # the ter correction: 20 000 failures to a stderr pipe nobody reads, then a SIGINT, and the
        # rollback never ran, rc -2, where the base c0455c74 restored the tree). The Ctrl-C lands
        # on the first failure line said
        root, real_say = self.rich("failures-blocked"), st._say
        before = state(root)

        def say(line: str) -> None:
            if line.lstrip().startswith("!"):
                raise KeyboardInterrupt("injected: a Ctrl-C while the failures are said")
            real_say(line)
        with mock.patch.object(st, "verify_manifest", return_value=["x: injected mismatch"]), \
                mock.patch.object(st, "_say", say), self.assertRaises(KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            st.main(["--root", str(root), *_APPLY_OK])
        self.assertEqual(state(root), before)  # THE WITNESS
        self.assertFalse((root / "fresh").exists(), "a directory the run created is left behind")

    def test_T6_links_judged_AFTER_the_TAKE_are_rolled_back_complete_T1113(self):
        # kills MT6 (a created path git turned into a directory counted as "not
        # undone" — ROLLBACK INCOMPLETE on a tree that IS restored). Both pre-passes
        # bypassed: the SOURCE tracks `.agents/state` as a LINK out of the tree and
        # a seed goes under it; `checkout-index` never writes through the link
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        self.repo()
        _git(self.root, "checkout", "-q", "main")
        try:
            os.symlink(outside, self.root / ".agents/state")
        except (OSError, NotImplementedError) as exc:
            raise unittest.SkipTest(f"no symbolic link here: {exc}") from exc
        _git(self.root, "add", "--", ".agents/state")
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "link")
        _git(self.root, "checkout", "-q", "template/starter-kit")
        before = state(self.root)
        with mock.patch.object(st, "_refuse_if_seed_through_link", lambda *a, **k: None, create=True), \
                mock.patch.object(st, "_refuse_if_path_conflict", lambda *a, **k: None, create=True):
            code, out, err = self.apply()
        self.assertEqual(state(self.root), before, err)
        self.assertEqual(code, st.EXIT_VERIFY_FAILED, err + out)
        self.assertIn("ROLLED BACK", err)
        self.assertNotIn("Recovery", err)
        self.assertEqual(sorted(outside.iterdir()), [], err)

    def test_T7_a_non_UTF8_source_name_is_never_fed_back_renamed(self):
        # kills MT7 (no guard): `git()` decodes `bad\xffname` as `bad�name`, and
        # `update-index` staged THAT name — a renamed file, verified clean, rc 0.
        # Built by plumbing in a THROW-AWAY index: the template checkout is untouched
        self.repo()
        root, env = str(self.root), {**os.environ, "GIT_INDEX_FILE": str(Path(self._tmp.name) / "idx")}
        blob = _git(self.root, "rev-parse", "main:README.md").stdout.strip().encode()
        subprocess.run(["git", "-C", root, "read-tree", "main"], env=env, check=True)
        subprocess.run(["git", "-C", root, "update-index", "-z", "--add", "--index-info"], env=env,
                       input=b"100644 " + blob + b"\tbad\xffname\0", check=True)
        tree = subprocess.run(["git", "-C", root, "write-tree"], env=env, capture_output=True,
                              check=True).stdout.decode().strip()
        commit = _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit-tree", tree,
                      "-p", "main", "-m", "non-utf8").stdout.strip()
        _git(self.root, "update-ref", "refs/heads/main", commit)
        before = state(self.root)
        code, out, err = self.apply()
        self.assertEqual(state(self.root), before, err)
        self.assertEqual(code, st.EXIT_CONFIG_ERROR, err + out)
        self.assertIn("are not UTF-8", err)

    def test_T5_modes_travel_a_TAKEn_executable_and_link_keep_the_sources(self):
        # kills MT5 (every TAKE staged 100644 — `update-index` takes the mode it is
        # given, `git checkout` read it) and MT5b (the verification hashing the
        # file a link points at — the BASE: "link: expected blob <the link's>,
        # got <README.md's>", VERIFICATION FAILED on a sound apply)
        self.repo()
        _git(self.root, "checkout", "-q", "main")
        (self.root / "tool.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(self.root / "tool.sh", 0o755)
        try:
            os.symlink("README.md", self.root / "link")
        except (OSError, NotImplementedError) as exc:
            raise unittest.SkipTest(f"no symbolic link here: {exc}") from exc
        _git(self.root, "add", "--", "tool.sh", "link")
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "modes")
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, out, err = self.apply()
        self.assertEqual(code, st.EXIT_OK, err + out)
        staged = _git(self.root, "ls-files", "-s", "--", "tool.sh", "link").stdout.split("\n")
        source = _git(self.root, "ls-tree", "main", "--", "tool.sh", "link").stdout.split("\n")
        self.assertEqual([s.split()[:2] for s in staged if s], [s.split()[::2] for s in source if s])
        self.assertTrue((self.root / "link").is_symlink())


README = HERE.parent / "README.md"


class FirstSeededSyncProcedureTests(unittest.TestCase):
    """The README's "First seeded sync" procedure names BY HAND the files to copy out of the
    repository to run the SOURCE's script: a module extracted later and left out of that list
    breaks the procedure in silence. Copied as the README says, alone in a throw-away folder,
    the script must at least start."""

    def named(self) -> list[str]:
        """The `.agents/bin/*.py` the procedure names, `sync_template.py` among them."""
        text = README.read_text(encoding="utf-8")
        start = text.index("First seeded sync")
        paragraph = text[start:text.index("Rules live in", start)]
        names = sorted(set(re.findall(r"\.agents/bin/([A-Za-z0-9_]+\.py)", paragraph)))
        self.assertIn("sync_template.py", names, paragraph)
        return names

    def test_P1_the_files_the_procedure_names_are_enough_to_run_the_script(self):
        # kills MP1 (the README naming `sync_template.py` alone — the procedure before the
        # sibling module was named: ModuleNotFoundError: No module named 'sync_template_proc')
        names = self.named()
        env ={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CLAUDE_PROJECT_DIR")}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            for name in names:
                shutil.copyfile(HERE / name, Path(tmp) / name)
            run = subprocess.run([sys.executable, "-B", "-E", "-s", str(Path(tmp) / "sync_template.py"),
                                  "--help"], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, f"copied {names} alone: {run.stderr}")  # THE WITNESS

    def test_P2_every_import_of_the_named_modules_is_stdlib_or_named_at_any_depth(self):
        # kills MLAZY (a sibling imported LAZILY, inside `do_apply`, and left out of the README:
        # `--help` never reaches it, so P1 stays green while the procedure breaks on the first
        # `--apply`). Every import node of every named module is walked, top level or nested
        names = self.named()
        allowed = {*sys.stdlib_module_names, "__future__", *(n[:-3] for n in names)}
        seen, strays = set(), []
        for name in names:
            for node in ast.walk(ast.parse((HERE / name).read_text(encoding="utf-8"), name)):
                if isinstance(node, ast.Import):
                    firsts = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):  # a relative one ("." first) never allowed
                    firsts = ["." * node.level + (node.module or "").split(".")[0]]
                else:
                    continue
                seen.update(firsts)
                strays += [f"{name}:{node.lineno}: {first}" for first in firsts if first not in allowed]
        self.assertIn("sync_template_proc", seen, "the walk met no sibling import: it read nothing")
        self.assertEqual(strays, [], "imported, neither stdlib nor named by the README")  # THE WITNESS


if __name__ == "__main__":
    unittest.main()
