"""ÉCRITURE ET LECTURE DES LEÇONS — la dualité locale / forme généralisée.

Phase 2 de T-012. Opère sur une connexion REÇUE (ouverte par `store.py`) : aucun
accès disque direct, aucune ouverture de connexion — ce que le banc de discipline
`test_cadre_ledger_purete.py` vérifie.

GÉNÉRALISATION À LA SOURCE : `ecrire_lecon` avec une `forme_generalisee` produit
DEUX enregistrements distincts — la leçon LOCALE (`portee=locale`,
`statut_partage=prive`, jamais partageable par construction) et sa forme
GÉNÉRALISÉE (`portee=partageable`, `statut_partage=en_attente_de_revue`, sans
origine projet), liées par `ref_forme_generalisee` et JAMAIS fusionnées. Ce qui
sort n'est pas une version épurée : c'est un objet distinct.

Ni mode distant, ni API de leçons, ni client réseau : on prépare la couture, on
ne coud pas.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cadre.ledger import ids, precedence, redaction, schema

if TYPE_CHECKING:
    import sqlite3

__all__ = ["Lecon", "inserer", "ecrire_lecon", "lire_lecon", "VERSION_SCHEMA_LECON"]

#: Version du FORMAT d'un enregistrement de leçon, versionnée INDÉPENDAMMENT du
#: noyau et de la version du store (spec).
VERSION_SCHEMA_LECON = 1

_INSERT = (
    "INSERT INTO " + schema.TABLE + " (" + ", ".join(schema.COLONNES) + ") "
    "VALUES (" + ", ".join("?" for _ in schema.COLONNES) + ")"
)
_SELECT_PAR_ULID = "SELECT * FROM " + schema.TABLE + " WHERE ulid = ?"


@dataclass
class Lecon:
    """Un enregistrement de leçon. L'INSERT lit les valeurs par NOM (`getattr`
    sur `schema.COLONNES`), pas par position — l'ordre des champs ici n'a donc
    qu'à porter les OBLIGATOIRES avant ceux qui ont un défaut."""

    ulid: str
    hash_contenu: str
    contenu: str
    cle_sujet: str
    portee: str
    provenance: str
    statut_partage: str
    statut_sync: str
    version_schema_lecon: int
    tenant_id: str
    project_id: str
    horodatage: str
    type: str | None = None
    origine_projet: str | None = None
    origine_hote: str | None = None
    origine_agent: str | None = None
    origine_run: str | None = None
    ref_forme_generalisee: str | None = None
    reference_accord: str | None = None
    identite_declaree: str | None = None
    validateur_1: str | None = None
    validateur_2: str | None = None
    revue_par: str | None = None
    revue_horodatage: str | None = None


def _hash(contenu: str) -> str:
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def inserer(conn: "sqlite3.Connection", lecon: Lecon) -> None:
    """Insère UN enregistrement. Bas niveau : la contrainte d'inégalité des
    validateurs et les CHECK d'énumération sont appliqués par SQLite, donc un
    `Lecon` invalide lève `sqlite3.IntegrityError`."""
    conn.execute(_INSERT, [getattr(lecon, c) for c in schema.COLONNES])


def _ulid_existant(
    conn: "sqlite3.Connection", tenant_id: str, project_id: str, portee: str,
    hash_contenu: str, *, cle_sujet: str | None = None,
    provenance: str | None = None,
) -> str | None:
    """L'ulid d'une leçon déjà présente pour sa clé de dédup, ou `None`.

    DEUX clés de dédup DISJOINTES depuis le correctif binôme PORTE 3 (B1), qui
    reflètent EXACTEMENT les deux index partiels de `schema._DDL_INDEX` :

      * portée LOCALE — clé `(tenant, projet, cle_sujet, provenance, hash)`, index
        `ux_lecons_dedup_locale`. `cle_sujet` ET `provenance` FONT PARTIE de la
        clé : sans eux, une écriture locale du même contenu qu'une embarquée
        réutilisait la ligne embarquée et la précédence relisait la MAUVAISE
        provenance (une locale « appliquée » ressortait embarquée).
      * portée NON LOCALE (partageable) — clé `(tenant, projet, portée, hash)`,
        index `ux_lecons_dedup`. La forme généralisée déduplique par contenu, la
        provenance indifférente : elle ne concourt PAS à la précédence.

    Une seconde écriture de MÊME clé RÉUTILISE la ligne au lieu d'en insérer une
    seconde, qui violerait l'index — c'est ce qui rend le push rejouable (spec
    « dédup »)."""
    if portee == "locale":
        row = conn.execute(
            "SELECT ulid FROM " + schema.TABLE + " WHERE tenant_id = ? AND "
            "project_id = ? AND portee = 'locale' AND cle_sujet = ? AND "
            "provenance = ? AND hash_contenu = ?",
            (tenant_id, project_id, cle_sujet, provenance, hash_contenu),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT ulid FROM " + schema.TABLE + " WHERE tenant_id = ? AND "
            "project_id = ? AND portee = ? AND hash_contenu = ?",
            (tenant_id, project_id, portee, hash_contenu),
        ).fetchone()
    return row["ulid"] if row is not None else None


def ecrire_lecon(
    conn: "sqlite3.Connection",
    *,
    contenu: str,
    cle_sujet: str,
    tenant_id: str,
    project_id: str,
    type: str | None = None,
    provenance: str = "locale",
    origine_projet: str | None = None,
    origine_hote: str | None = None,
    origine_agent: str | None = None,
    origine_run: str | None = None,
    identite_declaree: str | None = None,
    reference_accord: str | None = None,
    horodatage: str | None = None,
    forme_generalisee: str | None = None,
) -> tuple[str, str | None]:
    """Écrit la leçon LOCALE et, si `forme_generalisee` est fournie, sa forme
    GÉNÉRALISÉE — deux enregistrements distincts liés par `ref_forme_generalisee`,
    chacun stockant SON texte en clair (`contenu`).

    Rend `(ulid_local, ulid_generalisee_ou_None)`. La forme généralisée est
    insérée AVANT la locale, pour que le lien (clé étrangère) référence une ligne
    existante.

    TRANSACTIONNEL : les deux INSERT vivent dans UN bloc. Toute exception (un
    CHECK violé, un `contenu` `NULL`, une clé étrangère cassée) déclenche un
    `rollback` — jamais une locale sans sa généralisée, ni l'inverse — puis
    est relevée. Le `commit` ne vient qu'à la fin.

    DÉDUP : DEUX clés disjointes par portée (correctif binôme PORTE 3, B1). Une
    forme généralisée (partageable) déduplique sur `(tenant, projet, portée,
    hash)` — deux écritures de la même leçon générique partagent UNE ligne. Une
    locale déduplique sur `(tenant, projet, cle_sujet, provenance, hash)` : une
    locale en double de MÊME sujet ET MÊME provenance réutilise (elle ne refuse
    pas), mais une écriture de provenance DIFFÉRENTE est une ligne DISTINCTE, sans
    quoi la précédence relirait la provenance de la ligne réutilisée.

    RÉDACTION DES SECRETS À L'ÉCRITURE (`T-00000641`, invariant « aucun secret au
    ledger »). Les DEUX champs texte libre — `contenu` (corps de la locale) et
    `forme_generalisee` (corps de la partageable) — sont rédigés ICI, en tête,
    AVANT tout hachage et tout insert : un secret reconnu (`redaction.rediger`)
    est remplacé par un marqueur, il n'atteint jamais le magasin.

    MÉTADONNÉES : REFUS plutôt que rédaction (correctif binôme PORTE 3, C6). Les
    autres paramètres ne sont PAS du texte libre — `cle_sujet` est une CLÉ (dédup,
    précédence, index : la rédiger FRACTURERAIT l'identité du sujet), `provenance`
    est un CHECK fermé, `reference_accord`/`identite_declaree`/`type`/`origine_*`
    sont des métadonnées structurées. Les rédiger n'a pas de sens ; mais un secret
    y ATTEINDRAIT le magasin (elles ne passent pas par `rediger`). On les CONTRÔLE
    donc en tête : un secret reconnu dans l'une d'elles lève `ValueError` NOMMANT
    le champ, AVANT le moindre insert — rien n'atteint le store. Aucun autre chemin
    d'écriture de texte libre n'existe dans le service (`inserer` est bas niveau et
    reçoit un `Lecon` déjà construit ; `stores.py` n'écrit aucun texte de leçon).

    LE HASH EST CALCULÉ SUR LE TEXTE RÉDIGÉ, et c'est la seule forme correcte.
    `hash_contenu` est l'empreinte du `contenu` RÉELLEMENT stocké ; puisque c'est
    le texte rédigé qui est stocké, l'empreinte doit porter sur lui — hacher le
    texte brut stockerait une empreinte qui ne correspond pas à son propre contenu
    (l'invariant `hash_contenu == sha256(contenu)` casserait), ferait dépendre le
    hash du secret (une valeur dérivée du secret entrerait au magasin), et casserait
    la dédup, qui doit réunir deux écritures du même secret sur UNE ligne — ce
    qu'elle fait naturellement, les deux se rédigeant vers le même marqueur.
    """
    # C6 : les champs de métadonnée NE sont PAS rédigés (ce sont des clés ou des
    # énumérations) — mais un secret reconnu dedans est REFUSÉ, jamais écrit brut.
    # Contrôlé AVANT toute écriture, donc rien n'atteint le store en cas de refus.
    for _nom, _valeur in (
        ("cle_sujet", cle_sujet), ("reference_accord", reference_accord),
        ("identite_declaree", identite_declaree), ("type", type),
        ("origine_projet", origine_projet), ("origine_hote", origine_hote),
        ("origine_agent", origine_agent), ("origine_run", origine_run),
    ):
        if redaction.contient_secret(_valeur):
            raise ValueError(
                "secret reconnu dans le champ de métadonnée « " + _nom + " » : ce "
                "champ n'est PAS rédigé (clé ou énumération, pas du texte libre) et "
                "un secret y atteindrait le magasin — écriture REFUSÉE")
    contenu = redaction.rediger(contenu)
    forme_generalisee = redaction.rediger(forme_generalisee)
    ts = horodatage if horodatage is not None else _maintenant()
    ulid_gen: str | None = None
    try:
        # N3 (course) : verrou d'écriture pris EN TÊTE de la transaction, AVANT la
        # lecture read-modify-write du pointeur de précédence. Sans lui, deux
        # écritures concurrentes liraient toutes deux l'appliquée courante puis
        # écriraient, et la dernière gagnerait quel que soit son rang. `BEGIN
        # IMMEDIATE` sérialise : la seconde écrivaine attend le commit de la
        # première puis relit le pointeur à jour. Gardé par `in_transaction` pour
        # ne pas rouvrir une transaction qu'un appelant composerait déjà.
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        if forme_generalisee is not None:
            h_gen = _hash(forme_generalisee)
            ulid_gen = _ulid_existant(conn, tenant_id, project_id, "partageable", h_gen)
            if ulid_gen is None:
                ulid_gen = ids.nouvel_ulid()
                inserer(conn, Lecon(
                    ulid=ulid_gen,
                    hash_contenu=h_gen,
                    contenu=forme_generalisee,
                    cle_sujet=cle_sujet,
                    portee="partageable",
                    provenance=provenance,
                    statut_partage="en_attente_de_revue",
                    statut_sync="local",
                    version_schema_lecon=VERSION_SCHEMA_LECON,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    horodatage=ts,
                    type=type,
                    # AUCUN contexte projet sur la forme généralisée.
                    origine_projet=None,
                    origine_hote=origine_hote,
                    origine_agent=origine_agent,
                    origine_run=origine_run,
                    ref_forme_generalisee=None,
                    reference_accord=reference_accord,
                    identite_declaree=identite_declaree,
                ))
        h_loc = _hash(contenu)
        ulid_local = _ulid_existant(conn, tenant_id, project_id, "locale", h_loc,
                                    cle_sujet=cle_sujet, provenance=provenance)
        if ulid_local is None:
            ulid_local = ids.nouvel_ulid()
            inserer(conn, Lecon(
                ulid=ulid_local,
                hash_contenu=h_loc,
                contenu=contenu,
                cle_sujet=cle_sujet,
                portee="locale",
                provenance=provenance,
                statut_partage="prive",
                statut_sync="local",
                version_schema_lecon=VERSION_SCHEMA_LECON,
                tenant_id=tenant_id,
                project_id=project_id,
                horodatage=ts,
                type=type,
                origine_projet=origine_projet,
                origine_hote=origine_hote,
                origine_agent=origine_agent,
                origine_run=origine_run,
                ref_forme_generalisee=ulid_gen,
                reference_accord=reference_accord,
                identite_declaree=identite_declaree,
            ))
        # PRÉCÉDENCE À L'ÉCRITURE : la leçon PRIMAIRE (locale/contextualisée) de
        # ce sujet devient-elle l'APPLIQUÉE ? Décision prise MAINTENANT, dans la
        # même transaction que l'insert — jamais reportée à la lecture. Rien
        # n'est écrasé : seul le pointeur d'application bouge (voir
        # `precedence.py`). La forme généralisée (partageable) ne concourt PAS —
        # elle n'est pas la leçon appliquée localement.
        precedence.appliquer_precedence(
            conn, ulid=ulid_local, cle_sujet=cle_sujet,
            tenant_id=tenant_id, project_id=project_id,
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return ulid_local, ulid_gen


def lire_lecon(conn: "sqlite3.Connection", ulid: str) -> dict | None:
    """La leçon d'identifiant `ulid`, ou `None`. Rend un `dict` colonne→valeur."""
    row = conn.execute(_SELECT_PAR_ULID, (ulid,)).fetchone()
    return dict(row) if row is not None else None
