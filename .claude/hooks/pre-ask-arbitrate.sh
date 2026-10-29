#!/usr/bin/env bash
# PreToolUse [AskUserQuestion] — one forced checkpoint per question: take the
# answer that best serves the task when it is obvious, ask only when the choice
# is genuinely the pilot's.
#
# WHY THIS EVENT. Its sibling stop-arbitrate.sh fires on Stop, at the END of a
# turn, but a menu is handed over DURING the turn inside a tool call — so that
# guard sat after the thing it was meant to prevent and could only speak once the
# question had already been asked. Same defect class as a probe that can only
# pass, and as an inventory test asserting file layout: both found in this repo
# on 2026-07-27, which makes "wrong anchor point, correct internal logic" the
# dominant failure mode here. PreToolUse runs before the call and can refuse it.
#
# WHY NOT DETECT A MARKER. The first version blocked only when an option label
# carried "(recommandé)". That is a proxy, and a bad one: it is trivially gamed
# by deleting five characters, and it says nothing about the real question —
# whether the best answer was OBVIOUS for the task at hand. A guard that can be
# satisfied by editing a label measures the label, not the judgement.
#
# THE MECHANISM. One checkpoint per distinct question, per session. The first
# time a given question is submitted it is REFUSED, with the rule. If, having
# actually weighed it, the model still needs the pilot, it re-submits the SAME
# question and the call goes through. So:
#   * every question costs one deliberate pass before it reaches the pilot;
#   * a genuinely necessary question is never blocked, only delayed by one turn;
#   * there is no loop by construction — the second identical submission passes;
#   * and no magic word exists to game, because the escape is re-asking, which
#     is exactly the behaviour we want when the answer is not obvious.
# A materially CHANGED question hashes differently and gets its own checkpoint.
# That is intended: a different question deserves a fresh pass, and it also
# stops "reword it slightly until it goes through" from being cheaper than
# thinking.
#
# Anything unexpected — no python, unreadable stdin, unwritable marker dir —
# exits 0. A broken guard must never cost the pilot the ability to be asked a
# question, and must never wedge a turn.
#
# Registered in .claude/settings.local.json (git-ignored, personal), never in
# .claude/settings.json, so it does not ship enabled and never sits in the same
# file as the class-0 gates.

INPUT=$(cat)

PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -z "$PY" ] && exit 0

DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

REASON=$("$PY" - "$INPUT" "$DIR" <<'PYEOF'
import hashlib, json, os, sys

try:
    payload = json.loads(sys.argv[1] or "{}")
except Exception:
    sys.exit(0)                       # unparseable: never block a question

if payload.get("tool_name") != "AskUserQuestion":
    sys.exit(0)

questions = (payload.get("tool_input") or {}).get("questions") or []
if not questions:
    sys.exit(0)

# Identity of the question, stable across re-submission and sensitive to any
# material change: the prompt text plus every option label, in order.
parts = []
for q in questions:
    if not isinstance(q, dict):
        continue
    parts.append(str(q.get("question") or ""))
    for opt in q.get("options") or []:
        if isinstance(opt, dict):
            parts.append(str(opt.get("label") or ""))
key = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]

sid = str(payload.get("session_id") or "nosession")
sid_key = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:12]

mark_dir = os.path.join(sys.argv[2], ".agents", "state", "local",
                        "pre-ask-arbitrate", sid_key)
mark = os.path.join(mark_dir, key)
try:
    os.makedirs(mark_dir, exist_ok=True)
    # O_CREAT|O_EXCL is reliable on Windows (unlike O_APPEND — L-00000041), so
    # this doubles as the single-flight primitive: whoever creates it, blocks.
    fd = os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
except FileExistsError:
    sys.exit(0)                       # already checkpointed: let it through
except Exception:
    sys.exit(0)                       # cannot bound the checkpoint -> allow

headers = [str((q or {}).get("header") or (q or {}).get("question") or "?")
           for q in questions if isinstance(q, dict)]

print("\n".join([
    "ARBITRATION CHECKPOINT — this question was held back once "
    "(pre-ask-arbitrate.sh). It is not forbidden, it is delayed by one pass.",
    "",
    "  question(s): " + " | ".join(headers[:4]),
    "",
    "Take the answer that best serves the TASK when it is obvious. Obvious "
    "means: the repo, the ledger, the board, or the task sheet already settle "
    "it; one option is plainly better on the merits; or a sensible default "
    "exists and the cost of being wrong is a cheap correction. In that case "
    "act, say in one line why that option wins, and keep going.",
    "",
    "Ask only when the choice is genuinely the pilot's: it is irreversible or "
    "expensive to undo, it trades off things only they can weigh (scope, "
    "budget, risk appetite, priorities), it depends on intent you cannot read "
    "from the repo, or being wrong would waste substantial work.",
    "",
    "If after weighing it you still need them, re-submit the SAME question and "
    "it will go through — and state in one sentence why the decision is "
    "theirs. If you can now answer it yourself, do that instead and do not "
    "mention this checkpoint.",
]))
PYEOF
) || exit 0

[ -z "$REASON" ] && exit 0

printf '%s\n' "$REASON" >&2
exit 2
