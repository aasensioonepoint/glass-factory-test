"""Portable Python launcher fixtures for T-00000554.

All executable children are created below ``tmp_path``.  The only registered
hook launched by this suite is ``protect_paths.py`` with an allowed path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PYRUN_SH = ROOT / ".agents" / "pyrun.sh"
PYRUN_PS1 = ROOT / ".agents" / "pyrun.ps1"
PROBE_DIAGNOSTIC = "PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3."
FIXED_DIAGNOSTIC = PROBE_DIAGNOSTIC
PROBE_CODE = (
    "PY_PROBE='import sys; sys.stdout.write(sys.executable); "
    "sys.exit(sys.version_info[0] != 3)'"
)
PAYLOAD_ARGUMENTS = ("value with spaces", "apostrophe's value", "")

PROBE_FILES = (
    ".claude/hooks/agent-events.sh",
    ".claude/hooks/audit-gate.sh",
    ".claude/hooks/bancs-mandat.sh",
    ".claude/hooks/context-retro.sh",
    ".claude/hooks/emit-event.sh",
    ".claude/hooks/log-agent-usage.sh",
    ".claude/hooks/mcp-events.sh",
    ".claude/hooks/post-edit-check.sh",
    ".claude/hooks/pre-compact.sh",
    ".claude/hooks/protect-paths.sh",
    ".claude/hooks/run-recap.sh",
    ".claude/hooks/safe-bash.sh",
    ".claude/hooks/session-start.sh",
    ".claude/hooks/stop-reindex.sh",
    ".agents/security/gitleaks-scan.sh",
    ".agents/security/sca-scan.sh",
    ".agents/security/semgrep-scan.sh",
    ".agents/security/shellcheck-scan.sh",
    ".agents/bin/post-task-done-index.sh",
)

# One post-diagnostic anchor per dispatcher. These preserve its existing
# fail-open/fail-closed decision instead of treating the new message as policy.
PROBE_BEHAVIOR_ANCHORS = {
    ".claude/hooks/agent-events.sh": "exit 0\n}",
    ".claude/hooks/audit-gate.sh": 'degraded "no python on PATH to read the PreToolUse payload"',
    # S-01M5YZ6VJN : sans python, bancs-mandat REFUSE (rc 2).
    ".claude/hooks/bancs-mandat.sh": "mandat non lu — refus (S-01M5YZ6VJN). Remède : installer python 3 "
                                     "(python3, python ou py -3).\" >&2\n  exit 2\n}",
    ".claude/hooks/context-retro.sh": "exit 0\n}",
    ".claude/hooks/emit-event.sh": "exit 0\n}",
    ".claude/hooks/log-agent-usage.sh": "exit 0\n}",
    ".claude/hooks/mcp-events.sh": "exit 0\n}",
    ".claude/hooks/post-edit-check.sh": '[ -n "$PY" ] && FILE=',
    ".claude/hooks/pre-compact.sh": '[ -n "$PY" ] && TP=',
    ".claude/hooks/protect-paths.sh": '[ -n "$PY" ] && FILE=',
    ".claude/hooks/run-recap.sh": "exit 0\n}",
    ".claude/hooks/safe-bash.sh": 'degraded "no python on PATH to read the PreToolUse payload"',
    ".claude/hooks/session-start.sh": "exit 0\n}",
    ".claude/hooks/stop-reindex.sh": 'if [ -n "$PY" ] && [ -f',
    ".agents/security/gitleaks-scan.sh": 'ROOT="$(git rev-parse --show-toplevel',
    ".agents/security/sca-scan.sh": 'ROOT="$(git rev-parse --show-toplevel',
    ".agents/security/semgrep-scan.sh": 'ROOT="$(git rev-parse --show-toplevel',
    ".agents/security/shellcheck-scan.sh": "hook INACTIF, verify.sh reste l'arbitre\" >&2\n      exit 0",
    ".agents/bin/post-task-done-index.sh": 'TOKEN="interp-introuvable"',
}

_HELPER_CALL_RE = re.compile(
    r"& \(\$r\+'/\.agents/pyrun\.ps1'\) "
    r"'(?P<mode>module|bash)' \$r '(?P<target>\.[^']+\.(?:py|sh))'"
    r"(?P<arguments>(?: '[^']*')*)"
)
# Le seul préfixe admis devant `pyrun.sh` est le lanceur qui échoue FERMÉ, sous sa
# forme EXACTE (T-01M5CH9FA8BDDM33QKDBAZG42S) : tout autre script intercalé reste
# un lanceur caché.
_NESTED_POSIX_HELPER_RE = re.compile(
    r'bash (?:"\$\(git rev-parse --show-toplevel\)/\.agents/security/garde-fermee\.sh" '
    r'--echeance=[0-9]+ )?'
    r'"\$\(git rev-parse --show-toplevel\)/\.agents/pyrun\.sh" '
    r'"\$\(git rev-parse --show-toplevel\)/(?P<target>\.[^"]+\.py)"$'
)
# Même règle sous Copilot (T-01M5MCXKHQS4BME9Z9VVSWD6VT) : le lanceur fermé, sous
# sa forme EXACTE, est le seul préfixe admis devant `pyrun.sh`.
_COPILOT_POSIX_HELPER_RE = re.compile(
    r"bash (?:\.agents/security/garde-fermee\.sh --echeance=[0-9]+ )?"
    r"\.agents/pyrun\.sh (?P<target>\.[^ ]+\.py)$"
)
_SCRIPT_RE = re.compile(
    r"(?:\.claude|\.codex|\.gemini|\.agents|\.github|core-scripts|scripts)/"
    r"[\w./-]+\.(?:sh|py|ps1)\b"
)


def _powershell_engine() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _bash_engine() -> str:
    engine = shutil.which("bash")
    if engine is None:
        pytest.skip("bash absent — portable shell launcher arm not measured")
    return engine


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_candidate(bin_dir: Path, name: str, behavior: str) -> None:
    if behavior == "ok":
        action = 'printf "%s\\n" "$FAKE_RESOLVED_PYTHON"\nexit 0'
    elif behavior == "python2":
        action = "exit 2"
    elif behavior == "store":
        action = 'printf "%s\\n" "$FAKE_STORE_TARGET"\nexit 0'
    elif behavior == "python2-optimized":
        action = (
            '"$FAKE_RESOLVED_PYTHON" -c \'import sys; '
            'exec(sys.argv[1].replace("sys.version_info[0]", "2"))\' "$2"\nexit $?'
        )
    else:  # pragma: no cover - closed fixture table
        raise AssertionError(f"unknown candidate behavior {behavior}")
    _write_executable(
        bin_dir / name,
        "#!/bin/sh\n"
        + f"printf '%s\\n' '{name}' >> \"$PROBE_LOG\"\n"
        + '[ -z "${PROBE_CWD_LOG-}" ] || pwd >> "$PROBE_CWD_LOG"\n'
        + ('[ "${1-}" = "-3" ] || exit 95\n' if name == "py" else "")
        + "if [ \"$#\" -lt 2 ]; then exit 96; fi\n"
        + f"{action}\n",
    )


def _write_uname(bin_dir: Path, value: str) -> None:
    _write_executable(bin_dir / "uname", f"#!/bin/sh\nprintf '%s\\n' '{value}'\n")


def _launcher_env(bin_dir: Path, probe_log: Path, child_log: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": str(bin_dir),
            "PROBE_LOG": str(probe_log),
            "PROBE_CWD_LOG": str(probe_log.with_suffix(".cwd")),
            "CHILD_LOG": str(child_log),
            "FAKE_RESOLVED_PYTHON": sys.executable,
            "FAKE_STORE_TARGET": str(bin_dir / "MicrosoftStoreAliasMissing.exe"),
            "HOOK_FIXTURE_ENV": "environment-preserved",
        }
    )
    env.pop("OS", None)
    return env


def _candidate_names(probe_log: Path) -> list[str]:
    if not probe_log.exists():
        return []
    return probe_log.read_text(encoding="utf-8").splitlines()


def _assert_probe_contracts() -> None:
    # 21 -> 19 (T-01M5PCCHMWXTRCM5QJT8J5KNEH) : le hook et le lanceur de la route
    # de dev locale sont partis avec elle.
    assert len(PROBE_FILES) == len(set(PROBE_FILES)) == 19
    assert set(PROBE_BEHAVIOR_ANCHORS) == set(PROBE_FILES)
    primary_probe = (
        'PY_CANDIDATE="$("$c" -c "$PY_PROBE" </dev/null 2>/dev/null)" '
        '|| PY_CANDIDATE=""'
    )
    windows_probe = (
        'PY_CANDIDATE="$(py -3 -c "$PY_PROBE" </dev/null 2>/dev/null)" '
        '|| PY_CANDIDATE=""'
    )
    for relative in PROBE_FILES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert text.count(PROBE_CODE) == 1, f"{relative}: Python-major probe drifted"
        assert text.count(primary_probe) == 1, f"{relative}: primary probe is not stdin-isolated"
        assert text.count(windows_probe) == 1, f"{relative}: py -3 probe drifted"
        assert (
            text.count(
                'command -v uname >/dev/null 2>&1 && PY_UNAME="$(uname -s 2>/dev/null)"'
            )
            == 1
        ), f"{relative}: guarded uname resolution drifted"
        assert text.count('case "${OS-}:$PY_UNAME" in') == 1, (
            f"{relative}: combined OS/uname case drifted"
        )
        assert (
            text.count("Windows_NT:*|*:CYGWIN*|*:MINGW*|*:MSYS*)") == 1
        ), f"{relative}: Windows platform patterns drifted"
        assert 'case "$(uname -s 2>/dev/null)" in' not in text, (
            f"{relative}: unguarded uname probe still present"
        )
        diagnostic = f'echo "{PROBE_DIAGNOSTIC}" >&2'
        assert text.count(diagnostic) == 1, f"{relative}: fixed stderr diagnostic drifted"
        diagnostic_offset = text.index(diagnostic)
        following = text[diagnostic_offset : diagnostic_offset + 800]
        assert PROBE_BEHAVIOR_ANCHORS[relative] in following, (
            f"{relative}: historical no-Python dispatcher behavior drifted"
        )


def _make_safe_children(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo with spaces and apostrophe's mark"
    package = root / "fixture package"
    package.mkdir(parents=True)
    (package / "fixture_support.py").write_text(
        "VALUE = 'sibling-import-preserved'\n", encoding="utf-8"
    )
    python_child = package / "child_hook.py"
    python_child.write_text(
        "import json\n"
        "import os\n"
        "import sys\n"
        "from fixture_support import VALUE\n"
        "with open(os.environ['CHILD_LOG'], 'a', encoding='utf-8') as stream:\n"
        "    stream.write('child\\n')\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), "
        "'env': os.environ['HOOK_FIXTURE_ENV'], 'stdin': sys.stdin.read(), "
        "'support': VALUE}))\n"
        "print('fixture-child-stderr', file=sys.stderr)\n"
        "raise SystemExit(int(sys.argv[1]))\n",
        encoding="utf-8",
    )
    bash_child = package / "child hook.sh"
    _write_executable(
        bash_child,
        "#!/usr/bin/env bash\n"
        "exec \"$FIXTURE_PYTHON\" \"$FIXTURE_CHILD\" \"$@\"\n",
    )
    return root, python_child, bash_child


@pytest.mark.parametrize("helper", ("shell", "powershell"))
def test_no_python_fixed_stderr(tmp_path: Path, helper: str) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_bin)
    env.pop("OS", None)

    if helper == "shell":
        _assert_probe_contracts()
        proc = subprocess.run(
            [_bash_engine(), str(PYRUN_SH), "-c", "raise SystemExit(99)"],
            cwd=tmp_path,
            env=env,
            input="payload remains unread",
            text=True,
            capture_output=True,
        )
    else:
        source = PYRUN_PS1.read_text(encoding="utf-8")
        assert source.count(f"WriteLine('{FIXED_DIAGNOSTIC}')") == 1
        engine = _powershell_engine()
        if engine is None:
            pytest.skip("PowerShell engine absent — native no-Python arm not measured")
        target = tmp_path / "safe.py"
        target.write_text("raise SystemExit(99)\n", encoding="utf-8")
        proc = subprocess.run(
            [
                engine,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(PYRUN_PS1),
                "module",
                str(tmp_path),
                target.name,
            ],
            cwd=tmp_path,
            env=env,
            input="payload remains unread",
            text=True,
            capture_output=True,
        )

    assert proc.returncode == 127
    assert proc.stdout == ""
    assert proc.stderr.splitlines() == [FIXED_DIAGNOSTIC]


@pytest.mark.parametrize("rc", (0, 1, 2, 127))
@pytest.mark.parametrize(
    "runner",
    ("shell-root", "shell-subdirectory", "powershell-module", "powershell-bash"),
)
def test_existing_return_statuses(tmp_path: Path, runner: str, rc: int) -> None:
    root, python_child, bash_child = _make_safe_children(tmp_path)
    nested_cwd = root / "nested invocation directory"
    nested_cwd.mkdir()
    child_log = tmp_path / "child.log"
    probe_log = tmp_path / "probe.log"
    input_text = "stdin payload with spaces and apostrophe's mark"

    if runner.startswith("shell"):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_candidate(bin_dir, "python3", "ok")
        env = _launcher_env(bin_dir, probe_log, child_log)
        cwd = root if runner == "shell-root" else nested_cwd
        proc = subprocess.run(
            [
                _bash_engine(),
                str(PYRUN_SH),
                str(python_child),
                str(rc),
                *PAYLOAD_ARGUMENTS,
            ],
            cwd=cwd,
            env=env,
            input=input_text,
            text=True,
            capture_output=True,
        )
        expected_cwd = cwd
    else:
        engine = _powershell_engine()
        if engine is None:
            pytest.skip("PowerShell engine absent — native helper arm not measured")
        bash = _bash_engine()
        env = os.environ.copy()
        env.update(
            {
                "PATH": os.pathsep.join(
                    dict.fromkeys((str(Path(sys.executable).parent), str(Path(bash).parent)))
                ),
                "CHILD_LOG": str(child_log),
                "HOOK_FIXTURE_ENV": "environment-preserved",
                "FIXTURE_PYTHON": sys.executable,
                "FIXTURE_CHILD": str(python_child),
            }
        )
        mode = "module" if runner == "powershell-module" else "bash"
        target = python_child if mode == "module" else bash_child
        proc = subprocess.run(
            [
                engine,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(PYRUN_PS1),
                mode,
                str(root),
                str(target.relative_to(root)),
                str(rc),
                *PAYLOAD_ARGUMENTS,
            ],
            cwd=nested_cwd,
            env=env,
            input=input_text,
            text=True,
            capture_output=True,
        )
        expected_cwd = nested_cwd if mode == "module" else root

    assert proc.returncode == rc
    assert proc.stderr.splitlines() == ["fixture-child-stderr"]
    payload = json.loads(proc.stdout)
    assert payload == {
        "argv": [str(rc), *PAYLOAD_ARGUMENTS],
        "cwd": str(expected_cwd.resolve()),
        "env": "environment-preserved",
        "stdin": input_text,
        "support": "sibling-import-preserved",
    }
    assert child_log.read_text(encoding="utf-8").splitlines() == ["child"]


# T-00001191: a DEDICATED child — the shared child's JSON is compared for equality by
# test_existing_return_statuses, so it is never extended. This one imports its sibling,
# then runs a grandchild `sys.executable -c` that imports another sibling; both leave a
# trace, so a green run proves the two imports really happened.
_BYTECODE_CHILD = '''\
import os
import subprocess
import sys

from fixture_support import VALUE

with open(os.environ["CHILD_LOG"], "a", encoding="utf-8") as stream:
    stream.write(VALUE + "\\n")
GRANDCHILD = (
    "import sys; sys.path.insert(0, sys.argv[1]); import fixture_grandchild; "
    "open(sys.argv[2], 'a', encoding='utf-8').write(fixture_grandchild.MARK + chr(10))"
)
here = os.path.dirname(os.path.abspath(__file__))
done = subprocess.run([sys.executable, "-c", GRANDCHILD, here, os.environ["CHILD_LOG"]])
raise SystemExit(done.returncode)
'''


@pytest.mark.parametrize(
    "runner", ("shell", "shell-E", "powershell-module", "powershell-bash")
)
def test_launchers_write_no_bytecode_1191(tmp_path: Path, runner: str) -> None:
    """Neither launcher lets a hook, nor a process it spawns, write a `.pyc` (T-00001191).

    `shell` catches a missing export (the grandchild), `shell-E` a missing `-B` (an
    `-E` caller drops the env), the PowerShell arms a missing `$env:` line.
    """
    root, _python_child, bash_child = _make_safe_children(tmp_path)
    package = bash_child.parent
    (package / "fixture_grandchild.py").write_text("MARK = 'grandchild-ran'\n", encoding="utf-8")
    child = package / "bytecode_child.py"
    child.write_text(_BYTECODE_CHILD, encoding="utf-8")
    child_log = tmp_path / "child.log"

    if runner.startswith("shell"):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_candidate(bin_dir, "python3", "ok")
        env = _launcher_env(bin_dir, tmp_path / "probe.log", child_log)
        flags = ["-E"] if runner == "shell-E" else []
        command = [_bash_engine(), str(PYRUN_SH), *flags, str(child)]
    else:
        engine = _powershell_engine()
        if engine is None:
            pytest.skip("PowerShell engine absent — native helper arm not measured")
        bash = _bash_engine()
        env = os.environ.copy()
        env.update(
            {
                "PATH": os.pathsep.join(
                    dict.fromkeys((str(Path(sys.executable).parent), str(Path(bash).parent)))
                ),
                "CHILD_LOG": str(child_log),
                "FIXTURE_PYTHON": sys.executable,
                "FIXTURE_CHILD": str(child),
            }
        )
        mode = "module" if runner == "powershell-module" else "bash"
        target = child if mode == "module" else bash_child
        command = [
            engine, "-NoProfile", "-NonInteractive", "-File", str(PYRUN_PS1),
            mode, str(root), str(target.relative_to(root)),
        ]
    # A host value of either variable would make this witness vacuous.
    for name in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"):
        env.pop(name, None)

    proc = subprocess.run(command, cwd=root, env=env, input="", text=True, capture_output=True)

    assert proc.returncode == 0, proc.stderr
    assert child_log.read_text(encoding="utf-8").splitlines() == [
        "sibling-import-preserved",
        "grandchild-ran",
    ]
    cache = package / "__pycache__"
    assert not cache.exists(), sorted(entry.name for entry in cache.iterdir())


@pytest.mark.parametrize(
    ("case", "candidates", "windows_shell", "expected_probes", "succeeds"),
    (
        ("python-only", {"python": "ok"}, False, ["python"], True),
        ("python3-only", {"python3": "ok"}, False, ["python3"], True),
        ("both", {"python3": "ok", "python": "ok"}, False, ["python3"], True),
        ("none", {}, False, [], False),
        (
            "python2-rejected",
            {"python3": "python2", "python": "ok"},
            False,
            ["python3", "python"],
            True,
        ),
        (
            "store-stub-rejected",
            {"python3": "store", "python": "ok"},
            False,
            ["python3", "python"],
            True,
        ),
        ("py-3-windows", {"py": "ok"}, True, ["py"], True),
    ),
)
def test_path_candidate_matrix(
    tmp_path: Path,
    case: str,
    candidates: dict[str, str],
    windows_shell: bool,
    expected_probes: list[str],
    succeeds: bool,
) -> None:
    bin_dir = tmp_path / f"{case}-bin"
    bin_dir.mkdir()
    for name, behavior in candidates.items():
        _write_candidate(bin_dir, name, behavior)
    probe_log = tmp_path / f"{case}-probes.log"
    child_log = tmp_path / f"{case}-child.log"
    env = _launcher_env(bin_dir, probe_log, child_log)
    if windows_shell:
        assert "OS" not in env
        _write_uname(bin_dir, "MINGW64_NT-10.0")
    code = (
        "import json,os,sys; "
        "open(os.environ['CHILD_LOG'],'a',encoding='utf-8').write('child\\n'); "
        "print(json.dumps({'argv':sys.argv[1:],'stdin':sys.stdin.read()}))"
    )
    input_text = f"stdin-{case}"
    proc = subprocess.run(
        [_bash_engine(), str(PYRUN_SH), "-c", code, *PAYLOAD_ARGUMENTS],
        cwd=tmp_path,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
    )

    assert _candidate_names(probe_log) == expected_probes
    if not succeeds:
        assert proc.returncode == 127
        assert proc.stdout == ""
        assert proc.stderr.splitlines() == [FIXED_DIAGNOSTIC]
        assert not child_log.exists()
        return
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert json.loads(proc.stdout) == {
        "argv": list(PAYLOAD_ARGUMENTS),
        "stdin": input_text,
    }
    assert child_log.read_text(encoding="utf-8").splitlines() == ["child"]


@pytest.mark.parametrize("helper", ("shell", "powershell"))
def test_venv_sys_prefix_is_preserved(tmp_path: Path, helper: str) -> None:
    venv_root = tmp_path / "venv with spaces and apostrophe's mark"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    scripts_dir = venv_root / ("Scripts" if os.name == "nt" else "bin")
    env = os.environ.copy()
    env["PATH"] = str(scripts_dir)
    expected_prefix = str(venv_root.resolve())

    if helper == "shell":
        proc = subprocess.run(
            [
                _bash_engine(),
                str(PYRUN_SH),
                "-c",
                "import json,sys; print(json.dumps(sys.prefix))",
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
        )
    else:
        engine = _powershell_engine()
        if engine is None:
            pytest.skip("PowerShell engine absent — native venv arm not measured")
        target = tmp_path / "report_prefix.py"
        target.write_text(
            "import json, sys\nprint(json.dumps(sys.prefix))\n", encoding="utf-8"
        )
        proc = subprocess.run(
            [
                engine,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(PYRUN_PS1),
                "module",
                str(tmp_path),
                target.name,
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
        )

    assert proc.returncode == 0, proc.stderr
    assert Path(json.loads(proc.stdout)).resolve() == Path(expected_prefix)


def test_python2_rejected_with_pythonoptimize(tmp_path: Path) -> None:
    shell_source = PYRUN_SH.read_text(encoding="utf-8")
    powershell_source = PYRUN_PS1.read_text(encoding="utf-8")
    for name, source in (("pyrun.sh", shell_source), ("pyrun.ps1", powershell_source)):
        assert "assert sys.version_info" not in source, f"{name}: -O disables assert"
        assert "sys.exit" in source
        assert "sys.version_info[0] != 3" in source

    bin_dir = tmp_path / "optimized-python2-bin"
    bin_dir.mkdir()
    _write_candidate(bin_dir, "python3", "python2-optimized")
    _write_candidate(bin_dir, "python", "ok")
    probe_log = tmp_path / "optimized-probes.log"
    child_log = tmp_path / "optimized-child.log"
    env = _launcher_env(bin_dir, probe_log, child_log)
    env["PYTHONOPTIMIZE"] = "1"
    proc = subprocess.run(
        [_bash_engine(), str(PYRUN_SH), "-c", "print('fallback-python3')"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["fallback-python3"]
    assert _candidate_names(probe_log) == ["python3", "python"]


def test_powershell_helper_preserves_module_and_bash_contracts() -> None:
    source = PYRUN_PS1.read_text(encoding="utf-8")
    module_marker = "if ($Mode -eq 'module')"
    assert source.count(module_marker) == 1
    module_branch = source.split(module_marker, 1)[1]
    bash_marker = "if ([System.IO.Path]::GetExtension($resolvedTarget) -ne '.sh')"
    assert source.count(bash_marker) == 1
    module_branch, bash_branch = module_branch.split(bash_marker, 1)

    assert "runpy.run_module(" in module_branch
    assert "runpy.run_path(" not in module_branch
    assert "sys.path.insert(0" in module_branch
    assert "sys.argv=" in module_branch
    assert "-WorkingDirectory $resolvedRoot" not in module_branch
    assert "Resolve-Python3 -WorkingDirectory $callerDirectory" in source
    assert "-WorkingDirectory $callerDirectory" in source

    assert "subprocess.run(" in bash_branch
    assert "cwd=" in bash_branch
    assert "-WorkingDirectory $resolvedRoot" not in bash_branch
    assert "Resolve-ApplicationPath -Name 'bash'" not in bash_branch


# Hors du kit, les quatre énumérateurs ne rendent que les jambes du kit
# (T-01M54MWW5GH, S-01M550PYWS) : une jambe AJOUTÉE par l'adoptant est à sa charge.
def _nested_windows(registry: str) -> list[str]:
    obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
    return [
        str(hook["commandWindows"])
        for blocks in obj["hooks"].values()
        for block in blocks
        for hook in block["hooks"]
        if jambe_jugee(str(hook.get("commandWindows", "")))
    ]


def _nested_posix(registry: str) -> list[str]:
    obj = json.loads((ROOT / registry).read_text(encoding="utf-8"))
    return [
        str(hook["command"])
        for blocks in obj["hooks"].values()
        for block in blocks
        for hook in block["hooks"]
        if jambe_jugee(str(hook.get("command", "")))
    ]


def _copilot_windows() -> list[str]:
    obj = json.loads(
        (ROOT / ".github" / "hooks" / "agent-guardrails.json").read_text(encoding="utf-8")
    )
    return [str(hook["powershell"]) for hooks in obj["hooks"].values() for hook in hooks
            if jambe_jugee(str(hook.get("powershell", "")))]


def _copilot_posix() -> list[str]:
    obj = json.loads(
        (ROOT / ".github" / "hooks" / "agent-guardrails.json").read_text(encoding="utf-8")
    )
    return [str(hook["bash"]) for hooks in obj["hooks"].values() for hook in hooks
            if jambe_jugee(str(hook.get("bash", "")))]


def test_nested_posix_helper_admits_only_the_closed_guard_prefix() -> None:
    racine = '"$(git rev-parse --show-toplevel)'
    pyrun = f'{racine}/.agents/pyrun.sh" {racine}/.codex/hooks/protect_paths.py"'
    garde = f'{racine}/.agents/security/garde-fermee.sh" --echeance=7 '
    assert _NESTED_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=codex bash {pyrun}")
    assert _NESTED_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=codex bash {garde}{pyrun}")
    assert _NESTED_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=codex bash x.sh {pyrun}") is None
    assert _NESTED_POSIX_HELPER_RE.search(
        f"AGENTS_HOOK_HOST=codex bash {garde.replace('=7', '=x')}{pyrun}"
    ) is None


def test_copilot_posix_helper_admits_only_the_closed_guard_prefix() -> None:
    pyrun = ".agents/pyrun.sh .codex/hooks/protect_paths.py"
    garde = ".agents/security/garde-fermee.sh --echeance=7 "
    assert _COPILOT_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=copilot bash {pyrun}")
    assert _COPILOT_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=copilot bash {garde}{pyrun}")
    assert _COPILOT_POSIX_HELPER_RE.search(f"AGENTS_HOOK_HOST=copilot bash x.sh {pyrun}") is None
    assert _COPILOT_POSIX_HELPER_RE.search(
        f"AGENTS_HOOK_HOST=copilot bash {garde.replace('=7', '=x')}{pyrun}"
    ) is None


def test_registered_command_protocols() -> None:
    expected = {
        # +1 jambe Codex le 2026-09-21 (T-00000684) : le traceur de la chaine de
        # plan rejoint `SubagentStop`. Les autres registres restent non cables.
        # +1 module chacun le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard sur Bash.
        ".codex/hooks.json": (13, 8, "codex"),   # +1 bash : affirmation-guard sur Stop (alignement, L-C)
        ".agents/hooks.json": (12, 6, "gemini"),
        ".kimi-code/hooks.json": (12, 7, "kimi"),
    }
    total_module = total_bash = total_posix_module = 0
    all_windows: list[str] = []
    for registry, (expected_module, expected_bash, marker) in expected.items():
        legs = _nested_windows(registry)
        all_windows.extend(legs)
        matches = [_HELPER_CALL_RE.search(leg) for leg in legs]
        assert all(match is not None for match in matches), f"{registry}: hidden helper/target"
        modes = [match.group("mode") for match in matches if match is not None]
        assert (modes.count("module"), modes.count("bash")) == (
            expected_module,
            expected_bash,
        )
        total_module += modes.count("module")
        total_bash += modes.count("bash")
        for leg, match in zip(legs, matches, strict=True):
            assert match is not None
            assert leg.startswith('powershell -NoProfile -NonInteractive -Command "')
            assert "$r=(& git rev-parse --show-toplevel)" in leg
            assert f"$env:AGENTS_HOOK_HOST='{marker}'" in leg
            assert match.group("target").endswith(
                ".py" if match.group("mode") == "module" else ".sh"
            )
            assert (ROOT / match.group("target")).is_file()

        posix_module_legs = [leg for leg in _nested_posix(registry) if ".py" in leg]
        # Le compte POSIX doit suivre le compte Windows du MEME registre :
        # l'ajout T-00000684 est Codex-only, donc un littéral commun mentirait.
        assert len(posix_module_legs) == expected_module
        for leg in posix_module_legs:
            posix_match = _NESTED_POSIX_HELPER_RE.search(leg)
            assert posix_match is not None, (
                f"{registry}: bare or hidden POSIX module launcher"
            )
            assert leg.count(".agents/pyrun.sh") == 1
            assert re.search(r"\bpython(?:3)?\b", leg) is None
            assert (ROOT / posix_match.group("target")).is_file()
        total_posix_module += len(posix_module_legs)

    # (34, 21) -> (37, 21) le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard, 3 registres.
    assert (total_module, total_bash) == (37, 21)
    copilot = _copilot_windows()
    all_windows.extend(copilot)
    copilot_helper = [leg for leg in copilot if ".agents/pyrun.ps1" in leg]
    copilot_native_bash = [leg for leg in copilot if ".agents/pyrun.ps1" not in leg]
    # 10 -> 11 le 2026-09-13 (T-00000589) : Copilot aussi câble le traceur du
    # binôme sur `subagentStop`, l'événement qu'il déclarait déjà.
    # 11 -> 12 et 7 -> 8 le 2026-10-12 (alignement des hôtes, L-C) : plan_trace sur
    # `subagentStop` (jambe module) et affirmation-guard sur `agentStop` (jambe native).
    # 12 -> 13 le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard sur `preToolUse`.
    assert len(copilot_helper) == 13
    assert len(copilot_native_bash) == 8
    assert all(
        (match := _HELPER_CALL_RE.search(leg)) is not None
        and match.group("mode") == "module"
        and (ROOT / match.group("target")).is_file()
        for leg in copilot_helper
    )
    assert all(
        "$r=(& git rev-parse --show-toplevel)" in leg
        and "$env:AGENTS_HOOK_HOST='copilot'" in leg
        for leg in copilot_helper
    )
    for leg in copilot_native_bash:
        assert leg.startswith("$ErrorActionPreference='Stop'; try {")
        assert "$r=(& git rev-parse --show-toplevel)" in leg
        assert "$env:AGENTS_HOOK_HOST='copilot'" in leg
        assert "$childExitCode=$LASTEXITCODE; exit $childExitCode" in leg
        assert "python" not in leg.lower()
        assert "pyrun.ps1" not in leg
        targets = [match.group(0) for match in _SCRIPT_RE.finditer(leg)]
        assert len(targets) == 1 and targets[0].endswith(".sh")
        assert (ROOT / targets[0]).is_file()
        assert f"& bash ($r+'/{targets[0]}')" in leg

    copilot_posix_module = [leg for leg in _copilot_posix() if ".py" in leg]
    # 10 -> 11 le 2026-09-13 (T-00000589), jambe POSIX de Copilot.
    # 12 -> 13 le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard.
    assert len(copilot_posix_module) == 13
    for leg in copilot_posix_module:
        posix_match = _COPILOT_POSIX_HELPER_RE.search(leg)
        assert posix_match is not None, "Copilot: bare or hidden POSIX module launcher"
        assert leg.count(".agents/pyrun.sh") == 1
        assert re.search(r"\bpython(?:3)?\b", leg) is None
        assert (ROOT / posix_match.group("target")).is_file()
    total_posix_module += len(copilot_posix_module)

    # 71 -> 72 : une seule jambe Windows neuve, Codex uniquement (T-00000684).
    # 72 -> 75 le 2026-10-12 (alignement, L-C) : Codex +1, Copilot +2.
    # 75 -> 79 et 46 -> 50 le 2026-10-18 (T-01M52X1W3WPKCWX1DC36NMKJB6) : iac_guard, 4 registres.
    assert len(all_windows) == 79
    # 44 -> 45 : même borne sur la jambe module POSIX.
    assert total_posix_module == 50
    for leg in all_windows:
        assert re.search(r"encodedcommand|invoke-expression", leg, re.IGNORECASE) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX registered-command contract")
@pytest.mark.parametrize(
    ("registry", "from_subdirectory"),
    (
        (".codex/hooks.json", True),
        (".agents/hooks.json", True),
        (".kimi-code/hooks.json", True),
        (".github/hooks/agent-guardrails.json", False),
    ),
)
def test_registered_posix_command_uses_python3_helper(
    tmp_path: Path, registry: str, from_subdirectory: bool
) -> None:
    commands = _copilot_posix() if registry.startswith(".github/") else _nested_posix(registry)
    command = next(leg for leg in commands if "protect_paths.py" in leg)

    bin_dir = tmp_path / "python3-only-bin"
    bin_dir.mkdir()
    _write_candidate(bin_dir, "python3", "ok")
    # mktemp, sleep, cat, rm : les outils du lanceur `garde-fermee.sh`, qui REFUSE
    # sans eux ; les registres Codex et Copilot le câblent (Copilot depuis
    # T-01M5MCXKHQS4BME9Z9VVSWD6VT), et aucun n'est une sonde python.
    tools = ("bash", "git")
    if registry in (".codex/hooks.json", ".github/hooks/agent-guardrails.json"):
        tools += ("mktemp", "sleep", "cat", "rm")
    for tool in tools:
        resolved = shutil.which(tool)
        if resolved is None:
            pytest.skip(f"{tool} absent — registered POSIX arm not measured")
        (bin_dir / tool).symlink_to(resolved)

    probe_log = tmp_path / "registered-probes.log"
    child_log = tmp_path / "registered-child.log"
    env = _launcher_env(bin_dir, probe_log, child_log)
    cwd = ROOT / ".agents" / "evals" if from_subdirectory else ROOT
    payload = json.dumps(
        {"toolName": "Edit", "toolArgs": {"file_path": "README.md"}}
    )
    proc = subprocess.run(
        [_bash_engine(), "-c", command],
        cwd=cwd,
        env=env,
        input=payload,
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == ""
    assert _candidate_names(probe_log) == ["python3"]
    assert not child_log.exists()
