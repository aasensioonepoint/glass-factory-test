"""Keep the Next 15/16 build split and React routing in the travelling sheets."""

from __future__ import annotations

from pathlib import Path


REF = Path(__file__).resolve().parents[2] / ".agents" / "ref"


def _bullet(text: str, title: str) -> str:
    """Return one named Markdown bullet, including its continuation lines."""
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(f"- **{title}")),
        None,
    )
    assert start is not None, f"missing bullet: {title}"
    end = start + 1
    while end < len(lines) and not lines[end].startswith(("- ", "## ")):
        end += 1
    return " ".join(" ".join(lines[start:end]).split())


def test_next_version_split() -> None:
    next_text = (REF / "CONVENTIONS_nextjs.md").read_text(encoding="utf-8")
    typescript_text = (REF / "CONVENTIONS_typescript.md").read_text(
        encoding="utf-8"
    )
    build = next_text.split("## Build\n", 1)[1].split(
        "## Server / client boundary", 1
    )[0]
    next_15 = _bullet(build, "Next ≤ 15:")
    assert all(
        phrase in next_15
        for phrase in (
            "`next build`",
            "webpack by default",
            "ESLint runs during the build",
            "`next lint` is available",
        )
    ), "Next 15 must describe its default build and lint command"

    next_16 = _bullet(build, "Next ≥ 16:")
    assert all(
        phrase in next_16
        for phrase in (
            "`next dev`",
            "`next build`",
            "Turbopack by default",
            "--webpack",
            "no longer runs lint",
            "`next lint` is removed",
            "ESLint or Biome",
        )
    ), "Next 16 must describe its default build and separate lint step"

    verdict = _bullet(build, "The verdict")
    assert "output of `next build`" in verdict
    agent_files = _bullet(build, "Next ≥ 16.3 agent instructions:")
    assert all(
        phrase in agent_files
        for phrase in (
            "node_modules/next/dist/docs/",
            "agentRules: false",
            "create-next-app --no-agents-md",
        )
    ), "Next agent-file controls and local docs must be named"
    assert "never turbopack" not in next_text.casefold()

    # Exact facts — version, negation, threshold: each had a surviving mutant.
    assert next_15 == (
        "- **Next ≤ 15:** `next build` uses webpack by default; a configured ESLint runs "
        "during the build, and `next lint` is available (deprecated in 15.5). A "
        "Turbopack development render does not prove the webpack production result."
    ), "Next ≤ 15 bullet drifted"
    assert next_16 == (
        "- **Next ≥ 16:** `next dev` and `next build` use Turbopack by default; opt in to "
        "webpack with `--webpack` when the project needs it. `next build` no longer "
        "runs lint, and `next lint` is removed: run the configured ESLint or Biome "
        "script separately. Choose the build command from the installed Next version "
        "and the project's scripts, not from an assumed bundler."
    ), "Next ≥ 16 bullet drifted"
    for wrong in ("still lints", "still runs lint", "agentRules: true", "16.0 agent", "since 16.0"):
        assert wrong not in next_text, f"wrong fact written: {wrong}"
    # 16.3.x also writes CLAUDE.md; 16.4.2 writes AGENTS.md only (sourced).
    assert (
        "`AGENTS.md` (16.3.x: also `CLAUDE.md` — "
        "https://github.com/vercel/next.js/blob/v16.3.0/packages/next/src/server/lib/generate-agent-files.ts ; "
        "16.4.2 writes `AGENTS.md` only — "
        "https://github.com/vercel/next.js/blob/v16.4.2/packages/next/src/server/lib/generate-agent-files.ts )"
    ) in agent_files, "CLAUDE.md scope (16.3.x only) or its source lost"
    assert "`AGENTS.md` or `CLAUDE.md`" not in agent_files

    # C9: preserve all four anchors already used to reach these conventions.
    for anchor in ("webpack", "params", "react-server"):
        assert anchor in next_text, f"Next sheet lost {anchor}"
    assert "CONVENTIONS_nextjs.md" in typescript_text, "TypeScript lost the Next route"


def test_typescript_routes_react_skill() -> None:
    text = (REF / "CONVENTIONS_typescript.md").read_text(encoding="utf-8")
    route = text.split("**React detected → read ", 1)
    assert len(route) == 2, "React routing must be conditional"
    assert route[1].startswith(
        "`.agents/skills/react-best-practices/SKILL.md` as well."
    )
    assert "CONVENTIONS_nextjs.md" in text
    assert "webpack build" not in text.casefold()
    paragraph = " ".join(route[1].split("\n\n", 1)[0].split())
    assert paragraph == (
        "`.agents/skills/react-best-practices/SKILL.md` as well.** The React 19 and "
        "Next 15–16 rules live in that kit skill; route to it only when the detected "
        "stack uses React, so other TypeScript projects keep this base sheet."
    ), "React routing paragraph drifted"
