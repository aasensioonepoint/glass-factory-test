"""Suite for py_lock_pins.py — the lockfile -> pins translator of sca-scan.sh.

Collected by `python -m pytest` bare (pytest.ini covers `.agents`), the same
scope the gate runs. Every case drives the REAL CLI through a subprocess, because
the thing under test is a CONTRACT BETWEEN TWO LANGUAGES: a stdout line emitted
by this Python program and parsed by bash. Importing `main()` in-process would
prove the logic while leaving the only surface the caller actually reads —
argv, stdout, stderr, the exit code and the file on disk — unmeasured.

EVERY ASSERTION CARRIES THE MUTATION THAT REDDENS IT (L-00000343). An assertion
nothing can break describes a property instead of measuring it, and this lot has
already been billed three times for that family in one night.

THE PRECONDITIONS ARE FIXED HERE, NOT HOPED FOR (L-00000392). Two of them:

  * `--out` TERMINATION. Every pin line ends with `\\n`, the last one included.
    So the contract is asserted DIRECTLY (test_out_file_always_ends_with_newline)
    and every count is taken with `splitlines()`, which reads the same number
    whether or not a final newline is there. A count that flipped with the
    termination would go red against the very implementation this lot imposes,
    and the tempting repair — loosening the assertion — would turn the proof
    into decor.

  * `tomllib`. It is stdlib from 3.11 ONLY, and this suite must not silently
    stop measuring on an older interpreter. Rather than SKIP, the TOML cases are
    guarded by a real capability probe, and a dedicated pair PROVES the import is
    lazy by making `tomllib` unimportable on purpose — see
    test_missing_tomllib_* at the bottom, which is the arm reserve C43 asked for.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "py_lock_pins.py"

# Capability probe, derived from the FORMAT each fixture makes the program read
# (L-00000392) — never from what a case is "about". A TOML fixture needs tomllib;
# a JSON one does not, and that asymmetry is exactly what the C43 pair measures.
HAS_TOMLLIB = importlib.util.find_spec("tomllib") is not None
needs_toml = pytest.mark.skipif(
    not HAS_TOMLLIB,
    reason="tomllib absent (Python < 3.11) — TOML lock reading NOT measured here",
)


def run(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the CLI exactly as sca-scan.sh does: argv in, rc/stdout/stderr out."""
    env = None
    if env_extra is not None:
        import os

        env = dict(os.environ)
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


# --------------------------------------------------------------------------
# Fixture builders. Each writes the SMALLEST lock that is still valid for its
# format, so a failure points at the parser and not at the fixture's noise.
# --------------------------------------------------------------------------

def write_poetry(path: Path, packages: str = "") -> Path:
    lock = path / "poetry.lock"
    lock.write_text(packages + '\n[metadata]\nlock-version = "2.0"\n', encoding="utf-8")
    return lock


def write_uv(path: Path, packages: str) -> Path:
    lock = path / "uv.lock"
    lock.write_text("version = 1\n" + packages, encoding="utf-8")
    return lock


def write_pipfile(path: Path, payload: dict) -> Path:
    lock = path / "Pipfile.lock"
    lock.write_text(json.dumps(payload), encoding="utf-8")
    return lock


REGISTRY_JINJA = """
[[package]]
name = "jinja2"
version = "2.11.0"
source = { registry = "https://pypi.org/simple" }
"""

UV_ROOT = """
[[package]]
name = "monapp"
version = "0.1.0"
source = { editable = "." }
"""

UV_GIT_DEP = """
[[package]]
name = "vendored"
version = "1.2.3"
source = { git = "https://example.invalid/vendored.git" }
"""


# --------------------------------------------------------------------------
# One case per format — the nominal translation.
# --------------------------------------------------------------------------

@needs_toml
def test_poetry_registry_package_is_pinned(tmp_path):
    lock = write_poetry(tmp_path, '\n[[package]]\nname = "flask"\nversion = "2.0.0"\n')
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: treat a source-less poetry entry as non-registry -> zero pins,
    # no file, and this goes red on the missing file.
    assert out.read_text(encoding="utf-8").splitlines() == ["flask==2.0.0"]


@needs_toml
def test_uv_registry_package_is_pinned(tmp_path):
    lock = write_uv(tmp_path, REGISTRY_JINJA)
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: stop recognising the `registry` key -> the entry falls into
    # excluded_dep, no pin is written, and the file never appears.
    assert out.read_text(encoding="utf-8").splitlines() == ["jinja2==2.11.0"]


def test_pipfile_default_and_develop_are_both_pinned(tmp_path):
    lock = write_pipfile(tmp_path, {
        "default": {"flask": {"version": "==2.0.0"}},
        "develop": {"werkzeug": {"version": "==0.16.0"}},
    })
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: drop "develop" from the section loop -> werkzeug disappears and
    # this goes red. A dev dependency with a CVE is installed just as widely.
    assert out.read_text(encoding="utf-8").splitlines() == [
        "flask==2.0.0", "werkzeug==0.16.0",
    ]


def test_pipfile_entry_without_a_pinned_version_is_an_excluded_dep(tmp_path):
    lock = write_pipfile(tmp_path, {
        "default": {
            "flask": {"version": "==2.0.0"},
            "fromvcs": {"git": "https://example.invalid/x.git", "ref": "abc"},
        },
    })
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # POSITIVE witness first: the registry package really was retained.
    assert out.read_text(encoding="utf-8").splitlines() == ["flask==2.0.0"]
    # MUTATION: count the VCS entry as excluded_root -> this goes red, and so
    # does the caller's degradation, since only excluded_dep degrades.
    assert res.stdout == "excluded_root=0 excluded_dep=1\n"


# --------------------------------------------------------------------------
# THE C34 CASES — the two counters, and the separation proven in BOTH senses.
# --------------------------------------------------------------------------

@needs_toml
def test_uv_root_alone_is_structural_and_never_a_coverage_hole(tmp_path):
    """(alpha) root editable + one registry package."""
    lock = write_uv(tmp_path, UV_ROOT + REGISTRY_JINJA)
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: emit a single aggregated counter -> the line no longer matches,
    # and the caller's fail-closed `case` turns the whole run degraded.
    assert res.stdout == "excluded_root=1 excluded_dep=0\n"
    lines = out.read_text(encoding="utf-8").splitlines()
    # POSITIVE witness, paired with the absence just below (L-00000388): without
    # it, a program that excluded EVERYTHING would pass the absence assertion.
    assert lines == ["jinja2==2.11.0"]
    # ABSENCE: the scanned project itself must never be handed to pip-audit.
    # MUTATION: stop recognising `editable = "."` -> monapp lands in the file.
    assert not any("monapp" in line for line in lines)


@needs_toml
def test_uv_root_plus_git_dep_separates_the_two_motives(tmp_path):
    """(beta) root editable + a git dependency + one registry package.

    THIS is the arm that makes the separation falsifiable in both directions:
      - merge the counters      -> (alpha) would report a non-zero hole and the
                                   caller would degrade a perfectly scanned run;
      - count only the root     -> this case reports excluded_dep=0 and a REAL
                                   coverage hole goes out silently.
    Neither mutation can be green on both arms at once.
    """
    lock = write_uv(tmp_path, UV_ROOT + UV_GIT_DEP + REGISTRY_JINJA)
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    assert res.stdout == "excluded_root=1 excluded_dep=1\n"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == ["jinja2==2.11.0"]
    assert not any("vendored" in line for line in lines)


@needs_toml
def test_poetry_pure_registry_reports_zero_exclusions(tmp_path):
    """(gamma) a lock with nothing excluded still SAYS so, on the nominal path."""
    lock = write_poetry(tmp_path, '\n[[package]]\nname = "flask"\nversion = "2.0.0"\n')
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: emit the line only when a counter is non-zero -> the caller's
    # format guard fires and a clean run is reported degraded. "Nothing excluded"
    # is a measurement the report must carry, not a silence to be inferred.
    assert res.stdout == "excluded_root=0 excluded_dep=0\n"


@needs_toml
def test_poetry_git_source_is_a_real_coverage_hole(tmp_path):
    packages = (
        '\n[[package]]\nname = "flask"\nversion = "2.0.0"\n'
        '\n[[package]]\nname = "vendored"\nversion = "1.0.0"\n'
        '[package.source]\ntype = "git"\nurl = "https://example.invalid/v.git"\n'
    )
    lock = write_poetry(tmp_path, packages)
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    assert out.read_text(encoding="utf-8").splitlines() == ["flask==2.0.0"]
    # poetry has NO root entry by construction, so excluded_root is a property
    # here, not a measurement. MUTATION: count the git source as root -> red,
    # and a real hole would stop degrading the run.
    assert res.stdout == "excluded_root=0 excluded_dep=1\n"


# --------------------------------------------------------------------------
# THE OUTPUT CONTRACT ITSELF — one line, fixed shape, fixed termination.
# --------------------------------------------------------------------------

def test_stdout_is_exactly_one_line_in_the_fixed_format(tmp_path):
    lock = write_pipfile(tmp_path, {"default": {"flask": {"version": "==2.0.0"}}})
    res = run("--out", str(tmp_path / "pins.txt"), str(lock))
    assert res.returncode == 0, res.stderr
    # The caller reads this through `"$( … )"`, which strips the final newline
    # and then matches a `case` glob. More than one line, or a different shape,
    # trips its fail-closed branch. MUTATION: add a second print -> red here AND
    # degraded in sca-scan.sh, which is the behaviour we want on a broken contract.
    assert len(res.stdout.splitlines()) == 1
    assert res.stdout.startswith("excluded_root=")
    assert " excluded_dep=" in res.stdout


def test_out_file_always_ends_with_newline(tmp_path):
    """Reserve C42: the termination is FIXED BY THE CONTRACT, not left to chance.

    Fixing it is what lets every other count in this suite and in
    sca-python.test.sh stay insensitive to it. An assertion that depended on the
    absence of a final newline would go red against the correct implementation,
    and would then be "repaired" by weakening it.
    """
    lock = write_pipfile(tmp_path, {
        "default": {"flask": {"version": "==2.0.0"},
                    "werkzeug": {"version": "==0.16.0"}},
    })
    out = tmp_path / "pins.txt"
    assert run("--out", str(out), str(lock)).returncode == 0
    raw = out.read_text(encoding="utf-8")
    # MUTATION: join with "\n" instead of terminating each line -> red.
    assert raw.endswith("\n")
    assert raw.count("\n") == 2, "one terminator per pin, the last one included"


# --------------------------------------------------------------------------
# ATOMICITY, THE EMPTY CASE, AND THE STALE FILE.
# --------------------------------------------------------------------------

def test_zero_lock_argument_is_refused_by_argparse_alone(tmp_path):
    out = tmp_path / "pins.txt"
    res = run("--out", str(out))
    assert res.returncode == 2
    # The caller (S1/C21) relies on this: it never invokes the program with an
    # empty array, but if it ever did, the refusal must be loud and file-less.
    # MUTATION: switch nargs to "*" -> rc becomes 0 and this goes red.
    assert "LOCK" in res.stderr
    assert not out.exists()


def test_invalid_lock_yields_rc2_and_no_file(tmp_path):
    lock = tmp_path / "poetry.lock"
    lock.write_text("this is not [ valid toml", encoding="utf-8")
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    assert res.returncode == 2
    assert not out.exists()
    # The motive names the lock KIND — one of our three literals — and never a
    # line of the client's file. MUTATION: interpolate the file body -> red.
    assert "poetry.lock" in res.stderr


@needs_toml
def test_one_invalid_lock_among_two_writes_nothing_at_all(tmp_path):
    good = write_uv(tmp_path, REGISTRY_JINJA)
    bad = tmp_path / "poetry.lock"
    bad.write_text("nope [[[", encoding="utf-8")
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(good), str(bad))
    assert res.returncode == 2
    # ATOMICITY — and the mutation was ROLLED, not reasoned, which changed what
    # this line can honestly claim. Writing each lock's pins as it is parsed is
    # NOT enough to redden it: the refusal path's `_discard` then deletes the
    # half-written file and the suite stays green (measured, 23 passed). What
    # this arm really pins is the CONJUNCTION of the two belts — read-all-first
    # AND discard-on-refusal — and it goes red only when BOTH are removed
    # together (measured: 2 failed). Same shape as (L6) in sca-python.test.sh,
    # where one belt left standing still cleans up after the other.
    # The defect it closes is unchanged: a HALF perimeter audited as if whole.
    assert not out.exists()


@needs_toml
def test_two_locks_in_one_call_land_in_the_same_file(tmp_path):
    uv_dir = tmp_path / "a"
    uv_dir.mkdir()
    pip_dir = tmp_path / "b"
    pip_dir.mkdir()
    uv = write_uv(uv_dir, REGISTRY_JINJA)
    pipfile = write_pipfile(pip_dir, {"default": {"werkzeug": {"version": "==0.16.0"}}})
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(uv), str(pipfile))
    assert res.returncode == 0, res.stderr
    # MUTATION: have the caller loop one call per lock -> `--out` TRUNCATES, only
    # the last survives, and the run audits a smaller set than it reports.
    assert out.read_text(encoding="utf-8").splitlines() == [
        "jinja2==2.11.0", "werkzeug==0.16.0",
    ]
    # The counters AGGREGATE across locks; the caller logs one pair per run.
    assert res.stdout == "excluded_root=0 excluded_dep=0\n"


def test_exact_duplicates_across_locks_collapse(tmp_path):
    a_dir = tmp_path / "a"
    a_dir.mkdir()
    b_dir = tmp_path / "b"
    b_dir.mkdir()
    first = write_pipfile(a_dir, {"default": {"flask": {"version": "==2.0.0"}}})
    second = write_pipfile(b_dir, {"default": {"flask": {"version": "==2.0.0"}}})
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(first), str(second))
    assert res.returncode == 0, res.stderr
    # MUTATION: drop the dedup -> two identical `-r` lines reach pip-audit and
    # the same CVE is reported twice, inflating the finding count.
    assert out.read_text(encoding="utf-8").splitlines() == ["flask==2.0.0"]


def test_a_valid_lock_with_nothing_retained_succeeds_WITHOUT_a_file(tmp_path):
    """Reserve C45: a valid lock that retains ZERO packages is a SUCCESS.

    It is not an error and not a refusal — there is simply nothing to audit. The
    caller distinguishes it from a failure by rc=0 plus the ABSENCE of the file,
    and reports it as degraded on its own terms ("locks with no registry
    dependency"), never as a scanned perimeter.
    """
    lock = write_poetry(tmp_path)  # valid TOML, zero [[package]] entries
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock))
    # MUTATION: return 2 on an empty result -> the caller reports "resolution
    # FAILED" for a lock that is perfectly readable and simply holds nothing.
    assert res.returncode == 0, res.stderr
    assert not out.exists()
    assert res.stdout == "excluded_root=0 excluded_dep=0\n"


def test_a_stale_out_file_is_REMOVED_when_nothing_is_retained(tmp_path):
    """Reserve C22: `$OUT` survives between runs, so a leftover would be audited.

    This is the Python half of a two-belt guard; the caller `rm -f`s the same
    path before invoking. (L6) of sca-python.test.sh mutates BOTH belts together,
    because removing only one leaves the other cleaning up and proves nothing.
    """
    lock = write_poetry(tmp_path)
    out = tmp_path / "pins.txt"
    out.write_text("stale==0.0\n", encoding="utf-8")
    res = run("--out", str(out), str(lock))
    assert res.returncode == 0, res.stderr
    # MUTATION: drop `_discard` from the zero-pin branch -> `stale==0.0` survives
    # and the next run audits a dependency the project does not have.
    assert not out.exists()


def test_a_stale_out_file_is_REMOVED_on_a_refusal(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text("not [ toml", encoding="utf-8")
    out = tmp_path / "pins.txt"
    out.write_text("stale==0.0\n", encoding="utf-8")
    res = run("--out", str(out), str(lock))
    assert res.returncode == 2
    # MUTATION: return early on LockError without discarding -> a refused run
    # leaves a stale pins file that the caller's (ii) branch never looks at.
    assert not out.exists()


# --------------------------------------------------------------------------
# THE DISPLAY BOUND — sanitize_display is bash and stops at this program's edge.
# --------------------------------------------------------------------------

def test_an_unknown_lock_name_is_neutralised_before_reaching_stderr(tmp_path):
    hostile = tmp_path / "req;X(a).lock"
    hostile.write_text("x\n", encoding="utf-8")
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(hostile))
    assert res.returncode == 2
    assert not out.exists()
    # The scanned repo belongs to a CLIENT, so a file NAME is untrusted input,
    # and sca-scan.sh joins degradation reasons with `; ` — a `;` in a name can
    # forge a second, reassuring verdict inside the delivered HTML report.
    # POSITIVE witness first: the program really did speak about this name.
    assert "unknown lock kind" in res.stderr
    # MUTATION: print the basename raw -> `;` and `(` survive and this goes red.
    assert ";" not in res.stderr
    assert "(" not in res.stderr
    assert "req?X?a?.lock" in res.stderr


def test_a_legitimate_lock_name_is_NOT_mangled(tmp_path):
    """The paired face: a bound that garbles ordinary names is a bound nobody keeps."""
    plain = tmp_path / "requirements-dev_v2.1.lock"
    plain.write_text("x\n", encoding="utf-8")
    res = run("--out", str(tmp_path / "pins.txt"), str(plain))
    assert res.returncode == 2
    # MUTATION: shrink the whitelist (drop `.`, `-` or `_`) -> red. Neutralising
    # is the goal; mangling real names produces reports nobody acts on.
    assert "requirements-dev_v2.1.lock" in res.stderr


# --------------------------------------------------------------------------
# RESERVE C43 — the import is LAZY, and this PAIR is what proves it.
# --------------------------------------------------------------------------
# The capability guard above lists the arms that need `tomllib`. That list is
# only truthful if the import happens INSIDE the branch that reads TOML: a
# module-level `import tomllib` would kill the program for EVERY lock kind, so
# the guard would describe a list while the failure covered the whole suite
# (L-00000392). These two cases make `tomllib` genuinely unimportable — by
# shadowing it with a module that raises — and check BOTH sides of the boundary.

def _tomllib_blocked_env(tmp_path: Path) -> dict:
    shim_dir = tmp_path / "noshim"
    shim_dir.mkdir()
    (shim_dir / "tomllib.py").write_text(
        'raise ImportError("tomllib blocked on purpose by test_py_lock_pins")\n',
        encoding="utf-8",
    )
    return {"PYTHONPATH": str(shim_dir)}


def test_missing_tomllib_maps_onto_the_SAME_refusal_as_an_unreadable_lock(tmp_path):
    lock = write_uv(tmp_path, REGISTRY_JINJA)
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock), env_extra=_tomllib_blocked_env(tmp_path))
    # rc=2, exactly like an invalid lock: the caller has ONE degraded path to
    # handle, not two, and no rc is left untreated.
    assert res.returncode == 2, res.stdout
    assert not out.exists()
    # MUTATION: let the ImportError escape -> a traceback and some other rc; the
    # caller's (ii) branch still catches it, but the motive stops being readable.
    assert "tomllib" in res.stderr
    assert "uv.lock" in res.stderr


def test_missing_tomllib_leaves_the_JSON_lock_FULLY_working(tmp_path):
    """THE arm of reserve C43, and the one that can only be green on a lazy import.

    `Pipfile.lock` is JSON and needs nothing optional. If `import tomllib` sat at
    module level, this case would fail with the SAME rc=2 as the one above — the
    exemption granted to the JSON path would be fiction, and the whole suite
    would fall over on any interpreter below 3.11.
    """
    lock = write_pipfile(tmp_path, {"default": {"flask": {"version": "==2.0.0"}}})
    out = tmp_path / "pins.txt"
    res = run("--out", str(out), str(lock), env_extra=_tomllib_blocked_env(tmp_path))
    # MUTATION: move `import tomllib` to the top of py_lock_pins.py -> RED here,
    # while the case above stays green. That asymmetry is the whole measurement.
    assert res.returncode == 0, res.stderr
    assert out.read_text(encoding="utf-8").splitlines() == ["flask==2.0.0"]
    assert res.stdout == "excluded_root=0 excluded_dep=0\n"


def test_the_shim_really_blocks_tomllib(tmp_path):
    """Non-vacuity of the two cases above: prove the shim BITES.

    Without this, a PYTHONPATH that silently failed to shadow the stdlib module
    would make both C43 cases pass for the wrong reason — the JSON one because
    everything works, the TOML one only if something else happened to fail.
    """
    env = _tomllib_blocked_env(tmp_path)
    import os

    full = dict(os.environ)
    full.update(env)
    probe = subprocess.run(
        [sys.executable, "-c", "import tomllib"],
        capture_output=True, text=True, env=full,
    )
    assert probe.returncode != 0
    assert "blocked on purpose" in probe.stderr
