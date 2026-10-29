# Token budgets — tune from run recaps

<!-- Shared by Claude Code, Codex, and GitHub Copilot (one copy, decision 2026-07-08).
     The orchestrator reads this to compute its FORECAST block.
     When a recap shows an agent consistently off by >30%, edit the row here. -->

## Base cost per agent (typical run, tokens)
| agent             | tier   | base | scaling                    |
|-------------------|--------|------|----------------------------|
| language-detector | haiku  | 2k   | flat                       |
| board-reporter    | haiku  | 1k   | flat                       |
| communicator      | haiku  | 3k   | +1k per gate restituted    |
| planner           | opus    | 8k   | +1k per impacted symbol    |
| planner-sonnet    | sonnet | 8k   | HORS CHAÎNE (S-01M4TZZ13Y) — not invoked since the pilot decision of 2026-10-13: planning runs on Opus and `planner` revises its own plan at a NO_GO, so this def costs 0; it stays on disk, debranched, not removed |
| plan-critic       | opus    | 5k   | +1k per plan step reviewed |
| plan-critic-sonnet-max | sonnet | 5k | HORS CHAÎNE (S-01M4TZZ13Y) — not invoked since the pilot decision of 2026-10-13: `plan-critic` unavailable means COVERAGE DEGRADED, verdict absent, so this def costs 0; it stays on disk, debranched, not removed |
| exec-critic       | opus   | 6k   | +1k per acceptance criterion replayed |
| analyzer          | sonnet | 6k   | +2k per module swept       |
| dev-mono          | opus   | 5k   | +2k per 100 changed lines  |
| dev-multi         | opus   | 4k   | +3k per file               |
| load-tester       | opus   | 6k   | +2k per scenario generated |
| terraform-deployer | opus | 6k | +2k per plan/apply cycle |
| reverse-engineer | opus | 6k | +2k per rea command narrated |
| documenter        | sonnet | 4k   | flat                       |
| indexer           | sonnet | 6k   | +1k per new module         |
| orchestrator      | opus   | 3k   | flat                       |
| modeler           | opus   | 6k   | +1k per impacted symbol    |
| optimizer         | opus   | 7k   | +2k per module swept       |
| skills-resolver   | sonnet | 4k   | +1k per skill              |
| custom-docs-curator | sonnet | 4k | +1k per document            |
| security-orchestrator | sonnet | 4k | +2k per stack routed       |
| sca-npm           | haiku  | 2k   | flat                       |
| sca-java          | haiku  | 2k   | flat                       |
| sca-mobile        | haiku  | 2k   | flat                       |
| security-sca      | sonnet | 6k   | +2k per ecosystem          |
| security-remediation | sonnet | 5k | +2k per finding fixed     |
| security-code-review | sonnet | 4k | +2k per 200 diff lines    |
| security-code-review-global | opus | 12k | +1k per 3.5 KB read, one pass per ≤350 KB lot |
| frontend-fidelity | opus   | 10k  | +4k per screen/mockup      |
| critic-opus       | opus   | 6k   | +2k par surface auditée    |
| critic-fable      | opus   | 6k   | +2k par règle métier revue |
| critic-sonnet-max | sonnet | 7k   | +2k par fichier relu ligne à ligne |
| design-review     | opus   | 6k   | +2k per screen reviewed    |
| seo-specialist    | opus   | 6k   | +2k per public page measured — aligned on `design-review`, the reviewer that names it due |

**The `tier` and `base` columns keep matching the committed frontmatter**
(`.agents/evals/test_tier_surfaces.py` asserts exactly that): `dev-mono`
is still `opus`/`medium` on disk, and the FORECAST reads these rows as a measure of
VOLUME, not of a bill.

**`communicator` carries `haiku` on Claude Code since 2026-09-05, and that is a
PILOT DECISION taken by hand, not a derivation.** It replaces a deliberate absence:
until then this def declared no `model:` and no `effort:`, so it ran at the session
tier, and that vacuity was pinned on purpose (S-00000897) precisely because pinning
a tier here forecasts one nobody configured and DOWNGRADES a session already at
opus — which AGENTS.md § Full power forbids an AGENT to do. The pilot is not an
agent and this is his kit: the setting stands, and it is recorded here rather than
the doctrine rewritten, so that nobody cites it as a precedent for lowering a tier
on their own. The freeze is unchanged — `apply-mode` counts this def and never
raises it (MODEL_MODES § 3.2).

**The tier claim is host-scoped, and the scope is written so it is not re-read as
universal (L-00000079).** Per host, in the agent definitions:
- `claude`: `model: haiku` + `effort: medium`, FROZEN.
- `gemini`: `model:` only, FROZEN — no `effort:` (gemini-cli 0.57.0 refuses the
  key, S-00002854); the mode lever never touches it (MODEL_MODES § 3.2).
- `codex`: `model = "gpt-6-luna"` pinned and `model_reasoning_effort = "medium"`, frozen.
- `github` / `kimi`: no tier key on any agent, communicator included.

The row exists because a budget sheet that omits an agent makes the orchestrator's
FORECAST silently short; `3k` is an estimate to tune from run recaps, like every
other row.

**The two UI agents, and their configured review gap.**
Their tiers above are READ from the `model:` frontmatter of
`.claude/agents/frontend-fidelity.md` and `design-review.md`, not chosen here — a
budget sheet that invented a tier would drift from what actually runs. On Claude
Code the reviewer may sit a tier ABOVE the implementer, which is the whole point
of the pair: the agent that wrote a screen cannot be the one certifying it, and a
sharper reviewer is worth more than a sharper implementer at that step.
On Codex, `frontend-fidelity` uses
`gpt-6-sol` / `high` and `design-review` uses `gpt-6-astra` / `xhigh`
(T-00000553); this is a pilot role mapping, not a model-capability claim. On
Gemini both agents use the same tier. Budget these pairs at their configured
tiers; do not forecast an unconfigured gap.

**`security-code-review-global` is budgeted PER PASS, and its whole-run figure is
an estimate, not a bound** (pilot decision `S-01M51GNKV9FM9WWXSKXEJQSEQY`,
2026-10-16). The former read cap (about 150 files) is lifted: `/audit -global`
runs one census pass, then one pass per code lot of at most 350 KB
(`audit_report.py --lots`), and the row above prices ONE pass. Measured on this
kit by plan-critic during the plan review: tests excluded, ~260 source files,
7.7 MB, ~25 passes ≈ 2.5M tokens; tests included (607 code files, 20.5 MB), up
to ~6M, configuration on top. The first real `/audit -global` is the first
measurement.

## Confidence band
Default ±50%. Narrow to ±30% for flat-cost agents.

## Forecast output contract (what the hooks parse)
- Orchestrator FORECAST row: `<agent>  <one-line job>  ~Nk` (agents skipped by routing get no row); block ends at the `TOTAL` line.
- Planner refinement: `FORECAST-REFINE: <agent> ~Nk` on its own line.
- est format `~Nk` or `~?`; actual format `N.Nk`. Run log lives at `.agents/state/local/RUN_LOG.md` (git-ignored, cleared by the recap hook).
