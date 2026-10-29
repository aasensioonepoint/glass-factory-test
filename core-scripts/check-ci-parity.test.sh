#!/usr/bin/env bash
# ============================================================================
# GUARD OF THE GUARD — can core-scripts/check-ci-parity.sh still go red?
#
# The `.test.sh` suffix is deliberate and IS the registration: it makes
# `core-scripts/run-bash-tests.sh` discover this suite, and that runner is a step of
# BOTH `.github/workflows/ci.yml` and `core-scripts/verify.sh`. Case 1 runs the
# control against the REAL tree, so the parity net bites through the same door
# it guards — on the Windows dev box and on the linux leg alike. No new CI step
# is added on purpose: verify.sh must keep running EXACTLY what CI runs, and a
# third step in ci.yml alone would break that (the very promise this guards).
#
# ----------------------------------------------------------------------------
# ONE NEGATIVE CONTROL PER RULE, EACH WITH A POSITIVE TWIN
# ----------------------------------------------------------------------------
# A guard that cannot go red guards nothing. Every divergence class the control
# is meant to catch (D5 new step, D1/D2 flags off the allowlist, D4 apt drift,
# an empty extraction) therefore has a fixture that breaks it ONE AT A TIME,
# paired with a positive twin — without which a control that went red on
# everything would pass all the negative cases and prove nothing.
#
# The fixtures are COPIES of the real ci.yml / verify.sh, mutated: the control
# takes `--ci` and `--verify`, so a divergence is created on disk and fed in.
#
# Exit: 0 all cases pass · 1 at least one case failed.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

CONTROL="$ROOT/core-scripts/check-ci-parity.sh"
CI_REAL="$ROOT/.github/workflows/ci.yml"
VERIFY_REAL="$ROOT/core-scripts/verify.sh"
RUNNER="$ROOT/core-scripts/run-bash-tests.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
note() { echo "  $*"; }
ok()   { echo "--- PASS $1"; pass=$((pass + 1)); }
ko()   { echo "--- FAIL $1"; fail=$((fail + 1)); }

expect_rc() { # expect_rc <expected rc> <label> <control args...>
  local want="$1" label="$2"; shift 2
  local out rc
  out="$(bash "$CONTROL" "$@" 2>&1)"; rc=$?
  if [ "$rc" -eq "$want" ]; then
    ok "$label (rc=$rc)"
  else
    ko "$label (expected rc=$want, got rc=$rc)"
    printf '%s\n' "$out" | sed 's/^/      /'
  fi
  return 0
}

expect_says() { # expect_says <literal pattern> <label> <control args...>
  local pat="$1" label="$2"; shift 2
  local out
  out="$(bash "$CONTROL" "$@" 2>&1)"
  if printf '%s' "$out" | grep -qF -- "$pat"; then
    ok "$label"
  else
    ko "$label (pattern \"$pat\" absent from output)"
    printf '%s\n' "$out" | sed 's/^/      /'
  fi
  return 0
}

assert_ge() { # assert_ge <measured> <min> <label>
  if [ "${1:-0}" -ge "$2" ]; then ok "$3 (measured ${1:-0})"
  else ko "$3 — only ${1:-0}, perimeter has shrunk"; fi
}

# in_job_after <src> <dst> <anchor line> <block file> — copy <src> to <dst>,
# inserting the lines of <block file> right after the line EQUAL to <anchor>.
# Since T-00001183 ci.yml holds three jobs and the control compares the `tests`
# job only, so a fixture step must land INSIDE a job — appending at the end of
# the file would put it in the LAST job (`adoptant`). awk, not `sed 's/…/&\n…/'`:
# a newline in a sed replacement is not portable to BSD sed.
in_job_after() {
  awk -v anchor="$3" -v blk="$4" '
    { print }
    $0 == anchor { while ((getline l < blk) > 0) print l; close(blk) }
  ' "$1" > "$2"
  if cmp -s "$1" "$2"; then ko "fixture $2: the anchor [$3] was not found (vacuous mutation)"; fi
}
TESTS_ANCHOR='        run: bash core-scripts/run-bash-tests.sh'
PORTE_ANCHOR='          echo "porte=$porte" >> "$GITHUB_OUTPUT"'

# ============================================================================
echo "=== 1. THE REAL TREE — ci.yml and verify.sh are in parity"
# ============================================================================
expect_rc 0 "real repo: test commands, apt (by construction), python-version all agree" \
  --ci "$CI_REAL" --verify "$VERIFY_REAL"

echo
echo "=== 1bis. the measured perimeter is the one we believe (anti \"green and empty\")"
real_out="$(bash "$CONTROL" --ci "$CI_REAL" --verify "$VERIFY_REAL" 2>&1)"
note "$(printf '%s' "$real_out" | sed -n 's/^check-ci-parity: [0-9].*divergence.*/&/p')"
n_ci="$(printf '%s' "$real_out"     | sed -n -E 's/^check-ci-parity: ([0-9]+) CI test cmd.*/\1/p')"
n_host="$(printf '%s' "$real_out"   | sed -n -E 's/.* ([0-9]+) host step.*/\1/p')"
n_docker="$(printf '%s' "$real_out" | sed -n -E 's/.* ([0-9]+) docker cmd.*/\1/p')"
assert_ge "$n_ci"     2 ">= 2 CI test commands analysed"
assert_ge "$n_host"   2 ">= 2 verify.sh host steps analysed"
assert_ge "$n_docker" 2 ">= 2 verify.sh docker commands analysed"
# T-00001183: the adoptant perimeter is compared too, and must not be empty.
n_ci_ad="$(printf '%s' "$real_out"   | sed -n -E 's/.* adoptant: ci=([0-9]+) verify=.*/\1/p')"
n_host_ad="$(printf '%s' "$real_out" | sed -n -E 's/.* adoptant: ci=[0-9]+ verify=([0-9]+);.*/\1/p')"
assert_ge "$n_ci_ad"   1 ">= 1 ci.yml adoptant-job command analysed (porte_adoptant.py)"
assert_ge "$n_host_ad" 1 ">= 1 verify.sh adoptant step analysed (porte_adoptant.py)"

# ============================================================================
echo
echo "=== 2. D5 negative control: a NEW run: step in ci.yml, unreflected"
# ============================================================================
note "the structural hole — a step added to the tests job that verify.sh never runs"
printf '\n      - name: Extra check\n        run: bash scripts/extra-check.sh\n' > "$TMP/blk-addstep.txt"
in_job_after "$CI_REAL" "$TMP/ci-addstep.yml" "$TESTS_ANCHOR" "$TMP/blk-addstep.txt"
expect_rc 1 "new run: step in ci.yml, absent from verify.sh" \
  --ci "$TMP/ci-addstep.yml" --verify "$VERIFY_REAL"
expect_says "bash scripts/extra-check.sh" "the divergent command is named in full" \
  --ci "$TMP/ci-addstep.yml" --verify "$VERIFY_REAL"

echo
echo "=== 2bis. D5 POSITIVE twin: the same step reflected in BOTH verify.sh legs passes"
note "without this a control that reddened on everything would pass case 2 and prove nothing"
# host leg + docker heredoc both gain the command.
sed -E \
  -e 's#^step "bash core-scripts/run-bash-tests.sh" bash core-scripts/run-bash-tests.sh#&\nstep "bash scripts/extra-check.sh" bash scripts/extra-check.sh#' \
  -e 's#^        bash core-scripts/run-bash-tests.sh$#&\n        bash scripts/extra-check.sh#' \
  "$VERIFY_REAL" > "$TMP/verify-addstep.sh"
expect_rc 0 "new step reflected in ci.yml AND verify.sh host+docker" \
  --ci "$TMP/ci-addstep.yml" --verify "$TMP/verify-addstep.sh"

# ============================================================================
echo
echo "=== 2ter. ctags-PIN braces: one negative control PER brace — they must NOT over-eat"
# ============================================================================
note "the three is_setup braces (*curl*ctags* / *zipfile*ctags* / *ctags*--version*) are"
note "narrowed to *ctags*; a curl, a zipfile or a --version WITHOUT 'ctags' is a real test"
note "command and must still go RED — one probe per brace, so none can swallow a whole family"
{
  printf '\n      - name: Non-ctags commands (must not be swallowed)\n'
  printf '        run: |\n'
  printf '          curl -fsSL https://example.com/tool.zip\n'   # brace *curl*ctags* must NOT match
  printf '          python -m zipfile -e dist.zip out\n'         # brace *zipfile*ctags* must NOT match
  printf '          foo --version\n'                             # brace *ctags*--version* must NOT match
} > "$TMP/blk-nonctags.txt"
in_job_after "$CI_REAL" "$TMP/ci-nonctags.yml" "$TESTS_ANCHOR" "$TMP/blk-nonctags.txt"
expect_rc 1 "curl/zipfile/--version WITHOUT ctags stay divergences (braces don't over-eat)" \
  --ci "$TMP/ci-nonctags.yml" --verify "$VERIFY_REAL"
expect_says "curl -fsSL https://example.com/tool.zip" "brace *curl*ctags*: a bare curl is still named" \
  --ci "$TMP/ci-nonctags.yml" --verify "$VERIFY_REAL"
expect_says "python -m zipfile -e dist.zip out" "brace *zipfile*ctags*: a bare zipfile is still named" \
  --ci "$TMP/ci-nonctags.yml" --verify "$VERIFY_REAL"
expect_says "foo --version" "brace *ctags*--version*: a bare --version is still named" \
  --ci "$TMP/ci-nonctags.yml" --verify "$VERIFY_REAL"
note "positive twin = case 1 (real tree rc=0): the SAME braces DO swallow the real ctags"
note "step, else case 1 would have reddened the moment S1 added that step to ci.yml"

# ============================================================================
echo
echo "=== 3. negative control: a test command REMOVED from verify.sh's host leg"
# ============================================================================
sed '/^step "bash core-scripts\/run-bash-tests.sh"/d' "$VERIFY_REAL" > "$TMP/verify-rmhost.sh"
expect_rc 1 "run-bash-tests dropped from the host leg" \
  --ci "$CI_REAL" --verify "$TMP/verify-rmhost.sh"
expect_says "MISSING from verify.sh host leg" "the message names the leg that lost the command" \
  --ci "$CI_REAL" --verify "$TMP/verify-rmhost.sh"

# ============================================================================
echo
echo "=== 4. D1/D2 negative control: a flag change OFF the allowlist (-q -> -v)"
# ============================================================================
note "-q and --quiet are allowlisted verbosity; -v is a real behavioural change"
sed 's|bash core-scripts/run-pytest-shards.sh$|bash core-scripts/run-pytest-shards.sh -v|' "$VERIFY_REAL" > "$TMP/verify-flag.sh"
if cmp -s "$VERIFY_REAL" "$TMP/verify-flag.sh"; then ko "case 4: the flag mutant changed NOTHING (vacuous)"; fi
expect_rc 1 "the pytest runner call with -v in verify.sh vs ci.yml (not on the allowlist)" \
  --ci "$CI_REAL" --verify "$TMP/verify-flag.sh"

echo
echo "=== 4bis. D1/D2 POSITIVE twin: the allowlisted flags pass"
note "the REAL tree no longer carries pytest -q (the runner owns it, T-00001122), so the -q allowlist (D1)"
note "needs a FIXTURE twin: verify.sh with -q appended to the runner call vs the real ci.yml must be rc 0."
note "pip --quiet (D2) is still carried by the real tree: case 1 (real tree, rc=0) is its twin."
sed 's|bash core-scripts/run-pytest-shards.sh$|bash core-scripts/run-pytest-shards.sh -q|' "$VERIFY_REAL" > "$TMP/verify-q.sh"
if cmp -s "$VERIFY_REAL" "$TMP/verify-q.sh"; then ko "4bis: the -q fixture changed NOTHING (vacuous)"; fi
expect_rc 0 "the runner call with -q (allowlisted D1) is not a divergence" \
  --ci "$CI_REAL" --verify "$TMP/verify-q.sh"

# ============================================================================
echo
echo "=== 5. D4 negative control: an apt package added to ci.yml only"
# ============================================================================
note "with verify.sh's apt REGRESSED to a hardcoded literal (construction broken),"
note "a package ci.yml adds is no longer mirrored — exactly the drift D4 closes"
sed 's|sudo apt-get install -y universal-ctags jq|sudo apt-get install -y universal-ctags jq curl|' \
  "$CI_REAL" > "$TMP/ci-apt.yml"
sed -E 's#apt-get install -y -qq .* >/dev/null#apt-get install -y -qq universal-ctags jq git nodejs npm >/dev/null#' \
  "$VERIFY_REAL" > "$TMP/verify-hardapt.sh"
expect_rc 1 "curl added to ci.yml apt, verify.sh hardcoded without it" \
  --ci "$TMP/ci-apt.yml" --verify "$TMP/verify-hardapt.sh"
expect_says "curl" "the missing apt package is named" \
  --ci "$TMP/ci-apt.yml" --verify "$TMP/verify-hardapt.sh"

echo
echo "=== 5bis. D4 POSITIVE twin: the package added to BOTH sides passes"
sed -E 's#apt-get install -y -qq .* >/dev/null#apt-get install -y -qq universal-ctags jq curl git nodejs npm >/dev/null#' \
  "$VERIFY_REAL" > "$TMP/verify-aptcurl.sh"
expect_rc 0 "curl in ci.yml apt AND in verify.sh docker apt" \
  --ci "$TMP/ci-apt.yml" --verify "$TMP/verify-aptcurl.sh"

echo
echo "=== 5ter. D4 negative control: a docker surplus NOT named in RUNNER_PREINSTALLED"
note "an extra package verify installs but ci.yml does not, and which is not in the"
note "NAMED runner-preinstalled list, is an unexplained divergence"
sed -E 's#apt-get install -y -qq .* >/dev/null#apt-get install -y -qq universal-ctags jq git nodejs npm cowsay >/dev/null#' \
  "$VERIFY_REAL" > "$TMP/verify-surplus.sh"
expect_rc 1 "cowsay in verify docker, absent from ci.yml and RUNNER_PREINSTALLED" \
  --ci "$CI_REAL" --verify "$TMP/verify-surplus.sh"
expect_says "cowsay" "the unexplained surplus package is named" \
  --ci "$CI_REAL" --verify "$TMP/verify-surplus.sh"

# ============================================================================
echo
echo "=== 6. THE PERFECT FALSE GREEN: a reformat that empties the extraction"
# ============================================================================
note "a ci.yml the sed can no longer read must go RED, never green-and-empty"
cat > "$TMP/ci-broken.yml" <<'FIX'
name: ci
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-latest
FIX
expect_rc 1 "ci.yml with no extractable run:/apt/python-version" \
  --ci "$TMP/ci-broken.yml" --verify "$VERIFY_REAL"
expect_says "empty perimeter" "an empty extraction is a FAILURE, not a pass" \
  --ci "$TMP/ci-broken.yml" --verify "$VERIFY_REAL"

# ============================================================================
echo
echo "=== 7. USAGE — an unknown or malformed flag is REFUSED (rc=2), never ignored"
# ============================================================================
expect_rc 2 "unknown flag"                 --bogus
expect_rc 2 "--ci with no value"           --ci
expect_rc 2 "--ci to a nonexistent file"   --ci "$TMP/nope.yml" --verify "$VERIFY_REAL"
expect_rc 2 "--verify to a nonexistent file" --ci "$CI_REAL" --verify "$TMP/nope.sh"

# ============================================================================
echo
echo "=== 8. THE WIRING EXISTS — auto-discovery + this suite bites the real tree"
# ============================================================================
# Link one: the `*.test.sh` glob in run-bash-tests.sh is the ONLY reason this
# suite runs in CI at all. Comments stripped FIRST — a grep for the substring
# would happily match a disabled line.
runner_live="$(sed -E 's/^[[:space:]]*#.*$//' "$RUNNER")"
if printf '%s' "$runner_live" | grep -qF "'*.test.sh'"; then
  ok "run-bash-tests.sh still discovers *.test.sh (this suite runs in CI)"
else
  ko "run-bash-tests.sh no longer globs *.test.sh — this guard is UNWIRED"
fi

# NEGATIVE control: the same glob commented out must read as absent.
cat > "$TMP/runner-commented.sh" <<'FIX'
#!/usr/bin/env bash
find . \
  -path ./.git -prune -o \
  # -name '*.test.sh' -type f -print | LC_ALL=C sort
  -name '*.spec.sh' -type f -print | LC_ALL=C sort
FIX
runner_c="$(sed -E 's/^[[:space:]]*#.*$//' "$TMP/runner-commented.sh")"
if printf '%s' "$runner_c" | grep -qF "'*.test.sh'"; then
  ko "a COMMENTED-OUT glob was counted — case 8 is inert"
else
  ok "a COMMENTED-OUT discovery glob does not count (disarming would be SEEN)"
fi

# This suite must carry the suffix the glob matches.
case "$(basename "${BASH_SOURCE[0]}")" in
  *.test.sh) ok "this suite carries the .test.sh suffix the glob matches" ;;
  *)         ko "this suite does NOT carry .test.sh — it would never be discovered" ;;
esac

# Link two: this suite still POINTS at the real tree and asserts rc=0 on it.
# Assert the glob alone and the control could be diverted to only faked trees.
expect_rc 0 "this suite still asserts rc=0 on the REAL ci.yml + verify.sh" \
  --ci "$CI_REAL" --verify "$VERIFY_REAL"

# ============================================================================
echo
echo "=== 9. CWE-78: a shell metacharacter in ci.yml's apt line is REFUSED at extraction"
# ============================================================================
# verify.sh's --linux leg EXTRACTS the apt list from ci.yml and, before T-00000113
# hardening, spliced it into the container `bash -c '…'` script text — so a
# metacharacter (`;`, `$(...)`, backtick) on the `apt-get install -y` line would
# be re-parsed as CODE inside the container (which mounts the tree RW). The fix
# is belt-and-braces: (a) the value now crosses as an ENV var, never spliced;
# (b) each token is BOUND to a Debian package-name charset at extraction. This
# case runs the REAL extract+validate block — SLICED verbatim from verify.sh so
# it exercises the shipped bytes, not a copy that could drift — against fixtures.
note "the block is delimited by >>>/<<< markers in verify.sh; this test slices and runs it"

GUARD_BODY="$(sed -n '/# >>> apt-extract-validate/,/# <<< apt-extract-validate/p' "$VERIFY_REAL" \
  | sed '/# >>> apt-extract-validate/d; /# <<< apt-extract-validate/d')"
if [ -n "$GUARD_BODY" ] && printf '%s' "$GUARD_BODY" | grep -qF 'CI_APT='; then
  ok "the apt-extract-validate block is present and sliceable from verify.sh"
else
  ko "could not slice the apt-extract-validate block from verify.sh (markers moved?)"
fi

PWNED="$TMP/pwned"
guard_out=""; guard_rc=0
run_guard() { # run_guard <apt-rest-string>  — writes fixture, runs the sliced guard
  local rest="$1" root _guard_sh
  root="$(mktemp -d)"
  mkdir -p "$root/.github/workflows"
  {
    printf 'jobs:\n  tests:\n    steps:\n'
    printf '      - name: deps\n        run: |\n'
    printf '          sudo apt-get install -y %s\n' "$rest"
  } > "$root/.github/workflows/ci.yml"
  # printf writes $rest LITERALLY: `;`, `$(...)` and backticks land in the file
  # as bytes, never interpreted by the writing shell. The guard then runs them.
  # T-00000540 — la tranche de garde était splicée DANS le texte d'un `bash -c` :
  # finding `ERROR` de classe 1 (`agents.security.shell-c-flag-with-interpolation`),
  # NON-WAIVABLE, et invisible tant que ce fichier n'était pas parsé par le SAST.
  # Elle est maintenant écrite dans un FICHIER puis exécutée. Même corps, même
  # `set -uo pipefail` en tête, même shell — mais plus aucune re-analyse d'une
  # valeur comme syntaxe.
  _guard_sh="$(mktemp)"
  { printf 'set -uo pipefail\n'; printf '%s\n' "$GUARD_BODY"; } > "$_guard_sh"
  guard_out="$( cd "$root" && CI_REQS="$root/.reqs" bash "$_guard_sh" 2>&1 )"
  guard_rc=$?   # RELEVÉ AVANT le `rm` : sinon c'est le statut de `rm` qu'on lit
  rm -f "$_guard_sh"
  rm -rf "$root"
}

check_refused() { # check_refused <label> <apt-rest-string>
  local label="$1" rest="$2"
  rm -f "$PWNED"
  run_guard "$rest"
  if [ "$guard_rc" -ne 0 ]; then ok "$label — guard REFUSES (rc=$guard_rc)"
  else ko "$label — guard did NOT refuse (rc=$guard_rc)"; fi
  if printf '%s' "$guard_out" | grep -qF -- "CWE-78 guard"; then
    ok "$label — refusal names the CWE-78 guard and the bad token"
  else
    ko "$label — refusal message unclear"; printf '%s\n' "$guard_out" | sed 's/^/      /'
  fi
  if [ ! -e "$PWNED" ]; then ok "$label — NO side effect ($PWNED absent)"
  else ko "$label — SIDE EFFECT: $PWNED was created"; rm -f "$PWNED"; fi
}

note "each metachar the container bash -c would re-parse must be rejected BEFORE any use"
check_refused "command chaining \`;\`"      "foo; touch $PWNED"
check_refused "command substitution \$(...)" "\$(touch $PWNED)"
check_refused "backtick substitution"        "\`touch $PWNED\`"
check_refused "redirection into the tree"    "foo > $PWNED"

echo
echo "=== 9bis. POSITIVE twin: the real package list passes the same guard"
note "without this, a guard that reddened on everything would pass case 9 and prove nothing"
run_guard "universal-ctags jq"
if [ "$guard_rc" -eq 0 ]; then ok "clean Debian package names (universal-ctags jq) pass (rc=0)"
else ko "clean package list wrongly refused (rc=$guard_rc)"; printf '%s\n' "$guard_out" | sed 's/^/      /'; fi

echo
echo "=== 9ter. WIRING: verify.sh's docker leg passes \$APT_PKGS as ENV, never spliced"
note "point (a) of the fix: closing the single quote to interpolate the value is gone"
verify_live="$(sed -E 's/^[[:space:]]*#.*$//' "$VERIFY_REAL")"
if printf '%s' "$verify_live" | grep -qF -- '-e APT_PKGS="$APT_PKGS"'; then
  ok "docker run carries -e APT_PKGS=\"\$APT_PKGS\" (value crosses as an env var)"
else
  ko "docker run no longer passes APT_PKGS as an env var"
fi
if printf '%s' "$verify_live" | grep -qF -- "'\"\$APT_PKGS\"'"; then
  ko "verify.sh STILL splices '\"\$APT_PKGS\"' into the container script text (CWE-78)"
else
  ok "the old quote-break splice '\"\$APT_PKGS\"' is gone from verify.sh"
fi
# The apt line may carry apt OPTIONS between `-y -qq` and the variable
# (`--no-install-recommends`, T-00000453), so the pattern admits a BOUNDED
# option run — `( --[a-z-]+)*`, long options only — and never a `.*`, which
# would empty the net it widens. What this still forbids is what it was built
# for: `"$APT_PKGS"` QUOTED (one arg instead of one per package) and a literal
# package list in place of the variable. Both mutations stay red.
if printf '%s' "$verify_live" | grep -qE 'apt-get install -y -qq( --[a-z-]+)* \$APT_PKGS'; then
  ok "the container apt line references \$APT_PKGS unquoted (multi-package word-split preserved)"
else
  ko "the container apt line no longer references \$APT_PKGS unquoted"
fi

# ============================================================================
echo
echo "=== 10. THE CI PIN: the REAL ci.yml keeps CADRE_GATE_JOBS: \"1\" in the env: of the tests job"
# ============================================================================
# T-00001122: the local gate plays pytest and the bash suites in PARALLEL processes, and
# CI is pinned to the BARE serial reference instead of guessing from the runner size.
# Nothing else sees that pin — `collect_ci` reads `run:` lines only and the pins guard
# reads `uses:`/pip lines: removing it left every case above GREEN (measured by the plan
# critique). This case reads the env: block of the `tests` job, scoped by indentation.
pin_in_tests_env() { # pin_in_tests_env <ci.yml> — rc 0 iff `CADRE_GATE_JOBS: "1"` sits in jobs.tests.env
  awk '
    /^jobs:[[:space:]]*$/ { j = 1; next }
    j && /^  [A-Za-z0-9_-]+:/ { t = ($0 ~ /^  tests:[[:space:]]*$/); e = 0; next }
    j && t && /^    env:[[:space:]]*$/ { e = 1; next }
    j && t && e && /^    [^ #]/ { e = 0 }
    j && t && e && /^      CADRE_GATE_JOBS:[[:space:]]*"1"[[:space:]]*$/ { f = 1 }
    END { exit !f }' "$1"
}
if pin_in_tests_env "$CI_REAL"; then
  ok "the real ci.yml pins CADRE_GATE_JOBS: \"1\" in the tests job env (CI = the bare reference)"
else
  ko "the real ci.yml LOST its CADRE_GATE_JOBS: \"1\" pin — CI would guess parallelism from the runner size"
fi
note "negative twins: the pin removed, set to another value, or moved to another job must NOT count"
sed '/^      CADRE_GATE_JOBS: "1"$/d' "$CI_REAL" > "$TMP/ci-nopin.yml"
sed 's/^      CADRE_GATE_JOBS: "1"$/      CADRE_GATE_JOBS: "auto"/' "$CI_REAL" > "$TMP/ci-autopin.yml"
{ cat "$TMP/ci-nopin.yml"; printf '  other:\n    runs-on: ubuntu-latest\n    env:\n      CADRE_GATE_JOBS: "1"\n'; } > "$TMP/ci-otherjob.yml"
for _fx in ci-nopin.yml ci-autopin.yml ci-otherjob.yml; do
  if cmp -s "$CI_REAL" "$TMP/$_fx"; then
    ko "10: the fixture $_fx changed NOTHING (vacuous)"
  elif pin_in_tests_env "$TMP/$_fx"; then
    ko "10: $_fx is read as pinned — the pin check cannot go red"
  else
    ok "10: $_fx is NOT read as pinned"
  fi
done

# ============================================================================
echo
echo "=== 11. THE BOUND (T-00001183): only the tests job is compared to the kit legs"
# ============================================================================
# Before T-00001183 `collect_ci` read EVERY `run:` of the file; with the jobs
# `porte` and `adoptant` present that is 20 divergences on the real tree
# (measured). The bound is load-bearing, so it gets a twin that only a bounded
# control passes: a test-looking command in the `porte` job is NOT a kit command.
printf '          bash scripts/porte-only-probe.sh\n' > "$TMP/blk-porte.txt"
in_job_after "$CI_REAL" "$TMP/ci-porte-run.yml" "$PORTE_ANCHOR" "$TMP/blk-porte.txt"
expect_rc 0 "a run: command inside the porte job is not compared to verify.sh (bounded to tests)" \
  --ci "$TMP/ci-porte-run.yml" --verify "$VERIFY_REAL"
note "MUTATION: read the whole file again in collect_ci -> this case (and case 1) go red"

# ============================================================================
echo
echo "=== 12. an UNKNOWN job is refused, never silently ignored"
# ============================================================================
{ cat "$CI_REAL"; printf '\n  extra:\n    runs-on: ubuntu-latest\n    steps:\n      - run: bash scripts/extra.sh\n'; } > "$TMP/ci-unknownjob.yml"
expect_rc 1 "a fourth job [extra] in ci.yml" --ci "$TMP/ci-unknownjob.yml" --verify "$VERIFY_REAL"
expect_says "UNKNOWN job [extra]" "the unknown job is named" --ci "$TMP/ci-unknownjob.yml" --verify "$VERIFY_REAL"

# ============================================================================
echo
echo "=== 13. THE ADOPTANT PERIMETER: verify.sh's adoptant step <-> the adoptant job"
# ============================================================================
note "the adoptant step is set apart from the kit steps: on the real tree it is NOT a kit divergence"
expect_says "ci-adoptant   | python .agents/bin/porte_adoptant.py" "the adoptant job's run is in the adoptant perimeter" \
  --ci "$CI_REAL" --verify "$VERIFY_REAL"
expect_says "host-adoptant | python .agents/bin/porte_adoptant.py" "verify.sh's adoptant step is in the adoptant perimeter" \
  --ci "$CI_REAL" --verify "$VERIFY_REAL"

note "negative: the adoptant job no longer runs the gate script (CI side empty)"
sed 's|^        run: python .agents/bin/porte_adoptant.py$|        run: echo gate removed|' "$CI_REAL" > "$TMP/ci-noadoptant.yml"
if cmp -s "$CI_REAL" "$TMP/ci-noadoptant.yml"; then ko "13: the CI-side mutant changed NOTHING (vacuous)"; fi
expect_rc 1 "adoptant job without porte_adoptant.py" --ci "$TMP/ci-noadoptant.yml" --verify "$VERIFY_REAL"
expect_says "empty adoptant perimeter" "the empty adoptant side is named" \
  --ci "$TMP/ci-noadoptant.yml" --verify "$VERIFY_REAL"

note "negative: verify.sh lost its adoptant step (host side empty)"
sed '/step "porte adoptant"/d' "$VERIFY_REAL" > "$TMP/verify-noadoptant.sh"
if cmp -s "$VERIFY_REAL" "$TMP/verify-noadoptant.sh"; then ko "13: the host-side mutant changed NOTHING (vacuous)"; fi
expect_rc 1 "verify.sh without its adoptant step" --ci "$CI_REAL" --verify "$TMP/verify-noadoptant.sh"
expect_says "empty adoptant perimeter" "the empty adoptant side is named" \
  --ci "$CI_REAL" --verify "$TMP/verify-noadoptant.sh"

note "negative: the two sides run the gate DIFFERENTLY"
sed 's|^        run: python .agents/bin/porte_adoptant.py$|        run: python .agents/bin/porte_adoptant.py --liste|' "$CI_REAL" > "$TMP/ci-adoptant-flag.yml"
if cmp -s "$CI_REAL" "$TMP/ci-adoptant-flag.yml"; then ko "13: the flag mutant changed NOTHING (vacuous)"; fi
expect_rc 1 "adoptant job runs porte_adoptant.py --liste, verify.sh runs it bare" \
  --ci "$TMP/ci-adoptant-flag.yml" --verify "$VERIFY_REAL"
expect_says "MISSING from verify.sh adoptant step" "the divergence names the adoptant leg" \
  --ci "$TMP/ci-adoptant-flag.yml" --verify "$VERIFY_REAL"

note "negative: the gate command moved into the TESTS job is a kit divergence, not an adoptant match"
printf '\n      - name: Gate in the wrong job\n        run: python .agents/bin/porte_adoptant.py\n' > "$TMP/blk-gate-in-tests.txt"
in_job_after "$TMP/ci-noadoptant.yml" "$TMP/ci-gate-in-tests.yml" "$TESTS_ANCHOR" "$TMP/blk-gate-in-tests.txt"
expect_rc 1 "porte_adoptant.py run by the tests job instead of the adoptant job" \
  --ci "$TMP/ci-gate-in-tests.yml" --verify "$VERIFY_REAL"

echo
echo "================================================================"
echo "check-ci-parity: $pass passed / $fail failed"
[ "$fail" -eq 0 ] || exit 1
echo "CI <> verify.sh parity: guard green, and red on every one of its fixtures."
