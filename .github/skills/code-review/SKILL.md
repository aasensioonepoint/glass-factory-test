---
name: code-review
description: GitHub Copilot review skill for high-signal PR and branch review. Use when reviewing pull requests or local changes.
---

# GitHub Copilot Code Review

Review like an owner. Focus on issues that could block merge.

## Review Priorities

1. Correctness bugs and behavior regressions.
2. Security vulnerabilities and secret exposure.
3. Data loss, migration, or compatibility risks.
4. Missing tests for changed behavior.
5. Maintainability issues that directly affect the changed code.

## Output

Lead with findings. Each finding should include severity, file, line, impact, and a concrete fix direction.

If no issues are found, say that clearly and mention any checks that were not run.
