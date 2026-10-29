"""Banc de FORME et de VERSION du store V3 (`agentic_v3/db/schema.py`).

Deux tickets, un seul fichier de schéma (Étape B du LOT-2, T-012) :

  * T-00000629 — `events_ledger` était DÉCLARÉE à 6 colonnes et CRÉÉE à 9 (le
    CREATE + trois `ALTER ADD COLUMN` conditionnels). Aucune surface ne portait
    la forme vraie. Le témoin central compare les colonnes DÉCLARÉES par le
    `CREATE TABLE` aux colonnes RÉELLES après `create_tables`.
  * T-00000628 — le store ne portait AUCUNE version. `create_tables` pose
    désormais `PRAGMA user_version = SCHEMA_VERSION`, monte une base héritée sans
    destruction, est idempotent, et REFUSE une base venue d'un binaire plus récent.

INVARIANT DE MÉTHODE (mesuré, coûteux, payé) : jamais `:memory:`. `create_tables`
ouvre sa PROPRE connexion et ne la rend pas (-> None) ; une reconnexion `:memory:`
voit 0 objet et la fonction NE LÈVE PAS — le banc serait VERT PAR VACUITÉ. Tous
les témoins ici passent par un FICHIER TEMPORAIRE RÉEL (`tmp_path`) et rouvrent le
fichier pour introspecter.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path

import pytest

from agentic_v3.db import schema
from agentic_v3.db.schema import SCHEMA_VERSION, SchemaVersionError, create_tables

SCHEMA_SOURCE = Path(schema.__file__).read_text(encoding="utf-8")

# The six columns a LEGACY store (pre-T-00000629) declared: the CREATE TABLE
# stopped at created_at and the three others arrived only by ALTER.
_LEGACY_EVENTS_LEDGER_6COL = """
CREATE TABLE events_ledger (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _extract_create_table(source: str, table: str) -> str:
    """Return the literal `CREATE TABLE ... ( ... );` text for `table` as it is
    WRITTEN in the schema source — not what the running code produces."""
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS " + re.escape(table) + r"\s*\(.*?\);",
        source,
        re.DOTALL,
    )
    assert match is not None, f"no CREATE TABLE for {table!r} found in schema source"
    return match.group(0)


def _columns_of(conn: sqlite3.Connection, table: str) -> list[str]:
    # PRAGMA accepts no bound parameter; `table` is a test-local literal
    # ('events_ledger'), never external input.
    # nosemgrep: agents.security.python-sql-injection-string-format
    sql = f"PRAGMA table_info({table})"
    return [row[1] for row in conn.execute(sql).fetchall()]


def _declared_columns(source: str, table: str, tmp_path: Path) -> list[str]:
    """Columns the CREATE TABLE *declares*, read the way SQLite itself parses
    them: run ONLY the extracted CREATE statement in a throwaway real file, then
    ask PRAGMA table_info. No hand-rolled token parsing that could disagree with
    the engine."""
    ddl = _extract_create_table(source, table)
    scratch = tmp_path / "declared.db"
    with sqlite3.connect(str(scratch)) as conn:
        conn.execute(ddl)
        return _columns_of(conn, table)


def test_les_colonnes_DECLAREES_egalent_les_colonnes_REELLES(tmp_path: Path) -> None:
    """Le CREATE TABLE d'`events_ledger` déclare EXACTEMENT la table créée."""
    real_db = tmp_path / "real.db"
    create_tables(real_db)

    with sqlite3.connect(str(real_db)) as conn:
        # Non-vacuité 1 : la table lue est bien celle qu'on prétend lire.
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events_ledger'"
            ).fetchall()
        ]
        assert names == ["events_ledger"], f"events_ledger absent, tables lues: {names}"
        real_cols = _columns_of(conn, "events_ledger")

    declared_cols = _declared_columns(SCHEMA_SOURCE, "events_ledger", tmp_path)

    # Non-vacuité 2 : on mesure une table NON VIDE de colonnes des deux côtés.
    assert len(real_cols) > 0, "PRAGMA table_info rend 0 colonne — store vide (vacuité)"
    assert len(declared_cols) > 0, "le CREATE TABLE parsé ne déclare aucune colonne"

    # Le cœur du témoin : déclaré == réel, en ensemble ET en compte.
    assert set(declared_cols) == set(real_cols), (
        f"forme DÉMENTIE — déclaré={sorted(declared_cols)} "
        f"réel={sorted(real_cols)} (manquants au CREATE: "
        f"{sorted(set(real_cols) - set(declared_cols))})"
    )
    assert len(declared_cols) == len(real_cols)


def test_store_HERITE_6_colonnes_monte_a_11_avec_user_version_2(tmp_path: Path) -> None:
    """Une base à 6 colonnes (user_version=0) est montée à 11 + version, SANS
    destruction : une ligne préexistante survit. T-00000650 ajoute `ulid` et
    `predecesseur_ulid`, portant le store à 11 colonnes et `user_version = 2`."""
    legacy_db = tmp_path / "legacy.db"
    with sqlite3.connect(str(legacy_db)) as conn:
        conn.execute(_LEGACY_EVENTS_LEDGER_6COL)
        conn.execute(
            "INSERT INTO events_ledger (task_id, agent_role, event_type, payload_json) "
            "VALUES ('T-old', 'dev-multi', 'legacy_event', '{}')"
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        assert len(_columns_of(conn, "events_ledger")) == 6

    create_tables(legacy_db)

    with sqlite3.connect(str(legacy_db)) as conn:
        cols = _columns_of(conn, "events_ledger")
        assert set(cols) >= {
            "operation_id", "event_kind", "attempt", "ulid", "predecesseur_ulid",
        }
        assert len(cols) == 11, f"attendu 11 colonnes après montée, lu {len(cols)}: {cols}"
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 2
        # Aucune destruction : la ligne héritée est toujours là.
        surviving = conn.execute(
            "SELECT task_id, event_type FROM events_ledger WHERE task_id='T-old'"
        ).fetchall()
        assert surviving == [("T-old", "legacy_event")]


def test_montee_jouee_DEUX_fois_donne_le_MEME_etat(tmp_path: Path) -> None:
    """Idempotence : deux passages laissent schéma, colonnes et version identiques."""
    db = tmp_path / "idempotent.db"

    def snapshot() -> tuple:
        with sqlite3.connect(str(db)) as conn:
            tables = tuple(
                sorted(
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                )
            )
            ledger = tuple(_columns_of(conn, "events_ledger"))
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        return (tables, ledger, version)

    create_tables(db)
    first = snapshot()
    create_tables(db)
    second = snapshot()

    assert first == second, f"état divergent après rejeu: {first!r} != {second!r}"
    assert first[2] == SCHEMA_VERSION


def _empreinte_du_store(db: Path, tmp_path: Path) -> tuple:
    """Tout ce qu'une SEULE écriture perturberait : les octets bruts du fichier,
    son `journal_mode`, les tables que `sqlite_master` liste, et les noms triés de
    TOUS les fichiers de `tmp_path` — un basculement WAL déposerait `-wal`/`-shm`.
    Les octets sont lus AVANT toute connexion, pour que la mesure elle-même ne
    puisse pas fabriquer l'égalité qu'elle prétend constater."""
    data = db.read_bytes()
    with sqlite3.connect(str(db)) as conn:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = tuple(
            sorted(
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            )
        )
    fichiers = tuple(sorted(p.name for p in tmp_path.iterdir()))
    return (data, journal, tables, fichiers)


def test_un_user_version_SUPERIEUR_est_REFUSE_sans_toucher_au_store(tmp_path: Path) -> None:
    """Un store d'un binaire plus récent (user_version > SCHEMA_VERSION) est
    refusé et laissé INTACT — mesuré par empreinte AVANT/APRÈS : octets,
    `journal_mode`, tables et fichiers latéraux. La sonde nue ne bascule PAS le
    store en WAL, donc rien n'apparaît à côté."""
    future_db = tmp_path / "future.db"
    future_version = SCHEMA_VERSION + 1
    with sqlite3.connect(str(future_db)) as conn:
        conn.execute("CREATE TABLE sentinel_future (x INTEGER)")
        conn.execute("INSERT INTO sentinel_future (x) VALUES (42)")
        # PRAGMA accepts no bound parameter; `future_version` is SCHEMA_VERSION+1,
        # an int computed in-test, never external input.
        # nosemgrep: agents.security.python-sql-injection-string-format
        conn.execute(f"PRAGMA user_version = {future_version}")
        conn.commit()

    avant = _empreinte_du_store(future_db, tmp_path)

    with pytest.raises(SchemaVersionError):
        create_tables(future_db)

    apres = _empreinte_du_store(future_db, tmp_path)

    # Le refus n'a rien touché : empreinte identique, bit pour bit.
    assert avant == apres, (
        "le store refusé a été MODIFIÉ — "
        f"journal {avant[1]}->{apres[1]}, fichiers {avant[3]}->{apres[3]}, "
        f"octets {'identiques' if avant[0] == apres[0] else 'DIVERGENTS'}"
    )
    # Non-vacuité : on a bien mesuré un store réel, non un fantôme.
    assert avant[3] == ("future.db",), f"fichiers latéraux inattendus: {avant[3]}"

    # Et la sémantique tient : version conservée, sentinelle intacte.
    with sqlite3.connect(str(future_db)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == future_version
        assert conn.execute("SELECT x FROM sentinel_future").fetchone()[0] == 42


def test_create_tables_a_jour_ne_prend_AUCUN_verrou_meme_sous_BEGIN_IMMEDIATE(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un store DÉJÀ à `SCHEMA_VERSION` se rejoue sans prendre le moindre verrou
    d'écriture : `create_tables` réussit alors qu'une AUTRE connexion tient un
    `BEGIN IMMEDIATE`. Le tampon est conditionnel — un tampon inconditionnel
    bloquerait ici. Le timeout est raccourci pour qu'une régression échoue VITE
    (0,3 s) au lieu d'attendre les 30 s du verrou."""
    db = tmp_path / "locked.db"
    create_tables(db)  # -> user_version = SCHEMA_VERSION, à jour

    holder = sqlite3.connect(str(db), timeout=30.0)
    holder.execute("PRAGMA journal_mode=WAL")
    holder.execute("BEGIN IMMEDIATE")  # verrou d'écriture tenu pendant tout le test

    real_connect = sqlite3.connect

    def fast_connect(*args, **kwargs):
        kwargs["timeout"] = 0.3
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(schema.sqlite3, "connect", fast_connect)
    try:
        create_tables(db)  # ne doit PAS avoir besoin d'un verrou
        create_tables(db)  # deux fois : idempotent et toujours sans verrou
    finally:
        holder.rollback()
        holder.close()


def test_deux_appels_a_jour_laissent_les_octets_IDENTIQUES_apres_checkpoint(
    tmp_path: Path,
) -> None:
    """Entre deux appels sur un store à jour, aucun octet ne bouge — mesuré après
    un `wal_checkpoint(TRUNCATE)` pour que le contenu volatile du `-wal` n'entre
    pas dans la comparaison."""
    db = tmp_path / "stable.db"
    create_tables(db)

    def octets_apres_checkpoint() -> bytes:
        with sqlite3.connect(str(db)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return db.read_bytes()

    avant = octets_apres_checkpoint()
    assert avant, "store vide — mesure vacante"
    create_tables(db)  # store à jour : aucune écriture attendue
    apres = octets_apres_checkpoint()

    assert avant == apres, "un appel sur un store à jour a modifié les octets"


def test_une_COURSE_pose_un_user_version_SUPERIEUR_entre_sonde_et_tampon_est_REFUSEE(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Course : la sonde nue lit une version montante (0), puis un AUTRE écrivain
    pose `user_version = SCHEMA_VERSION + 1` avant que le tampon ne s'écrive. La
    relecture sous `BEGIN IMMEDIATE` le voit et REFUSE — le tampon est annulé
    (jamais de dégradation), la version reste à celle de l'écrivain récent.

    Simulation : on intercale l'écrivain concurrent DANS `get_db_connection`, qui
    est appelée APRÈS la sonde nue et AVANT le bloc de tampon."""
    race_db = tmp_path / "race.db"
    ahead = SCHEMA_VERSION + 1
    with sqlite3.connect(str(race_db)) as conn:
        conn.execute("PRAGMA user_version = 0")  # la sonde lira 0 -> entre au tampon
        conn.commit()

    real_get_conn = schema.get_db_connection

    def racing_get_conn(db_path):
        # Un binaire PLUS RÉCENT gagne la course juste après la sonde nue.
        writer = sqlite3.connect(str(db_path))
        try:
            # PRAGMA sans paramètre lié ; `ahead` est un int calculé au test.
            # nosemgrep: agents.security.python-sql-injection-string-format
            writer.execute(f"PRAGMA user_version = {ahead}")
            writer.commit()
        finally:
            writer.close()
        return real_get_conn(db_path)

    monkeypatch.setattr(schema, "get_db_connection", racing_get_conn)

    with pytest.raises(SchemaVersionError):
        create_tables(race_db)

    # Jamais redescendue : la version de l'écrivain récent est conservée.
    with sqlite3.connect(str(race_db)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ahead


# ---------------------------------------------------------------------------
# T-00000770 — le store V3 s'ouvre SANS SUIVRE (`cadre.ledger.store`, par la
# couture `run_export._cadre`) : un lien à l'emplacement est refusé AVANT toute
# ouverture, un store neuf naît en 0o600, `get_db_connection` ne crée plus.
# ---------------------------------------------------------------------------

_SANS_O_NOFOLLOW = pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"),
                                      reason="O_NOFOLLOW absent (R3 de T-00000759)")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _base_etrangere_tenue(chemin: Path) -> tuple[sqlite3.Connection, list[Path]]:
    """Une base V3 RÉELLE (schéma + une ligne) tenue OUVERTE en WAL : ses TROIS
    fichiers (base, `-wal`, `-shm`) existent tant que la connexion vit. Rend la
    connexion (à fermer par l'appelant) et les trois chemins."""
    create_tables(chemin)
    tenue = sqlite3.connect(str(chemin))
    tenue.execute("PRAGMA journal_mode=WAL")
    tenue.execute(
        "INSERT INTO events_ledger (task_id, agent_role, event_type, payload_json) "
        "VALUES ('T-1', 'banc', 'banc', '{}')")
    tenue.commit()
    trois = [chemin, Path(str(chemin) + "-wal"), Path(str(chemin) + "-shm")]
    assert all(p.exists() for p in trois), "banc non armé : la base tierce n'a pas trois fichiers"
    return tenue, trois


def test_memory_est_refuse_sans_creer_de_fichier_t770(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W1 — `":memory:"` n'est pas un emplacement de store : sans la garde, la
    création exclusive ferait naître un FICHIER de ce nom dans le cwd. Les deux
    entrées lèvent `ValueError` nommant la valeur, et rien n'apparaît. Rouge sur
    BASE (SQLite l'ouvrait en mémoire, sans lever). Mord : Mm (garde retirée)."""
    monkeypatch.chdir(tmp_path)
    for entree in (schema.get_db_connection, create_tables):
        with pytest.raises(ValueError, match=":memory:"):
            entree(":memory:")
    assert not (tmp_path / ":memory:").exists(), "un fichier `:memory:` a été créé"


@_SANS_O_NOFOLLOW
def test_create_tables_refuse_un_lien_a_l_emplacement_t770(tmp_path: Path) -> None:
    """V1 — `create_tables` sur un lien PENDANT : refus nommé « lien
    symbolique », la cible n'est JAMAIS créée (la sonde nue de BASE,
    `sqlite3.connect(str(path))`, suivait le lien et créait sa cible) ; sur un
    lien vers une base V3 tierce vivante : refus, ses trois fichiers inchangés.
    Mord : Me (sonde rendue à `sqlite3.connect(str(path_obj))`)."""
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    pendant = tmp_path / "pendant.db"
    os.symlink(dehors / "cible.db", pendant)
    with pytest.raises(ValueError, match="lien symbolique"):
        create_tables(pendant)
    assert not (dehors / "cible.db").exists(), "la cible du lien pendant a été créée"
    assert pendant.is_symlink(), "le lien a été retiré"

    tenue, trois = _base_etrangere_tenue(dehors / "tierce.db")
    try:
        avant = [_sha(p) for p in trois]
        lien = tmp_path / "lien.db"
        os.symlink(trois[0], lien)
        with pytest.raises(ValueError, match="lien symbolique"):
            create_tables(lien)
        assert [_sha(p) for p in trois] == avant, "la base tierce a été écrite"
    finally:
        tenue.close()


@_SANS_O_NOFOLLOW
def test_get_db_connection_refuse_un_lien_vers_une_base_tierce_t770(tmp_path: Path) -> None:
    """V2 — `get_db_connection` sur un lien vers une base V3 tierce vivante :
    refus nommé, ses trois fichiers inchangés (BASE la suivait et la passait en
    WAL). Mord : Mf (`get_db_connection` rendu à l'ancien)."""
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    tenue, trois = _base_etrangere_tenue(dehors / "tierce.db")
    try:
        avant = [_sha(p) for p in trois]
        lien = tmp_path / "lien.db"
        os.symlink(trois[0], lien)
        with pytest.raises(ValueError, match="lien symbolique"):
            schema.get_db_connection(lien)
        assert [_sha(p) for p in trois] == avant, "la base tierce a été écrite"
    finally:
        tenue.close()


@_SANS_O_NOFOLLOW
def test_backfill_refuse_un_lien_a_la_place_de_la_base_t770(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V3 — `backfill_historique(base=<lien>)` : `_ouvrir_base_sqlite` refuse le
    lien (`RunExportError` « refus d'ouverture : … lien symbolique »), la base
    tierce est intacte. BASE suivait le lien et lisait la base tierce. Mord : Mg
    (`_ouvrir_base_sqlite` rendu à l'ancien)."""
    from agentic_v3.db import run_export  # noqa: PLC0415

    (tmp_path / "projet").mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(tmp_path / "projet"))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    tenue, trois = _base_etrangere_tenue(dehors / "tierce.db")
    try:
        avant = [_sha(p) for p in trois]
        lien = tmp_path / "lien.db"
        os.symlink(trois[0], lien)
        with pytest.raises(run_export.RunExportError, match="refus d'ouverture") as refus:
            run_export.backfill_historique(base=lien, auteur="banc@test")
        assert "lien symbolique" in str(refus.value), str(refus.value)
        assert [_sha(p) for p in trois] == avant, "la base tierce a été écrite"
    finally:
        tenue.close()


def test_create_tables_fait_naitre_un_store_neuf_en_0o600_t770(tmp_path: Path) -> None:
    """V4 — un store V3 NEUF naît en 0o600 (création exclusive, décision R1 de
    T-00000759) ; BASE le faisait naître par SQLite en 0o644 sous umask 022.
    Mord : Ml (`mode=0o644`)."""
    ancien = os.umask(0o022)
    try:
        neuf = tmp_path / "run" / "v3_event_store.db"
        create_tables(neuf)
    finally:
        os.umask(ancien)
    assert oct(neuf.stat().st_mode & 0o777) == "0o600"


def test_get_db_connection_ne_cree_plus_un_store_absent_t770(tmp_path: Path) -> None:
    """V5 — `get_db_connection` sur un chemin ABSENT lève `ValueError` nommant
    le chemin et le remède (« create_tables … d'abord »), sans créer de fichier.
    BASE créait une base vide sans schéma. Mord : Mf."""
    absent = tmp_path / "jamais.db"
    with pytest.raises(ValueError) as refus:
        schema.get_db_connection(absent)
    message = str(refus.value)
    assert str(absent) in message and "create_tables" in message and "d'abord" in message, message
    assert not absent.exists(), "get_db_connection a créé le store"
