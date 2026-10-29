"""Regression guard: the per-task delta journal (specs.py) must NEVER be wired
into any SessionStart injection or hook registration surface (ledger L-004:
injected context is a prompt-injection surface that grows as it accumulates —
this store is read on demand, by task id, never reinjected wholesale).

Two things are asserted, deliberately at different layers so a future
REGRESSION turns red whether it happens at the prose layer or the
registration layer:

  (a) none of the three session-hook SCRIPTS mentions specs.py/SPECS.json —
      catches someone editing the hook body to shell out to it.
  (b) across the four hook REGISTRATION surfaces, no resolved command string
      of any registered hook references specs.py — catches someone adding a
      *new* hook entry that wires it in, even if no existing script changed.

ZERO LLM calls. Style aligned with .codex/test_pipeline_contract.py and
.agents/evals/test_golden_transcripts.py: deterministic, source-of-truth
files only.
"""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SESSION_HOOK_SCRIPTS = (
    ROOT / ".claude" / "hooks" / "session-start.sh",
    ROOT / ".codex" / "hooks" / "session_context.py",
    ROOT / ".gemini" / "hooks" / "session_context.py",
)

HOOK_REGISTRATION_SURFACES = (
    ROOT / ".claude" / "settings.json",
    ROOT / ".codex" / "hooks.json",
    ROOT / ".agents" / "hooks.json",
    ROOT / ".github" / "hooks" / "agent-guardrails.json",
)

FORBIDDEN_MARKERS = ("specs.py", "SPECS.json", "SPECS.md")


def collect_strings(node) -> list[str]:
    """Recursively collect every string leaf in a parsed JSON structure —
    hook command text lives under different keys per host (``command``,
    ``bash``, ``powershell``, ``commandWindows``), so walking everything is
    more robust than pinning key names that vary across the four schemas."""
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(collect_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(collect_strings(item))
    return out


class SessionHookScriptsNeverReferenceSpecsTests(unittest.TestCase):
    def test_no_session_hook_script_mentions_specs(self):
        for path in SESSION_HOOK_SCRIPTS:
            self.assertTrue(path.exists(), f"expected session hook script at {path}")
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_MARKERS:
                self.assertNotIn(
                    marker,
                    text,
                    f"{path} references {marker!r} — the journal must never be "
                    f"wired into a SessionStart injection (ledger L-004)",
                )


def hook_side(data):
    """The registration surface minus `permissions`, which registers NO hook:
    a `permissions.deny` rule naming SPECS.json PROTECTS the journal (T-00000847,
    rule `specs-journal`) — the opposite of wiring it in. That subtree is bounded
    separately below, so excluding it here opens nothing."""
    if isinstance(data, dict) and "permissions" in data:
        return {k: v for k, v in data.items() if k != "permissions"}
    return data


class HookRegistrationSurfacesNeverReferenceSpecsTests(unittest.TestCase):
    def test_no_registered_hook_command_string_references_specs(self):
        for path in HOOK_REGISTRATION_SURFACES:
            self.assertTrue(path.exists(), f"expected hook registration surface at {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
            for s in collect_strings(hook_side(data)):
                for marker in FORBIDDEN_MARKERS:
                    self.assertNotIn(
                        marker,
                        s,
                        f"{path} registers a hook whose command string references "
                        f"{marker!r} — a NEW hook registration would slip past a "
                        f"script-only check, this asserts the registration layer too",
                    )

    def test_permissions_name_specs_only_to_DENY_an_edit(self):
        """The excluded subtree stays bounded: SPECS may appear there ONLY as a
        `deny` rule — never under `allow`/`ask`, never as anything else."""
        for path in HOOK_REGISTRATION_SURFACES:
            data = json.loads(path.read_text(encoding="utf-8"))
            perms = data.get("permissions") if isinstance(data, dict) else None
            if not isinstance(perms, dict):
                continue
            for key, value in perms.items():
                for s in collect_strings(value):
                    for marker in FORBIDDEN_MARKERS:
                        if marker in s:
                            self.assertEqual(
                                "deny", key,
                                f"{path} permissions.{key} names {marker!r} — only a deny rule may",
                            )
                            self.assertTrue(
                                s.startswith("Edit("),
                                f"{path} permissions.deny names {marker!r} outside an Edit(...) rule: {s!r}",
                            )


if __name__ == "__main__":
    unittest.main()
