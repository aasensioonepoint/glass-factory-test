#!/usr/bin/env python3
"""Les routes paginées des JOURNAUX du dashboard (lot D de T-01M51Q7GJ1B6315SFKNDAAE2P0).

`/api/specs`, `/api/lecons`, `/api/recherche`, et le `contrat` de `/api/snapshot`. `dashboard.py` n'en garde que
la table (`ROUTES`, jointe à `_ALLOWED_UI_PATHS`), un `elif` de dispatch et la lambda du snapshot qui suit la
variante — le modèle de `dashboard_transport.py` et de `dashboard_handoff.py`.

LA GRAMMAIRE EST FERMÉE (annexe A2.3, figée au journal du parent par S-01M53C814Z, S-01M53E5XBA, S-01M53BTDZA) :
un paramètre inconnu, répété, vide, hors domaine ou hors borne rend 400 — jamais une liste vide muette.
  - `/api/specs` : task, kind (plusieurs, séparés par des virgules, aucun vide), dernier=1, avec=plan,
    ordre ∈ {recent, store}, q, autour, offset, limit. `open` est RETIRÉ (aucun consommateur) : 400.
  - `/api/lecons` : category ∈ {constraint, decision, lesson}, status ∈ {archived}, q, autour, offset, limit.
  - `/api/recherche` : aucun paramètre. `/api/snapshot` : contrat ∈ {absent, 1, 2}, rien d'autre.
  - limit, offset : `[0-9]{1,10}` ASCII ; limit ∈ [1, 200], défaut 25 ; offset ≤ 10^9, défaut 0 ; `autour` et
    `offset` ensemble : 400.
LES FILTRES, DANS CET ORDRE : task → kind → avec → dernier → q. `avec=plan` lit le store ENTIER (les tâches qui
ont au moins un plan, quels que soient les autres filtres) ; `dernier=1` garde, par (task, kind), la première de
l'ordre `recent` ; `q` est une SOUS-CHAÎNE LITTÉRALE du foin plié (`instr`, jamais LIKE : `_` et `%` ne sont pas
des jokers) — id/task/kind/title pour SPECS, id/title/text/text_preview/tags/related pour LEDGER (`foin`).
L'ORDRE EST RENDU PAR LE SERVEUR : `recent` (défaut) = tier DESC, num DESC, valeur DESC, rang ASC — une égalité
garde l'ordre du store ; `store` = rang ASC. `/api/lecons` : toujours `recent`, archivées HORS de la liste sauf
sous `status=archived` ; `counts` sur le store ENTIER, sans `q` ni `category`. Sous `autour=<id>` : la page qui
contient l'id, `rang` (sa place dans la liste filtrée, None si absente) et `trouve` ; ces deux clés n'existent
que sous `autour`.

DEUX LECTURES, UNE RÉPONSE. `etat_projection.lire(racine)` rend une connexion à une base À JOUR, dans une
transaction de lecture que ce module FERME : `source: "base"`. Sinon — base absente, périmée, une source
`degraded` (réserve C1), `cadre.paths` introuvable — ou quand une requête sur la base lève (réserve C8, toute
classe) : la lecture DIRECTE des journaux par leurs propriétaires (`specs.load`, `ledger.load`),
`source: "direct"`, avec les MÊMES fonctions que la projection — `rangement` (le tri), `foin` et `plier` (`q`),
`_texte` (le texte d'un champ, A2.1) — : la parité base/direct est témoignée sur les journaux réels. Une source
illisible en direct rend une page vide qui le DIT (`sources[].statut`, `raison` de `_safe_load_store`), et
`sources` porte TOUJOURS les deux lignes, SPECS puis LEDGER (exigence de F, S-01M53BTDZA). `/api/recherche`
rend `{decisions, lecons, stores, empreinte}` (S-01M53C814Z (4)) : `stores` a la forme de `sources`, et
`empreinte` est celle que porte `journaux.empreinte` du snapshot (`empreinte_journaux`).

ETag (A2.3) : sha256 de l'empreinte des sources prise AVANT toute lecture, de la requête canonique triée et de
l'empreinte du code que passe `dashboard.py` (prise une fois, à son chargement) — FAIBLE, la même pour les deux
codages ; 304 quand `If-None-Match` la porte. Une réponse dont la source de la ROUTE (SPECS pour `/api/specs`,
LEDGER pour `/api/lecons`, les deux pour `/api/recherche`) n'est pas `ok` ne porte PAS d'ETag : une panne de lecture
passagère, sans fichier qui bouge, ne doit jamais être revalidée en 304 indéfiniment — et la panne de l'AUTRE
journal n'ôte pas son 304 à une route qui ne le lit pas. Une empreinte des sources qui lève (avis LOW) ne fait
tomber aucune réponse : les routes partent sans ETag, le snapshot porte l'empreinte constante `indisponible`. Le
champ `source` n'entre pas dans l'ETag : base et direct rendent les mêmes données (parité), il dit seulement d'où.
`/api/recherche` (~2,1 Mo bruts mesurés) est MÉMORISÉ par ETag dans `MemoRecherche`, un par serveur : sans
changement des sources ni du code, un GET resert les mêmes octets (et leur gzip) sans relire ni resérialiser. Sa
borne est celle de la décision S-01M530QPV2 (a), `RECHERCHE_BORNE_OCTETS` : au-delà, le journal du démon le dit
et le plan se reprend (fil du banc sur les journaux réels). La raison d'une source illisible en direct ne porte
jamais le chemin absolu de la racine (remplacé par `.`).
En-têtes : `Cache-Control: no-store`, nosniff, no-referrer, `Vary: Accept-Encoding`, gzip au seul client qui le
nomme (`accepte_gzip`), AUCUN en-tête CORS. Un 400 passe par `_reject` du handler, la forme de tout refus.

LECTURE SEULE. Aucun handler n'écrit (SYM-01663) : ce module n'appelle ni `rafraichir` ni la boucle du démon,
seul écrivain de la base, et n'émet que des SELECT. Aucun nom de fichier de magasin n'est écrit ici (cliquet C3) :
les noms sont ceux des sources, et les chemins restent à leurs propriétaires.

`/api/livrables?task=<T>` (B3, T-01M54GENAAVDSBX5QWJV9PKEDP, annexe § 2) : les livrables Markdown d'UNE tâche, ni
SQL ni journal. `task` une fois, `re.fullmatch` de `T-[0-9A-Z]{3,26}`, sinon 400. Liste FERMÉE : `docs/tasks/<T>.md`
et `docs/tasks/<T>-<suffixe>.md` (suffixe `[A-Za-z0-9._-]{1,80}`), par un `glob` NON récursif. `docs/tasks` présent
mais illisible (`os.access` R+X refusé — `glob` avalerait EACCES en une liste vide) rend `degraded`, jamais `absent`.
Une entrée qui n'est pas un fichier régulier À LIEN UNIQUE (`lstat` : lien symbolique, dossier, FIFO, et lien DUR,
`st_nlink > 1`, qui servirait un fichier d'ailleurs sous un nom d'ici) ou dont le parent résolu n'est pas
`docs/tasks` est ÉCARTÉE et DITE (`degraded`). Ouverture `os.open(O_RDONLY | O_NONBLOCK | O_NOFOLLOW)` puis `fstat` :
une FIFO ne bloque jamais le handler, un lien glissé après le listage lève (ELOOP), un fichier devenu non régulier ou
multi-lié lève. Lecture BORNÉE : au plus `BORNE_DOC + 1` octets par document, `BORNE_TOTALE` en tout (un document
que le RESTE du budget coupe sous `BORNE_DOC` le dit : « <nom> : tronqué à <n> octets par la borne totale de la
tâche » ; au-delà : documents sans texte, `tronque`, raison dite), `DOCUMENTS_MAX` documents ; décodage UTF-8
`backslashreplace`, un caractère coupé par la borne retiré, puis le TEXTE coupé à `BORNE_DOC` caractères (un octet
invalide en rend quatre, `\\xNN` : sans cette coupe, 2 Mio lus se sérialisaient en plus de 3 Mo), `tronque`, raison
dite. PIRE CAS SÉRIALISÉ, BORNÉ MAIS NON RAMENÉ À 2 Mio : un contrôle ASCII (NUL, ESC…) est de l'UTF-8 valide, que
JSON écrit `\\u00NN`, six octets pour un — 2 Mio de NUL lus se servent en ~12,6 Mo en clair (~19 Ko en gzip, au
client qui le nomme) ; `ensure_ascii=False` (transport) garde un caractère non ASCII à sa taille UTF-8. Une réponse
qui ne se sérialise pas (un substitut isolé dans le texte) part `degraded`, sans documents, jamais en connexion
coupée. Corps
`{task, statut: ok|absent|degraded, raison,
documents: [{nom, genre, octets, mtime (ISO 8601 UTC), tronque, texte}]}`, ordre plan, annexe, critic-n, exec-critic-n,
LOT-*, puis le reste par nom. ETag faible sur `{nom: "mtime_ns:size"}` pris AVANT la lecture, émis SEULEMENT au
statut `ok` ; `absent` et `degraded` partent sans. Comme en A2.3, la revalidation précède la lecture : un document
rendu illisible sans que bouge son `mtime_ns:size` (un chmod) se revalide en 304 chez le client qui tient déjà
l'ETag, et seul le 200 suivant dit la panne. Une raison ne porte jamais de chemin absolu.
"""
from __future__ import annotations

import codecs
import datetime
import gzip
import hashlib
import importlib.util
import json
import logging
import os
import re
import stat
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple, Sequence

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


# La projection (lot C) — sa lecture, son empreinte et ses fonctions de rang et de foin, jamais son écrivain ;
# l'encodeur et l'en-tête gzip du transport ; les PROPRIÉTAIRES des journaux, pour la lecture directe.
_etat = _load_sibling("_routes_etat_projection", "etat_projection.py")
_transport = _load_sibling("_routes_etat_transport", "dashboard_transport.py")
_PROPRIETAIRES: dict[str, Any] = {"SPECS": _load_sibling("_routes_etat_specs", "specs.py"),
                                  "LEDGER": _load_sibling("_routes_etat_ledger", "ledger.py")}
# Le `text()` de format.js porté par C : la valeur des colonnes task, kind, category, status (A2.1).
_texte: Callable[[Any], str] = _etat._texte

ROUTE_LIVRABLES = "/api/livrables"
ROUTES: frozenset[str] = frozenset({"/api/specs", "/api/lecons", "/api/recherche", ROUTE_LIVRABLES})
# A2.3 telle que figée : la liste FERMÉE des paramètres de chaque route (+ `/api/livrables`, B3).
PARAMETRES: dict[str, tuple[str, ...]] = {
    "/api/specs": ("task", "kind", "dernier", "avec", "ordre", "q", "autour", "offset", "limit"),
    "/api/lecons": ("category", "status", "q", "autour", "offset", "limit"),
    "/api/recherche": (),
    ROUTE_LIVRABLES: ("task",),
}
CONTRATS: dict[str, int] = {"1": 1, "2": 2}
CATEGORIES: tuple[str, ...] = ("constraint", "decision", "lesson")
ORDRES: tuple[str, ...] = ("recent", "store")
LIMITE_DEFAUT, LIMITE_MAX, DECALAGE_MAX = 25, 200, 10 ** 9
CACHE_CONTROL = "no-store"
SOURCE_BASE, SOURCE_DIRECT = "base", "direct"
_ENTIER = re.compile(r"[0-9]{1,10}")  # `fullmatch` : ni signe, ni espace, ni fin de ligne, ni chiffre non ASCII
_ALLEGES = ("specs", "ledger")
_SOURCE_DE = {"/api/specs": "SPECS", "/api/lecons": "LEDGER"}
_RAISON_MAX = 300  # celle de `dashboard._safe_load_store` : la raison du direct est celle de la section du snapshot
EMPREINTE_INDISPONIBLE = "indisponible"
# Décision S-01M530QPV2 (a) : `/api/recherche` non paginée ACCEPTÉE jusqu'à ~5 Mo bruts ; au-delà, replanifier.
RECHERCHE_BORNE_OCTETS = 5 * 1000 * 1000
# `/api/livrables` (annexe § 2 de B3) : la forme d'une tâche, celle d'un suffixe, les bornes de lecture.
_TACHE = re.compile(r"T-[0-9A-Z]{3,26}")
_SUFFIXE = r"[A-Za-z0-9._-]{1,80}"
_CRITIQUE = re.compile(r"(exec-)?critic-([0-9]{1,9})")
BORNE_DOC = 512 * 1024
BORNE_TOTALE = 2 * 1024 * 1024
DOCUMENTS_MAX = 40
LIVRABLE_OK, LIVRABLE_ABSENT, LIVRABLE_DEGRADE = "ok", "absent", "degraded"
# Ni FIFO qui bloque (`O_NONBLOCK`), ni lien suivi (`O_NOFOLLOW`) ; `getattr` : ces drapeaux n'existent pas partout.
_OUVERTURE = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_BINARY", 0))
_BLOC_LECTURE = 64 * 1024

# ---------------------------------------------------------------------------
# Les requêtes sur la base : des LITTÉRAUX, paramètres liés par nom, aucun texte de la requête interpolé.
# ---------------------------------------------------------------------------
_SQL_SPECS = """
WITH f AS (
    SELECT id, rang, task, kind, tier, num, valeur, pli FROM specs
    WHERE (:task IS NULL OR task = :task)
      AND (:kinds IS NULL OR kind IN (SELECT value FROM json_each(:kinds)))
      AND (:avec IS NULL OR task IN (SELECT task FROM specs WHERE kind = 'plan'))
), d AS (
    SELECT id, rang, tier, num, valeur, pli,
           ROW_NUMBER() OVER (PARTITION BY task, kind ORDER BY tier DESC, num DESC, valeur DESC, rang ASC) AS n
    FROM f
)
SELECT id FROM d
WHERE (:dernier IS NULL OR n = 1) AND (:q IS NULL OR instr(pli, :q) > 0)
ORDER BY CASE WHEN :store IS NULL THEN 0 ELSE rang END, tier DESC, num DESC, valeur DESC, rang ASC
"""
_SQL_LECONS = """
SELECT id FROM journal_ledger
WHERE (CASE WHEN :archivees IS NULL THEN status <> 'archived' ELSE status = 'archived' END)
  AND (:category IS NULL OR category = :category)
  AND (:q IS NULL OR instr(pli, :q) > 0)
ORDER BY tier DESC, num DESC, valeur DESC, rang ASC
"""
_SQL_COMPTES = """
SELECT COALESCE(SUM(status <> 'archived'), 0),
       COALESCE(SUM(status <> 'archived' AND category = 'constraint'), 0),
       COALESCE(SUM(status <> 'archived' AND category = 'decision'), 0),
       COALESCE(SUM(status <> 'archived' AND category = 'lesson'), 0),
       COALESCE(SUM(status = 'archived'), 0)
FROM journal_ledger
"""
_SQL_CORPS = {
    "SPECS": "SELECT id, corps FROM specs WHERE id IN (SELECT value FROM json_each(?))",
    "LEDGER": "SELECT id, corps FROM journal_ledger WHERE id IN (SELECT value FROM json_each(?))",
}
_SQL_RECHERCHE = {
    "SPECS": "SELECT corps FROM specs WHERE kind = 'decision' ORDER BY rang",
    "LEDGER": "SELECT corps FROM journal_ledger WHERE status <> 'archived' ORDER BY rang",
}
_SQL_SOURCES = "SELECT nom, statut, raison FROM sources"


# ---------------------------------------------------------------------------
# La grammaire.
# ---------------------------------------------------------------------------

def refus(path: str, qs: Mapping[str, Sequence[str]]) -> str | None:
    """None si la requête (`parse_qs`, valeurs vides gardées) est dans la grammaire A2.3 de `path`, sinon la
    raison du 400. Ne lève jamais : `int` ne voit que dix chiffres ASCII au plus."""
    permis = PARAMETRES[path]
    for cle, valeurs in qs.items():
        if cle not in permis:
            return f"paramètre hors grammaire : {cle!r}"
        if len(valeurs) != 1:
            return f"paramètre répété : {cle}"
        if valeurs[0] == "":
            return f"valeur vide : {cle}"
    p = {cle: valeurs[0] for cle, valeurs in qs.items()}
    for cle in ("limit", "offset"):
        if cle in p and _ENTIER.fullmatch(p[cle]) is None:
            return f"{cle} hors grammaire"
    if "limit" in p and not 1 <= int(p["limit"]) <= LIMITE_MAX:
        return "limit hors borne"
    if "offset" in p and int(p["offset"]) > DECALAGE_MAX:
        return "offset hors borne"
    if path == ROUTE_LIVRABLES and _TACHE.fullmatch(p.get("task", "")) is None:
        return "task hors forme"  # `fullmatch` : `T-ABC\n` (`%0A`) est refusé, là où `match` + `$` l'accepterait
    if "autour" in p and "offset" in p:
        return "autour et offset ensemble"
    if "kind" in p and "" in p["kind"].split(","):
        return "kind vide"
    for cle, domaine in (("dernier", ("1",)), ("avec", ("plan",)), ("ordre", ORDRES), ("category", CATEGORIES),
                         ("status", ("archived",))):
        if cle in p and p[cle] not in domaine:
            return f"{cle} hors domaine"
    return None


def parametres(path: str, qs: Mapping[str, Sequence[str]]) -> dict[str, str] | None:
    """Les paramètres d'une requête DANS la grammaire (une valeur chacun), ou None : la requête rend 400."""
    if refus(path, qs) is not None:
        return None
    return {cle: valeurs[0] for cle, valeurs in qs.items()}


def variante(qs: Mapping[str, Sequence[str]]) -> int | None:
    """Le contrat de `/api/snapshot` : 1 sans paramètre ; sinon `contrat` SEUL, une fois, valant 1 ou 2 ; tout
    autre requête → None (400)."""
    if not qs:
        return 1
    if set(qs) != {"contrat"} or len(qs["contrat"]) != 1:
        return None
    return CONTRATS.get(qs["contrat"][0])


def alleger(snapshot: dict[str, Any], variante_: int) -> dict[str, Any]:
    """Le corps du contrat `variante_` : le 1 tel quel ; le 2 sans `specs` ni `ledger` (copie de surface : les
    autres sections, `journaux` compris, sont celles du 1 ; le corps du 1 n'est jamais muté)."""
    if variante_ == 2:
        return {cle: valeur for cle, valeur in snapshot.items() if cle not in _ALLEGES}
    return snapshot


def _hacher(empreintes: Mapping[str, str], code: str) -> str:
    canon = json.dumps([dict(sorted(empreintes.items())), code], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("ascii")).hexdigest()[:32]


def _empreintes(racine: Path) -> dict[str, str] | None:
    """`empreinte_sources`, ou None quand elle lève, quelle qu'en soit la classe : une empreinte indisponible ne
    fait jamais tomber une réponse (le snapshot en dépend sur ses deux contrats). La cause va au journal stderr."""
    try:
        return _etat.empreinte_sources(racine)
    except Exception as exc:  # noqa: BLE001 - avis LOW du lot D : jamais d'exception vers le handler
        _LOG.warning("EMPREINTE DES JOURNAUX INDISPONIBLE (%s: %s)", type(exc).__name__, exc)
        return None


def empreinte_journaux(racine: Any, code: str) -> str:
    """`journaux.empreinte` du snapshot (ses deux variantes) et `empreinte` de `/api/recherche` : l'empreinte des
    sources (`empreinte_sources`, `lstat` seuls) et du code servi. Elle bouge quand une route répondrait autre
    chose ; le client (lot E) relit ses pages sur elle et sur rien d'autre. Indisponible : la constante
    `EMPREINTE_INDISPONIBLE`, jamais une exception."""
    empreintes = _empreintes(Path(racine))
    return EMPREINTE_INDISPONIBLE if empreintes is None else _hacher(empreintes, code)


def etiquette(path: str, p: Mapping[str, str], empreintes: Mapping[str, str], code: str) -> str:
    """L'ETag faible d'une réponse : empreinte des sources prise AVANT la lecture, requête canonique triée, code."""
    canon = json.dumps([path, sorted(p.items()), dict(sorted(empreintes.items())), code],
                       ensure_ascii=True, separators=(",", ":"))
    return 'W/"' + hashlib.sha256(canon.encode("ascii")).hexdigest()[:32] + '"'


# ---------------------------------------------------------------------------
# Une réponse : la page, commune aux deux lectures.
# ---------------------------------------------------------------------------

def _reponse(rangs: list[Any], p: Mapping[str, str], *, ident: Callable[[Any], str],
             entrees: Callable[[list[Any]], list[Any]], source: str, sources: list[dict[str, Any]],
             counts: dict[str, int] | None) -> dict[str, Any]:
    """`rangs` est la liste FILTRÉE et ORDONNÉE (ids en base, lignes en direct) ; `entrees` rend les entrées
    brutes d'une tranche, dans son ordre."""
    limite = int(p.get("limit", LIMITE_DEFAUT))
    extra: dict[str, Any] = {}
    if "autour" in p:
        place = next((i for i, x in enumerate(rangs) if ident(x) == p["autour"]), None)
        decalage = place // limite * limite if place is not None else 0
        extra = {"rang": place, "trouve": place is not None}
    else:
        decalage = int(p.get("offset", 0))
    corps = {"entries": entrees(rangs[decalage:decalage + limite]), "total": len(rangs), "offset": decalage,
             "limit": limite, **extra, "source": source, "sources": sources}
    if counts is not None:
        corps["counts"] = counts
    return corps


def _ligne_source(nom: str, statut: str, raison: str | None) -> dict[str, Any]:
    return {"nom": nom, "statut": statut, "raison": raison}


# ---------------------------------------------------------------------------
# La lecture depuis la base.
# ---------------------------------------------------------------------------

def _depuis_base(con: Any, path: str, p: Mapping[str, str], empreinte: str) -> dict[str, Any]:
    """La réponse lue dans la base à jour que `lire` a ouverte (l'instantané contrôlé)."""
    lignes = {nom: (statut, raison) for nom, statut, raison in con.execute(_SQL_SOURCES)}
    sources = [_ligne_source(nom, *lignes[nom]) for nom in _etat.SOURCES]
    if path == "/api/recherche":
        return {"decisions": [json.loads(c) for (c,) in con.execute(_SQL_RECHERCHE["SPECS"])],
                "lecons": [json.loads(c) for (c,) in con.execute(_SQL_RECHERCHE["LEDGER"])],
                "stores": sources, "empreinte": empreinte}
    nom = _SOURCE_DE[path]
    counts = None
    if nom == "SPECS":
        kinds = json.dumps(p["kind"].split(",")) if "kind" in p else None
        ids = [i for (i,) in con.execute(_SQL_SPECS, {
            "task": p.get("task"), "kinds": kinds, "avec": p.get("avec"), "dernier": p.get("dernier"),
            "q": _etat.plier(p["q"]) if "q" in p else None, "store": "1" if p.get("ordre") == "store" else None})]
    else:
        ids = [i for (i,) in con.execute(_SQL_LECONS, {
            "archivees": p.get("status"), "category": p.get("category"),
            "q": _etat.plier(p["q"]) if "q" in p else None})]
        counts = dict(zip(("all", *CATEGORIES, "archived"), (int(n) for n in con.execute(_SQL_COMPTES).fetchone())))

    def entrees(tranche: list[str]) -> list[Any]:
        corps = dict(con.execute(_SQL_CORPS[nom], (json.dumps(tranche),)))
        return [json.loads(corps[i]) for i in tranche]
    return _reponse(ids, p, ident=lambda i: i, entrees=entrees, source=SOURCE_BASE, sources=sources, counts=counts)


# ---------------------------------------------------------------------------
# La lecture directe, avec les fonctions de la projection.
# ---------------------------------------------------------------------------

class _Ligne(NamedTuple):
    """Une entrée en lecture directe : ce que la projection en écrit (A2.1), `pli` calculé à la demande."""
    rang: int
    ident: str
    a: str  # task (SPECS) ou category (LEDGER)
    b: str  # kind (SPECS) ou status (LEDGER)
    cle_recente: tuple[int, int, str]
    entree: dict[str, Any]


def _raison(exc: BaseException, racine: Path) -> str:
    """La raison d'une source illisible : la classe et le message, bornés comme ceux du snapshot, la racine
    ABSOLUE remplacée par `.` (sa forme résolue d'abord, la plus longue : `/private/var/x` contient `/var/x`)."""
    message = str(exc)
    for prefixe in sorted({str(racine.resolve()), str(racine)}, key=len, reverse=True):
        if prefixe not in ("", "."):
            message = message.replace(prefixe, ".")
    return f"{type(exc).__name__}: {message[:_RAISON_MAX]}"


def _charger(racine: Path) -> dict[str, tuple[str, str | None, list[Any]]]:
    """(statut, raison, entrées) de CHAQUE source, lue par son propriétaire — la forme de `_safe_load_store`."""
    lues: dict[str, tuple[str, str | None, list[Any]]] = {}
    for nom in _etat.SOURCES:
        try:
            donnees = _PROPRIETAIRES[nom].load(racine)
        except Exception as exc:  # noqa: BLE001 - un journal illisible est un état de la réponse, jamais un 500
            lues[nom] = (_etat.STATUT_DEGRADE, _raison(exc, racine), [])
            continue
        entrees = donnees.get("entries") if isinstance(donnees, dict) else None
        if isinstance(entrees, list):
            lues[nom] = (_etat.STATUT_OK, None, entrees)
        else:
            lues[nom] = (_etat.STATUT_DEGRADE, "le propriétaire n'a pas rendu de liste d'entrées", [])
    return lues


def _lignes(nom: str, entrees: list[Any]) -> list[_Ligne]:
    """Les entrées qui sont des objets à id non vide, dans l'ordre du store (leur `rang` est leur place)."""
    champs = ("task", "kind") if nom == "SPECS" else ("category", "status")
    lignes = []
    for rang, entree in enumerate(entrees):
        if not isinstance(entree, dict):
            continue
        ident = _texte(entree.get("id"))
        if not ident:
            continue
        tier, num, valeur = _etat.rangement(ident)
        lignes.append(_Ligne(rang, ident, _texte(entree.get(champs[0])), _texte(entree.get(champs[1])),
                             (tier, -1 if num is None else num, valeur), entree))
    return lignes


def _recentes(lignes: list[_Ligne]) -> list[_Ligne]:
    """tier DESC, num DESC, valeur DESC ; `reverse=True` garde STABLE l'ordre d'entrée, celui du store : rang ASC."""
    return sorted(lignes, key=lambda ligne: ligne.cle_recente, reverse=True)


def _par_q(nom: str, lignes: list[_Ligne], p: Mapping[str, str]) -> list[_Ligne]:
    if "q" not in p:
        return lignes
    aiguille = _etat.plier(p["q"])
    return [ligne for ligne in lignes if aiguille in _etat.plier(_etat.foin(nom, ligne.entree))]


def _filtrer_specs(lignes: list[_Ligne], p: Mapping[str, str]) -> list[_Ligne]:
    choisies = lignes
    if "task" in p:
        choisies = [ligne for ligne in choisies if ligne.a == p["task"]]
    if "kind" in p:
        kinds = set(p["kind"].split(","))
        choisies = [ligne for ligne in choisies if ligne.b in kinds]
    if "avec" in p:
        planifiees = {ligne.a for ligne in lignes if ligne.b == "plan"}  # le store ENTIER
        choisies = [ligne for ligne in choisies if ligne.a in planifiees]
    if "dernier" in p:
        vues: set[tuple[str, str]] = set()
        gardees: set[int] = set()
        for ligne in _recentes(choisies):
            if (ligne.a, ligne.b) not in vues:
                vues.add((ligne.a, ligne.b))
                gardees.add(ligne.rang)
        choisies = [ligne for ligne in choisies if ligne.rang in gardees]
    choisies = _par_q("SPECS", choisies, p)
    return choisies if p.get("ordre") == "store" else _recentes(choisies)


def _filtrer_lecons(lignes: list[_Ligne], p: Mapping[str, str]) -> tuple[list[_Ligne], dict[str, int]]:
    actives = [ligne for ligne in lignes if ligne.b != "archived"]
    counts = {"all": len(actives), **{c: sum(1 for ligne in actives if ligne.a == c) for c in CATEGORIES},
              "archived": len(lignes) - len(actives)}
    choisies = [ligne for ligne in lignes if ligne.b == "archived"] if "status" in p else actives
    if "category" in p:
        choisies = [ligne for ligne in choisies if ligne.a == p["category"]]
    return _recentes(_par_q("LEDGER", choisies, p)), counts


def _en_direct(path: str, p: Mapping[str, str], racine: Path, empreinte: str) -> dict[str, Any]:
    """La réponse lue dans les journaux eux-mêmes, par leurs propriétaires."""
    lues = _charger(racine)
    sources = [_ligne_source(nom, lues[nom][0], lues[nom][1]) for nom in _etat.SOURCES]
    if path == "/api/recherche":
        return {"decisions": [ligne.entree for ligne in _lignes("SPECS", lues["SPECS"][2]) if ligne.b == "decision"],
                "lecons": [ligne.entree for ligne in _lignes("LEDGER", lues["LEDGER"][2]) if ligne.b != "archived"],
                "stores": sources, "empreinte": empreinte}
    nom = _SOURCE_DE[path]
    statut, _raison, entrees = lues[nom]
    if statut != _etat.STATUT_OK:
        return {"entries": [], "total": 0, "offset": 0, "limit": LIMITE_DEFAUT, "source": SOURCE_DIRECT,
                "sources": sources}
    lignes = _lignes(nom, entrees)
    if nom == "SPECS":
        choisies, counts = _filtrer_specs(lignes, p), None
    else:
        choisies, counts = _filtrer_lecons(lignes, p)
    return _reponse(choisies, p, ident=lambda ligne: ligne.ident,
                    entrees=lambda tranche: [ligne.entree for ligne in tranche],
                    source=SOURCE_DIRECT, sources=sources, counts=counts)


def _fermer(con: Any) -> None:
    try:
        con.close()
    except Exception:  # noqa: BLE001 - une fermeture ratée ne remonte jamais
        pass


def corps_route(path: str, p: Mapping[str, str], racine: Any, *, empreinte: str) -> dict[str, Any]:
    """Le corps d'une requête DANS la grammaire : la base si `lire` en rend une, sinon — ou si la requête sur la
    base lève, quelle qu'en soit la classe — la lecture directe. La connexion est fermée dans tous les cas."""
    racine = Path(racine)
    con = _etat.lire(racine)
    if con is not None:
        try:
            return _depuis_base(con, path, p, empreinte)
        except Exception as exc:  # noqa: BLE001 - réserve C8 : jamais un 500, la lecture directe répond
            _LOG.warning("ROUTE %s : base illisible (%s: %s) — lecture directe", path, type(exc).__name__, exc)
        finally:
            _fermer(con)
    return _en_direct(path, p, racine, empreinte)


# ---------------------------------------------------------------------------
# `/api/livrables` : les livrables Markdown d'une tâche, en lecture seule et bornée (B3, annexe § 2).
# ---------------------------------------------------------------------------

class _Candidat(NamedTuple):
    """Un document de la liste FERMÉE et le `lstat` pris au listage, dont l'ETag est fait."""
    nom: str
    genre: str
    cle: tuple[int, int, str]
    chemin: Path
    taille: int
    mtime_ns: int


class _Liste(NamedTuple):
    statut: str
    raisons: list[str]
    candidats: list[_Candidat]


def _raison_os(exc: BaseException) -> str:
    """La classe et le message d'une erreur de lecture, SANS chemin : `strerror` n'en porte pas ; une autre
    classe (un `RuntimeError` de boucle de liens cite le chemin) ne rend que son nom."""
    message = exc.strerror if isinstance(exc, OSError) and exc.strerror else ""
    return (f"{type(exc).__name__}: {message}" if message else type(exc).__name__)[:_RAISON_MAX]


def _genre(suffixe: str | None) -> tuple[str, tuple[int, int, str]]:
    """Le genre d'un document et sa clé d'ordre : plan, annexe, critic-n croissant, exec-critic-n, LOT-*, le reste."""
    if suffixe == "plan":
        return "plan", (0, 0, "")
    if suffixe == "annexe":
        return "annexe", (1, 0, "")
    critique = _CRITIQUE.fullmatch(suffixe or "")
    if critique is not None:
        execution = critique.group(1) is not None
        return ("exec-critic" if execution else "critic"), (3 if execution else 2, int(critique.group(2)), "")
    if suffixe is not None and suffixe.startswith("LOT-"):
        return "lot", (4, 0, suffixe)
    return "autre", (5, 0, suffixe or "")


def _lister(racine: Path, tache: str) -> _Liste:
    """La liste FERMÉE des livrables de `tache` (déjà dans sa forme), ordonnée ; une entrée qui n'est pas un fichier
    régulier sous `docs/tasks` même est ÉCARTÉE, jamais lue, et DITE. Ne lève pas sur une erreur de lecture."""
    dossier = racine / "docs" / "tasks"
    forme = re.compile(re.escape(tache) + r"(?:-(" + _SUFFIXE + r"))?\.md")
    try:
        if not dossier.is_dir():
            return _Liste(LIVRABLE_ABSENT, ["docs/tasks absent"], [])
        if not os.access(dossier, os.R_OK | os.X_OK):  # `glob` avale EACCES : un dossier illisible n'est pas vide
            raise PermissionError(13, "Permission denied")
        base = dossier.resolve()
        noms = sorted(p.name for p in dossier.glob(tache + "*.md"))  # un niveau : jamais `**`, jamais la requête
    except (OSError, RuntimeError) as exc:
        return _Liste(LIVRABLE_DEGRADE, [f"docs/tasks illisible ({_raison_os(exc)})"], [])
    candidats: list[_Candidat] = []
    ecartes: list[str] = []
    for nom in noms:
        reconnu = forme.fullmatch(nom)
        if reconnu is None:
            continue
        chemin = dossier / nom
        try:
            st = chemin.lstat()  # un lien n'est pas S_ISREG sous `lstat` : jamais suivi
            # Lien DUR (`st_nlink > 1`) : le même inode qu'un fichier hors du dossier, servi sous un nom d'ici.
            regulier = stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and chemin.resolve().parent == base
        except (OSError, RuntimeError):
            regulier = False
        if not regulier:
            ecartes.append(nom)
            continue
        genre, cle = _genre(reconnu.group(1))
        candidats.append(_Candidat(nom, genre, cle, chemin, st.st_size, st.st_mtime_ns))
    candidats.sort(key=lambda c: (c.cle, c.nom))
    if ecartes:
        return _Liste(LIVRABLE_DEGRADE, [f"entrée non régulière écartée : {', '.join(ecartes)}"[:_RAISON_MAX]],
                      candidats)
    if not candidats:
        return _Liste(LIVRABLE_ABSENT, [f"aucun livrable sous docs/tasks pour {tache}"], [])
    return _Liste(LIVRABLE_OK, [], candidats)


def _lire_document(chemin: Path, plafond: int) -> tuple[bytes, bool]:
    """(au plus `plafond` octets, tronqué) — JAMAIS plus de `plafond + 1` octets lus (M12). `O_NONBLOCK` : une FIFO
    ne bloque pas l'ouverture ; `O_NOFOLLOW` : un lien glissé après le listage lève ; `fstat` sur le descripteur
    ouvert : ce qui n'est pas un fichier régulier à lien unique lève avant toute lecture."""
    fd = os.open(chemin, _OUVERTURE)
    try:
        etat_fd = os.fstat(fd)
        if not stat.S_ISREG(etat_fd.st_mode):
            raise OSError(0, "pas un fichier régulier")
        if etat_fd.st_nlink != 1:
            raise OSError(0, "fichier à liens multiples")
        morceaux: list[bytes] = []
        reste = plafond + 1
        while reste > 0:
            bloc = os.read(fd, min(reste, _BLOC_LECTURE))
            if not bloc:
                break
            morceaux.append(bloc)
            reste -= len(bloc)
    finally:
        os.close(fd)
    brut = b"".join(morceaux)
    return brut[:plafond], len(brut) > plafond


def _decoder(brut: bytes, tronque: bool) -> str:
    """UTF-8, un octet invalide rendu `\\xNN` (`backslashreplace` : la constante de l'autre mode est lue comme du
    SQL par le banc de lecture seule) ; tronqué, la séquence que la borne a coupée est retirée, pas rendue."""
    return codecs.getincrementaldecoder("utf-8")("backslashreplace").decode(brut, final=not tronque)


def _mtime_iso(mtime_ns: int) -> str | None:
    try:
        moment = datetime.datetime.fromtimestamp(mtime_ns // 1_000_000_000, tz=datetime.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def corps_livrables(tache: str, liste: _Liste) -> dict[str, Any]:
    """Le corps de `/api/livrables` pour une liste prise AVANT la lecture : `BORNE_DOC` par document,
    `BORNE_TOTALE` en tout, `DOCUMENTS_MAX` documents ; un document qui ne se lit pas rend `degraded`, dit."""
    statut, raisons, documents = liste.statut, list(liste.raisons), []
    restant, muets = BORNE_TOTALE, 0
    for candidat in liste.candidats[:DOCUMENTS_MAX]:
        plafond = min(BORNE_DOC, restant)
        texte, tronque = "", candidat.taille > 0
        if plafond > 0:
            try:
                brut, tronque = _lire_document(candidat.chemin, plafond)
            except OSError as exc:
                statut = LIVRABLE_DEGRADE
                raisons.append(f"{candidat.nom} illisible ({_raison_os(exc)})")
                continue
            restant -= len(brut)
            if tronque and plafond < BORNE_DOC:  # coupé par le RESTE du budget, pas par les 512 Kio du document
                raisons.append(f"{candidat.nom} : tronqué à {plafond} octets par la borne totale de la tâche")
            texte = _decoder(brut, tronque)
            if len(texte) > BORNE_DOC:  # `backslashreplace` rend 4 caractères par octet invalide
                texte, tronque = texte[:BORNE_DOC], True
                raisons.append(f"{candidat.nom} : texte coupé à {BORNE_DOC} caractères (octets invalides)")
        else:
            muets += 1
        documents.append({"nom": candidat.nom, "genre": candidat.genre, "octets": candidat.taille,
                          "mtime": _mtime_iso(candidat.mtime_ns), "tronque": tronque, "texte": texte})
    if muets:
        raisons.append(f"borne totale de {BORNE_TOTALE} octets atteinte : {muets} document(s) sans texte")
    if len(liste.candidats) > DOCUMENTS_MAX:
        raisons.append(f"{len(liste.candidats) - DOCUMENTS_MAX} document(s) au-delà de {DOCUMENTS_MAX}, non listés")
    return {"task": tache, "statut": statut, "raison": " ; ".join(raisons) or None, "documents": documents}


def lire_livrables(racine: Any, tache: str) -> dict[str, Any]:
    """Le corps complet, sans ETag (bancs, outils) ; ne lève jamais."""
    try:
        return corps_livrables(tache, _lister(Path(racine), tache))
    except Exception as exc:  # noqa: BLE001 - une route qui lit des fichiers ne rend jamais un 500
        return {"task": tache, "statut": LIVRABLE_DEGRADE, "raison": _raison_os(exc), "documents": []}


# ---------------------------------------------------------------------------
# Le dispatch, appelé par `dashboard.UIHandler._route` après le jeton.
# ---------------------------------------------------------------------------

def _entetes(handler: Any, etag: str | None) -> None:
    if etag is not None:
        handler.send_header("ETag", etag)
    handler.send_header("Vary", "Accept-Encoding")
    handler.send_header("Cache-Control", CACHE_CONTROL)
    # La même paire de durcissement que toute réponse JSON de ce serveur ; aucun en-tête CORS, jamais.
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")


def _compresser(octets: bytes) -> bytes:
    return gzip.compress(octets, compresslevel=_transport.GZIP_NIVEAU, mtime=0)


def _rendu(path: str, p: Mapping[str, str], racine: Path, empreinte: str) -> tuple[bytes, bool]:
    """(octets JSON, saine) : `saine` = la source que la ROUTE lit est `ok` — SPECS pour `/api/specs`, LEDGER pour
    `/api/lecons`, les deux pour `/api/recherche`. Seule une réponse saine porte un ETag (docstring)."""
    corps = corps_route(path, p, racine, empreinte=empreinte)
    lignes = corps["stores"] if path == "/api/recherche" else corps["sources"]
    lues = [ligne for ligne in lignes if path == "/api/recherche" or ligne["nom"] == _SOURCE_DE[path]]
    octets = _transport.serialiser(corps)
    if path == "/api/recherche" and len(octets) > RECHERCHE_BORNE_OCTETS:
        _LOG.warning("ROUTE /api/recherche : %d octets bruts, au-delà de la borne de %d (S-01M530QPV2 (a)) — "
                     "replanifier la pagination du corpus", len(octets), RECHERCHE_BORNE_OCTETS)
    return octets, bool(lues) and all(ligne["statut"] == _etat.STATUT_OK for ligne in lues)


class MemoRecherche:
    """Le corps de `/api/recherche` pour UNE étiquette, la dernière, et son gzip calculé à la première demande ;
    un par serveur (`UIHTTPServer.recherche_memo`). Une construction par étiquette, sous le verrou ; une réponse
    non saine n'est jamais mémorisée (elle est relue au GET suivant, comme elle part sans ETag)."""

    def __init__(self) -> None:
        self.verrou = threading.Lock()
        self.etag: str | None = None
        self.octets = b""
        self.gzip: bytes | None = None
        self.constructions = 0

    def servir(self, etag: str, construire: Callable[[], tuple[bytes, bool]], compresse: bool) -> tuple[bytes, bool]:
        """(octets à envoyer, saine) pour `etag` : mémorisés si l'étiquette est la dernière, construits sinon."""
        with self.verrou:
            if self.etag != etag:
                octets, saine = construire()
                if not saine:
                    return (_compresser(octets) if compresse else octets), False
                self.etag, self.octets, self.gzip = etag, octets, None
                self.constructions += 1
            if not compresse:
                return self.octets, True
            if self.gzip is None:
                self.gzip = _compresser(self.octets)
            return self.gzip, True


def _repondre_304(handler: Any, etag: str) -> None:
    handler.send_response(304)
    _entetes(handler, etag)
    handler.end_headers()


def _envoyer(handler: Any, octets: bytes, compresse: bool, etag: str | None) -> None:
    """Le 200 JSON (`octets` déjà gzippés quand `compresse`), avec l'ETag s'il y en a un."""
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(octets)))
    if compresse:
        handler.send_header("Content-Encoding", "gzip")
    _entetes(handler, etag)
    handler.end_headers()
    try:
        handler.wfile.write(octets)
    except OSError:
        pass


def _traiter_livrables(handler: Any, path: str, p: Mapping[str, str], racine: Path, code: str) -> None:
    """`/api/livrables` : l'ETag est fait de la liste prise AVANT la lecture et n'existe qu'au statut `ok` — un
    document absent ou une lecture en panne ne se revalide jamais en 304 (M14) ; jamais l'empreinte des journaux."""
    try:
        liste = _lister(racine, p["task"])
    except Exception as exc:  # noqa: BLE001 - une route qui lit des fichiers ne rend jamais un 500
        liste = _Liste(LIVRABLE_DEGRADE, [_raison_os(exc)], [])
    etag = None
    if liste.statut == LIVRABLE_OK:
        etag = etiquette(path, p, {c.nom: f"{c.mtime_ns}:{c.taille}" for c in liste.candidats}, code)
        if _transport.etag_correspond(handler.headers.get("If-None-Match"), etag):
            _repondre_304(handler, etag)
            return
    try:
        corps = corps_livrables(p["task"], liste)
    except Exception as exc:  # noqa: BLE001 - idem
        corps = {"task": p["task"], "statut": LIVRABLE_DEGRADE, "raison": _raison_os(exc), "documents": []}
    try:
        octets = _transport.serialiser(corps)
    except Exception as exc:  # noqa: BLE001 - un substitut isolé ne coupe jamais la connexion : `degraded`, dit
        corps = {"task": p["task"], "statut": LIVRABLE_DEGRADE,
                 "raison": f"réponse non sérialisable ({type(exc).__name__})", "documents": []}
        octets = _transport.serialiser(corps)
    compresse = _transport.accepte_gzip(handler.headers.get("Accept-Encoding"))
    _envoyer(handler, _compresser(octets) if compresse else octets, compresse,
             etag if corps["statut"] == LIVRABLE_OK else None)


def traiter(handler: Any, path: str, qs: Mapping[str, Sequence[str]], racine: Any, code: str) -> None:
    """Répond au GET déjà authentifié d'une route de `ROUTES` : 400 hors grammaire, 304 si `If-None-Match`
    porte l'ETag courant, sinon 200 (gzippé si le client le nomme). Empreinte indisponible : ni ETag ni 304."""
    p = parametres(path, qs)
    if p is None:
        handler._reject(400, "bad_request")
        return
    racine = Path(racine)
    if path == ROUTE_LIVRABLES:  # AVANT l'empreinte des journaux, qu'elle ne lit pas
        _traiter_livrables(handler, path, p, racine, code)
        return
    empreintes = _empreintes(racine)  # AVANT toute lecture (A2.3)
    etag = None if empreintes is None else etiquette(path, p, empreintes, code)
    if etag is not None and _transport.etag_correspond(handler.headers.get("If-None-Match"), etag):
        _repondre_304(handler, etag)
        return
    empreinte = EMPREINTE_INDISPONIBLE if empreintes is None else _hacher(empreintes, code)
    compresse = _transport.accepte_gzip(handler.headers.get("Accept-Encoding"))
    memo = getattr(handler.server, "recherche_memo", None)
    if path == "/api/recherche" and etag is not None and isinstance(memo, MemoRecherche):
        octets, saine = memo.servir(etag, lambda: _rendu(path, p, racine, empreinte), compresse)
    else:
        octets, saine = _rendu(path, p, racine, empreinte)
        if compresse:
            octets = _compresser(octets)
    _envoyer(handler, octets, compresse, etag if saine else None)
