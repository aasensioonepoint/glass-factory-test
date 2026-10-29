#!/usr/bin/env bash
# Suite for the hook-mode throttle of sca-scan.sh (SCA_CHANGED_ONLY=1): the
# filter that decides whether a change vs HEAD touched a dependency manifest
# (T-01M5CKHWX9BDTX775TM4R0NP0Y), and the header that names the ecosystems
# actually scanned (T-01M5CKHXER9Y14Z99XABT112PR). Auto-discovered by
# core-scripts/run-bash-tests.sh.
#
# What it proves, in a REAL git repo (the throttle reads `git diff HEAD`, so a
# root outside any repo would never reach it): each manifest of the ecosystems
# NOT covered in v1 (Rust, Go, PHP, Ruby, .NET), committed then modified, WAKES
# the scan — it no longer answers "skipping", and the scan names the ecosystem
# as not covered. A README alone still skips; a `.csproj.bak` still skips (the
# `$` anchor of the .NET alternative bites).
#
# ZERO network, ZERO real scanner: none of these fixtures carries a scanned
# manifest, so the run ends on the "no ecosystem" branch, rc 0 under the hook.
#
# MUTATION TABLE — played red then reverted BY Edit before commit (2 and 3 in one
# edit: their cells are disjoint, and each named cell went red):
#   1. drop `Cargo\.(toml|lock)|` from the filter     => (a) Cargo.toml, Cargo.lock RED
#   2. drop `go\.(mod|sum)|`                          => (a) go.mod, go.sum RED
#   3. drop `[^/]*\.(csproj|sln)$|`                   => (a) x.csproj, x.sln RED
#   4. `[^/]*\.(csproj|sln)` without `$`              => (c) RED
#   5. header back to `Swift/CocoaPods`               => (d) RED
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
case "$TMP" in
  "" | "$PWD" | "$PWD"/*) echo "FATAL: refusing degenerate TMP='$TMP' (empty or inside CWD)"; exit 2 ;;
esac
[ -d "$TMP" ] || { echo "FATAL: TMP='$TMP' is not a directory (mktemp failed?)"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# A git repo whose first commit carries the file $2 (and, if given, an unchanged
# companion $3), then $2 modified: `git diff --name-only HEAD` names exactly $2.
# Same layout as sca-uncovered.test.sh make_root (module discovery + emit-event stub).
make_repo() {
  local r="$TMP/$1" f="$2" companion="${3:-}"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports" "$r/.claude/hooks"
  cp "$HERE/module_discovery.py" "$HERE/protected_module.py" "$r/.agents/security/"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "%s\n" "$@" > "$CLAUDE_PROJECT_DIR/emit-event.argv"' \
    > "$r/.claude/hooks/emit-event.sh"
  chmod +x "$r/.claude/hooks/emit-event.sh"
  printf 'v1\n' > "$r/$f"
  [ -z "$companion" ] || printf 'v1\n' > "$r/$companion"
  git -C "$r" init -q
  git -C "$r" add -A
  git -C "$r" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -qm init
  printf 'v2\n' >> "$r/$f"
  echo "$r"
}

run_hook() {
  (cd "$1" && SCA_CHANGED_ONLY=1 SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1)
}

SKIP='SCA: no dependency manifest / IaC file changed — skipping.'

# ---------------------------------------------------------------------------
echo "=== (a) each uncovered-ecosystem manifest wakes the hook"
# A lock is detected through its manifest, never alone: the lock cells carry the
# manifest UNCHANGED, so the change the filter sees is the lock's only.
i=0
for cell in Cargo.toml Cargo.lock:Cargo.toml go.mod go.sum:go.mod composer.json \
            composer.lock:composer.json Gemfile Gemfile.lock:Gemfile x.csproj x.sln; do
  i=$((i + 1))
  f="${cell%%:*}"; companion=''
  [ "$f" = "$cell" ] || companion="${cell#*:}"
  R="$(make_repo "a$i" "$f" "$companion")"
  OUT="$(run_hook "$R")"; rc=$?
  [ "$rc" -eq 0 ] && ok "(a) $f: rc=0" || ko "(a) $f: rc=$rc, expected 0 — output: $OUT"
  ! grep -Fq "$SKIP" <<<"$OUT" \
    && ok "(a) $f: the hook did not skip" || ko "(a) $f: the hook skipped a manifest change"
  grep -Fq 'ecosystem not covered in v1' <<<"$OUT" \
    && ok "(a) $f: the ecosystem is named as not covered" || ko "(a) $f: no not-covered line — output: $OUT"
done

# ---------------------------------------------------------------------------
echo "=== (b) a README alone still skips"
R="$(make_repo b README.md)"
OUT="$(run_hook "$R")"; rc=$?
[ "$rc" -eq 0 ] && ok "(b) rc=0" || ko "(b) rc=$rc, expected 0"
grep -Fq "$SKIP" <<<"$OUT" && ok "(b) skipped" || ko "(b) did not skip — output: $OUT"

# ---------------------------------------------------------------------------
echo "=== (c) a .csproj.bak still skips (the \$ anchor bites)"
R="$(make_repo c notes.csproj.bak)"
OUT="$(run_hook "$R")"; rc=$?
[ "$rc" -eq 0 ] && ok "(c) rc=0" || ko "(c) rc=$rc, expected 0"
grep -Fq "$SKIP" <<<"$OUT" && ok "(c) skipped" || ko "(c) did not skip — output: $OUT"

# ---------------------------------------------------------------------------
echo "=== (d) the header no longer claims CocoaPods is scanned"
HEAD_LINE="$(grep -m1 -F '# - Ecosystems SCANNED:' "$SCAN")"
! grep -Fq 'CocoaPods' <<<"$HEAD_LINE" \
  && ok "(d) no CocoaPods in the SCANNED line" || ko "(d) SCANNED line still names CocoaPods: $HEAD_LINE"
grep -Fq 'a Podfile.lock alone is NOT scanned' <<<"$HEAD_LINE" \
  && ok "(d) the Podfile.lock bound is said" || ko "(d) Podfile.lock bound missing: $HEAD_LINE"

# ---------------------------------------------------------------------------
echo "=== (e) the header no longer says the hook throttles these manifests"
! grep -Fq 'throttled before' "$SCAN" \
  && ok "(e) no 'throttled before' claim left" || ko "(e) the header still says the hook throttles uncovered manifests"
grep -Fq 'wakes the scan, which names it' "$SCAN" \
  && ok "(e) the header says the hook wakes the scan" || ko "(e) the wake-up sentence is missing"
# (f) The filter reads `git diff --name-only HEAD`: an UNTRACKED new manifest is skipped, and
# the header says so (critic-opus re-review, F4).
grep -Fq 'not yet `git add`ed is skipped' "$SCAN" \
  && ok "(f) the header names the untracked-manifest bound" || ko "(f) the untracked-manifest bound is missing"

echo
echo "sca-hook-filter: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
