#!/usr/bin/env bash
# Suite for the UNREADABLE-REPORT path of the SCA gate, end to end
# (T-01M4X7W4M2XCFBK1MSY04X2907, decision S-01M4XXZ7FMDJ3ZQFDVF2FC9WJZ).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. Every case runs the REAL
# dispatcher (a private copy of sca-scan.sh and the python siblings it resolves
# from its own SCRIPT_DIR) against a disposable fixture root. The report comes
# from a STUB `pip-audit` on the PATH, never from the real tool.
#
# THE DEFECT (class 1, measured before the fix): a pip-audit.json cut in the
# middle of a HIGH was SKIPPED by waiver_filter.py with a note; the run printed
# `SUMMARY active=0 accepted=0 pending=0 overdue=0`, then
# `SCA GATE (effective, waivers applied): GO`, rc 0 — a GO built on a report
# nobody could read.
#
# THE RULE UNDER TEST: a report PRESENT but unreadable makes waiver_filter.py
# answer rc 3 — no pivot, no SUMMARY, the report NAMED in .degraded — and the
# fail-closed block of sca-scan.sh (any rc outside {0,1}) turns that into exit 1,
# NO-GO, the stale pivot removed, `waiver_filter: no fresh effective verdict
# (rc 3)` in .degraded and the `COVERAGE DEGRADED:` banner naming the report.
#
#   (1) truncated pip-audit.json holding a HIGH + a stale GO pivot -> rc 1, the
#       fail-closed line `rc=3, gate_level=high`, the `waiver_filter: ` lines of
#       .degraded EXACTLY the two expected ones, the banner names pip-audit.json,
#       pivot gone, the audit row PARSES with verdict NO-GO
#   (2) control: a clean pip-audit -> GO rc 0, a fresh pivot, no `waiver_filter: `
#       line in .degraded
#   (3) pip-audit.json = `null`, READABLE but a shape the parser raises on ->
#       the same rc 3 path, named with its class (UnrecognisedShape since
#       T-01M4Z33N54TX0Q7VHBZATFNR4X: SHAPE_CHECKS rejects it before the parser
#       runs), no traceback (exec-critic MAJEUR: it was a traceback, rc 1, the
#       report never named)
#   (e1) T-01M4Z33N54TX0Q7VHBZATFNR4X, step 1: pip-audit.json = `{}`. It is
#       READABLE, raises nothing, and SHAPE_CHECKS does not recognise it ->
#       the same rc 3 path, named UnrecognisedShape. Before the step it was a GO,
#       with zero findings and rc 0.
#   (e2) step 2: package.json without a lockfile, npm answers ENOLOCK, socket
#       answers `{"alerts":[]}`, trivy exits 0 -> GO rc 0, DEGRADED named. The
#       `waiver_filter: ` subset of .degraded is EXACTLY the tool-error line,
#       and both the banner and the pivot notes carry that line.
#   (e1) and (e2) put STUBS of pip-audit, npm, socket and trivy first on the PATH.
#   All four are real tools on a dev box, and none of them may run here: no
#   network, no real verdict.
#
# WHY ONLY THE `waiver_filter: ` LINES OF .degraded ARE COMPARED (reserve C1 of
# plan-critic 2/8). Other blocks of the dispatcher write their own reasons to the
# same file on every run — trivy at least one line, installed or not
# (sca-scan.sh, IaC block: "no IaC file found" or "not installed"). An equality on
# the whole file would pin the host's tool set, not this rule. So the subset
# `^waiver_filter: ` is extracted, sorted under LC_ALL=C, and compared by `cmp`
# to the two expected lines, sorted the same way.
#
# MUTATIONS THAT MUST TURN THIS SUITE RED (L-00000343), each applied to a COPY of
# waiver_filter.py in a scratch tree, never to the tracked file:
#   MA1 back to the skip-with-note (no rc 3 path)        -> (1) RED
#   MA5 the `.degraded` append removed                   -> (1) RED (subset, banner)
#   MA6 the exception MESSAGE written instead of its class -> (1) RED (subset, banner)
# Replay: copy this file, sca-scan.sh and the four .py siblings it calls into one
# scratch directory, mutate the copy, run the copied suite (HERE resolves there).
# REPLAYED, not asserted (2026-10-14, bash 5.3.15, each mutation checked APPLIED
# by `cmp` and compiled before its run; control 21/21): MA1 9 KO, all of (1)
# but its witnesses; MA5 2 KO and MA6 2 KO, the subset and the banner; MA4
# (SUMMARY printed before rc 3) 1 KO, the SUMMARY arm. Two more of the plan's
# mutants are replayed with test_waiver_filter.py beside them: MA3
# (the register routed through the report path) makes (2) RED, 7 KO — its
# register is the absent one sca-scan.sh passes; MA2 (stale pivot not unlinked)
# stays GREEN here, BY DESIGN: sca-scan.sh removes the pivot itself on any rc
# outside {0,1}, so only the pytest case can see it.
# (3) REPLAYED the same way (2026-10-15, control 29/29): the guard narrowed to
# `except ValueError`, or back to `except (OSError, ValueError)` -> 4 KO each,
# all in (3): no rc=3 line, the subset, the banner, and a traceback is back.
# T-01M4Z33N54TX0Q7VHBZATFNR4X, lot A. The MA labels above belong to
# T-01M4X7W4M2; the ones below are this plan's. REPLAYED, not asserted
# (2026-10-16, bash 5.3.15, each mutant applied to a scratch copy, checked by
# `cmp` and parsed before its run; control 46/46):
#   MA1 (npm check forced to "recognised") -> 3 KO, all in (e2);
#   MA5 (pip check forced) -> 9 KO, in (e1) and (3);
#   MA11 (ENOLOCK turned into rc 3) -> 7 KO, all in (e2).
# The plan's other mutants are seen by test_waiver_filter.py.
#
# FORM (bash 3.2 floor): no heredoc at all; `grep -F`/`-Fx` wherever a literal
# is pinned; `rc` captured on the line that follows the command; no tree walk
# (`.agents/security` is in the perimeter of test_repo_walk_census.py). No SKIP:
# python3 is class B in core-scripts/tool-inventory.tsv, its absence reddens.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TMP="$(mktemp -d)"
# REFUSE a degenerate workspace root: an empty $TMP would make every
# `mkdir -p "$TMP/x"` write at `/x`.
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

# Hermetic: an inherited knob would change what every arm measures.
unset SCA_GATE_LEVEL SCA_CHANGED_ONLY SCA_ROOT_ONLY AGENTS_HOOK_HOST

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }
# THE EXACT NUMBER OF ARMS, count arm INCLUDED — an equality, never a floor, so
# a cell that dies before its assertions reddens the run.
EXPECT_ARMS=46

# A PRIVATE copy of the dispatcher and its python siblings, taken AS THEY ARE.
KIT="$TMP/kit"
mkdir -p "$KIT"
for f in sca-scan.sh waiver_filter.py protected_module.py module_discovery.py py_lock_pins.py; do
  cp "$HERE/$f" "$KIT/$f" || { echo "FATAL: cannot copy $f into the private kit"; exit 2; }
done
SCAN="$KIT/sca-scan.sh"

# Two pip-audit stubs: the MEASURED truncation (cut in the middle of a HIGH, exit
# 1 like the real tool on a finding) and a clean report (exit 0).
TRUNCBIN="$TMP/stub-trunc"
CLEANBIN="$TMP/stub-clean"
NULLBIN="$TMP/stub-null"
mkdir -p "$TRUNCBIN" "$CLEANBIN" "$NULLBIN"
# A third stub for (3): a report that DECODES — to `null` — and that the parser
# cannot walk (exec-critic MAJEUR: a traceback, rc 1, the report never named).
printf '%s\n' '#!/usr/bin/env bash' 'echo null' 'exit 1' > "$NULLBIN/pip-audit"
chmod +x "$NULLBIN/pip-audit"
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"severity":"HIGH"'"'" \
  'exit 1' > "$TRUNCBIN/pip-audit"
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[]}],"fixes":[]}'"'" \
  'exit 0' > "$CLEANBIN/pip-audit"
chmod +x "$TRUNCBIN/pip-audit" "$CLEANBIN/pip-audit"

# The stub sets of (e1) and (e2): pip-audit, npm, socket AND trivy, all four. A
# stub that must not be reached exits 97 and writes nothing.
E1BIN="$TMP/stub-e1"
E2BIN="$TMP/stub-e2"
mkdir -p "$E1BIN" "$E2BIN"
printf '%s\n' '#!/usr/bin/env bash' 'exit 97' > "$E1BIN/npm"
printf '%s\n' '#!/usr/bin/env bash' 'exit 97' > "$E1BIN/socket"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$E1BIN/trivy"
printf '%s\n' '#!/usr/bin/env bash' "echo '{}'" 'exit 0' > "$E1BIN/pip-audit"
# npm without a lockfile: the ENOLOCK envelope, exit 1 like the real tool.
printf '%s\n' '#!/usr/bin/env bash' \
  'echo '"'"'{"error":{"code":"ENOLOCK","summary":"This command requires an existing lockfile.","detail":"Try creating one first with: npm i --package-lock-only"}}'"'" \
  'exit 1' > "$E2BIN/npm"
printf '%s\n' '#!/usr/bin/env bash' 'echo '"'"'{"alerts":[]}'"'" 'exit 0' > "$E2BIN/socket"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$E2BIN/trivy"
printf '%s\n' '#!/usr/bin/env bash' 'exit 97' > "$E2BIN/pip-audit"
chmod +x "$E1BIN/npm" "$E1BIN/socket" "$E1BIN/trivy" "$E1BIN/pip-audit" \
  "$E2BIN/npm" "$E2BIN/socket" "$E2BIN/trivy" "$E2BIN/pip-audit"

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for ROOT.
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf 'flask==2.0.0\n' > "$r/requirements.txt"
  echo "$r"
}
# The npm root of (e2): a package.json, NO lockfile, no requirements file.
make_npm_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf '%s\n' '{"name":"enolock-fixture","version":"1.0.0"}' > "$r/package.json"
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
# The exact .degraded line waiver_filter.py writes for report $1, exception class $2.
wf_line() {
  printf 'waiver_filter: report %s unreadable/malformed (%s) — no effective verdict' "$1" "$2"
}
# The exact .degraded line of an npm no-lockfile tool error, code $1.
tool_error_line() {
  printf 'waiver_filter: report npm-audit.json is a tool error (%s) — npm audit NOT performed, coverage DEGRADED' "$1"
}
GATE_NOGO='SCA GATE (effective, waivers applied): NO-GO'
GATE_GO='SCA GATE (effective, waivers applied): GO'

# The LAST audit row of a fixture root, PARSED. Prints `verdict=<v>`, or
# `UNPARSABLE` when the row is not JSON — the exact fate of a row in
# dashboard_readers, which counts it `malformed`.
audit_last() {
  python3 -c 'import json, sys
rows = [l for l in open(sys.argv[1], encoding="utf-8").read().splitlines() if l.strip()]
try:
    rec = json.loads(rows[-1])
except Exception:
    print("UNPARSABLE")
    sys.exit(0)
print("verdict=%s" % rec.get("verdict"))' \
    "$(report_dir "$1")/audit-log.jsonl" 2>/dev/null || echo "UNREADABLE"
}

# Premise: the private kit is the dispatcher and filter beside this suite.
cmp -s "$HERE/sca-scan.sh" "$SCAN" && cmp -s "$HERE/waiver_filter.py" "$KIT/waiver_filter.py" \
  && ok "premise: the private kit is a byte copy of sca-scan.sh and waiver_filter.py beside this suite" \
  || ko "premise: the private kit differs from its source — these arms would measure a phantom"

# ---- (1) a truncated pip-audit.json holding a HIGH ----------------------------
echo "=== (1) truncated pip-audit.json (cut inside a HIGH) + stale GO pivot => rc 1, fail-closed, report named"
R1="$(make_root truncated)"
seed_pivot "$R1"
[ -f "$(report_dir "$R1")/effective-verdict.json" ] \
  && ok "(1) witness: the stale GO pivot is in place before the run" \
  || ko "(1) witness: could not seed the stale pivot"
O1="$(cd "$R1" && PATH="$TRUNCBIN:$PATH" bash "$SCAN" 2>&1)"
rc1=$?
PA1="$(report_dir "$R1")/pip-audit.json"
DEG1="$(report_dir "$R1")/.degraded"
# NON-VACUITY: the report really is there, really holds the HIGH, and really
# does not parse — otherwise every arm below measures some other path.
[ -s "$PA1" ] && LC_ALL=C grep -Fq '"severity":"HIGH"' "$PA1" \
  && ok "(1) witness: pip-audit.json is present, non-empty and carries the HIGH" \
  || ko "(1) witness: no pip-audit.json with the HIGH — the stub did not run"
if python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$PA1" >/dev/null 2>&1; then
  ko "(1) witness: pip-audit.json PARSES — the truncation is not measured"
else
  ok "(1) witness: pip-audit.json does NOT parse (the measured truncation)"
fi
[ "$rc1" -eq 1 ] && ok "(1) rc 1 on an unreadable report" || ko "(1) expected rc 1, got $rc1"
grep -Fxq -- "$(fc_line 3 high)" <<<"$O1" \
  && ok "(1) the fail-closed line names rc=3 and gate_level=high" \
  || ko "(1) fail-closed line 'rc=3, gate_level=high' missing or different"
grep -Fxq -- "$GATE_NOGO" <<<"$O1" && ok "(1) final verdict NO-GO" || ko "(1) final verdict is not NO-GO"
! LC_ALL=C grep -q 'SUMMARY active=' <<<"$O1" \
  && ok "(1) no SUMMARY line — no counters were computed from a partial run" \
  || ko "(1) a SUMMARY line was printed on an unreadable report"
[ ! -f "$(report_dir "$R1")/effective-verdict.json" ] \
  && ok "(1) the stale pivot was removed" || ko "(1) a stale effective-verdict.json is still in place"
# C1: ONLY the `waiver_filter: ` subset, sorted, against the two expected lines.
LC_ALL=C grep '^waiver_filter: ' "$DEG1" 2>/dev/null | LC_ALL=C sort > "$TMP/got1"
printf '%s\n' "$(wf_line pip-audit.json JSONDecodeError)" 'waiver_filter: no fresh effective verdict (rc 3)' \
  | LC_ALL=C sort > "$TMP/want1"
if cmp -s "$TMP/want1" "$TMP/got1"; then
  ok "(1) the waiver_filter lines of .degraded are EXACTLY the report line and the rc 3 line"
else
  ko "(1) waiver_filter lines of .degraded differ — want [$(paste -sd '|' "$TMP/want1")] got [$(paste -sd '|' "$TMP/got1")]"
fi
LC_ALL=C grep '^  COVERAGE DEGRADED: ' <<<"$O1" | LC_ALL=C grep -Fq -- "$(wf_line pip-audit.json JSONDecodeError)" \
  && ok "(1) the COVERAGE DEGRADED banner names pip-audit.json and the exception class" \
  || ko "(1) the COVERAGE DEGRADED banner does not name the unreadable report"
LC_ALL=C grep -Fq 'waiver_filter: UNREADABLE report pip-audit.json (' <<<"$O1" \
  && ok "(1) stderr names the unreadable report" \
  || ko "(1) no 'UNREADABLE report pip-audit.json' on stderr"
a1="$(audit_last "$R1")"
[ "$a1" = "verdict=NO-GO" ] \
  && ok "(1) the audit row PARSES with verdict NO-GO" \
  || ko "(1) expected audit [verdict=NO-GO], got [$a1]"

# ---- (2) control: a clean report ---------------------------------------------
echo "=== (2) control: a clean pip-audit => GO rc 0, fresh pivot, no waiver_filter line"
R2="$(make_root clean)"
seed_pivot "$R2"
O2="$(cd "$R2" && PATH="$CLEANBIN:$PATH" bash "$SCAN" 2>&1)"
rc2=$?
[ "$rc2" -eq 0 ] && ok "(2) rc 0 on a clean, readable report" || ko "(2) expected rc 0, got $rc2"
grep -Fxq -- "$GATE_GO" <<<"$O2" && ok "(2) final verdict GO" || ko "(2) final verdict is not a bare GO"
LC_ALL=C grep -q '^  SUMMARY active=0 ' <<<"$O2" \
  && ok "(2) witness: waiver_filter printed its SUMMARY line" \
  || ko "(2) witness: no SUMMARY line — the clean path was not reached"
[ -f "$(report_dir "$R2")/effective-verdict.json" ] \
  && ! LC_ALL=C grep -Fq 'SEEDED-STALE' "$(report_dir "$R2")/effective-verdict.json" \
  && ok "(2) a FRESH pivot replaced the seeded one" \
  || ko "(2) no fresh pivot after a clean run"
! LC_ALL=C grep -q '^waiver_filter: ' "$(report_dir "$R2")/.degraded" 2>/dev/null \
  && ok "(2) no waiver_filter line in .degraded on a clean run" \
  || ko "(2) a waiver_filter line reached .degraded on a clean run"
! LC_ALL=C grep -Fq 'UNREADABLE report' <<<"$O2" \
  && ok "(2) no UNREADABLE report on stderr" \
  || ko "(2) a clean report was announced unreadable"
a2="$(audit_last "$R2")"
[ "$a2" = "verdict=GO" ] \
  && ok "(2) the audit row PARSES with verdict GO" \
  || ko "(2) expected audit [verdict=GO], got [$a2]"

# ---- (3) a report that DECODES to a shape the parser raises on ---------------
echo "=== (3) pip-audit.json = null (readable JSON, unexpected shape) => rc 3 named, never a traceback"
R3="$(make_root nullshape)"
O3="$(cd "$R3" && PATH="$NULLBIN:$PATH" bash "$SCAN" 2>&1)"
rc3=$?
# NON-VACUITY: the report is READABLE JSON — `null` — so this cell measures the
# parser's failure, not the truncation of (1).
python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8")) is None else 1)' \
  "$(report_dir "$R3")/pip-audit.json" >/dev/null 2>&1 \
  && ok "(3) witness: pip-audit.json is present and decodes to null" \
  || ko "(3) witness: pip-audit.json is absent or is not the JSON null"
[ "$rc3" -eq 1 ] && ok "(3) rc 1 on an unexpected report shape" || ko "(3) expected rc 1, got $rc3"
grep -Fxq -- "$(fc_line 3 high)" <<<"$O3" \
  && ok "(3) the fail-closed line names rc=3 — the report motif, not a configuration fault" \
  || ko "(3) fail-closed line 'rc=3, gate_level=high' missing or different"
grep -Fxq -- "$GATE_NOGO" <<<"$O3" && ok "(3) final verdict NO-GO" || ko "(3) final verdict is not NO-GO"
LC_ALL=C grep '^waiver_filter: ' "$(report_dir "$R3")/.degraded" 2>/dev/null | LC_ALL=C sort > "$TMP/got3"
# PIÈGE 2, amended on purpose (T-01M4Z33N54TX0Q7VHBZATFNR4X): the class was
# AttributeError, raised by the parser. SHAPE_CHECKS now rejects `null` first.
printf '%s\n' "$(wf_line pip-audit.json UnrecognisedShape)" 'waiver_filter: no fresh effective verdict (rc 3)' \
  | LC_ALL=C sort > "$TMP/want3"
if cmp -s "$TMP/want3" "$TMP/got3"; then
  ok "(3) the waiver_filter lines of .degraded are EXACTLY the report line (UnrecognisedShape) and the rc 3 line"
else
  ko "(3) waiver_filter lines of .degraded differ — want [$(paste -sd '|' "$TMP/want3")] got [$(paste -sd '|' "$TMP/got3")]"
fi
LC_ALL=C grep '^  COVERAGE DEGRADED: ' <<<"$O3" | LC_ALL=C grep -Fq -- "$(wf_line pip-audit.json UnrecognisedShape)" \
  && ok "(3) the COVERAGE DEGRADED banner names pip-audit.json" \
  || ko "(3) the COVERAGE DEGRADED banner does not name pip-audit.json"
! LC_ALL=C grep -q '^Traceback ' <<<"$O3" \
  && ok "(3) no Python traceback — the parser's failure is caught and named" \
  || ko "(3) a Python traceback reached the output"
a3="$(audit_last "$R3")"
[ "$a3" = "verdict=NO-GO" ] \
  && ok "(3) the audit row PARSES with verdict NO-GO" \
  || ko "(3) expected audit [verdict=NO-GO], got [$a3]"

# ---- (e1) a READABLE pip-audit.json that SHAPE_CHECKS does not recognise ------
echo "=== (e1) pip-audit.json = {} (readable, unrecognised) => rc 1, fail-closed, UnrecognisedShape named"
RE1="$(make_root e1unrecognised)"
OE1="$(cd "$RE1" && PATH="$E1BIN:$PATH" bash "$SCAN" 2>&1)"
rce1=$?
# NON-VACUITY: the report is there and decodes to an EMPTY OBJECT, the form that
# used to give zero findings and a GO.
python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8")) == {} else 1)' \
  "$(report_dir "$RE1")/pip-audit.json" >/dev/null 2>&1 \
  && ok "(e1) witness: pip-audit.json is present and decodes to {}" \
  || ko "(e1) witness: pip-audit.json is absent or is not {}"
[ "$rce1" -eq 1 ] && ok "(e1) rc 1 on an unrecognised report" || ko "(e1) expected rc 1, got $rce1"
grep -Fxq -- "$(fc_line 3 high)" <<<"$OE1" \
  && ok "(e1) the fail-closed line names rc=3 and gate_level=high" \
  || ko "(e1) fail-closed line 'rc=3, gate_level=high' missing or different"
grep -Fxq -- "$GATE_NOGO" <<<"$OE1" && ok "(e1) final verdict NO-GO" || ko "(e1) final verdict is not NO-GO"
! LC_ALL=C grep -q 'SUMMARY active=' <<<"$OE1" \
  && ok "(e1) no SUMMARY line" \
  || ko "(e1) a SUMMARY line was printed on an unrecognised report"
LC_ALL=C grep '^waiver_filter: ' "$(report_dir "$RE1")/.degraded" 2>/dev/null | LC_ALL=C sort > "$TMP/gote1"
printf '%s\n' "$(wf_line pip-audit.json UnrecognisedShape)" 'waiver_filter: no fresh effective verdict (rc 3)' \
  | LC_ALL=C sort > "$TMP/wante1"
if cmp -s "$TMP/wante1" "$TMP/gote1"; then
  ok "(e1) the waiver_filter lines of .degraded are EXACTLY the UnrecognisedShape line and the rc 3 line"
else
  ko "(e1) waiver_filter lines of .degraded differ — want [$(paste -sd '|' "$TMP/wante1")] got [$(paste -sd '|' "$TMP/gote1")]"
fi
LC_ALL=C grep '^  COVERAGE DEGRADED: ' <<<"$OE1" | LC_ALL=C grep -Fq -- "$(wf_line pip-audit.json UnrecognisedShape)" \
  && ok "(e1) the COVERAGE DEGRADED banner names pip-audit.json (UnrecognisedShape)" \
  || ko "(e1) the COVERAGE DEGRADED banner does not name the unrecognised report"
ae1="$(audit_last "$RE1")"
[ "$ae1" = "verdict=NO-GO" ] \
  && ok "(e1) the audit row PARSES with verdict NO-GO" \
  || ko "(e1) expected audit [verdict=NO-GO], got [$ae1]"

# ---- (e2) npm without a lockfile: ENOLOCK is DEGRADED, named, never rc 3 ------
echo "=== (e2) package.json without lock, npm ENOLOCK, socket {\"alerts\":[]} => GO rc 0, DEGRADED named"
RE2="$(make_npm_root e2enolock)"
OE2="$(cd "$RE2" && PATH="$E2BIN:$PATH" bash "$SCAN" 2>&1)"
rce2=$?
TOOLERR="$(tool_error_line ENOLOCK)"
# NON-VACUITY: the npm stub ran (its ENOLOCK envelope is the report) and the
# root really has no lockfile, so this cell measures the no-lockfile path.
LC_ALL=C grep -Fq '"code":"ENOLOCK"' "$(report_dir "$RE2")/npm-audit.json" 2>/dev/null \
  && ok "(e2) witness: npm-audit.json is the ENOLOCK envelope of the stub" \
  || ko "(e2) witness: npm-audit.json is absent or is not the ENOLOCK envelope"
[ -f "$RE2/package.json" ] && [ ! -e "$RE2/package-lock.json" ] \
  && ok "(e2) witness: package.json present, no package-lock.json" \
  || ko "(e2) witness: the fixture root is not package.json without a lockfile"
[ "$rce2" -eq 0 ] && ok "(e2) rc 0 on a no-lockfile tool error" || ko "(e2) expected rc 0, got $rce2"
grep -Fxq -- "$GATE_GO" <<<"$OE2" && ok "(e2) final verdict GO" || ko "(e2) final verdict is not a bare GO"
LC_ALL=C grep -q '^  SUMMARY active=0 ' <<<"$OE2" \
  && ok "(e2) waiver_filter printed its SUMMARY line (a verdict was computed)" \
  || ko "(e2) no SUMMARY line — the verdict path was not reached"
# The `waiver_filter: ` subset is EXACTLY the tool-error line: no socket line
# (`{"alerts":[]}` is recognised), no rc line (the verdict is fresh).
LC_ALL=C grep '^waiver_filter: ' "$(report_dir "$RE2")/.degraded" 2>/dev/null > "$TMP/gote2"
printf '%s\n' "$TOOLERR" > "$TMP/wante2"
if cmp -s "$TMP/wante2" "$TMP/gote2"; then
  ok "(e2) the waiver_filter lines of .degraded are EXACTLY the ENOLOCK tool-error line"
else
  ko "(e2) waiver_filter lines of .degraded differ — want [$(paste -sd '|' "$TMP/wante2")] got [$(paste -sd '|' "$TMP/gote2")]"
fi
LC_ALL=C grep '^  COVERAGE DEGRADED: ' <<<"$OE2" | LC_ALL=C grep -Fq -- "$TOOLERR" \
  && ok "(e2) the COVERAGE DEGRADED banner names npm-audit.json (ENOLOCK)" \
  || ko "(e2) the COVERAGE DEGRADED banner does not name the npm tool error"
python3 -c 'import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if sys.argv[2] in v.get("notes", []) else 1)' \
  "$(report_dir "$RE2")/effective-verdict.json" "$TOOLERR" >/dev/null 2>&1 \
  && ok "(e2) the fresh pivot carries the tool-error line in its notes" \
  || ko "(e2) no pivot, or its notes do not carry the tool-error line"
ae2="$(audit_last "$RE2")"
[ "$ae2" = "verdict=GO" ] \
  && ok "(e2) the audit row PARSES with verdict GO" \
  || ko "(e2) expected audit [verdict=GO], got [$ae2]"

# ---- THE COUNT ARM ------------------------------------------------------------
ARMS_RUN=$((passed + failed + 1))
[ "$ARMS_RUN" -eq "$EXPECT_ARMS" ] \
  && ok "count: $ARMS_RUN arms ran, EXPECT_ARMS=$EXPECT_ARMS" \
  || ko "count: $ARMS_RUN arms ran but EXPECT_ARMS=$EXPECT_ARMS — a cell did not run, or an arm was added without updating the constant"

echo
echo "================================================================"
echo "sca-report-unreadable: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "An unreadable scanner report is a verdict NOT obtained: NO-GO, named."
