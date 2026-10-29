---
name: agentic-code-review
description: Review code changes for bugs, regressions, security risks, and missing tests. Use when asked for review, PR review, or pre-merge checks.
---

# Agentic Code Review

Take a code-review stance. Findings come first.

## Process

1. Inspect the diff and impacted symbols.
2. Prioritize correctness, security, data loss, regressions, and missing tests.
3. Reference exact files and lines when possible.
4. Keep summaries short and secondary.
5. If there are no findings, say so and mention residual risk or test gaps.

## Output

```text
Findings:
- [P1][high] file:line - issue and impact - repro: <command => observed output | input scenario>
- [P2][medium] file:line - issue and impact - repro: <...>

To verify (not counted):
- file:line - suspicion, and what would reproduce it

Open questions:
- ...

Summary:
- ...
```

## Rules

- Do not rewrite the code during review unless the user explicitly asks for fixes.
- Do not report style preferences as defects.
- Include the smallest reproduction or reasoning needed to justify each finding.

## Proof, confidence, counter-check

- **A blocking finding is receivable only with its reproduction**: a command and its observed output (`<command> => <output>`), or `file:line` plus a concrete input scenario that produces the defect. Without one it goes under `To verify` — listed, never counted as a P1, never routed to a fix as blocking.
- **Every finding carries a confidence**: `high` (reproduced), `medium` (precise scenario, not replayed), `low` (suspicion). Only `high` goes to a fix as is.
- **Zero findings is a valid review.** Never invent a finding to justify the review; name the residual risk instead (Process, point 5).
- **In this kit's pipeline** the two post-dev judges hold this rule under their own words — `security-code-review` (HIGH/CRITICAL) and `exec-critic` (`BLOQUANT`), confidence `haute` / `moyenne` / `basse`, unreceivable findings under `À VÉRIFIER` — and, before the fix pass, each of their gating findings is counter-checked by the OTHER judge in refutation mode (`CONFIRMÉ` / `RÉFUTÉ` / `NON TRANCHÉ`): `.agents/skills/kickoff/SKILL.md`, § THE ADVERSARIAL COUNTER-CHECK. Prose, held by no code: it prevents forgetting, not cheating.
