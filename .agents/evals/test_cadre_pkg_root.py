#!/usr/bin/env python3
"""LA QUATRIÈME RACINE, `PKG_ROOT`, RÉSOLUE DEPUIS UNE WHEEL INSTALLÉE (T-00000855).

POURQUOI CE BANC. `cadre.paths` résout quatre racines. Trois se redirigent par
variable d'environnement et sont éprouvées ailleurs ; `PKG_ROOT` ne se redirige
pas : elle vaut l'emplacement du paquet. Dans ce dépôt c'est `.agents/vendor/cadre/` (ou `src/cadre/`), où
toute ressource est évidemment présente — et le témoin (b) de
`test_cadre_cli_installed.py` installe en ÉDITABLE, où `PKG_ROOT` retombe sur
l'arbre source. Une ressource ABSENTE DE LA WHEEL ne se voit donc qu'à
l'installation, chez quelqu'un d'autre. Ce banc la voit ici.

CE QU'IL MESURE (`PkgRootDepuisLaWheelTests`) — une construction, une
installation et une sonde par exécution, en `setUpClass` :
  (a) la wheel bâtie depuis CET arbre (`uv build --wheel --offline`), installée
      dans un venv JETABLE, résout `pkg_root()` dans le site-packages de ce venv
      — hors de l'arbre source — et `importlib.resources.files("cadre")` rend LE
      MÊME répertoire ;
  (b) chaque ressource attendue sous `data/` est atteinte par LES TROIS voies
      (`pkg_root()` nu, `importlib.resources`, et `Workspace(pkg_root())` —
      celle du noyau), octet pour octet identique à l'arbre ;
  (c) CALIBRATION — une copie de la wheel amputée d'UNE ressource (membre du
      zip ET ligne de `RECORD`) s'installe sans erreur, et le verdict de (b)
      nomme cette ressource, par les trois voies, et elle seule.
Sans uv (`VerdictSansUvTests`) : le verdict, l'amputation et la liste des
ressources sont éprouvés sur des données synthétiques — la seule part de ce
banc qui tourne là où uv manque.

LA SONDE tourne sous `python -I` — ni `PYTHONPATH`, ni site utilisateur, ni
répertoire courant dans `sys.path` — depuis un répertoire jetable hors du
dépôt : rien ne peut y ramener le paquet de l'arbre. Elle RAPPORTE, elle ne juge pas ;
le verdict est rendu ici par `defauts`, que `VerdictSansUvTests` éprouve.

LA LISTE DES RESSOURCES EST DÉRIVÉE DE GIT, SANS EXCEPTION : `git ls-files`
sous `<paquet>/data` (`PREFIXE_ARBRE`, que rend `vendor_paths` : `.agents/vendor/cadre/`
ou `src/cadre/`). Une ressource suivie qui entre dans ce `data/`
entre dans l'exigence sans retoucher ce banc ; un fichier non suivi n'y entre
pas — la porte joue `--at HEAD`, où il n'existe pas.

CE QU'IL NE MESURE PAS, écrit pour ne pas être relu comme couvert :
  * la commande `cadre` installée depuis la wheel — `check_cli_mode_wheel`
    (`prevu` au manifeste) ;
  * l'inventaire de la wheel en lui-même — `test_les_deux_gabarits_sont_dans_la_wheel`
    (`test_cadre_init_surfaces.py`) ;
  * une installation depuis un index — `--offline`, jamais le réseau ;
  * les modules `.py` : l'import de `cadre.paths` par la sonde les prouve en
    bloc, sans les énumérer.

CINQ SAUTS ANNONCÉS, tous sur le canal wheel : uv absent, projet adoptant
(marqueur `.agents/IS_THE_KIT`) — ces deux-là par décorateur, sur
`PkgRootDepuisLaWheelTests` et `SautDuCacheTests` — puis, au build, cache uv
non inscriptible (« Failed to initialize cache », prouvé MORDANT par
`SautDuCacheTests`), backend de build non résolvable (cache uv froid + réseau
coupé — prédicat IMPORTÉ de `test_cadre_init_surfaces.py`, jamais recopié), et
délai du build dépassé (verrou du cache uv tenu par un autre processus, ou poste
saturé — le build est `--offline`, le réseau est hors de cause). Tout autre
échec — build, venv, installation, sonde, délai d'un pas hors réseau — est ROUGE
avec son journal. COUVERTURE : un poste au cache uv chaud ; la CI n'installe
pas uv et n'y joue que `VerdictSansUvTests`. Dans un arbre adoptant (sans
marqueur), mesuré sur une copie partielle : 4 passés, 4 sautés.

RÉSIDU : l'installation passe `--no-cache` et ne laisse rien au cache uv
(mesuré) ; le build lit son backend au cache uv hérité, comme le banc wheel
existant. Tout le reste vit sous un répertoire temporaire supprimé en fin de
classe.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# IMPORTÉS TELS QUELS — des noms seuls, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_cli_installed import DELAI_CLI, env_blanche  # noqa: E402
from test_cadre_init_surfaces import (  # noqa: E402
    DELAI_BUILD,
    _est_un_backend_non_resolvable,
)

UV = shutil.which("uv")
GIT = shutil.which("git")

PAQUET = "cadre"
# Le paquet où qu'il vive (`.agents/vendor/cadre`, sinon `src/cadre`) : la règle
# de `vendor_paths.py`, chargé PAR CHEMIN (patron v3prep), jamais recopiée.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_pkg_root_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_DOSSIER = _VENDOR.dossier_paquet(ROOT, PAQUET) or ROOT / _VENDOR.ANCIENS[PAQUET]
#: Le chemin du paquet dans l'arbre ; une ressource s'y nomme `data/<…>`, comme
#: sous `pkg_root()` et, préfixée de `cadre/`, comme dans la wheel.
PREFIXE_ARBRE = _DOSSIER.relative_to(ROOT).as_posix() + "/"
DATA = "data"

#: Les trois voies par lesquelles la sonde atteint une ressource : le chemin
#: nu sous `pkg_root()`, `importlib.resources`, et `Workspace(pkg_root())` — la
#: voie que le noyau emprunte réellement (`config.py`, `init_surfaces.py`).
VOIES = ("par_pkg_root", "par_resources", "par_workspace")

# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant » : la wheel bâtie serait celle d'un autre.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()

SAUT_UV = ("SAUT ANNONCE : `uv` absent du PATH, la wheel ne peut pas etre batie "
           "ici — la resolution de PKG_ROOT depuis une wheel installee n'est PAS "
           "mesuree par cette execution")
SAUT_ADOPTANT = ("SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet "
                 "adoptant, pas le kit) — la wheel batie ici serait celle d'un "
                 "autre projet, et PKG_ROOT n'aurait pas de sujet")
SAUT_BACKEND = ("SAUT ANNONCE : backend de build non resolvable (cache uv froid + "
                "reseau coupe) — la resolution de PKG_ROOT depuis une wheel "
                "installee n'est PAS mesuree par cette execution")
SAUT_DELAI = (f"SAUT ANNONCE : `uv build --offline` n'a pas rendu la main en {DELAI_BUILD} s "
              "(verrou du cache uv tenu par un autre processus, ou poste sature — le "
              "reseau est hors de cause) — la resolution de PKG_ROOT depuis une wheel "
              "installee n'est PAS mesuree par cette execution")
SAUT_CACHE = ("SAUT ANNONCE : cache uv non inscriptible — la resolution de PKG_ROOT "
              "depuis une wheel installee n'est PAS mesuree par cette execution")

#: LA SONDE, jouée par l'interpréteur du venv sous `-I`. Elle RAPPORTE : la
#: racine, ce que rend `importlib.resources`, le site-packages du venv, et pour
#: chaque ressource demandée (argv[1], JSON) son empreinte par chaque voie —
#: `null` quand la voie ne la trouve pas.
SONDE = """\
import hashlib, importlib.resources, json, sys, sysconfig
from cadre.paths import pkg_root
from cadre.workspace import Workspace

def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest() if chemin.is_file() else None

def par_workspace(atelier, rel):
    # FileNotFoundError seul devient `null` ; HorsRacine leve, et la sonde echoue.
    try:
        return hashlib.sha256(atelier.read_bytes(rel)).hexdigest()
    except FileNotFoundError:
        return None

racine = pkg_root()
ressources = importlib.resources.files("cadre")
atelier = Workspace(racine)
rels = json.loads(sys.argv[1])
print(json.dumps({
    "pkg_root": str(racine),
    "files": str(ressources),
    "purelib": sysconfig.get_paths()["purelib"],
    "par_pkg_root": {r: empreinte(racine.joinpath(*r.split("/"))) for r in rels},
    "par_resources": {r: empreinte(ressources.joinpath(*r.split("/"))) for r in rels},
    "par_workspace": {r: par_workspace(atelier, r) for r in rels},
}))
"""


def env_uv() -> dict[str, str]:
    """La liste blanche de `test_cadre_cli_installed.py`, plus deux verrous uv :
    aucune configuration utilisateur lue, aucun interpréteur téléchargé."""
    return env_blanche(os.environ) | {"UV_NO_CONFIG": "1", "UV_PYTHON_DOWNLOADS": "never"}


def ressources_attendues() -> list[str]:
    """Les ressources que la wheel DOIT porter, en `data/<…>`, triées.

    `git ls-files`, jamais un parcours du disque. Les `GIT_*` hérités sont
    ôtés : un `GIT_DIR` posé par un hook ferait lire l'index d'un autre dépôt.
    git absent ou en échec : ROUGE, jamais une liste vide qui rendrait le
    verdict vert par vacuité."""
    if GIT is None:
        raise AssertionError("git absent du PATH : la liste des ressources suivies "
                             "ne peut pas etre etablie")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    r = subprocess.run([GIT, "-C", str(ROOT), "ls-files", "-z", "--", PREFIXE_ARBRE + DATA],
                       env=env, capture_output=True, timeout=DELAI_CLI, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git ls-files en echec (rc={r.returncode}) :\n"
                             + r.stderr.decode("utf-8", errors="replace"))
    return sorted(brut.decode("utf-8")[len(PREFIXE_ARBRE):]
                  for brut in r.stdout.split(b"\0") if brut)


def empreintes_de_l_arbre(rels: list[str]) -> dict[str, str]:
    """Le sha256 de chaque ressource telle que l'ARBRE la porte."""
    return {rel: hashlib.sha256((ROOT / PREFIXE_ARBRE / rel).read_bytes()).hexdigest()
            for rel in rels}


def defauts(rapport: dict, attendu: dict[str, str]) -> list[tuple[str, str, str]]:
    """Le VERDICT : `(ressource, voie, cause)` pour chaque ressource attendue
    qu'une voie ne rend pas telle quelle. Liste vide = vert.

    `absente` : la voie ne la trouve pas ; `divergente` : octets différents de
    l'arbre. Une voie MANQUANTE au rapport rend toutes ses ressources absentes —
    une sonde amputée rougit, elle ne passe pas."""
    trouves = []
    for rel, empreinte in sorted(attendu.items()):
        for voie in VOIES:
            vu = rapport.get(voie, {}).get(rel)
            if vu is None:
                trouves.append((rel, voie, "absente"))
            elif vu != empreinte:
                trouves.append((rel, voie, "divergente"))
    return trouves


def amputer(source: Path, cible: Path, membre: str) -> None:
    """Copie la wheel `source` en `cible` SANS `membre`, ni sa ligne de `RECORD`.

    Retirer aussi la ligne de `RECORD` garde la wheel cohérente : l'installation
    réussit, et c'est la RÉSOLUTION qui échoue — le défaut même que le banc
    doit voir. Un membre absent de la source lève : une amputation qui ne
    retire rien rendrait la calibration vacante."""
    with zipfile.ZipFile(source) as entree:
        if membre not in entree.namelist():
            raise ValueError(f"{membre} absent de {source.name} : rien a amputer")
        cible.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as sortie:
            for info in entree.infolist():
                if info.filename == membre:
                    continue
                contenu = entree.read(info)
                if info.filename.endswith(".dist-info/RECORD"):
                    lignes = contenu.decode("utf-8").splitlines(keepends=True)
                    contenu = "".join(ligne for ligne in lignes
                                      if not ligne.startswith(membre + ",")).encode("utf-8")
                sortie.writestr(info, contenu)


def _texte(flux: str | bytes | None) -> str:
    """Un flux de `TimeoutExpired` : `None`, ou des OCTETS même en mode texte."""
    if flux is None:
        return ""
    return flux.decode("utf-8", errors="replace") if isinstance(flux, bytes) else flux


def _executer(argv: list[str], cwd: Path, quoi: str,
              delai: float = DELAI_CLI) -> subprocess.CompletedProcess:
    """Un pas hors réseau (venv, installation, sonde) : tout échec est ROUGE,
    dépassement de `delai` compris — nommé, avec ce que le pas a écrit."""
    try:
        r = subprocess.run(argv, cwd=str(cwd), env=env_uv(), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=delai, check=False)
    except subprocess.TimeoutExpired as e:
        raise AssertionError(f"{quoi} : {delai} s depasses\n"
                             f"{_texte(e.stdout)}{_texte(e.stderr)}") from None
    if r.returncode != 0:
        raise AssertionError(f"{quoi} en echec (rc={r.returncode}) :\n{r.stdout}{r.stderr}")
    return r


def batir_wheel(sortie: Path) -> Path:
    """`uv build --wheel --offline` depuis CET arbre, hors du dépôt ; rend la wheel.

    Trois sauts annoncés — délai, cache uv non inscriptible, backend non
    résolvable ; tout autre échec est ROUGE — une vraie casse d'empaquetage ne
    se saute pas."""
    argv = [UV, "build", "--wheel", "--offline", "--python", sys.executable,
            "--out-dir", str(sortie)]
    try:
        r = subprocess.run(argv, cwd=str(ROOT), env=env_uv(), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=DELAI_BUILD,
                           check=False)
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
        raise AssertionError(f"une seule wheel `cadre_kit-*.whl` attendue, vu {roues} :\n{journal}")
    return roues[0]


def _python_du_venv(venv: Path) -> Path:
    windows = venv / "Scripts" / "python.exe"
    return windows if windows.is_file() else venv / "bin" / "python"


def installer_et_sonder(roue: Path, venv: Path, rels: list[str]) -> dict:
    """Venv jetable, installation de `roue` seule, puis la sonde depuis « dehors »."""
    _executer([UV, "venv", "--offline", "--python", sys.executable, str(venv)],
              venv.parent, "uv venv")
    python = _python_du_venv(venv)
    _executer([UV, "pip", "install", "--offline", "--no-cache", "--no-deps",
               "--python", str(python), str(roue)], venv.parent, "uv pip install")
    dehors = venv.parent / "dehors"
    dehors.mkdir(exist_ok=True)
    r = _executer([str(python), "-I", "-c", SONDE, json.dumps(rels)], dehors, "sonde")
    return json.loads(r.stdout)


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class PkgRootDepuisLaWheelTests(unittest.TestCase):
    """`PKG_ROOT` et ses ressources, depuis la wheel installée dans un venv jetable."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="cadre-pkgroot-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        if cls.base.is_relative_to(ROOT):
            # Sous le dépôt, « hors de l'arbre source » ne discriminerait plus.
            raise AssertionError(f"TMPDIR est sous le depot ({cls.base}) : le temoin (a) "
                                 "ne mesurerait rien")
        cls.rels = ressources_attendues()
        cls.attendu = empreintes_de_l_arbre(cls.rels)
        cls.wheel = batir_wheel(cls.base / "wheel")
        cls.rapport = installer_et_sonder(cls.wheel, cls.base / "venv", cls.rels)

    def test_a_pkg_root_resout_dans_le_venv_jetable(self):
        """CRITÈRE 1 : la wheel installée résout `PKG_ROOT` dans SON venv.

        Trois ancrages, chacun nécessaire : le site-packages du venv (et pas un
        autre `cadre` sur le chemin), hors de l'arbre source (et pas une fuite
        de `src/`), et l'accord avec `importlib.resources` — la voie que la
        table de `cadre.paths` nomme pour `PKG_ROOT`."""
        racine = Path(self.rapport["pkg_root"]).resolve()
        self.assertEqual((Path(self.rapport["purelib"]) / PAQUET).resolve(), racine,
                         "pkg_root() ne vaut pas <site-packages du venv>/cadre")
        self.assertTrue(racine.is_relative_to(self.base),
                        f"pkg_root() hors du venv jetable : {racine}")
        self.assertFalse(racine.is_relative_to(ROOT),
                         f"pkg_root() resout dans l'arbre source ({racine}) : c'est "
                         "le paquet de l'arbre qui repond, pas la wheel installee")
        self.assertEqual(racine, Path(self.rapport["files"]).resolve(),
                         "importlib.resources.files('cadre') et pkg_root() divergent")

    def test_b_chaque_ressource_de_data_est_atteinte_telle_quelle(self):
        """CRITÈRE 2 : une ressource absente de la wheel ROUGIT ici, nommée."""
        self.assertTrue(self.attendu, "aucune ressource attendue sous data/ : le "
                                      "verdict serait vert par vacuite")
        self.assertEqual([], defauts(self.rapport, self.attendu),
                         "ressources que la wheel installee ne rend pas telles que "
                         "l'arbre les porte (ressource, voie, cause)")

    def test_c_calibration_une_wheel_amputee_fait_rougir_le_verdict(self):
        """Le verdict de (b) MORD sur une vraie wheel installée : amputée d'une
        ressource, elle s'installe, `pkg_root()` se résout, et le verdict nomme
        cette ressource par les trois voies — elle seule."""
        cible = self.rels[0]
        ampute = self.base / "ampute" / self.wheel.name
        amputer(self.wheel, ampute, f"{PAQUET}/{cible}")
        rapport = installer_et_sonder(ampute, self.base / "venv-ampute", self.rels)
        self.assertTrue(Path(rapport["pkg_root"]).resolve().is_relative_to(self.base / "venv-ampute"),
                        "la sonde de la wheel amputee ne resout pas dans son propre venv")
        self.assertEqual([(cible, voie, "absente") for voie in VOIES],
                         defauts(rapport, self.attendu),
                         f"amputee de {cible}, la wheel installee n'est pas jugee "
                         "comme il faut : le verdict ne mord pas")


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class SautDuCacheTests(unittest.TestCase):
    """Le saut « cache uv non inscriptible » MORD sur le canal `uv build` : un
    `UV_CACHE_DIR` posé sous un FICHIER fait rendre à uv « Failed to initialize
    cache », et `batir_wheel` saute en l'annonçant au lieu de rougir. Le témoin
    suppose que `env_uv()` transmet `UV_CACHE_DIR` (liste blanche) — sans quoi
    uv lirait son cache chaud et le témoin serait vide."""

    def test_cache_non_inscriptible_saute_en_l_annoncant(self):
        with tempfile.TemporaryDirectory(prefix="cadre-cache-") as d:
            (Path(d) / "fichier").write_bytes(b"")
            with mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(Path(d) / "fichier" / "sous")}):
                self.assertEqual(str(Path(d) / "fichier" / "sous"), env_uv().get("UV_CACHE_DIR"),
                                 "env_uv() ne transmet pas UV_CACHE_DIR : le temoin serait vide")
                with self.assertRaises(unittest.SkipTest) as ctx:
                    batir_wheel(Path(d) / "wheel")
        self.assertEqual(SAUT_CACHE, str(ctx.exception))


class VerdictSansUvTests(unittest.TestCase):
    """Le verdict, l'amputation et la liste, SANS uv — tenus aussi en CI."""

    ATTENDU = {"data/a.json": "aa", "data/b.tmpl": "bb"}

    def _rapport(self, **ecrase: dict) -> dict:
        rapport = {voie: dict(self.ATTENDU) for voie in VOIES}
        rapport.update(ecrase)
        return rapport

    def test_le_verdict_discrimine_dans_les_deux_sens(self):
        self.assertEqual([], defauts(self._rapport(), self.ATTENDU), "complet : vert")
        manque = self._rapport(par_resources={"data/a.json": None, "data/b.tmpl": "bb"})
        self.assertEqual([("data/a.json", "par_resources", "absente")],
                         defauts(manque, self.ATTENDU))
        diverge = self._rapport(par_pkg_root={"data/a.json": "aa", "data/b.tmpl": "zz"})
        self.assertEqual([("data/b.tmpl", "par_pkg_root", "divergente")],
                         defauts(diverge, self.ATTENDU))
        sans_voie = {"par_pkg_root": dict(self.ATTENDU)}
        self.assertEqual([(rel, voie, "absente") for rel in sorted(self.ATTENDU)
                          for voie in ("par_resources", "par_workspace")],
                         defauts(sans_voie, self.ATTENDU),
                         "une voie manquante au rapport doit rougir, pas passer")

    def test_l_amputation_retire_le_membre_et_sa_ligne_record(self):
        with tempfile.TemporaryDirectory(prefix="cadre-ampute-") as d:
            source, cible = Path(d) / "x.whl", Path(d) / "sortie" / "x.whl"
            record = "cadre/data/a.json,sha256=aa,2\ncadre/__init__.py,sha256=ii,1\nx.dist-info/RECORD,,\n"
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("cadre/__init__.py", "")
                z.writestr("cadre/data/a.json", "{}")
                z.writestr("x.dist-info/RECORD", record)
            amputer(source, cible, "cadre/data/a.json")
            with zipfile.ZipFile(cible) as z:
                self.assertEqual(["cadre/__init__.py", "x.dist-info/RECORD"], sorted(z.namelist()))
                self.assertEqual("cadre/__init__.py,sha256=ii,1\nx.dist-info/RECORD,,\n",
                                 z.read("x.dist-info/RECORD").decode("utf-8"))
            with self.assertRaises(ValueError):
                amputer(source, cible, "cadre/data/absent.json")

    def test_un_pas_qui_depasse_son_delai_rougit_en_le_nommant(self):
        """Un pas hors réseau qui pend est ROUGE et nommé, jamais un
        `TimeoutExpired` nu ni un saut : le réseau n'y est pour rien."""
        with tempfile.TemporaryDirectory(prefix="cadre-delai-") as d:
            with self.assertRaises(AssertionError) as ctx:
                _executer([sys.executable, "-c", "import time; time.sleep(30)"],
                          Path(d), "sommeil", delai=0.001)
        self.assertIn("sommeil : 0.001 s depasses", str(ctx.exception))

    def test_la_liste_des_ressources_est_derivee_et_non_vide(self):
        rels = ressources_attendues()
        self.assertTrue(rels, f"aucune ressource suivie sous {PREFIXE_ARBRE}{DATA}")
        for rel in rels:
            with self.subTest(ressource=rel):
                self.assertTrue(rel.startswith(DATA + "/"), rel)
                self.assertTrue((ROOT / PREFIXE_ARBRE / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
