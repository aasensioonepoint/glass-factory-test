"""LES SCHÉMAS DES TROIS STORES SQLITE DE L'ADOPTANT, PORTÉS PAR LA WHEEL.

T-00000646 (décision pilote S-00001591, clause « création hybride des stores »
amendée par S-00002138). Ce module ne fait AUCUNE E/S et ne résout AUCUN chemin :
il REÇOIT des `sqlite3.Connection` déjà ouvertes par `cadre.ledger.stores` (via
`cadre.ledger.store.connect`, l'unique ouverture du service) et y pose la forme
des trois stores :

  * `v3_event_store.db` — forme de `agentic_v3.db.schema.create_tables`
    (`PRAGMA user_version`, journal WAL) ;
  * `events.db`         — forme de `event_store._create_schema`
    (`PRAGMA user_version`, journal WAL) ;
  * `index.db`          — forme de `migrate_index_to_db.ensure_schema`, de son
    échelle de montée et des trois clés `meta` d'un état VIDE
    (`meta.schema_version`, journal `delete`).

SECONDE DÉFINITION DES SCHÉMAS, ASSUMÉE (S-00001592) jusqu'à l'inversion portée
par T-00000660. La wheel (`packages = ["src/cadre"]`) n'embarque pas
`agentic_v3/` ; de `.agents/bin/` elle ne porte que les 23 sources du moteur
du board, en données sous `cadre/_moteur/` (T-00000962), et aucun producteur
de ces schémas : le DDL ci-dessous est donc RECOPIÉ des
producteurs, à l'identique au blanc près, parce que SQLite garde le texte de
chaque `CREATE` dans `sqlite_master`. Le banc `test_cadre_ledger_stores.py`
(`PariteDesSchemasTests`) compare à chaque porte ce texte, les colonnes, les
versions, les journaux et les échelles des deux côtés : une dérive d'UN SEUL
côté rougit.

DEUX UNITÉS PAR STORE. `sonder_<x>(conn)` LIT seulement et lève `StoreRefuse`
dans trois cas — un store du FUTUR (version déclarée au-delà de celle de la
wheel, ou échelon de montée manquant), un `events.db` en version 0 NON vide, un
`index.db` qui porte des tables sans `meta.schema_version` lisible.
`garantir_<x>(conn)` crée ou met à niveau, idempotente. Elle ne prend le verrou
d'écriture (`BEGIN IMMEDIATE`) QUE si la version sondée diffère de celle de la
wheel, et RE-SONDE sous ce verrou AVANT tout DDL : un écrivain concurrent qui
aurait avancé la version entre la sonde et l'écriture fait REFUSER, jamais
rétrograder, et la naissance comme la montée (DDL et tampon) tiennent en UNE
transaction — deux créateurs d'un même store ne s'entrecroisent pas. Un store
À JOUR est rejoué SANS verrou — DDL `IF NOT EXISTS` seul, no-op mesuré sous un
écrivain tenant —, patron de `create_tables` : sans quoi un rejeu attendait
l'écrivain puis échouait (T-00000646, F1). L'attente d'un verrou tenu est celle
du producteur V3, 30 s (`_ATTENTE_ECRIVAIN_MS`). Rien n'est jamais supprimé
(« aucune suppression sans trace »).

CE QUI N'EST PAS RECOPIÉ, NOMMÉ PLUTÔT QUE TU. (a) Le repli d'ouverture
`_migrate_legacy_spool` et le relabel/backfill d'`open_store(create=True)` :
le repli `merge_day_files` devient INATTEIGNABLE pour un `events.db` né ici
(`open_store` ne le joue que sur base ABSENTE, `--merge-days` est no-op dès
qu'elle existe) : les fichiers par écrivain des jours passés sont ingérés sous
leur propre identité, jamais consolidés. Comptage préservé (`SpoolTests`). (b)
`run_apply`/`append_log` de l'index : sur un état vide, ils n'écrivent que les
trois clés `meta` posées ici et aucune ligne de journal. (c) Sur un `index.db`
PRÉSENT, `symbols_fts` n'est JAMAIS créé : `--resync` ne le remplit que s'il
l'a créé lui-même, donc un index plein-texte VIDE posé ici sur un index peuplé
répondrait « aucun résultat » à jamais. Sa création reste au producteur. (d) Le
prédicat de l'index : la wheel REFUSE un store sans `symbols` qui porte une
autre table, là où le producteur le traite comme neuf.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable

__all__ = [
    "ECHELONS_EVENTS",
    "ECHELONS_INDEX",
    "EVENTS_USER_VERSION",
    "INDEX_SCHEMA_VERSION",
    "StoreRefuse",
    "V3_USER_VERSION",
    "garantir_events",
    "garantir_index",
    "garantir_v3",
    "patienter",
    "sonder_events",
    "sonder_index",
    "sonder_v3",
]

#: `PRAGMA user_version` de `v3_event_store.db` — `agentic_v3.db.schema.SCHEMA_VERSION`.
V3_USER_VERSION = 2
#: `PRAGMA user_version` de `events.db` — `event_store.SCHEMA_VERSION`.
EVENTS_USER_VERSION = 1
#: `meta.schema_version` de `index.db` — `migrate_index_to_db.SCHEMA_VERSION`.
INDEX_SCHEMA_VERSION = 3


#: Attente d'un verrou tenu par un autre écrivain, en millisecondes — celle du
#: producteur V3 (`sqlite3.connect(…, timeout=30.0)`, `agentic_v3/db/schema.py`).
#: Le défaut de `sqlite3.connect` (5 s) faisait lever `garantir_v3` sous un
#: écrivain tenant là où le producteur attendait (T-00000646, F1).
_ATTENTE_ECRIVAIN_MS = 30000

#: Pas de la retente de `PRAGMA journal_mode=WAL` (`_passer_en_wal`), en
#: secondes. L'attente TOTALE reste bornée par `_ATTENTE_ECRIVAIN_MS`, plus au
#: plus un pas : chaque tentative n'attend que le RESTE de la borne (critic-opus
#: T5, T-00000668 — elle attendait la borne entière, soit jusqu'à 2×).
_PAS_RETENTE_WAL_S = 0.05


class StoreRefuse(RuntimeError):
    """Un store existant que la wheel REFUSE de toucher. Levée AVANT toute
    écriture dans ce store — à la sonde, ou à la re-sonde sous `BEGIN
    IMMEDIATE`, dont la transaction est alors annulée —, hors deux bornes :
    (1) la sonde de `cadre.ledger.stores` rabat un WAL orphelin (contenu
    intact, octets changés) ; (2) `garantir_v3` passe en WAL avant sa
    re-sonde, donc un refus à la re-sonde laisse le journal en WAL si le store
    n'y était pas (en-tête seul, aucune table ni ligne). Le message nomme la
    cause et le remède."""


Echelon = Callable[[sqlite3.Connection], None]


# --------------------------------------------------------------- aides communes
def _tampon_user_version(version: int) -> str:
    """Le texte `PRAGMA user_version = <n>`. Un PRAGMA n'accepte AUCUN paramètre
    lié ; la valeur est une constante entière de ce module, forcée par `int()`,
    jamais une entrée externe."""
    return "PRAGMA user_version = " + str(int(version))


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _est_vide(conn: sqlite3.Connection) -> bool:
    """Aucune table hors internes `sqlite_%` — un fichier de 0 octet l'est."""
    ligne = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%'"
    ).fetchone()
    return int(ligne[0]) == 0


def _version_et_vide(conn: sqlite3.Connection) -> tuple[int, bool]:
    """`user_version` ET vacuité (`_est_vide`) lues en UNE instruction, donc sur
    UN SEUL instantané. Deux lectures laissaient un créateur concurrent valider
    entre elles : version 0 lue avant, tables vues après, faux refus « non
    versionné » (T-00000646, critic-opus T2 : 8 sur 1 200 appels)."""
    ligne = conn.execute(
        "SELECT (SELECT user_version FROM pragma_user_version), "
        "(SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%')"
    ).fetchone()
    return int(ligne[0]), int(ligne[1]) == 0


def _table_existe(conn: sqlite3.Connection, nom: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ?", (nom,)
    ).fetchone() is not None


def _colonnes(conn: sqlite3.Connection, pragma_table_info: str) -> set[str]:
    return {ligne[1] for ligne in conn.execute(pragma_table_info)}


def _echelon_manquant(version: int, cible: int, echelons: dict[int, Echelon]) -> int | None:
    """La première version de `version` à `cible` sans échelon, ou `None`."""
    for depuis in range(version, cible):
        if depuis not in echelons:
            return depuis
    return None


def _autocommit_patient(conn: sqlite3.Connection) -> None:
    """Transactions tenues à la main (`isolation_level=None`, donc autocommit
    hors `_sous_verrou`) et attente d'un écrivain tenant portée à
    `_ATTENTE_ECRIVAIN_MS`. PRAGMA de CONNEXION : n'écrit rien dans le store."""
    conn.isolation_level = None
    conn.execute("PRAGMA busy_timeout = " + str(int(_ATTENTE_ECRIVAIN_MS)))


def patienter(conn: sqlite3.Connection) -> None:
    """Pose sur `conn` le mode et l'attente de `garantir_*` : pour une connexion
    de SONDE ouverte hors de ce module (`cadre.ledger.stores`), qui attendait
    sinon le défaut de `sqlite3.connect` (5 s) là où la création attend
    `_ATTENTE_ECRIVAIN_MS` (T-00000646, critic-opus T3). PRAGMA de connexion :
    n'écrit rien dans le store."""
    _autocommit_patient(conn)


def _passer_en_wal(conn: sqlite3.Connection) -> None:
    """`PRAGMA journal_mode=WAL`, RETENTÉ sur « locked » seulement, au pas de
    `_PAS_RETENTE_WAL_S`, tant que `_ATTENTE_ECRIVAIN_MS` n'est pas écoulée ;
    toute autre erreur, ou « locked » au-delà de l'attente, est RELEVÉE.

    POURQUOI une boucle à la main (T-00000668, critic-fable, décision
    S-00002394) : sur un store encore en journal CLASSIQUE, un tiers qui tient
    `BEGIN IMMEDIATE` (verrou RESERVED) fait lever ce PRAGMA IMMÉDIATEMENT —
    SQLite n'appelle pas le gestionnaire d'attente pour cette escalade, donc
    `busy_timeout` n'y peut rien (mesuré, sqlite 3.53.4 : 0,0 s sous un
    `busy_timeout` de 1,5 s). C'est la course de deux créateurs d'un store
    neuf : sans retente, le perdant levait `OperationalError` (1 sur 20 à 1
    sur 80 sous charge).

    CHAQUE TENTATIVE N'ATTEND QUE LE RESTE DE LA BORNE (critic-opus T5,
    T-00000668). Un lecteur SHARED, lui, fait passer le PRAGMA par le
    gestionnaire d'attente : la tentative qui suivait le relâchement du tenant
    RESERVED attendait alors `busy_timeout` ENTIER, au-delà de l'échéance —
    mesuré 1 207 à 1 237 ms pour une borne de 600 ms. `busy_timeout` est donc
    posé au reste (jamais négatif) avant chaque PRAGMA, et rétabli à
    `_ATTENTE_ECRIVAIN_MS` en sortie, levée comprise."""
    echeance = time.monotonic() + _ATTENTE_ECRIVAIN_MS / 1000.0
    try:
        while True:
            reste_ms = max(0, int((echeance - time.monotonic()) * 1000))
            conn.execute("PRAGMA busy_timeout = " + str(reste_ms))
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) or time.monotonic() >= echeance:
                    raise
            time.sleep(_PAS_RETENTE_WAL_S)
    finally:
        conn.execute("PRAGMA busy_timeout = " + str(int(_ATTENTE_ECRIVAIN_MS)))


def _sous_verrou(conn: sqlite3.Connection, corps: Echelon) -> None:
    """`corps(conn)` sous `BEGIN IMMEDIATE … COMMIT`, `ROLLBACK` sur toute levée —
    patron de `event_store._create_schema` et de `upgrade_schema`. L'attente du
    verrou est `_ATTENTE_ECRIVAIN_MS`, posée AVANT le `BEGIN IMMEDIATE`."""
    _autocommit_patient(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        corps(conn)
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    conn.execute("COMMIT")


# ======================================================== v3_event_store.db
# T-00001223 (S-00004503) : clé (file_path, req_id, version), texte identique
# octet pour octet à `SPEC_REQUIREMENTS_DDL` d'`agentic_v3/db/schema.py`. Ne fait
# naître que des stores neufs ; un store peuplé à l'ancienne clé est migré par le
# producteur, au premier sync-spec.
_V3_SPEC_REQUIREMENTS = """
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

_V3_EVENTS_LEDGER = """
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
    """

_V3_TASK_PROJECTIONS = """
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
    """

_V3_LESSONS_LEARNED = """
    CREATE TABLE IF NOT EXISTS lessons_learned (
        lesson_id INTEGER PRIMARY KEY AUTOINCREMENT,
        language TEXT NOT NULL,
        domain_tag TEXT NOT NULL,
        error_pattern TEXT NOT NULL,
        lesson_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

_V3_SESSION_CHECKPOINTS = """
    CREATE TABLE IF NOT EXISTS session_checkpoints (
        session_id TEXT PRIMARY KEY,
        current_phase INTEGER NOT NULL,
        phase_name TEXT NOT NULL,
        checkpoint_data_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

#: Colonnes ajoutées PAR INSPECTION à un `events_ledger` en service — no-op sur
#: un store né du `CREATE` ci-dessus, qui les porte déjà (redondance NOMMÉE du
#: producteur, T-00000629/T-00000650).
_V3_COLONNES_LEDGER = (
    ("operation_id", "ALTER TABLE events_ledger ADD COLUMN operation_id TEXT"),
    ("event_kind", "ALTER TABLE events_ledger ADD COLUMN event_kind TEXT"),
    ("attempt", "ALTER TABLE events_ledger ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0"),
    ("ulid", "ALTER TABLE events_ledger ADD COLUMN ulid TEXT"),
    ("predecesseur_ulid", "ALTER TABLE events_ledger ADD COLUMN predecesseur_ulid TEXT"),
)

_V3_UQ_OPERATION_ATTEMPT = """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_events_operation_attempt
    ON events_ledger(operation_id, event_kind, attempt)
    WHERE operation_id IS NOT NULL;
    """

_V3_UQ_ULID = """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_events_ulid
    ON events_ledger(ulid)
    WHERE ulid IS NOT NULL;
    """

_V3_BOARD_SYNC_INBOX = """
    CREATE TABLE IF NOT EXISTS board_sync_inbox (
        operation_id TEXT PRIMARY KEY,
        event_kind TEXT NOT NULL,
        attempt INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        effect_json TEXT NOT NULL,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

_V3_BOARD_SYNC_OUTBOX = """
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
    """

_V3_COLONNES_OUTBOX = (
    ("lease_owner", "ALTER TABLE board_sync_outbox ADD COLUMN lease_owner TEXT"),
    ("lease_token", "ALTER TABLE board_sync_outbox ADD COLUMN lease_token TEXT"),
    ("lease_expires_at", "ALTER TABLE board_sync_outbox ADD COLUMN lease_expires_at REAL"),
    ("cancelled_at", "ALTER TABLE board_sync_outbox ADD COLUMN cancelled_at TIMESTAMP"),
    ("superseded_by", "ALTER TABLE board_sync_outbox ADD COLUMN superseded_by TEXT"),
)

_V3_TASK_BOARD_MAPPING = """
    CREATE TABLE IF NOT EXISTS task_board_mapping (
        board_task_id TEXT PRIMARY KEY,
        v3_task_id TEXT NOT NULL UNIQUE,
        create_operation_id TEXT NOT NULL UNIQUE,
        tombstoned INTEGER NOT NULL DEFAULT 0 CHECK (tombstoned IN (0, 1)),
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

_V3_BOARD_IDENTITY_RESERVATIONS = """
    CREATE TABLE IF NOT EXISTS board_identity_reservations (
        v3_task_id TEXT PRIMARY KEY,
        creator_operation_id TEXT NOT NULL UNIQUE,
        board_task_id TEXT UNIQUE,
        reserved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finalized_at TIMESTAMP
    );
    """


def sonder_v3(conn: sqlite3.Connection) -> int:
    """La version du store V3, en LECTURE seule. `StoreRefuse` s'il vient du
    FUTUR. Une version 0 non vide n'est PAS un refus ici : le producteur la met
    à niveau par inspection (colonnes ajoutées), sans rien détruire."""
    version = _user_version(conn)
    if version > V3_USER_VERSION:
        raise StoreRefuse(
            f"v3_event_store.db porte user_version={version} mais la wheel "
            f"implémente v{V3_USER_VERSION} : un kit PLUS RÉCENT l'a écrit. Rien "
            f"n'est touché — mettez la wheel à jour plutôt que de rétrograder le store."
        )
    return version


def _ddl_v3(conn: sqlite3.Connection) -> None:
    """Le DDL du store V3 — ni sonde ni tampon, patron de `create_tables`.
    IDEMPOTENT par construction : `IF NOT EXISTS` partout, et chaque `ALTER`
    gardé par inspection des colonnes. Deux appelants : `garantir_v3` sur un
    store À JOUR, en autocommit (aucun verrou d'écriture pris, mesuré : 0 s
    sous un écrivain tenant) ; `_corps_v3` sous le verrou, pour la naissance
    et la montée."""
    for ddl in (_V3_SPEC_REQUIREMENTS, _V3_EVENTS_LEDGER, _V3_TASK_PROJECTIONS,
                _V3_LESSONS_LEARNED, _V3_SESSION_CHECKPOINTS):
        conn.execute(ddl)
    presentes = _colonnes(conn, "PRAGMA table_info(events_ledger)")
    for colonne, alter in _V3_COLONNES_LEDGER:
        if colonne not in presentes:
            conn.execute(alter)
    conn.execute(_V3_UQ_OPERATION_ATTEMPT)
    conn.execute(_V3_UQ_ULID)
    conn.execute(_V3_BOARD_SYNC_INBOX)
    conn.execute(_V3_BOARD_SYNC_OUTBOX)
    presentes = _colonnes(conn, "PRAGMA table_info(board_sync_outbox)")
    for colonne, alter in _V3_COLONNES_OUTBOX:
        if colonne not in presentes:
            conn.execute(alter)
    conn.execute(_V3_TASK_BOARD_MAPPING)
    conn.execute(_V3_BOARD_IDENTITY_RESERVATIONS)


def _corps_v3(conn: sqlite3.Connection) -> None:
    """Naissance ou montée du store V3, SOUS le verrou de `_sous_verrou`. RE-SONDE
    d'abord : un écrivain plus récent qui a gagné la course fait refuser AVANT
    tout DDL (transaction annulée), un créateur concurrent qui a déjà tamponné
    laisse le corps vide. Sinon le DDL et le tampon, dans la MÊME transaction."""
    if sonder_v3(conn) != V3_USER_VERSION:
        _ddl_v3(conn)
        conn.execute(_tampon_user_version(V3_USER_VERSION))


def garantir_v3(conn: sqlite3.Connection) -> None:
    """Crée ou met à niveau `v3_event_store.db`, idempotente — calquée sur
    `create_tables` pour un store À JOUR. DIVERGENCE NOMMÉE : naissance et
    montée prennent le patron de `_sous_verrou` (`event_store._create_schema`),
    là où `create_tables` les laisse en autocommit ; la FORME produite reste
    celle du producteur (`PariteDesSchemasTests`).

    La sonde passe AVANT le passage en WAL : un store du futur est refusé sans
    qu'aucun PRAGMA d'écriture ne l'ait touché (un refus à la RE-sonde suit ce
    passage : borne (2) de `StoreRefuse`). Puis `journal_mode=WAL` HORS
    transaction, RETENTÉ sur « locked » dans la borne de `_ATTENTE_ECRIVAIN_MS`
    (`_passer_en_wal` : un tenant RESERVED le fait lever sans attente). Store À
    JOUR : le DDL idempotent en autocommit, SANS verrou —
    un rejeu ne change aucun octet et passe sous un écrivain tenant. Sinon
    `_corps_v3` sous `BEGIN IMMEDIATE` : re-sonde, puis DDL et tampon en UNE
    transaction. Deux créateurs d'un v0 ne s'entrecroisent plus sur les `ALTER`
    (colonne dupliquée), un kit plus récent qui a gagné la course fait refuser
    sans qu'aucune table soit recréée, et un arrêt en cours est annulé en bloc.
    """
    _autocommit_patient(conn)
    version = sonder_v3(conn)
    _passer_en_wal(conn)
    if version == V3_USER_VERSION:
        _ddl_v3(conn)
        return
    _sous_verrou(conn, _corps_v3)


# ================================================================= events.db
_EVENTS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY,
        project     TEXT NOT NULL,
        "user"      TEXT,
        channel     TEXT NOT NULL,
        src_file    TEXT NOT NULL,
        line_index  INTEGER NOT NULL,
        line_hash   TEXT NOT NULL,
        day         TEXT NOT NULL,
        ts          TEXT,
        kind        TEXT,
        host        TEXT,
        sid         TEXT,
        -- `prompt_id`, NOT os.getpid(): the canal-B join key that the JSONL
        -- envelope calls `pid`. Renamed in the schema precisely because that
        -- short name is conflated with the process id twice in events.py's own
        -- comments; a column name is a good place to stop the confusion.
        prompt_id   TEXT,
        aid         TEXT,
        task        TEXT,
        agent       TEXT,
        effort      TEXT,
        body        TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    )
    """,
    'CREATE UNIQUE INDEX IF NOT EXISTS events_identity '
    'ON events (project, src_file, line_index, line_hash)',
    "CREATE INDEX IF NOT EXISTS events_day ON events (day)",
    "CREATE INDEX IF NOT EXISTS events_channel_id ON events (channel, id)",
    "CREATE INDEX IF NOT EXISTS events_ts ON events (ts)",
    "CREATE INDEX IF NOT EXISTS events_task ON events (task)",
    "CREATE INDEX IF NOT EXISTS events_kind ON events (kind)",
    "CREATE INDEX IF NOT EXISTS events_agent ON events (agent)",
    """
    CREATE TABLE IF NOT EXISTS digests (
        month     TEXT NOT NULL,
        dimension TEXT NOT NULL,
        key       TEXT NOT NULL DEFAULT '',
        count     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (month, dimension, key)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS digest_days (
        month TEXT NOT NULL,
        day   TEXT NOT NULL,
        PRIMARY KEY (month, day)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    ) WITHOUT ROWID
    """,
)

#: Échelle de montée d'`events.db`, clé = version DE DÉPART. VIDE, comme
#: `event_store._MIGRATIONS` : v1 est le plancher, donc aucun store en service
#: ne porte une version entre 0 (neuf) et `EVENTS_USER_VERSION`.
ECHELONS_EVENTS: dict[int, Echelon] = {}


def sonder_events(conn: sqlite3.Connection) -> int:
    """La version d'`events.db`, en LECTURE seule. `StoreRefuse` s'il vient du
    FUTUR, s'il déclare 0 sans être vide (store non versionné : rien ne peut
    être migré sans risque), ou s'il manque un échelon pour le monter. Version
    et vacuité sont lues sur UN instantané (`_version_et_vide`)."""
    version, vide = _version_et_vide(conn)
    if version > EVENTS_USER_VERSION:
        raise StoreRefuse(
            f"events.db porte user_version={version} mais la wheel implémente "
            f"v{EVENTS_USER_VERSION} : un kit PLUS RÉCENT l'a écrit. Rien n'est "
            f"touché — mettez la wheel à jour, ou exportez son contenu en spool "
            f"(`--export-spool`) avec le kit plus récent."
        )
    if version == 0:
        if not vide:
            raise StoreRefuse(
                "events.db déclare user_version=0 mais n'est pas vide : un store "
                "non versionné ne se migre pas sans risque. Rien n'est touché — "
                "déplacez-le ; le démon reconstruit depuis le spool restant."
            )
        return version
    manque = _echelon_manquant(version, EVENTS_USER_VERSION, ECHELONS_EVENTS)
    if manque is not None:
        raise StoreRefuse(
            f"events.db porte user_version={version} et aucun échelon ne monte "
            f"v{manque} vers v{EVENTS_USER_VERSION}. Rien n'est touché — "
            f"déplacez-le ; le démon reconstruit depuis le spool restant."
        )
    return version


def _corps_events(conn: sqlite3.Connection) -> None:
    version = sonder_events(conn)  # RE-SONDE sous le verrou d'écriture
    if version == 0:
        for ddl in _EVENTS_SCHEMA:
            conn.execute(ddl)
        conn.execute(_tampon_user_version(EVENTS_USER_VERSION))
        return
    for depuis in range(version, EVENTS_USER_VERSION):
        ECHELONS_EVENTS[depuis](conn)
    if version != EVENTS_USER_VERSION:
        conn.execute(_tampon_user_version(EVENTS_USER_VERSION))


def garantir_events(conn: sqlite3.Connection) -> None:
    """Crée ou met à niveau `events.db`, idempotente.

    Schéma et tampon de version sous `BEGIN IMMEDIATE` (patron de
    `_create_schema`) SEULEMENT si la version sondée diffère — un store à jour
    ne prend aucun verrou —, puis `journal_mode=WAL` HORS transaction, comme
    `open_store`. Le spool n'est NI lu NI touché : son ingestion reste au démon.
    """
    _autocommit_patient(conn)
    if sonder_events(conn) != EVENTS_USER_VERSION:
        _sous_verrou(conn, _corps_events)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        # Même choix que le producteur : un système de fichiers qui refuse le
        # WAL donne encore un store correct, plus lent.
        pass


# ================================================================== index.db
_INDEX_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta("
    " key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS symbols("
    " id INTEGER PRIMARY KEY, path TEXT, name TEXT, kind TEXT,"
    " start INTEGER, \"end\" INTEGER,"
    " deleted INTEGER NOT NULL DEFAULT 0, generation TEXT,"
    " ordinal INTEGER NOT NULL DEFAULT 0, body_sha TEXT)",
    "CREATE UNIQUE INDEX IF NOT EXISTS symbols_live_identity"
    " ON symbols(path, name, kind, ordinal) WHERE deleted = 0",
    "CREATE TABLE IF NOT EXISTS edges("
    " src_id INTEGER, dst_id INTEGER, PRIMARY KEY(src_id, dst_id))",
    "CREATE TABLE IF NOT EXISTS modules("
    " path TEXT PRIMARY KEY, role TEXT, depends_on TEXT, owner TEXT)",
    "CREATE TABLE IF NOT EXISTS annotations("
    " scope TEXT NOT NULL CHECK(scope IN ('symbol','module')), key TEXT NOT NULL,"
    " purpose TEXT, role TEXT, owner TEXT, PRIMARY KEY(scope, key))",
    "CREATE TABLE IF NOT EXISTS journal("
    " seq INTEGER PRIMARY KEY, at_sha TEXT, kind TEXT, payload TEXT)",
)
_INDEX_FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts"
              " USING fts5(name, path, purpose)")

#: Les trois clés `meta` qu'écrit `write_state` sur un état VIDE, dans SON ordre.
#: Posées UNIQUEMENT à la naissance : sur un store présent, `watermark` et
#: `built_at_sha` sont du contenu d'équipe, jamais réécrits.
_INDEX_META_NEUF = (
    ("schema_version", str(INDEX_SCHEMA_VERSION)),
    ("built_at_sha", ""),
    ("watermark", "0"),
)


def _index_v1_vers_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2 : la clé d'identité vivante gagne `ordinal` ; l'index v1 à trois
    colonnes, qui refusait les homonymes, est retiré (T-00000121)."""
    if "ordinal" not in _colonnes(conn, "PRAGMA table_info(symbols)"):
        conn.execute("ALTER TABLE symbols ADD COLUMN ordinal INTEGER NOT NULL DEFAULT 0")
    conn.execute("DROP INDEX IF EXISTS symbols_live_key")


def _index_v2_vers_v3(conn: sqlite3.Connection) -> None:
    """v2 -> v3 : `symbols` gagne `body_sha`, NULL sur les lignes existantes
    (T-00000377) — le `--resync` suivant le remplit."""
    if "body_sha" not in _colonnes(conn, "PRAGMA table_info(symbols)"):
        conn.execute("ALTER TABLE symbols ADD COLUMN body_sha TEXT")


#: Échelle de montée d'`index.db`, clé = version DE DÉPART — celle de
#: `migrate_index_to_db.SCHEMA_UPGRADES`. Un échelon est du DDL seul ; la
#: transaction et le tampon de version appartiennent à l'appelant.
ECHELONS_INDEX: dict[int, Echelon] = {
    1: _index_v1_vers_v2,
    2: _index_v2_vers_v3,
}


def _version_index(conn: sqlite3.Connection) -> int | None:
    """`None` = store VIDE (neuf). Sinon la version déclarée par
    `meta.schema_version`, et 0 quand elle est absente ou illisible."""
    if _est_vide(conn):
        return None
    if not _table_existe(conn, "meta"):
        return 0
    ligne = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    brut = None if ligne is None else ligne[0]
    if brut is None or not str(brut).isdigit():
        return 0
    return int(brut)


def sonder_index(conn: sqlite3.Connection) -> int | None:
    """La version d'`index.db`, en LECTURE seule ; `None` pour un store VIDE.
    `StoreRefuse` s'il porte des tables sans `meta.schema_version` lisible
    (store ÉTRANGER), s'il vient du FUTUR, ou s'il manque un échelon."""
    version = _version_index(conn)
    if version is None:
        return None
    if version == 0:
        raise StoreRefuse(
            "un index.db existe et porte des tables, mais ne déclare aucune "
            "meta.schema_version lisible : c'est un store étranger. Rien n'est "
            "supprimé — déplacez-le puis relancez la création (« aucune "
            "suppression sans trace »)."
        )
    if version > INDEX_SCHEMA_VERSION:
        raise StoreRefuse(
            f"index.db déclare le schéma v{version} mais la wheel implémente "
            f"v{INDEX_SCHEMA_VERSION} : un kit PLUS RÉCENT l'a écrit. Rien n'est "
            f"touché — mettez la wheel à jour plutôt que de rétrograder le store."
        )
    manque = _echelon_manquant(version, INDEX_SCHEMA_VERSION, ECHELONS_INDEX)
    if manque is not None:
        raise StoreRefuse(
            f"index.db déclare le schéma v{version} et aucun échelon ne monte "
            f"v{manque} vers v{INDEX_SCHEMA_VERSION}. Rien n'est touché — "
            f"déplacez-le et recréez-le ; les annotations se rejouent depuis "
            f"annotations_log.jsonl."
        )
    return version


def _corps_index(conn: sqlite3.Connection) -> None:
    version = sonder_index(conn)  # RE-SONDE sous le verrou d'écriture
    if version is None:
        for ddl in _INDEX_SCHEMA:
            conn.execute(ddl)
        # FTS5 est optionnel (absent de certains interpréteurs) : son échec ne
        # doit annuler que lui, jamais le schéma posé juste avant.
        conn.execute("SAVEPOINT cadre_index_fts")
        try:
            conn.execute(_INDEX_FTS)
        except sqlite3.OperationalError:
            conn.execute("ROLLBACK TO cadre_index_fts")
        conn.execute("RELEASE cadre_index_fts")
        for cle, valeur in _INDEX_META_NEUF:
            conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (cle, valeur))
        return
    for depuis in range(version, INDEX_SCHEMA_VERSION):
        ECHELONS_INDEX[depuis](conn)
    if version != INDEX_SCHEMA_VERSION:
        conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     ("schema_version", str(INDEX_SCHEMA_VERSION)))
    for ddl in _INDEX_SCHEMA:
        conn.execute(ddl)


def garantir_index(conn: sqlite3.Connection) -> None:
    """Crée ou met à niveau `index.db`, idempotente, journal `delete` inchangé.

    VIDE : le schéma, `symbols_fts` si FTS5 est là, puis les trois clés `meta`
    d'un état vide — un index versionné et sans symbole, qu'un `--resync`
    remplira. PRÉSENT : l'échelle, puis le schéma en `IF NOT EXISTS` ; JAMAIS
    `watermark` ni `built_at_sha` réécrits, JAMAIS `symbols_fts` créé (voir la
    tête de module). Naissance et montée sous `BEGIN IMMEDIATE` ; un store À
    JOUR ne rejoue que le DDL idempotent, SANS verrou.
    """
    _autocommit_patient(conn)
    if sonder_index(conn) == INDEX_SCHEMA_VERSION:
        for ddl in _INDEX_SCHEMA:
            conn.execute(ddl)
        return
    _sous_verrou(conn, _corps_index)
