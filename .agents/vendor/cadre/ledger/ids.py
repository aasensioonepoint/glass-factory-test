"""ULID en bibliothèque standard — 26 caractères Crockford base32, MONOTONES
dans la milliseconde, par copie chargée du module.

Phase 2 de T-012. `dependencies` VIDE dans `pyproject.toml` EST le contrat
« stdlib seule » (`check_no_network`), donc AUCUN paquet ULID : `time` +
`secrets` + `os.getpid` + `threading.Lock`. 128 bits = 48 bits d'horodatage
(millisecondes) EN TÊTE + 80 bits d'aléa, soit 10 + 16 = 26 caractères.

L'horodatage en tête donne le TRI LEXICOGRAPHIQUE CROISSANT DANS LE TEMPS :
l'alphabet Crockford est monotone en ASCII, donc l'ordre des chaînes de même
longueur suit l'ordre des valeurs encodées. `secrets` fournit l'aléa
cryptographique ; il n'est ni dans `IMPORTS_IMPURS` ni un client réseau.

MONOTONIE (T-00000689) : deux ULID émis par la MÊME copie chargée de ce module
dans la MÊME ms sortent STRICTEMENT croissants — aléa précédent + 1 au lieu
d'un tirage neuf (forme « ULID monotone » standard, à égalité de ms). L'état
`(pid, ms, aléa)` du DERNIER ULID émis vit EN MÉMOIRE de cette copie, sous
verrou : jamais écrit, jamais lu ailleurs, mort avec elle — ce n'est PAS un
compteur stocké. Aucune E/S : ce module CALCULE, il ne touche rien.

GARANTI : stricte croissance et unicité des ULID émis par UNE copie chargée du
module (tous threads) dans une même ms, TANT QU'AUCUN appel à ms EXPLICITE
(backfill) ne s'interpose entre deux émissions à l'horloge — l'état ne retient
que la DERNIÈRE ms émise, donc une ms intercalée rompt la chaîne « + 1 » et
l'émission suivante à l'horloge tire à neuf ; deux processus distincts ⇒
uniques (80 bits indépendants). NON GARANTI : l'ordre entre DEUX COPIES
chargées du module dans un même processus (la branche 2 de
`run_export._cadre` en charge une seconde par chemin, d'état indépendant —
UNE seule par processus depuis T-00000691 : `sys.modules` la partage entre
copies de `run_export` — magasins distincts, aucun ordre croisé requis) ;
l'ordre à travers une émission INTERCALÉE à une autre ms ; l'ordre ENTRE
processus dans une même ms (ordre ARBITRAIRE, comme avant — la reconstruction
de T-00000691 départage des ULID ÉGAUX par `(ulid, auteur/copie)`, jamais par
l'index de ligne) ; l'ordre à travers un RECUL d'horloge (le préfixe reste VRAI,
l'aléa est retiré à neuf) ; et le PASSÉ — aucun ULID existant n'est réécrit.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Callable

__all__ = ["nouvel_ulid", "ALPHABET", "LONGUEUR"]

#: Crockford base32 : 0-9 puis A-Z sans I, L, O, U. Monotone en ASCII.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_BITS_TEMPS = 48
_BITS_ALEA = 80
_CAR_TEMPS = 10   # 48 bits tiennent sur 10 symboles de 5 bits (50 bits, 2 en tête à 0)
_CAR_ALEA = 16    # 80 bits = 16 symboles de 5 bits, pile
LONGUEUR = _CAR_TEMPS + _CAR_ALEA  # 26


def _encoder(valeur: int, nb_caracteres: int) -> str:
    """`valeur` sur `nb_caracteres` symboles Crockford, poids fort à gauche."""
    out = []
    for _ in range(nb_caracteres):
        out.append(ALPHABET[valeur & 0x1F])
        valeur >>= 5
    return "".join(reversed(out))


_MAX_ALEA = (1 << _BITS_ALEA) - 1

#: Mémoire de PROCESSUS (jamais persistée, jamais partagée) : (pid, ms, aléa)
#: du DERNIER ULID émis. Pas un compteur stocké. Le pid en fait partie : sans
#: lui, un fils de `fork` émettant dans la ms de son père reprendrait
#: « aléa + 1 » — collision DÉTERMINISTE que l'ULID aléatoire n'avait pas.
_VERROU = threading.Lock()
_etat: tuple[int, int, int] | None = None


def _apres_fork() -> None:
    """Dans le FILS d'un `fork` : verrou NEUF et état vide. Le motif premier est
    le VERROU — forké pendant qu'un autre thread du père le tenait, le fils en
    hérite FERMÉ et bloquerait à son premier ULID. L'état remis à zéro double la
    garde par pid (conservée). Chaque copie chargée du module enregistre le
    sien ; il ne touche que ses deux globales."""
    global _VERROU, _etat
    _VERROU, _etat = threading.Lock(), None


if hasattr(os, "register_at_fork"):  # POSIX seul : absent sous Windows
    os.register_at_fork(after_in_child=_apres_fork)


def _suivant(
    etat: tuple[int, int, int] | None,
    pid: int,
    ms: int,
    tirer: Callable[[], int],
) -> tuple[tuple[int, int, int], int]:
    """PUR : (nouvel_etat, alea) pour `ms`. Même pid ET même ms que le dernier
    émis → aléa précédent + 1 ; sinon tirage neuf. Dépassement → OverflowError."""
    if etat is not None and etat[0] == pid and etat[1] == ms:
        alea = etat[2] + 1
        if alea > _MAX_ALEA:
            raise OverflowError("ULID monotone : aléa épuisé dans la milliseconde")
    else:
        alea = tirer()
    return (pid, ms, alea), alea


def nouvel_ulid(horodatage_ms: int | None = None) -> str:
    """Un ULID de 26 caractères, STRICTEMENT croissant dans la ms pour CETTE
    copie chargée du module.

    `horodatage_ms` sert aux bancs et au backfill (ms explicite) ; à défaut,
    l'horloge murale en millisecondes, tronquée à 48 bits — lue SOUS le verrou,
    sinon un thread préempté entre la lecture et le verrou émettrait, à la même
    ms, un ULID PLUS PETIT qu'un déjà émis. UN SEUL comportement dans les deux
    cas : même pid et même ms que le dernier ULID émis → aléa précédent + 1 ;
    sinon tirage neuf (`secrets`). L'état ne retient que la DERNIÈRE ms émise :
    une ms explicite intercalée entre deux émissions à l'horloge rompt la
    chaîne « + 1 » (tirage neuf au retour), et deux copies chargées du module
    ne partagent rien. Une ms ANTÉRIEURE à la dernière (recul d'horloge,
    backfill) n'est JAMAIS pincée sur celle-ci : le préfixe temps est la ms
    donnée. Lève `OverflowError` si l'aléa est épuisé dans la ms (≈ k/2^80 par
    émission) plutôt que de reboucler sur un ULID PLUS PETIT ; sous
    `BEGIN IMMEDIATE`, l'appelant fait son rollback.
    """
    global _etat
    with _VERROU:
        ms = (int(time.time() * 1000) if horodatage_ms is None
              else int(horodatage_ms))
        ms &= (1 << _BITS_TEMPS) - 1
        _etat, alea = _suivant(_etat, os.getpid(), ms,
                               lambda: secrets.randbits(_BITS_ALEA))
    return _encoder(ms, _CAR_TEMPS) + _encoder(alea, _CAR_ALEA)
