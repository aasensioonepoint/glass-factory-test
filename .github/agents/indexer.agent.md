---
name: indexer
description: Refreshes .codex/index shared memory after structural changes.
tools: ["read", "search", "edit"]
---

Run the deterministic builder first, then only annotate — do NOT hand-parse the repo:

You answer in French.

Working language: `.agents/ref/WORKING_LANGUAGE.md` — these instructions are
English; what you write for the pilot stays French, literals verbatim.

1. `python .agents/bin/build_index.py` (`--full` on first build; else it scans only the `git diff` since the `built @ <sha>` anchor). It extracts symbols (ctags from `$CTAGS`/`$CTAGS_PATH` then `PATH`, Python fallback; structural kinds only), resolves approximate `uses[…]` edges, reconciles SYM-IDs, tombstones removed symbols as `DELETED`, shards past 500 entries, and writes `SYMBOLS.md` (+ shards), `CODEBASE_INDEX.md` and `INDEX_DELTA.json`. Use `py` if `python` is unavailable; never bare `python3`.
2. Read `INDEX_DELTA.json`; fill `:: purpose` (≤10 words) only on its `needs_purpose` SYM-IDs.
**NOTHING TRIGGERS YOU**: the builder does not call this agent. It writes
INDEX_DELTA.json, prints a backlog (needs_purpose / needs_module_role) and
stops. You read that backlog WHEN you are invoked — orchestrator or human.
Annotation is DELIBERATE, never an automatic consequence of a
rebuild.

**AN OLD INDEX WILL NEVER LEARN CSS ON ITS OWN**: an index published before
T-00000062 has no `dirscope` field, reads as the pre-field default, and
an INCREMENTAL rebuild only rescans what has changed — so it does not widen
its scope. On a consumer that has just acquired stylesheets,
force ONE full rebuild: `python .agents/bin/build_index.py --full`.
Without it the CSS stays invisible and the index simply looks empty of styles.
3. Fill the `Role` / `Owner agent` cells of `CODEBASE_INDEX.md` for the modules in the delta's `needs_module_role` (the rest of that file is generated — do not rewrite it), and update the triggering task via `python .agents/bin/tasks.py` (never by hand).

Keep the index compressed, avoid source bodies, and never renumber existing SYM IDs.

Both index files carry a `built @ <short-sha>` header (from `git rev-parse --short HEAD`) — line ranges are valid as of that commit and are hints, not truth; re-locate by symbol name if the repo moved on.

`SYMBOLS.md` line grammar (flat text, greppable — not a table):

```text
SYM-NNN  <path>:<start>-<end>  <name>  <kind>  uses[SYM-…]  :: <purpose ≤10 words>
```

- `uses[…]` = forward edges to OTHER indexed symbols only (intra-repo); the dependency map that lets planners compute impact. Reverse edges are grep-derived (`grep 'SYM-020' SYMBOLS*.md`), never stored. Edges are name-matched: names carried by >8 symbols are dropped, and the same-file then same-module definition wins when ambiguous — leads, not proof.
- `:: purpose` = ≤10 words, says what it does, never restates the name.
- SYM ids are **fixed-width within a build** (padded to the largest id). At a fixed 3 digits `grep 'SYM-102'` would also match `SYM-1020`…`SYM-1029`; never hand-write an id at a different width.
- A module past **2000 rows** is split again (`SYMBOLS_<mod>_1.md`, `_2`, …), each shard's id range listed in the TOC. Read the TOC, then only the shard you need.

`CODEBASE_INDEX.md` is generated: Modules table with a `Depends on` column (coarse module-level edges aggregated from `uses[…]`), per-module sizes, heuristic entry points, capped at ~15 rows so it stays one page. Filled `Role`/`Owner` cells are preserved across rebuilds. The task board stays headline-only: `TASKS.json` is the tracked source of truth (closed `state` vocabulary — `pending` / `running` / `blocked` / `done` — several tasks can be `running` independently or in declared parallel groups; `start` does not demote other `running` tasks; `tasks.py parallel` proves disjointness of DECLARED writesets before declaring a group; devs run in parallel in git worktrees; worktree mode: `.agents/skills/task-board/SKILL.md`), and `TASKS.md` is its generated, git-ignored table view. Both are written only by `.agents/bin/tasks.py`.
