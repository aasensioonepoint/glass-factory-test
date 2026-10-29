#!/usr/bin/env bash
# PreToolUse Agent|Task: require a closed list of existing benches for anchored defs.
# Claude refusal channel: stderr and exit 2. No state marker arms this hook.
# Unreadable payload or no def name: COVERAGE DEGRADED on stderr, exit 0.
# No python 3 or an internal error (S-01M5YZ6VJN): BLOCKED on stderr, exit 2,
# blocking bare and passed through by garde-fermee (no hook.deny event on
# these two paths).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
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
  echo "BLOCKED by hook: bancs-mandat: aucun interpréteur python, mandat non lu — refus (S-01M5YZ6VJN). Remède : installer python 3 (python3, python ou py -3)." >&2
  exit 2
}

# The tool payload remains on stdin: neither the probe nor argv consumes it.
"$PY" -B -c '
import json
import os
from pathlib import Path
import re
import subprocess
import sys

anchor = "BANCS-BORNES (T-01M576S8956DA9FMXY384P7EYF)"
item_re = re.compile(r"^[A-Za-z0-9._/-]+(::[A-Za-z0-9_][A-Za-z0-9_.\[\]-]*)*$")
# Closed list of bench base names, one family per stack the kit ships a sheet
# or a skill for; Rust integration benches are judged by their tests/ parent.
bench_re = re.compile(r"^(test_[^/]*\.py|[^/]*_test\.(?:py|go)|[^/]*\.(?:test|spec)\.[A-Za-z0-9]+"
                      r"|[^/]*_spec\.rb|[^/]*(?:Test|Tests|IT)\.(?:java|kt|cs))$")
rust_re = re.compile(r"^[^/]+\.rs$")
template_re = re.compile(r"<[^>]*>")
# A reason is judged on its first 500 characters: the template search is
# quadratic on a run of "<", and a template past that horizon is not seen.
reason_max = 500
form = ("BANCS: <chemin>[::<test>], <chemin>, … sans backticks, "
        "chemins de bancs existants | BANCS: aucun | <pourquoi> "
        "| BANCS-SANS-BORNE: <pourquoi>")

def safe(value):
    return re.sub(r"[^A-Za-z0-9._:/-]", "?", str(value))

def event(kind, rule, name):
    emitter = root / ".claude/hooks/emit-event.sh"
    if emitter.is_file():
        try:
            subprocess.run(["bash", str(emitter), kind, "guard=bancs-mandat",
                            "rule=" + rule, "path=.claude/agents/" + name + ".md"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

def refuse(rule, item, name, remedy=form):
    print("BLOCKED by hook: " + rule + " : " + safe(item), file=sys.stderr)
    print(remedy, file=sys.stderr)
    event("hook.deny", rule, name)
    return 2

def main():
    # Messages leave as UTF-8 whatever PYTHONIOENCODING says: under ascii or
    # cp1252 the refusal and the way-out would otherwise read escaped.
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    # Bytes decoded as UTF-8, never through the locale: under a cp1252 or ascii
    # PYTHONIOENCODING an accented mandate would read as unreadable, and pass.
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, UnicodeError):
        print("COVERAGE DEGRADED — bancs-mandat: charge illisible", file=sys.stderr)
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("tool_name") not in ("Agent", "Task"):
        sys.exit(0)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    name = ""
    for key in ("subagent_type", "agent_type", "subagentType", "agentType"):
        value = tool_input.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            name = value.strip()
            break
    # No def name under any of the four keys: the guard would be inert, so it says so.
    if not name:
        print("COVERAGE DEGRADED — bancs-mandat: aucun nom de def dans la charge", file=sys.stderr)
        sys.exit(0)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        sys.exit(0)
    definition = root / ".claude/agents" / (name + ".md")
    try:
        if not definition.is_file() or anchor not in definition.read_text(encoding="utf-8"):
            sys.exit(0)
    except (OSError, UnicodeError):
        sys.exit(0)

    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        prompt = ""
    visible = []
    # Lines split on \n alone (annexe 2.4); a trailing \r is stripped with the item.
    # A fence is ``` or ~~~ after leading blanks; only a line of the same mark
    # closes it, the other mark being block content. An open fence refuses the
    # mandate before either BANCS form is chosen; the refusal names the mandate
    # line (from 1) of the fence left open, since a backtick would print as "?"
    # through safe().
    fence = ""
    opened = 0
    for number, line in enumerate(prompt.split("\n"), 1):
        mark = line.lstrip()[:3]
        if mark in ("```", "~~~") and mark == (fence or mark):
            fence = "" if fence else mark
            opened = number
        elif not fence:
            visible.append(line)
    if fence:
        sys.exit(refuse("cloture-ouverte", "ligne-" + str(opened), name, "referme la clôture"))
    # A way-out line counts only with a reason of ten characters or more; the
    # first one decides, a shorter one is not a way out and BANCS: then decides.
    # A way-out next to a BANCS: line is ambiguous and refused: a line relayed
    # from a report must never switch the list off.
    unbounded = [m.group(1) for m in
                 (re.fullmatch(r"BANCS-SANS-BORNE: (.{10,})", line) for line in visible)
                 if m]
    if unbounded and any(line.startswith("BANCS: ") for line in visible):
        sys.exit(refuse("ambigu", "BANCS-SANS-BORNE", name))
    if unbounded:
        reason = unbounded[0][:reason_max]
        if template_re.search(reason):
            sys.exit(refuse("raison-gabarit", reason, name))
        print("SORTIE TRACÉE — bancs-mandat : " + safe(name), file=sys.stderr)
        event("hook.warn", "sans-borne", name)
        sys.exit(0)

    lines = [line[len("BANCS: "):] for line in visible if line.startswith("BANCS: ")]
    if len(lines) != 1 or not lines[0]:
        sys.exit(refuse("sans-liste", "BANCS", name))
    value = lines[0].strip()
    if value.startswith("aucun | ") and len(value[len("aucun | "):]) >= 10:
        reason = value[len("aucun | "):][:reason_max]
        if template_re.search(reason):
            sys.exit(refuse("raison-gabarit", reason, name))
        sys.exit(0)
    for item in value.split(","):
        item = item.strip()
        if "`" in item or not item_re.fullmatch(item):
            sys.exit(refuse("liste-ouverte", item, name))
        path = item.split("::", 1)[0]
        segments = path.split("/")
        if any(segment in ("", ".", "..") for segment in segments):
            sys.exit(refuse("liste-ouverte", item, name))
        rust = len(segments) >= 2 and segments[-2] == "tests" and rust_re.fullmatch(segments[-1])
        if not (bench_re.fullmatch(segments[-1]) or rust):
            sys.exit(refuse("pas-un-banc", item, name))
        # A link loop (RuntimeError before 3.13), a name too long (OSError) or a
        # link leaving the root (ValueError) is an absent bench, never a crash.
        try:
            target = (root / path).resolve()
            target.relative_to(root)
            present = target.is_file()
        except (OSError, RuntimeError, ValueError):
            present = False
        if not present:
            sys.exit(refuse("absent", item, name))
    sys.exit(0)

root = Path(sys.argv[1]).resolve()
main()
' "$ROOT"
PY_RC=$?
# Any other exit (an uncaught exception, an interpreter that cannot start on
# its stdin) is a refusal (S-01M5YZ6VJN): exit 2, blocking bare and passed
# through by garde-fermee.
case "$PY_RC" in
  0|2) exit "$PY_RC" ;;
esac
echo "BLOCKED by hook: bancs-mandat: erreur interne, python sorti en rc $PY_RC — refus (S-01M5YZ6VJN)" >&2
exit 2
