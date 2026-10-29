# docs/tech — your custom knowledge drop zone

Drop extra `.md` docs and custom sub-skills here. The `custom-docs-curator` agent
analyzes each file for relevance to the detected stack, then ingests or skips it —
verdicts land in `.agents/state/index/CUSTOM_DOCS.md`.

## Layout
- `_shared/` — docs valid for every stack (API naming, git rules, review checklists…)
- `<stack>/` — created automatically when a language is detected (e.g. `typescript/`)
  - `*.md` — free-form notes: team conventions, internal API docs, gotchas
  - `skills/<name>/SKILL.md` — custom sub-skills (validated + security-reviewed
    before promotion to `.claude/skills/`)

## Rules
- Relevant files are indexed with a one-line summary; agents read the full file only
  when needed — write a clear title + first paragraph.
- Custom skills bypass skills.sh audits, so they get a manual security review here.
  Skills that fetch remote code or touch credentials are rejected.
- Re-run curation after adding files: `/docs-sync`
