#!/usr/bin/env bash
# Suite for the module-coverage widening and its safety catch (T-00000200).
#
# Two halves, and the second is what makes the first shippable:
#   - the bare form (what all four host hooks invoke) no longer sees ONLY the
#     repository root, so a project whose manifests live below it is scanned;
#   - a module under a PROTECTED path no longer gates, because a consumer cannot
#     bump a dependency in vendored code it is forbidden to edit.
#
# The classification itself is covered exhaustively by test_protected_module.py.
# What is asserted here is the WIRING — that sca-scan.sh actually consults it and
# actually substitutes a non-gating verdict — plus the fallback's own conditions.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/sca-scan.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

make_root() {
  local r="$TMP/$1"
  mkdir -p "$r/.agents/security" "$r/.agents/state/local/sca-reports"
  cp "$HERE/module_discovery.py" "$HERE/protected_module.py" "$r/.agents/security/"
  echo "$r"
}

echo "=== 1. A REPO WHOSE MANIFESTS LIVE BELOW THE ROOT IS NOW SCANNED"
# The measured defect: on this very repository the automatic gate answered
# "no known ecosystem detected" while --all-modules scanned .agents/ui-src fine.
R="$(make_root fallback)"
mkdir -p "$R/frontend" && echo '{"name":"f","version":"1.0.0"}' > "$R/frontend/package.json"
OUT="$( cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1 )"
grep -q "falling back to --all-modules" <<<"$OUT" \
  && ok "the bare form falls back when discovery finds a module a root scan would not cover" \
  || ko "no fallback — a module-only repo is still invisible to the hook"
grep -q "no known ecosystem detected" <<<"$OUT" \
  && ko "still reports 'no known ecosystem detected'" \
  || ok "it no longer claims there is nothing to scan"

echo
echo "=== 2. A REPO WITH A ROOT MANIFEST IS LEFT EXACTLY AS IT WAS"
# Deliberately additive: a repo whose ONLY module is the root does not fall back,
# keeping the exact same scan and report paths. Since T-00000291 the root module
# is relocated to the ROOT of sca-reports precisely FOR the dashboard and
# sca-watch.sh, which read effective-verdict.json there — the relocation serves
# that contract, it does not break it.
R="$(make_root rootmanifest)"
echo '{"name":"r","version":"1.0.0"}' > "$R/package.json"
OUT="$( cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1 )"
grep -q "falling back" <<<"$OUT" \
  && ko "a root-manifest repo was rerouted — report paths would move" \
  || ok "a root-manifest repo keeps the old scope and its report paths"

echo
echo "=== 3. THE OLD SCOPE STAYS REACHABLE ON PURPOSE"
R="$(make_root rootonly)"
mkdir -p "$R/frontend" && echo '{"name":"f","version":"1.0.0"}' > "$R/frontend/package.json"
OUT="$( cd "$R" && SCA_ROOT_ONLY=1 SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1 )"
grep -q "falling back" <<<"$OUT" \
  && ko "SCA_ROOT_ONLY=1 did not hold the old behaviour" \
  || ok "SCA_ROOT_ONLY=1 keeps the pre-T-200 scope"

echo
echo "=== 4. THE GATE CONSULTS THE PROTECTED-PATH PROBE, AND ACTS ON IT"
# Wiring, not classification: a probe that is called but whose answer is dropped
# would pass every test in test_protected_module.py and still block consumers.
LIVE="$(grep -v '^\s*#' "$SCAN" || true)"
grep -q 'protected_module.py' <<<"$LIVE" \
  && ok "sca-scan.sh calls the canonical probe" \
  || ko "the probe is not wired in — consumers keep the permanent NO-GO"
grep -q 'rc=3' <<<"$LIVE" \
  && ok "a NO-GO in a protected module is substituted, not propagated" \
  || ko "the substitution is gone — a protected module still gates"
grep -q 'TRACKED-NOT-GATING' <<<"$LIVE" \
  && ok "the summary carries a verdict of its own for that case" \
  || ko "no distinct verdict: a tracked module would read as a plain GO"
grep -q 'NOT GATING' <<<"$LIVE" \
  && ok "the exemption is announced in the run output" \
  || ko "the exemption is SILENT — it would read as 'nothing was found'"

echo
echo "=== 5. AMBIGUITY TAKES THE STRICTER BRANCH, OUT LOUD"
# Exempting on a guess would silence a real, actionable finding.
grep -q 'exempted this run' <<<"$LIVE" \
  && ok "an unreadable guard exempts nothing and says so" \
  || ko "the unknown case is unhandled or silent"

echo
echo "=== 6. NON-VACUITY OF THE WIRING PROBES"
# Each grep above must be able to FAIL. A stripped copy of the dispatcher, with
# the T-200 block removed, must trip every one of them.
STRIP="$TMP/stripped.sh"
sed '/protected_module/d; /rc=3/d; /TRACKED-NOT-GATING/d; /NOT GATING/d' "$SCAN" > "$STRIP"
DEAD="$(grep -v '^\s*#' "$STRIP" || true)"
miss=0
for pat in 'protected_module.py' 'rc=3' 'TRACKED-NOT-GATING' 'NOT GATING'; do
  grep -q "$pat" <<<"$DEAD" && miss=$((miss + 1))
done
[ "$miss" -eq 0 ] \
  && ok "all four probes go red on a dispatcher with the T-200 block removed" \
  || ko "$miss probe(s) still match a stripped dispatcher — they measure nothing"

echo
echo "=== 7. A ROOT MANIFEST NO LONGER DISABLES THE FALLBACK (T-00000291)"
# THE defect this task closes: a single root manifest used to switch the fallback
# off entirely, so a root package.json BESIDE a frontend/ module left the
# sub-module unscanned — invisible on this repo (no root manifest) and active at
# every adopter that had one. This case goes RED on the pre-T-291 dispatcher
# (root scan only, no 'falling back') and green after.
R="$(make_root rootplussub)"
echo '{"name":"r","version":"1.0.0"}' > "$R/package.json"
mkdir -p "$R/frontend" && echo '{"name":"f","version":"1.0.0"}' > "$R/frontend/package.json"
OUT="$( cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1 )"
grep -q "falling back to --all-modules" <<<"$OUT" \
  && ok "a root manifest beside a sub-module still falls back" \
  || ko "root manifest disabled the fallback — the sub-module went unscanned"
grep -q "== module frontend" <<<"$OUT" \
  && ok "the frontend sub-module is actually scanned" \
  || ko "the frontend sub-module was never reached"
[ -f "$R/.agents/state/local/sca-reports/effective-verdict.json" ] \
  && ok "the root module's verdict lands at the root of sca-reports" \
  || ko "no root verdict at sca-reports/ — the dashboard would read nothing"

echo
echo "=== 8. WORKSPACES FOLDED UNDER THE ROOT ⇒ NO FALLBACK (additive holds)"
# A root package.json that DECLARES workspaces folds packages/* under itself, so
# discovery emits only the root (path '.') and a root scan covers everything —
# no fallback, no report-path move. The additive guarantee, where the old rule
# was right.
R="$(make_root workspaces)"
printf '{"name":"r","version":"1.0.0","workspaces":["packages/*"]}' > "$R/package.json"
mkdir -p "$R/packages/a" && echo '{"name":"a","version":"1.0.0"}' > "$R/packages/a/package.json"
OUT="$( cd "$R" && SCA_AUDIT_DEV_DEPS=0 bash "$SCAN" 2>&1 )"
grep -q "falling back" <<<"$OUT" \
  && ko "workspaces triggered a needless fallback — additive guarantee broken" \
  || ok "workspaces folded under the root ⇒ no fallback, report paths unchanged"

echo
echo "================================================================"
echo "sca-module-gate: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Coverage widened; a finding nobody can act on is tracked, not a red light."
