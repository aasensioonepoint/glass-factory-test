# Angular 20-22 conventions — framework layer (shared by Claude Code, Codex, Copilot)

Framework layer on top of `.agents/ref/CONVENTIONS_typescript.md`, which stays the
TypeScript/JavaScript base: its rules are NOT repeated here. Read both. The code
rules (signals, `inject()`, control flow, zoneless, OnPush, the v20/v21/v22 table)
live in `.agents/skills/angular-modern/SKILL.md`; the official roots and the
audited upstream pin live in the `## angular` section of `.agents/ref/DOCS_REGISTRY.md`.

This sheet decides one thing: WHICH command verifies an Angular project. Every
answer is read from the project's own `package.json` and `angular.json`, never
assumed, because two Angular projects of the same major can use a different
package manager, builder and test runner — and a command guessed from the
habit of another project passes nowhere or tests nothing.

## Version

- Read the major of `@angular/core` in `package.json` before applying any
  version-specific rule; the skill's table says what changes between 20, 21
  and 22 — https://angular.dev/reference/releases .
- AngularJS (`angular` without `@angular/core`) is a different framework: this
  sheet does not apply to it.

## Package manager

- First read the lockfile beside `package.json`. When there are several,
  apply the language detector's precedence: `bun.lockb` > `pnpm-lock.yaml` >
  `yarn.lock` > `package-lock.json`.
- Then read the `packageManager` field of `package.json`.
- The detector reads neither `bun.lock` nor `cli.packageManager` in
  `angular.json` — https://angular.dev/reference/configs/workspace-config .
  When it emits `unknown`, these two sources decide, in that order (`bun.lock`,
  then `cli.packageManager`), and the report says which one did. When the
  sources disagree, say so in the report and follow the one read first.
- None of these present: the package manager is unknown. Say so in the
  report; do not install, and do not pick one by habit, because a second
  lockfile written by the wrong tool is a change the project never asked for.
- Run the CLI through that package manager's script runner (`npm run`,
  `pnpm`, `yarn`, `bun run`) or the project's `scripts`, not a globally
  installed `ng`, whose version can differ from the one the project pins.
  With npm, the CLI's flags go after `--`: `npm run ng -- test --watch=false`.
  Measured with npm 11: without `--`, npm keeps the flag for itself and Karma
  stays in watch mode.

## Build

- Read `projects.<name>.architect.build.builder` in `angular.json`.
  `@angular/build:application` is the esbuild-based application builder; the
  webpack `@angular-devkit/build-angular:browser` builder is deprecated —
  https://angular.dev/tools/cli/build-system-migration . Keep the builder the
  project declares; a migration is its own task.
- Verify with `ng build`; the verdict is taken on the build the project
  declares, not on `ng serve` — https://angular.dev/cli/build .

## Tests

- Read `projects.<name>.architect.test` in `angular.json`: its `builder`, and
  for `@angular/build:unit-test` its `options.runner`.
- `@angular/build:unit-test` runs `options.runner` when it is set (`vitest` or
  `karma`). When the option is absent: from v21 the default runner is Vitest;
  in v20 `runner` is required by the builder schema, so its absence is a broken
  configuration to report, not a default to guess
  — https://angular.dev/guide/testing .
- `@angular/build:karma` and `@angular-devkit/build-angular:karma` run Karma —
  https://angular.dev/guide/testing/karma . Keep the runner the project
  declares; never rewrite a Karma suite for Vitest inside an unrelated task.
- Run `ng test --watch=false`: `ng test` watches by default, and an agent
  waiting on a watcher never gets an exit code — https://angular.dev/cli/test .
- Karma in CI: add `--no-watch --no-progress --browsers=ChromeHeadless` —
  https://angular.dev/guide/testing/karma .
- No `test` target: report its absence; do not invent one.

## Lint

- Run `ng lint` only if `angular.json` declares a `lint` target for the
  project. The CLI ships no linter of its own: a package added by `ng add`
  provides the `lint` builder, and adding it is a dependency change, not a
  verification — https://angular.dev/cli/lint .
- No `lint` target: say lint was not run and why; run the project's own lint
  script from `package.json` if one exists.
