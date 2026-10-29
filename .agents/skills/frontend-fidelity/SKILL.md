---
name: frontend-fidelity
description: Reference numbers and mechanisms for advanced frontend work — Core Web Vitals thresholds, performance budget mechanisms that actually fail a build, WCAG 2.2 AA criteria with their exact ratios, visual-verification tooling with real tolerances and stabilisation levers, and the current-versus-obsolete state of React, Angular and NestJS. Load when implementing or reviewing UI where a number must be cited rather than remembered.
---

# Frontend fidelity — the numbers, and where there are none

This is a reference, not a workflow. The workflow lives in the `frontend-fidelity` agent; the design judgment in `frontend-design`; the stack rules in `.agents/ref/CONVENTIONS_<stack>.md`. Verified 2026-08; every version-dependent claim carries its version.

**Read the honesty section first.** Half the damage an agent does with numbers comes from citing one that was never official.

## Where there is no official number — do not invent one

- **Initial JS weight and request count**: there is NO web.dev standard. The only officially published budget defaults are Angular CLI's, and they are Angular's, not the web's: `initial` warning **500 kb** / error **1 mb**, `anyComponentStyle` **2 kb** / **4 kb**. The frequently quoted "~365 kB of JS" comes from Alex Russell's research, not a specification. For a React app: MEASURE a baseline and set the budget from it, then defend the number as measured rather than standard.
- **LCP and CLS "needs improvement" boundaries**: web.dev/vitals states the GOOD threshold explicitly; the upper bands below are the usual Lighthouse/CrUX ones. The INP article does state all three bands outright.
- **Pagination in NestJS**: no official primitive or convention. Offset versus cursor is a project decision; put it in the OpenAPI spec or the frontend cannot type it.
- **Figma resize constraints through the MCP**: undocumented. Do not bet on how they translate — ask the designer.
- **Percy and Applitools pricing, Figma Dev/Org seat pricing**: not verified here. Check the vendor's own grid before making a budget claim.

## Core Web Vitals — thresholds at the 75th percentile

| Metric | Good | Needs improvement | Poor |
|---|---|---|---|
| **LCP** | ≤ 2.5 s | 2.5 – 4.0 s | > 4.0 s |
| **CLS** | ≤ 0.1 | 0.1 – 0.25 | > 0.25 |
| **INP** | ≤ 200 ms | > 200 – 500 ms | > 500 ms |
| **TTFB** (diagnostic, NOT a Core Web Vital) | ≤ 800 ms | 800 – 1800 ms | > 1800 ms |

INP replaced FID and measures every interaction — input delay plus processing plus presentation — where FID measured only the first input's delay. "Long task > 50 ms" belongs to the Long Tasks API; it is not an INP threshold.

One rule rarely stated and worth more than most tuning: **optimise across a band boundary, not within one.** Moving LCP from 2.8 s to 2.6 s changes nothing that is scored; crossing 2.5 s does. And measure at p75 of real users — a green lab score with a red field INP means the lab is measuring the wrong thing.

## Budgets that actually fail a build

A budget nobody enforces is a comment. These are the mechanisms that break CI:

- **Angular** — `budgets` in `angular.json`: types `bundle · initial · allScript · all · anyComponentStyle · anyScript · any`, fields `maximumWarning`/`maximumError`, units `b/kb/mb/%`. `maximumError` fails the build.
- **size-limit** (`@size-limit/preset-app`) — limits in bytes AND in JS execution time (`"4500 ms"`). `andresz1/size-limit-action` comments the PR and fails on regression.
- **Lighthouse CI** — `budget.json` with `resourceSizes` (in **KiB**), `resourceCounts`, `timings`. Documented limit: `budget.json` cannot assert audit scores; use the `assertions` key in `lighthouserc` for that.
- **Vite/Rollup** — no native budget. Use size-limit or a size check over `dist/`.

## WCAG 2.2 level AA — the criteria custom components fail

| Criterion | Level | Exact requirement |
|---|---|---|
| 1.4.3 Contrast (Minimum) | AA | **4.5:1** normal text; **3:1** large text (≥ 18 pt, or ≥ 14 pt bold) |
| 1.4.11 Non-text Contrast | AA | **3:1** for UI components and meaningful graphics — input borders, state icons |
| 2.4.7 Focus Visible | AA | a mode of operation where the keyboard focus indicator is visible |
| 2.4.13 Focus Appearance | AA | **3:1** against adjacent colours, area at least that of a capital "X" |
| 2.5.8 Target Size (Minimum) | AA | target ≥ **24 × 24 CSS px**, with listed exceptions |
| 2.1.1 Keyboard | A | every function operable by keyboard, no per-keystroke timing |
| 2.4.3 Focus Order | A | tab order preserves meaning and operability |
| 4.1.2 Name, Role, Value | A | programmatically determinable — the classic trap being a `div` with `role="button"`, no accessible name, no key handling |

**The ceiling of the tooling, stated so nobody oversells it:** axe-core reports covering roughly **57%** of WCAG issues automatically. So 43% is out of CI's reach and a fully green report is a floor, not a verdict. `@axe-core/playwright` gives `withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa'])`, `include`/`exclude` (which excludes the element AND its descendants) and `disableRules`. Prefer violation FINGERPRINTS over a full snapshot: a whole-report snapshot breaks on any implementation change and gets disabled. `eslint-plugin-jsx-a11y` is static analysis of JSX and cannot see runtime state — pair it with axe on the rendered DOM.

## Visual verification — what to use, and what each one lies about

| Tool | Detects | False positives | Cost | Verdict |
|---|---|---|---|---|
| **Playwright `toHaveScreenshot`** | pixel diff (YIQ) on a local render; waits for two consecutive identical screenshots; baselines keyed by browser/platform | High OUTSIDE a container — fonts are cause number one. `threshold` defaults to `0.2` (per-pixel colour); `maxDiffPixels` and `maxDiffPixelRatio` have **no default** | Free; cost is Docker discipline and baseline review | **The default floor.** The only one that runs with no account and no network |
| **Chromatic** | cloud render, one snapshot per story; `diffThreshold` default **`.063`**; ignores antialiased pixels by default | Low IF you mock data, freeze dates, disable animations | Free 5 000 snapshots/month, then paid; **1 story × 1 browser × 1 viewport = 1 snapshot** | **Best if Storybook exists.** Budget the breakpoint × theme explosion BEFORE enabling |
| **Percy** | captures the DOM, re-renders server-side at N widths; freezes animations on the first frame | Low by construction — one controlled render environment | Paid | **Strongest on responsive**: one capture, N widths. But you stop testing YOUR browser |
| **Applitools Eyes** | perceptual match levels — `Strict`, `Content`, `Layout`, `Dynamic` (absorbs shifts from dynamic content) | Lowest of the panel | Paid | Justified past a threshold of scale; below it, sophistication paid for what Docker solves |
| **odiff** | pure comparator: YIQ, `threshold`, `antialiasing`, `ignoreRegions`, `failOnLayoutDiff` | Only what you allow | Free | **The right brick** when building your own comparator. No capture, no baselines, no review |
| **BackstopJS** | Puppeteer + ResembleJS, `misMatchThreshold` | High — raw pixel diff, no perceptual filtering | Free | **Do not pick in 2026.** No npm release in ~12 months; Chrome only |

### Mockup-versus-render: the honest answer

The industry compares **render against render**. Every tool above is a REGRESSION detector: it compares your UI to an earlier version of your UI. None takes a mockup as reference.

Direct mockup-versus-render comparison exists, and its measured limit is the point: **even a visually perfect implementation lands at 2–3% pixel difference** from font rendering and antialiasing alone. Two rendering engines, two glyph paths, same font. Add device pixel ratio, a fixed-height Figma frame against a page that reflows, and fractional `line-height`/`letter-spacing` that the browser rounds and Figma does not.

So use three layers, and only one of them is pixels:

1. **Property assertions** — `getComputedStyle` against the token values. Deterministic, zero false positives, and it names WHAT is wrong rather than that something changed. Blocking.
2. **Mockup-versus-render** — consultative score, tolerance ≥ 3%, component scope, attached as an artefact. **Never blocking.**
3. **Render-versus-render** against a committed baseline of your own product. Blocking, because both images come from the same engine.

### Stabilisation levers, each with its exact control

- **One pinned container image**, identical locally and in CI, same Playwright version. This is lever number one: a baseline captured on a developer's machine fails against a Linux runner with no code change.
- `animations: "disabled"` and `caret: "hide"` — already the defaults of `toHaveScreenshot`.
- `mask: [Locator]` (covered with `#FF00FF`, `maskColor` adjustable) and `stylePath` for a stylesheet hiding dynamic elements. Be aggressive: mask everything that moves between runs.
- Freeze the clock, mock API data, fix image fixtures.
- Self-host fonts and await `document.fonts.ready` — an element in the DOM is not an element finished rendering.
- Fix `deviceScaleFactor`/`scale` explicitly. Playwright defaults `scale: "css"`.
- **Narrow scope**: a component capture is far more stable than a full page.

### How these suites die, and the three rules that prevent it

They die of approval fatigue: people stop investigating and approve everything, or disable the tests. So: **never auto-approve a baseline** (it turns a detector into a recorder that always passes); **separate blocking from consultative** (a test that cannot be reliably green has no right to block); and **quarantine flake** — a visual test failing twice with no code change gets a ticket, not tolerance. One chronic red corrupts the signal of every other test.

## React — current versus obsolete (React 19.x, Compiler 1.0 stable)

The **React Compiler** inserts memoisation at build time, replacing hand-written `useMemo`/`useCallback`/`memo`. Verify it is actually applied: the "Memo ✨" badge in DevTools, `react/compiler-runtime` in the build, or `react-compiler-healthcheck`. What it does NOT absolve: it memoises only components and hooks (not a costly utility called outside one), does not share memoisation between components, and does not replace the Rules of React — non-conforming code is simply **not optimised**, silently. `"use no memo"` is an admission of a violation, not a fix. And on existing code, react.dev advises leaving manual memoisation in place rather than stripping it blind: removal changes the compiled output.

Now current: Server Components with a `"use client"` boundary; `"use server"` for Server Functions; Actions with `useActionState` and `useFormStatus`; `useOptimistic` (must be called inside an Action or `startTransition`, auto-rolls back if the action throws); `use(promise)`/`use(context)`, readable after an early return; `useEffectEvent` for reading fresh values without re-subscribing; `<Activity mode="hidden">` to preserve state instead of unmounting; `ref` as an ordinary prop and `<Context value>` — `forwardRef` and `<Context.Provider>` are announced for deprecation; native metadata and `preload`/`preinit`/`preconnect`.

Now false: memoise everything by hand; `React.memo` on list items; `forwardRef`; fetching in `useEffect` (use an async Server Component, or a promise prop with `use()` under `<Suspense>`); an effect to react to a prop; FID as the interactivity metric.

Errors the compiler does not fix, because they are design: an unvirtualised long list (it memoises the render, it does not reduce DOM nodes); state hoisted too high (the re-render is legitimate); one large context (split it); images without dimensions.

**A boundary rule worth its own line:** `"use client"` declares a MODULE GRAPH boundary — everything a client file imports enters the client bundle, though Server Components passed as `children` do not. The most-ignored corollary: keep context providers as DEEP as possible, never wrapped around the document root.

## Angular — current versus obsolete (v22 line; v20/v21/v22 supported)

Signals are the model: `signal`, `computed` (lazy, memoised, dynamic dependencies — an untaken branch creates no dependency), and `linkedSignal` for writable state derived from an input. `effect()` is reserved for NON-reactive APIs — angular.dev is explicit that state propagation belongs to `computed`/`linkedSignal`, never to an effect. `resource()`/`httpResource()` replace manual subscribe plus loading/error flags, exposing `status()` across `idle · loading · reloading · resolved · error · local`.

`input()`, `input.required<T>()`, `output()`, `model()` replace the decorators (`@Input` is legacy, not deprecated; `input.required` is build-checked). Control flow `@if`/`@for`/`@switch` replaces `*ngIf`/`*ngFor`/`ngSwitch`, **deprecated in v21**; `track` is MANDATORY in `@for` and tracking the object itself degrades performance significantly. Standalone components replace NgModules, hard-deprecated in v21.

**Zoneless is the default from v21** and changes what triggers change detection: `NgZone.onStable`/`onUnstable`/`onMicrotaskEmpty` no longer emit and `isStable` always returns `true` — move to `afterNextRender()`/`afterEveryRender()`. Notifications become explicit: a signal read in the template, `markForCheck()`, `ComponentRef.setInput()`, template/host listeners. **And the trap that costs an afternoon: in zoneless, Reactive Forms do NOT trigger change detection on `setValue`/`patchValue`/`FormArray.push`** — wire the observable to `markForCheck()` or move to signals. Signal Forms are stable in v22.

`@defer` with triggers `idle · viewport · interaction · hover · immediate · timer · when`, plus `prefetch` and `@placeholder`/`@loading`/`@error`: only STANDALONE components/directives/pipes are deferrable, and referencing a dependency outside the block cancels the deferral into an eager load. Incremental hydration is stable and on by default with `provideClientHydration()`; `@placeholder` is required for client navigation. On SSR, use `PendingTasks` — without it serialisation runs before async work finishes.

## NestJS as a BFF for a frontend (Nest 11, Node ≥ 20)

`FastifyAdapter` over Express where throughput matters — the docs claim nearly 2× on benchmarks — with real caveats: Express-dependent recipes break, middleware receives raw `req`/`res`, and `listen('0.0.0.0')` is required since Fastify binds `127.0.0.1` by default.

Global `ValidationPipe` with **`whitelist: true` + `forbidNonWhitelisted: true` + `transform: true`**: whitelist strips undecorated properties, `forbidNonWhitelisted` REJECTS instead of silently stripping (silent stripping is how mass assignment hides), transform converts string params.

The frontend contract is the load-bearing part. Enable the `@nestjs/swagger` CLI plugin (`compilerOptions.plugins` in `nest-cli.json`) so DTO types, required-ness and class-validator rules land in the spec without hand-written decorators — note it only analyses files matching `dtoFileNameSuffix` (`.dto.ts`, `.entity.ts`). Then generate the frontend types from that spec — `openapi-typescript` for types only, Orval for a client with React Query/Zod/mocks — and **make the spec a CI artefact: regenerate and fail the build if the diff is not committed.** That check is the only thing that stops the contract drifting; hand-written frontend duplicates of a DTO drift silently and surface as an `undefined` in production that the types swore was present.

Errors: `HttpException` and its subclasses, default shape `{ statusCode, message }`, `ExceptionFilter` with `@Catch()` scoped per method/controller/global. Built-in exceptions inherit `IntrinsicException` and are therefore **not logged by default** — a custom filter is needed to log them. Document the error shape in the OpenAPI spec or the frontend cannot type failure. Cache via `@nestjs/cache-manager`: **TTL in milliseconds**, default `0` meaning no expiry, GET endpoints only, incompatible with an injected `@Res()`.

## Anti-pattern → observable symptom

| Anti-pattern | What you will observe |
|---|---|
| Derived state duplicated (`useState` + effect to recompute; a signal written from another signal) | An intermediate render shows the stale value; two sources diverge after a network error |
| An effect that SYNCHRONISES state | Change-detection loops, a visible value flash, dependencies added then removed to silence it |
| `any` / `as unknown as` on a network boundary | A renamed backend field breaks nothing at compile time and everything at runtime |
| Hand-written frontend types duplicating a DTO | Spec and client drift silently; an `undefined` in production the types guaranteed |
| Hardcoded style values instead of tokens | Dark theme partially applied; contrast passing on one page and failing on another |
| Direct DOM access in a reactive framework | Hydration mismatch; in zoneless Angular no change detection fires so the screen simply does not move |
| `@for` without correct `track` | The list's DOM is rebuilt on every change; focus and input state lost inside rows |
| Unvirtualised long list | INP > 500 ms on click; the profile is dominated by layout, not application JS |
| One large React context | The whole app re-renders on one field change; the compiler changes nothing |
| Images without `width`/`height` or `aspect-ratio` | CLS > 0.1 at p75 |
| `ValidationPipe` without whitelist/forbidNonWhitelisted | Unexpected fields silently accepted — mass assignment |
| Tests asserting implementation (hook names, call order, full axe snapshot) | A behaviour-preserving refactor breaks the suite, so the suite gets disabled |
| Counting on axe alone to declare "accessible" | 43% of criteria uncovered; a fully green component still unusable by keyboard |
| An unmeasured performance budget in a checklist | It LOOKS like a gate and stops nothing — worse than no budget |

## The design-review grid, played by the dev

Pilot decision S-01M5N24P2Y0SH6S0W0YNG3TAN6. Before handing back, `frontend-fidelity` plays the eight phases of `design-review` (`.claude/agents/design-review.md` § Phases), in that order, on every width and state the plan's `INTERACTION:` line declares, and reports them under `GRID:`, one line per phase: `- <phase>: <evidence> | not checked: <why>`. The titles below are EQUAL to design-review's; `.agents/evals/test_grille_dev_ecran.py` turns red when one drifts, is dropped or is reordered.

1. **Primary flow.** — the task done end to end, keyboard only included; the unreachable control named.
2. **Responsive.** — each declared width (`largeurs=`), overflow and tap targets under 24×24 CSS px measured.
3. **States.** — each declared state (`etats=`), plus hover, focus-visible, disabled, error, loading, empty, dark mode, reduced motion, forced colours; an invented state said as such.
4. **Visual fidelity.** — against the mockup when one exists, the kind of difference named; `no mockup:` writes `not checked: no mockup`.
5. **Accessibility, normatively.** — the declared criteria (`wcag=`), contrast and focus ratios measured, the axe run per width, focus order and Escape (`focus=`, `echap=`, `modal=`, `empilement=`) by keyboard.
6. **Robustness.** — long text, an empty list, a dead or slow network, broken on purpose.
7. **Code health, narrowly.** — tokens over hardcoded values, no duplicated derived state, no direct DOM access, images with dimensions.
8. **Console and network.** — errors, warnings and failed requests on each path played.

`GRID:` is evidence, never a verdict: `design-review` still runs after the dev, and a phase the dev could not reach stays `not checked: <why>`, never silent.

## A plan that touches the screen names its mockup — repatriated from the router (P4)

Moved VERBATIM out of `AGENTS.md` so the router can stay thin. The router keeps the
invariant and points here. `plan-critic` REFUSES a screen plan that omits the line.

**A SCREEN PLAN ALSO CARRIES ITS INTERACTION SPEC** (pilot decision S-01M5N24P2Y0SH6S0W0YNG3TAN6). Beside its mockup line, a screen plan carries `INTERACTION: focus=<…> ; echap=<…> ; modal=<…> ; empilement=<…> ; wcag=<…> ; largeurs=<…> ; etats=<…>` — seven keys, in this order — or `INTERACTION: sans objet | <motif>`. Two UI checks block a screen plan: the mockup line and the INTERACTION line. `frontend-fidelity` applies the line at its step 0 and RETURNS to the parent any arbitration it does not cover; it never decides one in code. The three mockup values below stay exactly as they are.

**A PLAN THAT TOUCHES THE SCREEN NAMES ITS MOCKUP, OR DECLARES ITS ABSENCE.** Any plan touching a page, a component of the design system, or any surface a user sees carries exactly one of three CLOSED values, and `plan-critic` REFUSES a screen plan that omits the line:

- `mockup: <path or node URL>` — the reference to reproduce.
- `no mockup: <reason>` — legitimate and measured. A shared state, an error page, an internal tool may genuinely have none, and a plan is RIGHT to produce no fidelity score when there is nothing to compute it against. The strongest form of this value does not ASSERT the absence, it CITES it: where the project keeps an inventory of its design sources, the plan points at the line that already records the gap. The rule forces the QUESTION, never the invention of a mockup that does not exist.
- `mockup not reproduced: <path> + <task that will take it up>` — the assumed, named debt. Without this third value the rule becomes a lie the first day everything cannot be done at once; and the task named must EXIST on the board, or the debt is a wish.

**Where a design source EXISTS, using it is not optional.** If the project carries a mockup directory, a Figma node, a Stitch project or any exported design reference, a front-end task reproduces it — it does not reinvent it. A dev agent that starts a screen without knowing WHICH page or mockup it is implementing ASKS, and never infers from the code around it: the surrounding code is what the mockup is supposed to correct.

This paragraph is a repatriation, and the incident that produced it is the argument. On a consumer project a login screen shipped with its mockup sitting in the repo — `code.html` and `screen.png`, both committed — and nobody opened it: four hardcoded style values, a single design-system import, and no stage of the pipeline asked the question, because no plan ever had to name it. A guard nobody is obliged to invoke is a guard that does not exist.

## Détail déplacé d'AGENTS.md (T-00000838)

Instantané mot pour mot de `git show ec31545c:AGENTS.md` § Golden rules (règle UI et règle du mockup), retiré du routeur chargé à chaque session ; l'invariant court reste dans `AGENTS.md`. Seul amendement depuis l'instantané : la ligne INTERACTION, deuxième contrôle UI qui bloque (S-01M5N24P2Y0SH6S0W0YNG3TAN6).

**On a UI task the dev slot is `frontend-fidelity`, and `design-review` runs after it, before the human gate** — same shape as `planner`→`plan-critic`, and for the same reason: the agent that implemented a screen reads its own intention into what it sees, so it cannot be the one certifying fidelity. A UI task is any task carrying a mockup or asking for visual work. → `.agents/skills/frontend-fidelity/SKILL.md`

**Un plan qui touche l’écran NOMME SON MOCKUP ou DÉCLARE SON ABSENCE** — trois valeurs fermées et une seule s’applique : `mockup: <chemin ou nœud>`, `no mockup: <raison>`, ou `mockup not reproduced: <chemin> + <tâche qui le reprendra>` (et cette tâche doit EXISTER au board, sinon la dette est un souhait). `plan-critic` **REFUSE** un plan d’écran qui omet la ligne : c’est l’un des deux contrôles UI qui bloquent, la ligne mockup et la ligne INTERACTION. Le plan d’écran porte aussi `INTERACTION: focus=<…> ; echap=<…> ; modal=<…> ; empilement=<…> ; wcag=<…> ; largeurs=<…> ; etats=<…>` ou `INTERACTION: sans objet | <motif>` (S-01M5N24P2Y0SH6S0W0YNG3TAN6) ; `frontend-fidelity` l’applique et rend au parent tout arbitrage qu’elle ne couvre pas. Et là où une source de design EXISTE, on la reproduit — on ne la réinvente pas. → détail : `.agents/skills/frontend-fidelity/SKILL.md`
