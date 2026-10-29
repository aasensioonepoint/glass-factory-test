---
name: "source-command-index"
description: "Refresh the codebase index (CODEBASE_INDEX, SYMBOLS). Run after major refactors."
---

# source-command-index

Use this skill when the user asks to run the migrated source command `index`.

## Command Template

1. If `.agents/state/index/CODEBASE_INDEX.md` is missing or lacks a `## Stack` section, invoke the **language-detector** subagent FIRST — the indexer builds its Stack section from that snapshot. Pass its JSON to the indexer.
2. Invoke the **indexer** subagent — it runs the deterministic builder
   (`.agents/bin/build_index.py`; pass `--full` on the first build or after a
   large refactor, otherwise it scans only the `git diff` since the `built @ <sha>`
   anchor) and then only annotates the `:: purpose` blurbs on the delta. Do not do
   the extraction in the main context.
   - `--if-stale` skips the write entirely when a rebuild would produce the
     same files (prints `INDEX CURRENT`, exit 0) — this is also what the
     SessionStart hooks and the post-security-gate pipeline step run, 0 LLM.
   - `--stale-check` is the read-only probe (prints `INDEX CURRENT` or
     `INDEX STALE`, writes nothing, always exit 0) — the Stop-hook nudge's
     signal, so nudge and refresh share one staleness definition (T-00000033).
   - Exit 1 has two distinguishable marker lines, not codes (a Stop hook must
     never see exit 2 — it would loop the host): `FAILED mid-publish, index
     files are mixed-generation; re-run to converge` (a build died after its
     first artefact write — re-run converges it) and `identity source lost`
     (`SYMBOLS.md` is missing/unparseable but shards exist — restore it,
     delete the shards, or pass `--full` deliberately).
3. If a stack was detected in step 1 and it is absent from `DOCS_REGISTRY.md § installed`, remind me to run `$skills-sync` (never install from here — the audit gate lives in that workflow).
4. If the advisory SQLite store `index.db` exists — MACHINE state, outside the repository, `state_project()/index/index.db` (T-00000668; `migrate_index_to_db.py --check` says `db present` or `absent`) — the rebuild just left it a generation behind: the indexer resyncs it (`migrate_index_to_db.py --resync`; nothing to commit but `annotations_log.jsonl` if it moved) and it is queried — never with raw SQL — through `python .agents/bin/symbols.py query …`, the agent-facing CLI that also walks `edges` both ways (`--callers` / `--callees`) and refuses on a stale store with `--strict`.

After it returns:
- Show me a one-line summary of the diff.
- If HEAVY DIFF, remind me to re-read `CODEBASE_INDEX.md` at the start of next session.

Shared process reference: `.agents/skills/index/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
