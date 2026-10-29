# Docs & Skills Registry — shared (all five hosts)

<!--
Consumed by `skills-resolver` and available to `dev-*`, `optimizer`, `documenter`.
- `docs`: canonical official documentation roots. Dev agents WebFetch these AT NEED — never paste content into context.
- `llms_txt`: machine-readable doc index if the project exposes one. Resolver verifies liveness before relying on it.
- `search_hint`: query to feed https://skills.sh/api/v1/skills/search?q=… — NOTE this endpoint is OIDC-gated: without a Vercel token it answers `401`, which the CLI masks as "No skills found". An empty result is an auth failure, not an absence.
- fallback when skills.sh is 401-gated or unreachable: the audited GitHub-pinned skills vendored under `.agents/skills/vendor/` (see its README) — verify the AUDIT_LOG pin before install anyway, then an active GitHub search via `.agents/bin/skills_github_fallback.py` when the vendored set covers none of the detected stacks.
- `installed`: managed by skills-resolver — id + SHA-256 hash for change detection. Do not edit by hand.
- `conventions`: the `.agents/ref/CONVENTIONS_<stack>.md` sheet(s) of the section's stack, comma-separated, each path optionally followed by a parenthesised scope. NO code reads this key yet — only the bench `.agents/evals/test_conventions_routing.py` holds it (every value exists; each routed token resolves to a section naming its sheet). The language-detector does not read it: wiring it to the resolved section is the follow-up after T-01M5BZBWTT. Bound: the token `csharp` resolves NO section (only `c#`, `dotnet` and `.net` reach `## c# / .net`), and that title is not renamed (`MINI_ALIAS["dotnet"]` in `skills_github_fallback.py` points at it).
-->

## agent platforms (this kit's own hosts)
- codex          manual: https://developers.openai.com/codex/codex-manual.md · skills: https://developers.openai.com/codex/skills · hooks: https://developers.openai.com/codex/hooks · agents: https://developers.openai.com/codex/subagents
- github-copilot repo-instructions: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions · cloud-agent: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent · skills: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills · custom-agents: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/create-custom-agents · hooks: https://docs.github.com/en/copilot/reference/hooks-reference
- gemini-antigravity manual: https://antigravity.google/manual.html · skills: https://antigravity.google/skills · hooks: https://antigravity.google/hooks · agents: https://antigravity.google/subagents

### skill-discovery — WHERE each host actually looks, one line per FACT

These are the facts the kit's own layout depends on, and they were paid for: four
of this kit's skills were invisible for a while because discovery does not work
the way one would guess. Recorded here so nobody re-derives them from behaviour.

- **github-copilot — THREE directories**, not one: `.github/skills/` **plus**
  `.claude/skills/` **plus** `.agents/skills/`. Consequence for this kit: its
  `.claude/skills/` pointers are ALREADY visible to Copilot, and a skill DIRECTORY
  name OR a `name:` field duplicated across two of those directories is a collision
  whose precedence is undocumented — Claude Code keys discovery on the DIRECTORY
  (measured 2026-09-02, T-00000371); Copilot's key is NOT measured — keep BOTH the
  directory name and `name:` unique rather than betting on an order.
  `source: à ré-établir` (the three concurring pages — CLI, cloud-agent, VS Code —
  were read on 2026-08-06; no URL is written here unverified, see the rule below).
- **gemini-cli — `.agents/skills/` NATIVELY**, as a documented alias of
  `.gemini/skills/`. It is not a house convention its agents happen to read by
  path: discovery finds it. `source: à ré-établir`.
- **antigravity — `<workspace>/.agent/skills/<name>/`, `agent` SINGULAR**, and
  `.agents/skills/` is NOT supported there. The request to standardise on the
  plural was closed "not planned". Consequence: this kit ships no `.agent/skills/`,
  so skills reach Antigravity BY PATH from `GEMINI.md`, never by discovery —
  writing "Gemini / Antigravity" as one skill surface is false.
  `source: à ré-établir` (issue URL not verified during the night of 2026-08-19). CONTRADICTED 2026-10-07 by https://antigravity.google/docs/skills — see the host orchestration block below.

**FORM, and it is a rule rather than a preference: a URL is written here only
when it has been fetched and found to carry the fact.** An unverified URL in a
registry is worse than none — it looks like a source and sends the next reader
somewhere that may never have said this. Where the source could not be verified,
the FACT is written with `source: à ré-établir` and a board task carries the
re-sourcing. Re-sourcing task: **T-00000239**.

**FORM of a discovered skill, and two mistakes that hide one in silence:**
`SKILL.md` is found only at depth 1 under a skills directory
(`<skills>/<name>/SKILL.md`) — one extra level, as in `<skills>/vendor/<name>/`,
is invisible. And the frontmatter must open at LINE 1: a comment banner above the
`---` makes the file unparseable to every host's parser. Neither failure reports
anything — no error, no warning, just a skill that is never offered.

### host orchestration docs — fetched 2026-10-07 for T-00000791 (a)

Every URL in this block was FETCHED on 2026-10-07 and carries the fact written beside it (the
FORM rule above). The page's "Last updated" date or version is given where the page shows one;
otherwise the fetch date stands for the version. Where a fact below CONTRADICTS a line above, it
says so; the line above is stale until corrected (T-00000239).

- claude-code    llms_txt: https://code.claude.com/docs/llms.txt
                 hooks: https://code.claude.com/docs/en/hooks — events, exit 2 + stderr or JSON decision, `.claude/settings.json` (page cites up to v2.1.267)
                 subagents: https://code.claude.com/docs/en/sub-agents — `.claude/agents/`, `model`, `effort`, `isolation: worktree`; `tools` omitted = inherits every tool (up to v2.1.271)
                 skills: https://code.claude.com/docs/en/skills — project discovery under `.claude/skills/` only; `.agents/skills/` not read (up to v2.1.282)
                 permissions: https://code.claude.com/docs/en/permissions — deny → ask → allow; a `Write(path)` rule is accepted but never consulted (path rules: `Edit(path)`, `Read(path)`)
                 memory: https://code.claude.com/docs/en/memory — CLAUDE.md; can also read `AGENTS.md`
- codex          llms_txt: https://learn.chatgpt.com/llms.txt
                 hooks: https://learn.chatgpt.com/docs/hooks — `<repo>/.codex/hooks.json`; PreToolUse deny = `hookSpecificOutput.permissionDecision: "deny"` or exit 2 + stderr; fires on `apply_patch`; default timeout 600 s for most hooks; project hooks "skipped until trusted" via `/hooks`, trust recorded "against the hook's current hash"
                 agents: https://learn.chatgpt.com/docs/agent-configuration/subagents — `.codex/agents/*.toml`, `model`, `model_reasoning_effort`, `sandbox_mode`; parallel; worktree not addressed
                 skills: https://learn.chatgpt.com/docs/build-skills — `$CWD/.agents/skills` and `$REPO_ROOT/.agents/skills`
                 config-reference: https://learn.chatgpt.com/docs/config-file/config-reference.md — no `agents.max_depth`, no `agents.job_max_runtime_seconds` (whole page read); `agents.max_threads` = "Legacy alias"; `features.hooks`, `features.multi_agent` stable
                 approvals-security: https://learn.chatgpt.com/docs/agent-approvals-security.md — `read-only` "can read files and run commands within the read-only sandbox"
                 rules: https://learn.chatgpt.com/docs/agent-configuration/rules.md — `<repo>/.codex/rules/`, commands only (no paths), "Rules are experimental"
                 note: the four `developers.openai.com/codex/…` URLs on the `codex` line above answer 308 to `learn.chatgpt.com/docs/…` (measured 2026-10-07)
- gemini-cli     llms_txt: https://geminicli.com/llms.txt
                 hooks: https://geminicli.com/docs/hooks/ (Last updated: Apr 13, 2026) — hooks read from `settings.json` → `hooks` only; `.agents/hooks.json` is never named
                 hooks-reference: https://geminicli.com/docs/hooks/reference/ (Last updated: Apr 10, 2026) — events `BeforeTool`/`AfterTool`/`AfterAgent`/`PreCompress`…, no Claude-name alias; deny = `decision` + `reason` or exit 2; `permissionDecision` absent
                 subagents: https://geminicli.com/docs/core/subagents/ (Last updated: Jun 8, 2026) — `.gemini/agents/*.md`; `model`, no effort field; "subagents cannot call other subagents"
                 skills: https://geminicli.com/docs/cli/skills/ (Last updated: Apr 30, 2026) — `.agents/skills/` is a documented alias of `.gemini/skills/` and takes precedence over it (source for the gemini-cli skill-discovery line above)
                 policy-engine: https://geminicli.com/docs/reference/policy-engine/ (Last updated: Apr 30, 2026) — workspace `.gemini/policies/*.toml` "currently disabled"
                 gemini-md: https://geminicli.com/docs/cli/gemini-md/ (Last updated: Jun 18, 2026) — `GEMINI.md` default, `context.fileName`, `@file.md` imports
                 changelog: https://geminicli.com/docs/changelogs/latest/ — latest stable v0.63.0, Oct 6, 2026
                 trusted-folders: https://geminicli.com/docs/cli/trusted-folders/ (Last updated: Apr 23, 2026) — feature off by default: `security.folderTrust.enabled`; untrusted folder: `.gemini/settings.json` not loaded; `--skip-trust` or `GEMINI_CLI_TRUST_WORKSPACE=true` trusts the workspace for one session
                 note: banner on https://geminicli.com/docs/hooks/ (2026-10-07): "Unpaid tier and Google One users: Gemini CLI was replaced by Antigravity CLI on June 18th, 2026."
- antigravity    llms_txt: https://antigravity.google/llms.txt
                 hooks: https://antigravity.google/docs/hooks — workspace `.agents/hooks.json`; events PreToolUse/PostToolUse/PreInvocation/PostInvocation/Stop; deny = `decision`; exit code not documented; edit tools `write_to_file`/`replace_file_content`/`multi_replace_file_content`, shell `run_command`; PostToolUse payload carries `toolCall` (name and args)
                 subagents: https://antigravity.google/docs/subagents — `.agents/agents/<name>.md`; `model` inherit/flash/pro; nesting up to 10
                 skills: https://antigravity.google/docs/skills — "defaults to `.agents/skills`", `.agent/skills` kept for backward compatibility (CONTRADICTS the antigravity skill-discovery line above)
                 rules: https://antigravity.google/docs/rules — `AGENTS.md` or `GEMINI.md` in any subdirectory, `.agents/rules/*.md`
                 permissions: https://antigravity.google/docs/permissions — allow/ask/deny; CLI `~/.gemini/antigravity-cli/settings.json`, IDE settings UI
                 agent-settings: https://antigravity.google/docs/agent-settings — `fileAccessPolicy`-style keys and a workspace `.gemini/settings.json` are not documented
                 changelog: https://antigravity.google/docs/changelog — v2.19.1, September 30, 2026; v2.6.0 (August 7, 2026) rejects hook configurations that could never run
                 note: the four `antigravity.google/{manual.html,skills,hooks,subagents}` URLs on the `gemini-antigravity` line above answer 404 (measured 2026-10-07)
- kimi-code      llms_txt: https://moonshotai.github.io/kimi-code/llms.txt
                 hooks: https://moonshotai.github.io/kimi-code/en/customization/hooks.html — `[[hooks]]` TOML in `~/.kimi-code/config.toml` only, no project hooks file; deny = nested `hookSpecificOutput.permissionDecision`; only PreToolUse/Stop/UserPromptSubmit block; crash, other non-zero exit or timeout = "Default allow (fail-open)"
                 agents: https://moonshotai.github.io/kimi-code/en/customization/agents.html — `.kimi-code/agents/` and `.agents/agents/`; no `model` or effort field in the documented frontmatter; "a file without a `tools` list keeps every tool"; parallel sub-agents
                 skills: https://moonshotai.github.io/kimi-code/en/customization/skills — `.kimi-code/skills/` and `.agents/skills/` (project level)
                 config-files: https://moonshotai.github.io/kimi-code/en/configuration/config-files.html — project `.kimi-code/local.toml`; permission modes manual/yolo/auto
                 tools: https://moonshotai.github.io/kimi-code/en/reference/tools.html — `Read`, `Write`, `Edit`, `Bash`, `Agent`
- github-copilot hooks: https://docs.github.com/en/copilot/reference/hooks-reference — `.github/hooks/*.json` (cloud agent, CLI); preToolUse deny = top-level `permissionDecision` or exit 2; nested form not mentioned; preToolUse fail-closed on a crash, timeouts fail-open for every event; VS Code format = PascalCase events + snake_case fields, same decision fields
                 custom-agents: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/create-custom-agents — `.github/agents/*.agent.md`; `model` honored in VS Code, JetBrains IDEs, Eclipse, Xcode
                 custom-agents-config: https://docs.github.com/en/copilot/reference/custom-agents-configuration — aliases `execute` = `shell`/`Bash`, `agent` = `custom-agent`/`Task`; `tools` omitted = all tools
                 skills: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills — "`.github/skills`, `.claude/skills`, or `.agents/skills`" (source for the github-copilot skill-discovery line above)
                 repo-instructions: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions — `.github/copilot-instructions.md`, `.github/instructions/` (`applyTo`), nearest `AGENTS.md`, or root `CLAUDE.md`/`GEMINI.md`
                 note: the `about-cloud-agent` URL on the `github-copilot` line above answers 301 to `…/concepts/copilot-surfaces/copilot-on-github` (measured 2026-10-07)

## typescript / javascript
docs:
  - lang:    https://www.typescriptlang.org/docs/
  - js-ref:  https://developer.mozilla.org/en-US/docs/Web/JavaScript
  - node:    https://nodejs.org/docs/latest/api/
search_hint: "typescript best practices"
version_note: match `engines` in package.json; TS release notes at /docs/handbook/release-notes/

### frameworks
- next.js    docs: https://nextjs.org/docs        llms_txt: https://nextjs.org/docs/llms.txt   search_hint: "next.js app router"
- react      docs: https://react.dev/reference    llms_txt: probe react.dev/llms.txt           search_hint: "react performance patterns"   house_skill (react/next.js only, never this section's kit_skill): .agents/skills/react-best-practices/SKILL.md (React 19 / Next.js 15-16; conventions: .agents/ref/CONVENTIONS_nextjs.md)
- nestjs     docs: https://docs.nestjs.com        search_hint: "nestjs"
- vue/nuxt   docs: https://vuejs.org/guide/ · https://nuxt.com/docs                             search_hint: "nuxt"
- svelte     docs: https://svelte.dev/docs        llms_txt: https://svelte.dev/llms.txt         search_hint: "svelte 5 runes"
- expo/RN    docs: https://docs.expo.dev          search_hint: "react native expo"

## python
docs:
  - lang:    https://docs.python.org/3/            (append /3.12/ etc. to version-match)
  - packaging: https://packaging.python.org
  - typing:  https://typing.readthedocs.io
search_hint: "python best practices"

### frameworks
- django     docs: https://docs.djangoproject.com/en/stable/   search_hint: "django"
- fastapi    docs: https://fastapi.tiangolo.com                search_hint: "fastapi"
- flask      docs: https://flask.palletsprojects.com           search_hint: "flask"
- pytest     docs: https://docs.pytest.org                     search_hint: "pytest testing"

## rust
docs:
  - book:    https://doc.rust-lang.org/book/
  - std:     https://doc.rust-lang.org/std/
  - cargo:   https://doc.rust-lang.org/cargo/
  - clippy:  https://rust-lang.github.io/rust-clippy/master/
search_hint: "rust idiomatic"
version_note: edition in Cargo.toml (`edition = "2021" | "2024"`) changes idioms — always check
conventions: .agents/ref/CONVENTIONS_rust.md

## go
docs:
  - lang:    https://go.dev/doc/
  - std:     https://pkg.go.dev/std
  - effective: https://go.dev/doc/effective_go
search_hint: "golang best practices"
version_note: `go.mod` go directive sets language semantics
kit_skill: .agents/skills/go-idiomatic/SKILL.md

## java / kotlin
docs:
  - java:    https://docs.oracle.com/en/java/javase/25/   (Java 25 target; use the project's declared JDK for other versions)
  - spring-boot-4: https://docs.spring.io/spring-boot/4.1/reference/   (Boot 4.1 line; verify the project's patch)
  - spring-framework-7: https://docs.spring.io/spring-framework/reference/   (Framework 7 line; select the project's patch from the official version menu)
  - spring-security: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
  - archunit: https://www.archunit.org/userguide/html/000_Index.html
  - boot-testcontainers: https://docs.spring.io/spring-boot/4.1/reference/testing/testcontainers.html
  - kotlin:  https://kotlinlang.org/docs/home.html      (language reference, stdlib, idioms)
  - kotlin-coroutines: https://kotlinlang.org/docs/coroutines-guide.html
  - kotlin-kdoc: https://kotlinlang.org/docs/kotlin-doc.html
  - kotlin-api: https://kotlinlang.org/api/core/kotlin-stdlib/
search_hint: "kotlin idioms" | "kotlin coroutines"
version_note: Java 25 is this skill's target, not Boot 4's minimum; check the Java toolchain and Boot plugin or parent version. For Kotlin match `kotlin("jvm")` and `jvmToolchain(N)`; Kotlin release notes at /docs/whatsnew<version>.html
conventions: .agents/ref/CONVENTIONS_java.md (Java and Spring; Kotlin keeps its own language idioms), .agents/ref/CONVENTIONS_kotlin.md
kit_skill: .agents/skills/java-hexagonal-spring/SKILL.md

### build (gradle / maven)
- gradle       docs: https://docs.gradle.org/current/userguide/userguide.html         search_hint: "gradle kotlin dsl"
               kotlin-dsl: https://docs.gradle.org/current/userguide/kotlin_dsl.html
               version-catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html   (`gradle/libs.versions.toml` holds the versions, but it is NOT what SCA reads: `sca-scan.sh` triggers on a root `build.gradle(.kts)` and runs `dependencyCheckAnalyze` through the build)
               wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html   -- always invoke `./gradlew`, never a global `gradle`; the wrapper pins the version the build was verified with
               version_note: `gradle/wrapper/gradle-wrapper.properties` is authoritative; `build.gradle.kts` + `settings.gradle.kts` name the plugins
- maven        docs: https://maven.apache.org/guides/                                   search_hint: "maven"

### frameworks
- spring-boot  docs: https://docs.spring.io/spring-boot/reference/                      search_hint: "spring boot"
               kotlin-support: https://docs.spring.io/spring-boot/reference/features/kotlin.html
               version_note: match the `org.springframework.boot` plugin version in `build.gradle.kts`; migration guides at https://github.com/spring-projects/spring-boot/wiki (Release Notes per version)
- spring-framework docs: https://docs.spring.io/spring-framework/reference/            search_hint: "spring framework"
               kotlin: https://docs.spring.io/spring-framework/reference/languages/kotlin.html
- spring-data  docs: https://docs.spring.io/spring-data/jpa/reference/ (JPA) - https://docs.spring.io/spring-data/relational/reference/ (JDBC/R2DBC)   search_hint: "spring data jpa"
- spring-security docs: https://docs.spring.io/spring-security/reference/              search_hint: "spring security"
- spring-webflux docs: https://docs.spring.io/spring-framework/reference/web/webflux.html   (reactive stack; pairs with Kotlin coroutines via `kotlinx-coroutines-reactor`)
- hibernate    docs: https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html
- flyway / liquibase  docs: https://documentation.red-gate.com/flyway - https://docs.liquibase.com   search_hint: "database migrations"

### testing
- junit5       docs: https://junit.org/junit5/docs/current/user-guide/                  search_hint: "junit 5"
- kotest       docs: https://kotest.io/docs/framework/framework.html                   search_hint: "kotest"
- mockk        docs: https://mockk.io                                                   (Kotlin-first mocking; prefer over Mockito on Kotlin code)
- testcontainers docs: https://java.testcontainers.org                                 search_hint: "testcontainers"
- spring-test  docs: https://docs.spring.io/spring-boot/reference/testing/index.html    (`@SpringBootTest`, slices `@WebMvcTest` / `@DataJpaTest`)

### lint / format
- ktlint       docs: https://pinterest.github.io/ktlint/                                (formatting; Gradle plugin `org.jlleitschuh.gradle.ktlint`)
- detekt       docs: https://detekt.dev/docs/intro                                      (static analysis; rule sets in `detekt.yml`)

## c# / .net
docs:
  - lang:    https://learn.microsoft.com/en-us/dotnet/csharp/
  - runtime: https://learn.microsoft.com/en-us/dotnet/
search_hint: "dotnet best practices"
conventions: .agents/ref/CONVENTIONS_dotnet.md

## ruby
docs:
  - lang:    https://docs.ruby-lang.org/en/
  - rails:   https://guides.rubyonrails.org
search_hint: "rails"
conventions: .agents/ref/CONVENTIONS_ruby.md

## php
docs:
  - lang:    https://www.php.net/docs.php
  - laravel: https://laravel.com/docs
  - symfony: https://symfony.com/doc/current/
search_hint: "laravel" | "symfony"
conventions: .agents/ref/CONVENTIONS_php.md

## swift
docs:
  - lang:    https://www.swift.org/documentation/
  - apple:   https://developer.apple.com/documentation/
search_hint: "swift ios"
conventions: .agents/ref/CONVENTIONS_swift.md

## dart / flutter
docs:
  - dart:    https://dart.dev/guides
  - flutter: https://docs.flutter.dev
search_hint: "flutter"
conventions: .agents/ref/CONVENTIONS_dart.md

## c / c++ / cpp
docs:
  - reference: https://en.cppreference.com/   (200 measured 2026-10-20 ; the older `/w/` path answers 301)
  - core-guidelines: https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines
  - cmake:   https://cmake.org/cmake/help/latest/
  - clang-tidy: https://clang.llvm.org/extra/clang-tidy/
  - gcc:     https://gcc.gnu.org/onlinedocs/
search_hint: "modern c++"
version_note: the language standard is set by the build (`CMAKE_CXX_STANDARD` / `-std=c++20`), not by the compiler version alone — read it before citing a feature
conventions: .agents/ref/CONVENTIONS_cpp.md (C++ only — a pure C tree has no sheet)

## elixir
docs:
  - lang:    https://hexdocs.pm/elixir/
  - phoenix: https://hexdocs.pm/phoenix/
search_hint: "elixir phoenix"

## angular
docs:
  - lang:    https://angular.dev/overview
  - cli:    https://angular.dev/tools/cli
  - workspace-config: https://angular.dev/reference/configs/workspace-config
  - testing: https://angular.dev/guide/testing
  - releases: https://angular.dev/reference/releases
search_hint: "angular"
version_note: read the `@angular/core` major in package.json (20, 21 or 22); builder, test runner and lint target are read in angular.json
conventions: .agents/ref/CONVENTIONS_angular.md (framework layer over CONVENTIONS_typescript.md)
kit_skill: .agents/skills/angular-modern/SKILL.md
upstream_skill: angular/skills#angular-developer   pin=b1eb9a0a5e156a3640b07cfdd86a136abc65f31f   sha256=ec8d1925e160cf524f643880711ea70a706ff9974f66f6718d7651f1be388cc5   (SKILL.md only; audited in AUDIT_LOG; its rules are adopted into kit_skill, never installed — hence absent from ## installed)

## vue / nuxt
docs:
  - vue:    source: à ré-établir — T-00000239
  - nuxt:    source: à ré-établir — T-00000239
search_hint: "nuxt"
kit_skill: .agents/skills/vue-modern/SKILL.md

## terraform / hcl
<!-- T-01M52X1W3WPKCWX1DC36NMKJB6 (lot D) — every root below was OPENED by WebFetch on 2026-10-18 ; a point the opened page does not carry is marked `source: à vérifier`, never filled from memory. registry.terraform.io pages render NO text to WebFetch (measured 2026-10-18) : provider docs were read at their GitHub source, named on the same line. `hcl` is the detector's primary_language for Terraform code, hence the second title segment. -->
docs:
  - root:        https://developer.hashicorp.com/terraform/docs
  - language:    https://developer.hashicorp.com/terraform/language
  - cli:         https://developer.hashicorp.com/terraform/cli
  - style:       https://developer.hashicorp.com/terraform/language/style
  - lock-file:   https://developer.hashicorp.com/terraform/language/files/dependency-lock
  - plan:        https://developer.hashicorp.com/terraform/cli/commands/plan
  - test:        https://developer.hashicorp.com/terraform/cli/commands/test   tests language: https://developer.hashicorp.com/terraform/language/tests
  - automation:  https://developer.hashicorp.com/terraform/tutorials/automation/automate-terraform
  - sensitive:   https://developer.hashicorp.com/terraform/language/manage-sensitive-data
  - backends:    https://developer.hashicorp.com/terraform/language/backend/azurerm   https://developer.hashicorp.com/terraform/language/backend/gcs   https://developer.hashicorp.com/terraform/language/backend/s3
  - mcp-server:  https://developer.hashicorp.com/terraform/mcp-server   (linked from the root ; NOT opened — follow-up of pilot decision Q3 (a) S-01M55NC8AX4K24N96NDNZAEPGA ; the kit ships zero MCP server)
llms_txt: absent (404 mesuré 2026-10-16 ; re-mesuré 2026-10-18 sur https://developer.hashicorp.com/terraform/llms.txt)
registry_api:
  - modules:     https://registry.terraform.io/v1/modules/<namespace>/<name>/<provider>/versions   doc: https://developer.hashicorp.com/terraform/registry/api-docs
  - providers:   https://registry.terraform.io/v1/providers/<namespace>/<type>/versions   doc: https://developer.hashicorp.com/terraform/internals/provider-registry-protocol   note: the page names the path `:namespace/:type/versions` ; the `/v1/providers/` base appears only in its sample request
providers:
  - azurerm:     https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs   read at: https://github.com/hashicorp/terraform-provider-azurerm/tree/main/website/docs/guides (4.0-upgrade-guide, azure_cli, service_principal_oidc)
  - google:      https://registry.terraform.io/providers/hashicorp/google/latest/docs   read at: https://github.com/hashicorp/terraform-provider-google/blob/main/website/docs/guides/provider_reference.html.markdown
  - aws:         https://registry.terraform.io/providers/hashicorp/aws/latest/docs   read at: https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/index.html.markdown
cloud_auth:
  - aws-sso:     https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
  - gcp-adc:     https://docs.cloud.google.com/docs/authentication/provide-credentials-adc   (cloud.google.com redirects there, 301 measured 2026-10-18)
  - gcp-wif:     source: à vérifier — Workload Identity Federation for CI, no page opened
search_hint: "terraform"
version_note: `required_version` and `required_providers` in the `terraform` block, and the provider builds pinned in `.terraform.lock.hcl`, set what applies — read them before citing a version ; provider majors change required arguments (azurerm 4 requires the subscription)
note: hashicorp/agent-skills (Terraform skills) — candidate for an AUDITED /skills-sync only, never copied without the AUDIT_LOG pin — source: à vérifier
conventions: .agents/ref/CONVENTIONS_infra.md (bullets « Terraform: »)
kit_skill: .agents/skills/terraform-deploy/SKILL.md

## databases (cross-language)
- postgres  docs: https://www.postgresql.org/docs/   search_hint: "postgres schema migrations"
- prisma    docs: https://www.prisma.io/docs         search_hint: "prisma"
- supabase  docs: https://supabase.com/docs          search_hint: "supabase"

## cross-cutting skills (any stack — resolver picks at most ONE relevant)
- testing:   search_hint: "test driven development"
- security:  search_hint: "code security review"
- git:       search_hint: "git workflow commits"

## security / SCA tooling
- owasp-dc   docs: https://jeremylong.github.io/DependencyCheck/   search_hint: "dependency check"
             note: NVD refresh needs NVD_API_KEY (free) or a pre-seeded/mirrored DB — air-gapped stays DEGRADED, never a false GO
- npm-audit  docs: https://docs.npmjs.com/cli/commands/npm-audit
- socket     docs: https://docs.socket.dev                          (supply-chain / behavioural layer)
- snyk       docs: https://docs.snyk.io                             (supply-chain, needs network)

## observability (agent tracing)
- langfuse   docs: https://langfuse.com/docs
             claude-code integration: https://langfuse.com/integrations/developer-tools/claude-code
             self-host (docker/k8s helm): https://langfuse.com/self-hosting
             search_hint: "langfuse tracing"
configured: no — run /lang <project> <pk> <sk> <url>

## load testing (k6)
<!-- T-01M4JC50S6CTJ5HJ697929E6N8 — every root below was OPENED on 2026-10-08 ; a point the opened page does not carry is marked `source: à vérifier`, never filled from memory. -->
- k6-docs    docs: https://grafana.com/docs/k6/latest/
             search_hint: "k6 load testing"
- k6-thresholds   docs: https://grafana.com/docs/k6/latest/using-k6/thresholds/
             note: `<aggregation_method> <operator> <value>` ; Counter → count/rate, Rate → rate, Trend → avg/min/max/med/p(N) ; a failed threshold makes k6 exit non-zero
- k6-end-of-test-summary   docs: https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
             end-of-test options: https://grafana.com/docs/k6/latest/results-output/end-of-test/
             note: `handleSummary(data)` returns a `{stdout | stderr | <path>: content}` map ; `--summary-export` is on NEITHER page
             summary-export keys (read by `.agents/bin/loadtest.py`): FLAT form `metrics.http_req_duration["p(95)"]` (ms), `metrics.http_req_failed.value` (ratio 0..1), `metrics.http_reqs.rate` — measured: k6 v2.3.0, 2026-10-08 (darwin/arm64) ; other versions NOT measured
             note: `handleSummary` rend une forme IMBRIQUÉE (`data.metrics.http_req_duration.values["p(95)"]`, `http_req_failed.values.rate`, `http_reqs.values.rate`, mesuré k6 v2.3.0) alors que `--summary-export` est PLATE (`["p(95)"]`, `.value`, `.rate`) : l'adaptateur cloud (T-01M4JC50S6CTJ5HJ697929E6N9) convertit vers la forme plate du protocole `loadtest.py` — re-mesuré 2026-10-08, k6 v2.3.0 darwin/arm64, même run lu des deux côtés ; sur un run de 3 itérations, `vus` et `vus_max` manquaient aux DEUX formes ; conversion générique : `plat = {m: dict(b["values"]) for m, b in data["metrics"].items()}` puis, pour `b["type"] == "rate"`, `value` ← `rate` (mesuré k6 2.3.0 : la forme plate égale `values` pour compteurs, tendances et jauges ; seul `rate` devient `value`) ; `volume` lit `http_reqs.values.count` et `vus_max.values.max` côté `handleSummary`, soit `http_reqs.count` et `vus_max.max` dans la forme plate
- k6-exit-codes   source: à vérifier — rc 99 = seuil franchi, utilisé par loadtest.py (mesuré sur k6 v2.3.0)
             note: the two pages opened on 2026-10-08 (k6-docs root, k6-thresholds) say only « a non-zero exit code » ; rc 99 re-measured 2026-10-08 on k6 v2.3.0 darwin/arm64 (a `checks` threshold crossed, no network) ; any rc outside {0, 99} is read by the runner as DEGRADED, never as a verdict
- k6-cloud-commands   docs: https://grafana.com/docs/grafana-cloud/testing/k6/author-run/use-the-cli/
             note: `k6 cloud run`, `k6 cloud run --local-execution`, `k6 cloud upload` ; the token's env var name is not on the page — source: à vérifier
- azure-container-apps-jobs   docs: https://learn.microsoft.com/azure/container-apps/jobs
             note: manual job → `az containerapp job start --name --resource-group [--yaml <template>]`, history via `az containerapp job execution list` ; the right to START a job reaches its secrets (page § Permissions)
- azure-load-testing-frameworks   docs: https://learn.microsoft.com/azure/app-testing/load-testing/overview-what-is-azure-load-testing
             note: Apache JMeter and Locust ONLY (« does not support other testing frameworks ») — NOT a k6 runner
configured: no — targets live in `.agents/loadtest/targets.json` (adopter-owned ; example `.agents/ref/loadtest-targets.example.json`) ; no secret here, ever

## seo (technical, any stack)
<!-- T-01M5BZC1Y0T36EHTZY9AKZ650F — pointers only, NOT opened by that task (no network allowed on it) : every line below is `source: à vérifier` until a WebFetch opens it ; never fill a point from memory. Consumers: `.agents/skills/seo/SKILL.md`, agent `seo-specialist`, measure `.agents/bin/seo_mesure.py`. -->
- schema-org          docs: https://schema.org/docs/documents.html   types: https://schema.org/<Type>   (the closed subset checked by seo_mesure.py: Organization, WebSite, Article, BlogPosting, Product, BreadcrumbList, FAQPage)
- google-structured-data   intro: https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
             policies: https://developers.google.com/search/docs/appearance/structured-data/sd-policies
             per-type requirements (rich results): https://developers.google.com/search/docs/appearance/structured-data/search-gallery
- google-indexing     robots meta: https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag
             robots.txt: https://developers.google.com/search/docs/crawling-indexing/robots/intro
             canonical: https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
             sitemaps: https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview
             hreflang: https://developers.google.com/search/docs/specialty/international/localized-versions
             title links: https://developers.google.com/search/docs/appearance/title-link
- lighthouse-seo      audits: https://developer.chrome.com/docs/lighthouse/seo/
             note: the kit plays Lighthouse only when the PROJECT installed it (`lighthouse` on the PATH) ; `npx lighthouse` is a network access, never run by the kit
llms_txt: non mesuré
search_hint: "technical seo structured data"
kit_skill: .agents/skills/seo/SKILL.md

## reverse engineering (rea)
<!-- T-01M5HRY5AMXM31WH6PP574BX9R (lot C of T-01M5HEJZ9XVXWQ61XMZYGA3YT0) — NOT a detected stack: a pointer for the `reverse-engineer` agent, which drives the external rea CLI ; its kit skill (`kit_skill:` below) is delivered by T-01M5HEJYSJEYA8K3834FZVT60N. Every upstream root below is pinned to the tag `rea-agents-6.7.0` = commit 27dc42d10249f0410904a75c0997842eb03b931c (tag → commit read on the upstream release page by WebFetch on 2026-10-22), never to the default branch, which moves ; each root was OPENED by WebFetch at that commit on 2026-10-22. -->
docs:
  - repo:          https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c
  - readme:        https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/README.md
  - disclaimer:    https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/DISCLAIMER.md   (lawful analysis of owned or authorised software only)
  - cli:           https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/docs/cli.md   (commands, Evidence, exit codes, engine choice)
  - installation:  https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/docs/installation.md
  - js-apps:       https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/docs/javascript-application-workflows.md
  - apple-apps:    https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/docs/apple-application-analysis.md
  - mcp-contracts: https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/docs/mcp-contracts.md
  - boundary-tests: https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/tests/boundary/cli   (`callerPath*` : `callerPathSymlinkParentCli.test.ts`, the only one at that commit — rea resolves `link/../x` through the link ; the runner refuses every `..` segment)
  - upstream-skill: https://github.com/morluto/rea/tree/27dc42d10249f0410904a75c0997842eb03b931c/.agents/skills/reverse-engineer-anything   (NOT copied into the kit ; the npm package ships it under `skills/`, the repository under `.agents/skills/`)
npm: `rea-agents@6.7.0` — launched ONLY through the kit's runner, `bash .agents/pyrun.sh .agents/bin/rea_run.py …` (pins the version, sets `npm_config_omit=optional` unless `--with-optional` under a traced pilot decision) ; never a direct `npx` of the package, never `rea setup`, never `claude mcp add`
version_note: measured 2026-10-22 in THIS station's npx cache `~/.npm/_npx/a1722018f28f9df2/` (a local cache, not a lockfile the kit ships) : `version` 6.7.0 ; `engines.node` `^22.19.0 || ^24.11.0 || >=26.0.0` ; `optionalDependencies` = frida@17.23.2 only — native binding (99M on disk, `du -sh`), install script `node scripts/install.js` run ; an npx without `omit=optional` installs it, and a cache that already holds it keeps it (this one does). Transitives are NOT pinned by the kit : 174 packages on disk in that cache (lockfile entries present, `rea-agents` included ; `ls node_modules | wc -l` = 159 top-level entries) ; 146 besides `rea-agents` once the 27 optional ones are left out (frida, its 25 optional-only dependencies — `prebuild-install`'s tree, plus `bindings` and `file-uri-to-path` —, the darwin-arm64 build of `@lydell/node-pty`) — counted from that lockfile's `optional` flags, not from a fresh install ; a fresh `npm_config_omit=optional` install measured by the DEFS plan counted 136 (S-01M5HG8ZF5VY9T8DTV9TS86DT0) — that record names no method ; it matches `ls node_modules` units exactly, since this lockfile predicts 136 top-level names for its 147 non-optional entries, `rea-agents` included ; the install itself not replayed here. No SCA of the kit covers them : transitives accepted by pilot decision S-01M5HRWCH5, a security-sca task on them to open after delivery
note: AUDIT_LOG — rea's skills and docs never go through `npx skills add` (gated by `.agents/state/gates/AUDIT_LOG`) : this section only POINTS, no rea skill is vendored under `.agents/skills/vendor/` and none is listed under `## installed`
kit_skill: .agents/skills/reverse-engineering/SKILL.md

---

## installed
<!-- Managed by skills-resolver. Format:
- <id>   hash=<sha256-prefix>   installed=<YYYY-MM-DD>   audit=pass
-->
(none yet — run /skills-sync | $skills-sync)
