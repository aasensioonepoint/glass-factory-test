#!/usr/bin/env python3
"""Tests for module_discovery.py — run: cd .agents/security && python -m unittest test_module_discovery -v"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import module_discovery as md


def touch(root, relpath, content="{}"):
    p = Path(root) / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def lines(root):
    buf = io.StringIO()
    with redirect_stdout(buf):
        md.main(["--root", str(root)])
    return [l.split("\t") for l in buf.getvalue().splitlines()]


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_front_and_back_are_two_modules(self):
        touch(self.root, "frontend/package.json")
        touch(self.root, "backend/pom.xml", "<project/>")
        self.assertEqual(lines(self.root),
                         [["backend", "backend", "0", ""], ["frontend", "frontend", "0", ""]])

    def test_maven_reactor_collapses_to_aggregator(self):
        touch(self.root, "backend/pom.xml", "<project/>")
        touch(self.root, "backend/api/pom.xml", "<project/>")
        touch(self.root, "backend/core/pom.xml", "<project/>")
        self.assertEqual(lines(self.root),
                         [["backend", "backend", "2", "backend/api,backend/core"]])

    def test_deep_java_collapses_to_topmost(self):
        touch(self.root, "a/pom.xml", "<project/>")
        touch(self.root, "a/b/build.gradle", "")
        touch(self.root, "a/b/c/pom.xml", "<project/>")
        self.assertEqual(lines(self.root), [["a", "a", "2", "a/b,a/b/c"]])

    def test_npm_workspaces_collapse(self):
        touch(self.root, "frontend/package.json", json.dumps({"workspaces": ["e2e"]}))
        touch(self.root, "frontend/e2e/package.json")
        self.assertEqual(lines(self.root),
                         [["frontend", "frontend", "1", "frontend/e2e"]])

    def test_npm_independent_nested_stays_separate(self):
        touch(self.root, "frontend/package.json")
        touch(self.root, "frontend/e2e/package.json")
        self.assertEqual(lines(self.root),
                         [["frontend", "frontend", "0", ""],
                          ["frontend__e2e", "frontend/e2e", "0", ""]])

    def test_pnpm_workspace_yaml_collapses(self):
        touch(self.root, "frontend/package.json")
        touch(self.root, "frontend/pnpm-workspace.yaml", "packages: ['e2e']")
        touch(self.root, "frontend/e2e/package.json")
        self.assertEqual(lines(self.root),
                         [["frontend", "frontend", "1", "frontend/e2e"]])

    def test_families_never_cross_collapse(self):
        touch(self.root, "pom.xml", "<project/>")
        touch(self.root, "frontend/package.json")
        self.assertEqual(lines(self.root),
                         [["root", ".", "0", ""], ["frontend", "frontend", "0", ""]])

    def test_pruned_dirs_ignored(self):
        touch(self.root, "frontend/package.json")
        touch(self.root, "frontend/node_modules/dep/package.json")
        touch(self.root, "backend/target/generated/pom.xml", "<project/>")
        self.assertEqual(lines(self.root), [["frontend", "frontend", "0", ""]])

    def test_gradle_hexagonal_reactor_exposes_its_layers(self):
        """Collapsed != invisible: a code review that iterates only the standing
        module would open the aggregator root of a whole backend and call it
        covered. The folded layers must stay addressable in column 4."""
        touch(self.root, "settings.gradle", "include('domain','application')")
        touch(self.root, "build.gradle", "")
        for mod in ("domain", "application", "infrastructure"):
            touch(self.root, f"{mod}/build.gradle", "")
        out = lines(self.root)
        self.assertEqual([r[:3] for r in out], [["root", ".", "3"]])
        self.assertEqual(out[0][3].split(","),
                         ["application", "domain", "infrastructure"])

    def test_empty_repo_no_output(self):
        self.assertEqual(lines(self.root), [])

    # ---- the `.agents` prune and its single carve-out (T-00000197) ----------

    def test_agents_ui_src_is_discovered(self):
        """The kit's OWN dashboard source is first-party and must be scanned.

        Before this carve-out a HIGH advisory (nanoid < 3.3.18) sat in that
        lockfile while the dispatcher answered "no known ecosystem detected"
        for the entire repository.
        """
        touch(self.root, ".agents/ui-src/package.json")
        self.assertEqual(lines(self.root),
                         [[".agents__ui-src", ".agents/ui-src", "0", ""]])

    def test_rest_of_agents_stays_pruned(self):
        """The carve-out is one directory, not an opening of `.agents`.

        In a consumer project `.agents` holds the kit's VENDORED tooling, and
        auditing it would report the kit's manifests as the consumer's.
        """
        touch(self.root, ".agents/bin/package.json")
        touch(self.root, ".agents/security/package.json")
        self.assertEqual(lines(self.root), [])

    def test_agents_nested_deeper_stays_pruned_whole(self):
        """Only a ROOT `.agents` is descended into.

        A vendored copy sitting deeper is somebody else's tree, carve-out
        included — otherwise the exception widens every time a kit is nested.
        """
        touch(self.root, "vendor/kit/.agents/ui-src/package.json")
        self.assertEqual(lines(self.root), [])

    def test_carve_out_does_not_disturb_a_normal_module(self):
        touch(self.root, ".agents/ui-src/package.json")
        touch(self.root, "frontend/package.json")
        # Sorted here on purpose: what this case measures is that both modules
        # are present, not the order the dispatcher happens to emit them in.
        self.assertEqual(sorted(r[1] for r in lines(self.root)),
                         [".agents/ui-src", "frontend"])

    # ---- the python family (T-00000292) -------------------------------------

    def test_python_module_discovered(self):
        """A packaged Python project's manifest makes it a module.

        Before this family existed its dependencies were INVISIBLE (not
        under-scanned) — FAMILIES knew only npm/java/swift.
        """
        touch(self.root, "svc/requirements.txt", "flask==2.0.0\n")
        self.assertEqual(lines(self.root), [["svc", "svc", "0", ""]])

    def test_python_and_npm_same_dir_two_families_one_module(self):
        """A dir carrying both requirements.txt and package.json is ONE module.

        Two families stand in the same directory; the dispatcher emits a single
        line for that path (families are not a column, the path is the module).
        """
        touch(self.root, "app/package.json")
        touch(self.root, "app/requirements.txt", "flask==2.0.0\n")
        self.assertEqual(lines(self.root), [["app", "app", "0", ""]])

    def test_nested_python_dirs_stay_separate(self):
        """Python NEVER collapses to an ancestor (pins the owner-resolution
        branch of step 1): two nested requirement dirs are two modules, folded
        count 0 on both — unlike a maven reactor."""
        touch(self.root, "a/requirements.txt", "flask==2.0.0\n")
        touch(self.root, "a/b/requirements.txt", "django==4.0\n")
        self.assertEqual(lines(self.root),
                         [["a", "a", "0", ""],
                          ["a__b", "a/b", "0", ""]])

    def test_python_inside_agents_stays_pruned(self):
        """The `.agents` prune holds for python too — only `ui-src` is carved
        out, and it carries no python manifest here."""
        touch(self.root, ".agents/bin/requirements.txt", "requests==2.0\n")
        touch(self.root, ".agents/security/pyproject.toml", "[project]\n")
        self.assertEqual(lines(self.root), [])


PRUNED = "pruned (not in index)"
KEPT_IN_DOUBT = "kept (git did not answer)"


def said(path, verdict):
    """The one stderr line discover() writes per nested checkout it prunes or
    keeps in doubt (T-00001083) — the contract the SCA operator reads."""
    return f"module_discovery: nested checkout {path} {verdict}"


def bench_git(env, *argv, cwd=None):
    """git for BUILDING the throwaway trees: empty user config, identity and the
    file protocol passed as `-c`, any failure raises."""
    head = ["git"] + (["-C", cwd] if cwd else [])
    subprocess.run(head + ["-c", "protocol.file.allow=always", "-c", "user.name=t",
                           "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *argv],
                   check=True, capture_output=True, text=True, env=env, timeout=120)


@unittest.skipUnless(shutil.which("git"), "git not found: a REAL nested checkout cannot be built")
class NestedCheckoutTests(unittest.TestCase):
    """T-00001083 — discover() no longer walks into a nested checkout git does
    NOT track (linked worktree, unregistered clone) and still scans those it
    does (submodule, registered embedded repo). Doubt SCANS: one module too many
    is a duplicate finding, one module lost is a dependency never audited.

    Real trees (`git submodule add`, `git worktree add`, `git clone`) under a
    throwaway directory, never inside the repository; global and system git
    config point at an empty file, inherited `GIT_*` variables are dropped."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="t1083-")
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        empty = os.path.join(cls.base, "empty.gitconfig")
        Path(empty).write_text("", encoding="utf-8")
        # The module keeps GIT_CONFIG_GLOBAL/SYSTEM for its own git calls:
        # pointing them at an empty file isolates THOSE calls from the host too.
        patch = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": empty, "GIT_CONFIG_SYSTEM": empty})
        patch.start()
        cls.addClassCleanup(patch.stop)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        cls.env.update(GIT_CONFIG_GLOBAL=empty, GIT_CONFIG_SYSTEM=empty)

        src = os.path.join(cls.base, "src")
        cls._repo(src, "package.json", "{}")
        k = cls.k = os.path.join(cls.base, "k")
        cls._repo(k, "pyproject.toml", "[project]\n")
        bench_git(cls.env, "submodule", "add", "-q", src, "vendor/sub", cwd=k)    # gitfile -> .git/modules
        bench_git(cls.env, "clone", "-q", src, os.path.join(k, "vendor", "emb"))  # .git directory ...
        bench_git(cls.env, "add", "vendor/emb", cwd=k)                            # ... REGISTERED (gitlink)
        bench_git(cls.env, "commit", "-q", "-m", "sub+emb", cwd=k)
        bench_git(cls.env, "worktree", "add", "-q", "--detach", ".claude/worktrees/agent-w1", "HEAD", cwd=k)
        bench_git(cls.env, "clone", "-q", src, os.path.join(k, "nested", "clone"))  # NOT registered
        cls.worktree = os.path.join(k, ".claude", "worktrees", "agent-w1")
        cls.clone = os.path.join(k, "nested", "clone")
        cls.outside = os.path.join(cls.base, "outside")
        bench_git(cls.env, "clone", "-q", src, os.path.join(cls.outside, "app"))

    @classmethod
    def _repo(cls, path, manifest, text):
        bench_git(cls.env, "init", "-q", "-b", "main", path)
        Path(path, manifest).write_text(text, encoding="utf-8")
        bench_git(cls.env, "add", manifest, cwd=path)
        bench_git(cls.env, "commit", "-q", "-m", "x", cwd=path)

    def discover(self, root):
        err = io.StringIO()
        with redirect_stderr(err):
            mods = sorted(p.as_posix() for p in md.discover(root))
        return mods, err.getvalue().splitlines()

    def test_w1_linked_worktree_is_pruned_and_said(self):
        mods, err = self.discover(self.k)
        self.assertNotIn(".claude/worktrees/agent-w1", mods)
        self.assertIn(said(self.worktree, PRUNED), err)

    def test_w2_unregistered_clone_is_pruned_and_said(self):
        mods, err = self.discover(self.k)
        self.assertNotIn("nested/clone", mods)
        self.assertIn(said(self.clone, PRUNED), err)

    def test_w3_submodule_is_scanned(self):
        mods, err = self.discover(self.k)
        self.assertIn("vendor/sub", mods)
        self.assertEqual([], [l for l in err if os.path.join(self.k, "vendor") in l])

    def test_w4_registered_embedded_repo_is_scanned(self):
        mods, _err = self.discover(self.k)
        self.assertIn("vendor/emb", mods)

    def test_w5_root_is_scanned(self):
        mods, _err = self.discover(self.k)
        self.assertIn(".", mods)

    def test_w6_root_outside_any_repo_scans_its_clones(self):
        """Pilot default A1: outside any repository nothing is pruned."""
        p = subprocess.run(["git", "-C", self.outside, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, env=self.env, timeout=60)
        if p.returncode == 0:
            self.skipTest(f"{self.outside} lies inside a git work tree (TMPDIR under a repo): no outside root here")
        mods, err = self.discover(self.outside)
        self.assertIn("app", mods)
        self.assertEqual([], err)

    def test_w7_git_missing_keeps_the_worktree_and_says_so(self):
        with mock.patch.dict(os.environ, {"PATH": os.path.join(self.base, "no-git-here")}):
            mods, err = self.discover(self.k)
        self.assertIn(".claude/worktrees/agent-w1", mods)
        self.assertIn(said(self.worktree, KEPT_IN_DOUBT), err)

    def test_w8_linked_worktree_as_root_is_scanned(self):
        mods, _err = self.discover(self.worktree)
        self.assertIn(".", mods)

    def test_w9_index_query_timing_out_keeps_the_worktree_and_every_call_is_bounded(self):
        real = subprocess.run
        calls = []

        def fake(argv, *a, **kw):
            calls.append((list(argv), kw.get("timeout")))
            if "ls-files" in argv:
                raise subprocess.TimeoutExpired(argv, 60)
            return real(argv, *a, **kw)

        with mock.patch.object(md.subprocess, "run", fake):
            mods, err = self.discover(self.k)
        self.assertIn(".claude/worktrees/agent-w1", mods)
        self.assertIn(said(self.worktree, KEPT_IN_DOUBT), err)
        self.assertTrue(calls)
        self.assertEqual([], [c for c in calls if c[1] != 60 or "core.hooksPath=/dev/null" not in c[0]],
                         "every git call is bounded to 60 s and neutralises the queried repo's hooks")

    def test_w10_root_enclosed_by_a_repo_prunes_like_guard_m_and_says_so(self):
        """Pilot decision S-00003875: a non-repo root INSIDE a repository is
        pruned like the T-00001073 guard M — visible on stderr, never silent."""
        mods, err = self.discover(os.path.join(self.k, "nested"))
        self.assertNotIn("clone", mods)
        self.assertIn(said(self.clone, PRUNED), err)

    def test_w11_non_utf8_locale_and_raw_git_path_still_render_the_modules(self):
        """F2 (binôme 7+8) : sous une locale NON UTF-8 (`LC_ALL=C`, ni coercition ni mode UTF-8)
        et `core.quotePath=false`, `ls-files` rend le chemin « exposé » BRUT ; un décodage
        strict levait `UnicodeDecodeError` (traceback, rc 1) et `sca-scan.sh`, qui jette stderr
        et rc, perdait `web` sans signal. Le processus est un VRAI interpréteur sous cette locale."""
        env = {k: v for k, v in os.environ.items() if k not in ("LANG", "LC_CTYPE", "PYTHONIOENCODING")}
        env.update(LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0")
        enc = subprocess.run([sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
                             capture_output=True, text=True, env=env, timeout=60).stdout.strip()
        if "utf" in enc.lower().replace("-", ""):
            self.skipTest(f"l'interpréteur reste en {enc} sous LC_ALL=C : le décodage strict n'y lève pas")
        q, bare = os.path.join(self.base, "w11"), os.path.join(self.base, "w11-bare")
        self._repo(bare, "README", "x\n")  # checkout imbriqué SANS manifeste
        self._repo(q, "pyproject.toml", "[project]\n")
        Path(q, "web").mkdir()
        Path(q, "web", "package.json").write_text("{}", encoding="utf-8")
        bench_git(self.env, "clone", "-q", bare, os.path.join(q, "exposé"))  # `.git` RÉPERTOIRE : git est interrogé
        bench_git(self.env, "add", "exposé", cwd=q)                           # ... ENREGISTRÉ (gitlink)
        bench_git(self.env, "config", "core.quotePath", "false", cwd=q)
        p = subprocess.run([sys.executable, md.__file__, "--root", q], capture_output=True, env=env, timeout=120)
        self.assertEqual(0, p.returncode, p.stderr.decode("utf-8", "replace")[-600:])
        self.assertEqual([b"root", b"web"], [ligne.split(b"\t")[0] for ligne in p.stdout.splitlines()])

    def test_w11b_an_undecodable_git_byte_is_kept_never_raised(self):
        """Mutant `errors="strict"` (W11 ne le voit pas : « exposé » est de l'UTF-8 VALIDE). Un
        octet non UTF-8 — porté par un BLOB, brut par construction, qu'aucun système de fichiers
        ne refuse (un message de commit est converti par git) — est GARDÉ, jamais levé ni remplacé."""
        r = os.path.join(self.base, "w11b")
        self._repo(r, "README", "x\n")
        Path(r, "octet.bin").write_bytes(b"x\xff\n")
        bench_git(self.env, "add", "octet.bin", cwd=r)
        self.assertEqual("x\udcff\n", md._garde_git(["-C", r, "cat-file", "blob", ":octet.bin"]).stdout)

    def test_no_nested_checkout_means_no_git_call(self):
        """Hot path (SCA hook): git runs only on a dir carrying its own `.git`."""
        with tempfile.TemporaryDirectory() as root:
            touch(root, "app/package.json")
            with mock.patch.object(md.subprocess, "run", side_effect=AssertionError("git called")):
                mods, err = self.discover(root)
        self.assertEqual(["app"], mods)
        self.assertEqual([], err)


if __name__ == "__main__":
    unittest.main()
