#!/usr/bin/env bash
# Tests for semgrep-scan.sh (class-1 SAST input for security-code-review).
# Run: bash .agents/security/semgrep-scan.test.sh — also auto-discovered by
# core-scripts/run-bash-tests.sh. Cases (a) and (b) SKIP cleanly when semgrep is
# not installed (as gitleaks-scan.test.sh does without gitleaks); cases (c)
# and (d) run ALWAYS, including on the semgrep-less CI runner — so this suite
# is green in CI.
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# allows-missing: bash rm
#
# Case (c) NARROWS PATH DOWN TO A STUB ON PURPOSE (:204) to hide semgrep from the
# script under test and prove it degrades instead of blocking. Inside that narrow
# PATH the script reaches for commands the stub does not link — real 127s,
# deliberately caused, by a suite that passes — and each of them is either LINKED
# by the stub or DECLARED above, never left to chance. ONE criterion decides
# which: LINKED is what a DECISION of the script depends on (a measurement);
# DECLARED is what has only an EFFECT nothing branches on.
#
#   `bash` (telemetry) and `rm` (cleanup) are EFFECTS: absent, the run is poorer
#   and no verdict moves. They are declared, and the names are the ones MEASURED,
#   not a blanket. Case (c) itself now LINKS `rm` (arm sv2 asserts the removal
#   of the stale common verdict), and so do the hook arms' narrowed PATHs
#   (`absent`, `nopython` — closing review 2, F5: without it the hook's cleanup
#   `rm -f` failed and left its three payload files `.semgrep-hk-{pl,dir,cnd}.*`
#   in the caller's TMPDIR at each such run, measured 3 per run, 0 once linked).
#   `rm` stays DECLARED all the same, by the criterion above: it is an EFFECT,
#   and linking it stops the leak, it does not make a verdict depend on it.
#
#   `wc` is a MEASUREMENT, so the stub links it. It is the only unlinked input of
#   head_is_merge (semgrep-scan.sh:446, `git rev-list --parents -n 1 HEAD | wc
#   -w` — its other input, git, is linked already). On a tree with no upstream —
#   a detached clone, a fresh adopting checkout — resolve_base returns
#   INDETECTABLE and this predicate is the last disjunct before the refusal
#   "HEAD is a MERGE and no base is knowable". Take `wc` away and that predicate
#   is LOUD ON STDERR (`wc: command not found`, then `[: : integer expression
#   expected`) yet MUTE IN THE VERDICT: `set -uo pipefail` carries no `-e`
#   (semgrep-scan.sh:52) and `[ "" -gt 2 ]` exits 2, so the predicate answers
#   FALSE WHATEVER THE PARENT COUNT and the refusal becomes unreachable.
#   Declaring it missing would pin that blind guard down as intended; linking it
#   keeps the guard able to measure.
#
#   `tr` is a MEASUREMENT too, so every narrowed PATH links it: arbres_absents
#   lists the sparse-index entries through `ls-files --sparse -s -z | tr '\0'
#   '\n'`. Unlinked in case (c), the runner's sensor named it (`Missing
#   dependency (cmd: tr)`) and the gate said a FALSE loss — `sparse-index check
#   failed, git rc 127` — measured on 6f6700b0 and after, gone once linked.
#
# Without the declaration above, the runner's swallowed-127 sensor would turn the
# most careful degradation test in the repo red for doing its job. A future
# command escaping the stub should surface as a named red here, and be linked or
# declared on the same criterion — never absorbed unnamed.
#
# (a)/(b) spin up a throwaway git repo (mktemp -d + git init) per case instead
# of scanning THIS repo's live working-tree diff: semgrep-scan.sh scans
# whatever is currently changed/untracked, and this task's own changeset would
# otherwise leak into the "clean file" assertion. The isolated repo makes each
# case deterministic regardless of what else is in flight in the real repo.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/semgrep-scan.sh"
# SUITE_BASH — the interpreter this suite RESOLVES its runs onto. `${BASH:-…}`
# so `/bin/bash semgrep-scan.test.sh` makes the SCRIPT (and the stubs) run under
# /bin/bash 3.2, not the developer's PATH bash (T-00000477 S2.3): a suite that
# resolves its interpreter by PATH measures the developer's bash, never the one
# that travels. Every `"$SUITE_BASH" "$SCRIPT"` and every stub shebang routes here.
SUITE_BASH="${BASH:-$(command -v bash)}"
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
CFG="$REAL_ROOT/.agents/security/semgrep.yml"
[ -f "$SCRIPT" ] || { echo "FAIL: semgrep-scan.sh not found"; exit 1; }
[ -f "$CFG" ]    || { echo "FAIL: semgrep.yml not found"; exit 1; }

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

# assert_tmpdir — REFUSE a throwaway dir that is empty, equal to the repo/cwd,
# or outside the temp root, BEFORE any `git -C "$dir"` runs on it. An empty
# `$dir` makes `git -C "" init/commit` operate in the CURRENT directory — i.e.
# this live kit repo — which is how a throwaway "init" commit can sweep in-flight
# work across tasks. Same lesson as T-00000303 (a mass operation must refuse the
# input it would corrupt), applied here to the harness itself: fail loudly, never
# a silent fallback into the real tree.
assert_tmpdir() {  # $1 = candidate throwaway dir
  [ -n "$1" ]              || fail "throwaway dir is EMPTY — refusing (git -C '' would hit the live repo)"
  [ "$1" != "$PWD" ]       || fail "throwaway dir == PWD ($1) — refusing"
  [ "$1" != "$REAL_ROOT" ] || fail "throwaway dir == repo root ($1) — refusing"
  case "$1" in
    /tmp/*|/var/folders/*|/private/var/folders/*) : ;;
    *)
      # macOS $TMPDIR ends with a trailing slash (/var/folders/.../T/), so the
      # bare "$TMPDIR"/* pattern doubled the slash and never matched mktemp's
      # output beneath it — normalise the root before comparing.
      _tmproot="${TMPDIR:-/tmp}"; _tmproot="${_tmproot%/}"
      case "$1" in
        "$_tmproot"/*) : ;;
        *) fail "throwaway dir outside temp ($1) — refusing" ;;
      esac ;;
  esac
}

# ---- THE SUITE NEVER RUNS IN THE CALLER'S TREE (T-01M4X9PP7FED0570PMPSYGA0V8) --
# Arms (q), (q2), (t), (u), (v) and (h7) launch the script in the CURRENT
# directory, and the script writes `.agents/state/local/sca-reports/`
# (audit-log.jsonl, semgrep-verdict.json) under the git toplevel it finds THERE:
# measured by the exec-critic, run from the kit's root the suite rewrote the
# kit's own common verdict and audit journal. So before its first run the suite
# moves into a throwaway repo — one commit, `state/local/` ignored, so `--at
# HEAD` and `--since HEAD` still resolve — and removes it at the end. Every other
# path of the suite is absolute (HERE, SCRIPT, REAL_ROOT are resolved above).
SUITE_CWD="$(mktemp -d)"
assert_tmpdir "$SUITE_CWD"
git -C "$SUITE_CWD" init -q
mkdir -p "$SUITE_CWD/.agents"
printf 'state/local/\n' > "$SUITE_CWD/.agents/.gitignore"
git -C "$SUITE_CWD" add -A >/dev/null 2>&1
git -C "$SUITE_CWD" -c user.email="test@test.local" -c user.name="test" -c commit.gpgsign=false \
  commit -qm init >/dev/null 2>&1
git -C "$SUITE_CWD" rev-parse --verify --quiet HEAD >/dev/null 2>&1 \
  || fail "throwaway cwd $SUITE_CWD has no commit — the cwd arms would measure another branch"
cd "$SUITE_CWD" || fail "cannot enter the throwaway cwd $SUITE_CWD"

HAVE_SEMGREP=0; command -v semgrep >/dev/null 2>&1 && HAVE_SEMGREP=1
PY=""; for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done

# Build an isolated single-commit git repo under mktemp, with ONE untracked
# fixture file, then run semgrep-scan.sh with that repo as cwd (its own
# `git rev-parse --show-toplevel` resolves to the throwaway repo, not this one).
run_isolated() {  # $1 fixture-filename  $2 fixture-content(stdin)
  local dir; dir="$(mktemp -d)"
  assert_tmpdir "$dir"
  git -C "$dir" init -q
  git -C "$dir" -c user.email="test@test.local" -c user.name="test" \
    commit -q --allow-empty -m init
  cat > "$dir/$1"
  ( cd "$dir" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" ) >"$dir/.out" 2>&1
  local rc=$?
  cat "$dir/.out"
  rm -rf "$dir"
  return $rc
}

# run_isolated_path — like run_isolated, but INTERPOSES a parameterised semgrep
# stub on a narrowed PATH (case (c)'s farm inverted: (c) HID a tool from the
# script; here we interpose one). The throwaway repo carries ONE untracked
# fixture so the scan reaches the semgrep call — an empty tree exits at "nothing
# to scan" upstream of the invocation, and the stub would never be reached.
#   $1 stub-mode: argv|sleep|empty|invalid|scanned-empty|finding   $2 fixture-filename
#   stdin: fixture-content
# Optional caller env (forwarded): STUB_ARGV_OUT (argv sink, kept OUTSIDE the
# throwaway so it survives cleanup), STUB_SLEEP, SEMGREP_TIMEOUT, STUB_FINDINGS,
# STUB_RULE (check_id of every `finding` result; default stub.rule.<i>),
# STUB_RC (the stub's exit code; default 0).
# Optional caller env (read here, arms sv*): RUN_SCRIPT (the script to run,
# default $SCRIPT — a throwaway COPY), RUN_SENTINEL=1 (plant a stale verdict
# before the run), RUN_KEEP_VERDICT (file OUTSIDE the throwaway that receives
# the run's verdict, if any, before cleanup), RUN_RELATIVE=1 (copy the script
# and scan_verdict.py INTO the throwaway's .agents/security/ and launch it by a
# RELATIVE path from a subdirectory, `cd sub && bash ../.agents/security/…`).
run_isolated_path() {
  local mode="$1" fixture="$2"
  local dir; dir="$(mktemp -d)"
  assert_tmpdir "$dir"
  git -C "$dir" init -q
  git -C "$dir" -c user.email="test@test.local" -c user.name="test" \
    commit -q --allow-empty -m init
  cat > "$dir/$fixture"
  local verdict="$dir/.agents/state/local/sca-reports/semgrep-verdict.json"
  if [ "${RUN_SENTINEL:-0}" = "1" ]; then
    mkdir -p "${verdict%/*}"
    printf '{"sentinelle":"stale"}\n' > "$verdict"
  fi
  local script="${RUN_SCRIPT:-$SCRIPT}" rundir="$dir"
  if [ "${RUN_RELATIVE:-0}" = "1" ]; then
    mkdir -p "$dir/.agents/security" "$dir/sub"
    cp "$SCRIPT" "$dir/.agents/security/semgrep-scan.sh"
    cp "$HERE/scan_verdict.py" "$dir/.agents/security/scan_verdict.py"
    script="../.agents/security/semgrep-scan.sh"; rundir="$dir/sub"
  fi

  # The stub is PREPENDED to the real PATH, not a replacement: only `semgrep`
  # is shadowed (the stub is first), while every real tool — git, mkdir, date,
  # timeout, sleep — resolves from its normal location with its co-located
  # runtime DLLs intact. A full PATH replacement (case (c)'s technique, right
  # THERE because it must HIDE semgrep) breaks symlinked coreutils on Windows
  # Git Bash with "error while loading shared libraries"; interposition does
  # not need to hide anything, so prepending is both correct and simpler.
  local STUB; STUB="$(mktemp -d)"
  assert_tmpdir "$STUB"
  local REAL_BASH; REAL_BASH="$SUITE_BASH"
  {
    printf '#!%s\n' "$REAL_BASH"
    cat <<'STUBEOF'
# parameterised semgrep stub: behaviour by $STUB_MODE, argv sink by $STUB_ARGV_OUT
[ -n "${STUB_ARGV_OUT:-}" ] && printf '%s\n' "$*" > "$STUB_ARGV_OUT"
case "${STUB_MODE:-empty}" in
  argv)          echo '{"results":[],"paths":{"scanned":["x"]}}' ;;
  sleep)         sleep "${STUB_SLEEP:-30}" ;;
  empty)         : ;;                                   # no output => empty report
  invalid)       echo 'this is { not valid json' ;;
  scanned-empty) echo '{"results":[],"paths":{"scanned":[]}}' ;;
  finding)       # $STUB_FINDINGS distinct findings on the LAST scanned file
                 _f=""; _dd=0
                 for _a in "$@"; do [ "$_dd" = 1 ] && _f="$_a"; [ "$_a" = "--" ] && _dd=1; done
                 [ -n "$_f" ] || _f="x"
                 _n="${STUB_FINDINGS:-1}"; _i=1; _res=""
                 while [ "$_i" -le "$_n" ]; do
                   [ "$_i" -gt 1 ] && _res="$_res,"
                   _id="stub.rule.$_i"; [ -n "${STUB_RULE:-}" ] && _id="$STUB_RULE"
                   _res="$_res{\"check_id\":\"$_id\",\"path\":\"$_f\",\"start\":{\"line\":$_i},\"extra\":{\"severity\":\"ERROR\"}}"
                   _i=$((_i + 1))
                 done
                 printf '{"results":[%s],"paths":{"scanned":["%s"]}}\n' "$_res" "$_f" ;;
esac
exit "${STUB_RC:-0}"
STUBEOF
  } > "$STUB/semgrep"
  chmod +x "$STUB/semgrep"

  ( cd "$rundir" && PATH="$STUB:$PATH" STUB_MODE="$mode" \
      STUB_ARGV_OUT="${STUB_ARGV_OUT:-}" STUB_SLEEP="${STUB_SLEEP:-30}" \
      STUB_FINDINGS="${STUB_FINDINGS:-1}" \
      STUB_RULE="${STUB_RULE:-}" STUB_RC="${STUB_RC:-0}" \
      SEMGREP_TIMEOUT="${SEMGREP_TIMEOUT:-180}" \
      SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$script" ) >"$dir/.out" 2>&1
  local rc=$?
  cat "$dir/.out"
  if [ -n "${RUN_KEEP_VERDICT:-}" ]; then
    rm -f "$RUN_KEEP_VERDICT"
    [ -f "$verdict" ] && cp "$verdict" "$RUN_KEEP_VERDICT"
  fi
  rm -rf "$STUB" "$dir"
  return $rc
}

# --- (a) obvious sink (MD5) => exit 1 (SKIP if no semgrep) --------------------
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  OUT_A="$(run_isolated "sink.py" <<'PYEOF'
import hashlib

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()
PYEOF
)"
  rc=$?
  [ "$rc" -eq 1 ] || fail "(a) obvious sink should exit 1, got $rc — output: $OUT_A"
  ok "(a) file with an obvious sink => exit 1 (FINDINGS)"
else
  echo "  SKIP (a): semgrep not installed"
fi

# --- (b) clean file => exit 0 (SKIP if no semgrep) ----------------------------
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  OUT_B="$(run_isolated "clean.py" <<'PYEOF'
def add(a, b):
    return a + b
PYEOF
)"
  rc=$?
  [ "$rc" -eq 0 ] || fail "(b) clean file should exit 0, got $rc — output: $OUT_B"
  ok "(b) clean file => exit 0 (CLEAN)"
else
  echo "  SKIP (b): semgrep not installed"
fi

# --- (c) semgrep absent => exit 0 + COVERAGE DEGRADED (ALWAYS runs) ----------
# When semgrep is genuinely absent (this dev box + the CI runner), the plain
# run already IS the degraded path. When installed, hide it behind a minimal
# PATH stub (same technique as gitleaks-scan.test.sh case c) — but resolve the
# REAL bash binary FIRST and invoke that absolute path directly. On Windows
# Git Bash/MSYS2 a symlinked bash/sh loses its co-located runtime DLLs when
# re-resolved through a narrowed PATH ("error while loading shared libraries"),
# so `PATH="$STUB" bash ...` would launch a broken interpreter; invoking the
# original bash by absolute path sidesteps that while still narrowing PATH for
# the SCRIPT's own internal tool lookups (which is what must hide semgrep).
# The run happens in a THROWAWAY repo (C5, T-01M4W80Q5C3F6G99G0JXJB3RH4): run in
# the live repo it would delete the live common verdict on every pass. That
# repo carries a stale verdict (arm sv2), so the stub also LINKS `rm`: sv2
# asserts the effect of the script's removal, and an effect the suite asserts
# is never left to a missing tool (`rm` stays declared above, as an EFFECT; the
# hook arms link it too). It links `tr` as well, a MEASUREMENT (header above).
C_REPO="$(mktemp -d)"; assert_tmpdir "$C_REPO"
git -C "$C_REPO" init -q
git -C "$C_REPO" -c user.email="test@test.local" -c user.name="test" commit -q --allow-empty -m init
printf 'x = 1\n' > "$C_REPO/probe.py"
C_VERDICT="$C_REPO/.agents/state/local/sca-reports/semgrep-verdict.json"
mkdir -p "${C_VERDICT%/*}"
printf '{"sentinelle":"stale"}\n' > "$C_VERDICT"
if [ "$HAVE_SEMGREP" -eq 0 ]; then
  DEG="$(cd "$C_REPO" && "$SUITE_BASH" "$SCRIPT" 2>&1)"; rc=$?
else
  REAL_BASH="$SUITE_BASH"
  STUB="$(mktemp -d)"
  for tool in env cat git python python3 py mktemp date printf grep dirname sort mkdir sed wc rm tr; do
    p="$(command -v "$tool" 2>/dev/null)" && ln -s "$p" "$STUB/$tool" 2>/dev/null
  done
  DEG="$(cd "$C_REPO" && PATH="$STUB" "$REAL_BASH" "$SCRIPT" 2>&1)"; rc=$?
  rm -rf "$STUB"
fi
[ "$rc" -eq 0 ] || fail "(c) no semgrep must exit 0 (never a false block), got $rc"
printf '%s' "$DEG" | grep -q "COVERAGE DEGRADED" \
  || fail "(c) no semgrep must print COVERAGE DEGRADED, got: $DEG"
ok "(c) semgrep absent => exit 0 + COVERAGE DEGRADED"
# --- (sv2) an exit BEFORE the scan (semgrep absent) leaves NO common verdict:
# the stale one is removed, never left readable as this run's.
[ -e "$C_VERDICT" ] && fail "(sv2) semgrep absent: the stale semgrep-verdict.json must be REMOVED, it is still there: $(cat "$C_VERDICT")"
printf '%s' "$DEG" | grep -q 'verdict commun non rendu' \
  && fail "(sv2) an exit before the scan must not announce a verdict call, got: $DEG"
rm -rf "$C_REPO"
ok "(sv2) semgrep absent => the stale common verdict is removed, no verdict call"

# --- (d) class-1 findings are handled by this script with NO waiver logic ---
# (waivers are a dependency-class-2/3 concept; SAST findings on produced code
# are never waivable per AGENTS.md § Security gate) — zero reference (ALWAYS runs)
if grep -Eiq 'waiver|sca-waivers' "$SCRIPT"; then
  fail "(d) semgrep-scan.sh must NOT reference waiver/sca-waivers (class-1 code findings are non-waivable)"
fi
ok "(d) no waiver/sca-waivers reference in semgrep-scan.sh"

# --- (e) cleanup() EXIT trap guard: only the owning shell may delete (ALWAYS) --
# T-00000149: a background child that inherits the EXIT trap and is killed before
# it finishes exec'ing fires cleanup() too. Without the BASHPID owner guard it
# would rm -f this run's report while the parent is still scanning. Extract the
# REAL cleanup() from the script (not a copy that could drift) and exercise both
# branches: a subshell whose BASHPID != CLEANUP_OWNER must early-return and leave
# the file; the owning shell must still clean. Asserts the observable effect (file
# present / gone), never an exit code (L-00000161).
# nosemgrep: agents.security.shell-eval-on-interpolated-value — TRUE positive of
# the pattern, INTENTIONAL here and bounded: the value is a function body cut out
# of a repo-tracked script by a fixed sed range, at test time, so that cleanup()
# can be exercised in isolation without running the whole scanner. The input is
# not attacker-controlled in any threat model where the repo itself is trusted —
# and anyone who can edit $SCRIPT already owns the gate (see §7.4, frontière de
# menace). Annotated rather than silenced: an exception that is not written down
# is indistinguishable from a rule that never fired.
# nosemgrep: agents.security.shell-eval-on-interpolated-value
eval "$(sed -n '/^cleanup()/,/^}/p' "$SCRIPT")"
declare -f cleanup >/dev/null || fail "(e) cleanup extraction empty"
# Initialize every var the extracted body reads (suite runs set -u).
REPORT="$(mktemp)"; LOCFILE=""; UNPARSED=""   # T-00000370 added UNPARSED to cleanup()
CLEANUP_OWNER="not-a-real-pid"          # forces the guard's early return in the subshell
( cleanup )                             # subshell BASHPID != CLEANUP_OWNER => must no-op
[ -f "$REPORT" ] || fail "(e) guard must early-return in a non-owner subshell (REPORT was deleted)"
CLEANUP_OWNER="${BASHPID:-$$}"          # this shell now owns the trap
cleanup                                 # normal path must still clean up
[ -f "$REPORT" ] && fail "(e) owner cleanup must remove REPORT, but it still exists"
ok "(e) cleanup() runs only in the owning shell (BASHPID guard)"

# --- (f) NON-VACUITY: a trapped workflow reddens EVERY added rule; R1 by TWO
# distinct locations (run: AND script:); the SAFE env: indirection is a NEGATIVE
# control asserted ABSENT. Expected lines are DERIVED from the template, never
# hardcoded (L-00000057). SKIP if semgrep (hence Python) is absent.
if [ "$HAVE_SEMGREP" -eq 1 ] && [ -n "$PY" ]; then
  d="$(mktemp -d)"
  assert_tmpdir "$d"
  git -C "$d" init -q
  git -C "$d" -c user.email="test@test.local" -c user.name="test" commit -q --allow-empty -m init
  mkdir -p "$d/.github/workflows"
  wf="$d/.github/workflows/evil.yml"
  cat > "$wf" <<'YAMLEOF'
name: trapped
on:
  pull_request_target:
    types: [opened]
jobs:
  danger:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - name: inject-run
        run: echo "PR title is ${{ github.event.pull_request.title }}"
      - name: inject-script
        uses: actions/github-script@v7
        with:
          script: console.log("${{ github.event.pull_request.body }}")
      - name: safe-indirection
        env:
          TITLE: ${{ github.event.pull_request.title }}
        run: echo "$TITLE"
YAMLEOF
  fjson="$(mktemp)"
  ( cd "$d" && semgrep --config "$CFG" --json --quiet --disable-version-check --metrics=off \
      -- .github/workflows/evil.yml ) > "$fjson" 2>/dev/null
  # lines DERIVED from the template (never hardcoded): the content greps land on
  # the same line as the run:/script:/TITLE: key semgrep anchors its match to.
  run_line="$(grep -n 'PR title is' "$wf" | head -1 | cut -d: -f1)"
  script_line="$(grep -n 'console.log' "$wf" | head -1 | cut -d: -f1)"
  env_line="$(grep -n 'TITLE:' "$wf" | head -1 | cut -d: -f1)"
  "$PY" - "$fjson" "$run_line" "$script_line" "$env_line" <<'PYEOF' \
    || fail "(f) rule/location/negative-control assertion failed (detail on stderr above)"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
run_line, script_line, env_line = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
res = data.get("results", [])
def lines(sub): return sorted({r["start"]["line"] for r in res if sub in r["check_id"]})
r1, r2, r3 = lines("expression-injection"), lines("pull-request-target"), lines("job-level-write")
alllines = sorted({r["start"]["line"] for r in res})
errs = []
if run_line not in r1:    errs.append(f"R1 missing run: line {run_line} (got {r1})")
if script_line not in r1: errs.append(f"R1 missing script: line {script_line} (got {r1})")
if len(r1) < 2:           errs.append(f"R1 must be represented by TWO locations (got {r1})")
if not r2:                errs.append("R2 (pull_request_target) not represented")
if not r3:                errs.append("R3 (job-level write) not represented")
if env_line in alllines:  errs.append(f"NEG control failed: safe env: line {env_line} reddened (findings {alllines})")
if errs:
    sys.stderr.write("(f) FAIL: " + " | ".join(errs) + "\n"); sys.exit(1)
sys.exit(0)
PYEOF
  # exit-1 through the SCRIPT itself on the same trap (findings => rc 1)
  ( cd "$d" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" ) >"$d/.script.out" 2>&1; src=$?
  [ "$src" -eq 1 ] || fail "(f) trapped workflow must drive semgrep-scan.sh to exit 1, got $src — $(cat "$d/.script.out")"
  rm -rf "$d" "$fjson"
  ok "(f) trapped workflow: R1(×2 run:+script:), R2, R3 all red; safe env: indirection absent; script exits 1"
else
  echo "  SKIP (f): semgrep or Python not installed"
fi

# --- (g) NULL SCOPE: paths.scanned:[] => announce + DEGRADED + never "clean".
# CI-safe (uses the stub, no real semgrep); needs Python to read paths.scanned.
if [ -n "$PY" ]; then
  OUT_G="$(run_isolated_path scanned-empty "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 0 ] || fail "(g) null scope must exit 0 (never a false block), got $rc — output: $OUT_G"
  printf '%s' "$OUT_G" | grep -q 'COVERAGE DEGRADED' || fail "(g) null scope must be COVERAGE DEGRADED, got: $OUT_G"
  printf '%s' "$OUT_G" | grep -q 'cible inspectée'  || fail "(g) null scope must announce '0 cible inspectée sur N', got: $OUT_G"
  printf '%s' "$OUT_G" | grep -qi 'clean' && fail "(g) null scope must NEVER print 'clean': $OUT_G"
  ok "(g) paths.scanned:[] => annonce + DEGRADED + never 'clean'"
else
  echo "  SKIP (g): no Python interpreter to parse paths.scanned"
fi

# --- (h) DEFECTIVE REPORT => DEGRADED + never "clean". Empty output is
# UNCONDITIONAL (pure `-s` shell); invalid JSON needs a parser (SKIP announced).
OUT_H1="$(run_isolated_path empty "probe.py" <<'EOF'
x = 1
EOF
)"
rc=$?
[ "$rc" -eq 0 ] || fail "(h) empty report must exit 0, got $rc — output: $OUT_H1"
printf '%s' "$OUT_H1" | grep -q 'COVERAGE DEGRADED' || fail "(h) empty report must be DEGRADED, got: $OUT_H1"
printf '%s' "$OUT_H1" | grep -qi 'clean' && fail "(h) empty report must NEVER print 'clean': $OUT_H1"
if [ -n "$PY" ]; then
  OUT_H2="$(run_isolated_path invalid "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 0 ] || fail "(h) invalid JSON must exit 0, got $rc — output: $OUT_H2"
  printf '%s' "$OUT_H2" | grep -q 'COVERAGE DEGRADED' || fail "(h) invalid JSON must be DEGRADED, got: $OUT_H2"
  printf '%s' "$OUT_H2" | grep -qi 'clean' && fail "(h) invalid JSON must NEVER print 'clean': $OUT_H2"
  ok "(h) empty (unconditional) + invalid JSON (Python) => DEGRADED + never 'clean'"
else
  ok "(h) empty report (unconditional) => DEGRADED + never 'clean'  [SKIP invalid-JSON: no Python]"
fi

# --- (i) SPEED FLAGS pinned on the semgrep argv ALWAYS (L-00000145), and a fast
# stub never reports a timeout. Runs on every host (uses the stub, no semgrep).
ARGV_OUT="$(mktemp)"
OUT_I="$(STUB_ARGV_OUT="$ARGV_OUT" run_isolated_path argv "probe.py" <<'EOF'
x = 1
EOF
)"
rc=$?
[ "$rc" -eq 0 ] || fail "(i) fast stub scan should exit 0, got $rc — output: $OUT_I"
grep -q -- '--disable-version-check' "$ARGV_OUT" || fail "(i) semgrep argv missing --disable-version-check: $(cat "$ARGV_OUT")"
grep -q -- '--metrics=off'           "$ARGV_OUT" || fail "(i) semgrep argv missing --metrics=off: $(cat "$ARGV_OUT")"
printf '%s' "$OUT_I" | grep -q 'timed out' && fail "(i) a fast stub must NOT report a timeout: $OUT_I"
rm -f "$ARGV_OUT"
ok "(i) both speed flags always on argv + fast stub never says 'timed out'"

# --- (j) EXPIRY: sleeping stub + short SEMGREP_TIMEOUT => 'timed out' + DEGRADED
# + exit 0. The rc=124 branch is only reachable WITH the timeout envelope, so
# SKIP (announced) when `timeout` is not on PATH — a 'timed out' there would lie.
if command -v timeout >/dev/null 2>&1; then
  OUT_J="$(SEMGREP_TIMEOUT=2 STUB_SLEEP=20 run_isolated_path sleep "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 0 ] || fail "(j) an expiry must exit 0 (never a false block), got $rc — output: $OUT_J"
  printf '%s' "$OUT_J" | grep -q 'timed out'        || fail "(j) expiry must announce 'timed out', got: $OUT_J"
  printf '%s' "$OUT_J" | grep -q 'COVERAGE DEGRADED' || fail "(j) expiry must be COVERAGE DEGRADED, got: $OUT_J"
  printf '%s' "$OUT_J" | grep -qi 'clean' && fail "(j) an expiry must NEVER print 'clean': $OUT_J"
  ok "(j) sleeping stub + SEMGREP_TIMEOUT=2 => 'timed out' + DEGRADED + exit 0"
else
  echo "  SKIP (j): timeout not on PATH (rc=124 branch unreachable without the envelope)"
fi

# =============================================================================
# (sv1)..(sv6) — THE COMMON VERDICT ON THE GATE PATH (T-01M4W80Q5C3F6G99G0JXJB3RH4,
# S1). Outside the hook, semgrep-scan.sh hands semgrep's raw report to the
# scan_verdict.py BESIDE IT and writes .agents/state/local/sca-reports/
# semgrep-verdict.json; a failed or impossible call prints ONE fixed line and
# changes nothing else. The `finding` stub drives every arm, so they run
# PARTOUT; the arms that read a verdict need python 3 and SKIP, announced,
# without it. (sv2) lives with (c), whose setup it shares; (sv5) with the hook
# arms. Each arm names the mutant it must turn red.
# =============================================================================
SV_PY="$HERE/scan_verdict.py"
SV_T="$(mktemp -d)"; assert_tmpdir "$SV_T"
SV_FIXED='semgrep-scan: verdict commun non rendu (scan_verdict'
if [ -n "$PY" ] && [ -f "$SV_PY" ]; then
  # --- (sv1)+(sv6) a finding `agents.security.x` => the verdict is PRESENT,
  # VALID, status=findings, rule=x (the prefix is stripped only if --config
  # reached the adapter), candidates = the files semgrep was handed (argv after
  # `--`), tool_exit_code = the stub's rc (0) — and, under a FRESH TMPDIR, no
  # .semgrep-cands.* survives the run. Mutants: --config, --candidates or
  # --exit-code dropped from the call; the inline `rm` of the candidate list cut.
  SV_TMP="$SV_T/tmp"; mkdir "$SV_TMP"
  OUT_SV1="$(TMPDIR="$SV_TMP" STUB_RULE="agents.security.x" STUB_ARGV_OUT="$SV_T/argv" \
      RUN_KEEP_VERDICT="$SV_T/v1.json" run_isolated_path finding "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 1 ] || fail "(sv1) a finding must keep exit 1, got $rc — output: $OUT_SV1"
  [ -f "$SV_T/v1.json" ] || fail "(sv1) no semgrep-verdict.json after a gate-path run — output: $OUT_SV1"
  SV_VAL="$("$PY" "$SV_PY" validate "$SV_T/v1.json" 2>&1)" || fail "(sv1) the verdict must validate, got: $SV_VAL"
  [ "$SV_VAL" = "ok" ] || fail "(sv1) validate must print ok, got: $SV_VAL"
  SV_N=0; SV_DD=0
  for w in $(cat "$SV_T/argv"); do
    [ "$SV_DD" = 1 ] && SV_N=$((SV_N + 1))
    [ "$w" = "--" ] && SV_DD=1
  done
  [ "$SV_N" -ge 1 ] || fail "(sv1) the argv sink saw no file after --: $(cat "$SV_T/argv")"
  SV_GOT="$("$PY" -c 'import json,sys; v=json.load(open(sys.argv[1])); print(v["status"], ",".join(f["rule"] for f in v["findings"]), v["coverage"]["candidates"], v["tool_exit_code"])' "$SV_T/v1.json")"
  [ "$SV_GOT" = "findings x $SV_N 0" ] \
    || fail "(sv1) expected 'findings x $SV_N 0' (status rule candidates tool_exit_code), got: $SV_GOT"
  printf '%s' "$OUT_SV1" | grep -q "$SV_FIXED" && fail "(sv1) a rendered verdict must print no failure line: $OUT_SV1"
  ok "(sv1) gate path + finding => verdict valid, status=findings, rule=x, candidates=$SV_N, tool_exit_code=0"
  SV_LEFT="$(ls -A "$SV_TMP")"
  case "$SV_LEFT" in
    *.semgrep-cands.*) fail "(sv6) a candidate list survived the run under TMPDIR: $SV_LEFT" ;;
  esac
  ok "(sv6) fresh TMPDIR => no .semgrep-cands.* left after the run"

  # --- (sv1b) the verdict is produced BEFORE the rc branches and carries the
  # tool's REAL rc: a stub exiting 3 sends the script down 'semgrep error'
  # (exit 0, unchanged), and the verdict is there with tool_exit_code=3.
  # Mutants: production moved after the rc != 0 branch; `--exit-code 0` hard-coded.
  OUT_SV1B="$(STUB_RC=3 RUN_KEEP_VERDICT="$SV_T/v1b.json" run_isolated_path finding "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 0 ] || fail "(sv1b) semgrep rc 3 takes the 'semgrep error' branch (exit 0), got $rc — output: $OUT_SV1B"
  printf '%s' "$OUT_SV1B" | grep -q 'semgrep error (3)' || fail "(sv1b) the rc 3 branch must still speak, got: $OUT_SV1B"
  [ -f "$SV_T/v1b.json" ] || fail "(sv1b) the verdict must be produced BEFORE the rc branches — absent after rc 3: $OUT_SV1B"
  SV_GOT="$("$PY" -c 'import json,sys; v=json.load(open(sys.argv[1])); print(v["tool_exit_code"], v["status"])' "$SV_T/v1b.json")"
  [ "$SV_GOT" = "3 findings" ] || fail "(sv1b) expected tool_exit_code=3 status=findings, got: $SV_GOT"
  ok "(sv1b) semgrep rc 3 => verdict produced before the branches, tool_exit_code=3, script exit 0 unchanged"

  # --- (sv3) a scan_verdict.py that FAILS (exit 2) and POLLUTES stdout and
  # stderr (CANARI), under a `finding` stub: the script's rc stays 1, the console
  # carries the fixed line ONCE and neither CANARI nor 'semgrep error', and the
  # stale verdict planted before the run is gone. A throwaway COPY of the
  # script, beside the fake. Mutants (C1): `[ "$sv_rc" -ne 0 ] && rc=$sv_rc`;
  # the call's redirection removed; the sv_rc check removed.
  SV_C3="$(mktemp -d)"; assert_tmpdir "$SV_C3"
  cp "$SCRIPT" "$SV_C3/semgrep-scan.sh"
  printf '%s\n' 'import sys' 'sys.stdout.write("CANARI\n")' 'sys.stderr.write("CANARI\n")' 'sys.exit(2)' \
    > "$SV_C3/scan_verdict.py"
  OUT_SV3="$(RUN_SCRIPT="$SV_C3/semgrep-scan.sh" RUN_SENTINEL=1 RUN_KEEP_VERDICT="$SV_T/v3.json" \
      run_isolated_path finding "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  rm -rf "$SV_C3"
  [ "$rc" -eq 1 ] || fail "(sv3) a failing scan_verdict must leave the script's rc UNCHANGED (1 on a finding), got $rc — output: $OUT_SV3"
  SV_LINES="$(printf '%s\n' "$OUT_SV3" | grep -c "^$SV_FIXED rc=2)\$")"
  [ "$SV_LINES" -eq 1 ] || fail "(sv3) exactly ONE fixed line '$SV_FIXED rc=2)' expected, got $SV_LINES — output: $OUT_SV3"
  printf '%s' "$OUT_SV3" | grep -q 'CANARI' && fail "(sv3) scan_verdict's own output must never reach the console: $OUT_SV3"
  printf '%s' "$OUT_SV3" | grep -q 'semgrep error' && fail "(sv3) sv_rc must never become rc: $OUT_SV3"
  [ -e "$SV_T/v3.json" ] && fail "(sv3) a failed call leaves NO verdict (the stale one removed), got: $(cat "$SV_T/v3.json")"
  ok "(sv3) scan_verdict rc 2 + CANARI => rc 1 unchanged, ONE fixed line, no CANARI, no stale verdict"

  # --- (sv7) C4: the script launched by a RELATIVE path from a SUBDIRECTORY
  # (`cd sub && bash ../.agents/security/semgrep-scan.sh`) still renders the
  # verdict — $SV is resolved absolute BEFORE the call's `cd "$ROOT"`.
  # Mutant: `SV="$(dirname -- "${BASH_SOURCE[0]}")/scan_verdict.py"` (relative).
  OUT_SV7="$(RUN_RELATIVE=1 RUN_KEEP_VERDICT="$SV_T/v7.json" run_isolated_path finding "probe.py" <<'EOF'
x = 1
EOF
)"
  rc=$?
  [ "$rc" -eq 1 ] || fail "(sv7) a finding must keep exit 1, got $rc — output: $OUT_SV7"
  printf '%s' "$OUT_SV7" | grep -q "$SV_FIXED" && fail "(sv7) a relative launch must still render the verdict, got: $OUT_SV7"
  [ -f "$SV_T/v7.json" ] || fail "(sv7) no verdict after a relative launch from a subdirectory — output: $OUT_SV7"
  ok "(sv7) relative launch from a subdirectory => the verdict is rendered (absolute \$SV)"
else
  echo "  SKIP (sv1)(sv1b)(sv3)(sv6)(sv7): python 3 or scan_verdict.py beside the script absent — the verdict cannot be read"
fi

# --- (sv4) a copy WITHOUT scan_verdict.py => the fixed 'absent' line ONCE, the
# script's rc unchanged (1 on a finding). Runs PARTOUT (no verdict is read).
# Mutant: the 'absent' branch of the check removed.
SV_C4="$(mktemp -d)"; assert_tmpdir "$SV_C4"
cp "$SCRIPT" "$SV_C4/semgrep-scan.sh"
OUT_SV4="$(RUN_SCRIPT="$SV_C4/semgrep-scan.sh" run_isolated_path finding "probe.py" <<'EOF'
x = 1
EOF
)"
rc=$?
rm -rf "$SV_C4"
[ "$rc" -eq 1 ] || fail "(sv4) scan_verdict absent must leave the script's rc UNCHANGED (1 on a finding), got $rc — output: $OUT_SV4"
SV_LINES="$(printf '%s\n' "$OUT_SV4" | grep -c "^$SV_FIXED absent)\$")"
[ "$SV_LINES" -eq 1 ] || fail "(sv4) exactly ONE fixed line '$SV_FIXED absent)' expected, got $SV_LINES — output: $OUT_SV4"
ok "(sv4) scan_verdict.py absent => ONE fixed 'absent' line, rc 1 unchanged"
rm -rf "$SV_T"

# ==== T-00000293: submodule content enters the class-1 SAST perimeter ========
# mk_super_sg builds an OUT-OF-REPO superproject with an initialized submodule
# `sub` carrying an `os.system` sink (verified-red by semgrep.yml's
# python-command-injection-shell-true rule), itself carrying a nested `sub/nested`
# with its OWN sink — so a finding on `sub/nested/nested_vuln.py` PROVES the
# recursion descends past the first boundary. Files written with printf
# (L-00000197); assert_tmpdir guards every throwaway dir (T-00000311); GIT_ISO
# allows the file:// protocol for local-path submodules (git ≥ 2.38).
GIT_ISO="git -c protocol.file.allow=always -c user.name=t -c user.email=t@t.t -c commit.gpgsign=false -c advice.detachedHead=false"
mk_super_sg() {  # echoes the superproject path; a nested submodule is always present
  local nested sub super
  nested="$(mktemp -d)"; sub="$(mktemp -d)"; super="$(mktemp -d)"
  assert_tmpdir "$nested"; assert_tmpdir "$sub"; assert_tmpdir "$super"
  $GIT_ISO init -q "$nested"
  printf 'import os\n\n\ndef nested_run(x):\n    os.system("echo " + x)\n' > "$nested/nested_vuln.py"
  $GIT_ISO -C "$nested" add -A >/dev/null 2>&1
  $GIT_ISO -C "$nested" commit -qm n >/dev/null 2>&1
  $GIT_ISO init -q "$sub"
  printf 'import os\n\n\ndef run(cmd):\n    os.system("echo " + cmd)\n' > "$sub/vuln.py"
  $GIT_ISO -C "$sub" submodule add -q "$nested" nested >/dev/null 2>&1
  $GIT_ISO -C "$sub" add -A >/dev/null 2>&1
  $GIT_ISO -C "$sub" commit -qm s >/dev/null 2>&1
  $GIT_ISO init -q "$super"
  printf 'root\n' > "$super/README.md"
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm r >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule add -q "$sub" sub >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule update -q --init --recursive >/dev/null 2>&1
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm addsub >/dev/null 2>&1
  printf '%s\n' "$super"
}

# --- (k) sous-module commité: os.system committed inside an initialized submodule
# => exit 1, and the audit log carries BOTH sub/vuln.py and the nested
# nested_vuln.py (filename greps are separator-agnostic, so the assertion holds on
# Windows where the log path uses backslashes). SKIP if no semgrep.
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  SUPER_K="$(mk_super_sg)"
  ( cd "$SUPER_K" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 1 ] || fail "(k) os.system committed in a submodule must exit 1, got $rc"
  LOGLINE="$(tail -1 "$SUPER_K/.agents/state/local/sca-reports/audit-log.jsonl")"
  printf '%s' "$LOGLINE" | grep -q 'vuln\.py'        || fail "(k) audit must carry the submodule finding, got: $LOGLINE"
  printf '%s' "$LOGLINE" | grep -q 'nested_vuln\.py' || fail "(k) audit must carry the NESTED finding (proves recursion), got: $LOGLINE"
  ok "(k) os.system in an initialized submodule (+ nested) => exit 1, both findings in the audit log"
else
  echo "  SKIP (k): semgrep not installed"
fi

# --- (l) non initialisé: a deinit'd gitlink is ANNOUNCED absent (stderr) and the
# scan never blocks (exit 0). CI-safe via a semgrep stub whose only job is to make
# `have semgrep` true so enumeration runs — the deinit'd `sub` never reaches it.
STUBL="$(mktemp -d)"; assert_tmpdir "$STUBL"
REAL_BASH="$SUITE_BASH"
{ printf '#!%s\n' "$REAL_BASH"; printf '%s\n' 'echo "{\"results\":[],\"paths\":{\"scanned\":[]}}"'; printf 'exit 0\n'; } > "$STUBL/semgrep"
chmod +x "$STUBL/semgrep"
SUPER_L="$(mk_super_sg)"
( cd "$SUPER_L" && $GIT_ISO submodule deinit -f sub ) >/dev/null 2>&1
DEG_L="$( cd "$SUPER_L" && PATH="$STUBL:$PATH" SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(l) a not-initialized gitlink must never block (exit 0), got $rc — $DEG_L"
printf '%s' "$DEG_L" | grep -q "submodule 'sub' not initialized" \
  || fail "(l) a not-initialized gitlink must be ANNOUNCED, got: $DEG_L"
ok "(l) not-initialized gitlink => announced 'not initialized' + exit 0"

# --- (m) sans sous-module: the enumeration is WIRED (grep-scope pin, L-00000154 —
# a mechanism nothing asserts is disarmed in one silent edit) AND a repo carrying
# NO submodule behaves exactly as before. The wiring grep runs ALWAYS; the
# behavioural half needs semgrep (SKIP announced).
grep -q 'enumerate_submodules' "$SCRIPT" || fail "(m) enumerate_submodules not wired into semgrep-scan.sh"
grep -q '160000'               "$SCRIPT" || fail "(m) gitlink mode filter (160000) absent from semgrep-scan.sh"
grep -q 'not initialized'      "$SCRIPT" || fail "(m) 'not initialized' announcement absent from semgrep-scan.sh"
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  OUT_M="$(run_isolated "plain.py" <<'PYEOF'
import os
os.system("echo hi")
PYEOF
)"
  rc=$?
  [ "$rc" -eq 1 ] || fail "(m) a no-submodule repo with a sink must still exit 1 (unchanged), got $rc — $OUT_M"
  printf '%s' "$OUT_M" | grep -qi 'submodule' && fail "(m) a no-submodule repo must emit NO submodule notice, got: $OUT_M"
  ok "(m) enumeration wired (grep pin) + no-submodule repo unchanged (exit 1, zero submodule notice)"
else
  ok "(m) enumeration wired (grep pin)  [SKIP behavioural half: semgrep not installed]"
fi

# =============================================================================
# (n)..(r) — THE PERIMETER CAN SEE A COMMIT (T-00000364)
# =============================================================================
# WHAT WAS BROKEN, AND WHY EVERY CASE BELOW NEEDS A COMMITTED FIXTURE. The
# perimeter was built from `git diff HEAD` + `ls-files --others` — the WORKING
# TREE, never a commit. AGENTS.md's nominal pipeline runs the security gate
# AFTER the dev stage, and the dev stage COMMITS; so on the nominal path the
# perimeter is empty BY CONSTRUCTION and the script wrote `audit CLEAN`.
#
# MEASURED, old script vs new, on identical fresh fixtures (a clean tree whose
# single commit carries `os.system(...)`, i.e. a live command injection):
#   old -> "nothing to scan (clean working tree)", audit verdict CLEAN
#   new -> COVERAGE DEGRADED naming `--at HEAD`,   audit verdict DEGRADED
#   new --at HEAD -> 1 finding, exit 1
# So the old behaviour posted a CLEAN to the audit log with an injection sitting
# one line away, committed.
#
# THE FIXTURE MUST CARRY `.agents/.gitignore` WITH `state/local/`, AND THAT IS
# NOT A DETAIL. The script does `mkdir -p .agents/state/local/sca-reports` and
# appends its audit line THERE, inside the repo under test. Without the ignore
# rule that write makes the tree DIRTY, the perimeter is no longer empty, and the
# run takes a completely different branch — which is exactly how a first
# measurement of this defect came back wrong (the fixture polluted itself, and
# the old script appeared to degrade correctly when it does not). The real repo
# ignores that path via `.agents/.gitignore`, so mirroring it is what makes the
# fixture FAITHFUL rather than merely isolated.
#
# Each case builds its OWN fixture: reusing one across runs re-introduces the
# same pollution through the audit log appended by the previous case.

# committed_fixture — a repo with ONE commit carrying $2, and a CLEAN tree.
# Echoes the dir; the caller runs the script inside it.
committed_fixture() {  # $1 fixture-filename ; stdin = content
  local dir; dir="$(mktemp -d)"
  assert_tmpdir "$dir"
  mkdir -p "$dir/.agents"
  printf 'state/local/\n' > "$dir/.agents/.gitignore"
  git -C "$dir" init -q
  cat > "$dir/$1"
  git -C "$dir" add -A >/dev/null 2>&1
  git -C "$dir" -c user.email="test@test.local" -c user.name="test" \
    commit -qm init >/dev/null 2>&1
  # A fixture whose tree is NOT clean would silently test another branch.
  [ -z "$(git -C "$dir" status --porcelain)" ] \
    || fail "committed_fixture: tree not clean before the run — the case below would measure the wrong branch"
  printf '%s' "$dir"
}

# --- (q) USAGE errors are refused, never absorbed into a perimeter -----------
# Runs ALWAYS (no semgrep needed): argument parsing precedes the availability
# check. A mistyped flag that returned 0 would hand the caller a "clean" for a
# perimeter that was never built.
OUT_Q="$( "$SUITE_BASH" "$SCRIPT" --bogus 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(q) an unknown option must exit 2, got $rc — $OUT_Q"
printf '%s' "$OUT_Q" | grep -q "unknown option" || fail "(q) unknown option must be NAMED, got: $OUT_Q"
OUT_Q2="$( "$SUITE_BASH" "$SCRIPT" --at 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(q) --at with no ref must exit 2, got $rc — $OUT_Q2"
OUT_Q3="$( "$SUITE_BASH" "$SCRIPT" --at zzz-no-such-ref 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(q) an unresolvable --at ref must DEGRADE (exit 0), not exit 2, got $rc — $OUT_Q3"
printf '%s' "$OUT_Q3" | grep -q "COVERAGE DEGRADED" \
  || fail "(q) an unresolvable --at ref must announce COVERAGE DEGRADED, got: $OUT_Q3"
printf '%s' "$OUT_Q3" | grep -qi "nothing to scan" \
  && fail "(q) an unresolvable --at ref must NEVER read as a clean perimeter, got: $OUT_Q3"
ok "(q) usage errors exit 2 and are named; an unresolvable --at ref degrades (exit 0), never 'nothing to scan'"

# --- (q2) ARGUMENT INJECTION ON THE REF (CWE-88, L-009) ----------------------
# `$AT_REF` reaches `git rev-parse`/`git diff`/`git show` in REVISION position,
# and git offers no `--` escape that forces a leading-dash string to be read as
# a ref. So a value like `--upload-pack=...` would become an OPTION of the git
# command. The guard refuses the SHAPE; this case proves it refuses, and the
# witness below proves the guard is not simply refusing everything.
for bad in "--upload-pack=/x" "--output=/x" "-x"; do
  OUT_QI="$( "$SUITE_BASH" "$SCRIPT" --at "$bad" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(q2) --at '$bad' must be refused with exit 2 (CWE-88), got $rc — $OUT_QI"
  printf '%s' "$OUT_QI" | grep -q "CWE-88" \
    || fail "(q2) the refusal must name why, got: $OUT_QI"
done
# NON-VACUITY WITNESS: a legitimate ref must still be ACCEPTED, or the guard
# above would be indistinguishable from a script that rejects every --at.
OUT_QW="$( "$SUITE_BASH" "$SCRIPT" --at HEAD 2>&1 )"; rc=$?
[ "$rc" -ne 2 ] || fail "(q2) the guard rejects a LEGITIMATE ref (HEAD) — it refuses everything, so its refusals prove nothing: $OUT_QW"
ok "(q2) a leading-dash --at ref is refused as CWE-88, and a legitimate ref is still accepted (witness)"

# --- (r) the wiring is asserted, not assumed (L-00000154) --------------------
# Two links make this feature bite: the option must be PARSED, and the covered-
# language set must be READ FROM THE RULESET rather than re-typed. Asserting the
# first alone would let the second be deleted in one silent edit.
grep -q -- '--at)'                "$SCRIPT" || fail "(r) --at is not parsed by semgrep-scan.sh"
grep -q 'files_changed_by'         "$SCRIPT" || fail "(r) the commit-perimeter helper is absent"
grep -q 'covered_extensions'       "$SCRIPT" || fail "(r) the covered-language helper is absent"
grep -q "languages:" "$SCRIPT"                || fail "(r) the covered-language set is not READ from the ruleset (no 'languages:' extraction) — a hardcoded list is L-00000187"
grep -q 'cannot map to file extensions'  "$SCRIPT" \
  || fail "(r) an unmapped ruleset language must be ANNOUNCED, not silently dropped"
# T-00000370 replaced the pin on 'CANNOT see committed code'. That string was the
# BLINDNESS announcement, and the default mode is no longer blind: pinning it now
# would force the message back into a claim that is FALSE. What replaces it is a
# pin on each link of the mechanism that made it obsolete — L-00000154, assert
# all N links, because any one deleted silently restores the old hole.
grep -q -- '--since)'              "$SCRIPT" || fail "(r) --since is not parsed by semgrep-scan.sh"
grep -q 'resolve_base'             "$SCRIPT" || fail "(r) R-BASE resolution helper absent — the base would be guessed"
grep -q 'head_is_merge'            "$SCRIPT" || fail "(r) merge detector absent: a merge HEAD with an unknown base would omit this task's own commits"
grep -q 'files_changed_since'      "$SCRIPT" || fail "(r) the since-base perimeter helper is absent"
[ "$( grep -cE '^[^#]*git -C .* (diff|show) .*--no-renames' "$SCRIPT" )" -ge 3 ] || fail "(r) --no-renames is not on the git ENUMERATION COMMANDS (a mention in a comment is not a flag — L-00000143)"
grep -q 'validate_ref_option'      "$SCRIPT" || fail "(r) the single post-parse ref validator is absent (empty value + CWE-88)"
grep -q 'PARTIELLEMENT'            "$SCRIPT" || fail "(r) partially-parsed files are not named: they would be counted as covered"
ok "(r) all links wired: --at/--since parsed, R-BASE + merge detector, renames disarmed, one ref validator, partial parses named"

if [ "$HAVE_SEMGREP" -eq 1 ]; then
  # --- (n) THE DEFAULT MODE NOW *SEES* COMMITTED CODE (T-00000370) -----------
  # THIS ARM USED TO ASSERT THE OPPOSITE, and that is the point of the ticket.
  # Until T-00000370 it demanded exit 0, a `COVERAGE DEGRADED`, and a message
  # naming `--at HEAD` as the remedy — i.e. it CODIFIED the blindness: a clean
  # tree hiding a committed injection was the best the gate could do, so the test
  # locked in the degraded answer as correct.
  #
  # The default perimeter is now the TARGET (`R-BASE`: commits since the base,
  # or HEAD when the fork is undetectable, ∪ the dirty tree), so the committed
  # sink is IN SCOPE and is FOUND. The remedy hop it used to advertise no longer
  # exists — there is nothing narrower to hop to.
  #
  # This fixture has no upstream, so it exercises R-BASE line 3 (INDETECTABLE):
  # the run must PROCEED on HEAD alone and SAY SO, never refuse, never fall
  # silent. Both halves are asserted below.
  D_N="$(committed_fixture "bad.py" <<'PYEOF'
import os
def f(u):
    os.system("echo " + u)
PYEOF
)"
  OUT_N="$( cd "$D_N" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 1 ] \
    || fail "(n) THE FOUNDING DEFECT IS BACK: the DEFAULT mode must FIND a committed sink (exit 1), got $rc — $OUT_N"
  printf '%s' "$OUT_N" | grep -q "finding(s)" \
    || fail "(n) the default mode found nothing on a fixture built to be found — $OUT_N"
  printf '%s' "$OUT_N" | grep -qi "nothing to scan" \
    && fail "(n) THE FALSE GREEN IS BACK: a committed injection reported as a clean working tree — $OUT_N"
  # R-BASE line 3 must be ANNOUNCED, not silently taken.
  printf '%s' "$OUT_N" | grep -q "fork indétectable" \
    || fail "(n) an undetectable fork must be NAMED in the scope line, never silently assumed — $OUT_N"
  # And the dead remedy hop must not be advertised any more: sending a reader to
  # `--at HEAD` now points at a NARROWER perimeter than the one that just ran.
  printf '%s' "$OUT_N" | grep -q -- "re-run with: semgrep-scan.sh --at HEAD" \
    && fail "(n) the remedy HOP is dead but the message still advertises it — $OUT_N"
  grep -q '"verdict":"CLEAN"' "$D_N/.agents/state/local/sca-reports/audit-log.jsonl" \
    && fail "(n) the audit log received a CLEAN verdict for a perimeter carrying a sink"
  grep -q '"findings":1' "$D_N/.agents/state/local/sca-reports/audit-log.jsonl" \
    || fail "(n) the audit log must record the finding the default mode found"
  rm -rf "$D_N"
  ok "(n) DEFAULT mode reaches COMMITTED code and reports the sink (exit 1) — the blindness this ticket exists to kill"

  # --- (o) POSITIVE CONTROL: --at HEAD actually reaches the committed sink ---
  # A green here would prove nothing (L-00000186: a harness lies by the void).
  # The fixture carries a sink the default ruleset KNOWS, so the only acceptable
  # outcome is a real finding and exit 1.
  D_O="$(committed_fixture "bad.py" <<'PYEOF'
import os
def f(u):
    os.system("echo " + u)
PYEOF
)"
  OUT_O="$( cd "$D_O" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --at HEAD 2>&1 )"; rc=$?
  [ "$rc" -eq 1 ] || fail "(o) --at HEAD must FIND the committed sink (exit 1), got $rc — $OUT_O"
  printf '%s' "$OUT_O" | grep -q "finding(s)" \
    || fail "(o) --at HEAD found nothing on a fixture built to be found — $OUT_O"
  printf '%s' "$OUT_O" | grep -q "perimeter = commit" \
    || fail "(o) --at must ANNOUNCE its perimeter, or two runs are indistinguishable in the log — $OUT_O"
  rm -rf "$D_O"
  ok "(o) --at HEAD reaches COMMITTED code and reports the finding (exit 1) — the capability that did not exist"

  # --- (p) NEGATIVE CONTROL for (n): the new branch must NOT fire everywhere -
  # Same clean tree, but nothing in a covered language. The original CLEAN has
  # to survive, or the fix would degrade every clean run and make the journal
  # false in the other direction (L-00000187, and the same argument the `absent`
  # scope branch above already makes).
  D_P="$(committed_fixture "notes.txt" <<'TXTEOF'
plain text, no covered language here
TXTEOF
)"
  OUT_P="$( cd "$D_P" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(p) a genuinely empty perimeter must exit 0, got $rc — $OUT_P"
  # T-00000370 — the WORDING moved, the SUBSTANCE did not, and the difference is
  # worth stating. Under the old default the tree was clean, so the perimeter was
  # EMPTY and the run took the "nothing to scan (clean working tree)" branch. The
  # default is now the TARGET, so HEAD's files ARE in the perimeter: it is no
  # longer empty, it simply holds nothing of a covered language. That is class E,
  # and its message NAMES the reason instead of implying an empty tree. Asserting
  # the old literal here would force the code back into a message that is now
  # FALSE. What must hold is that the reason is NAMED — never a bare CLEAN.
  printf '%s' "$OUT_P" | grep -Eq "nothing to scan|aucun fichier du périmètre n'est d'un langage" \
    || fail "(p) with NO covered language committed, the run must NAME why there was nothing to read, got: $OUT_P"
  printf '%s' "$OUT_P" | grep -q "COVERAGE DEGRADED" \
    && fail "(p) the blindness branch fired where there is no blindness — it would degrade every clean run: $OUT_P"
  grep -q '"verdict":"CLEAN"' "$D_P/.agents/state/local/sca-reports/audit-log.jsonl" \
    || fail "(p) a genuinely empty perimeter must still record CLEAN"
  rm -rf "$D_P"
  ok "(p) negative control: no covered language committed => original CLEAN survives, branch does not fire"

  # --- (r2) THE BOUND IS REAL: an unmapped ruleset language is ANNOUNCED -----
  # L-00000187 in its functional form. Point the script at a ruleset declaring a
  # language the mapping table does not know, and require it to SAY so — a
  # detector that silently claims "no covered language" for an unknown one is
  # the fail-open shape this announcement exists to prevent.
  D_R="$(committed_fixture "bad.py" <<'PYEOF'
import os
os.system("echo hi")
PYEOF
)"
  # The probe ruleset lives OUTSIDE the fixture repo, and that is load-bearing:
  # written inside it, `odd.yml` would be UNTRACKED, the tree would be DIRTY, the
  # perimeter would be non-empty, and the run would never reach the blind-perimeter
  # branch this case exists to exercise (measured — it errored on the probe file
  # instead). Same self-pollution trap as the audit-log one described above.
  CFG_DIR="$(mktemp -d)"; assert_tmpdir "$CFG_DIR"
  CFG_ODD="$CFG_DIR/odd.yml"
  cat > "$CFG_ODD" <<'YMLEOF'
rules:
  - id: odd-lang-probe
    message: probe
    severity: INFO
    languages: [cobol]
    pattern: FOO
YMLEOF
  OUT_R="$( cd "$D_R" && SEMGREP_CONFIG="$CFG_ODD" "$SUITE_BASH" "$SCRIPT" 2>&1 )"
  printf '%s' "$OUT_R" | grep -q "cannot map to file extensions" \
    || fail "(r2) an unmapped ruleset language must be ANNOUNCED out loud, got: $OUT_R"
  printf '%s' "$OUT_R" | grep -q "cobol" \
    || fail "(r2) the announcement must NAME the unmapped language, got: $OUT_R"
  # TOTAL mapping failure (cobol is the ONLY declared language) => the detector
  # can conclude NOTHING, so it must refuse rather than report a clean tree.
  # A "nothing to scan" here would be indistinguishable from a genuinely
  # uncovered repo — the exact ambiguity this branch exists to remove.
  printf '%s' "$OUT_R" | grep -q "EVERY language the ruleset declares is unmapped" \
    || fail "(r2) a TOTAL mapping failure must refuse to conclude, got: $OUT_R"
  printf '%s' "$OUT_R" | grep -qi "nothing to scan" \
    && fail "(r2) a TOTAL mapping failure reported a clean working tree — that is the fail-open shape: $OUT_R"
  grep -q '"verdict":"DEGRADED"' "$D_R/.agents/state/local/sca-reports/audit-log.jsonl" \
    || fail "(r2) a TOTAL mapping failure must record DEGRADED in the audit log"
  rm -rf "$D_R" "$CFG_DIR"
  ok "(r2) unmapped language announced by name; a TOTAL mapping failure refuses to conclude (DEGRADED, never 'clean')"

  # --- (s) THE HELPER'S OWN INPUT CAN BE MISSING, AND THAT MUST BE SAID -------
  # MEASURED DEFECT IN THIS VERY TASK: with the ruleset absent, the detector
  # found zero languages, concluded "nothing is covered", and printed `nothing to
  # scan (clean working tree)` over a COMMITTED os.system. The false green this
  # task removes had been reintroduced one level down, in the detector's input.
  # L-00000186: a measurement harness lies by the void, and its lie has the shape
  # of a perfect green — so the floor belongs INSIDE the helper.
  D_S="$(committed_fixture "bad.py" <<'PYEOF'
import os
os.system("echo hi")
PYEOF
)"
  OUT_S="$( cd "$D_S" && SEMGREP_CONFIG="no/such/ruleset.yml" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(s) an unreadable ruleset must exit 0, got $rc — $OUT_S"
  printf '%s' "$OUT_S" | grep -q "absent or unreadable" \
    || fail "(s) an unreadable ruleset must be ANNOUNCED, got: $OUT_S"
  printf '%s' "$OUT_S" | grep -qi "nothing to scan" \
    && fail "(s) THE FALSE GREEN, ONE LEVEL DOWN: unreadable ruleset reported as a clean working tree — $OUT_S"
  grep -q '"verdict":"CLEAN"' "$D_S/.agents/state/local/sca-reports/audit-log.jsonl" \
    && fail "(s) an unreadable ruleset wrote CLEAN to the audit log"
  rm -rf "$D_S"
  ok "(s) unreadable ruleset => refuses to conclude (announced + DEGRADED), never a clean working tree"
else
  ok "(n)(o)(p)(r2)(s) perimeter/commit behaviour  [SKIP: semgrep not installed — (q)(r) wiring pins ran]"
fi

# --- (t) A24: EMPTY VALUE IS A MISSING VALUE, on BOTH forms of BOTH options ---
# The glued form used to carry NO arity check at all, so `--at=` set an empty ref
# that fell through to the dirty tree WITHOUT A WORD — while this script's own
# header forbids exactly that ("a silently dropped flag makes a caller believe it
# scanned a perimeter it never scanned"). Doc and defect lived three lines apart
# in the same file [L-00000111]. Four forms, because a control written into ONE
# parse branch guards one entry path out of two [L-00000268].
for badarg in "--at=" "--since=" ; do
  out="$( "$SUITE_BASH" "$SCRIPT" "$badarg" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(t) '$badarg' must exit 2 (empty value = missing value), got $rc — $out"
  printf '%s' "$out" | grep -qi "EMPTY value is a MISSING value" \
    || fail "(t) '$badarg' was refused but did not SAY why — $out"
done
for badflag in "--at" "--since" ; do
  out="$( "$SUITE_BASH" "$SCRIPT" "$badflag" "" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(t) '$badflag \"\"' must exit 2, got $rc — $out"
done
# NON-VACUITY WITNESS: the guard must not simply refuse everything.
out="$( "$SUITE_BASH" "$SCRIPT" --since HEAD 2>&1 )"; rc=$?
[ "$rc" -ne 2 ] || fail "(t) the guard refuses a LEGITIMATE base — it is refusing by default, not by shape: $out"
ok "(t) A24: empty value refused on both forms of both options (4 arms) + legitimate base still accepted (witness)"

# --- (u) A24bis: CWE-88 on --since, mirroring the --at arm --------------------
# In the three-dot form the base is embedded in ONE argument (`$BASE...HEAD`), so
# a leading-dash base turns the whole argument into a git OPTION. Adding a sister
# option without inheriting the sister's guard reopens the very class this
# script's founding incident was.
for evil in "--upload-pack=/tmp/x" "-x" ; do
  out="$( "$SUITE_BASH" "$SCRIPT" --since "$evil" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(u) --since '$evil' must be refused as CWE-88 (exit 2), got $rc — $out"
  printf '%s' "$out" | grep -q "CWE-88" \
    || fail "(u) --since '$evil' refused without naming the class — $out"
done
ok "(u) A24bis: a leading-dash --since base is refused as CWE-88, exactly as --at is"

# --- (v) --at and --since together are REFUSED, never silently ordered --------
out="$( "$SUITE_BASH" "$SCRIPT" --at HEAD --since main 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(v) --at with --since must be refused (they name different slices), got $rc — $out"
ok "(v) --at + --since refused: the perimeter is never decided by branch order"

# --- (w) 13th AXIS: a PARTIALLY parsed file is subtracted from scope and NAMED -
# MEASURED on this repo: 10 of its 50 shell scripts only partially parse, and all
# ten appear in semgrep's `paths.scanned` regardless — gitleaks-scan.sh (the
# class-0 secrets scanner) and verify.sh among them. Counting them as covered
# would let the gate announce FULL coverage of a file whose unknown remainder was
# never analysed: this ticket's founding defect, rebuilt one storey up BY the fix.
grep -q 'unparsed' "$SCRIPT" \
  || fail "(w) the partial-parse subtraction is absent — partially parsed files would count as covered"
grep -q 'NON LU, nommément' "$SCRIPT" \
  || fail "(w) partially parsed files are subtracted but NOT NAMED — 'named, or scanned' is the whole property"
# the subtraction must read BOTH shapes semgrep uses to report a parse error
grep -q "PartialParsing\|kind\[1\]\|isinstance(kind, list)" "$SCRIPT" \
  || fail "(w) only one error shape is read; the ['PartialParsing', [...]] payload would be missed"
ok "(w) 13th axis: partial parses subtracted from the scope figure AND named, both error shapes read"

# --- (x) R-BASE line 3 is ANNOUNCED, never silently taken --------------------
# Without an upstream the "is this branch past its fork" predicate has NO truth
# value. Guessing false restores the dangerous first-parent fall-back; guessing
# true is a denial of service on every repo without an upstream. So it PROCEEDS
# and SAYS SO. The absence of any refusal here is the assertion.
grep -q 'fork indétectable' "$SCRIPT" \
  || fail "(x) an undetectable fork is not announced — it would be silently assumed"
grep -q 'passez --since' "$SCRIPT" \
  || fail "(x) the announcement does not name what the operator can DO about it"
ok "(x) R-BASE line 3: an undetectable fork proceeds on HEAD alone and is NAMED in the scope line"

# --- (y) C27: the output carries TWO fields, and the precedence only goes UP ---
# "A sink was found" and "the perimeter was readable" are orthogonal questions. A
# perfectly real state — A SINK FOUND *AND* A SUBMODULE NOT ENUMERATED — has no
# rendering on one axis, so an implementer collapses it and a reader treats one as
# the other: fixes the sink, considers the coverage handled.
# nosemgrep: agents.security.shell-eval-on-interpolated-value — same bounded,
# intentional extraction as the cleanup() arm above; the reason is written there.
COUVERTURE="CLEAN"
# nosemgrep: agents.security.shell-eval-on-interpolated-value
eval "$(sed -n '/^couverture_at_least()/,/^}/p' "$SCRIPT")"
declare -f couverture_at_least >/dev/null || fail "(y) couverture_at_least extraction empty"
couverture_at_least "portable par attestation"
[ "$COUVERTURE" = "portable par attestation" ] || fail "(y) CLEAN must yield to attestation, got '$COUVERTURE'"
couverture_at_least "DEGRADED"
[ "$COUVERTURE" = "DEGRADED" ] || fail "(y) attestation must yield to DEGRADED, got '$COUVERTURE'"
couverture_at_least "portable par attestation"
[ "$COUVERTURE" = "DEGRADED" ] || fail "(y) DEGRADED must NOT be downgraded to attestation — a false green, got '$COUVERTURE'"
couverture_at_least "refus de conclure"
[ "$COUVERTURE" = "refus de conclure" ] || fail "(y) refus must outrank DEGRADED, got '$COUVERTURE'"
couverture_at_least "DEGRADED"
[ "$COUVERTURE" = "refus de conclure" ] || fail "(y) refus must NOT be downgraded to DEGRADED, got '$COUVERTURE'"
# the two axes must both be WIRED into the exit path, not merely defined
grep -q 'jamais à leur place' "$SCRIPT" \
  || fail "(y) a findings run does not render its coverage axis: one would be treated as the other"
grep -q "le vide N'EST PAS une preuve ici" "$SCRIPT" \
  || fail "(y) a zero-findings run with degraded coverage renders as a plain clean — the false green"
grep -q '"couverture":"%s"' "$SCRIPT" \
  || fail "(y) the machine channel does not carry the second field"
grep -q '"verdict":"%s"' "$SCRIPT" \
  || fail "(y) the machine channel LOST its verdict field — dashboard_readers histograms it (C40)"
ok "(y) C27: two fields on the wire, precedence only rises (5 transitions), both axes rendered at exit"

# --- (z) C25: the machine channel ANNOUNCES its own write failure -------------
# The audit log became the backbone of this whole mechanism, and it appended with
# no guard: an unwritable $OUT lost the line WITHOUT A WORD, so "no trace" became
# indistinguishable from "the gate never ran" — the exact ambiguity this ticket
# kills on the console, rebuilt in the journal.
# nosemgrep: agents.security.shell-eval-on-interpolated-value — see above.
OUT="$(mktemp -d)/not-a-directory"
: > "$OUT"                       # $OUT is a FILE, so "$OUT/audit-log.jsonl" cannot be written
# Initialize every var the extracted body reads (suite runs set -u). audit() grew
# `config` + the proposes/retains/unparsed partition in T-00000370, so the list
# grew with it — an extraction harness has to track the body it extracts.
TS="1970-01-01T00:00:00Z"; COUVERTURE="CLEAN"; CFG="x.yml"
FILES=(); PROPOSED=(); AUDIT_UNPARSED_N=0
# nosemgrep: agents.security.shell-eval-on-interpolated-value
eval "$(sed -n '/^audit()/,/^}/p' "$SCRIPT")"
declare -f audit >/dev/null || fail "(z) audit extraction empty"
err="$( audit "CLEAN" 0 "[]" 2>&1 >/dev/null )"; rc=$?
[ "$rc" -eq 0 ] || fail "(z) an unwritable audit channel must ANNOUNCE, never block (announce-only polarity), got rc=$rc"
printf '%s' "$err" | grep -q "canal d'audit inécrivable" \
  || fail "(z) the audit channel failed SILENTLY — 'no trace' is indistinguishable from 'never ran': $err"
ok "(z) C25: an unwritable audit channel announces on stderr and does NOT block (announce-only)"

# --- (aa) A22/A25/A27: the attestation is compared by EQUALITY, not inclusion --
# The manual half of this gate cannot be made honest by machinery — a lying
# attestation stays possible, and §7 says so. What IS mechanisable is the SHAPE,
# and the operator chosen for it decides whether the check means anything:
#
#   `∅ ⊆ retenues` is TRUE. Under inclusion, an EMPTY attestation passes the only
#   mechanical control on the least-assured path — the "vacant justification"
#   this gate forbids one storey down, readmitted by the very operator meant to
#   prevent it.
#
# Three failing shapes, one witness. A22 catches the SURPLUS, A25 the EMPTY, and
# A27 the PARTIAL — and A27 is the only one that separates ≡ from ⊆: an
# implementation keeping the old inclusion PLUS an empty-guard passes A22 and A25
# while accepting 1 entry for 50 files. Without A27 the other two are green on a
# mechanism that never got fixed.
att_repo="$(mktemp -d)"; att_files="$(mktemp -d)"
assert_tmpdir "$att_repo"
( cd "$att_repo" \
  && git init -q . \
  && git config user.email t@t.l && git config user.name t \
  && printf 'x=1\n' > a.py && printf 'y=2\n' > b.py \
  && git add -A && git commit -q -m init ) >/dev/null 2>&1
# The perimeter is DERIVED, never hardcoded (L-00000057: right logic, wrong anchor).
# Derived from the SCOPE line, which EVERY run emits, not from the empty-
# attestation message, which only one branch emits. The first version read the
# branch-specific line and returned '' on the linux leg — the harness measured
# nothing, and said so, which is the only reason this was caught.
att_perim="$( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest /dev/null 2>&1 \
              | sed -n 's/.*, \([0-9]*\) scannable file.*/\1/p' | head -1 )"
[ -n "$att_perim" ] && [ "$att_perim" -ge 2 ] \
  || fail "(aa) could not derive the fixture perimeter (got '$att_perim') — the arms below would assert nothing"

# A25 — EMPTY on a non-empty perimeter: malformed, never a pass.
: > "$att_files/empty.txt"
o="$( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest "$att_files/empty.txt" 2>&1 )"
printf '%s' "$o" | grep -q "attestation VIDE" \
  || fail "(aa/A25) an EMPTY attestation passed — this is exactly what inclusion lets through: $o"

# A27 — PARTIAL: every entry legitimately in scope, but fewer than N. THE
# discriminating arm: inclusion accepts this, equality does not.
printf 'a.py\tlu\n' > "$att_files/partial.txt"
o="$( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest "$att_files/partial.txt" 2>&1 )"
printf '%s' "$o" | grep -q "PARTIELLE" \
  || fail "(aa/A27) a PARTIAL attestation passed — the operator is still ⊆, not ≡: $o"

# A22 — SURPLUS: an entry outside the perimeter attests what it cannot attest.
printf 'a.py\tlu\nb.py\tlu\nzz.py\tlu\n' > "$att_files/outside.txt"
o="$( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest "$att_files/outside.txt" 2>&1 )"
printf '%s' "$o" | grep -q "HORS PÉRIMÈTRE" \
  || fail "(aa/A22) an attestation carrying an out-of-perimeter entry passed: $o"

# WITNESS — the mechanism must also ACCEPT. Without this the three arms above are
# satisfied by a function that refuses everything, which is a denial of service
# dressed as rigour. The attestation is BUILT from the perimeter the script
# itself reports, so the witness cannot drift from the implementation.
( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest /dev/null 2>&1 ) >/dev/null
  # The scanner excludes its OWN output directory from the perimeter (idempotence),
  # so a witness built from git alone would attest a file the perimeter no longer
  # holds and fail for a reason that has nothing to do with the operator under test.
( cd "$att_repo" && git ls-files ; cd "$att_repo" && git ls-files --others --exclude-standard ) \
  | grep -v '^[.]agents/state/local/' | sed 's/$/\tlu/' > "$att_files/full.txt"
o="$( cd "$att_repo" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" --attest "$att_files/full.txt" 2>&1 )"; rc=$?
printf '%s' "$o" | grep -q "attestation ≡ retenues" \
  || fail "(aa/witness) a COMPLETE attestation was refused — the check is a denial of service, not a control: $o"
[ "$rc" -eq 0 ] || fail "(aa/witness) a complete attestation must exit 0, got $rc"
printf '%s' "$o" | grep -q "portable par attestation" \
  || fail "(aa/witness) the coverage axis does not record that the attestation carried it: $o"
rm -rf "$att_repo" "$att_files"
ok "(aa) A22/A25/A27: attestation compared by EQUALITY — surplus, empty and PARTIAL all red, a complete one green"

# --- (ab) A8: ONE vocabulary, across the code AND all 9 route surfaces --------
# The coverage axis is emitted by this script and CONSUMED by the route surfaces.
# Two lists maintained in two places drift, and the drift is silent: a surface
# routing on a label the gate never emits is a branch that never fires, which
# reads exactly like a branch that never had anything to do. Asserted here rather
# than trusted, because the two lots that produced them were written in parallel.
ROUTE_SURFACES="
.agents/skills/security-gate/SKILL.md
.agents/skills/kickoff/SKILL.md
.agents/skills/night/SKILL.md
.claude/commands/kickoff.md
.claude/commands/night.md
.claude/agents/security-code-review.md
.codex/agents/security-code-review.toml
.github/agents/security-code-review.agent.md
.gemini/agents/security-code-review.md
.kimi-code/agents/security-code-review.md
"
REPO_ROOT="$(cd "$(dirname "$SCRIPT")/../.." && pwd)"
surf_n=0
while IFS= read -r s; do
  [ -n "$s" ] || continue
  [ -f "$REPO_ROOT/$s" ] || fail "(ab) route surface missing: $s"
  surf_n=$((surf_n + 1))
  grep -q "refus de conclure" "$REPO_ROOT/$s" \
    || fail "(ab) $s does not carry the coverage vocabulary — it routes on an axis the gate no longer speaks"
done <<< "$ROUTE_SURFACES"
[ "$surf_n" -eq 10 ] || fail "(ab) expected 10 route surfaces, checked $surf_n — the list drifted"
# and every label the CODE can emit must exist in the doctrinal surface
for lbl in "refus de conclure" "portable par attestation" "DEGRADED" ; do
  grep -q "$lbl" "$SCRIPT" \
    || fail "(ab) the code cannot emit '$lbl' but the surfaces document it"
  grep -q "$lbl" "$REPO_ROOT/.agents/skills/security-gate/SKILL.md" \
    || fail "(ab) the code emits '$lbl' but security-gate/SKILL.md never mentions it — an unroutable verdict"
done
ok "(ab) A8: one coverage vocabulary, present in the code and in all 9 route surfaces"

# --- (ac) C17 + A7: the record carries its PROVENANCE and its PARTITION -------
# C17 — two audit lines that read identically mean opposite things depending on
# WHICH ruleset produced them: the shipped offline set covers six languages,
# `p/security-audit` covers dozens, and "clean" under the first is not "clean"
# under the second. Without `config`, a coverage REGRESSION between two runs is
# invisible in the very journal built to make coverage visible.
# A7 — `proposes`/`retains`/`unparsed` is a PARTITION, not a total. `retains <
# proposes` is ordinary and harmless (a commit deleted files); `unparsed > 0` is
# the one meaning an unknown remainder was never analysed. One "N files" figure
# conflates them and reads as full coverage either way — the exact defect this
# task removes, so the journal must not rebuild it one field down.
grep -q '"config":"%s"'   "$SCRIPT" || fail "(ac/C17) the machine record does not carry the RULESET it used"
grep -q '"proposes":%s'   "$SCRIPT" || fail "(ac/A7) the record does not carry the proposed population"
grep -q '"retains":%s'    "$SCRIPT" || fail "(ac/A7) the record does not carry the retained population"
grep -q '"unparsed":%s'   "$SCRIPT" || fail "(ac/A7) the record does not carry the unparsed count — the one that means blindness"
# and they must be REAL values, not a template nobody fills: run it and parse.
if [ "$HAVE_SEMGREP" -eq 1 ] && [ -n "$PY" ]; then
  d_ac="$(mktemp -d)"; assert_tmpdir "$d_ac"
  ( cd "$d_ac" && git init -q . && git config user.email t@t.l && git config user.name t \
    && printf 'x=1\n' > a.py && git add -A && git commit -q -m init ) >/dev/null 2>&1
  ( cd "$d_ac" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" ) >/dev/null 2>&1
  "$PY" - "$d_ac/.agents/state/local/sca-reports/audit-log.jsonl" "$CFG" <<'PYEOF' || fail "(ac) the record's fields are absent or not the values the run actually used"
import json, sys
line = [l for l in open(sys.argv[1], encoding="utf-8") if l.strip()][-1]
rec = json.loads(line)
for k in ("config", "proposes", "retains", "unparsed"):
    if k not in rec: sys.exit(1)
if rec["config"] != sys.argv[2]: sys.exit(1)          # the ruleset ACTUALLY used
if not isinstance(rec["proposes"], int): sys.exit(1)
if rec["retains"] > rec["proposes"]: sys.exit(1)      # a partition, not two free numbers
PYEOF
  rm -rf "$d_ac"
fi
ok "(ac) C17+A7: the machine record names its ruleset and partitions its perimeter (proposes/retains/unparsed)"

# --- (ad) THE ATTESTATION MUST BE REACHABLE WITHOUT THE SCANNER ---------------
# Class A — semgrep absent — is PRECISELY when a human review has to carry the
# verdict, so `--attest` exists for exactly that case. It was nevertheless placed
# BEHIND the availability check, which made the one path written for a missing
# scanner unreachable whenever the scanner was missing. The host leg could not
# see it (semgrep installed there); the linux replay could, and did. This arm
# keeps it visible on BOTH platforms by asserting the ORDER in the source.
att_line="$(grep -n 'ATTESTATION MODE' "$SCRIPT" | head -1 | cut -d: -f1)"
sem_line="$(grep -n '^if ! have semgrep; then' "$SCRIPT" | head -1 | cut -d: -f1)"
[ -n "$att_line" ] && [ -n "$sem_line" ] \
  || fail "(ad) could not locate the attestation block or the availability check"
[ "$att_line" -lt "$sem_line" ] \
  || fail "(ad) the availability check (line $sem_line) precedes the attestation block (line $att_line) — --attest is unreachable in the very case it exists for"
ok "(ad) --attest is reachable with NO scanner installed (block precedes the availability check)"

# --- (ae) THE SCAN IS IDEMPOTENT: it never scans its own output --------------
# $OUT holds this run's report and the audit log it appends to. In a repo that
# does not gitignore it, those artifacts land in the NEXT run's perimeter, so the
# perimeter grows every time the gate runs. Two consecutive runs of an unchanged
# tree reported 8 then 7 scannable files, and the differential check caught it.
# A perimeter that is not stable across identical runs cannot support a verdict.
grep -q 'OUT_REL' "$SCRIPT" \
  || fail "(ae) the scanner does not exclude its own output directory — its perimeter drifts with every run"
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  d_ae="$(mktemp -d)"; assert_tmpdir "$d_ae"
  ( cd "$d_ae" && git init -q . && git config user.email t@t.l && git config user.name t \
    && printf 'x=1\n' > a.py && git add -A && git commit -q -m init ) >/dev/null 2>&1
  n1="$( cd "$d_ae" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 | sed -n 's/.*, \([0-9]*\) scannable file.*/\1/p' | head -1 )"
  n2="$( cd "$d_ae" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 | sed -n 's/.*, \([0-9]*\) scannable file.*/\1/p' | head -1 )"
  n3="$( cd "$d_ae" && SEMGREP_CONFIG="$CFG" "$SUITE_BASH" "$SCRIPT" 2>&1 | sed -n 's/.*, \([0-9]*\) scannable file.*/\1/p' | head -1 )"
  [ -n "$n1" ] || fail "(ae) could not read the scope figure — the arm would assert nothing"
  [ "$n1" = "$n2" ] && [ "$n2" = "$n3" ] \
    || fail "(ae) the perimeter DRIFTS across identical runs: $n1 then $n2 then $n3 — the gate is scanning its own artifacts"
  rm -rf "$d_ae"
fi
ok "(ae) the perimeter is stable across three identical runs — the gate does not scan its own output"

# =============================================================================
# (af)..(ai) — T-00000317: rules for go/ruby/php/csharp/rust + residual absence
#             NAMED per language. (af)/(ag) are grep pins (run ALWAYS); (ah)/(ai)
#             are behavioural (SKIP announced when semgrep is absent).
# =============================================================================

# The global $CFG is CLOBBERED to "x.yml" by arm (z) above (an extraction
# harness), so the real ruleset path is re-derived here from $REAL_ROOT, which is
# never mutated. Used by every arm below, pins and behavioural alike.
RULESET="$REAL_ROOT/.agents/security/semgrep.yml"
[ -f "$RULESET" ] || fail "(af) real ruleset not found at $RULESET"

# --- (af) C2: the coverage table ≡ the ruleset languages, read the SAME way ---
# The `cover:` table at the top of semgrep.yml is the human-facing coverage
# doctrine; the `languages:` keys are what actually runs. If a rule adds a
# language nobody put in the table (or a row claims rules for a language that has
# none), the doc lies about coverage — L-00000111. Extracted with the SAME sed
# the blindness detector uses in semgrep-scan.sh, so the pin cannot drift from
# the mechanism it guards. Mutation that reddens: add/remove a rule language
# without touching the table, or add a `cover: X rules` row with no such rule.
ruleset_langs="$( sed -n 's/^[[:space:]]*languages:[[:space:]]*\[\(.*\)\].*/\1/p' "$RULESET" \
                   | tr ',' '\n' | tr -d ' ' | grep -v '^$' | sort -u )"
[ -n "$ruleset_langs" ] || fail "(af) no languages extracted from the ruleset — the pin would assert nothing"
while IFS= read -r L; do
  [ -n "$L" ] || continue
  grep -Eq "^#[[:space:]]+cover:[[:space:]]+$L[[:space:]]+rules" "$RULESET" \
    || fail "(af) ruleset declares '$L' but the coverage table has no 'cover: $L rules' row — table and ruleset diverged"
done <<< "$ruleset_langs"
while IFS= read -r L; do
  [ -n "$L" ] || continue
  printf '%s\n' "$ruleset_langs" | grep -qx "$L" \
    || fail "(af) the coverage table claims 'cover: $L rules' but the ruleset declares no such language — the table over-claims"
done < <( grep -oE '^#[[:space:]]+cover:[[:space:]]+[a-z/+]+[[:space:]]+rules' "$RULESET" | awk '{print $3}' )
ok "(af) C2: coverage table ≡ ruleset languages (both directions, same extraction as the detector)"

# --- (ag) S4/C3: the residual absence is NAMED per language, not collapsed ----
# The wiring, pinned so a silent edit cannot disarm it (L-00000154). Mutation
# that reddens: drop the append and the branch collapses back to a bare "rien à
# lire"; rewrite the prefix and arm (p) plus the append both lose their anchor.
grep -q 'langage(s) présent(s) sans règle' "$SCRIPT" \
  || fail "(ag) the COVERED_COUNT=0 branch does not NAME present-without-rule languages — the objective's naming half is gone"
grep -q "aucun fichier du périmètre n'est d'un langage" "$SCRIPT" \
  || fail "(ag) the pinned prefix of the COVERED_COUNT=0 message was removed — arm (p) and the append both depend on it"
grep -q 'UNRULED_LANGS' "$SCRIPT" \
  || fail "(ag) the per-language accumulator is gone — the naming would collapse to a bare 'rien à lire'"
ok "(ag) S4/C3: COVERED_COUNT=0 branch names present-without-rule languages, pinned prefix conserved"

# --- (aj) T-01M5DFN4GRJMVQ4QZ1D88D6TXG lot C: the README's rule count IS the
# ruleset's, and the two Angular rules are typescript + ERROR. L-00000111: a
# doc asserting a count the ruleset does not hold hides the drift. The count
# is `grep -c '^  - id:'`; both README sites (the bold count and "the gap
# between N rules") must carry it. The severity is pinned HERE because the
# hook blocks on ANY finding, a WARNING included: a rule demoted to WARNING
# keeps (hng) red-on-trap, so only this pin turns it red. Mutations that
# redden: a rule added or removed without the README; either Angular rule
# demoted to WARNING, or its `languages:` widened or narrowed.
AJ_README="$REAL_ROOT/README-SECURITY-SCAN-SETUP.md"
[ -f "$AJ_README" ] || fail "(aj) README-SECURITY-SCAN-SETUP.md not found at $AJ_README"
aj_n="$(grep -c '^  - id:' "$RULESET")"
[ "$aj_n" -gt 0 ] || fail "(aj) no '  - id:' line counted in the ruleset — the pin would assert nothing"
aj_absent='(absent)'
aj_bold="$(sed -n 's/^\*\*\([0-9][0-9]*\) hand-written rules\*\*.*/\1/p' "$AJ_README")"
[ "$aj_bold" = "$aj_n" ] \
  || fail "(aj) README says '**${aj_bold:-$aj_absent} hand-written rules**' but semgrep.yml holds $aj_n rules"
aj_gap="$(sed -n 's/.*The gap between \([0-9][0-9]*\) rules.*/\1/p' "$AJ_README")"
[ "$aj_gap" = "$aj_n" ] \
  || fail "(aj) README says 'The gap between ${aj_gap:-$aj_absent} rules' but semgrep.yml holds $aj_n rules"
for aj_id in angular-bypass-security-trust angular-dom-innerhtml-dynamic; do
  aj_blk="$(awk -v id="$aj_id" '/^  - id:/ { on = ($3 == id) } on' "$RULESET")"
  [ -n "$aj_blk" ] || fail "(aj) rule $aj_id is absent from semgrep.yml"
  printf '%s\n' "$aj_blk" | grep -qx '    languages: \[typescript\]' \
    || fail "(aj) rule $aj_id must read typescript only — got: $(printf '%s\n' "$aj_blk" | grep 'languages:')"
  printf '%s\n' "$aj_blk" | grep -qx '    severity: ERROR' \
    || fail "(aj) rule $aj_id must be ERROR (the hook would still block a WARNING, so only this pin sees it) — got: $(printf '%s\n' "$aj_blk" | grep 'severity:')"
done
ok "(aj) README rule count = $aj_n = semgrep.yml '- id:' count (both sites); the 2 Angular rules are typescript + ERROR"

if [ "$HAVE_SEMGREP" -eq 1 ]; then
  # --- (ah) S5(ii) WITNESS: a committed .c file (ext KNOWN, ZERO C rules) NAMED
  # Independent of the five ruled languages, so the naming mechanism stays proven
  # even at full coverage. .c maps in the extension table but the ruleset carries
  # no C rule => COVERED_COUNT=0 => the branch must APPEND "c/c++". Mutation that
  # reddens: delete the append, or drop .c from the ext table.
  D_AH="$(committed_fixture "legacy.c" <<'CEOF'
int main(void){ char b[8]; gets(b); return 0; }
CEOF
)"
  OUT_AH="$( cd "$D_AH" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(ah) a lone unruled-language file must exit 0 (CLEAN, not blindness), got $rc — $OUT_AH"
  printf '%s' "$OUT_AH" | grep -q "langage(s) présent(s) sans règle" \
    || fail "(ah) a committed .c file was NOT named as present-without-rule — the residual absence collapsed: $OUT_AH"
  printf '%s' "$OUT_AH" | grep -q "c/c++" \
    || fail "(ah) the naming fired but did not name c/c++: $OUT_AH"
  printf '%s' "$OUT_AH" | grep -q "COVERAGE DEGRADED" \
    && fail "(ah) an unruled-but-known language is NOT blindness — DEGRADED would cry wolf: $OUT_AH"
  rm -rf "$D_AH"
  ok "(ah) S5(ii): a committed .c file is NAMED 'c/c++' as present-without-rule (independent witness, survives full coverage)"

  # --- (ai) S5(i): each new-language ruleset REDDENS a trap and SPARES a clean file
  # Per language: a committed trapped fixture must be FOUND (exit 1); a committed
  # clean fixture must PASS (exit 0). The clean half is the L-00000343 control —
  # a rule that dropped its non-literal guard would fire on the clean file and
  # redden here — so neither assertion is vacuous.
  run_committed() {  # $1 filename  $2 expected-rc  $3 label ; stdin = content
    local d out rc
    d="$( committed_fixture "$1" )"
    out="$( cd "$d" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq "$2" ] || { rm -rf "$d"; fail "$3: expected exit $2, got $rc — $out"; }
    if [ "$2" -eq 1 ]; then
      printf '%s' "$out" | grep -q "finding(s)" \
        || { rm -rf "$d"; fail "$3: exit 1 but no finding reported — $out"; }
    fi
    rm -rf "$d"
  }

  run_committed "vuln.go"  1 "(ai/go trap)"  <<'EOF'
package main
import ("database/sql"; "fmt"; "os/exec")
func bad(db *sql.DB, id string) {
	db.Query(fmt.Sprintf("SELECT %s", id))
	exec.Command("sh", "-c", id)
}
EOF
  run_committed "clean.go" 0 "(ai/go clean)" <<'EOF'
package main
import "database/sql"
func good(db *sql.DB) { db.Query("SELECT 1") }
EOF

  run_committed "vuln.rb"  1 "(ai/ruby trap)"  <<'EOF'
def bad(x)
  system("echo #{x}")
end
EOF
  run_committed "clean.rb" 0 "(ai/ruby clean)" <<'EOF'
def good
  system("ls", "-la")
end
EOF

  run_committed "vuln.php"  1 "(ai/php trap)"  <<'EOF'
<?php
function bad($db, $x) { exec("ls " . $x); }
EOF
  run_committed "clean.php" 0 "(ai/php clean)" <<'EOF'
<?php
function good() { exec("ls -la"); }
EOF

  run_committed "vuln.cs"  1 "(ai/csharp trap)"  <<'EOF'
using System.Data.SqlClient;
class C { void Bad(string x){ var c = new SqlCommand("SELECT " + x); } }
EOF
  run_committed "clean.cs" 0 "(ai/csharp clean)" <<'EOF'
using System.Data.SqlClient;
class C { void Good(){ var c = new SqlCommand("SELECT 1"); } }
EOF

  run_committed "vuln.rs"  1 "(ai/rust trap)"  <<'EOF'
use std::process::Command;
fn bad(x: &str){ let _ = Command::new("sh").arg("-c").arg(x).output(); }
EOF
  run_committed "clean.rs" 0 "(ai/rust clean)" <<'EOF'
use std::process::Command;
fn good(){ let _ = Command::new("sh").arg("-c").arg("ls").output(); }
EOF
  ok "(ai) S5(i): go/ruby/php/csharp/rust each redden a trap (exit 1) and spare a clean file (exit 0)"

  # --- (ak) Angular, gate path: the trap carries FIVE sinks (l.2 bypass, l.3
  # dynamic innerHTML, l.4 INDEXED bypass, l.5 Renderer2.setProperty innerHTML,
  # l.6 insertAdjacentHTML — closing review M3) and must count EXACTLY 5
  # findings; the clean twin calls another sanitizer method, assigns a LITERAL,
  # a `const` bound to one and sanitize(SecurityContext.HTML, v), trusts a
  # LITERAL resource URL, feeds literals to setProperty/insertAdjacentHTML and
  # carries one `// nosemgrep:` line, and must exit 0. Mutations that redden: a
  # rule or a sink removed (fewer findings); the bypass widened to any
  # `$S.$M(...)`, a literal/const/sanitize exclusion dropped (clean file found).
  D_AK="$(committed_fixture "pos.ts" <<'EOF'
export function f(s: any, el: any, r: any, v: string) {
  el.x = s.bypassSecurityTrustHtml(v);
  el.innerHTML = v;
  el.y = s['bypassSecurityTrustHtml'](v);
  r.setProperty(el, 'innerHTML', v);
  el.insertAdjacentHTML('beforeend', v);
}
EOF
)"
  OUT_AK="$( cd "$D_AK" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; rc=$?
  rm -rf "$D_AK"
  [ "$rc" -eq 1 ] || fail "(ak/angular trap) expected exit 1, got $rc — $OUT_AK"
  printf '%s' "$OUT_AK" | grep -q " 5 finding(s)" \
    || fail "(ak/angular trap) expected exactly 5 findings (one per Angular sink) — $OUT_AK"
  run_committed "neg.ts" 0 "(ak/angular clean)" <<'EOF'
import { SecurityContext } from '@angular/core';
const FIXE = '<b>fixe</b>';
export function g(s: any, el: any, r: any, v: string) {
  el.x = s.sanitize(1, v);
  el.innerHTML = "<b>fixed</b>";
  el.innerHTML = FIXE;
  el.innerHTML = s.sanitize(SecurityContext.HTML, v);
  el.y = s.bypassSecurityTrustResourceUrl('https://www.youtube.com/embed/x');
  r.setProperty(el, 'innerHTML', '<i>x</i>');
  el.insertAdjacentHTML('beforeend', '<i>x</i>');
  el.z = s.bypassSecurityTrustHtml(v); // nosemgrep: angular-bypass-security-trust
}
EOF
  ok "(ak) Angular: the trap .ts counts 5 findings (exit 1), the clean twin exits 0"
else
  ok "(ah)(ai)(ak) naming witness + per-language and Angular rules  [SKIP: semgrep not installed — (af)(ag)(aj) pins ran]"
fi

# =============================================================================
# (h1)..(h12) — HOOK MODE (T-00000459, Lot A). ALL run PARTOUT: a `finding` stub
# is interposed so `have semgrep` is true and the branch logic is exercised even
# on the semgrep-less CI runner (only (h5) hides semgrep on purpose). NO registry
# is touched by this lot — the flag makes the two events testable with no host.
# Every PAYLOAD below is COPIED from a shape this repo actually parses, never
# invented: Claude post_edit_check.sh:6; the toolInput graphy of SYM-008;
# apply_patch from test_hook_contracts.py:47-52 (SYM-048); Antigravity GEMINI.md:21;
# Stop Claude stop-arbitrate.sh:46-50; Stop non-Claude test_events_parity.py:302-303.
# =============================================================================
HK_BASH="$SUITE_BASH"

# run_hook — drive semgrep-scan.sh --hook. All input via P_* env; captures stdout
# and stderr to SEPARATE files ($HKO/$HKE), sets HKRC and HKREPO. @FIX@ in the
# payload is replaced by the fixture basename. P_HOST="-" leaves AGENTS_HOOK_HOST
# unset (ABSENT marker). P_REPO reuses a repo so a 2nd call shares its session
# markers. P_STUB: finding (default, semgrep PRESENT) | absent (PATH stripped of
# semgrep) | none | nopython | cleancount | cleanmutate | error | noresults |
# liste | meurt (the last three: (h15)).
run_hook() {
  local repo stub pth payload host t p
  repo="${P_REPO:-}"
  if [ -z "$repo" ]; then
    repo="$(mktemp -d)"; assert_tmpdir "$repo"
    git -C "$repo" init -q
    git -C "$repo" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
    if [ -n "${P_FIX-probe.py}" ]; then
      printf '%s\n' "${P_FIXBODY:-x = 1}" > "$repo/${P_FIX-probe.py}"
      if [ "${P_COMMIT:-0}" = "1" ]; then
        git -C "$repo" add -A >/dev/null 2>&1
        git -C "$repo" -c user.email="t@t.l" -c user.name="t" commit -qm fix >/dev/null 2>&1
      fi
    fi
  fi
  HKREPO="$repo"
  payload="${P_PAYLOAD//@FIX@/${P_FIX-probe.py}}"
  stub=""; pth="$PATH"
  case "${P_STUB:-finding}" in
    finding)
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"; cat <<'SGEOF'
_f=""; _dd=0
for _a in "$@"; do [ "$_dd" = 1 ] && _f="$_a"; [ "$_a" = "--" ] && _dd=1; done
[ -n "$_f" ] || _f="x"
_n="${STUB_FINDINGS:-1}"; _i=1; _res=""
while [ "$_i" -le "$_n" ]; do
  [ "$_i" -gt 1 ] && _res="$_res,"
  _res="$_res{\"check_id\":\"stub.rule.$_i\",\"path\":\"$_f\",\"start\":{\"line\":$_i},\"extra\":{\"severity\":\"ERROR\"}}"
  _i=$((_i + 1))
done
printf '{"results":[%s],"paths":{"scanned":["%s"]}}\n' "$_res" "$_f"
exit 0
SGEOF
      } > "$stub/semgrep"; chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    absent)
      # hide semgrep: PATH holds only the tools the script needs, none named semgrep.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      for t in env cat git python python3 py mktemp date printf grep dirname sort mkdir sed wc head cut rm tr; do
        p="$(command -v "$t" 2>/dev/null)" && ln -s "$p" "$stub/$t" 2>/dev/null
      done
      pth="$stub" ;;
    nopython)
      # like `absent`, but every python interpreter is PRESENT-AND-FAILING rather
      # than ABSENT, so the script's $PY resolves EMPTY and run_hook_mode takes the
      # no-python branch (:548-566). semgrep is absent too, but that branch exits
      # before have-semgrep matters.
      #
      # WHY LINKED-AND-BROKEN AND NOT SIMPLY OMITTED — measured, not stylistic.
      # The detector is `for c in python3 python py; do "$c" --version …` (:91): it
      # EXECUTES each candidate. Omitting them made bash raise three lookup failures,
      # which reach `command_not_found_handle` — the runner's exported K1 sensor
      # (`run-bash-tests.sh:169-176`) — and the whole run went
      # `MISSING DEP … (cmd: py python python3)`, `VERIFY FAILED`, on BOTH legs, while
      # this suite alone still printed PASS. A stub that EXITS NON-ZERO is found by
      # the lookup, so no 127 is logged, and `--version` still fails: $PY is empty
      # exactly as before and the branch under test is unchanged.
      #
      # This is also what the runner's own criterion prescribes
      # (`run-bash-tests.sh:208-216`): a command a DECISION of the script depends on
      # is LINKED in the stub so the probe still exercises the real branch; only a
      # pure EFFECT is DECLARED in `# allows-missing:`. Adding `py python python3`
      # to that header would have gone green too — and would have blinded this suite
      # to every FUTURE accidental python lookup failure. Declaring a measurement
      # makes the probe blind in silence; linking it keeps the sensor armed.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      for t in env cat git mktemp date printf grep dirname sort mkdir sed wc head cut rm tr; do
        p="$(command -v "$t" 2>/dev/null)" && ln -s "$p" "$stub/$t" 2>/dev/null
      done
      for t in python3 python py; do
        { printf '#!%s\n' "$HK_BASH"; printf 'exit 127\n'; } > "$stub/$t"
        chmod +x "$stub/$t"
      done
      pth="$stub" ;;
    cleancount)
      # a `semgrep` that finds NOTHING and appends one line to $STUB_TRACE per
      # call — the witness of the Stop cache (h14): a skipped scan leaves no line.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"
        printf 'echo call >> "$STUB_TRACE"\n'
        printf 'echo %s\n' "'{\"results\":[],\"paths\":{\"scanned\":[]}}'"
        printf 'exit 0\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    cleanmutate)
      # a `semgrep` that answers CLEAN but REWRITES $STUB_MUTATE during the call —
      # another writer racing the scan (h14b): the cache must not be filled.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"
        printf 'printf "w = 9\\n" >> "$STUB_MUTATE"\n'
        printf 'echo %s\n' "'{\"results\":[],\"paths\":{\"scanned\":[]}}'"
        printf 'exit 0\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    error)
      # a `semgrep` that writes NOTHING and exits EXACTLY 3 (shebang like the
      # `finding` stub): PHASE B json.load fails on the empty report BEFORE the
      # `rc not in (0,1)` test, so the branch is "report not readable JSON".
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"; printf 'exit 3\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    noresults)
      # (h15) valid JSON of the WRONG shape, rc 0: an object with no `results`.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"; printf 'echo %s\n' "'{}'"; printf 'exit 0\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    liste)
      # (h15) valid JSON of the WRONG shape, rc 0: a list, not an object.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"; printf 'echo %s\n' "'[1]'"; printf 'exit 0\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      pth="$stub:$PATH" ;;
    meurt)
      # (h15) a well-formed empty report, but PHASE B DIES: a `python3` beside
      # the stub exits 9 when HK_REPORT is set — the PHASE B call alone sets it —
      # and runs the real interpreter (path read from a DATA file) for every
      # other call, the probe of $PY included.
      stub="$(mktemp -d)"; assert_tmpdir "$stub"
      { printf '#!%s\n' "$HK_BASH"; printf 'echo %s\n' "'{\"results\":[]}'"; printf 'exit 0\n'; } > "$stub/semgrep"
      chmod +x "$stub/semgrep"
      command -v "$PY" > "$stub/real"
      { printf '#!%s\n' "$HK_BASH"
        printf '%s\n' '[ -n "${HK_REPORT:-}" ] && exit 9'
        printf '%s\n' 'exec "$(cat "$(dirname "$0")/real")" "$@"'; } > "$stub/python3"
      chmod +x "$stub/python3"
      pth="$stub:$PATH" ;;
  esac
  HKO="$repo/.hk.out"; HKE="$repo/.hk.err"
  # $CFG is clobbered to "x.yml" by arm (z); $RULESET is the real path re-derived
  # from $REAL_ROOT and used by every arm below it. covered_extensions reads it.
  local -a envv
  envv=(PATH="$pth" STUB_FINDINGS="${P_FINDINGS:-1}" STUB_TRACE="${P_TRACE:-/dev/null}" STUB_MUTATE="${P_MUTATE:-/dev/null}" SEMGREP_CONFIG="$RULESET" SEMGREP_TIMEOUT="${P_TIMEOUT:-45}")
  [ "${P_HOST:-claude}" != "-" ] && envv+=("AGENTS_HOOK_HOST=${P_HOST:-claude}")
  ( cd "$repo" && printf '%s' "$payload" | env "${envv[@]}" "$HK_BASH" "$SCRIPT" --hook ${P_EVT:-} ) >"$HKO" 2>"$HKE"
  HKRC=$?
  [ -n "$stub" ] && rm -rf "$stub"
}

# a covered PYTHON sink is not needed — the finding STUB reports on whatever file
# reaches the perimeter, so a trivial `.py` suffices as the covered fixture.

# --- (h1) post Edit .py, stub finding, host claude => exit 2, stderr names rule
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s1"}' \
  P_EVT="--event=post" P_HOST="claude" run_hook
[ "$HKRC" -eq 2 ] || fail "(h1) a finding on host claude must exit 2, got $HKRC — $(cat "$HKE")"
grep -qE '^stub\.rule\.1 probe\.py:1$' "$HKE" || fail "(h1) stderr must NAME the rule/location, got: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h1) post Edit .py + finding + host claude => exit 2, stderr names rule file:line"

# --- (h1b) --hook with NO --event + Stop Claude payload + dirty fixture =>
# hook_event_name fall-back to STOP: scans the tree (systemMessage form).
P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s1b"}' \
  P_EVT="" P_HOST="claude" run_hook
[ "$HKRC" -eq 2 ] || fail "(h1b) Stop fall-back on a dirty finding must exit 2, got $HKRC — $(cat "$HKE")"
grep -q 'systemMessage' "$HKO" || fail "(h1b) the Stop fall-back must emit the systemMessage form, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h1b) --hook with no --event + Stop payload => event resolved from hook_event_name (systemMessage)"

# --- (h1c) --event=stop with an Edit+file_path payload => the FLAG wins: the
# dirty TREE is scanned, not the single edited file (a clean tree => exit 0).
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s1c"}' \
  P_EVT="--event=stop" P_HOST="claude" P_COMMIT=1 run_hook
[ "$HKRC" -eq 0 ] || fail "(h1c) --event=stop on a CLEAN tree must exit 0 (the flag scans the tree, not the payload file), got $HKRC — $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h1c) --event=stop beats a post-shaped payload: the tree is the perimeter, not the edited file"

# --- (h2) host codex => exit 0, stdout = envelope hookEventName:PostToolUse + additionalContext
P_PAYLOAD='{"toolName":"Edit","toolInput":{"file_path":"@FIX@"},"session_id":"s2"}' \
  P_EVT="--event=post" P_HOST="codex" run_hook
[ "$HKRC" -eq 0 ] || fail "(h2) an envelope host must exit 0, got $HKRC — $(cat "$HKE")"
grep -q '"hookEventName": "PostToolUse"' "$HKO" || fail "(h2) codex stdout must carry the PostToolUse envelope, got: $(cat "$HKO")"
grep -q 'additionalContext' "$HKO" || fail "(h2) codex stdout must carry additionalContext, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h2) host codex => exit 0 + PostToolUse/additionalContext envelope on stdout"

# assert_top_context — T-01M4RWC0DBM6XC1PDQGEG4P79C. Judges $HKO: EXACTLY one
# JSON line, its key set EQUAL to $2 (sorted, comma-joined), and a top-level
# additionalContext EQUAL to hookSpecificOutput.additionalContext (the field the
# Copilot CLI reads, next to the unchanged nested one).
assert_top_context() {   # $1 = arm label ; $2 = expected sorted key list
  local msg
  msg="$("$PY" -c '
import json, sys
lines = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
if len(lines) != 1:
    sys.exit("expected one non-empty line, got %d: %r" % (len(lines), lines))
obj = json.loads(lines[0])
keys = ",".join(sorted(obj))
if keys != sys.argv[2]:
    sys.exit("key set %s != %s" % (keys, sys.argv[2]))
hso = obj.get("hookSpecificOutput") or {}
if obj.get("additionalContext") != hso.get("additionalContext") or not hso.get("additionalContext"):
    sys.exit("top-level additionalContext %r != nested %r" % (obj.get("additionalContext"), hso.get("additionalContext")))
' "$HKO" "$2" 2>&1)" || fail "($1) copilot stdout must carry additionalContext at the top level, equal to the nested one: $msg"
}

# --- (h2d) T-01M4RWC0DBM6XC1PDQGEG4P79C: host copilot + finding => exit 0, the
# PHASE B event form carries additionalContext at the TOP level too, equal to the
# nested one (keys exactly {additionalContext, hookSpecificOutput}).
P_PAYLOAD='{"toolName":"Edit","toolInput":{"file_path":"@FIX@"},"session_id":"s2d"}' \
  P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h2d) an envelope host must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'stub\.rule\.1' "$HKO" || fail "(h2d) the finding must reach stdout, got: $(cat "$HKO") / err: $(cat "$HKE")"
assert_top_context "h2d" "additionalContext,hookSpecificOutput"
rm -rf "$HKREPO"
ok "(h2d) host copilot + finding => exit 0, additionalContext at the top level AND nested, equal"

# --- (h2c) EXACT SYM-048 apply_patch charge with '*** Update File: <fix>' in
# `command`, host codex => a finding NAMED on the fixture. A parser that does not
# read `command` extracts zero paths and this arm reddens.
P_PAYLOAD='{"tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Update File: @FIX@\n*** End Patch"},"session_id":"s2c"}' \
  P_EVT="--event=post" P_HOST="codex" run_hook
[ "$HKRC" -eq 0 ] || fail "(h2c) apply_patch on codex must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'probe\.py' "$HKO" || fail "(h2c) the finding must NAME the fixture parsed out of the apply_patch command, got: $(cat "$HKO") / err: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h2c) apply_patch command (SYM-048) => path parsed from 'command', finding named on the fixture"

# --- (h3) host kimi (UNKNOWN marker) => envelope PostToolUse + stderr + exit 2,
# and ZERO permissionDecision (that is a PreToolUse shape, never emitted here).
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s3"}' \
  P_EVT="--event=post" P_HOST="kimi" run_hook
[ "$HKRC" -eq 2 ] || fail "(h3) an UNKNOWN host marker must exit 2, got $HKRC — $(cat "$HKE")"
grep -q '"hookEventName": "PostToolUse"' "$HKO" || fail "(h3) kimi must still carry the event form on stdout, got: $(cat "$HKO")"
grep -q 'permissionDecision' "$HKO" && fail "(h3) an UNKNOWN host must NEVER emit permissionDecision (PreToolUse shape): $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h3) host kimi => event form on stdout + stderr + exit 2, zero permissionDecision"

# --- (h3b) ABSENT host marker => the claude behaviour of (h1) EXACTLY: exit 2,
# stderr names the rule, stdout EMPTY (on an exit-2 PostToolUse the host jette stdout).
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s3b"}' \
  P_EVT="--event=post" P_HOST="-" run_hook
[ "$HKRC" -eq 2 ] || fail "(h3b) an ABSENT host marker must behave as claude (exit 2), got $HKRC — $(cat "$HKE")"
grep -qE '^stub\.rule\.1 probe\.py:1$' "$HKE" || fail "(h3b) absent-as-claude must name the rule on stderr, got: $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h3b) absent-as-claude POST must leave stdout EMPTY (stderr-only channel), got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h3b) ABSENT marker == claude exactly: exit 2, stderr names rule, stdout empty"

# --- (h4) Edit on a .md file => exit 0, zero bytes (extension outside COVERED_EXTS)
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"notes.md"},"session_id":"s4"}' \
  P_EVT="--event=post" P_HOST="claude" P_FIX="notes.md" P_FIXBODY="# hi" run_hook
[ "$HKRC" -eq 0 ] || fail "(h4) an uncovered extension must exit 0, got $HKRC — $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h4) a .md edit must emit zero stdout, got: $(cat "$HKO")"
[ -s "$HKE" ] && fail "(h4) a .md edit must emit zero stderr, got: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h4) Edit on .md => exit 0, zero bytes (uncovered extension)"

# --- (h4b) tool_name Read WITH a path => exit 0, zero bytes (IGNORE-mute list)
P_PAYLOAD='{"tool_name":"Read","tool_input":{"path":"@FIX@"},"session_id":"s4b"}' \
  P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h4b) an ignored tool must exit 0, got $HKRC — $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h4b) an ignored tool must emit zero stdout, got: $(cat "$HKO")"
[ -s "$HKE" ] && fail "(h4b) an ignored tool must emit zero stderr, got: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h4b) tool_name Read => exit 0, zero bytes (IGNORE-mute list)"

# --- (h4c) tool_name WriteFile + file_path .py => UNKNOWN tool: exit 0, stderr
# DEGRADED naming WriteFile, NO finding; a 2nd call with the SAME sid is silent.
P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"swf"}' \
  P_EVT="--event=post" P_HOST="codex" run_hook
[ "$HKRC" -eq 0 ] || fail "(h4c) an unknown tool must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'WriteFile' "$HKE" || fail "(h4c) the DEGRADED must NAME the unknown tool on stderr, got: $(cat "$HKE")"
grep -qi 'finding' "$HKO" && fail "(h4c) an unknown tool must produce NO finding, got: $(cat "$HKO")"
[ -s "$HKO" ] || fail "(h4c/C26) the DEGRADED must ALSO reach stdout on the 1st call, got empty"
P_REPO="$HKREPO" P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"swf"}' \
  P_EVT="--event=post" P_HOST="codex" run_hook
[ -s "$HKO" ] && fail "(h4c) a 2nd call with the same sid must be silent on stdout, got: $(cat "$HKO")"
[ -s "$HKE" ] && fail "(h4c) a 2nd call with the same sid must be silent on stderr, got: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h4c) WriteFile+path => unknown-tool DEGRADED naming it (both channels), deduped per session"

# --- (h4d) C25: a SCAN tool (Edit) with NO path key => 'clé de chemin inconnue',
# exit 0, DEGRADED on both channels (the key list is a BORNE).
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"note":"nothing here"},"session_id":"s4d"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
[ "$HKRC" -eq 0 ] || fail "(h4d) a SCAN tool with no path key must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'clé de chemin inconnue' "$HKE" || fail "(h4d) a SCAN tool with no path must announce 'clé de chemin inconnue', got: $(cat "$HKE")"
[ -s "$HKO" ] || fail "(h4d/C26) the unknown-key DEGRADED must also reach stdout, got empty"
grep -q 'la liste des clés est une BORNE' "$HKE" || fail "(h4d) with NO key at all, the cause named must be the key list, got: $(cat "$HKE")"
grep -q 'CONFINÉ' "$HKE" && fail "(h4d) nothing was confined here — no path was ever offered: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h4d) C25: SCAN tool, no path key => 'clé de chemin inconnue' DEGRADED (both channels), exit 0"

# --- (h4d2) LES DEUX CAUSES NE SE DISENT PAS PAREIL — le témoin de la
# distinction, et sans lui la correction est indémontrable.
#
# `paths` vide a DEUX causes, et pendant deux jours le hook les annonçait comme
# une seule : « la liste des clés est une BORNE ». C'était faux dans un cas sur
# deux — la clé était trouvée, c'est le CHEMIN que la garde CWE-22 refusait.
# (h4d) couvre la cause « aucune clé », (h10) la cause « chemin confiné ». Cet
# arm-ci est le seul qui les mette CÔTE À CÔTE : il exige que les deux charges
# rendent des messages DIFFÉRENTS. Sans lui, une régression qui refondrait les
# deux branches en une laisserait (h4d) et (h10) verts si le libellé commun
# contenait les deux fragments.
#
# TROISIÈME CAS COUVERT ICI : une clé PRÉSENTE mais VIDE. Elle n'est ni une
# absence de clé ni un confinement — rien n'a été refusé, il n'y avait rien à
# refuser — et la compter comme un confinement annoncerait une garde qui n'a
# rien gardé, c'est-à-dire la même faute de cause déplacée d'un cran.
h4d2repo="$(mktemp -d)"; assert_tmpdir "$h4d2repo"
git -C "$h4d2repo" init -q
git -C "$h4d2repo" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
h4d2out="$(mktemp -d)"; assert_tmpdir "$h4d2out"
printf 'x = 1\n' > "$h4d2out/dehors.py"

P_REPO="$h4d2repo" P_PAYLOAD='{"tool_name":"Edit","tool_input":{"note":"rien"},"session_id":"s4d2a"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
sans_cle="$(cat "$HKE")"

P_REPO="$h4d2repo" \
  P_PAYLOAD="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$h4d2out/dehors.py\"},\"session_id\":\"s4d2b\"}" \
  P_EVT="--event=post" P_HOST="gemini" run_hook
confine_msg="$(cat "$HKE")"

# VALEUR VIDE, PAS UNE SUITE D'ESPACES — et l'écart n'est pas cosmétique : la
# première rédaction de cet arm envoyait `"   "`, qui n'est PAS écarté par
# `normalize_path`. Un chemin d'espaces se résout SOUS la racine, donc il devient
# une cible et part au scan, et l'arm échouait sur sa propre condition de
# non-vacuité. Mesuré plutôt que supposé : seule une valeur vide ou nulle
# atteint la branche « clé connue, rien d'exploitable ».
P_REPO="$h4d2repo" P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":""},"session_id":"s4d2c"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
cle_vide="$(cat "$HKE")"

[ -n "$sans_cle" ] && [ -n "$confine_msg" ] && [ -n "$cle_vide" ] \
  || fail "(h4d2) les trois charges doivent parler — population vide, le test ne prouverait rien"
[ "$sans_cle" != "$confine_msg" ] \
  || fail "(h4d2) « aucune clé » et « chemin confiné » rendent le MÊME message — les deux causes sont confondues : $sans_cle"
case "$confine_msg" in
  *"CONFINÉ hors racine"*) : ;;
  *) fail "(h4d2) le confinement doit se nommer, got: $confine_msg" ;;
esac
case "$confine_msg" in
  *"la liste des clés est une BORNE"*) fail "(h4d2) le confinement accuse encore la liste des clés : $confine_msg" ;;
esac
case "$cle_vide" in
  *"aucune valeur exploitable"*) : ;;
  *) fail "(h4d2) une clé présente mais vide n'est ni une absence ni un confinement, got: $cle_vide" ;;
esac
rm -rf "$h4d2repo" "$h4d2out" "$HKREPO"
ok "(h4d2) les TROIS causes d'un scan vide se disent différemment : clé absente, chemin CONFINÉ, clé sans valeur"

# --- (h4e) C25: a non-JSON payload in post => 'payload not readable JSON',
# exit 0, DEGRADED on both channels (safe-bash.sh:88 precedent).
P_PAYLOAD='this is { not json' P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h4e) a non-JSON payload must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'payload not readable JSON' "$HKE" || fail "(h4e) a non-JSON payload must announce 'payload not readable JSON', got: $(cat "$HKE")"
[ -s "$HKO" ] || fail "(h4e/C26) the unreadable-JSON DEGRADED must also reach stdout, got empty"
assert_top_context "h4e" "additionalContext,hookSpecificOutput,systemMessage"
rm -rf "$HKREPO"
ok "(h4e) C25: non-JSON payload => 'payload not readable JSON' DEGRADED (both channels), exit 0, top-level additionalContext under copilot"

# --- (h4f) C26: a DEGRADED on an exit-0 path is NEVER stderr alone — the event
# form is on stdout on the 1st call (measured on the unknown-tool cell, host gemini).
P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"s4f"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
grep -q 'additionalContext' "$HKO" || fail "(h4f/C26) an exit-0 DEGRADED must render its event form on stdout, got: $(cat "$HKO")"
[ -s "$HKE" ] || fail "(h4f/C26) the same DEGRADED must ALSO be on stderr (detection), got empty"
rm -rf "$HKREPO"
ok "(h4f) C26: an exit-0 DEGRADED reaches BOTH stderr and the stdout event form (never stderr alone)"

# --- (h4g) C26: the 2nd call of the same DEGRADED cell (same sid) leaves stdout
# EMPTY — the once-per-session bound the arms assert as 'stdout vide au 2e'.
P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"s4g"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
[ -s "$HKO" ] || fail "(h4g) precondition: the 1st call must fill stdout"
first_repo="$HKREPO"
P_REPO="$first_repo" P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"s4g"}' \
  P_EVT="--event=post" P_HOST="gemini" run_hook
[ -s "$HKO" ] && fail "(h4g/C26) the 2nd call of the same cell must leave stdout empty, got: $(cat "$HKO")"
rm -rf "$first_repo"
ok "(h4g) C26: the 2nd call of a DEGRADED cell (same sid) leaves stdout empty (once per session)"

# --- (h5) semgrep ABSENT => exit 0, stderr DEGRADED every call, systemMessage on
# the 1st call and ABSENT on the 2nd with the same session_id.
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s5"}' \
  P_EVT="--event=post" P_HOST="claude" P_STUB="absent" run_hook
[ "$HKRC" -eq 0 ] || fail "(h5) semgrep absent must never block (exit 0), got $HKRC — $(cat "$HKE")"
grep -q 'COVERAGE DEGRADED' "$HKE" || fail "(h5) semgrep absent must announce COVERAGE DEGRADED on stderr, got: $(cat "$HKE")"
grep -q 'systemMessage' "$HKO" || fail "(h5) the 1st absent call must emit a systemMessage, got: $(cat "$HKO")"
h5repo="$HKREPO"
P_REPO="$h5repo" P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s5"}' \
  P_EVT="--event=post" P_HOST="claude" P_STUB="absent" run_hook
grep -q 'COVERAGE DEGRADED' "$HKE" || fail "(h5) stderr must still announce on the 2nd call, got: $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h5) the 2nd absent call (same sid) must NOT repeat the systemMessage, got: $(cat "$HKO")"
rm -rf "$h5repo"
ok "(h5) semgrep absent => exit 0, stderr every call, systemMessage once per session"

# --- (h5b) Antigravity payload (stepIdx, no path) => a systemMessage 'inerte'
# once per session, exit 0.
P_PAYLOAD='{"stepIdx":1,"conversationId":"cA","transcriptPath":"/t/x"}' \
  P_EVT="--event=post" P_HOST="gemini" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h5b) an inert payload must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'inerte' "$HKO" || fail "(h5b) the inert branch must emit a systemMessage 'inerte', got: $(cat "$HKO")"
grep -q 'systemMessage' "$HKO" || fail "(h5b) the inert notice must be a systemMessage, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h5b) Antigravity stepIdx payload => systemMessage 'inerte', exit 0"

# --- (h5c) Stop NON-Claude payload WITHOUT the flag (falls back to post, carries
# NEITHER a tool name NOR a path, but a transcriptPath) => exit 0 and NO 'inerte'
# message: transcriptPath alone must never trip the inert branch.
P_PAYLOAD='{"agentType":"dev-multi","sessionId":"s1","agentId":"a1","transcriptPath":"/t/x"}' \
  P_EVT="" P_HOST="gemini" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h5c) a transcript-only payload must exit 0, got $HKRC — $(cat "$HKE")"
grep -qi 'inerte' "$HKO" "$HKE" && fail "(h5c) transcriptPath alone must NOT trip the inert branch, got out:$(cat "$HKO") err:$(cat "$HKE")"
[ -s "$HKO" ] && fail "(h5c) a transcript-only payload must be mute on stdout, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h5c) Stop non-Claude without flag (transcriptPath only) => mute exit 0, never a false 'inerte'"

# --- (h5d) the session marker is sha256(sid)[:16] — the RAW sid never lands in a
# filename under .agents/state/local/semgrep-hook/ (stop-arbitrate.sh:54-63).
RAWSID="RAWSID-abc-123-ne-doit-pas-apparaitre"
P_PAYLOAD="{\"stepIdx\":1,\"conversationId\":\"$RAWSID\",\"transcriptPath\":\"/t/x\"}" \
  P_EVT="--event=post" P_HOST="gemini" P_FIX="" run_hook
MARKD="$HKREPO/.agents/state/local/semgrep-hook"
H16="$("$PY" - "$RAWSID" <<'PYEOF'
import sys, hashlib
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest()[:16])
PYEOF
)"
[ -f "$MARKD/inert-$H16" ] || fail "(h5d) the marker must be keyed by sha256(sid)[:16] (inert-$H16), files: $(ls "$MARKD" 2>/dev/null)"
find "$MARKD" -maxdepth 1 -name "*$RAWSID*" -print -quit 2>/dev/null | grep -q . && fail "(h5d) the RAW sid must NEVER appear in a marker filename, files: $(ls "$MARKD")"
rm -rf "$HKREPO"
ok "(h5d) markers are keyed by sha256(sid)[:16]; the raw sid never lands in a filename"

# --- (h14) STOP CACHE (T-00000836): an unchanged dirty tree after a CLEAN is
# NOT rescanned; a content change rescans; a finding clears the cache. The
# witness is a call TRACE, never a stopwatch.
H13_TRACE="$(mktemp)"
H13_STOP='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s13"}'
P_PAYLOAD="$H13_STOP" P_EVT="--event=stop" P_HOST="claude" P_STUB="cleancount" P_TRACE="$H13_TRACE" run_hook
H13_REPO="$HKREPO"
[ "$HKRC" -eq 0 ] || fail "(h14) a CLEAN Stop must exit 0, got $HKRC — $(cat "$HKE")"
P_REPO="$H13_REPO" P_PAYLOAD="$H13_STOP" P_EVT="--event=stop" P_HOST="claude" P_STUB="cleancount" P_TRACE="$H13_TRACE" run_hook
[ "$(wc -l < "$H13_TRACE" | tr -d ' ')" = "1" ] || fail "(h14) an unchanged tree after CLEAN must NOT rescan: $(wc -l < "$H13_TRACE") semgrep call(s), expected 1"
grep -q '"mode":"hook-cache"' "$H13_REPO/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null \
  || fail "(h14) a Stop served by the cache must still journal its audit line (mode hook-cache, C25)"
printf 'y = 2\n' >> "$H13_REPO/probe.py"
P_REPO="$H13_REPO" P_PAYLOAD="$H13_STOP" P_EVT="--event=stop" P_HOST="claude" P_STUB="cleancount" P_TRACE="$H13_TRACE" run_hook
[ "$(wc -l < "$H13_TRACE" | tr -d ' ')" = "2" ] || fail "(h14) a CHANGED file must rescan: $(wc -l < "$H13_TRACE") call(s), expected 2"
# The content moves FIRST: on an identical tree the cache rightly skips the
# scan (same bytes, same rules => same verdict), so the finding would never run.
printf 'z = 3\n' >> "$H13_REPO/probe.py"
P_REPO="$H13_REPO" P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s13b"}' \
  P_EVT="--event=stop" P_HOST="claude" run_hook
[ -f "$H13_REPO/.agents/state/local/semgrep-hook/stop-propre" ] && fail "(h14) a FINDING must clear the Stop cache"
rm -rf "$H13_REPO" "$H13_TRACE"
ok "(h14) Stop cache: unchanged tree after CLEAN not rescanned, a change rescans, a finding clears it"

# --- (h14b) a file REWRITTEN during the scan never fills the cache: the CLEAN
# belongs to bytes that are no longer on disk (race reproduced in review).
P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s14b"}' \
  P_EVT="--event=stop" P_HOST="claude" P_STUB="cleanmutate" P_MUTATE="/dev/null" run_hook
H14B_REPO="$HKREPO"
# PRÉALABLE PROUVÉ : le 1er Stop CLEAN (sans réécriture) a bien rempli le
# cache — sans ça, « pas de stop-propre » plus bas ne prouverait rien.
[ -f "$H14B_REPO/.agents/state/local/semgrep-hook/stop-propre" ] \
  || fail "(h14b) préalable : le 1er Stop CLEAN n'a pas rempli le cache"
rm -f "$H14B_REPO/.agents/state/local/semgrep-hook/stop-propre"
P_REPO="$H14B_REPO" P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s14b"}' \
  P_EVT="--event=stop" P_HOST="claude" P_STUB="cleanmutate" P_MUTATE="$H14B_REPO/probe.py" run_hook
[ -f "$H14B_REPO/.agents/state/local/semgrep-hook/stop-propre" ] && fail "(h14b) a file rewritten DURING the scan must not fill the Stop cache"
grep -q '"mode":"hook-cache"' "$H14B_REPO/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null \
  && fail "(h14b) no cache hit happened here, yet a hook-cache line was journaled"
rm -rf "$H14B_REPO"
ok "(h14b) a file rewritten during the scan never fills the Stop cache"

# --- (h14c) a CLEAN that carries a TRANSIENT semgrep error (Timeout) never
# fills the cache — a partial answer frozen as clean is a false green; (h14d)
# a PartialParsing error is deterministic, so that CLEAN IS cached.
for H14_CASE in c d; do
  if [ "$H14_CASE" = c ]; then H14_ERR='{"type":"Timeout","path":"probe.py"}'
  else H14_ERR='{"type":["PartialParsing",[]],"path":"probe.py"}'; fi
  H14_STUB="$(mktemp -d)"; assert_tmpdir "$H14_STUB"
  { printf '#!%s\n' "$HK_BASH"
    printf 'echo %s\n' "'{\"results\":[],\"errors\":[$H14_ERR],\"paths\":{\"scanned\":[]}}'"
    printf 'exit 0\n'; } > "$H14_STUB/semgrep"
  chmod +x "$H14_STUB/semgrep"
  H14_REPO="$(mktemp -d)"; assert_tmpdir "$H14_REPO"
  git -C "$H14_REPO" init -q
  git -C "$H14_REPO" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
  printf 'x = 1\n' > "$H14_REPO/probe.py"
  ( cd "$H14_REPO" && printf '%s' '{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s14cd"}' \
      | env PATH="$H14_STUB:$PATH" SEMGREP_CONFIG="$RULESET" AGENTS_HOOK_HOST=claude \
        "$HK_BASH" "$SCRIPT" --hook --event=stop ) >/dev/null 2>&1
  if [ "$H14_CASE" = c ]; then
    [ -f "$H14_REPO/.agents/state/local/semgrep-hook/stop-propre" ] \
      && fail "(h14c) a CLEAN with a Timeout error must NOT fill the Stop cache"
  else
    [ -f "$H14_REPO/.agents/state/local/semgrep-hook/stop-propre" ] \
      || fail "(h14d) a CLEAN with only a PartialParsing error must fill the Stop cache"
  fi
  rm -rf "$H14_STUB" "$H14_REPO"
done
ok "(h14c)(h14d) a transient error (Timeout) never fills the Stop cache; PartialParsing does"

# --- (h6) --event=stop + stop_hook_active:true ON a finding => NEVER exit 2
# (the host's own anti-loop signal short-circuits before any block).
P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":true,"session_id":"s6"}' \
  P_EVT="--event=stop" P_HOST="claude" run_hook
[ "$HKRC" -ne 2 ] || fail "(h6) stop_hook_active must forbid a 2nd exit 2, got $HKRC"
rm -rf "$HKREPO"
ok "(h6) --event=stop + stop_hook_active:true on a finding => never exit 2 (loop guard)"

# --- (h6b) Stop host claude => the systemMessage form, NEVER hookSpecificOutput
P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"s6b"}' \
  P_EVT="--event=stop" P_HOST="claude" run_hook
grep -q 'systemMessage' "$HKO" || fail "(h6b) claude Stop must use the systemMessage form, got: $(cat "$HKO")"
grep -q 'hookSpecificOutput' "$HKO" && fail "(h6b) claude Stop must NEVER use hookSpecificOutput (a PostToolUse shape), got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h6b) Stop host claude => systemMessage form, never hookSpecificOutput"

# --- (h6c) Stop NON-Claude payload under --event=stop, host gemini, dirty
# fixture => the DIRTY TREE is scanned and the finding is NAMED in the systemMessage.
P_PAYLOAD='{"agentType":"dev-multi","sessionId":"s6c","agentId":"a1","transcriptPath":"/t/x"}' \
  P_EVT="--event=stop" P_HOST="gemini" run_hook
[ "$HKRC" -eq 0 ] || fail "(h6c) an envelope host must exit 0 even on a stop finding, got $HKRC — $(cat "$HKE")"
grep -q 'systemMessage' "$HKO" || fail "(h6c) the stop finding must be a systemMessage, got: $(cat "$HKO")"
grep -q 'probe\.py' "$HKO" || fail "(h6c) the dirty-tree finding must NAME the fixture, got: $(cat "$HKO") / err: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h6c) Stop non-Claude under --event=stop => dirty tree scanned, finding named in systemMessage"

# --- (h6d) COPILOT (alignment L-B) POST: its write tool is `create` (MEASURED, P1/P1v,
# 2026-10-12) — payload shape copied from the real canary. The finding on the file the tool
# wrote is NAMED at the ROOT of the object (the NESTED form alone is IGNORED by Copilot, P1/P3)
# AND nested; never « outil inconnu 'create' ». Mutants: `create` out of SCAN, or the root key out.
P_PAYLOAD='{"sessionId":"scp6d","cwd":"/x","toolName":"create","toolArgs":{"file_text":"x = 1\n","path":"@FIX@"},"toolResult":{"resultType":"success"}}' \
  P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h6d) copilot post must exit 0, got $HKRC — $(cat "$HKE")"
grep -q "outil inconnu" "$HKE" && fail "(h6d) the copilot tool 'create' must be READ, never 'outil inconnu': $(cat "$HKE")"
python3 -c '
import json, sys
o = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[0])
assert "probe.py" in o.get("additionalContext", ""), "root additionalContext must NAME the fixture: %r" % o
assert "probe.py" in o["hookSpecificOutput"]["additionalContext"], "nested form kept: %r" % o
' "$HKO" || fail "(h6d) copilot post finding must sit at the ROOT and nested, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h6d) copilot post create => finding at the ROOT (additionalContext) and nested, tool read"

# --- (h6e) COPILOT STOP: `{"decision":"block","reason":…}` — the channel MEASURED at P3 (honoured,
# stop_hook_active present). ONCE per session (the stop-<h16> marker), and MUTE when the host
# re-enters (stop_hook_active true). Other envelope hosts keep the systemMessage ((h6c) above).
P_PAYLOAD='{"sessionId":"scp6e","cwd":"/x","transcriptPath":"/t/x","stopReason":"end_turn","stop_hook_active":false}' \
  P_EVT="--event=stop" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h6e) copilot stop must exit 0, got $HKRC — $(cat "$HKE")"
python3 -c '
import json, sys
o = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[0])
assert o.get("decision") == "block", "decision must be block: %r" % o
assert "probe.py" in o.get("reason", ""), "reason must NAME the fixture: %r" % o
assert "systemMessage" not in o, "no systemMessage beside the block: %r" % o
' "$HKO" || fail "(h6e) copilot stop finding must be decision:block + reason, got: $(cat "$HKO")"
P_REPO="$HKREPO" P_PAYLOAD='{"sessionId":"scp6e","cwd":"/x","stopReason":"end_turn","stop_hook_active":false}' \
  P_EVT="--event=stop" P_HOST="copilot" run_hook
[ -s "$HKO" ] && fail "(h6e) a 2nd stop of the SAME session must be silent (one block per session), got: $(cat "$HKO")"
P_REPO="$HKREPO" P_PAYLOAD='{"sessionId":"scp6f","stopReason":"end_turn","stop_hook_active":true}' \
  P_EVT="--event=stop" P_HOST="copilot" run_hook
[ -s "$HKO" ] && fail "(h6e) stop_hook_active true must be MUTE, got: $(cat "$HKO")"
rm -rf "$HKREPO"
ok "(h6e) copilot stop => decision:block once per session; stop_hook_active => mute"

# --- (h6f) COPILOT, END OF A SUB-AGENT — MEASURED (P4, 2026-10-13, Copilot CLI 1.0.95): the
# Stop fires on BOTH legs at the end of every sub-agent — native `agentStop` (camelCase, marker
# copilot) and the `Stop` of `.claude/settings.json` (snake_case, NO marker). The sub-agent
# payload carries ITS OWN id but the ROOT transcript. Payloads COPIED from the canaries
# (`rt/copilot/P4/agentStop-081644-60783.json` and `-081650-61305.json`,
# `rt/copilot-via-claude/P4/Stop-081646-60919.json` and `Stop-081652-61445.json`), home ->
# /home/user, ids -> SID_RACINE / SID_SOUS_AGENT. Sub-agent: ZERO refusal on both legs; root,
# SAME dirty repo: refused (the sub-agent MUTE never set the root marker); the registry-Claude
# root in a fresh repo: systemMessage + exit 2; the sub-agent payload under codex: judged.
# Mutants killed: exemption removed (sub-agent blocked), `!= ident` removed (root silent), host
# test removed (codex silent).
SID_RACINE="412fbc8b-fdbe-4a0f-837e-085056ae4429"
SID_SOUS_AGENT="af8e4d9a-0536-414f-9d0f-9eea7fda1a67"
TP_P4="/home/user/.copilot/session-state/$SID_RACINE/events.jsonl"
P4_CWD="/home/user/.local/state/cadre/semaine/clones/rt-copilot"
P4_NATIF_SOUS="{\"sessionId\":\"$SID_SOUS_AGENT\",\"timestamp\":1791872204740,\"cwd\":\"$P4_CWD\",\"transcriptPath\":\"$TP_P4\",\"stopReason\":\"end_turn\",\"stop_hook_active\":false}"
P4_NATIF_RACINE="{\"sessionId\":\"$SID_RACINE\",\"timestamp\":1791872210747,\"cwd\":\"$P4_CWD\",\"transcriptPath\":\"$TP_P4\",\"stopReason\":\"end_turn\",\"stop_hook_active\":false}"
P4_CLAUDE_SOUS="{\"hook_event_name\":\"Stop\",\"session_id\":\"$SID_SOUS_AGENT\",\"timestamp\":\"2026-10-13T06:16:44.740Z\",\"cwd\":\"$P4_CWD\",\"transcript_path\":\"$TP_P4\",\"stop_reason\":\"end_turn\",\"stop_hook_active\":false}"
P4_CLAUDE_RACINE="{\"hook_event_name\":\"Stop\",\"session_id\":\"$SID_RACINE\",\"timestamp\":\"2026-10-13T06:16:50.747Z\",\"cwd\":\"$P4_CWD\",\"transcript_path\":\"$TP_P4\",\"stop_reason\":\"end_turn\",\"stop_hook_active\":false}"
P_PAYLOAD="$P4_NATIF_SOUS" P_EVT="--event=stop" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h6f) native sub-agent Stop must exit 0, got $HKRC — $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h6f) native Copilot sub-agent Stop must NOT refuse (the root judges), got: $(cat "$HKO")"
H6F_REPO="$HKREPO"
P_REPO="$H6F_REPO" P_PAYLOAD="$P4_CLAUDE_SOUS" P_EVT="--event=stop" P_HOST="-" run_hook
[ "$HKRC" -eq 0 ] || fail "(h6f) registry-Claude sub-agent Stop under Copilot must exit 0 (no exit 2), got $HKRC — $(cat "$HKE")"
[ -s "$HKO" ] && fail "(h6f) registry-Claude sub-agent Stop under Copilot must NOT refuse, got: $(cat "$HKO")"
P_REPO="$H6F_REPO" P_PAYLOAD="$P4_NATIF_RACINE" P_EVT="--event=stop" P_HOST="copilot" run_hook
python3 -c '
import json, sys
o = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[0])
assert o.get("decision") == "block", "decision must be block: %r" % o
assert "probe.py" in o.get("reason", ""), "reason must NAME the fixture: %r" % o
' "$HKO" || fail "(h6f) the native ROOT Stop on the same dirty repo must be refused, got: $(cat "$HKO")"
rm -rf "$H6F_REPO"
P_PAYLOAD="$P4_CLAUDE_RACINE" P_EVT="--event=stop" P_HOST="-" run_hook
[ "$HKRC" -eq 2 ] || fail "(h6f) the registry-Claude ROOT Stop must exit 2 on a finding, got $HKRC — $(cat "$HKE")"
grep -q 'systemMessage' "$HKO" || fail "(h6f) the registry-Claude ROOT Stop must emit the systemMessage, got: $(cat "$HKO")"
rm -rf "$HKREPO"
P_PAYLOAD="$P4_CLAUDE_SOUS" P_EVT="--event=stop" P_HOST="codex" run_hook
grep -q 'probe\.py' "$HKO" || fail "(h6f) the sub-agent payload under codex must still be judged, got: $(cat "$HKO") / err: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h6f) copilot sub-agent Stop (P4 measured) => zero refusal on both legs; root refused; codex judged"

# --- (h6g) the sub-agent exemption needs the COPILOT LAYOUT, never "UUID parent != id" alone.
# The four transcripts below have a UUID-shaped parent DIFFERENT from the id (so the `!= ident`
# test alone would mute them) but NO Copilot layout: each must still be JUDGED. Mutants killed:
# disposition test removed (S5), `"session-state" in morceaux` (MF), `".copilot" in morceaux`
# (MG), non-consecutive pair (MH), tail without `events.jsonl` (MI).
for H6G_TP in \
  "/home/user/session-state/.claude/projects/$SID_RACINE/events.jsonl" \
  "/home/user/.copilot/.claude/projects/$SID_RACINE/events.jsonl" \
  "/home/user/.copilot/x/session-state/y/$SID_RACINE/events.jsonl" \
  "/home/user/x/session-state/$SID_RACINE/transcript.jsonl"; do
  P_PAYLOAD="{\"hook_event_name\":\"Stop\",\"session_id\":\"$SID_SOUS_AGENT\",\"cwd\":\"$P4_CWD\",\"transcript_path\":\"$H6G_TP\",\"stop_hook_active\":false}" \
    P_EVT="--event=stop" P_HOST="-" run_hook
  [ "$HKRC" -eq 2 ] || fail "(h6g) no Copilot layout ($H6G_TP): the Stop must be judged (exit 2), got $HKRC — $(cat "$HKO")"
  grep -q 'probe\.py' "$HKO" || fail "(h6g) no Copilot layout ($H6G_TP): the finding must be named, got: $(cat "$HKO")"
  rm -rf "$HKREPO"
  P_PAYLOAD="{\"sessionId\":\"$SID_SOUS_AGENT\",\"cwd\":\"$P4_CWD\",\"transcriptPath\":\"$H6G_TP\",\"stopReason\":\"end_turn\",\"stop_hook_active\":false}" \
    P_EVT="--event=stop" P_HOST="copilot" run_hook
  grep -q '"decision"' "$HKO" || fail "(h6g) native leg, no Copilot layout ($H6G_TP): must be refused, got: $(cat "$HKO")"
  rm -rf "$HKREPO"
done
ok "(h6g) UUID parent != id WITHOUT the Copilot layout => still judged on both legs (S5/MF/MG/MH/MI)"

# --- (h7) usage errors: --hook --at HEAD and --hook --event=pre => exit 2 -----
OUT_H7A="$( echo '{}' | "$SUITE_BASH" "$SCRIPT" --hook --at HEAD 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(h7) --hook --at HEAD must exit 2 (perimeter option with --hook), got $rc — $OUT_H7A"
OUT_H7B="$( echo '{}' | "$SUITE_BASH" "$SCRIPT" --hook --event=pre 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(h7) --hook --event=pre must exit 2 (bad event), got $rc — $OUT_H7B"
OUT_H7C="$( echo '{}' | "$SUITE_BASH" "$SCRIPT" --event=post 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(h7) --event without --hook must exit 2, got $rc — $OUT_H7C"
ok "(h7) usage: --hook+--at, --hook+--event=pre, and --event without --hook all exit 2"

# --- (h8) C2: the HEADER (every line before the first `set -`) carries NO rule
# COUNT — it reddens the day someone writes one back (L-00000111/L-00000187).
HEADER="$(sed -n '1,/^set -/p' "$SCRIPT")"
if printf '%s' "$HEADER" | grep -Eiq '[0-9]+ (rules|règles|regles)'; then
  fail "(h8) the header regained a rule COUNT — a delayed lie the day a rule is added: $(printf '%s' "$HEADER" | grep -Ei '[0-9]+ (rules|règles|regles)')"
fi
ok "(h8) C2: the header quotes no rule count (reddens if one returns)"

# --- (h9) the stderr location list is BOUNDED at 10 + '(+N non listés)' --------
# STUB_FINDINGS=12 => EXACTLY 10 lines of the shape `rule-id file:line`, in order
# 1..10, then ONE overflow line — never a raw stderr line count.
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"s9"}' \
  P_EVT="--event=post" P_HOST="claude" P_FINDINGS=12 run_hook
loc_n="$(grep -cE '^[^ ]+ [^:]+:[0-9]+$' "$HKE")"
[ "$loc_n" -eq 10 ] || fail "(h9) exactly 10 location lines expected, got $loc_n — $(cat "$HKE")"
grep -qE '^stub\.rule\.1 probe\.py:1$'  "$HKE" || fail "(h9) the list must start at finding 1, got: $(cat "$HKE")"
grep -qE '^stub\.rule\.10 probe\.py:10$' "$HKE" || fail "(h9) the list must run through finding 10 in order, got: $(cat "$HKE")"
grep -q '(+2 non listés)' "$HKE" || fail "(h9) the overflow must be announced as '(+2 non listés)', got: $(cat "$HKE")"
rm -rf "$HKREPO"
ok "(h9) stderr locations bounded at 10 (in order 1..10) + '(+2 non listés)' overflow line"

# --- (h10) [class-1, CWE-22] path CONFINEMENT. A payload carrying BOTH a
# relative `..` path AND an ABSOLUTE out-of-repo path, EACH pointing at a REAL
# covered (.py) file, must scan NOTHING outside root and SAY it rejected. A PoC
# once made semgrep open and read a file levels above root, chosen from STDIN
# (CWE-22); normalize_path now confines every candidate to root and a PHASE-B
# shell belt backs it up. The two files are REAL (not just missing) so the
# mutation that removes the confinement reddens THIS arm — the finding stub would
# then report on the out-of-repo file that got scanned.
h10repo="$(mktemp -d)"; assert_tmpdir "$h10repo"
h10parent="$(dirname "$h10repo")"
git -C "$h10repo" init -q
git -C "$h10repo" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
printf 'x = 1\n' > "$h10repo/probe.py"
printf 'import os\nos.system("id")\n' > "$h10parent/poc_a_$$.py"     # (a) real .py in the PARENT, reached by ../
h10out="$(mktemp -d)"; assert_tmpdir "$h10out"
printf 'import os\nos.system("id")\n' > "$h10out/poc_b.py"           # (b) real .py elsewhere, reached by ABSOLUTE
P_REPO="$h10repo" \
  P_PAYLOAD="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":[\"../poc_a_$$.py\",\"$h10out/poc_b.py\"]},\"session_id\":\"s10\"}" \
  P_EVT="--event=post" P_HOST="claude" run_hook
[ "$HKRC" -eq 0 ] || fail "(h10) a confined-away payload must never block (exit 0), got $HKRC — $(cat "$HKE")"
grep -qE 'stub\.rule' "$HKE" "$HKO" && fail "(h10/CWE-22) NOTHING outside root may be scanned — a stub finding means an out-of-repo file was read: $(cat "$HKE") / $(cat "$HKO")"
grep -q 'poc_[ab]' "$HKE" "$HKO" && fail "(h10) an out-of-repo path leaked into the output — not confined: $(cat "$HKE") / $(cat "$HKO")"
# LE REFUS EST DIT, ET IL EST DIT AVEC SA VRAIE CAUSE. Cet arm exigeait
# « clé de chemin inconnue » — le libellé était HONNÊTE SUR LE FOND (rien n'a été
# scanné) et TROMPEUR SUR LA CAUSE : la clé `file_path` a bel et bien été
# trouvée, c'est le CHEMIN que le confinement a refusé. Résidu nommé le
# 2026-09-10 (T-00000556), corrigé le 2026-09-12. Conséquence mesurée du
# libellé faux : TOUTE écriture hors dépôt — chaque fichier de scratchpad —
# imprimait une dégradation accusant la liste des clés, et un canal qui crie à
# la mauvaise cause finit ignoré, donc muet le jour où il compte (L-00000136).
grep -q 'CONFINÉ hors racine' "$HKE" || fail "(h10) the rejection must be SAID, and NAME the confinement, got: $(cat "$HKE")"
grep -q 'clé de chemin inconnue' "$HKE" && fail "(h10) the confinement must NOT be reported as an unknown path key — the key WAS found: $(cat "$HKE")"
rm -rf "$h10repo" "$h10out"; rm -f "$h10parent/poc_a_$$.py"
ok "(h10) CWE-22 confinement: a ..+absolute out-of-repo payload scans nothing outside root and says it rejected, NAMING the confinement"

# --- (h11) ABSOLUTE in-repo file_path — the graphy Claude Code REALLY emits
# (post-edit-check.sh:6 passes an absolute path). A relative fixture proves the
# PARSER; only an absolute one proves the WIRING. normalize_path resolves it back
# under root and it scans; host claude => exit 2, rule named on the fixture. An
# arm that only ever sends the relative form (handier for a fixture) would leave
# the graphy Claude actually emits untested — nothing would redden if it broke.
h11repo="$(mktemp -d)"; assert_tmpdir "$h11repo"
git -C "$h11repo" init -q
git -C "$h11repo" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
printf 'x = 1\n' > "$h11repo/probe.py"
P_REPO="$h11repo" \
  P_PAYLOAD="{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$h11repo/probe.py\"},\"session_id\":\"s11\"}" \
  P_EVT="--event=post" P_HOST="claude" run_hook
[ "$HKRC" -eq 2 ] || fail "(h11) an ABSOLUTE in-repo file_path must scan and exit 2, got $HKRC — $(cat "$HKE")"
grep -qE '^stub\.rule\.1 probe\.py:1$' "$HKE" || fail "(h11) the rule must be named on the fixture parsed from the absolute path, got: $(cat "$HKE")"
rm -rf "$h11repo"
ok "(h11) ABSOLUTE in-repo file_path (Claude's real graphy) => confined back under root, scanned, exit 2"

# --- (h12) the audit JOURNAL records the RESOLVED event, not the raw --event
# flag (exec-critic: a `hook_event_name:Stop` charge with NO flag once wrote
# "event":"post"). semgrep ABSENT forces the DEGRADED directive branch; PHASE A
# resolved 'stop' from hook_event_name and now writes it into the directive, so
# the journal must read "event":"stop", never the flag's default "post".
P_PAYLOAD='{"hook_event_name":"Stop","session_id":"s12"}' \
  P_EVT="" P_HOST="claude" P_STUB="absent" P_FIX="" run_hook
AUDITLOG="$HKREPO/.agents/state/local/sca-reports/audit-log.jsonl"
[ -f "$AUDITLOG" ] || fail "(h12) precondition: the audit journal must exist at $AUDITLOG"
grep -q '"mode":"hook","event":"stop"' "$AUDITLOG" || fail "(h12) the journal must record the RESOLVED event 'stop', got: $(cat "$AUDITLOG")"
grep -q '"mode":"hook","event":"post"' "$AUDITLOG" && fail "(h12) a Stop payload with NO flag must NOT be journaled as 'post' (the flag, not the resolved event): $(cat "$AUDITLOG")"
rm -rf "$HKREPO"
ok "(h12) audit journal records the RESOLVED event (hook_event_name:Stop, no flag => event:stop), never the raw flag"

# --- (h13) DEGRADED FORM CLOSED PER EVENT (T-00000479) — post = the two-key
# union {systemMessage, hookSpecificOutput.additionalContext}; stop = systemMessage
# alone. assert_form pins the KEY SET by EQUALITY, so this reddens if a later lot
# DROPS a key in post OR ADDS one at stop. Every cell first pins HKRC==0 (exact,
# never !=2: a missing binary exits 127 and would green a cell that read nothing).
# Each fail NAMES its cell (stub/host/event) and JOINS python's key-diff (C4).
HKFERR="$(mktemp)"
# $3 = the cell's AGENTS_HOOK_HOST, MANDATORY (C6, T-01M4RWC0DBM6XC1PDQGEG4P79C):
# under copilot the post set ADDS a top-level additionalContext equal to the
# nested one; under any other host it stays {systemMessage, hookSpecificOutput}.
# Mandatory so a cell that forgets its host fails loudly instead of being judged
# against the non-copilot set in silence.
assert_form() {   # $1 = post|stop ; $2 = cell label (stub/host/event) ; $3 = host
  [ -n "${3:-}" ] || fail "(h13 $2) assert_form needs the cell host as its 3rd argument"
  [ -s "$HKO" ] || fail "(h13 $2) precondition: stdout must be non-empty"
  HK_FORM_FILE="$HKO" HK_FORM_EVT="$1" HK_FORM_HOST="$3" "$PY" - 2>"$HKFERR" <<'PYEOF'
import os, sys, json
evt   = os.environ["HK_FORM_EVT"]
host  = os.environ["HK_FORM_HOST"]
raw   = open(os.environ["HK_FORM_FILE"], encoding="utf-8").read()
lines = [l for l in raw.splitlines() if l.strip()]
if len(lines) != 1:
    sys.stderr.write("expected EXACTLY one non-empty line, got %d: %r\n" % (len(lines), lines)); sys.exit(1)
try:
    obj = json.loads(lines[0])
except Exception as e:
    sys.stderr.write("stdout is not JSON (%s): %r\n" % (e, lines[0])); sys.exit(1)
if not isinstance(obj, dict):
    sys.stderr.write("stdout JSON is not an object: %r\n" % (obj,)); sys.exit(1)
keys = set(obj.keys())
if evt == "post":
    want = {"systemMessage", "hookSpecificOutput"}
    if host == "copilot":
        want = want | {"additionalContext"}
    if keys != want:
        sys.stderr.write("post key set %r != %r (host %s)\n" % (sorted(keys), sorted(want), host)); sys.exit(1)
    hso = obj["hookSpecificOutput"]
    if not isinstance(hso, dict) or hso.get("hookEventName") != "PostToolUse":
        sys.stderr.write("hookEventName %r != 'PostToolUse'\n" % (hso.get("hookEventName") if isinstance(hso, dict) else hso,)); sys.exit(1)
    if hso.get("additionalContext") != obj["systemMessage"]:
        sys.stderr.write("additionalContext != systemMessage (%r vs %r)\n" % (hso.get("additionalContext"), obj["systemMessage"])); sys.exit(1)
    if host == "copilot" and obj["additionalContext"] != hso.get("additionalContext"):
        sys.stderr.write("top-level additionalContext != nested (%r vs %r)\n" % (obj["additionalContext"], hso.get("additionalContext"))); sys.exit(1)
    if not str(obj["systemMessage"]).startswith("COVERAGE DEGRADED"):
        sys.stderr.write("systemMessage does not start with COVERAGE DEGRADED: %r\n" % (obj["systemMessage"],)); sys.exit(1)
else:
    want = {"systemMessage"}
    if keys != want:
        sys.stderr.write("stop key set %r != %r\n" % (sorted(keys), sorted(want))); sys.exit(1)
sys.exit(0)
PYEOF
  rc=$?
  [ "$rc" -eq 0 ] || fail "(h13 $2) DEGRADED form not closed for event=$1 (rc=$rc): $(cat "$HKFERR")"
}

# post cell 1: semgrep absent, gemini (repo KEPT for (h13b))
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13a"}' \
  P_EVT="--event=post" P_HOST="gemini" P_STUB="absent" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 absent/gemini/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "absent/gemini/post" gemini
h13a_repo="$HKREPO"

# post cell 2: inert (stepIdx, no path), gemini
P_PAYLOAD='{"stepIdx":1,"conversationId":"ch13","transcriptPath":"/t/x"}' \
  P_EVT="--event=post" P_HOST="gemini" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 inert/gemini/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "inert/gemini/post" gemini
rm -rf "$HKREPO"

# post cell 3: no python on PATH, codex
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13c"}' \
  P_EVT="--event=post" P_HOST="codex" P_STUB="nopython" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 nopython/codex/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "nopython/codex/post" codex
rm -rf "$HKREPO"

# post cell 4: unknown tool carrying a path, copilot
P_PAYLOAD='{"tool_name":"WriteFile","tool_input":{"file_path":"@FIX@"},"session_id":"sh13d"}' \
  P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 unknowntool/copilot/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "unknowntool/copilot/post" copilot
rm -rf "$HKREPO"

# post cell 5: SCAN tool with NO path key, kimi (unknown host; DEGRADED still exit 0)
P_PAYLOAD='{"tool_name":"Edit","tool_input":{},"session_id":"sh13e"}' \
  P_EVT="--event=post" P_HOST="kimi" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 unknownkey/kimi/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "unknownkey/kimi/post" kimi
rm -rf "$HKREPO"

# post cell 6: non-JSON payload, copilot
P_PAYLOAD='this is { not json' P_EVT="--event=post" P_HOST="copilot" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 nonjson/copilot/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "nonjson/copilot/post" copilot
rm -rf "$HKREPO"

# post cell 7: PHASE B report unreadable (semgrep exits 3, empty report), gemini
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13g"}' \
  P_EVT="--event=post" P_HOST="gemini" P_STUB="error" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 error/gemini/post) must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'report not readable JSON' "$HKE" || fail "(h13 error/gemini/post) PHASE B must announce 'report not readable JSON', got: $(cat "$HKE")"
assert_form post "error/gemini/post" gemini
rm -rf "$HKREPO"

# stop cell 8: semgrep absent under --event=stop, gemini => systemMessage alone
P_PAYLOAD='{"hook_event_name":"Stop","session_id":"sh13h"}' \
  P_EVT="--event=stop" P_HOST="gemini" P_STUB="absent" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 absent/gemini/stop) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form stop "absent/gemini/stop" gemini
rm -rf "$HKREPO"

# stop cell 9: no python, driven WITHOUT the flag (C2) so the payload's
# hook_event_name reaches the grep fall-back — a --event=stop would fill the flag
# and NEVER exercise the fall-back at :555-561. host claude.
P_PAYLOAD='{"hook_event_name":"Stop","session_id":"sh13i"}' \
  P_EVT="" P_HOST="claude" P_STUB="nopython" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 nopython/claude/stop) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form stop "nopython/claude/stop" claude
rm -rf "$HKREPO"

# post cell 10 (T-01M4RWC0DBM6XC1PDQGEG4P79C): no python on PATH, copilot — the
# shell printf branch, the one emitter PHASE A/B never reach.
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13j"}' \
  P_EVT="--event=post" P_HOST="copilot" P_STUB="nopython" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 nopython/copilot/post) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form post "nopython/copilot/post" copilot
rm -rf "$HKREPO"

# post cell 11 (T-01M4RWC0DBM6XC1PDQGEG4P79C): PHASE B degraded, copilot.
P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13k"}' \
  P_EVT="--event=post" P_HOST="copilot" P_STUB="error" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 error/copilot/post) must exit 0, got $HKRC — $(cat "$HKE")"
grep -q 'report not readable JSON' "$HKE" || fail "(h13 error/copilot/post) PHASE B must announce 'report not readable JSON', got: $(cat "$HKE")"
assert_form post "error/copilot/post" copilot
rm -rf "$HKREPO"

# stop cell 12 (T-01M4RWC0DBM6XC1PDQGEG4P79C): the stop branch is UNCHANGED under
# copilot — systemMessage alone, no top-level additionalContext.
P_PAYLOAD='{"hook_event_name":"Stop","session_id":"sh13l"}' \
  P_EVT="--event=stop" P_HOST="copilot" P_STUB="absent" P_FIX="" run_hook
[ "$HKRC" -eq 0 ] || fail "(h13 absent/copilot/stop) must exit 0, got $HKRC — $(cat "$HKE")"
assert_form stop "absent/copilot/stop" copilot
rm -rf "$HKREPO"

ok "(h13) DEGRADED form CLOSED per event: post = two-key union (+ top-level additionalContext under copilot), stop = systemMessage alone (12 cells, key-set equality)"

# --- (h13b) the two-key union does NOT reopen the once-per-session vacuity: a 2nd
# call on the absent/gemini cell (same sid) must leave stdout EMPTY.
P_REPO="$h13a_repo" P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh13a"}' \
  P_EVT="--event=post" P_HOST="gemini" P_STUB="absent" run_hook
[ -s "$HKO" ] && fail "(h13b absent/gemini/post) the 2nd call (same sid) must leave stdout empty, got: $(cat "$HKO")"
rm -rf "$h13a_repo"
ok "(h13b) the two-key union keeps the once-per-session vacuity: 2nd call leaves stdout empty"

# --- (h15) A MALFORMED REPORT, OR A DEAD PHASE B, IS SAID TO EVERY HOST
# (T-01M52EC9PE7758B4ZG95YXMSJN). Measured on 6fc0450c: `{}` read CLEAN (stdout
# empty, the Stop cache filled); `[1]` killed PHASE B with a traceback on stderr
# alone, stdout EMPTY on claude, codex and copilot. Six cells: noresults post/
# claude and stop/codex, liste post/copilot and stop/gemini (PHASE B's
# degrade()), meurt post/copilot and post/gemini (the two post printf of the
# shell belt; its stop printf is (hrs2)). Each: rc 0, ONE line in the closed
# DEGRADED form of its host/event, the reason on stderr.
h15_cell() {  # $1 stub  $2 post|stop  $3 host  $4 reason on stderr
  if [ "$2" = "stop" ]; then
    P_PAYLOAD='{"hook_event_name":"Stop","session_id":"sh15"}' \
      P_EVT="--event=stop" P_HOST="$3" P_STUB="$1" run_hook
  else
    P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"sh15"}' \
      P_EVT="--event=post" P_HOST="$3" P_STUB="$1" run_hook
  fi
  [ "$HKRC" -eq 0 ] || fail "(h15 $1/$3/$2) must exit 0, got $HKRC — $(cat "$HKE")"
  grep -q "$4" "$HKE" || fail "(h15 $1/$3/$2) the reason « $4 » must be on stderr, got: $(cat "$HKE")"
  assert_form "$2" "$1/$3/$2" "$3"
  rm -rf "$HKREPO"
}
h15_cell noresults post claude 'semgrep report malformed'
h15_cell noresults stop codex 'semgrep report malformed'
h15_cell liste post copilot 'semgrep report malformed'
h15_cell liste stop gemini 'semgrep report malformed'
h15_cell meurt post copilot 'the report phase died before any verdict'
h15_cell meurt post gemini 'the report phase died before any verdict'
ok "(h15) malformed report (noresults, liste) and dead PHASE B (meurt): rc 0, the reason on stderr, ONE line in the closed DEGRADED form per host/event (6 cells)"

# --- (hng) Angular through the REAL hook (T-01M5DFN4GRJMVQ4QZ1D88D6TXG lot C):
# P_STUB=none keeps the real semgrep on PATH, so the real ruleset decides.
# A post Edit of a trapped .ts on host claude exits 2 and NAMES both rules at
# their line; the clean twin exits 0 and names none. SKIP announced without
# semgrep. Mutations that redden: a rule removed (its name absent from
# stderr); the literal `pattern-not` dropped or the bypass widened (the clean
# twin blocks). Severity is (aj)'s pin: the hook blocks a WARNING as well.
if [ "$HAVE_SEMGREP" -eq 1 ]; then
  hng_pos='export function f(s: any, el: any, r: any, v: string) {
  el.x = s.bypassSecurityTrustUrl(v);
  el.outerHTML = v;
  el.y = s["bypassSecurityTrustResourceUrl"](v);
  r.setProperty(el, "outerHTML", v);
}'
  hng_neg='import { SecurityContext } from "@angular/core";
export function g(s: any, el: any, r: any, v: string) {
  el.x = s.sanitize(1, v);
  el.outerHTML = "<i>fixed</i>";
  el.y = s.bypassSecurityTrustResourceUrl("https://www.youtube.com/embed/x");
  el.innerHTML = s.sanitize(SecurityContext.HTML, v);
}'
  P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"shng1"}' \
    P_EVT="--event=post" P_HOST="claude" P_STUB="none" P_FIX="pos.ts" P_FIXBODY="$hng_pos" run_hook
  [ "$HKRC" -eq 2 ] || fail "(hng/trap) a trapped .ts edit must exit 2 through the real ruleset, got $HKRC — $(cat "$HKE")"
  grep -qE 'angular-bypass-security-trust pos\.ts:2$' "$HKE" \
    || fail "(hng/trap) stderr must name angular-bypass-security-trust at pos.ts:2, got: $(cat "$HKE")"
  grep -qE 'angular-dom-innerhtml-dynamic pos\.ts:3$' "$HKE" \
    || fail "(hng/trap) stderr must name angular-dom-innerhtml-dynamic at pos.ts:3, got: $(cat "$HKE")"
  grep -qE 'angular-bypass-security-trust pos\.ts:4$' "$HKE" \
    || fail "(hng/trap) stderr must name the INDEXED bypass at pos.ts:4, got: $(cat "$HKE")"
  grep -qE 'angular-dom-innerhtml-dynamic pos\.ts:5$' "$HKE" \
    || fail "(hng/trap) stderr must name Renderer2.setProperty outerHTML at pos.ts:5, got: $(cat "$HKE")"
  rm -rf "$HKREPO"
  P_PAYLOAD='{"tool_name":"Edit","tool_input":{"file_path":"@FIX@"},"session_id":"shng2"}' \
    P_EVT="--event=post" P_HOST="claude" P_STUB="none" P_FIX="neg.ts" P_FIXBODY="$hng_neg" run_hook
  [ "$HKRC" -eq 0 ] || fail "(hng/clean) the clean .ts twin must exit 0, got $HKRC — $(cat "$HKE")"
  grep -q 'angular-' "$HKE" && fail "(hng/clean) the clean .ts twin must name no Angular rule, got: $(cat "$HKE")"
  rm -rf "$HKREPO"
  ok "(hng) real hook: trapped .ts => exit 2 naming both Angular rules at their line; clean twin => exit 0"
else
  ok "(hng) Angular through the real hook  [SKIP: semgrep not installed — (aj) pins ran]"
fi

# --- (z) parse + run the SCRIPT under the OLDEST bash on this machine ----------
# T-00000477 S2.4. This suite resolves its runs onto $SUITE_BASH; here we pick
# the OLDEST bash among candidates and (z1) PARSE the live script under it, after
# (z0a/z0b) proving the sensor actually BITES the crash class — a fixture that
# never wrote would pass a naive `rc != 0` (a missing file exits 127), so we demand
# rc==2 AND guard existence with -s. `${SUITE_BASH_CANDIDATES-…}` uses NO colon:
# UNSET => default list; SET even EMPTY => it REPLACES the list (the set-but-empty
# case is what run-bash-tests.sh's channel proof exercises; a `:-` would fold it
# into "default" and kill that proof silently).
CANDS_STR="${SUITE_BASH_CANDIDATES-$SUITE_BASH /bin/bash /usr/bin/bash}"
read -r -a CANDS <<< "$CANDS_STR" || true
OLDEST=""; OLDEST_MAJ=""; Z_SEEN=""; Z_SKIPPED=""
for cand in ${CANDS[@]+"${CANDS[@]}"}; do
  if [ ! -x "$cand" ]; then Z_SKIPPED="$Z_SKIPPED $cand(absent)"; continue; fi
  maj="$("$cand" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null)" || maj=""
  case "$maj" in
    ''|*[!0-9]*) Z_SKIPPED="$Z_SKIPPED $cand(sonde-KO)"; continue ;;
  esac
  Z_SEEN="$Z_SEEN $cand:$maj"
  if [ -z "$OLDEST_MAJ" ] || [ "$maj" -lt "$OLDEST_MAJ" ]; then OLDEST_MAJ="$maj"; OLDEST="$cand"; fi
done

if [ -z "$OLDEST" ] || [ "$OLDEST_MAJ" -ge 4 ]; then
  cand_desc="${Z_SEEN# }"
  [ -n "$cand_desc" ] || cand_desc="aucun — SUITE_BASH_CANDIDATES défini vide"
  [ -z "$Z_SKIPPED" ] || cand_desc="$cand_desc ; écartés :${Z_SKIPPED}"
  echo "  SKIP (z): aucun bash < 4 sur cette machine (candidats : $cand_desc) — parse sous /bin/bash 3.2 NON mesuré"
else
  # (z0a)/(z0b) SENTINELS — the fixtures are written at TOP LEVEL (heredoc, never
  # inside a "$( )") so this *.test.sh does not redden itself. FOUR lines: `EOF)"`
  # on one line would not terminate the heredoc and the fixture would prove nothing.
  Z_TMP="$(mktemp -d)"; assert_tmpdir "$Z_TMP"
  cat > "$Z_TMP/z0-bad.sh" <<'FIX'
X="$(cat <<'EOF'
this repo's own comment
EOF
)"
FIX
  cat > "$Z_TMP/z0-ok.sh" <<'FIX'
X="$(cat <<'EOF'
this repo own comment
EOF
)"
FIX
  [ -s "$Z_TMP/z0-bad.sh" ] && [ -s "$Z_TMP/z0-ok.sh" ] \
    || { rm -rf "$Z_TMP"; fail "(z0) fixtures non écrites"; }
  "$OLDEST" -n "$Z_TMP/z0-bad.sh" 2>/dev/null; rc=$?
  [ "$rc" -eq 2 ] \
    || { rm -rf "$Z_TMP"; fail "(z0a) le capteur ne mord pas sur la classe (OLDEST=$OLDEST_MAJ, rc=$rc)"; }
  "$OLDEST" -n "$Z_TMP/z0-ok.sh" 2>/dev/null; rc=$?
  [ "$rc" -eq 0 ] \
    || { rm -rf "$Z_TMP"; fail "(z0b) fixture illisible ou OLDEST inapte — (z0a) n'a rien prouvé (rc=$rc)"; }
  rm -rf "$Z_TMP"
  ok "(z0) le capteur mord la classe sous bash $OLDEST_MAJ ($OLDEST): guillemets+heredoc+apostrophe => rc 2, contrôle sans apostrophe => rc 0"

  # (z1) the LIVE script must PARSE clean under the oldest bash.
  "$OLDEST" -n "$SCRIPT"; rc=$?
  [ "$rc" -eq 0 ] || fail "(z1) semgrep-scan.sh doit parser sous bash $OLDEST_MAJ ($OLDEST), rc=$rc"
  ok "(z1) semgrep-scan.sh parse sous le plus vieux bash de cette machine ($OLDEST_MAJ)"

  # (z2) FUNCTIONAL parity: rc IDENTICAL and reduced stderr identical under OLDEST
  # vs SUITE_BASH. Reduction keeps only semgrep-scan:/COVERAGE DEGRADED lines with
  # temp paths canonicalised; timestamps and emit-event.sh output fall out naturally.
  z_reduce() { sed -E 's#(/var/folders|/tmp|/private/tmp)/[^ ]*#<TMP>#g' | grep -E '^semgrep-scan:|COVERAGE DEGRADED' || true; }
  if [ "$HAVE_SEMGREP" -eq 1 ]; then
    z_dir="$(committed_fixture "legacy.c" <<'CEOF'
int main(void){ return 0; }
CEOF
)"
    Z_OUT_OLD="$( cd "$z_dir" && SEMGREP_CONFIG="$RULESET" "$OLDEST" "$SCRIPT" 2>&1 )"; z_rc_old=$?
    Z_OUT_NEW="$( cd "$z_dir" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" 2>&1 )"; z_rc_new=$?
    rm -rf "$z_dir"
  else
    Z_OUT_OLD="$( SUITE_BASH="$OLDEST" run_isolated_path scanned-empty legacy.c <<'CEOF'
int main(void){ return 0; }
CEOF
)"; z_rc_old=$?
    Z_OUT_NEW="$( run_isolated_path scanned-empty legacy.c <<'CEOF'
int main(void){ return 0; }
CEOF
)"; z_rc_new=$?
  fi
  [ "$z_rc_old" -eq "$z_rc_new" ] \
    || fail "(z2) rc diverge sous bash $OLDEST_MAJ vs SUITE_BASH : $z_rc_old vs $z_rc_new"
  z_red_old="$(printf '%s\n' "$Z_OUT_OLD" | z_reduce)"
  z_red_new="$(printf '%s\n' "$Z_OUT_NEW" | z_reduce)"
  [ "$z_red_old" = "$z_red_new" ] \
    || fail "(z2) stderr réduit diverge sous bash $OLDEST_MAJ : [$z_red_old] vs [$z_red_new]"
  ok "(z2) run fonctionnel à parité sous le plus vieux bash ($OLDEST_MAJ): rc + stderr réduit identiques"
fi

# ==== T-01M4RWC6VHHN479J2A9RRY1BE3 : SORTIE PRÉCOCE SOUS COPILOT, --hook --event=post ====
# (v) UN OBSERVABLE NOMMÉ (C3 du plan), JAMAIS le stdout : à la base il est VIDE
# pour `view` (dans IGNORE), `grep` ET `ask_user` (« rien à faire »), donc un bras
# jugé sur le stdout serait vert à la base. Le nom joué est `grep` : listé, et
# absent d'IGNORE. Le script tourne depuis un `mktemp -d` hors dépôt (ROOT = ce
# répertoire), TMPDIR à côté, la charge sur stdin, et un bouchon `git` en tête
# de PATH qui consigne son appel puis exécute le vrai binaire — écrit seulement
# pour un chemin ABSOLU (un bouchon de fonction shell se rappelle lui-même :
# 17 123 appels mesurés). Mesuré à la base : bouchon git x1 et
# ./.agents/state/local/semgrep-hook/ créé. Attendu : un nom LISTÉ sort avant
# tout git, mktemp ou mkdir ; les témoins (un exclu, bash, un nom vide, la forme
# groupée, `grep` sous codex) gardent les observables de la base.
lc_run() {  # $1 hôte, $2 charge -> LC_RC LC_GIT LC_AGENTS
  local hote="$1" charge="$2" p reel
  p="$(mktemp -d)"; assert_tmpdir "$p"
  mkdir -p "$p/w" "$p/bouchons" "$p/tmp" "$p/ev"
  : > "$p/trace"
  reel="$(command -v git 2>/dev/null || true)"
  case "$reel" in
    /*)
      {
        printf '#!/bin/sh\n'
        printf 'printf "%%s\\n" "git" >> "%s"\n' "$p/trace"
        printf 'exec "%s" "$@"\n' "$reel"
      } > "$p/bouchons/git"
      chmod +x "$p/bouchons/git"
      ;;
  esac
  ( cd "$p/w" && printf '%s' "$charge" \
      | env PATH="$p/bouchons:$PATH" TMPDIR="$p/tmp" AGENTS_EVENTS_DIR="$p/ev" AGENTS_HOOK_HOST="$hote" SEMGREP_CONFIG="$RULESET" \
          "$SUITE_BASH" "$SCRIPT" --hook --event=post ) >/dev/null 2>&1
  LC_RC=$?
  LC_GIT="$(grep -c '^git$' "$p/trace" || true)"
  LC_AGENTS=0
  [ -e "$p/w/.agents" ] && LC_AGENTS=1
  rm -rf "$p"
}
case "$(command -v git 2>/dev/null || true)" in
  /*)
    LC_GREP='{"toolName":"grep","toolArgs":{"pattern":"x","paths":["src"]}}'
    lc_run copilot "$LC_GREP"
    [ "$LC_GIT" -eq 0 ] || fail "(v1) copilot + grep (listé) : bouchon git appelé $LC_GIT fois, attendu 0 (base : 1)"
    [ "$LC_AGENTS" -eq 0 ] || fail "(v1) copilot + grep (listé) : ./.agents créé (semgrep-hook/), attendu aucun artefact"
    [ "$LC_RC" -eq 0 ] || fail "(v1) copilot + grep (listé) : rc $LC_RC, attendu 0"
    ok "(v1) copilot + grep (listé) : sortie avant tout git/mktemp/mkdir — 0 git, aucun ./.agents"
    lc_temoin() {  # $1 étiquette, $2 hôte, $3 charge
      lc_run "$2" "$3"
      [ "$LC_GIT" -ge 1 ] || fail "(v2) $1 : bouchon git jamais appelé — un nom non listé garde le chemin de la base"
      [ "$LC_AGENTS" -eq 1 ] || fail "(v2) $1 : aucun ./.agents écrit — un nom non listé garde le chemin de la base"
    }
    lc_temoin "copilot + exclu web_fetch" copilot '{"toolName":"web_fetch","toolArgs":{"url":"https://x.invalid/"}}'
    lc_temoin "copilot + bash" copilot '{"toolName":"bash","toolArgs":{"command":"ls"}}'
    lc_temoin "copilot + nom vide" copilot '{"toolName":"","toolArgs":{"path":"a"}}'
    lc_temoin "copilot + forme groupée" copilot '{"toolCalls":[{"toolName":"grep","toolArgs":{"pattern":"x"}}]}'
    lc_temoin "codex + grep" codex "$LC_GREP"
    ok "(v2) exclu, bash, nom vide, forme groupée et grep sous codex gardent les observables de la base (git appelé, ./.agents écrit)"
    ;;
  *)
    echo "  SKIP (v): git absent ou hors chemin absolu — l'observable nommé est le bouchon git"
    ;;
esac

# --- (sv5) T-01M4W80Q5C3F6G99G0JXJB3RH4: the HOOK neither writes nor removes the
# common verdict — a stale one survives a `--hook --event=stop` run BYTE FOR
# BYTE (the removal sits AFTER the hook dispatch). Non-vacuity: the Stop run
# reached the scan, the stub's finding is named. Mutant: the removal moved
# before the hook dispatch.
SV5_REPO="$(mktemp -d)"; assert_tmpdir "$SV5_REPO"
git -C "$SV5_REPO" init -q
git -C "$SV5_REPO" -c user.email="t@t.l" -c user.name="t" commit -q --allow-empty -m init
printf 'x = 1\n' > "$SV5_REPO/probe.py"
SV5_V="$SV5_REPO/.agents/state/local/sca-reports/semgrep-verdict.json"
mkdir -p "${SV5_V%/*}"
printf '{"sentinelle":"sv5"}\n' > "$SV5_V"
SV5_REF="$(mktemp)"
cp "$SV5_V" "$SV5_REF"
P_REPO="$SV5_REPO" P_PAYLOAD='{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"sv5"}' \
  P_EVT="--event=stop" P_HOST="claude" run_hook
[ -f "$SV5_V" ] || fail "(sv5) the hook REMOVED the common verdict (rc $HKRC)"
cmp -s "$SV5_REF" "$SV5_V" || fail "(sv5) the hook REWROTE the common verdict: $(cat "$SV5_V")"
grep -q 'stub\.rule\.1' "$HKO" "$HKE" \
  || fail "(sv5) non-vacuity: the Stop run must reach the scan (stub finding named), got: $(cat "$HKO") / $(cat "$HKE")"
rm -rf "$SV5_REPO" "$SV5_REF"
ok "(sv5) --hook --event=stop => the stale common verdict is intact byte for byte"

# =============================================================================
# (ill*) — AN UNREAD PATH IS NEVER DROPPED IN SILENCE (T-01M4X9PP7FED0570PMPSYGA0V8)
# =============================================================================
# `[ -f ]` used to be the only filter between what git listed and what semgrep
# read: a path behind an unsearchable directory was dropped exactly like a
# deleted one, a 000 file in a readable directory turned semgrep's run into an
# rc 2 that LOST every other finding, a failed `git diff` emptied the dirty
# tree, an unreachable submodule read "not initialized" — and the gate said
# `clean on the diff.` (measured, plan R1-R5). Each arm below is RED on the base
# script. ONE FIXTURE PER LOSS SOURCE (plan-critic objection): an arm that pairs
# a mutant carries the loss it exercises and no other, and asserts the absence of
# the others, so a second source cannot keep it green.
#
# PARTOUT: every arm but (ill1) runs on a semgrep STUB (`ill_sinkscan`) that reads
# like semgrep where it matters here — `paths.scanned` lists the `.py` it was
# given, a `.py` holding `os.system` yields one finding, and an UNREADABLE file
# makes it exit 2 with no report (semgrep's measured answer, R5). (ill1) replays
# R1 on the REAL semgrep, SKIP said when it is absent. Arms needing `chmod 000`
# are SKIPPED, said, under uid 0 or where 000 still reads (Windows); the rights
# are restored before every `rm -rf`. No `find` (test_repo_walk_census.py:157).
ILL_SKIP=""
ILL_PROBE="$(mktemp -d)"; assert_tmpdir "$ILL_PROBE"
mkdir -p "$ILL_PROBE/d"; printf 'x\n' > "$ILL_PROBE/d/f"; printf 'x\n' > "$ILL_PROBE/k"
chmod 000 "$ILL_PROBE/d" "$ILL_PROBE/k"
if [ "$(id -u 2>/dev/null)" = "0" ]; then
  ILL_SKIP="uid 0 (root reads through chmod 000)"
elif [ -e "$ILL_PROBE/d/f" ] || [ -r "$ILL_PROBE/k" ]; then
  ILL_SKIP="chmod 000 still lets this host read"
fi
chmod 755 "$ILL_PROBE/d"; chmod 644 "$ILL_PROBE/k"; rm -rf "$ILL_PROBE"

ILL_G="git -c user.email=t@t.t -c user.name=t -c commit.gpgsign=false -c advice.detachedHead=false"
ILL_W="$(mktemp -d)"; assert_tmpdir "$ILL_W"          # outputs live HERE, never in a fixture
ILL_O="$ILL_W/out"; ILL_HO="$ILL_W/hk.out"; ILL_HE="$ILL_W/hk.err"
mkdir -p "$ILL_W/stub"
{ printf '#!%s\n' "$SUITE_BASH"; cat <<'ILLSG'
# ill_sinkscan: semgrep stand-in for the (ill*) arms
[ -n "${ILL_TRACE:-}" ] && echo call >> "$ILL_TRACE"
_dd=0; _res=""; _sc=""; _bad=0
for _a in "$@"; do
  if [ "$_dd" = 1 ]; then
    if [ ! -r "$_a" ]; then _bad=1; continue; fi
    case "$_a" in
      *.py) : ;;
      *) continue ;;
    esac
    [ -n "$_sc" ] && _sc="$_sc,"
    _sc="$_sc\"$_a\""
    if grep -q 'os.system' "$_a" 2>/dev/null; then
      [ -n "$_res" ] && _res="$_res,"
      _res="$_res{\"check_id\":\"ill.sink\",\"path\":\"$_a\",\"start\":{\"line\":1},\"extra\":{\"severity\":\"ERROR\",\"message\":\"m\"}}"
    fi
  fi
  [ "$_a" = "--" ] && _dd=1
done
[ "$_bad" = 1 ] && exit 2
printf '{"results":[%s],"errors":[],"paths":{"scanned":[%s]}}\n' "$_res" "$_sc"
exit 0
ILLSG
} > "$ILL_W/stub/semgrep"
chmod +x "$ILL_W/stub/semgrep"
ILL_SINK='import os\n\n\ndef run(cmd):\n    os.system("echo " + cmd)\n'

# ill_repo — a throwaway repo carrying `.agents/.gitignore` (state/local/), so the
# script's own audit/verdict writes never dirty the tree under test.
ill_repo() {
  ILL_R="$(mktemp -d)"; assert_tmpdir "$ILL_R"
  $ILL_G init -q "$ILL_R"
  mkdir -p "$ILL_R/.agents"; printf 'state/local/\n' > "$ILL_R/.agents/.gitignore"
}
# ill_commit — commit everything added, then an EMPTY commit: HEAD's own commit
# changes nothing, so the default perimeter is the dirty tree alone.
ill_commit() {
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1
  $ILL_G -C "$ILL_R" commit -qm base >/dev/null 2>&1
  $ILL_G -C "$ILL_R" commit -q --allow-empty -m vide >/dev/null 2>&1
}
ill_fin() {  # $1 repo ; "$@" dirs/files to give back their rights first
  local _r="$1"; shift
  for _x in "$@"; do chmod u+rwx "$_x" 2>/dev/null; done
  rm -rf "$_r"
}
ill_gate() {  # $1 dir to run from ; then the script's arguments
  local _d="$1"; shift
  ( cd "$_d" && PATH="$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" "$@" ) >"$ILL_O" 2>&1
  ILL_RC=$?
}
ill_hook() {  # $1 repo  $2 post|stop  $3 payload
  ( cd "$1" && printf '%s' "$3" \
      | env PATH="$ILL_W/stub:$PATH" AGENTS_HOOK_HOST=claude SEMGREP_CONFIG="$RULESET" \
            ILL_TRACE="${ILL_TRACE:-}" "$SUITE_BASH" "$SCRIPT" --hook "--event=$2" ) >"$ILL_HO" 2>"$ILL_HE"
  ILL_RC=$?
}
ill_benin() {  # $1 file — TRUE if ANY of the four benign sentences is in it
  grep -q -e 'clean on the diff' -e 'nothing to scan' -e "rien à lire, ce n'est pas un aveuglement" \
    -e 'couverture portable par attestation' "$1"
}
ill_audit() {  # $1 repo — the last audit line
  tail -1 "$1/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null
}
ill_verdict() {  # $1 repo — the common verdict path
  printf '%s' "$1/.agents/state/local/sca-reports/semgrep-verdict.json"
}
ill_stop() {  # $1 session id
  printf '{"hook_event_name":"Stop","stop_hook_active":false,"session_id":"%s"}' "$1"
}
# The single-source fixtures, each named by the ONE loss it carries:
#   ill_fx_inj  — tracked d/t.py (modified) behind `chmod 000 d`, `d/` IGNORED so
#                 `ls-files --others` never walks it: the unreachable path ALONE.
#   ill_fx_warn — untracked u/v.py behind `chmod 000 u`: the ls-files warning ALONE.
#   ill_fx_ill  — a.py + k.py (000) in a READABLE root: the unreadable file ALONE.
ill_fx_inj() {  # $1 content of the modified d/t.py
  ill_repo
  mkdir -p "$ILL_R/d"; printf 'd/\n' > "$ILL_R/.gitignore"; printf 'x = 1\n' > "$ILL_R/d/t.py"
  $ILL_G -C "$ILL_R" add -f d/t.py >/dev/null 2>&1
  ill_commit
  printf "$1" > "$ILL_R/d/t.py"
  chmod 000 "$ILL_R/d"
}
ill_fx_warn() {
  ill_repo; printf 'y = 1\n' > "$ILL_R/b.py"; ill_commit
  printf 'y = 2\n' > "$ILL_R/b.py"
  mkdir -p "$ILL_R/u"; printf "$ILL_SINK" > "$ILL_R/u/v.py"; chmod 000 "$ILL_R/u"
}
ill_fx_ill() {  # $1 content of a.py  $2 content of k.py
  ill_repo; ill_commit
  printf "$1" > "$ILL_R/a.py"; printf "$2" > "$ILL_R/k.py"; chmod 000 "$ILL_R/k.py"
}
ill_fx_r1() {  # plan R1: d/t.py tracked modified + d/vuln.py untracked sink + b.py, `chmod 000 d`
  ill_repo
  mkdir -p "$ILL_R/d"; printf 'x = 1\n' > "$ILL_R/d/t.py"; printf 'y = 1\n' > "$ILL_R/b.py"
  ill_commit
  printf 'x = 2\n' > "$ILL_R/d/t.py"; printf 'y = 2\n' > "$ILL_R/b.py"
  printf "$ILL_SINK" > "$ILL_R/d/vuln.py"
  chmod 000 "$ILL_R/d"
}
ill_super_fin() {  # $1 super (from mk_super_sg) — removes it AND its two source repos
  local _s="$1" _sub _nest
  _sub="$(git -C "$_s" config -f .gitmodules --get submodule.sub.url 2>/dev/null)"
  _nest=""
  [ -n "$_sub" ] && _nest="$(git -C "$_sub" config -f .gitmodules --get submodule.nested.url 2>/dev/null)"
  chmod u+rwx "$_s/sub" "$_s/sub/d" "$_s/.git/modules/sub" 2>/dev/null
  rm -rf "$_s"
  case "$_sub" in
    /tmp/*|/var/folders/*|/private/var/folders/*) rm -rf "$_sub" ;;
  esac
  case "$_nest" in
    /tmp/*|/var/folders/*|/private/var/folders/*) rm -rf "$_nest" ;;
  esac
}

# ---- (ill) ARMS ----
arm_ill1() {  # gate, REAL semgrep, plan R1
  if [ "$HAVE_SEMGREP" -ne 1 ]; then echo "  SKIP (ill1): semgrep not installed"; return 0; fi
  ill_fx_r1
  ( cd "$ILL_R" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1; ILL_RC=$?
  [ "$ILL_RC" -eq 0 ] || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) R1 must exit 0 (degrade, never block), got $ILL_RC — $(cat "$ILL_O")"; }
  ill_benin "$ILL_O" && { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) R1 printed a benign sentence over an unread sink: $(cat "$ILL_O")"; }
  grep -q '1 listed path(s) unreachable' "$ILL_O" || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) the unreachable d/t.py must be COUNTED: $(cat "$ILL_O")"; }
  grep -q 'warning line(s) from git ls-files' "$ILL_O" || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) the ls-files warning must be COUNTED: $(cat "$ILL_O")"; }
  [ -e "$(ill_verdict "$ILL_R")" ] && { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) a perimeter that lost paths must leave NO common verdict"; }
  ill_audit "$ILL_R" | grep -q '"couverture":"DEGRADED"' || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1) audit couverture must be DEGRADED: $(ill_audit "$ILL_R")"; }
  chmod 755 "$ILL_R/d"
  ( cd "$ILL_R" && SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1; ILL_RC=$?
  ill_fin "$ILL_R"
  [ "$ILL_RC" -eq 1 ] || fail "(ill1) witness: d readable => the sink is found (rc 1), got $ILL_RC — $(cat "$ILL_O")"
  grep -q 'finding(s) on the diff' "$ILL_O" || fail "(ill1) witness: the finding line is missing: $(cat "$ILL_O")"
  ok "(ill1) R1 on the real semgrep: rc 0, both losses counted, no benign sentence, no verdict, audit DEGRADED; readable => rc 1"
}

arm_ill1i() {  # the unreachable path ALONE (pairs M1, M5)
  ill_fx_inj 'x = 2\n'
  ill_gate "$ILL_R"
  ill_fin "$ILL_R" "$ILL_R/d"
  [ "$ILL_RC" -eq 0 ] || fail "(ill1i) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"
  grep -q '1 listed path(s) unreachable' "$ILL_O" || fail "(ill1i) the unreachable path must be counted: $(cat "$ILL_O")"
  grep -q -e 'warning line(s)' -e 'unreadable' -e 'census' "$ILL_O" && fail "(ill1i) single-source fixture carries another loss: $(cat "$ILL_O")"
  ill_benin "$ILL_O" && fail "(ill1i) benign sentence over a lost path: $(cat "$ILL_O")"
  ok "(ill1i) an ignored-dir tracked path behind chmod 000 => '1 listed path(s) unreachable', the only loss, no benign sentence"
}

arm_ill1w() {  # the ls-files warning ALONE
  ill_fx_warn
  ill_gate "$ILL_R"
  ill_fin "$ILL_R" "$ILL_R/u"
  [ "$ILL_RC" -eq 0 ] || fail "(ill1w) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"
  grep -q 'warning line(s) from git ls-files --others' "$ILL_O" || fail "(ill1w) the ls-files warning must be counted: $(cat "$ILL_O")"
  grep -q -e 'unreachable' -e 'unreadable' -e 'census' "$ILL_O" && fail "(ill1w) single-source fixture carries another loss: $(cat "$ILL_O")"
  ill_benin "$ILL_O" && fail "(ill1w) benign sentence over an unlisted untracked file: $(cat "$ILL_O")"
  ok "(ill1w) untracked dir behind chmod 000 => 'warning line(s) from git ls-files --others', the only loss"
}

arm_ill1a() {  # --attest equal to the RETAINED files of a degraded perimeter
  ill_fx_r1
  printf 'b.py\n' > "$ILL_W/att"
  ill_gate "$ILL_R" --attest "$ILL_W/att"
  [ "$ILL_RC" -eq 0 ] || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1a) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"; }
  grep -q 'couverture portable par attestation' "$ILL_O" && { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1a) an attestation of the retained files concluded over a lost path: $(cat "$ILL_O")"; }
  ill_audit "$ILL_R" | grep -q '"couverture":"DEGRADED"' || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill1a) audit couverture must be DEGRADED: $(ill_audit "$ILL_R")"; }
  chmod 755 "$ILL_R/d"
  ill_gate "$ILL_R" --attest "$ILL_W/att"
  ill_fin "$ILL_R"
  grep -q 'attestation ≢ retenues' "$ILL_O" || fail "(ill1a) witness: d readable => the same attestation is PARTIAL and refused: $(cat "$ILL_O")"
  ok "(ill1a) --attest equal to the retained files of a degraded perimeter => no 'couverture portable par attestation'; readable => partial, refused"
}

arm_ill1s() {  # R1 launched from a SUBDIRECTORY (pairs M14)
  ill_fx_r1
  mkdir -p "$ILL_R/sub"
  ill_gate "$ILL_R/sub"
  ill_fin "$ILL_R" "$ILL_R/d"
  [ "$ILL_RC" -eq 0 ] || fail "(ill1s) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"
  grep -q '1 listed path(s) unreachable' "$ILL_O" || fail "(ill1s) from a subdirectory the unreachable path must still be counted (tested from ROOT, never the cwd): $(cat "$ILL_O")"
  ill_benin "$ILL_O" && fail "(ill1s) benign sentence: $(cat "$ILL_O")"
  ok "(ill1s) R1 run from R/sub => same loss lines, no benign sentence"
}

arm_ill2() {  # --at HEAD over a commit whose file sits behind chmod 000
  ill_repo; ill_commit
  mkdir -p "$ILL_R/d"; printf 'x = 1\n' > "$ILL_R/d/x.py"
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm add >/dev/null 2>&1
  chmod 000 "$ILL_R/d"
  ill_gate "$ILL_R" --at HEAD
  chmod 755 "$ILL_R/d"
  [ "$ILL_RC" -eq 0 ] || { ill_fin "$ILL_R"; fail "(ill2) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"; }
  grep -q 'unreachable' "$ILL_O" || { ill_fin "$ILL_R"; fail "(ill2) --at: the unreachable committed file must be counted: $(cat "$ILL_O")"; }
  ill_benin "$ILL_O" && { ill_fin "$ILL_R"; fail "(ill2) --at: benign sentence over a lost file: $(cat "$ILL_O")"; }
  ill_audit "$ILL_R" | grep -q '"couverture":"DEGRADED"' || { ill_fin "$ILL_R"; fail "(ill2) audit couverture must be DEGRADED: $(ill_audit "$ILL_R")"; }
  $ILL_G -C "$ILL_R" rm -q d/x.py >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm del >/dev/null 2>&1
  ill_gate "$ILL_R" --at HEAD
  ill_fin "$ILL_R"
  grep -q -e 'unreachable' -e 'perimeter INCOMPLETE' "$ILL_O" && fail "(ill2) witness: a commit that DELETES x.py is not a loss: $(cat "$ILL_O")"
  ok "(ill2) --at HEAD: committed file behind chmod 000 => unreachable + DEGRADED, no benign sentence; a deleting commit => no loss"
}

arm_ill3() {  # a genuine deletion is NOT unreachable, and injoignable terminates
  ill_repo; mkdir -p "$ILL_R/e/f"; printf 'x = 1\n' > "$ILL_R/e/f/t.py"; ill_commit
  rm -rf "$ILL_R/e"
  if command -v timeout >/dev/null 2>&1; then
    ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" timeout 60 "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
    ILL_RC=$?
  else
    ill_gate "$ILL_R"
  fi
  ill_fin "$ILL_R"
  [ "$ILL_RC" -ne 124 ] || fail "(ill3) the gate did not terminate on a deleted tree (injoignable loop)"
  [ "$ILL_RC" -eq 0 ] || fail "(ill3) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"
  grep -q -e 'perimeter INCOMPLETE' -e 'unreachable' "$ILL_O" && fail "(ill3) a deleted e/ is a real deletion, never a loss: $(cat "$ILL_O")"
  ok "(ill3) tracked e/f/t.py with e/ deleted => no loss line, terminates (under timeout)"
}

arm_ill4() {  # hook Stop, the unreachable path ALONE (pairs M2)
  ill_fx_inj 'x = 2\n'
  ill_hook "$ILL_R" stop "$(ill_stop ill4a)"
  [ "$ILL_RC" -eq 0 ] || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4) a loss must never block the hook (rc 0), got $ILL_RC — $(cat "$ILL_HE")"; }
  grep -q '^{"systemMessage": "COVERAGE DEGRADED' "$ILL_HO" || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4) Stop must say COVERAGE DEGRADED (systemMessage), got: $(cat "$ILL_HO") / $(cat "$ILL_HE")"; }
  ill_audit "$ILL_R" | grep -q '"verdict":"DEGRADED"' || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4) the hook audit line must be DEGRADED: $(ill_audit "$ILL_R")"; }
  chmod 755 "$ILL_R/d"; printf "$ILL_SINK" > "$ILL_R/d/t.py"
  ill_hook "$ILL_R" stop "$(ill_stop ill4b)"
  ill_fin "$ILL_R"
  [ "$ILL_RC" -eq 2 ] || fail "(ill4) witness: the readable sink blocks the Stop (rc 2), got $ILL_RC — $(cat "$ILL_HE")"
  ok "(ill4) hook Stop, path behind chmod 000 => rc 0 + systemMessage COVERAGE DEGRADED + audit DEGRADED; readable sink => rc 2"
}

arm_ill4x() {  # (ill4) replayed on `.cfg/t`: the extension is read on the BASENAME (closing review T2)
  # On the whole path `.cfg/t` read as the extension `cfg/t`, uncovered: the
  # loss went mute at the Stop AND at the Post. `t` has no extension, so it is
  # never scanned, but its loss counts.
  ill_repo
  mkdir -p "$ILL_R/.cfg"; printf '.cfg/\n' > "$ILL_R/.gitignore"; printf 'x = 1\n' > "$ILL_R/.cfg/t"
  $ILL_G -C "$ILL_R" add -f .cfg/t >/dev/null 2>&1
  ill_commit
  printf 'x = 2\n' > "$ILL_R/.cfg/t"; chmod 000 "$ILL_R/.cfg"
  ill_hook "$ILL_R" stop "$(ill_stop ill4x)"
  _rs=$ILL_RC; _hs="$(cat "$ILL_HO")"; _es="$(cat "$ILL_HE")"
  ill_hook "$ILL_R" post '{"tool_name":"Edit","tool_input":{"file_path":".cfg/t"},"session_id":"ill4x"}'
  _rp=$ILL_RC; _hp="$(cat "$ILL_HO")"
  chmod 755 "$ILL_R/.cfg"
  ill_hook "$ILL_R" stop "$(ill_stop ill4x-l)"
  ill_fin "$ILL_R"
  [ "$_rs" -eq 0 ] || fail "(ill4x) Stop: rc 0 expected, got $_rs — $_es"
  printf '%s' "$_hs" | grep -q '^{"systemMessage": "COVERAGE DEGRADED' || fail "(ill4x) Stop: '.cfg/t' behind chmod 000 must say COVERAGE DEGRADED, got: $_hs / $_es"
  printf '%s' "$_es" | grep -q '1 listed path(s) unreachable' || fail "(ill4x) Stop: the unreachable '.cfg/t' must be counted: $_es"
  [ "$_rp" -eq 0 ] || fail "(ill4x) Post: rc 0 expected, got $_rp"
  printf '%s' "$_hp" | grep -q '"systemMessage": "COVERAGE DEGRADED' || fail "(ill4x) Post: '.cfg/t' behind chmod 000 must not be muted, got: $_hp"
  [ "$ILL_RC" -eq 0 ] && [ ! -s "$ILL_HO" ] || fail "(ill4x) witness: readable '.cfg/t' (no extension, never scanned) => mute rc 0, got $ILL_RC: $(cat "$ILL_HO")"
  ok "(ill4x) '.cfg/t' behind chmod 000 => Stop and Post DEGRADED (extension read on the basename); readable => mute"
}

arm_ill4p() {  # hook Post on a path behind chmod 000, twice (pairs M16: no marker without h16)
  ill_fx_inj 'x = 2\n'
  _pl='{"tool_name":"Edit","tool_input":{"file_path":"d/t.py"},"session_id":"ill4p"}'
  for _i in 1 2; do
    ill_hook "$ILL_R" post "$_pl"
    [ "$ILL_RC" -eq 0 ] || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4p) call $_i: rc 0 expected, got $ILL_RC — $(cat "$ILL_HE")"; }
    "$PY" -c 'import json,sys
o = json.loads(open(sys.argv[1]).read().strip().splitlines()[0])
assert o["systemMessage"].startswith("COVERAGE DEGRADED"), o
assert o["hookSpecificOutput"]["additionalContext"] == o["systemMessage"], o' "$ILL_HO" 2>/dev/null \
      || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4p) call $_i: post must emit the two-key DEGRADED object, never mute: $(cat "$ILL_HO")"; }
  done
  _n="$(find "$ILL_R/.agents/state/local/semgrep-hook" -mindepth 1 -maxdepth 1 -name 'perte-*' 2>/dev/null | wc -l | tr -d ' ')"
  ill_fin "$ILL_R" "$ILL_R/d"
  [ "$_n" -eq 0 ] || fail "(ill4p) post has no h16: no perte- marker may be written, found $_n"
  ok "(ill4p) hook Post on a path behind chmod 000 => the two-key DEGRADED object at BOTH calls, no perte- marker"
}

arm_ill4m() {  # the Stop systemMessage once per session and per message (pairs M12)
  ill_fx_inj 'x = 2\n'
  ill_hook "$ILL_R" stop "$(ill_stop ill4m)"
  grep -q 'systemMessage' "$ILL_HO" || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4m) 1st Stop must carry the systemMessage: $(cat "$ILL_HO")"; }
  ill_hook "$ILL_R" stop "$(ill_stop ill4m)"
  [ -s "$ILL_HO" ] && { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4m) 2nd Stop of the same session must not repeat the systemMessage: $(cat "$ILL_HO")"; }
  grep -q 'perimeter INCOMPLETE' "$ILL_HE" || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4m) 2nd Stop must still say the loss on stderr: $(cat "$ILL_HE")"; }
  ill_audit "$ILL_R" | grep -q '"verdict":"DEGRADED"' || { ill_fin "$ILL_R" "$ILL_R/d"; fail "(ill4m) 2nd Stop audit must be DEGRADED: $(ill_audit "$ILL_R")"; }
  ill_hook "$ILL_R" stop "$(ill_stop ill4m-autre)"
  ill_fin "$ILL_R" "$ILL_R/d"
  grep -q 'systemMessage' "$ILL_HO" || fail "(ill4m) witness: another session gets the systemMessage: $(cat "$ILL_HO")"
  ok "(ill4m) Stop x2 same session => systemMessage once, stderr + audit DEGRADED both times; another session => systemMessage"
}

arm_ill5() {  # the Stop cache is never read over a loss (pairs M3)
  ill_repo; printf 'y = 1\n' > "$ILL_R/b.py"; ill_commit; printf 'y = 2\n' > "$ILL_R/b.py"
  : > "$ILL_W/trace"
  ILL_TRACE="$ILL_W/trace" ill_hook "$ILL_R" stop "$(ill_stop ill5a)"
  [ -f "$ILL_R/.agents/state/local/semgrep-hook/stop-propre" ] \
    || { ill_fin "$ILL_R"; fail "(ill5) precondition: the clean Stop must fill stop-propre (rc $ILL_RC): $(cat "$ILL_HE")"; }
  mkdir -p "$ILL_R/u"; printf "$ILL_SINK" > "$ILL_R/u/v.py"; chmod 000 "$ILL_R/u"
  ILL_TRACE="$ILL_W/trace" ill_hook "$ILL_R" stop "$(ill_stop ill5b)"
  _a="$(ill_audit "$ILL_R")"; _sp=0; [ -f "$ILL_R/.agents/state/local/semgrep-hook/stop-propre" ] && _sp=1
  ill_fin "$ILL_R" "$ILL_R/u"
  printf '%s' "$_a" | grep -q 'hook-cache' && fail "(ill5) a Stop that LOST paths read the clean cache: $_a"
  printf '%s' "$_a" | grep -q '"verdict":"DEGRADED"' || fail "(ill5) 2nd Stop must be DEGRADED: $_a"
  [ "$_sp" -eq 0 ] || fail "(ill5) the degraded Stop must ERASE stop-propre"
  grep -q 'systemMessage' "$ILL_HO" || fail "(ill5) 2nd Stop must say it: $(cat "$ILL_HO")"
  ok "(ill5) CLEAN Stop fills stop-propre; an unlisted untracked dir next => DEGRADED, cache not read, stop-propre erased"
}

arm_ill6() {  # submodule behind chmod 000 is unreachable, never "not initialized" (R3)
  _s="$(mk_super_sg)"
  chmod 000 "$_s/sub"
  ill_gate "$_s"
  chmod 755 "$_s/sub"
  [ "$ILL_RC" -eq 0 ] || { ill_super_fin "$_s"; fail "(ill6) rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"; }
  grep -q "unreachable submodule 'sub'" "$ILL_O" || { ill_super_fin "$_s"; fail "(ill6) the unreachable submodule must be NAMED unreachable: $(cat "$ILL_O")"; }
  grep -q 'not initialized' "$ILL_O" && { ill_super_fin "$_s"; fail "(ill6) an unreachable submodule read 'not initialized': $(cat "$ILL_O")"; }
  grep -q 'unreachable submodule(s)' "$ILL_O" || { ill_super_fin "$_s"; fail "(ill6) the submodule loss must be COUNTED (relever_signaux): $(cat "$ILL_O")"; }
  ill_benin "$ILL_O" && { ill_super_fin "$_s"; fail "(ill6) benign sentence over an unreachable submodule: $(cat "$ILL_O")"; }
  [ -e "$(ill_verdict "$_s")" ] && { ill_super_fin "$_s"; fail "(ill6) no common verdict on a lost submodule"; }
  ill_super_fin "$_s"
  _s="$(mk_super_sg)"
  ( cd "$_s" && $GIT_ISO submodule deinit -f sub ) >/dev/null 2>&1
  ill_gate "$_s"
  ill_super_fin "$_s"
  grep -q "submodule 'sub' not initialized" "$ILL_O" || fail "(ill6) witness: a deinit'd submodule stays 'not initialized': $(cat "$ILL_O")"
  grep -q 'COVERAGE DEGRADED' "$ILL_O" && fail "(ill6) witness: a deinit'd submodule is not a loss: $(cat "$ILL_O")"
  ok "(ill6) submodule dir behind chmod 000 => 'unreachable submodule', counted, no benign sentence, no verdict; deinit'd => 'not initialized', no DEGRADED"
}

arm_ill6b() {  # the submodule site: a tracked file of a readable submodule behind chmod 000 (pairs M9)
  _s="$(mk_super_sg)"
  mkdir -p "$_s/sub/d"; printf 'd/\n' > "$_s/sub/.gitignore"; printf 'x = 1\n' > "$_s/sub/d/x.py"
  $ILL_G -C "$_s/sub" add .gitignore >/dev/null 2>&1; $ILL_G -C "$_s/sub" add -f d/x.py >/dev/null 2>&1
  $ILL_G -C "$_s/sub" commit -qm d >/dev/null 2>&1
  $ILL_G -C "$_s" add sub >/dev/null 2>&1; $ILL_G -C "$_s" commit -qm bump >/dev/null 2>&1
  $ILL_G -C "$_s" commit -q --allow-empty -m vide >/dev/null 2>&1
  chmod 000 "$_s/sub/d"
  ill_gate "$_s"
  chmod 755 "$_s/sub/d"
  _o="$(cat "$ILL_O")"
  ill_gate "$_s"
  ill_super_fin "$_s"
  printf '%s' "$_o" | grep -q '1 listed path(s) unreachable' || fail "(ill6b) the submodule's unreachable d/x.py must be counted: $_o"
  printf '%s' "$_o" | grep -q -e 'census' -e 'warning line(s)' -e 'unreadable' && fail "(ill6b) single-source fixture carries another loss: $_o"
  printf '%s' "$_o" | grep -q 'SAST couverture: DEGRADED' || fail "(ill6b) the findings of the rest must carry the DEGRADED coverage line: $_o"
  [ "$ILL_RC" -eq 1 ] || fail "(ill6b) witness: readable => rc 1, got $ILL_RC — $(cat "$ILL_O")"
  grep -q 'unreachable' "$ILL_O" && fail "(ill6b) witness: readable => no unreachable line: $(cat "$ILL_O")"
  ok "(ill6b) a readable submodule's tracked d/x.py behind chmod 000 => counted at the submodule site, DEGRADED; readable => rc 1, no loss"
}

arm_ill6w() {  # the submodule's OWN `ls-files --others` warning ALONE (pairs the submodule relever_lserr)
  # The superproject's census never walks into a gitlink, so this warning can
  # only come from the per-submodule census — the one the exec-critic found
  # without a witness (removing its relever_lserr left the suite green).
  _s="$(mk_super_sg)"
  mkdir -p "$_s/sub/u"; printf "$ILL_SINK" > "$_s/sub/u/v.py"; chmod 000 "$_s/sub/u"
  ill_gate "$_s"
  chmod 755 "$_s/sub/u"
  _o="$(cat "$ILL_O")"
  ill_gate "$_s"
  _a2="$(ill_audit "$_s")"
  ill_super_fin "$_s"
  printf '%s' "$_o" | grep -q 'warning line(s) from git ls-files --others' || fail "(ill6w) the submodule's untracked dir behind chmod 000 must be counted: $_o"
  printf '%s' "$_o" | grep -q -e 'census' -e 'unreachable' -e 'unreadable' && fail "(ill6w) single-source fixture carries another loss: $_o"
  printf '%s' "$_o" | grep -q 'SAST couverture: DEGRADED' || fail "(ill6w) the findings of the rest must carry the DEGRADED coverage line: $_o"
  grep -q 'perimeter INCOMPLETE' "$ILL_O" && fail "(ill6w) witness: readable sub/u => no loss line: $(cat "$ILL_O")"
  printf '%s' "$_a2" | grep -q 'u/v\.py' || fail "(ill6w) witness: readable sub/u => its sink is found (audit locations): $_a2"
  ok "(ill6w) untracked dir behind chmod 000 inside a submodule => its ls-files warning counted, the only loss; readable => found, no loss"
}

arm_ill6d() {  # the depth bound is a COUNTED loss (pairs M18)
  _s="$(mk_super_sg)"
  ( cd "$_s" && PATH="$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" SUBMODULE_SCAN_DEPTH=0 "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  _o="$(cat "$ILL_O")"
  ill_gate "$_s"
  ill_super_fin "$_s"
  printf '%s' "$_o" | grep -q 'submodule(s) beyond the depth bound' || fail "(ill6d) SUBMODULE_SCAN_DEPTH=0 => the bound must be COUNTED: $_o"
  printf '%s' "$_o" | grep -q 'SAST couverture: DEGRADED' || fail "(ill6d) the bound must reach the coverage axis: $_o"
  grep -q 'depth bound' "$ILL_O" && fail "(ill6d) witness: the default depth (8) prints no bound line: $(cat "$ILL_O")"
  ok "(ill6d) SUBMODULE_SCAN_DEPTH=0 => 'submodule(s) beyond the depth bound', DEGRADED; default => no bound line"
}

arm_ill7() {  # R4: unreadable submodule gitdir, gate (pairs M4)
  _s="$(mk_super_sg)"
  chmod 000 "$_s/.git/modules/sub"
  ill_gate "$_s"
  chmod 755 "$_s/.git/modules/sub"
  _a="$(ill_audit "$_s")"; _v=0; [ -e "$(ill_verdict "$_s")" ] && _v=1
  _o="$(cat "$ILL_O")"
  ill_gate "$_s"
  _a2="$(ill_audit "$_s")"
  ill_super_fin "$_s"
  printf '%s' "$_a" | grep -q '"couverture":"refus de conclure"' || fail "(ill7) R4 audit couverture must be 'refus de conclure': $_a — $_o"
  # T-01M4Z24V0J813T40XRW3S4VW67: the root diff carries `--ignore-submodules=dirty`
  # and no longer opens the submodule's unreadable git dir (it was that open which
  # failed the dirty-tree census before); the loss is now SAID by the submodule's
  # own enumeration — still a refusal to conclude.
  printf '%s' "$_o" | grep -q -e 'submodule(s) whose enumeration failed' -e 'submodule(s) whose tracked files could not be listed' \
    || fail "(ill7) R4 must say the failed submodule enumeration: $_o"
  printf '%s' "$_o" | grep -q -e 'clean on the diff' -e 'nothing to scan' -e "rien à lire, ce n'est pas un aveuglement" && fail "(ill7) R4 benign sentence: $_o"
  [ "$_v" -eq 0 ] || fail "(ill7) R4 must leave no common verdict"
  printf '%s' "$_a2" | grep -q '"couverture":"CLEAN"' || fail "(ill7) witness: readable gitdir => couverture CLEAN: $_a2 — $(cat "$ILL_O")"
  ok "(ill7) R4 gitdir 000 => audit 'refus de conclure', the failed submodule enumeration said, no benign sentence, no verdict; readable => CLEAN"
}

arm_ill7c() {  # C20: the census failure ALONE, by a git stub (pairs M17)
  ill_repo; printf 'y = 1\n' > "$ILL_R/b.py"
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm b >/dev/null 2>&1
  printf 'z = 1\n' > "$ILL_R/c.py"
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm c >/dev/null 2>&1
  printf "$ILL_SINK" > "$ILL_R/b.py"
  _real="$(command -v git)"
  mkdir -p "$ILL_W/gstub"
  # Re-anchored (T-01M4Z24V0J813T40XRW3S4VW67) on the argv the script EMITS
  # now, traced by GIT_TRACE: the census diff ends `--ignore-submodules=dirty
  # HEAD --`; the commit census (`diff --raw … HEAD~1 HEAD --`) and the pointe
  # diff (`… HEAD -- <paths>`, by xargs) end otherwise and pass through.
  {
    printf '#!/bin/sh\n'
    printf 'case "$*" in\n'
    printf '  *"--ignore-submodules=dirty HEAD --") exit 128 ;;\n'
    printf 'esac\n'
    printf 'exec "%s" "$@"\n' "$_real"
  } > "$ILL_W/gstub/git"
  chmod +x "$ILL_W/gstub/git"
  # Self-test of the stub, on the EXACT argv of the script ("${GN[@]}" included):
  # it fails the dirty-tree census ONLY, never the commit read nor the pointe diff.
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null diff --raw -z --no-renames --no-abbrev HEAD~1 HEAD -- >/dev/null 2>&1 \
    || { ill_fin "$ILL_R"; fail "(ill7c) stub self-test: 'diff --raw HEAD~1 HEAD --' must pass through (rc 0)"; }
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null -c diff.autoRefreshIndex=false --literal-pathspecs diff --raw -z --no-renames --no-abbrev --no-ext-diff --no-textconv --ignore-submodules=dirty HEAD -- c.py >/dev/null 2>&1 \
    || { ill_fin "$ILL_R"; fail "(ill7c) stub self-test: the pointe diff over c.py must pass through (rc 0)"; }
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null -c diff.autoRefreshIndex=false diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty HEAD -- >/dev/null 2>&1
  [ "$?" -eq 128 ] || { ill_fin "$ILL_R"; fail "(ill7c) stub self-test: the census diff '… --ignore-submodules=dirty HEAD --' must return 128"; }
  ( cd "$ILL_R" && PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  _rc=$?; _o="$(cat "$ILL_O")"; _a="$(ill_audit "$ILL_R")"; _v=0; [ -e "$(ill_verdict "$ILL_R")" ] && _v=1
  ill_gate "$ILL_R"
  ill_fin "$ILL_R"
  rm -rf "$ILL_W/gstub"
  printf '%s' "$_o" | grep -q 'dirty-tree census FAILED' || fail "(ill7c) the failed census must be said (rc $_rc): $_o"
  printf '%s' "$_a" | grep -q '"couverture":"refus de conclure"' || fail "(ill7c) audit couverture must be 'refus de conclure': $_a"
  [ "$_v" -eq 0 ] || fail "(ill7c) a failed census must leave no common verdict (census counted in PERTE_N)"
  printf '%s' "$_o" | grep -q -e 'clean on the diff' -e 'nothing to scan' -e "rien à lire, ce n'est pas un aveuglement" && fail "(ill7c) benign sentence over the lost b.py: $_o"
  printf '%s' "$_o" | grep -q -e 'unreachable' -e 'unreadable' -e 'warning line(s)' -e 'submodule' && fail "(ill7c) single-source fixture carries another loss: $_o"
  [ "$ILL_RC" -eq 1 ] || fail "(ill7c) witness without the git stub: b.py's sink is found (rc 1), got $ILL_RC — $(cat "$ILL_O")"
  ok "(ill7c) git diff -z HEAD rc 128 alone => census FAILED, refus de conclure, no verdict, no benign sentence; without stub => rc 1"
}

arm_ill7s() {  # a failed submodule enumeration ALONE, by a git stub (pairs the submod-fail signal)
  _s="$(mk_super_sg)"
  _real="$(command -v git)"
  mkdir -p "$ILL_W/gstub"
  {
    printf '#!/bin/sh\n'
    printf 'case "$*" in\n'
    printf '  *"/sub "*" ls-files -z --stage") exit 128 ;;\n'
    printf 'esac\n'
    printf 'exec "%s" "$@"\n' "$_real"
  } > "$ILL_W/gstub/git"
  chmod +x "$ILL_W/gstub/git"
  # Self-tests on the EXACT argv the script emits ("${GN[@]}" after `-C`).
  "$ILL_W/gstub/git" -C "$_s" -c core.fsmonitor=false -c core.hooksPath=/dev/null ls-files -z --stage >/dev/null 2>&1 \
    || { ill_super_fin "$_s"; fail "(ill7s) stub self-test: the superproject's own enumeration must pass through"; }
  "$ILL_W/gstub/git" -C "$_s/sub" -c core.fsmonitor=false -c core.hooksPath=/dev/null ls-files -z --stage >/dev/null 2>&1
  [ "$?" -eq 128 ] || { ill_super_fin "$_s"; fail "(ill7s) stub self-test: the submodule's enumeration must return 128"; }
  ( cd "$_s" && PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  _o="$(cat "$ILL_O")"; _a="$(ill_audit "$_s")"; _v=0; [ -e "$(ill_verdict "$_s")" ] && _v=1
  ill_gate "$_s"
  ill_super_fin "$_s"
  rm -rf "$ILL_W/gstub"
  printf '%s' "$_o" | grep -q 'submodule(s) whose enumeration failed' || fail "(ill7s) the failed submodule enumeration must be COUNTED in the main shell: $_o"
  printf '%s' "$_a" | grep -q '"couverture":"refus de conclure"' || fail "(ill7s) audit couverture must be 'refus de conclure': $_a"
  [ "$_v" -eq 0 ] || fail "(ill7s) a failed submodule enumeration must leave no common verdict"
  printf '%s' "$_o" | grep -q -e 'census' -e 'unreachable' -e 'unreadable' -e 'warning line(s)' && fail "(ill7s) single-source fixture carries another loss: $_o"
  grep -q 'enumeration failed' "$ILL_O" && fail "(ill7s) witness: without the stub no enumeration fails: $(cat "$ILL_O")"
  ok "(ill7s) sub's 'ls-files --stage' rc 128 alone => counted, refus de conclure, no verdict; without stub => no failure"
}

arm_ill7l() {  # the submodule's TRACKED-file listing failing ALONE, by a git stub (pairs the submod-ls signal)
  # Security review finding: `git -C <sub> ls-files -z` had its rc and stderr
  # thrown away, so a failed listing dropped the submodule's tracked files in
  # silence. The stub fails exactly that call: `--stage` (enumeration) and
  # `--others` (untracked census) end differently and pass through.
  _s="$(mk_super_sg)"
  _real="$(command -v git)"
  mkdir -p "$ILL_W/gstub"
  {
    printf '#!/bin/sh\n'
    printf 'case "$*" in\n'
    printf '  *"/sub "*" ls-files -z") exit 128 ;;\n'
    printf 'esac\n'
    printf 'exec "%s" "$@"\n' "$_real"
  } > "$ILL_W/gstub/git"
  chmod +x "$ILL_W/gstub/git"
  # Self-tests on the EXACT argv the script emits ("${GN[@]}" after `-C`, the
  # sparse-index advice off on `--others`): `--stage` and `--others` pass through.
  "$ILL_W/gstub/git" -C "$_s/sub" -c core.fsmonitor=false -c core.hooksPath=/dev/null ls-files -z --stage >/dev/null 2>&1 \
    || { ill_super_fin "$_s"; fail "(ill7l) stub self-test: the submodule's enumeration (--stage) must pass through"; }
  "$ILL_W/gstub/git" -C "$_s/sub" -c core.fsmonitor=false -c core.hooksPath=/dev/null -c advice.sparseIndexExpanded=false ls-files --others --exclude-standard -z >/dev/null 2>&1 \
    || { ill_super_fin "$_s"; fail "(ill7l) stub self-test: the submodule's untracked census must pass through"; }
  "$ILL_W/gstub/git" -C "$_s/sub" -c core.fsmonitor=false -c core.hooksPath=/dev/null ls-files -z >/dev/null 2>&1
  [ "$?" -eq 128 ] || { ill_super_fin "$_s"; fail "(ill7l) stub self-test: the submodule's 'ls-files -z' must return 128"; }
  ( cd "$_s" && PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  _o="$(cat "$ILL_O")"; _a="$(ill_audit "$_s")"; _v=0; [ -e "$(ill_verdict "$_s")" ] && _v=1
  ill_gate "$_s"
  ill_super_fin "$_s"
  rm -rf "$ILL_W/gstub"
  printf '%s' "$_o" | grep -q 'submodule(s) whose tracked files could not be listed' || fail "(ill7l) the failed tracked-file listing must be COUNTED: $_o"
  printf '%s' "$_a" | grep -q '"couverture":"refus de conclure"' || fail "(ill7l) audit couverture must be 'refus de conclure': $_a"
  [ "$_v" -eq 0 ] || fail "(ill7l) a failed tracked-file listing must leave no common verdict"
  printf '%s' "$_o" | grep -q -e 'census' -e 'unreachable' -e 'unreadable' -e 'warning line(s)' -e 'enumeration failed' && fail "(ill7l) single-source fixture carries another loss: $_o"
  grep -q 'could not be listed' "$ILL_O" && fail "(ill7l) witness: without the stub every listing succeeds: $(cat "$ILL_O")"
  ok "(ill7l) sub's 'ls-files -z' rc 128 alone => counted, refus de conclure, no verdict; without stub => no loss"
}

arm_ill7k() {  # the COMMIT census failing ALONE, by a git stub (closing review T3, pairs commit-census)
  # files_changed_by reads a commit by `git diff X~1 X`, then `git show X`; both
  # in error (a partial clone without its trees offline) lost the committed sink
  # in silence: `nothing to scan` + audit CLEAN, default mode AND `--at HEAD`.
  ill_repo; printf 'x = 1\n' > "$ILL_R/a.py"
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm a >/dev/null 2>&1
  printf "$ILL_SINK" > "$ILL_R/c.py"
  $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm c >/dev/null 2>&1
  _real="$(command -v git)"
  mkdir -p "$ILL_W/gstub"
  # Re-anchored on the argv the script EMITS now (`--raw`, `--root`, traced by
  # GIT_TRACE, T-01M4XY8NC97JBSQP6C28AFD7QP); the self-tests replay it exactly.
  {
    printf '#!/bin/sh\n'
    printf 'case "$*" in\n'
    printf '  *" diff --raw -z --no-renames --no-abbrev HEAD~1 HEAD --") exit 128 ;;\n'
    printf '  *" show --root --raw "*) exit 128 ;;\n'
    printf 'esac\n'
    printf 'exec "%s" "$@"\n' "$_real"
  } > "$ILL_W/gstub/git"
  chmod +x "$ILL_W/gstub/git"
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null diff --raw -z --no-renames --no-abbrev HEAD~1 HEAD -- >/dev/null 2>&1
  [ "$?" -eq 128 ] || { ill_fin "$ILL_R"; fail "(ill7k) stub self-test: 'diff --raw HEAD~1 HEAD --' must return 128"; }
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null show --root --raw -z --no-renames --no-abbrev --no-show-signature --format= HEAD -- >/dev/null 2>&1
  [ "$?" -eq 128 ] || { ill_fin "$ILL_R"; fail "(ill7k) stub self-test: 'show --root --raw' must return 128"; }
  "$ILL_W/gstub/git" -C "$ILL_R" -c core.fsmonitor=false -c core.hooksPath=/dev/null -c diff.autoRefreshIndex=false diff --name-only --no-renames -z --no-ext-diff --no-textconv --ignore-submodules=dirty HEAD -- >/dev/null 2>&1 \
    || { ill_fin "$ILL_R"; fail "(ill7k) stub self-test: the dirty-tree census must pass through"; }
  ( cd "$ILL_R" && PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  _r1=$?; _o1="$(cat "$ILL_O")"; _a1="$(ill_audit "$ILL_R")"; _v=0; [ -e "$(ill_verdict "$ILL_R")" ] && _v=1
  ( cd "$ILL_R" && PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" --at HEAD ) >"$ILL_O" 2>&1
  _r2=$?; _o2="$(cat "$ILL_O")"; _a2="$(ill_audit "$ILL_R")"
  ill_gate "$ILL_R"
  ill_fin "$ILL_R"
  rm -rf "$ILL_W/gstub"
  for _m in 1 2; do
    if [ "$_m" = 1 ]; then _o="$_o1"; _a="$_a1"; _r="$_r1"; else _o="$_o2"; _a="$_a2"; _r="$_r2"; fi
    [ "$_r" -eq 0 ] || fail "(ill7k) run $_m: rc 0 expected (degrade, never block), got $_r — $_o"
    printf '%s' "$_o" | grep -q 'committed path(s) (the commit census failed)' || fail "(ill7k) run $_m: the failed commit census must be COUNTED: $_o"
    printf '%s' "$_a" | grep -q '"couverture":"refus de conclure"' || fail "(ill7k) run $_m: audit couverture must be 'refus de conclure': $_a"
    printf '%s' "$_o" | grep -q -e 'clean on the diff' -e 'nothing to scan' -e "rien à lire, ce n'est pas un aveuglement" && fail "(ill7k) run $_m: benign sentence over the lost committed sink: $_o"
    printf '%s' "$_o" | grep -q -e 'dirty-tree census' -e 'unreachable' -e 'unreadable' -e 'warning line(s)' -e 'submodule' && fail "(ill7k) run $_m: single-source fixture carries another loss: $_o"
  done
  [ "$_v" -eq 0 ] || fail "(ill7k) a failed commit census must leave no common verdict"
  [ "$ILL_RC" -eq 1 ] || fail "(ill7k) witness without the git stub: the committed sink is found (rc 1), got $ILL_RC — $(cat "$ILL_O")"
  ok "(ill7k) 'diff X~1 X' and 'show' rc 128 => commit census counted, refus de conclure, no verdict, default AND --at HEAD; without stub => rc 1"
}

arm_ill7h() {  # a FAILED census at the hook Stop is never mute (pairs M7); R4 no longer breaks it
  # T-01M4Z24V0J813T40XRW3S4VW67: the Stop's root diff carries
  # `--ignore-submodules=dirty` and no longer opens a submodule's git dir, so R4
  # (that git dir behind chmod 000) cannot fail the census of the Stop's own
  # perimeter any more — the submodules stay outside it (bound written in the
  # README). The census failure is now driven by the stub of (ill7c), on the
  # argv the Stop emits; R4 is replayed with a root sink, which must be FOUND.
  _s="$(mk_super_sg)"
  _real="$(command -v git)"
  mkdir -p "$ILL_W/gstub"
  {
    printf '#!/bin/sh\n'
    printf 'case "$*" in\n'
    printf '  *"--ignore-submodules=dirty HEAD --") exit 128 ;;\n'
    printf 'esac\n'
    printf 'exec "%s" "$@"\n' "$_real"
  } > "$ILL_W/gstub/git"
  chmod +x "$ILL_W/gstub/git"
  printf 'r = 2\n' > "$_s/README.md"
  ( cd "$_s" && printf '%s' "$(ill_stop ill7h)" \
      | env PATH="$ILL_W/gstub:$ILL_W/stub:$PATH" AGENTS_HOOK_HOST=claude SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" --hook --event=stop ) >"$ILL_HO" 2>"$ILL_HE"
  _ho="$(cat "$ILL_HO")"; _he="$(cat "$ILL_HE")"; _sp=0; [ -f "$_s/.agents/state/local/semgrep-hook/stop-propre" ] && _sp=1
  rm -rf "$ILL_W/gstub"
  printf "$ILL_SINK" > "$_s/r.py"
  chmod 000 "$_s/.git/modules/sub"
  ill_hook "$_s" stop "$(ill_stop ill7h-r4)"; _r4=$ILL_RC
  chmod 755 "$_s/.git/modules/sub"
  rm -f "$_s/r.py"; printf 'root\n' > "$_s/README.md"
  ill_hook "$_s" stop "$(ill_stop ill7h-l)"
  ill_super_fin "$_s"
  printf '%s' "$_ho" | grep -q '"systemMessage": "COVERAGE DEGRADED' || fail "(ill7h) a failed census at the Stop must say COVERAGE DEGRADED (never mute): $_ho / $_he"
  printf '%s' "$_he" | grep -q 'dirty-tree census FAILED' || fail "(ill7h) the failed census must be said on stderr: $_he"
  [ "$_sp" -eq 0 ] || fail "(ill7h) a Stop that lost its census must not leave stop-propre"
  [ "$_r4" -eq 2 ] || fail "(ill7h) R4 (submodule git dir 000) must no longer break the Stop's census: the root sink r.py blocks (rc 2), got $_r4 — $(cat "$ILL_HE")"
  [ "$ILL_RC" -eq 0 ] && [ ! -s "$ILL_HO" ] || fail "(ill7h) witness: readable gitdir, clean tree => mute rc 0, got $ILL_RC: $(cat "$ILL_HO")"
  ok "(ill7h) census diff rc 128 at the Stop => systemMessage COVERAGE DEGRADED, no stop-propre; R4 + root sink => rc 2; readable => mute"
}

arm_ill7n() {  # NOHEAD: a repo without a commit scans its indexed tree
  ill_repo; printf "$ILL_SINK" > "$ILL_R/a.py"; $ILL_G -C "$ILL_R" add a.py >/dev/null 2>&1
  ill_gate "$ILL_R"; _g=$ILL_RC; _o="$(cat "$ILL_O")"
  ill_hook "$ILL_R" stop "$(ill_stop ill7n)"; _h=$ILL_RC
  # The benign witness is staged TOO (T-01M4XY8NC97JBSQP6C28AFD7QP): the index
  # is now read, and an index still holding the sink under a benign tree is the
  # defect that task closes — arm (obj7), never a clean.
  printf 'x = 1\n' > "$ILL_R/a.py"; $ILL_G -C "$ILL_R" add a.py >/dev/null 2>&1
  ill_gate "$ILL_R"
  ill_fin "$ILL_R"
  [ "$_g" -eq 1 ] || fail "(ill7n) no commit + indexed sink => gate rc 1, got $_g — $_o"
  [ "$_h" -eq 2 ] || fail "(ill7n) no commit + indexed sink => hook Stop rc 2, got $_h — $(cat "$ILL_HE")"
  grep -q 'clean on the diff' "$ILL_O" || fail "(ill7n) witness: benign a.py => 'clean on the diff': $(cat "$ILL_O")"
  ok "(ill7n) no commit: indexed sink => gate rc 1, hook rc 2; benign => clean on the diff"
}

arm_ill8() {  # R5: a 000 file in a readable directory (pairs M8)
  ill_fx_ill "$ILL_SINK" 'z = 1\n'
  ill_gate "$ILL_R"; _g=$ILL_RC; _o="$(cat "$ILL_O")"
  ill_hook "$ILL_R" stop "$(ill_stop ill8)"; _h=$ILL_RC; _he="$(cat "$ILL_HE")"
  chmod 644 "$ILL_R/k.py"
  ill_gate "$ILL_R"
  ill_fin "$ILL_R"
  [ "$_g" -eq 1 ] || fail "(ill8) the finding of a.py must survive the unreadable k.py (gate rc 1), got $_g — $_o"
  printf '%s' "$_o" | grep -q '1 listed file(s) unreadable' || fail "(ill8) the unreadable k.py must be counted: $_o"
  printf '%s' "$_o" | grep -q -e 'unreachable' -e 'warning line(s)' -e 'census' && fail "(ill8) single-source fixture carries another loss: $_o"
  [ "$_h" -eq 2 ] || fail "(ill8) hook Stop must block on a.py (rc 2), got $_h — $_he"
  printf '%s' "$_he" | grep -q 'listed file(s) unreadable' || fail "(ill8) hook stderr must carry the loss line: $_he"
  grep -q 'perimeter INCOMPLETE' "$ILL_O" && fail "(ill8) witness: k.py 644 => no loss line: $(cat "$ILL_O")"
  ok "(ill8) a.py sink + k.py 000 => gate rc 1 + '1 listed file(s) unreadable', hook rc 2 + loss line; 644 => no loss"
}

arm_ill9() {  # the switch line: losses alone never block (pairs M11) + the common verdict (C10, pairs M13)
  ill_fx_ill 'x = 1\n' "$ILL_SINK"
  ill_gate "$ILL_R"; _g=$ILL_RC; _o="$(cat "$ILL_O")"; _v=0; [ -e "$(ill_verdict "$ILL_R")" ] && _v=1
  ill_hook "$ILL_R" stop "$(ill_stop ill9)"; _h=$ILL_RC
  chmod 644 "$ILL_R/k.py"
  ill_gate "$ILL_R"
  _vt="$(cat "$(ill_verdict "$ILL_R")" 2>/dev/null)"
  ill_fin "$ILL_R"
  [ "$_g" -eq 0 ] || fail "(ill9) a loss alone must not block the gate (rc 0, decision S-01M4XWS5WEV0DDV98HP04H8K9M), got $_g — $_o"
  [ "$_h" -eq 0 ] || fail "(ill9) a loss alone must not block the hook (rc 0), got $_h — $(cat "$ILL_HE")"
  ok "(ill9) loss alone (k.py 000) => gate rc 0 and hook rc 0"
  [ "$_v" -eq 0 ] || fail "(ill8v) k.py 000 carrying the sink: NO semgrep-verdict.json may say status=clean"
  printf '%s' "$_o" | grep -q 'verdict commun non rendu (périmètre incomplet)' || fail "(ill8v) the fixed line must say why there is no verdict: $_o"
  printf '%s' "$_vt" | grep -q '"status": *"findings"' || fail "(ill8v) witness: k.py 644 => verdict status=findings rendered, got: $_vt"
  ok "(ill8v) R5SV: no common verdict + 'verdict commun non rendu (périmètre incomplet)'; 644 => status=findings"
}

arm_ill9e() {  # canal A: a loss with no finding never emits status=scanned (closing review T1)
  # `emit_scan` swallows its own output (`>/dev/null 2>&1 || true`), so the
  # event is read through a fake `.claude/hooks/emit-event.sh` that appends its
  # `status=` argument. The fake is COMMITTED in the base commit: outside the
  # HEAD-only perimeter, it never becomes a scanned or a lost file.
  ill_repo; mkdir -p "$ILL_R/.claude/hooks"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$2" >> "%s"\n' "$ILL_W/emit" > "$ILL_R/.claude/hooks/emit-event.sh"
  ill_commit
  printf 'x = 1\n' > "$ILL_R/a.py"; printf "$ILL_SINK" > "$ILL_R/k.py"; chmod 000 "$ILL_R/k.py"
  : > "$ILL_W/emit"; ill_gate "$ILL_R"; _e="$(tail -1 "$ILL_W/emit")"; _o="$(cat "$ILL_O")"
  chmod 644 "$ILL_R/k.py"; printf 'x = 1\n' > "$ILL_R/k.py"
  : > "$ILL_W/emit"; ill_gate "$ILL_R"; _w="$(tail -1 "$ILL_W/emit")"
  ill_fin "$ILL_R"
  [ "$_e" = "status=degraded" ] || fail "(ill9e) loss + 0 finding must emit status=degraded, got '$_e' — $_o"
  [ "$_w" = "status=scanned" ] || fail "(ill9e) witness: no loss => status=scanned, got '$_w' — $(cat "$ILL_O")"
  ok "(ill9e) canal A: loss alone at the final exit => scan.sast status=degraded; witness => status=scanned"
}

arm_ill10() {  # TMPDIR not writable: no signal file, no capture file (pairs M15; C21 fallback)
  # C21 — the "stderr not captured" fallback is witnessed HERE only jointly with
  # "perimeter signals unavailable": one TMPDIR makes BOTH mktemps fail together.
  # RÉSIDU NON TÉMOIGNÉ: the capture mktemp failing ALONE (signal file created,
  # capture file not) has no arm — no fixture makes one of two mktemps of the
  # same TMPDIR fail without the other.
  ill_fx_r1
  mkdir -p "$ILL_W/ro"; chmod 555 "$ILL_W/ro"
  # LC_ALL=C: bash's own error text is localised (measured: a French host prints
  # « erreur de syntaxe arithmétique »), and an arithmetic error on "?" aborts the
  # WHOLE enclosing compound command, perimeter included, with rc 0 — so the arm
  # also requires the lines that only a COMPLETE run prints.
  ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" TMPDIR="$ILL_W/ro" LC_ALL=C SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_W/out555" 2>&1
  _rc=$?
  chmod 755 "$ILL_W/ro"
  _o="$(cat "$ILL_W/out555")"
  ill_gate "$ILL_R"
  ill_fin "$ILL_R" "$ILL_R/d"
  [ "$_rc" -eq 0 ] || fail "(ill10) TMPDIR 555: rc 0 expected, got $_rc — $_o"
  printf '%s' "$_o" | grep -q -e 'syntax error' -e 'unbound variable' -e 'arithmetic' && fail "(ill10) unwritable TMPDIR aborted the script: $_o"
  printf '%s' "$_o" | grep -q '1 listed path(s) unreachable' || fail "(ill10) the perimeter must still be built and its loss counted: $_o"
  printf '%s' "$_o" | grep -q 'verdict commun non rendu (périmètre incomplet)' || fail "(ill10) every loss must reach PERTE_N (no common verdict): $_o"
  printf '%s' "$_o" | grep -q 'perimeter signals unavailable' || fail "(ill10) no signal file must be a COUNTED loss: $_o"
  printf '%s' "$_o" | grep -q 'untracked census stderr not captured' || fail "(ill10) no capture file must be a COUNTED loss (C21): $_o"
  ill_benin "$ILL_W/out555" && fail "(ill10) TMPDIR 555 printed a benign sentence over R1: $_o"
  [ "$ILL_RC" -eq 0 ] || fail "(ill10) witness run: rc 0 expected, got $ILL_RC — $(cat "$ILL_O")"
  grep -q 'perimeter signals unavailable' "$ILL_O" && fail "(ill10) witness: writable TMPDIR => signals available: $(cat "$ILL_O")"
  ok "(ill10) TMPDIR 555 => 'perimeter signals unavailable' + 'stderr not captured' counted, no abort; writable => signals available"
}

arm_ill11() {  # no signal/capture file survives any exit
  _t="$(mktemp -d)"; assert_tmpdir "$_t"
  ill_fx_r1
  ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" TMPDIR="$_t" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >/dev/null 2>&1
  ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" TMPDIR="$_t" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" --at no-such-ref ) >/dev/null 2>&1
  ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" TMPDIR="$_t" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" --since no-such-base ) >/dev/null 2>&1
  ill_fin "$ILL_R" "$ILL_R/d"
  ill_repo; printf 'a = 1\n' > "$ILL_R/a.py"; ill_commit
  $ILL_G -C "$ILL_R" checkout -q -b x >/dev/null 2>&1
  printf 'b = 1\n' > "$ILL_R/b.py"; $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm x >/dev/null 2>&1
  $ILL_G -C "$ILL_R" checkout -q - >/dev/null 2>&1
  printf 'c = 1\n' > "$ILL_R/c.py"; $ILL_G -C "$ILL_R" add -A >/dev/null 2>&1; $ILL_G -C "$ILL_R" commit -qm c >/dev/null 2>&1
  $ILL_G -C "$ILL_R" merge -q --no-ff -m m x >/dev/null 2>&1
  ( cd "$ILL_R" && PATH="$ILL_W/stub:$PATH" TMPDIR="$_t" SEMGREP_CONFIG="$RULESET" "$SUITE_BASH" "$SCRIPT" ) >"$ILL_O" 2>&1
  ill_fin "$ILL_R"
  grep -q 'HEAD is a MERGE' "$ILL_O" || { rm -rf "$_t"; fail "(ill11) non-vacuity: the merge refusal was not reached: $(cat "$ILL_O")"; }
  _n="$(find "$_t" -mindepth 1 -maxdepth 1 \( -name 'semgrep-sig.*' -o -name 'semgrep-lserr.*' \) | wc -l | tr -d ' ')"
  rm -rf "$_t"
  [ "$_n" -eq 0 ] || fail "(ill11) $_n semgrep-sig/semgrep-lserr temp file(s) left behind in a dedicated TMPDIR"
  ok "(ill11) R1, --at <unknown>, --since <unknown>, merge refusal => no semgrep-sig/lserr temp file left"
}

arm_ill12() {  # outside any git repository the scope line says so (closing review T4)
  _d="$(mktemp -d)"; assert_tmpdir "$_d"
  if git -C "$_d" rev-parse --git-dir >/dev/null 2>&1; then
    rm -rf "$_d"; echo "  SKIP (ill12): the temp root sits inside a git repository"; return 0
  fi
  printf 'x = 1\n' > "$_d/a.py"
  ill_gate "$_d"; _rc=$ILL_RC; _o="$(cat "$ILL_O")"
  rm -rf "$_d"
  ill_repo; printf 'x = 1\n' > "$ILL_R/a.py"
  ill_gate "$ILL_R"
  ill_fin "$ILL_R"
  [ "$_rc" -eq 0 ] || fail "(ill12) outside git: rc 0 expected, got $_rc — $_o"
  printf '%s' "$_o" | grep -q 'perimeter = hors dépôt git' || fail "(ill12) outside git the scope line must say 'hors dépôt git': $_o"
  printf '%s' "$_o" | grep -q 'aucun commit' && fail "(ill12) outside git is not 'no commit yet': $_o"
  printf '%s' "$_o" | grep -q -e 'clean on the diff' -e 'nothing to scan' && fail "(ill12) outside git: benign sentence over a failed census: $_o"
  grep -q 'perimeter = arbre sale (aucun commit)' "$ILL_O" || fail "(ill12) witness: a repo without a commit keeps 'arbre sale (aucun commit)': $(cat "$ILL_O")"
  ok "(ill12) outside any git repository => 'perimeter = hors dépôt git', no benign sentence; repo without commit => 'aucun commit'"
}

# ---- (ill) CALLS ----
if [ -n "$ILL_SKIP" ]; then
  echo "  SKIP (ill1 ill1i ill1w ill1a ill1s ill2 ill4 ill4x ill4p ill4m ill5 ill6 ill6b ill6w ill7 ill7h ill8 ill9 ill8v ill9e ill10 ill11): $ILL_SKIP"
else
  arm_ill1; arm_ill1i; arm_ill1w; arm_ill1a; arm_ill1s; arm_ill2
  arm_ill4; arm_ill4x; arm_ill4p; arm_ill4m; arm_ill5
  arm_ill6; arm_ill6b; arm_ill6w; arm_ill7; arm_ill7h
  arm_ill8; arm_ill9; arm_ill9e; arm_ill10
fi
arm_ill3; arm_ill6d; arm_ill7c; arm_ill7s; arm_ill7l; arm_ill7k; arm_ill7n; arm_ill12
if [ -z "$ILL_SKIP" ]; then arm_ill11; fi
rm -rf "$ILL_W"

# The cwd arms wrote into the throwaway repo, never into the caller's tree.
cd / && rm -rf "$SUITE_CWD"

echo "PASS: semgrep-scan ($pass check(s); semgrep present=$HAVE_SEMGREP)"
