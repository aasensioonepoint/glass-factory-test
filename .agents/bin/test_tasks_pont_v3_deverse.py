"""Déversement de la `sync_outbox` hors du board sous refus du pont V3 (T-00001006, option C, S-00003315).

Au retour mémo d'une commande refusée, au-delà de `_SYNC_OUTBOX_SEUIL` intents, les plus ANCIENS sont AJOUTÉS à un
fichier local non versionné (`.agents/state/local/sync_outbox_deverse.jsonl`, à côté de `TASKS.lock`) puis ôtés de
TASKS.json ; le premier drain dont le pont se construit les remet EN TÊTE, dans l'ordre, puis renomme le fichier. Rien
n'est supprimé : chaque témoin qui reconstruit le pont vérifie que V3 reçoit CHAQUE `operation_id` écrit et CHAQUE tâche
du board. D19 fait VARIER l'adresse du dépôt (renommage, copie, autre état machine) : le fichier la suit.

Montage EMPRUNTÉ à `test_tasks_pont_v3.PontV3RefuseNeGelePasLeBoardTests` (fonctions référencées, jamais héritées : aucun
témoin de la base n'est recollecté ici). Règle des 800 lignes (S-00002684, relevée à 1600 par S-00004034) : module neuf.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tokenize
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import test_tasks_pont_v3 as base

tasks = base.tasks
INTERDITES_CODE = ("sync_outbox_perdus", "AU PLAFOND", "retiré(s)", "miroir V3 INCOMPLET", "_borner_sync_outbox")
#: Phrases du README ÉPINGLÉES mot pour mot (espaces normalisés) ; source unique, lue aussi par apply_rev8.py.
README_117_APRES = (
    'each print one stderr line (plus one `AU SEUIL` line when intents are spilled, see below) and leave '
    'the Board write untouched — a mutating command still exits 0, with the V3 events kept rather than '
    'lost: in the outbox, or beyond 200 pending intents in the spill file described below.'
)
README_117B_APRES = (
    'Since T-00001006, this refusal is also emitted as a `gate.coverage_degraded` event, relayed by the '
    "dashboard's Coverage view and not by `/night` or the hooks, and the outbox holds at most 200 intents "
    '(one per changed task), except in the cases listed below: the oldest are spilled to a local file described below.'
)
README_111_APRES = (
    'a Board write without its V3 effect remains in the file outbox (or, beyond 200 pending intents while '
    'the bridge is refused, in the spill file described below),'
)
PHRASES_README = (
    (
        'While the bridge is refused, the outbox is capped at 200 intents without dropping any (T-00001006): '
        'at the end of a refused mutating command, the oldest intents beyond 200 are appended to a local '
        'file outside the tracked Board, `.agents/state/local/sync_outbox_deverse.jsonl` (git-ignored, next '
        "to `TASKS.lock`), and only then removed from the Board's outbox folder; nothing leaves the Board while its head "
        'is held by a live delivery lease, or when that file cannot be written (one stderr line says so).'
    ),
    (
        'One `TASKS: sync_outbox AU SEUIL` stderr line gives the number spilled, the number waiting outside '
        "the Board and the number left in it; a command on the repository's own board (or with "
        '`AGENTS_EVENTS_DIR` set) also emits `gate.coverage_degraded`, reason `pont-v3-refuse` or '
        '`pont-v3-panne` for a refusal, `sync-outbox-deverse` for a spill, `sync-outbox-deverse-impossible` '
        'when a spill fails and `sync-outbox-rejeu-impossible` when the spill file cannot be put back; the '
        "dashboard's Coverage view relays them, `/night` does not, and outside a hook the host is `unknown`."
    ),
    (
        'The first drain whose bridge is built puts the spilled intents back at the head of the outbox, in '
        'their original order, then renames the file to `sync_outbox_deverse.jsonl.rejoue-<ns>`, which '
        'nothing deletes while it holds an intent (a drain that fails right after putting the intents back '
        'returns the undelivered ones to the spill file and keeps in the trace only its other lines, those '
        'delivered or set aside when put back; otherwise — a live lease on one of them, a spill file that '
        'reappeared, a trace it cannot read in full, a failed write — it keeps that trace whole and one '
        'stderr line says so); '
        'if the file cannot be read or put back, nothing is drained, so that no later '
        'intent overtakes an earlier one, `replay-sync` exits 1, and the outbox grows with every mutating '
        'command, beyond 200, until the file is repaired.'
    ),
    (
        'The spill file is local state, git-ignored like `TASKS.lock`; unlike the generated views of that folder '
        '(TASKS.md, SPECS.md, LEDGER.md), and like the closing-critic traces under `binome/`, no command '
        'regenerates it: it follows the repository folder when it is renamed or copied, but '
        'not a clone, a `git clean -xfd`, a `git worktree remove` or another machine, where those V3 events are lost (the Board is '
        'untouched). A drain that fails without a refusal is bounded the same way (T-00001053): the intents '
        'beyond 200 are spilled at the end of the failed drain and `replay-sync` exits 1 with one '
        '`drain V3 en ECHEC` line naming the cause; an unresolved run root is not bounded this way. '
        'A kit without `agentic_v3` is (T-00001052): a command that '
        'changes a task spills the same way, but no bridge is ever built there, so the spill file is neither '
        'put back nor emptied until `agentic_v3` is installed; it grows by a few hundred bytes per '
        'changed task, and one `TASKS: agentic_v3 absent` stderr line gives its size after each spill; '
        "where neither the kit's `cadre` package (`.agents/vendor/cadre`, or `src/cadre` in the older "
        'layout) nor an installed `cadre` package can be reached, the event of that '
        'spill carries no reason (the event spool then neutralizes its data).'
    ),
)
INTERDITES_README = (
    'kept in the outbox rather than lost', 'sync_outbox_perdus', 'AU PLAFOND', 'are dropped', 'is dropped',
    'Until T-00001006', 'visible on stderr only', 'state_project()/run/sync_outbox_deverse',
    'A kit without `agentic_v3`, a drain that fails', 'keeps in the trace only those it delivered',
    'its intent stays in the outbox;', 'its intent stays in the outbox, and',
)


class DeversementSousRefusTests(unittest.TestCase):
    setUp = base.PontV3RefuseNeGelePasLeBoardTests.setUp
    _main = base.PontV3RefuseNeGelePasLeBoardTests._main
    _board = base.PontV3RefuseNeGelePasLeBoardTests._board
    _lignes = staticmethod(base.PontV3RefuseNeGelePasLeBoardTests._lignes)
    _poser_lien = base.PontV3RefuseNeGelePasLeBoardTests._poser_lien

    # -- outillage --------------------------------------------------------------
    def _seuil(self, valeur: int):
        return mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", valeur)

    def _refus(self):
        from agentic_v3.db.run_export import PanneInfrastructure

        return mock.patch.object(self.board_bridge, "BoardBridge", side_effect=PanneInfrastructure("banc : pont refusé"))

    def _auteur(self):
        return mock.patch.object(self.run_export, "_email_git", return_value="banc@test")

    @property
    def fichier(self) -> Path:
        return tasks._chemin_deverse(str(self.root))

    def _du_deverse(self, fd: int) -> bool:
        """Vrai si `fd` est le fichier de déversement ou son dossier. T-00001058 (O2) : le `save()` du board fait ses
        PROPRES `fsync` (lot, fichiers d'intent, leurs dossiers) ; une faute ou une sonde de `fsync` qui vise le
        déversement se borne donc à LUI, sans quoi elle frappe l'écriture du board, hors du sujet du témoin."""
        st = os.fstat(fd)
        return any(chemin.exists() and os.path.samestat(st, os.stat(chemin)) for chemin in (self.fichier, self.fichier.parent))

    def _disque_plein_au_deverse(self):
        """`fsync` qui lève « disque plein » sur le fichier de déversement SEUL (voir `_du_deverse`)."""
        vrai = os.fsync

        def fsync(fd: int) -> None:
            if self._du_deverse(fd):
                raise OSError("banc : disque plein")
            return vrai(fd)

        return mock.patch.object(tasks.os, "fsync", side_effect=fsync)

    def _deverses(self) -> list[str]:
        if not self.fichier.exists():
            return []
        return [json.loads(l)["operation_id"] for l in self.fichier.read_bytes().split(b"\n")[:-1]]

    def _outbox(self) -> list[str]:
        return [i["operation_id"] for i in self._board()["sync_outbox"]]

    def _raisons(self) -> list[str]:
        dossier = Path(os.environ["AGENTS_EVENTS_DIR"])
        raisons = []
        for f in sorted(dossier.glob("*.jsonl")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(ligne)
                if r.get("kind") == "gate.coverage_degraded":
                    raisons.append((r.get("data") or {}).get("reason"))
        return raisons

    def _hotes(self) -> list[Any]:
        hotes = []
        for f in sorted(Path(os.environ["AGENTS_EVENTS_DIR"]).glob("*.jsonl")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(ligne)
                if r.get("kind") == "gate.coverage_degraded":
                    hotes.append(r.get("host"))
        return hotes

    @staticmethod
    def _id_rendu(out: str) -> str:
        """L'id que `new` A RENDU sur stdout, jamais un id prédit : sous l'allocateur `P-<ULID>` (T-00000726, C2)
        aucune valeur n'est devinable (règle R-BANCS (i))."""
        trouve = re.search(r"^TASKS: (\S+) → pending$", out, re.M)
        assert trouve, f"aucun id rendu par new dans : {out!r}"
        return trouve.group(1)

    def _ids_du_board(self) -> list[str]:
        """Les ids du board dans l'ordre du MAGASIN, qui est l'ordre de création (`new` ajoute en fin)."""
        return [t["id"] for t in self._board()["tasks"]]

    def _v3(self) -> tuple[set[str], dict[str, int], int]:
        c = sqlite3.connect(str(self.store))
        try:
            inbox = {r[0] for r in c.execute("SELECT operation_id FROM board_sync_inbox")}
            mapping = {r[0]: r[1] for r in c.execute("SELECT board_task_id, tombstoned FROM task_board_mapping")}
            echecs = c.execute("SELECT count(*) FROM events_ledger WHERE event_kind='BOARD_COMMAND_FAILED'").fetchone()[0]
        finally:
            c.close()
        return inbox, mapping, echecs

    def _refuses(self, *commandes: tuple[str, ...], seuil: int) -> tuple[list[str], str]:
        """Commandes sous pont refusé ; rend (operation_id de TOUS les intents écrits, dans l'ordre, stderr cumulé)."""
        ecrits, erreurs = [], ""
        with self._refus(), self._seuil(seuil):
            for commande in commandes:
                vus = set(self._outbox()) | set(self._deverses())
                rc, _out, err = self._main(*commande)
                self.assertEqual(0, rc, err)
                erreurs += err
                ecrits += [o for o in self._deverses() + self._outbox() if o not in vus and o not in ecrits]
        return ecrits, erreurs

    def _relever(self, ecrits: list[str]) -> str:
        """Lève le refus : `replay-sync`, puis V3 doit porter CHAQUE intent écrit et CHAQUE tâche du board."""
        with self._auteur():
            rc, _out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertEqual([], self._outbox(), "outbox non vidée par le rejeu")
        self.assertFalse(self.fichier.exists(), "fichier de déversement non renommé")
        inbox, mapping, echecs = self._v3()
        self.assertEqual(set(), set(ecrits) - inbox, "intent absent de V3")
        self.assertEqual(set(), {t["id"] for t in self._board()["tasks"]} - set(mapping), "tâche absente de V3")
        self.assertEqual(0, echecs)
        return err

    # -- témoins ----------------------------------------------------------------
    def test_D1_au_dela_du_seuil_les_plus_anciens_sont_deverses_et_le_board_garde_le_seuil(self) -> None:
        """Cinq `new` refusés, seuil 3 : après la i-ème, board = min(i, 3), fichier = max(0, i - 3), « fichier puis
        board » = l'ordre d'écriture ; une ligne AU SEUIL et un événement `sync-outbox-deverse` par déversement."""
        ecrits, err = [], ""
        for i in range(1, 6):
            e, er = self._refuses(("new", f"t{i}"), seuil=3)
            ecrits += e
            err += er
            self.assertEqual(min(i, 3), len(self._outbox()))
            self.assertEqual(max(0, i - 3), len(self._deverses()))
            self.assertEqual(ecrits, self._deverses() + self._outbox(), "ordre FIFO rompu")
        lignes = self._lignes(err, "AU SEUIL")
        self.assertEqual(2, len(lignes))
        self.assertEqual(
            f"TASKS: sync_outbox AU SEUIL (3) — 1 intent(s) déversé(s) hors du board vers {self.fichier}, 2 en attente "
            "d'un pont, 3 au board ; rien n'est supprimé — rejoués dans l'ordre PAR CE POSTE à la reconstruction du pont "
            "(fichier local .agents/state/local/, non versionné, absent d'un clone)", lignes[-1])
        self.assertEqual(2, self._raisons().count("sync-outbox-deverse"))
        self.assertEqual(5, self._raisons().count("pont-v3-panne"))

    def test_D2_le_pont_reconstruit_rejoue_le_deverse_en_tete_et_V3_est_complet(self) -> None:
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        self.assertEqual(2, len(self._deverses()))
        fichier = self.fichier
        err = self._relever(ecrits)
        self.assertEqual(1, len(self._lignes(err, "2 intent(s) déversé(s) réinjecté(s) en tête, 0 écarté(s)")))
        self.assertEqual(1, len(list(fichier.parent.glob(fichier.name + ".rejoue-*"))), "trace du rejeu absente")

    def test_D3_un_purge_au_dela_du_seuil_deverse_aussi_ses_propres_intents_sans_rien_perdre(self) -> None:
        crees: list[str] = []
        with self._auteur():
            for i in range(1, 5):
                rc, out, err = self._main("new", f"g{i}")
                self.assertEqual(0, rc, err)
                crees.append(self._id_rendu(out))
                self.assertEqual(0, self._main("done", crees[-1], "--raison", "fin")[0])
        self.assertEqual([], self._outbox())
        ecrits, _ = self._refuses(("new", "x"), seuil=10**6)
        (x,) = [tid for tid in self._ids_du_board() if tid not in crees]
        e2, _ = self._refuses(("purge",), seuil=3)
        self.assertEqual(4, len(e2), "w du purge")
        self.assertEqual(3, len(self._outbox()))
        self.assertEqual(ecrits + e2, self._deverses() + self._outbox())
        self._relever(ecrits + e2)
        self.assertEqual({tid: 1 for tid in crees}, {k: v for k, v in self._v3()[1].items() if k != x})

    def test_D4_tete_sous_bail_vivant_rien_n_est_deverse(self) -> None:
        self._refuses(*[("new", f"t{i}") for i in range(3)], seuil=10**6)
        data = self._board()
        data["sync_outbox"][0]["lease"] = {"owner": "autre", "token": "j", "expires_at": 4102444800.0}
        self.board.write_text(json.dumps(data), encoding="utf-8")
        _, err = self._refuses(("new", "t3"), seuil=2)
        self.assertEqual(4, len(self._outbox()))
        self.assertEqual([], self._deverses())
        self.assertEqual([], self._lignes(err, "AU SEUIL"))

    def test_D4b_tete_sous_bail_expire_est_deversee(self) -> None:
        """Un bail EXPIRÉ ne protège plus la tête : le déversement a lieu (un seul `claim` peut le reprendre, `attempt`
        monte au rejeu). Mutant : `bail is not None` seul -> la tête expirée bloque encore."""
        self._refuses(*[("new", f"t{i}") for i in range(3)], seuil=10**6)
        data = self._board()
        data["sync_outbox"][0]["lease"] = {"owner": "autre", "token": "j", "expires_at": 1.0}
        self.board.write_text(json.dumps(data), encoding="utf-8")
        ecrits = self._outbox()
        e, err = self._refuses(("new", "t3"), seuil=2)
        ecrits += e
        self.assertEqual(2, len(self._outbox()))
        self.assertEqual(ecrits[:2], self._deverses())
        self.assertEqual(1, len(self._lignes(err, "AU SEUIL")))
        self._relever(ecrits)

    def test_D5_ajout_en_echec_le_board_garde_tout_et_le_doublon_n_est_pas_reinjecte(self) -> None:
        """`fsync` qui lève : le board n'est PAS réécrit (l'ajout précède le `save`) ; le fichier peut garder les lignes
        écrites, ce doublon est écarté au rejeu et V3 reçoit chaque intent une fois."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=10**6)
        with self._disque_plein_au_deverse():
            e, err = self._refuses(("new", "t4"), seuil=3)
        ecrits += e
        self.assertEqual(ecrits, self._outbox(), "le board a perdu des intents")
        self.assertEqual(1, len(self._lignes(err, "déversement IMPOSSIBLE, intents gardés au board")))
        self.assertEqual(1, self._raisons().count("sync-outbox-deverse-impossible"), "échec de déversement sans signal distinct")
        self.assertEqual(ecrits[:2], self._deverses(), "le doublon attendu n'est pas là : le banc ne mesure rien")
        tasks._reinjecter_deverses(str(self.root))
        self.assertEqual(ecrits, self._outbox(), "doublon réinjecté ou ordre rompu")
        self._relever(ecrits)

    def test_D6_intent_deverse_sans_correlation_est_ecarte_et_le_board_reste_lisible(self) -> None:
        """Board remis à un état sans la corrélation d'un intent déversé (p. ex. TASKS.json restauré depuis git) : le
        rejeu l'ÉCARTE, le dit, et le board se relit ; la ligne reste dans la trace `.rejoue-*`."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        data = self._board()
        orphelin = self._deverses()[0]
        del data["sync_correlations"][orphelin]
        self.board.write_text(json.dumps(data), encoding="utf-8")
        fichier = self.fichier
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            tasks._reinjecter_deverses(str(self.root))
        self.assertEqual(1, len(self._lignes(err.getvalue(), "1 intent(s) déversé(s) réinjecté(s) en tête, 1 écarté(s)")))
        tasks.load(str(self.root))
        self.assertEqual([o for o in ecrits if o != orphelin], self._outbox())
        trace = next(fichier.parent.glob(fichier.name + ".rejoue-*")).read_text(encoding="utf-8")
        self.assertIn(orphelin, trace)

    def test_D7_segment_final_interrompu_ignore_a_la_lecture_tronque_avant_l_ajout_suivant(self) -> None:
        self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        with open(self.fichier, "ab") as f:
            f.write(b'{"operation_id": "trong')
        self.assertEqual(1, len(self._deverses()))
        self._refuses(("new", "t4"), seuil=3)
        brut = self.fichier.read_bytes()
        self.assertTrue(brut.endswith(b"\n"))
        self.assertEqual(2, len([json.loads(l) for l in brut.split(b"\n")[:-1]]))

    def test_D8_fichier_illisible_rien_n_est_draine_replay_sync_rend_1_et_la_croissance_est_dite(self) -> None:
        """Ligne TERMINÉE illisible : `replay-sync` EXPLICITE rend 1 (rien n'est rejoué = échec, comme un refus de
        construction), un événement `sync-outbox-rejeu-impossible` part, l'outbox et le fichier sont intacts ; un verbe
        mutant n'est pas gelé, mais chacun de ses DEUX drains annonce (deux lignes, deux événements) et l'outbox
        grossit au-delà du seuil tant que le fichier n'est pas réparé : limite NOMMÉE, jamais bornée ici."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        with open(self.fichier, "ab") as f:
            f.write(b"pas du json\n")
        with self._auteur():
            rc, out, err = self._main("replay-sync")
            self.assertEqual(1, rc, err)
            self.assertNotIn("replayed", out)
            self.assertEqual(1, len(self._lignes(err, "rejeu du déversement IMPOSSIBLE, aucun intent n'est drainé")))
            self.assertEqual(ecrits[1:], self._outbox())
            self.assertTrue(self.fichier.exists())
            self.assertEqual(1, self._raisons().count("sync-outbox-rejeu-impossible"))
            pont = self.board_bridge.BoardBridge(project_root=self.root)
            self.assertFalse(pont._drain_board_backlog())  # sans `pont_commande` : stderr seul, limite nommée
            rc, _out, err = self._main("new", "y")  # le verbe n'est pas gelé : il écrit le board
        self.assertEqual(0, rc, err)
        self.assertEqual(2, len(self._lignes(err, "rejeu du déversement IMPOSSIBLE")), "un drain avant le verbe, un après")
        self.assertEqual(3, self._raisons().count("sync-outbox-rejeu-impossible"))
        self.assertEqual(len(ecrits[1:]) + 1, len(self._outbox()), "l'outbox grossit : aucun déversement sans refus du pont")
        self.assertIn("y", [t["task"] for t in self._board()["tasks"]])

    def test_D8b_ligne_hors_schema_le_rejeu_est_impossible_le_board_reste_lisible_le_fichier_est_garde(self) -> None:
        """Le rejeu valide COMME `load` avant le `save` : une ligne `attempt = -1` rendrait TASKS.json illisible (rc 2 sur
        tous les verbes) ; un `operation_id` non textuel lèverait `TypeError`. Dans les deux cas : `DeverseIllisible`,
        rc 1, le board se relit, ni `save` ni renommage, le fichier est gardé tel quel."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        lignes = self.fichier.read_bytes().split(b"\n")[:-1]
        for nom, abime in (("attempt_negatif", lambda i: i.update(attempt=-1)), ("operation_id_liste", lambda i: i.update(operation_id=["x"]))):
            with self.subTest(nom):
                intents = [json.loads(l) for l in lignes]
                abime(intents[0])
                brut = b"".join(json.dumps(i, sort_keys=True).encode("utf-8") + b"\n" for i in intents)
                self.fichier.write_bytes(brut)
                avant = self._raisons().count("sync-outbox-rejeu-impossible")
                with self._auteur():
                    rc, _out, err = self._main("replay-sync")
                self.assertEqual(1, rc, err)
                self.assertEqual(1, len(self._lignes(err, "rejeu du déversement IMPOSSIBLE")))
                self.assertEqual(avant + 1, self._raisons().count("sync-outbox-rejeu-impossible"))
                tasks.load(str(self.root))  # le board se relit
                self.assertEqual(ecrits[2:], self._outbox())
                self.assertEqual(brut, self.fichier.read_bytes())
                self.assertEqual([], list(self.fichier.parent.glob(self.fichier.name + ".rejoue-*")))

    def test_D9_le_backlog_v3_vers_board_draine_le_deverse_avant_d_accepter(self) -> None:
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        with self._auteur():
            pont = self.board_bridge.BoardBridge(project_root=self.root)
            self.assertTrue(pont._drain_board_backlog())
        self.assertEqual(set(), set(ecrits) - self._v3()[0])

    def test_D10_lien_a_la_place_du_fichier_refuse_sans_rien_perdre(self) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(Path(self.tmp.name) / "ailleurs.jsonl", self.fichier)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        ecrits, err = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        self.assertEqual(ecrits, self._outbox())
        self.assertFalse((Path(self.tmp.name) / "ailleurs.jsonl").exists())
        self.assertEqual(1, len(self._lignes(err, "déversement IMPOSSIBLE")))
        self.assertEqual(1, self._raisons().count("sync-outbox-deverse-impossible"))
        self.assertRaises(tasks.DeverseIllisible, tasks.drain_sync_outbox, str(self.root), lambda i: True)

    def test_D16_renommage_en_echec_rien_n_est_draine_le_verbe_ecrit_le_rejeu_suivant_ecarte_les_doublons(self) -> None:
        """`os.replace` du fichier rejoué qui lève APRÈS le `save` : aucune réservation, `_drain_board_backlog` refuse,
        un verbe écrit quand même le board ; le drain suivant écarte les intents déjà réinjectés, renomme, et V3 est
        complet. Le `os.replace` du `save` du board, lui, n'est pas touché (filtre sur le nom de destination)."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        vrai = os.replace

        def replace(src, dst, *a, **k):
            if ".rejoue-" in str(dst):
                raise OSError("banc : renommage refusé")
            return vrai(src, dst, *a, **k)

        with self._auteur(), mock.patch.object(tasks.os, "replace", side_effect=replace):
            rc, _out, err = self._main("replay-sync")
            self.assertEqual(1, rc, err)  # rien n'est rejoué : échec de la commande explicite
            self.assertEqual(1, len(self._lignes(err, "rejeu du déversement IMPOSSIBLE, aucun intent n'est drainé")))
            self.assertEqual(1, self._raisons().count("sync-outbox-rejeu-impossible"))
            self.assertEqual(ecrits, self._outbox(), "réinjection perdue ou ordre rompu")
            self.assertTrue(self.fichier.exists())
            self.assertFalse(self.board_bridge.BoardBridge(project_root=self.root)._drain_board_backlog())
            rc, _out, err = self._main("new", "y")
        self.assertEqual(0, rc, err)
        self.assertIn("y", [t["task"] for t in self._board()["tasks"]])
        self._relever(ecrits + [i["operation_id"] for i in self._board()["sync_outbox"] if i["operation_id"] not in ecrits])

    def test_D11_vocabulaire_ferme_de_cinq_raisons_et_silence_hors_commande(self) -> None:
        self.assertEqual(
            ("pont-v3-refuse", "pont-v3-panne", "sync-outbox-deverse", "sync-outbox-deverse-impossible",
             "sync-outbox-rejeu-impossible"), tasks._RAISONS_DEGRADATION)
        tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "hors-vocabulaire")
        tasks._signaler_degradation_v3(str(self.root), str(base.REPO), None, "pont-v3-refuse")
        self.assertEqual([], self._raisons())
        for raison in tasks._RAISONS_DEGRADATION:
            tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, raison)
        self.assertEqual(sorted(tasks._RAISONS_DEGRADATION), sorted(self._raisons()))

    def test_D12_seuil_de_production_200_N_refus_successifs_ne_le_depassent_pas(self) -> None:
        """BK-406, critère 3, au seuil de PRODUCTION (200, sans patch) : 205 `new` refusés, le board ne dépasse jamais
        200 ; puis V3 reçoit les 205."""
        self.assertEqual(200, tasks._SYNC_OUTBOX_SEUIL)
        ecrits = []
        for i in range(205):
            e, _ = self._refuses(("new", f"t{i}"), seuil=200)
            ecrits += e
            self.assertLessEqual(len(self._outbox()), 200)
        self.assertEqual(5, len(self._deverses()))
        self._relever(ecrits)

    def test_D13_bornes_n0_0_1_C_moins_1_C_C_plus_1(self) -> None:
        """Seuil 3, un `new` (w = 1) après n0 intents en attente : déversés = max(0, n0 + 1 - 3), board = min(n0 + 1, 3)."""
        for n0 in (0, 1, 2, 3, 4):
            with self.subTest(n0=n0):
                self.setUp()
                avant, _ = self._refuses(*[("new", f"a{i}") for i in range(n0)], seuil=10**6)
                e, err = self._refuses(("new", "x"), seuil=3)
                self.assertEqual(max(0, n0 + 1 - 3), len(self._deverses()))
                self.assertEqual(min(n0 + 1, 3), len(self._outbox()))
                self.assertEqual(avant + e, self._deverses() + self._outbox())
                self.assertEqual(int(n0 + 1 > 3), len(self._lignes(err, "AU SEUIL")))
                self._relever(avant + e)

    def test_D14_readme_phrases_epinglees_et_formes_refusees(self) -> None:
        """Dans le KIT (`retro/` présent, retiré chez l'adoptant par `strip: retro/` de .template-exclude), la section
        EXISTE : son absence est rouge. Hors kit seulement, le témoin saute si l'adoptant a réécrit la section."""
        texte = " ".join((base.REPO / "README.md").read_text(encoding="utf-8").split())
        titre = "### Board ↔ V3 synchronization"
        if titre not in texte:
            if (base.REPO / "retro").is_dir():
                self.fail("section « Board ↔ V3 synchronization » absente du README du KIT")
            self.skipTest("README d'adoptant sans la section Board ↔ V3")
        for phrase in PHRASES_README + (README_117_APRES, README_117B_APRES, README_111_APRES):
            self.assertIn(" ".join(phrase.split()), texte)
        section = texte.split(titre, 1)[1].split(" ---", 1)[0]
        for forme in INTERDITES_README:
            self.assertNotIn(forme, section)

    def test_D15_ni_le_code_ni_ces_temoins_ne_portent_une_forme_de_retrait(self) -> None:
        """Commentaires et chaînes de tasks_sync.py et tasks_deversement.py (tokenize), noms et docstrings de CE module (ast) : aucune forme des
        rév. 1 à 6 (retrait, perte comptée), sauf la constante qui les énumère."""
        import ast

        sources = [base.TASKS_PATH.with_name(n).read_text(encoding="utf-8") for n in ("tasks_sync.py", "tasks_deversement.py")]
        jetons = [t.string for s in sources for t in tokenize.generate_tokens(io.StringIO(s).readline) if t.type in (tokenize.COMMENT, tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1))]
        arbre = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        textes = [n.name for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)]
        textes += [ast.get_docstring(n) or "" for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module))]
        for forme in INTERDITES_CODE:
            self.assertEqual([], [t for t in jetons + textes if forme in t])


    def test_D17_deux_deversements_dont_un_fsync_en_echec_les_doublons_du_fichier_sont_ecartes_au_rejeu(self) -> None:
        """Intents de NON-création (`retitle`) : le premier déversement échoue à `fsync` (lignes écrites, board intact),
        le second réussit : le fichier porte des doublons DE LUI-MÊME. Sans `vus.add`, le rejeu réinjecte deux fois le
        même `operation_id` : le premier acquitté EFFACE sa corrélation, le second n'en a plus et le board devient
        illisible. La ligne AU SEUIL compte les intents DISTINCTS en attente (3), pas les lignes du fichier (5)."""
        with self._auteur():
            for titre in ("a", "b", "c"):
                self.assertEqual(0, self._main("new", titre)[0])
        a, b, c = self._ids_du_board()
        ecrits, _ = self._refuses(("retitle", a, "x1"), ("retitle", a, "x2"),
                                  ("retitle", b, "y1"), ("retitle", b, "y2"), seuil=10**6)
        with self._disque_plein_au_deverse():
            e, _ = self._refuses(("retitle", c, "z1"), seuil=3)
        ecrits += e
        self.assertEqual(ecrits, self._outbox(), "le board a perdu des intents")
        self.assertEqual(ecrits[:2], self._deverses(), "le premier déversement n'a pas laissé ses lignes : le banc ne mesure rien")
        e, err = self._refuses(("retitle", c, "z2"), seuil=3)
        ecrits += e
        self.assertEqual(ecrits[:2] + ecrits[:3], self._deverses(), "doublons de fichier attendus")
        self.assertEqual(1, len(self._lignes(err, "AU SEUIL (3) — 3 intent(s) déversé(s) hors du board vers")))
        self.assertEqual(1, len(self._lignes(err, ", 3 en attente d'un pont, 3 au board")))
        err = self._relever(ecrits)
        self.assertEqual(1, len(self._lignes(err, "3 intent(s) déversé(s) réinjecté(s) en tête, 2 écarté(s)")))

    def test_D18_l_interface_de_deversement_est_appelable_hors_du_refus_avec_un_chemin_fourni(self) -> None:
        """S-00003330 : `_deverser_excedent(root, chemin=…)` SANS pont ni mémo : le tuple (déversés, distincts en attente,
        restants), la ligne AU SEUIL, le fichier FOURNI (jamais le défaut), aucun événement ; `signaler` reçoit la raison."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=10**6)
        chemin = Path(self.tmp.name) / "ailleurs" / "deverse.jsonl"
        recus: list[str] = []
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            with self._seuil(4):
                premier = tasks._deverser_excedent(str(self.root), chemin=chemin, signaler=recus.append)
            with self._seuil(2):
                second = tasks._deverser_excedent(str(self.root), chemin=chemin)
                rien = tasks._deverser_excedent(str(self.root), chemin=chemin)
        self.assertEqual((1, 1, 4), premier)
        self.assertEqual((2, 3, 2), second)
        self.assertIsNone(rien)
        self.assertEqual(["sync-outbox-deverse"], recus)
        ids = [json.loads(l)["operation_id"] for l in chemin.read_bytes().split(b"\n")[:-1]]
        self.assertEqual(ecrits[:3], ids)
        self.assertEqual(ecrits[3:], self._outbox())
        self.assertFalse(self.fichier.exists(), "le chemin par défaut n'a pas à être touché")
        lignes = self._lignes(err.getvalue(), "AU SEUIL")
        self.assertEqual(2, len(lignes))
        self.assertIn(str(chemin), lignes[0])
        self.assertEqual([], [r for r in self._raisons() if r.startswith("sync-outbox-")], "aucun événement sans pont")

    def test_D19_l_adresse_du_fichier_suit_le_depot_renomme_copie_ou_sous_un_autre_etat_machine(self) -> None:
        """B-C1 de l'it. 7 : l'adresse FAIT VARIER ce que le plan promet. Cinq `new` refusés (seuil 3), puis le dépôt est
        RENOMMÉ, COPIÉ, ou l'état machine (`CADRE_STATE_DIR`) change ; pont sain, `replay-sync` : V3 reçoit CHAQUE intent
        (5 sur 5) et le fichier est renommé en trace. Mutant : adresse sous `state_project(root)/run` -> V3 en reçoit 3
        (les TROIS cellules, comptées une à une : l'assertion d'adresse statique est le témoin D19c, à part)."""
        for variation in ("renommage", "copie", "autre_etat"):
            with self.subTest(variation):
                self.setUp()
                ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
                self.assertEqual(2, len(self._deverses()))
                if variation == "autre_etat":
                    os.environ["CADRE_STATE_DIR"] = str(Path(self.tmp.name) / "autre_etat")  # restauré par le `setUp` neuf
                else:
                    nouvelle = Path(self.tmp.name) / "depot-bis"
                    if variation == "renommage":
                        os.rename(self.root, nouvelle)
                    else:
                        shutil.copytree(self.root, nouvelle, symlinks=True)
                    self.root = nouvelle
                    self.board = nouvelle / ".agents" / "state" / "board" / "TASKS.json"
                from agentic_v3.db.schema import DEFAULT_DB_PATH

                self.store = DEFAULT_DB_PATH(self.root)
                self._relever(ecrits)
                self.assertEqual(1, len(list(self.fichier.parent.glob(self.fichier.name + ".rejoue-*"))))

    def test_D19c_l_adresse_est_celle_du_dossier_du_verrou_sous_la_racine(self) -> None:
        """Adresse STATIQUE : `.agents/state/local/sync_outbox_deverse.jsonl` sous la racine, à côté de `TASKS.lock`
        (dossier créé par `board_lock`, tenu avant toute écriture du fichier)."""
        self.assertEqual(Path(".agents/state/local/sync_outbox_deverse.jsonl"), self.fichier.relative_to(self.root))
        self.assertEqual(tasks.lock_path(str(self.root)).parent, self.fichier.parent)
        self.assertFalse(self.fichier.parent.exists(), "le dossier ne naît pas avant le premier verrou")
        self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        self.assertTrue(tasks.lock_path(str(self.root)).exists() and self.fichier.exists())

    def test_D19b_le_fichier_est_non_versionne_git_ignore_comme_le_verrou(self) -> None:
        """S-00003315, « un fichier non versionné » : dans un dépôt git jetable portant les DEUX `.gitignore` du kit,
        l'adresse du fichier ET celle de `TASKS.lock` sont ignorées PAR CES RÈGLES (et non par un ignore global).
        Dans le KIT seulement (`retro/` présent) : chez l'adoptant les règles sont les siennes."""
        if not (base.REPO / "retro").is_dir():
            self.skipTest("hors kit : les règles .gitignore sont celles de l'adoptant")
        if shutil.which("git") is None:
            self.skipTest("git absent")
        sources = (base.REPO / ".gitignore", base.REPO / ".agents" / ".gitignore")
        self.assertTrue(all(s.is_file() for s in sources), "les .gitignore du KIT manquent")
        depot = Path(self.tmp.name) / "depot-git"
        (depot / ".agents").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(depot)], check=True, capture_output=True)
        shutil.copy2(sources[0], depot / ".gitignore")
        shutil.copy2(sources[1], depot / ".agents" / ".gitignore")
        for chemin in (self.fichier, tasks.lock_path(str(self.root))):
            relatif = chemin.relative_to(self.root).as_posix()
            r = subprocess.run(["git", "-C", str(depot), "check-ignore", "-v", relatif], capture_output=True, text=True)
            self.assertEqual(0, r.returncode, f"{relatif} n'est pas ignoré")
            self.assertIn(r.stdout.split(":", 1)[0], (".gitignore", ".agents/.gitignore"), r.stdout)

    def test_D20_deux_cycles_deversement_rejeu_laissent_deux_traces_distinctes(self) -> None:
        """Deux cycles complets (déversement, levée du refus, rejeu) : DEUX traces `.rejoue-*` de noms distincts, chacune
        avec SES intents. Mutant : suffixe fixe `.rejoue-0` -> la seconde écrase la première (une trace)."""
        premiers, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        self._relever(premiers)
        seconds, _ = self._refuses(*[("new", f"u{i}") for i in range(5)], seuil=3)
        self._relever(premiers + seconds)
        traces = sorted(self.fichier.parent.glob(self.fichier.name + ".rejoue-*"))
        self.assertEqual(2, len(traces), [t.name for t in traces])
        lues = [[json.loads(l)["operation_id"] for l in t.read_bytes().split(b"\n")[:-1]] for t in traces]
        self.assertEqual(sorted([premiers[:2], seconds[:2]]), sorted(lues))

    def test_D20b_le_renommage_de_la_trace_reessaie_sur_un_PermissionError_transitoire(self) -> None:
        """Windows, L-00000054 : `os.replace` échoue sous un lecteur concurrent. Le renommage de la trace passe par
        `_replace_with_retry` : une première `PermissionError` est reprise, le rejeu aboutit. Mutant : `os.replace` nu."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        vrai, essais = os.replace, []

        def replace(src, dst, *a, **k):
            if ".rejoue-" in str(dst) and not essais:
                essais.append(str(dst))
                raise PermissionError("banc : violation de partage")
            return vrai(src, dst, *a, **k)

        with mock.patch.object(tasks.os, "replace", side_effect=replace):
            self._relever(ecrits)
        self.assertEqual(1, len(essais), "la panne transitoire n'a pas eu lieu : le banc ne mesure rien")
        self.assertEqual(1, len(list(self.fichier.parent.glob(self.fichier.name + ".rejoue-*"))))

    def test_D21_le_fichier_disparu_entre_le_test_et_le_verrou_n_est_pas_un_rejeu_impossible(self) -> None:
        """Deux drains croisés : le test SANS verrou voit le fichier, un autre drain le rejoue et le renomme, le test
        SOUS verrou ne le voit plus. Attendu : 0, pas `DeverseIllisible`. Mutant : second test retiré."""
        with mock.patch.object(tasks.os.path, "lexists", side_effect=[True, False]):
            self.assertEqual(0, tasks._reinjecter_deverses(str(self.root)))

    def test_D22_un_refus_REEL_de_l_emplacement_du_store_emet_pont_v3_refuse_et_non_panne(self) -> None:
        self._poser_lien()  # lien symbolique à l'emplacement du store : EmplacementRefuse, aucun mock du pont
        rc, _o, err = self._main("new", "x")
        self.assertEqual(0, rc, err)
        self.assertEqual(["pont-v3-refuse"], self._raisons())

    def test_D23_racine_etrangere_sans_AGENTS_EVENTS_DIR_aucune_emission_racine_du_depot_une(self) -> None:
        with mock.patch.dict(os.environ):
            os.environ.pop("AGENTS_EVENTS_DIR", None)
            with mock.patch.object(tasks, "_charger_events") as charge:
                tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "pont-v3-refuse")
            charge.assert_not_called()
            with mock.patch.object(tasks, "_charger_events") as charge:
                tasks._signaler_degradation_v3(str(base.REPO), str(base.REPO), {}, "pont-v3-refuse")
            charge.assert_called_once()

    def test_D24_host_ne_vient_que_d_un_hote_connu(self) -> None:
        for valeur, attendu in (("claude", "claude"), ("gemini", "gemini"), ("kimi", None), ("n'importe quoi", None), ("", None)):
            with self.subTest(AGENTS_HOOK_HOST=valeur):
                avant = len(self._hotes())
                with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": valeur}):
                    tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "pont-v3-refuse")
                self.assertEqual(attendu, self._hotes()[avant:][0])


    # -- critique B de clôture de la fournée 2 : témoins des mutants survivants et du verrou tenu au rejeu ---------------
    def test_D25_le_lot_est_dans_le_fichier_avant_le_fsync(self) -> None:
        """`fsync` ne couvre que ce qui a quitté le tampon de Python : à CHAQUE appel, le fichier porte déjà tout le lot.
        Puis, hors Windows, le DOSSIER du fichier est synchronisé (passe de correction de la fournée 2). Mutants :
        `flush()` retiré -> taille 0 à l'appel ; `fsync` du dossier retiré -> aucun dossier synchronisé."""
        self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=10**6)
        vrai, tailles, dossiers = os.fsync, [], []

        def fsync(fd):
            st = os.fstat(fd)
            if not self._du_deverse(fd):  # T-00001058 : les `fsync` de l'écriture O2 du board, hors sujet
                pass
            elif stat.S_ISDIR(st.st_mode):
                dossiers.append((st.st_dev, st.st_ino))
            else:
                tailles.append(st.st_size)
            return vrai(fd)

        with mock.patch.object(tasks.os, "fsync", side_effect=fsync):
            self._refuses(("new", "t4"), seuil=3)
        self.assertEqual([len(self.fichier.read_bytes())], tailles)
        parent = os.stat(self.fichier.parent)
        self.assertEqual([] if os.name == "nt" else [(parent.st_dev, parent.st_ino)], dossiers)

    @unittest.skipIf(os.name == "nt", "droits POSIX")
    def test_D26_le_fichier_de_deversement_est_prive_0600(self) -> None:
        """Les snapshots de tâches déversés ne sont lisibles que de leur propriétaire. Mutant : `0o600` -> `0o666`."""
        self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        self.assertEqual(0o600, stat.S_IMODE(os.stat(self.fichier).st_mode))

    def test_D27_une_ligne_illisible_deja_au_fichier_ne_fait_pas_lever_l_ajout_et_compte_pour_une_entree(self) -> None:
        """Ligne TERMINÉE illisible déjà présente quand un déversement s'y ajoute : l'ajout aboutit (rc 0), l'illisible compte
        pour UNE entrée en attente (1 intent + 1 illisible + 1 neuf = 3). Mutant : `distincts.add(ligne)` -> `raise`."""
        self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        with open(self.fichier, "ab") as f:
            f.write(b"pas du json\n")
        with self._refus(), self._seuil(3):  # `_refuses` relirait le fichier par `_deverses`, qui ne sait pas l'illisible
            rc, _out, err = self._main("new", "t4")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, ", 3 en attente d'un pont, 3 au board")))

    def test_D28_segment_final_interrompu_n_est_pas_rejoue_ni_ne_rend_le_fichier_illisible(self) -> None:
        """À la LECTURE aussi, le segment final non terminé est ignoré (et gardé dans la trace). Mutant : segment final PARSÉ
        -> `DeverseIllisible`."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        fichier = self.fichier
        with open(fichier, "ab") as f:
            f.write(b'{"operation_id": "trong')
        self.assertEqual(1, tasks._reinjecter_deverses(str(self.root)))
        self.assertEqual(ecrits, self._outbox())
        trace = next(fichier.parent.glob(fichier.name + ".rejoue-*")).read_bytes()
        self.assertTrue(trace.endswith(b'"trong'))

    def test_D29_un_lien_vers_un_fichier_valide_n_est_pas_suivi_a_la_lecture(self) -> None:
        """D10 couvre l'ÉCRITURE (lien vers un fichier absent) ; ici la LECTURE, lien vers un fichier VALIDE : refusé, rien
        n'est réinjecté à travers lui. Mutant : `open(chemin, "rb")` sans `opener`."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        ailleurs = Path(self.tmp.name) / "ailleurs-valide.jsonl"
        os.replace(self.fichier, ailleurs)
        try:
            os.symlink(ailleurs, self.fichier)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        self.assertRaises(tasks.DeverseIllisible, tasks.drain_sync_outbox, str(self.root), lambda i: True)
        self.assertEqual(ecrits[1:], self._outbox())
        self.assertTrue(ailleurs.exists())

    def test_D30_chaque_hote_connu_est_porte_par_l_evenement(self) -> None:
        """D24 ne tient que `claude` et `gemini` : `codex` et `copilot` le sont ici. Mutant : tuple réduit."""
        for hote in ("claude", "codex", "copilot", "gemini"):
            with self.subTest(hote):
                avant = len(self._hotes())
                with mock.patch.dict(os.environ, {"AGENTS_HOOK_HOST": hote}):
                    tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "pont-v3-refuse")
                self.assertEqual(hote, self._hotes()[avant:][0])

    def test_D31_charger_events_enregistre_le_module_avant_de_l_executer_et_le_retire_s_il_leve(self) -> None:
        """Contrat d'import d'`events.py` (L-00000142) : `sys.modules[spec.name]` posé AVANT `exec_module`, retiré sur levée.
        Mutant : enregistrement retiré -> `KeyError` dans le module."""
        depot = Path(self.tmp.name) / "faux-depot"
        (depot / ".agents" / "bin").mkdir(parents=True)
        events = depot / ".agents" / "bin" / "events.py"
        events.write_text("import sys\nENREGISTRE = sys.modules[__name__] is not None\n", encoding="utf-8")
        self.assertTrue(tasks._charger_events(depot).ENREGISTRE)
        events.write_text("raise RuntimeError('banc')\n", encoding="utf-8")
        self.assertRaises(RuntimeError, tasks._charger_events, depot)
        self.assertNotIn("_events_tasks_sync", sys.modules)

    @unittest.skipIf(os.name == "nt", "flock POSIX : la poignée est tenue par le banc")
    def test_D32_un_verrou_tenu_au_rejeu_garde_son_message_et_n_est_pas_un_fichier_illisible(self) -> None:
        """Le verrou du board qui expire (5 s en production) pendant le rejeu est un `BoardError` : rc 2 et SON message, comme
        avant T-00001006 ; ni la ligne « rejeu du déversement IMPOSSIBLE » ni l'événement `sync-outbox-rejeu-impossible`
        (le fichier est intact, rien ne dit qu'il est illisible). Mutant : `except (BoardError, OSError)` -> rc 1."""
        import fcntl

        self._refuses(*[("new", f"t{i}") for i in range(5)], seuil=3)
        fd = os.open(tasks.lock_path(str(self.root)), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self._auteur(), mock.patch.object(tasks, "_LOCK_TIMEOUT_SECONDS", 0.2):
                rc, _out, err = self._main("replay-sync")
        finally:
            os.close(fd)
        self.assertEqual(2, rc, err)
        self.assertIn("timed out waiting for board lock", err)
        self.assertEqual([], self._lignes(err, "rejeu du déversement IMPOSSIBLE"))
        self.assertEqual(0, self._raisons().count("sync-outbox-rejeu-impossible"))
        self.assertTrue(self.fichier.exists())

    def test_D33_l_emission_est_fail_open_quelle_que_soit_la_panne(self) -> None:
        """`events.emit` est fail-open : un chargeur qui lève, ou un `emit` qui lève, ne remonte JAMAIS au verbe.
        Mutant : `except Exception` réduit à `except OSError`."""
        pannes = (RuntimeError("banc : events.py cassé"), ImportError("banc"), KeyError("banc"), OSError("banc"))
        for panne in pannes:
            with self.subTest(chargeur=type(panne).__name__):
                with mock.patch.object(tasks, "_charger_events", side_effect=panne):
                    self.assertIsNone(tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "pont-v3-refuse"))
        for panne in pannes:
            with self.subTest(emit=type(panne).__name__):
                faux = mock.Mock(emit=mock.Mock(side_effect=panne))
                with mock.patch.object(tasks, "_charger_events", return_value=faux):
                    self.assertIsNone(tasks._signaler_degradation_v3(str(self.root), str(base.REPO), {}, "pont-v3-refuse"))

    # -- passe de correction de la fournée 2 (S-00003628, remède A) : FIFO face à un déversement concurrent ------------
    def test_D20_un_deversement_pendant_un_drain_vivant_ne_depasse_rien(self) -> None:
        """Un processus P, pont refusé, déverse ENTRE l'ACK de W et son claim suivant : W s'arrête (fichier présent, outbox
        non vide), le drain suivant rejoue le fichier d'abord ; V3 reçoit [0..5] dans l'ordre d'écriture, sans échec.
        Mutant : garde `lexists` de `claim_sync_event` retirée -> [0, 3, 4, 5, 1, 2], création de `a` non projetée.
        L'id de `a` est relu au board entre deux lots (seuil hors d'atteinte : rien n'est déversé, l'ordre d'écriture
        des six intents est celui d'un seul lot), jamais prédit (T-00000726, R-BANCS (i))."""
        ecrits, _ = self._refuses(("new", "x0"), ("new", "a"), ("new", "b"), seuil=10**6)
        a = self._ids_du_board()[1]
        suite, _ = self._refuses(("retitle", a, "a2"), ("new", "c"), ("new", "d"), seuil=10**6)
        ecrits += suite
        vrai, appels = tasks.claim_sync_event, []

        def claim(root, owner, **kw):
            appels.append(owner)
            if len(appels) == 2:  # P, entre l'ACK de x0 et le claim suivant de W
                with self._seuil(3):
                    self.assertEqual((2, 2, 3), tasks._deverser_excedent(root), "P n'a rien déversé : le banc ne mesure rien")
            return vrai(root, owner, **kw)

        with self._auteur():
            with mock.patch.object(tasks, "claim_sync_event", claim), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(1, tasks.replay_sync(str(self.root)))
            self.assertTrue(self.fichier.exists(), "le déversement de P a disparu pendant le drain de W")
            self.assertEqual(ecrits[3:], self._outbox(), "W a dépassé le déversement de P")
        self._relever(ecrits)
        c = sqlite3.connect(str(self.store))
        try:
            ordre = [r[0] for r in c.execute("SELECT operation_id FROM board_sync_inbox ORDER BY rowid")]
        finally:
            c.close()
        self.assertEqual(list(range(6)), [ecrits.index(o) for o in ordre])

    def test_D34_un_drain_sur_un_deversement_illisible_leve_sans_reserver_ni_livrer(self) -> None:
        """Le rejeu ôte le fichier (renommé : `_relever`) ou LÈVE, jamais ni l'un ni l'autre. Ligne illisible : le drain lève
        `DeverseIllisible` AVANT toute réservation (aucun claim, aucune livraison, outbox et fichier intacts) ; il ne boucle
        pas et ne rend pas 0. Côté CLI : `replay-sync` rend 1, un verbe 0 (D8) ; rc 2 est le verrou expiré (D32)."""
        ecrits, _ = self._refuses(*[("new", f"t{i}") for i in range(4)], seuil=3)
        with open(self.fichier, "ab") as f:
            f.write(b"pas du json\n")
        brut, claims, livres, vrai = self.fichier.read_bytes(), [], [], tasks.claim_sync_event
        with mock.patch.object(tasks, "claim_sync_event", lambda *a, **k: claims.append(a) or vrai(*a, **k)), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertRaises(tasks.DeverseIllisible, tasks.drain_sync_outbox, str(self.root), livres.append)
        self.assertEqual(([], []), (claims, livres))
        self.assertEqual(ecrits[1:], self._outbox())
        self.assertEqual(brut, self.fichier.read_bytes())

    def test_D35_le_backlog_n_est_pas_draine_tant_que_le_fichier_de_deversement_existe(self) -> None:
        """Défense en profondeur côté pont : W draine tout, PUIS une commande refusée de P déverse avant que W relise le
        backlog ; board vide, fichier présent -> commande V3 refusée. Un `tasks.py` sans `_chemin_deverse` (antérieur
        au déversement) n'est pas refusé pour autant. Mutant : test du fichier retiré de `_drain_board_backlog` -> True."""
        with self._auteur():
            pont = self.board_bridge.BoardBridge(project_root=self.root)
        module, appels = pont._tasks_module(), []  # le pont charge SON `tasks` (pas `base.tasks`) : patcher celui-là
        vrai = module.drain_sync_outbox

        def drain(*a, **k):
            appels.append(vrai(*a, **k))
            self._refuses(("new", "tardif"), seuil=0)  # P, pont refusé : son unique intent part dans le fichier
            return appels[-1]

        with self._auteur(), mock.patch.object(module, "drain_sync_outbox", drain):
            self.assertFalse(pont._drain_board_backlog())
        self.assertEqual(([0], [], 1), (appels, self._outbox(), len(self._deverses())), "le banc ne mesure rien")
        with mock.patch.object(module, "drain_sync_outbox", lambda *a, **k: 0), mock.patch.object(module, "_chemin_deverse", None):
            self.assertTrue(pont._drain_board_backlog())


if __name__ == "__main__":
    unittest.main()
