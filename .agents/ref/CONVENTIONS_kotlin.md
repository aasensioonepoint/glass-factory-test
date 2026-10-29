# Kotlin conventions — canonical (shared by Claude Code, Codex, Copilot)

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. Facts specific to ONE project (Kotlin and JVM target, Android or KMP layout, DI
library) belong in a §2 of that project's own copy, each with its ledger id — not here.

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

**REACHABILITY, said without euphemism.** `language-detector` emits no `kotlin` token (its token set
is CLOSED), so — not measured: the detector may name this sheet only if it emits a kotlin token
(language-detector.md:70-72) — it is reached through `CONVENTIONS_java.md`, the
`java-hexagonal-spring` skill and the `## java / kotlin` section of `DOCS_REGISTRY.md`. Widening the
detector is a residue to open after T-01M5BZBWTT, never a closed identifier.

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

**Layers live elsewhere — read them too.** Spring on Kotlin: the `java-hexagonal-spring` skill (its
rules hold for Kotlin beans; its examples are Java). JVM build, SQL, secrets and SCA: the rules of
`CONVENTIONS_java.md` apply unchanged. Android, KMP and Compose have NO kit skill: this sheet names
their gate rules only, and `DOCS_REGISTRY.md` lists NO Android, KMP or Compose root today (neither
`android`, `compose` nor `multiplatform` appears in it): fetch their official docs at need.

## Language & types

- No `!!`: prefer `?.`, `?:` or `requireNotNull(x) { "why" }` — `!!` is a `NullPointerException`
  that names neither the value nor the reason it was expected.
- `val` by default, and a public API exposes `List`/`Map`, never `MutableList`: a caller that can
  mutate the returned collection rewrites the owner's state behind its back.
- A `when` over a `sealed` type has no `else`: adding a subtype must break the build at every
  consumer, and an `else` branch absorbs it in silence.
- Java interop nullness is strict (`-Xjsr305=strict`): a platform type (`T!`) otherwise lets a
  Java `null` cross into code the compiler believes non-null.

## Boundaries & validation

- `CancellationException` is always rethrown — and `runCatching` around a `suspend` call catches it
  too: swallowing it keeps a cancelled coroutine running and breaks structured concurrency.
- No `GlobalScope`: work is launched in a scope that owns it (`coroutineScope`, `viewModelScope`),
  or its failure and its lifetime belong to nobody.
- Blocking I/O moves off the main thread or the event loop (`withContext(Dispatchers.IO)`): one
  blocking call there freezes every coroutine sharing it.
- A query takes BOUND parameters (`:name` in Room, bind variables in JDBC/Exposed): a string template
  inside SQL is an injection, exactly as concatenation is in Java.
- Secrets never live in source: on Android, `local.properties` (git-ignored) for local values and
  CI-provided build fields for releases; cleartext traffic is disabled and every exported
  component is guarded — an exported activity or receiver is an entry point any app can call.

## Guards & tests

- At the gate, `./gradlew check` runs BARE, exactly as CI does — never a hand-picked subset that
  green-lights a module the full run would fail. The dev and its judges run their `BANCS:` line
  (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`): `<mod>/src/test/kotlin/<pkg>/FooTest.kt::bar`
  is `./gradlew :<mod>:test --tests '<pkg>.FooTest.bar'`. A filter that matches nothing is a failure
  to report, never a reason to widen the run in silence.
- Coroutine code is tested under `runTest` (kotlinx-coroutines-test), never with a real delay:
  virtual time makes the test deterministic and fast.
- Hand-written fakes first, MockK when a mock is needed (the registry's choice for Kotlin): a fake
  exercises the contract, and MockK stubs `suspend` functions natively (`coEvery`).
- A gate is fail-closed: an unreadable file or an I/O error makes it fail loudly, never turn green.

## Tooling

- ktlint or detekt runs in CI, with `kotlin.code.style=official`: form is settled by a tool.
- Versions sit in the Gradle version catalog (`gradle/libs.versions.toml`) and the build goes through
  `./gradlew`: one place to bump a version, and one pinned Gradle for every machine.
- SCA: a Kotlin project is scanned through its BUILD TOOL, by the Java path of `sca-scan.sh` — a root
  `build.gradle.kts`/`build.gradle` runs `dependencyCheckAnalyze`, which yields a report ONLY if the
  project declares the OWASP plugin, and `NVD_OFFLINE`/`NVD_DATA_DIR` are NOT forwarded to Gradle;
  a root `pom.xml` goes through the Maven block. A missing tool, plugin or report is NAMED
  `java coverage DEGRADED` — do NOT read that GO as an absence of CVEs.

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested kotlin conventions.
