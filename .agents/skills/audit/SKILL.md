---
name: audit
description: Read-only multi-module security audit with an HTML report. Usage — $audit [-global]
---

# Audit Workflow

Read-only: no dependency fix, no waiver-register write, no approval gate.

1. If `.agents/state/index/CODEBASE_INDEX.md` is missing, invoke the
   language-detector agent first and keep its JSON (`modules` array).
2. Invoke the security-orchestrator agent in "audit mode": it runs its
   audit-mode command (the run's end read from the last-audit-scan log, rc +
   whole last line), consolidates the per-module effective verdicts (waivers
   applied), never remediates, and ends with an AUDIT-QUALIFIERS / AUDIT-GAPS tail block.
3. Every run first clears a previous security-code-review-global run: `python .agents/security/audit_report.py
   --reports-dir .agents/state/local/sca-reports --clear` (never `rm`: safe-bash refuses it there; it deletes the
   code-review*.json files and audit-latest.html, exit 1 names a file left); then, only with `-global`, run « -global passes » below.
4. Write the tail block to `.agents/state/local/sca-reports/audit-qualifiers.json` as
   `{"qualifiers": [...], "gaps": [...]}`.
5. Generate the report from the repo root: `python .agents/security/audit_report.py
   --reports-dir .agents/state/local/sca-reports --project "<repo folder name>"` (+ `--global`
   with `-global`; fallback `py`; never bare `python3`).
6. Print: global verdict (if the orchestrator said « no verdict obtained », print that, never summary.json's
   global_verdict), one line per module (verdict, active/waived counters, sub-module count when collapsed), report path
   (`.agents/state/local/sca-reports/audit-latest.html`), then verbatim the coverage / INCOMPLETE / absent / not merged lines of step 5. Remediation: $kickoff.

Never modify files outside `.agents/state/local/sca-reports/`. Never write
`.agents/security/sca-waivers.json`. Never invoke security-remediation.
Scanner prerequisites (NVD key, wrappers, gradle plugin):
`README-SECURITY-SCAN-SETUP.md`.

Claude Code counterpart: `.claude/commands/audit.md` — keep the two in sync.

## -global passes

Run from the repo root: audit_report.py judges every path against the current directory.
Each pass returns one fenced JSON block, written VERBATIM the moment it returns — the block
between the ```json fences, never the fences themselves; never rewritten, never merged by
hand; `k` is your pass counter.

1. Census (k = 1): invoke security-code-review-global for pass 1 alone (no `resume`), write
   its block to `.agents/state/local/sca-reports/code-review.pass-1.json`, then run
   `python .agents/security/audit_report.py --reports-dir .agents/state/local/sca-reports --lots`.
   It writes `code-review.lots.json` and prints `{"lots": [[path, …], …], "census_missing": […],
   "census_rejected": […]}`; on stderr, `lots: N · passes: N+1 … · estimate ≈ …k tokens`: print
   that line to the console before pass 2 — an announcement, never a question. Exit 2 (no
   readable census) → run no lot pass; go straight to step 4 below (the report says INCOMPLETE).
2. One pass per lot, in order: lot i (1-based) of `lots` is pass k = i + 1. Invoke the
   agent with `resume: {pass: k, lot: [exactly that lot's paths]}` — BOTH keys: without
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
