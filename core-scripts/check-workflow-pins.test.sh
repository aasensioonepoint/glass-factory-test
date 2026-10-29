#!/usr/bin/env bash
# ============================================================================
# GUARD OF THE GUARD — can core-scripts/check-workflow-pins.sh still go red?
#
# The `.test.sh` suffix is deliberate and IS the registration: it makes
# `core-scripts/run-bash-tests.sh` discover this suite, and run-bash-tests.sh is a
# step of BOTH `.github/workflows/ci.yml` and `core-scripts/verify.sh`. Case 1 below
# runs the scanner against the REAL tree, so the pinning guard is enforced by
# the same door it guards — on the Windows dev box and on the linux leg alike.
# No new CI step was added on purpose: verify.sh must keep running exactly what
# CI runs, and a third step in ci.yml alone would have broken that.
#
# THAT WIRING IS A CHAIN OF TWO LINKS, AND BOTH ARE ASSERTED (case 10 / 10bis):
# the discovery glob makes this suite RUN, and case 1 makes it BITE. Either link
# cut in silence leaves the pinning guard out of the pipeline with nothing red —
# measured: case 1's two lines commented out used to give `43 passed / 0 failed`,
# rc=0. Case 1bis does not cover for it; it asserts the perimeter COUNTS, which a
# real violation leaves untouched.
#
# ----------------------------------------------------------------------------
# ONE NEGATIVE CONTROL PER RULE, AND THAT IS THE POINT OF THE FILE
# ----------------------------------------------------------------------------
# A guard that cannot go red guards nothing, and its green is worse than nothing
# because it reassures. Every rule of check-workflow-pins.sh therefore has a
# fixture here that breaks it, ONE AT A TIME: if the scanner returned 1 for a
# collateral reason, the fixture would not prove what it claims to prove. Each
# negative control is paired with a POSITIVE one, without which a scanner that
# went red on everything would pass all the negative cases and measure nothing.
#
# THE R2 FIXTURE IS THE REPO'S REAL LINE, WORD FOR WORD:
#     run: python -m pip install --upgrade pip pytest
# That is what ci.yml and eval-nightly.yml carried before the hash pinning, and
# that line no longer exists anywhere in the tree. It survives here because a
# guard must be proven red on the ACTUAL defect it just removed, not on a
# textbook approximation that would be easier to catch. A rule written for bare
# `pip install` would never have seen it.
#
# THE INVERSE TRAP IS JUST AS MANDATORY: this repo's workflows spell out what
# they avoid — ci.yml's header writes `actions/checkout@v4` to explain why it no
# longer uses it, and names the removed `--upgrade pip` line. A guard matching
# substrings would go red on the PROSE and be disarmed within the week.
#
# AND THE PERFECT FALSE GREEN: "0 violations over 0 subjects" is green and
# measures nothing. Two cases exercise it, plus an explicit assertion on the
# measured perimeter of the real tree.
#
# Exit: 0 all cases pass · 1 at least one case failed.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

SCANNER="$ROOT/core-scripts/check-workflow-pins.sh"

PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "no python interpreter on PATH" >&2; exit 1; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
note() { echo "  $*"; }
ok()   { echo "--- PASS $1"; pass=$((pass + 1)); }
ko()   { echo "--- FAIL $1"; fail=$((fail + 1)); }

# fixture <name> — creates $TMP/<name>/.github/workflows/ and prints the path.
fixture() {
  local d="$TMP/$1/.github/workflows"
  mkdir -p "$d"
  printf '%s' "$d"
}

expect_rc() { # expect_rc <expected rc> <label> <scanner args...>
  local want="$1" label="$2"; shift 2
  local out rc
  out="$(bash "$SCANNER" "$@" 2>&1)"; rc=$?
  if [ "$rc" -eq "$want" ]; then
    ok "$label (rc=$rc)"
  else
    ko "$label (expected rc=$want, got rc=$rc)"
    printf '%s\n' "$out" | sed 's/^/      /'
  fi
  return 0
}

expect_says() { # expect_says <literal pattern> <label> <scanner args...>
  local pat="$1" label="$2"; shift 2
  local out
  out="$(bash "$SCANNER" "$@" 2>&1)"
  if printf '%s' "$out" | grep -qF -- "$pat"; then
    ok "$label"
  else
    ko "$label (pattern \"$pat\" absent from output)"
    printf '%s\n' "$out" | sed 's/^/      /'
  fi
  return 0
}

# Shared prologue for single-rule fixtures: root permissions present so R3 does
# not fire collaterally and muddy the verdict of the rule under test.
HDR='name: ci
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
'

# ============================================================================
echo "=== 1. THE REAL TREE holds all four rules"
# ============================================================================
expect_rc 0 "real repo: uses: pinned, pip hash-pinned, permissions root, credentials dropped" \
  --root "$ROOT"

# EFFECTIVENESS PROVEN BEFORE ANY CLAIM. An rc=0 alone does not say whether the
# guard LOOKED at anything. So the measured PERIMETER is asserted: if a workflow
# fell out of the analysis (path changed, glob broken), this case goes red while
# the previous one would stay green.
echo
echo "=== 1bis. the measured perimeter is the one we believe (anti \"green and empty\")"
real_out="$(bash "$SCANNER" --root "$ROOT" 2>&1)"
note "$real_out"
field() { printf '%s' "$real_out" | sed -n "s/.* \\([0-9]*\\) $1.*/\\1/p"; }
n_wf="$(printf '%s' "$real_out" | sed -n 's/^check-workflow-pins: \([0-9]*\) workflow.*/\1/p')"
n_uses="$(field 'uses: site(s)')"
n_co="$(field 'checkout(s)')"
n_pip="$(field 'pip line(s)')"
n_pin="$(field 'pinned requirement(s)')"
# T-00001183: the job `adoptant` installs semgrep by `-r` from
# .agents/security/gardes-ci-requirements.txt — that file must be OPENED (R2d).
n_reqf="$(field 'requirement file(s) followed')"
assert_ge() { # assert_ge <measured> <min> <label>
  if [ "${1:-0}" -ge "$2" ]; then ok "$3 (measured ${1:-0})"
  else ko "$3 — only ${1:-0}, perimeter has shrunk"; fi
}
assert_ge "$n_wf"   2  ">= 2 workflows analysed"
assert_ge "$n_uses" 4  ">= 4 uses: sites analysed"
assert_ge "$n_co"   2  ">= 2 checkout steps analysed"
assert_ge "$n_pip"  2  ">= 2 pip lines analysed"
assert_ge "$n_pin"  10 ">= 10 pinned requirement lines analysed"
assert_ge "$n_reqf" 1  ">= 1 requirement file followed by -r (gardes-ci-requirements.txt)"

# ============================================================================
echo
echo "=== 2. R1 negative control: a uses: on a FLOATING TAG"
# ============================================================================
note "the defect itself: a tag is a mutable pointer, moved with no commit here"
d="$(fixture r1-tag)"
printf '%s      - uses: actions/setup-python@v5\n' "$HDR" > "$d/ci.yml"
expect_rc 1 "uses: actions/setup-python@v5 (floating tag)" --root "$TMP/r1-tag"
expect_says "is NOT pinned to a SHA-40" "the message names the missing digest" \
  --root "$TMP/r1-tag"
expect_says "ci.yml:8" "the message names the FAULTY LINE" --root "$TMP/r1-tag"

echo
echo "=== 2bis. R1 negative control: SHA-40 with NO tag comment"
note "immutable but UNAUDITABLE: nobody recognises a bare digest, so nobody will"
note "ever know whether it needs bumping"
d="$(fixture r1-nocomment)"
printf '%s      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n' "$HDR" > "$d/ci.yml"
expect_rc 1 "SHA-40 without \"# vX.Y.Z\"" --root "$TMP/r1-nocomment"
expect_says "digest is unauditable" "the message names unauditability, not the digest" \
  --root "$TMP/r1-nocomment"

echo
echo "=== 2ter. R1 — a truncated \"# v5\" is not enough either"
note "a major-only tag comment is as uninformative as the floating tag removed"
d="$(fixture r1-major)"
printf '%s      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5\n' "$HDR" > "$d/ci.yml"
expect_rc 1 "comment \"# v5\" (incomplete semver)" --root "$TMP/r1-major"

echo
echo "=== 2ter-bis. R1 — a floating tag WEARING a valid tag comment is the worst case"
note "MUTATION TESTING FOUND THIS GAP: with the SHA-40 rule disabled, case 2 still"
note "went red — but only because its bare ref also lacked a tag comment, i.e. via"
note "the OTHER rule. This fixture isolates the digest rule: \`@v5 # v5.6.0\` looks"
note "auditable and is still a mutable pointer. Only R1's digest check can catch it."
d="$(fixture r1-disguised)"
printf '%s      - uses: actions/setup-python@v5 # v5.6.0\n' "$HDR" > "$d/ci.yml"
expect_rc 1 "floating tag disguised by a well-formed \"# v5.6.0\" comment" \
  --root "$TMP/r1-disguised"
expect_says "is NOT pinned to a SHA-40" "the digest rule alone carries this verdict" \
  --root "$TMP/r1-disguised"

echo
echo "=== 2quater. R1 POSITIVE control: the correct form passes, local action ignored"
note "without this case a scanner going red on EVERYTHING would pass 2 to 2ter"
note "and prove nothing at all"
d="$(fixture r1-ok)"
cat > "$d/ci.yml" <<'FIX'
name: ci
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
      # LOCAL action: a path in this repo, already frozen by the current commit.
      - uses: ./.github/actions/house
      - name: checkout-like spelling, uses: on its own line
        uses: actions/setup-node@1e60f620b9541d16bece96c5465dc8ee9832be0b # v4.0.4
FIX
expect_rc 0 "SHA-40 + \"# vX.Y.Z\", local action tolerated, both uses: spellings" \
  --root "$TMP/r1-ok"

# ============================================================================
echo
echo "=== 3. R2 negative control: THE REAL LINE the hash pinning removed"
# ============================================================================
note "word for word what ci.yml and eval-nightly.yml carried; this line no longer"
note "exists in the tree and survives only as this fixture"
d="$(fixture r2-real)"
cat > "$d/eval-nightly.yml" <<'FIX'
name: eval-nightly
permissions:
  contents: read
jobs:
  live-eval:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    steps:
      - name: Install pytest
        run: python -m pip install --upgrade pip pytest
FIX
expect_rc 1 "python -m pip install --upgrade pip pytest (the original line)" \
  --root "$TMP/r2-real"
expect_says "pip, pytest" "BOTH floating packages are named, not just the first" \
  --root "$TMP/r2-real"
expect_says "WITHOUT --require-hashes" "the absence of hash checking is named too" \
  --root "$TMP/r2-real"

echo
echo "=== 3bis. R2 — the other real spellings of pip are covered"
note "a rule written for bare \"pip install\" would have missed this repo's form"
d="$(fixture r2-forms)"
for form in "pip install pytest" "pip3 install pytest" "python3 -m pip install pytest"; do
  printf '%s      - run: %s\n' "$HDR" "$form" > "$d/a.yml"
  expect_rc 1 "$form" --root "$TMP/r2-forms"
done

echo
echo "=== 3ter. R2 negative control: VERSION-pinned but no hash checking"
note "this is the partial progress an \`==\` pin buys: the version is frozen, the"
note "ARTEFACT is not — PyPI allows a distribution file to be replaced"
d="$(fixture r2-nohash)"
printf '%s      - run: python -m pip install pytest==9.1.1\n' "$HDR" > "$d/a.yml"
expect_rc 1 "pytest==9.1.1 without --require-hashes" --root "$TMP/r2-nohash"

echo
echo "=== 3quater. R2 negative control: a requirement line with a TRUNCATED hash"
note "a short or garbled sha256 must not pass for a hash — it would read as"
note "pinned while pip could never match it"
d="$(fixture r2-shorthash)"
cat > "$d/a.yml" <<'FIX'
name: a
permissions:
  contents: read
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          REQ="$(mktemp)"
          cat > "$REQ" <<'EOF'
          pytest==9.1.1 --hash=sha256:37a86b45efb9a47a
          EOF
          python -m pip install --require-hashes --only-binary :all: -r "$REQ"
FIX
expect_rc 1 "requirement line with a 16-hex-char hash" --root "$TMP/r2-shorthash"
expect_says "NO valid --hash=sha256:<64 hex>" "the message names the invalid hash" \
  --root "$TMP/r2-shorthash"

echo
echo "=== 3quinquies. R2 POSITIVE control: the real hardened form passes"
note "and it proves the tokenizer does not read \":all:\" (the VALUE of"
note "--only-binary) as an unpinned package — that FALSE RED is how a guard"
note "gets disarmed, and it is as toxic as a false green"
d="$(fixture r2-ok)"
cat > "$d/a.yml" <<'FIX'
name: a
permissions:
  contents: read
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          set -euo pipefail
          REQ="$(mktemp)"
          cat > "$REQ" <<'EOF'
          pytest==9.1.1 --hash=sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c
          colorama==0.4.6; sys_platform == "win32" --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6
          EOF
          python -m pip install --require-hashes --only-binary :all: --disable-pip-version-check -r "$REQ"
      - run: python -m pip install --require-hashes -r reqs.txt && echo "installed"
FIX
# `-r reqs.txt` is FOLLOWED since T-00001183 (R2d): the file must exist and be
# hash-pinned, or this positive control would be reporting a missing fixture.
printf 'pytest==9.1.1 --hash=sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c\n' \
  > "$TMP/r2-ok/reqs.txt"
expect_rc 0 "hash-pinned form, marker-gated line, flag VALUES and && chaining" \
  --root "$TMP/r2-ok"

# ============================================================================
echo
echo "=== 4. R3 negative control: NO root permissions: block"
# ============================================================================
note "with no root block the token inherits the organisation default, which this"
note "repo does not control and which may be \"read and write\""
d="$(fixture r3-absent)"
cat > "$d/ci.yml" <<'FIX'
name: ci
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
FIX
expect_rc 1 "no root permissions:" --root "$TMP/r3-absent"

echo
echo "=== 4bis. R3 negative control: root permissions in WRITE"
d="$(fixture r3-write)"
cat > "$d/ci.yml" <<'FIX'
name: ci
permissions:
  contents: write
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
FIX
expect_rc 1 "permissions: contents: write at the root" --root "$TMP/r3-write"

echo
echo "=== 4ter. R3 — a permissions: INSIDE A JOB does not count as root"
note "a job block covers THAT job only: the next one falls back to the org"
note "default. That is the trap the \"root\" rule exists to close."
d="$(fixture r3-job)"
cat > "$d/ci.yml" <<'FIX'
name: ci
jobs:
  tests:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo ok
  other:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
FIX
expect_rc 1 "permissions: declared only inside a job" --root "$TMP/r3-job"

# ============================================================================
echo
echo "=== 5. R4 negative control: checkout KEEPING the token"
# ============================================================================
note "the default leaves GITHUB_TOKEN in .git/config for every later step — which"
note "is what turns an unpinned install into an exfiltration path"
d="$(fixture r4-absent)"
printf '%s      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0\n' "$HDR" > "$d/ci.yml"
expect_rc 1 "checkout without persist-credentials: false" --root "$TMP/r4-absent"
expect_says "GITHUB_TOKEN stays in .git/config" "the message names the exposure" \
  --root "$TMP/r4-absent"

echo
echo "=== 5bis. R4 negative control: persist-credentials: true with NO justification"
d="$(fixture r4-true)"
cat > "$d/ci.yml" <<'FIX'
name: ci
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: true
FIX
expect_rc 1 "persist-credentials: true, unexplained" --root "$TMP/r4-true"

echo
echo "=== 5ter. R4 POSITIVE control: a job that really pushes STATES it"
note "a rule with no way out is deleted the first time it is inconvenient; a"
note "stated reason is accepted, and stays greppable"
d="$(fixture r4-needs)"
cat > "$d/ci.yml" <<'FIX'
name: ci
permissions:
  contents: read
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: true # needs-token: this job pushes the rebuilt index
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
FIX
expect_rc 0 "persist-credentials: true + \"# needs-token: <reason>\", and false next door" \
  --root "$TMP/r4-needs"

# ============================================================================
echo
echo "=== 6. A workflow with NO uses: at all is legitimate and passes"
# ============================================================================
d="$(fixture no-uses)"
cat > "$d/a.yml" <<'FIX'
name: a
permissions:
  contents: read
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: echo "no action, no pip, nothing to pin"
FIX
expect_rc 0 "no uses:, no pip -> nothing to pin, green" --root "$TMP/no-uses"

# ============================================================================
echo
echo "=== 7. TRAP: workflows that CITE in comments what they avoid"
# ============================================================================
note "this is the REAL shape of our files — they name the defect they fixed."
note "Without this case the guard would go red on the prose."
d="$(fixture prose)"
cat > "$d/ci.yml" <<'FIX'
name: ci

# This workflow once carried  uses: actions/checkout@v4  and
#   run: python -m pip install --upgrade pip pytest
# Both are gone: mutable tag + floating packages. It also had
#   uses: actions/setup-python@v5
# and no persist-credentials: true anywhere, and pytest==9.1.1 unhashed.

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
FIX
expect_rc 0 "comment citations -> green" --root "$TMP/prose"

# ============================================================================
echo
echo "=== 8. THE PERFECT FALSE GREEN: an empty perimeter is a FAILURE"
# ============================================================================
note "\"0 violations over 0 subjects\" is green and measures nothing"
mkdir -p "$TMP/empty-nodir"
expect_rc 1 "tree with no .github/workflows" --root "$TMP/empty-nodir"
mkdir -p "$TMP/empty-withdir/.github/workflows"
expect_rc 1 "EMPTY .github/workflows directory" --root "$TMP/empty-withdir"

# ============================================================================
echo
echo "=== 9. USAGE — an unknown flag is REFUSED, never ignored"
# ============================================================================
note "a silent \"--rot\" would return a green that does not measure what we meant"
expect_rc 2 "unknown flag" --rot "$ROOT"
expect_rc 2 "--root with no value" --root
expect_rc 2 "--root to a nonexistent directory" --root "$TMP/does-not-exist"

# ============================================================================
echo
echo "=== 10. THE WIRING EXISTS — the registration is auto-discovery"
# ============================================================================
# THE MOST EMBARRASSING HOLE A GUARD CAN HAVE: every case above measures the
# SCANNER in isolation via `--root` on faked trees. NONE measured its WIRING.
# Here the wiring is the `*.test.sh` glob in run-bash-tests.sh — that single
# pattern is the only reason this suite runs in CI at all. Narrow it, or comment
# it out, and the pinning guard leaves the pipeline with NO test going red.
ANALYZER="$TMP/glob.py"
cat > "$ANALYZER" <<'PYEOF'
"""Is the `*.test.sh` discovery glob live (uncommented) in run-bash-tests.sh?

0 = present and active, 1 = absent or commented out. Comments are stripped
FIRST: a grep for the substring would happily match a disabled line, which is
precisely the disarming gesture this case exists to catch.
"""
import re
import sys

src = open(sys.argv[1], encoding="utf-8").read()
live = "\n".join(ln for ln in src.splitlines() if not re.match(r"^\s*#", ln))
sys.exit(0 if re.search(r"-name\s+'\*\.test\.sh'", live) else 1)
PYEOF

if "$PY" "$ANALYZER" "$ROOT/core-scripts/run-bash-tests.sh"; then
  ok "run-bash-tests.sh still discovers *.test.sh (this suite runs in CI)"
else
  ko "run-bash-tests.sh no longer globs *.test.sh — this guard is UNWIRED"
fi

# NEGATIVE CONTROL: the same glob, commented out, must read as absent.
cat > "$TMP/runner-commented.sh" <<'FIX'
#!/usr/bin/env bash
SUITES=(); while IFS= read -r _line; do SUITES+=("$_line"); done < <(
  find . \
    -path ./.git -prune -o \
    # -name '*.test.sh' -type f -print | LC_ALL=C sort
    -name '*.spec.sh' -type f -print | LC_ALL=C sort
)
FIX
if "$PY" "$ANALYZER" "$TMP/runner-commented.sh"; then
  ko "a COMMENTED-OUT glob was counted — case 10 is inert"
else
  ok "a COMMENTED-OUT discovery glob does not count (disarming would be SEEN)"
fi

# And this suite must actually carry the suffix the glob looks for.
case "$(basename "${BASH_SOURCE[0]}")" in
  *.test.sh) ok "this suite carries the .test.sh suffix the glob matches" ;;
  *)         ko "this suite does NOT carry .test.sh — it would never be discovered" ;;
esac

# ----------------------------------------------------------------------------
# 10bis. THE SECOND LINK OF THE SAME CHAIN — the suite still POINTS AT the real
# tree, and still asserts the scanner returns 0 on it.
# ----------------------------------------------------------------------------
# THE WIRING IS A CHAIN OF TWO LINKS, AND ONLY THE FIRST WAS ASSERTED ABOVE.
# Link one — the `*.test.sh` glob — makes this suite RUN in CI. Link two is case
# 1: `expect_rc 0 … --root "$ROOT"`, the one and only place where a violation
# re-introduced into a REAL workflow of this repo turns something red. Assert the
# glob alone and the guard can still be disarmed in ONE GESTURE.
#
# MEASURED, on this repo, rather than argued:
#   * case 1's two lines commented out -> suite `43 passed / 0 failed`, rc=0.
#     GREEN. The pinning guard no longer looked at the repo's own workflows and
#     no test said so — the glob assertion above stayed PASS throughout.
#   * case 1bis cannot stand in for it: on a copy of the real .github/workflows
#     with one `actions/checkout@v4` injected, the scanner's summary counts came
#     back IDENTICAL to the clean run (`2 workflow(s) — 4 uses: site(s),
#     2 checkout(s), 2 pip line(s), 12 pinned requirement(s)`) while rc flipped
#     0 -> 1. 1bis asserts the five COUNTS and never the rc, so it stays green on
#     a real violation. It guards the perimeter, not the verdict.
# A guard that a single commented line silences guards nothing — the same failure
# family as the empty perimeter of case 8, applied to the WIRING instead of the
# subject set.
#
# DISCIPLINE, identical to the glob analyzer above: full-line comments stripped
# FIRST (a substring grep would happily match a disabled call — precisely the
# gesture being caught), then STRICT TOKEN EQUALITY. Two additions this second
# link needs and the first did not:
#   * BACKSLASH CONTINUATIONS ARE JOINED. The real call is written over two lines
#     (`expect_rc 0 "…" \` then `  --root "$ROOT"`), so a line-at-a-time reader
#     would never see it and this case would be VACUOUS while looking thorough.
#   * THE EXPECTED RC IS PART OF THE PATTERN. `expect_rc 0` is the assertion that
#     bites; an `expect_says` or a bare `bash "$SCANNER"` reads the tree without
#     ever failing on what it finds.
REALTREE="$TMP/realtree.py"
cat > "$REALTREE" <<'PYEOF'
"""Does <file> still assert rc=0 from the pinning scanner on the REAL tree?

0 = yes (the guard is wired to this repo), 1 = no (wired to nothing, or only to
faked trees).

THE NEEDLE IS ASSEMBLED FROM PIECES, never written out, and that is load-bearing
rather than cute: this analyzer's source is EMBEDDED IN THE SUITE IT ANALYSES, so
a spelled-out pattern would match itself and the case would pass forever — a
self-satisfying assertion is just a green with extra steps.
"""
import re
import sys

CALLER = "expect_" + "rc"
WANT_RC = "0"
FLAG = "--" + "root"
WANT_ROOT = '"$' + 'ROOT"'

src = open(sys.argv[1], encoding="utf-8").read()

# 1. Comments out FIRST — a disabled call must read as absent.
#
# HONEST BOUND, established by mutation rather than assumed: with this step
# REMOVED the suite still went 48/0. It is REDUNDANT here, because step 3 anchors
# on the FIRST token of the logical line and a full-line comment always makes that
# token `#`. It is kept for two reasons and neither is decoration — it mirrors the
# sibling glob analyzer above, where the check is NOT redundant, and it keeps this
# one correct if the anchor is ever loosened to "contains" (a two-line change that
# would silently re-open the hole). What actually carries the refusal of a
# commented-out call is the anchor, not this line.
lines = [ln for ln in src.splitlines() if not re.match(r"^\s*#", ln)]

# 2. Rejoin backslash continuations into LOGICAL lines.
logical, buf = [], ""
for ln in lines:
    stripped = ln.rstrip()
    if stripped.endswith(chr(92)):
        buf += stripped[:-1] + " "
        continue
    logical.append(buf + ln)
    buf = ""
if buf:
    logical.append(buf)

# 3. Strict token equality: the caller, the expected rc, and a root argument that
#    is EXACTLY the repo root. `--root "$TMP/faked"` and `--root "$ROOT/sub"` are
#    other trees and must not count.
for line in logical:
    toks = line.split()
    if len(toks) < 4 or toks[0] != CALLER or toks[1] != WANT_RC:
        continue
    if any(t == FLAG and i + 1 < len(toks) and toks[i + 1] == WANT_ROOT
           for i, t in enumerate(toks)):
        sys.exit(0)
sys.exit(1)
PYEOF

# POSITIVE: this very suite. It also proves the continuation joiner works — the
# only match in the file is spread over two lines.
if "$PY" "$REALTREE" "${BASH_SOURCE[0]}"; then
  ok "this suite still asserts rc=0 from the scanner on the REAL tree (\$ROOT)"
else
  ko "no live \"expect_rc 0 … --root \$ROOT\" left — the guard is UNWIRED from this repo"
fi

# NEGATIVE 1: the exact disarming gesture, measured above — the call commented
# out. Everything else in the suite still passes, so only this reads it.
cat > "$TMP/suite-commented.sh" <<'FIX'
#!/usr/bin/env bash
# ============================================================================
echo "=== 1. THE REAL TREE holds all four rules"
# ============================================================================
# DISABLED "the time it takes" to fix a workflow, and the time it takes became
# permanent:
# expect_rc 0 "real repo: everything pinned" \
#   --root "$ROOT"
expect_rc 1 "no root permissions:" --root "$TMP/r3-absent"
FIX
if "$PY" "$REALTREE" "$TMP/suite-commented.sh"; then
  ko "a COMMENTED-OUT real-tree call was counted — case 10bis is inert"
else
  ok "a COMMENTED-OUT real-tree call does not count (the disarming would be SEEN)"
fi

# NEGATIVE 2: the call kept but DIVERTED to a faked tree. This is the shape that
# looks busiest and measures least — every fixture case in this file is exactly
# such a call, which is why equality is on the token and not on the substring.
cat > "$TMP/suite-diverted.sh" <<'FIX'
#!/usr/bin/env bash
expect_rc 0 "real repo: everything pinned" \
  --root "$TMP/faked-tree"
FIX
if "$PY" "$REALTREE" "$TMP/suite-diverted.sh"; then
  ko "a call DIVERTED to a faked root was accepted — the equality is not tested"
else
  ok "a call DIVERTED to a faked root is not the real tree"
fi

# NEGATIVE 3: a SUBPATH of the root. Realistic drift in this repo — it ships
# template/starter-kit, whose own .github/ is a different perimeter — and it is
# the case a prefix match would wave through.
cat > "$TMP/suite-subpath.sh" <<'FIX'
#!/usr/bin/env bash
expect_rc 0 "real repo: everything pinned" \
  --root "$ROOT/template/starter-kit"
FIX
if "$PY" "$REALTREE" "$TMP/suite-subpath.sh"; then
  ko "a SUBPATH of the root was accepted as the root — a prefix match, not equality"
else
  ok "a SUBPATH of the root is a different perimeter, not the real tree"
fi

# NEGATIVE 4: the call present, on the real tree, but through a harness that
# NEVER FAILS on what it finds. `expect_says` greps the output; the scanner's
# verdict is discarded. Reading the tree is not asserting on it.
cat > "$TMP/suite-norc.sh" <<'FIX'
#!/usr/bin/env bash
expect_says "workflow(s)" "the scanner ran" --root "$ROOT"
real_out="$(bash "$SCANNER" --root "$ROOT" 2>&1)"
FIX
if "$PY" "$REALTREE" "$TMP/suite-norc.sh"; then
  ko "a call whose RC is never asserted was accepted — reading is not measuring"
else
  ok "a real-tree call with no rc assertion does not count as the wiring"
fi

# ============================================================================
echo
echo "=== 11. THE TWO WORKFLOWS' REQUIREMENT BLOCKS CANNOT DRIFT"
# ============================================================================
# The hash-pinned requirement block is duplicated in ci.yml and eval-nightly.yml
# because this repo has no package manifest by design and a shared requirements
# file was outside the approved scope. Duplication without a guard drifts: one
# file gets bumped, the other keeps installing the old artefacts, and the job
# that keeps the stale set is the one holding ANTHROPIC_API_KEY. So parity is
# asserted rather than hoped for.
PARITY="$TMP/parity.py"
cat > "$PARITY" <<'PYEOF'
"""Compare the inline pip requirement blocks of the two workflows.

0 = both present and byte-identical, 1 = missing or divergent.
"""
import re
import sys


def block(path):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"cat > \"\$REQ\" <<'EOF'\n(.*?)\n\s*EOF", src, re.S)
    return m.group(1) if m else None


a = block(sys.argv[1])
b = block(sys.argv[2])
if a is None or b is None:
    print("requirement block not found in %s" % ("ci.yml" if a is None else "eval-nightly.yml"))
    sys.exit(1)
if a != b:
    print("requirement blocks DIVERGE")
    sys.exit(1)
# A block of one line would be a suspiciously thin closure.
if len([ln for ln in a.splitlines() if "==" in ln]) < 5:
    print("requirement block has fewer than 5 pinned lines — closure looks incomplete")
    sys.exit(1)
sys.exit(0)
PYEOF

if "$PY" "$PARITY" "$ROOT/.github/workflows/ci.yml" "$ROOT/.github/workflows/eval-nightly.yml"; then
  ok "ci.yml and eval-nightly.yml pin the SAME closure, >= 5 requirements"
else
  ko "the two workflows' requirement blocks are missing or have DRIFTED"
fi

# ============================================================================
echo
echo "=== 12. THE WINDOWS LEG IS PINNED IN THE MATRIX (plan 5bis, C2/C5)"
# ============================================================================
# L-00000145: a fix nothing pins gets silently undone. The Windows leg is a
# `windows-latest` entry in ci.yml's build matrix; delete it and the
# skipUnless(WINDOWS, …) probes stop running in CI with nothing going red. So
# its PRESENCE is asserted — and asserted on the file with COMMENTS STRIPPED,
# because this repo cites in comment exactly what it avoids (case 7), so a bare
# grep for "windows-latest" would match a line that only mentions it. That is
# the hardened negative control below (C5, iteration 2).
MATRIX="$TMP/matrix.py"
cat > "$MATRIX" <<'PYEOF'
"""Is `windows-latest` a LIVE token in ci.yml (not inside a YAML comment)?

0 = present outside comments, 1 = absent or only cited in a comment. Every
comment — full-line AND inline `#…` — is stripped FIRST. No os:/matrix line in
this workflow carries a '#' inside a quoted string, so cutting from the first
'#' to end-of-line is a sound YAML-comment strip here.
"""
import re
import sys

live = "\n".join(re.sub(r"#.*$", "", ln) for ln in open(sys.argv[1], encoding="utf-8").read().splitlines())
sys.exit(0 if re.search(r"\bwindows-latest\b", live) else 1)
PYEOF

if "$PY" "$MATRIX" "$ROOT/.github/workflows/ci.yml"; then
  ok "ci.yml pins windows-latest in a LIVE matrix line (the Windows CI leg exists)"
else
  ko "ci.yml no longer carries a live windows-latest matrix entry — the Windows leg is GONE"
fi

# NEGATIVE CONTROL, hardened (C5 it.2): windows-latest present ONLY in a
# comment, with no live matrix entry, MUST read as absent — the exact false
# positive case 7 documents.
cat > "$TMP/ci-windows-commented.yml" <<'FIX'
jobs:
  tests:
    # windows-latest is deliberately avoided here for now.
    runs-on: ubuntu-latest # not windows-latest yet
    strategy:
      matrix:
        os: [ubuntu-latest]
FIX
if "$PY" "$MATRIX" "$TMP/ci-windows-commented.yml"; then
  ko "windows-latest cited only in a COMMENT was counted — case 12 is inert"
else
  ok "windows-latest in a COMMENT does not count (a disarming edit would be SEEN)"
fi

# POSITIVE CONTROL: a live matrix entry IS detected — proves the analyzer reads
# presence, not merely the real file by luck (L-00000057).
cat > "$TMP/ci-windows-live.yml" <<'FIX'
jobs:
  tests:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
FIX
if "$PY" "$MATRIX" "$TMP/ci-windows-live.yml"; then
  ok "a live [ubuntu-latest, windows-latest] matrix reads as present"
else
  ko "a live windows-latest matrix entry was missed — the analyzer is blind"
fi

# ============================================================================
echo
echo "=== 13. R2d — a \`-r <file>\` is FOLLOWED (T-00001183)"
# ============================================================================
# Before T-00001183, `-r` was skipped as an option and R2c read only the INLINE
# lines of a workflow: a requirement file named by `-r` was never opened, so the
# header's "every requirement line carries a full hash" was false for it
# (measured). The job `adoptant` installs semgrep from such a file, so the rule
# now follows it. One fixture per refusal, each against a positive twin.
H64_A="37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c"
H64_B="f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12"
# req_fixture <name> <requirement flag> — a workflow whose ONLY pip line installs
# `<flag>` (e.g. `-r sec/gardes.txt`) under the hardened flags; prints the
# fixture root. The requirement file itself is written by the caller.
req_fixture() {
  local d root
  d="$(fixture "$1")"
  root="$TMP/$1"
  printf '%s      - run: python -m pip install --require-hashes --only-binary :all: --disable-pip-version-check %s\n' \
    "$HDR" "$2" > "$d/a.yml"
  mkdir -p "$root/sec"
  printf '%s' "$root"
}

note "positive: a comment, a marker-gated line, a backslash continuation — all valid"
root="$(req_fixture r2d-ok '-r sec/gardes.txt')"
{
  printf '# a full comment line is not a requirement\n'
  printf 'pytest==9.1.1 --hash=sha256:%s\n' "$H64_A"
  printf 'colorama==0.4.6; sys_platform == "win32" --hash=sha256:%s  # trailing comment\n' "$H64_B"
  printf 'iniconfig==2.3.0 \\\n'
  printf '    --hash=sha256:%s\n' "$H64_B"
} > "$root/sec/gardes.txt"
expect_rc 0 "-r of a hash-pinned file (comment, marker, continuation) passes" --root "$root"
expect_says "1 requirement file(s) followed" "the file was OPENED, not skipped (anti green-and-empty)" \
  --root "$root"
expect_says "3 pinned requirement(s)" "its 3 LOGICAL requirements are counted (the continuation is one)" \
  --root "$root"

note "mutant 1: --hash removed from ONE requirement of the file"
root="$(req_fixture r2d-nohash '-r sec/gardes.txt')"
printf 'pytest==9.1.1 --hash=sha256:%s\niniconfig==2.3.0\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "a requirement without --hash in the -r file" --root "$root"
expect_says "sec/gardes.txt:2" "the message names the FILE and its line, not the workflow" --root "$root"

note "mutant 2: >= instead of =="
root="$(req_fixture r2d-range '-r sec/gardes.txt')"
printf 'pytest>=9.1.1 --hash=sha256:%s\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "pytest>=9.1.1 in the -r file" --root "$root"
expect_says "is NOT ==-pinned" "the range is named" --root "$root"

note "mutant 3: a hash truncated to 63 hex"
root="$(req_fixture r2d-63 '-r sec/gardes.txt')"
printf 'pytest==9.1.1 --hash=sha256:%s\n' "${H64_A%?}" > "$root/sec/gardes.txt"
expect_rc 1 "a 63-hex hash in the -r file" --root "$root"
expect_says "NO valid --hash=sha256:<64 hex>" "the truncated hash is named" --root "$root"

note "mutant 4: an --index-url option line added"
root="$(req_fixture r2d-index '-r sec/gardes.txt')"
printf -- '--index-url https://example.invalid/simple\npytest==9.1.1 --hash=sha256:%s\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "--index-url line in the -r file" --root "$root"
expect_says "option line \"--index-url\"" "the option line is named" --root "$root"

note "mutant 5: an EMPTY file (comments only)"
root="$(req_fixture r2d-empty '-r sec/gardes.txt')"
printf '# nothing pinned here\n\n' > "$root/sec/gardes.txt"
expect_rc 1 "-r of a file holding no requirement" --root "$root"
expect_says "holds NO requirement" "the emptiness is named" --root "$root"

note "the file named by -r does not exist"
root="$(req_fixture r2d-absent '-r sec/absent.txt')"
expect_rc 1 "-r to a file absent from the repository" --root "$root"
expect_says "requirement file NOT FOUND" "the absence is named" --root "$root"

note "-r of a URL, -r of an absolute path, a NESTED -r inside the file"
# The MESSAGE is asserted, not only the rc: without its own refusal a URL or an
# absolute path would still go red as "NOT FOUND" under the root, and a mutant
# deleting the refusal would survive on the rc alone (measured).
root="$(req_fixture r2d-url '-r https://example.invalid/reqs.txt')"
expect_rc 1 "-r https://… (a URL)" --root "$root"
expect_says "is a URL" "the URL is refused AS a URL" --root "$root"
root="$(req_fixture r2d-abs '-r /etc/reqs.txt')"
expect_rc 1 "-r /etc/reqs.txt (an absolute path)" --root "$root"
expect_says "is an ABSOLUTE path" "the absolute path is refused AS such" --root "$root"
root="$(req_fixture r2d-nested '-r sec/gardes.txt')"
printf -- '-r other.txt\npytest==9.1.1 --hash=sha256:%s\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "a nested -r inside the followed file" --root "$root"

note "the GLUED form -r<file> and --requirement=<file> are followed too (pip accepts both)"
root="$(req_fixture r2d-glued '-rsec/gardes.txt')"
printf 'pytest>=9.1.1 --hash=sha256:%s\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "-rsec/gardes.txt (glued) is followed: its range is caught" --root "$root"
root="$(req_fixture r2d-eq '--requirement=sec/gardes.txt')"
printf 'pytest>=9.1.1 --hash=sha256:%s\n' "$H64_A" > "$root/sec/gardes.txt"
expect_rc 1 "--requirement=sec/gardes.txt is followed: its range is caught" --root "$root"

note "a shell expansion (-r \"\$REQ\") is NOT followed — the inline block is R2c's (bound 9)"
note "positive twin: case 3quinquies above (its -r \"\$REQ\" stays green)"

echo
echo "================================================================"
echo "check-workflow-pins: $pass passed / $fail failed"
[ "$fail" -eq 0 ] || exit 1
echo "Workflow pinning: guard green, and red on every one of its fixtures."
