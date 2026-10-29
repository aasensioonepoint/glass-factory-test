"""Canal B du dashboard : recalcul BORNÉ, valeur DATÉE, lecture INCRÉMENTALE (T-01M5T5G6MR).

Un recalcul entier de canal B coûte ~19 s sur une rétention pleine (mesuré : 185 522 lignes, 1,8 M records,
15,6 s de lecture et normalisation, 2,8 s d'agrégat). `dashboard._read_canal_b` le fait au plus selon trois
règles, toutes ici, sans boîte noire :

  1. BORNE. Une valeur ok de source sqlite n'est pas recalculée avant `debut + FACTEUR × duree` quand SEULE
     la part DONNÉES du store a bougé (mtime, taille, génération de `store_fingerprint`) : au plus 1/FACTEUR
     d'un cœur. Sous `SEUIL_S` de durée, rien n'est différé. Un statut, une base, un dossier, un spool, un
     `dropped_foreign` ou une identité qui changent recalculent tout de suite (`differer`).
  2. DATÉE. Toute valeur ok servie porte `fraicheur = {calcule_le, duree_s, differe, prochain_au_plus_tot}` ;
     différée, c'est la valeur en cache avec `differe: True`, l'objet en cache n'est jamais muté. `jeton()`
     entre dans la clé du transport : l'échéance franchie reconstruit le snapshot sans ligne neuve.
  3. INCRÉMENTALE. Après une lecture complète, seules les lignes `id > dernier` sont relues et normalisées,
     tant que la base, `rewrite_generation` et `canal_b_bornes(dernier) == (premier, lignes)` tiennent ;
     sinon `oublier()` puis relecture entière (`suite`). Le cumul n'est écrit qu'APRÈS un flux complet
     (`cumuler`) : un flux mort laisse l'état tel qu'il était, l'appel suivant reprend au même filigrane.

Le cumul (records) est RÉSIDENT : RSS de l'ordre de 2 Go au rejeu, plafond = la rétention de 30 jours.
Horloges injectables : `_horloge` (monotone, fenêtres) et `_mur` (murale, dates affichées).
"""
from __future__ import annotations

import functools
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

# `_etat` est GLOBAL au processus, le verrou du transport ne vaut que PAR SERVEUR : tout appel qui lit ou écrit
# l'état de canal B passe par CE verrou (`sous_verrou`), quel que soit le serveur ou le fil appelant.
VERROU = threading.Lock()


def sous_verrou(fonction: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fonction)
    def _sous_verrou(*args: Any, **kwargs: Any) -> Any:
        with VERROU:
            return fonction(*args, **kwargs)
    return _sous_verrou


SEUIL_S = 0.5
FACTEUR = 10
# Rang de `store_fingerprint()` dans l'empreinte de `dashboard._canal_b_fingerprint` (+ dropped_foreign, id propre).
INDEX_STORE = 5

_horloge: Callable[[], float] = time.monotonic
_mur: Callable[[], datetime] = lambda: datetime.now(timezone.utc)  # noqa: E731 - horloge injectable

_etat: dict[str, Any] = {}
_echeances = 0  # différés finis, monotone : `jeton()` ; `oublier` n'y touche pas (une clé ne revient jamais)


def oublier() -> None:
    """Tout l'état, cumul compris : appelé avant toute relecture entière, pour qu'aucun ancien cumul ne
    coexiste avec le nouveau (pic mémoire), et par `dashboard._reset_canal_b_cache_for_tests`."""
    _etat.clear()
    _etat.update(valeur=None, empreinte=None, debut=None, duree=None, filigrane=None, cumul=None,
                 reecriture_lue=None, differe=False)


oublier()


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sans_donnees(empreinte: Any) -> Any:
    """L'empreinte sans la part DONNÉES de `store_fingerprint` — `(path, present, mtime_ns, size, (status,
    data_generation))` devient `(path, present, status)`. Toute autre forme reste entière (rien différé)."""
    if not isinstance(empreinte, tuple) or len(empreinte) <= INDEX_STORE:
        return empreinte
    store = empreinte[INDEX_STORE]
    if not isinstance(store, tuple) or len(store) != 5:
        return empreinte
    generation = store[4]
    statut = generation[0] if isinstance(generation, tuple) and generation else generation
    return empreinte[:INDEX_STORE] + ((store[0], store[1], statut),) + empreinte[INDEX_STORE + 1:]


def differer(ancienne: Any, nouvelle: Any, statut: str) -> dict[str, Any] | None:
    """La valeur en cache, datée `differe: True`, si le recalcul peut attendre ; None s'il faut recalculer.

    La garde `statut == "ok"` est REDONDANTE avec l'égalité membre à membre qui suit : l'ancienne empreinte a
    été prise sur un store ok, et le statut y est deux fois (membre `store_status` et premier champ de la
    génération). Elle reste pour la lecture ; un mutant qui ne retire qu'elle ne change rien, d'où M9, qui
    retire les trois (verdict plan-critic 2/8, réserve C6, SPECS S-01M5W0XEY93PW4DYC1FNRADSNP)."""
    valeur = _etat["valeur"]
    if statut != "ok" or valeur is None or valeur.get("source") != "sqlite" or ancienne is None:
        return None
    if _sans_donnees(ancienne) != _sans_donnees(nouvelle):
        return None
    duree, debut = _etat["duree"], _etat["debut"]
    if duree is None or duree < SEUIL_S or _horloge() >= debut + FACTEUR * duree:
        return None
    _etat["differe"] = True  # arme `jeton()` : l'échéance franchie changera la clé du transport
    return {**valeur, "fraicheur": {**valeur["fraicheur"], "differe": True}}


def servir(empreinte: Any, statut: str) -> dict[str, Any] | None:
    """Empreinte inchangée : la valeur en cache (mémo) ; dans la fenêtre : la valeur différée ; sinon None.
    Un différé en cours qui n'est plus servi FINIT ici : `_echeances` avance, comme `jeton()` l'annonçait."""
    global _echeances
    if _etat["valeur"] is not None and _etat["empreinte"] == empreinte:
        return _etat["valeur"]
    differee = differer(_etat["empreinte"], empreinte, statut)
    if differee is None and _etat["differe"]:
        _echeances += 1
        _etat["differe"] = False
    return differee


def top() -> float:
    """Début d'un calcul, sur l'horloge monotone injectable."""
    return _horloge()


def dater(valeur: dict[str, Any], empreinte: Any, debut: float) -> dict[str, Any]:
    """Date une valeur OK et la met en cache avec son empreinte et sa durée ; jamais appelé sur un dégradé."""
    fin = _horloge()
    duree = max(0.0, fin - debut)
    maintenant = _mur()
    attente = max(0.0, debut + FACTEUR * duree - fin) if duree >= SEUIL_S else 0.0
    valeur = {**valeur, "fraicheur": {
        "calcule_le": _iso(maintenant), "duree_s": round(duree, 3), "differe": False,
        "prochain_au_plus_tot": _iso(maintenant + timedelta(seconds=attente))}}
    _etat.update(valeur=valeur, empreinte=empreinte, debut=debut, duree=duree)
    return valeur


def jeton() -> int:
    """Part de canal B dans la clé du transport : le nombre de différés FINIS (`_echeances`, monotone, jamais
    remis à zéro par `oublier`), plus 1 dès qu'un différé en cours a franchi son échéance — l'annonce de celui
    que la construction suivante va finir dans `servir`. Trois propriétés, chacune témoignée :
      * au repos et à l'ouverture d'un différé, il ne bouge pas : la clé du transport est prise AVANT la
        construction, un jeton qui bougerait à chaque calcul reconstruirait une fois de trop ;
      * l'échéance franchie le change pour TOUTES les variantes du transport (une case et une clé chacune) ;
      * la construction qui finit le différé À SON ÉCHÉANCE retombe sur la valeur annoncée : pas de construction
        en trop. BORNE : un différé clos AVANT son échéance (identité, statut, base, spool qui changent) avance
        `_echeances` sans annonce, d'où une construction de plus par variante — la clé bougeait déjà.
    L'horloge n'y entre que par le drapeau d'échéance, jamais en continu."""
    if _etat["differe"] and _horloge() >= _etat["debut"] + FACTEUR * _etat["duree"]:
        return _echeances + 1
    return _echeances


def suite(store: Any) -> int | None:
    """L'id après lequel lire (lecture incrémentale), ou None : alors `oublier()` et relecture entière.
    Lève comme une lecture (`canal_b_bornes`) : l'appelant le fait dans le `try` de sa lecture. Le compteur
    `rewrite_generation` est lu ICI, AVANT la lecture : une réécriture pendant le flux relira tout ensuite."""
    reecriture_lue = store.canal_b_reecriture()  # LÈVE sur erreur : jamais un 0 qui passerait pour « rien »
    filigrane = _etat["filigrane"]
    if filigrane is not None and _etat["cumul"] is not None and store.status == "ok":
        premier, dernier, lignes, empreinte, reecriture, base = filigrane
        if (base == str(store.path) and reecriture == reecriture_lue
                and store.canal_b_bornes(dernier) == (premier, lignes, empreinte)):
            _etat["reecriture_lue"] = reecriture_lue
            return dernier
    oublier()
    _etat["reecriture_lue"] = reecriture_lue
    return None


def cumuler(lot: tuple[list[Any], list[Any], int, int], store: Any) -> tuple[list[Any], list[Any], int, int]:
    """Ajoute le lot d'un flux COMPLET au cumul et avance le filigrane depuis `store.canal_b_lu` ; rend les
    totaux `(census, records, rows_read, malformed)`. Un `canal_b_lu` absent (lecture inconnue) ne laisse
    aucun filigrane : le prochain appel relit tout."""
    census, records, rows_read, malformed = lot
    cumul, filigrane = _etat["cumul"], _etat["filigrane"]
    if cumul is None:
        cumul, filigrane = (census, records, rows_read, malformed), None
    else:
        cumul[0].extend(census)
        cumul[1].extend(records)
        cumul = (cumul[0], cumul[1], cumul[2] + rows_read, cumul[3] + malformed)
    lu = getattr(store, "canal_b_lu", None)
    reecriture, base = _etat.get("reecriture_lue"), str(store.path)
    if lu is None or reecriture is None:
        filigrane = None
    elif lu[2]:  # `(premier, dernier, lignes, line_hash du dernier)` : le hash nomme la ligne, l'id seul non
        premier, lignes = (lu[0], lu[2]) if filigrane is None else (filigrane[0], filigrane[2] + lu[2])
        filigrane = (premier, lu[1], lignes, lu[3], reecriture, base)
    elif filigrane is not None:
        filigrane = filigrane[:4] + (reecriture, base)
    _etat.update(cumul=cumul, filigrane=filigrane)
    return cumul
