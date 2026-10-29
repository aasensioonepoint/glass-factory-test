#!/usr/bin/env python3
"""etat.db — la base SQLite DÉRIVÉE des deux journaux d'équipe (lot C de T-01M51Q7GJ1B6315SFKNDAAE2P0).

UN CACHE SANS AUTORITÉ. Les journaux suivis par git restent la seule vérité ; cette base n'en est qu'une
projection reconstructible, que les routes paginées du dashboard (lot D) lisent quand elle est À JOUR et
abandonnent pour la lecture directe dans tous les autres cas. Elle n'est pas une surface de mémoire : aucune
ligne de DDL ci-dessous ne nomme la boucle d'apprentissage (motif R-B1), et le registre de ces surfaces n'est
pas amendé.

OÙ ELLE VIT. Sous `cadre.paths.state_project(racine)` — l'état MACHINE, hors dépôt (cible « état machine hors
dépôt », « aucun fichier SQLite du kit ») — ou au chemin nommé par `AGENTS_ETAT_DB` (les bancs). La couture
`cadre.paths` suit le patron S-00001655 : (1) le paquet installé, (2) À DÉFAUT `paths.py` du clone
(`.agents/vendor/cadre`, sinon `src/cadre` : résolveur `vendor_paths.py`), chargé PAR CHEMIN (stdlib seule). Les deux absents, ou une racine résolue qui n'est pas la racine demandée
(`$CADRE_PROJECT_ROOT` d'un autre projet, `.agents/` dans un sous-dossier d'un dépôt git) : `chemin_base` rend
None, `rafraichir` rend chaque source `degraded` SANS créer de base, et `lire` rend None — les routes lisent
alors les journaux directement. Le dossier créé l'est en 0o700, la base en 0o600 (ses `-wal`/`-shm` héritent de
ses droits, et sont resserrés à chaque ouverture de l'écrivain).

UN FICHIER QUI N'EST PAS LE NÔTRE N'EST JAMAIS MODIFIÉ NI SUPPRIMÉ (avis sécurité S-01M53CAX4W). Est NÔTRE une
base SQLite dont la table `meta` porte la ligne `schema`. Au chemin forcé (`AGENTS_ETAT_DB`), seule une base
absente (créée) ou au schéma '1' est acceptée — tout autre fichier existant est REFUSÉ, intact. Au chemin par
défaut s'y ajoutent un fichier vide ou une base SQLite sans aucun objet (crash de la toute première création),
initialisés, et une base NÔTRE d'un autre schéma, refaite (ses seules tables). Une base corrompue, un fichier qui
n'est pas SQLite, une base SQLite d'autrui : refusés aux deux chemins, `degraded`, jamais supprimés — le remède
(supprimer le fichier à la main) est nommé dans la cause.

UN SEUL ÉCRIVAIN : le fil `Boucle` que `dashboard_daemon.run_daemon` démarre (et les bancs). Aucun handler
HTTP n'écrit. Aucun état mutable de niveau module : deux chargements de ce fichier dans un processus (le démon,
puis `dashboard.py` pour les routes) ne partagent ni ne se disputent rien.

L'ORDRE D'ÉCRITURE, ET LA REPRISE APRÈS CRASH (cible « ordre d'écriture texte → projection »).
  1. Le relevé de chaque source est pris EN PREMIER (`empreinte_sources`) : `lstat` — type et droits, inode,
     taille, mtime, ctime — de chaque fichier de la recette de `dashboard_readers_base` (ses constantes, jamais
     un nom de magasin écrit ici — cliquet C3), et de CHAQUE nom de ses dossiers, quel qu'il soit : le
     propriétaire refuse un nom qu'il ne reconnaît pas (un `.json.orig`, un sous-dossier), donc l'empreinte les
     voit tous ; un `chmod` qui rend une entrée illisible bouge le ctime et le mode (réserve C1).
  2. Seule une source dont l'empreinte a bougé est rechargée par son PROPRIÉTAIRE (`specs.load`,
     `ledger.load`) ; un tick sans changement ne charge rien — une source `degraded` n'est donc relue qu'au
     prochain changement de son empreinte (d'ici là, `lire` rend None et les routes lisent en direct). Au-delà
     de `_TAILLE_MAX` octets relevés, la source est `degraded` SANS être chargée ; au-delà de `_ENTREES_MAX`
     entrées chargées, aussi. Un lien symbolique ou un fichier non régulier dans un magasin : `degraded` SANS
     chargement, les liens y sont REFUSÉS (`_releve`).
  3. Le chargement, le calcul des lignes ET leur écriture se font SOUS LE VERROU DE CONSTRUCTION DU SNAPSHOT
     (`MemoCorps.verrou`, passé par le démon) : jamais deux chargements d'un journal en même temps dans le
     démon (réserve C2, M5). Les lignes passent en FLUX du journal chargé à `executemany` : seule la ligne qui
     change est construite, aucune liste du store entier n'est bâtie à côté de lui.
  4. Le diff (id, sha, rang) d'une source est écrit en UNE transaction avec sa ligne `sources`. Un crash au
     milieu laisse l'ancienne transaction en place : l'empreinte stockée est l'ancienne, `lire` rend None, et
     le tick suivant reprend. Un journal modifié PENDANT le chargement laisse une empreinte stockée plus vieille
     que le disque : même chose, rien de périmé n'est jamais servi pour à jour.

SOURCE ILLISIBLE (réserve C1). Sa ligne `sources` passe `degraded` avec sa raison, ses lignes restent INTACTES
— et `lire` rend None dès qu'UNE source est `degraded` : la base ne sert jamais les lignes d'avant là où la
lecture directe n'en sert aucune.

`lire` ne lève jamais (réserve C8) : toute exception (connexion, lecture de `meta` ou de `sources`) est écrite
au journal stderr du démon (`logging`, gestionnaire de dernier recours) et rend None.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import math
import os
import re
import sqlite3
import stat
import sys
import threading
import unicodedata
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
_LOG = logging.getLogger(__name__)


def _load_sibling(name: str, filename: str) -> Any:
    """Même contrat d'import par chemin explicite que `dashboard.py` : jamais `sys.path[0]`."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise ImportError(f"{filename} introuvable sous {HERE}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# Les propriétaires des journaux, la recette d'empreinte et l'encodeur du corps — chargés sous des noms propres
# à ce module : aucun n'est partagé avec une autre copie, aucun n'est muté ici.
_base = _load_sibling("_etat_readers_base", "dashboard_readers_base.py")
_specs = _load_sibling("_etat_specs", "specs.py")
_ledger = _load_sibling("_etat_ledger", "ledger.py")
_transport = _load_sibling("_etat_transport", "dashboard_transport.py")

SCHEMA = "1"
ENV_BASE = "AGENTS_ETAT_DB"
NOM_BASE = "etat.db"
STATUT_OK = "ok"
STATUT_DEGRADE = "degraded"
SOURCES: tuple[str, ...] = ("SPECS", "LEDGER")
PERIODE_SECONDES = 5.0
MAGIE_SQLITE = b"SQLite format 3\x00"
# Au-delà, le tick n'attend plus le verrou du snapshot : il repasse au tick suivant, rien n'est écrit.
_VERROU_SECONDES = 30.0
# Le busy_timeout de l'écrivain : une base verrouillée au-delà rend la tick `degraded`, jamais supprimée.
_ATTENTE_SECONDES = 5.0
# Les plafonds d'une source (avis sécurité, LOW) : au-delà, `degraded` — la lecture directe reste servie.
# Mesuré le 2026-10-16 : 6,1 Mo et 6 240 entrées pour le plus gros journal du kit.
_TAILLE_MAX = 64 * 2 ** 20
_ENTREES_MAX = 100_000
_RAISON_MAX = 240
# SQLite INTEGER est signé sur 64 bits ; un numéro de queue plus grand y est borné (le JS, lui, perd la
# précision au-delà de 2^53 : l'ordre de deux tels géants n'est tenu ni d'un côté ni de l'autre).
_ENTIER_MAX = 2 ** 63 - 1
_DROITS_DOSSIER = 0o700
_DROITS_FICHIER = 0o600

# A2.1 — le DDL EXACT, recopié par le banc (`ddl_egal_A2_1`).
DDL: tuple[str, ...] = (
    "CREATE TABLE meta(cle TEXT PRIMARY KEY, valeur TEXT NOT NULL)",
    "CREATE TABLE specs(id TEXT PRIMARY KEY, rang INTEGER NOT NULL, task TEXT NOT NULL, kind TEXT NOT NULL, "
    "date TEXT NOT NULL, tier INTEGER NOT NULL, num INTEGER, valeur TEXT NOT NULL, pli TEXT NOT NULL, "
    "sha TEXT NOT NULL, corps TEXT NOT NULL)",
    "CREATE TABLE journal_ledger(id TEXT PRIMARY KEY, rang INTEGER NOT NULL, category TEXT NOT NULL, "
    "status TEXT NOT NULL, created TEXT NOT NULL, tier INTEGER NOT NULL, num INTEGER, valeur TEXT NOT NULL, "
    "pli TEXT NOT NULL, sha TEXT NOT NULL, corps TEXT NOT NULL)",
    "CREATE TABLE sources(nom TEXT PRIMARY KEY, empreinte TEXT NOT NULL, statut TEXT NOT NULL, raison TEXT)",
)
# Les SEULES tables qu'un DROP touche jamais — et seulement dans une base NÔTRE (docstring).
_DROP: tuple[str, ...] = (
    "DROP TABLE IF EXISTS meta",
    "DROP TABLE IF EXISTS specs",
    "DROP TABLE IF EXISTS journal_ledger",
    "DROP TABLE IF EXISTS sources",
)

# La recette de chaque source : les fichiers et dossiers que son propriétaire lit, NOMMÉS par
# `dashboard_readers_base` (les mêmes que `_VIEW_SOURCE_FILES` et `_LEDGER_ENTRIES_REL`, témoin du banc).
_RECETTE: dict[str, tuple[tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...]]] = {
    "SPECS": ((_base._SPECS_REL, _base._SPECS_JOURNAL_REL), ()),
    "LEDGER": ((_base._LEDGER_REL,), (_base._LEDGER_ENTRIES_REL,)),
}
_PROPRIETAIRES: dict[str, Any] = {"SPECS": _specs, "LEDGER": _ledger}
# Les trois colonnes propres à chaque table, dans l'ordre du DDL ; champ absent → ''.
_CHAMPS: dict[str, tuple[str, str, str]] = {
    "SPECS": ("task", "kind", "date"),
    "LEDGER": ("category", "status", "created"),
}
# Le SQL de chaque table, en LITTÉRAUX : aucun nom de table n'est interpolé.
_SQL: dict[str, dict[str, str]] = {
    "SPECS": {
        "lignes": "SELECT id, sha, rang FROM specs",
        "retirer": "DELETE FROM specs WHERE id = ?",
        "poser": "INSERT OR REPLACE INTO specs(id, rang, task, kind, date, tier, num, valeur, pli, sha, corps) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    },
    "LEDGER": {
        "lignes": "SELECT id, sha, rang FROM journal_ledger",
        "retirer": "DELETE FROM journal_ledger WHERE id = ?",
        "poser": "INSERT OR REPLACE INTO journal_ledger(id, rang, category, status, created, tier, num, valeur, "
                 "pli, sha, corps) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    },
}
_SQL_OBJETS = "SELECT name FROM sqlite_master"
_SQL_SCHEMA = "SELECT valeur FROM meta WHERE cle = 'schema'"
_SQL_POSER_SCHEMA = "INSERT INTO meta(cle, valeur) VALUES ('schema', '1')"
_SQL_SOURCES = "SELECT nom, empreinte, statut FROM sources"
_SQL_POSER_SOURCE = "INSERT OR REPLACE INTO sources(nom, empreinte, statut, raison) VALUES (?, ?, ?, ?)"

# La couture `cadre.paths` (S-00001655) : le paquet, puis le fichier du clone par chemin.
# T-01M5BXTGX5YN8XEXTG1PP7A5ZX (phase E) : le dossier du fichier vient du RÉSOLVEUR `vendor_paths.py` (frère chargé
# PAR CHEMIN, jamais par `sys.path`) — `.agents/vendor/cadre` s'il porte le paquet, sinon `src/cadre` ; résolveur
# absent, illisible ou paquet introuvable : `src/cadre`, le lieu d'avant (son absence reste dite : `degraded`).
# Illisible (son exécution lève) : le repli le DIT en une ligne sur stderr, comme `event_store` (S-01M5CN1KBT).
# Incomplet (un nom de `_API_RESOLVEUR` manque) : ABSENT, repli muet, comme `event_store` et `record_id`.
_API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _dossier_cadre(racine: Path) -> Path:
    chemin = HERE / "vendor_paths.py"
    if not chemin.is_file():  # résolveur absent (copie partielle de `.agents/bin`) : le repli d'avant, muet
        return racine / "src" / "cadre"
    nom = "_vendor_paths_etat_projection"
    try:
        spec = importlib.util.spec_from_file_location(nom, chemin)
        if spec is None or spec.loader is None:  # pragma: no cover - défensif
            raise ImportError("vendor_paths.py sans chargeur")
        resolveur = importlib.util.module_from_spec(spec)
        existant = sys.modules.get(nom)
        sys.modules[nom] = resolveur  # enregistré AVANT `exec_module` (T-00000134) ; s'il lève, l'entrée d'avant
        try:
            spec.loader.exec_module(resolveur)
        except BaseException:
            if existant is not None:
                sys.modules[nom] = existant
            else:
                sys.modules.pop(nom, None)
            raise
    except Exception as exc:  # noqa: BLE001 - illisible = ABSENT, et le repli le DIT
        print(f"etat_projection: résolveur {chemin} illisible ({type(exc).__name__}: "
              f"{' '.join(str(exc).split())}) — repli sur src/cadre", file=sys.stderr)
        return racine / "src" / "cadre"
    if not all(hasattr(resolveur, n) for n in _API_RESOLVEUR):  # incomplet = ABSENT, comme les 4 autres
        return racine / "src" / "cadre"
    try:
        dossier = resolveur.dossier_paquet(racine, "cadre")
    except Exception:  # noqa: BLE001 - `dossier_paquet` qui lève = repli d'avant
        dossier = None
    return dossier if dossier is not None else racine / "src" / "cadre"


_CHEMIN_CADRE_PATHS = _dossier_cadre(HERE.parents[1]) / "paths.py"
_NOM_CADRE_PATHS_PAR_CHEMIN = "_cadre_paths_etat_projection"
_ATTRIBUTS_CADRE_PATHS = ("state_project", "project_root", "canonique_disque")


# ---------------------------------------------------------------------------
# Les fonctions PURES du contrat : pli, rang de tri, foin de recherche.
# ---------------------------------------------------------------------------

_DIACRITIQUES = re.compile("[̀-ͯ]")
# recordTier (section.js:166-172), porté à l'identique : `$` du JS sans drapeau m = fin de chaîne (`\Z`),
# `\d` du JS = ASCII, `\s` du JS = la classe ci-dessous (celle d'ECMAScript, pas celle de Python).
_JS_ESPACE = "\t\n\v\f\r    -     　﻿"
_QUEUE_ULID = re.compile(r"(?:^|[^0-9A-Za-z])([0-9A-HJKMNP-TV-Z]{26})\Z")
_QUEUE_NUM = re.compile(r"(?:^|[^0-9A-Za-z])([0-9]+)[" + _JS_ESPACE + r"]*\Z")


def plier(s: str) -> str:
    """`fold` de Memory.jsx:96 : NFD, U+0300–U+036F ôtés, PUIS minuscules (le même ordre que le JS)."""
    return _DIACRITIQUES.sub("", unicodedata.normalize("NFD", s)).lower()


def _texte(valeur: Any) -> str:
    """`text()` de format.js (null, undefined, '' → '' ; sinon `String(v)`), pour les types d'un JSON."""
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, float):
        if math.isnan(valeur):
            return "NaN"
        if math.isinf(valeur):
            return "Infinity" if valeur > 0 else "-Infinity"
        if valeur.is_integer() and abs(valeur) < 1e21:
            return str(int(valeur))
        return repr(valeur)
    if isinstance(valeur, list):
        return ",".join(_texte(v) for v in valeur)
    return "[object Object]"


def _vrai_js(valeur: Any) -> bool:
    """La véracité du JS sur une valeur JSON : '', 0, NaN, null, false sont faux ; [] et {} sont VRAIS."""
    if valeur is None or valeur is False:
        return False
    if isinstance(valeur, str):
        return valeur != ""
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return valeur != 0 and not (isinstance(valeur, float) and math.isnan(valeur))
    return True


def rangement(ident: str) -> tuple[int, int | None, str]:
    """(tier, num, valeur) de `recordTier` : ULID de queue → (2, None, ulid) ; numéro de queue → (1, int, '') ;
    sinon (0, None, id). L'ordre `recent` est (tier, num, valeur) DÉCROISSANT, `rang` croissant aux égalités."""
    s = _texte(ident)
    ulid = _QUEUE_ULID.search(s)
    if ulid:
        return (2, None, ulid.group(1))
    num = _QUEUE_NUM.search(s)
    if num:
        return (1, min(int(num.group(1)), _ENTIER_MAX), "")
    return (0, None, s)


def _liste_texte(valeur: Any, *, singleton: bool) -> list[str]:
    """`tagsOf` (tableau seul) ou `relatedOf` (tableau, ou valeur vraie seule) : `text` puis `filter(Boolean)`."""
    if isinstance(valeur, list):
        brut = valeur
    elif singleton and _vrai_js(valeur):
        brut = [valeur]
    else:
        brut = []
    return [t for t in (_texte(v) for v in brut) if t]


def foin(nom: str, entree: dict[str, Any]) -> str:
    """Le texte de recherche AVANT pliage (A2.1) : SPECS = id, task, kind, title (Memory.jsx:100-102) ; LEDGER =
    id, title, text, text_preview, tags…, related… (Memory.jsx:97-99), joints par une espace."""
    if nom == "SPECS":
        parts = [entree.get(c) for c in ("id", "task", "kind", "title")]
    elif nom == "LEDGER":
        parts = [entree.get(c) for c in ("id", "title", "text", "text_preview")]
        parts.append(" ".join(_liste_texte(entree.get("tags"), singleton=False)))
        parts.append(" ".join(_liste_texte(entree.get("related"), singleton=True)))
    else:
        raise ValueError(f"source inconnue : {nom!r} (connues : {SOURCES})")
    return " ".join(_texte(p) for p in parts)


# ---------------------------------------------------------------------------
# Où vit la base, et l'empreinte des sources.
# ---------------------------------------------------------------------------

def _cadre_paths() -> Any:
    """`cadre.paths` : (1) le paquet installé s'il porte les trois fonctions lues ici, (2) à défaut le fichier
    du clone PAR CHEMIN. Lève si les deux échouent ; `sys.modules` n'est relu que pour le fichier ATTENDU."""
    try:
        module = importlib.import_module("cadre.paths")
        if all(hasattr(module, a) for a in _ATTRIBUTS_CADRE_PATHS):
            return module
    except Exception:  # noqa: BLE001 - toute faute du paquet renvoie au repli déclaré
        pass
    existant = sys.modules.get(_NOM_CADRE_PATHS_PAR_CHEMIN)
    fichier = getattr(existant, "__file__", None)
    if existant is not None and fichier and Path(fichier) == _CHEMIN_CADRE_PATHS:
        return existant
    spec = importlib.util.spec_from_file_location(_NOM_CADRE_PATHS_PAR_CHEMIN, _CHEMIN_CADRE_PATHS)
    if spec is None or spec.loader is None:
        raise ImportError(f"cadre.paths introuvable : ni paquet installé, ni {_CHEMIN_CADRE_PATHS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _resoudre_base(racine: str | os.PathLike[str]) -> tuple[Path | None, str | None, bool]:
    """(chemin, None, forcé) ou (None, cause, False) quand l'emplacement ne se résout pas. Ne crée rien."""
    force = os.environ.get(ENV_BASE, "").strip()
    if force:
        return Path(force).expanduser(), None, True
    try:
        cp = _cadre_paths()
        demandee = cp.canonique_disque(Path(racine).resolve())
        resolue = cp.project_root(depuis=racine)
        if Path(resolue) != Path(demandee):
            return None, (f"racine résolue {resolue} ≠ racine demandée {demandee} (cadre.paths : "
                          f"$CADRE_PROJECT_ROOT ou la racine git prime)"), False
        return Path(cp.state_project(depuis=racine)) / NOM_BASE, None, False
    except Exception as exc:  # noqa: BLE001 - cadre introuvable = degraded, jamais une exception
        return None, f"cadre.paths introuvable ou en échec ({type(exc).__name__}: {exc})", False


def chemin_base(racine: str | os.PathLike[str]) -> Path | None:
    """A2.2 — `state_project(racine)/etat.db`, ou `AGENTS_ETAT_DB` ; None si `cadre.paths` est introuvable ou
    résout une autre racine. Ne crée ni répertoire ni fichier."""
    return _resoudre_base(racine)[0]


def _signature(chemin: Path) -> list[Any]:
    """`lstat` : type et droits, inode, taille, mtime, ctime — un chmod, un lien, un renommage qui garde mtime et
    taille bougent l'empreinte. Absent ou illisible : un marqueur et l'errno."""
    try:
        st = chemin.lstat()
    except OSError as exc:
        return ["absent" if isinstance(exc, FileNotFoundError) else "illisible", exc.errno]
    return [st.st_mode, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def _releve(racine: Path, nom: str) -> tuple[str, int, str | None]:
    """(empreinte, octets, refus) d'une source : la signature de chaque fichier de la recette, et celle de CHAQUE
    nom que portent ses dossiers — sans filtre de nom. Un dossier absent, illisible ou qui n'en est pas un donne un
    marqueur et son errno. Les octets sont ceux des fichiers réguliers relevés.

    LES LIENS SONT REFUSÉS DANS LES MAGASINS (avis sécurité, LOW) : un fichier de la recette qui existe sans être
    un fichier régulier (lien symbolique, FIFO, dossier…), un dossier de la recette qui est un lien, une entrée
    (hors nom pointé) qui est un lien — `refus` le nomme, et la source passe `degraded` SANS être chargée. Sans
    ce refus, un lien compterait 0 octet au plafond que le propriétaire, lui, dépasserait en le suivant ; son
    `lstat` ne bougerait pas quand sa cible change ; et une FIFO bloquerait le chargement sous le verrou du
    snapshot. La lecture directe, elle, reste servie."""
    fichiers, dossiers = _RECETTE[nom]
    parts: list[Any] = []
    octets = 0
    refus: str | None = None
    for rel in fichiers:
        signature = _signature(racine.joinpath(*rel))
        parts.append(signature)
        if len(signature) == 5:
            if stat.S_ISREG(signature[0]):
                octets += signature[2]
            elif refus is None:
                refus = "un fichier du magasin n'est pas un fichier régulier (lien, FIFO…) : refusé, non chargé"
    for rel in dossiers:
        dossier = racine.joinpath(*rel)
        signature_dossier = _signature(dossier)
        # Le seul TYPE du dossier entre dans l'empreinte (dossier ou lien) : un dossier remplacé par un lien vers
        # le même contenu garde ses noms et leurs `lstat`, et ne serait jamais relu.
        parts.append(["type", stat.S_IFMT(signature_dossier[0]) if len(signature_dossier) == 5 else None])
        if len(signature_dossier) == 5 and stat.S_ISLNK(signature_dossier[0]) and refus is None:
            refus = "le dossier du magasin est un lien symbolique : refusé, non chargé"
        try:
            with os.scandir(dossier) as entrees:
                noms = sorted(e.name for e in entrees)
        except OSError as exc:
            parts.append(["liste", exc.errno])
            continue
        for n in noms:
            signature = _signature(dossier / n)
            parts.append([n, *signature])
            if len(signature) == 5:
                if stat.S_ISREG(signature[0]):
                    octets += signature[2]
                elif stat.S_ISLNK(signature[0]) and not n.startswith(".") and refus is None:
                    refus = "une entrée du magasin est un lien symbolique : refusé, non chargé"
    empreinte = hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode("utf-8")).hexdigest()
    return empreinte, octets, refus


def empreinte_sources(racine: str | os.PathLike[str]) -> dict[str, str]:
    """A2.2 — l'empreinte de chaque source ('SPECS', 'LEDGER') : le relevé `lstat` de sa recette, haché
    (`_releve`). La racine n'y entre pas : deux graphies d'une même racine donnent la même empreinte."""
    racine = Path(racine)
    return {nom: _releve(racine, nom)[0] for nom in SOURCES}


# ---------------------------------------------------------------------------
# La lecture (D) : une connexion en lecture seule, ou None.
# ---------------------------------------------------------------------------

def _nature(base: Path) -> str:
    """'absente', 'vide' (0 octet), 'sqlite' (l'en-tête SQLite) ou 'etrangere' — LU, jamais ouvert en écriture.
    Ouvert comme `ledger._read_entry` : O_NONBLOCK (une FIFO ne bloque jamais le tick), O_NOFOLLOW (un lien
    n'est pas suivi), puis S_ISREG sur le descripteur ; tout ce qui n'est pas un fichier régulier lisible est
    'etrangere'."""
    try:
        fd = os.open(base, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return "absente"
    except OSError:
        return "etrangere"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "etrangere"
        tete = os.read(fd, len(MAGIE_SQLITE))
    finally:
        os.close(fd)
    if not tete:
        return "vide"
    return "sqlite" if tete == MAGIE_SQLITE else "etrangere"


def _connecter_lecture(base: Path) -> sqlite3.Connection:
    """`file:…?mode=ro` SANS `immutable` : le lecteur voit le WAL de l'écrivain."""
    return sqlite3.connect(base.resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0, isolation_level=None)


def _fermer(con: Any) -> None:
    try:
        con.close()
    except Exception:  # noqa: BLE001 - une fermeture ratée ne remonte jamais
        pass


def lire(racine: str | os.PathLike[str]) -> sqlite3.Connection | None:
    """A2.2 — une connexion en LECTURE SEULE à une base À JOUR, ou None : base absente ou qui n'est pas SQLite,
    `meta.schema` ≠ '1', une ligne `sources` absente, `degraded` (C1) ou dont l'empreinte n'est plus celle du
    disque. La connexion rendue est DANS une transaction de lecture ouverte avant ces contrôles : ce que
    l'appelant lit ensuite est l'instantané contrôlé. L'appelant la ferme. Ne lève jamais : toute exception est
    journalisée et rend None."""
    con: Any = None
    try:
        base, _cause, _force = _resoudre_base(racine)
        if base is None or base.is_symlink() or not base.is_file() or _nature(base) != "sqlite":
            return None
        con = _connecter_lecture(base)
        con.execute("BEGIN")
        schema = con.execute(_SQL_SCHEMA).fetchone()
        if schema is None or tuple(schema) != (SCHEMA,):
            _fermer(con)
            return None
        stockees = {nom: (empreinte, statut) for nom, empreinte, statut in con.execute(_SQL_SOURCES)}
        courantes = empreinte_sources(racine)
        if any(stockees.get(nom) != (courantes[nom], STATUT_OK) for nom in SOURCES):
            _fermer(con)
            return None
        return con
    except Exception as exc:  # noqa: BLE001 - A2.2 : jamais d'exception vers l'appelant
        _LOG.warning("ETAT DB ILLISIBLE (%s: %s) — les routes lisent les journaux directement",
                     type(exc).__name__, exc)
        if con is not None:
            _fermer(con)
        return None


# ---------------------------------------------------------------------------
# L'écriture (le fil du démon, les bancs).
# ---------------------------------------------------------------------------

class _Refus(Exception):
    """Le fichier au chemin de la base n'est pas une etat.db acceptable : il n'est ni modifié ni supprimé."""


class _Degradation(Exception):
    """Une entrée que la projection ne sait pas ranger : la source passe `degraded`, rien d'autre écrit."""


def _raison(exc: BaseException, racine: Path) -> str:
    """La raison d'une source illisible : la classe et le message, la racine absolue retirée, bornée."""
    message = str(exc)
    for prefixe in {str(racine.resolve()), str(racine)}:
        if prefixe and prefixe != ".":
            message = message.replace(prefixe, ".")
    return f"{type(exc).__name__}: {message}"[:_RAISON_MAX]


def _ligne(nom: str, ident: str, rang: int, entree: dict[str, Any], corps: str, sha: str) -> tuple[Any, ...]:
    tier, num, valeur = rangement(ident)
    a, b, c = (_texte(entree.get(champ)) for champ in _CHAMPS[nom])
    return (ident, rang, a, b, c, tier, num, valeur, plier(foin(nom, entree)), sha, corps)


def _lignes_changees(nom: str, entrees: list[Any], existants: dict[str, tuple[str, int]],
                     vus: set[str]) -> Iterator[tuple[Any, ...]]:
    """En FLUX, la ligne de chaque entrée dont (sha, rang) diffère de `existants` ; `vus` reçoit chaque id.
    Une entrée sans id texte, ou un id en double : `_Degradation`."""
    for rang, entree in enumerate(entrees):
        ident = entree.get("id") if isinstance(entree, dict) else None
        if not isinstance(ident, str) or not ident:
            raise _Degradation(f"entrée de rang {rang} sans identifiant texte")
        if ident in vus:
            raise _Degradation(f"identifiant en double : {ident}"[:_RAISON_MAX])
        vus.add(ident)
        octets = _transport.serialiser(entree)
        sha = hashlib.sha256(octets).hexdigest()
        if existants.get(ident) == (sha, rang):
            continue
        yield _ligne(nom, ident, rang, entree, octets.decode("utf-8"), sha)


def _annuler(con: sqlite3.Connection) -> None:
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _poser_source(con: sqlite3.Connection, nom: str, empreinte: str, statut: str, raison: str | None) -> None:
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute(_SQL_POSER_SOURCE, (nom, empreinte, statut, raison))
        con.execute("COMMIT")
    except BaseException:
        _annuler(con)
        raise


def _ecrire(con: sqlite3.Connection, nom: str, entrees: list[Any], existants: dict[str, tuple[str, int]],
            empreinte: str) -> None:
    """UNE transaction : les poses (en flux), les retraits, puis la ligne `sources` de la source."""
    vus: set[str] = set()
    con.execute("BEGIN IMMEDIATE")
    try:
        con.executemany(_SQL[nom]["poser"], _lignes_changees(nom, entrees, existants, vus))
        con.executemany(_SQL[nom]["retirer"], [(i,) for i in existants if i not in vus])
        con.execute(_SQL_POSER_SOURCE, (nom, empreinte, STATUT_OK, None))
        con.execute("COMMIT")
    except BaseException:
        _annuler(con)
        raise


def _projeter(con: sqlite3.Connection, nom: str, racine: Path, releve: tuple[str, int, str | None],
              existants: dict[str, tuple[str, int]]) -> str:
    """Charge une source par son propriétaire et l'écrit ; toute faute → sa ligne `sources` `degraded`."""
    empreinte, octets, refus = releve
    raison: str | None = None
    if refus is not None:
        raison = refus
    elif octets > _TAILLE_MAX:
        raison = f"au-delà du plafond de taille ({octets} > {_TAILLE_MAX} octets) : non chargée"
    else:
        try:
            donnees = _PROPRIETAIRES[nom].load(racine)
            entrees = donnees.get("entries") if isinstance(donnees, dict) else None
            if not isinstance(entrees, list):
                raise _Degradation("le propriétaire n'a pas rendu de liste d'entrées")
            del donnees
            if len(entrees) > _ENTREES_MAX:
                raise _Degradation(f"au-delà du plafond d'entrées ({len(entrees)} > {_ENTREES_MAX})")
            _ecrire(con, nom, entrees, existants, empreinte)
            return STATUT_OK
        except _Degradation as exc:
            raison = str(exc)
        except sqlite3.Error:
            raise
        except Exception as exc:  # noqa: BLE001 - une source illisible est un état, jamais une panne
            raison = _raison(exc, racine)
    _poser_source(con, nom, empreinte, STATUT_DEGRADE, raison)
    return STATUT_DEGRADE


def _creer_dossier(dossier: Path) -> None:
    """Chaque ancêtre manquant de `dossier`, créé en 0o700 (jamais un dossier existant n'est rechmodé)."""
    manquants: list[Path] = []
    courant = dossier
    while not courant.exists():
        manquants.append(courant)
        courant = courant.parent
    for chemin in reversed(manquants):
        chemin.mkdir(mode=_DROITS_DOSSIER, exist_ok=True)


def _restreindre(base: Path) -> None:
    """La base et ses `-wal`/`-shm` en 0o600 (seulement s'ils sont des fichiers réguliers aux droits autres)."""
    for chemin in (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm")):
        try:
            mode = chemin.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISREG(mode) and stat.S_IMODE(mode) != _DROITS_FICHIER:
            os.chmod(chemin, _DROITS_FICHIER)


def _etat_sqlite(con: sqlite3.Connection) -> str:
    """'vierge' (aucun objet), 'a_jour' (schéma 1), 'autre_schema' (NÔTRE, autre schéma) ou 'etrangere' — par
    LECTURE seule. Verrouillée : l'OperationalError remonte (ni refus ni suppression, le tick suivant reprend)."""
    try:
        objets = {n for (n,) in con.execute(_SQL_OBJETS)}
        if not objets:
            return "vierge"
        if "meta" not in objets:
            return "etrangere"
        ligne = con.execute(_SQL_SCHEMA).fetchone()
    except sqlite3.OperationalError:
        raise
    except sqlite3.DatabaseError:
        return "etrangere"  # corrompue : jamais supprimée
    if ligne is None:
        return "etrangere"
    return "a_jour" if tuple(ligne) == (SCHEMA,) else "autre_schema"


def _assurer_schema(con: sqlite3.Connection) -> None:
    """Schéma 1 en place, ou NOS tables reposées (la base est NÔTRE ou vierge : `_ouvrir_ecrivain` l'a prouvé)."""
    ligne = con.execute(_SQL_SCHEMA).fetchone() if "meta" in {n for (n,) in con.execute(_SQL_OBJETS)} else None
    if ligne is not None and tuple(ligne) == (SCHEMA,):
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        for instruction in _DROP + DDL:
            con.execute(instruction)
        con.execute(_SQL_POSER_SCHEMA)
        con.execute("COMMIT")
    except BaseException:
        _annuler(con)
        raise


def _ouvrir_ecrivain(base: Path, force: bool) -> sqlite3.Connection:
    """La connexion de l'écrivain, après preuve que le fichier est acceptable (docstring du module) : sinon
    `_Refus`, et le fichier n'a été ni écrit ni supprimé. WAL, busy_timeout, droits resserrés, schéma assuré."""
    if base.is_symlink():
        raise _Refus(f"{base} est un lien symbolique : refusé, jamais suivi")
    remede = (f"corrigez {ENV_BASE}" if force else
              "supprimez-le à la main s'il ne sert à rien (la base est dérivée, refaite au tick suivant)")
    nature = _nature(base)
    if nature == "etrangere" or (force and nature == "vide"):
        raise _Refus(f"{base} n'est pas une etat.db de ce kit ({nature}) : refusé, jamais modifié — {remede}")
    if nature == "absente":
        _creer_dossier(base.parent)
        os.close(os.open(base, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _DROITS_FICHIER))
    # `timeout` EST le busy_timeout de SQLite (`sqlite3_busy_timeout`), posé par le module à la connexion.
    con = sqlite3.connect(str(base), timeout=_ATTENTE_SECONDES, isolation_level=None)
    try:
        if nature == "sqlite":
            etat = _etat_sqlite(con)
            if etat == "etrangere" or (force and etat != "a_jour"):
                raise _Refus(f"{base} n'est pas une etat.db acceptable ({etat}) : refusé, jamais modifié — {remede}")
        _restreindre(base)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        _assurer_schema(con)
        _restreindre(base)
        return con
    except BaseException:
        _fermer(con)
        raise


def _rafraichir(racine: str | os.PathLike[str], verrou: Any | None) -> tuple[dict[str, str], str | None]:
    """(statut par source, cause d'une dégradation de la base elle-même ou None)."""
    racine = Path(racine)
    base, cause, force = _resoudre_base(racine)
    if base is None:
        return {nom: STATUT_DEGRADE for nom in SOURCES}, cause
    releves = {nom: _releve(racine, nom) for nom in SOURCES}  # EN PREMIER : avant tout chargement
    try:
        con = _ouvrir_ecrivain(base, force)
    except _Refus as exc:
        return {nom: STATUT_DEGRADE for nom in SOURCES}, str(exc)
    except (sqlite3.Error, OSError) as exc:
        return {nom: STATUT_DEGRADE for nom in SOURCES}, f"base {base} inutilisable ({type(exc).__name__}: {exc})"
    try:
        stockees = {nom: (empreinte, statut) for nom, empreinte, statut in con.execute(_SQL_SOURCES)}
        a_charger = [nom for nom in SOURCES if nom not in stockees or stockees[nom][0] != releves[nom][0]]
        if not a_charger:
            return {nom: stockees[nom][1] for nom in SOURCES}, None
        existants = {nom: {i: (sha, rang) for i, sha, rang in con.execute(_SQL[nom]["lignes"])}
                     for nom in a_charger}
        if verrou is not None and not verrou.acquire(timeout=_VERROU_SECONDES):
            return ({nom: stockees.get(nom, ("", STATUT_DEGRADE))[1] for nom in SOURCES},
                    "verrou du snapshot non obtenu : tick reporté")
        try:
            statuts = {nom: stockees[nom][1] for nom in SOURCES if nom in stockees}
            for nom in a_charger:
                statuts[nom] = _projeter(con, nom, racine, releves[nom], existants.pop(nom))
        finally:
            if verrou is not None:
                verrou.release()
        return {nom: statuts[nom] for nom in SOURCES}, None
    except (sqlite3.Error, OSError) as exc:
        return {nom: STATUT_DEGRADE for nom in SOURCES}, f"base {base} : écriture en échec ({type(exc).__name__}: {exc})"
    finally:
        _fermer(con)


def rafraichir(racine: str | os.PathLike[str], *, verrou: Any | None = None) -> dict[str, str]:
    """A2.2 — met la base au niveau des journaux et rend le statut de chaque source ('ok' | 'degraded').
    `verrou` : le verrou de construction du snapshot (`MemoCorps.verrou`), tenu pendant le chargement, le
    calcul et l'écriture des lignes (C2). Écrivain : le fil du démon et les bancs, jamais un handler."""
    return _rafraichir(racine, verrou)[0]


class Boucle:
    """Le fil écrivain unique : un tick tout de suite, puis toutes les `periode` secondes. Ne meurt jamais d'un
    tick raté ; journalise un changement d'état (statuts ou cause), pas chaque tick."""

    def __init__(self, racine: str | os.PathLike[str], *, verrou: Any | None = None,
                 periode: float = PERIODE_SECONDES) -> None:
        self._racine = Path(racine)
        self._verrou = verrou
        self._periode = periode
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._dernier: tuple[Any, ...] | None = None
        self.ticks = 0

    def start(self) -> bool:
        self._fil = threading.Thread(target=self._run, daemon=True, name="etat-projection")
        self._fil.start()
        return True

    def _tick(self) -> None:
        try:
            statuts, cause = _rafraichir(self._racine, self._verrou)
        except Exception as exc:  # noqa: BLE001 - le fil ne meurt jamais d'un tick
            statuts, cause = {}, f"tick en échec ({type(exc).__name__}: {exc})"
        self.ticks += 1
        etat = (tuple(sorted(statuts.items())), cause)
        if etat != self._dernier:
            self._dernier = etat
            if cause is not None or any(s != STATUT_OK for s in statuts.values()):
                _LOG.warning("ETAT DB DEGRADED: %s — %s ; les routes lisent les journaux directement",
                             dict(statuts), cause or "source illisible")

    def _run(self) -> None:
        while not self._arret.is_set():
            self._tick()
            self._arret.wait(self._periode)

    def signaler_arret(self) -> None:
        """Pose l'événement d'arrêt SANS attendre : le démon le pose avant sa première jointure."""
        self._arret.set()

    def stop(self, timeout: float = 10.0) -> bool:
        """Arrêt borné : True si le fil est sorti dans `timeout` (aucune transaction en cours)."""
        self._arret.set()
        if self._fil is None:
            return True
        self._fil.join(timeout)
        return not self._fil.is_alive()
