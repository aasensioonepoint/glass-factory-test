"""Banc T-00001188 : la porte REFUSE un `.py`/`.sh` git-ignoré non suivi que pytest ou run-bash-tests.sh chargerait.

Un dépôt git jetable HORS de l'arbre par test (`.gitignore`, `pytest.ini` `testpaths = .agents pkgs` +
`python_files = test_*.py`) ; le conftest racine et run-bash-tests.sh du kit y sont COPIÉS — les deux seuls
chemins du kit que ce banc lit. Un plant écrit un FICHIER canari quand il est importé ou exécuté (la collecte
capture stdout) : 0 canari = rien de planté n'a tourné. Prémisse : pytest==9.1.1 épinglé à la CI
(`.github/workflows/ci.yml:282`) — la règle de la garde est la portée réelle de CETTE version.

Plan : docs/tasks/T-00001188-plan.md (rév. 7) § Tests. Témoins rouges sans la garde : P1-P12, P13 (dossier
ignoré illisible sous un départ de pytest nu : fail-closed), D1 (différentiel à deux sens), B1-B6 (runner) ;
verts avant et après : V1-V6, V9-V11. Ajoutés par l'exec-critic (GO_AVEC_RESERVES) : P14 (testpath sous un
dossier ignoré élagué), P15 ((e2), fichier `conftest.py` ignoré), P16 et B7 (racine d'un worktree LIÉ, `.git`
fichier), V12 (illisible HORS des départs : vert). Revue de clôture, décision pilote `decision/T-00001188/04`
(un lien ignoré vers un dossier est SUIVI, une fois par (dev, ino), et jugé par son seul contenu) : P5, P11d et
le lien de D1 réécrits, P17 (lien cassé sous un départ : refus), V13 (lien vers des données : vert), V14
(boucles de liens : terminent, vert). Revue sécu du delta 117dcf47 : P18 (marche BORNÉE, plafond réduit par
injection), P19 (TOCTOU : un lien qui disparaît ne fait sauter aucune entrée voisine) et V15 (`vus` partagé : un
sous-arbre n'est lu qu'une fois), P20 (sans inode stable, `st_ino == 0` : aucune déduplication) — P19, P20 et V15
jouent la garde EN PROCESSUS (`os.stat`/`os.scandir` instrumentés, restaurés). Mutants M1-M34 : copie du conftest
ou du runner MUTÉE par
remplacement exact (1 occurrence exigée), chacun doit rougir ses témoins. P11a et D1 jouent sous `testpaths = .agents .agents/evals pkgs` (la
configuration mesurée) : pytest ne charge l'AMORCE d'un `test*/conftest.py` élagué que sous une ANCRE
(_pytest/runner.py:388-405 : un conftest de collecte n'est chargé que pour un dossier COLLECTÉ).
Skips ANNONCÉS hors posix, cas par cas : liens (P5, P11d, P17, V13, V14, liens de D1), faux git `#!/bin/sh` (P8, P10),
`/bin/bash` (B1-B9 et la jambe runner de V1, V5, V6).
Passe de correction F5 (avis sécu A1-A3 de S-01M4QK54G557S6WDHATX61RQED, N5 de la revue de clôture) : P21 et B8
(`.git` présent, git absent du PATH ⇒ REFUS, remplacent V10 et V10r qui disaient « INACTIVE »), V16 (`.git` retiré :
seul motif d'inactivité restant), P22 (`Conftest.py`, toute casse), B9 (noms quotés par `printf %q`), V17 et P23
(`norecursedirs` de pytest.ini REMPLACE les défauts) ; mutants M35-M39r.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFTEST = (ROOT / "conftest.py").read_text(encoding="utf-8")
RUNNER = (ROOT / "core-scripts" / "run-bash-tests.sh").read_text(encoding="utf-8")
POSIX = os.name == "posix"
L = ".agents/state/local/"
GITIGNORE = (".agents/state/local/\n/.worktrees/\n/outside/\n/env/\n.direnv/\n__pycache__/\nevil/\n*.bak\n*.egg\n"
             ".deep/\n.ipynb_checkpoints\npkgs/env/\npkgs/cenv/\npkgs/gen/\npkgs/.tox/\npkgs/build/\npkgs/test_venv/\n")
INI = "[pytest]\ntestpaths =\n    .agents\n    pkgs\npython_files = test_*.py\n"
INI3 = "[pytest]\ntestpaths =\n    .agents\n    .agents/evals\n    pkgs\npython_files = test_*.py\n"
REFUS = "que pytest chargerait : "
TOOLS = ("bash", "find", "sort", "sed", "dirname", "tr", "cat", "env", "mktemp", "grep", "date", "uname", "sleep",
         "timeout", "gtimeout", "head", "tail", "wc", "awk", "mkdir", "rm", "cp", "ls", "basename", "xargs", "pwd",
         "tee", "cut", "printf", "kill", "ps", "chmod", "touch", "id")


def _skip_unless_posix(why: str) -> None:
    if not POSIX:
        pytest.skip(f"ANNOUNCED SKIP: {why} -- not posix ({os.name}), case not measured")


def _mutate(text: str, pairs) -> str:
    """`text` où chaque ancre (UNIQUE, sinon le mutant rougirait à vide) est remplacée."""
    for old, new in pairs:
        assert text.count(old) == 1, f"anchor missing or repeated ({text.count(old)}): {old!r}"
        text = text.replace(old, new)
    return text


class Run:
    def __init__(self, rc: int, canaries: list[str], out: str, ran: list[str] | None = None) -> None:
        self.rc, self.canaries, self.out, self.ran = rc, canaries, out, ran or []

    @property
    def named(self) -> set[str]:
        _, sep, tail = self.out.partition(REFUS)
        return set(tail.partition(" ; remède")[0].split(", ")) if sep else set()

    @property
    def refused(self) -> set[str]:
        """Les suites nommées SOUS l'en-tête du refus du runner (jamais le listing de découverte)."""
        tail = self.out.partition("T-00001188 : porte REFUSÉE — suite(s) non suivie(s)")[2]
        return {ln[len("  - ./"):] for ln in tail.splitlines() if ln.startswith("  - ./")}

    def __repr__(self) -> str:
        return f"rc={self.rc} canaries={self.canaries} ran={self.ran}\n{self.out[-3000:]}"


class Tree:
    """Dépôt jetable : config git vide, aucun `GIT_*` ni `PYTEST_*` hérité ; conftest et runner COPIÉS."""

    def __init__(self, tmp: Path, conftest: str = CONFTEST, runner: str = RUNNER, ini: str = INI,
                 git: bool = True) -> None:
        self.tmp, self.root, self.ran = tmp, tmp / "rep", tmp / "RAN"
        self.root.mkdir()
        gcfg = tmp / "gitconfig-empty"
        gcfg.write_text("", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("GIT_", "PYTEST_")) and k not in ("CLAUDE_PROJECT_DIR", "PYTHONPYCACHEPREFIX")}
        self.env.update(GIT_CONFIG_GLOBAL=str(gcfg), GIT_CONFIG_NOSYSTEM="1", XDG_CONFIG_HOME=str(tmp / "xdg"),
                        PYTHONDONTWRITEBYTECODE="1", RAN_1188=str(self.ran))
        self.write(".gitignore", GITIGNORE)
        self.write("pytest.ini", ini)
        self.write(".agents/evals/test_ok.py", "def test_ok():\n    pass\n")
        self.write("pkgs/test_pk.py", "def test_pk():\n    pass\n")
        self.write("conftest.py", conftest)
        self.write("core-scripts/run-bash-tests.sh", runner)
        self.suite("ok.test.sh", "ok")
        if git:
            for args in (("init", "-q", "."), ("config", "user.email", "b@x.invalid"), ("config", "user.name", "b"),
                         ("config", "commit.gpgsign", "false"), ("config", "core.excludesFile", os.devnull)):
                self.git(*args)
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "init")
        (self.root / L).mkdir(parents=True, exist_ok=True)

    def git(self, *args: str, cwd: Path | None = None, stdin: str = "") -> str:
        cp = subprocess.run(["git", *args], cwd=cwd or self.root, env=self.env, input=stdin, capture_output=True,
                            encoding="utf-8", timeout=120, check=False)
        assert cp.returncode == 0, f"git {args}: {cp.stderr}"
        return cp.stdout.strip()

    def write(self, rel: str, text: str = "", base: Path | None = None) -> Path:
        p = (base or self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def canary(self, tag: str) -> str:
        return "open(%r, 'w').write('x')\n" % str(self.root / ("CANARY_" + tag))

    def plant(self, rel: str, tag: str, test: bool = True, base: Path | None = None) -> None:
        self.write(rel, self.canary(tag) + ("def test_x():\n    pass\n" if test else ""), base=base)

    def suite(self, rel: str, tag: str, base: Path | None = None) -> None:
        self.write(rel, f'#!/usr/bin/env bash\necho {tag} >> "$RAN_1188"\nexit 0\n', base=base).chmod(0o755)

    def ignore(self, *rules: str) -> None:
        with (self.root / ".gitignore").open("a", encoding="utf-8") as fh:
            fh.write("".join(f"{r}\n" for r in rules))

    def worktree(self, rel: str) -> Path:
        """Worktree ENREGISTRÉ sur une branche VIDE de tests suivis du dépôt (un commit orphelin)."""
        commit = self.git("commit-tree", self.git("mktree"), "-m", "orphan")
        path = self.root / rel
        self.git("worktree", "add", "-q", "--detach", str(path), commit)
        self.plant("conftest.py", "WTC", test=False, base=path)
        self.plant("test_wt.py", "WTT", base=path)
        self.git("add", "conftest.py", "test_wt.py", cwd=path)
        self.git("commit", "-q", "-m", "evil", cwd=path)
        return path

    def linked_root(self) -> Path:
        """La racine d'un worktree LIÉ de ce dépôt, HORS de lui : `.git` y est un FICHIER — là où tournent les agents
        dev. Conftest, runner et `.gitignore` y sont ceux du commit."""
        path = self.tmp / "wtroot"
        self.git("worktree", "add", "-q", "--detach", str(path), "HEAD")
        assert (path / ".git").is_file(), "control: a linked worktree carries a .git FILE"
        return path

    def fakegit(self, body: str) -> str:
        fb = self.tmp / "fakebin"
        fb.mkdir(exist_ok=True)
        g = fb / "git"
        g.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        g.chmod(0o755)
        return str(fb) + os.pathsep + os.environ.get("PATH", "")

    def pytest(self, *args: str, env: dict | None = None, mode: str | None = None, cwd: Path | None = None) -> Run:
        for c in self.root.glob("CANARY_*"):
            c.unlink()
        e = dict(self.env, **(env or {}))
        extra = [f"--import-mode={mode}"] if mode else []
        cp = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra, *args],
                            cwd=cwd or self.root, env=e, capture_output=True, encoding="utf-8", errors="replace",
                            timeout=180, check=False)
        return Run(cp.returncode, sorted(c.name for c in self.root.glob("CANARY_*")), cp.stdout + cp.stderr)

    def runner(self, *args: str, env: dict | None = None, cwd: Path | None = None) -> Run:
        if self.ran.exists():
            self.ran.unlink()
        e = dict(self.env, CADRE_GATE_JOBS="1", **(env or {}))
        cp = subprocess.run(["/bin/bash", "core-scripts/run-bash-tests.sh", *args], cwd=cwd or self.root, env=e,
                            capture_output=True, encoding="utf-8", errors="replace", timeout=300, check=False)
        ran = self.ran.read_text(encoding="utf-8").split() if self.ran.exists() else []
        return Run(cp.returncode, [], cp.stdout + cp.stderr, ran)


def _plant_l(t: Tree) -> None:
    t.plant(L + "conftest.py", "CONF", test=False)
    t.plant(L + "test_evil.py", "PY")
    t.plant(L + "__init__.py", "INIT", test=False)


def _refused(r: Run, *rels: str) -> bool:
    """Le refus attendu : rc 4, chaque chemin nommé, aucun canari."""
    return r.rc == 4 and not r.canaries and set(rels) <= r.named


# --- Témoins pytest : chaque scénario rend (tient ?, détail) --------------------------------------------------
def p1(t: Tree, mode: str | None = None):
    _plant_l(t)
    r = t.pytest(mode=mode)
    return _refused(r, L + "conftest.py", L + "test_evil.py"), r


def p2(t: Tree, mode: str | None = None):
    _plant_l(t)
    r = t.pytest(L, mode=mode)
    return _refused(r, L + "conftest.py", L + "test_evil.py"), r


def p3(t: Tree, mode: str | None = None):
    _plant_l(t)
    r = t.pytest(L + "test_evil.py", mode=mode)
    return _refused(r, L + "test_evil.py"), r


def p4(t: Tree):
    _plant_l(t)
    t.git("init", "-q", ".", cwd=t.root / L)
    r = t.pytest()
    return _refused(r, L + "test_evil.py"), r


def p5(t: Tree):
    """Décision `decision/T-00001188/04` : un lien ignoré vers un dossier hors dépôt est SUIVI ; le test qu'il porte
    est refusé sous le chemin du lien, celui que pytest charge — jamais le lien lui-même."""
    _skip_unless_posix("symbolic link")
    out = t.tmp / "outside_target"
    t.plant("test_x.py", "LNK", base=out)
    os.symlink(out, t.root / L / "lnk")
    r = t.pytest()
    return (_refused(r, L + "lnk/test_x.py") and L + "lnk" not in r.named), r


def p6(t: Tree):
    t.write(L + "t/test_t.py", "def test_t():\n    pass\n")
    t.git("add", "-f", L + "t/test_t.py")
    t.git("commit", "-q", "-m", "tracked under an ignored directory")
    t.plant(L + "t/__init__.py", "INIT6", test=False)
    r = t.pytest()
    return _refused(r, L + "t/__init__.py"), r


def p7(t: Tree):
    _plant_l(t)
    host = t.tmp / "host"
    host.mkdir()
    t.git("init", "-q", ".", cwd=host)
    r = t.pytest(env={"GIT_DIR": str(host / ".git"), "GIT_WORK_TREE": str(host)})
    return _refused(r, L + "test_evil.py"), r


def p8(t: Tree):
    _skip_unless_posix("fake git #!/bin/sh")
    _plant_l(t)
    path = t.fakegit("echo 'fatal: detected dubious ownership in repository' >&2\nexit 128\n")
    r = t.pytest(env={"PATH": path})
    return (r.rc == 4 and not r.canaries and "rc=128" in r.out and "dubious ownership" in r.out), r


def p9(t: Tree):
    t.worktree(L + "wt2")
    r = t.pytest()
    return _refused(r, L + "wt2/conftest.py", L + "wt2/test_wt.py"), r


def p10(t: Tree):
    _skip_unless_posix("fake git #!/bin/sh")
    _plant_l(t)
    path = t.fakegit("exec sleep 60\n")
    t0 = time.monotonic()
    r = t.pytest(env={"PATH": path})
    return (r.rc == 4 and not r.canaries and "a dépassé" in r.out and time.monotonic() - t0 < 40), r


def p11a(t: Tree):
    t.write("pytest.ini", INI3)
    t.write(".agents/evals/test_cache.bak/pyvenv.cfg", "home = /x\n")
    t.plant(".agents/evals/test_cache.bak/conftest.py", "P11A", test=False)
    r = t.pytest()
    return _refused(r, ".agents/evals/test_cache.bak/conftest.py"), r


def p11b(t: Tree):
    t.write(".agents/testvenv.bak/pyvenv.cfg", "home = /x\n")
    t.plant(".agents/testvenv.bak/conftest.py", "P11B", test=False)
    r = t.pytest()
    return _refused(r, ".agents/testvenv.bak/conftest.py"), r


def p11c(t: Tree):
    t.write(L + "test_v/pyvenv.cfg", "home = /x\n")
    t.plant(L + "test_v/conftest.py", "P11C", test=False)
    r = t.pytest(L)
    return _refused(r, L + "test_v/conftest.py"), r


def p11d(t: Tree):
    """Lien ignoré ÉLAGUÉ (`*.egg`) : ni pytest ni la garde ne le suivent (décision /04 ne vaut que pour un lien
    NON élagué) ; seule l'AMORCE charge son `conftest.py`, refusé — son `test_y.py` n'est pas nommé."""
    _skip_unless_posix("symbolic link")
    out = t.tmp / "outside_lnk"
    t.plant("conftest.py", "P11D", test=False, base=out)
    t.plant("test_y.py", "P11DY", base=out)
    os.symlink(out, t.root / "pkgs" / "test_lnk.egg")
    r = t.pytest()
    return (_refused(r, "pkgs/test_lnk.egg/conftest.py") and "pkgs/test_lnk.egg/test_y.py" not in r.named), r


def p11e(t: Tree):
    t.write("pytest.ini", INI.replace("    pkgs\n", "    pkgs\n    .deep/t\n"))
    (t.root / ".deep" / "t").mkdir(parents=True)
    t.plant(".deep/conftest.py", "P11E", test=False)
    r = t.pytest()
    return _refused(r, ".deep/conftest.py"), r


def p11f(t: Tree):
    """C3 (plan-critic it.7) : (e1) à D = RACINE, l'ancre de `pytest .` et de la porte adoptant (ini SANS
    `testpaths`, forme de porte_adoptant.py)."""
    t.write("pytest.ini", "[pytest]\npython_files = test_*.py\n")
    t.write("test_r.bak/pyvenv.cfg", "home = /x\n")
    t.plant("test_r.bak/conftest.py", "P11F", test=False)
    r = t.pytest()
    return _refused(r, "test_r.bak/conftest.py"), r


def p12(t: Tree):
    with (t.root / ".git" / "info" / "exclude").open("a", encoding="utf-8") as fh:
        fh.write("/.agents/evals/__init__.py\n")
    t.plant(".agents/evals/__init__.py", "P12", test=False)
    r = t.pytest()
    return _refused(r, ".agents/evals/__init__.py"), r


def p13(t: Tree):
    """Dev (au-delà du plan, fail-closed) : un dossier ignoré illisible de la portée arrête la garde, nommé."""
    locked = t.root / L / "locked"
    t.plant(L + "locked/test_x.py", "P13")
    locked.chmod(0o000)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("ANNOUNCED SKIP: chmod 000 does not lock this user out (root or no POSIX modes) -- P13 not measured")
        r = t.pytest()
    finally:
        locked.chmod(0o755)
    return (r.rc == 4 and not r.canaries and "illisible" in r.out and L + "locked" in r.out), r


def p14(t: Tree):
    """exec-critic XM10 : un testpath SOUS un dossier ignoré ÉLAGUÉ depuis la racine (`.deep/`) n'est atteint que
    par son propre départ ; son contenu est refusé."""
    t.write("pytest.ini", INI.replace("    pkgs\n", "    pkgs\n    .deep/t\n"))
    t.plant(".deep/t/test_deep.py", "P14")
    r = t.pytest()
    return _refused(r, ".deep/t/test_deep.py"), r


def p15(t: Tree):
    """exec-critic XM22 : (e2) quand c'est le FICHIER `conftest.py` de l'ancêtre qui est ignoré (pas son dossier),
    l'ancêtre étant élagué depuis la racine (`.dd/`)."""
    t.write("pytest.ini", INI.replace("    pkgs\n", "    pkgs\n    .dd/t\n"))
    t.ignore(".dd/conftest.py")
    (t.root / ".dd" / "t").mkdir(parents=True)
    t.plant(".dd/conftest.py", "P15", test=False)
    r = t.pytest()
    return _refused(r, ".dd/conftest.py"), r


def p16(t: Tree):
    """exec-critic XM18 : la garde s'ACTIVE à la racine d'un worktree LIÉ (`.git` fichier)."""
    wt = t.linked_root()
    t.plant(L + "conftest.py", "WTRC", test=False, base=wt)
    t.plant(L + "test_evil.py", "WTRP", base=wt)
    r = t.pytest(cwd=wt)
    return (_refused(r, L + "conftest.py", L + "test_evil.py") and "garde fichiers ignorés INACTIVE" not in r.out), r


def v12(t: Tree):
    """exec-critic, constat 2 : un dossier ignoré illisible HORS des départs de pytest nu (sous la racine, hors
    `testpaths`) n'est PAS refusé — pytest nu n'y descend pas."""
    locked = t.root / "outside" / "locked"
    t.plant("outside/locked/test_x.py", "V12")
    locked.chmod(0o000)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("ANNOUNCED SKIP: chmod 000 does not lock this user out (root or no POSIX modes) -- V12 not measured")
        r = t.pytest()
    finally:
        locked.chmod(0o755)
    return (r.rc == 0 and not r.canaries and "illisible" not in r.out), r


def p17(t: Tree):
    """Un lien ignoré CASSÉ sous un départ de pytest nu : refus nommé, fail-closed — pytest l'ignorerait
    (`_pytest/pathlib.py` scandir), faux rouge voulu (revue de clôture, T1)."""
    _skip_unless_posix("symbolic link")
    os.symlink(str(t.tmp / "nowhere"), t.root / L / "dangling")
    r = t.pytest()
    return (r.rc == 4 and "lien git-ignoré cassé" in r.out and L + "dangling" in r.out), r


def v13(t: Tree):
    """Décision `decision/T-00001188/04` : un lien ignoré vers un dossier de DONNÉES (un `.csv` seul) est suivi et
    n'est PAS refusé — le faux rouge data/ML ou Bazel que la règle « refusé, jamais suivi » produisait."""
    _skip_unless_posix("symbolic link")
    data = t.tmp / "outside_data"
    t.write("data.csv", "a,b\n1,2\n", base=data)
    os.symlink(data, t.root / L / "datalnk")
    r = t.pytest()
    return (r.rc == 0 and "T-00001188" not in r.out), r


def v14(t: Tree):
    """Boucles de liens ignorés (un lien vers son propre dossier, deux dossiers qui se désignent) : la garde
    termine, une fois par (dev, ino), sans refus."""
    _skip_unless_posix("symbolic link")
    for d in ("loop", "x", "y"):
        t.write(L + d + "/data.csv", "a\n")
    os.symlink(".", t.root / L / "loop" / "self")
    os.symlink("../y", t.root / L / "x" / "to_y")
    os.symlink("../x", t.root / L / "y" / "to_x")
    r = t.pytest()
    return (r.rc == 0 and "T-00001188" not in r.out), r


def p18(t: Tree):
    """Revue sécu (medium 2) : la marche est BORNÉE — plafond réduit à 5 par injection (`INJECT`), un dossier
    ignoré de 11 entrées sous un départ : refus fail-closed qui nomme le dossier et le remède."""
    for i in range(10):
        t.write(f"{L}big/d{i}.csv", "a\n")
    t.plant(L + "big/test_big.py", "P18")
    r = t.pytest()
    return (r.rc == 4 and not r.canaries and "plus de 5 entrées git-ignorées" in r.out and L + "big" in r.out), r


class _Ordonne:
    """Un `os.scandir` dont les LIENS sortent en premier : rend déterministe le témoin d'une entrée sautée."""

    def __init__(self, reel, chemin) -> None:
        with reel(chemin) as it:
            self.entrees = sorted(it, key=lambda e: (not e.is_symlink(), e.name))

    def __enter__(self):
        return iter(self.entrees)

    def __exit__(self, *exc) -> bool:
        return False

    def __iter__(self):
        return iter(self.entrees)

    def close(self) -> None:
        return None


def _in_process(t: Tree, fail_stat_after_first: str | None = None, links_first: bool = False,
                ino_zero: bool = False) -> tuple[Run, dict]:
    """La garde COPIÉE dans `t`, exécutée DANS ce processus contre `t.root` (seul moyen de forcer une course :
    `os.stat` d'un chemin qui échoue à partir de son 2e appel, comme un lien qui disparaît après `exists()` ; ou
    un système de fichiers sans inode stable : `ino_zero` rend `st_ino == 0` sous `t.root`, FAT/exFAT simulé).
    Rend le verdict et le compte des `os.scandir` par chemin RÉEL. `os` et l'env git sont restaurés."""
    src = (t.root / "conftest.py").read_text(encoding="utf-8")
    ancre = "_RACINE_1188 = os.path.dirname(os.path.abspath(__file__))"
    if ancre in src:
        src = src.replace(ancre, "_RACINE_1188 = %r" % str(t.root))
    reel_scandir, reel_stat, appels, comptes = os.scandir, os.stat, {}, {}

    def scandir(chemin="."):
        reel = os.path.realpath(chemin)
        comptes[reel] = comptes.get(reel, 0) + 1
        return _Ordonne(reel_scandir, chemin) if links_first else reel_scandir(chemin)

    def stat(chemin, *a, **k):
        if fail_stat_after_first and os.fspath(chemin) == fail_stat_after_first:
            appels[fail_stat_after_first] = appels.get(fail_stat_after_first, 0) + 1
            if appels[fail_stat_after_first] > 1:
                raise FileNotFoundError(2, "No such file or directory", fail_stat_after_first)
        r = reel_stat(chemin, *a, **k)
        if ino_zero and not isinstance(chemin, int) and os.fspath(chemin).startswith(str(t.root)):
            return os.stat_result((r.st_mode, 0, r.st_dev, r.st_nlink, r.st_uid, r.st_gid, r.st_size,
                                   int(r.st_atime), int(r.st_mtime), int(r.st_ctime)))
        return r

    noms = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "XDG_CONFIG_HOME")
    sauves = {k: os.environ.get(k) for k in noms}
    os.environ.update({k: t.env[k] for k in noms})
    os.scandir, os.stat = scandir, stat
    try:
        exec(compile(src, str(t.root / "conftest.py"), "exec"), {"__name__": "conftest_1188_en_processus"})
        return Run(0, [], ""), comptes
    except pytest.UsageError as exc:
        return Run(4, [], str(exc)), comptes
    finally:
        os.scandir, os.stat = reel_scandir, reel_stat
        for k, v in sauves.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def p20(t: Tree):
    """Revue sécu (advisory) : sans inode stable (`st_ino == 0`, FAT/exFAT simulé en processus), la garde ne
    déduplique pas — sinon tous les dossiers se confondraient et `.agents/state/local/b/test_b.py` ne serait jamais
    lu (fail-open)."""
    t.write(L + "a/data.csv", "a\n")
    t.plant(L + "b/test_b.py", "P20")
    r, _ = _in_process(t, ino_zero=True)
    return (r.rc == 4 and L + "b/test_b.py" in r.named), r


def p19(t: Tree):
    """Revue sécu (medium 1, TOCTOU) : un lien qui disparaît entre `exists()` et `stat()` ne fait sauter AUCUNE
    entrée voisine — `outside/test_z.py`, lu APRÈS le lien, est nommé (en processus, lien lu en premier)."""
    _skip_unless_posix("symbolic link")
    cible = t.tmp / "lnk_target"
    t.write("x.csv", "a\n", base=cible)
    t.plant("outside/test_z.py", "P19")
    os.symlink(cible, t.root / "outside" / "lnk")
    r, _ = _in_process(t, fail_stat_after_first=str(t.root / "outside" / "lnk"), links_first=True)
    return (r.rc == 4 and "outside/test_z.py" in r.named), r


def v15(t: Tree):
    """Revue sécu (medium 2-3) : `vus` PARTAGÉ — `pkgs/gen/`, atteint par deux départs (`pkgs`, la racine) et par un
    lien depuis `.agents/state/local/`, n'est lu qu'UNE fois (compte des `os.scandir` par chemin réel)."""
    _skip_unless_posix("symbolic link")
    t.write("pkgs/gen/sub/x.csv", "a\n")
    t.write("pkgs/gen/y.csv", "a\n")
    os.symlink(t.root / "pkgs" / "gen", t.root / L / "lnk")
    r, comptes = _in_process(t)
    gen = os.path.realpath(t.root / "pkgs" / "gen")
    return (r.rc == 0 and comptes.get(gen) == 1 and max(comptes.values()) == 1), Run(r.rc, [], f"{comptes}\n{r.out}")


def v1(t: Tree):
    r = t.pytest()
    return (r.rc == 0 and "T-00001188" not in r.out), r


def v2(t: Tree):
    t.worktree(".worktrees/b-T-1")
    r = t.pytest()
    return (r.rc == 0 and not r.canaries), r


def v3(t: Tree):
    t.write("pkgs/gen/_version.py", "v = '1'\n")
    t.write("pkgs/gen/__init__.py", "")
    r = t.pytest()
    return r.rc == 0, r


def v4(t: Tree):
    t.write("pkgs/build/lib/pkg/__init__.py", "")
    t.plant("pkgs/.tox/py/test_x.py", "TOX")
    t.plant("pkgs/build/test_k.py", "BLD")
    r = t.pytest()
    return (r.rc == 0 and not r.canaries), r


def v6(t: Tree):
    t.plant(L + "t/test_t.py", "TRACKED")
    t.git("add", "-f", L + "t/test_t.py")
    t.git("commit", "-q", "-m", "tracked under an ignored directory")
    r = t.pytest(L)
    return (r.rc == 0 and r.canaries == ["CANARY_TRACKED"]), r


def v9(t: Tree):
    for venv in ("pkgs/env", "env", ".direnv/python-3.14"):
        tag = venv.replace("/", "_")
        t.write(venv + "/pyvenv.cfg", "home = /x\n")
        t.plant(venv + "/lib/python3.14/site-packages/certifi/tests/test_certify.py", "V" + tag)
        t.plant(venv + "/lib/python3.14/site-packages/certifi/conftest.py", "VC" + tag, test=False)
    t.write("pkgs/cenv/conda-meta/history", "")
    t.plant("pkgs/cenv/lib/test_cc.py", "CONDA")
    t.plant(".agents/evals/.ipynb_checkpoints/test_ok-checkpoint.py", "IPYNB")
    r = t.pytest()
    return (r.rc == 0 and not r.canaries), r


def p21(t: Tree):
    """Avis sécu A1 (passe de correction F5) — remplace V10 : `.git` présent, git absent du PATH ⇒ REFUS rc 4 nommé,
    aucun plant chargé ; la garde n'est plus INACTIVE pour ce motif."""
    _plant_l(t)
    empty = t.tmp / "emptybin"
    empty.mkdir()
    r = t.pytest(env={"PATH": str(empty)})
    return (r.rc == 4 and not r.canaries and "git absent du PATH" in r.out and "porte REFUSÉE" in r.out), r


def v16(t: Tree):
    """Borne (n), le SEUL motif d'inactivité restant après A1 : `.git` retiré ⇒ garde INACTIVE ANNONCÉE, rc 0."""
    (t.root / ".git").rename(t.tmp / "git-retire")
    r = t.pytest()
    return (r.rc == 0 and "garde fichiers ignorés INACTIVE (pas de .git" in r.out), r


def p22(t: Tree):
    """Avis sécu A2 : `Conftest.py` ignoré — sur un FS insensible à la casse (APFS), pytest le charge comme conftest
    (`is_file()`) ; la garde le refuse quelle que soit la casse (faux rouge déclaré sur un FS sensible)."""
    t.plant(L + "Conftest.py", "CCONF", test=False)
    r = t.pytest()
    return (r.rc == 4 and L + "Conftest.py" in r.named and not r.canaries), r


INI_N5 = "[pytest]\ntestpaths = tests\nnorecursedirs = vendor\npython_files = test_*.py\n"


def v17(t: Tree):
    """N5 (revue de clôture F5) : `norecursedirs = vendor` de pytest.ini — pytest n'entre pas dans `vendor/`, la garde
    non plus : un test ignoré sous `vendor/lib/` n'est ni chargé ni refusé, pytest nu ET `pytest .`. Rouge à la base
    (UsageError rc 4, mesuré par critic-opus sous pytest 9.1.1)."""
    t.write("pytest.ini", INI_N5)
    t.write("tests/test_t.py", "def test_t():\n    pass\n")
    t.ignore("vendor/")
    t.plant("vendor/lib/test_x.py", "VENDOR")
    r, r2 = t.pytest(), t.pytest(".")
    ok = all(x.rc == 0 and not x.canaries and "T-00001188" not in x.out for x in (r, r2))
    return ok, Run(r.rc, r.canaries + r2.canaries, r.out + "\n--- pytest .\n" + r2.out)


def p23(t: Tree):
    """N5, polarité : l'ini REMPLACE les défauts comme dans pytest — `.*` n'élague plus, pytest nu descend dans
    `.hid/` : son test ignoré est REFUSÉ (une union ini ∪ défauts le laisserait passer, et pytest le chargerait)."""
    t.write("pytest.ini", "[pytest]\nnorecursedirs = vendor\npython_files = test_*.py\n")
    t.ignore(".hid/")
    t.plant(".hid/test_h.py", "HID")
    r = t.pytest()
    return _refused(r, ".hid/test_h.py"), r


def v11(t: Tree):
    t.write("pkgs/test_venv/pyvenv.cfg", "home = /x\n")
    t.plant("pkgs/test_venv/lib/test_x.py", "V11T")
    t.plant("pkgs/test_venv/sub/conftest.py", "V11C", test=False)
    r = t.pytest()
    return (r.rc == 0 and not r.canaries and "T-00001188" not in r.out), r


# --- Témoins runner (/bin/bash) --------------------------------------------------------------------------------
def _bash() -> None:
    if not (POSIX and os.path.exists("/bin/bash")):
        pytest.skip("ANNOUNCED SKIP: no /bin/bash -- run-bash-tests.sh case not measured")


def b1(t: Tree):
    _bash()
    t.suite("evil/x.test.sh", "evil")
    r = t.runner()
    return (r.rc == 2 and not r.ran and r.refused == {"evil/x.test.sh"}), r


def b2(t: Tree):
    _bash()
    t.suite("evil/x.test.sh", "evil")
    r = t.runner("--only", "./evil/x.test.sh")
    return (r.rc == 2 and not r.ran and r.refused == {"evil/x.test.sh"}), r


def b3(t: Tree):
    _bash()
    t.suite("evil/x.test.sh", "evil")
    r = t.runner("--only", "./ok.test.sh")
    return (r.rc == 2 and not r.ran and r.refused == {"evil/x.test.sh"}), r


def b4(t: Tree):
    _bash()
    t.suite("evil/x.test.sh", "evil")
    host = t.tmp / "host"
    host.mkdir()
    t.git("init", "-q", ".", cwd=host)
    r = t.runner(env={"GIT_DIR": str(host / ".git"), "GIT_WORK_TREE": str(host)})
    return (r.rc == 2 and not r.ran and r.refused == {"evil/x.test.sh"}), r


def b5(t: Tree):
    _bash()
    t.suite("evil/x.test.sh", "evil")
    r = t.runner(env={"PATH": t.fakegit("exit 128\n")})
    return (r.rc == 2 and not r.ran and "check-ignore rc=128 (fail-closed)" in r.out), r


def b6(t: Tree):
    _bash()
    t.git("rm", "-q", "ok.test.sh")
    t.git("commit", "-q", "-m", "no own suite")
    (t.root / "nest").mkdir()
    t.git("init", "-q", ".", cwd=t.root / "nest")
    t.suite("nest/y.test.sh", "foreign")
    r = t.runner()
    return (r.rc == 0 and not r.ran and "COVERAGE DEGRADED" in r.out and "T-00001188" not in r.out), r


def v1r(t: Tree):
    _bash()
    r = t.runner()
    return (r.rc == 0 and r.ran == ["ok"] and "T-00001188" not in r.out), r


def v6r(t: Tree):
    _bash()
    t.suite(L + "tracked.test.sh", "tracked")
    t.git("add", "-f", L + "tracked.test.sh")
    t.git("commit", "-q", "-m", "tracked suite under an ignored directory")
    r = t.runner()
    return (r.rc == 0 and sorted(r.ran) == ["ok", "tracked"]), r


def b8(t: Tree):
    """Avis sécu A1, côté runner — remplace V10r : `.git` présent, git absent du PATH ⇒ REFUS rc 2 nommé, aucune
    suite lancée (la suite ignorée ne tourne plus sous une garde inactive)."""
    _bash()
    t.suite("evil/x.test.sh", "evil")
    tools = t.tmp / "toolsbin"
    tools.mkdir()
    for name in TOOLS:
        found = shutil.which(name)
        if found:
            os.symlink(found, tools / name)
    r = t.runner(env={"PATH": str(tools)})
    return (r.rc == 2 and not r.ran and "git absent du PATH" in r.out and "porte REFUSÉE" in r.out), r


def b9(t: Tree):
    """Avis sécu A3 : un nom de suite ignorée porteur d'un caractère de contrôle (ESC) est écrit QUOTÉ par `printf %q`,
    jamais brut sur le terminal."""
    _bash()
    t.suite("evil/a\x1b[31mb.test.sh", "evil")
    r = t.runner()
    return (r.rc == 2 and not r.ran and "\x1b" not in r.out and "evil/a" in r.out), r


def b7(t: Tree):
    """exec-critic XM18, côté runner : la garde s'ACTIVE à la racine d'un worktree LIÉ (`.git` fichier)."""
    _bash()
    wt = t.linked_root()
    t.suite(L + "evil.test.sh", "evil", base=wt)
    r = t.runner(cwd=wt)
    return (r.rc == 2 and not r.ran and r.refused == {L + "evil.test.sh"}), r


SCENARIOS = {"P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5, "P6": p6, "P7": p7, "P8": p8, "P9": p9, "P10": p10,
             "P11a": p11a, "P11b": p11b, "P11c": p11c, "P11d": p11d, "P11e": p11e, "P11f": p11f, "P12": p12,
             "P13": p13, "P14": p14, "P15": p15, "P16": p16, "V1": v1, "V2": v2, "V3": v3, "V4": v4, "V6": v6,
             "P17": p17, "P18": p18, "P19": p19, "P20": p20, "V15": v15, "V9": v9, "V11": v11, "V12": v12, "V13": v13, "V14": v14, "B1": b1, "B2": b2, "B3": b3, "B4": b4, "B5": b5, "B6": b6,
             "B7": b7, "V1r": v1r, "V6r": v6r,
             # Passe de correction F5 : A1 (P21, B8 — remplacent V10, V10r), A2 (P22), A3 (B9), N5 (V17, P23), V16.
             "P21": p21, "P22": p22, "P23": p23, "V16": v16, "V17": v17, "B8": b8, "B9": b9}
#: Réglages INJECTÉS par remplacement exact, jamais des mutants : le délai git réduit (P10), le plafond d'entrées
#: réduit (P18 — aucun vrai parcours géant n'est joué).
INJECT = {"P10": (("_DELAI = 30\n", "_DELAI = 1\n"),), "P18": (("_PLAFOND = 200000\n", "_PLAFOND = 5\n"),)}


def _tree(tmp: Path, name: str, conftest: str = CONFTEST, runner: str = RUNNER) -> Tree:
    return Tree(tmp, conftest=_mutate(conftest, INJECT[name]) if name in INJECT and conftest else conftest, runner=runner)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_holds(tmp_path: Path, name: str) -> None:
    holds, r = SCENARIOS[name](_tree(tmp_path, name))
    assert holds, f"{name}: {r!r}"


@pytest.mark.parametrize("mode", ["prepend", "append", "importlib"])
@pytest.mark.parametrize("name", ["P1", "P2", "P3"])
def test_refusal_holds_in_every_import_mode(tmp_path: Path, name: str, mode: str) -> None:
    holds, r = SCENARIOS[name](_tree(tmp_path, name), mode=mode)
    assert holds, f"{name} --import-mode={mode}: {r!r}"


RED_WITHOUT_GUARD = [n for n in SCENARIOS if n.startswith("P")]


@pytest.mark.parametrize("name", RED_WITHOUT_GUARD)
def test_witness_is_red_without_the_guard(tmp_path: Path, name: str) -> None:
    """Rouge à HEAD : sans la garde (conftest d'avant T-00001188, ici le conftest VIDE), le témoin ne tient pas —
    et pytest CHARGE vraiment le plant (canari écrit), sauf P13 (dossier illisible : pytest ne peut pas le lister)
    et P17 (lien cassé : pytest l'ignore, refus fail-closed), et P19, P20 (joués EN PROCESSUS : pas de pytest, pas
    de canari — sans la garde, rien n'est refusé)."""
    holds, r = SCENARIOS[name](_tree(tmp_path, name, conftest=""))
    assert not holds, f"{name} holds without the guard: {r!r}"
    # P22 : sur un FS SENSIBLE à la casse, pytest ne charge pas `Conftest.py` (faux rouge déclaré) — pas de canari.
    if name not in ("P13", "P17", "P19", "P20", "P22"):
        assert r.canaries, f"{name}: pytest did not load the plant without the guard -- the witness is vacuous: {r!r}"


# --- D1 : différentiel à deux sens ----------------------------------------------------------------------------
D1_IN = (L + "test_a.py", L + "sub/test_b.py", L + "v1/Venv/test_c.py", "pkgs/gen2/Node_Modules/test_d.py",
         "pkgs/gen/test_g.py", "pkgs/Venv/test_j.py")
D1_PRUNED = (L + "venv/test_e.py", L + ".hid/test_f.py", L + "build/test_k.py", L + "env/test_v.py",
             L + "cenv/test_cv.py", L + "node_modules/test_nm.py", L + "x.egg/test_egg.py", L + "dist/test_dist.py",
             L + ".ipynb_checkpoints/test_ck.py")
D1_OUT = (".worktrees/b1/test_o.py", "env/lib/test_env.py", "outside/test_out.py")
D1_AMORCE = ("pkgs/test_c.bak", ".agents/testvenv.bak", ".agents/evals/test_cache.bak", L + "test_v")
#: Faux rouge DÉCLARÉ (Contrat) : `*_test.py` ignoré, que `python_files = test_*.py` ne collecte pas.
D1_FALSE_RED = {L + "evil_test.py"}


class D1:
    def __init__(self, tmp: Path) -> None:
        self.t = t = Tree(tmp, conftest="", ini=INI3)
        self.planted: dict[str, str] = {}
        t.ignore("pkgs/gen2/", ".hid/", "venv/", "build/", "node_modules/", "Node_Modules/", "Venv/", "x.egg/", "dist/",
                 "env/", "cenv/", "nested/")
        for rel in D1_IN + D1_PRUNED + D1_OUT + (L + "evil_test.py", "pkgs/test_venv/lib/test_x.py"):
            self._plant(rel)
        for rel in (L + "conftest.py", "pkgs/test_venv/sub/conftest.py") + tuple(d + "/conftest.py" for d in D1_AMORCE):
            self._plant(rel, test=False)
        for d in D1_AMORCE + ("pkgs/test_venv",):
            t.write(d + "/pyvenv.cfg", "home = /x\n")
        t.write(L + "env/pyvenv.cfg", "home = /x\n")
        t.write(L + "cenv/conda-meta/history", "")
        self._plant(L + "nested/test_n.py")
        t.git("init", "-q", ".", cwd=t.root / L / "nested")
        t.worktree(L + "wt2")
        self.planted["WTC"] = L + "wt2/conftest.py"
        self.planted["WTT"] = L + "wt2/test_wt.py"
        if POSIX:  # décision /04 : liens SUIVIS ; le test est nommé sous le chemin du lien, le dossier de données jamais
            out = tmp / "outside_target"
            t.write("test_lnk.py", t.canary("LNK") + "def test_l():\n    pass\n", base=out)
            os.symlink(out, t.root / L / "lnk")
            self.planted["LNK"] = L + "lnk/test_lnk.py"
            t.write("data.csv", "a,b\n", base=tmp / "outside_data")
            os.symlink(tmp / "outside_data", t.root / L / "datalnk")
        self.loaded: set[str] = set()
        for args in (("--collect-only",), ("--collect-only", "."), ("--collect-only", L)):
            self.loaded |= {self.planted[c[len("CANARY_"):]] for c in t.pytest(*args).canaries}

    def _plant(self, rel: str, test: bool = True) -> None:
        tag = rel.replace("/", "__")
        self.t.plant(rel, tag, test=test)
        self.planted[tag] = rel

    def named(self, conftest: str) -> tuple[set[str], Run]:
        self.t.write("conftest.py", conftest)
        r = self.t.pytest()
        return r.named, r

    def holds(self, conftest: str) -> tuple[bool, str]:
        named, r = self.named(conftest)
        missing, extra = self.loaded - named, named - self.loaded
        return (not missing and extra == D1_FALSE_RED and r.rc == 4 and not r.canaries,
                f"CHARGÉ∖NOMMÉ={sorted(missing)} NOMMÉ∖CHARGÉ={sorted(extra)} rc={r.rc} canaries={r.canaries}")


@pytest.fixture(scope="module")
def d1(tmp_path_factory) -> D1:
    return D1(tmp_path_factory.mktemp("d1"))


def test_d1_two_way_differential(d1: D1) -> None:
    """Ce que pytest CHARGE sans garde (nu ∪ `pytest .` ∪ `pytest .agents/state/local`) ⊆ ce que la garde NOMME,
    et ce qu'elle nomme de plus est exactement le faux rouge déclaré ; l'univers n'est pas vide."""
    assert {d + "/conftest.py" for d in D1_AMORCE} <= d1.loaded, sorted(d1.loaded)
    assert {L + "wt2/conftest.py", L + "nested/test_n.py"} <= d1.loaded, sorted(d1.loaded)
    assert not (set(D1_PRUNED) | {".worktrees/b1/test_o.py"}) & d1.loaded, sorted(d1.loaded)
    holds, detail = d1.holds(CONFTEST)
    assert holds, detail


# --- Mutants ---------------------------------------------------------------------------------------------------
_PRUNE_VENV = ('    if os.path.isfile(os.path.join(chemin, "pyvenv.cfg")) or os.path.isfile(\n'
               '            os.path.join(chemin, "conda-meta", "history")):\n        return True\n')
_ROOT_ONLY = ("    for motif in motifs:\n", "    for motif in ():\n")
_LOOP_GUARD = ("        if vus.get(cle) or (cle in vus and not strict):\n"
               "            continue  # déjà parcouru : boucle de liens, ou sous-arbre atteint par un autre chemin\n")
_LINK_LISTED = "_marcher(e, sortie, inits, dep in ancres, vus, compte)  # (b) décision /04 : suivi"
_WALK_IF = "                        if not _elague(e.path, e.name):\n"
_STRICT = "    if strict:\n        raise"
_GUARD_BLOCK_START = '_g1188=""\n'
_GUARD_BLOCK_END = '  if [ -n "$_g1188" ]; then echo "T-00001188 : garde suites ignorées INACTIVE ($_g1188)" >&2; fi\nfi\n'
_ONLY_END = '  echo "Only: $_hit (--only)"\nfi\n'


def _guard_after_only(runner: str) -> str:
    """M10 : le bloc de garde DÉPLACÉ après `--only` (il ne juge plus que la suite élue)."""
    start, end = runner.index(_GUARD_BLOCK_START), runner.index(_GUARD_BLOCK_END) + len(_GUARD_BLOCK_END)
    assert runner.count(_GUARD_BLOCK_START) == 1 and runner.count(_ONLY_END) == 1
    block, rest = runner[start:end], runner[:start] + runner[end:]
    at = rest.index(_ONLY_END) + len(_ONLY_END)
    return rest[:at] + block + rest[at:]


MUTANTS = {  # nom -> (cible, remplacements, témoins)
    "M1_guard_removed": ("conftest", (("_INACTIVE_1188 = _garde_1188()\n", "_INACTIVE_1188 = None\n"),),
                         ("P1", "P2", "P3")),
    "M4_links_not_followed": ("conftest", ((_WALK_IF, "                        if not _elague(e.path, e.name) and not"
                                                      " e.is_symlink():\n"), (_LINK_LISTED, "pass")), ("P5", "D1")),
    "M5_no_init_rule": ("conftest", (("    if inits:\n", "    if False:\n"),), ("P6",)),
    "M6_env_not_purged": ("conftest", (("env = {k: v for k, v in os.environ.items() if not git_herite(k)}",
                                        "env = dict(os.environ)"),), ("P7",)),
    "M7_git_rc_ignored": ("conftest", (("    if cp.returncode:\n        lignes", "    if False:\n        lignes"),),
                          ("P8",)),
    "M12_no_venv_pruning": ("conftest", ((_PRUNE_VENV, ""),), ("V9", "D1")),
    "M13_nest_exempted": ("conftest", (("        d = pile.pop()\n", "        d = pile.pop()\n        if os.path.lexists("
                                        "os.path.join(_RACINE_1188, d, \".git\")):\n            continue\n"),),
                          ("P4", "P9", "D1")),
    "M16_inactive_silent": ("conftest", (("    if _INACTIVE_1188:\n", "    if False:\n"),), ("V16",)),
    "M17_no_name_pruning": ("conftest", (("    return any(_apparie(chemin, nom, motif) for motif in motifs)\n",
                                          "    return False\n"),), ("V2", "V4", "V9", "V17", "D1")),
    "M18_root_only": ("conftest", (_ROOT_ONLY,), ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P9", "D1")),
    "M20_whole_tree": ("conftest", (('_NORECURSE_1188 = ("*.egg", ".*", ', '_NORECURSE_1188 = ("*.egg", '), _ROOT_ONLY),
                       ("V2", "V4", "V9", "D1")),
    "M21_no_amorce": ("conftest", (('    return fnmatch.fnmatchcase(nom, "test*") and', "    return False and"),
                                   ("            if os.path.isfile(os.path.join(_RACINE_1188, cand)) and (",
                                    "            if False and (")),
                      ("P11a", "P11b", "P11c", "P11d", "P11e", "P11f", "D1")),
    "M22_tracked_only_if_ignored": ("conftest", (('suivis = _git_1188(env, "ls-files", "-c", "-z")',
                                                  'suivis = _git_1188(env, "ls-files", "-c", "-i", "--exclude-standard",'
                                                  ' "-z")'),), ("P12",)),
    "M6r_runner_env_not_purged": ("runner", (("      unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY "
                                              "GIT_COMMON_DIR \\\n        GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE"
                                              " GIT_PREFIX \\\n        GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT\n", ""),),
                                  ("B4",)),
    "M8_no_check_ignore": ("runner", (('if [ "${#SUITES[@]}" -gt 0 ]; then\n  if [ ! -e "$ROOT/.git" ]',
                                       'if false; then\n  if [ ! -e "$ROOT/.git" ]'),), ("B1",)),
    "M9_no_index": ("runner", (("check-ignore -z --stdin", "check-ignore --no-index -z --stdin"),), ("V6r",)),
    "M10_refusal_after_only": ("runner", None, ("B3",)),
    "M14_empty_list_checked": ("runner", (('if [ "${#SUITES[@]}" -gt 0 ]; then', "if true; then"),), ("B6",)),
    # exec-critic (GO_AVEC_RESERVES) : ses trois survivants XM10, XM22, XM18, et l'illisible restreint aux départs.
    "M23_testpath_under_ignored_not_walked": ("conftest", (('                _marcher("/".join(dep), sortie, inits,'
                                                            ' dep in ancres, vus, compte)  # un testpath SOUS un'
                                                            ' dossier ignoré',
                                                            "                pass"),), ("P14",)),
    "M24_e2_file_level_missed": ("conftest", (("                    cand in fichiers or any(cand.startswith(x) for x in"
                                               " dossiers)):", "                    any(cand.startswith(x) for x in"
                                               " dossiers)):"),), ("P15",)),
    "M25_git_file_inactive": ("conftest", (('    if not os.path.lexists(os.path.join(_RACINE_1188, ".git")):',
                                            '    if not os.path.isdir(os.path.join(_RACINE_1188, ".git")):'),), ("P16",)),
    "M25r_runner_git_file_inactive": ("runner", (('  if [ ! -e "$ROOT/.git" ]; then', '  if [ ! -d "$ROOT/.git" ]; then'),),
                                      ("B7",)),
    "M26_unreadable_refused_everywhere": ("conftest", ((_STRICT, "    if True:\n        raise"),), ("V12",)),
    "M27_unreadable_skipped": ("conftest", ((_STRICT, "    if False:\n        raise"),), ("P13", "P17")),
    # Revue de clôture (T1), décision pilote decision/T-00001188/04 : liens SUIVIS, anti-boucle, lien cassé.
    "M28_links_refused_unread": ("conftest", ((_WALK_IF, "                        if not _elague(e.path, e.name) and"
                                                         " e.is_symlink():\n                            sortie.add(rel)\n"
                                                         "                        elif not _elague(e.path, e.name):\n"),
                                              (_LINK_LISTED, "sortie.add(e)")), ("V13",)),
    "M29_no_loop_guard": ("conftest", ((_LOOP_GUARD, ""),), ("V14",)),
    "M30_dangling_link_skipped": ("conftest", (('                        _illisible(rel, "lien git-ignoré cassé", strict)\n',
                                                "                        pass\n"),), ("P17",)),
    # Revue sécu du delta 117dcf47 : TOCTOU, plafond, `vus` partagé.
    "M31_no_entry_cap": ("conftest", (("                    if compte[0] > _PLAFOND:\n", "                    if False:\n"),),
                         ("P18",)),
    "M32_unguarded_link_stat": ("conftest", ((_WALK_IF, _WALK_IF + "                            if e.is_symlink():\n"
                                                                   "                                os.stat(e.path)\n"),),
                                ("P19",)),
    "M33_visited_set_per_walk": ("conftest", (("    pile = [depart]\n", "    vus = {}\n    pile = [depart]\n"),), ("V15",)),
    "M34_dedup_without_stable_inode": ("conftest", ((" if st.st_ino else None\n", " if True else None\n"),), ("P20",)),
    # Passe de correction F5 : N5 (norecursedirs de l'ini), A1 (git absent ⇒ refus), A2 (casse), A3 (printf %q).
    "M35_ini_norecurse_ignored": ("conftest", (("        _NORECURSE_INI = tuple(shlex.split(brut)) if brut is not None"
                                                " else None\n", "        _NORECURSE_INI = None\n"),), ("V17", "P23")),
    "M36_ini_norecurse_union": ("conftest", (("    motifs = _NORECURSE_1188 if _NORECURSE_INI is None else _NORECURSE_INI\n",
                                              "    motifs = _NORECURSE_1188 + (_NORECURSE_INI or ())\n"),), ("P23",)),
    "M37_conftest_exact_case": ("conftest", (('    return (nom.casefold() == "conftest.py" or',
                                              '    return (nom == "conftest.py" or'),), ("P22",)),
    "M38_git_absent_inactive": ("conftest", (('    if shutil.which("git") is None:\n        raise pytest.UsageError(sans_git)\n',
                                              '    if shutil.which("git") is None:\n        return "git absent du PATH"\n'),),
                                ("P21",)),
    "M38r_runner_git_absent_inactive": ("runner", (("    exit 2\n  else\n    _rc1188=0\n",
                                                    "    _g1188=\"git absent du PATH\"\n  else\n    _rc1188=0\n"),), ("B8",)),
    "M39r_names_unquoted": ("runner", (("printf '  - %q\\n' \"$_l\" >&2", 'echo "  - $_l" >&2'),), ("B9",)),
}
MUTANT_PARAMS = [(m, w) for m, (_c, _r, ws) in MUTANTS.items() for w in ws]


@pytest.mark.parametrize(("mut", "witness"), MUTANT_PARAMS, ids=[f"{m}-{w}" for m, w in MUTANT_PARAMS])
def test_mutant_turns_its_witness_red(request, tmp_path: Path, mut: str, witness: str) -> None:
    target, pairs, _ = MUTANTS[mut]
    conftest, runner = CONFTEST, RUNNER
    if target == "conftest":
        conftest = _mutate(CONFTEST, pairs)
        compile(conftest, "conftest.py", "exec")
    else:
        runner = _guard_after_only(RUNNER) if pairs is None else _mutate(RUNNER, pairs)
    if witness == "D1":
        holds, detail = request.getfixturevalue("d1").holds(conftest)
        assert not holds, f"{mut} did not turn D1 red: {detail}"
        return
    holds, r = SCENARIOS[witness](_tree(tmp_path, witness, conftest=conftest, runner=runner))
    assert not holds, f"{mut} did not turn {witness} red: {r!r}"


def test_v5_a_tree_without_git_announces_an_inactive_guard(tmp_path: Path) -> None:
    """V5 : arbre sans `.git` (projet sous-dossier d'un dépôt, borne n) : garde INACTIVE ANNONCÉE, jamais muette —
    pytest ET runner ; rien n'est refusé."""
    t = Tree(tmp_path, git=False)
    _plant_l(t)
    r = t.pytest()
    assert r.rc == 0 and "garde fichiers ignorés INACTIVE (pas de .git" in r.out, r
    _bash()
    r = t.runner()
    assert r.rc == 0 and "garde suites ignorées INACTIVE (pas de .git)" in r.out and r.ran == ["ok"], r


def test_this_bench_uses_no_census_walk_idiom() -> None:
    """Le banc voyage : il ne lit que conftest.py et run-bash-tests.sh, et n'emploie aucun idiome de parcours que
    test_repo_walk_census.py:88-91 recense (ses canaris se lisent par un motif sans `**`)."""
    own = Path(__file__).read_text(encoding="utf-8")
    for idiom in ("os." + "walk(", "r" + "glob(", "glob." + "glob(", "os." + "scandir(", "copy" + "tree("):
        assert idiom not in own, idiom
