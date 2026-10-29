#!/usr/bin/env python3
"""Is a module path one this project forbids editing?  (T-00000200)

Exit codes, consumed by `sca-scan.sh`:
    0 = protected   -> its findings are TRACKED, never gating
    1 = not protected
    2 = cannot tell -> caller exempts nothing and says so

WHY THIS QUESTION IS ASKED AT ALL. Widening the SCA scan to every module is
right, and it carries a failure mode the kit would inflict on its own users: in
a consumer project part of the tree is PROTECTED — `.agents/bin/` and whatever
that project lists in `.agents/protected-paths.local` — precisely because it is
vendored code they must not edit. An advisory landing there is unfixable BY
CONSTRUCTION: they cannot bump it, so a gate that goes NO-GO on it stays red
forever and blocks every use of the kit. That is not a security control, it is a
denial of service delivered by us. The doctrine already classes a non-actionable
finding as class 3 — list and track, never hard-block — and this is how a module
gets recognised as one.

THE PREFIX LIST IS READ FROM THE CANONICAL GUARD, NEVER COPIED. A second list
would drift from the one that actually denies the edits, and a project would end
up exempted here while still blocked there, or the reverse. Both host copies are
tried because neither directory is guaranteed to exist in a given project.

AMBIGUITY RESOLVES TO NOT-PROTECTED. Exempting on a guess would silence a real,
actionable finding; refusing to exempt only keeps today's behaviour, and the
caller announces it.

CLI: protected_module.py --root DIR PATH
"""
import argparse
import sys
from pathlib import Path

HOST_GUARD_DIRS = (".codex/hooks", ".gemini/hooks")

PROTECTED = 0
NOT_PROTECTED = 1
UNKNOWN = 2


def guard_prefixes(root):
    """Protected prefixes from the canonical guard, or None if unreadable."""
    for host in HOST_GUARD_DIRS:
        directory = Path(root) / host
        if not (directory / "protect_paths.py").is_file():
            continue
        sys.path.insert(0, str(directory))
        try:
            import protect_paths as pp
        except Exception:
            sys.path.pop(0)
            continue
        try:
            extra = tuple(pp.extra_prefixes())
        except Exception:
            # A malformed project list must not make the whole probe unreadable:
            # the built-ins are still authoritative and still worth applying.
            extra = ()
        return tuple(p for p in tuple(pp.PROTECTED_PREFIXES) + extra if p)
    return None


def classify(root, path):
    module = str(path).replace("\\", "/").strip()
    while module.startswith("./"):
        module = module[2:]
    module = module.strip("/")
    # The repository root is never "a protected module": exempting it would
    # exempt the whole project in one step, which is the opposite of the intent.
    if not module or module == ".":
        return NOT_PROTECTED
    prefixes = guard_prefixes(root)
    if prefixes is None:
        return UNKNOWN
    probe = module.lower() + "/"
    return PROTECTED if any(probe.startswith(p) for p in prefixes) else NOT_PROTECTED


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("path")
    args = ap.parse_args(argv)
    return classify(args.root, args.path)


if __name__ == "__main__":
    sys.exit(main())
