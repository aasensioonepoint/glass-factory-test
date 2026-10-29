#!/usr/bin/env bash
# Tests for the trivy IaC-misconfiguration block embedded in sca-scan.sh
# (T-004 shard 3). Run: bash .agents/security/trivy-config.test.sh — also
# auto-discovered by core-scripts/run-bash-tests.sh. Cases (a), (b) and (e) SKIP
# cleanly when trivy is not installed (as gitleaks/semgrep test suites do
# without their tool); cases (c), (d) and (f) run ALWAYS, including on the
# trivy-less CI runner, so this suite is green in CI either way. Case (d) is
# the non-regression guard: an existing ecosystem (npm) must keep scanning
# fine now that the trivy block sits right after it in the dispatcher. Case
# (e) is the false-GO regression the security review flagged: scanned=1 must
# only trigger on a REAL trivy finding-set (Results key present), never
# merely because trivy is installed and ran without error.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/sca-scan.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: sca-scan.sh not found"; exit 1; }

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

HAVE_TRIVY=0; command -v trivy >/dev/null 2>&1 && HAVE_TRIVY=1

# Isolated single-commit git repo under mktemp: sca-scan.sh's own
# `git rev-parse --show-toplevel` resolves to it, not to this repo — so this
# task's own in-flight changeset never leaks into a "clean" assertion.
new_repo() {
  local dir; dir="$(mktemp -d)"
  git -C "$dir" init -q
  git -C "$dir" -c user.email="test@test.local" -c user.name="test" \
    commit -q --allow-empty -m init
  printf '%s' "$dir"
}

# --- (a) Dockerfile with an obvious misconfig => trivy reports finding(s) ---
if [ "$HAVE_TRIVY" -eq 1 ]; then
  dir="$(new_repo)"
  cat > "$dir/Dockerfile" <<'DOCKEREOF'
FROM ubuntu:latest
RUN apt-get update
DOCKEREOF
  OUT_A="$(cd "$dir" && bash "$SCRIPT" 2>&1)"
  report="$dir/.agents/state/local/sca-reports/trivy-config.json"
  [ -f "$report" ] || fail "(a) trivy-config.json not produced — output: $OUT_A"
  # Count "Status": "FAIL" rows — the actual finding marker in trivy's config
  # report schema (stable across versions; some trivy releases omit the
  # legacy "AVDID" field and only carry a plain "ID", so don't key on that).
  count="$(grep -Ec '"Status"[[:space:]]*:[[:space:]]*"FAIL"' "$report" 2>/dev/null || true)"; count="${count:-0}"
  rm -rf "$dir"
  [ "$count" -gt 0 ] || fail "(a) expected >=1 misconfiguration finding, got $count — output: $OUT_A"
  ok "(a) Dockerfile with an obvious misconfig => trivy reports $count finding(s)"
else
  echo "  SKIP (a): trivy not installed"
fi

# --- (b) no IaC file at all => clean trivy report (SKIP if no trivy) --------
if [ "$HAVE_TRIVY" -eq 1 ]; then
  dir="$(new_repo)"
  printf '# nothing IaC here\n' > "$dir/README.md"
  OUT_B="$(cd "$dir" && bash "$SCRIPT" 2>&1)"
  report="$dir/.agents/state/local/sca-reports/trivy-config.json"
  count=0
  if [ -f "$report" ]; then
    # Count "Status": "FAIL" rows — the actual finding marker in trivy's config
    # report schema (stable across versions; some trivy releases omit the
    # legacy "AVDID" field and only carry a plain "ID", so don't key on that).
    count="$(grep -Ec '"Status"[[:space:]]*:[[:space:]]*"FAIL"' "$report" 2>/dev/null || true)"; count="${count:-0}"
  fi
  rm -rf "$dir"
  [ "$count" -eq 0 ] || fail "(b) expected a clean IaC scan, got $count finding(s) — output: $OUT_B"
  ok "(b) no IaC file => clean trivy report"
else
  echo "  SKIP (b): trivy not installed"
fi

# --- (c) trivy absent => noted (trivy: not installed), never a false GO -----
# Repo has no ecosystem at all (no manifest, no IaC file) — with trivy absent,
# NOTHING was scanned, so sca-scan.sh correctly reports NO-ECOSYSTEM (exit 2,
# CHANGED_ONLY not set here) rather than a false GO. When trivy IS installed on
# this box, hide it by excising ONLY its directory from PATH (not a from-
# scratch symlinked stub of every tool): on Windows Git Bash/MSYS2, a
# symlinked MSYS-linked binary (bash, grep, mkdir, sed, ...) invoked from a
# directory other than its own loses its co-located runtime DLL resolution
# ("error while loading shared libraries") — so a minimal stub silently
# breaks tools OTHER than the one being hidden too. Filtering PATH keeps every
# real tool at its real, DLL-resolvable location; only trivy disappears.
dir="$(new_repo)"
printf '# nothing IaC here\n' > "$dir/README.md"
if [ "$HAVE_TRIVY" -eq 0 ]; then
  OUT_C="$(cd "$dir" && bash "$SCRIPT" 2>&1)"; rc=$?
else
  TRIVY_DIR="$(dirname "$(command -v trivy)")"
  FILTERED_PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -Fxv "$TRIVY_DIR" | tr '\n' ':')"
  FILTERED_PATH="${FILTERED_PATH%:}"
  OUT_C="$(cd "$dir" && PATH="$FILTERED_PATH" bash "$SCRIPT" 2>&1)"; rc=$?
fi
degraded_file_content="$(cat "$dir/.agents/state/local/sca-reports/.degraded" 2>/dev/null || true)"
rm -rf "$dir"
[ "$rc" -eq 2 ] || fail "(c) no ecosystem + trivy absent must exit 2 (NO-ECOSYSTEM, never a false GO), got $rc — output: $OUT_C"
# When scanned=0 (no ecosystem at all), since T-00000488 sca-scan.sh ALSO echoes
# the .degraded reasons to the console (COVERAGE DEGRADED: …) before exiting — the
# pre-T-488 claim that it exited first is no longer true. This suite still asserts
# on the .degraded FILE itself, the surface it owns and the actual source of truth.
printf '%s' "$degraded_file_content" | grep -q "trivy: not installed" \
  || fail "(c) missing trivy must be noted in .degraded (trivy: not installed), got: $degraded_file_content"
ok "(c) trivy absent => noted in .degraded, never a false GO"

# --- (e) SECURITY-REVIEW-FLAGGED CASE: trivy PRESENT + no manifest + no IaC -
# must NOT be a false GO. This is the case (c) covers when trivy is absent
# (hidden), but the review specifically flagged the untested branch: on a
# box where trivy IS actually installed and runs normally (not hidden), does
# `scanned=1` still only trigger on a REAL IaC finding-set? trivy always
# writes a valid, non-empty JSON envelope even for a target with zero IaC
# files (confirmed empirically, v0.72.0: no "Results" key at all in that
# case) — a naive `[ -s "$TRIVY_TMP" ]` check alone would wrongly set
# scanned=1 here and turn NO-ECOSYSTEM into a false GO. SKIP if trivy is
# absent — that path is already exercised by case (c) above.
if [ "$HAVE_TRIVY" -eq 1 ]; then
  dir="$(new_repo)"
  printf '# nothing IaC here either\n' > "$dir/README.md"
  OUT_E="$(cd "$dir" && bash "$SCRIPT" 2>&1)"; rc=$?
  degraded_e="$(cat "$dir/.agents/state/local/sca-reports/.degraded" 2>/dev/null || true)"
  rm -rf "$dir"
  [ "$rc" -eq 2 ] || fail "(e) trivy present + no manifest + no IaC must still exit 2 (NO-ECOSYSTEM, never a false GO), got $rc — output: $OUT_E"
  printf '%s' "$degraded_e" | grep -q "trivy: no IaC file found to scan" \
    || fail "(e) expected a 'no IaC file found' note in .degraded, got: $degraded_e"
  ok "(e) trivy present, no manifest/no IaC => still NO-ECOSYSTEM, never a false GO"
else
  echo "  SKIP (e): trivy not installed (this exact branch needs a real trivy run — see case c for the absent-trivy equivalent)"
fi

# --- (d) NON-REGRESSION: an npm module with no IaC file still scans fine ----
# The trivy block is additive and unconditional (it has no manifest to gate
# on) — this proves it doesn't break the pre-existing npm ecosystem path.
dir="$(new_repo)"
cat > "$dir/package.json" <<'PKGEOF'
{"name": "fixture", "version": "1.0.0"}
PKGEOF
cat > "$dir/package-lock.json" <<'LOCKEOF'
{"name": "fixture", "version": "1.0.0", "lockfileVersion": 3, "packages": {"": {"name": "fixture", "version": "1.0.0"}}}
LOCKEOF
OUT_D="$(cd "$dir" && bash "$SCRIPT" 2>&1)"; rc=$?
rm -rf "$dir"
[ "$rc" -eq 0 ] || fail "(d) non-regression: npm-only module (no IaC) should still exit 0 (GO), got $rc — output: $OUT_D"
ok "(d) non-regression: existing npm/lock module scan unaffected by the trivy block"

# --- (f) T-01M52X1W3WPKCWX1DC36NMKJB6 : the hook throttle wakes on Terraform --
# Under SCA_CHANGED_ONLY=1 (the hook form) sca-scan.sh exits early unless
# `git diff --name-only HEAD` names a manifest or an IaC file. Before this
# task the trigger knew `*.tf` / `*.tf.json` only: a changed `prod.tfvars` or
# `.terraform.lock.hcl` printed the skip line and trivy config never ran.
# Two-sided witness: the README-only control MUST print the skip line and
# write no report (so the "absent" assertions cannot pass on a renamed line);
# each Terraform file MUST NOT print it, and the run reaches the reports
# directory. The file is committed THEN modified: an untracked file is not in
# `git diff HEAD`. Runs ALWAYS (no trivy needed). AGENTS_HOOK_HOST is unset so
# the Copilot early exit never reads this suite's stdin.
SKIP_LINE='SCA: no dependency manifest / IaC file changed — skipping.'
commit_then_change() {  # $1 = repo dir, $2 = path inside it: commit, then modify
  mkdir -p "$(dirname "$1/$2")"
  printf 'region = "fixture-a"\n' > "$1/$2"
  git -C "$1" add -- "$2"
  git -C "$1" -c user.email="test@test.local" -c user.name="test" \
    commit -q -m fixture
  printf 'region = "fixture-b"\n' > "$1/$2"
}
hook_run() {  # $1 = repo dir: the hook form of sca-scan.sh, output on stdout
  ( unset AGENTS_HOOK_HOST; cd "$1" && SCA_CHANGED_ONLY=1 bash "$SCRIPT" </dev/null 2>&1 )
}
dir="$(new_repo)"
commit_then_change "$dir" README.md
OUT_F0="$(hook_run "$dir")"
reports_f0=0; [ -d "$dir/.agents/state/local/sca-reports" ] && reports_f0=1
rm -rf "$dir"
printf '%s\n' "$OUT_F0" | grep -Fxq "$SKIP_LINE" \
  || fail "(f) control: a README-only change must print the skip line — output: $OUT_F0"
[ "$reports_f0" -eq 0 ] || fail "(f) control: the skip must exit before any report is written"
ok "(f) control: README-only change => skip line printed, no report"
for tf_file in infra/prod.tfvars infra/.terraform.lock.hcl; do
  dir="$(new_repo)"
  commit_then_change "$dir" "$tf_file"
  OUT_F="$(hook_run "$dir")"
  reports_f=0; [ -d "$dir/.agents/state/local/sca-reports" ] && reports_f=1
  rm -rf "$dir"
  if printf '%s\n' "$OUT_F" | grep -Fxq "$SKIP_LINE"; then
    fail "(f) a changed $tf_file must wake the SCA hook, got the skip line — output: $OUT_F"
  fi
  [ "$reports_f" -eq 1 ] || fail "(f) a changed $tf_file: the run never reached the reports directory — output: $OUT_F"
  ok "(f) changed $tf_file => SCA hook not skipped"
done

echo "PASS: trivy-config ($pass check(s); trivy present=$HAVE_TRIVY)"
