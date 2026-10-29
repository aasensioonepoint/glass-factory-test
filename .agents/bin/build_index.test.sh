#!/usr/bin/env bash
# Tests for build_index.py. Run: bash .agents/bin/build_index.test.sh
#
# Directives read by core-scripts/run-bash-tests.sh (T-00000427):
# requires: git
# optional: ctags
# allows-missing: python python3 py
#
# `git` is REQUIRED rather than auto-skipped, and the difference is the whole
# point: 18 call sites below build and commit the fixture repo, so WITHOUT git
# this suite proves nothing — and it used to say so with `exit 0`, which the
# runner read as a pass. The runner now declines to run it and reports a missing
# dependency, which is red. Two judges for one dependency is how a blind judge
# gets built, so the `command -v git` escape that lived here is gone.
#
# `ctags` is genuinely OPTIONAL: the ctags-only assertions (:144, :309) carry
# their own guard and the stdlib fallback still exercises everything else.
#
# `allows-missing` covers the interpreter probe two lines down. It EXECUTES each
# of three names in turn, so on a box carrying only python3 the names `python`
# and `py` legitimately fail to resolve — without this line the runner's
# swallowed-127 sensor would blame the suite for its own probe. It stays a probe
# instead of becoming a `requires:` header because that header names ONE command
# and this is a three-name ALTERNATIVE: it would red a box that has python3. If
# none of the three resolve, the SKIP below is now counted by the runner's
# survey, so that path is no longer silent either.
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/build_index.py"
PY=""; for c in python python3 py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -z "$PY" ] && { echo "SKIP: no python"; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SYM="$TMP/.agents/state/index/SYMBOLS.md"
DELTA="$TMP/.agents/state/index/INDEX_DELTA.json"
fail() { echo "FAIL: $1"; exit 1; }
symid() { grep -oE 'SYM-[0-9]+' <<<"$1" | head -1; }

mkdir -p "$TMP/src/auth" "$TMP/src/api"
cat > "$TMP/src/auth/session.py" <<'PYF'
def create_session(user):
    token = mint_token(user)
    return token

def mint_token(user):
    return "t"

class SessionStore:
    def get(self, key):
        return None
PYF
cat > "$TMP/src/api/users.ts" <<'TSF'
export function listUsers() {
  return buildQuery();
}
export function buildQuery() {
  return "q";
}
export const PAGE_SIZE = 20;
TSF

git -C "$TMP" init -q
git -C "$TMP" config user.email t@t
git -C "$TMP" config user.name t
git -C "$TMP" add -A && git -C "$TMP" commit -qm init

# 1. full build extracts symbols + kinds across languages
"$PY" "$SCRIPT" --root "$TMP" >/dev/null
[ -f "$SYM" ] || fail "SYMBOLS.md not written"
grep -q 'built @ ' "$SYM" || fail "no built@ anchor"
grep -q 'create_session  function' "$SYM" || fail "py function not extracted"
grep -q 'SessionStore  class' "$SYM"      || fail "py class not extracted"
grep -q 'listUsers  function' "$SYM"      || fail "ts function not extracted"
grep -q 'PAGE_SIZE  const' "$SYM"         || fail "ts const not extracted"

# 2. approximate edges resolve to real SYM ids
MINT=$(symid "$(grep 'mint_token  function' "$SYM")"); [ -n "$MINT" ] || fail "no id for mint_token"
BQ=$(symid "$(grep 'buildQuery  function' "$SYM")");   [ -n "$BQ" ]   || fail "no id for buildQuery"
grep 'create_session  function' "$SYM" | grep -q "uses\[.*$MINT.*\]" || fail "edge create_session->mint_token missing"
grep 'listUsers  function' "$SYM"      | grep -q "uses\[.*$BQ.*\]"   || fail "edge listUsers->buildQuery missing"

# 3. delta flags new symbols as needing a purpose
grep -q '"needs_purpose"' "$DELTA" || fail "no needs_purpose in delta"
CS_ID=$(symid "$(grep 'create_session  function' "$SYM")")
grep -q "$CS_ID" "$DELTA" || fail "new symbol not in delta"

# 4. incremental build: stable SYM ids, new symbol appended
printf '\ndef revoke_session(token):\n    return None\n' >> "$TMP/src/auth/session.py"
git -C "$TMP" add -A && git -C "$TMP" commit -qm add
"$PY" "$SCRIPT" --root "$TMP" >/dev/null
CS_AFTER=$(symid "$(grep 'create_session  function' "$SYM")")
[ "$CS_ID" = "$CS_AFTER" ] || fail "SYM id not stable ($CS_ID -> $CS_AFTER)"
grep -q 'revoke_session  function' "$SYM" || fail "incremental: new symbol missing"

# 5. removed symbols are tombstoned, not renumbered
cat > "$TMP/src/auth/session.py" <<'PYF'
def create_session(user):
    return None
PYF
git -C "$TMP" add -A && git -C "$TMP" commit -qm del
"$PY" "$SCRIPT" --root "$TMP" >/dev/null
grep -q "$MINT  DELETED  mint_token" "$SYM" || fail "removed symbol not tombstoned with its id"
grep -q 'create_session  function' "$SYM"   || fail "surviving symbol lost"

# 6. shard past the threshold
"$PY" "$SCRIPT" --root "$TMP" --full --threshold 1 >/dev/null
grep -qi 'index-of-indexes' "$SYM" || fail "sharding: no index-of-indexes"
ls "$TMP/.agents/state/index/"SYMBOLS_*.md >/dev/null 2>&1 || fail "sharding: no shard files"

# ---------------------------------------------------------------- scale (P0)
CB="$TMP/.agents/state/index/CODEBASE_INDEX.md"

# 7. SKIP_DIRS applies to the `git ls-files` path, not just the os.walk one
mkdir -p "$TMP/vendor" "$TMP/node_modules/pkg"
echo 'def vendored_helper(x): return x' > "$TMP/vendor/dep.py"
echo 'export function bundledThing() { return 1; }' > "$TMP/node_modules/pkg/i.js"
git -C "$TMP" add -A -f && git -C "$TMP" commit -qm vendor
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
grep -rq 'vendored_helper' "$TMP/.agents/state/index/" && fail "vendor/ indexed despite SKIP_DIRS"
grep -rq 'bundledThing' "$TMP/.agents/state/index/" && fail "node_modules/ indexed despite SKIP_DIRS"

# 8. CODEBASE_INDEX.md is generated deterministically, with a module table
[ -f "$CB" ] || fail "CODEBASE_INDEX.md not written"
grep -q '^## Modules' "$CB" || fail "no Modules table"
grep -q '^## Entry points' "$CB" || fail "no Entry points section"
grep -q '"needs_module_role"' "$DELTA" || fail "needs_module_role missing from delta"

# 9. hand-written Role/Owner cells survive a rebuild (they are LLM work)
"$PY" - "$CB" <<'PYEOF'
import re, sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().splitlines()
for i, l in enumerate(lines):
    m = re.match(r"^\| (?!Path )([^|]+?) \| — \| (.*) \| — \|$", l)
    if m:                                      # first module row with an empty Role
        lines[i] = f"| {m.group(1)} | Auth and API | {m.group(2)} | dev-multi |"
        break
else:
    sys.exit("no empty Role row to edit")
open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PYEOF
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
grep -q 'Auth and API' "$CB" || fail "indexer-written Role cell clobbered on rebuild"

# 10. $CTAGS is honored; a bogus value degrades to PATH instead of blowing up
"$PY" - "$SCRIPT" <<'PYEOF' || fail "ctags_binary() env resolution"
import importlib.util, os, shutil, sys
spec = importlib.util.spec_from_file_location("bi", sys.argv[1])
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
os.environ.pop("CTAGS_PATH", None)
real = shutil.which("ctags")
os.environ["CTAGS"] = "/definitely/not/ctags"
got = m.ctags_binary()                      # must not raise
if real and m._is_universal_ctags(real) and not got:
    sys.exit("bogus $CTAGS suppressed a working PATH ctags")
if real and m._is_universal_ctags(real):
    os.environ["CTAGS"] = real
    if not m.ctags_binary():
        sys.exit("$CTAGS pointing at a real ctags was not honored")
    print("  $CTAGS honored ->", real)
else:
    print("  note: no universal-ctags on PATH; env test partial")
PYEOF

# ctags-only assertions — the fallback has its own (looser) kind vocabulary
if command -v ctags >/dev/null 2>&1 && ctags --version 2>&1 | grep -q "Universal Ctags"; then
  mkdir -p "$TMP/src/jv"
  cat > "$TMP/src/jv/A.java" <<'JF'
package com.example;
class Widget {
  private int hiddenField;
  public int compute() {
    return hiddenField;
  }
}
JF
  cat > "$TMP/src/jv/big.ts" <<'TF'
export function spansManyLines(a) {
  const step1 = a + 1;
  const step2 = step1 * 2;
  return step2;
}
TF
  git -C "$TMP" add -A && git -C "$TMP" commit -qm kinds
  "$PY" "$SCRIPT" --root "$TMP" --full >/dev/null

  # 11. non-structural ctags kinds are dropped (they 3-4x the index at scale)
  grep -rq 'hiddenField' "$TMP/.agents/state/index/" && fail "ctags 'field' kind not filtered out"
  grep -rq '  package  ' "$TMP/.agents/state/index/" && fail "ctags 'package' kind not filtered out"
  grep -rq 'Widget  class' "$TMP/.agents/state/index/" || fail "structural kind 'class' wrongly dropped"

  # 12. end lines are derived for parsers that report none (TS/JS, Ruby, PHP, C#)
  RANGE=$(grep -rho 'big\.ts:[0-9]*-[0-9]*' "$TMP/.agents/state/index/" | head -1)
  [ -n "$RANGE" ] || fail "ts symbol missing from index"
  S=${RANGE##*:}; START=${S%%-*}; END=${S##*-}
  [ "$END" -gt "$START" ] || fail "ts end line not derived (collapsed to $RANGE)"
  echo "  ts range derived: $RANGE"
fi

# 13. a full rebuild purges symbols whose file left the source set entirely
mkdir -p "$TMP/src/tmpmod"
echo 'def doomed_symbol(x): return x' > "$TMP/src/tmpmod/gone.py"
git -C "$TMP" add -A && git -C "$TMP" commit -qm doomed
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
grep -rq 'doomed_symbol' "$TMP/.agents/state/index/" || fail "setup: doomed_symbol not indexed"
git -C "$TMP" rm -q "src/tmpmod/gone.py" && git -C "$TMP" commit -qm undoomed
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
grep -rq 'DELETED  doomed_symbol' "$TMP/.agents/state/index/" \
  || fail "full rebuild did not tombstone a symbol whose file is gone"
grep -rq 'gone\.py:' "$TMP/.agents/state/index/" && fail "stale path survived the purge"

# ------------------------------------------------------------- P1/P2 hardening
# 14. generated / minified / oversized files are not indexed
mkdir -p "$TMP/src/gen"
echo 'export function minifiedThing(){}' > "$TMP/src/gen/app.min.js"
echo 'def proto_symbol(x): return x'     > "$TMP/src/gen/schema_pb2.py"
echo 'export function typedOnly(){}'     > "$TMP/src/gen/types.d.ts"
"$PY" - "$TMP/src/gen/huge.py" <<'PYEOF'
import sys
with open(sys.argv[1], "w", encoding="utf-8") as f:
    f.write("def huge_symbol(x): return x\n")
    f.write("# pad\n" * 300000)          # > MAX_FILE_BYTES
PYEOF
git -C "$TMP" add -A && git -C "$TMP" commit -qm generated
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
for s in minifiedThing proto_symbol typedOnly huge_symbol; do
  grep -rq "$s" "$TMP/.agents/state/index/" && fail "$s indexed (should be filtered)"
done

# 15. SYM ids are fixed-width, so `grep SYM-x` cannot match a longer id
"$PY" - "$SCRIPT" "$TMP" <<'PYEOF' || fail "id width"
import importlib.util, sys
spec = importlib.util.spec_from_file_location("bi", sys.argv[1])
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
m.set_id_width(1200)
a, b = m.sid(102), m.sid(1020)
if a in b:
    sys.exit(f"{a} is a prefix of {b} — grep for callers would over-match")
if len(a) != len(b):
    sys.exit("ids are not fixed-width within a build")
m.set_id_width(5)                        # small repos stay on the 3-digit form
if m.sid(7) != "SYM-007":
    sys.exit(f"small-repo id format changed: {m.sid(7)}")
PYEOF

# 16. a large module is split across capped shards, not one giant one
"$PY" - "$TMP" <<'PYEOF'
import pathlib, sys
d = pathlib.Path(sys.argv[1]) / "src" / "bigmod"
d.mkdir(parents=True, exist_ok=True)
for f in range(13):                      # 2600 symbols > MAX_SHARD_ENTRIES (2000)
    (d / f"part{f}.py").write_text(
        "".join(f"def big_{f}_{i}(a):\n    return a\n" for i in range(200)),
        encoding="utf-8")
PYEOF
git -C "$TMP" add -A && git -C "$TMP" commit -qm bigmod
"$PY" "$SCRIPT" --root "$TMP" --full --threshold 100 >/dev/null
ls "$TMP/.agents/state/index/"SYMBOLS_bigmod_1.md >/dev/null 2>&1 \
  || fail "oversized module was not split into numbered shards"
BIGGEST=$("$PY" - "$TMP" <<'PYEOF'
import pathlib, sys
d = pathlib.Path(sys.argv[1]) / ".agents" / "state" / "index"
print(max(sum(1 for _ in p.open(encoding="utf-8")) for p in d.glob("SYMBOLS_*.md")))
PYEOF
)
[ "$BIGGEST" -le 2010 ] || fail "a shard holds $BIGGEST lines, past the cap"
grep -q 'index-of-indexes' "$SYM" || fail "TOC missing after capped sharding"

# 17. uses[] never points at a tombstoned symbol
grep -rhoE 'uses\[[^]]*\]' "$TMP/.agents/state/index/"SYMBOLS*.md | tr ',' '\n' \
  | grep -oE 'SYM-[0-9]+' | sort -u > "$TMP/refs.txt"
grep -rhoE '^SYM-[0-9]+  DELETED' "$TMP/.agents/state/index/"SYMBOLS*.md \
  | grep -oE 'SYM-[0-9]+' | sort -u > "$TMP/dead.txt"
DANGLING=$(comm -12 "$TMP/refs.txt" "$TMP/dead.txt" | head -3)
[ -z "$DANGLING" ] || fail "uses[] references tombstoned symbols: $DANGLING"

# 18. edge resolution prefers the local definition over a same-named distant one
mkdir -p "$TMP/src/near" "$TMP/src/far"
cat > "$TMP/src/far/dup.py" <<'PYF'
def shared_target(x):
    return x
PYF
cat > "$TMP/src/near/dup.py" <<'PYF'
def shared_target(x):
    return x

def local_caller(x):
    return shared_target(x)
PYF
git -C "$TMP" add -A && git -C "$TMP" commit -qm locality
"$PY" "$SCRIPT" --root "$TMP" --full >/dev/null
NEAR=$(grep -rh 'src/near/dup.py.*shared_target  function' "$TMP/.agents/state/index/" | grep -oE '^SYM-[0-9]+')
CALLER=$(grep -rh 'local_caller  function' "$TMP/.agents/state/index/")
echo "$CALLER" | grep -q "$NEAR" || fail "edge did not prefer the same-file definition ($NEAR)"

# 19. hexagonal Gradle layouts: `adapter/out/` is source, `<module>/build/` is not,
#     and src/main/java/<group>/ does not flatten every layer into one "main"
HEX="$TMP/hex"
mkdir -p "$HEX/backend/src/main/java/com/acme/domain" \
         "$HEX/backend/src/main/java/com/acme/adapter/out/persistence" \
         "$HEX/backend/src/main/java/com/acme/adapter/in/web" \
         "$HEX/backend/build/generated/source" "$HEX/out"
printf 'plugins { id("java") }\n' > "$HEX/backend/build.gradle"
printf 'package com.acme.domain;\npublic class Order { public void pay(){} }\n' \
  > "$HEX/backend/src/main/java/com/acme/domain/Order.java"
printf 'package com.acme.adapter.out.persistence;\npublic class OrderRepo { public void save(){} }\n' \
  > "$HEX/backend/src/main/java/com/acme/adapter/out/persistence/OrderRepo.java"
printf 'package com.acme.adapter.in.web;\npublic class OrderApi { public void post(){} }\n' \
  > "$HEX/backend/src/main/java/com/acme/adapter/in/web/OrderApi.java"
printf 'package gen;\npublic class Generated { public void x(){} }\n' \
  > "$HEX/backend/build/generated/source/Generated.java"
printf 'package top;\npublic class TopOut { public void y(){} }\n' > "$HEX/out/TopOut.java"
git -C "$HEX" init -q && git -C "$HEX" config user.email t@t && git -C "$HEX" config user.name t
git -C "$HEX" add -A && git -C "$HEX" commit -qm hex
"$PY" "$SCRIPT" --root "$HEX" --full >/dev/null
HSYM="$HEX/.agents/state/index/SYMBOLS.md"
# These four assertions read Java symbols out of the index, so they REQUIRE
# universal-ctags: the stdlib fallback parses only .py/.ts/.js, so without it the
# .java fixtures above yield NO symbols at all — the two keep-assertions then
# false-RED and the two prune-assertions pass by the VOID (no symbol either way).
# Guarded exactly like the ctags-only block earlier in this file. Measured cause
# of T-00000324: the Windows CI leg USED TO ship no universal-ctags, so case 19
# turned red here under the misleading "pruned as build output" label while the
# pruning predicate was correct all along (proven green on any ctags-equipped
# box). T-00000325 then pinned a universal-ctags release by sha256 on the Windows
# leg (ci.yml, step "Install system deps (Windows, ctags pinned)"), so case 19
# now runs there too — but the guard STAYS: the macOS leg, and any box without
# ctags, still take the fallback, and this predicate must not false-RED there.
# The pruning code is platform-agnostic Python, so the ubuntu leg (ctags
# installed) still exercises it in full; module_of below needs no ctags and stays live.
if command -v ctags >/dev/null 2>&1 && ctags --version 2>&1 | grep -q "Universal Ctags"; then
  grep -q 'OrderRepo' "$HSYM" || fail "hexagonal adapter/out/ pruned as build output"
  grep -q 'OrderApi'  "$HSYM" || fail "hexagonal adapter/in/ not indexed"
  grep -q 'Generated' "$HSYM" && fail "<module>/build/ (next to build.gradle) was indexed"
  grep -q 'TopOut'    "$HSYM" && fail "top-level out/ was indexed"
fi
MODOF=$("$PY" - "$SCRIPT" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("bi", sys.argv[1])
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
print(",".join(m.module_of(p) for p in [
    "src/main/java/com/acme/domain/Order.java",
    "src/main/kotlin/com/acme/adapter/out/Repo.kt",
    "backend/src/main/java/com/acme/domain/Order.java",
    "packages/ui/src/index.ts", "src/utils/date.ts", "main.py"]))
PYEOF
)
[ "$MODOF" = "domain,adapter,backend,ui,utils,(root)" ] \
  || fail "module_of regressed: $MODOF"

# ------------------------------------------- atomic publish / lock / --if-stale
IDXD="$TMP/.agents/state/index"
LOCK="$TMP/.agents/state/local/.build_index.lock"
# sha of the whole index directory — proves a run wrote nothing at all
idxhash() { "$PY" - "$1" <<'PYEOF'
import hashlib, pathlib, sys
d = pathlib.Path(sys.argv[1]) / ".agents" / "state" / "index"
h = hashlib.sha256()
for p in sorted(d.iterdir()):
    h.update(p.name.encode("utf-8")); h.update(p.read_bytes())
print(h.hexdigest())
PYEOF
}

# 20. publication is staged in a temp file and moved in — nothing is left behind
ls "$IDXD"/._tmp_* >/dev/null 2>&1 && fail "staging file left in the index dir"
grep -q '"max_sym_id"' "$DELTA" || fail "delta carries no SYM-ID watermark"

# 21. a same-generation orphan shard is watermark-only, never merged, then dropped
CS_BEFORE=$(grep -rhE '^SYM-[0-9]+  .*create_session  function' "$IDXD" | grep -oE '^SYM-[0-9]+' | head -1)
[ -n "$CS_BEFORE" ] || fail "setup: create_session not indexed"
FIRST=$(grep -lE '^SYM-[0-9]+  [^ ]+:[0-9]+-[0-9]+' "$IDXD"/SYMBOLS_*.md | head -1)
[ -n "$FIRST" ] || fail "setup: no shard with an active row"
cp "$FIRST" "$IDXD/SYMBOLS_zzorphan.md"          # sorts AFTER the live shards
"$PY" - "$IDXD/SYMBOLS_zzorphan.md" <<'PYEOF'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
# Claim an absurd range for the first active row: if the orphan were merged, the
# next build would carry 9001-9002 forward (last-writer-wins over by_key).
t, n = re.subn(r"^(SYM-\d+  \S+):\d+-\d+", r"\1:9001-9002", t, count=1, flags=re.M)
if not n:
    sys.exit("could not mutate the orphan shard")
open(p, "w", encoding="utf-8").write(t)
PYEOF
"$PY" "$SCRIPT" --root "$TMP" >/dev/null
[ -f "$IDXD/SYMBOLS_zzorphan.md" ] && fail "same-generation orphan shard not dropped after publish"
grep -rq ':9001-9002' "$IDXD" && fail "orphan shard was merged into identity (L-023)"
CS_AFTER=$(grep -rhE '^SYM-[0-9]+  .*create_session  function' "$IDXD" | grep -oE '^SYM-[0-9]+' | head -1)
[ "$CS_BEFORE" = "$CS_AFTER" ] || fail "orphan handling reallocated ids ($CS_BEFORE -> $CS_AFTER)"

# 22. --if-stale is a no-op, with zero writes, when the index already matches HEAD
# -c advice.addEmbeddedRepo: case 19 left a nested repo in $TMP/hex on purpose
git -C "$TMP" -c advice.addEmbeddedRepo=false add -A && git -C "$TMP" commit -qm ifstale
"$PY" "$SCRIPT" --root "$TMP" >/dev/null          # index now anchored on HEAD
H_BEFORE=$(idxhash "$TMP")
"$PY" "$SCRIPT" --root "$TMP" --if-stale | grep -q 'INDEX CURRENT @' \
  || fail "--if-stale rebuilt an index that already matches HEAD"
[ "$H_BEFORE" = "$(idxhash "$TMP")" ] || fail "--if-stale wrote to a current index"

# 23. --if-stale still rebuilds once a source file changes
printf '\ndef stale_probe(x):\n    return x\n' >> "$TMP/src/auth/session.py"
"$PY" "$SCRIPT" --root "$TMP" --if-stale | grep -q 'INDEX BUILT @' \
  || fail "--if-stale skipped a stale index"
grep -rq 'stale_probe' "$IDXD" || fail "--if-stale did not index the new symbol"

# 24. --full overrides --if-stale even when the index is current
git -C "$TMP" -c advice.addEmbeddedRepo=false add -A && git -C "$TMP" commit -qm probe
"$PY" "$SCRIPT" --root "$TMP" >/dev/null
"$PY" "$SCRIPT" --root "$TMP" --if-stale | grep -q 'INDEX CURRENT @' \
  || fail "setup: index not current before the --full precedence check"
"$PY" "$SCRIPT" --root "$TMP" --if-stale --full | grep -q 'INDEX BUILT @' \
  || fail "--full did not override --if-stale"

# 25. single-flight: a fresh lock skips the build without touching the index
mkdir -p "$(dirname "$LOCK")"
printf '999999 %s\n' "$(date +%s)" > "$LOCK"
H_BEFORE=$(idxhash "$TMP")
"$PY" "$SCRIPT" --root "$TMP" | grep -q 'INDEX BUILD IN FLIGHT' \
  || fail "a held lock did not skip the build"
[ "$H_BEFORE" = "$(idxhash "$TMP")" ] || fail "a skipped build still wrote the index"

# 26. a lock older than the stale window is stolen, and released afterwards
"$PY" - "$LOCK" <<'PYEOF'
import os, sys, time
old = time.time() - 4000                   # > LOCK_STALE_SECONDS (300)
os.utime(sys.argv[1], (old, old))
PYEOF
"$PY" "$SCRIPT" --root "$TMP" | grep -q 'INDEX BUILT @' || fail "stale lock was not stolen"
[ -f "$LOCK" ] && fail "lock not released after the build"

# 27. a fresh clone has no state/local/ and no state/index/: both get created
FRESH="$TMP/fresh"
mkdir -p "$FRESH/src"
echo 'def fresh_symbol(x): return x' > "$FRESH/src/f.py"
git -C "$FRESH" init -q && git -C "$FRESH" config user.email t@t \
  && git -C "$FRESH" config user.name t
git -C "$FRESH" add -A && git -C "$FRESH" commit -qm fresh
"$PY" "$SCRIPT" --root "$FRESH" >/dev/null
grep -q 'fresh_symbol' "$FRESH/.agents/state/index/SYMBOLS.md" \
  || fail "bare tree: symbol not indexed"
grep -q '"max_sym_id"' "$FRESH/.agents/state/index/INDEX_DELTA.json" \
  || fail "bare tree: watermark not reserved (needs its own mkdir)"
ls "$FRESH/.agents/state/index/"._tmp_* >/dev/null 2>&1 && fail "bare tree: staging file left behind"

# 28. T-00000541 — .sh reaches the index through the CLI, and the Python that
# lives INSIDE a shell script does not. Three constraints hold on this fixture
# and none is cosmetic: it owns a SEPARATE repo root, so the case-11 greps that
# sweep the whole of "$TMP/.agents/state/index/" cannot ever see it; it declares
# no function named `package` and never spells `hiddenField`, so it could not
# red them even if it landed there; and it uses no `cd` at all, because SC2164
# is not in the closed exclusion list of .agents/security/shellcheck-scan.sh.
if command -v ctags >/dev/null 2>&1 && ctags --version 2>&1 | grep -q "Universal Ctags"; then
  SHREPO="$TMP/shellrepo"
  SHIDX="$SHREPO/.agents/state/index"
  mkdir -p "$SHREPO/tools"
  cat > "$SHREPO/tools/release.sh" <<'SHF'
#!/usr/bin/env bash
set -e

publish_release() {
  local tag="$1"
  echo "publishing $tag"
}

collect_rows() {
  "$PY" -c '
import hashlib
rows = [r.strip() for r in open("in.txt").read().splitlines()]
key = hashlib.sha256(rows[0].encode()).hexdigest()
'
  "$PY" - <<'PYEOF'
print("embedded")
PYEOF
}
SHF
  git -C "$SHREPO" init -q && git -C "$SHREPO" config user.email t@t \
    && git -C "$SHREPO" config user.name t
  git -C "$SHREPO" add -A && git -C "$SHREPO" commit -qm shell
  "$PY" "$SCRIPT" --root "$SHREPO" --full >/dev/null

  grep -rqE 'release\.sh:[0-9]+-[0-9]+  publish_release  function' "$SHIDX/" \
    || fail "a bash function did not reach the index"
  grep -rq 'collect_rows' "$SHIDX/" || fail "the second bash function is missing"
  grep -rq 'PYEOF' "$SHIDX/" && fail "a heredoc delimiter was published as a symbol"
  grep -rq 'hexdigest' "$SHIDX/" && fail "an embedded-Python dotted name was published"
  SHRANGE=$(grep -rho 'release\.sh:[0-9]*-[0-9]*' "$SHIDX/" | head -1)
  [ -n "$SHRANGE" ] || fail "no shell symbol range in the index"
  SHS=${SHRANGE##*:}; SHSTART=${SHS%%-*}; SHEND=${SHS##*-}
  [ "$SHEND" -gt "$SHSTART" ] || fail "shell end line not derived (collapsed to $SHRANGE)"
  echo "  shell range derived: $SHRANGE"
else
  echo "  SKIP 28: no universal-ctags on PATH (shell extraction not exercised)"
fi

echo "PASS: build_index (28/28)"
