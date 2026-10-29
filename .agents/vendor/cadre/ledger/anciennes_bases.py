"""Lecture d'une ANCIENNE base V3 posée DANS le dépôt, sur une connexion REÇUE.

T-01M534ZNXKKP91XZRV5M5WBAYX (commande setup), étape 6. Avant T-00000650, la
base V3 vivait sous la racine du dépôt, et certains adoptants l'ont SUIVIE par
git. Aucun code ne la lit plus : ses `spec_requirements` sont invisibles. Ce
module en lit les lignes pour que le setup puisse (1) rejouer `sync-spec` sur
les fichiers qu'elles citent et (2) chiffrer ce que le rejeu ne rend pas.

CE QUE CE MODULE NE FAIT PAS, PAR CONSTRUCTION (réserve C14 du plan-critic) :
  * il n'OUVRE rien. `lire_specs(conn)` reçoit une connexion déjà ouverte ;
    c'est l'appelant qui ouvre par `store.connect(<chemin absolu>,
    lecture_seule=True)` (`mode=ro&immutable=1`), après avoir jugé la base et
    son `-wal` sur disque. `connect` reste l'apanage de `store.py`
    (`test_cadre_ledger_purete`), et aucune E/S de chemin n'a lieu ici ;
  * il n'écrit rien : une seule requête de lecture, plus la lecture du
    catalogue pour distinguer une table ABSENTE (`None`) d'une table VIDE
    (`[]`) — trois états, jamais deux ;
  * il ne répare rien : la base n'est jamais copiée, réécrite ni effacée.

BORNE, celle de `immutable=1` (stores.py, `_sonder`) : les trames d'un `-wal`
non rabattu sont INVISIBLES à cette lecture. L'appelant doit donc refuser de
conclure (`dégradé`) quand un `-wal` non vide est à côté de la base. Un `-wal`
déjà rabattu mais non vide donne alors un `dégradé` par excès : la règle se
ferme du bon côté, et c'est une borne dite, pas un défaut corrigé (C17).
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

__all__ = ["LigneSpec", "Bilan", "lire_specs", "empreinte", "normaliser_chemin",
           "chemins", "bilan"]

_TABLE = "spec_requirements"
_EXISTE = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
_LIGNES = ("SELECT file_path, req_id, version, content_markdown "
           "FROM spec_requirements")


@dataclass(frozen=True)
class LigneSpec:
    """Une ligne de `spec_requirements` : le chemin TEL QU'ÉCRIT dans la base
    (séparateur d'origine), la section, sa version et l'empreinte sha256 de son
    texte."""

    file_path: str
    req_id: str
    version: int
    empreinte: str


@dataclass(frozen=True)
class Bilan:
    """Ce que le rejeu rend et ne rend pas, clé `(chemin normalisé, req_id)`,
    version la plus haute de chaque côté.

    `lignes` : lignes de l'ancienne base ; `cles` : clés distinctes dont le
    chemin reste dans le dépôt ; `identiques` / `changees` : clés retrouvées
    après rejeu, texte égal ou non ; `sans_source` : clés absentes après
    rejeu ; `versions_perdues` : lignes qui ne sont pas la dernière version de
    leur clé (l'historique n'est jamais rejoué) ; `hors_depot` : lignes dont le
    chemin est absolu, vide ou traverse `..`, jamais synchronisées."""

    lignes: int
    cles: int
    identiques: int
    changees: int
    sans_source: int
    versions_perdues: int
    hors_depot: int

    @property
    def retrouvees(self) -> int:
        return self.identiques + self.changees


def empreinte(texte: str) -> str:
    """sha256 hexadécimal du texte, encodé UTF-8."""
    return hashlib.sha256(texte.encode("utf-8", "surrogatepass")).hexdigest()


def lire_specs(conn: sqlite3.Connection) -> list[LigneSpec] | None:
    """Les lignes de `spec_requirements` sur `conn`, ouverte par l'appelant.

    `None` si la table n'existe pas, `[]` si elle est vide. Une
    `sqlite3.Error` (base illisible, non SQLite) remonte telle quelle :
    l'appelant la dit `dégradé`. Le tuple de chaque ligne est lu par indice,
    donc indifférent à la `row_factory` de la connexion."""
    if conn.execute(_EXISTE, (_TABLE,)).fetchone() is None:
        return None
    lignes = []
    for ligne in conn.execute(_LIGNES).fetchall():
        lignes.append(LigneSpec(file_path=str(ligne[0]), req_id=str(ligne[1]),
                                version=int(ligne[2]),
                                empreinte=empreinte(str(ligne[3]))))
    return lignes


def normaliser_chemin(brut: str) -> str | None:
    """Le chemin RELATIF, séparé par `/`, d'un `file_path` lu dans une base ;
    `None` s'il ne désigne pas un fichier SOUS la racine : vide, absolu
    (`/…`, lecteur `X:`), ou traversant `..`. C'est une DONNÉE d'une base
    suivie : rien n'en est déduit sans ce filtre. `./` en tête est retiré.
    (Pas de `str.replace` ici : le filet de pureté du ledger le prend pour
    l'E/S `Path.replace`.)"""
    texte = "/".join(brut.split("\\"))
    if not texte or texte.startswith("/") or (len(texte) > 1 and texte[1] == ":"):
        return None
    parties = [p for p in texte.split("/") if p not in ("", ".")]
    if not parties or ".." in parties:
        return None
    return "/".join(parties)


def chemins(lignes: list[LigneSpec]) -> list[str]:
    """Les chemins normalisés, distincts et triés, que citent `lignes` ; les
    chemins refusés par `normaliser_chemin` n'y sont pas."""
    vus = {normaliser_chemin(x.file_path) for x in lignes}
    return sorted(c for c in vus if c is not None)


def _derniere_version(lignes: list[LigneSpec]) -> dict[tuple[str, str], LigneSpec]:
    dernieres: dict[tuple[str, str], LigneSpec] = {}
    for x in lignes:
        chemin = normaliser_chemin(x.file_path)
        if chemin is None:
            continue
        cle = (chemin, x.req_id)
        if cle not in dernieres or x.version > dernieres[cle].version:
            dernieres[cle] = x
    return dernieres


def bilan(anciennes: list[LigneSpec], nouvelles: list[LigneSpec]) -> Bilan:
    """Compare l'ancienne base à la base du poste APRÈS rejeu (voir `Bilan`)."""
    avant = _derniere_version(anciennes)
    apres = _derniere_version(nouvelles)
    hors_depot = sum(1 for x in anciennes if normaliser_chemin(x.file_path) is None)
    identiques = changees = sans_source = 0
    for cle, ligne in avant.items():
        trouvee = apres.get(cle)
        if trouvee is None:
            sans_source += 1
        elif trouvee.empreinte == ligne.empreinte:
            identiques += 1
        else:
            changees += 1
    versions_perdues = len(anciennes) - hors_depot - len(avant)
    return Bilan(lignes=len(anciennes), cles=len(avant), identiques=identiques,
                 changees=changees, sans_source=sans_source,
                 versions_perdues=versions_perdues, hors_depot=hors_depot)
