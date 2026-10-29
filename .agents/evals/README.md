# Agent evals

`test_golden_transcripts.py` is a **deterministic drift test, not a behavioral eval** — it makes zero LLM calls. It recomposes the invariants of the `orchestrator` and `planner` agents from their live definitions across the 5 hosts (Claude/Codex/Copilot/Gemini/Kimi) and checks against `fixtures/{orchestrator,planner}.golden.json`:

- fidelity to the golden invariants (the agent's contract didn't silently drift when a definition file was edited);
- multi-host parity (all 5 mirrors agree);
- "only `planner` owns the approval gate" (routing rules stay separated by role).

It also checks `plan-critic`'s live definitions across the 5 hosts against `fixtures/plan-critic.golden.json`. **What that golden pins is exactly five booleans** — `emits_forecast`, `owns_approval_gate`, `hands_to_dev`, `declares_writes_nothing`, `is_adversarial` — and nothing else. It has no keys for verdict vocabulary, the 8-iteration cap or fail-closed behavior; attributing those guarantees to the golden would hide the need to check the suite that holds them.

The verdict vocabulary, fail-closed behavior and cap's value ARE pinned, but by a different suite, **`test_plan_critic_contract.py`**, and the split is worth knowing when a check goes red:

- verdict vocabulary (`GO`/`GO_AVEC_RESERVES`/`NO_GO`) and fail-closed behavior on a malformed verdict;
- the canonical sentence, byte-identical across 9 surfaces (the 5 host defs + `AGENTS.md`, `copilot-instructions.md`, `commands/kickoff.md`, `skills/kickoff/SKILL.md`);
- **the cap's VALUE, pinned at 8** — a separate check from the byte-identity one above, and deliberately so. Byte-identity obtains its expected text by READING one host def, so a coordinated edit turning all nine surfaces to "at most 2" keeps them identical and leaves that check GREEN. Measured: that is what happened, and nothing flinched. The value therefore lives as `CAP_ITERATIONS` inside the test — a test that reads its expected value out of the file it watches is not watching anything.

Two additional fixtures, `fixtures/plan_critic_bad_plan.golden.json` and `fixtures/plan_critic_good_plan.golden.json`, are opt-in-nightly data (behavioral, LLM-driven) rather than part of this free CI path.

It runs in `ci.yml` on every push/PR via `python -m pytest` (CI pins `CADRE_GATE_JOBS: "1"`, the bare path), for free. Locally, `verify.sh` runs the same scope through `core-scripts/run-pytest-shards.sh` (parallel slices; `CADRE_GATE_JOBS=1` gives the bare command).

Live, LLM-driven behavioral evals are a separate, opt-in concern: `.github/workflows/eval-nightly.yml` (cron + `workflow_dispatch`, gated on the `ANTHROPIC_API_KEY` secret, non-blocking, currently a stub). That's the only CI path that spends tokens — don't fold live-eval logic into this file.
