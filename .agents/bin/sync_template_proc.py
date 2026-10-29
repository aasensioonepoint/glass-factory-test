"""sync_template_proc.py — THE GIT RUNNER of `sync_template.py`, and the signal window of its
`--apply` transaction. Extracted from it (T-00001163) so that the script stays under the
1600-line bound; it has no other consumer and is not run by itself. `sync_template.py` loads it
as `kickoff_guard.py` loads its siblings (its own directory put on `sys.path`, then a plain
import) and re-exports every public name below, so `st.git`, `st.GitError` and `st.read_blob`
are what they were — and a test that patches `st.git` still reaches every caller in it.

WHY NOT `subprocess.run` (critic-opus F6 bis T1, measured). On ANY exception while it waits —
a KeyboardInterrupt, which the transaction also makes of SIGTERM and SIGHUP, or its own timeout —
`subprocess.run` gives the child 0.25 s, then SIGKILL. A git killed that way cannot remove its
`index.lock`, and the rollback's `read-tree HEAD` / `git checkout HEAD --` then fail on it:
ROLLBACK INCOMPLETE, the index left loaded. Here the child gets SIGTERM first — git's own handler
removes its lock, then exits —, a bounded wait (`_TERM_GRACE`), and SIGKILL only as the last
resort (a git deaf to SIGTERM, or a further signal during the wait); the exception then goes on,
a timeout turned into `GitError`. BOUND: a git killed by that last resort still leaves its lock,
which is why the manual recovery names it. POSIX ONLY: on Windows `Popen.terminate()` is
`TerminateProcess`, an outright stop — git's handler never runs, the lock stays, and the manual
recovery applies.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
from pathlib import Path

_GIT_TIMEOUT = 300  # s: a network `fetch` may be slow; every local call answers in well under a second
_TERM_GRACE = 10  # s: a git given SIGTERM removes its lock and exits well within it


class GitError(Exception):
    """A git command that was expected to succeed did not."""


def _stop(proc: subprocess.Popen) -> None:
    """SIGTERM, then at most `_TERM_GRACE` s, then SIGKILL. A further exception during the wait
    (the grace ran out, or one more signal) goes straight to SIGKILL; the caller's own exception
    is the one that goes on."""
    try:
        proc.terminate()
        proc.wait(timeout=_TERM_GRACE)
    except BaseException:  # the last resort, whatever interrupted the wait
        proc.kill()
        proc.wait()


def run_git(root: Path, args: tuple[str, ...], *, stdin: str | bytes | None = None,
            env: dict[str, str] | None = None, text: bool = True) -> subprocess.CompletedProcess:
    """`git -C <root> <args>`, stdout and stderr captured; `stdin`, when given, is written whole
    (a str under `text`, decoded UTF-8 with replacement; bytes otherwise). Whatever interrupts
    the wait, the child is STOPPED (`_stop`) before the exception goes on; a timeout is a
    `GitError`. The return code is never judged here."""
    argv = ["git", "-C", str(root), *args]
    codec = {"encoding": "utf-8", "errors": "replace"} if text else {}
    with subprocess.Popen(argv, stdin=None if stdin is None else subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                          **codec) as proc:
        try:
            out, err = proc.communicate(stdin, timeout=_GIT_TIMEOUT)
        except BaseException as exc:
            _stop(proc)
            if isinstance(exc, subprocess.TimeoutExpired):
                raise GitError(f"git {' '.join(args)} timed out after {_GIT_TIMEOUT} s") from exc
            raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def git(root: Path, *args: str, check: bool = True,
        literal: bool = False, stdin: str | None = None) -> subprocess.CompletedProcess:
    """`literal=True` runs git under `GIT_LITERAL_PATHSPECS=1`: every path after
    `--` is a NAME, never a pattern — a tracked `f[ab].txt` must not also match
    `fa.txt`. Set on every call whose pathspecs are plan paths. `stdin` feeds the
    `-z --stdin` / `--index-info` plumbing: NUL-separated names, never argv."""
    result = run_git(root, args, stdin=stdin,
                     env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"} if literal else None)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def read_blob(root: Path, sha: str) -> bytes:
    """A blob's RAW bytes. `git()` decodes text with replacement; a seed is
    written byte for byte, so its blob is read without any decoding."""
    r = run_git(root, ("cat-file", "blob", sha), text=False)
    if r.returncode != 0:
        detail = r.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git cat-file blob {sha} failed: {detail}")
    return r.stdout


@contextlib.contextmanager
def signals_as_interrupt():
    """SIGTERM and SIGHUP raise KeyboardInterrupt, as SIGINT already does, for the TRANSACTION
    only: the previous handlers come back in the `finally`, whatever happened, and none is
    installed outside it. A signal already IGNORED stays so (`nohup` remains the master,
    T-00001163). Off the main thread (`signal.signal` refuses there) or where the signal does
    not exist (SIGHUP on Windows), nothing is converted. The handlers are given back BEFORE the
    rollback runs: a SIGTERM or SIGHUP during it, or a second Ctrl-C, stops it."""
    def interrupt(signum, _frame):
        raise KeyboardInterrupt(f"signal {signum} during --apply")
    previous = {}
    try:
        for sig in (getattr(signal, name, None) for name in ("SIGTERM", "SIGHUP")):
            if (sig is not None and threading.current_thread() is threading.main_thread()
                    and signal.getsignal(sig) is not signal.SIG_IGN):
                previous[sig] = signal.signal(sig, interrupt)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, signal.SIG_DFL if handler is None else handler)
