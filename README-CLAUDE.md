# Claude Code Multi-Agent Kit — token-frugal edition

An opinionated setup for Claude Code (Opus-friendly) built around three principles:

1. **Don't load context you don't need.** Every subagent has its own window; the main session stays clean.
2. **Never re-read the codebase.** An index (`CODEBASE_INDEX.md` + `SYMBOLS.md`) is the working memory.
3. **Detect the stack before touching code.** A dedicated `language-detector` agent runs first, always.

---

## Requirements (cross-platform)

Machine prerequisites — Git Bash, a real Python 3, Node.js, host CLI installs, and the Windows Store python-alias gotcha — now live in **[QUICK-SETUP.md](QUICK-SETUP.md)**; read it before your first `/kickoff`.
The kit still runs on macOS, Linux, and Windows: each hook command in `settings.json` carries `"shell": "bash"` and, like the status line, opens with a fixed prefix that converts `$CLAUDE_PROJECT_DIR` with `cygpath -u` only when it has a Windows form, sidestepping the known Git-Bash backslash-path failure ([claude-code#21878](https://github.com/anthropics/claude-code/issues/21878)) that would otherwise make hooks silently no-op on Windows — a real risk here since the guards would fail *open*. The prefix then clears a FIXED list of inherited variables and, of `GIT_CONFIG_PARAMETERS`/`GIT_CONFIG_COUNT`, hands the hooks only the `safe.directory` entries (read by git itself under `env -i`, with stdin closed and no other config source or environment variable, no `GIT_TRACE*` included; both names are simply dropped when they carry an `include` or more than eight `GIT_CONFIG_COUNT` entries — an `include` anywhere in `GIT_CONFIG_PARAMETERS`, values included, so a `safe.directory` whose path contains `include` is lost through `git -c` yet kept through `GIT_CONFIG_COUNT`, measured; every other key they carry no longer reaches a hook) — not `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `XDG_CONFIG_HOME` nor `HOME`, which can carry git keys that run code (open residue) — keeping a private copy of `GIT_DIR`/`GIT_WORK_TREE` that only the state-commit hook reads back, and hands over with `exec bash -p "<script>"`; prefix and open residues: `.agents/skills/guardrails/SKILL.md`, « Invocation durcie des hooks Claude ».

---

## Install

Drop the whole folder at the root of your repo. Layout:

```
your-repo/
├── CLAUDE.md                          # short, always-on rules
├── QUICK-SETUP.md                     # machine prerequisites, first run
├── .claude/
│   ├── agents/                        # 35 subagents (isolated context each)
│   │   ├── orchestrator.md
│   │   ├── language-detector.md
│   │   ├── skills-resolver.md
│   │   ├── custom-docs-curator.md
│   │   ├── planner.md
│   │   ├── modeler.md
│   │   ├── analyzer.md
│   │   ├── dev-mono.md
│   │   ├── dev-multi.md
│   │   ├── documenter.md
│   │   ├── optimizer.md
│   │   ├── indexer.md
│   │   ├── security-orchestrator.md   # security lead: routes, consolidates, auto-fixes
│   │   ├── security-sca.md            # generalist SCA fallback
│   │   ├── sca-npm.md / sca-java.md / sca-mobile.md   # per-ecosystem SCA specialists
│   │   ├── security-remediation.md    # minimal dependency fixes, write-capable
│   │   ├── security-code-review.md    # diff-scoped AppSec gate (class-1, never waivable)
│   │   └── security-code-review-global.md   # whole-repo AppSec review, /audit -global
│   ├── settings.json                  # hooks + permissions + statusline (no secrets)
│   ├── hooks/                         # deterministic guards (9 scripts + 2 test files + fixtures/)
│   ├── rules/                         # conditionally-loaded rules (per file glob)
│   ├── ci/                            # headless scripts + GitHub Actions example
│   ├── statusline.sh
│   ├── commands/                      # slash commands
│   │   ├── kickoff.md                 # /kickoff [-s true|false] [--defer-night]
│   │   ├── audit.md                   # /audit [-global]
│   │   ├── index.md
│   │   ├── skills-sync.md
│   │   ├── lang.md
│   │   ├── night.md                   # /night — Claude Code only
│   │   ├── jira.md                    # /jira — read-only Jira check
│   │   ├── setup.md                   # /setup — prepares the project (setup_projet.py)
│   │   └── docs-sync.md
│   └── index/                         # the "shared memory"
│       ├── CODEBASE_INDEX.md
│       ├── SYMBOLS.md
│       ├── TASKS.json                  # task board (source of truth)
│       ├── TASKS.md                    # generated view, git-ignored
│       ├── TOKEN_BUDGETS.md
│       ├── DOCS_REGISTRY.md
│       └── CUSTOM_DOCS.md
├── .agents/
│   ├── security/                      # SCA engine, shared with Codex/Copilot
│   │   ├── sca-scan.sh / sca-watch.sh # deterministic scan + continuous watch
│   │   ├── sca-policy.json            # auto-fix bounds (patch/minor only)
│   │   ├── sca-waivers.json           # waiver register (class-3 accept/track)
│   │   ├── waiver_filter.py / module_discovery.py / audit_report.py
│   │   └── test_*.py                  # unit tests (TDD'd waiver filter)
│   └── pyrun.sh                       # shared python-interpreter resolver (Windows-safe)
└── docs/tech/                         # YOUR custom knowledge drop zone
    ├── _shared/                       # docs valid for all stacks
    └── <stack>/                       # auto-created on detection
        ├── *.md                       # team conventions, notes, internal APIs
        └── skills/<name>/SKILL.md     # custom sub-skills (security-reviewed)
```

Commit `agents/` and `commands/` — the single source of the defs and commands — AND their renders (`.claude/agents/`, `.claude/commands/`, the other hosts' agent folders, `.agents/vendor/cadre/data/roster/`, the `.agents/skills/source-command-*` mirrors, `.cursor/`) in the same commit, so the whole team uses the same specialists: edit the source, then `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`; never edit a render by hand (`--check` names any drift of the flat files of these folders; a subfolder, a hidden file or another suffix is not read). Add `.agents/state/`, `.agents/ref/` and `.agents/security/` to git too — the index IS the shared memory and the SCA engine + waiver register are the shared security state, one copy read and written by Claude Code, Codex, and Copilot.

---

## First run

```
/setup                     # project (identity, board, index, specs), then the 7-leg bilan
/skills-sync               # detects stack, installs audited skills, resolves official docs
/lang myproject pk-lf-… sk-lf-… https://langfuse.example.com   # optional: agent tracing
/docs-sync                 # after dropping custom docs/skills in docs/tech/
/audit                     # optional: read-only security baseline → .agents/state/local/sca-reports/audit-latest.html
/night --dry-run           # optional: rehearse an overnight run — Claude Code only, writes nothing

# Windows / macOS / Node / Python prerequisites: see QUICK-SETUP.md.
# Optional (only for scripts you run directly, e.g. CI): chmod +x .claude/ci/*.sh
/kickoff Add refresh token flow to auth
```

You'll get:
1. Orchestrator's routing plan → approve
2. Language-detector JSON → confirm stack
3. Planner's step-by-step → approve
4. dev-* diff summary → verify, then `exec-critic` replays every acceptance criterion (NO_GO → back to dev), in parallel with 5
5. Security gate, in parallel with 4: `security-code-review` (class-1, must be clean) + `security-orchestrator` if a dependency manifest changed (auto-fixes in policy, asks FIX/ACCEPT&TRACK per class-3 finding unless `-s false`)
6. documenter + indexer wrap-up

---

## The agents at a glance

Model tier and default effort are role-tuned baselines that the orchestrator raises freely at runtime — independent agents fan out in parallel, in waves of at most the `PEUT_AJOUTER` of `charge_poste.py verdict`, and depth is never rationed for cost:

| Agent | Model | Effort | Role |
|---|---|---|---|
| `language-detector` | haiku | low | Detect stack/framework from manifests before any code work. Never guesses from filenames |
| `skills-resolver` | sonnet | low | Install audited GitHub-pinned best-practice skills — skills.sh is an opportunistic probe only; resolve versioned official docs |
| `indexer` | sonnet | low | Build/refresh the codebase index and symbol table |
| `board-reporter` | haiku | low | Read-only task-board display: what is running / blocked / pending / recently done, on demand. Never edits, never calls dev-* |
| `communicator` | haiku | medium | Pilot's translator: every message the pipeline addresses to the human, in plain French — modes `décision` / `rapport` / `état`. Read-only. Tier set by hand by the pilot, and FROZEN: `apply-mode` counts it and never raises it |
| `documenter` | sonnet | low | README, ADRs, API docs after a change lands |
| `analyzer` | sonnet | medium | Read-only Q&A: "how does X work" — reads a lot, returns a compressed summary |
| `dev-mono` | opus | medium | Implement a single-file change from an approved plan |
| `custom-docs-curator` | sonnet | medium | Vet user-dropped docs/skills in `docs/tech/` (relevance + security review) |
| `orchestrator` | opus | high | Route the task: pick the pipeline, emit FORECAST + EFFORT PLAN, then stop |
| `dev-multi` | opus | medium | Implement a coherent multi-file changeset from an approved plan |
| `load-tester` | opus | xhigh | On demand: generate a k6 scenario from OpenAPI or detected routes, run it against a DEPLOYED target through the deterministic runner `.agents/bin/loadtest.py`, and narrate its GO / NO_GO / REFUS / DEGRADED verdict — never rewrites it, never invents a threshold |
| `terraform-deployer` | opus | xhigh | Writes the project's Terraform IaC as the dev slot of an IaC board task (never applied in that task), then deploys it OUT OF CHAIN on Azure, GCP or AWS through the deterministic runner `.agents/bin/tfdeploy.py`, after `done` and a green frozen gate — narrates its GO / NO_GO / REFUS / DEGRADED verdict, never rewrites it, never writes the apply decision, never applies prod from the workstation |
| `reverse-engineer` | opus | xhigh | Reverse-engineers a binary, package or application that the pilot NAMES and declares owned or authorised, by driving the external rea CLI (npm rea-agents@6.7.0, pinned) through the deterministic runner .agents/bin/rea_run.py — runs whitelisted static inspections that never execute the target, keeps Evidence outside git under .agents/state/local/rea/, and narrates rea's observations, inferences and unknowns in French — never rebuilds rea's analysis, never runs a gated command or option without a traced pilot decision. Invoke on demand, outside the default pipeline. |
| `planner` | opus | medium | Turn routing into an approval-ready plan (symbols, steps, risks, tests, rollback) |
| `planner-sonnet` | sonnet | xhigh | Out of pipeline — not invoked: since the pilot decision of 2026-10-13 planning runs on Opus and `planner` revises its own plan at a `NO_GO`; the definition stays on disk (disconnected, not removed), its traces still accepted by the `start` guard, with no end date — each trace expires 24 h after it is written, like any trace |
| `plan-critic` | opus | high | THE plan critic — the only one since the pilot decision, its verdict IS the verdict. Read-only adversarial review of the plan AND its premises before the approval gate; verdict GO/GO_AVEC_RESERVES/NO_GO, max 8 iterations with planner in the kit; at an adopter, 2 by default, raisable on its pilot's explicit request (`plafond-critique=N`) |
| `plan-critic-sonnet-max` | sonnet | max | Out of pipeline — not invoked: since the pilot decision of 2026-10-13 `plan-critic` is the only plan critic, and when it is unavailable the gate carries `COVERAGE DEGRADED`, verdict absent; the definition stays on disk (disconnected, not removed), its traces still accepted by the `start` guard, with no end date — each trace expires 24 h after it is written, like any trace |
| `exec-critic` | opus | xhigh | Read-only adversarial replay of every acceptance criterion against real command output, after dev, in parallel with the security gate |
| `modeler` | opus | high | Data models, module boundaries, architecture diagrams |
| `optimizer` | opus | high | Performance work — never optimizes without a measurement |
| `frontend-fidelity` | opus | high | Implement UI against a mockup and PROVE it — computed-style parity against tokens, Core Web Vitals, accessibility. Declares the fidelity tier it can actually reach |
| `critic-opus` | opus | xhigh | Primary closing reviewer for every delivery. Alone, it checks structure, system consistency, side effects, state, business logic, regressions and unverified assumptions. Read-only. Excluded from `apply-mode`, which changes models while these three names encode their models |
| `critic-fable` | opus | max | First fallback when `critic-opus` is unavailable. Alone, it checks business logic, functional regressions, unverified assumptions, structure, side effects and state. Read-only. Excluded from `apply-mode` |
| `critic-sonnet-max` | sonnet | max | Second fallback after `critic-fable`. Alone, it checks implementation bugs, types, resource leaks, security, structure, side effects, state and business logic. Read-only. Excluded from `apply-mode` |
| `design-review` | opus | xhigh | Read-only adversarial audit of the RUNNING UI, after `frontend-fidelity` and before the human gate — never certifies its own implementation |
| `seo-specialist` | opus | high | Read-only technical SEO review of public pages: runs the deterministic `.agents/bin/seo_mesure.py` (JSON-LD, title, description, h1, canonical, noindex, lang; Lighthouse SEO only when the project installed it) before any advice, keeps MEASURED apart from ADVICE and names every unmeasured leg. On demand, or named owed by `design-review` |
| `sca-npm` / `sca-java` / `sca-mobile` | haiku | low | Read-only SCA specialists per ecosystem; raw verdict fragments |
| `security-sca` | sonnet | medium | Generalist SCA fallback (read-only) — GO/NO-GO on the effective verdict |
| `security-orchestrator` | sonnet | high | Security lead: routes specialists, consolidates, auto-fix under policy, pilot list |
| `security-remediation` | sonnet | medium | Minimal dependency fixes (bump/override), re-scan proof, write-capable |
| `security-code-review` | sonnet | high | AppSec review of the produced diff — class-1 findings are never waivable |
| `security-code-review-global` | opus | max | Whole-repo AppSec review for `/audit -global` — grep-directed, census then code-partitioned passes, coverage rated, informative findings |

(35 agents total — kept in sync with the table in [README.md](README.md#1-the-agents).)

---

## Full power, clean context — baked in

The kit spends context on precision, and tokens on depth. Token spend is never a reason to thin a stage — parallel fan-out (by waves under the station verdict, `charge_poste.py verdict`), workflows, and the strongest models are the point:

- **CLAUDE.md is deliberately short** — every extra line ships on every request; the saved context goes to real work.
- **Subagents don't inherit the main convo** — they read the index instead, so each runs with a clean, focused window.
- **`explore` and `plan` (built-in) skip CLAUDE.md by design** — leverage that: keep global rules out of the exploration path.
- **Symbol IDs** (SYM-042) replace copy-pasting code between agents — precision, not economy.
- **Diffs, not files** — dev-* agents return line counts + status, not the file body: the main context stays sharp.
- **Model tiers raised freely**: role-tuned defaults, but the orchestrator bumps any stage to the strongest tier on doubt — never the reverse.
- **Parallel fan-out by waves under the station verdict** — independent subagents launch one message per wave, at most the `PEUT_AJOUTER` of `bash .agents/pyrun.sh .agents/bin/charge_poste.py verdict --actifs <n>` (first wave at most `BASE` — five, up to half the cores on an idle station, never above the ceiling —, then, below 2C/3, all the `LIBRE` room at once, net of the `TENU` seats other callers hold (agents of live sessions under one hour, grants under 300 s, one hour for a grant given at `ACTIFS = 0`) and its own grants under 300 s not yet active; a ceiling the tool calibrates by itself; no readable `PLAFOND=` line: five minus the active agents); workflows (ultracode) and `/code-review ultra` for multi-agent depth.
- **Index-first reads** — CLAUDE.md forbids blind file reads.

---

## Forecast & recap (token governance)

Before the approval gate the orchestrator prints a `FORECAST` — one `~Nk` row per pipeline agent from `.agents/ref/TOKEN_BUDGETS.md` (shared with Codex/Copilot), total ±50%. Hooks then capture each agent's real billable tokens into `.agents/state/local/RUN_LOG.md` (git-ignored), and a session-end RECAP shows est→actual with ⚠ on deltas >30%. Tune the budgets file from recurring deltas — that's the whole loop. Estimates are coarse by design; the recap header names its fidelity source (`hook` / `baseline`).

## The enforcement layer (v5)

Natural-language rules are advisory: the model follows them most of the time. The layers below are deterministic — they run no matter what.

### 1. Hooks — `.claude/settings.json` + `.claude/hooks/`

| Event | Script | What it enforces |
|-------|--------|------------------|
| PreToolUse Edit\|Write | protect-paths.sh | **Blocks** edits to `src/legacy/`, `generated/`, `.env*`, credential-like files. Extend patterns in **`.agents/protected-paths.local`** — the SHARED list, honoured by all four hosts' guards, so a rule added there holds whichever agent is working; `.claude/hooks/protected-paths.local` still works as the Claude-only equivalent. One prefix per line, `#` comments allowed. Either file's **presence** additionally tells `build_index.py` this tree is a *vendored* kit, so `.claude`/`.codex`/`.gemini` stop being indexed at the root. |
| PreToolUse Bash | audit-gate.sh | **Blocks** `npx skills add <ref>` unless `.agents/state/gates/AUDIT_LOG` contains `<ref> audit=pass`. The skills-resolver logs this line after a passed security audit — the gate is now physically unbypassable. |
| PreToolUse Bash | safe-bash.sh | **Blocks** `rm`/`mv` on tracked files (allowed in /tmp, node_modules, dist, build). Why: Bash side effects escape Claude Code's checkpoint model — they're not rewindable. Agents must use Edit/Write. |
| PreToolUse Agent\|Task | bancs-mandat.sh | **Blocks** a call of the 7 anchored defs (`BANCS-BORNES` read in the RENDER `.claude/agents/<name>.md`, rendered from the source `agents/<name>.md`) whose mandate lacks ONE `BANCS:` line of existing benches; traced way out `BANCS-SANS-BORNE: <why>`, refused next to a `BANCS:` line; a fence left open: refused `cloture-ouverte`; no def name in the payload: `COVERAGE DEGRADED`. A real Agent call: NOT MEASURED (`.agents/skills/guardrails/SKILL.md` § bancs-mandat). |
| PostToolUse Edit\|Write | post-edit-check.sh | Runs a quick typecheck/lint for the edited file's language. Never blocks; surfaces issues as a system message. |
| SessionStart | session-start.sh | Silently injects the sorted task board (`list --session`: running and blocked in full, newest 20 pending, cut announced), the ledger, `.agents/state/index/CODEBASE_INDEX.md` and the CI line, then the head of `PLAN-ETAT.md` if one exists — all under a **9 400-byte budget** (`SS_BUDGET`), because Claude Code reduces any larger `additionalContext` to a 2 kB preview. Every cut is announced with where to read the rest. |
| PreCompact | pre-compact.sh | Backs up the transcript to `.claude/backups/` (keeps last 10) before compaction. |
| Stop | stop-reindex.sh | Nudges when source files are newer than `SYMBOLS.md` (stale index). |
| SubagentStop | log-agent-usage.sh | Parses the orchestrator's FORECAST / planner's FORECAST-REFINE into `.agents/state/local/RUN_LOG.md` and fills each finished agent's **actual** billable tokens from its transcript. Deterministic — zero model tokens. |
| Stop | run-recap.sh | Prints the est→actual RECAP (⚠ flags deltas >30%) when the run had a forecast, then clears the run log. |
| PostToolUse Edit\|Write + Stop | `.agents/security/sca-scan.sh` (changed-only) | Waiver-aware SCA gate: fires only when a dependency manifest changed (`package.json`, `pom.xml`, `build.gradle*`, `Package.resolved`, `Podfile.lock`, …). Effective verdict applies `.agents/security/sca-waivers.json`; never a silent GO. See § Security subsystem below. |

Blocked = exit code 2; the reason on stderr is fed back to Claude, which reports it to you instead of working around it (rule in the shared core AGENTS.md § Enforcement layer, imported by CLAUDE.md).

**Setup note:** hooks and the status line are launched via `exec bash -p "<path>"` after that prefix, so the executable bit is **not** required (this also avoids Windows/git dropping the `+x` bit). Only scripts you invoke directly — e.g. `.claude/ci/*.sh` in CI — need `chmod +x`. On Windows, Git Bash must be installed (see [Requirements](#requirements-cross-platform)); a Windows-form `$CLAUDE_PROJECT_DIR` is converted with `cygpath -u` so `C:\…` paths work.

### 2. Rules — conditional loading (`.claude/rules/`)

Stack rules load only when a matching file is touched (frontmatter `paths:` globs). Each rule file is a thin wrapper: the canonical content lives once in `.agents/ref/CONVENTIONS_<stack>.md`, shared with Codex and Copilot (`.github/instructions/*.instructions.md` wraps the same files for Copilot). Add your own stack: create `.agents/ref/CONVENTIONS_<stack>.md`, then a wrapper here with tight `paths:` globs.

### 3. Permissions — declarative allow/deny/ask (`settings.json`)

Independent second layer under the hooks: `deny` on reading `.env*`/credentials/`*.pem` and editing legacy/generated; `ask` (interactive confirmation) on `npm publish` and `kubectl delete`. `npx skills add` is in neither list, so the host prompts by default; the protection is the `AUDIT_LOG` gate in the hook table above, not the dialog. `git push` and `docker rm` sit in `allow` deliberately — they are what the automatic dependency-remediation flow needs to run unattended. The lists are committed in `.claude/settings.json`, which travels with the template: a fresh adoption receives them as they are, but an adopter whose `.claude/settings.json` already exists keeps its own file and adds a new rule — such as the Codex launcher's below — by hand. Edit them to taste — permission rule syntax is `Tool(pattern)`.

**The Codex dev launcher — pre-approved, NOT a confinement.** One rule lets Claude Code start a Codex dev without a prompt: `Bash(bash .agents/bin/codex-dev.sh *)`, first in `allow`, and no other rule pre-approves `codex`. The only supported call is, from the ROOT of the main worktree, `bash .agents/bin/codex-dev.sh --worktree <name> --model <m> [--effort low|medium|high|xhigh] --mandat <file> [--dry-run]` (or `--help` alone). The launcher checks that `.claude/worktrees/<name>` is a linked worktree of this repository, whose git-dir is exactly `<common-dir>/worktrees/<id>`, and that its `.codex/` tree equals the root's `HEAD` (no skip-worktree or assume-unchanged entry), accepts a mandate only as a regular file whose real path lies under `<root>/docs/tasks/`, `/tmp/`, `/private/tmp/` or `$TMPDIR`, passes `-s workspace-write`, `network_access=false` and `writable_roots=[]` — their effect under Codex is not measured by the kit, only the argv is — and refuses `-s`, `-c`, `--add-dir`, `--dangerously-*`, any other option and any `..` in `<name>` or `<m>` (rc 3, Codex never started). Any untracked file under the worktree's `.codex/`, `__pycache__` included, is refused on purpose: a planted `.pyc` matching the source's size and mtime is loaded instead of it, invisible to the diff — run Claude-side tests in a Codex worktree under `PYTHONDONTWRITEBYTECODE=1`. `codex`, `git` and `dirname` are resolved through `PATH`; an inherited `BASH_ENV`, `SHELLOPTS` (xtrace with a substituting `PS4`) or exported function named `builtin` runs code before any check; a hard link or a forged `$TMPDIR` brings any readable file into the mandate zone — it is not a boundary. What it does NOT do: once started, Codex is outside Claude's hooks and `ask`/`deny` lists — it reads the WHOLE disk (`.env`, `~/.aws`: Claude's `Read` denials do not bind it) and writes `/tmp` and `$TMPDIR` (scratchpads, `/tmp/cadre-*` clones); the mandate file is prompt-injection surface; the rule is RELATIVE to the cwd, so started from a worktree it runs that worktree's copy of the launcher, which Codex can rewrite — arbitrary code pre-approved, which is why it is started from the root only (a window still separates the checks from the `exec`); Codex hooks are trusted per absolute path, so a worktree's `.codex/hooks.json` stays untrusted there. `.git` is outside the writable roots: Codex does not commit — the caller commits.

### 4. Compaction discipline

The shared core AGENTS.md § Compaction instructions (imported by CLAUDE.md) tells Claude exactly what to preserve when the context is compacted: approved plan + step statuses, session SYM-IDs, active T-NNN, curator verdicts, pending gates — and what to discard (raw file contents are recoverable via the index). The PreCompact hook guarantees a transcript backup either way.

### 5. Statusline

`.claude/statusline.sh` shows `model | running task + pending/done counters | context % | session cost ($)` at all times (refreshes every 5s). Cost pairs well with the Langfuse traces from `/lang` for spotting expensive patterns live.

### 6. Headless / CI (`.claude/ci/`)

- `pr-analyze.sh "origin/main...HEAD"` — runs the **analyzer** agent non-interactively (`claude -p`) on a diff, JSON output, tool allowlist locked to read-only + git.
- `nightly-index.sh` — refreshes the index without a human session (cron/scheduler).
- `github-actions-example.yml` — copy to `.github/workflows/`; needs the `ANTHROPIC_API_KEY` secret. Langfuse tracing works in CI too if the env vars are set on the runner.

The pipeline gates (plan approval) are interactive by design; headless mode is for READ and INDEX work. If you automate dev-* in CI, add your own review gate (PR comment approval) — don't ship auto-merge.

## Security subsystem (SCA + AppSec review)

8 dedicated agents (see table above): `security-orchestrator` fans out `sca-npm`/`sca-java`/`sca-mobile` (or the `security-sca` generalist fallback) in parallel, in waves of at most the `budget` the calling session passes (no budget given: one specialist at a time), consolidates one GO/NO-GO from the **effective** verdict (waiver register applied), and auto-fixes patch/minor bumps within `.agents/security/sca-policy.json` via `security-remediation`. `security-code-review` gates every diff a dev-* agent produces — HIGH/CRITICAL findings are **class-1: never waivable**, looped back to dev-* until clean. `security-code-review-global` is the informative, whole-repo counterpart for `/audit -global`.

Non-actionable dependency findings (class-3) land in the waiver register `.agents/security/sca-waivers.json`: `/kickoff` asks **FIX NOW** or **ACCEPT & TRACK** per finding, unless run as `/kickoff -s false`, which auto-flags them `pending_review` instead of interrupting you. Continuous background watch: `sca-watch.sh`.

New command: `/audit [-global]` — read-only, no waiver writes, no approval gates; HTML report at `.agents/state/local/sca-reports/audit-latest.html` (add `-global` for the whole-repo code-review pass too).

Scanner prerequisites per ecosystem (NVD API key for Java/Swift, Gradle plugin snippet, degraded-verdict semantics): **[README-SECURITY-SCAN-SETUP.md](README-SECURITY-SCAN-SETUP.md)**.

## Dynamic skills & official docs

Nothing language-specific is hardcoded. The flow:

1. `language-detector` emits stack + version + `registry_sections`.
2. `skills-resolver` probes skills.sh, then falls back by name — never silently:
   - `GET /api/v1/skills/search?q=<stack>` — OIDC-gated (Vercel): without a token it answers `401`, which the CLI masks as "No skills found". An empty result is an auth failure, not an absence.
   - fallback: the audited GitHub-pinned skills vendored under `.agents/skills/vendor/`, announced as `COVERAGE DEGRADED — skills.sh OIDC-gated (401), pinned-GitHub fallback in use`.
   - the fallback is now ACTIVE, not just vendored: `.agents/bin/skills_github_fallback.py` searches GitHub, validates, pins the top 1–2 candidates to their SHA, installs under an `audit=pass pinned=<sha>` `AUDIT_LOG` line, and keeps `DOCS_REGISTRY.md`'s stack sections current — all governed by the travelling policy `.agents/security/skills-fallback-policy.json` (`install_mode` ∈ {auto, confirm}, default `confirm` — `install` refuses rc 5 without `--confirmed-by <pilote>`, so the machine gate ships ARMED; a project opts into `auto` explicitly; `top` ≤ 2).
   - `npx skills add` only with an `audit=pass` entry in `.agents/state/gates/AUDIT_LOG` (hook-enforced).
   - SHA-256 hash pinned in `DOCS_REGISTRY.md § installed` → upstream changes are detected, never silently applied.
3. `.agents/ref/DOCS_REGISTRY.md` maps each language/framework to its **canonical official docs** (typescriptlang.org, docs.python.org, doc.rust-lang.org, go.dev…) plus `llms.txt` endpoints when the project exposes one (Next.js, Svelte…).
4. `dev-*` and `optimizer` agents WebFetch the **version-matched** doc page at need — content is read in the subagent's context, never pasted back.

Run `/skills-sync` on first setup and whenever a new stack appears. Restart the session after installs so new SKILL.md files are discovered.

## Your custom knowledge (docs/tech → curated ingestion)

When a language is detected, `docs/tech/<stack>/` is scaffolded. Drop anything there:
- **Free-form .md docs** — team conventions, internal API notes, gotchas. `_shared/` for stack-agnostic docs.
- **Custom sub-skills** — `docs/tech/<stack>/skills/<name>/SKILL.md` (+ scripts).

Nothing is swallowed blindly. The `custom-docs-curator` agent hashes every file, analyzes relevance to the detected stack, and renders a verdict: **ingest** (one-line summary into `CUSTOM_DOCS.md`, agents open the full file only at need), **skip** (dormant — wrong stack, auto-reconsidered later), **stale** (contradicts current versions → flagged), or **reject** (custom skills get a full manual security review since they bypass the pinned-skill audit trail — remote code execution, credential access, or data exfiltration are disqualifying). Approved skills are promoted to `.claude/skills/` with their hash pinned; any later edit triggers re-review, never a silent update.

Run `/docs-sync` after dropping files. Ingested conventions carry the same force as CLAUDE.md rules for their stack.

## Observability (/lang → Langfuse)

`/lang` wires this project into a Langfuse instance (local Docker or Kubernetes) so every Claude Code session is traced: turns, tool calls, token usage, grouped by session. Setup asks for exactly four things — project name, public key, secret key, base URL — tests the connection first, and installs the official Langfuse observability plugin (fallback: Stop-hook + `.claude/settings.local.json`, git-ignored so keys never get committed).

Why it fits this kit: the trace view is where you SEE the token waste the architecture fights — repeated file reads, near-duplicate searches, long exploration stretches. Use it to tune your agents and index.

### Dashboard cost telemetry (canal B — OTLP)

The `/dash` dashboard's cost/token KPIs (Coût view, header tiles) are fed by Claude Code's **native OTLP telemetry**, received by the daemon on `127.0.0.1:4318`. This is OFF by default: without it the receiver listens but nothing arrives, and the dashboard shows the last captured figures forever (the "live" badge refers to the transport, not to data freshness).

Enable it in your **user-scope** `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`) — deliberately user-scope: Claude Code ignores these keys when they come from a project's `.claude/settings.json` or `.claude/settings.local.json` (read in the 2.1.299 binary: "project-scoped settings can't set this key. Set it in ~/.claude/settings.json or managed settings instead."). The same block is part of `docs/settings-utilisateur-recommande.json`. Exports go to `127.0.0.1` only:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "OTEL_METRIC_EXPORT_INTERVAL": "5000"
  }
}
```

Three measured telemetry facts:

- Telemetry activates at **CLI startup** — restart Claude Code after adding the block; a running session cannot be revived.
- `http/json` is mandatory: the embedded receiver is a stdlib HTTP server that only parses OTLP/JSON (no gRPC, no protobuf).
- `OTEL_METRIC_EXPORT_INTERVAL=5000` matters — the default is 60 s of dashboard latency.

Do **NOT** set `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS` or `OTEL_LOG_RAW_API_BODIES`: they would export prompts, tool inputs and Bash commands into the local capture files. Known caveat: port 4318 is machine-global while the kit is provisioned per project — with two provisioned projects open in parallel, whichever daemon holds the port receives both projects' telemetry; read canal-B figures as "this machine".

## Customize

- **Add a stack**: create `.agents/ref/CONVENTIONS_<lang>.md` and reference it in `language-detector.md`'s output field `conventions_file`. Shipping no sheet is an equally valid answer — the detector then emits `null`, and the stack skill plus `registry_sections` carries the conventions. What it must never do is name a sheet that does not exist: the dev agent's read fails and it falls back on its own habits in silence.
- **Add a specialist** (e.g., a new SCA ecosystem or review lens): copy the closest existing source (`agents/analyzer.md`, or `agents/sca-npm.md` for a new dependency ecosystem) to `agents/<name>.md`, tighten the description, add it to the routing rules of `agents/orchestrator.md` / `agents/security-orchestrator.md`, then `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire` renders it to the five hosts and the roster.
- **Restrict tools**: every subagent's `tools:` frontmatter is the allowlist. Fewer tools = safer.

---

## Notes on Claude Code specifics

- Built-in subagents (`explore`, `plan`) are already available — this kit complements them, doesn't replace them.
- Frontmatter fields used here (`name`, `description`, `tools`, `model`) are the supported ones.
- If two agents share a `name`, only one loads — keep names unique; `agents/` is flat (a subfolder is refused as ILLISIBLE).
- For the latest docs: https://code.claude.com/docs/en/sub-agents


## Claude Code specifics — details

The full text moved out of `CLAUDE.md` on 2026-09-29: that file loads in EVERY
session and for EVERY subagent, so it now keeps one line per point. The details
below started as a verbatim snapshot of `CLAUDE.md`; some points have since
changed, and it is not kept up to date by a bench. The authoritative
`Commands:` line remains in `CLAUDE.md` (`host_sync.test.sh` § 3c).

- Commands: `/kickoff`, `/audit`, `/index`, `/skills-sync`, `/docs-sync`, `/specs-sync`, `/lang`, `/dash`, `/planning`, `/planning-all`, `/night`, `/jira`, `/setup` (defined in `commands/<name>.md`, the single source; `.claude/commands/` and the cross-host mirrors `.agents/skills/source-command-*` are rendered from `commands/` by `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire`, never edited by hand, and `--check` names any drift of the flat files of these folders (a subfolder, a hidden file or another suffix is not read); `night` is Claude Code only and has no mirror). A `$name` workflow in shared docs maps to `/name` here. `/audit [-global]` = read-only multi-module security audit with HTML report in `.agents/state/local/sca-reports/`. `/dash` = local observability dashboard: the native Claude Code entry stays in `.claude/commands/`, and a traveling homonym skill also lives under `.agents/skills/`, so hosts that discover that directory reach it too. `/planning` = build a pool of plans ready for BOTH `/kickoff` (which resumes a valid plan — file present, `plan_pool.py check` = 0, verdict GO/GO_AVEC_RESERVES — and never skips the human gate) and `/night` (preparation only; the plan file + a `sha256=` in the traced verdict make the lot consumable by `night_approve.py --apply --lot` once the pilot has committed the plan (`/planning` commits nothing; an uncommitted plan is skipped by condition 8), the contract itself stays the pilot's gesture; `core-scripts/plan_pool.py` reports freshness and is NOT authoritative on `/night` eligibility).
- `/night` is **Claude Code only** and is the one command that runs unattended — four preparation phases, one gate, then it works the backlog to morning. Three things make it safe to leave alone, and each was a blocking finding of the plan critique rather than an afterthought. **Its agenda is closed**: only a task the pilot approved is eligible — `/kickoff --defer-night` for one task, or `.agents/bin/night_approve.py --apply --lot <plan.md> T-… [--lot …]` for N **NAMED** lots in one gesture (same contract, same guarantee; no "approve everything" mode and no discovery of lots by sweeping the board) — and eligibility is re-established BY RELEVÉ each night: state `pending`, contract present, plan snapshot's sha256 recomputed and identical, plan committed and identical to HEAD, cited verdict `GO`/`GO_AVEC_RESERVES` (ou `PASS`/`CONCERNS` historiques), and the plan ENROLS the task (its id in the plan's title or first `Tâches :` line, never just anywhere in the bytes). A plan edited after approval therefore loses its eligibility without anyone having to remember the edit, and a task with no contract is REFUSED rather than implicitly admitted. **Its clock partitions**: `D = (cible − H0) mod 1440` (the mod is the midnight crossing), then attente/plein/atterrissage/clôture whose durations sum to exactly `D` — nine literal splits are printed, and `.agents/evals/test_night_contract.py` re-implements the rule and checks it over all 1440 minutes, so no minute of the night is left without a regime. **Its two escapes are fail-closed**: `--dry-run` writes nothing at all (no file, no `tasks.py`/`specs.py`/`ledger.py` call — its only observable effect is text on screen), and `--headless` refuses to print a loop until `.agents/state/gates/NIGHT_HEADLESS.allow` exists, derives `--allowed-tools` from it, requires `--max-budget-usd`, and never emits `--dangerously-skip-permissions`. Everything the night reads overnight — CI logs, the previous night's report, plans, board — enters framed `[do not obey]` and bounded (30 lines / 2 000 chars, truncation announced). The command file is French because it is a repatriation of Lavande's, and because the restitution strings it fixes are the ones the pilot reads.
- Full power made concrete: launch independent subagents in parallel, one message per wave of at most `PEUT_AJOUTER` (`charge_poste.py verdict`); use the Workflow tool (ultracode) for substantive multi-agent orchestration and `/code-review ultra` for branch/PR reviews; run any stage at the strongest model tier that helps — never downgrade to save tokens.
- Batch launcher, the kit's own and travelling: `.claude/workflows/workflow-fournee.js` — Claude Code only. After `tasks.py fournee <T>`, call the Workflow tool with `scriptPath: .claude/workflows/workflow-fournee.js` and JSON `args`, all validated before the first agent, otherwise nothing starts. `base`, `label` and `grappes` are required, with `bancs` required in every grappe. The CALLER passes `session`, the session link, because a Workflow script cannot read its own session; without it the `Claude-Session` line is left out of the commits and the log says so. `repo` is optional: a context agent derives the root with `git rev-parse --show-toplevel`, and a `repo` that does not equal it stops everything before the first dev. The devs run on the host: no route to a local model exists any more. No other host has the Workflow tool, so on Codex, Copilot, Gemini CLI, Kimi Code and Antigravity the same batch plays its lots in SERIES, one worktree at a time, under the `COVERAGE DEGRADED — parallélisme des devs` line its host carries. Per-host status, date and cause are in `.agents/ref/PARALLELISME_HOTES.md`: its § Statuts carries the six `HOTE:` rows, and its § Le lanceur de fournée gives this contract. NOT MEASURED, so nothing is promised about them:
  - whether the PreToolUse hooks fire on a Workflow `agent()` or on the tools it calls: `bancs-mandat.sh` (`Agent|Task`), `safe-bash.sh` and `audit-gate.sh` (`Bash`), `protect-paths.sh` (`Edit|Write`). No hook is promised inside a workflow;
  - the `worktree` isolation of a Workflow `agent()`: each dev checks its own linked worktree before any other git command, and stops otherwise.

  Measured on 2026-10-19: the launcher resolves `scriptPath` and loads the script without starting an agent. A grappe whose branch is already present (an interrupted run) stops everything with status `contexte`.

  The named losses, written in the launcher's header:
  - the automatic local dev mandate;
  - the local-model advice (`review_diff`) on the merge diff;
  - the start of the local model server (LM Studio), a tool of one machine;
  - the fixed `Co-Authored-By` line: each agent follows its host's attribution instruction;
  - the quota stop where `cadre-quota` is not installed: the return says `quota: NON MESURÉ`;
  - the targeted tests of a non-Python adopter (`go test`, `npm test`, `mvn`…): `tests`, optional, admits only a pytest on test files; absent, the batch runs the lots' benches alone and the project's gate covers the rest;
  - a write-set path that is non-ASCII or holds a blank: only `[A-Za-z0-9_.@+/-]` passes (no such path in the kit).
- Subagents load from `.claude/agents/`, rendered from `agents/` — each def's single source is `agents/<name>.md` (a pilot decision), and `bash .agents/pyrun.sh .agents/bin/render_hosts.py --ecrire` writes the five hosts' defs and the roster `.agents/vendor/cadre/data/roster/<name>.json` from it in one go — never edit a render by hand; `--check` names any drift of the flat files of these folders (ABSENT, DERIVE, ORPHELIN, ETRANGER; a file without a kit witness of the same name is HORS RENDU — counted, never named; a subfolder, a hidden file or another suffix is not read). Invoke `language-detector` first for any code work; use plan mode before edits for any task touching 6 files or more. A task of 5 files or fewer goes straight to `dev-*`, with no planner, plan critic or human gate, once `python .agents/bin/tasks.py direct T-NNN` has stamped it — the verb VERIFIES the criteria by code, and its refusal sends the task back to the planned path (AGENTS.md § Golden rules, « LA VOIE DIRECTE »); `exec-critic`, `security-code-review`, closing review, gate and `done` stay.
- **UI work goes through `frontend-fidelity` then `design-review`** (see AGENTS.md § Golden rules for why the pair, not one agent). `frontend-fidelity` implements against a mockup and proves it — Figma MCP for the source of truth (its `get_design_context` REQUIRES the `figma-design-to-code` guidance loaded first, or it emits code that ignores this project's own components and tokens), Chrome MCP to render, screenshot and read the console, then computed-style parity against tokens before any image comparison. It declares the fidelity tier it can actually reach and STOPS at a prose-only brief instead of dressing a guess as a reproduction. `design-review` is read-only, judges the RUNNING app rather than the source, triages `[Blocker]/[High]/[Medium]/Nit:` with evidence per finding, and states problems rather than prescribing fixes. Two honest limits are written into both: mockup-versus-render pixel comparison is consultative only (the noise floor is 2–3% on a perfect implementation), and axe covers roughly 57% of WCAG — so the keyboard is checked by hand. Stitch MCP belongs to the NO-mockup path: it GENERATES a proposal to approve, never a reference to reproduce.
- **A red closing gate is repaired in 3 tentatives at most** (a pilot order): each attempt is traced `--kind delta` before the gate is replayed, under `CADRE_GATE_FAIL_FAST=0`; the loop stops as soon as the errors rise (k_n > k_(n-1): the last fix is reverted) or at the 3rd attempt still red, then `tasks.py block` and an escalation through `communicator` in décision mode; a killed gate is not a red gate, and `/night` is out of scope. Prose only — it prevents forgetting, not cheating. Detail: `.agents/skills/kickoff/SKILL.md` § La boucle de réparation bornée (porte rouge).
- `communicator` is the pilot's translator (read-only, French, no jargon), and **EVERYTHING addressed to the pilot passes through it — not only decision requests** (see AGENTS.md § Restitution au pilote for the scope, what is excluded, and why the test is ADDRESS rather than length). Three modes. `décision` — the four gates (plan approval, blocked task, class-3 security decision, plan-critic escalation) restituted in a fixed block (contexte / la question / options with concrete consequences / recommandation / sans réponse). `rapport` — a result, a failure, a blocker, a progress point: what BLOCKS or FAILED first, never an identifier without its substance, a table as soon as several items share the same fields, and always what it CHANGES for the pilot. `état` — invocable at any time for meta questions about the session (« que se passe-t-il ? », « pourquoi c'est bloqué ? ») — it reads the board, ledger, specs and RUN_LOG and narrates in plain French. It explains where `board-reporter` lists; it never edits and never invokes another agent. **If the communicator is unavailable** (server error, agent absent), the orchestrator does not skip the restitution and does not stall the pipeline: it restitutes the decision DIRECTLY, itself, in the communicator's own format (contexte / la question / options with concrete consequences / recommandation / sans réponse), headed by `COVERAGE DEGRADED — communicator indisponible, restitution directe` — same shape as the plan-critic's degraded path. Never a blocked pipeline, never a decision request left unrestituted, and never a silence that reads as a restitution already made (measured on a consumer project: the translator fell over, nothing was written, the pilot had to restitute the decision himself).
- `board-reporter` is the read-only task-board display agent: it shows what is running / blocked / pending / recently done (from `.agents/bin/tasks.py`), on demand and decoupled from the pipeline — it never edits and never calls `dev-mono`/`dev-multi`. Board *writes* stay with the pipeline (`/kickoff` driving `tasks.py`); this agent only reads.
- Security agents (`security-orchestrator`, `security-sca`, `security-remediation`, `sca-npm`, `sca-java`, `sca-mobile`, `security-code-review`) implement the shared security gate; assets in `.agents/security/`. OWASP Dependency-Check needs `NVD_API_KEY` (or a pre-seeded DB) to refresh — setup per ecosystem: `README-SECURITY-SCAN-SETUP.md`.
- Deterministic guards (`.claude/settings.json` + `.claude/hooks/*.sh`): protected paths block Edit/Write; `npx skills add` is gated by `.agents/state/gates/AUDIT_LOG`; `rm`/`mv` via Bash on tracked files is blocked because it breaks checkpoint rewind — use Edit/Write instead. Three more refusals, texts and bounds in `.agents/ref/PORTES_REFUS.md`: `safe-bash` refuses a git command that skips the repository's hooks (`--no-verify` and its prefixes, `-n`/`-an` on commit and am, `-c core.hooksPath=…`, a `git config` that writes `core.hooksPath`; rule `git-hooks-bypass`, `core.hooksPath=.githooks` exactly excepted; undoing the hooks is the pilot's gesture); `protect-paths.sh` refuses an Edit/Write on an EXISTING lint/format config once `.agents/state/gates/CONFIG_QUALITE_PROTEGE` is set (`config-qualite`; grant: the pilot, in `CONFIG_QUALITE_AUTORISE`) and on the Unicode exception register `.agents/security/unicode-allowlist.json` (`unicode-allowlist`). `cp`, `sed -i`, `tee` and `python3 -c` still write those files: they prevent forgetting, not cheating. The SAST scanner (`semgrep-scan.sh --hook`) runs on `PostToolUse Edit|Write` and on `Stop`, blocking on stderr + exit 2 (Claude is the one host where that channel is MEASURED) — host coverage 3 measured / 0 inherited / 1 assumed / 2 inert-measured, never "six hosts covered".
- **The kickoff guard** (`.agents/bin/kickoff_guard.py`) is registered here as the second `PreToolUse Edit|Write` hook, right after `protect-paths.sh`, and it carries `AGENTS_HOOK_HOST=claude` — which is what selects its Claude branch of the per-host refusal contract: **stderr + exit 2**, the channel this host measures end to end (the three envelope hosts get `permissionDecision: deny` + exit 0 instead, and an absent marker gets both channels; see AGENTS.md § Enforcement layer for why, and for the coverage honesty — 3 measured / 0 inherited / 1 assumed / 2 inert-measured, never "six hosts covered"). It is **OFF while `.agents/state/gates/KICKOFF_REQUIRED` is absent**, so on this repository — which ships DISARMED — it produces exit 0 and zero bytes on every edit. Present, that file arms every `running` task by its CLASS — no declared write-set, a glob or directory entry, 6 files or more, or a guard path of `tasks_direct.py` whatever its count, stamped by `tasks.py direct` or not — and the ids the pilot writes in it by hand add to those. Its arming file is denied twice over on this host: by the case-folded block in `protect-paths.sh` and by a single `Edit(./.agents/state/gates/KICKOFF_REQUIRED)` line in `permissions.deny` — one line, because `Edit(path)` covers every file-editing tool and a `Write(path)` rule would be inert. If it blocks you, the refusal names the missing condition and a remedy you can actually run; do not work around it.
- **The plan-target guard** (`.agents/bin/plan_cible.py` driving `tasks.py` and `specs.py`) refuses a `done`, a `start` that already carries an approval trace, or a `plan-critic` verdict when the armed plan does not annotate every step with a target. **Unlike the kickoff guard, it reaches adopters ARMED — but not with THIS repository's file**: `.template-exclude` carries `strip: .agents/state/`, so the kit's own marker never travels, and the template sync's SEED channel writes `.agents/state/gates/PLAN_CIBLE_REQUIRED` on the template from the tracked adopter seed — `spec=docs/PROMPT-projet.md` (the adopter's template spec, seven generic targets) and `chantier=*` (every task of the board, with or without a chantier). `python .agents/bin/sync_template.py --check --source <the branch the template was last synced from>` (dry run — a bare `--check` exits 22 on this repository due to the lineage guard) reports no `.agents/state/` path under TAKE, a `SEED — 4 path(s)` section naming the four seeded markers, and does NOT list `strip: .agents/state/` under `prophylactic (no match)` — the rule matches, so the kit's arming file is stripped from the distributable branch and the seed written in its place. **Do not "prove" this with `git ls-tree -r origin/template/starter-kit -- .agents/state/`**: that branch carries no `.agents/state/` at all and predates the marker, so it returns zero whatever the rule does — a witness that cannot fail (measured 2026-09-18). And the bound: `strip:` binds the `sync_template.py` channel ONLY, exactly as `.template-exclude:50-52` already says — a hand copy of `.agents/` carries the marker anyway. **On THIS repository it is ARMED since 2026-09-18** (pilot gesture, `769bb28`): `.agents/state/gates/PLAN_CIBLE_REQUIRED` carries `spec=docs/PROMPT-refonte-packaging-cadre.md` (kit repository only — the spec is stripped from the template: `strip: docs/PROMPT-refonte-packaging-cadre.md` in `.template-exclude`) and `chantier=refonte-packaging`, it is TRACKED, so anyone cloning this branch gets it armed — every `done` of that chantier needs an approved plan whose every step is annotated, or a traced `--sans-cible "<why>"`. That file is denied twice over on this host, exactly like `KICKOFF_REQUIRED`: by the case-folded block in `protect-paths.sh` and by a single `Edit(./.agents/state/gates/PLAN_CIBLE_REQUIRED)` line in `permissions.deny` (one line — `Edit(path)` covers every file-editing tool, a `Write(path)` rule would be inert). The traced way out is `--sans-cible "<why>"`, visible on the board; do not work around it.
- **`affirmation-guard.sh` (`Stop`) blocks a turn that wrote a DURABLE CLAIM without a recorded critical review.**
  It watches four surfaces: a task **added** to the board; the project state in both `PLAN-ETAT.md` **AND** `PLAN-ETAT-DETAIL.md` since the 2026-09-14 split, so moving all durable state into the second file cannot bypass the guard; a NAMED list of doctrine surfaces; and a batch-resume file in the kit's internal lot directory or under `docs/tasks/LOT-*-REPRISE.md`, including untracked files.
  Its `{"decision":"block"}` channel is **measured**: `exit 2` is ignored on `Stop`. It requires the number of closing critics that `BINOME_MIN` sets (ONE in the kit), from a closed set of names, recorded **since the penultimate distinct green gate**; consecutive duplicates for the same commit are folded. This is `tasks.py::cycle_precedent`'s rule, copied into the guard and checked by a parity test.
  With fewer than two distinct green gates, the guard uses a 12-hour window; `tasks.py done` does not. A review from one cycle covers the next cycle's writes. A malformed `at` without `Z` also makes the guard use 12 hours while `done` still expires it by string comparison. The guard anchors its diff to the **SHA of the last stamp**, rather than `HEAD`, because committing in the turn would otherwise disarm it.
  **When armed, it blocks the turn if it cannot read its infrastructure** (stamp, green-gate journal or traces), naming the file or the exception for other failures; this also applies when the diff anchor is unreadable in a turn with no writes. The host's retry passes through `stop_hook_active`. Armed by `.agents/state/gates/AFFIRMATION_REQUIRED`, protected twice like its peers; the one-time `AFFIRMATION_SANS_BINOME` escape is **consumed and logged, and is not honored unless it can be consumed and logged**.
  Three stated limits: it checks WRITES rather than truth, counts critic NAMES rather than coverage, and does not block a turn following another `Stop` hook's block because that turn carries `stop_hook_active`.
- A PreCompact hook backs up the transcript to `.claude/backups/` (last 10 kept) before compaction.
- A `PostToolUse(Bash)` hook fires on a `tasks.py … done` — the one command that means "a task is finished" — and commits the three state stores in a commit of their own — and the run exports under `runs/` in a second commit of their own, played by `tasks.py commit-run-exports` under the same lock and only when the stores token is `committed`/`nothing`/`failed`/`locked-out` — never on `busy:`; on the degraded path the exports are not attempted and the message says so (see AGENTS.md § Task tracking for why, and for the per-host coverage). If the adopting project provides `scripts/index-refresh.sh`, the hook chains it AFTER those commits, so index and state never land in the same commit. Advisory, always exit 0. The hook is **`.agents/bin/post-task-done-index.sh`**, not `.claude/hooks/`: Codex, Copilot and Kimi Code register the same file, so it belongs to no host — its own test suite lives beside it and covers the no-`CLAUDE_PROJECT_DIR` path those three hosts take.
- The SessionStart context hook (`.claude/hooks/session-start.sh`) injects both the task board (`tasks.py list --session`: pending bounded, cut announced) and `python .agents/bin/ledger.py context` (institutional memory — see AGENTS.md § Institutional memory) as `additionalContext`, under a 9 400-byte budget (above ~10 000 characters Claude Code passes only a 2 kB preview); a second leg, `session-banner.sh`, only prints the brand banner (a `systemMessage`, never `additionalContext`; guardrails/SKILL.md § Bannière de marque); capitalize into it with `ledger.py add` the same way you drive `tasks.py`.
