#!/usr/bin/env bash
# Tests for log-agent-usage.sh. Run: bash .claude/hooks/log-agent-usage.test.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_PROJECT_DIR="$TMP"
FIX="$HERE/fixtures/subagent-transcript.jsonl"
LOG="$TMP/.agents/state/local/RUN_LOG.md"
fail() { echo "FAIL: $1"; exit 1; }

# 1. actual capture: reads the subagent's own toolUseResult.totalTokens (5000 -> 5.0k),
#    NOT the sum of per-turn usage (the fixture inflates that to ~245k via cache_read).
printf '{"hook_event_name":"SubagentStop","agent_type":"dev-multi","transcript_path":"%s","last_assistant_message":"done"}' "$FIX" \
  | bash "$HERE/log-agent-usage.sh"
grep -q '| dev-multi | - | 5.0k |' "$LOG" || fail "actual not captured from toolUseResult"
! grep -q '245' "$LOG" || fail "regression: summed per-turn usage instead of reading totalTokens"

# 2. orchestrator seeding: FORECAST block seeds est rows, merges with existing actual
printf '%s' '{"hook_event_name":"SubagentStop","agent_type":"orchestrator","transcript_path":"","last_assistant_message":"PIPELINE:\n  1. planner\nFORECAST                est.\n  planner   write plan   ~8k\n  dev-multi edit 3 files ~15k\n  TOTAL (rough)          ~23k"}' \
  | bash "$HERE/log-agent-usage.sh"
grep -q '| planner | ~8k |' "$LOG" || fail "planner est not seeded"
grep -q '| dev-multi | ~15k | 5.0k |' "$LOG" || fail "est+actual not merged"

# 3. planner refine updates est, keeps actual
printf '%s' '{"hook_event_name":"SubagentStop","agent_type":"planner","transcript_path":"","last_assistant_message":"## Forecast refine\nFORECAST-REFINE: dev-multi ~18k"}' \
  | bash "$HERE/log-agent-usage.sh"
grep -q '| dev-multi | ~18k | 5.0k |' "$LOG" || fail "refine not applied"

# 4. malformed input never fails
echo 'not json' | bash "$HERE/log-agent-usage.sh" || fail "should exit 0 on garbage"

# 5. no matching toolUseResult -> no actual written (honest blank, never a garbage number)
NR="$TMP/no-result.jsonl"
printf '{"type":"assistant","message":{"role":"assistant","usage":{"input_tokens":5,"cache_read_input_tokens":99999,"output_tokens":50}}}\n' > "$NR"
printf '{"hook_event_name":"SubagentStop","agent_type":"optimizer","transcript_path":"%s","last_assistant_message":"x"}' "$NR" \
  | bash "$HERE/log-agent-usage.sh"
! grep -q 'optimizer' "$LOG" || fail "wrote a row for an agent with no toolUseResult (should stay silent)"

# 6. agentType mismatch -> the queried agent gets no actual from another agent's result
printf '{"hook_event_name":"SubagentStop","agent_type":"documenter","transcript_path":"%s","last_assistant_message":"x"}' "$FIX" \
  | bash "$HERE/log-agent-usage.sh"
! grep -q 'documenter' "$LOG" || fail "matched a different agentType's toolUseResult"

# --- THE REAL CHRONO (T-01M55Z3ZCS34CDR2EQN1CEBHR7): journal .agents/state/local/agent-chrono.jsonl ---
JOURNAL="$TMP/.agents/state/local/agent-chrono.jsonl"
PY=""; for c in python3 python py; do "$c" --version >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || fail "no python for the chrono cases"
AT="$TMP/agent-transcript.jsonl"   # the AGENT's own transcript: last turn = 2+1000+200000+600 = 201602
printf '%s\n' '{"type":"assistant","message":{"role":"assistant","usage":{"input_tokens":5,"cache_read_input_tokens":99999,"output_tokens":50}}}' \
  '{"type":"assistant","message":{"role":"assistant","usage":{"input_tokens":2,"cache_creation_input_tokens":1000,"cache_read_input_tokens":200000,"output_tokens":600}}}' > "$AT"
stop_of() { # <aid> -> the last `stop` line of that aid, or nothing
  "$PY" -c 'import json,sys
for l in reversed(open(sys.argv[1], encoding="utf-8").read().splitlines()):
    d = json.loads(l)
    if d.get("ev") == "stop" and d.get("aid") == sys.argv[2]:
        print(json.dumps(d, sort_keys=True)); break' "$JOURNAL" "$1" 2>/dev/null
}
field() { "$PY" -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2], "ABSENT"))' "$1" "$2"; }

# 7. a start 90 s ago (written in the contract's form, never by the module under test) + the
#    same agent_id at SubagentStop -> stop line with that duration and the agent's last-turn tokens.
mkdir -p "$(dirname "$JOURNAL")"
"$PY" -c 'import json,sys,time; print(json.dumps({"ev":"start","aid":"aid-90","agent":"plan-critic","ts":int(time.time()*1000)-90000}))' >> "$JOURNAL"
printf '{"hook_event_name":"SubagentStop","agent_type":"plan-critic","agent_id":"aid-90","agent_transcript_path":"%s","transcript_path":"","last_assistant_message":"x"}' "$AT" \
  | bash "$HERE/log-agent-usage.sh"
S7="$(stop_of aid-90)"
[ -n "$S7" ] || fail "no stop line for aid-90"
D7="$(field "$S7" duration_ms)"
[ "$D7" -ge 90000 ] 2>/dev/null && [ "$D7" -lt 100000 ] || fail "duration_ms=$D7, expected 90 s since the start"
[ "$(field "$S7" tokens)" = "201602" ] || fail "tokens=$(field "$S7" tokens), expected the agent's last turn 201602"
grep -q '| plan-critic | - | 201.6k |' "$LOG" || fail "RUN_LOG actual did not take the agent transcript's figure"

# 8. no start seen -> stop line WITHOUT duration_ms (never a 0)
printf '{"hook_event_name":"SubagentStop","agent_type":"planner","agent_id":"aid-sans-depart","agent_transcript_path":"%s","last_assistant_message":"x"}' "$AT" \
  | bash "$HERE/log-agent-usage.sh"
S8="$(stop_of aid-sans-depart)"
[ -n "$S8" ] && [ "$(field "$S8" duration_ms)" = "ABSENT" ] || fail "no start, yet a duration (or no stop line): $S8"

# 9. the REAL pair: agent-events.sh SubagentStart then this hook, same agent_id, same project dir
printf '{"hook_event_name":"SubagentStart","agent_id":"aid-paire","agent_type":"dev-multi"}' | bash "$HERE/agent-events.sh"
printf '{"hook_event_name":"SubagentStop","agent_type":"dev-multi","agent_id":"aid-paire","agent_transcript_path":"%s","last_assistant_message":"x"}' "$AT" \
  | bash "$HERE/log-agent-usage.sh"
S9="$(stop_of aid-paire)"
[ "$(field "$S9" duration_ms)" != "ABSENT" ] || fail "SubagentStart -> SubagentStop: no duration (start never marked?): $S9"

# 10. agent_chrono.py ABSENT, or RAISING, in the hook's own tree -> the hook keeps its pre-chrono
#     behaviour (loader and calls under try): RUN_LOG captured, rc 0, no journal written.
for mode in absent leve; do
  KITX="$TMP/kit-$mode"; ETAT="$TMP/etat-$mode"
  mkdir -p "$KITX/.claude/hooks" "$KITX/.agents/bin" "$ETAT"
  cp "$HERE/log-agent-usage.sh" "$KITX/.claude/hooks/log-agent-usage.sh"
  [ "$mode" = leve ] && printf 'raise RuntimeError("casse")\n' > "$KITX/.agents/bin/agent_chrono.py"
  printf '{"hook_event_name":"SubagentStop","agent_type":"dev-multi","agent_id":"aid-x","transcript_path":"%s","last_assistant_message":"done"}' "$FIX" \
    | CLAUDE_PROJECT_DIR="$ETAT" bash "$KITX/.claude/hooks/log-agent-usage.sh" || fail "module $mode: rc != 0"
  grep -q '| dev-multi | - | 5.0k |' "$ETAT/.agents/state/local/RUN_LOG.md" || fail "module $mode: RUN_LOG lost"
  [ ! -e "$ETAT/.agents/state/local/agent-chrono.jsonl" ] || fail "module $mode: a journal was written"
done

# 11. the session-transcript fallback (toolUseResult) feeds RUN_LOG only, NEVER the journal: an aid
#     whose own transcript is absent gets a stop line WITHOUT `tokens` (no unproven figure recorded).
printf '{"hook_event_name":"SubagentStop","agent_type":"dev-multi","agent_id":"aid-repli","transcript_path":"%s","last_assistant_message":"x"}' "$FIX" \
  | bash "$HERE/log-agent-usage.sh"
S11="$(stop_of aid-repli)"
[ -n "$S11" ] && [ "$(field "$S11" tokens)" = "ABSENT" ] || fail "the toolUseResult fallback reached the journal: $S11"

echo "PASS: log-agent-usage (11/11)"
