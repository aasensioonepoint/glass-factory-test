"""L'API D'INIT DU PAQUET — `cadre init`, PREMIER TIERS (T-00000968, BK-120),
ET L'IDENTITÉ DU PROJET RELOGÉE DE `project_init.py` (T-00000969, BK-121).

DEUX VERSANTS, UNE SEULE ENTRÉE D'INIT À TERME. `initialiser` (ci-dessous,
T-00000968) crée les stores de l'adoptant. `principal_project_init` (T-00000969)
porte la logique de `.agents/bin/project_init.py`, qui n'est plus qu'un
DÉLÉGATEUR (amorçage de `cadre`, ré-exports nommés, fournisseur du board,
`main`) : mêmes drapeaux, mêmes messages, mêmes canaux, mêmes codes — tenu
octet pour octet par le golden I11 de `test_cadre_init.py`, relevé AVANT le
relogement. Divergence DÉCIDÉE — décision pilote, tags git
decision/T-00000969/01 (0644 partout) et /02 (umask respecté) : après
`--rename`, `project.json` est REPOSÉ en 0644 (`Workspace.write_bytes(...,
mode=0o644)`, masqué par l'umask comme à la création, donc 0600 sous 077),
même depuis un 0600, là où l'ancien `mkstemp` le passait en 0600. Les AUTRES
écarts, tous sur des liens, sont bornés ci-dessous (BORNES
DU RELOGEMENT) ; le contrat en processus de `main`, dans sa docstring
(`project_init.py`).

  * la racine de l'identité est celle de git depuis le répertoire courant
    (`paths._git_toplevel`), repli sur le répertoire courant — JAMAIS
    `project_root()` : `$CADRE_PROJECT_ROOT` y est IGNORÉ, comme avant (I17) ;
  * `git config user.name` passe par un `Executor` (borne 5 s) ;
  * le board appartient à `tasks`, que ce paquet n'importe JAMAIS : il est
    INJECTÉ (`FournisseurBoard`) ; sans fournisseur, la branche ATTENTION le
    dit, et `--ensure-stores` rend 2 ;
  * un refus est une `RefusIdentite`, rendue `project_init: <cause>` sur
    stderr, code 2, par l'entrée — jamais un traceback.

BORNES DU RELOGEMENT, écrites parce que `Workspace` CONFINE là où l'ancien code
suivait les liens sans juger. Un `project.json` LIEN HORS RACINE est refusé en 2
(« supprimer le lien puis rejouer »), rien écrit, par l'init, `--rename` et
`--print-otel-env` — l'ancien lisait au travers et, au `--rename`, REMPLAÇAIT le
lien par un fichier. Un lien DANS la racine voit sa CIBLE réécrite par
`--rename`, le lien restant (témoin I19). `.claude/settings.json` n'est plus
lu du tout, lien ou non (T-01M4WNKCBXS893CHPSKD1Z1PN9) : `--print-otel-env`
n'en rend rien, stderr vide (témoin I15) — l'ancien relevait la cible. Un
`.agents/kit.lock` lien hors racine est jugé AU BOUT du lien (existence seule,
rien lu, `_juge`) : « présent » si la cible est un fichier, comme l'ancien
(témoin I21). Un `project.json` dont un RÉPERTOIRE parent (`.agents`,
`.agents/state`) est un lien hors racine reçoit le même refus en 2 à l'init
(témoin I20) — l'ancien créait identité, board et vue DANS la cible. Un BOARD
qui résout hors racine (le fichier, ou un répertoire parent, en lien) est jugé
au bout du lien : un board y EXISTE, « board deja present — inchange », lien et
cible intacts, comme l'ancien ; AUCUN board au bout (lien pendant, cible vide),
ATTENTION en 2, rien écrit, « supprimer le lien puis rejouer » (témoins I20) —
l'ancien remplaçait un lien fichier pendant par un board neuf, écrivait le
board HORS racine dans une cible répertoire ou sous un parent lien, et tombait
en ATTENTION sur un répertoire pendant.

CE QUE `initialiser` FAIT, ET RIEN DE PLUS. Il résout la racine du projet
(`cadre.paths.project_root`) et y crée — ou y monte, idempotent — les trois
stores de l'adoptant par `cadre.ledger.stores.creer_les_stores`, l'API de la
wheel (T-00000646). C'est le premier appelant de production de cette API.

CE QU'IL NE FAIT PAS ENCORE, ÉCRIT POUR QU'AUCUN LECTEUR NE LE CROIE FAIT. Les
surfaces de l'adoptant — gabarits, doctrine, déclarations natives par hôte
(`settings.json`, `hooks.json`…) — ne sont PAS posées : elles sont le deuxième
tiers de T-00000756 (BK-124), qui les posera par cette même API. `kit.lock`, que
la note du verrou promet pour `cadre init`, n'est pas écrit non plus. Le nom
`cadre init` reste donc `reserve` au verrou (`contract.lock.json`) : la bascule
publique suit le câblage complet, et elle est portée par T-00000756.
`events.db` naît SOUS la racine (`.agents/state/local/events.db`), contre le
critère de recette « aucun fichier SQLite dans le dépôt cible, suivi ou non »
(`docs/PROMPT-refonte-packaging-cadre.md:37-39`) : T-00000755 le déplace sous la
partition machine. Le `.gitignore` que T-00000971 doit poser (gabarit de
`init_surfaces.rendre_gitignore`) ignore `/.agents/state/local/` — ignoré n'est
pas absent : le critère compte aussi les fichiers non suivis.

`--host` EST VALIDÉ, PAS ENCORE EXPLOITÉ. L'hôte demandé est contrôlé contre la
liste fermée `cadre.config.HOTES` AVANT toute écriture, puis rendu dans
`InitFaite.hote` ; aucun réglage propre à l'hôte n'est écrit par ce tiers. Les
stores ne dépendent pas de l'hôte.

LA RACINE EST TRANSMISE TELLE QUELLE À `creer_les_stores`. Résoudre ici
`project_root(depuis=racine)` avant l'appel ferait gagner `$CADRE_PROJECT_ROOT`
sur l'argument EN SILENCE : les stores naîtraient ailleurs que là où l'appelant
l'a demandé. Transmise telle quelle, une racine divergente est REFUSÉE par
`chemins_des_stores` (`CadrePathError`), sans rien créer.

IDEMPOTENCE. Deux appels successifs ne changent aucun octet, ni sous la racine
ni sous la partition machine : c'est la propriété de `creer_les_stores`
(`IdempotenceTests` de `test_cadre_ledger_stores.py`), rejouée de bout en bout,
par la CLI, dans `test_cadre_init.py`.

AUCUNE E/S HORS `Workspace`. Ce module DÉCIDE : il est couvert par le filet de
pureté du paquet (`test_cadre_package.py`). La seule lecture propre
d'`initialiser` est `Workspace.est_repertoire` sur la racine (garde
ci-dessous) ; toute écriture passe par `creer_les_stores`, donc par `Workspace`
et `store.ouvrir_sans_suivre`. Le versant identité lit et écrit par un
`atelier: Workspace`, lance `git` par un `Executor` et par `paths`, et n'écrit
sur `sys.stdout`/`sys.stderr` que les messages de sa CLI.

LA RACINE DOIT EXISTER. `project_root` rend `$CADRE_PROJECT_ROOT` canonisé SANS
vérifier qu'il existe, et `creer_les_stores` crée les répertoires parents d'un
store : sans garde, une variable mal tapée faisait naître un arbre entier — et
la partition machine qui va avec — sous un chemin que personne n'a demandé,
code 0 (mesuré). `cadre init` s'installe dans un projet, il ne le crée pas : une
racine absente ou qui n'est pas un répertoire est REFUSÉE avant toute écriture.

REFUS. `HoteInconnu` (fille de `ValueError`) pour un hôte hors liste, levé avant
toute écriture ; `CadrePathError` pour tout le reste — racine introuvable (dont
un répertoire sans git ni `.agents/` hors `$CADRE_PROJECT_ROOT`, refusé par
`project_root`, témoin I6, contre `init_surfaces.py:21-23`, qui écrit qu'`init`
peut tourner sur un répertoire sans `git init` ; arbitrage BK-124), racine
absente ou non-répertoire, racine illisible (la `RuntimeError` d'une boucle de
liens que `Path.resolve()` lève en 3.11/3.12, CONVERTIE ici, témoin I10),
racine divergente, store refusé (`creer_les_stores` traduit ses propres
refus) ; `ValueError` ou `OSError` restent possibles hors de cette traduction
(`est_repertoire` lève `PermissionError` sur une racine non traversable). La
CLI les rend en code 2, jamais en traceback.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from cadre.config import HOTES, HoteInconnu
from cadre.executor import Executor, LocalExecutor
from cadre.ledger.stores import StoresCrees, creer_les_stores
from cadre.paths import CadrePathError, _git_toplevel, project_root
from cadre.workspace import HorsRacine, Workspace

__all__ = ["InitFaite", "initialiser",
           "IDENTITE_RELATIVE", "RefusIdentite", "FournisseurBoard",
           "resoudre_racine_projet", "chemin_identite", "slugifier",
           "creer_identite_exclusive", "reecrire_champ", "provisionner_stores",
           "initialiser_identite", "env_otel", "publier_otel", "renommer",
           "principal_project_init"]


@dataclass(frozen=True)
class InitFaite:
    """Ce que `initialiser` a fait : la racine CANONIQUE du projet, les chemins
    absolus des trois stores créés ou montés, et l'hôte demandé (validé, non
    exploité par ce tiers), `None` quand aucun n'a été demandé."""

    racine: Path
    stores: StoresCrees
    hote: str | None


def initialiser(racine: str | os.PathLike[str] | None = None, *,
                hote: str | None = None) -> InitFaite:
    """Crée (ou monte, idempotent) les trois stores du projet de `racine`.

    `racine` vaut par défaut la racine résolue depuis le répertoire courant
    (`project_root()`), résolue ICI, à l'appel, jamais à l'import. Une racine
    fournie est transmise TELLE QUELLE à `creer_les_stores`, qui refuse une
    divergence avec `$CADRE_PROJECT_ROOT` ou la racine git.

    `hote` est contrôlé contre `HOTES` AVANT toute résolution ou écriture. La
    racine doit EXISTER et être un répertoire, sinon `CadrePathError` avant
    toute écriture.
    """
    if hote is not None and hote not in HOTES:
        raise HoteInconnu(
            f"hôte inconnu : {hote!r}. Liste fermée : {' | '.join(HOTES)}. "
            "Aucun store n'a été créé."
        )
    # Python 3.11/3.12 : `Path.resolve()` LÈVE `RuntimeError` sur une boucle de
    # liens symboliques — dans `project_root()` (`$CADRE_PROJECT_ROOT` y est
    # résolu) comme dans `Workspace(cible)` (mesuré 3.12.14, `a -> b -> a`) ;
    # en 3.14.7 (mesuré) `resolve` ne lève pas et `est_repertoire` rend faux
    # (ELOOP) — 3.11 et 3.13 non mesurés ici, bornés par la doc de
    # `Workspace.est_repertoire`. Convertie
    # ici, l'API et la CLI refusent pareil, sans traceback. `CadrePathError`
    # DÉRIVE de `RuntimeError` : relevée telle quelle AVANT, sans quoi « racine
    # de projet introuvable » deviendrait « illisible ».
    try:
        cible = project_root() if racine is None else racine
        atelier: Workspace = Workspace(cible)
    except CadrePathError:
        raise
    except RuntimeError as exc:
        demandee = racine if racine is not None else "$CADRE_PROJECT_ROOT ou le répertoire courant"
        raise CadrePathError(
            f"racine {demandee} illisible ({type(exc).__name__}: {exc}) : aucun "
            "store n'est créé. Une boucle de liens symboliques en est la cause "
            "connue — corrigez le chemin, ou $CADRE_PROJECT_ROOT."
        ) from None
    if not atelier.est_repertoire():
        raise CadrePathError(
            f"racine {Path(cible)} introuvable ou n'est pas un répertoire : "
            "aucun store n'est créé. `cadre init` s'installe dans un projet, il "
            "ne le crée pas — placez-vous dedans, ou corrigez $CADRE_PROJECT_ROOT."
        )
    stores = creer_les_stores(cible)
    return InitFaite(racine=project_root(depuis=cible), stores=stores, hote=hote)


# --- L'IDENTITÉ DU PROJET (T-00000969 : logique relogée de project_init.py) ---
#
# Ce que l'en-tête historique de `project_init.py` établissait, et qui tient ici :
#   * `.agents/state/project.json` est git-ignoré, généré SUR PLACE, JAMAIS
#     copié : hérité d'un clone ou d'un fork, il se supprime puis se ré-inite ;
#   * champs GELÉS — `project_id` (uuid4, seule clé infalsifiable d'une fusion
#     distante), `slug` (dérivé du nom À L'INIT, gelé au `--rename`, C4 : il
#     clé des chemins machine), `created` (ISO-8601 UTC) ; MUTABLE — `name`,
#     réécrit par `--rename` SEUL, et NON affiché par le tableau de bord depuis
#     T-00000582 (il montre le basename du répertoire) ; AUCUN champ `user` ;
#     `kit_version` RETIRÉ (T-00000594 : `.agents/kit.lock` la porte) ;
#   * STORES À L'INIT (décision D7) : le board SEUL est provisionné, parce que
#     son ABSENCE rougit une porte par un lecteur tiers
#     (`check-stale-justification.sh`) ; sa vue suit ; `v3_event_store.db`,
#     `index.db`, SPECS et LEDGER restent PARESSEUX. Le board est écrit APRÈS
#     l'identité et JAMAIS écrasé (garde d'existence) : `--ensure-stores` est
#     idempotent ;
#   * ATOMICITÉ : la création passe par `O_CREAT|O_EXCL`, seul arbitre (N inits
#     concurrentes, UN gagnant), le partiel retiré sur toute `BaseException`
#     (`Workspace.ecrire_fichier_exclusif`) ; la réécriture par temporaire,
#     `fsync`, puis `os.replace` repris sur `PermissionError`
#     (`Workspace.write_bytes(..., reprises=True)`, L-00000054), le temporaire
#     retiré lui aussi sur toute `BaseException` (Ctrl-C pendant `--rename`).

#: L'identité, RELATIVE à la racine du projet.
IDENTITE_RELATIVE = Path(".agents") / "state" / "project.json"
_VERROU_RELATIF = Path(".agents") / "kit.lock"
_INVITE = "Nom du projet : "
_RELANCER = "lancer d'abord: python .agents/bin/project_init.py"
_CORROMPU = ("project.json présent mais corrompu (écriture partielle ?) — supprimer "
             ".agents/state/project.json puis ré-initer")
#: Réserve C4 du plan-critic : `Workspace` refuse ce que l'ancien suivait. Le
#: lien peut être un RÉPERTOIRE parent (`.agents`, `.agents/state`) : le dire.
_LIEN_HORS_RACINE = ("project.json, ou l'un de ses répertoires parents, est un lien "
                     "hors racine — supprimer le lien puis rejouer")
_AVERTISSEMENT_NOM = (
    "project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le "
    "basename du répertoire du dépôt, pas ce champ ; --name (ou l'invite) ne "
    "remplit que project.json:name, écrit et NON affiché. Pour choisir le nom "
    "affiché, nommez le répertoire du dépôt.\n")
_AVERTISSEMENT_RENOM = (
    "project_init: AVERTISSEMENT — depuis T-00000582 le dashboard affiche le "
    "basename du répertoire du dépôt, pas ce champ ; --rename ne change plus "
    "l'affichage. Pour renommer le projet affiché, renommez son répertoire.\n")


class RefusIdentite(Exception):
    """Un refus NOMMÉ du flux d'identité — cause et remède dans le message.
    `principal_project_init` le rend `project_init: <message>` sur stderr, code
    2 ; rien n'est écrit sur le chemin qui le lève."""


class FournisseurBoard(Protocol):
    """Le board appartient à `tasks` (`.agents/bin/`), que `cadre` n'importe
    jamais : son PROPRIÉTAIRE est injecté. `chemins` rend `(store, vue)`
    absolus sous `racine` ; `creer` écrit le board VIDE canonique et sa vue —
    la forme est demandée au propriétaire, jamais recopiée ici."""

    def chemins(self, racine: Path) -> tuple[Path, Path]: ...

    def creer(self, racine: Path) -> None: ...


def resoudre_racine_projet() -> Path:
    """La racine git du répertoire COURANT, repli sur le répertoire courant ;
    rendue résolue. `$CADRE_PROJECT_ROOT` n'y entre pas (I17) : c'est la
    racine qu'avait `project_init.py`, pas celle de `project_root()`."""
    depart = os.getcwd()
    haut = _git_toplevel(depart)
    return Workspace(haut if haut else depart).racine


def chemin_identite(racine: Path) -> Path:
    """`<racine>/.agents/state/project.json` (ré-exporté `project_json_path`)."""
    return Path(racine) / IDENTITE_RELATIVE


def slugifier(nom: str) -> str:
    """Slug fs/URL : minuscules, toute suite non alphanumérique ramenée à un
    seul `-`, bords rognés ; un résultat vide retombe sur `project`, pour
    qu'une clé gelée ne soit jamais la chaîne vide (ré-exporté `slugify`)."""
    slug = re.sub(r"[^a-z0-9]+", "-", nom.strip().lower()).strip("-")
    return slug or "project"


def _lire_json(atelier: Workspace, relatif: Path) -> dict | None:
    """Le JSON objet de `relatif` ; `None` s'il est absent, illisible, mal
    formé ou pas un objet. `HorsRacine` (un lien qui sort) est RELEVÉE, jamais
    lue comme une absence — c'est une `ValueError`, donc nommée d'abord."""
    try:
        donnees = json.loads(atelier.read_text(relatif))
    except HorsRacine:
        raise
    except (OSError, ValueError):
        return None
    return donnees if isinstance(donnees, dict) else None


def _corps(donnees: dict) -> bytes:
    return (json.dumps(donnees, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def creer_identite_exclusive(chemin: Path, donnees: dict) -> None:
    """Crée l'identité `chemin` (= `chemin_identite(racine)`) avec `donnees`,
    EXCLUSIVEMENT : `FileExistsError` si le nom est pris (le diagnostic est à
    l'appelant) ; toute `BaseException` en cours d'écriture retire le partiel.
    Le répertoire parent est créé au besoin. Signature héritée de
    `_atomic_create`, ré-exportée sous ce nom (C1) ; `ValueError` sur un
    chemin qui n'est pas un chemin d'identité."""
    chemin = Path(chemin)
    n = len(IDENTITE_RELATIVE.parts)
    if chemin.parts[-n:] != IDENTITE_RELATIVE.parts:
        raise ValueError(f"{chemin} n'est pas un chemin d'identité "
                         f"(<racine>/{IDENTITE_RELATIVE.as_posix()})")
    atelier: Workspace = Workspace(chemin.parents[n - 1])
    atelier.creer_repertoire(IDENTITE_RELATIVE.parent)
    if atelier.ecrire_fichier_exclusif(IDENTITE_RELATIVE, _corps(donnees), mode=0o644) is None:
        raise FileExistsError(errno.EEXIST, "identité déjà présente", str(chemin))


def _refus_de_collision(atelier: Workspace) -> RefusIdentite:
    """`O_EXCL` a perdu : deux diagnostics, un remède — valide (porte un
    `project_id`) : déjà initialisée ; sinon : corrompue."""
    try:
        donnees = _lire_json(atelier, IDENTITE_RELATIVE)
    except HorsRacine:
        return RefusIdentite(_LIEN_HORS_RACINE)
    if donnees is not None and donnees.get("project_id"):
        return RefusIdentite(
            f"identité déjà initialisée (project_id={donnees['project_id']} ; si "
            "héritée d'un clone/fork, supprimer .agents/state/project.json puis "
            "ré-initer)")
    return RefusIdentite(_CORROMPU)


def reecrire_champ(atelier: Workspace, cle: str, valeur: object) -> dict:
    """Réécrit UN champ mutable de l'identité, les champs gelés intacts ; rend
    l'identité réécrite. `RefusIdentite` si elle est absente ou corrompue ;
    `HorsRacine` relevée si `project.json` est un lien qui sort. Écriture par
    `write_bytes(reprises=True, mode=0o644)` : l'identité est REPOSÉE en 0644,
    masqué par l'umask comme à la création, même depuis un 0600 — décision
    pilote, tags git decision/T-00000969/01 (0644 partout) et /02 (umask
    respecté)."""
    donnees = _lire_json(atelier, IDENTITE_RELATIVE)
    if donnees is None:
        if not atelier.exists(IDENTITE_RELATIVE):
            raise RefusIdentite("aucune identité à modifier (.agents/state/project.json "
                                f"absent) — {_RELANCER}")
        raise RefusIdentite(_CORROMPU)
    donnees[cle] = valeur
    atelier.write_bytes(IDENTITE_RELATIVE, _corps(donnees), reprises=True, mode=0o644)
    return donnees


def _relatif(racine: Path, chemin: Path) -> str:
    """Chemin montré au pilote : relatif à la racine, séparateurs POSIX."""
    try:
        return chemin.relative_to(racine).as_posix()
    except ValueError:
        return chemin.as_posix()


def _attention(cause: object) -> str:
    return (f"ATTENTION — board non provisionne ({cause}) ; "
            "lancer: python3 .agents/bin/project_init.py --ensure-stores\n")


def _juge(atelier: Workspace, chemin: Path) -> Workspace:
    """Le lecteur qui JUGE l'existence de `chemin` : l'atelier s'il résout
    sous la racine ; sinon un lecteur ancré à la racine du système de fichiers
    (`chemin.anchor`), pour un `stat` AU BOUT du lien hors racine, comme la
    base (`Path.exists`, `Path.is_file`, lien suivi) — existence seule, jamais
    une lecture ni une écriture. `Workspace.exists` avale `HorsRacine` en
    faux : sans ce lecteur, un lien hors racine serait dit ABSENT."""
    try:
        atelier.resolve(chemin)
    except HorsRacine:
        return Workspace(Path(chemin).anchor)
    return atelier


def _store_present(atelier: Workspace, store: Path) -> bool:
    """Garde d'existence d'un store : vrai s'il est là, y compris AU BOUT d'un
    lien hors racine (le fichier, ou un répertoire parent, en lien) ;
    `HorsRacine` NOMMÉE si le chemin sort de la racine SANS rien au bout.

    Deux faux mesurés. `Workspace.exists` seul avalait `HorsRacine` en faux :
    un board lien hors racine passait pour ABSENT, et `creer` remplaçait le
    lien par une copie ou réécrivait la cible extérieure (443dad15,
    exec-critic). Lu « présent » sans juger la cible (be8dc812), un lien
    PENDANT ou une cible VIDE rendait « board deja present », code 0, sans
    board nulle part — le faux vert du geste de réparation que prescrit
    `check-stale-justification.sh` (critic-opus, clôture). Jugé au bout
    (`_juge`) : présent, rien écrit ; absent, ATTENTION en 2 par l'appelant."""
    lecteur: Workspace = _juge(atelier, store)
    if lecteur.exists(store):
        return True
    if lecteur is not atelier:
        raise HorsRacine(f"{_relatif(atelier.racine, store)} : lien hors racine (le "
                         "fichier ou un répertoire parent) sans board au bout — "
                         "supprimer le lien puis rejouer")
    return False


def provisionner_stores(atelier: Workspace, board: FournisseurBoard | None) -> int:
    """Provisionne le board s'il manque, JAMAIS ne l'écrase. Rend 0 si un board
    est sur disque (créé, ou déjà là — y compris au bout d'un lien hors racine,
    laissé intact) ; 2 si le provisionnement a ÉCHOUÉ, dont un chemin de board
    qui sort de la racine SANS board au bout (ATTENTION, rien écrit,
    `_store_present`) — l'init garde son 0 (l'identité est écrite),
    `--ensure-stores` seul rend ce 2.

    `except Exception` LARGE, VOULU : l'identité est déjà sur disque quand ceci
    tourne, aucune panne d'un store secondaire ne doit la coûter ; la panne est
    NOMMÉE (cause + commande de réparation), jamais avalée. Sans fournisseur,
    la même branche le dit."""
    racine = atelier.racine
    if board is None:
        sys.stderr.write(_attention("aucun fournisseur de board injecté : le board "
                                    "appartient à tasks, que cadre n'importe pas"))
        return 2
    try:
        store, vue = board.chemins(racine)
        if _store_present(atelier, store):
            sys.stdout.write("board deja present — inchange\n")
        else:
            board.creer(racine)
            sys.stdout.write(f"board cree: {_relatif(racine, store)} "
                             f"(+ vue {_relatif(racine, vue)}, git-ignoree)\n")
    except Exception as exc:  # noqa: BLE001 — voir la docstring
        sys.stderr.write(_attention(exc))
        return 2
    sys.stdout.write("RESTE A FAIRE : /index · /skills-sync\n")
    sys.stdout.write("magasins paresseux (normaux a l absence) : "
                     "v3_event_store.db · index.db (machine, hors depot : "
                     "state_project()/index/index.db)\n")
    return 0


def _nom_demande(atelier: Workspace, demander: Callable[[str], str] | None) -> str:
    """Le nom DEMANDÉ ; sans saisie possible, le basename de la racine.

    Trois cas sans saisie (T-00001103) : `EOFError` (stdin vide,
    `</dev/null`) ; stdin fermé (`0<&-`), où Python pose `sys.stdin is None`
    et `input` lève `RuntimeError: lost sys.stdin` (mesuré) — le même
    `except` couvre les deux. Une ligne LUE, même vide, est rendue telle
    quelle : l'appelant refuse le vide. L'avis stderr nomme la seule
    correction, `--rename`."""
    try:
        return (input if demander is None else demander)(_INVITE).strip()
    except (EOFError, RuntimeError):
        return _nom_par_defaut(atelier)


def _nom_par_defaut(atelier: Workspace) -> str:
    nom = atelier.racine.name
    sys.stderr.write(f"project_init: aucun nom saisi (stdin vide ou fermé) — nom par "
                     f"défaut « {nom} » (basename du dépôt) ; pour le changer : "
                     f"python .agents/bin/project_init.py --rename \"<nom>\"\n")
    return nom


def initialiser_identite(atelier: Workspace, nom: str | None, *,
                         board: FournisseurBoard | None,
                         executeur: Executor | None = None,
                         demander: Callable[[str], str] | None = None) -> int:
    """Crée l'identité du projet `atelier.racine`, puis provisionne le board.

    `git config user.name` est vérifié NON VIDE AVANT toute écriture ; `nom`
    absent est DEMANDÉ (`input` par défaut) ; une ligne lue mais vide après
    rognage est refusée. Sans saisie possible (stdin vide, fermé ou absent :
    `_nom_demande`), le nom par défaut est le basename de la racine, avis sur
    stderr (T-00001103). Le board vient en DERNIER : jamais atteint sur un
    refus, et son échec ne défait pas une identité écrite (code 0 gardé)."""
    executeur = LocalExecutor() if executeur is None else executeur
    auteur = executeur.run(["git", "config", "user.name"], cwd=atelier.racine, timeout=5)
    if not (auteur.ok and auteur.stdout.strip()):
        raise RefusIdentite("git user.name est vide — configure git user.name avant "
                            "d'initialiser (git config user.name \"Ton Nom\")")
    if nom is None:
        nom = _nom_demande(atelier, demander)
    nom = nom.strip()
    if not nom:
        raise RefusIdentite("le nom du projet ne peut pas être vide (--name)")
    donnees = {
        "project_id": str(uuid.uuid4()),
        "name": nom,
        "slug": slugifier(nom),
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        creer_identite_exclusive(chemin_identite(atelier.racine), donnees)
    except FileExistsError:
        raise _refus_de_collision(atelier) from None
    except HorsRacine:
        raise RefusIdentite(_LIEN_HORS_RACINE) from None
    sys.stdout.write(f"project_init: identité créée — {donnees['name']} "
                     f"(project_id={donnees['project_id']}, slug={donnees['slug']})\n")
    sys.stderr.write(_AVERTISSEMENT_NOM)
    provisionner_stores(atelier, board)
    return 0


def env_otel(atelier: Workspace, project_id: str) -> dict[str, str]:
    """L'objet `env` à coller dans `.claude/settings.local.json` : la SEULE
    clé d'identité `OTEL_RESOURCE_ATTRIBUTES` (T-01M4WNKCBXS893CHPSKD1Z1PN9).
    `.claude/settings.json` n'est plus lu : Claude Code 2.1.299 refuse les
    cinq clés d'activation en portée projet ET locale (`… is ignored`, mesuré),
    elles vivent en portée UTILISATEUR ; et l'`env` des portées fusionne clé
    par clé (mesuré), donc un objet complet n'est plus nécessaire. `atelier`
    reste pour la signature publique (`__all__`), rien n'y est lu."""
    del atelier
    return {"OTEL_RESOURCE_ATTRIBUTES": f"agentkit.project_id={project_id}"}


def publier_otel(atelier: Workspace, fmt: str = "both") -> int:
    """Imprime le bloc d'attribution de CE projet (V1-c, T-00000050) : forme
    `shell` (direnv, profil), `json` (PUR, pour `settings.local.json`, la
    seule clé d'identité : `env_otel`) ou `both` (shell D'ABORD, inchangé,
    puis le JSON). LECTURE SEULE. Sans identité, refus et AUCUNE forme
    imprimée : un id fictif collé serait une attribution silencieusement
    perdue."""
    try:
        donnees = _lire_json(atelier, IDENTITE_RELATIVE)
    except HorsRacine:
        raise RefusIdentite(_LIEN_HORS_RACINE) from None
    if donnees is None or not donnees.get("project_id"):
        raise RefusIdentite("aucune identité à publier (.agents/state/project.json "
                            f"absent ou corrompu) — {_RELANCER}")
    project_id = donnees["project_id"]
    if fmt in ("shell", "both"):
        sys.stdout.write(
            f"# agentkit — attribution canal B pour « {donnees.get('name') or project_id} »\n"
            "# Colle ce bloc dans l'environnement de l'hôte AVANT son lancement.\n"
            "# Per-clone et jamais tracké : le project_id est git-ignoré.\n"
            f"OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id={project_id}\n")
    if fmt == "both":
        sys.stdout.write("\n# — ou, pour Claude Code, dans .claude/settings.local.json :\n")
    if fmt in ("json", "both"):
        charge = {"env": env_otel(atelier, project_id)}
        sys.stdout.write(json.dumps(charge, indent=2, ensure_ascii=False) + "\n")
    return 0


def renommer(atelier: Workspace, nouveau: str) -> int:
    """Réécrit `name` SEUL (slug, id, created gelés). Un `project.json` lien
    hors racine est refusé, rien écrit (C4)."""
    nouveau = nouveau.strip()
    if not nouveau:
        raise RefusIdentite("le nouveau nom ne peut pas être vide (--rename)")
    try:
        donnees = reecrire_champ(atelier, "name", nouveau)
    except HorsRacine:
        raise RefusIdentite(_LIEN_HORS_RACINE) from None
    sys.stdout.write(f"project_init: name -> {donnees['name']} "
                     f"(slug inchangé: {donnees.get('slug')})\n")
    sys.stderr.write(_AVERTISSEMENT_RENOM)
    return 0


def _analyseur() -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(
        prog="project_init.py",
        description="Generate or update a project's immutable identity (.agents/state/project.json).",
    )
    analyseur.add_argument("--name",
                           help="Project name STORED in project.json:name at init "
                                "(else prompted interactively). NOT the displayed "
                                "name since T-00000582: the dashboard shows the repo "
                                "directory basename.")
    analyseur.add_argument("--rename",
                           help="Rewrite the STORED human name ONLY (slug/id/created "
                                "frozen). Does NOT change what the dashboard displays "
                                "since T-00000582 (that is the directory basename).")
    analyseur.add_argument(
        "--print-otel-env", dest="print_otel_env", action="store_true",
        help="Print the paste-ready OTEL_RESOURCE_ATTRIBUTES block carrying this "
             "project's real project_id (V1-c canal-B attribution). READ-ONLY.")
    analyseur.add_argument(
        "--ensure-stores", dest="ensure_stores", action="store_true",
        help="Provision the state stores an init provisions (today: the task "
             "board), WITHOUT touching the identity. Idempotent, never "
             "overwrites — the repair gesture for a project inited before this "
             "flag existed.")
    analyseur.add_argument(
        "--format", dest="otel_format", choices=("shell", "json", "both"), default="both",
        help="Form of the --print-otel-env output: 'shell' for direnv/profile, "
             "'json' for .claude/settings.local.json (pure, parsable), 'both' "
             "(default) for the shell block followed by the JSON one.")
    # Pierre tombale (T-00000734) : drapeau RETIRÉ par T-00000594, gardé caché
    # pour rendre la cause et le remède au lieu d'un « unrecognized arguments ».
    analyseur.add_argument("--stamp-kit-version", dest="stamp_kit_version",
                           nargs="?", const="", default=None, help=argparse.SUPPRESS)
    return analyseur


def _refus_pierre_tombale(atelier: Workspace) -> RefusIdentite:
    """Le refus du drapeau retiré, qui dit si `kit.lock` est là. Un lien hors
    racine est jugé AU BOUT (`_juge`), comme la base (`Path.is_file`, lien
    suivi) : le dire ABSENT serait un diagnostic faux (critic-opus, clôture).
    Une BOUCLE de liens est dite ABSENT, comme la base : sous 3.11/3.12,
    `Path.resolve` lève `RuntimeError` (témoin I21, bras `boucle`). Le `try`
    reste LOCAL à ces deux lignes : `CadrePathError` hérite de `RuntimeError`
    et ne doit être avalé nulle part ailleurs."""
    verrou = atelier.racine / _VERROU_RELATIF
    try:
        lecteur: Workspace = _juge(atelier, verrou)
        present = lecteur.exists(verrou) and not lecteur.est_repertoire(verrou)
    except RuntimeError:
        present = False  # boucle de liens, resolve 3.11/3.12 ; la base disait ABSENT
    etat = ("présent" if present
            else "ABSENT ici — arbre copié à la main ou antérieur à T-00000705")
    return RefusIdentite("--stamp-kit-version RETIRÉ (T-00000594) — la version du kit vit "
                         f"dans .agents/kit.lock (clé version_kit, {etat}) ; retire ce drapeau.")


def principal_project_init(argv: list[str] | None = None, *,
                           board: FournisseurBoard | None = None,
                           executeur: Executor | None = None) -> int:
    """L'entrée de `project_init.py` ; rend le code de sortie.

    La pierre tombale est lue par `parse_known_args` D'ABORD : un argument
    inconnu à côté du drapeau retiré ne cache pas la cause derrière l'erreur
    d'argparse, et elle précède toute branche qui écrit. Puis la préséance
    d'origine : `--print-otel-env` > `--rename` > `--ensure-stores` > init.
    Une erreur d'argparse reste son `SystemExit(2)`, comme avant."""
    analyseur = _analyseur()
    connus, _inconnus = analyseur.parse_known_args(argv)
    try:
        if connus.stamp_kit_version is not None:
            raise _refus_pierre_tombale(Workspace(resoudre_racine_projet()))
        args = analyseur.parse_args(argv)
        atelier: Workspace = Workspace(resoudre_racine_projet())
        if args.print_otel_env:
            return publier_otel(atelier, args.otel_format)
        if args.rename is not None:
            return renommer(atelier, args.rename)
        if args.ensure_stores:
            return provisionner_stores(atelier, board)
        return initialiser_identite(atelier, args.name, board=board, executeur=executeur)
    except RefusIdentite as refus:
        sys.stderr.write(f"project_init: {refus}\n")
        return 2
