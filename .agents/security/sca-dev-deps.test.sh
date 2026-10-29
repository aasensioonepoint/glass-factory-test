#!/usr/bin/env bash
# Suite for the devDependency scope switch of sca-scan.sh (T-00000199).
#
# Auto-discovered by core-scripts/run-bash-tests.sh. Every case runs the real
# dispatcher against a FIXTURE root holding no dependency manifest: it resolves
# and announces the scope, then exits 2 ("no known ecosystem detected") in well
# under a second. No npm, no network, no registry — what is under test is the
# DECISION and its announcement, not the audit itself.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

# A fixture root outside any repo: sca-scan.sh falls back to `pwd` for ROOT, so
# the opt-in it looks for is the fixture's own.
make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  echo "$r"
}

run_in() { ( cd "$1" && shift && env "$@" bash "$SCAN" 2>&1 ); }

echo "=== 1. NO OPT-IN FILE — devDependencies are NOT audited"
R="$(make_root off)"
OUT="$(run_in "$R" SCA_AUDIT_DEV_DEPS=)"
grep -q "scope: production only (--omit=dev)" <<<"$OUT" \
  && ok "the default scope is production only" || ko "wrong default scope"
grep -q "default (no opt-in file)" <<<"$OUT" \
  && ok "the report says WHY the scope is narrow" || ko "the reason is not stated"

echo
echo "=== 2. OPT-IN PRESENT — devDependencies ARE audited"
# The measured case: this is the setting under which `npm audit` would have seen
# nanoid < 3.3.18 instead of answering "found 0 vulnerabilities".
R="$(make_root on)"
: > "$R/.agents/security/audit-dev-deps.local"
OUT="$(run_in "$R" SCA_AUDIT_DEV_DEPS=)"
grep -q "scope: dev dependencies INCLUDED" <<<"$OUT" \
  && ok "the opt-in file widens the scope" || ko "the opt-in file had no effect"
grep -q "audit-dev-deps.local" <<<"$OUT" \
  && ok "the report names what turned it on" || ko "the source is not named"

echo
echo "=== 3. THE SCOPE IS ANNOUNCED ON EVERY RUN, NEVER INFERRED"
# A scope narrowed in silence reads, in a report, exactly like a scan that found
# nothing — the failure mode this whole switch was created by.
R="$(make_root announce)"
OUT="$(run_in "$R" SCA_AUDIT_DEV_DEPS=)"
grep -q "\[npm\] scope:" <<<"$OUT" \
  && ok "the scope line is present with no manifest at all" \
  || ko "the scope was decided in silence"

echo
echo "=== 4. THE ENV OVERRIDE WINS, IN BOTH DIRECTIONS"
# One direction only would be a trap: a repo could be widened but never narrowed
# back for a one-off run, and the override would read as broken.
R="$(make_root envon)"
OUT="$(run_in "$R" SCA_AUDIT_DEV_DEPS=1)"
grep -q "scope: dev dependencies INCLUDED" <<<"$OUT" \
  && ok "env can widen a repo with no opt-in file" || ko "env failed to widen"
R="$(make_root envoff)"
: > "$R/.agents/security/audit-dev-deps.local"
OUT="$(run_in "$R" SCA_AUDIT_DEV_DEPS=0)"
grep -q "scope: production only (--omit=dev)" <<<"$OUT" \
  && ok "env can narrow a repo that carries the opt-in file" || ko "env failed to narrow"
grep -q "env SCA_AUDIT_DEV_DEPS" <<<"$OUT" \
  && ok "the report names the override as the source" || ko "the override is not named"

echo
echo "=== 5. THE OPT-IN CANNOT TRAVEL TO A CONSUMER"
# The guarantee is not the file's content, it is the strip rule: without it the
# switch would ride to every adopting project the first time anyone syncs.
EXCL="$(cd "$HERE/../.." && pwd)/.template-exclude"
grep -q "^strip: .agents/security/audit-dev-deps.local$" "$EXCL" \
  && ok ".template-exclude strips the opt-in from the template branch" \
  || ko "THE OPT-IN WOULD TRAVEL — no strip rule in .template-exclude"

echo
echo "=== 6. THE FLAG IS NOT HARDCODED ANYWHERE ANYMORE"
# A second `--omit=dev` left inline would quietly win over the switch for one
# package manager and not the other — the kind of split nobody notices.
# The scope resolution legitimately spells the flag twice — once as the value,
# once inside the human-readable label. What must never happen is an AUDIT
# INVOCATION carrying it inline, which would win over the switch for one package
# manager and not the other: a split nobody notices until a report is empty.
LIVE="$(grep -v '^\s*#' "$SCAN" || true)"
INLINE="$(grep -nE '(npm|pnpm) audit .*(--omit=dev|--prod)' <<<"$LIVE" || true)"
[ -z "$INLINE" ] \
  && ok "no audit invocation hardcodes the scope" \
  || ko "an audit invocation bypasses the switch: $INLINE"
# Non-vacuity: the same probe must SEE the pattern when it is really there.
grep -qE '(npm|pnpm) audit .*(--omit=dev|--prod)' \
  <<<"  ( cd \"\$TGT\" && npm audit --package-lock-only --omit=dev --json )" \
  && ok "the probe recognises a hardcoded invocation when shown one" \
  || ko "the probe cannot detect what it is meant to ban — it measures nothing"

echo
echo "================================================================"
echo "sca-dev-deps: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Dev-dep scope: decided per repo, announced every run, unable to travel."
