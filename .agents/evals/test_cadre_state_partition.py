#!/usr/bin/env python3
"""Banc de la PARTITION DE STATE_HOME PAR PROJET — check_state_partition (T-00000649).

`cadre.paths.state_project()` rend `state_home()/projets/<empreinte sha256 du
chemin canonique>` en LISANT le disque pour canonicaliser la casse par identite
(st_dev, st_ino), sans RIEN y creer (T-00000674). Ce banc prouve la forme de
l'empreinte et sa stabilite, l'ACCORD DES BRANCHES sur une racine EXISTANTE et le
non-repli d'une racine INEXISTANTE (decisions pilote S-00001598, S-00001650), et que
la resolution de la racine machine ne se re-derive nulle part ailleurs dans le
paquet `cadre` (`.agents/vendor/cadre/` ou `src/cadre/`, ce que `vendor_paths`
designe) — un ensemble d'appelants CLOS que tout ajout fait rougir.

Il porte aussi deux temoins de PROSE : le cardinal et les noms de cles annonces
par le `cli.py` du paquet et la note du verrou doivent suivre le schema reel, et le
docstring de module de `cadre.paths` (qui VOYAGE dans la wheel) doit nommer toutes
les cles rendues. Leur mode d'echec n'est pas « le texte ment » mais « le texte
DISPARAIT » : une resolution de fusion peut effacer la phrase, et alors plus rien
ne tiendrait le cardinal.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# OU vit le paquet `cadre` : `vendor_paths` charge PAR CHEMIN (patron v3prep,
# T-01M5BXTPQE3JZV3KZA6WD9P5XC), `.agents/vendor/cadre` d'abord, `src/cadre`
# sinon ; `charger_paquet` ne touche jamais `sys.path`.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_state_partition_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
PKG = _VENDOR.exiger(ROOT, "cadre")

import cadre.paths  # noqa: E402
from cadre.cli import _racines  # noqa: E402
from cadre.paths import canonique_disque, nom_projet, project_root, state_home, state_project, vider_cache_racine  # noqa: E402

# adopting-tree: checks.manifest.json est strip:-é — ce registre est celui du kit, l'adoptant n'en a pas
MANIFESTE = ROOT / "checks.manifest.json"

# Le jeu de cles hors `erreur` apres l'etape 2, relu sur le litteral de cli.py.
# UN SEUL endroit dans ce banc ; le second est test_cadre_package.py, tenu d'accord
# par test_les_deux_enumerations_de_cles_du_depot_sont_D_ACCORD. Les temoins 10 et 11
# comparent par EGALITE contre lui.
CLES_ATTENDUES = {"PKG_ROOT", "CONFIG_HOME", "STATE_HOME",
                  "PROJECT_ROOT", "AGENTS_DIR", "STATE_PROJECT"}

# Table de NUMERAUX FRANCAIS bornee 5-9, encodant une CONVENTION d'ecriture
# (cardinal en lettres : capitales dans cli.py, minuscules dans le verrou). Au-dela
# de neuf cles, ou si un auteur ecrit le cardinal en CHIFFRES, un temoin rougit sur
# un texte VRAI : le remede est d'etendre la table ou la convention, jamais de
# retirer l'assertion.
MOTS = {5: "CINQ", 6: "SIX", 7: "SEPT", 8: "HUIT", 9: "NEUF"}


def _elements_cadre_paths() -> list[dict]:
    return [e for e in json.loads((ROOT / "contract.lock.json").read_text(encoding="utf-8"))["elements"]
            if e["element"] == "cadre paths"]


def _appels_state_home(texte: str) -> list[str]:
    """Les APPELS a `state_home` par l'AST, nommes par leur fonction englobante."""
    trouves: list[str] = []

    def visite(n, englobant):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            englobant = n.name
        if (isinstance(n, ast.Call)
                and ((isinstance(n.func, ast.Name) and n.func.id == "state_home")
                     or (isinstance(n.func, ast.Attribute) and n.func.attr == "state_home"))):
            trouves.append(englobant)
        for c in ast.iter_child_nodes(n):
            visite(c, englobant)

    visite(ast.parse(texte), "<module>")
    return trouves


class _Base(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        vider_cache_racine()


class PartitionTests(_Base):
    """Temoins 1 a 6 : la forme et les proprietes de `state_project()`."""

    def test_deux_racines_distinctes_donnent_deux_sous_dossiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            etat = Path(tmp) / "etat"
            os.environ["CADRE_STATE_DIR"] = str(etat)
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "a")
            p1 = state_project()
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "b")
            p2 = state_project()
            self.assertNotEqual(p1, p2)
            self.assertEqual(p1.parent, p2.parent)
            self.assertEqual(p1.parent.name, "projets")

    def test_deux_copies_du_meme_depot_donnent_deux_sous_dossiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "etat")
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "a" / "projet")
            pa = state_project()
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "b" / "projet")
            pb = state_project()
            self.assertNotEqual(pa.name, pb.name)

    def test_la_casse_du_chemin_est_CONSERVEE_pour_une_racine_INEXISTANTE(self):
        # Repertoires DELIBEREMENT NON CREES : on mesure la DECISION (S-00001598),
        # pas le systeme de fichiers. Sur un FS insensible a la casse, realpath
        # rendrait la casse du disque ; _from_env n'exige aucune existence.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "etat")
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "Projet")
            haut = state_project()
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "projet")
            bas = state_project()
            self.assertNotEqual(haut.name, bas.name)

    def test_l_empreinte_est_la_forme_promise(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "etat")
            racine_dir = Path(tmp) / "mon" / "projet"
            os.environ["CADRE_PROJECT_ROOT"] = str(racine_dir)
            p = state_project()
            # Golden par RECALCUL independant, jamais un second appel de la fonction.
            attendu = hashlib.sha256(
                project_root().resolve().as_posix().encode("utf-8")
            ).hexdigest()[:16]
            self.assertEqual(p.name, attendu)
            self.assertEqual(len(p.name), 16)
            self.assertRegex(p.name, r"^[0-9a-f]{16}$")

    def test_la_partition_ne_cree_rien_sur_le_disque(self):
        with tempfile.TemporaryDirectory() as tmp:
            etat = Path(tmp) / "etat"  # NON cree
            os.environ["CADRE_STATE_DIR"] = str(etat)
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "projet")
            p = state_project()
            self.assertFalse(p.exists())
            self.assertFalse((etat / "projets").exists())
            self.assertFalse(etat.exists())

    def test_la_partition_suit_CADRE_STATE_DIR(self):
        with tempfile.TemporaryDirectory() as tmp:
            etat = Path(tmp) / "etat"
            os.environ["CADRE_STATE_DIR"] = str(etat)
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "projet")
            p = state_project()
            self.assertEqual(p.parent, etat.resolve() / "projets")
            self.assertTrue(p.is_relative_to(etat.resolve()),
                            f"la partition {p} sort de {etat} — $CADRE_STATE_DIR n est pas suivi")

    def test_le_separateur_est_normalise_meme_sur_une_racine_WINDOWS(self):
        # Empreinte mesurable sur une racine FABRIQUEE : on ne peut pas fabriquer
        # un vrai chemin Windows sur la machine de porte, mais PureWindowsPath
        # rend `str()` != `as_posix()`. Sans as_posix(), la moitie « separateur
        # normalise » de S-00001598 n'etait tenue par aucun temoin.
        from pathlib import PureWindowsPath
        from cadre.paths import _empreinte_de_racine
        win = PureWindowsPath(r"C:\a\Projet")
        self.assertEqual(_empreinte_de_racine(win),
                         hashlib.sha256(b"C:/a/Projet").hexdigest()[:16])
        self.assertNotEqual(_empreinte_de_racine(win),
                            hashlib.sha256(str(win).encode()).hexdigest()[:16])

    def test_un_chemin_non_decodable_ne_fait_pas_exploser_la_partition(self):
        # Mesure du 2026-09-20 : `cadre paths --json` mourait en traceback,
        # zero octet sur stdout, et la fonction etait inutilisable en bibliotheque.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "etat")
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "pro\udcffjet")
            p = state_project()                       # ne doit PAS lever
            self.assertRegex(p.name, r"^[0-9a-f]{16}$")
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "projet")
            self.assertNotEqual(p.name, state_project().name)

    def test_une_racine_EXISTANTE_donne_LA_MEME_partition_par_les_DEUX_branches(self):
        # Remplace l'ancien temoin d'epinglage (SYM-9065, S-00001651) :
        # les DEUX branches de project_root — $CADRE_PROJECT_ROOT et
        # git — rendent DESORMAIS la MEME empreinte pour UN repertoire a deux
        # graphies. On asserte l'EGALITE des ensembles, jamais un cardinal.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            sur_disque = tmp / "Projet"
            sur_disque.mkdir()
            insensible = (tmp / "projet").is_dir()
            if not insensible:
                # Le saut PRECEDE toute resolution : sur FS sensible, state_project
                # sur une graphie absente ferait echouer git puis la remontee et
                # leverait CadrePathError NON capturee.
                self.skipTest("FS sensible a la casse : deux graphies = deux depots")
            os.environ["CADRE_STATE_DIR"] = str(tmp / "etat")
            par_env = set()
            for graphie in (sur_disque, tmp / "projet"):        # branche 1
                os.environ["CADRE_PROJECT_ROOT"] = str(graphie)
                par_env.add(state_project().name)
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            subprocess.run(["git", "init", "-q", str(sur_disque)], check=True)
            par_git = set()
            for graphie in (sur_disque, tmp / "projet"):        # branche 2
                vider_cache_racine()
                par_git.add(state_project(str(graphie)).name)
            self.assertEqual(par_env, par_git,
                             "les deux branches ne rendent pas la MEME partition")

    def test_deux_depots_de_casse_differente_restent_DEUX_partitions_sur_FS_sensible(self):
        # DEUX BRAS QUI ASSERTENT, aucun skipTest : ce temoin ne saute sur aucune
        # jambe. Le bras sensible prouve le NON-REPLI, l'insensible rejoue l'accord
        # des branches (redondant par construction).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            (tmp / "Projet").mkdir()
            os.environ["CADRE_STATE_DIR"] = str(tmp / "etat")
            try:
                (tmp / "projet").mkdir()
            except FileExistsError:
                with self.subTest(bras="insensible"):
                    subprocess.run(["git", "init", "-q", str(tmp / "Projet")], check=True)
                    par_env = set()
                    for graphie in (tmp / "Projet", tmp / "projet"):
                        os.environ["CADRE_PROJECT_ROOT"] = str(graphie)
                        par_env.add(state_project().name)
                    os.environ.pop("CADRE_PROJECT_ROOT", None)
                    par_git = set()
                    for graphie in (tmp / "Projet", tmp / "projet"):
                        vider_cache_racine()
                        par_git.add(state_project(str(graphie)).name)
                    self.assertEqual(par_env, par_git)
            else:
                with self.subTest(bras="sensible"):
                    # deux inodes distincts : (i) conserve chaque graphie tapee.
                    self.assertEqual(canonique_disque(tmp / "projet"), tmp / "projet")
                    os.environ["CADRE_PROJECT_ROOT"] = str(tmp / "Projet")   # branche 1
                    n_haut = state_project().name
                    os.environ["CADRE_PROJECT_ROOT"] = str(tmp / "projet")   # branche 1
                    n_bas = state_project().name
                    os.environ.pop("CADRE_PROJECT_ROOT", None)
                    self.assertNotEqual(n_haut, n_bas)

    def test_le_marqueur_ancetre_rejoint_la_branche_environnement_sur_une_racine_EXISTANTE(self):
        # Branche 3 (remontee d'ancetres, SANS git) : elle rejoint la branche env
        # sur une racine EXISTANTE. $CADRE_PROJECT_ROOT reste RETIRE tout le temoin.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            os.environ["CADRE_STATE_DIR"] = str(tmp / "etat")
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            (tmp / "Projet" / ".agents").mkdir(parents=True)
            vider_cache_racine()
            a = state_project(depuis=tmp / "Projet").name
            try:
                (tmp / "projet").mkdir()
            except FileExistsError:
                with self.subTest(bras="insensible"):
                    vider_cache_racine()
                    b = state_project(depuis=tmp / "projet").name
                    self.assertEqual(a, b)
            else:
                with self.subTest(bras="sensible"):
                    (tmp / "projet" / ".agents").mkdir()
                    vider_cache_racine()
                    b = state_project(depuis=tmp / "projet").name
                    self.assertNotEqual(a, b)

    def test_une_OSError_pendant_la_canonicalisation_rend_le_chemin_d_entree_INCHANGE(self):
        # Probant SEULEMENT parce que canonique_disque appelle os.scandir par
        # ATTRIBUT de module (etape 2) : un `from os import scandir` rendrait ce
        # mock.patch INERTE et ce temoin vert meme sans la clause `except`.
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve() / "Projet"
            p.mkdir()
            # DANS le with tmp, AVANT sa fermeture : rmtree appelle os.scandir, la
            # rustine doit etre levee avant. os.lstat de (0) reussit, scandir de (i)
            # leve, la clause rend l'ENTREE inchangee.
            with mock.patch("os.scandir", side_effect=PermissionError("injectee")):
                self.assertEqual(canonique_disque(p), p)

    def test_une_graphie_NFC_rejoint_l_entree_NFD_du_disque(self):
        import unicodedata
        with tempfile.TemporaryDirectory() as tmp:
            # tmp resolu EN TETE : sur macOS $TMPDIR est /var/folders (lien vers
            # /private/var) ; canonique_disque ne resout AUCUN lien, git rend
            # /private — sans ce resolve() l'egalite rougirait pour une raison
            # etrangere au temoin.
            tmp = Path(tmp).resolve()
            nfd = tmp / unicodedata.normalize("NFD", "Projé")
            nfc = tmp / unicodedata.normalize("NFC", "Projé")
            nfd.mkdir()
            subprocess.run(["git", "init", "-q", str(nfd)], check=True)
            os.environ["CADRE_STATE_DIR"] = str(tmp / "etat")
            if nfc.exists():
                with self.subTest(bras="insensible"):
                    self.assertEqual(canonique_disque(nfc), canonique_disque(nfd))
                    sortie = subprocess.run(
                        ["git", "-C", str(nfd), "rev-parse", "--show-toplevel"],
                        capture_output=True, text=True, check=True).stdout.strip()
                    # l'attendu est la forme de git (jamais un litteral NFD fige).
                    self.assertEqual(canonique_disque(nfc), Path(sortie))
                    os.environ["CADRE_PROJECT_ROOT"] = str(nfc)
                    e_nfc = state_project().name
                    os.environ["CADRE_PROJECT_ROOT"] = str(nfd)
                    e_nfd = state_project().name
                    os.environ.pop("CADRE_PROJECT_ROOT", None)
                    vider_cache_racine()
                    e_git = state_project(str(nfc)).name
                    self.assertEqual(e_nfc, e_nfd)
                    self.assertEqual(e_nfc, e_git)
            else:
                with self.subTest(bras="sensible"):
                    self.assertEqual(canonique_disque(nfc), nfc)
                    nfc.mkdir()   # deux repertoires distincts

    def test_une_ValueError_pendant_la_canonicalisation_rend_le_chemin_d_entree_INCHANGE(self):
        # La moitie ValueError de `except (OSError, ValueError)` : os.lstat de (0)
        # leve (UnicodeEncodeError est une sous-classe de ValueError, PAS d'OSError —
        # borne Windows non mesuree) -> l'entree est conservee, jamais un traceback.
        # Probant parce que canonique_disque appelle os.lstat par ATTRIBUT de module.
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp).resolve() / "Projet"
            p.mkdir()
            # Rustine levee AVANT la fermeture du TemporaryDirectory (rmtree lstat).
            with mock.patch("os.lstat", side_effect=ValueError("injectee")):
                self.assertEqual(canonique_disque(p), p)

    def test_deux_candidates_casefold_egales_font_CONSERVER_le_composant_tape(self):
        # Le garde-fou « EXACTEMENT UNE » de (ii) : DEUX entrees casefold-egales au
        # composant tape, d'OCTETS differents, du MEME inode (doublure) -> la
        # fonction CONSERVE la graphie tapee, jamais de choix arbitraire. Sans
        # doublure, aucune coexistence casefold-egale de MEME inode n'existe sur un
        # FS reel (deux graphies d'UN repertoire ne sont qu'UNE entree).
        from types import SimpleNamespace
        from unittest import mock

        faux = [SimpleNamespace(name="Projet"), SimpleNamespace(name="PROJET")]
        faux_stat = SimpleNamespace(st_dev=1, st_ino=42)

        class _Scandir:
            def __enter__(self_inner):
                return iter(faux)

            def __exit__(self_inner, *exc):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp).resolve() / "projet"
            # Patchs leves AVANT la fermeture du TemporaryDirectory (rmtree scandir).
            with mock.patch("os.lstat", return_value=faux_stat), \
                 mock.patch("os.scandir", return_value=_Scandir()):
                self.assertEqual(canonique_disque(cible), cible)

    def test_la_casse_d_un_ANCETRE_est_corrigee_et_le_reste_INEXISTANT_reste_ENTIER(self):
        # Deux proprietes qu'aucun temoin ne tenait : (a) la casse se corrige sur un
        # ANCETRE, pas seulement sur la feuille ; (b) le correctif de (iii) trouve au
        # dev — un composant absent conserve CE composant ET tout le reste, jamais
        # une troncature du chemin.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            (tmp / "Projet" / "SousDir").mkdir(parents=True)
            cible = tmp / "projet" / "sousdir"
            if (tmp / "projet").is_dir():
                with self.subTest(bras="insensible"):
                    self.assertEqual(canonique_disque(cible), tmp / "Projet" / "SousDir")
            else:
                with self.subTest(bras="sensible"):
                    self.assertEqual(canonique_disque(cible), cible)
            jamais = tmp / "JaMaIsCree" / "SousDir" / "Encore"
            self.assertEqual(canonique_disque(jamais), jamais)

    def test_la_branche_git_canonicalise_AUSSI_quand_git_rend_une_autre_graphie(self):
        # BLOQUANT binome de cloture (opus T1 = fable 1) : sous GIT_WORK_TREE,
        # `git rev-parse --show-toplevel` rend la graphie TAPEE, pas celle du
        # disque. Sans canonicalisation de la SORTIE de git (branche 2), la racine
        # divergerait des branches 1 (env) et 3 (marqueur) — mesure opus.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            sur_disque = tmp / "Projet"
            sur_disque.mkdir()
            if not (tmp / "projet").is_dir():
                self.skipTest("FS sensible a la casse : deux graphies = deux depots")
            subprocess.run(["git", "init", "-q", str(sur_disque)], check=True)
            os.environ["CADRE_STATE_DIR"] = str(tmp / "etat")
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            os.environ["GIT_DIR"] = str(sur_disque / ".git")
            os.environ["GIT_WORK_TREE"] = str(tmp / "projet")
            self.addCleanup(os.environ.pop, "GIT_DIR", None)
            self.addCleanup(os.environ.pop, "GIT_WORK_TREE", None)
            vider_cache_racine()
            self.assertEqual(project_root(str(tmp / "projet")), sur_disque)

    def test_depuis_deplace_la_partition_et_CadrePathError_se_PROPAGE(self):
        # Les deux promesses de docstring qu aucun temoin ne tenait : ignorer
        # `depuis`, ou avaler l erreur, laissait le banc VERT (mesure 2026-09-20).
        # Le CLI ne les couvre pas non plus : _racines leve sur project_root()
        # AVANT d appeler state_project().
        from cadre.paths import CadrePathError
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "etat")
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            depot = Path(tmp) / "depot"
            (depot / ".agents").mkdir(parents=True)
            vider_cache_racine()
            self.assertNotEqual(state_project(str(depot)).name, state_project().name)
            orphelin = Path(tmp) / "orphelin"
            orphelin.mkdir()
            vider_cache_racine()
            with self.assertRaises(CadrePathError):
                state_project(str(orphelin))

    def test_state_project_est_dans___all___de_cadre_paths(self):
        # `git grep __all__ -- .agents/evals/` rendait ZERO le 2026-09-20 :
        # aucun banc ne lisait la surface publique DECLAREE d un module du noyau.
        self.assertIn("state_project", cadre.paths.__all__)


class NomProjetTests(_Base):
    """T-00000582 : `nom_projet()` = basename de la racine, re-derive a chaque
    lecture, repli LITTERAL 'projet' sur un basename vide, present dans __all__."""

    def test_nom_projet_est_le_basename_de_la_racine(self):
        # S-00001541 : une regle, zero branche -> project_root(depuis).name.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "mon-projet")
            self.assertEqual(nom_projet(), "mon-projet")

    def test_nom_projet_se_rederive_a_chaque_lecture(self):
        # S-00001542 : AUCUNE memoisation sur nom_projet. Reaffecter la variable
        # dans le MEME processus change le nom rendu (source ENV, pas le disque).
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "a")
            self.assertEqual(nom_projet(), "a")
            os.environ["CADRE_PROJECT_ROOT"] = str(Path(tmp) / "b")
            self.assertEqual(nom_projet(), "b")

    def test_nom_projet_repli_projet_sur_basename_vide(self):
        # Path("/").name == "" -> repli LITTERAL "projet", DISTINCT de
        # project_init.slugify (return slug or "project") : le slug est une CLE,
        # le nom un AFFICHAGE, ecart assume.
        os.environ["CADRE_PROJECT_ROOT"] = os.sep
        self.assertEqual(nom_projet(), "projet")

    def test_nom_projet_est_dans___all___de_cadre_paths(self):
        # __all__ est un filet (etape 1, test_cadre_state_partition lit la
        # surface publique DECLAREE), comme pour state_project.
        self.assertIn("nom_projet", cadre.paths.__all__)


class StabiliteProcessusTests(_Base):
    """Temoin 7 : stabilite d'un processus a l'autre."""

    def test_la_partition_est_stable_d_un_processus_a_l_autre(self):
        with tempfile.TemporaryDirectory() as tmp:
            # env par FILTRAGE EXPLICITE (jamais os.environ nu). PYTHONHASHSEED est
            # RETIRE, jamais pose : herite d'un lanceur, il figerait la
            # randomisation de hash() et rendrait la mutation `hash()` INVISIBLE.
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("CADRE_") and k != "PYTHONHASHSEED"} | {
                "PYTHONPATH": str(_VENDOR.parent_import(ROOT, "cadre")),
                "CADRE_PROJECT_ROOT": str(Path(tmp) / "projet"),
                "CADRE_STATE_DIR": str(Path(tmp) / "etat"),
            }

            def lire():
                r = subprocess.run(
                    [sys.executable, "-m", "cadre.cli", "paths", "--json"],
                    capture_output=True, text=True, cwd=str(ROOT), env=env)
                self.assertEqual(r.returncode, 0, r.stderr)
                return json.loads(r.stdout)["STATE_PROJECT"]

            v1 = lire()
            v2 = lire()
        self.assertIsNotNone(v1)
        self.assertEqual(v1, v2)


class ControlePerimetreTests(_Base):
    """Temoin 8 : le check et son controle negatif."""

    def test_check_state_partition_et_son_controle_negatif(self):
        # (a) perimetre REEL : l'ensemble des (fichier, fonction englobante)
        # portant un APPEL a state_home dans le paquet `cadre` est EXACTEMENT
        # {paths.py::state_project, cli.py::_racines}. Le resume du manifeste
        # promet la FONCTION cli.py::_racines ; mesurer le seul FICHIER laissait
        # un appel dans cli.py::main passer au VERT (mesure 2026-09-20, par les
        # DEUX critiques). Egalite CLOSE et assumee ; tout appelant neuf rougit,
        # l'amendement est un geste conscient d'une ligne.
        pkg = PKG
        fautifs = {(py.relative_to(pkg).as_posix(), fn)
                   for py in pkg.rglob("*.py")
                   for fn in _appels_state_home(py.read_text(encoding="utf-8"))}
        self.assertEqual(fautifs, {("paths.py", "state_project"), ("cli.py", "_racines")})

        # (b) controle negatif : une source synthetique portant UN appel reel et
        # DEUX leurres textuels -> EXACTEMENT un fautif, nomme par sa fonction. Les
        # leurres distinguent l'AST du texte.
        synth = (
            "def a():\n"
            "    return state_home() / 'p'\n"
            "# state_home() n'est pas appele ici (leurre commentaire)\n"
            "s = \"state_home()\"  # leurre litteral\n"
        )
        self.assertEqual(_appels_state_home(synth), ["a"])


class ManifesteTests(_Base):
    """Temoin 9 : l'entree du manifeste, sa presence ET sa position."""

    def test_l_entree_du_manifeste_nomme_ce_banc_ET_LA_POSITIONNE(self):
        if not MANIFESTE.is_file():
            self.skipTest("arbre adoptant : ce registre n'est pas le sien")
        entrees = json.loads(MANIFESTE.read_text(encoding="utf-8"))["checks"]
        noms = [e["nom"] for e in entrees]
        # Bornes AVANT tout indexage : un ValueError/IndexError opaque
        # remplacerait un echec NOMME.
        self.assertIn("check_sql_locality", noms)
        self.assertEqual(noms.count("check_state_partition"), 1)

        entree = next(e for e in entrees if e["nom"] == "check_state_partition")
        self.assertEqual(entree["statut"], "actif")
        self.assertEqual(entree["phase"], "2")
        self.assertEqual(
            entree["implementation"],
            Path(__file__).resolve().relative_to(ROOT).as_posix())

        i = noms.index("check_sql_locality")
        self.assertLess(i + 1, len(noms),
                        "check_sql_locality est la derniere entree — re-ancrer l'adjacence")
        self.assertEqual(
            noms[i + 1], "check_state_partition",
            "l'adjacence unique de l'etape 6 a ete perdue — re-ancrer, jamais retirer cette assertion")


class ProseTests(_Base):
    """Temoins 10 et 11 : l'accord texte <-> code sur le cardinal ET les noms."""

    def test_les_textes_qui_annoncent_un_CARDINAL_de_cles_disent_le_bon(self):
        cles = set(_racines()) - {"erreur"}
        self.assertEqual(cles, CLES_ATTENDUES)
        n = len(_racines())  # 7, `erreur` comprise
        self.assertIn(n, MOTS)

        # Le TEXTE de cli.py (pas __doc__) : ce cardinal garde un sens sous -OO.
        p_cli = PKG / "cli.py"
        self.assertTrue(p_cli.is_file(),
                        f"{p_cli} absent : ce temoin lit le TEXTE livre, pas __doc__")
        txt_cli = p_cli.read_text(encoding="utf-8")
        m = re.search(r"TOUJOURS LES (\w+) CLÉS", txt_cli)
        self.assertIsNotNone(
            m, f"{p_cli} n'annonce plus AUCUN cardinal — la phrase a DISPARU")
        self.assertEqual(m.group(1), MOTS[n])

        elements = _elements_cadre_paths()
        self.assertEqual(
            len(elements), 1,
            "l element `cadre paths` du verrou a disparu ou est en double — "
            "T-00000647 ecrit contract.lock.json : re-ancrer, jamais retirer l assertion")
        note = elements[0]["note"]
        m2 = re.search(r"TOUJOURS les (\w+) cles", note)
        self.assertIsNotNone(
            m2, "la note du verrou n'annonce plus AUCUN cardinal — la phrase a DISPARU")
        self.assertEqual(m2.group(1), MOTS[n].lower())
        # La note NOMME chacune des cles.
        for cle in cles:
            self.assertIn(cle, note)

    def test_le_docstring_de_paths_nomme_TOUTES_les_cles_rendues(self):
        cles = set(_racines()) - {"erreur"}
        self.assertEqual(cles, CLES_ATTENDUES)
        # L'ATTRIBUT, pas le fichier : c'est ce que l'adoptant recoit dans la
        # wheel, et c'est aussi ce qu'un interpreteur -OO met a None.
        doc = cadre.paths.__doc__
        self.assertTrue(
            doc, "le docstring de module est vide ou depouille (python -OO) : ce temoin ne mesurerait rien")
        for cle in cles:
            self.assertIn(cle, doc)

    def test_les_deux_enumerations_de_cles_du_depot_sont_D_ACCORD(self):
        # « UN SEUL endroit a amender » etait faux : test_cadre_package.py
        # enumere le MEME jeu (avec `erreur`). Rouge a la DIVERGENCE, plutot qu a
        # la 8e cle.
        txt = (ROOT / ".agents" / "evals" / "test_cadre_package.py").read_text(encoding="utf-8")
        m = re.search(r"attendues = \{([^}]*)\}", txt, re.S)
        self.assertIsNotNone(m, "l ensemble `attendues` de SYM-7690 a disparu")
        vu = {s.strip().strip('"') for s in m.group(1).split(",") if s.strip()}
        self.assertEqual(vu, CLES_ATTENDUES | {"erreur"})


#: Le banc RÉEL de `.agents/bin/` qu'observe le Témoin 12 : deux tests, aucune
#: écriture du dépôt. Retiré ou renommé, le témoin rougit en le NOMMANT — on en
#: choisit alors un autre d'au moins deux tests, jamais on ne retire le témoin.
BANC_AGENTS_BIN = ROOT / ".agents" / "bin" / "test_stop_reindex_domaine.py"

#: Le banc RÉEL de `.agents/bin/` qui appelle `monkeypatch.undo()` dans son corps,
#: observé en FIN de test : sans marque de saut (un saut levé au setup empêche la
#: fixture de tourner, le témoin rougirait à tort) et sans sous-processus. S'il
#: disparaît ou cesse d'appeler `undo()`, le témoin rougit en le NOMMANT — on en
#: choisit alors un autre (`LC_ALL=C git grep -n 'monkeypatch.undo()' --
#: '.agents/bin/*.py'`), jamais on ne retire le témoin.
BANC_UNDO = ROOT / ".agents" / "bin" / "test_event_store.py"
TEST_UNDO = "test_un_events_db_disparu_avant_l_ouverture_n_est_pas_un_refus_t770"


def _test_appelle_monkeypatch_undo(banc: Path, nom: str) -> bool:
    """Vrai si la fonction de test `nom`, au niveau module de `banc`, appelle `monkeypatch.undo()`."""
    if not banc.is_file():
        return False
    arbre = ast.parse(banc.read_text(encoding="utf-8"))
    for noeud in arbre.body:
        if isinstance(noeud, ast.FunctionDef) and noeud.name == nom:
            return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr == "undo" and isinstance(n.func.value, ast.Name)
                       and n.func.value.id == "monkeypatch" for n in ast.walk(noeud))
    return False


#: La sonde que le pytest ENFANT charge par `-p`, depuis un dossier temporaire
#: HORS du dépôt. `tryfirst` sur `pytest_runtest_call` : les fixtures du test sont
#: posées, ni son `setUp` ni son corps n'ont tourné — la valeur relevée est celle
#: de la fixture, jamais celle qu'un banc se pose lui-même. `tryfirst` sur
#: `pytest_runtest_teardown` : le corps (et le `tearDown` d'un `unittest`) a tourné,
#: aucun finaliseur de fixture encore — la valeur relevée est celle que le banc
#: LAISSE, avant que la garde ne soit rendue.
SONDE_T758 = '''\
import json
import os
import sys

import pytest


def _ecrire(releve):
    with open(os.environ["SONDE_T758_SORTIE"], "a", encoding="utf-8") as f:
        f.write(json.dumps(releve) + "\\n")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    module = sys.modules.get("conftest")
    _ecrire({"phase": "appel", "test": item.nodeid,
             "etat": os.environ.get("CADRE_STATE_DIR"),
             "conftest": getattr(module, "__file__", None)})


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    _ecrire({"phase": "fin", "test": item.nodeid,
             "etat": os.environ.get("CADRE_STATE_DIR")})
'''


class FixtureAgentsBinTests(_Base):
    """Temoin 12 — le « T9 » de l'enonce de T-00000758 (BK-422), distinct du
    Temoin 9 ci-dessus : la fixture `autouse` de `.agents/bin/conftest.py` FORCE un
    `CADRE_STATE_DIR` neuf PAR TEST, meme quand l'appelant en a pose un.

    La fixture n'est pas visible d'ici (`.agents/evals/`) : le temoin lance un
    pytest ENFANT sur un VRAI banc de `.agents/bin/` (consigne S-00004599), avec
    une sonde chargee depuis un dossier temporaire hors du depot ; rien n'est
    ecrit dans l'arbre (`-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE`). L'enfant
    recoit un `CADRE_STATE_DIR` SENTINELLE, le cas d'un appelant qui exporte le
    vrai `~/.local/state/cadre` : le filet de session du `conftest.py` racine le
    RESPECTE, donc seule la fixture de `.agents/bin/` peut l'ecarter.
    `XDG_STATE_HOME` et `TMPDIR` sont repointes dans le meme temporaire : aucun
    repli de l'enfant n'atteint l'etat de la machine.

    Le troisieme test releve la valeur en FIN de test, sur un banc qui appelle
    `monkeypatch.undo()` dans son corps : une garde posee par la fixture
    `monkeypatch` PARTAGEE avec le test y serait defaite, et le banc finirait sur
    la valeur de l'appelant.

    Mutations mesurees, toutes rouges : fixture retiree, `autouse=False`, fixture
    qui ne pose la variable que si elle est absente, un meme dossier pour tous les
    tests (premier test) ; garde posee par la fixture `monkeypatch` partagee
    (troisieme test) ; pont `pytest_configure` retire (second test)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        dossier = tempfile.TemporaryDirectory(prefix="t758-", ignore_cleanup_errors=True)
        cls.addClassCleanup(dossier.cleanup)
        tmp = Path(dossier.name)
        sonde = tmp / "sonde"
        sonde.mkdir()
        (sonde / "sonde_etat_t758.py").write_text(SONDE_T758, encoding="utf-8")
        (tmp / "tmpdir").mkdir()
        cls.sentinelle = tmp / "etat-de-l-appelant"
        cls.basetemp = tmp / "basetemp"
        sortie = tmp / "releves.jsonl"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CADRE_", "PYTEST_"))}
        env.update({
            "CADRE_STATE_DIR": str(cls.sentinelle),
            "XDG_STATE_HOME": str(tmp / "xdg-state"),
            "TMPDIR": str(tmp / "tmpdir"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(p for p in (str(sonde), os.environ.get("PYTHONPATH")) if p),
            "SONDE_T758_SORTIE": str(sortie),
        })
        # Le banc `undo` n'est lance que s'il appelle encore `monkeypatch.undo()` :
        # absent ou renomme, le troisieme test le NOMME au lieu de laisser l'enfant
        # rendre « not found » aux trois.
        cls.undo_present = _test_appelle_monkeypatch_undo(BANC_UNDO, TEST_UNDO)
        cls.cibles = [str(BANC_AGENTS_BIN)] + ([f"{BANC_UNDO}::{TEST_UNDO}"] if cls.undo_present else [])
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-p", "sonde_etat_t758", "--basetemp", str(cls.basetemp), *cls.cibles],
            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=300, check=False)
        cls.rc = r.returncode
        cls.journal = (r.stdout + r.stderr)[-3000:]
        tous = ([json.loads(ligne) for ligne in sortie.read_text(encoding="utf-8").splitlines()]
                if sortie.is_file() else [])
        cls.releves = [t for t in tous if t.get("phase") == "appel"]
        cls.fins = [t for t in tous if t.get("phase") == "fin"]

    def _exiger_le_releve(self):
        self.assertTrue(BANC_AGENTS_BIN.is_file(),
                        f"banc observe absent : {BANC_AGENTS_BIN} — en choisir un autre "
                        "d'au moins deux tests, jamais retirer ce temoin")
        self.assertEqual(self.rc, 0, f"pytest enfant rc={self.rc}\n{self.journal}")
        self.assertGreaterEqual(len(self.releves), 2,
                                f"la sonde a releve {len(self.releves)} test(s), au moins 2 attendus "
                                f"(cibles lancees : {self.cibles})\n{self.journal}")

    def test_la_fixture_de_agents_bin_FORCE_un_CADRE_STATE_DIR_neuf_par_test(self):
        self._exiger_le_releve()
        base = self.basetemp.resolve()
        for r in self.releves:
            with self.subTest(test=r["test"]):
                self.assertIsNotNone(r["etat"], "CADRE_STATE_DIR absent pendant un banc de .agents/bin")
                etat = Path(r["etat"]).resolve()
                self.assertNotEqual(
                    etat, self.sentinelle.resolve(),
                    "le banc a HERITE le CADRE_STATE_DIR de l'appelant : fixture de "
                    ".agents/bin/conftest.py retiree, non autouse, ou qui respecte une valeur posee")
                self.assertTrue(etat.is_relative_to(base),
                                f"{etat} hors du basetemp {base} du pytest enfant")
        etats = [r["etat"] for r in self.releves]
        self.assertEqual(len(set(etats)), len(etats),
                         f"un meme CADRE_STATE_DIR partage entre des tests : {etats}")

    def test_la_garde_TIENT_jusqu_a_la_fin_d_un_banc_qui_appelle_monkeypatch_undo(self):
        self.assertTrue(self.undo_present,
                        f"banc observe absent ou sans `monkeypatch.undo()` : {BANC_UNDO}::{TEST_UNDO} "
                        "— en choisir un autre qui l'appelle, sans marque de saut, jamais retirer ce temoin")
        self._exiger_le_releve()
        sentinelle = self.sentinelle.resolve()
        appel = [r for r in self.releves if r["test"].endswith("::" + TEST_UNDO)]
        fin = [r for r in self.fins if r["test"].endswith("::" + TEST_UNDO)]
        self.assertEqual((len(appel), len(fin)), (1, 1),
                         f"releves du banc undo (appel, fin) : {appel} {fin}\n{self.journal}")
        self.assertIsNotNone(fin[0]["etat"], "CADRE_STATE_DIR absent en fin du banc undo")
        self.assertNotEqual(
            Path(fin[0]["etat"]).resolve(), sentinelle,
            "le banc FINIT sur le CADRE_STATE_DIR de l'appelant : son `monkeypatch.undo()` a "
            "defait la garde — fixture de .agents/bin/conftest.py repassee par la fixture "
            "`monkeypatch` partagee avec le test")
        self.assertEqual(fin[0]["etat"], appel[0]["etat"],
                         "la valeur de fin n'est plus celle que la fixture a posee pour ce test")
        self.assertTrue(Path(fin[0]["etat"]).resolve().is_relative_to(self.basetemp.resolve()))
        for r in self.fins:
            with self.subTest(test=r["test"]):
                self.assertIsNotNone(r["etat"], "CADRE_STATE_DIR absent en fin de banc")
                self.assertNotEqual(Path(r["etat"]).resolve(), sentinelle,
                                    "un banc de .agents/bin FINIT sur le CADRE_STATE_DIR de l'appelant")

    def test_le_conftest_de_agents_bin_n_ombre_pas_le_conftest_racine(self):
        racine = ROOT / "conftest.py"
        if not racine.is_file():
            self.skipTest("arbre sans conftest.py racine : rien a ombrer")
        self._exiger_le_releve()
        for r in self.releves:
            with self.subTest(test=r["test"]):
                self.assertEqual(
                    Path(r["conftest"] or "").resolve(), racine.resolve(),
                    "sys.modules['conftest'] n'est plus le conftest racine : "
                    "`from conftest import greffe_email_git_franchissable` levera "
                    "ImportError dans les bancs collectes apres .agents/bin/")


if __name__ == "__main__":
    unittest.main()
