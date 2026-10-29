#!/usr/bin/env python3
"""LE KIT INSTALLÉ PAR `uv tool install`, DANS DES RACINES JETABLES (T-01M51QMKSGANKPZ5DWTFWZKX56).

POURQUOI CE BANC. La tâche d'installation réelle sur le poste du pilote est
T-00000989. Avant elle, il faut la preuve que la forme d'installation du README
(une roue installée en outil par uv, la commande `cadre`) tourne de bout en bout SANS
rien écrire chez l'utilisateur. La recette a été mesurée à la main le
2026-10-16 (essai isolé, passage 2 « ISOLATION PROUVÉE ») ; ce banc la rejoue à
chaque porte. Il ne doublonne pas ses voisins : `test_cadre_prefix_install.py`
installe sous un préfixe en lecture seule mais bâtit la roue depuis le dépôt
avec le HOME réel ; `test_cadre_cmd_tasks_wheel.py` installe dans un venv par
`uv pip`. Aucun des deux ne joue `uv tool install` avec HOME, cache uv et XDG
jetables, ni ne bâtit depuis un clone.

CE QU'IL FAIT, une fois par exécution (`setUpClass`), sous une base jetable :
  1. un clone `--depth 1` de CET arbre (HEAD), sparse sur les dossiers que la
     roue embarque (lus dans le `pyproject.toml` du clone) : seuls les
     fichiers COMMITÉS entrent dans la roue ;
  2. la roue bâtie depuis le clone, hors ligne (`uv build --wheel --offline`) ;
  3. l'installation hors ligne et sans index par `uv tool install <roue>`,
     dans un environnement où HOME, UV_TOOL_DIR, UV_TOOL_BIN_DIR,
     UV_CACHE_DIR, XDG_CONFIG_HOME, XDG_STATE_HOME, XDG_CACHE_HOME,
     XDG_DATA_HOME, TMPDIR et PYTHONPYCACHEPREFIX visent la base, sans
     aucun `CADRE_*`, `PYTHON*` ni `GIT_*` hérité (liste blanche de
     `test_cadre_cli_installed.py`) ;
  4. `cadre --version`, puis, dans un projet `git init` vierge borné par
     GIT_CEILING_DIRECTORIES, `cadre paths --json` et `cadre tasks list` ;
     enfin `cadre init`, le seul écrivain d'état machine du banc (ni `paths`
     ni `tasks list` n'en écrivent : mesuré, le projet ne porte que `.git`
     après `tasks list`).

CE QU'IL ASSERTE :
  (a) `cadre` résout sous `<base>/bin`, et `--version` rend 0 ;
  (b) `cadre tasks list` rend 0 dans le projet vierge et affiche le board ;
  (c) TÉMOIN POSITIF : chaque racine que uv (`tool dir`, `tool dir --bin`,
      `cache dir`) et cadre (`PKG_ROOT`, `CONFIG_HOME`, `STATE_HOME`,
      `STATE_PROJECT`) rapportent dans cet environnement est SOUS la base, et
      `uv tool list` y voit `cadre-kit` ;
  (d) TÉMOIN NÉGATIF, sur les surfaces RÉELLES que chaque outil viserait sans
      redirection — demandées aux outils eux-mêmes dans l'environnement
      hérité, jamais devinées : l'entrée `cadre-kit` du dossier d'outils uv et
      l'exécutable `cadre` du dossier bin uv (relevés lstat avant le build,
      comparés après les commandes ; bytecode exclu et dossiers relevés par
      leur seul mode, pour qu'un vrai `cadre` lancé pendant le banc, qui écrit
      ses `.pyc` dans son venv, ne le fasse pas rougir à tort), et l'état
      machine de CE projet : PRÉSENT sous la base après `cadre init`
      (non-vacuité), ABSENT sous chaque état réel de cadre — celui de
      l'environnement hérité ET celui par défaut sans CADRE_STATE_DIR, que
      le conftest racine pose sous pytest vers une racine de session.

SAUTS ANNONCÉS (jamais un rouge faute d'outil, jamais le réseau) : uv absent,
git absent, projet adoptant (marqueur
`.agents/IS_THE_KIT`), puis au build : backend introuvable dans le cache uv
(prédicat IMPORTÉ de `test_cadre_init_surfaces.py`), cache uv non
inscriptible, délai dépassé. Tout autre échec — clone, build, installation,
commande — est ROUGE avec son journal. COUVERTURE : un poste au cache uv chaud ;
la CI n'installe pas uv et y saute.

RÉSIDU NOMMÉ — LE BUILD N'EST PAS ISOLÉ DU CACHE UV. Le backend `hatchling`
doit venir de quelque part et le banc ne va jamais sur le réseau : le build
lit le cache uv HÉRITÉ (`env_uv`, comme `batir_wheel`), et y pose un
environnement de build temporaire, retiré après (mesuré le 2026-10-16 : sur
trois niveaux du cache, seule la date de `builds-v0/` change). Un
UV_CACHE_DIR jetable au build ferait sauter le
banc à chaque exécution (mesuré à la main : `hatchling was not found in the
cache`). L'installation et les commandes, elles, ont leur cache jetable.

CE QU'IL NE MESURE PAS, écrit pour ne pas être relu comme couvert :
  * l'absence UNIVERSELLE d'écriture : seules les surfaces de (d) sont
    relevées. Le bytecode que l'interpréteur PARTAGÉ écrirait dans sa
    bibliothèque standard est renvoyé sous la base par PYTHONPYCACHEPREFIX,
    mais n'est pas relevé : des tranches parallèles de la porte, qui
    partagent cet interpréteur, y écrivent aussi ;
  * la configuration de cadre : aucune commande du banc n'en écrit (mesuré :
    CONFIG_HOME absent après `cadre init`), un relevé n'y pourrait pas
    rougir — seul (c) dit qu'elle vise la base ;
  * Python < 3.11 n'est PAS un saut : les voisins importés lisent `tomllib`
    au niveau module, et le banc ne se collecte pas sous un interpréteur
    plus ancien ; la porte du kit tourne sous un Python qui le porte ;
  * le dépôt source : le clone le lit sans y écrire, rien ne le relève ;
  * Windows (la CI saute faute de uv) ; une installation depuis un index ;
    ce que `cadre init` pose dans le projet ; la désinstallation.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# IMPORTÉS TELS QUELS — des noms seuls, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_cli_installed import env_blanche  # noqa: E402
from test_cadre_init_surfaces import (  # noqa: E402
    DELAI_BUILD,
    _est_un_backend_non_resolvable,
)
from test_cadre_pkg_root import EST_LE_KIT, UV, env_uv  # noqa: E402
from test_cadre_prefix_install import _lancer, hors_de, inventaire  # noqa: E402

GIT = shutil.which("git")

#: Le résolveur du kit, chargé PAR CHEMIN (patron v3prep) : le paquet `cadre` du
#: clone est lu où il vit, `.agents/vendor/cadre/` d'abord, `src/cadre/` sinon.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_uv_tool_install_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)

#: Le nom du venv d'outil que `uv tool install` crée : celui de la distribution.
OUTIL = "cadre-kit"

PAS_MESURE = "l'installation du kit par uv tool install n'est PAS mesuree par cette execution"
SAUT_UV = f"SAUT ANNONCE : `uv` absent du PATH — {PAS_MESURE}"
SAUT_GIT = f"SAUT ANNONCE : `git` absent du PATH, aucun clone jetable possible — {PAS_MESURE}"
SAUT_MARQUEUR = ("SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet adoptant, pas "
                 f"le kit) — la roue batie serait celle d'un autre projet — {PAS_MESURE}")
SAUT_BACKEND = ("SAUT ANNONCE : `uv build --offline` ne trouve pas le backend de build "
                "(hatchling) dans le cache uv — cache froid, et ce banc ne va jamais sur "
                f"le reseau — {PAS_MESURE}")
SAUT_CACHE = f"SAUT ANNONCE : cache uv non inscriptible au build — {PAS_MESURE}"
SAUT_DELAI = (f"SAUT ANNONCE : `uv build --offline` n'a pas rendu la main en {DELAI_BUILD} s "
              f"(verrou du cache uv, ou poste sature) — {PAS_MESURE}")

#: Configuration git des appels du banc : rien de l'utilisateur, aucun hook.
_GIT_C = ("-c", "init.defaultBranch=main", "-c", f"core.hooksPath={os.devnull}")

#: L'état machine RÉEL de cadre, demandé à `cadre.paths` du CLONE dans
#: l'environnement hérité. `-I -B` : ni `PYTHON*`, ni bytecode écrit.
SONDE_RACINES_REELLES = """\
import json, sys
sys.path.insert(0, sys.argv[1])
from cadre.paths import state_home
print(json.dumps({"STATE_HOME": str(state_home())}))
"""


def _sans_bytecode(rel: str) -> bool:
    """Vrai pour une entrée que l'interpréteur écrit en LANÇANT le code :
    un `__pycache__` et ce qu'il contient, ou un `.pyc`."""
    parties = PurePosixPath(rel).parts
    return "__pycache__" not in parties and not rel.endswith(".pyc")


def releve(chemin: Path) -> dict[str, tuple[int, int, int]] | None:
    """`None` si `chemin` n'existe pas ; sinon son propre lstat (clé `.`) et,
    pour un dossier, l'inventaire de ce qu'il contient. Un lien est relevé,
    jamais suivi. LE BYTECODE EST EXCLU, et un dossier ne garde que son mode :
    un vrai `cadre` lancé pendant le banc écrit ses `.pyc` dans son venv, et la
    date du dossier qui reçoit un `__pycache__` neuf change — ni l'un ni
    l'autre n'est une installation."""
    try:
        st = os.lstat(chemin)
    except FileNotFoundError:
        return None
    vu = {".": (st.st_size, st.st_mtime_ns, st.st_mode)}
    if stat.S_ISDIR(st.st_mode):
        vu.update((rel, (0, 0, mode) if stat.S_ISDIR(mode) else (taille, date, mode))
                  for rel, (taille, date, mode) in inventaire(chemin).items()
                  if _sans_bytecode(rel))
        vu["."] = (0, 0, st.st_mode)
    return vu


def dossiers_de_la_roue(manifeste: str) -> list[str]:
    """Les dossiers que la roue embarque, lus dans le texte du manifeste :
    `packages` tels quels, et le dossier parent de chaque source
    `force-include`. Liste vide si la table manque : le clone reste alors
    complet, jamais amputé en silence."""
    try:
        roue = tomllib.loads(manifeste)["tool"]["hatch"]["build"]["targets"]["wheel"]
    except (KeyError, TypeError, tomllib.TOMLDecodeError):
        return []
    chemins = [PurePosixPath(p) for p in [*roue.get("packages", []), *roue.get("force-include", {})]]
    return sorted({str(p.parent if p.suffix else p) for p in chemins})


def _executable(dossier: Path, nom: str) -> Path:
    """`<dossier>/<nom>`, ou `<nom>.exe` sous Windows."""
    windows = dossier / f"{nom}.exe"
    return windows if windows.is_file() else dossier / nom


def _env_git() -> dict[str, str]:
    """Liste blanche, sans configuration git globale ni système."""
    return env_blanche(os.environ) | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _exiger(r: subprocess.CompletedProcess, quoi: str) -> subprocess.CompletedProcess:
    if r.returncode != 0:
        raise AssertionError(f"{quoi} en echec (rc={r.returncode}) :\n{r.stdout}{r.stderr}")
    return r


def env_jetable(base: Path) -> dict[str, str]:
    """L'environnement de l'installation et des commandes : la liste blanche,
    puis chaque racine que uv, cadre, Python ou git écriraient, sous `base`."""
    env = env_blanche(os.environ)
    env.update({
        "HOME": str(base / "home"),
        "TMPDIR": str(base / "tmp"),
        "UV_TOOL_DIR": str(base / "outils"),
        "UV_TOOL_BIN_DIR": str(base / "bin"),
        "UV_CACHE_DIR": str(base / "cache-uv"),
        "UV_NO_CONFIG": "1",
        "UV_OFFLINE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
        "XDG_CONFIG_HOME": str(base / "xdg" / "config"),
        "XDG_STATE_HOME": str(base / "xdg" / "state"),
        "XDG_CACHE_HOME": str(base / "xdg" / "cache"),
        "XDG_DATA_HOME": str(base / "xdg" / "data"),
        "PYTHONPYCACHEPREFIX": str(base / "pycache"),
        "GIT_CEILING_DIRECTORIES": str(base),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    env["PATH"] = os.pathsep.join([str(base / "bin"), env.get("PATH", "")])
    return env


def cloner(base: Path) -> Path:
    """Clone `--depth 1` de HEAD, sparse sur les dossiers de la roue ; HEAD du
    clone vérifié égal à celui de l'arbre. Tout échec est ROUGE."""
    clone = base / "clone"
    env = _env_git()
    _exiger(_lancer([GIT, *_GIT_C, "clone", "-q", "--depth", "1", "--sparse", "--",
                     ROOT.as_uri(), str(clone)], base, env, "git clone"), "git clone")
    dossiers = dossiers_de_la_roue((clone / "pyproject.toml").read_text(encoding="utf-8"))
    if dossiers:
        _exiger(_lancer([GIT, "-C", str(clone), "sparse-checkout", "add", *dossiers], base, env,
                        "git sparse-checkout"), "git sparse-checkout")
    else:
        _exiger(_lancer([GIT, "-C", str(clone), "sparse-checkout", "disable"], base, env,
                        "git sparse-checkout disable"), "git sparse-checkout disable")
    tetes = [_exiger(_lancer([GIT, "-C", str(d), "rev-parse", "HEAD"], base, env, "rev-parse"),
                     "git rev-parse").stdout.strip() for d in (ROOT, clone)]
    if tetes[0] != tetes[1]:
        raise AssertionError(f"le clone ne porte pas HEAD de l'arbre : {tetes}")
    return clone


def batir_depuis(clone: Path, sortie: Path) -> Path:
    """`uv build --wheel --offline` depuis le clone, cache uv HÉRITÉ (résidu
    nommé en tête), bytecode du build renvoyé sous la base. Trois sauts
    annoncés ; tout autre échec est ROUGE."""
    env = env_uv() | {"UV_OFFLINE": "1",
                      "PYTHONPYCACHEPREFIX": str(sortie.parent / "pycache-build")}
    argv = [UV, "build", "--wheel", "--offline", "--python", sys.executable,
            "--out-dir", str(sortie), str(clone)]
    try:
        r = subprocess.run(argv, cwd=str(sortie.parent), env=env, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=DELAI_BUILD, check=False)
    except subprocess.TimeoutExpired:
        raise unittest.SkipTest(SAUT_DELAI) from None
    journal = r.stdout + r.stderr
    if r.returncode != 0 and "Failed to initialize cache" in journal:
        raise unittest.SkipTest(SAUT_CACHE)
    if r.returncode != 0 and _est_un_backend_non_resolvable(journal):
        raise unittest.SkipTest(SAUT_BACKEND)
    if r.returncode != 0:
        raise AssertionError(f"uv build en echec (rc={r.returncode}) :\n{journal}")
    roues = sorted(sortie.glob("cadre_kit-*.whl"))
    if len(roues) != 1:
        raise AssertionError(f"une seule roue `cadre_kit-*.whl` attendue, vu {roues} :\n{journal}")
    return roues[0]


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_MARQUEUR)
class UvToolInstallJetableTests(unittest.TestCase):
    """Clone, roue, `uv tool install` et commandes, tout sous une base jetable."""

    @classmethod
    def setUpClass(cls):
        if GIT is None:
            raise unittest.SkipTest(SAUT_GIT)
        cls.base = Path(tempfile.mkdtemp(prefix="cadre-uvtool-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        if cls.base.is_relative_to(ROOT):
            raise AssertionError(f"TMPDIR est sous le depot ({cls.base}) : « hors de "
                                 "toute source » ne discriminerait plus")
        clone = cloner(cls.base)
        parent_cadre = _VENDOR.parent_import(clone, "cadre")
        if parent_cadre is None:
            raise AssertionError("le clone ne porte le paquet cadre ni sous .agents/vendor "
                                 f"ni sous src : {clone}")

        # Les surfaces RÉELLES, demandées aux outils dans l'environnement hérité.
        herite = dict(os.environ)
        uv_reel = {cle: Path(_exiger(_lancer([UV, "tool", "dir", *opt], cls.base, herite,
                                              f"uv tool dir {' '.join(opt)}"), "uv tool dir")
                             .stdout.strip())
                   for cle, opt in (("outils", ()), ("bin", ("--bin",)))}
        # DEUX états réels : celui de l'environnement hérité, et celui par défaut
        # SANS `CADRE_STATE_DIR` — sous pytest, le conftest racine pose cette
        # variable vers une racine de SESSION, et le seul hérité manquerait
        # `XDG_STATE_HOME` ou `~/.local/state/cadre`, l'état de l'utilisateur.
        sans_variable = {k: v for k, v in herite.items() if k != "CADRE_STATE_DIR"}
        cls.etats_reels = sorted({json.loads(_exiger(_lancer(
            [sys.executable, "-I", "-B", "-c", SONDE_RACINES_REELLES, str(parent_cadre)],
            cls.base, env, "etat reel de cadre"), "etat reel de cadre").stdout)["STATE_HOME"]
            for env in (herite, sans_variable)})
        cls.surfaces = {
            "outil uv reel": uv_reel["outils"] / OUTIL,
            "executable uv reel": _executable(uv_reel["bin"], "cadre"),
        }
        cls.avant = {nom: releve(p) for nom, p in cls.surfaces.items()}

        roue = batir_depuis(clone, cls.base / "dist")

        cls.env = env_jetable(cls.base)
        for cle in ("HOME", "TMPDIR"):
            Path(cls.env[cle]).mkdir(parents=True)
        # La cible reste sur la ligne du verbe (lisibilité ; le juge lit les lignes qui nomment cadre
        # ou portent un fragment uv/uvx, et celle qui les précède dans un pli).
        cls.installation = _lancer([UV, "tool", "install", str(roue), "--no-config", "--offline",
                                    "--no-index", "--python", sys.executable],
                                   cls.base, cls.env, "uv tool install")
        _exiger(cls.installation, "uv tool install")
        cls.commande = _executable(cls.base / "bin", "cadre")

        cls.version = _lancer([str(cls.commande), "--version"], cls.base, cls.env,
                              "cadre --version")
        cls.projet = cls.base / "projet"
        cls.projet.mkdir()
        _exiger(_lancer([GIT, *_GIT_C, "init", "-q"], cls.projet, cls.env, "git init"), "git init")
        cls.paths = _lancer([str(cls.commande), "paths", "--json"], cls.projet, cls.env,
                            "cadre paths --json")
        cls.tasks = _lancer([str(cls.commande), "tasks", "list"], cls.projet, cls.env,
                            "cadre tasks list")
        # L'ÉCRIVAIN D'ÉTAT, joué APRÈS `tasks list` (projet encore vierge) : ni
        # `paths` ni `tasks list` n'écrivent l'état machine, et un témoin
        # « rien sous l'état réel » sans écrivain ne pourrait pas rougir.
        cls.init = _lancer([str(cls.commande), "init"], cls.projet, cls.env, "cadre init")
        cls.uv_jetable = {" ".join(argv): _lancer([UV, *argv], cls.base, cls.env, " ".join(argv))
                          for argv in (("tool", "dir"), ("tool", "dir", "--bin"), ("cache", "dir"))}
        cls.uv_liste = _lancer([UV, "tool", "list"], cls.base, cls.env, "uv tool list")

        cls.apres = {nom: releve(p) for nom, p in cls.surfaces.items()}

    def _rc0(self, r: subprocess.CompletedProcess, quoi: str) -> None:
        self.assertEqual(r.returncode, 0, f"{quoi} (rc={r.returncode}) :\n{r.stdout}{r.stderr}")

    def test_a_cadre_resout_sous_la_base_et_rend_sa_version(self):
        """MUTATION : PYTHONHOME cassé dans l'environnement → l'interpréteur de
        l'outil ne démarre pas → rouge."""
        trouve = shutil.which("cadre", path=self.env["PATH"])
        self.assertIsNotNone(trouve, "cadre introuvable sur le PATH jetable")
        self.assertEqual(Path(trouve).resolve(), self.commande.resolve())
        self._rc0(self.version, "cadre --version")
        self.assertTrue(self.version.stdout.strip(), "cadre --version n'a rien affiche")

    def test_b_cadre_tasks_list_dans_un_projet_vierge(self):
        self._rc0(self.tasks, "cadre tasks list")
        self.assertIn("TASK BOARD", self.tasks.stdout)

    def test_c_chaque_racine_rapportee_est_sous_la_base(self):
        """MUTATION : XDG_STATE_HOME dirigé hors de la base → rouge."""
        self._rc0(self.paths, "cadre paths --json")
        rapport = json.loads(self.paths.stdout)
        for cle, r in self.uv_jetable.items():
            self._rc0(r, f"uv {cle}")
            rapport[f"uv {cle}"] = r.stdout.strip()
        cles = ("PKG_ROOT", "CONFIG_HOME", "STATE_HOME", "STATE_PROJECT",
                *(f"uv {cle}" for cle in self.uv_jetable))
        self.assertEqual([], hors_de(rapport, {cle: self.base for cle in cles}),
                         "une racine rapportee sort de la base jetable")
        self._rc0(self.uv_liste, "uv tool list")
        self.assertIn(OUTIL, self.uv_liste.stdout, "uv tool list ne voit pas l'outil installe")

    def test_d_rien_sur_les_surfaces_reelles(self):
        """Les relevés avant le build et après les commandes sont égaux, et
        l'état machine que `cadre init` a écrit pour CE projet, présent sous la
        base, est absent sous l'état réel de cadre.
        MUTATIONS : une surface réelle remplacée par un dossier de la base que
        l'installation écrit → rouge ; XDG_STATE_HOME du parent qui fuit dans
        l'environnement jetable (parent dirigé vers un faux réel) → rouge."""
        for nom in self.surfaces:
            with self.subTest(surface=nom):
                self.assertEqual(self.avant[nom], self.apres[nom],
                                 f"{nom} ({self.surfaces[nom]}) a change pendant l'essai")
        self._rc0(self.paths, "cadre paths --json")
        self._rc0(self.init, "cadre init")
        rapport = json.loads(self.paths.stdout)
        jetable = Path(rapport["STATE_PROJECT"])
        # NON-VACUITÉ : l'état de CE projet a bien été écrit, sous la base.
        ecrits = [rel for rel, (_, _, mode) in inventaire(jetable).items() if stat.S_ISREG(mode)]
        self.assertTrue(ecrits, f"cadre init n'a rien ecrit sous {jetable} : le temoin ne "
                                "pourrait pas rougir")
        relatif = jetable.relative_to(Path(rapport["STATE_HOME"]))
        for reel in self.etats_reels:
            with self.subTest(etat_reel=reel):
                fuite = Path(reel) / relatif
                self.assertFalse(os.path.lexists(fuite),
                                 f"etat du projet jetable ecrit sous l'etat reel : {fuite}")


if __name__ == "__main__":
    unittest.main()
