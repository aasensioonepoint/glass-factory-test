"""Lecture et premier tirage DURCIS de `<partition>/run/copie` (T-01M5ETBT21G550XBXPR4V3XPH0).

Extrait de `run_export` (cliquet de longueur des `.py`) : `identifiant_de_copie`
et `_lire_copie` y restent et passent par ce module, chargé paresseusement
(`run_export._run_copie`). Aucun import de `run_export` ici : un refus lève
`CopieRefusee`, que `identifiant_de_copie` convertit en `RunExportError` et que
`_lire_copie` (relevé des partitions sœurs) traduit en `None`.

Les messages nomment `run/copie`, jamais le chemin absolu de la partition (il
porte le dossier personnel de l'utilisateur).
"""

from __future__ import annotations

import errno
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path
from typing import Optional

#: Octets lus au plus : 16 hex et fin de ligne tiennent large ; au-delà, le
#: fichier n'est pas un tirage de ce module (refus, jamais tronqué).
COPIE_OCTETS_MAX = 64

#: Même valeur que `run_export.RESERVE_BACKFILL` (décision pilote S-00001594),
#: recopiée pour ne pas importer `run_export` ; un témoin tient l'égalité.
RESERVE_BACKFILL = "backfill"

_COPIE_RE = re.compile(r"[0-9a-f]{16}")
_NOM = "run/copie"
_EFFACER = "efface STATE_PROJECT/run/copie (chemin : `cadre paths`) pour tirer une copie neuve."


class CopieRefusee(Exception):
    """`run/copie` existe mais n'est pas une identité lisible : jamais réécrit."""


def lire_copie_disque(chemin: Path) -> Optional[str]:
    """La copie gardée dans `chemin`, ou `None` s'il est ABSENT. Tout autre état
    lève `CopieRefusee` — jamais un retirage silencieux : un identifiant existant
    mal formé peut être une vraie identité abîmée, le remplacer scinderait les
    exports de cette copie en deux dossiers sans que personne le voie ; la
    réparation (effacer `run/copie`) reste un geste humain.

    Ouverture `O_NOFOLLOW | O_NONBLOCK` (modèle : `_acteur_copie_lue` du board) :
    un lien symbolique est refusé (ELOOP), un FIFO n'est jamais attendu, puis
    fichier ordinaire exigé, au plus `COPIE_OCTETS_MAX` octets, ASCII strict,
    16 hex exacts. BORNE : `O_NOFOLLOW` n'existe qu'en POSIX ; sous Windows le
    drapeau vaut 0 et un lien y serait suivi (la forme 16 hex reste exigée)."""
    drapeaux = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(chemin, drapeaux)
    except FileNotFoundError:
        return None
    except OSError as exc:
        # Windows : `os.open` sur un dossier lève PermissionError (non mesuré là-bas ;
        # témoin par simulation) — dit « pas un fichier ordinaire », comme en POSIX.
        if isinstance(exc, PermissionError) and os.path.isdir(chemin):
            raise CopieRefusee(f"{_NOM} n'est pas un fichier ordinaire — refus ; {_EFFACER}") from exc
        cause = "lien symbolique" if exc.errno == errno.ELOOP else type(exc).__name__
        raise CopieRefusee(f"{_NOM} illisible ({cause}) — refus ; {_EFFACER}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CopieRefusee(f"{_NOM} n'est pas un fichier ordinaire — refus ; {_EFFACER}")
        brut = os.read(fd, COPIE_OCTETS_MAX + 1)
    finally:
        os.close(fd)
    if len(brut) > COPIE_OCTETS_MAX:
        raise CopieRefusee(f"{_NOM} de plus de {COPIE_OCTETS_MAX} octets — refus ; {_EFFACER}")
    try:
        valeur = brut.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CopieRefusee(f"{_NOM} porte un octet non ASCII — refus ; {_EFFACER}") from exc
    if not valeur:
        raise CopieRefusee(f"{_NOM} vide (résidu probable d'une coupure) — refus ; {_EFFACER}")
    if valeur == RESERVE_BACKFILL:
        raise CopieRefusee(
            "copie réservée « backfill » lue comme identité de copie normale : "
            "refus (décision pilote S-00001594)."
        )
    if not _COPIE_RE.fullmatch(valeur):
        raise CopieRefusee(f"{_NOM} mal formé (16 hex attendus) — refus ; {_EFFACER}")
    return valeur


def publier_copie(chemin: Path) -> str:
    """Premier tirage (`secrets.token_hex(8)`) : temporaire UNIQUE (`mkstemp`,
    0600) écrit puis `fsync`, publié par `os.link`, qui échoue si `chemin` existe
    — deux démarrages concurrents rendent la valeur du GAGNANT, relue, jamais deux
    identités. Le `fsync` AVANT le lien : une coupure ne publie jamais un `copie`
    vide, que `lire_copie_disque` refuserait ensuite à demeure. Le temporaire est
    supprimé en toutes circonstances. Sans lien dur (`os.link` lève une autre
    `OSError` : exFAT, SMB, FUSE — décision S-01M5EX00Q2), repli
    `_publier_sans_lien`. BORNES : le repli n'est pas atomique (voir sa
    docstring) ; le dossier parent n'est pas `fsync` (une coupure peut perdre
    l'entrée). L'appelant a déjà créé le dossier et posé le marqueur."""
    ligne = secrets.token_hex(8) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=chemin.name + ".", suffix=".tmp", dir=str(chemin.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as sortie:
            sortie.write(ligne)
            sortie.flush()
            os.fsync(sortie.fileno())
        try:
            os.link(tmp, chemin)
        except FileExistsError:
            pass  # un démarrage concurrent a publié d'abord : sa valeur fait foi
        except OSError:
            _publier_sans_lien(chemin, ligne)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    valeur = lire_copie_disque(chemin)
    if valeur is None:
        raise CopieRefusee(f"{_NOM} disparu après publication — refus.")
    return valeur


def _errno_nom(exc: OSError) -> str:
    """Le nom symbolique de l'errno (`EPERM`…), jamais le message : il porte les chemins absolus."""
    return errno.errorcode.get(exc.errno or 0, type(exc).__name__)


def _publier_sans_lien(chemin: Path, ligne: str) -> None:
    """Repli sans lien dur (décision S-01M5EX00Q2) : `chemin` créé `O_CREAT | O_EXCL`
    (0600), écrit, `flush` puis `fsync`. `FileExistsError` = un démarrage
    concurrent a créé d'abord : rien n'est écrit, l'appelant relit le gagnant.
    Toute autre `OSError` devient `CopieRefusee` avec l'errno symbolique, sans
    chemin absolu ; un fichier créé ici puis non écrit est retiré. BORNE : non
    atomique — entre la création et l'écriture, un lecteur concurrent voit un
    fichier vide et le refuse (« vide ») ; une coupure dans cette fenêtre laisse
    ce vide, refusé à demeure jusqu'au geste humain."""
    drapeaux = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(chemin, drapeaux, 0o600)
    except FileExistsError:
        return
    except OSError as exc:
        raise CopieRefusee(f"{_NOM} impubliable sans lien dur ({_errno_nom(exc)}) — refus.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as sortie:
            sortie.write(ligne)
            sortie.flush()
            os.fsync(sortie.fileno())
    except OSError as exc:
        try:
            os.unlink(chemin)
        except OSError:
            pass
        raise CopieRefusee(f"{_NOM} non écrit sans lien dur ({_errno_nom(exc)}) — refus.") from exc
