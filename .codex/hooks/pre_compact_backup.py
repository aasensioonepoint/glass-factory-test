import shutil
import time
from pathlib import Path

from _common import ROOT, emit_event, hook_dir, read_payload


def main():
    payload = read_payload()
    # session.compact{trigger=pre} — emitted BEFORE the transcript checks below,
    # exactly where .claude/hooks/pre-compact.sh emits it: a compaction happened
    # whether or not there was a transcript to copy, and gating the event on the
    # backup succeeding would silently under-report compactions. NEVER the
    # transcript or a summary of it — events.py allowlists {trigger, tokens} for
    # this kind precisely so model prose cannot reach a committed stream.
    emit_event("session.compact", trigger="pre")
    transcript = (
        payload.get("transcriptPath")
        or payload.get("transcript_path")
        or payload.get("conversationPath")
        or payload.get("conversation_path")
    )
    if not transcript:
        return
    source = Path(transcript)
    if not source.exists():
        return
    dest_dir = ROOT / hook_dir(__file__) / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"pre-compact-{time.time_ns()}.jsonl"
    shutil.copy2(source, dest)
    backups = sorted(dest_dir.glob("pre-compact-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[10:]:
        old.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
