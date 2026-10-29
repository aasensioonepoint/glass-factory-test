#!/usr/bin/env bash
# mcp-events.sh — PreToolUse/PostToolUse [matcher mcp__.*] -> scan.mcp_call
# (T-00000018 shard 2, new registration — see docs/tasks/T-00000018.md).
#
# Claude Code names MCP tool calls "mcp__<server>__<tool>"; the server segment
# is parsed out here so the event carries package identity, never the raw
# tool_input/tool_response (an MCP argument can BE a live credential — this
# day-file is tracked, so scan.mcp_call's ALLOWLIST in events.py deliberately
# excludes both).
#
# audit_state is a 3-state field (events.py's own comment, C15):
#   "unresolved" — no .mcp.json in THIS project's scope, OR the server isn't
#                  listed in it (e.g. only present in user-scope config,
#                  which this script cannot see or should not try to). This
#                  is the NORMAL state today: the kit ships zero MCP servers
#                  (AGENTS.md), so every call here resolves "unresolved" —
#                  and that must never be treated as degraded (L-00000033/34).
#   "audited"    — server present in .mcp.json AND listed in
#                  .agents/state/gates/MCP_ALLOWLIST.md (human-appended).
#   "unaudited"  — server present in .mcp.json but NOT in the allowlist.
#
# gate.coverage_degraded is reserved for the ONE narrow case the design doc
# calls out: a RESOLUTION FAILURE (malformed .mcp.json, unreadable
# MCP_ALLOWLIST.md) on a server that IS actually present in project config.
# It is never raised for "no .mcp.json at all" or "server not in project
# config" — both of those are the normal "unresolved" outcome.
#
# Import contract: this file IS a "Python fed from stdin" site (same shape as
# run-recap.sh / log-agent-usage.sh) — events.py is loaded in-process by
# explicit path, `from events import emit` is BANNED.
#
# Fail-open, ALWAYS exits 0. Never blocks (this script only ever OBSERVES an
# MCP tool call, it makes no allow/deny decision — that stays with the human
# audit procedure in .agents/ref/MCP_REGISTRY.md).
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
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

"$PY" -B - "$ROOT" "$INPUT" << 'PYEOF' >/dev/null 2>&1
import importlib.util
import json
import os
import re
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


_TOOL_RE = re.compile(r"^mcp__([^_]+)__(.+)$")


def main():
    root = sys.argv[1]
    raw = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    tool = payload.get("tool_name") or ""
    m = _TOOL_RE.match(tool)
    server = m.group(1) if m else (tool or "unknown")
    suffix = m.group(2) if m else ""

    duration_ms = None
    try:
        resp = payload.get("tool_response")
        if isinstance(resp, dict):
            duration_ms = payload.get("duration_ms") or resp.get("duration_ms")
        else:
            duration_ms = payload.get("duration_ms")
    except Exception:
        duration_ms = None

    mcp_json = os.path.join(root, ".mcp.json")
    allowlist = os.path.join(root, ".agents", "state", "gates", "MCP_ALLOWLIST.md")

    audit_state = "unresolved"
    degrade_reason = None
    if os.path.isfile(mcp_json):
        try:
            with open(mcp_json, encoding="utf-8") as fh:
                cfg = json.load(fh)
            servers = cfg.get("mcpServers") or {} if isinstance(cfg, dict) else {}
            if server in servers:
                try:
                    text = ""
                    if os.path.isfile(allowlist):
                        with open(allowlist, encoding="utf-8") as fh:
                            text = fh.read()
                    audit_state = "audited" if server in text else "unaudited"
                except Exception:
                    audit_state = "unresolved"
                    degrade_reason = f"mcp_resolution_failed:{server}"
            # server not listed in THIS project's .mcp.json -> stays
            # "unresolved" (normal: e.g. user-scope-only config).
        except Exception:
            # .mcp.json present but unparsable -> a real resolution failure on
            # config that IS present, the one case that DOES degrade.
            audit_state = "unresolved"
            degrade_reason = f"mcp_resolution_failed:{server}"
    # else: no project .mcp.json at all -> "unresolved" is NORMAL, never
    # raises gate.coverage_degraded (L-00000033/34).

    events = _load("events", os.path.join(root, ".agents", "bin", "events.py"))
    if events is None:
        return

    fields = {"host": "claude", "server": server, "tool": suffix, "audit_state": audit_state}
    if duration_ms is not None:
        fields["duration_ms"] = duration_ms
    try:
        events.emit("scan.mcp_call", **fields)
        if degrade_reason:
            events.emit("gate.coverage_degraded", host="claude", reason=degrade_reason)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
PYEOF
exit 0
