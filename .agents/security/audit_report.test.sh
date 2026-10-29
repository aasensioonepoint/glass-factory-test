#!/usr/bin/env bash
# Tests for audit_report.py module-coverage rendering. Run: bash .agents/security/audit_report.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# allows-missing: python python3 py
#
# The interpreter probe below EXECUTES each of three names to find one that
# answers `--version`, so on a box carrying only python3 the names `python` and
# `py` legitimately fail to resolve. MEASURED here: `python` is absent and the
# runner's swallowed-127 sensor caught it. Without this line the sensor would
# report a missing dependency for a probe doing exactly its job — the false red
# the opt-out exists to prevent. It is NOT `requires:`, because that header names
# ONE command while this is a three-name ALTERNATIVE; if none of the three
# resolve, the SKIP on the line after is counted by the runner's survey.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/audit_report.py"
PY=""; for c in python python3 py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RD="$TMP/.agents/state/local/sca-reports"
mkdir -p "$RD"
OUT="$TMP/out.html"
fail() { echo "FAIL: $1"; exit 1; }
gen() { "$PY" "$SCRIPT" --reports-dir "$RD" --project t --out "$OUT" --waivers "$TMP/none.json" >/dev/null; }

# minimal mono-module scan input so gather() builds a model
printf '{"counters":{}}' > "$RD/effective-verdict.json"

# 1. iterative global review WITH per-module coverage -> report shows it
cat > "$RD/code-review.json" <<'JSON'
{"stats":{"files_flagged":9,"files_read":7,"caps_hit":true,"modules_total":4,"modules_covered":2,"modules_unread":["api","db"]},
 "findings":[{"file":"src/api/x.ts","line":10,"severity":"high","category":"sql-injection","summary":"concat","fix_hint":"bind","module":"api"}]}
JSON
gen
grep -q 'modules: 2/4 covered' "$OUT" || fail "per-module coverage not rendered"
grep -q 'unread: api, db' "$OUT"      || fail "unread modules not rendered"
grep -q 'files read: 7' "$OUT"        || fail "file counts not rendered"

# 2. legacy stats WITHOUT module fields -> no coverage clause, no crash
printf '{"stats":{"files_flagged":3,"files_read":2,"caps_hit":false},"findings":[]}' > "$RD/code-review.json"
gen
grep -q 'files read: 2' "$OUT" || fail "legacy stats not rendered"
! grep -q 'modules: ' "$OUT"   || fail "coverage clause should be omitted when module fields are absent"

echo "PASS: audit_report (2/2)"
