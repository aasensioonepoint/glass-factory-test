---
name: "source-command-dash"
description: "Open the observability dashboard (starts the daemon if absent). Usage — /dash"
---

# source-command-dash

Use this skill when the user asks to run the migrated source command `dash`.

## Command Template

1. Run `python .agents/bin/dashboard_daemon.py --dash --root "$CLAUDE_PROJECT_DIR"`.
   - It is idempotent: if a live daemon already holds
     `.agents/state/local/dashboard.lock` (pid alive AND tokenised ping),
     nothing new is spawned; otherwise a detached daemon is launched and the
     command waits (bounded, ~5s) for its lock to appear.
   - On success it prints exactly one line: the tokenised URL
     (`http://127.0.0.1:<port>/?token=…`).
2. Show the user that URL as a clickable link. Do NOT open a browser yourself
   and do NOT paste the token anywhere else — the token is the only auth on
   the API and rotates at every daemon launch.
3. If the command exits 2 (`dashboard unavailable`), report it and suggest a
   manual foreground run to see the degradation reason:
   `python .agents/bin/dashboard_daemon.py --daemon --root "$CLAUDE_PROJECT_DIR"`
   (typical causes: UI bind failure; OTLP 4318 held by another process shows
   as `otel: degraded` in `--status` but never blocks the UI).
4. Useful companions: `--status` (lock state as JSON, token elided),
   `--stop` (terminate a live daemon). The daemon auto-stops after 4h idle.
   `--stop` sends SIGTERM, then releases the lock only once the pid is gone: a
   pid still alive after 5 s is answered `still-running`, exit 2, and its lock
   is KEPT (the daemon is not declared stopped while its process lives) —
   except a daemon whose ping has gone silent: `--stop` then answers
   `not-running` without signalling it, and `--ensure`/`--dash` may take over
   its lock — read `ps -p <pid> -o command=`; code fix: T-00001120.
   `--status` also carries `demons_du_poste` (the daemon runs `ps` shows on
   this machine, AT LEAST those, never a complete census; Python launches
   only; `null` when `ps` cannot be read, e.g. Windows) and
   `demons_du_poste_etalon` (`pid`, `vu`) checked on the one daemon that
   answered the ping: `vu: false` means a launch form is missed, or that
   daemon died between the ping and `ps` (recount by hand first).
5. Stale-code safety (T-00000040): a running daemon holds its route table in
   memory, so after a kit upgrade it 404s new front-end modules and the page
   renders blank while pid+ping still report "alive". The lock therefore
   records a fingerprint of the code the process serves: `--status` reports
   `code: current | stale | unknown` (plus an `action` line when stale), and
   `--dash` restarts a stale daemon by itself instead of handing back a URL
   that would render blank. `unknown` means the lock predates this field — an
   upgrade in flight, never a reason to restart.

Shared process reference: `.agents/skills/dash/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
