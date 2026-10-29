"""Witnesses of condition 8 of night_approve.py — the plan is COMMITTED and identical
to HEAD (T-01M5T4NRDNZ0ESYGFR3154RRJM, plan r2, annexe § 4).

Every test builds a REAL git repository through `Repo.build()` of the elder bench
(which commits under the bench identity) and every commit made HERE carries the same
`-c user.name=banc -c user.email=banc@local -c commit.gpgsign=false` (C2: a station or a
CI runner without a global identity refuses a bare commit, measured rc 128).

Each witness NAMES the mutant that turns it red (« MUTANT M<n> »), played on a copy
outside the repository: a witness that does not name what reddens it is not a witness.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import night_approve
from test_night_approve import PLAN_REL, TASK, Repo, plan_text

GO = f"plan-critic GO (iteration 1/8) sur {PLAN_REL}"


KEPT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def git(root: Path, *args: str) -> str:
    # Independent of `night_approve._git_env`, so a mutant of the purge never bends the fixture.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in KEPT}
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=banc", "-c", "user.email=banc@local",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True, text=True, env=env, check=True,
    ).stdout


def untrack(repo: Repo) -> None:
    """The plan leaves HEAD, its bytes stay on disk (verdict and fingerprint intact)."""
    before = repo.plan_path().read_bytes()
    git(repo.root, "rm", "-q", "--cached", "--", PLAN_REL)
    git(repo.root, "commit", "-q", "-m", "chore: plan hors suivi")
    assert repo.plan_path().read_bytes() == before


def outside_any_repo(root: Path) -> bool:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, env=env)
    return p.returncode != 0


def test_w0_committed_clean_plan_is_approved():
    """W0. MUTANT M0: `condition_committed` always refuses => 'skip' != 'approve'."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        outcome = Repo(Path(tmp)).build().outcome()
    assert outcome.decision == night_approve.APPROVE, outcome.reason


def test_w1_plan_absent_from_head_is_refused_with_its_remedy():
    """W1. MUTANT M1: the call removed from `evaluate_lot` => APPROVE (bytes unchanged,
    `diff --quiet` alone reads 0 on an untracked file). MUTANT M1b: the remedy dropped
    from the reason => the `git add --` assertion reddens. MUTANT M1c: the task id not
    filled in (`<T>` printed literally) => the `plan T-…` assertion reddens."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        untrack(repo)
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "absent de HEAD" in outcome.reason, outcome.reason
    assert f"git add -- {PLAN_REL}" in outcome.reason, outcome.reason
    assert f'git commit -m "docs(tasks): plan {TASK}" -- {PLAN_REL}' in outcome.reason, outcome.reason


def test_w2_indexed_uncommitted_plan_reads_absent_never_modified():
    """W2 (C4). MUTANT M2: the HEAD leg replaced by `ls-files --error-unmatch` (the
    index, not HEAD) => the refusal comes through the diff leg, « modifie depuis HEAD »."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        untrack(repo)
        git(repo.root, "add", "--", PLAN_REL)
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "absent de HEAD" in outcome.reason, outcome.reason
    assert "modifie" not in outcome.reason, outcome.reason


def test_w3_plan_modified_since_head_is_refused():
    """W3. HEAD holds an older revision, the verdict cites the CURRENT bytes (condition 4
    holds). MUTANT M3: the diff leg removed => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        current = repo.plan_path().read_bytes()
        repo.plan_path().write_bytes(current + b"\nrevision anterieure\n")
        git(repo.root, "commit", "-q", "-a", "-m", "chore: revision anterieure")
        repo.plan_path().write_bytes(current)
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "modifie depuis HEAD" in outcome.reason, outcome.reason


def test_w4_root_in_a_subdirectory_reads_head_relative_to_root():
    """W4. `--root` is a sub-directory of the repository. MUTANT M4: `HEAD:<plan>`
    without `./` (resolved from the top) => SKIP « absent de HEAD »."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        top = Path(tmp)
        repo = Repo(top / "sous").build()
        shutil.rmtree(repo.root / ".git")
        git(top, "init", "-q")
        git(top, "add", "-A")
        git(top, "commit", "-q", "-m", "chore: banc sous-dossier")
        outcome = repo.outcome()
    assert outcome.decision == night_approve.APPROVE, outcome.reason


def test_w5_root_outside_any_repository_is_refused_git_unreadable():
    """W5. MUTANT M5: a failing `rev-parse HEAD` read as « suivi » (`return None`) => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        shutil.rmtree(repo.root / ".git")
        assert outside_any_repo(repo.root), "le dossier temporaire est dans un depot : W5 ne mesure rien"
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "git illisible" in outcome.reason, outcome.reason


def test_w6_inherited_git_dir_never_reads_another_repository():
    """W6. An inherited `GIT_DIR` (a `pre-push` exports it) points at a repo where the
    SAME plan bytes are committed; the root itself is outside git. MUTANT M6: the `GIT_*`
    purge removed => APPROVE (P8)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        other = Repo(Path(tmp) / "autre").build()
        repo = Repo(Path(tmp) / "racine").build()
        shutil.rmtree(repo.root / ".git")
        assert outside_any_repo(repo.root), "le dossier temporaire est dans un depot : W6 ne mesure rien"
        with mock.patch.dict(os.environ, {"GIT_DIR": str(other.root / ".git")}):
            outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason


def test_w7_crlf_worktree_over_lf_blob_is_identical_to_head():
    """W7. `core.autocrlf=true`, CRLF on disk, LF blob in HEAD: git says identical.
    MUTANT M7: the diff leg replaced by a comparison with the raw blob sha => SKIP (P7)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        git(root, "init", "-q")
        git(root, "config", "core.autocrlf", "true")
        repo = Repo(root)
        repo.plan = plan_text().replace("\n", "\r\n")
        repo.build()
        assert b"\r\n" in repo.plan_path().read_bytes()
        assert "\r" not in git(root, "cat-file", "-p", f"HEAD:./{PLAN_REL}"), "blob non normalise : W7 ne mesure rien"
        outcome = repo.outcome()
    assert outcome.decision == night_approve.APPROVE, outcome.reason


def test_w8_draft_and_uncommitted_names_condition_6_first():
    """W8 (order). MUTANT M8: `condition_committed` placed FIRST => « condition 8 »."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.plan = plan_text(body="STATUS: IN_PROGRESS\nREVISION: 1\n")
        repo.verdicts = [{"title": GO}]
        repo.build()
        untrack(repo)
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 6" in outcome.reason, outcome.reason


def test_w9_night_delivered_and_uncommitted_names_condition_7_first():
    """W9 (C11, condition 8 LAST). MUTANT M9: `condition_committed` placed before
    `condition_night_delivered` => « condition 8 »."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.extra = [(TASK, "decision", "night-delivered: attente binome du matin")]
        repo.build()
        untrack(repo)
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 7" in outcome.reason, outcome.reason


def test_w10_git_env_drops_redirections_and_keeps_config_locations():
    """W10 (C12). MUTANT M10: `or k in GIT_CONSERVE` removed => the three configuration
    locations are purged too. MUTANT M10b: the purge removed => GIT_DIR survives."""
    redirections = {"GIT_DIR": "/x", "GIT_WORK_TREE": "/x", "GIT_INDEX_FILE": "/x",
                    "GIT_OBJECT_DIRECTORY": "/x", "GIT_COMMON_DIR": "/x"}
    locations = {"GIT_CONFIG_GLOBAL": "/g", "GIT_CONFIG_SYSTEM": "/s", "GIT_CONFIG_NOSYSTEM": "1"}
    with mock.patch.dict(os.environ, {**redirections, **locations}):
        env = night_approve._git_env()
    # Only the bench's own keys reach the assertion message, never the inherited environment.
    leaked = sorted(k for k in redirections if k in env)
    kept = {k: env.get(k) for k in locations}
    assert leaked == []
    assert kept == locations


def test_w11_committed_symlink_to_an_untracked_outside_file_is_refused():
    """W11 (security advisory). The plan is COMMITTED as a symlink (mode 120000) to a
    file outside the repository whose content changed after the commit; the verdict
    cites the CURRENT target bytes. HEAD holds the link text only: `cat-file -e` 0 and
    `diff --quiet` 0. MUTANT M11: the `islink` refusal removed => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        outside = Path(tmp) / "dehors.md"
        outside.write_bytes(b"revision commitee nulle part\n")
        repo = Repo(Path(tmp) / "racine")
        repo.write_plan = False
        repo.plan_path().parent.mkdir(parents=True)
        os.symlink(outside, repo.plan_path())
        repo.build()
        mode = git(repo.root, "ls-files", "-s", "--", PLAN_REL).split(" ", 1)[0]
        assert mode == "120000", f"le lien n'est pas commite comme lien ({mode}) : W11 ne mesure rien"
        outside.write_bytes(repo.plan.encode("utf-8"))
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "lien symbolique" in outcome.reason, outcome.reason


def test_w12_staged_revision_with_worktree_back_to_head_is_refused_like_the_night():
    """W12 (closing review F1). A revision is STAGED, then the worktree goes back to
    HEAD: `git status --porcelain` prints `MM` (the night refuses it) while
    `diff --quiet HEAD` reads 0. MUTANT M12: the `diff --cached` leg removed => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        current = repo.plan_path().read_bytes()
        repo.plan_path().write_bytes(current + b"\nrevision indexee\n")
        git(repo.root, "add", "--", PLAN_REL)
        repo.plan_path().write_bytes(current)
        assert git(repo.root, "status", "--porcelain", "--", PLAN_REL).startswith("MM"), "MM non pose"
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert f"git restore --staged -- {PLAN_REL}" in outcome.reason, outcome.reason


def test_w13_ignored_plan_gets_the_forced_add_remedy():
    """W13 (closing review F4). The plan leaves HEAD and `.gitignore` names it: a bare
    `git add --` would refuse it. MUTANT M13: the `ls-files --ignored` branch removed
    => the remedy reads `git add --`, the `git add -f --` assertion reddens."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        untrack(repo)
        (repo.root / ".gitignore").write_text(PLAN_REL + "\n", encoding="utf-8")
        git(repo.root, "add", "--", ".gitignore")
        git(repo.root, "commit", "-q", "-m", "chore: plan ignore")
        assert git(repo.root, "status", "--porcelain", "--ignored", "--", PLAN_REL).startswith("!!"), "!! non pose"
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "ignore par git" in outcome.reason, outcome.reason
    assert f"git add -f -- {PLAN_REL}" in outcome.reason, outcome.reason


def test_w14_git_absent_from_path_is_refused_never_read_committed():
    """W14 (closing review F5). PATH points at an EMPTY folder: git cannot be launched.
    MUTANT M14: `_git_rc` answers 0 on the exception (`except …: return 0`) => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp) / "racine").build()
        empty = Path(tmp) / "vide"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "git non lance" in outcome.reason, outcome.reason


HIDDEN = "$Id: ETAPE CACHEE rm -rf ~ $"


def test_w15_ident_collapsed_disk_bytes_differ_from_head_and_are_refused():
    """W15 (closing review n°2 F-maj). `.gitattributes` commits `*.md ident`; the plan
    on disk carries `$Id: ETAPE CACHEE … $`, which the `ident` clean collapses to `$Id$`
    in the blob: `diff --quiet HEAD` reads 0 while the disk bytes are in no commit, in
    neither the raw blob nor its smudged form. MUTANT M15: the byte comparison replaced
    by `diff --quiet HEAD` alone => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        (repo.root / ".gitattributes").write_text("*.md ident\n", encoding="utf-8")
        repo.plan = plan_text() + f"\n{HIDDEN}\n"
        repo.build()
        assert "ETAPE CACHEE" not in git(repo.root, "cat-file", "-p", f"HEAD:./{PLAN_REL}"), \
            "le blob garde l'ident : W15 ne mesure rien"
        assert "ETAPE CACHEE" in repo.plan_path().read_text(encoding="utf-8")
        outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "octets" in outcome.reason, outcome.reason


def test_w15b_ident_expanded_by_checkout_is_identical_to_head():
    """W15b (non-vacuity of the `--filters` leg). Under `*.md ident`, a plan freshly
    checked out carries `$Id: <blob sha> $`: legitimate, the smudged HEAD. MUTANT M15b:
    only the raw blob compared => SKIP."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        (repo.root / ".gitattributes").write_text("*.md ident\n", encoding="utf-8")
        repo.plan = plan_text() + "\n$Id$\n"
        repo.build()
        repo.plan_path().unlink()
        git(repo.root, "checkout", "--", PLAN_REL)
        repo.plan = repo.plan_path().read_text(encoding="utf-8")
        assert "$Id: " in repo.plan, "ident non developpe : W15b ne mesure rien"
        repo.build()
        outcome = repo.outcome()
    assert outcome.decision == night_approve.APPROVE, outcome.reason


def _hidden_behind_index_flag(tmp: str, flag: str) -> night_approve.TaskOutcome:
    repo = Repo(Path(tmp)).build()
    git(repo.root, "update-index", flag, "--", PLAN_REL)
    repo.plan = plan_text() + f"\n{HIDDEN}\n"
    repo.build()  # disk + verdict on the NEW bytes; `add -A` skips the flagged entry
    assert "ETAPE CACHEE" not in git(repo.root, "cat-file", "-p", f"HEAD:./{PLAN_REL}"), \
        f"{flag} n'a pas tenu le blob : le temoin ne mesure rien"
    return repo.outcome()


def test_w16_assume_unchanged_plan_with_other_bytes_is_refused():
    """W16 (closing review n°2 F-maj). `update-index --assume-unchanged`: git never reads
    the worktree, `diff --quiet HEAD` reads 0. MUTANT M16 = M15 => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        outcome = _hidden_behind_index_flag(tmp, "--assume-unchanged")
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason
    assert "--no-assume-unchanged --no-skip-worktree" in outcome.reason, outcome.reason


def test_w16b_skip_worktree_plan_with_other_bytes_is_refused():
    """W16b. Same under `--skip-worktree`. MUTANT M16 => APPROVE."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        outcome = _hidden_behind_index_flag(tmp, "--skip-worktree")
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 8" in outcome.reason, outcome.reason


def test_w17_git_not_launched_on_the_head_leg_is_never_read_untracked():
    """W17 (closing review n°2 F3). `_git_rc` answers None on `cat-file -e` (git not
    launched, timeout): the plan is NOT VERIFIABLE, never « absent de HEAD ». MUTANT M17:
    None folded into « != 0 » => « absent de HEAD (non suivi) »."""
    real = night_approve._git_rc

    def flaky(root, *args):
        return None if args[:1] == ("cat-file",) else real(root, *args)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp)).build()
        with mock.patch.object(night_approve, "_git_rc", side_effect=flaky):
            outcome = repo.outcome()
    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "git non lance" in outcome.reason, outcome.reason
    assert "absent de HEAD" not in outcome.reason, outcome.reason


def test_blob_sha_differs_from_crlf_bytes_so_w7_can_redden():
    """Non-vacuity of W7: the raw bytes on disk do NOT hash to the HEAD blob, so a
    sha comparison (M7) would refuse where git's normalised diff accepts."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        git(root, "init", "-q")
        git(root, "config", "core.autocrlf", "true")
        repo = Repo(root)
        repo.plan = plan_text().replace("\n", "\r\n")
        repo.build()
        assert b"\r\n" in repo.plan_path().read_bytes()
        # Blob id of the raw disk bytes, computed by git itself (no filter applied).
        raw = git(root, "hash-object", "--no-filters", "--", PLAN_REL).strip()
        head = git(root, "rev-parse", f"HEAD:./{PLAN_REL}").strip()
    assert raw != head
