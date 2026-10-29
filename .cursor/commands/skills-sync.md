---
description: Detect the stack, then resolve & install best-practice skills from audited GitHub-pinned sources (manual audit + AUDIT_LOG; skills.sh is an OIDC-gated probe that degrades loudly) and refresh official docs pointers. Run on first setup and after adding a new language/framework.
---

Effort: both agents run at their defaults — `language-detector` (`effort: low`, `model: haiku`) and `skills-resolver` (`effort: low`, `model: sonnet`). Detection and audited-install selection (from the GitHub-pinned vendor set, since skills.sh is OIDC-gated) are mechanical; the defaults suffice unless language-detector returns `confidence: low`, in which case rerun it at `model: opus`.

1. Invoke the **language-detector** subagent on the repo root.
2. Feed its JSON to the **skills-resolver** subagent.
3. Show me:
   - skills it proposes to install, each with its security audit verdict
   - skills it refused (and why)
   - the official docs / llms.txt links it resolved
4. STOP for my approval before any install. For a GitHub-pinned fallback candidate the resolver first records the passed audit with `python3 .agents/bin/skills_github_fallback.py audit-log <owner>/<repo>#<skill>@<sha> --pass`, THEN stops — the gate is MACHINE: the fallback refuses with rc 5 until I have myself run `install … --confirmed-by <moi>`. `npx skills add` (the skills.sh path) still stops for my approval on skills with audit=warn and stays audit-gated on `.agents/state/gates/AUDIT_LOG`.
5. After install, confirm DOCS_REGISTRY § installed was updated with hashes.
6. Remind me to restart the Claude Code session so new SKILL.md files are discovered.

- If skills.sh is 401-gated and python .agents/bin/skills_github_fallback.py check --from-detector reports ARM: yes for a detected stack, the resolver searches GitHub, shows each candidate as DATA, and audit-logs the passed ones; the kit ships install_mode confirm, so install refuses with rc 5 unless --confirmed-by <pilote> is passed and the resolver stops after show and lists the exact install command for the pilot, while a project that opted its policy to auto installs at most 2 audited skills per stack at a pinned sha directly; either way it creates the missing DOCS_REGISTRY section through registry ensure-section — candidates and verdicts appear in the report above before any install.

Shared process reference: `.agents/skills/skills-sync/SKILL.md` (Codex/Copilot counterpart — keep the two in sync).
