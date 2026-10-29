#!/usr/bin/env bash
# PostToolUse [Edit|Write] — quick lint/typecheck feedback. Never blocks (exit 0 always).
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
FILE=""
[ -n "$PY" ] && FILE=$(printf '%s' "$INPUT" | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)
[ -z "$FILE" ] && exit 0
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
OUT=""
case "$FILE" in
  *.ts|*.tsx) command -v npx >/dev/null && OUT=$(npx --no-install tsc --noEmit 2>&1 | head -5);;
  *.py)       [ -n "$PY" ] && OUT=$("$PY" -m py_compile "$FILE" 2>&1 | head -5);;
  *.rs)       command -v cargo >/dev/null && OUT=$(cargo check -q 2>&1 | head -5);;
  *.go)       command -v go >/dev/null && OUT=$(go vet ./... 2>&1 | head -5);;
esac
if [ -n "$OUT" ]; then
  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/emit-event.sh" hook.check_fail guard=post-edit-check "rule=${FILE##*.}" "path=$FILE" >/dev/null 2>&1 || true
  printf '{"systemMessage": "post-edit check found issues in %s — see next tool output or run the check manually."}' "$FILE"
fi
exit 0
