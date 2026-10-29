#!/usr/bin/env python3
"""`check_cli_mode_installed` — le côté INSTALLÉ de la CLI (T-00000573).

Entrée `check_cli_mode_installed` du `checks.manifest.json`, phase 4 (clause
« entry point console `cadre` ») ; tourne dans la porte par `pytest` (`testpaths`).

POURQUOI CE BANC EXISTE. `check_cli_mode_source` (`test_cadre_package.py`) joue
la CLI par `PYTHONPATH=<parent du paquet>` + `python -m cadre.cli` : l'entry point console n'y
est JAMAIS exercé, et un chemin d'import forcé gagne toujours sur un paquet
installé. Ici le paquet est INSTALLÉ en éditable par uv dans un bac à sable
jetable, et c'est le BINAIRE `cadre` que uv a posé qui répond.

CE QU'IL MESURE, cinq témoins :
  (a) PARITÉ OCTET À OCTET — neuf invocations, (rc, stdout, stderr) identiques
      entre le mode source et le binaire installé, codes 0, 1 et 2 compris ;
  (b) l'installé est l'éditable de CET arbre — `--version` égale
      `cadre.__version__` et `PKG_ROOT` vaut le dossier du paquet de CET arbre
      (`paquet_de` : `.agents/vendor/cadre`, sinon `src/cadre`) ;
  (c) CONTRÔLE NÉGATIF — sur une copie dont le script vise `cadre.cli:absent`,
      le binaire échoue sur `ImportError` quand le mode source reste vert : sans
      lui, (a) passerait aussi sur un « binaire » qui ne serait que `-m` ;
  (d) LEURRE — un paquet `cadre` factice posé sur un `PYTHONPATH` d'env parent
      GAGNE quand la fuite passe (calibration), et PERD derrière la liste
      blanche : sans leurre, une fuite serait invisible ;
  (e) NON-VACUITÉ — la liste d'invocations couvre les codes 0, 1 et 2.
Et une SONDE avant d'installer : le dossier « dehors » ne résout aucune racine.

CE QU'IL NE MESURE PAS, écrit pour ne pas être relu comme couvert :
  * la WHEEL — portée par `check_cli_mode_wheel` (`prevu`, T-00000661) ;
  * `cadre doctor` « vert » — nom RÉSERVÉ (Phase 6), joué pour la seule parité
    de son refus (rc 2), jamais pour un diagnostic ;
  * la CI et la jambe conteneur — ni ci.yml ni `python:<ver>-slim` n'installent
    uv : le saut y est ANNONCÉ et ne prouve rien, « uv absent » ou « backend »
    selon l'image, NON MESURÉ. Seule la DÉCLARATION y est tenue, sans uv
    (`EntreeConsoleDeclareeTests`) ;
  * une installation depuis un index — `--offline`, jamais le réseau.

COUVERTURE, à citer telle quelle : 1 poste, CONDITIONNELLE AU CACHE CHAUD. Au
cache uv froid le check SAUTE (saut « backend », porte verte, et la porte ne
passe pas `-rs` : le saut n'y est pas lu). Borné, pas résolu.

LE BAC À SABLE. `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` jetables sous tmpdir,
`UV_NO_CONFIG=1`, `UV_PYTHON_DOWNLOADS=never`, interpréteur ÉPINGLÉ (`--python
sys.executable` : sans lui uv prend un autre Python, et `argparse` diffère —
mesuré entre 3.9 et 3.14). Cache uv HÉRITÉ, jamais neuf : neuf, le backend est
introuvable hors ligne, donc un saut garanti (mesuré). RÉSIDU assumé, ~280K de
cache uv par porte, croissance NON BORNÉE, ménage = geste du pilote : mesure et
décompte au `resume` du manifeste.

CINQ SAUTS ANNONCÉS, un fragment chacun dans `sauts_admis` : uv absent, projet
adoptant, cache uv non inscriptible, backend non résolvable, délai dépassé. Le
prédicat « backend » et le délai sont IMPORTÉS de `test_cadre_init_surfaces.py`,
jamais recopiés ; `SautsDeLInstallationTests` prouve que les sauts « cache » et
« backend » mordent sur le canal `uv tool install`.

LE DISCRIMINANT KIT/ADOPTANT EST LE MARQUEUR `.agents/IS_THE_KIT` (`strip:` dans
`.template-exclude`, le même que `_is_kit_repo` de `test_template_hygiene.py`),
JAMAIS `[project.scripts]` : la lire pour décider de sauter faisait de la casse
de la propriété gardée un saut admis. Marqueur absent → saut « projet
adoptant ». Marqueur PRÉSENT : table absente, aucune clé, deux clés, ou une clé
autre que `cadre` visant `cadre.cli:main` → ÉCHEC nommé (`nom_de_commande`), uv
ou non ; `CliModeInstalleTests.setUpClass` lève alors (cinq ERREURS), sauf
quand un décorateur de saut passe avant (uv absent).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Le paquet où qu'il vive (`.agents/vendor/cadre`, sinon `src/cadre`) : la règle
# de `vendor_paths.py`, chargé PAR CHEMIN (patron v3prep) ; `sys.path` intact.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_cli_installed_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)


def paquet_de(racine: Path) -> Path:
    """Le dossier du paquet `cadre` sous `racine` (`PaquetIntrouvable` s'il manque) :
    `.agents/vendor/cadre` d'abord, sinon `src/cadre`. Son parent est le
    `PYTHONPATH` du mode source — jamais `racine/src` en dur."""
    return _VENDOR.exiger(racine, "cadre")

# IMPORTÉS TELS QUELS — seulement ces deux noms, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_init_surfaces import (  # noqa: E402
    DELAI_BUILD,
    _est_un_backend_non_resolvable,
)

UV = shutil.which("uv")

#: La cible de l'entry point console, et la commande que le contrat FIXE (clause
#: « entry point console `cadre` », décision pilote S-00002939) : la clé qui vise
#: ENTRY doit être COMMANDE — jamais dérivée de la table ni de `project.name`.
ENTRY = "cadre.cli:main"
COMMANDE = "cadre"

#: Borne d'une invocation de la CLI : un démarrage d'interpréteur, pas un build.
DELAI_CLI = 120

#: LA LISTE BLANCHE de l'environnement transmis aux sous-processus. Tout ce qui
#: n'y est pas est ÔTÉ — `PYTHON*` (PYTHONPATH, PYTHONHOME…), `CADRE_*`, et les
#: `UV_*` autres que le cache. HOME, XDG_CACHE_HOME et UV_CACHE_DIR sont GARDÉS :
#: ce sont eux qui mènent uv à son cache chaud. Les clés Windows servent au
#: démarrage du processus sur cet hôte et ne portent aucun chemin d'import.
LISTE_BLANCHE = frozenset({
    "PATH", "HOME", "XDG_CACHE_HOME", "UV_CACHE_DIR", "TMPDIR", "TMP", "TEMP",
    "LANG", "LC_ALL", "LC_CTYPE",
    "SYSTEMROOT", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PATHEXT", "COMSPEC",
})

VERSION_LEURRE = "0.0.0+leurre"

SAUT_UV = ("SAUT ANNONCE : `uv` absent du PATH, l'installation editable ne peut "
           "pas etre faite ici — l'entry point console n'est PAS exerce par cette "
           "execution")
# SANS « arbre » + « adoptant » (fragment de `check_state_partition`, qui
# admettrait CE saut : retirer le nôtre ne rougirait plus rien — mutant M4) ; SANS
# `[project.scripts]` : ce saut se lit sur le MARQUEUR, jamais sur la propriété.
SAUT_ADOPTANT = ("SAUT ANNONCE : marqueur `.agents/IS_THE_KIT` absent (projet "
                 "adoptant, pas le kit) — le binaire installe serait celui d'un "
                 "autre projet, et la parite n'aurait pas de sujet")
SAUT_BACKEND = ("SAUT ANNONCE : backend de build non resolvable pour l'installation "
                "editable (cache uv froid + reseau coupe) — l'entry point console "
                "n'est PAS exerce par cette execution")
SAUT_CACHE = ("SAUT ANNONCE : cache uv non inscriptible — l'entry point console "
              "n'est PAS exerce par cette execution")
SAUT_DELAI = (f"SAUT ANNONCE : l'installation editable par uv n'a pas rendu la main "
              f"en {DELAI_BUILD} s — l'entry point console n'est PAS exerce par "
              "cette execution")

#: Les neuf invocations de la parité : (argv, cwd « dedans » = ROOT). Toutes
#: tournent hors dépôt sauf `paths --json` « dedans ». Codes attendus, mesurés :
#: 0 (`--version`, `--help`, `paths --json` dedans, `--hote`), 1 (`paths --json`
#: dehors, racine non résolue), 2 (noms réservés, options inconnues).
INVOCATIONS: tuple[tuple[tuple[str, ...], bool], ...] = (
    (("--version",), False),
    (("doctor",), False),
    (("paths", "--json"), True),
    (("paths", "--json"), False),
    (("paths", "--jsonn"), False),
    (("init", "--upgrade"), False),
    (("--help",), False),
    (("config", "explain", "k", "--hote", "claude"), False),
    (("config", "explain", "k", "--hotte", "claude"), False),
)


def env_blanche(parent: Mapping[str, str]) -> dict[str, str]:
    """L'env `parent` réduit à la liste blanche. PURE : elle ne lit jamais
    `os.environ` elle-même, pour que (d) lui passe un parent SYNTHÉTIQUE porteur
    de la fuite et constate la clé ôtée."""
    return {k: v for k, v in parent.items() if k.upper() in LISTE_BLANCHE}


def lancer_source(args, cwd: Path, racine: Path, env: Mapping[str, str]) -> subprocess.CompletedProcess:
    """Le MODE SOURCE : `python -m cadre.cli` sous `env`, son `PYTHONPATH` posé sur
    le parent du paquet de `racine` (`paquet_de`), quel que soit son emplacement."""
    return subprocess.run([sys.executable, "-m", "cadre.cli", *args], cwd=str(cwd),
                          env=dict(env) | {"PYTHONPATH": str(paquet_de(racine).parent)},
                          capture_output=True, timeout=DELAI_CLI, check=False)


def table_scripts(manifeste: Path) -> dict[str, str] | None:
    """`[project.scripts]` de `manifeste`, ou `None` : absent, illisible, sans la
    table, ou `project`/`scripts` non-table (lue au CHARGEMENT : un
    `AttributeError` couperait la collecte sans nom). Elle LIT, ne décide rien —
    le saut « adoptant » se lit sur le marqueur (NO_GO exec-critic, P1/P2)."""
    if not manifeste.is_file():
        return None
    try:
        charge = tomllib.loads(manifeste.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return None
    projet = charge.get("project")
    scripts = projet.get("scripts") if isinstance(projet, dict) else None
    return dict(scripts) if isinstance(scripts, dict) else None


def entry_points_declares(manifeste: Path) -> list[str]:
    """Les clés de `[project.scripts]` qui valent `cadre.cli:main`, triées ;
    `[]` quand aucune ne la vise ou que la table manque."""
    return sorted(k for k, v in (table_scripts(manifeste) or {}).items() if v == ENTRY)


def nom_de_commande(scripts: Mapping[str, str] | None) -> str:
    """La commande à exercer SUR LE KIT : l'unique clé de `scripts` qui vise
    `cadre.cli:main`, et elle doit valoir COMMANDE. PURE, pour que ses refus
    aient un témoin sans uv (`EntreeConsoleDeclareeTests`). Jamais un saut — elle
    n'est appelée que derrière le marqueur, et sur le kit une déclaration cassée
    est la régression même que ce banc garde :
      * table absente, ou aucune clé ne vise `cadre.cli:main` → ÉCHEC nommé ;
      * DEUX clés ou plus la visent → ÉCHEC nommé (choisir est une décision) ;
      * une clé unique AUTRE que `cadre` → ÉCHEC nommé : le contrat fixe le nom."""
    if scripts is None:
        raise AssertionError(
            "le KIT (marqueur .agents/IS_THE_KIT present) n'a plus de table "
            f"[project.scripts] : l'entry point console `{ENTRY}` a disparu — c'est "
            "la propriete que ce banc garde, jamais un saut")
    visees = sorted(k for k, v in scripts.items() if v == ENTRY)
    if not visees:
        raise AssertionError(
            "le KIT (marqueur .agents/IS_THE_KIT present) : aucune cle de "
            f"[project.scripts] ne vise {ENTRY} ({dict(scripts)}) — l'entry point "
            "console a ete change : c'est la propriete que ce banc garde, jamais un saut")
    if len(visees) != 1:
        raise AssertionError(
            f"plusieurs cles de [project.scripts] visent {ENTRY} : {visees} "
            "— le banc n'exerce qu'une commande, choisir laquelle est une decision")
    if visees[0] != COMMANDE:
        raise AssertionError(
            f"la commande declaree est `{visees[0]}`, le contrat exige `{COMMANDE}` "
            f"(clause « entry point console `{COMMANDE}` ») — jamais un saut")
    return visees[0]


def ligne_du_script(nom: str) -> re.Pattern[str]:
    """La ligne `<nom> = "cadre.cli:main"`, ANCRÉE en début de ligne : un
    commentaire qui cite la valeur n'y répond pas — compter le texte brut le
    comptait, et le témoin (c) rougissait à tort (« ambigu »)."""
    return re.compile(rf'^([ \t]*"?{re.escape(nom)}"?[ \t]*=[ \t]*)(["\'])'
                      rf'{re.escape(ENTRY)}\2', re.MULTILINE)


# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « projet adoptant », INDÉPENDANT de la propriété gardée.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()
# adopting-tree: le manifeste ne voyage pas (strip: pyproject.toml, S-00004099) ; absent,
# `table_scripts` rend None, et SCRIPTS n'est lu que derrière EST_LE_KIT.
SCRIPTS = table_scripts(ROOT / "pyproject.toml")


def installer(racine: Path, outils: Path, nom: str) -> Path:
    """Installe `racine` en éditable dans le bac à sable `outils` ; rend le binaire.

    L'argv est une LISTE, et la source est un CHEMIN : aucun nom de paquet n'est
    résolu sur un index. Trois sauts annoncés (délai, cache non inscriptible,
    backend introuvable) ; tout autre échec est ROUGE — une vraie casse
    d'empaquetage ne se saute pas. Cache : uv 0.12.7 rend rc 2 et « Failed to
    initialize cache » sur EACCES comme sur ENOTDIR (mesuré le 2026-09-27)."""
    outils.mkdir(parents=True, exist_ok=True)
    env = env_blanche(os.environ) | {
        "UV_TOOL_DIR": str(outils / "tools"),
        "UV_TOOL_BIN_DIR": str(outils / "bin"),
        "UV_NO_CONFIG": "1",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    argv = [UV, "tool", "install", "--offline", "--editable", str(racine),
            "--python", sys.executable]
    try:
        r = subprocess.run(argv, cwd=str(outils), env=env, capture_output=True,
                           text=True, timeout=DELAI_BUILD, check=False)
    except subprocess.TimeoutExpired:
        raise unittest.SkipTest(SAUT_DELAI) from None
    journal = r.stdout + r.stderr
    if r.returncode != 0 and "Failed to initialize cache" in journal:
        raise unittest.SkipTest(SAUT_CACHE)
    if r.returncode != 0 and _est_un_backend_non_resolvable(journal):
        raise unittest.SkipTest(SAUT_BACKEND)
    if r.returncode != 0:
        raise AssertionError(f"installation editable en echec (rc={r.returncode}) :\n{journal}")
    binaire = shutil.which(nom, path=str(outils / "bin"))
    if binaire is None:
        raise AssertionError(f"uv a rendu 0 sans poser `{nom}` dans {outils / 'bin'} :\n{journal}")
    return Path(binaire)


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class CliModeInstalleTests(unittest.TestCase):
    """L'entry point console `cadre`, installé en éditable, contre le mode source."""

    @classmethod
    def setUpClass(cls):
        # Sur le kit : zéro clé, deux clés ou une clé autre que `cadre` (ou un
        # « dehors » sous un projet, plus bas) → AssertionError ici, donc les cinq
        # tests en ERREUR — sauf quand un décorateur de saut passe avant (uv
        # absent, marqueur absent) : il empêche setUpClass de tourner. La
        # déclaration reste alors tenue, sans uv, par `EntreeConsoleDeclareeTests`.
        cls.nom = nom_de_commande(SCRIPTS)
        cls.base = Path(tempfile.mkdtemp(prefix="cadre-installe-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        cls.dehors = cls.base / "dehors"
        cls.dehors.mkdir()
        # SONDE, avant d'installer : « dehors » doit être hors de tout projet.
        # Sous un dépôt git ou un `.agents/`, le code 1 ne serait jamais joué, et
        # seul (e) rougirait — sans nommer la cause.
        sonde = cls._source(("paths", "--json"), cls.dehors)
        if sonde.returncode != 1:  # rc 0 : racine résolue ; autre : cadre.cli ne tourne pas
            cause = ("TMPDIR est sous un depot git ou sous un .agents/, la parite « dehors » "
                     "ne mesurerait rien" if sonde.returncode == 0 else "cadre.cli en echec")
            raise AssertionError(
                f"sonde « dehors » ({cls.dehors}) : `paths --json` y rend "
                f"rc={sonde.returncode}, pas 1 — {cause} ; stderr :\n"
                + sonde.stderr.decode(errors="replace"))
        cls.binaire = installer(ROOT, cls.base / "outils", cls.nom)
        cls._mesures = None

    # -- les deux côtés, sous LE MÊME env -----------------------------------

    @classmethod
    def _env(cls, **en_plus: str) -> dict[str, str]:
        """Liste blanche + racines CONFIG/STATE redirigées + aucune écriture de
        bytecode : le mode source importe depuis le parent du paquet, et le banc ne doit
        rien déposer dans l'arbre qu'il mesure."""
        return env_blanche(os.environ) | {
            "CADRE_CONFIG_HOME": str(cls.base / "conf"),
            "CADRE_STATE_DIR": str(cls.base / "etat"),
            "PYTHONDONTWRITEBYTECODE": "1",
        } | en_plus

    @classmethod
    def _source(cls, args, cwd: Path, racine: Path = ROOT) -> subprocess.CompletedProcess:
        return lancer_source(args, cwd, racine, cls._env())

    def _installe(self, args, cwd: Path, binaire: Path | None = None,
                  env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(binaire or self.binaire), *args], cwd=str(cwd),
                              env=self._env() if env is None else env,
                              capture_output=True, timeout=DELAI_CLI, check=False)

    @classmethod
    def _mesurer(cls, moi: CliModeInstalleTests):
        """Les neuf invocations, jouées UNE fois pour (a) et (e)."""
        if cls._mesures is None:
            cls._mesures = [
                (args, dedans, moi._source(args, ROOT if dedans else cls.dehors),
                 moi._installe(args, ROOT if dedans else cls.dehors))
                for args, dedans in INVOCATIONS
            ]
        return cls._mesures

    # -- (a) ------------------------------------------------------------------

    def test_a_parite_octet_a_octet_source_contre_binaire_installe(self):
        """(rc, stdout, stderr) IDENTIQUES, en OCTETS, pour les neuf invocations.
        Une divergence dit que l'entry point ne sert pas la même CLI que le
        mode source — interpréteur, chemin d'import ou `prog` différents."""
        for args, dedans, s, i in self._mesurer(self):
            with self.subTest(argv=" ".join(args), dedans=dedans):
                self.assertEqual(
                    (i.returncode, i.stdout, i.stderr),
                    (s.returncode, s.stdout, s.stderr),
                    "le binaire installe et le mode source divergent",
                )

    # -- (b) ------------------------------------------------------------------

    def test_b_le_binaire_est_l_editable_de_CET_arbre(self):
        """La parité seule ne dit pas QUEL paquet répond : deux copies du même
        code seraient paritaires. `--version` et `PKG_ROOT` l'ancrent à CET arbre.
        MUTATION : éditable pointée sur une copie au `__version__` différent."""
        cadre = _VENDOR.charger_paquet(ROOT, "cadre")

        r = self._installe(("--version",), self.dehors)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        self.assertEqual(r.stdout.decode().strip(), cadre.__version__,
                         "le binaire installe ne sert pas la version de cet arbre")
        r = self._installe(("paths", "--json"), ROOT)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        self.assertEqual(Path(json.loads(r.stdout)["PKG_ROOT"]),
                         paquet_de(ROOT).resolve(),
                         "l'editable ne pointe pas le paquet de cet arbre")

    # -- (c) ------------------------------------------------------------------

    def test_c_controle_negatif_un_entry_point_CASSE_fait_echouer_le_binaire(self):
        """Sans ce témoin, (a) serait vert sur un « binaire » qui ne serait que
        `python -m cadre.cli` : rien n'y dépend de l'entry point. Ici le script
        vise `cadre.cli:absent` — le binaire DOIT échouer sur `ImportError`,
        quand le mode source de la MÊME copie reste vert (le code est sain,
        seule la déclaration est cassée). Dossiers d'outils PROPRES à la copie.
        MUTATION : binaire remplacé par `-m cadre.cli` → rc 0 → rouge."""
        copie = self.base / "copie"
        copie.mkdir(parents=True)
        for nom in ("pyproject.toml", "README.md"):
            shutil.copy2(ROOT / nom, copie / nom)
        paquet = paquet_de(ROOT)  # même place relative dans la copie que dans l'arbre
        shutil.copytree(paquet, copie / paquet.relative_to(ROOT.resolve()),
                        ignore=shutil.ignore_patterns("__pycache__"))
        # La wheel FORCE l'inclusion des sources du moteur du board (T-00000962) :
        # sans elles dans la copie, hatch refuse « Forced include not found ».
        # adopting-tree: le manifeste ne voyage pas (strip: pyproject.toml) ; test_c saute deja hors kit
        outils_hatch = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        forces = (outils_hatch.get("tool", {}).get("hatch", {}).get("build", {})
                  .get("targets", {}).get("wheel", {}).get("force-include", {}))
        for source in forces:
            (copie / source).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / source, copie / source)
        manifeste = copie / "pyproject.toml"
        texte = manifeste.read_text(encoding="utf-8")
        ligne = ligne_du_script(self.nom)
        self.assertEqual(len(ligne.findall(texte)), 1,
                         f"ligne `{self.nom} = \"{ENTRY}\"` introuvable ou ambigue — la "
                         "copie ne serait pas cassee, le temoin serait vert a vide")
        manifeste.write_text(ligne.sub(r'\1\2cadre.cli:absent\2', texte), encoding="utf-8")
        self.assertEqual(entry_points_declares(manifeste), [], "la copie vise encore main")

        binaire = installer(copie, self.base / "outils-copie", self.nom)
        r = self._installe(("--version",), self.dehors, binaire=binaire)
        self.assertNotEqual(r.returncode, 0,
                            "un entry point casse repond quand meme : le binaire "
                            "n'exerce pas l'entry point")
        self.assertIn(b"ImportError", r.stderr, r.stderr.decode(errors="replace"))
        s = self._source(("--version",), self.dehors, racine=copie)
        self.assertEqual(s.returncode, 0,
                         "le mode source de la copie echoue aussi : l'echec du binaire "
                         "ne prouve plus rien sur l'entry point\n"
                         + s.stderr.decode(errors="replace"))

    # -- (d) ------------------------------------------------------------------

    def test_d_la_liste_blanche_ote_un_PYTHONPATH_fuyant_de_l_env_parent(self):
        """Un `PYTHONPATH` hérité fait importer AUTRE CHOSE au binaire. Le leurre
        rend la fuite OBSERVABLE : calibré d'abord (la fuite gagne), puis la
        liste blanche doit la faire perdre.
        MUTATION : `PYTHONPATH` ajouté à `LISTE_BLANCHE` → le leurre gagne → rouge."""
        cadre = _VENDOR.charger_paquet(ROOT, "cadre")

        leurre = self.base / "leurre"
        (leurre / "cadre").mkdir(parents=True)
        (leurre / "cadre" / "__init__.py").write_text(
            f'__version__ = "{VERSION_LEURRE}"\n', encoding="utf-8")
        (leurre / "cadre" / "cli.py").write_text(
            "from cadre import __version__\n\n\n"
            "def main(argv=None):\n    print(__version__)\n    return 0\n",
            encoding="utf-8")

        # CALIBRATION : sans elle, un leurre qui ne serait jamais importé rendrait
        # la seconde moitié verte par construction.
        fuite = self._env(PYTHONPATH=str(leurre))
        r = self._installe(("--version",), self.dehors, env=fuite)
        self.assertEqual(r.stdout.decode().strip(), VERSION_LEURRE,
                         "calibration : le leurre n'est pas importe malgre la fuite "
                         "— ce temoin ne mesurerait rien\n" + r.stderr.decode(errors="replace"))

        parent = dict(os.environ, PYTHONPATH=str(leurre), PYTHONHOME=str(leurre),
                      CADRE_PROJECT_ROOT=str(leurre), CADRE_CONFIG_HOME=str(leurre))
        propre = env_blanche(parent)
        r = self._installe(("--version",), self.dehors,
                           env=propre | {"PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        self.assertEqual(r.stdout.decode().strip(), cadre.__version__,
                         "le leurre gagne : la liste blanche laisse passer la fuite")
        self.assertEqual(sorted(k for k in propre
                                if k.upper().startswith(("PYTHON", "CADRE_"))), [],
                         "la liste blanche laisse passer une variable PYTHON*/CADRE_*")

    # -- (e) ------------------------------------------------------------------

    def test_e_non_vacuite_la_liste_couvre_les_codes_0_1_et_2(self):
        """Une parité sur des invocations qui rendraient toutes le même code
        ne distinguerait pas un binaire qui échoue toujours pareil. La liste
        doit exercer les trois codes, et la sortie ne doit pas être vide."""
        mesures = self._mesurer(self)
        self.assertEqual(len(mesures), 9, "la liste a perdu une invocation")
        self.assertEqual({s.returncode for _, _, s, _ in mesures}, {0, 1, 2},
                         "la liste n'exerce plus les codes 0, 1 et 2")
        self.assertTrue(any(s.stdout for _, _, s, _ in mesures), "stdout toujours vide")
        self.assertTrue(any(s.stderr for _, _, s, _ in mesures), "stderr toujours vide")


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class SautsDeLInstallationTests(unittest.TestCase):
    """Les deux sauts d'ENVIRONNEMENT d'`installer` MORDENT sur le canal `uv tool
    install` — le prédicat « backend » est importé d'un banc `uv build`, et rien
    d'autre n'établit qu'il reconnaît la sortie de ce canal-ci."""

    def test_cache_froid_et_cache_non_inscriptible_sautent_en_l_annoncant(self):
        """Cache neuf → saut « backend » ; cache sous un FICHIER (ENOTDIR, qui
        tient quel que soit l'euid, root compris) → saut « cache ». Caches
        jetables : aucun résidu dans le cache réel.
        MUTATION : l'un des deux prédicats retiré d'`installer` → ROUGE."""
        with tempfile.TemporaryDirectory(prefix="cadre-sauts-",
                                         ignore_cleanup_errors=True) as d:
            (Path(d) / "fichier").write_text("", encoding="utf-8")
            for cas, cache, attendu in (("froid", Path(d) / "froid", SAUT_BACKEND),
                                        ("illisible", Path(d) / "fichier" / "sous", SAUT_CACHE)):
                with self.subTest(cache=cas), \
                        mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(cache)}):
                    with self.assertRaises(unittest.SkipTest) as saut:
                        installer(ROOT, Path(d) / f"outils-{cas}", COMMANDE)
                    self.assertEqual(str(saut.exception), attendu)


class EntreeConsoleDeclareeTests(unittest.TestCase):
    """LA DÉCLARATION de l'entry point, SANS uv : elle tourne donc aussi là où
    `CliModeInstalleTests` saute (CI, conteneur, cache froid). Elle ne prouve
    RIEN sur le binaire — seulement que le kit déclare encore `cadre.cli:main`
    sous une clé et une seule, et que le banc refuse le reste par un ÉCHEC."""

    @unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
    def test_le_KIT_declare_cadre_cli_main_sous_une_seule_cle(self):
        """Sur le kit, une table retirée ou une valeur changée ÉCHOUE ici, uv
        présent ou non — jamais un saut « projet adoptant ».
        MUTATION : `EST_LE_KIT` relu sur `[project.scripts]` (l'ancien prédicat)
        → une copie du kit cassée (P1 valeur, P2 table) redevient un saut."""
        self.assertEqual(nom_de_commande(SCRIPTS), COMMANDE)

    def test_zero_deux_ou_une_autre_cle_ECHOUENT_cadre_seule_passe(self):
        """Témoins sur des pyproject FIXTURES, jamais celui de ROOT : les refus
        de `nom_de_commande` et son unique issue verte, `cadre` — que
        `project.name` n'influence pas (distribution `autre`).
        MUTATIONS : `if len(visees) != 1` retiré → deux clés rendent la première
        → rouge ; `visees[0] != COMMANDE` retiré → `kit` rendue → rouge."""
        entete = '[project]\nname = "autre"\nversion = "0"\n'
        cas = {
            "table absente": (entete, "n'a plus de table"),
            "valeur changee": (entete + '\n[project.scripts]\ncadre = "cadre.cli:principal"\n',
                               "aucune cle"),
            "deux cles": (entete + f'\n[project.scripts]\ncadre = "{ENTRY}"\n'
                          f'cadre2 = "{ENTRY}"\n', "plusieurs cles"),
            "cle renommee": (entete + f'\n[project.scripts]\nkit = "{ENTRY}"\n',
                             "le contrat exige `cadre`"),
            "illisible": ("[project\n", "n'a plus de table"),
            "project scalaire": ('project = "x"\n', "n'a plus de table"),
        }
        with tempfile.TemporaryDirectory(prefix="cadre-scripts-") as d:
            manifeste = Path(d) / "pyproject.toml"
            for nom, (texte, motif) in cas.items():
                with self.subTest(cas=nom):
                    manifeste.write_text(texte, encoding="utf-8")
                    with self.assertRaisesRegex(AssertionError, motif):
                        nom_de_commande(table_scripts(manifeste))
            manifeste.write_text(entete + f'\n[project.scripts]\ncadre = "{ENTRY}"\n'
                                 'autre = "ailleurs:main"\n', encoding="utf-8")
            self.assertEqual(nom_de_commande(table_scripts(manifeste)), "cadre")
        self.assertEqual(table_scripts(Path(d) / "pyproject.toml"), None,
                         "manifeste absent : la table doit manquer, pas etre vide")

    def test_la_ligne_du_script_ignore_un_commentaire_qui_cite_la_valeur(self):
        """Le repérage de (c), sans uv : un commentaire citant la valeur ne compte
        pas, et seule la VALEUR de la vraie ligne est remplacée.
        MUTATION : ancre `^` retirée → le commentaire compte (2) → rouge."""
        texte = ('[project]\nname = "autre"\nversion = "0"\n\n[project.scripts]\n'
                 f'# ancien : cadre = "{ENTRY}"\ncadre = "{ENTRY}"  # vise {ENTRY}\n')
        ligne = ligne_du_script(COMMANDE)
        self.assertEqual(len(ligne.findall(texte)), 1, "le commentaire est compte")
        with tempfile.TemporaryDirectory(prefix="cadre-scripts-") as d:
            manifeste = Path(d) / "pyproject.toml"
            manifeste.write_text(ligne.sub(r'\1\2cadre.cli:absent\2', texte), encoding="utf-8")
            self.assertEqual(table_scripts(manifeste), {COMMANDE: "cadre.cli:absent"})


class VendorSeulTests(unittest.TestCase):
    """TÉMOIN E (T-01M5BXTPQE3JZV3KZA6WD9P5XC, lot E) — le mode source suit le
    paquet là où `vendor_paths` le désigne, sans uv ni marqueur du kit.

    Kit JETABLE : le paquet réel copié sous `.agents/vendor/cadre` SEUL (« vendor
    seul »), puis un LEURRE posé sous `src/cadre` (« les deux » : le neuf doit
    gagner). Les deux fois, `lancer_source` doit servir la version du paquet réel.
    MUTATION : `paquet_de` ou le `PYTHONPATH` de `lancer_source` ramené à
    `racine / "src"` → vendor seul : `No module named cadre` ; les deux : le
    leurre répond → rouge."""

    def test_vendor_seul_e(self):
        reel = _VENDOR.charger_paquet(ROOT, "cadre")
        with tempfile.TemporaryDirectory(prefix="cadre-vendor-e-") as d:
            base = Path(d).resolve()
            kit, dehors = base / "kit", base / "dehors"
            dehors.mkdir()
            shutil.copytree(paquet_de(ROOT), kit / ".agents" / "vendor" / "cadre",
                            ignore=shutil.ignore_patterns("__pycache__"))
            env = env_blanche(os.environ) | {
                "CADRE_CONFIG_HOME": str(base / "conf"), "CADRE_STATE_DIR": str(base / "etat"),
                "PYTHONDONTWRITEBYTECODE": "1"}
            leurre = kit / "src" / "cadre"
            for cas in ("vendor seul", "les deux"):
                if cas == "les deux":
                    leurre.mkdir(parents=True)
                    (leurre / "__init__.py").write_text(
                        f'__version__ = "{VERSION_LEURRE}"\n', encoding="utf-8")
                    (leurre / "cli.py").write_text(
                        "from cadre import __version__\n\n\n"
                        "def main(argv=None):\n    print(__version__)\n    return 0\n\n\n"
                        'if __name__ == "__main__":\n    main()\n',
                        encoding="utf-8")
                with self.subTest(cas=cas):
                    self.assertEqual(paquet_de(kit), kit / ".agents" / "vendor" / "cadre")
                    r = lancer_source(("--version",), dehors, kit, env)
                    self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
                    self.assertEqual(r.stdout.decode().strip(), reel.__version__,
                                     f"{cas} : le mode source ne sert pas le paquet vendor")


if __name__ == "__main__":
    unittest.main()
