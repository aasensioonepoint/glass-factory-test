#!/usr/bin/env bash
# Stop — arbitration reminder: when several recommendations are on the table,
# pick the strongest and act; when none dominates, ask the pilot.
#
# WHY THIS BLOCKS. A Stop hook's stdout on exit 0 is shown in the transcript but
# never enters the model's context. The only channel back into the model is a
# {"decision":"block","reason":...} response — which by definition prevents the
# stop. So "advisory" is not available here: blocking IS the mechanism, and
# loop-safety is therefore the entire design of this file.
#
# TWO CUMULATIVE GUARDS, either one alone sufficient to forbid an infinite loop:
#   1. stop_hook_active — the host sets this true when the model is already
#      continuing BECAUSE of a stop hook. Seeing it, we exit 0 immediately.
#   2. a per-session marker under state/local/ (git-ignored, throw-away bucket):
#      at most ONE block per session, so the cost is one short turn per session
#      rather than one per user turn.
#
# Anything unexpected — no python, unreadable stdin, unwritable marker dir —
# exits 0. This hook must never be able to hold a session open. A benign path
# that fails closed is how a Stop hook freezes a host, and that has already
# happened once in this project.
#
# It is registered in .claude/settings.local.json (git-ignored, personal), NOT
# in .claude/settings.json, so it never travels with the kit and never sits in
# the same file as the class-0 gates.

INPUT=$(cat)

PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -z "$PY" ] && exit 0

DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

"$PY" - "$INPUT" "$DIR" <<'PYEOF' || exit 0
import json, os, sys, hashlib

try:
    payload = json.loads(sys.argv[1] or "{}")
except Exception:
    sys.exit(0)                      # unparseable stdin: never hold the session

# Guard 1 — the host's own anti-loop signal.
if payload.get("stop_hook_active"):
    sys.exit(0)

root = sys.argv[2]
sid = str(payload.get("session_id") or "")
if not sid:
    sys.exit(0)                      # no session identity -> cannot bound; stay out

# Guard 2 — one block per session. Marker lives in the throw-away bucket, keyed
# by a hash so a session id never lands in a filename.
mark_dir = os.path.join(root, ".agents", "state", "local", "stop-arbitrate")
mark = os.path.join(mark_dir, hashlib.sha256(sid.encode()).hexdigest()[:16])
try:
    os.makedirs(mark_dir, exist_ok=True)
    # O_CREAT|O_EXCL is reliable on Windows (unlike O_APPEND — see L-00000041),
    # so this doubles as the single-flight primitive: whoever creates it, blocks.
    fd = os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
except FileExistsError:
    sys.exit(0)                      # already reminded this session
except Exception:
    sys.exit(0)                      # cannot bound the reminder -> do not block

REASON = (
    "ARBITRATION CHECK (once per session, from stop-arbitrate.sh) — this is a "
    "reminder about how to end the turn, not a new task and not a request to "
    "start work.\n"
    "If you are holding SEVERAL candidate recommendations or next steps: pick "
    "the strongest one on the merits, say in one line why it beats the others, "
    "and act on it. Do not hand the pilot a menu you could have resolved.\n"
    "If no option genuinely dominates — the trade-off is the pilot's to make, "
    "the choice is irreversible, or it depends on intent you cannot read from "
    "the repo — then ASK, with the real trade-off stated, not a survey.\n"
    "If you were already acting on a clear best step, or the turn is simply "
    "finished, stop now: say nothing further and end. Do not invent extra work "
    "to justify this reminder."
)

print(json.dumps({"decision": "block", "reason": REASON}))
PYEOF
exit 0
