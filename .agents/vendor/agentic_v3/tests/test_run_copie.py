"""Témoins de `run_copie` (T-01M5ETBT21G550XBXPR4V3XPH0) : `run/copie` lue sans suivre de lien,
sans attendre un FIFO, bornée à 64 octets, ASCII strict, 16 hex exacts ; premier tirage `fsync` puis
publié par `os.link` (le perdant d'une course relit le gagnant) ; le relevé des partitions sœurs
(`run_export._lire_copie`) passe par le même lecteur."""

import errno
import os
import stat
import threading
import unittest
from pathlib import Path
from unittest import mock

from agentic_v3.db import run_copie, run_export
from agentic_v3.db.run_export import RESERVE_BACKFILL, RunExportError, identifiant_de_copie
from agentic_v3.tests.test_run_export import _PartitionFixture

_VALIDE = b"0123456789abcdef"


def _sans_blocage(test: unittest.TestCase, fifo: Path, appel) -> object:
    """Joue `appel()` dans un fil ; s'il pend plus de 5 s sur `fifo`, le débloque puis échoue."""
    issue = []

    def jouer() -> None:
        try:
            issue.append(appel())
        except BaseException as exc:  # rapporté au fil principal
            issue.append(exc)

    fil = threading.Thread(target=jouer, daemon=True)
    fil.start()
    fil.join(5)
    if fil.is_alive():
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        fil.join(5)
        test.fail(f"la lecture a BLOQUÉ sur le FIFO {fifo.name}")
    return issue[0]


class TestLectureCopie(_PartitionFixture):
    def _poser(self, contenu: bytes) -> Path:
        fichier = run_export._fichier_copie()
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_bytes(contenu)
        return fichier

    def _refus(self, motif: str) -> RunExportError:
        with self.assertRaisesRegex(RunExportError, motif) as ctx:
            identifiant_de_copie()
        return ctx.exception

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (Windows) : un lien y serait suivi")
    def test_un_lien_symbolique_est_refuse_sans_chemin_absolu(self) -> None:
        cible = self.state.parent / "cible-copie"
        cible.write_bytes(_VALIDE + b"\n")
        fichier = run_export._fichier_copie()
        fichier.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(cible, fichier)
        refus = self._refus("lien symbolique")
        self.assertNotIn(str(self.state), str(refus), "le message nomme run/copie, pas le chemin absolu")
        self.assertTrue(fichier.is_symlink(), "le lien n'est ni remplacé ni retiré")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "pas de FIFO sur cette plateforme")
    def test_un_fifo_est_refuse_sans_blocage(self) -> None:
        fichier = run_export._fichier_copie()
        fichier.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(fichier)
        self.assertIsInstance(_sans_blocage(self, fichier, identifiant_de_copie), RunExportError)

    def test_un_dossier_a_la_place_du_fichier_est_refuse(self) -> None:
        run_export._fichier_copie().mkdir(parents=True)
        self._refus("fichier ordinaire")

    def test_un_dossier_refuse_par_os_open_comme_sous_windows(self) -> None:
        # Windows (non mesuré là-bas) : `os.open` sur un dossier lève PermissionError.
        dossier = run_export._fichier_copie()
        dossier.mkdir(parents=True)
        reel = os.open

        def ouvrir(chemin, drapeaux, *args, **kwargs):
            if Path(chemin) == dossier:
                raise PermissionError(errno.EACCES, "Permission denied", str(dossier))
            return reel(chemin, drapeaux, *args, **kwargs)

        with mock.patch("os.open", side_effect=ouvrir):
            refus = self._refus("fichier ordinaire")
        self.assertNotIn(str(self.state), str(refus))

    def test_une_copie_vide_est_refusee_et_conservee(self) -> None:
        fichier = self._poser(b"")
        refus = self._refus("vide")
        self.assertIn("cadre paths", str(refus), "le remède nomme la commande qui donne le chemin")
        self.assertTrue(fichier.is_file() and fichier.read_bytes() == b"", "jamais retirée en silence")

    def test_exactement_64_octets_est_lu(self) -> None:
        self._poser(_VALIDE + b" " * 48)
        self.assertEqual(identifiant_de_copie(), _VALIDE.decode())

    def test_65_octets_est_refuse(self) -> None:
        # 16 hex valides suivis de blancs : seule la BORNE de taille refuse.
        self._poser(_VALIDE + b" " * 49)
        self._refus("64 octets")

    def test_seize_hex_suivis_d_un_residu_sont_refuses(self) -> None:
        self._poser(_VALIDE + b"zz\n")
        self._refus("mal formé")

    def test_une_valeur_non_hex_est_refusee_et_conservee(self) -> None:
        fichier = self._poser(b"0123456789ABCDEF\n")
        self._refus("mal formé")
        self.assertEqual(fichier.read_bytes(), b"0123456789ABCDEF\n", "jamais retirée en silence")

    def test_un_octet_non_ascii_est_refuse(self) -> None:
        # UTF-8 VALIDE : un décodage utf-8 l'accepterait, seul l'ASCII strict refuse.
        self._poser("0123456789abcdé\n".encode("utf-8"))
        self._refus("non ASCII")

    def test_backfill_reste_refuse_avec_son_message(self) -> None:
        self._poser((RESERVE_BACKFILL + "\n").encode())
        self._refus("S-00001594")
        self.assertEqual(run_copie.RESERVE_BACKFILL, RESERVE_BACKFILL)

    def test_un_identifiant_valide_est_relu_tel_quel(self) -> None:
        fichier = self._poser(_VALIDE + b"\n")
        with mock.patch.object(run_export, "_sonder_partition") as sonde:
            self.assertEqual(identifiant_de_copie(), _VALIDE.decode())
        sonde.assert_not_called()  # relu : aucun tirage, aucune sonde de partition
        self.assertEqual(fichier.read_bytes(), _VALIDE + b"\n")


class TestPublicationCopie(_PartitionFixture):
    def test_course_deux_tirages_rendent_la_meme_valeur(self) -> None:
        premier = identifiant_de_copie()
        fichier = run_export._fichier_copie()
        reel = run_copie.lire_copie_disque
        appels = []

        def lecture_d_avant_la_publication(chemin: Path):
            appels.append(chemin)
            return None if len(appels) == 1 else reel(chemin)

        # Le second démarrage a lu AVANT que le premier publie : il tire, puis
        # trouve `copie` déjà publié et doit rendre la valeur du gagnant.
        with mock.patch.object(run_copie, "lire_copie_disque", side_effect=lecture_d_avant_la_publication):
            second = identifiant_de_copie()
        self.assertEqual(second, premier)
        self.assertEqual(fichier.read_text(encoding="utf-8").strip(), premier)
        self.assertEqual(sorted(p.name for p in fichier.parent.iterdir()), ["copie"], "aucun temporaire laissé")

    def test_le_temporaire_est_fsync_avant_d_etre_publie(self) -> None:
        ordre = []
        fsync_reel, link_reel = os.fsync, os.link

        def fsync(fd):
            ordre.append(("fsync", os.fstat(fd).st_size))
            return fsync_reel(fd)

        def link(src, dst):
            ordre.append("link")
            return link_reel(src, dst)

        with mock.patch("os.fsync", side_effect=fsync), mock.patch("os.link", side_effect=link):
            identifiant_de_copie()
        self.assertEqual(ordre[-1], "link")
        self.assertEqual(ordre[-2][0], "fsync")
        self.assertGreaterEqual(ordre[-2][1], 17, "16 hex + fin de ligne déjà sur disque au fsync (flush)")

    def _sans_lien(self):
        return mock.patch("os.link", side_effect=PermissionError(errno.EPERM, "Operation not permitted"))

    def test_sans_lien_dur_le_repli_publie_puis_relit(self) -> None:
        with self._sans_lien():
            valeur = identifiant_de_copie()
            self.assertEqual(identifiant_de_copie(), valeur, "relu, jamais retiré")
        fichier = run_export._fichier_copie()
        self.assertRegex(valeur, r"^[0-9a-f]{16}$")
        self.assertEqual(fichier.read_bytes(), (valeur + "\n").encode())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(fichier.stat().st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in fichier.parent.iterdir()), ["copie"], "aucun temporaire laissé")

    def test_sans_lien_dur_en_concurrence_rend_le_gagnant(self) -> None:
        premier = identifiant_de_copie()
        reel = run_copie.lire_copie_disque
        appels = []

        def lecture_d_avant_la_publication(chemin: Path):
            appels.append(chemin)
            return None if len(appels) == 1 else reel(chemin)

        with self._sans_lien(), mock.patch.object(
                run_copie, "lire_copie_disque", side_effect=lecture_d_avant_la_publication):
            second = identifiant_de_copie()
        self.assertEqual(second, premier)
        self.assertEqual(run_export._fichier_copie().read_text(encoding="utf-8"), premier + "\n")

    def test_sans_lien_dur_un_echec_du_repli_est_refuse_sans_chemin(self) -> None:
        fichier = run_export._fichier_copie()
        reel = os.open

        def ouvrir(chemin, drapeaux, *args, **kwargs):
            if Path(chemin) == fichier and drapeaux & os.O_CREAT:
                raise PermissionError(errno.EACCES, "Permission denied", str(fichier))
            return reel(chemin, drapeaux, *args, **kwargs)

        with self._sans_lien(), mock.patch("os.open", side_effect=ouvrir):
            with self.assertRaisesRegex(RunExportError, "EACCES") as ctx:
                identifiant_de_copie()
        self.assertNotIn(str(self.state), str(ctx.exception), "errno symbolique, jamais le chemin absolu")
        self.assertEqual(list(fichier.parent.iterdir()), [], "ni copie ni temporaire laissés")


class TestLectureSoeur(_PartitionFixture):
    """`_lire_copie` (relevé des partitions sœurs, à chaque `EventStore`) : le même lecteur durci."""

    def _partition(self) -> Path:
        partition = self.state / "projets" / "aaaaaaaaaaaaaaaa"
        (partition / "run").mkdir(parents=True)
        return partition

    @unittest.skipUnless(hasattr(os, "mkfifo"), "pas de FIFO sur cette plateforme")
    def test_un_fifo_soeur_rend_none_sans_blocage(self) -> None:
        partition = self._partition()
        os.mkfifo(partition / "run" / "copie")
        self.assertIsNone(_sans_blocage(self, partition / "run" / "copie",
                                        lambda: run_export._lire_copie(partition)))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (Windows) : un lien y serait suivi")
    def test_un_lien_soeur_rend_none(self) -> None:
        partition = self._partition()
        cible = self.state.parent / "cible-soeur"
        cible.write_bytes(_VALIDE + b"\n")
        os.symlink(cible, partition / "run" / "copie")
        self.assertIsNone(run_export._lire_copie(partition))

    def test_un_module_run_copie_introuvable_rend_none(self) -> None:
        partition = self._partition()
        with mock.patch.object(run_export, "_run_copie", side_effect=ImportError("run_copie absent")):
            self.assertIsNone(run_export._lire_copie(partition), "jamais de levée, même au chargement")

    def test_une_copie_soeur_valide_est_lue(self) -> None:
        partition = self._partition()
        (partition / "run" / "copie").write_bytes(_VALIDE + b"\n")
        self.assertEqual(run_export._lire_copie(partition), _VALIDE.decode())
