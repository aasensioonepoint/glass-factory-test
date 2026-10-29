---
name: index
description: Refresh the shared codebase index in .agents/state/index. Use after structural changes, first setup, or when the index is stale.
---

# Index Workflow

Build or refresh the compressed project memory used by Codex and Copilot.

## Outputs

- `.agents/state/index/CODEBASE_INDEX.md`
- `.agents/state/index/SYMBOLS.md`
- `.agents/state/index/INDEX_DELTA.json`
- `.agents/state/index/INDEX_BODIES.json` — one `body_sha` per live symbol, in a
  LATERAL file (never a field on the `SYM-NNN` row, which no existing reader
  could parse). Believed whole or not at all: its `generation` must equal the
  index files' `built @` stamp, and a mismatch makes the whole map unknown and
  forces exactly one full rebuild.
- the board (`.agents/state/board/TASKS.json`, or the record files under `.agents/state/board/tasks/`) (+ generated `TASKS.md` view)

## Process

0. If `CODEBASE_INDEX.md` is missing or lacks a `## Stack` section, run language
   detection first (the host's language-detector agent, or manifest inspection)
   — the index's Stack section is built from that snapshot. If the detected
   stack is absent from `DOCS_REGISTRY.md § installed`, suggest the skills-sync
   workflow afterwards (never install from here — the audit gate lives there).
1. **Run the deterministic builder** — `python .agents/bin/build_index.py`
   (`--full` on first build; else it scans only the `git diff` since the
   `built @ <short-sha>` anchor). It extracts symbols (ctags, Python fallback for
   `.py`/`.ts`/`.js`), resolves approximate `uses[…]` edges, reconciles SYM-IDs,
   tombstones removed symbols as `DELETED`, shards past 500 entries, and writes
   `SYMBOLS.md` (+ shards), `INDEX_DELTA.json` and `INDEX_BODIES.json`. Then fill `:: purpose` (≤10 words)
   only on the `needs_purpose` SYM-IDs it lists. Only if the builder can't run on
   your host, extract manually per the grammar in step 4.
   - `--if-stale` skips the write when **NO INDEXED FILE changed** since the
     `built @` anchor (prints `INDEX CURRENT`, exit 0, 0 LLM) — the flag the
     SessionStart hooks and the post-security-gate pipeline step both run. It
     does **not** compare `built @` to HEAD: since T-00000575 HEAD may be
     arbitrarily far ahead, because 62 % of commits touch no indexed file and
     each one used to force a rebuild that dirtied the tree and called for a
     commit of its own. **BORNE, dite plutôt que découverte** — ce n'est donc
     PAS « quand une reconstruction produirait les mêmes fichiers » : un upgrade
     du BUILDER lui-même (ses règles d'exclusion, sa taille limite, un
     extracteur) n'entre dans aucune empreinte, et sur un dépôt ADOPTANT — où
     `.agents/` est hors périmètre — il n'atterrit jamais par ce chemin.
     `--full` est le seul rattrapage, et l'empreinte qui fermerait ce trou est
     portée par une tâche à part.
   - Exit 1 is distinguished by its stdout marker line, never by the code
     itself: `FAILED mid-publish, index files are mixed-generation; re-run to
     converge` (re-run converges it) vs. `identity source lost` (`SYMBOLS.md`
     missing/unparseable with shards still present — restore it, delete the
     shards, or pass `--full` deliberately, accepting dangling SYM-ID citations).
2. Detect manifests and entry points using search/glob tools; note intra-repo edges the builder may have missed on unsupported languages.
3. Keep `CODEBASE_INDEX.md` to one screen. Its Modules table carries a `Depends on` column (coarse module-level edges); collapse leaf dirs and shard large domains instead of spilling past ~15 rows.
4. Record addressable symbols in `SYMBOLS.md` (flat, greppable text — not a table):

   ```text
   # grammar: SYM-NNN  <path>:<start>-<end>  <name>  <kind>  uses[SYM-…]  :: <purpose ≤10 words>
   SYM-001  src/path/file.ts:12-40  symbolName()  export  uses[SYM-005]  :: what it does, ≤10 words
   ```

   - `uses[…]` = forward edges to OTHER indexed symbols only (intra-repo) — the dependency map for impact analysis. Reverse edges are grep-derived (`grep 'SYM-005' SYMBOLS.md`), never stored.
   - `:: purpose` = ≤10 words, says what it does, never restates the name.

5. Keep the task board headline-only. the board (`TASKS.json` or its record files) is the tracked source of
   truth, one object per task; `TASKS.md` is a generated, git-ignored table view:

   ```json
   {"id": "T-001", "state": "running", "task": "Short title",
    "owner": "planner", "stage": "planner", "updated": "2026-07-22"}
   ```

   `state` is a CLOSED vocabulary (`pending` / `running` / `blocked` / `done`);
   several tasks may be `running` independently or in a group. `tasks.py parallel`
   assigns a group after proving DECLARED write-sets disjoint. Devs use git
   worktrees, one active session per clone (worktree mode: `.agents/skills/task-board/SKILL.md`). Write it ONLY through
   `python .agents/bin/tasks.py` (`new` / `start` / `stage` / `block` /
   `unblock` / `done` / `regroup` / `writeset` / `parallel` / `render`), never by hand.

6. If the machine carries the advisory SQLite store `index.db` — MACHINE state,
   outside the repository, `state_project()/index/index.db` (T-00000668;
   `python .agents/bin/migrate_index_to_db.py --check` says `db present` or
   `absent`) — query it with `python .agents/bin/symbols.py query …` instead of
   grepping the shards (it also walks `edges` both ways: `--callers` /
   `--callees`), and bring it back in line after a rebuild with
   `migrate_index_to_db.py --resync`. Nothing to commit: only
   `annotations_log.jsonl`, if it moved. Raw SQL is forbidden; a `!! DB STALE`
   banner means the answer is another generation's.

## Rules

- Do not paste source bodies into the index.
- Do not renumber existing symbols. Mark removed entries as `DELETED`. Refresh `uses[…]` on symbols whose edges changed.
- A `path:start-end` range is a hint valid as of the header sha — if the repo moved on and the file changed, re-locate by symbol name (grep) before trusting it.
- Include do-not-touch paths from `AGENTS.md`.
- If the repository is polyglot, list each stack and mark the primary stack by current task scope.
