#!/usr/bin/env python3
"""Tri topologique du board en VAGUES, sur `depends_on` — lecture seule, 0 LLM.

FRÈRE DE `plan_pool.py`, MÊME DOCTRINE. Il lit les stores d'état directement,
n'importe RIEN de `.agents/bin/` (du code vendoré chez un adoptant), n'écrit
jamais, et se termine sur un verdict porté par son code de sortie.

CE SCRIPT NE FAIT PAS AUTORITÉ SUR L'ORDRE D'UNE NUIT, exactement comme
`plan_pool.py` ne fait pas autorité sur son éligibilité. `/night` reconstruit
son ordre en phase 3 à partir du board qu'il relit lui-même. Ce relevé PRÉPARE :
il dit au pilote ce que la fermeture amène, dans quel ordre les vagues tombent,
et ce qui restera hors d'atteinte. Il n'admet rien.

CE QU'IL CALCULE, ET CE QU'IL NE PROUVE PAS
-------------------------------------------
DEUX AXES, JAMAIS CONFONDUS.

*Axe 1 — l'ordre DUR.* Kahn déterministe sur `depends_on`. Une arête `a → b`
est SATISFAITE ssi `b` est `done` ou absente du board (lien pendant). Vague 1 =
les tâches dont toutes les arêtes sont satisfaites ; vague n+1 = celles dont les
arêtes non satisfaites atterrissent toutes dans les vagues ≤ n. Départage à
l'intérieur d'une vague : clé d'id croissante, comme `plan_pool` — les anciens
par NUMÉRO, puis les `T-<ULID>` dans l'ordre de frappe (T-00000726).

*Axe 2 — le parallélisme DANS une vague.* Découpe en bottes sur le champ
`writeset` DU BOARD, et lui seul. **Pas** le `files` du checkpoint `plan` : ce
sont deux ensembles différents (l'un sert à intersecter un `git diff`, l'autre
est ce que `tasks.py parallel` re-prouvera), et les confondre est le piège des
« deux machines à verdict » que l'en-tête de `plan_pool.py` raconte déjà.

*Ce qui pèse.* `chemin_critique` : la plus longue chaîne de `depends_on` entre
tâches PLACÉES, amont d'abord (`[]` sans arête) ; `liberations` : pour chaque
tâche placée, son aval transitif et direct, et son `responsable` humain lu au
board. Rendus après vagues, murs et hors-vagues ; même statut NON-AUTORITATIF.

LA SONDE DE CHEVAUCHEMENT SUR-DÉTECTE, PAR CONSTRUCTION, ET LE DIT.
`tasks.py parallel` reste le SEUL prouveur de disjonction de ce dépôt — sa
preuve fait ~160 lignes mesurées (frontière de segment, `NFC ∘ casefold ∘ NFC`,
« an inadmissible stored path counts as an overlap »). Une seconde
implémentation ici dériverait, et **la dérive serait muette**. Celle-ci est donc
délibérément grossière, avec une direction d'erreur FIXÉE : elle sérialise plus
que nécessaire, jamais moins. Une botte proposée reste NON PROUVÉE ; si
`tasks.py parallel` la refuse, il a raison contre ce relevé.

LA FERMETURE TRANSITIVE DU PÉRIMÈTRE
-------------------------------------
Une sélection est FERMÉE sur `depends_on` : si T-A est demandée et dépend de
T-B, alors T-B entre. Sans ça, ce relevé produirait un ordre pour des plans qui
ne peuvent pas s'exécuter — et se contenterait de le CONSTATER.

Trois règles, toutes dites dans le rapport :
  - l'expansion est CHIFFRÉE et chaque tâche tirée nomme QUI l'a tirée ;
  - une dépendance `done` ne tire rien : elle est satisfaite, la récursion
    s'arrête là ;
  - une dépendance `blocked` ARRÊTE la branche et la NOMME. On ne peut pas
    fabriquer un plan pour une tâche qui attend une décision humaine.

LE CYCLE EST UN REFUS BRUYANT, ET RIEN N'EST RENDU
---------------------------------------------------
Pas « la partie acyclique plus un reliquat » : un ordre partiel qui a l'air
complet est le mode de défaillance à éviter. Le chemin est nommé en entier, et
le remède est une commande qui TOURNE — `tasks.py load()` accepte un board
cyclique par choix, précisément pour que `depends --retirer` reste jouable
(T-00000765 : on retire UNE arête technique, jamais la déclaration entière ;
un cycle tenu par des seuls ORDRE PILOTE renvoie à la route SUGGESTION).

    python core-scripts/plan_waves.py [--root DIR] waves [--state pending]
                                 [--workstream X] [--task T-x …] [--json]
    (`--chantier X`, l'ancien nom, reste accepté)

Codes de sortie — ils SONT le verdict :
    0  une décomposition en vagues a été produite
    1  erreur d'exécution (store malformé) — jamais dégradée en « pas de
       dépendances », qui se lirait comme un graphe plat
    2  usage (argparse)
    3  CYCLE — aucune vague n'est produite
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

BOARD_REL = Path(".agents") / "state" / "board" / "TASKS.json"
# La forme ENREGISTREMENT du board (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : sa LECTURE est déléguée au frère `plan_pool.py`.
BOARD_DOSSIERS = ("tasks", "epics")

# Borne d'affichage, même valeur et même raison que `plan_pool.STATUS_MAX_ROWS` :
# une table qui déborde l'écran ne sera pas lue à 3 h du matin. La troncature est
# TOUJOURS dite, avec le total — une troncature silencieuse se lit comme une
# couverture complète.
WAVES_MAX_ROWS = 30
# Ids nommés par ligne de LIBERATIONS ; le reste est COMPTÉ (« … +k »), jamais tu.
LIBERE_MAX_IDS = 10

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CYCLE = 3

# RECOPIE VERBATIM de `.agents/bin/plan_depends.ORDRE_PILOTE_CANONIQUE` (T-00000765)
# — jamais importée, ce script ne dépend d'aucun code de `.agents/bin/` ; la parité
# des deux copies est tenue par un témoin (W14 dans test_depends_add.py).
ORDRE_PILOTE_CANONIQUE = re.compile(r"^ORDRE PILOTE S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\b")

# LA FORME `P-<ULID>` (T-00000726, forme A) — RECOPIE de `ULID_BODY` / `_ULID_ID` de
# `.agents/bin/tasks_stockage.py`, jamais importée (même raison que ci-dessus) :
# 26 symboles Crockford MAJUSCULES, ancrés aux DEUX bouts.
ULID_BODY = "[0-9A-HJKMNP-TV-Z]{26}"
_ULID_ID = re.compile(r"\A[TSL]-(" + ULID_BODY + r")\Z")

# Un id du board est une DONNÉE : `numeric_id` n'en lit que la queue, si bien qu'un id
# porteur d'un caractère de contrôle (séquence ESC) se range sans lever. Avant d'être
# IMPRIMÉ dans CHEMIN CRITIQUE et LIBERATIONS, tout caractère hors de l'alphabet d'un
# id (`T-`, chiffres, ULID) y sort en `?` — comme le `responsable` ne sort qu'imprimable.
_HORS_ALPHABET_ID = re.compile(r"[^0-9A-Za-z-]")


def _id_imprime(tid: Any) -> str:
    return _HORS_ALPHABET_ID.sub("?", str(tid))


class WavesError(Exception):
    """Store malformé : échec franc, exit 1, jamais de dégradé."""


def force_utf8_stdio() -> None:
    """Consoles Windows en cp1252 : les stores sont UTF-8 par construction."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", newline="\n")


def numeric_id(id_str: str) -> tuple[int, int | str]:
    """Clé d'ORDRE à DEUX ÉTAGES, jamais la chaîne (T-00000726) : `(0, n)` pour
    un id ancien — queue de 1 à 15 chiffres non précédée d'un chiffre, par sa
    valeur NUMÉRIQUE (`T-14` et `T-00000014` sont la même) ; `(1, ulid)` pour un
    `P-<ULID>`, après tout ancien, les ULID entre eux dans l'ordre de frappe.
    PARITÉ avec `tasks.sort_key` (`.agents/bin/tasks_stockage.py`), RECOPIÉE et
    jamais importée, tenue par (k6) de `plan_waves.test.sh` sur CE domaine : ids
    de 1 à 15 chiffres et ULID T/S/L à queue lettre ou chiffre, rangés ; ids de 16
    chiffres, levés des DEUX côtés. Le nom est gardé : les huit sites qui rangent
    en héritent. Un id ni ancien ni ULID lève `WavesError`."""
    ulid = _ULID_ID.match(id_str or "")
    if ulid:
        return (1, ulid.group(1))
    match = re.search(r"(?<!\d)(\d{1,15})\Z", id_str or "")
    if not match:
        raise WavesError(f"id de tâche malformé : {id_str!r}")
    return (0, int(match.group(1)))


def _charger_plan_pool() -> Any:
    """Le frère `plan_pool.py`, chargé PAR CHEMIN (patron `_charger_plan_waves` de feuille_de_route : aucun
    `sys.path` modifié, SANS cache de bytecode), enregistré sous un nom privé AVANT son exécution (ses dataclasses
    l'exigent, T-00000134). Absent ⇒ `WavesError` : la forme dossier ne se lit pas sans lui."""
    chemin = Path(__file__).resolve().with_name("plan_pool.py")
    spec = importlib.util.spec_from_file_location("_plan_waves_plan_pool", chemin) if chemin.is_file() else None
    if spec is None or spec.loader is None:
        raise WavesError(f"{chemin} : module frère introuvable — le board en dossier ne se lit pas sans lui")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    avant = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    finally:
        sys.dont_write_bytecode = avant
    return module


def load_board(root: Path) -> list[dict[str, Any]]:
    """Lecture DIRECTE du store, comme `plan_pool` — aucun import de
    `.agents/bin/`. Un JSON malformé lève ; il ne se dégrade jamais en board
    vide, qui rendrait « aucune dépendance » et donc un faux graphe plat.
    DEUX FORMES (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : dès qu'un dossier d'enregistrements
    existe, la LECTURE est déléguée à `plan_pool.lire_board_forme` (dossier, ou
    refus nommé des deux formes) ; sans lui, le monolithe se lit ici, comme avant
    — `plan_pool.py` n'est alors pas chargé (feuille_de_route.test.sh (k))."""
    path = root / BOARD_REL
    if any((path.parent / d).is_dir() or (path.parent / d).is_symlink() for d in BOARD_DOSSIERS):
        pool = _charger_plan_pool()
        try:
            data = pool.lire_board_forme(root)
        except pool.PoolError as exc:
            raise WavesError(f"{path.parent} : illisible ({exc})") from exc
    elif not path.exists():
        raise WavesError(f"{path} : store introuvable")
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WavesError(f"{path} : illisible ({exc})") from exc
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise WavesError(f"{path} : clé 'tasks' absente ou non-liste")
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not task.get("id") or not task.get("state"):
            raise WavesError(f"{path} : tâche #{i} sans id ou sans state")
    return tasks


def depends_on_of(task: dict[str, Any]) -> list[str]:
    """La déclaration, `[]` quand elle est absente — la MÊME règle que
    `tasks.py::depends_on_of` : clé absente, null et liste vide sont un seul et
    même état. Répétée ici plutôt qu'importée, parce que ce script ne dépend
    d'aucun code de `.agents/bin/` ; le contrat est de trois lignes et son
    unique source de vérité est le docstring de `tasks.py`."""
    declared = task.get("depends_on")
    if not isinstance(declared, list):
        return []
    return [d for d in declared if isinstance(d, str) and d]


def writeset_of(task: dict[str, Any]) -> list[str]:
    declared = task.get("writeset")
    if not isinstance(declared, list):
        return []
    return [p for p in declared if isinstance(p, str) and p]


def coarse_overlap(left: list[str], right: list[str]) -> tuple[str, str] | None:
    """SUR-DÉTECTE, et c'est le contrat. Préfixe canonique à la frontière de
    SÉPARATEUR, casefold, séparateurs unifiés. Elle ne sait pas ce que
    `tasks.py` sait (formes NFC, noms de périphériques Win32, chemins
    inadmissibles) — donc elle sérialise plus que nécessaire, JAMAIS moins."""

    def canon(path: str) -> str:
        return path.replace("\\", "/").strip("/").casefold()

    for a in left:
        ca = canon(a)
        for b in right:
            cb = canon(b)
            if not ca or not cb:
                continue
            if ca == cb or ca.startswith(cb + "/") or cb.startswith(ca + "/"):
                return (a, b)
    return None


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tous les cycles atteignables, chacun rendu comme un chemin nommé et
    fermé (`[a, b, c, a]`). Itératif : un board édité à la main peut porter un
    cycle, et une récursion y exploserait au lieu de le rapporter."""
    cycles: list[list[str]] = []
    seen_signatures: set[frozenset[str]] = set()
    colour: dict[str, int] = {}  # 0 = en cours, 1 = terminé

    for origin in sorted(graph, key=numeric_id):
        if colour.get(origin) == 1:
            continue
        stack: list[tuple[str, list[str]]] = [(origin, [origin])]
        colour[origin] = 0
        while stack:
            node, path = stack.pop()
            progressed = False
            for dep in graph.get(node, []):
                if dep in path:
                    cycle = path[path.index(dep) :] + [dep]
                    signature = frozenset(cycle)
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        cycles.append(cycle)
                    continue
                if colour.get(dep) == 1:
                    continue
                colour[dep] = 0
                stack.append((dep, path + [dep]))
                progressed = True
            if not progressed:
                colour[node] = 1
    return cycles


def _coupe_du_cycle(cycle: list[str], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Le remède qui ne DÉTRUIT rien (T-00000765) : la PREMIÈRE arête du cycle
    dont le motif n'est pas un `ORDRE PILOTE` canonique, avec les arêtes qui
    RESTENT à l'aval — un `depends --clear` effaçait toute la déclaration pour
    en retirer une. Toutes ordre pilote ⇒ `ordre_pilote_seul`, la route
    SUGGESTION est imprimée à la place. Clé ADDITIVE du résultat `--json`."""
    premiere: dict[str, Any] | None = None
    for aval, amont in zip(cycle, cycle[1:]):
        task = by_id.get(aval) or {}
        motifs = task.get("depends_motif") or {}
        motif = motifs.get(amont) or None
        if premiere is None:
            premiere = {"aval": aval, "amont": amont, "motif": motif}
        if motif and ORDRE_PILOTE_CANONIQUE.match(motif):
            continue
        restes = [(d, motifs.get(d) or None) for d in depends_on_of(task) if d != amont]
        return {"aval": aval, "amont": amont, "motif": motif, "restes": restes,
                "ordre_pilote_seul": False}
    return {**(premiere or {"aval": cycle[0], "amont": cycle[1], "motif": None}),
            "restes": [], "ordre_pilote_seul": True}


def close_perimeter(
    selected: list[str], by_id: dict[str, dict[str, Any]]
) -> tuple[list[str], dict[str, str], list[tuple[str, str]]]:
    """Ferme la sélection sur `depends_on`.

    Rend ``(périmètre, tiré_par, murs)`` — ``tiré_par`` nomme, pour chaque tâche
    ENTRÉE par fermeture, celle qui l'a tirée (l'expansion doit être lisible,
    pas seulement chiffrée), et ``murs`` liste les ``(dépendante, dépendance)``
    dont la branche s'arrête sur une tâche ``blocked``.

    Une tâche DEMANDÉE n'est jamais « tirée » (T-00001249) : elle est déjà dans la
    file dès le départ, et l'y inscrire quand son aval est dépilé avant elle (aval
    d'id plus petit) gonflait ``tiré_par`` — mesuré le 2026-10-09 : 97 des 100
    « tirées » du board du kit étaient des demandées."""
    perimeter: list[str] = []
    pulled_by: dict[str, str] = {}
    walls: list[tuple[str, str]] = []
    demandees = set(selected)
    queue = list(selected)
    while queue:
        tid = queue.pop(0)
        if tid in perimeter:
            continue
        perimeter.append(tid)
        task = by_id.get(tid)
        if task is None:
            continue
        for dep in depends_on_of(task):
            target = by_id.get(dep)
            # Absente du board ou close : SATISFAITE, la récursion s'arrête.
            if target is None or target["state"] == "done":
                continue
            # `blocked` = attend une décision humaine. On ne fabrique pas un plan
            # pour ça : la branche s'arrête et le mur est NOMMÉ.
            if target["state"] == "blocked":
                walls.append((tid, dep))
                continue
            # Demandée : déjà dans la file, jamais « tirée » (T-00001249).
            if dep not in perimeter and dep not in demandees:
                pulled_by.setdefault(dep, tid)
                queue.append(dep)
    return perimeter, pulled_by, walls


def build_waves(
    perimeter: list[str], by_id: dict[str, dict[str, Any]]
) -> tuple[list[list[str]], list[tuple[str, str, str]]]:
    """Kahn déterministe. Rend ``(vagues, hors_vagues)`` où chaque entrée de
    ``hors_vagues`` est ``(tâche, dépendance, raison)``."""
    inside = set(perimeter)
    unreachable: list[tuple[str, str, str]] = []
    remaining: dict[str, set[str]] = {}
    for tid in perimeter:
        task = by_id.get(tid)
        pending_deps: set[str] = set()
        for dep in depends_on_of(task or {}):
            target = by_id.get(dep)
            if target is None or target["state"] == "done":
                continue  # satisfaite
            if dep not in inside:
                reason = (
                    f"{target['state']}, hors périmètre"
                    if target["state"] != "blocked"
                    else "blocked — attend une décision humaine"
                )
                unreachable.append((tid, dep, reason))
                continue
            pending_deps.add(dep)
        remaining[tid] = pending_deps

    blocked_out = {tid for tid, _, _ in unreachable}
    waves: list[list[str]] = []
    placed: set[str] = set()
    candidates = {t for t in perimeter if t not in blocked_out}
    while candidates:
        wave = sorted(
            (t for t in candidates if remaining[t] <= placed),
            key=numeric_id,
        )
        if not wave:
            # Plus aucun progrès sans qu'un cycle ait été détecté en amont :
            # ce sont des tâches derrière un mur. Elles sortent NOMMÉES.
            for tid in sorted(candidates, key=numeric_id):
                held = sorted(remaining[tid] - placed, key=numeric_id)
                unreachable.append(
                    (tid, ", ".join(held), "derrière une branche arrêtée")
                )
            break
        waves.append(wave)
        placed.update(wave)
        candidates -= set(wave)
    return waves, unreachable


def bundle_wave(
    wave: list[str], by_id: dict[str, dict[str, Any]]
) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """Découpe une vague en bottes PROPOSÉES. Rend ``(bottes, sérialisées)`` où
    chaque sérialisée est ``(tâche, raison)``.

    Une tâche sans `writeset` n'est JAMAIS mise en botte : `tasks.py parallel`
    la refuserait comme « vacuously true », et proposer un groupe que l'outil
    refusera est un mensonge poli."""
    bundles: list[list[str]] = []
    serialised: list[tuple[str, str]] = []
    for tid in wave:
        task = by_id.get(tid) or {}
        paths = writeset_of(task)
        if not paths:
            serialised.append(
                (tid, "writeset non déclaré — `tasks.py parallel` le refuserait")
            )
            continue
        for bundle in bundles:
            clash = None
            for member in bundle:
                clash = coarse_overlap(paths, writeset_of(by_id.get(member) or {}))
                if clash is not None:
                    break
            if clash is None:
                bundle.append(tid)
                break
        else:
            bundles.append([tid])
    # Une botte d'un seul membre ne prouve rien : elle redevient une
    # sérialisation, et sa raison le dit.
    real, singles = [], []
    for bundle in bundles:
        (real if len(bundle) > 1 else singles).append(bundle)
    for bundle in singles:
        serialised.append((bundle[0], "seule de sa vague à ne rien chevaucher"))
    return real, sorted(serialised, key=lambda row: numeric_id(row[0]))


def _aretes_placees(
    waves: list[list[str]], by_id: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """Les amonts NON SATISFAITS de chaque tâche placée, restreints aux tâches
    placées : l'arête vers une `done` ou une absente est satisfaite, celle vers une
    tâche hors vagues ne vaut rien ici (la tâche ne serait pas placée)."""
    placed = {t for wave in waves for t in wave}
    return {t: [d for d in depends_on_of(by_id.get(t) or {}) if d in placed]
            for wave in waves for t in wave}


def critical_path(waves: list[list[str]], by_id: dict[str, dict[str, Any]]) -> list[str]:
    """La plus longue chaîne de `depends_on` parmi les tâches PLACÉES, amont
    d'abord. Départage entre chaînes de même longueur : la plus petite suite de
    clés `numeric_id`, comparée amont d'abord — déterministe, et exact par
    programmation dynamique dans l'ordre des vagues (un préfixe d'une chaîne
    minimale est minimal parmi ses égales). `[]` quand aucune arête ne relie deux
    tâches placées : une chaîne d'une seule tâche n'est pas un chemin critique."""
    amonts = _aretes_placees(waves, by_id)
    best: dict[str, list[str]] = {}

    def cle(chaine: list[str]) -> tuple[int, list[tuple[int, int | str]]]:
        return (-len(chaine), [numeric_id(t) for t in chaine])

    for wave in waves:  # l'ordre des vagues EST un ordre topologique
        for tid in wave:
            prefixes = [best[d] for d in amonts[tid]]
            best[tid] = (min(prefixes, key=cle) if prefixes else []) + [tid]
    if not best:
        return []
    chemin = min(best.values(), key=cle)
    return chemin if len(chemin) > 1 else []


def liberations(
    waves: list[list[str]], by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Ce que chaque tâche placée LIBÈRE : son aval transitif parmi les tâches
    placées (`libere`), dont ses avals directs (`directes`), et le `responsable`
    humain du board lu par `.get` — champ posé par `tasks.py`, jamais importé ici ;
    une valeur qui n'est pas une chaîne non vide est rendue `None`. Seules les
    tâches qui libèrent au moins une autre sont listées, la plus libérante
    d'abord, puis par `numeric_id`."""
    amonts = _aretes_placees(waves, by_id)
    avals: dict[str, set[str]] = {t: set() for t in amonts}
    for tid, deps in amonts.items():
        for dep in deps:
            avals[dep].add(tid)
    rows: list[dict[str, Any]] = []
    for tid in avals:
        if not avals[tid]:
            continue
        vus: set[str] = set()
        pile = list(avals[tid])
        while pile:  # itératif : pas de récursion sur une chaîne longue
            courant = pile.pop()
            if courant in vus:
                continue
            vus.add(courant)
            pile.extend(avals[courant] - vus)
        responsable = (by_id.get(tid) or {}).get("responsable")
        rows.append({
            "tache": tid,
            "libere": sorted(vus, key=numeric_id),
            "directes": sorted(avals[tid], key=numeric_id),
            "responsable": responsable if isinstance(responsable, str) and responsable else None,
        })
    return sorted(rows, key=lambda r: (-len(r["libere"]), numeric_id(r["tache"])))


def compute(
    root: Path,
    state: str | None,
    chantier: str | None,
    explicit: list[str] | None,
) -> dict[str, Any]:
    board = load_board(root)
    by_id = {t["id"]: t for t in board}

    if explicit:
        unknown = [t for t in explicit if t not in by_id]
        if unknown:
            raise WavesError(
                f"id inconnu au board : {', '.join(unknown)} — un id qui ne résout pas "
                f"est un refus, jamais un périmètre silencieusement plus petit"
            )
        selected = sorted(explicit, key=numeric_id)
    else:
        selected = sorted(
            (
                t["id"]
                for t in board
                if (state is None or t["state"] == state)
                and (chantier is None or (t.get("chantier") or "") == chantier)
            ),
            key=numeric_id,
        )

    perimeter, pulled_by, walls = close_perimeter(selected, by_id)

    # Le cycle est cherché SUR LE PÉRIMÈTRE FERMÉ, pas sur tout le board : un
    # cycle dans un coin qu'on ne planifie pas ne doit pas bloquer ce relevé.
    graph = {tid: [d for d in depends_on_of(by_id.get(tid) or {}) if d in perimeter]
             for tid in perimeter}
    cycles = find_cycles(graph)
    if cycles:
        return {
            "cycles": cycles,
            "perimetre": perimeter,
            "coupes": [_coupe_du_cycle(c, by_id) for c in cycles],
        }

    waves, unreachable = build_waves(perimeter, by_id)
    return {
        "cycles": [],
        "demandees": selected,
        "perimetre": perimeter,
        "tirees_par": pulled_by,
        "murs": walls,
        "vagues": [
            {
                "rang": i,
                "taches": wave,
                "bottes": bundle_wave(wave, by_id)[0],
                "serialisees": [
                    {"tache": t, "raison": r} for t, r in bundle_wave(wave, by_id)[1]
                ],
            }
            for i, wave in enumerate(waves, start=1)
        ],
        "hors_vagues": [
            {"tache": t, "dependance": d, "raison": r} for t, d, r in unreachable
        ],
        # Clés ADDITIVES (D2, T-01M54GEHJBGA5996W0T48JXNQ4) : absentes du résultat CYCLE.
        "chemin_critique": critical_path(waves, by_id),
        "liberations": liberations(waves, by_id),
    }


def render(result: dict[str, Any]) -> int:
    if result["cycles"]:
        print("CYCLE — aucune vague n'est produite.\n", file=sys.stderr)
        for cycle in result["cycles"]:
            print(f"  {' → '.join(cycle)}", file=sys.stderr)
        print(
            "\nUn ordre partiel qui a l'air complet est pire que pas d'ordre du tout.\n"
            "Remède, et il TOURNE (le board charge un cycle par choix) — il retire UNE\n"
            "arête, jamais la déclaration entière (T-00000765) :",
            file=sys.stderr,
        )
        for coupe in result.get("coupes", []):
            # Un id du board est une DONNÉE : chaque commande imprimée le passe par
            # `shlex.quote`, la SUGGESTION entière aussi (entre `"…"`, un `$(…)` vivrait).
            # Bornes : quotage POSIX — collé dans PowerShell ou cmd, `'…'` n'est pas leur
            # échappement ; un id qui commence par `-` est lu comme une option par `depends`
            # et `specs.py add` (refus argparse rc 2, ou l'aide rc 0 pour `-h` ; jamais une
            # écriture) ; un caractère de contrôle (ESC) dans un id n'est pas neutralisé
            # par `shlex.quote` — non couvert ici.
            q_aval, q_amont = shlex.quote(coupe["aval"]), shlex.quote(coupe["amont"])
            if coupe["ordre_pilote_seul"]:
                # Toutes les arêtes du cycle sont des ORDRES PILOTE : un agent n'en
                # retire aucun. La route est une SUGGESTION que le pilote tranche.
                suggestion = shlex.quote(f"SUGGESTION: retirer {coupe['aval']} <- {coupe['amont']}")
                print(
                    f"  toutes les arêtes de ce cycle sont des ORDRE PILOTE — route :\n"
                    f"  python .agents/bin/specs.py add --task {q_aval} --kind delta "
                    f"{suggestion} --text \"<pourquoi>\"\n"
                    f"  puis, après décision du pilote :\n"
                    f"  python .agents/bin/tasks.py depends {q_aval} "
                    f"--retirer-ordre-pilote {q_amont} S-<décision du pilote>",
                    file=sys.stderr,
                )
                continue
            restes = ", ".join(f"{d} ({repr(m) if m else 'héritée'})" for d, m in coupe["restes"])
            suite = f" (restent : {restes})" if restes else " (c'était sa seule arête)"
            print(
                f"  python .agents/bin/tasks.py depends {q_aval} --retirer {q_amont}{suite}",
                file=sys.stderr,
            )
        return EXIT_CYCLE

    demandees, perimetre = result["demandees"], result["perimetre"]
    pulled = result["tirees_par"]
    if not perimetre:
        print("(aucune tâche dans le périmètre demandé)")
        return EXIT_OK

    if pulled:
        print(
            f"FERMETURE — {len(demandees)} demandée(s), {len(perimetre)} planifiée(s) : "
            f"{len(pulled)} tirée(s) par dépendance."
        )
        for tid in sorted(pulled, key=numeric_id)[:WAVES_MAX_ROWS]:
            print(f"  {tid:<12} tirée par {pulled[tid]}")
        if len(pulled) > WAVES_MAX_ROWS:
            print(
                f"  … tronqué : {WAVES_MAX_ROWS} lignes sur {len(pulled)} tirées "
                f"— --json pour la totalité"
            )
        print()

    for wave in result["vagues"]:
        rang, taches = wave["rang"], wave["taches"]
        behind = "" if rang == 1 else f" (derrière la vague {rang - 1})"
        print(f"VAGUE {rang} — {len(taches)} tâche(s){behind}")
        for bundle in wave["bottes"]:
            print(f"  botte (parallélisme PROPOSÉ, non prouvé ici) : {' '.join(bundle)}")
            # Ids quotés (POSIX), et `--` : un id qui commence par `-` reste un id, jamais une option.
            print(f"      python .agents/bin/tasks.py parallel -- {' '.join(map(shlex.quote, bundle))}")
        for row in wave["serialisees"]:
            print(f"  {row['tache']:<12} sérialisée : {row['raison']}")

    if result["murs"]:
        print(f"\nMURS — {len(result['murs'])} branche(s) arrêtée(s) sur une tâche blocked")
        for dependent, dep in result["murs"]:
            print(f"  {dependent:<12} dépend de {dep} (blocked — attend une décision)")

    if result["hors_vagues"]:
        print(f"\nHORS VAGUES — {len(result['hors_vagues'])} tâche(s)")
        for row in result["hors_vagues"][:WAVES_MAX_ROWS]:
            print(f"  {row['tache']:<12} dépend de {row['dependance']} — {row['raison']}")
        if len(result["hors_vagues"]) > WAVES_MAX_ROWS:
            print(
                f"  … tronqué : {WAVES_MAX_ROWS} lignes sur {len(result['hors_vagues'])} "
                f"— --json pour la totalité"
            )

    # APRÈS vagues, murs et hors-vagues : chaque id y a déjà paru (premières
    # occurrences intactes, `avant()` de plan_waves.test.sh).
    chemin = result.get("chemin_critique") or []
    if chemin:
        print(f"\nCHEMIN CRITIQUE — {len(chemin)} tâche(s) : {' → '.join(_id_imprime(t) for t in chemin)}")
    else:
        print("\nCHEMIN CRITIQUE — aucune dépendance entre les tâches placées (aucune libération)")
    libs = result.get("liberations") or []
    if libs:
        print(f"\nLIBERATIONS — {len(libs)} tâche(s) en libèrent d'autres, la plus libérante d'abord")
        for row in libs[:WAVES_MAX_ROWS]:
            ids = row["libere"]
            vus = ", ".join(_id_imprime(t) for t in ids[:LIBERE_MAX_IDS])
            if len(ids) > LIBERE_MAX_IDS:
                vus += f", … +{len(ids) - LIBERE_MAX_IDS}"
            resp = row.get("responsable")
            # Donnée du board, texte libre : seuls ses caractères imprimables sortent.
            qui = f" — responsable : {''.join(c for c in resp if c.isprintable())}" if resp else ""
            print(f"  {_id_imprime(row['tache']):<12} libère {len(ids)} ({vus}) dont "
                  f"{len(row['directes'])} directe(s){qui}")
        if len(libs) > WAVES_MAX_ROWS:
            print(f"  … tronqué : {WAVES_MAX_ROWS} lignes sur {len(libs)} — --json pour la totalité")

    # Le relevé dit ce qu'il EST, à chaque appel. `NON-AUTORITATIF` en ASCII et
    # d'un seul tenant : c'est le marqueur sur lequel le banc asserte, et un
    # motif accentué se compare mal sous une console Windows en cp1252.
    print(
        f"\n{len(result['vagues'])} vague(s) sur {len(perimetre)} tâche(s). "
        f"RELEVE AMONT, NON-AUTORITATIF : /night reconstruit son ordre lui-même, "
        f"et la disjonction des bottes n'est PROUVEE que par `tasks.py parallel`."
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sorts the board into waves on depends_on (read only). "
        "NOT AUTHORITATIVE on the order of a night run - see the file header.",
        epilog="exit codes: 0 waves produced - 1 runtime error - 2 usage - 3 CYCLE",
    )
    ap.add_argument("--root", default=".", help="repository root (default: .) - used by the tests")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_waves = sub.add_parser("waves", help="wave decomposition of the scope")
    p_waves.add_argument(
        "--state",
        default="pending",
        help="scope by state (default: pending - the one a night run consumes)",
    )
    p_waves.add_argument("--workstream", "--chantier", dest="chantier", default=None, metavar="WORKSTREAM",
                         help="restrict to one workstream (old name: --chantier)")
    p_waves.add_argument(
        "--task",
        action="append",
        default=None,
        metavar="T-NNN",
        help="EXPLICIT scope, repeatable; still closed over depends_on",
    )
    p_waves.add_argument("--json", action="store_true", help="full JSON, not truncated")

    args = ap.parse_args(argv)
    force_utf8_stdio()
    root = Path(os.fspath(args.root))
    try:
        result = compute(root, args.state, args.chantier, args.task)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_CYCLE if result["cycles"] else EXIT_OK
        return render(result)
    except WavesError as exc:
        print(f"plan_waves: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
