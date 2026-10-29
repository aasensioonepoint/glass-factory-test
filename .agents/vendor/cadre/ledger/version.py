"""LA VERSION DU MAGASIN — montée idempotente et REFUS de démarrer trop vieux.

Phase 2 de T-012. La version du store NE VIT NI DANS LE DDL NI DANS
`sqlite_master` (leçon du ticket T-00000625, mesurée sur cinq itérations) : elle
est portée par `PRAGMA user_version`, lisible AVANT toute ouverture applicative.
Elle est DISTINCTE de `version_schema_lecon`, qui est une COLONNE versionnée
indépendamment du noyau — l'une gouverne la STRUCTURE du store, l'autre le FORMAT
d'un enregistrement.

REFUS EXPLICITE, JAMAIS DE DÉGRADATION SILENCIEUSE (spec, ligne « Refus explicite
de démarrer si le schéma est plus récent que le binaire ») : un store en version
supérieure à ce que le binaire connaît lève `SchemaPlusRecent`, il ne s'ouvre pas
en mode réduit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cadre.ledger import schema

if TYPE_CHECKING:
    import sqlite3

__all__ = ["VERSION_SCHEMA", "SchemaPlusRecent", "SchemaInconnu", "lire_version",
           "garantir_schema"]

#: La version de schéma que CE binaire sait produire et lire. Passée à 2 par
#: `T-00000639` : la v2 ajoute la table de précédence
#: (`schema.creer_table_appliquee`). Sur un store neuf, `garantir_schema` joue
#: les migrations 1 PUIS 2 ; sur un store déjà à jour, elle ne rejoue rien.
VERSION_SCHEMA = 2


class SchemaPlusRecent(RuntimeError):
    """Le magasin est dans une version que ce binaire ne connaît pas."""


class SchemaInconnu(RuntimeError):
    """Le magasin porte une version NÉGATIVE : aucun binaire du kit n'en pose,
    le store est étranger ou abîmé. Levée avant toute écriture."""


def lire_version(conn: "sqlite3.Connection") -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _poser_version(conn: "sqlite3.Connection", valeur: int) -> None:
    # `PRAGMA user_version` n'accepte pas de paramètre lié ; `valeur` est un int
    # DÉRIVÉ de constantes du binaire (jamais une entrée externe), forcé par
    # `int()` — aucune injection possible.
    conn.execute("PRAGMA user_version = " + str(int(valeur)))


def garantir_schema(conn: "sqlite3.Connection") -> int:
    """Amène le store à `VERSION_SCHEMA` et rend la version atteinte.

    - courante 0 (store neuf)  : applique tout le schéma, pose `VERSION_SCHEMA` ;
    - courante < cible         : rejoue les migrations manquantes (idempotentes) ;
    - courante == cible        : rien ;
    - courante > cible         : `SchemaPlusRecent` — REFUS de démarrer ;
    - courante < 0             : `SchemaInconnu` — REFUS de démarrer.

    Un refus n'écrit RIEN. LA COURSE (T-00000905) : la montée prend le verrou
    d'écriture (`BEGIN IMMEDIATE`) et RE-SONDE sous lui avant toute migration —
    un kit plus récent qui a tamponné entre la sonde et la montée fait refuser,
    jamais rétrograder ; migrations et tampon tiennent en UNE transaction,
    annulée en bloc sur toute levée (patron de `stores_schemas._sous_verrou`).

    L'APPELANT : une transaction qu'il a ouverte est VALIDÉE dès que la première
    sonde accepte le store — avant la montée, donc aussi avant une re-sonde qui
    refuserait, et même sur un store déjà à jour ; un refus dès la première
    sonde ne valide rien. Son réglage (`isolation_level`, et `autocommit` sous
    Python >= 3.12) lui est rendu à l'identique.
    """
    courante = lire_version(conn)
    _refuser_version_inconnue(courante)
    if courante == VERSION_SCHEMA:
        conn.commit()
        return VERSION_SCHEMA
    # Valide d'abord une transaction ouverte par l'appelant, comme le `commit`
    # final le faisait déjà. EXPLICITE : le `commit` implicite du passage à
    # `isolation_level = None` (mesuré sous CPython 3.14) n'est pas un contrat.
    conn.commit()
    mode = conn.isolation_level
    # PEP 249 (`autocommit=False`, Python >= 3.12) : `isolation_level` y est sans
    # effet et une transaction reste ouverte — autocommit le temps de la montée.
    # Attribut absent (< 3.12) : le chemin legacy seul.
    auto = getattr(conn, "autocommit", None)
    if auto is False:
        conn.autocommit = True
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            courante = lire_version(conn)  # RE-SONDE sous le verrou d'écriture
            _refuser_version_inconnue(courante)
            for cible in range(courante + 1, VERSION_SCHEMA + 1):
                schema.MIGRATIONS[cible](conn)
            if courante < VERSION_SCHEMA:
                _poser_version(conn, VERSION_SCHEMA)
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = mode
        if auto is False:
            conn.autocommit = False
    return VERSION_SCHEMA


def _refuser_version_inconnue(courante: int) -> None:
    """Le refus, à la sonde comme à la re-sonde : levé avant toute écriture."""
    if courante > VERSION_SCHEMA:
        raise SchemaPlusRecent(
            "magasin en version " + str(courante) + ", ce binaire connaît "
            + str(VERSION_SCHEMA) + " : mets à jour le kit avant d'ouvrir ce "
            "store. Aucune dégradation silencieuse n'est faite."
        )
    if courante < 0:
        raise SchemaInconnu(
            "magasin en version " + str(courante) + " : le kit ne pose jamais de "
            "version négative, ce store est étranger ou abîmé. Rien n'est touché "
            "— déplace-le, ou restaure-le depuis une sauvegarde."
        )
