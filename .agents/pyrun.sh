#!/usr/bin/env bash
# .agents/pyrun.sh — run a python script with the kit's interpreter resolver.
# Usage: bash .agents/pyrun.sh <script.py> [args...]   (also: -c "code")
# Why: bare `python3` can be a Microsoft Store alias on Windows, while
# `python` often does not exist on Linux/macOS. Probe Python 3 without reading
# hook stdin, then exec the resolved interpreter exactly once.

set -uo pipefail

probe_python3() {
  _candidate=$1
  shift
  _resolved=$("$_candidate" "$@" -c 'import sys; sys.exit(1) if sys.version_info[0] != 3 else None; sys.stdout.write(sys.executable)' </dev/null 2>/dev/null) || return 1
  [ -n "$_resolved" ] || return 1
  [ -f "$_resolved" ] || return 1
  [ -x "$_resolved" ] || return 1
  printf '%s\n' "$_resolved"
}

_python=''
for _candidate in python3 python; do
  if _resolved=$(probe_python3 "$_candidate"); then
    _python=$_resolved
    break
  fi
done

if [ -z "$_python" ]; then
  _uname=""
  command -v uname >/dev/null 2>&1 && _uname="$(uname -s 2>/dev/null || true)"
  case "${OS-}:$_uname" in
    Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
      if _resolved=$(probe_python3 py -3); then
        _python=$_resolved
      fi
      ;;
  esac
fi

if [ -z "$_python" ]; then
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  exit 127
fi

# T-00001191: no .pyc from a hook. The exported env reaches descendants (sys.executable);
# -B holds even when the caller passes -E or -I in "$@".
export PYTHONDONTWRITEBYTECODE=1
exec "$_python" -B "$@"
