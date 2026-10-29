"""T-01M4N1FJC2X6YNA0XR51AYQKK1 (M6 de T-00001068), option A : un evenement que `runs/` porte et que la base
VIVANTE non vide n'a pas est ANNONCE a l'ouverture, RIEN n'est ecrit (`TestEcartRunsVersBase`, T52-T63).

Fichier NEUF : `test_run_export.py` est au cliquet des 1600 lignes (plafond 4574, aucun passe-droit) et ne grossit
pas. La fixture est `test_run_export._ReconstructionFixture`, importee ; la memoire de l'annonce et la borne de la
sonde vivent dans `agentic_v3.db.event_store_annonces`.
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from agentic_v3.db import run_export
from agentic_v3.tests.test_run_export import _ReconstructionFixture, _env_sans_git, _pont_en_panne


#: T62 (C2 it. 4) : un champ a RETIRER de la ligne (et non a ecraser).
_CHAMP_ABSENT = object()


def _copier_base(src: Path, dst: Path) -> None:
    """Copie COHERENTE d'une base SQLite (API backup)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


class TestEcartRunsVersBase(_ReconstructionFixture):
    """T-01M4N1FJC2X6YNA0XR51AYQKK1 (M6 de T-00001068), option A : un evenement que `runs/` porte et que la base
    VIVANTE non vide n'a pas est ANNONCE a l'ouverture, RIEN n'est ecrit. Les ecarts sont fabriques en deposant
    des lignes valides sous UNE AUTRE copie de `runs/` - ce que fait une fusion git."""

    @property
    def an(self):
        """Le module qui porte la memoire de l'annonce, la borne de la sonde et les ids du kit."""
        import agentic_v3.db.event_store_annonces as annonces

        return annonces

    def setUp(self) -> None:
        super().setUp()
        optout = mock.patch.dict(os.environ, {"AGENTS_V3_AUTO_SYNC": "0"})
        optout.start()
        self.addCleanup(optout.stop)
        patch = mock.patch.object(self.an, "_ECARTS_RUNS_ANNONCES", set())
        patch.start()
        self.addCleanup(patch.stop)

    def _base_avec_ecart(self, n: int):
        """Base au chemin par defaut NON vide (1 evenement), puis `n` lignes valides sous une AUTRE copie."""
        store, _ = self._ouvrir_defaut()
        store.append_event("T-52", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op52")
        self._ecrire_runs([self._ligne(u) for u in self._ulids(n)], auteur="auteurZ", copie="copieZ")
        return store

    def _verifier_geste(self, err: str, base: Path) -> None:
        """Ce que l'annonce dit du GESTE, dans les DEUX bras : acteur, copie AVANT la suppression, trois noms
        exacts, jamais un joker, `replay-sync`, comptes verifies."""
        nom = base.name
        for attendu in ("geste de l'ORCHESTRATEUR sur feu vert du PILOTE", "arreter les autres sessions",
                        "COPIER a part", "RETIRE de la base vivante", f"{nom}, {nom}-wal, {nom}-shm",
                        "trois noms EXACTS", "tasks.py replay-sync", "comparer evenements, liens et projections"):
            self.assertIn(attendu, err)
        self.assertNotIn(nom + "*", err, "le joker prend AUSSI les sauvegardes S-00002370 voisines")
        self.assertLess(err.index("COPIER a part"), err.index("supprimer ces trois noms"),
                        "la copie PRECEDE la suppression")
        self.assertLess(err.index("supprimer ces trois noms"), err.index("replay-sync"))

    def test_T52_hors_partition_du_kit_le_geste_est_generique_et_rien_n_est_ecrit(self) -> None:
        # M-W5-muet ; M-W5-ecrit ; M-W5-glob ; M-W5-ordre ; M-W5-acteur ; M-W5-portee-partout (NO_GO it. 3, C5) :
        # la decision S-00002370 et les deux ids de partition du KIT ne sont imprimes dans AUCUNE autre partition.
        self._base_avec_ecart(3)
        base = self._base_defaut()
        avant = self._tables(base)
        _, err = self._ouvrir_defaut()
        self.assertEqual(err.count("ecart runs/ -> base V3 vivante"), 1, err)
        self.assertIn("3 evenement(s) de runs/ absents", err)
        self.assertIn("auteurZ/copieZ (3)", err)
        self._verifier_geste(err, base)
        self.assertIn("decision du pilote d'abord pour cette partition", err)
        for kit in ("S-00002370", "d5dbf35ba35777da", "2af11384315eb8aa"):
            self.assertNotIn(kit, err, "une decision et des ids qui ne sont pas ceux de cette partition")
        self.assertEqual(self._tables(base), avant, "option A : rien n'est ecrit")
        self.assertEqual(self._compter(base), 1)

    def test_T52k_dans_la_partition_du_kit_le_geste_cite_la_decision_et_les_deux_ids(self) -> None:
        # M-W5-portee-nulle : la clause S-00002370 jamais imprimee, meme dans la partition du kit. La partition du
        # banc n'est pas d5dbf35ba35777da : la constante est amenee AU NOM de la partition du banc.
        es = self._es()
        # les VALEURS PAR DEFAUT sont figees (M-W5-partition-defaut, M-W5-perso-defaut) : sans cela le banc ne lit
        # jamais les ids du kit, il les remplace.
        self.assertEqual("d5dbf35ba35777da", self.an._PARTITION_GESTE_S2370)
        self.assertEqual("2af11384315eb8aa", self.an._PARTITION_PERSO_EXCLUE)
        self._base_avec_ecart(2)
        base = self._base_defaut()
        with mock.patch.object(self.an, "_PARTITION_GESTE_S2370", base.parent.parent.name), \
                mock.patch.object(self.an, "_PARTITION_PERSO_EXCLUE", "0123456789abcdef"):
            _, err = self._ouvrir_defaut()
        self.assertIn("2 evenement(s) de runs/ absents", err)
        self._verifier_geste(err, base)
        self.assertIn("le geste de S-00002370", err)
        self.assertIn(f"decide pour la seule partition {base.parent.parent.name}", err)
        self.assertIn("jamais la partition perso 0123456789abcdef", err)
        self.assertIn("toute autre partition : decision du pilote d'abord", err)

    def test_T52c_la_copie_nommee_est_celle_de_la_ligne_que_la_reconstruction_inserera(self) -> None:
        # M-W5-sans-tri (NO_GO it. 3, C3) : deux lignes de MEME identite, ULID distincts, sous deux copies ; la
        # reconstruction insere la PREMIERE dans l'ordre (ULID, copie) - la sonde nomme celle-la, quel que soit
        # l'ordre dans lequel `_lire_exports` les rend (ici : inverse).
        es = self._es()
        store, _ = self._ouvrir_defaut()
        store.append_event("T-52c", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op52c")
        u1, u2 = sorted(self._ulids(2))
        self._ecrire_runs([self._ligne(u1, op="op-X")], auteur="auteurZ", copie="copieB")
        self._ecrire_runs([self._ligne(u2, op="op-X")], auteur="auteurZ", copie="copieA")
        vrai = es.EventStore._lire_exports

        def inverse(self_, *args, **kwargs):
            return list(reversed(vrai(self_, *args, **kwargs)))

        with mock.patch.object(es.EventStore, "_lire_exports", inverse):
            _, err = self._ouvrir_defaut()
        self.assertIn("1 evenement(s) de runs/ absents", err)
        self.assertIn("auteurZ/copieB (1)", err, "la premiere ligne dans l'ordre ULID est celle de copieB")
        self.assertNotIn("copieA", err)

    def test_T52b_les_copies_nommees_sont_bornees_et_la_borne_est_dite(self) -> None:
        # M-W5-borne-copies : la liste des copies coupee a 5 SANS « et N autres ». R5 (it. 4) : comptes INEGAUX - le
        # rang est (-compte, nom) ; un rang par NOM seul (C-rang-par-nom) nommerait copie0-copie4 et tairait copie5.
        store, _ = self._ouvrir_defaut()
        store.append_event("T-52b", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op52b")
        for i, n in enumerate((1, 1, 1, 1, 1, 3, 2)):
            self._ecrire_runs([self._ligne(u) for u in self._ulids(n)], auteur="auteurZ", copie=f"copie{i}")
        _, err = self._ouvrir_defaut()
        self.assertIn("10 evenement(s) de runs/ absents", err)
        self.assertIn("auteurZ/copie5 (3), auteurZ/copie6 (2), auteurZ/copie0 (1), auteurZ/copie1 (1), "
                      "auteurZ/copie2 (1), et 2 autres", err)
        self.assertNotIn("auteurZ/copie3", err)

    @unittest.skipIf(os.name == "nt", "NTFS refuse \\n, ESC et : dans un nom")
    def test_T52d_un_nom_hostile_est_echappe_une_seule_ligne_aucun_esc(self) -> None:
        # C6 (it. 4) : un nom d'auteur ou de copie vient d'un dossier de `runs/` FUSIONNE. Un saut de ligne y forgeait
        # une FAUSSE ligne « event_store: ... » et un ESC pilotait le terminal : echappes en \\xNN. Reserve 2 (it. 5) :
        # TOUTE la categorie `Cc` - C0, DEL (\x7f) et C1 (\x9b, le CSI sur un octet) ; un filtre « C0 seul »
        # (`ord(c) < 0x20`) laisserait passer les deux derniers.
        store, _ = self._ouvrir_defaut()
        store.append_event("T-52d", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op52d")
        self._ecrire_runs([self._ligne(u) for u in self._ulids(1)], auteur="auteur\x1bZ\x7f",
                          copie="c\nevent_store: base V3 saine, rien a faire \x1b[2K\x9b")
        _, err = self._ouvrir_defaut()
        self.assertEqual(1, err.count("\n"), err)
        for brut in ("\x1b", "\x7f", "\x9b"):
            self.assertNotIn(brut, err)
        self.assertIn("\\x7f", err, "DEL non echappe")
        self.assertIn("\\x9b", err, "C1 non echappe")
        self.assertIn("auteur\\x1bZ\\x7f/c\\x0aevent_store: base V3 saine, rien a faire \\x1b[2K\\x9b (1)", err)

    def test_T52e_un_nom_bidi_ou_separateur_de_ligne_est_echappe(self) -> None:
        # R5 (cloture fournee 4) : `Cc` seul laissait passer `Cf` (U+202E, RLO : retourne l'affichage ; U+E0001 hors
        # BMP), `Zl` (U+2028) et `Zp` (U+2029), qu'un terminal ou une visionneuse rend comme un saut de ligne.
        store, _ = self._ouvrir_defaut()
        store.append_event("T-52e", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op52e")
        self._ecrire_runs([self._ligne(u) for u in self._ulids(1)], auteur="a‮Z", copie="c d e\U000e0001")
        _, err = self._ouvrir_defaut()
        for brut in ("‮", " ", " ", "\U000e0001"):
            self.assertNotIn(brut, err)
        self.assertIn("a\\u202eZ/c\\u2028d\\u2029e\\U000e0001 (1)", err)
        self.assertEqual("é\\x0a", self.an._sans_controle("é\n"), "un imprimable non ASCII reste tel quel")

    def test_T54b_le_texte_d_une_levee_de_la_sonde_est_echappe(self) -> None:
        # R5 (cloture fournee 4) : le message d'exception peut citer un chemin de `runs/` FUSIONNE.
        es = self._es()
        self._base_avec_ecart(1)
        with mock.patch.object(es.EventStore, "_lire_exports", side_effect=RuntimeError("bo\num‮")):
            _, err = self._ouvrir_defaut()
        self.assertIn("NON sonde (RuntimeError: bo\\x0aum\\u202e)", err)
        self.assertEqual(err.count("\n"), 1, "UNE ligne")

    def test_T53_sans_ecart_ou_sur_une_base_explicite_la_sonde_se_tait_et_ne_lit_pas(self) -> None:
        # M-W5-toujours (annonce sans ecart) ; M-W5-partout (sonde hors partition).
        es = self._es()
        store, _ = self._ouvrir_defaut()
        store.append_event("T-53", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op53")
        _, err = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", err, "aucun ecart : aucune annonce")
        self.assertNotIn("NON sonde", err)
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurZ", copie="copieZ")
        with mock.patch.object(es.EventStore, "_lire_exports", side_effect=AssertionError("sonde hors partition")):
            err2 = io.StringIO()
            with redirect_stderr(err2):
                self._store_explicite("explicite.db")
        self.assertEqual(err2.getvalue(), "", "base EXPLICITE hors partition : aucune sonde")

    def test_T54_une_levee_de_la_sonde_n_est_jamais_fatale_et_se_dit_une_fois(self) -> None:
        # M-W5-fatal ; M-W5-memo-succes.
        es = self._es()
        self._base_avec_ecart(1)
        with mock.patch.object(es.EventStore, "_lire_exports", side_effect=RuntimeError("boum")):
            _, err = self._ouvrir_defaut()  # ne DOIT PAS lever
            _, err2 = self._ouvrir_defaut()
        self.assertIn("ecart runs/ -> base NON sonde (RuntimeError: boum)", err)
        self.assertEqual(err.count("\n"), 1, "UNE ligne")
        self.assertEqual(err2, "", "une fois par processus : l'echec aussi")
        self.assertEqual(self._compter(self._base_defaut()), 1)

    def test_T55_l_ecart_est_annonce_une_fois_et_la_memoire_note_l_annonce_pas_la_sonde(self) -> None:
        # M-W5-repete ; M-W5-sonde.
        es = self._es()
        self._base_avec_ecart(2)
        _, e1 = self._ouvrir_defaut()
        _, e2 = self._ouvrir_defaut()
        self.assertEqual(e1.count("ecart runs/ -> base V3 vivante"), 1)
        self.assertNotIn("ecart runs/", e2, "deja annonce dans ce processus")
        self.an._ECARTS_RUNS_ANNONCES.clear()
        self._ecrire_runs([self._ligne(u) for u in self._ulids(1)], auteur="auteurY", copie="copieY")
        _, e3 = self._ouvrir_defaut()
        self.assertIn("3 evenement(s)", e3, "l'annonce redit le TOTAL de l'ecart")

    def test_T55b_une_ouverture_sans_ecart_ne_masque_pas_la_fusion_suivante(self) -> None:
        store, _ = self._ouvrir_defaut()
        store.append_event("T-55b", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op55b")
        _, silence = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", silence)
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurZ", copie="copieZ")
        _, err = self._ouvrir_defaut()
        self.assertIn("2 evenement(s) de runs/ absents", err, "un memo « sonde » aveuglerait la fusion")

    def test_T55c_la_memoire_est_par_base(self) -> None:
        # M-W5-memo-constant : une cle CONSTANTE tairait l'ecart d'une AUTRE base du meme processus.
        store = self._base_avec_ecart(2)
        _, e1 = self._ouvrir_defaut()
        self.assertIn("2 evenement(s) de runs/ absents", e1)
        autre = self.state / "autre" / "v3_event_store.db"
        _copier_base(self._base_defaut(), autre)
        store.db_path = autre
        err = io.StringIO()
        with redirect_stderr(err):
            store._annoncer_ecart_runs()
        self.assertIn("2 evenement(s) de runs/ absents", err.getvalue(), "la memoire d'UNE base tait l'autre")

    def test_T56_la_sonde_lit_runs_sous_la_racine_de_l_ecrivain(self) -> None:
        # M-W5-monorepo.
        subprocess.run(["git", "init", "-q", str(self.racine)], env=_env_sans_git(), check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        foo = self.racine / "apps" / "foo"
        (foo / ".agents").mkdir(parents=True)
        err = io.StringIO()
        with mock.patch.dict(os.environ):
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            with redirect_stderr(err):
                store = self._es().EventStore(project_root=foo)
                store.append_event("T-56", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op56")
            self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurZ", copie="copieZ")
            err2 = io.StringIO()
            with redirect_stderr(err2):
                self._es().EventStore(project_root=foo)
        self.assertIn("2 evenement(s) de runs/ absents", err2.getvalue())

    def test_T57_la_sonde_se_tait_quand_la_reconstruction_d_office_a_agi(self) -> None:
        # M-W5-agi.
        es = self._es()
        self._base_avec_ecart(2)
        with mock.patch.object(es.EventStore, "_reconstruire_si_vide", return_value=True):
            _, err = self._ouvrir_defaut()
        self.assertEqual(err, "")

    def test_T58_la_sonde_vient_apres_le_rejeu_des_journaux(self) -> None:
        # M-W5-avant. Borne DITE : l'ordre est assere par enregistrement d'appels.
        es = self._es()
        ordre: list = []
        with mock.patch.object(es.EventStore, "_rejouer_journaux_attente", lambda s: ordre.append("rejeu")), \
                mock.patch.object(es.EventStore, "_annoncer_ecart_runs", lambda s: ordre.append("sonde")):
            self._ouvrir_defaut()
        self.assertEqual(ordre, ["rejeu", "sonde"])

    def test_T59_la_connexion_de_lecture_ne_laisse_aucun_fichier_et_refuse_d_ecrire(self) -> None:
        # M-W5-mode-ro ; M-W5-sans-query-only ; M-W5-creer (NO_GO it. 3, C3) : `creer=True` ferait NAITRE un store
        # absent - la sonde ne cree JAMAIS rien.
        es = self._es()
        dossier = self.state / "sonde"
        dossier.mkdir(parents=True)
        base = dossier / "v3_event_store.db"
        c = sqlite3.connect(str(base))
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (1)")
        c.commit()
        c.close()
        self.assertEqual(sorted(os.listdir(dossier)), ["v3_event_store.db"], "precondition : aucune session")
        store = es.EventStore.__new__(es.EventStore)
        store.db_path = base
        conn = store._connexion_lecture()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (2)")
        conn.close()
        self.assertEqual(sorted(os.listdir(dossier)), ["v3_event_store.db"], "la sonde a laisse des fichiers")
        absent = self.state / "absent"
        absent.mkdir()
        sans_store = es.EventStore.__new__(es.EventStore)
        sans_store.db_path = absent / "v3_event_store.db"
        with self.assertRaises(Exception):
            sans_store._connexion_lecture()
        self.assertEqual(os.listdir(absent), [], "un store ABSENT n'est pas cree par la sonde")

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "liens POSIX")
    def test_T59b_un_lien_a_la_place_du_store_ou_d_un_annexe_n_est_ni_suivi_ni_cree(self) -> None:
        # M-W5-connect-nu (C1 it. 2) : `sqlite3.connect` nu SUIT le lien (lit la victime) et CREE la cible d'un lien
        # pendant hors de la partition. M-W5-sans-refuser-les-liens (NO_GO it. 3, C3) : `ouvrir_sans_suivre` ne juge
        # que la FEUILLE ; seul `refuser_les_liens` juge aussi les annexes `-wal` / `-shm`. Le lien est plante APRES
        # le rejeu, juste avant la sonde.
        es = self._es()
        self._base_avec_ecart(2)
        base = self._base_defaut()
        gardee = self.state / "gardee" / base.name
        _copier_base(base, gardee)
        victime = self.state / "victime" / "victime.db"
        _copier_base(base, victime)
        octets_victime = victime.read_bytes()
        pendante = self.state / "ailleurs" / "creee-par-la-sonde.db"
        pendante.parent.mkdir(parents=True)
        vrai = es.EventStore._rejouer_journaux_attente

        def sur_la_feuille(cible: Path) -> None:
            for suffixe in ("", "-wal", "-shm"):
                f = base.parent / (base.name + suffixe)
                if f.exists():
                    f.unlink()
            base.symlink_to(cible)

        def sur_l_annexe(cible: Path) -> None:
            wal = base.parent / (base.name + "-wal")
            if wal.exists():
                wal.unlink()
            wal.symlink_to(cible)

        for nom_cas, cible, planter in (("victime", victime, sur_la_feuille), ("pendant", pendante, sur_la_feuille),
                                        ("annexe-wal", victime, sur_l_annexe)):
            with self.subTest(lien=nom_cas):
                for suffixe in ("", "-wal", "-shm"):
                    f = base.parent / (base.name + suffixe)
                    if f.is_symlink() or f.exists():
                        f.unlink()
                _copier_base(gardee, base)
                self.an._ECARTS_RUNS_ANNONCES.clear()

                def rejeu_puis_lien(store, _cible=cible, _planter=planter):
                    vrai(store)
                    _planter(_cible)

                with mock.patch.object(es.EventStore, "_rejouer_journaux_attente", rejeu_puis_lien):
                    _, err = self._ouvrir_defaut()
                self.assertEqual(1, err.count("\n"), err)
                self.assertIn("ecart runs/ -> base NON sonde (EmplacementRefuse", err)
                self.assertNotIn("ecart runs/ -> base V3 vivante", err, "la sonde a LU la cible du lien")
                self.assertFalse(pendante.exists(), "la sonde a CREE la cible d'un lien pendant")
                self.assertEqual(octets_victime, victime.read_bytes())
        for suffixe in ("", "-wal", "-shm"):
            f = base.parent / (base.name + suffixe)
            if f.is_symlink() or f.exists():
                f.unlink()

    def test_T59c_sous_un_verrou_tenu_la_sonde_rend_la_main_vite_et_le_dit(self) -> None:
        # M-W5-attente-longue : `timeout=30` => 30 s d'attente a chaque commande sous verrou. NO_GO it. 3, C3 :
        # `timeout=5` et `timeout=9` passaient l'ancienne borne (< 10 s) - l'ESPION asserte la VALEUR passee a
        # `sqlite3.connect` (1), la duree (< 3 s) le comportement.
        store = self._base_avec_ecart(1)
        base = self._base_defaut()
        bloqueur = sqlite3.connect(str(base), timeout=0)
        bloqueur.execute("PRAGMA locking_mode=EXCLUSIVE")
        bloqueur.execute("BEGIN EXCLUSIVE")
        timeouts: list = []
        vrai_connect = sqlite3.connect

        def espion(*args, **kwargs):
            if kwargs.get("uri"):
                timeouts.append(kwargs.get("timeout"))
            return vrai_connect(*args, **kwargs)

        try:
            err = io.StringIO()
            t0 = time.monotonic()
            with mock.patch.object(sqlite3, "connect", espion), redirect_stderr(err):
                store._annoncer_ecart_runs()
            duree = time.monotonic() - t0
        finally:
            bloqueur.rollback()
            bloqueur.close()
        self.assertEqual([1], timeouts, "la sonde ouvre le store avec une attente de 1 s, pas plus")
        self.assertIn("ecart runs/ -> base NON sonde (OperationalError", err.getvalue())
        self.assertLess(duree, 3.0, "la sonde attend le verrou au-dela de sa borne courte")

    def test_T60_le_geste_annonce_ferme_l_ecart(self) -> None:
        # Le geste est EXTRAIT de l'annonce (noms ET ordre) puis EXECUTE : M-W5-glob (le joker emporte la
        # sauvegarde voisine) et M-W5-ordre (supprimer avant de copier : copie absente) le rougissent.
        import shutil

        es = self._es()
        self._base_avec_ecart(3)
        base = self._base_defaut()
        _, err = self._ouvrir_defaut()
        self.assertIn("3 evenement(s)", err)
        m_copie = re.search(r"COPIER a part, hors de (.+?) : (.+?) \(ceux qui existent\)", err)
        m_suppr = re.search(r"supprimer ces trois noms EXACTS : (.+?) \(jamais", err)
        self.assertIsNotNone(m_copie, err)
        self.assertIsNotNone(m_suppr, err)
        parent = Path(m_copie.group(1))
        self.assertEqual(parent, base.parent)
        sauve = self.state / "sauvegarde"
        sauve.mkdir()
        voisine = base.parent / (base.name + ".avant-S-00002370.20260926")
        voisine.write_bytes(b"sauvegarde voisine")

        def copier() -> None:
            for motif in m_copie.group(2).split(", "):
                for f in parent.glob(motif):
                    shutil.copy2(f, sauve / f.name)

        def supprimer() -> None:
            for motif in m_suppr.group(1).split(", "):
                for f in parent.glob(motif):
                    f.unlink()

        for _pos, geste in sorted([(err.index("COPIER a part"), copier),
                                   (err.index("supprimer ces trois noms"), supprimer)], key=lambda t: t[0]):
            geste()
        self.assertTrue((sauve / base.name).exists(), "la copie n'a rien garde : suppression AVANT la copie")
        self.assertTrue(voisine.exists(), "le geste a emporte une sauvegarde voisine")
        self.assertFalse(base.exists())
        self.an._ECARTS_RUNS_ANNONCES.clear()
        _, err2 = self._ouvrir_defaut()  # = tasks.py replay-sync : la base vide est reconstruite d'office
        self.assertIn("reconstruite depuis runs/", err2)
        self.assertEqual(self._compter(base), 4, "1 evenement propre + 3 de l'autre copie")
        self.an._ECARTS_RUNS_ANNONCES.clear()
        _, err3 = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", err3, "l'ecart est ferme")
        self.assertTrue(voisine.exists())

    def test_T61_sous_blocage_la_sonde_se_tait_meme_avec_un_runs_plein(self) -> None:
        # M-W5-agi / « jamais sous blocage ».
        es = self._es()
        self._peupler_A()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne):
            store, err = self._ouvrir_defaut()
        self.assertTrue(store._reconstruction_bloquee)
        self.assertIn("reconstruction AVORTEE", err)
        self.assertNotIn("ecart runs/", err)

    def test_T61b_sous_une_sonde_de_reconstruction_en_echec_la_sonde_d_ecart_se_tait(self) -> None:
        # M-W5-nontentee-faux (NO_GO it. 3, C3) : `_reconstruire_si_vide` qui rend `False` en NON TENTEE laisserait
        # la sonde parler sur une base VIDE dont la reconstruction est DUE. Un dossier illisible SEUL donne cette
        # cause (T28b) mais ne peut pas rougir ce mutant (rien de lisible a compter) : l'echec est greffe, avec un
        # `runs/` LISIBLE a cote.
        es = self._es()
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurZ", copie="copieZ")
        with mock.patch.object(es.EventStore, "_reconstruction_due", side_effect=PermissionError("sonde greffee")):
            store, err = self._ouvrir_defaut()
        self.assertTrue(store._reconstruction_bloquee)
        self.assertIn("reconstruction automatique non tentee : PermissionError", err)
        self.assertNotIn("ecart runs/", err)

    # T62 : les classes de ligne de FORME VALIDE (`_obj_reconstruction_valide`), (nom, champs ecrases, APPLIQUEE par
    # la reconstruction ?). Les etiquettes NE SONT PAS des hypotheses : le test les asserte sur la reconstruction
    # REELLE. Les temoins `True` gardent le mutant « tout rejeter » ; `req_id`/`spec_version` nuls et NaN sont des NOT NULL
    # de projection, comptes `echecs` comme les autres (C5 it. 4 : plus jamais « deja present »). C2 it. 4 : `attempt`
    # ABSENT (identite prise ou libre) - l'identite demandee a la base est celle que l'ecrivain a ECRITE. R4 : un
    # `payload_json` qui n'est pas du JSON se projette sur `{}` (jamais `None`).
    _CLASSES_T62 = (
        ("temoin_event_type_inconnu", {"event_type": "ZZZ_INCONNU"}, True),
        ("temoin_code_diff_null", {"event_type": "CODE_GENERATED", "payload_json": '{"code_diff": null}'}, True),
        ("temoin_attempt_2_63_moins_1", {"attempt": 2 ** 63 - 1}, True),
        ("attempt_absent_libre", {"attempt": _CHAMP_ABSENT}, True),
        ("attempt_absent_identite_prise", {"operation_id": "op62", "attempt": _CHAMP_ABSENT}, False),
        ("payload_non_json_TEST_RUN", {"event_type": "TEST_RUN", "payload_json": "pas du json"}, True),
        ("payload_liste_TASK_CREATED", {"event_type": "TASK_CREATED", "payload_json": "[]"}, False),
        ("payload_null_TEST_RUN", {"event_type": "TEST_RUN", "payload_json": "null"}, False),
        ("req_id_objet", {"event_type": "TASK_CREATED", "payload_json": '{"req_id": {"a": 1}}'}, False),
        ("req_id_null", {"event_type": "TASK_CREATED", "payload_json": '{"req_id": null}'}, False),
        ("spec_version_null", {"event_type": "TASK_CREATED", "payload_json": '{"spec_version": null}'}, False),
        ("spec_version_NaN", {"event_type": "TASK_CREATED", "payload_json": '{"spec_version": NaN}'}, False),
        ("spec_version_2_70", {"event_type": "TASK_CREATED", "payload_json": '{"spec_version": %d}' % (2 ** 70)}, False),
        ("code_diff_objet", {"event_type": "CODE_GENERATED", "payload_json": '{"code_diff": {"a": 1}}'}, False),
        ("task_id_surrogate", {"task_id": "T-\ud800"}, False),
        ("agent_role_surrogate", {"agent_role": "r\udcff"}, False),
        ("payload_json_surrogate", {"payload_json": "{\"x\": \"\ud800\"}"}, False),
        ("operation_id_surrogate", {"operation_id": "op-\ud800"}, False),
        ("operation_id_objet", {"operation_id": {"a": 1}}, False),
        ("event_kind_liste", {"event_kind": [1]}, False),
        ("created_at_objet", {"created_at": {"x": 1}}, False),
        ("predecesseur_liste", {"predecesseur_ulid": [1]}, False),
        ("attempt_2_63", {"attempt": 2 ** 63}, False),
        ("attempt_2_70", {"attempt": 2 ** 70}, False),
    )

    def _ecrire_runs_ascii(self, lignes, *, auteur: str, copie: str) -> Path:
        """Comme `_ecrire_runs`, mais `ensure_ascii` : un substitut UTF-16 isole est ECHAPPE, donc ecrivable."""
        dossier = self.racine / "runs" / auteur / copie
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{run_export._mois_de_ulid(lignes[0]['ulid'])}.jsonl"
        with fichier.open("a", encoding="ascii") as fh:
            for ligne in lignes:
                fh.write(json.dumps(ligne) + "\n")
        return fichier

    def test_T62_l_ecart_annonce_est_exactement_ce_que_la_reconstruction_appliquerait(self) -> None:
        # M-W5-non-applique (le banc rend toujours Vrai) ; M-W5-tout-rejeter ; M-W5-sans-projection (le banc ne joue
        # que l'ecrivain) ; M-W5-sans-ecrivain. NO_GO it. 3, C1 : six classes d'UNE ligne fusionnee, de forme
        # valide, passaient le filtre de la rev. 2, etaient ANNONCEES, puis la reconstruction les rejetait : l'annonce
        # prescrivait de supprimer la base vivante POUR RIEN, a chaque verbe qui ecrit, sans fin. Ici : (1) la sonde
        # compte EXACTEMENT les lignes que la reconstruction inserera (par copie nommee) ; (2) le geste est EXECUTE
        # et chaque etiquette est verifiee sur la base REBATIE ; (3) l'annonce se TAIT ensuite.
        import shutil

        es = self._es()
        store, _ = self._ouvrir_defaut()
        store.append_event("T-62", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op62")
        base = self._base_defaut()
        ulids = {}
        for i, (nom, champs, _appliquee) in enumerate(self._CLASSES_T62):
            ligne = self._ligne(run_export.nouvel_ulid(), task_id=f"T-62-{i}")
            ligne.update(champs)
            for cle in [c for c, v in champs.items() if v is _CHAMP_ABSENT]:
                del ligne[cle]
            self._ecrire_runs_ascii([ligne], auteur="auteurZ", copie=f"c{i:02d}")
            ulids[nom] = ligne["ulid"]
        valide = self._ligne(run_export.nouvel_ulid(), task_id="T-62-valide")
        self._ecrire_runs_ascii([valide], auteur="auteurZ", copie="cvalide")
        attendues = {f"c{i:02d}" for i, (_n, _c, ok) in enumerate(self._CLASSES_T62) if ok} | {"cvalide"}
        _, avant = self._ouvrir_defaut()
        evenements = store._lire_exports(
            self.racine, {"fichiers_illisibles": 0, "fichiers_trop_gros": 0, "lignes_illisibles": 0, "ignores": 0},
            {"fichiers_illisibles": [], "fichiers_trop_gros": [], "lignes_illisibles": []})
        evenements.sort(key=lambda t: (t[0], t[1]))
        conn = sqlite3.connect(str(base))
        try:
            comptees = {tie.split("/", 1)[1] for tie in store._manquants_nommes(conn.cursor(), evenements).values()}
        finally:
            conn.close()
        for i, (nom, _c, appliquee) in enumerate(self._CLASSES_T62):
            with self.subTest(classe=nom, etape="sonde"):
                self.assertEqual(appliquee, f"c{i:02d}" in comptees,
                                 "la sonde compte autre chose que ce que la reconstruction appliquera")
        self.assertEqual(attendues, comptees, "la sonde compte autre chose que ce que la reconstruction appliquera")
        self.assertIn(f"{len(attendues)} evenement(s) de runs/ absents", avant)
        # (2) le geste, EXECUTE : copie a part, retrait des trois noms exacts, reouverture = reconstruction.
        sauve = self.state / "sauvegarde62"
        sauve.mkdir()
        for suffixe in ("", "-wal", "-shm"):
            f = base.parent / (base.name + suffixe)
            if f.exists():
                shutil.copy2(f, sauve / f.name)
                f.unlink()
        self.an._ECARTS_RUNS_ANNONCES.clear()
        self._ouvrir_defaut()
        entres = {u for (u,) in sqlite3.connect(str(base)).execute("SELECT ulid FROM events_ledger")}
        for i, (nom, _c, appliquee) in enumerate(self._CLASSES_T62):
            with self.subTest(classe=nom):
                self.assertEqual(appliquee, ulids[nom] in entres, "l'etiquette de la classe n'est pas celle de la "
                                 "reconstruction REELLE")
        self.assertIn(valide["ulid"], entres)
        self.assertEqual(1 + len(attendues), len(entres), "le geste insere EXACTEMENT ce que la sonde annoncait")
        # (3) apres le geste : le silence.
        self.an._ECARTS_RUNS_ANNONCES.clear()
        _, apres = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", apres, "le geste annonce ne ferme pas l'ecart annonce")

    def test_T62b_le_decompte_de_saute_non_vide_herite_de_la_meme_definition(self) -> None:
        # M-W5-non-applique : `_compter_manquants` (F5) delegue a `_manquants_nommes` - le meme filtre. Une ligne que
        # la reconstruction rejette n'est pas « absente » : « 2 evenements » serait une fausse alerte.
        store, _ = self._ouvrir_defaut()
        store.append_event("T-62b", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op62b")
        rejetee = self._ligne(run_export.nouvel_ulid(), task_id="T-62b-r")
        rejetee["payload_json"] = "[]"
        self._ecrire_runs_ascii([rejetee], auteur="auteurZ", copie="crejetee")
        self._ecrire_runs_ascii([self._ligne(run_export.nouvel_ulid(), task_id="T-62b-v")], auteur="auteurZ", copie="cvalide")
        err = io.StringIO()
        with redirect_stderr(err):
            res = store._reconstruire(None, si_vide=True)
        self.assertEqual(res["saute_non_vide"], 1, res)
        self.assertIn("1 evenements de runs/ absents", err.getvalue())

    def test_T62c_une_panne_systeme_du_banc_se_dit_une_erreur_de_donnee_se_tait(self) -> None:
        # M-W5-panne-avalee : un banc qui avale TOUTE levee changerait une panne (E/S, memoire, base corrompue) en
        # « aucune ligne a appliquer » - l'ecart disparaitrait SANS UN MOT. Une erreur de DONNEE, elle, ecarte la
        # ligne (c'est ce que fait la reconstruction : `_est_panne_systeme`, UNE classification).
        es = self._es()
        self._base_avec_ecart(2)
        with mock.patch.object(es.EventStore, "_apply_projection",
                               side_effect=sqlite3.OperationalError("disk I/O error")):
            _, err = self._ouvrir_defaut()
        self.assertIn("ecart runs/ -> base NON sonde (OperationalError: disk I/O error)", err)
        self.assertNotIn("evenement(s) de runs/ absents", err)
        self.an._ECARTS_RUNS_ANNONCES.clear()
        with mock.patch.object(es.EventStore, "_apply_projection", side_effect=RuntimeError("donnee")):
            _, err2 = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", err2, "une erreur de DONNEE ecarte la ligne : rien a annoncer")

    def test_T62d_un_ulid_revu_ne_compte_pas_comme_la_reconstruction_le_juge(self) -> None:
        # M-W5-sans-vus-ulid. `_appliquer_lignes` marque un ULID VU AVANT de juger la FORME : (1) deux lignes de MEME
        # ULID valides (une divergente, `merge=union`) : seule la PREMIERE est jouee (T-496 compte l'autre
        # `divergentes`) ; (2) une premiere ligne HORS FORME (payload_json entier) ecarte AUSSI la seconde, valide :
        # sans `vus`, la sonde compterait la seconde a CHAQUE ouverture, geste fait - elle n'est jamais inseree.
        store, _ = self._ouvrir_defaut()
        store.append_event("T-62d", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op62d")
        u1, u2 = self._ulids(2)
        self._ecrire_runs_ascii([self._ligne(u1, op="op-A")], auteur="auteurZ", copie="copieA1")
        self._ecrire_runs_ascii([self._ligne(u1, op="op-B")], auteur="auteurZ", copie="copieB1")
        hors_forme = self._ligne(u2, op="op-C")
        hors_forme["payload_json"] = 5
        self._ecrire_runs_ascii([hors_forme], auteur="auteurZ", copie="copieA2")
        self._ecrire_runs_ascii([self._ligne(u2, op="op-D")], auteur="auteurZ", copie="copieB2")
        _, err = self._ouvrir_defaut()
        self.assertIn("1 evenement(s) de runs/ absents", err)
        self.assertIn("auteurZ/copieA1 (1)", err)
        self.assertNotIn("copieB1", err)
        self.assertNotIn("copieB2", err, "la seconde ligne d'un ULID dont la premiere est hors forme n'est jamais inseree")

    def test_T62e_une_identite_entiere_rencontre_la_meme_identite_en_texte_comme_a_la_reconstruction(self) -> None:
        # M-W5-banc-sans-base (le banc ne porte pas les cles de la base) ; M-W5-banc-defait-tout (un succes n'y reste
        # pas : les lignes suivantes ne le rencontrent plus). `operation_id` ENTIER 5 : la colonne (affinite TEXT) le
        # range '5', et une ligne a `operation_id` texte '5' de MEME (event_kind, attempt) entre en collision (index
        # unique) : la reconstruction insere la premiere, ecarte la seconde EN SILENCE. Un filtre par IDENTITE qui ne
        # compare que des chaines (la rev. 2, F5) comptait la seconde a CHAQUE ouverture, apres le geste aussi.
        import shutil

        es = self._es()
        store, _ = self._ouvrir_defaut()
        store.append_event("T-62e", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op62e")
        base = self._base_defaut()
        u1, u2 = sorted(self._ulids(2))
        self._ecrire_runs_ascii([self._ligne(u1, op="5")], auteur="auteurZ", copie="copieA")
        self._ecrire_runs_ascii([self._ligne(u2, op=5)], auteur="auteurZ", copie="copieB")
        _, avant = self._ouvrir_defaut()
        self.assertIn("1 evenement(s) de runs/ absents", avant)
        self.assertIn("auteurZ/copieA (1)", avant)
        sauve = self.state / "sauvegarde62e"
        sauve.mkdir()
        for suffixe in ("", "-wal", "-shm"):
            f = base.parent / (base.name + suffixe)
            if f.exists():
                shutil.copy2(f, sauve / f.name)
                f.unlink()
        self.an._ECARTS_RUNS_ANNONCES.clear()
        self._ouvrir_defaut()
        entres = {u for (u,) in sqlite3.connect(str(base)).execute("SELECT ulid FROM events_ledger")}
        self.assertIn(u1, entres)
        self.assertNotIn(u2, entres, "la reconstruction ecarte la seconde : meme identite, une fois la colonne en TEXTE")
        self.an._ECARTS_RUNS_ANNONCES.clear()
        _, apres = self._ouvrir_defaut()
        self.assertNotIn("ecart runs/", apres, "l'identite entiere rencontree en texte est comptee a CHAQUE ouverture")

    def test_T62f_l_identite_durable_est_operation_kind_ET_attempt(self) -> None:
        # M-W5-sans-identite-base (la base ne juge plus rien : la ligne a l'identite DEJA PRISE serait comptee) ;
        # M-W5-identite-sans-attempt (l'attempt n'est plus compare : une TENTATIVE de plus de la meme operation,
        # que la reconstruction insere, serait ecartee). Base : (op62f, TASK_CREATED, 0). runs/ : la MEME identite
        # sous un autre ULID (ecartee en silence par l'index unique) et la tentative 1 (inseree).
        store, _ = self._ouvrir_defaut()
        store.append_event("T-62f", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op62f",
                           event_kind="TASK_CREATED", attempt=0)
        meme, suivante = sorted(self._ulids(2))
        self._ecrire_runs_ascii([self._ligne(meme, op="op62f", attempt=0)], auteur="auteurZ", copie="copieMeme")
        self._ecrire_runs_ascii([self._ligne(suivante, op="op62f", attempt=1)], auteur="auteurZ", copie="copieSuivante")
        _, err = self._ouvrir_defaut()
        self.assertIn("1 evenement(s) de runs/ absents", err)
        self.assertIn("auteurZ/copieSuivante (1)", err)
        self.assertNotIn("copieMeme", err)

    def test_T63_au_dela_de_la_borne_la_sonde_ne_lit_pas_runs_et_le_dit(self) -> None:
        # M-W5-sans-borne (R8 it. 2) ; M-W5-borne-large (`>=` vs `>`) ; la valeur par defaut est figee.
        es = self._es()
        self.assertEqual(self.an._SONDE_RUNS_MAX_OCTETS, es._TAILLE_FICHIER_MAX_OCTETS)
        self._base_avec_ecart(2)
        taille = sum(f.stat().st_size for f in (self.racine / "runs").rglob("*.jsonl"))
        with mock.patch.object(self.an, "_SONDE_RUNS_MAX_OCTETS", taille - 1), \
                mock.patch.object(es.EventStore, "_lire_exports", side_effect=AssertionError("lu au-dela")):
            _, err = self._ouvrir_defaut()
        self.assertEqual(1, err.count("ecart runs/ -> base NON sonde (runs/ pese"), err)
        self.assertNotIn("AssertionError", err)
        self.an._ECARTS_RUNS_ANNONCES.clear()
        with mock.patch.object(self.an, "_SONDE_RUNS_MAX_OCTETS", taille):
            _, err2 = self._ouvrir_defaut()
        self.assertIn("2 evenement(s) de runs/ absents", err2, "A la borne : la sonde lit")

    @unittest.skipUnless(hasattr(os, "symlink"), "liens symboliques indisponibles")
    def test_T63b_la_taille_d_un_lien_est_celle_du_lien_pas_de_sa_cible(self) -> None:
        # M-W5-taille-stat : `_taille_runs` mesure par `lstat`. `parcourir_runs` ne rend jamais un lien, donc `stat`
        # et `lstat` sont indiscernables sur ce qu'il rend : le temoin INJECTE un lien dans l'enumeration. Une taille
        # prise par `stat` lirait, par la taille, la cible d'un lien posee hors de `runs/`.
        store, _ = self._ouvrir_defaut()
        cible = self.state / "cible_grosse.bin"
        cible.write_bytes(b"x" * 5000)
        lien = self.racine / "runs" / "auteurL" / "copieL" / "2026-10.jsonl"
        lien.parent.mkdir(parents=True)
        try:
            lien.symlink_to(cible)
        except OSError as exc:  # pragma: no cover - plateforme sans droit de lien
            self.skipTest(f"lien impossible : {exc}")
        self.assertLess(os.lstat(lien).st_size, 5000)
        with mock.patch.object(run_export, "parcourir_runs", return_value=iter([lien])):
            self.assertEqual(os.lstat(lien).st_size, store._taille_runs(self.racine))

    def test_T64_status_puis_dashboard_summary_annoncent_une_fois_sans_rien_ecrire(self) -> None:
        # C1 (it. 4) : la sonde vit dans `EventStore.__init__` - TOUTE construction du store au chemin par defaut
        # l'annonce, verbes de LECTURE compris : « verbes qui ecrivent seulement » etait faux. Mutant : la sonde
        # reservee aux verbes qui ecrivent (C-sonde-verbes-ecriture). Une fois par processus et par base.
        import sys
        from agentic_v3 import cli

        self._base_avec_ecart(3)
        base = self._base_defaut()
        avant = self._tables(base)
        err = io.StringIO()
        for cmd in (["status", "T-52"], ["dashboard-summary"]):
            with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(self.racine)}), \
                    mock.patch.object(sys, "argv", ["agentic_v3"] + cmd), redirect_stderr(err), \
                    redirect_stdout(io.StringIO()):
                cli.main()
        self.assertEqual(1, err.getvalue().count("ecart runs/ -> base V3 vivante - 3 evenement(s)"), err.getvalue())
        self.assertEqual(self._tables(base), avant, "un verbe de lecture n'ecrit rien")

    def test_T65_un_not_null_de_projection_est_un_echec_compte_jamais_un_deja_present(self) -> None:
        # C5 (it. 4) : `_appliquer_lignes` rangeait TOUTE `IntegrityError` en « deja present » : une ligne fusionnee
        # en echec sur un NOT NULL de projection (`req_id` ou `spec_version` nuls) etait PERDUE EN SILENCE (echecs=0).
        # Seule l'UNICITE (ULID ou identite durable deja prise) reste idempotente et muette.
        u_a, u_b, u_c, u_d = sorted(self._ulids(4))
        self._ecrire_runs([self._ligne(u_a, op="op65"), self._ligne(u_b, op="op65"),
                           self._ligne(u_c, payload={"req_id": None}),
                           self._ligne(u_d, payload={"spec_version": None})], auteur="auteurZ", copie="copie65")
        espion, resumes = self._espionner_reconstruire()
        with espion:
            _, err = self._ouvrir_defaut()
        res = resumes[-1]
        self.assertEqual((1, 2), (res["applied"], res["echecs"]), res)
        for u in (u_c, u_d):
            self.assertIn(f"ligne ecartee (echec base) ulid={u} : NOT NULL constraint failed", err)
        self.assertNotIn(f"ulid={u_b}", err, "une collision d'UNICITE reste idempotente et muette")
        self.assertIn("echecs=2", err)

    def test_T65b_une_unicite_levee_apres_l_insert_est_defaite_avant_d_etre_ecartee(self) -> None:
        # R2 (cloture fournee 4) : la branche d'UNICITE de `_appliquer_lignes` saute la ligne (`continue`) ; elle doit
        # la DEFAIRE d'abord (`ROLLBACK TO`). Une unicite levee APRES l'INSERT de l'evenement (ici par la projection)
        # laisserait sinon l'evenement en base, muet : ni applique, ni echec.
        es = self._es()
        u_a, u_b = sorted(self._ulids(2))
        self._ecrire_runs([self._ligne(u_a), self._ligne(u_b, task_id="T-65b")], auteur="auteurZ", copie="copie65b")
        vrai = es.EventStore._apply_projection

        def projeter(store, cursor, task_id, *args, **kwargs):
            if task_id == "T-65b":
                exc = sqlite3.IntegrityError("UNIQUE constraint failed: injecte apres l'INSERT")
                exc.sqlite_errorname = "SQLITE_CONSTRAINT_UNIQUE"
                raise exc
            return vrai(store, cursor, task_id, *args, **kwargs)

        espion, resumes = self._espionner_reconstruire()
        with espion, mock.patch.object(es.EventStore, "_apply_projection", projeter):
            _, err = self._ouvrir_defaut()
        res = resumes[-1]
        self.assertEqual((1, 0), (res["applied"], res["echecs"]), res)
        entres = {u for (u,) in sqlite3.connect(str(self._base_defaut())).execute("SELECT ulid FROM events_ledger")}
        self.assertIn(u_a, entres)
        self.assertNotIn(u_b, entres, "l'evenement d'une ligne ecartee pour unicite reste en base : ROLLBACK TO saute")
        self.assertNotIn(f"ulid={u_b}", err)
