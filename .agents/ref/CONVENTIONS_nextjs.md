# Next.js / React conventions — canonical (shared by Claude Code, Codex, Copilot)

Framework layer on top of `CONVENTIONS_typescript.md`, which stays the
TypeScript/JavaScript base — the rules here are NOT repeated there. Read both.

Every rule states its REASON in one clause: a rule without its reason does not
survive a disagreement. *measured* marks a rule paid for by an incident on a
consumer project — prefer it to a general best practice, and if you measure the
contrary, correct the record rather than working around it in silence. Facts
specific to ONE project (Next version, router flavour, repo layout) belong in a
§2 of that project's own copy, each with its ledger id — not here.

**GUARANTEE — a §2 written by an adopting project SURVIVES a template refresh.**
Same contract as the TypeScript sheet, and for the same reason: an invitation to
write something a later refresh might erase is a trap. §1 belongs to the kit and
is rewritten wholesale by kit-side syncs; §2 belongs to the project and no kit
mechanism ever writes this file inside an adopting project — `sync_template.py`
runs inside the kit repo only and refuses when the local `template/starter-kit`
branch is absent, and docs-sync never touches `.agents/ref/`. A consumer refresh
is a MERGE, never a copy-overwrite (L-015). Honest limit: the external
provisioning tool does not live in this repo, so this pins OUR mechanisms and
states the doctrine that tool must respect. Pinned by
`.agents/evals/test_conventions_contract.py`.

**WHY THIS FILE EXISTS AT ALL** (T-00000162). The agents that serve Next.js —
`frontend-fidelity` and `design-review` — point at the generic
`.agents/ref/CONVENTIONS_<stack>.md`, and `language-detector` emits
`conventions_file: CONVENTIONS_typescript.md` even on a Next project. Without
this sheet those two agents fall back on their habits for EXACTLY the framework
they are meant to serve. The rules below are the highest-value ones left behind
at the consumer during the TypeScript repatriation, generalised.

## Build

- **Next ≤ 15:** `next build` uses webpack by default; a configured ESLint runs
  during the build, and `next lint` is available (deprecated in 15.5). A
  Turbopack development render does not prove the webpack production result.
- **Next ≥ 16:** `next dev` and `next build` use Turbopack by default; opt in to
  webpack with `--webpack` when the project needs it. `next build` no longer
  runs lint, and `next lint` is removed: run the configured ESLint or Biome
  script separately. Choose the build command from the installed Next version
  and the project's scripts, not from an assumed bundler.
- **The verdict is taken on the output of `next build`** *measured*. A screen
  rendered by `next dev` can still fail or differ in the production build;
  check the build actually used by the project before claiming fidelity.
- **Next ≥ 16.3 agent instructions:** read the installed, version-matched docs
  under `node_modules/next/dist/docs/` before changing framework code. `next
  dev` can update its managed block in `AGENTS.md` (16.3.x: also `CLAUDE.md` —
  https://github.com/vercel/next.js/blob/v16.3.0/packages/next/src/server/lib/generate-agent-files.ts ;
  16.4.2 writes `AGENTS.md` only —
  https://github.com/vercel/next.js/blob/v16.4.2/packages/next/src/server/lib/generate-agent-files.ts );
  In a repository equipped with this kit, `AGENTS.md` is the doctrine: set
  `agentRules: false` in Next config.
  For a new project that must omit generated agent files, use
  `create-next-app --no-agents-md` with a release that supports the flag.

## Server / client boundary

- **`params` is a PROMISE in a route handler and in a page (Next 15+)** *measured*.
  `await params` before reading a field. Reading `params.id` directly still
  type-checks in enough setups to reach review, then yields `undefined` at run
  time — a bug that looks like a data problem and is a signature problem.
- Keep the boundary explicit: a component is a Server Component unless it says
  `"use client"`, and that directive is contagious downward. Push it as far down
  the tree as the interactivity actually goes, because everything below it leaves
  the server bundle and lands in the client one.

## Testing

- **The `react-server` export condition splits the suite into TWO runner
  projects** *measured*. React ships different entry points for the server and
  client conditions, so one runner configuration cannot exercise both: a single
  project silently tests one half and reports green for the whole. Configure a
  server project (condition `react-server`) and a client project (jsdom), and
  name which project a test belongs to rather than letting resolution decide.
- Prefer `getByRole` and the accessible name over test ids — see
  `playwright-best-practices` for the locator priority; a test that cannot find a
  control by its role is telling you the control has no accessible name.

## Rendering & data

- Fetch in Server Components and pass data down; a client component that fetches
  on mount pays a round trip the server already made.
- Derive state during render instead of syncing it in an effect — an effect that
  only mirrors props is a re-render you scheduled for nothing. See
  `react-best-practices` for the full rendering rules.
