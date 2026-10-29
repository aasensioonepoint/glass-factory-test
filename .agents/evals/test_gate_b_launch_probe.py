"""GATE B — T-00000025 shard 2 probe: can the dashboard daemon be launched
DETACHED from the Claude Code `SessionStart` hook on Windows/MSYS at all?

PROBE ONLY. This file builds NOTHING that ships: no daemon, no lock module, no
`/dash`, no auto-stop, no UI. It exists to answer one question empirically
before shard 2 writes a single line of product code, per the routing decision
(S-00000035): "GATE B = sonde de detachement via la vraie surface".

Why the harness is what it is
------------------------------
An earlier version of this probe used a bare `subprocess.Popen` launched
directly from pytest to spawn the "detached" child. An adversarial review
killed it: pytest's own process does not hold the handles a real
`SessionStart` hook invocation holds, so a child spawned straight from pytest
can never reproduce the failure mode under test (a grandchild inheriting the
HOST's captured stdout/stderr pipe, so the host's read-until-EOF never
unblocks). The gate could only ever pass — the same defect class recorded
against this task twice already (shard 0's bind-conflict fixture, shard 1's
path-traversal case pre-normalised by the stdlib).

So every test here drives the REAL surface: `subprocess.run([BASH, hook],
capture_output=True, timeout=N)` against a bash hook script, modelled on
`.agents/evals/test_ledger_parity.py:102-114` (`run_session_start_sh`), which
already runs `.claude/hooks/session-start.sh` exactly this way. The real
`session-start.sh` is READ but NEVER modified; every fixture below is a COPY
written fresh into a per-test tmp dir, with one block replaced: the closing
heredoc that prints the hook's single JSON line (lines 46-49 of the real
script) is where a real shard-2 launcher would most plausibly be added,
because it is the one place in the hook that is already NOT wrapped in a
`>/dev/null` redirect (it cannot be — printing that JSON to the real,
captured stdout is the hook's entire contract). That makes it the one place
where a naive `subprocess.Popen(...)` with no explicit stdio redirection would
inherit the live captured pipe and reproduce the exact hazard the gate is
built to catch. Testing the same launch call wrapped in its own
`bash ... >/dev/null 2>&1` would be testing a different, already-safe shape
and would not be adversarial.
"""
import contextlib
import ctypes
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION_START_SH = ROOT / ".claude" / "hooks" / "session-start.sh"
BASH = shutil.which("bash")

# GATE B measured WINDOWS behaviour: that is the point of the probe, since
# Windows is the platform this kit runs on and the platform whose semantics
# broke the naive designs (L-00000050 bind reuse, L-00000054 sharing
# violations). Several cases below therefore assert facts that are FALSE
# elsewhere — a POSIX rename succeeds with the source fd open, and there is no
# sharing violation to observe. On ubuntu CI they failed, which said nothing
# about the code and everything about the platform, so they are skipped there
# EXPLICITLY rather than loosened into assertions weak enough to pass anywhere
# (that would delete the measurement this file exists to preserve).
WINDOWS = os.name == "nt"
WINDOWS_ONLY = "measures a Windows-specific semantic; false or unobservable on POSIX"

HEREDOC_MARKER_START = '"$PY" - "$CTX" << \'PYEOF\'\nimport json, sys\nprint('
HEREDOC_ORIGINAL = '''"$PY" - "$CTX" << 'PYEOF'
import json, sys
try:
    # T-00000025 shard 2 - dashboard daemon, launched fully DETACHED (GATE B,
    # S-00000041: DEVNULL on all three stdio handles + DETACHED_PROCESS |
    # CREATE_NEW_PROCESS_GROUP on Windows; start_new_session on POSIX). The
    # child dedupes against state/local/dashboard.lock on its own. Fail-open
    # by contract: this block may never raise and never touch stdout - the
    # hook's stdout stays the single JSON line below, byte-identical whether
    # the launch works, dedupes, or crashes at import (GATE B item 5).
    import os, re, subprocess
    _root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if _root and not os.path.exists(_root):
        _m = re.match(r"^/([A-Za-z])/(.*)$", _root)  # MSYS /c/... -> c:/... (L-003)
        if _m and os.path.exists(_m.group(1) + ":/" + _m.group(2)):
            _root = _m.group(1) + ":/" + _m.group(2)
    _daemon = os.path.join(_root, ".agents", "bin", "dashboard_daemon.py")
    if _root and os.path.exists(_daemon):
        _kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if _flags:
            _kw["creationflags"] = _flags
        else:
            _kw["start_new_session"] = True
        subprocess.Popen([sys.executable, _daemon, "--daemon", "--root", _root], **_kw)
except Exception:
    pass
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[AUTO-INJECTED INDEX — do not re-read these files]\\n" + sys.argv[1]}}))
PYEOF
exit 0
'''


def _posix(path: Path) -> str:
    """Forward-slash form so the path can be embedded as a plain (non-raw)
    Python string literal inside a generated heredoc without backslash
    escaping headaches."""
    return str(path).replace("\\", "/")


def _base_env() -> dict:
    return dict(os.environ)


def build_hook_fixture(project_dir: Path, daemon_launch_pycode: str) -> Path:
    """A COPY of the real session-start.sh with `daemon_launch_pycode`
    (arbitrary python source, already correctly indented at column 0) spliced
    into the closing heredoc, right before the JSON print. Never touches the
    real file."""
    real = SESSION_START_SH.read_text(encoding="utf-8")
    assert HEREDOC_ORIGINAL in real, "session-start.sh's closing heredoc shape changed — update this fixture"
    new_heredoc = (
        '"$PY" - "$CTX" << \'PYEOF\'\n'
        'import json, sys, subprocess\n'
        f'{daemon_launch_pycode}\n'
        'print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[AUTO-INJECTED INDEX — do not re-read these files]\\n" + sys.argv[1]}}))\n'
        "PYEOF\n"
        "exit 0\n"
    )
    fixture = real.replace(HEREDOC_ORIGINAL, new_heredoc)
    hook_path = project_dir / "session-start-fixture.sh"
    hook_path.write_text(fixture, encoding="utf-8")
    # Minimal non-empty CTX source so the hook reaches the heredoc at all
    # (board/ledger blocks stay absent -> skipped, matching the real guards).
    index_dir = project_dir / ".agents" / "state" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "CODEBASE_INDEX.md").write_text("probe fixture index\n", encoding="utf-8")
    return hook_path


DAEMON_STUB_SRC = textwrap.dedent(
    """
    # Long-lived stand-in for the dashboard daemon: writes a heartbeat every
    # 0.2s until its bounded lifetime elapses, so a test can tell "still
    # running" from "dead leftover file" by re-reading it after a pause.
    import sys, time, pathlib
    heartbeat = pathlib.Path(sys.argv[1])
    deadline = time.time() + float(sys.argv[2])
    while time.time() < deadline:
        heartbeat.write_text(repr(time.time()), encoding="utf-8")
        time.sleep(0.2)
    """
).strip()

DAEMON_STUB_CRASH_SRC = "raise ImportError('simulated crash at import — GATE B item 5')\n"


def write_daemon_stub(tmp_dir: Path, crash: bool = False) -> Path:
    name = "daemon_stub_crash.py" if crash else "daemon_stub.py"
    path = tmp_dir / name
    path.write_text(DAEMON_STUB_CRASH_SRC if crash else DAEMON_STUB_SRC, encoding="utf-8")
    return path


def kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass


# Spawn-flag combinations under test. Each maps to the literal `kwargs = ...`
# line spliced into the daemon-launch python. `A` (bare inherit) is the
# deliberate negative control: it must reproduce the hang, or the harness
# itself is not adversarial.
COMBOS = {
    "A_inherit_baseline": "kwargs = dict()",
    "B_devnull_only": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL)"
    ),
    "C_devnull_close_fds": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, close_fds=True)"
    ),
    "D_devnull_detached_process": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, creationflags=subprocess.DETACHED_PROCESS)"
    ),
    "E_devnull_new_process_group": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)"
    ),
    "F_devnull_detached_and_group": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, creationflags=subprocess.DETACHED_PROCESS | "
        "subprocess.CREATE_NEW_PROCESS_GROUP)"
    ),
    "G_devnull_start_new_session": (
        "kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, start_new_session=True)"
    ),
    "H_inherit_detached_process_only": (
        # stdio NOT redirected, only the Windows creationflag set - isolates
        # whether DETACHED_PROCESS alone (without DEVNULL) is enough.
        "kwargs = dict(creationflags=subprocess.DETACHED_PROCESS)"
    ),
}

# --- Two RELATIVE budgets, calibrated PER ATTEMPT (T-00000172, T-00000242) ---
# The wall-clock a hook is allowed is NOT a fixed budget. On a shared/loaded
# machine bash+python cold start alone can exceed a small absolute ceiling, so
# the old 2.0s constant measured the LOAD, not a hang (T-00000172). But a SINGLE
# per-run baseline taken in setUp misses the sub-second bursts that arrive DURING
# the shot, so the reference is now re-measured on EVERY attempt of _run_combo
# (T-00000242) and the shot is retried a bounded number of times: only a
# DETERMINISTIC defect survives all three attempts.
#
# Two SEPARATE budgets, no longer derived from one number:
#   promptitude = max(PROMPT_FLOOR, PROMPT_K * baseline)               -- did the hook return fast?
#   hang cutoff = min(CEILING, max(HARNESS_TIMEOUT_FLOOR, K*baseline)) -- did it hold the pipe?
# The old code judged promptitude against `hang_cutoff * 0.75`, which tied the two
# together and RETURNED the "we never tighten" guarantee: the effective promptitude
# threshold (1.5s on a calm box: 2.0 floor * 0.75) was TIGHTER than the historical
# absolute 2.0s budget, so a 1.85s hook that passed the absolute budget failed here
# (the T-00000242 counter-example). The `* 0.75` is gone; promptitude has its OWN
# floor of exactly 2.0s (the historical absolute), so on a calm box it is neither
# tighter nor looser than the budget it should never have stopped being.
#
# Recompute, promptitude max(2, 10b) vs hang min(12, max(4, 20b)):
#   b <= 0.2s        -> prompt 2.0s     hang 4.0s     strict separation
#   0.2 < b <= 0.6s  -> prompt 10b      hang 20b      strict (half)
#   0.6 < b < 1.2s   -> prompt 10b (<12) hang 12 cap  strict
#   b >= 1.2s        -> prompt >= 12    hang 12       SUBSUMED
# Promptitude is STRICTLY below the hang cutoff everywhere under b = 1.2s. The
# subsumption is pushed out to b >= 1.2s — a genuinely extreme regime, no longer
# the nominal one it was under the earlier (retracted) K=20 / equal-floors tuning
# that made the two budgets identical for b <= 0.6s. In that extreme tail only the
# NON-hang half keeps meaning; promptitude collapses into it, and that is NAMED
# here rather than hidden.
#
# Raising HARNESS_TIMEOUT_FLOOR from 2.0 to 4.0 WIDENS the SINGLE hang budget only —
# the one direction the doctrine allows — and it is what OPENS the 2-4s window where
# promptitude measures something the timeout never will: a hook that regressed
# deterministically to ~3s returns under the 4.0s hang cutoff (never times out) yet
# fails promptitude 3/3 (3 > 2.0). A stray wait/join/sleep in a launcher is exactly
# that class. Widening the hang budget also makes the "we never tighten" claim TRUE
# on the hang side (>= FLOOR always), which the `* 0.75` had made false.
#
# Why calibration still cannot mask a real hang: a healthy hook returns in one cold
# start (a few x baseline), while a hung hook holds the host's captured stdout pipe
# for the WHOLE DAEMON_LIFETIME (45s) — the detached grandchild inherited it and
# capture_output's read never unblocks. CEILING (12s) is pinned FAR below 45s, so a
# genuine hang trips the timeout long before the daemon dies. Distinguish the
# classification DELAY (<= CEILING 12s) from the WALL-CLOCK of a hung attempt
# (~45s: subprocess.run kills the hook then communicate() drains the pipe the
# grandchild holds for DAEMON_LIFETIME — CPython Windows behaviour, MEASURED by the
# chronometry of test_A below, not assumed).
PROMPT_FLOOR = 2.0                 # promptitude budget floor = the historical absolute budget
PROMPT_K = 10.0                    # half the hang K: keeps promptitude < hang under b < 1.2s
HARNESS_TIMEOUT_FLOOR = 4.0        # hang budget floor, raised 2.0->4.0 to open the 2-4s window
HARNESS_TIMEOUT_K = 20.0           # multiples of the measured cold-start baseline
HARNESS_TIMEOUT_CEILING = 12.0     # << DAEMON_LIFETIME (45s): a real hang still trips it
HARNESS_TIMEOUT_BASELINE_SAMPLES = 3
RETRY_ATTEMPTS = 3                 # bounded retries; only a DETERMINISTIC defect survives all 3
# The stub must outlive the survival assertion by a wide margin: a lifetime
# tuned close to the assertion's own waits turns a slow machine into a failure
# (T-00000043). Every pid started here is killed in tearDown regardless.
DAEMON_LIFETIME = 45.0


def daemon_launch_pycode(kwargs_line: str, daemon_stub: Path, heartbeat: Path, pidfile: Path) -> str:
    return (
        f"{kwargs_line}\n"
        f'_p = subprocess.Popen([sys.executable, "{_posix(daemon_stub)}", '
        f'"{_posix(heartbeat)}", "{DAEMON_LIFETIME}"], **kwargs)\n'
        f'open("{_posix(pidfile)}", "w", encoding="utf-8").write(str(_p.pid))\n'
    )


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude Code hook")
class LaunchDetachmentTests(unittest.TestCase):
    """Items 1, 2, 5."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name)
        self._pids_to_kill = []
        # No per-run baseline here any more: it is re-measured on EVERY attempt of
        # _run_combo, so the reference shares the shot's own load window (T-00000242).

    def tearDown(self):
        for pid in self._pids_to_kill:
            kill_pid(pid)
        self._tmp.cleanup()

    def _measure_cold_start_baseline(self) -> float:
        """Median wall-time of a trivial bash->python cold start, timed in THIS
        run so it reflects the CURRENT load — the same bash+python startup the
        hook itself pays before it can even reach the daemon launch. Median (not
        min) so a single scheduling stall neither inflates the estimate nor is
        fully dodged. Returns 0.0 if the probe cannot run at all, which collapses
        the timeout to FLOOR (never below the old absolute budget)."""
        samples = []
        for _ in range(HARNESS_TIMEOUT_BASELINE_SAMPLES):
            t0 = time.perf_counter()
            try:
                subprocess.run(
                    [BASH, "-c", "python -c pass"],
                    capture_output=True, text=True,
                    timeout=HARNESS_TIMEOUT_CEILING, check=False,
                )
            except (subprocess.TimeoutExpired, OSError):
                continue
            samples.append(time.perf_counter() - t0)
        if not samples:
            return 0.0
        samples.sort()
        return samples[len(samples) // 2]

    def _budgets(self, baseline: float):
        """Two INDEPENDENT budgets from one attempt's baseline (T-00000242):
        promptitude = max(PROMPT_FLOOR, PROMPT_K*baseline) — did the hook return
        fast? — and the hang cutoff = min(CEILING, max(HARNESS_TIMEOUT_FLOOR,
        HARNESS_TIMEOUT_K*baseline)) — did it hold the pipe? Strictly separated for
        baseline < 1.2s; see the HARNESS_TIMEOUT_* block for the full recompute and
        why neither can mask a real hang."""
        prompt_budget = max(PROMPT_FLOOR, PROMPT_K * baseline)
        hang_cutoff = min(
            HARNESS_TIMEOUT_CEILING,
            max(HARNESS_TIMEOUT_FLOOR, HARNESS_TIMEOUT_K * baseline),
        )
        return prompt_budget, hang_cutoff

    def _run_combo_once(self, combo_name: str, work: Path, crash_daemon: bool = False):
        """A SINGLE shot: fresh workdir, baseline re-measured in this attempt's own
        load window, both budgets derived from it, then the real hook is driven once.
        Returns the raw outcome plus the computed `prompt` verdict; retries and
        property assertions live in the callers."""
        work.mkdir(parents=True, exist_ok=True)
        daemon_stub = write_daemon_stub(work, crash=crash_daemon)
        heartbeat = work / "heartbeat.txt"
        pidfile = work / "daemon.pid"
        project_dir = work / "project"
        project_dir.mkdir()

        pycode = daemon_launch_pycode(COMBOS[combo_name], daemon_stub, heartbeat, pidfile)
        hook = build_hook_fixture(project_dir, pycode)

        # Baseline re-measured HERE (T-00000242), inside the shot's own load window,
        # so a sub-second burst arriving during the run is reflected in the budget.
        baseline = self._measure_cold_start_baseline()
        prompt_budget, hang_cutoff = self._budgets(baseline)

        env = {**_base_env(), "CLAUDE_PROJECT_DIR": str(project_dir)}
        t0 = time.perf_counter()
        timed_out = False
        result = None
        try:
            result = subprocess.run(
                [BASH, str(hook)], env=env, capture_output=True, text=True,
                timeout=hang_cutoff, check=False,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
        elapsed = time.perf_counter() - t0

        # Track the daemon pid for forced cleanup regardless of outcome
        # (L-00000050 discipline: kill everything this probe starts).
        if pidfile.exists():
            try:
                self._pids_to_kill.append(int(pidfile.read_text(encoding="utf-8").strip()))
            except (ValueError, OSError):
                pass

        prompt = (not timed_out) and elapsed <= prompt_budget
        return {
            "elapsed": elapsed,
            "timed_out": timed_out,
            "result": result,
            "heartbeat": heartbeat,
            "baseline": baseline,
            "prompt_budget": prompt_budget,
            "hang_cutoff": hang_cutoff,
            "prompt": prompt,
        }

    def _run_combo(self, combo_name: str, crash_daemon: bool = False, label: str = None):
        """Bounded RETRY around _run_combo_once (T-00000242): a winning attempt is one
        that NEITHER timed out NOR overran the promptitude budget; the FIRST such
        attempt is returned for the caller's property assertions (which are therefore
        never retried, C3). If no attempt wins in RETRY_ATTEMPTS, the whole combo is
        failed with a per-attempt breakdown naming the KIND of each red (timeout vs
        not-prompt), so a promptitude failure can never be mistaken for a hang. Each
        attempt uses a FRESH workdir and records its pid. `test_A` deliberately does
        NOT use this — it is a single shot whose timeout IS the verdict."""
        label = label or combo_name
        attempts = []
        for i in range(RETRY_ATTEMPTS):
            work = self.tmp_path / f"{label}_attempt{i}"
            r = self._run_combo_once(combo_name, work, crash_daemon=crash_daemon)
            attempts.append(r)
            ratio = (r["elapsed"] / r["baseline"]) if r["baseline"] else float("inf")
            # MESURE DU RATIO RÉEL (T-00000242): elapsed/baseline of this attempt,
            # printed for every attempt so the chosen K=10 can be checked against the
            # observed healthy-hook ratio under real load.
            print(
                f"\n[T-00000242 ratio] {label} attempt {i}: elapsed={r['elapsed']:.4f}s "
                f"baseline={r['baseline']:.4f}s ratio={ratio:.2f} "
                f"prompt_budget={r['prompt_budget']:.2f}s hang_cutoff={r['hang_cutoff']:.2f}s "
                f"timed_out={r['timed_out']} prompt={r['prompt']}"
            )
            if not r["timed_out"] and r["prompt"]:
                return r
        lines = []
        for i, r in enumerate(attempts):
            kind = "TIMEOUT" if r["timed_out"] else "NOT-PROMPT"
            lines.append(
                f"  attempt {i}: {kind} elapsed={r['elapsed']:.4f}s "
                f"baseline={r['baseline']:.4f}s prompt_budget={r['prompt_budget']:.2f}s "
                f"hang_cutoff={r['hang_cutoff']:.2f}s"
            )
        self.fail(
            f"combo {label} failed all {RETRY_ATTEMPTS} attempts — no attempt both "
            f"returned within the hang cutoff AND met the promptitude budget:\n"
            + "\n".join(lines)
        )

    def _assert_single_json_object(self, stdout: str):
        # json.loads on the WHOLE string raises "Extra data" if anything
        # trailing (a stray line from a launcher) follows a first valid value
        # - this IS the "exactly one JSON object" contract check.
        payload = json.loads(stdout)
        self.assertIsInstance(payload, dict)
        self.assertIn("hookSpecificOutput", payload)
        return payload

    def _assert_daemon_alive_after_return(self, heartbeat: Path):
        # Process-creation latency (python.exe cold start on Windows) is
        # separate from the hazard under test (whether the harness call itself
        # returns promptly, asserted elsewhere by `elapsed`), so this waits
        # GENEROUSLY and polls for PROGRESS instead of sleeping a fixed amount.
        #
        # The earlier version waited 3s for the first heartbeat then slept
        # exactly 1s and required movement. Under full-suite load that measured
        # cold-start latency, not survival: it failed intermittently while the
        # child was perfectly alive (T-00000043). A property assertion must not
        # double as a performance budget — the stub's own lifetime is the only
        # real deadline here, and teardown kills it either way.
        deadline = time.time() + 20.0
        while not heartbeat.exists() and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(heartbeat.exists(),
                        "daemon never wrote its first heartbeat (waited 20s)")
        first = heartbeat.read_text(encoding="utf-8")
        progressed = False
        deadline = time.time() + 10.0
        while time.time() < deadline:
            time.sleep(0.1)
            if heartbeat.read_text(encoding="utf-8") != first:
                progressed = True
                break
        self.assertTrue(progressed,
                        "heartbeat did not advance in 10s — daemon is not actually still running")

    def test_A_inherit_baseline_reproduces_the_hang(self):
        """Negative control: proves the harness itself is adversarial. If this does
        NOT time out, the fixture is not exercising the real hazard and every other
        result in this class is meaningless. SINGLE shot (never retried): the timeout
        IS the expected verdict. Its wall-clock is also the MEASUREMENT of the
        post-kill pipe drain (~DAEMON_LIFETIME on Windows), printed here rather than
        assumed (T-00000242 / C4)."""
        work = self.tmp_path / "A_inherit_baseline"
        t0 = time.perf_counter()
        r = self._run_combo_once("A_inherit_baseline", work)
        wall = time.perf_counter() - t0
        print(
            f"\n[T-00000242 wall-clock] test_A single hung shot: "
            f"elapsed(subprocess.run)={r['elapsed']:.2f}s total_wall={wall:.2f}s "
            f"hang_cutoff={r['hang_cutoff']:.2f}s "
            f"(post-kill drain ~ elapsed - hang_cutoff)"
        )
        self.assertTrue(
            r["timed_out"],
            "baseline (inherited stdio) did not hang the harness — the probe is not "
            "reproducing the real hazard; results for other combos cannot be trusted "
            "until this negative control fails as expected",
        )

    def test_B_devnull_only_returns_promptly_and_child_survives(self):
        # Promptitude and non-hang are now enforced INSIDE _run_combo's retry: a
        # returned winner is, by construction, prompt and not timed out (the `* 0.75`
        # coupling is gone). Only the PROPERTY assertions remain here, and they run on
        # the winning attempt WITHOUT retry (C3): exactly one JSON object, empty
        # stderr, daemon still alive after the hook returned.
        r = self._run_combo("B_devnull_only")
        self._assert_single_json_object(r["result"].stdout)
        self.assertEqual(r["result"].stderr, "")
        self._assert_daemon_alive_after_return(r["heartbeat"])

    def test_C_devnull_close_fds_returns_promptly_and_child_survives(self):
        r = self._run_combo("C_devnull_close_fds")
        self.assertFalse(r["timed_out"], f"combo C hung the harness (elapsed={r['elapsed']:.2f}s)")
        self._assert_single_json_object(r["result"].stdout)
        self._assert_daemon_alive_after_return(r["heartbeat"])

    @unittest.skipUnless(WINDOWS, "subprocess.DETACHED_PROCESS / "
                         "CREATE_NEW_PROCESS_GROUP are Windows-only creationflags")
    def test_D_devnull_detached_process(self):
        r = self._run_combo("D_devnull_detached_process")
        self.assertFalse(r["timed_out"], f"combo D hung the harness (elapsed={r['elapsed']:.2f}s)")
        self._assert_single_json_object(r["result"].stdout)
        self._assert_daemon_alive_after_return(r["heartbeat"])

    @unittest.skipUnless(WINDOWS, "subprocess.DETACHED_PROCESS / "
                         "CREATE_NEW_PROCESS_GROUP are Windows-only creationflags")
    def test_E_devnull_new_process_group(self):
        r = self._run_combo("E_devnull_new_process_group")
        self.assertFalse(r["timed_out"], f"combo E hung the harness (elapsed={r['elapsed']:.2f}s)")
        self._assert_single_json_object(r["result"].stdout)
        self._assert_daemon_alive_after_return(r["heartbeat"])

    @unittest.skipUnless(WINDOWS, "subprocess.DETACHED_PROCESS / "
                         "CREATE_NEW_PROCESS_GROUP are Windows-only creationflags")
    def test_F_devnull_detached_and_group(self):
        r = self._run_combo("F_devnull_detached_and_group")
        self.assertFalse(r["timed_out"], f"combo F hung the harness (elapsed={r['elapsed']:.2f}s)")
        self._assert_single_json_object(r["result"].stdout)
        self._assert_daemon_alive_after_return(r["heartbeat"])

    def test_G_devnull_start_new_session(self):
        # start_new_session (setsid) is documented POSIX-only; report what
        # actually happens on this platform rather than assuming.
        r = self._run_combo("G_devnull_start_new_session")
        if r["timed_out"]:
            self.fail("combo G hung the harness")
        payload_stdout = r["result"].stdout
        try:
            self._assert_single_json_object(payload_stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"combo G corrupted the hook's stdout contract: stdout={payload_stdout!r} stderr={r['result'].stderr!r} ({exc})"
            )
        self._assert_daemon_alive_after_return(r["heartbeat"])

    def test_H_inherit_detached_process_only_without_devnull(self):
        """Isolates whether DETACHED_PROCESS alone, without explicit stdio
        redirection, is sufficient. Exploratory: reported either way, not
        asserted, because both outcomes are informative data points for
        shard 2 and forcing a direction here would be tuning, not measuring."""
        r = self._run_combo("H_inherit_detached_process_only")
        stdout_ok = None
        if not r["timed_out"] and r["result"] is not None:
            try:
                json.loads(r["result"].stdout)
                stdout_ok = True
            except json.JSONDecodeError:
                stdout_ok = False
        # Same process-creation-latency poll as the assertive combos, so a
        # slow python.exe cold start isn't misreported as "never started".
        deadline = time.time() + 3.0
        while not r["heartbeat"].exists() and time.time() < deadline:
            time.sleep(0.1)
        alive_after = False
        if r["heartbeat"].exists():
            first = r["heartbeat"].read_text(encoding="utf-8")
            time.sleep(1.0)
            alive_after = r["heartbeat"].exists() and r["heartbeat"].read_text(encoding="utf-8") != first
        print(
            f"\n[GATE B item 1, combo H] creationflags=DETACHED_PROCESS alone, stdio "
            f"NOT redirected: timed_out={r['timed_out']} elapsed={r['elapsed']:.2f}s "
            f"stdout_single_json={stdout_ok} heartbeat_written={r['heartbeat'].exists()} "
            f"still_alive_after_1s={alive_after}"
        )

    def test_item5_fail_open_on_child_crash_at_import(self):
        """A child that crashes at import must leave the hook's exit code and stdout
        byte-identical to the non-crashing case, using the same winning combo (B) for
        both arms. Both arms now go through the shared retry runner (T-00000242): the
        crash arm inherits the per-attempt budget and bounded retry, so a
        TimeoutExpired becomes a NAMED failure instead of a NoneType crash. The
        equalities and the heartbeat-absence net are unchanged (C2)."""
        clean = self._run_combo("B_devnull_only")
        # Crash arm: SAME combo B, crashing daemon target, its own workdir label.
        crashed_r = self._run_combo("B_devnull_only", crash_daemon=True, label="item5_crash")
        crashed = crashed_r["result"]

        self.assertEqual(crashed.returncode, clean["result"].returncode, "exit code changed when child crashed at import")
        self.assertEqual(crashed.returncode, 0)
        self.assertEqual(
            crashed.stdout, clean["result"].stdout,
            "hook stdout changed when the launched child crashed at import — fail-open is broken",
        )
        self._assert_single_json_object(crashed.stdout)
        # And the crash really happened, on its own, without touching the parent —
        # evaluated on the WINNING attempt's workdir (C2). The crashing stub must
        # never have written a heartbeat there.
        time.sleep(0.3)
        self.assertFalse(crashed_r["heartbeat"].exists(), "crashing stub should never have written a heartbeat")


# ---------------------------------------------------------------------------
# Item 3: O_CREAT|O_EXCL lock race across real OS processes.
# ---------------------------------------------------------------------------

WINNER_LOSER_SRC = textwrap.dedent(
    """
    import os, sys
    lockpath, outpath = sys.argv[1], sys.argv[2]
    try:
        fd = os.open(lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"locked")
        os.close(fd)
        open(outpath, "w", encoding="utf-8").write("WIN")
    except FileExistsError:
        open(outpath, "w", encoding="utf-8").write("LOSE")
    """
).strip()


class LockRaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_exactly_one_winner_across_concurrent_processes(self):
        n = 10
        racer = self.tmp_path / "racer.py"
        racer.write_text(WINNER_LOSER_SRC, encoding="utf-8")
        lockpath = self.tmp_path / "dashboard.lock"
        procs = []
        outs = []
        # Launch all N back-to-back, unwaited, to maximise overlap before
        # any of them reaches the os.open() call.
        for i in range(n):
            out = self.tmp_path / f"out_{i}.txt"
            outs.append(out)
            procs.append(subprocess.Popen([sys.executable, str(racer), str(lockpath), str(out)]))
        for p in procs:
            p.wait(timeout=10)
        results = [out.read_text(encoding="utf-8") for out in outs]
        wins = results.count("WIN")
        losses = results.count("LOSE")
        self.assertEqual(wins, 1, f"expected exactly 1 winner across {n} processes, got results={results}")
        self.assertEqual(losses, n - 1)
        self.assertTrue(lockpath.exists())


# ---------------------------------------------------------------------------
# Item 4: stale-lock recovery — pid probe alone is insufficient, tokenised
# HTTP ping distinguishes, atomic reclaim via mkstemp -> write -> fsync ->
# os.replace (fd closed before replace).
# ---------------------------------------------------------------------------

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def pid_alive(pid: int) -> bool:
    """Windows pid-liveness probe via ctypes (stdlib) — the naive half of
    the liveness check this item proves is insufficient on its own."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return bool(ok) and exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TokenPingServer(HTTPServer):
    # L-00000050: never inherit http.server's allow_reuse_address=True on
    # Windows — it permits a second live listener on the same port.
    allow_reuse_address = False


def make_ping_handler(expected_token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            token = self.headers.get("X-Gateb-Token", "")
            body = b"ALIVE" if token == expected_token else b"NOT-OURS"
            code = 200 if token == expected_token else 403
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def ping(port: int, token: str, timeout: float = 1.0) -> bool:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/ping", headers={"X-Gateb-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200 and resp.read() == b"ALIVE"
    except (urllib.error.URLError, ConnectionError, OSError):
        return False


class StaleLockRecoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name)
        self._servers = []
        self._helper_procs = []

    def tearDown(self):
        for srv in self._servers:
            srv.shutdown()
            srv.server_close()
        for p in self._helper_procs:
            p.kill()
            p.wait(timeout=5)
        self._tmp.cleanup()

    def _spawn_unrelated_sleeper(self) -> int:
        """A REAL, live, unrelated process — stands in for 'this pid got
        reused by something else' without needing true OS pid recycling
        (which cannot be forced deterministically in a test)."""
        script = self.tmp_path / "sleeper.py"
        script.write_text("import time; time.sleep(30)\n", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(script)])
        self._helper_procs.append(proc)
        return proc.pid

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_pid_alone_is_insufficient_but_token_ping_distinguishes(self):
        unrelated_pid = self._spawn_unrelated_sleeper()
        self.assertTrue(pid_alive(unrelated_pid), "sanity: helper process should be alive")

        # A lock file naming this unrelated, but genuinely live, pid — this
        # is exactly what pid reuse would produce: the pid slot is occupied
        # by something, just not our daemon.
        real_token = "correct-token-abc"
        port = free_port()
        lock = {"pid": unrelated_pid, "port": port, "token": real_token}
        lockfile = self.tmp_path / "dashboard.lock"
        lockfile.write_text(json.dumps(lock), encoding="utf-8")

        # (a) pid-alone liveness says ALIVE — false positive, by construction.
        self.assertTrue(pid_alive(lock["pid"]), "pid-alone check must (wrongly) say alive here")

        # (b) nothing is actually serving our token at that port — ping says NOT ours.
        self.assertFalse(ping(port, real_token), "no server listening: ping must report not-ours/stale")

        # (c) even if some OTHER http server happens to occupy the port
        # (again: what a reused port would produce), a WRONG token still
        # correctly reports not-ours.
        #
        # The imposter gets its OWN allocated port, retried until it actually
        # binds. The first version bound `port + 1`, assuming the neighbour of
        # a free port is free too — it is not, under any concurrent load that
        # consumes ephemeral ports (this suite's own servers, a running
        # dashboard daemon), and that assumption made this test fail once in
        # six full-suite runs. A port allocation is a race by nature; the fix
        # is to bind-then-check rather than to predict.
        imposter_token = "some-other-daemon-token"
        srv = None
        for _ in range(20):
            candidate = free_port()
            if candidate == port:
                continue  # (b) above needs `port` to stay unoccupied
            try:
                srv = _TokenPingServer(("127.0.0.1", candidate),
                                      make_ping_handler(imposter_token))
                imposter_port = candidate
                break
            except OSError:
                continue  # taken between the probe and the bind — try another
        self.assertIsNotNone(srv, "could not bind an imposter listener on any free port")
        self._servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.assertFalse(
            ping(imposter_port, real_token),
            "an imposter listener on the port must not be accepted as our daemon",
        )
        self.assertTrue(
            ping(imposter_port, imposter_token),
            "sanity: the imposter server itself answers its own correct token",
        )

    def _stage_and_write(self, i: int) -> str:
        fd, tmp = tempfile.mkstemp(dir=str(self.tmp_path), prefix="._tmp_", suffix=".part")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": 222 + i, "port": 2, "token": f"new-{i}"}))
            fh.flush()
            os.fsync(fh.fileno())
        # fd is closed here (the `with` block exited) BEFORE os.replace.
        return tmp

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_atomic_reclaim_without_retry_hits_sharing_violations_on_windows(self):
        """Documents an unplanned finding: even with the fd correctly closed
        before `os.replace` (the documented recipe), a concurrent READER
        merely holding the target open for `open()+read()` makes Windows
        raise PermissionError/WinError-5 on `os.replace` at high frequency.
        This is a NEGATIVE CONTROL for the next test - if replace never
        failed here, bounded retry (below) would be untested dead code."""
        target = self.tmp_path / "dashboard.lock"
        target.write_text(json.dumps({"pid": 111, "port": 1, "token": "old"}), encoding="utf-8")

        stop = threading.Event()
        bad_reads = []
        read_attempts = [0]

        def hammer():
            while not stop.is_set():
                read_attempts[0] += 1
                try:
                    raw = target.read_text(encoding="utf-8")
                    if raw:
                        json.loads(raw)  # must NEVER see a truncated/partial write
                except json.JSONDecodeError as exc:
                    bad_reads.append(("torn-content", repr(exc)))
                except OSError:
                    pass  # a transient sharing violation on the READ side is not torn content

        reader = threading.Thread(target=hammer)
        reader.start()
        replace_errors = []
        try:
            for i in range(100):
                tmp = self._stage_and_write(i)
                try:
                    os.replace(tmp, str(target))
                except OSError as exc:
                    replace_errors.append(repr(exc))
                    with contextlib.suppress(OSError):
                        os.unlink(tmp)
        finally:
            stop.set()
            reader.join(timeout=5)

        self.assertEqual(bad_reads, [], f"reader observed TORN content (never acceptable): {bad_reads}")
        print(
            f"\n[GATE B item 4] without retry: {len(replace_errors)}/100 os.replace() calls hit a "
            f"sharing violation under a concurrent reader ({read_attempts[0]} read attempts). "
            f"Sample: {replace_errors[:3]}"
        )
        self.assertGreater(
            len(replace_errors), 0,
            "expected at least some sharing violations under contention on Windows - if none occurred, "
            "the retry wrapper tested next is untested dead code and this negative control is invalid",
        )

    def test_atomic_reclaim_with_bounded_retry_never_tears_and_always_converges(self):
        """The recipe shard 2 must actually ship: same mkstemp/write/fsync/
        close/replace staging, wrapped in a bounded retry-with-backoff on
        PermissionError, because the previous test proves a bare os.replace
        is not reliable under concurrent readers on Windows. Property under
        test: readers NEVER see torn/partial content, and every reclaim
        eventually converges (no permanent failure)."""

        def replace_with_retry(tmp: str, target: str, attempts: int = 30, delay: float = 0.01) -> int:
            last = None
            for attempt in range(attempts):
                try:
                    os.replace(tmp, target)
                    return attempt
                except PermissionError as exc:
                    last = exc
                    time.sleep(delay)
            raise last

        target = self.tmp_path / "dashboard.lock"
        target.write_text(json.dumps({"pid": 111, "port": 1, "token": "old"}), encoding="utf-8")

        stop = threading.Event()
        bad_reads = []

        def hammer():
            while not stop.is_set():
                try:
                    raw = target.read_text(encoding="utf-8")
                    if raw:
                        json.loads(raw)
                except json.JSONDecodeError as exc:
                    bad_reads.append(("torn-content", repr(exc)))
                except OSError:
                    pass

        reader = threading.Thread(target=hammer)
        reader.start()
        retries_needed = []
        try:
            for i in range(50):
                tmp = self._stage_and_write(i)
                retries_needed.append(replace_with_retry(tmp, str(target)))
        finally:
            stop.set()
            reader.join(timeout=5)

        self.assertEqual(bad_reads, [], f"reader observed a torn/partial write during replace: {bad_reads}")
        final = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(final["port"], 2)
        print(f"\n[GATE B item 4] with bounded retry: max retries needed across 50 reclaims = {max(retries_needed)}")

    @unittest.skipUnless(WINDOWS, WINDOWS_ONLY)
    def test_replace_without_closing_fd_first_fails_on_windows(self):
        """Empirically justifies the 'fd closed before replace' clause of the
        recipe: proves it is load-bearing on this platform, not decorative."""
        target = self.tmp_path / "dashboard.lock"
        target.write_text("original", encoding="utf-8")
        fd, tmp = tempfile.mkstemp(dir=str(self.tmp_path), prefix="._tmp_", suffix=".part")
        try:
            os.write(fd, b"new content")
            os.fsync(fd)
            # fd is DELIBERATELY still open here — replace before close.
            with self.assertRaises(OSError) as ctx:
                os.replace(tmp, str(target))
            self.assertIn(
                ctx.exception.winerror if hasattr(ctx.exception, "winerror") else None,
                (32, None),
            )
        finally:
            os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
