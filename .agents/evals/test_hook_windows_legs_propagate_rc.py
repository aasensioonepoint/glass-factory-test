"""Windows registry legs use the shared PowerShell launcher contract.

The frozen ``DEFECTIVE_LITERALS`` still reproduce the historical swallowed-rc
defect. Current registrations must instead expose one literal ``pyrun.ps1``
helper call and one literal target. Bash-mode legs are executed through a real
PowerShell engine when one is available; otherwise that native arm is an
explicit skip, never evidence about Windows behaviour.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# Closed table: (registry, host marker). Gemini/Antigravity share .agents/hooks.json.
REGISTRIES = (
    (".codex/hooks.json", "codex"),
    (".agents/hooks.json", "gemini"),
    (".kimi-code/hooks.json", "kimi"),
)

# Non-vacuity pin (piège 2): (module legs, Python-mediated bash legs) per registry.
EXPECTED_POPULATION = {
    # +1 jambe Codex le 2026-09-21 (T-00000684) : le traceur de la chaîne de
    # plan rejoint `SubagentStop`. Les autres registres restent non câblés.
    # Ce compte est ÉPINGLÉ pour qu'une jambe neuve ne puisse pas échapper au
    # balayage en silence.
    # +1 jambe Codex (bash) le 2026-10-12 (alignement des hôtes, L-C) :
    # `affirmation-guard.sh` rejoint `Stop` — le vide était le contrat, la jambe
    # neuve est VOULUE (X3b : `decision:block` honoré sous Codex).
    # +1 module chacun le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard, voulu.
    ".codex/hooks.json": (13, 8),
    ".agents/hooks.json": (12, 6),
    ".kimi-code/hooks.json": (12, 7),
}

# --- The THREE defective literals of 1f509a1, recopied VERBATIM from
#     .codex/hooks.json:38, :78, :97 — the runtime negative control (arm 4)
#     runs THESE against an `exit 2` stub and asserts the wrapper still says 0.
#     This is what proves the defect was REAL, not supposed.
DEFECTIVE_LITERALS = (
    "python -c \"import os,subprocess; r=subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip(); subprocess.run(['bash', r+'/.agents/security/gitleaks-scan.sh', '--content'], cwd=r, env=dict(os.environ, AGENTS_HOOK_HOST='codex'))\"",
    "python -c \"import os,subprocess; r=subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip(); e=dict(os.environ, AGENTS_HOOK_HOST='codex', SCA_CHANGED_ONLY='1'); subprocess.run(['bash', r+'/.agents/security/sca-scan.sh'], cwd=r, env=e)\"",
    "python -c \"import os,subprocess; r=subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip(); subprocess.run(['bash', r+'/.agents/bin/post-task-done-index.sh'], cwd=r, env=dict(os.environ, AGENTS_HOOK_HOST='codex'))\"",
)

_LEGACY_SCRIPT_RE = re.compile(r"r\+'(/[^']+)'")
_POWERSHELL_RE = re.compile(
    r'^powershell(?:\.exe)? -NoProfile -NonInteractive -Command "(?P<body>.*)"$'
)
_HELPER_CALL_RE = re.compile(
    r"& \(\$r\+'/\.agents/pyrun\.ps1'\) "
    r"'(?P<mode>module|bash)' \$r '(?P<target>\.[^']+\.(?:py|sh))'"
    r"(?P<arguments>(?: '[^']*')*)"
)


def _load(registry: str) -> dict:
    return json.loads((ROOT / registry).read_text(encoding="utf-8"))


def _all_windows_legs(registry: str) -> list[str]:
    """Every `commandWindows` string in a registry, walking event -> block -> hooks.
    Outside the kit, the kit's legs only (T-01M54MWW5GH, S-01M550PYWS)."""
    obj = _load(registry)
    legs: list[str] = []
    for _event, blocks in obj.get("hooks", {}).items():
        for block in blocks:
            for hook in block.get("hooks", []):
                cw = hook.get("commandWindows")
                if cw and jambe_jugee(str(cw)):
                    legs.append(cw)
    return legs


def _legacy_script_path(leg: str) -> str | None:
    """The single historical ``r+'/…'`` path, or ``None``."""
    m = _LEGACY_SCRIPT_RE.search(leg)
    return m.group(1) if m else None


def _powershell_body(leg: str) -> str | None:
    match = _POWERSHELL_RE.fullmatch(leg)
    return match.group("body") if match else None


def _helper_call(leg: str) -> re.Match[str] | None:
    body = _powershell_body(leg)
    return _HELPER_CALL_RE.search(body) if body else None


def _leg_violations(registry: str, leg: str) -> list[str]:
    """THE RULE for one leg, as a list of `<registry>…: msg` strings — replayed by
    the negative controls rather than re-implemented (L-00000349)."""
    v: list[str] = []
    body = _powershell_body(leg)
    if body is None:
        v.append(f"{registry}/{leg[:60]!r}: not a clear PowerShell command")
        return v
    if "EncodedCommand" in leg or "Invoke-Expression" in leg:
        v.append(f"{registry}/{leg[:60]!r}: encoded or evaluated bootstrap")
    if "$r=(& git rev-parse --show-toplevel)" not in body:
        v.append(f"{registry}/{leg[:60]!r}: root lookup is not visible")

    calls = list(_HELPER_CALL_RE.finditer(body))
    if len(calls) != 1:
        v.append(f"{registry}/{leg[:60]!r}: expected one identifiable helper call")
        return v

    call = calls[0]
    mode = call.group("mode")
    target = call.group("target")
    label = f"{registry}:{Path(target).name}/windows"
    expected_suffix = ".py" if mode == "module" else ".sh"
    if not target.endswith(expected_suffix):
        v.append(f"{label}: {mode} mode targets {target}")
    if not (ROOT / target).is_file():
        v.append(f"{label}: literal target does not exist")
    marker = dict(REGISTRIES)[registry]
    if f"$env:AGENTS_HOOK_HOST='{marker}'" not in body:
        v.append(f"{label}: AGENTS_HOOK_HOST bootstrap missing")
    has_sca_env = "$env:SCA_CHANGED_ONLY='1'" in body
    if has_sca_env != (target == ".agents/security/sca-scan.sh"):
        v.append(f"{label}: SCA_CHANGED_ONLY bootstrap does not match target")
    return v


def _all_violations() -> list[str]:
    out: list[str] = []
    for registry, _marker in REGISTRIES:
        for leg in _all_windows_legs(registry):
            out += _leg_violations(registry, leg)
    return out


def _run_leg(leg: str, tmp: Path, rc: int, engine: str) -> subprocess.CompletedProcess:
    """Run one current bash-mode registration against a safe child stub."""
    call = _helper_call(leg)
    assert call is not None, "leg carries no identifiable helper call"
    assert call.group("mode") == "bash", "runtime arm only executes bash-mode legs"
    stub = tmp / call.group("target")
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(f'#!/bin/sh\ntouch "$PWD/.called"\nexit {rc}\n', encoding="utf-8")
    assert stub.stat().st_size > 0, "stub was not written before the call"

    helper = tmp / ".agents" / "pyrun.ps1"
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / ".agents" / "pyrun.ps1", helper)

    called = tmp / ".called"
    if called.exists():
        called.unlink()

    body = _powershell_body(leg)
    assert body is not None, "leg is not a clear PowerShell command"
    proc = subprocess.run(
        [engine, "-NoProfile", "-NonInteractive", "-Command", body],
        cwd=str(tmp), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc


def _run_defective_leg(leg: str, tmp: Path, rc: int) -> subprocess.CompletedProcess:
    """Execute one frozen inline-Python witness on the current OS."""
    path = _legacy_script_path(leg)
    assert path is not None, "defective leg carries no historical script path"
    stub = tmp / path.lstrip("/")
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(f'#!/bin/sh\ntouch "$PWD/.called"\nexit {rc}\n', encoding="utf-8")

    called = tmp / ".called"
    if called.exists():
        called.unlink()
    argv = shlex.split(leg)
    argv[0] = sys.executable
    return subprocess.run(
        argv,
        cwd=str(tmp),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _git_init(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(tmp), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _powershell_engine() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _legacy_tools_present() -> bool:
    return bool(shutil.which("bash") and shutil.which("git"))


class WindowsLegPropagationTests:
    """The 20 Python-mediated Bash legs preserve rc; all 54 legs stay inspectable."""

    # ---- every registry parses ----
    def test_each_registry_parses_as_json(self):
        for registry, _marker in REGISTRIES:
            assert isinstance(_load(registry), dict), f"{registry} is not valid JSON"

    # ---- the positive rule (FORM), per leg ----
    def test_every_windows_leg_is_well_formed(self):
        offenders = _all_violations()
        assert not offenders, "leg violations: " + "; ".join(offenders)

    # ---- non-vacuity (piège 2) ----
    def test_non_vacuity_population_is_the_one_announced(self):
        total_module = total_bash = 0
        for registry, _marker in REGISTRIES:
            legs = _all_windows_legs(registry)
            modes = [call.group("mode") for leg in legs if (call := _helper_call(leg))]
            module_n = modes.count("module")
            bash_n = modes.count("bash")
            assert (module_n, bash_n) == EXPECTED_POPULATION[registry], (
                f"{registry}: population moved to {(module_n, bash_n)} — update the "
                f"table, or a leg is scanned by no test"
            )
            total_module += module_n
            total_bash += bash_n
        # (34, 21) -> (37, 21) le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard.
        assert (total_module, total_bash) == (37, 21), (
            f"total population moved to {(total_module, total_bash)}, expected (37, 21)"
        )

    # ---- positive executable arm: every subprocess leg × rc in {1,2} ----
    def test_subprocess_legs_propagate_child_rc(self, tmp_path):
        engine = _powershell_engine()
        if engine is None:
            pytest.skip("PowerShell engine absent — native Windows-leg arm not measured")
        if not shutil.which("bash") or not shutil.which("git"):
            pytest.skip("bash and/or git absent — the native executable arm cannot run")
        _git_init(tmp_path)
        failures: list[str] = []
        for registry, _marker in REGISTRIES:
            for leg in _all_windows_legs(registry):
                call = _helper_call(leg)
                if call is None or call.group("mode") != "bash":
                    continue
                script = Path(call.group("target")).name
                for rc in (1, 2):
                    proc = _run_leg(leg, tmp_path, rc, engine)
                    if proc.returncode != rc:
                        failures.append(
                            f"{registry}:{script} returned {proc.returncode}, "
                            f"expected {rc} (leg swallows child rc)"
                        )
                    if not (tmp_path / ".called").exists():
                        failures.append(f"{registry}:{script} — child stub never ran")
        assert not failures, "propagation failures: " + "; ".join(failures)

    # ---- negative RUNTIME control: the defect reproduced from 1f509a1 ----
    def test_defective_literals_swallow_rc(self, tmp_path):
        if not _legacy_tools_present():
            pytest.skip("bash and/or git absent — the runtime control cannot run")
        _git_init(tmp_path)
        for leg in DEFECTIVE_LITERALS:
            proc = _run_defective_leg(leg, tmp_path, 2)
            assert proc.returncode == 0, (
                "a 1f509a1 defective literal no longer swallows rc — either it was "
                "fixed in place (it must not be, it is a frozen witness) or the arm "
                "broke"
            )
            assert (tmp_path / ".called").exists(), (
                "the child never ran — rc 0 would not prove the wrapper swallowed it"
            )

    # ---- negative STATIC control: mutate a fixed leg back to the defect ----
    def test_static_mutation_of_a_gitleaks_leg_reddens(self):
        for registry, _marker in REGISTRIES:
            leg = next(
                l for l in _all_windows_legs(registry)
                if " 'bash' $r " in l and "gitleaks-scan.sh" in l
            )
            # A well-formed leg must exist for this control to be meaningful.
            assert not _leg_violations(registry, leg), (
                f"{registry}: gitleaks leg is not well-formed — run S1 first"
            )
            mutated = leg.replace("/.agents/pyrun.ps1", "/.agents/pyrun-missing.ps1")
            assert mutated != leg, "the negative control mutated nothing"
            offenders = _leg_violations(registry, mutated)
            assert any("identifiable helper call" in m for m in offenders), (
                f"{registry}: mutating the leg back to the defect did not redden"
            )


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    raise SystemExit(pytest.main([__file__, "-v"]))
