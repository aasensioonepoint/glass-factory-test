#!/usr/bin/env python3
"""Console mirror LAUNCHER — T-00000087 (M5b).

    python .agents/bin/wrap.py <cli> [args…]

Runs `<cli>` through a pseudo-terminal, duplicating everything the CLI PRINTS
into a spool the dashboard daemon can read (`/api/term`, `/api/term/stream`)
while the bytes still reach the real terminal verbatim. `claude`, `codex`,
`gemini` — anything that draws a TUI — behaves exactly as it does unwrapped.

WHAT THIS CANNOT DO, STATED RATHER THAN IMPLIED
-----------------------------------------------
* ONE WAY, STRICTLY. The dashboard has NO path back into the child: this
  module exposes no socket, no fifo, no control file, and the two HTTP routes
  that read its spool are GET-only. Injecting a keystroke from the UI is
  T-00000088, deliberately blocked behind the T-00000028 gate. The ONLY writer
  into the child is the LOCAL keyboard on this terminal's own stdin, forwarded
  below — without it a wrapped interactive CLI could not be used at all, which
  would make the nominal branch strictly worse than the degraded one. Those
  bytes are forwarded and NEVER spooled: what you type is not part of the
  mirror, and cannot be read back through the API.
* AN ALREADY-OPEN TERMINAL IS INVISIBLE, BY CONSTRUCTION. There is no way to
  attach to a console someone started by hand — a mirror exists only for
  sessions launched THROUGH this file. The UI must say so rather than render
  silence (`Sessions.jsx` badges an unmirrored session « événements seulement »).
* SECRETS PRINTED IN THE TERMINAL ARE NOT REDACTABLE. This is a faithful copy
  of a byte stream, not a parsed transcript; a token echoed by a CLI lands in
  the spool as-is. Declared residual, not a defect: the spool lives under
  `.agents/state/local/` (git-ignored), the routes that expose it are
  token-gated on 127.0.0.1, and class-0 secret scanning still applies to what
  gets COMMITTED. Anyone who can read the spool already has the daemon token.
* macOS IS THE POSIX BRANCH AND IS NOT TESTED IN CI. CI is ubuntu only
  (L-00000068); the macOS path is the same stdlib `pty` code with no
  platform-specific branch, and that is an ACCEPTED risk, not a measured pass.

PLATFORM SPLIT — the only real one in this lot
----------------------------------------------
* POSIX: stdlib `pty` + `select` + `TIOCSWINSZ` on `SIGWINCH`. Byte-verbatim.
* Windows: ConPTY through `pywinpty`, imported LAZILY. When it is absent the
  launcher does NOT fail: it says so on stderr and executes the CLI DIRECTLY,
  with the child's exit code propagated. A launcher that refuses to launch is
  a worse outcome than a launcher without a mirror.

  PIN: pywinpty==3.0.5. It is deliberately NOT in a manifest — this repo has no
  Python dependency manifest ON PURPOSE (`pytest.ini` says why: a manifest here
  flips stack detection and trips the SCA gate). RE-BUMP PROCEDURE: changing
  the pin in this docstring and in `_PYWINPTY_PIN` is a dependency change like
  any other — run the SCA gate MANUALLY for it (`.agents/security/sca-scan.sh`
  cannot see a pin that lives in a docstring), record the verdict, and only
  then ship the new number. An unaudited bump here is an unaudited native
  extension loaded into the process that runs the coding agent.

  Windows fidelity caveat: `winpty.PtyProcess.read()` hands back TEXT already
  decoded by pywinpty, so the Windows spool is UTF-8-NORMALISED rather than
  byte-verbatim (an invalid sequence does not round-trip). POSIX is verbatim.

SPOOL LAYOUT — `.agents/state/local/term/`
------------------------------------------
    <sid>.raw        append-only, raw ANSI, never truncated in place
    <sid>.meta.json  atomically rewritten {sid, cmd, pid, cols, rows,
                     started, ended, gen, resize}

`sid` is `<utc-timestamp>-<pid>`. The meta is created in EXCLUSIVE mode ("x"):
a collision is refused outright rather than silently adopting another
session's file. `cmd` is the BASENAME ONLY — never the full argv, never the
environment: a mirror list that leaked `--api-key …` from a command line would
undo the very custody rules the rest of this kit enforces.

THE RING, AND WHY ITS RECIPE IS EXACT
-------------------------------------
A mirror runs for hours; the spool is capped at 4 MiB and keeps the last 1 MiB.
The rotation is the one place a concurrent reader could observe a torn file, so
the order is fixed and asserted by `test_wrap.py`:

  1. the 1 MiB tail is written to `<sid>.raw.part`, flushed AND fsync'd, closed;
  2. `gen` is incremented and published in the meta ATOMICALLY (tmp + fsync +
     `os.replace`) BEFORE the swap — a reader that sees the new generation and
     the old content resets to offset 0 and replays, which the front absorbs
     with a `term.reset()`; a reader that saw new content under an old
     generation would silently splice two different files together;
  3. `os.replace(part, raw)` with a BOUNDED retry (30 × 10 ms), because on
     Windows a reader holding a transient handle makes the replace fail. If the
     retries are exhausted the rotation is ABANDONED for this round: the append
     continues into the existing file and the swap is retried later. There is
     NO truncate-in-place fallback — that is exactly the operation that hands a
     reader a file shorter than its own offset with different bytes in it.
"""
from __future__ import annotations

import codecs
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# The pin the degraded message quotes. One literal, so the stderr line, the
# docstring's re-bump procedure and any future installer cannot disagree.
_PYWINPTY_PIN = "3.0.5"

# Ring geometry. 4 MiB is roughly a day of an ordinary agent session's output;
# 1 MiB of tail is far more than any terminal can show at once, so a reader
# reconnecting after a rotation still lands in context.
_SPOOL_CAP_BYTES = 4 * 1024 * 1024
_SPOOL_KEEP_BYTES = 1 * 1024 * 1024

# Bounded retry for `os.replace` — Windows only in practice (POSIX rename over
# an open file always succeeds), but applied on both so the two platforms run
# the SAME code path and the test that exercises it is not skipped on ubuntu.
_REPLACE_ATTEMPTS = 30
_REPLACE_SLEEP_S = 0.01

# After an abandoned rotation, do not retry on the very next write: a reader
# holding a handle would otherwise make every subsequent write pay for a failed
# 300 ms retry loop and bump `gen` each time.
_ROTATE_BACKOFF_S = 0.5

# Windows resize polling — there is no SIGWINCH; `shutil.get_terminal_size()`
# is cheap and 500 ms matches the dashboard's own poll interval.
_WIN_RESIZE_POLL_S = 0.5

_READ_CHUNK = 65536


def term_dir() -> Path:
    """`.agents/state/local/term/`, resolved from THIS FILE's location — the
    same convention as `events._events_dir()`, and for the same reason: a
    launcher is invoked from arbitrary working directories, so cwd is not a
    safe anchor. `AGENTS_TERM_DIR` is the test escape hatch, and is what lets
    `dashboard.py` (which imports this module rather than re-deriving the path)
    read a redirected tree in its own suite."""
    override = os.environ.get("AGENTS_TERM_DIR")
    if override:
        return Path(override)
    return HERE.parent / "state" / "local" / "term"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_sid(pid: int | None = None) -> str:
    """`<utc-timestamp>-<pid>`. Unique enough that the exclusive meta creation
    below is a genuine last line of defence rather than the primary mechanism,
    and readable enough that a human can tell two spools apart."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{pid or os.getpid()}"


# ---------------------------------------------------------------------------
# Liveness — shared with `dashboard.py`, which imports this module instead of
# writing its own copy.
# ---------------------------------------------------------------------------

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid: int) -> bool | None:
    """True / False / None, where None means CANNOT TELL — and that third
    answer is the point. A mirror whose meta has no `ended` and whose pid is
    gone is a session that died without closing its spool; rendering it as
    "live" is a lie and rendering it as "ended" is a different lie, so the
    caller gets `unknown` and says so.

    `os.kill(pid, 0)` is used ONLY on POSIX. On Windows CPython implements
    `os.kill` as OpenProcess + TerminateProcess, so `os.kill(pid, 0)` would
    KILL the process with exit code 0 — a liveness probe that kills what it
    probes. Windows therefore goes through OpenProcess/GetExitCodeProcess with
    a query-only right."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, owned by someone else
        except OSError:
            return None
        return True
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - a probe must never raise into a route
        return None


# ---------------------------------------------------------------------------
# Atomic meta + bounded replace
# ---------------------------------------------------------------------------

def _replace_with_retry(src: Path, dst: Path,
                        attempts: int = _REPLACE_ATTEMPTS,
                        sleep_s: float = _REPLACE_SLEEP_S) -> bool:
    """`os.replace` that tolerates a reader's TRANSIENT handle. Returns False
    after the bounded retry rather than raising: every caller here has a
    correct do-nothing fallback, and "the swap did not happen this round" is a
    recoverable state while a raised exception inside the output loop is a dead
    mirror."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return True
        except OSError:
            if attempt == attempts - 1:
                return False
            time.sleep(sleep_s)
    return False


def write_meta_atomic(path: Path, meta: dict[str, Any]) -> bool:
    """tmp + fsync + `os.replace`, same discipline as every other state writer
    in this kit. A reader therefore sees either the previous meta or the new
    one, never a half-written JSON document — which matters most for `gen`,
    the field a reader uses to decide whether to reset its offset."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(meta, fh, ensure_ascii=False, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        return False
    if _replace_with_retry(tmp, path):
        return True
    try:
        tmp.unlink()
    except OSError:
        pass
    return False


def read_meta(path: Path) -> dict[str, Any] | None:
    """Never raises. A meta being rewritten, missing or corrupt yields None and
    the caller degrades — the same posture every reader in `dashboard.py` takes
    towards every store it reads."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# The spool
# ---------------------------------------------------------------------------

class Spool:
    """The append-only side of the mirror: the `<sid>.raw` writer, its meta,
    and the ring rotation whose exact recipe is in this module's docstring.

    NOT thread-safe by design — it has exactly one writer, the output loop of
    the session that owns it. The concurrency this class actually has to
    survive is a READER in another process, which is what the rotation order
    is built for."""

    def __init__(self, directory: Path, sid: str, cmd: str, pid: int,
                 cols: int, rows: int, resize: str) -> None:
        self.dir = Path(directory)
        self.sid = sid
        self.raw_path = self.dir / f"{sid}.raw"
        self.part_path = self.dir / f"{sid}.raw.part"
        self.meta_path = self.dir / f"{sid}.meta.json"
        self.gen = 0
        self._meta: dict[str, Any] = {
            "sid": sid,
            # BASENAME ONLY. Never the full argv (flags carry credentials),
            # never the environment.
            "cmd": os.path.basename(str(cmd)),
            "pid": int(pid),
            "cols": int(cols),
            "rows": int(rows),
            "started": _now_iso(),
            "ended": None,
            "gen": 0,
            # "posix" | "poll" | "frozen" — a UI that shows dimensions must be
            # able to say "these are frozen", not imply they track the terminal.
            "resize": resize,
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        # EXCLUSIVE creation: a sid collision refuses cleanly instead of two
        # sessions interleaving bytes into one spool.
        with open(self.meta_path, "x", encoding="utf-8", newline="\n") as fh:
            json.dump(self._meta, fh, ensure_ascii=False, sort_keys=True)
        self._fh = open(self.raw_path, "ab", buffering=0)
        self._size = self._fh.tell()
        self._next_rotate_at = 0.0

    # -- meta ------------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    def _publish_meta(self) -> bool:
        return write_meta_atomic(self.meta_path, self._meta)

    def set_size(self, cols: int, rows: int) -> None:
        if int(cols) == self._meta["cols"] and int(rows) == self._meta["rows"]:
            return
        self._meta["cols"] = int(cols)
        self._meta["rows"] = int(rows)
        self._publish_meta()

    # -- bytes -----------------------------------------------------------

    def write(self, data: bytes) -> None:
        """Append, then rotate if the cap is reached. Never raises: a spool
        that fails must not take the child's output down with it — the terminal
        keeps working, the mirror is what degrades."""
        if not data:
            return
        try:
            self._fh.write(data)
            self._size = self._fh.tell()
        except (OSError, ValueError):
            # ValueError is what a CLOSED handle raises, and a handle the OS
            # took away is exactly the case this must survive silently.
            return
        if self._size >= _SPOOL_CAP_BYTES and time.monotonic() >= self._next_rotate_at:
            self.rotate()

    def rotate(self) -> bool:
        """The exact recipe. Returns True when the swap happened.

        The writer's own handle is CLOSED before the swap and reopened after,
        because on Windows `os.replace` onto a file this process holds open
        fails unconditionally — the retry loop exists for OTHER processes'
        transient handles, not for our own."""
        try:
            self._fh.flush()
        except (OSError, ValueError):
            pass
        try:
            os.fsync(self._fh.fileno())
        except (OSError, ValueError):
            pass
        try:
            self._fh.close()
        except (OSError, ValueError):
            pass

        swapped = False
        try:
            # (1) tail -> .part, flushed and fsync'd before anything else moves.
            try:
                with open(self.raw_path, "rb") as src:
                    size = src.seek(0, os.SEEK_END)
                    src.seek(max(0, size - _SPOOL_KEEP_BYTES), os.SEEK_SET)
                    tail = src.read()
                with open(self.part_path, "wb") as part:
                    part.write(tail)
                    part.flush()
                    os.fsync(part.fileno())
            except OSError:
                self._next_rotate_at = time.monotonic() + _ROTATE_BACKOFF_S
                return False

            # (2) the NEW generation is published BEFORE the content changes.
            self.gen += 1
            self._meta["gen"] = self.gen
            self._publish_meta()

            # (3) the swap, bounded. On failure the rotation is abandoned for
            # this round — the old file is still whole and still being
            # appended to. NEVER a truncate-in-place.
            swapped = _replace_with_retry(self.part_path, self.raw_path)
            if not swapped:
                self._next_rotate_at = time.monotonic() + _ROTATE_BACKOFF_S
                try:
                    self.part_path.unlink()
                except OSError:
                    pass
        finally:
            try:
                self._fh = open(self.raw_path, "ab", buffering=0)
                self._size = self._fh.tell()
            except (OSError, ValueError):
                # Reopen failed: further writes are dropped (guarded above),
                # the terminal is unaffected. Nothing here may raise.
                pass
        return swapped

    def close(self) -> None:
        """Stamp `ended` and let go. A meta WITHOUT `ended` and with a dead pid
        is what `/api/term` reports as `unknown`, so writing this stamp is what
        distinguishes a clean end from a crash."""
        try:
            self._fh.flush()
            os.fsync(self._fh.fileno())
        except (OSError, ValueError):
            pass
        try:
            self._fh.close()
        except (OSError, ValueError):
            pass
        self._meta["ended"] = _now_iso()
        self._publish_meta()


# ---------------------------------------------------------------------------
# PTY backends
# ---------------------------------------------------------------------------

def _terminal_size(default_cols: int = 80, default_rows: int = 24) -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size((default_cols, default_rows))
        return max(1, int(size.columns)), max(1, int(size.lines))
    except Exception:  # noqa: BLE001 - a size probe must never end a session
        return default_cols, default_rows


class PtySession:
    """The common shape both backends implement: `spawn`, `resize`, `read`.

    Instantiated through `open_session()`, never directly — the choice of
    backend, and the DEGRADED answer when there is no backend at all, is a
    single decision made in one place."""

    backend = "abstract"
    resize_mode = "frozen"

    def spawn(self, argv: list[str], cols: int, rows: int) -> int:
        raise NotImplementedError

    def read(self) -> bytes:
        raise NotImplementedError

    def write_stdin(self, data: bytes) -> None:
        raise NotImplementedError

    def resize(self, cols: int, rows: int) -> None:
        raise NotImplementedError

    def alive(self) -> bool:
        raise NotImplementedError

    def wait(self) -> int:
        raise NotImplementedError


class _PosixPty(PtySession):
    """stdlib `pty` + `select`. Byte-verbatim in both directions."""

    backend = "posix"
    resize_mode = "posix"

    def __init__(self) -> None:
        self.pid = -1
        self.master = -1
        self._exit_code: int | None = None
        self._winch = False

    def spawn(self, argv: list[str], cols: int, rows: int) -> int:
        import pty
        import signal

        pid, master = pty.fork()
        if pid == 0:  # child
            try:
                os.execvp(argv[0], argv)
            except Exception:  # noqa: BLE001 - the child must never unwind
                os._exit(127)
            os._exit(127)
        self.pid = pid
        self.master = master
        self.resize(cols, rows)
        try:
            signal.signal(signal.SIGWINCH, self._on_winch)
        except (ValueError, OSError, AttributeError):
            # Not the main thread, or no SIGWINCH: dimensions stay as spawned
            # and `resize_mode` says so rather than pretending they track.
            self.resize_mode = "frozen"
        return pid

    def _on_winch(self, _signum, _frame) -> None:
        self._winch = True

    def take_winch(self) -> bool:
        seen, self._winch = self._winch, False
        return seen

    def resize(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios

        try:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ,
                        struct.pack("HHHH", int(rows), int(cols), 0, 0))
        except (OSError, ValueError):
            pass

    def read(self) -> bytes:
        try:
            return os.read(self.master, _READ_CHUNK)
        except OSError:
            # EIO on Linux is the NORMAL end of a pty master once the child
            # closed the slave — an EOF, not a failure.
            return b""

    def write_stdin(self, data: bytes) -> None:
        try:
            os.write(self.master, data)
        except OSError:
            pass

    def alive(self) -> bool:
        if self._exit_code is not None:
            return False
        try:
            done, status = os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            return False
        if done == 0:
            return True
        self._exit_code = os.waitstatus_to_exitcode(status)
        return False

    def wait(self) -> int:
        if self._exit_code is not None:
            return self._exit_code
        try:
            _, status = os.waitpid(self.pid, 0)
            self._exit_code = os.waitstatus_to_exitcode(status)
        except OSError:
            self._exit_code = 0
        return self._exit_code


class _WinPty(PtySession):
    """ConPTY through `pywinpty`, imported LAZILY inside `spawn` so that
    importing this module on a machine without the package costs nothing and
    fails nowhere — the absence is decided by `open_session()`, once."""

    backend = "winpty"
    resize_mode = "poll"

    def __init__(self) -> None:
        self.proc = None
        self._exit_code: int | None = None
        # THE DECODER IS HELD AT THE SINK, NOT AT THE PUMP (T-00000092).
        # `pump_stdin` reads ONE BYTE at a time — deliberate, because there is no
        # `select()` on a Windows console — so a keystroke that is several bytes
        # wide (any accented character, anything an IME composes) arrives here as
        # several separate calls. Decoding per call turned `é` (0xC3 0xA9) into
        # TWO replacement characters: the child received mojibake for a key the
        # user pressed correctly. An INCREMENTAL decoder holds the partial
        # sequence between calls and emits the character once it is complete.
        # `errors="replace"` is kept, so a byte that is genuinely invalid still
        # becomes exactly one U+FFFD rather than being swallowed.
        # WHAT IS LOST, KNOWINGLY: a partial sequence still pending when the
        # session ends is an INCOMPLETE keystroke by definition — there is no
        # character to deliver, and inventing one would be worse than dropping it.
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def spawn(self, argv: list[str], cols: int, rows: int) -> int:
        from winpty import PtyProcess  # noqa: PLC0415 - lazy on purpose

        self.proc = PtyProcess.spawn(list(argv), dimensions=(int(rows), int(cols)))
        if not hasattr(self.proc, "setwinsize"):
            # No resize API on this build: the dimensions are FROZEN at the
            # spawn size and the meta says `frozen`, so the UI renders a mirror
            # it knows is fixed instead of one it wrongly believes follows.
            self.resize_mode = "frozen"
        return int(getattr(self.proc, "pid", 0) or 0)

    def resize(self, cols: int, rows: int) -> None:
        if self.resize_mode != "poll" or self.proc is None:
            return
        try:
            self.proc.setwinsize(int(rows), int(cols))
        except Exception:  # noqa: BLE001 - a resize must never end a session
            pass

    def read(self) -> bytes:
        if self.proc is None:
            return b""
        try:
            chunk = self.proc.read(_READ_CHUNK)
        except EOFError:
            return b""
        except Exception:  # noqa: BLE001 - treat any read failure as EOF
            return b""
        if not chunk:
            return b""
        # pywinpty decodes for us; see the docstring's fidelity caveat.
        return chunk if isinstance(chunk, bytes) else chunk.encode("utf-8", "replace")

    def write_stdin(self, data: bytes) -> None:
        if self.proc is None or not data:
            return
        # A partial sequence yields "" and is HELD until the next byte arrives;
        # writing nothing is the correct behaviour there, not a dropped keystroke.
        text = self._dec.decode(data)
        if not text:
            return
        try:
            self.proc.write(text)
        except Exception:  # noqa: BLE001 - a dead child is not this loop's error
            pass

    def alive(self) -> bool:
        if self.proc is None:
            return False
        try:
            return bool(self.proc.isalive())
        except Exception:  # noqa: BLE001
            return False

    def wait(self) -> int:
        if self._exit_code is not None:
            return self._exit_code
        try:
            self.proc.wait()
            self._exit_code = int(self.proc.exitstatus or 0)
        except Exception:  # noqa: BLE001
            self._exit_code = 0
        return self._exit_code


def winpty_available() -> bool:
    """Whether the Windows backend can actually be used. Import-based, not
    version-based: a package that is installed but unloadable (wrong ABI, wrong
    Python) must count as ABSENT, and the degraded path is the correct answer
    for both cases."""
    if os.name != "nt":
        return False
    try:
        import winpty  # noqa: F401,PLC0415
    except Exception:  # noqa: BLE001
        return False
    return True


def open_session() -> PtySession | None:
    """The single place the backend is chosen. None means "no mirror on this
    machine" and the caller runs the CLI directly."""
    if os.name != "nt":
        return _PosixPty()
    if winpty_available():
        return _WinPty()
    return None


# ---------------------------------------------------------------------------
# Run loops
# ---------------------------------------------------------------------------

def run_direct(argv: list[str], reason: str) -> int:
    """DEGRADED, and loud about it: no mirror, but the CLI still runs and its
    exit code is still the launcher's exit code. This is the branch that makes
    `wrap.py` safe to put in front of a command unconditionally."""
    print(f"WRAP DEGRADED: {reason} — miroir désactivé, la commande s'exécute "
          f"normalement (pip install pywinpty=={_PYWINPTY_PIN} pour l'activer)",
          file=sys.stderr, flush=True)
    try:
        return subprocess.call(list(argv))
    except FileNotFoundError:
        print(f"WRAP: commande introuvable: {argv[0]}", file=sys.stderr, flush=True)
        return 127
    except OSError as exc:
        print(f"WRAP: exécution impossible: {type(exc).__name__}",
              file=sys.stderr, flush=True)
        return 126


def _stdout_bytes():
    buffer = getattr(sys.stdout, "buffer", None)
    return buffer if buffer is not None else sys.stdout


def _emit(data: bytes) -> None:
    """The real terminal first, the spool second. A stalled spool must never
    delay what the human sees, and the ORDER is what guarantees the mirror can
    only ever lag the terminal, never lead it."""
    out = _stdout_bytes()
    try:
        out.write(data)
        out.flush()
    except (OSError, ValueError):
        pass


def _run_posix(session: _PosixPty, argv: list[str], spool_dir: Path) -> int:
    import select
    import termios
    import tty

    cols, rows = _terminal_size()
    pid = session.spawn(argv, cols, rows)
    spool = Spool(spool_dir, new_sid(pid), argv[0], pid, cols, rows,
                  session.resize_mode)

    stdin_fd = _stdin_fd()
    saved_tty = None
    if stdin_fd is not None and os.isatty(stdin_fd):
        try:
            saved_tty = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)
        except (termios.error, OSError, ValueError):
            saved_tty = None
    try:
        watch = [session.master] + ([stdin_fd] if stdin_fd is not None else [])
        while True:
            if session.take_winch():
                cols, rows = _terminal_size()
                session.resize(cols, rows)
                spool.set_size(cols, rows)
            try:
                readable, _, _ = select.select(watch, [], [], 0.5)
            except (OSError, ValueError):
                break
            if session.master in readable:
                data = session.read()
                if not data:
                    break
                _emit(data)
                spool.write(data)
            if stdin_fd is not None and stdin_fd in readable:
                # LOCAL KEYBOARD ONLY, and never spooled. See the module
                # docstring: this is the one-way rule's only exception and it
                # runs in the opposite direction to the mirror.
                try:
                    typed = os.read(stdin_fd, 4096)
                except OSError:
                    typed = b""
                if typed:
                    session.write_stdin(typed)
    finally:
        if saved_tty is not None:
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved_tty)
            except (termios.error, OSError, ValueError):
                pass
        spool.close()
        try:
            os.close(session.master)
        except OSError:
            pass
    return session.wait()


def _run_windows(session: _WinPty, argv: list[str], spool_dir: Path) -> int:
    import threading

    cols, rows = _terminal_size()
    pid = session.spawn(argv, cols, rows)
    spool = Spool(spool_dir, new_sid(pid), argv[0], pid, cols, rows,
                  session.resize_mode)

    stop = threading.Event()

    def pump_stdin() -> None:
        """Local keyboard -> child, in a thread because Windows has no
        `select()` over a console handle. Daemon: a blocked read on a console
        that never gets another key must not keep the process alive."""
        source = getattr(sys.stdin, "buffer", None)
        if source is None:
            return
        while not stop.is_set():
            try:
                typed = source.read(1)
            except (OSError, ValueError):
                return
            if not typed:
                return
            session.write_stdin(typed)

    pump = threading.Thread(target=pump_stdin, daemon=True)
    pump.start()

    next_poll = time.monotonic() + _WIN_RESIZE_POLL_S
    try:
        while True:
            data = session.read()
            if data:
                _emit(data)
                spool.write(data)
            elif not session.alive():
                break
            else:
                time.sleep(0.01)
            now = time.monotonic()
            if now >= next_poll:
                next_poll = now + _WIN_RESIZE_POLL_S
                new_cols, new_rows = _terminal_size()
                if (new_cols, new_rows) != (cols, rows):
                    cols, rows = new_cols, new_rows
                    session.resize(cols, rows)
                    spool.set_size(cols, rows)
    finally:
        stop.set()
        spool.close()
    return session.wait()


def _stdin_fd() -> int | None:
    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        return None
    return fd if fd >= 0 else None


def run(argv: list[str], spool_dir: Path | None = None) -> int:
    """Launch `argv` with a mirror when one is available, DIRECTLY when it is
    not. The child's exit code is the return value in every branch — a wrapper
    that swallowed it would break every `&&` and every CI step it sits in."""
    if not argv:
        print("WRAP: usage: python .agents/bin/wrap.py <cli> [args…]",
              file=sys.stderr, flush=True)
        return 2
    directory = Path(spool_dir) if spool_dir is not None else term_dir()
    session = open_session()
    if session is None:
        return run_direct(argv, "pywinpty absent (ConPTY requis sur Windows)")
    try:
        if isinstance(session, _PosixPty):
            return _run_posix(session, argv, directory)
        return _run_windows(session, argv, directory)
    except FileNotFoundError:
        print(f"WRAP: commande introuvable: {argv[0]}", file=sys.stderr, flush=True)
        return 127
    except OSError as exc:
        # A pty that cannot be allocated is not a reason to refuse to run the
        # command: fall back to the same direct execution the missing-backend
        # branch uses.
        return run_direct(argv, f"pseudo-terminal indisponible ({type(exc).__name__})")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # No flags of our own, deliberately: everything after the program name
    # belongs to the wrapped CLI, so `wrap.py claude --help` shows CLAUDE's
    # help rather than being intercepted here. `--` is accepted and dropped for
    # callers who want to be explicit.
    if args and args[0] == "--":
        args = args[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__ or "", file=sys.stderr)
        return 0 if args else 2
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
