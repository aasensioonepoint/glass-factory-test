#!/usr/bin/env python3
"""Sync a SOURCE branch (`--source`, default `main`) -> `template/starter-kit`.

WHY this exists: the kit's working branch carries the kit plus this project's
own dev state (the task board, the ledger, design docs). `template/starter-kit`
is the kit team's TEST branch — pilot decision S-00002355, which SUPERSEDES the
"distribution perimeter" reading of ledger L-00000215: the team uses it by
COPYING the current version into a project or a folder, nobody pulls it, and
its history is one continuous line of sync commits. Every change on the source
that should ship, and every deletion on the source (the step humans forget),
has to be mirrored onto the template branch. This script mechanizes that
mirroring and prints a complete, reviewable plan. **The review is HUMAN.** This
tool claims no leak-detection capability (ledger L-025: a denylist derived from
tracked paths is structurally blind to an artefact that has already leaked and
become identical on both sides — it never appears in the report at all). Read
every diff yourself.

    python .agents/bin/sync_template.py [--check | --apply] [--source BRANCH]
                                         [--allow-stale-source] [--allow-stale-template]
                                         [--allow-stale-build] [--allow-foreign-source]
                                         [--allow-unseeding]
                                         [--remote origin] [--root DIR]

Default is `--check`: a read-only report, nothing is written. `--source` names
a LOCAL branch (default `main`, same alphabet as `--remote`, never a leading
dash — L-009). It is resolved ONCE, as `refs/heads/<source>^{commit}`, to a
full sha — a tag or a remote-tracking ref carrying the same name is never read
— and EVERY read of the source consumes that sha: its tree, its
`.template-exclude`, the overwrite diffs, the UI-build order, the apply
checkout and the `@ <sha>` (all 40 hex) of the suggested commit subject. The template is
read as `refs/heads/template/starter-kit` (tree, diffs, staleness count). The
lineage ANCHOR below is NOT a name either: its hex is looked up as an object
prefix (`rev-parse --disambiguate`), so a tag named like it is never read —
until T-00001065's security pass it WAS (`rev-parse --verify <sha7>^{commit}`
prefers a ref), which let a homonymous tag redirect the guard. The source is a
PARAMETER, never a mutation of `MAIN_REF`. `--allow-stale-main` is kept as the
older spelling of `--allow-stale-source` (same flag).

ALL comparisons are done against git REFS (the source's sha,
`template/starter-kit`), never the working tree. The one exception is
post-apply verification, which hashes files that were just written to the
working tree via `git hash-object --path <repo-path> <file>` so `.gitattributes`
clean filters apply the same normalization git would apply on `add` (an
`eol=crlf` path checked out as CRLF still verifies against its LF-normalized
blob sha this way — see `.gitattributes:11-13`).

`--check` contract (tested): produces byte-identical output regardless of
which branch is currently checked out; performs exactly one fetch of exactly
two refs (the source, `template/starter-kit`) from `--remote` (default
`origin`) — that updates remote-tracking refs and `FETCH_HEAD`, which is git
plumbing, not repo content; writes NO worktree file and NO index entry, ever.
A read-only ref comparison is still valid when offline: `--check` NEVER
refuses on a fetch failure or on staleness — it prints a loud banner
(`STALENESS NOT PERFORMED (fetch failed: ...)` or
`SOURCE/DEST BEHIND <ref> by <n> commits`) and then the report anyway. It
DOES refuse on an unusable SOURCE (20, 21, 22 below) and on an unseeding plan
(23 below), exactly like `--apply`:
a plan computed from a source the template does not descend from is not a
description of the sync, it is a false one (measured on this repository on
2026-10-01: a bare run from `main` planned 106 DELETEs).

Source refusals — `--check` AND `--apply`, before any fetch:
    20  the source is not a local branch (`refs/heads/<source>` does not resolve).
    21  the source IS `template/starter-kit`.
    22  LINEAGE GUARD — the source does not continue the branch the template
        was last synced from, or the guard cannot conclude (below).
Plan refusal — `--check` AND `--apply`, after the plan is computed and BEFORE
it is printed (same reason as 20-22: a report that reads as the truth about a
regressive sync is what `--check` must never print):
    23  UNSEEDING — the template carries at least one marker under
        `.agents/state/gates/` and the source carries NO seed (no
        `.agents/adopter-seed/`): the sync would delete every marker and every
        later adopter would start UNARMED. `--allow-unseeding` lifts 23 and 23
        only, in both modes, and prints `UNSEEDING` with what it deletes.
        Removing SOME seeds (the source still carries at least one) is not
        refused: those destinations are planned as DELETE like any other.
Apply refusal — `--apply` only, after the report and BEFORE any write (T-00001149,
pilot decision S-00004031, option A):
    24  PATH CONFLICT — a path the plan WRITES (a TAKE, a new or changed seed)
        meets the other kind in the template's tree: a FILE (tracked, or on disk
        anything but a real directory) where a parent directory is needed, or a
        DIRECTORY (tracked paths under it, or one on disk) where the file goes.
        Measured on the base, all four shapes (seed or TAKE, either way round)
        ended 18 "mid-way" on a half-applied tree — `.agents/state/gates` tracked
        as a FILE under a planned seed was `[Errno 17] File exists`. Nothing is
        applied; the remedy is on the template: remove the blocking path in its
        own commit, then re-run `--apply`. Same code (T-00001155): a path NEW to
        the template that something already holds on disk (an ignored file, a
        case variant of a tracked path) — the write would erase it and no
        rollback could bring it back; move it away, then re-run.

THE SEED CHANNEL (T-00001093). `.agents/state/` is `strip:` — the kit's own
board, ledger and markers never travel. Five gate markers must reach an
adopter ARMED all the same, so the source carries their SEEDS under
`.agents/adopter-seed/<rel>` (itself `strip:`, it never travels as such) and
the sync writes each one to `.agents/state/<rel>` on the template — from the
source's SHA (its blob, staged by sha), NEVER from the kit's own `.agents/state/`,
which keeps its own regime. The destination root is CLOSED: a seed whose
destination is not under `.agents/state/gates/`, a seed source or destination
not covered by a `strip:` rule, is a config error (17). `--apply` STAGES each
new or changed seed from the source's blob (mode 100644: a marker is a plain
file) and writes it from the index, like any TAKE (the transaction below), and
the verification demands the planned blob in the INDEX as well as on disk —
a seed written to disk only would be left untracked, out of the commit the
operator types, and would block the checkout back to the source.

THE LINEAGE GUARD (exit 22). The ANCHOR is the newest commit on the template's
first-parent line whose subject STARTS (`re.match`, `SYNC_ANCHOR_RE`) with the
machine prefix `chore(template): sync from <label> @ <sha7-40>`. A
`Revert "chore(template): …"` or a `docs:` subject that merely QUOTES the form
is therefore not an anchor, and an older sync subject without `@ <sha>` is
skipped. The `<sha>` must be the prefix of EXACTLY ONE COMMIT here
(`rev-parse --disambiguate`, which never consults a ref, lists EVERY object with
that prefix, blobs and trees included; `cat-file -t` then types each one and
only the commits are counted, so a blob sharing a 7-hex prefix never makes a
sound anchor ambiguous — the subject `--apply` suggests now carries all 40 hex,
older 7-hex anchors are still read; no commit, several commits, or an object git
cannot type is 22, each named), and that
commit an ancestor of the source's sha (`merge-base --is-ancestor`): a foreign
source fails, so does a source moved BEHIND the anchor, and so does anything git
cannot answer — a guard that cannot conclude does not conclude green (that
includes a `--check` run where no local template branch exists).
`--allow-foreign-source` lifts 22 and 22 only, in both modes, and prints what
it skipped. The commit subject `--apply` suggests IS an anchor
(`SYNC_SUBJECT_PREFIX`), so from the first sync made by this script on, the
anchor is written by the machine, not by hand. BOUNDS, said here so the guard
is never read as more than it is (L-00000187):
  - it measures an ALLEGATION of lineage written in a commit subject, not a
    property of the content: a hand-written subject can lie either way;
  - NAMED HOLE — a template with NO anchored subject (a fresh or orphan
    template, the test fixture's `make_repo`) is NOT guarded: the guard prints
    `LINEAGE UNGUARDED` on stderr and lets the run through. Pinned by
    `test_lineage_guard_is_silent_without_an_anchor`; the day the hole is
    closed, that test turns red and this paragraph changes with it.

`--apply` refuses (before any mutation, each with a distinct message and exit
code), in this order: there is no local `template/starter-kit` branch (10,
checked FIRST — the tell of a project provisioned from the template rather
than the kit repo itself; this tool is for kit maintainers); HEAD is not on
`template/starter-kit` (11); the working tree is dirty (12, `git status
--porcelain` non-empty, INCLUDING untracked files); the source is unusable
(20/21/22 above); the dashboard build is older than its source on the source
branch (19); the fetch fails or the source/`template/starter-kit` is behind or
diverged from its remote-tracking ref (13/14/15 — bypass per-ref with
`--allow-stale-source` / `--allow-stale-template`; a failed fetch means BOTH
cannot be verified, so it takes both flags together, each printing its own
loud warning naming what was skipped); or `.template-exclude` cannot be read
via `git show <source sha>:.template-exclude` (16, never from disk — the
working tree may not even be on the source).

`.template-exclude` rules (one per line, `#` comments, read from the source only):
    strip: <prefix>/     never taken from the source; deleted from the template if present.
    keep:  <prefix>/     never taken from the source; NEVER deleted from the template.
    own:   <exact/path>  exists only on the template; never taken, never deleted.
A trailing `/` marks a directory (prefix) rule; anything else is an exact file
match. Overlap resolves longest-prefix-wins; two rules at the IDENTICAL prefix
with different polarity is a config error (ambiguous, not an override). A
`keep`/`own` rule that matches nothing on either ref is almost certainly a typo
and is a config error; a `strip` rule that matches nothing is not an error (it
is normal for a prophylactic rule to guard against something that has not
happened yet) and gets one quiet summary line, never a warning — a permanent
warning teaches operators to skip warnings.

`--check` report has four classes, full path lists, plus one reminder line —
every line names the REAL source, never a hard-coded `main`:
    TAKE (new)       on the source, not on template, outside all rules.
    TAKE (overwrite) on both, content differs; each path's unified diff is
                     printed (`<= 10` paths in the class -> full diffs;
                     more -> each diff capped at 80 lines with a
                     "truncated — full diff: ..." footer naming the exact
                     command to reproduce it).
    DELETE           template-side paths gone from the source, or matching a
                     `strip:` rule; each line names its reason. Computed from
                     the template ref, never hand-written.
    FROZEN/OWN       keep/own matches — listed, untouched.
    SEED             each `.agents/adopter-seed/<rel>` of the source and the
                     `.agents/state/<rel>` it is written to (new / overwrite /
                     unchanged) — printed AFTER FROZEN/OWN, never as "git add".
    REMINDER         TEMPLATE.md (`own:`) is prose this tool does not edit; if
                     it needs an edit, that edit goes in a SEPARATE commit
                     AFTER the sync commit, so the sync commit's tree is
                     exactly the planned one (the pilot checks it by tree sha).

`--apply` computes the same plan, builds a manifest (path, action, planned
blob sha), then applies it AS A TRANSACTION (T-00001155, pilot decision
S-00004031: never a half-applied tree). (1) THE INDEX, the disk untouched:
`update-index --force-remove` for the DELETEs, then `update-index --add
--index-info` stages each TAKE (the source's mode and blob, read from its tree)
and each new or changed seed — blobs already in the object store, names fed
NUL-separated on stdin, never on argv. (2) THE DISK: `checkout-index -f -u`
writes what (1) staged, then each DELETE is unlinked and its emptied parents
pruned, as `git rm` did (the removal stays STAGED: apply only ever runs on a
clean tree and the operator commits the result). (3) Every manifest entry is
verified against the working tree. Step (2) is NOT atomic — one call writes N
paths, and `[Errno 17] File exists` was measured there — so a ROLLBACK JOURNAL
is filled before it: each path new to the template (absent from the disk, the
pre-pass proved it), each directory the run creates, each path tracked at HEAD
it touches. A failure in (1), (2) or (3) — an error raised by the verification
itself included — any other exception, or an interrupt (SIGINT; SIGTERM and
SIGHUP are turned into one for the transaction only, unless already ignored —
`nohup` stays the master —, the previous handlers given back BEFORE the
rollback; a git running at that moment gets SIGTERM, which lets it remove its
`index.lock`, and SIGKILL only after a bounded grace — `sync_template_proc.py`;
POSIX ONLY: on Windows `Popen.terminate()` is `TerminateProcess`, an outright
stop, so the lock stays and the manual recovery applies)
says what failed and `ROLLING BACK` FIRST — every line guarded: a dead terminal
swallows it, never the rollback; a failed verification's list of mismatches comes AFTER
the rollback, in a `finally`, never ahead of it (unbounded, it would hold the rollback
behind a blocked stderr) — then replays the journal path by path — created paths unlinked,
created directories removed if empty, `read-tree HEAD`, `git checkout HEAD --
<touched paths>` — and prints `ROLLED BACK`: `status --porcelain` and `ls-files
-s` are what they were. A git or disk error and a failed verification exit 18;
an interrupt or any other exception is raised again after the rollback. Never
`reset --hard` (it would touch more than the journal), never `git clean` (it
can take untracked files this tool never created). Only a rollback that itself
fails prints `ROLLBACK INCOMPLETE`, what it could not undo, and the manual
recovery — the index lock (`.git/index.lock`; in a linked worktree, the path
`git rev-parse --git-path index.lock` prints) removed if a killed git left it
and no git runs, then `git reset`, then `git checkout -- .`, then the newly created paths
by name, newly SEEDED markers included — addressed to the OPERATOR at a
terminal: the kit's shell guard refuses `git checkout -- .` and a relative
`rm --` from an agent, by design, not a refusal to work around. BOUNDS: the
journal lives in MEMORY, so SIGKILL, a power cut or a process killed outright
replays nothing and prints nothing — the index is then at (or part-way to) the
plan and the disk mixed: follow the steps of that manual recovery by hand
(`--check` prints the plan again, its `TAKE (new)` and new `SEED` paths are the
ones to remove). The handlers being given back before the rollback, ANY
SIGTERM or SIGHUP while it runs (one not ignored), or a second Ctrl-C (the FIRST
one on a failed step or a failed verification), stops it: same recovery — and so
does one in the window just BEFORE it, while the headline and the wait line are
said. A DEAD terminal (a dropped SSH session) gets the rollback but
no report and the same exit: at reconnection a clean `git status` on the template
and no file at the path `git rev-parse --git-path index.lock` prints mean ROLLED
BACK, anything else the manual recovery; an empty directory the run created may
remain all the same (git never lists an empty directory): remove it with `rmdir`,
left there it changes nothing for the next `--apply`. From afar, run `--apply`
under tmux/screen or `nohup`.
The rollback restores the index from HEAD,
so the skip-worktree (sparse checkout), assume-unchanged and intent-to-add bits
are not carried back. On success it prints the
suggested commit command — `git commit -m "<subject>" -m "Sans-tache: synchronisation du gabarit"`,
nothing before it: the first `-m` is the subject
`chore(template): sync from <source> @ <sha>` (the source's full 40-hex sha), the lineage anchor above;
the second is the `Sans-tache:` trailer `.githooks/commit-msg` accepts in place of a task number — and
never runs it. Never `git add -A`: the apply already staged exactly the plan,
and a sweeping add would carry any other local state into the template.

The script never commits, never pushes, never switches branches. Every
externally-derived path list is passed to git after `--` (ledger L-009), and
under `GIT_LITERAL_PATHSPECS=1` where git would match it as a pattern
(the rollback's `checkout`, the verification's `ls-files`); the plumbing of the
transaction reads NAMES on stdin (`-z`), never patterns nor options — the one deliberate
exception is the diff helper, which builds `<ref>:<path>` tokens: prefixing
the ref makes the argv token start with the ref name, never with a path's own
(possibly dash-leading) first character, so it cannot be read as an option
either.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The git runner and the transaction's signal window: the sibling module (T-00001163), re-exported
# here — `st.git`, `st.GitError`, `st.read_blob` are what they were, and patching `st.git` still
# reaches every caller below.
from sync_template_proc import GitError, git, read_blob, signals_as_interrupt  # noqa: E402,F401
from sync_template_docs import doc_targets, SOURCE as DOC_SOURCE  # noqa: E402

MAIN_REF = "main"
TEMPLATE_REF = "template/starter-kit"
EXCLUDE_PATH = ".template-exclude"
# THE SEED CHANNEL (see the docstring): `<SEED_SRC_ROOT><rel>` on the source is
# written to `<SEED_DEST_PREFIX><rel>` on the template. The destination root is
# CLOSED to `SEED_DEST_ROOT`: only gate markers are ever seeded — a future seed
# aimed at the board or the ledger is a config error, not a quiet copy.
SEED_SRC_ROOT = ".agents/adopter-seed/"
SEED_DEST_PREFIX = ".agents/state/"
SEED_DEST_ROOT = ".agents/state/gates/"
FULL_DIFF_CAP = 10
DIFF_LINE_CAP = 80
_CMDLINE_BUDGET = 6000  # conservative batch size for `git checkout`/`git rm` argv (Windows limit ~8191)

# Exit codes are distinct per refusal reason so callers/tests assert on WHY, not just nonzero.
EXIT_OK = 0
EXIT_REFUSED_NO_TEMPLATE_BRANCH = 10
EXIT_REFUSED_WRONG_BRANCH = 11
EXIT_REFUSED_DIRTY_TREE = 12
EXIT_REFUSED_FETCH_FAILED = 13
EXIT_REFUSED_STALE_MAIN = 14
EXIT_REFUSED_STALE_TEMPLATE = 15
EXIT_REFUSED_EXCLUDE_UNREADABLE = 16
EXIT_CONFIG_ERROR = 17
EXIT_VERIFY_FAILED = 18
# 19 and not 17: the refusal series runs 10..16, but 17 (config or git error) and 18 (apply failed, AND the
# seed-link pre-pass `Refusal` of do_apply) were already a published contract that tests and callers assert
# on, so the new refusal takes the next free number rather than renumbering them.
EXIT_REFUSED_STALE_UI_BUILD = 19
# The SOURCE refusals (T-00001065), --check AND --apply. 14 keeps its published
# name; `EXIT_REFUSED_STALE_SOURCE` is the same code under the --source wording.
EXIT_REFUSED_STALE_SOURCE = EXIT_REFUSED_STALE_MAIN
EXIT_REFUSED_SOURCE_NOT_A_BRANCH = 20
EXIT_REFUSED_SOURCE_IS_TEMPLATE = 21
EXIT_REFUSED_FOREIGN_LINEAGE = 22
# The PLAN refusal (T-00001093), --check AND --apply: a source with no seed
# would delete every marker the template carries under `.agents/state/gates/`.
EXIT_REFUSED_UNSEEDING = 23
# The APPLY refusal (T-00001149, pilot decision S-00004031, option A), --apply only, BEFORE
# any write: the template's tree holds the other kind (file / directory) where the plan writes.
EXIT_REFUSED_PATH_CONFLICT = 24

# THE LINEAGE ANCHOR — one prefix, shared by the WRITER (`do_apply`'s suggested
# commit subject) and the READER (`_last_synced_commit`), so the two cannot drift
# apart. `re.match`, never `re.search`: only a subject that STARTS with the
# machine prefix is an anchor — a `Revert "chore(template): ..."` or a `docs:`
# subject quoting the form is not. `\b` after the sha: `@ dda1c22 — text` is the
# measured shape on this repository's template (4781a824).
SYNC_SUBJECT_PREFIX = "chore(template): sync from"
SYNC_ANCHOR_RE = re.compile(re.escape(SYNC_SUBJECT_PREFIX) + r" (\S+) @ ([0-9a-f]{7,40})\b")

# A ref NAME given on the command line (`--remote`, `--source`) reaches git as a
# positional token. `--` is not a safe separator for rev-parse (it splits revs
# from paths there), so the defence is validation (L-009): never a leading dash,
# and this alphabet only.
_REF_NAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?")

# The dashboard's source tree and the build output it produces. `.template-exclude`
# carries `strip: .agents/ui-src/`, so the BUILD travels to the template branch and
# the SOURCE never does — which opens the window this pair of constants guards.
UI_SOURCE_PATH = ".agents/ui-src"
UI_BUILD_PATH = ".agents/ui"


def force_utf8_stdio() -> None:
    """Same guard as tasks.py/migrate_layout.py: a Windows cp1252 console cannot
    encode the arrows/diff marks this script prints, and a plan must not die
    trying to print itself."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


class ConfigError(Exception):
    """`.template-exclude` is malformed — a human must fix the file."""


class Refusal(Exception):
    """A precondition failed; carries the message and the exit code to use."""

    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# git plumbing (the runner itself, `git()`, lives in `sync_template_proc.py`)
# --------------------------------------------------------------------------

def list_tree(root: Path, ref: str, *, modes: dict[str, str] | None = None) -> dict[str, str]:
    """path -> blob sha for every blob tracked at `ref`, repo-root-relative POSIX paths.
    `modes`, when given, is filled with path -> mode (100644, 100755, 120000)."""
    r = git(root, "ls-tree", "-r", "-z", "--full-tree", ref)
    out: dict[str, str] = {}
    for record in r.stdout.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        parts = meta.split(" ")
        if len(parts) != 3:
            continue
        mode, obj_type, sha = parts
        if obj_type != "blob":
            continue
        out[path] = sha
        if modes is not None:
            modes[path] = mode
    return out


def read_exclude(root: Path, ref: str = MAIN_REF, *, label: str | None = None) -> str:
    """Read `.template-exclude` from `ref` via `git show` — never from disk, so
    the report is identical no matter what is checked out. `label` names the
    branch in the refusal when `ref` is a resolved sha."""
    r = git(root, "show", f"{ref}:{EXCLUDE_PATH}", check=False)
    if r.returncode != 0:
        where = ref if label is None else f"{label} ({ref[:8]})"
        raise Refusal(
            f"REFUSE: {EXCLUDE_PATH} is unreadable on {where} "
            f"({r.stderr.strip() or 'git show failed'})",
            EXIT_REFUSED_EXCLUDE_UNREADABLE,
        )
    return r.stdout


def try_fetch(root: Path, remote: str, source: str = MAIN_REF) -> str | None:
    """Fetch exactly the source branch and `template/starter-kit` from `remote`,
    in ONE command — a source that was never pushed fails the whole fetch, it is
    never swallowed. Returns None on success, or a short failure reason string.
    With the default source the argv is the historical one, byte for byte."""
    r = git(root, "fetch", remote, source, TEMPLATE_REF, check=False)
    if r.returncode != 0:
        return r.stderr.strip() or r.stdout.strip() or f"git fetch {remote} exited {r.returncode}"
    return None


def _ahead_behind(root: Path, local_ref: str, remote_ref: str) -> tuple[int, int] | None:
    probe = git(root, "rev-parse", "--verify", "--quiet", remote_ref, check=False)
    if probe.returncode != 0:
        return None
    r = git(root, "rev-list", "--left-right", "--count", f"{local_ref}...{remote_ref}")
    ahead_s, behind_s = r.stdout.split()
    return int(ahead_s), int(behind_s)


def staleness(root: Path, local_ref: str, remote: str, *,
              local_rev: str | None = None) -> tuple[bool, str]:
    """(is_stale, detail) for `local_ref` against `<remote>/<local_ref>`. Stale
    covers both plain "behind" and "diverged" (ahead AND behind). `local_rev`,
    when given, is the already-resolved sha — or the full `refs/heads/` ref — of
    the local branch: the count reads it instead of re-resolving a NAME a
    homonymous tag could capture."""
    remote_ref = f"{remote}/{local_ref}"
    ab = _ahead_behind(root, local_rev or local_ref, remote_ref)
    if ab is None:
        return False, f"no remote-tracking ref {remote_ref} yet"
    ahead, behind = ab
    if behind == 0:
        return False, "up to date"
    kind = "diverged from" if ahead > 0 else "behind"
    suffix = f" ({ahead} commit(s) ahead too)" if ahead else ""
    return True, f"{kind} {remote_ref} by {behind} commit(s){suffix}"


# --------------------------------------------------------------------------
# .template-exclude
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    polarity: str  # strip | keep | own
    prefix: str
    lineno: int
    raw: str

    @property
    def is_dir(self) -> bool:
        return self.prefix.endswith("/")

    def matches(self, path: str) -> bool:
        return path.startswith(self.prefix) if self.is_dir else path == self.prefix


def parse_exclude(text: str) -> list[Rule]:
    rules: list[Rule] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ConfigError(
                f"{EXCLUDE_PATH}:{lineno}: malformed rule (expected 'polarity: prefix'): {raw!r}"
            )
        polarity, _, prefix = line.partition(":")
        polarity = polarity.strip()
        prefix = prefix.strip()
        if polarity not in ("strip", "keep", "own"):
            raise ConfigError(
                f"{EXCLUDE_PATH}:{lineno}: unknown polarity {polarity!r} (want strip/keep/own)"
            )
        if not prefix:
            raise ConfigError(f"{EXCLUDE_PATH}:{lineno}: empty prefix")
        rules.append(Rule(polarity=polarity, prefix=prefix, lineno=lineno, raw=raw))
    return rules


def validate_rules(rules: list[Rule], all_paths: set[str]) -> list[str]:
    """Structural + dead-rule validation against the union of paths on both
    refs. Returns the prophylactic `strip:` summary lines. Raises ConfigError
    on: a directory rule missing its trailing '/', a polarity tie at an
    identical prefix, or a keep/own rule that matches nothing anywhere (typo)."""
    by_prefix: dict[str, Rule] = {}
    for rule in rules:
        prior = by_prefix.get(rule.prefix)
        if prior is not None and prior.polarity != rule.polarity:
            raise ConfigError(
                f"{EXCLUDE_PATH}:{rule.lineno}: polarity tie at identical prefix {rule.prefix!r} "
                f"({prior.polarity!r} on line {prior.lineno} vs {rule.polarity!r} on line {rule.lineno})"
            )
        by_prefix.setdefault(rule.prefix, rule)

        if not rule.is_dir:
            exact_hit = rule.prefix in all_paths
            looks_like_dir = any(p.startswith(rule.prefix + "/") for p in all_paths)
            if looks_like_dir and not exact_hit:
                raise ConfigError(
                    f"{EXCLUDE_PATH}:{rule.lineno}: {rule.prefix!r} matches files UNDER it but has "
                    f"no trailing '/' — add one if this is meant to be a directory rule"
                )

    prophylactic: list[str] = []
    for rule in rules:
        if any(rule.matches(p) for p in all_paths):
            continue
        if rule.polarity == "strip":
            prophylactic.append(f"prophylactic (no match): {rule.raw.strip()}")
        else:
            raise ConfigError(
                f"{EXCLUDE_PATH}:{rule.lineno}: {rule.polarity}: {rule.prefix!r} matches nothing on "
                f"either ref — typo?"
            )
    return prophylactic


def match_rule(path: str, rules: list[Rule]) -> Rule | None:
    """Longest-prefix-wins among rules whose condition holds for `path`."""
    best: Rule | None = None
    for rule in rules:
        if rule.matches(path) and (best is None or len(rule.prefix) > len(best.prefix)):
            best = rule
    return best


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

@dataclass
class Plan:
    take_new: list[str]
    take_overwrite: list[str]
    delete: list[tuple[str, str]]  # (path, reason)
    frozen: list[str]
    prophylactic: list[str]
    main_paths: dict[str, str]  # the SOURCE's paths; name kept for its callers
    template_paths: dict[str, str]
    source_label: str = MAIN_REF  # the branch every report line names
    # (destination, seed source, "new" | "overwrite" | "unchanged")
    seed: list[tuple[str, str, str]] = field(default_factory=list)
    docs: list[tuple[str, str, str]] = field(default_factory=list)


def seed_targets(source_paths) -> dict[str, str]:
    """destination -> seed source, for every `.agents/adopter-seed/<rel>` of the
    SOURCE: `.agents/state/<rel>`. The ONE derivation of the seed set — the
    kit-side gate calls it rather than paraphrasing it. It does not judge the
    destination: `build_plan` refuses one outside the closed root (17)."""
    return {SEED_DEST_PREFIX + p[len(SEED_SRC_ROOT):]: p
            for p in sorted(source_paths) if p.startswith(SEED_SRC_ROOT)}


def _validate_seeds(seeds: dict[str, str], rules: list[Rule]) -> None:
    """17 on a seed the channel must not carry. The destination root is CLOSED;
    the source must be `strip:` (a seed never travels as itself) and so must the
    destination (otherwise the kit's own copy would be TAKEN as well and the
    plan would carry two writers for one path)."""
    for dest, src in seeds.items():
        if ".." in Path(dest).parts:  # `gates/../board/…` starts with the root yet leaves it
            raise ConfigError(f"seed {src!r} -> {dest!r}: a '..' component leaves the closed root")
        if not dest.startswith(SEED_DEST_ROOT):
            raise ConfigError(
                f"seed {src!r} -> {dest!r}: destination outside the closed root "
                f"{SEED_DEST_ROOT!r} — only gate markers are seeded"
            )
        for what, path in (("source", src), ("destination", dest)):
            rule = match_rule(path, rules)
            if rule is None or rule.polarity != "strip":
                raise ConfigError(
                    f"seed {what} {path!r} is not covered by a `strip:` rule in "
                    f"{EXCLUDE_PATH} — the seed channel needs both ends stripped"
                )


def build_plan(main_paths: dict[str, str], template_paths: dict[str, str],
               rules: list[Rule], *, source_label: str = MAIN_REF) -> Plan:
    all_paths = set(main_paths) | set(template_paths)
    prophylactic = validate_rules(rules, all_paths)
    seeds = seed_targets(main_paths)
    _validate_seeds(seeds, rules)
    try:
        docs = doc_targets(main_paths)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    for dest, src in docs.items():
        if (rule := match_rule(src, rules)) is None or rule.polarity != "strip":
            raise ConfigError(f"document source {src!r} must be strip:")
        if match_rule(dest, rules) is not None:
            raise ConfigError(f"document destination {dest!r} must travel without a rule")

    take_new: list[str] = []
    take_overwrite: list[str] = []
    delete: list[tuple[str, str]] = []
    frozen: list[str] = []
    seed: list[tuple[str, str, str]] = []
    document: list[tuple[str, str, str]] = []

    # `| set(seeds)`, and not `all_paths` alone: a destination on NEITHER ref
    # (a marker the kit itself does not carry) would otherwise be dropped
    # without a word — measured on the prototype, one seed of three vanished.
    for path in sorted(all_paths | set(seeds) | set(docs)):
        if path in seeds or path in docs:
            # BEFORE the rules: the destination is `strip:` by construction,
            # and a seeded destination is written, never deleted.
            src = (seeds if path in seeds else docs)[path]
            have = template_paths.get(path)
            if have == main_paths[src]:
                state = "unchanged"
            elif have is None:
                state = "new"
            else:
                state = "overwrite"
            (seed if path in seeds else document).append((path, src, state))
            continue
        rule = match_rule(path, rules)
        if rule is not None and rule.polarity in ("keep", "own"):
            frozen.append(path)
            continue
        if rule is not None and rule.polarity == "strip":
            if path in template_paths:
                delete.append((path, rule.raw.strip()))
            continue

        in_main = path in main_paths
        in_template = path in template_paths
        if in_main and in_template:
            if main_paths[path] != template_paths[path]:
                take_overwrite.append(path)
        elif in_main:
            take_new.append(path)
        elif in_template:
            delete.append((path, f"gone from {source_label}"))

    return Plan(take_new, take_overwrite, delete, frozen, prophylactic, main_paths, template_paths,
                source_label, seed, document)


# --------------------------------------------------------------------------
# report (--check and the plan half of --apply)
# --------------------------------------------------------------------------

def diff_lines(root: Path, path: str, source_rev: str = MAIN_REF) -> list[str]:
    # `<ref>:<path>` tokens: the ref name (or the source's hex sha) always leads
    # the argv token, so a path that starts with '-' can never be read as an
    # option (L-009).
    r = git(root, "diff", f"refs/heads/{TEMPLATE_REF}:{path}", f"{source_rev}:{path}",
            check=False)
    return r.stdout.splitlines()


def print_overwrite_diffs(root: Path, plan: Plan, out, source_rev: str = MAIN_REF) -> None:
    full = len(plan.take_overwrite) <= FULL_DIFF_CAP
    for path in plan.take_overwrite:
        lines = diff_lines(root, path, source_rev)
        print(f"\n--- diff: {path} ---", file=out)
        if full or len(lines) <= DIFF_LINE_CAP:
            for line in lines:
                print(line, file=out)
        else:
            for line in lines[:DIFF_LINE_CAP]:
                print(line, file=out)
            # The footer is a command for a HUMAN: it names the branch, as the
            # reader would type it, not the sha this run read.
            print(
                f"... truncated ({len(lines)} lines) — full diff: "
                f"git diff {TEMPLATE_REF}:{path} {plan.source_label}:{path}",
                file=out,
            )


def print_report(root: Path, plan: Plan, out, source_rev: str = MAIN_REF) -> None:
    source = plan.source_label
    print("=" * 72, file=out)
    print(f"TEMPLATE SYNC PLAN  ({source} -> {TEMPLATE_REF})", file=out)
    print("=" * 72, file=out)

    for line in plan.prophylactic:
        print(line, file=out)

    print(
        f"\nTAKE (new) — {len(plan.take_new)} path(s): on {source}, not on template, "
        f"outside all rules",
        file=out,
    )
    for p in plan.take_new:
        print(f"  + {p}", file=out)

    print(
        f"\nTAKE (overwrite) — {len(plan.take_overwrite)} path(s): these template files "
        f"will be OVERWRITTEN with {source}'s content — review each diff",
        file=out,
    )
    for p in plan.take_overwrite:
        print(f"  ~ {p}", file=out)
    print_overwrite_diffs(root, plan, out, source_rev)

    print(
        f"\nDELETE — {len(plan.delete)} path(s): template-side paths removed by this sync",
        file=out,
    )
    for p, reason in plan.delete:
        print(f"  - {p}  ({reason})", file=out)

    print(
        f"\nFROZEN/OWN — {len(plan.frozen)} path(s): keep/own matches — untouched",
        file=out,
    )
    for p in plan.frozen:
        print(f"  = {p}", file=out)

    # AFTER FROZEN/OWN, on purpose: callers slice the report on the DELETE and
    # FROZEN/OWN headers, and a section inserted between them would change what
    # they read. The text names the channel, never the staging command.
    print(
        f"\nSEED — {len(plan.seed)} path(s): written from {source}:{SEED_SRC_ROOT}<rel> "
        f"to {SEED_DEST_PREFIX}<rel>, never from the kit's own state",
        file=out,
    )
    for dest, src, state in plan.seed:
        mark = {"new": "+", "overwrite": "~"}.get(state, "=")
        print(f"  {mark} {dest}  (<- {src}; {state})", file=out)
    print(f"\nDOCS — {len(plan.docs)} path(s): written from {source}:{DOC_SOURCE}", file=out)
    for dest, src, state in plan.docs:
        mark = {"new": "+", "overwrite": "~"}.get(state, "=")
        print(f"  {mark} {dest}  (<- {src}; {state})", file=out)

    print(
        "\nREMINDER: TEMPLATE.md's store paragraph is prose this tool does not edit — "
        "check it still describes the shipped state; if it needs an edit, make it in a "
        "SEPARATE commit AFTER the sync commit, so the sync commit's tree stays exactly "
        "the planned one.",
        file=out,
    )


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------

@dataclass
class ManifestEntry:
    path: str
    action: str  # "take" | "delete" | "keep" | "seed"
    planned_sha: str | None


def build_manifest(plan: Plan) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    for p in plan.take_new + plan.take_overwrite:
        entries.append(ManifestEntry(p, "take", plan.main_paths[p]))
    for p, _reason in plan.delete:
        entries.append(ManifestEntry(p, "delete", None))
    for p in plan.frozen:
        entries.append(ManifestEntry(p, "keep", plan.template_paths.get(p)))
    for dest, src, _state in plan.seed + plan.docs:
        entries.append(ManifestEntry(dest, "seed", plan.main_paths[src]))
    return entries


def _batched(paths: list[str], max_chars: int = _CMDLINE_BUDGET) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    total = 0
    for p in paths:
        cost = len(p) + 3
        if current and total + cost > max_chars:
            batches.append(current)
            current = []
            total = 0
        current.append(p)
        total += cost
    if current:
        batches.append(current)
    return batches


def hash_worktree_file(root: Path, rel_path: str) -> str | None:
    full = root / rel_path
    if full.is_symlink():  # a link's blob is its TARGET, never the bytes of the file it points at
        r = git(root, "hash-object", "--stdin", check=False, stdin=os.readlink(full))
        return r.stdout.strip() if r.returncode == 0 else None
    if not full.is_file():
        return None
    r = git(root, "hash-object", "--path", rel_path, "--", str(full), check=False)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def verify_manifest(root: Path, manifest: list[ManifestEntry]) -> list[str]:
    """Return a list of human-readable mismatch descriptions (empty = clean)."""
    failures: list[str] = []
    for entry in manifest:
        if entry.action == "delete":
            if (root / entry.path).exists():
                failures.append(f"{entry.path}: expected deleted, still present on disk")
                continue
            tracked = git(root, "ls-files", "--", entry.path, check=False,
                          literal=True).stdout.strip()
            if tracked:
                failures.append(f"{entry.path}: expected deleted, still tracked in the index")
            continue
        if entry.action == "seed":
            # THE INDEX, NOT ONLY THE DISK: a seed written but never staged is
            # out of the commit the operator types, and the untracked file then
            # refuses the checkout back to the source. Disk alone verified clean.
            staged = git(root, "ls-files", "-s", "--", entry.path, check=False,
                         literal=True).stdout.split()
            index_sha = staged[1] if len(staged) > 1 else None
            if index_sha != entry.planned_sha:
                failures.append(f"{entry.path}: seed expected staged blob "
                                f"{entry.planned_sha}, index has {index_sha}")
        got = hash_worktree_file(root, entry.path)
        if got != entry.planned_sha:
            failures.append(f"{entry.path}: expected blob {entry.planned_sha}, got {got}")
    return failures


def print_recovery(plan: Plan, out) -> None:
    print("\nRecovery — run in exactly this order:", file=out)
    # To the OPERATOR, said rather than discovered: the kit's shell guard
    # refuses these steps from an agent, and a reader who did not know would go
    # looking for a way around a refusal that is the design.
    print("  (for the OPERATOR at a terminal: the kit's shell guard refuses "
          "`git checkout -- .` and a relative `rm --` from an agent, by design)", file=out)
    # T-00001163: a git killed outright leaves its lock, and every step below needs it gone.
    print("  1. if .git/index.lock exists and no git is running, remove it (in a linked worktree, "
          "`git rev-parse --git-path index.lock` names it)", file=out)
    print("  2. git reset", file=out)
    print("  3. git checkout -- .", file=out)
    step = 4
    if plan.take_new:
        print(
            f"  {step}. remove these newly created files by name (they did not exist on the "
            "template's HEAD, so step 3 does not touch them):",
            file=out,
        )
        for p in plan.take_new:
            print(f"       rm -- {shlex.quote(p)}", file=out)
        step += 1
    new_seeds = [dest for dest, _src, state in plan.seed + plan.docs if state == "new"]
    if new_seeds:
        print(
            f"  {step}. remove these newly SEEDED markers by name (written by this run, "
            "absent from the template's HEAD — step 3 does not touch them either):",
            file=out,
        )
        for p in new_seeds:
            print(f"       rm -- {shlex.quote(p)}", file=out)
    print("  Never `git clean` — it can take untracked files this tool never created.", file=out)


def sync_subject(source_label: str, source_sha: str) -> str:
    """The commit subject `--apply` suggests — and the lineage ANCHOR the next
    run reads back through `SYNC_ANCHOR_RE` (writer and reader share
    `SYNC_SUBJECT_PREFIX`). The FULL sha, never a 7-hex prefix: a short anchor
    is one more object sharing it away from a guard that refuses on every run."""
    return f"{SYNC_SUBJECT_PREFIX} {source_label} @ {source_sha}"


def _is_real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _refuse_if_seed_through_link(root: Path, take_paths: list[str], written_seeds: list[str]) -> None:
    """18, BEFORE any write (T-00001113). Never written THROUGH a link (a parent or the leaf;
    `root` not judged): a TAKEn path on the way may BE one — compared CASEFOLDED, since on
    APFS/NTFS a TAKEn `.agents/State` IS `.agents/state`. Nothing applied. Since the
    transaction (T-00001155) `checkout-index -f` unlinks a link in its way rather than
    follow it, and a failure rolls back (measured, `test_sync_template_transaction.py` T6):
    this refusal names up front what would otherwise be rolled back — or, a tracked link
    at the seed's own place, silently replaced by a plain file."""
    for dest in written_seeds:
        for p in (*map(str, reversed(PurePosixPath(dest).parents[:-1])), dest):
            if p.casefold() in map(str.casefold, take_paths) or (root / p).is_symlink():
                raise Refusal(f"\nAPPLY REFUSED, nothing applied: seed {dest!r}: {p} is a symbolic link "
                              "or a TAKEn path — never written through", EXIT_VERIFY_FAILED)


def _refuse_if_path_conflict(root: Path, plan: Plan, written: list[str]) -> None:
    """24, `--apply`, BEFORE any write (T-00001149, pilot decision S-00004031, option A).
    Every path the plan WRITES needs each parent to be a DIRECTORY and its own place free of
    one; the template's tree may hold the other kind there. Judged against the tree (the
    template's blobs, and the directories they imply) AND the disk (`lexists`, never
    following a link), so an ignored occupant the clean-tree check (12) cannot see is caught
    too. Measured on the base: every shape ended 18 "mid-way" on a half-applied tree.
    Third rule (T-00001155): a path new to the template must be ABSENT from the disk —
    an ignored occupant would be overwritten and no rollback could bring it back."""
    tree_dirs = {str(d) for p in plan.template_paths for d in PurePosixPath(p).parents[:-1]}
    judged: set[str] = set()
    for path in written:
        for d in map(str, reversed(PurePosixPath(path).parents[:-1])):
            if d in judged:
                continue
            judged.add(d)
            if d in plan.template_paths or (os.path.lexists(root / d) and not _is_real_dir(root / d)):
                raise Refusal(f"\nAPPLY REFUSED, nothing applied: {path!r} needs a directory at {d!r} "
                              "and the template's tree holds a FILE there — remove it from the template "
                              "in its own commit, then re-run --apply", EXIT_REFUSED_PATH_CONFLICT)
        if path in tree_dirs or _is_real_dir(root / path):
            raise Refusal(f"\nAPPLY REFUSED, nothing applied: {path!r} is written as a file and the "
                          "template's tree holds a DIRECTORY there — remove it from the template in "
                          "its own commit, then re-run --apply", EXIT_REFUSED_PATH_CONFLICT)
        if path not in plan.template_paths and os.path.lexists(root / path):
            raise Refusal(f"\nAPPLY REFUSED, nothing applied: {path!r} is not tracked on the template "
                          "and yet something holds it on disk (an ignored file, or a case variant of a "
                          "tracked path) — the write would erase it and no rollback could bring it "
                          "back: move it away, then re-run --apply", EXIT_REFUSED_PATH_CONFLICT)


@dataclass
class Journal:
    """THE ROLLBACK JOURNAL (T-00001155) — filled BEFORE each disk step, so a step that fails
    half-way (one `checkout-index` writes N paths; `[Errno 17] File exists` was measured there)
    is undone as a whole. Replayed path by path: never `reset --hard` (it would touch more
    than the journal), never `git clean` (it would take untracked files this tool never made)."""
    created: list[str] = field(default_factory=list)       # absent before (the pre-pass proved it)
    created_dirs: list[str] = field(default_factory=list)  # not a real directory before
    restored: list[str] = field(default_factory=list)      # tracked at HEAD: `git checkout HEAD --`


def _apply_transaction(root: Path, plan: Plan, source_rev: str, journal: Journal) -> None:
    """(1) THE INDEX, the disk untouched: each DELETE removed, each TAKE and written seed staged
    from a blob already in the object store — `update-index`, NUL-separated names on stdin.
    (2) THE DISK: `checkout-index -f -u` writes what (1) staged, then each DELETE is unlinked
    and its emptied parents pruned, as `git rm` did. (2) is NOT atomic, hence the journal."""
    modes: dict[str, str] = {}
    list_tree(root, source_rev, modes=modes)
    written = plan.take_new + plan.take_overwrite
    records = [f"{modes[p]} {plan.main_paths[p]}\t{p}" for p in written]
    for dest, src, state in plan.seed + plan.docs:
        if state != "unchanged":
            written.append(dest)
            records.append(f"100644 {plan.main_paths[src]}\t{dest}")  # a marker is a plain file
    deleted = [p for p, _reason in plan.delete]
    if deleted:
        git(root, "update-index", "-z", "--force-remove", "--stdin", stdin="\0".join(deleted) + "\0")
    if records:
        git(root, "update-index", "-z", "--add", "--index-info", stdin="\0".join(records) + "\0")
    judged: set[str] = set()
    for p in written:
        (journal.restored if p in plan.template_paths else journal.created).append(p)
        for d in map(str, PurePosixPath(p).parents[:-1]):
            if d not in judged:
                judged.add(d)
                if not _is_real_dir(root / d):
                    journal.created_dirs.append(d)
    journal.restored += deleted
    if written:
        git(root, "checkout-index", "-f", "-u", "-z", "--stdin", stdin="\0".join(written) + "\0")
    for p in deleted:
        (root / p).unlink()
        for d in PurePosixPath(p).parents[:-1]:
            try:
                (root / d).rmdir()  # an EMPTY directory only — anything else stays
            except OSError:
                break


def _rollback(root: Path, journal: Journal) -> list[str]:
    """Undo what the journal names; returns what could NOT be undone (empty: the index and
    every journaled path are HEAD's again). Created paths first — their directories may sit
    where a restored file goes — then `read-tree HEAD`, then `git checkout HEAD --`."""
    left: list[str] = []
    turned_dirs = []  # a written path git replaced by a directory (a link in the way of a seed)
    for p in journal.created:
        if _is_real_dir(root / p):
            turned_dirs.append(p)
            continue
        try:
            (root / p).unlink(missing_ok=True)
        except OSError as exc:
            left.append(f"{p}: {exc}")
    for d in sorted({*journal.created_dirs, *turned_dirs}, key=lambda d: d.count("/"), reverse=True):
        try:
            if _is_real_dir(root / d):
                (root / d).rmdir()
        except OSError as exc:
            left.append(f"{d}/: {exc}")
    for args in (("read-tree", "HEAD"),
                 *(("checkout", "HEAD", "--", *b) for b in _batched(journal.restored))):
        try:
            git(root, *args, literal=True)
        except GitError as exc:
            left.append(str(exc))
    return left


def _say(line: str) -> None:
    """One line to stderr, a dead terminal swallowed (EIO on a pty an SSH drop left; a closed
    stream): what the rollback has to say never costs the rollback, nor the interrupt after it."""
    try:
        print(line, file=sys.stderr)
    except (OSError, ValueError):
        pass


def _roll_back_and_report(root: Path, plan: Plan, journal: Journal, headline: str,
                          failures: list[str]) -> int:
    # Only through `_say` (critic F7 F1, measured: a SIGHUP comes with its terminal gone, and a
    # bare print raised OSError EIO — rollback never run, the tree left half-applied). The
    # headline and the wait line BEFORE the rollback, so that a live terminal knows what happened
    # even when a Ctrl-C stops the rollback or the rollback itself raises; the failures AFTER it,
    # in a `finally` (critic F7-ter F1, measured: unbounded, said before the rollback and outside
    # the signal window, 20 000 of them to a stderr pipe nobody read, then a SIGINT — the rollback
    # never ran). Two short lines are the only window left before the rollback starts.
    _say(f"\n{headline}")
    _say("ROLLING BACK — wait: a Ctrl-C now stops the rollback (manual recovery then).")
    try:
        left = _rollback(root, journal)
    finally:
        for f in failures:
            _say(f"  ! {f}")
    if not left:
        _say("ROLLED BACK — the index and every path this run touched are HEAD's again: "
             "nothing applied.")
        return EXIT_VERIFY_FAILED
    _say("ROLLBACK INCOMPLETE — not undone:")
    for f in left:
        _say(f"  ! {f}")
    try:
        print_recovery(plan, sys.stderr)
    except (OSError, ValueError):
        pass
    return EXIT_VERIFY_FAILED


def do_apply(root: Path, plan: Plan, out, source_rev: str = MAIN_REF) -> int:
    manifest = build_manifest(plan)
    take_paths = plan.take_new + plan.take_overwrite
    written_seeds = [d for d, _src, state in plan.seed + plan.docs if state != "unchanged"]
    _refuse_if_seed_through_link(root, take_paths, written_seeds)  # 18, judged first
    _refuse_if_path_conflict(root, plan, take_paths + written_seeds)  # 24
    # 17, before any write: `git()` decodes with `errors="replace"`, so a name git returned as
    # non-UTF-8 bytes carries U+FFFD — fed back to `update-index`, it would stage a RENAMED file.
    mangled = [p for p in (*take_paths, *written_seeds, *(d for d, _r in plan.delete)) if "�" in p]
    if mangled:
        raise GitError(f"{len(mangled)} plan path(s) are not UTF-8 ({mangled[0]!r}…) — never fed "
                       "back to git: a decoded name would stage a renamed file; nothing applied")

    # THE TRANSACTION (T-00001155, pilot decision S-00004031): whatever fails — a git step, a
    # disk step, the verification or an error raised INSIDE it, any other exception, an
    # interrupt (SIGINT, SIGTERM, SIGHUP) — is rolled back from the journal, and the tree is
    # never left half-applied; an interrupt or an unexpected error is raised AGAIN after the
    # rollback, never swallowed. Seeds come from the SOURCE's blob, never from the kit's own
    # `.agents/state/`; the removal is STAGED, as `git rm` did: apply only ever runs on a
    # clean tree and the operator commits the result.
    journal = Journal()
    try:
        with signals_as_interrupt():
            _apply_transaction(root, plan, source_rev, journal)
            failures = verify_manifest(root, manifest)
    except (GitError, OSError) as exc:
        return _roll_back_and_report(root, plan, journal, f"APPLY FAILED mid-way: {exc}", [])
    except BaseException as exc:  # an interrupt, or ANY other error: rolled back, then raised again
        what = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"
        _roll_back_and_report(root, plan, journal, f"APPLY {what} mid-way: {exc!r}", [])
        raise
    if failures:
        return _roll_back_and_report(
            root, plan, journal,
            "VERIFICATION FAILED — the working tree did not match the planned manifest:", failures)

    print("\nApply verified clean. Suggested commit (review `git status` first — not run for you):",
          file=out)
    # The sha in the subject is the one this run READ (the resolved source),
    # never a re-resolution of the name: it is the next run's lineage anchor.
    sha = source_rev
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        sha = git(root, "rev-parse", "--verify", f"refs/heads/{source_rev}^{{commit}}").stdout.strip()
    # `git commit` ALONE: the apply already staged exactly the plan; a `git add -A`
    # would sweep any other local state into the distributable branch. The second
    # `-m` is the traced `Sans-tache:` way out `.githooks/commit-msg` accepts: a
    # template sync belongs to no board task (T-01M54GEQ68NTP1C34EYTF0SDHX).
    print(f'  git commit -m "{sync_subject(plan.source_label, sha)}"'
          ' -m "Sans-tache: synchronisation du gabarit"', file=out)
    return EXIT_OK


# --------------------------------------------------------------------------
# apply preconditions
# --------------------------------------------------------------------------

def _refuse_if_not_ready_for_apply(root: Path) -> None:
    branch_check = git(root, "rev-parse", "--verify", "--quiet",
                        f"refs/heads/{TEMPLATE_REF}", check=False)
    if branch_check.returncode != 0:
        raise Refusal(
            f"REFUSE: no local '{TEMPLATE_REF}' branch here. This tool syncs the kit's own "
            f"main/template branches for kit MAINTAINERS — a project provisioned FROM the "
            f"template does not carry both branches and should not run this.",
            EXIT_REFUSED_NO_TEMPLATE_BRANCH,
        )
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != TEMPLATE_REF:
        raise Refusal(
            f"REFUSE: HEAD is on {branch!r}, not {TEMPLATE_REF!r} — checkout {TEMPLATE_REF} "
            f"before applying.",
            EXIT_REFUSED_WRONG_BRANCH,
        )
    status = git(root, "status", "--porcelain").stdout
    if status.strip():
        raise Refusal(
            "REFUSE: working tree is dirty (tracked or untracked changes present) — commit, "
            "stash, or clean it before syncing.",
            EXIT_REFUSED_DIRTY_TREE,
        )


def _last_synced_commit(root: Path, ref: str = f"refs/heads/{TEMPLATE_REF}") -> tuple[str, str, str] | None:
    """(commit, label, anchor sha as written) of the NEWEST commit on the
    template's first-parent line whose subject is a lineage anchor
    (`SYNC_ANCHOR_RE.match`); None when no subject is one.

    First-parent, in traversal order — ancestry, never commit dates: a rebase or
    a skewed clock rewrites dates, not the line of sync commits. `re.match` on
    the subject: a `Revert "chore(template): ..."`, a `docs:` subject quoting the
    form, or an older `sync from main` without `@ <sha>` is not an anchor.

    Raises GitError when git cannot read the template's history (no local
    template branch included) — the caller turns that into 22, never a pass."""
    r = git(root, "log", "--first-parent", "--format=%H%x00%s",
            ref, "--", check=False)
    if r.returncode != 0:
        raise GitError(f"git log {ref} failed: "
                       f"{r.stderr.strip() or f'exit {r.returncode}'}")
    for line in r.stdout.splitlines():
        commit, sep, subject = line.partition("\0")
        if not sep:
            continue
        m = SYNC_ANCHOR_RE.match(subject)
        if m:
            return commit, m.group(1), m.group(2)
    return None


def _refuse_if_source_unusable(root: Path, args) -> str:
    """Refusals 20, 21, 22 — `--check` AND `--apply`, before any fetch. Returns
    the source's full sha, resolved ONCE from `refs/heads/<source>`: every later
    read of the source consumes it (a tag of the same name is never read).

    22 is the LINEAGE GUARD (see the module docstring for its bounds): the
    anchor sha of the template's last sync must be an ancestor of the source.
    No anchor at all => the NAMED HOLE: a stderr line, and the run goes on."""
    source = args.source
    if source == TEMPLATE_REF:
        raise Refusal(
            f"REFUSE: --source is {TEMPLATE_REF!r} itself — a sync copies ANOTHER branch "
            f"onto {TEMPLATE_REF}; name the branch the template is synced from.",
            EXIT_REFUSED_SOURCE_IS_TEMPLATE,
        )
    probe = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{source}^{{commit}}",
                check=False)
    source_sha = probe.stdout.strip()
    if probe.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Refusal(
            f"REFUSE: --source {source!r} is not a local branch here (refs/heads/{source} does "
            f"not resolve to a commit). The source must be a LOCAL branch — a tag or a "
            f"remote-tracking ref is never read; create the local branch first.",
            EXIT_REFUSED_SOURCE_NOT_A_BRANCH,
        )

    problem: str
    try:
        anchor = _last_synced_commit(root)
    except GitError as exc:
        problem = f"the template's history cannot be read ({exc}), so the lineage cannot be checked"
    else:
        if anchor is None:
            print(
                f"LINEAGE UNGUARDED: no '{SYNC_SUBJECT_PREFIX} <branch> @ <sha>' subject on "
                f"{TEMPLATE_REF}'s first-parent line — whether {source} continues the template's "
                f"lineage is NOT checked on this run (named hole of the lineage guard).",
                file=sys.stderr,
            )
            return source_sha
        sync_commit, label, written = anchor
        said = f"{sync_commit[:8]} '{SYNC_SUBJECT_PREFIX} {label} @ {written}'"
        # `written` matched [0-9a-f]{7,40}: it starts with a hex digit, never a dash (L-009).
        # Looked up as an OBJECT prefix, never as a name: `rev-parse <written>`
        # prefers a ref, so a tag named like the 7 hex would redirect the anchor.
        # `--disambiguate` lists EVERY object with that prefix (blobs and trees
        # too, ~23 000 objects on this repository): only the COMMITS are counted,
        # so a blob sharing the prefix never turns a sound anchor into AMBIGUOUS.
        # An object git cannot type is NOT dropped: the guard cannot conclude.
        found = git(root, "rev-parse", f"--disambiguate={written}", check=False)
        objects = found.stdout.split()
        kinds: dict[str, str] = {}
        untyped: list[str] = []
        if found.returncode == 0:
            for obj in objects:
                typed = (git(root, "cat-file", "-t", obj, check=False)
                         if re.fullmatch(r"[0-9a-f]{40}", obj) else None)
                if typed is None or typed.returncode != 0:
                    untyped.append(obj)
                else:
                    kinds[obj] = typed.stdout.strip()
        commits = [obj for obj in objects if kinds.get(obj) == "commit"]
        anchor_sha = commits[0] if len(commits) == 1 else ""
        if found.returncode != 0:
            problem = (f"git rev-parse --disambiguate={written} exited {found.returncode} "
                       f"({found.stderr.strip()}), so the lineage cannot be checked")
        elif untyped:
            problem = (f"the last sync, {said}, names {written}, and git cannot type "
                       f"{untyped[0][:40]!r} among the {len(objects)} object(s) starting "
                       f"with it, so the lineage cannot be checked")
        elif len(commits) != 1:
            if not objects:
                what = "no object starts with it"
            elif len(commits) > 1:
                what = f"AMBIGUOUS: {len(commits)} commits start with it"
            elif len(objects) == 1:
                what = f"the one object starting with it is a {kinds[objects[0]] or '?'}, not a commit"
            else:
                what = f"none of the {len(objects)} objects starting with it is a commit"
            problem = (f"the last sync, {said}, names {written}, which is not one commit in this "
                       f"repository ({what}), so the lineage cannot be checked")
        else:
            order = git(root, "merge-base", "--is-ancestor", anchor_sha, source_sha, check=False)
            if order.returncode == 0:
                return source_sha
            if order.returncode == 1:
                problem = (f"{source} @ {source_sha[:8]} does not descend from {anchor_sha[:8]}, "
                           f"the source of the last sync ({said}) — a foreign branch, or one "
                           f"moved behind that sync")
            else:
                problem = (f"git merge-base --is-ancestor exited {order.returncode} "
                           f"({order.stderr.strip()}), so the lineage cannot be checked")

    if not args.allow_foreign_source:
        raise Refusal(
            f"REFUSE: LINEAGE — {problem}. A plan computed from it would DELETE from the "
            f"template whatever that branch lacks. Pass --source <the branch the template was "
            f"last synced from>, or --allow-foreign-source to proceed anyway.",
            EXIT_REFUSED_FOREIGN_LINEAGE,
        )
    print(
        f"LINEAGE NOT VERIFIED (--allow-foreign-source): {problem}. SKIPPED: the check that "
        f"{source} continues the branch the template was last synced from — every DELETE below "
        f"is computed against {source} as given.",
        file=sys.stderr,
    )
    return source_sha


def _last_commit_touching(root: Path, ref: str, path: str) -> str | None:
    """Full sha of the newest commit on `ref` that changed `path`, or None when
    `path` has no history there (the directory does not exist on that ref).
    Raises GitError when git fails or answers something that is not one sha."""
    r = git(root, "rev-list", "-1", ref, "--", path, check=False)
    if r.returncode != 0:
        raise GitError(f"git rev-list -1 {ref} -- {path} failed: {r.stderr.strip()}")
    sha = r.stdout.strip()
    if not sha:
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GitError(f"git rev-list -1 {ref} -- {path} returned {sha!r}, not one sha")
    return sha


def _refuse_if_ui_build_is_stale(root: Path, args, source_rev: str = MAIN_REF) -> None:
    """--apply only. `.agents/ui/` (the built dashboard) travels to the template
    branch while `.agents/ui-src/` (its React/Vite source) is stripped, so a
    source edited on the source branch and never rebuilt ships a dashboard
    matching no state of the repo, silently. This tool cannot rebuild it: at
    apply time HEAD is on the template branch, where the source does not even
    exist. So it REFUSES and names the rebuild, which belongs on the source
    branch. Both commits are looked up on `source_rev` — the source's resolved
    sha — never on a hard-coded `main`.

    Measured in git, never on disk — the working tree here has no `ui-src/` to
    look at. The comparison is topological (`merge-base --is-ancestor`), not by
    timestamp: a rebase or a skewed clock rewrites dates, not ancestry. A commit
    is its own ancestor, so the normal case — one commit touching BOTH source and
    build — passes.

    WHAT THIS DOES NOT PROVE, and it is the whole limit: it measures the ORDER OF
    COMMITS, not the CONTENT of the bundle. Committing edited sources and a
    non-rebuilt bundle in the same commit defeats it entirely. Same shape as the
    writeset disjunction, which is proven on DECLARATIONS and never on the writes
    actually performed.

    Either directory absent on the source => silent pass (a project with no
    dashboard is not this guard's business). Anything git cannot answer =>
    REFUSE: a guard that cannot conclude does not conclude green.
    """
    branch = args.source
    try:
        source_sha = _last_commit_touching(root, source_rev, UI_SOURCE_PATH)
        build_sha = _last_commit_touching(root, source_rev, UI_BUILD_PATH)
    except GitError as exc:
        if not args.allow_stale_build:
            raise Refusal(
                f"REFUSE: cannot measure whether the dashboard build is current on {branch} "
                f"({exc}). Pass --allow-stale-build to proceed anyway.",
                EXIT_REFUSED_STALE_UI_BUILD,
            ) from exc
        print(f"WARNING: dashboard build freshness NOT measured ({exc}) — proceeding on "
              f"--allow-stale-build.", file=sys.stderr)
        return

    if source_sha is None or build_sha is None:
        return

    probe = git(root, "merge-base", "--is-ancestor", source_sha, build_sha, check=False)
    if probe.returncode == 0:
        return  # build is at least as recent as the source (equal sha included)
    if probe.returncode != 1:
        if args.allow_stale_build:
            print(f"WARNING: dashboard build freshness NOT measured (git merge-base exited "
                  f"{probe.returncode}) — proceeding on --allow-stale-build.", file=sys.stderr)
            return
        raise Refusal(
            f"REFUSE: cannot order the last {UI_SOURCE_PATH}/ commit ({source_sha[:8]}) against "
            f"the last {UI_BUILD_PATH}/ commit ({build_sha[:8]}) on {branch} "
            f"({probe.stderr.strip() or f'git merge-base exited {probe.returncode}'}). "
            f"Pass --allow-stale-build to proceed anyway.",
            EXIT_REFUSED_STALE_UI_BUILD,
        )

    # NAME THE FILES, NOT ONLY THE SHAs (T-00000374). This refusal used to give
    # two abbreviated hashes and nothing else, which forced the reader to run
    # `git show` on both before they could judge anything. Measured on
    # 2026-08-25: the refusal fired, and the whole of what had changed under
    # `ui-src/` since the build was `ui-gate.sh` and `ui-gate.test.sh` — two
    # SHELL scripts, which cannot enter a Vite JavaScript bundle. A rebuild
    # confirmed it: byte-identical output, twice. (Those two files have SINCE
    # been removed from the repo — T-00000505 withdrew the interface gate from
    # every verification gate. The measurement above is kept as the RECORD of
    # what happened on that date, not as a claim about today's tree; what it
    # establishes about the commit-order proxy is unchanged.)
    #
    # So the check was RIGHT about commit order and WRONG about the world, and
    # the reader needed twenty minutes to find that out. The list below is what
    # turns that into one glance. It does NOT decide for the reader — deciding
    # whether a file is a build input is exactly the enumeration this tool must
    # not fake (L-00000187) — it just stops hiding the evidence.
    changed = []
    listing = git(root, "diff", "--name-only", build_sha, source_sha, "--",
                  f"{UI_SOURCE_PATH}/", check=False)
    if listing.returncode == 0:
        changed = [ln for ln in listing.stdout.splitlines() if ln.strip()]
    shown = changed[:20]
    if changed:
        files_block = (
            f"  WHAT CHANGED under {UI_SOURCE_PATH}/ since that build "
            f"({len(changed)} file(s)):\n"
            + "".join(f"    {p}\n" for p in shown)
            + (f"    … +{len(changed) - len(shown)} more\n" if len(changed) > len(shown) else "")
            + "  If NONE of these can affect the bundle (a shell script, a test, a\n"
              "  README), the build is fresh in CONTENT and this refusal is a false\n"
              "  positive of the commit-order proxy — rebuild to confirm, then\n"
              "  --allow-stale-build is an INFORMED decision rather than a bypass.\n"
        )
    else:
        files_block = (
            f"  (could not list what changed under {UI_SOURCE_PATH}/ between the two "
            f"commits — judge from the SHAs above)\n"
        )

    message = (
        f"REFUSE: the dashboard build is STALE on {branch}. {UI_SOURCE_PATH}/ was last changed "
        f"by {source_sha[:8]}, which is not an ancestor of {build_sha[:8]}, the last commit "
        f"touching {UI_BUILD_PATH}/. Since `.template-exclude` strips {UI_SOURCE_PATH}/, only the "
        f"BUILD travels — applying now would ship an adopting project a dashboard matching no "
        f"state of this repo.\n"
        + files_block +
        f"  Remedy, on {branch} (this tool cannot do it: HEAD is on {TEMPLATE_REF}, where the "
        f"source does not exist):\n"
        f"    cd {UI_SOURCE_PATH} && npm run build\n"
        f"  then commit the rebuilt {UI_BUILD_PATH}/, return to {TEMPLATE_REF} and re-run.\n"
        f"  LIMIT: this check measures the ORDER OF COMMITS, not the CONTENT of the bundle — "
        f"committing edited sources and a non-rebuilt bundle in one commit defeats it, and a "
        f"change that cannot reach the bundle at all makes it refuse a build that is fresh.\n"
        f"  Pass --allow-stale-build to proceed anyway."
    )
    if not args.allow_stale_build:
        raise Refusal(message, EXIT_REFUSED_STALE_UI_BUILD)
    print(f"WARNING: proceeding with a possibly stale {UI_BUILD_PATH}/ build "
          f"({UI_SOURCE_PATH}/ @ {source_sha[:8]} is newer than {UI_BUILD_PATH}/ @ "
          f"{build_sha[:8]}) (--allow-stale-build).", file=sys.stderr)


def _check_fetch_and_staleness(root: Path, args, out, source_rev: str | None = None) -> None:
    """Shared by --check and --apply. --check only ever prints; --apply raises
    Refusal when a check fails and its break-glass flag was not given. The
    source is `args.source`; `source_rev` is its sha, resolved once upstream."""
    source = args.source
    fetch_error = try_fetch(root, args.remote, source)

    if not args.apply:
        if fetch_error is not None:
            print(f"STALENESS NOT PERFORMED (fetch failed: {fetch_error})", file=out)
            return
        for label, ref, rev in (("SOURCE", source, source_rev),
                                ("DEST", TEMPLATE_REF, f"refs/heads/{TEMPLATE_REF}")):
            stale, detail = staleness(root, ref, args.remote, local_rev=rev)
            if stale:
                print(f"{label} BEHIND: {ref} is {detail}", file=out)
        return

    # --apply
    if fetch_error is not None:
        if not (args.allow_stale_main and args.allow_stale_template):
            raise Refusal(
                f"REFUSE: fetch of '{args.remote}' failed ({fetch_error}); staleness of "
                f"{source} and {TEMPLATE_REF} cannot be verified. Pass both "
                f"--allow-stale-source --allow-stale-template to proceed anyway.",
                EXIT_REFUSED_FETCH_FAILED,
            )
        print(
            f"WARNING: fetch of '{args.remote}' failed ({fetch_error}) — staleness check for "
            f"{source} and {TEMPLATE_REF} SKIPPED, proceeding on --allow-stale-*.",
            file=sys.stderr,
        )
        return

    source_stale, source_detail = staleness(root, source, args.remote, local_rev=source_rev)
    if source_stale and not args.allow_stale_main:
        raise Refusal(
            f"REFUSE: SOURCE {source} is {source_detail} — pass --allow-stale-source to "
            f"proceed anyway.",
            EXIT_REFUSED_STALE_SOURCE,
        )
    if source_stale:
        print(f"WARNING: proceeding with SOURCE {source} {source_detail} (--allow-stale-source).",
              file=sys.stderr)

    dest_stale, dest_detail = staleness(root, TEMPLATE_REF, args.remote,
                                        local_rev=f"refs/heads/{TEMPLATE_REF}")
    if dest_stale and not args.allow_stale_template:
        raise Refusal(
            f"REFUSE: DEST {TEMPLATE_REF} is {dest_detail} — pass --allow-stale-template to "
            f"proceed anyway.",
            EXIT_REFUSED_STALE_TEMPLATE,
        )
    if dest_stale:
        print(f"WARNING: proceeding with DEST {TEMPLATE_REF} {dest_detail} "
              f"(--allow-stale-template).", file=sys.stderr)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."),
                    help="repo root (default: CLAUDE_PROJECT_DIR or cwd)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="dry run — the default")
    mode.add_argument("--apply", action="store_true", help="perform the sync")
    ap.add_argument("--allow-stale-source", "--allow-stale-main", dest="allow_stale_main",
                     action="store_true",
                     help="proceed even if the source branch is behind/diverged from its "
                          "remote-tracking ref (--allow-stale-main: the older spelling)")
    ap.add_argument("--allow-stale-template", action="store_true",
                     help="proceed even if template/starter-kit is behind/diverged")
    ap.add_argument("--allow-stale-build", action="store_true",
                     help="proceed even if .agents/ui-src/ was committed after .agents/ui/ on "
                          "the source (i.e. the dashboard bundle may not have been rebuilt)")
    ap.add_argument("--allow-foreign-source", action="store_true",
                     help="proceed even if the lineage guard (exit 22) cannot confirm that the "
                          "source continues the branch the template was last synced from")
    ap.add_argument("--allow-unseeding", action="store_true",
                     help="lift 23 and 23 only, in both modes: let a source that carries no "
                          ".agents/adopter-seed/ delete the template's markers under "
                          ".agents/state/gates/ (prints UNSEEDING and what it deletes)")
    def _remote_name(value: str) -> str:
        # Security-review hardening: the remote name reaches `git fetch` and
        # `git rev-parse` as a positional token. `--` is not a safe separator
        # for rev-parse (it splits revs from paths there), so the defence is
        # validation: a git remote name never starts with a dash and stays in
        # this alphabet. Rejecting here keeps the file's L-009 invariant whole.
        if not _REF_NAME_RE.fullmatch(value):
            raise argparse.ArgumentTypeError(f"invalid remote name: {value!r}")
        return value

    def _branch_name(value: str) -> str:
        # Same defence, same alphabet: the source reaches `git fetch` as a
        # positional token and `rev-parse` as `refs/heads/<value>`.
        if not _REF_NAME_RE.fullmatch(value):
            raise argparse.ArgumentTypeError(f"invalid branch name: {value!r}")
        return value

    ap.add_argument("--remote", default="origin", type=_remote_name,
                    help="remote to fetch from (default: origin)")
    ap.add_argument("--source", default=MAIN_REF, type=_branch_name,
                    help="LOCAL branch to sync FROM (default: main); refused with 20 if it is "
                         "not a local branch, 21 if it is the template, 22 if the template's "
                         "last sync anchor is not one of its ancestors")
    return ap


def _refuse_if_unseeding(plan: Plan, args) -> None:
    """23, BOTH modes, after `build_plan` and BEFORE `print_report`. Measured on
    the prototype: a template carrying the three seeded markers, synced from a
    source with no `.agents/adopter-seed/`, planned `DELETE` for all three at
    rc 0 — the next adopter copied an UNARMED tree and nothing said so. The
    condition is deliberately narrow: at least one marker under the closed root
    on the template, and NO seed at all on the source. A source that still
    seeds at least one marker is a choice, planned as DELETE for the others."""
    markers = sorted(p for p in plan.template_paths if p.startswith(SEED_DEST_ROOT))
    if not markers or plan.seed:
        return
    listed = ", ".join(markers)
    if args.allow_unseeding:
        print(f"UNSEEDING (--allow-unseeding): {len(markers)} marker(s) under "
              f"{SEED_DEST_ROOT} will be DELETED from {TEMPLATE_REF}: {listed}",
              file=sys.stderr)
        return
    raise Refusal(
        f"REFUSE: {TEMPLATE_REF} carries {len(markers)} marker(s) under {SEED_DEST_ROOT} "
        f"({listed}) and the source {plan.source_label} carries no {SEED_SRC_ROOT}: this "
        f"sync would DELETE them all and every later adopter would start UNARMED. Sync "
        f"from a source that carries {SEED_SRC_ROOT}, or pass --allow-unseeding to "
        f"un-seed on purpose.",
        EXIT_REFUSED_UNSEEDING,
    )


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    args = build_arg_parser().parse_args(argv)
    root = Path(args.root).resolve()
    out = sys.stdout

    try:
        if args.apply:
            _refuse_if_not_ready_for_apply(root)  # 10, 11, 12

        # BOTH modes (20, 21, 22), and this is the one place --check refuses.
        # --check is a dry run that DESCRIBES the plan, so it never refuses on
        # fetch or staleness: an offline or behind description is still true
        # about the refs it read. A plan computed from an UNUSABLE source is not:
        # it describes a sync from the wrong branch — measured, the bare default
        # here planned 106 DELETEs — and a report that reads as the truth about
        # the sync is exactly what --check must never print.
        source_sha = _refuse_if_source_unusable(root, args)

        if args.apply:
            # --apply only, on purpose: the build-order proxy can refuse a build
            # that is fresh in content (see its docstring), and a description
            # that refused on it would stop telling the truth about the plan.
            _refuse_if_ui_build_is_stale(root, args, source_sha)  # 19

        _check_fetch_and_staleness(root, args, out, source_sha)  # 13, 14, 15

        exclude_text = read_exclude(root, source_sha, label=args.source)  # 16
        rules = parse_exclude(exclude_text)
        main_paths = list_tree(root, source_sha)
        template_paths = list_tree(root, f"refs/heads/{TEMPLATE_REF}")
        plan = build_plan(main_paths, template_paths, rules, source_label=args.source)
        _refuse_if_unseeding(plan, args)  # 23, BOTH modes, before the report

        print_report(root, plan, out, source_sha)

        if args.apply:
            return do_apply(root, plan, out, source_sha)
        return EXIT_OK
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except GitError as exc:
        print(f"GIT ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    sys.exit(main())
