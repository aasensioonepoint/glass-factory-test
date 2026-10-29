"""The Claude event emitters and the SubagentStop/Stop hooks listed here write no `.pyc` (T-00001191).

This bench IS the list the docs-only route points at ("listed in
test_event_emitters_bytecode_1191.py"). It is a list of what is MEASURED, never a
claim that nothing else writes one: a bare `python3`, the documenter's pytest and a
child run under `-E`/`-I` stay named residues (docs_only_scope.py (i)).

emit-event.sh, agent-events.sh, mcp-events.sh and log-agent-usage.sh load
events.py — and, through it, the cadre package's ledger/redaction.py (src/cadre
or .agents/vendor/cadre) — BY PATH, from
Python fed on stdin. Without `-B` that load caches both modules: measured on the
docs-only window replay (T-00001191 plan, M3), agent-events.sh writes them on
every documenter call and the docs-only check prints them OUT, a fail-closed
false red. log-agent-usage.sh (SubagentStop, same window) was the fourth,
measured by the plan critic (S-00004348, finding C1).

The closing pair's correction pass (batch 2) added two Stop hooks, measured at a
cold cache: run-recap.sh (tasks.py, events.py, redaction.py by path) and
stop-reindex.sh (build_index.py, migrate_index_to_db.py, src/cadre/paths.py). A
Stop hook CAN fire inside the window when the documenter runs in the background
(inferred from the hook model, not replayed here; the T-00001191 plan had Stop
outside the window).
Each one is played twice: the shipped hook (no cache) and a MUTANT copy with the
fix removed (a cache), so the leg is proven able to go red, every run.
statusline.sh (tasks.py, every 5 s) is held by a text pin (the launcher of the
local dev route had one too; it left with that route). binome-trace.sh and affirmation-guard.sh
were REFUTED (0 `.pyc` measured, critic payload included: `tasks.py list` execs
its parts from compiled bytes, the guard imports the stdlib only) — no leg, since
no mutant of theirs could go red. They carry `-B` anyway, held by text pins
(PreventiveLaunchersPinsTests, closing pair's correction pass ter, S-00004359).

The witness reuses the canal-A fixture of test_events_parity.py BY IMPORT
(build_fixture, hook_env, run_claude_hook, records) and never modifies that
file. The cache directories are EXPLICIT paths, never a tree walk
(test_repo_walk_census.py classifies every walk). Each emitter must also leave
its record in the redirected events dir: that is the proof events.py really
loaded, without which "no cache" would be vacuous.
"""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_events_parity import (  # noqa: E402 — needs the path inserted above
    BASH,
    build_fixture,
    hook_env,
    records,
    run_claude_hook,
)

ROOT = Path(__file__).resolve().parents[2]
# The resolver loaded BY PATH (v3prep pattern), never through sys.path: the cadre
# package lives at .agents/vendor/cadre or src/cadre (T-01M5BXTPQE3JZV3KZA6WD9P5XC).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_bytecode_1191_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
# A host value of either variable would make the witness vacuous.
BYTECODE_VARS = ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")
# Both package locations in the fixture: a cache is looked for wherever the loader reads.
CADRE_LOCATIONS = (Path("src") / "cadre", Path(".agents") / "vendor" / "cadre")
BIN_CACHE = Path(".agents") / "bin" / "__pycache__"
LEDGER_CACHES = tuple(lieu / "ledger" / "__pycache__" for lieu in CADRE_LOCATIONS)
CADRE_CACHES = tuple(lieu / "__pycache__" for lieu in CADRE_LOCATIONS)
CACHE_DIRS = (BIN_CACHE, *LEDGER_CACHES, *CADRE_CACHES)
EXPORT_LINE = "export PYTHONDONTWRITEBYTECODE=1"
# What the two Stop hooks load from the project root, copied LOCALLY into the
# fixture (build_fixture ships none of it); tasks.py's parts are added from its AST.
# (fixture path, kit source): paths.py goes where the fixture's migrate_index_to_db.py
# falls back without a package (src/cadre), read from the kit's RESOLVED package.
STOP_HOOK_FILES = (
    (Path(".agents") / "bin" / "build_index.py", ROOT / ".agents" / "bin" / "build_index.py"),
    (Path(".agents") / "bin" / "migrate_index_to_db.py", ROOT / ".agents" / "bin" / "migrate_index_to_db.py"),
    (Path(".agents") / "bin" / "tasks.py", ROOT / ".agents" / "bin" / "tasks.py"),
    (Path("src") / "cadre" / "paths.py", _VENDOR.exiger(ROOT, "cadre") / "paths.py"),
)
RUN_LOG = (
    "# Run log\n| agent | est | actual | note |\n|-------|-----|--------|------|\n"
    "| dev-multi | ~5k |  |  |\n"
)
SONDE = Path(".agents") / "state" / "local" / "stop-reindex" / "sonde"


def tasks_parts() -> tuple:
    """`PARTIES` of tasks.py, read from its AST: the fixture copies the exact set it execs."""
    tree = ast.parse((ROOT / ".agents" / "bin" / "tasks.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PARTIES" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("tasks.py: no PARTIES tuple — the fixture cannot load the board")


def without_fix(text: str) -> str:
    """The hook as it was before T-00001191: no export line, no `-B` on the launch.
    LF only: `.gitattributes` pins `*.sh text eol=lf`, so the `+ "\\n"` anchor holds on every checkout."""
    return text.replace(EXPORT_LINE + "\n", "").replace('"$PY" -B ', '"$PY" ')


@unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude emitters")
class EventEmittersBytecodeTests(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors: same Windows teardown noise as the parity bench (L-00000035).
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.fixture = build_fixture(self.tmp / "project")

    def tearDown(self):
        self._tmp.cleanup()

    def _clear_caches(self):
        # Explicit paths, cleared per leg: a cache is attributed to ITS emitter.
        for relative in CACHE_DIRS:
            shutil.rmtree(self.fixture / relative, ignore_errors=True)

    def _emit_event(self, events_dir: Path):
        """The fixture's OWN copy of emit-event.sh (build_fixture copies it), with a
        kind the parity bench already drives (session-start.sh emits it this way)."""
        return subprocess.run(
            [BASH, str(self.fixture / ".claude" / "hooks" / "emit-event.sh"), "session.start"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            cwd=str(self.fixture),
            env=hook_env(events_dir, project_dir=self.fixture),
            timeout=60,
        )

    def _agent_events(self, events_dir: Path):
        payload = {"hook_event_name": "SubagentStart", "session_id": "s1",
                   "agent_id": "a1", "agent_type": "documenter"}
        return run_claude_hook(self.fixture, "agent-events.sh", payload, events_dir)

    def _mcp_events(self, events_dir: Path):
        payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "mcp__x__y"}
        return run_claude_hook(self.fixture, "mcp-events.sh", payload, events_dir)

    def _log_agent_usage(self, events_dir: Path):
        """SubagentStop: the parity bench's own log_agent_usage payload, with the
        Claude transcript build_fixture copies (claude-transcript.jsonl)."""
        payload = {"hook_event_name": "SubagentStop", "agent_type": "dev-multi", "session_id": "s1",
                   "agent_id": "a1", "transcript_path": str(self.fixture / "claude-transcript.jsonl"),
                   "last_assistant_message": "done"}
        return run_claude_hook(self.fixture, "log-agent-usage.sh", payload, events_dir)

    def test_event_emitters_write_no_bytecode_1191(self):
        legs = (
            ("emit-event.sh", "session.start", self._emit_event),
            ("agent-events.sh", "agent.start", self._agent_events),
            ("mcp-events.sh", "scan.mcp_call", self._mcp_events),
            ("log-agent-usage.sh", "agent.stop", self._log_agent_usage),
        )
        for script, kind, run in legs:
            with self.subTest(emitter=script):
                self._clear_caches()
                events = self.tmp / "events" / script
                events.mkdir(parents=True)
                with mock.patch.dict(os.environ):
                    for name in BYTECODE_VARS:
                        os.environ.pop(name, None)
                    proc = run(events)
                self.assertEqual(proc.returncode, 0, f"{script}: {proc.stderr!r}")
                kinds = [record.get("kind") for record in records(events)]
                self.assertIn(
                    kind, kinds,
                    f"{script}: no {kind} record — events.py never loaded, the witness is vacuous",
                )
                for relative in CACHE_DIRS:
                    cache = self.fixture / relative
                    self.assertFalse(
                        cache.exists(),
                        f"{script} wrote {relative}: {sorted(p.name for p in cache.iterdir())}"
                        if cache.is_dir() else f"{script} wrote {relative}",
                    )

    # -- Stop hooks: the shipped file, then its mutant without the fix ----------

    def _extend_fixture_for_stop_hooks(self):
        """LOCAL to this bench: what run-recap.sh and stop-reindex.sh load, plus an
        empty board (run-recap loads tasks.py only when TASKS.json exists)."""
        bin_dir = Path(".agents") / "bin"
        parts = tuple((bin_dir / name, ROOT / bin_dir / name) for name in tasks_parts())
        for relative, source in (*STOP_HOOK_FILES, *parts):
            (self.fixture / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, self.fixture / relative)
        board = self.fixture / ".agents" / "state" / "board" / "TASKS.json"
        board.parent.mkdir(parents=True, exist_ok=True)
        board.write_text(json.dumps({"next_id": 1, "tasks": []}), encoding="utf-8")

    def _run_stop_hook(self, script: Path, events_dir: Path):
        """A Stop payload; CADRE_STATE_DIR redirected so build_index's DB probe never
        reads the host's machine state."""
        (self.fixture / SONDE).unlink(missing_ok=True)  # else a cache hit skips Python
        run_log = self.fixture / ".agents" / "state" / "local" / "RUN_LOG.md"
        run_log.parent.mkdir(parents=True, exist_ok=True)
        run_log.write_text(RUN_LOG, encoding="utf-8")  # run-recap clears it on every run
        env = hook_env(events_dir, project_dir=self.fixture)
        env["CADRE_STATE_DIR"] = str(self.tmp / "state")
        for name in BYTECODE_VARS:
            env.pop(name, None)
        return subprocess.run(
            [BASH, str(script)],
            input=json.dumps({"hook_event_name": "Stop", "session_id": "s1"}).encode("utf-8"),
            capture_output=True,
            cwd=str(self.fixture),
            env=env,
            timeout=120,
        )

    def test_stop_hooks_write_no_bytecode_and_their_mutants_do_1191(self):
        self._extend_fixture_for_stop_hooks()
        legs = (
            # (hook, record proving Python ran, caches its unfixed copy writes: one per group,
            # at whichever package location the loader read)
            ("run-recap.sh", "gate.forecast", ((BIN_CACHE,), LEDGER_CACHES)),
            ("stop-reindex.sh", "index.stale", ((BIN_CACHE,), CADRE_CACHES)),
        )
        for script, kind, mutant_writes in legs:
            with self.subTest(hook=script):
                if script == "stop-reindex.sh" and shutil.which("timeout") is None:
                    self.skipTest("no timeout(1) on PATH — stop-reindex.sh takes its git fallback, no Python")
                shipped = ROOT / ".claude" / "hooks" / script
                mutant = self.tmp / "mutants" / script
                for label, path in (("shipped", shipped), ("mutant", mutant)):
                    if label == "mutant":  # built AFTER the shipped leg, so a removed fix reds THERE first
                        original = shipped.read_text(encoding="utf-8")
                        mutant_text = without_fix(original)
                        self.assertTrue(mutant_text != original, f"{script}: the T-00001191 anchors are gone")
                        mutant.parent.mkdir(parents=True, exist_ok=True)
                        mutant.write_text(mutant_text, encoding="utf-8")
                    self._clear_caches()
                    events = self.tmp / "events" / f"{label}-{script}"
                    events.mkdir(parents=True)
                    proc = self._run_stop_hook(path, events)
                    self.assertEqual(proc.returncode, 0, f"{label} {script}: {proc.stderr!r}")
                    self.assertIn(kind, [r.get("kind") for r in records(events)],
                                  f"{label} {script}: no {kind} record — the leg never reached Python")
                    if script == "stop-reindex.sh":
                        self.assertTrue((self.fixture / SONDE).is_file(),
                                        f"{label} {script}: no probe verdict cached — build_index.py never ran")
                    written = [str(r) for r in CACHE_DIRS if (self.fixture / r).exists()]
                    if label == "shipped":
                        self.assertEqual(written, [], f"{script} wrote {written}")
                    else:
                        missing = [" or ".join(map(str, group)) for group in mutant_writes
                                   if not any(str(r) in written for r in group)]
                        self.assertEqual(missing, [], f"{script} unfixed wrote no {missing}: the leg is vacuous")
                self._clear_caches()


class UnexercisedLaunchersPinsTests(unittest.TestCase):
    """Text pin for the launcher this bench does not run (T-00001191)."""

    def test_statusline_exports_before_its_python_call_1191(self):
        """The env alone: `-B` would break test_context_retro_contract.py, which finds the call
        by its exact substring."""
        lines = (ROOT / ".claude" / "statusline.sh").read_text(encoding="utf-8").splitlines()
        export_at = [i for i, line in enumerate(lines) if line == EXPORT_LINE]
        launch_at = [i for i, line in enumerate(lines) if '"$PY" -c "' in line]
        self.assertEqual(len(export_at), 1, export_at)
        self.assertEqual(len(launch_at), 1, launch_at)
        self.assertLess(export_at[0], launch_at[0], "the export must precede the python call")


class PreventiveLaunchersPinsTests(unittest.TestCase):
    """Text pins for binome-trace.sh and affirmation-guard.sh: 0 `.pyc` today, `-B` for tomorrow.

    Why pins, not legs: neither hook writes a `.pyc` today, so a mutant without
    `-B` writes none either and a cache leg could never go red. affirmation-guard.sh
    imports the stdlib only. binome-trace.sh holds the property only because
    tasks.py loads its PARTIES with `compile` + `exec` (`_charger_parties`), which
    caches nothing. Its named debt (the comment above `PARTIES`, tasks.py:375-377 at
    8071d969: `check_no_inprocess_load` forbids `exec` under src/cadre/, and the
    repackaging will turn that loader into imports) would make the `tasks.py list`
    child of binome-trace cache every part on every critic stop, and no bench would
    go red. These pins hold the fix until that day (S-00004359, critic-fable T2).
    """

    def _single(self, lines, needle, hook):
        found = [line for line in lines if needle in line]
        self.assertEqual(len(found), 1, f"{hook}: {needle!r} on {len(found)} lines: {found}")
        return found[0]

    def test_binome_trace_launch_and_tasks_child_carry_dash_b_1191(self):
        """The env reaches the `tasks.py list` child (subprocess.run inherits it), and `-B`
        sits on that child's argv as well: each one alone keeps the child cache-free."""
        hook = ".claude/hooks/binome-trace.sh"
        lines = (ROOT / hook).read_text(encoding="utf-8").splitlines()
        launch = self._single(lines, "<<'PYEOF'", hook)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1 "$PY" -B - ', launch)
        child = self._single(lines, "run(sys.executable,", hook)
        self.assertIn('run(sys.executable, "-B", ', child)
        self.assertIn('"tasks.py"', child, "the pinned child is no longer the tasks.py call")

    def test_affirmation_guard_launch_carries_dash_b_1191(self):
        """No Python child in the guard: `-B` on the launch is enough."""
        hook = ".claude/hooks/affirmation-guard.sh"
        lines = (ROOT / hook).read_text(encoding="utf-8").splitlines()
        launch = self._single(lines, "<<'PYEOF'", hook)
        self.assertIn('"$PY" -B - ', launch)


if __name__ == "__main__":
    unittest.main()
