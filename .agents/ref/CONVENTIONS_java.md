# Java 25 / Spring Boot 4 conventions — canonical (shared by Claude Code, Codex, Copilot)

Every rule states its REASON in one clause: a rule without its reason does not survive a
disagreement. Facts specific to ONE project (module layout, JDK release, framework version, build
tool) belong in a §2 of that project's own copy, each with its ledger id — not here.

Adapted from ECC (affaan-m/ECC @ 6f1881ae, MIT, (c) 2026 Affaan Mustafa) — notice : THIRD_PARTY_NOTICES.md

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

**Versions.** Java 25 is the target of this kit's guidance; Spring Boot 4
requires Java 17 at minimum and runs on Spring Framework 7. Check the project's build file and
wrapper before applying a version-specific rule: the project's own release, recorded in its §2, is
what ships.

**Spring and hexagonal layers live in the `java-hexagonal-spring` skill and `## java / kotlin` of
`DOCS_REGISTRY.md`. Read both.** The two are NOT disjoint: rules stated in both include `record`
value types, `Optional` as a return type only, no swallowed exception, `final` fields and the domain
tested in plain JUnit; where both state a rule this sheet adds its gate detail, and a disagreement
between them is a defect to report. This sheet is the SHORT routing, language and verification
layer; the skill carries ports and adapters, injection, transactions, the web layer and slice
tests, each under its version label. Kotlin on the JVM has its own sheet,
`CONVENTIONS_kotlin.md`; the JVM build and SCA rules below hold for it too.

## Package boundaries

Choose an architecture explicitly; the two layouts below are alternatives. Keep
business decisions out of the web and persistence adapters.

Hexagonal (ports and adapters):

```text
src/main/java/com/example/orders/
  domain/model/Order.java
  domain/port/OrderRepository.java
  application/PlaceOrder.java
  adapter/in/web/OrderController.java
  adapter/out/persistence/JpaOrderRepository.java
src/test/java/com/example/orders/ArchitectureTest.java
```

The domain owns its ports and imports no Spring or persistence classes. An adapter
implements a port and translates between external and domain types. In an
ArchUnit test under `src/test`, use `onionArchitecture()` for the domain,
application and adapter packages; add a direct assertion that domain classes do
not depend on `org.springframework..`. Match the package patterns to the real
project and ensure they select classes, otherwise a green rule can be empty.

N-tier (controller, service, persistence):

```text
src/main/java/com/example/orders/
  controller/OrderController.java
  service/OrderService.java
  persistence/OrderRepository.java
src/test/java/com/example/orders/ArchitectureTest.java
```

In an ArchUnit test under `src/test`, use `layeredArchitecture()` with controller,
service and persistence layers. Constrain which layer may access each one and
check for real classes in every declared layer. Do not call this layout hexagonal:
its service and persistence boundaries are different from domain-owned ports.

## Language & types

- Fields are `final` by default and value types are `record`s: an object that cannot change after
  construction cannot be observed half-updated by another thread or another caller.
- A public method returns `List.copyOf(...)` (or `Set`/`Map`), never its internal collection: handing
  out the live collection lets any caller rewrite the object's state behind its invariants.
- No raw generic types (`List` for `List<T>`): a raw type switches the compiler check off, so the
  `ClassCastException` moves from the build to the first unlucky request.
- A closed hierarchy is `sealed` and its `switch` has no `default`: adding a variant must break the
  build at every consumer, and a `default` branch absorbs the new case in silence.
- `Optional` is a RETURN type only, consumed by `map`/`orElseThrow`, never by a bare `get()`: `get()`
  on an empty value is a `NoSuchElementException` with no context, i.e. a null check postponed.

## Boundaries & validation

- An exception is never swallowed: `catch (Exception e) {}` erases the failure, so either rethrow
  with context or log with the cause; a broad catch lives only in the top-level handler.
- Domain errors are unchecked exceptions that carry their identifiers (`id=…`): a message without
  the failing key cannot be traced back from a log line.
- SQL takes BIND parameters only (`PreparedStatement`, named parameters): a value concatenated into
  a query string is an injection, whatever the source of the value looks like today.
- `ProcessBuilder` gets an argument LIST, never a shell string built from input, and a user-supplied
  path is normalised then checked against its base directory before any open: both turn data into
  an instruction otherwise (command injection, path traversal).
- Secrets come from the environment or a secret manager, never from source, and are never logged;
  an error response carries a generic message: a stack trace or SQL text in a response is a map
  of the system handed to whoever triggered it.
- A shared singleton holds no mutable instance field, and async work runs on a BOUNDED executor:
  the first is a data race no serial test sees, the second creates threads until the host falls over.

## Build and tests

- At the gate, the build runs BARE, exactly as CI does — `./mvnw -B verify` when `mvnw` exists, or
  `./gradlew test` when `gradlew` exists — never a hand-picked subset that green-lights a module the
  full run would fail. If neither wrapper is present, report its absence; do not guess a test task.
  The dev and its judges run their `BANCS:` line (THE BENCH LIST, `.agents/skills/kickoff/SKILL.md`):
  `<mod>/src/test/java/<pkg>/FooTest.java::bar` is
  `./mvnw -q -pl <mod> -am test -Dtest='FooTest#bar' -Dsurefire.failIfNoSpecifiedTests=false`
  (Maven) or `./gradlew :<mod>:test --tests '<pkg>.FooTest.bar'` (Gradle). A filter that matches
  nothing is a failure to report, never a reason to widen the run in silence: with
  `-Dsurefire.failIfNoSpecifiedTests=false` Maven stays green on an empty match, so read
  `Tests run: 0` as a FAILED bench.
- Always the wrapper (`./mvnw`, `./gradlew`), never a globally installed `mvn`/`gradle`: the wrapper
  pins the build tool version the project was verified with.
- No `Thread.sleep` in a test — poll with a bounded wait (Awaitility): a sleep is a flake under load.
- The domain is tested in plain JUnit, independent of Spring and with no container: if it needs
  one, the boundary leaked. Put architecture tests under `src/test/java`; a package rule belongs in
  the build's test phase.
- On Boot 4 tests, use `@MockitoBean`; the old `@MockBean` was removed and replaced by
  `@MockitoBean`. Check the project's version before migrating test annotations.
  Likewise check `@SpyBean` against the Boot 4 replacement `@MockitoSpyBean`.
- A gate is fail-closed: an unreadable file or an I/O error makes it fail loudly, never turn green.

## Tooling

- The compile target is DECLARED (`maven.compiler.release` or a Gradle toolchain): a build on another
  JDK otherwise compiles against a different platform API than the one that ships.
- Run Checkstyle only if its plugin is declared in `pom.xml` or `build.gradle*`.
  Run Spotless only if its plugin is declared in `pom.xml` or `build.gradle*`.
  Run PMD only if its plugin is declared in `pom.xml` or `build.gradle*`.
  Run each lint or formatting command only if the corresponding plugin is declared;
  neither Maven nor Gradle supplies a universal lint task. Where a formatter is declared it runs
  in CI: form is settled by a tool, so a review spends its attention on substance.
- Annotation processors (Lombok, MapStruct) are declared as PROCESSORS, not only as dependencies: a
  processor the compiler never runs leaves generated code missing in CI while the IDE stays green.
- SCA: a `pom.xml` at the ROOT LOOKED AT is scanned by OWASP dependency-check (aggregate, through
  `./mvnw` or `mvn`); a root `build.gradle`/`build.gradle.kts` runs `dependencyCheckAnalyze`, which
  yields a report ONLY if the project declares the OWASP plugin, and `NVD_OFFLINE`/`NVD_DATA_DIR` are
  NOT forwarded to Gradle (`.agents/security/sca-scan.sh`, Maven and Gradle blocks). A missing tool,
  plugin or report is NAMED `java coverage DEGRADED` — do NOT read a GO with java coverage degraded
  as an absence of CVEs. Sub-modules are reached by `--all-modules` discovery.

Sources: [Java 25](https://docs.oracle.com/en/java/javase/25/),
[Spring Boot 4.1](https://docs.spring.io/spring-boot/4.1/reference/),
[Spring Framework 7](https://docs.spring.io/spring-framework/reference/),
[ArchUnit architectures](https://www.archunit.org/userguide/html/000_Index.html).

Check `.agents/state/index/CUSTOM_DOCS.md` for ingested java conventions.
