# Swift conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (Swift and Xcode versions, language mode, schemes,
layout) belong in a §2 of that project's own copy, each with its ledger id — not here.

**GUARANTEE — a §2 written by an adopting project SURVIVES a template refresh.**
Without this written down the invitation above is a trap: it asks you to write
something the next sync might erase, and nobody would find out until it was gone.
What holds, by relevé rather than by promise:

- **§1 belongs to the kit, §2 belongs to the project.** §1 is rewritten wholesale
  by kit-side syncs; nothing in the kit ever writes §2.
- **No kit mechanism writes this file inside an adopting project.**
  `sync_template.py` runs `main → template/starter-kit` INSIDE the kit repo only,
  and the docs-sync flow never touches `.agents/ref/` at all.
- **A consumer refresh is a MERGE, never a copy-overwrite** (L-015): a three-way
  merge keeps an added §2, or raises a conflict — it never deletes it silently.
- **The honest limit**: it is pinned by `.agents/evals/test_conventions_contract.py`.

**Framework layer: NO kit skill carries Swift, SwiftUI or UIKit.** The `## swift` section of
`DOCS_REGISTRY.md` lists the Swift and Apple references, fetched at need. This sheet is the SHORT
gate layer; the rules below hold for an app, a package or a server-side target alike.

## Language & types

- `swift-tools-version` (first line of `Package.swift`) and the Swift language mode are read BEFORE
  writing: syntax or strict-concurrency checks newer than the declared mode build locally and not on CI.
- `!`, `try!` and `as!` stay out of production paths — `guard let`, `do/catch` or `throws`, `as?`:
  each one turns an unexpected value into a crash on the user's device.
- No empty `catch {}`, and `try?` only where the error genuinely carries nothing: both drop the cause
  the caller needed to decide.
- `assert` is stripped in release builds; an invariant that must hold in production is a
  `precondition` or a `throw`, and a library throws rather than calling `fatalError`.
- `let` over `var`, `struct` over `class` unless identity is needed: a shared reference is mutable
  state any holder can change for every other.
- A `switch` on an enum lists its cases; on an enum you do not own, `@unknown default`: a new case
  must surface as a warning, not fall silently into `default`.

## Boundaries & validation

- Shared mutable state lives in an `actor` or is `Sendable`; `@unchecked Sendable` and
  `nonisolated(unsafe)` state why the type is safe: they silence the checker, not the data race.
- Structured concurrency (`async let`, `TaskGroup`) before an unstructured `Task {}`; a stored task
  is cancelled with its owner: a fire-and-forget task outlives the screen and writes into nothing.
- No blocking work on `@MainActor` (`Thread.sleep`, synchronous I/O), and state read before an
  `await` is re-checked after it: actor reentrancy lets another call run at every suspension point.
- Escaping closures name their capture of `self` (`[weak self]` where the closure can outlive it) and
  delegates are `weak`: a strong cycle is a leak no test notices.
- Secrets and tokens live in the Keychain — never `UserDefaults`, never a literal in source: a
  shipped binary is decompiled in minutes. App Transport Security exceptions say why, per domain.
- Input from deep links, the pasteboard, the network or a file is validated before use; SQL is bound,
  a `Process` takes an argument array, and a user path is checked against its allowed root.

## Guards & tests

- SwiftLint (or `swift-format`) with the project's checked-in config, behind one command local and
  CI share; an inline `// swiftlint:disable` is narrow and says why.
- At the gate the suite runs BARE, exactly as CI does (`swift test`, or `xcodebuild test` with the
  CI scheme and destination). The dev and its judges run their `BANCS:` line (THE BENCH LIST,
  `.agents/skills/kickoff/SKILL.md`): `Tests/AppTests/UserTests.swift::testCreate` is
  `swift test --filter '^AppTests\.UserTests/testCreate$'` — `--filter` is a REGEX, and unanchored it
  runs every test whose identifier contains the string; `swift test list` prints the exact
  identifiers, Swift Testing `@Test` functions included. In an Xcode project the same test is
  `xcodebuild test -scheme <Scheme> -destination <dest> -only-testing:AppTests/UserTests/testCreate`.
- No test depends on order, the network or a real clock: each test builds its own fixtures, or the
  suite flakes on the machine that is not yours.
- `print` never reaches a commit; logging goes through `os.Logger` or the project's logger.

## Tooling

- `Package.resolved` is committed for an app: without it two resolutions pick two dependency sets
  and CI validates one that is not shipped.
- SCA: `Package.resolved` at the ROOT LOOKED AT, or anywhere under its `ios/` folder, starts
  `sca-scan.sh`'s Swift block — OWASP dependency-check with its EXPERIMENTAL analyzers
  (`--enableExperimental`). Without the `dependency-check` CLI, swift coverage is DEGRADED and nothing
  is scanned; with it, the block has no "no report" branch, so a run that produced no report still
  reads `scanned`. A `Podfile.lock` or `Package.swift` alone does not start the block, and an Xcode
  project's `Package.resolved` (inside `*.xcodeproj/`) is seen only under `ios/`. Do NOT read a GO
  verdict on a Swift project as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested swift conventions.
