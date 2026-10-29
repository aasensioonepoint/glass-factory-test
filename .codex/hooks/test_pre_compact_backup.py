import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    tmp = Path(tempfile.mkdtemp())
    try:
        hooks = tmp / ".codex" / "hooks"
        hooks.mkdir(parents=True)
        shutil.copy2(HERE / "_common.py", hooks / "_common.py")
        shutil.copy2(HERE / "pre_compact_backup.py", hooks / "pre_compact_backup.py")
        transcript = tmp / "transcript.jsonl"
        transcript.write_text(json.dumps({"message": "sensitive"}) + "\n", encoding="utf-8")
        payload = json.dumps({"transcript_path": str(transcript)})
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-B", str(hooks / "pre_compact_backup.py")],
                input=payload,
                capture_output=True,
                text=True,
                cwd=tmp,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        backups = list((tmp / ".codex" / "backups").glob("pre-compact-*.jsonl"))
        assert len(backups) == 2, backups
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS: pre_compact_backup (2/2)")


if __name__ == "__main__":
    main()
