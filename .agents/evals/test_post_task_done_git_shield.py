"""T-00000801 — LES APPELS GIT DU HOOK DE COMMIT D'ÉTAT (`post-task-done-index.sh`).

S-00003742 (option A', amendée par S-00003821 pour le préfixe) et S-00003226. Le préfixe des jambes Claude ne rend aux hooks,
de GIT_CONFIG_PARAMETERS et GIT_CONFIG_COUNT, que les entrées `safe.directory` (S-00003224) ; un hôte SANS préfixe les passe entiers,
et GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM, XDG_CONFIG_HOME et HOME traversent toujours. Par au moins ces SIX canaux d'environnement
git EXÉCUTE `core.fsmonitor` (au moins aux verbes de `VERBES_FSMONITOR`) et les hooks de `core.hooksPath` (`post-index-change` dès
qu'un verbe réécrit l'index, tous les hooks de commit au commit) — mesuré git 2.54 et 2.55 pour P, C et G, et S, X, H hors de ce
fichier (`fenetre8.py`, git 2.55, avec témoin). Le hook blinde donc CHAQUE appel git au site d'appel (`git_hote` :
`-c core.fsmonitor=false -c core.hooksPath=/dev/null`, de portée ligne de commande, qui l'emporte sur ces canaux et laisse
`safe.directory` passer) ET rend à ces appels le GIT_DIR / GIT_WORK_TREE que le préfixe a retirés (copie privée `_CADRE_GIT_DIR` /
`_CADRE_GIT_WORK_TREE`). Les canaux sont posés ICI directement à l'environnement du hook (P, C, G : un hôte sans préfixe) ; que P et C
n'atteignent plus un hook Claude est tenu par `test_hook_env_hardening.py::test_config_canary_stops_at_prefix`.

TROIS COUCHES. (1) RECENSEMENT DYNAMIQUE : un faux `git` du PATH journalise l'argv de CHAQUE appel du hook ; un argv qui ne
s'ouvre pas par les deux `-c` est une violation — il couvre les sites que git n'exécute pas (rev-parse, symbolic-ref, config)
et ne lit aucun texte du hook. (2) CANARI : un script fsmonitor et des hooks qui ÉCRIVENT un fichier, posés par chacun des
trois canaux JOUÉS ICI (P, C, G) ; ÉTALONNÉ (un git nu l'écrit — sinon le canal ne mord pas sur ce git : saut annoncé, ÉCHEC sous `CI=true` dans le kit)
avant d'être exigé vide sous le hook. (3) RESTAURATION : dépôt nu SOUS un parent ou SANS parent, GIT_DIR/GIT_WORK_TREE absents,
copies privées posées (la forme que donne le préfixe). Un MUTANT par site et par `-c` retiré prouve que chaque témoin peut
rougir. LA COUTURE : la jambe `PostToolUse(post-task-done-index)` LUE dans `.claude/settings.json` est jouée par `/bin/sh -c` (et
`/bin/dash -c` quand il diffère), GIT_DIR/GIT_WORK_TREE exportés — préfixe et hook s'accordent, de bout en bout, sur les NOMS des copies. Sous le préfixe (ii), P et C sont fermés AVANT le hook : leurs cellules prouvent la restauration (le
commit au bon dépôt), pas le blindage — celui des canaris directs, ci-dessus.
LES ENFANTS (`nu/enfants`) : tasks.py (commit-stores, commit-run-exports), specs_graph.py et scripts/index-refresh.sh ne
voient ni GIT_DIR ni GIT_WORK_TREE — un mutant par site d'enfant (MX1–MX4). Restaurer HORS du sous-shell est ÉQUIVALENT
pour eux, écrit : chaque appel `git_hote` de la jambe externe est dans une substitution `$( )`.
LES VERBES (`test_fsmonitor_verbs_listed`) : relevé « au moins » de ceux qui exécutent `core.fsmonitor`, sondé à deux faces
(des verbes témoins NE l'exécutent pas) et épinglé au SKILL guardrails, qui en porte la phrase.
OÙ MORD L'ÉCHEC NOMMÉ : `CI=true` est posé par GitHub Actions ; `verify.sh --linux` ne le transmet pas à son conteneur
(`docker run -e APT_PKGS` seul), où un canal muet SAUTE annoncé — la première mesure Linux est la CI après le push.

RÉSIDUS NOMMÉS, relevé « au moins » (L-00000187) : le blindage est une liste de clés, pas une purge du canal ;
`filter.<nom>.clean` (par `core.attributesFile`, à l'`add`) et `gpg.program` (interrupteur de signature posé par l'environnement)
EXÉCUTENT encore du code — mesuré, épinglé par `test_named_residues`, qui rougira le jour où la classe se ferme. Idem quand
ces clés sont portées par la config du dépôt DÉSIGNÉ par la copie privée (`nu/residu-filtre`, `nu/residu-gpg`, B-C2) : seuls
ses hooks et son `core.fsmonitor` sont neutralisés (`nu/depot-piege`).
OVERRIDE : `HOOK_HARDENING_SETTINGS=<chemin>` (même variable que `test_hook_env_hardening.py`) fait lire un candidat de
réglages à la couture ; refusé sous CI=true s'il ne désigne pas le fichier vivant.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

if os.name == "nt":
    pytest.skip("filet POSIX : hook bash + git (dette CI Windows T-00000744)", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[2]
HOOK_VIVANT = ROOT / ".agents" / "bin" / "post-task-done-index.sh"
SKILL_GARDES = ROOT / ".agents" / "skills" / "guardrails" / "SKILL.md"
REGLAGES_VIVANTS = ROOT / ".claude" / "settings.json"
# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT)
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
EN_CI = os.environ.get("CI") == "true"
GIT_REEL = shutil.which("git") or "git"
BLINDAGE = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
CANAUX = ("P", "C", "G")  # PARAMETERS, COUNT/KEY/VALUE, fichier GIT_CONFIG_GLOBAL ; GIT_CONFIG_SYSTEM, XDG_CONFIG_HOME, HOME : hors test
#: Enveloppes POSIX de la couture, dédoublonnées par chemin réel (sous Linux /bin/sh EST dash).
SHELLS = sorted({os.path.realpath(s): s for s in ("/bin/sh", "/bin/dash") if os.access(s, os.X_OK)}.values())
FLUX = ("stores", "exports", "echec", "externe", "degrade", "sans-racine")
#: Pas de maintenance de fond : `git commit` lance `maintenance run --auto` DÉTACHÉ, dont le verrou `objects/maintenance.lock`
#: fait échouer un `copytree` du dépôt (flake MESURÉ sous charge) et survit au test.
SANS_MAINTENANCE = "[maintenance]\n\tauto = false\n[gc]\n\tauto = 0\n"
HOOKS_CANARI = ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "post-index-change",
                "reference-transaction")
#: Verbes que chaque flux DOIT avoir joués : un recensement sur un flux court-circuité serait vide.
VERBES_ATTENDUS = {
    "stores": {"rev-parse", "symbolic-ref", "status", "add", "config", "commit"},
    "exports": {"rev-parse", "symbolic-ref", "status", "add", "config", "commit"},
    "echec": {"status", "add", "commit", "reset"},
    "externe": {"status", "add", "commit", "config"},
    "degrade": {"status", "add", "commit", "config"},
    "sans-racine": {"rev-parse", "status", "add", "commit"},
}
PAYLOAD = json.dumps({"tool_input": {"command": "python .agents/bin/tasks.py done T-34"}})


def run(argv, *, env, cwd=None, inp=None, timeout=180):
    return subprocess.run(argv, input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, cwd=None if cwd is None else str(cwd), timeout=timeout)


def ecrire(chemin: Path, texte: str, exe: bool = False) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    if exe:
        chemin.chmod(chemin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return chemin


# ---------------------------------------------------------------------------
# LE CANARI
# ---------------------------------------------------------------------------
class Canari:
    """Un script fsmonitor, des hooks, un attributs+filtre et un signataire qui ÉCRIVENT un
    fichier : la mesure — non une promesse — qu'un git a exécuté la config piégée."""

    def __init__(self, base: Path):
        self.rep = base / "canari"
        self.rep.mkdir()
        self.log = self.rep / "log"
        self.log.write_text("")
        self.fsm = ecrire(self.rep / "fsm.sh", f'#!/bin/sh\necho fsmonitor >> "{self.log}"\nexit 0\n', True)
        self.hooks = self.rep / "hooks"
        for h in HOOKS_CANARI:
            ecrire(self.hooks / h, f'#!/bin/sh\necho "hook {h}" >> "{self.log}"\nexit 0\n', True)
        self.conf_globale = ecrire(self.rep / "gconf", f"{SANS_MAINTENANCE}[core]\n\tfsmonitor = {self.fsm}\n\thooksPath = {self.hooks}\n")
        self.filtre = ecrire(self.rep / "filt.sh", f'#!/bin/sh\necho filter-clean >> "{self.log}"\ncat\n', True)
        self.attributs = ecrire(self.rep / "attrs", "* filter=canari\n")
        self.signataire = ecrire(self.rep / "gpg.sh", f'#!/bin/sh\necho gpg-program >> "{self.log}"\nexit 1\n', True)

    def vu(self) -> list[str]:
        return sorted({x for x in self.log.read_text().split("\n") if x})

    def paires(self) -> list[tuple[str, str]]:
        return [("core.fsmonitor", str(self.fsm)), ("core.hooksPath", str(self.hooks))]

    def env(self, canal: str, paires=None) -> dict:
        paires = self.paires() if paires is None else paires
        if canal == "P":
            return {"GIT_CONFIG_PARAMETERS": " ".join(f"'{k}={v}'" for k, v in paires)}
        if canal == "C":
            e = {"GIT_CONFIG_COUNT": str(len(paires))}
            for i, (k, v) in enumerate(paires):
                e[f"GIT_CONFIG_KEY_{i}"], e[f"GIT_CONFIG_VALUE_{i}"] = k, v
            return e
        corps = SANS_MAINTENANCE + "".join(f"[{k.split('.')[0]}]\n\t{k.split('.', 1)[1]} = {v}\n" for k, v in paires
                                          if not k.startswith("filter."))
        if any(k == "filter.canari.clean" for k, _ in paires):
            corps += f'[filter "canari"]\n\tclean = {self.filtre}\n'
        return {"GIT_CONFIG_GLOBAL": str(ecrire(self.rep / "gconf-x", corps))}


# ---------------------------------------------------------------------------
# LE DÉPÔT JETABLE : normal, ou nu (SOUS un parent, SANS parent)
# ---------------------------------------------------------------------------
class Depot:
    def __init__(self, base: Path, layout: str = "normal", hook_texte: str | None = None):
        self.base, self.layout = base, layout
        self.nu = layout.startswith("nu")
        self.home = base / "home"
        (self.home / "xdg").mkdir(parents=True)
        self.vide = ecrire(base / "gconf-vide", SANS_MAINTENANCE)
        self.census = ecrire(base / "census.log", "")
        self.stub = base / "stub-git"
        ecrire(self.stub / "git", '#!/bin/sh\nprintf \'%s\\037\' "$@" >> "$CENSUS_LOG"\nprintf \'\\n\' >> "$CENSUS_LOG"\n'
               'exec "$CENSUS_GIT" "$@"\n', True)
        self.stub_py = base / "stub-py"
        for nom in ("python3", "python", "py"):
            ecrire(self.stub_py / nom, "#!/usr/bin/env bash\nexit 1\n", True)
        self.parent = None
        if layout == "nu-sous-parent":
            self.parent = base / "P"
            self.parent.mkdir()
            self.g(["init", "-q"], cwd=self.parent)
            self.identite(self.parent)
            ecrire(self.parent / "README", "parent\n")
            self.g(["add", "README"], cwd=self.parent)
            self.g(["commit", "-qm", "parent"], cwd=self.parent)
            self.w, self.n = self.parent / "w", self.parent / "n.git"
        elif layout == "nu-sans-parent":
            self.w, self.n = base / "w", base / "n.git"
        else:
            self.w, self.n = base / "w", None
        self.w.mkdir(parents=True, exist_ok=True)
        bin_ = self.w / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for f in sorted((ROOT / ".agents" / "bin").glob("tasks*.py")):
            shutil.copy2(f, bin_ / f.name)
        self.hook = ecrire(bin_ / "post-task-done-index.sh",
                           HOOK_VIVANT.read_text(encoding="utf-8") if hook_texte is None else hook_texte)
        ecrire(self.w / ".gitignore", "/.agents/state/local/\n")
        self.n_salir = 0
        ecrire(self.w / ".agents/state/board/TASKS.json", '{"tasks":[]}\n')
        ecrire(self.w / ".agents/state/memory/LEDGER.json", '{"entries":[]}\n')
        ecrire(self.w / ".agents/state/specs/SPECS.json", '{"entries":[]}\n')
        if self.nu:
            self.g(["init", "-q", "--bare", str(self.n)], cwd=base)
            self.identite(self.n, nu=True)
        else:
            self.g(["init", "-q"], cwd=self.w)
            self.identite(self.w)
        self.g(["config", "cadre.signStateCommits", "false"], cwd=self.w, nu=self.nu)
        self.g(["add", "-A"], cwd=self.w, nu=self.nu)
        self.g(["commit", "-qm", "init"], cwd=self.w, nu=self.nu)

    # -- git de FIXTURE : jamais le git du hook, jamais de canal hostile
    def genv(self, nu=False) -> dict:
        e = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "xdg"),
             "GIT_CONFIG_GLOBAL": str(self.vide), "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}
        if nu:
            e.update(GIT_DIR=str(self.n), GIT_WORK_TREE=str(self.w))
        return e

    def g(self, args, cwd=None, nu=False, check=True):
        p = run([GIT_REEL, *args], env=self.genv(nu), cwd=cwd)
        if check and p.returncode != 0:
            raise AssertionError(f"git {args} : rc {p.returncode} {p.stderr[:200]}")
        return p.stdout.strip()

    def identite(self, depot: Path, nu=False):
        argv = (["--git-dir", str(depot)] if nu else ["-C", str(depot)])
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            run([GIT_REEL, *argv, "config", k, v], env=self.genv())

    def depot_nu(self, *a, check=True):
        return self.g(["--git-dir", str(self.n), *a], check=check)

    def tete(self) -> str:
        return self.depot_nu("rev-parse", "HEAD") if self.nu else self.g(["rev-parse", "HEAD"], cwd=self.w)

    def tete_parent(self) -> str:
        return self.g(["rev-parse", "HEAD"], cwd=self.parent)

    # -- salir : contenu DIFFÉRENT à chaque appel (réécrire la même chose ne salit rien)
    def salir(self):
        self.n_salir += 1
        ecrire(self.w / ".agents/state/board/TASKS.json", '{"tasks":[{"id":"T-%d"}]}\n' % self.n_salir)

    def salir_export(self):
        self.n_salir += 1
        ecrire(self.w / "runs" / "aut" / "cop" / "2026-09.jsonl", "{}\n" * self.n_salir)

    # -- environnement du HOOK
    def env(self, extra=None, *, racine=True, copies=True) -> dict:
        e = {"PATH": f"{self.stub}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "xdg"),
             "GIT_CONFIG_GLOBAL": str(self.vide), "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
             "CADRE_STATE_DIR": str(self.base / "st"), "AGENTS_EVENTS_DIR": str(self.base / "ev"),
             "TMPDIR": str(self.base), "CENSUS_LOG": str(self.census), "CENSUS_GIT": GIT_REEL}
        if racine:
            e["CLAUDE_PROJECT_DIR"] = str(self.w)
        if copies and self.nu:
            e.update(_CADRE_GIT_DIR=str(self.n), _CADRE_GIT_WORK_TREE=str(self.w))
        e.update(extra or {})
        return e

    def appels(self) -> list[list[str]]:
        return [ligne.rstrip("\x1f").split("\x1f") for ligne in self.census.read_text().split("\n") if ligne]


def verbe(argv: list[str]) -> str:
    i = 0
    while i < len(argv):
        if argv[i] in ("-C", "-c"):
            i += 2
        elif argv[i].startswith("-"):
            i += 1
        else:
            return argv[i]
    return ""


def violations_recensement(appels: list[list[str]], attendus: set[str]) -> list[str]:
    v = [f"git NU (argv {a[:7]})" for a in appels if a[:4] != BLINDAGE]
    manque = attendus - {verbe(a) for a in appels}
    if manque:
        v.append(f"recensement à vide : verbes jamais joués {sorted(manque)}")
    return v


# ---------------------------------------------------------------------------
# LES FLUX (un par chemin du hook qui porte des appels git)
# ---------------------------------------------------------------------------
def derniere_ligne(s: str) -> str:
    lignes = s.strip().splitlines()
    return lignes[-1] if lignes else ""


def section(d: Depot, env: dict, selecteur: str) -> str:
    return derniere_ligne(run(["bash", str(d.hook), "--commit-section", str(d.w), selecteur], env=env, cwd=d.w).stdout)


def externe(d: Depot, env: dict, cwd=None) -> str:
    return run(["bash", str(d.hook)], env=env, inp=PAYLOAD, cwd=cwd or d.w).stdout


def sans_identite(d: Depot, actif: bool):
    cible = ["--git-dir", str(d.n)] if d.nu else ["-C", str(d.w)]
    if actif:
        run([GIT_REEL, *cible, "config", "user.useConfigOnly", "true"], env=d.genv())
        for k in ("user.email", "user.name"):
            run([GIT_REEL, *cible, "config", "--unset", k], env=d.genv())
    else:
        run([GIT_REEL, *cible, "config", "--unset", "user.useConfigOnly"], env=d.genv())
        d.identite(d.n if d.nu else d.w, nu=d.nu)


def flux_stores(d, env):
    d.salir()
    return section(d, env, "stores")


def flux_exports(d, env):
    d.salir_export()
    return section(d, env, "run-exports")


def flux_echec(d, env):
    d.salir()
    sans_identite(d, True)
    try:
        return section(d, env, "stores")
    finally:
        sans_identite(d, False)


def flux_externe(d, env):
    d.salir()
    d.salir_export()
    return externe(d, env)


def flux_degrade(d, env):
    d.salir()
    d.salir_export()
    return externe(d, dict(env, PATH=str(d.stub_py) + os.pathsep + env["PATH"]))


def flux_sans_racine(d, env):
    d.salir()
    env = {k: v for k, v in env.items() if k != "CLAUDE_PROJECT_DIR"}
    return externe(d, env)


FLUX_FN = {"stores": flux_stores, "exports": flux_exports, "echec": flux_echec, "externe": flux_externe,
           "degrade": flux_degrade, "sans-racine": flux_sans_racine}


def issue_attendue(flux: str, sortie: str) -> list[str]:
    if flux in ("stores", "exports"):
        return [] if sortie == "committed" else [f"{flux} : jeton {sortie!r}, attendu 'committed'"]
    if flux == "echec":
        return [] if sortie == "failed" else [f"echec : jeton {sortie!r}, attendu 'failed'"]
    attendu = {"externe": ("stores commités", "exports commités"), "degrade": ("sans verrou", "non tentés"),
               "sans-racine": ("stores commités",)}[flux]
    return [f"{flux} : « {a} » absent de {sortie[:120]!r}" for a in attendu if a not in sortie]


# ---------------------------------------------------------------------------
# COUCHE 1+2 : recensement et canari
# ---------------------------------------------------------------------------
def temoin_canari(base: Path, canal: str, flux: str, hook_texte=None) -> list[str]:
    d, c = Depot(base, "normal", hook_texte), Canari(base)
    sortie = FLUX_FN[flux](d, d.env(c.env(canal)))
    return (issue_attendue(flux, sortie) + [f"canari écrit : {x}" for x in c.vu()]
            + violations_recensement(d.appels(), VERBES_ATTENDUS[flux]))


def canal_mord(base: Path, canal: str) -> str | None:
    """None si un git NU exécute le canari par ce canal (status → fsmonitor, commit → hooks)."""
    d, c = Depot(base, "normal"), Canari(base)
    d.salir()
    env = d.genv()
    env.update(c.env(canal))
    for argv in (["status", "--porcelain"], ["add", "--", ".agents/state/board/TASKS.json"],
                 ["commit", "-q", "-m", "x", "--", ".agents/state/board/TASKS.json"]):
        run([GIT_REEL, "-C", str(d.w), *argv], env=env)
    vus = c.vu()
    if "fsmonitor" in vus and any(x.startswith("hook ") for x in vus):
        return None
    return f"{subprocess.run([GIT_REEL, '--version'], capture_output=True, text=True).stdout.strip()} n'exécute pas le canari par {canal} (vu {vus})"


def exiger_canal(raison: str | None, canal: str):
    if raison is None:
        return
    if EN_CI and EST_LE_KIT:
        pytest.fail(f"ÉCHEC NOMMÉ — canal {canal} : {raison} (sous CI=true dans le kit, un canari muet rendrait le témoin vide)")
    warnings.warn(f"canal {canal} muet : {raison} — témoins de ce canal non joués")
    pytest.skip(f"canal {canal} muet : {raison}")


@pytest.fixture(scope="session")
def etalon(tmp_path_factory):
    return {c: canal_mord(tmp_path_factory.mktemp(f"etal{c}"), c) for c in CANAUX}


@pytest.fixture(scope="session")
def matrice(tmp_path_factory, etalon):
    cellules = [(f, c, tmp_path_factory.mktemp(f"m-{f}-{c}")) for f in FLUX for c in CANAUX if etalon[c] is None]

    def une(fcb):
        f, c, base = fcb
        return (f, c), temoin_canari(base, c, f)

    with cf.ThreadPoolExecutor(4) as ex:  # les dossiers sont créés ICI, dans le fil principal : mktemp n'est pas pensé concurrent
        return dict(ex.map(une, cellules))


@pytest.mark.parametrize("canal", CANAUX)
def test_canary_bites_unshielded_git(canal, etalon):
    exiger_canal(etalon[canal], canal)


@pytest.mark.parametrize("canal", CANAUX)
@pytest.mark.parametrize("flux", FLUX)
def test_every_git_call_is_shielded(flux, canal, etalon, matrice):
    exiger_canal(etalon[canal], canal)
    assert not matrice[(flux, canal)], "\n".join(matrice[(flux, canal)])


def temoin_safe(base: Path, canal: str, texte=None) -> list[str]:
    """S-00003224 : le blindage `-c` laisse passer un `safe.directory` posé par l'environnement. Propriétaire étranger SIMULÉ
    (GIT_TEST_ASSUME_DIFFERENT_OWNER, git >= 2.35.2) : seul, git répond rc 128 (jeton `nothing`) ; avec safe.directory
    par le canal, le commit d'état naît."""
    d, c = Depot(base, "normal", texte), Canari(base)
    d.salir()
    etranger = {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}
    seul = section(d, d.env(etranger), "stores")
    if seul == "committed":
        return ["BOUTON_MUET"]
    jeton = section(d, d.env({**etranger, **c.env(canal, [("safe.directory", "*")])}), "stores")
    return ([] if jeton == "committed" else [f"safe.directory/{canal} : jeton {jeton!r}, attendu 'committed' (safe.directory perdu)"]) \
        + violations_recensement(d.appels(), {"status", "add", "commit"})


@pytest.mark.parametrize("canal", CANAUX)
def test_safe_directory_passes_through_shield(canal, tmp_path_factory, etalon):
    exiger_canal(etalon[canal], canal)
    v = temoin_safe(tmp_path_factory.mktemp(f"safe{canal}"), canal)
    if v == ["BOUTON_MUET"]:
        if EN_CI and EST_LE_KIT:
            pytest.fail("ÉCHEC NOMMÉ — GIT_TEST_ASSUME_DIFFERENT_OWNER ne mord pas sous CI=true dans le kit : témoin vide")
        warnings.warn("GIT_TEST_ASSUME_DIFFERENT_OWNER ne mord pas (git < 2.35.2 ?) : témoin safe.directory non joué")
        pytest.skip("bouton de propriétaire étranger muet")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# COUCHE 3 : RESTAURATION (le préfixe retire GIT_DIR/GIT_WORK_TREE, copies privées posées)
# ---------------------------------------------------------------------------
def recens(d: Depot) -> list[str]:
    """Aucun appel nu, quel que soit le scénario : le recensement vaut aussi aux restaurations."""
    return [x for x in violations_recensement(d.appels(), set()) if x.startswith("git NU")]


def au_nu(d: Depot, nom: str, jeton: str, avant: str, avant_p=None, attendu="committed") -> list[str]:
    ne = (d.tete() != avant) is (attendu == "committed")  # un commit est né ssi on en attendait un
    v = [] if jeton == attendu and ne else [f"{nom} : commit attendu au dépôt nu (jeton {attendu!r}), obtenu {jeton!r}"]
    if avant_p is not None and d.tete_parent() != avant_p:
        v.append(f"{nom} : le dépôt PARENT a bougé")
    return v + recens(d)


def nu_flux(base, texte, layout, flux):
    d = Depot(base, layout, texte)
    avant, avant_p = d.tete(), (d.tete_parent() if d.parent else None)
    return au_nu(d, f"{layout} / {flux}", FLUX_FN[flux](d, d.env()), avant, avant_p)


def nu_degrade(base, texte=None):
    d = Depot(base, "nu-sous-parent", texte)
    avant, avant_p = d.tete(), d.tete_parent()
    sortie = flux_degrade(d, d.env())
    v = [] if "non tentés" in sortie else [f"dégradé : clause « non tentés » absente de {sortie[:100]!r}"]
    return v + au_nu(d, "dégradé", "committed" if d.tete() != avant else "rien", avant, avant_p)


def nu_sous_parent(base, texte, nom, env_extra, prepare=None, attendu="committed"):
    """Scénarios de section `stores` en nu-sous-parent : `env_extra` (copies=False) fixe les variables posées ;
    `prepare(d)` abîme le parent ou le dépôt nu avant le jeu."""
    d = Depot(base, "nu-sous-parent", texte)
    if prepare:
        prepare(d)
    avant, avant_p = d.tete(), d.tete_parent()
    d.salir()
    jeton = section(d, d.env(copies=False, extra=env_extra(d)), "stores")
    return au_nu(d, nom, jeton, avant, avant_p, attendu)


def nu_preseance(base, texte=None):
    """La copie privée l'emporte sur un GIT_DIR ambiant (hôte portant les deux)."""
    d = Depot(base, "nu-sous-parent", texte)
    leurre = base / "leurre.git"
    d.g(["init", "-q", "--bare", str(leurre)], cwd=base)
    avant = d.tete()
    d.salir()
    jeton = section(d, d.env(extra={"GIT_DIR": str(leurre), "GIT_WORK_TREE": str(d.w)}), "stores")
    v = au_nu(d, "préséance", jeton, avant)
    if run([GIT_REEL, "--git-dir", str(leurre), "rev-parse", "-q", "--verify", "HEAD"], env=d.genv()).returncode == 0:
        v.append("préséance : un commit est né dans le leurre GIT_DIR")
    return v


def nu_depot_piege(base, texte=None):
    """B-C7 : la copie privée désigne un dépôt PIÉGÉ (hooks, core.fsmonitor dans SA config) : le commit y atterrit (même
    confiance que GIT_DIR avant T-801) mais ni ses hooks ni son `core.fsmonitor` ne s'exécutent — `-c` l'emporte sur eux ; sa config
    peut encore faire exécuter `filter.<nom>.clean` et `gpg.program` (`nu_residu`, B-C2)."""
    d, c = Depot(base, "nu-sans-parent", texte), Canari(base)
    piege = base / "piege.git"
    d.g(["clone", "-q", "--bare", str(d.n), str(piege)], cwd=base)  # pas de copytree : `test_repo_walk_census` le recense comme parcours
    d.identite(piege, nu=True)
    for h in HOOKS_CANARI:
        ecrire(piege / "hooks" / h, f'#!/bin/sh\necho "hook {h}" >> "{c.log}"\nexit 0\n', True)
    run([GIT_REEL, "--git-dir", str(piege), "config", "core.fsmonitor", str(c.fsm)], env=d.genv())
    tete = lambda: run([GIT_REEL, "--git-dir", str(piege), "rev-parse", "HEAD"], env=d.genv()).stdout.strip()  # noqa: E731
    avant = tete()
    d.salir()
    jeton = section(d, d.env(copies=False, extra={"_CADRE_GIT_DIR": str(piege), "_CADRE_GIT_WORK_TREE": str(d.w)}), "stores")
    v = [] if jeton == "committed" and tete() != avant else [f"dépôt piégé : le commit doit y atterrir, jeton {jeton!r}"]
    return v + [f"dépôt piégé : canari écrit {x}" for x in c.vu()] + recens(d)


def nu_residu(base, texte=None, quoi="filtre"):
    """B-C2 : la config du dépôt DÉSIGNÉ par la copie privée porte `filter.<nom>.clean` (par `core.attributesFile`) ou `gpg.program`
    (avec l'interrupteur de signature) : ils EXÉCUTENT encore sous le hook blindé — seuls ses hooks et son `core.fsmonitor` sont
    neutralisés (`nu_depot_piege`). RÉSIDU NOMMÉ, relevé « au moins » : ce témoin rougit (« résidu fermé ? ») le jour où la classe
    se ferme — amender alors le SKILL, l'en-tête du hook et ce témoin."""
    d, c = Depot(base, "nu-sans-parent", texte), Canari(base)
    piege = base / "piege.git"
    d.g(["clone", "-q", "--bare", str(d.n), str(piege)], cwd=base)
    d.identite(piege, nu=True)
    if quoi == "filtre":
        cles, attendu, aiguille = (("core.attributesFile", str(c.attributs)), ("filter.canari.clean", str(c.filtre))), "committed", "filter-clean"
    else:
        cles = (("cadre.signStateCommits", "true"), ("commit.gpgsign", "true"), ("gpg.program", str(c.signataire)))
        attendu, aiguille = "failed", "gpg-program"
    for k, x in cles:
        run([GIT_REEL, "--git-dir", str(piege), "config", k, x], env=d.genv())
    d.salir()
    jeton = section(d, d.env(copies=False, extra={"_CADRE_GIT_DIR": str(piege), "_CADRE_GIT_WORK_TREE": str(d.w)}), "stores")
    v = [] if aiguille in c.vu() else [f"résidu fermé ? {aiguille} n'a pas été exécuté (vu {c.vu()}) — amender SKILL, en-tête du hook et ce témoin"]
    v += [] if jeton == attendu else [f"résidu {quoi} : jeton {jeton!r}, attendu {attendu!r}"]
    return v + recens(d)


def nu_signature(base, texte=None):
    """Interrupteur `true` + signataire qui échoue, AU DÉPÔT NU : le hook ne pose PAS --no-gpg-sign (lecture de
    l'interrupteur au bon dépôt), le signataire est lancé, le commit échoue, l'index est défait (reset au bon dépôt)."""
    d = Depot(base, "nu-sans-parent", texte)
    marqueur = base / "signataire.lance"
    signataire = ecrire(base / "signataire.sh", f'#!/bin/sh\n: > "{marqueur}"\nexit 1\n', True)
    for k, val in (("cadre.signStateCommits", "true"), ("commit.gpgsign", "true"), ("gpg.program", str(signataire))):
        d.depot_nu("config", k, val)
    d.salir()
    jeton = section(d, d.env(), "stores")
    v = [] if jeton == "failed" else [f"signature : jeton {jeton!r}, attendu 'failed'"]
    if not marqueur.exists():
        v.append("signature : le signataire n'a pas été lancé (l'interrupteur du dépôt nu n'a pas été lu)")
    if d.depot_nu("diff", "--cached", "--name-only"):
        v.append("signature : index du dépôt nu sale après l'échec (le reset n'a pas visé le bon dépôt)")
    return v + recens(d)


def nu_mention(base, texte=None, inverse=False):
    """cas 63 : le dépôt NU demande la signature, le PARENT porte l'interrupteur `true` → mention « non signés » DITE.
    cas 64 (inverse) : le PARENT demande la signature, le NU non → AUCUNE mention."""
    d = Depot(base, "nu-sous-parent", texte)
    if inverse:
        d.g(["config", "commit.gpgsign", "true"], cwd=d.parent)
    else:
        d.depot_nu("config", "commit.gpgsign", "true")
        d.g(["config", "cadre.signStateCommits", "true"], cwd=d.parent)
    avant, avant_p = d.tete(), d.tete_parent()
    sortie = flux_externe(d, d.env())
    v = au_nu(d, "mention", "committed" if d.tete() != avant else "rien", avant, avant_p)
    if ("non signés" in sortie) is inverse:
        v.append(f"mention : « non signés » {'annoncée à tort' if inverse else 'absente'} dans {sortie[:100]!r}")
    return v


def nu_enfants(base, texte=None):
    """B-C5 : les copies ne sont rendues qu'aux appels git (sous-shell de `git_hote`) ; les ENFANTS du hook ne voient ni
    GIT_DIR ni GIT_WORK_TREE. Un faux `python3` du PATH et un faux `scripts/index-refresh.sh` journalisent leur env."""
    d = Depot(base, "nu-sous-parent", texte)
    journal = ecrire(base / "enfants.log", "")
    trace = 'printf \'%s\\037%s\\037%s\\n\' "${GIT_DIR-absent}" "${GIT_WORK_TREE-absent}" "$*" >> "' + str(journal) + '"\n'
    for nom in ("python3", "python"):
        ecrire(base / "stub-pylog" / nom, "#!/bin/sh\n" + trace + f'exec "{sys.executable}" "$@"\n', True)
    ecrire(d.w / ".agents/bin/specs_graph.py", "import sys\nsys.exit(0)\n")
    ecrire(d.w / "scripts/index-refresh.sh", "#!/bin/sh\nset -- index-refresh.sh\n" + trace)
    avant, avant_p = d.tete(), d.tete_parent()
    env = d.env()
    flux_externe(d, dict(env, PATH=f"{base / 'stub-pylog'}{os.pathsep}{env['PATH']}"))
    v = au_nu(d, "enfants", "committed" if d.tete() != avant else "rien", avant, avant_p)
    lignes = [(ligne.split("\x1f") + ["", ""])[:3] for ligne in journal.read_text().splitlines()]
    for nom, jetons in ENFANTS.items():
        vus = [(gd, gw) for gd, gw, args in lignes if all(j in args for j in jetons)]
        v += [] if vus else [f"enfants : {nom} jamais lancé (témoin à vide)"]
        v += [f"enfant {nom} voit GIT_DIR={gd!r} GIT_WORK_TREE={gw!r}" for gd, gw in vus if (gd, gw) != ("absent", "absent")]
    return v


ENFANTS = {"tasks.py commit-stores": ("tasks.py", "commit-stores"), "tasks.py commit-run-exports": ("tasks.py", "commit-run-exports"),
           "specs_graph.py": ("specs_graph.py",), "index-refresh.sh": ("index-refresh.sh",)}


def occupe(d: Depot):
    ecrire(d.parent / ".git" / "MERGE_HEAD", "0" * 40 + "\n")


def detache(d: Depot):
    d.g(["checkout", "-q", "--detach"], cwd=d.parent)


def pose(**kw):
    return lambda d: {k: str(getattr(d, v)) if v in ("n", "w") else v for k, v in kw.items()}


NU = {
    "nu-sous-parent/stores": lambda b, t=None: nu_flux(b, t, "nu-sous-parent", "stores"),
    "nu-sans-parent/stores": lambda b, t=None: nu_flux(b, t, "nu-sans-parent", "stores"),
    "nu-sous-parent/exports": lambda b, t=None: nu_flux(b, t, "nu-sous-parent", "exports"),
    "nu-sans-parent/exports": lambda b, t=None: nu_flux(b, t, "nu-sans-parent", "exports"),
    "nu/degrade": nu_degrade,
    "nu/sans-prefixe": lambda b, t=None: nu_sous_parent(b, t, "sans préfixe (hôte Codex/Copilot/Kimi)",
                                                          pose(GIT_DIR="n", GIT_WORK_TREE="w")),
    "nu/copie-vide": lambda b, t=None: nu_sous_parent(b, t, "copie vide (GIT_DIR='' hérité) : aucun commit nulle part",
                                                        pose(_CADRE_GIT_DIR=""), attendu="nothing"),
    "nu/preseance": nu_preseance,
    "nu/depot-piege": nu_depot_piege,
    "nu/parent-occupe": lambda b, t=None: nu_sous_parent(b, t, "parent occupé (MERGE_HEAD)", pose(_CADRE_GIT_DIR="n", _CADRE_GIT_WORK_TREE="w"), occupe),
    "nu/parent-detache": lambda b, t=None: nu_sous_parent(b, t, "parent détaché", pose(_CADRE_GIT_DIR="n", _CADRE_GIT_WORK_TREE="w"), detache),
    "nu/signature": nu_signature,
    "nu/mention": lambda b, t=None: nu_mention(b, t),
    "nu/mention-inverse": lambda b, t=None: nu_mention(b, t, inverse=True),
    "nu/enfants": nu_enfants,
    "nu/residu-filtre": lambda b, t=None: nu_residu(b, t, "filtre"),
    "nu/residu-gpg": lambda b, t=None: nu_residu(b, t, "gpg"),
}


@pytest.fixture(scope="session")
def nus(tmp_path_factory):
    bases = {nom: tmp_path_factory.mktemp("nu") for nom in NU}

    with cf.ThreadPoolExecutor(4) as ex:
        return dict(ex.map(lambda nom: (nom, NU[nom](bases[nom])), NU))


@pytest.mark.parametrize("nom", list(NU))
def test_bare_repo_restoration(nom, nus):
    assert not nus[nom], "\n".join(nus[nom])


# ---------------------------------------------------------------------------
# LA COUTURE : la jambe LUE dans les réglages, jouée par chaque enveloppe POSIX distincte
# ---------------------------------------------------------------------------
def reglages() -> tuple[Path, dict]:
    brut = os.environ.get("HOOK_HARDENING_SETTINGS")
    chemin = Path(brut) if brut else REGLAGES_VIVANTS
    if EN_CI and chemin.resolve() != REGLAGES_VIVANTS.resolve():
        pytest.fail(f"CI=true : HOOK_HARDENING_SETTINGS={brut} remplace {REGLAGES_VIVANTS} — refusé")
    if not chemin.is_file():
        if EN_CI and EST_LE_KIT:
            pytest.fail(f"ÉCHEC NOMMÉ — {chemin} absent sous CI=true dans le kit : la couture n'aurait rien à lire")
        pytest.skip(f"{chemin} absent (projet sans hôte Claude) : couture préfixe → hook non jouée")
    return chemin, json.loads(chemin.read_text(encoding="utf-8"))


def commande_hook(doc: dict) -> str:
    cmds = [h.get("command", "") for blocs in doc.get("hooks", {}).values() for b in blocs for h in b.get("hooks", [])
            if "/.agents/bin/post-task-done-index.sh" in h.get("command", "")]
    assert len(cmds) == 1, f"la jambe post-task-done-index doit être UNIQUE dans les réglages : {len(cmds)}"
    return cmds[0]


def temoin_couture(base: Path, canal: str, commande: str, shell="/bin/sh") -> list[str]:
    d, c = Depot(base, "nu-sous-parent"), Canari(base)
    avant, avant_p = d.tete(), d.tete_parent()
    d.salir()
    env = d.env({**c.env(canal), "GIT_DIR": str(d.n), "GIT_WORK_TREE": str(d.w)}, copies=False)
    p = run([shell, "-c", commande], env=env, inp=PAYLOAD, cwd=d.w)
    v = []
    if d.tete() == avant:
        v.append(f"couture / {canal} : aucun commit au dépôt nu (stdout {p.stdout[:80]!r})")
    if d.tete_parent() != avant_p:
        v.append(f"couture / {canal} : le dépôt PARENT a reçu le commit")
    if "stores commités" not in p.stdout:
        v.append(f"couture / {canal} : « stores commités » absent de {p.stdout[:100]!r}")
    return v + [f"couture / {canal} : canari écrit {x}" for x in c.vu()] + violations_recensement(d.appels(), {"status", "add", "commit"})


@pytest.fixture(scope="session")
def couture(tmp_path_factory, etalon):
    chemin, doc = reglages()
    cmd = commande_hook(doc)
    cellules = [(s, c, tmp_path_factory.mktemp(f"seam{c}")) for s in SHELLS for c in CANAUX if etalon[c] is None]
    with cf.ThreadPoolExecutor(3) as ex:
        return {(s, c): v for (s, c, _), v in zip(cellules, ex.map(lambda x: temoin_couture(x[2], x[1], cmd, x[0]), cellules))}


@pytest.mark.parametrize("canal", CANAUX)
@pytest.mark.parametrize("shell", SHELLS)
def test_prefix_hands_private_copy_to_hook(shell, canal, etalon, couture):
    exiger_canal(etalon[canal], canal)
    assert not couture[(shell, canal)], "\n".join(couture[(shell, canal)])


# ---------------------------------------------------------------------------
# MUTANTS : chaque témoin PEUT rougir
# ---------------------------------------------------------------------------
def muter(texte: str, ancien: str, nouveau: str) -> str:
    assert texte.count(ancien) == 1, (texte.count(ancien), ancien[:80])
    return texte.replace(ancien, nouveau, 1)


SITES = {  # nom : (ancre du site avec la fonction, ancre nue)
    "rev-parse --git-dir": ('  git_hote -C "$dir" rev-parse --git-dir', '  git -C "$dir" rev-parse --git-dir'),
    "rev-parse --show-toplevel (exports)": ('top="$(git_hote -C "$dir" rev-parse --show-toplevel', 'top="$(git -C "$dir" rev-parse --show-toplevel'),
    "rev-parse --absolute-git-dir": ('gitdir="$(git_hote -C "$dir" rev-parse --absolute-git-dir', 'gitdir="$(git -C "$dir" rev-parse --absolute-git-dir'),
    "symbolic-ref": ('  git_hote -C "$dir" symbolic-ref', '  git -C "$dir" symbolic-ref'),
    "status": ('$(git_hote "${gx[@]}" status', '$(git "${gx[@]}" status'),
    "add": ('  git_hote "${gx[@]}" add', '  git "${gx[@]}" add'),
    "config interrupteur (commit)": ('[ "$(git_hote -C "$dir" config --bool --get "$SIGN_SWITCH_KEY"', '[ "$(git -C "$dir" config --bool --get "$SIGN_SWITCH_KEY"'),
    "commit": ('  if git_hote -C "$dir" "${commit_cmd[@]}"', '  if git -C "$dir" "${commit_cmd[@]}"'),
    "reset": ('    git_hote -C "$dir" reset', '    git -C "$dir" reset'),
    "rev-parse --show-toplevel (racine)": ('DIR="$(git_hote rev-parse --show-toplevel', 'DIR="$(git rev-parse --show-toplevel'),
    "config commit.gpgsign (mention)": ('if [ "$(git_hote -C "$DIR" config --bool --get commit.gpgsign', 'if [ "$(git -C "$DIR" config --bool --get commit.gpgsign'),
    "config interrupteur (mention)": ('&& [ "$(git_hote -C "$DIR" config --bool --get "$SIGN_SWITCH_KEY"', '&& [ "$(git -C "$DIR" config --bool --get "$SIGN_SWITCH_KEY"'),
    "status (non tentés)": ('[ -n "$(git_hote -C "$DIR" -c "$EXCLUDES_OFF" status', '[ -n "$(git -C "$DIR" -c "$EXCLUDES_OFF" status'),
}
EXEC_ARG = "exec git -c core.fsmonitor=false -c core.hooksPath=/dev/null"
#: B-C5 : la copie privée EXPORTÉE à un enfant du hook (forme du mutant MX-ENFANTS-bis de la critique B, un site à la fois).
EXPORT_ENFANT = '[ "${_CADRE_GIT_DIR+x}" = x ] && export GIT_DIR="${_CADRE_GIT_DIR}"; [ "${_CADRE_GIT_WORK_TREE+x}" = x ] && export GIT_WORK_TREE="${_CADRE_GIT_WORK_TREE}"; '
# (nom, ancien, nouveau, [(témoin, aiguille attendue dans la violation)])
MUTANTS = [
    ("MS1 -c core.fsmonitor=false retiré", EXEC_ARG, "exec git -c core.hooksPath=/dev/null",
     [("canari", "stores", "P", "canari écrit : fsmonitor"), ("canari", "stores", "C", "canari écrit : fsmonitor"),
      ("canari", "stores", "G", "canari écrit : fsmonitor"), ("nu", "nu/depot-piege", None, "canari écrit fsmonitor")]),
    ("MS2 -c core.hooksPath=/dev/null retiré", EXEC_ARG, "exec git -c core.fsmonitor=false",
     [("canari", "stores", "P", "canari écrit : hook"), ("canari", "stores", "C", "canari écrit : hook"),
      ("canari", "stores", "G", "canari écrit : hook"), ("nu", "nu/depot-piege", None, "canari écrit hook")]),
    ("MS3 status nu", *SITES["status"], [("canari", "stores", "P", "canari écrit : fsmonitor")]),
    ("MS4 add nu", *SITES["add"], [("canari", "stores", "P", "canari écrit : fsmonitor")]),
    ("MS5 commit nu", *SITES["commit"], [("canari", "stores", "P", "canari écrit : hook")]),
    ("MS6 reset nu", *SITES["reset"], [("canari", "echec", "P", "canari écrit : fsmonitor")]),
    ("MS7 status (non tentés) nu", *SITES["status (non tentés)"], [("canari", "degrade", "P", "git NU")]),
    ("MS8 rev-parse --git-dir nu", *SITES["rev-parse --git-dir"], [("canari", "stores", "P", "git NU"), ("nu", "nu-sans-parent/stores", None, "commit attendu")]),
    ("MS9 rev-parse --show-toplevel (exports) nu", *SITES["rev-parse --show-toplevel (exports)"],
     [("canari", "exports", "P", "git NU"), ("nu", "nu-sans-parent/exports", None, "commit attendu")]),
    ("MS10 rev-parse --absolute-git-dir nu", *SITES["rev-parse --absolute-git-dir"], [("canari", "stores", "P", "git NU"), ("nu", "nu/parent-occupe", None, "commit attendu")]),
    ("MS11 symbolic-ref nu", *SITES["symbolic-ref"], [("canari", "stores", "P", "git NU"), ("nu", "nu/parent-detache", None, "commit attendu")]),
    ("MS12 config interrupteur (commit) nu", *SITES["config interrupteur (commit)"], [("canari", "stores", "P", "git NU"), ("nu", "nu/signature", None, "signataire")]),
    ("MS13 rev-parse --show-toplevel (racine) nu", *SITES["rev-parse --show-toplevel (racine)"], [("canari", "sans-racine", "P", "git NU")]),
    ("MS14 config commit.gpgsign (mention) nu", *SITES["config commit.gpgsign (mention)"], [("canari", "externe", "P", "git NU"), ("nu", "nu/mention", None, "non signés"),
                                                ("nu", "nu/mention-inverse", None, "annoncée à tort")]),
    ("MS15 config interrupteur (mention) nu", *SITES["config interrupteur (mention)"], [("nu", "nu/mention", None, "git NU"), ("nu", "nu/mention", None, "non signés")]),
    ("MS16 git_hote purge GIT_CONFIG_PARAMETERS/COUNT (safe.directory perdu)", EXEC_ARG,
     "exec env -u GIT_CONFIG_PARAMETERS -u GIT_CONFIG_COUNT git -c core.fsmonitor=false -c core.hooksPath=/dev/null",
     [("safe", "-", "P", "safe.directory perdu"), ("safe", "-", "C", "safe.directory perdu")]),
    ("MR1 restauration retirée (GIT_DIR)", 'GIT_DIR="$_CADRE_GIT_DIR"', 'GIT_DIR="${GIT_DIR-}"', [("nu", "nu-sans-parent/stores", None, "commit attendu")]),
    ("MR2 restauration retirée (GIT_WORK_TREE)", 'GIT_WORK_TREE="$_CADRE_GIT_WORK_TREE"', 'GIT_WORK_TREE="${GIT_WORK_TREE-}"',
     [("nu", "nu-sans-parent/stores", None, "commit attendu")]),
    ("MR3 +x → :+x (le vide est perdu)", '[ -n "${_CADRE_GIT_DIR+x}" ]', '[ -n "${_CADRE_GIT_DIR:+x}" ]', [("nu", "nu/copie-vide", None, "copie vide")]),
    ("MR6 la copie ne l'emporte plus sur un GIT_DIR ambiant (préséance)", '[ -n "${_CADRE_GIT_DIR+x}" ]',
     '[ -n "${_CADRE_GIT_DIR+x}" ] && [ -z "${GIT_DIR+x}" ]', [("nu", "nu/preseance", None, "préséance")]),
    ("MX1 copie exportée à tasks.py commit-stores", 'TOKEN="$("$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-stores',
     'TOKEN="$(' + EXPORT_ENFANT + '"$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-stores',
     [("nu", "nu/enfants", None, "enfant tasks.py commit-stores voit GIT_DIR")]),
    ("MX2 copie exportée à tasks.py commit-run-exports", 'TOKEN2="$("$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-run-exports',
     'TOKEN2="$(' + EXPORT_ENFANT + '"$PY" "$DIR/.agents/bin/tasks.py" --root "$DIR" commit-run-exports',
     [("nu", "nu/enfants", None, "enfant tasks.py commit-run-exports voit GIT_DIR")]),
    ("MX3 copie exportée à specs_graph.py", '  "$PY" "$DIR/.agents/bin/specs_graph.py" --root "$DIR" generate >/dev/null 2>&1 || true',
     '  ( ' + EXPORT_ENFANT + '"$PY" "$DIR/.agents/bin/specs_graph.py" --root "$DIR" generate >/dev/null 2>&1 ) || true',
     [("nu", "nu/enfants", None, "enfant specs_graph.py voit GIT_DIR")]),
    ("MX4 copie exportée à index-refresh.sh", 'OUT="$(bash "$DIR/scripts/index-refresh.sh" 2>&1)"',
     'OUT="$(' + EXPORT_ENFANT + 'bash "$DIR/scripts/index-refresh.sh" 2>&1)"',
     [("nu", "nu/enfants", None, "enfant index-refresh.sh voit GIT_DIR")]),
    ("MR7 la classe `filter.<nom>.clean` fermée (core.attributesFile=/dev/null)", EXEC_ARG,
     EXEC_ARG + " -c core.attributesFile=/dev/null", [("nu", "nu/residu-filtre", None, "résidu fermé")]),
    ("MR8 la classe `gpg.program` fermée (gpg.program=false)", EXEC_ARG,
     EXEC_ARG + " -c gpg.program=false", [("nu", "nu/residu-gpg", None, "résidu fermé")]),
    ("MR5 restauration inconditionnelle (hôte sans préfixe cassé)", '[ -n "${_CADRE_GIT_DIR+x}" ]', "true", [("nu", "nu/sans-prefixe", None, "sans préfixe")]),
]


def jouer_temoin(base: Path, texte: str, spec) -> list[str]:
    genre, a, b, _ = spec
    if genre == "canari":
        return temoin_canari(base, b, a, texte)
    if genre == "safe":
        return temoin_safe(base, b, texte)
    return NU[a](base, texte)


@pytest.fixture(scope="session")
def mutes(tmp_path_factory, etalon):
    travaux = []
    base_texte = HOOK_VIVANT.read_text(encoding="utf-8")
    for nom, ancien, nouveau, temoins in MUTANTS:
        texte = muter(base_texte, ancien, nouveau)
        for spec in temoins:
            if spec[0] in ("canari", "safe") and etalon[spec[2]] is not None:
                continue
            travaux.append((nom, texte, spec, tmp_path_factory.mktemp("mut")))

    def une(t):
        nom, texte, spec, base = t
        v = jouer_temoin(base, texte, spec)
        return None if v == ["BOUTON_MUET"] else (nom, spec, v)  # bouton muet : déjà dit (échec sous CI+kit) par son test

    with cf.ThreadPoolExecutor(4) as ex:
        return [r for r in ex.map(une, travaux) if r is not None]


def test_mutants_are_killed(mutes):
    survivants = [f"{nom} : témoin {spec[:3]} vert (aiguille « {spec[3]} » absente de {v[:2]})"
                  for nom, spec, v in mutes if not any(spec[3] in x for x in v)]
    assert mutes, "aucun mutant joué"
    assert not survivants, "mutants survivants :\n" + "\n".join(survivants)


def test_seam_mutants_are_killed(tmp_path_factory, etalon):
    """B-C2 : renommer les copies d'UN SEUL côté, ou retirer le bloc de copie du préfixe, rougit la couture."""
    chemin, doc = reglages()
    cmd = commande_hook(doc)
    exiger_canal(etalon["P"], "P")
    survivants = []
    for nom, mut in (("renommage préfixe seul _CADRE_GIT_DIR→_CADRE_GIT_REPO", cmd.replace("_CADRE_GIT_DIR", "_CADRE_GIT_REPO")),
                     ("renommage préfixe seul _CADRE_GIT_WORK_TREE→_CADRE_GIT_WT", cmd.replace("_CADRE_GIT_WORK_TREE", "_CADRE_GIT_WT")),
                     ("bloc de copie retiré", re.sub(r"unset _CADRE_GIT_DIR _CADRE_GIT_WORK_TREE; .*?esac; (?=unset BASH_ENV)", "", cmd, count=1))):
        assert mut != cmd, f"mutant {nom} sans effet : ancre de la jambe absente"
        if not temoin_couture(tmp_path_factory.mktemp("sm"), "P", mut):
            survivants.append(nom)
    assert not survivants, "mutants de couture survivants : " + ", ".join(survivants)


# ---------------------------------------------------------------------------
# LES VERBES QUI EXÉCUTENT core.fsmonitor : relevé « AU MOINS », sondé à deux faces, épinglé au SKILL (B-C2)
# ---------------------------------------------------------------------------
VERBES_FSMONITOR = (("status", ["status", "--porcelain"]), ("add", ["add", "a.txt"]), ("commit", ["commit", "--allow-empty", "-qm", "x"]),
                    ("reset", ["reset", "-q", "--", "a.txt"]), ("ls-files", ["ls-files"]), ("diff", ["diff", "--quiet", "HEAD"]),
                    ("diff-index", ["diff-index", "--quiet", "HEAD"]), ("check-ignore", ["check-ignore", "-q", "a.txt"]),
                    ("grep", ["grep", "-l", "a"]), ("update-index --refresh", ["update-index", "--refresh"]))
#: Verbes TÉMOINS qui ne l'exécutent pas (mesuré git 2.54/2.55) : la sonde doit savoir répondre non.
VERBES_SANS = (("rev-parse", ["rev-parse", "HEAD"]), ("config", ["config", "--get", "user.name"]),
               ("symbolic-ref", ["symbolic-ref", "-q", "HEAD"]))


def phrase_verbes() -> str:
    noms = [f"`{n}`" for n, _ in VERBES_FSMONITOR]
    return "`core.fsmonitor` au moins à " + ", ".join(noms[:-1]) + " et " + noms[-1]


def test_fsmonitor_verbs_listed(tmp_path_factory, etalon):
    """Chaque verbe de la liste EXÉCUTE le canari posé par P, aucun verbe témoin ne le fait, et le SKILL porte la phrase."""
    exiger_canal(etalon["P"], "P")
    base = tmp_path_factory.mktemp("verbes")
    c, r = Canari(base), base / "r"
    r.mkdir()
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(base), "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": str(ecrire(base / "g", SANS_MAINTENANCE + "[user]\n\temail = t@t\n\tname = t\n"))}
    ecrire(r / "a.txt", "a\n")
    for argv in (["init", "-q"], ["add", "a.txt"], ["commit", "-qm", "init"]):
        assert run([GIT_REEL, *argv], env=env, cwd=r).returncode == 0, argv
    v = []
    for nom, argv in VERBES_FSMONITOR + VERBES_SANS:
        c.log.write_text("")
        run([GIT_REEL, *argv], env={**env, **c.env("P")}, cwd=r)
        if ("fsmonitor" in c.vu()) is not ((nom, argv) in VERBES_FSMONITOR):
            v.append(f"git {nom} : fsmonitor {'NON ' if (nom, argv) in VERBES_FSMONITOR else ''}exécuté, contraire au relevé")
    if not SKILL_GARDES.is_file():
        if EN_CI and EST_LE_KIT:
            pytest.fail(f"ÉCHEC NOMMÉ — {SKILL_GARDES} absent sous CI=true dans le kit")
        pytest.skip(f"{SKILL_GARDES} absent : épingle de la liste non jouée")
    if phrase_verbes() not in SKILL_GARDES.read_text(encoding="utf-8"):
        v.append(f"SKILL guardrails : phrase absente ou divergente — {phrase_verbes()}")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# RÉSIDUS ÉPINGLÉS : la classe n'est PAS fermée — le jour où elle l'est, ce test rougit
# ---------------------------------------------------------------------------
def test_named_residues(tmp_path_factory, etalon):
    """`filter.<nom>.clean` posé par l'environnement à l'`add`, et `gpg.program` quand l'interrupteur
    est posé par l'environnement, EXÉCUTENT encore du code sous le hook blindé (mesuré, git 2.54/2.55)."""
    exiger_canal(etalon["P"], "P")
    base = tmp_path_factory.mktemp("res")
    d, c = Depot(base, "normal"), Canari(base)
    d.salir()
    paires = [("core.attributesFile", str(c.attributs)), ("filter.canari.clean", str(c.filtre))]
    env = d.env({"GIT_CONFIG_PARAMETERS": " ".join(f"'{k}={v}'" for k, v in paires)})
    section(d, env, "stores")
    vus = c.vu()
    assert "filter-clean" in vus, f"résidu fermé ? filter.clean n'a pas été exécuté : {vus} — amender SKILL et ce test"
    c2 = Canari(tmp_path_factory.mktemp("res2"))
    d2 = Depot(tmp_path_factory.mktemp("res3"), "normal")
    d2.salir()
    paires = [("cadre.signStateCommits", "true"), ("commit.gpgsign", "true"), ("gpg.program", str(c2.signataire))]
    section(d2, d2.env({"GIT_CONFIG_PARAMETERS": " ".join(f"'{k}={v}'" for k, v in paires)}), "stores")
    assert "gpg-program" in c2.vu(), f"résidu fermé ? gpg.program n'a pas été exécuté : {c2.vu()} — amender SKILL et ce test"
