"""The Gemini/Antigravity shell guards are behind a matcher that NAMES their
shell tool -- `run_command`, not only `Bash` (T-00000350).

WHAT WENT WRONG, MEASURED. `.agents/hooks.json` is the hook registration file
for BOTH Gemini CLI and Antigravity (they share it, per AGENTS.md § Cross-agent
surfaces). Its `PreToolUse` shell stage was registered on `"matcher": "Bash"`
alone: `run_command` appeared ZERO times in the whole file, with `Bash` as the
non-vacuity witness at exactly one occurrence. And AGENTS.md § Task tracking
already ACTS on the opposite fact for a different hook -- "there the shell tool
is named `run_command` (a `Bash` matcher is silently inert)" -- so the reasoning
was written down in one place and violated in another. The guard did not FAIL on
those hosts; it never RAN.

THE BLAST RADIUS IS WIDER THAN THE TICKET NAMED, and the sweep is what found it.
That one matcher block carries TWO guards, not one:

  * `safe_bash.py`  -- the destructive-command guard AND the write-redirect
                       guard of T-00000244 (the one that refuses `> tracked`)
  * `audit_gate.py` -- the skill-install audit gate (`npx skills add` etc.)

`audit_gate` was not in the ticket's text. It is in the same block, so it had the
same hole, and it is pinned here for the same reason.

WHY AN ALTERNATION AND NOT A REPLACEMENT. `"Bash|run_command"` is STRICTLY
ADDITIVE: on a host whose shell tool is `Bash` the alternation still matches, and
on a host whose shell tool is `run_command` the guard now runs. There is no
direction in which this can regress, which is what makes it safe to land without
being able to measure the host (see the honesty limit below). The alternation
form is not invented either -- it is the idiom this very file already uses, in
`SessionStart`'s `"startup|resume|clear|compact"`.

THE HONESTY LIMIT, WRITTEN RATHER THAN HIDDEN. Gemini CLI is NOT installed on the
maintainer's box (`command -v gemini` -> absent), so the tool name that host
really presents at `PreToolUse` could not be measured here. What this suite
pins is therefore the kit's own established fact -- AGENTS.md's `run_command` --
carried into the one place that had contradicted it. It does NOT prove the host
matches the string; it proves the kit stopped disagreeing with itself.

WHAT THIS SUITE DELIBERATELY DOES NOT COVER, so its green is not read as more
than it is: the `"Edit|Write|apply_patch"` matcher in the same file, which gates
`protect_paths.py`, `kickoff_guard.py` and the class-0 `gitleaks --content`
scan. The repository establishes NO edit-tool name for Gemini/Antigravity, and
guessing three names into a security guard would put invention where measurement
belongs -- the failure mode L-00000253 names (a correction that closes the doors
it can see and CERTIFIES the rest closed is worse than an incomplete one). If
those tools carry other names on those hosts, that whole stage is inert too --
graver than this ticket, and NOT closed by it. Tracked separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = ROOT / ".agents" / "hooks.json"

# The shell tool name Gemini CLI / Antigravity present, per AGENTS.md. A matcher
# that does not carry it leaves the guard registered-but-never-invoked.
SHELL_TOOL = "run_command"

# A hook whose command cites any of these is a SHELL-STAGE guard: it exists to
# inspect a command line, so it is inert unless the shell tool matches. Matched
# against the hook's command strings, which name the module being run.
# `iac_guard` ajouté le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : garde de l'étage shell.
SHELL_STAGE_GUARDS = ("safe_bash", "audit_gate", "iac_guard")


def _load() -> dict:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def _matcher_covers(matcher: str, tool: str) -> bool:
    """Does `matcher` name `tool` as one of its alternatives?

    The host treats the matcher as an alternation, so the decision is on a
    SPLIT, never on a substring (L-00000143: a substring guard is wrong in both
    directions -- `Bash` is a substring of nothing useful here, but `command` is
    a substring of `run_command`, and a prefix test would accept `run_command2`).
    """
    return tool in [alt.strip() for alt in (matcher or "").split("|")]


def _shell_stage_blocks_missing_tool(hooks_obj: dict, tool: str) -> list[tuple[str, str]]:
    """THE RULE, as one function, so the negative control can replay THIS rule
    rather than a re-implementation of it.

    Returns one `(matcher, guard_module)` pair per shell-stage guard whose block
    does not name `tool`. An empty list is the conformant answer.
    """
    offenders: list[tuple[str, str]] = []
    for block in hooks_obj.get("hooks", {}).get("PreToolUse", []):
        matcher = block.get("matcher", "")
        for hook in block.get("hooks", []):
            cmds = " ".join(
                str(hook.get(key, "")) for key in ("command", "commandWindows")
            )
            for guard in SHELL_STAGE_GUARDS:
                if guard in cmds and not _matcher_covers(matcher, tool):
                    offenders.append((matcher, guard))
    return offenders


class GeminiShellMatcherTests:
    """`.agents/hooks.json` shell stage names `run_command`, and the rule bites."""

    def test_hooks_json_is_valid_json(self) -> None:
        # A1/A2: the edit must not have broken the file the two hosts parse.
        assert isinstance(_load(), dict)

    def test_every_shell_stage_guard_matcher_names_run_command(self) -> None:
        offenders = _shell_stage_blocks_missing_tool(_load(), SHELL_TOOL)
        assert not offenders, (
            "shell-stage guard registered behind a matcher that does not name "
            f"{SHELL_TOOL!r} -- it is SILENTLY INERT on Gemini CLI / Antigravity: "
            + "; ".join(f"matcher {m!r} -> {g}" for m, g in offenders)
        )

    def test_non_vacuity_the_sweep_actually_found_the_guards(self) -> None:
        """A rule that inspected an EMPTY population would also return no
        offenders (L-00000232, L-00000186: a harness lies by the void, and its
        lie has the shape of a perfect green). So NAME the members that must be
        found, established through the file itself, and refuse to conclude when
        the count is zero.
        """
        obj = _load()
        seen: set[str] = set()
        for block in obj.get("hooks", {}).get("PreToolUse", []):
            for hook in block.get("hooks", []):
                cmds = " ".join(
                    str(hook.get(key, "")) for key in ("command", "commandWindows")
                )
                for guard in SHELL_STAGE_GUARDS:
                    if guard in cmds:
                        seen.add(guard)
        assert seen == set(SHELL_STAGE_GUARDS), (
            "the population this suite claims to measure is not the one it found: "
            f"expected {sorted(SHELL_STAGE_GUARDS)}, found {sorted(seen)}. Either a "
            "guard was removed from .agents/hooks.json (then this suite is watching "
            "nothing) or one was renamed (then SHELL_STAGE_GUARDS is stale)."
        )

    def test_negative_control_the_rule_refuses_a_bare_bash_matcher(self) -> None:
        """THE CONTROL THAT MAKES THE GREEN MEAN SOMETHING (L-00000057: the
        dominant failure mode is right logic wired to the wrong anchor, and only
        a negative control sees it).

        Re-enable the defect -- the exact `"matcher": "Bash"` the file carried
        before T-00000350 -- and require the rule to go RED. The mutation is
        asserted IN PLACE before the verdict is counted (L-00000161), so a rule
        that silently inspected nothing cannot pass this test either.
        """
        mutated = _load()
        blocks = mutated["hooks"]["PreToolUse"]
        touched = 0
        for block in blocks:
            for hook in block.get("hooks", []):
                cmds = " ".join(
                    str(hook.get(key, "")) for key in ("command", "commandWindows")
                )
                if any(guard in cmds for guard in SHELL_STAGE_GUARDS):
                    block["matcher"] = "Bash"
                    touched += 1
                    break

        # Prove the mutation applied before any verdict is read.
        assert touched, "the negative control mutated nothing -- it measures nothing"
        assert any(
            b.get("matcher") == "Bash"
            for b in blocks
        ), "the reverted matcher is not in place; the control below would be vacuous"

        offenders = _shell_stage_blocks_missing_tool(mutated, SHELL_TOOL)
        assert offenders, (
            "THE RULE DOES NOT BITE: replayed against the pre-T-00000350 matcher "
            '("Bash" alone) it still reported no offender, so its green on the real '
            "file measures nothing at all."
        )

    def test_scope_the_edit_stage_is_named_as_uncovered(self) -> None:
        """The uncovered surface is asserted to still BE uncovered, so the day
        someone closes it this test fails and the docstring above gets corrected
        instead of quietly becoming a lie (L-00000111: a doc asserting a
        guarantee the code does not hold prevents anyone from seeing the defect).
        """
        edit_matchers = [
            block.get("matcher", "")
            for block in _load().get("hooks", {}).get("PreToolUse", [])
            if "protect_paths" in json.dumps(block.get("hooks", []))
        ]
        assert edit_matchers, "the edit stage vanished from .agents/hooks.json"
        assert not any(
            _matcher_covers(m, SHELL_TOOL) for m in edit_matchers
        ), (
            "the edit stage now names a Gemini tool name -- good, but this suite's "
            "header still declares that surface UNCOVERED. Update the header and "
            "this test together, or the file starts lying about its own scope."
        )


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    raise SystemExit(pytest.main([__file__, "-v"]))
