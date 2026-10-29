# Deterministic, incremental index build — design

Date: 2026-07-20
Status: implemented (`.agents/bin/build_index.py`)

## Problem

`/index` invoked a single `indexer` subagent that did a full LLM-driven pass over
the repo and rewrote `CODEBASE_INDEX.md` from scratch. That does not scale: on a
~500k-LOC repo a single-agent full pass blows the context/time budget, and the
`uses[…]` dependency edges in the schema need real static analysis to be accurate.

## Approach

Move the heavy work to a **deterministic, no-LLM** script, `build_index.py`. The
`indexer` agent's LLM role shrinks to annotating `:: purpose` on the bounded delta.

- **Extractor** — `universal-ctags` when present (100+ languages, offline, one
  binary), stdlib fallback otherwise (`ast` for `.py`, regex + brace-matching for
  `.ts/.js`). Portable / air-gap friendly; no hard dependency.
- **Edges (`uses[…]`)** — approximate: identifiers in a symbol's body that match
  another known symbol name become forward edges (cap 6), flagged APPROXIMATE in
  the header (misses aliasing / dynamic dispatch). Reverse edges stay grep-derived.
- **Incremental** — re-scan only files changed since the `built @ <sha>` anchor
  (`git diff` + working-tree + untracked); `--full` forces a complete rebuild.
  Non-git trees fall back to a filesystem walk.

## Pipeline

1. **scope** — changed source files (incremental) or all tracked source (full).
2. **extract** — ctags or fallback → `{path, start, end, name, kind}`.
3. **reconcile IDs** — key `(path, name, kind)` against existing SYMBOLS; reuse
   SYM-IDs, never renumber, tombstone removed as `DELETED`, preserve `:: purpose`.
4. **edges** — recompute `uses[…]` for re-extracted symbols against the global
   name→id map (preserved symbols keep stored edges).
5. **shard** — group by top-level module; past `--threshold` (default 500) write
   `SYMBOLS_<module>.md` shards + `SYMBOLS.md` index-of-indexes. Stamp `built @ <sha>`.
6. **emit delta** — `INDEX_DELTA.json`: counts, `added/removed/changed`, and
   `needs_purpose` (new symbols with no blurb).

`indexer` agent (reduced): run the script, read `INDEX_DELTA.json`, annotate
`:: purpose` only on `needs_purpose`, regenerate `CODEBASE_INDEX.md` (modules +
`Depends on` aggregated from edges). `/index` and the host mirrors point at the script.

## How it seeds points 2 & 3

The per-module grouping the script emits is reused by the fan-out layer (parallelise
dev/audit by module) and the iterative global audit (loop over the same grouping).

## Testing

`build_index.test.sh`: temp git repo with a `.py` + `.ts` fixture → extraction,
kinds, resolved edges, `built @ <sha>` header, stable SYM-IDs across re-runs,
`DELETED` tombstones, sharding past the threshold, incremental scope, fallback path.

## Out of scope (v1)

Accurate call-graph edges (LSP/tree-sitter), cross-file edge refresh for unchanged
files, and languages with neither ctags nor a stdlib fallback (symbols only, no edges).
