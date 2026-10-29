---
name: "source-command-docs-sync"
description: "Re-scan docs/tech/ for user-dropped custom docs and sub-skills; analyze relevance and ingest what qualifies. Run after adding or editing files in docs/tech/."
---

# source-command-docs-sync

Use this skill when the user asks to run the migrated source command `docs-sync`.

## Command Template

1. Invoke the **custom-docs-curator** subagent.
2. Show me its verdict table: ingested / promoted / skipped / rejected / stale, with reasons for rejections and stale entries.
3. If any custom skill was promoted to `.agents/skills/<name>/` or `.github/skills/<name>/`, remind me to restart the session so it's discovered.
4. If anything was flagged STALE or REJECTED, ask me whether I want to fix, force-ingest (docs only — never force a security-rejected skill), or delete.

Shared process reference: `.agents/skills/docs-sync/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
