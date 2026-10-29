#!/usr/bin/env bash
# Suite for the "ecosystem NOT covered in v1 is NAMED, never a silent GO" shard
# of sca-scan.sh (T-00000488). Auto-discovered by core-scripts/run-bash-tests.sh.
#
# What it proves: on every ENTRY that reaches a detection — the bare form, the
# single-module form, the --all-modules loop AND its no-module branch, and the
# root-non-module branch of --all-modules — a manifest of Go/Rust/.NET/PHP/Ruby
# present AT THE ROOT LOOKED AT is NAMED (`<eco>: ecosystem not covered in v1`),
# marked `degraded`, announced as `COVERAGE DEGRADED`, and NEVER read as scanned
# and NEVER a hard block. The bound is pinned too: a manifest in a sub-folder
# that is not a discovered module is NOT named (c3), lifted by T-00000312.
#
# ZERO network, ZERO real scanner needed: package.json makes scanned=1 by
# presence alone (sca-scan.sh:397-399), so npm/socket/trivy are all OPTIONAL —
# they only ever DEGRADE, which does not gate. The scan.sca argv is captured by
# a STUB emit-event.sh (precedent: sca-socket-timeout.test.sh:242-244).
#
# ASSERTION DISCIPLINE (pieges 1-2, measured):
#   - Never assert a substring of the JOINED render of .degraded. `paste -sd '; '`
#     has a CYCLIC delimiter (a\nb\nc => "a;b c") and the npm block writes to
#     .degraded BEFORE name_uncovered, so `go:` is never the first line on a
#     package.json fixture. We assert on individual LINES of the file
#     (grep -Fxq on "$DEG") and on SEPARATE presence of the pieces in the output.
#     Exception (c4)/(b2): the ROOT .degraded carries ONLY our line (no scanner
#     runs on that path), so its joined render is stable and asserted whole.
#   - grep -c on "$DEG" is GUARDED, and the guard has TWO forms:
#       PRESENCE cells (a,a2,b,b2,c,c4): [ -f "$DEG" ] && [ "$(grep -c ..)" -eq N ]
#         — the `[ ! -f ] ||` form here would be fail-OPEN.
#       ABSENCE  cells (c2,c3,d,d2):     [ ! -f "$DEG" ] || [ "$(grep -c ..)" -eq 0 ]
#         — an absent file is a valid way to have zero lines.
#   - Every rc is captured DIRECTLY (rc=$? right after the command), never behind
#     a pipe (L-00000354/L-00000349). Every literal/path search is -F.
#
# MUTATION TABLE — each COUNTED against the fixtures it touches, played red then
# reverted BY Edit before commit (S5). bash-parse-oldest.test.sh is a live sensor.
#   1. empty name_uncovered body        => (a)(a2)(b)(b2)(c) RED
#   2. scanned=1 inside name_uncovered   => (b) RED (a false GO)
#   3. drop announce_degraded from the scanned=0 branch (:694) => (b) AND (d2) RED
#   4. drop the 3 lines of S1e (no-module branch :197-199)     => (b2) RED, (a2) GREEN
#   5. drop the 3 lines of S1e-bis (root-non-module :215-217)  => (c4) RED under
#      --all-modules; (a)(a2)(b2) UNCHANGED (proves a distinct fourth site)
#   6. -maxdepth 4 in the dotnet find                          => (c2) RED
#   7. -maxdepth 2 in the dotnet find                          => (c)  RED
#   8. `$f` instead of `$rel` in the dotnet writes             => (c)  RED
#   9. drop the five keys from the emit_sca map                => (a)(b)(c)(c2)(c3)(d) RED
#  10. drop the `sanitize_display` call on `rel`               => (e) RED, (e2) GREEN
#      (the pair proves the filter bites a HOSTILE name without touching a
#       legitimate one — a filter nothing distinguishes proves nothing)
#  11. sanitize_display back to a blacklist `tr -d '\000-\037\177'` => (e) RED on
#      the forgery assertions, GREEN on the ESC one — which is precisely how the
#      first fix of this lot passed the class-1 review once and failed it twice
#  12. whitelist `\r` — `tr -c 'A-Za-z0-9._/ \r-' '?'`          => (e) RED
#      Named by the THIRD class-1 pass, which measured it GREEN against the
#      first version of (e): the ESC-specific assertion missed CR, and a name
#      like `A\rWIPED go OK.csproj` overwrote the banner from column 0. The
#      assertion now bounds the CLASS ([[:cntrl:]]), not the sampled byte.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
# REFUSE a degenerate root: an empty $TMP under `set -u` would make every mkdir
# and cd land in the real tree (same class as `git -C ""`). Non-empty, a real
# directory, under the system temp, never the current tree, or stop here.
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# A fixture root OUTSIDE any repo: sca-scan.sh falls back to `pwd` for ROOT, so
# ROOT == $R and the stub's CLAUDE_PROJECT_DIR (=$ROOT) is $R too. make_root
# mirrors sca-module-gate.test.sh:26-30 (parity with the suite that exercises
# --all-modules) plus the emit-event.sh stub (sca-socket-timeout.test.sh:242-244),
# written by printf, NEVER a heredoc (L-00000197).
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports" "$r/.claude/hooks"
  cp "$HERE/module_discovery.py" "$HERE/protected_module.py" "$r/.agents/security/"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "%s\n" "$@" > "$CLAUDE_PROJECT_DIR/emit-event.argv"' \
    > "$r/.claude/hooks/emit-event.sh"
  chmod +x "$r/.claude/hooks/emit-event.sh"
  echo "$r"
}

npm_json() { printf '{"name":"x","version":"1.0.0"}' > "$1"; }

# ---------------------------------------------------------------------------
echo "=== (a) MIXED, bare form — package.json + go.mod named, still GO"
R="$(make_root a)"
npm_json "$R/package.json"
printf 'module example.com/x\n' > "$R/go.mod"
printf 'package main\n' > "$R/main.go"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(a) rc=0" || ko "(a) rc=$rc, expected 0 — output: $OUT"
grep -Fq 'SCA GATE (effective, waivers applied): GO' <<<"$OUT" \
  && ok "(a) verdict is GO" || ko "(a) not a GO"
grep -Fxq 'go: ecosystem not covered in v1 (go.mod present)' "$DEG" \
  && ok "(a) go line present in .degraded" || ko "(a) go line missing from .degraded"
{ [ -f "$DEG" ] && [ "$(grep -c 'ecosystem not covered' "$DEG")" -eq 1 ]; } \
  && ok "(a) exactly one not-covered line" || ko "(a) not-covered line count != 1"
[ "$(grep -c '^  COVERAGE DEGRADED:' <<<"$OUT")" -eq 1 ] \
  && ok "(a) one COVERAGE DEGRADED announce" || ko "(a) COVERAGE DEGRADED count != 1"
# C2: the two pieces asserted SEPARATELY, never as one contiguous substring.
grep -Fq '  COVERAGE DEGRADED:' <<<"$OUT" \
  && ok "(a) COVERAGE DEGRADED marker in output" || ko "(a) no COVERAGE DEGRADED marker"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(a) go reason in output" || ko "(a) go reason absent from output"
grep -Fq '[go] go.mod present' <<<"$OUT" \
  && ok "(a) [go] log line printed" || ko "(a) [go] log line missing"
[ "$(grep -c 'go\.mod' <<<"$OUT")" -ge 1 ] \
  && ok "(a) go.mod named at least once (was 0 before the lot)" || ko "(a) go.mod named 0 times"
grep -Fq '"go":"degraded"' "$ARGV" \
  && ok "(a) scan.sca map carries go:degraded" || ko "(a) go not degraded in scan.sca map"
! grep -Fq '"go":"scanned"' "$ARGV" \
  && ok "(a) go never reads as scanned in the map" || ko "(a) go:scanned in the map — false coverage"
# L-00000353 (C2 form): remove the TOKEN, not the line.
grep -Fq '(NOT scanned)' <<<"$OUT" \
  && ok "(a) the [go] line says (NOT scanned)" || ko "(a) (NOT scanned) missing"
{ grep -E '^  \[go\]' <<<"$OUT" | sed 's/NOT scanned//g' | grep -qi 'scanned'; } \
  && ko "(a) a [go] line still reads as scanned once 'NOT scanned' is removed" \
  || ok "(a) no [go] line reads as scanned"
grep -qi 'scanned' "$DEG" \
  && ko "(a) .degraded contains the word scanned" || ok "(a) .degraded never says scanned"

# ---------------------------------------------------------------------------
echo "=== (a2) MIXED under --all-modules — the /audit LOOP path"
R="$(make_root a2)"
npm_json "$R/package.json"
printf 'module example.com/x\n' > "$R/go.mod"
printf 'package main\n' > "$R/main.go"
DEG="$R/.agents/state/local/sca-reports/.degraded"
SUM="$R/.agents/state/local/sca-reports/modules/summary.json"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" --all-modules 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(a2) rc=0" || ko "(a2) rc=$rc, expected 0 — output: $OUT"
grep -Fq 'SCA GATE all-modules (effective, waivers applied): GO' <<<"$OUT" \
  && ok "(a2) all-modules verdict is GO" || ko "(a2) not a GO"
grep -Fq '  COVERAGE DEGRADED:' <<<"$OUT" \
  && ok "(a2) COVERAGE DEGRADED marker in output" || ko "(a2) no COVERAGE DEGRADED marker"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(a2) go reason in output" || ko "(a2) go reason absent from output"
[ "$(grep -c '^  COVERAGE DEGRADED:' <<<"$OUT")" -eq 1 ] \
  && ok "(a2) one COVERAGE DEGRADED announce (root module only)" || ko "(a2) announce count != 1"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' "$SUM" \
  && ok "(a2) summary.json carries the go line (surface audit_report.py reads)" \
  || ko "(a2) go line missing from summary.json"

# ---------------------------------------------------------------------------
echo "=== (b) PURE-GO, bare form — control: named, rc=2, never a GO"
R="$(make_root b)"
printf 'module example.com/x\n' > "$R/go.mod"
printf 'package main\n' > "$R/main.go"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(b) rc=2" || ko "(b) rc=$rc, expected 2 — output: $OUT"
grep -Fq 'SCA: no known ecosystem detected.' <<<"$OUT" \
  && ok "(b) says no known ecosystem detected" || ko "(b) no-ecosystem message missing"
grep -Fq 'COVERAGE DEGRADED:' <<<"$OUT" \
  && ok "(b) COVERAGE DEGRADED marker in output" || ko "(b) no COVERAGE DEGRADED marker"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(b) go reason in output" || ko "(b) go reason absent from output"
# ORDER: the announce precedes the no-ecosystem line.
n_deg="$(grep -n 'COVERAGE DEGRADED:' <<<"$OUT" | head -1 | cut -d: -f1)"
n_sca="$(grep -n 'SCA: no known ecosystem detected.' <<<"$OUT" | head -1 | cut -d: -f1)"
{ [ -n "$n_deg" ] && [ -n "$n_sca" ] && [ "$n_deg" -lt "$n_sca" ]; } \
  && ok "(b) COVERAGE DEGRADED printed before the no-ecosystem line" \
  || ko "(b) announce not ordered before no-ecosystem line ($n_deg vs $n_sca)"
! grep -q 'SCA GATE' <<<"$OUT" \
  && ok "(b) no SCA GATE line on the no-ecosystem path" || ko "(b) an SCA GATE line leaked"
grep -Fxq 'go: ecosystem not covered in v1 (go.mod present)' "$DEG" \
  && ok "(b) go line present in .degraded" || ko "(b) go line missing from .degraded"
grep -Fq '"go":"degraded"' "$ARGV" \
  && ok "(b) scan.sca map carries go:degraded" || ko "(b) go not degraded in scan.sca map"

# ---------------------------------------------------------------------------
echo "=== (b2) PURE-GO under --all-modules — the /audit NO-MODULE branch"
R="$(make_root b2)"
printf 'module example.com/x\n' > "$R/go.mod"
printf 'package main\n' > "$R/main.go"
DEG="$R/.agents/state/local/sca-reports/.degraded"
SUM="$R/.agents/state/local/sca-reports/modules/summary.json"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" --all-modules 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(b2) rc=2" || ko "(b2) rc=$rc, expected 2 — output: $OUT"
grep -Fq 'SCA: no known ecosystem detected in any module.' <<<"$OUT" \
  && ok "(b2) says no ecosystem in any module" || ko "(b2) no-module message missing"
grep -Fq 'COVERAGE DEGRADED:' <<<"$OUT" \
  && ok "(b2) COVERAGE DEGRADED marker in output" || ko "(b2) no COVERAGE DEGRADED marker"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(b2) go reason in output" || ko "(b2) go reason absent from output"
n_deg="$(grep -n 'COVERAGE DEGRADED:' <<<"$OUT" | head -1 | cut -d: -f1)"
n_sca="$(grep -n 'SCA: no known ecosystem detected in any module.' <<<"$OUT" | head -1 | cut -d: -f1)"
{ [ -n "$n_deg" ] && [ -n "$n_sca" ] && [ "$n_deg" -lt "$n_sca" ]; } \
  && ok "(b2) announce ordered before the no-module line" \
  || ko "(b2) announce not ordered ($n_deg vs $n_sca)"
! grep -q 'SCA GATE' <<<"$OUT" \
  && ok "(b2) no SCA GATE line on the no-module path" || ko "(b2) an SCA GATE line leaked"
grep -Fxq 'go: ecosystem not covered in v1 (go.mod present)' "$DEG" \
  && ok "(b2) go line present in .degraded" || ko "(b2) go line missing from .degraded"
{ [ -f "$DEG" ] && [ "$(grep -c '' "$DEG")" -eq 1 ]; } \
  && ok "(b2) .degraded has exactly ONE line — no scanner ran (proves S1e did not wake ecosystem blocks)" \
  || ko "(b2) .degraded line count != 1"
# BOUND: the no-module branch writes no summary.json — stdout + .degraded carry
# the announcement, the HTML Gaps list cannot.
[ ! -f "$SUM" ] \
  && ok "(b2) no summary.json on the no-module branch (bound pinned)" \
  || ko "(b2) a summary.json was written — bound broken"

# ---------------------------------------------------------------------------
echo "=== (c) FIVE manifests, bare form — all named, still GO"
R="$(make_root c)"
npm_json "$R/package.json"
printf 'module example.com/x\n' > "$R/go.mod"
printf '[package]\nname = "x"\n' > "$R/Cargo.toml"
printf '{"name":"x/y"}' > "$R/composer.json"
printf 'GEM\n' > "$R/Gemfile.lock"
mkdir -p "$R/src/App"
printf '<Project Sdk="Microsoft.NET.Sdk"></Project>\n' > "$R/src/App/App.csproj"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(c) rc=0" || ko "(c) rc=$rc, expected 0 — output: $OUT"
{ [ -f "$DEG" ] && [ "$(grep -c 'ecosystem not covered in v1' "$DEG")" -eq 5 ]; } \
  && ok "(c) five not-covered lines" || ko "(c) not-covered line count != 5"
for lit in \
  'go: ecosystem not covered in v1 (go.mod present)' \
  'rust: ecosystem not covered in v1 (Cargo.toml present)' \
  'php: ecosystem not covered in v1 (composer.json present)' \
  'ruby: ecosystem not covered in v1 (Gemfile.lock present)' \
  'dotnet: ecosystem not covered in v1 (src/App/App.csproj present)'; do
  grep -Fxq "$lit" "$DEG" && ok "(c) line present: $lit" || ko "(c) line MISSING: $lit"
done
! grep -Fq "$R" "$DEG" \
  && ok "(c) no absolute fixture path leaked into .degraded (rel, not f)" \
  || ko "(c) an absolute path leaked into .degraded"
for key in go rust php ruby dotnet; do
  grep -Fq "\"$key\":\"degraded\"" "$ARGV" \
    && ok "(c) map: $key degraded" || ko "(c) map: $key not degraded"
done

# ---------------------------------------------------------------------------
echo "=== (c2) -maxdepth bound — a csproj at depth 4 is NOT named"
R="$(make_root c2)"
npm_json "$R/package.json"
mkdir -p "$R/a/b/c"
printf '<Project Sdk="Microsoft.NET.Sdk"></Project>\n' > "$R/a/b/c/Deep.csproj"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
{ [ ! -f "$DEG" ] || [ "$(grep -c '^dotnet:' "$DEG")" -eq 0 ]; } \
  && ok "(c2) a depth-4 csproj is not named (maxdepth 3 bound)" \
  || ko "(c2) a depth-4 csproj was named — bound broken"
grep -Fq '"dotnet":"skipped"' "$ARGV" \
  && ok "(c2) map: dotnet skipped" || ko "(c2) dotnet not skipped in map"

# ---------------------------------------------------------------------------
echo "=== (c3) BOUND of the lot — a sub-module go.mod is NOT named (T-00000312)"
R="$(make_root c3)"
npm_json "$R/package.json"
mkdir -p "$R/api"
printf 'module example.com/api\n' > "$R/api/go.mod"
printf 'package main\n' > "$R/api/main.go"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(c3) rc=0" || ko "(c3) rc=$rc, expected 0 — output: $OUT"
# BOUND pinned on purpose — lifted by T-00000312 (couture C1: Go family in
# module_discovery.py); amend this cell there.
{ [ ! -f "$DEG" ] || [ "$(grep -c '^go:' "$DEG")" -eq 0 ]; } \
  && ok "(c3) KNOWN GAP pinned — sub-module go.mod NOT named (T-00000312 lifts it)" \
  || ko "(c3) a sub-module go.mod was named — the bound moved unexpectedly"
[ "$(grep -c 'go\.mod' <<<"$OUT")" -eq 0 ] \
  && ok "(c3) go.mod named 0 times on the sub-module bound" || ko "(c3) go.mod leaked into output"
grep -Fq '"go":"skipped"' "$ARGV" \
  && ok "(c3) map: go skipped (sub-module not reached)" || ko "(c3) go not skipped in map"

# ---------------------------------------------------------------------------
echo "=== (c4) ROOT-NON-MODULE — go.mod at root beside web/package.json (S1e-bis)"
R="$(make_root c4)"
printf 'module example.com/x\n' > "$R/go.mod"
printf 'package main\n' > "$R/main.go"
mkdir -p "$R/web"
npm_json "$R/web/package.json"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
# bare form (falls back to --all-modules because web/ is a non-root module)
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
grep -Fxq 'go: ecosystem not covered in v1 (go.mod present)' "$DEG" \
  && ok "(c4/bare) root go line present in .degraded" || ko "(c4/bare) root go line missing"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(c4/bare) go reason in output" || ko "(c4/bare) go reason absent"
# The ROOT .degraded carries ONLY the go line (no scanner runs on that path), so
# its joined render is stable and asserted whole.
grep -Fxq '  COVERAGE DEGRADED: go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(c4/bare) exact root announce line" || ko "(c4/bare) root announce line not exact"
# --all-modules form (the /audit entry) — same root-non-module branch
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" --all-modules 2>&1)"; rc=$?
grep -Fxq 'go: ecosystem not covered in v1 (go.mod present)' "$DEG" \
  && ok "(c4/all) root go line present in .degraded" || ko "(c4/all) root go line missing"
grep -Fq 'go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(c4/all) go reason in output" || ko "(c4/all) go reason absent"
grep -Fxq '  COVERAGE DEGRADED: go: ecosystem not covered in v1 (go.mod present)' <<<"$OUT" \
  && ok "(c4/all) exact root announce line" || ko "(c4/all) root announce line not exact"
# KNOWN INCOHERENCE (T-00000488): the scan.sca map belongs to the LAST module
# scanned, not to the root announce — a consumer reading only the event sees
# go:skipped while the console names go.mod. Lifted by T-00000312 (couture C1:
# the root becomes a real module).
grep -Fq '"go":"skipped"' "$ARGV" \
  && ok "(c4) map says go:skipped while the console named go.mod — KNOWN INCOHERENCE, lifted by T-00000312" \
  || ko "(c4) scan.sca map did not read go:skipped — the incoherence changed shape"

# ---------------------------------------------------------------------------
echo "=== (d) NEGATIVE — package.json alone names nothing"
R="$(make_root d)"
npm_json "$R/package.json"
DEG="$R/.agents/state/local/sca-reports/.degraded"
ARGV="$R/emit-event.argv"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
{ [ ! -f "$DEG" ] || [ "$(grep -c 'ecosystem not covered' "$DEG")" -eq 0 ]; } \
  && ok "(d) no not-covered line in .degraded" || ko "(d) a not-covered line appeared"
[ "$(grep -c 'ecosystem not covered' <<<"$OUT")" -eq 0 ] \
  && ok "(d) no not-covered line in output" || ko "(d) a not-covered line leaked to output"
for key in go rust php ruby dotnet; do
  grep -Fq "\"$key\":\"skipped\"" "$ARGV" \
    && ok "(d) map: $key skipped" || ko "(d) map: $key not skipped"
done

# ---------------------------------------------------------------------------
echo "=== (d2) EMPTY — S1d announces .degraded on the rc=2 path, unconditional"
R="$(make_root d2)"
DEG="$R/.agents/state/local/sca-reports/.degraded"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(d2) rc=2" || ko "(d2) rc=$rc, expected 2 — output: $OUT"
grep -Fq 'SCA: no known ecosystem detected.' <<<"$OUT" \
  && ok "(d2) no-ecosystem message present" || ko "(d2) no-ecosystem message missing"
[ "$(grep -c 'not covered' <<<"$OUT")" -eq 0 ] \
  && ok "(d2) no not-covered line in output" || ko "(d2) a not-covered line leaked"
{ [ ! -f "$DEG" ] || [ "$(grep -c 'not covered' "$DEG")" -eq 0 ]; } \
  && ok "(d2) no not-covered line in .degraded" || ko "(d2) a not-covered line in .degraded"
# premise: the trivy block must have written SOMETHING, or the announce contract
# is untestable on this machine.
[ -s "$DEG" ] \
  || ko "(d2) premise broken: .degraded empty — the trivy block wrote nothing, announce contract untestable"
# contract: the console announce mirrors .degraded on the rc=2 path — one branch;
# the environment picks the reason TEXT (trivy absent|present), not the branch.
if [ -s "$DEG" ]; then
  grep -Fq "COVERAGE DEGRADED: $(paste -sd '; ' "$DEG")" <<<"$OUT" \
    && ok "(d2) announce mirrors .degraded on the rc=2 path [trivy absent|present]" \
    || ko "(d2) announce does not mirror .degraded"
fi

# ---------------------------------------------------------------------------
# (e)/(e2) SANITIZER — the only cells that treat the file NAME as an attacker.
# Not a hypothetical: the class-1 review of this very lot found the first fix
# (strip control bytes) closed the terminal-erasure face and left the FORGERY
# face open. The reason lines are rendered JOINED by `paste -sd '; '`, so `;`
# `(` `)` `:` are the GRAMMAR the reader parses, and a client `.csproj` can
# carry them. Assertions are on the .degraded LINE (never on the joined render,
# whose delimiter is cyclic) plus one on the absence of the forged entry in the
# rendered output — that second one is where the forgery would actually show.
echo "=== (e) HOSTILE NAME — a .csproj cannot forge an entry nor erase a line"
R="$(make_root e)"
mkdir -p "$R/src/App"
# The name carries BOTH erasure primitives, deliberately: ESC (cursor-up +
# erase-line) AND a bare CR (overwrite from column 0). One byte is not the
# class — the third class-1 pass measured that an ESC-only fixture kept this
# suite at 83/0 while a `\r` whitelist reopened the banner overwrite.
HOSTILE="$(printf 'A\rW\033[1AX); go: scanned, 0 CVE (go.mod present) (z.csproj')"
: > "$R/src/App/$HOSTILE"
DEG="$R/.agents/state/local/sca-reports/.degraded"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(e) rc=2 (dotnet-only repo: no known ecosystem)" \
  || ko "(e) rc=$rc, expected 2 — output: $OUT"
# EXACT sanitized form: every char outside [A-Za-z0-9._/ -] became `?`.
EXPECT_E='dotnet: ecosystem not covered in v1 (src/App/A?W??1AX?? go? scanned? 0 CVE ?go.mod present? ?z.csproj present)'
[ -f "$DEG" ] && grep -Fqx "$EXPECT_E" "$DEG" \
  && ok "(e) .degraded carries the EXACT sanitized line" \
  || ko "(e) sanitized line absent — got: $([ -f "$DEG" ] && grep -F 'dotnet:' "$DEG")"
# structural: the entry SEPARATOR can never appear inside an entry.
[ "$(grep -F 'dotnet:' "$DEG" | tr -cd ';' | wc -c | tr -d ' ')" -eq 0 ] \
  && ok "(e) no ';' inside the dotnet entry (separator cannot be forged)" \
  || ko "(e) a ';' survived inside the dotnet entry — an entry can be forged"
# the forged claim must not appear ANYWHERE in what the reader sees.
[ "$(grep -c 'go: scanned' <<<"$OUT")" -eq 0 ] \
  && ok "(e) no forged 'go: scanned' entry in the rendered output" \
  || ko "(e) a forged go entry reached the reader: $(grep 'COVERAGE DEGRADED' <<<"$OUT")"
# terminal-erasure face (the original CWE-150). Asserts on the CLASS, not on the
# one byte the fixture happens to carry: an ESC-specific `grep -c $'\033'` let a
# mutation that whitelists `\r` keep this suite at 83/0 while a name like
# `A\rWIPED go OK.csproj` overwrote the COVERAGE DEGRADED banner from column 0 —
# the very face this cell exists to guard, reopened under a green suite. A guard
# must bound the class it claims, not the sample it was written against.
[ "$(LC_ALL=C grep -c '[[:cntrl:]]' <<<"$OUT")" -eq 0 ] \
  && ok "(e) zero control byte in output (class, not just ESC)" \
  || ko "(e) a control byte reached stdout"

echo "=== (e2) NON-REGRESSION — a legitimate name is passed through untouched"
R="$(make_root e2)"
mkdir -p "$R/src/My-App_v2.1"
: > "$R/src/My-App_v2.1/Sub.csproj"
DEG="$R/.agents/state/local/sca-reports/.degraded"
OUT="$(cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(e2) rc=2" || ko "(e2) rc=$rc, expected 2 — output: $OUT"
EXPECT_E2='dotnet: ecosystem not covered in v1 (src/My-App_v2.1/Sub.csproj present)'
[ -f "$DEG" ] && grep -Fqx "$EXPECT_E2" "$DEG" \
  && ok "(e2) dots, dashes, underscores and slashes pass through unchanged" \
  || ko "(e2) a legitimate name was mangled — got: $([ -f "$DEG" ] && grep -F 'dotnet:' "$DEG")"
[ "$(grep -F 'dotnet:' "$DEG" | tr -cd '?' | wc -c | tr -d ' ')" -eq 0 ] \
  && ok "(e2) no '?' introduced on a clean name" || ko "(e2) the whitelist mangled a clean name"

# ---------------------------------------------------------------------------
echo
echo "================================================================"
echo "sca-uncovered: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "An uncovered ecosystem is NAMED on every entry that reaches detection — never a silent GO."
