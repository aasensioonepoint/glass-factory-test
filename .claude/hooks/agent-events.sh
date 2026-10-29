#!/usr/bin/env bash
# agent-events.sh — canal-A emission for the agent/session lifecycle hooks NOT
# already owned by an existing script (T-00000018 shard 2, new registrations —
# see docs/tasks/T-00000018.md's "Nouveaux événements à câbler"). Dispatches on
# `hook_event_name` in the stdin payload, so ONE script can be registered under
# several distinct hook events without duplicating the load-events boilerplate:
#
#   SubagentStart              -> agent.start   (aid) + a `start` line in
#                                  .agents/state/local/agent-chrono.jsonl
#                                  (agent_chrono.marquer_debut), written
#                                  BEFORE and WITHOUT events.py: the real
#                                  chrono of the agent (T-01M55Z3ZCS34CDR2EQN1CEBHR7)
#                                  does not depend on canal A's health.
#   SessionEnd                 -> session.stop  (reason)
#   PostCompact                -> session.compact (trigger="post" — distinct
#                                  from pre-compact.sh's own trigger="pre" emit
#                                  on PreCompact; same kind, different phase)
#   PostToolUse [matcher Agent] -> NOTHING since T-01M55Z3ZCS34CDR2EQN1CEBHR7.
#                                  That branch emitted an agent.stop with EMPTY
#                                  data at the LAUNCH of every background agent
#                                  (measured in the kit's own events.db,
#                                  2026-10-19: 3 257 / 3 257 agent.stop empty,
#                                  stamped with the agent.start's time) — a
#                                  second, false stop. agent.stop now comes
#                                  from log-agent-usage.sh (SubagentStop) alone,
#                                  with aid, duration_ms and tokens.
#                                  WHY THE REGISTRATION STAYS (C35): it lives in
#                                  .claude/settings.json, a guard path owned by
#                                  another lot of the same delivery; this script
#                                  exits in bash on that event, BEFORE probing
#                                  any Python. What runs first, per Agent call:
#                                  one bash process; the KIT substitution (a
#                                  subshell: `cd`, `dirname` — an external —
#                                  and `pwd`); `cat` reading stdin in a second
#                                  substitution; a `pwd` substitution only when
#                                  CLAUDE_PROJECT_DIR is unset. Nothing else.
#                                  Its removal: suivi, voir le board.
#
# TOOLING IS ANCHORED TO THIS SCRIPT, STATE FOLLOWS CLAUDE_PROJECT_DIR — same
# split as binome-trace.sh: agent_chrono.py loads from this script's tree,
# UNDER try (absent or raising => no journal line, the hook unchanged).
#
# Registration is NOT part of this shard (pilot, step 2) — see the task's
# scope boundary. This script is proven by direct invocation with synthetic
# stdin, per the same import contract as emit-event.sh (explicit-path load,
# `from events import emit` BANNED — this file IS a "Python fed from stdin"
# site, same shape as run-recap.sh / log-agent-usage.sh, hence the
# in-process load here rather than shelling out to emit-event.sh).
#
# Fail-open, ALWAYS exits 0. Never blocks; never raises past its own stderr.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
KIT="$(cd "$(dirname "$0")/../.." && pwd)"
INPUT=$(cat)
# PostToolUse[Agent] owns no emission any more (header): leave before any Python.
case "$INPUT" in
  *'"hook_event_name":"PostToolUse"'*|*'"hook_event_name": "PostToolUse"'*) exit 0 ;;
esac
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

"$PY" -B - "$ROOT" "$INPUT" "$KIT" << 'PYEOF' >/dev/null 2>&1
import importlib.util
import json
import os
import sys

# NOTE: the hook JSON is passed as sys.argv[2], NOT read from sys.stdin.
# `"$PY" - ... << 'PYEOF'` already uses stdin to feed THIS SCRIPT's own
# source to the interpreter (the `-` + heredoc idiom) — by the time this
# code runs, stdin is at EOF, so `json.load(sys.stdin)` here would always
# see nothing. Same argv-passing fix as log-agent-usage.sh already uses for
# exactly this reason.


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
    raw = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    hook_name = payload.get("hook_event_name") or ""

    # THE START MARK, before events.py and independent of it. Loader AND call
    # under try: `_load` returns None on any failure, `marquer_debut` never raises.
    if hook_name == "SubagentStart" and len(sys.argv) > 3:
        try:
            chrono = _load("_cadre_agent_chrono_hook",
                           os.path.join(sys.argv[3], ".agents", "bin", "agent_chrono.py"))
            if chrono is not None:
                chrono.marquer_debut(root, payload)
        except Exception:
            pass

    events = _load("events", os.path.join(root, ".agents", "bin", "events.py"))
    if events is None:
        return

    sid = payload.get("session_id")

    def safe_emit(kind, **fields):
        clean = {k: v for k, v in fields.items() if v is not None}
        clean.setdefault("host", "claude")
        try:
            events.emit(kind, **clean)
        except Exception:
            pass

    if hook_name == "SubagentStart":
        safe_emit(
            "agent.start",
            sid=sid, aid=payload.get("agent_id"), agent=payload.get("agent_type"),
        )
    elif hook_name == "SessionEnd":
        safe_emit("session.stop", sid=sid, reason=payload.get("reason"))
    elif hook_name == "PostCompact":
        safe_emit("session.compact", sid=sid, trigger="post")
    elif hook_name == "Notification":
        # T-00000090 — the SENSING half of the dashboard's "question en attente"
        # badge. The badge and its marker shipped with T-00000086; nothing ever
        # fed them, so the section rendered a structural OFF that reads exactly
        # like the measurement "no session is waiting". That is the L-010
        # false-GO shape applied to a human's attention.
        # NO PROSE IN `data`, and it is the same argument that kept `message`
        # out of `session.compact`: the day-file is TRACKED, so anything under
        # `data` gets committed. The marker only needs to EXIST — the envelope
        # already carries host/sid/ts, which is all the badge reads. The
        # question the agent asked stays in the transcript, where it belongs.
        safe_emit("session.notify", sid=sid)
    # Any other hook_event_name — PostToolUse[Agent] included since
    # T-01M55Z3ZCS34CDR2EQN1CEBHR7 (header) — : this script was invoked for an
    # event it does not own — silently do nothing rather than guess a kind
    # (never invent outside the closed vocabulary, same discipline as events.py).


try:
    main()
except Exception:
    pass
PYEOF
exit 0
