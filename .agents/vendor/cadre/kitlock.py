"""`.agents/kit.lock` — la version de kit ET de contrat d'un dépôt.

Format 1 : un objet JSON à TROIS clés, ni plus ni moins —

* `version_contrat` — la clé du lockstep, SemVer sur le contrat seul ; elle
  égale `cadre.__version_contrat__` du noyau qui a écrit le fichier ;
* `version_kit` — `cadre.__version__`, PEP 440, INFORMATIVE : elle ne garantit
  rien et aucune comparaison ne la lit ; elle n'est jamais vide ;
* `version_format` — `1`.

La sérialisation est celle des trois magasins d'état partagé :
`json.dumps(…, indent=2, ensure_ascii=False, sort_keys=True)` suivi d'un retour
à la ligne final, fins de ligne LF. Ni horodatage ni chemin : deux écritures
des mêmes valeurs rendent les mêmes octets.

LE REFUS EST UN TYPE, JAMAIS UNE VALEUR PAR DÉFAUT. Tout ce qui n'est pas un
`kit.lock` au format 1 lève `KitLockIllisible` ; un `version_format` entier
autre que 1 lève sa sous-classe `KitLockFormatInconnu`, parce que c'est le seul
cas où le fichier est probablement BIEN FORMÉ — écrit par un noyau plus récent —
et où le remède n'est pas de le réparer mais de mettre ce noyau à jour. Le
format est donc lu AVANT l'ensemble des clés : un format 2 porte légitimement
des clés que le format 1 ignore.

CE QUE CE MODULE NE FAIT PAS. Il ne compare rien : la règle qui confronte le
fichier au noyau installé relève d'un lot ultérieur. Il n'est appelé par aucune
commande : `cadre init`, qui l'écrira, reste réservé. Hôtes activés, niveau et
empreintes des définitions viendront en format 2.

Pureté : ce module DÉCIDE, il ne touche pas le disque lui-même. Toute E/S passe
par le paramètre annoté `atelier: Workspace`, la couture du noyau.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cadre import __version__, __version_contrat__
from cadre.workspace import HorsRacine, Workspace

VERSION_FORMAT = 1
RELATIF = ".agents/kit.lock"
CLES = frozenset({"version_contrat", "version_format", "version_kit"})

#: MAJEUR.MINEUR.CORRECTIF sans zéro de tête, pré-version et métadonnées de
#: construction tolérées. `re.ASCII` : sans lui, `\d` accepte tout chiffre
#: décimal Unicode, et SemVer n'en connaît que dix.
_SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
    re.ASCII,
)


class KitLockIllisible(ValueError):
    """Le contenu n'est pas un `kit.lock` au format 1, ou il n'a pas pu être lu.
    Jamais de valeur par défaut : un fichier illisible est refusé, pas complété."""


class KitLockFormatInconnu(KitLockIllisible):
    """`version_format` est un entier que ce noyau ne connaît pas — le fichier a
    probablement été écrit par un noyau plus récent."""


@dataclass(frozen=True)
class KitLock:
    version_kit: str
    version_contrat: str
    version_format: int = VERSION_FORMAT


def attendu() -> KitLock:
    """Le `kit.lock` que CE noyau écrit : ses deux versions, format 1."""
    return KitLock(
        version_kit=__version__,
        version_contrat=__version_contrat__,
        version_format=VERSION_FORMAT,
    )


def rendre(lock: KitLock) -> str:
    """Les octets du fichier, en texte : clés triées, indentation 2, LF final.

    Le texte rendu est relu par `parser` avant d'être rendu : ce module ne
    produit jamais un contenu qu'il refuserait de lire. Un `lock` mal formé
    lève donc `KitLockIllisible` ICI, avant toute écriture.
    """
    objet = {
        "version_contrat": lock.version_contrat,
        "version_format": lock.version_format,
        "version_kit": lock.version_kit,
    }
    texte = json.dumps(objet, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    parser(texte)
    return texte


def parser(texte: str) -> KitLock:
    """Le `KitLock` porté par `texte`, ou `KitLockIllisible`.

    Refusés, dans cet ordre : un texte qui n'est pas du JSON lisible (y compris
    trop imbriqué ou portant un entier trop long à convertir) ; un JSON qui
    n'est pas un objet ; un `version_format` présent mais qui n'est pas un
    entier ; un `version_format` entier autre que 1 (`KitLockFormatInconnu`) ;
    une clé manquante ; une clé inconnue ; une version qui n'est pas une
    chaîne ; un `version_contrat` qui n'est pas SemVer ; un `version_kit` vide.
    """
    try:
        objet = json.loads(texte)
    except (ValueError, RecursionError) as exc:
        raise KitLockIllisible(
            f"{RELATIF} n'est pas du JSON lisible : {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(objet, dict):
        raise KitLockIllisible(
            f"{RELATIF} doit être un objet JSON, pas {type(objet).__name__}")
    # LE FORMAT D'ABORD : un format 2 porte des clés que le format 1 ignore, et
    # le rapporter comme « clé inconnue » enverrait réparer un fichier sain.
    if "version_format" in objet:
        fmt = objet["version_format"]
        if type(fmt) is not int:
            raise KitLockIllisible(
                f"{RELATIF} : version_format doit être un entier, pas "
                f"{type(fmt).__name__}")
        if fmt != VERSION_FORMAT:
            raise KitLockFormatInconnu(
                f"{RELATIF} : version_format {fmt} inconnu de ce noyau, écrit "
                f"par un noyau plus récent ? Ce noyau lit le format "
                f"{VERSION_FORMAT} ; monter la distribution `cadre-kit` (paquet "
                f"d'import `cadre`) par la forme épinglée — README du kit, "
                f"§ Install the core (glass-dist).")
    manquantes = sorted(CLES - set(objet))
    if manquantes:
        raise KitLockIllisible(f"{RELATIF} : clé(s) manquante(s) {manquantes}")
    inconnues = sorted(set(objet) - CLES)
    if set(objet) != CLES:
        raise KitLockIllisible(
            f"{RELATIF} : clé(s) inconnue(s) au format {VERSION_FORMAT} {inconnues}")
    for cle in ("version_contrat", "version_kit"):
        if not isinstance(objet[cle], str):
            raise KitLockIllisible(
                f"{RELATIF} : {cle} doit être une chaîne, pas "
                f"{type(objet[cle]).__name__}")
    if not _SEMVER.fullmatch(objet["version_contrat"]):
        raise KitLockIllisible(
            f"{RELATIF} : version_contrat {objet['version_contrat']!r} n'est pas "
            "une version SemVer (MAJEUR.MINEUR.CORRECTIF)")
    if not objet["version_kit"]:
        raise KitLockIllisible(f"{RELATIF} : version_kit est vide")
    return KitLock(
        version_kit=objet["version_kit"],
        version_contrat=objet["version_contrat"],
        version_format=objet["version_format"],
    )


def lire(atelier: Workspace) -> KitLock | None:
    """Le `kit.lock` du dépôt, ou `None` s'il est ABSENT — et seulement alors.

    Toute autre issue de lecture est un refus `KitLockIllisible` : un chemin qui
    sort de la racine (lien symbolique), un répertoire, un fichier illisible,
    un contenu qui n'est pas de l'UTF-8, ou un contenu que `parser` refuse. Un
    lien qui pointe hors du dépôt n'est PAS un fichier absent : le lire comme
    tel ferait passer un dépôt dont le verrou existe pour un dépôt qui n'en a
    pas.
    """
    try:
        brut = atelier.read_bytes(RELATIF)
    except FileNotFoundError:
        return None
    except HorsRacine as exc:
        raise KitLockIllisible(
            f"{RELATIF} pointe hors de la racine du dépôt : {exc}") from exc
    except OSError as exc:
        raise KitLockIllisible(
            f"{RELATIF} illisible : {type(exc).__name__}: {exc}") from exc
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KitLockIllisible(f"{RELATIF} n'est pas de l'UTF-8 : {exc}") from exc
    return parser(texte)


def ecrire(atelier: Workspace, lock: KitLock) -> Path:
    """Écrit `lock` à `RELATIF`, atomiquement, et rend le chemin écrit.

    Un `lock` que `parser` refuserait lève `KitLockIllisible` AVANT toute
    écriture (la validation est dans `rendre`) : rien n'est posé sur le disque.
    """
    return atelier.write_text(RELATIF, rendre(lock))
