#!/usr/bin/env bash
# emit-event.sh — canal-A emission bridge for Claude Code hooks (T-00000018 shard 2).
#
# Usage: bash emit-event.sh <kind> [key=value | key:=<json-literal> ...]
#   key=value    stored as a plain string.
#   key:=<json>  the <json> text is json.loads()'d before being stored — use
#                this for status maps (scan.sca), counter dicts, and location
#                arrays; never for a single scalar string (that's key=value).
#
# Envelope fields (sid/pid/aid/task/agent/effort/host) are read from the
# CALLER's environment (EVT_SID / EVT_PID / EVT_AID / EVT_TASK / EVT_AGENT /
# EVT_EFFORT / EVT_HOST), never re-read from stdin here — a caller may have
# already consumed its own stdin (most hooks do, to get tool_input), and a
# second read of a closed/empty pipe would at best return nothing and at
# worst hang. `host` defaults to "claude" (this bridge is Claude-Code-only;
# the other 3 hosts get their own emit path per D5, out of scope here).
#
# Import contract (events.py's own docstring, non-negotiable — see
# docs/tasks/T-00000018.md item 1): `from events import emit` is BANNED.
# This script loads the module by explicit path (importlib.util
# spec_from_file_location -> module_from_spec -> exec_module), the same
# idiom already used at run-recap.sh:39-41 (tasks.py) and statusline.sh:22
# (tasks.py) — the only two places anything on the hook hot path invoked
# Python by explicit path before this shard. `run-recap.sh`/`log-agent-usage.sh`
# run Python fed FROM STDIN (`"$PY" - <<PYEOF`) and load events.py inline,
# in-process, for the same reason: `sys.path[0]` there is the invoking
# shell's cwd, not this file's directory, so a bare name-import would
# silently resolve to nothing (or the wrong module).
#
# Fail-open, ALWAYS exits 0 regardless of what happens inside — a caller
# must never gate its own exit code, stdout, or stderr on this script.
# events.py's own emit() is already fail-open (never raises); every layer
# here (module load, field parsing, the emit() call itself) is wrapped in
# its own try/except so a broken events.py, a missing interpreter, or a
# malformed key:=value argument degrades to "nothing written", never to a
# stack trace on the hook's stderr.
#
# C12 (events.py): no self-report of a permanently-absent module. A module
# that never loads has, by construction, no future successful emit to
# piggyback a report on — the reader infers permanent absence instead
# (design doc §G.4:459). This script does not attempt one either.
#
# Accepted risk (item 7, docs/tasks/T-00000018.md): wiring canal-A raises
# Python-by-explicit-path call sites from 2 (run-recap.sh, statusline.sh) to
# roughly 10, INCLUDING PreToolUse paths (protect-paths.sh, safe-bash.sh,
# audit-gate.sh, mcp-events.sh) that run BEFORE the class-0 secrets gate
# (gitleaks-scan.sh --content). `.agents/bin/` — where this script and
# events.py both live — is NOT among protect-paths.sh's BLOCKED_PATTERNS
# (`src/legacy/ generated/ .env`). This is a stated, accepted risk, not
# fixed here: this script does not modify protect-paths.sh.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
KIND="${1:-}"
[ -z "$KIND" ] && exit 0
shift || true

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

# T-00000032: hard wall bound on the python child. This bridge runs on
# PreToolUse hot paths (protect-paths, safe-bash, audit-gate) — a hung
# interpreter (AV scan, filesystem stall) would freeze the whole session,
# which fail-open cannot tolerate; a LOST event can (that is the module's
# stated contract). Same 5s precedent as session-start.sh's index refresh.
# If timeout(1) is absent (non-MSYS exotic shell), run unbounded rather than
# never emitting — the hang risk is the rarer failure there.
TIMEOUT_CMD=""
command -v timeout >/dev/null 2>&1 && TIMEOUT_CMD="timeout 5"

$TIMEOUT_CMD "$PY" -B - "$ROOT" "$KIND" "$@" << 'PYEOF' >/dev/null 2>&1
import importlib.util
import json
import os
import sys


def _load(name, path):
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def main():
    root = sys.argv[1]
    kind = sys.argv[2]
    raw_pairs = sys.argv[3:]

    events = _load("events", os.path.join(root, ".agents", "bin", "events.py"))
    if events is None:
        return  # events.py absent/unreadable — nothing to do (C12: unreportable in-band)

    fields = {}
    for item in raw_pairs:
        try:
            if ":=" in item:
                k, v = item.split(":=", 1)
                if k:
                    fields[k] = json.loads(v)
            elif "=" in item:
                k, v = item.split("=", 1)
                if k:
                    fields[k] = v
        except Exception:
            continue  # one malformed field must never drop the whole event

    for env_key, field in (
        ("EVT_HOST", "host"), ("EVT_SID", "sid"), ("EVT_PID", "pid"),
        ("EVT_AID", "aid"), ("EVT_TASK", "task"), ("EVT_AGENT", "agent"),
        ("EVT_EFFORT", "effort"),
    ):
        val = os.environ.get(env_key)
        if val:
            fields[field] = val
    fields.setdefault("host", "claude")

    try:
        events.emit(kind, **fields)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
PYEOF
exit 0
