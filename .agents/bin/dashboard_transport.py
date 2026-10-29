#!/usr/bin/env python3
"""Le TRANSPORT de `/api/snapshot` (T-01M4XR9ESWKJ8G545AJBJQNC7Q, E-36 vague 0).

Le CONTENU reste celui de `dashboard.build_snapshot`, inchangé ; ce module décide seulement QUAND il est
reconstruit et COMMENT il voyage. `dashboard.py` n'en garde qu'une table de poignées (`_SNAPSHOT_SOURCES`)
et un appel de dispatch — le modèle de `dashboard_handoff.py`.

MESURÉ AVANT (copie du store réel tenue ouverte comme par le démon, corps de 10 Mo) : chaque GET
re-sérialisait le corps (0,19 s, mémos frappés) et l'envoyait sans gzip ; une ligne de spool pas encore
ingérée reconstruisait canal B pour rien (4,4 s), puis le tick qui l'ingérait le reconstruisait encore
(4,3 s) ; aucun 304 n'existait ; six lectures simultanées (T-01M4TH6H6P) construisaient six fois.

LES CINQ GESTES.
  1. UNE CONSTRUCTION PAR CLÉ, sous le verrou du mémo : une requête qui arrive pendant une construction
     attend celle-ci et en reçoit les octets. La clé se calcule DANS le verrou, après `avant_cle()` : un
     test hors verrou laisserait deux fils voir la même clé périmée et construire tous les deux.
  2. LA CLÉ = (variante, avant_cle(), date UTC, empreinte()). `empreinte` vient de `dashboard.py` et
     observe chaque entrée que lit `build_snapshot` (`empreinte_snapshot` ; l'autorité de « chaque » est le
     témoin du banc, borné aux fichiers OUVERTS sur une copie de l'arbre réel : une sonde d'existence
     (`is_dir`, `exists`) et une entrée absente de cet arbre n'y sont pas vues), `late` (il vieillit avec
     l'horloge, jamais avec un fichier) et `dropped_foreign`, gelé à 0 depuis T-00000084, gardé pour le jour
     où il remonte. La date UTC y est parce que la ligne de tarif en vigueur se choisit
     au jour. `variante` est le contrat de réponse, et le mémo tient UNE CASE PAR VARIANTE, {1, 2} et rien
     d'autre (ValueError) : la 1 est le contrat servi, la 2 (`?contrat=2`, corps allégé) arrive avec
     T-01M51Q7GJ1B6315SFKNDAAE2P0 (ex-lot D) ; deux clients de deux contrats n'évincent jamais le gabarit
     l'un de l'autre.
     `avant_cle` est un crochet GARDÉ, inutilisé à ce jour : appelé sous le verrou AVANT la clé, sa valeur
     de retour ENTRE dans la clé. Vide par défaut.
  3. UN GABARIT EN MÉMO : `serialiser` et le deflate une fois par clé, jamais par GET. `serialiser` encode
     PAR MORCEAUX (`JSONEncoder.iterencode`, octets identiques à `json.dumps`) : `json.dumps` de la charge
     entière bâtissait une chaîne de la taille du corps avant ses octets UTF-8, et le footprint du démon
     montait à chaque reconstruction (mesuré par le plan de T-01M4XMQ1QC, spool sans ingestion : 319 → 951 Mo
     en 20 ; par morceaux : 308 → 314). Le prix, une fois par CONSTRUCTION sous le verrou du mémo, jamais
     par GET — mesuré sur le corps réel (10,5 Mo, Python 3.14.7, passe de correction de la revue de clôture) :
     l'encodeur Python pur (`iterencode` sans `_one_shot`), 84 ms contre 35 pour `json.dumps` (+49 ms, ×2,4),
     et un pic transitoire de 75 Mo contre 52 (×1,4 ; la liste de TOUS les morceaux, que `b"".join`
     matérialise avant de joindre) ; sur une charge synthétique de petits conteneurs (14,7 Mo), ×4-5 en CPU et
     ×3 en pic. L'accumulation dans un `bytearray` (pic 21 Mo, octets identiques) est MESURÉE ET REFUSÉE :
     elle rouvre la rétention (même rejeu, copie fraîche du store : 289 → 341 Mo en 20, pente ~2,6 Mo par
     construction, deux fois ; le join : 294 → 309, plat dès la 2e). Le gzip n'est SERVI qu'au client dont
     `Accept-Encoding` le nomme avec un q non nul.
  4. RIEN DE CE QUE L'ÉCRAN AFFICHE COMME VIVANT N'EST FIGÉ (B1 de l'exec-critic, décision orchestrateur) :
     les champs `vivant` (`generated_at`, tout `ingestion` — la pastille de Header.jsx, l'horodatage de
     Board.jsx) sont des MARQUES dans le gabarit, relues et greffées à CHAQUE envoi. Ils n'entrent pas dans
     la clé (exclu par T-00000615, event_store.py:1472-1474 : un tick les bouge toutes les 5 s). Le gzip
     s'ASSEMBLE : segments fixes déjà compressés, chacun clos sur une frontière d'octet (`Z_SYNC_FLUSH`), plus
     le deflate des petites greffes, puis l'en-tête et le CRC de la RFC 1952 — aucun envoi ne recompresse
     les 10 Mo.
  5. ETag/304 : un validateur FAIBLE sur le GABARIT SEUL (son empreinte), le même pour les deux codages
     (`Vary: Accept-Encoding`), comparé faiblement (RFC 9110 §13.1.2). Tiré des OCTETS et non de la clé :
     un démon redémarré ne répond jamais 304 à un corps qu'un code plus ancien a bâti des mêmes entrées. Les
     valeurs greffées n'y entrent pas (`generated_at` bouge chaque seconde : au repos, un sondage ne serait
     jamais revalidé) ; elles voyagent dans l'en-tête `X-Snapshot-Vivant`, sur le 200 COMME sur le 304 : un
     objet JSON ASCII compact dont chaque clé est un champ vivant DE TÊTE du corps
     (`{"generated_at":…,"ingestion":{…}}`), que le client greffe sur le corps qu'il a mémorisé quand il
     reçoit un 304 (lot B de T-01M4XMQ1QC, `api.js`). Le geste 4 tient donc sur le 304 aussi : rien de vivant
     n'est figé. Garde : un en-tête de plus de `VIVANT_MAX` (8 Kio), ou un champ vivant qui n'est pas de tête
     (un objet de tête ne saurait le greffer sans écraser ses frères) — ni en-tête ni 304, un 200 entier et
     greffé. Le corps du 200 porte toujours ses greffes : un client qui ignore l'en-tête reste juste.

CE QUI RESTE CELUI DE LA CONSTRUCTION, dit plutôt que sous-entendu : `views_meta` (`build_ms`, `cached`)
décrit la construction qui a produit ce corps, et `views.coverage.ingestion` reste celui du mémo des vues,
comme avant ce module — aucune vue ne l'affiche.

CACHE-CONTROL : `private, no-cache` (delta S-01M4XXZ8CP3), UN SEUL pour tous les contrats de la route,
sur le 200 comme sur le 304 ; épinglé par `test_dashboard.py::test_cache_control_is_bounded_to_the_projects_route`.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import struct
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Hashable, Mapping

# L'UNIQUE Cache-Control de `/api/snapshot`, tous contrats confondus (docstring).
CACHE_CONTROL: str | None = "private, no-cache"
GZIP_NIVEAU = 6
# RFC 1952 : deflate, aucun drapeau, mtime 0 (des octets stables d'un envoi à l'autre), OS inconnu.
_ENTETE_GZIP = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
# Les contrats de réponse servis, une case de mémo chacun (geste 2) ; toute autre variante : ValueError.
VARIANTES: tuple[int, ...] = (1, 2)
# Les champs vivants du moment, en en-tête (geste 5) ; au-delà de VIVANT_MAX octets : ni en-tête ni 304.
ENTETE_VIVANT = "X-Snapshot-Vivant"
VIVANT_MAX = 8 * 1024

# Les fichiers que `build_snapshot` lit et que `snapshot_fingerprint` (vues + board) n'observe pas : le badge
# (`_read_project`) et la grille de tarifs (`read_model_rates`). Relevés par le témoin d'audit du banc. Puis le
# dernier bilan de setup (`read_setup_bilan`, son `SETUP_BILAN_REL`), T-01M5A1244ZHSSA8RPCZYDJ49XE.
FICHIERS_HORS_VUES: tuple[tuple[str, ...], ...] = (
    (".agents", "state", "project.json"),
    (".agents", "ref", "MODEL_RATES.json"),
    (".agents", "state", "local", "setup-bilan.json"),
)
# Les lots d'une sauvegarde du board inachevée : `tasks_stockage._lire_lots` les superpose au board lu. Le
# témoin d'audit ne les voit pas (`is_dir()` d'abord, rien d'ouvert quand le dossier manque) : témoin dédié.
DOSSIERS_HORS_VUES: tuple[tuple[str, ...], ...] = ((".agents", "state", "local", "sync_outbox_lots"),)


@dataclass(frozen=True)
class Entree:
    """Un GABARIT mémorisé : les segments fixes du corps JSON autour des champs vivants, le deflate brut de
    chacun (tous clos par `Z_SYNC_FLUSH`, le dernier final), les chemins de ces champs dans l'ordre du corps,
    et l'empreinte du gabarit. Sans champ vivant : un seul segment, le corps entier."""
    segments: tuple[bytes, ...]
    deflates: tuple[bytes, ...]
    chemins: tuple[tuple[str, ...], ...]
    empreinte: bytes


@dataclass(frozen=True)
class Rendu:
    """UN envoi : les morceaux du corps (gabarit + greffes, jamais recollés pour la socket), leur taille,
    les greffes sérialisées, l'ETag faible — celui du gabarit SEUL — et `vivant`, la valeur de l'en-tête
    `X-Snapshot-Vivant` (None : ni en-tête ni 304, geste 5)."""
    morceaux: tuple[bytes, ...]
    taille: int
    greffes: tuple[bytes, ...]
    etag: str
    vivant: str | None

    @property
    def corps(self) -> bytes:
        return b"".join(self.morceaux)


@dataclass
class Case:
    """La case d'UNE variante dans le mémo : sa clé et son gabarit, posés ensemble après une construction."""
    cle: tuple | None = None
    entree: Entree | None = None


class MemoCorps:
    """UNE case par variante (`VARIANTES`) et UN verrou par instance de serveur (`UIHTTPServer.snapshot_memo`) :
    un serveur de banc démarre froid, et deux serveurs d'un même processus ne partagent jamais un corps.
    `constructions` compte les constructions de TOUTES les cases."""

    def __init__(self) -> None:
        self.verrou = threading.Lock()
        self.cases: dict[int, Case] = {variante: Case() for variante in VARIANTES}
        self.constructions = 0

    def case(self, variante: Hashable) -> Case:
        """La case de `variante` ; toute variante hors de `VARIANTES` (un booléen compris) lève ValueError."""
        if type(variante) is not int or variante not in self.cases:
            raise ValueError(f"variante de contrat inconnue : {variante!r} (servies : {VARIANTES})")
        return self.cases[variante]


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def cle_du_corps(variante: Hashable, jeton: Any, jour: str, empreinte: tuple) -> tuple:
    """La clé du corps mémorisé ET de son ETag : (variante, retour d'`avant_cle`, date UTC, empreinte)."""
    return (variante, jeton, jour, empreinte)


def _deflate(donnees: bytes, *, final: bool) -> bytes:
    """Deflate BRUT (sans en-tête zlib) d'un segment, avec SON compresseur : aucune référence ne traverse
    une frontière, et `Z_SYNC_FLUSH` clôt sur un octet entier — des segments ainsi produits se concatènent en
    UN flux deflate valide (le procédé de pigz), dont seul le dernier bloc est final."""
    compresseur = zlib.compressobj(GZIP_NIVEAU, zlib.DEFLATED, -15)
    return compresseur.compress(donnees) + compresseur.flush(zlib.Z_FINISH if final else zlib.Z_SYNC_FLUSH)


def _poser(racine: Any, chemin: tuple[str, ...], valeur: Any) -> Any:
    """Copie de `racine` dont la feuille `chemin` vaut `valeur`. Les objets d'origine ne sont JAMAIS modifiés :
    ils peuvent appartenir à un mémo interne (canal B, vues). None si un maillon manque ou n'est pas un dict :
    ce contrat ne porte pas ce champ, il n'est pas greffé (et rien n'est ajouté)."""
    if not isinstance(racine, dict) or chemin[0] not in racine:
        return None
    if len(chemin) == 1:
        return {**racine, chemin[0]: valeur}
    enfant = _poser(racine[chemin[0]], chemin[1:], valeur)
    return None if enfant is None else {**racine, chemin[0]: enfant}


def serialiser(charge: Any) -> bytes:
    """Les octets UTF-8 de `json.dumps(charge, ensure_ascii=False)`, encodés PAR MORCEAUX (geste 3) : aucune
    chaîne de la taille du corps n'est jamais bâtie. Le seul encodeur de la charge dans `gabarit`. Son prix
    (CPU, pic transitoire de la liste des morceaux) est au geste 3, comme la raison de ne PAS accumuler
    dans un `bytearray` : mesuré, il rouvre la rétention."""
    return b"".join(c.encode("utf-8") for c in json.JSONEncoder(ensure_ascii=False).iterencode(charge))


def corps_degrade(exc: BaseException) -> dict[str, Any]:
    """Le corps BORNÉ servi quand la charge ne se sérialise pas : le TYPE de l'exception seul, jamais son
    message (il recopierait la donnée fautive)."""
    return {"status": "degraded",
            "reason": f"snapshot non sérialisable : {type(exc).__name__} — section fautive non identifiée"}


def gabarit(charge: dict[str, Any], champs_vivants: tuple[tuple[str, ...], ...] = ()) -> Entree:
    """Sérialise `charge` UNE fois, chaque champ vivant remplacé par une marque aléatoire (un NUL ne survit
    jamais en clair dans du JSON : la marque ne peut pas être une donnée), puis découpe aux marques.

    GARDE GÉNÉRALE, de n'importe quelle source : une chaîne à substitut UTF-16 isolé (`UnicodeEncodeError`) ou
    une imbrication que l'encodeur pur Python ne réécrit pas (`RecursionError`) rend le gabarit de
    `corps_degrade`, jamais une exception qui tuerait `/api/snapshot` à chaque GET. Ici, pas dans `serialiser` :
    `etat_projection` et `dashboard_routes_etat` l'appellent aussi, et un corps de repli y serait faux en silence."""
    jeton, marques = secrets.token_hex(8), {}
    for i, chemin in enumerate(champs_vivants):
        marque = f"\x00vivant:{jeton}:{i}\x00"
        posee = _poser(charge, chemin, marque)
        if posee is not None:
            charge, marques[chemin] = posee, json.dumps(marque, ensure_ascii=False).encode("utf-8")
    try:
        corps = serialiser(charge)
    except (RecursionError, UnicodeEncodeError) as exc:
        return gabarit(corps_degrade(exc))
    places = sorted((corps.index(marque), chemin, marque) for chemin, marque in marques.items())
    segments, debut = [], 0
    for position, _chemin, marque in places:
        segments.append(corps[debut:position])
        debut = position + len(marque)
    segments.append(corps[debut:])
    dernier = len(segments) - 1
    return Entree(tuple(segments), tuple(_deflate(s, final=i == dernier) for i, s in enumerate(segments)),
                  tuple(chemin for _p, chemin, _m in places), hashlib.sha256(b"\x00".join(segments)).digest())


def _entete_vivant(entree_: Entree, valeurs: Mapping[tuple[str, ...], Any]) -> str | None:
    """La valeur de `X-Snapshot-Vivant` : objet JSON ASCII compact {champ de tête: valeur} (aucun CR/LF ni
    octet hors ASCII : une valeur d'en-tête sûre). None — ni en-tête ni 304 — si un champ vivant n'est pas
    de tête ou si l'objet dépasse `VIVANT_MAX` octets (geste 5)."""
    if any(len(chemin) != 1 for chemin in entree_.chemins):
        return None
    vivant = json.dumps({chemin[0]: valeurs.get(chemin) for chemin in entree_.chemins},
                        ensure_ascii=True, separators=(",", ":"))
    return vivant if len(vivant) <= VIVANT_MAX else None


def rendre(entree_: Entree, valeurs: Mapping[tuple[str, ...], Any]) -> Rendu:
    """Greffe les valeurs VIVANTES du moment dans le gabarit ; l'ETag est celui du gabarit SEUL, les valeurs
    du moment partent aussi dans l'en-tête vivant (geste 5)."""
    greffes = tuple(json.dumps(valeurs.get(chemin), ensure_ascii=False).encode("utf-8")
                    for chemin in entree_.chemins)
    morceaux = [entree_.segments[0]]
    for greffe, segment in zip(greffes, entree_.segments[1:]):
        morceaux += [greffe, segment]
    etag = 'W/"' + entree_.empreinte.hex()[:32] + '"'
    return Rendu(tuple(morceaux), sum(len(m) for m in morceaux), greffes, etag, _entete_vivant(entree_, valeurs))


def assembler_gzip(entree_: Entree, rendu: Rendu) -> bytes:
    """Le membre gzip de CET envoi : en-tête, deflates du gabarit entrelacés avec celui des greffes, CRC-32
    et taille (RFC 1952) calculés sur les morceaux réels. Seules les greffes sont compressées ici."""
    flux = [entree_.deflates[0]]
    for greffe, deflate in zip(rendu.greffes, entree_.deflates[1:]):
        flux += [_deflate(greffe, final=False), deflate]
    crc = 0
    for morceau in rendu.morceaux:
        crc = zlib.crc32(morceau, crc)
    return _ENTETE_GZIP + b"".join(flux) + struct.pack("<II", crc, rendu.taille & 0xFFFFFFFF)


def entree(memo: MemoCorps, *, construire: Callable[[Hashable], dict[str, Any]],
           empreinte: Callable[[], tuple], variante: Hashable = 1,
           avant_cle: Callable[[], Any] | None = None,
           maintenant: Callable[[], datetime] | None = None,
           champs_vivants: tuple[tuple[str, ...], ...] = ()) -> Entree:
    """Le gabarit de la clé COURANTE dans la case de `variante`, construit au plus une fois par clé.

    La case d'abord (`memo.case` : une variante inconnue lève ValueError avant tout appel). Ordre sous le
    verrou : `avant_cle()`, PUIS la date et l'empreinte, PUIS la comparaison, PUIS — seulement si la clé a
    bougé — `construire(variante)` et le gabarit, PUIS la clé est posée : une exception de `construire`
    laisse donc la case (gabarit ET clé) intacte et libère le verrou (`with`)."""
    horloge = maintenant if maintenant is not None else _maintenant
    case = memo.case(variante)
    with memo.verrou:
        jeton = avant_cle() if avant_cle is not None else None
        jour = horloge().astimezone(timezone.utc).date().isoformat()
        cle = cle_du_corps(variante, jeton, jour, empreinte())
        if case.entree is None or case.cle != cle:
            case.entree = gabarit(construire(variante), champs_vivants)
            case.cle = cle
            memo.constructions += 1
        return case.entree


def accepte_gzip(entete: str | None) -> bool:
    """Vrai seulement si `Accept-Encoding` NOMME `gzip` (ou `x-gzip`) avec un q non nul ; `*` ne suffit pas,
    pour qu'un `gzip;q=0, *` explicite ne reçoive jamais du gzip."""
    for element in (entete or "").split(","):
        codage, _, params = element.strip().partition(";")
        if codage.strip().lower() not in ("gzip", "x-gzip"):
            continue
        q = 1.0
        for param in params.split(";"):
            nom, _, valeur = param.strip().partition("=")
            if nom.strip().lower() == "q":
                try:
                    q = float(valeur.strip())
                except ValueError:
                    q = 0.0
        return q > 0.0
    return False


def etag_correspond(entete: str | None, etag: str) -> bool:
    """Comparaison FAIBLE d'`If-None-Match` (RFC 9110 §13.1.2) : `*`, ou une étiquette dont la partie opaque
    est celle d'`etag`, préfixe `W/` ignoré des deux côtés."""
    opaque = etag[2:] if etag.startswith("W/") else etag
    for etiquette in (entete or "").split(","):
        etiquette = etiquette.strip()
        if etiquette == "*" or (etiquette[2:] if etiquette.startswith("W/") else etiquette) == opaque:
            return True
    return False


def _entetes_communs(handler: Any, rendu: Rendu) -> None:
    handler.send_header("ETag", rendu.etag)
    handler.send_header("Vary", "Accept-Encoding")
    if rendu.vivant is not None:
        handler.send_header(ENTETE_VIVANT, rendu.vivant)
    if CACHE_CONTROL is not None:
        handler.send_header("Cache-Control", CACHE_CONTROL)
    # La même paire de durcissement que toute réponse JSON de ce serveur ; aucun en-tête CORS, jamais.
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")


def servir(handler: Any, *, construire: Callable[[Hashable], dict[str, Any]], empreinte: Callable[[], tuple],
           variante: Hashable = 1, avant_cle: Callable[[], Any] | None = None,
           maintenant: Callable[[], datetime] | None = None,
           vivant: Mapping[tuple[str, ...], Callable[[], Any]] | None = None) -> None:
    """Répond au GET déjà authentifié : 304 si `If-None-Match` porte l'ETag courant ET que l'en-tête vivant
    est servi (geste 5), sinon 200 avec le gabarit mémorisé et ses greffes du moment, gzippé si le client
    l'accepte ; l'en-tête vivant part sur l'un comme sur l'autre. `vivant` : chemin -> lecteur, chaque
    lecteur appelé à CHAQUE envoi, HORS du verrou, après le gabarit (la valeur la plus fraîche). L'écriture
    sur la socket a lieu hors du verrou aussi : un client lent ne retient jamais les autres. Sans
    `snapshot_memo` sur le serveur, un mémo jetable : correct, sans mémo."""
    memo = getattr(handler.server, "snapshot_memo", None)
    if not isinstance(memo, MemoCorps):
        memo = MemoCorps()
    lecteurs = dict(vivant or {})
    courante = entree(memo, construire=construire, empreinte=empreinte, variante=variante,
                      avant_cle=avant_cle, maintenant=maintenant, champs_vivants=tuple(lecteurs))
    rendu = rendre(courante, {chemin: lire() for chemin, lire in lecteurs.items()})
    if rendu.vivant is not None and etag_correspond(handler.headers.get("If-None-Match"), rendu.etag):
        handler.send_response(304)
        _entetes_communs(handler, rendu)
        handler.end_headers()
        return
    compresse = accepte_gzip(handler.headers.get("Accept-Encoding"))
    morceaux = (assembler_gzip(courante, rendu),) if compresse else rendu.morceaux
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(sum(len(m) for m in morceaux)))
    if compresse:
        handler.send_header("Content-Encoding", "gzip")
    _entetes_communs(handler, rendu)
    handler.end_headers()
    try:
        for morceau in morceaux:
            handler.wfile.write(morceau)
    except OSError:
        pass


def part_du_spool(repertoire: Path | None, statut_store: str, motif: str = "*.jsonl") -> tuple:
    """La part d'UN répertoire de spool dans la clé du mémo canal B (`dashboard._canal_b_fingerprint`).

    Le spool n'est la SOURCE de canal B que tant qu'aucune projection n'existe (`absent`) ; avec un store
    `ok` (ou tout autre statut) la section ne lit que la base, dont la clé porte déjà la génération de
    DONNÉES — une ligne écrite et pas encore ingérée, ou un fichier que l'ingesteur supprime une fois
    projeté, reconstruisait canal B pour rien (4,4 s mesurées). Sous `absent`, un fichier en ajout seul se
    reconnaît à `(nom, taille)` : son horodatage n'est jamais lu, aucune ligne n'entre sans octets."""
    if repertoire is None or statut_store != "absent":
        return ()
    try:
        candidats = sorted(repertoire.glob(motif))
    except OSError:
        return ()
    parts: list[tuple[str, int]] = []
    for chemin in candidats:
        try:
            parts.append((chemin.name, chemin.stat().st_size))
        except OSError:
            continue
    return tuple(parts)


def _fichier(chemin: Path | None) -> tuple:
    if chemin is None:
        return ("non résolu",)
    try:
        st = chemin.stat()
    except OSError:
        return (str(chemin), "absent")
    return (str(chemin), st.st_mtime_ns, st.st_size)


def _repertoire(chemin: Path) -> tuple:
    """`(nom, mtime_ns, taille)` de chaque `*.json` du dossier, trié ; dossier absent : `()`."""
    try:
        return tuple(sorted((p.name, *_fichier(p)[1:]) for p in chemin.glob("*.json")))
    except OSError:
        return ("illisible",)


def rejets_etrangers(store_mod: Any) -> Any:
    """`dropped_foreign`, que canal B affiche (`attribution_counters`), gelé à 0 depuis T-00000084, gardé pour
    le jour où il remonte : compteur en mémoire, aucun fichier ne bougerait quand il monte. Lu par le module
    `event_store` de `dashboard.py`, jamais par un second chargement (qui lirait 0). Jamais d'exception : None
    entre alors dans la clé."""
    try:
        with store_mod.open_store(create=False) as store:
            return store.attribution_counters().get("dropped_foreign", 0)
    except Exception:  # noqa: BLE001 - une clé ne lève jamais
        return None


def empreinte_snapshot(racine: Path, sources: Mapping[str, Callable[..., Any]]) -> tuple:
    """Chaque entrée de `build_snapshot(racine)`, en stat() et lectures brèves — jamais un octet de store.

    `sources` sont les poignées PROPRES de `dashboard.py` (`_SNAPSHOT_SOURCES`). L'empreinte du store est
    prise EN PREMIER, avant toute autre lecture (octies F1) : un tick entre les deux coûte une reconstruction,
    jamais un corps périmé. Au-delà de `snapshot_fingerprint` (vues + board), le témoin d'audit du banc a
    relevé `FICHIERS_HORS_VUES` et le fichier d'identité contre lequel canal B attribue ; s'y ajoutent les
    lots de board en suspens (`DOSSIERS_HORS_VUES`, témoin dédié) et `dropped_foreign`, gelé à 0 depuis
    T-00000084, gardé pour le jour où il remonte. `canal_b` (T-01M5T5G6MR) : le jeton du recalcul borné, dont
    l'échéance franchie reconstruit sans ligne neuve ; absent des sources d'un appelant, il vaut None."""
    store_fp = sources["store_fingerprint"]()
    events_dir, otel_dir = sources["events_dir"](), sources["otel_dir"]()
    ingestion = sources["ingestion"]()
    return (
        sources["inputs"](racine, events_dir, otel_dir, store_fp),
        tuple(_fichier(racine.joinpath(*rel)) for rel in FICHIERS_HORS_VUES),
        tuple(_repertoire(racine.joinpath(*rel)) for rel in DOSSIERS_HORS_VUES),
        _fichier(sources["identity_path"]()),
        sources["dropped_foreign"](),
        ingestion.get("late") if isinstance(ingestion, dict) else None,
        sources.get("canal_b", lambda: None)(),
    )
