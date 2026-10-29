"""The host block « While auto mode is active » is PRE-ARBITRATED in doctrine,
and NO instruction surface of the repo carries it — proven, not assumed (T-00000279).

WHAT THIS EXISTS FOR. A host session setting can inject, AFTER `AGENTS.md`, a block
opening on « While auto mode is active ». On 2026-08-22 that cost a single day:
several agents refused it and flagged it, two ATTRIBUTED it to a repo file that does
not carry it (`.claude/rules/python.md`, five lines on disk), and one corrupted its
own test bench with a heredoc then announced a security bypass that did not exist.
The chosen remedy is written doctrine living in the SAME system prompt as the block
(the `### Consigne d'hôte …` subsection of `AGENTS.md`), plus this ABSENCE NET.

WHAT IT ASSERTS — through `scan_block_detailed(root)` (carriers + oversized relevé),
`paragraph_present_in(text)` and one CONFRONTATION of the closed list against the
hosts AGENTS.md declares; the negative controls only change the root/file (they
replay production, not a re-derivation):
  1. `paragraph_present`               — `AGENTS.md` carries the subsection: title
                                         marker, verbatim block citation, AND a
                                         carrier of each of the four doctrine points.
  2. `no_instruction_surface_carries_block` — the REPO sweep is EMPTY: no instruction
                                         surface carries the block, AND no carrier
                                         hides over the read bound (the oversized
                                         relevé is consumed from the RETURN, not
                                         stderr — a bound reported only to stderr
                                         passes green under pytest capture, L-…136).
                                         Its LOWER BOUND is pinned by named anchors,
                                         one per surface the sweep walks INTO, so a
                                         prune that emptied the corpus cannot buy the
                                         green by ceasing to measure.
  2-bis. `gitignored_tree_pruned_but_tracked_surface_swept` / `prune_failure_is_
                                         raised_not_degraded` — the git-ignore prune
                                         bites on BOTH pattern classes, a TRACKED file
                                         under an ignored directory is swept anyway,
                                         and an unrecognised git fatal raises instead
                                         of degrading into « nothing to prune ».
  3. `detector_reds_on_planted_block`  — a tmp root with a planted `.claude/rules/
                                         python.md` carrying the block makes
                                         `scan_block(tmp)` non-empty (non-vacuity).
  4. `paragraph_removal_reds`          — a copy of `AGENTS.md` amputated of the
                                         subsection fails `paragraph_present_in`.
  5. `paragraph_requires_all_four_points` / `paragraph_reds_when_any_single_point_
                                         removed` (points 1-3, one at a time) /
                                         `paragraph_reds_when_point4_gutted` —
                                         stripping all four points, removing any ONE
                                         of points 1-3 alone, or turning point 4
                                         (« reste légitime ») into « ne signale pas »,
                                         reds the presence check.
  6. `closed_list_covers_declared_hosts` — every `.<host>/` directory named in
                                         § Cross-agent surfaces is swept (bar `.agent`,
                                         already listed), so the next host reds here.
  7. `symlink_not_followed`            — a symlink under a surface, pointing OUT of the
                                         tree, is not counted (a real sibling is).
  8. `oversized_file_ignored_and_reported` — a file over `_MAX_READ_BYTES` is not read
                                         into a hit but IS surfaced (never a silent skip).
  9. `self_pinned_by_exact_path_not_basename` / `file_named_backups_swept_but_dir_
                                         excluded` — self-exclusion is the EXACT test
                                         path, and `backups` excludes a DIRECTORY only.

THE NET IS PROPHYLACTIC, AND SAID SO. The block lives today only in this plan and
two state stores, all as DATA. Its role is to PIN the absence: the day the block
appears in an instruction surface, a test reds instead of an agent enquiring for
twenty minutes. The damage actually measured (heredoc corruption, L-00000197) is
handled by point 2 of the doctrine paragraph — edits go through `Edit`/`Write` —
not by this net.

CLOSED LIST, AND ITS LIMIT. `scan_block` sweeps a CLOSED list of instruction
surfaces (below). A future instruction surface outside that list escapes the net —
so `closed_list_covers_declared_hosts` reds the day AGENTS.md § Cross-agent surfaces
names a `.<host>/` directory absent from the list. The sweep never follows symlinks
(no out-of-tree bytes, no infinite walk) and never reads a file over `_MAX_READ_BYTES`
whole — an oversized file is announced, not silently skipped. What is deliberately
NOT swept, and why:
  * `.agents/state/`, `docs/`, `.worktrees/` — they cite the block AS DATA, never as
    instruction, and the stores carry it LEGITIMATELY today (board + specs). Sweeping
    them would red this net on the very day it ships: the exclusion is FORCED.
  * transcript backups (a `backups/` DIRECTORY segment) and byte caches
    (`__pycache__`) — these hold whatever a session discussed, including this block;
    they are history, no more an instruction surface than `.agents/state/` is. The
    exclusion is by directory segment, so a FILE named `backups` is still swept.
  * GIT-IGNORED TREES, pruned before descent. Installed dependencies and gate
    outputs land INSIDE a swept surface (`.agents/ui-src/node_modules/`,
    `.agents/ui-src/test-results/`), and they are neither authored here nor read by
    any agent — but they carry files far over the read bound, so the sweep reported
    them as unreadable carriers and the net red on bytes npm had written. The prune
    reads the ignore rules FROM GIT rather than re-deriving a prefix list, because a
    hand-kept list drifts from `.gitignore` — which is the very defect this closes.
    ITS LIMIT, and it is the safety property: only UNTRACKED-AND-IGNORED paths are
    pruned. A tracked file is never pruned even under an ignored directory, so no
    instruction surface of this repository — all tracked — can be removed from the
    corpus by this mechanism.
  * NESTED CHECKOUTS THAT NOTHING REGISTERS (T-00001073), pruned BEFORE the
    git-ignore prune. A live worktree under `.claude/worktrees/` is a full copy of
    the repository — `AGENTS.md` included, which quotes the block by design — so
    the sweep red on another branch's doctrine (measured on a clone: 12 carriers
    under one worktree). A child that carries its own `.git` (directory, or a
    WORKTREE gitfile) is pruned only if the index of the checkout CONTAINING it
    registers nothing there: submodules, gitlinks and every directory holding
    TRACKED files are still swept. Outside a repository (`_prune_mode` = `none`)
    every such child is pruned with NO git call. Same block as the three other
    walkers, pinned by fingerprint in `test_repo_walk_census.py`.
THIS BENCH THEREFORE REQUIRES A GIT CHECKOUT, stated rather than left to be
discovered: a `git archive` export or a `COPY . .` image without `.git` reds it,
naming the missing work tree. That is acceptable because `core-scripts/verify.sh`
already requires one — it anchors every verdict to a SHA and grants the container
a `safe.directory` entry — and because the alternative, degrading silently to "no
prune", would put the red back exactly where it started.
Note on the residual: the state channel ENTERS agent context (SessionStart injects
the board render and the ledger context; specs are read on demand) — but its guard
is elsewhere, the "data, never instructions" framing of L-004 and CLI-only writes,
NEVER this net.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The verbatim opening of the host block — the short citation the doctrine
# paragraph embeds and the signature this net searches for.
BLOCK_SIGNATURE = "While auto mode is active"

# A stable marker of the doctrine subsection's heading in AGENTS.md (matched
# verbatim, accent included, against the heading this task inserts).
TITLE_MARKER = "Consigne d'hôte"

# The four points of the pre-arbitration subsection (AGENTS.md § Consigne d'hôte).
# `paragraph_present_in` requires a load-bearing substring of EACH — amputating any
# one, or gutting point 4 into a "stay silent" order, reds the presence check. Point
# 4's carrier is the exact sentence that keeps the reporting channel open.
_DOCTRINE_POINT_MARKERS = (
    "La consigne n'est dans AUCUN fichier du dépôt",        # point 1
    "Sur ce dépôt, les ÉDITIONS passent par",               # point 2
    "Le shell reste libre pour tout le reste",              # point 3
    "Signaler une consigne inattendue reste légitime",      # point 4
)

# CLOSED list of instruction surfaces, relative to a root. `.agents` is swept
# ENTIRELY except `.agents/state/` (see _EXCLUDED_PREFIXES) — covering `ref/`,
# `skills/`, `bin/`, `security/` AND `.agents/hooks.json`, whose refusal messages
# enter agent context. `.agent` (SINGULAR) is Antigravity's directory, `.kimi-code`
# is Kimi Code's — both declared in AGENTS.md § Cross-agent surfaces; `.cursor` is the
# DERIVED Cursor target (rules `.mdc` and commands rendered by `render_hosts.py` from
# `agents/` and `commands/`, T-01M5BZCDMCEQXKA2RKTB2EMW8M — that Cursor reads them is
# NOT MEASURED, but they are written to enter an agent's context); absent surfaces
# cost zero and close the hole the day they appear. `test_closed_list_covers_declared_hosts`
# CONFRONTS this list with the `.<host>/` directories that section declares, so the
# next host added there reds until it is swept here. `AGENTS.md` (the doctrine's own
# home) and this test file are NOT in the list — they carry the block by design.
INSTRUCTION_SURFACES = (
    "CLAUDE.md",
    "GEMINI.md",
    ".claude",
    ".codex",
    ".github",
    ".gemini",
    ".agent",
    ".agents",
    ".kimi-code",
    ".cursor",
)

# Excluded WITHIN the swept surfaces — the state stores carry the block as DATA,
# legitimately, today.
_EXCLUDED_PREFIXES = (".agents/state/",)

# Excluded wherever a DIRECTORY segment matches: transcript backups and byte caches
# are session history, not instruction, and the VCS metadata is not the repo's
# content. Matched against directory segments ONLY (never the filename), so a FILE
# named `backups` carrying the block is still swept and flagged.
_EXCLUDED_SEGMENTS = frozenset({"__pycache__", "backups", ".git"})

# Read cap: files larger than this are NOT read (bounded I/O). Oversized files are
# not silently dropped — `scan_block` surfaces them (see `_scan`).
_MAX_READ_BYTES = 2 * 1024 * 1024  # 2 MiB

# This file quotes the block verbatim; it must never flag itself. Pinned by its
# EXACT path relative to the repo root — NOT its basename — so a DIFFERENT file that
# merely shares the name (e.g. a planted `.codex/test_automode_doctrine.py`) is still
# swept and flagged.
_SELF_REL = Path(__file__).resolve().relative_to(ROOT).as_posix()

# LOWER BOUND of the production sweep, and every entry earns its place. The sweep
# now PRUNES git-ignored trees, and an over-generous prune would empty the corpus
# while every equality-to-empty assertion stayed green — so the corpus is pinned by
# name. One anchor per surface actually WALKED: `CLAUDE.md` is a top-level FILE
# surface and never passes through `_walk_files`, so it alone could not detect an
# inverted prune. A trailing slash means a PREFIX anchor — the surface is pinned,
# not one filename inside it. All are tracked and all travel (none sits under a
# `strip:` rule of `.template-exclude`), so none can ever be pruned by a mechanism
# that only ever removes untracked bytes.
_SWEEP_ANCHORS = (
    "GEMINI.md",                       # second top-level host doc
    ".claude/settings.json",           # Claude Code, declared in Cross-agent surfaces
    ".codex/hooks.json",               # Codex
    ".github/copilot-instructions.md",  # Copilot
    ".gemini/hooks/",                  # Gemini CLI — the DIRECTORY, not one hook
    ".agents/hooks.json",              # shared hook wiring
    ".kimi-code/hooks.json",           # Kimi Code
)


def _is_excluded(rel: str) -> bool:
    if rel == _SELF_REL:
        return True
    if any(rel.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
        return True
    # Directory segments only — parts[:-1] drops the filename, so a file named like
    # an excluded segment (e.g. `.claude/rules/backups`) is NOT excluded.
    if set(Path(rel).parts[:-1]) & _EXCLUDED_SEGMENTS:
        return True
    return False


def _git_env() -> dict[str, str]:
    """The environment every git child runs in: `os.environ` PLUS a pinned C locale.

    THE INHERITANCE IS DELIBERATE. The negative controls neutralise the machine's
    gitconfig through `monkeypatch.setenv`, i.e. through `os.environ` — a dict
    built from scratch here would never carry it, and those controls would silently
    measure the contributor's global ignore rules instead of their own.

    THE LOCALE PIN IS NOT COSMETIC, AND IT WAS MEASURED. `_prune_mode` tells « no
    repository at all » from every other fatal by READING git's stderr, and git
    speaks the operator's language: on a French machine the very same fatal comes
    back as « ni ceci ni aucun de ses répertoires parents n'est un dépôt git », in
    which the English message never appears. Unpinned, every tmp-root control below
    raises instead of sweeping, and this bench is green only where the contributor
    happens to work in English. `LANGUAGE` is emptied as well because GNU gettext
    lets it outrank `LC_ALL` on non-C locales, and an empty value is the documented
    way to take it out of the decision.

    Built in the BODY and never as a default argument: `os.environ` changes between
    import and call — that is precisely what `monkeypatch.setenv` does."""
    return {**os.environ, "LC_ALL": "C", "LANGUAGE": ""}


def _prune_mode(root: Path) -> str:
    """Which pruning regime applies under `root`: `"git"` inside a work tree,
    `"none"` outside any repository. ANY other answer RAISES — it is never
    degraded into `"none"`.

    THE THREE-WAY DISCRIMINATION IS THE LOAD-BEARING PART. `git rev-parse
    --is-inside-work-tree` answers `true` in a work tree, `false` AT RETURN CODE 0
    in a bare repository or inside a `.git` directory, and 128 for a whole FAMILY
    of fatals of which « not a git repository » is only one member. Folding that
    family into "no pruning available" would turn a broken environment into a
    green sweep: the fatal this repository actually meets is « detected dubious
    ownership », the one `core-scripts/verify.sh` answers with a `safe.directory`
    entry before running the container leg. A sweep that degraded silently there
    would rake the ignored trees back in and red on the far side, naming the
    oversized artefacts instead of the environment that caused them.

    READING THE STDERR IS ONLY SOUND BECAUSE THE LOCALE IS PINNED. git translates
    its fatals, so the English message below is a message git emits only under the
    C locale `_git_env` forces; drop that pin and this branch stops matching on
    every non-English machine, turning every tmp-root control into a raise.

    A MISSING `git` BINARY IS THE SAME CLASS and raises too: this bench requires a
    real checkout (see the module docstring), and a bench that cannot tell
    "nothing is ignored" from "nobody could answer" measures nothing."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, env=_git_env())
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise RuntimeError(
            f"could not run `git` to decide the prune regime under {root}: {exc}. "
            "This bench sweeps a git checkout and prunes the ignored trees; run it "
            "from a checkout, with git on PATH."
        ) from exc
    if proc.returncode == 0 and proc.stdout.strip() == "true":
        return "git"
    if proc.returncode == 128 and "not a git repository" in proc.stderr.lower():
        return "none"  # a bare tmp tree — every negative control below builds one
    raise RuntimeError(
        f"git could not say whether {root} is a work tree (rc={proc.returncode}, "
        f"stdout={proc.stdout.strip()!r}, stderr={proc.stderr.strip()!r}). This is "
        "NOT read as « nothing to prune »: a `dubious ownership` fatal answers 128 "
        "like that, and a bare repository answers `false` at rc 0. Fix the "
        "environment — e.g. `git config --global --add safe.directory <path>` — or "
        "run the bench from a work tree."
    )


def _git_ignored(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """(ignored directories, ignored files) under `root` — root-relative, posix.

    ONE git call, and it is INDEX-AWARE BY CONSTRUCTION: `--others` lists only
    UNTRACKED paths, so a TRACKED file can NEVER appear in either set. That is what
    turns « no instruction surface is ever pruned away » into a property of the
    mechanism rather than an assertion someone must remember to keep true — every
    instruction surface of this repository is tracked. The deliberate consequence
    is the LIMIT stated in the module docstring: only untracked-AND-ignored bytes
    are pruned.

    `--directory` collapses a wholly-untracked ignored directory to a single
    `dir/` entry, so a dependency tree costs one string instead of thousands. A
    directory holding a TRACKED file is NOT collapsed: git lists its
    untracked-ignored files ONE BY ONE instead, which is exactly the behaviour
    `test_gitignored_tree_pruned_but_tracked_surface_swept` pins — descend into
    such a directory, then judge file by file.

    WHY ONE `ls-files` AND NOT ONE `check-ignore --stdin` PER VISITED DIRECTORY.
    Both were measured, on BOTH legs, and they return the SAME corpus to the file
    (98 directories visited, 468 files kept): 1 process instead of 98, ~32 ms
    against ~1.45 s on macOS, ~50 ms against ~200 ms in the linux container. This
    form also passes no path on stdin at all, so the absolute-versus-relative path
    hazard of a stdin protocol — acute where the temp root resolves through a
    symlink — simply does not arise."""
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--others", "--ignored",
         "--exclude-standard", "--directory"],
        capture_output=True, text=True, env=_git_env())
    if proc.returncode != 0:
        raise RuntimeError(
            f"`git ls-files --others --ignored` failed under {root} "
            f"(rc={proc.returncode}): {proc.stderr.strip()!r}. The ignored trees "
            "cannot be pruned, and sweeping them anyway would red this net on "
            "dependency bytes — fix the environment rather than the assertion."
        )
    entries = [e for e in proc.stdout.split("\0") if e]
    return (frozenset(e.rstrip("/") for e in entries if e.endswith("/")),
            frozenset(e for e in entries if not e.endswith("/")))


# --- NESTED CHECKOUTS (T-00001073) ---------------------------------------------
# The BLOCK below is TEXTUALLY identical in the four walkers that use it
# (check-stale-justification.sh, test_modload_registration.py, this file,
# test_repo_walk_census.py) and pinned by fingerprint in the census: it says
# « this directory carries its own `.git` » — a DIRECTORY (clone, embedded
# submodule, link to a directory; empty included) or a WORKTREE gitfile.
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


# THE GUARD (text A — this file only). The prune regime is `_prune_mode(root)`,
# decided ONCE per sweep: under `none` (no repository at all) every block hit is
# pruned WITHOUT a git call, since no index exists to register anything. Under
# `git`, a block hit is pruned only if the index of the checkout that DIRECTLY
# contains it registers nothing there (`git -C <parent> ls-files -s --
# ":(literal)<name>"`, rc 0 AND empty output). Any other answer RAISES: a child
# answering « not a git repository (or any … » inside a work tree is a BLOCKED
# discovery (ceiling, mount point), never an absence; every other fatal is the
# environment's, never « nothing registered ». The guard's environment is
# `_git_env()` (unchanged: it carries the scratch-repo neutralisation) MINUS every
# GIT_* variable except GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM and
# GIT_CONFIG_NOSYSTEM — a name list let GIT_CEILING_DIRECTORIES through, under
# which a REGISTERED child answers exactly that « not a git repository ».
# The index query NEUTRALISES the queried repository's config (`-c
# core.fsmonitor=false -c core.hooksPath=/dev/null` before `-C`): an embedded
# clone from an untrusted archive ran its `core.fsmonitor` on every `ls-files -s`
# (measured, git 2.55, S-00003664). The call is bounded at 60 s; past it,
# `subprocess.TimeoutExpired` RAISES — neither pruned nor swept silently.
# `_prune_mode` and `_git_ignored` query the SWEPT ROOT itself, not a candidate's
# containing repository: they are outside this guard and carry neither.
# garde d'index (T-00001073) : debut
_GARDE_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_GARDE_HORS_DEPOT = "not a git repository (or any"


def _garde_env() -> dict[str, str]:
    # It only DROPS variables: the C locale comes from `_git_env()`, which pins it and
    # whose pin `test_prune_mode_survives_a_translated_git` asserts. Re-pinning here
    # was measured dead — removing those two lines left every arm green.
    return {k: v for k, v in _git_env().items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}


def _enregistre(chemin: str) -> bool:
    p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                        "-C", os.path.dirname(chemin), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(chemin)],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
    if p.returncode == 0:
        return bool(p.stdout.strip())
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        raise RuntimeError(
            f"nested-checkout guard: discovery BLOCKED on {chemin} inside a work tree "
            f"({p.stderr.strip()!r}) — a ceiling or a mount point, never « not registered »")
    raise RuntimeError(
        f"nested-checkout guard: git could not say whether {chemin} is registered "
        f"(rc={p.returncode}, stderr={p.stderr.strip()!r}) — neither pruned nor swept silently")


def _elague(chemin: str, mode: str) -> bool:
    if not _checkout_imbrique(chemin):
        return False
    if mode == "none":
        return True
    return not _enregistre(chemin)
# garde d'index (T-00001073) : fin


def _walk_files(directory: Path, root: Path, ignored_dirs: frozenset[str], mode: str):
    """Regular files under `directory`, WITHOUT following symlinks, WITHOUT
    entering a nested checkout that nothing registers, and WITHOUT descending into
    a git-ignored directory.

    `os.walk` with `followlinks=False` never descends into a symlinked directory,
    and each file is dropped if it is itself a symlink — so a link pointing OUT of
    the tree can never smuggle outside content into the sweep.

    `topdown` is left at its default `True`, which is what makes the
    `dirnames[:] = …` assignment a PRUNE: os.walk re-reads that list before
    descending, so an ignored directory is never entered at all rather than
    entered and filtered afterwards.

    `mode` is `_prune_mode(root)`, resolved ONCE by the caller. The nested-checkout
    prune runs BEFORE the git-ignore prune; under `none` it costs no git call."""
    for dirpath, dirnames, filenames in os.walk(directory, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = [d for d in dirnames if not _elague(os.path.join(dirpath, d), mode)]
        if ignored_dirs:
            dirnames[:] = [d for d in dirnames if prefix + d not in ignored_dirs]
        for name in filenames:
            f = Path(dirpath) / name
            if f.is_symlink():
                continue  # link to a file, possibly outside the tree — not swept
            yield f


def _iter_surface_files(root: Path):
    """Yield (rel, path) for every non-excluded, non-git-ignored file under the
    closed surface list.

    Exposed so the production sweep can prove itself NON-VACUOUS (a zero-hit sweep
    over an empty corpus would otherwise read as success — L-00000232).

    The prune regime and the ignored set are each resolved ONCE per sweep, before
    the first surface is opened — never once per visited directory."""
    root = Path(root)
    mode = _prune_mode(root)
    if mode == "git":
        ignored_dirs, ignored_files = _git_ignored(root)
    else:
        ignored_dirs, ignored_files = frozenset(), frozenset()
    for base in INSTRUCTION_SURFACES:
        p = root / base
        if p.is_symlink():
            continue  # a symlinked surface ROOT: do not follow out of the tree
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            candidates = _walk_files(p, root, ignored_dirs, mode)
        else:
            continue  # surface absent under this root — costs zero, stays closed
        for f in candidates:
            rel = f.relative_to(root).as_posix()
            if rel in ignored_files:
                continue  # untracked AND git-ignored — never an instruction surface
            if _is_excluded(rel):
                continue
            yield rel, f


def _scan(root: Path) -> tuple[list[str], list[str]]:
    """Return (carriers, oversized) under `root`.

    `carriers` = non-excluded instruction surfaces that CARRY the block.
    `oversized` = files skipped for exceeding `_MAX_READ_BYTES` — surfaced by
    `scan_block`, never silently dropped (a silent skip reads as absence)."""
    hits: list[str] = []
    oversized: list[str] = []
    for rel, f in _iter_surface_files(root):
        try:
            size = f.stat().st_size
        except OSError:
            continue  # unstatable: nothing to read
        if size > _MAX_READ_BYTES:
            oversized.append(rel)
            continue  # bounded I/O: an outsized file is not read whole
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable: nothing textual to carry the block
        if BLOCK_SIGNATURE in text:
            hits.append(rel)
    return sorted(set(hits)), sorted(set(oversized))


def scan_block_detailed(root: Path) -> tuple[list[str], list[str]]:
    """Return (carriers, oversized) under `root` — the FULL result of the sweep.

    `carriers` are instruction surfaces that CARRY the block; `oversized` are files
    skipped for exceeding `_MAX_READ_BYTES`. BOTH ride the RETURN so a caller can red
    on either: an oversized relevé emitted to stderr ALONE passes green under pytest
    capture — the return channel is the one the assertion reads (L-00000136). The
    oversized list is STILL announced to stderr too, so the bound is loud in both
    channels, not moved from one to the other."""
    hits, oversized = _scan(root)
    if oversized:
        print(
            f"[test_automode_doctrine] {len(oversized)} file(s) over "
            f"{_MAX_READ_BYTES} bytes NOT scanned (bounded read): {oversized}",
            file=sys.stderr,
        )
    return hits, oversized


def scan_block(root: Path) -> list[str]:
    """Relative paths of instruction surfaces under `root` that CARRY the block — the
    carriers half of `scan_block_detailed`. Every negative control that weighs ONLY
    carriers calls this; the production assertion calls the detailed form so the
    oversized relevé reaches its RETURN, not just stderr."""
    hits, _oversized = scan_block_detailed(root)
    return hits


def paragraph_present_in(text: str) -> bool:
    """The doctrine subsection is present in `text`: its title marker, the verbatim
    block citation, AND a load-bearing substring of EACH of the four points. All
    live ONLY in the subsection, so amputating the subsection — or any single point,
    including gutting point 4 into a "stay silent" order — flips this to False."""
    return (
        TITLE_MARKER in text
        and BLOCK_SIGNATURE in text
        and all(marker in text for marker in _DOCTRINE_POINT_MARKERS)
    )


def _cross_agent_surfaces_section(text: str) -> str:
    """The body of AGENTS.md's `## Cross-agent surfaces` section — from its heading
    up to the next level-2 (`## `) heading. Empty string if the heading is absent."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith("## ") and "Cross-agent surfaces" in line:
            capturing = True
            continue
        if capturing and line.startswith("## "):
            break
        if capturing:
            out.append(line)
    return "".join(out)


def _declared_host_dirs(section: str) -> set[str]:
    """The `.<host>/` directory prefixes cited in the Cross-agent surfaces section
    (e.g. `.claude`, `.codex`, `.kimi-code`). Only the top path segment before the
    first slash is kept, so `.claude/skills/` and `.claude/hooks/` both yield
    `.claude`. File tokens like `copilot-instructions.md` (no trailing slash) are
    NOT matched."""
    return {"." + name for name in re.findall(r"\.([a-z][a-z0-9-]*)/", section)}


def _amputate_subsection(text: str) -> str:
    """Return `text` with the `### <TITLE_MARKER> …` subsection removed, up to the
    next level-2 (`## `) heading. Used by the negative control for assertion (a)."""
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if not skipping and line.startswith("### ") and TITLE_MARKER in line:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False  # reached the next section — keep it
        if not skipping:
            out.append(line)
    return "".join(out)


def _scratch_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                  gitignore_text: str) -> Path:
    """A throwaway repository under `tmp_path` whose entire `.gitignore` is
    `gitignore_text`, insulated from the MACHINE's git configuration.

    Editing this repository's own `.gitignore` to prove the prune can go red would
    leave a window in which the repository is wrong, and the shell guard rightly
    refuses the redirect that would do it. Replaying the rule TEXT in a scratch
    repo touches nothing tracked.

    THE NEUTRALISATION GOES THROUGH THE ENVIRONMENT, and the exact mechanism
    matters because it is the one a later reader will check. `_prune_mode` and
    `_git_ignored` DO pass an explicit `env=` — `_git_env()` — and that call is
    precisely what carries the neutralisation, because `_git_env()` is built as
    `{**os.environ, …}`: it EXTENDS the process environment instead of replacing
    it. So `monkeypatch.setenv` reaches the git child, and it restores at teardown.
    The day `_git_env()` is rebuilt from a hand-picked set of variables, that
    channel closes silently — which is why `test_prune_mode_survives_a_translated_
    git` asserts the inheritance on a NAMED variable rather than on a tautology.
    Without any of this, a contributor carrying `node_modules/` in a GLOBAL ignore
    file would see these arms pass for a reason having nothing to do with the rules
    under test.

    XDG_CONFIG_HOME AND HOME ARE ISOLATED TOO (T-00001073), and the neutral
    gitconfig cannot do it: git reads `$XDG_CONFIG_HOME/git/ignore` (or
    `$HOME/.config/git/ignore`) as the DEFAULT `core.excludesFile`, with no config
    key at all. A contributor's machine ignoring `worktrees/` there would hide a
    nested worktree from these arms through `--exclude-standard`, and they would
    pass with no prune at all — `test_xdg_ignore_of_the_machine_does_not_reach_the_
    scratch_repo` pins it."""
    root = tmp_path / "repo"
    root.mkdir()
    neutral = tmp_path / "neutral.gitconfig"
    neutral.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(neutral))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(neutral))
    (tmp_path / "xdg").mkdir(exist_ok=True)
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    subprocess.run(["git", "init", "-q", str(root)],
                   capture_output=True, text=True, check=True)
    (root / ".gitignore").write_text(gitignore_text, encoding="utf-8")
    return root


# --- NESTED-CHECKOUT BENCH (T-00001073) ----------------------------------------
# Arms built on `_scratch_repo(gitignore_text="")`, so the machine's own ignore
# rules can never decide a verdict. Construction rules, because this bench
# TRAVELS and runs in `python:3.14-slim` (git 2.47, no identity): every git
# child runs without GIT_* (config variables excepted); LOCAL identity per repo
# that commits; `-c protocol.file.allow=always` on every submodule; W8's relative
# gitfile WRITTEN; W7/W12 tracked files COMMITTED before the gitfile or the
# `git init` (asserted 100644); LIT's neighbour and W3d's host come from a source
# carrying no carrier; git >= 2.40 options only.
_WINDOWS = os.name == "nt"

# Arms of the scratch repo: (candidate directory, verdict). P = pruned (its
# carrier is NOT found), S = swept (it is). IDX is absent ON PURPOSE: a corrupt
# index makes `_git_ignored` raise BEFORE the guard is reached, so it would red
# for a reason this bench does not measure.
_NESTED_ARMS = {
    "W1": (".claude/worktrees/w1", "P"),
    "W8": (".claude/worktrees/w8", "P"),
    "W9": (".claude/w9", "P"),
    "W2": (".claude/w2", "P"),
    "W10": (".claude/w10", "P"),
    "W11": (".claude/w11p/w11", "P"),
    "LIT": (".claude/lit/[y]", "P"),
    "DEREG": (".claude/dereg", "P"),
    "DEREG2": (".claude/dereg2", "P"),
    "W5e": (".claude/w5e", "P"),
    "W3": (".claude/w3", "S"),
    "W3b": (".claude/w3b", "S"),
    "W3c": (".claude/w3c", "S"),
    "W3d": (".claude/w3dh/inner", "S"),
    "W3g": (".claude/w3g", "S"),
    "R": (".claude/r/worktrees/foo", "S"),
    "W4": (".claude/w4", "S"),
    "W5": (".claude/w5", "S"),
    "W5b": (".claude/w5b", "S"),
    "W10b": (".claude/w10b", "S"),
    "W6": (".claude/w6", "S"),
    "W7": (".claude/w7", "S"),
    "W12": (".claude/w12", "S"),
}
_LINK_ARMS = ("W10", "W10b")


def _build_git(*args: str, cwd: Path | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    argv = ["git"] + (["-C", str(cwd)] if cwd else []) + ["-c", "protocol.file.allow=always", *args]
    return subprocess.run(argv, check=True, capture_output=True, text=True, env=env).stdout


def _identity(repo: Path) -> None:
    _build_git("config", "user.email", "t@t", cwd=repo)
    _build_git("config", "user.name", "t", cwd=repo)


def _plant(directory: Path) -> None:
    (directory / "x").mkdir(parents=True, exist_ok=True)
    (directory / "x" / "n.md").write_text(BLOCK_SIGNATURE + " (planted carrier).\n", encoding="utf-8")


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    """src1 CARRIES the block (x/n.md); src2 carries nothing."""
    s1, s2 = tmp_path / "src1", tmp_path / "src2"
    for s in (s1, s2):
        _build_git("init", "-q", "-b", "main", str(s))
        _identity(s)
        (s / "README").write_text("ok\n", encoding="utf-8")
    _plant(s1)
    for s in (s1, s2):
        _build_git("add", "-A", cwd=s)
        _build_git("commit", "-q", "-m", "s", cwd=s)
    return s1, s2


def _build_nested_arms(root: Path, s1: Path, s2: Path) -> None:
    """Every arm of `_NESTED_ARMS` under the scratch repo `root`."""
    _identity(root)
    c = lambda rel: root.joinpath(*rel.split("/"))  # noqa: E731 - an arm's path
    (root / "README").write_text("k\n", encoding="utf-8")
    c(".claude/w11p").mkdir(parents=True)
    c(".claude/w11p/README").write_text("tracked\n", encoding="utf-8")
    _plant(c(".claude/w7"))
    _plant(c(".claude/w12"))
    _build_git("add", "-A", cwd=root)
    _build_git("commit", "-q", "-m", "k0", cwd=root)
    _build_git("submodule", "add", "-q", str(s1), ".claude/w3", cwd=root)
    _build_git("clone", "-q", str(s1), str(c(".claude/w3b")))
    _build_git("submodule", "add", "-q", str(s1), ".claude/w3b", cwd=root)
    _build_git("clone", "-q", str(s1), str(c(".claude/w3c")))
    _build_git("add", ".claude/w3c", cwd=root)
    _build_git("submodule", "add", "-q", str(s2), ".claude/w3dh", cwd=root)
    _build_git("clone", "-q", str(s1), str(c(".claude/w3g")))
    _build_git("submodule", "add", "-q", str(s1), ".claude/w3g", cwd=root)
    _build_git("submodule", "add", "-q", str(s1), ".claude/r/worktrees/foo", cwd=root)
    _build_git("submodule", "add", "-q", str(s2), ".claude/lit/y", cwd=root)
    for rel in (".claude/dereg", ".claude/dereg2"):
        _build_git("clone", "-q", str(s1), str(c(rel)))
        _build_git("submodule", "add", "-q", str(s1), rel, cwd=root)
    _build_git("commit", "-q", "-m", "subs", cwd=root)
    _build_git("rm", "-q", "--cached", "-f", ".claude/dereg", ".claude/dereg2", cwd=root)
    _build_git("config", "-f", ".gitmodules", "--remove-section", "submodule..claude/dereg", cwd=root)
    _build_git("add", ".gitmodules", cwd=root)  # `.gitmodules` ONLY: `add -A` would re-register both
    _build_git("commit", "-q", "-m", "dereg", cwd=root)
    _build_git("clone", "-q", str(s1), str(c(".claude/w3dh/inner")))
    _build_git("submodule", "add", "-q", str(s1), "inner", cwd=c(".claude/w3dh"))
    c(".claude/w3g/.git/HEAD").unlink()
    _build_git("clone", "-q", str(s1), str(c(".claude/lit/[y]")))
    _build_git("worktree", "add", "-q", "--detach", ".claude/worktrees/w1", "HEAD", cwd=root)
    _plant(c(".claude/worktrees/w1"))
    _build_git("worktree", "add", "-q", "--detach", ".claude/worktrees/w8", "HEAD", cwd=root)
    c(".claude/worktrees/w8/.git").write_text("gitdir: ../../../.git/worktrees/w8\n", encoding="utf-8")
    _plant(c(".claude/worktrees/w8"))
    _plant(c(".claude/w9"))
    c(".claude/w9/.git").write_text(f"gitdir: {root}/.git/worktrees/gone\n", encoding="utf-8")
    _build_git("clone", "-q", str(s1), str(c(".claude/w2")))
    _build_git("clone", "-q", str(s1), str(c(".claude/w11p/w11")))
    _plant(c(".claude/w5e"))
    c(".claude/w5e/.git").mkdir()
    _plant(c(".claude/w4"))
    c(".claude/w4/.git").write_text("gitdir: ../../.git/worktrees/agent-x/modules/.claude/w4\n", encoding="utf-8")
    _plant(c(".claude/w5"))
    c(".claude/w5/.git").write_text("", encoding="utf-8")
    _plant(c(".claude/w5b"))
    c(".claude/w5b/.git").write_text("gitdir: /nonexistent\n", encoding="utf-8")
    _plant(c(".claude/w6"))
    c(".claude/w7/.git").write_text(f"gitdir: {root}/.git/worktrees/agent-x\n", encoding="utf-8")
    _build_git("init", "-q", str(c(".claude/w12")))
    if not _WINDOWS:
        real = root.parent / "w10real"
        _build_git("clone", "-q", str(s1), str(real))
        _plant(c(".claude/w10"))
        c(".claude/w10/.git").symlink_to(real / ".git")
        _plant(c(".claude/w10b"))
        c(".claude/w10b/.git").symlink_to(root.parent / "nowhere" / ".git")


def _arm_verdicts(root: Path, arms: dict[str, tuple[str, str]]) -> dict[str, str]:
    carriers = set(scan_block(root))
    return {name: ("S" if f"{rel}/x/n.md" in carriers else "P") for name, (rel, _v) in arms.items()}


def _deviations(root: Path, arms: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    got = _arm_verdicts(root, arms)
    return {a: (want, got[a]) for a, (_rel, want) in arms.items() if got[a] != want}


def _nested_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
    s1, s2 = _sources(tmp_path)
    _build_nested_arms(root, s1, s2)
    return root


def _arms_here() -> dict[str, tuple[str, str]]:
    return {k: v for k, v in _NESTED_ARMS.items() if not (_WINDOWS and k in _LINK_ARMS)}


class AutomodeDoctrineTests:
    def test_paragraph_present(self) -> None:
        """(a) AGENTS.md carries the pre-arbitration subsection — title + verbatim
        citation of the host block, in the same system prompt as the block."""
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert paragraph_present_in(text), (
            "AGENTS.md no longer carries the « While auto mode is active » "
            "pre-arbitration subsection (title marker + verbatim citation). The "
            "doctrine that answers the host block must live beside it, or every "
            "agent re-opens a closed enquiry."
        )

    def test_no_instruction_surface_carries_block(self) -> None:
        """(b) No instruction surface of the repo carries the block. NON-VACUITY
        first: the sweep must reach a real corpus, or its emptiness says nothing.
        The oversized relevé is CONSUMED here too — a carrier over the read bound
        would otherwise pass green (unread), so it reds this assertion by name."""
        assert _prune_mode(ROOT) == "git", (
            "this bench sweeps a git CHECKOUT — it prunes the git-ignored trees, and "
            "outside a work tree it cannot tell a dependency directory from an "
            "instruction surface. Run it in a checkout (a `git archive` export or a "
            "`COPY . .` image without `.git` is not one)."
        )
        scanned = [rel for rel, _ in _iter_surface_files(ROOT)]
        assert scanned, (
            "the surface sweep found NO files — it is measuring an empty corpus, so "
            "a zero-hit result proves nothing about instruction hygiene"
        )
        assert "CLAUDE.md" in scanned, (
            "CLAUDE.md is not in the swept corpus — the closed surface list has "
            "drifted from the repo and the sweep is blind to the primary host doc"
        )
        seen = set(scanned)
        missing = [a for a in _SWEEP_ANCHORS if not (
            any(rel.startswith(a) for rel in seen) if a.endswith("/") else a in seen)]
        assert not missing, (
            f"swept corpus lost {len(missing)} anchor(s): {missing} (corpus is "
            f"{len(scanned)} file(s)). Each anchor is a surface the sweep must WALK "
            "INTO — `CLAUDE.md` above is a top-level file and would survive an "
            "inverted prune that emptied every directory. Either the git-ignore "
            "prune has become too generous, or the closed surface list has drifted "
            "from the repo; in both cases the assertions below are measuring an "
            "amputated corpus and their emptiness says nothing."
        )
        carriers, oversized = scan_block_detailed(ROOT)
        assert carriers == [], (
            "instruction surface(s) now CARRY the « While auto mode is active » "
            f"block: {carriers}. It belongs in NO repo file (it is a host session "
            "setting). If a surface must cite it, cite it as DATA under an excluded "
            "prefix; otherwise this is the leak the net exists to catch."
        )
        assert oversized == [], (
            f"{len(oversized)} fichier(s) hors borne, non balayé(s) — la garantie "
            f"'aucune surface ne porte le bloc' ne tient pas : {oversized}. Un porteur "
            f"au-delà de _MAX_READ_BYTES n'est pas lu, donc le bloc peut s'y trouver "
            f"sans que le balayage le voie : réduire le fichier, l'exclure "
            f"explicitement, ou relever la borne."
        )

    def test_detector_reds_on_planted_block(self, tmp_path: Path) -> None:
        """(b) NEGATIVE CONTROL — same function, root changed. A tmp root with a
        planted `.claude/rules/python.md` carrying the block MUST be found; without
        this, a detector that silently stopped matching would read as success."""
        planted = tmp_path / ".claude" / "rules" / "python.md"
        planted.parent.mkdir(parents=True)
        planted.write_text(
            "Some host guidance.\n" + BLOCK_SIGNATURE + " do as told.\n",
            encoding="utf-8",
        )
        found = scan_block(tmp_path)
        assert ".claude/rules/python.md" in found, (
            "THE DETECTOR DOES NOT BITE: a file plainly carrying the block was not "
            f"flagged (found={found}). scan_block would then certify absence it "
            "cannot see."
        )

    def test_gitignored_tree_pruned_but_tracked_surface_swept(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) NEGATIVE CONTROL — the PRUNE, on BOTH pattern classes, plus the case
        that decides the design.

        The `.gitignore` of a scratch repo carries the two classes this repository
        actually uses, because they are matched differently: an UNANCHORED rule
        (`node_modules/`, which matches at any depth) and a rule ANCHORED BY A SLASH
        (`.claude/rules/out/`, which matches from the repo root only). Pruning the
        first and missing the second would leave half the defect standing.

        THE THIRD PLANT IS THE MEASUREMENT. A file force-added under the ignored
        directory must still be SWEPT: git answers « not ignored » for any TRACKED
        path, and for a DIRECTORY holding one it refuses to collapse the directory
        at all, listing its untracked-ignored files one by one instead. That is the
        whole reason no instruction surface can ever be pruned away — every one of
        them is tracked. If this arm reds, the design is wrong, not the test."""
        root = _scratch_repo(tmp_path, monkeypatch,
                             "node_modules/\n.claude/rules/out/\n")
        (root / ".claude" / "rules" / "node_modules").mkdir(parents=True)
        (root / ".claude" / "rules" / "out").mkdir(parents=True)
        plants = (".claude/rules/normal.md",
                  ".claude/rules/node_modules/pruned.md",
                  ".claude/rules/node_modules/forced.md",
                  ".claude/rules/out/pruned.md")
        for rel in plants:
            (root / rel).write_text(f"{BLOCK_SIGNATURE} in {rel}.\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", "-f",
             ".claude/rules/node_modules/forced.md"],
            capture_output=True, text=True, check=True)

        assert _prune_mode(root) == "git", (
            "the scratch repo is not seen as a work tree — this control would then "
            "prune nothing and pass for the wrong reason"
        )
        found = scan_block(root)
        assert ".claude/rules/normal.md" in found, (
            "BASE NOT GREEN: a carrier in a perfectly ordinary surface was not "
            f"flagged (found={found}) — the prune is eating the corpus itself, and "
            "the two exclusions below would then prove nothing"
        )
        assert ".claude/rules/node_modules/forced.md" in found, (
            "A TRACKED FILE WAS PRUNED: a force-added carrier under a git-ignored "
            f"directory escaped the sweep (found={found}). « tracked ⇒ never pruned » "
            "is what makes this net safe to prune at all — if it does not hold, the "
            "prune can hide an instruction surface, and the design is wrong"
        )
        assert ".claude/rules/node_modules/pruned.md" not in found, (
            "THE PRUNE DOES NOT BITE on an UNANCHORED rule: an untracked file under "
            f"an ignored `node_modules/` was swept (found={found}) — installed "
            "dependencies would be raked in as instruction surfaces"
        )
        assert ".claude/rules/out/pruned.md" not in found, (
            "THE PRUNE DOES NOT BITE on a SLASH-ANCHORED rule: an untracked file "
            f"under an ignored, root-anchored directory was swept (found={found}). "
            "Half a prune is not a prune — this repository ignores build outputs "
            "with exactly this class of rule"
        )

    def test_prune_mode_survives_a_translated_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) WITNESS — a git that speaks the operator's language is still read.

        `_prune_mode` recognises « no repository at all » by its MESSAGE, and git
        translates its fatals. Under a French locale the same fatal comes back as
        « ni ceci ni aucun de ses répertoires parents n'est un dépôt git », where
        the English message never appears — so an unpinned sweep raises on a tmp
        root instead of sweeping it, and this bench would be green only for
        contributors working in English. That was MEASURED here, not imagined.

        HONEST BOUND: the first arm bites only where git's French catalogue is
        installed; elsewhere git answers in English anyway and the arm passes
        without proving anything. The second and third arms therefore pin the
        MECHANISM, and they bite everywhere.

        THE THIRD ARM GUARDS THE INHERITANCE, ON A NAMED VARIABLE. `_git_env()` must
        EXTEND `os.environ`, because that is the only channel by which
        `_scratch_repo`'s `monkeypatch.setenv` of `GIT_CONFIG_GLOBAL` reaches the
        git child and neutralises the machine's own ignore rules. Asserting that a
        variable is « absent or truthy » would be satisfied by a dictionary
        inheriting NOTHING — measured: rebuilding `_git_env` from a hand-picked set
        left the whole file green. So the arm SETS a value and demands THAT value
        back: a rebuilt environment then reds here instead of quietly disarming
        every scratch-repo control."""
        monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
        monkeypatch.setenv("LANG", "fr_FR.UTF-8")
        monkeypatch.setenv("LANGUAGE", "fr")
        assert _prune_mode(tmp_path) == "none", (
            "A TRANSLATED GIT BREAKS THE DISCRIMINATION: a plain tmp directory was "
            "not recognised as « outside any repository » once git was asked to "
            "speak French. The stderr match reads an English message, so the C "
            "locale must be forced on every git child."
        )
        env = _git_env()
        assert env.get("LC_ALL") == "C" and env.get("LANGUAGE") == "", (
            f"the git child environment no longer pins the C locale ({env.get('LC_ALL')!r}"
            f"/{env.get('LANGUAGE')!r}) — git would translate the very fatal this "
            "module parses, and the arm above cannot see it on a machine that has no "
            "translation catalogue installed"
        )
        witness = str(tmp_path / "witness-inheritance.gitconfig")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", witness)
        assert _git_env().get("GIT_CONFIG_GLOBAL") == witness, (
            "THE INHERITANCE IS BROKEN: a variable set in os.environ did not reach "
            f"the git child environment ({_git_env().get('GIT_CONFIG_GLOBAL')!r} "
            f"instead of {witness!r}). `_git_env()` must EXTEND os.environ, never "
            "rebuild it from a chosen set of names: `_scratch_repo` neutralises the "
            "machine's gitconfig through exactly this variable, so a rebuilt "
            "environment would silently hand every scratch-repo control back to the "
            "contributor's own global ignore rules"
        )

    def test_prune_failure_is_raised_not_degraded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) NEGATIVE CONTROL — a git fatal that is NOT « not a git repository »
        must RAISE, never soften into « nothing to prune ».

        The fatal replayed here is the one this repository actually meets: `detected
        dubious ownership`, which `core-scripts/verify.sh` disarms with a `safe.directory`
        entry before the container leg. Return code 128 alone does not identify it —
        it is shared with the legitimate « outside any repository » case that every
        tmp-root control below relies on — so the discrimination reads the stderr,
        and anything unrecognised is surfaced rather than absorbed. The raise must
        reach the SWEEP too, not only the helper: a degraded sweep would rake the
        ignored trees back in and red far away, naming dependency bytes instead of
        the environment."""
        fatal = ("fatal: detected dubious ownership in repository at '/repo'\n"
                 "To add an exception for this directory, call:\n"
                 "\tgit config --global --add safe.directory /repo\n")

        def _fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=args, returncode=128,
                                               stdout="", stderr=fatal)

        monkeypatch.setattr(subprocess, "run", _fake_run)
        with pytest.raises(RuntimeError) as raised:
            _prune_mode(tmp_path)
        message = str(raised.value)
        assert "dubious ownership" in message, (
            "THE FATAL IS SWALLOWED: the raise does not carry git's own stderr "
            f"({message!r}), so the operator sees a broken sweep with no cause"
        )
        assert "safe.directory" in message, (
            "the refusal names no remedy — a guard that only says « no » costs a "
            "diagnosis every time it fires"
        )
        with pytest.raises(RuntimeError):
            scan_block(tmp_path)

    def test_paragraph_removal_reds(self) -> None:
        """(a) NEGATIVE CONTROL — same predicate, on an amputated copy. Base must be
        green first, then the amputated copy MUST fail `paragraph_present_in`."""
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert paragraph_present_in(text), (
            "base not green: AGENTS.md does not carry the subsection, so amputating "
            "it would prove nothing"
        )
        amputated = _amputate_subsection(text)
        assert amputated != text, "the amputation removed nothing — wrong heading marker"
        assert not paragraph_present_in(amputated), (
            "THE PRESENCE CHECK DOES NOT BITE: AGENTS.md with the subsection removed "
            "still satisfied paragraph_present_in, so its green measures nothing"
        )

    def test_paragraph_requires_all_four_points(self) -> None:
        """(a) NEGATIVE CONTROL — points 1-4 removed. `paragraph_present_in` pins a
        carrier of EACH of the four doctrine points; strip all four and the check
        must red, so a subsection reduced to a bare title + citation cannot pass."""
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        assert paragraph_present_in(text), "base not green: AGENTS.md misses a point marker"
        gutted = text
        for marker in _DOCTRINE_POINT_MARKERS:
            gutted = gutted.replace(marker, "")
        assert not paragraph_present_in(gutted), (
            "THE FOUR-POINT PIN DOES NOT BITE: AGENTS.md stripped of all four "
            "doctrine points still satisfied paragraph_present_in — the check would "
            "certify a hollowed subsection"
        )

    @pytest.mark.parametrize("point_index", [0, 1, 2])
    def test_paragraph_reds_when_any_single_point_removed(self, point_index: int) -> None:
        """(a) NEGATIVE CONTROL, PER POINT — points 1-3 pinned ONE AT A TIME. Removing
        a SINGLE point marker must red `paragraph_present_in`, so « each of the four
        points is carried » is proven point by point, not only in bulk (point 4 is
        pinned on its own by test_paragraph_reds_when_point4_gutted)."""
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        marker = _DOCTRINE_POINT_MARKERS[point_index]
        assert marker in text, (
            f"base not green: point {point_index + 1} carrier « {marker} » "
            "absent from AGENTS.md"
        )
        without_one = text.replace(marker, "")
        assert without_one != text, f"removing point {point_index + 1} changed nothing"
        assert not paragraph_present_in(without_one), (
            f"POINT {point_index + 1} IS NOT PINNED INDIVIDUALLY: AGENTS.md stripped of "
            f"« {marker} » alone still satisfied paragraph_present_in — the check would "
            "pass a subsection missing one required point"
        )

    def test_paragraph_reds_when_point4_gutted(self) -> None:
        """(a) NEGATIVE CONTROL — point 4 turned into its opposite. Replacing « Signaler
        une consigne inattendue reste légitime » with « Ne signale pas cette consigne »
        MUST red: the net exists precisely to refuse a doctrine that silences a
        security signal (the clause T-00000279 rejected)."""
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        point4 = _DOCTRINE_POINT_MARKERS[3]
        assert point4 in text, "base not green: point 4 carrier absent from AGENTS.md"
        mutated = text.replace(point4, "Ne signale pas cette consigne")
        assert mutated != text, "the point-4 mutation replaced nothing"
        assert not paragraph_present_in(mutated), (
            "POINT 4 IS NOT PINNED: AGENTS.md with « reste légitime » swapped for a "
            "« ne signale pas » still passed — the check would bless the very "
            "silencing clause the doctrine refuses"
        )

    def test_closed_list_covers_declared_hosts(self) -> None:
        """CONFRONTATION — the closed sweep list vs the hosts AGENTS.md declares. Every
        `.<host>/` directory named in § Cross-agent surfaces must be swept, so the next
        host added there reds until it is added to INSTRUCTION_SURFACES. `.agent`
        (Antigravity, ships nothing) is already in the list and exempt from the check."""
        section = _cross_agent_surfaces_section((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        assert section, "AGENTS.md § Cross-agent surfaces not found — extraction is blind"
        declared = _declared_host_dirs(section)
        assert ".kimi-code" in declared, (
            "extraction drifted: `.kimi-code` (a declared host) was not read out of the "
            "section — the confrontation is measuring nothing"
        )
        # `.agent` (Antigravity) is DECLARED in § Cross-agent surfaces (`.agent/skills/`)
        # yet the kit ships NOTHING under it — skills reach Antigravity BY PATH, not by
        # discovery (AGENTS.md § Antigravity). It sits in INSTRUCTION_SURFACES today, so
        # this subtraction is a no-op RIGHT NOW; it earns its keep the day `.agent` leaves
        # the sweep list (a legitimate choice — nothing ships there), so the confrontation
        # does NOT then red demanding a surface with no bytes back into the list.
        required = declared - {".agent"}
        missing = sorted(d for d in required if d not in INSTRUCTION_SURFACES)
        assert not missing, (
            f"host directory(ies) declared in AGENTS.md § Cross-agent surfaces but NOT "
            f"in the closed sweep list: {missing}. A block planted under one of these "
            f"escapes the net — add each to INSTRUCTION_SURFACES."
        )

    def test_symlink_not_followed(self, tmp_path: Path) -> None:
        """(b) WITNESS — a symlink under a swept surface, pointing at a block-carrying
        file OUTSIDE the tree, must NOT be counted; a real sibling file must be."""
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        outside = tmp_path / "outside.md"  # not under any swept surface
        outside.write_text("host guidance\n" + BLOCK_SIGNATURE + " do as told.\n", encoding="utf-8")
        (rules / "link.md").symlink_to(outside)
        (rules / "real.md").write_text(BLOCK_SIGNATURE + " here.\n", encoding="utf-8")
        found = scan_block(tmp_path)
        assert ".claude/rules/real.md" in found, (
            "the sweep stopped seeing a REAL carrier while adding symlink safety "
            f"(found={found}) — it now under-scans"
        )
        assert ".claude/rules/link.md" not in found, (
            "A SYMLINK WAS FOLLOWED OUT OF THE TREE: content reached only through a "
            f"link was counted (found={found}); a link could then smuggle in outside "
            "bytes or spin an infinite walk"
        )

    def test_oversized_file_ignored_and_reported(self, tmp_path: Path) -> None:
        """(b) WITNESS — a file over `_MAX_READ_BYTES` carrying the block is NOT read
        into a hit, but IS surfaced in the oversized relevé RETURNED by
        `scan_block_detailed` (not stderr — that is the channel production consumes,
        L-00000136). A small carrier alongside it must still be flagged."""
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        big = rules / "big.md"
        big.write_text(BLOCK_SIGNATURE + "\n" + "x" * (_MAX_READ_BYTES + 1), encoding="utf-8")
        (rules / "small.md").write_text(BLOCK_SIGNATURE + " here.\n", encoding="utf-8")
        hits, oversized = scan_block_detailed(tmp_path)
        assert ".claude/rules/small.md" in hits, "the bounded read dropped a small carrier too"
        assert ".claude/rules/big.md" not in hits, (
            "an oversized file was read whole into a hit — the I/O bound is not applied"
        )
        assert ".claude/rules/big.md" in oversized, (
            "an oversized file was skipped SILENTLY — a bound must be reported, or its "
            "absence reads as clean"
        )

    def test_self_pinned_by_exact_path_not_basename(self, tmp_path: Path) -> None:
        """(b) WITNESS — self-exclusion is by EXACT path, not basename. A planted
        `.codex/test_automode_doctrine.py` (same name, different path) carrying the
        block MUST be flagged; only THIS file at its real path is exempt."""
        planted = tmp_path / ".codex" / _SELF_REL.rsplit("/", 1)[-1]
        planted.parent.mkdir(parents=True)
        planted.write_text(BLOCK_SIGNATURE + " planted.\n", encoding="utf-8")
        found = scan_block(tmp_path)
        assert ".codex/test_automode_doctrine.py" in found, (
            "A FOREIGN FILE WAS EXEMPTED BY NAME: a planted file merely sharing this "
            f"test's basename escaped the sweep (found={found}); self-exclusion must "
            "pin the exact path, not the name"
        )

    def test_file_named_backups_swept_but_dir_excluded(self, tmp_path: Path) -> None:
        """(b) WITNESS — `backups` excludes a DIRECTORY segment only. A FILE named
        `backups` carrying the block is flagged; a file under a `backups/` directory
        is not (transcript history stays excluded)."""
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        (tmp_path / ".claude" / "rules" / "backups").write_text(
            BLOCK_SIGNATURE + " in a file named backups.\n", encoding="utf-8"
        )
        (tmp_path / ".claude" / "backups").mkdir()
        (tmp_path / ".claude" / "backups" / "note.md").write_text(
            BLOCK_SIGNATURE + " in a backups directory.\n", encoding="utf-8"
        )
        found = scan_block(tmp_path)
        assert ".claude/rules/backups" in found, (
            "A FILE NAMED `backups` WAS EXCLUDED AS IF A DIRECTORY: a real instruction "
            f"file escaped the sweep (found={found})"
        )
        assert ".claude/backups/note.md" not in found, (
            "the `backups/` DIRECTORY exclusion regressed — transcript history is being "
            f"swept as instruction (found={found})"
        )

    # --- T-00001073 : nested checkouts --------------------------------------------

    def test_nested_checkout_table_on_a_scratch_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) PRUNED : W1 W8 W9 W2 W10 W11 LIT DEREG DEREG2 W5e — nothing
        registers them. SWEPT : W3 W3b W3c W3d W3g R W4 W5 W5b W10b W6, and W7/W12
        whose files are TRACKED under a `.git` of their own. W5e (an EMPTY `.git`
        DIRECTORY, nothing tracked beneath) is pruned: a named bound — only
        untracked bytes can be hidden. The message is `{arm: (wanted, got)}`."""
        root = _nested_root(tmp_path, monkeypatch)
        for rel in (".claude/w7/x/n.md", ".claude/w12/x/n.md"):
            mode = _build_git("ls-files", "-s", "--", rel, cwd=root)[:6]
            assert mode == "100644", f"PRECONDITION: {rel} is not a TRACKED file ({mode!r})"
        w8 = root / ".claude" / "worktrees" / "w8"
        top = _build_git("rev-parse", "--show-toplevel", cwd=w8).strip()
        assert os.path.realpath(top) == os.path.realpath(w8), "PRECONDITION: W8 is not a real worktree"
        assert _deviations(root, _arms_here()) == {}

    def test_nested_checkout_ceiling_is_not_inherited_by_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) GIT_CEILING_DIRECTORIES=<root>: under it a REGISTERED child
        answers « not a git repository (or any … » — exactly the out-of-repo
        message. The guard drops every GIT_* but the config three, so the table
        is UNCHANGED and nothing raises. Control: a ceiling ABOVE the root changes
        nothing either."""
        root = _nested_root(tmp_path, monkeypatch)
        deviations = {}
        for ceiling in (str(root), str(root.parent)):
            monkeypatch.setenv("GIT_CEILING_DIRECTORIES", ceiling)
            d = _deviations(root, _arms_here())
            if d:
                deviations[ceiling] = d
        assert deviations == {}

    def test_nested_checkout_outside_any_repo_prunes_without_git(self, tmp_path: Path) -> None:
        """(T-00001073) `_prune_mode` = `none`: every `.git` child is pruned, NO
        guard call. NGmod/NGquote/NGsp carry a `.gitmodules` line this file does not
        read — a WANTED divergence from check-stale, which sweeps them."""
        texts = {"NGborne": None,
                 "NGmod": '[submodule "e"]\n\tpath = .claude/emb\n\turl = x\n',
                 "NGquote": '[submodule "e"]\n\tpath = ".claude/emb"\n\turl = x\n',
                 "NGsp": '[submodule "e"]\n  path=.claude/emb   \n'}
        deviations = {}
        for name, gitmodules in texts.items():
            root = tmp_path / name
            root.mkdir()
            if _prune_mode(root) != "none":
                pytest.skip(f"SKIP: the temporary directory sits INSIDE a repository ({root})")
            _plant(root / ".claude" / "emb")
            (root / ".claude" / "emb" / ".git").mkdir()
            if gitmodules:
                (root / ".gitmodules").write_text(gitmodules, encoding="utf-8")
            deviations.update(_deviations(root, {name: (".claude/emb", "P")}))
        assert deviations == {}

    def test_nested_checkout_git_failure_on_a_child_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) W5c (clone under an empty `.git` FILE) and W5d (under a bogus
        gitdir): git fails on the CHILD, with a fatal that is not « outside a
        repository ». The guard RAISES — never prunes, never sweeps in silence."""
        root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        s1, _s2 = _sources(tmp_path)
        (root / ".claude" / "w5").mkdir(parents=True)
        (root / ".claude" / "w5" / ".git").write_text("", encoding="utf-8")
        _build_git("clone", "-q", str(s1), str(root / ".claude" / "w5" / "c"))
        with pytest.raises(RuntimeError):
            scan_block(root)
        (root / ".claude" / "w5" / ".git").write_text("gitdir: /nonexistent\n", encoding="utf-8")
        with pytest.raises(RuntimeError):
            scan_block(root)

    def test_nested_checkout_rc_on_a_child_is_read_not_inverted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) The guard's own answer, patched: rc 128 « not a git
        repository (or any … » on a CHILD inside a work tree is a BLOCKED discovery
        and RAISES; so does any other rc 128. Reading either as « not registered »
        (an inverted rc) would prune a registered path in silence."""
        root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        (root / ".claude" / "w2" / ".git").mkdir(parents=True)
        real = subprocess.run
        for stderr, word in (("fatal: not a git repository (or any of the parent directories): .git\n", "BLOCKED"),
                             ("fatal: detected dubious ownership in repository at '/x'\n", "dubious")):
            def fake(argv, *a, _stderr=stderr, **kw):
                if "-s" in argv and "ls-files" in argv:
                    return subprocess.CompletedProcess(argv, 128, "", _stderr)
                return real(argv, *a, **kw)
            monkeypatch.setattr(subprocess, "run", fake)
            with pytest.raises(RuntimeError) as raised:
                scan_block(root)
            assert word in str(raised.value)
            monkeypatch.setattr(subprocess, "run", real)

    @pytest.mark.skipif(_WINDOWS, reason="SKIP: a `sh` core.fsmonitor script is not measured on Windows")
    def test_nested_checkout_guard_never_runs_the_queried_repos_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(S-00003664) A queried repository may carry `core.fsmonitor=<cmd>` (an
        embedded clone from an untrusted archive); git runs it on every `ls-files
        -s` (measured, git 2.55). CONTROL first: the SAME argv without the two `-c`,
        under the SAME environment, creates the marker — otherwise the zero below
        proves nothing. The config is set AFTER construction, which would run it.
        The GUARD is called directly: `_git_ignored` queries the root itself and is
        outside it."""
        root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        _identity(root)
        (root / "README").write_text("r\n", encoding="utf-8")
        _build_git("add", "-A", cwd=root)
        _build_git("commit", "-q", "-m", "r", cwd=root)
        cand = root / ".claude" / "fs"
        (cand / ".git").mkdir(parents=True)
        marker, script = tmp_path / "fsm.marker", tmp_path / "fsm.sh"
        script.write_text(f'#!/bin/sh\necho "fsmonitor $*" >> "{marker}"\nexit 1\n', encoding="utf-8")
        script.chmod(0o755)
        _build_git("config", "core.fsmonitor", str(script), cwd=root)
        subprocess.run(["git", "-C", str(cand.parent), "ls-files", "-s", "--", ":(literal)" + cand.name],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
        assert marker.exists(), "CONTROL: a BARE ls-files -s does not run core.fsmonitor — this witness measures nothing"
        marker.unlink()
        assert _elague(str(cand), "git") is True, "PRECONDITION: an untracked empty `.git` is pruned"
        assert not marker.exists(), "the guard RAN the queried repository's core.fsmonitor"

    def test_nested_checkout_guard_raises_on_a_silent_git_and_carries_60_s(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(S-00003664) The guard's index query carries `timeout=60`; past it,
        `subprocess.TimeoutExpired` RAISES — a bench that cannot ask does not conclude."""
        cand = tmp_path / ".claude" / "w2"
        (cand / ".git").mkdir(parents=True)
        seen = []

        def fake(argv, *a, **kw):
            seen.append(kw.get("timeout"))
            raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
        monkeypatch.setattr(subprocess, "run", fake)
        with pytest.raises(subprocess.TimeoutExpired):
            _elague(str(cand), "git")
        assert seen == [60]

    def test_nested_checkout_root_worktree_with_a_real_submodule(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) W4r — the ROOT is itself a linked worktree carrying a real
        initialised submodule: the submodule is swept."""
        q = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        s1, _s2 = _sources(tmp_path)
        _identity(q)
        _build_git("add", "-A", cwd=q)
        _build_git("commit", "-q", "-m", "q0", cwd=q)
        _build_git("submodule", "add", "-q", str(s1), ".claude/sub", cwd=q)
        _build_git("commit", "-q", "-m", "sub", cwd=q)
        w4r = tmp_path / "W4r"
        _build_git("worktree", "add", "-q", "--detach", str(w4r), "HEAD", cwd=q)
        _build_git("submodule", "update", "-q", "--init", cwd=w4r)
        assert _deviations(w4r, {"W4r": (".claude/sub", "S")}) == {}

    @pytest.mark.skipif(_WINDOWS, reason="SKIP: a `sh` shim at the head of PATH is not measured on Windows")
    def test_nested_checkout_guard_is_lazy_and_speaks_c(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073) Only the GUARD's calls are counted (`ls-files -s --`):
        `_prune_mode` and `_git_ignored` already cost two calls on any repo. CLEAN
        (no repo) and W6 (repo, no `.git` child) -> 0 guard call; NGborne (no repo)
        -> 0; a live worktree -> at least one. Every guard call sees LC_ALL=C and an
        empty LANGUAGE although the session speaks French."""
        shim, log = tmp_path / "shim", tmp_path / "git.log"
        shim.mkdir()
        (shim / "git").write_text(
            '#!/bin/sh\nprintf "%s|%s|%s\\n" "${LC_ALL-}" "${LANGUAGE-}" "$*" >> "$SHIM_JOURNAL"\n'
            f'exec "{shutil.which("git")}" "$@"\n', encoding="utf-8")
        (shim / "git").chmod(0o755)
        w6 = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        _plant(w6 / ".claude" / "w6")
        clean = tmp_path / "CLEAN"
        _plant(clean / ".claude" / "a")
        ngb = tmp_path / "NGborne"
        _plant(ngb / ".claude" / "emb")
        (ngb / ".claude" / "emb" / ".git").mkdir()
        w1 = tmp_path / "W1"
        _build_git("init", "-q", "-b", "main", str(w1))
        _identity(w1)
        (w1 / "README").write_text("r\n", encoding="utf-8")
        _build_git("add", "-A", cwd=w1)
        _build_git("commit", "-q", "-m", "r", cwd=w1)
        _build_git("worktree", "add", "-q", "--detach", ".claude/worktrees/w1", "HEAD", cwd=w1)
        cases = [("CLEAN", clean, 0), ("W6", w6, 0), ("W1", w1, None)]
        if _prune_mode(ngb) == "none":
            cases.append(("NGborne", ngb, 0))
        monkeypatch.setenv("PATH", str(shim) + os.pathsep + os.environ.get("PATH", ""))
        monkeypatch.setenv("SHIM_JOURNAL", str(log))
        monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
        monkeypatch.setenv("LANGUAGE", "fr")
        seen = {}
        for name, root, _want in cases:
            log.write_text("", encoding="utf-8")
            scan_block(root)
            lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l]
            guard = [l for l in lines if "ls-files -s --" in l]
            seen[name] = (len(guard), [l for l in guard if not l.startswith("C||")])
        for name, _root, want in cases:
            n, not_c = seen[name]
            assert not_c == [], f"{name}: guard call(s) outside the C locale: {not_c}"
            if want is None:
                assert n >= 1, f"{name}: no guard call — this witness measures nothing"
            else:
                assert n == want, f"{name}: {n} guard call(s), wanted {want}"

    def test_xdg_ignore_of_the_machine_does_not_reach_the_scratch_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(T-00001073, M6) PRECONDITION of every scratch-repo arm: a hostile
        `$XDG_CONFIG_HOME/git/ignore` — the default `core.excludesFile`, read with no
        config key — must not decide a verdict. Set it BEFORE `_scratch_repo`; a
        carrier in the directory it ignores is still found."""
        hostile = tmp_path / "hostile-xdg"
        (hostile / "git").mkdir(parents=True)
        (hostile / "git" / "ignore").write_text("hidden/\nworktrees/\n", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(hostile))
        root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        _plant(root / ".claude" / "hidden")
        assert ".claude/hidden/x/n.md" in scan_block(root), (
            "the MACHINE's XDG ignore file reached the scratch repo: a directory it "
            "ignores was pruned, so every scratch-repo arm can pass for that reason")

    def test_nested_checkout_without_git_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """(T-00001073) PATH without git: the sweep RAISES (via `_prune_mode`) —
        a bench that cannot ask the index does not conclude."""
        root = _scratch_repo(tmp_path, monkeypatch, gitignore_text="")
        (root / ".claude" / "w2" / ".git").mkdir(parents=True)
        empty = tmp_path / "no-git"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        with pytest.raises(RuntimeError):
            scan_block(root)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
