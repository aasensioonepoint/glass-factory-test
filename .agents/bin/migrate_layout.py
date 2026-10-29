#!/usr/bin/env python3
"""One-shot migration of a provisioned project from the flat `.agents/index/`
layout to the split `.agents/{bin,ref,state}` layout.

WHY this exists: the kit is provisioned INTO projects. Upgrading the kit ships the
new `bin/` and `ref/` files, but the project's own generated state (task board,
ledger, index artefacts, audit log, SCA reports) lives in the old flat directory
and only the project can move it. Doing that by hand loses TASKS.json sooner or
later, so it is a script.

Two classes of file, deliberately handled differently:

- STATE — project data (TASKS.json, LEDGER.json, SYMBOLS.md, AUDIT_LOG, …). Moved.
  Tracked files move with ``git mv`` so history and the checkpoint model survive.
- TOOLING — kit-shipped code and reference data (tasks.py, TOKEN_BUDGETS.md, …).
  Moved only when the new location is still empty; when the upgraded kit already
  provided it, the stale copy is REPORTED, never deleted. Deleting is the pilot's
  call, not this script's.

Idempotent: run it twice and the second run reports "nothing to do". It never
overwrites an existing destination — a collision is a conflict to look at, not a
file to clobber.

    python .agents/bin/migrate_layout.py [--root DIR] [--check | --apply]

``--check`` (the default) prints the plan and changes nothing. Exit code is 0 when
the plan is clean or empty, 1 when a conflict needs a human.
"""
from __future__ import annotations

import argparse
import errno
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OLD = Path(".agents") / "index"

# Project data — always moved.
STATE_MOVES = [
    ("CODEBASE_INDEX.md", Path(".agents") / "state" / "index"),
    ("SYMBOLS.md", Path(".agents") / "state" / "index"),
    ("INDEX_DELTA.json", Path(".agents") / "state" / "index"),
    ("CUSTOM_DOCS.md", Path(".agents") / "state" / "index"),
    ("TASKS.json", Path(".agents") / "state" / "board"),
    ("LEDGER.json", Path(".agents") / "state" / "memory"),
    ("AUDIT_LOG", Path(".agents") / "state" / "gates"),
    ("TASKS.md", Path(".agents") / "state" / "local"),
    ("LEDGER.md", Path(".agents") / "state" / "local"),
    ("RUN_LOG.md", Path(".agents") / "state" / "local"),
]

# Kit-shipped — moved only if the destination is still missing.
TOOLING_MOVES = [
    ("build_index.py", Path(".agents") / "bin"),
    ("build_index.test.sh", Path(".agents") / "bin"),
    ("tasks.py", Path(".agents") / "bin"),
    ("tasks.test.sh", Path(".agents") / "bin"),
    ("ledger.py", Path(".agents") / "bin"),
    ("test_ledger.py", Path(".agents") / "bin"),
    ("DOCS_REGISTRY.md", Path(".agents") / "ref"),
    ("TOKEN_BUDGETS.md", Path(".agents") / "ref"),
]

SHARD_GLOB = "SYMBOLS_*.md"
CONVENTIONS_GLOB = "CONVENTIONS_*.md"
OLD_REPORTS = Path(".sca-reports")
NEW_REPORTS = Path(".agents") / "state" / "local" / "sca-reports"

# Bounded retry on each move. ROOT CAUSE, measured: on Windows the antivirus /
# search indexer briefly holds a handle on a freshly written file, `shutil.move`
# falls back to copy + `os.unlink(src)` and that unlink raises PermissionError
# [WinError 32] — which stopped a real consumer's migration with 12 files already
# moved, i.e. a half-migrated layout. Same doctrine as L-00000115 (hot file under
# a reader -> bounded retry, never an infinite wait, never a swallowed failure).
# Off Windows the retry simply never triggers: those errno values are not what a
# POSIX rename returns for a busy file.
_MOVE_ATTEMPTS = 5
_MOVE_BACKOFF_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8)


def force_utf8_stdio() -> None:
    """Same guard as tasks.py: a Windows cp1252 console cannot encode the arrows
    and dashes this script prints, and a migration must not die on its own log."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def git(root: Path, *args: str) -> bool:
    """Run a git command; True on success. Never raises on a missing git."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def is_tracked(root: Path, rel: Path) -> bool:
    # `--` ends option parsing: a path that starts with a dash is a path, not a flag.
    return git(root, "ls-files", "--error-unmatch", "--", rel.as_posix())


def plan_moves(root: Path) -> tuple[list, list, list]:
    """Return (moves, conflicts, superseded). A move is (src_rel, dst_rel, kind)."""
    moves, conflicts, superseded = [], [], []
    old_dir = root / OLD

    def consider(name: str, dst_dir: Path, kind: str) -> None:
        src = old_dir / name
        if not src.is_file():
            return
        dst = root / dst_dir / name
        if dst.exists():
            (superseded if kind == "tooling" else conflicts).append(
                (OLD / name, dst_dir / name))
            return
        moves.append((OLD / name, dst_dir / name, kind))

    for name, dst in STATE_MOVES:
        consider(name, dst, "state")
    if old_dir.is_dir():
        for shard in sorted(old_dir.glob(SHARD_GLOB)):
            consider(shard.name, Path(".agents") / "state" / "index", "state")
        for conv in sorted(old_dir.glob(CONVENTIONS_GLOB)):
            consider(conv.name, Path(".agents") / "ref", "tooling")
    for name, dst in TOOLING_MOVES:
        consider(name, dst, "tooling")

    if (root / OLD_REPORTS).is_dir():
        if (root / NEW_REPORTS).exists():
            conflicts.append((OLD_REPORTS, NEW_REPORTS))
        else:
            moves.append((OLD_REPORTS, NEW_REPORTS, "reports"))
    return moves, conflicts, superseded


def is_transient_lock(exc: OSError) -> bool:
    """True only for the transient "someone still holds this file" family.
    WinError 32 (sharing violation) and 5 (access denied) are what an AV or
    indexer handle surfaces as; when there is no winerror (POSIX) fall back to
    EACCES/EPERM. Anything else — a real ENOENT, a full disk, a collision — is
    not retried, it is a bug or a conflict and must surface immediately."""
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in (5, 32)
    return exc.errno in (errno.EACCES, errno.EPERM)


def remove_tree_or_file(path: Path) -> None:
    """Delete `path` whatever it is — the file/directory fork spelled ONCE, so
    no phase below can forget one of the two shapes."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        os.unlink(path)


def _discard(path: Path) -> None:
    """Best-effort removal of a temporary we own. Swallows OSError ON PURPOSE:
    it runs while the real exception is in flight and must never replace it. A
    leftover is named `<dst>.part-<pid>` and the next run clears it."""
    try:
        remove_tree_or_file(path)
    except OSError:
        pass


def _retrying(op, attempts: int, backoff: tuple[float, ...]) -> int:
    """Run `op()` under the bounded backoff, retrying ONLY a transient lock.
    Returns the attempts used. Anything else, and the exhausted bound itself,
    re-raises the ORIGINAL exception untouched."""
    for attempt in range(attempts):
        try:
            op()
            return attempt + 1
        except OSError as exc:
            if attempt == attempts - 1 or not is_transient_lock(exc):
                raise
            time.sleep(backoff[min(attempt, len(backoff) - 1)])
    raise AssertionError("unreachable: the loop either returns or raises")


def move_with_retry(src: Path, dst: Path, attempts: int = _MOVE_ATTEMPTS,
                    backoff: tuple[float, ...] = _MOVE_BACKOFF_SECONDS) -> int:
    """Move `src` onto `dst` (file or directory) with a bounded retry on a held
    handle. Returns the number of attempts used (1 = no retry anywhere).

    NOT `shutil.move`, deliberately: its cross-volume fallback is
    copytree-then-rmtree, and copytree CREATES the destination before it has
    copied every child. So "the destination exists" is NOT proof that the copy
    completed, and a retry keyed on that can delete a source whose destination
    is partial — silent, permanent loss of data this module's docstring calls
    unregenerable (CWE-367/459). Four explicit phases instead, of which only the
    non-destructive ones are retried:

      (a) `os.rename` — nominal, atomic, same volume.                  RETRIED.
      (b) cross-volume fallback: copy into a SIBLING temporary under
          `dst.parent`. NOT retried: a failure here discards the
          temporary and re-raises, with `src` untouched.
      (c) promote the temporary onto `dst` by rename — the copy is
          complete before the final name ever appears.                 RETRIED.
      (d) only now, remove `src`.                                      RETRIED.

    Worst case is therefore a duplicate (dst complete, src still there) plus a
    loud exception — never a source deleted against a partial destination."""
    if dst.exists():
        # This module never overwrites; plan_moves already filters collisions
        # out, so reaching this means the tree moved under us mid-run. On POSIX
        # os.rename would clobber silently, so the guard is not decoration.
        raise FileExistsError(errno.EEXIST, "destination already exists", str(dst))

    try:
        return _retrying(lambda: os.rename(src, dst), attempts, backoff)
    except OSError as exc:
        if is_transient_lock(exc):
            raise  # the bound is exhausted on a held handle — surface it
        # Anything else — EXDEV above all — means rename cannot do this move.

    tmp = dst.with_name(f"{dst.name}.part-{os.getpid()}")
    if dst.parent.is_dir():
        for entry in dst.parent.iterdir():
            if entry.name.startswith(f"{dst.name}.part-"):
                remove_tree_or_file(entry)  # orphan from a run that died mid-copy
    try:
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, tmp, symlinks=True)
        else:
            shutil.copy2(src, tmp, follow_symlinks=False)
    except BaseException:
        _discard(tmp)
        raise
    extra = _retrying(lambda: os.rename(tmp, dst), attempts, backoff) - 1
    extra += _retrying(lambda: remove_tree_or_file(src), attempts, backoff) - 1
    return 1 + extra


def apply_move(root: Path, src_rel: Path, dst_rel: Path) -> str:
    (root / dst_rel).parent.mkdir(parents=True, exist_ok=True)
    if is_tracked(root, src_rel) and git(root, "mv", "--", src_rel.as_posix(), dst_rel.as_posix()):
        return "git mv"
    used = move_with_retry(root / src_rel, root / dst_rel)
    # A move that needed a retry is worth seeing in the log — the handle that
    # forced it may still be around for the next file.
    return "mv" if used == 1 else "mv+retry"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    ap.add_argument("--apply", action="store_true",
                    help="perform the moves (default is a dry run)")
    ap.add_argument("--check", action="store_true",
                    help="dry run — the default, accepted for symmetry")
    args = ap.parse_args(argv)
    force_utf8_stdio()
    root = Path(args.root).resolve()

    moves, conflicts, superseded = plan_moves(root)
    if not moves and not conflicts and not superseded:
        print("layout: already migrated — nothing to do")
        return 0

    label = "APPLY" if args.apply else "CHECK (dry run)"
    print(f"layout migration — {label}  root={root}")
    for src, dst, kind in moves:
        how = apply_move(root, src, dst) if args.apply else "would move"
        print(f"  [{kind:<7}] {how:<8} {src.as_posix()}  ->  {dst.as_posix()}")
    for src, dst in superseded:
        print(f"  [stale  ] keep     {src.as_posix()}  (superseded by {dst.as_posix()}) "
              f"— delete it yourself once you have checked it")
    for src, dst in conflicts:
        print(f"  [CONFLICT] {src.as_posix()}  and  {dst.as_posix()}  both exist "
              f"— merge by hand, nothing was moved")

    left = root / OLD
    if args.apply and left.is_dir() and not any(left.iterdir()):
        left.rmdir()
        print(f"  removed empty {OLD.as_posix()}/")
    elif left.is_dir():
        print(f"  note: {OLD.as_posix()}/ still holds files (untracked leftovers or "
              f"stale kit copies) — review, then remove it")

    if not args.apply:
        print("\nre-run with --apply to perform the moves")
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
