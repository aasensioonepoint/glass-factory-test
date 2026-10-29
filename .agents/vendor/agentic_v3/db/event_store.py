"""
EventStore: SQLite Event Sourcing Manager & Task Projection Engine.
All mutations are recorded as immutable events; task state is projected dynamically.
"""

import contextlib
import datetime
import importlib.util
import json
import os
import secrets
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import (
    Any, Dict, Iterable, Iterator, List, NamedTuple, Optional, Set, Tuple, Union,
)
from agentic_v3.db.schema import get_db_connection, create_tables, DEFAULT_DB_PATH
from agentic_v3.db import event_store_sync, run_export
from agentic_v3.db.event_store_annonces import AnnoncesRunsMixin, _SONDE_RUNS_MAX_OCTETS
from agentic_v3.models.events import EventType

# --- T-00000641 : RÉDACTION DES SECRETS À L'ÉCRITURE (couture d'import) -------
# `redaction.py` (invariant « aucun secret au ledger ») est résolu PARESSEUSEMENT,
# à la PREMIÈRE écriture — jamais au niveau module : un échec à l'import tuerait le
# fichier ENTIER (et tout ce qui importe `EventStore`).
#
# DÉCISION PILOTE S-00001655 — résolution à DEUX BRANCHES :
#   (1) le PAQUET INSTALLÉ `cadre.ledger.redaction` (jamais un doublon embarqué) ;
#   (2) À DÉFAUT SEULEMENT, le chargeur PAR CHEMIN ci-dessous — REPLI DÉCLARÉ, à
#       retirer le jour où (1) est garanti.
# Depuis vendor 5/5, (1) ne joue que si `run_export._cadre_d_ici()` tient (le `cadre`
# du kit DÉJÀ chargé, ou aucun paquet sous le kit) ; sinon (2), jamais un import
# d'abord (S-01M5CN1KM2). `_CHEMIN_REDACTION` est un
# GLOBAL et (1) est isolée dans `_importer_redaction_paquet` — les deux sont
# monkeypatchables (T16, banc de sélection de branche).
#
# POSTURE DU STORE DU RUN — FAIL-CLOSED (distincte du spool `events.py`, qui est
# fail-OPEN) : si AUCUNE branche n'aboutit, l'écriture LÈVE un `RuntimeError`
# nommant le chemin manquant — un store du run qui ne peut pas rédiger n'écrit pas.
# Conséquence MESURÉE (T16, B-1) : les deux branches en échec ⇒ toute écriture V3
# lève ; `tasks.py` ne TOMBE PAS pour autant — `drain_sync_outbox` attrape ce
# `RuntimeError`, relâche le bail, l'annonce sur stderr et suspend le miroir
# board->V3 (rc inchangé). BORNE ADOPTANT : hors clone du kit et sans paquet
# installé, l'écriture V3 est refusée (fail-closed).
_CHEMIN_REDACTION = (
    run_export._dossier_cadre() / "ledger" / "redaction.py"
)
_REDACTION: Any = None  # None = pas encore chargé (un chargement RÉUSSI est mémoïsé)


def _importer_redaction_paquet() -> Any:
    """Branche (1), S-00001655 : le PAQUET, si sa provenance tient (`run_export._cadre_d_ici`, S-01M5CN1KM2)."""
    if not run_export._cadre_d_ici():
        raise ImportError("`cadre` d'un autre arbre ou non chargé : (2) par chemin")
    return importlib.import_module("cadre.ledger.redaction")


def _redaction() -> Any:
    """Le module `redaction`, mémoïsé, en DEUX branches (S-00001655) : (1) le
    paquet installé, puis (2) — à défaut SEULEMENT — le chargeur par chemin (repli
    déclaré). LÈVE un `RuntimeError` nommant `_CHEMIN_REDACTION` si les DEUX
    échouent (posture fail-closed du store du run) — l'appeler EST le point
    d'écriture qui refuse de fuir."""
    global _REDACTION
    if _REDACTION is None:
        try:
            _REDACTION = _importer_redaction_paquet()  # (1) paquet installé
        except Exception:
            try:
                spec = importlib.util.spec_from_file_location(
                    "_cadre_redaction_v3", _CHEMIN_REDACTION
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                _REDACTION = module  # (2) repli PAR CHEMIN, déclaré
            except Exception as exc:
                raise RuntimeError(
                    "redaction indisponible (paquet ET chemin), ecriture V3 refusee "
                    f"(fail-closed) : {_CHEMIN_REDACTION}"
                ) from exc
    return _REDACTION


class RunStep(NamedTuple):
    """One operation of a run: an idempotent event keyed by its durable identity.

    A « run » is an ORDERED sequence of RunStep applied to the V3 store's
    ``events_ledger``. Each step carries an ``operation_id`` so that its identity
    ``(operation_id, event_kind, attempt)`` is unique in the ledger
    (index ``uq_events_operation_attempt``): re-applying the SAME step is a no-op,
    which is exactly what makes a run replayable from the start after an
    interruption at any step.
    """

    operation_id: str
    task_id: str
    agent_role: str
    event_type: Union[EventType, str]
    payload: Dict[str, Any]
    event_kind: Optional[str] = None
    attempt: int = 0
    ulid: Optional[str] = None
    predecesseur_ulid: Optional[str] = None


#: Les champs qu'un objet d'export DOIT porter comme CHAÎNE pour traverser
#: l'écrivain unique — un `.jsonl` fusionnable entre contributeurs peut porter une
#: ligne bien formée mais absurde (BLOQUANT 2 du binôme).
_CHAMPS_RECONSTRUCTION = ("task_id", "agent_role", "event_type", "payload_json")

#: T-00000691 : les `event_kind` d'INTENT board (`tasks.py` -> `consume_board_intent`),
#: rejoués par `_rebatir_pont`. Les `BOARD_COMMAND_*` sont des EFFETS (demande,
#: acquittement, échec), jamais réduits : les rejouer comme intents inventerait des
#: transitions que le board n'a jamais demandées.
_KINDS_INTENT_BOARD = (
    EventType.BOARD_TASK_OBSERVED.value,
    EventType.BOARD_RUNNING_REPLACED.value,
)

#: T-00000691 (S-00002460) : borne PAR FICHIER de la lecture de `runs/`. Un fichier
#: plus gros est SAUTÉ sans être ouvert, compté (`fichiers_trop_gros`) et nommé avec
#: son remède. ≈ 15 × le plus gros fichier mesuré le 2026-09-26 (4 347 188 o, un
#: fichier de BACKFILL ; les fichiers par auteur font 0,35-0,55 MiB/mois) : aucun
#: fichier légitime actuel n'est sauté.
#: COÛT MÉMOIRE — MESURÉ, ET CORRIGÉ (S-00002518 F6) : la première rédaction disait
#: « ≈ 2 à 3 × la borne, de l'ordre de 200 MiB ». Mesuré par critic-opus le
#: 2026-09-26 @ c6af0253 : un fichier de 62 MiB coûte 242 MiB TRACÉS (tracemalloc)
#: et +313 MiB de RSS — soit 4 à 5 × ce qui est lu (octets bruts, lignes issues de
#: `split`, lignes décodées, et surtout les OBJETS PARSÉS, gardés jusqu'au tri) ; le
#: `runs/` réel (7,3 MiB) coûte 31 MiB tracés. REMESURÉ après la lecture par
#: descripteur de la passe de revue, `_lire_exports` SEUL : 62,2 MiB → pic 242 MiB
#: tracés (117 MiB retenus), +314 MiB de RSS — le chiffre tient ; `runs/` réel
#: 7,3 MiB → pic 16 MiB tracés, +30 MiB de RSS (le 31 MiB du binôme n'est pas
#: reproduit par la lecture seule : périmètre de mesure différent, non recoupé).
#: Un fichier À la borne coûte donc de l'ordre de 250 à 320 MiB, pas 200. CE
#: QU'ELLE NE BORNE PAS : le TOTAL lu vaut
#: N × 64 MiB, NON borné en N — les objets parsés de TOUS les fichiers restent en
#: mémoire jusqu'au tri de fusion `(ulid, auteur/copie)`, qui exige un tri GLOBAL.
#: Un `runs/` dont l'ensemble parsé dépasse la RAM n'est pas reconstructible par ce
#: code (`MemoryError` ⇒ AVORTÉE ; un OOM-kill noyau, lui, n'est attrapable par
#: personne). Il faudrait une lecture streamée + un tri externe — suite NOMMÉE,
#: ouverte seulement si le cas apparaît (total mesuré ≈ 7,3 MiB).
_TAILLE_FICHIER_MAX_OCTETS = 64 * 1024 * 1024

#: Au plus N chemins nommés par catégorie dans une annonce (« et N autres » au-delà).
_CHEMINS_ANNONCES_MAX = 5

#: T-01M4N496YD7BZDA2NHYQ73JND9 : au plus N ULID divergents NOMMES (`divergentes_ulid`) - la MEME borne que
#: `run_export.re_exporter_frappees` pour la MEME cle (`divergentes[:20]`).
_DIVERGENTES_NOMMEES_MAX = 20

#: Erreurs SQLite qu'une DONNÉE hostile suffit à provoquer au rejeu d'un intent
#: (mesuré 2026-09-26 : `after.owner` = `{}` ou `[]` fusionné sous `runs/` ⇒
#: `sqlite3.ProgrammingError: Error binding parameter 4: type 'dict' is not
#: supported` dans `_reduce_board_intent`) — comptées `pont_ecartes`, jamais un
#: avortement : une ligne fusionnable ne doit pas bloquer l'historique de tous.
#: Toute AUTRE `sqlite3.Error` (E/S, disque plein, base corrompue, verrou) est une
#: panne SYSTÈME et remonte au filet R (voir `_rebatir_pont`).
_ERREURS_SQLITE_DE_DONNEES = (
    sqlite3.IntegrityError,
    sqlite3.ProgrammingError,
    sqlite3.InterfaceError,
    sqlite3.DataError,
)


def _est_panne_systeme(exc: BaseException) -> bool:
    """Vrai pour une panne SYSTÈME — `sqlite3.Error` hors `_ERREURS_SQLITE_DE_DONNEES`
    (E/S, disque plein, base corrompue, verrou) ou `MemoryError` — qui AVORTE la
    reconstruction (filet R) ; faux pour une erreur qu'une DONNÉE suffit à
    provoquer, comptée par ligne ou par intent. UNE classification pour la phase 1
    (`_appliquer_lignes`, S-00002560) ET le pont (`_rebatir_pont`, addendum
    exec-critic), maintenue par S-00002547."""
    return isinstance(exc, (sqlite3.Error, MemoryError)) and not isinstance(
        exc, _ERREURS_SQLITE_DE_DONNEES
    )


def _contrainte_unique(exc: BaseException) -> bool:
    """C5 (NO_GO it. 4) : seule une `IntegrityError` d'UNICITE reste hors des `echecs` ; un NOT NULL de
    projection (`req_id` ou `spec_version` nuls) est un echec de DONNEE, compte et annonce. Deux cas d'unicite :
    ULID deja en base => deja present, idempotent ; identite durable `(operation_id, event_kind, attempt)` deja
    prise sous un AUTRE ULID => identite deja prise : ecartee sans bruit, contenu non compare (borne de portee du
    plan : `evenements=1/2`, `echecs` 0, ULID non nomme, et la sonde ne la compte pas - defaut preexistant).

    Reserve 4 (it. 5) : `sqlite_errorname` n'existe que sous Python >= 3.11 et rien ne le garde a l'execution -
    sous un Python plus ancien `getattr` rend "" : toute collision d'unicite est alors comptee `echecs` et
    annoncee (bruyant, jamais muet ; T65 rougit). Plancher declare : `pyproject.toml`, `requires-python >= 3.11`.
    `SQLITE_CONSTRAINT_PRIMARYKEY` n'est PAS dans la liste : inatteignable ici (`event_id` AUTOINCREMENT, jamais
    fourni par l'ecrivain ; `task_projections` ecrite en upsert `ON CONFLICT(task_id)`) - s'il survenait, il
    serait compte `echecs`, donc annonce."""
    return getattr(exc, "sqlite_errorname", "") == "SQLITE_CONSTRAINT_UNIQUE"


def _parcourir_runs(
    racine: Path, refuses: List[Path], erreurs: List[Tuple[Path, OSError]]
) -> Iterator[Path]:
    """Les exports candidats de `runs/`, SANS JAMAIS SUIVRE DE LIEN (S-00002509) —
    délègue à `run_export.parcourir_runs`, l'implémentation UNIQUE partagée avec
    l'écrivain et `mesurer_runs` (T-00000691, passe 3). Liens ⇒ `refuses`, dossiers
    illisibles ⇒ `erreurs` ; aux appelants de trancher : la lecture COMPTE les
    deux, la sonde lève la première erreur quand rien d'autre ne rend la
    reconstruction due."""
    return run_export.parcourir_runs(racine, refuses, erreurs)


def _lire_export_sans_lien(chemin: Path) -> Tuple[str, Optional[bytearray]]:
    """Lit UN export sans lien (symbolique ou PHYSIQUE, S-00002550) ni au-delà de
    `_TAILLE_FICHIER_MAX_OCTETS` — délègue à `run_export.lire_export_sans_lien`
    (`lstat`, `O_NOFOLLOW`, `fstat` sur le descripteur, lecture depuis lui)."""
    return run_export.lire_export_sans_lien(chemin, _TAILLE_FICHIER_MAX_OCTETS)


class ReconstructionAvorteeError(Exception):
    """T-00000691 (S-00002372) : écriture V3 REFUSÉE sur une instance dont la
    reconstruction automatique était DUE et n'a pas été commitée — AVORTÉE,
    DIFFÉRÉE (rédaction indisponible) ou NON TENTÉE (sonde en échec). Écrire
    rendrait la base NON vide, donc jamais plus reconstruite d'office
    (S-00002370) : l'historique de `runs/` serait perdu en silence pour ce clone.

    Hérite d'`Exception` et NON de `RuntimeError`, à dessein :
    `tasks.py::drain_sync_outbox` range alors l'échec dans sa branche « echec
    inattendu du consumer, intent NON acquitte (rejeu au prochain drain) », relâche
    le bail et s'arrête — l'intent reste dans l'outbox de `TASKS.json` et sera
    rejoué par la première construction qui réussit la reconstruction."""


def _obj_reconstruction_valide(obj: Dict[str, Any]) -> bool:
    """Filtre de forme conservé comme couture patchable des anciens appelants."""
    return event_store_sync.obj_reconstruction_valide(obj)


class EventStore(AnnoncesRunsMixin):
    """Manages immutable event insertion and task projection updates."""

    def __init__(
        self,
        db_path: Union[str, Path, None] = None,
        *,
        project_root: Union[str, Path, None] = None,
    ) -> None:
        # T-00000691 (S-00002372) : PREMIÈRE instruction. Levé tant qu'une
        # reconstruction automatique DUE n'a pas été commitée sur CETTE instance
        # (AVORTEE, DIFFEREE, NON TENTEE) : elle n'écrit alors RIEN — ni événement,
        # ni lien, ni réservation, ni rejeu de journal — pour que la construction
        # suivante retente réellement sur une base encore VIDE.
        self._reconstruction_bloquee = False
        self._cause_reconstruction: Optional[str] = None
        self._remede_particulier: Optional[str] = None  # remède propre à la cause
        self._auto_sync_result: Optional[Dict[str, Any]] = None
        # T-00000650 : la racine du dépôt sert (1) la partition MACHINE de la base
        # (`DEFAULT_DB_PATH`) et (2) la racine de l'export `runs/`. `None` la
        # résout par `cadre.paths.project_root()` (variable `CADRE_PROJECT_ROOT`,
        # sinon racine git). C'est la clause de TEST-ISOLATION (B-C2) : un banc qui
        # pose `CADRE_PROJECT_ROOT` ET `CADRE_STATE_DIR` n'écrit rien hors fixture.
        self.project_root = (
            Path(project_root) if project_root is not None else run_export.project_root()
        )
        self.db_path = (
            Path(db_path) if db_path is not None else DEFAULT_DB_PATH(self.project_root)
        )
        # T-00000692 (S-00002199 options C+D), ORDRE IMPOSÉ en trois temps :
        # (i) AVANT `create_tables`, sonder si la partition EXISTAIT — seulement
        #     quand `db_path` est EXACTEMENT `state_project(root)/run/v3_event_
        #     store.db` (cas de `BoardBridge` et du défaut) ; une base explicite
        #     ailleurs, ou une partition non résoluble, ne marque rien et reste
        #     muette (`_partition_marquable` rend `None`) ;
        # (ii) `create_tables` crée le dossier, comme avant ;
        # (iii) APRÈS lui — l'écrivain ne crée pas le dossier, et lui faire créer
        #     ajouterait un neuvième créateur — poser le marqueur (`naissance` si le
        #     dossier vient de naître, `adoption` sinon), puis relever (à la
        #     naissance, et à chaque APPARITION d'une sœur depuis le dernier relevé
        #     — S-00002240, signal répété jusqu'à acquittement ou disparition) et
        #     signaler les partitions apparentées. Les deux appels sont AVANT le
        #     rejeu des journaux d'attente, et chacun est enveloppé à part : jamais
        #     fatal, comme `_rejouer_journaux_attente`.
        partition = self._partition_marquable()
        existait = partition.is_dir() if partition is not None else True
        agi = False  # `_reconstruire_si_vide` a-t-elle AGI (reconstruction due) ?
        create_tables(self.db_path, racine=self.project_root)
        if partition is not None:
            try:
                run_export.assurer_marqueur_partition(
                    partition, self.project_root,
                    origine="adoption" if existait else "naissance",
                )
            except Exception as exc:  # défensif : l'écrivain avale déjà
                print(f"event_store: marqueur de partition non pose : {exc}", file=sys.stderr)
            try:
                run_export.signaler_partitions_apparentees(partition, self.project_root)
            except Exception as exc:  # défensif : le signal avale déjà
                print(f"event_store: signal des partitions apparentees interrompu : {exc}", file=sys.stderr)
            # T-00000691 (S-00002372) : une base VIDE au chemin par défaut alors que
            # `runs/` porte des exports se reconstruit d'elle-même, pont board
            # compris — APRÈS marqueur et signal, AVANT le rejeu des journaux (un
            # journal rejoué d'abord masquerait la reconstruction due et
            # ré-exporterait un événement déjà présent). Filets S, R et N.
            agi = self._reconstruire_si_vide()
            if not agi and os.environ.get("AGENTS_V3_AUTO_SYNC") != "0":
                self._auto_sync_result = self._synchroniser_base_vivante(partition)
        # Reprise des journaux (T-00000805) : INSERT accepté ⇒ appliqué SANS projection (T-00000825 (1)) ;
        # refusé, ULID en base ⇒ la ligne de la BASE exportée ; refusé, ULID absent ⇒ CONSERVÉ et annoncé.
        self._rejouer_journaux_attente()
        # T-01M4N1FJC2X6YNA0XR51AYQKK1 : APRES le rejeu (la sonde voit l'etat FINAL de la construction),
        # sur la seule base au chemin par defaut, et seulement si la reconstruction d'office n'a PAS agi
        # (commitee : ecart nul ; `saute_non_vide` : deja annonce ; avortee/differee/non tentee : base vide).
        if partition is not None and not agi:
            self._annoncer_ecart_runs()

    def _partition_marquable(self) -> Optional[Path]:
        """La partition d'état MACHINE à marquer, ou `None` — SANS UN MOT — quand
        `db_path` n'est pas EXACTEMENT `state_project(project_root)/run/v3_event_
        store.db` (base explicite ailleurs : bancs sur `tmp/v3.db`, outils qui
        ouvrent une base à part), ou quand la partition n'est pas résoluble
        (`CadrePathError` : ni `$CADRE_PROJECT_ROOT`, ni dépôt git, ni ancêtre
        `.agents/`) ou la couture `cadre.paths` absente. Comparaison d'abord
        littérale, puis résolue (un `db_path` passé en chaîne peut porter une
        autre graphie du même fichier). `None` veut dire : ne marque rien À LA
        CONSTRUCTION ; le premier événement journalisé marque quand même la
        partition de `project_root`, via `preparer_journal_attente` (marqueur posé
        AVANT l'INSERT, sur `<partition>/run/attente/`, quelle que soit `db_path`)."""
        try:
            partition = Path(run_export.state_project(self.project_root))
        except Exception:
            return None
        attendu = partition / "run" / "v3_event_store.db"
        if self.db_path == attendu:
            return partition
        try:
            if self.db_path.resolve() == attendu.resolve():
                return partition
        except OSError:
            pass
        return None

    def _ecrire_evenement(
        self,
        cursor: sqlite3.Cursor,
        task_id: str,
        agent_role: str,
        event_type_str: str,
        payload_json: str,
        *,
        operation_id: Optional[str],
        event_kind: Optional[str],
        attempt: int,
        predecesseur_ulid: Optional[str] = None,
        ulid: Optional[str] = None,
        created_at: Optional[str] = None,
        journaliser: bool = True,
    ) -> tuple[str, Optional[Path], Dict[str, Any]]:
        """L'écrivain UNIQUE de `events_ledger`, à portée de CURSEUR — appelé par
        les CINQ sites DANS la transaction de l'appelant (T-00000650, étape 3).

        Il exécute (0) `preparer_journal_attente` (forme, dossier, marqueur : hors du
        verrou pour `append_event` et le rejeu, SOUS le `BEGIN IMMEDIATE` des trois
        sites du board — chemin rapide : un `stat`, le constructeur ayant posé le
        marqueur ; marqueur REFUSÉ ⇒ jusqu'à 3 appels git par événement sous ce verrou
        (mesuré : 20 événements, 1,66 s)), (1) l'INSERT dans la transaction de l'appelant, PUIS (2) le
        JOURNAL D'ATTENTE (`prepare=True`, texte NON versionné, `state_project()/run/
        attente/<ulid>.json`) — AVANT le commit, jamais avant un INSERT refusé
        (T-00000805 : un INSERT refusé ne laisse aucun journal, et ne touche pas le
        journal en attente d'un ULID déjà commité). RETOURNE `(ulid, journal, ligne)`.
        L'ajout à l'export versionné n'a PAS lieu ici : l'appelant, APRÈS son
        `commit()`, ajoute la ligne DEPUIS le journal puis efface le journal ;
        et dans sa branche `rollback` il efface le journal AVANT `raise`. C'est le
        SEUL site qui insère dans le ledger d'événements (témoin 18 compte le
        littéral) : la valeur écrite au journal ET à l'export est la valeur DÉJÀ
        RÉDIGÉE (témoin 8).

        `journaliser=False` — la RECONSTRUCTION (BLOQUANT 1 du binôme) : elle LIT
        depuis l'export, elle n'a RIEN à exporter, donc AUCUN journal d'attente ne
        doit naître ici. Un journal né en reconstruction survivait à une contention
        de verrou/interruption et, au redémarrage suivant, ressuscitait l'événement
        d'un AUTRE contributeur sous l'auteur COURANT (corruption d'attribution en
        ajout seul). Le journal (None quand `journaliser=False`) n'est jamais
        consommé par les chemins d'export/rollback dans ce cas.

        T-00000691 : quand `journaliser` est vrai, la PREMIÈRE instruction est le
        garde `_refuser_si_reconstruction_due` — AVANT `preparer_journal_attente`,
        donc aucun journal orphelin ne naît d'une écriture refusée. La
        reconstruction (`journaliser=False`) n'y passe jamais."""
        if journaliser:
            self._refuser_si_reconstruction_due()
        if ulid is None:
            ulid = run_export.nouvel_ulid()
        if created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ligne = {
            "task_id": task_id,
            "agent_role": agent_role,
            "event_type": event_type_str,
            "payload_json": payload_json,
            "created_at": created_at,
            "operation_id": operation_id,
            "event_kind": event_kind,
            "attempt": attempt,
            "ulid": ulid,
            "predecesseur_ulid": predecesseur_ulid,
        }
        if journaliser:  # forme de l'ULID (CONSTAT 1), dossier et marqueur AVANT l'INSERT (C1)
            run_export.preparer_journal_attente(ulid, depuis=self.project_root)
        cursor.execute(
            """
            INSERT INTO events_ledger
                (task_id, agent_role, event_type, created_at, payload_json,
                 operation_id, event_kind, attempt, ulid, predecesseur_ulid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                task_id,
                agent_role,
                event_type_str,
                created_at,
                payload_json,
                operation_id,
                event_kind,
                attempt,
                ulid,
                predecesseur_ulid,
            ),
        )
        journal = (
            run_export.ecrire_journal_attente(ligne, depuis=self.project_root, prepare=True)
            if journaliser
            else None
        )
        return ulid, journal, ligne

    @staticmethod
    def _flush_export(journaux: List[tuple], project_root: Path) -> None:
        """Étapes (3) puis (4), APRÈS le `commit()` de l'appelant : ajoute chaque
        ligne à l'export versionné DEPUIS son journal, PUIS efface le journal —
        jamais avant le commit, sinon une ligne annulée resterait dans le texte
        qui fait autorité.

        EXPORT DIFFÉRÉ, JAMAIS FATAL APRÈS COMMIT — SYMÉTRIE avec
        `_rejouer_journaux_attente`. L'événement est DÉJÀ commité en base (db +
        inbox) et son journal d'attente DÉJÀ écrit ; le miroir board→V3 a RÉUSSI.
        Propager ici faisait passer ce miroir réussi pour un ÉCHEC : `drain_sync_
        outbox` relâchait alors l'intent, qui restait dans `TASKS.json` et rouvrait
        sa file à CHAQUE transition (banc `tasks.test.sh`, « un champ changé = UNE
        ligne » : une transition réécrivait 45 lignes du store au lieu de ≤ 4 ;
        report en non fatal -> 2). `drain_sync_outbox` ACK désormais un miroir
        RÉUSSI et ne voit plus un faux échec.

        DEUX niveaux de report, et la distinction est PORTÉE PAR LE TYPE
        (S-00001805 (1)/(2), S-00001806 T4) :

          * RÉSOLUTION DE L'AUTEUR — on n'attrape QUE `AuteurIndisponible` (git
            `user.email` absent/vide : report TEMPORAIRE, convergence au rejeu dès
            qu'un email existe). Une panne d'INFRASTRUCTURE (git absent, dépôt
            corrompu, OU couture `cadre.executor` introuvable -> TOUTES
            `PanneInfrastructure`, levée par `run_export._email_git`) n'est PAS une
            `AuteurIndisponible` — PAS attrapée
            ici — et REMONTE fail-closed jusqu'à `tasks.py::drain_sync_outbox`,
            qui l'annonce « PANNE … export BLOQUÉ » : une panne PERMANENTE ne doit
            pas se présenter comme un report temporaire, ni contourner la posture
            fail-closed. C'est le contrat écrit dans la docstring de
            `run_export.AuteurIndisponible`.

          * ÉCHEC D'EXPORT DANS LA BOUCLE — un `ajouter_a_l_export` qui échoue
            APRÈS le commit (OSError disque plein, verrou d'export non acquis, copie
            réservée, traversée de chemin) NE redevient PAS fatal : il rejouerait la
            régression 45 lignes sur un miroir DÉJÀ réussi (mesuré par mutation sur
            clone de b33d131 avec email injecté ; `tasks.py::drain_sync_outbox`
            (son appel à `release_sync_event`) relâchait EN SILENCE). On ANNONCE sur stderr, on CONSERVE le journal — effacé
            SEULEMENT en cas de succès, sans quoi le flot retombe dans le chemin de
            succès et détruit la seule trace de reprise — et on POURSUIT au journal
            suivant. `_rejouer_journaux_attente` rattrape à la prochaine
            construction du store, dans des conditions saines.

        Le décompte annoncé est l'ARRIÉRÉ TOTAL (`lister_journaux_attente`), PAS la
        taille du LOT courant (S-00001806 C5) : « 2 journaux conservés » alors que
        156 attendent conclurait l'inverse de la vérité.

        RÉSIDU DE PORTABILITÉ ASSUMÉ, ÉCRIT PLUTÔT QUE SUPPOSÉ (décision tracée
        S-00001803). La convergence est MACHINE-LOCALE : le journal d'attente vit
        sous la partition d'état MACHINE (`state_project()`), dont la clé est
        `cadre.paths._empreinte_de_racine` — le sha256 de la GRAPHIE de la racine
        (`as_posix()`), appelée par `cadre.paths.state_project` — donc CHANGE selon la graphie du répertoire (clone ailleurs,
        archive, `git worktree add`, machine changée, état nettoyé). Après une telle
        bascule, les journaux de l'ANCIENNE partition ne sont plus jamais listés :
        journal ORPHELIN, export JAMAIS complété. C'est une régression de
        PORTABILITÉ assumée — l'alternative (garder l'intent en `sync_outbox` de
        `TASKS.json`, suivi et portable) recasse le banc en ≤ 4 lignes — pas un
        oubli. LA DÉCISION PILOTE SUR LA CLÉ EST PRISE (S-00002199, options C+D,
        T-00000692) : la clé RESTE la graphie canonique, aucune migration n'est
        faite, et l'ancienne partition est désormais SIGNALÉE plutôt que perdue
        en silence — chaque partition porte un `racine.json` qui nomme sa racine
        (`run_export.assurer_marqueur_partition`), et `EventStore.__init__`
        relève (à la naissance, puis à chaque apparition d'une sœur) et écrit sur
        stderr, à chaque construction et jusqu'à acquittement ou disparition, un
        bloc `PARTITION D'ÉTAT APPARENTÉE` nommant l'ancienne partition, les
        jambes tenues (même répertoire, même historique git, exports présents
        sous `runs/`) et le geste de reprise
        (`run_export.signaler_partitions_apparentees`). Les journaux orphelins
        restent orphelins ; ce qui change est qu'on le SAIT."""
        if not journaux:
            return
        try:
            auteur = run_export.auteur_courant(depuis=project_root)
        except run_export.AuteurIndisponible as exc:
            restant = len(run_export.lister_journaux_attente(depuis=project_root))
            print(
                f"event_store: {restant} journaux d'attente conserves pour rejeu "
                f"ulterieur (auteur d'export indisponible : {exc})",
                file=sys.stderr,
            )
            return
        for journal, ligne in journaux:
            exporte = False
            try:
                run_export.ajouter_a_l_export(ligne, depuis=project_root, auteur=auteur)
                exporte = True
                # F6 (binôme, C4) : l'effacement est DANS le `try`. `effacer_journal_
                # attente` n'absorbe que `FileNotFoundError` — une partition passée en
                # lecture seule, ou un journal tenu par un rejeu concurrent sous Windows
                # (PermissionError), le ferait PROPAGER, et `consume_board_intent`
                # lèverait : la régression 45 lignes rouverte par l'AUTRE porte. On
                # l'attrape donc plus bas — mais SANS mentir (voir G3).
                run_export.effacer_journal_attente(journal)
            except (run_export.RunExportError, OSError) as exc:
                # G3 (binôme, 2026-09-22) : DISTINGUER les deux causes de ce `except`.
                # Le drapeau `exporte` (posé APRÈS le retour de `ajouter_a_l_export`) est
                # le SEUL signal fiable : un `effacer_journal_attente` qui échoue laisse
                # le journal PRÉSENT sur disque EXACTEMENT comme un export qui échoue (un
                # unlink refusé ne retire rien — mesuré), donc la présence du fichier ne
                # les sépare PAS. Export réussi + effacement refusé : le rejeu retraitera
                # le journal (idempotent par ULID). Message VRAI dans les deux cas.
                restant = len(run_export.lister_journaux_attente(depuis=project_root))
                cause = ("export REUSSI, effacement du journal refuse"
                         if exporte else "echec export")
                print(
                    "event_store: ajout a l'export differe "
                    f"({cause}, {restant} journaux conserves pour rejeu) {journal} : {exc}",
                    file=sys.stderr,
                )
                continue

    @staticmethod
    def _annuler_journaux(journaux: List[tuple]) -> None:
        """Branche `rollback` : efface les journaux AVANT `raise` — un journal
        survivant ressusciterait un événement annulé APRÈS son INSERT (projection,
        inbox, 2e événement). Un INSERT refusé, lui, ne laisse aucun journal."""
        for journal, _ in journaux:
            run_export.effacer_journal_attente(journal)

    def _rejouer_journaux_attente(self) -> int:
        """Au démarrage, tente de rejouer chaque journal d'attente restant : INSERT
        accepté ⇒ appliqué au ledger SANS projection ni inbox (T-00000825 (1)), la ligne
        RENDUE par l'écrivain exportée ; refusé, ULID en base ⇒ la ligne de la BASE, qui
        fait foi, exportée (annoncé après l'export si le journal diverge) ; refusé, ULID
        absent ⇒ CONSERVÉ et annoncé ; ULID hors forme ⇒ refus DÉFINITIF, CONSERVÉ. Le
        journal n'est effacé qu'après un export RÉUSSI (idempotent par relecture du
        `.jsonl` du mois). Un journal né d'un arrêt entre commit et export est ici rattrapé.

        NON FATAL SUR UN AUTEUR DEFERRABLE, ET C'EST UNE BORNE MESURÉE : la
        CONSTRUCTION d'un `EventStore` ne DOIT JAMAIS échouer parce que `git
        user.email` est absent (jambe conteneur en root). Ce cas est une
        `AuteurIndisponible` : le journal est LAISSÉ pour un rejeu ultérieur, jamais
        propagé, sinon `tasks.py` (`replay_sync` -> `BoardBridge` ->
        `EventStore.__init__`) tomberait sur chaque `done`/`new` sans email git.

        PANNE D'INFRA À LA CONSTRUCTION — ATTRAPÉE, NON PROPAGÉE (G1, T-00000695/696,
        borne de S-00001806 T4 au chemin où elle a un sens). Une panne
        d'INFRASTRUCTURE à la résolution de l'auteur (`.git/config` illisible / dépôt
        corrompu -> 128, git absent ou cwd invalide -> 127, lancement refusé -> 126,
        timeout -> 124, `cadre.executor` introuvable OU en erreur) lève une
        `PanneInfrastructure` — sous-classe de `RunExportError`, jamais une
        `AuteurIndisponible` — sur TOUTES ces causes. (La couture introuvable sortait
        SANS ce type : `RunExportError` nu, ou `FileNotFoundError` du repli par chemin,
        qui tuait cette construction au lieu d'être attrapé ici — exec-critic,
        T-00000695/696.) Sur CE chemin de CONSTRUCTION on l'ATTRAPE, on annonce
        DISTINCTEMENT « PANNE … export BLOQUÉ jusqu'à réparation » et on rend 0 :
        construire un store n'est PAS exporter, et TOUTE commande de board (y compris
        celles qui RÉPARENT la panne) le construit — la faire mourir rend le dépôt
        irréparable par son propre outil et contredit le report que le drain vient
        d'annoncer. La distinction que T4 exige TIENT : le message porte PANNE et
        BLOQUÉ, jamais « auteur absent ». C'est le CHEMIN D'ÉCRITURE (`_flush_export`)
        qui, lui, PROPAGE fail-closed cette même panne — voir sa docstring. Un échec
        d'export DANS la boucle (E/S) reste, lui, non fatal et laissé pour rejeu."""
        rejoues = 0
        journaux = run_export.lister_journaux_attente(depuis=self.project_root)
        if not journaux:
            return 0
        # T-00000691 (S-00002372) : reconstruction automatique DUE et non commitée
        # sur cette instance — rejouer un journal rendrait la base NON vide, donc
        # jamais plus reconstruite d'office. On CONSERVE les journaux, on le DIT, et
        # la construction suivante (qui retente la reconstruction) les rejouera.
        if getattr(self, "_reconstruction_bloquee", False):
            print(
                f"event_store: {len(journaux)} journaux d'attente CONSERVES, rejeu "
                "differe : reconstruction automatique "
                f"{self._cause_reconstruction or 'AVORTEE'} sur cette instance "
                "(retentee a la construction suivante)",
                file=sys.stderr,
            )
            return 0
        # MAJEUR 4 (les DEUX revues) : résoudre l'empreinte d'auteur UNE SEULE FOIS
        # avant la boucle. `ajouter_a_l_export` relançait `git config user.email` par
        # journal — mesuré 4,41 s pour 300 journaux orphelins, à CHAQUE construction
        # du store, donc à chaque appel de l'outil de board. Auteur indisponible
        # (jambe conteneur en root sans git email) : on ANNONCE le nombre de journaux
        # CONSERVÉS et on SORT, au lieu de boucler pour rien.
        try:
            auteur = run_export.auteur_courant(depuis=self.project_root)
        except run_export.AuteurIndisponible as exc:
            print(
                f"event_store: {len(journaux)} journaux d'attente conserves pour "
                f"rejeu ulterieur (auteur d'export indisponible : {exc})",
                file=sys.stderr,
            )
            return 0
        except run_export.RunExportError as exc:
            # G1 (T-00000695/696) : panne d'infra à la résolution d'auteur — ATTRAPÉE ici,
            # non propagée (§ « PANNE D'INFRA » de la docstring : raison et distinction T4).
            print(
                f"event_store: PANNE de resolution d'auteur, {len(journaux)} journaux "
                f"d'attente conserves, export BLOQUE jusqu'a reparation : {exc}",
                file=sys.stderr,
            )
            return 0
        for chemin in journaux:
            exporte, annonce = False, None  # `annonce` : imprimée APRÈS un export RÉUSSI seulement
            try:
                ligne = run_export.lire_journal_attente(chemin)
                if not isinstance(ligne, dict):
                    raise ValueError(
                        f"forme inattendue : {type(ligne).__name__} au lieu d'un objet JSON"
                    )
            # exec-critic (T-00000695/696, T-00000718) : un octet non UTF-8, un JSON non-objet
            # ou une imbrication profonde tuaient TOUTE commande de board (mesuré, rc 1) ;
            # la forme est VALIDÉE ci-dessus, `RecursionError` nommée. BORNE : `MemoryError`.
            except FileNotFoundError:
                # T-00000691 (S-00002518 F7) : listé puis DISPARU — un rejeu
                # CONCURRENT (autre `tasks.py`) l'a exporté et effacé entre le listage
                # et la lecture. Ce n'est pas un journal illisible : l'annoncer « a
                # retirer a la main » était une FAUSSE alarme, sur un fichier absent.
                continue
            except (OSError, ValueError, RecursionError) as exc:
                # critic-fable T3 (T-00000695/696) : ce `continue` était MUET. Un
                # journal corrompu (tronqué, illisible) était ignoré à CHAQUE rejeu —
                # donc à chaque construction du store — sans un mot, et COMPTÉ quand
                # même dans les « N journaux d'attente conserves » que les autres
                # sites annoncent (`lister_journaux_attente` le liste). On l'ANNONCE,
                # une ligne par rejeu, sans l'effacer : l'outil n'a pas su le lire, ce
                # n'est pas une raison pour le jeter.
                print(
                    "event_store: journal d'attente ILLISIBLE, ignore a chaque rejeu "
                    "et COMPTE dans les journaux conserves -- a retirer a la main : "
                    f"{chemin} ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )
                continue
            if not ligne.get("ulid"):
                run_export.effacer_journal_attente(chemin)
                continue
            u, g = ligne["ulid"], ligne.get  # repr : un `\n` du journal ne fait qu'UNE ligne stderr
            if not run_export.ulid_bien_forme(u):  # refus DÉFINITIF avant tout INSERT, journal conservé
                print("event_store: journal d'attente REFUSE (ULID hors forme, definitif, jamais rejoue) "
                      f"{chemin} ulid={u!r}", file=sys.stderr)
                continue
            try:
                conn = get_db_connection(self.db_path)
                try:
                    _u, _j, ligne = self._ecrire_evenement(
                        conn.cursor(),
                        ligne["task_id"],
                        ligne["agent_role"],
                        ligne["event_type"],
                        ligne["payload_json"],
                        operation_id=ligne.get("operation_id"),
                        event_kind=ligne.get("event_kind"),
                        attempt=int(ligne.get("attempt", 0)),
                        predecesseur_ulid=ligne.get("predecesseur_ulid"),
                        ulid=ligne.get("ulid"),
                        created_at=ligne.get("created_at"),
                    )
                    conn.commit()
                except Exception as exc:
                    # CONSTAT 2 : échec RÉEL de l'INSERT (verrou WAL, E/S) ou SELECT qui lève ⇒ «echec base», ni
                    # export ni effacement. IntegrityError (S-00003233) : ULID en base ⇒ SA ligne, TOUJOURS.
                    conn.rollback()
                    ident = f"ulid={u} identite=({g('operation_id')!r}, {g('event_kind')!r}, {g('attempt')!r})"
                    cause = "rejeu du journal d'attente differe (echec base, journal conserve pour rejeu)"
                    if isinstance(exc, sqlite3.IntegrityError):
                        try:
                            trouve = conn.execute(
                                "SELECT task_id, agent_role, event_type, created_at, payload_json,"
                                " operation_id, event_kind, attempt, predecesseur_ulid"
                                " FROM events_ledger WHERE ulid=?", (u,),
                            ).fetchone()
                            _n = lambda v: None if v is None else str(v)  # affinité (0 == "0"), NULL ≠ "None"
                            cause = None if trouve is not None else (
                                f"rejeu du journal d'attente REFUSE par la base (ULID absent de {self.db_path} : "
                                "orphelin POSSIBLE, ne le deplacer qu'apres verification des autres bases du projet, "
                                "T-00000825)")
                            if trouve is not None:  # clés ET valeurs comparées ; l'annonce attend l'export
                                base = {**{k: trouve[k] for k in trouve.keys()}, "ulid": u}
                                if set(ligne) != set(base) or any(_n(base[k]) != _n(g(k)) for k in base):
                                    annonce = ("event_store: rejeu : journal divergent de la base, ligne de la "
                                               f"BASE exportée {ident}")
                                ligne = base
                        except sqlite3.Error:
                            pass
                    if cause:
                        print(f"event_store: {cause} {chemin} {ident} : {exc}", file=sys.stderr)
                        continue  # `finally` ferme la connexion avant de passer au suivant
                finally:
                    conn.close()
                # (3) puis (4) : ligne RENDUE ou ligne de la BASE ; auteur résolu UNE fois (MAJEUR 4).
                run_export.ajouter_a_l_export(ligne, depuis=self.project_root, auteur=auteur)
                if annonce:
                    print(annonce, file=sys.stderr)
                exporte = True
                run_export.effacer_journal_attente(chemin)
                rejoues += 1
            except Exception as exc:
                # MAJEUR 4 / F8 / G3 : échec d'AJOUT à l'export APRÈS la base — ANNONCÉ (jamais muet),
                # arriéré TOTAL comme `_flush_export`, journal LAISSÉ ; `exporte` sépare un échec
                # d'export d'un effacement refusé (le fichier présent ne les sépare pas).
                restant = len(run_export.lister_journaux_attente(depuis=self.project_root))
                cause = ("export REUSSI, effacement du journal refuse"
                         if exporte else "echec export")
                print(
                    "event_store: ajout a l'export differe "
                    f"({cause}, {restant} journaux conserves pour rejeu) {chemin} : {exc}",
                    file=sys.stderr,
                )
                continue
        return rejoues

    def append_event(
        self,
        task_id: str,
        agent_role: str,
        event_type: Union[EventType, str],
        payload: Dict[str, Any],
        *,
        operation_id: Optional[str] = None,
        attempt: int = 0,
        event_kind: Optional[str] = None,
        predecesseur_ulid: Optional[str] = None,
        ulid: Optional[str] = None,
    ) -> int:
        """Appends an immutable event to events_ledger and updates task_projections.

        T-00000650 : `append_event` devient UN appelant parmi cinq de l'écrivain
        unique `_ecrire_evenement`. L'ordre (1)insert dans la transaction ->
        (2)journal -> commit -> (3)export -> (4)efface le journal (T-00000805 : le
        journal naît APRÈS l'INSERT accepté) ; sur rollback, le journal est effacé
        AVANT `raise`.

        VERROU, écrit exactement (report T-00000689) : ici l'ULID naît AVANT
        l'INSERT qui prend le verrou d'écriture, le journal APRÈS, SOUS ce verrou —
        aucune `BEGIN IMMEDIATE`, la transaction implicite ne prend le verrou qu'au
        premier INSERT. Deux `append_event` concurrents peuvent donc commiter dans
        l'ordre INVERSE de leurs ULID. `consume_board_intent`,
        `enqueue_board_command`, `ack_board_command_with_event` et `_reconstruire`
        écrivent, eux, SOUS `BEGIN IMMEDIATE`.

        T-00000691 : lève `ReconstructionAvorteeError` (sans rien écrire) tant
        qu'une reconstruction automatique due n'est pas commitée sur l'instance."""
        event_type_str = event_type.value if isinstance(event_type, EventType) else str(event_type)
        # T-00000641 (P1) : rédiger l'arbre du payload À LA SOURCE, AVANT insert ET
        # projection. `task_id`/`agent_role`/`event_type`/`operation_id`/
        # `event_kind`/`attempt` restent BRUTS (identités et jointures).
        payload_redige = _redaction().rediger_arbre(payload)
        payload_str = json.dumps(payload_redige, ensure_ascii=False)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        journaux: List[tuple] = []
        try:
            _ulid, journal, ligne = self._ecrire_evenement(
                cursor,
                task_id,
                agent_role,
                event_type_str,
                payload_str,
                operation_id=operation_id,
                event_kind=event_kind or event_type_str,
                attempt=attempt,
                predecesseur_ulid=predecesseur_ulid,
                ulid=ulid,
            )
            journaux.append((journal, ligne))
            event_id = int(cursor.lastrowid)
            self._apply_projection(cursor, task_id, agent_role, event_type_str, payload_redige)
            conn.commit()
        except Exception:
            conn.rollback()
            self._annuler_journaux(journaux)
            raise
        finally:
            conn.close()
        self._flush_export(journaux, self.project_root)
        return event_id

    def _apply_projection(self, cursor: sqlite3.Cursor, task_id: str, agent_role: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Internal deterministic projector for task_projections table.

        T-00000641 : `code_diff` stocké ici est REÇU DÉJÀ RÉDIGÉ (P1, par
        `append_event`) ; un diff légitime portant une chaîne de FORME secrète y
        est visible MUTILÉ, marqueur `[SECRET RÉDIGÉ:<famille>]`. Taux de faux
        positif NON MESURÉ ; coût accepté QUALITATIVEMENT (la mutilation est
        visible, une fuite ne l'est pas) — nommé ici pour le lecteur de cette
        colonne (dashboard, reprise). Aucune logique ne change."""
        if event_type == EventType.TASK_CREATED.value:
            req_id = payload.get("req_id", "REQ-UNKNOWN")
            spec_version = payload.get("spec_version", 1)
            cursor.execute(
                """
                INSERT INTO task_projections (task_id, req_id, spec_version, status, current_assignee)
                VALUES (?, ?, ?, 'PENDING', ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status='PENDING', current_assignee=excluded.current_assignee, last_updated=CURRENT_TIMESTAMP;
                """,
                (task_id, req_id, spec_version, agent_role)
            )

        elif event_type == EventType.CODE_GENERATED.value:
            code_diff = payload.get("code_diff", "")
            cursor.execute(
                """
                INSERT INTO task_projections (task_id, req_id, spec_version, status, current_assignee, code_diff)
                VALUES (?, 'REQ-UNKNOWN', 1, 'IN_DEV', ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status='IN_DEV', code_diff=excluded.code_diff, current_assignee=excluded.current_assignee, last_updated=CURRENT_TIMESTAMP;
                """,
                (task_id, agent_role, code_diff)
            )

        elif event_type == EventType.CRITIC_VERDICT.value:
            passed = payload.get("passed", False)
            new_status = "IN_TEST" if passed else "IN_DEV"
            cursor.execute(
                """
                INSERT INTO task_projections (task_id, req_id, spec_version, status, current_assignee)
                VALUES (?, 'REQ-UNKNOWN', 1, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status, retry_count=retry_count + ?, current_assignee=excluded.current_assignee, last_updated=CURRENT_TIMESTAMP;
                """,
                (task_id, new_status, agent_role, 0 if passed else 1)
            )

        elif event_type == EventType.TEST_RUN.value:
            passed = payload.get("passed", False)
            new_status = "COMPLETED" if passed else "IN_DEV"
            cursor.execute(
                """
                INSERT INTO task_projections (task_id, req_id, spec_version, status, current_assignee)
                VALUES (?, 'REQ-UNKNOWN', 1, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status=excluded.status, current_assignee=excluded.current_assignee, last_updated=CURRENT_TIMESTAMP;
                """,
                (task_id, new_status, agent_role)
            )

        elif event_type == EventType.SPEC_MUTATION_CANCEL.value:
            cursor.execute(
                """
                UPDATE task_projections
                SET is_blocked=1, last_updated=CURRENT_TIMESTAMP
                WHERE task_id=?;
                """,
                (task_id,)
            )

    @staticmethod
    def _board_status(snapshot: Dict[str, Any]) -> str:
        state = snapshot["state"]
        if state == "pending":
            return "PENDING"
        if state == "blocked":
            return "BLOCKED"
        if state == "done":
            return "COMPLETED"
        if state != "running":
            raise ValueError(f"unknown board state: {state!r}")
        stage = snapshot.get("stage", "")
        if stage in {"critic", "plan-critic", "security-code-review", "v3:IN_CRITIC"}:
            return "IN_CRITIC"
        if stage in {"test", "v3:IN_TEST"}:
            return "IN_TEST"
        return "IN_DEV"

    def consume_board_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Record and reduce one Board -> V3 intent exactly once.

        T-00000691 : sur une instance dont la reconstruction due n'est pas
        commitée, refusé (`ReconstructionAvorteeError`) AVANT `BEGIN IMMEDIATE` —
        le verrou d'écriture n'est même pas pris (addendum exec-critic). La garde
        de `_ecrire_evenement` reste la seconde ligne."""
        self._refuser_si_reconstruction_due()
        operation_id = str(intent["operation_id"])
        event_kind = str(intent["event_kind"])
        attempt = int(intent.get("attempt", 0))
        task_id = str(intent["affected_task_ids"][0])
        # T-00000641 (P2) : le contrôle de flux garde l'intent BRUT (identités et
        # jointures) ; ce qui est ÉCRIT ou COMPARÉ passe par la forme rédigée.
        intent_redige = _redaction().rediger_arbre(intent)
        payload_json = json.dumps(intent_redige, ensure_ascii=False, sort_keys=True)
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        journaux: List[tuple] = []
        cree_par: Optional[str] = None  # T-00001055 : créateur d'un refus `creation-collision`
        effect_board_id: Optional[str] = None  # l'id que NOMME l'effet, pas `affected_task_ids[0]`
        try:
            cursor.execute("BEGIN IMMEDIATE")
            prior = cursor.execute(
                """
                SELECT event_kind, payload_json, effect_json
                FROM board_sync_inbox WHERE operation_id=?
                """,
                (operation_id,),
            ).fetchone()
            if prior is not None:
                prior_payload = json.loads(prior["payload_json"])
                identity_fields = (
                    "event_kind",
                    "affected_task_ids",
                    "before",
                    "after",
                    "revision_sha256",
                )
                prior_identity = {
                    field: prior_payload.get(field) for field in identity_fields
                }
                # C9 : les deux côtés RÉDIGÉS (`prior_identity` vient du store,
                # donc déjà rédigé) — sinon un rejeu légitime d'un intent portant
                # un secret lèverait `operation identity mismatch`.
                current_identity = {
                    field: intent_redige.get(field) for field in identity_fields
                }
                if prior["event_kind"] != event_kind or prior_identity != current_identity:
                    raise ValueError(
                        f"operation identity mismatch for board intent {operation_id}"
                    )
                conn.commit()
                resultat = json.loads(prior["effect_json"])
            else:
                # T-00000650 : l'INSERT de l'événement passe par l'écrivain unique,
                # DANS cette transaction ; son journal est mis de côté pour l'export
                # APRÈS le commit.
                _u1, j1, l1 = self._ecrire_evenement(
                    cursor,
                    task_id,
                    "BoardBridge",
                    event_kind,
                    payload_json,
                    operation_id=operation_id,
                    event_kind=event_kind,
                    attempt=attempt,
                )
                journaux.append((j1, l1))
                effect = self._reduce_board_intent(cursor, intent)
                if effect.get("action") == "creation-collision":
                    cree_par = str(effect["create_operation_id"])
                    effect_board_id = str(effect["board_task_id"])
                # A-T2 : rédiger `effect` UNE fois à la source — une seule forme
                # pour l'events_ledger (branche échec), pour
                # `board_sync_inbox.effect_json` ET pour le retour. Le contrôle de
                # flux garde `effect` brut (`applied` est un booléen d'identité).
                effect_redige = _redaction().rediger_arbre(effect)
                if not effect.get("applied", False):
                    _u2, j2, l2 = self._ecrire_evenement(
                        cursor,
                        task_id,
                        "BoardBridge",
                        EventType.BOARD_COMMAND_FAILED.value,
                        json.dumps(
                            {"intent": intent_redige, "effect": effect_redige},
                            ensure_ascii=False, sort_keys=True,
                        ),
                        operation_id=operation_id,
                        event_kind=EventType.BOARD_COMMAND_FAILED.value,
                        attempt=attempt,
                    )
                    journaux.append((j2, l2))
                cursor.execute(
                    """
                    INSERT INTO board_sync_inbox
                        (operation_id, event_kind, attempt, payload_json, effect_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        event_kind,
                        attempt,
                        payload_json,
                        json.dumps(effect_redige, ensure_ascii=False, sort_keys=True),
                    ),
                )
                conn.commit()
                resultat = effect_redige
        except Exception:
            conn.rollback()
            self._annuler_journaux(journaux)
            raise
        finally:
            conn.close()
        if cree_par is not None:
            # T-00001055 : nommé AVANT `_flush_export`, qui peut lever après le commit
            # (le rejeu passerait alors par la branche dédupliquée, muette). Rien au
            # rejeu ni à la reconstruction : FAILED et effet d'inbox y suffisent.
            # `!r` : un `\n` d'identifiant ne fait qu'UNE ligne (cf. journal d'attente).
            print(
                f"event_store: creation refusee — {effect_board_id!r} deja cree par {cree_par!r}, "
                f"operation {operation_id!r} NON projetee (BOARD_COMMAND_FAILED ecrit)",
                file=sys.stderr,
            )
        self._flush_export(journaux, self.project_root)
        return resultat

    def _reduce_board_intent(
        self,
        cursor: sqlite3.Cursor,
        intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Réduit UN intent board en lien `task_board_mapping` + projection. Le drain
        vif (`consume_board_intent`) ET la reconstruction (`_rejouer_intent`) passent
        ici : une règle posée ici tient aux deux chemins.

        T-00001055 (S-00003347 M1) — une seconde CRÉATION (`before=None`) d'un id
        déjà lié, sous un AUTRE operation_id que le créateur du lien, est REFUSÉE :
        `applied=False`, action `creation-collision`, l'effet nomme `board_task_id` et
        `create_operation_id` (le créateur). Placée APRÈS `never-resurrect` : une
        création sur un lien tombé garde ce nom. Aucun SQL : la garde lit `link_row`.

        CE QUI RESTE, voulu. Le lien naît au PREMIER intent vu, quel que soit son
        `before` : les 59 liens de runs/ à créateur `before≠None` (mesurés le
        2026-10-01, dont d6c40430 de T-00000573) n'ont aucun intent `before=None`, la
        règle stricte les délierait (S-00003378). L'adoption d'un lien existant par
        un DELTA (`before≠None`) sous un autre operation_id est toute mise à jour du
        board. RÉSIDU NOMMÉ (M6) :
        après une création refusée, les deltas de la lignée perdante restent adoptés
        et projetés sur le lien du créateur — la garde nomme le premier symptôme,
        elle ne sépare pas les lignées.

        VISIBILITÉ DU REFUS, par chemin :
          * drain vif : 3/3, sauf processus tué ou stderr fermé entre le commit et
            la ligne : 2/3, le rejeu dédupliqué est muet — `BOARD_COMMAND_FAILED`
            au ledger (exporté), effet d'inbox `creation-collision`, UNE ligne
            stderr nommant l'id et les deux opérations ;
          * reconstruction après un refus vif : 2/3 — FAILED rejoué et apparié,
            effet d'inbox ; aucune ligne stderr ;
          * clones fusionnés (deux créateurs, aucun FAILED) : l'effet d'inbox, et sur
            stderr le seul compteur ANONYME `echecs_sans_failed` de l'annonce.
        Relire les refus exportés : `git grep --untracked -n creation-collision -- runs/`. Après
        un revert de la garde, chaque FAILED `creation-collision` exporté se compte
        `faux_failed` à la reconstruction (non fatal, annoncé)."""
        operation_id = str(intent["operation_id"])
        event_kind = str(intent["event_kind"])
        before = intent.get("before")
        after = intent.get("after")
        board_task_id = str((after or before)["id"])
        link_row = cursor.execute(
            "SELECT * FROM task_board_mapping WHERE board_task_id=?",
            (board_task_id,),
        ).fetchone()

        if event_kind == EventType.BOARD_RUNNING_REPLACED.value:
            if link_row is None:
                return {"applied": False, "action": "replacement-without-link"}
            replacement_link = dict(link_row)
            replacement_projection = cursor.execute(
                "SELECT status FROM task_projections WHERE task_id=?",
                (replacement_link["v3_task_id"],),
            ).fetchone()
            if replacement_projection is None or str(replacement_projection["status"]) not in {
                "IN_DEV",
                "IN_CRITIC",
                "IN_TEST",
            }:
                return {
                    "applied": False,
                    "action": "replacement-divergence",
                    "v3_task_id": replacement_link["v3_task_id"],
                }

        if link_row is None:
            if after is None:
                v3_task_id = f"BOARD:{operation_id}"
                cursor.execute(
                    """
                    INSERT INTO task_board_mapping
                        (board_task_id, v3_task_id, create_operation_id, tombstoned)
                    VALUES (?, ?, ?, 1)
                    """,
                    (board_task_id, v3_task_id, operation_id),
                )
                return {
                    "applied": True,
                    "action": "tombstone-unlinked",
                    "v3_task_id": v3_task_id,
                }
            v3_task_id = f"BOARD:{operation_id}"
            cursor.execute(
                """
                INSERT INTO task_board_mapping
                    (board_task_id, v3_task_id, create_operation_id, tombstoned)
                VALUES (?, ?, ?, 0)
                """,
                (board_task_id, v3_task_id, operation_id),
            )
            tombstoned = 0
        else:
            link = dict(link_row)
            v3_task_id = str(link["v3_task_id"])
            tombstoned = int(link["tombstoned"])

        if after is None:
            cursor.execute(
                "UPDATE task_board_mapping SET tombstoned=1 WHERE board_task_id=?",
                (board_task_id,),
            )
            return {"applied": True, "action": "tombstoned", "v3_task_id": v3_task_id}
        if tombstoned:
            return {"applied": False, "action": "never-resurrect", "v3_task_id": v3_task_id}
        if (
            link_row is not None
            and before is None
            and str(link_row["create_operation_id"]) != operation_id
        ):
            # T-00001055 : CRÉATION d'un id déjà lié par un autre créateur (docstring).
            return {
                "applied": False,
                "action": "creation-collision",
                "v3_task_id": v3_task_id,
                "board_task_id": board_task_id,
                "create_operation_id": str(link_row["create_operation_id"]),
            }

        status = self._board_status(after)
        prior_projection = cursor.execute(
            "SELECT status FROM task_projections WHERE task_id=?",
            (v3_task_id,),
        ).fetchone()
        if event_kind == EventType.BOARD_RUNNING_REPLACED.value:
            status = "PENDING"

        cursor.execute(
            """
            INSERT INTO task_projections
                (task_id, req_id, spec_version, status, current_assignee, is_blocked)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                current_assignee=excluded.current_assignee,
                is_blocked=excluded.is_blocked,
                last_updated=CURRENT_TIMESTAMP
            """,
            (
                v3_task_id,
                board_task_id,
                status,
                # T-00000641 : seule colonne libre rédigée ici. `rediger_arbre`
                # (et non `rediger`) car `owner` n'est pas typé. `board_task_id`
                # et `status` restent bruts (identité, énumération).
                _redaction().rediger_arbre(after.get("owner")) or "BoardBridge",
                1 if status.startswith("BLOCKED") else 0,
            ),
        )
        return {"applied": True, "action": "projected", "v3_task_id": v3_task_id, "status": status}

    def get_board_link(self, board_task_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM task_board_mapping WHERE board_task_id=?",
                (board_task_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def reserve_board_identity(
        self, v3_task_id: str, operation_id: str, board_task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Reserve one V3 identity before any file-backed board mutation.

        T-00001060 (K1) : `board_task_id`, frappé par le pont AVANT tout texte, est posé
        à l'INSERT, `finalized_at` NULL ; une réservation déjà là le laisse inchangé.
        T-00000691 : refusé (`ReconstructionAvorteeError`) tant qu'une
        reconstruction automatique due n'est pas commitée sur l'instance."""
        self._refuser_si_reconstruction_due()
        conn = get_db_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            mapping = conn.execute(
                "SELECT * FROM task_board_mapping WHERE v3_task_id=?",
                (v3_task_id,),
            ).fetchone()
            if mapping is not None:
                existing = dict(mapping)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO board_identity_reservations
                        (v3_task_id, creator_operation_id, board_task_id, finalized_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        v3_task_id,
                        existing["create_operation_id"],
                        existing["board_task_id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO board_identity_reservations
                        (v3_task_id, creator_operation_id, board_task_id)
                    VALUES (?, ?, ?)
                    """,
                    (v3_task_id, operation_id, board_task_id),
                )
            reservation = conn.execute(
                "SELECT * FROM board_identity_reservations WHERE v3_task_id=?",
                (v3_task_id,),
            ).fetchone()
            conn.commit()
            return dict(reservation)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def link_board_task(
        self,
        board_task_id: str,
        v3_task_id: str,
        operation_id: str,
    ) -> Dict[str, Any]:
        """Finalize a reserved identity, rejecting conflicting replays.

        T-00000691 : refusé (`ReconstructionAvorteeError`) tant qu'une
        reconstruction automatique due n'est pas commitée sur l'instance."""
        self._refuser_si_reconstruction_due()
        conn = get_db_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            reservation_row = conn.execute(
                "SELECT * FROM board_identity_reservations WHERE v3_task_id=?",
                (v3_task_id,),
            ).fetchone()
            if reservation_row is None:
                raise ValueError(f"unreserved V3 board identity: {v3_task_id}")
            reservation = dict(reservation_row)
            if reservation["creator_operation_id"] != operation_id:
                raise ValueError(
                    f"operation {operation_id} does not own V3 identity {v3_task_id}"
                )
            if reservation["board_task_id"] not in {None, board_task_id}:
                raise ValueError(f"conflicting board identity for V3 task {v3_task_id}")
            existing = conn.execute(
                """
                SELECT * FROM task_board_mapping
                WHERE board_task_id=? OR v3_task_id=? OR create_operation_id=?
                """,
                (board_task_id, v3_task_id, operation_id),
            ).fetchone()
            if existing is not None:
                link = dict(existing)
                if (
                    link["board_task_id"] != board_task_id
                    or link["v3_task_id"] != v3_task_id
                    or link["create_operation_id"] != operation_id
                ):
                    raise ValueError(f"conflicting board/V3 mapping for operation {operation_id}")
            else:
                conn.execute(
                    """
                    INSERT INTO task_board_mapping
                        (board_task_id, v3_task_id, create_operation_id, tombstoned)
                    VALUES (?, ?, ?, 0)
                    """,
                    (board_task_id, v3_task_id, operation_id),
                )
            conn.execute(
                """
                UPDATE board_identity_reservations
                SET board_task_id=?, finalized_at=CURRENT_TIMESTAMP
                WHERE v3_task_id=? AND creator_operation_id=?
                """,
                (board_task_id, v3_task_id, operation_id),
            )
            row = conn.execute(
                "SELECT * FROM task_board_mapping WHERE board_task_id=?",
                (board_task_id,),
            ).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def enqueue_board_command(
        self,
        operation_id: str,
        event_kind: Union[EventType, str],
        payload: Dict[str, Any],
        *,
        supersedes_operation_id: Optional[str] = None,
    ) -> bool:
        kind = event_kind.value if isinstance(event_kind, EventType) else str(event_kind)
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        conn = get_db_connection(self.db_path)
        journaux: List[tuple] = []
        try:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                """
                SELECT event_kind, payload_json FROM board_sync_outbox
                WHERE operation_id=?
                """,
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior["event_kind"] != kind or prior["payload_json"] != payload_json:
                    raise ValueError(
                        f"operation identity mismatch for board command {operation_id}"
                    )
                conn.commit()
                resultat = False
            else:
                if (
                    supersedes_operation_id
                    and supersedes_operation_id != operation_id
                ):
                    conn.execute(
                        """
                        UPDATE board_sync_outbox
                        SET cancelled_at=CURRENT_TIMESTAMP, superseded_by=?,
                            lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL
                        WHERE operation_id=? AND acked_at IS NULL AND cancelled_at IS NULL
                        """,
                        (operation_id, supersedes_operation_id),
                    )
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO board_sync_outbox
                        (operation_id, event_kind, payload_json)
                    VALUES (?, ?, ?)
                    """,
                    (operation_id, kind, payload_json),
                )
                inserted = cursor.rowcount == 1
                if inserted:
                    task_id = str(payload.get("board_task_id", "BOARD-UNKNOWN"))
                    # T-00000641 (P3) : variable SÉPARÉE ne servant QUE
                    # l'events_ledger. L'outbox et la comparaison d'identité gardent
                    # `payload_json` BRUT — les deux côtés bruts, aucun changement.
                    payload_json_redige = json.dumps(
                        _redaction().rediger_arbre(payload), ensure_ascii=False, sort_keys=True
                    )
                    _u, journal, ligne = self._ecrire_evenement(
                        conn.cursor(),
                        task_id,
                        "BoardBridge",
                        EventType.BOARD_COMMAND_REQUESTED.value,
                        payload_json_redige,
                        operation_id=operation_id,
                        event_kind=EventType.BOARD_COMMAND_REQUESTED.value,
                        attempt=0,
                    )
                    journaux.append((journal, ligne))
                conn.commit()
                resultat = inserted
        except Exception:
            conn.rollback()
            self._annuler_journaux(journaux)
            raise
        finally:
            conn.close()
        self._flush_export(journaux, self.project_root)
        return resultat

    def pending_board_commands(self) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT * FROM board_sync_outbox
                WHERE acked_at IS NULL AND cancelled_at IS NULL
                ORDER BY rowid
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def claim_board_command(
        self,
        owner: str,
        *,
        now: Optional[float] = None,
        lease_seconds: float = 30.0,
        operation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically lease one pending/expired SQLite outbox command."""
        conn = get_db_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            claimed_at = time.time() if now is None else now
            row = conn.execute(
                """
                SELECT * FROM board_sync_outbox
                WHERE acked_at IS NULL
                  AND cancelled_at IS NULL
                ORDER BY rowid
                LIMIT 1
                """,
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            command = dict(row)
            if operation_id is not None and command["operation_id"] != operation_id:
                conn.commit()
                return None
            if command.get("lease_token") is not None and (
                command.get("lease_expires_at") is None
                or float(command["lease_expires_at"]) > claimed_at
            ):
                conn.commit()
                return None
            attempt = int(command["attempt"]) + (1 if command.get("lease_token") else 0)
            token = str(uuid.uuid4())
            conn.execute(
                """
                UPDATE board_sync_outbox
                SET attempt=?, lease_owner=?, lease_token=?, lease_expires_at=?
                WHERE operation_id=? AND acked_at IS NULL AND cancelled_at IS NULL
                """,
                (attempt, owner, token, claimed_at + lease_seconds, command["operation_id"]),
            )
            claimed = conn.execute(
                "SELECT * FROM board_sync_outbox WHERE operation_id=?",
                (command["operation_id"],),
            ).fetchone()
            conn.commit()
            return dict(claimed)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def renew_board_command_lease(
        self,
        operation_id: str,
        lease_token: str,
        lease_seconds: float = 30.0,
    ) -> bool:
        """Extend the active head lease across the Board critical section.

        Renewal is atomic, and strict FIFO keeps every later command
        unclaimable while the head command owns its renewed lease.
        """
        conn = get_db_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            renewed_at = time.time()
            cursor = conn.execute(
                """
                UPDATE board_sync_outbox
                SET lease_expires_at=?
                WHERE operation_id=? AND lease_token=?
                  AND acked_at IS NULL AND cancelled_at IS NULL
                  AND lease_expires_at > ?
                """,
                (
                    renewed_at + lease_seconds,
                    operation_id,
                    lease_token,
                    renewed_at,
                ),
            )
            conn.commit()
            return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def is_board_command_acked(self, operation_id: str) -> bool:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT acked_at FROM board_sync_outbox WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            return bool(row and row["acked_at"])
        finally:
            conn.close()

    def is_board_command_active(
        self,
        operation_id: str,
        lease_token: str,
        *,
        now: Optional[float] = None,
    ) -> bool:
        """Return whether this exact lease may still apply its board effect."""
        checked_at = time.time() if now is None else now
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT 1 FROM board_sync_outbox
                WHERE operation_id=? AND lease_token=?
                  AND acked_at IS NULL AND cancelled_at IS NULL
                  AND lease_expires_at > ?
                """,
                (operation_id, lease_token, checked_at),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _insert_board_ack_event(
        self,
        cursor: sqlite3.Cursor,
        command: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> tuple:
        """Insère l'événement ACK par l'écrivain unique ; RETOURNE `(journal,
        ligne)` que l'appelant flushe vers l'export APRÈS son commit."""
        _u, journal, ligne = self._ecrire_evenement(
            cursor,
            str(payload.get("board_task_id", "BOARD-UNKNOWN")),
            "BoardBridge",
            EventType.BOARD_COMMAND_ACKED.value,
            # T-00000641 (P4) : payload rédigé ; `board_task_id` reste brut.
            json.dumps(_redaction().rediger_arbre(payload), ensure_ascii=False, sort_keys=True),
            operation_id=command["operation_id"],
            event_kind=EventType.BOARD_COMMAND_ACKED.value,
            attempt=int(command["attempt"]),
        )
        return journal, ligne

    def ack_board_command_with_event(
        self,
        operation_id: str,
        lease_token: str,
        payload: Dict[str, Any],
        *,
        now: Optional[float] = None,
    ) -> bool:
        """Commit ACK state and immutable ACK event in one transaction."""
        conn = get_db_connection(self.db_path)
        journaux: List[tuple] = []
        try:
            conn.execute("BEGIN IMMEDIATE")
            checked_at = time.time() if now is None else now
            row = conn.execute(
                """
                SELECT * FROM board_sync_outbox
                WHERE operation_id=? AND acked_at IS NULL
                  AND cancelled_at IS NULL AND lease_token=?
                  AND lease_expires_at > ?
                """,
                (operation_id, lease_token, checked_at),
            ).fetchone()
            if row is None:
                conn.commit()
                resultat = False
            else:
                command = dict(row)
                journaux.append(self._insert_board_ack_event(conn.cursor(), command, payload))
                conn.execute(
                    """
                    UPDATE board_sync_outbox
                    SET acked_at=CURRENT_TIMESTAMP, last_error=NULL,
                        lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL
                    WHERE operation_id=? AND lease_token=?
                      AND cancelled_at IS NULL
                      AND lease_expires_at > ?
                    """,
                    (operation_id, lease_token, checked_at),
                )
                conn.commit()
                resultat = True
        except Exception:
            conn.rollback()
            self._annuler_journaux(journaux)
            raise
        finally:
            conn.close()
        self._flush_export(journaux, self.project_root)
        return resultat

    def release_board_command(
        self,
        operation_id: str,
        lease_token: str,
        error: str,
    ) -> bool:
        # T-00000641 (P5, C1 bis) : `last_error` embarque `str(exc)` d'une
        # validation, donc la valeur fautive. Rédigé À LA SOURCE, dans la fonction
        # qui écrit. `error` est typé `str`, l'appel direct à `rediger` est sûr ;
        # `rediger(None)` rendrait `None` (colonne à NULL, comme aujourd'hui).
        error = _redaction().rediger(error)
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                UPDATE board_sync_outbox
                SET attempt=attempt+1, last_error=?,
                    lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL
                WHERE operation_id=? AND acked_at IS NULL AND lease_token=?
                  AND cancelled_at IS NULL
                """,
                (error, operation_id, lease_token),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    def get_task_projection(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Reads current state of a task from task_projections."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM task_projections WHERE task_id=?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieves complete immutable history of events for a task."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events_ledger WHERE task_id=? ORDER BY event_id ASC", (task_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @staticmethod
    def _resolved_kind(step: "RunStep") -> str:
        """The ``event_kind`` an ``append_event`` will actually store for ``step``
        — ``event_kind or event_type`` — recomputed the SAME way ``append_event``
        does, so a lookup by durable identity matches what was written."""
        event_type_str = (
            step.event_type.value if isinstance(step.event_type, EventType)
            else str(step.event_type)
        )
        return step.event_kind or event_type_str

    def _event_by_identity(self, step: "RunStep") -> Optional[Dict[str, Any]]:
        """The ledger row for ``step``'s durable identity
        ``(operation_id, event_kind, attempt)``, or ``None`` if none exists."""
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT task_id, agent_role, event_type, payload_json,
                       operation_id, event_kind, attempt
                FROM events_ledger
                WHERE operation_id=? AND event_kind=? AND attempt=?
                """,
                (step.operation_id, self._resolved_kind(step), step.attempt),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def apply_run_step(self, step: RunStep) -> bool:
        """Apply ONE run step, idempotently.

        Returns ``True`` when the step is appended for the first time, ``False``
        when its durable identity ``(operation_id, event_kind, attempt)`` is
        already in ``events_ledger`` with IDENTICAL content and it is therefore
        SKIPPED without re-running its projection.

        The only uniqueness constraint an ``append_event`` can violate is
        ``uq_events_operation_attempt`` on that durable identity
        (``task_projections`` upserts via ``ON CONFLICT`` and never raises here),
        and the failed append already rolled back — so a duplicate leaves NO
        extra event and NO double projection.

        WHAT THIS ONLY SWALLOWS, corrected by the PORTE 3 review (C1). A prior
        ``IntegrityError`` was treated as « already applied » whenever its text
        merely contained ``unique`` — swallowing ANY unique violation, including
        one that has nothing to do with this run. Now, on ``IntegrityError``, the
        durable identity is RE-READ (``_event_by_identity``) and three cases are
        separated, mirroring ``consume_board_intent``'s identity guard:

          * absent      -> the violation was NOT ours; ``raise``.
          * present, SAME task_id/agent_role/event_type/payload (a MULTISET of sorted
            pairs: key order ignored, duplicate keys kept, NOT « last key wins » —
            ``{"1":"S","1":"b"}`` then ``{"1":"b","1":"S"}`` is a skip) -> ``return False``.
          * present, DIFFERENT content (unreadable stored JSON included, integer over
            4300 digits too) -> the SAME durable identity is reused for a DIFFERENT
            event; ``ValueError`` — never silently absorbed as « already applied ».
          BORNE : sur Python 3.11, un payload de plus de ~496 niveaux lève
          ``RecursionError`` au rejeu (3.11.16, pile quasi vide ; non atteint sous 3.14).

        SAME operation_id, DIFFERENT event_type -> TWO events, and it is
        INTENDED. ``event_kind`` defaults to the event type when a step leaves it
        unset (``append_event``: ``event_kind or event_type_str``), so two steps
        sharing an ``operation_id`` but differing in ``event_type`` have
        DIFFERENT durable identities and both append — a run legitimately emits
        several kinds under one operation. The collision guard above fires only on
        the SAME ``(operation_id, event_kind, attempt)``.
        """
        if not step.operation_id:
            raise ValueError("apply_run_step requires a durable operation_id")
        try:
            self.append_event(
                step.task_id,
                step.agent_role,
                step.event_type,
                step.payload,
                operation_id=step.operation_id,
                attempt=step.attempt,
                event_kind=step.event_kind,
                predecesseur_ulid=step.predecesseur_ulid,
                ulid=step.ulid,
            )
            return True
        except sqlite3.IntegrityError:
            existing = self._event_by_identity(step)
            if existing is None:
                raise  # a DIFFERENT integrity violation — never ours to absorb
            event_type_str = (
                step.event_type.value if isinstance(step.event_type, EventType)
                else str(step.event_type)
            )
            # T-00000641 puis T-00000680 : `existing` (ledger, RÉDIGÉ) et l'entrant (rédigé, sérialisé
            # comme `append_event`) relus en paires triées À PLAT — ordre des clés ignoré, doublons GARDÉS.
            def _paires(p: list) -> dict:  # 2 niveaux par objet (3 : RecursionError dès ~329 en 3.11)
                doublee = len({k for k, _ in p}) < len(p)  # clé doublée : départage par la valeur
                tri = sorted(p, key=lambda kv: (kv[0], json.dumps(kv[1])) if doublee else kv[0])
                return {"\0": [x for kv in tri for x in kv]}
            def canon(texte: str | bytes) -> str:
                return json.dumps(json.loads(texte, object_pairs_hook=_paires))
            motif = (f"same durable identity, DIFFERENT content: operation_id={step.operation_id!r} "
                     f"event_kind={self._resolved_kind(step)!r} attempt={step.attempt} — a run step "
                     "is reusing a durable identity already spent by a different event")
            entrant = canon(json.dumps(_redaction().rediger_arbre(step.payload), ensure_ascii=False))
            try:  # STOCKÉ illisible (JSON, BLOB non UTF-8, imbrication, entier géant) = DIVERGENT
                meme = canon(existing["payload_json"]) == entrant  # HORS except : jamais chaîné
            except (ValueError, RecursionError):  # JSONDecodeError, UnicodeDecodeError ⊂ ValueError
                meme = False
            if not meme or (existing["task_id"], existing["agent_role"],
                            existing["event_type"]) != (step.task_id, step.agent_role,
                                                        event_type_str):
                raise ValueError(motif)
            return False

    def replay_run(self, steps: Iterable[RunStep]) -> Dict[str, int]:
        """Replay a whole run from its start, idempotently.

        Steps already present are skipped, missing steps are appended — so a run
        interrupted after ANY step can be resumed by replaying it entire: the
        final ``task_projections`` state and the ``events_ledger`` count match a
        single clean run (no event duplicated, no effect applied twice).
        Returns a ``{applied, skipped, total}`` tally.
        """
        applied = skipped = 0
        for step in steps:
            if self.apply_run_step(step):
                applied += 1
            else:
                skipped += 1
        return {"applied": applied, "skipped": skipped, "total": applied + skipped}

    # --- T-00000691 : reconstruction depuis runs/ -------------------------------
    # Pont board compris, en UNE transaction, déclenchée d'office à l'ouverture
    # d'une base VIDE, lecture CONTENUE, trois filets DISJOINTS (S la sonde, R la
    # lecture + la transaction, N le nettoyage des journaux) — aucun n'enveloppe
    # un autre, chacun a son témoin qui le mord seul.

    def _remede_reconstruction(self, cause: str) -> str:
        """Le remède écrit d'une reconstruction non commitée. Jamais « la même
        commande » tel quel : (a) nomme ce qu'une NOUVELLE construction fait."""
        if cause == "DIFFEREE":
            return (
                "remede : reparer cadre.ledger.redaction (paquet installe, ou "
                f"{_CHEMIN_REDACTION}) puis python3 .agents/bin/tasks.py replay-sync"
            )
        return (
            "remede : (a) python3 .agents/bin/tasks.py replay-sync [nouvelle "
            "construction : retente la base encore vide, rejoue les intents "
            "differes] ; (b) \"database is locked\" repete : une autre session tient "
            "la base, attendre ; (c) \"database or disk is full\" : disque plein, "
            "liberer de la place puis (a) ; (d) \"malformed\", \"disk I/O\", "
            "\"readonly\", \"MemoryError\" : reparer, reduire runs/, ou supprimer "
            f"{self.db_path.name}* sous {self.db_path.parent} puis (a)"
        )

    @staticmethod
    def _remede_sonde(exc: BaseException) -> Optional[str]:
        """Le remède PROPRE à une sonde qui a levé sur un dossier de `runs/`
        illisible (S-00002557 : un `runs/` au SEUL dossier illisible bloquait toute
        écriture, et le remède générique — rejouer, supprimer la base — ne répare
        pas un dossier illisible). `None` pour toute autre cause."""
        chemin = getattr(exc, "filename", None) if isinstance(exc, OSError) else None
        if not chemin:
            return None
        return (
            f"remede : rendre lisible {chemin} (chmod u+rx) ou le retirer de runs/, "
            "puis python3 .agents/bin/tasks.py replay-sync"
        )

    def _refuser_si_reconstruction_due(self) -> None:
        """Garde d'écriture (T-00000691, S-00002372). Tant qu'une reconstruction
        automatique DUE n'a pas été commitée sur cette instance, rien ne s'écrit :
        aucun événement, lien, réservation, projection, inbox ni rejeu de journal
        — sinon la base deviendrait NON vide et ne serait plus jamais reconstruite
        d'office (S-00002370). Borne écrite : les baux de l'outbox
        (`claim/renew/release_board_command`) ne sont PAS gardés — aucun appelant
        de production, et l'outbox est vide sur une base vide."""
        if not getattr(self, "_reconstruction_bloquee", False):
            return
        cause = getattr(self, "_cause_reconstruction", None) or "AVORTEE"
        remede = getattr(self, "_remede_particulier", None) or self._remede_reconstruction(cause)
        raise ReconstructionAvorteeError(
            f"ecriture V3 refusee : reconstruction automatique {cause} sur cette "
            f"instance (une nouvelle ouverture retentera) ; {remede}"
        )

    def exiger_ecriture_permise(self) -> None:
        """Garde PUBLIQUE (T-00000691, S-00002519) : lève
        `ReconstructionAvorteeError` — sans rien écrire — tant qu'une
        reconstruction automatique due n'est pas commitée sur cette instance.

        Pour l'appelant qui écrit dans la base HORS de l'écrivain unique AVANT d'y
        écrire un événement : `SpecParser.process_and_sync_spec` commite
        `spec_requirements` puis `SPEC_MUTATED`. Sans cette garde avant sa
        PREMIÈRE écriture, la version était commitée, l'événement refusé, et au sync
        suivant la version « UP-TO-DATE » ne l'émettait jamais (S-00002518 F2)."""
        self._refuser_si_reconstruction_due()

    def _racine_runs(self) -> Path:
        """La racine SOUS laquelle vit `runs/`, résolue EXACTEMENT comme l'écrivain :
        `run_export.chemin_export` compose `project_root(depuis=…)/runs/…`
        (`$CADRE_PROJECT_ROOT`, sinon racine GIT). Sonder et lire sous
        `self.project_root` BRUT rendait la reconstruction INERTE sur un monorepo dont
        `.agents/` vit sous `apps/foo/` : l'écrivain exporte sous la racine git, la
        sonde ne voyait rien (S-00002518 F1). Peut lever (`CadrePathError`, couture
        absente) : n'est appelée que sous les filets S et R."""
        return Path(run_export.project_root(depuis=self.project_root))

    def _reconstruction_due(self) -> bool:
        """La SONDE « vide ? » : vrai si `events_ledger` est VIDE ET que `runs/` —
        sous `_racine_runs()`, la racine de l'ÉCRIVAIN — porte au moins un export
        candidat OU un lien refusé (la lecture le NOMMERA). Le `SELECT` d'abord —
        une base peuplée rend `False` sans toucher `runs/`, donc n'est jamais
        bloquée par un `runs/` illisible ; le parcours ensuite, par
        `_parcourir_runs` (aucun lien suivi).

        Un dossier illisible n'est JAMAIS « rien de dû » (S-00002518 F4 : le glob
        l'avalait et la sonde certifiait « rien à faire », l'écriture suivante
        rendait la base non vide, son contenu perdu pour ce clone) : si rien d'autre
        n'a rendu la reconstruction due, sa première `OSError` est LEVÉE — au filet
        S, qui bloque l'écriture. Un candidat trouvé suffit, dans n'importe quel
        ordre : la lecture comptera l'illisible. Sondée HORS verrou ;
        `_reconstruire` RE-VÉRIFIE sous `BEGIN IMMEDIATE`."""
        conn = get_db_connection(self.db_path)
        try:
            if conn.execute("SELECT 1 FROM events_ledger LIMIT 1").fetchone() is not None:
                return False
        finally:
            conn.close()
        refuses: List[Path] = []
        erreurs: List[Tuple[Path, OSError]] = []
        for _candidat in _parcourir_runs(self._racine_runs(), refuses, erreurs):
            return True
        if refuses:
            return True
        if erreurs:
            raise erreurs[0][1]
        return False

    def _reconstruire_si_vide(self) -> bool:
        """Reconstruction d'office d'une base vide au chemin par défaut.
        Une base vivante suit la synchro avec sauvegarde, sans reconstruction.

        Filet S : `_reconstruction_due()` seule, de la connexion au parcours.
        Une sonde en échec ne certifie pas « rien de dû » : drapeau LEVÉ, cause
        `NON TENTEE`, et l'instance n'écrit rien (écrire rendrait la base non
        vide, donc jamais plus reconstruite — perte silencieuse). `_reconstruire`
        est appelé APRÈS ce `try`, HORS de lui (filets R et N distincts).

        Rend `True` quand une reconstruction etait DUE (tentee, commitee, sautee, avortee, differee ou non
        tentee), `False` sinon : `__init__` s'en sert pour ne pas sonder l'ecart apres une reconstruction."""
        try:
            due = self._reconstruction_due()
        except Exception as exc:
            self._reconstruction_bloquee = True
            self._cause_reconstruction = "NON TENTEE"
            # S-00002557 : un dossier illisible SEUL sous runs/ — le remède dit de
            # le rendre lisible ou de le retirer, ici ET dans le refus d'écriture.
            self._remede_particulier = self._remede_sonde(exc)
            print(
                "event_store: reconstruction automatique non tentee : "
                f"{type(exc).__name__}: {exc} — ecritures V3 refusees sur cette "
                "instance ; "
                f"{self._remede_particulier or self._remede_reconstruction('NON TENTEE')}",
                file=sys.stderr,
            )
            return True
        if not due:
            return False
        resume = self._reconstruire(None, si_vide=True)
        self._remede_particulier = None
        if resume["avortee"]:
            self._reconstruction_bloquee, self._cause_reconstruction = True, "AVORTEE"
        elif resume["differee"]:
            self._reconstruction_bloquee, self._cause_reconstruction = True, "DIFFEREE"
        else:  # commitée, ou `saute_non_vide` (base trouvée non vide SOUS le verrou)
            self._reconstruction_bloquee, self._cause_reconstruction = False, None
        return True

    def reconstruire_depuis_exports(
        self, racine: Union[str, Path, None] = None
    ) -> Dict[str, Any]:
        """Reconstruit `events_ledger`, `task_projections` ET le pont board
        (`task_board_mapping`, projections `BOARD:*`, `board_sync_inbox`) depuis
        TOUS les `runs/*/*/*.jsonl` (T-00000650 étape 5, T-00000691) — clause
        « état partagé fusionnable » (Exception nommée : un enregistrement
        autonome par ligne).

        FUSION par `(ulid, auteur/copie)`, jamais par horloge ou index de ligne.
        Lecture inverse volontaire ; les en-têtes `{"borne": …}` sont ignorés.

        CE QUE FAIT L'APPEL, depuis T-00000691 :
          * UNE transaction `BEGIN IMMEDIATE` — un `SAVEPOINT` par ligne (l'écriture
            de l'événement PUIS sa projection, dans le même savepoint) et par
            intent ; tout ou rien pour le lot.
          * le PONT est reprojeté après les événements : les intents board
            (`_KINDS_INTENT_BOARD`) sont rejoués par ordre ULID dans
            `_reduce_board_intent` ; liens `V3:*` (réservés/liés) conservés.
          * lecture contenue : liens physiques et symboliques refusés, fichiers
            trop gros ou illisibles et lignes indécodables comptés et annoncés.
            Le nombre total de fichiers n'est pas borné.
          * `runs/` est cherché sous la racine de l'ÉCRIVAIN (`_racine_runs`), pas
            sous `project_root` brut — sauf `racine` explicite.
          * trois filets disjoints : lecture, transaction et nettoyage. Un échec
            rend `avortee=1` et une base inchangée ; stderr fermé peut lever.
          * ce n'est plus seulement un appel explicite : la construction d'un
            `EventStore` sur une base VIDE au chemin par défaut, alors que `runs/`
            porte des exports, la déclenche d'office (`_reconstruire_si_vide`) ; et
            tant qu'une telle reconstruction DUE n'est pas commitée, l'instance
            refuse toute écriture au registre d'événements et au pont board
            (événement, lien, réservation, projection, inbox, rejeu de journal) et
            `sync-spec` refuse avant sa première écriture
            (`ReconstructionAvorteeError`). NON gardés, écrit : les baux de
            l'outbox (`claim/renew/release_board_command`), les checkpoints de
            session et les leçons.

        Ici (appel EXPLICITE) : un commit rabaisse le drapeau de l'instance ; un
        avortement le laisse INCHANGÉ ; une rédaction indisponible écrit les
        événements et laisse le pont tel quel (`pont_non_rebati=1`). Le résumé
        porte TOUJOURS toutes ses clés."""
        resume = self._reconstruire(racine, si_vide=False)
        if not resume["avortee"]:
            self._reconstruction_bloquee, self._cause_reconstruction = False, None
            self._remede_particulier = None
        return resume

    def _reconstruire(
        self, racine: Union[str, Path, None], *, si_vide: bool
    ) -> Dict[str, Any]:
        """Reconstruit explicitement ou, sur une base vide, automatiquement.

        Filet R : de la résolution de runs/ au commit, toute panne avorte la
        transaction. La base vide est revérifiée sous verrou ; une base devenue
        non vide n'est pas effacée. Filet N : journaux nettoyés après le commit.
        La synchro d'une base vivante suit `_synchroniser_base_vivante`.
        """
        # Repli d'ANNONCE seulement : la racine lue est résolue SOUS le filet R.
        root = Path(racine) if racine is not None else self.project_root
        conn: Optional[sqlite3.Connection] = None
        resume: Dict[str, Any] = {
            "applied": 0, "total": 0, "ignores": 0, "malformes": 0, "echecs": 0,
            "lignes_illisibles": 0, "fichiers_illisibles": 0, "fichiers_trop_gros": 0,
            "avortee": 0, "differee": 0, "saute_non_vide": 0,
            "pont_intents": 0, "pont_ecartes": 0, "pont_deja_vus": 0,
            "pont_remplaces": 0, "pont_non_rebati": 0, "faux_failed": 0,
            "echecs_sans_failed": 0, "failed_hors_intent": 0,
            "failed_v3_vers_board": 0,
            "divergentes": 0, "divergentes_ulid": [],
            "auteurs_rejoues": [],
        }
        # F5 : événements VALIDES lus de runs/ et ABSENTS d'une base trouvée non vide
        # sous le verrou (`None` : pas de saut).
        manquants_saute: Optional[int] = None
        chemins: Dict[str, List[Path]] = {
            "fichiers_illisibles": [], "fichiers_trop_gros": [], "lignes_illisibles": [],
        }
        entres: Set[str] = set()  # ULID ENTRÉS dans un SAVEPOINT — seuls nettoyés (N)
        auteurs: Set[str] = set()
        cause_redaction: Optional[BaseException] = None
        raison_pont: Optional[str] = None
        pont_ecartes_nommes: List[str] = []
        # --- Filet R : lecture + transaction, jusqu'au `commit` inclus. ---
        try:
            if racine is None:
                root = self._racine_runs()  # S-00002518 F1 : la racine de l'écrivain
            evenements = self._lire_exports(root, resume, chemins)
            # Fusion : ULID croissant, puis <auteur>/<copie>. JAMAIS created_at.
            evenements.sort(key=lambda t: (t[0], t[1]))
            resume["total"] = len(evenements)
            # R1 : la branche DIFFÉRÉE est clée sur l'APPEL, jamais sur un type —
            # `_redaction()` lève `RuntimeError`, dont `RecursionError` hérite : un
            # `except` typé plus bas l'étiquetterait mal.
            try:
                redaction = _redaction()
            except Exception as exc:
                redaction, cause_redaction = None, exc
            if redaction is None and si_vide:
                resume["differee"] = 1
            else:
                conn = get_db_connection(self.db_path)
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                if si_vide and cursor.execute(
                    "SELECT 1 FROM events_ledger LIMIT 1"
                ).fetchone() is not None:
                    # Une autre session a écrit entre la sonde et le verrou : la base
                    # n'est plus vide, on ne reconstruit pas par-dessus (S-00002370).
                    # F5 : mesurer, SOUS le verrou, ce que runs/ porte de valide et
                    # que la base n'a pas — une session qui a elle-même reconstruit
                    # ne manque de rien (silence), une session qui n'a écrit qu'UN
                    # événement laisse l'historique dehors (annoncé).
                    manquants_saute = self._compter_manquants(cursor, evenements)
                    conn.rollback()
                    resume["saute_non_vide"] = 1
                else:
                    self._appliquer_lignes(cursor, evenements, resume, entres, auteurs)
                    if redaction is None:
                        resume["pont_non_rebati"] = 1
                        raison_pont = (
                            f"redaction indisponible : {type(cause_redaction).__name__}: "
                            f"{cause_redaction} ; evenements ecrits, "
                            f"{self._remede_reconstruction('DIFFEREE')}"
                        )
                    else:
                        compteurs, pont_ecartes_nommes, raison_pont = self._rebatir_pont(
                            cursor, redaction
                        )
                        resume.update(compteurs)
                    conn.commit()
        except Exception as exc:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.rollback()  # un rollback sur disque en panne lève aussi
            resume["avortee"] = 1
            refus = " — ecritures V3 refusees sur cette instance" if si_vide else ""
            print(
                "event_store: reconstruction AVORTEE, rien ecrit "
                f"({type(exc).__name__}: {exc}){refus} ; "
                f"{self._remede_reconstruction('AVORTEE')}",
                file=sys.stderr,
            )
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()
        if resume["avortee"]:
            resume["applied"] = 0  # rien n'a été commité
            auteurs.clear()
        resume["auteurs_rejoues"] = sorted(auteurs)
        # --- Filet N : APRÈS R et HORS de lui. ---
        if entres:
            self._nettoyer_journaux(entres)
        self._annoncer_reconstruction(
            root, resume, chemins, si_vide=si_vide, cause_redaction=cause_redaction,
            raison_pont=raison_pont, pont_ecartes_nommes=pont_ecartes_nommes,
            manquants_saute=manquants_saute,
        )
        return resume

    def _compter_manquants(self, cursor: sqlite3.Cursor, evenements: List[tuple]) -> int:
        """Nombre d'événements que le rejeu insérerait et que la base n'a pas."""
        return len(self._manquants_nommes(cursor, evenements))

    def _manquants_nommes(self, cursor: sqlite3.Cursor, evenements: List[tuple]) -> Dict[str, str]:
        """ULID que le rejeu ordonné insérerait, dédoublonnés aussi par identité durable."""
        en_base_ulids: Set[str] = {
            ulid for (ulid,) in cursor.execute("SELECT ulid FROM events_ledger WHERE ulid IS NOT NULL")
        }
        manquants: Dict[str, str] = {}
        vus: Set[str] = set()
        banc: Optional[sqlite3.Connection] = None
        try:
            for ulid, tie, obj in evenements:
                if ulid in vus:
                    continue
                vus.add(ulid)
                if not _obj_reconstruction_valide(obj) or ulid in en_base_ulids:
                    continue
                if banc is None:
                    banc = self._banc_a_blanc(cursor)
                if self._appliquable_a_blanc(banc, cursor, ulid, obj):
                    manquants[ulid] = tie
        finally:
            if banc is not None:
                banc.close()
        return manquants

    def _synchroniser_base_vivante(self, partition: Path) -> Dict[str, Any]:
        resultat: Dict[str, Any] = dict(ecart=0, applied=0, inhibee=False, avortee=False, sauvegarde=None)
        conn: Optional[sqlite3.Connection] = None
        sauvegarde_echouee = False
        try:
            conn = self._connexion_lecture()
            if conn.execute("SELECT 1 FROM events_ledger LIMIT 1").fetchone() is None:
                return resultat
            autorisee = event_store_sync.autorisee(partition, self.project_root)
            racine = self._racine_runs()
            if self._taille_runs(racine) > _SONDE_RUNS_MAX_OCTETS:
                resultat["non_sonde"] = True
                return resultat
            resume = dict(fichiers_illisibles=0, fichiers_trop_gros=0, lignes_illisibles=0, ignores=0)
            chemins: Dict[str, List[Path]] = {
                cle: [] for cle in ("fichiers_illisibles", "fichiers_trop_gros", "lignes_illisibles")}
            evenements = self._lire_exports(racine, resume, chemins)
            resultat.update(resume, malformes=sum(not _obj_reconstruction_valide(o) for _, _, o in evenements))
            evenements.sort(key=lambda t: (t[0], t[1]))
            voulus = {u for u, _t, _o in evenements}
            en_base = {ligne[0]: dict(zip(run_export._CHAMPS_DIVERGENCE, ligne[1:]))
                       for ligne in conn.execute("SELECT ulid, " + ", ".join(run_export._CHAMPS_DIVERGENCE)
                                                 + " FROM events_ledger WHERE ulid IS NOT NULL") if ligne[0] in voulus}
            divergentes, divergentes_ulid = event_store_sync.divergences(
                evenements, en_base, run_export._CHAMPS_DIVERGENCE, _DIVERGENTES_NOMMEES_MAX)
            resultat.update(divergentes=divergentes, divergentes_ulid=divergentes_ulid)
            manquants = self._manquants_nommes(conn.cursor(), evenements) if evenements else {}
            resultat.update(ecart=len(manquants), nommes=manquants)
            if not manquants:
                return resultat
            if not autorisee:
                resultat["inhibee"] = True
                return resultat
            neuve = (identite := int(conn.execute("PRAGMA application_id").fetchone()[0])) == 0
            identite = secrets.randbelow(2**31 - 2) + 1 if neuve else identite
            conn.close()
            conn = None
            try:
                resultat["sauvegarde"] = event_store_sync.sauvegarder(
                    partition, self.db_path, lambda c: c.execute("PRAGMA data_version").fetchone()[0], identite)
            except Exception:
                sauvegarde_echouee = True
                raise
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            manquants = self._manquants_nommes(cursor, evenements)
            resultat.update(ecart=len(manquants), nommes=manquants)
            if not manquants:
                conn.rollback()
                return resultat
            if neuve:
                cursor.execute("PRAGMA application_id = " + str(identite))
            avant = self._comptes_sync(cursor)
            resume_import = dict(applied=0, malformes=0, echecs=0, divergentes=0, divergentes_ulid=[])
            self._appliquer_lignes(cursor, evenements, resume_import, set(), set())
            touches = {o["task_id"] for u, _t, o in evenements if u in manquants}
            touches.update(r[0] for r in cursor.execute(
                "SELECT v3_task_id FROM task_board_mapping WHERE v3_task_id NOT GLOB 'BOARD:*'"
            ))
            redaction = _redaction()
            compteurs_pont, _ecartes, raison_pont = self._rebatir_pont(
                cursor, redaction, projection_tasks=touches)
            if compteurs_pont["pont_non_rebati"]:
                raise ValueError(raison_pont or "pont non rebati")
            apres = self._comptes_sync(cursor)
            conn.commit()
            resultat.update(applied=resume_import["applied"], avant=avant, apres=apres,
                            divergentes=divergentes, divergentes_ulid=divergentes_ulid,
                            echecs=resume_import["echecs"], malformes=resume_import["malformes"],
                            pont_ecartes=compteurs_pont["pont_ecartes"], ecartes_nommes=_ecartes)
        except Exception as exc:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.rollback()
            resultat["avortee"] = True
            resultat["erreur"] = f"{type(exc).__name__}: {exc}"
            if sauvegarde_echouee:
                self._reconstruction_bloquee, self._cause_reconstruction = True, "SYNCHRO AVORTEE"
                self._remede_particulier = "reparer la cause et rouvrir le store"
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()
        return resultat

    @staticmethod
    def _comptes_sync(cursor: sqlite3.Cursor) -> Tuple[int, int, int]:
        return (cursor.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0],
                cursor.execute("SELECT COUNT(*) FROM task_board_mapping").fetchone()[0],
                cursor.execute("SELECT COUNT(*) FROM task_projections").fetchone()[0])

    def _lire_exports(
        self, root: Path, resume: Dict[str, Any], chemins: Dict[str, List[Path]]
    ) -> List[tuple]:
        """Lecture sans lien et bornée, sous le filet R ; couture patchable."""
        return event_store_sync.lire_exports(
            root, resume, chemins, _parcourir_runs, _lire_export_sans_lien, json
        )

    def _ecrire_et_projeter(self, cursor: sqlite3.Cursor, ulid: str, obj: Dict[str, Any]) -> None:
        """UNE definition de ce que la reconstruction APPLIQUE pour une ligne de forme valide : l'ecrivain
        (`_ecrire_evenement`) PUIS le projecteur (`_apply_projection`), a portee de CURSEUR, dans le savepoint
        de l'appelant. Partagee par `_appliquer_lignes` (la base vivante) et `_appliquable_a_blanc` (le banc
        `:memory:` de la sonde) : l'ecart que la sonde annonce est CE QUE la reconstruction inserera, jamais
        une enumeration de classes hostiles qu'un nouveau cas rend fausse (NO_GO it. 3, C1).
        BLOQUANT 1(a) : la reconstruction LIT depuis l'export et n'a RIEN a exporter - `journaliser=False`."""
        self._ecrire_evenement(
            cursor,
            obj["task_id"],
            obj["agent_role"],
            obj["event_type"],
            obj["payload_json"],
            operation_id=obj.get("operation_id"),
            event_kind=obj.get("event_kind"),
            attempt=int(obj.get("attempt", 0)),
            predecesseur_ulid=obj.get("predecesseur_ulid"),
            ulid=ulid,
            created_at=obj.get("created_at"),
            journaliser=False,
        )
        try:
            payload = json.loads(obj["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        self._apply_projection(cursor, obj["task_id"], obj["agent_role"], obj["event_type"], payload)

    @staticmethod
    def _banc_a_blanc(cursor: sqlite3.Cursor) -> sqlite3.Connection:
        """Un banc `:memory:` qui porte le schema du store LU (`sqlite_master` : les deux tables et leurs deux
        index uniques - jamais une seconde copie du DDL, qui deriverait). Une table absente leve `sqlite3.Error` :
        la sonde le dit (« NON sonde »)."""
        banc = sqlite3.connect(":memory:", isolation_level=None)
        try:
            ddl = cursor.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name IN "
                "('events_ledger', 'task_projections', 'uq_events_operation_attempt', 'uq_events_ulid') "
                "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"
            ).fetchall()
            for (sql,) in ddl:
                banc.execute(sql)
        except BaseException:
            banc.close()
            raise
        return banc

    def _appliquable_a_blanc(
        self, banc: sqlite3.Connection, cursor: sqlite3.Cursor, ulid: str, obj: Dict[str, Any]
    ) -> bool:
        """Vrai si la reconstruction INSERERAIT cette ligne. (1) `_ecrire_et_projeter` joue sur le banc, dans un
        SAVEPOINT : une erreur de DONNEE (`IntegrityError` comprise : `req_id` ou `spec_version` nuls, que la
        reconstruction compte `echecs`, C5 it. 4) rend faux, une panne SYSTEME (`_est_panne_systeme`) remonte,
        comme dans `_appliquer_lignes` ; (2) l'identite durable `(operation_id, event_kind, attempt)` que l'ecrivain
        vient d'ECRIRE sur le banc, RELUE telle quelle (jamais recalculee depuis `obj` : C2 it. 4), est-elle DEJA
        PRISE dans la base VIVANTE ? Son propre moteur tranche, affinite de colonne comprise (un `operation_id`
        entier 5 y rencontre le texte '5') ; (3) un succes est GARDE sur le banc (les candidates suivantes y
        rencontrent ses cles, comme a la reconstruction), un echec est defait."""
        banc.execute("SAVEPOINT a_blanc")
        try:
            self._ecrire_et_projeter(banc, ulid, obj)
            identite = banc.execute(
                "SELECT operation_id, event_kind, attempt FROM events_ledger WHERE ulid = ?", (ulid,)
            ).fetchone()
            if cursor.execute(
                "SELECT 1 FROM events_ledger WHERE operation_id = ? AND event_kind = ? AND attempt = ? LIMIT 1",
                identite,
            ).fetchone() is not None:
                raise sqlite3.IntegrityError("identite durable deja en base")
        except Exception as exc:
            if _est_panne_systeme(exc):
                raise
            banc.execute("ROLLBACK TO SAVEPOINT a_blanc")
            banc.execute("RELEASE SAVEPOINT a_blanc")
            return False
        banc.execute("RELEASE SAVEPOINT a_blanc")
        return True

    def _appliquer_lignes(
        self,
        cursor: sqlite3.Cursor,
        evenements: List[tuple],
        resume: Dict[str, Any],
        entres: Set[str],
        auteurs: Set[str],
    ) -> None:
        """Phase 1, DANS la transaction de l'appelant : un `SAVEPOINT` par ligne —
        l'écriture de l'événement (`journaliser=False`) PUIS sa projection
        (`_apply_projection`), dans le MÊME savepoint. `IntegrityError` d'UNICITÉ
        (`_contrainte_unique`) : ULID déjà en base ⇒ déjà présent, idempotent ; identité
        durable déjà prise sous un autre ULID ⇒ identité déjà prise : écartée sans bruit,
        contenu non comparé (borne de portée du plan). Un NOT NULL de projection est un
        échec (C5 it. 4) ; une panne SYSTÈME (`_est_panne_systeme` : E/S, disque
        plein, corruption, `MemoryError`) REMONTE au filet R — le lot est AVORTÉ,
        jamais commité partiel (S-00002560) ; toute autre levée (erreur de DONNÉE)
        ⇒ `echecs`, ANNONCÉE, la ligne seule est défaite. La contention de verrou
        n'arrive plus ici : elle se prend au `BEGIN IMMEDIATE` et avorte le lot."""
        vus: Dict[str, Dict[str, Any]] = {}
        divergents: Set[str] = set()
        for ulid, tie, obj in evenements:
            if ulid in vus:
                # T-01M4N496YD7BZDA2NHYQ73JND9 : un ULID REVU. Identique => silence (doublon de `merge=union`) ;
                # un des 9 champs de `run_export._CHAMPS_DIVERGENCE` differe => COMPTE (par ULID) et NOMME,
                # jamais repare. La ligne GARDEE reste la premiere dans l'ordre (ulid, auteur/copie).
                if ulid not in divergents and any(
                    obj.get(c) != vus[ulid].get(c) for c in run_export._CHAMPS_DIVERGENCE
                ):
                    divergents.add(ulid)
                    resume["divergentes"] += 1
                    if len(resume["divergentes_ulid"]) < _DIVERGENTES_NOMMEES_MAX:
                        resume["divergentes_ulid"].append(ulid)
                continue
            vus[ulid] = obj
            # BLOQUANT 2 (les deux revues) : valider présence ET type des quatre
            # champs consommés AVANT d'entrer dans le savepoint — une seule ligne
            # hostile (task_id absent, attempt non numérique, payload non-chaîne)
            # niait TOUT l'historique.
            if not _obj_reconstruction_valide(obj):
                resume["malformes"] += 1
                continue
            cursor.execute("SAVEPOINT reconstruction_ligne")
            # R2 : seul un ULID ENTRÉ dans un savepoint (appliqué, déjà présent, ou
            # en échec base) voit son journal nettoyé par le filet N — jamais une
            # ligne ignorée, hors forme ou illisible, dont le journal reste la
            # seule trace réparable par le rejeu.
            entres.add(ulid)
            try:
                self._ecrire_et_projeter(cursor, ulid, obj)
            except Exception as exc:
                if _est_panne_systeme(exc):
                    # S-00002560 : une panne SYSTÈME sur UNE ligne n'est pas un échec
                    # de ligne — la compter laissait commiter une base PARTIELLE, donc
                    # NON vide, jamais plus reconstruite. Relevée AVANT le `ROLLBACK
                    # TO` : sur SQLITE_FULL, SQLite a déjà défait la transaction, et
                    # ce `ROLLBACK TO` lèverait « no such savepoint », qui MASQUAIT
                    # « database or disk is full » dans l'annonce du filet R.
                    raise
                cursor.execute("ROLLBACK TO SAVEPOINT reconstruction_ligne")
                cursor.execute("RELEASE SAVEPOINT reconstruction_ligne")
                if _contrainte_unique(exc):
                    # ULID deja en base : idempotent. Identite deja prise : ecartee sans bruit, contenu non
                    # compare (borne de portee dite). Jamais un NOT NULL (C5 it. 4) : celui-la va aux `echecs`.
                    continue
                resume["echecs"] += 1
                print(
                    f"event_store: reconstruction — ligne ecartee (echec base) "
                    f"ulid={ulid} : {exc}",
                    file=sys.stderr,
                )
                continue
            cursor.execute("RELEASE SAVEPOINT reconstruction_ligne")
            resume["applied"] += 1
            auteurs.add(tie.split("/", 1)[0])

    def _rebatir_pont(
        self, cursor: sqlite3.Cursor, redaction: Any,
        projection_tasks: Optional[Set[str]] = None,
    ) -> Tuple[Dict[str, int], List[str], Optional[str]]:
        """Phase 2 (§ 2 point 2), DANS la transaction de l'appelant — donc sous le
        filet R. Rend `(compteurs, intents écartés nommés, raison du non-rebâti)`.

        Un intent sans ULID interdit l'ordre de rejeu : pont NON rebâti, liens et
        projections board laissés tels quels (`pont_non_rebati=1`). Sinon :
        effacer l'inbox, les projections `BOARD:*` et les liens `BOARD:*` (les
        liens `V3:*` réservés puis liés survivent), rejouer les intents par ordre
        ULID dans `_reduce_board_intent`, chacun dans son `SAVEPOINT` — intent hors
        forme, identité divergente ou réduction qui lève ⇒ `pont_ecartes`, jamais
        un avortement ; `effect_json = rediger_arbre(effect)`, comme
        `consume_board_intent`.

        PANNE SYSTÈME ≠ INTENT HOSTILE (addendum exec-critic, avis L de S-00002509) :
        une `sqlite3.Error` de SYSTÈME (E/S, disque plein, base corrompue, verrou)
        ou une `MemoryError` au rejeu d'un intent REMONTE au filet R — reconstruction
        AVORTÉE, rien commité, drapeau levé, retentée à la construction suivante.
        Sinon chaque intent était « écarté » tour à tour, puis le `commit`
        enregistrait une base aux événements rebâtis et au pont VIDE, jamais plus
        reconstruite (base non vide). Les erreurs SQLite qu'une DONNÉE suffit à
        provoquer (`_ERREURS_SQLITE_DE_DONNEES`, mesuré : `owner` objet ⇒
        `ProgrammingError`) restent des écarts : les faire avorter laisserait UNE
        ligne fusionnée bloquer toute reconstruction, à chaque ouverture.

        Les `BOARD_COMMAND_FAILED` sont appariés à leur cause par
        `(operation_id, event_kind de l'intent)` lu dans LEUR payload — jamais par
        adjacence ULID (S-00002334 : un FAILED peut trier avant sa cause). FAILED
        dont la cause réussit au rejeu ⇒ `faux_failed` ; intent qui échoue sans
        FAILED ⇒ `echecs_sans_failed` ; FAILED d'une commande V3 → board (payload
        objet SANS clé `intent` : le drain de l'outbox, `board_bridge`) ⇒
        `failed_v3_vers_board`, un échec NORMAL, compté à part (critic-fable) ;
        FAILED au payload non analysable, à l'intent hors forme ou sans intent
        rejoué ⇒ `failed_hors_intent`, l'anomalie. Aucun FAILED n'est écrit ici."""
        res = {
            "pont_intents": 0, "pont_ecartes": 0, "pont_deja_vus": 0,
            "pont_remplaces": 0, "pont_non_rebati": 0, "faux_failed": 0,
            "echecs_sans_failed": 0, "failed_hors_intent": 0,
            "failed_v3_vers_board": 0,
        }
        ecartes_nommes: List[str] = []
        marques = ", ".join("?" * len(_KINDS_INTENT_BOARD))
        sans_ulid = cursor.execute(
            f"SELECT COUNT(*) FROM events_ledger WHERE event_type IN ({marques}) "
            "AND ulid IS NULL",
            _KINDS_INTENT_BOARD,
        ).fetchone()[0]
        if sans_ulid:
            res["pont_non_rebati"] = 1
            return res, ecartes_nommes, (
                f"{sans_ulid} intent(s) board sans ulid : ordre de rejeu indefinissable"
            )
        echecs_par_cle: Dict[tuple, int] = {}
        for ligne in cursor.execute(
            "SELECT operation_id, payload_json FROM events_ledger WHERE event_type=?",
            (EventType.BOARD_COMMAND_FAILED.value,),
        ).fetchall():
            try:
                corps = json.loads(ligne["payload_json"])
            except (ValueError, TypeError, RecursionError, OverflowError):
                corps = None
            if isinstance(corps, dict) and "intent" not in corps:
                res["failed_v3_vers_board"] += 1  # drain V3 → board : pas de cause board
                continue
            intent_echoue = corps.get("intent") if isinstance(corps, dict) else None
            cause = (
                intent_echoue.get("event_kind") if isinstance(intent_echoue, dict) else None
            )
            if not isinstance(cause, str) or ligne["operation_id"] is None:
                res["failed_hors_intent"] += 1
                continue
            cle = (ligne["operation_id"], cause)
            echecs_par_cle[cle] = echecs_par_cle.get(cle, 0) + 1
        intents = cursor.execute(
            "SELECT ulid, operation_id, event_type, attempt, payload_json "
            f"FROM events_ledger WHERE event_type IN ({marques}) ORDER BY ulid",
            _KINDS_INTENT_BOARD,
        ).fetchall()
        cles_intents = {(r["operation_id"], r["event_type"]) for r in intents}
        res["failed_hors_intent"] += sum(
            n for cle, n in echecs_par_cle.items() if cle not in cles_intents
        )
        res["pont_remplaces"] = sum(
            cursor.execute(requete).fetchone()[0]
            for requete in (
                "SELECT COUNT(*) FROM board_sync_inbox",
                "SELECT COUNT(*) FROM task_projections WHERE task_id GLOB 'BOARD:*'",
                "SELECT COUNT(*) FROM task_board_mapping WHERE v3_task_id GLOB 'BOARD:*'",
            )
        )
        cursor.execute("DELETE FROM board_sync_inbox")
        cursor.execute("DELETE FROM task_projections WHERE task_id GLOB 'BOARD:*'")
        cursor.execute("DELETE FROM task_board_mapping WHERE v3_task_id GLOB 'BOARD:*'")
        if projection_tasks is not None:
            for task_id in projection_tasks:
                cursor.execute("DELETE FROM task_projections WHERE task_id=?", (task_id,))
            a_rejouer = cursor.execute(
                "SELECT ulid, operation_id, event_type, attempt, payload_json, "
                "task_id, agent_role FROM events_ledger ORDER BY ulid, event_id"
            ).fetchall()
        else:
            a_rejouer = intents
        for ligne in a_rejouer:
            if projection_tasks is not None and ligne["task_id"] in projection_tasks:
                try:
                    payload = json.loads(ligne["payload_json"])
                except (ValueError, TypeError):
                    payload = {}
                cursor.execute("SAVEPOINT sync_projection")
                try:
                    self._apply_projection(cursor, ligne["task_id"], ligne["agent_role"],
                                           ligne["event_type"], payload)
                except Exception as exc:
                    if _est_panne_systeme(exc):
                        raise
                    cursor.execute("ROLLBACK TO SAVEPOINT sync_projection")
                cursor.execute("RELEASE SAVEPOINT sync_projection")
            if ligne["event_type"] not in _KINDS_INTENT_BOARD:
                continue
            res["pont_intents"] += 1
            cursor.execute("SAVEPOINT pont_intent")
            try:
                effet = self._rejouer_intent(cursor, ligne, redaction)
            except Exception as exc:
                if _est_panne_systeme(exc):
                    raise  # panne SYSTÈME : filet R, AVORTÉE, retentée (docstring)
                cursor.execute("ROLLBACK TO SAVEPOINT pont_intent")
                cursor.execute("RELEASE SAVEPOINT pont_intent")
                res["pont_ecartes"] += 1
                if len(ecartes_nommes) < _CHEMINS_ANNONCES_MAX:
                    ecartes_nommes.append(
                        f"{ligne['operation_id']} ({type(exc).__name__}: {exc})"
                    )
                continue
            cursor.execute("RELEASE SAVEPOINT pont_intent")
            if effet is None:
                res["pont_deja_vus"] += 1
                continue
            applique = bool(effet.get("applied", False))
            echoue = (ligne["operation_id"], ligne["event_type"]) in echecs_par_cle
            if echoue and applique:
                res["faux_failed"] += 1
            elif not echoue and not applique:
                res["echecs_sans_failed"] += 1
        return res, ecartes_nommes, None

    def _rejouer_intent(
        self, cursor: sqlite3.Cursor, ligne: sqlite3.Row, redaction: Any
    ) -> Optional[Dict[str, Any]]:
        """Rejoue UN intent lu dans `events_ledger` (forme RÉDIGÉE, celle que
        `consume_board_intent` a écrite). Rend l'effet réduit, ou `None` si
        l'`operation_id` est DÉJÀ dans l'inbox avec la MÊME identité (rejeu d'un
        autre `attempt` : `pont_deja_vus`). Lève sur toute forme invalide ou
        identité divergente — l'appelant défait le savepoint et compte l'écart."""
        intent = json.loads(ligne["payload_json"])
        if not isinstance(intent, dict):
            raise ValueError(f"intent non-objet ({type(intent).__name__})")
        if (
            intent.get("operation_id") != ligne["operation_id"]
            or intent.get("event_kind") != ligne["event_type"]
        ):
            raise ValueError("operation_id ou event_kind du payload divergent de la ligne")
        attempt = int(ligne["attempt"])
        prior = cursor.execute(
            "SELECT event_kind, payload_json FROM board_sync_inbox WHERE operation_id=?",
            (ligne["operation_id"],),
        ).fetchone()
        if prior is not None:
            prior_payload = json.loads(prior["payload_json"])
            identite = ("event_kind", "affected_task_ids", "before", "after", "revision_sha256")
            if prior["event_kind"] != ligne["event_type"] or {
                champ: prior_payload.get(champ) for champ in identite
            } != {champ: intent.get(champ) for champ in identite}:
                raise ValueError(
                    f"operation identity mismatch for board intent {ligne['operation_id']}"
                )
            return None
        effet = self._reduce_board_intent(cursor, intent)
        cursor.execute(
            """
            INSERT INTO board_sync_inbox
                (operation_id, event_kind, attempt, payload_json, effect_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ligne["operation_id"],
                ligne["event_type"],
                attempt,
                ligne["payload_json"],
                json.dumps(redaction.rediger_arbre(effet), ensure_ascii=False, sort_keys=True),
            ),
        )
        return effet

    def _nettoyer_journaux(self, entres: Set[str]) -> None:
        """Filet N (§ 2 point 10, ceinture) : APRÈS le filet R, HORS de lui. Efface
        les journaux d'attente dont l'ULID est ENTRÉ dans un savepoint (nom de
        fichier `<ulid>.json`, aucune relecture) — même après un avortement : ces
        événements sont DÉJÀ dans `runs/` ; gardés, ils seraient ré-exportés sous
        l'auteur COURANT. Un `except Exception` autour du listage, et un PAR
        journal, pour qu'un refus n'empêche pas les suivants ; ligne annoncée,
        drapeau et `avortee` INCHANGÉS, jamais propagé. Appels par l'attribut de
        module `run_export.…` (jamais un `from … import`) : une greffe du banc
        atteint ce site.

        Borne écrite (R4) : un journal dont l'effacement est refusé est relu par
        le rejeu qui suit ; son export n'est idempotent que pour un journal du
        MÊME auteur — un journal d'un auteur ÉTRANGER, antérieur à T-00000650,
        serait ré-exporté sous l'auteur courant."""
        try:
            journaux = run_export.lister_journaux_attente(depuis=self.project_root)
        except Exception as exc:
            print(
                "event_store: nettoyage des journaux differe, a retirer a la main : "
                f"run/attente (listage) ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )
            return
        for journal in journaux:
            if Path(journal).stem not in entres:
                continue
            try:
                run_export.effacer_journal_attente(journal)
            except Exception as exc:
                print(
                    "event_store: nettoyage des journaux differe, a retirer a la main : "
                    f"{journal} ({type(exc).__name__}: {exc})",
                    file=sys.stderr,
                )

    @staticmethod
    def _nommer_chemins(chemins: List[Path], root: Path) -> str:
        """Au plus `_CHEMINS_ANNONCES_MAX` chemins, relatifs à la racine, puis
        « et N autres » — la borne est ANNONCÉE, jamais une troncature muette."""
        noms = []
        for chemin in chemins[:_CHEMINS_ANNONCES_MAX]:
            try:
                noms.append(str(chemin.relative_to(root)))
            except ValueError:
                noms.append(str(chemin))
        if len(chemins) > _CHEMINS_ANNONCES_MAX:
            noms.append(f"et {len(chemins) - _CHEMINS_ANNONCES_MAX} autres")
        return ", ".join(noms)
