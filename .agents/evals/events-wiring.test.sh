#!/usr/bin/env bash
# events-wiring.test.sh — T-00000018 shard 2 proof suite (canal A hook wiring).
# Run: bash .agents/evals/events-wiring.test.sh
#
# Three independent parts, per docs/tasks/T-00000018.md's proof obligation:
#
#   PART 1 — STATIC registration inventory against .claude/settings.json.
#            The property under test is WIRING — event key -> matcher ->
#            script — asserted from the PARSED JSON, PRESENCE ONLY. A line
#            number is printed as INFORMATIONAL CONTEXT next to a PASS, never
#            as a pass/fail condition: file layout and wiring are not the
#            same property, and gating on layout means every legitimate
#            insertion earlier in the file (e.g. the pilot registering the 6
#            new rows below) shifts every later line number and reports a
#            REGRESSION THAT ISN'T ONE. That happened once already — see
#            PART 1B, the regression test for exactly this defect. A missing
#            or wrong-script pre-existing registration hard-fails the suite
#            immediately (that IS a real regression). The 6 new rows
#            (SubagentStart, PostCompact, SessionEnd, PostToolUse[Agent],
#            PreToolUse[mcp__.*], PostToolUse[mcp__.*]) are reported PASS/
#            MISSING the same presence-only way, never hard-failing — before
#            the pilot registers them this is expected and counted into the
#            suite's overall (non-hard) exit code; once registered, 0
#            missing is required for a clean exit.
#
#   PART 2 — DIFFERENTIAL: for every touched hook, run it twice — once with
#            events.py present, once with it absent from the fixture — and
#            assert stdout+stderr+exit code are BYTE-IDENTICAL. Proves the
#            emit call sites are invisible to each hook's own contract
#            regardless of events.py's health (fail-open, both directions).
#
#   PART 3 — POSITIVE: with events.py present, invoke each surface with
#            synthetic stdin and assert the emitted JSONL carries the
#            expected `kind` AND its load-bearing `data` fields (never just
#            kind-only — a kind-only assertion would let a forgotten field
#            land as `data: {}` with the suite green, the exact C13 gap).
#
# Isolation: every hook that touches project state (RUN_LOG.md, the board,
# the real events dir) runs against a DISPOSABLE fixture directory, never the
# real repo — AGENTS_EVENTS_DIR redirects events.py's own write path, and
# CLAUDE_PROJECT_DIR points at a throwaway copy for hooks that resolve paths
# from it. gitleaks-scan.sh / semgrep-scan.sh / sca-scan.sh resolve their
# ROOT via `git rev-parse --show-toplevel` (NOT CLAUDE_PROJECT_DIR) — those
# three run inside a disposable `git init`'d fixture repo instead.
#
# DIFFERENTIAL COMPARATOR AUDIT — closed set, re-derive this list rather than
# guessing if a differential ever flakes again. Every "A vs B" pair below is
# built from TWO SEPARATE, independently-constructed fixtures (two mktemp
# dirs, sometimes two `git init`'d repos) — anything that fixture construction
# legitimately randomizes must be normalized out BEFORE comparing, or the
# comparator is non-deterministic by construction (coordinator-caught: this
# happened once already, see stop-reindex.sh below).
#   - stop-reindex.sh: the fixture pair is TWO INDEPENDENT git repos, each
#     committed separately — `git commit` legitimately yields two different
#     SHAs for "the same" content (commit timestamp + author + tree all feed
#     the hash). The hook's own systemMessage embeds "built @ <sha>" — MUST
#     normalize (regex `built @ [0-9a-fA-F]{7,40}` -> placeholder).
#   - sca-scan.sh: the fixture pair is TWO INDEPENDENT mktemp directories —
#     the hook's own console output legitimately embeds its absolute
#     TGT/OUT/WAIVERS paths, which differ by construction — MUST normalize
#     (regex-strip any mktemp-shaped absolute path).
#   - Audited and found to need NO normalization (verified by reading each
#     hook's own stdout-producing code, not just observed test runs):
#     protect-paths.sh / safe-bash.sh / audit-gate.sh (messages built purely
#     from the SAME static synthetic $FILE/$CMD string passed to both
#     invocations — no timestamp, sha, pid, or path unique to one fixture);
#     post-edit-check.sh (message embeds $FILE, but the SAME absolute fixture
#     path is used for both the events.py-present and -absent runs); session-
#     start.sh (both fixtures lack index/board/ledger content, so CTX is
#     empty and the hook exits 0 silently both times — nothing to compare);
#     pre-compact.sh, log-agent-usage.sh, agent-events.sh, mcp-events.sh
#     (none of these print anything to their own stdout — all output/state
#     goes to a file, which is checked separately via last_record(), never
#     via the OUT_A/OUT_B string compare); run-recap.sh (systemMessage is
#     derived purely from the FIXED RUN_LOG_CONTENT fixture text — no
#     wall-clock value is embedded in the recap line itself); gitleaks-
#     scan.sh / semgrep-scan.sh (the "COVERAGE DEGRADED"/"clean" messages
#     compared here are static strings — the run's own $TS timestamp goes
#     into audit-log.jsonl, a FILE, never into the compared stdout).
#   - NOT part of this audit's scope: the events.py-produced JSONL itself
#     (`ts`, `user`, per-process day-filename) is NEVER differential-compared
#     record-for-record — PART 3's positive assertions check individual
#     named fields (kind, status, tokens, ...) on ONE side only, by design.
#
# Windows/L-00000035: every assertion below executes and is checked BEFORE
# any `trap ... EXIT` cleanup fires — a teardown-only PermissionError is
# infrastructure noise, not a test failure, but nothing here counts as clean
# unless its own assertions actually ran.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")/../.." && pwd)"   # repo root (.agents/evals/ -> up 2)
HOOKS="$HERE/.claude/hooks"
SEC="$HERE/.agents/security"
SETTINGS="$HERE/.claude/settings.json"
EVENTS_PY="$HERE/.agents/bin/events.py"
# T-00000641 (S-00001649) : la couture d'events.py charge redaction.py PAR CHEMIN
# (parents[2] de .agents/bin/events.py = racine de la fixture). Toute fixture qui
# invoque emit doit le rendre atteignable, sinon emit dégrade et neutralise les
# valeurs — les assertions POSITIVES de PART 3 rougissent.
FIXTURE_TRANSCRIPT="$HERE/.claude/hooks/fixtures/subagent-transcript.jsonl"

PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "SKIP: no python interpreter found"; exit 0; fi

PASS=0; FAIL=0; MISSING=0
note_pass()    { PASS=$((PASS+1));    printf '  PASS: %s\n' "$1"; }
note_fail()    { FAIL=$((FAIL+1));    printf '  FAIL: %s\n' "$1"; }
note_missing() { MISSING=$((MISSING+1)); printf '  MISSING (step 2 — pilot must register, see JSON block below): %s\n' "$1"; }
hard_fail()    { printf 'HARD FAIL (regression in EXISTING wiring): %s\n' "$1"; exit 1; }

WORK="$(mktemp -d)"
cleanup() { chmod -R u+w "$WORK" 2>/dev/null; }
trap cleanup EXIT

# T-01M5BXTPQE3JZV3KZA6WD9P5XC (S-01M5BXT85VP4JBBMXVXR9STP5F) : la SOURCE de
# redaction.py est le paquet `cadre` que `vendor_paths.exiger` désigne sous une
# racine (neuf `.agents/vendor/cadre` d'abord, ancien `src/cadre` ensuite),
# vendor_paths chargé PAR CHEMIN depuis ce kit ; jamais un `src/cadre` en dur.
cadre_pkg() {  # $1 = racine ; stdout = dossier du paquet, sans fin de ligne
  "$PY" -I -B -c 'import importlib.util as u, sys
s = u.spec_from_file_location("vendor_paths", sys.argv[1])
m = sys.modules[s.name] = u.module_from_spec(s); s.loader.exec_module(m)
sys.stdout.write(m.exiger(sys.argv[2], "cadre").as_posix())' "$HERE/.agents/bin/vendor_paths.py" "$1"
}
CADRE_PKG="$(cadre_pkg "$HERE")" || hard_fail "paquet cadre introuvable sous $HERE (vendor_paths.exiger)"
REDACTION_PY="$CADRE_PKG/ledger/redaction.py"
[ -f "$REDACTION_PY" ] || hard_fail "redaction.py absent du paquet résolu : $REDACTION_PY"
# La DESTINATION : les DEUX emplacements, dont le lieu que lit events.py (`_CHEMIN_REDACTION`).
poser_redaction() {  # $1 = racine de la fixture
  local l
  for l in src/cadre/ledger .agents/vendor/cadre/ledger; do
    mkdir -p "$1/$l" && cp "$REDACTION_PY" "$1/$l/redaction.py" || return 1
  done
}
# vendor-seul : le résolveur de CETTE suite suit la règle aux trois dispositions.
VS="$(mktemp -d -p "$WORK")"
mkdir -p "$VS/v/.agents/vendor/cadre" "$VS/a/src/cadre" "$VS/d/.agents/vendor/cadre" "$VS/d/src/cadre"
touch "$VS/v/.agents/vendor/cadre/__init__.py" "$VS/a/src/cadre/__init__.py" \
  "$VS/d/.agents/vendor/cadre/__init__.py" "$VS/d/src/cadre/__init__.py"
VS_V="$(cadre_pkg "$VS/v")"; VS_A="$(cadre_pkg "$VS/a")"; VS_D="$(cadre_pkg "$VS/d")"
case "$VS_V+$VS_A+$VS_D" in
  */v/.agents/vendor/cadre+*/a/src/cadre+*/d/.agents/vendor/cadre) note_pass "vendor-seul : source cadre résolue par vendor_paths (vendor seul, ancien seul, les deux => vendor ; ce kit : $CADRE_PKG)" ;;
  *) note_fail "vendor-seul : résolution cadre inattendue [$VS_V] [$VS_A] [$VS_D]" ;;
esac
# vendor-seul : le chemin que la suite UTILISE (REDACTION_PY, copié par poser_redaction)
# est sous le lieu que la règle désigne dans CE kit — un REDACTION_PY remis en dur sur
# src rougit ici quand les deux lieux coexistent (et meurt en hard_fail en vendor seul).
if [ -f "$HERE/.agents/vendor/cadre/__init__.py" ]; then VS_LIEU=".agents/vendor/cadre"; else VS_LIEU="src/cadre"; fi
case "$REDACTION_PY" in
  */"$VS_LIEU"/ledger/redaction.py) note_pass "vendor-seul : REDACTION_PY suit la règle ($VS_LIEU) : $REDACTION_PY" ;;
  *) note_fail "vendor-seul : REDACTION_PY hors du lieu désigné ($VS_LIEU) : $REDACTION_PY" ;;
esac

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

# A disposable, non-git project skeleton with events.py + emit-event.sh (+
# agent-events.sh / mcp-events.sh) copied in at the same relative paths the
# real hooks expect under $CLAUDE_PROJECT_DIR.
mk_fakeproj() {
  local d; d="$(mktemp -d -p "$WORK")"
  mkdir -p "$d/.agents/bin" "$d/.claude/hooks" "$d/.agents/state/gates" "$d/.agents/state/local"
  cp "$EVENTS_PY" "$d/.agents/bin/events.py"
  # Non-git skeleton (pas une cible gitleaks/semgrep) : copie simple suffit.
  poser_redaction "$d"
  cp "$HOOKS/emit-event.sh" "$d/.claude/hooks/emit-event.sh"
  cp "$HOOKS/agent-events.sh" "$d/.claude/hooks/agent-events.sh"
  cp "$HOOKS/mcp-events.sh" "$d/.claude/hooks/mcp-events.sh"
  printf '%s' "$d"
}

# Same, but WITHOUT events.py (the "module absent/unreadable" differential leg).
mk_fakeproj_noevents() {
  local d; d="$(mktemp -d -p "$WORK")"
  mkdir -p "$d/.agents/bin" "$d/.claude/hooks" "$d/.agents/state/gates" "$d/.agents/state/local"
  cp "$HOOKS/emit-event.sh" "$d/.claude/hooks/emit-event.sh"
  cp "$HOOKS/agent-events.sh" "$d/.claude/hooks/agent-events.sh"
  cp "$HOOKS/mcp-events.sh" "$d/.claude/hooks/mcp-events.sh"
  printf '%s' "$d"
}

# A disposable GIT repo fixture for gitleaks-scan.sh / semgrep-scan.sh /
# sca-scan.sh, whose ROOT is `git rev-parse --show-toplevel`, not
# CLAUDE_PROJECT_DIR — running them from inside a throwaway repo fully
# sandboxes both directions of the proof, real repo untouched.
mk_fakerepo() {
  local with_events="$1"
  local d; d="$(mktemp -d -p "$WORK")"
  git -C "$d" init -q
  git -C "$d" config user.email t@t
  git -C "$d" config user.name t
  mkdir -p "$d/.agents/bin" "$d/.agents/security" "$d/.claude/hooks"
  [ "$with_events" = "yes" ] && cp "$EVENTS_PY" "$d/.agents/bin/events.py"
  # T-00000641 (S-00001649, A-T4) : redaction.py atteignable par la voie nominale.
  # `src/cadre/` et `.agents/vendor/cadre/` au .gitignore le gardent NON SUIVI (convention des fixtures : les
  # bridges copiés restent untracked). Le .gitignore NE le soustrait PAS au
  # scanner — gitleaks tourne en `--no-git`, qui IGNORE le .gitignore (mesuré :
  # 9187 vs 9176 octets, l'écart étant le .gitignore lui-même). Ce qui protège est
  # que redaction.py ne produit AUCUN finding (mesuré : `no leaks found`).
  if [ "$with_events" = "yes" ]; then
    poser_redaction "$d"
    printf 'src/cadre/\n.agents/vendor/cadre/\n' > "$d/.gitignore"
  fi
  cp "$HOOKS/emit-event.sh" "$d/.claude/hooks/emit-event.sh"
  cp "$SEC/gitleaks-scan.sh" "$d/.agents/security/gitleaks-scan.sh"
  cp "$SEC/semgrep-scan.sh" "$d/.agents/security/semgrep-scan.sh"
  cp "$SEC/sca-scan.sh" "$d/.agents/security/sca-scan.sh"
  cp "$SEC/waiver_filter.py" "$d/.agents/security/waiver_filter.py"
  printf '{"waivers":[]}' > "$d/.agents/security/sca-waivers.json"
  printf 'x' > "$d/README.md"
  git -C "$d" add -A && git -C "$d" commit -qm init >/dev/null
  printf '%s' "$d"
}

# Latest-record helper: glob the (possibly multi-writer) events dir and print
# the last JSON line across all files — mirrors the reader-aggregates
# contract (design doc §C / events.py's own _lines() test helper), never
# assumes a single file.
last_record() {  # $1 = events dir
  "$PY" - "$1" << 'PYEOF'
import glob, json, os, sys
d = sys.argv[1]
recs = []
for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
print(json.dumps(recs[-1]) if recs else "")
PYEOF
}

all_records() {  # $1 = events dir -> one JSON object per line, in file order
  "$PY" - "$1" << 'PYEOF'
import glob, json, os, sys
d = sys.argv[1]
for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                print(line)
PYEOF
}

field_eq() {  # $1 = json line, $2 = dotted data-field path (e.g. data.status), $3 = expected
  "$PY" - "$1" "$2" "$3" << 'PYEOF'
import json, sys
rec = json.loads(sys.argv[1])
path = sys.argv[2].split(".")
cur = rec
for p in path:
    if not isinstance(cur, dict) or p not in cur:
        print("MISSING"); sys.exit(0)
    cur = cur[p]
expected = sys.argv[3]
print("OK" if str(cur) == expected else f"MISMATCH got={cur!r}")
PYEOF
}

# Shared presence-only inventory logic — written to a real .py file (not a
# bash string) precisely to avoid a second layer of quote-escaping bugs on
# top of the one this whole section already fixed once. Used against BOTH
# the real .claude/settings.json (PART 1) and a mutated fixture copy
# (PART 1B, the regression test for the line-number defect below). One
# definition, two invocations: no duplicated logic to drift out of sync.
INVENTORY_SCRIPT="$WORK/inventory_check.py"
cat > "$INVENTORY_SCRIPT" << 'PYEOF'
import json, sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    raw_lines = fh.readlines()
with open(path, encoding="utf-8") as fh:
    cfg = json.load(fh)

hooks = cfg.get("hooks", {})


def commands_for(event, matcher=None):
    out = []
    for block in hooks.get(event, []):
        if matcher is not None and block.get("matcher") != matcher:
            continue
        if matcher is None and "matcher" in block:
            continue
        for h in block.get("hooks", []):
            out.append(h.get("command", ""))
    return out


_line_of_cursor = {}
def line_of(needle):
    """INFORMATIONAL ONLY — never a pass/fail condition. A line number
    encodes file LAYOUT; the property under test is WIRING (event -> matcher
    -> script). Gating on this line previously reported 9 false regressions
    the moment the pilot legitimately inserted 6 new registrations earlier
    in the file, shifting everything after them (coordinator-caught)."""
    start = _line_of_cursor.get(needle, 0)
    for i in range(start, len(raw_lines)):
        if needle in raw_lines[i]:
            _line_of_cursor[needle] = i + 1
            return i + 1
    return None


# (event, matcher_or_None, script_substring) — PRESENCE ONLY, computed from
# the PARSED JSON. A script registered under several events (sca-scan.sh,
# gitleaks-scan.sh) needs one row per event/matcher pair it is expected under.
PRE_EXISTING = [
    ("PreToolUse", "Edit|Write", "protect-paths.sh"),
    ("PreToolUse", "Edit|Write", 'gitleaks-scan.sh" --content'),
    ("PreToolUse", "Bash", "audit-gate.sh"),
    ("PreToolUse", "Bash", "safe-bash.sh"),
    ("PostToolUse", "Edit|Write", "post-edit-check.sh"),
    ("PostToolUse", "Edit|Write", "sca-scan.sh"),
    ("SubagentStop", None, "log-agent-usage.sh"),
    ("SessionStart", None, "session-start.sh"),
    ("PreCompact", None, "pre-compact.sh"),
    ("Stop", None, "stop-reindex.sh"),
    ("Stop", None, "run-recap.sh"),
    ("Stop", None, "sca-scan.sh"),
    ("Stop", None, "gitleaks-scan.sh"),
]

pre_fail = []
for event, matcher, needle in PRE_EXISTING:
    cmds = commands_for(event, matcher)
    present = any(needle in c for c in cmds)
    plain = needle.split('"')[0].strip()
    line_hint = line_of(plain)  # printed for context only, never asserted on
    matcher_tag = f"[{matcher}]" if matcher else ""
    label = f"{event}{matcher_tag} -> {needle}"
    if present:
        print(f"  PASS: {label} (line {line_hint})")
    else:
        print(f"  FAIL: {label} — registration ABSENT or points at a different script")
        pre_fail.append(label)

NEW_ROWS = [
    ("SubagentStart", None, "agent-events.sh", "agent.start"),
    ("PostCompact", None, "agent-events.sh", "session.compact(post)"),
    ("SessionEnd", None, "agent-events.sh", "session.stop"),
    # Declaration KEPT, emission GONE (T-01M55Z3ZCS34CDR2EQN1CEBHR7, C35): the
    # script exits in bash on this event; PART 3 asserts it emits NO agent.stop.
    ("PostToolUse", "Agent", "agent-events.sh", "declared, emits nothing (C35)"),
    ("PreToolUse", "mcp__.*", "mcp-events.sh", "scan.mcp_call (PreToolUse)"),
    ("PostToolUse", "mcp__.*", "mcp-events.sh", "scan.mcp_call (PostToolUse)"),
]

missing = []
for event, matcher, needle, purpose in NEW_ROWS:
    cmds = commands_for(event, matcher)
    present = any(needle in c for c in cmds)
    matcher_tag = f"[{matcher}]" if matcher else ""
    label = f"{event}{matcher_tag} -> {needle} ({purpose})"
    if present:
        print(f"  PASS: {label}")
    else:
        print(f"  MISSING: {label}")
        missing.append(label)

print(f"__SUMMARY__ pre_fail={len(pre_fail)} missing={len(missing)}")
PYEOF

echo "=== PART 1: static registration inventory (.claude/settings.json) ==="
PART1_OUTPUT=$("$PY" "$INVENTORY_SCRIPT" "$SETTINGS")
STATIC_OUT_RC=$?
echo "$PART1_OUTPUT"
[ "$STATIC_OUT_RC" -ne 0 ] && hard_fail "static registration check crashed"

SUMMARY_LINE="$(printf '%s\n' "$PART1_OUTPUT" | grep '^__SUMMARY__')"
PRE_FAIL_N="$(printf '%s' "$SUMMARY_LINE" | sed -n 's/.*pre_fail=\([0-9]*\).*/\1/p')"
MISSING_N="$(printf '%s' "$SUMMARY_LINE" | sed -n 's/.*missing=\([0-9]*\).*/\1/p')"
[ "$PRE_FAIL_N" -gt 0 ] 2>/dev/null && hard_fail "$PRE_FAIL_N pre-existing registration(s) ABSENT or pointing at a different script — this is a real regression, not step-2 pending work"
MISSING=$((MISSING + MISSING_N))
echo "PART 1 done: pre_fail=$PRE_FAIL_N (must be 0), missing=$MISSING_N/6 (0 once the pilot has registered all 6)."
echo

echo "=== PART 1B (regression test): a harmless insertion must never report a false pre-existing failure ==="
# The exact defect the coordinator caught: gating presence on a HARDCODED
# line number. Insert a dummy hook block at the very TOP of PreToolUse's
# "Edit|Write" matcher array in a FIXTURE COPY of the real settings.json —
# every line number below that point shifts — and assert the SAME
# presence-only inventory still reports pre_fail=0 against the fixture.
FIXTURE_SETTINGS="$WORK/settings-with-dummy-block.json"
"$PY" -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    cfg = json.load(fh)
dummy = {'type': 'command', 'shell': 'bash', 'command': 'echo dummy-inserted-by-regression-test-only'}
for block in cfg['hooks']['PreToolUse']:
    if block.get('matcher') == 'Edit|Write':
        block['hooks'].insert(0, dummy)
        break
with open(sys.argv[2], 'w', encoding='utf-8') as fh:
    json.dump(cfg, fh, indent=2)
" "$SETTINGS" "$FIXTURE_SETTINGS"
REGRESSION_OUTPUT=$("$PY" "$INVENTORY_SCRIPT" "$FIXTURE_SETTINGS")
REGRESSION_SUMMARY="$(printf '%s\n' "$REGRESSION_OUTPUT" | grep '^__SUMMARY__')"
REGRESSION_PRE_FAIL="$(printf '%s' "$REGRESSION_SUMMARY" | sed -n 's/.*pre_fail=\([0-9]*\).*/\1/p')"
if [ "$REGRESSION_PRE_FAIL" = "0" ]; then
  note_pass "PART 1B: dummy block at the top of PreToolUse[Edit|Write] shifts every later line — presence-only inventory still reports pre_fail=0 (0 false regressions)"
else
  note_fail "PART 1B: line-number brittleness resurfaced — a harmless insertion produced pre_fail=$REGRESSION_PRE_FAIL false failure(s):
$REGRESSION_OUTPUT"
fi
echo

# ---------------------------------------------------------------------------
echo "=== PART 2+3: per-surface differential (events.py present vs absent) + positive assertion ==="

# --- protect-paths.sh : hook.deny -------------------------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN='{"tool_input":{"file_path":"src/legacy/x.ts"}}'
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/protect-paths.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/protect-paths.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "protect-paths.sh differential (rc=$RC_A, output byte-identical)"; else note_fail "protect-paths.sh differential MISMATCH: rc $RC_A vs $RC_B / out [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind hook.deny)" = "OK" ] && [ "$(field_eq "$REC" data.guard protect-paths)" = "OK" ] \
    && [ "$(field_eq "$REC" data.rule src/legacy/)" = "OK" ] && [ "$(field_eq "$REC" data.path src/legacy/x.ts)" = "OK" ] \
    && note_pass "protect-paths.sh positive: hook.deny{guard,rule,path}" \
    || note_fail "protect-paths.sh positive assertion failed: $REC"
else
  note_fail "protect-paths.sh: no event captured"
fi

# --- safe-bash.sh : hook.deny -------------------------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN='{"tool_input":{"command":"rm -rf /"}}'
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/safe-bash.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/safe-bash.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "safe-bash.sh differential (rc=$RC_A)"; else note_fail "safe-bash.sh differential MISMATCH"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind hook.deny)" = "OK" ] && [ "$(field_eq "$REC" data.guard safe-bash)" = "OK" ] && [ "$(field_eq "$REC" data.rule rm-rf-root)" = "OK" ] \
    && [ "$("$PY" -c "import json,sys; d=json.loads(sys.argv[1])['data']; print('OK' if d.get('cmd_sha256') and d.get('cmd_len') and 'path' not in d else 'MISSING')" "$REC")" = "OK" ] \
    && note_pass "safe-bash.sh positive: hook.deny{guard,rule,cmd_sha256,cmd_len} — NEVER path" || note_fail "safe-bash.sh positive assertion failed: $REC"
else note_fail "safe-bash.sh: no event captured"; fi

# --- safe-bash.sh REGRESSION, BRANCH 1 (rm-rf-root) — security-code-review,
# class-1 HIGH, T-00000018 addendum: a hook.deny from THIS guard must carry
# NO substring of the originating command — a whole shell command is
# model-controlled and can legitimately contain a live credential (curl -H
# "Authorization: Bearer <token>" ...). Feed a fixture with a distinctive
# fake token and assert it is absent from the ENTIRE written record
# (envelope + data), not merely absent from one named field — this is the
# test whose absence let the original leak ship (the value was smuggled
# through `path`, which no single-field check would have caught if aimed at
# the wrong field name). Kept as its OWN case, not parameterised with branch
# 2 below — a single failure must say unambiguously which branch broke.
FP="$(mk_fakeproj)"
EVDIR_LEAK_B1="$(mktemp -d -p "$WORK")"
DISTINCTIVE_TOKEN_B1="sk-FAKE-TOKEN-9f8e7d6c5b4a3210"
IN_LEAK_B1=$("$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command': 'curl -H \"Authorization: Bearer ' + sys.argv[1] + '\" https://example.com && rm -rf /'}}))" "$DISTINCTIVE_TOKEN_B1")
printf '%s' "$IN_LEAK_B1" | CLAUDE_PROJECT_DIR="$FP" AGENTS_EVENTS_DIR="$EVDIR_LEAK_B1" bash "$HOOKS/safe-bash.sh" >/dev/null 2>&1
ALL_LEAK_B1="$(all_records "$EVDIR_LEAK_B1")"
if [ -z "$ALL_LEAK_B1" ]; then
  note_fail "safe-bash.sh[rm-rf-root] credential-leak regression: no event captured to check"
elif printf '%s' "$ALL_LEAK_B1" | grep -qF "$DISTINCTIVE_TOKEN_B1"; then
  note_fail "safe-bash.sh[rm-rf-root] credential-leak regression: the distinctive fake token LEAKED into the written record: $ALL_LEAK_B1"
else
  note_pass "safe-bash.sh[rm-rf-root] credential-leak regression: distinctive fake token absent from the written record (guard against T-00000018's class-1 HIGH)"
fi

# --- safe-bash.sh REGRESSION, BRANCH 2 (rm-mv-bypass-checkpoint) — the branch
# that ACTUALLY fires in normal use (branch 1 above is the rare catastrophic-
# command path) and the one that leaked 1171 characters twice in the live
# session that found this. Coordinator-flagged gap: the original regression
# only covered branch 1. Same shape, deliberately a SEPARATE case (not
# parameterised with branch 1) so a single failure names its own branch.
# Two independent markers checked, plus the whole raw command string, so
# this is not just "one token happens to be absent" — it is "no substring of
# the command, by several independent samples of it, survived into the
# record."
FP="$(mk_fakeproj)"
EVDIR_LEAK_B2="$(mktemp -d -p "$WORK")"
DISTINCTIVE_TOKEN_B2="sk-FAKE-TOKEN-1a2b3c4d5e6f7081"
DISTINCTIVE_MARKER_B2="zzDISTINCTIVE-FILE-MARKER-b2zz"
RAW_CMD_B2="curl -H \"Authorization: Bearer $DISTINCTIVE_TOKEN_B2\" https://example.com/upload; rm src/$DISTINCTIVE_MARKER_B2.txt"
IN_LEAK_B2=$("$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command': sys.argv[1]}}))" "$RAW_CMD_B2")
printf '%s' "$IN_LEAK_B2" | CLAUDE_PROJECT_DIR="$FP" AGENTS_EVENTS_DIR="$EVDIR_LEAK_B2" bash "$HOOKS/safe-bash.sh" >/dev/null 2>&1
ALL_LEAK_B2="$(all_records "$EVDIR_LEAK_B2")"
if [ -z "$ALL_LEAK_B2" ]; then
  note_fail "safe-bash.sh[rm-mv-bypass-checkpoint] credential-leak regression: no event captured to check"
elif printf '%s' "$ALL_LEAK_B2" | grep -qF "$DISTINCTIVE_TOKEN_B2"; then
  note_fail "safe-bash.sh[rm-mv-bypass-checkpoint] credential-leak regression: the distinctive fake token LEAKED into the written record: $ALL_LEAK_B2"
elif printf '%s' "$ALL_LEAK_B2" | grep -qF "$DISTINCTIVE_MARKER_B2"; then
  note_fail "safe-bash.sh[rm-mv-bypass-checkpoint] credential-leak regression: the distinctive filename marker LEAKED into the written record: $ALL_LEAK_B2"
elif printf '%s' "$ALL_LEAK_B2" | grep -qF "$RAW_CMD_B2"; then
  note_fail "safe-bash.sh[rm-mv-bypass-checkpoint] credential-leak regression: the FULL raw command leaked into the written record: $ALL_LEAK_B2"
else
  REC_B2="$(last_record "$EVDIR_LEAK_B2")"
  if [ -n "$REC_B2" ] && [ "$("$PY" -c "import json,sys; d=json.loads(sys.argv[1])['data']; print('OK' if d.get('cmd_sha256') and d.get('cmd_len') else 'MISSING')" "$REC_B2")" = "OK" ]; then
    note_pass "safe-bash.sh[rm-mv-bypass-checkpoint] credential-leak regression: token/marker/full-command absent, cmd_sha256+cmd_len present (the branch that actually leaked in this session)"
  else
    note_fail "safe-bash.sh[rm-mv-bypass-checkpoint]: no leak, but cmd_sha256/cmd_len missing: $REC_B2"
  fi
fi

# --- audit-gate.sh : hook.deny -------------------------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN='{"tool_input":{"command":"npx skills add some/ref"}}'
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/audit-gate.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/audit-gate.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "audit-gate.sh differential (rc=$RC_A)"; else note_fail "audit-gate.sh differential MISMATCH"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind hook.deny)" = "OK" ] && [ "$(field_eq "$REC" data.guard audit-gate)" = "OK" ] && [ "$(field_eq "$REC" data.path some/ref)" = "OK" ] \
    && note_pass "audit-gate.sh positive: hook.deny{guard,rule,path}" || note_fail "audit-gate.sh positive assertion failed: $REC"
else note_fail "audit-gate.sh: no event captured"; fi

# --- post-edit-check.sh : hook.check_fail -----------------------------------
# CLAUDE_PROJECT_DIR only needs to resolve emit-event.sh here (py_compile is
# invoked with an ABSOLUTE path to the fixture file, so the toolchain lookup
# itself is independent of cwd) — a fakeproj skeleton is enough for both legs.
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
BADPY="$WORK/bad_syntax.py"; printf 'def f(:\n  pass\n' > "$BADPY"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN=$("$PY" -c "import json,sys; print(json.dumps({'tool_input':{'file_path': sys.argv[1]}}))" "$BADPY")
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/post-edit-check.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/post-edit-check.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "post-edit-check.sh differential (rc=$RC_A)"; else note_fail "post-edit-check.sh differential MISMATCH: [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind hook.check_fail)" = "OK" ] && [ "$(field_eq "$REC" data.guard post-edit-check)" = "OK" ] && [ "$(field_eq "$REC" data.rule py)" = "OK" ] \
    && note_pass "post-edit-check.sh positive: hook.check_fail{guard,rule,path}" || note_fail "post-edit-check.sh positive assertion failed: $REC"
else note_fail "post-edit-check.sh: no event captured"; fi

# --- session-start.sh : session.start ---------------------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(printf '{}' | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/session-start.sh" 2>&1); RC_A=$?
OUT_B=$(printf '{}' | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/session-start.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "session-start.sh differential (rc=$RC_A)"; else note_fail "session-start.sh differential MISMATCH: [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind session.start)" = "OK" ] && note_pass "session-start.sh positive: session.start emitted" || note_fail "session-start.sh positive assertion failed: $REC"
else note_fail "session-start.sh: no event captured (index/board/ledger all absent must still emit — item 4)"; fi

# --- stop-reindex.sh : index.stale ------------------------------------------
GR_A="$(mktemp -d -p "$WORK")"; GR_B="$(mktemp -d -p "$WORK")"
for GR in "$GR_A" "$GR_B"; do
  mkdir -p "$GR/src" "$GR/.agents/state/index" "$GR/.claude/hooks" "$GR/.agents/bin"
  git -C "$GR" init -q; git -C "$GR" config user.email t@t; git -C "$GR" config user.name t
  cp "$HOOKS/emit-event.sh" "$GR/.claude/hooks/emit-event.sh"
  printf 'export const a = 1;\n' > "$GR/src/a.ts"
  git -C "$GR" add -A && git -C "$GR" commit -qm init >/dev/null
  SHA="$(git -C "$GR" rev-parse --short HEAD)"
  printf '# Symbols built @ %s\nSYM-001 src/a.ts:1-1 a export uses[] :: c\n' "$SHA" > "$GR/.agents/state/index/SYMBOLS.md"
  printf 'export const a = 2;\n' > "$GR/src/a.ts"
done
cp "$EVENTS_PY" "$GR_A/.agents/bin/events.py"
# T-00000641 : GR_A porte events.py (voie présente du différentiel) ; redaction.py
# doit l'accompagner pour la voie nominale. Copié APRÈS le commit comme events.py
# (donc non suivi) ; ce fixture n'est PAS une cible gitleaks/semgrep (stop-reindex
# seul), et le différentiel ne dépend pas des fichiers non suivis (mesuré).
poser_redaction "$GR_A"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(CLAUDE_PROJECT_DIR="$GR_A" AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/stop-reindex.sh" 2>&1); RC_A=$?
OUT_B=$(CLAUDE_PROJECT_DIR="$GR_B" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/stop-reindex.sh" 2>&1); RC_B=$?
# Normalize the "built @ <sha>" commit hash out of the compared payload: GR_A
# and GR_B are TWO INDEPENDENT git-init'd fixtures, so `git commit` legitimately
# produces two different SHAs for "the same" content — that is not a
# differential regression, it is this fixture pair's own non-determinism
# (coordinator-caught: the un-normalized comparator was flaky by construction,
# passing or failing depending on incidental SHA divergence, not on wiring).
OUT_A_NORM="$("$PY" -c "import re,sys; print(re.sub(r'built @ [0-9a-fA-F]{7,40}', 'built @ <SHA>', sys.argv[1]))" "$OUT_A")"
OUT_B_NORM="$("$PY" -c "import re,sys; print(re.sub(r'built @ [0-9a-fA-F]{7,40}', 'built @ <SHA>', sys.argv[1]))" "$OUT_B")"
if [ "$OUT_A_NORM" = "$OUT_B_NORM" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "stop-reindex.sh differential (rc=$RC_A, sha-normalized)"; else note_fail "stop-reindex.sh differential MISMATCH: [$OUT_A_NORM] vs [$OUT_B_NORM]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind index.stale)" = "OK" ] && [ "$("$PY" -c "import json,sys; print('OK' if 'reason' in json.loads(sys.argv[1])['data'] and json.loads(sys.argv[1])['data']['reason'] else 'MISSING')" "$REC")" = "OK" ] \
    && note_pass "stop-reindex.sh positive: index.stale{reason}" || note_fail "stop-reindex.sh positive assertion failed: $REC"
else note_fail "stop-reindex.sh: no event captured"; fi

# --- pre-compact.sh : session.compact(trigger=pre) --------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
mkdir -p "$FP/.claude/backups" "$FPN/.claude/backups"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN='{"transcript_path":""}'
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/pre-compact.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/pre-compact.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "pre-compact.sh differential (rc=$RC_A)"; else note_fail "pre-compact.sh differential MISMATCH"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind session.compact)" = "OK" ] && [ "$(field_eq "$REC" data.trigger pre)" = "OK" ] \
    && note_pass "pre-compact.sh positive: session.compact{trigger=pre}" || note_fail "pre-compact.sh positive assertion failed: $REC"
else note_fail "pre-compact.sh: no event captured"; fi

# --- log-agent-usage.sh : agent.stop{tokens} ---------------------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN=$("$PY" -c "import json,sys; print(json.dumps({'hook_event_name':'SubagentStop','agent_type':'dev-multi','session_id':'sess-1','agent_id':'agent-1','transcript_path':sys.argv[1],'last_assistant_message':'done'}))" "$FIXTURE_TRANSCRIPT")
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/log-agent-usage.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/log-agent-usage.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "log-agent-usage.sh differential (rc=$RC_A)"; else note_fail "log-agent-usage.sh differential MISMATCH"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind agent.stop)" = "OK" ] && [ "$(field_eq "$REC" data.tokens 5000)" = "OK" ] \
    && note_pass "log-agent-usage.sh positive: agent.stop{tokens=5000} (accurate toolUseResult total, never the inflated per-turn sum)" \
    || note_fail "log-agent-usage.sh positive assertion failed: $REC"
else note_fail "log-agent-usage.sh: no event captured"; fi

# --- run-recap.sh : gate.forecast{estimates,total_est} ----------------------
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
mkdir -p "$FP/.agents/state/local" "$FPN/.agents/state/local"
RUNLOG_CONTENT='# Run log
| agent | est | actual | note |
|-------|-----|--------|------|
| dev-multi | ~15k | 12.0k |  |
'
printf '%s' "$RUNLOG_CONTENT" > "$FP/.agents/state/local/RUN_LOG.md"
printf '%s' "$RUNLOG_CONTENT" > "$FPN/.agents/state/local/RUN_LOG.md"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(printf '{}' | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/run-recap.sh" 2>&1); RC_A=$?
OUT_B=$(printf '{}' | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/run-recap.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "run-recap.sh differential (rc=$RC_A, systemMessage byte-identical)"; else note_fail "run-recap.sh differential MISMATCH: [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind gate.forecast)" = "OK" ] && [ "$(field_eq "$REC" data.total_est 15.0k)" = "OK" ] \
    && [ "$("$PY" -c "import json,sys; d=json.loads(sys.argv[1])['data']; print('OK' if d.get('estimates') and d['estimates'][0].get('agent')=='dev-multi' else 'MISSING')" "$REC")" = "OK" ] \
    && note_pass "run-recap.sh positive: gate.forecast{estimates,total_est} — emitted BEFORE RUN_LOG.md is cleared" \
    || note_fail "run-recap.sh positive assertion failed: $REC"
else note_fail "run-recap.sh: no event captured"; fi

# --- gitleaks-scan.sh : scan.secrets{status} --------------------------------
GR_A="$(mk_fakerepo yes)"; GR_B="$(mk_fakerepo no)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(printf 'no secret here' | AGENTS_EVENTS_DIR="$EVDIR_A" bash -c 'cd "$1" && bash .agents/security/gitleaks-scan.sh --content' _ "$GR_A" 2>&1); RC_A=$?
OUT_B=$(printf 'no secret here' | AGENTS_EVENTS_DIR="$EVDIR_B" bash -c 'cd "$1" && bash .agents/security/gitleaks-scan.sh --content' _ "$GR_B" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "gitleaks-scan.sh differential (rc=$RC_A)"; else note_fail "gitleaks-scan.sh differential MISMATCH: [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind scan.secrets)" = "OK" ] && [ "$("$PY" -c "import json,sys; print('OK' if json.loads(sys.argv[1])['data'].get('status') else 'MISSING')" "$REC")" = "OK" ] \
    && note_pass "gitleaks-scan.sh positive: scan.secrets{status=$( "$PY" -c "import json,sys;print(json.loads(sys.argv[1])['data']['status'])" "$REC")}" \
    || note_fail "gitleaks-scan.sh positive assertion failed: $REC"
else note_fail "gitleaks-scan.sh: no event captured"; fi

# --- semgrep-scan.sh : scan.sast{status} ------------------------------------
GR_A="$(mk_fakerepo yes)"; GR_B="$(mk_fakerepo no)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(AGENTS_EVENTS_DIR="$EVDIR_A" bash -c 'cd "$1" && bash .agents/security/semgrep-scan.sh' _ "$GR_A" 2>&1); RC_A=$?
OUT_B=$(AGENTS_EVENTS_DIR="$EVDIR_B" bash -c 'cd "$1" && bash .agents/security/semgrep-scan.sh' _ "$GR_B" 2>&1); RC_B=$?
# NORMALIZE THE PERIMETER COUNT BEFORE COMPARING (T-00000370). The fixture pair
# is `mk_fakerepo yes` vs `mk_fakerepo no` — the two repos differ by EXACTLY one
# file, events.py itself. T-00000370 gave the default mode a scope line that
# ANNOUNCES how many files it will scan, so that legitimate one-file difference
# now shows up in stdout: 8 vs 7. That is fixture construction, not a contract
# regression, and it is the case this file's own header prescribes normalizing
# (see the `built @ <sha>` note for stop-reindex.sh). The substitution is kept
# NARROW — only the integer in that one sentence — so any other divergence in
# the scope line, or anywhere else in the output, still fails the comparison.
norm_scope() { sed -E "s/, [0-9]+ scannable file\(s\)/, <N> scannable file(s)/g"; }
OUT_A="$(printf %s "$OUT_A" | norm_scope)"; OUT_B="$(printf %s "$OUT_B" | norm_scope)"
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "semgrep-scan.sh differential (rc=$RC_A)"; else note_fail "semgrep-scan.sh differential MISMATCH: [$OUT_A] vs [$OUT_B]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind scan.sast)" = "OK" ] && [ "$("$PY" -c "import json,sys; print('OK' if json.loads(sys.argv[1])['data'].get('status') else 'MISSING')" "$REC")" = "OK" ] \
    && note_pass "semgrep-scan.sh positive: scan.sast{status=$( "$PY" -c "import json,sys;print(json.loads(sys.argv[1])['data']['status'])" "$REC")}" \
    || note_fail "semgrep-scan.sh positive assertion failed: $REC"
else note_fail "semgrep-scan.sh: no event captured"; fi

# --- sca-scan.sh : scan.sca{status per-ecosystem map} -----------------------
GR_A="$(mk_fakerepo yes)"; GR_B="$(mk_fakerepo no)"
mkdir -p "$GR_A/mod" "$GR_B/mod"
printf '{"name":"x","version":"1.0.0"}' > "$GR_A/mod/package.json"
printf '{"name":"x","version":"1.0.0"}' > "$GR_B/mod/package.json"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
OUT_A=$(AGENTS_EVENTS_DIR="$EVDIR_A" bash -c 'cd "$1" && bash .agents/security/sca-scan.sh mod' _ "$GR_A" 2>&1); RC_A=$?
OUT_B=$(AGENTS_EVENTS_DIR="$EVDIR_B" bash -c 'cd "$1" && bash .agents/security/sca-scan.sh mod' _ "$GR_B" 2>&1); RC_B=$?
# Normalize the two fixture repos' own (necessarily distinct) mktemp paths
# out of the compared text — sca-scan.sh legitimately echoes its absolute
# TGT/OUT/WAIVERS paths, which differ between GR_A and GR_B by construction;
# that is NOT a real differential regression, it is the fixture's own path.
# A prefix-string substitution proved unreliable here (sca-scan.sh's own
# `git rev-parse --show-toplevel` can canonicalize a Windows TEMP path
# differently than a plain `cd && pwd` on the same directory — same
# directory, different text). Regex-strip ANY mktemp-shaped absolute path
# instead of trying to compute the exact matching prefix.
OUT_A_NORM="$("$PY" -c "import re,sys; print(re.sub(r'/[^ \"]*tmp\.[A-Za-z0-9]+(?:/tmp\.[A-Za-z0-9]+)?', '/<REPO>', sys.argv[1]))" "$OUT_A")"
OUT_B_NORM="$("$PY" -c "import re,sys; print(re.sub(r'/[^ \"]*tmp\.[A-Za-z0-9]+(?:/tmp\.[A-Za-z0-9]+)?', '/<REPO>', sys.argv[1]))" "$OUT_B")"
if [ "$OUT_A_NORM" = "$OUT_B_NORM" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "sca-scan.sh differential (rc=$RC_A, path-normalized)"; else note_fail "sca-scan.sh differential MISMATCH: [$OUT_A_NORM] vs [$OUT_B_NORM]"; fi
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ]; then
  STATUS_JSON="$("$PY" -c "import json,sys; print(json.dumps(json.loads(sys.argv[1])['data'].get('status')))" "$REC")"
  [ "$(field_eq "$REC" kind scan.sca)" = "OK" ] \
    && [ "$("$PY" -c "
import json,sys
s = json.loads(sys.argv[1])
ok = isinstance(s, dict) and s.get('npm') == 'scanned' and s.get('java') == 'skipped' and s.get('swift') == 'skipped'
print('OK' if ok else 'MISMATCH ' + repr(s))
" "$STATUS_JSON")" = "OK" ] \
    && note_pass "sca-scan.sh positive: scan.sca{status=$STATUS_JSON} — java/swift correctly 'skipped', never 'scanned' (L-010)" \
    || note_fail "sca-scan.sh positive assertion failed: status=$STATUS_JSON"
else note_fail "sca-scan.sh: no event captured"; fi

# --- agent-events.sh : agent.start / session.stop / session.compact(post) / PostToolUse[Agent] SILENT ---
# The PostToolUse stimuli carry the MEASURED async shape of the Agent tool's
# response (isAsync, agentId, resolvedModel): the leg removed by
# T-01M55Z3ZCS34CDR2EQN1CEBHR7 emitted an EMPTY agent.stop on exactly that
# shape, at the agent's launch. Two spellings: the compact one leaves in bash,
# the spaced one reaches Python — each layer must stay silent on its own.
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
POSTTOOL_ASYNC='{"hook_event_name":"PostToolUse","tool_name":"Agent","session_id":"s1","tool_response":{"isAsync":true,"status":"async_launched","agentId":"a1","resolvedModel":"claude-opus-5-5","description":"x"}}'
POSTTOOL_SPACED='{"tool_name": "Agent", "hook_event_name" : "PostToolUse", "session_id": "s1", "tool_response": {"isAsync": true, "agentId": "a1", "resolvedModel": "claude-opus-5-5", "totalTokens": 4321, "duration_ms": 999}}'
for CASE_IN in \
  '{"hook_event_name":"SubagentStart","session_id":"s1","agent_id":"a1","agent_type":"dev-multi"}' \
  '{"hook_event_name":"SessionEnd","session_id":"s1","reason":"logout"}' \
  '{"hook_event_name":"PostCompact","session_id":"s1"}' \
  "$POSTTOOL_ASYNC" "$POSTTOOL_SPACED"
do
  EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
  OUT_A=$(printf '%s' "$CASE_IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/agent-events.sh" 2>&1); RC_A=$?
  OUT_B=$(printf '%s' "$CASE_IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/agent-events.sh" 2>&1); RC_B=$?
  HNAME="$("$PY" -c "import json,sys; print(json.loads(sys.argv[1])['hook_event_name'])" "$CASE_IN")"
  if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "agent-events.sh[$HNAME] differential (rc=$RC_A)"; else note_fail "agent-events.sh[$HNAME] differential MISMATCH"; fi
  REC="$(last_record "$EVDIR_A")"
  case "$HNAME" in
    SubagentStart)
      [ -n "$REC" ] && [ "$(field_eq "$REC" kind agent.start)" = "OK" ] && [ "$(field_eq "$REC" aid a1)" = "OK" ] \
        && note_pass "agent-events.sh positive: agent.start{aid}" || note_fail "agent-events.sh SubagentStart assertion failed: $REC";;
    SessionEnd)
      [ -n "$REC" ] && [ "$(field_eq "$REC" kind session.stop)" = "OK" ] && [ "$(field_eq "$REC" data.reason logout)" = "OK" ] \
        && note_pass "agent-events.sh positive: session.stop{reason}" || note_fail "agent-events.sh SessionEnd assertion failed: $REC";;
    PostCompact)
      [ -n "$REC" ] && [ "$(field_eq "$REC" kind session.compact)" = "OK" ] && [ "$(field_eq "$REC" data.trigger post)" = "OK" ] \
        && note_pass "agent-events.sh positive: session.compact{trigger=post}" || note_fail "agent-events.sh PostCompact assertion failed: $REC";;
    PostToolUse)
      ALL_PT="$(all_records "$EVDIR_A")"
      if printf '%s' "$ALL_PT" | grep -q '"agent.stop"'; then
        note_fail "agent-events.sh PostToolUse[Agent] emitted an agent.stop — the second, false stop is back: $ALL_PT"
      else
        note_pass "agent-events.sh PostToolUse[Agent] (async isAsync/agentId/resolvedModel): NO agent.stop"
      fi;;
  esac
done

# PostToolUse[Agent] leaves in BASH, before any Python probe (C35: the kept
# registration costs one bash process, nothing more). Witness: a PATH holding
# only what the script needs before that exit, and python3/python/py as STUBS
# that fail the probe and append their path to "$NOPY_MARK" — never an absent
# command: the runner's exported command_not_found_handle would log it and
# classify this suite MISSING DEP (core-scripts/run-bash-tests.sh, criterion of
# `# allows-missing:` — a measurement the script branches on is LINKED, not
# declared). PostToolUse must leave no mark and no stderr; SubagentStart must
# leave a mark AND the probe failure message.
NOPY="$WORK/path-sans-python"; mkdir -p "$NOPY"
for tool in cat dirname; do ln -s "$(command -v "$tool")" "$NOPY/$tool"; done
for py in python3 python py; do
  printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$0" >>"$NOPY_MARK"' 'exit 1' > "$NOPY/$py"
  chmod +x "$NOPY/$py"
done
MARK_PT="$WORK/nopy-mark-pt"; MARK_SS="$WORK/nopy-mark-ss"
BASH_BIN="$(command -v bash)"
ERR_PT="$(printf '%s' "$POSTTOOL_ASYNC" | NOPY_MARK="$MARK_PT" PATH="$NOPY" CLAUDE_PROJECT_DIR="$FP" "$BASH_BIN" "$HOOKS/agent-events.sh" 2>&1 >/dev/null)"; RC_PT=$?
ERR_SS="$(printf '%s' '{"hook_event_name":"SubagentStart","agent_id":"a9"}' | NOPY_MARK="$MARK_SS" PATH="$NOPY" CLAUDE_PROJECT_DIR="$FP" "$BASH_BIN" "$HOOKS/agent-events.sh" 2>&1 >/dev/null)"
if [ "$RC_PT" -eq 0 ] && [ -z "$ERR_PT" ] && [ ! -e "$MARK_PT" ] \
   && [ -s "$MARK_SS" ] && printf '%s' "$ERR_SS" | grep -q 'PYTHON 3 NOT FOUND'; then
  note_pass "agent-events.sh PostToolUse[Agent] exits in bash, before the python probe (witness: SubagentStart does probe)"
else
  note_fail "agent-events.sh PostToolUse[Agent] reached the python probe (rc=$RC_PT, stderr=[$ERR_PT], mark_pt=$([ -e "$MARK_PT" ] && echo yes || echo no), witness=[$ERR_SS])"
fi

# --- THE REAL CHRONO, end to end: SubagentStart (agent-events.sh) -> SubagentStop
# (log-agent-usage.sh), SAME agent_id, SAME project dir (T-01M55Z3ZCS34CDR2EQN1CEBHR7).
# The stop must carry the aid AND a duration_ms: without the start mark there is none.
FP="$(mk_fakeproj)"; EVDIR_A="$(mktemp -d -p "$WORK")"
printf '%s' '{"hook_event_name":"SubagentStart","session_id":"s1","agent_id":"aidpaire1","agent_type":"plan-critic"}' \
  | CLAUDE_PROJECT_DIR="$FP" AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/agent-events.sh" >/dev/null 2>&1
IN=$("$PY" -c "import json,sys; print(json.dumps({'hook_event_name':'SubagentStop','agent_type':'plan-critic','session_id':'s1','agent_id':'aidpaire1','transcript_path':sys.argv[1],'agent_transcript_path':'','last_assistant_message':'done'}))" "$FIXTURE_TRANSCRIPT")
printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP" AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/log-agent-usage.sh" >/dev/null 2>&1
REC="$(last_record "$EVDIR_A")"
if [ -n "$REC" ] && [ "$(field_eq "$REC" kind agent.stop)" = "OK" ] && [ "$(field_eq "$REC" aid aidpaire1)" = "OK" ] \
   && [ "$(field_eq "$REC" data.duration_ms x)" != "MISSING" ]; then
  note_pass "SubagentStart -> SubagentStop: agent.stop{aid, duration_ms}"
else
  note_fail "SubagentStart -> SubagentStop: agent.stop without aid or duration_ms (start never marked?): $REC"
fi
JOURNAL_EVS="$("$PY" -c 'import json,sys; print(" ".join(json.loads(l)["ev"] for l in open(sys.argv[1], encoding="utf-8")))' "$FP/.agents/state/local/agent-chrono.jsonl" 2>/dev/null)"
[ "$JOURNAL_EVS" = "start stop" ] && note_pass "agent-chrono.jsonl: exactly one start then one stop" \
  || note_fail "agent-chrono.jsonl: expected 'start stop', got [$JOURNAL_EVS]"

# --- mcp-events.sh : scan.mcp_call{server,audit_state} + coverage_degraded --
FP="$(mk_fakeproj)"; FPN="$(mk_fakeproj_noevents)"
EVDIR_A="$(mktemp -d -p "$WORK")"; EVDIR_B="$(mktemp -d -p "$WORK")"
IN='{"tool_name":"mcp__figma__use_figma","duration_ms":42}'
OUT_A=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FP"  AGENTS_EVENTS_DIR="$EVDIR_A" bash "$HOOKS/mcp-events.sh" 2>&1); RC_A=$?
OUT_B=$(printf '%s' "$IN" | CLAUDE_PROJECT_DIR="$FPN" AGENTS_EVENTS_DIR="$EVDIR_B" bash "$HOOKS/mcp-events.sh" 2>&1); RC_B=$?
if [ "$OUT_A" = "$OUT_B" ] && [ "$RC_A" -eq "$RC_B" ]; then note_pass "mcp-events.sh differential (rc=$RC_A)"; else note_fail "mcp-events.sh differential MISMATCH"; fi
REC="$(last_record "$EVDIR_A")"
ALL_A="$(all_records "$EVDIR_A")"
if [ -n "$REC" ]; then
  [ "$(field_eq "$REC" kind scan.mcp_call)" = "OK" ] && [ "$(field_eq "$REC" data.server figma)" = "OK" ] && [ "$(field_eq "$REC" data.audit_state unresolved)" = "OK" ] \
    && note_pass "mcp-events.sh positive: scan.mcp_call{server=figma,audit_state=unresolved} (no .mcp.json — NORMAL, L-00000033/34)" \
    || note_fail "mcp-events.sh positive assertion failed: $REC"
  if printf '%s' "$ALL_A" | grep -q '"kind": "gate.coverage_degraded"'; then
    note_fail "mcp-events.sh: 'unresolved' with no project .mcp.json wrongly raised gate.coverage_degraded"
  else
    note_pass "mcp-events.sh: 'unresolved' with no .mcp.json correctly did NOT raise gate.coverage_degraded"
  fi
else note_fail "mcp-events.sh: no event captured"; fi

# mcp-events.sh: resolution FAILURE on a server actually present -> DOES degrade
FP2="$(mk_fakeproj)"
printf '{not valid json' > "$FP2/.mcp.json"
EVDIR_C="$(mktemp -d -p "$WORK")"
printf '%s' '{"tool_name":"mcp__figma__use_figma"}' | CLAUDE_PROJECT_DIR="$FP2" AGENTS_EVENTS_DIR="$EVDIR_C" bash "$HOOKS/mcp-events.sh" >/dev/null 2>&1
ALL_C="$(all_records "$EVDIR_C")"
if printf '%s' "$ALL_C" | grep -q '"kind": "gate.coverage_degraded"'; then
  note_pass "mcp-events.sh: malformed .mcp.json (config actually present) correctly raised gate.coverage_degraded"
else
  note_fail "mcp-events.sh: malformed .mcp.json did not raise gate.coverage_degraded — $ALL_C"
fi

echo
echo "=== SUMMARY ==="
echo "PASS=$PASS FAIL=$FAIL MISSING(step2)=$MISSING"
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: FAIL — $FAIL assertion(s) failed. This is a real problem, fix before proceeding."
  exit 1
fi
if [ "$MISSING" -gt 0 ]; then
  echo "RESULT: RED BY DESIGN — 0 wiring failures, but $MISSING/6 new hook.settings.json row(s) are still unregistered."
  echo "This is expected for shard 2 (registration is the pilot's step 2, out of this shard's scope)."
  echo "Turns green only once ALL 5 new events are pasted into .claude/settings.json (see the JSON block in the report)."
  exit 1
fi
echo "RESULT: PASS — all wiring proven AND all registrations present."
exit 0
