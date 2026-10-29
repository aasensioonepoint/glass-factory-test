#!/usr/bin/env bash
# Suite for the FAIL-CLOSED effective gate of sca-scan.sh (T-01M4X6FJG4XZ3ZN2BJCVVEMGXY).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. Every case runs the REAL
# dispatcher against a disposable fixture root. ZERO network: the findings come
# from a STUB `pip-audit` on the PATH, never from the real tool.
#
# THE DEFECT (class 1, measured before the fix): `SCA_GATE_LEVEL=medium` made
# waiver_filter.py die in argparse (rc 2) WITHOUT writing effective-verdict.json;
# sca-scan.sh only ever tested `gate = 1`, so it printed
# `SCA GATE (effective, waivers applied): GO` and exited 0 on 19 known HIGH,
# leaving the PREVIOUS run's pivot in place to be read as today's.
#
# THE RULE UNDER TEST: the pivot is FRESH only when waiver_filter returned 0 or 1
# AND printed its `SUMMARY ` line (printed after the write). Anything else, with
# Python present: exit 1, stale pivot REMOVED, reason named in .degraded and in
# the `COVERAGE DEGRADED:` banner. With Python ABSENT (rectified decision,
# « DEGRADED VISIBLE »): never a block, exit code as before, BUT the stale pivot
# is removed and `waiver_filter: not run (python absent)` reaches .degraded and
# the banner — before this revision the run was a mute GO, "PYTHON 3 NOT FOUND"
# on stderr its only signal (measured).
#
#   (1)  SCA_GATE_LEVEL=medium, real waiver_filter, stub HIGH       -> rc 1
#   (1b) hostile SCA_GATE_LEVEL (ESC, `;`, `:`) -> neutralised in the line
#   (2)  stub waiver_filter: exit 2, writes nothing, stale GO pivot -> rc 1,
#        pivot GONE, `.degraded` and the banner name it
#   (3)  stub waiver_filter: exit 0, no SUMMARY                     -> rc 1
#   (4a) non-regression: clean findings                             -> rc 0, fresh pivot
#   (4b) non-regression: a HIGH finding                             -> rc 1, no fail-closed line
#   (5)  stub waiver_filter: prints SUMMARY then exit 3             -> rc 1
#   (6)  Python ABSENT + a manifest + stale pivot -> rc 0 (not a block), pivot
#        GONE, `.degraded` and the banner say "python absent", the last line is
#        `GO (DEGRADED — no effective verdict)` (never a bare `GO`) and the audit
#        row PARSES with `"verdict":"DEGRADED"` (decision S-01M4X99ZY9); and the
#        dispatcher EXECUTES no empty command: `"$PY" …` with PY="" made the
#        bash-tests runner log `MISSING DEP (cmd: ?)` on a 40/40 run (2026-10-14)
#   (2), (4a) the audit row PARSES as JSON: an empty summary used to leave
#        `"gate_level":"high",""}`, a row dashboard_readers counts `malformed`
#   (7)  bare form, SCA_GATE_LEVEL carrying a newline and a forged GO row -> ONE
#        row appended, it PARSES, NO-GO, no `"ts":"forged"` in the log
#        (T-01M4XF9HVVSB16Q2N1M1ZX2MTX, decision S-01M4XWS69W13H8ZATG6PT03W0A)
#   (7b) the same vector under --all-modules (one `sub/` module) -> modules + 1
#        rows, none forged, none parsed GO, the LAST one all-modules NO-GO
#   (7c) a bare `"` vector (a duplicated `verdict` key: the last one wins), bare
#        form AND --all-modules -> every appended row parses NO-GO
#   (7d) a module directory named `mod"x` -> the row parses, module `mod?x`
#   (8)  --all-modules with Python ABSENT, a stale pivot, summary.json and a
#        stale `.degraded` reason seeded -> rc 0, all three gone, the banner
#        names the discovery, the last line and the audit row say DEGRADED,
#        never `no known ecosystem`, no empty command executed
#        (T-01M4XF9JQXK6QJHHBFQZX7AGAJ, decision S-01M4XWS634J9QWVP7EZPTT2C8Y)
#   (9)  uv.lock alone + Python ABSENT -> `.degraded` says the lock was NOT READ
#        (python absent), never `illisible` nor `rc=127`, no empty command
#   (10) stale reports of tools that did NOT run (npm-audit.json TRUNCATED, a
#        READABLE dependency-check CRITICAL, socket and trivy-config truncated)
#        -> purged before the tools: GO, all four gone, today's pip-audit.json
#        kept (reserve C5). The readable CRITICAL is what reddens the purge
#        mutant whatever waiver_filter does with an unreadable report.
#   (10b) trivy-image.json — written by a project's image-scan step, never by
#        sca-scan.sh — is NOT purged: its CRITICAL still gates, rc 1
#   (11) --all-modules, the module run of `sub` KILLED (SIGKILL, rc 137) -> rc 1,
#        the module line `… NO-GO — module sub exited rc=137, no verdict obtained
#        (fail-closed)`, summary.json NO-GO with `sub` ERROR and gating, the last
#        audit row all-modules NO-GO (T-01M4Z395686TR4M7326AQ8ZPHW; measured
#        before: rc 0, GO, summary GO [('sub','ERROR',137)])
#   (11b) a bare `exit 3` in that module run -> ERROR, rc 1 (it used to read
#        TRACKED-NOT-GATING, GO)
#   (11c) non-regression: a PROTECTED module's real NO-GO -> TRACKED-NOT-GATING,
#        not gating, GO rc 0
#   (11d) a killed module whose directory holds an EARLIER pivot (active 7) ->
#        that pivot REMOVED, `counters {}`, counters_total without the 7
#   (11e) a bare `exit 2` -> ERROR, rc 1 (it used to read NO-ECOSYSTEM)
#   (11f) non-regression: the no-ecosystem line + exit 2 -> NO-ECOSYSTEM, GO rc 0
#   (11g) a PROTECTED module whose run forgets SCA_LOCK_OWNER, so it waits for its
#        own parent's lock and ends lock-busy (a raw 1, no verdict obtained), over
#        an EARLIER pivot (active 7) -> rc 1, ERROR, gating, `counters {}`, no
#        protected substitution, the pivot LEFT (closing review T2, scenario E2;
#        measured before: TRACKED-NOT-GATING, c=7, GO rc 0)
#   (11h) a PROTECTED module whose pip-audit.json is truncated (waiver_filter rc 3,
#        a raw 1) -> rc 1, ERROR, gating, `counters {}`, its own line `… NO-GO —
#        module sub: no fresh effective verdict (fail-closed)`, never the
#        `exited rc=1, no verdict obtained` line, no protected substitution (E1,
#        T-01M51RFFECAFAAR0CM3NR1GYEC; measured before: TRACKED-NOT-GATING, GO rc 0)
#   (11i) a PROTECTED module's raw 1 (a real HIGH) whose module log could not be
#        created (a `mktemp` stub refusing `.modlog.`) -> rc 1, ERROR, gating, no
#        protected substitution (security review MEDIUM; measured before:
#        TRACKED-NOT-GATING c=1, GO rc 0)
#   (11j) PINNED: a PROTECTED module whose waiver_filter answers rc 2
#        (SCA_GATE_LEVEL=medium) -> TRACKED-NOT-GATING, not gating, GO rc 0, no
#        rc 3 module line (the branch « non » of the plan's blind spot)
#   The module runs are driven through BASH_ENV: a file sourced by EVERY bash of
#   the run, whose one-shot DEBUG trap acts only where `$1` is `sub` — the module
#   run itself; the dispatcher, the --all-modules loop and the pip-audit stub
#   pass through it (why a DEBUG trap: see crash_env, measured under 3.2).
#
# The former BOUND of this header (--all-modules without Python not measured)
# is CLOSED by (8): that path now has a branch of its own, measured here.
# BOUND (8), (9): the empty-command sensor needs bash >= 4; under bash < 4 the
# arms fall back on the stderr text, plus their TEXT witnesses (NO-ECOSYSTEM,
# `illisible`, `rc=127`), which go red under both.
#
# MUTATIONS THAT MUST TURN THIS SUITE RED (L-00000343), each applied to a COPY of
# sca-scan.sh in a scratch tree, never to the tracked file:
#   M1 `gate=1` removed                           -> (1), (1b), (2), (3), (5) RED
#   M2 `rm -f` of the stale pivot removed         -> (1), (2), (3), (6) RED
#   M3 rc test removed (`if true; then`)          -> (5) RED
#   M4 SUMMARY test removed (`*) pivot_fresh=1`)  -> (3) RED
#   M5 sanitize_display dropped from the message  -> (1b) RED
#   M6 `if [ -n "$PY" ]` made `if true`           -> (6) RED (Python absent blocks)
#   M7 the fail-closed `.degraded` line removed   -> (2) RED
#   M8 the python-absent `.degraded` line removed -> (6) RED
#   M9 the DEGRADED final line prints a bare `GO` -> (6) RED
#   M10 the audit verdict never becomes DEGRADED  -> (6) RED
#   M11 the old audit form (`,"%s"}` on an empty summary) -> (2), (6) RED
#   M12a the `[ -n "$PY" ]` guard of module discovery made `if true`  -> (6) RED
#   M12b the `[ -n "$PY" ]` guard of waiver_filter made `if true`     -> (6) RED
#   MB1 raw `$GATE_LEVEL` in the single-module audit printf  -> (7), (7c) RED
#   MB2 raw `$GATE_LEVEL` in the --all-modules audit printf   -> (7b), (7c) RED
#   MB3 the python-absent branch of --all-modules made `if false` -> (8) RED
#   MB4 that branch made `if false` AND a naive `[ -n "$PY" ] &&` put before
#       module discovery -> (8) RED at the VERDICT, the sensor green
#   MB5 the python-absent branch of the lock block made `if false` -> (9) RED
#   MB6 the `rm -f` of the two verdict files of (8)'s branch removed -> (8) RED
#   MB7 raw `$SLUG` in the single-module audit printf        -> (7d) RED
#   MB8 the `.degraded` reset of (8)'s branch removed (C2)   -> (8) RED
#   MB9 the purge of the scanner reports removed (C5)        -> (10) RED
#   MB10 trivy-image.json added to that purge                -> (10b) RED
#   MB5b the `[ -n "$PY" ]` guard of the py_lock_pins call made `if true` -> (9) RED
#       through the sensor only (bash >= 4)
#   MUTANTS OF THE MODULE RC (plan T-01M4Z33N54TX0Q7VHBZATFNR4X rév. 4, named
#   MB1-MB6 THERE — a namespace distinct from MB1-MB10 above):
#   MB1 the module error no longer raises `global`       -> (11)(11b)(11d)(11e) RED
#   MB2 a raw 3 read as the protected substitution       -> (11b) RED
#   MB3 `glob_ng` blind to the error flag                -> summary of (11)(11b)(11d)(11e) RED
#   MB4 the module line removed                          -> (11)(11b)(11e) RED
#   MB5 the pivot of the module in error kept            -> (11d) RED
#   MB6 a 2 accepted without the no-ecosystem line       -> (11e) RED
#   MB7 the `no verdict obtained` test of a raw 1 removed -> (11g) RED (closing review T2)
#   MB8 the pivot removed under a raw 1 too (`rc != "1"`) -> (11g) RED, the pivot line
#   MB9 the `waiver_filter rc=3, ` test of a raw 1 removed -> (11h) RED (E1); (11c) green
#   MB10 the empty-module-log test of a raw 1 removed -> (11i) RED
#   MB11 the rc 3 anchor widened to any rc (`waiver_filter rc=`) -> (11j) RED
#   REPLAYED 2026-10-16 (closing-review pass), same method, sandbox-exec without
#   network: control 124/124 under bash 5.3.15 AND 3.2.57; MB7 4 KO (rc 0, GO,
#   TRACKED-NOT-GATING — the measured defect), MB8 1 KO — the same under both.
#   REPLAYED 2026-10-16 through SCA_SCAN_UNDER_TEST (below), each applied by an
#   exact-once replacement on a copy, checked by `cmp` and parsed under both
#   bashes: control 118/118 under bash 5.3.15 AND 3.2.57 (`bash` on PATH =
#   /bin/bash); MB1 6 KO, MB2 3 KO, MB3 4 KO, MB4 3 KO, MB5 1 KO, MB6 3 KO —
#   the same counts under both.
# Replay of the plan's mutants: SCA_SCAN_UNDER_TEST=<mutated copy> on this
# in-tree suite (the python siblings still come from HERE).
# Replay: copy this file, sca-scan.sh and the four .py siblings it calls into one
# scratch directory, mutate the copy, run the copied suite (HERE resolves there).
# A mutant must still PARSE: deleting the only line of a branch leaves an empty
# `else` (syntax error, measures nothing) — replace it with `:` instead.
# REPLAYED, not asserted (2026-10-14, after the DEGRADED-final-line revision,
# suite and dispatcher under bash 5.3.15; each mutation checked to have APPLIED,
# by `cmp`, and to parse, before its run). Observed: control 40/40; M1 8 KO, the
# rc/verdict assertions of (1), (1b), (2), (3), (5) and the audit verdict of
# (2); M2 4 KO, the pivot assertions of (1), (2), (3), (6); M3 2 KO, (5) alone;
# M4 3 KO, (3) alone; M5 1 KO, (1b) alone; M6 6 KO, (6) alone; M7 2 KO, (2)
# alone; M8 2 KO, (6) alone (.degraded and banner); M9 2 KO, (6) final line;
# M10 3 KO, (6) final line and audit verdict; M11 2 KO, the audit rows of (2)
# and (6) UNPARSABLE. The pre-revision sca-scan.sh: 4 KO, (2) audit row
# unparsable, (6) final line, bare GO and audit row.
# M12 REPLAYED the same way (2026-10-14, same method). Under bash 5.3: control
# 41/41; M12a 1 KO, M12b 1 KO, both together 1 KO listing `[] []` — the (6)
# empty-command line alone. Under bash 3.2 (`bash` on PATH = /bin/bash), where
# the sensor is absent and the stderr text answers: control 41/41, M12b 1 KO,
# M12a GREEN — the stated BOUND (discovery's stderr goes to /dev/null).
# MB1-MB10 and MB5b REPLAYED the same way (2026-10-14, T-01M4XF9HVVSB16Q2N1M1ZX2MTX
# and T-01M4XF9JQXK6QJHHBFQZX7AGAJ; each applied by an exact-once replacement,
# checked by `cmp` and `bash -n`). Under bash 5.3.15: control 93/93; MB1 8 KO,
# (7) row count, row and forged ts, (7b) count, forged and GO rows, (7c) both
# forms; MB2 5 KO, (7b) count, forged, GO and last row, (7c) --all-modules;
# MB3 9 KO, (8) rc 2, NO-ECOSYSTEM, both verdict files, banner, last line,
# audit row and the `[]` sensor; MB4 8 KO, the same (8) assertions minus the
# sensor (green, as the plan predicted); MB5 3 KO, (9) .degraded line and the
# two `illisible` witnesses; MB5b 1 KO, (9) sensor; MB6 2 KO, (8) the two
# verdict files; MB7 1 KO, (7d) UNPARSABLE; MB8 2 KO, (8) the stale reason in
# the banner and in .degraded; MB9 7 KO, (10) rc, GO, the four stale reports
# and the pivot count; MB10 4 KO, (10b) rc, NO-GO, the purged report and the
# pivot count. Under bash 3.2.57 (`bash` on PATH = /bin/bash): control 93/93;
# MB3 9 KO (the stderr text replaces the sensor: discovery's stderr is not
# redirected); MB5 3 KO; MB5b GREEN — the stated BOUND (py_lock_pins' stderr
# goes to py-locks.log, so no text reaches the output).
#
# FORM (bash 3.2 floor): no heredoc at all; `grep -F`/`-Fx` wherever a literal
# is pinned; `rc` captured on the line that follows the command. No SKIP: python3
# is class B in core-scripts/tool-inventory.tsv, its absence reddens arms here.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TMP="$(mktemp -d)"
# REFUSE a degenerate workspace root (same guard as sca-python.test.sh): an empty
# $TMP would make every `mkdir -p "$TMP/x"` write at `/x`.
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

# Hermetic: an inherited knob would change what every arm measures.
unset SCA_GATE_LEVEL SCA_CHANGED_ONLY SCA_ROOT_ONLY AGENTS_HOOK_HOST
unset SCA_LOCK_WAIT_SECONDS SCA_LOCK_OWNER BASH_ENV

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# MUTATION REPLAY. `SCA_SCAN_UNDER_TEST` is read HERE and nowhere else (no
# production site reads it): it names the dispatcher copied into the private kit
# below, in place of the tracked one. Announced on its own line, so that a green
# obtained under it can never read as a green of the tracked file.
SCAN_SRC="${SCA_SCAN_UNDER_TEST:-$HERE/sca-scan.sh}"
if [ -n "${SCA_SCAN_UNDER_TEST:-}" ]; then
  echo "MUTATION REPLAY — under test: $SCAN_SRC (NOT the tracked sca-scan.sh)"
fi

# A PRIVATE copy of the dispatcher and the python siblings it resolves from its
# own SCRIPT_DIR: arms (2), (3) and (5) replace waiver_filter.py in it.
KIT="$TMP/kit"
mkdir -p "$KIT"
cp "$SCAN_SRC" "$KIT/sca-scan.sh" || { echo "FATAL: cannot copy $SCAN_SRC into the private kit"; exit 2; }
for f in waiver_filter.py protected_module.py module_discovery.py py_lock_pins.py; do
  cp "$HERE/$f" "$KIT/$f" || { echo "FATAL: cannot copy $f into the private kit"; exit 2; }
done
SCAN="$KIT/sca-scan.sh"
real_wf() { cp "$HERE/waiver_filter.py" "$KIT/waiver_filter.py"; }
stub_wf() { printf '%s\n' "$1" > "$KIT/waiver_filter.py"; }

# Two pip-audit stubs: a boxed HIGH (exit 1, like the real tool on a finding) and
# a clean report (exit 0).
HIGHBIN="$TMP/stub-high"
CLEANBIN="$TMP/stub-clean"
NOPYBIN="$TMP/stub-nopy"
mkdir -p "$HIGHBIN" "$CLEANBIN" "$NOPYBIN"
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"aliases":["CVE-2023-30861"],"severity":"HIGH","description":"boxed"}]}],"fixes":[]}'"'" \
  'exit 1' > "$HIGHBIN/pip-audit"
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[]}],"fixes":[]}'"'" \
  'exit 0' > "$CLEANBIN/pip-audit"
# Python ABSENT: both names the dispatcher probes answer nothing and fail, so its
# probe leaves PY empty (Darwin/Linux never try `py -3`).
printf '%s\n' '#!/bin/sh' 'exit 1' > "$NOPYBIN/python3"
printf '%s\n' '#!/bin/sh' 'exit 1' > "$NOPYBIN/python"
chmod +x "$HIGHBIN/pip-audit" "$CLEANBIN/pip-audit" "$NOPYBIN/python3" "$NOPYBIN/python"

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for ROOT.
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf 'flask==2.0.0\n' > "$r/requirements.txt"
  echo "$r"
}
report_dir() { echo "$1/.agents/state/local/sca-reports"; }

# The pivot an EARLIER run left behind — a GO, marked so a rewrite is visible.
seed_pivot() {
  printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","gate_level":"high","active":[],"waived_accepted":[],"waived_pending":[],"counters":{"active_at_gate":0,"accepted":0,"pending_review":0,"overdue_review":0},"notes":["SEEDED-STALE"]}' \
    > "$(report_dir "$1")/effective-verdict.json"
}

# The exact fail-closed line for waiver_filter rc $1 at gate level $2.
fc_line() {
  printf '  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=%s, gate_level=%s, no fresh effective verdict (fail-closed)' "$1" "$2"
}
FC_TAIL='no fresh effective verdict (fail-closed)'
GATE_NOGO='SCA GATE (effective, waivers applied): NO-GO'
GATE_GO='SCA GATE (effective, waivers applied): GO'
GATE_DEG='SCA GATE (effective, waivers applied): GO (DEGRADED — no effective verdict)'

# The LAST audit row of a fixture root, PARSED by python3 (the harness has
# Python; only the dispatcher is run without it in (6)). Prints
# `verdict=<v> active=<n|->`, or `UNPARSABLE` when the row is not JSON — the
# exact fate of a row in dashboard_readers, which counts it `malformed`.
audit_last() {
  python3 -c 'import json, sys
rows = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
try:
    rec = json.loads(rows[-1])
except Exception:
    print("UNPARSABLE")
    sys.exit(0)
print("verdict=%s active=%s" % (rec.get("verdict"), rec.get("active", "-")))' \
    "$(report_dir "$1")/audit-log.jsonl" 2>/dev/null || echo "UNREADABLE"
}

# EMPTY-COMMAND SENSOR, for arm (6). Called INSIDE a subshell only, never in this
# shell: the handler it exports reaches the dispatcher run of that subshell and
# nothing else, so core-scripts/run-bash-tests.sh keeps its own sensor on every
# other arm. It logs `[<name>]` for each command bash could not resolve — an
# EMPTY name included (`[]`), which is what `"$PY" …` with PY="" executes — and
# reproduces bash's message in English whatever the locale (bash 5 under a
# French locale prints `commande introuvable`, measured).
nf_sensor_on() {
  command_not_found_handle() {
    printf '[%s]\n' "${1-}" >>"${NF_LOG:-/dev/null}"
    printf 'bash: %s: command not found\n' "${1-}" >&2
    return 127
  }
  export -f command_not_found_handle
}

# A root whose ONLY module is `sub/` (a requirements.txt, nothing at the root):
# module discovery answers exactly one row, `sub<TAB>sub<TAB>0<TAB>` (measured).
make_mod_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports" "$r/sub"
  printf 'flask==2.0.0\n' > "$r/sub/requirements.txt"
  echo "$r"
}
# A root carrying a HEALTHY uv.lock and no other Python manifest.
make_lock_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf '%s\n' 'version = 1' 'requires-python = ">=3.11"' '' '[[package]]' \
    'name = "flask"' 'version = "2.0.0"' 'source = { registry = "https://pypi.org/simple" }' \
    > "$r/uv.lock"
  echo "$r"
}
GATE_DEG_ALL='SCA GATE all-modules (effective, waivers applied): GO (DEGRADED — no effective verdict)'

# Rows in a fixture root's audit log, by NEWLINE (what a JSONL reader splits
# on); 0 when the log does not exist yet.
audit_count() {
  local f
  f="$(report_dir "$1")/audit-log.jsonl"
  if [ -f "$f" ]; then grep -c '' "$f"; else echo 0; fi
}
# Every row appended AFTER the first $2 rows, one output line each, PARSED by
# python3 like dashboard_readers does (a duplicated key: the last one wins):
# `mode=<m> verdict=<v> module=<m|-> ts=<real|forged>`, or `UNPARSABLE`.
audit_new() {
  python3 -c 'import json, sys
rows = open(sys.argv[1], encoding="utf-8").read().split("\n")
if rows and rows[-1] == "":
    rows.pop()
for l in rows[int(sys.argv[2]):]:
    try:
        rec = json.loads(l)
    except Exception:
        print("UNPARSABLE")
        continue
    print("mode=%s verdict=%s module=%s ts=%s" % (rec.get("mode"), rec.get("verdict"),
          rec.get("module", "-"), "forged" if rec.get("ts") == "forged" else "real"))' \
    "$(report_dir "$1")/audit-log.jsonl" "$2" 2>/dev/null || echo "UNREADABLE"
}

# ---- (1) SCA_GATE_LEVEL=medium: the measured defect --------------------------
echo "=== (1) SCA_GATE_LEVEL=medium, real waiver_filter, stub HIGH => rc 1, fail-closed"
real_wf
R1="$(make_root lvl-medium)"
seed_pivot "$R1"
O1="$(cd "$R1" && SCA_GATE_LEVEL=medium PATH="$HIGHBIN:$PATH" bash "$SCAN" 2>&1)"
rc1=$?
[ "$rc1" -eq 1 ] && ok "(1) rc 1 under SCA_GATE_LEVEL=medium" || ko "(1) expected rc 1, got $rc1"
grep -Fxq -- "$(fc_line 2 medium)" <<<"$O1" \
  && ok "(1) the fail-closed line names rc 2 and the level" \
  || ko "(1) fail-closed line missing or different"
grep -Fxq -- "$GATE_NOGO" <<<"$O1" && ok "(1) final verdict NO-GO" || ko "(1) final verdict is not NO-GO"
[ ! -f "$(report_dir "$R1")/effective-verdict.json" ] \
  && ok "(1) the stale pivot was removed" || ko "(1) a stale effective-verdict.json is still in place"
# Non-vacuity: rc 2 really came from argparse, i.e. from the level, not a stub.
grep -Fq "invalid choice: 'medium'" <<<"$O1" \
  && ok "(1) witness: waiver_filter refused the level in argparse" \
  || ko "(1) witness: no argparse refusal — some other path was measured"

# ---- (1b) hostile level: only sanitized bytes reach the line -----------------
echo "=== (1b) hostile SCA_GATE_LEVEL => the fail-closed line carries it neutralised"
HOSTILE="$(printf 'x\033[2K; go: scanned')"
R1B="$(make_root lvl-hostile)"
O1B="$(cd "$R1B" && SCA_GATE_LEVEL="$HOSTILE" PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc1b=$?
[ "$rc1b" -eq 1 ] && ok "(1b) rc 1 on an unknown level" || ko "(1b) expected rc 1, got $rc1b"
grep -Fxq -- "$(fc_line 2 'x??2K? go? scanned')" <<<"$O1B" \
  && ok "(1b) ESC, ';' and ':' land as '?' in the fail-closed line" \
  || ko "(1b) the fail-closed line is missing or carries raw level bytes"

# ---- (2) waiver_filter exits 2, writes nothing, a stale GO pivot is in place --
echo "=== (2) stub waiver_filter rc 2 + stale GO pivot => rc 1, pivot removed, reason named"
stub_wf 'import sys
sys.exit(2)'
R2="$(make_root wf-rc2)"
seed_pivot "$R2"
[ -f "$(report_dir "$R2")/effective-verdict.json" ] \
  && ok "(2) witness: the stale pivot is in place before the run" \
  || ko "(2) witness: could not seed the stale pivot"
O2="$(cd "$R2" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc2=$?
[ "$rc2" -eq 1 ] && ok "(2) rc 1 when waiver_filter exits 2" || ko "(2) expected rc 1, got $rc2"
grep -Fxq -- "$(fc_line 2 high)" <<<"$O2" \
  && ok "(2) the fail-closed line is printed" || ko "(2) fail-closed line missing or different"
[ ! -f "$(report_dir "$R2")/effective-verdict.json" ] \
  && ok "(2) the stale pivot is GONE" || ko "(2) the stale pivot survived the fail-closed run"
grep -Fxq 'waiver_filter: no fresh effective verdict (rc 2)' "$(report_dir "$R2")/.degraded" 2>/dev/null \
  && ok "(2) .degraded names the missing verdict" || ko "(2) .degraded lacks the waiver_filter line"
grep '^  COVERAGE DEGRADED:' <<<"$O2" | grep -Fq 'waiver_filter: no fresh effective verdict (rc 2)' \
  && ok "(2) the COVERAGE DEGRADED banner names it" || ko "(2) the banner does not name it"
grep -Fxq -- "$GATE_NOGO" <<<"$O2" && ok "(2) final verdict NO-GO" || ko "(2) final verdict is not NO-GO"
[ -s "$(report_dir "$R2")/pip-audit.json" ] \
  && ok "(2) witness: the python path really ran (pip-audit.json present)" \
  || ko "(2) witness: pip-audit.json missing — the gate was not reached by the python path"
A2="$(audit_last "$R2")"
[ "$A2" = "verdict=NO-GO active=-" ] \
  && ok "(2) the audit row PARSES, verdict NO-GO, no counter invented" \
  || ko "(2) expected [verdict=NO-GO active=-] from the audit row, got [$A2]"

# ---- (3) waiver_filter exits 0 but never prints SUMMARY ----------------------
echo "=== (3) stub waiver_filter rc 0 without SUMMARY => rc 1"
stub_wf 'import sys
sys.exit(0)'
R3="$(make_root wf-nosummary)"
seed_pivot "$R3"
O3="$(cd "$R3" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc3=$?
[ "$rc3" -eq 1 ] && ok "(3) rc 1 when SUMMARY is missing" || ko "(3) expected rc 1, got $rc3"
grep -Fxq -- "$(fc_line 0 high)" <<<"$O3" \
  && ok "(3) the fail-closed line names rc 0" || ko "(3) fail-closed line missing or different"
[ ! -f "$(report_dir "$R3")/effective-verdict.json" ] \
  && ok "(3) the stale pivot is GONE" || ko "(3) the stale pivot survived"

# ---- (5) waiver_filter prints SUMMARY then exits 3 ---------------------------
echo "=== (5) stub waiver_filter prints SUMMARY then rc 3 => rc 1"
stub_wf 'import sys
print("SUMMARY active=0 accepted=0 pending=0 overdue=0")
sys.exit(3)'
R5="$(make_root wf-rc3)"
O5="$(cd "$R5" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc5=$?
[ "$rc5" -eq 1 ] && ok "(5) rc 1 on SUMMARY + rc 3" || ko "(5) expected rc 1, got $rc5"
grep -Fxq -- "$(fc_line 3 high)" <<<"$O5" \
  && ok "(5) the fail-closed line names rc 3" || ko "(5) fail-closed line missing or different"
grep -Fq '  SUMMARY active=0 accepted=0 pending=0 overdue=0' <<<"$O5" \
  && ok "(5) witness: the stub's SUMMARY reached the dispatcher" \
  || ko "(5) witness: the stub's SUMMARY was not read — some other path was measured"

# ---- (4) non-regression: the two verdicts waiver_filter really gives ---------
echo "=== (4a) real waiver_filter, clean findings => rc 0, fresh pivot"
real_wf
R4A="$(make_root clean)"
seed_pivot "$R4A"
O4A="$(cd "$R4A" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc4a=$?
[ "$rc4a" -eq 0 ] && ok "(4a) rc 0 on a clean scan" || ko "(4a) expected rc 0, got $rc4a"
grep -Fxq -- "$GATE_GO" <<<"$O4A" && ok "(4a) final verdict GO" || ko "(4a) final verdict is not GO"
grep -Fq -- "$FC_TAIL" <<<"$O4A" && ko "(4a) fail-closed fired on a clean scan" || ok "(4a) no fail-closed line"
P4A="$(report_dir "$R4A")/effective-verdict.json"
[ -f "$P4A" ] && ! grep -Fq 'SEEDED-STALE' "$P4A" \
  && ok "(4a) the pivot was REWRITTEN by this run" || ko "(4a) the pivot is absent or still the stale one"
A4A="$(audit_last "$R4A")"
[ "$A4A" = "verdict=GO active=0" ] \
  && ok "(4a) the audit row PARSES and still carries the SUMMARY counters" \
  || ko "(4a) expected [verdict=GO active=0] from the audit row, got [$A4A]"

echo "=== (4b) real waiver_filter, a HIGH finding => rc 1, NO-GO, no fail-closed line"
R4B="$(make_root high)"
O4B="$(cd "$R4B" && PATH="$HIGHBIN:$PATH" bash "$SCAN" 2>&1)"
rc4b=$?
[ "$rc4b" -eq 1 ] && ok "(4b) rc 1 on a HIGH" || ko "(4b) expected rc 1, got $rc4b"
grep -Fxq -- "$GATE_NOGO" <<<"$O4B" && ok "(4b) final verdict NO-GO" || ko "(4b) final verdict is not NO-GO"
grep -Fq -- "$FC_TAIL" <<<"$O4B" && ko "(4b) fail-closed fired on a real finding" || ok "(4b) no fail-closed line"
grep -Fq '"active_at_gate": 1' "$(report_dir "$R4B")/effective-verdict.json" 2>/dev/null \
  && ok "(4b) the fresh pivot counts the finding" || ko "(4b) the pivot does not count the finding"

# ---- (6) Python ABSENT: DEGRADED, announced, never a block --------------------
echo "=== (6) Python absent + a manifest + stale pivot => rc 0, pivot removed, DEGRADED announced"
R6="$(make_root nopy)"
seed_pivot "$R6"
NF6="$TMP/notfound-6.log"
NFP="$TMP/notfound-probe.log"
: >"$NF6"
: >"$NFP"
# Non-vacuity of the sensor, through the SAME `bash` that runs the dispatcher:
# bash < 4 has no command_not_found_handle and would log nothing, ever.
( nf_sensor_on; NF_LOG="$NFP" bash -c '""' ) >/dev/null 2>&1
O6="$(nf_sensor_on; cd "$R6" && NF_LOG="$NF6" PATH="$NOPYBIN:$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc6=$?
grep -Fq 'PYTHON 3 NOT FOUND' <<<"$O6" \
  && ok "(6) witness: the dispatcher really found no Python" \
  || ko "(6) witness: Python was still found — this arm measures nothing"
# With PY empty the dispatcher used to EXECUTE `"$PY" …` — an empty command — at
# module discovery (stderr to /dev/null) and at waiver_filter: the runner logged
# `MISSING DEP (cmd: ?)` and the run went red on a 40/40 suite (2026-10-14).
if grep -Fxq '[]' "$NFP"; then
  [ ! -s "$NF6" ] \
    && ok "(6) every command the dispatcher ran resolved — no empty \"\$PY\" executed" \
    || ko "(6) the dispatcher executed unresolved command(s) $(tr '\n' ' ' <"$NF6")— an empty \"\$PY\" ran"
else
  # BOUND: bash < 4. Only the stderr text remains, and it cannot see the
  # discovery site, whose stderr goes to /dev/null.
  grep -Fq 'command not found' <<<"$O6" \
    && ko "(6) the output says 'command not found' — an empty \"\$PY\" ran (bash < 4: stderr only)" \
    || ok "(6) no 'command not found' in the output (BOUND: bash < 4, discovery site unseen)"
fi
[ "$rc6" -eq 0 ] && ok "(6) rc 0, never a block" || ko "(6) expected rc 0 (not a block), got $rc6"
grep -Fq -- "$FC_TAIL" <<<"$O6" && ko "(6) fail-closed fired without Python" || ok "(6) no fail-closed line"
[ ! -f "$(report_dir "$R6")/effective-verdict.json" ] \
  && ok "(6) the stale pivot is GONE" || ko "(6) the stale pivot survived a run where waiver_filter never ran"
grep -Fxq 'waiver_filter: not run (python absent)' "$(report_dir "$R6")/.degraded" 2>/dev/null \
  && ok "(6) .degraded says python absent" || ko "(6) .degraded lacks the python-absent line"
grep '^  COVERAGE DEGRADED:' <<<"$O6" | grep -Fq 'waiver_filter: not run (python absent)' \
  && ok "(6) the COVERAGE DEGRADED banner names it" || ko "(6) the banner does not name it — a mute GO"
grep -Fxq -- "$GATE_DEG" <<<"$O6" \
  && ok "(6) the last line says GO (DEGRADED — no effective verdict)" \
  || ko "(6) the DEGRADED final line is missing"
grep -Fxq -- "$GATE_GO" <<<"$O6" \
  && ko "(6) a bare final GO was printed without an effective verdict" \
  || ok "(6) no bare final GO"
A6="$(audit_last "$R6")"
[ "$A6" = "verdict=DEGRADED active=-" ] \
  && ok "(6) the audit row PARSES with verdict DEGRADED" \
  || ko "(6) expected [verdict=DEGRADED active=-] from the audit row, got [$A6]"

# ---- (7) the audit row cannot be forged through the level (bare form) --------
# Measured before the fix: this vector appended TWO valid JSON rows, the real
# NO-GO and then `{"ts":"forged",…,"verdict":"GO"}` — the LAST row read was a GO.
echo "=== (7) bare form, a level carrying a newline + a forged GO row => ONE row, it parses, NO-GO"
real_wf
FORGE_NL="$(printf 'x"}\n{"ts":"forged","mode":"scan","entry":"sca-scan.sh","module":"root","verdict":"GO')"
FORGE_Q='x","verdict":"GO'
R7="$(make_root forge-nl)"
B7="$(audit_count "$R7")"
O7="$(cd "$R7" && SCA_GATE_LEVEL="$FORGE_NL" PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc7=$?
[ "$rc7" -eq 1 ] && ok "(7) rc 1 on the forging level" || ko "(7) expected rc 1, got $rc7"
grep -Fq "invalid choice" <<<"$O7" \
  && ok "(7) witness: waiver_filter received the raw level and refused it" \
  || ko "(7) witness: no argparse refusal — the vector never reached the gate"
N7="$(audit_count "$R7")"
[ "$((N7 - B7))" -eq 1 ] && ok "(7) exactly ONE audit row appended" \
  || ko "(7) expected 1 appended audit row, got $((N7 - B7))"
A7="$(audit_new "$R7" "$B7")"
[ "$A7" = "mode=scan verdict=NO-GO module=root ts=real" ] \
  && ok "(7) the row PARSES, verdict NO-GO" \
  || ko "(7) expected [mode=scan verdict=NO-GO module=root ts=real], got [$A7]"
grep -Fq '"ts":"forged"' "$(report_dir "$R7")/audit-log.jsonl" 2>/dev/null \
  && ko "(7) a forged \"ts\":\"forged\" reached the audit log" \
  || ok "(7) no forged ts in the audit log (text witness)"

echo "=== (7b) the same vector under --all-modules => modules + 1 rows, none forged, last one NO-GO"
R7B="$(make_mod_root forge-nl-all)"
B7B="$(audit_count "$R7B")"
O7B="$(cd "$R7B" && SCA_GATE_LEVEL="$FORGE_NL" PATH="$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc7b=$?
grep -Fxq '== module sub (sub, submodules=0) ==' <<<"$O7B" \
  && ok "(7b) witness: the module loop scanned sub/" \
  || ko "(7b) witness: the module loop never reached sub/ — some other path was measured"
[ "$rc7b" -eq 1 ] && ok "(7b) rc 1" || ko "(7b) expected rc 1, got $rc7b"
N7B="$(audit_count "$R7B")"
[ "$((N7B - B7B))" -eq 2 ] && ok "(7b) exactly modules + 1 = 2 rows appended" \
  || ko "(7b) expected 2 appended audit rows, got $((N7B - B7B))"
A7B="$(audit_new "$R7B" "$B7B")"
grep -Fq 'ts=forged' <<<"$A7B" && ko "(7b) a forged row was appended" || ok "(7b) no forged row"
grep -Fxq 'UNPARSABLE' <<<"$A7B" && ko "(7b) an appended row does not parse" || ok "(7b) every appended row parses"
grep -Fq ' verdict=GO ' <<<"$A7B" && ko "(7b) an appended row PARSES as GO" || ok "(7b) no appended row parses as GO"
L7B="$(printf '%s\n' "$A7B" | tail -n 1)"
[ "$L7B" = "mode=all-modules verdict=NO-GO module=- ts=real" ] \
  && ok "(7b) the LAST row is the all-modules NO-GO" \
  || ko "(7b) expected the last row [mode=all-modules verdict=NO-GO module=- ts=real], got [$L7B]"

# ---- (7c) a bare quote: one duplicated key, and json keeps the LAST one -------
echo "=== (7c) level 'x\",\"verdict\":\"GO' => every appended row parses NO-GO (bare and --all-modules)"
R7C="$(make_root forge-q)"
B7C="$(audit_count "$R7C")"
(cd "$R7C" && SCA_GATE_LEVEL="$FORGE_Q" PATH="$CLEANBIN:$PATH" bash "$SCAN" >/dev/null 2>&1)
A7C="$(audit_new "$R7C" "$B7C")"
[ "$A7C" = "mode=scan verdict=NO-GO module=root ts=real" ] \
  && ok "(7c) bare form: the one appended row parses NO-GO" \
  || ko "(7c) bare form: expected [mode=scan verdict=NO-GO module=root ts=real], got [$A7C]"
R7C2="$(make_mod_root forge-q-all)"
B7C2="$(audit_count "$R7C2")"
(cd "$R7C2" && SCA_GATE_LEVEL="$FORGE_Q" PATH="$CLEANBIN:$PATH" bash "$SCAN" --all-modules >/dev/null 2>&1)
A7C2="$(audit_new "$R7C2" "$B7C2")"
n7c2="$(printf '%s\n' "$A7C2" | grep -c ' verdict=NO-GO ')"
[ "$n7c2" -eq 2 ] && [ "$(printf '%s\n' "$A7C2" | grep -c '')" -eq 2 ] \
  && ok "(7c) --all-modules: both appended rows parse NO-GO" \
  || ko "(7c) --all-modules: expected 2 rows, both NO-GO, got [$(printf '%s' "$A7C2" | tr '\n' '|')]"

# ---- (7d) a `"` in a module directory name ----------------------------------
echo "=== (7d) module directory 'mod\"x' => the row parses, module mod?x"
R7D="$(make_root slug-quote)"
if mkdir -p "$R7D/mod\"x" 2>/dev/null && printf 'flask==2.0.0\n' > "$R7D/mod\"x/requirements.txt" 2>/dev/null; then
  B7D="$(audit_count "$R7D")"
  O7D="$(cd "$R7D" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 'mod"x' 2>&1)"
  rc7d=$?
  [ "$rc7d" -eq 0 ] && ok "(7d) rc 0 on a clean module" \
    || ko "(7d) expected rc 0, got $rc7d — last line [$(printf '%s\n' "$O7D" | tail -n 1)]"
  [ -f "$(report_dir "$R7D")/modules/mod\"x/pip-audit.json" ] \
    && ok "(7d) witness: the module was scanned, its reports under the RAW name" \
    || ko "(7d) witness: no pip-audit.json under modules/mod\"x — some other path was measured"
  A7D="$(audit_new "$R7D" "$B7D")"
  [ "$A7D" = "mode=scan verdict=GO module=mod?x ts=real" ] \
    && ok "(7d) the row parses, module mod?x" \
    || ko "(7d) expected [mode=scan verdict=GO module=mod?x ts=real], got [$A7D]"
else
  # BOUND, never a false green: this filesystem refuses the name (Windows).
  echo "  BOUND: (7d) the filesystem refused a directory named mod\"x — the slug arm is NOT measured here"
fi

# ---- (8) --all-modules with Python ABSENT: DEGRADED, named, never NO-ECOSYSTEM -
# Measured before the branch: `"$PY" …` ran an empty command at discovery and
# the run said `no known ecosystem detected in any module`, rc 2, on a repo with
# a requirements.txt — false, since nothing was looked at.
echo "=== (8) --all-modules, Python absent, stale verdict files + stale reason => rc 0, DEGRADED named"
R8="$(make_mod_root nopy-all)"
D8="$(report_dir "$R8")"
mkdir -p "$D8/modules"
seed_pivot "$R8"
printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","modules":[],"global_verdict":"GO","note":"SEEDED-STALE"}' \
  > "$D8/modules/summary.json"
printf '%s\n' 'SEEDED-STALE-REASON of an earlier run' > "$D8/.degraded"
[ -f "$D8/effective-verdict.json" ] && [ -f "$D8/modules/summary.json" ] && [ -s "$D8/.degraded" ] \
  && ok "(8) witness: stale pivot, summary.json and reason are in place before the run" \
  || ko "(8) witness: could not seed the stale files"
B8="$(audit_count "$R8")"
NF8="$TMP/notfound-8.log"
: >"$NF8"
O8="$(nf_sensor_on; cd "$R8" && NF_LOG="$NF8" PATH="$NOPYBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc8=$?
grep -Fq 'PYTHON 3 NOT FOUND' <<<"$O8" \
  && ok "(8) witness: the dispatcher really found no Python" \
  || ko "(8) witness: Python was still found — this arm measures nothing"
[ "$rc8" -eq 0 ] && ok "(8) rc 0, never a block" || ko "(8) expected rc 0, got $rc8"
grep -Fq 'no known ecosystem' <<<"$O8" \
  && ko "(8) the run claims no known ecosystem — nothing was looked at" \
  || ok "(8) no 'no known ecosystem' claim"
grep -Fxq 'SCA: module discovery not run (python absent) — modules NOT enumerated, NOT scanned.' <<<"$O8" \
  && ok "(8) the run says discovery did not run" || ko "(8) the discovery line is missing"
[ ! -f "$D8/effective-verdict.json" ] && ok "(8) the stale pivot is GONE" \
  || ko "(8) the stale pivot survived a run that produced no verdict"
[ ! -f "$D8/modules/summary.json" ] && ok "(8) the stale summary.json is GONE" \
  || ko "(8) the stale summary.json survived — security-orchestrator would read it"
grep '^  COVERAGE DEGRADED:' <<<"$O8" | grep -Fq 'module discovery: not run (python absent)' \
  && ok "(8) the COVERAGE DEGRADED banner names the discovery" \
  || ko "(8) the banner does not name the discovery"
grep -Fq 'SEEDED-STALE-REASON' <<<"$O8" \
  && ko "(8) an earlier run's reason reached the banner (.degraded not reset)" \
  || ok "(8) no stale reason in the output (.degraded reset first)"
grep -Fq 'SEEDED-STALE-REASON' "$D8/.degraded" 2>/dev/null \
  && ko "(8) .degraded still carries the earlier run's reason" \
  || ok "(8) .degraded no longer carries the earlier run's reason"
L8="$(printf '%s\n' "$O8" | tail -n 1)"
[ "$L8" = "$GATE_DEG_ALL" ] && ok "(8) the last line says GO (DEGRADED — no effective verdict)" \
  || ko "(8) expected the DEGRADED all-modules last line, got [$L8]"
A8="$(audit_new "$R8" "$B8")"
[ "$A8" = "mode=all-modules verdict=DEGRADED module=- ts=real" ] \
  && ok "(8) ONE audit row, it parses, verdict DEGRADED" \
  || ko "(8) expected [mode=all-modules verdict=DEGRADED module=- ts=real], got [$A8]"
if grep -Fxq '[]' "$NFP"; then
  [ ! -s "$NF8" ] \
    && ok "(8) every command the dispatcher ran resolved — no empty \"\$PY\" executed" \
    || ko "(8) the dispatcher executed unresolved command(s) $(tr '\n' ' ' <"$NF8")— an empty \"\$PY\" ran"
else
  grep -Fq 'command not found' <<<"$O8" \
    && ko "(8) the output says 'command not found' (bash < 4: stderr only)" \
    || ok "(8) no 'command not found' in the output (BOUND: bash < 4)"
fi

# ---- (9) a healthy uv.lock with Python ABSENT: NOT READ, never "illisible" -----
# Measured before the guard: `[python] locks: uv.lock illisible(s) — résolution
# ÉCHOUÉE (pas refusée), rc=127` on a sound lock — the reader was missing.
echo "=== (9) uv.lock alone + Python absent => .degraded says not read (python absent), never illisible"
R9="$(make_lock_root nopy-uvlock)"
D9="$(report_dir "$R9")"
NF9="$TMP/notfound-9.log"
: >"$NF9"
O9="$(nf_sensor_on; cd "$R9" && NF_LOG="$NF9" PATH="$NOPYBIN:$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc9=$?
grep -Fq 'PYTHON 3 NOT FOUND' <<<"$O9" \
  && ok "(9) witness: the dispatcher really found no Python" \
  || ko "(9) witness: Python was still found — this arm measures nothing"
grep -Fxq 'python: uv.lock non lus (python absent) — py_lock_pins.py non lancé' "$D9/.degraded" 2>/dev/null \
  && ok "(9) .degraded says the lock was not read, python absent" \
  || ko "(9) .degraded lacks the lock-not-read line"
grep -Fq 'illisible' "$D9/.degraded" 2>/dev/null \
  && ko "(9) .degraded calls a healthy lock 'illisible'" || ok "(9) no 'illisible' in .degraded"
grep -Fq 'illisible' <<<"$O9" && ko "(9) the output calls a healthy lock 'illisible'" || ok "(9) no 'illisible' in the output"
grep -Fq 'rc=127' <<<"$O9" && ko "(9) the output carries rc=127 (an empty command ran)" || ok "(9) no rc=127 in the output"
[ "$rc9" -eq 0 ] && ok "(9) rc 0, never a block" || ko "(9) expected rc 0, got $rc9"
grep -Fxq -- "$GATE_DEG" <<<"$O9" && ok "(9) the last line says GO (DEGRADED — no effective verdict)" \
  || ko "(9) the DEGRADED final line is missing"
if grep -Fxq '[]' "$NFP"; then
  [ ! -s "$NF9" ] \
    && ok "(9) every command the dispatcher ran resolved — no empty \"\$PY\" executed" \
    || ko "(9) the dispatcher executed unresolved command(s) $(tr '\n' ' ' <"$NF9")— an empty \"\$PY\" ran"
else
  grep -Fq 'command not found' <<<"$O9" \
    && ko "(9) the output says 'command not found' (bash < 4: stderr only)" \
    || ok "(9) no 'command not found' in the output (BOUND: bash < 4)"
fi

# ---- (10) stale reports of tools that did NOT run: purged, never read --------
# Reserve C5: `$OUT` survives between runs and waiver_filter reads every report
# of its `parsers` table it finds there. The fixture has no package.json, no
# pom.xml and no IaC file, so npm, socket, dependency-check and the trivy copy
# never write — whatever is installed on the PATH. Only pip-audit (the stub)
# runs, and its report must SURVIVE: the purge precedes the tools.
echo "=== (10) stale truncated / readable reports of tools that did not run => purged, GO"
real_wf
R10="$(make_root stale-reports)"
D10="$(report_dir "$R10")"
DC_CRIT='{"dependencies":[{"fileName":"log4j-core-2.14.1.jar","packages":[{"id":"pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"}],"vulnerabilities":[{"name":"CVE-2021-44228","severity":"CRITICAL"}]}]}'
seed_stale() {
  printf '%s' '{"auditReportVersion":2,"vulnerabilities":{"lodash":{"name":"lodash","severity":"high"' > "$1/npm-audit.json"
  printf '%s\n' "$DC_CRIT" > "$1/dependency-check-report.json"
  printf '%s' '{"issues":[{"type":"malware"' > "$1/socket.json"
  printf '%s' '{"SchemaVersion":2,"Results":[{"Target":"Dockerfile","Misconfigurations":[{"ID":"DS002","Severity":"HIGH"' > "$1/trivy-config.json"
}
seed_stale "$D10"
# Non-vacuity: read as they are, the seeded reports BLOCK (the readable CRITICAL
# today; every truncated one too once waiver_filter fails closed on them).
PROBE10="$TMP/stale-probe"
mkdir -p "$PROBE10"
seed_stale "$PROBE10"
python3 "$KIT/waiver_filter.py" --reports-dir "$PROBE10" --waivers "$TMP/no-register.json" --root "$R10" >/dev/null 2>&1
rcp10=$?
[ "$rcp10" -ne 0 ] && ok "(10) witness: the seeded reports block when read (waiver_filter rc $rcp10)" \
  || ko "(10) witness: the seeded reports do not block when read — this arm measures nothing"
O10="$(cd "$R10" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc10=$?
[ "$rc10" -eq 0 ] && ok "(10) rc 0 — no stale report gated the run" || ko "(10) expected rc 0, got $rc10"
grep -Fxq -- "$GATE_GO" <<<"$O10" && ok "(10) final verdict GO" || ko "(10) final verdict is not GO"
grep -Fq -- "$FC_TAIL" <<<"$O10" && ko "(10) fail-closed fired on a stale report" || ok "(10) no fail-closed line"
for f10 in npm-audit.json dependency-check-report.json socket.json trivy-config.json; do
  [ ! -f "$D10/$f10" ] && ok "(10) the stale $f10 is GONE" \
    || ko "(10) the stale $f10 survived — it would be read as today's"
done
[ -s "$D10/pip-audit.json" ] && ok "(10) today's pip-audit.json is kept (purge BEFORE the tools)" \
  || ko "(10) today's pip-audit.json is missing — the purge ran after the tools?"
grep -Fq '"active_at_gate": 0' "$D10/effective-verdict.json" 2>/dev/null \
  && ok "(10) the fresh pivot counts 0 active finding" || ko "(10) the pivot counts a stale finding (or is absent)"

# ---- (10b) trivy-image.json is NOT purged: its producer is not this script ----
echo "=== (10b) a trivy-image.json from the project's image-scan step => kept, its CRITICAL gates"
R10B="$(make_root image-report)"
D10B="$(report_dir "$R10B")"
printf '%s\n' '{"SchemaVersion":2,"ArtifactName":"myapp/web:ci","ArtifactType":"container_image","_BaseRef":"debian:12.13","Results":[{"Target":"myapp/web:ci (debian 12.13)","Class":"os-pkgs","Type":"debian","Vulnerabilities":[{"VulnerabilityID":"CVE-2026-13221","PkgName":"perl-base","InstalledVersion":"5.36.0-7+deb12u2","Severity":"CRITICAL"}]}]}' \
  > "$D10B/trivy-image.json"
O10B="$(cd "$R10B" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc10b=$?
[ "$rc10b" -eq 1 ] && ok "(10b) rc 1 — the image CVE still gates" || ko "(10b) expected rc 1, got $rc10b"
grep -Fxq -- "$GATE_NOGO" <<<"$O10B" && ok "(10b) final verdict NO-GO" || ko "(10b) final verdict is not NO-GO"
[ -f "$D10B/trivy-image.json" ] && ok "(10b) trivy-image.json was NOT purged" \
  || ko "(10b) trivy-image.json was purged — the producer's image CVEs vanish"
grep -Fq '"active_at_gate": 1' "$D10B/effective-verdict.json" 2>/dev/null \
  && ok "(10b) the fresh pivot counts the image finding" || ko "(10b) the pivot does not count the image finding"

# ---- (11)-(11f) a module run whose rc carries NO verdict ----------------------
# T-01M4Z395686TR4M7326AQ8ZPHW. The --all-modules loop tested `-eq 1` only, so a
# module killed by a signal, or ending on a bare `exit 3` / `exit 2`, read GO,
# TRACKED-NOT-GATING or NO-ECOSYSTEM — never "no verdict obtained". The module
# runs are driven through BASH_ENV (see the header): a file of several lines (no
# first clause on the `case` line, test_no_compact_case.py), acting where `$1` is
# `sub`. A trivy stub that answers nothing keeps a real trivy out of these arms.
QUIETBIN="$TMP/stub-quiet"
mkdir -p "$QUIETBIN"
printf '%s\n' '#!/bin/sh' 'exit 0' > "$QUIETBIN/trivy"
chmod +x "$QUIETBIN/trivy"
# WHY A DEBUG TRAP, MEASURED: bash 3.2.57 sources BASH_ENV BEFORE it sets the
# script's positional parameters (`$#` 0, `$0` /bin/bash), 5.3.15 after — a
# plain `case "$1"` in the file acts under 5.x only. The trap fires at the
# script's FIRST command, where `$1` is set under both, and disarms itself IN
# ITS OWN STRING: disarmed from inside the function, 3.2 kept it, and the trap
# then overwrote the PIPESTATUS the loop reads (the killed module read rc 0).
crash_env() {  # FILE ACTION...: a BASH_ENV file running ACTION... in the run of `sub`
  local f="$1" a
  shift
  {
    printf '%s\n' 'crash_hook() {' '  case "${1:-}" in' '    sub)'
    for a in "$@"; do printf '      %s\n' "$a"; done
    printf '%s\n' '      ;;' '  esac' '}' "trap 'trap - DEBUG; crash_hook \"\${1:-}\"' DEBUG"
  } > "$f"
}
mod_line() {  # SLUG RC: the exact module line, as `log` prints it
  printf '  SCA GATE all-modules (effective, waivers applied): NO-GO — module %s exited rc=%s, no verdict obtained (fail-closed)' "$1" "$2"
}
GATE_NOGO_ALL='SCA GATE all-modules (effective, waivers applied): NO-GO'
GATE_GO_ALL='SCA GATE all-modules (effective, waivers applied): GO'
MOD_TAIL='no verdict obtained (fail-closed)'
# summary.json of a fixture root, PARSED: `global=<v> <slug>:<verdict>:<exit>:<gating>:c=<{}|active> total=<active>`.
summary_of() {
  python3 -c 'import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
def c(m):
    return "{}" if not m["counters"] else str(m["counters"].get("active_at_gate"))
mods = " ".join("%s:%s:%s:%s:c=%s" % (m["slug"], m["verdict"], m["exit_code"], m["gating"], c(m)) for m in s["modules"])
print("global=%s %s total=%s" % (s["global_verdict"], mods, s["counters_total"]["active_at_gate"]))' \
    "$(report_dir "$1")/modules/summary.json" 2>/dev/null || echo "UNREADABLE"
}
reasons_of() {  # ROOT SLUG: that module's degraded_reasons, one per line
  python3 -c 'import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
for m in s["modules"]:
    if m["slug"] == sys.argv[2]:
        print("\n".join(m["degraded_reasons"]))' \
    "$(report_dir "$1")/modules/summary.json" "$2" 2>/dev/null
}

echo "=== (11) --all-modules, the module run of sub KILLED (rc 137) => rc 1, ERROR, NO-GO on every surface"
R11="$(make_mod_root killed)"
E11="$TMP/env-killed.sh"
crash_env "$E11" 'kill -9 $$'
B11="$(audit_count "$R11")"
O11="$(cd "$R11" && BASH_ENV="$E11" PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11=$?
grep -Fxq '== module sub (sub, submodules=0) ==' <<<"$O11" \
  && ok "(11) witness: the module loop reached sub/" \
  || ko "(11) witness: the module loop never reached sub/ — some other path was measured"
[ "$rc11" -eq 1 ] && ok "(11) rc 1 on a killed module" || ko "(11) expected rc 1, got $rc11"
grep -Fxq -- "$(mod_line sub 137)" <<<"$O11" \
  && ok "(11) the module line names sub and rc=137, no verdict obtained" \
  || ko "(11) the module line is missing or different"
S11="$(summary_of "$R11")"
[ "$S11" = "global=NO-GO sub:ERROR:137:True:c={} total=0" ] \
  && ok "(11) summary.json: NO-GO, sub ERROR, gating, no counter" \
  || ko "(11) expected [global=NO-GO sub:ERROR:137:True:c={} total=0], got [$S11]"
reasons_of "$R11" sub | grep -Fxq 'module run exited rc=137 — no verdict obtained' \
  && ok "(11) the module's degraded_reasons name the rc" \
  || ko "(11) degraded_reasons lack [module run exited rc=137 — no verdict obtained]"
L11="$(printf '%s\n' "$O11" | tail -n 1)"
[ "$L11" = "$GATE_NOGO_ALL" ] && ok "(11) the last line is the all-modules NO-GO" \
  || ko "(11) expected the last line [$GATE_NOGO_ALL], got [$L11]"
A11="$(audit_new "$R11" "$B11" | tail -n 1)"
[ "$A11" = "mode=all-modules verdict=NO-GO module=- ts=real" ] \
  && ok "(11) the last audit row is the all-modules NO-GO" \
  || ko "(11) expected the last audit row [mode=all-modules verdict=NO-GO module=- ts=real], got [$A11]"

echo "=== (11b) a bare exit 3 in the module run => ERROR, never TRACKED-NOT-GATING"
R11B="$(make_mod_root exit3)"
E11B="$TMP/env-exit3.sh"
crash_env "$E11B" 'exit 3'
O11B="$(cd "$R11B" && BASH_ENV="$E11B" PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11b=$?
[ "$rc11b" -eq 1 ] && ok "(11b) rc 1 on a raw 3" || ko "(11b) expected rc 1, got $rc11b"
grep -Fxq -- "$(mod_line sub 3)" <<<"$O11B" \
  && ok "(11b) the module line names rc=3" || ko "(11b) the module line is missing or different"
S11B="$(summary_of "$R11B")"
[ "$S11B" = "global=NO-GO sub:ERROR:3:True:c={} total=0" ] \
  && ok "(11b) summary.json: sub ERROR, gating" \
  || ko "(11b) expected [global=NO-GO sub:ERROR:3:True:c={} total=0], got [$S11B]"

echo "=== (11c) non-regression: a PROTECTED module's real NO-GO => TRACKED-NOT-GATING, GO"
R11C="$(make_mod_root protected)"
mkdir -p "$R11C/.codex/hooks"
printf '%s\n' 'PROTECTED_PREFIXES = ("sub/",)' 'def extra_prefixes():' '    return ()' \
  > "$R11C/.codex/hooks/protect_paths.py"
O11C="$(cd "$R11C" && PATH="$QUIETBIN:$HIGHBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11c=$?
grep -Fq "NOT GATING: 'sub' is a protected path" <<<"$O11C" \
  && ok "(11c) witness: the protected-path probe exempted sub/" \
  || ko "(11c) witness: sub/ was not exempted — some other path was measured"
[ "$rc11c" -eq 0 ] && ok "(11c) rc 0: a tracked finding does not gate" || ko "(11c) expected rc 0, got $rc11c"
S11C="$(summary_of "$R11C")"
[ "$S11C" = "global=GO sub:TRACKED-NOT-GATING:3:False:c=1 total=1" ] \
  && ok "(11c) summary.json: sub TRACKED-NOT-GATING, not gating, its finding counted" \
  || ko "(11c) expected [global=GO sub:TRACKED-NOT-GATING:3:False:c=1 total=1], got [$S11C]"
grep -Fq -- "$MOD_TAIL" <<<"$O11C" && ko "(11c) a module line fired on a tracked module" \
  || ok "(11c) no module line"

echo "=== (11d) a killed module over an EARLIER pivot (active 7) => pivot removed, the 7 counted nowhere"
R11D="$(make_mod_root killed-stale)"
D11D="$(report_dir "$R11D")/modules/sub"
mkdir -p "$D11D"
printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","gate_level":"high","active":[],"waived_accepted":[],"waived_pending":[],"counters":{"active_at_gate":7,"accepted":0,"pending_review":0,"overdue_review":0},"notes":["SEEDED-STALE"]}' \
  > "$D11D/effective-verdict.json"
[ -f "$D11D/effective-verdict.json" ] && ok "(11d) witness: the earlier pivot is in place" \
  || ko "(11d) witness: could not seed the earlier pivot"
O11D="$(cd "$R11D" && BASH_ENV="$E11" PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11d=$?
[ "$rc11d" -eq 1 ] && ok "(11d) rc 1" || ko "(11d) expected rc 1, got $rc11d"
[ ! -f "$D11D/effective-verdict.json" ] && ok "(11d) the earlier pivot of the killed module is GONE" \
  || ko "(11d) the earlier pivot survived — a reader would take its 7 for today's"
S11D="$(summary_of "$R11D")"
[ "$S11D" = "global=NO-GO sub:ERROR:137:True:c={} total=0" ] \
  && ok "(11d) summary.json: counters {} and counters_total without the 7" \
  || ko "(11d) expected [global=NO-GO sub:ERROR:137:True:c={} total=0], got [$S11D]"

echo "=== (11e) a bare exit 2 (no no-ecosystem line) => ERROR, never NO-ECOSYSTEM"
R11E="$(make_mod_root exit2)"
E11E="$TMP/env-exit2.sh"
crash_env "$E11E" 'exit 2'
O11E="$(cd "$R11E" && BASH_ENV="$E11E" PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11e=$?
[ "$rc11e" -eq 1 ] && ok "(11e) rc 1 on a raw 2" || ko "(11e) expected rc 1, got $rc11e"
grep -Fxq -- "$(mod_line sub 2)" <<<"$O11E" \
  && ok "(11e) the module line names rc=2" || ko "(11e) the module line is missing or different"
S11E="$(summary_of "$R11E")"
[ "$S11E" = "global=NO-GO sub:ERROR:2:True:c={} total=0" ] \
  && ok "(11e) summary.json: sub ERROR" \
  || ko "(11e) expected [global=NO-GO sub:ERROR:2:True:c={} total=0], got [$S11E]"

echo "=== (11f) non-regression: the no-ecosystem line + exit 2 => NO-ECOSYSTEM, GO"
R11F="$(make_mod_root noeco)"
E11F="$TMP/env-noeco.sh"
crash_env "$E11F" 'echo "SCA: no known ecosystem detected."' 'exit 2'
O11F="$(cd "$R11F" && BASH_ENV="$E11F" PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11f=$?
[ "$rc11f" -eq 0 ] && ok "(11f) rc 0" || ko "(11f) expected rc 0, got $rc11f"
S11F="$(summary_of "$R11F")"
[ "$S11F" = "global=GO sub:NO-ECOSYSTEM:2:True:c={} total=0" ] \
  && ok "(11f) summary.json: sub NO-ECOSYSTEM" \
  || ko "(11f) expected [global=GO sub:NO-ECOSYSTEM:2:True:c={} total=0], got [$S11F]"
grep -Fq -- "$MOD_TAIL" <<<"$O11F" && ko "(11f) a module line fired on a real no-ecosystem run" \
  || ok "(11f) no module line"
L11F="$(printf '%s\n' "$O11F" | tail -n 1)"
[ "$L11F" = "$GATE_GO_ALL" ] && ok "(11f) the last line is the all-modules GO" \
  || ko "(11f) expected the last line [$GATE_GO_ALL], got [$L11F]"

echo "=== (11g) a PROTECTED module whose run is lock-busy (raw 1, no verdict) => ERROR, gating, rc 1, pivot left"
# The module run forgets SCA_LOCK_OWNER (the DEBUG trap of crash_env), so it waits
# for its OWN parent's lock: a REAL lock-busy, rc 1, after SCA_LOCK_WAIT_SECONDS=1.
R11G="$(make_mod_root protected-busy)"
mkdir -p "$R11G/.codex/hooks"
printf '%s\n' 'PROTECTED_PREFIXES = ("sub/",)' 'def extra_prefixes():' '    return ()' \
  > "$R11G/.codex/hooks/protect_paths.py"
D11G="$(report_dir "$R11G")/modules/sub"
mkdir -p "$D11G"
printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","gate_level":"high","active":[],"waived_accepted":[],"waived_pending":[],"counters":{"active_at_gate":7,"accepted":0,"pending_review":0,"overdue_review":0},"notes":["SEEDED-STALE"]}' \
  > "$D11G/effective-verdict.json"
E11G="$TMP/env-unset-owner.sh"
crash_env "$E11G" 'unset SCA_LOCK_OWNER'
O11G="$(cd "$R11G" && BASH_ENV="$E11G" SCA_LOCK_WAIT_SECONDS=1 PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11g=$?
grep -Fq '  SCA GATE (effective, waivers applied): NO-GO — reports lock held by pid ' <<<"$O11G" \
  && ok "(11g) witness: the module run of sub ended lock-busy" \
  || ko "(11g) witness: no lock-busy line — some other path was measured"
[ "$rc11g" -eq 1 ] && ok "(11g) rc 1 on a protected module that obtained no verdict" \
  || ko "(11g) expected rc 1, got $rc11g"
grep -Fxq -- "$(mod_line sub 1)" <<<"$O11G" \
  && ok "(11g) the module line names sub and rc=1, no verdict obtained" \
  || ko "(11g) the module line is missing or different"
grep -Fq "NOT GATING: 'sub' is a protected path" <<<"$O11G" \
  && ko "(11g) the protected substitution applied to a run with NO verdict" \
  || ok "(11g) no protected substitution"
S11G="$(summary_of "$R11G")"
[ "$S11G" = "global=NO-GO sub:ERROR:1:True:c={} total=0" ] \
  && ok "(11g) summary.json: sub ERROR, gating, counters {}, the 7 counted nowhere" \
  || ko "(11g) expected [global=NO-GO sub:ERROR:1:True:c={} total=0], got [$S11G]"
grep -Fq '"active_at_gate":7' "$D11G/effective-verdict.json" 2>/dev/null \
  && ok "(11g) the earlier pivot is LEFT under a raw 1 (a busy lock is another run's)" \
  || ko "(11g) the pivot was removed under a raw 1"

echo "=== (11h) a PROTECTED module whose scanner report is unreadable (waiver_filter rc 3) => ERROR, gating, rc 1"
# E1 (T-01M51RFFECAFAAR0CM3NR1GYEC). The MEASURED truncation of
# sca-report-unreadable.test.sh (cut inside a HIGH, exit 1): waiver_filter
# answers rc 3, the module run prints its fail-closed line and exits 1. Measured
# before: that raw 1 took the protected substitution, TRACKED-NOT-GATING, GO rc 0
# — an absence of verdict is not a finding (L-00000180 exempts findings only).
TRUNCBIN="$TMP/stub-trunc"
mkdir -p "$TRUNCBIN"
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"severity":"HIGH"'"'" \
  'exit 1' > "$TRUNCBIN/pip-audit"
chmod +x "$TRUNCBIN/pip-audit"
rc3_mod_line() {  # SLUG: the exact line of a module whose report was unreadable, as `log` prints it
  printf '  SCA GATE all-modules (effective, waivers applied): NO-GO — module %s: no fresh effective verdict (fail-closed)' "$1"
}
R11H="$(make_mod_root protected-unreadable)"
mkdir -p "$R11H/.codex/hooks"
printf '%s\n' 'PROTECTED_PREFIXES = ("sub/",)' 'def extra_prefixes():' '    return ()' \
  > "$R11H/.codex/hooks/protect_paths.py"
B11H="$(audit_count "$R11H")"
O11H="$(cd "$R11H" && PATH="$QUIETBIN:$TRUNCBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11h=$?
grep -Fxq -- "$(fc_line 3 high)" <<<"$O11H" \
  && ok "(11h) witness: the module run of sub printed waiver_filter's rc=3 line" \
  || ko "(11h) witness: no rc=3 line in the module run — some other path was measured"
[ "$rc11h" -eq 1 ] && ok "(11h) rc 1 on a protected module whose report is unreadable" \
  || ko "(11h) expected rc 1, got $rc11h"
S11H="$(summary_of "$R11H")"
[ "$S11H" = "global=NO-GO sub:ERROR:1:True:c={} total=0" ] \
  && ok "(11h) summary.json: sub ERROR, gating, counters {}" \
  || ko "(11h) expected [global=NO-GO sub:ERROR:1:True:c={} total=0], got [$S11H]"
grep -Fxq -- "$(rc3_mod_line sub)" <<<"$O11H" \
  && ok "(11h) the module line says sub obtained no fresh effective verdict" \
  || ko "(11h) the line [$(rc3_mod_line sub)] is missing"
grep -Fxq -- "$(mod_line sub 1)" <<<"$O11H" \
  && ko "(11h) the run-cut-short line fired (sca-watch would add the wrong motif)" \
  || ok "(11h) no 'exited rc=1, no verdict obtained' line"
grep -Fq 'NOT GATING' <<<"$O11H" \
  && ko "(11h) the protected substitution applied to a report it could not read" \
  || ok "(11h) no NOT GATING"
L11H="$(printf '%s\n' "$O11H" | tail -n 1)"
[ "$L11H" = "$GATE_NOGO_ALL" ] && ok "(11h) the last line is the all-modules NO-GO" \
  || ko "(11h) expected the last line [$GATE_NOGO_ALL], got [$L11H]"
A11H="$(audit_new "$R11H" "$B11H" | tail -n 1)"
[ "$A11H" = "mode=all-modules verdict=NO-GO module=- ts=real" ] \
  && ok "(11h) the last audit row is the all-modules NO-GO" \
  || ko "(11h) expected the last audit row [mode=all-modules verdict=NO-GO module=- ts=real], got [$A11H]"

echo "=== (11i) a PROTECTED module's raw 1 whose module log could not be created => ERROR, gating, rc 1"
# Security review MEDIUM: with no module log, neither no-verdict line can be read,
# and the raw 1 used to take the protected substitution — TRACKED-NOT-GATING, GO
# rc 0, whatever that run said. A `mktemp` that refuses the `.modlog.` template
# only (counted), the real one otherwise; a real HIGH in the protected module.
MKTFAIL="$TMP/stub-mktfail"
mkdir -p "$MKTFAIL"
REAL_MKTEMP="$(command -v mktemp)"
printf '%s\n' '#!/usr/bin/env bash' \
  'case "$*" in' \
  '  *.modlog.*)' \
  '    printf "x\n" >> "$FC_MKT_CTR"' \
  '    exit 1' \
  '    ;;' \
  'esac' \
  "exec \"$REAL_MKTEMP\" \"\$@\"" > "$MKTFAIL/mktemp"
chmod +x "$MKTFAIL/mktemp"
R11I="$(make_mod_root protected-nolog)"
mkdir -p "$R11I/.codex/hooks"
printf '%s\n' 'PROTECTED_PREFIXES = ("sub/",)' 'def extra_prefixes():' '    return ()' \
  > "$R11I/.codex/hooks/protect_paths.py"
O11I="$(cd "$R11I" && FC_MKT_CTR="$TMP/mkt11i.ctr" PATH="$MKTFAIL:$QUIETBIN:$HIGHBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11i=$?
[ "$(grep -c '' "$TMP/mkt11i.ctr" 2>/dev/null)" = 1 ] \
  && ok "(11i) witness: the module log of sub was refused (once)" \
  || ko "(11i) witness: the .modlog. mktemp was not refused once — some other path was measured"
[ "$rc11i" -eq 1 ] && ok "(11i) rc 1: a raw 1 that cannot be read is not exempted" \
  || ko "(11i) expected rc 1, got $rc11i"
S11I="$(summary_of "$R11I")"
[ "$S11I" = "global=NO-GO sub:ERROR:1:True:c={} total=0" ] \
  && ok "(11i) summary.json: sub ERROR, gating" \
  || ko "(11i) expected [global=NO-GO sub:ERROR:1:True:c={} total=0], got [$S11I]"
grep -Fq 'NOT GATING' <<<"$O11I" \
  && ko "(11i) the protected substitution applied to a raw 1 nobody could read" \
  || ok "(11i) no NOT GATING"

echo "=== (11j) a PROTECTED module whose waiver_filter answers rc 2 (SCA_GATE_LEVEL=medium) => TRACKED-NOT-GATING, GO (pinned)"
# The plan's blind spot, branch « non » (exec-critic): only rc 3 reaches ERROR; an
# invalid SCA_GATE_LEVEL in a protected module stays tracked. Pinned so that a
# widening of the rc 3 anchor is SEEN — it is a pilot decision, not a drift.
R11J="$(make_mod_root protected-rc2)"
mkdir -p "$R11J/.codex/hooks"
printf '%s\n' 'PROTECTED_PREFIXES = ("sub/",)' 'def extra_prefixes():' '    return ()' \
  > "$R11J/.codex/hooks/protect_paths.py"
O11J="$(cd "$R11J" && SCA_GATE_LEVEL=medium PATH="$QUIETBIN:$CLEANBIN:$PATH" bash "$SCAN" --all-modules 2>&1)"
rc11j=$?
grep -Fxq -- "$(fc_line 2 medium)" <<<"$O11J" \
  && ok "(11j) witness: the module run of sub printed waiver_filter's rc=2 line" \
  || ko "(11j) witness: no rc=2 line — some other path was measured"
[ "$rc11j" -eq 0 ] && ok "(11j) rc 0: rc 2 in a protected module stays tracked" \
  || ko "(11j) expected rc 0, got $rc11j"
S11J="$(summary_of "$R11J")"
[ "$S11J" = "global=GO sub:TRACKED-NOT-GATING:3:False:c={} total=0" ] \
  && ok "(11j) summary.json: sub TRACKED-NOT-GATING, not gating" \
  || ko "(11j) expected [global=GO sub:TRACKED-NOT-GATING:3:False:c={} total=0], got [$S11J]"
grep -Fxq -- "$(rc3_mod_line sub)" <<<"$O11J" \
  && ko "(11j) the rc 3 line fired on an rc 2" || ok "(11j) no 'no fresh effective verdict' module line"

echo
echo "sca-gate-failclosed: $passed passed / $failed failed"
[ "$failed" -eq 0 ]
