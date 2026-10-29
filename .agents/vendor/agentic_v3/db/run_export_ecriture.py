"""Forme du store V3 exigée avant la frappe des ULID de `run_export backfill`.

Module frère de `run_export.py`, chargé PARESSEUSEMENT par lui — import dans la
fonction appelante, jamais en tête, comme `naissance_partition` — pour que
`run_export.py` ne grossisse pas (cliquet des 1600 lignes, S-00002684, S-00004034). Deux refus, dans
l'ordre où `run_export._ouvrir_base_sqlite` les appelle : le schéma FUTUR, puis la
forme ANTÉRIEURE sans `ulid`. Puis, au seuil de la phase d'écriture de
`run_export.backfill_historique`, la RELECTURE de version sous `BEGIN IMMEDIATE`
(R3-bis, T-00001082) : `relire_version_sous_verrou`.

Il n'importe PAS `run_export` : lancé en forme chemin
(`python3 agentic_v3/db/run_export.py backfill`), ce module-là est `__main__`, et
la `RunExportError` qu'attrape son `_cli` (rc 6) n'est pas celle du paquet. La
classe à lever est donc PASSÉE par l'appelant (T-00001097).

Seul SQL ici : des `PRAGMA`, aucun `SELECT`, `INSERT` ni `UPDATE` — le filet de
localité SQL du dépôt ne compte pas ce module parmi ses exceptions.
"""

import sqlite3
from pathlib import Path
from typing import Type

#: Les deux colonnes que la frappe lit puis écrit, apportées par la forme v2
#: (`SCHEMA_VERSION` = 2, T-00000650) : un store qui en manque une est antérieur.
COLONNES_FRAPPE = ("ulid", "predecesseur_ulid")


def refuser_schema_futur(conn: sqlite3.Connection, chemin: Path) -> None:
    """Corps de `run_export._refuser_schema_futur` (T-00001075), déplacé ici tel
    quel (T-00001097) : lit `PRAGMA user_version` sur la connexion NUE et lève
    `SchemaVersionError` — la classe du PAQUET `agentic_v3.db.schema`, celle de
    `create_tables` — quand la version DÉPASSE `SCHEMA_VERSION`."""
    from agentic_v3.db.schema import SCHEMA_VERSION, SchemaVersionError  # paresseux

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"{chemin} porte user_version={version} mais ce binaire implémente "
            f"v{SCHEMA_VERSION} : un kit PLUS RÉCENT l'a écrit. Refus d'y toucher."
        )


def relire_version_sous_verrou(conn: sqlite3.Connection, chemin: Path) -> None:
    """R3-bis, la COURSE (T-00001082) : RELIT `PRAGMA user_version` sur `conn`, que
    `run_export.backfill_historique` a passée en `BEGIN IMMEDIATE` juste avant —
    verrou d'écriture tenu, aucun autre écrivain ne peut plus migrer le store
    jusqu'au commit. Un kit PLUS RÉCENT qui l'a migré ENTRE la lecture de
    l'ouverture et ce verrou est VU ici : la transaction est défaite (`rollback`),
    puis `SchemaVersionError` du PAQUET est levée — `classer_refus` la classe en
    `CAUSE_VERSION`, code 4 au bord de `_cli` — avant tout UPDATE. Seule une
    version qui DÉPASSE `SCHEMA_VERSION` est refusée, comme dans `create_tables`
    (patron de sa relecture) : le tampon d'un kit de CETTE version vers v2 ne
    change pas les colonnes que la frappe lit et écrit."""
    from agentic_v3.db.schema import SCHEMA_VERSION, SchemaVersionError  # paresseux

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        conn.rollback()
        raise SchemaVersionError(
            f"{chemin} est passé à user_version={version} ENTRE l'ouverture et "
            f"l'écriture (course R3-bis) mais ce binaire implémente v{SCHEMA_VERSION} : "
            "un kit PLUS RÉCENT l'a migré. Rien n'est frappé — refus d'y toucher."
        )


def refuser_sans_ulid(conn: sqlite3.Connection, chemin: Path, erreur: Type[Exception]) -> None:
    """Lève `erreur` quand `events_ledger` existe SANS l'une de `COLONNES_FRAPPE`
    (store v0 ou v1, antérieur à la forme v2) : le message nomme le chemin, la
    version lue, les colonnes manquantes et le remède, `create_tables()`, qui les
    ajoute (mesuré : `user_version` 0 -> 2, puis une ligne frappée).

    Appelé par `run_export._ouvrir_base_sqlite` APRÈS le refus de version et avant
    toute lecture de ligne de ce store : un store FUTUR sans `ulid` reste refusé en
    `CAUSE_VERSION` (T-00001075). Une table ABSENTE (base de 0 octet, store sans
    `events_ledger`) PASSE : sa première lecture lève plus loin `OperationalError`
    code 1, brute (résidu R2)."""
    from agentic_v3.db.schema import SCHEMA_VERSION  # paresseux, comme run_export

    colonnes = {str(r[1]) for r in conn.execute("PRAGMA table_info(events_ledger)")}
    manquantes = [c for c in COLONNES_FRAPPE if c not in colonnes]
    if colonnes and manquantes:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        raise erreur(
            f"{chemin} : events_ledger sans colonne {', '.join(manquantes)} "
            f"(user_version={version}, forme antérieure à v{SCHEMA_VERSION}) — monte "
            "ce store par create_tables() (agentic_v3.db.schema), puis relance ; "
            "aucune ligne n'est frappée."
        )
