#!/usr/bin/env bash
# Suite for the REPORTS LOCK of sca-scan.sh (T-01M4Z39613YVM24WCTWB56N2TH; plan
# T-01M4Z33N54TX0Q7VHBZATFNR4X rév. 4, step 5, with the reserves C1-C5 of its
# plan-critic 4/8).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. Every arm runs a PRIVATE copy
# of the real dispatcher against disposable fixture roots outside any repo. ZERO
# network: pip-audit and trivy are STUBS first on the PATH (no package.json
# anywhere, so npm and socket never run); `ps`, `rm` and `mkdir` are stubbed only
# in the arms that say so.
#
# COST, said up front: about 80 s. (d2), (d2b) and (d2c) wait out the FIXED 40 s
# grace of an owner-less lock (no public knob shortens it, on purpose); they are
# launched FIRST and judged LAST, so every other arm runs inside their ~66 s. Every
# wait of this suite is BOUNDED (`timeout`, or a watchdog that SIGKILLs a
# background run).
#
# THE DEFECT (measured before the lock, plan § Couverture T3): run A holding a HIGH
# and run B clean, on the same root -> A rc 0 GO, two audit rows GO. B purged and
# rewrote the reports under A.
#
# THE ARMS
#   (a)   the race replayed: A NO-GO rc 1, B waits for it, then GO; witness: A
#         alone is NO-GO
#   (b)   live owner, WAIT=1 -> rc 1, the exact lock-busy lines, the held line and
#         NOT the removal remedy, the holder's files untouched (cmp), the audit row
#         NO-GO lock-busy; under LC_ALL=C no "unbound variable", no witness file
#   (b2)  `ps` mute: start written empty (v1), or written then `ps` mute at the
#         judgement (v2) -> lock-busy, "alive but not describable", never taken;
#         v1 also: the remedy of an ALIVE undescribable owner (check its pid
#         first), never the orphan-lock one (closing review T4)
#   (b3)  owner pid 1 at its real start -> lock-busy (EPERM reads ALIVE)
#   (c)   dead pid -> taken over, GO
#   (c2)  live pid at a FALSE start -> taken over (the pid was recycled)
#   (c3)  another host, a dead pid there -> lock-busy, never taken
#   (c4)  `ps` answering `Thu Jan  1 00:00:00 1970   ` (padded) to holder and
#         waiter -> lock-busy: the owner is re-read with `IFS=`
#   (c5)  deterministic interleaving: thief 1 suspended on its first judgement,
#         thief 2 steals and holds, thief 1 resumes -> lock-busy, owner = thief 2,
#         ONE "taken over" in all
#   (c6)  holder under TZ=Asia/Tokyo, waiter under TZ=America/New_York -> busy,
#         the holder's owner intact, the holder still alive
#   (c7)  Linux only: owner line 3 = `ticks:` + field 22 of /proc/<pid>/stat
#   (c8)  Linux, `unshare` permitted: this suite's LIVE owner, a waiter in ANOTHER
#         pid namespace under the same hostname -> lock-busy rc 1, never taken, the
#         owner intact (closing review T6: with the bare hostname, read dead, stolen)
#   (c9)  Linux only: owner line 2 = `uname -n`, a space, `readlink /proc/self/ns/pid`
#         — the expectation built by the suite, never by lock_host
#   (d1)  owner-less lock, WAIT=8 -> lock-busy, the removal remedy, no stderr
#   (d2)  owner-less lock aged to 2020, replaced at t0+15 by a NEW owner-less lock
#         carrying a sentinel -> sentinel present at t0+47, taken over in
#         [t0+52, t0+66] (the plan's [55, 65], widened by the 1 s granularity of
#         SECONDS on both clocks)
#   (d2b) the same, the replacement dated in the PAST (2025-01-01, older than now,
#         newer than the original) -> same: `touch -r` resets the grace on it
#   (d2c) the same, the replacement dated BEFORE the original (2015-01-01 < 2020)
#         -> same: the grace restarts on a date that DIFFERS, older included
#         (`-nt` alone kept the old grace and stole the replacement at t0+40)
#   (d3)  owner `$(touch PWNED)` -> no PWNED anywhere, read unreadable
#   (d4)  owner truncated without its last newline -> lock-busy, not taken
#   (d5)  dead owner + an orphan `.lock.steal` -> lock-busy, the remedy names both
#   (d6)  dead owner, a `rm` that fails on the lock -> rc 1 before WAIT+5 s, NO
#         "taken over", lock kept, no mutex left, at most WAIT+2 attempts
#   (d7)  dead owner, `mkdir` refused on the lock for 3 s after the theft -> at
#         most 5 refusals, ONE "taken over"
#   (e)   --all-modules root + sub, WAIT=1 -> no lock-busy; both module runs see
#         the PARENT as the owner
#   (f)   lock and witness file gone after a nominal run, after TERM and HUP of the
#         holder, after a trivy run (its temp file gone too); under LC_ALL=C the
#         early exit "module dir not found" leaves no "unbound variable". The
#         audit rows PARSED (F2b, T-01M51YJ5GXM101STF0NM586RXN): the nominal run
#         ONE scan GO, no aborted; TERM and HUP ONE scan NO-GO `aborted`; a module
#         `mod"x` cut by TERM ONE row whose slug reads `mod?x` (sanitised, C13)
#   (f2)  TERM to a thief suspended INSIDE the mutex -> rc 143, mutex gone, NO
#         audit row (it never held the lock); `go` is posed AFTER the TERM (bash
#         3.2 defers the signal until the command substitution returns, reserve C4)
#   (f3)  the REAL cleanup() in a subshell leaves the lock; in its owner, removes it
#   (f4)  --all-modules cut by TERM: to the parent ALONE -> the lock still held 1 s
#         later (the trap waits for the module run), rc 143, the module's scan GO
#         row then ONE all-modules NO-GO `aborted` row, last; to the GROUP (bgs,
#         its own process group) -> rc 143, that one row only. Measured before
#         the trap: the parent released the lock while its module ran, and no row
#   (f5)  TERM to the group, then a SECOND TERM 0.7 s later while cleanup() sits in
#         its `$(date …)` (a `date` stub slowed 2 s) -> rc 143, lock gone, no
#         witness file, ONE scan NO-GO `aborted` row (cleanup opens on `trap ''
#         TERM HUP`; before it: lock and witness LEFT, no row — exec-critic t2.sh)
#   (g)   --all-modules without Python -> rc 0 DEGRADED, lock gone, no "unbound
#         variable" under LC_ALL=C
#   (h)   SCA_CHANGED_ONLY=1 and no SCA_LOCK_WAIT_SECONDS -> waits 30 s, not more
#   (h2)  the 10 hook records of the 5 host files: every budget >= 30 + 30 s;
#         .claude/settings.json NAMED for carrying no key
#   (i)   SCA_LOCK_WAIT_SECONDS=abc -> logged, the default (600) used
#   (i2)  live owner, SCA_LOCK_WAIT_SECONDS 09 / 010 -> logged invalid, the default
#         600 s waited (never the octal 8 s, never a run WITHOUT the lock: rc 124,
#         no gate line, the owner intact); 0 -> lock-busy `beyond 0s` rc 1; 3600 ->
#         valid, waited (the bound itself)
#   (i3)  the fail-closed NET, on a copy whose lock_wait_valid is forced true: 09
#         aborts `$(( ))` in lock_acquire, bash DISCARDS the call -> the scan form
#         AND --all-modules end NO-GO rc 1 `run cut short …`, audit `aborted`, the
#         line read by sca-watch's FC_RUN_RE, the owner intact, no "unbound
#         variable" under LC_ALL=C
#   (j)   a root without sca-reports/ -> lock taken, run normal
#   (k)   sca-reports/ not writable (chmod 555), no lock, WAIT=5 -> NO-GO rc 1 in <= 3 s,
#         the exact line, read by sca-watch's FC_RUN_RE, no wait (closing review T5;
#         measured before: the 600 s wait of a held lock); INERT under uid 0, a
#         named skip
#   (l)   E3: a GO summary.json dated 2000 + a live owner -> --all-modules rc 1
#         lock-busy, then the tracked audit_report.py -> badge NO-GO and the
#         no-verdict line (closing review T1; measured before: badge GO)
#
# PREMISES, measured on the host before any arm; each turns its arms into a
# NAMED, COUNTED skip rather than a false green:
#   START  the two-branch start form (the REAL lock_start, sourced below) on a
#          live `sleep`. Empty -> "start indescriptible (ps -o refusé)" (Git Bash,
#          MSYS: T-00000410) for (b) held line, (b2) v2, (c2), (c5), (c6), (f2);
#   DEAD   `kill -0` on a reaped pid says `No such process`; otherwise (c), (c3),
#          (d6), (d7) cannot tell a dead owner from a live one;
#   LINUX  (b2) v2, (c4), (c5), (f2) need a `ps` the /proc branch never calls ->
#          skipped there; (c7) runs there ONLY;
#   BASHPID (f3)'s subshell half needs it (bash >= 4).
#   NS     (c8): `unshare --user --map-root-user --pid --fork --mount-proc
#          --kill-child`, else the same without the user namespace (uid 0 with
#          CAP_SYS_ADMIN). Neither -> a named skip; GitHub's runners NOT measured.
#
# MUTANTS THAT MUST TURN THIS SUITE RED (plan names), each applied to a COPY of
# sca-scan.sh and run through SCA_SCAN_UNDER_TEST — see the replay note below.
#   MB7 acquisition no-op -> (a) · MB8 the run continues at the deadline -> (b)
#   cmp · MB9 exit 0 at the deadline -> (b) · MB10 theft removed -> (c) · MB11
#   start ignored -> (c2) · MB12 host ignored -> (c3) · MB13 unreadable owner kept
#   forever -> (d2) · MB14 owner evaluated -> (d3) · MB15 the child ignores
#   SCA_LOCK_OWNER -> (e) · MB16 the child releases -> (e) · MB17 release removed
#   -> (f) · MB18 a second `trap … EXIT` in the trivy block -> (f) trivy · MB19
#   CHANGED_ONLY default 120 -> (h) · MB20 validation removed -> (i) · MB21 lock
#   before the mkdir -p -> (j) · MB22 no re-judgement under the mutex -> (c5) ·
#   MB23 empty start read dead -> (b2) · MB24 grace 5 s -> (d1) · MB25 the rc of
#   `kill -0` alone -> (b3) · MB26 `read -r` without `IFS=` -> (c4) · MB27a the
#   `-nt` reset removed -> (d2) · MB27b reset and guard removed -> (d2) · MB28 the
#   redirections inverted -> (d1) stderr · MB29 liveness by `ps` -> (b2) · MB30
#   TZ=UTC0 removed -> (c6) · MB31 `continue` after a failed theft -> (d6) · MB32
#   "taken over" unconditional -> (d6) · MB33 the mutex rmdir removed from
#   cleanup -> (f2) · MB34 the Linux branch removed -> (c7), Linux only · MB35
#   `ref=` not initialised before the trap -> (f) early exit · MB36 the removal
#   remedy also under `held` -> (b) · MB37 the 1 s sleep removed -> (d6) · MB38
#   `took` sticky -> (d7) · MB38b `steal` and `took` sticky -> (d7) · MB39 the
#   BASHPID guard removed -> (f3) · MB40 `touch "$ref"` for `touch -r` -> (d2b)
#   · MB41 lock_wait_valid back to `^[0-9]+$` -> (i2) · MB41b that AND both nets
#   removed -> (i2) GO rc 0, (i3) · MB42 lock_changed back to `-nt` alone -> (d2c)
#   · MB42a the reset alone back to `-nt` -> (d2c) · MB43 the scan net removed ->
#   (i3) · MB43b the --all-modules net removed -> (i3) · MB43c `lock_ok=1` at the
#   claim removed -> (a) · MB43d `lock_ok=1` at re-entry removed -> (e) · MB44
#   the undescribed remedy removed -> (b2) · MB45 the not-writable test removed ->
#   (k) · MB46 the Linux branch of lock_host removed -> (c8), (c9) · MB47
#   audit_report.py's no-verdict override short-circuited -> (l), replayed on a
#   COPY of this suite whose HERE carries the mutated audit_report.py · MB48 the
#   signal test of cleanup's aborted row removed -> (f) nominal · MB49 that printf
#   removed -> (f) TERM · MB50 sanitize_display removed from it -> (f) mod"x ·
#   MB51 its LOCK_MODE test made `if false` -> (f4) · MB52 the `trap '' TERM HUP`
#   at the head of cleanup removed -> (f5): 3 KO under 5.3.15 AND 3.2.57 (lock
#   LEFT, witness left, no row), measured on the tracked file at f33cb053
#   REPLAYED 2026-10-16 (F2b, T-01M51YJ5GXM101STF0NM586RXN), same method, arms
#   f f2 f3 f4, KO count identical under 5.3.15 AND 3.2.57: MB48 1 ((f) nominal:
#   a second, aborted row) · MB49 3 ((f) TERM, HUP, mod"x: no row) · MB50 1
#   (mod"x: UNPARSABLE) · MB51 2 ((f4) parent and group: a scan row, no module).
#   Before the trap (the tracked file at 0e99781e): 6 KO — (f) TERM, HUP, mod"x,
#   (f4) parent lock released early and no aborted row, (f4) group no row.
#   Control: 172/172 arms, bash 5 165 ok + 6 named skips, bash 3.2 164 ok + 7.
#   REPLAYED 2026-10-16 (closing-review pass), same method. macOS, no sandbox (the
#   setuid ps): control bash 5.3.15 150 ok + 6 named skips, bash 3.2.57 148 ok + 7,
#   156/156 arms, ~69 s; MB44 2/2 · MB45 3/3 (it waited the 5 s) · MB47 2/2 —
#   KO count b5/b32. LINUX, local container (python:3.12-slim, bash 5.2.37, uid 0,
#   `--pull never --network none`, plus seccomp and apparmor unconfined and
#   CAP_SYS_ADMIN for `unshare`; no ps in it): control 136 ok / 0 KO / 20 named
#   skips, 156/156, (c7) (c8) (c9) green, (k) INERT (uid 0); MB46 5 KO — (c9) and
#   the four of (c8): the live owner "taken over".
#   REPLAYED 2026-10-16 at 07d0de3d (exec-critic NO_GO, C15: no raw output had
#   been kept), the same container and flags, RAW logs + exact commands kept
#   outside the repo: ~/.local/state/cadre/reprises/op-agentic-builder-kit-
#   2026-10-15/preuves/sca-linux/ (controle-*, MB46-*, MB34-*, k-uid1000-*,
#   commande.txt). Control 136 ok / 0 KO / 20 named skips, 156/156, (c7) (c8)x4
#   (c9) green; MB46 5 KO as above; MB34 1 KO — (c7), but ONLY since this commit:
#   with no ps, MB34 empties the start, START_OK=0, and the arm used to SKIP
#   "(c7): Linux only" (0 KO, measured at 00ddbfff); on Linux an empty start is
#   now a KO. (k) under --user 1000:1000 (`k c6`): 11 ok / 0 KO.
#   REPLAYED 2026-10-16 (lot B, correction pass), same method, under 5.3.15 AND
#   3.2.57, KO count identical under both: MB41 3 · MB41b 9 · MB42 2 ((d2c) only:
#   the sentinel stolen before t0+47) · MB42a 2 (never taken: the guard refuses)
#   · MB43 3 (rc 0 GO) · MB43b 3 (rc 2 `module dir not found: --all-modules`, the
#   pre-net outcome) · MB43c 7 · MB43d 2. INERT, and why: MB42b (the guard before
#   the theft alone back to `-nt`) — the reset at (3) has already copied the
#   replacement's date onto the witness; the guard bites only on a lock changed
#   BETWEEN (3) and the `rm`, a race no arm provokes. Control: 141/141 arms,
#   bash 5 140 ok + 1 named skip, bash 3.2 139 ok + 2, ~68 s.
#   REPLAYED 2026-10-16, each mutant an exact-once replacement on a COPY, checked
#   by `cmp`, parsed under both bashes, run with SCA_LOCK_TEST_ARMS on its arm,
#   under bash 5.3.15 AND 3.2.57 (`bash` on PATH = /bin/bash), macOS. Control:
#   bash 5 118 ok + 1 named skip (c7), bash 3.2 117 ok + 2 ((c7), (f3) subshell),
#   both 119/119 arms, ~61 s. RED under BOTH, KO count b5/b32: MB7 4/4 · MB8 1/2
#   (the loop spins to the watchdog, rc 124) · MB8b — lock_acquire RETURNS at the
#   deadline, the run goes on — 5/5, the holder's 3 files touched (cmp) · MB9 1/1
#   · MB10 4/4 · MB11 2/2 · MB12 3/3 · MB13 4/4 · MB14 1/1 · MB15 4/4 · MB16 (the
#   child adopts the lock: lock_mine=1 and MY_PID=owner) 1/1 · MB17 4/4 · MB18
#   4/4 · MB19 1/1 · MB20 2/2 · MB21 3/3 · MB22 3/3 (two thieves) · MB23 3/3 ·
#   MB24 4/4 · MB25 2/2 · MB26 3/3 · MB27a 4/4 (never taken) · MB27b 4/4 (the
#   sentinel stolen before t0+47) · MB28 1/1 · MB29 6/6 · MB30 2/2 · MB31 3/4
#   (rc 124, 435/585 failed removals) · MB32 1/1 · MB33 1/1 · MB35 1/1 · MB36 1/1
#   · MB37 1/1 (58/72 removals) · MB38 1/1 (244/392 refusals) · MB38b 2/2 · MB40
#   2/2 ((d2b) only, as designed). INERT, and why: MB16a (lock_mine=1 alone) and
#   MB16b (the owner re-read dropped from cleanup alone) — two INDEPENDENT guards
#   keep a child from releasing, each single-point variant is covered by the
#   other (MB16c, both removed, 1/1 RED); MB34 on macOS (no /proc branch taken);
#   MB39 under 3.2 (no BASHPID, the named skip). LINUX, local container
#   (postgres:16.15 aarch64, bash 5.2.37, procps-ng 4.0.4, uid 0, `--pull never
#   --network none`, no python3 in it): the full suite 92 ok / 11 KO / 15 named
#   skips, 119/119 arms — every KO a python3-absent consequence ((a) GO lines and
#   audit parse, (b) audit parse, (e) discovery, (h2), (j) the DEGRADED last
#   line); (c), (c2), (c6), (c7), (d2), (d2b) (t0+56), (d6), (d7), (f3) green;
#   (b3) noted INERT (kill -0 1 rc 0 as root); MB34 RED there, (c7) 1 KO.
#
# KNOBS, read by THIS suite only: SCA_SCAN_UNDER_TEST (a mutated copy replaces the
# tracked dispatcher, announced on its own line) and SCA_LOCK_TEST_ARMS (a space-
# separated list of arm names; every other arm is a named SKIP and the count arm
# is not judged).
#
# FORM (bash 3.2 floor): no heredoc, no tree walk (test_repo_walk_census.py),
# stubs and BASH_ENV-like files written with printf, a `case` never on one line.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

TMP="$(mktemp -d)"
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
BG=''
bench_exit() {
  # L-00000146: this suite launches background runs and signals them. Only the
  # shell that installed the trap may kill them and destroy $TMP.
  [ "${BASHPID:-$$}" = "$BENCH_OWNER" ] || return 0
  local p
  for p in $BG; do kill -9 "$p" 2>/dev/null; done
  rm -rf "$TMP"
}
BENCH_OWNER="${BASHPID:-$$}"
trap bench_exit EXIT

# Hermetic: an inherited knob would change what every arm measures.
unset SCA_GATE_LEVEL SCA_CHANGED_ONLY SCA_ROOT_ONLY AGENTS_HOOK_HOST BASH_ENV
unset SCA_LOCK_WAIT_SECONDS SCA_LOCK_OWNER

passed=0
failed=0
skipped_arms=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }
skip() { echo "  SKIP $1"; skipped_arms=$((skipped_arms + $2)); }

command -v timeout >/dev/null 2>&1 || {
  echo "SKIP sca-scan-lock: GNU timeout absent — every arm of this suite is a bounded wait, none runs"
  exit 0
}

ONLY="${SCA_LOCK_TEST_ARMS:-}"
if [ -n "$ONLY" ]; then
  echo "ARM FILTER — only: $ONLY (every other arm is a named SKIP; the count arm is not judged)"
fi
want() {  # ARM: 0 when ARM runs
  [ -n "$ONLY" ] || return 0
  case " $ONLY " in
    *" $1 "*) return 0 ;;
  esac
  skip "($1): hors du filtre SCA_LOCK_TEST_ARMS" 0
  return 1
}

# MUTATION REPLAY: SCA_SCAN_UNDER_TEST names the dispatcher copied into the kit.
SCAN_SRC="${SCA_SCAN_UNDER_TEST:-$HERE/sca-scan.sh}"
if [ -n "${SCA_SCAN_UNDER_TEST:-}" ]; then
  echo "MUTATION REPLAY — under test: $SCAN_SRC (NOT the tracked sca-scan.sh)"
fi
KIT="$TMP/kit"
mkdir -p "$KIT"
cp "$SCAN_SRC" "$KIT/sca-scan.sh" || { echo "FATAL: cannot copy $SCAN_SRC into the private kit"; exit 2; }
for f in waiver_filter.py protected_module.py module_discovery.py py_lock_pins.py; do
  cp "$HERE/$f" "$KIT/$f" || { echo "FATAL: cannot copy $f into the private kit"; exit 2; }
done
SCAN="$KIT/sca-scan.sh"

# THE REAL lock_start and cleanup, cut out of the dispatcher under test and
# SOURCED from a file (never evaluated): an owner "at its true start" is computed
# by the very form the dispatcher compares with, and (f3) exercises the real body.
LOCK_OS="$(uname -s 2>/dev/null)"
LOCK_RP=')'
sed -n '/^lock_start()/,/^}/p' "$SCAN" > "$TMP/lock_start.fn"
sed -n '/^lock_host()/,/^}/p' "$SCAN" > "$TMP/lock_host.fn"
sed -n '/^cleanup()/,/^}/p' "$SCAN" > "$TMP/cleanup.fn"
grep -q '^lock_start()' "$TMP/lock_start.fn" && grep -q '^lock_host()' "$TMP/lock_host.fn" \
  && grep -q '^cleanup()' "$TMP/cleanup.fn" \
  || { echo "FATAL: lock_start(), lock_host() or cleanup() not found in $SCAN"; exit 2; }
. "$TMP/lock_start.fn"
. "$TMP/lock_host.fn"

# The host line a holder of THIS shell's pid namespace writes, by the dispatcher's
# own form: on Linux `uname -n` plus the pid namespace (closing review T6).
HOST="$(lock_host)"
REAL_PS="$(command -v ps)"
REAL_RM="$(command -v rm)"
REAL_MKDIR="$(command -v mkdir)"
REAL_DATE="$(command -v date)"

# ---- stubs ------------------------------------------------------------------
CLEAN_JSON='{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[]}],"fixes":[]}'
HIGH_JSON='{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"aliases":["CVE-2023-30861"],"severity":"HIGH","description":"boxed"}]}],"fixes":[]}'
# mk_pip DIR RC JSON: a pip-audit stub (and a trivy that answers nothing). Held
# when LOCKB_GO is set (it poses LOCKB_PAUSED, then waits for LOCKB_GO, 30 s at
# most); LOCKB_OWNERLOG appends line 1 of the lock owner it sees.
mk_pip() {
  mkdir -p "$1"
  printf '%s\n' '#!/usr/bin/env bash' \
    'if [ -n "${LOCKB_OWNERLOG:-}" ]; then' \
    '  p=""' \
    '  { IFS= read -r p; } 2>/dev/null < "$LOCKB_LOCKDIR/owner"' \
    '  printf "%s\n" "${p:-none}" >> "$LOCKB_OWNERLOG"' \
    'fi' \
    'if [ -n "${LOCKB_PAUSED:-}" ]; then' \
    '  : > "$LOCKB_PAUSED"' \
    'fi' \
    'i=0' \
    'while [ -n "${LOCKB_GO:-}" ] && [ ! -e "$LOCKB_GO" ] && [ "$i" -lt 300 ]; do' \
    '  sleep 0.1' \
    '  i=$((i + 1))' \
    'done' \
    "printf '%s\\n' '$3'" \
    "exit $2" > "$1/pip-audit"
  printf '%s\n' '#!/bin/sh' 'exit 0' > "$1/trivy"
  chmod +x "$1/pip-audit" "$1/trivy"
}
CLEAN="$TMP/bin-clean"
HIGH="$TMP/bin-high"
mk_pip "$CLEAN" 0 "$CLEAN_JSON"
mk_pip "$HIGH" 1 "$HIGH_JSON"
# A trivy that finds an IaC file: its report is written where --output says.
TRIVYOK="$TMP/bin-trivyok"
mkdir -p "$TRIVYOK"
printf '%s\n' '#!/usr/bin/env bash' 'out=""' \
  'while [ "$#" -gt 0 ]; do' \
  '  if [ "$1" = "--output" ]; then out="$2"; fi' \
  '  shift' \
  'done' \
  'if [ -n "$out" ]; then' \
  '  printf "%s\n" '"'"'{"SchemaVersion":2,"Results":[]}'"'"' > "$out"' \
  'fi' \
  'exit 0' > "$TRIVYOK/trivy"
chmod +x "$TRIVYOK/trivy"
# Python ABSENT: both names the dispatcher probes answer nothing and fail.
NOPY="$TMP/bin-nopy"
mkdir -p "$NOPY"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$NOPY/python3"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$NOPY/python"
chmod +x "$NOPY/python3" "$NOPY/python"
# `ps` mute: the PS_MUTE form of night_keepawake.test.sh — exit 1, nothing said.
PSMUTE="$TMP/bin-psmute"
mkdir -p "$PSMUTE"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$PSMUTE/ps"
chmod +x "$PSMUTE/ps"
# `ps` answering the epoch, padded the way macOS pads lstart.
EPOCH_ST='Thu Jan  1 00:00:00 1970   '
PSEPOCH="$TMP/bin-psepoch"
mkdir -p "$PSEPOCH"
printf '%s\n' '#!/bin/sh' "printf '%s\\n' '$EPOCH_ST'" 'exit 0' > "$PSEPOCH/ps"
chmod +x "$PSEPOCH/ps"
# `ps` that suspends on its LOCKB_PAUSE_AT-th call `ps -p LOCKB_JUDGED`, in the run
# that carries LOCKB_JUDGED only, until LOCKB_GO (30 s at most); real ps otherwise.
PSPAUSE="$TMP/bin-pspause"
mkdir -p "$PSPAUSE"
printf '%s\n' '#!/usr/bin/env bash' \
  'if [ "${1:-}" = "-p" ] && [ "${2:-}" = "${LOCKB_JUDGED:-none}" ]; then' \
  '  n=0' \
  '  [ -f "$LOCKB_CTR" ] && n="$(cat "$LOCKB_CTR")"' \
  '  n=$((n + 1))' \
  '  printf "%s\n" "$n" > "$LOCKB_CTR"' \
  '  if [ "$n" = "${LOCKB_PAUSE_AT:-1}" ]; then' \
  '    : > "$LOCKB_PAUSED"' \
  '    i=0' \
  '    while [ ! -e "$LOCKB_GO" ] && [ "$i" -lt 300 ]; do' \
  '      sleep 0.1' \
  '      i=$((i + 1))' \
  '    done' \
  '  fi' \
  'fi' \
  "exec \"$REAL_PS\" \"\$@\"" > "$PSPAUSE/ps"
chmod +x "$PSPAUSE/ps"
# (d6) a removal that FAILS on `rm -r <…>/.lock`, counted; the real rm otherwise.
RMFAIL="$TMP/bin-rmfail"
mkdir -p "$RMFAIL"
printf '%s\n' '#!/usr/bin/env bash' \
  'case "${1:-}:${2:-}" in' \
  '  -r:*/.lock)' \
  '    printf "x\n" >> "$LOCKB_RMCTR"' \
  '    exit 1' \
  '    ;;' \
  'esac' \
  "exec \"$REAL_RM\" \"\$@\"" > "$RMFAIL/rm"
chmod +x "$RMFAIL/rm"
# (d7) the real removal of the lock poses LOCKB_FLAG; `mkdir <…>/.lock` is then
# REFUSED (counted) until LOCKB_REL exists.
D7BIN="$TMP/bin-d7"
mkdir -p "$D7BIN"
printf '%s\n' '#!/usr/bin/env bash' \
  'case "${1:-}:${2:-}" in' \
  '  -r:*/.lock)' \
  "    \"$REAL_RM\" \"\$@\"" \
  '    rc=$?' \
  '    [ "$rc" = 0 ] && : > "$LOCKB_FLAG"' \
  '    exit "$rc"' \
  '    ;;' \
  'esac' \
  "exec \"$REAL_RM\" \"\$@\"" > "$D7BIN/rm"
printf '%s\n' '#!/usr/bin/env bash' \
  'case "${1:-}" in' \
  '  */.lock)' \
  '    if [ -e "$LOCKB_FLAG" ] && [ ! -e "$LOCKB_REL" ]; then' \
  '      printf "x\n" >> "$LOCKB_MKCTR"' \
  '      exit 1' \
  '    fi' \
  '    ;;' \
  'esac' \
  "exec \"$REAL_MKDIR\" \"\$@\"" > "$D7BIN/mkdir"
chmod +x "$D7BIN/rm" "$D7BIN/mkdir"

# ---- helpers ----------------------------------------------------------------
# A fixture root OUTSIDE any repo (sca-scan.sh falls back to `pwd` for ROOT).
make_root() {
  local r="$TMP/root-$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf 'flask==2.0.0\n' > "$r/requirements.txt"
  echo "$r"
}
rep() { echo "$1/.agents/state/local/sca-reports"; }
# put_owner ROOT PID HOST START: a lock and its owner, in ONE printf, as a holder writes it.
put_owner() {
  local l
  l="$(rep "$1")/.lock"
  mkdir -p "$l"
  printf '%s\n%s\n%s\n' "$2" "$3" "$4" > "$l/owner"
}
# fg ROOT OUT ERR SECS ARG...: `timeout SECS env ARG...` run from ROOT; rc in FRC.
fg() {
  local r="$1" o="$2" e="$3" t="$4"
  shift 4
  ( cd "$r" && exec timeout "$t" env "$@" ) > "$o" 2> "$e"
  FRC=$?
}
# bg ROOT OUT ARG...: `env ARG...` from ROOT in the background; its pid (the
# dispatcher's own, through two execs) in BPID.
bg() {
  local r="$1" o="$2"
  shift 2
  ( cd "$r" && exec env "$@" ) > "$o" 2>&1 &
  BPID=$!
  BG="$BG $BPID"
}
# bgs ROOT OUT ARG...: as bg, in a process group of its OWN (python3 os.setsid,
# then exec): the group id is BPID, so `kill -- -BPID` reaches the dispatcher,
# its module runs, tee and the stubs — never this suite (measured: pgid = pid,
# rc 143 on a group TERM, under 3.2.57 and 5.3.15).
bgs() {
  local r="$1" o="$2"
  shift 2
  ( cd "$r" && exec python3 -c 'import os, sys
os.setsid()
os.execvp(sys.argv[1], sys.argv[1:])' env "$@" ) > "$o" 2>&1 &
  BPID=$!
  BG="$BG $BPID"
}
# reap PID SECS: wait for our child PID; SIGKILL it if it outlives SECS. rc in RRC.
NREAP=0
reap() {
  local wd flag
  NREAP=$((NREAP + 1))
  flag="$TMP/reap.$NREAP"
  ( i=0
    n=$(( $2 * 5 ))
    while [ "$i" -lt "$n" ] && [ ! -e "$flag" ]; do
      sleep 0.2
      i=$((i + 1))
    done
    [ -e "$flag" ] || kill -9 "$1" 2>/dev/null ) > /dev/null 2>&1 < /dev/null &
  wd=$!
  wait "$1" 2>/dev/null
  RRC=$?
  : > "$flag"
  wait "$wd" 2>/dev/null
  return 0
}
wait_file() {  # FILE SECS: 0 once FILE exists
  local i=0 n=$(( $2 * 10 ))
  while [ ! -e "$1" ]; do
    [ "$i" -lt "$n" ] || return 1
    sleep 0.1
    i=$((i + 1))
  done
  return 0
}
wait_text() {  # FILE SECS TEXT...: 0 once FILE carries one of the TEXTs
  local f="$1" i=0 n=$(( $2 * 10 )) t
  shift 2
  while :; do
    for t in "$@"; do
      grep -Fq -- "$t" "$f" 2>/dev/null && return 0
    done
    [ "$i" -lt "$n" ] || return 1
    sleep 0.1
    i=$((i + 1))
  done
}
# leftovers DIR: the witness or trivy temp files the dispatcher left in DIR.
leftovers() {
  local f out=''
  for f in "$1"/scalockref.* "$1"/.trivy-scan.*; do
    [ -e "$f" ] && out="$out ${f##*/}"
  done
  printf '%s' "$out"
}
# The theft line only: "alive but not describable — not taken over" ALSO ends
# with "taken over", so the mark is the theft line's own head.
TAKEN_MARK='SCA: stale reports lock (pid '
taken_count() { grep -cF -- "$TAKEN_MARK" "$1" 2>/dev/null; }
audit_last() {  # ROOT: `mode=<m> verdict=<v> reason=<r|->` of the LAST audit row, PARSED
  python3 -c 'import json, sys
rows = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
try:
    r = json.loads(rows[-1])
except Exception:
    print("UNPARSABLE")
    sys.exit(0)
print("mode=%s verdict=%s reason=%s" % (r.get("mode"), r.get("verdict"), r.get("reason", "-")))' \
    "$(rep "$1")/audit-log.jsonl" 2>/dev/null || echo "UNREADABLE"
}
audit_verdicts() {  # ROOT: every row's verdict, in order
  python3 -c 'import json, sys
rows = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
print(" ".join(json.loads(l).get("verdict", "?") for l in rows))' \
    "$(rep "$1")/audit-log.jsonl" 2>/dev/null || echo "UNREADABLE"
}
# audit_rows ROOT: EVERY audit row, PARSED, one output line each, joined by `|`:
# `mode=<m> verdict=<v> reason=<r|-> module=<m|->`, `UNPARSABLE` for a row that
# is not JSON; nothing at all when the log does not exist. "ONE row" is asserted
# on this whole string — the rows' structure, never a line count (L-00000394).
audit_rows() {
  python3 -c 'import json, os, sys
p = sys.argv[1]
out = []
if os.path.exists(p):
    for l in open(p, encoding="utf-8").read().splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            out.append("UNPARSABLE")
            continue
        out.append("mode=%s verdict=%s reason=%s module=%s" % (r.get("mode"), r.get("verdict"), r.get("reason", "-"), r.get("module", "-")))
print("|".join(out))' \
    "$(rep "$1")/audit-log.jsonl" 2>/dev/null || echo "UNREADABLE"
}
# The exact lines, as `log` prints them.
wait_line() { printf '  SCA: reports lock held by pid %s — waiting up to %ss' "$1" "$2"; }
busy_line() { printf '  SCA GATE (effective, waivers applied): NO-GO — reports lock held by pid %s beyond %ss, no verdict obtained (fail-closed)' "$1" "$2"; }
held_line() { printf '  SCA: reports lock held by live pid %s — re-run when it ends; do not remove the lock' "$1"; }
taken_line() { printf '  SCA: stale reports lock (pid %s) taken over' "$1"; }
undesc_line() { printf '  SCA: reports lock owner pid %s alive but not describable — not taken over' "$1"; }
undesc_rm_line() { printf '  SCA: reports lock owner pid %s is ALIVE (start not describable) — remove the lock only if pid %s is not a sca-scan.sh: rm -r .agents/state/local/sca-reports/.lock' "$1" "$1"; }
NOWRITE_LINE='  SCA GATE (effective, waivers applied): NO-GO — reports directory not writable, no verdict obtained (fail-closed)'
RM_LINE='  SCA: if no sca-scan.sh is running, remove the orphan lock: rm -r .agents/state/local/sca-reports/.lock .agents/state/local/sca-reports/.lock.steal'
GATE_GO='SCA GATE (effective, waivers applied): GO'
GATE_NOGO='SCA GATE (effective, waivers applied): NO-GO'
has() { grep -Fxq -- "$2" "$1" 2>/dev/null; }   # FILE LINE: the exact line is there

# ---- premises ---------------------------------------------------------------
echo "=== premises"
sleep 600 &
LIVE=$!
BG="$BG $LIVE"
LIVE_ST="$(lock_start "$LIVE")"
START_OK=0
[ -n "$LIVE_ST" ] && START_OK=1
IS_LINUX=0
[ "$LOCK_OS" = "Linux" ] && IS_LINUX=1
dead_pid() { ( exit 0 ) & DEADP=$!; wait "$DEADP"; }
dead_pid
DEAD_MSG="$(export LC_ALL=C; kill -0 "$DEADP" 2>&1)"
DEAD_OK=0
case "$DEAD_MSG" in
  *'No such process'*) DEAD_OK=1 ;;
esac
HAS_BASHPID=0
[ -n "${BASHPID:-}" ] && HAS_BASHPID=1
if [ "$IS_LINUX" = 1 ]; then FAKE_ST='ticks:1'; else FAKE_ST='Thu Jan  1 00:00:00 1970'; fi
# NS (c8): a waiter in ANOTHER pid namespace — the unprivileged form first (a user
# namespace), then the plain one (uid 0 with CAP_SYS_ADMIN: MEASURED in a local
# container, where the user form fails to mount /proc and the plain one passes).
NS_OK=0
NS_USER=0
NS_MSG='not Linux'
if [ "$IS_LINUX" = 1 ]; then
  if ! command -v unshare >/dev/null 2>&1; then
    NS_MSG='unshare absent'
  elif NS_MSG="$(unshare --user --map-root-user --pid --fork --mount-proc --kill-child true 2>&1)"; then
    NS_OK=1
    NS_USER=1
  elif NS_MSG="$NS_MSG | plain: $(unshare --pid --fork --mount-proc --kill-child true 2>&1)"; then
    NS_OK=1
  fi
fi
echo "  premises: LOCK_OS=$LOCK_OS START_OK=$START_OK [$LIVE_ST] DEAD_OK=$DEAD_OK [$DEAD_MSG] BASHPID=$HAS_BASHPID NS_OK=$NS_OK NS_USER=$NS_USER HOST=[$HOST] bash=$BASH_VERSION body=$(bash -c 'echo $BASH_VERSION')"
SKIP_START="start indescriptible (ps -o refusé)"

# ---- (d2)/(d2b) launched FIRST, judged LAST ---------------------------------
# d2_drive NAME ROOT PASTDATE: an owner-less lock aged to 2020; the waiter's
# `waiting up to` line is t0 (never a fixed sleep); at t0+15 the lock is REPLACED
# — atomically, by a rename within the same parent, so the waiter cannot slip in
# between — by a new owner-less one carrying a sentinel, dated PASTDATE if given;
# the sentinel is looked at at t0+47; the takeover time is noted. Results in
# $TMP/NAME.res as `<present|absent> <seconds|none> <rc>`.
d2_drive() {
  local n="$1" r="$2" past="$3" l nl t0 s47 tk pid rc
  l="$(rep "$r")/.lock"
  nl="$(rep "$r")/.lock.next"
  mkdir -p "$l"
  touch -t 202001010000 "$l"
  ( cd "$r" && exec env PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=70 timeout 90 bash "$SCAN" ) > "$TMP/$n.out" 2>&1 &
  pid=$!
  if ! wait_text "$TMP/$n.out" 20 'waiting up to 70s'; then
    wait "$pid"
    printf 'no-t0 none %s\n' "$?" > "$TMP/$n.res"
    return 0
  fi
  t0=$SECONDS
  while [ $((SECONDS - t0)) -lt 14 ]; do sleep 0.2; done
  mkdir -p "$nl"
  : > "$nl/sentinel"
  [ -n "$past" ] && touch -t "$past" "$nl"
  while [ $((SECONDS - t0)) -lt 15 ]; do sleep 0.2; done
  python3 -c 'import os, sys; os.rename(sys.argv[1], sys.argv[2])' "$nl" "$l" 2>/dev/null \
    || { rmdir "$l" && mv "$nl" "$l"; }
  while [ $((SECONDS - t0)) -lt 47 ]; do sleep 0.2; done
  s47=absent
  [ -e "$l/sentinel" ] && s47=present
  tk=none
  while [ $((SECONDS - t0)) -lt 80 ]; do
    if grep -Fq "$TAKEN_MARK" "$TMP/$n.out" 2>/dev/null; then
      tk=$((SECONDS - t0))
      break
    fi
    sleep 0.2
  done
  wait "$pid"
  rc=$?
  printf '%s %s %s\n' "$s47" "$tk" "$rc" > "$TMP/$n.res"
}
D2_ON=0
if want d2; then
  D2_ON=1
  echo "=== (d2)/(d2b)/(d2c) launched now (~66 s), judged at the end"
  RD2="$(make_root swap)"
  RD2B="$(make_root swap-past)"
  RD2C="$(make_root swap-older)"
  ( d2_drive d2 "$RD2" '' ) &
  PD2=$!
  ( d2_drive d2b "$RD2B" 202501010000 ) &
  PD2B=$!
  # (d2c): dated BEFORE the 2020 original — `-nt` alone never saw it change.
  ( d2_drive d2c "$RD2C" 201501010000 ) &
  PD2C=$!
  BG="$BG $PD2 $PD2B $PD2C"
fi

# ---- (a) the race ------------------------------------------------------------
if want a; then
  echo "=== (a) the race replayed: A holds a HIGH, B (clean) waits — A NO-GO, then B GO"
  RA="$(make_root race)"
  bg "$RA" "$TMP/a.A.out" PATH="$HIGH:$PATH" LOCKB_PAUSED="$TMP/a.paused" LOCKB_GO="$TMP/a.go" SCA_LOCK_WAIT_SECONDS=30 bash "$SCAN"
  PA=$BPID
  wait_file "$TMP/a.paused" 20 \
    && ok "(a) witness: A holds the lock, inside its pip-audit" \
    || ko "(a) witness: A never reached its pip-audit — this arm measures nothing"
  bg "$RA" "$TMP/a.B.out" PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=30 bash "$SCAN"
  PB=$BPID
  # B waits — or, with no lock, finishes on its own: whichever comes first.
  wait_text "$TMP/a.B.out" 15 'waiting up to 30s' 'SCA GATE (effective' >/dev/null
  has "$TMP/a.B.out" "$(wait_line "$PA" 30)" \
    && ok "(a) B waits, naming A's pid" || ko "(a) B did not wait for A's lock: $(tr '\n' '|' < "$TMP/a.B.out")"
  : > "$TMP/a.go"
  reap "$PA" 40
  rc_a=$RRC
  reap "$PB" 40
  rc_b=$RRC
  [ "$rc_a" -eq 1 ] && ok "(a) A rc 1 — B did not rewrite A's reports under it" \
    || ko "(a) A expected rc 1, got $rc_a — the race: B rewrote A's reports"
  has "$TMP/a.A.out" "$GATE_NOGO" && ok "(a) A's final verdict NO-GO" || ko "(a) A's final verdict is not NO-GO"
  [ "$rc_b" -eq 0 ] && ok "(a) B rc 0 once A released" || ko "(a) B expected rc 0, got $rc_b"
  has "$TMP/a.B.out" "$GATE_GO" && ok "(a) B's final verdict GO" || ko "(a) B's final verdict is not GO"
  V_A="$(audit_verdicts "$RA")"
  [ "$V_A" = "NO-GO GO" ] && ok "(a) two audit rows: A's NO-GO, THEN B's GO" \
    || ko "(a) expected audit verdicts [NO-GO GO], got [$V_A]"
  RA2="$(make_root race-alone)"
  fg "$RA2" "$TMP/a2.out" "$TMP/a2.err" 30 PATH="$HIGH:$PATH" bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(a) witness: A alone is NO-GO rc 1" \
    || ko "(a) witness: A alone gave rc $FRC — the HIGH stub gates nothing"
fi

# ---- (b) a live, described owner ----------------------------------------------
if want b; then
  echo "=== (b) live owner, WAIT=1 => lock-busy NO-GO, nothing of the holder touched"
  RB="$(make_root held)"
  DB="$(rep "$RB")"
  put_owner "$RB" "$LIVE" "$HOST" "$LIVE_ST"
  printf '%s\n' 'HOLDER-PIVOT' > "$DB/effective-verdict.json"
  printf '%s\n' 'holder: its own reason' > "$DB/.degraded"
  printf '%s\n' 'HOLDER-REPORT' > "$DB/pip-audit.json"
  mkdir -p "$TMP/b.snap" "$TMP/td-b"
  cp "$DB/effective-verdict.json" "$DB/.degraded" "$DB/pip-audit.json" "$DB/.lock/owner" "$TMP/b.snap/"
  fg "$RB" "$TMP/b.out" "$TMP/b.err" 20 LC_ALL=C TMPDIR="$TMP/td-b" PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=1 bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(b) rc 1 — a lock held beyond the wait is a NO-GO" || ko "(b) expected rc 1, got $FRC"
  has "$TMP/b.out" "$(wait_line "$LIVE" 1)" && ok "(b) the waiting line names the holder and the wait" \
    || ko "(b) the waiting line is missing or different"
  has "$TMP/b.out" "$(busy_line "$LIVE" 1)" && ok "(b) the lock-busy NO-GO line, exact" \
    || ko "(b) the lock-busy NO-GO line is missing or different"
  if [ "$START_OK" = 1 ]; then
    has "$TMP/b.out" "$(held_line "$LIVE")" && ok "(b) the remedy: held by a live pid, do not remove" \
      || ko "(b) the held remedy is missing"
    has "$TMP/b.out" "$RM_LINE" && ko "(b) the REMOVAL remedy was printed for a live, described holder" \
      || ok "(b) no removal remedy for a live holder"
  else
    skip "(b) held line: $SKIP_START — the owner reads undescribed here, never held" 2
  fi
  n_b=0
  for f in effective-verdict.json .degraded pip-audit.json; do
    cmp -s "$TMP/b.snap/$f" "$DB/$f" || n_b=$((n_b + 1))
  done
  cmp -s "$TMP/b.snap/owner" "$DB/.lock/owner" || n_b=$((n_b + 1))
  [ "$n_b" -eq 0 ] && ok "(b) the holder's three files and its owner are byte-identical (cmp)" \
    || ko "(b) $n_b file(s) of the holder were touched by the waiter"
  A_B="$(audit_last "$RB")"
  [ "$A_B" = "mode=scan verdict=NO-GO reason=lock-busy" ] && ok "(b) the audit row: NO-GO, reason lock-busy" \
    || ko "(b) expected [mode=scan verdict=NO-GO reason=lock-busy], got [$A_B]"
  grep -Fq "$TAKEN_MARK" "$TMP/b.out" && ko "(b) a live holder was taken over" || ok "(b) never taken over"
  grep -Fq 'unbound variable' "$TMP/b.err" && ko "(b) the lock-busy exit says 'unbound variable' (LC_ALL=C)" \
    || ok "(b) no 'unbound variable' on the lock-busy exit (LC_ALL=C)"
  left_b="$(leftovers "$TMP/td-b")"
  [ -z "$left_b" ] && ok "(b) no witness file left in TMPDIR" || ko "(b) left in TMPDIR:$left_b"
fi

# ---- (b2) ps mute ---------------------------------------------------------------
if want b2; then
  echo "=== (b2) ps mute => alive but not describable, lock-busy, never taken"
  RB2="$(make_root psmute-v1)"
  put_owner "$RB2" "$LIVE" "$HOST" ""
  fg "$RB2" "$TMP/b2.out" "$TMP/b2.err" 20 PATH="$PSMUTE:$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(b2) v1 (start written empty): rc 1" || ko "(b2) v1: expected rc 1, got $FRC"
  has "$TMP/b2.out" "$(undesc_line "$LIVE")" && ok "(b2) v1: alive but not describable, said once" \
    || ko "(b2) v1: the 'alive but not describable' line is missing"
  grep -Fq "$TAKEN_MARK" "$TMP/b2.out" && ko "(b2) v1: an undescribable live owner was taken over" \
    || ok "(b2) v1: never taken over"
  has "$TMP/b2.out" "$(undesc_rm_line "$LIVE")" && ok "(b2) v1: the remedy of an ALIVE undescribable owner: check its pid first" \
    || ko "(b2) v1: the undescribed remedy is missing: $(tr '\n' '|' < "$TMP/b2.out")"
  has "$TMP/b2.out" "$RM_LINE" && ko "(b2) v1: the ORPHAN-lock remedy printed for an alive owner" \
    || ok "(b2) v1: no orphan-lock remedy for an alive owner"
  if [ "$IS_LINUX" = 1 ]; then
    skip "(b2) v2: Linux — the /proc branch never calls ps, a mute ps changes nothing" 3
  elif [ "$START_OK" = 0 ]; then
    skip "(b2) v2: $SKIP_START" 3
  else
    RB2V="$(make_root psmute-v2)"
    put_owner "$RB2V" "$LIVE" "$HOST" "$LIVE_ST"
    fg "$RB2V" "$TMP/b2v.out" "$TMP/b2v.err" 20 PATH="$PSMUTE:$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
    [ "$FRC" -eq 1 ] && ok "(b2) v2 (start written, ps mute at the judgement): rc 1" || ko "(b2) v2: expected rc 1, got $FRC"
    has "$TMP/b2v.out" "$(undesc_line "$LIVE")" && ok "(b2) v2: alive but not describable" \
      || ko "(b2) v2: the 'alive but not describable' line is missing"
    grep -Fq "$TAKEN_MARK" "$TMP/b2v.out" && ko "(b2) v2: taken over" || ok "(b2) v2: never taken over"
  fi
fi

# ---- (b3) pid 1 -----------------------------------------------------------------
if want b3; then
  echo "=== (b3) owner pid 1 at its real start => lock-busy (EPERM reads alive)"
  M_1="$(export LC_ALL=C; kill -0 1 2>&1)"
  r_1=$?
  case "$M_1" in
    *'No such process'*)
      skip "(b3): kill -0 1 says 'No such process' on this host" 2 ;;
    *)
      [ "$r_1" -eq 0 ] && echo "  note: (b3) kill -0 1 answers rc 0 here (root or a container): EPERM is NOT exercised, MB25 is INERT on this host"
      RB3="$(make_root pid1)"
      put_owner "$RB3" 1 "$HOST" "$(lock_start 1)"
      fg "$RB3" "$TMP/b3.out" "$TMP/b3.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
      [ "$FRC" -eq 1 ] && ok "(b3) rc 1 — pid 1 ($M_1) reads alive" || ko "(b3) expected rc 1, got $FRC"
      grep -Fq "$TAKEN_MARK" "$TMP/b3.out" && ko "(b3) the lock of pid 1 was taken over" || ok "(b3) never taken over"
      ;;
  esac
fi

# ---- (c)-(c4) dead, recycled, foreign, padded ------------------------------------
if want c; then
  echo "=== (c) a dead owner => taken over, GO"
  if [ "$DEAD_OK" = 0 ]; then
    skip "(c): kill -0 on a reaped pid does not say 'No such process' here [$DEAD_MSG]" 4
  else
    dead_pid
    RC="$(make_root dead)"
    put_owner "$RC" "$DEADP" "$HOST" "x"
    fg "$RC" "$TMP/c.out" "$TMP/c.err" 30 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=3 bash "$SCAN"
    [ "$FRC" -eq 0 ] && ok "(c) rc 0" || ko "(c) expected rc 0, got $FRC"
    has "$TMP/c.out" "$(taken_line "$DEADP")" && ok "(c) the stale lock of the dead pid is taken over, said" \
      || ko "(c) no 'taken over' line for the dead pid"
    [ "$(taken_count "$TMP/c.out")" = 1 ] && ok "(c) exactly one 'taken over'" || ko "(c) $(taken_count "$TMP/c.out") 'taken over' lines"
    [ ! -d "$(rep "$RC")/.lock" ] && ok "(c) the lock is released at the end" || ko "(c) the lock outlived the run"
  fi
fi
if want c2; then
  echo "=== (c2) a live pid at a FALSE start => recycled, taken over"
  if [ "$START_OK" = 0 ]; then
    skip "(c2): $SKIP_START" 2
  else
    RC2="$(make_root recycled)"
    put_owner "$RC2" "$LIVE" "$HOST" "$FAKE_ST"
    fg "$RC2" "$TMP/c2.out" "$TMP/c2.err" 30 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=3 bash "$SCAN"
    [ "$FRC" -eq 0 ] && ok "(c2) rc 0" || ko "(c2) expected rc 0, got $FRC"
    has "$TMP/c2.out" "$(taken_line "$LIVE")" && ok "(c2) the recycled pid's lock is taken over" \
      || ko "(c2) no 'taken over' for a pid at a false start"
  fi
fi
if want c3; then
  echo "=== (c3) another host => lock-busy, never taken (a dead pid there, so the host is the only guard)"
  if [ "$DEAD_OK" = 0 ]; then
    skip "(c3): kill -0 on a reaped pid does not say 'No such process' here" 3
  else
    dead_pid
    RC3="$(make_root foreign)"
    put_owner "$RC3" "$DEADP" "other-host.invalid" "x"
    fg "$RC3" "$TMP/c3.out" "$TMP/c3.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
    [ "$FRC" -eq 1 ] && ok "(c3) rc 1" || ko "(c3) expected rc 1, got $FRC"
    grep -Fq "$TAKEN_MARK" "$TMP/c3.out" && ko "(c3) a lock of ANOTHER host was taken over" || ok "(c3) never taken over"
    has "$TMP/c3.out" "$RM_LINE" && ok "(c3) the removal remedy (not held: foreign)" || ko "(c3) the removal remedy is missing"
  fi
fi
if want c4; then
  echo "=== (c4) ps answering a PADDED lstart to holder and waiter => held, lock-busy"
  if [ "$IS_LINUX" = 1 ]; then
    skip "(c4): Linux — the /proc branch calls no ps" 3
  else
    RC4="$(make_root padded)"
    put_owner "$RC4" "$LIVE" "$HOST" "$EPOCH_ST"
    fg "$RC4" "$TMP/c4.out" "$TMP/c4.err" 20 PATH="$PSEPOCH:$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
    [ "$FRC" -eq 1 ] && ok "(c4) rc 1" || ko "(c4) expected rc 1, got $FRC"
    has "$TMP/c4.out" "$(held_line "$LIVE")" && ok "(c4) the padded start compared equal: held" \
      || ko "(c4) the padded start did not compare equal (trailing spaces lost?)"
    grep -Fq "$TAKEN_MARK" "$TMP/c4.out" && ko "(c4) taken over on a padded start" || ok "(c4) never taken over"
  fi
fi

# ---- (c5) deterministic interleaving ---------------------------------------------
if want c5; then
  echo "=== (c5) thief 1 suspended on its first judgement, thief 2 steals and holds => thief 1 busy"
  if [ "$IS_LINUX" = 1 ]; then
    skip "(c5): Linux — the re-judgement calls no external binary, the ps stub suspends nothing" 6
  elif [ "$START_OK" = 0 ]; then
    skip "(c5): $SKIP_START" 6
  else
    RC5="$(make_root interleave)"
    put_owner "$RC5" "$LIVE" "$HOST" "$FAKE_ST"
    bg "$RC5" "$TMP/c5.t1.out" PATH="$PSPAUSE:$CLEAN:$PATH" LOCKB_JUDGED="$LIVE" LOCKB_CTR="$TMP/c5.ctr" \
      LOCKB_PAUSE_AT=1 LOCKB_PAUSED="$TMP/c5.paused" LOCKB_GO="$TMP/c5.go" SCA_LOCK_WAIT_SECONDS=8 bash "$SCAN"
    T1=$BPID
    wait_file "$TMP/c5.paused" 20 && ok "(c5) witness: thief 1 is suspended in its first judgement" \
      || ko "(c5) witness: thief 1 never reached the judgement"
    bg "$RC5" "$TMP/c5.t2.out" PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/c5.t2held" LOCKB_GO="$TMP/c5.t2go" \
      SCA_LOCK_WAIT_SECONDS=8 bash "$SCAN"
    T2=$BPID
    wait_file "$TMP/c5.t2held" 20 && ok "(c5) witness: thief 2 stole the lock and holds it" \
      || ko "(c5) witness: thief 2 never got the lock"
    : > "$TMP/c5.go"
    reap "$T1" 30
    rc_t1=$RRC
    own_c5="$(sed -n 1p "$(rep "$RC5")/.lock/owner" 2>/dev/null)"
    : > "$TMP/c5.t2go"
    reap "$T2" 30
    [ "$rc_t1" -eq 1 ] && ok "(c5) thief 1 rc 1: it re-judged under the mutex and found thief 2" \
      || ko "(c5) thief 1 expected rc 1, got $rc_t1"
    [ "$own_c5" = "$T2" ] && ok "(c5) the owner is thief 2 when thief 1 is done" \
      || ko "(c5) expected owner $T2 (thief 2), got [$own_c5]"
    n_c5=$(( $(taken_count "$TMP/c5.t1.out") + $(taken_count "$TMP/c5.t2.out") ))
    [ "$n_c5" -eq 1 ] && ok "(c5) ONE 'taken over' in all" || ko "(c5) $n_c5 'taken over' lines — two thieves"
    [ "$RRC" -eq 0 ] && ok "(c5) thief 2 completes, rc 0" || ko "(c5) thief 2 expected rc 0, got $RRC"
  fi
fi

# ---- (c6)/(c7) one holder under TZ=Asia/Tokyo -------------------------------------
if want c6; then
  echo "=== (c6) holder under TZ=Asia/Tokyo, waiter under TZ=America/New_York => held"
  if [ "$START_OK" = 0 ] && [ "$IS_LINUX" = 1 ] && [ ! -r /proc/self/stat ]; then
    # /proc unreadable: the scanner's own bound (README « The reports lock »), the
    # start cannot be described there — a named skip, never a false diagnosis.
    skip "(c6): /proc unreadable — the scanner's own bound, start not describable" 4
    skip "(c7): /proc unreadable (README bound)" 1
    skip "(c9): /proc unreadable (README bound)" 1
  elif [ "$START_OK" = 0 ] && [ "$IS_LINUX" = 1 ]; then
    # On Linux with /proc readable the start comes from /proc, no external binary: an
    # empty start on the LIVE premise pid is the dispatcher's defect (MB34). Measured
    # in a ps-less container: the former "(c7): Linux only" skip kept MB34 green.
    skip "(c6): the start is not describable, see (c7)" 4
    ko "(c7) Linux: lock_start answered nothing on the live pid $LIVE — the /proc branch is broken"
    skip "(c9): its holder needs a describable start, see (c7)" 1
  elif [ "$START_OK" = 0 ]; then
    skip "(c6): $SKIP_START" 4
    skip "(c7): Linux only" 1
    skip "(c9): Linux only" 1
  else
    RC6="$(make_root tz)"
    bg "$RC6" "$TMP/c6.h.out" TZ=Asia/Tokyo PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/c6.held" LOCKB_GO="$TMP/c6.go" bash "$SCAN"
    H6=$BPID
    wait_file "$TMP/c6.held" 20 && ok "(c6) witness: the Tokyo holder holds the lock" \
      || ko "(c6) witness: the holder never got the lock"
    cp "$(rep "$RC6")/.lock/owner" "$TMP/c6.owner" 2>/dev/null
    fg "$RC6" "$TMP/c6.w.out" "$TMP/c6.w.err" 20 TZ=America/New_York PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=3 bash "$SCAN"
    [ "$FRC" -eq 1 ] && has "$TMP/c6.w.out" "$(held_line "$H6")" \
      && ok "(c6) the New York waiter reads the Tokyo holder HELD, rc 1" \
      || ko "(c6) expected rc 1 and the held line, got rc $FRC: $(tr '\n' '|' < "$TMP/c6.w.out")"
    cmp -s "$TMP/c6.owner" "$(rep "$RC6")/.lock/owner" && ok "(c6) the holder's owner is intact" \
      || ko "(c6) the holder's owner was replaced — a live holder was stolen"
    if [ "$IS_LINUX" = 1 ]; then
      l3="$(sed -n 3p "$(rep "$RC6")/.lock/owner" 2>/dev/null)"
      f22="$(sed 's/.*) //' "/proc/$H6/stat" 2>/dev/null | cut -d' ' -f20)"
      [ -n "$f22" ] && [ "$l3" = "ticks:$f22" ] && ok "(c7) owner line 3 [$l3] = ticks: + field 22 of /proc/$H6/stat" \
        || ko "(c7) owner line 3 [$l3] is not ticks:[$f22]"
      # (c9) the expectation is built HERE, never by lock_host: the form, not a copy.
      l2="$(sed -n 2p "$(rep "$RC6")/.lock/owner" 2>/dev/null)"
      ns9="$(readlink /proc/self/ns/pid 2>/dev/null)"
      [ -n "$ns9" ] && [ "$l2" = "$(uname -n) $ns9" ] \
        && ok "(c9) owner line 2 [$l2] = uname -n + the pid namespace" \
        || ko "(c9) owner line 2 [$l2] is not [$(uname -n) $ns9]"
    else
      skip "(c7): Linux only (/proc/<pid>/stat field 22)" 1
      skip "(c9): Linux only (the pid namespace in the host line)" 1
    fi
    : > "$TMP/c6.go"
    reap "$H6" 30
    [ "$RRC" -eq 0 ] && ok "(c6) the holder was alive all along and completes, rc 0" \
      || ko "(c6) the holder expected rc 0, got $RRC"
  fi
fi

# ---- (c8) another pid namespace, the same hostname (closing review T6) --------------
# The owner is this suite's LIVE sleep; the waiter runs in a NEW pid namespace (and
# user namespace, so no privilege is needed), where that pid does not exist. With
# the bare hostname it read dead and was TAKEN OVER while alive.
if want c8; then
  echo "=== (c8) Linux: a LIVE owner here, a waiter in ANOTHER pid namespace => foreign, never taken"
  if [ "$IS_LINUX" = 0 ]; then
    skip "(c8): Linux only (pid namespaces)" 4
  elif [ "$NS_OK" = 0 ]; then
    skip "(c8): unshare --user --pid refused or absent here [$NS_MSG]" 4
  else
    RC8="$(make_root pidns)"
    put_owner "$RC8" "$LIVE" "$HOST" "$LIVE_ST"
    cp "$(rep "$RC8")/.lock/owner" "$TMP/c8.owner"
    if [ "$NS_USER" = 1 ]; then
      fg "$RC8" "$TMP/c8.out" "$TMP/c8.err" 30 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 \
        unshare --user --map-root-user --pid --fork --mount-proc --kill-child bash "$SCAN"
    else
      fg "$RC8" "$TMP/c8.out" "$TMP/c8.err" 30 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 \
        unshare --pid --fork --mount-proc --kill-child bash "$SCAN"
    fi
    [ "$FRC" -eq 1 ] && ok "(c8) rc 1 — the live owner of the other namespace is never judged dead" \
      || ko "(c8) expected rc 1, got $FRC: $(tr '\n' '|' < "$TMP/c8.out") $(tr '\n' '|' < "$TMP/c8.err")"
    has "$TMP/c8.out" "$(busy_line "$LIVE" 2)" && ok "(c8) the lock-busy line" || ko "(c8) the lock-busy line is missing"
    grep -Fq "$TAKEN_MARK" "$TMP/c8.out" && ko "(c8) a LIVE owner of another pid namespace was TAKEN OVER" \
      || ok "(c8) never taken over"
    cmp -s "$TMP/c8.owner" "$(rep "$RC8")/.lock/owner" && ok "(c8) the live owner's lock is intact" \
      || ko "(c8) the live owner's lock was replaced"
  fi
fi

# ---- (d1) an owner-less lock --------------------------------------------------------
if want d1; then
  echo "=== (d1) an owner-less lock, WAIT=8 => lock-busy, the removal remedy, quiet stderr"
  RD1="$(make_root ownerless)"
  mkdir -p "$(rep "$RD1")/.lock"
  fg "$RD1" "$TMP/d1.out" "$TMP/d1.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=8 bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(d1) rc 1 — the 40 s grace outlasts the wait" || ko "(d1) expected rc 1, got $FRC"
  has "$TMP/d1.out" "$(wait_line '?' 8)" && ok "(d1) the waiting line says pid ?" || ko "(d1) the waiting line is missing"
  has "$TMP/d1.out" "$(busy_line '?' 8)" && ok "(d1) the lock-busy line says pid ?" || ko "(d1) the lock-busy line is missing"
  has "$TMP/d1.out" "$RM_LINE" && ok "(d1) the removal remedy, both paths named" || ko "(d1) the removal remedy is missing"
  grep -Fq "$TAKEN_MARK" "$TMP/d1.out" && ko "(d1) taken over before the grace" || ok "(d1) not taken over"
  grep -Fq 'No such file' "$TMP/d1.err" && ko "(d1) stderr leaks 'No such file' (redirection order)" \
    || ok "(d1) reading the missing owner leaks nothing on stderr"
fi

# ---- (d3)-(d5) hostile, truncated, orphan mutex ------------------------------------
if want d3; then
  echo "=== (d3) an owner whose pid line is \$(touch PWNED) => never evaluated"
  RD3="$(make_root pwned)"
  put_owner "$RD3" '$(touch PWNED)' "$HOST" 'x'
  fg "$RD3" "$TMP/d3.out" "$TMP/d3.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(d3) rc 1 — read unreadable, within the grace" || ko "(d3) expected rc 1, got $FRC"
  [ ! -e "$RD3/PWNED" ] && [ ! -e "$(rep "$RD3")/PWNED" ] && [ ! -e "$PWD/PWNED" ] \
    && ok "(d3) no PWNED anywhere — the owner was never evaluated" || ko "(d3) PWNED exists: the owner was EVALUATED"
fi
if want d4; then
  echo "=== (d4) an owner truncated without its last newline => unreadable, not taken"
  RD4="$(make_root truncated)"
  mkdir -p "$(rep "$RD4")/.lock"
  printf '%s\n%s\n%s' "$LIVE" "$HOST" 'Thu Oct' > "$(rep "$RD4")/.lock/owner"
  fg "$RD4" "$TMP/d4.out" "$TMP/d4.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
  [ "$FRC" -eq 1 ] && has "$TMP/d4.out" "$(busy_line '?' 2)" && ok "(d4) rc 1, read unreadable (pid ?)" \
    || ko "(d4) expected rc 1 and pid ?, got rc $FRC"
  grep -Fq "$TAKEN_MARK" "$TMP/d4.out" && ko "(d4) a truncated owner was taken over" || ok "(d4) not taken over"
fi
if want d5; then
  echo "=== (d5) a dead owner and an ORPHAN .lock.steal => lock-busy, the remedy names both"
  dead_pid
  RD5="$(make_root orphan-mutex)"
  put_owner "$RD5" "$DEADP" "$HOST" "x"
  mkdir -p "$(rep "$RD5")/.lock.steal"
  fg "$RD5" "$TMP/d5.out" "$TMP/d5.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
  [ "$FRC" -eq 1 ] && ok "(d5) rc 1 — the orphan mutex forbids the theft" || ko "(d5) expected rc 1, got $FRC"
  has "$TMP/d5.out" "$RM_LINE" && ok "(d5) the remedy names .lock AND .lock.steal" || ko "(d5) the removal remedy is missing"
  grep -Fq "$TAKEN_MARK" "$TMP/d5.out" && ko "(d5) taken over through an orphan mutex" || ok "(d5) not taken over"
fi

# ---- (d6)/(d7) the theft that fails, the claim refused after it ---------------------
if want d6; then
  echo "=== (d6) a dead owner whose lock cannot be removed => rc 1 in time, no false 'taken over'"
  if [ "$DEAD_OK" = 0 ]; then
    skip "(d6): kill -0 on a reaped pid does not say 'No such process' here" 6
  else
    dead_pid
    RD6="$(make_root rmfail)"
    put_owner "$RD6" "$DEADP" "$HOST" "x"
    s_d6=$SECONDS
    fg "$RD6" "$TMP/d6.out" "$TMP/d6.err" 12 PATH="$RMFAIL:$CLEAN:$PATH" LOCKB_RMCTR="$TMP/d6.ctr" SCA_LOCK_WAIT_SECONDS=2 bash "$SCAN"
    el_d6=$((SECONDS - s_d6))
    n_d6="$(grep -c '' "$TMP/d6.ctr" 2>/dev/null)"
    n_d6="${n_d6:-0}"
    [ "$FRC" -eq 1 ] && ok "(d6) rc 1 (never the watchdog's 124)" || ko "(d6) expected rc 1, got $FRC"
    [ "$el_d6" -le 7 ] && ok "(d6) ended in ${el_d6}s <= WAIT+5" || ko "(d6) took ${el_d6}s — the loop spun past the wait"
    grep -Fq "$TAKEN_MARK" "$TMP/d6.out" && ko "(d6) 'taken over' said for a removal that FAILED" || ok "(d6) no 'taken over'"
    [ -d "$(rep "$RD6")/.lock" ] && ok "(d6) the lock is still there" || ko "(d6) the lock vanished"
    [ ! -d "$(rep "$RD6")/.lock.steal" ] && ok "(d6) no mutex left behind" || ko "(d6) a .lock.steal was left"
    [ "$n_d6" -ge 1 ] && [ "$n_d6" -le 4 ] && ok "(d6) the failing removal was tried $n_d6 time(s), <= WAIT+2" \
      || ko "(d6) the failing removal was tried $n_d6 time(s) (expected 1..4)"
  fi
fi
if want d7; then
  echo "=== (d7) the claim refused for 3 s after a theft => <= 5 refusals, ONE 'taken over'"
  if [ "$DEAD_OK" = 0 ]; then
    skip "(d7): kill -0 on a reaped pid does not say 'No such process' here" 4
  else
    dead_pid
    RD7="$(make_root mkrefuse)"
    put_owner "$RD7" "$DEADP" "$HOST" "x"
    bg "$RD7" "$TMP/d7.out" PATH="$D7BIN:$CLEAN:$PATH" LOCKB_FLAG="$TMP/d7.flag" LOCKB_REL="$TMP/d7.rel" \
      LOCKB_MKCTR="$TMP/d7.mk" SCA_LOCK_WAIT_SECONDS=12 bash "$SCAN"
    P7=$BPID
    wait_file "$TMP/d7.flag" 15 && ok "(d7) witness: the theft removed the lock" || ko "(d7) witness: no theft"
    sleep 3
    : > "$TMP/d7.rel"
    reap "$P7" 30
    n_d7="$(grep -c '' "$TMP/d7.mk" 2>/dev/null)"
    n_d7="${n_d7:-0}"
    [ "$n_d7" -ge 1 ] && [ "$n_d7" -le 5 ] && ok "(d7) $n_d7 refused claim(s) in 3 s, <= 5" \
      || ko "(d7) $n_d7 refused claims (expected 1..5) — the loop spun"
    [ "$(taken_count "$TMP/d7.out")" = 1 ] && ok "(d7) ONE 'taken over'" || ko "(d7) $(taken_count "$TMP/d7.out") 'taken over' lines"
    [ "$RRC" -eq 0 ] && ok "(d7) rc 0 once the claim succeeds" || ko "(d7) expected rc 0, got $RRC"
  fi
fi

# ---- (e) re-entry ---------------------------------------------------------------------
if want e; then
  echo "=== (e) --all-modules root + sub, WAIT=1 => the children see the parent as the owner"
  RE="$(make_root modules)"
  mkdir -p "$RE/sub"
  printf 'flask==2.0.0\n' > "$RE/sub/requirements.txt"
  bg "$RE" "$TMP/e.out" PATH="$CLEAN:$PATH" LOCKB_OWNERLOG="$TMP/e.owners" LOCKB_LOCKDIR="$(rep "$RE")/.lock" \
    SCA_LOCK_WAIT_SECONDS=1 bash "$SCAN" --all-modules
  PE=$BPID
  reap "$PE" 60
  [ "$(grep -c '^== module ' "$TMP/e.out")" = 2 ] && ok "(e) witness: two module runs" \
    || ko "(e) witness: expected two module runs: $(grep '^== module ' "$TMP/e.out" | tr '\n' '|')"
  [ "$RRC" -eq 0 ] && ok "(e) rc 0" || ko "(e) expected rc 0, got $RRC"
  grep -Fq 'waiting up to' "$TMP/e.out" && ko "(e) a module run waited for its own parent's lock" || ok "(e) no module run waited"
  grep -Fq 'reports lock held by pid' "$TMP/e.out" && ko "(e) a lock line in the output" || ok "(e) no lock-busy line"
  own_e="$(sort -u "$TMP/e.owners" 2>/dev/null | tr '\n' ' ')"
  [ "$(grep -c '' "$TMP/e.owners" 2>/dev/null)" = 2 ] && [ "$own_e" = "$PE " ] \
    && ok "(e) both module runs saw the parent ($PE) as the owner" \
    || ko "(e) the owners seen by the module runs: [$own_e] (parent $PE)"
fi

# ---- (f) cleanup on every exit -----------------------------------------------------------
if want f; then
  echo "=== (f) the lock and the witness file are gone after every exit"
  RF="$(make_root nominal)"
  mkdir -p "$TMP/td-f1"
  fg "$RF" "$TMP/f1.out" "$TMP/f1.err" 30 TMPDIR="$TMP/td-f1" PATH="$CLEAN:$PATH" bash "$SCAN"
  [ "$FRC" -eq 0 ] && [ ! -d "$(rep "$RF")/.lock" ] && ok "(f) nominal run: rc 0, lock released" \
    || ko "(f) nominal run: rc $FRC, lock $( [ -d "$(rep "$RF")/.lock" ] && echo PRESENT || echo absent)"
  left_f1="$(leftovers "$TMP/td-f1")"
  [ -z "$left_f1" ] && ok "(f) nominal run: no witness file left" || ko "(f) nominal run left:$left_f1"
  r_f1="$(audit_rows "$RF")"
  [ "$r_f1" = "mode=scan verdict=GO reason=- module=root" ] \
    && ok "(f) nominal run: ONE audit row, parsed scan GO — no aborted row" \
    || ko "(f) nominal run: audit rows [$r_f1] (expected the one scan GO)"
  RFT="$(make_root trivy)"
  mkdir -p "$TMP/td-ft"
  fg "$RFT" "$TMP/ft.out" "$TMP/ft.err" 30 TMPDIR="$TMP/td-ft" PATH="$TRIVYOK:$CLEAN:$PATH" bash "$SCAN"
  [ -f "$(rep "$RFT")/trivy-config.json" ] && ok "(f) witness: the trivy path ran and kept its report" \
    || ko "(f) witness: no trivy-config.json — the trivy block was not reached"
  [ ! -d "$(rep "$RFT")/.lock" ] && ok "(f) trivy run: lock released (ONE trap, cleanup's)" \
    || ko "(f) trivy run: the lock outlived the run — a second trap replaced cleanup?"
  left_ft="$(leftovers "$TMP/td-ft")"
  [ -z "$left_ft" ] && ok "(f) trivy run: neither the trivy temp file nor the witness left" || ko "(f) trivy run left:$left_ft"
  for sig in TERM HUP; do
    RFS="$(make_root "sig-$sig")"
    mkdir -p "$TMP/td-$sig"
    bg "$RFS" "$TMP/f-$sig.out" TMPDIR="$TMP/td-$sig" PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/f-$sig.held" \
      LOCKB_GO="$TMP/f-$sig.go" bash "$SCAN"
    PS_=$BPID
    wait_file "$TMP/f-$sig.held" 20
    w_sig="$(leftovers "$TMP/td-$sig")"
    [ -d "$(rep "$RFS")/.lock" ] && [ -n "$w_sig" ] && ok "(f) $sig witness: the holder holds the lock and its witness file" \
      || ko "(f) $sig witness: lock or witness file missing while held [$w_sig]"
    kill -s "$sig" "$PS_" 2>/dev/null
    : > "$TMP/f-$sig.go"
    reap "$PS_" 40
    case "$sig" in
      TERM) want_rc=143 ;;
      *) want_rc=129 ;;
    esac
    [ "$RRC" -eq "$want_rc" ] && ok "(f) $sig: the holder died of it (rc $RRC)" || ko "(f) $sig: expected rc $want_rc, got $RRC"
    [ ! -d "$(rep "$RFS")/.lock" ] && ok "(f) $sig: lock released by the trap" || ko "(f) $sig: the lock outlived the signal"
    left_s="$(leftovers "$TMP/td-$sig")"
    [ -z "$left_s" ] && ok "(f) $sig: no witness file left" || ko "(f) $sig: left:$left_s"
    r_s="$(audit_rows "$RFS")"
    [ "$r_s" = "mode=scan verdict=NO-GO reason=aborted module=root" ] \
      && ok "(f) $sig: ONE audit row, parsed scan NO-GO aborted" \
      || ko "(f) $sig: audit rows [$r_s] (expected the one scan NO-GO aborted)"
  done
  # The module slug of the aborted row goes through sanitize_display (C13): a
  # `"` written raw would break the row, which a JSONL reader then drops.
  RFQ="$(make_root quote)"
  mkdir -p "$RFQ/mod\"x"
  printf 'flask==2.0.0\n' > "$RFQ/mod\"x/requirements.txt"
  bg "$RFQ" "$TMP/fq.out" PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/fq.held" LOCKB_GO="$TMP/fq.go" bash "$SCAN" 'mod"x'
  PQ=$BPID
  wait_file "$TMP/fq.held" 20 && [ -d "$(rep "$RFQ")/.lock" ] \
    && ok "(f) mod\"x witness: the module run holds the lock" || ko "(f) mod\"x witness: not held"
  kill -s TERM "$PQ" 2>/dev/null
  : > "$TMP/fq.go"
  reap "$PQ" 40
  r_q="$(audit_rows "$RFQ")"
  [ "$RRC" -eq 143 ] && [ "$r_q" = "mode=scan verdict=NO-GO reason=aborted module=mod?x" ] \
    && ok "(f) mod\"x TERM: rc 143, ONE row, parsed scan NO-GO aborted, module mod?x (sanitised)" \
    || ko "(f) mod\"x TERM: rc $RRC, audit rows [$r_q]"
  [ ! -d "$(rep "$RFQ")/.lock" ] && ok "(f) mod\"x TERM: lock released" || ko "(f) mod\"x TERM: the lock outlived the signal"
  RFE="$(make_root early)"
  mkdir -p "$TMP/td-fe"
  fg "$RFE" "$TMP/fe.out" "$TMP/fe.err" 20 LC_ALL=C TMPDIR="$TMP/td-fe" PATH="$CLEAN:$PATH" bash "$SCAN" no-such-module
  [ "$FRC" -eq 2 ] && has "$TMP/fe.out" 'SCA: module dir not found: no-such-module' \
    && ok "(f) witness: the early exit 'module dir not found', rc 2" || ko "(f) witness: expected the module-not-found exit, rc $FRC"
  grep -Fq 'unbound variable' "$TMP/fe.err" && ko "(f) the early exit says 'unbound variable': $(cat "$TMP/fe.err")" \
    || ok "(f) the early exit leaves no 'unbound variable' (LC_ALL=C)"
fi

# ---- (f2) TERM inside the mutex ---------------------------------------------------------
if want f2; then
  echo "=== (f2) TERM to a thief suspended INSIDE the mutex => rc 143, mutex gone"
  if [ "$IS_LINUX" = 1 ]; then
    skip "(f2): Linux — the re-judgement calls no ps, nothing suspends it" 4
  elif [ "$START_OK" = 0 ]; then
    skip "(f2): $SKIP_START" 4
  else
    RF2="$(make_root term-mutex)"
    put_owner "$RF2" "$LIVE" "$HOST" "$FAKE_ST"
    bg "$RF2" "$TMP/f2.out" PATH="$PSPAUSE:$CLEAN:$PATH" LOCKB_JUDGED="$LIVE" LOCKB_CTR="$TMP/f2.ctr" \
      LOCKB_PAUSE_AT=2 LOCKB_PAUSED="$TMP/f2.paused" LOCKB_GO="$TMP/f2.go" SCA_LOCK_WAIT_SECONDS=20 bash "$SCAN"
    P_F2=$BPID
    wait_file "$TMP/f2.paused" 20
    [ -d "$(rep "$RF2")/.lock.steal" ] && ok "(f2) witness: the thief holds the mutex, suspended in its re-judgement" \
      || ko "(f2) witness: the thief is not inside the mutex"
    kill -s TERM "$P_F2" 2>/dev/null
    : > "$TMP/f2.go"
    reap "$P_F2" 40
    [ "$RRC" -eq 143 ] && ok "(f2) rc 143" || ko "(f2) expected rc 143, got $RRC"
    [ ! -d "$(rep "$RF2")/.lock.steal" ] && ok "(f2) the mutex is gone — cleanup released it" \
      || ko "(f2) the mutex .lock.steal is ORPHANED"
    r_f2="$(audit_rows "$RF2")"
    [ -z "$r_f2" ] && ok "(f2) the thief never held the lock: no audit row, no aborted" \
      || ko "(f2) the thief wrote audit rows [$r_f2] — an aborted row without the lock"
  fi
fi

# ---- (f3) the real cleanup() in a subshell -------------------------------------------------
if want f3; then
  echo "=== (f3) the REAL cleanup(): a subshell leaves the lock, the owner shell removes it"
  . "$TMP/cleanup.fn"
  L="$TMP/f3/.lock"
  mkdir -p "$L"
  MY_PID=$$
  MY_HOST="$HOST"
  printf '%s\n%s\n%s\n' "$MY_PID" "$MY_HOST" "x" > "$L/owner"
  lock_mine=1
  steal_held=0
  ref=''
  modlog=''
  TRIVY_TMP=''
  CLEANUP_OWNER="${BASHPID:-$$}"
  if [ "$HAS_BASHPID" = 1 ]; then
    ( cleanup )
    [ -d "$L" ] && ok "(f3) cleanup() in a subshell left the lock (BASHPID guard)" \
      || ko "(f3) cleanup() in a SUBSHELL released the lock of the run"
  else
    skip "(f3) subshell: BASHPID absent (bash < 4) — the guard is inert, a subshell is NOT told apart" 1
  fi
  cleanup
  # cleanup() opens on `trap '' TERM HUP` (a second signal must not cut it):
  # called HERE, in this suite's own shell, it would leave both IGNORED, and every
  # run launched below would inherit that and never see a TERM. Restored.
  trap - TERM HUP
  [ ! -d "$L" ] && ok "(f3) cleanup() in its owner shell released the lock" || ko "(f3) the owner's cleanup() kept the lock"
fi

# ---- (f4) --all-modules cut by TERM: the parent alone, then its group ----------------------
if want f4; then
  echo "=== (f4) --all-modules, TERM to the parent alone, then to its group => rc 143, ONE all-modules aborted row, last"
  # The parent alone: bash defers its TERM trap while the foreground module
  # pipeline runs. MEASURED before the trap: the parent died at once, released the
  # lock WHILE its module still ran, and that module wrote its reports and its row
  # without the lock; now it stays, the lock held, until the module ends.
  RF4="$(make_root am-parent)"
  bg "$RF4" "$TMP/f4.out" PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/f4.held" LOCKB_GO="$TMP/f4.go" bash "$SCAN" --all-modules
  P4=$BPID
  wait_file "$TMP/f4.held" 20 && ok "(f4) parent witness: its module run holds in pip-audit" \
    || ko "(f4) parent witness: the module run never reached pip-audit"
  kill -s TERM "$P4" 2>/dev/null
  sleep 1
  [ -d "$(rep "$RF4")/.lock" ] && ok "(f4) parent: 1 s after TERM the lock is still HELD (the trap waits for the module)" \
    || ko "(f4) parent: the lock was released while the module run was still running"
  : > "$TMP/f4.go"
  reap "$P4" 40
  [ "$RRC" -eq 143 ] && ok "(f4) parent: rc 143" || ko "(f4) parent: expected rc 143, got $RRC"
  r_4="$(audit_rows "$RF4")"
  [ "$r_4" = "mode=scan verdict=GO reason=- module=root|mode=all-modules verdict=NO-GO reason=aborted module=-" ] \
    && ok "(f4) parent: the module's row, then ONE all-modules NO-GO aborted row, last (parsed)" \
    || ko "(f4) parent: audit rows [$r_4]"
  [ ! -d "$(rep "$RF4")/.lock" ] && ok "(f4) parent: lock released" || ko "(f4) parent: the lock outlived the run"
  # The group: every process of the run is signalled at once (a host timeout's way).
  RF5="$(make_root am-group)"
  bgs "$RF5" "$TMP/f5.out" PATH="$CLEAN:$PATH" LOCKB_PAUSED="$TMP/f5.held" LOCKB_GO="$TMP/f5.go" bash "$SCAN" --all-modules
  P5=$BPID
  wait_file "$TMP/f5.held" 20 && ok "(f4) group witness: its module run holds in pip-audit" \
    || ko "(f4) group witness: the module run never reached pip-audit"
  kill -s TERM -- "-$P5" 2>/dev/null
  reap "$P5" 40
  : > "$TMP/f5.go"
  [ "$RRC" -eq 143 ] && ok "(f4) group: rc 143" || ko "(f4) group: expected rc 143, got $RRC"
  r_5="$(audit_rows "$RF5")"
  [ "$r_5" = "mode=all-modules verdict=NO-GO reason=aborted module=-" ] \
    && ok "(f4) group: ONE row, parsed all-modules NO-GO aborted (the module run, a re-entry, writes none)" \
    || ko "(f4) group: audit rows [$r_5]"
  [ ! -d "$(rep "$RF5")/.lock" ] && ok "(f4) group: lock released" || ko "(f4) group: the lock outlived the run"
fi

# ---- (f5) a SECOND TERM while cleanup() runs ---------------------------------------------
if want f5; then
  echo "=== (f5) TERM to the group, then a SECOND TERM inside cleanup() => cleanup ends: lock gone, no witness, ONE aborted row"
  # A `date` that sleeps 2 s once LOCKB_SLOW exists: cleanup's own `$(date …)` is
  # then where the second TERM lands (0.7 s after the first). Measured before
  # `trap '' TERM HUP` at the head of cleanup (exec-critic, tools/t2.sh): the
  # second TERM ran the trap INSIDE cleanup, `exit 143` cut it — .lock and the
  # witness left, no row.
  SLOWDATE="$TMP/bin-slowdate"
  mkdir -p "$SLOWDATE"
  printf '%s\n' '#!/usr/bin/env bash' \
    'if [ -n "${LOCKB_SLOW:-}" ] && [ -e "$LOCKB_SLOW" ]; then' \
    '  sleep 2' \
    'fi' \
    "exec \"$REAL_DATE\" \"\$@\"" > "$SLOWDATE/date"
  chmod +x "$SLOWDATE/date"
  RF6="$(make_root second-term)"
  mkdir -p "$TMP/td-f5"
  bgs "$RF6" "$TMP/f5b.out" TMPDIR="$TMP/td-f5" PATH="$SLOWDATE:$CLEAN:$PATH" LOCKB_SLOW="$TMP/f5.slow" \
    LOCKB_PAUSED="$TMP/f5b.held" LOCKB_GO="$TMP/f5b.go" bash "$SCAN"
  P6=$BPID
  wait_file "$TMP/f5b.held" 20 && [ -d "$(rep "$RF6")/.lock" ] && [ -n "$(leftovers "$TMP/td-f5")" ] \
    && ok "(f5) witness: the holder holds the lock and its witness file" || ko "(f5) witness: not held"
  : > "$TMP/f5.slow"
  kill -s TERM -- "-$P6" 2>/dev/null
  sleep 0.7
  kill -s TERM "$P6" 2>/dev/null
  reap "$P6" 40
  : > "$TMP/f5b.go"
  [ "$RRC" -eq 143 ] && ok "(f5) rc 143" || ko "(f5) expected rc 143, got $RRC"
  [ ! -d "$(rep "$RF6")/.lock" ] && ok "(f5) the lock released despite the second TERM" \
    || ko "(f5) the second TERM cut cleanup(): the lock is LEFT"
  left_6="$(leftovers "$TMP/td-f5")"
  [ -z "$left_6" ] && ok "(f5) no witness file left" || ko "(f5) left:$left_6"
  r_6="$(audit_rows "$RF6")"
  [ "$r_6" = "mode=scan verdict=NO-GO reason=aborted module=root" ] \
    && ok "(f5) ONE audit row, parsed scan NO-GO aborted" || ko "(f5) audit rows [$r_6]"
fi

# ---- (g) --all-modules without Python ------------------------------------------------------
if want g; then
  echo "=== (g) --all-modules without Python => rc 0 DEGRADED, lock gone, quiet stderr"
  RG="$(make_root nopy)"
  mkdir -p "$TMP/td-g"
  fg "$RG" "$TMP/g.out" "$TMP/g.err" 20 LC_ALL=C TMPDIR="$TMP/td-g" PATH="$NOPY:$CLEAN:$PATH" bash "$SCAN" --all-modules
  [ "$FRC" -eq 0 ] && has "$TMP/g.out" 'SCA GATE all-modules (effective, waivers applied): GO (DEGRADED — no effective verdict)' \
    && ok "(g) rc 0 DEGRADED" || ko "(g) expected rc 0 and the DEGRADED line, got rc $FRC"
  [ ! -d "$(rep "$RG")/.lock" ] && ok "(g) lock released" || ko "(g) the lock outlived the run"
  grep -Fq 'unbound variable' "$TMP/g.err" && ko "(g) 'unbound variable' on the python-absent exit" \
    || ok "(g) no 'unbound variable' on the python-absent exit (LC_ALL=C)"
  left_g="$(leftovers "$TMP/td-g")"
  [ -z "$left_g" ] && ok "(g) no witness file left" || ko "(g) left:$left_g"
fi

# ---- (h)/(h2) the hook budget ---------------------------------------------------------------
if want h; then
  echo "=== (h) SCA_CHANGED_ONLY=1, no SCA_LOCK_WAIT_SECONDS => waits 30 s, not more"
  RH="$(make_root hook)"
  put_owner "$RH" "$LIVE" "$HOST" "$LIVE_ST"
  fg "$RH" "$TMP/h.out" "$TMP/h.err" 4 SCA_CHANGED_ONLY=1 PATH="$CLEAN:$PATH" bash "$SCAN"
  [ "$FRC" -eq 124 ] && ok "(h) still waiting when the watchdog stopped it (rc 124)" || ko "(h) expected rc 124, got $FRC"
  has "$TMP/h.out" "$(wait_line "$LIVE" 30)" && ok "(h) the hook waits up to 30s" \
    || ko "(h) the hook wait is not 30s: $(grep -F 'waiting up to' "$TMP/h.out")"
  echo "=== (h2) the 10 hook records that run sca-scan.sh: every budget >= 30 + 30 s"
  H2="$(python3 -c 'import json, sys
from pathlib import Path
root = Path(sys.argv[1])
files = (".codex/hooks.json", ".kimi-code/hooks.json", ".agents/hooks.json",
         ".github/hooks/agent-guardrails.json", ".claude/settings.json")
def walk(o):
    if isinstance(o, dict):
        if any(isinstance(v, str) and "sca-scan.sh" in v for v in o.values()):
            yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)
for f in files:
    p = root / f
    if not p.is_file():
        print("ABSENT %s -" % f)
        continue
    for rec in walk(json.loads(p.read_text(encoding="utf-8"))):
        b = rec.get("timeout", rec.get("timeoutSec"))
        print("REC %s %s" % (f, "none" if b is None else b))' "$REPO" 2>&1)"
  n_rec=0; n_bad=0; n_none=0; n_abs=0; bad_h2=''
  while IFS=' ' read -r kind file budget; do
    case "$kind" in
      REC)
        n_rec=$((n_rec + 1))
        case "$budget" in
          none)
            if [ "$file" = ".claude/settings.json" ]; then n_none=$((n_none + 1)); else n_bad=$((n_bad + 1)); bad_h2="$bad_h2 $file:none"; fi
            ;;
          ''|*[!0-9]*) n_bad=$((n_bad + 1)); bad_h2="$bad_h2 $file:$budget" ;;
          *)
            if [ "$budget" -lt 60 ]; then n_bad=$((n_bad + 1)); bad_h2="$bad_h2 $file:$budget"; fi
            ;;
        esac
        ;;
      ABSENT) n_abs=$((n_abs + 1)) ;;
    esac
  done <<<"$H2"
  if [ "$n_abs" -gt 0 ]; then
    skip "(h2): $n_abs host file(s) absent from this tree — $(printf '%s' "$H2" | grep '^ABSENT' | tr '\n' ' ')" 3
  else
    [ "$n_rec" -eq 10 ] && ok "(h2) 10 hook records run sca-scan.sh" || ko "(h2) $n_rec hook records (expected 10): $H2"
    [ "$n_bad" -eq 0 ] && ok "(h2) every budget >= 60 s (the 30 s wait + a scan)" || ko "(h2) budgets below 60 s:$bad_h2"
    [ "$n_none" -eq 2 ] && ok "(h2) .claude/settings.json NAMED: 2 records with no timeout key — its 60 s host budget is cited (semgrep-scan.sh), not measured" \
      || ko "(h2) expected 2 key-less .claude records, got $n_none"
  fi
fi
if want i; then
  echo "=== (i) SCA_LOCK_WAIT_SECONDS=abc => logged, the default used"
  RI="$(make_root badwait)"
  put_owner "$RI" "$LIVE" "$HOST" "$LIVE_ST"
  fg "$RI" "$TMP/i.out" "$TMP/i.err" 4 SCA_LOCK_WAIT_SECONDS=abc PATH="$CLEAN:$PATH" bash "$SCAN"
  has "$TMP/i.out" '  SCA: invalid SCA_LOCK_WAIT_SECONDS value; using 600 seconds' \
    && ok "(i) the invalid value is logged" || ko "(i) no log line for the invalid value"
  has "$TMP/i.out" "$(wait_line "$LIVE" 600)" && ok "(i) the default 600 s is used" || ko "(i) the default is not used"
fi
BAD_WAIT_LINE='  SCA: invalid SCA_LOCK_WAIT_SECONDS value; using 600 seconds'
if want i2; then
  echo "=== (i2) SCA_LOCK_WAIT_SECONDS 09 / 010 / 0 / 3600, live owner => no octal, never a run without the lock"
  # The four runs together, each bounded by its own `timeout 4`; judged after.
  pi2=''
  for v in 09 010 0 3600; do
    r="$(make_root "wait-$v")"
    put_owner "$r" "$LIVE" "$HOST" "$LIVE_ST"
    cp "$(rep "$r")/.lock/owner" "$TMP/i2-$v.owner"
    ( fg "$r" "$TMP/i2-$v.out" "$TMP/i2-$v.err" 4 SCA_LOCK_WAIT_SECONDS="$v" PATH="$CLEAN:$PATH" bash "$SCAN"
      printf '%s\n' "$FRC" > "$TMP/i2-$v.rc" ) &
    pi2="$pi2 $!"
  done
  for p in $pi2; do wait "$p"; done
  for v in 09 010; do
    r="$TMP/root-wait-$v"
    rc="$(cat "$TMP/i2-$v.rc" 2>/dev/null)"
    has "$TMP/i2-$v.out" "$BAD_WAIT_LINE" && has "$TMP/i2-$v.out" "$(wait_line "$LIVE" 600)" \
      && ok "(i2) $v: logged invalid, the default 600 s waited" \
      || ko "(i2) $v: not refused — $(grep -E 'invalid|waiting up to' "$TMP/i2-$v.out" | tr '\n' ' ')"
    if [ "$rc" = 124 ] && ! grep -Fq 'SCA GATE' "$TMP/i2-$v.out" && cmp -s "$TMP/i2-$v.owner" "$(rep "$r")/.lock/owner"; then
      ok "(i2) $v: still waiting at the watchdog (rc 124), no gate line, the owner intact"
    else
      ko "(i2) $v: rc [$rc], gate [$(grep -F 'SCA GATE' "$TMP/i2-$v.out")] — the run did not wait for the lock"
    fi
  done
  rc="$(cat "$TMP/i2-0.rc" 2>/dev/null)"
  [ "$rc" = 1 ] && has "$TMP/i2-0.out" "$(busy_line "$LIVE" 0)" \
    && ok "(i2) 0: valid, lock-busy beyond 0s, rc 1" \
    || ko "(i2) 0: rc [$rc], gate [$(grep -F 'SCA GATE' "$TMP/i2-0.out")]"
  grep -Fq 'invalid SCA_LOCK_WAIT_SECONDS' "$TMP/i2-0.out" && ko "(i2) 0: refused as invalid" \
    || ok "(i2) 0: not logged invalid"
  rc="$(cat "$TMP/i2-3600.rc" 2>/dev/null)"
  has "$TMP/i2-3600.out" "$(wait_line "$LIVE" 3600)" && ! grep -Fq 'invalid SCA_LOCK_WAIT_SECONDS' "$TMP/i2-3600.out" \
    && ok "(i2) 3600: valid, waited up to 3600s" \
    || ko "(i2) 3600: not taken as valid — $(grep -E 'invalid|waiting up to' "$TMP/i2-3600.out" | tr '\n' ' ')"
  [ "$rc" = 124 ] && ok "(i2) 3600: still waiting at the watchdog (rc 124)" || ko "(i2) 3600: rc [$rc], expected 124"
fi
if want i3; then
  echo "=== (i3) the fail-closed net: lock_acquire DISCARDED by bash => NO-GO rc 1, both call forms"
  # A copy of the dispatcher under test whose validation is forced TRUE (one
  # anchor, replaced by awk, counted): `09` then reaches `$(( ))` and aborts it.
  BYP="$KIT/sca-scan-bypass.sh"
  awk '{ if ($0 == "lock_wait_valid() {") { print "lock_wait_valid() { return 0; }"; print "lock_wait_valid_unused() {" } else print }' "$SCAN" > "$BYP"
  n_anchor="$(grep -c '^lock_wait_valid() { return 0; }$' "$BYP")"
  FC_RE="$(sed -n "s/^FC_RUN_RE='\(.*\)'\$/\1/p" "$HERE/sca-watch.sh")"
  ABORT_LINE='  SCA GATE (effective, waivers applied): NO-GO — run cut short by a shell error before its verdict, no verdict obtained (fail-closed)'
  if [ "$n_anchor" = 1 ] && [ -n "$FC_RE" ]; then
    ok "(i3) bypass copy built (one anchor), FC_RUN_RE read from sca-watch.sh"
    for form in scan all-modules; do
      r="$(make_root "net-$form")"
      put_owner "$r" "$LIVE" "$HOST" "$LIVE_ST"
      cp "$(rep "$r")/.lock/owner" "$TMP/i3-$form.owner"
      if [ "$form" = scan ]; then
        fg "$r" "$TMP/i3-$form.out" "$TMP/i3-$form.err" 20 LC_ALL=C SCA_LOCK_WAIT_SECONDS=09 PATH="$CLEAN:$PATH" bash "$BYP"
      else
        fg "$r" "$TMP/i3-$form.out" "$TMP/i3-$form.err" 20 LC_ALL=C SCA_LOCK_WAIT_SECONDS=09 PATH="$CLEAN:$PATH" bash "$BYP" --all-modules
      fi
      [ "$FRC" -eq 1 ] && has "$TMP/i3-$form.out" "$ABORT_LINE" \
        && ok "(i3) $form: rc 1, the run-cut-short NO-GO line" \
        || ko "(i3) $form: rc $FRC, $(grep -E 'SCA GATE|module dir' "$TMP/i3-$form.out" | tr '\n' ' ')"
      a3="$(audit_last "$r")"
      [ "$a3" = "mode=$form verdict=NO-GO reason=aborted" ] && ok "(i3) $form: audit row NO-GO aborted" \
        || ko "(i3) $form: audit row [$a3]"
      LC_ALL=C grep -q "$FC_RE" "$TMP/i3-$form.out" && ok "(i3) $form: the line is read by sca-watch's FC_RUN_RE" \
        || ko "(i3) $form: sca-watch's FC_RUN_RE does not read the line"
      [ -d "$(rep "$r")/.lock" ] && cmp -s "$TMP/i3-$form.owner" "$(rep "$r")/.lock/owner" \
        && ok "(i3) $form: the live owner's lock intact" || ko "(i3) $form: the live owner's lock touched"
      grep -Fq 'unbound variable' "$TMP/i3-$form.err" && ko "(i3) $form: 'unbound variable' on the net's exit" \
        || ok "(i3) $form: no 'unbound variable' (LC_ALL=C)"
    done
  else
    ko "(i3) no bypass copy: anchor count [$n_anchor], FC_RUN_RE [$FC_RE]"
    skip "(i3): the net is not exercised without its bypass copy" 10
  fi
fi
if want j; then
  echo "=== (j) a root without sca-reports/ => the lock is taken, the run is normal"
  RJ="$TMP/root-noreports"
  mkdir -p "$RJ/.agents/security"
  printf 'flask==2.0.0\n' > "$RJ/requirements.txt"
  [ ! -d "$RJ/.agents/state/local/sca-reports" ] && ok "(j) witness: no sca-reports/ before the run" || ko "(j) witness: sca-reports/ exists"
  fg "$RJ" "$TMP/j.out" "$TMP/j.err" 30 SCA_LOCK_WAIT_SECONDS=3 PATH="$CLEAN:$PATH" bash "$SCAN"
  [ "$FRC" -eq 0 ] && has "$TMP/j.out" "$GATE_GO" && ok "(j) rc 0 GO" || ko "(j) expected rc 0 GO, got rc $FRC"
  grep -Fq 'waiting up to' "$TMP/j.out" && ko "(j) the run waited for a lock it should have taken" || ok "(j) no wait"
  [ ! -d "$(rep "$RJ")/.lock" ] && [ -s "$(rep "$RJ")/audit-log.jsonl" ] && ok "(j) lock released, audit row written" \
    || ko "(j) lock left or no audit row"
fi
if want k; then
  echo "=== (k) a reports directory the run cannot write, no lock => NO-GO at once, never a wait (closing review T5)"
  RK="$(make_root readonly)"
  chmod 555 "$(rep "$RK")"
  if [ -w "$(rep "$RK")" ]; then
    chmod 755 "$(rep "$RK")"
    skip "(k): sca-reports/ stays writable after chmod 555 (uid 0?) — INERT here" 5
  else
    s_k=$SECONDS
    fg "$RK" "$TMP/k.out" "$TMP/k.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=5 bash "$SCAN"
    el_k=$((SECONDS - s_k))
    chmod 755 "$(rep "$RK")"
    FC_RE_K="$(sed -n "s/^FC_RUN_RE='\(.*\)'\$/\1/p" "$HERE/sca-watch.sh")"
    [ "$FRC" -eq 1 ] && ok "(k) rc 1" || ko "(k) expected rc 1, got $FRC"
    has "$TMP/k.out" "$NOWRITE_LINE" && ok "(k) the not-writable NO-GO line, exact" \
      || ko "(k) the not-writable line is missing: $(tr '\n' '|' < "$TMP/k.out")"
    grep -Fq 'waiting up to' "$TMP/k.out" && ko "(k) the run WAITED, as for a held lock" || ok "(k) no wait"
    [ "$el_k" -le 3 ] && ok "(k) ended in ${el_k}s, before the 5 s wait" || ko "(k) took ${el_k}s — it waited"
    [ -n "$FC_RE_K" ] && LC_ALL=C grep -q "$FC_RE_K" "$TMP/k.out" && ok "(k) the line is read by sca-watch's FC_RUN_RE" \
      || ko "(k) sca-watch's FC_RUN_RE [$FC_RE_K] does not read the line"
  fi
fi
if want l; then
  echo "=== (l) E3: a GO summary dated 2000, a live owner, --all-modules lock-busy => the HTML badge says NO-GO"
  # audit_report.py is the tracked one (HERE): its mutant is replayed on a copy of
  # this suite, see the header (closing review T1).
  RL="$(make_root e3)"
  mkdir -p "$(rep "$RL")/modules"
  printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","root":"","gate_level":"high","modules":[{"slug":"root","path":".","submodules":0,"verdict":"GO","exit_code":0,"gating":true,"reports_dir":".agents/state/local/sca-reports","counters":{"active_at_gate":0}}],"global_verdict":"GO","counters_total":{"active_at_gate":0}}' \
    > "$(rep "$RL")/modules/summary.json"
  put_owner "$RL" "$LIVE" "$HOST" "$LIVE_ST"
  fg "$RL" "$TMP/l.out" "$TMP/l.err" 20 PATH="$CLEAN:$PATH" SCA_LOCK_WAIT_SECONDS=1 bash "$SCAN" --all-modules
  a_l="$(audit_last "$RL")"
  [ "$FRC" -eq 1 ] && [ "$a_l" = "mode=all-modules verdict=NO-GO reason=lock-busy" ] \
    && ok "(l) witness: --all-modules rc 1, its audit row lock-busy" || ko "(l) witness: rc $FRC, audit [$a_l]"
  python3 "$HERE/audit_report.py" --reports-dir "$(rep "$RL")" --project e3 --out "$TMP/l.html" \
    --waivers "$TMP/l-none.json" > /dev/null 2>&1
  grep -Fq "<span class='badge' style='background:#b91c1c'>NO-GO</span>" "$TMP/l.html" 2>/dev/null \
    && ok "(l) the HTML badge says NO-GO" \
    || ko "(l) the HTML badge is not NO-GO: $(grep -o "class='badge'[^<]*" "$TMP/l.html" 2>/dev/null)"
  grep -Fq 'latest run obtained NO verdict (lock-busy, ' "$TMP/l.html" 2>/dev/null \
    && ok "(l) the page says the latest run obtained NO verdict" || ko "(l) the no-verdict line is missing"
fi

# ---- (d2)/(d2b) judged now ------------------------------------------------------------------
if [ "$D2_ON" = 1 ]; then
  echo "=== (d2)/(d2b)/(d2c) an owner-less lock REPLACED at t0+15 => the grace restarts"
  wait "$PD2"
  wait "$PD2B"
  wait "$PD2C"
  for n in d2 d2b d2c; do
    s47=missing; tk=none; rc=none
    [ -f "$TMP/$n.res" ] && read -r s47 tk rc < "$TMP/$n.res"
    [ "$s47" = present ] && ok "($n) the new lock's sentinel is still there at t0+47" \
      || ko "($n) sentinel [$s47] at t0+47 — the replacement was stolen on the OLD lock's grace"
    case "$tk" in
      ''|*[!0-9]*) ko "($n) never taken over (tk=$tk) — the grace never ran out" ;;
      *)
        if [ "$tk" -ge 52 ] && [ "$tk" -le 66 ]; then ok "($n) taken over at t0+${tk}s, in [52, 66]"
        else ko "($n) taken over at t0+${tk}s, outside [52, 66]"; fi
        ;;
    esac
    [ "$rc" = 0 ] && ok "($n) the waiter completes, rc 0" || ko "($n) the waiter rc [$rc]"
  done
elif [ -n "$ONLY" ]; then
  :
fi

# ---- THE COUNT ARM ----------------------------------------------------------------------------
# `passed + failed + skipped_arms + 1` — arms that RAN, whatever their verdict, plus
# this one, against an EXACT constant: an arm that stops running goes RED here.
EXPECT_ARMS=177
if [ -n "$ONLY" ]; then
  echo "  (count arm not judged under SCA_LOCK_TEST_ARMS)"
else
  ARMS_RUN=$((passed + failed + skipped_arms + 1))
  [ "$ARMS_RUN" -eq "$EXPECT_ARMS" ] \
    && ok "count: $ARMS_RUN arms ran, EXPECT_ARMS=$EXPECT_ARMS ($passed ok / $failed KO / $skipped_arms suppressed by a NAMED skip)" \
    || ko "count: $ARMS_RUN arms ran but EXPECT_ARMS=$EXPECT_ARMS ($passed ok / $failed KO / $skipped_arms skipped)"
fi

echo
echo "sca-scan-lock: $passed passed / $failed failed / $skipped_arms arms skipped (named)"
[ "$failed" -eq 0 ]
