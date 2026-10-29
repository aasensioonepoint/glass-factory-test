#!/usr/bin/env python3
"""Bancs de `Workspace` et `LocalExecutor` — les deux coutures de la Phase 1.

Ces deux classes existent pour être REMPLACÉES un jour : `paths` résout,
`Workspace` fait les E/S, `Executor` lance les commandes, et le déport promis
par le §5-A du plan remplacera les deux dernières sans toucher à ce qui les
appelle. Un banc qui ne mesurerait que le chemin nominal ne protégerait pas
cette promesse ; ce qui compte ici, ce sont les REFUS et les cas limites.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import stat
import subprocess
import tempfile
import threading
import time
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# `cadre` là où la règle de `vendor_paths` le désigne (vendor d'abord, `src` sinon),
# chargé par chemin : aucune entrée neuve en tête de `sys.path`.
_SPEC_VP = importlib.util.spec_from_file_location(
    "_workspace_executor_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
VENDOR = importlib.util.module_from_spec(_SPEC_VP)
sys.modules[_SPEC_VP.name] = VENDOR
_SPEC_VP.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")

from cadre import workspace as module_workspace  # noqa: E402
from cadre.executor import ExecutionRefusee, LocalExecutor, Resultat  # noqa: E402
from cadre.workspace import HorsRacine, Workspace, remplacer_avec_reprise  # noqa: E402


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = Workspace(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cadre_charge_est_celui_que_vendor_paths_designe(self):
        """Arbre « les deux » : le paquet vendor, jamais `src/cadre` mis en tete."""
        attendu, _origine = VENDOR.verifier_charge(ROOT, "cadre")
        self.assertEqual(attendu, Path(module_workspace.__file__).resolve().parent)

    def test_aller_retour_fidele_aux_octets(self):
        """Les fins de ligne ne sont PAS traduites — c'est ce qui empêche un
        aller-retour de réécrire un fichier entier sous Windows."""
        contenu = "a\nb\r\nc\n"
        self.w.write_text("f.txt", contenu)
        self.assertEqual(self.w.read_text("f.txt"), contenu)

    def test_l_ecriture_cree_les_repertoires_manquants(self):
        self.w.write_text("x/y/z.txt", "ok")
        self.assertTrue(self.w.exists("x/y/z.txt"))

    def test_l_ecriture_ne_laisse_aucun_temporaire(self):
        """Un résidu de `.cadre-tmp` serait ramassé par un `git add -A` — le
        motif exact qui a coûté une entrée aux actions du pilote ce jour-là."""
        self.w.write_text("a/b.txt", "x")
        restes = [p.name for p in (Path(self._tmp.name) / "a").iterdir()]
        self.assertEqual(restes, ["b.txt"])

    def test_l_ecriture_est_atomique_sur_un_fichier_existant(self):
        """Une écriture qui échoue laisse l'ANCIEN contenu, jamais un fichier
        tronqué. Mesuré ailleurs dans le kit : une écriture interrompue laissait
        un marqueur de porte vide, donc une garde qui passait en silence."""
        self.w.write_text("f.txt", "ancien")
        cible = self.w.resolve("f.txt")
        avant = cible.read_bytes()
        with self.assertRaises(TypeError):
            self.w.write_bytes("f.txt", "x")  # type: ignore[arg-type]
        self.assertEqual(cible.read_bytes(), avant, "l'ancien contenu a ete perdu")
        restes = [p.name for p in cible.parent.iterdir() if p.name.endswith(".cadre-tmp")]
        self.assertEqual(restes, [], "un temporaire survit a l'echec")

    def test_un_chemin_qui_sort_de_la_racine_est_refuse(self):
        for evasion in ("../dehors", "a/../../dehors", "/etc/passwd"):
            with self.subTest(chemin=evasion), self.assertRaises(HorsRacine):
                self.w.resolve(evasion)

    def test_un_lien_qui_remonte_est_refuse(self):
        """LA MOITIÉ QU'UNE COMPARAISON LEXICALE RATE. Un lien symbolique dont
        le nom est innocent mais la cible hors de l'arbre passerait un contrôle
        de chaîne ; la résolution le voit."""
        dehors = Path(self._tmp.name).parent / "cible-hors-arbre"
        dehors.mkdir(exist_ok=True)
        lien = Path(self._tmp.name) / "innocent"
        try:
            lien.symlink_to(dehors, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        with self.assertRaises(HorsRacine):
            self.w.resolve("innocent/x.txt")

    def test_exists_hors_racine_rend_faux_sans_lever(self):
        """Une question rend une réponse ; seule une ACTION refuse."""
        self.assertFalse(self.w.exists("../../etc/passwd"))

    def test_iter_files_est_trie(self):
        """Un ordre de système de fichiers n'est pas stable d'une plateforme à
        l'autre : un banc qui en dépend est vert ici et rouge en CI."""
        for nom in ("c.txt", "a.txt", "b.txt"):
            self.w.write_text(nom, "x")
        self.assertEqual([p.name for p in self.w.iter_files("*.txt")],
                         ["a.txt", "b.txt", "c.txt"])

    # -- les constats de la revue de clôture du 2026-09-12 --------------

    def test_iter_files_NE_rend_PAS_un_lien_qui_sort_de_la_racine(self):
        """UNE MÉTHODE SUR SIX N'APPLIQUAIT PAS LA GARDE DE SA CLASSE.

        Le module annonce en tête qu'un lien symbolique qui remonte est refusé,
        et `iter_files` globait sans passer par `resolve`. Mesuré : un lien
        interne vers `/etc/hosts` était rendu comme un fichier du projet. Une
        garde énoncée pour la classe et tenue par cinq méthodes sur six est une
        garde dont personne ne connaît la vraie portée.
        """
        self.w.write_text("dedans.txt", "x")
        lien = Path(self._tmp.name) / "dehors"
        try:
            os.symlink(os.devnull if os.name != "nt" else "NUL", lien)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        noms = [p.name for p in self.w.iter_files()]
        self.assertIn("dedans.txt", noms, "le confinement a mange un fichier legitime")
        self.assertNotIn("dehors", noms)

    def test_l_ecriture_PRESERVE_le_mode_du_fichier_existant(self):
        """`os.replace` remplace la cible ET SES PERMISSIONS par celles du
        temporaire, que `mkstemp` crée en 0600. Mesuré : un `.sh` en 0755
        réécrit ressortait en 0644 — donc un hook non exécutable, donc une garde
        qui ne mord plus. C'est la classe de défaut la plus discrète du lot : le
        contenu est correct, et seule la prochaine exécution échoue."""
        if os.name == "nt":
            self.skipTest("les bits POSIX n'ont pas de sens sous Windows")
        cible = Path(self._tmp.name) / "hook.sh"
        self.w.write_text("hook.sh", "#!/bin/sh\n")
        os.chmod(cible, 0o755)
        self.w.write_text("hook.sh", "#!/bin/sh\necho relu\n")
        self.assertEqual(stat.S_IMODE(cible.stat().st_mode), 0o755)

    def test_deux_ecrivains_concurrents_ne_se_detruisent_pas(self):
        """Le temporaire portait un nom FIXE — `<cible>.cadre-tmp` — donc deux
        écrivains sur la même cible écrivaient le MÊME inode, et le nettoyage de
        l'un supprimait le temporaire en vol de l'autre. Mesuré :
        `FileNotFoundError` sous trois fils. L'atomicité tenait le crash et pas
        le voisin, ce que la docstring du module ne disait pas — et le kit lance
        des shards en parallèle."""
        erreurs: list[str] = []

        def ecrire(taille: int) -> None:
            try:
                for _ in range(40):
                    self.w.write_text("concurrent.txt", "x" * taille)
            except Exception as exc:  # noqa: BLE001 — on veut la CLASSE
                erreurs.append(type(exc).__name__)

        fils = [threading.Thread(target=ecrire, args=(n,)) for n in (50, 150, 250)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        self.assertEqual(erreurs, [], f"ecritures concurrentes en echec : {erreurs}")
        # ET LE CONTENU RESTE ENTIER : un lecteur ne voit jamais un fichier
        # a moitie ecrit, seulement l'une ou l'autre des versions completes.
        self.assertIn(len(self.w.read_text("concurrent.txt")), (50, 150, 250))

    # -- les deux primitives de parcours de T-00000633 -----------------

    def test_walk_rend_du_RELATIF_et_iter_files_de_l_ABSOLU(self):
        """L'ASYMÉTRIE ASSUMÉE, ÉPINGLÉE CÔTE À CÔTE. `walk` rend un chemin
        POSIX relatif (`"."` à la racine) ; `iter_files` rend des `Path`
        absolus. Un futur « harmonisons » qui retourne l'une des deux casse ce
        test au lieu de glisser en silence. On ÉCRIT un fichier et on asserte
        que la liste est non vide AVANT le `all(...)` : sur un atelier vide,
        `all(...)` serait vrai par vacuité."""
        self.w.write_text("a/b.txt", "x")
        premier_rel = next(iter(self.w.walk(".")))[0]
        self.assertEqual(premier_rel, ".", "le premier triplet n'est pas ancre a `.`")
        fichiers = list(self.w.iter_files())
        self.assertTrue(fichiers, "atelier vide : `all(...)` serait vrai par vacuite")
        self.assertTrue(all(p.is_absolute() for p in fichiers),
                        "iter_files doit rendre des chemins ABSOLUS")

    def test_walk_elague_par_predicat_et_le_defaut_n_elague_rien(self):
        """L'élagage est un PRÉDICAT porté par l'appelant. Le défaut ne coupe
        rien ; un prédicat coupe la branche nommée À TOUTE PROFONDEUR."""
        for rel in ("garder/test_ok.py", "sauter/dedans/test_ko.py",
                    "sauter/test_ko.py"):
            self.w.write_text(rel, "x")
        sans = {rel for rel, _r, _f in self.w.walk(".")}
        self.assertIn("sauter", sans)
        self.assertIn("sauter/dedans", sans)
        avec = {rel for rel, _r, _f in self.w.walk(elaguer={"sauter"}.__contains__)}
        self.assertIn("garder", avec)
        self.assertNotIn("sauter", avec)
        self.assertNotIn("sauter/dedans", avec,
                         "l'elagage doit mordre A TOUTE PROFONDEUR")

    def test_walk_a_la_racine_rend_le_point(self):
        """Sans argument, le parcours part de la racine et son premier chemin
        rendu est `"."` — jamais `""`, qu'un `testpaths` lirait comme vide."""
        self.w.write_text("test_x.py", "x")
        rels = [rel for rel, _r, _f in self.w.walk()]
        self.assertEqual(rels[0], ".")

    def test_walk_depuis_un_SOUS_repertoire_rend_du_relatif_a_la_RACINE(self):
        """`walk(sous)` avec `sous != "."` : les chemins rendus restent RELATIFS
        À LA RACINE, jamais au point de départ. Sans ce banc, un futur
        `relative_to(depart)` passerait toute la suite — ses dix autres appels
        partent de `"."`, où `depart == racine`, donc ne discriminent rien."""
        self.w.write_text("a/b/test_x.py", "x")
        self.assertEqual(sorted(rel for rel, _r, _f in self.w.walk("a")),
                         ["a", "a/b"])
        self.assertEqual(sorted(rel for rel, _r, _f in self.w.walk("a/b")),
                         ["a/b"])

    def test_walk_refuse_de_sortir_de_l_arbre(self):
        """Le départ est confiné : viser hors de la racine est un `HorsRacine`,
        levé À l'itération (le corps d'un générateur ne tourne qu'alors)."""
        with self.assertRaises(HorsRacine):
            list(self.w.walk("../.."))

    @staticmethod
    def _scandir_refuse(nom_refuse: str):
        """Un `os.scandir` qui LÈVE `PermissionError` sur le repertoire nomme
        `nom_refuse` et DELEGUE a l'original partout ailleurs.

        `os.walk` scanne le disque par `os.scandir` (verifie sur son corps :
        `with scandir(top) as entries`) et route toute erreur vers `onerror` ;
        injecter le refus ICI reproduit un `chmod 000` mais SANS dependre des
        droits — donc le banc EXERCE la faute meme sur un hote root, ou un
        `chmod 000` ne refuse rien et ou la garde `os.access` faisait skipper la
        suite EN SILENCE (jambe conteneur de `verify.sh --linux`)."""
        vrai = os.scandir

        def _faux(chemin=".", *a, **k):
            if os.path.basename(os.fspath(chemin)) == nom_refuse:
                raise PermissionError(13, "Permission denied", os.fspath(chemin))
            return vrai(chemin, *a, **k)

        return _faux

    def test_walk_sans_sur_erreur_LEVE_sur_un_repertoire_illisible(self):
        """`sur_erreur=None` INVERSE le défaut d'`os.walk` : au lieu d'avaler
        l'erreur en silence, il la LÈVE. BRAS 1 (toujours exercé, indépendant des
        droits) : illisibilité injectée par `os.scandir` mocké. BRAS 2 (quand les
        droits mordent) : `chmod 000` RÉEL, jamais seul. Un `chmod 000` faisait
        sinon disparaitre un repertoire de bancs sans une ligne (mesure 16/09)."""
        if os.name == "nt":
            self.skipTest("`os.scandir` mocke cible POSIX (la faute 16/09 est POSIX)")
        secret = Path(self._tmp.name) / "secret"
        secret.mkdir()
        (secret / "test_dedans.py").write_text("x", encoding="utf-8")

        with self.subTest(bras="scandir-mocke"):
            with mock.patch("os.scandir", side_effect=self._scandir_refuse("secret")):
                with self.assertRaises(OSError):
                    list(self.w.walk("."))

        os.chmod(secret, 0o000)
        try:
            if not os.access(secret, os.R_OK):
                with self.subTest(bras="chmod-000-reel"), self.assertRaises(OSError):
                    list(self.w.walk("."))
        finally:
            os.chmod(secret, 0o755)

    def test_walk_avec_sur_erreur_COLLECTE_sans_lever(self):
        """Avec un collecteur, l'erreur va dans la liste et le parcours CONTINUE.
        BRAS 1 (indépendant des droits) : `os.scandir` mocké ; BRAS 2 : `chmod
        000` RÉEL quand les droits mordent — jamais comme seule voie."""
        if os.name == "nt":
            self.skipTest("`os.scandir` mocke cible POSIX (la faute 16/09 est POSIX)")
        secret = Path(self._tmp.name) / "secret"
        secret.mkdir()

        with self.subTest(bras="scandir-mocke"):
            with mock.patch("os.scandir", side_effect=self._scandir_refuse("secret")):
                vus: list[OSError] = []
                list(self.w.walk(".", sur_erreur=vus.append))
                self.assertTrue(vus, "l'erreur injectee n'a pas ete collectee")
                self.assertTrue(all(isinstance(e, OSError) for e in vus))

        os.chmod(secret, 0o000)
        try:
            if not os.access(secret, os.R_OK):
                with self.subTest(bras="chmod-000-reel"):
                    vus2: list[OSError] = []
                    list(self.w.walk(".", sur_erreur=vus2.append))
                    self.assertTrue(vus2, "l'erreur reelle n'a pas ete collectee")
        finally:
            os.chmod(secret, 0o755)

    def test_walk_NE_suit_PAS_les_liens_symboliques(self):
        """`followlinks=False` : un arbre atteint par lien n'est PAS descendu,
        ce qui borne les boucles et les sorties d'arbre."""
        cible = Path(self._tmp.name) / "vrai"
        cible.mkdir()
        (cible / "test_dedans.py").write_text("x", encoding="utf-8")
        lien = Path(self._tmp.name) / "lien"
        try:
            lien.symlink_to(cible, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        descendus = {rel for rel, _r, _f in self.w.walk(".")}
        self.assertIn("vrai", descendus)
        self.assertFalse(any(r.startswith("lien/") for r in descendus),
                         "un lien symbolique a ete suivi")

    def test_les_capacites_de_l_hote_sont_exercees(self):
        """CONTRE-TÉMOIN de la garde de portabilité du banc symbolique. Ce banc
        garde son `skipTest` « liens indisponibles » ; sans ce contre-témoin, la
        jambe conteneur (Linux) pourrait VERDIR sans jamais exercer le non-suivi
        de lien. Sur POSIX, `os.symlink` DOIT etre present ET fonctionner — donc
        le skip n'y est JAMAIS admis, et un poste POSIX ou le lien echoue ROUGIT
        au lieu de se taire. Hors POSIX, le skip reste motive."""
        if os.name != "posix":
            self.skipTest("capacite de lien symbolique non garantie hors POSIX")
        self.assertTrue(
            hasattr(os, "symlink"),
            "os.symlink absent sur un POSIX — le banc symbolique se tairait",
        )
        cible = Path(self._tmp.name) / "cible_cap"
        cible.mkdir()
        lien = Path(self._tmp.name) / "lien_cap"
        os.symlink(cible, lien)  # sur POSIX : reussit, sinon ROUGE (jamais un skip)
        self.assertTrue(lien.is_symlink(), "le lien symbolique n'a pas ete cree")

    def test_est_repertoire_vrai_sur_un_repertoire_faux_sinon(self):
        self.w.write_text("sous/f.txt", "x")
        self.assertTrue(self.w.est_repertoire("sous"))
        self.assertFalse(self.w.est_repertoire("sous/f.txt"),
                         "un fichier n'est pas un repertoire")
        self.assertFalse(self.w.est_repertoire("absent"))

    def test_est_repertoire_repond_sur_la_racine_par_defaut(self):
        """Le défaut `"."` interroge la racine elle-même — acceptée par la
        garde `candidat == self.racine`, jamais un `HorsRacine`."""
        self.assertTrue(self.w.est_repertoire())

    def test_est_repertoire_hors_racine_rend_faux_sans_lever(self):
        """Comme `exists` : une question rend une réponse, seule une action
        refuse."""
        self.assertFalse(self.w.est_repertoire("../../etc"))

    @staticmethod
    def _stat_qui_leve(cible, exc):
        """Un `os.stat` qui LÈVE `exc` sur le chemin `cible` et délègue à
        l'original ailleurs (T-00001232)."""
        vrai = os.stat

        def _faux(chemin, *a, **k):
            if os.fspath(chemin) == cible:
                raise exc
            return vrai(chemin, *a, **k)

        return _faux

    def test_est_repertoire_leve_sur_parent_non_traversable(self):
        """T1 (T-00001232) : un refus de traversée LÈVE, jamais « absent ».

        `chmod 000` RÉEL sur `locked` : `locked/inner` lève `PermissionError`,
        `locked` lui-même reste un répertoire (son `stat` ne demande que la
        traversée du parent). Rouge sur 3.14 avant le correctif (`is_dir` y
        rendait faux), déjà vert en 3.11–3.13 : c'est la divergence mesurée."""
        if os.name != "posix":
            self.skipTest("chmod 000 hors POSIX : aucun refus de traversee a mesurer")
        if os.geteuid() == 0:
            self.skipTest("hote root : chmod 000 ne refuse pas la traversee (T2 couvre)")
        locked = Path(self._tmp.name) / "locked"
        (locked / "inner").mkdir(parents=True)
        os.chmod(locked, 0o000)
        # try/finally DANS le test, PAS addCleanup : tearDown supprime l'arbre
        # (cleanup réussit malgré le 000), puis doCleanups jouerait le chmod sur
        # un chemin disparu → FileNotFoundError.
        try:
            self.assertRaises(PermissionError, self.w.est_repertoire, "locked/inner")
            self.assertTrue(self.w.est_repertoire("locked"),
                            "le repertoire en 000 lui-meme reste un repertoire")
        finally:
            os.chmod(locked, 0o755)

    def test_est_repertoire_eacces_simule_leve(self):
        """T2 : EACCES SIMULÉ sur le `stat` d'un répertoire RÉEL — joué partout,
        hôte root compris, là où le `chmod 000` de T1 ne mord pas."""
        self.w.creer_repertoire("cible")
        cible = os.fspath(self.w.resolve("cible"))
        refus = PermissionError(errno.EACCES, "Permission denied", cible)
        with mock.patch("os.stat", side_effect=self._stat_qui_leve(cible, refus)):
            with self.assertRaises(PermissionError):
                self.w.est_repertoire("cible")

    def test_est_repertoire_faux_sur_absence_fichier_nom_trop_long(self):
        """T3 : la réponse est NON, donc FAUX, sur tout interpréteur — absence
        (ENOENT), composant fichier (ENOTDIR), nom trop long (ENAMETOOLONG ;
        3.11–3.13 levaient `OSError` 63 avant le correctif). BRAS BOUCLE (ELOOP)
        à partir de 3.13 seulement : en 3.11/3.12 `resolve` lève `RuntimeError`
        avant le `stat`, et le bras saute en le disant."""
        self.w.write_text("f.txt", "x")
        self.assertFalse(self.w.est_repertoire("nope/inner"), "ENOENT")
        self.assertFalse(self.w.est_repertoire("f.txt/x"), "ENOTDIR")
        self.assertFalse(self.w.est_repertoire("x" * 300), "ENAMETOOLONG")
        with self.subTest(bras="boucle-ELOOP"):
            if sys.version_info < (3, 13):
                self.skipTest("boucle de liens : en 3.11/3.12 `resolve` leve "
                              "RuntimeError avant le stat (reserve C3)")
            racine = Path(self._tmp.name)
            try:
                os.symlink("loop_b", racine / "loop_a")
                os.symlink("loop_a", racine / "loop_b")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"lien symbolique impossible sur ce poste : {exc}")
            self.assertFalse(self.w.est_repertoire("loop_a"), "ELOOP")

    def test_est_repertoire_propage_une_erreur_d_e_s(self):
        """T4 : une erreur d'E/S (EIO) n'est pas une réponse NON — elle est
        PROPAGÉE telle quelle, jamais lue « absent »."""
        self.w.creer_repertoire("io")
        cible = os.fspath(self.w.resolve("io"))
        panne = OSError(errno.EIO, "Input/output error", cible)
        with mock.patch("os.stat", side_effect=self._stat_qui_leve(cible, panne)):
            with self.assertRaises(OSError) as pris:
                self.w.est_repertoire("io")
        self.assertEqual(pris.exception.errno, errno.EIO,
                         "l'erreur d'E/S n'est pas propagee telle quelle")

    def test_creer_repertoire_cree_les_parents_et_rend_l_absolu(self):
        """T-00000646 F5 : le répertoire SEUL, parents compris, jamais un
        fichier ; rend le chemin absolu résolu sous la racine."""
        rendu = self.w.creer_repertoire("a/b/c")
        self.assertEqual(rendu, Path(self._tmp.name).resolve() / "a" / "b" / "c")
        self.assertTrue(rendu.is_dir())
        self.assertEqual(sorted(p.name for p in rendu.iterdir()), [],
                         "creer_repertoire a pose un fichier")

    def test_creer_repertoire_est_idempotente_et_ne_touche_pas_au_contenu(self):
        """Rejouée sur un répertoire PEUPLÉ : ni levée, ni fichier remplacé —
        même inode, mêmes octets. C'est la propriété que `write_bytes` n'a pas
        sur une cible vivante (`os.replace`)."""
        self.w.write_text("d/vivant.db", "lignes validees")
        cible = self.w.resolve("d/vivant.db")
        avant = (cible.stat().st_ino, cible.read_bytes())
        self.w.creer_repertoire("d")
        self.w.creer_repertoire("d")
        self.assertEqual((cible.stat().st_ino, cible.read_bytes()), avant)

    def test_creer_repertoire_hors_racine_est_refuse_sans_rien_creer(self):
        """Une ACTION refuse : `HorsRacine`, et rien n'apparaît à côté de la
        racine."""
        voisin = Path(self._tmp.name).resolve().parent / "hors_arbre_creer_rep"
        self.assertFalse(voisin.exists(), "banc non armé : le voisin existe déjà")
        with self.assertRaises(HorsRacine):
            self.w.creer_repertoire("../hors_arbre_creer_rep")
        self.assertFalse(voisin.exists(), "un répertoire a été créé hors racine")

    def test_age_secondes_rend_maintenant_moins_le_mtime(self):
        """T-00000646 (S-00002323) : l'âge d'un fichier RÉEL antidaté de 2 h est
        lu par exécution, et celui d'un fichier frais reste sous la minute —
        les deux côtés, sans quoi une méthode qui rendrait une constante
        passerait l'un des deux."""
        self.w.write_text("v/ancien.lock", "")
        ancien = self.w.resolve("v/ancien.lock")
        il_y_a_2h = time.time() - 7200.0
        os.utime(ancien, (il_y_a_2h, il_y_a_2h))
        self.w.write_text("v/frais.lock", "")

        age_ancien = self.w.age_secondes("v/ancien.lock")
        age_frais = self.w.age_secondes("v/frais.lock")

        self.assertGreaterEqual(age_ancien, 7200.0)
        self.assertLess(age_ancien, 7200.0 + 60.0)
        self.assertGreaterEqual(age_frais, 0.0)
        self.assertLess(age_frais, 60.0)

    def test_age_secondes_hors_racine_leve_HorsRacine(self):
        """Une LECTURE hors racine refuse, par `..` comme par un lien qui
        remonte vers un fichier RÉEL — jamais l'âge d'un fichier étranger."""
        dehors = tempfile.NamedTemporaryFile(delete=False)
        dehors.close()
        self.addCleanup(os.unlink, dehors.name)
        os.symlink(dehors.name, Path(self._tmp.name) / "lien_dehors")
        for evasion in ("../hors_arbre_age", "lien_dehors"):
            with self.subTest(chemin=evasion), self.assertRaises(HorsRacine):
                self.w.age_secondes(evasion)

    def test_age_secondes_d_un_absent_leve_FileNotFoundError(self):
        """Absent ⇒ `FileNotFoundError`, jamais un âge inventé (0 ou infini)."""
        with self.assertRaises(FileNotFoundError):
            self.w.age_secondes("absent.lock")

    # -- T-00000759 : création exclusive et identité non suivie ------------

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : repli O_EXCL seul, non mesuré ici")
    def test_creer_fichier_exclusif_ne_suit_ni_n_ecrase(self):
        """W6 (T-00000759) : la création EXCLUSIVE ne suit pas un lien planté à
        sa place — ni vers une cible PRÉSENTE (octets intacts), ni vers une
        cible ABSENTE (jamais créée) — et n'écrase pas un fichier existant : les
        trois rendent `None`, le lien reste en place. Le cas nominal rend
        l'identité du fichier NEUF (vide, régulier, à `resolve(parent)/nom`) ;
        un chemin qui sort de la racine lève `HorsRacine` sans rien créer."""
        racine = Path(self._tmp.name)
        cible = racine / "cible.txt"
        cible.write_bytes(b"octets d'un tiers\n")
        absente = racine / "absente.db"
        try:
            os.symlink(cible, racine / "lien_present")
            os.symlink(absente, racine / "lien_pendant")
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        (racine / "existant.db").write_bytes(b"store vivant\n")

        self.assertIsNone(self.w.creer_fichier_exclusif("lien_present"))
        self.assertIsNone(self.w.creer_fichier_exclusif("lien_pendant"))
        self.assertIsNone(self.w.creer_fichier_exclusif("existant.db"))
        neuf = self.w.creer_fichier_exclusif("neuf.db")

        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n",
                         "la cible d'un lien a été touchée")
        self.assertFalse(absente.exists(), "la cible absente d'un lien a été CRÉÉE")
        self.assertTrue((racine / "lien_present").is_symlink(), "le lien a été retiré")
        self.assertTrue((racine / "lien_pendant").is_symlink(), "le lien a été retiré")
        self.assertEqual((racine / "existant.db").read_bytes(), b"store vivant\n",
                         "un fichier existant a été écrasé")
        self.assertIsNotNone(neuf, "le cas nominal n'a rien créé")
        vu = os.lstat(self.w.resolve("neuf.db"))
        self.assertEqual(neuf.chemin, self.w.racine / "neuf.db")
        self.assertEqual((neuf.dev, neuf.ino), (vu.st_dev, vu.st_ino))
        self.assertTrue(neuf.est_regulier)
        self.assertFalse(neuf.est_lien)
        self.assertEqual(vu.st_size, 0, "le fichier neuf n'est pas vide")
        voisin = racine.resolve().parent / "hors_arbre_exclusif"
        self.assertFalse(voisin.exists(), "banc non armé : le voisin existe déjà")
        with self.assertRaises(HorsRacine):
            self.w.creer_fichier_exclusif("../hors_arbre_exclusif")
        self.assertFalse(voisin.exists(), "un fichier a été créé hors racine")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : identité non mesurée ici")
    def test_identite_ne_suit_pas_la_feuille(self):
        """W7 (T-00000759) : `identite` lit la FEUILLE sans la suivre (`lstat`).
        Un lien rend SA propre identité (lien, non régulier, inode du LIEN et
        non de sa cible, chemin du lien) ; un lien PENDANT rend une identité,
        jamais `None` ; un absent rend `None` ; un parent qui sort de la racine
        lève `HorsRacine`."""
        racine = Path(self._tmp.name)
        self.w.write_text("cible.txt", "x")
        try:
            os.symlink(racine / "cible.txt", racine / "lien")
            os.symlink(racine / "absente", racine / "pendant")
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")

        lien = self.w.identite("lien")
        cible = self.w.identite("cible.txt")
        pendant = self.w.identite("pendant")

        self.assertIsNotNone(lien)
        self.assertIsNotNone(cible)
        self.assertTrue(lien.est_lien, "la feuille a été SUIVIE")
        self.assertFalse(lien.est_regulier)
        self.assertEqual(lien.chemin, self.w.racine / "lien")
        self.assertEqual(lien.ino, os.lstat(racine / "lien").st_ino)
        self.assertNotEqual(lien.ino, cible.ino, "l'inode rendu est celui de la cible")
        self.assertFalse(cible.est_lien)
        self.assertTrue(cible.est_regulier)
        self.assertIsNotNone(pendant, "un lien pendant a été dit absent")
        self.assertTrue(pendant.est_lien)
        self.assertIsNone(self.w.identite("absent.db"))
        with self.assertRaises(HorsRacine):
            self.w.identite("../hors_arbre_identite/x.db")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : st_nlink non mesuré ici")
    def test_identite_et_creation_comptent_les_liens_physiques(self):
        """W8 (T-00000759, binôme F1) : les DEUX constructeurs d'`Identite`
        portent `nliens` (`st_nlink`) — 1 pour un fichier neuf (`fstat`), N
        pour un fichier à N noms (`lstat`), et celui du LIEN, jamais de sa
        cible, pour un lien symbolique. Un lien PHYSIQUE ajouté change donc
        l'identité : c'est ce qui la rend comparable avant/après."""
        racine = Path(self._tmp.name)
        neuf = self.w.creer_fichier_exclusif("neuf.db")
        self.assertIsNotNone(neuf, "banc non armé : rien créé")
        self.assertEqual(neuf.nliens, 1, "un fichier neuf porte un seul nom")
        self.assertEqual(self.w.identite("neuf.db"), neuf,
                         "banc non armé : les deux constructeurs divergent")
        try:
            os.link(racine / "neuf.db", racine / "second_nom")
            os.symlink(racine / "neuf.db", racine / "lien")
        except (OSError, NotImplementedError):
            self.skipTest("liens indisponibles sur ce système de fichiers")

        principal = self.w.identite("neuf.db")
        second = self.w.identite("second_nom")
        lien = self.w.identite("lien")

        self.assertEqual(principal.nliens, 2, "le lien physique n'est pas compté")
        self.assertEqual(second.nliens, 2)
        self.assertEqual((second.dev, second.ino), (neuf.dev, neuf.ino),
                         "banc non armé : le second nom n'est pas le même inode")
        self.assertNotEqual(principal, neuf,
                            "un lien physique ajouté laisse l'identité inchangée")
        self.assertEqual(lien.nliens, os.lstat(racine / "lien").st_nlink)
        self.assertEqual(lien.nliens, 1, "`nliens` d'un lien est celui de sa CIBLE")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"),
                         "O_NOFOLLOW absent (Windows) : repli O_EXCL seul, non mesuré ici")
    def test_O_NOFOLLOW_tient_seul_la_feuille(self):
        """W9 (T-00000759, exec-critic, branche de secours) : `O_NOFOLLOW` est
        le SECOND verrou de la feuille dans `creer_fichier_exclusif`. `O_EXCL`
        le masque (un nom pris lève `EEXIST` avant lui), donc on RETIRE
        `O_EXCL` des drapeaux au passage de `os.open` : seul `O_NOFOLLOW`
        reste pour refuser un lien, vers une cible présente (octets intacts)
        comme ABSENTE (jamais créée). Sans lui, `os.open` suivrait le lien et
        rendrait l'identité de la cible."""
        racine = Path(self._tmp.name)
        cible = racine / "cible.txt"
        cible.write_bytes(b"octets d'un tiers\n")
        absente = racine / "absente.db"
        try:
            os.symlink(cible, racine / "lien_present")
            os.symlink(absente, racine / "lien_pendant")
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        vrai_open = os.open
        vus: list[int] = []

        def open_sans_excl(chemin, drapeaux, *args, **kwargs):
            vus.append(drapeaux)
            return vrai_open(chemin, drapeaux & ~os.O_EXCL, *args, **kwargs)

        for nom in ("lien_present", "lien_pendant"):
            with mock.patch.object(os, "open", open_sans_excl):
                with self.assertRaises(OSError) as ctx:
                    self.w.creer_fichier_exclusif(nom)
            self.assertIn(ctx.exception.errno, (errno.ELOOP, errno.EMLINK),
                          f"{nom} : pas le refus d'O_NOFOLLOW")

        self.assertEqual(len(vus), 2, "banc non armé : os.open non intercepté")
        self.assertTrue(all(d & os.O_EXCL for d in vus), "banc non armé : O_EXCL absent")
        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n",
                         "la cible d'un lien a été ouverte en écriture")
        self.assertFalse(absente.exists(), "la cible absente d'un lien a été CRÉÉE")
        self.assertTrue((racine / "lien_present").is_symlink(), "le lien a été retiré")
        self.assertTrue((racine / "lien_pendant").is_symlink(), "le lien a été retiré")


class EcritureExclusiveTests(unittest.TestCase):
    """`Workspace.ecrire_fichier_exclusif` (T-00000969) : créer ET écrire en un
    geste, jamais sur un nom pris, jamais une demi-écriture laissée."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name).resolve()
        self.w = Workspace(self.racine)

    def tearDown(self):
        self._tmp.cleanup()

    def test_EX1_le_cas_nominal_ecrit_les_octets_en_0644_masque(self):
        ancien = os.umask(0o022)
        self.addCleanup(os.umask, ancien)
        rendu = self.w.ecrire_fichier_exclusif("neuf.json", b"{}\n\xc3\xa9\n")
        self.assertEqual(rendu, self.racine / "neuf.json")
        self.assertEqual((self.racine / "neuf.json").read_bytes(), b"{}\n\xc3\xa9\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.racine / "neuf.json").stat().st_mode), 0o644)
        self.assertEqual(sorted(p.name for p in self.racine.iterdir()), ["neuf.json"],
                         "un temporaire est resté")

    def test_EX2_un_nom_pris_rend_None_sans_rien_toucher(self):
        (self.racine / "fichier").write_bytes(b"d'un tiers\n")
        (self.racine / "rep").mkdir()
        self.assertIsNone(self.w.ecrire_fichier_exclusif("fichier", b"x"))
        self.assertIsNone(self.w.ecrire_fichier_exclusif("rep", b"x"))
        self.assertEqual((self.racine / "fichier").read_bytes(), b"d'un tiers\n")
        self.assertEqual(list((self.racine / "rep").iterdir()), [])

    def test_EX3_un_lien_meme_pendant_n_est_ni_suivi_ni_retire(self):
        cible, absente = self.racine / "cible.txt", self.racine / "absente.json"
        cible.write_bytes(b"octets d'un tiers\n")
        try:
            os.symlink(cible, self.racine / "lien_present")
            os.symlink(absente, self.racine / "lien_pendant")
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques indisponibles sur ce poste")
        self.assertIsNone(self.w.ecrire_fichier_exclusif("lien_present", b"x"))
        self.assertIsNone(self.w.ecrire_fichier_exclusif("lien_pendant", b"x"))
        self.assertEqual(cible.read_bytes(), b"octets d'un tiers\n")
        self.assertFalse(absente.exists(), "la cible absente d'un lien a été CRÉÉE")
        self.assertTrue((self.racine / "lien_pendant").is_symlink(), "le lien a été retiré")

    def test_EX4_un_crash_au_fsync_retire_le_partiel_puis_releve(self):
        """`KeyboardInterrupt` (une `BaseException`, pas une `Exception`) au
        `fsync` : le fichier CRÉÉ par `O_EXCL` est retiré, l'exception relevée,
        et une seconde création au même nom passe — jamais une fausse collision."""
        with mock.patch.object(os, "fsync", side_effect=KeyboardInterrupt("crash")) as espion:
            with self.assertRaises(KeyboardInterrupt):
                self.w.ecrire_fichier_exclusif("ident.json", b"partiel")
        self.assertEqual(espion.call_count, 1, "banc non armé : fsync non atteint")
        self.assertFalse((self.racine / "ident.json").exists(), "le partiel est resté")
        self.assertIsNotNone(self.w.ecrire_fichier_exclusif("ident.json", b"plein"))
        self.assertEqual((self.racine / "ident.json").read_bytes(), b"plein")

    def test_EX5_hors_racine_et_parent_absent_levent_sans_rien_creer(self):
        voisin = self.racine.parent / (self.racine.name + "_voisin.json")
        with self.assertRaises(HorsRacine):
            self.w.ecrire_fichier_exclusif(f"../{voisin.name}", b"x")
        self.assertFalse(voisin.exists(), "un fichier est né hors racine")
        with self.assertRaises(FileNotFoundError):
            self.w.ecrire_fichier_exclusif("absent/ident.json", b"x")
        self.assertFalse((self.racine / "absent").exists())


class RemplacerAvecRepriseTests(unittest.TestCase):
    """`remplacer_avec_reprise` et `write_bytes(..., reprises=...)` (T-00000969).
    `os.replace` est INJECTÉ par `mock.patch.object` : portable, sans Windows."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self._tmp.name).resolve()
        self.w = Workspace(self.racine)
        self.vrai_replace = os.replace

    def tearDown(self):
        self._tmp.cleanup()

    def _flanchant(self, n: int, compte: list[int]):
        """`os.replace` qui lève `PermissionError` `n` fois, puis remplace."""
        def remplacer(src, cible):
            compte.append(1)
            if len(compte) <= n:
                raise PermissionError(13, f"tenu #{len(compte)}")
            return self.vrai_replace(src, cible)
        return remplacer

    def test_R1_trois_PermissionError_sont_absorbees(self):
        (self.racine / "s").write_bytes(b"neuf")
        compte: list[int] = []
        with mock.patch.object(os, "replace", self._flanchant(3, compte)), \
                mock.patch.object(time, "sleep"):
            remplacer_avec_reprise(self.racine / "s", self.racine / "c")
        self.assertEqual(len(compte), 4)
        self.assertEqual((self.racine / "c").read_bytes(), b"neuf")

    def test_R2_une_autre_OSError_sort_au_premier_appel(self):
        compte: list[int] = []

        def casse(src, cible):
            compte.append(1)
            raise OSError(22, "argument invalide")

        with mock.patch.object(os, "replace", casse), mock.patch.object(time, "sleep"):
            with self.assertRaises(OSError) as ctx:
                remplacer_avec_reprise("s", "c")
        self.assertNotIsInstance(ctx.exception, PermissionError)
        self.assertEqual(len(compte), 1)

    def test_R3_l_epuisement_releve_la_DERNIERE_apres_exactement_30(self):
        compte: list[int] = []
        with mock.patch.object(os, "replace", self._flanchant(10**6, compte)), \
                mock.patch.object(time, "sleep"):
            with self.assertRaises(PermissionError) as ctx:
                remplacer_avec_reprise("s", "c")
        self.assertEqual(len(compte), module_workspace.REMPLACER_TENTATIVES)
        self.assertEqual(module_workspace.REMPLACER_TENTATIVES, 30)
        self.assertEqual(module_workspace.REMPLACER_DELAI_S, 0.01)
        self.assertIn("tenu #30", str(ctx.exception))

    def test_R4_les_bornes_sont_RELUES_a_chaque_appel(self):
        """C5 : muter `workspace.REMPLACER_DELAI_S` / `REMPLACER_TENTATIVES` est
        ENTENDU. Délai à 0 : 30 échecs passent sous la borne de 0,25 s que les
        30 × 10 ms figés dépasseraient (0,3 s au moins) ; tentatives à 3 :
        l'épuisement tombe au 3e appel ; le délai muté est celui qu'on dort."""
        compte: list[int] = []
        with mock.patch.object(module_workspace, "REMPLACER_DELAI_S", 0.0), \
                mock.patch.object(os, "replace", self._flanchant(10**6, compte)):
            debut = time.monotonic()
            with self.assertRaises(PermissionError):
                remplacer_avec_reprise("s", "c")
            ecoule = time.monotonic() - debut
        self.assertEqual(len(compte), 30)
        self.assertLess(ecoule, 0.25, "le délai muté n'a pas été relu")
        compte.clear()
        with mock.patch.object(module_workspace, "REMPLACER_TENTATIVES", 3), \
                mock.patch.object(module_workspace, "REMPLACER_DELAI_S", 0.125), \
                mock.patch.object(os, "replace", self._flanchant(10**6, compte)), \
                mock.patch.object(time, "sleep") as dort:
            with self.assertRaises(PermissionError) as ctx:
                remplacer_avec_reprise("s", "c")
        self.assertEqual(len(compte), 3)
        self.assertIn("tenu #3", str(ctx.exception))
        self.assertEqual([c.args for c in dort.call_args_list], [(0.125,)] * 3)

    def test_R5_write_bytes_sans_reprises_fait_UN_appel(self):
        """Le défaut `reprises=False` ne change aucun appelant : une
        `PermissionError` sort au premier `os.replace`, l'ancien contenu reste
        et aucun temporaire ne traîne ; `reprises=True` l'absorbe."""
        self.w.write_bytes("c.json", b"ancien")
        compte: list[int] = []
        with mock.patch.object(os, "replace", self._flanchant(1, compte)), \
                mock.patch.object(time, "sleep"):
            with self.assertRaises(PermissionError):
                self.w.write_bytes("c.json", b"neuf")
        self.assertEqual(len(compte), 1)
        self.assertEqual((self.racine / "c.json").read_bytes(), b"ancien")
        self.assertEqual(sorted(p.name for p in self.racine.iterdir()), ["c.json"])
        compte.clear()
        with mock.patch.object(os, "replace", self._flanchant(2, compte)), \
                mock.patch.object(time, "sleep"):
            self.w.write_bytes("c.json", b"neuf", reprises=True)
        self.assertEqual(len(compte), 3)
        self.assertEqual((self.racine / "c.json").read_bytes(), b"neuf")
        self.assertEqual(sorted(p.name for p in self.racine.iterdir()), ["c.json"])

    def test_R6_un_KeyboardInterrupt_avant_le_renommage_ne_laisse_aucun_temporaire(self):
        """T-00000969 (exec-critic) : un Ctrl-C entre `mkstemp` et le renommage
        — au `fsync` comme à `os.replace`, avec ou sans reprises — RETIRE le
        temporaire, garde l'ancien contenu et RELÈVE l'interruption, jamais
        avalée. Mesuré sur 443dad15 : `--rename` interrompu laissait
        `project.json.<rnd>.cadre-tmp`, non ignoré par git. Mutant
        `except Exception` : le `.cadre-tmp` reste, ce témoin rougit."""
        self.w.write_bytes("p.json", b"ancien")
        for point in ("fsync", "replace"):
            for reprises in (False, True):
                with self.subTest(point=point, reprises=reprises):
                    with mock.patch.object(os, point,
                                           side_effect=KeyboardInterrupt("ctrl-c")) as espion:
                        with self.assertRaises(KeyboardInterrupt):
                            self.w.write_bytes("p.json", b"neuf", reprises=reprises)
                    self.assertEqual(espion.call_count, 1, "banc non armé : point non atteint")
                    self.assertEqual((self.racine / "p.json").read_bytes(), b"ancien")
                    self.assertEqual(sorted(p.name for p in self.racine.iterdir()),
                                     ["p.json"], "un temporaire est resté")

    def test_R7_un_mode_fourni_est_IMPOSE_masque_par_l_umask(self):
        """T-00000969 (clôture, F5 ; décision decision/T-00000969/01) : sans
        `mode`, une cible 0600 le reste (report) ; `mode=0o644` la passe en
        0644, neuve ou existante, masqué par l'umask comme une création
        (umask 077 : 0600). Mutant « `mode` ignoré » : la ligne 0600 → 0644 rougit."""
        if os.name == "nt":
            self.skipTest("les bits POSIX n'ont pas de sens sous Windows")
        ancien = os.umask(0o022)
        self.addCleanup(os.umask, ancien)
        cible = self.racine / "m.json"
        self.w.write_bytes("m.json", b"a")
        os.chmod(cible, 0o600)
        self.w.write_bytes("m.json", b"b")
        self.assertEqual(stat.S_IMODE(cible.stat().st_mode), 0o600, "report d'origine perdu")
        for umask, depart, attendu in ((0o022, 0o600, 0o644), (0o022, None, 0o644),
                                       (0o077, 0o644, 0o600)):
            with self.subTest(umask=oct(umask), depart=depart):
                os.umask(umask)
                if depart is None:
                    cible.unlink()
                else:
                    os.chmod(cible, depart)
                self.w.write_bytes("m.json", b"c", reprises=True, mode=0o644)
                self.assertEqual(stat.S_IMODE(cible.stat().st_mode), attendu)
                self.assertEqual(cible.read_bytes(), b"c")


#: Le script de l'ENFANT qui simule un poste en cp1252. Tout en ASCII : sous
#: `-X utf8=0` sur Windows, la sortie de l'enfant est en cp1252, et y imprimer le
#: glyphe leverait `UnicodeEncodeError` (ci.yml documente ce piege) — l'enfant
#: juge donc lui-meme et n'imprime que des `ascii(...)`.
_ENFANT_CP1252 = r'''
import locale
import subprocess
import sys
from unittest import mock

sys.path.insert(0, sys.argv[1])
mode = sys.argv[2]

# GARDE 1 : le mode UTF-8 masquerait le defaut (subprocess._text_encoding rend
# "utf-8" sans consulter le locale). `-X utf8=0` doit l'avoir coupe.
if sys.flags.utf8_mode:
    print("SIMULATION-INERTE: mode UTF-8 actif dans l'enfant")
    sys.exit(3)

# U+23F8 (le glyphe pause de `cadre tasks --statusline`) en UTF-8 : E2 8F B8.
# 0x8F n'a AUCUNE correspondance en cp1252. Ecrit en octets bruts, pour ne
# dependre ni de l'encodage du petit-enfant ni de celui de l'enfant.
EMETTEUR = (
    "import sys, time\n"
    "o = bytes([0xE2, 0x8F, 0xB8, 0x0A])\n"
    "sys.stdout.buffer.write(o); sys.stdout.flush()\n"
    "sys.stderr.buffer.write(o); sys.stderr.flush()\n"
    "if sys.argv[1:] == ['dormir']: time.sleep(30)\n"
)

with mock.patch.object(locale, "getencoding", lambda: "cp1252"), \
        mock.patch.object(locale, "getpreferredencoding",
                          lambda do_setlocale=True: "cp1252"):
    # GARDE 2 : la simulation mord-elle la bibliotheque standard ? Un
    # `text=True` sans encodage DOIT lever ici, sinon ce temoin ne peut pas
    # rougir et passerait a vide.
    try:
        subprocess.run([sys.executable, "-c", EMETTEUR], capture_output=True,
                       text=True, check=False, timeout=60)
    except UnicodeDecodeError:
        pass
    else:
        print("SIMULATION-INERTE: text=True sans encodage n'a pas leve sous cp1252")
        sys.exit(3)

    from cadre.executor import LocalExecutor

    if mode == "timeout":
        r = LocalExecutor().run([sys.executable, "-c", EMETTEUR, "dormir"], timeout=3.0)
    else:
        r = LocalExecutor().run([sys.executable, "-c", EMETTEUR])

attendu = "⏸"
constats = []
if mode == "timeout":
    if not r.expire:
        constats.append("la commande n'a pas expire")
elif r.code != 0:
    constats.append("rc=%d" % r.code)
if r.stdout.strip() != attendu:
    constats.append("stdout mal decode")
if r.stderr.splitlines()[:1] != [attendu]:
    constats.append("stderr mal decode")
print(ascii((r.code, r.expire, r.stdout, r.stderr)))
print(ascii(constats))
sys.exit(1 if constats else 0)
'''


class LocalExecutorTests(unittest.TestCase):
    def setUp(self):
        self.e = LocalExecutor()

    def test_commande_nominale(self):
        r = self.e.run([sys.executable, "-c", "print('ok')"])
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout.strip(), "ok")

    def test_un_code_non_nul_est_un_resultat_pas_une_exception(self):
        r = self.e.run([sys.executable, "-c", "raise SystemExit(3)"])
        self.assertEqual(r.code, 3)
        self.assertFalse(r.ok)

    def test_un_executable_absent_degrade_bruyamment(self):
        """LE KIT DÉGRADE, IL NE CASSE PAS. Un scanner absent rend un verdict
        dégradé nommé, jamais une trace d'erreur."""
        r = self.e.run(["binaire-qui-n-existe-vraiment-pas-42"])
        self.assertEqual(r.code, 127)
        self.assertIn("introuvable", r.stderr)

    def test_l_expiration_est_bornee_et_dite(self):
        r = self.e.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.4)
        self.assertTrue(r.expire)
        self.assertEqual(r.code, 124)
        self.assertIn("expire", r.stderr)

    def test_une_commande_malformee_est_refusee_avant_lancement(self):
        for mauvaise in ([], ["python\x00"]):
            with self.subTest(argv=mauvaise), self.assertRaises(ExecutionRefusee):
                self.e.run(mauvaise)

    # -- les constats de la revue de clôture du 2026-09-12 --------------

    def test_l_expiration_GARDE_la_sortie_partielle(self):
        """UNE DIVERGENCE DE PLATEFORME TRANSFORMÉE EN PERTE SILENCIEUSE.

        Sous POSIX, `subprocess` construit `TimeoutExpired` avec des OCTETS même
        en `text=True` ; sous Windows il rappelle `communicate()` et rend du
        `str`. Le garde `isinstance(exp.stdout, str)` rendait donc `""` au lieu
        de décoder : un test qui expire perdait son journal partiel sur la CI
        Linux et le gardait sur le poste. C'est précisément la classe de
        divergence que ce paquet dit surveiller, et elle vivait dans le paquet.
        """
        r = self.e.run(
            [sys.executable, "-u", "-c",
             "print('AVANT-LE-TIMEOUT', flush=True)\nimport time; time.sleep(30)"],
            timeout=1.0,
        )
        self.assertTrue(r.expire)
        self.assertEqual(r.code, 124)
        self.assertIn("AVANT-LE-TIMEOUT", r.stdout,
                      "la sortie partielle d'une commande expiree a ete jetee")

    def test_un_repertoire_de_travail_absent_N_EST_PAS_dit_executable_absent(self):
        """`subprocess` lève le MÊME `FileNotFoundError` pour l'exécutable
        introuvable et pour un `cwd` qui n'existe pas ; le handler en supposait
        un seul. Mesuré : `run([python3, …], cwd='/n/existe/pas')` annonçait
        « executable introuvable sur le PATH : python3 » alors que python3 est
        installé. Un diagnostic faux envoie chercher un binaire présent, ce qui
        coûte plus cher que pas de diagnostic."""
        r = self.e.run([sys.executable, "-c", "print(1)"], cwd="/n/existe/vraiment/pas")
        self.assertEqual(r.code, 127)
        self.assertIn("repertoire de travail introuvable", r.stderr)
        self.assertNotIn("PATH", r.stderr)

    def test_un_fichier_non_executable_est_un_RESULTAT_pas_une_exception(self):
        """Le `Protocol` annonce `-> Resultat`, et le module écrit qu'« un
        exécutable absent n'est pas une exception, c'est un résultat ». Or
        `PermissionError` et `NotADirectoryError` traversaient le contrat :
        l'appelant qui écrit `if not r.ok:` recevait une trace Python. 126 est
        la convention POSIX « trouvé mais non exécutable »."""
        if os.name == "nt":
            self.skipTest("les bits d'execution POSIX n'ont pas de sens sous Windows")
        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp) / "pas_executable.txt"
            cible.write_text("pas un programme\n", encoding="utf-8")
            os.chmod(cible, 0o644)
            r = self.e.run([str(cible)])
        self.assertEqual(r.code, 126)
        self.assertIn("lancement refuse", r.stderr)

    def test_aucun_shell_dans_le_module(self):
        """LA PROPRIÉTÉ CENTRALE, vérifiée sur la SOURCE. Une valeur re-parsée
        comme du shell est un finding de classe 1 non-waivable dans ce dépôt, et
        `bash -c` échoue dès qu'un chemin porte une apostrophe."""
        import ast  # noqa: PLC0415

        import cadre.executor as mod  # noqa: PLC0415

        # PAR AST, JAMAIS PAR RECHERCHE TEXTUELLE — deuxieme fois que ce piege
        # se referme dans cette phase : une recherche de chaine attrape la
        # DOCSTRING qui explique la regle, et un check qui refuse qu'on
        # documente ce qu'il interdit se fait contourner en supprimant la
        # documentation. On cherche un ARGUMENT `shell=True` passe a un appel.
        arbre = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        fautifs = [
            n.lineno for n in ast.walk(arbre) if isinstance(n, ast.Call)
            for kw in n.keywords
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value
        ]
        self.assertEqual(fautifs, [], f"shell=True passe a un appel, lignes {fautifs}")

    def test_le_detecteur_de_shell_mord_et_ignore_la_prose(self):
        """Les DEUX moities : il voit un appel, il ignore un texte."""
        import ast  # noqa: PLC0415

        arbre = ast.parse('"""On parle de shell=True."""\nrun(x, shell=True)\n')
        vus = [n.lineno for n in ast.walk(arbre) if isinstance(n, ast.Call)
               for kw in n.keywords
               if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value]
        self.assertEqual(len(vus), 1, "le detecteur confond le code et la prose")

    def test_le_resume_est_borne(self):
        """Ce qui part dans un journal est BORNÉ : un contexte noyé de sorties
        brutes déclenche une compaction, et une compaction perd un plan."""
        r = Resultat(argv=("a", "b", "c", "d", "e", "f"), code=0, stdout="x" * 9000, stderr="")
        self.assertLess(len(r.resume()), 120)

    # -- le defaut cp1252 (T-01M523WZN8WD6YB9RQJJD594ZE) -------------------

    def _sous_cp1252(self, mode: str) -> None:
        """Joue `_ENFANT_CP1252` dans un Python en `-X utf8=0`.

        UN SOUS-PROCESSUS, PAS UN MONKEYPATCH EN PLACE : `ci.yml` pose
        `PYTHONUTF8=1` sur la jambe Windows, et en mode UTF-8
        `subprocess._text_encoding` rend « utf-8 » sans jamais lire le locale —
        un patch de `locale` dans CE processus y serait inerte, et le temoin
        passerait a vide sur la CI meme sans correctif. `-X utf8=0` l'emporte
        sur la variable heritee ; la garde de l'enfant le VERIFIE (rc 3 sinon).
        """
        p = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-c", _ENFANT_CP1252,
             str(VENDOR.parent_import(ROOT, "cadre")), mode],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        detail = f"\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"
        self.assertNotEqual(p.returncode, 3, "simulation cp1252 INERTE : le temoin ne peut pas rougir" + detail)
        self.assertEqual(p.returncode, 0, "sortie UTF-8 mal decodee sous un encodage local cp1252" + detail)

    def test_la_sortie_UTF8_est_decodee_quel_que_soit_l_encodage_local(self):
        """LE DÉFAUT MESURÉ : `cadre tasks --statusline` écrit ⏸ en UTF-8
        (E2 8F B8) ; `text=True` sans `encoding=` décodait avec l'encodage
        LOCAL, et sous cp1252 l'octet 0x8F est indécodable —
        `UnicodeDecodeError` traversait le contrat `-> Resultat` (rc 2 du
        lanceur). La CI Windows ne le voyait pas : `PYTHONUTF8=1`."""
        self._sous_cp1252("nominal")

    def test_l_expiration_decode_aussi_en_UTF8_sous_cp1252(self):
        """LE CHEMIN `TimeoutExpired`, MÊME CONTRAT. PORTÉE : sous POSIX la
        sortie partielle arrive en OCTETS et `_txt` la décodait déjà en UTF-8 —
        ce témoin ne rougit donc PAS sur l'ancien code hors Windows ; il garde
        `_txt` (un retour au décodage local le fait rougir partout). Sous
        Windows, `subprocess` rappelle `communicate()` et décode avec
        l'encodage du `run` : là, l'ancien code levait aussi."""
        self._sous_cp1252("timeout")


if __name__ == "__main__":
    unittest.main()
