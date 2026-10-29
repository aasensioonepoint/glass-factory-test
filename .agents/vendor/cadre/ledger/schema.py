"""LE SCHÉMA DU MAGASIN DE LEÇONS — DDL et migrations idempotentes.

Phase 2 de T-012. Ce module DÉCRIT le schéma ; il n'ouvre aucune connexion
(c'est `store.py`) et ne lit pas la version (c'est `version.py`). Il opère sur
une connexion REÇUE — d'où l'annotation `sqlite3.Connection` sous `TYPE_CHECKING`
seulement, pour que `sqlite3` ne soit importé à l'exécution QUE par `store.py`.

LE SCHÉMA DE LEÇON EST COMPLET DÈS LA v0.1 — la spec le commande (« Classification
à l'écriture, pas après coup » ; « ce qui ne se rattrape pas, c'est ce qui n'a
pas été enregistré ») : un champ oublié ici coûte une relecture manuelle de tout
le magasin, pas une dette ordinaire. Deux axes ORTHOGONAUX :

  - AXE 1, précédence : `provenance ∈ {embarquee, distante, locale}`.
  - AXE 2, dualité — généralisation à la source : une leçon LOCALE (jamais
    partageable par construction) et sa FORME GÉNÉRALISÉE le cas échéant sont
    DEUX enregistrements distincts, liés par `ref_forme_generalisee`, JAMAIS
    fusionnés. Ce qui sort n'est pas une version épurée : c'est un objet distinct.

Le CONTENU EST STOCKÉ EN CLAIR (`contenu TEXT NOT NULL`), pas seulement son
`hash_contenu` : la spec exige que chaque leçon candidate soit « présentée en
clair au relecteur » — un hash ne se relit pas. La locale stocke son contexte,
la forme généralisée stocke son texte générique ; ce sont deux `contenu`
distincts, comme ce sont deux enregistrements distincts.

Le partage opt-in à TROIS NIVEAUX est porté par le SCHÉMA dès la v0.1 même si
aucun niveau n'est implémenté en Phase 2 — et les niveaux sont CONTRAINTS, pas
seulement déclarés :

  - `reference_accord` (référence d'un accord client externe, jamais un
    consentement interactif) ;
  - `statut_partage` incluant `en_attente_de_revue` (revue du contenu), avec
    `revue_par` / `revue_horodatage` : « aucune leçon ne sort sans acte de revue
    enregistré », donc un statut `revue_faite`/`partage` EXIGE ces deux champs ;
  - `validateur_1`/`validateur_2` (double validation par deux comptes distincts,
    vérifiable APPLICATIVEMENT — sinon « c'est une case cochée deux fois »).

CES RÈGLES SONT DES CHECK, PAS DES COMMENTAIRES — une écriture qui les viole est
REFUSÉE par SQLite, pas découverte à la relecture :

  - portée `locale` ⇒ `statut_partage = 'prive'` (la locale ne sort jamais) ;
  - pas de `validateur_2` sans `validateur_1` ;
  - deux validateurs DISTINCTS, casse repliée et espaces rognés
    (`lower(trim(...))`) — `lower()` SQLite ne replie que l'ASCII, borne assumée ;
  - `statut_partage` `revue_faite`/`partage` ⇒ `revue_par` + `revue_horodatage` ;
  - `statut_partage = 'partage'` ⇒ `reference_accord` + deux validateurs.

MINIMISATION, CONTRAINTE DE SCHÉMA : `identite_declaree` est déclarative et
modifiable (indice, jamais preuve). AUCUNE COLONNE MACHINE — pas de hostname,
d'utilisateur système ni d'IP : données personnelles à valeur probante faible.
L'origine `hôte` désigne l'HÔTE D'AGENT (Claude Code, Codex…), jamais la machine.

`version_schema_lecon` versionne le FORMAT d'un enregistrement, INDÉPENDAMMENT du
noyau et de la version du store (`PRAGMA user_version`, porté par `version.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

__all__ = ["TABLE", "TABLE_APPLIQUEE", "COLONNES", "MIGRATIONS", "creer_schema",
           "creer_table_appliquee", "PROVENANCES", "PORTEES", "STATUTS_PARTAGE",
           "STATUTS_SYNC"]

TABLE = "lecons"

#: La table AUXILIAIRE de précédence (schéma v2, `T-00000639`). Elle NOMME, par
#: sujet, la leçon actuellement APPLIQUÉE — un POINTEUR, jamais une copie.
#: SÉPARÉE de `lecons` À DESSEIN : la précédence est une propriété ENTRE leçons,
#: pas un champ d'UNE leçon — le schéma de leçon, lui, reste EXACTEMENT celui de
#: la spec (aucune colonne ajoutée à `lecons`). La logique qui la maintient et la
#: lit vit dans `precedence.py` ; seul le DDL vit ici, où vit tout le DDL du
#: service.
TABLE_APPLIQUEE = "lecon_appliquee"

#: Valeurs fermées, en CHECK plutôt qu'en commentaire : une valeur hors
#: énumération est REFUSÉE à l'écriture, pas découverte à la relecture.
PROVENANCES = ("embarquee", "distante", "locale")
PORTEES = ("locale", "partageable", "generale")
STATUTS_PARTAGE = ("prive", "en_attente_de_revue", "revue_faite", "partage", "revoque")
STATUTS_SYNC = ("local", "en_attente", "synchronise")

#: L'ordre canonique des colonnes. `lessons.py` s'y aligne pour ses INSERT ; le
#: banc `le_schema_de_lecon_porte_EXACTEMENT_les_champs_de_la_spec` compare le
#: schéma RÉEL (PRAGMA table_info) à la liste dérivée de la spec, jamais à
#: celle-ci — les deux ne doivent pas être la même source.
COLONNES = (
    "ulid", "hash_contenu", "contenu", "cle_sujet", "portee", "type", "provenance",
    "origine_projet", "origine_hote", "origine_agent", "origine_run",
    "statut_partage", "statut_sync", "version_schema_lecon",
    "ref_forme_generalisee", "tenant_id", "project_id", "reference_accord",
    "identite_declaree", "horodatage", "validateur_1", "validateur_2",
    "revue_par", "revue_horodatage",
)


def _liste_sql(valeurs: tuple[str, ...]) -> str:
    """Une liste `IN ('a', 'b', ...)` depuis un n-uplet de littéraux CONTRÔLÉS
    (constantes de ce module, jamais une entrée externe)."""
    return "(" + ", ".join("'" + v + "'" for v in valeurs) + ")"


_DDL_LECONS = (
    "CREATE TABLE IF NOT EXISTS " + TABLE + " (\n"
    "    ulid                   TEXT    PRIMARY KEY NOT NULL,\n"
    "    hash_contenu           TEXT    NOT NULL,\n"
    "    contenu                TEXT    NOT NULL,\n"
    "    cle_sujet              TEXT    NOT NULL,\n"
    "    portee                 TEXT    NOT NULL,\n"
    "    type                   TEXT,\n"
    "    provenance             TEXT    NOT NULL,\n"
    "    origine_projet         TEXT,\n"
    "    origine_hote           TEXT,\n"
    "    origine_agent          TEXT,\n"
    "    origine_run            TEXT,\n"
    "    statut_partage         TEXT    NOT NULL,\n"
    "    statut_sync            TEXT    NOT NULL,\n"
    "    version_schema_lecon   INTEGER NOT NULL,\n"
    "    ref_forme_generalisee  TEXT    REFERENCES " + TABLE + "(ulid),\n"
    "    tenant_id              TEXT    NOT NULL,\n"
    "    project_id             TEXT    NOT NULL,\n"
    "    reference_accord       TEXT,\n"
    "    identite_declaree      TEXT,\n"
    "    horodatage             TEXT    NOT NULL,\n"
    "    validateur_1           TEXT,\n"
    "    validateur_2           TEXT,\n"
    "    revue_par              TEXT,\n"
    "    revue_horodatage       TEXT,\n"
    "    CHECK (provenance IN " + _liste_sql(PROVENANCES) + "),\n"
    "    CHECK (portee IN " + _liste_sql(PORTEES) + "),\n"
    "    CHECK (statut_partage IN " + _liste_sql(STATUTS_PARTAGE) + "),\n"
    "    CHECK (statut_sync IN " + _liste_sql(STATUTS_SYNC) + "),\n"
    # Borne BASSE seule : `version_schema_lecon >= 1`. La borne HAUTE n'est PAS
    # figée dans le DDL — un store à v1 non encore migré rejetterait sinon une
    # ligne v2 parfaitement valide (le DDL est `IF NOT EXISTS`, il ne se rejoue
    # pas) ; l'appelant borne le haut par `lessons.VERSION_SCHEMA_LECON`.
    "    CHECK (version_schema_lecon >= 1),\n"
    # Portée locale ⇒ statut FORCÉ à 'prive' : la leçon locale ne sort jamais par
    # construction (spec § généralisation à la source).
    "    CHECK (portee <> 'locale' OR statut_partage = 'prive'),\n"
    # Pas de second validateur sans le premier.
    "    CHECK (validateur_2 IS NULL OR validateur_1 IS NOT NULL),\n"
    # Deux comptes DISTINCTS (spec « deux comptes distincts ») : casse repliée,
    # espaces rognés. `lower()` SQLite ne replie que l'ASCII — deux identités ne
    # différant que par la casse d'un caractère non-ASCII passeraient ; borne
    # connue et assumée en Phase 2.
    "    CHECK (validateur_1 IS NULL OR validateur_2 IS NULL "
    "OR lower(trim(validateur_1)) <> lower(trim(validateur_2))),\n"
    # « Aucune leçon ne sort sans acte de revue enregistré » : un statut
    # revue faite / partagé EXIGE le relecteur ET l'horodatage de revue.
    "    CHECK (statut_partage NOT IN ('revue_faite', 'partage') "
    "OR (revue_par IS NOT NULL AND revue_horodatage IS NOT NULL)),\n"
    # Partage effectif ⇒ référence d'accord client + double validation (spec,
    # niveaux 1 et 3 du partage opt-in).
    "    CHECK (statut_partage <> 'partage' "
    "OR (reference_accord IS NOT NULL AND validateur_1 IS NOT NULL "
    "AND validateur_2 IS NOT NULL))\n"
    ")"
)

_DDL_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_" + TABLE + "_cle_sujet ON " + TABLE + "(cle_sujet)",
    "CREATE INDEX IF NOT EXISTS ix_" + TABLE + "_hash ON " + TABLE + "(hash_contenu)",
    # DÉDUP — DEUX index partiels DISJOINTS (correctif binôme PORTE 3, B1). Le DDL
    # v1 est MODIFIÉ EN PLACE, et c'est ADMIS : aucun store n'est déployé hors des
    # fichiers temporaires des bancs, donc pas de migration à écrire. La dédup
    # mono-index `(tenant, projet, portée, hash)` laissait une écriture LOCALE
    # RÉUTILISER la ligne d'une AUTRE provenance de même contenu ; la précédence
    # lisait alors la provenance de la ligne réutilisée, si bien qu'une locale
    # « appliquée » ressortait embarquée. Séparés par portée :
    #   * NON-LOCALE `(tenant, projet, portée, hash)` — la forme généralisée
    #     (partageable) déduplique par contenu, provenance indifférente : elle ne
    #     concourt PAS à la précédence.
    #   * LOCALE `(tenant, projet, cle_sujet, provenance, hash)` — une locale de
    #     provenance DIFFÉRENTE, ou sur un AUTRE sujet, est une ligne DISTINCTE, si
    #     bien que la précédence voit la VRAIE provenance de chaque écriture.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_" + TABLE + "_dedup ON " + TABLE
    + "(tenant_id, project_id, portee, hash_contenu) WHERE portee <> 'locale'",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_" + TABLE + "_dedup_locale ON " + TABLE
    + "(tenant_id, project_id, cle_sujet, provenance, hash_contenu) "
    "WHERE portee = 'locale'",
)


def creer_schema(conn: "sqlite3.Connection") -> None:
    """Crée la table et les index du magasin. IDEMPOTENT (`IF NOT EXISTS`), donc
    rejouable sur un store déjà en service sans effet de bord."""
    conn.execute(_DDL_LECONS)
    for ddl in _DDL_INDEX:
        conn.execute(ddl)


_DDL_APPLIQUEE = (
    "CREATE TABLE IF NOT EXISTS " + TABLE_APPLIQUEE + " (\n"
    "    tenant_id   TEXT NOT NULL,\n"
    "    project_id  TEXT NOT NULL,\n"
    "    cle_sujet   TEXT NOT NULL,\n"
    # POINTEUR vers la leçon appliquée ; la FK garantit qu'il ne pend jamais sur
    # une leçon absente (`PRAGMA foreign_keys = ON`, posé par store.py en écriture).
    "    ulid        TEXT NOT NULL REFERENCES " + TABLE + "(ulid),\n"
    # AU PLUS une appliquée par (tenant, projet, sujet) : la clé primaire PORTE la
    # règle, elle ne la commente pas. `precedence.appliquer_precedence` fait un
    # UPSERT sur cette clé pour déplacer le pointeur sans jamais le dupliquer.
    "    PRIMARY KEY (tenant_id, project_id, cle_sujet)\n"
    ")"
)


#: RATTRAPAGE v2 (correctif binôme PORTE 3, N2). Un store v1 peut déjà porter des
#: leçons écrites AVANT que le pointeur d'application existe ; la montée v2 crée
#: la table VIDE, donc aucun sujet n'aurait d'appliquée. On AMORCE le pointeur
#: avec la MEILLEURE leçon `portee = 'locale'` par sujet — celle que la règle de
#: précédence aurait posée à l'écriture : rang de provenance DESC (locale >
#: distante > embarquee), puis horodatage DESC, puis ulid DESC. `INSERT OR IGNORE`
#: rend l'amorçage idempotent : il ne détrône jamais un pointeur déjà posé.
_DDL_RATTRAPAGE_APPLIQUEE = (
    "INSERT OR IGNORE INTO " + TABLE_APPLIQUEE
    + " (tenant_id, project_id, cle_sujet, ulid)\n"
    "SELECT tenant_id, project_id, cle_sujet, ulid FROM (\n"
    "    SELECT tenant_id, project_id, cle_sujet, ulid,\n"
    "           ROW_NUMBER() OVER (\n"
    "               PARTITION BY tenant_id, project_id, cle_sujet\n"
    "               ORDER BY CASE provenance\n"
    "                   WHEN 'locale' THEN 2 WHEN 'distante' THEN 1\n"
    "                   WHEN 'embarquee' THEN 0 ELSE -1 END DESC,\n"
    "               horodatage DESC, ulid DESC\n"
    "           ) AS rn\n"
    "    FROM " + TABLE + " WHERE portee = 'locale'\n"
    ") WHERE rn = 1"
)


def creer_table_appliquee(conn: "sqlite3.Connection") -> None:
    """Migration v2 : la table de précédence (pointeur d'application par sujet).
    IDEMPOTENT (`IF NOT EXISTS`) — rejouable sans effet de bord. Ne touche PAS le
    SCHÉMA de `lecons` : le schéma de leçon reste EXACTEMENT celui de la spec.

    RATTRAPE les leçons déjà présentes (N2) : après la création de la table, elle
    amorce le pointeur d'application depuis les leçons `locale` existantes (voir
    `_DDL_RATTRAPAGE_APPLIQUEE`). Sur un store NEUF, `lecons` est vide et le
    rattrapage n'insère rien ; sur un store v1 peuplé migré vers v2, il pose
    l'appliquée de chaque sujet SANS jamais écraser une leçon."""
    conn.execute(_DDL_APPLIQUEE)
    conn.execute(_DDL_RATTRAPAGE_APPLIQUEE)


#: Échelle de migrations : version CIBLE -> callable(conn). `version.py` les
#: applique dans l'ordre croissant. v1 pose le schéma de leçon ; v2 ajoute la
#: table de précédence (`T-00000639`) — une montée idempotente, jouable deux fois
#: sans effet de bord, plutôt qu'un DDL rejoué à la main. La v3 s'ajoutera ici
#: sans toucher `version.py`.
MIGRATIONS = {1: creer_schema, 2: creer_table_appliquee}
