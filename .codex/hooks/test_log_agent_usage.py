"""Tests for log_agent_usage.py. Run: python .codex/hooks/test_log_agent_usage.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def run_hook(root: Path, payload: dict, host=None, events_dir=None) -> subprocess.CompletedProcess:
    # The host marker is NEVER inherited: arm 7 proves the copilot branch differs,
    # so an AGENTS_HOOK_HOST left in the caller's shell must not leak into arms 1-6.
    env = dict(os.environ)
    env.pop("AGENTS_HOOK_HOST", None)
    if host is not None:
        env["AGENTS_HOOK_HOST"] = host
    if events_dir is not None:
        env["AGENTS_EVENTS_DIR"] = str(events_dir)
    return subprocess.run(
        [sys.executable, str(root / ".codex" / "hooks" / "log_agent_usage.py")],
        input=json.dumps(payload), capture_output=True, text=True, cwd=root, timeout=30, env=env,
    )


def event_records(events_dir: Path) -> list:
    lines = b"".join(p.read_bytes() for p in sorted(events_dir.glob("*.jsonl")))
    return [json.loads(l) for l in lines.decode("utf-8").splitlines() if l.strip()]


def event_kinds(events_dir: Path) -> list:
    return [rec["kind"] for rec in event_records(events_dir)]


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    passed = 0
    try:
        hooks = tmp / ".codex" / "hooks"
        hooks.mkdir(parents=True)
        shutil.copy2(HERE / "_common.py", hooks / "_common.py")
        shutil.copy2(HERE / "log_agent_usage.py", hooks / "log_agent_usage.py")
        fix = tmp / "transcript.jsonl"
        shutil.copy2(HERE / "fixtures" / "transcript.jsonl", fix)
        log = tmp / ".agents" / "state" / "local" / "RUN_LOG.md"

        # 1. agent-level stop: capture actual for that agent
        r = run_hook(tmp, {"agentType": "dev-multi", "transcriptPath": str(fix)})
        assert r.returncode == 0, r.stderr
        assert "| dev-multi | - | 6.5k |" in log.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")
        passed += 1

        # 2. SubagentStop payload: agent_transcript_path wins over (absent) session transcript
        r = run_hook(tmp, {"agent_type": "planner", "agent_id": "x1",
                           "transcript_path": str(tmp / "absent-session.jsonl"),
                           "agent_transcript_path": str(fix)})
        assert r.returncode == 0, r.stderr
        assert "| planner | - | 6.5k |" in log.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")
        passed += 1

        # 3. session stop with FORECAST in last message: seed est, then recap + clear
        msg = "FORECAST  est.\n  dev-multi edit ~5k\n  TOTAL ~5k"
        r = run_hook(tmp, {"lastAssistantMessage": msg})
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert "RECAP" in out.get("systemMessage", ""), r.stdout
        assert "| dev-multi |" not in log.read_text(encoding="utf-8"), "log not cleared"
        passed += 1

        # 4. concurrent SubagentStop writes keep every agent row
        def run_agent(index):
            return run_hook(
                tmp,
                {"agent_type": f"worker-{index}", "agent_transcript_path": str(fix)},
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run_agent, range(8)))
        assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
        content = log.read_text(encoding="utf-8")
        assert all(f"| worker-{index} |" in content for index in range(8)), content
        passed += 1

        # 5. garbage input: exit 0, no output
        r = subprocess.run(
            [sys.executable, str(hooks / "log_agent_usage.py")],
            input="not json", capture_output=True, text=True, cwd=tmp, timeout=30,
        )
        assert r.returncode == 0
        passed += 1

        # 7-8 (T-01M4RWC6VHHN479J2A9RRY1BE3, étape 4) — a project of their own,
        # with events.py, so agent.stop is OBSERVABLE (arms 1-6 run without it and
        # emit nothing). The same transcript (6.5k of message.usage) on every host.
        # Placed BEFORE arm 6, which reads the real repo's .gitignore: replayed on a
        # partial extraction (plan §9, step 3) the first failure is then arm 7's.
        proj = tmp / "events-project"
        (proj / ".codex" / "hooks").mkdir(parents=True)
        (proj / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(HERE / "_common.py", proj / ".codex" / "hooks" / "_common.py")
        shutil.copy2(HERE / "log_agent_usage.py", proj / ".codex" / "hooks" / "log_agent_usage.py")
        shutil.copy2(REPO / ".agents" / "bin" / "events.py", proj / ".agents" / "bin" / "events.py")
        # The `cadre` package where events.py looks first (T-01M5BXTRP8GKS7DMDQCTKK88DZ):
        # `.agents/vendor/cadre`, `src/cadre` as fallback. Only if present: without it
        # events.py still writes the line (degraded data) — a partial extraction without
        # the package replays arms 7-8 on the `kind` alone; with it, arm 8 asserts the
        # redaction leg RAN (no `redaction_unavailable`).
        paquet = next((p for p in (REPO / ".agents" / "vendor" / "cadre", REPO / "src" / "cadre")
                       if (p / "__init__.py").is_file()), None)
        if paquet is not None:
            (proj / ".agents" / "vendor" / "cadre" / "ledger").mkdir(parents=True)
            for rel in ("__init__.py", "ledger/redaction.py"):
                shutil.copy2(paquet / rel, proj / ".agents" / "vendor" / "cadre" / rel)
        proj_log = proj / ".agents" / "state" / "local" / "RUN_LOG.md"

        # 7. copilot: transcript_total is NOT called. Its transcriptPath is the
        #    PARENT's events.jsonl (M-P10), which carries no `usage` key — up to
        #    10 MB were read for 0. No actual row, no agent.stop: the couple
        #    (log_agent_usage, copilot) is SANS_ENREGISTREMENT in test_events_parity.
        ev = tmp / "ev-copilot"
        ev.mkdir()
        r = run_hook(proj, {"agentType": "dev-copilot", "transcriptPath": str(fix)},
                     host="copilot", events_dir=ev)
        assert r.returncode == 0, r.stderr
        text = proj_log.read_text(encoding="utf-8") if proj_log.exists() else ""
        assert "| dev-copilot |" not in text, f"copilot must not read the transcript: {text}"
        assert "agent.stop" not in event_kinds(ev), event_kinds(ev)
        passed += 1

        # 8. witnesses of scope: codex and kimi are unchanged — same payload, the
        #    transcript IS read (6.5k) and ONE agent.stop is emitted.
        for host in ("codex", "kimi"):
            ev = tmp / f"ev-{host}"
            ev.mkdir()
            r = run_hook(proj, {"agentType": f"dev-{host}", "transcriptPath": str(fix)},
                         host=host, events_dir=ev)
            assert r.returncode == 0, r.stderr
            assert f"| dev-{host} | - | 6.5k |" in proj_log.read_text(encoding="utf-8"), host
            assert event_kinds(ev).count("agent.stop") == 1, (host, event_kinds(ev))
            if paquet is not None:
                stop = next(rec for rec in event_records(ev) if rec["kind"] == "agent.stop")
                assert "redaction_unavailable" not in stop.get("data", {}), (host, stop)
        passed += 1

        # 6. Codex backups are git-ignored in the real repo.
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", ".codex/backups/probe.jsonl"],
            cwd=HERE.parents[1],
            check=False,
        )
        assert ignored.returncode == 0, "Codex backups must be ignored"
        passed += 1

        print(f"PASS: log_agent_usage ({passed}/{passed})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
