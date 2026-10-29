"""LA PROMOTION HUMAINE D'UNE FORME GÉNÉRALISÉE — module DÉCISION, sans E/S.

Phase 2 de T-012, `T-00000647`. « promotion humaine revue » (décision pilote du
2026-09-17) : la promotion d'une forme généralisée vers l'état d'équipe est un
GESTE HUMAIN explicite et TRACÉ, jamais un effet de bord automatique. On promeut
TOUJOURS la forme généralisée, jamais la leçon locale telle quelle.

Ce module OPÈRE sur une connexion REÇUE (ouverte par la CLI, hors du service
`ledger/`) : aucune ouverture de connexion, aucun accès disque, aucune horloge —
le banc de discipline `test_cadre_ledger_purete.py` le vérifie. L'horodatage de
revue est un PARAMÈTRE REQUIS : une horloge dans un module de décision est la
même faute de classe que l'E/S (`spec:60`, « couture d'E/S »), et c'est aussi ce
qui rend un octet-à-octet figé possible côté banc.

CE MODULE N'ÉCRIT PAS DE FICHIER et NE COMMITE PAS : la transaction appartient à
l'appelant, qui écrit le fichier JSON (source de vérité, `spec:260-262`) PUIS
commite. La promotion ne change ni provenance ni contenu, donc elle ne rejoue
aucune précédence.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cadre.ledger import schema

if TYPE_CHECKING:
    import sqlite3

__all__ = ["promouvoir"]


def promouvoir(conn: "sqlite3.Connection", ulid: str, *, revue_par: str,
               horodatage: str) -> tuple[dict, bytes]:
    """Transitionne la forme généralisée `ulid` de `en_attente_de_revue` vers
    `revue_faite`, en enregistrant l'acte de revue (`revue_par`, `revue_horodatage`).

    REFUSE par `ValueError` — message nommant le champ fautif — toute ligne qui
    n'est pas EXACTEMENT `portee='partageable'` ET `provenance='locale'` ET
    `statut_partage='en_attente_de_revue'` (`spec:257`). Cette précondition à trois
    membres, et le fait que les deux champs de revue sont posés ENSEMBLE, sont
    précisément ce qui rend aucun `CHECK` du schéma atteignable depuis ce geste :
    `schema.py:142` (forçage `prive` dès `portee='locale'`) est écarté par la
    précondition ; `schema.py:153-154` (revue_par ET revue_horodatage) est
    satisfait par le couple ; `schema.py:157-158` ne concerne que
    `statut_partage='partage'`, jamais écrit ici (niveaux 1 et 3 hors de ce geste,
    `spec:264-268`).

    REFUSE AUSSI par `ValueError` un `revue_par` ou un `horodatage` VIDE (un acte
    de revue nomme son relecteur et se date — le `CHECK` schema.py:153-154 ne voit
    que `NOT NULL`, `''` le satisferait), et une PROMOTION CONCURRENTE : l'`UPDATE`
    est CONDITIONNÉ sur `statut_partage = 'en_attente_de_revue'` et un `rowcount != 1`
    lève — si un autre geste a promu `ulid` entre la lecture de précondition et
    l'écriture, rien n'est écrasé (perte de mise à jour évitée sans verrou
    d'écriture à tenir).

    Rend le `dict` relu APRÈS l'`UPDATE` et ses octets canoniques (clés triées,
    indentation deux espaces, saut de ligne final) — la forme du fichier JSON par
    forme promue.
    """
    row = conn.execute(
        "SELECT * FROM " + schema.TABLE + " WHERE ulid = ?", (ulid,)
    ).fetchone()
    if row is None:
        raise ValueError("ulid absent du magasin : " + repr(ulid))
    ligne = dict(row)
    if ligne["portee"] != "partageable":
        raise ValueError(
            "portee=" + repr(ligne["portee"]) + " : seule une forme partageable se "
            "promeut, jamais une leçon locale")
    if ligne["provenance"] != "locale":
        raise ValueError(
            "provenance=" + repr(ligne["provenance"]) + " : la promotion humaine ne "
            "porte que sur une forme de provenance locale")
    if ligne["statut_partage"] != "en_attente_de_revue":
        raise ValueError(
            "statut_partage=" + repr(ligne["statut_partage"]) + " : seule une forme "
            "en attente de revue se promeut (déjà promue, ou jamais mise en attente)")
    if revue_par is None or not revue_par.strip():
        raise ValueError(
            "revue_par vide : « aucune leçon ne sort sans acte de revue ENREGISTRÉ » "
            "(spec §5bis-B) — le relecteur doit être NOMMÉ")
    if horodatage is None or not horodatage.strip():
        raise ValueError(
            "horodatage vide : « aucune leçon ne sort sans acte de revue ENREGISTRÉ » "
            "(spec §5bis-B) — l'acte de revue doit être DATÉ")
    # UPDATE CONDITIONNÉ sur `en_attente_de_revue` : la précondition ci-dessus a été
    # évaluée sur une LECTURE qui peut être périmée (sqlite3 différé ne verrouille
    # pas au SELECT). Si un AUTRE geste a promu `ulid` entre la lecture et ici,
    # `rowcount` vaut 0 et on lève — rien n'est écrasé, sans verrou d'écriture à
    # tenir et sans ordre de verrou à respecter (A-C3).
    curseur = conn.execute(
        "UPDATE " + schema.TABLE + " SET statut_partage = 'revue_faite', "
        "revue_par = ?, revue_horodatage = ? "
        "WHERE ulid = ? AND statut_partage = 'en_attente_de_revue'",
        (revue_par, horodatage, ulid),
    )
    if curseur.rowcount != 1:
        raise ValueError(
            "promotion CONCURRENTE : " + repr(ulid) + " a été promue par un autre "
            "geste entre la lecture et l'écriture — rien n'a été modifié")
    relue = dict(conn.execute(
        "SELECT * FROM " + schema.TABLE + " WHERE ulid = ?", (ulid,)
    ).fetchone())
    octets = json.dumps(relue, ensure_ascii=False, sort_keys=True,
                        indent=2).encode("utf-8") + b"\n"
    return relue, octets
