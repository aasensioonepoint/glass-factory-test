"""Durcissement du fichier de déversement de la `sync_outbox` (T-00001081, suite advisory de T-00001006).

Trois bornes de `tasks_deversement.py` :
(a) une ligne JSON trop imbriquée fait lever `RecursionError` à `json.loads`, et `RecursionError` n'est PAS une
    `ValueError` (mesuré : sa MRO est `RuntimeError`). Rattrapée avec elle, elle devient une entrée à part au comptage
    du déversement, et un refus NOMMÉ au rejeu (`DeverseIllisible`, numéro de ligne), jamais une exception qui remonte ;
(b) une FIFO à la place du fichier est ouverte en `O_NONBLOCK` puis refusée par `S_ISREG` sur le descripteur OUVERT,
    sans attendre d'écrivain, et elle n'est pas renommée ;
(c) la borne Windows (ni `O_NOFOLLOW` ni `O_NONBLOCK`) est dite dans la docstring de `_ouvrir_sans_lien`.

Le seuil de récursion de `json` dépend de l'interpréteur (mesuré sous 3.14.7 : 10**5 niveaux passent, 10**6 lèvent).
La ligne empoisonnée est donc bien imbriquée, mais sa levée passe par un `json.loads` substitué (`mock.patch`) qui
lève sur CES octets seuls, jamais par l'interpréteur courant ; chaque témoin compte ses passages sur la ligne.

Montage minimal, sans pont V3 : un board vide, cinq intents posés par `enqueue_sync_intent`, un seuil abaissé à 2.
Les témoins FIFO sautent, en le nommant, là où `os.mkfifo` n'existe pas (Windows).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
SPEC = importlib.util.spec_from_file_location("tasks_deversement_durcissement_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

#: Ligne bien imbriquée ; la levée de `RecursionError` sur elle est substituée (voir la docstring du module).
POISON = b"[" * 1_000_000 + b"]" * 1_000_000
#: Garde de chaque fil qui ouvre une FIFO : au-delà, l'ouverture est dite BLOQUÉE.
GARDE_S = 5.0
_LOADS = json.loads


class DurcissementDeversementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "repo"
        board_dir = self.root / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        self.board = board_dir / "TASKS.json"
        self.board.write_text(
            json.dumps({"next_id": 1, "tasks": [], "sync_outbox": [], "sync_correlations": {}}),
            encoding="utf-8",
        )
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(base / "state"),
            "AGENTS_EVENTS_DIR": str(base / "events"),
        })
        env.start()
        self.addCleanup(env.stop)
        data = tasks.load(str(self.root))
        for i in range(5):
            tasks.enqueue_sync_intent(data, f"banc-{i}", None, None)
        tasks.save(str(self.root), data)
        self.ecrits = [intent["operation_id"] for intent in data["sync_outbox"]]
        self.fichier = tasks._chemin_deverse(str(self.root))
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        self.passages = 0

    # -- outillage --------------------------------------------------------------
    def _outbox(self) -> list[str]:  # la VUE (T-00001058, O2), jamais le JSON brut
        return [intent["operation_id"] for intent in tasks.load(str(self.root))["sync_outbox"]]

    def _intent_au_board(self, rang: int) -> bytes:
        intent = tasks.load(str(self.root))["sync_outbox"][rang]
        return json.dumps(intent, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"

    @contextmanager
    def _recursion(self) -> Iterator[None]:
        """`json.loads` lève `RecursionError` sur `POISON` seul, et compte ces passages ; le reste est délégué."""

        def loads(texte: Any, *args: Any, **kwargs: Any) -> Any:
            if texte == POISON:
                self.passages += 1
                raise RecursionError("banc : imbrication trop profonde")
            return _LOADS(texte, *args, **kwargs)

        with mock.patch.object(tasks.json, "loads", new=loads):
            yield

    def _poser_fifo(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("os.mkfifo absent ici (Windows) : aucune FIFO à poser à la place du fichier")
        os.mkfifo(self.fichier, 0o600)

    def _sous_garde(self, appel: Any) -> dict[str, Any]:
        """Joue `appel` dans un fil borné par `GARDE_S`. Fil encore vivant : l'ouverture attend un écrivain. On en
        ouvre un pour libérer le fil, puis on échoue en le disant."""
        rendu: dict[str, Any] = {}

        def corps() -> None:
            try:
                rendu["valeur"] = appel()
            except BaseException as exc:  # le témoin juge le type ; rien ne doit mourir dans le fil
                rendu["exc"] = exc

        fil = threading.Thread(target=corps, daemon=True)
        fil.start()
        fil.join(GARDE_S)
        if fil.is_alive():
            try:
                os.close(os.open(self.fichier, os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass  # ENXIO : le fil n'attend pas sur la FIFO ; l'échec ci-dessous le dit quand même
            fil.join(GARDE_S)
            self.fail(f"BLOQUÉ plus de {GARDE_S} s sur une FIFO à la place de {self.fichier.name}")
        return rendu

    def _rejoues(self) -> list[str]:
        return [nom for nom in os.listdir(self.fichier.parent) if ".rejoue-" in nom]

    # -- (a) RecursionError ------------------------------------------------------
    def test_A1_ligne_trop_imbriquee_au_deversement_une_entree_a_part_jamais_une_levee(self) -> None:
        """Une ligne déjà au fichier lève `RecursionError` au comptage des intents distincts. Base : la levée remonte
        hors de `_deverser_excedent` APRÈS l'ajout au fichier et AVANT le `save`. Attendu : 3 déversés, 4 distincts
        (3 `operation_id` + la ligne opaque), 2 au board, la ligne illisible gardée en tête du fichier."""
        self.fichier.write_bytes(POISON + b"\n")
        err = io.StringIO()
        with self._recursion(), mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 2), mock.patch("sys.stderr", err):
            rendu = tasks._deverser_excedent(str(self.root))
        self.assertGreaterEqual(self.passages, 1, "la ligne empoisonnée n'est plus lue : le témoin ne mesure rien")
        self.assertEqual((3, 4, 2), rendu, err.getvalue())
        self.assertEqual(self.ecrits[3:], self._outbox())
        lignes = self.fichier.read_bytes().split(b"\n")
        self.assertEqual(POISON, lignes[0])
        self.assertEqual(self.ecrits[:3], [_LOADS(ligne)["operation_id"] for ligne in lignes[1:-1]])
        self.assertIn("AU SEUIL", err.getvalue())

    def test_A2_ligne_trop_imbriquee_au_rejeu_refus_nomme_rien_n_est_draine(self) -> None:
        """Au rejeu, la ligne 2 lève `RecursionError`. Base : elle traverse `_reinjecter_deverses` ET
        `drain_sync_outbox`, qui n'attendent que `OSError`/`ValueError`. Attendu : `DeverseIllisible` qui nomme la
        ligne, une ligne `rejeu du déversement IMPOSSIBLE` sur stderr, rien de livré, fichier et outbox intacts."""
        self.fichier.write_bytes(self._intent_au_board(0) + POISON + b"\n")
        brut = self.fichier.read_bytes()
        livres: list[Any] = []
        err = io.StringIO()
        with self._recursion(), mock.patch("sys.stderr", err):
            with self.assertRaises(tasks.DeverseIllisible) as refus:
                tasks.drain_sync_outbox(str(self.root), livres.append)
        self.assertGreaterEqual(self.passages, 1, "la ligne empoisonnée n'est plus lue : le témoin ne mesure rien")
        self.assertIn("ligne 2", str(refus.exception))
        annonces = [l for l in err.getvalue().splitlines() if "rejeu du déversement IMPOSSIBLE" in l]
        self.assertEqual(1, len(annonces), err.getvalue())
        self.assertIn("ligne 2", annonces[0])
        self.assertEqual([], livres)
        self.assertEqual(brut, self.fichier.read_bytes())
        self.assertEqual([], self._rejoues())
        self.assertEqual(self.ecrits, self._outbox())

    # -- (b) FIFO ----------------------------------------------------------------
    def test_B1_fifo_au_rejeu_refusee_sans_attendre_ni_renommer(self) -> None:
        """Base, mesuré : `open("rb")` attend un écrivain (fil BLOQUÉ) ; libéré, il rejoue 0 intent puis RENOMME la
        FIFO en `.rejoue-<ns>`. Attendu : `DeverseIllisible` qui dit « pas un fichier régulier », dans la garde, la
        FIFO toujours là et toujours une FIFO, aucun `.rejoue-*`, l'outbox intacte. Sans `O_NONBLOCK` le fil bloque ;
        sans `S_ISREG` après l'ouverture, la FIFO vide est rejouée puis renommée : chacun des deux rougit ici."""
        self._poser_fifo()
        rendu = self._sous_garde(lambda: tasks._reinjecter_deverses(str(self.root)))
        self.assertIsInstance(rendu.get("exc"), tasks.DeverseIllisible, rendu)
        self.assertIn("pas un fichier régulier", str(rendu["exc"]))
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.fichier).st_mode), "la FIFO a été remplacée")
        self.assertEqual([], self._rejoues())
        self.assertEqual(self.ecrits, self._outbox())

    def test_B2_fifo_au_deversement_refus_nomme_intents_gardes_au_board(self) -> None:
        """Côté ajout (`"a+b"`, donc `O_RDWR`), la base ne bloquait pas sur darwin : elle refusait DÉJÀ, mais par
        accident, sur le `seek` (« File or stream is not seekable. »). Seule la CAUSE nommée rougit sur la base :
        attendu `pas un fichier régulier` sur la ligne `déversement IMPOSSIBLE`, `None`, le signal
        `sync-outbox-deverse-impossible`, les cinq intents au board, la FIFO intacte."""
        self._poser_fifo()
        raisons: list[str] = []
        err = io.StringIO()
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 2), mock.patch("sys.stderr", err):
            rendu = self._sous_garde(lambda: tasks._deverser_excedent(str(self.root), signaler=raisons.append))
        self.assertNotIn("exc", rendu, rendu)
        self.assertIsNone(rendu["valeur"])
        annonces = [l for l in err.getvalue().splitlines() if "déversement IMPOSSIBLE" in l]
        self.assertEqual(1, len(annonces), err.getvalue())
        self.assertIn("pas un fichier régulier", annonces[0])
        self.assertEqual(["sync-outbox-deverse-impossible"], raisons)
        self.assertEqual(self.ecrits, self._outbox())
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.fichier).st_mode))

    # -- (c) borne Windows -------------------------------------------------------
    def test_C1_la_borne_windows_est_dite_a_l_ouverture(self) -> None:
        doc = tasks._ouvrir_sans_lien.__doc__ or ""
        for mot in ("Windows", "O_NOFOLLOW", "O_NONBLOCK", "S_ISREG", "DERNIER composant"):
            self.assertIn(mot, doc, f"la docstring de `_ouvrir_sans_lien` ne dit pas « {mot} »")


if __name__ == "__main__":
    unittest.main()
