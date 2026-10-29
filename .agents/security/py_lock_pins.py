#!/usr/bin/env python3
"""py_lock_pins.py — resolve Python LOCKFILES into a pinned requirements file.

Called by sca-scan.sh's Python block (T-00000462, case #143). It closes the hole
where a project carrying ONLY `poetry.lock` / `uv.lock` / `Pipfile.lock` — and no
`requirements*.txt` at all — reached the dispatcher's degraded branch and was
never audited, while the run still published `python: scanned`.

  py_lock_pins.py --out <pins.txt> <lock> [<lock> ...]

WHY A SEPARATE PROGRAM. `pip-audit --no-deps` audits only what is PINNED (`==`),
and the dispatcher's whole posture is that it never RESOLVES anything (resolving
downloads and BUILDS sdists, i.e. executes arbitrary `setup.py`). A lockfile
already holds exact versions, so reading it is a pure TRANSLATION — no network,
no build, no mutation of the scanned tree. Bash cannot parse TOML; this can.

=============================================================================
THE OUTPUT CONTRACT — stdout is parsed by sca-scan.sh, so it is FIXED
=============================================================================
stdout is EXACTLY ONE line, terminated by ONE newline:

    excluded_root=<N> excluded_dep=<M>

Two counters, never one aggregate, and the separation is the point (L-00000388).
An entry dropped from the audit scope used to leave no byte on the NOMINAL path,
so a run published `scanned` over an AMPUTATED perimeter. But the two motives do
not mean the same thing, and merging them forces a choice between a permanent
`degraded` and a silence:

  excluded_root — the lockfile's OWN root project (uv.lock's `editable = "."` or
                  `virtual = "."`). It is not a dependency, so its exclusion is
                  STRUCTURAL and is NOT a coverage hole. It NEVER degrades.
  excluded_dep  — any other non-registry entry (git, url, path, file, directory,
                  or an `editable` that is not the root). Those ARE dependencies
                  we cannot audit: a REAL coverage hole, and the caller degrades.

`poetry.lock` and `Pipfile.lock` have no root entry by construction, so
`excluded_root` is 0 for them ALWAYS — never a measurement, a property.

=============================================================================
EXIT CODES — a BOUND, not an enumeration (L-00000187)
=============================================================================
  0  success. Either `--out` was written (>= 1 pin) or NO file exists (0 pins).
  2  refusal of any kind: unknown lock kind, unreadable/invalid lock, missing
     `tomllib`, unwritable `--out`, or no LOCK argument at all (argparse).

There is no third code. The caller treats EVERY non-zero rc identically, so a
new failure mode cannot slip through as a success.

ATOMIC BY CONSTRUCTION. Every lock is read and validated BEFORE one byte is
written, so one invalid lock among three yields exit 2 and NO file — never a
half-written pin set that the caller would audit as if it were complete.

AND ON BOTH FILE-LESS OUTCOMES A PRE-EXISTING `--out` IS REMOVED. `$OUT` in the
dispatcher SURVIVES between runs, so a stale pins file from a previous run would
be handed to `pip-audit` as if it were fresh — auditing dependencies the project
no longer has, and missing the ones it now does. The caller also `rm -f`s it; the
two belts are deliberate and are mutated TOGETHER by the (L6) arm of
sca-python.test.sh, because removing only one leaves the other cleaning up.

TERMINATION OF `--out` IS PART OF THE CONTRACT (reserve C42): every pin line,
INCLUDING THE LAST, is terminated by `\n`. Nothing downstream may depend on the
absence of a final newline, and nothing may break on its presence.

=============================================================================
DISPLAY BOUND — this file is read from a CLIENT's repository
=============================================================================
`sanitize_display` lives in sca-scan.sh and is BASH; it cannot cover a Python
program reading a client file. So this program bounds its OWN output: stderr
carries a MOTIVE and the lock KIND (one of our three literals), never a line of
file content and never a package name. The one client-controlled string that can
reach stderr — an unknown lock's basename — goes through `_safe()`, the same
whitelist as sca-scan.sh's helper (`[A-Za-z0-9._/ -]`, everything else `?`).
Replacing rather than deleting is deliberate: tampering stays VISIBLE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# The three lockfile basenames this program understands. Dispatch is by BASENAME
# and the enumeration is CLOSED: anything else is refused with exit 2 rather than
# guessed at. `pyproject.toml` and `Pipfile` are deliberately absent — they carry
# version RANGES, not pins, and resolving a range is the one thing the lock-only
# posture forbids. The dispatcher keeps naming those as degraded on its own.
POETRY_LOCK = "poetry.lock"
UV_LOCK = "uv.lock"
PIPFILE_LOCK = "Pipfile.lock"
KNOWN_KINDS = (POETRY_LOCK, UV_LOCK, PIPFILE_LOCK)

# Whitelist mirrored from sca-scan.sh:189 (`tr -c 'A-Za-z0-9._/ -' '?'`). Kept
# byte-wise on purpose: a UTF-8 character outside the set becomes one `?` per
# byte, exactly as `LC_ALL=C tr` does, so the two bounds render identically.
_ALLOWED = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/ -"
)

# A poetry `source.type` that still designates a PyPI-style index. `legacy` is
# what poetry writes for a custom/mirrored index — the package is a normal
# registry artifact at an exact version, so it is audited like any other.
_POETRY_REGISTRY_TYPES = frozenset({"legacy"})


class LockError(Exception):
    """A lock could not be read or understood. Always maps onto exit 2.

    Carries an ALREADY-BOUNDED message: callers print it verbatim to stderr, so
    whatever builds it is responsible for having passed client bytes through
    `_safe()` first.
    """


def _safe(text: str) -> str:
    """Neutralise a client-controlled string for DISPLAY. Whitelist, not blacklist.

    A blacklist leaks everything >= 0x80 (U+009B CSI and U+202E RLO both survive a
    control-byte strip), and control bytes are not even the worst face: `;` and
    `()` let a crafted file name FORGE a second, reassuring verdict inside a
    report handed to the client. See sca-scan.sh's `sanitize_display` block for
    the two attacks measured on this kit.
    """
    raw = text.encode("utf-8", "replace")
    return "".join(chr(b) if b in _ALLOWED else "?" for b in raw)


def _load_toml(path: Path, kind: str) -> dict:
    """Parse a TOML lockfile, importing `tomllib` LAZILY.

    THE IMPORT IS INSIDE THIS FUNCTION AND THAT IS LOAD-BEARING (reserve C43).
    `tomllib` is stdlib from Python 3.11 only. At module top an older interpreter
    would kill this program for EVERY lock kind, including `Pipfile.lock`, which
    is JSON and needs nothing optional — the declared scope of the capability
    guard and the real scope of the failure would then diverge in silence, which
    is precisely the shape L-00000392 names.

    Its absence maps onto the SAME outcome as an unreadable lock — a LockError,
    hence exit 2 — so the caller has one degraded path to handle, not two.
    """
    try:
        import tomllib
    except ImportError as exc:
        raise LockError(
            f"{kind}: TOML reader unavailable (tomllib needs Python >= 3.11)"
        ) from exc

    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise LockError(f"{kind}: file not found") from exc
    except OSError as exc:
        raise LockError(f"{kind}: unreadable") from exc
    except ValueError as exc:  # tomllib.TOMLDecodeError subclasses ValueError
        raise LockError(f"{kind}: invalid TOML") from exc


def _load_json(path: Path, kind: str) -> dict:
    """Parse a JSON lockfile. Nothing optional here — `json` is always present."""
    try:
        with path.open("rb") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise LockError(f"{kind}: file not found") from exc
    except OSError as exc:
        raise LockError(f"{kind}: unreadable") from exc
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise LockError(f"{kind}: invalid JSON") from exc
    if not isinstance(data, dict):
        raise LockError(f"{kind}: invalid JSON (expected an object at the root)")
    return data


def _packages(data: dict, kind: str) -> list:
    """Return the `[[package]]` array of a TOML lock, or refuse.

    A lock with NO package array at all is VALID and simply holds nothing to pin
    (poetry writes `[metadata]` alone for an empty project). It yields zero pins
    and zero exclusions — a success without a file, never an error.
    """
    packages = data.get("package")
    if packages is None:
        return []
    if not isinstance(packages, list):
        raise LockError(f"{kind}: invalid structure (`package` is not an array)")
    return packages


def _parse_poetry(path: Path) -> tuple[list, int, int]:
    """poetry.lock -> (pins, excluded_root, excluded_dep).

    `excluded_root` is 0 BY CONSTRUCTION, not by measurement: a poetry lock never
    lists the project itself. A registry entry has no `source` table at all, or a
    `source.type` of `legacy` (a mirrored index). Anything else — git, url, file,
    directory — is a dependency we cannot audit, hence a REAL coverage hole.
    """
    data = _load_toml(path, POETRY_LOCK)
    pins: list = []
    excluded_dep = 0
    for entry in _packages(data, POETRY_LOCK):
        if not isinstance(entry, dict):
            raise LockError(f"{POETRY_LOCK}: invalid structure (package entry)")
        source = entry.get("source")
        if isinstance(source, dict) and source.get("type") not in _POETRY_REGISTRY_TYPES:
            excluded_dep += 1
            continue
        pins.append(_pin(entry, POETRY_LOCK))
    return pins, 0, excluded_dep


def _parse_uv(path: Path) -> tuple[list, int, int]:
    """uv.lock -> (pins, excluded_root, excluded_dep).

    uv is the ONLY one of the three that lists the scanned project ITSELF, as an
    `editable = "."` (or `virtual = "."`) entry. That entry is not a dependency,
    so excluding it is STRUCTURAL and must never degrade the run — counting it
    with the real holes would make every uv project permanently degraded, and a
    permanent degradation is read as noise until nobody reads it at all.

    An `editable` pointing ANYWHERE ELSE is a different animal: a local package
    outside the root, un-auditable, and therefore a genuine hole.
    """
    data = _load_toml(path, UV_LOCK)
    pins: list = []
    excluded_root = 0
    excluded_dep = 0
    for entry in _packages(data, UV_LOCK):
        if not isinstance(entry, dict):
            raise LockError(f"{UV_LOCK}: invalid structure (package entry)")
        source = entry.get("source")
        if not isinstance(source, dict):
            # No source table: uv always writes one. Treat as un-auditable rather
            # than guessing it is a registry package — guessing here would invent
            # coverage, which is the failure this whole lot exists to prevent.
            excluded_dep += 1
            continue
        if "registry" in source:
            pins.append(_pin(entry, UV_LOCK))
            continue
        local = source.get("editable", source.get("virtual"))
        if local == ".":
            excluded_root += 1
            continue
        excluded_dep += 1
    return pins, excluded_root, excluded_dep


def _parse_pipfile(path: Path) -> tuple[list, int, int]:
    """Pipfile.lock -> (pins, excluded_root, excluded_dep).

    BOTH `default` and `develop` are read: a dev dependency with a known CVE is
    still installed on every contributor's machine and in most CI images, and the
    lock-only posture has no reason to look at one and not the other.

    Pipenv writes the pin as a `version` string that ALREADY carries its `==`.
    An entry with no such `version` is a VCS/path/file requirement — a real hole.
    Like poetry, a Pipfile lock never lists the project itself, so `excluded_root`
    is 0 by construction.
    """
    data = _load_json(path, PIPFILE_LOCK)
    pins: list = []
    excluded_dep = 0
    for section in ("default", "develop"):
        block = data.get(section)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise LockError(f"{PIPFILE_LOCK}: invalid structure (`{section}`)")
        for name, entry in block.items():
            if not isinstance(entry, dict):
                raise LockError(f"{PIPFILE_LOCK}: invalid structure (package entry)")
            version = entry.get("version")
            if not isinstance(version, str) or not version.startswith("=="):
                excluded_dep += 1
                continue
            if not isinstance(name, str) or not name:
                raise LockError(f"{PIPFILE_LOCK}: invalid structure (empty package name)")
            pins.append(f"{name}=={version[2:]}")
    return pins, 0, excluded_dep


def _pin(entry: dict, kind: str) -> str:
    """Render one retained package as `name==version`, or refuse the lock.

    A registry entry without a name or a version is a MALFORMED lock, not an
    exclusion: silently dropping it would shrink the audit perimeter without a
    single byte saying so, which is the exact defect this program was written to
    close one level up.
    """
    name = entry.get("name")
    version = entry.get("version")
    if not isinstance(name, str) or not name:
        raise LockError(f"{kind}: invalid structure (package without a name)")
    if not isinstance(version, str) or not version:
        raise LockError(f"{kind}: invalid structure (registry package without a version)")
    return f"{name}=={version}"


_PARSERS = {
    POETRY_LOCK: _parse_poetry,
    UV_LOCK: _parse_uv,
    PIPFILE_LOCK: _parse_pipfile,
}


def _discard(out: Path) -> None:
    """Remove a pre-existing `--out`. Absence is the desired state, not an error."""
    try:
        os.remove(out)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise LockError(f"--out: cannot remove a stale pins file ({exc.strerror})") from exc


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="py_lock_pins.py",
        description="Translate Python lockfiles into a pinned requirements file.",
    )
    parser.add_argument("--out", required=True, metavar="PATH",
                        help="pins file to write (removed when nothing is retained)")
    # `nargs='+'` and NOT a loop in the caller: `--out` TRUNCATES, so two calls
    # would leave only the second lock's pins behind and the run would audit a
    # perimeter smaller than the one it reports. One call, every lock.
    # Zero locks is refused by argparse itself (rc=2, stderr naming LOCK) — the
    # empty case never reaches this program's own logic.
    parser.add_argument("locks", nargs="+", metavar="LOCK",
                        help="poetry.lock, uv.lock or Pipfile.lock (any number)")
    args = parser.parse_args(argv)

    out = Path(args.out)
    pins: list = []
    excluded_root = 0
    excluded_dep = 0

    try:
        # READ EVERYTHING FIRST. Nothing below writes, so a refusal on the third
        # lock leaves exactly the same state as a refusal on the first.
        for raw in args.locks:
            path = Path(raw)
            kind = path.name
            parse = _PARSERS.get(kind)
            if parse is None:
                raise LockError(f"unknown lock kind: {_safe(kind)}")
            got, root_n, dep_n = parse(path)
            pins.extend(got)
            excluded_root += root_n
            excluded_dep += dep_n
    except LockError as exc:
        # Refusal: no file must survive, including a stale one from a past run.
        try:
            _discard(out)
        except LockError:
            pass  # the refusal already stands; a failed cleanup must not mask it
        print(f"py_lock_pins: {exc}", file=sys.stderr)
        return 2

    # EXACT duplicates across locks collapse; a genuine version CONFLICT does not
    # and both pins are kept, because `pip-audit --no-deps` audits each `==` line
    # it is given and silently picking a winner here would hide one of them.
    seen = set()
    unique = []
    for pin in sorted(pins):
        if pin not in seen:
            seen.add(pin)
            unique.append(pin)

    try:
        if unique:
            # Every line terminated, the last one included (contract, C42).
            out.write_text("".join(f"{pin}\n" for pin in unique), encoding="utf-8")
        else:
            _discard(out)
    except LockError as exc:
        print(f"py_lock_pins: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"py_lock_pins: --out: cannot write ({exc.strerror})", file=sys.stderr)
        return 2

    # THE contract line. One line, two counters, always emitted — including when
    # both are zero, because "no exclusion" is a measurement the caller logs, not
    # a silence it has to infer.
    print(f"excluded_root={excluded_root} excluded_dep={excluded_dep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
