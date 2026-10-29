# Forge-side protection — two MODELS, shipped inert

`main-protection.ruleset.json` and `main-protection.adoptant.ruleset.json` are
**templates you import by hand** — ONE of them, the one that matches the mode of
your tree (§ "Which file to import"). Nothing in this kit applies them, and no
agent can: a ruleset lives in the forge's settings, not in the tree. Until a
human imports one, this directory changes nothing.

## Read this before anything else: which of the two things is the gate

This lot ships **two** mechanisms and they are not of the same nature. Saying so
plainly is the point — a document that claims a guarantee the code does not hold
is what stops anyone from seeing the defect.

**The local `pre-push` hook is a REMINDER.** It reads
`.agents/state/local/VERIFY_STAMP`, a **git-ignored, unauthenticated** file that a
five-line `printf` fabricates in three seconds. It **attests a discipline; it
proves nothing.** It also does nothing at all if it was never installed, and
`git push --no-verify` walks straight past it.

**The gate is the IMPORTED ruleset, and only once the pilot has activated it.** It is the
only half of the pair a contributor cannot talk their way around, because it is
enforced by the forge rather than by the clone.

**The known holes, bounded rather than enumerated:** `--no-verify`, a hook never
installed, a forge whose plan carries no ruleset, and tag pushes (an annotated
tag's local sha is the tag object, not a commit, so the hook declines to gate it
and says so) are the holes we **know**. **The list is not closed** — treat it as a
floor on what escapes, never as the full set.

## The ceiling, measured rather than assumed

**Rulesets on a PRIVATE repository require a paid plan.** Measured on this
repository: `403` on the rulesets endpoint. On a **public** repository they are
free. On a private one, GitHub Team or Enterprise Cloud is the condition — so on
a private repo without a plan, importing this file is simply not possible, and
**nothing enforceable exists after this lot**. That is a fact to bring to the
pilot, not a step to skip quietly.

## Which file to import — the mode of your tree decides

`.github/workflows/ci.yml` carries three jobs. Its `porte` job
decides the mode with the same rule as `core-scripts/verify.sh` and
`.githooks/pre-push`: **ADOPTANT iff `.agents/IS_THE_KIT` is absent AND
`.agents/security/module_discovery.py` is present**. `tests` (the kit's suite)
runs unless `porte` answered `adoptant`; `adoptant` runs
`.agents/bin/porte_adoptant.py` only then: the project's own build and tests,
submodules included — or its tracked `scripts/verify-projet.sh`, which then
decides for the WHOLE repository, no default sequence for any module (pilot
by design); without a script and without any module of a known family
(npm, python, java, swift), the guards alone judge and the gate warns
(`build et tests non vérifiés par le kit`) without blocking — plus, always,
gitleaks, and semgrep on what is NEW since the base the job passes
(`CADRE_SEMGREP_BASE`: the PR's base, or `github.event.before` on a push), or
else the merge-base with the default branch. If `porte` itself fails, its outputs are empty: `tests` runs,
`adoptant` is skipped, and `porte` — required by both models — blocks. On a pull
request `porte` also reads the base (`HEAD^1`): a PR that takes an ADOPTANT base
out of adoptant mode (the marker added, or the discovery removed) fails `porte`,
so the required check blocks it — instead of `adoptant` being skipped, which the
forge reports as Success.

| your tree | import | required checks |
|---|---|---|
| the kit itself (`.agents/IS_THE_KIT` present) | `main-protection.ruleset.json` | `adoptant`, `porte`, `tests (macos-latest)` |
| a project that adopted the kit and KEPT its `ci.yml` | `main-protection.adoptant.ruleset.json` | `adoptant`, `porte` |
| a project that REWROTE `ci.yml` | neither as-is | the contexts of YOUR jobs — both models describe the kit's `ci.yml` |

**Why the kit's model may require `adoptant`, a job that never runs there.** A
job skipped by its `if:` reports Success. GitHub documentation, page "Using
conditions to control job execution" (read 2026-10-06): « A job that is skipped
will report its status as "Success". It will not prevent a pull request from
merging, even if it is a required check. » Documented, not measured on a forge.

**Why the adopting project's model requires NO check of the kit's mode.** In
adoptant mode `tests` is skipped, and the name the forge gives a SKIPPED MATRIX
check is not in that documentation — a required check that may never report is
a merge blocked forever. The adoptant model therefore requires only the jobs that
run in its mode, and depends on nothing the documentation leaves unsaid.

**The residue, named.** A project that already imported the OLD model (one
check, `tests (macos-latest)`) or the KIT's model is exactly in that undocumented
case: if `tests (macos-latest)` stays pending on its pull requests, replace the
stored ruleset with `main-protection.adoptant.ruleset.json`. The stored ruleset
does not follow the file — editing the JSON in the tree changes nothing on the
forge.

## Import it

Settings → Rules → Rulesets → **New ruleset** → **Import a ruleset**, then upload
the file chosen above.

Verify it landed — and verify it from the API, not from the page you just used:

```bash
gh api repos/{owner}/{repo}/rulesets
gh api repos/{owner}/{repo}/rulesets/<id>   # the rules actually stored
```

An empty array means the import did not happen. A ruleset whose `enforcement` is
`disabled` or `evaluate` is **not protecting anything** — `evaluate` reports what
*would* have been blocked and blocks nothing. The file ships `"enforcement":
"active"` on purpose: a model that imported itself into a silent no-op would be
the false activation this whole lot exists to avoid.

## What they contain, and why each line

Both models carry the same four rules; only the list of required checks differs.

| Rule | Effect |
|---|---|
| `deletion` | the default branch cannot be deleted |
| `non_fast_forward` | no force-push over shared history |
| `pull_request` | 1 approval, and approvals are **dismissed when new commits land** |
| `required_status_checks` | strict: the branch must be up to date, and the named checks must pass |

**The required checks are `adoptant`, `porte` and `tests (macos-latest)` on the
kit's model, `adoptant` and `porte` on the adopting project's — the ubuntu and
windows legs of `tests` are deliberately absent from both.** In
`.github/workflows/ci.yml` the `tests` job runs a
three-OS matrix with `continue-on-error` on ubuntu (pilot decision, 2026-09-01)
and on windows (pilot decision, 2026-09-24, after its first real run went red and
hung past the timeout): both still run and still give a signal, but a red leg
there no longer fails the run. Requiring a check that is allowed to fail would be
a rule that never bites. Reversible in one line, on both sides, the day that
decision changes.

**Check names are `<job id> (<matrix value>)` for a matrix job, and `<job id>`
for a job without a matrix (`porte`, `adoptant`).** Rename a job in `ci.yml`, or
change the matrix, and these contexts stop matching — a required check that never
reports leaves pull requests pending forever, which reads like an outage rather
than like a stale config. A kit-only test derives the expected contexts of BOTH
models from `ci.yml` — the kit's: every blocking leg of
every job; the adopting project's: the legs of the jobs that run in adoptant
mode, and none proper to the kit's mode — and fails when they drift; that net is
**kit-only** (it is stripped from the template) because its operands belong to
the adopting project and are meant to diverge.

## `CODEOWNERS`

`.github/CODEOWNERS.example` is a starting point, and its **name is its safety**:
GitHub activates a file named exactly `CODEOWNERS` the moment it reaches the
default branch. Rename it deliberately, replace every `@ORG/TEAM` placeholder, and
only then consider setting `require_code_owner_review` to `true` in the ruleset —
turning that on without owners who can actually review is how a repository locks
itself out of its own default branch.

## Removing it

Delete the ruleset in Settings → Rules, or `gh api -X DELETE
repos/{owner}/{repo}/rulesets/<id>`. Deleting the JSON file from the tree does
**not** remove an imported ruleset: the file was a model, the ruleset is state
held by the forge.
