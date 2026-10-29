---
description: Read-only multi-module security audit with an HTML report. Usage — /audit [-global]
---

Arguments: $ARGUMENTS

Argument parsing: `-global` enables the -global parts of steps 3, 5 and 6 below
(step 3 always clears the review files); ignore any other text (an audit takes no task description).

Execute this READ-ONLY audit pipeline — no fixes, no waiver-register writes,
no approval gates, no pilot questions:

1. If `.agents/state/index/CODEBASE_INDEX.md` is missing, invoke the
   **language-detector** subagent first and keep its JSON (its `modules` array
   primes the next step). If the index exists, skip this step.
2. Invoke the **security-orchestrator** subagent with: "audit mode: run its
   audit-mode command (the run's end read from the last-audit-scan log, rc +
   whole last line), consolidate the per-module effective verdicts, do NOT
   remediate, and end with the AUDIT-QUALIFIERS / AUDIT-GAPS tail block."
3. EVERY run first clears the review files of a previous **security-code-review-global** run:
   `python .agents/security/audit_report.py --reports-dir .agents/state/local/sca-reports --clear`
   (`py` if `python` is unavailable; never `rm`: safe-bash refuses it there). It deletes
   `code-review.json`, `code-review.pass-*.json`, `code-review.lots.json` and `audit-latest.html`,
   so no leftover is merged or shown as this run's; exit 1 names a file it could not remove — say
   so in step 6. Then, only if `-global` was passed, run that subagent (read-only; it may run in
   parallel with step 2 — total concurrency stays ≤ min(3, PEUT_AJOUTER de `charge_poste.py verdict`))
   through the « -global passes » section at
   the end of this file.
4. Write the orchestrator's tail block to `.agents/state/local/sca-reports/audit-qualifiers.json`
   as `{"qualifiers": [...], "gaps": [...]}` (drop `- none` entries; empty
   arrays are fine).
5. Generate the report, from the repo root:
   `python .agents/security/audit_report.py --reports-dir .agents/state/local/sca-reports --project "<repo folder name>"`
   — add `--global` when `-global` was passed (use `py` if `python` is unavailable; NEVER bare `python3`).
6. Print the console summary: global verdict — if the orchestrator said « no verdict obtained »,
   print that, never summary.json's global_verdict —, one line per module
   (slug — verdict — active/waived counters, sub-module count when collapsed),
   waived totals and overdue reviews, then the report paths
   (`.agents/state/local/sca-reports/audit-latest.html` + the timestamped file), then VERBATIM
   whichever of these step 5 printed after the report path: `coverage: …`, `INCOMPLETE — …`,
   `global review: absent (run failed)`, `… pass files present, not merged (no --global)`.
   Point to /kickoff for remediation. Ask nothing.

Do NOT modify any file outside `.agents/state/local/sca-reports/`. Do NOT write to
`.agents/security/sca-waivers.json`. Do NOT invoke security-remediation.

## -global passes

Run from the repo root: audit_report.py judges every path against the current directory.
Each pass returns one fenced JSON block, written VERBATIM the moment it returns — the block
between the ```json fences, never the fences themselves; never rewritten, never merged by
hand; `k` is your pass counter.

1. Census (k = 1): invoke **security-code-review-global** for pass 1 alone (no `resume`), write
   its block to `.agents/state/local/sca-reports/code-review.pass-1.json`, then run
   `python .agents/security/audit_report.py --reports-dir .agents/state/local/sca-reports --lots`.
   It writes `code-review.lots.json` and prints `{"lots": [[path, …], …], "census_missing": […],
   "census_rejected": […]}`; on stderr, `lots: N · passes: N+1 … · estimate ≈ …k tokens`: print
   that line to the console before pass 2 — an announcement, never a question. Exit 2 (no
   readable census) → run no lot pass; go straight to step 4 below (the report says INCOMPLETE).
2. One pass per lot, in order: lot i (1-based) of `lots` is pass k = i + 1. Invoke the
   subagent with `resume: {pass: k, lot: [exactly that lot's paths]}` — BOTH keys: without
   them the def runs a census again — and write its block to `code-review.pass-<k>.json`. A block that does not parse as JSON → write it anyway, then
   run no further pass and go to step 4 below (step 5 reports it as invalid-pass, INCOMPLETE).
3. PROBE: the FIRST lot of more than one file that is PLAYED is the probe. If it returns
   `stopped: budget`, run no further pass ("lot too large for the window") and go to step 4
   below: INCOMPLETE. After the probe, a lot
   that returns `budget` is a LOCAL gap, never a stop: go on, the report marks it INCOMPLETE.
   A single-file lot (one file over 350 KB, read by offset/limit) that returns `budget` never
   stops the run either.
4. Then — ALWAYS, after an early stop above too — steps 4 to 6, with `--global`: step 5 rewrites
   `audit-latest.html`, so no earlier run's report is left as the latest. The coverage the report
   prints is what the agent DECLARED (census and reads), its consistency — never a measured
   coverage of the repo.

Shared process reference: `.agents/skills/audit/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
