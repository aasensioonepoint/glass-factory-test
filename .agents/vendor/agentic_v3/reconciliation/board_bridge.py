"""Crash-safe, idempotent bridge between TASKS.json and the V3 EventStore.

ORDRE D'ÉCRITURE D'UNE CRÉATION V3 → board (T-00001060, K1, décision pilote
S-00003347) : MACHINE d'abord, TEXTE ensuite. L'id board est frappé
(`record_id.mint`, pour une identité V3 que ni réservation ni lien ne portent
encore : un rejeu n'alloue rien) puis RÉSERVÉ dans `board_identity_reservations` avant que
`TASKS.json` ne porte quoi que ce soit ; la tâche texte naît sous CET id ; le lien
(`link_board_task`) finalise. Deux magasins, AUCUNE transaction commune : une mort
entre deux écritures laisse soit une réservation sans tâche (fenêtre inverse),
soit une tâche sans finalisation (K1) — la reprise relit la réservation et
recrée ou CRÉDITE sous l'id réservé, jamais sous un id neuf. Une suppression EN
VOL (outbox ou déversement, `tasks.suppressions_en_vol`) se lit `TOMBSTONED` pour
une tâche ABSENTE du texte — jamais pour une tâche présente. Une reprise dont l'id
réservé porte DÉJÀ un lien machine (verbe humain drainé dans la fenêtre K1) est
ABANDONNÉE, acquittée avec une trace `abandon` (S-01M4KHNE8597YSZ4YY54YVWFDZ,
`CreationAbandonnee`) : X reste à l'humain et la file derrière est livrée."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional, Union

from agentic_v3.db.event_store import EventStore
from agentic_v3.db import run_export
from agentic_v3.db.schema import get_db_connection, DEFAULT_DB_PATH
from agentic_v3.models.events import EventType


BOARD_STATES = (
    "pending",
    "running",
    "blocked",
    "done",
    "ABSENT_NEVER_LINKED",
    "TOMBSTONED",
)
V3_BOARD_MATRIX = {
    "PENDING": ("N", "E", "U", "E", "C(auth)/NR", "NR"),
    "IN_DEV": ("E", "Sdev", "E", "E", "NR", "NR"),
    "IN_CRITIC": ("E", "Scritic", "E", "E", "NR", "NR"),
    "IN_TEST": ("E", "Stest", "E", "E", "NR", "NR"),
    "COMPLETED": ("D", "D", "D", "N", "NR", "NR"),
    "BLOCKED": ("B", "B", "B*", "E", "NR", "NR"),
    "BLOCKED_WAITING_DEPENDENCY": ("B", "B", "B*", "E", "NR", "NR"),
    "BLOCKED_WAITING_HUMAN_DECISION": ("B", "B", "B*", "E", "NR", "NR"),
    "OUTDATED_REQUIRES_REFACTOR": (
        "B+DELTA",
        "B+DELTA",
        "B+DELTA",
        "B+DELTA",
        "DELTA(auth)/NR",
        "DELTA(auth)/NR",
    ),
}
STATUS_STAGE = {
    "IN_DEV": "dev",
    "IN_CRITIC": "plan-critic",
    "IN_TEST": "test",
}
BLOCK_NOTES = {
    "BLOCKED": "v3:BLOCKED",
    "BLOCKED_WAITING_DEPENDENCY": "v3:WAITING_DEP",
    "BLOCKED_WAITING_HUMAN_DECISION": "v3:WAITING_HUMAN",
    "OUTDATED_REQUIRES_REFACTOR": "v3:OUTDATED_REFACTOR",
}


def acteur_pont_v3() -> Dict[str, Any]:
    """L'ACTEUR DU PONT V3 EST FIXE (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot B). Le pont écrit sur la
    foi d'un événement V3, sans session ni humain : il signe « pont V3 », sans email ni copie,
    et ne lit JAMAIS l'identité Git ni la copie du clone (``acteur_courant``) — sinon le stage
    porterait le nom de quiconque a lancé ``sync-spec``. Un dict NEUF à chaque appel."""
    return {"auteur": {"nom": "pont V3", "email": None}, "copie": None}


class CreationAbandonnee(RuntimeError):
    """Création V3 → board ABANDONNÉE avant toute écriture texte (décision pilote
    S-01M4KHNE8597YSZ4YY54YVWFDZ, option b) : l'id réservé porte déjà un lien machine.
    `trace` nomme la décision, l'identité V3 sans tâche board, l'id, l'op créatrice et le
    lien TROUVÉ ; `drain_board_commands` l'acquitte dans le payload de l'ACK (`abandon`)."""

    def __init__(self, message: str, trace: Dict[str, Any]) -> None:
        super().__init__(message)
        self.trace = trace


class BoardBridge:
    """Bidirectional adapter; all projection writes stay inside EventStore."""

    def __init__(
        self,
        db_path: Union[str, Path, None] = None,
        project_root: Union[str, Path, None] = None,
    ) -> None:
        # T-00000650 : ORDRE des trois lignes IMPOSÉ. `self.project_root` n'existe
        # pas encore à la ligne (1) et `_infer_root` lit `self.db_path` — l'écrire
        # dans l'autre sens serait une circularité. Le défaut de `db_path` résout
        # PARESSEUSEMENT vers `DEFAULT_DB_PATH(project_root)` (partition MACHINE,
        # hors dépôt), et `EventStore` reçoit désormais la racine que cette ligne
        # ne lui transmettait pas.
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH(project_root)
        self.project_root = Path(project_root) if project_root is not None else self._infer_root()
        self.event_store = EventStore(self.db_path, project_root=self.project_root)
        self._tasks_module_cache: Optional[ModuleType] = None

    def _infer_root(self) -> Path:
        current = self.db_path.resolve().parent
        for candidate in (current, *current.parents):
            if (candidate / ".agents").exists():
                return candidate
        return Path.cwd()

    def consume_board_intent(self, intent: Dict[str, Any]) -> bool:
        """Apply one Board -> V3 intent and confirm its durable inbox row."""
        self.event_store.consume_board_intent(intent)
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT operation_id FROM board_sync_inbox WHERE operation_id=?",
                (intent["operation_id"],),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    @staticmethod
    def decide_action(
        status: str,
        board_state: str,
        *,
        create_authorized: bool = False,
        delta_authorized: bool = False,
        block_note_convergent: bool = False,
    ) -> str:
        if status not in V3_BOARD_MATRIX:
            raise ValueError(f"unknown V3 status: {status!r}")
        if board_state not in BOARD_STATES:
            raise ValueError(f"unknown board state: {board_state!r}")
        raw = V3_BOARD_MATRIX[status][BOARD_STATES.index(board_state)]
        if raw == "C(auth)/NR":
            return "CREATE" if create_authorized else "NR"
        if raw == "DELTA(auth)/NR":
            return "DELTA" if delta_authorized else "NR"
        if raw == "B*":
            return "N" if block_note_convergent else "B"
        return raw

    def _board_data(self) -> Dict[str, Any]:
        """Le board BRUT, quelle que soit sa forme (T-00001009) : par le lecteur UNIQUE du module tasks
        (`lire_board_brut` : le monolithe tel quel, ou les enregistrements, un lot validé en surcouche et
        `sync_correlations` = leur projection) ; un `tasks.py` qui ne l'a pas est antérieur : lecture brute
        de TASKS.json (chemin d'avant). Sans ce lecteur, un board en dossier se lirait `{"tasks": []}` et
        chaque tâche `ABSENT_NEVER_LINKED` : un CREATE autorisé ferait un doublon."""
        lecteur = getattr(self._tasks_module(), "lire_board_brut", None)
        if lecteur is not None:
            return lecteur(self.project_root)
        path = self.project_root / ".agents" / "state" / "board" / "TASKS.json"
        if not path.exists():
            return {"tasks": [], "sync_correlations": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _suppressions_en_vol(self, data: Dict[str, Any]) -> set[str]:
        """Les ids dont une suppression est EN VOL (T-00001060), par le lecteur UNIQUE du
        module tasks ; un `tasks.py` qui ne l'a pas est antérieur : ensemble vide (chemin
        d'avant). Illisible ⇒ la levée REMONTE : la commande est relâchée, jamais CREATE."""
        lecteur = getattr(self._tasks_module(), "suppressions_en_vol", None)
        return lecteur(data, self.project_root) if lecteur is not None else set()

    def _board_state(self, board_task_id: str, status: str) -> tuple[str, Optional[Dict[str, Any]]]:
        """État board de `board_task_id`. `TOMBSTONED` si le lien machine ou une corrélation
        texte le porte, OU — tâche ABSENTE du texte seulement — une suppression EN VOL
        (T-00001060, option B) : seule la case `PENDING × ABSENT` change d'issue (CREATE ⇒
        NR) quand la clé texte manque. Une tâche PRÉSENTE (texte restauré pendant que le
        déversement persiste) n'est jamais lue tombée par une suppression en vol, et un
        déversement illisible ne fait lever que la commande sur une tâche absente."""
        data = self._board_data()
        task = next((item for item in data.get("tasks", []) if item["id"] == board_task_id), None)
        link = self.event_store.get_board_link(board_task_id)
        correlations = [
            value
            for value in data.get("sync_correlations", {}).values()
            if value.get("board_task_id") == board_task_id
        ]
        tombstoned = bool(link and link.get("tombstoned")) or any(
            value.get("tombstoned") for value in correlations
        )
        if not tombstoned and task is None:
            tombstoned = board_task_id in self._suppressions_en_vol(data)
        if tombstoned:
            return "TOMBSTONED", task
        if task is None:
            return "ABSENT_NEVER_LINKED", None
        if task["state"] == "blocked":
            expected_note = BLOCK_NOTES.get(status, "")
            if expected_note and task.get("stage") == expected_note:
                return "blocked", task
        return str(task["state"]), task

    def reconcile_v3_to_board(
        self,
        board_task_id: str,
        status: str,
        *,
        operation_id: str,
        create_authorized: bool = False,
        create_title: str = "",
        create_owner: str = "",
        v3_task_id: Optional[str] = None,
        delta_authorized: bool = False,
        delta_title: str = "",
        delta_owner: str = "dev-multi",
        delta_v3_task_id: Optional[str] = None,
        delivery_lease_token: Optional[str] = None,
        delivery_lease_seconds: float = 30.0,
    ) -> str:
        """Heartbeat, mutate, and verify under the board's writer exclusion.

        The heartbeat covers the Board critical section; strict FIFO keeps every
        later command unclaimable until this head command is ACKed or released.
        """
        tasks = self._tasks_module()
        if delivery_lease_token is None:
            with tasks.board_lock(self.project_root):
                return self._reconcile_v3_to_board_locked(
                    tasks=tasks,
                    board_task_id=board_task_id,
                    status=status,
                    operation_id=operation_id,
                    create_authorized=create_authorized,
                    create_title=create_title,
                    create_owner=create_owner,
                    v3_task_id=v3_task_id,
                    delta_authorized=delta_authorized,
                    delta_title=delta_title,
                    delta_owner=delta_owner,
                    delta_v3_task_id=delta_v3_task_id,
                )

        lease_seconds = max(float(delivery_lease_seconds), 0.004)
        if not self.event_store.renew_board_command_lease(
            operation_id,
            delivery_lease_token,
            lease_seconds=lease_seconds,
        ):
            return "CANCELLED"

        stop_heartbeat = threading.Event()
        lease_lost = threading.Event()
        heartbeat_interval = max(lease_seconds / 3.0, 0.001)

        def maintain_lease() -> None:
            while not stop_heartbeat.wait(heartbeat_interval):
                try:
                    renewed = self.event_store.renew_board_command_lease(
                        operation_id,
                        delivery_lease_token,
                        lease_seconds=lease_seconds,
                    )
                except Exception:
                    lease_lost.set()
                    return
                if not renewed:
                    lease_lost.set()
                    return

        def approve_board_commit() -> bool:
            if lease_lost.is_set():
                return False
            try:
                renewed = self.event_store.renew_board_command_lease(
                    operation_id,
                    delivery_lease_token,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                lease_lost.set()
                return False
            if not renewed:
                lease_lost.set()
            return renewed

        heartbeat = threading.Thread(
            target=maintain_lease,
            name=f"board-lease-heartbeat-{operation_id}",
            daemon=True,
        )
        heartbeat.start()
        action = "CANCELLED"
        reconciliation_error: Optional[Exception] = None
        try:
            with tasks.board_lock(self.project_root):
                if self.event_store.is_board_command_active(
                    operation_id, delivery_lease_token
                ):
                    with tasks.guard_board_commit(approve_board_commit):
                        action = self._reconcile_v3_to_board_locked(
                            tasks=tasks,
                            board_task_id=board_task_id,
                            status=status,
                            operation_id=operation_id,
                            create_authorized=create_authorized,
                            create_title=create_title,
                            create_owner=create_owner,
                            v3_task_id=v3_task_id,
                            delta_authorized=delta_authorized,
                            delta_title=delta_title,
                            delta_owner=delta_owner,
                            delta_v3_task_id=delta_v3_task_id,
                        )
        except Exception as exc:
            reconciliation_error = exc
        finally:
            stop_heartbeat.set()
            heartbeat.join()
        if lease_lost.is_set():
            return "CANCELLED"
        if reconciliation_error is not None:
            raise reconciliation_error
        if not self.event_store.renew_board_command_lease(
            operation_id,
            delivery_lease_token,
            lease_seconds=lease_seconds,
        ):
            return "CANCELLED"
        return action

    def _reconcile_v3_to_board_locked(
        self,
        *,
        tasks: ModuleType,
        board_task_id: str,
        status: str,
        operation_id: str,
        create_authorized: bool,
        create_title: str,
        create_owner: str,
        v3_task_id: Optional[str],
        delta_authorized: bool,
        delta_title: str,
        delta_owner: str,
        delta_v3_task_id: Optional[str],
    ) -> str:
        """Apply one matrix action while the caller holds the board lock."""
        board_state, task = self._board_state(board_task_id, status)
        expected_note = BLOCK_NOTES.get(status, "")
        action = self.decide_action(
            status,
            board_state,
            create_authorized=create_authorized,
            delta_authorized=delta_authorized,
            block_note_convergent=bool(
                task and board_state == "blocked" and expected_note and task.get("stage") == expected_note
            ),
        )
        if action == "E":
            return action

        created_id: Optional[str] = None
        expected_v3_id: Optional[str] = None
        identity_title = ""
        identity_owner = ""
        reservation: Optional[Dict[str, Any]] = None
        if action == "CREATE":
            expected_v3_id = v3_task_id or board_task_id
            identity_title = create_title
            identity_owner = create_owner
        elif action in {"DELTA", "B+DELTA"}:
            if not delta_authorized:
                raise ValueError(f"{action} requires an authorized delta intent")
            expected_v3_id = delta_v3_task_id or f"DELTA:{operation_id}"
            identity_title = delta_title
            identity_owner = delta_owner
        if expected_v3_id is not None:
            # K1 (T-00001060) : l'id board est frappé ICI et réservé en MACHINE avant
            # tout texte, SEULEMENT pour une identité que rien ne porte encore : une
            # réservation (ou un lien) déjà là garde SON id, donc un rejeu n'alloue
            # rien et une copie sans `record_id.py` (M33) le rejoue encore.
            frappe = (
                tasks.record_id_module().mint("T")
                if self._identite_reservee_disponible(tasks)
                and not self._identite_deja_portee(expected_v3_id)
                else None
            )
            reservation = self.event_store.reserve_board_identity(
                expected_v3_id, operation_id, board_task_id=frappe
            )

        if action not in {"N", "NR"}:
            with tasks.suppress_sync(operation_id):
                if action == "U":
                    tasks.unblock_task(str(self.project_root), board_task_id)
                elif action in {"Sdev", "Scritic", "Stest"}:
                    tasks.stage_running_task(
                        str(self.project_root), board_task_id, STATUS_STAGE[status],
                        **self._acteur_si_accepte(tasks.stage_running_task),
                    )
                elif action == "D":
                    # LE MOTIF EST OBLIGATOIRE DEPUIS LE 2026-09-12, et la garde
                    # vit dans `set_state` plutôt que dans la CLI précisément
                    # pour que CE chemin ne l'esquive pas. Le pont ferme sur la
                    # foi d'un événement V3 : le motif NOMME cet événement, donc
                    # une clôture automatique reste rattachable à ce qui l'a
                    # décidée, comme une clôture faite à la main.
                    # ET LA DÉROGATION AU BINÔME EST STRUCTURELLE ICI, PAS UNE
                    # EXCEPTION (T-00000586, correctif du binôme de clôture). La
                    # garde qui exige `BINOME_MIN` critique(s) — un depuis S-00004500 — vit dans `set_state` pour la
                    # même raison que celle du motif — mais son échappatoire
                    # n'existait que dans `argparse`, donc ce chemin-ci se faisait
                    # refuser TOUTE clôture, sans issue : `sync-spec` échouait sur
                    # chaque statut terminal. Mesuré, pas raisonné.
                    # Aucun sous-agent critique ne tourne sur ce chemin — il n'y a
                    # pas de session, donc pas de `SubagentStop`, donc jamais de
                    # trace. Exiger la revue ici ne la ferait pas exister : ça ne
                    # ferait que casser le pont. On DÉROGE donc, et la dérogation
                    # atterrit dans le motif de clôture, visible au board comme
                    # celle d'un humain — jamais un silence.
                    # ET LA DÉROGATION À LA CIBLE EST STRUCTURELLE ICI DE LA MÊME
                    # FAÇON (T-00000654) : la garde de cible vit dans `set_state`
                    # pour que ce chemin ne l'esquive pas, mais le pont ferme sur
                    # la foi d'un événement V3 — il n'a ni plan approuvé à relire,
                    # ni étapes à annoter. Sans `sans_cible=`, une clôture pilotée
                    # par V3 sur un chantier armé se ferait refuser SANS ISSUE.
                    # La dérogation atterrit dans le motif, visible au board.
                    tasks.set_state(
                        str(self.project_root), board_task_id, "done",
                        stage=f"clos par le pont V3 — statut {status} (op {operation_id})",
                        sans_binome=(
                            "clôture automatique du pont V3 : aucun sous-agent "
                            "critique ne tourne sur ce chemin, donc aucune trace "
                            "de revue ne peut exister"
                        ),
                        sans_cible=(
                            "clôture automatique du pont V3 : aucun plan approuvé "
                            "à relire ni étape à annoter sur ce chemin"
                        ),
                        **self._acteur_si_accepte(tasks.set_state),
                    )
                elif action in {"B", "B+DELTA"}:
                    tasks.block_task(str(self.project_root), board_task_id, expected_note)
                    if action == "B+DELTA":
                        created_id = self._ensure_board_identity(
                            tasks=tasks,
                            reservation=reservation,
                            operation_id=operation_id,
                            v3_task_id=expected_v3_id,
                            title=identity_title,
                            owner=identity_owner,
                        )
                elif action == "CREATE":
                    created_id = self._ensure_board_identity(
                        tasks=tasks,
                        reservation=reservation,
                        operation_id=operation_id,
                        v3_task_id=expected_v3_id,
                        title=identity_title,
                        owner=identity_owner,
                    )
                elif action == "DELTA":
                    created_id = self._ensure_board_identity(
                        tasks=tasks,
                        reservation=reservation,
                        operation_id=operation_id,
                        v3_task_id=expected_v3_id,
                        title=identity_title,
                        owner=identity_owner,
                    )
                else:
                    raise ValueError(f"unimplemented board action: {action}")

        self._verify_reconciliation(
            action=action,
            operation_id=operation_id,
            board_task_id=board_task_id,
            status=status,
            expected_note=expected_note,
            created_id=created_id,
            expected_v3_id=expected_v3_id,
            creator_operation_id=(
                str(reservation["creator_operation_id"]) if reservation else None
            ),
        )
        return action

    def _ensure_board_identity(
        self,
        *,
        tasks: ModuleType,
        reservation: Optional[Dict[str, Any]],
        operation_id: str,
        v3_task_id: Optional[str],
        title: str,
        owner: str,
    ) -> str:
        """Resume one reserved creator and alias this delivery operation to it.

        TROIS BRANCHES DE CODE, QUATRE CAS (T-00001060) :
          * id réservé ET (réservation FINALISÉE OU `tasks.py` chargé sans la capacité) —
            `link_operation_to_task` rattache la clé créatrice par alias ; finalisée : la
            tâche et le lien existent (chemin d'avant) ; capacité absente : l'id réservé
            n'est PAS vérifié au texte (résidu nommé : pas de `create_linked_task` à
            paramètre `board_task_id`).
          * id réservé NON finalisé — la machine a parlé, le texte peut manquer (fenêtre
            inverse) ou porter la tâche sans sa clé créatrice (K1). DEUX ISSUES, AVANT
            toute écriture texte : (a) l'id porte DÉJÀ un lien machine — tombé, ou vers une
            AUTRE identité V3 ou une AUTRE op créatrice : un verbe humain dans la fenêtre
            K1 draine le sens Board → V3 et le réducteur y pose `BOARD:<op>` (tombé si ce
            verbe est une suppression) ⇒ ABANDON ; (b) sans lien, la suppression de l'id
            est EN VOL ⇒ REFUS. ADOPTER le lien est une décision du réducteur, non prise
            ici. Sinon `create_linked_task(board_task_id=…)` crée OU crédite sous CET id,
            puis `link_board_task` finalise ; `link_operation_to_task` ne touche l'id
            réservé qu'APRÈS cette confirmation.
          * réservation SANS id (antérieure à T-00001060) — chemin d'avant, par la clé
            créatrice du texte (résidu nommé).

        (a) L'ABANDON (décision pilote S-01M4KHNE8597YSZ4YY54YVWFDZ, option b ; lecture
        S-01M4PR7RE7EQ940STQ6V6WRCX4 : lien tombé d'une suppression DRAINÉE, et lien vers
        une identité non `BOARD:`, une anomalie, compris) lève `CreationAbandonnee` ; le
        drain ACQUITTE la commande, l'ACK porte `abandon` (décision, identité V3, id, op
        créatrice, lien trouvé, `lien_tombe` s'il est tombé), et les commandes suivantes
        sont livrées. X reste à l'humain, jamais recréé ; la réservation reste NON
        finalisée sous X : l'identité V3 ORPHELINE n'est nommée que par la trace. Un rejeu
        de création de la même identité relit la même réservation et est ré-abandonné,
        jamais une seconde tâche — BORNE : tant que la base machine vit ; une
        reconstruction depuis `runs/` rebâtit l'ACK porteur d'abandon mais ni l'outbox ni
        la réservation (BK-105) ; une nouvelle création crée alors une seconde tâche —
        résidu hérité de T-00001060, identique à la BASE. L'adoption du lien est
        T-01M4KHNEQG8R0ADG7MQEYZD6H6. RÉSIDU NOMMÉ (B+DELTA) : l'abandon survient APRÈS
        `block_task` ; l'ACK acquitte le blocage sans la post-condition de
        `_verify_reconciliation` (écrit dans la même section sous verrou).

        (b) LE REFUS EST UNE LEVÉE (réserve C7), comme celui de `create_linked_task` sur
        une clé tombée : la commande est relâchée, `BOARD_COMMAND_FAILED` est tracé, et
        elle RESTE en tête de la FIFO SQLite — un POISON qui retient les commandes
        suivantes. Il n'est levé que par une commande de remplacement qui N'EST PAS une
        création autorisée de la même identité V3 (`create_authorized=False` ⇒ NR,
        acquittée) ; une création de remplacement (`supersedes_operation_id=…`) relit la
        même réservation et retombe en tête (mesuré). AUCUN verbe ne pose aujourd'hui ce
        remplacement. Le poison ne dure que tant que la suppression reste EN VOL :
        drainée, elle pose le lien tombé et la reprise suivante ABANDONNE (a). CAPACITÉ
        PERDUE, nommée, dans les deux issues : la réservation reste, et cette identité V3
        n'aura plus de tâche board."""
        if reservation is None or v3_task_id is None:
            raise RuntimeError("board creation requires a reserved V3 identity")
        creator_operation_id = str(reservation["creator_operation_id"])
        reserved_board_task_id = reservation.get("board_task_id")
        if reserved_board_task_id and (
            reservation.get("finalized_at") or not self._identite_reservee_disponible(tasks)
        ):
            created_id = str(reserved_board_task_id)
            tasks.link_operation_to_task(
                str(self.project_root), created_id, creator_operation_id
            )
        elif reserved_board_task_id:
            created_id = str(reserved_board_task_id)
            link = self.event_store.get_board_link(created_id)
            if link and (
                int(link["tombstoned"])
                or link["v3_task_id"] != v3_task_id
                or link["create_operation_id"] != creator_operation_id
            ):
                trace: Dict[str, Any] = {
                    "decision": "S-01M4KHNE8597YSZ4YY54YVWFDZ",
                    "v3_task_id": v3_task_id,
                    "board_task_id": created_id,
                    "creator_operation_id": creator_operation_id,
                    "lien_v3_task_id": link["v3_task_id"],
                    "lien_create_operation_id": link["create_operation_id"],
                }
                if int(link["tombstoned"]):
                    trace["lien_tombe"] = True
                raise CreationAbandonnee(
                    f"reserved board identity {created_id} is already linked to "
                    f"{link['v3_task_id']} by {link['create_operation_id']}"
                    f"{' (tombstoned)' if int(link['tombstoned']) else ''}; creation of "
                    f"{v3_task_id} ABANDONED, {created_id} stays with the human",
                    trace,
                )
            if created_id in self._suppressions_en_vol(self._board_data()):
                raise RuntimeError(
                    f"reserved board identity {created_id} is deleted in flight; "
                    "refusing resurrection (command stays FAILED at the FIFO head)"
                )
            created_id = tasks.create_linked_task(
                str(self.project_root), title, owner, creator_operation_id,
                board_task_id=created_id,
            )
            self.event_store.link_board_task(
                created_id, v3_task_id, creator_operation_id
            )
        else:
            created_id = tasks.create_linked_task(
                str(self.project_root), title, owner, creator_operation_id
            )
            self.event_store.link_board_task(
                created_id, v3_task_id, creator_operation_id
            )
        tasks.link_operation_to_task(str(self.project_root), created_id, operation_id)
        return created_id

    @staticmethod
    def _acteur_si_accepte(ecrivain: Any) -> Dict[str, Any]:
        """``{"acteur": acteur_pont_v3()}`` si l'écrivain du ``tasks.py`` RÉSOLU (``_tasks_module`` :
        celui du projet, sinon celui du dépôt) accepte ``acteur=`` ; ``{}`` pour une copie d'avant
        le lot A, dont l'écriture reste celle d'avant — jamais un ``TypeError`` qui casse le pont."""
        try:
            accepte = "acteur" in inspect.signature(ecrivain).parameters
        except (TypeError, ValueError):
            accepte = False
        return {"acteur": acteur_pont_v3()} if accepte else {}

    @staticmethod
    def _identite_reservee_disponible(tasks: ModuleType) -> bool:
        """Vrai si le `tasks.py` chargé sait frapper un id (`record_id_module`) ET créer
        sous un id donné (`create_linked_task(board_task_id=…)`). Faux : chemin d'avant."""
        if getattr(tasks, "record_id_module", None) is None:
            return False
        try:
            return "board_task_id" in inspect.signature(tasks.create_linked_task).parameters
        except (AttributeError, TypeError, ValueError):
            return False

    def _identite_deja_portee(self, v3_task_id: str) -> bool:
        """Vrai si une réservation OU un lien porte déjà `v3_task_id` :
        `reserve_board_identity` ignore alors l'id passé (INSERT OR IGNORE ; un lien
        donne une réservation finalisée sous SON id), il n'y a rien à frapper. Aucune
        fenêtre nuisible : une réservation n'est jamais supprimée, et un id frappé en
        trop est ignoré par l'INSERT OR IGNORE."""
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM board_identity_reservations WHERE v3_task_id=? "
                "UNION ALL SELECT 1 FROM task_board_mapping WHERE v3_task_id=? LIMIT 1",
                (v3_task_id, v3_task_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _verify_reconciliation(
        self,
        *,
        action: str,
        operation_id: str,
        board_task_id: str,
        status: str,
        expected_note: str,
        created_id: Optional[str],
        expected_v3_id: Optional[str],
        creator_operation_id: Optional[str],
    ) -> None:
        """Reread exact state/correlation/mapping before an ACK is possible."""
        data = self._board_data()
        tasks_by_id = {task["id"]: task for task in data.get("tasks", [])}
        if action in {"CREATE", "DELTA"} or (action == "B+DELTA" and created_id):
            if created_id is None or expected_v3_id is None or created_id not in tasks_by_id:
                raise RuntimeError(f"{action} effect is missing after board reread")
            correlations = data.get("sync_correlations", {})
            expected_correlation = {
                "board_task_id": created_id,
                "tombstoned": False,
            }
            correlation_ids = {operation_id, creator_operation_id}
            if any(
                correlation_id is None
                or correlations.get(correlation_id) != expected_correlation
                for correlation_id in correlation_ids
            ):
                raise RuntimeError(f"{action} correlation mismatch after board reread")
            link = self.event_store.get_board_link(created_id)
            if not link or (
                link["v3_task_id"] != expected_v3_id
                or link["create_operation_id"] != creator_operation_id
                or int(link["tombstoned"]) != 0
            ):
                raise RuntimeError(f"{action} mapping mismatch after board reread")

        if action in {"CREATE", "DELTA"}:
            return
        if action == "NR":
            reread_state, _ = self._board_state(board_task_id, status)
            if reread_state not in {"ABSENT_NEVER_LINKED", "TOMBSTONED"}:
                raise RuntimeError("non-resurrection target appeared before ACK")
            return
        task = tasks_by_id.get(board_task_id)
        if task is None:
            raise RuntimeError(f"{action} target disappeared before ACK")
        # APPARTENANCE, plus égalité (T-01M5F728RH) : plusieurs tâches peuvent être running
        # à la fois depuis le lot A ; la cible doit être UNE d'elles, pas la seule. `task` est
        # lue dans ce même `data` : son état `running` SUFFIT, aucune comparaison aux autres.
        expected = {
            "N": lambda: self.decide_action(
                status,
                self._board_state(board_task_id, status)[0],
                block_note_convergent=bool(expected_note and task.get("stage") == expected_note),
            )
            == "N",
            "U": lambda: task["state"] == "pending" and not task.get("stage"),
            "Sdev": lambda: task["state"] == "running" and task.get("stage") == STATUS_STAGE[status],
            "Scritic": lambda: task["state"] == "running" and task.get("stage") == STATUS_STAGE[status],
            "Stest": lambda: task["state"] == "running" and task.get("stage") == STATUS_STAGE[status],
            # `D` ATTENDAIT UN `stage` VIDE, et ce n'est plus vrai depuis le
            # 2026-09-12 : le motif de clôture est OBLIGATOIRE et c'est
            # précisément dans `stage` qu'il atterrit, où il remplace l'étape en
            # vol — une tâche close n'en a plus. La post-condition ne se contente
            # donc pas d'accepter un champ non vide : elle exige que le motif
            # NOMME le pont, sans quoi elle validerait une clôture écrite par
            # quelqu'un d'autre entre la commande et la relecture.
            "D": lambda: task["state"] == "done" and "pont V3" in (task.get("stage") or ""),
            "B": lambda: task["state"] == "blocked" and task.get("stage") == expected_note,
            "B+DELTA": lambda: task["state"] == "blocked" and task.get("stage") == expected_note,
        }
        predicate = expected.get(action)
        if predicate is None or not predicate():
            raise RuntimeError(f"{action} effect diverged before ACK")

    def _drain_board_backlog(self) -> bool:
        """Drain every durable Board intent before accepting a V3 command.

        The backlog includes the spill file (T-00001006): while it exists, older
        Board intents wait outside ``sync_outbox``, so the backlog is not drained.
        A ``tasks.py`` without ``_chemin_deverse`` predates the spill file."""
        tasks = self._tasks_module()
        try:
            tasks.drain_sync_outbox(self.project_root, self.consume_board_intent)
            chemin_deverse = getattr(tasks, "_chemin_deverse", None)
            with tasks.board_lock(self.project_root):
                deverse = chemin_deverse(self.project_root) if chemin_deverse is not None else None
                return not bool(tasks.load(self.project_root).get("sync_outbox")) and not (
                    deverse is not None and (deverse.exists() or deverse.is_symlink())
                )
        except Exception:
            return False

    def request_v3_to_board(
        self,
        operation_id: str,
        board_task_id: str,
        status: str,
        *,
        supersedes_operation_id: Optional[str] = None,
        **options: Any,
    ) -> bool:
        """Enqueue one V3 → board command, then drain. `True` = commande TERMINALE
        (acquittée), abandon compris : l'ACK porte alors `abandon` et aucune tâche board
        n'est créée (S-01M4KHNE8597YSZ4YY54YVWFDZ). `False` = backlog Board → V3 non
        drainé, ou commande non acquittée (relâchée, ou en vol)."""
        if not self._drain_board_backlog():
            return False
        payload = {"board_task_id": board_task_id, "status": status, **options}
        tasks = self._tasks_module()
        with tasks.board_lock(self.project_root):
            self.event_store.enqueue_board_command(
                operation_id,
                EventType.BOARD_COMMAND_REQUESTED,
                payload,
                supersedes_operation_id=supersedes_operation_id,
            )
        self.drain_board_commands()
        return self.event_store.is_board_command_acked(operation_id)

    def drain_board_commands(self) -> int:
        worker = f"BoardBridge:{uuid.uuid4()}"
        drained = 0
        while True:
            command = self.event_store.claim_board_command(worker)
            if command is None:
                break
            operation_id = str(command["operation_id"])
            payload = json.loads(command["payload_json"])
            lease_token = str(command["lease_token"])
            lease_seconds = max(
                float(command["lease_expires_at"]) - time.time(),
                0.004,
            )
            try:
                ack_payload = payload
                try:
                    action = self.reconcile_v3_to_board(
                        operation_id=operation_id,
                        delivery_lease_token=lease_token,
                        delivery_lease_seconds=lease_seconds,
                        **payload,
                    )
                except CreationAbandonnee as abandon:
                    # S-01M4KHNE8597YSZ4YY54YVWFDZ (b) : commande TERMINALE, rien d'écrit au
                    # texte ; l'ACK COMMUN ci-dessous la trace (bail perdu ⇒ CANCELLED avant).
                    action = "ABANDON"
                    ack_payload = {**payload, "abandon": abandon.trace}
                if action == "CANCELLED":
                    continue
                if action == "E":
                    error = "board/V3 divergence requires an explicit delta"
                    self.event_store.release_board_command(operation_id, lease_token, error)
                    self.event_store.append_event(
                        task_id=str(payload["board_task_id"]),
                        agent_role="BoardBridge",
                        event_type=EventType.BOARD_COMMAND_FAILED,
                        payload={**payload, "error": error},
                        operation_id=operation_id,
                        attempt=int(command["attempt"]),
                        event_kind=EventType.BOARD_COMMAND_FAILED.value,
                    )
                    break
                if self.event_store.ack_board_command_with_event(
                    operation_id, lease_token, ack_payload
                ):
                    drained += 1
                else:
                    break
            except Exception as exc:
                self.event_store.release_board_command(
                    operation_id, lease_token, str(exc)
                )
                self.event_store.append_event(
                    task_id=str(payload.get("board_task_id", "BOARD-UNKNOWN")),
                    agent_role="BoardBridge",
                    event_type=EventType.BOARD_COMMAND_FAILED,
                    payload={**payload, "error": str(exc)},
                    operation_id=operation_id,
                    attempt=int(command["attempt"]),
                    event_kind=EventType.BOARD_COMMAND_FAILED.value,
                )
                break
        return drained

    # T-00001060 (étape 5, S-00003372) : les trois corrélations du KIT qui n'existaient
    # qu'en TEXTE. Chez un adoptant ces ids nomment d'autres tâches : chaque cas COMPARE
    # puis REMPLACE, sinon `sans objet` ; sans `.agents/IS_THE_KIT`, rien (réserve C10).
    _MIGRATION_T571 = ("T-00000571", "ed8cf3e0-4684-4572-a170-424dd55d85fb")
    _MIGRATION_T572 = ("T-00000572", "7ffd64ba-41de-490e-821b-a292e365cbcc")
    _MIGRATION_T573 = (
        "T-00000573",
        "a1eceddf-5849-4727-b14e-0ef6324b233b",  # clé TEXTE d'un DELTA, sans événement
        "d6c40430-dfae-438c-a4cf-82f54899c9f3",  # créateur MACHINE, exporté dans runs/
    )

    def migrer_correlations_texte_seules(self) -> Dict[str, str]:
        """Porte en MACHINE les corrélations du kit que seul le texte connaît, sous
        `tasks.board_lock`, et rend un verdict par tâche : `posé`, `déjà migrée`, `sans
        objet` ou `divergente`. Geste G-DONNÉES de l'orchestrateur, jamais un verbe.

          * T-571 — texte `ed8cf3e0 == {T-571, vivante}`, tâche présente, AUCUN lien
            machine ⇒ intent de création (`before=None`, `operation_id=ed8cf3e0`, `after`
            = instantané courant) ;
          * T-572 — texte `7ffd64ba == {T-572, tombée}`, tâche absente, aucun lien ⇒
            intent de création sous `7ffd64ba` (instantané `pending` aux champs vides :
            aucun instantané n'a été commité, le titre n'est pas inventé) PUIS intent de
            suppression, dans le MÊME `save` ;
          * T-573 — texte `a1eceddf == {T-573, vivante}` EXACTEMENT, `d6c40430` absent du
            texte, lien machine créé par `d6c40430` ⇒ la clé texte est RÉALIGNÉE sur
            `d6c40430`, `a1eceddf` retirée.
        Un lien machine déjà présent rend `déjà migrée` (sous l'opération attendue) ou
        `divergente` (sous une autre), et RIEN n'est écrit : ré-enqueuer un instantané
        changé lèverait `operation identity mismatch` et bloquerait la FIFO. Refus
        (`RuntimeError`) si l'outbox n'est pas vide ou si un déversement existe :
        `tasks.py replay-sync` d'abord."""
        t571, op571 = self._MIGRATION_T571
        t572, op572 = self._MIGRATION_T572
        t573, op573_texte, op573_machine = self._MIGRATION_T573
        if not (self.project_root / ".agents" / "IS_THE_KIT").is_file():
            return {t571: "sans objet", t572: "sans objet", t573: "sans objet"}
        tasks = self._tasks_module()
        verdicts: Dict[str, str] = {}

        def deja_lie(board_task_id: str, operation_id: str) -> Optional[str]:
            link = self.event_store.get_board_link(board_task_id)
            if link is None:
                return None
            return "déjà migrée" if link["create_operation_id"] == operation_id else "divergente"

        def enqueue(data: Dict[str, Any], board_task_id: str, before: Any, after: Any, **op: str) -> None:
            emis = tasks.enqueue_sync_intent(data, board_task_id, before, after, **op)
            if op and emis != op["operation_id"]:
                raise RuntimeError(f"intent of {board_task_id} suppressed; migration not written")

        with tasks.board_lock(self.project_root):
            data = tasks.load(self.project_root)
            chemin_deverse = getattr(tasks, "_chemin_deverse", None)
            deverse = chemin_deverse(self.project_root) if chemin_deverse is not None else None
            if data.get("sync_outbox") or (
                deverse is not None and (deverse.exists() or deverse.is_symlink())
            ):
                raise RuntimeError(
                    "text-only correlation migration refused: sync_outbox or spill file not "
                    "empty — run `tasks.py replay-sync` d'abord"
                )
            correlations = data.setdefault("sync_correlations", {})
            presentes = {task["id"]: task for task in data.get("tasks", [])}
            ecrire = False

            if correlations.get(op571) != {"board_task_id": t571, "tombstoned": False}:
                verdicts[t571] = "sans objet"
            elif (lie := deja_lie(t571, op571)) is not None:
                verdicts[t571] = lie
            elif t571 not in presentes:
                verdicts[t571] = "divergente"
            else:
                enqueue(data, t571, None, presentes[t571], operation_id=op571)
                verdicts[t571], ecrire = "posé", True

            if correlations.get(op572) != {"board_task_id": t572, "tombstoned": True}:
                verdicts[t572] = "sans objet"
            elif (lie := deja_lie(t572, op572)) is not None:
                verdicts[t572] = lie
            elif t572 in presentes:
                verdicts[t572] = "divergente"
            else:
                instantane = tasks.canonical_task_snapshot({"id": t572, "state": "pending"})
                enqueue(data, t572, None, instantane, operation_id=op572)
                enqueue(data, t572, instantane, None)
                verdicts[t572], ecrire = "posé", True

            vivante = {"board_task_id": t573, "tombstoned": False}
            cree_par_machine = deja_lie(t573, op573_machine) == "déjà migrée"
            if (
                cree_par_machine
                and correlations.get(op573_texte) == vivante
                and op573_machine not in correlations
            ):
                correlations[op573_machine] = dict(vivante)
                del correlations[op573_texte]
                verdicts[t573], ecrire = "posé", True
            elif (
                cree_par_machine
                and op573_texte not in correlations
                and correlations.get(op573_machine) == vivante
            ):
                verdicts[t573] = "déjà migrée"
            else:
                verdicts[t573] = "sans objet"

            if ecrire:
                tasks.save(self.project_root, data)
        return verdicts

    def _tasks_module(self) -> ModuleType:
        if self._tasks_module_cache is not None:
            return self._tasks_module_cache
        project_candidate = self.project_root / ".agents" / "bin" / "tasks.py"
        repository_candidate = run_export._racine_depot() / ".agents" / "bin" / "tasks.py"
        path = project_candidate if project_candidate.exists() else repository_candidate
        spec = importlib.util.spec_from_file_location("agentic_v3_board_tasks", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot import tasks.py from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._tasks_module_cache = module
        return module
