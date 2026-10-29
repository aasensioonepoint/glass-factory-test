---
description: Re-scan docs/tech/ for user-dropped custom docs and sub-skills; analyze relevance and ingest what qualifies. Run after adding or editing files in docs/tech/.
---

Effort: the **custom-docs-curator** runs at its default (`effort: medium`, `model: sonnet` — read off its own front-matter, not asserted) — its security review of custom skills warrants medium. Bump to `model: opus` if a dropped skill bundles scripts you need read closely; otherwise keep the default. **The bump value is a TIER ALIAS on purpose**: the Agent tool's `model` parameter is a closed enum (`sonnet`, `opus`, `haiku`, `fable`), so a full id such as `claude-opus-5-5` is NOT accepted there — per-invocation overrides cannot be pinned the way a def's front-matter can.

1. Invoke the **custom-docs-curator** subagent.
2. Show me its verdict table: ingested / promoted / skipped / rejected / stale, with reasons for rejections and stale entries.
3. If any custom skill was promoted to `.claude/skills/`, remind me to restart the session so it's discovered.
4. If anything was flagged STALE or REJECTED, ask me whether I want to fix, force-ingest (docs only — never force a security-rejected skill), or delete.

Shared process reference: `.agents/skills/docs-sync/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
