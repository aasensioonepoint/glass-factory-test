---
name: dash
description: Open the observability dashboard (starts the daemon if absent). Usage — $dash
---

# Dashboard Workflow

Open the project's tokenised observability dashboard URL.

1. Resolve the repository root from `CLAUDE_PROJECT_DIR` when available,
   otherwise from `git rev-parse --show-toplevel`.
2. Run `python .agents/bin/dashboard_daemon.py --dash --root <project-root>`.
   It reuses a live daemon holding `.agents/state/local/dashboard.lock`, or
   starts one detached and waits, bounded, for its lock.
3. On success, show the user the single tokenised URL as a clickable link. Do
   not open a browser or paste the token elsewhere: it is the only dashboard
   authentication and rotates at every daemon launch.
4. If it exits 2 (`dashboard unavailable`), report that result and suggest
   `python .agents/bin/dashboard_daemon.py --daemon --root <project-root>` for
   the foreground diagnostic.
5. `--status` reports lock state with the token elided; `--stop` terminates a
   live daemon. The daemon auto-stops after four hours idle.
   `--stop` sends SIGTERM, then releases the lock only once the pid is gone. A
   pid still alive after 5 s (a choice, not a measurement) is answered
   `still-running`, exit 2, and its lock is KEPT: the daemon is not declared
   stopped while its process lives — except a daemon whose ping has gone
   silent: `--stop` then answers `not-running` without signalling it, and
   `--ensure`/`--dash` may take over its lock — read `ps -p <pid> -o command=`;
   code fix: T-00001120. `--status` also carries
   `demons_du_poste`, the daemon runs `ps` shows on this machine, any project:
   AT LEAST those, never a complete census (Python launches only; `null` when
   `ps` cannot be read, e.g. Windows), and `demons_du_poste_etalon` (`pid`,
   `vu`), a check on the one daemon that answered the ping. `vu: false` means
   the count misses at least one launch form, or that daemon died between the
   ping and `ps`: recount by hand first. `vu: true` says only that this daemon
   is seen.

`--dash` restarts a daemon serving stale code, identified by the fingerprint in
its lock, instead of returning a URL that would render a blank dashboard.
