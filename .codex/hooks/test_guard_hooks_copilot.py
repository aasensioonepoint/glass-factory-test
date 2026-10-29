"""Gate of the local skills fallback's `install`, through the Codex audit_gate hook.

Moved out of test_guard_hooks.py (length ratchet, .agents/evals/test_python_file_length.py):
the fixture strips EVERY agent marker of the fallback's own `AGENT_CALLER_MARKERS` tuple,
Copilot CLI's included (T-01M5MCXKHQS4BME9Z9VVSWD6VT). Same harness as test_guard_hooks.py:
`invoke`, `_audit_gate_arm` and the canal-A events sandbox are reused from it, never copied.
"""
import ast
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_guard_hooks as _base

audit_gate = _base.audit_gate  # the very module `_audit_gate_arm` drives, never a homonym


def setUpModule():
    _base.setUpModule()


def tearDownModule():
    _base.tearDownModule()


def _agent_caller_markers(src):
    """The `AGENT_CALLER_MARKERS` tuple of `skills_github_fallback.py`, read off its
    source (ast literal, no import): the fixture strips exactly what the gate reads,
    never a hand-kept copy that ages. Fail-closed on an absent or empty tuple."""
    for node in ast.parse(Path(src).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "AGENT_CALLER_MARKERS" for t in node.targets):
            markers = tuple(ast.literal_eval(node.value))
            if markers:
                return markers
    raise AssertionError(f"AGENT_CALLER_MARKERS absent or empty in {src}")


class FallbackGateTests(unittest.TestCase):
    _audit_gate_arm = _base.GuardHookTests._audit_gate_arm

    def _fallback_gate_arm(self, command, install_mode="confirm"):
        """Build a fixture root carrying skills_github_fallback.py + a policy,
        point audit_gate.GATES at it, DELETE every agent marker of the fallback's
        own `AGENT_CALLER_MARKERS` tuple from the environment (so the ONLY marker
        is the neutral 'hook' this twin poses itself — a bench run from Copilot
        CLI inherits COPILOT_CLI, which would otherwise refuse in its place), and
        return whether the host is told to deny."""
        repo = Path(__file__).resolve().parents[2]
        src = repo / ".agents" / "bin" / "skills_github_fallback.py"
        markers = _agent_caller_markers(src)
        real_policy = repo / ".agents" / "security" / "skills-fallback-policy.json"
        original = audit_gate.GATES
        self.addCleanup(setattr, audit_gate, "GATES", original)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = Path(tmp)
        (root / ".agents" / "bin").mkdir(parents=True)
        (root / ".agents" / "security").mkdir(parents=True)
        (root / ".agents" / "state" / "gates").mkdir(parents=True)
        shutil.copy(src, root / ".agents" / "bin" / "skills_github_fallback.py")
        (root / ".agents" / "state" / "gates" / "AUDIT_LOG").write_text("# audit\n", encoding="utf-8")
        policy = json.loads(real_policy.read_text(encoding="utf-8"))
        policy["install_mode"] = install_mode
        (root / ".agents" / "security" / "skills-fallback-policy.json").write_text(
            json.dumps(policy), encoding="utf-8")
        audit_gate.GATES = root / ".agents" / "state" / "gates"
        with mock.patch.dict(os.environ, {}, clear=False):
            for marker in markers:
                os.environ.pop(marker, None)
            return self._audit_gate_arm(command)

    def test_audit_gate_gates_the_local_skills_fallback_install(self):
        """T-00000461, sibling of the runner-form test: the local skills fallback's
        own `install` is gated in COMMAND POSITION by its `gate` subcommand, and the
        twin POSES AGENTS_HOOK_HOST=hook. Without that default a `--confirmed-by x`
        would TRAVERSE on Gemini AND Antigravity, whose registry
        `.agents/hooks.json:49-50` passes NO marker (C10). Mutation: drop the 'hook'
        default -> the --confirmed-by case ALLOWS -> this test reddens."""
        sha = "a" * 40
        ident = f"o/r#s@{sha}"
        self.assertTrue(
            self._fallback_gate_arm(
                f"python .agents/bin/skills_github_fallback.py install {ident} --confirmed-by x",
                install_mode="confirm"),
            "the hook poses AGENTS_HOOK_HOST=hook, so --confirmed-by from a hook is refused")
        self.assertTrue(
            self._fallback_gate_arm(
                f"python .agents/bin/skills_github_fallback.py install {ident}",
                install_mode="confirm"),
            "confirm mode with no --confirmed-by must be denied")
        self.assertFalse(
            self._fallback_gate_arm(
                f"python .agents/bin/skills_github_fallback.py install {ident}",
                install_mode="auto"),
            "auto mode without --confirmed-by is allowed")
        self.assertFalse(
            self._fallback_gate_arm(
                f"echo 'skills_github_fallback.py install {ident}'",
                install_mode="confirm"),
            "a quoted mention must not be gated")


if __name__ == "__main__":
    unittest.main()
