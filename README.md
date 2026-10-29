# Glass Factory — your project's AI dev team

The Glass Factory turns your coding assistant (Claude Code, Codex or GitHub Copilot) into a governed team of 35 specialized agents that live in your repository. You describe what you want; the factory plans it, waits for your approval, writes the code, has it reviewed and security-checked, and verifies it before you push. Tasks, decisions and checks are kept in your repository, next to your code.

## What the factory does

- **Plans before it codes.** A planner writes a plan, a critic attacks it, and you approve it before any edit. Small, low-risk tasks (five files or fewer, admitted by a board check) can take a shorter, direct path.
- **Builds with specialists.** Developer agents implement the plan; frontend work is checked against its mockup.
- **Reviews everything.** An execution critic replays the plan's acceptance criteria, a security reviewer checks the diff, and a closing critic reviews the result before a task is marked done.
- **Verifies before a push.** `core-scripts/verify.sh` runs your project's checks (put your own build and tests in `scripts/verify-projet.sh`); once the Git hooks are enabled, the push hook refuses a push without a green verification.
- **Remembers.** A task board, a codebase index and a lessons ledger live under `.agents/state/`, shared by every assistant and every teammate.
- **Guards the repository.** On Claude Code (and on Codex once you trust them), hooks refuse protected-path edits, dangerous shell commands, leaked secrets and attempts to skip the Git hooks.

You stay in charge: approving a plan, answering a decision, and pushing are always your call.

## Set up

1. **Copy the kit into your repository.** Copy every top-level entry of this branch except `TEMPLATE.md` into the root of your repository and commit it. [QUICK-SETUP.md § 3](QUICK-SETUP.md) explains what to merge if your repository already has a `CLAUDE.md` or `.claude/settings.json`.

2. **Equip your machine (once per machine).** In an ordinary terminal, not from your assistant:

   ```bash
   bash core-scripts/setup.sh
   bash core-scripts/doctor.sh
   ```

   `setup.sh` installs the prerequisites, gitleaks, semgrep and the audit tool of each module family it detects in your project (it announces the JDK before installing dependency-check). On Linux, gitleaks, trivy and dependency-check stay manual. On Windows, run `powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1`, then use Git Bash for every other command; it covers the prerequisites only, and the scanners stay manual. The script names what is missing and the command to install it; rerunning it reinstalls nothing.

3. **Prepare the project (once per clone).** Open your assistant at the root of the repository and type:

   | Claude Code | Codex / Copilot |
   |---|---|
   | `/setup` | `$setup` |

   Or run the same preparation yourself in a terminal:

   ```bash
   python3 .agents/bin/setup_projet.py
   ```

   It sets up the project identity, the task board, the codebase index and the specs, and prints a summary with one line per step. It then checks the setup in seven legs: kit version (your copy against the last published one, read with the Git credentials already stored on your machine, never a prompt), tools, security scanners, interpreter, hooks, gates and dashboard. A failing line carries its remedy. It is safe to rerun: nothing is overwritten. Add `--dry-run` to see what it would do without writing anything. On Windows, if `python3` is missing, use `bash .agents/pyrun.sh .agents/bin/setup_projet.py`. Some questions (the board merge driver, local or Jira board, Git hooks) are asked only in a real terminal, so run the command yourself when the assistant tells you to.

   On Codex, run `/hooks` once in an interactive session and trust the kit hooks (again after each kit update): until then they do not run, and the factory plans but blocks when a task starts.

4. **Start working.** Install the best practices for your stack with `/skills-sync` (`$skills-sync`), then describe your first task with `/kickoff <task>` (`$kickoff <task>`).

## The tutorial: `docs/usage.html`

[`docs/usage.html`](docs/usage.html) is a single-page interactive guide (in French) to open in any browser:

```bash
open docs/usage.html
```

Linux: `xdg-open docs/usage.html` · Windows: `start docs\usage.html`. On GitHub or GitLab, download the file and open it locally: the forge shows its source, not the page.

It has four tabs: **1 · Installer** (the setup above, step by step, for your assistant and your OS), **2 · Travailler** (how to describe a task and what stays your call), **3 · Dashboard** (following the factory without reading the terminal) and **4 · Avancé** (every command and its options, the guards, security, team work).

## Your commands

`/name` on Claude Code, `$name` on Codex and Copilot.

| Command | What it does |
|---|---|
| `/setup [--dry-run]` | Prepares the project (identity, board, index, specs), then checks kit version, tools, scanners, interpreter, hooks, gates and dashboard. Once per clone, safe to rerun. |
| `/kickoff <task>` | Runs the full pipeline on a task: plan, your approval, development, reviews, verification. |
| `/planning [N\|all]` | Prepares reviewed plans for upcoming tasks without touching the code. |
| `/planning-all [T-… \| --workstream X]` | Plans an ordered batch of tasks, wave by wave, and gives you one line to approve it. |
| `/night` | Claude Code only: works through the tasks you approved overnight. |
| `/index` | Builds or refreshes the codebase index the agents read. |
| `/skills-sync` | Detects your stack and installs audited best-practice skills for it. |
| `/docs-sync` | Curates the documents you drop in `docs/tech/` into the agents' knowledge. |
| `/specs-sync` | Versions your Markdown specifications (`docs/specs/`, `specs/`). |
| `/audit [-global]` | Read-only security audit with an HTML report. |
| `/dash` | Opens the observability dashboard (board, costs, activity). |
| `/jira` | Checks your Jira connection, read-only. |
| `/lang` | Sets up tracing: Langfuse on Claude Code; other hosts get pointers to their own tracing. |

Not sure what to run next? `python3 .agents/bin/aiguillage.py` reads the board and suggests the next command. The task board itself: `python3 .agents/bin/tasks.py list`.

## Going further

- Machine prerequisites and first run in depth: [QUICK-SETUP.md](QUICK-SETUP.md)
- Per assistant: [Claude Code](README-CLAUDE.md) · [Codex, Copilot, Gemini, Kimi Code](README-OTHER-HOSTS.md)
- Security scanners: [README-SECURITY-SCAN-SETUP.md](README-SECURITY-SCAN-SETUP.md)
- What changed in this version: [CHANGELOG.md](CHANGELOG.md)
- The rules every agent follows: [AGENTS.md](AGENTS.md)
- Your own agents and commands: write them in `agents/` and `commands/`, then run `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`; a file of yours with no kit witness of the same name is left untouched (details: [Claude Code](README-CLAUDE.md))
