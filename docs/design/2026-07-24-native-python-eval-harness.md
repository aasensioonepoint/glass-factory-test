# Native Python drift-eval harness over promptfoo/Node — design

Date: 2026-07-24
Status: implemented (`.agents/evals/test_golden_transcripts.py`)

## Problem

Agent definitions are mirrored across four hosts (Claude/Codex/Copilot/Gemini). Nothing caught a definition edit silently drifting from its intended invariants (e.g. the approval gate leaking from `planner` into `orchestrator`), or the four host mirrors falling out of parity. A real eval tool (promptfoo) was considered, but it pulls in a Node toolchain and its own dependency tree purely for a drift check that needs no LLM call.

## Decision

Write the drift check as a plain Python `pytest` module (Option B) instead of adopting promptfoo/Node: `test_golden_transcripts.py` recomposes each agent's invariants from the live definition files and diffs them against small golden fixtures (`fixtures/*.golden.json`). It runs in the same `python -m pytest` invocation as the rest of the suite, in `ci.yml`, on every push/PR.

## Consequences

- Positive: no new runtime/ecosystem (no Node, no extra SCA surface, no dependency manifest at all — stdlib only); one test command for the whole repo; the check is free (no LLM calls) so it can run on every push.
- Negative: it only catches *definition drift* against a hand-maintained golden, not actual behavioral regressions in what an LLM does with the prompt.
- Neutral: real behavioral coverage is deferred to the separate opt-in `eval-nightly.yml` workflow, which does call a live model and is explicitly non-blocking/stub for now.

## Alternatives considered

- **promptfoo**: richer eval features, but a whole Node toolchain + dependency surface for a check that doesn't need to call a model.
- **No automated check**: rejected — definition drift across 4 host mirrors had already gone unnoticed once.
