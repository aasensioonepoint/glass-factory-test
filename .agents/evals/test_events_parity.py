"""Cross-host parity for canal-A emission (T-00000027 / dashboard D5).

`events.py` is the single write path for canal A. Four hosts reach it through
three different bridges (the emitter count is MEASURED at runtime — §B of the
T-00000394 plan keeps it at four):

  claude  -> .claude/hooks/*.sh            (bash, shells out to emit-event.sh)
  codex   -> .codex/hooks/*.py             (python, _common.emit_event)
  copilot -> .codex/hooks/*.py             (THE SAME FILES — L-006)
  gemini  -> .gemini/hooks/*.py            (python, _common.emit_event)

A fifth registration, kimi, reuses the Copilot bridge (.codex/hooks/*.py via
AGENTS_HOOK_HOST=kimi). Its host LABEL is proven here — the shared file labels
host=kimi from the registration (test 4 below) — but its runtime EMISSION is
only SUPPOSED: no kimi CLI run is exercised, so the emitter count stays four
(T-00000395, residual runtime).

What this suite asserts, and nothing more:

  1. PARITY — one stimulus per surface, replayed on every host that wires that
     surface, must produce the same `kind` and the same set of `data` keys.
     Where the two hosts compute the same thing (a denied path, a command
     fingerprint, a skill ref) the VALUES must match too; where the underlying
     check genuinely differs (staleness definition, whitespace vs toolchain,
     token accounting) only the shape is asserted and the divergence is named
     in that row's comment rather than papered over. A couple listed in the
     closed SANS_ENREGISTREMENT table, with its written motive, must emit NO
     event of the row's kind — asserted, never skipped.
  2. LF STRICT (L-003) — never a CR byte in the JSONL, on any host.
  3. FAIL-OPEN DIFFERENTIAL — every wired hook run twice, once with events.py
     present and once with it deleted from the fixture: stdout, stderr and exit
     code must be BYTE-IDENTICAL. Same technique as events-wiring.test.sh
     PART 2, which proves the emit call sites are invisible to each hook's own
     contract whatever events.py's health.
  4. HOST LABEL — the shared Codex/Copilot file labels the host that is
     RUNNING, and labels NOTHING when it cannot tell (rather than defaulting to
     "codex" and blaming Codex for Copilot's denials).
  5. NEGATIVE CONTROLS — proof the comparators above can actually fail.

Style follows .agents/evals/test_ledger_parity.py (host parity, bash pinned via
shutil.which, fixture project rooted in a temp dir). Every write is redirected
through AGENTS_EVENTS_DIR: the real .agents/state/events/ is never touched, so a
test run can never inject fake denials into the dashboard's audit trail.
Fixtures use ignore_cleanup_errors=True (L-00000035: Windows teardown flake is
infrastructure noise, not a test failure).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Le paquet `cadre` est résolu par `vendor_paths` chargé PAR CHEMIN (vendor
# d'abord, puis `src/cadre`), jamais par `ROOT / "src" / "cadre"` en dur
# (décision pilote S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_events_parity_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = sys.modules[_SPEC_VENDOR.name] = importlib.util.module_from_spec(_SPEC_VENDOR)
_SPEC_VENDOR.loader.exec_module(_VENDOR)

# Les DEUX lieux où la fixture pose redaction.py, dont le lieu que lit
# events.py (`_CHEMIN_REDACTION`) : l'ancien `src` et le neuf vendor.
REDACTION_LIEUX = (
    Path("src") / "cadre" / "ledger" / "redaction.py",
    Path(".agents") / "vendor" / "cadre" / "ledger" / "redaction.py",
)


def poser_redaction(cible: Path, source: Path = ROOT) -> None:
    """Copie le `redaction.py` du paquet `cadre` résolu sous `source` aux deux
    lieux de `REDACTION_LIEUX` sous `cible` (refus nommé si le paquet manque)."""
    origine = _VENDOR.exiger(source, "cadre") / "ledger" / "redaction.py"
    for lieu in REDACTION_LIEUX:
        (cible / lieu).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origine, cible / lieu)

# On Windows a bare "bash" resolved by CreateProcess can hit the WSL relay shim
# in System32 (searched before PATH) instead of Git Bash. Pin it the same way
# test_ledger_parity.py does, so the Claude leg is honoured on both the
# ubuntu-latest runner and a Windows dev box.
BASH = shutil.which("bash")

PY_HOSTS = {"codex": ".codex", "copilot": ".codex", "gemini": ".gemini", "kimi": ".codex"}
# `iac_guard` ajouté le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : copié dans la fixture.
HOOK_MODULES = (
    "protect_paths", "safe_bash", "audit_gate", "post_edit_check",
    "stale_index", "pre_compact_backup", "session_context", "log_agent_usage", "iac_guard",
)
COMMON_FILES = ("_common.py", "safe_bash_git.py", "safe_bash_hooks.py") + tuple(f"{m}.py" for m in HOOK_MODULES)

# A distinctive fake credential, planted in the safe-bash stimulus. Its ABSENCE
# from the written record is the regression guard for L-00000043 (a hook.deny
# carried 1171 characters of live shell in a field named `path`).
FAKE_TOKEN = "sk-FAKE-TOKEN-9f8e7d6c5b4a3210"
LEAKY_COMMAND = (
    f'curl -H "Authorization: Bearer {FAKE_TOKEN}" https://example.com && rm -rf /'
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def build_fixture(root: Path) -> Path:
    """A disposable git project carrying every host's bridge at the same
    relative paths the real hooks expect, plus the state each stimulus needs.

    It is a REAL git repo because three surfaces need one: `_common.project_root`
    resolves through `git rev-parse --show-toplevel` (so the copied hooks anchor
    on the fixture, not on this checkout), post_edit_check runs
    `git diff --check`, and the Claude staleness fallback compares the worktree
    against the commit named in SYMBOLS.md.
    """
    (root / ".agents" / "bin").mkdir(parents=True)
    for sub in ("index", "gates", "local"):
        (root / ".agents" / "state" / sub).mkdir(parents=True)
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / "src").mkdir()

    shutil.copy2(ROOT / ".agents" / "bin" / "events.py", root / ".agents" / "bin" / "events.py")
    # T-00000641 : la couture d'events.py charge redaction.py PAR CHEMIN
    # (parents[2] de .agents/bin/events.py = la racine de la fixture). Sans lui, le
    # sous-processus tomberait en voie DÉGRADÉE et data deviendrait
    # {"redaction_unavailable": True} — envelope_signature divergerait. On copie le
    # SEUL redaction.py pour exercer la voie NORMALE (critère 7), aux deux lieux.
    poser_redaction(root)
    shutil.copy2(
        ROOT / ".claude" / "hooks" / "emit-event.sh", root / ".claude" / "hooks" / "emit-event.sh"
    )
    for host_dir in (".codex", ".gemini"):
        target = root / host_dir / "hooks"
        target.mkdir(parents=True)
        for name in COMMON_FILES:
            shutil.copy2(ROOT / host_dir / "hooks" / name, target / name)

    # Per-host transcripts: the two hosts compute a token total from DIFFERENT
    # shapes (Claude reads the harness's toolUseResult, Codex/Gemini sum
    # message.usage), so each leg gets the fixture its own reader understands.
    shutil.copy2(
        ROOT / ".codex" / "hooks" / "fixtures" / "transcript.jsonl", root / "codex-transcript.jsonl"
    )
    shutil.copy2(
        ROOT / ".claude" / "hooks" / "fixtures" / "subagent-transcript.jsonl",
        root / "claude-transcript.jsonl",
    )

    (root / "bad_syntax.py").write_text("def f(:\n  pass\n", encoding="utf-8")
    (root / "src" / "a.ts").write_text("export const a = 1;\n", encoding="utf-8")
    (root / "src" / "ws.txt").write_text("clean\n", encoding="utf-8")

    # Only src/ and bad_syntax.py are TRACKED; every copied bridge stays
    # untracked. Not cosmetic: with events.py tracked, a box whose git has
    # autocrlf on prints "LF will be replaced by CRLF" for it, that warning
    # lands on `git diff --check`'s stdout, and the fail-open differential then
    # compares a leg where events.py exists against one where it does not — the
    # comparator diverges on a FIXTURE artefact instead of on hook behaviour.
    # Found by this suite on the first run; keeping the bridges untracked
    # removes the artefact at the source rather than normalizing it away.
    (root / ".gitignore").write_text(
        ".agents/\n.claude/\n.codex/\n.gemini/\nsrc/cadre/\n", encoding="utf-8"
    )

    git = ["git", "-C", str(root)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["config", "user.email", "t@t"], check=True)
    subprocess.run(git + ["config", "user.name", "t"], check=True)
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(git + ["commit", "-qm", "fixture"], check=True, capture_output=True)
    sha = subprocess.run(
        git + ["rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    # index.stale stimulus, made deterministic for BOTH definitions of stale:
    # a "built @ <sha>" anchor plus a worktree change outside .agents (the Claude
    # git fallback), and an mtime strictly newer than SYMBOLS.md (the Codex/
    # Gemini mtime walk). The mtime is SET, not merely "written later" — a
    # rewrite landing inside the filesystem's timestamp granularity is exactly
    # how an mtime fixture flakes.
    symbols = root / ".agents" / "state" / "index" / "SYMBOLS.md"
    symbols.write_text(
        f"# Symbols built @ {sha}\nSYM-001 src/a.ts:1-1 a export uses[] :: c\n", encoding="utf-8"
    )
    source = root / "src" / "a.ts"
    source.write_text("export const a = 2;\n", encoding="utf-8")
    newer = symbols.stat().st_mtime + 10
    os.utime(source, (newer, newer))

    # post_edit_check stimulus: a tracked file whose unstaged diff carries a
    # trailing space, so `git diff --check` exits non-zero and names it.
    (root / "src" / "ws.txt").write_text("clean \n", encoding="utf-8")
    return root


def hook_env(events_dir: Path, hook_host=None, project_dir=None) -> dict:
    env = dict(os.environ)
    env.pop("AGENTS_HOOK_HOST", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["AGENTS_EVENTS_DIR"] = str(events_dir)
    if hook_host is not None:
        env["AGENTS_HOOK_HOST"] = hook_host
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return env


def run_python_hook(fixture: Path, host: str, module: str, payload: dict, events_dir: Path):
    """Run one Python host's hook as a real subprocess.

    A subprocess, not an in-process call, because assertion 3 compares stdout,
    stderr AND the exit code as BYTES — none of which an in-process invocation
    can honestly produce, and `text=True` would hide an encoding divergence
    behind the locale decoder. `-B` keeps __pycache__ out of the fixture (one
    less open handle at teardown on Windows, L-00000035).
    """
    script = fixture / PY_HOSTS[host] / "hooks" / f"{module}.py"
    return subprocess.run(
        [sys.executable, "-B", str(script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(fixture),
        env=hook_env(events_dir, hook_host=host),
        timeout=60,
    )


def run_claude_hook(fixture: Path, script: str, payload: dict, events_dir: Path):
    """Run the REAL Claude hook against the fixture project. Only its project
    dir is a fixture: the script under test is the shipped file, and the
    emit-event.sh + events.py it reaches are the fixture's copies."""
    return subprocess.run(
        [BASH, str(ROOT / ".claude" / "hooks" / script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(fixture),
        env=hook_env(events_dir, project_dir=fixture),
        timeout=60,
    )


def raw_stream(events_dir: Path) -> bytes:
    """Every byte written under the redirected events dir, in filename order.
    Read as BYTES on purpose — assertion 2 is about bytes, and a text-mode read
    would silently translate away the very CR this suite is looking for."""
    return b"".join(p.read_bytes() for p in sorted(events_dir.glob("*.jsonl")))


def records(events_dir: Path) -> list:
    """Reader-aggregates contract: a day is N files (one per writer), so glob
    and concatenate — never assume a single day-file (events.py option C)."""
    out = []
    for line in raw_stream(events_dir).decode("utf-8").split("\n"):
        if line.strip():
            out.append(json.loads(line))
    return out


def assert_lf(raw: bytes) -> None:
    """L-003: the JSONL stream is LF-only. events.py opens the day-file with
    os.O_BINARY on Windows precisely so the CRT cannot rewrite "\\n" as
    "\\r\\n"; this is the assertion that keeps that true from the outside."""
    if b"\r" in raw:
        raise AssertionError(f"CR byte in the event stream (L-003): {raw!r}")


def envelope_signature(record: dict) -> tuple:
    """The part of a canal-A line that MUST match across hosts: the kind and the
    set of `data` keys.

    `host` is excluded BY DEFINITION — it is the one field that has to differ.
    So are the per-write facts no two processes could ever share: `ts`, `user`,
    and the pid inside the day-filename.
    """
    return record["kind"], tuple(sorted((record.get("data") or {}).keys()))


def find_record(recs: list, kind: str) -> dict:
    for record in recs:
        if record.get("kind") == kind:
            return record
    raise AssertionError(f"no {kind} event captured; got {[r.get('kind') for r in recs]}")


# (label, kind, claude script + payload, python payload, compare data values?)
#
# The python payload is shared by codex/copilot/gemini; the Claude payload is
# separate because two surfaces cannot be given the same stimulus at all (see
# the per-row notes). `values` is False exactly where the two hosts run a
# genuinely different check — asserting equal values there would force one host
# to lie about what it measured.
PARITY_SURFACES = (
    # A protected path is a protected path on every host: same rule vocabulary
    # (the matched prefix), same normalized path.
    ("protect_paths", "hook.deny", "protect-paths.sh",
     {"tool_input": {"file_path": "src/legacy/x.ts"}},
     {"tool_input": {"file_path": "src/legacy/x.ts"}}, True),
    # Same command -> same UNSALTED sha256 and same length, across a bash hook
    # and a python hook. That byte equality is the whole point of keeping the
    # fingerprint algorithm identical (see safe_bash.command_fingerprint).
    ("safe_bash", "hook.deny", "safe-bash.sh",
     {"tool_input": {"command": LEAKY_COMMAND}},
     {"tool_input": {"command": LEAKY_COMMAND}}, True),
    # Both hosts extract the same skill ref from the same command line.
    ("audit_gate", "hook.deny", "audit-gate.sh",
     {"tool_input": {"command": "npx skills add some/ref"}},
     {"tool_input": {"command": "npx skills add some/ref"}}, True),
    # A compaction is a compaction: trigger=pre, no payload to diverge on.
    ("pre_compact", "session.compact", "pre-compact.sh",
     {"transcript_path": ""}, {"transcript_path": ""}, True),
    # session.start carries an empty data object by design (envelope only).
    ("session_start", "session.start", "session-start.sh", {}, {}, True),
    # index.stale: shape only. Claude asks build_index.py --stale-check (falling
    # back to git here), the python hosts walk mtimes over WATCH_DIRS — two
    # different definitions of "stale", so two different `reason` strings. The
    # field is the same; the sentence describes the check that actually ran.
    ("stale_index", "index.stale", "stop-reindex.sh", {}, {}, False),
    # hook.check_fail: shape only, and the STIMULUS itself differs by
    # construction — Claude compiles the edited file (rule = its extension),
    # while these hosts run `git diff --check` over the worktree (rule =
    # whitespace). There is no stimulus that triggers both checks.
    ("post_edit_check", "hook.check_fail", "post-edit-check.sh",
     {"tool_input": {"file_path": "REPLACED_WITH_FIXTURE_PATH"}},
     {"tool_input": {"file_path": "src/ws.txt"}}, False),
    # agent.stop: shape only. Claude reads the agent's own last turn, else the
    # harness's toolUseResult total (log-agent-usage.sh header), the python hosts
    # sum message.usage from their transcript — the token VALUE is host-specific
    # accounting, not a parity property. `duration_ms` is CLAUDE-ONLY in
    # production (T-01M55Z3ZCS34CDR2EQN1CEBHR7: stop minus the SubagentStart mark
    # of the same agent_id) and absent from this stimulus, which plants no start:
    # the parity below is the shape WITHOUT a start, never a claim that the hosts
    # carry the same fields live.
    ("log_agent_usage", "agent.stop", "log-agent-usage.sh",
     {"hook_event_name": "SubagentStop", "agent_type": "dev-multi", "session_id": "s1",
      "agent_id": "a1", "transcript_path": "REPLACED_WITH_FIXTURE_PATH",
      "last_assistant_message": "done"},
     {"agentType": "dev-multi", "sessionId": "s1", "agentId": "a1",
      "transcriptPath": "REPLACED_WITH_FIXTURE_PATH"}, False),
)

# (surface, host) couples that must emit NO event of the row's kind, each with
# its WRITTEN motive. CLOSED table: the arm below demands the ABSENCE of the kind
# for these couples — never a silent skip — and the parity stays required between
# the remaining hosts of the row.
SANS_ENREGISTREMENT = {
    ("log_agent_usage", "copilot"): (
        "un subagentStop copilot ne porte pas de totaux (M-P5, M-P10) : son "
        "transcriptPath désigne l'events.jsonl du parent, sans clé usage, donc "
        "transcript_total n'est plus appelé sous copilot (T-01M4RWC6VHHN479J2A9RRY1BE3) ; "
        "T-01M4RWCM1ZR65Y47X3M9WXRE67 émet agent.stop à l'agentStop du parent depuis "
        "subagent.completed, jamais au subagentStop : le couple reste exclu après elle"
    ),
}

CLAUDE_SCRIPT_FOR = {
    "protect_paths": "protect-paths.sh", "safe_bash": "safe-bash.sh",
    "audit_gate": "audit-gate.sh", "pre_compact": "pre-compact.sh",
    "session_start": "session-start.sh", "stale_index": "stop-reindex.sh",
    "post_edit_check": "post-edit-check.sh", "log_agent_usage": "log-agent-usage.sh",
}
PY_MODULE_FOR = {
    "protect_paths": "protect_paths", "safe_bash": "safe_bash", "audit_gate": "audit_gate",
    "pre_compact": "pre_compact_backup", "session_start": "session_context",
    "stale_index": "stale_index", "post_edit_check": "post_edit_check",
    "log_agent_usage": "log_agent_usage",
}


class CanalAParityTests(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors: a lingering git/AV handle on a fixture file
        # raises PermissionError at teardown on Windows (L-00000035). That is
        # infrastructure noise; every assertion has already run by then.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.fixture = build_fixture(self.tmp / "project")

    def tearDown(self):
        self._tmp.cleanup()

    def events_dir(self, name: str) -> Path:
        # Outside the fixture: the emitter must not be able to influence the
        # staleness/whitespace stimuli by writing into a watched directory.
        target = self.tmp / "events" / name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _resolve(self, payload: dict, surface: str, host: str) -> dict:
        """Substitute the two fixture-dependent placeholders in the table."""
        payload = json.loads(json.dumps(payload))
        if surface == "post_edit_check" and host == "claude":
            payload["tool_input"]["file_path"] = str(self.fixture / "bad_syntax.py")
        if surface == "log_agent_usage":
            name = "claude-transcript.jsonl" if host == "claude" else "codex-transcript.jsonl"
            key = "transcript_path" if host == "claude" else "transcriptPath"
            payload[key] = str(self.fixture / name)
        return payload

    def capture(self, surface: str, host: str, claude_payload: dict, py_payload: dict):
        """Run one surface on one host and return (record, raw bytes)."""
        events = self.events_dir(f"{surface}-{host}")
        if host == "claude":
            run_claude_hook(
                self.fixture, CLAUDE_SCRIPT_FOR[surface],
                self._resolve(claude_payload, surface, host), events,
            )
        else:
            run_python_hook(
                self.fixture, host, PY_MODULE_FOR[surface],
                self._resolve(py_payload, surface, host), events,
            )
        return records(events), raw_stream(events)

    # -- 1. parity ---------------------------------------------------------

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_every_wired_surface_emits_the_same_envelope_on_every_host(self):
        for couple, motive in SANS_ENREGISTREMENT.items():
            self.assertTrue(str(motive or "").strip(), f"{couple}: an exclusion needs a written motive")
        for surface, kind, _script, claude_payload, py_payload, values in PARITY_SURFACES:
            with self.subTest(surface=surface):
                signatures, data_by_host = {}, {}
                for host in ("claude", "codex", "copilot", "gemini"):
                    recs, raw = self.capture(surface, host, claude_payload, py_payload)
                    assert_lf(raw)  # assertion 2, checked per host per surface
                    if (surface, host) in SANS_ENREGISTREMENT:
                        # The ABSENCE is the assertion — never a silent skip.
                        self.assertEqual(
                            [r for r in recs if r.get("kind") == kind], [],
                            f"{surface}/{host}: {kind} must be absent — "
                            f"{SANS_ENREGISTREMENT[(surface, host)]}",
                        )
                        continue
                    record = find_record(recs, kind)
                    self.assertEqual(
                        record["host"], host,
                        f"{surface}/{host}: envelope host mislabelled as {record['host']!r}",
                    )
                    signatures[host] = envelope_signature(record)
                    data_by_host[host] = record.get("data") or {}
                distinct = set(signatures.values())
                self.assertEqual(
                    len(distinct), 1,
                    f"{surface}: kind/data-key divergence across hosts -> {signatures}",
                )
                if values:
                    distinct_data = {json.dumps(d, sort_keys=True) for d in data_by_host.values()}
                    self.assertEqual(
                        len(distinct_data), 1,
                        f"{surface}: same stimulus produced different data -> {data_by_host}",
                    )

    # -- 1b. the security-critical row, asserted on its own ----------------

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_safe_bash_deny_never_carries_a_substring_of_the_command_on_any_host(self):
        """L-00000043's regression guard, extended to all four hosts.

        Kept separate from the table above so a failure names this property
        instead of "surface=safe_bash": the field-shape assertion and "no
        credential survived into the record" are different claims, and only one
        of them shipped a live leak.
        """
        for host in ("claude", "codex", "copilot", "gemini"):
            with self.subTest(host=host):
                recs, raw = self.capture(
                    "safe_bash", host,
                    {"tool_input": {"command": LEAKY_COMMAND}},
                    {"tool_input": {"command": LEAKY_COMMAND}},
                )
                text = raw.decode("utf-8")
                self.assertNotIn(FAKE_TOKEN, text, f"{host}: fake token leaked into the record")
                self.assertNotIn(LEAKY_COMMAND, text, f"{host}: raw command leaked into the record")
                data = find_record(recs, "hook.deny")["data"]
                self.assertTrue(data.get("cmd_sha256"), f"{host}: no cmd_sha256")
                # T-00000042 — assert the TYPE, not merely the presence. The
                # earlier `assertTrue(...)` accepted "94" and 94 alike, which is
                # how the two hosts drifted apart in the first place: one field
                # name carrying two JSON types depending on who denied.
                self.assertIsInstance(data.get("cmd_len"), int,
                                      f"{host}: cmd_len must be a JSON number, got {data.get('cmd_len')!r}")
                self.assertEqual(data["cmd_len"], len(LEAKY_COMMAND),
                                 f"{host}: cmd_len must be the command's real length")
                self.assertNotIn("path", data, f"{host}: safe-bash must never send `path`")

    # -- 1b bis. hook.warn: the kit-code grant, the one protect-paths WARNING --

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_kit_code_grant_warn_is_identical_across_hosts(self):
        """T-00000763 A — under `KIT_CODE_PROTEGE` a write covered by a pilot
        grant PASSES, and that passage is the only canal-A line protect-paths
        writes without refusing: `hook.warn{guard, rule=kit-code-octroi, path}`.
        A grant that one host logs and another swallows would make the audit of
        who wrote kit code depend on which host did — so the line is asserted by
        VALUE on the four hosts, and the absence of any `hook.deny` with it.
        The markers are planted by `write_text` in the fixture only: the kit
        ships disarmed."""
        gates = self.fixture / ".agents" / "state" / "gates"
        (gates / "KIT_CODE_PROTEGE").write_text("", encoding="utf-8")
        (gates / "KIT_CODE_AUTORISE").write_text(
            ".claude/hooks/ T-00000763 2099-01-01T00:00Z\n", encoding="utf-8")
        shutil.copy2(ROOT / ".agents" / "bin" / "kit_code_guard.py",
                     self.fixture / ".agents" / "bin" / "kit_code_guard.py")
        payload = {"tool_input": {"file_path": ".claude/hooks/x.sh"}}
        data_by_host = {}
        for host in ("claude", "codex", "copilot", "gemini"):
            with self.subTest(host=host):
                recs, raw = self.capture("protect_paths", host, payload, payload)
                assert_lf(raw)
                self.assertEqual([r for r in recs if r.get("kind") == "hook.deny"], [],
                                 f"{host}: a granted kit-code write was refused")
                record = find_record(recs, "hook.warn")
                self.assertEqual(record["host"], host)
                data_by_host[host] = record.get("data") or {}
        self.assertEqual(
            {json.dumps(d, sort_keys=True) for d in data_by_host.values()},
            {json.dumps({"guard": "protect-paths", "rule": "kit-code-octroi",
                         "path": ".claude/hooks/x.sh"}, sort_keys=True)},
            f"the grant warning differs across hosts -> {data_by_host}",
        )

    # -- 1c. gate.forecast: same surface, two different scripts on Claude --

    @unittest.skipIf(BASH is None, "no bash on PATH — cannot exercise the Claude host")
    def test_gate_forecast_envelope_is_identical_across_hosts(self):
        """The est→actual reconciliation, one of canal A's two highest-value
        events — and the only wired surface where Claude splits the work across
        TWO scripts (log-agent-usage.sh captures, run-recap.sh reconciles) while
        the python hosts do both in log_agent_usage.py's session-level branch.

        Seeded so the reconciled state is genuinely the same on both sides — one
        agent, one estimate, no actual — which makes `estimates` and `total_est`
        comparable by VALUE, not merely by shape. `total_est` in particular is
        what caught the two hosts formatting the same total differently (fmtk vs
        fmt): 5000 must read "5.0k" everywhere.
        """
        run_log = self.fixture / ".agents" / "state" / "local" / "RUN_LOG.md"
        header = (
            "# Run log\n| agent | est | actual | note |\n|-------|-----|--------|------|\n"
        )
        forecast_message = "FORECAST  est.\n  dev-multi edit ~5k\n  TOTAL ~5k"
        expected = {
            "estimates": [{"agent": "dev-multi", "est": "~5k", "actual": ""}],
            "total_est": "5.0k",
        }
        for host in ("claude", "codex", "copilot", "gemini"):
            with self.subTest(host=host):
                events = self.events_dir(f"forecast-{host}")
                if host == "claude":
                    run_log.parent.mkdir(parents=True, exist_ok=True)
                    run_log.write_text(header + "| dev-multi | ~5k |  |  |\n", encoding="utf-8")
                    run_claude_hook(self.fixture, "run-recap.sh", {}, events)
                else:
                    run_log.unlink(missing_ok=True)  # est comes from the message
                    run_python_hook(
                        self.fixture, host, "log_agent_usage",
                        {"lastAssistantMessage": forecast_message}, events,
                    )
                record = find_record(records(events), "gate.forecast")
                assert_lf(raw_stream(events))
                self.assertEqual(record["host"], host)
                self.assertEqual(record["data"], expected, f"{host}: gate.forecast diverged")

    # -- 3. fail-open differential ----------------------------------------

    def test_fail_open_is_byte_identical_with_and_without_events_py(self):
        """events.py present vs deleted: stdout, stderr and exit code identical.

        ONE fixture, two legs, the module unlinked in between — deliberately not
        two independently-built fixtures, which is what forces
        events-wiring.test.sh to normalize commit SHAs and mktemp paths out of
        its comparator. With a single fixture there is nothing to normalize, so
        the comparator cannot be non-deterministic by construction.
        """
        payloads = {
            "protect_paths": {"tool_input": {"file_path": "src/legacy/x.ts"}},
            "safe_bash": {"tool_input": {"command": LEAKY_COMMAND}},
            "audit_gate": {"tool_input": {"command": "npx skills add some/ref"}},
            "post_edit_check": {"tool_input": {"file_path": "src/ws.txt"}},
            "stale_index": {},
            "pre_compact_backup": {"transcript_path": ""},
            "session_context": {},
            "log_agent_usage": {
                "agentType": "dev-multi",
                "transcriptPath": str(self.fixture / "codex-transcript.jsonl"),
            },
            "iac_guard": {"tool_input": {"command": "terraform apply"}},
        }
        events_py = self.fixture / ".agents" / "bin" / "events.py"
        for host in ("codex", "gemini"):
            for module in HOOK_MODULES:
                with self.subTest(host=host, hook=module):
                    payload = payloads[module]
                    with_events = run_python_hook(
                        self.fixture, host, module, payload, self.events_dir(f"a-{host}-{module}")
                    )
                    backup = events_py.read_bytes()
                    events_py.unlink()
                    try:
                        without = run_python_hook(
                            self.fixture, host, module, payload,
                            self.events_dir(f"b-{host}-{module}"),
                        )
                    finally:
                        events_py.write_bytes(backup)
                    self.assertEqual(
                        with_events.returncode, without.returncode,
                        f"{host}/{module}: exit code moved when events.py vanished",
                    )
                    self.assertEqual(
                        with_events.stdout, without.stdout,
                        f"{host}/{module}: stdout is not byte-identical",
                    )
                    self.assertEqual(
                        with_events.stderr, without.stderr,
                        f"{host}/{module}: stderr is not byte-identical",
                    )

    # -- 4. host label -----------------------------------------------------

    def test_shared_codex_file_labels_the_running_host_from_the_registration(self):
        for declared in ("codex", "copilot", "kimi"):
            with self.subTest(declared=declared):
                events = self.events_dir(f"label-{declared}")
                run_python_hook(
                    self.fixture, declared, "protect_paths",
                    {"tool_input": {"file_path": "src/legacy/x.ts"}}, events,
                )
                self.assertEqual(find_record(records(events), "hook.deny")["host"], declared)

    def test_shared_codex_file_labels_nothing_when_it_cannot_tell(self):
        """The documented limit, asserted rather than trusted.

        With no AGENTS_HOOK_HOST (a project provisioned before T-00000027) — or
        an unrecognised one — .codex/hooks/ genuinely cannot tell Codex from
        Copilot, so it must leave `host` null instead of defaulting to "codex"
        and attributing every Copilot denial to Codex.
        """
        for value in (None, "definitely-not-a-host"):
            with self.subTest(value=value):
                events = self.events_dir(f"label-absent-{value}")
                script = self.fixture / ".codex" / "hooks" / "protect_paths.py"
                subprocess.run(
                    [sys.executable, "-B", str(script)],
                    input=json.dumps({"tool_input": {"file_path": "src/legacy/x.ts"}}).encode(),
                    capture_output=True, cwd=str(self.fixture),
                    env=hook_env(events, hook_host=value), timeout=60,
                )
                self.assertIsNone(find_record(records(events), "hook.deny")["host"])
                names = [p.name for p in events.glob("*.jsonl")]
                self.assertTrue(
                    all(".unknown." in n for n in names),
                    f"an unlabelled writer must file under .unknown.: {names}",
                )

    def test_gemini_file_ignores_the_shared_discriminant_and_stays_gemini(self):
        """.gemini/hooks/ serves one host, so event_host() reads its label from the
        DIRECTORY (the closed table _HOOK_DIR_HOSTS) before AGENTS_HOOK_HOST is
        consulted. Feeding it the Codex/Copilot discriminant must not move it —
        otherwise an env var set for another host could relabel Gemini's whole trail."""
        events = self.events_dir("label-gemini")
        script = self.fixture / ".gemini" / "hooks" / "protect_paths.py"
        subprocess.run(
            [sys.executable, "-B", str(script)],
            input=json.dumps({"tool_input": {"file_path": "src/legacy/x.ts"}}).encode(),
            capture_output=True, cwd=str(self.fixture),
            env=hook_env(events, hook_host="copilot"), timeout=60,
        )
        self.assertEqual(find_record(records(events), "hook.deny")["host"], "gemini")

    # -- 5. negative controls ---------------------------------------------

    def test_negative_control_signature_comparator_detects_divergence(self):
        """Proof the parity assertions can FAIL. If a dropped `data` key or a
        changed `kind` compared equal here, every parity subTest above would be
        passing vacuously."""
        full = {"kind": "hook.deny", "data": {"guard": "g", "rule": "r", "path": "p"}}
        missing_key = {"kind": "hook.deny", "data": {"guard": "g", "rule": "r"}}
        other_kind = {"kind": "hook.warn", "data": dict(full["data"])}
        self.assertEqual(envelope_signature(full), envelope_signature(dict(full)))
        self.assertNotEqual(envelope_signature(full), envelope_signature(missing_key))
        self.assertNotEqual(envelope_signature(full), envelope_signature(other_kind))
        # `host` must NOT participate: it is the field required to differ.
        self.assertEqual(
            envelope_signature({**full, "host": "codex"}),
            envelope_signature({**full, "host": "gemini"}),
        )

    def test_negative_control_lf_assertion_rejects_crlf(self):
        """Proof the L-003 assertion can FAIL — a CRLF stream must raise."""
        assert_lf(b'{"kind":"hook.deny"}\n')
        with self.assertRaises(AssertionError):
            assert_lf(b'{"kind":"hook.deny"}\r\n')

    def test_negative_control_find_record_fails_on_a_silent_host(self):
        """Proof that "no event at all" is a failure, not a pass. A host that
        emits nothing must not slip through as trivially parity-compliant."""
        with self.assertRaises(AssertionError):
            find_record([], "hook.deny")
        with self.assertRaises(AssertionError):
            find_record([{"kind": "session.start", "data": {}}], "hook.deny")


# Sonde jouée dans un processus isolé : la branche (1) d'`events._redaction`
# (paquet installé) est forcée en échec, seule la branche (2) PAR CHEMIN reste.
_SONDE_REDACTION = (
    "import importlib.util, sys\n"
    "s = importlib.util.spec_from_file_location('_ep_events_sonde', sys.argv[1])\n"
    "m = sys.modules[s.name] = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
    "def _absent(): raise ImportError('paquet installe ecarte')\n"
    "m._importer_redaction_paquet = _absent\n"
    "r = m._redaction()\n"
    "print('ABSENTE' if r is None else r.__file__)\n"
)


def test_vendor_seul_c():
    """Témoin C (T-01M5BXTPQE3JZV3KZA6WD9P5XC) : un kit SOURCE où `cadre` ne vit
    QUE sous `.agents/vendor/cadre/` alimente quand même la fixture, et le
    `redaction.py` posé est trouvé aux DEUX lieux — l'`events.py` copié le
    charge par chemin, sans tomber en voie dégradée."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp).resolve()
        source, kit = base / "source", base / "kit"
        paquet = source / ".agents" / "vendor" / "cadre"
        (paquet / "ledger").mkdir(parents=True)
        (paquet / "__init__.py").write_text("", encoding="utf-8")
        origine = _VENDOR.exiger(ROOT, "cadre") / "ledger" / "redaction.py"
        shutil.copy2(origine, paquet / "ledger" / "redaction.py")
        assert not (source / "src").exists(), "le kit source doit être vendor seul"
        (kit / ".agents" / "bin").mkdir(parents=True)
        events = kit / ".agents" / "bin" / "events.py"
        shutil.copy2(ROOT / ".agents" / "bin" / "events.py", events)

        poser_redaction(kit, source)

        attendu = origine.read_bytes()
        for lieu in REDACTION_LIEUX:
            assert (kit / lieu).read_bytes() == attendu, f"redaction.py absent ou faux : {lieu}"
        env = dict(os.environ, AGENTS_EVENTS_DIR=str(base / "events"))
        env.pop("PYTHONPATH", None)
        sortie = subprocess.run(
            [sys.executable, "-I", "-B", "-c", _SONDE_REDACTION, str(events)],
            capture_output=True, text=True, env=env, cwd=str(kit),
        )
        assert sortie.returncode == 0, sortie.stderr
        charge = sortie.stdout.strip()
        assert charge != "ABSENTE", "events.py tombe en voie dégradée : redaction introuvable"
        assert Path(charge).resolve() in {(kit / lieu).resolve() for lieu in REDACTION_LIEUX}, charge

        # L'`events.py` de 5/5, qui lira le lieu NEUF : sa copie réécrite doit charger
        # `kit/.agents/vendor/cadre/ledger/redaction.py` — un lieu vendor retiré de
        # `REDACTION_LIEUX` la laisse sans rédaction (rouge).
        texte = events.read_text(encoding="utf-8")
        vise = texte.replace('"src" / "cadre"', '".agents" / "vendor" / "cadre"')
        if vise == texte:  # 5/5 : events.py lit déjà le lieu neuf
            assert '".agents" / "vendor" / "cadre"' in texte, "events.py ne cite ni `src` ni le lieu neuf"
        events_vendor = kit / ".agents" / "bin" / "events_vendor.py"
        events_vendor.write_text(vise, encoding="utf-8")
        sortie = subprocess.run(
            [sys.executable, "-I", "-B", "-c", _SONDE_REDACTION, str(events_vendor)],
            capture_output=True, text=True, env=env, cwd=str(kit),
        )
        assert sortie.returncode == 0, sortie.stderr
        charge = sortie.stdout.strip()
        neuf = kit / ".agents" / "vendor" / "cadre" / "ledger" / "redaction.py"
        assert charge != "ABSENTE" and Path(charge).resolve() == neuf.resolve(), charge


if __name__ == "__main__":
    unittest.main()
