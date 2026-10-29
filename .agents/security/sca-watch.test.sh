#!/usr/bin/env bash
# Suite for sca-watch.sh — the scheduled vulnerability watch (T-00000462, #47).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. ZERO network: the finding is
# emitted by a STUB `pip-audit` on the PATH, never by the real tool.
#
# WHY THIS SUITE IS THE PROOF, AND THE WORKFLOW IS NOT. The nightly workflow that
# schedules this watch is WRITTEN but NOT EXERCISED — the GitHub Actions quota is
# exhausted on this repository (a pilot fact, not re-measured). A scheduled job
# nobody has ever seen run is a plan, not a mechanism. So the proof is moved to
# where it can actually be made: this suite runs sca-watch.sh HERE, on a
# disposable fixture, and checks the three things the watch exists to produce —
# a DATED digest, an audit line marked `mode=watch`, and a refusal to invoke an
# orchestrator that is not there.
#
# THE THREE CASES
#   (a) FINDINGS, scan-only  — exit 1, a dated digest naming the package, and an
#                              audit line carrying both `mode` and `verdict`.
#   (b) CLEAN, scan-only     — exit 0, and the digest REFRESHED to zero. The
#                              refresh is the point: a digest that only ever
#                              grows would keep showing yesterday's findings as
#                              today's, which is worse than no digest at all.
#   (c) ORCHESTRATE with no `claude` on PATH — the documented fallback, an
#                              actionable trace and exit 1, and NEVER a call.
#
# FORM (bash 3.2 floor, T-00000477): heredocs at STATEMENT level only; `grep -F`
# wherever a literal is pinned; `LC_ALL=C` on every grep (L-00000342).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# MUTATION REPLAY. `SCA_WATCH_UNDER_TEST` is read HERE and nowhere else — no
# production site reads it — so it cannot change what the watch DOES. What it
# could do is make a green run READ as a green run of the tracked file when it
# was a green run of some other copy, and a variable exported by mistake would
# carry that misreading into `verify.sh`. So when it is set the suite announces
# it on its own line and the `(def)` premise below stops using the word
# "tracked". A green obtained under an override must be ILLEGIBLE as a green of
# the tracked file.
WATCH="${SCA_WATCH_UNDER_TEST:-$HERE/sca-watch.sh}"
WATCH_LABEL="the tracked sca-watch.sh"
if [ -n "${SCA_WATCH_UNDER_TEST:-}" ]; then
  echo "MUTATION REPLAY — under test: $WATCH (NOT the tracked sca-watch.sh)"
  WATCH_LABEL="the OVERRIDDEN copy $WATCH (NOT the tracked file)"
fi

TMP="$(mktemp -d)"
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
skipped_arms=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }
# A SKIP IS ANNOUNCED **AND COUNTED**. `$2` is how many arms this skip
# suppresses, so that `passed + skipped_arms` is HOST-INVARIANT and the count arm
# at the bottom of this file can be an EXACT equality on every platform. A skip
# that only printed would silently shrink the tally, which is the whole hole the
# count arm exists to close.
skip() { echo "  SKIP $1"; skipped_arms=$((skipped_arms + $2)); }

# THE EXACT NUMBER OF ARMS THIS FILE IS SUPPOSED TO RUN, count arm INCLUDED.
# NOT a floor. A `>=` cannot see a cell that never ran — delete (g) and (h), or
# break the `dashboard_readers` import, and a `>=` stays green on a suite that
# stopped measuring the two things it was written for. Measured before this
# constant existed: a broken import gave `47 passed / 0 failed`, EXIT=0, and
# `grep -rn "49 passed"` over the whole repository returned NOTHING, so no other
# net pinned it either. Adding an arm means editing this number BY HAND; that is
# the intended friction.
# THE IDENTITY IT ASSERTS IS `passed + failed + skipped_arms + 1 == EXPECT_ARMS`
# — arms that RAN, whatever their verdict, plus the count arm itself. Counting
# only `passed` would make the count arm red during a mutation replay, where the
# cells are SUPPOSED to fail; whether an arm passed is already the `failed`
# counter's job. So this one answers a different question: did every cell run at
# all?
# AMENDED, said: 102 -> 119 with the run motif (T-01M4Z395686TR4M7326AQ8ZPHW,
# T-01M4Z39613YVM24WCTWB56N2TH): (k1), 8 arms inside the stub-claude block (its
# named skip moves 18 -> 26), and (k3), 9 arms. 121 -> 124 with (m), 3 arms (a
# reports directory the watch cannot write: its own motif; a named skip of 3
# under uid 0).
EXPECT_ARMS=124

# A fixture root OUTSIDE any repo: sca-watch.sh falls back to `pwd` for ROOT and
# `cd`s into it, so every report path below is inside the disposable tree.
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf 'flask==2.0.0\n' > "$r/requirements.txt"   # pinned, so it is auditable
  echo "$r"
}

report_dir() { echo "$1/.agents/state/local/sca-reports"; }

VULNBIN="$TMP/vulnbin"; mkdir -p "$VULNBIN"
cat > "$VULNBIN/pip-audit" <<'STUB'
#!/usr/bin/env bash
cat <<'JSON'
{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"aliases":["CVE-2023-30861"],"severity":"HIGH","description":"boxed"}]}],"fixes":[]}
JSON
exit 1
STUB
chmod +x "$VULNBIN/pip-audit"

CLEANBIN="$TMP/cleanbin"; mkdir -p "$CLEANBIN"
cat > "$CLEANBIN/pip-audit" <<'STUB'
#!/usr/bin/env bash
cat <<'JSON'
{"dependencies":[{"name":"flask","version":"2.3.3","vulns":[]}],"fixes":[]}
JSON
exit 0
STUB
chmod +x "$CLEANBIN/pip-audit"

# The MEASURED truncation (T-01M4X7W4M2XCFBK1MSY04X2907): a report cut in the
# middle of a HIGH, exit 1 like the real tool on a finding. Cells (j1) and (j3).
TRUNCBIN="$TMP/truncbin"; mkdir -p "$TRUNCBIN"
cat > "$TRUNCBIN/pip-audit" <<'STUB'
#!/usr/bin/env bash
cat <<'JSON'
{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"severity":"HIGH"
JSON
exit 1
STUB
chmod +x "$TRUNCBIN/pip-audit"

# A report that DECODES — to `null` — and that the parser cannot walk (exec-critic
# MAJEUR on lot A: it was a traceback, rc 1, read here as a CONFIGURATION fault).
# Cell (j5).
NULLBIN="$TMP/nullbin"; mkdir -p "$NULLBIN"
printf '%s\n' '#!/usr/bin/env bash' 'echo null' 'exit 1' > "$NULLBIN/pip-audit"
chmod +x "$NULLBIN/pip-audit"

# ---- (a) FINDINGS in scan-only mode ------------------------------------------
echo "=== (a) a finding in scan-only mode => exit 1, dated digest, audit line"
R_A="$(make_root findings)"
OUT_A="$(cd "$R_A" && PATH="$VULNBIN:$PATH" bash "$WATCH" 2>&1)"; rc_a=$?
DIGEST_A="$(report_dir "$R_A")/last-watch-digest.md"
AUDIT_A="$(report_dir "$R_A")/audit-log.jsonl"
# NON-VACUITY FIRST: the watch must really have produced its two artefacts.
[ -s "$DIGEST_A" ] \
  && ok "(a) witness: the digest file exists and is non-empty" \
  || ko "(a) witness: no digest — the watch produced nothing to read"
[ -s "$AUDIT_A" ] \
  && ok "(a) witness: the audit log exists and is non-empty" \
  || ko "(a) witness: no audit line — the run left no dated trace"
[ "$rc_a" -eq 1 ] \
  && ok "(a) findings make the watch exit 1" \
  || ko "(a) expected exit 1, got $rc_a"
# THE DIGEST IS DATED, and the date is on line 1. A digest without a stamp cannot
# be told from a stale one, which is the failure this file exists to prevent.
LC_ALL=C head -1 "$DIGEST_A" | LC_ALL=C grep -qE '^# SCA watch digest — [0-9]{4}-[0-9]{2}-[0-9]{2}T' \
  && ok "(a) line 1 carries the ISO-8601 UTC stamp" \
  || ko "(a) line 1 is not a dated header: [$(LC_ALL=C head -1 "$DIGEST_A")]"
LC_ALL=C grep -qF 'Active findings at gate: **1**' "$DIGEST_A" \
  && ok "(a) the digest counts the finding at the gate" \
  || ko "(a) expected 'Active findings at gate: **1**': $(cat "$DIGEST_A")"
# NAMED, not merely counted: a digest saying "1" without saying WHAT cannot be
# acted on, and the whole point of a watch is that someone acts on it.
LC_ALL=C grep -qF 'flask@2.0.0' "$DIGEST_A" \
  && ok "(a) the digest NAMES the vulnerable package and version" \
  || ko "(a) flask@2.0.0 absent from the digest: $(cat "$DIGEST_A")"
# The audit line is what distinguishes a WATCH run from a gate run in the log.
LC_ALL=C grep -qF '"mode":"watch"' "$AUDIT_A" \
  && ok "(a) the audit line is marked mode=watch" \
  || ko "(a) no \"mode\":\"watch\" in the audit log"
LC_ALL=C grep -qF '"verdict":"NO-GO"' "$AUDIT_A" \
  && ok "(a) the audit line carries the NO-GO verdict" \
  || ko "(a) no \"verdict\":\"NO-GO\" in the audit log"
LC_ALL=C grep -qF '"entry":"sca-watch.sh"' "$AUDIT_A" \
  && ok "(a) the audit line names its entry point" \
  || ko "(a) no \"entry\":\"sca-watch.sh\" in the audit log"

# ---- (b) CLEAN: the digest is REFRESHED, not appended to ----------------------
echo
echo "=== (b) a clean scan => exit 0 and a digest refreshed to zero"
R_B="$(make_root clean)"
# Run 1 WITH the finding, so there is something stale to overwrite. Without this
# first run the refresh assertion would be satisfied by a digest that had simply
# never held anything — vacuously green.
( cd "$R_B" && PATH="$VULNBIN:$PATH" bash "$WATCH" >/dev/null 2>&1 ) || true
DIGEST_B="$(report_dir "$R_B")/last-watch-digest.md"
LC_ALL=C grep -qF 'Active findings at gate: **1**' "$DIGEST_B" \
  && ok "(b) witness: run 1 left a digest showing ONE finding" \
  || ko "(b) witness: run 1 did not leave a finding to clear"
printf 'flask==2.3.3\n' > "$R_B/requirements.txt"
OUT_B="$(cd "$R_B" && PATH="$CLEANBIN:$PATH" bash "$WATCH" 2>&1)"; rc_b=$?
[ "$rc_b" -eq 0 ] \
  && ok "(b) a clean watch exits 0" \
  || ko "(b) expected exit 0, got $rc_b"
LC_ALL=C grep -qF 'Active findings at gate: **0**' "$DIGEST_B" \
  && ok "(b) the digest was REFRESHED to zero" \
  || ko "(b) the digest still shows yesterday's findings: $(cat "$DIGEST_B")"
# The paired absence: the previous count must be GONE, not merely joined by a new
# line. A digest that accumulates reads as a permanent alarm.
! LC_ALL=C grep -qF 'Active findings at gate: **1**' "$DIGEST_B" \
  && ok "(b) the stale count is gone — the digest is rewritten, not appended" \
  || ko "(b) both counts coexist in the digest: $(cat "$DIGEST_B")"
# The audit log, by contrast, IS append-only: two runs, two lines.
AUDIT_B="$(report_dir "$R_B")/audit-log.jsonl"
[ "$(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_B")" -eq 2 ] \
  && ok "(b) the audit log APPENDS (2 watch lines) while the digest replaces" \
  || ko "(b) expected 2 watch lines, got $(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_B")"

# ---- (c) ORCHESTRATE with no `claude` on PATH => documented fallback ----------
echo
echo "=== (c) orchestrate mode without a claude binary => trace, exit 1, no call"
# Build a PATH with `claude`'s own directory removed, and ASSERT the absence
# before trusting the result — an unsimulated absence would measure nothing.
if command -v claude >/dev/null 2>&1; then
  cl_dir="$(cd "$(dirname "$(command -v claude)")" 2>/dev/null && pwd)"
  CPATH=""; _oldifs="$IFS"; IFS=':'
  for d in $PATH; do
    [ -n "$d" ] || continue
    case "$(cd "$d" 2>/dev/null && pwd)" in
      "$cl_dir") continue ;;
    esac
    CPATH="${CPATH:+$CPATH:}$d"
  done
  IFS="$_oldifs"
else
  CPATH="$PATH"
fi
R_C="$(make_root orchestrate)"
OUT_C="$(cd "$R_C" && PATH="$VULNBIN:$CPATH" SCA_WATCH_MODE=orchestrate bash "$WATCH" 2>&1)"; rc_c=$?
if PATH="$CPATH" command -v claude >/dev/null 2>&1; then
  skip "(c): impossible de simuler l'absence de \`claude\` — le repli n'est PAS mesuré" 5
else
  ok "(c) premise: claude is really absent from the curated PATH"
  [ "$rc_c" -eq 1 ] \
    && ok "(c) the fallback still exits 1 — findings are never swallowed" \
    || ko "(c) expected exit 1, got $rc_c"
  LC_ALL=C grep -qF 'scan-only mode' <<<"$OUT_C" \
    && ok "(c) the run says it fell back, instead of pretending to orchestrate" \
    || ko "(c) no fallback trace in the output: $OUT_C"
  # The absence assertion that matters, paired with the positives above: nothing
  # was handed to an orchestrator, so no log of one can exist.
  [ ! -f "$(report_dir "$R_C")/last-watch-run.log" ] \
    && ok "(c) no orchestrator run log — the call was never attempted" \
    || ko "(c) an orchestrator log exists: a call was made without a binary"
  # And the run is still traced: a fallback is not an excuse to log nothing.
  LC_ALL=C grep -qF '"watch_mode":"orchestrate"' "$(report_dir "$R_C")/audit-log.jsonl" \
    && ok "(c) the audit line records the mode that was ASKED for" \
    || ko "(c) the requested watch_mode is missing from the audit log"
fi

# ==============================================================================
# (d)(e)(f) — THE UNEXPECTED EXIT CODE, AND WHAT IT MUST NOT BE ALLOWED TO DO.
#
# WHY THESE THREE EXIST (L-00000393). The arms above exercise rc 0, 1 and 2 —
# the codes the watch EXPECTS. That is precisely why a false GO survived under a
# green suite: the failure lived at rc 126, which no arm ever produced. A suite
# proves only what it EXERCISES, and the missing arm is always the one that would
# have gone red. These three exercise the OTHER side of the boundary.
#
# HOW THE SCANNER IS STUBBED. sca-watch.sh resolves the scanner as
# "$SCRIPT_DIR/sca-scan.sh" — its OWN directory. Driving its exit code therefore
# means running a COPY of the watch beside a fake scanner, in a disposable
# directory. THE TRACKED TREE IS NEVER TOUCHED, and the copy is asserted
# byte-identical to the tracked file before anything is concluded from it: a
# drifted copy would measure a program nobody ships.
# ==============================================================================
echo
echo "=== (d)(e)(f) unexpected exit codes and audit-log integrity"

PY_T=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY_T="$c"; break; }; done

STUBDIR="$TMP/watchstub"; mkdir -p "$STUBDIR"
cp "$WATCH" "$STUBDIR/sca-watch.sh"
cat > "$STUBDIR/sca-scan.sh" <<'STUB'
#!/usr/bin/env bash
echo "stub sca-scan.sh: exiting ${STUB_RC:-126} without scanning anything"
exit "${STUB_RC:-126}"
STUB
chmod +x "$STUBDIR/sca-scan.sh"
# WHAT THIS PREMISE ACTUALLY CHECKS — and what it does NOT. It used to be
# commented "NON-VACUITY OF THE WHOLE HARNESS: if the copy ever drifts from the
# tracked file…", and that claim was FALSE: the copy is made from `$WATCH` four
# lines up, so it cannot drift from `$WATCH`, and under an override `$WATCH` is
# not the tracked file at all — the arm has no way to notice. It is not vacuous
# (a truncated or failed `cp` reddens it, and so would a mutation step inserted
# between the `cp` and here), it is simply much WEAKER than it claimed. So it now
# says what it does.
# COMPARING AGAINST `git show HEAD:…` WAS CONSIDERED AND REJECTED, deliberately:
# it reddens on every uncommitted edit — including the changeset that adds this
# comment — and a suite that goes red while you work is a suite people switch
# off. That is the false red banned at run-bash-tests.sh:29-31. The guarantee
# "the file under test is the one git tracks" is therefore ABSENT here, by
# choice, and the second arm below is what covers the part that can be covered
# without inventing a red: that the DEFAULT target is still the in-tree path.
cmp -s "$WATCH" "$STUBDIR/sca-watch.sh" \
  && ok "(def) premise: the copy in the stub dir is byte-identical to its source, $WATCH_LABEL" \
  || ko "(def) premise: the copy DIFFERS from its source $WATCH_LABEL — a failed cp, or a mutation slipped in between: these arms would measure a phantom"
# NON-VACUOUS, and here is the mutation that proves it: point `WATCH` at anything
# other than `$HERE/sca-watch.sh` with no override set and this arm goes red. It
# pins that a run WITHOUT `SCA_WATCH_UNDER_TEST` really exercises the file beside
# this suite, which is the only sense in which a green here is a green of the
# shipped watch.
if [ -n "${SCA_WATCH_UNDER_TEST:-}" ]; then
  skip "(def-path): override actif — la cible par défaut n'est PAS vérifiée (c'est le but de l'override)" 1
elif [ "$WATCH" = "$HERE/sca-watch.sh" ]; then
  ok "(def) premise: with no override, the file under test IS the in-tree \$HERE/sca-watch.sh"
else
  ko "(def) premise: no override is set, yet WATCH='$WATCH' is not \$HERE/sca-watch.sh — this run measures some other file while reporting on the tracked one"
fi

# ---- (d) A DEGRADED RUN MUST NOT LEAVE YESTERDAY'S COUNTERS UNDER TODAY'S DATE
echo
echo "=== (d) a degraded run REPLACES the digest instead of refreshing it"
R_D="$(make_root degraded)"
printf 'flask==2.3.3\n' > "$R_D/requirements.txt"
# Run 1 is REAL and CLEAN: it fills the digest with genuine counters. Without it
# the assertion below would be satisfied by a digest that had never held
# anything — vacuously green, and blind to the defect it exists to catch.
( cd "$R_D" && PATH="$CLEANBIN:$PATH" bash "$WATCH" >/dev/null 2>&1 ) || true
DIGEST_D="$(report_dir "$R_D")/last-watch-digest.md"
LC_ALL=C grep -qF 'Active findings at gate: **0**' "$DIGEST_D" \
  && ok "(d) witness: the clean run really filled the digest with counters" \
  || ko "(d) witness: no counters to overwrite — this arm would prove nothing"
# Run 2 dies with a code the watch does not recognise.
OUT_D="$(cd "$R_D" && STUB_RC=126 bash "$STUBDIR/sca-watch.sh" 2>&1)"; rc_d=$?
[ "$rc_d" -eq 3 ] \
  && ok "(d) an unrecognised scanner exit yields watch exit 3 (DEGRADED)" \
  || ko "(d) expected exit 3, got $rc_d"
# THE ASSERTION THAT MATTERS. The digest is what a HUMAN reads. Leaving the old
# counters in place under a fresh timestamp is the same lie as the false GO this
# task closes, moved onto the surface people actually look at.
! LC_ALL=C grep -qF 'Active findings at gate' "$DIGEST_D" \
  && ok "(d) the stale counters are GONE — no figures are shown for a run that did not happen" \
  || ko "(d) yesterday's counters survived under today's timestamp: $(cat "$DIGEST_D")"
LC_ALL=C grep -qF 'DEGRADED — no scan was performed' "$DIGEST_D" \
  && ok "(d) the digest says WHY there are no figures" \
  || ko "(d) no DEGRADED banner in the digest: $(cat "$DIGEST_D")"
# The audit log records the same fact, so the two surfaces cannot disagree.
LC_ALL=C grep -qF '"verdict":"DEGRADED"' "$(report_dir "$R_D")/audit-log.jsonl" \
  && ok "(d) the audit log carries the DEGRADED verdict too" \
  || ko "(d) the audit log does not record the degradation"

# ---- (e) A LINE OF THE AUDIT LOG CANNOT BE FORGED FROM THE ENVIRONMENT -------
echo
echo "=== (e) SCA_WATCH_MODE cannot forge an audit-log line"
# `audit-log.jsonl` is append-only and is THE file a reader consults to know
# whether the watch ran. `$MODE` comes from the environment; interpolated raw, a
# newline in it writes a WHOLE EXTRA LINE — a verdict that no run ever produced,
# sitting in the evidence file.
FORGE_NL="$(printf 'scan-only\n{"ts":"1999-01-01T00:00:00Z","mode":"watch","entry":"sca-watch.sh","verdict":"GO","watch_mode":"forge"}')"
R_E="$(make_root forge_newline)"
OUT_E="$(cd "$R_E" && PATH="$VULNBIN:$PATH" SCA_WATCH_MODE="$FORGE_NL" bash "$WATCH" 2>&1)"; rc_e=$?
AUDIT_E="$(report_dir "$R_E")/audit-log.jsonl"
# PAIRED POSITIVE WITNESS, and the arm is worthless without it: prove the PAYLOAD
# is genuinely dangerous by running it through the UNHARDENED form. If this shows
# 1 line, the payload is inert and every assertion below is green for nothing.
WITNESS="$TMP/witness.jsonl"
printf '{"ts":"%s","mode":"watch","entry":"sca-watch.sh","verdict":"%s","watch_mode":"%s"}\n' \
  "1999-01-01T00:00:00Z" "NO-GO" "$FORGE_NL" > "$WITNESS"
[ "$(LC_ALL=C grep -c '' "$WITNESS")" -eq 2 ] \
  && ok "(e) witness: the payload DOES forge a second line through a raw printf" \
  || ko "(e) witness: the payload is inert ($(LC_ALL=C grep -c '' "$WITNESS") line(s)) — this arm measures nothing"
# COUNT THE WATCH ROWS, NOT THE FILE'S LINES — and the difference is a measured
# correction, not a nicety. A single run legitimately appends TWO rows to this
# log: sca-scan.sh writes its own (`"mode":"scan"`) and the watch writes its own
# (`"mode":"watch"`). A raw line count therefore reads 2 on a perfectly hardened
# run, which would have made this arm red against the correct implementation —
# the very trap that gets "repaired" by weakening an assertion. What forging
# would produce is an EXTRA WATCH ROW, so that is what is counted.
[ "$(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_E")" -eq 1 ] \
  && ok "(e) EXACTLY ONE watch row for one run — no line was forged" \
  || ko "(e) $(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_E") watch rows — a row was forged"
LC_ALL=C grep -qF '"verdict":"NO-GO"' "$AUDIT_E" \
  && ok "(e) the recorded verdict is the REAL one (NO-GO), not the injected GO" \
  || ko "(e) the real verdict is missing: $(cat "$AUDIT_E")"
# The injected fragment must survive ONLY as escaped DATA inside the watch_mode
# string — never as a record of its own. So the test is not "1999 is absent from
# the bytes" (it legitimately appears, escaped, inside the value): it is that no
# ROW carries the forged verdict. `"verdict":"GO"` cannot match `"NO-GO"`, and
# cannot match the payload either, whose quotes are backslash-escaped.
! LC_ALL=C grep -qF '"verdict":"GO"' "$AUDIT_E" \
  && ok "(e) no row carries the injected GO verdict — the payload stayed DATA" \
  || ko "(e) a forged GO record landed in the audit log: $(cat "$AUDIT_E")"

# The quote-only variant: no newline, so it cannot forge a LINE, but a bare `"`
# truncates the JSON object and makes the record unparseable — a row the reader's
# tooling silently drops is a row that might as well not exist.
FORGE_Q='scan-only","verdict":"GO'
R_E2="$(make_root forge_quote)"
OUT_E2="$(cd "$R_E2" && PATH="$VULNBIN:$PATH" SCA_WATCH_MODE="$FORGE_Q" bash "$WATCH" 2>&1)"; rc_e2=$?
AUDIT_E2="$(report_dir "$R_E2")/audit-log.jsonl"
[ "$(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_E2")" -eq 1 ] \
  && ok "(e2) the quote payload still yields exactly one watch row" \
  || ko "(e2) $(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_E2") watch rows"
if [ -z "$PY_T" ]; then
  skip "(e-json): aucun interpréteur python — la validité JSON des lignes n'est PAS mesurée" 2
else
  # THE assertion no grep can make: EVERY row must still PARSE. A bare `\"` does
  # not forge a line, it TRUNCATES the object — and a row the reader's tooling
  # silently drops is a row that might as well never have been written. The
  # script prints nothing and fails if any row is malformed.
  for pair in "$AUDIT_E:newline" "$AUDIT_E2:quote"; do
    f="${pair%:*}"; label="${pair##*:}"
    got="$("$PY_T" -c '
import json,sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
watch = [r for r in rows if r.get("mode") == "watch"]
forged = [r for r in rows if r.get("verdict") == "GO" or str(r.get("ts", "")).startswith("1999")]
print(len(watch), len(forged), (watch[0].get("verdict") if watch else "-"))
' "$f" 2>/dev/null)"
    if [ -z "$got" ]; then
      ko "(e-json/$label) a row does NOT parse as JSON: $(cat "$f")"
    else
      case "$got" in
        "1 0 NO-GO") ok "(e-json/$label) every row parses; ONE watch row, ZERO forged, verdict=NO-GO" ;;
        *) ko "(e-json/$label) expected [1 0 NO-GO] (watch/forged/verdict), got [$got]" ;;
      esac
    fi
  done
fi

# ---- (f) ANY unexpected code, not just the one that was measured ------------
echo
echo "=== (f) an arbitrary unexpected exit code (137, OOM-kill) => exit 3"
# The original hole was rc=126. Pinning 126 alone would prove the fix for the
# code that was measured and nothing else — the enumeration defect, one level up.
# 137 is a process killed by SIGKILL: nothing about it is special, which is the
# point. What is asserted is the BOUND.
R_F="$(make_root oomkill)"
OUT_F="$(cd "$R_F" && STUB_RC=137 bash "$STUBDIR/sca-watch.sh" 2>&1)"; rc_f=$?
[ "$rc_f" -eq 3 ] \
  && ok "(f) rc=137 degrades exactly like rc=126 — a BOUND, not a list of codes" \
  || ko "(f) expected exit 3 for rc=137, got $rc_f"
LC_ALL=C grep -qF 'DEGRADED' <<<"$OUT_F" \
  && ok "(f) the run SAYS it is degraded instead of falling through quietly" \
  || ko "(f) no DEGRADED announcement: $OUT_F"
# The paired absence: the cheap path's reassuring sentence must never appear on a
# run that scanned nothing. It is the exact sentence a reader takes as "fine".
! LC_ALL=C grep -qF 'no action needed' <<<"$OUT_F" \
  && ok "(f) 'no action needed' is NEVER printed for a run that never scanned" \
  || ko "(f) the degraded run borrowed the clean path's wording: $OUT_F"
LC_ALL=C grep -qF '"verdict":"DEGRADED"' "$(report_dir "$R_F")/audit-log.jsonl" \
  && ok "(f) the audit log records DEGRADED for rc=137 as well" \
  || ko "(f) rc=137 was not recorded as degraded"

# ==============================================================================
# (g)(h) — THE TWO WAYS `$MODE` STILL REACHED THE JSON UNFILTERED.
#
# (e) above closed the newline and the bare quote. Two vectors survived, and they
# are NOT of the same weight — saying which is which is half the value of these
# two cells:
#   (h) AN INVALID UTF-8 BYTE — the only one of the two with an observable victim
#       in this repo TODAY. `dashboard_readers.read_new_records`, the production
#       reader behind the dashboard's Security view, splits on `b"\n"` and
#       decodes each line, counting a `UnicodeDecodeError` as `malformed`. So one
#       bad byte in SCA_WATCH_MODE makes a REAL run DISAPPEAR from that view: not
#       a forged row, a MISSING one. This cell measures it with that very
#       function — same reader, before and after.
#   (g) THE NON-C0 `splitlines()` SEPARATORS: U+2028, U+2029 and U+0085 (NEL) —
#       PROSPECTIVE, and labelled so deliberately. All three are JSON-valid and
#       forge nothing for a reader that splits on `b"\n"`, which is what every
#       reader in this repo does. The cell exists for a consumer that splits with
#       Python's `str.splitlines()`, which DOES split on all three. No such
#       consumer exists here yet; the arm is the guard for the day one appears.
#       AND WHAT THAT CONSUMER LOSES IS THE REAL ROW, NOT A FORGED ONE. Measured
#       on the FULLY unhardened watch through the mutation replay: this cell's
#       payload yields `[splitlines-unparsable=6 forged=0]` — the shell has
#       already backslash-escaped its quotes, so nothing in it parses. Strip the
#       NEL substitution ALONE and the same probe reads
#       `[splitlines-unparsable=3 forged=0]`: still forged=0. That is class (h)
#       damage, a line LOST, not a readable fabricated verdict. The paired
#       witness in this cell reaches `forged=2` only because it writes the
#       payload through a RAW `printf`, bypassing that escaping on purpose.
#       NEL was MISSED on the first pass and is why this cell is now three
#       separators wide: it is the one `splitlines()` separator that is neither
#       C0 (so `tr -d '\000-\037\177'` never sees its \xc2\x85) nor part of the
#       U+2028/9 pair, and it is valid UTF-8 so `iconv -c` keeps it. The class
#       stands at 10 of the 10 code points `str.splitlines()` splits on — a
#       COUNT, re-derivable, never the word "closed".
#
# BOTH CELLS CALL `/bin/bash "$WATCH"` EXPLICITLY, and that is not cosmetic. The
# `bash` first on PATH on a dev box is typically a Homebrew 5.x (measured 5.3.15
# here), so every arm above measures 5.x — while the cron documented at the top
# of sca-watch.sh has PATH=/usr/bin:/bin and runs it under 3.2.57. Without these
# two invocations the 3.2 floor this file claims to respect is never exercised at
# all, and `$'\xHH'` plus `${v//p/r}` are exactly 3.2-era constructs.
#
# ASSERTIONS BEAR ON THE PARSED STRUCTURE, NEVER ON THE FILE'S LINE COUNT
# (L-00000394): one run legitimately appends TWO rows here — sca-scan.sh its own
# `"mode":"scan"`, the watch its own `"mode":"watch"`. See (e)'s note above; the
# assertion that got it wrong once already is the one that counts lines.
#
# NO SEPARATOR IS EVER WRITTEN RAW IN THIS FILE. Every occurrence below is built
# from an octal escape in shell — `printf '\342\200\250'` — and reaches the
# Python probe as an ARGUMENT, never as a literal pasted into its source. An
# invisible byte sitting in source is the very defect these cells close, and it
# is also the one a later editor deletes without ever seeing it.
# ==============================================================================

# ---- (v) WHICH BASH RUNS THE BODY, AND WHETHER THE 3.2 FLOOR IS REAL ---------
echo
echo "=== (v) which bash actually runs the watch in (g) and (h)"
# This file CLAIMS a bash 3.2 floor (T-00000477) and (g)/(h) call `/bin/bash`
# explicitly to exercise it. That exercises 3.2 only where `/bin/bash` HAPPENS to
# be 3.2 — true on macOS, FALSE on the ubuntu and windows legs, where it is 5.x.
# Before this arm nothing printed which one had run, so a green suite read as
# "the floor was tested" on all three CI legs when two of them had tested 5.x.
# The version of the BODY's interpreter is now measured and stated; where the
# floor is absent the answer is a NAMED, COUNTED skip, never a silent green.
BODY_BASH="$(/bin/bash -c 'printf "%s.%s" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}"' 2>/dev/null)"
echo "  interpreters: (g)/(h) run the watch under /bin/bash ${BODY_BASH:-unknown} — this suite itself runs under $BASH_VERSION"
case "$BODY_BASH" in
  3.2)
    ok "(v) the 3.2 floor IS exercised here: /bin/bash is $BODY_BASH and (g)+(h) invoke it explicitly" ;;
  "")
    skip "(v): /bin/bash n'a rendu aucune version — plancher 3.2 NON mesuré sur cet hôte" 1 ;;
  *)
    skip "(v): plancher 3.2 NON mesuré sur cet hôte — /bin/bash est $BODY_BASH, donc (g) et (h) ont tourné sous $BODY_BASH et non sous 3.2" 1 ;;
esac

# ONE probe for (g), used on BOTH sides — the raw payload and the hardened
# journal — so before and after are the same measurement. It splits with
# `splitlines()`, which is the entire point of (g), and it NEVER raises: an
# unparseable fragment is COUNTED, because on the raw side counting them is
# precisely what shows what the separator did.
sep_probe() {
  "$PY_T" -c '
import json, sys
rows = []
bad = 0
for line in open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except Exception:
        bad += 1
watch = [r for r in rows if isinstance(r, dict) and r.get("mode") == "watch"]
forged = [r for r in rows if isinstance(r, dict) and (r.get("verdict") == "GO" or str(r.get("ts", "")).startswith("1999"))]
if bad:
    print("splitlines-unparsable=%d forged=%d" % (bad, len(forged)))
else:
    print(len(watch), len(forged), (watch[0].get("verdict") if watch else "-"))
' "$1" 2>/dev/null
}

# The separators are handed to the probe below as argv, built here from octal
# escapes so that no invisible byte lives in any source line. NEL is built the
# same way and for the same reason — `\302\205` is two bytes that a reviewer
# cannot see, and the first pass of this task seeded two such bytes by accident.
SEP28="$(printf '\342\200\250')"
SEP29="$(printf '\342\200\251')"
SEPNEL="$(printf '\302\205')"

# The paired POSITIVE of (g)'s two byte-level absences: the separators must
# survive as escaped DATA inside the value, not be deleted. A field silently
# emptied of what the operator actually set is a different defect, not a fix.
wm_probe() {
  "$PY_T" -c '
import json, sys
sep28, sep29, sepnel = sys.argv[2], sys.argv[3], sys.argv[4]
wm = ""
for line in open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except Exception:
        continue
    if isinstance(r, dict) and r.get("mode") == "watch":
        wm = r.get("watch_mode", "")
print("sep28=%d sep29=%d nel=%d starts=%d" % (
    sep28 in wm, sep29 in wm, sepnel in wm, wm.startswith("scan-only")))
' "$1" "$SEP28" "$SEP29" "$SEPNEL" 2>/dev/null
}

# The (h) probe is the PRODUCTION reader itself, imported from .agents/bin. Using
# the real function instead of a re-implementation is what makes the witness a
# measurement of the actual consumer rather than of a model of it.
reader_probe() {
  "$PY_T" -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from dashboard_readers import read_jsonl_file
records, malformed = read_jsonl_file(Path(sys.argv[1]))
watch = [r for r in records if r.get("mode") == "watch"]
print("watch=%d malformed=%d verdict=%s mode=%s" % (
    len(watch), malformed,
    watch[0].get("verdict") if watch else "-",
    watch[0].get("watch_mode") if watch else "-"))
' "$1" "$HERE/../bin" 2>/dev/null
}

# ---- (g) U+2028/U+2029 must stay DATA (PROSPECTIVE hardening) ----------------
echo
echo "=== (g) U+2028/U+2029/U+0085 in SCA_WATCH_MODE stay DATA (prospective)"
# The payload forges TWO complete, WELL-DELIMITED JSON objects: the first between
# two U+2028, the second between two U+0085 (NEL), with a U+2029 splitting the
# scraps in between and a final scrap that absorbs the record template's trailing
# `"}`. The delimiting is what makes the witness show a FORGE rather than a mere
# LOSS: an object left ragged yields unparseable fragments, i.e. a corrupted row,
# which proves nothing about forging a row.
# ONE OBJECT PER SEPARATOR FAMILY IS WHAT MAKES THE WITNESS DISCRIMINATE. Its
# expected value is `forged=2`, and MEASURED: neutralise NEL alone and the same
# probe reads `splitlines-unparsable=3 forged=1`. So `forged=2` is unreachable
# unless NEL genuinely splits for `str.splitlines()` — the arm cannot pass by
# accident on the strength of U+2028 alone.
FORGE_U="$(printf 'scan-only\342\200\250{"ts":"1999-01-01T00:00:00Z","mode":"watch","entry":"sca-watch.sh","verdict":"GO","watch_mode":"forge28"}\342\200\250tail\342\200\251mid\302\205{"ts":"1999-01-01T00:00:00Z","mode":"watch","entry":"sca-watch.sh","verdict":"GO","watch_mode":"forgeNEL"}\302\205end')"
R_G="$(make_root forge_sep)"
OUT_G="$(cd "$R_G" && PATH="$VULNBIN:$PATH" SCA_WATCH_MODE="$FORGE_U" /bin/bash "$WATCH" 2>&1)"; rc_g=$?
AUDIT_G="$(report_dir "$R_G")/audit-log.jsonl"
if [ -z "$PY_T" ]; then
  skip "(g): aucun interpréteur python — la structure PARSÉE n'est PAS mesurée" 3
else
  # PAIRED WITNESS, and its SHAPE is the correction. A witness that only asserts
  # "anything but 1 0 NO-GO" is satisfied by an EMPTY output from a probe that
  # crashed — it would pass while measuring nothing at all. So this one demands a
  # POSITIVE and PRECISE value: four unparseable fragments and EXACTLY TWO forged
  # records that PARSE — one delimited by U+2028, one by NEL. Anything else, the
  # empty string included, is an inert witness and says so.
  WITNESS_U="$TMP/witness_u.jsonl"
  printf '{"ts":"%s","mode":"watch","entry":"sca-watch.sh","verdict":"%s","watch_mode":"%s"}\n' \
    "2026-01-01T00:00:00Z" "NO-GO" "$FORGE_U" > "$WITNESS_U"
  w_g="$(sep_probe "$WITNESS_U")"
  case "$w_g" in
    "splitlines-unparsable=4 forged=2")
      ok "(g) witness: through a raw printf the payload forges TWO records that PARSE (one per separator family) for a splitlines() reader" ;;
    *)
      ko "(g) TEMOIN INERTE: expected [splitlines-unparsable=4 forged=2], got [$w_g] — this cell would measure nothing" ;;
  esac
  a_g="$(sep_probe "$AUDIT_G")"
  case "$a_g" in
    "1 0 NO-GO")
      ok "(g) hardened: every splitlines() fragment parses; ONE watch row, ZERO forged, verdict=NO-GO" ;;
    *)
      ko "(g) expected [1 0 NO-GO] (watch/forged/verdict) from the hardened journal, got [$a_g]" ;;
  esac
  m_g="$(wm_probe "$AUDIT_G")"
  case "$m_g" in
    "sep28=1 sep29=1 nel=1 starts=1")
      ok "(g) all THREE separators survive as ESCAPED DATA in watch_mode, and the real mode is still readable at its head" ;;
    *)
      ko "(g) expected [sep28=1 sep29=1 nel=1 starts=1] from the hardened journal, got [$m_g]" ;;
  esac
fi
# The byte-level absences, which need no interpreter: what must never reach the
# file is the RAW separator.
# THE FAILURE MESSAGES NAME THE MEASURED CONSEQUENCE, NOT A GUESSED ONE. They
# used to say a `splitlines()` reader "would see a forged row", and the probe a
# few lines above refuted that IN THE SAME RUN by printing
# `[splitlines-unparsable=6 forged=0]` against fully unhardened code. What that
# reader actually loses is the REAL row.
! LC_ALL=C grep -qF "$SEP28" "$AUDIT_G" \
  && ok "(g) not one RAW U+2028 byte reached the journal" \
  || ko "(g) a raw U+2028 survived into the audit log — a splitlines() reader LOSES the real row (measured, fully unhardened: 6 unparsable fragments, forged=0)"
! LC_ALL=C grep -qF "$SEP29" "$AUDIT_G" \
  && ok "(g) not one RAW U+2029 byte reached the journal either" \
  || ko "(g) a raw U+2029 survived into the audit log — same damage: the real row becomes unreadable for a splitlines() reader"
! LC_ALL=C grep -qF "$SEPNEL" "$AUDIT_G" \
  && ok "(g) not one RAW U+0085 (NEL) byte reached the journal either" \
  || ko "(g) a raw NEL (\\xc2\\x85) survived into the audit log — neither tr nor iconv catches it, so the real row is lost for a splitlines() reader"
[ "$(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_G")" -eq 1 ] \
  && ok "(g) EXACTLY ONE watch row for one run" \
  || ko "(g) $(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_G") watch rows — a row was forged"
[ "$rc_g" -eq 1 ] \
  && ok "(g) the run still reaches its REAL verdict (exit 1) — the payload did not derail it" \
  || ko "(g) expected exit 1, got $rc_g"

# ---- (h) AN INVALID UTF-8 BYTE MUST NOT MAKE THE ROW UNREADABLE -------------
echo
echo "=== (h) an invalid UTF-8 byte in SCA_WATCH_MODE => the row still READS"
# THE BYTE SITS IN THE MIDDLE OF THE VALUE, NOT AT ITS END, and that placement is
# this arm's only defence against a silent pass. Should a platform TRUNCATE on
# the invalid byte instead of passing it through, a byte at the END would leave
# the old form indistinguishable from the hardened one and the mutation replay
# would stay GREEN on uncorrected code. In the middle, a truncation is VISIBLE —
# `scan` is not `scan-only`. (Measured here: BSD `tr` passes the byte through and
# does not truncate, with or without LC_ALL=C, so the replay does redden on this
# box. The placement covers the platforms that were NOT measured.)
# DEL (`\177`) is carried HERE, not in (g): step 2 strips it, and an arm living
# only in the prospective cell would leave DEL untested the day (g) is cut.
FORGE_B="$(printf 'scan\377-only\177')"
DELCH="$(printf '\177')"
BADBYTE="$(printf '\377')"
R_H="$(make_root forge_utf8)"
OUT_H="$(cd "$R_H" && PATH="$VULNBIN:$PATH" SCA_WATCH_MODE="$FORGE_B" /bin/bash "$WATCH" 2>&1)"; rc_h=$?
AUDIT_H="$(report_dir "$R_H")/audit-log.jsonl"
if [ -z "$PY_T" ]; then
  skip "(h): aucun interpréteur python — le LECTEUR DE PRODUCTION n'est PAS interrogé" 2
elif ! "$PY_T" -c 'import sys; sys.path.insert(0, sys.argv[1]); import dashboard_readers' "$HERE/../bin" >/dev/null 2>&1; then
  skip "(h): dashboard_readers non importable — le témoin par le LECTEUR DE PRODUCTION n'est PAS mesuré" 2
else
  # WITNESS, THROUGH THE PRODUCTION READER: prove the payload really costs a row.
  # `read_jsonl_file` on the raw printf must report ZERO records and ONE
  # malformed — the run vanishes from the Security view. Not "some number other
  # than the good one": the exact pair.
  WITNESS_B="$TMP/witness_b.jsonl"
  printf '{"ts":"%s","mode":"watch","entry":"sca-watch.sh","verdict":"%s","watch_mode":"%s"}\n' \
    "2026-01-01T00:00:00Z" "NO-GO" "$FORGE_B" > "$WITNESS_B"
  w_h="$(reader_probe "$WITNESS_B")"
  case "$w_h" in
    "watch=0 malformed=1 verdict=- mode=-")
      ok "(h) witness: the production reader LOSES the raw row entirely (0 records, 1 malformed)" ;;
    *)
      ko "(h) TEMOIN INERTE: expected [watch=0 malformed=1 verdict=- mode=-], got [$w_h] — this cell would measure nothing" ;;
  esac
  # SAME FUNCTION on the hardened journal: the row is back, readable, carrying
  # the REAL verdict, and the mode reads `scan-only` — `iconv -c` dropped the
  # invalid byte and `tr` dropped the DEL, with no marker left behind.
  a_h="$(reader_probe "$AUDIT_H")"
  case "$a_h" in
    "watch=1 malformed=0 verdict=NO-GO mode=scan-only")
      ok "(h) hardened: the SAME production reader finds the row (1 watch, 0 malformed, NO-GO, mode=scan-only)" ;;
    *)
      ko "(h) expected [watch=1 malformed=0 verdict=NO-GO mode=scan-only] from the hardened journal, got [$a_h]" ;;
  esac
fi
! LC_ALL=C grep -qF "$BADBYTE" "$AUDIT_H" \
  && ok "(h) the invalid byte 0xFF never reached the journal" \
  || ko "(h) 0xFF survived into the audit log — the row is unreadable to the production reader"
! LC_ALL=C grep -qF "$DELCH" "$AUDIT_H" \
  && ok "(h) DEL (0x7F) never reached the journal either" \
  || ko "(h) DEL survived into the audit log"
[ "$(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_H")" -eq 1 ] \
  && ok "(h) EXACTLY ONE watch row for one run" \
  || ko "(h) $(LC_ALL=C grep -c '"mode":"watch"' "$AUDIT_H") watch rows"
[ "$rc_h" -eq 1 ] \
  && ok "(h) the run still reaches its REAL verdict (exit 1)" \
  || ko "(h) expected exit 1, got $rc_h"

# ---- (i) A FAIL-CLOSED NO-GO IS A VERDICT NOT OBTAINED, NEVER "FINDINGS" ------
echo
echo "=== (i) fail-closed config (SCA_GATE_LEVEL=medium) => said as a verdict NOT obtained, never as findings"
# WHY (closing review of lot 0, finding 2). rc 1 from sca-scan.sh means EITHER
# real findings OR its fail-closed gate — waiver_filter gave no fresh effective
# verdict. Before the fix the watch read both as findings: in orchestrate mode it
# handed `claude -p` "high/critical findings are present", and in scan-only mode
# it printed "Findings in …", on a run with a CLEAN pip-audit that had
# established none (measured, SCA_GATE_LEVEL=medium).
# NO REAL `claude` IS EVER CALLED HERE: a stub that only records its arguments
# sits FIRST on the PATH, and the orchestrate arms run only once the premise arm
# has seen `claude` resolve to that stub. If it does not, they are skipped by
# name — never run against whatever `claude` the host has.
# MUTANTS, REPLAYED through SCA_WATCH_UNDER_TEST on copies (2026-10-14, bash
# 5.3.15, each checked APPLIED by `cmp` and parsed before its run; control 67 ok
# + the named def-path skip): detection forced to 0 -> 6 KO (i1)(i3); fail-closed
# prompt swapped for the findings one -> 2 KO (i1); scan-only fail-closed branch
# removed -> 2 KO (i3); digest note dropped -> 1 KO (i3); scan output no longer
# captured -> 7 KO (i1)(i3); the pre-fix sca-watch.sh -> 7 KO (i1)(i3).
CLAUDESTUB="$TMP/claudestub"; mkdir -p "$CLAUDESTUB"
cat > "$CLAUDESTUB/claude" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CLAUDE_STUB_LOG"
echo "stub claude: arguments recorded, no model was called"
STUB
chmod +x "$CLAUDESTUB/claude"

# ---- (j) setup: the two motifs of a fail-closed NO-GO -------------------------
# (j1)/(j3) run the REAL scanner and filter beside the watch against the
# truncated report: waiver_filter answers rc 3, the report motif. (j2)/(j2o) need
# a log carrying BOTH motifs, rc=2 AND rc=3, and no single real run produces that
# — the watch runs the single-module form and SCA_GATE_LEVEL is global, so an
# argparse refusal (rc 2) always comes before any report is read. That is the
# --all-modules shape (one fail-closed line per module), so it is produced by a
# fake scanner beside a COPY of the watch, the (d)(e)(f) method, the copy checked
# byte-identical in (j2).
FCSTUBDIR="$TMP/fcstub"; mkdir -p "$FCSTUBDIR"
cp "$WATCH" "$FCSTUBDIR/sca-watch.sh"
cat > "$FCSTUBDIR/sca-scan.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' '  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=2, gate_level=medium, no fresh effective verdict (fail-closed)'
printf '%s\n' '  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=3, gate_level=high, no fresh effective verdict (fail-closed)'
echo 'SCA GATE (effective, waivers applied): NO-GO'
exit 1
STUB
chmod +x "$FCSTUBDIR/sca-scan.sh"
J_MOTIF_CONFIG='verdict SCA non obtenu (fail-closed config)'
J_MOTIF_REPORT='verdict SCA non obtenu (rapport de scanner illisible — voir COVERAGE DEGRADED)'
J_FC3_LINE='  SCA GATE (effective, waivers applied): NO-GO — waiver_filter rc=3, gate_level=high, no fresh effective verdict (fail-closed)'
# The three phrases a report-motif NO-GO must never carry: the configuration's
# remedy, its knob, and the findings' claim. Prints the FIRST one found in the
# text on stdin — empty when none is, so `[ -z ]` is the pass.
forbidden_in() {
  local t p
  t="$(cat)"
  for p in 'fix the configuration' 'SCA_GATE_LEVEL' 'high/critical findings'; do
    if LC_ALL=C grep -qF -- "$p" <<<"$t"; then printf '%s' "$p"; return 0; fi
  done
  return 0
}
# The watch's OWN console lines: the scan output is streamed through the same
# stdout by `tee`, and is not what these cells judge.
watch_lines() { LC_ALL=C grep '^sca-watch: ' <<<"$1"; }

# ---- (k) setup: a run that obtained NO verdict at all ---------------------------
# T-01M4Z395686TR4M7326AQ8ZPHW / T-01M4Z39613YVM24WCTWB56N2TH. A module run of
# --all-modules killed, or the reports lock busy, prints a NO-GO line that names
# no waiver_filter: FC_ANY cannot see it, and the watch read it as FINDINGS.
# (k1)/(k3) run the REAL watch beside the REAL scanner (copies; the scanner
# overridable through SCA_SCAN_UNDER_TEST, read here only, for mutation replay)
# on a root whose ONLY module is sub/ — the bare form falls back to --all-modules
# — with the module run of `sub` KILLED through BASH_ENV, in the one-shot DEBUG
# trap form of sca-gate-failclosed.test.sh (bash 3.2 sources BASH_ENV before `$1`
# is set; measured there). A stale root pivot (active 5, one finding) is seeded:
# under this motif the digest must NOT read it. No heredoc in these cells.
# MUTANTS, REPLAYED 2026-10-16 on copies (exact-once replacement, `cmp`, parsed
# under both bashes; control 119/119 under bash 5.3.15 AND 3.2.57): MW1 the run
# anchor never fires -> 9 KO (k1)(k3), the findings prompt and "Findings in"
# back; MW2 the digest reads the pivot under the run motif -> 2 KO (k1)(k3);
# MB4 of the plan (the module line removed from sca-scan.sh, through
# SCA_SCAN_UNDER_TEST) -> 11 KO (k1)(k3). Same counts under both bashes.
KSCAN_SRC="${SCA_SCAN_UNDER_TEST:-$HERE/sca-scan.sh}"
if [ -n "${SCA_SCAN_UNDER_TEST:-}" ]; then
  echo "MUTATION REPLAY — scanner under test in (k): $KSCAN_SRC (NOT the tracked sca-scan.sh)"
fi
KDIR="$TMP/krun"; mkdir -p "$KDIR"
cp "$WATCH" "$KDIR/sca-watch.sh"
cp "$KSCAN_SRC" "$KDIR/sca-scan.sh"
for f in waiver_filter.py protected_module.py module_discovery.py py_lock_pins.py; do cp "$HERE/$f" "$KDIR/$f"; done
KQUIET="$TMP/kquiet"; mkdir -p "$KQUIET"
printf '%s\n' '#!/bin/sh' 'exit 0' > "$KQUIET/trivy"
chmod +x "$KQUIET/trivy"
KENV="$TMP/k-crash.sh"
printf '%s\n' 'crash_hook() {' '  case "${1:-}" in' '    sub)' '      kill -9 $$' '      ;;' '  esac' '}' \
  "trap 'trap - DEBUG; crash_hook \"\${1:-}\"' DEBUG" > "$KENV"
make_kroot() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports" "$r/sub"
  printf 'flask==2.0.0\n' > "$r/sub/requirements.txt"
  printf '%s\n' '{"generated":"2000-01-01T00:00:00Z","gate_level":"high","active":[{"package":"stalepkg","version":"9.9","ecosystem":"pypi","severity":"HIGH","advisory":"STALE-ADVISORY"}],"waived_accepted":[],"waived_pending":[],"counters":{"active_at_gate":5,"accepted":2,"pending_review":1,"overdue_review":1},"notes":["SEEDED-STALE"]}' \
    > "$r/.agents/state/local/sca-reports/effective-verdict.json"
  echo "$r"
}
K_MOD_LINE='  SCA GATE all-modules (effective, waivers applied): NO-GO — module sub exited rc=137, no verdict obtained (fail-closed)'
J_MOTIF_RUN='verdict SCA non obtenu (run de module interrompu ou verrou occupé — relancer le scan)'
# Every module rc that obtains NO verdict, said whole (closing review T9: the text
# said "outside {0,1,2}" and dropped the 2 without its line and the raw 1).
# REPLAYED 2026-10-16 through SCA_WATCH_UNDER_TEST (a copy beside the real
# siblings), control 121/121: the note's former wording -> (k3) 1 KO, the
# prompt's -> (k1) 1 KO, under bash 5.3.15 AND 3.2.57.
K_RCSET='exited outside {0,1,2}, with 2 without its no-ecosystem line, or with 1 on its no-verdict line'
if [ "$(PATH="$CLAUDESTUB:$PATH" command -v claude)" = "$CLAUDESTUB/claude" ]; then
  ok "(i) premise: \`claude\` resolves to the recording stub, never to a real binary"
  # (i1) orchestrate + fail-closed config.
  R_I1="$(make_root failclosed_orch)"
  ARGS_I1="$TMP/claude_args_i1.txt"
  OUT_I1="$(cd "$R_I1" && CLAUDE_STUB_LOG="$ARGS_I1" SCA_GATE_LEVEL=medium SCA_WATCH_MODE=orchestrate PATH="$CLAUDESTUB:$CLEANBIN:$PATH" bash "$WATCH" 2>&1)"
  [ -s "$ARGS_I1" ] \
    && ok "(i1) witness: the stub was called — the orchestrate branch was really reached" \
    || ko "(i1) witness: the stub was never called — this cell measures nothing: $OUT_I1"
  LC_ALL=C grep -qF 'verdict SCA non obtenu (fail-closed config)' "$ARGS_I1" 2>/dev/null \
    && ok "(i1) the prompt says the SCA verdict was NOT obtained (fail-closed config)" \
    || ko "(i1) the prompt does not name the fail-closed motif"
  ! LC_ALL=C grep -qF 'high/critical findings are present' "$ARGS_I1" 2>/dev/null \
    && ok "(i1) the prompt does NOT claim findings the run never established" \
    || ko "(i1) the prompt claims high/critical findings on a fail-closed run"
  LC_ALL=C grep -qF 'NO-GO — verdict SCA non obtenu (fail-closed config)' <<<"$OUT_I1" \
    && ok "(i1) the console line names the fail-closed motif" \
    || ko "(i1) the console line does not name the fail-closed motif"
  # (i2) orchestrate + a REAL finding: the findings prompt is unchanged.
  R_I2="$(make_root findings_orch)"
  ARGS_I2="$TMP/claude_args_i2.txt"
  OUT_I2="$(cd "$R_I2" && CLAUDE_STUB_LOG="$ARGS_I2" SCA_WATCH_MODE=orchestrate PATH="$CLAUDESTUB:$VULNBIN:$PATH" bash "$WATCH" 2>&1)"
  LC_ALL=C grep -qF 'high/critical findings are present' "$ARGS_I2" 2>/dev/null \
    && ok "(i2) a real finding still hands the findings prompt to the (stub) orchestrator" \
    || ko "(i2) the findings prompt is missing on a real finding: $OUT_I2"
  ! LC_ALL=C grep -qF 'verdict SCA non obtenu' "$ARGS_I2" 2>/dev/null \
    && ok "(i2) no fail-closed motif on a real finding" \
    || ko "(i2) a real finding was announced as a verdict not obtained"
  # (j1) orchestrate + an UNREADABLE report (real scanner, truncated pip-audit).
  R_J1="$(make_root unreadable_orch)"
  ARGS_J1="$TMP/claude_args_j1.txt"
  OUT_J1="$(cd "$R_J1" && CLAUDE_STUB_LOG="$ARGS_J1" SCA_WATCH_MODE=orchestrate PATH="$CLAUDESTUB:$TRUNCBIN:$PATH" bash "$WATCH" 2>&1)"
  CON_J1="$(watch_lines "$OUT_J1")"
  LC_ALL=C grep -Fxq -- "$J_FC3_LINE" "$(report_dir "$R_J1")/last-watch-scan.log" 2>/dev/null \
    && ok "(j1) witness: the real scan failed closed on waiver_filter rc=3 — the report branch is reached" \
    || ko "(j1) witness: no rc=3 fail-closed line in last-watch-scan.log — this cell measures nothing"
  [ -s "$ARGS_J1" ] \
    && ok "(j1) witness: the stub was called — the orchestrate branch was really reached" \
    || ko "(j1) witness: the stub was never called: $CON_J1"
  LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" "$ARGS_J1" 2>/dev/null \
    && ok "(j1) the prompt names the report motif" \
    || ko "(j1) the prompt does not name the report motif"
  LC_ALL=C grep -qF 're-run the scanner, auto-fix nothing' "$ARGS_J1" 2>/dev/null \
    && ok "(j1) the prompt says re-run the scanner, auto-fix nothing" \
    || ko "(j1) the prompt does not say 're-run the scanner, auto-fix nothing'"
  bad_j1p="$(forbidden_in 2>/dev/null < "$ARGS_J1")"
  [ -s "$ARGS_J1" ] && [ -z "$bad_j1p" ] \
    && ok "(j1) the prompt carries neither the configuration's remedy nor a findings claim" \
    || ko "(j1) the prompt of an unreadable-report NO-GO says [$bad_j1p]"
  LC_ALL=C grep -qF -- "NO-GO — $J_MOTIF_REPORT — launching" <<<"$CON_J1" \
    && ok "(j1) the console line names the report motif" \
    || ko "(j1) the console line does not name the report motif: $CON_J1"
  bad_j1c="$(forbidden_in <<<"$CON_J1")"
  [ -z "$bad_j1c" ] \
    && ok "(j1) the console carries neither the configuration's remedy nor a findings claim" \
    || ko "(j1) the console of an unreadable-report NO-GO says [$bad_j1c]"
  # (j2o) orchestrate + BOTH motifs in one log (fake scanner, rc=2 and rc=3).
  R_J2O="$(make_root bothmotifs_orch)"
  ARGS_J2O="$TMP/claude_args_j2o.txt"
  OUT_J2O="$(cd "$R_J2O" && CLAUDE_STUB_LOG="$ARGS_J2O" SCA_WATCH_MODE=orchestrate PATH="$CLAUDESTUB:$PATH" bash "$FCSTUBDIR/sca-watch.sh" 2>&1)"
  CON_J2O="$(watch_lines "$OUT_J2O")"
  [ -s "$ARGS_J2O" ] \
    && ok "(j2o) witness: the stub was called on the two-motif log" \
    || ko "(j2o) witness: the stub was never called: $CON_J2O"
  LC_ALL=C grep -qF -- "$J_MOTIF_CONFIG" "$ARGS_J2O" 2>/dev/null \
    && ok "(j2o) the prompt names the rc=2 motif (fail-closed config)" \
    || ko "(j2o) the prompt drops the rc=2 motif on a two-motif log"
  LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" "$ARGS_J2O" 2>/dev/null \
    && ok "(j2o) the prompt names the rc=3 motif (unreadable report)" \
    || ko "(j2o) the prompt drops the rc=3 motif on a two-motif log"
  LC_ALL=C grep -qF -- "$J_MOTIF_CONFIG + $J_MOTIF_REPORT" <<<"$CON_J2O" \
    && ok "(j2o) the console line names BOTH motifs" \
    || ko "(j2o) the console line does not name both motifs: $CON_J2O"
  ! LC_ALL=C grep -qF 'high/critical findings are present' "$ARGS_J2O" 2>/dev/null \
    && ok "(j2o) the two-motif prompt claims no findings" \
    || ko "(j2o) the two-motif prompt claims high/critical findings"
  # (k1) orchestrate + a module run KILLED (real watch and scanner, BASH_ENV).
  R_K1="$(make_kroot norun_orch)"
  ARGS_K1="$TMP/claude_args_k1.txt"
  OUT_K1="$(cd "$R_K1" && CLAUDE_STUB_LOG="$ARGS_K1" SCA_WATCH_MODE=orchestrate BASH_ENV="$KENV" PATH="$CLAUDESTUB:$KQUIET:$CLEANBIN:$PATH" bash "$KDIR/sca-watch.sh" 2>&1)"
  CON_K1="$(watch_lines "$OUT_K1")"
  DIG_K1="$(report_dir "$R_K1")/last-watch-digest.md"
  LC_ALL=C grep -Fxq -- "$K_MOD_LINE" "$(report_dir "$R_K1")/last-watch-scan.log" 2>/dev/null \
    && ok "(k1) witness: the real scan logged the killed module (rc=137, no verdict obtained)" \
    || ko "(k1) witness: no module line in last-watch-scan.log — this cell measures nothing"
  [ -s "$ARGS_K1" ] \
    && ok "(k1) witness: the stub was called — the orchestrate branch was reached" \
    || ko "(k1) witness: the stub was never called: $CON_K1"
  LC_ALL=C grep -qF -- "$J_MOTIF_RUN" "$ARGS_K1" 2>/dev/null \
    && ok "(k1) the prompt names the run motif" \
    || ko "(k1) the prompt does not name the run motif"
  LC_ALL=C grep -qF 're-run the scan, auto-fix nothing' "$ARGS_K1" 2>/dev/null \
    && ok "(k1) the prompt says re-run the scan, auto-fix nothing" \
    || ko "(k1) the prompt does not say 're-run the scan, auto-fix nothing'"
  LC_ALL=C grep -qF -- "$K_RCSET" "$ARGS_K1" 2>/dev/null \
    && ok "(k1) the prompt names every module rc that obtains no verdict" \
    || ko "(k1) the prompt does not say [$K_RCSET]"
  bad_k1p="$(forbidden_in 2>/dev/null < "$ARGS_K1")"
  [ -s "$ARGS_K1" ] && [ -z "$bad_k1p" ] \
    && ok "(k1) the prompt carries neither the configuration's remedy nor a findings claim" \
    || ko "(k1) the prompt of a no-verdict NO-GO says [$bad_k1p]"
  LC_ALL=C grep -qF -- "NO-GO — $J_MOTIF_RUN — launching" <<<"$CON_K1" \
    && ok "(k1) the console line names the run motif" \
    || ko "(k1) the console line does not name the run motif: $CON_K1"
  bad_k1c="$(forbidden_in <<<"$CON_K1")"
  [ -z "$bad_k1c" ] \
    && ok "(k1) the console carries neither the configuration's remedy nor a findings claim" \
    || ko "(k1) the console of a no-verdict NO-GO says [$bad_k1c]"
  LC_ALL=C grep -qF 'Active findings at gate: **?**' "$DIG_K1" 2>/dev/null \
    && ! LC_ALL=C grep -qF 'STALE-ADVISORY' "$DIG_K1" 2>/dev/null \
    && ok "(k1) the digest reads **?** and lists no finding — the stale pivot was NOT read" \
    || ko "(k1) the digest read the stale pivot: $(cat "$DIG_K1" 2>/dev/null)"
else
  ko "(i) premise: \`claude\` does not resolve to the recording stub — the orchestrate arms are NOT run"
  skip "(i1)(i2)(j1)(j2o)(k1): stub \`claude\` not first on PATH — a real binary could be called, so nothing is run" 27
fi
# (i3) scan-only + fail-closed config.
R_I3="$(make_root failclosed_scan)"
OUT_I3="$(cd "$R_I3" && SCA_GATE_LEVEL=medium PATH="$CLEANBIN:$PATH" bash "$WATCH" 2>&1)"; rc_i3=$?
LC_ALL=C grep -qF 'no fresh effective verdict (fail-closed)' "$(report_dir "$R_I3")/last-watch-scan.log" 2>/dev/null \
  && ok "(i3) witness: the scan really failed closed, and this run's log kept the line" \
  || ko "(i3) witness: no fail-closed line in last-watch-scan.log — this cell measures nothing"
[ "$rc_i3" -eq 1 ] \
  && ok "(i3) still exit 1 — a verdict not obtained is never a pass" \
  || ko "(i3) expected exit 1, got $rc_i3"
LC_ALL=C grep -qF 'verdict SCA non obtenu (fail-closed config)' <<<"$OUT_I3" \
  && ok "(i3) scan-only names the fail-closed motif" \
  || ko "(i3) scan-only does not name the fail-closed motif: $OUT_I3"
! LC_ALL=C grep -qF 'Findings in' <<<"$OUT_I3" \
  && ok "(i3) scan-only does NOT say 'Findings in' when the run established none" \
  || ko "(i3) scan-only says 'Findings in' on a fail-closed run"
LC_ALL=C grep -qF 'scan-only mode' <<<"$OUT_I3" \
  && ok "(i3) the line still says scan-only mode" \
  || ko "(i3) 'scan-only mode' is gone from the fail-closed line"
LC_ALL=C grep -qF 'verdict SCA non obtenu (fail-closed config)' "$(report_dir "$R_I3")/last-watch-digest.md" 2>/dev/null \
  && ok "(i3) the digest carries the motif, not a bare '?'" \
  || ko "(i3) the digest does not name the fail-closed motif"
# (i4) non-regression on cell (a): a REAL finding keeps its wording.
LC_ALL=C grep -qF 'Findings in' <<<"$OUT_A" \
  && ok "(i4) a real finding (cell a) still says 'Findings in'" \
  || ko "(i4) cell (a) lost its 'Findings in' line"
! LC_ALL=C grep -qF 'verdict SCA non obtenu' "$DIGEST_A" \
  && ok "(i4) and its digest carries no fail-closed note" \
  || ko "(i4) the digest of a real finding carries the fail-closed note"

# ---- (j) AN UNREADABLE REPORT IS A VERDICT NOT OBTAINED, NEVER A CONFIG FAULT --
echo
echo "=== (j) unreadable scanner report (waiver_filter rc 3) => its own motif, never the configuration's remedy"
# WHY (T-01M4X7W4M2XCFBK1MSY04X2907, decision S-01M4XXZ7FMDJ3ZQFDVF2FC9WJZ). A
# report present but unreadable now makes waiver_filter answer rc 3 and the
# scan fail closed. Read with the (i) wording, the watch would tell the operator
# to "fix the configuration (e.g. SCA_GATE_LEVEL)" on a run whose configuration
# is fine: the remedy is to re-run the scanner, and the report is named on the
# COVERAGE DEGRADED line. Cells (j1)/(j2o) live in the stub-`claude` block above.
# MUTANTS, REPLAYED through SCA_WATCH_UNDER_TEST on copies (2026-10-14, bash
# 5.3.15, each checked APPLIED by `cmp` and parsed before its run; control 97 ok
# + the named def-path skip): FC_REPORT detection forced to 0 -> 12 KO (j1)(j2)
# (j2o)(j3), "fix the configuration" and SCA_GATE_LEVEL back on the report
# motif; FC_CONFIG reading `FC_REPORT -eq 0` alone (the count dropped) -> 4 KO
# (j2)(j2o), the rc=2 motif lost on a two-motif log; the pre-change sca-watch.sh
# -> 12 KO (j1)(j2)(j2o)(j3). (j5), 2026-10-15, waiver_filter.py beside the
# watch copy mutated, control 101 ok + the def-path skip: its guard narrowed to
# `except ValueError` or to `except (OSError, ValueError)` -> 4 KO each, all
# (j5), "fix the configuration" back on a null report.
# (j2) scan-only + BOTH motifs (fake scanner: rc=2 AND rc=3).
cmp -s "$WATCH" "$FCSTUBDIR/sca-watch.sh" \
  && ok "(j2) premise: the watch beside the fake scanner is byte-identical to $WATCH_LABEL" \
  || ko "(j2) premise: the watch copy beside the fake scanner DIFFERS from its source — (j2)/(j2o) would measure a phantom"
R_J2="$(make_root bothmotifs_scan)"
OUT_J2="$(cd "$R_J2" && bash "$FCSTUBDIR/sca-watch.sh" 2>&1)"; rc_j2=$?
CON_J2="$(watch_lines "$OUT_J2")"
DIGEST_J2="$(report_dir "$R_J2")/last-watch-digest.md"
[ "$(LC_ALL=C grep -c 'no fresh effective verdict (fail-closed)$' "$(report_dir "$R_J2")/last-watch-scan.log" 2>/dev/null)" = "2" ] \
  && ok "(j2) witness: this run's log carries TWO fail-closed lines, rc=2 and rc=3" \
  || ko "(j2) witness: the two-motif log was not produced — this cell measures nothing"
[ "$rc_j2" -eq 1 ] \
  && ok "(j2) still exit 1 on a two-motif fail-closed run" \
  || ko "(j2) expected exit 1, got $rc_j2"
LC_ALL=C grep -qF -- "scan-only mode. $J_MOTIF_CONFIG:" <<<"$CON_J2" \
  && ok "(j2) the console names the rc=2 motif (fail-closed config)" \
  || ko "(j2) the console drops the rc=2 motif: $CON_J2"
LC_ALL=C grep -qF -- "scan-only mode. $J_MOTIF_REPORT:" <<<"$CON_J2" \
  && ok "(j2) the console names the rc=3 motif (unreadable report)" \
  || ko "(j2) the console drops the rc=3 motif: $CON_J2"
LC_ALL=C grep -qF -- "**NO-GO — $J_MOTIF_CONFIG.**" "$DIGEST_J2" 2>/dev/null \
  && ok "(j2) the digest names the rc=2 motif" \
  || ko "(j2) the digest drops the rc=2 motif: $(cat "$DIGEST_J2" 2>/dev/null)"
LC_ALL=C grep -qF -- "**NO-GO — $J_MOTIF_REPORT.**" "$DIGEST_J2" 2>/dev/null \
  && ok "(j2) the digest names the rc=3 motif" \
  || ko "(j2) the digest drops the rc=3 motif: $(cat "$DIGEST_J2" 2>/dev/null)"
# (j3) scan-only + an UNREADABLE report (real scanner, truncated pip-audit).
R_J3="$(make_root unreadable_scan)"
OUT_J3="$(cd "$R_J3" && PATH="$TRUNCBIN:$PATH" bash "$WATCH" 2>&1)"; rc_j3=$?
CON_J3="$(watch_lines "$OUT_J3")"
LOG_J3="$(report_dir "$R_J3")/last-watch-scan.log"
DIGEST_J3="$(report_dir "$R_J3")/last-watch-digest.md"
LC_ALL=C grep -Fxq -- "$J_FC3_LINE" "$LOG_J3" 2>/dev/null \
  && ok "(j3) witness: the real scan failed closed on waiver_filter rc=3 — the report branch is reached" \
  || ko "(j3) witness: no rc=3 fail-closed line in last-watch-scan.log — this cell measures nothing"
if [ -z "$PY_T" ]; then
  skip "(j3-witness): aucun interpréteur python — l'illisibilité de pip-audit.json n'est PAS vérifiée" 1
elif "$PY_T" -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$(report_dir "$R_J3")/pip-audit.json" >/dev/null 2>&1; then
  ko "(j3) witness: pip-audit.json PARSES (or is absent and the probe lied) — the truncation is not measured"
elif [ -s "$(report_dir "$R_J3")/pip-audit.json" ]; then
  ok "(j3) witness: pip-audit.json is present, non-empty and does NOT parse"
else
  ko "(j3) witness: pip-audit.json is absent or empty — the stub did not run"
fi
[ "$rc_j3" -eq 1 ] \
  && ok "(j3) still exit 1 — an unreadable report is never a pass" \
  || ko "(j3) expected exit 1, got $rc_j3"
LC_ALL=C grep -qF -- "scan-only mode. $J_MOTIF_REPORT:" <<<"$CON_J3" \
  && ok "(j3) scan-only names the report motif" \
  || ko "(j3) scan-only does not name the report motif: $CON_J3"
bad_j3c="$(forbidden_in <<<"$CON_J3")"
[ -z "$bad_j3c" ] \
  && ok "(j3) the console carries neither the configuration's remedy nor a findings claim" \
  || ko "(j3) the console of an unreadable-report NO-GO says [$bad_j3c]: $CON_J3"
! LC_ALL=C grep -qF 'Findings in' <<<"$CON_J3" \
  && ok "(j3) scan-only does NOT say 'Findings in' on an unreadable report" \
  || ko "(j3) scan-only says 'Findings in' on an unreadable report"
LC_ALL=C grep -qF -- "**NO-GO — $J_MOTIF_REPORT.**" "$DIGEST_J3" 2>/dev/null \
  && ok "(j3) the digest carries the report motif, not a bare '?'" \
  || ko "(j3) the digest does not name the report motif: $(cat "$DIGEST_J3" 2>/dev/null)"
bad_j3d="$(forbidden_in 2>/dev/null < "$DIGEST_J3")"
[ -s "$DIGEST_J3" ] && [ -z "$bad_j3d" ] \
  && ok "(j3) the digest carries neither the configuration's remedy nor a findings claim" \
  || ko "(j3) the digest of an unreadable-report NO-GO says [$bad_j3d] (or is missing)"
LC_ALL=C grep '^  COVERAGE DEGRADED: ' "$LOG_J3" 2>/dev/null \
  | LC_ALL=C grep -Fq 'waiver_filter: report pip-audit.json unreadable/malformed (JSONDecodeError)' \
  && ok "(j3) the COVERAGE DEGRADED line the motif points to names pip-audit.json" \
  || ko "(j3) no COVERAGE DEGRADED line naming pip-audit.json in last-watch-scan.log"
# (j4) non-regression, the other way: the report motif never leaks onto a
# configuration fault (cell i3) or onto a real finding (cell a).
! LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" <<<"$OUT_I3" \
  && ! LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" "$(report_dir "$R_I3")/last-watch-digest.md" 2>/dev/null \
  && ok "(j4) a config-only fail-closed run (cell i3) carries no report motif, console or digest" \
  || ko "(j4) the report motif leaked onto a configuration fault (cell i3)"
! LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" <<<"$OUT_A" \
  && ! LC_ALL=C grep -qF -- "$J_MOTIF_REPORT" "$DIGEST_A" \
  && ok "(j4) a real finding (cell a) carries no report motif, console or digest" \
  || ko "(j4) the report motif leaked onto a real finding (cell a)"
# (j5) scan-only + a report that DECODES to `null` (real scanner and filter).
R_J5="$(make_root nullshape_scan)"
OUT_J5="$(cd "$R_J5" && PATH="$NULLBIN:$PATH" bash "$WATCH" 2>&1)"
CON_J5="$(watch_lines "$OUT_J5")"
LC_ALL=C grep -Fxq -- "$J_FC3_LINE" "$(report_dir "$R_J5")/last-watch-scan.log" 2>/dev/null \
  && ok "(j5) witness: a null report makes the real scan fail closed on rc=3, not on a traceback's rc=1" \
  || ko "(j5) witness: no rc=3 fail-closed line in last-watch-scan.log for a null report"
LC_ALL=C grep -qF -- "scan-only mode. $J_MOTIF_REPORT:" <<<"$CON_J5" \
  && ok "(j5) scan-only names the report motif for a null report" \
  || ko "(j5) scan-only does not name the report motif for a null report: $CON_J5"
bad_j5c="$(forbidden_in <<<"$CON_J5")"
[ -z "$bad_j5c" ] \
  && ok "(j5) the console of a null-report NO-GO carries neither the configuration's remedy nor a findings claim" \
  || ko "(j5) the console of a null-report NO-GO says [$bad_j5c]: $CON_J5"
LC_ALL=C grep -qF -- "**NO-GO — $J_MOTIF_REPORT.**" "$(report_dir "$R_J5")/last-watch-digest.md" 2>/dev/null \
  && ok "(j5) the digest carries the report motif for a null report" \
  || ko "(j5) the digest does not name the report motif for a null report"

# ---- (k3) A RUN WITH NO VERDICT AT ALL IS ITS OWN MOTIF, NEVER "FINDINGS" --------
echo
echo "=== (k3) scan-only, a module run KILLED => the run motif, the stale pivot NOT read"
# MUTANTS, REPLAYED through SCA_WATCH_UNDER_TEST (watch) and SCA_SCAN_UNDER_TEST
# (scanner) on copies — results recorded in the header note of (k), below (j).
cmp -s "$WATCH" "$KDIR/sca-watch.sh" \
  && ok "(k3) premise: the watch beside the real scanner copy is byte-identical to $WATCH_LABEL" \
  || ko "(k3) premise: the watch copy of (k) DIFFERS from its source — (k1)/(k3) would measure a phantom"
R_K3="$(make_kroot norun_scan)"
OUT_K3="$(cd "$R_K3" && BASH_ENV="$KENV" PATH="$KQUIET:$CLEANBIN:$PATH" bash "$KDIR/sca-watch.sh" 2>&1)"; rc_k3=$?
CON_K3="$(watch_lines "$OUT_K3")"
DIG_K3="$(report_dir "$R_K3")/last-watch-digest.md"
LC_ALL=C grep -Fxq -- "$K_MOD_LINE" "$(report_dir "$R_K3")/last-watch-scan.log" 2>/dev/null \
  && ok "(k3) witness: the real scan logged the killed module" \
  || ko "(k3) witness: no module line in last-watch-scan.log — this cell measures nothing"
[ "$rc_k3" -eq 1 ] \
  && ok "(k3) still exit 1 — a verdict not obtained is never a pass" \
  || ko "(k3) expected exit 1, got $rc_k3"
LC_ALL=C grep -qF -- "scan-only mode. $J_MOTIF_RUN:" <<<"$CON_K3" \
  && ok "(k3) scan-only names the run motif" \
  || ko "(k3) scan-only does not name the run motif: $CON_K3"
bad_k3c="$(forbidden_in <<<"$CON_K3")"
[ -z "$bad_k3c" ] \
  && ok "(k3) the console carries neither the configuration's remedy nor a findings claim" \
  || ko "(k3) the console of a no-verdict NO-GO says [$bad_k3c]: $CON_K3"
! LC_ALL=C grep -qF 'Findings in' <<<"$CON_K3" \
  && ok "(k3) scan-only does NOT say 'Findings in' on a run with no verdict" \
  || ko "(k3) scan-only says 'Findings in' on a run with no verdict"
LC_ALL=C grep -qF -- "**NO-GO — $J_MOTIF_RUN.**" "$DIG_K3" 2>/dev/null \
  && ok "(k3) the digest carries the run motif" \
  || ko "(k3) the digest does not name the run motif: $(cat "$DIG_K3" 2>/dev/null)"
LC_ALL=C grep -qF -- "$K_RCSET" "$DIG_K3" 2>/dev/null \
  && ok "(k3) the digest names every module rc that obtains no verdict" \
  || ko "(k3) the digest does not say [$K_RCSET]"
LC_ALL=C grep -qF 'Active findings at gate: **?**' "$DIG_K3" 2>/dev/null \
  && ! LC_ALL=C grep -qF 'STALE-ADVISORY' "$DIG_K3" 2>/dev/null \
  && ok "(k3) the digest reads **?** and lists no finding — the stale pivot was NOT read" \
  || ko "(k3) the digest read the stale pivot: $(cat "$DIG_K3" 2>/dev/null)"
bad_k3d="$(forbidden_in 2>/dev/null < "$DIG_K3")"
[ -s "$DIG_K3" ] && [ -z "$bad_k3d" ] \
  && ok "(k3) the digest carries neither the configuration's remedy nor a findings claim" \
  || ko "(k3) the digest of a no-verdict NO-GO says [$bad_k3d] (or is missing)"

# ---- (m) A REPORTS DIRECTORY THE WATCH CANNOT WRITE: ITS OWN MOTIF, AT ONCE ------
echo
echo "=== (m) reports directory not writable (chmod 555) => its own motif, never 'Findings', never the run motif"
# MEASURED before the test it pins (scan-only, the real scanner's line): with no
# earlier log the watch said "Findings in ..."; with one, the run motif and its
# remedy "relancer le scan", which cannot work. MUTANT, replayed through
# SCA_WATCH_UNDER_TEST (a copy beside the real siblings): the `-w` block removed
# -> (m) RED, 2 KO. INERT under uid 0 (`-w` always true there): a named skip.
J_MOTIF_NOWRITE='verdict SCA non obtenu (dossier de rapports non inscriptible — le rendre inscriptible, puis relancer)'
R_M="$(make_root nowrite)"
chmod 555 "$(report_dir "$R_M")"
if [ -w "$(report_dir "$R_M")" ]; then
  skip "(m): the reports directory stays writable after chmod 555 (uid 0?) — INERT here" 3
else
  OUT_M="$(cd "$R_M" && PATH="$CLEANBIN:$PATH" bash "$WATCH" 2>&1)"; rc_m=$?
  CON_M="$(watch_lines "$OUT_M")"
  [ "$rc_m" -eq 1 ] \
    && ok "(m) exit 1 — a verdict not obtained is never a pass" \
    || ko "(m) expected exit 1, got $rc_m: $OUT_M"
  LC_ALL=C grep -qF -- "sca-watch: NO-GO — $J_MOTIF_NOWRITE: " <<<"$CON_M" \
    && ok "(m) the console names the not-writable motif and its remedy" \
    || ko "(m) the console does not name the not-writable motif: $CON_M"
  ! LC_ALL=C grep -qF 'Findings in' <<<"$CON_M" && ! LC_ALL=C grep -qF -- "$J_MOTIF_RUN" <<<"$CON_M" \
    && ok "(m) neither 'Findings in' nor the run motif (its remedy, re-run the scan, cannot work here)" \
    || ko "(m) the console says 'Findings in' or the run motif: $CON_M"
fi
chmod 755 "$(report_dir "$R_M")" 2>/dev/null

# ---- THE COUNT ARM: did every cell actually RUN? -----------------------------
echo
echo "=== count: an EXACT arm count, so a cell that stops running goes RED"
# `passed + failed + skipped_arms + 1` — arms that RAN, whatever their verdict,
# plus this arm. Compared to an EXACT constant, never a floor. This is the arm
# that reddens when (g) or (h) is deleted, or when a cell dies before reaching
# its assertions; the `failed` counter already covers arms that ran and lost, and
# a NAMED skip is accounted for rather than quietly shrinking the tally.
ARMS_RUN=$((passed + failed + skipped_arms + 1))
[ "$ARMS_RUN" -eq "$EXPECT_ARMS" ] \
  && ok "count: $ARMS_RUN arms ran, EXPECT_ARMS=$EXPECT_ARMS ($passed ok / $failed KO / $skipped_arms suppressed by a NAMED skip)" \
  || ko "count: $ARMS_RUN arms ran but EXPECT_ARMS=$EXPECT_ARMS — a cell did not run (removed, or it died before its assertions), or an arm was added without updating the constant ($passed ok / $failed KO / $skipped_arms skipped)"

echo
echo "================================================================"
echo "sca-watch: $passed passed / $failed failed / $skipped_arms arms skipped (named)"
[ "$failed" -eq 0 ] || exit 1
echo "Watch: the digest is DATED and REWRITTEN at each run (a stale one is worse"
echo "than none), the audit log APPENDS one mode=watch line per run, and an"
echo "orchestrate mode with no binary falls back loudly instead of failing quiet."
