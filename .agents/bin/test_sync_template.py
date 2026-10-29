#!/usr/bin/env python3
"""Tests for sync_template.py. Run: python -m pytest .agents/bin/test_sync_template.py -q

Every destructive case builds its own throw-away two-branch git repo (`main` +
`template/starter-kit`) in a mktemp directory — nothing here touches the real
kit repo. Fetch-dependent cases add a real bare "origin" remote so the fetch
path is exercised for real, not mocked.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sync_template", HERE / "sync_template.py")
st = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = st  # dataclasses' ClassVar/InitVar lookup needs the module registered
_spec.loader.exec_module(st)

DEFAULT_EXCLUDE = """\
strip: .agents/state/
keep: docs/
own: TEMPLATE.md
"""


# --------------------------------------------------------------------------
# fixture harness
# --------------------------------------------------------------------------

def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git -C {root} {args} failed: {r.stderr}")
    return r


def _write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message)


_COMMIT_MSG_HOOK = HERE.parent.parent / ".githooks" / "commit-msg"


def _git_env() -> dict[str, str]:
    """The environment WITHOUT any inherited `GIT_*` (a GIT_DIR exported by an
    enclosing git hook would point the hook at the host repo's history)."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _depot_au_palier_refus(depot: Path) -> None:
    """A throw-away repo whose history sets `.githooks/commit-msg` at its REFUSING
    threshold: 20 conforming commits, written by ONE `git fast-import`."""
    depot.mkdir(parents=True)
    messages = [f"feat: conforme {i} (T-00000001)" for i in range(1, 21)]
    flux = "".join("commit refs/heads/main\ncommitter Banc <banc@example.invalid> 1700000000 +0000\n"
                   f"data {len(m)}\n{m}\n" for m in messages)
    for args, stdin in ((["init", "-q"], None), (["symbolic-ref", "HEAD", "refs/heads/main"], None),
                        (["fast-import", "--quiet"], flux)):
        r = subprocess.run(["git", "-C", str(depot), *args], input=stdin,
                           capture_output=True, text=True, encoding="utf-8", env=_git_env())
        if r.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {r.stderr}")


def _run_commit_msg_hook(depot: Path, message: str) -> subprocess.CompletedProcess:
    msg = depot.parent / "COMMIT_MSG_BANC"
    msg.write_text(message, encoding="utf-8", newline="\n")
    return subprocess.run(["bash", str(_COMMIT_MSG_HOOK), str(msg)], cwd=str(depot),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=_git_env(), timeout=60)


def make_repo(root: Path, main_files: dict[str, str], template_files: dict[str, str],
              exclude_text: str = "") -> None:
    """Build `root` into a repo with a `main` branch (carrying `.template-exclude`,
    read via `git show main:...` by the script) and an independent (orphan)
    `template/starter-kit` branch, HEAD left on `main`."""
    _git(root, "init", "-q", ".")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "commit.gpgsign", "false")

    _git(root, "checkout", "-q", "-b", "main")
    _write_files(root, {**main_files, ".template-exclude": exclude_text})
    _commit_all(root, "seed main")

    _git(root, "checkout", "-q", "--orphan", "template/starter-kit")
    # -f: the inherited index entries are "new" relative to the (nonexistent) orphan
    # HEAD, so plain `git rm` refuses them as "staged changes" without it.
    _git(root, "rm", "-rqf", "--", ".", check=False)
    _write_files(root, template_files)
    _commit_all(root, "seed template")

    _git(root, "checkout", "-q", "main")


def add_origin(root: Path, bare: Path) -> None:
    """Create a bare remote at `bare`, push both branches, leave `origin`
    tracking refs populated in `root`."""
    _git(root.parent, "init", "-q", "--bare", str(bare))
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-q", "origin", "main:main", "template/starter-kit:template/starter-kit")
    _git(root, "fetch", "-q", "origin")


def advance_remote_branch(bare: Path, branch: str, extra_files: dict[str, str], clone_dir: Path) -> None:
    """Push one more commit directly to `bare`'s `branch`, bypassing `root`,
    so `root`'s remote-tracking ref ends up ahead of `root`'s local branch."""
    subprocess.run(["git", "clone", "-q", str(bare), str(clone_dir)],
                    capture_output=True, text=True, check=True)
    _git(clone_dir, "checkout", "-q", branch)
    _write_files(clone_dir, extra_files)
    _commit_all(clone_dir, "advance on origin only")
    _git(clone_dir, "push", "-q", "origin", branch)


def add_branch(root: Path, name: str, files: dict[str, str], exclude_text: str | None = None,
               *, orphan: bool = False, start: str = "main") -> str:
    """Create the local branch `name` — from `start`, or ORPHAN — carrying `files`
    and, when `exclude_text` is given, ITS OWN `.template-exclude` (a third branch
    that read main's file would leave the exclude mutant green). HEAD goes back to
    where it was; returns the new tip sha."""
    back = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if orphan:
        _git(root, "checkout", "-q", "--orphan", name)
        _git(root, "rm", "-rqf", "--", ".", check=False)
    else:
        _git(root, "checkout", "-q", "-b", name, start)
    payload = dict(files)
    if exclude_text is not None:
        payload[".template-exclude"] = exclude_text
    _write_files(root, payload)
    _commit_all(root, f"seed {name}")
    _git(root, "checkout", "-q", back)
    return _git(root, "rev-parse", f"refs/heads/{name}").stdout.strip()


def add_sync_commit(root: Path, label: str, sha: str, *, subject: str | None = None) -> str:
    """Append an EMPTY commit to `template/starter-kit` (plumbing: no checkout, so
    a template checked out stays clean) whose subject is the lineage anchor in its
    MEASURED literal form — `chore(template): sync from <label> @ <sha7>` — or
    `subject` verbatim. Literal on purpose: a mutant of the script's prefix
    constant must not move this fixture with it. The 7 hex are the anchors
    ALREADY on template branches: the script now writes all 40 (M7, M20), and
    the reader must keep accepting both."""
    ref = "refs/heads/template/starter-kit"
    parent = _git(root, "rev-parse", ref).stdout.strip()
    tree = _git(root, "rev-parse", f"{parent}^{{tree}}").stdout.strip()
    message = subject if subject is not None else f"chore(template): sync from {label} @ {sha[:7]}"
    new = _git(root, "-c", "user.email=t@t", "-c", "user.name=t",
               "commit-tree", tree, "-p", parent, "-m", message).stdout.strip()
    _git(root, "update-ref", ref, new, parent)
    return new


def porcelain_snapshot(root: Path) -> tuple[str, set[str]]:
    status = _git(root, "status", "--porcelain").stdout
    files = {p.relative_to(root).as_posix() for p in root.rglob("*")
             if p.is_file() and ".git" not in p.parts}
    return status, files


LONG_BLOCK_A = "\n".join(f"line {i} original" for i in range(120)) + "\n"
LONG_BLOCK_B = "\n".join(f"line {i} CHANGED" for i in range(120)) + "\n"


class SyncTemplateTestCase(unittest.TestCase):
    def setUp(self):
        # Windows flake: git/AV handles can outlive the test and make cleanup
        # raise PermissionError (ledger L-00000035) — never a regression here.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        import io
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = st.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------
# classification: the four classes
# --------------------------------------------------------------------------

class ClassificationTests(SyncTemplateTestCase):
    def test_deletion_propagation_gone_from_main(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n", "old_only_on_template.txt": "stale\n"})
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        delete_section = stdout.split("DELETE")[1].split("FROZEN/OWN")[0]
        self.assertIn("old_only_on_template.txt", delete_section)
        self.assertIn("(gone from main)", delete_section)
        take_new_section = stdout.split("TAKE (new)")[1].split("TAKE (overwrite)")[0]
        self.assertNotIn("old_only_on_template.txt", take_new_section)

    def test_take_new_outside_rules(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "src/new_module.py": "print(1)\n"},
                  template_files={"README.md": "hello\n"})
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("src/new_module.py", stdout)
        take_new_section = stdout.split("TAKE (overwrite)")[0]
        self.assertIn("src/new_module.py", take_new_section)

    def test_strip_never_taken_and_deleted_when_present(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n",
                              ".agents/state/board/TASKS.json": '{"main":true}\n'},
                  template_files={"README.md": "hello\n",
                                   ".agents/state/board/TASKS.json": '{"template":true}\n'},
                  exclude_text="strip: .agents/state/\n")
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        overwrite_section = stdout.split("DELETE")[0]
        self.assertNotIn(".agents/state/board/TASKS.json", overwrite_section)
        self.assertIn(".agents/state/board/TASKS.json", stdout)
        self.assertIn("strip: .agents/state/", stdout)

    def test_prophylactic_strip_quiet_line_run_proceeds(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"},
                  exclude_text="strip: .gemini/backups/\n")
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("prophylactic (no match): strip: .gemini/backups/", stdout)
        self.assertNotIn("WARNING", stdout)

    def test_keep_never_taken_never_deleted(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n",
                              "docs/design/only-on-main.md": "design note\n"},
                  template_files={"README.md": "hello\n",
                                  "docs/usage.html": "<html></html>\n"},
                  exclude_text="keep: docs/\n")
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        take_new_section = stdout.split("TAKE (overwrite)")[0]
        delete_section = stdout.split("DELETE")[1].split("FROZEN/OWN")[0]
        self.assertNotIn("docs/design/only-on-main.md", take_new_section)
        self.assertNotIn("docs/usage.html", delete_section)
        frozen_section = stdout.split("FROZEN/OWN")[1]
        self.assertIn("docs/design/only-on-main.md", frozen_section)
        self.assertIn("docs/usage.html", frozen_section)

    def test_own_untouched(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n", "TEMPLATE.md": "template intro\n"},
                  exclude_text="own: TEMPLATE.md\n")
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertNotIn("TEMPLATE.md", stdout.split("DELETE")[0])
        self.assertIn("TEMPLATE.md", stdout.split("FROZEN/OWN")[1])

    def test_overwrite_lists_diff_body(self):
        make_repo(self.root,
                  main_files={"README.md": "line one\nline TWO changed\nline three\n"},
                  template_files={"README.md": "line one\nline two\nline three\n"})
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("README.md", stdout.split("DELETE")[0])
        self.assertIn("--- diff: README.md ---", stdout)
        self.assertIn("-line two", stdout)
        self.assertIn("+line TWO changed", stdout)

    def test_adaptive_cap_full_vs_truncated(self):
        # <= 10 paths: full diff, no truncation footer.
        main_small = {f"file{i}.txt": LONG_BLOCK_B for i in range(3)}
        template_small = {f"file{i}.txt": LONG_BLOCK_A for i in range(3)}
        make_repo(self.root, main_files=main_small, template_files=template_small)
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertNotIn("truncated", stdout)
        self.assertIn("line 119 CHANGED", stdout)

    def test_adaptive_cap_above_ten_is_capped(self):
        main_big = {f"file{i}.txt": LONG_BLOCK_B for i in range(11)}
        template_big = {f"file{i}.txt": LONG_BLOCK_A for i in range(11)}
        make_repo(self.root, main_files=main_big, template_files=template_big)
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("truncated", stdout)
        self.assertIn("full diff: git diff template/starter-kit:file0.txt main:file0.txt", stdout)
        # line 119 (the 120th changed line) is past the 80-line cap and must not leak through.
        self.assertNotIn("line 119 CHANGED", stdout)


# --------------------------------------------------------------------------
# .template-exclude parsing / validation
# --------------------------------------------------------------------------

class ExcludeRuleTests(SyncTemplateTestCase):
    def test_keep_own_dead_rule_is_config_error(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"},
                  exclude_text="own: DOES_NOT_EXIST.md\n")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR)
        self.assertIn("matches nothing", stderr)

    def test_overlap_precedence_longest_prefix_wins(self):
        make_repo(
            self.root,
            main_files={"README.md": "hello\n"},
            template_files={"README.md": "hello\n",
                             "docs/frozen/keep-me.md": "kept\n",
                             "docs/strip-me.md": "stripped\n"},
            exclude_text="strip: docs/\nkeep: docs/frozen/\n",
        )
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("docs/frozen/keep-me.md", stdout.split("FROZEN/OWN")[1])
        delete_section = stdout.split("DELETE")[1].split("FROZEN/OWN")[0]
        self.assertIn("docs/strip-me.md", delete_section)

    def test_polarity_tie_at_identical_prefix_is_config_error(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"},
                  exclude_text="strip: docs/\nkeep: docs/\n")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR)
        self.assertIn("polarity tie", stderr)

    def test_directory_rule_without_trailing_slash_is_config_error(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "docs/tasks/T-1.md": "task\n"},
                  template_files={"README.md": "hello\n"},
                  exclude_text="keep: docs\n")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_CONFIG_ERROR)
        self.assertIn("no trailing", stderr)


# --------------------------------------------------------------------------
# --check contract: byte-identical, read-only
# --------------------------------------------------------------------------

class CheckContractTests(SyncTemplateTestCase):
    def test_check_byte_identical_from_either_branch(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "src/a.py": "1\n"},
                  template_files={"README.md": "hello v2\n"})
        code1, stdout1, _ = self.run_main(["--check"])
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code2, stdout2, _ = self.run_main(["--check"])
        _git(self.root, "checkout", "-q", "main")
        self.assertEqual(code1, code2)
        self.assertEqual(stdout1, stdout2)

    def test_check_writes_no_worktree_file_or_index_entry(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "src/a.py": "1\n"},
                  template_files={"README.md": "hello v2\n", "gone.txt": "bye\n"})
        before = porcelain_snapshot(self.root)
        code, _stdout, _ = self.run_main(["--check"])
        after = porcelain_snapshot(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(before, after)


# --------------------------------------------------------------------------
# fetch / staleness
# --------------------------------------------------------------------------

class FetchStalenessTests(SyncTemplateTestCase):
    def test_fetch_failure_apply_refuses_without_flag_proceeds_with_it(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"})
        _git(self.root, "remote", "add", "origin",
             str(self.root.parent / "does-not-exist.git"))
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_FETCH_FAILED)
        self.assertIn("fetch", stderr.lower())

        code2, _stdout2, stderr2 = self.run_main(
            ["--apply", "--allow-stale-main", "--allow-stale-template"])
        self.assertEqual(code2, 0, stderr2)
        self.assertIn("WARNING", stderr2)

    def test_fetch_failure_check_banners_and_still_reports(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "new.txt": "n\n"},
                  template_files={"README.md": "hello\n"})
        _git(self.root, "remote", "add", "origin",
             str(self.root.parent / "does-not-exist.git"))
        code, stdout, _ = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("STALENESS NOT PERFORMED", stdout)
        self.assertIn("new.txt", stdout)

    def test_stale_diverged_destination_refused(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"})
        bare = self.root.parent / "origin.git"
        add_origin(self.root, bare)
        clone_dir = self.root.parent / "advance-clone"
        advance_remote_branch(bare, "template/starter-kit",
                               {"extra.txt": "pushed upstream only\n"}, clone_dir)
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_TEMPLATE)
        self.assertIn("DEST", stderr)

        code2, _stdout2, stderr2 = self.run_main(["--apply", "--allow-stale-template"])
        self.assertEqual(code2, 0, stderr2)


# --------------------------------------------------------------------------
# --apply preconditions
# --------------------------------------------------------------------------

class ApplyPreconditionTests(SyncTemplateTestCase):
    def test_missing_template_branch_refused(self):
        _git(self.root, "init", "-q", ".")
        _git(self.root, "config", "commit.gpgsign", "false")
        _git(self.root, "checkout", "-q", "-b", "main")
        _write_files(self.root, {"README.md": "hello\n"})
        _commit_all(self.root, "seed main")
        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_NO_TEMPLATE_BRANCH)
        self.assertIn("no local", stderr.lower())

    def test_wrong_branch_refused(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"})
        # HEAD is on main, not template/starter-kit
        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_WRONG_BRANCH)
        self.assertIn("HEAD is on", stderr)

    def test_dirty_tree_refused(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n"},
                  template_files={"README.md": "hello\n"})
        _git(self.root, "checkout", "-q", "template/starter-kit")
        (self.root / "untracked.txt").write_text("oops\n", encoding="utf-8")
        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_DIRTY_TREE)
        self.assertIn("dirty", stderr.lower())


# --------------------------------------------------------------------------
# apply + verification + recovery
# --------------------------------------------------------------------------

class ApplyVerificationTests(SyncTemplateTestCase):
    def test_eol_crlf_fixture_verifies_post_apply(self):
        make_repo(
            self.root,
            main_files={
                "README.md": "hello\n",
                ".gitattributes": "*.ps1 text eol=crlf\n",
                "scripts/tool.ps1": "Write-Host 'one'\nWrite-Host 'two'\n",
            },
            template_files={"README.md": "hello\n",
                             ".gitattributes": "*.ps1 text eol=crlf\n"},
        )
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, stdout, stderr = self.run_main(
            ["--apply", "--allow-stale-main", "--allow-stale-template"])
        self.assertEqual(code, 0, stderr + stdout)

        on_disk = (self.root / "scripts" / "tool.ps1").read_bytes()
        self.assertIn(b"\r\n", on_disk, "checked-out eol=crlf file should carry CRLF on disk")

        main_sha = _git(self.root, "ls-tree", "main", "--", "scripts/tool.ps1").stdout.split()[2]
        got_sha = st.hash_worktree_file(self.root, "scripts/tool.ps1")
        self.assertEqual(got_sha, main_sha,
                          "hash-object --path must re-apply the clean filter so eol=crlf verifies")

    def test_post_apply_verification_catches_mismatch_and_recovery_restores(self):
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "new_file.txt": "fresh from main\n"},
                  template_files={"README.md": "hello\n"})
        _git(self.root, "checkout", "-q", "template/starter-kit")
        template_head = _git(self.root, "rev-parse", "HEAD").stdout.strip()

        code, _stdout, stderr = self.run_main(
            ["--apply", "--allow-stale-main", "--allow-stale-template"])
        self.assertEqual(code, 0, stderr)
        self.assertTrue((self.root / "new_file.txt").is_file())

        # Plant a mismatch: corrupt the freshly-taken file after a successful apply.
        (self.root / "new_file.txt").write_text("corrupted by test\n", encoding="utf-8")
        main_sha = _git(self.root, "ls-tree", "main", "--", "new_file.txt").stdout.split()[2]
        entries = [st.ManifestEntry("new_file.txt", "take", main_sha)]
        failures = st.verify_manifest(self.root, entries)
        self.assertTrue(failures)
        self.assertIn("new_file.txt", failures[0])

        # Recovery per the script's own printed order: git reset; git checkout -- .;
        # then remove newly-created paths by name (they are untracked once reset —
        # `.template-exclude` is also a take-new path here, main's only, so both go).
        rules = st.parse_exclude(st.read_exclude(self.root, "main"))
        plan = st.build_plan(st.list_tree(self.root, "main"),
                              st.list_tree(self.root, "template/starter-kit"), rules)
        _git(self.root, "reset")
        _git(self.root, "checkout", "--", ".")
        for p in plan.take_new:
            (self.root / p).unlink()
        self.assertEqual(_git(self.root, "rev-parse", "HEAD").stdout.strip(), template_head)
        status = _git(self.root, "status", "--porcelain").stdout.strip()
        self.assertEqual(status, "", "tree must be byte-identical to template HEAD after recovery")


# --------------------------------------------------------------------------
# dashboard build staleness (T-00000232)
# --------------------------------------------------------------------------

# `--apply` in these fixtures has no reachable remote, so the two pre-existing
# staleness flags are always passed: they let a run that the new guard clears
# reach exit 0, which is what makes the negative controls below mean something.
_APPLY_OK = ["--apply", "--allow-stale-main", "--allow-stale-template"]

UI_BUILD_FILES = {".agents/ui/index.html": "<html>built</html>\n"}
UI_SOURCE_FILES = {".agents/ui-src/src/App.jsx": "export default () => null\n"}


class UiBuildStalenessTests(SyncTemplateTestCase):
    def _repo_with_ui(self, main_extra: dict[str, str]) -> None:
        """main carries `main_extra` (source and/or build) in ONE seed commit —
        the normal case where sources and bundle are committed together."""
        make_repo(self.root,
                  main_files={"README.md": "hello\n", **main_extra},
                  template_files={"README.md": "hello\n"},
                  exclude_text="strip: .agents/ui-src/\n")

    def test_source_committed_after_build_refused(self):
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'edited'\n"})
        _commit_all(self.root, "edit the front source, forget the rebuild")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_UI_BUILD)
        self.assertIn("STALE", stderr)
        self.assertIn("npm run build", stderr)
        # The limit is stated in the refusal itself, not only in the source.
        self.assertIn("ORDER OF COMMITS", stderr)

    def test_build_committed_after_source_not_refused(self):
        """Negative control for the case above: without it the refusal test does
        not distinguish a working guard from one that refuses everything."""
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'edited'\n"})
        _commit_all(self.root, "edit the front source")
        _write_files(self.root, {".agents/ui/index.html": "<html>rebuilt</html>\n"})
        _commit_all(self.root, "rebuild the bundle")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("STALE", stderr)

    def test_one_commit_touching_both_not_refused(self):
        """The normal maintenance case: sources and rebuilt bundle in one commit.
        A commit is its own ancestor, so this must pass."""
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'e'\n",
                                  ".agents/ui/index.html": "<html>rebuilt</html>\n"})
        _commit_all(self.root, "edit and rebuild together")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, 0, stderr)

    def test_build_directory_absent_not_refused(self):
        """A project with no dashboard is not this guard's business."""
        self._repo_with_ui(UI_SOURCE_FILES)
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'e'\n"})
        _commit_all(self.root, "edit the front source, no build dir at all")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, 0, stderr)

    def test_source_directory_absent_not_refused(self):
        self._repo_with_ui(UI_BUILD_FILES)
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, 0, stderr)

    def test_the_refusal_NAMES_the_files_that_changed_since_the_build(self):
        """T-00000374 — the refusal used to give two abbreviated SHAs and nothing
        else, so judging it meant running `git show` on both.

        MEASURED, and this is why the list is not cosmetic: on 2026-08-25 the
        refusal fired on this repo. What had actually changed under `ui-src/`
        since the build was two SHELL scripts and ONE LINE of `package.json` (the
        `test:e2e` command) — none of which can enter a Vite bundle, and a rebuild
        confirmed it with byte-identical output, twice. The commit-order proxy was
        right about the order and wrong about the world.

        A manual investigation of the single blamed commit MISSED `package.json`
        entirely, because the gap spans more commits than the one the SHA names.
        That is exactly what the list prevents.
        """
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {
            ".agents/ui-src/src/App.jsx": "export default () => 'edited'" + chr(10),
            ".agents/ui-src/scripts/helper.sh": "#!/usr/bin/env bash" + chr(10) + "exit 0" + chr(10),
        })
        _commit_all(self.root, "touch two files under ui-src")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_UI_BUILD)
        self.assertIn("WHAT CHANGED under", stderr)
        # BOTH files named — a list that showed only one would be worse than none,
        # because it would look complete.
        self.assertIn("ui-src/src/App.jsx", stderr)
        self.assertIn("ui-src/scripts/helper.sh", stderr)
        self.assertIn("2 file(s)", stderr)
        # And it must NOT decide for the reader: the refusal still stands, and it
        # still names the remedy. Surfacing evidence is not granting permission.
        self.assertIn("npm run build", stderr)
        self.assertIn("false", stderr.lower())

    def test_negative_control_the_list_is_not_hardcoded_prose(self):
        """A message that always printed the same filenames would satisfy the arm
        above (L-00000232). Change WHICH file moves and require the list to follow.
        """
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/README.md": "notes" + chr(10)})
        _commit_all(self.root, "touch a different file entirely")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main(["--apply"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_UI_BUILD)
        self.assertIn("ui-src/README.md", stderr)
        self.assertIn("1 file(s)", stderr)
        self.assertNotIn("helper.sh", stderr, "the list is prose, not a measurement")

    def test_allow_stale_build_lifts_the_refusal(self):
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'edited'\n"})
        _commit_all(self.root, "edit the front source, forget the rebuild")
        _git(self.root, "checkout", "-q", "template/starter-kit")

        code, _stdout, stderr = self.run_main([*_APPLY_OK, "--allow-stale-build"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("WARNING", stderr)
        self.assertIn("--allow-stale-build", stderr)

    def test_check_never_refuses_on_a_stale_build(self):
        """--check is a dry run: it describes the plan, it does not gate."""
        self._repo_with_ui({**UI_BUILD_FILES, **UI_SOURCE_FILES})
        _write_files(self.root, {".agents/ui-src/src/App.jsx": "export default () => 'edited'\n"})
        _commit_all(self.root, "edit the front source, forget the rebuild")

        code, _stdout, _stderr = self.run_main(["--check"])
        self.assertEqual(code, 0)


# --------------------------------------------------------------------------
# --source and the lineage guard (T-00001065)
# --------------------------------------------------------------------------
# Each test names the MUTANT it must turn red (plan T-00001065 § Tests, plus
# M18-M20 from the approval reserves and M21 for "cannot conclude = 22").

UI_STALE_EDIT = {".agents/ui-src/src/App.jsx": "export default () => 'edited'\n"}


class SourceRefTests(SyncTemplateTestCase):
    def _base(self, **extra_main: str) -> None:
        make_repo(self.root,
                  main_files={"README.md": "hello\n", **extra_main},
                  template_files={"README.md": "hello\n"})

    def _commit_on(self, branch: str, files: dict[str, str], message: str) -> str:
        back = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(self.root, "checkout", "-q", branch)
        _write_files(self.root, files)
        _commit_all(self.root, message)
        _git(self.root, "checkout", "-q", back)
        return _git(self.root, "rev-parse", f"refs/heads/{branch}").stdout.strip()

    def _feat_behind_origin(self) -> None:
        """`feat` pushed to a bare origin, then advanced THERE only: the local
        `feat` is one commit behind `origin/feat` once a fetch brings it in."""
        self._base()
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        bare = self.root.parent / "origin.git"
        add_origin(self.root, bare)
        _git(self.root, "push", "-q", "origin", "feat:feat")
        _git(self.root, "fetch", "-q", "origin")
        advance_remote_branch(bare, "feat", {"upstream.txt": "pushed upstream only\n"},
                              self.root.parent / "advance-clone")

    @staticmethod
    def _section(stdout: str, start: str, end: str) -> str:
        return stdout.split(start)[1].split(end)[0]

    # -- the source feeds every read -----------------------------------------

    def test_source_takes_paths_from_the_named_branch(self):
        """M1 — `list_tree(root, MAIN_REF)` left in `main()`."""
        self._base()
        add_branch(self.root, "feat", {"src/feat_only.py": "x\n"})
        self._commit_on("main", {"main_after_branch.txt": "m\n"}, "main moves on")
        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        take_new = self._section(stdout, "TAKE (new)", "TAKE (overwrite)")
        self.assertIn("src/feat_only.py", take_new)
        self.assertNotIn("main_after_branch.txt", stdout)

    def test_exclude_is_read_on_the_source(self):
        """M2 — `read_exclude(root, MAIN_REF)`: main's exclude is EMPTY, feat's
        strips `secret/`; read on main, `secret/x.txt` would be taken."""
        self._base()
        add_branch(self.root, "feat", {"secret/x.txt": "s\n"}, exclude_text="strip: secret/\n")
        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        take_new = self._section(stdout, "TAKE (new)", "TAKE (overwrite)")
        self.assertNotIn("secret/x.txt", take_new)

    def test_staleness_is_measured_on_the_source_ref(self):
        """M3 — `staleness` on `MAIN_REF`; M4 — `try_fetch` without the source
        (origin/feat would stay at the tip fetched in setup: not behind)."""
        self._feat_behind_origin()
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, _stdout, stderr = self.run_main(["--apply", "--source", "feat"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_SOURCE, stderr)
        self.assertIn("SOURCE feat is behind origin/feat by 1 commit(s)", stderr)
        self.assertIn("--allow-stale-source", stderr)

    def test_ui_build_staleness_is_measured_on_the_source(self):
        """M5 — `_last_commit_touching(root, MAIN_REF, ...)`: main's build is
        fresh, feat edited the UI source after it."""
        make_repo(self.root,
                  main_files={"README.md": "hello\n", **UI_BUILD_FILES, **UI_SOURCE_FILES},
                  template_files={"README.md": "hello\n"},
                  exclude_text="strip: .agents/ui-src/\n")
        add_branch(self.root, "feat", UI_STALE_EDIT)
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, _stdout, stderr = self.run_main([*_APPLY_OK, "--source", "feat"])
        self.assertEqual(code, st.EXIT_REFUSED_STALE_UI_BUILD, stderr)
        self.assertIn("STALE on feat", stderr)
        self.assertIn("Remedy, on feat", stderr)
        # Negative control: the same apply from main (fresh build) is not refused.
        code2, _stdout2, stderr2 = self.run_main(_APPLY_OK)
        self.assertEqual(code2, 0, stderr2)

    def test_apply_checks_out_from_the_source_and_verifies(self):
        """M6 — `git checkout MAIN_REF --`; M7 — suggested subject left at
        "from main", or without the EXACT `@ <sha>` of the source read — all 40
        hex since the E-24 closing pair (T5): a 7-hex anchor shares its prefix
        with ~23 000 objects' worth of chance."""
        self._base()
        feat_sha = add_branch(self.root, "feat",
                              {"README.md": "hello from feat\n", "new.txt": "n\n"})
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, stdout, stderr = self.run_main([*_APPLY_OK, "--source", "feat"])
        self.assertEqual(code, 0, stderr + stdout)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "hello from feat\n")
        self.assertTrue((self.root / "new.txt").is_file())
        # The suggested command is `git commit` ALONE, on a line of its own: a
        # `git add -A` before it would sweep local state into the template
        # (S-00003505, MEDIUM 1).
        self.assertEqual(len(feat_sha), 40, feat_sha)
        # The second `-m` is the traced `Sans-tache:` way out `.githooks/commit-msg`
        # accepts (T-01M54GEQ68NTP1C34EYTF0SDHX).
        self.assertIn(f'\n  git commit -m "chore(template): sync from feat @ {feat_sha}"'
                      ' -m "Sans-tache: synchronisation du gabarit"\n',
                      stdout)
        self.assertNotIn("git add -A", stdout)
        self.assertNotIn("git add", stdout)

    def test_overwrite_diff_is_against_the_source(self):
        """M8 — `diff_lines` against `MAIN_REF` (main == template here: empty diff)."""
        self._base()
        add_branch(self.root, "feat", {"README.md": "hello FEAT\n"})
        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("--- diff: README.md ---", stdout)
        self.assertIn("+hello FEAT", stdout)

    def test_unknown_or_template_source_refused(self):
        """M9 — the 20/21 checks removed, or the leading-dash validation removed."""
        self._base()
        code, _stdout, stderr = self.run_main(["--check", "--source", "nope"])
        self.assertEqual(code, st.EXIT_REFUSED_SOURCE_NOT_A_BRANCH, stderr)
        self.assertIn("not a local branch", stderr)
        code, _stdout, stderr = self.run_main(["--check", "--source", "template/starter-kit"])
        self.assertEqual(code, st.EXIT_REFUSED_SOURCE_IS_TEMPLATE, stderr)
        with self.assertRaises(SystemExit):
            self.run_main(["--check", "--source=-x"])

    def test_allow_stale_source_alias_lifts_the_source_refusal(self):
        """M10 — `--allow-stale-source` not wired to the `--allow-stale-main` dest."""
        self._feat_behind_origin()
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, _stdout, stderr = self.run_main(["--apply", "--source", "feat", "--allow-stale-source"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("(--allow-stale-source)", stderr)

    def test_default_source_is_main_and_header_names_it(self):
        """M11 — the default changed."""
        self._base()
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        code, stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("TEMPLATE SYNC PLAN  (main -> template/starter-kit)", stdout)
        self.assertNotIn("feat_only.txt", stdout)

    def test_report_names_the_real_source(self):
        """M12 in five variants, each red on its own: a `build_plan` without
        `source_label`, b header, c class heads, d "full diff" footer, e the
        `SOURCE BEHIND` banner."""
        make_repo(self.root,
                  main_files={**{f"file{i}.txt": LONG_BLOCK_A for i in range(11)},
                              "README.md": "hello\n"},
                  template_files={**{f"file{i}.txt": LONG_BLOCK_A for i in range(11)},
                                  "README.md": "hello\n", "gone.txt": "only on template\n"})
        add_branch(self.root, "feat", {f"file{i}.txt": LONG_BLOCK_B for i in range(11)})
        bare = self.root.parent / "origin.git"
        add_origin(self.root, bare)
        _git(self.root, "push", "-q", "origin", "feat:feat")
        advance_remote_branch(bare, "feat", {"upstream.txt": "u\n"}, self.root.parent / "adv")

        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("gone.txt  (gone from feat)", stdout)                          # a
        self.assertIn("TEMPLATE SYNC PLAN  (feat -> template/starter-kit)", stdout)  # b
        self.assertIn("on feat, not on template", stdout)                            # c
        self.assertIn("with feat's content", stdout)                                 # c
        self.assertIn("full diff: git diff template/starter-kit:file0.txt feat:file0.txt",
                      stdout)                                                        # d
        self.assertIn("SOURCE BEHIND: feat is behind origin/feat by 1 commit(s)", stdout)  # e
        for wrong in ("gone from main", "(main ->", "main's content", " main:file0.txt",
                      "on main, not on template"):
            self.assertNotIn(wrong, stdout)

    def test_source_never_pushed_check_banners_apply_refuses_13(self):
        """M13 — `try_fetch` fetching the source apart and swallowing its failure
        (distinct from M4: the source IS fetched, its error is lost)."""
        self._base()
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        add_origin(self.root, self.root.parent / "origin.git")  # main + template only
        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("STALENESS NOT PERFORMED", stdout)
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, _stdout, stderr = self.run_main(["--apply", "--source", "feat"])
        self.assertEqual(code, st.EXIT_REFUSED_FETCH_FAILED, stderr)
        self.assertIn("fetch", stderr)
        self.assertIn("staleness of feat and template/starter-kit", stderr)

    # -- the lineage guard ---------------------------------------------------

    def test_foreign_lineage_refused_in_check_and_apply(self):
        """M14a — guard never called; M14b — `--allow-foreign-source` ignored.
        The anchor names main's tip; a branch of main passes, an orphan branch,
        a branch moved BEHIND the anchor and an anchor sha absent from the repo
        are all 22; the escape lifts 22 in both modes and SAYS what it skipped."""
        self._base()
        main_tip = self._commit_on("main", {"second.txt": "2\n"}, "main, second commit")
        _git(self.root, "branch", "old", "main~1")
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="", orphan=True)
        add_sync_commit(self.root, "main", main_tip)

        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)
        code, _stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        code, stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("REFUSE: LINEAGE", stderr)
        self.assertIn("does not descend from", stderr)
        self.assertNotIn("TEMPLATE SYNC PLAN", stdout, "a refused --check prints no plan")
        code, _stdout, stderr = self.run_main(["--check", "--source", "old"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)

        code, stdout, stderr = self.run_main(["--check", "--source", "other",
                                              "--allow-foreign-source"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("LINEAGE NOT VERIFIED (--allow-foreign-source)", stderr)
        self.assertIn("SKIPPED: the check that other continues the branch the template was "
                      "last synced from", stderr)
        for token in ("WARNING", "STALE"):
            self.assertNotIn(token, stderr)
        self.assertIn("(gone from other)", stdout)

        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, _stdout, stderr = self.run_main([*_APPLY_OK, "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertEqual(_git(self.root, "status", "--porcelain").stdout, "")
        code, _stdout, stderr = self.run_main([*_APPLY_OK, "--source", "other",
                                               "--allow-foreign-source"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("LINEAGE NOT VERIFIED (--allow-foreign-source)", stderr)

        add_sync_commit(self.root, "ghost", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("not one commit in this repository", stderr)

    def test_lineage_anchor_is_the_newest_sync_subject_in_history(self):
        """M15 — anchor read on the HEAD subject only (here a non-sync commit,
        over an unanchored `sync from main`). Also red if the OLDEST anchor won:
        the older one names an orphan branch main does not descend from."""
        self._base()
        other_sha = add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="", orphan=True)
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        add_sync_commit(self.root, "other", other_sha)
        add_sync_commit(self.root, "main", main_tip)
        add_sync_commit(self.root, "", "", subject="chore(template): sync from main")
        add_sync_commit(self.root, "", "", subject="fix(template): tweak TEMPLATE.md")

        code, _stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn(f"@ {main_tip[:7]}", stderr, "the refusal names the anchor it used")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)

    def test_source_refusals_precede_the_ui_guard(self):
        """M16 — the source guard placed after `_refuse_if_ui_build_is_stale`:
        main AND `other` are UI-stale, so a guard moved behind it answers 19."""
        make_repo(self.root,
                  main_files={"README.md": "hello\n", **UI_BUILD_FILES, **UI_SOURCE_FILES},
                  template_files={"README.md": "hello\n"},
                  exclude_text="strip: .agents/ui-src/\n")
        main_tip = self._commit_on("main", UI_STALE_EDIT, "edit the front source, no rebuild")
        add_branch(self.root, "other", {**UI_BUILD_FILES, **UI_SOURCE_FILES},
                   exclude_text="strip: .agents/ui-src/\n", orphan=True)
        self._commit_on("other", UI_STALE_EDIT, "other: edit the front source, no rebuild")
        add_sync_commit(self.root, "main", main_tip)
        _git(self.root, "checkout", "-q", "template/starter-kit")

        for source, expected in (("nope", st.EXIT_REFUSED_SOURCE_NOT_A_BRANCH),
                                 ("template/starter-kit", st.EXIT_REFUSED_SOURCE_IS_TEMPLATE),
                                 ("other", st.EXIT_REFUSED_FOREIGN_LINEAGE)):
            code, _stdout, stderr = self.run_main([*_APPLY_OK, "--source", source])
            self.assertEqual(code, expected, f"--source {source}: {stderr}")
        # Control: the UI guard still bites once the source is usable.
        code, _stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, st.EXIT_REFUSED_STALE_UI_BUILD, stderr)

    def test_lineage_guard_is_silent_without_an_anchor(self):
        """M17 — the guard CLOSED without an anchor (or the merge-base variant,
        measured 28/32 red). THIS PINS A NAMED HOLE, it does not bless it: a
        template with no anchored subject is NOT guarded (module docstring,
        BOUNDS). The day the hole is closed, this test turns red and the
        docstring changes with it."""
        self._base()
        add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="", orphan=True)
        code, _stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("LINEAGE UNGUARDED", stderr)
        self.assertIn("NOT checked", stderr)
        for token in ("WARNING", "STALE"):
            self.assertNotIn(token, stderr)

    def test_homonymous_tag_is_never_read(self):
        """M18 — the source resolved by NAME instead of `refs/heads/<name>`: a tag
        `feat` on main would win (git prefers refs/tags), the plan would be main's
        tree and the guard would validate main. A tag alone is not a source (20)."""
        self._base()
        feat_sha = add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        _git(self.root, "tag", "feat", "main")
        _git(self.root, "tag", "v1", "main")
        add_sync_commit(self.root, "feat", feat_sha)

        code, stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("feat_only.txt", self._section(stdout, "TAKE (new)", "TAKE (overwrite)"))
        code, _stdout, stderr = self.run_main(["--check", "--source", "v1"])
        self.assertEqual(code, st.EXIT_REFUSED_SOURCE_NOT_A_BRANCH, stderr)

    def test_revert_and_quoting_subjects_are_not_anchors(self):
        """M19 — `re.search` instead of `re.match` on the subject: the two newest
        subjects QUOTE an anchor naming an orphan branch; taken as anchors, they
        would refuse main and let the orphan through."""
        self._base()
        other_sha = add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="", orphan=True)
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        quoted = f"chore(template): sync from other @ {other_sha[:7]}"
        add_sync_commit(self.root, "main", main_tip)
        add_sync_commit(self.root, "", "", subject=f'Revert "{quoted}"')
        add_sync_commit(self.root, "", "", subject=f"docs(template): explain {quoted}")

        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)
        code, _stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)

    def test_apply_subject_round_trips_as_the_next_anchor(self):
        """M20 — the subject `--apply` WRITES and the anchor the guard READS drift
        apart: commit the suggested subject verbatim, then the next run must be
        guarded by it (bare main refused, feat accepted)."""
        self._base()
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, stdout, stderr = self.run_main([*_APPLY_OK, "--source", "feat"])
        self.assertEqual(code, 0, stderr + stdout)
        # The SUBJECT is the first `-m` (cut on `" -m "`): the second is the
        # `Sans-tache:` trailer, which the anchor never reads.
        found = [ln.split('git commit -m "', 1)[1].split('" -m "', 1)[0]
                 for ln in stdout.splitlines() if 'git commit -m "' in ln]
        self.assertEqual(len(found), 1, stdout)
        self.assertNotIn("git add -A", stdout)
        _commit_all(self.root, found[0])

        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        code, _stdout, stderr = self.run_main(["--check", "--source", "feat"])
        self.assertEqual(code, 0, stderr)

    def test_printed_commit_passes_the_commit_msg_hook(self):
        """D3 (T-01M54GEQ68NTP1C34EYTF0SDHX) — the command `--apply` prints, parsed
        as a shell would, must pass the REAL `.githooks/commit-msg` in a throw-away
        repo at the REFUSING threshold (20 conforming commits): printed message
        (subject, blank line, trailer) → rc 0; subject alone → rc 1. Mutant
        "trailer dropped" (second `-m` removed from `do_apply`) → red here."""
        self._base()
        add_branch(self.root, "feat", {"feat_only.txt": "f\n"})
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, stdout, stderr = self.run_main([*_APPLY_OK, "--source", "feat"])
        self.assertEqual(code, 0, stderr + stdout)
        lines = [ln for ln in stdout.splitlines() if 'git commit -m "' in ln]
        self.assertEqual(len(lines), 1, stdout)
        argv = shlex.split(lines[0])
        self.assertEqual(argv[:2], ["git", "commit"], argv)
        # `git commit -m A -m B` records A and B as paragraphs, a blank line apart.
        paragraphs = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-m"]
        depot = Path(self._tmp.name) / "palier-refus"
        _depot_au_palier_refus(depot)
        full = _run_commit_msg_hook(depot, "\n\n".join(paragraphs) + "\n")
        self.assertEqual(full.returncode, 0, full.stderr)
        alone = _run_commit_msg_hook(depot, paragraphs[0] + "\n")
        self.assertEqual(alone.returncode, 1, alone.stderr)
        self.assertIn("aucun numéro de tâche", alone.stderr)

    def test_lineage_guard_that_cannot_conclude_refuses(self):
        """M21 — "cannot conclude = 22" (B-C6): with no local template branch the
        template's history cannot be read, and the guard refuses instead of
        reading that as "no anchor" (which would be inert, then exit 17)."""
        _git(self.root, "init", "-q", ".")
        _git(self.root, "config", "commit.gpgsign", "false")
        _git(self.root, "checkout", "-q", "-b", "main")
        _write_files(self.root, {"README.md": "hello\n", ".template-exclude": ""})
        _commit_all(self.root, "seed main")
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("cannot be read", stderr)

    # -- security pass S-00003505: nothing is read by a NAME a tag can take ----

    def test_homonymous_tag_never_redirects_the_anchor(self):
        """M22 — the anchor resolved by NAME (`rev-parse --verify <sha7>^{commit}`):
        a tag named like the anchor's 7 hex, on the root of an orphan branch, wins
        over the object prefix (git prefers a ref) and validates that orphan."""
        self._base()
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        other_root = add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="",
                                orphan=True)
        add_sync_commit(self.root, "main", main_tip)
        _git(self.root, "tag", main_tip[:7], other_root)

        code, _stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("does not descend from", stderr)
        code, _stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)

    def test_anchor_naming_a_non_commit_object_is_refused(self):
        """M23 — the `cat-file -t` check removed: the ONE object the anchor's hex
        names is an annotated TAG OBJECT on an orphan root (a hand-written anchor,
        or a brute-forced 7-hex collision where the real commit is absent);
        `merge-base` peels it to that commit and would validate the orphan."""
        self._base()
        other_root = add_branch(self.root, "other", {"o.txt": "o\n"}, exclude_text="",
                                orphan=True)
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t",
             "tag", "-a", "-m", "lure", "lure", other_root)
        tag_object = _git(self.root, "rev-parse", "refs/tags/lure").stdout.strip()
        add_sync_commit(self.root, "main", tag_object)

        code, _stdout, stderr = self.run_main(["--check", "--source", "other"])
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("is a tag, not a commit", stderr)

    def _check_with_disambiguate_listing(self, *listed: str) -> tuple[int, str]:
        """`--check` from `main`, its anchor naming `main`'s tip, with
        `--disambiguate` answered by a stub listing `listed` (a real 7-hex
        collision costs ~2^28 objects); every other git call is real, so the
        `cat-file -t` that types each listed object is the real one."""
        real_git = st.git

        def stub(root, *args, **kw):
            if args[:1] == ("rev-parse",) and args[1].startswith("--disambiguate="):
                return subprocess.CompletedProcess(["git", *args], 0,
                                                   "".join(f"{o}\n" for o in listed), "")
            return real_git(root, *args, **kw)

        with mock.patch.object(st, "git", stub):
            code, _stdout, stderr = self.run_main(["--check"])
        return code, stderr

    def test_ambiguous_anchor_prefix_is_refused(self):
        """M24 — "exactly one commit" relaxed to "the first": the stub names TWO
        real COMMITS, the TRUE anchor first — taken, it would pass."""
        self._base()
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        add_sync_commit(self.root, "main", main_tip)
        other_commit = _git(self.root, "rev-parse", "refs/heads/template/starter-kit").stdout.strip()
        self.assertNotEqual(other_commit, main_tip)
        code, stderr = self._check_with_disambiguate_listing(main_tip, other_commit)
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("AMBIGUOUS: 2 commits start with it", stderr)

    def test_a_non_commit_object_sharing_the_prefix_is_not_an_ambiguity(self):
        """M24b (E-24 closing pair, T5) — "exactly one OBJECT" put back: a TREE
        sharing the anchor's prefix (any blob or tree may, ~23 000 objects here)
        would make a sound anchor AMBIGUOUS and refuse 22 on every run."""
        self._base()
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        add_sync_commit(self.root, "main", main_tip)
        tree = _git(self.root, "rev-parse", "main^{tree}").stdout.strip()
        self.assertEqual(_git(self.root, "cat-file", "-t", tree).stdout.strip(), "tree")
        code, stderr = self._check_with_disambiguate_listing(main_tip, tree)
        self.assertEqual(code, 0, stderr)

    def test_an_object_git_cannot_type_is_refused_not_dropped(self):
        """M24c — the commit filter made fail-OPEN: an object `--disambiguate`
        lists but `cat-file -t` cannot type, silently dropped, would leave the
        true anchor alone and pass. A guard that cannot conclude refuses."""
        self._base()
        main_tip = _git(self.root, "rev-parse", "main").stdout.strip()
        add_sync_commit(self.root, "main", main_tip)
        code, stderr = self._check_with_disambiguate_listing(main_tip, "f" * 40)
        self.assertEqual(code, st.EXIT_REFUSED_FOREIGN_LINEAGE, stderr)
        self.assertIn("git cannot type 'ffff", stderr)

    def test_homonymous_tag_never_stands_for_the_template(self):
        """M25 — `template/starter-kit` resolved by bare NAME: a local tag of that
        name on the template's FIRST commit wins (git prefers refs/tags). a:
        `list_tree` misses `t2.txt`; b: `diff_lines` diffs the old README; c/d:
        the DEST staleness count reads the tag, one behind origin (--check
        banner, --apply refusal 15)."""
        make_repo(self.root, main_files={"README.md": "hello main\n"},
                  template_files={"README.md": "hello\n"})
        first = _git(self.root, "rev-parse", "refs/heads/template/starter-kit").stdout.strip()
        self._commit_on("template/starter-kit", {"README.md": "hello v2\n", "t2.txt": "t\n"},
                        "template v2")
        add_origin(self.root, self.root.parent / "origin.git")
        _git(self.root, "tag", "template/starter-kit", first)

        code, stdout, stderr = self.run_main(["--check"])
        self.assertEqual(code, 0, stderr)
        self.assertIn("t2.txt", self._section(stdout, "\nDELETE —", "\nFROZEN/OWN —"))  # a
        self.assertIn("-hello v2", stdout)                                              # b
        self.assertNotIn("DEST BEHIND", stdout)                                         # c
        args = argparse.Namespace(source="main", remote="origin", apply=True,
                                  allow_stale_main=False, allow_stale_template=False)
        main_sha = _git(self.root, "rev-parse", "refs/heads/main").stdout.strip()
        st._check_fetch_and_staleness(self.root, args, io.StringIO(), main_sha)        # d

    def test_glob_like_paths_are_names_never_patterns(self):
        """M26 `checkout`, M27 `rm`, M28 verification `ls-files` without
        GIT_LITERAL_PATHSPECS: TAKE `g[ab].txt` would also check out the
        `strip:`ped `ga.txt`, unseen by the manifest (a leak into the template);
        DELETE `f[ab].txt` would also remove the `own:` `fa.txt`, or the
        verification would read `fa.txt` as the deleted path still tracked."""
        make_repo(self.root,
                  main_files={"README.md": "hello\n", "g[ab].txt": "take me\n",
                              "ga.txt": "stripped\n"},
                  template_files={"README.md": "hello\n", "f[ab].txt": "gone\n",
                                  "fa.txt": "owned\n"},
                  exclude_text="strip: ga.txt\nown: fa.txt\n")
        _git(self.root, "checkout", "-q", "template/starter-kit")
        code, stdout, stderr = self.run_main(_APPLY_OK)
        self.assertEqual(code, 0, stderr + stdout)
        self.assertTrue((self.root / "g[ab].txt").is_file())
        self.assertFalse((self.root / "ga.txt").exists(), "a strip: path was checked out")
        self.assertFalse((self.root / "f[ab].txt").exists())
        self.assertEqual((self.root / "fa.txt").read_text(encoding="utf-8"), "owned\n")
        status = _git(self.root, "status", "--porcelain").stdout
        self.assertNotIn(" ga.txt", status)
        self.assertNotIn(" fa.txt", status)


# --------------------------------------------------------------------------
# the Workflow launcher travels to the adopter (T-01M57JS1GFPVQ93BGEFGX08FDB, lot B)
# --------------------------------------------------------------------------

REAL_EXCLUDE = HERE.parents[1] / st.EXCLUDE_PATH
# Values WRITTEN here: the tree is synthetic, only the RULES are the real ones — except the
# integration witness, which carries the REAL launcher's bytes (read, never parsed).
LAUNCHER = ".claude/workflows/workflow-fournee.js"
LAUNCHER_ARCHIVE = "docs/interne/chantier/lots/workflow-fournee.js"
HOST_DEFS = (".claude/agents/orchestrator.md", ".codex/agents/orchestrator.toml",
             ".github/agents/orchestrator.agent.md", ".gemini/agents/orchestrator.md",
             ".kimi-code/agents/orchestrator.md", "AGENTS.md")
SEED_SRC = ".agents/adopter-seed/gates/PLAN_CHAIN_REQUIRED"
SEED_DEST = ".agents/state/gates/PLAN_CHAIN_REQUIRED"


def _frozen_fixtures(rules: list) -> dict[str, str]:
    """One path per `keep:`/`own:` rule: a rule that matches nothing on either
    ref is a CONFIG ERROR (17), so the real rules need their own fixture."""
    return {(r.prefix + "fixture.txt" if r.is_dir else r.prefix): "frozen\n"
            for r in rules if r.polarity in ("keep", "own")}


def adopter_tree_faults(root: Path, exclude_text: str,
                        launcher_text: str = "// synthetic launcher\n") -> list[str]:
    """Apply a synthetic kit tree governed by `exclude_text` onto a template
    branch, as the maintainer does before an adopter copies it, and list what
    the adopter's tree gets wrong. Empty = the launcher travels. `launcher_text`
    lets the integration witness carry the REAL launcher's bytes."""
    rules = st.parse_exclude(exclude_text)
    main_files = {"README.md": "kit\n", LAUNCHER: launcher_text,
                  LAUNCHER_ARCHIVE: "// kit-only archive\n", SEED_SRC: "armed\n",
                  **{p: f"def {p}\n" for p in HOST_DEFS}, **_frozen_fixtures(rules)}
    make_repo(root, main_files=main_files, template_files={"README.md": "old\n"},
              exclude_text=exclude_text)
    _git(root, "checkout", "-q", st.TEMPLATE_REF)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = st.main(["--root", str(root), *_APPLY_OK])
    if code != st.EXIT_OK:
        return [f"apply rc {code}: {err.getvalue()}{out.getvalue()}"]
    staged = set(_git(root, "ls-files").stdout.splitlines())
    f: list[str] = []
    for path in (LAUNCHER, *HOST_DEFS):
        if path not in staged or not (root / path).is_file():
            f.append(f"{path}: absent from the adopter tree (TAKE expected)")
    if (root / LAUNCHER).is_file() and (root / LAUNCHER).read_bytes() != launcher_text.encode("utf-8"):
        f.append(f"{LAUNCHER}: bytes differ from the kit's")
    # The bytes are not re-read: `verify_manifest` already refuses a divergent copy (rc 18 above).
    for path in (LAUNCHER_ARCHIVE, SEED_SRC):
        if path in staged or (root / path).exists():
            f.append(f"{path}: travelled although `strip:`")
    if SEED_DEST not in staged or not (root / SEED_DEST).is_file() \
            or (root / SEED_DEST).read_text(encoding="utf-8") != "armed\n":
        f.append(f"{SEED_DEST}: the seed did not reach the gates")
    return f


class LauncherTravelsTests(unittest.TestCase):
    """Rules are the kit's REAL `.template-exclude` (it travels, so does this
    bench); the tree is synthetic, so the witness never reads the launcher."""

    def setUp(self):
        if not REAL_EXCLUDE.is_file():
            self.skipTest(f"{REAL_EXCLUDE} absent: launcher travel not judged")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.exclude = REAL_EXCLUDE.read_text(encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _root(self, name: str) -> Path:
        root = Path(self._tmp.name) / name
        root.mkdir()
        return root

    def test_apply_workflow_travels_to_adopter(self):
        self.assertEqual(adopter_tree_faults(self._root("real"), self.exclude), [])

    def test_mutant_strip_of_the_workflows_dir_turns_red(self):
        faults = adopter_tree_faults(self._root("mutant"), self.exclude + "\nstrip: .claude/workflows/\n")
        self.assertIn(f"{LAUNCHER}: absent from the adopter tree (TAKE expected)", faults,
                      "mutant SURVIVOR: a stripped launcher still reads as travelling")

    def _real_launcher(self) -> str:
        real = HERE.parents[1] / LAUNCHER
        if not real.is_file():
            self.skipTest(f"{real} absent: the real launcher's copy not judged")
        return real.read_text(encoding="utf-8")

    def test_apply_copies_the_real_launcher_bytes(self):
        """Integration of T-01M57JS1GFPVQ93BGEFGX08FDB: the REAL launcher's
        bytes, under the REAL rules, reach the adopter's tree byte for byte."""
        real = self._real_launcher()
        root = self._root("real-bytes")
        self.assertEqual(adopter_tree_faults(root, self.exclude, real), [])
        self.assertEqual((root / LAUNCHER).read_bytes(), real.encode("utf-8"))

    def test_mutant_strip_of_the_real_launcher_turns_red(self):
        faults = adopter_tree_faults(self._root("real-mutant"), self.exclude + f"\nstrip: {LAUNCHER}\n",
                                     self._real_launcher())
        self.assertIn(f"{LAUNCHER}: absent from the adopter tree (TAKE expected)", faults,
                      "mutant SURVIVOR: the real launcher, stripped, still reads as travelling")


if __name__ == "__main__":
    unittest.main(verbosity=2)
