#!/usr/bin/env bash
# Tests for core-scripts/verify.sh --at <ref>. Run: bash core-scripts/verify.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# requires: git
#
# REQUIRED, not auto-skipped, and this suite is the sharpest case for the rule:
# it is the suite that guards THE GATE. Git call sites below build throwaway
# repos, commit into them, and drive `verify.sh` against real refs —
# without git it establishes exactly nothing. It used to announce that with
# `exit 0`, which the runner counted as a pass: the judge of the gate was
# certified by a judge that had not run. The runner now declines to run it and
# reports a missing dependency, which is red, and the `command -v git` escape
# that stood below is gone — one dependency, one judge.
#
# What is under test is a CONTRACT, not a convenience: verify.sh must never be
# able to print a verdict for a tree that is not the SHA it names, and must
# never run a destructive checkout/clean on a directory it has not proven to be
# its own verification clone. Hence arms 5-8 (invalid ref, foreign-directory and
# foreign-clone collisions, held lock) matter as much as the happy path. Arm 10
# adds the lock's own contract: a refusal must say WHO holds it and since when,
# and a lock whose holder is dead must be reclaimed without a human.
#
# Arms 11-14 pin the PERSISTED VERDICT: a printed `VERIFY OK @ <sha>` had no
# reader, and a mechanism whose return channel is discarded does not exist
# (L-00000136). They check where the stamp lands, what it records, that exactly
# ONE installation status line is printed, that a red never leaves a green behind
# — on BOTH verdict sites, which are different code and only one of which was ever
# wrong — and, at arm 14, that the channel HAS TWO ENDS AND THEY MEET.
#
# ARM 14 EXISTS BECAUSE THIS BENCH WAS COMMITTING THE DEFECT IT QUOTES. Every stamp
# `.githooks/pre-push.test.sh` reads is fabricated by its own `stamp()` helper, and
# until arm 14 nothing anywhere handed the hook a stamp that `stamp_write` had
# actually produced. One field renamed in that function — or reordered, or given a
# trailing \r — and BOTH suites would have stayed green while the installed hook
# refused every push in the repository. L-00000136 was cited six lines above and
# not applied to the bench citing it.
#
# WHAT IS REAL, ARM BY ARM, because the sweeping sentence that used to stand here
# ("arms 1-8 and 10-11 run against a STUB verify.sh") swallowed arm 11a and made
# its two named mutations UNREACHABLE: the stub calls neither guarded function, so
# `stamp_write` and `hook_status_line` could BOTH lose their VERIFY_INNER guard
# with the arm still green — measured, `PASS: verify --at (13/13)`, rc=0, twice.
# No Docker anywhere:
#   - arms 1-8, 10, 11b : STUB inner (commit 1); nothing real is executed.
#   - arm 9             : the REAL inner, guaranteed RED in seconds.
#   - arms 11a and 14   : the REAL inner, guaranteed GREEN. Commit `greenleg`
#                         carries the shipped script plus a passing
#                         `core-scripts/run-bash-tests.sh`, and an interpreter SHIM
#                         sits first on PATH for the pytest leg. THE SCRIPT UNDER
#                         TEST IS THE SHIPPED ONE; only its two leaf commands are
#                         stubbed, which is exactly what lets control flow reach
#                         `stamp_write` and `hook_status_line` at all.
#   - arm 12            : a deliberately RED stub inner.
#   - arm 13            : the real script on the LIVE fixture tree.
#   - arm 18            : the REAL inner, guaranteed RED at its FIRST step (commit
#                         `ffleg`), its later leaves stubbed into markers and
#                         `docker` stubbed first on PATH — the fail-fast. Placed
#                         BEFORE arm 15 in this file, so the nested run carries it.
#   - arm 15            : THIS FILE, re-run under VERIFY_INNER=1. Real inner twice.
# (measured: 0s for arms 12 and 13; 8s for arms 1-14, so ~17s with arm 15.)
#
# THE BENCH BUILDS THE ENVIRONMENT OF WHAT IT LAUNCHES — INHERITED VARIABLE AND
# DEFAULT BRANCH INCLUDED — IT NEVER INHERITS IT.
#
# Third failure of that exact shape on this lot, so it is written down as a bound
# rather than fixed in silence: the bench was measuring something OTHER than what
# it believed, because its environment was not the one it assumed. Both of the
# first two were green on the host and red under the gate, which is the worst
# possible place to learn it.
#
# Here the variable is VERIFY_INNER. `core-scripts/verify.sh` sets it as a COMMAND
# PREFIX on the delegated run (`VERIFY_INNER=1 bash "$WT/core-scripts/verify.sh"`), so
# it is EXPORTED into that process and INHERITED by everything that run launches —
# which includes `core-scripts/run-bash-tests.sh`, which includes this file. Under the
# gate this bench therefore runs with VERIFY_INNER=1 already in its environment.
# But every `verify.sh` this bench starts inside its OWN throwaway repository is an
# INDEPENDENT run, never a delegated one: it must see VERIFY_INNER=0, and it is
# this file's job to say so. All FOUR launch sites (`run`, `run_green`, arm 13's
# bare call, arm 18's `ff_run`) pin it explicitly. `ff_run` also pins the two
# settings arm 18 is about — CADRE_GATE_FAIL_FAST and CADRE_GATE_DURATIONS_DIR —
# because the gate hands them down the same way (arm 15 poisons both).
#
# MEASURED before the fix — under the gate, and reproduced on the host with
# `VERIFY_INNER=1 bash core-scripts/verify.test.sh`:
#   FAIL: 11a: a green --at wrote no verdict stamp at …/repo/.agents/state/local/VERIFY_STAMP
# `stamp_write` took its guarded early return, wrote nothing, and the arm blamed
# verify.sh for a hole the bench had dug. This is NOT a defect in verify.sh:
# marking the delegated run is the mechanism working as designed.
#
# THE RULE IS NOT NEW IN THIS REPOSITORY, ONLY NEW HERE: `core-scripts/run-bash-tests.sh`
# (:160-166) already assigns RBT_MISSING_LOG "UNCONDITIONALLY, NEVER INHERITED",
# because a nested copy of the runner inheriting its parent's log made the parent
# go red over a suite that had passed. Same defect, same fix, one level down — the
# runner learned it and the two benches it runs had not.
#
# A COMMAND PREFIX AT EACH SITE, AND DELIBERATELY NOT AN `unset VERIFY_INNER` AT
# THE TOP OF THIS FILE. An unset would neutralise the poison at line 1, before arm
# 15 could ever carry it to the launch sites — and arm 15 would then stay GREEN
# with all three prefixes removed. That is a negative control that certifies
# itself. A prefix is scoped to one command and never touches this shell, which is
# what lets arm 15 hold VERIFY_INNER=1 all the way down and still demand green.
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
# THE SERIES FOR ARMS 1-18 (T-01M60XKFK7MPKZWNHH326ZMW3M): verify.sh's `auto` legs play pytest and the bash
# suites TOGETHER on 16 cores or more, and arm 18a pins the series' contract (`--- NOT RUN bash …` after a
# red pytest). Exported, so every launch site of arms 1-18 — `run`, `run_green`, arm 13's bare call,
# `ff_run`, and the `--at` inner they delegate to — plays the series; arm 19 sets its own mode at each
# launch. verify.sh unsets the variable after reading it, so the suites under the gate never carry it.
export CADRE_GATE_JAMBES=serie
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_VERIFY="$HERE/verify.sh"
SELF="$HERE/$(basename "${BASH_SOURCE[0]}")"
[ -f "$REAL_VERIFY" ] || { echo "FAIL: $REAL_VERIFY not found"; exit 1; }

TMP="$(mktemp -d)"
# The cleanup is guarded on BASHPID, not left bare, and that is a MEASURED
# necessity rather than caution: a FORKED CHILD of this shell can run this EXIT
# trap. On Git-Bash (MINGW64, bash 5.2.37) a background job killed shortly after
# being spawned dies BEFORE it finishes exec'ing — MSYS fork emulation is slow —
# so the victim is still bash and it executes the trap it inherited. 25 firings
# out of 25 attempts. Unguarded, that wiped $TMP MID-RUN: arm 10b then failed with
# `bash: .../repo/core-scripts/verify.sh: No such file or directory`, ~70% of runs,
# and the "leftover" $TMP contained only the lock directory recreated afterwards.
# `$$` cannot guard this — it is the PARENT's pid in the child too. $BASHPID can.
# A function, not an inline `[ … ] && rm`, so the trap's own exit status can never
# be mistaken for the suite's verdict.
TMP_OWNER="${BASHPID:-$$}"
cleanup() {
  if [ "${BASHPID:-$$}" = "$TMP_OWNER" ]; then rm -rf "$TMP"; fi
  return 0
}
trap cleanup EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }

# --- throwaway repo -----------------------------------------------------------
REPO="$TMP/repo"
mkdir -p "$REPO/core-scripts"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t
git -C "$REPO" config user.name t
# Byte-identical checkouts: with a global autocrlf=true (the Windows default)
# the worktree copy of a shell script comes back CRLF, which is a different file
# than the one under test.
git -C "$REPO" config core.autocrlf false

# commit 1: a stub verify.sh. It self-locates via BASH_SOURCE exactly like the
# real scripts do, so it can report WHICH tree it was run from — that is the
# whole point: the outer never cd's into the clone, the inner rebases itself.
# Being TRACKED, the stub travels through `git clone` like any other file.
cat > "$REPO/core-scripts/verify.sh" <<'STUB'
#!/usr/bin/env bash
STUB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
{
  echo "HEAD=$(git -C "$STUB_ROOT" rev-parse HEAD)"
  echo "ROOT=$STUB_ROOT"
  echo "PWD=$PWD"
  echo "ARGS=$*"
  # The lock is HELD for as long as the inner run executes, so this is the only
  # vantage point from which its owner file can be observed IN FLIGHT.
  echo "LOCKOWNER=$(tr '\n' ' ' < "${VERIFY_WORKTREE_DIR:-/nonexistent}.lock/owner" 2>/dev/null)"
} > "$VERIFY_STUB_OUT"
echo "STUB RAN"
STUB
# The kit git-ignores its one throw-away bucket (`/.agents/state/local/`), and the
# fixture must too — from the persisted-verdict change on, a green run WRITES a
# stamp there. Without this line arm 3 ("the live tree was not dirtied by the run")
# goes red on an untracked stamp, and would be reporting a gap in the FIXTURE
# rather than a defect in verify.sh.
printf '/.agents/state/local/\n' > "$REPO/.gitignore"
git -C "$REPO" add -A
git -C "$REPO" commit -qm stub
SHA1="$(git -C "$REPO" rev-parse HEAD)"

# commit 2: the REAL script under test, so the outer run is the code we ship.
cp "$REAL_VERIFY" "$REPO/core-scripts/verify.sh"
git -C "$REPO" add -A
git -C "$REPO" commit -qm real
SHA2="$(git -C "$REPO" rev-parse HEAD)"
SHORT2="$(git -C "$REPO" rev-parse --short HEAD)"

WT="$TMP/wt"
OUT="$TMP/stub-out.txt"
# `run <wtdir> <args...>` — every invocation goes through the repo's checked-out
# copy (HEAD = commit 2 = the real script), with the clone location pinned
# inside the tmpdir so nothing is ever created beside the developer's repo.
# `VERIFY_INNER=0` is part of that pinning and not decoration: this is an
# INDEPENDENT run in the fixture repo, so it must not inherit the marker the gate
# puts on its DELEGATED run (header, "the bench builds the environment").
# MUTATION: drop the prefix and run this file under VERIFY_INNER=1 → arm 11b goes
# red (`--linux was not recorded in the stamp`, because `stamp_write` returns
# early), then arm 12 (`A STALE GREEN SURVIVED A RED --at`). Caught by arm 15.
run() { local w="$1"; shift; VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$w" VERIFY_STUB_OUT="$OUT" bash "$REPO/core-scripts/verify.sh" "$@"; }
field() { sed -n "s/^$1=//p" "$OUT"; }

# 1. --at <sha1> checks out sha1 in a sibling CLONE and runs THAT copy there.
#    `.git` must be a real DIRECTORY: a worktree's pointer file holds an absolute
#    host path, which is unreadable once the tree is mounted in the --linux
#    container (measured: "fatal: not a git repository: /repo/C:/Users/...").
rm -f "$OUT"
out="$(run "$WT" --at "$SHA1" 2>&1)" || fail "1: --at sha1 should exit 0 (stub returns 0): $out"
[ -d "$WT/.git" ] || fail "1: $WT/.git is not a directory — not a self-contained clone"
[ ! -f "$WT/.git" ] || fail "1: $WT/.git is a pointer file — a linked worktree cannot be mounted"
[ -f "$OUT" ] || fail "1: the clone's own verify.sh never ran"
[ "$(field HEAD)" = "$SHA1" ] || fail "1: inner HEAD is $(field HEAD), expected sha1 $SHA1"
WTREAL="$(cd "$WT" && pwd)"
[ "$(field ROOT)" = "$WTREAL" ] || fail "1: inner ran from $(field ROOT), expected the clone $WTREAL"
[ "$(field ARGS)" = "" ] || fail "1: inner got residual args '$(field ARGS)', expected none"
echo "$out" | grep -q "frozen checkout @" || fail "1: no frozen-checkout banner"

# 2. --linux is forwarded, --at is NOT (or the inner would recurse). Flag order
#    must not matter, so this arm passes them the other way round.
rm -f "$OUT"
out="$(run "$WT" --linux --at "$SHA1" 2>&1)" || fail "2: --linux --at should exit 0: $out"
[ "$(field ARGS)" = "--linux" ] || fail "2: inner args were '$(field ARGS)', expected exactly '--linux'"

# 3. The live tree is not measured and not touched, and the lock is released.
[ "$(git -C "$REPO" rev-parse HEAD)" = "$SHA2" ] || fail "3: live tree HEAD moved"
[ -z "$(git -C "$REPO" status --porcelain)" ] || fail "3: live tree was dirtied by the run"
[ ! -e "$WT.lock" ] || fail "3: lock $WT.lock survived a successful run"

# 4. Reuse: a leftover untracked file in the clone must not survive into the
#    next measurement (CI starts from a clean checkout; so must this). This arm
#    also exercises the reuse path end to end: identity check, then fetch.
echo parasite > "$WT/parasite.txt"
rm -f "$OUT"
out="$(run "$WT" --at "$SHA1" 2>&1)" || fail "4: reuse run should exit 0: $out"
[ ! -e "$WT/parasite.txt" ] || fail "4: untracked leftover survived the re-checkout"
[ "$(field HEAD)" = "$SHA1" ] || fail "4: reused clone is not at sha1"

# 5. An unresolvable ref costs nothing: no clone, no lock, non-zero exit.
WT5="$TMP/wt5"
if out="$(run "$WT5" --at no-such-ref 2>&1)"; then fail "5: an invalid ref must not exit 0"; fi
echo "$out" | grep -q "does not resolve to a commit" || fail "5: no diagnostic for the bad ref: $out"
[ ! -e "$WT5" ] || fail "5: a clone was created for an invalid ref"
[ ! -e "$WT5.lock" ] || fail "5: a lock was left behind for an invalid ref"

# 6. A dirty live tree warns (the verdict covers the SHA, not the edits) but
#    never blocks — blocking here would defeat the point of the frozen mode.
echo dirt > "$REPO/dirty.txt"
rm -f "$OUT"
out="$(run "$WT" --at "$SHA1" 2>&1)" || fail "6: a dirty live tree must not block the run: $out"
echo "$out" | grep -q "warning: live tree has uncommitted changes" || fail "6: no dirty-tree warning: $out"
[ -f "$OUT" ] || fail "6: the run did not continue after the warning"
rm -f "$REPO/dirty.txt"

# 7. IDENTITY GUARD, two shapes. `checkout -f` + `clean -fdx` on an
#    unidentified directory is a data-loss bug, so both must be hard errors with
#    the target left exactly as it was.
#    (a) a plain directory holding real files — no .git at all.
WT7="$TMP/wt7"
mkdir -p "$WT7"
echo precious > "$WT7/keep.txt"
if out="$(run "$WT7" --at "$SHA1" 2>&1)"; then fail "7a: a non-clone directory must not exit 0"; fi
echo "$out" | grep -q "is not the verification clone of this repository" || fail "7a: no identity diagnostic: $out"
[ "$(cat "$WT7/keep.txt")" = "precious" ] || fail "7a: the unidentified directory was modified"
[ ! -e "$WT7.lock" ] || fail "7a: lock leaked on the identity failure"

#    (b) a real git clone — of SOMEONE ELSE'S repository. The `.git` directory
#        test passes here, so only the origin comparison can catch it. This is
#        the arm that would fail if the origin URL were compared naively: git
#        stores it in Windows form (measured: an 8.3 short name like
#        `C:/Users/USER~1.NAME/...`) while $ROOT in bash is `/c/Users/...`.
OTHER="$TMP/other"
mkdir -p "$OTHER"
git -C "$OTHER" init -q
git -C "$OTHER" config user.email t@t
git -C "$OTHER" config user.name t
git -C "$OTHER" config core.autocrlf false
echo "someone else's work" > "$OTHER/theirs.txt"
git -C "$OTHER" add -A
git -C "$OTHER" commit -qm other
WT7B="$TMP/wt7b"
git clone -q "$OTHER" "$WT7B"
OTHER_HEAD="$(git -C "$WT7B" rev-parse HEAD)"
if out="$(run "$WT7B" --at "$SHA1" 2>&1)"; then fail "7b: a clone of another repo must not exit 0"; fi
echo "$out" | grep -q "is not the verification clone of this repository" || fail "7b: no identity diagnostic: $out"
[ "$(git -C "$WT7B" rev-parse HEAD)" = "$OTHER_HEAD" ] || fail "7b: the foreign clone was checked out over"
[ -f "$WT7B/theirs.txt" ] || fail "7b: the foreign clone's files were cleaned"
[ ! -e "$WT7B.lock" ] || fail "7b: lock leaked on the identity failure"

#    (c) THE FORGED ORIGIN (CWE-346, regression test). `git init` + `remote add
#        origin <path to the repo>` is enough to satisfy both the .git-directory
#        test and the origin comparison, with no clone and no shared history —
#        and the reviewer's PoC then had `clean -fdx` delete a planted
#        precious.txt. The lineage proof (shared root commits) is what refuses
#        it, so this arm is run twice: once with no commit at all (rev-list
#        fails), once with a full but UNRELATED history (roots differ).
WT7C="$TMP/wt7c"
mkdir -p "$WT7C"
git -C "$WT7C" init -q
git -C "$WT7C" config user.email t@t
git -C "$WT7C" config user.name t
git -C "$WT7C" config core.autocrlf false
git -C "$WT7C" remote add origin "$REPO"
echo precious > "$WT7C/precious.txt"          # untracked: exactly what clean -fdx eats
if out="$(run "$WT7C" --at "$SHA1" 2>&1)"; then fail "7c: a forged origin must not exit 0"; fi
echo "$out" | grep -q "is not the verification clone of this repository" || fail "7c: no identity diagnostic: $out"
[ "$(cat "$WT7C/precious.txt")" = "precious" ] || fail "7c: PoC reproduced — the forged clone lost untracked files"
[ ! -e "$WT7C.lock" ] || fail "7c: lock leaked on the identity failure"
#        ...same forgery, but now carrying a real history of its own, so the
#        refusal can only come from the root commits differing.
echo unrelated > "$WT7C/unrelated.txt"
git -C "$WT7C" add unrelated.txt
git -C "$WT7C" commit -qm unrelated
[ -n "$(git -C "$WT7C" rev-list --max-parents=0 HEAD)" ] || fail "7c: fixture has no root commit"
if out="$(run "$WT7C" --at "$SHA1" 2>&1)"; then fail "7c: an unrelated history behind a forged origin must not exit 0"; fi
echo "$out" | grep -q "root commit" || fail "7c: refusal did not come from the lineage proof: $out"
[ "$(cat "$WT7C/precious.txt")" = "precious" ] || fail "7c: untracked file destroyed despite the refusal"

# 8. LOCK GUARD. A held lock fails fast, names the recovery gesture, and reaches
#    no checkout at all (nor does it remove someone else's lock).
WT8="$TMP/wt8"
mkdir "$WT8.lock"
if out="$(run "$WT8" --at "$SHA1" 2>&1)"; then fail "8: a held lock must not exit 0"; fi
echo "$out" | grep -q "already in progress" || fail "8: no concurrency diagnostic: $out"
echo "$out" | grep -q "rmdir" || fail "8: no recovery gesture in the message: $out"
[ ! -e "$WT8" ] || fail "8: a clone/checkout happened despite the held lock"
[ -d "$WT8.lock" ] || fail "8: the failing run removed a lock it did not take"
rmdir "$WT8.lock"

# 9. END TO END, real inner script (commit 2), anchored verdict. In this fake
#    repo the host legs cannot pass — pytest finds no tests (exit 5) and
#    core-scripts/run-bash-tests.sh does not exist — so red is guaranteed in seconds,
#    and the assertion is on the ANCHOR: the verdict must carry sha2.
PY=""
for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then
  echo "SKIP arm 9: no python interpreter on PATH"
else
  WT9="$TMP/wt9"
  set +e
  out="$(run "$WT9" --at "$SHA2" 2>&1)"
  rc=$?
  set -e
  [ "$rc" -ne 0 ] || fail "9: the inner run cannot be green in this fixture"
  echo "$out" | grep -q "VERIFY FAILED @ $SHORT2" \
    || fail "9: verdict is not anchored to sha2 ($SHORT2): $out"
fi

# 10. LOCK IDENTITY. Arm 8 proves a held lock refuses; this arm proves the lock
#     CARRIES ITS HOLDER, which is what turns "someone is running" into a
#     decision. Measured twice in one evening at the pilot's expense: a killed
#     run left a lock nobody could attribute, and — worse — a run believed dead
#     was ALIVE because the stop had killed only the shell wrapper while its
#     children kept verifying and kept holding the lock. The reproduction of that
#     second, costlier measurement is arm (a), so it comes first.
#
#     The pid liveness test is `kill -0`, MEASURED under Git-Bash rather than
#     assumed (MINGW64_NT-10.0, bash 5.2.37: a shell builtin speaking MSYS pids,
#     self → 0, exited child → 1, pid 999999 → 1, live `sleep &` → 0), so these
#     arms are not Linux-only fiction.
lock_owner_write() {  # lock_owner_write <lockdir> <pid> <age-seconds>
  local dir="$1" pid="$2" age="$3" now
  now="$(date +%s)"
  mkdir -p "$dir"
  { echo "pid=$pid"
    echo "started=$((now - age))"
    echo "started_at=fixture"
    echo "host=fixture"
  } > "$dir/owner"
}

#     (a) THE REPRODUCTION: the holder is ALIVE. Refuse — and refuse INFORMATIVELY,
#         naming the pid and the age, because "already in progress" alone is what
#         cost a manual `ps` investigation. The age is asserted as a FORMAT
#         (`1h 02m NNs`, zero-padded), not as an exact second: the fixture stamps
#         `started` and the script reads the clock a few seconds later — measured
#         2s of drift on the first run of this arm, which an exact-second
#         assertion turned into a flake. 3725s (1h 02m 05s) sits 55s away from the
#         minute boundary, so the minute field is stable.
WT10A="$TMP/wt10a"
sleep 60 & LIVE_PID=$!
kill -0 "$LIVE_PID" 2>/dev/null || fail "10a: fixture pid $LIVE_PID is not alive — arm is vacuous"
lock_owner_write "$WT10A.lock" "$LIVE_PID" 3725
rm -f "$OUT"
if out="$(run "$WT10A" --at "$SHA1" 2>&1)"; then fail "10a: a lock held by a LIVE pid must not exit 0"; fi
echo "$out" | grep -q "PID $LIVE_PID" || fail "10a: the refusal does not name the holding pid: $out"
echo "$out" | grep -qE 'held for 1h 02m [0-9]{2}s' || fail "10a: the refusal does not say since when (expected 'held for 1h 02m NNs'): $out"
echo "$out" | grep -q "ALIVE" || fail "10a: the refusal does not state the holder is alive: $out"
[ ! -e "$WT10A" ] || fail "10a: a clone/checkout happened despite the live lock"
[ ! -f "$OUT" ] || fail "10a: the inner run executed despite the live lock"
[ -f "$WT10A.lock/owner" ] || fail "10a: the refusing run damaged a lock it does not own"
kill "$LIVE_PID" 2>/dev/null || true
wait "$LIVE_PID" 2>/dev/null || true
rm -f "$WT10A.lock/owner"; rmdir "$WT10A.lock"

#     (b) THE HOLDER IS DEAD → the lock is ABANDONED: reclaim it automatically,
#         announce the reclamation, and RUN. An abandoned lock must never again
#         cost a manual gesture. The fixture pid is proven dead first, so a green
#         here cannot come from a pid that merely looked dead.
WT10B="$TMP/wt10b"
# A dead pid obtained WITHOUT killing anything: a short-lived child is left to
# exit on its own and then reaped. Deliberate — `sleep 60 & kill $!` was the first
# shape here and it made this arm flaky (~70%) through the fork/exec race
# documented on the EXIT trap above: the kill landed before the exec, the victim
# was still bash, and the trap it inherited deleted $TMP mid-suite. No kill, no
# race. Pid reuse would be the other way to make this arm lie, and MSYS pids were
# observed to increase monotonically (878737, 878738, …) rather than being
# recycled immediately, so a just-exited pid stays dead for the few ms that
# matter; the assertion below re-checks it regardless.
sleep 0.2 & DEAD_PID=$!
wait "$DEAD_PID" 2>/dev/null || true
for _ in 1 2 3 4 5 6 7 8 9 10; do
  kill -0 "$DEAD_PID" 2>/dev/null || break
  sleep 0.2
done
if kill -0 "$DEAD_PID" 2>/dev/null; then fail "10b: fixture pid $DEAD_PID is still alive — arm cannot test the dead path"; fi
lock_owner_write "$WT10B.lock" "$DEAD_PID" 42
rm -f "$OUT"
out="$(run "$WT10B" --at "$SHA1" 2>&1)" || fail "10b: an abandoned lock must be reclaimed, not refused: $out"
echo "$out" | grep -q "abandoned by PID $DEAD_PID" || fail "10b: the takeover was not announced with the dead pid: $out"
echo "$out" | grep -qE 'held for [0-9]+s' || fail "10b: the takeover does not say how old the stale lock was: $out"
[ -f "$OUT" ] || fail "10b: the run did not actually start after reclaiming the lock"
[ "$(field HEAD)" = "$SHA1" ] || fail "10b: the reclaiming run did not check out sha1"
[ ! -e "$WT10B.lock" ] || fail "10b: the reclaimed lock was not released at exit"

#     (c) THE LOCK SAYS NOTHING USABLE → manual recovery, and NO silent takeover:
#         stealing a lock we cannot attribute is exactly the shape that loses
#         someone else's work. Three shapes, all of which must refuse.
c_refuse() {  # c_refuse <label> <lockdir>
  local label="$1" w="$2" o
  rm -f "$OUT"
  if o="$(run "$w" --at "$SHA1" 2>&1)"; then fail "10c$label: an unattributable lock must not exit 0"; fi
  echo "$o" | grep -q "already in progress" || fail "10c$label: no concurrency diagnostic: $o"
  echo "$o" | grep -q "names no usable holder" || fail "10c$label: the refusal does not say the holder is unreadable: $o"
  echo "$o" | grep -q "rmdir" || fail "10c$label: no manual recovery gesture: $o"
  if echo "$o" | grep -q "taking it over"; then fail "10c$label: SILENT TAKEOVER of an unreadable lock: $o"; fi
  [ -d "$w.lock" ] || fail "10c$label: the refusing run removed a lock it could not attribute"
  [ ! -f "$OUT" ] || fail "10c$label: the inner run executed despite the refusal"
  [ ! -e "$w" ] || fail "10c$label: a clone/checkout happened despite the refusal"
}
#         (i) a bare lock directory — exactly what a pre-T-00000128 run left.
WT10C="$TMP/wt10c"; mkdir "$WT10C.lock"
c_refuse i "$WT10C"
rmdir "$WT10C.lock"
#         (ii) an owner file whose pid is not a number. This shape matters
#              BECAUSE of a measured `kill -0` property: it also answers non-zero
#              for a non-numeric or empty argument, so a liveness test asked
#              before validating would report "dead" and steal the lock.
WT10C2="$TMP/wt10c2"; lock_owner_write "$WT10C2.lock" "not-a-pid" 10
c_refuse ii "$WT10C2"
rm -f "$WT10C2.lock/owner"; rmdir "$WT10C2.lock"
#         (iii) an owner file with no pid line at all (a truncated write).
WT10C3="$TMP/wt10c3"; mkdir "$WT10C3.lock"; echo "started=$(date +%s)" > "$WT10C3.lock/owner"
c_refuse iii "$WT10C3"
rm -f "$WT10C3.lock/owner"; rmdir "$WT10C3.lock"

#     (d) NORMAL TAKE AND RELEASE. The owner file is observed IN FLIGHT (the stub
#         reads it while the lock is held — arm 3 could only see the after), and
#         the directory must be gone afterwards: a lock that survives a clean run
#         is the leak that started all of this.
WT10D="$TMP/wt10d"
rm -f "$OUT"
out="$(run "$WT10D" --at "$SHA1" 2>&1)" || fail "10d: a free lock must let the run through: $out"
owner="$(field LOCKOWNER)"
[ -n "$owner" ] || fail "10d: no owner file existed while the lock was held"
echo "$owner" | grep -qE 'pid=[0-9]+' || fail "10d: the held lock records no numeric pid: $owner"
echo "$owner" | grep -qE 'started=[0-9]+' || fail "10d: the held lock records no take-time: $owner"
[ ! -e "$WT10D.lock" ] || fail "10d: the lock directory survived a clean run"

# 11. THE PERSISTED VERDICT. `VERIFY OK @ <sha>` used to go to stdout and nowhere
#     else — a return channel that is discarded is a mechanism that does not exist
#     (L-00000136). These arms pin the channel itself: WHERE the stamp lands, WHAT
#     it says, and that a red never leaves a green behind.
#
#     `$REPO/…` and never `$ROOT/…`: `.agents/evals/test_adopting_gate.py` flags a
#     `\bROOT\b` anchored on the real tree followed by a stripped prefix, and this
#     suite travels.
STAMP="$REPO/.agents/state/local/VERIFY_STAMP"
CHRONO="$REPO/.agents/state/local/porte-chrono.tsv"
stamp_field() { sed -n "s/^$1=//p" "$STAMP"; }

#     THE GREEN FIXTURE — a commit whose inner run is the REAL script AND returns 0.
#     Both facts are required and neither is negotiable: the two guards under test
#     (`stamp_write`, `hook_status_line`) live in the shipped script, and the green
#     path is the ONLY one that reaches `stamp_write` at all. Commit 2 is the real
#     script but is guaranteed RED in this fixture (arm 9), and commit 1 is a stub
#     that calls neither function — which is why arm 11a used to prove nothing.
#
#     Two leaf commands stand between the real script and a verdict, and each is
#     satisfied in the CHEAPEST way that keeps the script itself untouched:
#       - `bash core-scripts/run-bash-tests.sh` -> committed here, exits 0
#         (and so is `run-pytest-shards.sh`, the pytest leg since T-00001122);
#       - the interpreter verify.sh resolves -> a SHIM, first on PATH.
#     The shim rather than a real pytest run, DELIBERATELY: a negative control that
#     only bites on boxes carrying a given tool is a negative control with a hole,
#     and this one guards the frozen mode. It costs no dependency and no seconds.
#
#     Built WITHOUT touching HEAD, the index or the working tree (temporary index +
#     commit-tree, the same technique as arm 12 below), then made reachable by a
#     branch so the clone's `fetch` can find it. Arm 13 runs the LIVE fixture tree
#     and MUST stay red, so these files exist only inside this commit.
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/green-bash-tests.sh"
GREEN_BLOB="$(git -C "$REPO" hash-object -w "$TMP/green-bash-tests.sh")"
GIT_INDEX_FILE="$TMP/idxg" git -C "$REPO" read-tree "$SHA2"
GIT_INDEX_FILE="$TMP/idxg" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$GREEN_BLOB,core-scripts/run-bash-tests.sh"
# Le scanner shellcheck est une ÉTAPE de verify.sh depuis le 2026-09-09 : sans
# bouchon ici, l'arbre synthétique ne le porte pas et l'étape sort en 127 —
# « command not found » — alors que l'arm 11a mesure un `--at` VERT. Le même
# blob suffit : ces bouchons ne prouvent rien sur le scanner, ils rendent
# seulement la jambe complète exécutable dans un arbre qui n'est pas le kit.
GIT_INDEX_FILE="$TMP/idxg" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$GREEN_BLOB,.agents/security/shellcheck-scan.sh"
# La jambe python de la porte est un RUNNER depuis T-00001122 : sans ce bouchon l'arbre synthetique ne le
# porte pas et l'arm 11a rend 127 (mesure) au lieu d'un `--at` vert.
GIT_INDEX_FILE="$TMP/idxg" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$GREEN_BLOB,core-scripts/run-pytest-shards.sh"
GREEN_TREE="$(GIT_INDEX_FILE="$TMP/idxg" git -C "$REPO" write-tree)"
SHA_G="$(git -C "$REPO" commit-tree "$GREEN_TREE" -p "$SHA2" -m green)"
git -C "$REPO" branch greenleg "$SHA_G"
SHORT_G="$(git -C "$REPO" rev-parse --short "$SHA_G")"
[ "$(git -C "$REPO" rev-parse HEAD)" = "$SHA2" ] || fail "11: building the green commit moved HEAD"

SHIM="$TMP/shim"
mkdir -p "$SHIM"
printf '#!/usr/bin/env bash\ncase "${1:-}" in --version) echo "Python 3.0.0 (fixture shim)" ;; esac\nexit 0\n' \
  > "$SHIM/python3"
chmod +x "$SHIM/python3"
[ "$("$SHIM/python3" --version)" = "Python 3.0.0 (fixture shim)" ] \
  || fail "11: the interpreter shim does not answer --version — the green arms would be red for the wrong reason"

# `run_green <wtdir> <args...>` — `run`, with the shim FIRST on PATH. The prefix
# assignment is scoped to the `bash` command and never leaks into this shell (a
# `PATH=… run …` on the FUNCTION would persist in bash and poison every later arm).
# `VERIFY_INNER=0` for the reason given on `run` above, and this is the site where
# its absence was actually MEASURED red under the gate.
# MUTATION: drop the prefix and run this file under VERIFY_INNER=1 → arm 11a goes
# red (`a green --at wrote no verdict stamp`), which is verbatim the gate failure
# this fix answers. Caught by arm 15.
run_green() {
  local w="$1"; shift
  PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$w" VERIFY_STUB_OUT="$OUT" \
    bash "$REPO/core-scripts/verify.sh" "$@"
}

#     (a) A GREEN --at WRITES THE STAMP INTO THE LIVE REPOSITORY, not into the
#         clone, AND PRINTS EXACTLY ONE INSTALLATION STATUS LINE. Both claims are
#         claims about the VERIFY_INNER guard, so the inner MUST be the real script:
#         `--at "$SHA_G"`, never `--at "$SHA1"`.
#
#         THE CORRECTION IS WRITTEN OUT RATHER THAN QUIETLY APPLIED, because the
#         previous shape is the exact failure this file is supposed to prevent. This
#         arm ran `--at "$SHA1"`, whose inner is the STUB of commit 1 — it calls
#         neither `stamp_write` nor `hook_status_line`. So the clone-stamp assertion
#         could not fail whatever the guard did, and the status-line count could
#         never reach 2. MEASURED on mutants of the real script: with
#         `hook_status_line` stripped of its guard, `PASS: verify --at (13/13)`,
#         rc=0; with `stamp_write` stripped of its guard, `13/13`, rc=0. The guard
#         at the heart of the frozen mode had NO negative control, while these two
#         lines asserted it had two. A mutation comment is worth exactly what it was
#         measured at, and these are re-measured on the shape below.
#         MUTATION MA: drop `[ "$VERIFY_INNER" = "1" ] && return 0` from
#           `hook_status_line` → the inner answers for the CLONE ("NOT installed")
#           immediately before the outer answers for the live tree → 2 lines, red.
#         MUTATION MB: drop the same line from `stamp_write` → the inner writes a
#           stamp under $WT, where the next run's `clean -fdx` eats it → red.
rm -f "$STAMP"
rm -f "$CHRONO"
rm -f "$OUT"
set +e
out="$(run_green "$WT" --at "$SHA_G" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "11a: a green --at should exit 0: $out"
#         NON-VACUITY, asserted FIRST: the real inner ran all the way to its own
#         verdict. The stub cannot print this line and the outer never prints it
#         under --at, so a green 11a can no longer come from a stubbed inner.
echo "$out" | grep -q "VERIFY OK @ $SHORT_G" \
  || fail "11a: the REAL inner never reached its verdict — neither guard is exercised: $out"
[ -f "$STAMP" ] || fail "11a: a green --at wrote no verdict stamp at $STAMP"
[ -f "$CHRONO" ] || fail "11a: a green --at wrote no gate duration at $CHRONO"
[ "$(wc -l < "$CHRONO")" -eq 1 ] || fail "11a: one outer --at must write exactly one gate duration"
IFS= read -r chrono_row < "$CHRONO"
#         SIX columns since T-01M5PVWF7H: the 6th is the first red step, `-` on a
#         green. Read into its own field — five names would glue `0<TAB>-` into rc.
#         MUTATION: keep the label on a green (`etape="$ETAPE_ROUGE"` whatever rc)
#         → `?` here → red « sixth field ».
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[[ "$chrono_start" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] \
  || fail "11a: gate start is not ISO UTC: $chrono_start"
[[ "$chrono_seconds" =~ ^[0-9]+$ ]] || fail "11a: gate duration is not integer seconds: $chrono_seconds"
[ "$chrono_sha" = "$SHA_G" ] && [ "$chrono_mode" = frozen ] && [ "$chrono_rc" = 0 ] \
  || fail "11a: wrong gate duration fields: $chrono_row"
[ "$chrono_etape" = - ] || fail "11a: a green gate's sixth field is '$chrono_etape', expected '-': $chrono_row"
[ ! -e "$WT/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: the delegated frozen clone wrote a second gate duration"
[ ! -e "$WT/.agents/state/local/VERIFY_STAMP" ] \
  || fail "11a: the stamp was written INSIDE the clone, where the next run's clean -fdx eats it"
#         The FULL 40-hex sha, because the reader compares it to git's `<local-sha>`.
[ "$(stamp_field sha)" = "$SHA_G" ] \
  || fail "11a: stamp sha is '$(stamp_field sha)', expected the full green sha $SHA_G"
[ "$(stamp_field mode)" = "frozen" ] \
  || fail "11a: stamp mode is '$(stamp_field mode)', expected frozen"
[ "$(stamp_field linux)" = "0" ] \
  || fail "11a: stamp linux is '$(stamp_field linux)', expected 0 without --linux"
#         A hook FILE that exists is not a hook that RUNS: the verdict says which.
echo "$out" | grep -q "pre-push guard:" || fail "11a: no installation status line at the verdict: $out"
#         ONE status line, not two. Under --at the inner run would answer for the
#         CLONE — always "NOT installed" — immediately before the outer answers for
#         the live tree; two contradictory lines in one log are worse than none.
[ "$(echo "$out" | grep -c "pre-push guard:")" -eq 1 ] \
  || fail "11a: expected exactly ONE status line, got $(echo "$out" | grep -c "pre-push guard:"): $out"

# The elapsed field must measure a real step. Keep the shipped inner script and
# replace only its bash runner with a one-second fixture in a frozen commit.
printf '#!/usr/bin/env bash\nsleep 1\nexit 0\n' > "$TMP/slow-bash-tests.sh"
SLOW_BLOB="$(git -C "$REPO" hash-object -w "$TMP/slow-bash-tests.sh")"
GIT_INDEX_FILE="$TMP/idxslow" git -C "$REPO" read-tree "$SHA_G"
GIT_INDEX_FILE="$TMP/idxslow" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$SLOW_BLOB,core-scripts/run-bash-tests.sh"
SLOW_TREE="$(GIT_INDEX_FILE="$TMP/idxslow" git -C "$REPO" write-tree)"
SHA_SLOW="$(git -C "$REPO" commit-tree "$SLOW_TREE" -p "$SHA_G" -m slow)"
git -C "$REPO" branch slowleg "$SHA_SLOW"
rm -f "$CHRONO"
out="$(run_green "$TMP/slow-clone" --at "$SHA_SLOW" 2>&1)" \
  || fail "11a: one-second frozen gate should exit 0: $out"
echo "$out" | grep -q "VERIFY OK @" || fail "11a: slow inner never reached its real verdict: $out"
[ -f "$CHRONO" ] && [ "$(wc -l < "$CHRONO")" -eq 1 ] \
  || fail "11a: one-second gate must write exactly one duration"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[[ "$chrono_seconds" =~ ^[0-9]+$ ]] && [ "$chrono_seconds" -ge 1 ] \
  || fail "11a: one-second runner produced gate duration '$chrono_seconds'"
[ "$chrono_sha" = "$SHA_SLOW" ] && [ "$chrono_mode" = frozen ] && [ "$chrono_rc" = 0 ] && [ "$chrono_etape" = - ] \
  || fail "11a: one-second gate duration has wrong fields: $chrono_row"

# The UPPER bound, exact: a frozen clock (`date +%s` reads $FAKE_NOW, every other
# form is the real date) that the inner's bash runner advances by 42 s. The row
# must say 42 — "at least 1" above lets an inflated duration through.
# MUTATION MN8: `elapsed=$((end - CHRONO_START + 1))` → 43 → red.
FAKE_NOW="$TMP/fake-now"
CLOCK_SHIM="$TMP/clock-shim"
mkdir -p "$CLOCK_SHIM"
printf '#!/usr/bin/env bash\nif [ "${1:-}" = "+%%s" ]; then cat "$FAKE_NOW"; exit 0; fi\nexec "%s" "$@"\n' \
  "$(command -v date)" > "$CLOCK_SHIM/date"
chmod +x "$CLOCK_SHIM/date"
printf '#!/usr/bin/env bash\necho 1000000042 > "$FAKE_NOW"\nexit 0\n' > "$TMP/clock-bash-tests.sh"
CLOCK_BLOB="$(git -C "$REPO" hash-object -w "$TMP/clock-bash-tests.sh")"
GIT_INDEX_FILE="$TMP/idxclock" git -C "$REPO" read-tree "$SHA_G"
GIT_INDEX_FILE="$TMP/idxclock" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$CLOCK_BLOB,core-scripts/run-bash-tests.sh"
CLOCK_TREE="$(GIT_INDEX_FILE="$TMP/idxclock" git -C "$REPO" write-tree)"
SHA_CLOCK="$(git -C "$REPO" commit-tree "$CLOCK_TREE" -p "$SHA_G" -m clock)"
git -C "$REPO" branch clockleg "$SHA_CLOCK"
echo 1000000000 > "$FAKE_NOW"
rm -f "$CHRONO"
out="$(PATH="$CLOCK_SHIM:$SHIM:$PATH" FAKE_NOW="$FAKE_NOW" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/clock-clone" \
  VERIFY_STUB_OUT="$OUT" bash "$REPO/core-scripts/verify.sh" --at "$SHA_CLOCK" 2>&1)" \
  || fail "11a: frozen-clock gate should exit 0: $out"
[ "$(cat "$FAKE_NOW")" = 1000000042 ] || fail "11a: the clock runner never ran — the bound proves nothing: $out"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_seconds" = 42 ] || fail "11a: a 42-second frozen-clock gate recorded '$chrono_seconds'"
[ "$chrono_rc" = 0 ] && [ "$chrono_etape" = - ] || fail "11a: frozen-clock gate has wrong rc/sixth fields: $chrono_row"

# WRITER AND READER, ONE ROOT RULE. `reader_rows <dir>` prints how many gate rows
# the READER sees from <dir> — agent_chrono.releve_etapes, the code behind
# `specs.py chrono --etapes`. Every configuration below runs the writer, then
# asks the reader from the SAME directory: 1, or the two disagree on the root.
# MUTATION: racine_commune back to the parent of the common dir → the
# submodule and --separate-git-dir rows below read 0 → red.
# The writer emits SIX columns since T-01M5PVWF7H, so every call below also pins
# the reader's column count. MUTATION: keep `len(champs) != 5` in
# agent_chrono.releve_etapes → « 11a: the reader sees 0 gate row(s) » → red.
KIT_BIN="$HERE/../.agents/bin"
reader_rows() {
  [ -n "$PY" ] && [ -f "$KIT_BIN/agent_chrono.py" ] || { echo skip; return 0; }
  "$PY" -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import agent_chrono as a
p = a.releve_etapes(sys.argv[2])["portes"]; print(p["vertes"] + p["rouges"])' "$KIT_BIN" "$1"
}
reader_says_one() {  # reader_says_one <dir> <label>
  local seen
  seen="$(reader_rows "$1")"
  if [ "$seen" = skip ]; then
    echo "SKIP 11a reader leg ($2): no python interpreter or no .agents/bin/agent_chrono.py beside this suite"
    return 0
  fi
  [ "$seen" = 1 ] || fail "11a: the reader sees $seen gate row(s) from $2, the writer wrote 1 — two root rules"
}

# The same frozen branch from a linked worktree must use git-common-dir's
# parent, which is $REPO, rather than its own checkout or verification clone.
git -C "$REPO" worktree add --detach -q "$TMP/linked" "$SHA2"
rm -f "$CHRONO"
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/linked-clone" \
  bash "$TMP/linked/core-scripts/verify.sh" --at "$SHA_G" 2>&1)" \
  || fail "11a: linked worktree --at should exit 0: $out"
[ -f "$CHRONO" ] || fail "11a: linked worktree did not write under the common git root"
[ "$(wc -l < "$CHRONO")" -eq 1 ] || fail "11a: linked worktree wrote more than one gate duration"
[ ! -e "$TMP/linked/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: linked worktree wrote its own gate duration"
[ ! -e "$TMP/linked-clone/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: linked worktree's delegated clone wrote a gate duration"
reader_says_one "$TMP/linked" "a linked worktree"
reader_says_one "$REPO" "the main worktree"

# A submodule keeps its common git directory below the superproject's .git;
# there the worktree root comes from --show-toplevel, not the directory's parent.
SUPER="$TMP/super"
git -C "$TMP" init -q super
git -C "$SUPER" config user.email t@t
git -C "$SUPER" config user.name t
git -c protocol.file.allow=always -C "$SUPER" submodule add -q "$REPO" sub
SUB_CHRONO="$SUPER/sub/.agents/state/local/porte-chrono.tsv"
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/sub-clone" \
  bash "$SUPER/sub/core-scripts/verify.sh" --at "$SHA1" 2>&1)" \
  || fail "11a: submodule --at should exit 0: $out"
[ -f "$SUB_CHRONO" ] || fail "11a: submodule wrote no gate duration at its worktree root"
[ "$(wc -l < "$SUB_CHRONO")" -eq 1 ] || fail "11a: submodule wrote more than one gate duration"
[ ! -e "$SUPER/.git/modules/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: submodule gate duration went under the superproject's git storage"
[ ! -e "$TMP/sub-clone/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: submodule's delegated clone wrote a gate duration"
reader_says_one "$SUPER/sub" "a submodule"

# A linked worktree OF A SUBMODULE: its common dir sits under the superproject's
# .git/modules, whose core.worktree names the submodule's checkout.
git -C "$SUPER/sub" worktree add --detach -q "$TMP/sublinked" HEAD
rm -f "$SUB_CHRONO"
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/sublinked-clone" \
  bash "$TMP/sublinked/core-scripts/verify.sh" --at "$SHA1" 2>&1)" \
  || fail "11a: submodule linked worktree --at should exit 0: $out"
[ -f "$SUB_CHRONO" ] && [ "$(wc -l < "$SUB_CHRONO")" -eq 1 ] \
  || fail "11a: a submodule's linked worktree did not write one row at the submodule's checkout"
[ ! -e "$SUPER/.git/modules/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: a submodule's linked worktree wrote under the superproject's git storage"
reader_says_one "$TMP/sublinked" "a submodule's linked worktree"

# --separate-git-dir: the main checkout is its own toplevel; a LINKED worktree of
# it also writes at its own toplevel — git records no main worktree there (measured:
# `git worktree list` names the git dir itself), never beside the git dir.
git -C "$TMP" clone -q --separate-git-dir "$TMP/sepgit" "$REPO" sepwt
SEP_CHRONO="$TMP/sepwt/.agents/state/local/porte-chrono.tsv"
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/sep-clone" \
  bash "$TMP/sepwt/core-scripts/verify.sh" --at "$SHA1" 2>&1)" \
  || fail "11a: --separate-git-dir --at should exit 0: $out"
[ -f "$SEP_CHRONO" ] && [ "$(wc -l < "$SEP_CHRONO")" -eq 1 ] \
  || fail "11a: a --separate-git-dir checkout did not write one row at its toplevel"
reader_says_one "$TMP/sepwt" "a --separate-git-dir checkout"
git -C "$TMP/sepwt" worktree add --detach -q "$TMP/seplinked" HEAD
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/seplinked-clone" \
  bash "$TMP/seplinked/core-scripts/verify.sh" --at "$SHA1" 2>&1)" \
  || fail "11a: --separate-git-dir linked worktree --at should exit 0: $out"
[ -f "$TMP/seplinked/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: a --separate-git-dir linked worktree did not write at its own toplevel"
[ ! -e "$TMP/.agents/state/local/porte-chrono.tsv" ] \
  || fail "11a: a --separate-git-dir linked worktree wrote beside the git dir"
reader_says_one "$TMP/seplinked" "a --separate-git-dir linked worktree"

# A delegated invocation records nothing, and a failed append is observational
# only: the same real green --at must still return its green verdict.
rm -f "$CHRONO"
out="$(PATH="$SHIM:$PATH" VERIFY_INNER=1 VERIFY_WORKTREE_DIR="$TMP/inner-clone" \
  bash "$REPO/core-scripts/verify.sh" --at "$SHA_G" 2>&1)" \
  || fail "11a: VERIFY_INNER=1 --at should exit 0: $out"
[ ! -e "$CHRONO" ] || fail "11a: VERIFY_INNER=1 wrote a gate duration"
mkdir "$CHRONO"
out="$(run_green "$WT" --at "$SHA_G" 2>&1)" \
  || fail "11a: unwritable gate duration changed the green verdict: $out"
[ -d "$CHRONO" ] || fail "11a: an unwritable gate duration path was replaced"
rmdir "$CHRONO"
#         A symlinked gate duration is never followed, and the verdict stays green.
#         MUTATION: drop `[ ! -L "$path" ] || return 0` → the target grows a row → red.
printf 'intact\n' > "$TMP/chrono-target"
ln -s "$TMP/chrono-target" "$CHRONO"
out="$(run_green "$WT" --at "$SHA_G" 2>&1)" \
  || fail "11a: a symlinked gate duration changed the green verdict: $out"
[ "$(cat "$TMP/chrono-target")" = intact ] || fail "11a: the gate duration followed a symlink"
rm -f "$CHRONO"

#     (b) --linux IS RECORDED. Without this the container leg could never be told
#         apart from a host-only run, and the hook's requireLinux setting would be
#         reading a field that means nothing.
#         MUTATION: hardcode linux=0 in the write → red.
rm -f "$STAMP"
rm -f "$CHRONO"
rm -f "$OUT"
out="$(run "$WT" --linux --at "$SHA1" 2>&1)" || fail "11b: --linux --at should exit 0: $out"
[ "$(stamp_field linux)" = "1" ] || fail "11b: --linux was not recorded in the stamp"
[ "$(stamp_field mode)" = "frozen" ] || fail "11b: --linux --at is still a frozen verdict"
[ -f "$CHRONO" ] || fail "11b: --linux --at wrote no gate duration"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_sha" = "$SHA1" ] && [ "$chrono_mode" = frozen-linux ] && [ "$chrono_rc" = 0 ] && [ "$chrono_etape" = - ] \
  || fail "11b: --linux --at gate duration has wrong fields: $chrono_row"

# A refusal before the lock and before the first step is no gate observation.
rm -f "$CHRONO"
set +e
out="$(run "$TMP/early-clone" --at no-such-ref-xyz 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "11c: invalid ref should exit 1, got $rc: $out"
[ ! -e "$CHRONO" ] || fail "11c: invalid ref wrote a gate duration before taking the lock"

#     (d) A GATE KILLED MID-RUN RECORDS NOTHING (critic-opus T1). bash runs the
#         EXIT trap on SIGTERM with `$?` = the last COMPLETED command, not 143
#         (measured, bash 5.3: `false; sleep 3` killed -> 1, `X=$(sleep 3)` killed
#         -> 0), so a `--at` killed during its delegated run wrote a `frozen … 0`
#         row at a truncated duration: a false green of the metric. The runner
#         signals that it started, then sleeps; the outer gate is killed then.
#         MUTATION: drop `[ "$CHRONO_INFLIGHT" = "1" ] && return 0` -> a row -> red.
printf '#!/usr/bin/env bash\necho started > "%s"\nsleep 5\nexit 0\n' "$TMP/kill-started" > "$TMP/kill-bash-tests.sh"
KILL_BLOB="$(git -C "$REPO" hash-object -w "$TMP/kill-bash-tests.sh")"
GIT_INDEX_FILE="$TMP/idxkill" git -C "$REPO" read-tree "$SHA_G"
GIT_INDEX_FILE="$TMP/idxkill" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$KILL_BLOB,core-scripts/run-bash-tests.sh"
KILL_TREE="$(GIT_INDEX_FILE="$TMP/idxkill" git -C "$REPO" write-tree)"
SHA_KILL="$(git -C "$REPO" commit-tree "$KILL_TREE" -p "$SHA_G" -m kill)"
git -C "$REPO" branch killleg "$SHA_KILL"
rm -f "$CHRONO" "$TMP/kill-started"
set +e
PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/kill-clone" VERIFY_STUB_OUT="$OUT" \
  bash "$REPO/core-scripts/verify.sh" --at "$SHA_KILL" > "$TMP/kill.out" 2>&1 &
kill_pid=$!
i=0
while [ ! -s "$TMP/kill-started" ] && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
[ -s "$TMP/kill-started" ] || fail "11d: the runner never started, the kill proves nothing: $(cat "$TMP/kill.out")"
#         A GREEN STAMP OF THE SAME SHA DOES NOT SURVIVE THE KILL: the trap's
#         `exit` fires before `rc=$?`, so the red branch never clears it; the trap
#         itself must. Seeded here, while the run is in flight.
#         MUTATION: `trap 'exit 143' TERM` (no stamp_clear) -> stamp left -> red.
mkdir -p "$(dirname "$STAMP")"
printf 'sha=%s\nmode=frozen\nlinux=0\nhost=fixture\nat=fixture\n' "$SHA_KILL" > "$STAMP"
kill -TERM "$kill_pid"
#         THE LOCK IS HELD UNTIL THE INNER RUN RETURNS (T-01M4NP1W0D36YFCS4H2TWN25F2):
#         TERM is trapped once the lock is held, so bash defers it until the
#         foreground step returns, then exits 143 and releases. The runner still
#         sleeps here, 1 s after the kill.
#         MUTATION: drop `trap 'stamp_clear; exit 143' TERM` -> lock freed at once -> red.
sleep 1
[ -d "$TMP/kill-clone.lock" ] || fail "11d: SIGTERM freed the --at lock while the inner run was still verifying"
wait "$kill_pid"
kill_rc=$?
#         The wrapper returns only after its inner run did; this wait is then
#         immediate, and keeps a regressed run's orphan from outliving the arm.
i=0
while ! grep -q "^VERIFY \(OK\|FAILED\) @" "$TMP/kill.out" && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
set -e
[ "$kill_rc" -eq 143 ] || fail "11d: the TERMed gate should exit 143, got $kill_rc: $(cat "$TMP/kill.out")"
[ ! -e "$TMP/kill-clone.lock" ] || fail "11d: the --at lock outlived the TERMed gate"
[ ! -s "$CHRONO" ] || fail "11d: a gate killed by SIGTERM recorded a gate duration: $(cat "$CHRONO")"
[ ! -e "$STAMP" ] || fail "11d: a green stamp of the same SHA survived the TERMed gate: $(cat "$STAMP")"

#         The same under SIGHUP (a closed terminal or session): held, then 129.
#         A HUP ignored on entry (nohup) cannot be trapped: announced, not run.
#         Detected by BEHAVIOUR, not by `trap -p` (empty there under bash 3.2):
#         the probe exits 3 only if its own HUP trap fires (measured 3.2.57 and
#         5.3.15: 3 plain, 0 under nohup).
#         MUTATION: drop `trap 'stamp_clear; exit 129' HUP` -> lock freed at once -> red.
hup_probe_rc=0
bash -c 'trap "exit 3" HUP; kill -HUP $$; exit 0' || hup_probe_rc=$?
if [ "$hup_probe_rc" -ne 3 ]; then
  echo "SKIP: 11d SIGHUP variant — SIGHUP is ignored on entry here (nohup?), the gate cannot trap it"
else
  rm -f "$CHRONO" "$TMP/kill-started"
  set +e
  PATH="$SHIM:$PATH" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/kill-clone" VERIFY_STUB_OUT="$OUT" \
    bash "$REPO/core-scripts/verify.sh" --at "$SHA_KILL" > "$TMP/killhup.out" 2>&1 &
  kill_pid=$!
  i=0
  while [ ! -s "$TMP/kill-started" ] && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
  [ -s "$TMP/kill-started" ] || fail "11d: the runner never started, the HUP proves nothing: $(cat "$TMP/killhup.out")"
  #       MUTATION: `trap 'exit 129' HUP` (no stamp_clear) -> stamp left -> red.
  printf 'sha=%s\nmode=frozen\nlinux=0\nhost=fixture\nat=fixture\n' "$SHA_KILL" > "$STAMP"
  kill -HUP "$kill_pid"
  sleep 1
  [ -d "$TMP/kill-clone.lock" ] || fail "11d: SIGHUP freed the --at lock while the inner run was still verifying"
  wait "$kill_pid"
  kill_rc=$?
  i=0
  while ! grep -q "^VERIFY \(OK\|FAILED\) @" "$TMP/killhup.out" && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
  set -e
  [ "$kill_rc" -eq 129 ] || fail "11d: the HUPed gate should exit 129, got $kill_rc: $(cat "$TMP/killhup.out")"
  [ ! -e "$TMP/kill-clone.lock" ] || fail "11d: the --at lock outlived the HUPed gate"
  [ ! -s "$CHRONO" ] || fail "11d: a gate killed by SIGHUP recorded a gate duration: $(cat "$CHRONO")"
  [ ! -e "$STAMP" ] || fail "11d: a green stamp of the same SHA survived the HUPed gate: $(cat "$STAMP")"
fi

#         A SECOND TERM DURING THE RELEASE IS IGNORED: an `rm` shim slows the
#         owner removal inside the EXIT trap, and a second TERM lands right then.
#         Without `trap '' TERM HUP` in verify_on_exit, the deferred `exit 143`
#         ends the trap between `rm` and `rmdir`: the lock directory stays.
#         MUTATION: drop `trap '' TERM HUP` from verify_on_exit -> lock left -> red.
SLOWRM_SHIM="$TMP/slowrm-shim"
mkdir -p "$SLOWRM_SHIM"
cat > "$SLOWRM_SHIM/rm" <<'SLOWRM'
#!/usr/bin/env bash
case "$*" in
  *kill-clone.lock/owner*)
    : > "$SLOWRM_MARK"
    sleep 2 ;;
esac
exec "$SLOWRM_REAL" "$@"
SLOWRM
chmod +x "$SLOWRM_SHIM/rm"
rm -f "$CHRONO" "$TMP/kill-started" "$TMP/slowrm-mark"
set +e
PATH="$SLOWRM_SHIM:$SHIM:$PATH" SLOWRM_MARK="$TMP/slowrm-mark" SLOWRM_REAL="$(command -v rm)" \
  VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/kill-clone" VERIFY_STUB_OUT="$OUT" \
  bash "$REPO/core-scripts/verify.sh" --at "$SHA_KILL" > "$TMP/kill2.out" 2>&1 &
kill_pid=$!
i=0
while [ ! -s "$TMP/kill-started" ] && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
[ -s "$TMP/kill-started" ] || fail "11d: the runner never started, the second TERM proves nothing: $(cat "$TMP/kill2.out")"
kill -TERM "$kill_pid"
i=0
while [ ! -e "$TMP/slowrm-mark" ] && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
[ -e "$TMP/slowrm-mark" ] || fail "11d: the release never reached the owner removal: $(cat "$TMP/kill2.out")"
kill -TERM "$kill_pid"
wait "$kill_pid"
kill_rc=$?
set -e
[ "$kill_rc" -eq 143 ] || fail "11d: the twice-TERMed gate should exit 143, got $kill_rc: $(cat "$TMP/kill2.out")"
[ ! -e "$TMP/kill-clone.lock" ] || fail "11d: a second SIGTERM during the release left the --at lock behind"

#     (e) THE SAME RULE WITHOUT --at: a LIVE gate killed inside a step records
#         nothing either. Run from a linked worktree at the same commit, so the row
#         would land at $CHRONO (the common root) and the fixture tree is untouched.
#         MUTATION: drop `CHRONO_INFLIGHT=1` from step() -> a `live` row -> red.
git -C "$REPO" worktree add --detach -q "$TMP/killlive" "$SHA_KILL"
rm -f "$CHRONO" "$TMP/kill-started"
set +e
PATH="$SHIM:$PATH" VERIFY_INNER=0 bash "$TMP/killlive/core-scripts/verify.sh" > "$TMP/killlive.out" 2>&1 &
kill_pid=$!
i=0
while [ ! -s "$TMP/kill-started" ] && [ "$i" -lt 600 ]; do sleep 0.1; i=$((i + 1)); done
[ -s "$TMP/kill-started" ] || fail "11e: the runner never started, the kill proves nothing: $(cat "$TMP/killlive.out")"
kill -TERM "$kill_pid"
wait "$kill_pid"
kill_rc=$?
set -e
[ "$kill_rc" -ne 0 ] || fail "11e: the killed live gate exited 0: $(cat "$TMP/killlive.out")"
[ ! -s "$CHRONO" ] || fail "11e: a live gate killed by SIGTERM recorded a gate duration: $(cat "$CHRONO")"

# 12. A RED --at REMOVES A PRE-SEEDED GREEN. THIS ARM EXISTS BECAUSE THE ASYMMETRY
#     WAS MEASURED, not imagined: the --at branch ends at `exit "$rc"` and never
#     reaches the live-tree cleanup, so a red run used to leave yesterday's green
#     stamp on disk — and the hook would have waved the push through.
#     The claim this pins is narrow on purpose: A STALE GREEN DOES NOT SURVIVE A
#     RED ON THE SAME PATH. It is not "a stale green cannot exist".
#     MUTATION: delete the `stamp_clear` in the rc≠0 branch → red.
#
#     The red inner is a commit built WITHOUT touching HEAD, the index or the
#     working tree (a temporary index + commit-tree), then made reachable by a
#     branch so the clone's `fetch` can find it. Cheaper and far more deterministic
#     than making the real script go red: measured 0s.
printf '#!/usr/bin/env bash\necho "RED STUB"\nexit 1\n' > "$TMP/red-stub.sh"
RED_BLOB="$(git -C "$REPO" hash-object -w "$TMP/red-stub.sh")"
GIT_INDEX_FILE="$TMP/idx" git -C "$REPO" read-tree "$SHA2"
GIT_INDEX_FILE="$TMP/idx" git -C "$REPO" update-index --add --cacheinfo "100755,$RED_BLOB,core-scripts/verify.sh"
RED_TREE="$(GIT_INDEX_FILE="$TMP/idx" git -C "$REPO" write-tree)"
SHA3="$(git -C "$REPO" commit-tree "$RED_TREE" -p "$SHA2" -m red)"
git -C "$REPO" branch redleg "$SHA3"
[ "$(git -C "$REPO" rev-parse HEAD)" = "$SHA2" ] || fail "12: building the red commit moved HEAD"

printf 'sha=%s\nmode=frozen\nlinux=1\nhost=fixture\nat=fixture\n' "$SHA1" > "$STAMP"
[ -f "$STAMP" ] || fail "12: the fixture stamp was not seeded — the arm would prove nothing"
WT12="$TMP/wt12"
rm -f "$CHRONO"
#     Launched under ETAPE_ROUGE=leurre, written out rather than through `run` so
#     the poison is EXPORTED to the process (pins identical to `run`). The red stub
#     notes no step, so the 6th column must be `?` — never the inherited value.
#     MUTATION: `ETAPE_ROUGE="${ETAPE_ROUGE:-}"` at the head of verify.sh → the
#     column says `leurre` → red « sixth field ». MUTATION: write `-` whatever rc
#     → red too.
set +e
out="$(ETAPE_ROUGE=leurre VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$WT12" VERIFY_STUB_OUT="$OUT" \
  bash "$REPO/core-scripts/verify.sh" --at "$SHA3" 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "12: the red inner must make --at exit non-zero: $out"
[ ! -e "$STAMP" ] || fail "12: A STALE GREEN SURVIVED A RED --at — stamp still on disk: $(cat "$STAMP")"
[ -f "$CHRONO" ] || fail "12: a red --at wrote no gate duration"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_sha" = "$SHA3" ] && [ "$chrono_mode" = frozen ] && [ "$chrono_rc" = "$rc" ] \
  || fail "12: red --at gate duration has wrong fields: $chrono_row"
[ "$chrono_etape" = "?" ] \
  || fail "12: sixth field '$chrono_etape', expected '?' (a red with no step noted, ETAPE_ROUGE=leurre inherited): $chrono_row"

# 12b. THE CLONE'S FILE IS A TRUST BOUNDARY: written by the code of the frozen SHA,
#      read by the live gate. A stub inner seeds `.agents/state/local/ETAPE_ROUGE`
#      three hostile ways ($ER_MODE crosses to the inner through the environment):
#        tab  : `a<TAB>b<LF>c` → `?`, the row keeps exactly six fields, one line.
#               MUTATION: drop the control-character test of chrono_write → red.
#        link : a symlink to a file holding `suivi` → `?`.
#               MUTATION: drop `[ ! -L "$_etape_fichier" ]` of the reread → red.
#        long : 300 bytes → the column holds the first 200.
#               MUTATION: `head -c 200` → `cat` → red.
cat > "$TMP/er-stub.sh" <<'ERSTUB'
#!/usr/bin/env bash
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.agents/state/local"
mkdir -p "$R"
case "${ER_MODE:-}" in
  tab)
    printf 'a\tb\nc' > "$R/ETAPE_ROUGE" ;;
  link)
    printf 'suivi' > "$R/cible"
    ln -s "$R/cible" "$R/ETAPE_ROUGE" ;;
  long)
    printf '%0300d' 0 > "$R/ETAPE_ROUGE" ;;
esac
exit 1
ERSTUB
ER_BLOB="$(git -C "$REPO" hash-object -w "$TMP/er-stub.sh")"
GIT_INDEX_FILE="$TMP/idxer" git -C "$REPO" read-tree "$SHA2"
GIT_INDEX_FILE="$TMP/idxer" git -C "$REPO" update-index --add --cacheinfo "100755,$ER_BLOB,core-scripts/verify.sh"
ER_TREE="$(GIT_INDEX_FILE="$TMP/idxer" git -C "$REPO" write-tree)"
SHA_ER="$(git -C "$REPO" commit-tree "$ER_TREE" -p "$SHA2" -m etape-rouge)"
git -C "$REPO" branch erleg "$SHA_ER"
er_run() {  # er_run <mode> — prints the journal's single row, sixth field after a tab
  rm -f "$CHRONO"
  set +e
  ER_MODE="$1" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$TMP/wt12b" VERIFY_STUB_OUT="$OUT" \
    bash "$REPO/core-scripts/verify.sh" --at "$SHA_ER" > "$TMP/er.out" 2>&1
  er_rc=$?
  set -e
  [ "$er_rc" -ne 0 ] || fail "12b ($1): the red stub inner must make --at exit non-zero: $(cat "$TMP/er.out")"
  [ -f "$CHRONO" ] && [ "$(wc -l < "$CHRONO")" -eq 1 ] \
    || fail "12b ($1): expected exactly one journal line: $(cat "$CHRONO" 2>/dev/null)"
  [ "$(awk -F'\t' '{print NF}' "$CHRONO")" = 6 ] \
    || fail "12b ($1): the row does not have six fields: $(cat "$CHRONO")"
}
er_run tab
[ "$(cut -f6 "$CHRONO")" = "?" ] || fail "12b (tab): sixth field '$(cut -f6 "$CHRONO")', expected '?'"
er_run link
[ "$(cut -f6 "$CHRONO")" = "?" ] || fail "12b (link): sixth field '$(cut -f6 "$CHRONO")', expected '?' — the symlink was followed"
er_run long
[ "$(cut -f6 "$CHRONO")" = "$(printf '%0200d' 0)" ] \
  || fail "12b (long): sixth field is $(cut -f6 "$CHRONO" | wc -c | tr -d ' ') bytes with its newline, expected the first 200"

# 13. THE LIVE PATH CLEARS TOO, at its own verdict site. Arm 12 covers the frozen
#     path only; the two sites are different code and only one of them was ever
#     wrong. A run WITHOUT --at measures the live tree, so this one is executed
#     bare, in the fixture, where the gate is red in 0s (no pytest scope, no
#     run-bash-tests.sh).
#     MUTATION: delete the `stamp_clear` in the `failed -ne 0` branch → red.
#     The third and last launch site, bare rather than through `run`, and it needs
#     the same `VERIFY_INNER=0` for the same reason — MUTATION: drop it and run
#     this file under VERIFY_INNER=1 → `stamp_clear` returns early and this arm
#     goes red on `a red LIVE run left the stale green stamp on disk`. Arm 15.
printf 'sha=%s\nmode=frozen\nlinux=1\nhost=fixture\nat=fixture\n' "$SHA1" > "$STAMP"
[ -f "$STAMP" ] || fail "13: the fixture stamp was not seeded"
rm -f "$CHRONO"
set +e
out="$(cd "$REPO" && VERIFY_INNER=0 bash "$REPO/core-scripts/verify.sh" 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "13: the live gate cannot be green in this fixture: $out"
[ ! -e "$STAMP" ] || fail "13: a red LIVE run left the stale green stamp on disk: $(cat "$STAMP")"
echo "$out" | grep -q "pre-push guard:" || fail "13: the live verdict carries no status line: $out"
[ -f "$CHRONO" ] || fail "13: a live gate wrote no gate duration"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_sha" = "$SHA2" ] && [ "$chrono_mode" = live ] && [ "$chrono_rc" = "$rc" ] \
  || fail "13: live gate duration has wrong fields: $chrono_row"
#         The live red names its step: the fixture has no runner, the first step fails.
[ "$chrono_etape" = "python -m pytest (CI scope, shards)" ] \
  || fail "13: sixth field '$chrono_etape', expected the first red step: $chrono_row"

# 13b. THE FIRST LABEL, AND ONLY IT: CADRE_GATE_FAIL_FAST=0 plays the three steps,
#      all red in this fixture (no runner, no scanner). Launched like 13, with
#      VERIFY_INNER=0 pinned (the nested run of arm 15 inherits VERIFY_INNER=1, and
#      chrono_write would stay silent), and under ETAPE_ROUGE=leurre: the live path
#      keeps the first label « if empty », so an inherited value would win.
#      MUTATION: `ETAPE_ROUGE="$1"` without the empty test in noter_rouge → the
#      label of the shellcheck step → red. MUTATION: `ETAPE_ROUGE="${ETAPE_ROUGE:-}"` at the
#      head of verify.sh → `leurre` → red. MUTATION: drop VERIFY_INNER=0 below →
#      nested 13b red (arm 15).
rm -f "$CHRONO"
set +e
out="$(cd "$REPO" && ETAPE_ROUGE=leurre VERIFY_INNER=0 CADRE_GATE_FAIL_FAST=0 bash "$REPO/core-scripts/verify.sh" 2>&1)"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "13b: the live gate cannot be green in this fixture: $out"
[ "$(echo "$out" | grep -c -e '^--- FAIL ')" -eq 3 ] || fail "13b: CADRE_GATE_FAIL_FAST=0 did not play three red steps: $out"
[ -f "$CHRONO" ] || fail "13b: a live gate wrote no gate duration"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_etape" = "python -m pytest (CI scope, shards)" ] \
  || fail "13b: sixth field '$chrono_etape', expected the FIRST red step only: $chrono_row"

# 14. THE CHANNEL, END TO END: verify.sh WRITES a real stamp, the REAL hook READS
#     it, and the push is ALLOWED. Everything above this line tests one end of that
#     channel; `.githooks/pre-push.test.sh` tests the other and fabricates every
#     stamp it reads with its own `stamp()` helper. Nothing joined them — so a field
#     renamed in `stamp_write`, a line reordered, or a trailing \r would have kept
#     BOTH suites green while the installed hook refused every push in the
#     repository. A mechanism whose return channel is never exercised end to end
#     does not exist (L-00000136); this arm is that lesson applied to its own bench
#     rather than quoted by it.
#     THE TWO MUTATIONS BELOW ARE THE ONES THIS ARM AND ONLY THIS ARM CATCHES, and
#     they were CHOSEN BY MEASUREMENT rather than by plausibility. The obvious
#     candidate — rename `sha=` to `commit=` in `stamp_write` — is NOT one of them:
#     measured, it dies at arm 11a (`stamp sha is '', expected the full green sha`)
#     and never reaches here, so naming it would have credited this arm with a kill
#     arm 11a makes. What 11a cannot see is a DIVERGENCE between the two ends,
#     because 11a re-implements the reader with its own `sed`.
#     MUTATION D (the divergence, and the reason this arm exists) — the hook starts
#       REQUIRING a field `stamp_write` does not emit, and `.githooks/pre-push.test.sh`
#       is updated in the same edit to fabricate it. That is the natural,
#       self-consistent change, and it is invisible everywhere else. MEASURED:
#         .githooks/pre-push.test.sh  ->  PASS: pre-push (11/11)
#         core-scripts/verify.test.sh      ->  FAIL: 14a: THE CHANNEL IS BROKEN — a stamp
#           verify.sh wrote for 32663c4b… did not let 32663c4b… through: PUSH
#           REFUSED (refs/heads/greenleg): the verdict stamp is MALFORMED
#       Both benches green, every push in the repository refused: that is precisely
#       the state this arm exists to make impossible.
#     MUTATION S — delete the "installed" branch of `hook_status_line`. MEASURED:
#       `FAIL: 14a: the verdict does not report the hook as installed`, while
#       `.githooks/pre-push.test.sh` stays at 11/11. This arm is the ONLY place that
#       branch is exercised: arms 11 and 13 both run in a repo where the hook is not
#       installed, so they can only ever reach the "NOT installed" side.
E2E_REMOTE="$TMP/e2e-remote.git"
git init -q --bare "$E2E_REMOTE"
git -C "$REPO" remote add e2e "$E2E_REMOTE"
#     The DOCUMENTED installation gesture, executed rather than described — the same
#     one `.githooks/pre-push.test.sh` performs, so the two ends are wired alike.
HOOK_SRC="$HERE/../.githooks/pre-push"
[ -f "$HOOK_SRC" ] || fail "14: $HOOK_SRC not found — the reader of this channel does not exist"
mkdir -p "$REPO/.githooks"
cp "$HOOK_SRC" "$REPO/.githooks/pre-push"
chmod +x "$REPO/.githooks/pre-push"
git -C "$REPO" config core.hooksPath .githooks

#     (a) THE WRITER AND THE READER AGREE. Nothing in this arm writes the stamp:
#         it is produced by `stamp_write` inside a real green `--at`, then handed
#         to the hook exactly as a developer's push would hand it over.
rm -f "$STAMP"
WT14="$TMP/wt14"
set +e
out="$(run_green "$WT14" --at "$SHA_G" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "14a: the green --at that feeds this channel failed: $out"
[ -f "$STAMP" ] || fail "14a: no stamp was produced — the hook has nothing to read"
[ "$(stamp_field sha)" = "$SHA_G" ] \
  || fail "14a: the produced stamp covers '$(stamp_field sha)', not the pushed sha $SHA_G"
#         The "installed" branch of the status line, exercised here for the first
#         time: arms 11 and 13 can only ever reach the "NOT installed" branch.
echo "$out" | grep -q "pre-push guard: installed (core.hooksPath=.githooks)" \
  || fail "14a: the verdict does not report the hook as installed: $out"
set +e
PUSH_OUT="$(git -C "$REPO" push e2e greenleg 2>&1)"
PUSH_RC=$?
set -e
[ "$PUSH_RC" -eq 0 ] \
  || fail "14a: THE CHANNEL IS BROKEN — a stamp verify.sh wrote for $SHA_G did not let $SHA_G through: $PUSH_OUT"
[ "$(git -C "$E2E_REMOTE" rev-parse refs/heads/greenleg)" = "$SHA_G" ] \
  || fail "14a: the accepted push never reached the remote"
#         The hook did more than exit 0: it PARSED the fields of a real stamp. This
#         line is what a renamed `linux=` would take down.
echo "$PUSH_OUT" | grep -q "container leg: NOT covered" \
  || fail "14a: the hook never announced linux=0 — it did not read the field: $PUSH_OUT"

#     (b) AND THE HOOK IS ACTUALLY RUNNING HERE. Without this control (a) would be
#         green on any box where `core.hooksPath` is not honoured at all — the push
#         would simply succeed, unexamined, and the channel would be declared open
#         on the strength of nothing. Same repo, same stamp, a sha it does NOT
#         cover: refused, and the refusal names it.
set +e
PUSH_OUT="$(git -C "$REPO" push e2e redleg 2>&1)"
PUSH_RC=$?
set -e
[ "$PUSH_RC" -ne 0 ] \
  || fail "14b: a sha the stamp does not cover was pushed — the hook is not running, so 14a proved nothing: $PUSH_OUT"
echo "$PUSH_OUT" | grep -q "$SHA3" || fail "14b: the refusal does not name the sha being pushed: $PUSH_OUT"
if git -C "$E2E_REMOTE" rev-parse --verify --quiet refs/heads/redleg >/dev/null; then
  fail "14b: the refused push reached the remote anyway"
fi

# 18. FAIL-FAST AT THE SCALE OF verify.sh's OWN STEPS (T-01M4WTYT8M, décision
#     pilote S-01M4WTZ1QZQJZZNYRC5YA67AZW). Once a step is red, the later steps
#     and the --linux leg are NOT RUN, and said so; CADRE_GATE_FAIL_FAST=0 plays
#     everything. THE CLAIM IS NARROW: only the time after the first red changes —
#     the verdict, its anchor and the stamp clearing are those of a red, in BOTH
#     modes. Numbered 18 but PLACED BEFORE ARM 15, so that the nested run carries
#     it under the poisons the gate hands this bench (VERIFY_INNER=1, and the two
#     settings this arm is about).
#
#     THE FIXTURE, on the model of `greenleg`: the SHIPPED verify.sh, its leaves
#     stubbed, built as a commit of its own WITHOUT touching HEAD, the index or the
#     working tree (arms 3 and 13 depend on the live fixture staying as it is):
#       - run-pytest-shards.sh is RED (rc 1) — the FIRST step fails; it also writes
#         the CADRE_GATE_DURATIONS_DIR it received into $FF_TRACE (arm d);
#       - run-bash-tests.sh creates $FF_MARK — "did a step run after the red?";
#       - shellcheck-scan.sh is green (else CADRE_GATE_FAIL_FAST=0 adds a 127);
#       - .github/workflows/ci.yml, MINIMAL: the --linux leg EXTRACTS three things
#         from it (hash-pinned requirements, apt list, python-version) and exits
#         FATAL without them, BEFORE docker. Without this file arm (b) could never
#         reach docker, and (a)'s "DMARK absent" would be vacuous (critique C2).
#     `docker` is a stub FIRST on PATH, never in the tree: `run` writes its
#     arguments, one per line, into $FF_DMARK (arm b reads the `-e` it receives).
#     A stub rather than the real client for the reason arm 16 gives: this suite is
#     replayed INSIDE the --linux container, where docker does not exist.
#     COST, measured 2026-10-14 on the whole file: 12.9 s → 16.5 s (arm 18 runs
#     twice, top level and nested).
cat > "$TMP/ff-pytest.sh" <<'FFPY'
#!/usr/bin/env bash
echo "${CADRE_GATE_DURATIONS_DIR:-ABSENT}" > "$FF_TRACE"
exit 1
FFPY
cat > "$TMP/ff-bash-tests.sh" <<'FFSH'
#!/usr/bin/env bash
: > "$FF_MARK"
exit 0
FFSH
cat > "$TMP/ff-ci.yml" <<'FFCI'
name: fixture of verify.test.sh arm 18 - the three lines the --linux leg extracts
jobs:
  tests:
    steps:
      - with:
          python-version: "3.12"
      - run: |
          sudo apt-get install -y jq
          pytest==8.0.0 --hash=sha256:0000
FFCI
FF_PY_BLOB="$(git -C "$REPO" hash-object -w "$TMP/ff-pytest.sh")"
FF_SH_BLOB="$(git -C "$REPO" hash-object -w "$TMP/ff-bash-tests.sh")"
FF_CI_BLOB="$(git -C "$REPO" hash-object -w "$TMP/ff-ci.yml")"
GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" read-tree "$SHA2"
GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$FF_PY_BLOB,core-scripts/run-pytest-shards.sh"
GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$FF_SH_BLOB,core-scripts/run-bash-tests.sh"
GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" update-index --add \
  --cacheinfo "100755,$GREEN_BLOB,.agents/security/shellcheck-scan.sh"
GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" update-index --add \
  --cacheinfo "100644,$FF_CI_BLOB,.github/workflows/ci.yml"
FF_TREE="$(GIT_INDEX_FILE="$TMP/idxff" git -C "$REPO" write-tree)"
SHA_FF="$(git -C "$REPO" commit-tree "$FF_TREE" -p "$SHA2" -m fail-fast)"
git -C "$REPO" branch ffleg "$SHA_FF"
SHORT_FF="$(git -C "$REPO" rev-parse --short "$SHA_FF")"
[ "$(git -C "$REPO" rev-parse HEAD)" = "$SHA2" ] || fail "18: building the fail-fast commit moved HEAD"

FF_DSHIM="$TMP/ff-dshim"
mkdir -p "$FF_DSHIM"
cat > "$FF_DSHIM/docker" <<'FFDK'
#!/usr/bin/env bash
case "${1:-}" in
  run)
    printf '%s\n' "$@" > "$FF_DMARK" ;;
esac
exit 0
FFDK
chmod +x "$FF_DSHIM/docker"
FF_MARK="$TMP/ff-mark"
FF_DMARK="$TMP/ff-dmark"
FF_TRACE="$TMP/ff-trace"
#     The live root of the fixture, as verify.sh computes it (`cd … && pwd`): the
#     table must land in the LIVE tree, never in the clone `clean -fdx` wipes.
FF_LIVE_DURATIONS="$(cd "$REPO" && pwd)/.agents/state/local/porte-durees"

# `ff_run <wtdir> <CADRE_GATE_FAIL_FAST, empty = the default> <args...>` — the
# FOURTH launch site. Every variable comes from the bench, none is inherited:
# VERIFY_INNER=0 for the reason given on `run`; the two settings under test are
# pinned too — an EMPTY value takes verify.sh's `:-` default, which is exactly
# the default under test.
# MUTATIONS, measured 2026-10-14 (the first three red in the NESTED run of arm 15
# only, top level green):
#   - drop `VERIFY_INNER=0`              → nested 18a: "A STALE GREEN SURVIVED";
#   - empty `ff` INHERITS instead of taking the default
#     (`CADRE_GATE_FAIL_FAST="${ff:-${CADRE_GATE_FAIL_FAST:-}}"`)
#                                        → nested 18a: "a step RAN after the red";
#   - drop `CADRE_GATE_DURATIONS_DIR=""` → nested 18d: the poison reached the stub;
#   - drop `CADRE_GATE_FAIL_FAST="$ff"` outright → already red at TOP level, 18b
#     ("must play every step"): the value under test no longer arrives at all.
ff_run() {
  local w="$1" ff="$2"; shift 2
  PATH="$FF_DSHIM:$SHIM:$PATH" VERIFY_INNER=0 CADRE_GATE_FAIL_FAST="$ff" CADRE_GATE_DURATIONS_DIR="" \
    FF_MARK="$FF_MARK" FF_DMARK="$FF_DMARK" FF_TRACE="$FF_TRACE" \
    VERIFY_WORKTREE_DIR="$w" VERIFY_STUB_OUT="$OUT" bash "$REPO/core-scripts/verify.sh" "$@"
}
FF_WT="$TMP/wt18"

#     (a) THE DEFAULT, under `--at` WITH `--linux`: the first step is red, so the
#         two host steps after it and the container leg are NOT RUN — and the
#         verdict is the red one, anchored, the pre-seeded green stamp ERASED.
#         MUTATION M1: remove the guard at the head of `step()` → red ("a step RAN").
#         MUTATION M2: remove the --linux `elif` guard → red ("docker run was called").
printf 'sha=%s\nmode=frozen\nlinux=1\nhost=fixture\nat=fixture\n' "$SHA1" > "$STAMP"
[ -f "$STAMP" ] || fail "18a: the fixture stamp was not seeded — the arm would prove nothing"
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE"
rm -f "$CHRONO"
set +e
out="$(ff_run "$FF_WT" "" --linux --at "$SHA_FF" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "18a: a red first step must make --at exit 1, got $rc: $out"
#         NON-VACUITY first: the red step really ran, in the real inner.
echo "$out" | grep -qF -e "--- FAIL python -m pytest (CI scope, shards)" \
  || fail "18a: the first step never failed — the arm measures nothing: $out"
[ ! -e "$FF_MARK" ] || fail "18a: a step RAN after the red — the fail-fast of step() is not applied: $out"
[ ! -e "$FF_DMARK" ] || fail "18a: docker run was called after a red host leg — the --linux leg ignores the fail-fast: $out"
echo "$out" | grep -qF -e "--- NOT RUN bash core-scripts/run-bash-tests.sh" \
  || fail "18a: the skipped step is not named NOT RUN: $out"
echo "$out" | grep -qF -e "--- NOT RUN bash .agents/security/shellcheck-scan.sh" \
  || fail "18a: the third step is not named NOT RUN: $out"
echo "$out" | grep -qF -e "=== linux replay NOT RUN" \
  || fail "18a: the container leg is not named NOT RUN: $out"
echo "$out" | grep -qF -e "NOT RUN (fail-fast=prio): 3 step(s) — the failure list is NOT complete" \
  || fail "18a: no count line (default prio, 2 steps + the --linux leg): $out"
echo "$out" | grep -q "VERIFY FAILED @ $SHORT_FF" \
  || fail "18a: the verdict is not the red one anchored to $SHORT_FF: $out"
echo "$out" | sed -n '/^NOT RUN (fail-fast=/,$p' | grep -q "VERIFY FAILED @ $SHORT_FF" \
  || fail "18a: the count line must come BEFORE the verdict line: $out"
[ ! -e "$STAMP" ] || fail "18a: A STALE GREEN SURVIVED a fail-fast red --at: $(cat "$STAMP")"

#     (f) THE LABEL CROSSES --at: the REAL inner noted its first red step and
#         wrote it to the clone's file; the outer reads it into the 6th column.
#         MUTATION: the outer no longer rereads `$WT/.agents/state/local/ETAPE_ROUGE`
#         → `?` → red. MUTATION: the inner no longer writes it → red.
[ -f "$CHRONO" ] && [ "$(wc -l < "$CHRONO")" -eq 1 ] \
  || fail "18f: a red --at must write exactly one journal line: $(cat "$CHRONO" 2>/dev/null)"
IFS= read -r chrono_row < "$CHRONO"
IFS=$'\t' read -r chrono_start chrono_seconds chrono_sha chrono_mode chrono_rc chrono_etape <<< "$chrono_row"
[ "$chrono_mode" = frozen-linux ] && [ "$chrono_rc" = 1 ] \
  && [ "$chrono_etape" = "python -m pytest (CI scope, shards)" ] \
  || fail "18f: the inner's first red step did not reach the journal across --at: $chrono_row"

#     (d) THE DURATIONS DIR the outer hands the inner names the LIVE fixture tree.
#         MUTATION M4: remove the `CADRE_GATE_DURATIONS_DIR=` prefix of the inner
#         call → the stub sees nothing ("ABSENT") → red.
[ -f "$FF_TRACE" ] || fail "18d: the pytest stub never ran — (d) proves nothing"
[ "$(cat "$FF_TRACE")" = "$FF_LIVE_DURATIONS" ] \
  || fail "18d: the inner received CADRE_GATE_DURATIONS_DIR='$(cat "$FF_TRACE")', expected the LIVE tree's $FF_LIVE_DURATIONS"

#     (b) CADRE_GATE_FAIL_FAST=0 PLAYS EVERYTHING, docker included — and the
#         verdict is the SAME red: only the stopping changed, never the verdict.
printf 'sha=%s\nmode=frozen\nlinux=1\nhost=fixture\nat=fixture\n' "$SHA1" > "$STAMP"
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE"
set +e
out="$(ff_run "$FF_WT" 0 --linux --at "$SHA_FF" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "18b: CADRE_GATE_FAIL_FAST=0 must keep the red verdict (rc 1), got $rc: $out"
[ -e "$FF_MARK" ] || fail "18b: CADRE_GATE_FAIL_FAST=0 must play every step — run-bash-tests.sh did not run: $out"
[ -e "$FF_DMARK" ] || fail "18b: CADRE_GATE_FAIL_FAST=0 must play the --linux leg — docker run was not called: $out"
#         The container gets its OWN durations dir, outside the /repo mount: the
#         runners' default would write Linux durations, as root, into the mounted
#         tree — the LIVE table under a bare --linux.
#         MUTATION M5: drop `-e CADRE_GATE_DURATIONS_DIR=…` from `docker run` → red.
ff_dur="$(grep -A1 -x -e '-e' "$FF_DMARK" | sed -n 's/^CADRE_GATE_DURATIONS_DIR=//p')"
case "$ff_dur" in
  ''|/repo|/repo/*)
    fail "18b: docker run hands the container no durations dir outside /repo (got '$ff_dur'): $(tr '\n' ' ' < "$FF_DMARK")" ;;
  /*)
    : ;;
  *)
    fail "18b: the container durations dir is not absolute: '$ff_dur'" ;;
esac
if echo "$out" | grep -qF -e "NOT RUN"; then
  fail "18b: CADRE_GATE_FAIL_FAST=0 still skipped something: $out"
fi
echo "$out" | grep -q "VERIFY FAILED @ $SHORT_FF" \
  || fail "18b: the verdict line changed with the setting: $out"
[ ! -e "$STAMP" ] || fail "18b: A STALE GREEN SURVIVED a red --at under CADRE_GATE_FAIL_FAST=0: $(cat "$STAMP")"

#     (g) A FATAL `exit 1` AFTER A RED STEP KEEPS ITS LABEL: the commit is the
#         fail-fast one WITHOUT the minimal ci.yml, so under CADRE_GATE_FAIL_FAST=0
#         the inner notes the red pytest step, then dies on the FATAL extraction
#         guard of the --linux leg before docker — never reaching the final
#         verdict. The label was written by `noter_rouge` itself, so it survives.
#         MUTATION: write ETAPE_ROUGE at the final verdict only (the code before
#         this arm) → `?` → red.
GIT_INDEX_FILE="$TMP/idxft" git -C "$REPO" read-tree "$SHA_FF"
GIT_INDEX_FILE="$TMP/idxft" git -C "$REPO" update-index --force-remove .github/workflows/ci.yml
FT_TREE="$(GIT_INDEX_FILE="$TMP/idxft" git -C "$REPO" write-tree)"
SHA_FT="$(git -C "$REPO" commit-tree "$FT_TREE" -p "$SHA2" -m fatal-after-red)"
git -C "$REPO" branch fatalleg "$SHA_FT"
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE" "$CHRONO"
set +e
out="$(ff_run "$FF_WT" 0 --linux --at "$SHA_FT" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "18g: a FATAL exit after a red step must make --at exit 1, got $rc: $out"
echo "$out" | grep -qF -e "FATAL: could not extract the hash-pinned requirements" \
  || fail "18g: the inner never reached the FATAL guard — the arm measures nothing: $out"
[ ! -e "$FF_DMARK" ] || fail "18g: docker run was called despite the FATAL guard: $out"
[ "$(cut -f6 "$CHRONO")" = "python -m pytest (CI scope, shards)" ] \
  || fail "18g: sixth field '$(cut -f6 "$CHRONO")' after a FATAL exit, expected the red step noted before it"

#     (h) THE CONTAINER LEG NAMES ITSELF: every host step green (the green blobs
#         plus the minimal ci.yml), a docker stub whose `run` FAILS, under
#         CADRE_GATE_FAIL_FAST=0 — the first red is the container leg.
#         MUTATION: drop `noter_rouge "linux replay"` from the FAIL branch of the
#         container leg → `?` → red.
GIT_INDEX_FILE="$TMP/idxdk" git -C "$REPO" read-tree "$SHA_G"
GIT_INDEX_FILE="$TMP/idxdk" git -C "$REPO" update-index --add \
  --cacheinfo "100644,$FF_CI_BLOB,.github/workflows/ci.yml"
DK_TREE="$(GIT_INDEX_FILE="$TMP/idxdk" git -C "$REPO" write-tree)"
SHA_DK="$(git -C "$REPO" commit-tree "$DK_TREE" -p "$SHA2" -m docker-red)"
git -C "$REPO" branch dockerleg "$SHA_DK"
DK_SHIM="$TMP/dk-shim"
mkdir -p "$DK_SHIM"
printf '#!/usr/bin/env bash\ncase "${1:-}" in run) exit 1 ;; esac\nexit 0\n' > "$DK_SHIM/docker"
chmod +x "$DK_SHIM/docker"
rm -f "$CHRONO"
set +e
out="$(PATH="$DK_SHIM:$SHIM:$PATH" VERIFY_INNER=0 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_DURATIONS_DIR="" \
  VERIFY_WORKTREE_DIR="$FF_WT" VERIFY_STUB_OUT="$OUT" bash "$REPO/core-scripts/verify.sh" --linux --at "$SHA_DK" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "18h: a red container leg must make --at exit 1, got $rc: $out"
echo "$out" | grep -qF -e "--- FAIL linux replay" \
  || fail "18h: the container leg never failed — the arm measures nothing: $out"
[ "$(cut -f6 "$CHRONO")" = "linux replay" ] \
  || fail "18h: sixth field '$(cut -f6 "$CHRONO")', expected 'linux replay'"

#     (e) CADRE_GATE_FAIL_FAST=all IS A STOP TOO, at this scale (« ≠ 0 »): only (a)
#         played the default `prio`, so a `step()` guard narrowed to it went unseen.
#         MUTATION M6: `[ "$FF" != "0" ]` → `[ "$FF" = "prio" ]` in step() → red here
#         ("a step RAN after the red"), (a) stays green.
printf 'sha=%s\nmode=frozen\nlinux=1\nhost=fixture\nat=fixture\n' "$SHA1" > "$STAMP"
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE"
set +e
out="$(ff_run "$FF_WT" all --linux --at "$SHA_FF" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "18e: CADRE_GATE_FAIL_FAST=all with a red first step must exit 1, got $rc: $out"
echo "$out" | grep -qF -e "--- FAIL python -m pytest (CI scope, shards)" \
  || fail "18e: the first step never failed — the arm measures nothing: $out"
[ ! -e "$FF_MARK" ] || fail "18e: a step RAN after the red under CADRE_GATE_FAIL_FAST=all — step() honours prio only: $out"
[ ! -e "$FF_DMARK" ] || fail "18e: docker run was called after a red host leg under CADRE_GATE_FAIL_FAST=all: $out"
echo "$out" | grep -qF -e "NOT RUN (fail-fast=all): 3 step(s) — the failure list is NOT complete" \
  || fail "18e: no count line for all (2 steps + the --linux leg): $out"
echo "$out" | grep -q "VERIFY FAILED @ $SHORT_FF" \
  || fail "18e: the verdict is not the red one anchored to $SHORT_FF: $out"
[ ! -e "$STAMP" ] || fail "18e: A STALE GREEN SURVIVED a fail-fast red --at under all: $(cat "$STAMP")"

#     (c) AN INVALID VALUE IS rc 2, BEFORE THE LOCK AND THE CLONE: no step runs.
#         MUTATION M3: neutralise the validation (`prio|all|0)` → `*)`) → rc 1 → red.
FF_WTC="$TMP/wt18c"
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE"
rm -f "$CHRONO"
set +e
out="$(ff_run "$FF_WTC" x --at "$SHA_FF" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "18c: CADRE_GATE_FAIL_FAST=x must be rc 2, got $rc: $out"
echo "$out" | grep -qF -e "CADRE_GATE_FAIL_FAST='x' is invalid" \
  || fail "18c: the refusal does not name the value: $out"
[ ! -e "$FF_TRACE" ] && [ ! -e "$FF_MARK" ] || fail "18c: a step ran despite an invalid value: $out"
[ ! -e "$FF_WTC" ] || fail "18c: a clone was made — the validation must come before the lock and the clone"
[ ! -e "$FF_WTC.lock" ] || fail "18c: a lock was taken — the validation must come before the lock"
[ ! -e "$CHRONO" ] || fail "18c: an invalid setting wrote a gate duration before the lock"
#         The same refusal on the LIVE path writes no row either: no gate row
#         before the first step, in both modes. MUTATION MN9: `[ -n "$AT" ] ||
#         CHRONO_ACTIVE=1` ahead of chrono_write → red here, and only here.
rm -f "$FF_MARK" "$FF_DMARK" "$FF_TRACE"
set +e
out="$(ff_run "$FF_WTC" x 2>&1)"
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "18c: live CADRE_GATE_FAIL_FAST=x must be rc 2, got $rc: $out"
[ ! -e "$FF_TRACE" ] && [ ! -e "$FF_MARK" ] || fail "18c: a live step ran despite an invalid value: $out"
[ ! -e "$CHRONO" ] || fail "18c: a live refusal before the first step wrote a gate duration"

# 15. THIS BENCH, RUN THE WAY THE GATE RUNS IT: WITH VERIFY_INNER=1 ALREADY IN THE
#     ENVIRONMENT. Arms 1-14 above are all green on a developer's box, where that
#     variable is unset; the gate delegates through `VERIFY_INNER=1 bash
#     "$WT/core-scripts/verify.sh"`, which exports it into run-bash-tests.sh and from
#     there into this file. Fourteen arms proved nothing about that environment,
#     and the difference cost a red gate — `linux legs: pytest rc=0, bash rc=1` —
#     on a lot whose fourteen arms were green when they were written.
#
#     WITHOUT THIS ARM THE FIX IS UNGUARDED AND THE RED COMES BACK UNEXPLAINED:
#     the three `VERIFY_INNER=0` prefixes could be dropped one at a time, by a
#     reviewer who reads them as noise, and every arm above would stay green on
#     the host that reviewer is using. This is the only cell that runs the bench in
#     the environment the bench is actually deployed into.
#
#     MUTATIONS, one per launch site, each measured red HERE and green everywhere
#     above (each is also written at its own site):
#       - drop `VERIFY_INNER=0` from `run_green` → nested 11a: "a green --at wrote
#         no verdict stamp" — verbatim the gate failure.
#       - drop it from `run`     → nested 11b: "--linux was not recorded in the stamp".
#       - drop it from arm 13    → nested 13: "a red LIVE run left the stale green
#         stamp on disk".
#       - the three pins of `ff_run` (arm 18): their mutations are listed there.
#     The nested run is ALSO handed CADRE_GATE_FAIL_FAST=0 and a foreign
#     CADRE_GATE_DURATIONS_DIR — what a developer's `CADRE_GATE_FAIL_FAST=0 bash
#     core-scripts/verify.sh --at HEAD` hands this bench through the gate. Arms
#     1-14 do not depend on them (9 and 13 stay red, 11a and 14 stay green); arm 18
#     must, by its pins, stay deaf to them.
#
#     RE-ENTRY IS GUARDED, not by cleverness but because it must be: this arm runs
#     THIS FILE, so an unguarded copy would recurse until the box gave up.
#     VERIFY_TEST_NESTED is the sentinel, and the nested run REPORTS THE VALUE OF
#     VERIFY_INNER IT ACTUALLY SAW rather than merely announcing that it is nested.
#     That is what makes this arm non-vacuous: a green here can no longer come from
#     a nested run that was never poisoned in the first place — the assertion below
#     pins the string to `VERIFY_INNER=1`, so a poison that failed to arrive is red.
if [ "${VERIFY_TEST_NESTED:-0}" = "1" ]; then
  # `<unset>` passe par une variable : des chevrons dans une valeur de défaut
  # ne se parsent pas (tree-sitter-bash), et le fichier ENTIER sortirait du
  # compte des cibles inspectées par le SAST. Message affiché INCHANGÉ.
  _unset='<unset>'
  echo "PASS: verify --at (15/15, arms 1-14 and 18, nested with VERIFY_INNER=${VERIFY_INNER:-$_unset} CADRE_GATE_FAIL_FAST=${CADRE_GATE_FAIL_FAST:-$_unset} CADRE_GATE_DURATIONS_DIR=${CADRE_GATE_DURATIONS_DIR:-$_unset} — arm 15 not re-entered)"
  exit 0
fi

set +e
nested_out="$(VERIFY_INNER=1 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_DURATIONS_DIR="$TMP/poison-durees" VERIFY_TEST_NESTED=1 bash "$SELF" 2>&1)"
nested_rc=$?
set -e
[ "$nested_rc" -eq 0 ] \
  || fail "15: this bench is RED when VERIFY_INNER=1 is inherited — which is exactly how the gate runs it: $nested_out"
echo "$nested_out" | grep -q "nested with VERIFY_INNER=1" \
  || fail "15: the nested run did not report VERIFY_INNER=1 — the poison never arrived and this arm proved nothing: $nested_out"
echo "$nested_out" | grep -q "CADRE_GATE_FAIL_FAST=0 CADRE_GATE_DURATIONS_DIR=$TMP/poison-durees" \
  || fail "15: the nested run did not report the two fail-fast poisons — arm 18's pins were not exercised: $nested_out"

# --- 16. LE CHRONOMETRE DE LA JAMBE CONTENEUR (T-00000611) -------------------
# CE QU IL DEFEND. Le pilote a tranche le COMPORTEMENT au depassement
# (COVERAGE DEGRADED + exit 0), mais la VALEUR du plafond n etait pas decidable :
# cette jambe n avait JAMAIS ete chronometree. L instrument precede donc le
# plafond. Sans cet arm, le retirer ne ferait rougir personne et on reviendrait
# dans deux semaines poser un nombre invente — la faute exacte que le ticket
# interdit.
grep -q "_linux_duree()" "$HERE/verify.sh" \
  || fail "16: le chronometre de la jambe conteneur a disparu — la valeur du plafond redevient non mesurable"
grep -q 'LINUX_T0="$(date +%s' "$HERE/verify.sh" \
  || fail "16: le point de depart du chronometre a disparu"
grep -q 'PASS linux replay\$(_linux_duree)' "$HERE/verify.sh" \
  || fail "16: la duree n est plus imprimee sur la ligne de verdict — mesurer sans dire ne sert a rien"

# LE HELPER EST SOURCE DEPUIS UN FICHIER, PAS EPISSE DANS DU TEXTE SHELL. La
# premiere redaction faisait `bash -c 'litt'"$(sed … verify.sh)"'litt'`, c est-a-
# dire une VALEUR RE-PARSEE COMME DU SHELL — forme que AGENTS.md declare finding
# de classe 1 NON-WAIVABLE. Impact securite nul ici (la valeur est un fichier du
# depot), mais la regle est ecrite sans exception, et le SAST ne voyait pas cette
# forme-la : sa regle ne filtre que la double-quote unique.
_ld_probe="$TMP/ld_probe.sh"
sed -n "/^_linux_duree() {/,/^}/p" "$HERE/verify.sh" > "$_ld_probe"
grep -q '^_linux_duree() {' "$_ld_probe" \
  || fail "16: extraction du helper VIDE — sans ce controle les arms suivants passeraient au vert sur une fonction ABSENTE"

# TOLERANCE D UNE SECONDE, ET ELLE EST MESUREE. La graine et le helper lisent
# l horloge DEUX fois ; 35 fois sur 3000 (1,17 %) elles enjambent une frontiere
# de seconde et le delta vaut 43. Cet arm tourne DEUX fois par porte --linux
# (hote + conteneur), donc exiger 42 pile fabriquait ~2,3 % de portes ROUGES
# sans cause de code — la faute exacte que T-00000611 interdit, posee sur la
# seule surface qui n a pas le droit de mentir. Releve du binome.
_ld_avec="$(bash -c '. "$1"; LINUX_T0="$(expr "$(date +%s)" - 42)"; _linux_duree' _ "$_ld_probe")"
case "$_ld_avec" in
  " (42s)"|" (43s)") : ;;
  *) fail "16: le chronometre ne rend pas la duree attendue a une seconde pres (rendu: [$_ld_avec])" ;;
esac

# UNE JAMBE SUB-SECONDE EST UNE MESURE, PAS UNE HORLOGE ILLISIBLE. C est le cas
# du demon Docker absent (echec en 53 ms, mesure) et `expr` sort 1 sur un
# resultat nul : sans cet arm, le FAIL le plus frequent de cette jambe
# s imprimait sous le signal reserve a l instrument en panne.
_ld_zero="$(bash -c '. "$1"; LINUX_T0="$(date +%s)"; _linux_duree' _ "$_ld_probe")"
case "$_ld_zero" in
  " (0s)"|" (1s)") : ;;
  *) fail "16: une jambe sub-seconde doit rendre une duree, jamais le silence reserve a l horloge illisible (rendu: [$_ld_zero])" ;;
esac

_ld_sans="$(bash -c '. "$1"; LINUX_T0=""; _linux_duree' _ "$_ld_probe")"
[ -z "$_ld_sans" ] \
  || fail "16: sans horloge le chronometre devrait se taire, il rend: $_ld_sans"

# LE TEMOIN DE PULL N AVAIT AUCUN ARM — et c est precisement lui qui mentait.
_pn_probe="$TMP/pn_probe.sh"
sed -n "/^_linux_pull_note() {/,/^}/p" "$HERE/verify.sh" > "$_pn_probe"
grep -q '^_linux_pull_note() {' "$_pn_probe" \
  || fail "16: extraction du temoin de pull VIDE — l arm suivant passerait au vert sur une fonction ABSENTE"
# LE `docker` EST STUBE PAR UNE FONCTION, ET CE N EST PAS UN CONFORT DE BANC.
# La redaction d origine posait DOCKER_HOST sur un port mort et comptait sur un
# binaire `docker` REEL pour echouer a s y connecter. Or cette suite est rejouee
# PAR LA JAMBE --linux A L INTERIEUR DU CONTENEUR, ou docker N EXISTE PAS — et
# l arm y devenait faux des deux cotes a la fois (mesure du 2026-09-14) :
#   * VACANT — la fonction rendait le vide parce que la commande etait absente,
#     pas parce que sa logique etait juste ; elle serait passee sur une fonction
#     cassee ;
#   * ROUGE — le `command_not_found_handle` de run-bash-tests.sh voyait la
#     commande absente, stampait `MISSING DEP (cmd: docker)` et rougissait LA
#     PORTE ENTIERE. Relevé : jambe hote `PASS (17s)`, jambe conteneur
#     `MISSING DEP (cmd: docker, 2s)`, `FAIL linux replay`, `VERIFY FAILED`.
# L appel etait INVISIBLE sans ce capteur — son stderr est supprime — ce qui est
# la raison pour laquelle il a survecu a sa propre revue.
#
# Une FONCTION shell nommee `docker` prime sur le binaire, donc la sonde mesure
# la logique a deux etats sans jamais toucher au vrai client, et de facon
# DETERMINISTE partout. Un stub rendant 1 est l observable EXACT des deux cas
# que l arm d origine visait : demon injoignable, et image absente.
# CE QUE CE STUB NE MESURE PLUS, ET IL FAUT LE DIRE : que le VRAI client docker
# rende non-zero contre un demon injoignable. C est desormais une HYPOTHESE de ce
# banc, pas une mesure. Si elle tombe, `_linux_pull_note` se TAIT quand meme —
# le residu est un `image PULLED` manquant, jamais un affirme a tort.
_pn_run() {  # _pn_run <rc-du-stub-docker> [etat-AVANT, defaut 1] -> sortie de _linux_pull_note
  local _rc="$1" _pulled="${2:-1}" _f="$TMP/pn_probe_$1_${2:-1}.sh"
  { printf 'docker() { return %s; }\n' "$_rc"; cat "$_pn_probe"; } > "$_f"
  bash -c '. "$1"; _LINUX_PULLED="$2"; IMAGE="python:3.12-slim"; _linux_pull_note' _ "$_f" "$_pulled"
}

_pn_out="$(_pn_run 1)"
[ -z "$_pn_out" ] \
  || fail "16: un demon injoignable annonce un telechargement qui n a pas eu lieu (rendu: [$_pn_out])"

# CONTROLE NEGATIF, ET IL MANQUAIT. Sans lui l arm ci-dessus est satisfait par
# une fonction qui ne rend JAMAIS rien — c est-a-dire par la fonction supprimee.
# C est la seconde lecture que le collapsus a deux etats exigeait : `PULLED` ne
# s affirme que sur `absente AVANT` ET `presente APRES`.
_pn_out_ok="$(_pn_run 0)"
case "$_pn_out_ok" in
  *"image PULLED"*)
    : ;;
  *)
    fail "16: image reellement presente, le temoin de pull reste muet (rendu: [$_pn_out_ok])" ;;
esac

# TROISIEME LECTURE — L AUTRE MOITIE DU COLLAPSUS, ET ELLE MANQUAIT. Les deux
# arms ci-dessus figent `_LINUX_PULLED=1`, donc aucun ne voit la garde de l etat
# AVANT. Mutant mesure par le binome : retirer
# `[ "${_LINUX_PULLED:-0}" = "1" ] || return 0` de verify.sh laisse les deux
# INCHANGES — [] puis `, image PULLED` — et l arm 16 reste VERT. La garde posee
# par 9f6bf16, « PULLED ne s affirme que sur absente AVANT *ET* presente APRES »,
# n avait donc aucun temoin ; sans elle la porte reaffirme `image PULLED (0s)`
# sur une image deja en cache, ce qui disqualifie le releve dont on doit tirer
# le plafond de la jambe.
_pn_out_deja="$(_pn_run 0 0)"
[ -z "$_pn_out_deja" ] \
  || fail "16: image DEJA presente AVANT la jambe, le banc annonce quand meme un telechargement (rendu: [$_pn_out_deja])"

# ET LA SONDE NE DOIT JAMAIS ATTEINDRE UN VRAI `docker`. Sans cet arm, un
# refactor qui retirerait le stub rendrait les deux precedents verts sur l hote
# (ou docker existe) et rougirait la porte dans le conteneur — exactement le
# defaut qu on vient de fermer, et il se serait reintroduit en silence.
for _pn_f in "$TMP"/pn_probe_*_*.sh; do
  grep -q '^docker() { return [01]; }$' "$_pn_f" \
    || fail "16: la sonde $_pn_f n embarque pas son stub docker — elle appellera le binaire reel"
done

# ET LE STUB NE PRIME QUE SUR UN APPEL `docker` NU. Un refactor de verify.sh
# vers `command docker` ou vers un chemin absolu contournerait la fonction, donc
# rejoindrait le binaire reel et reintroduirait `MISSING DEP (cmd: docker)` dans
# le conteneur — pendant que les trois arms ci-dessus resteraient VERTS, puisque
# leurs sondes porteraient toujours leur stub. Mesure : `command docker` avec un
# PATH vide atteint bien `command_not_found_handle` (rc 127). On epingle donc la
# FORME de l appel dans la source, pas seulement la presence du stub.
grep -q '^  docker image inspect "\${IMAGE:-}"' "$HERE/verify.sh" \
  || fail "16: l appel n est plus un \`docker\` nu — command/chemin absolu contournent le stub et rougissent le conteneur"

# LA BRANCHE FAIL DOIT PORTER LA DUREE AUSSI : c est la que l echec infra de
# 53 ms se mesure, et le premier arm ne grepait que la branche PASS.
grep -q 'FAIL linux replay\$(_linux_duree)' "$HERE/verify.sh" \
  || fail "16: la duree n est plus imprimee sur la branche FAIL"

# --- 17. LA JAMBE --linux JOUE LA FORME NUE DE LA CI PAR DEFAUT (binome 7+8, T1) ----
# ci.yml epingle CADRE_GATE_JOBS "1" (une session pytest unique). `docker run` ne
# transmettait QUE APT_PKGS : dans le conteneur la valeur retombait sur `auto`, donc
# tranches paralleles et rejeu seul — plus AUCUNE jambe de la porte ne jouait la forme
# de la CI, et check-ci-parity (qui compare le texte des commandes, jamais l env) ne
# pouvait pas le voir. Forme epinglee SUR la ligne `docker run`, jamais un commentaire.
grep -Eq '^[[:space:]]*docker run .*-e CADRE_GATE_JOBS="\$\{CADRE_GATE_JOBS:-1\}" ' "$HERE/verify.sh" \
  || fail "17: docker run ne transmet plus CADRE_GATE_JOBS (defaut 1) — la jambe --linux ne joue plus la forme nue de la CI"

# --- 19. LES JAMBES EN PARALLELE (T-01M60XKFK7MPKZWNHH326ZMW3M) --------------------
# CADRE_GATE_JAMBES=parallele joue pytest au premier plan et la jambe bash en fond ;
# `auto` ne le fait que sur la porte du kit, CADRE_GATE_JOBS vide ou `auto`, hors
# MINGW/MSYS/CYGWIN, a 16 coeurs ou plus. LE SCRIPT SOUS TEST EST CELUI LIVRE : un
# depot jetable `r19` porte verify.sh tel quel et deux bouchons de coureurs pilotes
# par des variables J19_* (comportement, marqueurs). Joue APRES l'arm 15, donc une
# seule fois (le run imbrique s'arrete a 15).
# L'ENVIRONNEMENT EST CONSTRUIT, JAMAIS HERITE (en-tete) : `j19-run.sh` RETIRE
# CADRE_GATE_JOBS (la CI l'exporte a 1, ci.yml : herite, les bras `auto` mesureraient
# la serie de la CI et leurs mutants seraient aveugles — C13, C15), le mode exporte en
# tete de ce banc, et CADRE_GATE_JOBS_BASH ; il epingle VERIFY_INNER=0 (cinquieme site
# de lancement) et un TMPDIR a lui, que chaque bras relit vide : le journal de la
# jambe bash vit sous le ROUGES_TMP de la porte, efface a la sortie (C8).
# Interpreteur des bras 19h2-h3 : `$PY` de l'arm 9, resolu AVANT le bouchon $SHIM,
# pris en chemin absolu — jamais le faux python3 de $SHIM (C16).
is_win() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  return 1
}
cat > "$TMP/j19-pytest.sh" <<'J19PY'
#!/usr/bin/env bash
# J19_PY : vert | rouge | attend (le marqueur de la jambe bash, 10 s au plus) | 143 | tardif (rouge apres
# le pid de la jambe bash) | sourd | court | dort
[ -z "${J19_ENV_PY:-}" ] || echo "${CADRE_GATE_JAMBES-absente}" > "$J19_ENV_PY"
case "${J19_PY:-vert}" in
  attend)
    i=0
    while [ ! -e "$J19_MARK" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done
    [ -e "$J19_MARK" ] || { echo "jambe pytest : marqueur de la jambe bash absent apres 10 s"; exit 1; } ;;
  rouge)
    echo "sortie pytest"; exit 1 ;;
  143)
    i=0
    while [ ! -s "$J19_PID" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done
    exit 143 ;;
  tardif)
    i=0
    while [ ! -s "$J19_PID" ] && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done
    echo "sortie pytest"; exit 1 ;;
  sourd)
    trap '' INT; sleep 5 ;;
  court)
    sleep 0.5 ;;
  dort)
    sleep 3 ;;
esac
echo "sortie pytest"
exit 0
J19PY
cat > "$TMP/j19-bash.sh" <<'J19SH'
#!/usr/bin/env bash
# J19_SH : vert | rouge (exit 3) | long (exec sleep 30, son pid ecrit dans J19_PID)
[ -z "${J19_PID:-}" ] || echo "$$" > "$J19_PID"
[ -z "${J19_ENV_SH:-}" ] || echo "${CADRE_GATE_JAMBES-absente}" > "$J19_ENV_SH"
[ -z "${J19_JOBS:-}" ] || echo "${CADRE_GATE_JOBS_BASH-absente}" > "$J19_JOBS"
[ -z "${J19_MARK:-}" ] || : > "$J19_MARK"
case "${J19_SH:-vert}" in
  rouge)
    echo "sortie bash"; exit 3 ;;
  long)
    exec sleep 30 ;;
esac
echo "sortie bash"
exit 0
J19SH
# j19-run.sh <depot> <tmpdir> [VAR=valeur…] -- [arguments de verify.sh…] — EXEC la porte : lance en fond,
# son `$!` est le pid de verify.sh lui-meme (bras 19e).
cat > "$TMP/j19-run.sh" <<'J19RUN'
#!/usr/bin/env bash
d="$1"; t="$2"; shift 2
envs=()
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
[ "$#" -eq 0 ] || shift
cd "$d" || exit 1
exec env -u CADRE_GATE_JOBS -u CADRE_GATE_JAMBES -u CADRE_GATE_JOBS_BASH \
  VERIFY_INNER=0 CADRE_GATE_FAIL_FAST="" CADRE_GATE_DURATIONS_DIR="" TMPDIR="$t" \
  ${envs[@]+"${envs[@]}"} bash core-scripts/verify.sh "$@"
J19RUN
J19_TMPDIR="$TMP/j19-tmpdir"
mkdir -p "$J19_TMPDIR"
j19() { local d="$1"; shift; bash "$TMP/j19-run.sh" "$d" "$J19_TMPDIR" "$@"; }
j19_tmp_vide() { [ -z "$(ls -A "$J19_TMPDIR")" ] || fail "$1: the gate left its temporary directory behind (jambe-bash.log): $(ls -A "$J19_TMPDIR")"; }
mk_j19() {  # mk_j19 <depot> <verify.sh a livrer>
  mkdir -p "$1/core-scripts" "$1/.agents/security"
  cp "$2" "$1/core-scripts/verify.sh"
  cp "$TMP/j19-pytest.sh" "$1/core-scripts/run-pytest-shards.sh"
  cp "$TMP/j19-bash.sh" "$1/core-scripts/run-bash-tests.sh"
  cp "$TMP/green-bash-tests.sh" "$1/.agents/security/shellcheck-scan.sh"
  printf '/.agents/state/local/\n' > "$1/.gitignore"
  git -C "$1" init -q
  git -C "$1" config user.email t@t
  git -C "$1" config user.name t
  git -C "$1" config core.autocrlf false
  git -C "$1" add -A
  git -C "$1" commit -qm j19
}
ligne_de() { printf '%s\n' "$out" | grep -nF -e "$1" | sed -n '1s/:.*//p'; }
J19="$TMP/r19"
mk_j19 "$J19" "$REAL_VERIFY"
J19_STAMP="$J19/.agents/state/local/VERIFY_STAMP"
J19_CHRONO="$J19/.agents/state/local/porte-chrono.tsv"
J19_MARK="$TMP/j19-mark"
J19_PIDF="$TMP/j19-pid"
J19_ENVP="$TMP/j19-env-py"
J19_ENVS="$TMP/j19-env-sh"
J19_JOBSF="$TMP/j19-jobs"
L_PY="python -m pytest (CI scope, shards)"
L_SH="bash core-scripts/run-bash-tests.sh"
# Coeurs (getconf, nproc, sysctl) et systeme bouchonnes, premier sur le PATH.
for _c in 18 8; do
  mkdir -p "$TMP/cs$_c"
  for _o in getconf nproc sysctl; do printf '#!/bin/sh\necho %s\n' "$_c" > "$TMP/cs$_c/$_o"; chmod +x "$TMP/cs$_c/$_o"; done
done
mkdir -p "$TMP/csw"
cp "$TMP/cs18/getconf" "$TMP/cs18/nproc" "$TMP/cs18/sysctl" "$TMP/csw/"
printf '#!/bin/sh\necho MINGW64_NT-10.0\n' > "$TMP/csw/uname"
chmod +x "$TMP/csw/uname"

#     (a) CHEVAUCHEMENT, (b) ORDRE DU JOURNAL, (k) HERITAGE — un seul run `parallele`.
#         Le bouchon pytest ATTEND le marqueur que cree le bouchon bash : en serie il
#         rougit apres 10 s. MUTATION « jambes en serie » (jambes_jouer neutralise) →
#         19a rouge. MUTATION « cat du journal bash avant le bloc pytest » → 19b rouge.
#         MUTATION « unset CADRE_GATE_JAMBES retire » → les bouchons lisent `parallele`
#         → 19k rouge.
rm -f "$J19_MARK" "$J19_ENVP" "$J19_ENVS" "$J19_JOBSF"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=parallele J19_PY=attend J19_MARK="$J19_MARK" J19_ENV_PY="$J19_ENVP" J19_ENV_SH="$J19_ENVS" J19_JOBS="$J19_JOBSF" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "19a: the two legs did not overlap (the pytest leg waits for the bash leg's marker), rc $rc: $out"
echo "$out" | grep -qF -e "porte: jambes en parallèle" || fail "19a: no 'porte: jambes en parallèle' line under parallele: $out"
echo "$out" | grep -qF -e "VERIFY OK @" || fail "19a: two green legs must give the green verdict: $out"
n1="$(ligne_de "=== $L_PY")"; n2="$(ligne_de "sortie pytest")"; n3="$(ligne_de "--- PASS $L_PY")"
n4="$(ligne_de "=== $L_SH")"; n5="$(ligne_de "sortie bash")"; n6="$(ligne_de "--- PASS $L_SH")"
[ -n "$n1" ] && [ -n "$n2" ] && [ -n "$n3" ] && [ -n "$n4" ] && [ -n "$n5" ] && [ -n "$n6" ] \
  && [ "$n1" -lt "$n2" ] && [ "$n2" -lt "$n3" ] && [ "$n3" -lt "$n4" ] && [ "$n4" -lt "$n5" ] && [ "$n5" -lt "$n6" ] \
  || fail "19b: the journal is not in the series' order (pytest block, then bash block: $n1 $n2 $n3 $n4 $n5 $n6): $out"
[ "$(cat "$J19_ENVP")" = absente ] && [ "$(cat "$J19_ENVS")" = absente ] \
  || fail "19k: a leg inherited CADRE_GATE_JAMBES (pytest: $(cat "$J19_ENVP"), bash: $(cat "$J19_ENVS")) — verify.sh must unset it after reading"
[ "$(cat "$J19_JOBSF")" = absente ] || fail "19a: CADRE_GATE_JOBS_BASH reached the bash leg outside auto: $(cat "$J19_JOBSF")"
j19_tmp_vide 19a

#     (c) LE RC DE LA JAMBE DE FOND EST SON VERDICT : bouchon bash `exit 3`, pytest vert.
#         MUTATION « rc du wait ignore » → PASS → rouge.
printf 'sha=x\nmode=live\nlinux=0\nhost=fixture\nat=fixture\n' > "$J19_STAMP"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=parallele J19_SH=rouge 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "19c: a red background leg must make the gate exit 1, got $rc: $out"
echo "$out" | grep -qF -e "--- FAIL $L_SH (exit 3)" || fail "19c: the background leg's rc 3 was not its verdict: $out"
echo "$out" | grep -qF -e "--- PASS $L_PY" || fail "19c: the green pytest leg is not PASS: $out"
n4="$(ligne_de "=== $L_SH")"; n5="$(ligne_de "sortie bash")"; n6="$(ligne_de "--- FAIL $L_SH")"
[ -n "$n4" ] && [ -n "$n5" ] && [ -n "$n6" ] && [ "$n4" -lt "$n5" ] && [ "$n5" -lt "$n6" ] \
  || fail "19c: the bash leg's output is not inside its own block: $out"
[ ! -e "$J19_STAMP" ] || fail "19c: a red parallel gate left the stale stamp: $(cat "$J19_STAMP")"
j19_tmp_vide 19c

#     (d) DEUX ROUGES : sous CADRE_GATE_FAIL_FAST=0 les deux jambes jouent, la 6e
#         colonne du journal et la liste des rouges nomment pytest D'ABORD ; sous le
#         defaut, un pytest rouge ARRETE la jambe bash (longue, 30 s) : TERMee, jamais
#         attendue, annoncee NOT RUN comme en serie, puis shellcheck NOT RUN.
#         MUTATIONS « noter_rouge bash d'abord » → rouge ; « branche kill retiree »
#         → la porte attend la jambe 30 s, aucune ligne NOT RUN → rouge.
rm -f "$J19_CHRONO"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=parallele CADRE_GATE_FAIL_FAST=0 J19_PY=rouge J19_SH=rouge 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "19d: two red legs must exit 1, got $rc: $out"
[ "$(cut -f6 "$J19_CHRONO")" = "$L_PY" ] || fail "19d: sixth field '$(cut -f6 "$J19_CHRONO")', expected the pytest leg first"
[ "$(grep -c -e '^etape' "$J19/.agents/state/local/PORTE_ROUGES")" -eq 2 ] \
  && [ "$(sed -n '/^etape/{s/^etape.//p;q;}' "$J19/.agents/state/local/PORTE_ROUGES")" = "$L_PY" ] \
  || fail "19d: PORTE_ROUGES does not list pytest then bash: $(cat "$J19/.agents/state/local/PORTE_ROUGES")"
echo "$out" | grep -qF -e "--- FAIL $L_PY (exit 1)" && echo "$out" | grep -qF -e "--- FAIL $L_SH (exit 3)" \
  || fail "19d: under CADRE_GATE_FAIL_FAST=0 both legs must play and report their own red: $out"
if echo "$out" | grep -qF -e "--- NOT RUN"; then fail "19d: CADRE_GATE_FAIL_FAST=0 announced a NOT RUN: $out"; fi
rm -f "$J19_PIDF"
_t0="$(date +%s)"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=parallele J19_PY=tardif J19_SH=long J19_PID="$J19_PIDF" 2>&1)"
rc=$?
set -e
_t1="$(date +%s)"
[ "$rc" -eq 1 ] || fail "19d: a red pytest leg under the default must exit 1, got $rc: $out"
echo "$out" | grep -qF -e "--- FAIL $L_PY (exit 1)" || fail "19d: the pytest leg must report its own red: $out"
echo "$out" | grep -qF -e "--- NOT RUN $L_SH (échec rapide ; CADRE_GATE_FAIL_FAST=0 joue tout)" \
  || fail "19d: under the default a red pytest leg must stop the bash leg, announced NOT RUN: $out"
if echo "$out" | grep -qF -e "--- PASS $L_SH" || echo "$out" | grep -qF -e "--- FAIL $L_SH"; then
  fail "19d: a stopped bash leg was given a verdict: $out"
fi
_nr="$(printf '%s\n' "$out" | grep -c -e '^--- NOT RUN ')"
echo "$out" | grep -qF -e "NOT RUN (fail-fast=prio): $_nr step(s)" \
  || fail "19d: the summary does not count the $_nr NOT RUN lines (the stopped bash leg included): $out"
echo "$out" | grep -qF -e "--- NOT RUN bash .agents/security/shellcheck-scan.sh" \
  || fail "19d: the fail-fast must apply to the step after the two legs: $out"
[ "$((_t1 - _t0))" -lt 10 ] || fail "19d: the gate waited $((_t1 - _t0)) s for the bash leg after a red pytest leg: $out"
[ -s "$J19_PIDF" ] || fail "19d: the background leg never started — the arm measures nothing: $out"
j19_bg="$(cat "$J19_PIDF")"
if kill -0 "$j19_bg" 2>/dev/null; then kill -TERM "$j19_bg" 2>/dev/null || true; fail "19d: the bash leg survived a red pytest leg: $out"; fi
j19_tmp_vide 19d

#     (e) TERM A LA PORTE : la jambe de fond ne survit pas. verify_on_exit la TERM puis
#         l'attend. MUTATIONS « bloc retire de verify_on_exit » → le bouchon vit → rouge ;
#         « kill seul retire » → le `wait` restant attend 30 s → la borne de 10 s rougit.
rm -f "$J19_PIDF"
bash "$TMP/j19-run.sh" "$J19" "$J19_TMPDIR" CADRE_GATE_JAMBES=parallele J19_PY=dort J19_SH=long J19_PID="$J19_PIDF" -- \
  > "$TMP/j19e.out" 2>&1 &
j19_gate=$!
_i=0
while [ ! -s "$J19_PIDF" ] && [ "$_i" -lt 100 ]; do sleep 0.1; _i=$((_i + 1)); done
[ -s "$J19_PIDF" ] || fail "19e: the background leg never started — the arm measures nothing: $(cat "$TMP/j19e.out")"
_t0="$(date +%s)"
kill -TERM "$j19_gate"
set +e
wait "$j19_gate"
set -e
_t1="$(date +%s)"
j19_bg="$(cat "$J19_PIDF")"
if kill -0 "$j19_bg" 2>/dev/null; then
  kill -TERM "$j19_bg" 2>/dev/null || true
  fail "19e: the background leg (pid $j19_bg) SURVIVED a TERM to the gate: $(cat "$TMP/j19e.out")"
fi
[ "$((_t1 - _t0))" -lt 10 ] || fail "19e: the gate took $((_t1 - _t0)) s to exit after a TERM — the background leg was waited for, never TERMed"
j19_tmp_vide 19e

#     (f) AUTO, coeurs bouchonnes : 18 → parallele (et 4 jobs a la jambe bash) ; 8 →
#         serie ; 18 + CADRE_GATE_JOBS=1 → serie ; 18 sous MINGW → serie. f1-f3 ne
#         jugent rien sous Windows (auto y vaut la serie) : SKIP nomme ; f4 joue partout.
#         MUTATIONS « auto => serie » (f1), « seuil 16 ignore » (f2), « JOBS explicite
#         ignore » (f3), « MINGW ignore » (f4) → rouges.
if is_win; then
  echo "SKIP: 19f1-f3 — sous Git Bash auto vaut la serie par conception (19f4 le couvre)"
else
  rm -f "$J19_JOBSF"
  set +e
  out="$(j19 "$J19" CADRE_GATE_JAMBES=auto "PATH=$TMP/cs18:$PATH" J19_JOBS="$J19_JOBSF" 2>&1)"
  rc=$?
  set -e
  [ "$rc" -eq 0 ] && echo "$out" | grep -qF -e "porte: jambes en parallèle" \
    || fail "19f1: auto on 18 cores must play the legs in parallel, rc $rc: $out"
  [ "$(cat "$J19_JOBSF")" = 4 ] || fail "19f1: auto on 18 cores must hand the bash leg 4 jobs, got $(cat "$J19_JOBSF")"
  #   (f6) UN CADRE_GATE_JOBS_BASH EXPORTE PRIME sur min(4, coeurs/4) : 2 sur 18 coeurs.
  #        MUTATION « valeur exportee ignoree » → 4 → rouge.
  rm -f "$J19_JOBSF"
  set +e
  out="$(j19 "$J19" CADRE_GATE_JAMBES=auto "PATH=$TMP/cs18:$PATH" CADRE_GATE_JOBS_BASH=2 J19_JOBS="$J19_JOBSF" 2>&1)"
  rc=$?
  set -e
  [ "$rc" -eq 0 ] && echo "$out" | grep -qF -e "jambe bash à 2 jobs" \
    || fail "19f6: auto on 18 cores with CADRE_GATE_JOBS_BASH=2 must announce 2 jobs, rc $rc: $out"
  [ "$(cat "$J19_JOBSF")" = 2 ] || fail "19f6: an exported CADRE_GATE_JOBS_BASH=2 must reach the bash leg, got $(cat "$J19_JOBSF")"
  for _v in "f2:cs8:" "f3:cs18:CADRE_GATE_JOBS=1"; do
    _id="${_v%%:*}"; _rest="${_v#*:}"; _dir="${_rest%%:*}"; _jobs="${_rest#*:}"
    rm -f "$J19_JOBSF"
    set +e
    if [ -n "$_jobs" ]; then
      out="$(j19 "$J19" CADRE_GATE_JAMBES=auto "PATH=$TMP/$_dir:$PATH" "$_jobs" J19_JOBS="$J19_JOBSF" 2>&1)"
    else
      out="$(j19 "$J19" CADRE_GATE_JAMBES=auto "PATH=$TMP/$_dir:$PATH" J19_JOBS="$J19_JOBSF" 2>&1)"
    fi
    rc=$?
    set -e
    [ "$rc" -eq 0 ] || fail "19$_id: the series must stay green, rc $rc: $out"
    if echo "$out" | grep -qF -e "porte: jambes"; then fail "19$_id: auto must keep the series ($_dir $_jobs): $out"; fi
    [ "$(cat "$J19_JOBSF")" = absente ] || fail "19$_id: the series handed CADRE_GATE_JOBS_BASH to the bash leg"
  done
  #   (f5) LE DEFAUT EST `auto` : CADRE_GATE_JAMBES ABSENTE (j19-run.sh la retire), puis
  #        VIDE, sur 18 coeurs → parallele. MUTATION « ${CADRE_GATE_JAMBES:-serie} » → rouge.
  for _v in "absente" "vide"; do
    set +e
    if [ "$_v" = vide ]; then
      out="$(j19 "$J19" CADRE_GATE_JAMBES= "PATH=$TMP/cs18:$PATH" 2>&1)"
    else
      out="$(j19 "$J19" "PATH=$TMP/cs18:$PATH" 2>&1)"
    fi
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && echo "$out" | grep -qF -e "porte: jambes en parallèle" \
      || fail "19f5: CADRE_GATE_JAMBES $_v on 18 cores must default to auto and play the legs in parallel, rc $rc: $out"
  done
fi
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=auto "PATH=$TMP/csw:$PATH" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "19f4: the series must stay green under MINGW, rc $rc: $out"
if echo "$out" | grep -qF -e "porte: jambes"; then fail "19f4: auto must keep the series under MINGW on 18 cores: $out"; fi

#     (g) UNE VALEUR INVALIDE EST rc 2, AVANT TOUTE ETAPE ; aucune ligne de journal.
#         MUTATION « validation retiree » → rc 0 → rouge.
rm -f "$J19_MARK" "$J19_ENVP" "$J19_CHRONO"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=vite J19_MARK="$J19_MARK" J19_ENV_PY="$J19_ENVP" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "19g: CADRE_GATE_JAMBES=vite must be rc 2, got $rc: $out"
echo "$out" | grep -qF -e "CADRE_GATE_JAMBES='vite' is invalid" || fail "19g: the refusal does not name the value: $out"
[ ! -e "$J19_MARK" ] && [ ! -e "$J19_ENVP" ] || fail "19g: a leg ran despite an invalid value: $out"
[ ! -e "$J19_CHRONO" ] || fail "19g: an invalid value wrote a gate duration"

#     (h1) UNE JAMBE PYTEST QUI REND 143 (sans signal) : la jambe de fond meurt tout de
#          suite, aucun tampon, aucun journal temporaire. MUTATION « rc 130/143 non
#          traite » → la porte attend 30 s → rouge.
rm -f "$J19_PIDF"
printf 'sha=x\nmode=live\nlinux=0\nhost=fixture\nat=fixture\n' > "$J19_STAMP"
_t0="$(date +%s)"
set +e
out="$(j19 "$J19" CADRE_GATE_JAMBES=parallele J19_PY=143 J19_SH=long J19_PID="$J19_PIDF" 2>&1)"
rc=$?
set -e
_t1="$(date +%s)"
[ -s "$J19_PIDF" ] || fail "19h1: the background leg never started — the arm measures nothing: $out"
j19_bg="$(cat "$J19_PIDF")"
if kill -0 "$j19_bg" 2>/dev/null; then kill -TERM "$j19_bg" 2>/dev/null || true; fail "19h1: the background leg survived a pytest leg that came back 143: $out"; fi
[ "$rc" -ne 0 ] || fail "19h1: a pytest leg killed (143) cannot give rc 0: $out"
[ "$((_t1 - _t0))" -lt 10 ] || fail "19h1: the gate waited $((_t1 - _t0)) s for the background leg after a 143: $out"
if echo "$out" | grep -qF -e "VERIFY OK"; then fail "19h1: a green verdict after a 143: $out"; fi
[ "$(sed -n 's/^sha=//p' "$J19_STAMP")" = x ] || fail "19h1: an interrupted gate touched the stamp"
j19_tmp_vide 19h1

#     (h2) CTRL-C AU GROUPE, la jambe pytest IGNORE SIGINT (`trap '' INT; sleep 5`) :
#          le piege INT de la porte tue la jambe de fond et sort 130, sans tampon.
#          MUTATION « trap INT retire » → ~30 s et rc 0 → rouge.
#     (h3) CTRL-C PENDANT LE `wait` de la jambe de fond (pytest fini en 0,5 s, signal a
#          1,5 s) : la jambe de fond meurt, rc 130. MUTATION « piege qui note sans
#          tuer » → la jambe vit → rouge.
#          Lanceur : `$PY` en chemin absolu (C16), nouvelle session (le groupe recoit le
#          signal, comme sous un Ctrl-C) et SIGINT remis par DEFAUT — un job en fond d'un
#          shell non interactif (ce banc sous le coureur parallele) ignore SIGINT, et un
#          signal ignore a l'entree ne se piege plus. SKIP nomme sous Windows (groupe et
#          session MSYS non mesures) et sans interpreteur.
#          Le lanceur est ecrit au niveau superieur, comme les autres bouchons j19 :
#          un heredoc dans une branche `if` fait perdre le fichier entier au SAST
#          (PartialParsing, .agents/ref/CONVENTIONS_shell.md).
cat > "$TMP/j19-int.py" <<'J19INT'
import os
import signal
import subprocess
import sys
import time

signal.signal(signal.SIGINT, signal.SIG_DFL)
pidfile, delay, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
t0 = time.time()
with open(out, "wb") as f:
    p = subprocess.Popen(sys.argv[4:], stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                         start_new_session=True)
    for _ in range(100):
        if os.path.exists(pidfile) and os.path.getsize(pidfile) > 0:
            break
        time.sleep(0.1)
    time.sleep(delay)
    try:
        os.killpg(p.pid, signal.SIGINT)
    except OSError:
        pass
    try:
        rc = p.wait(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        rc = p.wait()
print("rc=%d s=%d" % (rc, int(time.time() - t0)))
J19INT
J19_PYBIN=""
[ -z "$PY" ] || J19_PYBIN="$(command -v "$PY")"
if is_win; then
  echo "SKIP: 19h2-h3 — sous Git Bash le signal au groupe d'une session n'est pas mesure"
elif [ -z "$J19_PYBIN" ]; then
  echo "SKIP: 19h2-h3: no python interpreter"
else
  for _v in "h2:sourd:0.3" "h3:court:1.5"; do
    _id="${_v%%:*}"; _rest="${_v#*:}"; _py="${_rest%%:*}"; _delay="${_rest#*:}"
    rm -f "$J19_PIDF"
    printf 'sha=x\nmode=live\nlinux=0\nhost=fixture\nat=fixture\n' > "$J19_STAMP"
    set +e
    res="$("$J19_PYBIN" "$TMP/j19-int.py" "$J19_PIDF" "$_delay" "$TMP/j19$_id.out" \
      bash "$TMP/j19-run.sh" "$J19" "$J19_TMPDIR" CADRE_GATE_JAMBES=parallele J19_PY="$_py" J19_SH=long J19_PID="$J19_PIDF" -- 2>&1)"
    set -e
    [ -s "$J19_PIDF" ] || fail "19$_id: the background leg never started — the arm measures nothing: $res $(cat "$TMP/j19$_id.out")"
    j19_bg="$(cat "$J19_PIDF")"
    if kill -0 "$j19_bg" 2>/dev/null; then kill -TERM "$j19_bg" 2>/dev/null || true; fail "19$_id: the background leg SURVIVED a Ctrl-C ($res): $(cat "$TMP/j19$_id.out")"; fi
    _rc="${res#rc=}"; _rc="${_rc%% *}"; _s="${res##*s=}"
    [ "$_rc" = 130 ] || fail "19$_id: a Ctrl-C must exit 130 ($res): $(cat "$TMP/j19$_id.out")"
    [ "$_s" -lt 10 ] || fail "19$_id: the gate took $_s s after a Ctrl-C ($res)"
    [ ! -e "$J19_STAMP" ] || [ "$(sed -n 's/^sha=//p' "$J19_STAMP")" = x ] || fail "19$_id: a Ctrl-C wrote a stamp"
    j19_tmp_vide "19$_id"
  done
fi

#     (i) STATIQUE : le pid est INITIALISE avant le piege EXIT (C14 : sous `set -u`, sinon
#         verify_on_exit meurt sur un nom non lie et le verrou fuit), la recolte est la
#         forme citee qui garde 127 (C2, C12) et vide le pid (C11), et les deux TERM
#         visent un pid non vide seulement. MUTATIONS « guillemets retires », « init
#         apres le piege », « garde du TERM retiree » → rouges.
grep -qF -e 'if [ -n "$JAMBE_PID" ]; then wait "$JAMBE_PID"; rc=$?; JAMBE_PID=""; else rc=127; fi' "$REAL_VERIFY" \
  || fail "19i: the background leg is no longer reaped by the quoted, 127-keeping form"
_li="$(grep -n -x -e 'JAMBE_PID=""' "$REAL_VERIFY" | sed -n '1s/:.*//p')"
_lt="$(grep -n -x -F -e "trap 'verify_on_exit \"\$?\"' EXIT" "$REAL_VERIFY" | sed -n '1s/:.*//p')"
[ -n "$_li" ] && [ -n "$_lt" ] && [ "$_li" -lt "$_lt" ] \
  || fail "19i: JAMBE_PID is not initialised BEFORE the EXIT trap (init line '$_li', trap line '$_lt')"
[ "$(grep -c -F -e 'if [ -n "${JAMBE_PID:-}" ]; then' "$REAL_VERIFY")" -eq 2 ] \
  || fail "19i: the two TERMs of the background leg (verify_on_exit, jambes_interrompre) must each be guarded on a non-empty pid"

#     (j) UNE JAMBE D'ARGV VIDE N'EST JAMAIS UN PASS : copie de verify.sh dont le libelle
#         pytest de la table de step() est renomme — la jambe pytest reste vide.
#         MUTATION « garde de la jambe vide retiree » → PASS ou erreur → rouge.
sed 's/") JAMBE_PY=/-renomme") JAMBE_PY=/' "$REAL_VERIFY" > "$TMP/verify-j19j.sh"
[ "$(grep -c -e '-renomme") JAMBE_PY=' "$TMP/verify-j19j.sh")" -eq 1 ] \
  || fail "19j: the fixture could not rename the deferred pytest label — the arm would prove nothing"
mk_j19 "$TMP/r19j" "$TMP/verify-j19j.sh"
set +e
out="$(j19 "$TMP/r19j" CADRE_GATE_JAMBES=parallele 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "19j: an empty leg must make the gate red, got $rc: $out"
echo "$out" | grep -qF -e "--- FAIL $L_PY (exit 127 : jambe vide)" || fail "19j: the empty leg is not named FAIL 127: $out"

#     (l) --at : la valeur LUE traverse la delegation (prefixe en tete des deux lignes,
#         C10). Commit `jambesleg` : verify.sh livre + les bouchons. l1 : 18 coeurs,
#         `serie`, pytest rouge → aucune ligne parallele et `NOT RUN bash` (SKIP sous
#         Windows : auto y vaut la serie, le mutant serait aveugle) ; l2 : 8 coeurs,
#         `parallele` → la ligne. MUTATION « prefixe retire » → l'interne rejoue `auto`
#         → l1 parallele, l2 serie → rouges.
J19_PY_BLOB="$(git -C "$REPO" hash-object -w "$TMP/j19-pytest.sh")"
J19_SH_BLOB="$(git -C "$REPO" hash-object -w "$TMP/j19-bash.sh")"
GIT_INDEX_FILE="$TMP/idxj" git -C "$REPO" read-tree "$SHA2"
GIT_INDEX_FILE="$TMP/idxj" git -C "$REPO" update-index --add --cacheinfo "100755,$J19_PY_BLOB,core-scripts/run-pytest-shards.sh"
GIT_INDEX_FILE="$TMP/idxj" git -C "$REPO" update-index --add --cacheinfo "100755,$J19_SH_BLOB,core-scripts/run-bash-tests.sh"
GIT_INDEX_FILE="$TMP/idxj" git -C "$REPO" update-index --add --cacheinfo "100755,$GREEN_BLOB,.agents/security/shellcheck-scan.sh"
J_TREE="$(GIT_INDEX_FILE="$TMP/idxj" git -C "$REPO" write-tree)"
SHA_J="$(git -C "$REPO" commit-tree "$J_TREE" -p "$SHA2" -m jambes)"
git -C "$REPO" branch jambesleg "$SHA_J"
[ "$(git -C "$REPO" rev-parse HEAD)" = "$SHA2" ] || fail "19l: building the legs commit moved HEAD"
if is_win; then
  echo "SKIP: 19l1 — sous Git Bash auto vaut la serie par conception (19l2 le couvre)"
else
  set +e
  out="$(j19 "$REPO" CADRE_GATE_JAMBES=serie "PATH=$TMP/cs18:$PATH" J19_PY=rouge VERIFY_WORKTREE_DIR="$TMP/wt19" -- --at "$SHA_J" 2>&1)"
  rc=$?
  set -e
  [ "$rc" -eq 1 ] || fail "19l1: a red pytest under --at must exit 1, got $rc: $out"
  echo "$out" | grep -qF -e "--- NOT RUN $L_SH" || fail "19l1: the inner did not play the series it was handed: $out"
  if echo "$out" | grep -qF -e "porte: jambes"; then fail "19l1: CADRE_GATE_JAMBES=serie was lost across --at: $out"; fi
fi
set +e
out="$(j19 "$REPO" CADRE_GATE_JAMBES=parallele "PATH=$TMP/cs8:$PATH" VERIFY_WORKTREE_DIR="$TMP/wt19" -- --at "$SHA_J" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "19l2: a green parallel --at must exit 0, got $rc: $out"
echo "$out" | grep -qF -e "porte: jambes en parallèle" || fail "19l2: CADRE_GATE_JAMBES=parallele was lost across --at: $out"

echo "PASS: verify --at (19/19)"
