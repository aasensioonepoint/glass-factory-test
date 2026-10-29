"""Terminal-event hook: capture per-agent tokens into the shared run log; on
session-level stops (no agent in payload) also emit the est->actual recap and
clear the log. Advisory: never raises, never blocks. One file, byte for byte
in `.codex/hooks/` and `.gemini/hooks/`, registered by FOUR files: Codex
SubagentStop + Stop (.codex/hooks.json), Copilot subagentStop + agentStop
(.github/hooks/agent-guardrails.json) and Kimi SubagentStop + Stop
(.kimi-code/hooks.json) run the `.codex` copy; Antigravity SubagentStop + Stop
(.agents/hooks.json) runs the `.gemini` copy. The lock prefix follows the
directory (_common.hook_dir), one lock per directory. On SubagentStop the
agent-specific transcript (agent_transcript_path) takes priority over the
session transcript."""
import json
import hashlib
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from _common import ROOT, emit_event, event_host, hook_dir, read_payload, system_message

LOG = ROOT / ".agents" / "state" / "local" / "RUN_LOG.md"
FLAG_PCT = 30
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens")
HEADER = [
    "# Run log — ephemeral (git-ignored). est seeded from FORECAST; actual filled on agent stop; cleared by recap.",
    "| agent | est | actual | note |",
    "|-------|-----|--------|------|",
]
ROW = re.compile(r"\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")

Rows = Dict[str, List[str]]


def fmt(tokens: int) -> str:
    return f"{tokens/1000:.1f}k" if tokens >= 1000 else str(tokens)


def toi(s: str) -> Optional[int]:
    s = (s or "").strip().lstrip("~")
    m = re.match(r"^(\d+(?:\.\d+)?)k$", s)
    if m:
        return int(float(m.group(1)) * 1000)
    return int(s) if s.isdigit() else None


def read_rows() -> Tuple[Rows, List[str]]:
    rows: Rows = {}
    order: List[str] = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            m = ROW.match(line)
            if m and m.group(1) != "agent" and set(m.group(1)) - {"-"}:
                rows[m.group(1)] = [m.group(2).strip(), m.group(3).strip(), m.group(4).strip()]
                if m.group(1) not in order:
                    order.append(m.group(1))
    return rows, order


def write_rows(rows: Rows, order: List[str]) -> None:
    lines = HEADER + [
        f"| {a} | {rows[a][0] or '-'} | {rows[a][1] or ''} | {rows[a][2] or ''} |"
        for a in order
    ]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=LOG.parent,
            prefix="RUN_LOG.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp.write("\n".join(lines) + "\n")
            temp.flush()
            os.fsync(temp.fileno())
            temp_path = Path(temp.name)
        os.replace(temp_path, LOG)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@contextmanager
def log_lock(timeout=10):
    lock_id = hashlib.sha256(str(LOG.resolve()).encode("utf-8")).hexdigest()[:16]
    prefix = hook_dir(__file__).lstrip(".")
    lock_path = Path(tempfile.gettempdir()) / f"{prefix}-run-log-{lock_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write("0")
            handle.flush()
        deadline = time.monotonic() + timeout
        acquired = False
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for the usage log lock")
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def seed_from_message(msg: str, rows: Rows, order: List[str]) -> None:
    in_block = False
    for line in msg.splitlines():
        if re.match(r"\s*FORECAST\b", line) and "REFINE" not in line:
            in_block = True
            continue
        if in_block:
            if re.match(r"\s*TOTAL\b", line) or re.match(r"\s*-{4,}\s*$", line):
                in_block = False
                continue
            m = re.match(r"\s*([a-z][a-z0-9-]*)\s+.*?(~\d+k|~\?)\s*$", line)
            if m:
                prev = rows.get(m.group(1), ["", "", ""])
                rows[m.group(1)] = [m.group(2), prev[1], prev[2]]
                if m.group(1) not in order:
                    order.append(m.group(1))
    for m in re.finditer(r"FORECAST-REFINE:\s*([a-z][a-z0-9-]*)\s+(~\d+k)", msg):
        prev = rows.get(m.group(1), ["", "", ""])
        rows[m.group(1)] = [m.group(2), prev[1], prev[2]]
        if m.group(1) not in order:
            order.append(m.group(1))


def transcript_total(path: str) -> int:
    total = 0
    p = Path(path)
    if not p.exists():
        return 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(j, dict):
            continue
        u = (j.get("message") or {}).get("usage") if isinstance(j.get("message"), dict) else None
        u = u or j.get("usage") or {}
        if isinstance(u, dict):
            total += sum(int(u.get(k) or 0) for k in USAGE_KEYS)
    return total


def recap(rows: Rows, order: List[str]) -> Optional[str]:
    est_rows = [a for a in order if rows[a][0].startswith("~")]
    if not est_rows:
        return None
    have_actual = any(toi(rows[a][1]) for a in est_rows)
    src = "hook" if have_actual else "baseline — no hook captures"
    out = [f"RECAP [source: {src}]  est → actual"]
    te = ta = 0
    flags: List[str] = []
    for a in est_rows:
        ev, av = toi(rows[a][0]), toi(rows[a][1])
        if ev:
            te += ev
        if av:
            ta += av
            pct = round((av - ev) / ev * 100) if ev else 0
            mark = f"⚠ {pct:+d}%" if ev and abs(pct) > FLAG_PCT else "✓"
            if ev and abs(pct) > FLAG_PCT:
                flags.append(a)
            out.append(f"  {a:<18} {rows[a][0]:>5} → {rows[a][1]:>7}  {mark}")
        else:
            out.append(f"  {a:<18} {rows[a][0]:>5} → {'—':>7}  (self-reported)")
    out.append(f"  TOTAL  est {fmt(te)} → actual {fmt(ta) if ta else '—'}")
    if flags:
        out.append(f"  ⚠ {', '.join(flags)} off >{FLAG_PCT}% — consider tuning .agents/ref/TOKEN_BUDGETS.md")
    return "\n".join(out)


def forecast_fields(rows: Rows, order: List[str]) -> dict:
    """`{estimates, total_est}` for gate.forecast, from the rows this recap just
    reconciled — the reader computes variance, the emitter only writes the dated
    fact (design doc §C: "events.py n'agrège jamais").

    `total_est` is formatted with an unconditional `k` suffix to match the Claude
    homologue's fmtk(), NOT this file's fmt(), which drops the suffix under 1000
    and would make the same total read differently per host.
    """
    est_rows = [a for a in order if rows[a][0].startswith("~")]
    total = sum(toi(rows[a][0]) or 0 for a in est_rows)
    return {
        "estimates": [
            {"agent": a, "est": rows[a][0], "actual": rows[a][1]} for a in est_rows
        ],
        "total_est": f"{total/1000:.1f}k",
    }


def main() -> None:
    payload = read_payload()
    agent = (payload.get("agentType") or payload.get("agent_type") or "").strip()
    sid = payload.get("sessionId") or payload.get("session_id") or None
    aid = payload.get("agentId") or payload.get("agent_id") or None
    msg = payload.get("lastAssistantMessage") or payload.get("last_assistant_message") or ""
    transcript = (payload.get("agentTranscriptPath") or payload.get("agent_transcript_path")
                  or payload.get("transcriptPath") or payload.get("transcript_path")
                  or payload.get("conversationPath") or payload.get("conversation_path") or "")
    with log_lock():
        rows, order = read_rows()
        if msg:
            seed_from_message(msg, rows, order)
        # Sous copilot, transcriptPath désigne l'events.jsonl du PARENT (M-P10),
        # sans aucune clé `usage` : jusqu'à 10 Mo étaient lus pour 0. Le total
        # n'y est donc plus calculé, ni agent.stop émis au subagentStop
        # (T-01M4RWC6VHHN479J2A9RRY1BE3 ; SANS_ENREGISTREMENT de
        # test_events_parity.py). Codex, Kimi et Gemini (étiqueté par son
        # répertoire, jamais par la variable) sont inchangés.
        if agent and transcript and event_host() != "copilot":
            total = transcript_total(transcript)
            if total:
                prev = rows.get(agent, ["", "", ""])
                rows[agent] = [prev[0], fmt(total), prev[2]]
                if agent not in order:
                    order.append(agent)
                # agent.stop{tokens,est} — the one place this host computes a
                # real per-agent total. Same kind and same fields as the Claude
                # homologue; ALLOWLIST(agent.stop) also has duration_ms/model,
                # which this payload shape does not carry and which are therefore
                # left ABSENT rather than guessed (an absent field is a fact the
                # Coverage view can read; a fabricated one is not).
                emit_event(
                    "agent.stop", sid=sid, aid=aid, agent=agent,
                    tokens=total, est=rows[agent][0] or None,
                )
        if not agent:  # session-level stop → recap once, then reset
            text = recap(rows, order)
            if text:
                system_message(text)
                # gate.forecast — emitted BEFORE the log is cleared just below,
                # the same ordering (and the same fields) as run-recap.sh on
                # Claude: after write_rows({}, []) the reconciled estimates no
                # longer exist anywhere.
                emit_event("gate.forecast", sid=sid, **forecast_fields(rows, order))
                write_rows({}, [])
                return
        if order:
            write_rows(rows, order)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
