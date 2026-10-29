#!/usr/bin/env bash
# Tests for run-recap.sh. Run: bash .claude/hooks/run-recap.test.sh
set -e
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
# Resolve a WORKING interpreter — macOS ships only `python3`, never bare `python`;
# probe by execution, like run-recap.sh itself (a stub can exist yet fail to run).
PYBIN=""; for _c in python3 python py; do "$_c" --version >/dev/null 2>&1 && { PYBIN="$_c"; break; }; done
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# T-00000726 (R25, même ligne que T-00000753 dans les autres bancs) : joué DIRECTEMENT, ce banc isole son
# état machine — il jette le stderr de tasks.py, où seul se dit un pont REFUSÉ. Une valeur déjà posée est RESPECTÉE.
if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi
export CLAUDE_PROJECT_DIR="$TMP"
mkdir -p "$TMP/.agents/state/local"
LOG="$TMP/.agents/state/local/RUN_LOG.md"
fail() { echo "FAIL: $1"; exit 1; }

# 1. no est rows -> silent, exit 0
printf '# Run log\n| agent | est | actual | note |\n|-------|-----|--------|------|\n' > "$LOG"
OUT=$(bash "$HERE/run-recap.sh")
[ -z "$OUT" ] || fail "should be silent without forecast rows"

# 2. est+actual rows -> recap with delta flag, then file cleared
cat > "$LOG" <<'EOF'
# Run log
| agent | est | actual | note |
|-------|-----|--------|------|
| planner | ~8k | 7.8k |  |
| dev-multi | ~15k | 22.4k |  |
EOF
OUT=$(bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'RECAP \[source: hook\]' || fail "no recap header"
echo "$OUT" | grep -q '+49%' || fail "dev-multi delta not flagged"
echo "$OUT" | grep -q 'TOKEN_BUDGETS' || fail "tuning hint missing"
if grep -q '| planner |' "$LOG"; then fail "log not cleared"; fi

# 3. missing hook binary path never fails the session
OUT=$(bash "$HERE/run-recap.sh")   # log is now header-only
[ -z "$OUT" ] || fail "cleared log should be silent"

# 4. the BOARD headline actually reaches the recap.
# AGENTS.md promises the running task is "echoed in the Stop recap", but nothing
# asserted it — and board_line() loaded tasks.py from the board's OWN directory,
# correct only while TASKS.json still lived in .agents/bin/ (commit ee3c930).
# The bin/ref/state split (4b447c1) moved the store and left the path stale, so
# every call raised FileNotFoundError straight into `except Exception: return ""`
# and the headline silently never appeared again. This case pins it.
REPO="$(mktemp -d)"
mkdir -p "$REPO/.agents/state/local" "$REPO/.agents/bin"
# The copy ALLOCATES (`new`), so it carries its two allocation siblings too (T-00000726, E13):
# record_id.py next to tasks*.py, and the generator src/cadre/ledger/ids.py at parents[2].
# T-01M5BXTPQE3JZV3KZA6WD9P5XC (S-01M5BXT85VP4JBBMXVXR9STP5F) : the SOURCE is the `cadre`
# package `vendor_paths.exiger` names under this kit (new `.agents/vendor/cadre` first, old
# `src/cadre` next), vendor_paths loaded BY PATH; the DESTINATION stays `src/cadre/ledger/` —
# the copy carries no vendor_paths.py, so record_id.py's fallback (record_id.py:98-103) reads there.
cp "$HERE"/../../.agents/bin/tasks*.py "$HERE"/../../.agents/bin/record_id.py "$REPO/.agents/bin/"
KIT="$(cd "$HERE/../.." && pwd)"
CADRE_PKG="$("$PYBIN" -I -B -c 'import importlib.util as u, sys
s = u.spec_from_file_location("vendor_paths", sys.argv[1])
m = sys.modules[s.name] = u.module_from_spec(s); s.loader.exec_module(m)
sys.stdout.write(m.exiger(sys.argv[2], "cadre").as_posix())' "$KIT/.agents/bin/vendor_paths.py" "$KIT")" \
  || fail "cadre package not found under $KIT (vendor_paths.exiger)"
mkdir -p "$REPO/src/cadre/ledger" && cp "$CADRE_PKG/ledger/ids.py" "$REPO/src/cadre/ledger/"
# CLAUDE_PROJECT_DIR, not cwd, is what tasks.py resolves its store from — and
# this file exports it to $TMP at the top. Without the per-call override the
# board lands in $TMP and this fixture silently tests an empty $REPO.
# The id is the one `new` RETURNED, never a predicted one (T-00000726, R-BANCS (i)).
TID=$(CLAUDE_PROJECT_DIR="$REPO" "$PYBIN" "$REPO/.agents/bin/tasks.py" new "Board headline reaches the recap" --owner dev-mono 2>/dev/null | sed -n 's/^TASKS: \(T-[0-9A-HJKMNP-TV-Z]*\) .*/\1/p')
[ -n "$TID" ] || fail "new did not report the id it allocated"
CLAUDE_PROJECT_DIR="$REPO" "$PYBIN" "$REPO/.agents/bin/tasks.py" start "$TID" --stage dev-mono >/dev/null 2>&1
[ -f "$REPO/.agents/state/board/TASKS.json" ] || fail "fixture board was not created in \$REPO"
cat > "$REPO/.agents/state/local/RUN_LOG.md" <<'EOF'
# Run log
| agent | est | actual | note |
|-------|-----|--------|------|
| planner | ~8k | 7.9k |  |
EOF
OUT=$(CLAUDE_PROJECT_DIR="$REPO" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'BOARD' || fail "recap dropped the BOARD headline: $OUT"
echo "$OUT" | grep -q "$TID" || fail "BOARD headline lost the running task id: $OUT"

# 5. no running task -> no BOARD line (the headline must not fire on an idle board)
CLAUDE_PROJECT_DIR="$REPO" "$PYBIN" "$REPO/.agents/bin/tasks.py" done "$TID" --raison "clos par le banc" >/dev/null 2>&1
cat > "$REPO/.agents/state/local/RUN_LOG.md" <<'EOF'
# Run log
| agent | est | actual | note |
|-------|-----|--------|------|
| planner | ~8k | 7.9k |  |
EOF
OUT=$(CLAUDE_PROJECT_DIR="$REPO" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'BOARD' && fail "BOARD headline fired with no active task: $OUT"
rm -rf "$REPO"

# 6. R1 (T-00001012) — the board in RECORD form ONLY (`board/tasks/<id>.json`, the home fixed by
# S-01M4N1G4VXD01A3W54Y9FR9856) carries the BOARD headline like the monolith does. The content goes
# through the API (`statusline`, stubbed here), never read raw. Red at the base (guard on TASKS.json
# alone). Mutant that reddens: guard back to the monolith alone.
REPO2="$(mktemp -d)"
mkdir -p "$REPO2/.agents/bin" "$REPO2/.agents/state/board/tasks"
printf 'def statusline(root):\n    return "STUB-STATUSLINE T-00000001 running"\n' > "$REPO2/.agents/bin/tasks.py"
printf '{"format": 1, "id": "T-00000001", "record": {"id": "T-00000001"}, "sync_operations": []}\n' \
  > "$REPO2/.agents/state/board/tasks/T-00000001.json"
OUT=$(CLAUDE_PROJECT_DIR="$REPO2" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'BOARD STUB-STATUSLINE' || fail "R1: board in record form only, BOARD headline missing: $OUT"

# 7. R2 CONTROL — `tasks/` holds no record (empty but for a DOTTED name, the temp of an atomic
# write): no BOARD headline. Mutants that redden: a bare `tasks/` folder as guard; a dotted name counted.
rm -f "$REPO2/.agents/state/board/tasks/T-00000001.json"
printf '{}\n' > "$REPO2/.agents/state/board/tasks/.T-00000002.json"
OUT=$(CLAUDE_PROJECT_DIR="$REPO2" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'BOARD' && fail "R2: tasks/ without a record, no BOARD headline expected: $OUT"
rm -rf "$REPO2"

# 8. R3 (T-00001012, run-recap.sh:126, E-26 closing pass) — « N board line(s) uncommitted » reads the
# RECORD folders too: `git diff --numstat HEAD` over TASKS.json AND `tasks/` AND `epics/`. A task record
# COMMITTED then rewritten as 4 lines counts 4. Mutant that reddens: rr-diff-sans-dossier (the diff back
# to `str(board)` alone). The git env a hook exports would redirect these commands: unset first.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
REPO3="$(mktemp -d)"
mkdir -p "$REPO3/.agents/bin" "$REPO3/.agents/state/board/tasks" "$REPO3/.agents/state/board/epics"
printf 'def statusline(root):\n    return "STUB-STATUSLINE T-00000001 running"\n' > "$REPO3/.agents/bin/tasks.py"
printf '{"format": 1, "id": "T-00000001", "record": {"id": "T-00000001"}, "sync_operations": []}\n' \
  > "$REPO3/.agents/state/board/tasks/T-00000001.json"
printf '{"format": 1, "id": "E-01", "record": {"id": "E-01"}}\n' > "$REPO3/.agents/state/board/epics/E-01.json"
git -C "$REPO3" init -q
git -C "$REPO3" add -A
git -C "$REPO3" -c user.name=banc -c user.email=banc@local -c commit.gpgsign=false commit -qm base
OUT=$(CLAUDE_PROJECT_DIR="$REPO3" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -q 'uncommitted' && fail "R3 control: nothing uncommitted, no count expected: $OUT"
printf '{\n  "format": 1,\n  "id": "T-00000001"\n}\n' > "$REPO3/.agents/state/board/tasks/T-00000001.json"
OUT=$(CLAUDE_PROJECT_DIR="$REPO3" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -qF '4 board line(s) uncommitted' || fail "R3: a rewritten task record is not counted: $OUT"

# 9. R4 — the same for `epics/`: the task record committed, an EPIC record rewritten as 4 lines counts 4.
# Mutant that reddens: `epics/` dropped from the diff.
git -C "$REPO3" add -A
git -C "$REPO3" -c user.name=banc -c user.email=banc@local -c commit.gpgsign=false commit -qm tache
printf '{\n  "format": 1,\n  "id": "E-01"\n}\n' > "$REPO3/.agents/state/board/epics/E-01.json"
OUT=$(CLAUDE_PROJECT_DIR="$REPO3" bash "$HERE/run-recap.sh")
echo "$OUT" | grep -qF '4 board line(s) uncommitted' || fail "R4: a rewritten epic record is not counted: $OUT"
rm -rf "$REPO3"

echo "PASS: run-recap (9/9)"
