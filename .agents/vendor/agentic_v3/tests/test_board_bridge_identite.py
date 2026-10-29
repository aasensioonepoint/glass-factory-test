"""Banc FRÈRE de `test_board_bridge.py` (T-00001060, écart E1 du plan : le banc
d'origine est au plafond de longueur, tout nouveau témoin vient ici).

CE QUE CE BANC TIENT. L'identité board d'une création V3 est posée en MACHINE
(`board_identity_reservations.board_task_id`) AVANT l'écriture TEXTE
(`TASKS.json`) — K1, décision pilote S-00003347 ; la fenêtre inverse (id réservé,
tâche absente du texte) se reprend sans `BoardError` ; une suppression EN VOL
(intent `after=None` dans l'outbox ou dans le fichier de déversement) se lit
`TOMBSTONED`, donc une création autorisée y rend `NR`. Une reprise K1 dont l'id réservé
porte DÉJÀ un lien machine (verbe humain drainé : `BOARD:<op>` ; suppression drainée :
lien tombé ; anomalie : identité non `BOARD:`) est ABANDONNÉE — commande acquittée,
trace `abandon` dans l'ACK, la file derrière livrée (décision pilote
S-01M4KHNE8597YSZ4YY54YVWFDZ, option b ; lecture S-01M4PR7RE7EQ940STQ6V6WRCX4).

INJECTION SITUÉE PAR L'ÉTAT, jamais par un compte d'appels : `tasks.save` du
module que charge le pont est enveloppé ; la sonde lit le `TASKS.json` sur disque
et la ligne de `board_identity_reservations`, et le crash est une sous-classe de
`BaseException` (il échappe aux `except Exception`, comme une mort de processus).
Chaque témoin ASSERTE que son injection a tiré. Aucun parcours d'arbre ici
(`test_repo_walk_census.py`).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Optional
from unittest import mock

import pytest

from agentic_v3.db.schema import get_db_connection
from agentic_v3.models.events import EventType


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """Recopie de `test_board_bridge.py::_isolation_export_run` (réserve C1) : l'export
    sous une racine de TEST (`CADRE_PROJECT_ROOT`), la base machine sous
    `CADRE_STATE_DIR`, l'auteur fixé par la porte UNIQUE
    `conftest.greffe_email_git_franchissable` (franchissable, L-00000500)."""
    from conftest import greffe_email_git_franchissable
    from agentic_v3.db import run_export

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)


class _Crash(BaseException):
    """Une mort de processus : traverse les `except Exception` du pont et du drain."""


V3_ID = "V3-K1"
OP1 = "k1-create-op1"
OP2 = "k1-create-op2"
OP3 = "k1-autre-op3"
OP4 = "k1-create-op4"
DECISION_ABANDON = "S-01M4KHNE8597YSZ4YY54YVWFDZ"


_LECTEUR: list[Any] = []


def _tasks_lecteur() -> Any:
    """Le `tasks.py` du dépôt, chargé UNE fois par chemin, pour LIRE la vue de l'outbox (T-00001058)."""
    if not _LECTEUR:
        import importlib.util
        import sys

        chemin = ROOT / ".agents" / "bin" / "tasks.py"
        spec = importlib.util.spec_from_file_location("tasks_identite_lecteur", chemin)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _LECTEUR.append(module)
    return _LECTEUR[0]


class _Banc(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "v3.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def bridge(self) -> Any:
        """Une instance NEUVE (module `tasks` rechargé), comme une reprise de processus."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        return BoardBridge(self.db_path, self.root)

    @staticmethod
    def payload(board_task_id: str = "T-AUTHORIZED-CREATE", title: str = "K1") -> dict[str, Any]:
        return {
            "board_task_id": board_task_id,
            "status": "PENDING",
            "create_authorized": True,
            "create_title": title,
            "create_owner": "dev-multi",
            "v3_task_id": V3_ID,
        }

    def disque(self) -> dict[str, Any]:
        """TASKS.json BRUT, son `sync_outbox` lue par la VUE (T-00001058, O2 : un fichier par intent) — par un
        `tasks.py` chargé à part, `load` seul (aucun verrou, aucun pont construit pour lire). En forme DOSSIER
        (T-00001009), `load` du même lecteur : les enregistrements, leur projection et la vue de l'outbox."""
        chemin = self.root / ".agents" / "state" / "board" / "TASKS.json"
        lecteur = _tasks_lecteur()
        if not chemin.exists():
            if getattr(lecteur, "store_form", None) is not None and lecteur.store_form(self.root) == "dossier":
                data = lecteur.load(self.root)
                return {cle: data[cle] for cle in ("tasks", "sync_correlations", "sync_outbox")}
            return {"tasks": [], "sync_correlations": {}, "sync_outbox": []}
        return {**json.loads(chemin.read_text(encoding="utf-8")), "sync_outbox": lecteur.load(self.root)["sync_outbox"]}

    def ids_disque(self) -> list[str]:
        return [task["id"] for task in self.disque().get("tasks", [])]

    def reservation(self, v3_task_id: str = V3_ID) -> Optional[dict[str, Any]]:
        with closing(get_db_connection(self.db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM board_identity_reservations WHERE v3_task_id=?",
                (v3_task_id,),
            ).fetchone()
        return dict(row) if row else None

    def crash_sur_save(
        self, tasks: Any, sonde: Callable[[], bool], *, apres: bool
    ) -> tuple[Any, dict[str, Any]]:
        """Enveloppe `tasks.save` : la sonde est lue AVANT (`apres=False`) ou APRÈS le
        vrai `save` ; elle tire UNE fois, note la réservation et le disque, puis crashe."""
        vrai_save = tasks.save
        tir: dict[str, Any] = {"tire": False}

        def enveloppe(root: Any, data: dict[str, Any]) -> None:
            if not apres and not tir["tire"] and sonde():
                tir.update(tire=True, reservation=self.reservation(), ids=self.ids_disque())
                raise _Crash("mort avant save")
            vrai_save(root, data)
            if apres and not tir["tire"] and sonde():
                tir.update(tire=True, reservation=self.reservation(), ids=self.ids_disque())
                raise _Crash("mort après save")

        return mock.patch.object(tasks, "save", enveloppe), tir

    def sonde_k1(self) -> bool:
        """APRÈS save : tâche en texte, réservation NON finalisée."""
        reservation = self.reservation()
        return reservation is not None and reservation["finalized_at"] is None and bool(self.ids_disque())

    def sonde_inverse(self) -> bool:
        """AVANT save : réservation porteuse d'un id, non finalisée, tâche ABSENTE du disque."""
        reservation = self.reservation()
        return (
            reservation is not None
            and reservation["board_task_id"] is not None
            and reservation["finalized_at"] is None
            and reservation["board_task_id"] not in self.ids_disque()
        )

    def crash_k1(self, *, sonde: Callable[[], bool], apres: bool) -> dict[str, Any]:
        bridge = self.bridge()
        patch, tir = self.crash_sur_save(bridge._tasks_module(), sonde, apres=apres)
        with patch:
            try:
                bridge.reconcile_v3_to_board(operation_id=OP1, **self.payload())
            except _Crash:
                pass
        self.assertTrue(tir["tire"], "l'injection n'a pas tiré : l'état sondé n'a jamais été atteint")
        return tir

    def vue_sans_cle(self, board_task_id: str) -> Any:
        """La clé texte de `board_task_id` retirée de la VUE du pont (`_board_data`) ; le
        magasin reste VALIDE (retirée du FICHIER, l'outbox deviendrait illisible : M-VOL)."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        vraie_vue = BoardBridge._board_data

        def vue(pont: Any) -> dict[str, Any]:
            data = vraie_vue(pont)
            data["sync_correlations"] = {
                cle: valeur
                for cle, valeur in data.get("sync_correlations", {}).items()
                if valeur.get("board_task_id") != board_task_id
            }
            return data

        return mock.patch.object(BoardBridge, "_board_data", vue)

    @staticmethod
    def espion_actions() -> tuple[Any, list[str]]:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        vraie = BoardBridge._reconcile_v3_to_board_locked
        actions: list[str] = []

        def espion(pont: Any, **options: Any) -> str:
            action = vraie(pont, **options)
            actions.append(action)
            return action

        return mock.patch.object(BoardBridge, "_reconcile_v3_to_board_locked", espion), actions


class IdentiteReserveeTests(_Banc):
    def test_W1_k1_l_id_reserve_en_machine_porte_la_reprise_sans_la_cle_creatrice(self) -> None:
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        vu = tir["ids"]
        self.assertEqual(1, len(vu), vu)
        tasks = self.bridge()._tasks_module()
        with tasks.board_lock(self.root):
            data = tasks.load(self.root)
            del data["sync_correlations"][OP1]  # retrait de la clé créatrice
            tasks.save(self.root, data)

        reprise = self.bridge()
        self.assertEqual("CREATE", reprise.reconcile_v3_to_board(operation_id=OP2, **self.payload()))

        self.assertEqual(vu, self.ids_disque(), "une seule tâche, celle vue à l'injection (M-K1 : 2 avant)")
        self.assertEqual(vu[0], tir["reservation"]["board_task_id"], "id réservé en machine AVANT le texte")
        lien = reprise.event_store.get_board_link(vu[0])
        self.assertEqual((V3_ID, OP1, 0), (lien["v3_task_id"], lien["create_operation_id"], lien["tombstoned"]))
        self.assertIsNotNone(self.reservation()["finalized_at"])

    def test_W2_fenetre_inverse_reprend_sous_l_id_reserve_sans_board_error(self) -> None:
        tir = self.crash_k1(sonde=self.sonde_inverse, apres=False)
        reserve = tir["reservation"]["board_task_id"]
        self.assertEqual([], tir["ids"])

        reprise = self.bridge()
        self.assertEqual("CREATE", reprise.reconcile_v3_to_board(operation_id=OP2, **self.payload()))

        self.assertEqual([reserve], self.ids_disque())
        self.assertEqual(OP1, reprise.event_store.get_board_link(reserve)["create_operation_id"])

    def test_W3_une_tache_intercalee_n_est_jamais_creditee(self) -> None:
        tir = self.crash_k1(sonde=self.sonde_inverse, apres=False)
        reserve = tir["reservation"]["board_task_id"]
        tasks = self.bridge()._tasks_module()
        intercalee = tasks.new_task(str(self.root), "intercalée", "dev-multi").split()[1]

        reprise = self.bridge()
        self.assertEqual("CREATE", reprise.reconcile_v3_to_board(operation_id=OP2, **self.payload()))

        self.assertTrue(tasks.is_ulid_id(reserve), reserve)
        self.assertNotEqual(reserve, intercalee)
        self.assertEqual(sorted([reserve, intercalee]), sorted(self.ids_disque()))
        correlations = self.disque()["sync_correlations"]
        for operation_id in (OP1, OP2):
            self.assertEqual({"board_task_id": reserve, "tombstoned": False}, correlations[operation_id])
        lien = reprise.event_store.get_board_link(intercalee)
        self.assertTrue(lien is None or lien["v3_task_id"] != V3_ID, lien)
        self.assertEqual(V3_ID, reprise.event_store.get_board_link(reserve)["v3_task_id"])

    def test_W5_k1_puis_suppression_avant_reprise_jamais_recree(self) -> None:
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        cree = tir["ids"][0]
        tasks = self.bridge()._tasks_module()
        tasks.delete_task(str(self.root), cree)

        reprise = self.bridge()
        reprise.event_store.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        self.assertEqual(0, reprise.drain_board_commands())

        self.assertNotIn(cree, self.ids_disque())
        self.assertEqual([], self.ids_disque())
        # C7 : le refus est une LEVÉE — commande relâchée, FAILED tracé, tête de FIFO.
        self.assertFalse(reprise.event_store.is_board_command_acked(OP2))
        self.assertEqual([OP2], [c["operation_id"] for c in reprise.event_store.pending_board_commands()])
        dernier = reprise.event_store.get_task_events("T-AUTHORIZED-CREATE")[-1]
        self.assertEqual("BOARD_COMMAND_FAILED", dernier["event_type"])
        self.assertIn("refusing resurrection", json.dumps(dernier, ensure_ascii=False))

    def k1_puis_verbe_humain(self, *, retirer_cle: bool = True) -> tuple[str, dict[str, Any]]:
        """K1, puis un verbe humain sur X drainé Board → V3 : le réducteur pose `BOARD:<op>`
        sur X. `retirer_cle` : variante W1 (clé créatrice OP1 retirée du texte)."""
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        cree = tir["ids"][0]
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tasks.block_task(str(self.root), cree, "note humaine")
        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        lien = bridge.event_store.get_board_link(cree)
        self.assertTrue(lien["v3_task_id"].startswith("BOARD:"), lien)
        if retirer_cle:
            with tasks.board_lock(self.root):
                data = tasks.load(self.root)
                del data["sync_correlations"][OP1]  # variante W1
                tasks.save(self.root, data)
        return cree, lien

    @staticmethod
    def abandon_attendu(cree: str, lien: dict[str, Any]) -> dict[str, Any]:
        return {
            "decision": DECISION_ABANDON,
            "v3_task_id": V3_ID,
            "board_task_id": cree,
            "creator_operation_id": OP1,
            "lien_v3_task_id": lien["v3_task_id"],
            "lien_create_operation_id": lien["create_operation_id"],
        }

    @staticmethod
    def dernier_evenement(es: Any, task_id: str = "T-AUTHORIZED-CREATE") -> tuple[str, str, dict[str, Any]]:
        dernier = es.get_task_events(task_id)[-1]
        return dernier["event_type"], dernier["operation_id"], json.loads(dernier["payload_json"])

    def tache_disque(self, board_task_id: str) -> tuple[str, Optional[str]]:
        tache = next(t for t in self.disque()["tasks"] if t["id"] == board_task_id)
        return tache["state"], tache.get("stage")

    def reservation_ouverte(self) -> tuple[Optional[str], Optional[str]]:
        reservation = self.reservation()
        return reservation["board_task_id"], reservation["finalized_at"]

    def test_W5c_k1_puis_verbe_humain_avant_reprise_abandonne_et_nomme(self) -> None:
        """Revue de clôture T-00001060 (trouvaille 1), puis décision pilote
        S-01M4KHNE8597YSZ4YY54YVWFDZ (option b) : dans la fenêtre K1, un verbe humain sur X
        draine le sens Board → V3 et le réducteur pose `BOARD:<op>` sur X. La reprise
        ABANDONNE AVANT `create_linked_task` (variante W1 : OP1 n'est pas réécrit au texte) :
        commande ACQUITTÉE, trace `abandon` ENTIÈRE dans l'ACK, X à l'humain, réservation NON
        finalisée. Le contrat d'avant (poison : FAILED en tête de FIFO) est AMENDÉ par la
        décision, jamais « ajusté ». MUTANTS : MA (aucun abandon au drain) ; MD, ME (trace
        amputée) ; MI2 (`create_linked_task` juste avant la levée : OP1 → X au texte)."""
        cree, lien = self.k1_puis_verbe_humain()
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        self.assertEqual(1, reprise.drain_board_commands())

        self.assertTrue(es.is_board_command_acked(OP2))
        self.assertEqual([], es.pending_board_commands())
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP2), (type_, operation))
        self.assertEqual(self.abandon_attendu(cree, lien), charge["abandon"])
        self.assertEqual([cree], self.ids_disque())
        self.assertEqual(("blocked", "note humaine"), self.tache_disque(cree))
        correlations = self.disque()["sync_correlations"]
        self.assertNotIn(OP1, correlations, "rien d'écrit au texte avant l'abandon")
        self.assertNotIn(OP2, correlations)
        self.assertEqual(lien, es.get_board_link(cree), "le lien BOARD: reste intact")
        self.assertEqual((cree, None), self.reservation_ouverte())

    def test_W5d_la_file_se_debloque_et_le_rejeu_reste_abandonne(self) -> None:
        """Le poison retenait TOUTE la file (M1 : `drains=(0,0)`). Derrière la création
        abandonnée : OP3, commande ÉTRANGÈRE qui BLOQUE `autre`, puis OP4, rejeu de création
        de la même identité V3. UN drain livre les trois : `autre` bloquée par le pont, OP4
        ré-abandonné, jamais une seconde tâche. MUTANTS : MB (`break` après l'ACK
        d'abandon) ; MJ (acquitter sans appliquer : `autre` resterait `pending`)."""
        cree, lien = self.k1_puis_verbe_humain(retirer_cle=False)
        autre = self.bridge()._tasks_module().new_task(str(self.root), "autre", "dev-multi").split()[1]
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        es.enqueue_board_command(OP3, EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": autre, "status": "BLOCKED"})
        es.enqueue_board_command(OP4, EventType.BOARD_COMMAND_REQUESTED, self.payload(title="K1 bis"))
        self.assertEqual(3, reprise.drain_board_commands())

        self.assertEqual([], es.pending_board_commands())
        self.assertEqual([cree, autre], self.ids_disque())
        self.assertEqual(("blocked", "v3:BLOCKED"), self.tache_disque(autre))
        self.assertEqual(("blocked", "note humaine"), self.tache_disque(cree))
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP4), (type_, operation))
        self.assertEqual(self.abandon_attendu(cree, lien), charge["abandon"])
        self.assertEqual((cree, None), self.reservation_ouverte())

    def test_W5e_l_ack_d_abandon_qui_leve_relache_et_trace_failed(self) -> None:
        """Réserve 3 (S-01M4PR7RB0E2X4N2HCNF55XDKQ) : l'ACK d'abandon passe par le chemin
        COMMUN du drain — s'il lève, la commande est relâchée et FAILED tracé, comme pour
        tout ACK ; jamais une exception qui fuit le drain, bail en vol. MUTANT MG (ACK
        d'abandon dans son propre `except CreationAbandonnee`) : la levée sort du drain."""
        cree, lien = self.k1_puis_verbe_humain()
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        with mock.patch.object(es, "ack_board_command_with_event", side_effect=RuntimeError("ack en panne")) as ack:
            self.assertEqual(0, reprise.drain_board_commands())

        self.assertEqual(1, ack.call_count)
        self.assertEqual(self.abandon_attendu(cree, lien), ack.call_args.args[2]["abandon"])
        self.assertFalse(es.is_board_command_acked(OP2))
        self.assertEqual(
            [(OP2, 1, None)],
            [(c["operation_id"], c["attempt"], c["lease_token"]) for c in es.pending_board_commands()],
            "relâchée : tentative comptée, bail rendu",
        )
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_FAILED", OP2, "ack en panne"), (type_, operation, charge["error"]))
        self.assertEqual([cree], self.ids_disque())

    def test_W5f_l_ack_d_abandon_refuse_arrete_le_drain_sans_compter(self) -> None:
        """Réserve 3 : un ACK d'abandon REFUSÉ (`False`, bail perdu) n'est pas compté et
        arrête le drain, comme tout ACK refusé ; la commande reste à reprendre, OP3 n'est
        pas touchée. MUTANT MF (résultat de l'ACK ignoré) : compté, le drain continue."""
        cree, lien = self.k1_puis_verbe_humain()
        autre = self.bridge()._tasks_module().new_task(str(self.root), "autre", "dev-multi").split()[1]
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        es.enqueue_board_command(OP3, EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": autre, "status": "BLOCKED"})
        with mock.patch.object(es, "ack_board_command_with_event", return_value=False) as ack:
            self.assertEqual(0, reprise.drain_board_commands())

        self.assertEqual(1, ack.call_count)
        self.assertEqual(self.abandon_attendu(cree, lien), ack.call_args.args[2]["abandon"])
        self.assertEqual([OP2, OP3], [c["operation_id"] for c in es.pending_board_commands()])
        self.assertEqual("pending", self.tache_disque(autre)[0], "OP3 jamais appliquée")

    def test_S1_k1_puis_suppression_drainee_abandonne_sans_resurrection(self) -> None:
        """Décision S-01M4PR7RE7EQ940STQ6V6WRCX4 (3a) : dans la fenêtre K1, la suppression
        humaine de X DRAINÉE (le réducteur pose `BOARD:<op>` TOMBÉ sur X) abandonne comme un
        verbe humain : ACK + trace (`lien_tombe`), aucune résurrection, X reste supprimé, la
        file derrière est livrée. À la BASE : poison, file gelée. La suppression EN VOL sans
        lien (W5) reste un refus levé (3b). MUTANT MS1 (le lien tombé reste un poison)."""
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        cree = tir["ids"][0]
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tasks.delete_task(str(self.root), cree)
        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        lien = bridge.event_store.get_board_link(cree)
        self.assertEqual((True, 1), (lien["v3_task_id"].startswith("BOARD:"), lien["tombstoned"]), lien)
        autre = tasks.new_task(str(self.root), "autre", "dev-multi").split()[1]

        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        es.enqueue_board_command(OP3, EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": autre, "status": "BLOCKED"})
        self.assertEqual(2, reprise.drain_board_commands())

        self.assertEqual([], es.pending_board_commands())
        self.assertEqual([autre], self.ids_disque(), "X reste supprimé, jamais recréé")
        self.assertEqual(("blocked", "v3:BLOCKED"), self.tache_disque(autre))
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP2), (type_, operation))
        self.assertEqual({**self.abandon_attendu(cree, lien), "lien_tombe": True}, charge["abandon"])
        self.assertEqual(lien, es.get_board_link(cree), "le lien tombé reste tombé")
        self.assertEqual((cree, None), self.reservation_ouverte())

    def test_S1b_suppression_en_vol_puis_drainee_le_rejeu_suivant_abandonne(self) -> None:
        """3b reste un refus levé TANT QUE la suppression est EN VOL (W5) ; drainée, elle pose
        le lien tombé et le rejeu suivant de la MÊME commande abandonne (3a) : le poison de
        3b n'est plus permanent. À la BASE, le rejeu retombe en FAILED."""
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        cree = tir["ids"][0]
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tasks.delete_task(str(self.root), cree)
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        self.assertEqual(0, reprise.drain_board_commands())
        self.assertEqual(("BOARD_COMMAND_FAILED", OP2), self.dernier_evenement(es)[:2])

        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        lien = es.get_board_link(cree)
        self.assertEqual(1, lien["tombstoned"], lien)
        self.assertEqual(1, reprise.drain_board_commands())
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP2), (type_, operation))
        self.assertEqual({**self.abandon_attendu(cree, lien), "lien_tombe": True}, charge["abandon"])
        self.assertEqual([], self.ids_disque())

    def test_S2_precedence_lien_vivant_et_suppression_en_vol_abandonne(self) -> None:
        """Réserve MAJEURE de l'exec-critic (S-01M4PVH2CMRBKJ4H4W4A19VPSR, passe de correction F5) : la PRÉCÉDENCE,
        conforme à la décision S-01M4PR7RE7EQ940STQ6V6WRCX4 mais sans témoin. X porte un lien `BOARD:<op>` VIVANT (verbe
        humain drainé) ET sa suppression humaine est EN VOL (outbox, non drainée) : le lien l'emporte, la reprise
        ABANDONNE (ACK, trace sans `lien_tombe`, file livrée), jamais le refus levé de 3b. MUTANT MP (le contrôle « en
        vol » avant celui du lien) : FAILED en tête de FIFO, rouge."""
        cree, lien = self.k1_puis_verbe_humain()
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tasks.delete_task(str(self.root), cree)
        self.assertIn(cree, bridge._suppressions_en_vol(bridge._board_data()), "contrôle : la suppression est EN VOL")
        self.assertEqual(0, bridge.event_store.get_board_link(cree)["tombstoned"], "contrôle : le lien est VIVANT")
        reprise = self.bridge()
        es = reprise.event_store
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        self.assertEqual(1, reprise.drain_board_commands())

        self.assertEqual([], es.pending_board_commands())
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP2), (type_, operation))
        self.assertEqual(self.abandon_attendu(cree, lien), charge["abandon"])
        self.assertEqual([], self.ids_disque(), "X reste supprimé, jamais recréé")
        self.assertEqual((cree, None), self.reservation_ouverte())

    def test_G6_lien_vers_une_identite_non_board_abandonne_avec_le_lien_trouve(self) -> None:
        """Décision S-01M4PR7RE7EQ940STQ6V6WRCX4 (G6) : un lien machine de X vers une identité
        V3 qui n'est PAS `BOARD:` — une anomalie : l'UNIQUE de
        `board_identity_reservations.board_task_id` interdit d'y arriver par
        `link_board_task`, le banc l'écrit donc en base — abandonne aussi, la trace nommant
        le lien TROUVÉ tel quel. MUTANT MG6 (abandon réservé aux liens `BOARD:`) : poison."""
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        cree = tir["ids"][0]
        with closing(get_db_connection(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO task_board_mapping (board_task_id, v3_task_id, create_operation_id, tombstoned) "
                "VALUES (?, ?, ?, 0)",
                (cree, "V3-ANOMALIE", "op-anomalie"),
            )
            conn.commit()
        reprise = self.bridge()
        es = reprise.event_store
        lien = es.get_board_link(cree)
        self.assertEqual(("V3-ANOMALIE", "op-anomalie"), (lien["v3_task_id"], lien["create_operation_id"]))
        es.enqueue_board_command(OP2, EventType.BOARD_COMMAND_REQUESTED, self.payload())
        self.assertEqual(1, reprise.drain_board_commands())

        self.assertEqual([], es.pending_board_commands())
        type_, operation, charge = self.dernier_evenement(es)
        self.assertEqual(("BOARD_COMMAND_ACKED", OP2), (type_, operation))
        self.assertEqual(self.abandon_attendu(cree, lien), charge["abandon"])
        self.assertEqual([cree], self.ids_disque())
        self.assertEqual(lien, es.get_board_link(cree))
        self.assertEqual((cree, None), self.reservation_ouverte())

    def test_W_LEGACY_reservation_sans_id_reprend_par_la_cle_texte(self) -> None:
        """C3 : une réservation ANTÉRIEURE (sans `board_task_id`) reprend par le chemin
        d'avant — la clé créatrice du texte. MUTANT K-M13 : la branche « sans id » qui
        frappe un id neuf crée une seconde tâche."""
        bridge = self.bridge()
        bridge.event_store.reserve_board_identity(V3_ID, OP1)  # forme d'avant : aucun id
        tasks = bridge._tasks_module()
        cree = tasks.create_linked_task(str(self.root), "K1", "dev-multi", OP1)
        self.assertIsNone(self.reservation()["board_task_id"])

        reprise = self.bridge()
        self.assertEqual("CREATE", reprise.reconcile_v3_to_board(operation_id=OP2, **self.payload()))

        self.assertEqual([cree], self.ids_disque())
        self.assertEqual(OP1, reprise.event_store.get_board_link(cree)["create_operation_id"])
        self.assertEqual(cree, self.reservation()["board_task_id"])

    def test_W_M33_copie_sans_record_id_rejoue_et_ne_refuse_que_d_allouer(self) -> None:
        """Clôture du lot B 3 (critic-T1060, constat 7) : une copie de `tasks*.py` SANS
        `record_id.py` (état M33, tasks_stockage.py) REJOUE une création finalisée, sans
        frapper d'id, et ne refuse que d'ALLOUER, sans rien réserver. MUTANT (`mint` avant
        la lecture de la réservation, 1b030742) : le rejeu lève `BoardError`. MUTANT
        (`try/except BoardError: frappe = None`) : l'identité neuve laisse une réservation
        SANS id, vouée au chemin d'avant."""
        bridge = self.bridge()
        self.assertEqual("CREATE", bridge.reconcile_v3_to_board(operation_id=OP1, **self.payload()))
        cree = self.ids_disque()
        source = Path(bridge._tasks_module().__file__).parent
        copie_bin = self.root / ".agents" / "bin"
        copie_bin.mkdir(parents=True)
        for partie in source.glob("tasks*.py"):
            (copie_bin / partie.name).write_bytes(partie.read_bytes())
        self.assertFalse((copie_bin / "record_id.py").exists())

        copie = self.bridge()
        self.assertEqual(copie_bin / "tasks.py", Path(copie._tasks_module().__file__))
        self.assertEqual("CREATE", copie.reconcile_v3_to_board(operation_id=OP2, **self.payload()))
        self.assertEqual(cree, self.ids_disque())
        self.assertEqual({"board_task_id": cree[0], "tombstoned": False}, self.disque()["sync_correlations"][OP2])

        neuve = dict(self.payload(), v3_task_id="V3-NEUVE")
        with self.assertRaisesRegex(copie._tasks_module().BoardError, "record_id.py"):
            copie.reconcile_v3_to_board(operation_id="m33-neuve", **neuve)
        self.assertIsNone(self.reservation("V3-NEUVE"), "rien de réservé avant le refus d'allouer")
        self.assertEqual(cree, self.ids_disque())


class SuppressionEnVolTests(_Banc):
    def supprimer_en_vol(self) -> tuple[Any, str]:
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tid = tasks.new_task(str(self.root), "à supprimer", "dev-multi").split()[1]
        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        tasks.delete_task(str(self.root), tid)
        return tasks, tid

    def reprendre_creation(self, tid: str) -> tuple[Any, list[str]]:
        reprise = self.bridge()
        reprise.event_store.enqueue_board_command(
            "v3-resurrect", EventType.BOARD_COMMAND_REQUESTED, self.payload(tid, title="resurrect?")
        )
        espion, actions = self.espion_actions()
        with self.vue_sans_cle(tid), espion:
            draines = reprise.drain_board_commands()
            etat = reprise._board_state(tid, "PENDING")[0]
        self.assertEqual(1, draines, "commande non acquittée")
        self.assertTrue(reprise.event_store.is_board_command_acked("v3-resurrect"))
        self.assertEqual(["NR"], actions)
        self.assertEqual("TOMBSTONED", etat)
        self.assertEqual([], self.ids_disque(), "aucune tâche créée")
        return reprise, actions

    def test_W4e_suppression_multi_id_ne_compte_que_le_premier_comme_le_reducteur(self) -> None:
        """Clôture du lot B 3 (critic-T1060, constat 6) : le réducteur ne tombe que
        `affected_task_ids[0]` (`EventStore.consume_board_intent`) ; le lecteur des
        suppressions en vol compte comme lui. MUTANT (union de tous les ids) ⇒ T-B vu."""
        tasks = self.bridge()._tasks_module()
        intent = {"after": None, "before": {"id": "T-A"}, "affected_task_ids": ["T-A", "T-B"]}
        self.assertEqual({"T-A"}, tasks.suppressions_en_vol({"sync_outbox": [intent]}, self.root))

    def test_W4_suppression_dans_l_outbox_rend_NR(self) -> None:
        tasks, tid = self.supprimer_en_vol()
        bridge = self.bridge()
        outbox = self.disque()["sync_outbox"]
        self.assertEqual([(tid, None)], [((i["before"] or {}).get("id"), i["after"]) for i in outbox])
        self.assertEqual(0, bridge.event_store.get_board_link(tid)["tombstoned"])
        self.assertNotIn(tid, self.ids_disque())
        self.reprendre_creation(tid)

    def test_W4b_suppression_deversee_rend_NR(self) -> None:
        tasks, tid = self.supprimer_en_vol()
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 0):
            self.assertIsNotNone(tasks._deverser_excedent(self.root))
        deverse = tasks._chemin_deverse(self.root)
        lignes = [json.loads(l) for l in deverse.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([(tid, None)], [((i["before"] or {}).get("id"), i["after"]) for i in lignes])
        self.assertEqual([], self.disque()["sync_outbox"])
        self.assertEqual(0, self.bridge().event_store.get_board_link(tid)["tombstoned"])
        self.reprendre_creation(tid)

    def test_W4c_deversement_illisible_releve_la_commande_jamais_CREATE(self) -> None:
        """FAIL-CLOSED (étape 3) : un fichier de déversement illisible fait LEVER
        `suppressions_en_vol` ; la commande est relâchée et tracée FAILED, aucune tâche
        n'est créée. MUTANT : l'aide qui avale l'erreur rend NR puis ACK."""
        tasks, tid = self.supprimer_en_vol()
        deverse = tasks._chemin_deverse(self.root)
        deverse.write_bytes(b"pas du json\n")  # ligne TERMINÉE : jamais le segment final ignoré
        with self.assertRaises(tasks.DeverseIllisible):
            tasks.suppressions_en_vol(tasks.load(self.root), self.root)
        reprise = self.bridge()
        reprise.event_store.enqueue_board_command(
            "v3-resurrect", EventType.BOARD_COMMAND_REQUESTED, self.payload(tid, title="resurrect?")
        )
        with self.vue_sans_cle(tid):
            self.assertEqual(0, reprise.drain_board_commands())
        self.assertFalse(reprise.event_store.is_board_command_acked("v3-resurrect"))
        self.assertEqual(["v3-resurrect"], [c["operation_id"] for c in reprise.event_store.pending_board_commands()])
        self.assertEqual("BOARD_COMMAND_FAILED", reprise.event_store.get_task_events(tid)[-1]["event_type"])
        self.assertEqual([], self.ids_disque())

    def test_W4d_tache_presente_et_suppression_deversee_n_est_pas_tombee(self) -> None:
        """Revue de clôture, trouvaille 3 : texte RESTAURÉ (tâche présente) pendant que sa
        suppression persiste au déversement. Une suppression en vol ne se lit que pour une
        tâche ABSENTE du texte : `pending × IN_DEV` rend `E` — commande relâchée, FAILED
        tracé, BRUYANT et réversible. MUTANT (lecture sans `task is None`) : TOMBSTONED,
        NR acquitté en SILENCE (divergence board/V3 sans trace)."""
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tid = tasks.new_task(str(self.root), "vivante", "dev-multi").split()[1]
        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        snapshot = tasks.canonical_task_snapshot(tasks.find(tasks.load(self.root), tid))
        deverse = tasks._chemin_deverse(self.root)
        deverse.parent.mkdir(parents=True, exist_ok=True)
        intent = {"operation_id": "op-suppression-restauree", "event_kind": "BOARD_TASK_OBSERVED",
                  "affected_task_ids": [tid], "before": snapshot, "after": None,
                  "revision_sha256": "0" * 64, "attempt": 0, "lease": None}
        deverse.write_text(json.dumps(intent) + "\n", encoding="utf-8")
        self.assertIn(tid, tasks.suppressions_en_vol(tasks.load(self.root), self.root))
        self.assertIn(tid, self.ids_disque())

        reprise = self.bridge()
        self.assertEqual("pending", reprise._board_state(tid, "IN_DEV")[0])
        reprise.event_store.enqueue_board_command(
            "v3-dev", EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": tid, "status": "IN_DEV"}
        )
        espion, actions = self.espion_actions()
        with espion:
            self.assertEqual(0, reprise.drain_board_commands())
        self.assertEqual(["E"], actions)
        self.assertFalse(reprise.event_store.is_board_command_acked("v3-dev"))
        self.assertEqual(["v3-dev"], [c["operation_id"] for c in reprise.event_store.pending_board_commands()])
        dernier = reprise.event_store.get_task_events(tid)[-1]
        self.assertEqual("BOARD_COMMAND_FAILED", dernier["event_type"])
        self.assertIn("explicit delta", json.dumps(dernier, ensure_ascii=False))
        self.assertEqual("pending", tasks.find(tasks.load(self.root), tid)["state"])

    def test_W6_suppression_reduite_rejouee_sous_une_op_neuve_never_resurrect(self) -> None:
        bridge = self.bridge()
        tasks = bridge._tasks_module()
        tid = tasks.new_task(str(self.root), "réduite", "dev-multi").split()[1]
        tasks.drain_sync_outbox(self.root, bridge.consume_board_intent)
        snapshot = tasks.canonical_task_snapshot(tasks.find(tasks.load(self.root), tid))
        tasks.delete_task(str(self.root), tid)
        tasks.drain_sync_outbox(self.root, bridge.consume_board_intent)
        self.assertEqual(1, bridge.event_store.get_board_link(tid)["tombstoned"])

        effet = bridge.event_store.consume_board_intent(
            {
                "operation_id": "op-neuve-apres-reduction",
                "event_kind": "BOARD_TASK_OBSERVED",
                "affected_task_ids": [tid],
                "before": snapshot,
                "after": {**snapshot, "task": "ressuscitée ?"},
                "revision_sha256": "0" * 64,
                "attempt": 0,
                "lease": None,
            }
        )
        self.assertEqual((False, "never-resurrect"), (effet["applied"], effet["action"]))
        self.assertEqual(1, bridge.event_store.get_board_link(tid)["tombstoned"])


class CoteTexteTests(_Banc):
    def tasks(self) -> Any:
        return self.bridge()._tasks_module()

    def test_W8_create_linked_task_sous_un_id_donne(self) -> None:
        tasks = self.tasks()
        donne = tasks.record_id_module().mint("T")
        self.assertEqual(donne, tasks.create_linked_task(str(self.root), "t", "dev-multi", "op-a", board_task_id=donne))
        self.assertEqual([donne], self.ids_disque())
        self.assertEqual({"board_task_id": donne, "tombstoned": False}, self.disque()["sync_correlations"]["op-a"])

        existante = tasks.new_task(str(self.root), "existante", "dev-multi").split()[1]
        self.assertEqual(
            existante, tasks.create_linked_task(str(self.root), "autre titre", "x", "op-b", board_task_id=existante)
        )
        self.assertEqual(sorted([donne, existante]), sorted(self.ids_disque()), "créditée, jamais recréée")
        self.assertEqual("existante", tasks.find(tasks.load(self.root), existante)["task"])
        self.assertEqual({"board_task_id": existante, "tombstoned": False}, self.disque()["sync_correlations"]["op-b"])

        with self.assertRaisesRegex(tasks.BoardError, "another board identity"):
            tasks.create_linked_task(str(self.root), "t", "dev-multi", "op-a", board_task_id=existante)

        tombee = tasks.new_task(str(self.root), "tombée", "dev-multi").split()[1]
        tasks.delete_task(str(self.root), tombee)
        with self.assertRaisesRegex(tasks.BoardError, "refusing resurrection"):
            tasks.create_linked_task(str(self.root), "t", "dev-multi", "op-c", board_task_id=tombee)
        self.assertNotIn(tombee, self.ids_disque())
        self.assertNotIn("op-c", self.disque()["sync_correlations"])

    def test_W9_enqueue_sync_intent_refuse_une_op_deja_dans_l_outbox(self) -> None:
        tasks = self.tasks()
        tid = tasks.new_task(str(self.root), "t", "dev-multi").split()[1]
        data = tasks.load(self.root)
        deja = data["sync_outbox"][0]["operation_id"]
        task = tasks.find(data, tid)
        with self.assertRaisesRegex(tasks.BoardError, deja):
            tasks.enqueue_sync_intent(data, tid, task, task, operation_id=deja)
        self.assertEqual(1, len(data["sync_outbox"]))
        self.assertEqual("op-explicite", tasks.enqueue_sync_intent(data, tid, task, task, operation_id="op-explicite"))
        self.assertEqual("op-explicite", data["sync_outbox"][-1]["operation_id"])
        self.assertEqual({"board_task_id": tid, "tombstoned": False}, data["sync_correlations"]["op-explicite"])


ED8 = "ed8cf3e0-4684-4572-a170-424dd55d85fb"
FF7 = "7ffd64ba-41de-490e-821b-a292e365cbcc"
A1E = "a1eceddf-5849-4727-b14e-0ef6324b233b"
D6C = "d6c40430-dfae-438c-a4cf-82f54899c9f3"
T571, T572, T573 = ("T-%08d" % n for n in (571, 572, 573))


class MigrationTexteSeuleTests(_Banc):
    """W-MIG (étape 5, S-00003372) sur une racine FABRIQUÉE : les trois corrélations
    texte seules du kit portées en machine, puis rejouées depuis l'export dans une
    base NEUVE. MUTANTS : K-M9 (intent T-571 omis, T-572 sans suppression, T-573 non
    réaligné) et K-M10 (contrôle de présence machine retiré : la 2e passe ré-écrit)."""

    @staticmethod
    def tache(tid: str) -> dict[str, str]:
        return {"id": tid, "state": "done", "task": tid, "owner": "dev-multi", "stage": "clos", "updated": "2026-09-30"}

    def fabriquer(self, *, kit: bool = True, t573_tombee: bool = False) -> Any:
        """`t573_tombee` : la clé texte A1E est TOMBÉE et nomme une AUTRE tâche, ABSENTE (variante adoptant : ces ids y
        nomment d'autres tâches) — T-573 est alors « sans objet ». Jamais T-573 vivante sous une clé tombée : depuis
        T-00001058 c'est une résurrection (F5), et tout `save()` du board la refuse."""
        if kit:
            (self.root / ".agents").mkdir(parents=True, exist_ok=True)
            (self.root / ".agents" / "IS_THE_KIT").write_text("banc\n", encoding="utf-8")
        board = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board.parent.mkdir(parents=True, exist_ok=True)
        correlations = {
            ED8: {"board_task_id": T571, "tombstoned": False},
            FF7: {"board_task_id": T572, "tombstoned": True},
            A1E: {"board_task_id": "T-09999573" if t573_tombee else T573, "tombstoned": t573_tombee},
        }
        board.write_text(
            json.dumps({"tasks": [self.tache(T571), self.tache(T573)], "sync_outbox": [], "sync_correlations": correlations}),
            encoding="utf-8",
        )
        bridge = self.bridge()
        self.semer_lien(bridge, T573, D6C)  # le créateur MACHINE de T-573, un intent DELTA
        return bridge

    def semer_lien(self, bridge: Any, tid: str, operation_id: str) -> None:
        apres = self.tache(tid)
        bridge.consume_board_intent(
            {
                "operation_id": operation_id,
                "event_kind": "BOARD_TASK_OBSERVED",
                "affected_task_ids": [tid],
                "before": {**apres, "stage": ""},
                "after": apres,
                "revision_sha256": "0" * 64,
                "attempt": 0,
                "lease": None,
            }
        )

    @staticmethod
    def lignes_export() -> list[str]:
        """Les lignes de `runs/<auteur>/<copie>/*.jsonl` sous la racine d'export du banc."""
        runs = Path(os.environ["CADRE_PROJECT_ROOT"]) / "runs"
        lignes: list[str] = []
        for auteur in sorted(runs.iterdir()) if runs.is_dir() else []:
            for copie in sorted(auteur.iterdir()):
                for fichier in sorted(copie.iterdir()):
                    if fichier.suffix == ".jsonl":
                        lignes += [l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()]
        return lignes

    def reconstruire(self) -> Any:
        from agentic_v3.db.event_store import EventStore

        store = EventStore(self.root / "neuve.db", project_root=self.root)
        resume = store.reconstruire_depuis_exports(racine=os.environ["CADRE_PROJECT_ROOT"])
        self.assertFalse(resume["avortee"], resume)
        return store

    def test_W_MIG_trois_jointures_portees_en_machine_puis_idempotente(self) -> None:
        bridge = self.fabriquer()
        self.assertEqual({T571: "posé", T572: "posé", T573: "posé"}, bridge.migrer_correlations_texte_seules())
        correlations = self.disque()["sync_correlations"]
        self.assertNotIn(A1E, correlations)
        self.assertEqual({"board_task_id": T573, "tombstoned": False}, correlations[D6C])
        tasks = bridge._tasks_module()
        self.assertEqual(3, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))
        self.assertEqual([], self.disque()["sync_outbox"])

        store = self.reconstruire()
        for tid, operation_id, tombe in ((T571, ED8, 0), (T572, FF7, 1), (T573, D6C, 0)):
            lien = store.get_board_link(tid)
            self.assertIsNotNone(lien, tid)
            self.assertEqual((operation_id, tombe), (lien["create_operation_id"], int(lien["tombstoned"])), tid)
        correlations = self.disque()["sync_correlations"]
        self.assertEqual({"board_task_id": T571, "tombstoned": False}, correlations[ED8])
        self.assertEqual({"board_task_id": T572, "tombstoned": True}, correlations[FF7])
        self.assertNotIn(A1E, correlations)

        export, avant = self.lignes_export(), self.disque()
        self.assertEqual(
            {T571: "déjà migrée", T572: "déjà migrée", T573: "déjà migrée"},
            self.bridge().migrer_correlations_texte_seules(),
        )
        self.assertEqual(avant, self.disque(), "2e passe : rien d'écrit")
        self.assertEqual(export, self.lignes_export(), "2e passe : export inchangé")

    def test_W_MIG_variante_adoptant_et_lien_divergent_rien_d_ecrit(self) -> None:
        bridge = self.fabriquer(t573_tombee=True)
        self.semer_lien(bridge, T571, "op-d-un-autre-createur")
        avant = self.disque()
        self.assertEqual(
            {T571: "divergente", T572: "posé", T573: "sans objet"}, bridge.migrer_correlations_texte_seules()
        )
        apres = self.disque()
        self.assertEqual(avant["sync_correlations"][A1E], apres["sync_correlations"][A1E])
        self.assertNotIn(D6C, apres["sync_correlations"])
        operations = [intent["operation_id"] for intent in apres["sync_outbox"]]
        self.assertEqual(2, len(operations), operations)  # T-572 seule : création PUIS suppression
        self.assertEqual(FF7, operations[0])
        self.assertNotIn(ED8, operations)

    def test_W_MIG_sans_marqueur_du_kit_tout_est_sans_objet(self) -> None:
        """C10 : sans `.agents/IS_THE_KIT`, aucun des trois cas ne s'applique, rien n'est lu ni écrit."""
        bridge = self.fabriquer(kit=False)
        chemin = self.root / ".agents" / "state" / "board" / "TASKS.json"
        octets = chemin.read_bytes()
        self.assertEqual(
            {T571: "sans objet", T572: "sans objet", T573: "sans objet"}, bridge.migrer_correlations_texte_seules()
        )
        self.assertEqual(octets, chemin.read_bytes())

    def test_W_MIG_refuse_une_outbox_ou_un_deversement_non_vides(self) -> None:
        bridge = self.fabriquer()
        tasks = bridge._tasks_module()
        tasks.new_task(str(self.root), "en attente", "dev-multi")
        with self.assertRaisesRegex(RuntimeError, "replay-sync"):
            bridge.migrer_correlations_texte_seules()
        with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 0):
            self.assertIsNotNone(tasks._deverser_excedent(self.root))
        self.assertEqual([], self.disque()["sync_outbox"])
        with self.assertRaisesRegex(RuntimeError, "replay-sync"):
            bridge.migrer_correlations_texte_seules()
        self.assertIn(A1E, self.disque()["sync_correlations"])


#: La racine RÉELLE du dépôt, dérivée du fichier (ancre du localisateur de
#: `test_adopting_gate.py`) ; chaque témoin qui la nomme saute d'abord hors du kit.
ROOT = Path(__file__).resolve().parents[4] if Path(__file__).resolve().parents[2].name == "vendor" else Path(__file__).resolve().parents[2]


class ExportsSuivisTests(_Banc):
    """W7 (étape 8, passe 2) sur les exports SUIVIS du kit, lus par `operation_id` —
    jamais par grep : W7a extrait l'archive du commit courant (`runs`,
    `.agents/state/board`) dans une racine jetable ; W7b ne lit que le board suivi
    (`git show HEAD:…/TASKS.json`, sans extraire l'archive). W7a (machine) et W7b (texte) sont
    SÉPARÉS : T-1009 réécrit W7b seul au retrait de la clé texte (S-00003390). Kit
    seul (`runs/` et `.agents/IS_THE_KIT` ne voyagent pas). ROUGE mesuré sur
    l'archive de la fusion d'avant données (8415957c). MUTANTS : K-M11 (ligne de
    l'intent T-571 retirée de l'export) ⇒ W7a ; K-M12 (`a1eceddf` remis au texte)
    ⇒ W7b."""

    def extraire_exports_suivis(self, racine: Path) -> Path:
        """`git archive HEAD runs .agents/state/board` de `racine`, extrait par
        `tarfile` sous la racine jetable du banc ; les deux chemins attendus sont
        ASSERTÉS présents, pour qu'une archive vide ne passe pas pour une jointure
        fausse."""
        sortie = subprocess.run(
            ["git", "-C", str(racine), "archive", "HEAD", "runs", ".agents/state/board"],
            capture_output=True,
            check=True,
        ).stdout
        jetable = self.root / "archive"
        with tarfile.open(fileobj=io.BytesIO(sortie)) as archive:
            archive.extractall(path=jetable, filter="data")
        self.assertTrue((jetable / "runs").is_dir(), "archive sans runs/")
        board = jetable / ".agents" / "state" / "board"
        self.assertTrue(self.board_suivi_present(board), "archive sans board")
        return jetable

    @staticmethod
    def board_suivi_present(board: Path) -> bool:
        """Les DEUX formes du board (T-00001009) : le monolithe, ou au moins UN enregistrement `tasks/T-*.json` après
        la bascule — un dossier `tasks/` VIDE n'est pas un board (mineur de l'exec-critic)."""
        return (board / "TASKS.json").is_file() or any((board / "tasks").glob("T-*.json"))

    def test_W7a_un_dossier_tasks_vide_n_est_pas_un_board(self) -> None:
        """Le prédicat de présence de W7a : dossier `tasks/` VIDE ⇒ absent ; un `T-*.json` ⇒ présent ; TASKS.json ⇒
        présent. MUTANT « `tasks/` existe suffit » ⇒ rouge."""
        board = self.root / "w7a" / ".agents" / "state" / "board"
        (board / "tasks").mkdir(parents=True)
        self.assertFalse(self.board_suivi_present(board))
        (board / "tasks" / "T-1.json").write_text("{}", encoding="utf-8")
        self.assertTrue(self.board_suivi_present(board))
        (board / "tasks" / "T-1.json").unlink()
        (board / "TASKS.json").write_text("{}", encoding="utf-8")
        self.assertTrue(self.board_suivi_present(board))

    def correlations_suivies(self, racine: Path) -> dict[str, Any]:
        """`sync_correlations` du board SUIVI au HEAD de `racine`, dans SA forme (T-00001009, S-00003390) : le
        monolithe s'il est suivi ; sinon la projection des enregistrements `board/tasks/` lus par UN
        `git cat-file --batch` (aucune extraction), assemblés par le `tasks.py` du dépôt."""
        board = ".agents/state/board"
        if subprocess.run(["git", "-C", str(racine), "cat-file", "-e", f"HEAD:{board}/TASKS.json"],
                          capture_output=True).returncode == 0:
            sortie = subprocess.run(["git", "-C", str(racine), "show", f"HEAD:{board}/TASKS.json"],
                                    capture_output=True, check=True).stdout
            return json.loads(sortie)["sync_correlations"]
        noms = subprocess.run(["git", "-C", str(racine), "ls-tree", "-r", "--name-only", "HEAD", "--", f"{board}/tasks/"],
                              capture_output=True, check=True, text=True).stdout.splitlines()
        self.assertTrue(noms, "HEAD ne suit ni TASKS.json ni board/tasks/")
        brut = subprocess.run(["git", "-C", str(racine), "cat-file", "--batch"], capture_output=True, check=True,
                              input="".join(f"HEAD:{nom}\n" for nom in noms).encode("utf-8")).stdout
        fichiers, curseur = {}, 0
        for nom in noms:
            fin = brut.index(b"\n", curseur)
            taille = int(brut[curseur:fin].split()[2])
            fichiers[f"tasks/{Path(nom).name}"] = brut[fin + 1:fin + 1 + taille]
            curseur = fin + 1 + taille + 1
        return _tasks_lecteur().assemble_store(fichiers, ("tasks", "epics"))["sync_correlations"]

    def trois_jointures_sans_a1e(self, correlations: dict[str, Any]) -> None:
        self.assertEqual({"board_task_id": T571, "tombstoned": False}, correlations.get(ED8))
        self.assertEqual({"board_task_id": T572, "tombstoned": True}, correlations.get(FF7))
        self.assertEqual({"board_task_id": T573, "tombstoned": False}, correlations.get(D6C))
        # Appartenance EXACTE, message court : `assertNotIn` déverserait le dict entier.
        self.assertFalse(A1E in correlations, f"{A1E} encore au texte : {correlations.get(A1E)}")

    def test_W7a_machine_trois_liens_reconstruits_depuis_les_exports_suivis(self) -> None:
        marqueur = ROOT / ".agents" / "IS_THE_KIT"
        if not marqueur.is_file():
            self.skipTest("kit seul : les exports suivis du kit ne voyagent pas")
        from agentic_v3.db.event_store import EventStore

        jetable = self.extraire_exports_suivis(ROOT)
        store = EventStore(jetable / "neuve.db", project_root=jetable)
        resume = store.reconstruire_depuis_exports(racine=jetable)
        self.assertFalse(resume["avortee"], resume)
        self.assertGreater(resume["applied"], 0, resume)
        for tid, operation_id, tombe in ((T571, ED8, 0), (T572, FF7, 1), (T573, D6C, 0)):
            lien = store.get_board_link(tid)
            self.assertIsNotNone(lien, f"{tid} absente de task_board_mapping")
            self.assertEqual((operation_id, tombe), (lien["create_operation_id"], int(lien["tombstoned"])), tid)

    def test_W7b_texte_correlations_suivies_sans_la_cle_a1eceddf(self) -> None:
        marqueur = ROOT / ".agents" / "IS_THE_KIT"
        if not marqueur.is_file():
            self.skipTest("kit seul : le board suivi du kit ne voyage pas")
        self.trois_jointures_sans_a1e(self.correlations_suivies(ROOT))

    def test_W7b_repli_sur_un_head_migre(self) -> None:
        """W7b sur un HEAD FACTICE migré (T-00001009) : dépôt jetable dont le board suivi est en enregistrements
        (`migrate_store`), sans TASKS.json — mêmes trois jointures et absence de A1E, lues par le repli. ROUGE à la
        BASE ; MUTANT « W7b sans repli » (le monolithe seul : `git show HEAD:…/TASKS.json` échoue) ⇒ rouge."""
        depot = self.root / "factice"
        depot.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(depot), "-c", f"core.hooksPath={os.devnull}", *args],
                           capture_output=True, check=True, env=env, timeout=120)

        git("-c", "init.defaultBranch=main", "init", "-q")
        for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"), ("commit.gpgsign", "false")):
            git("config", cle, valeur)
        (depot / ".gitignore").write_text("/.agents/state/local/\n", encoding="utf-8")
        board = depot / ".agents" / "state" / "board"
        board.mkdir(parents=True)
        tache = MigrationTexteSeuleTests.tache
        (board / "TASKS.json").write_text(json.dumps({
            "tasks": [tache(T571), tache(T573)],
            "sync_correlations": {ED8: {"board_task_id": T571, "tombstoned": False},
                                  FF7: {"board_task_id": T572, "tombstoned": True},
                                  D6C: {"board_task_id": T573, "tombstoned": False}},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _tasks_lecteur().migrate_store(depot)
        git("add", "-A")
        git("commit", "-q", "-m", "board migré")
        self.assertFalse((board / "TASKS.json").exists())
        self.trois_jointures_sans_a1e(self.correlations_suivies(depot))


class LectureDuBoardParFormeTests(_Banc):
    """T-00001009, étape 6 : le pont lit le board par le module tasks (`lire_board_brut`), quelle que soit sa forme
    — sur un board en dossier, `_board_data` brut rendait `{"tasks": []}` et chaque tâche serait
    `ABSENT_NEVER_LINKED` : un CREATE autorisé ferait un doublon (M4 du plan)."""

    def test_B1_le_pont_lit_l_etat_publie(self) -> None:
        """B1 CONTRÔLE (vert à la BASE, sur le monolithe) : `_board_data` rend les tâches et la corrélation du board
        PUBLIÉ. En forme dossier (là où `migrate_store` existe), un save mort APRÈS son lot (le point de validation) est
        lu en ENTIER par le pont : la surcouche du lot. Tue M-sans-surcouche."""
        tasks = self.bridge()._tasks_module()
        tid = tasks.new_task(str(self.root), "b1", "banc").split()[1]
        data = self.bridge()._board_data()
        self.assertEqual([t["id"] for t in data["tasks"]], [tid])
        self.assertEqual({c["board_task_id"] for c in data["sync_correlations"].values()}, {tid})
        if getattr(tasks, "migrate_store", None) is None:
            return  # BASE : la forme dossier n'existe pas, le contrôle du monolithe suffit
        tasks.migrate_store(str(self.root))

        def mort(*_args: Any, **_kwargs: Any) -> None:
            raise _Crash("mort après le lot")

        with mock.patch.object(tasks, "_poser_definitif", mort), self.assertRaises(_Crash):
            tasks.stage_task(str(self.root), tid, "b1-lot")
        data = self.bridge()._board_data()
        self.assertEqual([(t["id"], t["stage"]) for t in data["tasks"]], [(tid, "b1-lot")])
        self.assertNotIn("sync_outbox", data)

    def test_B2_dossier_cle_creatrice_retiree_credit_sous_l_id_reserve(self) -> None:
        """B2 : board en DOSSIER, K1 (mort après le save texte, réservation non finalisée), clé créatrice retirée ⇒ la
        reprise crédite l'id RÉSERVÉ, jamais une seconde tâche (sans lecture par forme : `ABSENT_NEVER_LINKED`,
        doublon)."""
        tasks = self.bridge()._tasks_module()
        tasks.new_task(str(self.root), "graine", "banc")
        tasks.migrate_store(str(self.root))
        tir = self.crash_k1(sonde=self.sonde_k1, apres=True)
        vu = tir["ids"]
        self.assertEqual(2, len(vu), vu)
        tasks = self.bridge()._tasks_module()
        with tasks.board_lock(self.root):
            data = tasks.load(self.root)
            del data["sync_correlations"][OP1]
            tasks.save(self.root, data)
        self.assertEqual("dossier", tasks.store_form(self.root))
        reprise = self.bridge()
        reprise.reconcile_v3_to_board(operation_id=OP2, **self.payload())
        self.assertEqual(sorted(vu), sorted(self.ids_disque()), "une seule tâche créée, celle vue à l'injection")
        self.assertIn(tir["reservation"]["board_task_id"], vu)
        self.assertIsNotNone(self.reservation()["finalized_at"])

    def test_B3_un_board_en_dossier_seul_est_lu_par_le_pont(self) -> None:
        """B3 : un board en dossier SEUL (aucun TASKS.json) — `_board_data` rend sa tâche et la projection de sa
        corrélation, sans `sync_outbox` ; `_board_state` ne la lit pas `ABSENT_NEVER_LINKED`. ROUGE à la BASE
        (`{"tasks": []}`). Tue M-lecture-brute."""
        dossier = self.root / ".agents" / "state" / "board" / "tasks"
        dossier.mkdir(parents=True)
        tache = {"id": "T-1", "owner": "", "stage": "", "state": "pending", "task": "un", "updated": "2026-10-11"}
        (dossier / "T-1.json").write_text(json.dumps({"format": 1, "id": "T-1", "record": tache,
                                                      "sync_operations": ["op-1"]}, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
        pont = self.bridge()
        data = pont._board_data()
        self.assertEqual(data.get("tasks"), [tache])
        self.assertEqual(data.get("sync_correlations"), {"op-1": {"board_task_id": "T-1", "tombstoned": False}})
        self.assertNotIn("sync_outbox", data)
        self.assertNotEqual("ABSENT_NEVER_LINKED", pont._board_state("T-1", "PENDING")[0])
