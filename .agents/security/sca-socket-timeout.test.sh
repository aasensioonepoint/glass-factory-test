#!/usr/bin/env bash
# Behavioural regression suite for T-00000202. Every case executes the real
# sca-scan.sh; only the external npm, Socket and Trivy CLIs are deterministic.
#
# TIMING DOCTRINE (T-00000305) — READ THIS BEFORE DIAGNOSING A RED HERE.
# This suite blocked two real deliveries by turning red on a product that was
# fine: it ran the whole gate against a 25s external watchdog and read the
# resulting 124 as a verdict, in the same words a genuine defect would produce
# (L-00000234). Two consecutive nights, the Windows leg went red at 23s then at
# 14s — FASTER as the machine got busier — while the Linux leg stayed green and
# `main` stayed red over a fix that was already proven.
#
# So every verdict below measures a STATE — a witness file, an exit code, an
# exact diagnostic string — and every clock is only a GENEROUS CAP on the wait
# for that state. NO VERDICT IS EVER TAKEN ON A CLOCK BELOW ITS BOUND. A run
# that hits a bound exits under its OWN label — DEADLINE BREACH, ARM NOT
# REACHED, MUTANT NOT BUILT, MUTANT NOT REPRODUCED, MUTANT GATE EXITED, FAKE
# SOCKET NOT INVOKED — never as a bare `got 124`. Any of those labels means
# REPLAY ON A CALM BOX FIRST; none of them is a product diagnosis.
#
# Sensitivity, stated so it can be checked instead of trusted. The worst
# latencies MEASURED on this repo are 17s of Git-Bash spawn under a full gate
# (T-00000390) and 8-17s of SIGKILL delivery (S-00000827). Every fixed duration
# here is >= 1.7x the worst latency it has to dominate: HANG_TIMEOUT 30s and
# DEADLINE 120s against 17s of spawn, GRACE 60s against 17+5s of SIGKILL. Only
# ONE of them can still turn red — HANG_TIMEOUT — and it does so labelled
# `ARM NOT REACHED (contention)`, which needs a single bash to take over 30s to
# spawn: never yet measured anywhere.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "$0")" && pwd)"
SCAN="$HERE/sca-scan.sh"
TMP="$(mktemp -d)"
# Installed IMMEDIATELY, and deliberately not the richer trap below: the knob
# validation a few lines down can `fail` before `cleanup_case` exists, and a trap
# naming a function that is not defined yet would fire
# `command_not_found_handle` — which core-scripts/run-bash-tests.sh reads as a
# MISSING DEP, turning a bad env var into a red attributed to a phantom tool.
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $1"; exit 1; }
ok() { echo "  ok: $1"; }

ROOT="$TMP/repo"
BIN="$TMP/bin"
REPORTS="$ROOT/.agents/state/local/sca-reports"
EVENTS_FILE="$ROOT/.agents/state/local/emitted-events.log"
MARKER="$TMP/socket-invoked"
# The ARM: two witness files the fake socket publishes about ITSELF. They are
# what turns "the clock ran out" into "the state was reached", and they are what
# a red message carries so the reader can tell the two apart.
SOCKET_PID_FILE="$TMP/socket.pid"
SOCKET_TERM_FILE="$TMP/socket.term"

# A CAP ON A WAIT, NOT A THRESHOLD. Nothing is judged sooner because this is
# small; a case that reaches it dies LABELLED. Floor of 30s because the shortest
# legitimate hang case already costs ~40s. Ceiling of 900s because that is
# core-scripts/run-bash-tests.sh's own per-suite watchdog: past it the RUNNER's
# TIMEOUT label fires first and replaces every verdict this file can produce —
# and because an unbounded knob feeds `BOUND2` arithmetic that would break with
# a shell error instead of the `fail` message written here.
DEADLINE="${SCA_TEST_DEADLINE_SECONDS:-120}"
case "$DEADLINE" in
  ''|*[!0-9]*) fail "SCA_TEST_DEADLINE_SECONDS must be an integer 30..900, got '$DEADLINE'" ;;
  # 4+ DIGITS ARE REJECTED HERE, BEFORE ANY ARITHMETIC TOUCHES THEM. `[ x -ge y ]`
  # on a value past the 64-bit range does not return false, it writes a raw shell
  # error to stderr — so the refusal below would arrive already preceded by noise
  # this file did not author. Nothing with four digits can be within 30..900.
  ????*) fail "SCA_TEST_DEADLINE_SECONDS must be an integer 30..900, got '$DEADLINE' (4+ digits is never in range)" ;;
esac
{ [ "$DEADLINE" -ge 30 ] && [ "$DEADLINE" -le 900 ]; } \
  || fail "SCA_TEST_DEADLINE_SECONDS must be 30..900 (floor: a hang case legitimately takes ~40s; ceiling: run-bash-tests.sh kills a suite at 900s), got $DEADLINE"

# The PRODUCT-side socket timeout used by the hang cases. 30s DOMINATES the 17s
# spawn measured on Git Bash — the old 1s did not, which is how a slow spawn
# became a fake product verdict. The product accepts 1..900
# (README-SECURITY-SCAN-SETUP.md:290), so this stays inside its own contract.
# On a calm box, SCA_TEST_HANG_TIMEOUT_SECONDS=5 cuts the wall time.
HANG_TIMEOUT="${SCA_TEST_HANG_TIMEOUT_SECONDS:-30}"
case "$HANG_TIMEOUT" in
  ''|*[!0-9]*) fail "SCA_TEST_HANG_TIMEOUT_SECONDS must be an integer 1..900, got '$HANG_TIMEOUT'" ;;
  # Same guard as DEADLINE above, same reason: out-of-range arithmetic answers
  # with a shell error on stderr, not with a verdict this file chose.
  ????*) fail "SCA_TEST_HANG_TIMEOUT_SECONDS must be an integer 1..900, got '$HANG_TIMEOUT' (4+ digits is never in range)" ;;
esac
{ [ "$HANG_TIMEOUT" -ge 1 ] && [ "$HANG_TIMEOUT" -le 900 ]; } \
  || fail "SCA_TEST_HANG_TIMEOUT_SECONDS must be within the product's own 1..900 bound, got $HANG_TIMEOUT"

# How long case 2 HOLDS the reproduction open. A constant, >= 2x (17s SIGKILL
# delivery + 5s kill-after): a socket that dies inside this window died of
# something other than an escalation the mutant does not have.
GRACE=60
# The background case's own bound, with >= 29s of tail left after the release —
# more than the 17s worst spawn — so its final rc is a product answer and not a
# watchdog's.
BOUND2=$((DEADLINE + GRACE + 30))

GNU_TIMEOUT="$(command -v timeout)"
# SKIP (not FAIL) when GNU timeout is absent: this suite drives sca-scan.sh's
# EXTERNAL socket watchdog, which is GNU `timeout --kill-after` specifically. A
# vanilla macOS/BSD runner ships no GNU timeout (no coreutils) and sca-scan.sh
# itself DEGRADES there — so the watchdog behaviour is untested on that platform,
# not broken. A machine with coreutils runs every case as before.
skip() { echo "SKIP: $1"; exit 0; }
[ -n "$GNU_TIMEOUT" ] || skip "no GNU timeout on PATH (vanilla macOS/BSD) — external-watchdog cases need GNU coreutils"
"$GNU_TIMEOUT" --version 2>/dev/null | grep -q 'GNU coreutils' \
  || skip "timeout on PATH is not GNU coreutils — external-watchdog cases skipped"

# Per-case process state. Declared here so cleanup is safe on every exit path,
# including one taken before the first case ever launches.
SOCKET_PID=""
GATE_PID=""
CASE_RC=""
CASE_ELAPSED=""
CASE_STARTED=0
CASE_LOG=""
CASE_OUT=""
CASE_DEGRADED=""
CASE_EVENT=""
WITNESS_MARKER="no"
WITNESS_PID_FILE="no"
WITNESS_TERM_FILE="no"
WITNESSES=""

# Kills what this case launched, in the only order that reaches all of it. The
# socket FIRST and BY PID: the product's inner `timeout` does setpgid(0,0), so
# the socket lives in ITS process group, out of reach of any group kill issued
# from here. Then the gate's whole group, whose leader is the outer timeout.
# Idempotent, and that means CONSUMING both sources of the PID — the variable
# AND the file. Blanking the variable alone was not enough and the first version
# of this comment claimed otherwise: the EXIT trap re-runs this function after a
# fail_case, `[ -s "$SOCKET_PID_FILE" ]` re-derived the very same number, and a
# second `kill -KILL` went out without rechecking that the number still
# designates the process it was read from. Sub-second window, nothing external
# aims at it — but a guarantee that is WRITTEN and not HELD is what stops anyone
# from seeing the defect (L-00000111), so the file is emptied here.
cleanup_case() {
  if [ -z "$SOCKET_PID" ] && [ -s "$SOCKET_PID_FILE" ]; then
    SOCKET_PID="$(cat "$SOCKET_PID_FILE" 2>/dev/null)"
  fi
  # Emptied BEFORE the kill, unconditionally: a kill that fails, or a PID this
  # call could not derive, must still leave nothing behind to re-derive.
  : > "$SOCKET_PID_FILE" 2>/dev/null
  [ -n "$SOCKET_PID" ] && kill -KILL "$SOCKET_PID" 2>/dev/null
  if [ -n "$GATE_PID" ]; then
    kill -KILL -- -"$GATE_PID" 2>/dev/null
    wait "$GATE_PID" 2>/dev/null || true
  fi
  SOCKET_PID=""
  GATE_PID=""
  return 0
}
# Now that cleanup_case exists, the EXIT trap is upgraded to reap processes too,
# so no exit path — red, green, or interrupted — can leave a gate behind.
trap 'cleanup_case; rm -rf "$TMP"' EXIT

# Every red path from here on: never leave a gate or a hung fake behind.
fail_case() { cleanup_case; fail "$1"; }

read_case_outputs() {
  CASE_OUT="$(cat "$CASE_LOG" 2>/dev/null || true)"
  CASE_DEGRADED="$(cat "$REPORTS/.degraded" 2>/dev/null || true)"
  CASE_EVENT="$(cat "$EVENTS_FILE" 2>/dev/null || true)"
  return 0
}

read_witnesses() {
  WITNESS_MARKER="no"; [ -e "$MARKER" ] && WITNESS_MARKER="yes"
  WITNESS_PID_FILE="no"; [ -s "$SOCKET_PID_FILE" ] && WITNESS_PID_FILE="yes"
  WITNESS_TERM_FILE="no"; [ -e "$SOCKET_TERM_FILE" ] && WITNESS_TERM_FILE="yes"
  WITNESSES="marker=$WITNESS_MARKER pid_file=$WITNESS_PID_FILE term_file=$WITNESS_TERM_FILE"
  return 0
}

# THE ONE RULE THAT MAKES A CLOCK UNABLE TO IMPERSONATE THE PRODUCT. 124 = the
# TERM deadline fired, 137 = the SIGKILL escalation was needed; both are also
# reachable from a gate that ended on its own, so the elapsed time has to AGREE
# before the watchdog is blamed. Same shape as core-scripts/run-bash-tests.sh, on
# purpose: one model of "the bound fired", read the same way in both places.
classify_rc() {
  local rc="$1" elapsed="$2" bound="$3" name="$4"
  if { [ "$rc" = "124" ] || [ "$rc" = "137" ]; } && [ "$elapsed" -ge "$bound" ]; then
    fail_case "DEADLINE BREACH (contention, not a product verdict — L-00000234): $name still running after ${elapsed}s, bound ${bound}s — replay on a calm box before diagnosing anything"
  fi
  return 0
}

mkdir -p "$REPORTS" "$ROOT/.agents/security" "$ROOT/.claude/hooks" "$BIN" \
  || fail "fixture: mkdir of the synthetic tree failed"
git -C "$ROOT" init -q || fail "fixture: git init failed"
git -C "$ROOT" -c user.email=test@test.local -c user.name=test \
  commit -q --allow-empty -m init || fail "fixture: git commit failed"
cat > "$ROOT/package.json" <<'JSON' || fail "fixture: package.json"
{"name":"socket-timeout-fixture","version":"1.0.0"}
JSON
cat > "$ROOT/package-lock.json" <<'JSON' || fail "fixture: package-lock.json"
{"name":"socket-timeout-fixture","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"socket-timeout-fixture","version":"1.0.0"}}}
JSON
printf '%s\n' '{"version":1,"waivers":[]}' > "$ROOT/.agents/security/sca-waivers.json" \
  || fail "fixture: sca-waivers.json"

cat > "$BIN/npm" <<'SH' || fail "fixture: fake npm"
#!/usr/bin/env bash
printf '%s\n' '{"auditReportVersion":2,"vulnerabilities":{},"metadata":{"vulnerabilities":{"info":0,"low":0,"moderate":0,"high":0,"critical":0,"total":0}}}'
SH
# PIÈGE 2, stated (T-01M4Z33N54TX0Q7VHBZATFNR4X): `success` KEEPS `{"ok":true}`.
# That report carries no alert list, so waiver_filter.py now names it DEGRADED,
# with rc 0 unchanged, and socket_ok pins that line. `alerts` answers a
# RECOGNISED empty list, which must produce no line at all (socket_alerts).
cat > "$BIN/socket" <<'SH' || fail "fixture: fake socket"
#!/usr/bin/env bash
[ -n "${SOCKET_MARKER:-}" ] && : > "$SOCKET_MARKER"
case "${SOCKET_BEHAVIOR:-success}" in
  success) printf '%s\n' '{"ok":true}' ;;
  alerts) printf '%s\n' '{"alerts":[]}' ;;
  fail) exit 42 ;;
  exit137) exit 137 ;;
  hang)
    # THE ARM, IN THIS ORDER AND NO OTHER. Publishing the PID FIRST is what
    # makes the invariant hold: a TERM witness implies a PID witness. A TERM
    # landing between these two lines kills this fake outright, and the caller
    # then reads a MISSING witness as ARM NOT REACHED — contention — instead of
    # blaming the product.
    printf '%s\n' "$$" > "$SOCKET_PID_FILE"
    # A HANDLER, not `trap '' TERM` + `exec sleep`. Ignoring TERM proves only
    # that the signal was ignorable; RECORDING it proves the TERM was received
    # AND survived, which is what leaves the SIGKILL escalation as the only
    # thing that can end this process.
    trap ': > "$SOCKET_TERM_FILE"' TERM
    # Unbounded BY DESIGN: this fake must never end itself, or the escalation
    # under test would be credited for a death it did not cause. `sleep 1` and
    # not a long sleep, so a KILL on this shell leaves no orphan past a second.
    while :; do sleep 1; done
    ;;
  *) exit 99 ;;
esac
SH
cat > "$BIN/trivy" <<'SH' || fail "fixture: fake trivy"
#!/usr/bin/env bash
out=""
while [ "$#" -gt 0 ]; do
  [ "$1" = "--output" ] && { shift; out="$1"; }
  shift
done
[ -n "$out" ] && printf '%s\n' '{"SchemaVersion":2}' > "$out"
SH
cat > "$ROOT/.claude/hooks/emit-event.sh" <<'SH' || fail "fixture: emit-event.sh"
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CLAUDE_PROJECT_DIR/.agents/state/local/emitted-events.log"
SH
chmod +x "$BIN/npm" "$BIN/socket" "$BIN/trivy" "$ROOT/.claude/hooks/emit-event.sh" \
  || fail "fixture: chmod of the fake CLIs failed"

# ONE environment for BOTH voices. A synchronous case and a background case that
# could drift apart in what they export would make case 2 unable to speak about
# case 1. Ends in `exec`, so the PID the caller holds IS the GNU timeout — a
# process-group leader, which is what makes `kill -KILL -- -PID` reach the whole
# gate tree in cleanup.
_gate_exec() {
  cd "$ROOT" || exit 98
  export PATH="$BIN:$PATH" SCA_AUDIT_DEV_DEPS=0
  export SOCKET_BEHAVIOR="$LAUNCH_BEHAVIOR" SOCKET_MARKER="$MARKER"
  export SOCKET_PID_FILE SOCKET_TERM_FILE
  if [ "$LAUNCH_TIMEOUT_VALUE" = "unset" ]; then
    unset SCA_SOCKET_TIMEOUT_SECONDS
  else
    export SCA_SOCKET_TIMEOUT_SECONDS="$LAUNCH_TIMEOUT_VALUE"
  fi
  if [ -n "$LAUNCH_BASH_ENV" ]; then export BASH_ENV="$LAUNCH_BASH_ENV"; else unset BASH_ENV; fi
  exec "$GNU_TIMEOUT" --kill-after=5 "${LAUNCH_BOUND}s" bash "$LAUNCH_SCANNER"
}

# launch_case NAME SCANNER TIMEOUT_VALUE SOCKET_BEHAVIOR TIMEOUT_MODE [STALE] [BG] [BOUND]
# TIMEOUT_VALUE="unset" leaves the production default in force.
# BG="bg" hands back a LIVING gate (GATE_PID) instead of a finished one, which is
# what lets case 2 observe a condition while the gate is still in it.
launch_case() {
  LAUNCH_NAME="$1"
  LAUNCH_SCANNER="$2"
  LAUNCH_TIMEOUT_VALUE="$3"
  LAUNCH_BEHAVIOR="$4"
  local mode="$5" stale="${6:-no}" bg="${7:-no}"
  LAUNCH_BOUND="${8:-$DEADLINE}"
  LAUNCH_BASH_ENV=""
  CASE_LOG="$TMP/$LAUNCH_NAME.log"

  SOCKET_PID=""
  GATE_PID=""
  CASE_RC=""
  CASE_ELAPSED=""
  rm -f "$EVENTS_FILE" "$MARKER" "$BIN/timeout" "$REPORTS/socket.json" \
        "$SOCKET_PID_FILE" "$SOCKET_TERM_FILE" \
    || fail "reset: could not clear the case witnesses"
  if [ "$stale" = "yes" ]; then
    printf '%s\n' '{"stale":true}' > "$REPORTS/socket.json" || fail "reset: could not seed a stale socket.json"
  fi
  case "$mode" in
    gnu) ;;
    non_gnu)
      cat > "$BIN/timeout" <<'SH' || fail "fixture: fake non-GNU timeout"
#!/usr/bin/env bash
echo "not a GNU utility"
exit 0
SH
      chmod +x "$BIN/timeout" || fail "fixture: chmod of the fake timeout failed"
      ;;
    absent)
      LAUNCH_BASH_ENV="$TMP/timeout-absent.bash"
      printf '%s\n' 'timeout() { return 127; }' > "$LAUNCH_BASH_ENV" \
        || fail "fixture: could not write the timeout-absent BASH_ENV"
      ;;
    *) fail "unknown timeout mode: $mode" ;;
  esac

  CASE_STARTED=$SECONDS
  if [ "$bg" = "bg" ]; then
    ( _gate_exec ) >"$CASE_LOG" 2>&1 &
    GATE_PID=$!
  else
    ( _gate_exec ) >"$CASE_LOG" 2>&1
    CASE_RC=$?
    CASE_ELAPSED=$((SECONDS - CASE_STARTED))
    read_case_outputs
    classify_rc "$CASE_RC" "$CASE_ELAPSED" "$LAUNCH_BOUND" "$LAUNCH_NAME"
  fi
  return 0
}

# THE MUTANT IS BUILT HERE, BEFORE CASE 1, AND THE REASON IS A MEASUREMENT.
# Its `cmp` guard is the only check in this file that can name a MISSING
# --kill-after=5 in the PRODUCT, and it costs one file comparison. Left inside
# case 2 it never got the chance: a product that had lost its escalation made
# case 1 hang to its bound first, so the suite reported
# `DEADLINE BREACH (contention)` — pointing at the machine — for a genuine
# product regression. Measured on darwin at DEADLINE=30: red in 30s under the
# contention label instead of red in under a second under its own name. Same
# doctrine as the rest of the file, applied to itself: a real defect must not
# inherit a clock's excuse any more than a clock may borrow a defect's words.
MUTANT_DIR="$TMP/mutant"
mkdir -p "$MUTANT_DIR" || fail "fixture: mkdir of the mutant dir failed"
sed 's/timeout --kill-after=5 /timeout /' "$SCAN" > "$MUTANT_DIR/sca-scan.sh" \
  || fail "fixture: sed of the mutant failed"
cp "$HERE/waiver_filter.py" "$MUTANT_DIR/waiver_filter.py" \
  || fail "fixture: cp of waiver_filter.py failed"
# A MUTANT THAT IS NOT A MUTANT ASSERTS NOTHING, and would do it in green.
cmp -s "$SCAN" "$MUTANT_DIR/sca-scan.sh" \
  && fail "MUTANT NOT BUILT: the anchor 'timeout --kill-after=5 ' no longer matches sca-scan.sh — either the product LOST its SIGKILL escalation, or the line moved and case 2 would assert nothing"

echo "=== 1. REAL TIMEOUT IS BOUNDED AND REPORTED"
launch_case timeout "$SCAN" "$HANG_TIMEOUT" hang gnu
read_witnesses
# WITNESSES BEFORE VERDICT. Each branch below names what was MISSING, so a red
# says which state was not reached rather than which number was seen.
if [ "$WITNESS_MARKER" = "no" ]; then
  if grep -q "timed out after ${HANG_TIMEOUT}s" <<<"$CASE_OUT"; then
    fail_case "ARM NOT REACHED (contention): the fake socket started but was TERM-killed before it could touch its marker ($WITNESSES, elapsed=${CASE_ELAPSED}s)"
  fi
  fail_case "FAKE SOCKET NOT INVOKED (env drift): the gate never reached the fake socket ($WITNESSES, elapsed=${CASE_ELAPSED}s): $CASE_OUT"
fi
if [ "$WITNESS_PID_FILE" = "no" ] || [ "$WITNESS_TERM_FILE" = "no" ]; then
  fail_case "ARM NOT REACHED (contention): the fake socket was not armed before the ${HANG_TIMEOUT}s TERM ($WITNESSES, elapsed=${CASE_ELAPSED}s)"
fi
[ "$CASE_RC" -eq 0 ] \
  || fail_case "Socket timeout must preserve gate rc=0, got $CASE_RC ($WITNESSES, elapsed=${CASE_ELAPSED}s, bound=${DEADLINE}s): $CASE_OUT"
grep -q "Socket scan timed out after ${HANG_TIMEOUT}s" <<<"$CASE_OUT" \
  || fail_case "missing exact timeout diagnostic: $CASE_OUT"
grep -q "socket: scan timed out after ${HANG_TIMEOUT}s" <<<"$CASE_DEGRADED" \
  || fail_case "missing exact timeout .degraded reason: $CASE_DEGRADED"
grep -q '"supply_chain":"degraded"' <<<"$CASE_EVENT" \
  || fail_case "timeout event is not degraded: $CASE_EVENT"
grep -q '"supply_chain":"scanned"' <<<"$CASE_EVENT" \
  && fail_case "timeout event falsely reports scanned: $CASE_EVENT"
# THE SIGKILL PATH, PROVEN RATHER THAN ASSUMED (item 3 of T-00000301).
# term_file=yes says the TERM was received AND survived — the handler ran and
# wrote it. rc=0 with the exact diagnostic says the gate then watched its socket
# die. The only thing standing between those two facts is --kill-after=5, so the
# escalation is what ended it. The liveness check below only CONFIRMS: a dead
# PID can be satisfied by a stranger, so it can refute, never prove.
kill -0 "$(cat "$SOCKET_PID_FILE")" 2>/dev/null \
  && fail_case "the fake socket outlived its gate: --kill-after=5 never escalated ($WITNESSES)"
CASE1_ELAPSED="$CASE_ELAPSED"
ok "TERM-ignoring Socket is killed, diagnosed exactly, and degraded"
echo "witness: SIGKILL path took ${CASE1_ELAPSED}s wall (calm ~ HANG_TIMEOUT+5+spawn ~ 40s at HANG_TIMEOUT=${HANG_TIMEOUT}s; >= 70s reads as contention on this box, not as a product regression)"

echo "=== 2. --kill-after=5 IS REQUIRED BEHAVIOUR, NOT SOURCE TEXT"
# Built and guarded above, before case 1 — see the note there.
launch_case no_kill_after "$MUTANT_DIR/sca-scan.sh" "$HANG_TIMEOUT" hang gnu no bg "$BOUND2"

# PHASE A — WAIT FOR THE CONDITION: the TERM was delivered to the fake and
# recorded by it. DEADLINE is the only clock, and reaching it is labelled.
phase_a_end=$((SECONDS + DEADLINE))
term_seen="no"
gate_dead="no"
while [ "$SECONDS" -lt "$phase_a_end" ]; do
  if [ -e "$SOCKET_TERM_FILE" ]; then term_seen="yes"; break; fi
  if ! kill -0 "$GATE_PID" 2>/dev/null; then gate_dead="yes"; break; fi
  sleep 0.5
done

if [ "$term_seen" = "no" ]; then
  read_witnesses
  if [ "$gate_dead" = "yes" ]; then
    wait "$GATE_PID"; rc=$?
    GATE_PID=""
    elapsed=$((SECONDS - CASE_STARTED))
    read_case_outputs
    echo "  witnesses: $WITNESSES rc=$rc elapsed=${elapsed}s bound=${BOUND2}s"
    classify_rc "$rc" "$elapsed" "$BOUND2" no_kill_after
    if [ "$WITNESS_MARKER" = "yes" ] && [ "$WITNESS_TERM_FILE" = "no" ] && [ "$rc" -eq 0 ]; then
      fail_case "ARM NOT REACHED (contention): the mutant gate's socket was TERM-killed before arming ($WITNESSES, elapsed=${elapsed}s)"
    fi
    if [ "$WITNESS_MARKER" = "no" ]; then
      fail_case "FAKE SOCKET NOT INVOKED (env drift): the mutant gate exited rc=$rc after ${elapsed}s without ever touching the fake ($WITNESSES)"
    fi
    fail_case "MUTANT GATE EXITED (rc $rc after ${elapsed}s) while its socket should still be hanging ($WITNESSES)"
  fi
  fail_case "ARM NOT REACHED (contention): TERM never recorded within ${DEADLINE}s ($WITNESSES)"
fi

# PHASE B — HOLD THE CONDITION. With no --kill-after there is no escalation, so
# the socket must still be alive well past its TERM. GRACE is >= 2x the worst
# SIGKILL delivery measured, which is what makes survival here the reproduction
# rather than a coincidence. It is also the POSITIVE measurement of `kill -0` on
# a `$$` published by a fake: held 60s on a live PID, then rc 0 after a KILL on
# that same PID.
[ -s "$SOCKET_PID_FILE" ] \
  || fail_case "ARM STATE INCONSISTENT: a TERM was recorded with no PID file ($WITNESSES)"
SOCKET_PID="$(cat "$SOCKET_PID_FILE")" \
  || fail_case "ARM STATE INCONSISTENT: could not read $SOCKET_PID_FILE ($WITNESSES)"
term_at=$((SECONDS - CASE_STARTED))
hold_end=$((SECONDS + GRACE))
while [ "$SECONDS" -lt "$hold_end" ]; do
  if ! kill -0 "$GATE_PID" 2>/dev/null; then
    wait "$GATE_PID"; rc=$?
    GATE_PID=""
    elapsed=$((SECONDS - CASE_STARTED))
    read_case_outputs
    read_witnesses
    echo "  witnesses: $WITNESSES rc=$rc elapsed=${elapsed}s bound=${BOUND2}s"
    classify_rc "$rc" "$elapsed" "$BOUND2" no_kill_after
    fail_case "MUTANT GATE EXITED (rc $rc after ${elapsed}s) during the ${GRACE}s hold ($WITNESSES)"
  fi
  if ! kill -0 "$SOCKET_PID" 2>/dev/null; then
    read_witnesses
    fail_case "MUTANT NOT REPRODUCED: a socket with no --kill-after died $((SECONDS - CASE_STARTED - term_at))s after its TERM ($WITNESSES)"
  fi
  sleep 0.5
done

# RELEASE, BY THE TEST. The inner `timeout` put the socket in its OWN process
# group, so this explicit KILL on the published PID is the only signal from here
# that reaches it — see the note on cleanup_case.
kill -KILL "$SOCKET_PID" 2>/dev/null
wait "$GATE_PID"; rc=$?
GATE_PID=""
elapsed=$((SECONDS - CASE_STARTED))
read_case_outputs
read_witnesses
echo "  witnesses: $WITNESSES rc=$rc elapsed=${elapsed}s bound=${BOUND2}s"
# BOUND FIRST: a 124 in this tail is a breach with a label, never a bare number.
classify_rc "$rc" "$elapsed" "$BOUND2" no_kill_after
[ "$rc" -eq 0 ] \
  || fail_case "mutant gate rc after release: $rc after ${elapsed}s ($WITNESSES): $CASE_OUT"
SOCKET_PID=""
ok "removing --kill-after=5 leaves the socket alive across a ${GRACE}s hold: the escalation is behaviour, not source text"

echo "=== 3. GNU TIMEOUT UNAVAILABLE NEVER RUNS SOCKET OR REUSES A REPORT"
for mode in absent non_gnu; do
  launch_case "timeout_$mode" "$SCAN" unset success "$mode" yes
  [ "$CASE_RC" -eq 0 ] || fail_case "$mode timeout branch must preserve rc=0, got $CASE_RC: $CASE_OUT"
  grep -q 'GNU timeout not installed' <<<"$CASE_DEGRADED" \
    || fail_case "$mode timeout branch lacks explicit degradation: $CASE_DEGRADED"
  [ ! -e "$REPORTS/socket.json" ] || fail_case "$mode timeout left stale socket.json consumable"
  [ ! -e "$MARKER" ] || fail_case "$mode timeout launched Socket without a bound"
  grep -q '"supply_chain":"degraded"' <<<"$CASE_EVENT" \
    || fail_case "$mode timeout event is not degraded: $CASE_EVENT"
  grep -q '"supply_chain":"scanned"' <<<"$CASE_EVENT" \
    && fail_case "$mode timeout event falsely reports scanned: $CASE_EVENT"
done
ok "absent and non-GNU timeout paths are safe and remove stale output"

echo "=== 4. SOCKET EXIT CODES MAP TO HONEST STATES"
# The exact line waiver_filter.py writes for a socket report with no alert list.
SOCKET_NO_ALERTS='waiver_filter: report socket.json carries no alert list — supply-chain layer NOT read, coverage DEGRADED'
launch_case socket_ok "$SCAN" 1 success gnu
[ "$CASE_RC" -eq 0 ] || fail_case "successful Socket changed gate rc: $CASE_RC"
[ -s "$REPORTS/socket.json" ] || fail_case "successful Socket did not retain its report"
grep -q '"supply_chain":"scanned"' <<<"$CASE_EVENT" \
  || fail_case "successful Socket event is not scanned: $CASE_EVENT"
# EQUALITY on the `waiver_filter: ` subset of .degraded, never on the whole file.
# Other blocks write their own reasons to it on every run: the trivy stub leaves
# no `Results`, so a trivy line is there too.
socket_wf="$(LC_ALL=C grep '^waiver_filter: ' <<<"$CASE_DEGRADED")"
[ "$socket_wf" = "$SOCKET_NO_ALERTS" ] \
  || fail_case "Socket {\"ok\":true}: the waiver_filter lines of .degraded must be EXACTLY the no-alert-list line, got [$socket_wf] in: $CASE_DEGRADED"

# The pair: a report WITH an alert list, even an empty one, is read, so no line.
launch_case socket_alerts "$SCAN" 1 alerts gnu
[ "$CASE_RC" -eq 0 ] || fail_case "Socket {\"alerts\":[]} changed gate rc: $CASE_RC: $CASE_OUT"
[ -s "$REPORTS/socket.json" ] || fail_case "Socket {\"alerts\":[]} did not retain its report"
grep -q '"supply_chain":"scanned"' <<<"$CASE_EVENT" \
  || fail_case "Socket {\"alerts\":[]} event is not scanned: $CASE_EVENT"
LC_ALL=C grep -Fq 'waiver_filter: report socket.json' <<<"$CASE_DEGRADED" \
  && fail_case "Socket {\"alerts\":[]} produced a waiver_filter socket line: $CASE_DEGRADED"

launch_case socket_fail "$SCAN" 1 fail gnu
[ "$CASE_RC" -eq 0 ] || fail_case "optional Socket exit 42 changed gate rc: $CASE_RC"
grep -q 'Socket scan failed (exit 42)' <<<"$CASE_OUT" \
  || fail_case "generic Socket failure lacks its exit diagnostic: $CASE_OUT"
grep -q 'socket: scan failed (exit 42)' <<<"$CASE_DEGRADED" \
  || fail_case "generic Socket failure lacks .degraded reason: $CASE_DEGRADED"
grep -q '"supply_chain":"degraded"' <<<"$CASE_EVENT" \
  || fail_case "generic Socket failure event is not degraded: $CASE_EVENT"

# 1s survives here on purpose: this fake exits IMMEDIATELY, so there is no arm to
# reach and no spawn latency to dominate.
launch_case socket_137 "$SCAN" 1 exit137 gnu
[ "$CASE_RC" -eq 0 ] || fail_case "optional Socket exit 137 changed gate rc: $CASE_RC"
grep -q 'Socket scan timed out after 1s' <<<"$CASE_OUT" \
  || fail_case "Socket exit 137 is not classified as timeout: $CASE_OUT"
grep -q '"supply_chain":"degraded"' <<<"$CASE_EVENT" \
  || fail_case "Socket exit 137 event is not degraded: $CASE_EVENT"
ok "Socket success (no alert list: DEGRADED named), alert list, generic failure, and 137 states are distinct"

echo "=== 5. TIMEOUT CONFIG ACCEPTS ONLY 1..900"
for value in 1 900; do
  launch_case "bound_$value" "$SCAN" "$value" success gnu
  grep -q "timeout ${value}s" <<<"$CASE_OUT" \
    || fail_case "valid timeout $value was not used: $CASE_OUT"
  grep -q 'invalid SCA_SOCKET_TIMEOUT_SECONDS' <<<"$CASE_OUT" \
    && fail_case "valid timeout $value was rejected: $CASE_OUT"
done
for value in 0 901 invalid; do
  launch_case "invalid_$value" "$SCAN" "$value" success gnu
  grep -q 'invalid SCA_SOCKET_TIMEOUT_SECONDS value; using 60 seconds' <<<"$CASE_OUT" \
    || fail_case "invalid timeout $value was not announced: $CASE_OUT"
  grep -q 'timeout 60s' <<<"$CASE_OUT" \
    || fail_case "invalid timeout $value did not fall back to 60: $CASE_OUT"
done
ok "timeout bounds 1 and 900 are accepted; invalid values fall back to 60"

echo "PASS: sca-socket-timeout"
