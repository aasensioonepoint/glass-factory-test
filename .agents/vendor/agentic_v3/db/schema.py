"""
SQLite DDL Schema definition for Agentic V3 Event Sourcing engine.
Enforces immutable event ledger, projected task tables, versioned spec registry, and tagged lessons.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Union

from agentic_v3.db import naissance_partition


def DEFAULT_DB_PATH(racine: Optional[Path] = None) -> Path:
    """Le chemin de la base du run, résolu PARESSEUSEMENT sous la partition
    MACHINE du projet (`state_project()/run/v3_event_store.db`) — HORS dépôt
    (T-00000650). `racine` défaut = `project_root()`. Le nom RESTE en MAJUSCULES
    pour que le relevé par symbole retrouve les mêmes sites qu'avant.

    Un défaut d'argument est lié À L'IMPORT (convention Python) : cette valeur
    doit être résolue à CHAQUE appel, donc c'est une FONCTION et jamais une
    constante — un `= DEFAULT_DB_PATH` nu en défaut de paramètre lierait l'objet
    fonction, et `Path(objet_fonction)` lèverait `TypeError`. Les appelants
    passent donc `None` et le corps résout ici (T-00000650, étape 2 b/c)."""
    from agentic_v3.db.run_export import state_project as _state_project

    return _state_project(racine) / "run" / "v3_event_store.db"


# Schema version carried by `PRAGMA user_version`, mirroring events.db
# (.agents/bin/event_store.py:160). Before T-00000628 this was the ONLY of the
# three stores carrying no version at all — inspection alone cannot tell "not yet
# migrated" from "migrated then damaged". `2` is the shape of T-00000650 and
# corresponds to events_ledger carrying its eleven columns (the nine of v1 plus
# `ulid` and `predecesseur_ulid`).
#
# The version gates ONE thing only: the refusal of a store written by a NEWER
# binary (user_version > SCHEMA_VERSION). It does NOT drive the column upgrades —
# those stay piloted by INSPECTION (`PRAGMA table_info` + conditional ALTER), so a
# store already at this version still has its shape checked, never assumed from a
# number.
#
# T-00001223 (S-00004503) moved the spec_requirements key to (file_path, req_id,
# version) WITHOUT a bump: the version only refuses a store from the future, and an
# older binary on a migrated store violates nothing — the new key is WIDER than the
# old uniqueness. The migration is piloted by inspection, in `parse_specs`.
SCHEMA_VERSION = 2


class SchemaVersionError(RuntimeError):
    """The store on disk was written by a NEWER binary.

    `create_tables` REFUSES to touch a store whose `PRAGMA user_version` exceeds
    `SCHEMA_VERSION`: per the invariant « aucune suppression sans trace »
    nothing is destroyed, and an in-place downgrade of
    an unknown future schema cannot be done safely. Roll this binary forward
    instead.
    """


#: Mode d'un store V3 NEUF (T-00000770, décision R1 de T-00000759) : données
#: d'exécution PRIVÉES d'un utilisateur. Avant T-00000770, SQLite le faisait
#: naître en `0o666 & ~umask` (0o644 sous umask 022). Un store présent garde le sien.
_MODE_STORE = 0o600

#: Registre versionné des specs Markdown (T-00001223, décision pilote S-00004503) :
#: la chaîne de versions est propre à CHAQUE fichier — clé (file_path, req_id,
#: version), le chemin tel que passé à `sync-spec`. Avant, la clé était (req_id,
#: version) : deux fichiers portant le même id partageaient une chaîne et
#: enregistraient de faux SPEC_MUTATED. Texte IDENTIQUE octet pour octet à
#: `_V3_SPEC_REQUIREMENTS` de `src/cadre/ledger/stores_schemas.py`, indentation du
#: corps comprise (`sqlite_master.sql` la garde, `PariteDesSchemasTests` la compare).
#: Seul créateur de la table : `create_tables`, et la migration de
#: `parse_specs.SpecParser._migrer_cle_spec`, qui recrée sous ce même texte.
SPEC_REQUIREMENTS_DDL = """
    CREATE TABLE IF NOT EXISTS spec_requirements (
        req_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        file_path TEXT NOT NULL,
        section_title TEXT NOT NULL,
        content_markdown TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        PRIMARY KEY (file_path, req_id, version)
    );
    """


def _couture_ledger_store():
    """`(cadre.ledger.store, cadre.workspace)` par la couture de
    `run_export` (`_couture_ledger_store`), importée PARESSEUSEMENT — comme
    `DEFAULT_DB_PATH` dépend déjà de `run_export._cadre("paths")` : un import au
    niveau module ferait un cycle. Couture indisponible -> `PanneInfrastructure`
    qui nomme `cadre.ledger.store`."""
    from agentic_v3.db.run_export import _couture_ledger_store as couture

    return couture()


def _connexion_nue(uri: str) -> sqlite3.Connection:
    """La connexion NUE (aucun PRAGMA d'écriture) que la primitive ouvre sur
    l'URI `file:…?mode=rw` qu'elle a vérifiée — `timeout` 30 s, celui que
    `get_db_connection` a toujours posé (`busy_timeout` lu par exécution par
    `test_l_attente_d_un_ecrivain_egale_celle_du_producteur_V3`)."""
    return sqlite3.connect(uri, uri=True, timeout=30.0)


def get_db_connection(db_path: Union[str, Path, None] = None) -> sqlite3.Connection:
    """Returns a thread-safe SQLite connection with WAL mode enabled.

    T-00000770 — the store is opened WITHOUT FOLLOWING and WITHOUT CREATING it,
    through `cadre.ledger.store` (`refuser_les_liens`, then
    `ouvrir_sans_suivre(creer=False)`): a link (symbolic or a second hard name),
    a non-regular file or a name that changes between the check and the open
    raises `ValueError` naming it, and nothing is followed. An ABSENT store
    raises `ValueError` too, naming the path and the remedy — `create_tables`
    first: this function no longer creates the store (every production
    constructor calls `create_tables` in the same `__init__`, so « deleting
    `v3_event_store.db*` re-arms » still holds BEFORE construction; a store
    deleted DURING a run now raises instead of being reborn empty). Its parent
    directory is still created, as before — unless that creation would give birth
    to the state partition of a disposable root without `CADRE_STATE_DIR`
    (T-00000753: `EmplacementRefuse`, nothing created). `":memory:"` is refused."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH()
    path_obj = Path(db_path)
    naissance_partition.garder_store(path_obj)  # T-00000753 : AVANT le mkdir
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    store_mod, workspace_mod = _couture_ledger_store()
    atelier = workspace_mod.Workspace(path_obj.parent)
    store_mod.refuser_les_liens(atelier, path_obj.name)
    if atelier.identite(path_obj.name) is None:
        raise ValueError(
            f"{path_obj} n'existe pas : create_tables(db_path) d'abord — "
            f"get_db_connection ne crée plus le store (T-00000770). Rien n'a été créé."
        )
    conn, _ident, _cree = store_mod.ouvrir_sans_suivre(
        atelier, path_obj.name, creer=False, connecter=_connexion_nue)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_tables(db_path: Union[str, Path, None] = None, *, racine: Optional[Path] = None) -> None:
    """Creates all required V3 database tables if they do not exist.

    Idempotent and version-aware (T-00000628). The version is read FIRST on a
    NUDE connection — one that sets no write PRAGMA — so a store from the future
    (user_version > SCHEMA_VERSION) is refused with `SchemaVersionError` while
    LEFT INTACT: its journal_mode, tables and side files are never touched,
    because `get_db_connection` (which switches the store to WAL) is only reached
    once the version check has passed.

    A store already in service is brought up to `SCHEMA_VERSION` WITHOUT
    destruction: the additive `ALTER TABLE` steps add any missing events_ledger
    columns by INSPECTION, then `PRAGMA user_version` is stamped — but ONLY when
    the store is not already at this version, and under `BEGIN IMMEDIATE` with a
    re-read so a writer that raced the version ahead wins (never a downgrade).
    Replaying this call on an up-to-date store takes no write lock and changes no
    byte.

    T-00000770 — this is the ONE creator of the V3 store, and it creates without
    following: after the parent directory, `cadre.ledger.store.refuser_les_liens`
    judges the leaf and its side files (a link, pending or not, a second hard
    name, a non-regular file: `ValueError`, nothing followed nor removed), then
    the probe opens through `ouvrir_sans_suivre(creer=True, mode=0o600)` — a new
    store is born EMPTY by an exclusive create (`O_CREAT|O_EXCL|O_NOFOLLOW`), in
    0o600, and is opened `mode=rw` on the same nude connection as before (no
    write PRAGMA). The primitive is reached through `run_export`'s seam; if it
    cannot be loaded, `PanneInfrastructure` names `cadre.ledger.store`.
    `":memory:"` is refused (this function opens its own connection and returns
    none: an in-memory store would be created and lost).

    T-00000753 — `racine` (keyword, default the cwd's project root) is the root
    whose state partition the default path would give birth to: BEFORE the
    parent directory is created, `naissance_partition.garder_store` refuses that
    birth for a disposable root without `CADRE_STATE_DIR` (`EmplacementRefuse`,
    nothing created); an existing partition is adopted as before.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH()
    path_obj = Path(db_path)
    naissance_partition.garder_store(path_obj, racine)  # T-00000753 : AVANT le mkdir
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    # T-00000770: judge the location BEFORE any open — a link at the store's
    # place (or at one of its side files) is refused, never followed.
    store_mod, workspace_mod = _couture_ledger_store()
    atelier = workspace_mod.Workspace(path_obj.parent)
    store_mod.refuser_les_liens(atelier, path_obj.name)
    # Refuse a store from the future BEFORE touching it (invariant « aucune
    # suppression sans trace »: nothing is destroyed). Read on a NUDE connection
    # that sets NO write PRAGMA — no WAL switch, no -wal/-shm side files — so the
    # refused store is left byte-for-byte intact. A fresh store reads 0. The
    # probe is opened WITHOUT FOLLOWING nor letting SQLite create the file: a new
    # store is born empty by exclusive creation, in 0o600 (T-00000770).
    probe, _ident, _cree = store_mod.ouvrir_sans_suivre(
        atelier, path_obj.name, creer=True, mode=_MODE_STORE, connecter=_connexion_nue)
    try:
        current_version = int(probe.execute("PRAGMA user_version").fetchone()[0])
    finally:
        probe.close()
    if current_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{path_obj} carries user_version={current_version} but this "
            f"binary implements v{SCHEMA_VERSION}: a NEWER kit wrote it. Refusing "
            f"to touch it — roll this binary forward."
        )

    conn = get_db_connection(db_path)
    # Own the transaction boundary explicitly: the idempotent DDL below runs in
    # autocommit, and the version stamp lives in its own BEGIN IMMEDIATE so an
    # up-to-date store can be replayed without ever taking a write lock.
    conn.isolation_level = None
    cursor = conn.cursor()

    # 1. Versioned Markdown Specification Registry — key (file_path, req_id,
    # version), T-00001223. An existing table keeps its shape here (IF NOT EXISTS):
    # a store at the OLD key is migrated by its producer, at the first sync-spec.
    cursor.execute(SPEC_REQUIREMENTS_DDL)

    # 2. Immutable Event Ledger
    # The CREATE TABLE now declares ALL ELEVEN columns so a single site tells the
    # true shape (T-00000629, extended by T-00000650). The last five (operation_id,
    # event_kind, attempt, ulid, predecesseur_ulid) are DELIBERATELY REDUNDANT with
    # the conditional `ALTER TABLE ... ADD COLUMN` steps below: the ALTERs stay to
    # upgrade legacy databases in place, and the indexes uq_events_operation_attempt
    # / uq_events_ulid REFERENCE these columns — a CREATE copied without them plants
    # at index creation. `ulid`/`predecesseur_ulid` are the fusion key of « run par
    # auteur » (Ordre de fusion causal) — `ulid` NULL is admitted (historical rows
    # carry none before the sister task's backfill; SQLite tolerates many NULLs
    # under a partial UNIQUE index).
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events_ledger (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        agent_role TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        operation_id TEXT,
        event_kind TEXT,
        attempt INTEGER NOT NULL DEFAULT 0,
        ulid TEXT,
        predecesseur_ulid TEXT
    );
    """)
    
    # 3. Projected Task Tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_projections (
        task_id TEXT PRIMARY KEY,
        req_id TEXT NOT NULL,
        spec_version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL,
        current_assignee TEXT,
        code_diff TEXT,
        retry_count INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 4. Tagged Lessons Learned (Triple Tag: language, domain_tag, error_pattern)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lessons_learned (
        lesson_id INTEGER PRIMARY KEY AUTOINCREMENT,
        language TEXT NOT NULL,
        domain_tag TEXT NOT NULL,
        error_pattern TEXT NOT NULL,
        lesson_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 5. Session Checkpoints (Token & Multi-Session Resilience)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS session_checkpoints (
        session_id TEXT PRIMARY KEY,
        current_phase INTEGER NOT NULL,
        phase_name TEXT NOT NULL,
        checkpoint_data_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Additive columns preserve legacy databases while giving every retry a
    # durable identity in the immutable ledger. On a store born from the
    # CREATE TABLE above these three ALTERs are NO-OPS (columns already present):
    # the redundancy is intentional and named (T-00000629) — the CREATE carries
    # the true shape for readers, the ALTERs carry the migration for the field.
    ledger_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(events_ledger)").fetchall()
    }
    if "operation_id" not in ledger_columns:
        cursor.execute("ALTER TABLE events_ledger ADD COLUMN operation_id TEXT")
    if "event_kind" not in ledger_columns:
        cursor.execute("ALTER TABLE events_ledger ADD COLUMN event_kind TEXT")
    if "attempt" not in ledger_columns:
        cursor.execute("ALTER TABLE events_ledger ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0")
    # T-00000650 : `ulid`/`predecesseur_ulid` par ALTER pour une base en service
    # (redondance NOMMÉE avec le CREATE ci-dessus). L'unicité de `ulid` est un
    # index PARTIEL — jamais une contrainte `UNIQUE` sur la colonne, que
    # `ADD COLUMN` refuse (« The column may not have a PRIMARY KEY or UNIQUE
    # constraint », doc SQLite ALTER TABLE).
    if "ulid" not in ledger_columns:
        cursor.execute("ALTER TABLE events_ledger ADD COLUMN ulid TEXT")
    if "predecesseur_ulid" not in ledger_columns:
        cursor.execute("ALTER TABLE events_ledger ADD COLUMN predecesseur_ulid TEXT")
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_events_operation_attempt
    ON events_ledger(operation_id, event_kind, attempt)
    WHERE operation_id IS NOT NULL;
    """)
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_events_ulid
    ON events_ledger(ulid)
    WHERE ulid IS NOT NULL;
    """)

    # Board -> V3 inbox: one reducer application for one logical operation.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS board_sync_inbox (
        operation_id TEXT PRIMARY KEY,
        event_kind TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        effect_json TEXT NOT NULL,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # V3 -> Board outbox: effect and acknowledgement are recoverable separately.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS board_sync_outbox (
        operation_id TEXT PRIMARY KEY,
        event_kind TEXT NOT NULL,
        attempt INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL,
        lease_owner TEXT,
        lease_token TEXT,
        lease_expires_at REAL,
        acked_at TIMESTAMP,
        cancelled_at TIMESTAMP,
        superseded_by TEXT,
        last_error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    outbox_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(board_sync_outbox)").fetchall()
    }
    if "lease_owner" not in outbox_columns:
        cursor.execute("ALTER TABLE board_sync_outbox ADD COLUMN lease_owner TEXT")
    if "lease_token" not in outbox_columns:
        cursor.execute("ALTER TABLE board_sync_outbox ADD COLUMN lease_token TEXT")
    if "lease_expires_at" not in outbox_columns:
        cursor.execute("ALTER TABLE board_sync_outbox ADD COLUMN lease_expires_at REAL")
    if "cancelled_at" not in outbox_columns:
        cursor.execute("ALTER TABLE board_sync_outbox ADD COLUMN cancelled_at TIMESTAMP")
    if "superseded_by" not in outbox_columns:
        cursor.execute("ALTER TABLE board_sync_outbox ADD COLUMN superseded_by TEXT")

    # A board id can be renamed but never re-identified. Tombstones remain so a
    # later V3 replay cannot resurrect a deleted task.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_board_mapping (
        board_task_id TEXT PRIMARY KEY,
        v3_task_id TEXT NOT NULL UNIQUE,
        create_operation_id TEXT NOT NULL UNIQUE,
        tombstoned INTEGER NOT NULL DEFAULT 0 CHECK (tombstoned IN (0, 1)),
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Reserve the V3 identity before touching the file-backed board. A retry
    # with a different operation id adopts the original creator reservation.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS board_identity_reservations (
        v3_task_id TEXT PRIMARY KEY,
        creator_operation_id TEXT NOT NULL UNIQUE,
        board_task_id TEXT UNIQUE,
        reserved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finalized_at TIMESTAMP
    );
    """)

    # Stamp the version LAST, once the shape matches this binary — but ONLY when
    # the store is not already at it. On an up-to-date store this whole block is
    # skipped, so create_tables takes NO write lock and changes NO byte (measured:
    # the idempotent DDL above needs none either). When a stamp IS due, take the
    # write lock and RE-READ under it: a concurrent writer may have moved the
    # version between the nude probe and here. A store that raced AHEAD of this
    # binary is refused — the stamp is rolled back, never a downgrade.
    if current_version != SCHEMA_VERSION:
        conn.execute("BEGIN IMMEDIATE")
        live_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if live_version > SCHEMA_VERSION:
            conn.rollback()
            conn.close()
            raise SchemaVersionError(
                f"{path_obj} raced to user_version={live_version} while this "
                f"binary (v{SCHEMA_VERSION}) was migrating it: a NEWER kit won. "
                f"Rolling back the stamp — roll this binary forward."
            )
        if live_version != SCHEMA_VERSION:
            # PRAGMA takes no bound parameter; the value is a module int coerced
            # with int(), never external input.
            # nosemgrep: agents.security.python-sql-injection-string-format
            conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.commit()

    conn.close()
