# TypeScript / JavaScript conventions — canonical (shared by Claude Code, Codex, Copilot)

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (framework version, ORM, repo layout) belong in
a §2 of that project's own copy, each with its ledger id — not here.

**GUARANTEE — a §2 written by an adopting project SURVIVES a template refresh.**
Without this written down the invitation above is a trap: it asks you to write
something the next sync might erase, and nobody would find out until it was gone.
What holds, by relevé rather than by promise:

- **§1 belongs to the kit, §2 belongs to the project.** §1 is rewritten wholesale
  by kit-side syncs; nothing in the kit ever writes §2.
- **No kit mechanism writes this file inside an adopting project.**
  `sync_template.py` runs `main → template/starter-kit` INSIDE the kit repo only,
  and refuses first thing when the local `template/starter-kit` branch is absent —
  which is exactly the tell that you cloned a consumer project. The docs-sync flow
  never touches `.agents/ref/` at all; it curates `docs/tech/` into
  `CUSTOM_DOCS.md`.
- **A consumer refresh is a MERGE, never a copy-overwrite** (L-015). A three-way
  merge keeps an added §2, or raises a conflict — it never deletes it silently.
- **The honest limit**: the external provisioning tool does not live in this repo,
  so this guarantee pins OUR mechanisms and states the doctrine that tool must
  respect — merge, never copy-overwrite. It is pinned by
  `.agents/evals/test_conventions_contract.py`.

**Next.js detected → read `CONVENTIONS_nextjs.md` as well.** One line here rather
than an edit to four agent sheets: the framework rules (version-specific build,
`params` as a promise, the `react-server` split) sit beside this file, and this
file stays the TypeScript/JavaScript base.

**React detected → read `.agents/skills/react-best-practices/SKILL.md` as well.**
The React 19 and Next 15–16 rules live in that kit skill; route to it only when
the detected stack uses React, so other TypeScript projects keep this base sheet.

## Language & types

- Strict mode assumed; never introduce `any` without a short `// justified:` comment.
- Prefer `Result`-style returns over thrown exceptions in services; throw only at boundaries.
- Type-only imports via `import type`.
- Module resolution is a PER-PACKAGE fact, not a per-repo one: `nodenext` wants the `.js` suffix on
  relative imports, a bundler-resolved app breaks on it. Measured: the suffix compiled and passed
  the unit runner, then failed the production build with `Module not found`. Check per package.
- `tsc` does not reliably auto-discover `@types` under a pnpm-style layout: a package using Node
  globals declares `"types": ["node"]` in its own `tsconfig` — a devDependency is not enough, and a
  package resolving it transitively through another `@types` compiles by accident (measured).
- Tooling that inspects imports tests the suffix on the file RESOLVED ON DISK, never on the written
  specifier — otherwise the rule is dead while its tests report green (measured, two rules).

## Untrusted data, secrets & UI

- Never put data in the DOM through `innerHTML`, `outerHTML` or `document.write` — build nodes and
  set `textContent`. Anything read from a file, a database or an API is untrusted text, including
  values your own backend wrote. Deliberately offering no HTML-injection helper is what makes this
  enforceable rather than hoped for.
- Render an ABSENCE as an absence, never as a zero: "not fetched yet" and "fetch failed" are not
  "the value is 0". Keep a distinct state for unmeasured, or the UI reports a measurement it
  never made.
- Never reflect the input back in an error message: returning a value the client just sent adds
  nothing and turns every error into a mirror.
- Validate the SHAPE of an identifier taken from a URL before it reaches the database, or the
  driver raises a type error no layer translates and the response escapes the JSON error contract
  (measured, caught by a security gate).
- Mask a secret inside a URL with `new URL()`, never a regex: a regex stops at the first `@` and
  leaks the tail of a password. Fail closed on an opaque URL and on a parse failure (measured, one
  HIGH paid). The `TypeError` from `new URL()` carries the whole URL in its `input` property — never
  relay it as `cause`, any log that serialises the error reopens the leak.
- Never pass a secret on a command line (visible in the process table); use the child's environment.
- A generator that writes TypeScript from data escapes KEYS as much as VALUES, and refuses
  fail-closed upstream any name outside `^[A-Za-z_][A-Za-z0-9_]*$`: a quoted identifier accepts
  everything but the quote, so a `}` followed by code leaves the literal and injects into a file
  that is generated, committed and imported (measured, HIGH).

## Boundaries & validation

- Keep the TRANSPORT ceiling and the BUSINESS invariant apart: the ceiling (schema validation,
  `.max()`, identifier shape) bounds what enters over HTTP and must not invent a limit duplicating
  a domain rule, while the invariant lives in the domain and is called by EVERY adapter — otherwise
  one rule exists in two copies, free to diverge, with tests passing for different reasons.
- Two implementations of one port share ONE contract test suite run against both: parity must not
  rest on discipline.
- A dev-reload singleton guard (`globalThis`) sits ONCE at the root owning the shared resource,
  never per consumer — a fix applied at a leaf gets recopied by every consumer added after it.

## Guards & tests

- Tests colocated `foo.ts` ↔ `foo.test.ts`; runner per language-detector output.
- Every guard carries a POSITIVE assertion proving it SEES the real case it is meant to judge, not
  only negative assertions on fixtures: "0 violations" proves nothing until the scanner is shown to
  see something. Measured four times on one consumer project — a probe listening on the wrong
  address, a rule whose pattern could never match, a scanner bounded at 8 lines where the real case
  spanned eleven; each reported "all good".
- A gate is fail-closed: an unreadable file or an I/O error makes it fail loudly. A gate that turns
  green on error is worse than no gate.
- Prove a blind spot with a dedicated test case, never a sentence of documentation — future
  coverage then announces itself.
- Never pin a counter in a test when its value can diverge between a workstation and CI (ignored
  files, an over-counting index).

## Tooling

- Use the package manager detected from lockfiles.
- ESLint 9 flat config: entries of an `ignores` list are an OR, so a test file inside a scoped
  folder needs its own entry; and `no-restricted-imports` treats an `import type` as a value import
  unless `allowTypeImports: true` is set explicitly (checked in the rule's source).
- On Windows, `spawnSync` of a `.cmd` without `shell: true` returns `EINVAL` since the
  CVE-2024-27980 fix, and the bare name returns `ENOENT` — pass the command as ONE string, because
  `cmd + args[] + shell: true` is deprecated (DEP0190) and concatenates without escaping.
- Check `.agents/state/index/CUSTOM_DOCS.md` for ingested team conventions on this stack.

## Coverage measurement

- Use the runner's own coverage, not a second harness: `vitest --coverage`, `jest --coverage`,
  or `c8 <command>` for a runner without one. Reason: a separate harness instruments a
  different build than the one your tests ran against, and the two disagree exactly where a
  transform (SWC, esbuild, a path alias) sits between source and executed code.
- Measure the SAME scope the gate runs. A `--coverage` limited to a changed folder produces a
  figure about that folder, and reporting it as the project's is how a number stops meaning
  anything.
- The figure is REPORTED, never gated. The dev agent carries it in its `CHECKS` line
  (`coverage=…`) or writes `unmeasured: <reason>`. A figure silently omitted reads as a
  measurement that was taken and found unremarkable, which is the one thing it is not.
- **NO THRESHOLD IS SET HERE, AND THE ABSENCE IS THE DECISION.** A number written into this
  sheet would be a commitment made on a codebase nobody has measured. A project that HAS
  measured its own floor writes it into its own config (`vitest.config.ts` thresholds,
  `jest.config.js` `coverageThreshold`), where the runner enforces it and where it moves with
  the project. A threshold living in a shared convention sheet is either ignored or gamed.
- Coverage is a LOCATOR, not a verdict: it shows lines nothing executed. It cannot show an
  executed line whose assertion proves nothing — which is why the positive-control rule above
  is the stronger guarantee of the two.
