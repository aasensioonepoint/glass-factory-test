#!/usr/bin/env bash
# PreCompact — back up the transcript before compaction so nothing is lost.
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
[ -n "$PY" ] || echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
TP=""
[ -n "$PY" ] && TP=$(printf '%s' "$INPUT" | "$PY" -c "import sys,json;print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" session.compact trigger=pre >/dev/null 2>&1 || true
DEST="$CLAUDE_PROJECT_DIR/.claude/backups"
mkdir -p "$DEST"
[ -f "$TP" ] && cp "$TP" "$DEST/pre-compact-$(date +%Y%m%d-%H%M%S).jsonl"
# Keep only the 10 most recent backups
ls -t "$DEST"/pre-compact-*.jsonl 2>/dev/null | tail -n +11 | xargs -r rm -f
exit 0
