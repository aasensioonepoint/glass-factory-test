#!/usr/bin/env bash
# Suite for the Python ecosystem of sca-scan.sh (T-00000292) — NON-VACUITY, BOTH FACES.
#
# Auto-discovered by core-scripts/run-bash-tests.sh. Every case runs the REAL
# dispatcher against a disposable fixture root. ZERO network: the vulnerability
# is emitted by a STUB `pip-audit` on the PATH, never by the real tool.
#
# The two faces are the whole point (L-00000186 / L-00000232): a harness that
# only ever proves "nothing found" has the exact shape of a broken campaign.
#   (a) a POSITIVE control that MUST go RED — pinned vulnerable requirements +
#       a stub pip-audit emitting a boxed HIGH => exit 1, NO-GO.
#   (b) an INCAPACITY control — no pip-audit on PATH => degraded, NAMED on the
#       python line AND announced as COVERAGE DEGRADED, never a block.
# (b) is what distinguishes "found nothing" from "was unable to look".
#
# T-00000489 adds the four DISPLAY arms. A scanned repo belongs to a CLIENT, so
# a file NAME in it is untrusted input, and `.degraded` is read back joined by
# `paste -sd '; '` into the banner and the Gaps <li> of the delivered HTML:
#   (c)  `$py_other` — pyproject.toml alone must be named VERBATIM, zero `?`.
#        It is NOT sanitized, and that is deliberate: it is built from OUR five
#        fixed literals, so there is no client byte in it to neutralise.
#   (d)  HOSTILE — an unpinned requirements*.txt whose NAME carries CR, ESC,
#        `;`, `:`, `(`, `)` and `,` must land neutralised, once.
#   (d2) LEGITIMATE — an ordinary unpinned name must pass through UNCHANGED,
#        or the sanitizer is merely breaking real reports.
#   (d3) JOIN — TWO unpinned files must still render as a `, `-separated pair.
#
# MUTATIONS THAT MUST TURN THIS SUITE RED (L-00000343 — an arm carries the
# mutation that reddens it, or nobody can tell whether it still measures):
#   1. drop `sanitize_display` from the `$unpinned` accumulation in sca-scan.sh
#      -> (d) RED on the exact line AND on the control-byte count. (d2) stays
#         green, which is the point: the fix is neutralisation, not mangling.
#   2. swap the whitelist for a blacklist (`tr -d '\000-\037\177'`)
#      -> (d) RED: the forged `; go: scanned, 0 CVE (` survives untouched, while
#         the ESC face alone would have looked repaired.
#   3. move the call AFTER the join (`unpinned="$(sanitize_display "$unpinned")"`)
#      -> (d3) RED: the `, ` separator itself becomes `? `, so the DYNAMIC span
#         holds 0 commas instead of 1 — while (d) and (d2) stay GREEN. This is
#         the only arm that catches the mistake copying the dotnet site invites.
#   4. sanitize `$py_other` through an amputated charset (`tr -c 'A-Za-z0-9 -'`)
#      -> (c) RED: `pyproject?toml`. A belt with nothing to hold still breaks.
#   5. edit the literal `résolution refusée, posture lock-only (`
#      -> (d), (d2) and (d3) RED (all three pin the whole line with `grep -Fx`).
#
# The table above was REPLAYED, not asserted (2026-09-06, bash 3.2.57, each
# mutation applied to a COPY of sca-scan.sh in a scratch tree — never to the
# tracked file). Observed: control 31/31 green; 1 -> (d) alone; 2 -> (d) alone,
# and its control-byte assertion stays GREEN, which is precisely why the forged
# `; go: scanned` matters more than the ESC; 3 -> (d3) alone; 4 -> (c) alone;
# 5 -> (d), (d2), (d3). Copy the WHOLE directory when replaying: sca-scan.sh
# resolves waiver_filter.py from its own SCRIPT_DIR, and a copy without the
# sibling .py files loses the gate and reddens case (a) for the wrong reason.
#
# FORM (bash 3.2 floor, T-00000477): heredocs at STATEMENT level only, never
# inside a `"$( … )"` which bash < 4.4 mis-parses; `grep -F`/`-Fx` wherever a
# literal is pinned; `rc` captured on the line that follows the command.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
# REFUSE rather than continue on an empty/degenerate workspace root. A silently
# empty $TMP (mktemp failure under `set -u` catches unset, NOT empty) would make
# every `mkdir -p "$TMP/x"` write at `/x` and every `cd` land in the real tree —
# the exact `git -C ""` = current-directory class that has scarred repos with a
# phantom commit. A disposable-repo variable must be non-empty, a real directory,
# under the system temp, and NEVER the current tree, or the harness stops here.
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for ROOT.
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  printf 'flask==2.0.0\n' > "$r/requirements.txt"   # pinned + (stub-)vulnerable
  echo "$r"
}

report_dir() { echo "$1/.agents/state/local/sca-reports"; }

# make_root ALWAYS writes a requirements.txt, so it can never reach the branch
# where `py_reqs` is empty. (c) needs a root with no requirements*.txt at all.
make_root_bare() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  echo "$r"
}

# The unpinned reason line, and its DYNAMIC span — everything after the fixed
# prefix `… lock-only (`.
#
# WHY THE SPAN AND NOT THE LINE (reserve C1 of the plan-critic, S-00001188): the
# fixed prefix ALREADY contains a comma, in "résolution refusée, posture". So on
# CORRECT code a whole-line count gives 1 for a single file and 2 for a pair —
# and under the "sanitize after the join" mutation the pair falls back to 1,
# i.e. exactly the value a naive `-eq 1` assertion would call a PASS. Counting
# the line would have been green on the very defect the arm exists to catch.
# Inside the span the reading is unambiguous: (d)=0, (d2)=0, (d3)=1.
py_unpinned_line() { grep -F 'python: requirements non épinglé' "$1"; }
py_span() { py_unpinned_line "$1" | sed 's/^.*lock-only (//'; }

# Count occurrences of the characters in $2 inside the string $1. `tr -cd` keeps
# only that set; `wc -c` then counts bytes, and macOS pads its output with
# spaces, hence the strip.
count_char() { printf '%s' "$1" | LC_ALL=C tr -cd "$2" | wc -c | tr -d '[:space:]'; }

# ---- (a) POSITIVE CONTROL: pinned + vulnerable + stub pip-audit => NO-GO ------
echo "=== (a) pinned vulnerable requirements + stub pip-audit => exit 1, NO-GO"
STUBBIN="$TMP/stubbin"; mkdir -p "$STUBBIN"
cat > "$STUBBIN/pip-audit" <<'STUB'
#!/usr/bin/env bash
# Fake pip-audit: emit a boxed HIGH finding, exit 1 like the real tool does when
# it FINDS vulnerabilities. Zero network, zero resolution, zero build.
cat <<'JSON'
{"dependencies":[{"name":"flask","version":"2.0.0","vulns":[{"id":"PYSEC-2023-62","fix_versions":["2.2.5"],"aliases":["CVE-2023-30861"],"severity":"HIGH","description":"boxed"}]}],"fixes":[]}
JSON
exit 1
STUB
chmod +x "$STUBBIN/pip-audit"

RA="$(make_root vuln)"
OUT_A="$(cd "$RA" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_a=$?
[ "$rc_a" -eq 1 ] \
  && ok "the dispatcher exits 1 (NO-GO) on a boxed HIGH" \
  || ko "expected exit 1, got $rc_a"
grep -q "NO-GO" <<<"$OUT_A" \
  && ok "the effective gate is announced NO-GO" || ko "no NO-GO in the output"
# Non-vacuity witness: the stub REALLY ran and its report reached the filter —
# a green here without this would measure some other gate, not python.
PA="$(report_dir "$RA")/pip-audit.json"
[ -s "$PA" ] && grep -q '"flask"' "$PA" \
  && ok "the stub's pip-audit.json is present and names flask (the stub ran)" \
  || ko "pip-audit.json missing or empty — the python path was not exercised"

# ---- (b) INCAPACITY CONTROL: no pip-audit on PATH => degraded, NAMED ----------
echo
echo "=== (b) pip-audit ABSENT => .degraded carries the python line, COVERAGE DEGRADED"
# The measured dev box + this kit's CI carry no pip-audit; when a machine does,
# build a curated PATH that omits it so the absence is REAL, and ASSERT it before
# trusting the result — an unsimulated absence would measure nothing.
if command -v pip-audit >/dev/null 2>&1; then
  # A machine that HAS pip-audit must simulate its absence. Do NOT copy the tools
  # into an isolated bin: on Git Bash / MSYS `ln` COPIES the binaries, which then
  # fail to load their shared libraries (exit 127) so the scan never runs and this
  # case would measure nothing. Instead, drop pip-audit's OWN directory from PATH —
  # every other tool keeps its real location (and its DLLs) intact. The absence is
  # ASSERTED just below (line: "could not simulate pip-audit absence"), so a strip
  # that misses (e.g. path-casing) fails LOUD rather than measuring the wrong gate.
  pa_dir="$(cd "$(dirname "$(command -v pip-audit)")" 2>/dev/null && pwd)"
  BPATH=""; _oldifs="$IFS"; IFS=':'
  for d in $PATH; do
    [ -n "$d" ] || continue
    case "$(cd "$d" 2>/dev/null && pwd)" in
      "$pa_dir") continue ;;
    esac
    BPATH="${BPATH:+$BPATH:}$d"
  done
  IFS="$_oldifs"
else
  BPATH="$PATH"
fi

RB="$(make_root nooutil)"
OUT_B="$(cd "$RB" && PATH="$BPATH" bash "$SCAN" 2>&1)"; rc_b=$?
if PATH="$BPATH" command -v pip-audit >/dev/null 2>&1; then
  ko "could not simulate pip-audit absence — this case would measure nothing"
else
  DEG="$(report_dir "$RB")/.degraded"
  [ -f "$DEG" ] && grep -qi "python" "$DEG" && grep -q "pip-audit not installed" "$DEG" \
    && ok ".degraded carries the python line naming the missing tool" \
    || ko ".degraded does not name the python incapacity"
  grep -q "COVERAGE DEGRADED" <<<"$OUT_B" \
    && ok "the run announces COVERAGE DEGRADED" || ko "no COVERAGE DEGRADED announced"
  [ "$rc_b" -ne 1 ] \
    && ok "an incapacity is NEVER a block (exit $rc_b, not 1)" \
    || ko "pip-audit absence hard-blocked the gate (exit 1)"
fi

# ---- (c) $py_other: an unsupported manifest is named VERBATIM ----------------
echo
echo "=== (c) pyproject.toml alone => named in .degraded, verbatim, zero '?'"
# This branch (`py_reqs` empty, `py_other` non-empty) sits BEHIND `if ! have
# pip-audit`, so it is only reachable with the stub on the PATH — without it the
# run would degrade on "pip-audit not installed" and measure case (b) again.
R_C="$(make_root_bare pyproj)"
printf '[project]\nname = "x"\n' > "$R_C/pyproject.toml"
OUT_C="$(cd "$R_C" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_c=$?
DEG_C="$(report_dir "$R_C")/.degraded"
# POSITIVE witness FIRST (L-00000343): an arm that asserts an ABSENCE goes green
# on an early crash. Prove the file exists and that python spoke at all.
if [ -f "$DEG_C" ] && grep -qF 'python:' "$DEG_C"; then
  ok "(c) witness: .degraded exists and carries a python: line"
  PY_C="$(grep -F 'python:' "$DEG_C")"
  # C3: pin the RENDERING of $py_other, not the sentence around it. The wording
  # belongs to the block and a later plan may legitimately move it; what must
  # not drift is that our own literal reaches the client report untouched.
  grep -qF '(pyproject.toml)' <<<"$PY_C" \
    && ok "(c) the unsupported manifest is named VERBATIM: (pyproject.toml)" \
    || ko "(c) expected '(pyproject.toml)', got: $PY_C"
  [ "$(count_char "$PY_C" '?')" -eq 0 ] \
    && ok "(c) zero '?' on the line — \$py_other is OUR literals, not client bytes" \
    || ko "(c) the python line was mangled: $PY_C"
else
  ko "(c) premise: no .degraded or no python line — the branch was not reached"
fi
grep -q "COVERAGE DEGRADED" <<<"$OUT_C" \
  && ok "(c) the run announces COVERAGE DEGRADED" || ko "(c) no COVERAGE DEGRADED announced"
[ "$rc_c" -ne 1 ] \
  && ok "(c) an unsupported manifest is NEVER a block (exit $rc_c, not 1)" \
  || ko "(c) an unsupported manifest hard-blocked the gate (exit 1)"

# ---- (d) HOSTILE: a client file NAME carrying CR/ESC/;/:/(/)/, is neutralised -
echo
echo "=== (d) hostile unpinned requirements NAME => neutralised once, in .degraded"
R_D="$(make_root hostile)"
# Two measured attacks in one name. CR + ESC[1A rewrites the line ABOVE in the
# pilot's terminal; and since announce_degraded joins the reasons with `; `, a
# `;` in a NAME forges a second ecosystem verdict — here a reassuring
# `go: scanned, 0 CVE` that never ran — inside the report handed to the client.
HOSTILE="$(printf 'requirements-A\rW\033[1AX); go: scanned, 0 CVE (z.txt')"
printf 'flask\n' > "$R_D/$HOSTILE" 2>/dev/null || true
if [ ! -f "$R_D/$HOSTILE" ]; then
  # Never a silent green: some filesystems (NTFS refuses ':') cannot hold it.
  ko "(d) premise: hostile fixture not creatable on this filesystem"
else
  ok "(d) premise: the hostile fixture exists on disk"
  OUT_D="$(cd "$R_D" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_d=$?
  DEG_D="$(report_dir "$R_D")/.degraded"
  PA_D="$(report_dir "$R_D")/pip-audit.json"
  # Positive witnesses before any absence assertion.
  [ "$rc_d" -eq 1 ] \
    && ok "(d) witness: the run reached its verdict (exit 1 on the boxed HIGH)" \
    || ko "(d) witness: expected exit 1, got $rc_d"
  [ -s "$PA_D" ] && grep -qF '"flask"' "$PA_D" \
    && ok "(d) witness: pip-audit.json names flask — the python path really ran" \
    || ko "(d) witness: pip-audit.json missing/empty — some other path was measured"
  [ -f "$DEG_D" ] && grep -qF 'python: requirements non épinglé' "$DEG_D" \
    && ok "(d) witness: .degraded carries the unpinned python line" \
    || ko "(d) witness: no unpinned python line in .degraded"
  EXPECT_D='python: requirements non épinglé — résolution refusée, posture lock-only (requirements-A?W??1AX?? go? scanned? 0 CVE ?z.txt)'
  grep -Fxq "$EXPECT_D" "$DEG_D" \
    && ok "(d) the reason line is EXACTLY the neutralised form" \
    || ko "(d) expected [$EXPECT_D] got [$(py_unpinned_line "$DEG_D")]"
  SPAN_D="$(py_span "$DEG_D")"
  [ "$(count_char "$SPAN_D" ',')" -eq 0 ] \
    && ok "(d) zero ',' in the dynamic span — no forged list item" \
    || ko "(d) a ',' survived in the span: $SPAN_D"
  [ "$(count_char "$SPAN_D" ';')" -eq 0 ] \
    && ok "(d) zero ';' in the dynamic span — no forged reason entry" \
    || ko "(d) a ';' survived in the span: $SPAN_D"
  n="$(grep -cF 'go: scanned' "$DEG_D" || true)"
  [ "$n" -eq 0 ] \
    && ok "(d) the forged 'go: scanned' verdict never reaches .degraded" \
    || ko "(d) forged go verdict present $n time(s) in .degraded"
  n="$(printf '%s' "$OUT_D" | grep -cF 'go: scanned' || true)"
  [ "$n" -eq 0 ] \
    && ok "(d) the forged 'go: scanned' verdict never reaches stdout either" \
    || ko "(d) forged go verdict present $n time(s) on stdout"
  # The CLASS, not one octet (3rd-pass lesson of T-00000488): pinning \033 alone
  # would have let CR through, and CR is what rewrites the pilot's line.
  n="$(LC_ALL=C grep -c '[[:cntrl:]]' "$DEG_D" || true)"
  [ "$n" -eq 0 ] \
    && ok "(d) zero control byte anywhere in .degraded (the class, not one octet)" \
    || ko "(d) $n line(s) of .degraded still carry a control byte"
fi

# ---- (d2) LEGITIMATE: an ordinary name must pass through UNCHANGED ------------
echo
echo "=== (d2) legitimate unpinned name => rendered verbatim, zero '?'"
# Without this face, mutation 1 (drop the call) and a sanitizer that mangles
# EVERYTHING would be indistinguishable — and a report that garbles real file
# names is a report nobody acts on.
R_D2="$(make_root legit)"
printf 'flask\n' > "$R_D2/requirements-dev_v2.1.txt"
OUT_D2="$(cd "$R_D2" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_d2=$?
DEG_D2="$(report_dir "$R_D2")/.degraded"
[ "$rc_d2" -eq 1 ] \
  && ok "(d2) witness: the run reached its verdict (exit 1 on the boxed HIGH)" \
  || ko "(d2) witness: expected exit 1, got $rc_d2"
[ -f "$DEG_D2" ] && grep -qF 'python: requirements non épinglé' "$DEG_D2" \
  && ok "(d2) witness: .degraded carries the unpinned python line" \
  || ko "(d2) witness: no unpinned python line in .degraded"
EXPECT_D2='python: requirements non épinglé — résolution refusée, posture lock-only (requirements-dev_v2.1.txt)'
grep -Fxq "$EXPECT_D2" "$DEG_D2" \
  && ok "(d2) a legitimate name survives INTACT (dots, dashes, underscore)" \
  || ko "(d2) expected [$EXPECT_D2] got [$(py_unpinned_line "$DEG_D2")]"
SPAN_D2="$(py_span "$DEG_D2")"
[ "$(count_char "$SPAN_D2" '?')" -eq 0 ] \
  && ok "(d2) zero '?' — the sanitizer neutralises, it does not mangle" \
  || ko "(d2) a legitimate name was mangled: $SPAN_D2"
[ "$(count_char "$SPAN_D2" ',')" -eq 0 ] \
  && ok "(d2) a single file yields a span with no separator" \
  || ko "(d2) unexpected ',' in a one-file span: $SPAN_D2"

# ---- (d3) JOIN: the separator is GRAMMAR and must survive ---------------------
echo
echo "=== (d3) two unpinned files => still a ', '-separated pair"
# THE arm of this lot. `$unpinned` is a LIST, and `,` is outside the whitelist,
# so sanitizing the JOINED string destroys the separator that the reader parses:
#   printf 'requirements-a.txt, requirements-b.txt' | LC_ALL=C tr -c 'A-Za-z0-9._/ -' '?'
#   -> requirements-a.txt? requirements-b.txt
# Measured on this box before the fix was written. Hence: sanitize PER ELEMENT,
# before accumulation. The count below is taken in the dynamic span only (C1).
R_D3="$(make_root join)"
printf 'flask\n' > "$R_D3/requirements-a.txt"
printf 'flask\n' > "$R_D3/requirements-b.txt"
OUT_D3="$(cd "$R_D3" && PATH="$STUBBIN:$PATH" bash "$SCAN" 2>&1)"; rc_d3=$?
DEG_D3="$(report_dir "$R_D3")/.degraded"
[ "$rc_d3" -eq 1 ] \
  && ok "(d3) witness: the run reached its verdict (exit 1 on the boxed HIGH)" \
  || ko "(d3) witness: expected exit 1, got $rc_d3"
[ -f "$DEG_D3" ] && grep -qF 'python: requirements non épinglé' "$DEG_D3" \
  && ok "(d3) witness: .degraded carries the unpinned python line" \
  || ko "(d3) witness: no unpinned python line in .degraded"
EXPECT_D3='python: requirements non épinglé — résolution refusée, posture lock-only (requirements-a.txt, requirements-b.txt)'
grep -Fxq "$EXPECT_D3" "$DEG_D3" \
  && ok "(d3) the pair renders with its ', ' separator INTACT" \
  || ko "(d3) expected [$EXPECT_D3] got [$(py_unpinned_line "$DEG_D3")]"
SPAN_D3="$(py_span "$DEG_D3")"
[ "$(count_char "$SPAN_D3" ',')" -eq 1 ] \
  && ok "(d3) exactly ONE ',' in the dynamic span (0 would mean a killed separator)" \
  || ko "(d3) span holds $(count_char "$SPAN_D3" ',') ',' instead of 1: $SPAN_D3"
[ "$(count_char "$SPAN_D3" '?')" -eq 0 ] \
  && ok "(d3) zero '?' — per-element sanitizing left both names untouched" \
  || ko "(d3) the join was sanitized as a whole: $SPAN_D3"

# ==============================================================================
# T-00000462 — LOCKFILES. Case #143: a project with poetry.lock / uv.lock /
# Pipfile.lock and NO requirements*.txt was never audited, while the run still
# published a python status. The arms below are lettered L* because (a)..(d3)
# are taken.
#
# THE STATUS IS NOT OBSERVABLE, AND THESE ARMS USE A PROXY — SAID ONCE, HERE
# (reserve C46). `PYTHON_STATUS` reaches exactly one emitter, `emit_sca`, and
# that call is MUZZLED at the byte (`>/dev/null 2>&1 || true`); worse, on a
# fixture root OUTSIDE this repo it invokes a `.claude/hooks/emit-event.sh` that
# does not exist there. The audit line carries ts/mode/entry/module/verdict/
# gate_level and the summary counters — never the per-ecosystem status. So NO
# fixture can read `PYTHON_STATUS`.
# What these arms assert instead is its PROXY: the presence or absence of a line
# matching `^python:` in `.degraded`, plus the `COVERAGE DEGRADED` banner. The
# proxy is an EQUIVALENCE, re-counted on disk for this lot: every site that sets
# `PYTHON_STATUS="degraded"` is immediately preceded by a `python:` write, and
# those are the ONLY writers of a `python:` line. It is a proxy all the same, and
# it is named as one rather than dressed up as a status assertion.
#
# MUTATIONS THAT MUST TURN THESE ARMS RED:
#   6. drop `|| [ "${#py_locks[@]}" -gt 0 ]` from the entry predicate
#      -> (L1) RED: a lock-only root never enters the block at all.
#   7. move the lock sequence out of the `else` branch (same level, after `fi`)
#      -> (L1)/(L7) RED: `pin_args=()` erases the pins, pip-audit never runs.
#   8. aggregate the two exclusion counters into one
#      -> (L2) RED on the nominal `locks:` line, (L2b) RED on its degraded line.
#   9. count the git dependency as a ROOT exclusion
#      -> (L2b) RED alone, while (L2) stays green. Both senses, or neither.
#  10. restore `[ "$rc" -eq 2 ]` in place of `[ "$rc" -ne 0 ]`
#      -> (L8) RED: an rc of 1 slips through as a success.
#  11. remove BOTH the `rm -f` of sca-scan.sh AND `_discard` of py_lock_pins.py
#      -> (L6) RED. Removing only one leaves the other cleaning up — measured.
#  12. loop py_lock_pins.py once per lock instead of one variadic call
#      -> (L7) RED: `--out` truncates and only the last lock survives.
# ==============================================================================
echo
echo "=== T-00000462: LOCKFILES (case #143) ==================================="

# CAPABILITY GUARD, DERIVED FROM THE FORMAT EACH FIXTURE MAKES THE PROGRAM READ,
# never from what an arm is "about" (L-00000392). `tomllib` is stdlib from Python
# 3.11 only, so a TOML fixture needs it and a JSON one does not.
# The three candidates and their ORDER are those of sca-scan.sh's own probe, so
# this suite resolves the SAME interpreter the dispatcher will.
PY_T=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY_T="$c"; break; }; done
HAVE_TOML=0; [ -n "$PY_T" ] && "$PY_T" -c 'import tomllib' >/dev/null 2>&1 && HAVE_TOML=1
if [ "$HAVE_TOML" -eq 0 ]; then
  echo "  SKIP (L1)(L2)(L2b)(L6)(L7): tomllib absent (Python < 3.11) — lecture des locks TOML NON mesurée"
fi
# (L3) and (L5) are deliberately OUTSIDE this guard, and for two different
# reasons. (L3) reads JSON, which needs nothing optional — so lock coverage never
# drops to zero whatever the interpreter. (L5) feeds a CORRUPTED TOML lock and
# pins rc=2: py_lock_pins.py maps a missing `tomllib` onto the SAME LockError as
# an invalid lock, so the exit code it demands holds with or without the library.
# An arm that pinned a code only reachable WITH tomllib would have been the exact
# defect reserve C43 named.

# A journaling pip-audit stub — SEPARATE from $STUBBIN so the arms above keep the
# stub they were written against. The journal path is EXPORTED before the heredoc
# (reserve C28): the stub runs in a child shell with a cd'd cwd, so a relative
# path would land somewhere nobody reads and the arm would assert on an empty
# file — vacuously green.
LOCKBIN="$TMP/lockbin"; mkdir -p "$LOCKBIN"
PIPLOG="$TMP/pip-argv.log"
export PIPLOG
cat > "$LOCKBIN/pip-audit" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PIPLOG"
cat <<'JSON'
{"dependencies":[{"name":"jinja2","version":"2.11.0","vulns":[{"id":"PYSEC-2020-95","fix_versions":["2.11.3"],"aliases":["CVE-2020-28493"],"severity":"HIGH","description":"boxed"}]}],"fixes":[]}
JSON
exit 1
STUB
chmod +x "$LOCKBIN/pip-audit"

# Fixture writers. Heredocs at STATEMENT level only (bash 3.2 floor, T-00000477).
write_uv_root_and_jinja() {
  cat > "$1/uv.lock" <<'LOCK'
version = 1

[[package]]
name = "monapp"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "jinja2"
version = "2.11.0"
source = { registry = "https://pypi.org/simple" }
LOCK
}

write_poetry_jinja() {
  cat > "$1/poetry.lock" <<'LOCK'
[[package]]
name = "jinja2"
version = "2.11.0"
description = "templating"
optional = false

[metadata]
lock-version = "2.0"
LOCK
}

write_pipfile_lock() {
  cat > "$1/Pipfile.lock" <<'LOCK'
{"_meta": {"hash": {"sha256": "0"}},
 "default": {"jinja2": {"version": "==2.11.0"}},
 "develop": {"werkzeug": {"version": "==0.16.0"}}}
LOCK
}

deg_python_count() { LC_ALL=C grep -c '^python:' "$1" 2>/dev/null || true; }

# ---- (a)+ EXTENSION of the EXISTING requirements-only arm (a) -----------------
# The gain is a NOMINAL-path proof: on a root with NO lock at all, the new code
# must not fire — no pins file, and not one degraded python line of its own.
# VARIABLES ARE LOCAL TO THIS ARM ON PURPOSE. `$DEG` is defined only inside the
# `else` branch of (b)'s absence guard, and (b) runs AFTER (a): under
# `set -uo pipefail` reaching for `$DEG` here would ABORT the whole suite.
echo
echo "=== (a)+ requirements-only root: the lock sequence must NOT fire"
DEG_A="$(report_dir "$RA")/.degraded"
PINS_A="$(report_dir "$RA")/pins-from-locks.txt"
# Paired with the positives ALREADY established for (a) in this same run — exit 1
# and a pip-audit.json naming flask — so these absences are not vacuous.
[ ! -f "$PINS_A" ] \
  && ok "(a)+ no pins file on a root without a lock" \
  || ko "(a)+ pins-from-locks.txt was produced without any lock"
if [ ! -f "$DEG_A" ] || [ "$(deg_python_count "$DEG_A")" -eq 0 ]; then
  ok "(a)+ no python: degradation line — the proxy says the status stayed scanned"
else
  ko "(a)+ unexpected python: line(s): $(LC_ALL=C grep '^python:' "$DEG_A")"
fi

# ---- (L1) poetry.lock, LOCK-ONLY: case #143 itself ----------------------------
echo
echo "=== (L1) poetry.lock alone (NO requirements*.txt) => audited, NO-GO"
if [ "$HAVE_TOML" -eq 1 ]; then
  R_L1="$(make_root_bare l1poetry)"
  write_poetry_jinja "$R_L1"
  : > "$PIPLOG"
  OUT_L1="$(cd "$R_L1" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l1=$?
  PINS_L1="$(report_dir "$R_L1")/pins-from-locks.txt"
  DEG_L1="$(report_dir "$R_L1")/.degraded"
  # POSITIVE witnesses first: the block was really entered and really audited.
  [ -s "$PINS_L1" ] && LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L1" \
    && ok "(L1) the lock was translated into a pin: jinja2==2.11.0" \
    || ko "(L1) no pins file, or it does not carry jinja2==2.11.0"
  LC_ALL=C grep -qF -- '-r' "$PIPLOG" && LC_ALL=C grep -qF 'pins-from-locks.txt' "$PIPLOG" \
    && ok "(L1) pip-audit really received the pins file (argv journalled)" \
    || ko "(L1) pip-audit was never handed the pins: [$(cat "$PIPLOG")]"
  [ "$rc_l1" -eq 1 ] \
    && ok "(L1) a CVE inside a lock-only project goes NO-GO (exit 1)" \
    || ko "(L1) expected exit 1, got $rc_l1"
  # MUTATION 6: drop the `|| [ "${#py_locks[@]}" -gt 0 ]` term -> the block is
  # never entered, no pins file, no audit, and the three lines above go red.
  ! LC_ALL=C grep -qF 'flask' "$PINS_L1" \
    && ok "(L1) the pins file holds ONLY what the lock declares" \
    || ko "(L1) flask leaked into a fixture that never mentioned it"
  # The root is not degraded: nothing was excluded, so nothing to report.
  if [ ! -f "$DEG_L1" ] || [ "$(deg_python_count "$DEG_L1")" -eq 0 ]; then
    ok "(L1) proxy: no python: line — a fully read lock is a scanned perimeter"
  else
    ko "(L1) unexpected python: line(s): $(LC_ALL=C grep '^python:' "$DEG_L1")"
  fi
fi

# ---- (L2) uv.lock with an editable ROOT: the exclusion is ASSERTED ------------
echo
echo "=== (L2) uv.lock root editable => root EXCLUDED, run still scanned"
if [ "$HAVE_TOML" -eq 1 ]; then
  R_L2="$(make_root_bare l2uv)"
  write_uv_root_and_jinja "$R_L2"
  : > "$PIPLOG"
  OUT_L2="$(cd "$R_L2" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l2=$?
  PINS_L2="$(report_dir "$R_L2")/pins-from-locks.txt"
  DEG_L2="$(report_dir "$R_L2")/.degraded"
  # (1) POSITIVE of the SAME run. Without it, a program that excluded EVERYTHING
  # would sail through the absence and the count below (L-00000388).
  [ -s "$PINS_L2" ] && LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L2" \
    && ok "(L2) witness: the registry package was retained" \
    || ko "(L2) witness: jinja2==2.11.0 missing from the pins file"
  # (2) ABSENCE — the scanned project itself must never reach pip-audit.
  ! LC_ALL=C grep -q 'monapp' "$PINS_L2" \
    && ok "(L2) the editable ROOT is absent from the pins" \
    || ko "(L2) the root project leaked into the pins file"
  # (3) EXACT COUNT. `grep -c .` counts NON-EMPTY lines, so it reads the same
  # whether or not the file ends with a newline — the contract says it does
  # (test_out_file_always_ends_with_newline), and this count does not depend on
  # that being true. That is reserve C42 closed on BOTH halves.
  [ "$(LC_ALL=C grep -c . "$PINS_L2")" -eq 1 ] \
    && ok "(L2) exactly ONE pin — nothing else slipped in" \
    || ko "(L2) expected 1 pin, got $(LC_ALL=C grep -c . "$PINS_L2")"
  # (4) THE NOMINAL PATH (L-00000388): the exclusion is written on the run that
  # applies it, with its count, and it does NOT degrade — a root is not a
  # dependency. MUTATION 8: aggregate the counters -> this line changes shape.
  LC_ALL=C grep -qF '1 entrée(s) racine exclue(s)' <<<"$OUT_L2" \
    && ok "(L2) the nominal log names the structural exclusion and its count" \
    || ko "(L2) no structural exclusion on the nominal path: $OUT_L2"
  if [ ! -f "$DEG_L2" ] || [ "$(deg_python_count "$DEG_L2")" -eq 0 ]; then
    ok "(L2) proxy: no python: line — a structural exclusion NEVER degrades"
  else
    ko "(L2) the root exclusion wrongly degraded: $(LC_ALL=C grep '^python:' "$DEG_L2")"
  fi
fi

# ---- (L2b) root + a git dependency: the OTHER sense of the separation ---------
echo
echo "=== (L2b) uv.lock root + git dep => REAL hole, run degraded"
if [ "$HAVE_TOML" -eq 1 ]; then
  R_L2B="$(make_root_bare l2buv)"
  write_uv_root_and_jinja "$R_L2B"
  cat >> "$R_L2B/uv.lock" <<'LOCK'

[[package]]
name = "vendored"
version = "1.2.3"
source = { git = "https://example.invalid/vendored.git" }
LOCK
  : > "$PIPLOG"
  OUT_L2B="$(cd "$R_L2B" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l2b=$?
  PINS_L2B="$(report_dir "$R_L2B")/pins-from-locks.txt"
  DEG_L2B="$(report_dir "$R_L2B")/.degraded"
  [ -s "$PINS_L2B" ] && LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L2B" \
    && ok "(L2b) witness: the registry package was still retained" \
    || ko "(L2b) witness: jinja2==2.11.0 missing from the pins file"
  ! LC_ALL=C grep -q 'vendored' "$PINS_L2B" \
    && ok "(L2b) the git dependency is absent from the pins" \
    || ko "(L2b) the git dependency leaked into the pins file"
  # EXACTLY ONE degraded python line, NAMING the count and the motive.
  # MUTATION 9: count the git dep as a root -> this goes red while (L2) stays
  # green. MUTATION 8: aggregate -> (L2) goes red while this stays green.
  # Neither mutation can be green on both arms, which is what "both senses" means.
  [ "$(deg_python_count "$DEG_L2B")" -eq 1 ] \
    && ok "(L2b) proxy: EXACTLY one python: line — the run is degraded" \
    || ko "(L2b) expected 1 python: line, got $(deg_python_count "$DEG_L2B")"
  LC_ALL=C grep -qF '1 dépendance(s) à source non-registre EXCLUE(S)' "$DEG_L2B" \
    && ok "(L2b) the reason names the count AND the motive (non-registry source)" \
    || ko "(L2b) reason line missing or reworded: $(LC_ALL=C grep '^python:' "$DEG_L2B")"
  LC_ALL=C grep -qF 'COVERAGE DEGRADED' <<<"$OUT_L2B" \
    && ok "(L2b) the run announces COVERAGE DEGRADED" \
    || ko "(L2b) no COVERAGE DEGRADED announced"
fi

# ---- (L3) Pipfile.lock — JSON, so MEASURED on every interpreter ---------------
echo
echo "=== (L3) Pipfile.lock alone => default AND develop pinned (no tomllib needed)"
R_L3="$(make_root_bare l3pipfile)"
write_pipfile_lock "$R_L3"
: > "$PIPLOG"
OUT_L3="$(cd "$R_L3" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l3=$?
PINS_L3="$(report_dir "$R_L3")/pins-from-locks.txt"
[ -s "$PINS_L3" ] && LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L3" \
  && ok "(L3) the default section is pinned" \
  || ko "(L3) jinja2==2.11.0 missing from the pins file"
LC_ALL=C grep -qFx 'werkzeug==0.16.0' "$PINS_L3" \
  && ok "(L3) the develop section is pinned too (dev CVEs are installed CVEs)" \
  || ko "(L3) werkzeug==0.16.0 missing — develop was dropped"
[ "$rc_l3" -eq 1 ] \
  && ok "(L3) a CVE in a Pipfile.lock-only project goes NO-GO (exit 1)" \
  || ko "(L3) expected exit 1, got $rc_l3"

# ---- (c)+ EXTENSION of the EXISTING pyproject-only arm ------------------------
# The only assertion that DISCRIMINATES here is the COUNT: the split moved
# poetry/uv/Pipfile locks out of `$py_other`, and a bug that also wrote a lock
# line would show up as two. NOT adding an assertion on "not supported in v1":
# T-00000489 refused that deliberately (:201-203) and pinned the RENDERING of
# `$py_other` instead. That decision stands.
echo
echo "=== (c)+ pyproject.toml alone => EXACTLY one python: line"
[ "$(deg_python_count "$DEG_C")" -eq 1 ] \
  && ok "(c)+ exactly ONE python: line for an unsupported manifest" \
  || ko "(c)+ expected 1 python: line, got $(deg_python_count "$DEG_C")"

# ---- (L4) NON-MUTATION: the scanned tree is untouched -------------------------
echo
echo "=== (L4) reading a lock mutates NOTHING in the scanned tree"
R_L4="$(make_root_bare l4nomut)"
write_pipfile_lock "$R_L4"
TREE_BEFORE="$(cd "$R_L4" && find . -path '*/.agents' -prune -o -type f -print | LC_ALL=C sort)"
( cd "$R_L4" && PATH="$LOCKBIN:$PATH" bash "$SCAN" >/dev/null 2>&1 ) || true
TREE_AFTER="$(cd "$R_L4" && find . -path '*/.agents' -prune -o -type f -print | LC_ALL=C sort)"
# Non-vacuity: the listing must not be empty, or "identical" would mean nothing.
[ -n "$TREE_BEFORE" ] \
  && ok "(L4) witness: the fixture listing is non-empty before the run" \
  || ko "(L4) witness: empty listing — this comparison would prove nothing"
[ "$TREE_BEFORE" = "$TREE_AFTER" ] \
  && ok "(L4) the scanned tree is byte-identical before and after (no resolution)" \
  || ko "(L4) the run MUTATED the scanned tree"

# ---- (L5) UNREADABLE lock: resolution FAILED, not refused --------------------
# Outside the tomllib guard by design: a missing library and an invalid lock map
# onto the SAME rc=2, so this arm holds on any interpreter (reserve C43).
echo
echo "=== (L5) corrupted lock => resolution FAILED (rc=2), never a silent skip"
R_L5="$(make_root l5broken)"     # make_root also writes a PINNED requirements.txt
printf 'this is not [ valid toml\n' > "$R_L5/poetry.lock"
: > "$PIPLOG"
OUT_L5="$(cd "$R_L5" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l5=$?
DEG_L5="$(report_dir "$R_L5")/.degraded"
[ -f "$DEG_L5" ] && LC_ALL=C grep -qF 'résolution ÉCHOUÉE' "$DEG_L5" \
  && ok "(L5) the reason says FAILED, not refused — the two are not the same" \
  || ko "(L5) no 'résolution ÉCHOUÉE' line: $(cat "$DEG_L5" 2>/dev/null)"
LC_ALL=C grep -qF 'rc=2' "$DEG_L5" \
  && ok "(L5) the exit code is carried into the report" \
  || ko "(L5) rc=2 absent from the degradation line"
[ "$(deg_python_count "$DEG_L5")" -ge 1 ] \
  && ok "(L5) proxy: a python: line is present — the run is degraded" \
  || ko "(L5) no python: line — an unreadable lock degraded nothing"
# CLASS control (C41), the same one :268 gives the older zone: the new line
# interpolates our three literals and an integer, so it can hold no control byte.
[ "$(LC_ALL=C grep -c '[[:cntrl:]]' "$DEG_L5" || true)" -eq 0 ] \
  && ok "(L5) zero control byte in .degraded (the class, not one octet)" \
  || ko "(L5) a control byte reached .degraded"

# ---- (L6) STALE pins file: the two belts, mutated TOGETHER --------------------
echo
echo "=== (L6) a lock emptied between two runs leaves NO stale pins"
if [ "$HAVE_TOML" -eq 1 ]; then
  R_L6="$(make_root_bare l6stale)"
  write_poetry_jinja "$R_L6"
  : > "$PIPLOG"
  ( cd "$R_L6" && PATH="$LOCKBIN:$PATH" bash "$SCAN" >/dev/null 2>&1 ) || true
  PINS_L6="$(report_dir "$R_L6")/pins-from-locks.txt"
  [ -s "$PINS_L6" ] \
    && ok "(L6) witness: run 1 really produced a pins file" \
    || ko "(L6) witness: run 1 produced nothing — run 2 would prove nothing"
  # A VALID lock that retains nothing. Not a root entry: poetry locks have none,
  # which is why the plan's original fixture contradicted its own arbitration
  # (reserve C45). An empty package list is the honest shape here.
  cat > "$R_L6/poetry.lock" <<'LOCK'
[metadata]
lock-version = "2.0"
LOCK
  # The journal is emptied BEFORE run 2 (reserve C29), or run 1's argv would
  # answer for run 2 and the absence assertion below would be meaningless.
  : > "$PIPLOG"
  OUT_L6="$(cd "$R_L6" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l6=$?
  DEG_L6="$(report_dir "$R_L6")/.degraded"
  # MUTATION 11: remove BOTH the `rm -f` in sca-scan.sh AND `_discard` in
  # py_lock_pins.py. Removing only ONE leaves the other cleaning up — measured
  # on this lot, and the reason this arm names the pair rather than a single site.
  [ ! -f "$PINS_L6" ] \
    && ok "(L6) run 2 leaves NO stale pins file behind" \
    || ko "(L6) the previous run's pins survived: [$(cat "$PINS_L6")]"
  ! LC_ALL=C grep -qF 'pins-from-locks.txt' "$PIPLOG" \
    && ok "(L6) pip-audit was never handed a stale pins file" \
    || ko "(L6) run 2 audited a stale pins file: [$(cat "$PIPLOG")]"
  LC_ALL=C grep -qF 'locks sans dépendance de registre' "$DEG_L6" \
    && ok "(L6) the empty lock is NAMED, not silently treated as scanned" \
    || ko "(L6) no 'locks sans dépendance de registre' line: $(cat "$DEG_L6" 2>/dev/null)"
  [ "$(deg_python_count "$DEG_L6")" -ge 1 ] \
    && ok "(L6) proxy: a python: line is present — the run is degraded" \
    || ko "(L6) an empty lock produced no degradation"
fi

# ---- (L7) TWO locks in ONE call: `--out` truncates, so a loop would lose one --
echo
echo "=== (L7) poetry.lock + Pipfile.lock => one pin from EACH, single call"
if [ "$HAVE_TOML" -eq 1 ]; then
  R_L7="$(make_root_bare l7two)"
  write_poetry_jinja "$R_L7"
  cat > "$R_L7/Pipfile.lock" <<'LOCK'
{"_meta": {"hash": {"sha256": "0"}},
 "default": {"werkzeug": {"version": "==0.16.0"}}}
LOCK
  : > "$PIPLOG"
  OUT_L7="$(cd "$R_L7" && PATH="$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l7=$?
  PINS_L7="$(report_dir "$R_L7")/pins-from-locks.txt"
  DEG_L7="$(report_dir "$R_L7")/.degraded"
  # MUTATION 12: one call per lock -> `--out` truncates and only the last
  # survives; whichever of these two lines belongs to the first lock goes red.
  LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L7" \
    && ok "(L7) the poetry lock's pin survived" \
    || ko "(L7) jinja2==2.11.0 missing — a per-lock loop truncated it"
  LC_ALL=C grep -qFx 'werkzeug==0.16.0' "$PINS_L7" \
    && ok "(L7) the Pipfile lock's pin survived" \
    || ko "(L7) werkzeug==0.16.0 missing — a per-lock loop truncated it"
  [ "$(LC_ALL=C grep -c . "$PINS_L7")" -eq 2 ] \
    && ok "(L7) exactly TWO pins, one per lock" \
    || ko "(L7) expected 2 pins, got $(LC_ALL=C grep -c . "$PINS_L7")"
  # The tool was invoked ONCE with both locks: a single argv line mentioning the
  # pins file, not two. This is what makes "one variadic call" observable.
  [ "$(LC_ALL=C grep -c 'pins-from-locks.txt' "$PIPLOG")" -eq 1 ] \
    && ok "(L7) pip-audit received the pins file in a SINGLE invocation" \
    || ko "(L7) $(LC_ALL=C grep -c 'pins-from-locks.txt' "$PIPLOG") invocations carried the pins file"
  if [ ! -f "$DEG_L7" ] || [ "$(deg_python_count "$DEG_L7")" -eq 0 ]; then
    ok "(L7) proxy: no python: line — two fully read locks are a scanned perimeter"
  else
    ko "(L7) unexpected python: line(s): $(LC_ALL=C grep '^python:' "$DEG_L7")"
  fi
fi

# ---- (L8) an rc OTHER than 2 must degrade just the same ----------------------
# The failure mode this closes: enumerating exit codes instead of BOUNDING them.
# A resolver that dies with rc=1 — a traceback, an OOM, a killed process — must
# land in the same degraded branch as an invalid lock, or it passes for success.
echo
echo "=== (L8) py_lock_pins.py failing with rc=1 => still degraded"
REAL_PY="$(command -v python3 || command -v python || command -v py || true)"
if [ -z "$REAL_PY" ]; then
  echo "  SKIP (L8): aucun interpréteur python sur le PATH — rc≠2 NON mesuré"
else
  export REAL_PY
  # TWO FACES, AND THE SECOND IS THE ONE THAT MEASURES — this was found by
  # ROLLING mutation 10, not by reasoning about it (L-00000390). With a single
  # face the arm was GREEN under the very defect it names: a resolver that dies
  # writes NOTHING to stdout, so `$pl_out` is empty, so the FORMAT guard
  # (`pl_ok=0`) fires and degrades the run whatever the rc test says. The arm
  # proved the format guard twice over and the rc bound not at all.
  #   face 1 — rc=1 with EMPTY stdout: either guard may legitimately catch it.
  #   face 2 — rc=1 with a PERFECTLY VALID contract line: the format guard has
  #            nothing to object to, so ONLY the `-ne 0` bound can catch it.
  # That is the boundary L-00000387 asks to exercise on BOTH sides: face 2 is
  # the side where the exception must NOT save us.
  PYSTUB="$TMP/pystub"; mkdir -p "$PYSTUB"
  # The stub takes the BASENAME the dispatcher's probe resolves, so the PATH
  # prefix intercepts it. `export REAL_PY` is load-bearing: without it the `exec`
  # below runs `exec ""` and the arm dies at 127 — LOUDLY, which is the point.
  cat > "$PYSTUB/$(basename "$REAL_PY")" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *py_lock_pins.py*) echo "stub: traceback simulé" >&2; exit 1 ;;
esac
exec "$REAL_PY" "$@"
STUB
  chmod +x "$PYSTUB/$(basename "$REAL_PY")"
  PYSTUB2="$TMP/pystub2"; mkdir -p "$PYSTUB2"
  cat > "$PYSTUB2/$(basename "$REAL_PY")" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *py_lock_pins.py*)
    # A CONTRACT-PERFECT line, and then death. Nothing in the format is wrong;
    # only the exit code says the run failed.
    echo "excluded_root=0 excluded_dep=0"
    echo "stub: mort APRES avoir emis une ligne valide" >&2
    exit 1 ;;
esac
exec "$REAL_PY" "$@"
STUB
  chmod +x "$PYSTUB2/$(basename "$REAL_PY")"

  R_L8="$(make_root_bare l8rc1)"
  write_pipfile_lock "$R_L8"
  OUT_L8="$(cd "$R_L8" && PATH="$PYSTUB:$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l8=$?
  DEG_L8="$(report_dir "$R_L8")/.degraded"
  LOG_L8="$(report_dir "$R_L8")/py-locks.log"
  # Non-vacuity FIRST: prove the stub actually intercepted the resolver. Without
  # this, a PATH that failed to shadow would make every line below green for the
  # wrong reason — the run would simply have succeeded.
  [ -f "$LOG_L8" ] && LC_ALL=C grep -qF 'traceback simulé' "$LOG_L8" \
    && ok "(L8) face 1 witness: the stub really intercepted py_lock_pins.py" \
    || ko "(L8) face 1 witness: the stub never ran — this arm would measure nothing"
  [ -f "$DEG_L8" ] && LC_ALL=C grep -qF 'résolution ÉCHOUÉE' "$DEG_L8" \
    && ok "(L8) face 1: a dead resolver degrades the run" \
    || ko "(L8) face 1: rc=1 was not treated as a failure: $(cat "$DEG_L8" 2>/dev/null)"
  LC_ALL=C grep -qF 'rc=1' "$DEG_L8" \
    && ok "(L8) face 1: the real exit code is reported, not a hardcoded one" \
    || ko "(L8) face 1: rc=1 absent from the degradation line"

  R_L8B="$(make_root_bare l8valid)"
  write_pipfile_lock "$R_L8B"
  OUT_L8B="$(cd "$R_L8B" && PATH="$PYSTUB2:$LOCKBIN:$PATH" bash "$SCAN" 2>&1)"; rc_l8b=$?
  DEG_L8B="$(report_dir "$R_L8B")/.degraded"
  LOG_L8B="$(report_dir "$R_L8B")/py-locks.log"
  [ -f "$LOG_L8B" ] && LC_ALL=C grep -qF 'mort APRES avoir emis' "$LOG_L8B" \
    && ok "(L8) face 2 witness: the stub emitted a VALID line and then failed" \
    || ko "(L8) face 2 witness: the stub never ran — this arm would measure nothing"
  # MUTATION 10: restore `[ "$rc" -eq 2 ]`. Face 2 then falls through to the
  # file-absent branch and the report says "locks read, nothing to pin" — a
  # calm, false sentence about a resolver that CRASHED. This line goes red.
  # ROLLED: with face 1 alone the mutation left the suite at 74/0.
  [ -f "$DEG_L8B" ] && LC_ALL=C grep -qF 'résolution ÉCHOUÉE' "$DEG_L8B" \
    && ok "(L8) face 2: EVERY non-zero rc degrades — a BOUND, not an enumeration" \
    || ko "(L8) face 2: rc=1 with a valid line slipped through: $(cat "$DEG_L8B" 2>/dev/null)"
  ! LC_ALL=C grep -qF 'locks sans dépendance de registre' "$DEG_L8B" \
    && ok "(L8) face 2: a crashed resolver is never reported as an empty lock" \
    || ko "(L8) face 2: a crash was reported as 'nothing to pin'"
  [ "$(deg_python_count "$DEG_L8B")" -ge 1 ] \
    && ok "(L8) face 2 proxy: a python: line is present — the run is degraded" \
    || ko "(L8) face 2: no python: line for a failed resolver"
fi

# ---- (L9) BASH 3.2 FLOOR: replay the lock arms under the oldest interpreter ---
# The empty-array expansion `${py_reqs[@]+…}` and the lock sequence's placement
# are both bash-3.2 concerns, and lock-only mode is precisely where `py_reqs` is
# EMPTY — so this is not a formality.
echo
echo "=== (L9) bash 3.2 floor"
FLOOR_MAJ="$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || echo "")"
case "$FLOOR_MAJ" in
  ''|*[!0-9]*) echo "  SKIP (L9): /bin/bash injoignable ou sonde KO — plancher NON mesuré" ;;
  *)
    if [ "$FLOOR_MAJ" -ge 4 ]; then
      echo "  SKIP (L9): /bin/bash est en version $FLOOR_MAJ (>= 4) — le plancher 3.2 n'est PAS mesuré ici"
    else
      R_L9="$(make_root_bare l9floor)"
      write_pipfile_lock "$R_L9"
      OUT_L9="$(cd "$R_L9" && PATH="$LOCKBIN:$PATH" /bin/bash "$SCAN" 2>&1)"; rc_l9=$?
      PINS_L9="$(report_dir "$R_L9")/pins-from-locks.txt"
      [ -s "$PINS_L9" ] && LC_ALL=C grep -qFx 'jinja2==2.11.0' "$PINS_L9" \
        && ok "(L9) lock-only works under /bin/bash $FLOOR_MAJ (empty py_reqs array survives set -u)" \
        || ko "(L9) the lock path broke under bash $FLOOR_MAJ: $OUT_L9"
      [ "$rc_l9" -eq 1 ] \
        && ok "(L9) the verdict is reached under bash $FLOOR_MAJ (exit 1)" \
        || ko "(L9) expected exit 1 under bash $FLOOR_MAJ, got $rc_l9"
    fi
    ;;
esac

echo
echo "================================================================"
echo "sca-python: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Python SCA: a boxed HIGH goes red, an absent tool degrades but never blocks,"
echo "and a client file NAME is neutralised PER ELEMENT — the ', ' that joins the"
echo "list is grammar, not payload, so it survives while a comma in a name does not."
