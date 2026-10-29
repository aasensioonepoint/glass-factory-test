"""Keep the module convention rule on both Codex and Copilot surfaces."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


ROOT = Path(os.environ.get("MODULE_DOCTRINE_ROOT", Path(__file__).resolve().parents[2]))
DOCS = ("AGENTS.md", ".github/copilot-instructions.md")
HOST_DEFS = (".codex/agents/dev-mono.toml", ".github/agents/dev-mono.agent.md")


@pytest.mark.parametrize("relative_path", DOCS)
def test_module_choice_and_root_fallback(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    for rule in (
        "`modules[]`",
        "longest directory prefix",
        "if none matches, use the root `conventions_file` and `test_runner`",
        # Aligned with dev-mono: segments, with or without a trailing separator
        # (the detector emits `frontend`), and a field absent from the chosen
        # entry falls back to the root one.
        "compared by whole path segments, whether `path` ends with a separator or not",
        "`frontend` and `frontend/` both own `frontend/src/a.ts`, never `frontend-old/src/a.ts`",
        "a field absent from the selected entry takes the root value",
    ):
        assert rule in text, f"{relative_path}: missing module rule {rule}"
    for stale in (
        "not the root values when a module matches",
        "must end at a path separator",
    ):
        assert stale not in text, f"{relative_path}: stale module rule {stale}"


@pytest.mark.parametrize("relative_path", DOCS)
def test_absent_sheet_has_an_explicit_module_fallback(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    for rule in ("`null`", "stack skill", "selected `registry_sections`"):
        assert rule in text, f"{relative_path}: missing absent-sheet rule {rule}"
    announcement = (
        "the dev agent that falls back on them says so"
        if relative_path == "AGENTS.md"
        else "say so, never fall back silently"
    )
    assert announcement in text, f"{relative_path}: missing absent-sheet announcement"


@pytest.mark.parametrize("relative_path", DOCS)
def test_compact_hosts_receive_rule_through_common_doctrine(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    assert (
        "Codex and Copilot `dev-mono` definitions do not name "
        "`conventions_file` or `test_runner`"
    ) in text, f"{relative_path}: compact-host limitation is no longer explained"
    for host_def in HOST_DEFS:
        host_text = (ROOT / host_def).read_text(encoding="utf-8")
        assert "conventions_file" not in host_text, host_def
        assert "test_runner" not in host_text, host_def
