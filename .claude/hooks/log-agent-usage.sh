#!/usr/bin/env bash
# SubagentStop — deterministic per-subagent token capture + forecast seeding into .agents/state/local/RUN_LOG.md,
# and the STOP of the agent's real chrono (T-01M55Z3ZCS34CDR2EQN1CEBHR7): one `stop` line in
# .agents/state/local/agent-chrono.jsonl and one agent.stop{aid, duration_ms, tokens} on canal A.
#
# DURATION = this stop minus the LAST SubagentStart of the same agent_id (agent-events.sh writes
# it); no start seen => no duration_ms key, never a 0.
# TOKENS: (1) the usage of the LAST assistant turn of the AGENT's own transcript
# (`agent_transcript_path`: input + cache creation + cache read + output) — the ONLY figure the
# journal records. (2) Failing it, RUN_LOG and agent.stop keep their pre-chrono source, the
# harness's `toolUseResult.totalTokens` matched on `agentType` in the SESSION transcript; that key
# was absent from 10/10 recent session transcripts of this kit (exec-critic, 2026-10-19), and (2)
# never reaches the journal: no `tokens` key there rather than an unproven figure. NEVER a sum of
# per-turn message.usage (that would N-count the re-read cache prefix and, since transcript_path is
# the SESSION transcript, misattribute every agent's usage). (1) answering spares reading the
# session transcript, which measured 130 MB on one session of this kit.
#
# (1) IS AN ESTIMATE, AND ITS ERROR IS BOUNDED ONLY TO WHAT WAS MEASURED — on THIS kit, against the
# harness's own subagent total: under it by 1 % or less on 3 agents (2026-10-16), and by 4.1 % on
# ONE agent (plan-critic r1 of T-01M55Z3ZCS34CDR2EQN1CEBHR7: its last output was still partial).
# A sample of four, on one kit and one host version: not a bound for any other agent or adopter.
#
# Tooling (agent_chrono.py) loads from this script's tree, UNDER try; state follows
# CLAUDE_PROJECT_DIR. Zero model tokens. Advisory only: ALWAYS exits 0.
INPUT=$(cat)
PY=""
PY_PROBE='import sys; sys.stdout.write(sys.executable); sys.exit(sys.version_info[0] != 3)'
PY_CR="$(printf '\r')"
for c in python3 python; do
  PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
  case "$PY_CANDIDATE" in
    *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
  esac
  if [ -n "$PY_CANDIDATE" ]; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  PY_UNAME=""
  command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"
  case "${OS-}:$PY_UNAME" in
    Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
      PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
      case "$PY_CANDIDATE" in
        *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
      esac
      [ -n "$PY_CANDIDATE" ] && PY="$PY_CANDIDATE"
      ;;
  esac
fi
[ -n "$PY" ] || {
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  exit 0
}
KIT="$(cd "$(dirname "$0")/../.." && pwd)"
"$PY" -B - "$INPUT" "$KIT" << 'PYEOF'
import importlib.util, json, os, re, sys
from pathlib import Path

# events.py loaded by EXPLICIT PATH — `from events import emit` is BANNED here.
# This script runs Python FED FROM STDIN (`"$PY" - "$INPUT" << 'PYEOF'`, see
# the invocation above) — sys.path[0] there is the invoking shell's
# cwd, not this file's directory, so a bare name-import would silently
# resolve to nothing. Same idiom as run-recap.sh:39-41 (tasks.py).
def _load_events(root):
    try:
        p = Path(root) / ".agents" / "bin" / "events.py"
        spec = importlib.util.spec_from_file_location("events", p)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None

def _chrono(d, root):
    # agent_chrono.py from THIS script's tree (argv[2]); loader AND calls under try:
    # absent or raising => {} and the hook keeps its pre-chrono behaviour.
    try:
        p = Path(sys.argv[2]) / ".agents" / "bin" / "agent_chrono.py"
        spec = importlib.util.spec_from_file_location("_cadre_agent_chrono_hook", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod, mod.chrono_de(root, d)
    except Exception:
        return None, {}

HEADER = [
    "# Run log — ephemeral (git-ignored). est seeded from FORECAST; actual filled on SubagentStop; cleared by recap.",
    "| agent | est | actual | note |",
    "|-------|-----|--------|------|",
]
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens")

def fmt(tokens):
    return f"{tokens/1000:.1f}k" if tokens >= 1000 else str(tokens)

def resolve_path(p):
    # Best-effort: a Git-Bash/MSYS POSIX-style path (e.g. /c/Users/...) passed
    # to a native (non-MSYS) Windows Python won't resolve as-is. If the literal
    # path is missing, try translating a leading "/<drive>/" to "<drive>:/".
    path = Path(p)
    if path.exists():
        return path
    m = re.match(r"^/([A-Za-z])/(.*)$", p)
    if m:
        alt = Path(f"{m.group(1)}:/{m.group(2)}")
        if alt.exists():
            return alt
    return path

def read_rows(path):
    rows, order = {}, []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$", line)
            if m:
                agent = m.group(1)
                if agent != "agent" and set(agent) - {"-"}:
                    rows[agent] = [m.group(2).strip(), m.group(3).strip(), m.group(4).strip()]
                    if agent not in order:
                        order.append(agent)
    return rows, order

def write_rows(path, rows, order):
    lines = HEADER + [
        f"| {a} | {rows[a][0] or '-'} | {rows[a][1] or ''} | {rows[a][2] or ''} |"
        for a in order
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def set_est(rows, order, agent, est):
    prev = rows.get(agent, ["", "", ""])
    rows[agent] = [est, prev[1], prev[2]]
    if agent not in order:
        order.append(agent)

def main():
    d = json.loads(sys.argv[1])
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    log = root / ".agents" / "state" / "local" / "RUN_LOG.md"
    agent = (d.get("agent_type") or "").strip()
    msg = d.get("last_assistant_message") or ""
    rows, order = read_rows(log)

    # Orchestrator finished → seed est rows from its FORECAST block.
    if agent == "orchestrator":
        in_block = False
        for line in msg.splitlines():
            if re.match(r"\s*FORECAST\b", line):
                in_block = True
                continue
            if in_block:
                if re.match(r"\s*TOTAL\b", line) or re.match(r"\s*-{4,}\s*$", line):
                    break
                m = re.match(r"\s*([a-z][a-z0-9-]*)\s+.*?(~\d+k|~\?)\s*$", line)
                if m:
                    set_est(rows, order, m.group(1), m.group(2))

    # Planner (or anyone) may refine an estimate.
    for m in re.finditer(r"FORECAST-REFINE:\s*([a-z][a-z0-9-]*)\s+(~\d+k)", msg):
        set_est(rows, order, m.group(1), m.group(2))

    # Any agent → its ACCURATE own total from the `toolUseResult` the harness writes when the
    # Task finishes. transcript_path is the session transcript, so match on agentType and take
    # the last such result (the run that just ended). totalTokens is the subagent's aggregate;
    # fall back to summing its aggregate `usage` if absent. Never summed per-turn (cache_read
    # recurs every turn) — a missing result yields no number rather than a wrong one.
    # The chrono first: duration since the agent's start, tokens of its own last turn.
    chrono_mod, chrono = _chrono(d, root)
    tp = d.get("transcript_path") or ""
    tp_path = resolve_path(tp) if tp else None
    total = chrono.get("tokens")
    if agent and not total and tp_path and tp_path.exists():
        for line in tp_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line).get("toolUseResult")
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(r, dict) and r.get("agentType") == agent:
                t = r.get("totalTokens")
                if not isinstance(t, int):
                    u = r.get("usage")
                    t = sum(int(u.get(k) or 0) for k in USAGE_KEYS) if isinstance(u, dict) else None
                if isinstance(t, int) and t > 0:
                    total = t  # keep scanning → last match wins
    if agent and total:
        prev = rows.get(agent, ["", "", ""])
        rows[agent] = [prev[0], fmt(total), prev[2]]
        if agent not in order:
            order.append(agent)

    if order:
        write_rows(log, rows, order)

    # The journal's `stop` line, BEFORE and WITHOUT events.py (the chrono does
    # not depend on canal A); keys only when known, never a 0; `tokens` from the
    # agent's own transcript only — the session fallback above never lands here.
    if chrono_mod is not None and chrono:
        try:
            chrono_mod.noter_fin(root, chrono)
        except Exception:
            pass

    # agent.stop — one of the two highest-value events in T-00000018 (the
    # other is run-recap.sh's gate.forecast), and since T-01M55Z3ZCS34CDR2EQN1CEBHR7
    # the ONLY agent.stop of this host (agent-events.sh's PostToolUse leg is
    # gone). ALLOWLIST(agent.stop) = {tokens, est, duration_ms, model}: tokens
    # (header), est, and duration_ms when a start was seen; `model` is not on
    # this payload and is left absent rather than guessed.
    if agent and (total or chrono):
        events = _load_events(root)
        if events is not None:
            est = (rows.get(agent) or ["", "", ""])[0] or None
            # `est` always (None included: emit keeps it, the shape of every host);
            # tokens and duration_ms ONLY when known — absent, never null nor 0.
            fields = {"est": est}
            if total:
                fields["tokens"] = total
            if isinstance(chrono.get("duration_ms"), int):
                fields["duration_ms"] = chrono["duration_ms"]
            try:
                events.emit(
                    "agent.stop", host="claude",
                    sid=d.get("session_id"), aid=d.get("agent_id") or d.get("agentId"), agent=agent,
                    **fields,
                )
            except Exception:
                pass

try:
    main()
except Exception:
    pass
sys.exit(0)
PYEOF
exit 0
