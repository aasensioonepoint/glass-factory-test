#!/usr/bin/env bash
# session-reindex-exec.test.sh — T-00000117.
# Run: bash .agents/evals/session-reindex-exec.test.sh
#
# WHAT THIS PROVES, AND WHY IT IS NOT ALREADY PROVEN. `test_session_reindex.py`
# pins the SessionStart refresh by TEXT: the guard clause is present, the flags
# are the deterministic ones, the builder path is the kit's. A text net cannot
# tell you that the thing RUNS — it would stay green on a hook whose guard is
# intact and whose subprocess never fires. This suite executes the three hooks
# for real, against a tracer standing in for the builder, and observes what they
# did.
#
# TWO PROPERTIES, KEPT SEPARATE ON PURPOSE:
#   (a) a builder runs when it must   — fixture WITH SYMBOLS.md -> exactly one
#       traced invocation, carrying `--if-stale` and the expected root.
#   (b) none runs when it must not    — fresh fixture WITHOUT SYMBOLS.md -> the
#       trace file does not exist at all. An unindexed project never gets its
#       first full scan from a session hook; that stays an explicit decision.
#
# OBSERVATION IS BY FILE, NEVER BY STDOUT: all three hooks discard the builder's
# output (`>/dev/null 2>&1` on the bash side, `capture_output=True` on the two
# python ones), so a stdout-based probe would measure nothing.
#
# THE EXPECTED ROOT IS COMPARED PER HOOK FAMILY, because the two families do not
# hold the same invariant, and one shared rule would just move the defect from
# one arm to the other:
#   * python family (.codex, .gemini) — the hook resolves the root ITSELF, via
#     `_common.py` (git rev-parse then Path.resolve(), i.e. a native `C:\...`
#     form on Windows). The assertion therefore compares against what the COPIED
#     `_common.py` resolves for itself, asked at run time. Never the shell's idea
#     of the fixture path.
#   * bash family (.claude) — the hook resolves NOTHING; it passes
#     `$CLAUDE_PROJECT_DIR` through verbatim. Its invariant IS that pass-through,
#     so comparing its trace to a resolved root would be wrong in the other
#     direction. The fixture exports the root in native form first (`pwd -W`
#     under Git Bash) and the arm demands exactly that exported value back.
# Comparing either arm against the raw `mktemp` path would be a deterministic
# red on a Windows box, at night, with nobody watching (L-00000068).
#
# NON-VACUITY HAS FOUR SUPPORTS, and A1 is the one that matters:
#   A0  the tracer, invoked directly, writes its line — the instrument is alive.
#   (a) the hook->tracer wiring works under the very same invocation.
#   (b) the hook exits 0 AND emits a non-empty context, which proves it ran to
#       completion and CHOSE not to launch the builder, rather than dying before
#       the guard.
#   A1  MUTATION CONTROL: one hook of EACH family, copied with its SYMBOLS.md
#       clause removed, must make the trace APPEAR in the (b) fixture. Without
#       it, the `[ ! -e ]` assertion of (b) would never have been seen red, and a
#       suite whose assertion has never failed is exactly the instrument whose
#       vacuity is discovered the day the refresh breaks in silence.
#
# SKIPS ARE LOUD AND WHOLESALE. If `timeout(1)` is missing, BOTH bash arms skip —
# never just (a). Skipping (a) alone would be worse than skipping nothing: with
# no `timeout`, the bash guard short-circuits the builder EVEN with SYMBOLS.md
# present, so (b) would go green for the wrong reason.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PASS=0; FAIL=0; SKIP=0

ok()   { PASS=$((PASS+1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL: $1"; }
skip() { SKIP=$((SKIP+1)); echo "SKIP: $1"; }

PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then
  echo "SKIP: session-reindex-exec.test.sh needs python"; exit 0
fi
if ! command -v git >/dev/null 2>&1; then
  echo "SKIP: session-reindex-exec.test.sh needs git (the python hooks resolve their root with it)"; exit 0
fi
HAVE_TIMEOUT=0
command -v timeout >/dev/null 2>&1 && HAVE_TIMEOUT=1

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# The fixture. `git init` matters: the python hooks resolve their root with
# `git rev-parse` from the hook FILE's location, and a TMPDIR nested inside a
# real repository would otherwise resolve to that repository instead.
# ---------------------------------------------------------------------------
make_fixture() {   # make_fixture <dir> <with_symbols:0|1>
  local fx="$1" with="$2"
  mkdir -p "$fx/.agents/bin" "$fx/.agents/state/index" "$fx/.agents/state/board"
  # The tracer: appends its argv and exits 0. Four lines, no imports beyond sys.
  cat > "$fx/.agents/bin/build_index.py" <<'TRACER'
import sys, os
here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(here, "BUILDER_TRACE.log"), "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
TRACER
  # A planted CODEBASE_INDEX.md is what makes (b) able to prove the hook ran to
  # completion: its injected context must come back non-empty.
  printf '# fixture codebase index\n' > "$fx/.agents/state/index/CODEBASE_INDEX.md"
  printf '[]\n' > "$fx/.agents/state/board/TASKS.json"
  if [ "$with" = "1" ]; then
    printf '# fixture symbols\n' > "$fx/.agents/state/index/SYMBOLS.md"
  fi
  ( cd "$fx" && git init -q . && git add -A >/dev/null 2>&1 \
    && git -c user.name=t -c user.email=t@t commit -qm fixture >/dev/null 2>&1 ) || true
}

trace_lines() {  # trace_lines <fixture>
  [ -f "$1/BUILDER_TRACE.log" ] && wc -l < "$1/BUILDER_TRACE.log" | tr -d ' ' || echo 0
}

# ---------------------------------------------------------------------------
# A0 — the instrument is alive.
# ---------------------------------------------------------------------------
FX0="$WORK/a0"; make_fixture "$FX0" 1
"$PY" "$FX0/.agents/bin/build_index.py" --root "$FX0" --if-stale >/dev/null 2>&1
if [ "$(trace_lines "$FX0")" = "1" ]; then
  ok "(A0) the tracer records one invocation when called directly"
else
  bad "(A0) the tracer wrote nothing — every arm below would measure nothing"
fi
rm -f "$FX0/BUILDER_TRACE.log"

# ---------------------------------------------------------------------------
# BASH FAMILY — .claude/hooks/session-start.sh
# ---------------------------------------------------------------------------
if [ "$HAVE_TIMEOUT" = "0" ]; then
  skip "(a/bash) timeout(1) absent — BOTH bash arms skipped, never just one"
  skip "(b/bash) timeout(1) absent — the guard short-circuits, (b) would be green for the wrong reason"
else
  FXA="$WORK/bash-a"; make_fixture "$FXA" 1
  FXAW="$(cd "$FXA" && pwd -W 2>/dev/null || pwd)"
  OUT_A="$(printf '{}' | CLAUDE_PROJECT_DIR="$FXAW" bash "$ROOT/.claude/hooks/session-start.sh" 2>/dev/null)"
  RC_A=$?
  if [ "$RC_A" -eq 0 ] && [ -n "$OUT_A" ]; then
    ok "(a/bash) the hook ran to completion and injected a non-empty context"
  else
    bad "(a/bash) hook rc=$RC_A, context empty=$([ -z "$OUT_A" ] && echo yes || echo no)"
  fi
  if [ "$(trace_lines "$FXA")" = "1" ]; then
    ok "(a/bash) exactly ONE builder invocation was traced"
  else
    bad "(a/bash) expected 1 traced invocation, got $(trace_lines "$FXA")"
  fi
  # `--if-stale` is the deterministic form: a refresh that rebuilt unconditionally
  # would be a full scan on every session start.
  if grep -F -q -- "--if-stale" "$FXA/BUILDER_TRACE.log" 2>/dev/null; then
    ok "(a/bash) the invocation carries --if-stale"
  else
    bad "(a/bash) the traced invocation does not carry --if-stale"
  fi
  # The pass-through invariant: VERBATIM the value the fixture exported.
  if grep -F -q -- "$FXAW" "$FXA/BUILDER_TRACE.log" 2>/dev/null; then
    ok "(a/bash) the root is passed through VERBATIM as exported"
  else
    bad "(a/bash) expected the exported root <$FXAW> in the trace, got: $(cat "$FXA/BUILDER_TRACE.log" 2>/dev/null)"
  fi

  FXB="$WORK/bash-b"; make_fixture "$FXB" 0
  FXBW="$(cd "$FXB" && pwd -W 2>/dev/null || pwd)"
  OUT_B="$(printf '{}' | CLAUDE_PROJECT_DIR="$FXBW" bash "$ROOT/.claude/hooks/session-start.sh" 2>/dev/null)"
  RC_B=$?
  if [ ! -e "$FXB/BUILDER_TRACE.log" ]; then
    ok "(b/bash) no SYMBOLS.md -> the builder was NOT invoked at all"
  else
    bad "(b/bash) the builder ran on an unindexed repo: $(cat "$FXB/BUILDER_TRACE.log")"
  fi
  if [ "$RC_B" -eq 0 ] && [ -n "$OUT_B" ]; then
    ok "(b/bash) the hook still ran to completion — it CHOSE not to build"
  else
    bad "(b/bash) hook rc=$RC_B with empty context — it may have died before the guard"
  fi
fi

# ---------------------------------------------------------------------------
# PYTHON FAMILY — .codex and .gemini, same shape, twin assertions.
# ---------------------------------------------------------------------------
run_python_family() {  # run_python_family <host-dir>
  local host="$1"
  local src="$ROOT/$host/hooks"
  if [ ! -f "$src/session_context.py" ] || [ ! -f "$src/_common.py" ]; then
    skip "($host) session_context.py or _common.py absent"
    return
  fi

  local fxa="$WORK/$host-a"; make_fixture "$fxa" 1
  mkdir -p "$fxa/$host/hooks"
  cp "$src/session_context.py" "$src/_common.py" "$fxa/$host/hooks/"
  local out rc traced expected
  out="$(cd "$fxa" && AGENTS_EVENTS_DIR="$fxa/scratch-events" "$PY" "$fxa/$host/hooks/session_context.py" < /dev/null 2>/dev/null)"
  rc=$?
  if [ "$rc" -eq 0 ] && [ -n "$out" ]; then
    ok "(a/$host) the hook ran to completion and injected a non-empty context"
  else
    bad "(a/$host) hook rc=$rc, context empty=$([ -z "$out" ] && echo yes || echo no)"
  fi
  traced="$(trace_lines "$fxa")"
  if [ "$traced" = "1" ]; then
    ok "(a/$host) exactly ONE builder invocation was traced"
  else
    bad "(a/$host) expected 1 traced invocation, got $traced"
  fi
  if grep -F -q -- "--if-stale" "$fxa/BUILDER_TRACE.log" 2>/dev/null; then
    ok "(a/$host) the invocation carries --if-stale"
  else
    bad "(a/$host) the traced invocation does not carry --if-stale"
  fi
  # THE ROOT IS ASKED OF THE COPIED _common.py ITSELF — never guessed from the
  # shell's path form. This is the whole point of splitting the rule by family.
  expected="$(cd "$fxa/$host/hooks" && "$PY" -c "import sys; sys.path.insert(0, '.'); from _common import ROOT; print(ROOT)" 2>/dev/null)"
  if [ -z "$expected" ]; then
    bad "(a/$host) could not ask the copied _common.py for its own ROOT"
  elif grep -F -q -- "$expected" "$fxa/BUILDER_TRACE.log" 2>/dev/null; then
    ok "(a/$host) the traced root is the one _common.py resolves for itself"
  else
    bad "(a/$host) expected root <$expected>, trace: $(cat "$fxa/BUILDER_TRACE.log" 2>/dev/null)"
  fi

  local fxb="$WORK/$host-b"; make_fixture "$fxb" 0
  mkdir -p "$fxb/$host/hooks"
  cp "$src/session_context.py" "$src/_common.py" "$fxb/$host/hooks/"
  out="$(cd "$fxb" && AGENTS_EVENTS_DIR="$fxb/scratch-events" "$PY" "$fxb/$host/hooks/session_context.py" < /dev/null 2>/dev/null)"
  rc=$?
  if [ ! -e "$fxb/BUILDER_TRACE.log" ]; then
    ok "(b/$host) no SYMBOLS.md -> the builder was NOT invoked at all"
  else
    bad "(b/$host) the builder ran on an unindexed repo: $(cat "$fxb/BUILDER_TRACE.log")"
  fi
  if [ "$rc" -eq 0 ] && [ -n "$out" ]; then
    ok "(b/$host) the hook still ran to completion — it CHOSE not to build"
  else
    bad "(b/$host) hook rc=$rc with empty context — it may have died before the guard"
  fi
}

run_python_family ".codex"
run_python_family ".gemini"

# ---------------------------------------------------------------------------
# A1 — MUTATION CONTROL, one hook per family. This is what makes every `[ ! -e ]`
# above mean something: with the SYMBOLS.md clause removed, the trace MUST
# appear in the very fixture where (b) demanded its absence.
# ---------------------------------------------------------------------------
FXM="$WORK/mutants"; make_fixture "$FXM" 0

if [ "$HAVE_TIMEOUT" = "0" ]; then
  skip "(A1/bash) timeout(1) absent — the mutant could not run the builder either"
else
  MUT_SH="$WORK/session-start.mutant.sh"
  sed 's/ && \[ -f "\$STATE\/index\/SYMBOLS.md" \]//' "$ROOT/.claude/hooks/session-start.sh" > "$MUT_SH"
  if grep -F -q 'SYMBOLS.md" ]' "$MUT_SH"; then
    bad "(A1/bash) the mutation did not remove the SYMBOLS.md clause — the control is vacuous"
  else
    FXMW="$(cd "$FXM" && pwd -W 2>/dev/null || pwd)"
    printf '{}' | CLAUDE_PROJECT_DIR="$FXMW" bash "$MUT_SH" >/dev/null 2>&1
    if [ -e "$FXM/BUILDER_TRACE.log" ]; then
      ok "(A1/bash) guard removed -> the builder DOES run, so (b/bash) can fail"
    else
      bad "(A1/bash) guard removed and still no invocation — (b/bash) proves nothing"
    fi
    rm -f "$FXM/BUILDER_TRACE.log"
  fi
fi

MUT_HOST=".codex"
if [ -f "$ROOT/$MUT_HOST/hooks/session_context.py" ]; then
  mkdir -p "$FXM/$MUT_HOST/hooks"
  cp "$ROOT/$MUT_HOST/hooks/_common.py" "$FXM/$MUT_HOST/hooks/"
  sed 's/ and (INDEX \/ "SYMBOLS.md").exists()//' \
      "$ROOT/$MUT_HOST/hooks/session_context.py" > "$FXM/$MUT_HOST/hooks/session_context.py"
  if grep -F -q 'SYMBOLS.md").exists()' "$FXM/$MUT_HOST/hooks/session_context.py"; then
    bad "(A1/$MUT_HOST) the mutation did not remove the SYMBOLS.md clause — the control is vacuous"
  else
    ( cd "$FXM" && AGENTS_EVENTS_DIR="$FXM/scratch-events" \
      "$PY" "$FXM/$MUT_HOST/hooks/session_context.py" < /dev/null >/dev/null 2>&1 )
    if [ -e "$FXM/BUILDER_TRACE.log" ]; then
      ok "(A1/$MUT_HOST) guard removed -> the builder DOES run, so (b/python) can fail"
    else
      bad "(A1/$MUT_HOST) guard removed and still no invocation — (b/python) proves nothing"
    fi
  fi
else
  skip "(A1/$MUT_HOST) hook absent"
fi

echo "----------------------------------------"
echo "session-reindex-exec.test.sh: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
