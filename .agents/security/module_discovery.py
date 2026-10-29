#!/usr/bin/env python3
"""Discover dependency-manifest modules for multi-module SCA scans. stdlib only.

Families: npm (package.json) | java (pom.xml, build.gradle[.kts]) |
swift (Package.swift/.resolved, Podfile[.lock]) |
python (requirements.txt, pyproject.toml, Pipfile[.lock], poetry.lock, uv.lock).
Pruned dirs: node_modules, .git, dist, build, target, .agents — plus nested
checkouts the enclosing git index does not hold (linked worktree, unregistered
clone; T-00001083). Submodules and registered embedded repos are still scanned;
any git doubt scans too. Each prune or doubt is one line on stderr.

Ancestor-collapse (T-008):
- java/swift: a manifest dir whose ancestor holds a same-family manifest is a
  sub-module of the TOPMOST such ancestor (one reactor scan covers children).
- npm: collapses into the NEAREST npm ancestor ONLY if that ancestor declares
  workspaces ("workspaces" key in package.json or pnpm-workspace.yaml).
- python: NEVER collapses into an ancestor (T-00000292) — pip has no reactor or
  workspace concept, so two nested requirement dirs are two independent modules.
- Families never collapse into each other.
Known limit: a dir standing for one family while another of its families
collapsed elsewhere is scanned wholly (rare; double-scan accepted).

Collapse is a SCAN economy (one reactor build covers its children), never a
statement that the children do not exist: the folded paths are emitted as a 4th
column so consumers that must walk real code — the global code review — iterate
every module instead of reading only the aggregator root.

CLI: module_discovery.py --root DIR
Output: one line per module, tab-separated:
<slug>\t<path>\t<submodules>\t<comma-separated folded paths>
(root module: slug 'root', path '.'). Exit 0 even when no module is found.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ".sca-reports" kept for projects not yet migrated to .agents/state/local/sca-reports.
PRUNE = {"node_modules", ".git", "dist", "build", "target", ".agents", ".sca-reports"}

# ONE CARVE-OUT INSIDE `.agents`, AND IT IS SAFE BY CONSTRUCTION (T-00000197).
#
# `.agents` is pruned because in a CONSUMER project it holds the kit's VENDORED
# tooling: scanning it would audit the kit's own manifests as if they were the
# consumer's dependencies. That reasoning is right, and it left a hole in the
# kit's OWN repo — `.agents/ui-src/` is the dashboard's first-party source, with
# real dependencies that no scan ever reached. Measured: a HIGH advisory
# (nanoid < 3.3.18) sat in that lockfile while `sca-scan.sh` answered "no known
# ecosystem detected" for the whole repository.
#
# The exception costs consumers nothing, and not by luck: `ui-src` is stripped
# from the template (`.template-exclude`), so the directory does not exist in an
# adopting project — there is nothing there for this rule to reach.
AGENTS_KEEP = {"ui-src"}
FAMILIES = {
    "npm": {"package.json"},
    "java": {"pom.xml", "build.gradle", "build.gradle.kts"},
    "swift": {"Package.swift", "Package.resolved", "Podfile", "Podfile.lock"},
    "python": {"requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock",
               "poetry.lock", "uv.lock"},
}


def npm_declares_workspaces(dirpath):
    if (dirpath / "pnpm-workspace.yaml").is_file():
        return True
    try:
        return "workspaces" in json.loads(
            (dirpath / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


def _keep_dirs(rel, dirs):
    """Which child dirs os.walk should descend into, given the current rel path.

    `.agents` is descended into ONLY at the root, and once inside, only the
    AGENTS_KEEP entries survive — so the prune still holds everywhere else and
    the carve-out cannot widen by accident (a `.agents` nested deeper stays
    pruned whole).
    """
    if rel == Path(".agents"):
        return sorted(d for d in dirs if d in AGENTS_KEEP)
    return sorted(d for d in dirs
                  if d not in PRUNE or (d == ".agents" and rel == Path(".")))


# --- NESTED CHECKOUTS (T-00001083) --------------------------------------------
# A linked worktree or a clone dropped under the scanned root is a WHOLE copy of
# a repository: walking into it audits another branch's manifests as modules of
# this one. The detection BLOCK below is shared byte for byte with the
# T-00001073 walkers (`.agents/evals/test_repo_walk_census.py` proves it by
# fingerprint); the index GUARD after it is this module's own variant S.
# checkout imbrique : debut (T-00001073)
def _checkout_imbrique(chemin):
    marqueur = os.path.join(chemin, ".git")
    if os.path.isdir(marqueur):
        return True
    if not os.path.isfile(marqueur):
        return False
    try:
        with open(marqueur, encoding="utf-8", errors="replace") as fh:
            ligne = fh.readline(4096)
    except OSError:
        return False
    m = re.match(r"gitdir:\s*(.+?)\s*$", ligne)
    return bool(m and re.search(r"/worktrees/[^/]+/?$", m.group(1).replace("\\", "/")))
# checkout imbrique : fin (T-00001073)


# GUARD S — the SCA variant of the T-00001073 index guard. Guard M (the census)
# RAISES on doubt; for a dependency audit the safe direction is to SCAN, because
# `sca-scan.sh` drops this module's stderr AND rc on its default path — the one
# the SCA hook runs — where a raise would read as "no module below the root" and
# lose every submodule in silence (`--all-modules` lets stderr through). So: a
# checkout git TRACKS (submodule, registered embedded repo) is scanned; one the
# index does not hold is pruned; a root outside any repository prunes nothing
# (pilot default A1; under a non-repo root that a repository ENCLOSES, untracked
# checkouts are pruned like guard M does, S-00003875); git missing, timing out or
# answering an unexpected rc KEEPS the checkout. Every prune and every
# kept-in-doubt checkout is ONE stderr line — never a silent decision.
# garde d'index (T-00001073) : debut
_GARDE_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_GARDE_HORS_DEPOT = "not a git repository (or any"


def _garde_git(argv):
    """Run git with the queried repo's fsmonitor and hooks neutralised, inherited
    `GIT_*` dropped (config locations kept), C locale, 60 s bound (S-00003664).
    Output decoded as UTF-8 with `surrogateescape`, NEVER by this process's locale:
    under `core.quotePath=false` git prints a path's raw bytes, and a strict ASCII
    decode raised out of `discover()` (binôme 7+8, F2). Lossless, unlike `replace`.
    None when git cannot be run or does not answer in time."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    env["LC_ALL"] = "C"
    env["LANGUAGE"] = ""
    try:
        return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *argv],
                              capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
                              env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _garde_mode(root):
    """'git' (root in a work tree), 'none' (outside any repository) or 'doubt'."""
    p = _garde_git(["-C", os.fspath(root), "rev-parse", "--is-inside-work-tree"])
    if p is None:
        return "doubt"
    if p.returncode == 0:
        return "git" if p.stdout.strip() == "true" else "none"
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        return "none"
    return "doubt"


def _dire(chemin, verdict):
    print(f"module_discovery: nested checkout {chemin} {verdict}", file=sys.stderr)


def _elague(chemin, root, etat):
    """True when `chemin` is a nested checkout the enclosing index does not hold."""
    if not _checkout_imbrique(chemin):
        return False
    if "mode" not in etat:
        etat["mode"] = _garde_mode(root)
    if etat["mode"] == "none":
        return False
    if etat["mode"] == "git":
        p = _garde_git(["-C", os.path.dirname(chemin), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(chemin)])
        if p is not None and p.returncode == 0:
            if p.stdout.strip():
                return False
            _dire(chemin, "pruned (not in index)")
            return True
    _dire(chemin, "kept (git did not answer)")
    return False
# garde d'index (T-00001073) : fin


def discover(root):
    root = Path(root)
    candidates = {}
    etat = {}  # guard S: git mode of the root, computed at the FIRST nested checkout
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in _keep_dirs(Path(cur).relative_to(root), dirs)
                   if not _elague(os.path.join(cur, d), root, etat)]
        fams = {fam for fam, names in FAMILIES.items() if names & set(files)}
        if fams:
            candidates[Path(cur).relative_to(root)] = fams
    modules = {}  # rel Path -> {"families": set, "folded": set of collapsed rel Paths}
    for rel in sorted(candidates, key=lambda p: (len(p.parts), p.as_posix())):
        standing = set()
        for fam in sorted(candidates[rel]):
            # rel.parents is nearest-first (a/b/c -> [a/b, a, .])
            ancestors = [a for a in rel.parents
                         if a in modules and fam in modules[a]["families"]]
            owner = None
            if fam == "npm":
                for a in ancestors:  # nearest qualifying ancestor
                    if npm_declares_workspaces(root / a):
                        owner = a
                        break
            elif fam == "python":
                # Python NEVER collapses into an ancestor (T-00000292): pip has
                # no reactor/workspace concept, so a nested requirement dir is
                # its own module. Explicit branch, NOT a table entry — the
                # `elif ancestors` below would otherwise fold it to the topmost.
                owner = None
            elif ancestors:
                owner = ancestors[-1]  # topmost
            if owner is not None:
                modules[owner]["folded"].add(rel)
            else:
                standing.add(fam)
        if standing:
            entry = modules.setdefault(rel, {"families": set(), "folded": set()})
            entry["families"] |= standing
    return modules


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    args = ap.parse_args(argv)
    modules = discover(args.root)
    for rel in sorted(modules, key=lambda p: (len(p.parts), p.as_posix())):
        slug = "root" if rel == Path(".") else rel.as_posix().replace("/", "__")
        folded = sorted(p.as_posix() for p in modules[rel]["folded"])
        print(f"{slug}\t{rel.as_posix()}\t{len(folded)}\t{','.join(folded)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
