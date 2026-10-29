"""Banc T-00000816 : la route docs-only voit les exécutables cachés là où les runners les trouvent.

Un dépôt git jetable par test ; le script est lancé en forme blob (`python3 -I -S -`, comme la route) ;
chaque mutant remplace un texte à ancre UNIQUE et doit rougir son témoin. Témoins W1-W24, mutants
M1-M18 (plan rév. 3, § Tests), W25/M19 (plan-critic it. 3, S-00004274, C1), W26/M20 (revue de sécurité
S-00004281 : tout dépôt imbriqué ignoré est parcouru), W27/W28 et M21-M24 (critic-opus S-00004298 : un dossier
que git ne peut ouvrir sort rc 2), épingles du docstring, des lignes de route et de
`RUNNER_TREES`, et un témoin DIFFÉRENTIEL :
ce que pytest et une copie de run-bash-tests.sh découvrent d'ignoré est inclus dans ce que le script liste.
"""
from __future__ import annotations

import configparser
import hashlib
import importlib.util
import json
import marshal
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "bin" / "docs_only_scope.py"
GITIGNORE = ".agents/state/local/\n.agents/state/events/\n__pycache__/\n.venv/\nnode_modules/\n.claude/worktrees/\n"
# Variables d'hôte qui changeraient la mesure (`.pyc` non écrit ou déplacé, options pytest, racine du
# projet) : jamais héritées par un sous-processus du banc.
_HOST_VARS = ("CLAUDE_PROJECT_DIR", "PYTEST_ADDOPTS", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")


class Repo:
    """Dépôt jetable : config git vide, aucun `GIT_*` ni variable d'hôte hérités."""

    def __init__(self, tmp: Path) -> None:
        self.tmp, self.root, self.state = tmp, tmp / "repo", tmp / "state.json"
        self.root.mkdir()
        gcfg = tmp / "gitconfig-empty"
        gcfg.write_text("", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in _HOST_VARS}
        self.env.update(GIT_CONFIG_GLOBAL=str(gcfg), GIT_CONFIG_NOSYSTEM="1", XDG_CONFIG_HOME=str(tmp / "xdg"))
        for name in ("AGENTS_EVENTS_DIR", "CADRE_STATE_DIR"):
            (tmp / name).mkdir()
            self.env[name] = str(tmp / name)
        for args in (("init", "-q", "."), ("config", "user.email", "b@x.invalid"), ("config", "user.name", "b"),
                     ("config", "commit.gpgsign", "false"), ("config", "core.excludesFile", os.devnull)):
            self.git(*args)
        self.write(".gitignore", GITIGNORE)
        for rel in ("docs/a.md", "README.md", "src/m.py", ".agents/bin/tool.py"):
            self.write(rel)
        self.write(".agents/state/local/binome/x")
        self.write(".agents/state/events/x")
        self.commit("init")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        cp = subprocess.run(["git", *args], cwd=cwd or self.root, env=self.env, capture_output=True,
                            encoding="utf-8", timeout=120, check=False)
        assert cp.returncode == 0, f"git {args}: {cp.stderr}"
        return cp.stdout

    def write(self, rel: str, text: str = "x = 1\n") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def commit(self, msg: str, *paths: str) -> None:
        if paths:
            self.git("add", "-f", "--", *paths)
            self.git("commit", "-q", "-m", msg, "--", *paths)
        else:
            self.git("add", "-A")
            self.git("commit", "-q", "-m", msg)

    def exclude(self, *rules: str) -> None:
        p = self.root / ".git" / "info" / "exclude"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8") if p.exists() else ""
        p.write_text(old + "".join(f"{r}\n" for r in rules), encoding="utf-8")

    def run(self, *args: str, src: bytes | None = None) -> tuple[int, list[str]]:
        cp = subprocess.run([sys.executable, "-I", "-S", "-", *args], input=SCRIPT.read_bytes() if src is None else src,
                            cwd=self.root, env=self.env, capture_output=True, timeout=300, check=False)
        return cp.returncode, [ln for ln in cp.stdout.decode("utf-8").splitlines() if ln]

    def snap(self, src: bytes | None = None) -> str:
        rc, lines = self.run("snapshot", "--state", str(self.state), src=src)
        assert rc == 0 and lines and lines[0].startswith("SNAPSHOT "), lines
        return lines[0].split()[1]

    def check(self, digest: str, *declared: str, src: bytes | None = None) -> tuple[int, list[str]]:
        tail = ["--declared", *declared] if declared else []
        return self.run("check", "--state", str(self.state), "--digest", digest, *tail, src=src)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


def _mut(old: str, new: str) -> bytes:
    """Le script où `old` (ancre UNIQUE) devient `new` ; un mutant qui ne compile pas rougirait à vide."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"anchor missing or repeated ({src.count(old)}): {old!r}"
    out = src.replace(old, new)
    compile(out, str(SCRIPT), "exec")
    return out.encode("utf-8")


def _scenario(repo: Repo, prep, window, declared=("docs/a.md",), src: bytes | None = None) -> tuple[int, list[str]]:
    prep(repo)
    digest = repo.snap(src=src)
    window(repo)
    return repo.check(digest, *declared, src=src)


def _nop(r: Repo) -> None:
    return None


UNSEEN = "DECLARED-UNSEEN\tdocs/a.md"
RC1, RC0 = "RESULT\trc=1", "RESULT\trc=0"


def _w(*pairs):
    def go(r: Repo) -> None:
        for rel, *text in pairs:
            r.write(rel, *text)
    return go


def _nested(rel: str):
    """Un dépôt git imbriqué IGNORÉ, présent avant le snapshot (règle dans `.git/info/exclude`)."""
    def prep(r: Repo) -> None:
        r.exclude(rel + "/")
        (r.root / rel).mkdir(parents=True, exist_ok=True)
        r.git("init", "-q", ".", cwd=r.root / rel)
        r.write(rel + "/old_test.py")
    return prep


_PYC_816 = "core-scripts/__pycache__/mod.cpython-312.pyc"


def _pycache_marker(r: Repo) -> None:
    """Un `.git` minimal (HEAD, objects/, refs/) dans `core-scripts/__pycache__/` : git y voit un dépôt imbriqué,
    le Python de la porte y importe quand même le `.pyc` de `core-scripts/mod.py` (S-00004281)."""
    r.write("core-scripts/__pycache__/.git/HEAD", "ref: refs/heads/main\n")
    for d in ("objects", "refs"):
        (r.root / "core-scripts/__pycache__/.git" / d).mkdir()


def _tracked_mod(r: Repo) -> None:
    r.write("core-scripts/mod.py")
    r.commit("tracked module", "core-scripts/mod.py")


def _evil_dir(r: Repo) -> str:
    d = r.tmp / "evil_dir"
    d.mkdir(exist_ok=True)
    (d / "test_evil.py").write_text("def test_e():\n    pass\n", encoding="utf-8")
    return str(d)


CASES = {  # nom -> (prep, fenêtre, déclarés, sortie EXACTE du check)
    "W1": (_nop, _w((".agents/state/local/test_evil.py",)), ("docs/a.md",),
           ["OUT\t.agents/state/local/test_evil.py", UNSEEN, RC1]),
    "W2": (_nop, _w((".agents/state/local/evil.test.sh", "x\n")), ("docs/a.md",),
           ["OUT\t.agents/state/local/evil.test.sh", UNSEEN, RC1]),
    "W3": (_nop, _w((".agents/bin/__pycache__/tool.cpython-314.pyc", "x\n"), (".agents/bin/__pycache__/evil.test.sh", "x\n")),
           ("docs/a.md",), ["OUT\t.agents/bin/__pycache__/evil.test.sh", "OUT\t.agents/bin/__pycache__/tool.cpython-314.pyc", UNSEEN, RC1]),
    "W4": (lambda r: r.exclude("/pytest.py"), _w(("pytest.py",)), ("docs/a.md",), [UNSEEN, "OUT\tpytest.py", RC1]),
    "W5": (_nop, _w((".agents/state/local/conftest.py",)), ("docs/a.md",), ["OUT\t.agents/state/local/conftest.py", UNSEEN, RC1]),
    "W6a": (_nested(".agents/nest"), _w((".agents/nest/test_new.py",)), ("docs/a.md",), ["OUT\t.agents/nest/test_new.py", UNSEEN, RC1]),
    "W6b": (_nested("docs/sub"), _w(("docs/sub/evil.sh", "x\n")), ("docs/a.md",), [UNSEEN, "OUT\tdocs/sub/evil.sh", RC1]),
    "W10": (_w((".agents/state/local/pre.py",)), lambda r: (r.root / ".agents/state/local/pre.py").unlink(), ("docs/a.md",),
            ["OUT\t.agents/state/local/pre.py", UNSEEN, RC1]),
    # S-00004281 : tout dépôt imbriqué ignoré est parcouru, hors zone et arbres compris (un worktree d'agent aussi).
    "W8a": (_nested(".claude/worktrees/x"), _w((".claude/worktrees/x/t2.py",)), ("docs/a.md",),
            ["OUT\t.claude/worktrees/x/t2.py", UNSEEN, RC1]),
    "W26": (lambda r: (_tracked_mod(r), _pycache_marker(r)), _w((_PYC_816, "x\n")), ("docs/a.md",), [f"OUT\t{_PYC_816}", UNSEEN, RC1]),
    "W26b": (_tracked_mod, lambda r: (_pycache_marker(r), r.write(_PYC_816, "x\n")), ("docs/a.md",),
             ["OUT\tcore-scripts/__pycache__\tvia=core-scripts/__pycache__/", f"OUT\t{_PYC_816}", UNSEEN, RC1]),
    "W18": (_nop, _w(("core-scripts/__pycache__/evil.test.sh", "x\n")), ("docs/a.md",), ["OUT\tcore-scripts/__pycache__/evil.test.sh", UNSEEN, RC1]),
    "W8b": (_nop, _w(("node_modules/p/n.py",), (".agents/ui/node_modules/p/n.sh", "x\n")), ("docs/a.md",), [UNSEEN, RC0]),
    "W16a": (_nop, _w((".venv/lib/python3.11/site-packages/x.py",), (".venv/lib/python3.11/site-packages/__pycache__/x.cpython-311.pyc", "x\n")),
             ("docs/a.md",), [UNSEEN, RC0]),
    "W16b": (_nop, _w((".venv/evil.test.sh", "x\n")), ("docs/a.md",), ["OUT\t.venv/evil.test.sh", UNSEEN, RC1]),
    "W11": (_nop, lambda r: (r.write("src/new.py"), r.commit("third-party", "src/new.py")), ("docs/a.md",),
            [UNSEEN, "COMMITTED-EXOGENOUS\tsrc/new.py", RC0]),
    "W14": (_w((".agents/bin/vis.py",)), lambda r: r.commit("third-party", ".agents/bin/vis.py"), ("docs/a.md",),
            ["COMMITTED-EXOGENOUS\t.agents/bin/vis.py", UNSEEN, RC0]),
    "W19": (_w((".agents/state/local/pre.py",)), lambda r: r.commit("third-party force-add", ".agents/state/local/pre.py"), ("docs/a.md",),
            ["COMMITTED-EXOGENOUS\t.agents/state/local/pre.py", "OUT\t.agents/state/local/pre.py", UNSEEN, RC1]),
    "W9": (_nop, _w((".agents/state/local/plan/x.py",)), ("docs/a.md",), ["OUT\t.agents/state/local/plan/x.py", UNSEEN, RC1]),
    # C1 (S-00004258) : pytest (`fnmatch`) et run-bash-tests.sh (`find -name`) apparient à casse EXACTE.
    "W21": (_nop, _w((".agents/state/local/Venv/test_evil.py",)), ("docs/a.md",), ["OUT\t.agents/state/local/Venv/test_evil.py", UNSEEN, RC1]),
    "W22": (_nop, _w((".agents/state/local/Node_Modules/test_evil.py",), (".agents/state/local/Node_Modules/evil.test.sh", "x\n")),
            ("docs/a.md",), ["OUT\t.agents/state/local/Node_Modules/evil.test.sh", "OUT\t.agents/state/local/Node_Modules/test_evil.py", UNSEEN, RC1]),
    # C4 : la marche d'un dépôt imbriqué filtre comme le listage (.py/.pyc sous venv/ sautés, .sh gardé, casse exacte).
    "W24": (_nested(".agents/nest"), _w((".agents/nest/venv/lib/x.py",), (".agents/nest/venv/evil.test.sh", "x\n"), (".agents/nest/sub/Venv/test_v.py",)),
            ("docs/a.md",), ["OUT\t.agents/nest/sub/Venv/test_v.py", "OUT\t.agents/nest/venv/evil.test.sh", UNSEEN, RC1]),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_case(repo: Repo, name: str) -> None:
    prep, window, declared, want = CASES[name]
    _rc, lines = _scenario(repo, prep, window, declared)
    assert lines == want, f"{name}: {lines}"


def test_w7_link_to_a_directory_under_a_tree_is_refused(repo: Repo) -> None:
    tgt = _evil_dir(repo)
    d = repo.snap()
    os.symlink(tgt, repo.root / ".agents/state/local/lnk")
    rc, lines = repo.check(d, "docs/a.md")
    assert rc == 2 and lines == ["ERROR\tsymbolic link to a directory under a runner tree: .agents/state/local/lnk", "RESULT\trc=2"], lines


def test_w7b_pre_existing_link_stops_the_snapshot(repo: Repo) -> None:
    os.symlink(_evil_dir(repo), repo.root / ".agents/state/local/lnk")
    rc, lines = repo.run("snapshot", "--state", str(repo.state))
    assert rc == 2 and lines[0].startswith("ERROR\tsymbolic link to a directory under a runner tree"), lines


def _venv_link(r: Repo, venv: str = ".agents/.venv") -> None:
    """Le `lib64 -> lib` qu'un venv crée sur Linux 64 bits, IGNORÉ, sous un arbre de pytest, avant le snapshot."""
    (r.root / venv / "lib").mkdir(parents=True)
    os.symlink("lib", r.root / venv / "lib64")


def test_w25_a_link_inside_a_venv_under_a_tree_does_not_stop_the_snapshot(repo: Repo) -> None:
    """C1 (S-00004274) : pytest élague `.venv/`/`venv/` avant de suivre un lien — le snapshot passe. Contrôle :
    un `Venv/` ignoré (casse EXACTE, pytest le parcourt) reste refusé."""
    _venv_link(repo)
    d = repo.snap()
    assert repo.check(d, "docs/a.md") == (0, [UNSEEN, RC0])
    _venv_link(repo, ".agents/state/local/Venv")
    rc, lines = repo.run("snapshot", "--state", str(repo.state))
    assert rc == 2 and lines[0] == "ERROR\tsymbolic link to a directory under a runner tree: .agents/state/local/Venv/lib64", lines


def _v4_state(repo: Repo) -> str:
    """L'état écrit par le VRAI script, réécrit en version 4 ; rend le digest du fichier réécrit."""
    repo.snap()
    st = json.loads(repo.state.read_text(encoding="utf-8"))
    st["version"] = 4
    raw = (json.dumps(st, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")
    repo.state.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_w13_a_v4_state_is_refused_by_name(repo: Repo) -> None:
    rc, lines = repo.check(_v4_state(repo), "docs/a.md")
    assert rc == 2 and lines[0].startswith("ERROR\tstate file version mismatch"), lines


def _import_tool(r: Repo) -> None:
    """Importe `.agents/bin/tool.py` : un `.pyc` écrit sous `__pycache__/` si le cache est froid, rien sinon."""
    subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, '.agents/bin'); import tool"],
                   cwd=r.root, env=r.env, check=True, timeout=120)


def test_w15_warm_bytecode_is_calm_and_cold_bytecode_is_named(repo: Repo) -> None:
    _import_tool(repo)  # chauffe le cache
    d = repo.snap()
    _import_tool(repo)  # rien à réécrire
    assert repo.check(d, "docs/a.md")[1] == [UNSEEN, RC0]
    pyc = next((repo.root / ".agents/bin/__pycache__").glob("tool.*.pyc"))
    pyc.unlink()  # cache FROID au snapshot suivant
    d = repo.snap()
    _import_tool(repo)  # un `.pyc` neuf dans la fenêtre
    rc, lines = repo.check(d, "docs/a.md")
    assert rc == 1 and any(ln.startswith("OUT\t.agents/bin/__pycache__/tool.") and ln.endswith(".pyc") for ln in lines), lines


_LINK_ARM = '        elif in_tree and set(p.split("/")).isdisjoint(VENV_DIRS) and os.path.islink(full) and os.path.isdir(full):\n'
MUTANTS = {  # nom -> (ancre, remplacement, témoins)
    "M1_zone_only": ('    *(f":(glob,icase)**/*{suffix}" for suffix in LISTED_SUFFIXES),\n',
                     '    *(f":(glob,icase){root}{suffix}" for suffix in LISTED_SUFFIXES for root in ("docs/**/*", "README*")),\n', ("W4", "W18")),
    "M2_no_pyc": ('LISTED_SUFFIXES = (*EXEC_SUFFIXES, ".pyc")', 'LISTED_SUFFIXES = (*EXEC_SUFFIXES,)', ("W3",)),
    "M3_no_nested_walk": ("in os.walk(full, onerror=_gone):", "in iter(()):", ("W6a", "W6b")),
    "M4_no_link_abort": (_LINK_ARM, "        elif False:\n", ("W7",)),
    "M13_no_tree_globs": ('    *(f":(glob,icase){tree}**" for tree in RUNNER_TREES),\n', "", ("W7",)),
    "M6_no_under_watched": ("_listed_paths(top, [q for q in _split_z(raw) if not under_watched(q, roots)])", "_listed_paths(top, _split_z(raw))", ("W9",)),
    "M20_nested_limited_to_trees": ('        if p.endswith("/"):\n            keep.append(p)\n',
                                    '        if p.endswith("/"):\n            if not (in_tree or low.startswith((ALLOW_TREE_PREFIX,'
                                    ' ALLOW_ROOT_BASENAME_PREFIX))):\n                continue\n            keep.append(p)\n', ("W26", "W8a")),
    "M20b_walk_limited_to_trees": ("            for dirpath, dirnames, filenames in os.walk(full, onerror=_gone):\n",
                                   "            for dirpath, dirnames, filenames in (os.walk(full, onerror=_gone) if in_tree or"
                                   " low.startswith((ALLOW_TREE_PREFIX, ALLOW_ROOT_BASENAME_PREFIX)) else ()):\n", ("W26", "W8a")),
    "M9_node_modules_kept": ('    f"{_EXCLUDE_EXACT}**/node_modules/**",\n', "", ("W8b",)),
    "M10_version_4": ("STATE_VERSION = 5\n", "STATE_VERSION = 4\n", ("W13",)),
    "M11_visible_untracked_listed": ('["ls-files", "-o", "-i", "--exclude-standard", "-z", "--", *RUNNER_EXEC_PATHSPECS]',
                                     '["ls-files", "-o", "--exclude-standard", "-z", "--", *RUNNER_EXEC_PATHSPECS]', ("W14",)),
    "M12_venv_sh_excluded": ('VENV_SKIPPED = (".venv", "venv"), (".py", ".pyc")', 'VENV_SKIPPED = (".venv", "venv"), (".py", ".pyc", ".sh")', ("W16b",)),
    "M14_venv_not_excluded": ('    *(f"{_EXCLUDE_EXACT}**/{d}/**/*{s}" for d in VENV_DIRS for s in VENV_SKIPPED),\n', "", ("W16a",)),
    "M16_exclusions_fold_case": ('_EXCLUDE_EXACT = ":(exclude,glob)"', '_EXCLUDE_EXACT = ":(exclude,glob,icase)"', ("W21", "W22")),
    "M17_walk_keeps_venv_py": (" and not (venv and n.endswith(VENV_SKIPPED))]", "]", ("W24",)),
    "M17b_walk_prunes_venv": ('if d not in (".git", "node_modules")]', 'if d not in (".git", "node_modules", *VENV_DIRS)]', ("W24",)),
    "M19_venv_links_refused": (_LINK_ARM, "        elif in_tree and os.path.islink(full) and os.path.isdir(full):\n", ("W25",)),
}
PARAMS = [(m, w) for m, (_o, _n, ws) in MUTANTS.items() for w in ws]


@pytest.mark.parametrize(("mut", "witness"), PARAMS, ids=[f"{m}-{w}" for m, w in PARAMS])
def test_mutant_turns_its_witness_red(repo: Repo, mut: str, witness: str) -> None:
    old, new, _ = MUTANTS[mut]
    src = _mut(old, new)
    if witness == "W7":
        d = repo.snap(src=src)
        os.symlink(_evil_dir(repo), repo.root / ".agents/state/local/lnk")
        rc, lines = repo.check(d, "docs/a.md", src=src)
        assert not (rc == 2 and lines[0].startswith("ERROR\tsymbolic link")), f"{mut} did not turn W7 red: {lines}"
        return
    if witness == "W13":
        rc, lines = repo.check(_v4_state(repo), "docs/a.md", src=src)
        assert not (rc == 2 and lines[0].startswith("ERROR\tstate file version mismatch")), f"{mut} did not turn W13 red: {lines}"
        return
    if witness == "W25":
        _venv_link(repo)
        rc, lines = repo.run("snapshot", "--state", str(repo.state), src=src)
        assert rc != 0, f"{mut} did not turn W25 red: {lines}"
        return
    prep, window, declared, want = CASES[witness]
    _rc, lines = _scenario(repo, prep, window, declared, src=src)
    assert lines != want, f"{mut} did not turn {witness} red: {lines}"


def _load(src: str | None = None):
    """Le script chargé comme module (le texte du kit, muté ou non) ; enregistré pour ses dataclasses."""
    spec = importlib.util.spec_from_file_location("dos_816", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    if src is None:
        spec.loader.exec_module(mod)
    else:
        exec(compile(src, str(SCRIPT), "exec"), mod.__dict__)
    return mod


# adopting-tree: kit-only — .agents/IS_THE_KIT est strip: ; le pytest.ini d'un adoptant est copié tel quel par sync ; porte_adoptant.py l'ignore à la racine
@pytest.mark.skipif(not (ROOT / ".agents" / "IS_THE_KIT").is_file(),
                    reason="kit-only : .agents/IS_THE_KIT ne voyage pas (strip:) ; le pytest.ini d'un adoptant est copié tel quel par sync, et porte_adoptant.py l'ignore à la racine")
def test_runner_trees_mirror_the_pytest_ini_testpaths() -> None:
    """`RUNNER_TREES` copie `testpaths` du KIT : une épingle d'INCLUSION (testpaths ⊆ arbres), jamais d'égalité."""
    dos = _load()
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ROOT / "pytest.ini", encoding="utf-8")
    paths = [p.strip() for p in cp["pytest"]["testpaths"].split() if p.strip()]
    assert paths, "pytest.ini sans testpaths : l'épingle serait vide"
    assert all(f"{p.rstrip('/')}/".startswith(dos.RUNNER_TREES) for p in paths), (paths, dos.RUNNER_TREES)
    assert set(dos.EXEC_SUFFIXES) <= set(dos.LISTED_SUFFIXES)


DOCSTRING_816 = (
    # S-00004298 : (a) et (b) disent la condition (git ouvre le dossier), le refus rc 2 et ce qui reste borné.
    "(a) FERMÉE par T-00000816 et le refus rc 2 de S-00004298", "— NOMMÉ OUT — là où git ouvre son dossier",
    "un dossier que git ne peut ouvrir (`chmod 311`/`111` : git le saute en rc 0, l'import le traverse) sort rc 2 en"
    " le nommant, hors des racines surveillées",
    "reste BORNÉ : ce refus lit l'avertissement « could not open directory » de git sous `LC_ALL=C`",
    "(b) FERMÉE de même", "son dossier rendu illisible à git sort rc 2 (borne de (a))",
    "dossier que git ne peut ouvrir (`chmod 311` ou `111`) hors des racines surveillées, git en échec",
    "(f) FERMÉE par T-00000816",
    "(h) `RUNNER_TREES` copie `testpaths` du KIT",
    "ou VISIBLE non suivi déjà présent au snapshot, n'est pas vu",
    "sous `.venv/` ou `venv/` (que pytest élague avant de suivre)",
    "reste exécuté au démarrage de l'interpréteur du venv : hors périmètre",
    "(f) FERMÉE par T-00000816 : un dépôt git imbriqué ignoré DÉJÀ présent, où qu'il soit",
    "y compris dans les worktrees d'agents (`.claude/worktrees/*`)",
    "(i) un `.pyc` régénéré dans la fenêtre",
    # T-00001191 : les lanceurs et les hooks du banc 1191 n'écrivent plus de `.pyc` — liste BORNÉE par le banc, jamais
    # un compte clos (L-00000187) ; résidus nommés.
    "un `python3` nu, un enfant lancé en `-E`/`-I`, `post-edit-check.sh` hors route",
    "`pyrun.sh`, `pyrun.ps1` et les hooks du banc `test_event_emitters_bytecode_1191.py` n'en écrivent plus, T-00001191",
    "un exécutable ignoré ILLISIBLE, n'importe où, arrête CHAQUE snapshot, rc 2 nommé `hidden:<chemin>`",
    "noms EXACTS, en minuscules, ceux que pytest (`fnmatch`) et run-bash-tests.sh (`find -name`) sautent",
    "sous Windows pytest replie la casse (`normcase`) : un `Venv/` peuplé y sort OUT, faux rouge fail-closed, non mesuré",
    "L'exclusion tient aux DÉFAUTS `norecursedirs` de pytest 9 (`venv`, `.*`) et à sa détection `pyvenv.cfg`",
    "(k) la mesure NOMME un exécutable caché",
)


def test_docstring_names_the_new_bounds() -> None:
    flat = " ".join((_load().__doc__ or "").split())
    missing = [frag for frag in DOCSTRING_816 if frag not in flat]
    assert not missing, f"docstring: T-00000816 bound missing: {missing}"
    # S-00004298 : la fermeture sans condition affirmée par T-816 est fausse (un dossier en 311 la contournait).
    for gone in ("(a) FERMÉE par T-00000816 : un exécutable", "(b) FERMÉE par T-00000816 : un exécutable"):
        assert gone not in flat, f"docstring: unconditional closure claim is back: {gone}"
    assert "4 émetteurs" not in flat, "docstring: a closed emitter count is back (T-00001191, L-00000187)"


ROUTE_DEFS = tuple(ROOT / h / "agents" / "orchestrator.md" for h in (".claude", ".gemini", ".kimi-code"))
_WORKTREE_FALSE_RED = ("or a .py, .sh or .pyc a concurrent session writes in an agent worktree (.claude/worktrees/*: every"
                       " ignored nested repository is walked, for those suffixes only — any other file written there"
                       " stays invisible, rc 0, so the documenter runs in the checkout the snapshot measures, never with"
                       " isolation: worktree) is printed OUT")


@pytest.mark.skipif(not all(p.is_file() for p in ROUTE_DEFS), reason="kit-only : les trois défs orchestrateur")
def test_route_lines_say_every_nested_repository_is_walked() -> None:
    """S-00004281 : aucune ligne de route ne dit plus un dépôt imbriqué « not walked » ; le faux rouge fail-closed
    d'un worktree d'agent y est nommé, sur les trois hôtes."""
    for p in ROUTE_DEFS:
        flat = " ".join(p.read_text(encoding="utf-8").split())
        assert _WORKTREE_FALSE_RED in flat and "is not walked" not in flat, p


_PYC_ROUTE_1191 = ("a documenter's pytest replay, a bare python3, a child run under -E/-I, or post-edit-check.sh on a .py edit,"
                   " off this route — pyrun.sh, pyrun.ps1 and the hooks listed in test_event_emitters_bytecode_1191.py no"
                   " longer write one, T-00001191")


@pytest.mark.skipif(not all(p.is_file() for p in ROUTE_DEFS), reason="kit-only : les trois défs orchestrateur")
def test_route_lines_say_the_launchers_write_no_pyc_1191() -> None:
    """T-00001191 : la ligne de route ne dit plus qu'un hook lancé par pyrun.sh régénère un `.pyc` ; la même phrase,
    sur les trois hôtes, nomme les résidus (pytest du documenter, python3 nu, enfant en -E/-I)."""
    for p in ROUTE_DEFS:
        flat = " ".join(p.read_text(encoding="utf-8").split())
        assert _PYC_ROUTE_1191 in flat and "a host hook launched by pyrun.sh (no -B)" not in flat, p
        assert "4 event emitters" not in flat and "those 4 emitters" not in flat, f"{p}: closed emitter count is back"


_UNOPENED_ROUTE = ("(T-00000816 closes the detection, not the execution, and only where git can open the directory: a"
                   " directory git cannot open — chmod 311 or 111, skipped by git with rc 0 yet imported through by"
                   " Python — outside the watched roots is rc 2, named, S-00004298; bounded: that refusal reads git's"
                   ' "could not open directory" warning under LC_ALL=C')


@pytest.mark.skipif(not all(p.is_file() for p in ROUTE_DEFS), reason="kit-only : les trois défs orchestrateur")
def test_route_lines_name_the_directory_git_cannot_open() -> None:
    """S-00004298 : la ligne de route ne dit plus « closes the detection » sans condition ; la même phrase, sur les
    trois hôtes, nomme le refus rc 2 et sa borne."""
    for p in ROUTE_DEFS:
        flat = " ".join(p.read_text(encoding="utf-8").split())
        assert _UNOPENED_ROUTE in flat and "(T-00000816 closes the detection, not the execution);" not in flat, p


def test_w20_an_unreadable_directory_inside_a_nested_repo_is_refused(repo: Repo) -> None:
    _nested(".agents/nest")(repo)
    locked = repo.root / ".agents/nest/locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        if not hasattr(os, "geteuid") or os.geteuid() == 0 or os.access(locked, os.R_OK):
            pytest.skip("ANNOUNCED SKIP: chmod 000 does not lock this user out (root or no POSIX modes) -- case not measured")
        rc, lines = repo.run("snapshot", "--state", str(repo.state))
        assert rc == 2 and lines[0] == "ERROR\tnested repository unreadable: .agents/nest/locked", lines
        rc, lines = repo.run("snapshot", "--state", str(repo.state), src=_mut("os.walk(full, onerror=_gone)", "os.walk(full)"))
        assert rc == 0, f"M15 (no onerror) did not turn W20 red: {lines}"
    finally:
        locked.chmod(0o755)


def _vanishing_walk(repo: Repo, monkeypatch, src: str | None = None) -> str:
    """W20b (C3) : un dossier d'un dépôt imbriqué DISPARU pendant la marche -> la cause dite, jamais « unreadable »."""
    _nested(".agents/nest")(repo)
    gone = repo.root / ".agents/nest/gone"
    gone.mkdir()
    (gone / "t.py").write_text("x = 1\n", encoding="utf-8")
    mod = _load(src)
    real, fired = os.scandir, []

    def vanishing(path=".", *a, **k):
        if not fired and os.fspath(path).replace(os.sep, "/").endswith("/.agents/nest/gone"):
            fired.append(path)
            shutil.rmtree(gone)
        return real(path, *a, **k)

    for k in [k for k in os.environ if k.startswith("GIT_") or k in _HOST_VARS]:
        monkeypatch.delenv(k)
    for k, v in repo.env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(repo.root)
    monkeypatch.setattr(os, "scandir", vanishing)
    try:
        mod.ignored_zone_exec(str(repo.root), ())
        msg = "no Abort"
    except mod.Abort as exc:
        msg = str(exc)
    finally:
        monkeypatch.setattr(os, "scandir", real)
    assert fired, "control: the directory never vanished (the race was not played)"
    return msg


def test_w20b_a_vanished_directory_in_a_nested_repo_is_named(repo: Repo, monkeypatch) -> None:
    assert _vanishing_walk(repo, monkeypatch) == "nested repository vanished during the walk: .agents/nest/gone"


def test_w20b_mutant_generic_cause_turns_red(repo: Repo, monkeypatch) -> None:
    src = _mut('raise Abort(f"nested repository {_gone_or_unreadable(exc)}: {rel}")', 'raise Abort(f"nested repository unreadable: {rel}")')
    assert _vanishing_walk(repo, monkeypatch, src.decode("utf-8")) != "nested repository vanished during the walk: .agents/nest/gone"


def test_w23_an_unreadable_hidden_executable_stops_the_snapshot(repo: Repo) -> None:
    """C8, épingle du comportement existant : un exécutable ignoré ILLISIBLE, n'importe où, arrête chaque
    snapshot, rc 2 nommé `hidden:<chemin>` (borne (i))."""
    locked = repo.write(".agents/state/local/locked.py")
    locked.chmod(0)
    try:
        if not hasattr(os, "geteuid") or os.geteuid() == 0 or os.access(locked, os.R_OK):
            pytest.skip("ANNOUNCED SKIP: chmod 000 does not lock this user out (root or no POSIX modes) -- case not measured")
        rc, lines = repo.run("snapshot", "--state", str(repo.state))
        assert rc == 2 and lines == [
            "ERROR\tgit control member or hidden executable unreadable or replaced while read: hidden:.agents/state/local/locked.py",
            "RESULT\trc=2"], lines
    finally:
        locked.chmod(0o644)


def _muts(*pairs: tuple[str, str]) -> bytes:
    """Le script où chaque `old` (ancre UNIQUE) devient son `new`, dans l'ordre ; recompilé comme `_mut`."""
    src = SCRIPT.read_text(encoding="utf-8")
    for old, new in pairs:
        assert src.count(old) == 1, f"anchor missing or repeated ({src.count(old)}): {old!r}"
        src = src.replace(old, new)
    compile(src, str(SCRIPT), "exec")
    return src.encode("utf-8")


def _forged_pyc(src: Path) -> Path:
    """Un `.pyc` FORGÉ que l'import accepte : en-tête horodaté (PEP 552) sur le `mtime` et la taille de la source."""
    st = src.stat()
    head = importlib.util.MAGIC_NUMBER + b"\0" * 4 + (int(st.st_mtime) & 0xFFFFFFFF).to_bytes(4, "little")
    pyc = Path(importlib.util.cache_from_source(str(src)))
    pyc.parent.mkdir(parents=True, exist_ok=True)
    code = marshal.dumps(compile('print("PAYLOAD")\n', str(src), "exec"))
    pyc.write_bytes(head + (st.st_size & 0xFFFFFFFF).to_bytes(4, "little") + code)
    return pyc


def _unopened(repo: Repo, name: str, src: bytes | None = None) -> tuple[int, list[str], str]:
    """S-00004298 (critic-opus T1) : un dossier en `chmod 311` créé dans la fenêtre — git ne peut pas l'ouvrir et
    se tait en rc 0, l'import Python le traverse. W27 (S3) : `core-scripts/__pycache__/` IGNORÉ et un `.pyc` forgé ;
    W28 (S4) : `.agents/bin/json/__init__.py` VISIBLE, que charge le `import json` de `tool.py`. Rend le check et ce
    qu'imprime l'import : le CONTRÔLE que la charge tourne vraiment (sans lui, le témoin pourrait être vide)."""
    if name == "W27":
        _tracked_mod(repo)
        cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, 'core-scripts'); import mod"]
    else:
        repo.write(".agents/bin/tool.py", "import json\n")
        repo.commit("tool imports json", ".agents/bin/tool.py")
        cmd = [sys.executable, ".agents/bin/tool.py"]
    digest = repo.snap(src=src)
    if name == "W27":
        locked = _forged_pyc(repo.root / "core-scripts/mod.py").parent
    else:
        locked = repo.write(".agents/bin/json/__init__.py", 'print("PAYLOAD")\n').parent
    locked.chmod(0o311)
    try:
        if not hasattr(os, "geteuid") or os.geteuid() == 0 or os.access(locked, os.R_OK):
            pytest.skip("ANNOUNCED SKIP: chmod 311 does not lock this user out (root or no POSIX modes) -- case not measured")
        rc, lines = repo.check(digest, "docs/a.md", src=src)
        ran = subprocess.run(cmd, cwd=repo.root, env=repo.env, capture_output=True, text=True, timeout=60, check=False)
        return rc, lines, ran.stdout
    finally:
        locked.chmod(0o755)


UNOPENED = {  # témoin -> sortie EXACTE du check (le premier appel git qui refuse est nommé)
    "W27": ["ERROR\tgit ls-files could not open directory: core-scripts/__pycache__", "RESULT\trc=2"],
    "W28": ["ERROR\tgit status could not open directory: .agents/bin/json", "RESULT\trc=2"],
}


@pytest.mark.parametrize("name", sorted(UNOPENED))
def test_w27_w28_a_directory_git_cannot_open_is_refused(repo: Repo, name: str) -> None:
    _rc, lines, ran = _unopened(repo, name)
    assert "PAYLOAD" in ran, f"{name} control: the payload did not run, the witness would be empty: {ran!r}"
    assert lines == UNOPENED[name], f"{name}: {lines}"


_WHOLE_LS = tuple((a, a.replace(", whole=roots", "")) for a in (
    "*TREE_CONTROL_GLOBS], top, whole=roots)", "*RUNNER_EXEC_PATHSPECS], top, whole=roots)"))
_WHOLE_ST = (('"--untracked-files=all"], top, whole=())', '"--untracked-files=all"], top)'),)
# Mutant -> (remplacements, témoin, sortie EXACTE sous le mutant). Sur un dossier VISIBLE, `status` et `ls-files`
# se couvrent : sans `whole=()`, W28 reste rc 2, refusé par `ls-files` (rouge sur la ligne, pas sur le rc) ; sans
# les deux, rc 0. Le `__pycache__/` IGNORÉ de W27 n'est ouvert que par `ls-files` (mesuré, git 2.55).
UNOPENED_MUTANTS = {
    "M21_no_whole_at_ls_files": (_WHOLE_LS, "W27", [UNSEEN, RC0]),
    "M22_no_whole_at_status": (_WHOLE_ST, "W28", ["ERROR\tgit ls-files could not open directory: .agents/bin/json", "RESULT\trc=2"]),
    "M23_no_whole_anywhere": (_WHOLE_LS + _WHOLE_ST, "W28", [UNSEEN, RC0]),
}


@pytest.mark.parametrize("mut", sorted(UNOPENED_MUTANTS))
def test_unopened_mutant_turns_its_witness_red(repo: Repo, mut: str) -> None:
    pairs, witness, want = UNOPENED_MUTANTS[mut]
    _rc, lines, _ran = _unopened(repo, witness, src=_muts(*pairs))
    assert lines != UNOPENED[witness] and lines == want, f"{mut} on {witness}: {lines}"


_FR = {"LANG": "fr_FR.UTF-8", "LC_ALL": "fr_FR.UTF-8", "LANGUAGE": "fr"}
_NO_LC_ALL = ('GIT_NO_REPLACE_OBJECTS="1", LC_ALL="C")', 'GIT_NO_REPLACE_OBJECTS="1")')


def test_w28_holds_under_a_translated_git(repo: Repo) -> None:
    """`LC_ALL=C` : l'hôte peut traduire l'avertissement de git (mesuré : `fr_FR.UTF-8`) ; le refus tient quand même."""
    repo.env.update(_FR)
    assert _unopened(repo, "W28")[1] == UNOPENED["W28"]


def test_m24_no_lc_all_turns_the_translated_witness_red(repo: Repo) -> None:
    """Sans `LC_ALL=C`, un git traduit écrit un avertissement que le refus ne lit pas : rc 0. Observable seulement
    là où git porte le catalogue français — sinon saut ANNONCÉ, jamais un vert à vide."""
    repo.env.update(_FR)
    _rc, lines, _ran = _unopened(repo, "W28", src=_mut(*_NO_LC_ALL))
    if lines == UNOPENED["W28"]:
        pytest.skip("ANNOUNCED SKIP: git prints its warning in English under fr_FR (no catalog) -- M24 not observable here")
    assert lines == [UNSEEN, RC0], lines


DIFF_PY = (".agents/state/local/test_a.py", ".agents/state/local/v1/Venv/test_b.py", ".agents/state/local/Node_Modules/test_c.py",
           ".agents/state/local/v2/venv/test_d.py", ".venv/test_e.py", "node_modules/test_f.py", "pkg/Venv/test_j.py", "build/test_k.py")
DIFF_SH = (".agents/state/local/a.test.sh", ".agents/state/local/Node_Modules/c.test.sh", "node_modules/f.test.sh",
           ".venv/e.test.sh", "core-scripts/__pycache__/g.test.sh", "pkg/Venv/j.test.sh")


#: T-00001188 : ce que la garde du conftest racine NOMME sous `testpaths = . .agents` (mesuré : égalité), et ce
#: qu'elle ne nomme pas parce que pytest l'élague (`.venv`, `node_modules`, `venv`).
GUARD_NAMED = {".agents/state/local/test_a.py", ".agents/state/local/v1/Venv/test_b.py",
               ".agents/state/local/Node_Modules/test_c.py", "pkg/Venv/test_j.py", "docs/sub/test_g.py",
               "docs/sub/old_test.py"}
GUARD_PRUNED = {".venv/test_e.py", "node_modules/test_f.py", ".agents/state/local/v2/venv/test_d.py"}
#: T-00001188 : les suites ignorées que la copie du runner REFUSE (rc 2) au lieu de les jouer.
RUNNER_REFUSED = {".agents/state/local/a.test.sh", ".agents/state/local/Node_Modules/c.test.sh", ".venv/e.test.sh",
                  "core-scripts/__pycache__/g.test.sh", "pkg/Venv/j.test.sh"}


def _runner_refuses(repo: Repo, env: dict, tracked: set, listed: set) -> None:
    """Copie de run-bash-tests.sh : depuis T-00001188 elle REFUSE (rc 2) les suites ignorées non suivies et n'en
    lance AUCUNE ; ce qu'elle nomme (lignes `  - ./…`) ⊆ ce que le script liste. L'ancienne inclusion
    `(joué ∖ suivi) ⊆ listé` serait VIDE par construction (joué = ∅) : remplacée, jamais affaiblie."""
    runner = repo.root / "core-scripts" / "run-bash-tests.sh"
    runner.write_bytes((ROOT / "core-scripts" / "run-bash-tests.sh").read_bytes())
    cp = subprocess.run(["bash", str(runner)], cwd=repo.root, env=dict(env, CADRE_GATE_JOBS="1"), capture_output=True,
                        encoding="utf-8", timeout=300, check=False)
    ran = {ln.split("=== RUN", 1)[1].strip().removeprefix("./") for ln in cp.stdout.splitlines() if ln.startswith("=== RUN")}
    refused = {ln[len("  - ./"):] for ln in cp.stderr.splitlines() if ln.startswith("  - ./")}
    assert cp.returncode == 2 and not ran, cp.stdout + cp.stderr
    assert RUNNER_REFUSED <= refused, f"run-bash-tests does not name: {sorted(RUNNER_REFUSED - refused)}"
    assert (refused - tracked) <= listed, f"run-bash-tests names what the script does not list: {sorted((refused - tracked) - listed)}"


def _guard_names(repo: Repo, env: dict, tracked: set, listed: set, conftest: str | None = None) -> None:
    """Jambe T-00001188 : conftest racine du kit COPIÉ (ou `conftest`, texte muté) + `pytest.ini`
    (`testpaths = . .agents`) ; `pytest` nu sort rc 4 et nomme les ignorés qu'il chargerait ; ce qu'il nomme ⊆ ce
    que le script liste."""
    if conftest is None:
        shutil.copy(ROOT / "conftest.py", repo.root / "conftest.py")
    else:
        (repo.root / "conftest.py").write_text(conftest, encoding="utf-8")
    (repo.root / "pytest.ini").write_text("[pytest]\ntestpaths =\n    .\n    .agents\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo.root, env=env,
                        capture_output=True, encoding="utf-8", timeout=300, check=False)
    out = cp.stdout + cp.stderr
    _, sep, tail = out.partition("que pytest chargerait : ")
    named = set(tail.partition(" ; remède")[0].split(", ")) if sep else set()
    assert cp.returncode == 4 and sep, out
    assert GUARD_NAMED <= named, f"the conftest guard does not name: {sorted(GUARD_NAMED - named)}"
    assert not (GUARD_PRUNED & named), f"the conftest guard names what pytest prunes: {sorted(GUARD_PRUNED & named)}"
    assert (named - tracked) <= listed, f"the conftest guard names what the script does not list: {sorted((named - tracked) - listed)}"


def _differential(repo: Repo, tmp_path: Path, src: bytes | None = None, conftest: str | None = None) -> None:
    """Sème des `.py`/`.sh` ignorés, prend le snapshot (avec `src` si donné), puis exige : (découvert ∖ suivi ∖
    visible) ⊆ (`ignored_exec` ∪ `watched`) pour pytest SANS conftest ; puis (T-00001188) que la copie de
    run-bash-tests.sh REFUSE les suites ignorées et que la garde du conftest racine REFUSE ce que pytest chargerait,
    chacune ne nommant que ce que le script liste."""
    repo.exclude("/pkg/", "/build/")
    for rel in DIFF_PY:
        repo.write(rel, "def test_x():\n    pass\n")
    for rel in DIFF_SH:
        repo.write(rel, "#!/usr/bin/env bash\nexit 0\n").chmod(0o755)
    _nested("docs/sub")(repo)
    repo.write("docs/sub/test_g.py", "def test_x():\n    pass\n")
    tracked = set(repo.git("ls-files").split("\n")) | set(repo.git("ls-files", "-o", "--exclude-standard").split("\n"))
    assert not ({"pkg/Venv/test_j.py", "pkg/Venv/j.test.sh"} & tracked), "control: pkg/ must be ignored"
    repo.snap(src=src)
    st = json.loads(repo.state.read_text(encoding="utf-8"))
    listed = set(st["ignored_exec"]) | set(st["watched"])
    ini = tmp_path / "empty.ini"
    ini.write_text("[pytest]\n", encoding="utf-8")
    env = dict(repo.env, PYTHONDONTWRITEBYTECODE="1")
    cp = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-c", str(ini),
                         "--rootdir", str(repo.root), ".", ".agents"], cwd=repo.root, env=env, capture_output=True,
                        encoding="utf-8", timeout=300, check=False)
    collected = {ln.split("::", 1)[0] for ln in cp.stdout.splitlines() if "::" in ln}
    assert "pkg/Venv/test_j.py" in collected and "docs/sub/test_g.py" in collected, cp.stdout + cp.stderr
    assert (collected - tracked) <= listed, f"pytest discovers what the script does not list: {sorted((collected - tracked) - listed)}"
    skips = []
    if shutil.which("bash"):
        _runner_refuses(repo, env, tracked, listed)
    else:
        skips.append("no bash -- the run-bash-tests.sh half of the differential is not measured")
    if os.name == "posix":
        _guard_names(repo, env, tracked, listed, conftest)
    else:
        skips.append("not posix -- the conftest guard leg (T-00001188) is not measured (case of `Venv`, posix fnmatch)")
    if skips:
        pytest.skip("ANNOUNCED SKIP: " + " ; ".join(skips))


def test_runners_discover_only_what_the_script_lists(repo: Repo, tmp_path: Path) -> None:
    """Objection (S-00004258) : témoin DIFFÉRENTIEL — inclusion, jamais égalité (le script est un sur-ensemble
    fail-closed, `build/` compris) ; un chemin VISIBLE relève de `git status`. Config pytest PAR DÉFAUT (borne (j))."""
    _differential(repo, tmp_path)


#: T-00001188 (plan : « M17 → jambe 816 », « M18 → jambe 816 ») : copie du conftest racine MUTÉE par remplacement
#: EXACT ; chacun doit rougir la jambe garde POUR SA raison — le message de son assertion.
GUARD_MUTANTS = {
    # Ancre suivie à la passe de correction F5 (N5 : `_elague` applique `norecursedirs` de l'ini par `_apparie`).
    "M17_no_name_pruning": ("    return any(_apparie(chemin, nom, motif) for motif in motifs)\n",
                            "    return False\n", "names what pytest prunes"),
    "M18_root_only": ("    for motif in motifs:\n", "    for motif in ():\n", "does not name"),
}


@pytest.mark.parametrize("mut", list(GUARD_MUTANTS))
def test_guard_mutant_turns_the_differential_red(repo: Repo, tmp_path: Path, mut: str) -> None:
    old, new, why = GUARD_MUTANTS[mut]
    src = (ROOT / "conftest.py").read_text(encoding="utf-8")
    assert src.count(old) == 1, f"anchor missing or repeated ({src.count(old)}): {old!r}"
    with pytest.raises(AssertionError, match=why):
        _differential(repo, tmp_path, conftest=src.replace(old, new))
