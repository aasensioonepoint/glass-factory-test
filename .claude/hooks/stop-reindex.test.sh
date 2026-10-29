#!/usr/bin/env bash
# Tests for stop-reindex.sh. Run: bash .claude/hooks/stop-reindex.test.sh
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/stop-reindex.sh"
command -v git >/dev/null 2>&1 || { echo "SKIP: no git"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/src" "$TMP/.agents/state/index"
git -C "$TMP" init -q
git -C "$TMP" config user.email t@t
git -C "$TMP" config user.name t
echo "export const a = 1;" > "$TMP/src/a.ts"
git -C "$TMP" add -A && git -C "$TMP" commit -qm init
SHA=$(git -C "$TMP" rev-parse --short HEAD)

fail() { echo "FAIL: $1"; exit 1; }
# Cases 1-11 pin how the hook READS the probe; each one swaps the stub's canned
# output under an unchanged tree, so the probe cache (T-00000837) is dropped
# before each of them — the cache has its own arms (12-17) below.
run() { rm -rf "$TMP/.agents/state/local/stop-reindex"; CLAUDE_PROJECT_DIR="$TMP" bash "$HOOK"; }
# synthetic index header carrying a given built@ sha (ASCII only)
sym() { printf '# Symbols built @ %s\nSYM-001 src/a.ts:1-1 a export uses[] :: c\n' "$1" > "$TMP/.agents/state/index/SYMBOLS.md"; }

# 1. index at HEAD, no source change -> silent
sym "$SHA"
[ -z "$(run)" ] || fail "should be silent when the index matches HEAD"

# 2. source changed since the built commit -> stale nudge (git path)
echo "export const a = 2;" > "$TMP/src/a.ts"
run | grep -q 'stale' || fail "should nudge when source changed since built@"

# 3. only docs/index changed (both excluded from the diff) -> silent
git -C "$TMP" add -A && git -C "$TMP" commit -qm change
sym "$(git -C "$TMP" rev-parse --short HEAD)"
mkdir -p "$TMP/docs" && echo x > "$TMP/docs/x.md"
[ -z "$(run)" ] || fail "docs/index-only change should not nudge"

# 4. no built@ anchor -> mtime fallback nudges when source is newer
printf '# Symbols legacy no anchor\nSYM-001 src/a.ts:1-1 a export\n' > "$TMP/.agents/state/index/SYMBOLS.md"
sleep 1; touch "$TMP/src/a.ts"
run | grep -q 'stale' || fail "mtime fallback should nudge when source is newer than the index"

# 5. NEGATIVE ARM (T-00000062). NO vendoring marker -> .codex is source code, as
#    in the kit's own repo, and a change there MUST still nudge. This arm is what
#    keeps case 6 meaningful: an unconditional host exclusion would blind the kit
#    to its own hooks and still pass case 6 (L-00000025).
mkdir -p "$TMP/.codex/hooks" "$TMP/agentic_v3"
echo "def h(): return 1" > "$TMP/.codex/hooks/x.py"
echo "def e(): return 1" > "$TMP/agentic_v3/x.py"
git -C "$TMP" add -A && git -C "$TMP" commit -qm codex
SHA5=$(git -C "$TMP" rev-parse --short HEAD)
sym "$SHA5"
echo "def h(): return 2" > "$TMP/.codex/hooks/x.py"
run | grep -q 'stale' \
  || fail "without a marker, .codex IS source: the fallback must still nudge"
#    ...and the same for the kit's own code (T-00000388): in the kit's repo
#    agentic_v3/ IS the engine we maintain, so a change there must nudge too.
git -C "$TMP" checkout -q -- .codex/hooks/x.py
echo "def e(): return 2" > "$TMP/agentic_v3/x.py"
run | grep -q 'stale' \
  || fail "without a marker, agentic_v3 IS source: the fallback must still nudge"
# The kit also indexes the relocated engine. Its .agents/ path is excluded by
# the ordinary git diff, so the fallback needs its dedicated vendor check.
git -C "$TMP" checkout -q -- agentic_v3/x.py
mkdir -p "$TMP/.agents/vendor/agentic_v3"
echo "def e(): return 1" > "$TMP/.agents/vendor/agentic_v3/x.py"
git -C "$TMP" add -A && git -C "$TMP" commit -qm vendor-engine
sym "$(git -C "$TMP" rev-parse --short HEAD)"
: > "$TMP/.agents/IS_THE_KIT"
echo "def e(): return 2" > "$TMP/.agents/vendor/agentic_v3/x.py"
run | grep -q 'stale' \
  || fail "vendor-v3: in the kit, a vendor engine change must nudge"
git -C "$TMP" checkout -q -- .agents/vendor/agentic_v3/x.py
rm -f "$TMP/.agents/IS_THE_KIT"

# 6. POSITIVE ARM. With a vendoring marker the tree is a vendored kit, the builder
#    stops indexing .codex at the root, so the fallback must stop nudging for it —
#    otherwise the nudge is inextinguishable (T-00000033 all over again).
printf '.agents/bin/\n' > "$TMP/.agents/protected-paths.local"
git -C "$TMP" checkout -q -- agentic_v3/x.py
echo "def h(): return 2" > "$TMP/.codex/hooks/x.py"
[ -z "$(run)" ] || fail "with a marker, a .codex-only change must not nudge"
#    ...same for the kit's own code (T-00000388): under a marker the builder
#    stops indexing agentic_v3/ at the root, so an agentic_v3-only change must
#    be silent here too, or the nudge points at a refresh that changes nothing.
git -C "$TMP" checkout -q -- .codex/hooks/x.py
echo "def e(): return 2" > "$TMP/agentic_v3/x.py"
[ -z "$(run)" ] || fail "with a marker, an agentic_v3-only change must not nudge"
# In an adopting tree the builder does not index the vendor engine either.
git -C "$TMP" checkout -q -- agentic_v3/x.py
echo "def e(): return 2" > "$TMP/.agents/vendor/agentic_v3/x.py"
[ -z "$(run)" ] || fail "vendor-v3: with a vendoring marker, a vendor engine change must not nudge"
git -C "$TMP" checkout -q -- .agents/vendor/agentic_v3/x.py
#    ...and a real source change still does, in the same tree.
echo "export const a = 3;" > "$TMP/src/a.ts"
run | grep -q 'stale' || fail "a src change must nudge even in a vendored kit"
#    ...root-only, exactly like the builder: a workspace of the same name is source.
#    `git add` is not decoration: `git diff <sha> -- .` never reports an UNTRACKED
#    file, so an unstaged new file would make this arm pass for the wrong reason
#    (silence by invisibility, not by exclusion). Staging it puts the path in the
#    index, where the diff can see it — and the '.agents' / '.codex' paths staged
#    alongside stay out via the pathspec, which is what this arm is testing.
git -C "$TMP" checkout -q -- src/a.ts
mkdir -p "$TMP/packages/app/.codex"
echo "def deep(): return 1" > "$TMP/packages/app/.codex/deep.py"
git -C "$TMP" add -A
run | grep -q 'stale' || fail "packages/*/.codex is source: it must still nudge"
rm -rf "$TMP/packages" "$TMP/.agents/protected-paths.local"

# 7. no index file at all -> silent
printf '' > "$TMP/.agents/state/index/SYMBOLS.md" && : > "$TMP/.agents/state/index/SYMBOLS.md"
find "$TMP/.agents/state/index" -name 'SYMBOLS.md' -delete
[ -z "$(run)" ] || fail "missing index should be silent"

# --- the PROBE path (T-00000108) ---------------------------------------------
# Cases 1-7 above all exercise the git/mtime FALLBACK, because a toy repo carries
# no .agents/bin/build_index.py. The cases below exercise the OTHER branch: the
# builder's read-only probe, whose stdout this hook parses. The builder is
# STUBBED on purpose — what is under test here is the hook's reading of the two
# verdicts and the shape of what it prints, never the builder's computation of
# them (that is .agents/bin/test_build_index_atomic.py's job).
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ] || ! command -v timeout >/dev/null 2>&1; then
  # The same guard the hook applies. Without python or timeout(1) it takes the
  # fallback, which by design says NOTHING about the DB rather than guess.
  echo "PASS: stop-reindex (7/7; probe cases skipped - no python or no timeout(1))"
  exit 0
fi

mkdir -p "$TMP/.agents/bin"
cat > "$TMP/.agents/bin/build_index.py" <<'STUB'
import os, pathlib, sys
trace = os.environ.get("SR_TRACE")
if trace:
    with open(trace, "a", encoding="utf-8") as fh:
        fh.write("call\n")
print(pathlib.Path(__file__).with_name("PROBE_OUT").read_text(encoding="utf-8"), end="")
sys.stdout.flush()
sys.exit(int(os.environ.get("SR_PROBE_RC") or "0"))
STUB
# one canned probe output, one line per argument (ASCII only: a cp1252 console
# mangles the builder's real em dashes, which is why the hook parses hex, not prose)
probe() { printf '%s\n' "$@" > "$TMP/.agents/bin/PROBE_OUT"; }
json_ok() { printf '%s' "$1" | "$PY" -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; }
sym "$(git -C "$TMP" rev-parse --short HEAD)"

# 8. NEGATIVE ARM, first: the probe says the index is current and says nothing
#    about any DB -> total silence. A print that fires with nothing to say is the
#    T-00000033 defect, and it is the only way this feature can regress.
probe "INDEX CURRENT @ deadbee - nothing to rebuild"
OUT="$(run)"; RC=$?
[ -z "$OUT" ] || fail "an INDEX CURRENT probe with no DB line must stay silent (got: $OUT)"
[ "$RC" -eq 0 ] || fail "the hook must exit 0 (a non-zero Stop hook loops the host)"

# 9. SECOND NEGATIVE ARM: index stale, no DB line -> the historical message, and
#    NOT a word about --resync. This is what keeps cases 10-11 meaningful.
probe "INDEX STALE @ deadbee - a rebuild would change the index files"
OUT="$(run)"; RC=$?
[ "$RC" -eq 0 ] || fail "the hook must exit 0"
printf '%s' "$OUT" | grep -q 'build_index.py --if-stale' \
  || fail "an index-stale probe must still nudge the rebuild"
if printf '%s' "$OUT" | grep -q -- '--resync'; then
  fail "no DB line in the probe means no DB advice in the message"
fi
json_ok "$OUT" || fail "the systemMessage must be valid JSON"

# 10. THE MEASURED CASE of this very repo: index files CURRENT, the machine
#     index.db a generation behind. Nothing said this before T-00000108.
probe "INDEX CURRENT @ 43e44a3 - nothing to rebuild" \
      "DB STALE @ f483129 vs files @ 43e44a3 - the machine index.db (outside the repository) was built from another index generation; run python .agents/bin/migrate_index_to_db.py --resync - nothing to commit"
OUT="$(run)"; RC=$?
[ "$RC" -eq 0 ] || fail "the hook must exit 0"
printf '%s' "$OUT" | grep -q 'migrate_index_to_db.py --resync' \
  || fail "a stale DB must name the exact realignment command"
# NEGATIVE ARM (T-00000668): index.db is a machine store outside the repository,
# so no message may tell anyone to commit it any more.
if printf '%s' "$OUT" | grep -q 'commit.*index\.db'; then
  fail "a stale DB must never advise committing index.db (machine store, T-00000668)"
fi
printf '%s' "$OUT" | grep -q 'f483129' || fail "the message must carry the DB generation"
printf '%s' "$OUT" | grep -q '43e44a3' || fail "the message must carry the files generation"
if printf '%s' "$OUT" | grep -q -- '--if-stale'; then
  fail "a CURRENT index must not be reported as needing a rebuild"
fi
json_ok "$OUT" || fail "the systemMessage must be valid JSON"

# 11. BOTH stale -> both commands, in the order that converges (rebuild the files
#     first; a resync before the rebuild binds the DB to a doomed generation).
#     Also the JSON guard: the probe's SECOND line must never leak a raw newline
#     into the payload (a prefix-strip over the whole capture used to do exactly
#     that, and a payload with an embedded newline is not JSON).
probe "INDEX STALE @ 684ca89 - a rebuild would change the index files" \
      "DB STALE @ f483129 vs files @ 43e44a3 - the machine index.db (outside the repository) was built from another index generation"
OUT="$(run)"; RC=$?
[ "$RC" -eq 0 ] || fail "the hook must exit 0"
json_ok "$OUT" || fail "a two-line probe must still produce valid JSON (no raw newline)"
printf '%s' "$OUT" | grep -q 'build_index.py --if-stale' || fail "both stale: the rebuild must be named"
printf '%s' "$OUT" | grep -q 'migrate_index_to_db.py --resync' || fail "both stale: the resync must be named"
if printf '%s' "$OUT" | grep -q 'commit.*index\.db'; then
  fail "both stale: the message must never advise committing index.db (T-00000668)"
fi
REBUILD_AT=$(printf '%s' "$OUT" | grep -bo 'build_index.py --if-stale' | head -1 | cut -d: -f1)
RESYNC_AT=$(printf '%s' "$OUT" | grep -bo 'migrate_index_to_db.py --resync' | head -1 | cut -d: -f1)
[ "$REBUILD_AT" -lt "$RESYNC_AT" ] \
  || fail "the rebuild must be advised BEFORE the resync (else the DB is re-staled at once)"

# --- the PROBE CACHE (T-00000837) — witnessed by TRACE, never by a stopwatch --
# The stubbed builder appends one line per call to $SR_TRACE; an emit-event.sh
# spy in the fixture logs every event. The machine state root is pinned to a
# throwaway CADRE_STATE_DIR so the index.db arm never reads the real one.
SR_TRACE_F="$(mktemp)"; SR_EVT_F="$(mktemp)"; SR_ETAT_D="$(mktemp -d)"
trap 'rm -rf "$TMP" "$SR_TRACE_F" "$SR_EVT_F" "$SR_ETAT_D"' EXIT
mkdir -p "$TMP/.claude/hooks"
cat > "$TMP/.claude/hooks/emit-event.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SR_EVT"
STUB
runc() { CLAUDE_PROJECT_DIR="$TMP" SR_TRACE="$SR_TRACE_F" SR_EVT="$SR_EVT_F" CADRE_STATE_DIR="$SR_ETAT_D" bash "$HOOK"; }
calls() { wc -l < "$SR_TRACE_F" | tr -d ' '; }
SR_CACHE_F="$TMP/.agents/state/local/stop-reindex/sonde"
rm -rf "$TMP/.agents/state/local/stop-reindex"

# 12. unchanged inputs -> ONE probe for two Stops, the SAME bytes, and the
#     index.stale event re-emitted on the replay (no silent turn).
probe "INDEX STALE @ deadbee - a rebuild would change the index files"
A="$(runc)"; B="$(runc)"
[ "$(calls)" = "1" ] || fail "12: unchanged inputs must be answered by the cache: $(calls) probe call(s), expected 1"
[ -n "$A" ] || fail "12: the first Stop must nudge"
[ "$A" = "$B" ] || fail "12: the replayed message must be byte-identical (got [$A] then [$B])"
[ "$(grep -c '^index.stale' "$SR_EVT_F")" = "2" ] || fail "12: the replay must still emit index.stale ($(grep -c '^index.stale' "$SR_EVT_F") emission(s), expected 2)"

# 13. the NAMES the probe reads: a tracked file whose content now differs from
#     HEAD, then a second new file inside an ALREADY-untracked directory (the
#     -uall case: without it `git status` shows only `newdir/` both times).
echo "export const a = 3;" > "$TMP/src/a.ts"; runc >/dev/null
[ "$(calls)" = "2" ] || fail "13: a tracked file entering the diff must re-probe: $(calls) call(s), expected 2"
mkdir -p "$TMP/newdir"; echo x > "$TMP/newdir/one.ts"; runc >/dev/null
echo y > "$TMP/newdir/two.ts"; runc >/dev/null
[ "$(calls)" = "4" ] || fail "13: a new file inside an untracked dir must re-probe: $(calls) call(s), expected 4"
runc >/dev/null
[ "$(calls)" = "4" ] || fail "13: and then be cached again: $(calls) call(s), expected 4"

# 14. the CONTENT of the index files, under an UNCHANGED git status: the first
#     rewrite moves SYMBOLS.md to "modified in the worktree"; the second keeps
#     that exact status line, so only the content hash can see it.
sym "cafe123"; runc >/dev/null
[ "$(calls)" = "5" ] || fail "14: a rewritten index file must re-probe: $(calls) call(s), expected 5"
sym "beef456"; runc >/dev/null
[ "$(calls)" = "6" ] || fail "14: a second rewrite (same git status) must re-probe: $(calls) call(s), expected 6"

# 15. an incomplete answer is NEVER cached: IN FLIGHT (another build) twice.
probe "INDEX BUILD IN FLIGHT - skipped"; rm -f "$SR_CACHE_F"
runc >/dev/null; runc >/dev/null
[ "$(calls)" = "8" ] || fail "15: an IN FLIGHT answer must never be cached: $(calls) call(s), expected 8"
[ -e "$SR_CACHE_F" ] && fail "15: an IN FLIGHT answer must leave the cache EMPTY"

# 16. a build LOCK present -> the builder is asked even with a valid cache.
probe "INDEX STALE @ deadbee - a rebuild would change the index files"
runc >/dev/null; runc >/dev/null                                   # call 9, then a hit
[ "$(calls)" = "9" ] || fail "16: precondition — the stale answer must be cached: $(calls) call(s), expected 9"
: > "$TMP/.agents/state/local/.build_index.lock"; runc >/dev/null
rm -f "$TMP/.agents/state/local/.build_index.lock"
[ "$(calls)" = "10" ] || fail "16: a present build lock must bypass the cache: $(calls) call(s), expected 10"

# 17. the machine index.db: appearing re-probes; untouched is replayed; REWRITTEN
#     (a --resync) re-probes. `sleep 1` orders mtimes for bash 3.2's one-second
#     `-nt` — an ordering, not a stopwatch.
mkdir -p "$SR_ETAT_D/projets/abc/index"; : > "$SR_ETAT_D/projets/abc/index/index.db"
sleep 1; runc >/dev/null; runc >/dev/null
[ "$(calls)" = "11" ] || fail "17: a new index.db re-probes once, then is cached: $(calls) call(s), expected 11"
sleep 1; touch "$SR_ETAT_D/projets/abc/index/index.db"; runc >/dev/null
[ "$(calls)" = "12" ] || fail "17: a rewritten index.db (--resync) must re-probe: $(calls) call(s), expected 12"

# 18. a PARTIAL answer is never cached: the probe prints a complete-looking
#     "INDEX CURRENT @ abc" and then exits 124 (what timeout(1) returns when it
#     kills it — the DB line never came). The hook must not cache that output,
#     and must clear a cache it would otherwise leave behind.
#     `sleep 1`: arm 17 just touched index.db, and bash 3.2's `-nt` is to the
#     second — without it the witness below would miss on the DB mtime instead.
probe "INDEX CURRENT @ abc"; rm -f "$SR_CACHE_F"
sleep 1; SR_PROBE_RC=124 runc >/dev/null
[ -e "$SR_CACHE_F" ] && fail "18: a probe that exits 124 must leave the cache EMPTY (partial output)"
SR_PROBE_RC=124 runc >/dev/null
[ "$(calls)" = "14" ] || fail "18: after a partial answer the next Stop must re-probe: $(calls) call(s), expected 14"
runc >/dev/null; runc >/dev/null
[ "$(calls)" = "15" ] || fail "18: witness — the same output with rc 0 IS cached: $(calls) call(s), expected 15"

echo "PASS: stop-reindex (18/18, + 2 negative arms: no commit of index.db; 7 probe-cache arms by trace)"
