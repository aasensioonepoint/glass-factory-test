#!/usr/bin/env bash
# Stop — print est→actual recap from .agents/state/local/RUN_LOG.md (only if forecast rows exist)
# plus the task-board headline, then clear the run log.
# Advisory only: ALWAYS exits 0.
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$ROOT/.agents/state/local/RUN_LOG.md"
PY=""
PY_PROBE='import sys; sys.stdout.write(sys.executable); sys.exit(sys.version_info[0] != 3)'
PY_CR="$(printf '\r')"
for c in python3 python; do
  PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
  case "$PY_CANDIDATE" in
    *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
  esac
  if [ -n "$PY_CANDIDATE" ]; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  PY_UNAME=""
  command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"
  case "${OS-}:$PY_UNAME" in
    Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)
      PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" || PY_CANDIDATE=""
      case "$PY_CANDIDATE" in
        *"$PY_CR") PY_CANDIDATE="${PY_CANDIDATE%?}" ;;
      esac
      [ -n "$PY_CANDIDATE" ] && PY="$PY_CANDIDATE"
      ;;
  esac
fi
[ -n "$PY" ] || {
  echo "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3." >&2
  exit 0
}
# T-00001191 : aucun `.pyc` (events.py, redaction.py, tasks.py chargés par chemin) ; l'env atteint les enfants.
export PYTHONDONTWRITEBYTECODE=1
"$PY" -B - "$LOG" "$ROOT" << 'PYEOF'
import importlib.util, json, re, subprocess, sys
from pathlib import Path

FLAG_PCT = 30  # spec default ⚠ threshold

# events.py loaded by EXPLICIT PATH — `from events import emit` is BANNED
# here. This script runs Python FED FROM STDIN (`"$PY" - "$LOG" "$ROOT"
# << 'PYEOF'`, see above) — sys.path[0] there is the invoking shell's cwd,
# not this file's directory, so a bare name-import would silently resolve to
# nothing. Same idiom this file ALREADY uses at :39-41 below to load tasks.py.
def _load_events(root):
    try:
        p = Path(root) / ".agents" / "bin" / "events.py"
        spec = importlib.util.spec_from_file_location("events", p)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None
HEADER = [
    "# Run log — ephemeral (git-ignored). est seeded from FORECAST; actual filled on SubagentStop; cleared by recap.",
    "| agent | est | actual | note |",
    "|-------|-----|--------|------|",
]

def toi(s):
    s = (s or "").strip().lstrip("~")
    m = re.match(r"^(\d+(?:\.\d+)?)k$", s)
    if m:
        return int(float(m.group(1)) * 1000)
    return int(s) if s.isdigit() else None

def fmtk(t):
    return f"{t/1000:.1f}k"

def board_line(root):
    """Task-board headline for the session end: what is running, what is left,
    and whether the board moved. The diff is taken on TASKS.json — the tracked
    source of truth; TASKS.md is a generated, git-ignored view. `git diff` is
    against the last commit, not session start — hence "uncommitted".

    TWO STORE FORMS (T-00001012, BK-419, E-26): the board is present as the TASKS.json monolith OR
    as at least one `T-*.json` record under `board/tasks/` (home fixed by pilot decision
    S-01M4N1G4VXD01A3W54Y9FR9856, beside `board/epics/`); a dotted name — the temp of an atomic
    write — never counts. The headline itself still comes from `statusline` (the API), never from a
    raw read. BOUND, written: an UNTRACKED record is not a diff line, so a board in record form
    counts only the tracked records it changed. Claude only: the Codex/Copilot/Kimi/Gemini hooks
    carry no run recap."""
    board = Path(root) / ".agents" / "state" / "board" / "TASKS.json"
    records = board.parent / "tasks"
    try:
        en_dossier = any(p.name.startswith("T-") and p.name.endswith(".json") and p.is_file()
                         for p in records.iterdir())
    except OSError:
        en_dossier = False
    if not board.exists() and not en_dossier:
        return ""
    try:
        # tasks.py lives in .agents/bin/, NEVER beside the store. `board.parent`
        # was right only while TASKS.json still sat in .agents/bin/ (ee3c930);
        # the bin/ref/state split (4b447c1) moved the store and left this path
        # stale, so every call raised FileNotFoundError into the `except` below
        # and the BOARD headline AGENTS.md promises silently stopped appearing.
        # Same `root`-anchored form as every other explicit-path load in the
        # hooks (statusline.sh:22, log-agent-usage.sh:21, emit-event.sh).
        spec = importlib.util.spec_from_file_location("tasks", Path(root) / ".agents" / "bin" / "tasks.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        line = mod.statusline(str(root))
    except Exception:
        return ""
    # startswith, not ==: tasks.py returns the bare sentinel ONLY for a board
    # with zero tasks (tasks.py:399). An idle board that HAS tasks returns
    # "no active task · ⏸0 ✓1", which slipped past an equality check and put
    # "BOARD no active task" in the recap — a headline about nothing. Never
    # observed, because this whole function was dead until the tasks.py path
    # above was fixed. A blocked head ("⛔ T-… blocked") still prints: the guard
    # suppresses the idle case, not the absence of a *running* task.
    if line.startswith("no active task"):
        return ""
    try:
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--numstat", "HEAD", "--", str(board), str(records),
             str(board.parent / "epics")],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if diff:
            changed = sum(int(f.split("\t")[0]) for f in diff.splitlines() if f.split("\t")[0].isdigit())
            if changed:
                line += f" · {changed} board line(s) uncommitted"
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return "BOARD " + line


def main():
    p = Path(sys.argv[1])
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    board = board_line(root)
    rows = []
    if not p.exists():
        if board:
            print(json.dumps({"systemMessage": board}))
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$", line)
        if m and m.group(1) != "agent" and set(m.group(1)) - {"-"}:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()))
    rows = [r for r in rows if r[1].startswith("~")]
    if not rows:
        # No forecast to reconcile, but the board headline still stands on its own.
        if board:
            print(json.dumps({"systemMessage": board}))
        return

    have_actual = any(toi(r[2]) for r in rows)
    src = "hook" if have_actual else "baseline — no hook captures"
    out = [f"RECAP [source: {src}]  est → actual"]
    te = ta = 0
    flags = []
    for a, e, act, note in rows:
        ev, av = toi(e), toi(act)
        if ev:
            te += ev
        if av:
            ta += av
            if ev:
                pct = round((av - ev) / ev * 100)
                mark = f"⚠ {pct:+d}%" if abs(pct) > FLAG_PCT else "✓"
                if abs(pct) > FLAG_PCT:
                    flags.append(a)
            else:
                mark = ""
            out.append(f"  {a:<18} {e:>5} → {act:>7}  {mark}")
        else:
            out.append(f"  {a:<18} {e:>5} → {'—':>7}  (self-reported)")
    out.append(f"  TOTAL  est {fmtk(te)} → actual {fmtk(ta) if ta else '—'}")
    if flags:
        out.append(f"  ⚠ {', '.join(flags)} off >{FLAG_PCT}% — consider tuning .agents/ref/TOKEN_BUDGETS.md")
    if board:
        out.append(board)
    print(json.dumps({"systemMessage": "\n".join(out)}))

    # gate.forecast — EMITTED BEFORE clearing RUN_LOG.md below (shard-2 spec:
    # "run-recap.sh émet AVANT de vider RUN_LOG.md — la ligne la plus
    # rentable du lot"). ALLOWLIST(gate.forecast) = {estimates, total_est};
    # `estimates` is the per-agent est/actual pairs this recap already
    # reconciled — the reader computes duration/variance, this just writes
    # the dated fact (design doc §C: "events.py n'agrège jamais").
    events = _load_events(root)
    if events is not None:
        estimates = [{"agent": a, "est": e, "actual": act} for a, e, act, _note in rows]
        try:
            events.emit("gate.forecast", host="claude", estimates=estimates, total_est=fmtk(te))
        except Exception:
            pass

    p.write_text("\n".join(HEADER) + "\n", encoding="utf-8")

try:
    main()
except Exception:
    pass
sys.exit(0)
PYEOF
exit 0
