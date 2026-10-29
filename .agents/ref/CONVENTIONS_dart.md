# Dart / Flutter conventions — canonical (shared by Claude Code, Codex, Copilot)

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. *measured* marks a rule paid for by an incident on a consumer project — prefer it to a
general best practice, and if you measure the contrary, correct the record rather than working
around it in silence. Facts specific to ONE project (Dart and Flutter SDK versions, state
management, router, codegen policy, repo layout) belong in a §2 of that project's own copy, each
with its ledger id — not here.

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

**Framework layer: NO kit skill carries Flutter.** The `## dart / flutter` section of
`DOCS_REGISTRY.md` lists the Dart and Flutter docs, fetched at need. A Flutter screen is UI work:
the dev slot is `frontend-fidelity`, then `design-review` (AGENTS.md § Golden rules). This sheet is
the SHORT gate layer, and its language rules hold for a pure-Dart package too.

## Language & types

- `analysis_options.yaml` turns on `strict-casts`, `strict-inference` and `strict-raw-types`: without
  them an implicit `dynamic` compiles and the type error surfaces at runtime instead.
- `!` and `late` are a claim the compiler cannot check — prefer `?.`, `??`, `if (x case final v?)`
  or constructor initialisation; never `dynamic` to silence an analyser error.
- `final` locals, `const` constructors when every field is final, unmodifiable collections out of a
  public API: a mutable value handed out is state any caller can change behind its owner.
- A state with variants is a `sealed` type handled by an exhaustive `switch`, never a soup of
  `isLoading`/`isError` booleans: booleans encode impossible states and the compiler flags no
  forgotten case.
- Every `Future` is `await`ed or wrapped in `unawaited()`: a dropped Future loses its error in
  silence.

## Boundaries & validation

- `catch` always carries an `on` type, and an `Error` subtype is never caught: `Error` is a bug, and
  catching it hides the bug instead of fixing it.
- After any `await` in widget code, `context.mounted` (or `mounted` before `setState`) is checked:
  the widget may be gone, and the call then throws or acts on a dead screen.
- Every controller, subscription, `StreamController` and `Timer` created in `initState` is released
  in `dispose`: a leaked listener keeps firing into a disposed state.
- Deep-link URLs and user input are parsed (`Uri.tryParse`) and validated — scheme, host, path —
  before navigation, storage or an API call; a WebView loads no URL taken from a deep link.
- Any value shipped in the client binary — `--dart-define`, `String.fromEnvironment`, a bundled
  `.env` asset — is PUBLIC: a server-side secret stays behind a backend. Runtime tokens and PII go to
  platform-secure storage (`flutter_secure_storage`), never `SharedPreferences`, and never into
  `print`/`debugPrint`.
- `http://` is refused in release builds (Android cleartext off, iOS ATS on): cleartext traffic is
  readable by anyone on the network path.

## Guards & tests

- At the gate the suite runs BARE, exactly as CI does (`flutter test`, or `dart test` for a pure-Dart
  package). The dev and its judges run their `BANCS:` line (THE BENCH LIST,
  `.agents/skills/kickoff/SKILL.md`): `test/foo_test.dart::<name>` is
  `flutter test test/foo_test.dart --name '<name>$'` — `--name` is a regex over the full name, group
  prefixes included, so the `$` keeps a longer name out; `--plain-name` matches a SUBSTRING.
- Async widget tests advance time with `pump(Duration)` / `pumpAndSettle` or `fake_async`, never a
  real delay: wall-clock waits are the flake that only fails in CI.
- External dependencies are faked behind their interface; no test shares mutable state with
  another, or the result depends on execution order.

## Tooling

- `dart format --set-exit-if-changed .` and `flutter analyze` (or `dart analyze`) both run in CI; an
  `// ignore:` carries its reason on the same line.
- Generated files (`.g.dart`, `.freezed.dart`) are either all committed or all gitignored — one
  policy per project — and never edited by hand: the next `build_runner` run erases the edit.
- `pubspec.lock` is committed for an application, and CI resolves with
  `flutter pub get --enforce-lockfile`: otherwise CI validates a dependency set nobody pinned.
- SCA: `pubspec.yaml` and `pubspec.lock` are NEITHER scanned NOR NAMED by `sca-scan.sh` — its
  `name_uncovered` lists go, rust, php, ruby and dotnet only, so a Dart project gets no degraded
  line at all, and no board task carries the work. Do NOT read a GO verdict on a Dart project as an
  absence of CVEs: it is an absence of LOOKING.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested dart conventions.
