"""Drain V3 en ÉCHEC sans refus du pont (T-00001053, BK-766) : canal d'échec, déversement à la sortie, restitution.

Le pont se CONSTRUIT, mais le drain s'arrête sur un échec : le consumer lève, ou confirme `False`. Avant T-00001053,
l'outbox grossissait sans borne, `replay-sync` rendait 0 et chaque drain réécrivait tout le fichier de déversement
dans une trace `.rejoue-*`. Ici : la cause est NOMMÉE et remonte par `echec` (`replay-sync` rend 1), les intents
au-delà de 200 sont déversés à la sortie du drain, ceux que le drain venait de reprendre au fichier et n'a pas livrés
y RETOURNENT, copie du board (la trace ne garde que ses autres lignes, sauf sous une garde, dite sur stderr), et une
attente de verrou d'écrivain n'est payée qu'UNE fois par commande. W1 est le critère de BK-766, au seuil de production.
W13 à W17 : passe de correction de la clôture (attempt, temporaire orphelin, code étendu, gardes, fausse alarme).

Montage EMPRUNTÉ à `test_tasks_pont_v3.PontV3RefuseNeGelePasLeBoardTests` (SYM-10824, `setUp` SYM-10825) et à
`test_tasks_pont_v3_deverse.DeversementSousRefusTests` (SYM-12042) : fonctions référencées, jamais héritées, aucun
témoin de ces modules n'est recollecté ici. Le consumer est remplacé sur `BoardBridge.consume_board_intent`, le
chemin que prend `replay_sync` ; le pont, lui, charge SON `tasks` (`_tasks_module`), patché à part (W11).
"""
from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import time
import unittest
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import test_tasks_pont_v3 as base
import test_tasks_pont_v3_deverse as deverse

tasks = base.tasks


def _faux(_pont: Any, _intent: dict[str, Any]) -> bool:
    """Consumer qui confirme `False` sans rien écrire : la classe 1 de BK-766."""
    return False


def _leve(exc: BaseException) -> Callable[[Any, dict[str, Any]], bool]:
    def consumer(_pont: Any, _intent: dict[str, Any]) -> bool:
        raise exc

    return consumer


def _ids(chemin: Path) -> list[str]:
    return [json.loads(ligne)["operation_id"] for ligne in chemin.read_bytes().split(b"\n")[:-1]]


class DrainEnEchecTests(unittest.TestCase):
    # Jamais une classe empruntée liée au niveau du module : pytest la recollecterait.
    def setUp(self) -> None:
        tasks._RESOLVEUR_V3.charger_paquet(base.REPO, "agentic_v3")
        base.PontV3RefuseNeGelePasLeBoardTests.setUp(self)
    _main = base.PontV3RefuseNeGelePasLeBoardTests._main
    _board = base.PontV3RefuseNeGelePasLeBoardTests._board
    _lignes = staticmethod(base.PontV3RefuseNeGelePasLeBoardTests._lignes)
    _amorcer_store = base.PontV3RefuseNeGelePasLeBoardTests._amorcer_store
    _exiger_sqlite_errorcode = base.PontV3RefuseNeGelePasLeBoardTests._exiger_sqlite_errorcode
    _seuil = deverse.DeversementSousRefusTests._seuil
    _refus = deverse.DeversementSousRefusTests._refus
    _auteur = deverse.DeversementSousRefusTests._auteur
    fichier = deverse.DeversementSousRefusTests.fichier
    _deverses = deverse.DeversementSousRefusTests._deverses
    _outbox = deverse.DeversementSousRefusTests._outbox
    _raisons = deverse.DeversementSousRefusTests._raisons
    _v3 = deverse.DeversementSousRefusTests._v3
    _refuses = deverse.DeversementSousRefusTests._refuses

    # -- outillage --------------------------------------------------------------
    def _consumer(self, consumer: Callable[[Any, dict[str, Any]], bool]):
        return mock.patch.object(self.board_bridge.BoardBridge, "consume_board_intent", consumer)

    def _panne_auteur(self):
        """Classe 2 : le VRAI consumer commite en base, puis `_flush_export` lève (`PanneInfrastructure`)."""
        panne = self.run_export.PanneInfrastructure("banc : git config user.email en echec (127)")
        return mock.patch.object(self.run_export, "_email_git", side_effect=panne)

    def _traces(self) -> list[Path]:
        return sorted(self.fichier.parent.glob(self.fichier.name + ".rejoue-*"))

    def _lignes_traces(self) -> list[str]:
        return [o for t in self._traces() for o in _ids(t)]

    def _attempts(self) -> list[int]:
        return [json.loads(ligne)["attempt"] for ligne in self.fichier.read_bytes().split(b"\n")[:-1]]

    def _non_faite(self, err: str) -> list[str]:
        return self._lignes(err, "restitution NON faite")

    def _commandes(self, prefixe: str, n: int, ecrits: list[str], *, apres: Callable[[int], None] | None = None) -> None:
        """`n` `new` ; chaque `operation_id` NEUF (outbox, fichier ou trace) est ajouté à `ecrits`, dans l'ordre."""
        for i in range(n):
            vus = set(self._outbox()) | set(self._deverses()) | set(self._lignes_traces())
            rc, _out, err = self._main("new", f"{prefixe}{i}")
            self.assertEqual(0, rc, err)
            ecrits += [o for o in self._deverses() + self._outbox() if o not in vus and o not in ecrits]
            if apres is not None:
                apres(i)

    @contextmanager
    def _sonde(self, attendus: Callable[[], set[str]], suppression: str | None = None) -> Iterator[list[str]]:
        """Après CHAQUE `save` du board, chaque substitution (`_replace_with_retry`) et chaque `fsync` (écriture du
        fichier) : chaque intent attendu est dans le fichier ∪ l'outbox, et la suppression en vol reste visible de
        `suppressions_en_vol` (T-00001060). Rend la liste des écarts, et une entrée « sondes » par sonde jouée."""
        ecarts: list[str] = []
        racine = str(self.root)

        def sonder(ou: str) -> None:
            ecarts.append("sondes")
            manquants = attendus() - set(self._outbox()) - set(self._deverses())
            if manquants:
                ecarts.append(f"{ou} : hors fichier et hors outbox {sorted(manquants)}")
            if suppression is not None and suppression not in tasks.suppressions_en_vol(tasks.load(racine), racine):
                ecarts.append(f"{ou} : suppression de {suppression} invisible")

        vrai_save, vrai_replace, vrai_fsync = tasks.save, tasks._replace_with_retry, os.fsync

        def save(*a: Any, **k: Any) -> None:
            vrai_save(*a, **k)
            sonder("save")

        def replace(*a: Any, **k: Any) -> None:
            vrai_replace(*a, **k)
            sonder("replace")

        def fsync(fd: int) -> None:
            vrai_fsync(fd)
            sonder("fsync")

        with mock.patch.object(tasks, "save", save), mock.patch.object(tasks, "_replace_with_retry", replace), \
                mock.patch.object(tasks.os, "fsync", fsync):
            yield ecarts

    def _sans_ecart(self, ecarts: list[str]) -> None:
        self.assertIn("sondes", ecarts, "aucune sonde jouée : le banc ne mesure rien")
        self.assertEqual([], [e for e in ecarts if e != "sondes"])

    # -- témoins ----------------------------------------------------------------
    def test_W1_critere_BK766_consumer_faux_seuil_200_le_board_ne_depasse_jamais_200(self) -> None:
        """BK-766 au seuil de PRODUCTION : le consumer confirme `False`, 205 `new` (pont construit, aucun refus) ; le
        board ne dépasse jamais 200, les 205 intents sont au board ou au fichier, aucune trace ; puis le pont sain
        livre tout. Mutant m11 (déversement de sortie retiré) -> 205 au board."""
        self.assertEqual(200, tasks._SYNC_OUTBOX_SEUIL)
        ecrits: list[str] = []
        with self._auteur(), self._consumer(_faux):
            self._commandes("t", 205, ecrits, apres=lambda i: self.assertLessEqual(len(self._outbox()), 200, i))
        self.assertEqual(205, len(ecrits))
        self.assertEqual(set(ecrits), set(self._outbox()) | set(self._deverses()))
        self.assertEqual([], self._traces())
        with self._auteur():
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed", out)
        self.assertEqual([], self._outbox())
        self.assertEqual(set(), set(ecrits) - self._v3()[0])

    def test_W2_classe_1_aucune_trace_et_un_fichier_sans_doublon(self) -> None:
        """Seuil 3, 12 `new`, consumer `False` : aucune trace (chaque drain rend au fichier ce qu'il en a repris), le
        fichier sans doublon, « fichier puis board » = l'ordre d'écriture. Mutant m1 (restitution retirée) -> une
        trace pleine par drain."""
        ecrits: list[str] = []
        with self._auteur(), self._consumer(_faux), self._seuil(3):
            self._commandes("t", 12, ecrits, apres=lambda i: self.assertLessEqual(len(self._outbox()), 3, i))
        self.assertEqual([], self._traces())
        self.assertEqual(len(set(self._deverses())), len(self._deverses()), "doublon dans le fichier")
        self.assertEqual(ecrits, self._deverses() + self._outbox(), "intent perdu ou ordre FIFO rompu")

    def test_W3_classe_2_commit_puis_levee_les_traces_ne_dupliquent_aucune_ligne(self) -> None:
        """Le témoin de B-C1 : fichier bâti par le refus de T-1006 (E0 >= 30), puis le VRAI consumer commite et
        `_flush_export` lève, seuil 20, 40 `new`. Chaque ligne en trace est DISTINCTE (une trace d'une ligne par drain
        qui livre puis lève), au plus 600 octets par ligne, V3 reçoit +2 intents par commande, puis tout à la levée.
        Mutant m1 -> chaque drain recopie tout le fichier dans une trace."""
        self._amorcer_store()
        ecrits, _ = self._refuses(*[("new", f"p{i}") for i in range(55)], seuil=20)
        self.assertGreaterEqual(len(self._deverses()), 30, "fichier trop court : le banc ne mesure rien")
        progression: list[int] = []
        with self._panne_auteur(), self._seuil(20):
            avant = [len(self._v3()[0])]

            def compter(_i: int) -> None:
                progression.append(len(self._v3()[0]) - avant[0])
                avant[0] = len(self._v3()[0])

            self._commandes("q", 40, ecrits, apres=compter)
        lignes = self._lignes_traces()
        self.assertEqual(len(set(lignes)), len(lignes), "une ligne recopiée d'une trace à l'autre")
        self.assertLessEqual(sum(t.stat().st_size for t in self._traces()), 600 * max(1, len(set(lignes))))
        self.assertEqual({2}, set(progression))
        with self._auteur(), self._seuil(20):
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertEqual([], self._outbox())
        self.assertEqual(set(), set(ecrits) - self._v3()[0])

    def test_W4_replay_sync_rend_1_et_nomme_la_cause_puis_0_une_fois_sain(self) -> None:
        """À l'échelle d'UNE commande : `replay-sync` rend 1 avec une ligne « drain V3 en ECHEC » qui porte la cause —
        `False`, code SQLite 5, `RuntimeError` ; sain, il rend 0 et « replayed ». Mutants m7 (`refus` non posé) -> rc 0 ;
        m8 (`cause = repr(exc)` retiré) -> la cause du code 5 est perdue."""
        verrou = sqlite3.OperationalError("database is locked")
        verrou.sqlite_errorcode = 5  # type: ignore[attr-defined]
        for bras, consumer, cause in (
                ("confirme False", _faux, "confirmation refusee par le consumer"),
                ("code 5", _leve(verrou), "database is locked"),
                ("RuntimeError", _leve(RuntimeError("banc : panne nommee W4")), "banc : panne nommee W4")):
            with self.subTest(bras):
                if not self._outbox():
                    tasks.new_task(str(self.root), "w4", "dev-multi")
                with self._auteur(), self._consumer(consumer):
                    rc, out, err = self._main("replay-sync")
                self.assertEqual(1, rc, err)
                lignes = self._lignes(err, "drain V3 en ECHEC")
                self.assertEqual(1, len(lignes), err)
                self.assertIn(cause, lignes[0])
                self.assertNotIn("replayed", out)
                self.assertEqual([], self._non_faite(err), "aucun fichier repris : rien à restituer, aucune alarme")
        with self._auteur():
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertIn("replayed", out)
        self.assertEqual([], self._lignes(err, "drain V3 en ECHEC"))
        self.assertEqual([], self._outbox())

    def test_W5_a_chaque_instant_chaque_intent_est_au_fichier_ou_a_l_outbox(self) -> None:
        """Ordre d'écriture de la restitution : fichier vivant (écrit, `fsync`) AVANT le `save` du board. Sondé après
        chaque `save`, substitution et `fsync`, sur une restitution qui aboutit puis sur une dont le `save` lève ; la
        suppression d'une tâche purgée reste visible de `suppressions_en_vol` avant, pendant et après ; la levée
        livre tout. Mutant m2 (board avant fichier) -> un instant où les intents repris ne sont nulle part."""
        racine = str(self.root)
        self._refuses(("new", "g1"), seuil=10**6)
        (purgee,) = [t["id"] for t in self._board()["tasks"] if t["task"] == "g1"]
        self._refuses(("done", purgee, "--raison", "fin"), ("purge",), seuil=10**6)
        self._refuses(*[("new", f"n{i}") for i in range(4)], seuil=3)
        ecrits = self._deverses() + self._outbox()
        self.assertEqual(7, len(ecrits))
        self.assertIn(purgee, tasks.suppressions_en_vol(tasks.load(racine), racine), "avant")
        self.assertEqual(4, len(self._deverses()), "la suppression doit partir au fichier : le banc ne mesure rien")
        with self.subTest("restitution aboutie"):
            with self._sonde(lambda: set(ecrits), purgee) as ecarts, self._seuil(3), \
                    mock.patch("sys.stderr", io.StringIO()):
                tasks.drain_sync_outbox(racine, lambda _i: False)
            self._sans_ecart(ecarts)
            self.assertEqual(ecrits, self._deverses() + self._outbox())
            self.assertEqual([], self._traces())
        with self.subTest("save du board en échec pendant la restitution"):
            vrai, etat = tasks._restituer_deverse, {"dans": False, "levee": 0}

            def restituer(*a: Any, **k: Any) -> bool:
                etat["dans"] = True
                try:
                    return vrai(*a, **k)
                finally:
                    etat["dans"] = False

            with self._sonde(lambda: set(ecrits), purgee) as ecarts, self._seuil(3), \
                    mock.patch("sys.stderr", io.StringIO()):
                sonde_save = tasks.save

                def save(*a: Any, **k: Any) -> None:
                    if etat["dans"] and not etat["levee"]:
                        etat["levee"] += 1
                        raise OSError("banc : save du board en echec pendant la restitution")
                    sonde_save(*a, **k)

                with mock.patch.object(tasks, "_restituer_deverse", restituer), mock.patch.object(tasks, "save", save):
                    tasks.drain_sync_outbox(racine, lambda _i: False)
            self.assertEqual(1, etat["levee"], "le save n'a pas levé : le banc ne mesure rien")
            self._sans_ecart(ecarts)
            self.assertEqual(set(ecrits), set(self._deverses()) | set(self._outbox()))
        self.assertIn(purgee, tasks.suppressions_en_vol(tasks.load(racine), racine), "après")
        with self._auteur():
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertEqual(set(), set(ecrits) - self._v3()[0])
        self.assertEqual(1, self._v3()[1].get(purgee), "la suppression n'a pas atteint V3")

    def test_W6_gardes_bail_vivant_et_fichier_reparu_rien_n_est_touche(self) -> None:
        """(a) un intent repris porte un bail VIVANT d'un autre ouvrier : la restitution ne touche rien, la trace reste
        pleine, rien n'est perdu (mutant m3, garde de bail retirée). (b) le fichier REPARAÎT pendant la livraison (effet
        de bord du consumer) : ses octets sont intacts (mutant m4, `xb` -> `wb` et garde du fichier retirées)."""
        racine = str(self.root)
        with self.subTest("a : bail vivant"):
            ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)

            def bail(_intent: dict[str, Any]) -> bool:
                with tasks.board_lock(racine):
                    data = tasks.load(racine)
                    data["sync_outbox"][1]["lease"] = {"owner": "autre", "token": "w6", "expires_at": time.time() + 3600}
                    tasks.save(racine, data)
                return False

            err = io.StringIO()
            with self._seuil(10**6), mock.patch("sys.stderr", err):
                tasks.drain_sync_outbox(racine, bail)
            self.assertFalse(self.fichier.exists(), "restitution malgré un bail vivant")
            self.assertEqual([ecrits[:2]], [_ids(t) for t in self._traces()], "trace réduite malgré un bail vivant")
            self.assertEqual(ecrits, self._outbox())
            self.assertEqual("w6", self._board()["sync_outbox"][1]["lease"]["token"])
            self.assertEqual(1, len(self._non_faite(err.getvalue())), "C2 : retour de la restitution jeté en silence")
        self.setUp()
        racine = str(self.root)
        with self.subTest("b : fichier reparu"):
            ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
            octets: dict[str, bytes] = {}

            def reparu(_intent: dict[str, Any]) -> bool:
                with tasks.board_lock(racine):
                    data = tasks.load(racine)
                    dernier = data["sync_outbox"].pop()
                    octets["fichier"] = json.dumps(dernier, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                    self.fichier.write_bytes(octets["fichier"])
                    tasks.save(racine, data)
                return False

            err = io.StringIO()
            with self._seuil(10**6), mock.patch("sys.stderr", err):
                tasks.drain_sync_outbox(racine, reparu)
            self.assertEqual(octets["fichier"], self.fichier.read_bytes(), "fichier reparu réécrit")
            self.assertEqual([ecrits[:2]], [_ids(t) for t in self._traces()])
            self.assertEqual(set(ecrits), set(self._outbox()) | set(self._deverses()))
            self.assertEqual(1, len(self._non_faite(err.getvalue())), "C2 : retour de la restitution jeté en silence")

    def test_W7_un_ACK_perdu_n_est_pas_un_echec(self) -> None:
        """Consumer vrai, `ack_sync_event` rend `False` (bail repris par un autre) : `echec` reste vide, rien n'est
        restitué ni déversé, aucune ligne d'échec, retour 0. Mutant m9 (`if cause is None`) -> un échec inventé."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        echec: dict[str, Any] = {}
        err = io.StringIO()
        with self._seuil(3), mock.patch.object(tasks, "ack_sync_event", return_value=False), \
                mock.patch("sys.stderr", err):
            self.assertEqual(0, tasks.drain_sync_outbox(str(self.root), lambda _i: True, echec=echec))
        self.assertEqual({}, echec)
        self.assertEqual(ecrits, self._outbox(), "déversé ou restitué sur un ACK perdu")
        self.assertFalse(self.fichier.exists())
        self.assertEqual([], self._lignes(err.getvalue(), "AU SEUIL"))
        self.assertNotIn("confirmation refusee", err.getvalue())

    def test_W8_hors_verrou_le_second_drain_n_est_pas_saute(self) -> None:
        """B-C9 : un consumer qui lève HORS code 5 est rappelé par le drain d'après le verbe — DEUX appels pour une
        commande qui trouve un intent en attente ; le rythme de drainage ne baisse pas. Mutant m5 (mémo sur tout
        échec) -> un appel."""
        appels: list[str] = []

        def disque_plein(_pont: Any, intent: dict[str, Any]) -> bool:
            appels.append(intent["operation_id"])
            raise OSError("banc : disque plein W8")

        with self._auteur(), self._consumer(disque_plein):
            rc, _out, err = self._main("new", "a")
            self.assertEqual(0, rc, err)
            avant = len(appels)
            rc, _out, err = self._main("new", "b")
        self.assertEqual(0, rc, err)
        self.assertEqual(2, len(appels) - avant, "second drain sauté hors verrou")

    def test_W9_vrai_verrou_WAL_une_seule_attente_par_commande_replay_sync_rend_1(self) -> None:
        """Patron de T18 : verrou d'écrivain WAL RÉEL, attente ramenée à 50 ms. Le 2e `new` trouve un intent en
        attente : UNE ligne « store verrouille par un autre ecrivain » (le drain d'après le verbe est sauté) ;
        `replay-sync` rend 1. Mutant m6 (mémo retirée) -> deux lignes, deux attentes."""
        self._exiger_sqlite_errorcode()
        self._amorcer_store()
        from agentic_v3.db import schema

        verrou = sqlite3.connect(str(self.store), isolation_level=None)
        self.addCleanup(verrou.close)
        verrou.execute("BEGIN IMMEDIATE")
        verrou.execute("CREATE TABLE IF NOT EXISTS banc_verrou(x)")
        with mock.patch.object(schema, "_connexion_nue", lambda uri: sqlite3.connect(uri, uri=True, timeout=0.05)), \
                self._auteur():
            rc, _out, err = self._main("new", "a")
            self.assertEqual(0, rc, err)
            self.assertGreaterEqual(len(self._outbox()), 1, "aucun intent en attente : le banc ne mesure rien")
            rc, _out, err = self._main("new", "b")
            self.assertEqual(0, rc, err)
            self.assertEqual(1, len(self._lignes(err, "store verrouille par un autre ecrivain")), err)
            rc, _out, err = self._main("replay-sync")
        verrou.rollback()
        self.assertEqual(1, rc, err)
        lignes = self._lignes(err, "drain V3 en ECHEC")
        self.assertEqual(1, len(lignes), err)
        self.assertIn("database is locked", lignes[0])

    def test_W10_le_deversement_sous_echec_est_relaye_par_gate_coverage_degraded(self) -> None:
        """`AGENTS_EVENTS_DIR` posé (montage), consumer `False`, seuil 3 : le déversement de sortie émet
        `sync-outbox-deverse`, sans aucun refus du pont. Mutant m10 (`signaler` non passé) -> aucun événement."""
        with self._auteur(), self._consumer(_faux), self._seuil(3):
            self._commandes("t", 5, [])
        self.assertGreaterEqual(self._raisons().count("sync-outbox-deverse"), 1)
        self.assertEqual([], [r for r in self._raisons() if r.startswith("pont-v3-")])

    def test_W11_le_backlog_v3_vers_board_en_echec_reste_borne_sans_evenement(self) -> None:
        """`BoardBridge._drain_board_backlog` (voie V3->board, SON module `tasks`), fichier présent et board AU-DESSUS du
        seuil 3 : il rend `False`, le board revient au seuil, aucune trace ; sain, il rend `True` et l'outbox est vide.
        Résidu R1 NOMMÉ (réserve C3) : cette voie appelle le drain sans `signaler`, donc AUCUN `gate.coverage_degraded`.
        Mutant m13 (déversement placé dans `replay_sync` seul) -> le board reste au-dessus du seuil."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(6)], seuil=3)
        for titre in ("d1", "d2"):
            tasks.new_task(str(self.root), titre, "dev-multi")  # au board, sans drain : 5 > 3
        ecrits += [o for o in self._outbox() if o not in ecrits]
        self.assertEqual((3, 5), (len(self._deverses()), len(self._outbox())), "le banc ne mesure rien")
        with self._auteur():
            pont = self.board_bridge.BoardBridge(project_root=self.root)
        avant = self._raisons()
        with self._consumer(_faux), mock.patch.object(pont._tasks_module(), "_SYNC_OUTBOX_SEUIL", 3), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertFalse(pont._drain_board_backlog())
        self.assertLessEqual(len(self._outbox()), 3)
        self.assertEqual([], self._traces())
        self.assertEqual(set(ecrits), set(self._outbox()) | set(self._deverses()))
        self.assertEqual(avant, self._raisons(), "résidu R1 : la voie V3->board n'émet rien")
        with self._auteur(), mock.patch("sys.stderr", io.StringIO()):
            self.assertTrue(pont._drain_board_backlog())
        self.assertEqual([], self._outbox())

    def test_W12_deux_livres_puis_echec_une_trace_des_seuls_livres(self) -> None:
        """R6 de T-1006 : deux intents du fichier se livrent, le troisième échoue. `replay-sync` rend 1, le board reste au
        seuil, UNE trace qui ne porte que les deux livrés, rien de perdu, et à chaque instant chaque intent non livré
        est au fichier ou à l'outbox. Réserve C1 : la trace se réduit par UN temporaire
        `sync_outbox_deverse.jsonl.reduite-<ns>` (hors `.rejoue-`, vu du `find` de 7(e)), ouvert par `_ouvrir_sans_lien`,
        substitué, sans reliquat. Mutants m1 (restitution retirée) -> trace pleine ; m2 -> un instant sans eux."""
        ecrits, _ = self._refuses(*[("new", f"e{i}") for i in range(6)], seuil=3)
        self.assertEqual(3, len(self._deverses()), "le banc ne mesure rien")
        vrai, livres = self.board_bridge.BoardBridge.consume_board_intent, []

        def deux_puis_faux(pont: Any, intent: dict[str, Any]) -> bool:
            if len(livres) >= 2:
                return False
            confirme = vrai(pont, intent)
            livres.append(intent["operation_id"])
            return confirme

        ouverts: list[str] = []
        vrai_ouvrir = tasks._ouvrir_sans_lien

        def ouvrir(chemin: str, drapeaux: int) -> int:
            ouverts.append(os.fspath(chemin))
            return vrai_ouvrir(chemin, drapeaux)

        with ExitStack() as pile:
            pile.enter_context(self._auteur())
            pile.enter_context(self._seuil(3))
            pile.enter_context(self._consumer(deux_puis_faux))
            ecarts = pile.enter_context(self._sonde(lambda: set(ecrits) - set(livres)))
            pile.enter_context(mock.patch.object(tasks, "_ouvrir_sans_lien", ouvrir))
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(1, rc, err)
        self.assertEqual(ecrits[:2], livres)
        self.assertLessEqual(len(self._outbox()), 3)
        self.assertEqual([livres], [_ids(t) for t in self._traces()])
        self.assertEqual(set(ecrits), set(livres) | set(self._outbox()) | set(self._deverses()))
        self.assertEqual(set(), set(livres) - self._v3()[0])
        self._sans_ecart(ecarts)
        temporaires = [Path(c).name for c in ouverts if ".reduite" in Path(c).name]
        self.assertEqual(1, len(temporaires), ouverts)
        self.assertIsNotNone(re.fullmatch(r"sync_outbox_deverse\.jsonl\.reduite-\d+", temporaires[0]), temporaires)
        self.assertNotIn(".rejoue-", temporaires[0])
        self.assertEqual([], list(self.fichier.parent.glob("*.reduite*")), "reliquat de temporaire")
        self.assertEqual([], self._non_faite(err), "restitution faite : aucune alarme")
        self.assertEqual([], self._lignes(err, "NON réduite"))

    # -- passe de correction de la clôture (critic-opus C1, C2, C5 ; exec-critic mC, mF, mG, temporaire) ---------
    def _n_puis_faux(self, n: int, livres: list[str]) -> Callable[[Any, dict[str, Any]], bool]:
        """Consumer : les `n` premiers intents passent par le VRAI consumer (livrés, notés dans `livres`), puis `False`."""
        vrai = self.board_bridge.BoardBridge.consume_board_intent

        def consumer(pont: Any, intent: dict[str, Any]) -> bool:
            if len(livres) >= n:
                return False
            confirme = vrai(pont, intent)
            livres.append(intent["operation_id"])
            return confirme

        return consumer

    def test_W13_la_restitution_ecrit_la_copie_du_board_attempt_compte_sans_doublon(self) -> None:
        """C1 : le fichier vivant reçoit la copie du BOARD, dont `release_sync_event` a compté l'échec, jamais les octets
        de la trace. 5 `new` sous refus au seuil 3 (fichier = 2 intents), une ligne DOUBLÉE (`fsync` en échec, D17), puis
        3 `replay-sync` dont le consumer confirme `False` : seule la TÊTE est réservée puis relâchée à chaque drain, donc
        `attempt` = [3, 0], et le doublon ne repart pas au fichier. Code de d72e15d2 (octets recopiés) -> [0, 0, 0]."""
        self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        ids = self._deverses()
        self.assertEqual(([0, 0], 2), (self._attempts(), len(ids)), "le banc ne mesure rien")
        with open(self.fichier, "ab") as fichier:
            fichier.write(self.fichier.read_bytes().split(b"\n")[0] + b"\n")
        vus: list[int] = []

        def faux(_pont: Any, intent: dict[str, Any]) -> bool:
            vus.append(intent["attempt"])
            return False

        for _tour in range(3):
            with self._auteur(), self._consumer(faux), self._seuil(3):
                rc, _out, err = self._main("replay-sync")
            self.assertEqual(1, rc, err)
        self.assertEqual([3, 0], self._attempts(), "attempt figé : octets de la trace recopiés")
        self.assertEqual([0, 1, 2], vus)
        self.assertEqual(ids, self._deverses(), "doublon de la trace recopié au fichier")
        self.assertEqual([], self._traces())

    def test_W14_substitution_de_la_trace_en_echec_ni_orphelin_ni_perte_une_ligne(self) -> None:
        """Exec-critic : la substitution `reduite -> trace` lève (OSError injectée sur le seul `_replace_with_retry` d'un
        `.reduite-`). Le non-livré est rendu au fichier, la trace reste PLEINE, UNE ligne « NON réduite » le dit, et le
        temporaire `.reduite-<ns>` ne reste pas sur disque. Code de d72e15d2 -> un orphelin, aucune ligne."""
        ecrits, _ = self._refuses(*[("new", f"e{i}") for i in range(6)], seuil=3)
        self.assertEqual(3, len(self._deverses()), "le banc ne mesure rien")
        livres: list[str] = []
        vrai_replace, levees = tasks._replace_with_retry, []

        def replace(src: Any, cible: Any) -> None:
            if ".reduite-" in Path(src).name:
                levees.append(Path(src).name)
                raise OSError("banc : substitution de la trace en echec")
            vrai_replace(src, cible)

        with self._auteur(), self._seuil(3), self._consumer(self._n_puis_faux(2, livres)), \
                mock.patch.object(tasks, "_replace_with_retry", replace):
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(1, rc, err)
        self.assertEqual(1, len(levees), "la substitution n'a pas été tentée : le banc ne mesure rien")
        self.assertEqual([], list(self.fichier.parent.glob("*.reduite*")), "temporaire orphelin")
        self.assertEqual([ecrits[:3]], [_ids(t) for t in self._traces()], "la trace doit rester pleine")
        self.assertEqual([ecrits[2]], self._deverses())
        self.assertEqual(1, len(self._lignes(err, "NON réduite")), err)
        self.assertEqual([], self._non_faite(err), "restitution faite : seule la réduction manque")
        self.assertEqual(set(ecrits), set(livres) | set(self._outbox()) | set(self._deverses()))

    def test_W15_code_etendu_517_pose_le_libelle_ET_l_attente(self) -> None:
        """C5 : code SQLite ÉTENDU 517 (SQLITE_BUSY_SNAPSHOT, primaire 5) levé par le consumer d'un drain direct : la
        ligne dit « store verrouille par un autre ecrivain » ET `echec["attente"]` est posé — libellé et mémo lisent le
        même code PRIMAIRE. Mutant mC (masque `& 0xFF` retiré de la condition d'`attente`) -> pas d'attente."""
        etendu = sqlite3.OperationalError("database is locked (snapshot)")
        etendu.sqlite_errorcode = 517  # type: ignore[attr-defined]

        def leve(_intent: dict[str, Any]) -> bool:
            raise etendu

        tasks.new_task(str(self.root), "w15", "dev-multi")
        echec: dict[str, Any] = {}
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(0, tasks.drain_sync_outbox(str(self.root), leve, echec=echec))
        self.assertEqual(1, len(self._lignes(err.getvalue(), "store verrouille par un autre ecrivain")), err.getvalue())
        self.assertIs(True, echec.get("attente"), "code étendu : le mémo d'attente est perdu")
        self.assertIn("database is locked (snapshot)", echec.get("cause", ""))

    def test_W16_gardes_segment_final_interrompu_et_ligne_illisible_rien_n_est_touche(self) -> None:
        """Exec-critic, gardes que la docstring de `_restituer_deverse` annonce : (a) le fichier repris finit par un segment
        NON terminé (ajout interrompu ; la réinjection l'ignore, la trace renommée le garde) ; (b) une ligne illisible
        paraît dans la trace pendant la livraison (altération externe). Rien n'est touché : aucun fichier recréé, trace
        intacte à l'octet, intents au board, UNE ligne « restitution NON faite ». Mutants mF (garde du segment final
        ôtée) et mG (garde de ligne neutralisée) -> fichier recréé, ou levée hors du drain."""
        racine = str(self.root)
        with self.subTest("a : segment final interrompu"):
            ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
            with open(self.fichier, "ab") as fichier:
                fichier.write(b'{"operation_id": "ajout interrompu"')
            avant = self.fichier.read_bytes()
            err = io.StringIO()
            with self._seuil(10**6), mock.patch("sys.stderr", err):
                tasks.drain_sync_outbox(racine, lambda _i: False)
            self.assertFalse(self.fichier.exists(), "restitution malgré un segment final interrompu")
            self.assertEqual([avant], [t.read_bytes() for t in self._traces()])
            self.assertEqual(ecrits, self._outbox())
            self.assertEqual(1, len(self._non_faite(err.getvalue())), err.getvalue())
        self.setUp()
        racine = str(self.root)
        with self.subTest("b : ligne illisible dans la trace"):
            ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
            octets: dict[str, bytes] = {}

            def altere(_intent: dict[str, Any]) -> bool:
                (trace,) = self._traces()
                with open(trace, "ab") as fichier:
                    fichier.write(b"{pas du json\n")
                octets["trace"] = trace.read_bytes()
                return False

            err = io.StringIO()
            with self._seuil(10**6), mock.patch("sys.stderr", err):
                tasks.drain_sync_outbox(racine, altere)
            self.assertIn("trace", octets, "le consumer n'a pas tourné : le banc ne mesure rien")
            self.assertFalse(self.fichier.exists(), "restitution malgré une ligne illisible")
            self.assertEqual([octets["trace"]], [t.read_bytes() for t in self._traces()])
            self.assertEqual(ecrits, self._outbox())
            self.assertEqual(1, len(self._non_faite(err.getvalue())), err.getvalue())

    def test_W17_tous_les_repris_livres_puis_echec_rien_a_restituer_aucune_alarme(self) -> None:
        """Les trois intents repris au fichier se livrent, le quatrième (né au board) échoue : rien à rendre au fichier,
        la trace ne porte que les livrés, et AUCUNE ligne « restitution NON faite » — le patch C2 de la revue imprimait
        sur tout retour faux, donc aussi ici. Mutant « attente vide -> retour faux » -> une fausse alarme."""
        ecrits, _ = self._refuses(*[("new", f"e{i}") for i in range(6)], seuil=3)
        self.assertEqual(3, len(self._deverses()), "le banc ne mesure rien")
        livres: list[str] = []
        with self._auteur(), self._seuil(3), self._consumer(self._n_puis_faux(3, livres)):
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(1, rc, err)
        self.assertEqual(ecrits[:3], livres)
        self.assertEqual([livres], [_ids(t) for t in self._traces()])
        self.assertFalse(self.fichier.exists())
        self.assertEqual([], self._non_faite(err), err)
        self.assertEqual(set(ecrits), set(livres) | set(self._outbox()))


if __name__ == "__main__":
    unittest.main()
