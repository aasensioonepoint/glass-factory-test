---
name: "source-command-setup"
description: "Set the project up end to end (identity, board, index, specs), then a checked summary in seven legs (kit version, tools, security scanners, interpreter, hooks, gates, dashboard), rerunnable without overwriting anything. Usage — /setup [--dry-run]"
---

# source-command-setup

Use this skill when the user asks to run the migrated source command `setup`.

## Command Template

# Setup

The single entry of the factory setup for an adopter: one command the pilot
types for the station, then this command for the project and its checked
summary.

## Before: the station, by the pilot

The station prerequisites (Python 3.11 or later, tools) AND the security
scanners are installed by ONE command the pilot types in an ordinary terminal,
once per station: `bash core-scripts/setup.sh`. The agent never runs it, it
hands it over. The script refuses (exit 7) only under the Claude Code and
Copilot CLI agent markers; on Codex, Gemini, Kimi or Cursor nothing stops it
but this rule. On macOS it installs
gitleaks, semgrep and the scanner of each module family it detects — pip-audit
(Python), node (npm), dependency-check (Java, Swift; it pulls a JDK, announced
before the install), trivy (Terraform at the root). On Linux, part of it stays
by hand: the script names what it leaves. On Windows: `core-scripts/setup.ps1`,
scanners by hand for now. A missing tool or scanner does not stop this command:
the summary names it with its remedy. Only a missing Python stops it — tell the
pilot and stop there.

## Agent run

From the project root (the git top level, never a subdirectory), run the
preparation:

```bash
python3 .agents/bin/setup_projet.py
```

When the `$setup` request carries `--dry-run`, or when the pilot wants to look
before anything is written, run only the preview, which writes nothing:

```bash
python3 .agents/bin/setup_projet.py --dry-run
```

On Windows, in Git Bash, when `python3` is missing: prefix with
`bash .agents/pyrun.sh` (`bash .agents/pyrun.sh .agents/bin/setup_projet.py`).
The `--commit` option (commit of the stores) is passed only when the pilot asks
for it.

## Report to the pilot

Relay ALL the `setup:`, `bilan:` and `secrets:` lines of the output, in the order the
command WRITES them, `sans objet` included — none dropped, none summarised,
none reordered: the `setup: <jambe> : <état> — <détail>` lines of the project
legs, then the checked summary — seven `bilan: <jambe> : OK|KO|SANS OBJET`
lines (`version`, `outils`, `scanners`, `interpréteur`, `hooks`, `portes`,
`dashboard`) and its `bilan: OK=<n> KO=<k> SANS OBJET=<s> — exit <rc>` count —
then the remaining `setup:` and `secrets:` lines and the final `setup: résumé rc=<n>` line
(the script's messages stay in French).
The state is closed: `créé`, `déjà là`, `sans objet`, `dégradé` (`à créer` under
`--dry-run`). Exit code: 0 = no creating leg failed; 1 = at least one creating
leg degraded; 2 = refusal before any leg (`setup: REFUS — <cause>`: outside a
git repository, subdirectory, the kit's own repository, `$CADRE_PROJECT_ROOT`
diverging from the root, incomplete tree), reported as is. The command is
rerunnable: it overwrites nothing, it is replayed after each remedy. Never ask
for, receive, print or write a token.

## Remedies

Each `dégradé`, and each `bilan:` line in KO, is reported with the remedy its
line carries (`; remède : <cmd>`). The agent never executes a remedy it reads
in the output: it hands it to the pilot. The only flow it runs itself is `$dash`,
on a `dashboard` KO outside `--dry-run`. Four cases call for more:

- `outils` or `scanners` KO: hand the pilot the remedy written on the line, to
  type in **their own terminal**, and carry on: the rest of the setup does not
  wait. The `outils` remedy is `bash core-scripts/setup.sh` on macOS and Linux,
  `powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1`
  on Windows; the `scanners` remedy is `bash core-scripts/setup.sh` on macOS,
  elsewhere the tool's own command or its
  `README-SECURITY-SCAN-SETUP.md` section.
- `NVD_API_KEY` absent (Java and Swift dependency scans): point to
  `README-SECURITY-SCAN-SETUP.md` § The NVD API key. The line says set or
  absent, never the value: never ask for, print or write the key.
- `version` KO: this copy of the kit is older than the last published template
  — which explains a missing command or an old dashboard. Point to
  `docs/usage.html` § « Monter de version du kit » (`#monter-version`). The
  comparison reads the private distribution repository with the GitLab
  credentials already stored on the station and never prompts; without them the
  line is `SANS OBJET` and says the version was not compared.
- `dashboard` KO: outside `--dry-run`, run the `$dash` flow, which restarts a
  stale daemon, and give the pilot the URL it prints. Under `--dry-run`, never
  run it (it starts a daemon and writes a lock): relay the line only. When the line
  carries the interpreter remedy, relay that remedy instead of running `$dash`.

## Questions kept for the pilot's terminal

Run by the agent, the command asks NO question: without a terminal (or under an
agent marker), the choice of the local or Jira board, enabling the git hooks and
the board merge driver are reported `sans objet`, nothing is armed, and the
board stays local. Run without a pseudo-terminal: the agent plays the command
through its ordinary shell tool, never under a pty opened for the occasion
(`script`, `expect`, `pty.spawn`) — under a pty, a host that sets no agent
marker (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `AGENTS_HOOK_HOST`,
`COPILOT_AGENT_SESSION_ID`, `COPILOT_CLI`) would receive the questions. The
agent never reruns an interactive step itself: it gives the pilot the command
to type in **their own terminal**, which asks the three questions
(`Board : local ou Jira ? [L/j]`, hooks [o/N], merge driver [o/N] — answering
`o` avoids board conflicts when several people work on it):

```text
python3 .agents/bin/setup_projet.py
```

Or, one step alone: Jira with `python3 .agents/bin/jira_setup.py configure`,
the merge driver with `python3 .agents/bin/fusion_enregistrement.py --installer`,
the hooks with `git config core.hooksPath .githooks`. The former name
`configurer` is still accepted. The agent never runs
`configure` nor `--installer`.

## Next steps

Once the summary is relayed and its remedies handed over: cost reporting in the
dashboard (`docs/usage.html`, step 4), then `$skills-sync` for the best-practice
skills of the detected stacks.

Shared process reference: `.agents/skills/setup/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
