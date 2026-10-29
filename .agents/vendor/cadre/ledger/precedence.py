"""LA PRÉCÉDENCE DES LEÇONS — décidée À L'ÉCRITURE, jamais à la lecture.

Phase 2 de T-012, étape D (point 6, `T-00000639`), bloquant B-C3 du plan LOT-2
phase 2. La spec (§5bis-B) : « Précédence : leçons embarquées dans la release <
leçons tirées du serveur < leçons locales de l'adoptant. Une mise à jour du kit
ou un pull n'écrase JAMAIS une leçon locale, et la provenance de chaque leçon
appliquée est traçable. À vérifier MAINTENANT, avant que le pull existe. »

POURQUOI À L'ÉCRITURE, ET C'EST LE CŒUR. Le jour où un `lessons pull` écrira dans
le même magasin, un UPSERT naïf par sujet écraserait la leçon locale EN SILENCE.
La règle mord donc au moment de l'écriture : une écriture de provenance
INFÉRIEURE sur un sujet déjà porté par une provenance SUPÉRIEURE ne devient pas
l'appliquée — mais elle est CONSERVÉE, présente, jamais perdue. Une écriture de
provenance supérieure (ou égale, la plus récente) devient l'appliquée.

RIEN N'EST ÉCRASÉ NI SUPPRIMÉ. Toutes les leçons de tous les niveaux coexistent
dans `lecons` ; la précédence ne fait que déplacer un POINTEUR — la table
auxiliaire `lecon_appliquee` (schéma v2, `schema.TABLE_APPLIQUEE`), qui nomme au
plus UNE leçon appliquée par `(tenant_id, project_id, cle_sujet)`. C'est un
pointeur et non une copie : la leçon appliquée reste lue dans `lecons`, sa
`provenance` incluse et traçable.

LA DÉCISION EST ISOLÉE (`doit_devenir_appliquee`) pour être le POINT D'INJECTION
du contrôle négatif : un « magasin qui ajoute sans règle » se fabrique en
remplaçant cette seule fonction, et le témoin de précédence rougit alors — ce qui
prouve que son assertion mesure la règle et non une tautologie.

Aucune E/S ni ouverture de connexion : ce module OPÈRE sur une connexion REÇUE
(ouverte par `store.py`), comme `schema.py` et `lessons.py` — le banc de
discipline `test_cadre_ledger_purete.py` le vérifie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cadre.ledger import schema

if TYPE_CHECKING:
    import sqlite3

__all__ = [
    "PRECEDENCE", "rang", "doit_devenir_appliquee", "appliquer_precedence",
    "ulid_applique", "lecon_appliquee", "gagnantes_partageables", "lecons_appliquees",
]

#: L'ORDRE de précédence : `embarquee < distante < locale`. L'INDICE dans ce
#: n-uplet EST le rang — un pull (distante) ne domine jamais une locale, une
#: release embarquée ne domine jamais un pull. Le jeu de valeurs est le MÊME que
#: `schema.PROVENANCES` (un CHECK SQLite refuse toute autre valeur à l'écriture) ;
#: seul l'ORDRE ajoute ici l'information de précédence.
PRECEDENCE = ("embarquee", "distante", "locale")


def rang(provenance: str) -> int:
    """Le rang de précédence d'une provenance (0 = le plus faible). `ValueError`
    sur une valeur hors énumération — un CHECK SQLite l'aurait déjà refusée à
    l'écriture, donc ce rang ne voit que des valeurs valides."""
    return PRECEDENCE.index(provenance)


def doit_devenir_appliquee(rang_nouvelle: int, rang_courant: int | None) -> bool:
    """LA DÉCISION DE PRÉCÉDENCE, isolée pour être le point d'injection du
    contrôle négatif.

    La nouvelle leçon devient l'appliquée si aucune ne l'est encore
    (`rang_courant is None`), ou si sa provenance DOMINE (`>=`) celle de
    l'appliquée courante. Le `>=` et non `>` est un choix ASSUMÉ : une leçon de
    MÊME provenance écrite plus tard remplace l'appliquée (la dernière locale
    prime sur une locale antérieure), tandis qu'une provenance STRICTEMENT
    inférieure — une embarquée arrivant sur une locale — ne franchit jamais le
    seuil.
    """
    return rang_courant is None or rang_nouvelle >= rang_courant


def ulid_applique(conn: "sqlite3.Connection", cle_sujet: str, *,
                  tenant_id: str, project_id: str) -> str | None:
    """L'ulid de la leçon actuellement appliquée pour ce sujet, ou `None`."""
    row = conn.execute(
        "SELECT ulid FROM " + schema.TABLE_APPLIQUEE + " WHERE tenant_id = ? "
        "AND project_id = ? AND cle_sujet = ?",
        (tenant_id, project_id, cle_sujet),
    ).fetchone()
    return row["ulid"] if row is not None else None


def _provenance_de(conn: "sqlite3.Connection", ulid: str) -> str:
    """La provenance RÉELLE de la ligne `ulid` (jamais la valeur qu'on croyait
    écrire : la dédup peut réutiliser une ligne d'une autre provenance)."""
    row = conn.execute(
        "SELECT provenance FROM " + schema.TABLE + " WHERE ulid = ?", (ulid,)
    ).fetchone()
    if row is None:
        raise KeyError("ulid absent de " + schema.TABLE + " : " + repr(ulid))
    return row["provenance"]


def appliquer_precedence(conn: "sqlite3.Connection", *, ulid: str, cle_sujet: str,
                         tenant_id: str, project_id: str) -> bool:
    """Décide, À L'ÉCRITURE, si la leçon `ulid` devient l'appliquée de son sujet.

    Ne SUPPRIME ni ne MODIFIE aucune leçon : toutes restent présentes dans
    `lecons`. Seul le POINTEUR d'application bouge. Rend `True` si `ulid` est (ou
    devient) l'appliquée du sujet, `False` si une provenance supérieure la garde.

    N'appelle PAS `conn.commit()` : la décision vit dans la transaction de
    l'écriture qui l'a déclenchée — elle est atomique avec l'insert de la leçon.
    """
    rang_nouvelle = rang(_provenance_de(conn, ulid))
    courant = ulid_applique(conn, cle_sujet, tenant_id=tenant_id, project_id=project_id)
    rang_courant = None if courant is None else rang(_provenance_de(conn, courant))
    if not doit_devenir_appliquee(rang_nouvelle, rang_courant):
        return False
    conn.execute(
        "INSERT INTO " + schema.TABLE_APPLIQUEE
        + " (tenant_id, project_id, cle_sujet, ulid) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(tenant_id, project_id, cle_sujet) DO UPDATE SET ulid = excluded.ulid",
        (tenant_id, project_id, cle_sujet, ulid),
    )
    return True


def lecon_appliquee(conn: "sqlite3.Connection", cle_sujet: str, *,
                    tenant_id: str, project_id: str) -> dict | None:
    """La leçon APPLIQUÉE pour ce sujet (provenance dominante), ou `None`.

    Rend un `dict` colonne→valeur, `provenance` incluse et LISIBLE — c'est
    l'exigence de traçabilité de la spec. La sélection LIT le pointeur posé à
    l'écriture ; elle ne recalcule pas la précédence à la lecture.
    """
    row = conn.execute(
        "SELECT l.* FROM " + schema.TABLE + " l JOIN " + schema.TABLE_APPLIQUEE
        + " a ON a.ulid = l.ulid WHERE a.tenant_id = ? AND a.project_id = ? "
        "AND a.cle_sujet = ?",
        (tenant_id, project_id, cle_sujet),
    ).fetchone()
    return dict(row) if row is not None else None


def gagnantes_partageables(lignes: list[dict]) -> list[dict]:
    """LA DÉCISION DE PRÉCÉDENCE ENTRE PORTÉES PARTAGEABLES, isolée pour être le
    POINT D'INJECTION du contrôle négatif — exactement comme `doit_devenir_appliquee`.

    Reçoit les lignes candidates d'un MÊME sujet (portée `partageable`/`generale`,
    tous tenants confondus) et rend celles qui s'appliquent. Décision PURE, aucun
    SQL : elle ne voit que les `dict` qu'on lui passe.

    - une ligne `statut_partage == 'revoque'` ne s'applique JAMAIS et ne masque pas
      les autres (elle est écartée AVANT le calcul du rang) ;
    - la précédence se joue sur la SEULE provenance (`rang`), tous tenants
      confondus (`spec:283`) ; toutes les lignes au rang MAXIMAL sont rendues, les
      ex æquo CONSERVÉS (`spec:283`, « deux partageables de même provenance, même
      sujet : LES DEUX S'APPLIQUENT ») ;
    - l'ordre de sortie est DÉTERMINISTE, `(portee, tenant_id, project_id, ulid)`.

    L'échelle de rang N'EST PAS recopiée en `CASE` SQL : un `CASE` dupliquerait
    `PRECEDENCE` et rendrait le contrôle négatif inerte. Cette fonction EST le seul
    lieu de la règle, donc la remplacer par un patch la fait mordre.
    """
    en_lice = [ligne for ligne in lignes if ligne["statut_partage"] != "revoque"]
    if not en_lice:
        return []
    rang_max = max(rang(ligne["provenance"]) for ligne in en_lice)
    gagnantes = [ligne for ligne in en_lice if rang(ligne["provenance"]) == rang_max]
    return sorted(
        gagnantes,
        key=lambda ligne: (ligne["portee"], ligne["tenant_id"],
                           ligne["project_id"], ligne["ulid"]),
    )


def lecons_appliquees(conn: "sqlite3.Connection", cle_sujet: str, *,
                      tenant_id: str, project_id: str) -> list[dict]:
    """LES leçons appliquées pour ce sujet : la locale de CE tenant (via le
    pointeur, 0 ou 1) PLUS toutes les partageables gagnantes, tous tenants
    confondus, RÉSOLUES EN LECTURE.

    Ceci INVERSE `lecon_appliquee`, qui n'admet qu'UNE leçon par (tenant, projet,
    sujet) et dont seule la locale concourt (`spec:291`) : ici les deux portées
    COEXISTENT sans précédence entre elles (`spec:283`, `spec:293-295`, « les deux
    s'appliquent »), et la résolution des partageables se fait en LECTURE, non par
    la clé primaire — borne de `S-00001614`/`S-00001615`.

    TROIS gestes :
      1. la locale de CE tenant via `lecon_appliquee` (pointeur inchangé), 0 ou 1 ;
      2. les partageables du sujet FILTRÉES PAR STATUT ET TENANT (décision pilote
         `S-00001665`, option A) : une partageable de MON tenant s'applique quel que
         soit son statut (mon propre brouillon `en_attente_de_revue` me sert) ;
         celle d'un AUTRE tenant ne s'applique QUE si elle porte l'acte de revue
         (`revue_faite` ou `partage`) — un brouillon non revu d'autrui ne s'applique
         plus et ne masque plus la leçon revue. Les candidates ainsi retenues sont
         départagées par `gagnantes_partageables` (aucun classement en SQL) ;
      3. ÉCART de tout `ulid` déjà rendu par (1) — sans lui, un pointeur qui nomme
         une partageable (possible : la PK à 3 colonnes ne porte pas `portee` et la
         FK `schema.py:202` est permissive) la rendrait DEUX fois. Les deux membres
         ne sont disjoints aujourd'hui que par accident (`lessons.py:282-285` ne
         pointe que la locale) ; l'écart rend la disjonction structurelle.

    Rend (1) puis (2) écrémé. `'generale'` est inclus dans le `IN` : la clause
    « générale = partageable » honorée en COMPORTEMENT, sans DDL.
    """
    locale = lecon_appliquee(conn, cle_sujet, tenant_id=tenant_id, project_id=project_id)
    brutes = conn.execute(
        "SELECT l.* FROM " + schema.TABLE + " l WHERE l.cle_sujet = ? "
        "AND l.portee IN ('partageable', 'generale') "
        "AND ((l.tenant_id = ? AND l.project_id = ?) "
        "     OR l.statut_partage IN ('revue_faite', 'partage'))",
        (cle_sujet, tenant_id, project_id),
    ).fetchall()
    partageables = gagnantes_partageables([dict(ligne) for ligne in brutes])
    if locale is not None:
        deja = locale["ulid"]
        partageables = [ligne for ligne in partageables if ligne["ulid"] != deja]
        return [locale] + partageables
    return partageables
