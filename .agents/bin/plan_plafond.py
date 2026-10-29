#!/usr/bin/env python3
"""PLAFOND DU CRITIQUE DE PLAN — lecteur sans LLM (T-01M4V7QQ6FE40YC4CRGR830BJA, décision pilote S-01M4V7RGDPP6ZK64NQ0RMN7BEN).

Usage : `bash .agents/pyrun.sh .agents/bin/plan_plafond.py [--root R] [--task T [--lot K]]`

LIGNE 1, toujours : `PLAFOND=<N> SOURCE=<kit|decoupe|adoptant|adoptant-illisible>`
  * `.agents/IS_THE_KIT` présent (marqueur de PRÉSENCE, strippé à la synchro) → `8 kit`, quelle que soit la ligne ;
  * sinon UNE seule ligne `plafond-critique=N` dans `.agents/state/gates/PLAN_CHAIN_REQUIRED`, N lu par
    `[1-9][0-9]*` en entier → `N adoptant` ;
  * marqueur absent, ou présent sans la ligne → `2 adoptant` (un adoptant qui désarme la chaîne reste à 2) ;
  * ligne en double, valeur invalide, fichier illisible → `2 adoptant-illisible` + `AVERTISSEMENT` sur stderr.
  Une ligne de COMMENTAIRE (`#`) n'est jamais lue : l'en-tête de la graine cite `plafond-critique=N` en prose.
  Sans `--task`, cette ligne n'importe que la stdlib : un `plan_cible` cassé ne la fait jamais tomber.
  * PLAN PAR LOT (T-01M54GE4K9EZRRQFD9TAVNWYKM, décisions pilote S-01M56T2BMTYFRSMEVGSWGD53CG et
    S-01M583Y4ZG42VFAEVS7X2647VF) : dans le kit seul, une tâche DÉCOUPÉE lit `2 decoupe` pour CHAQUE plan — son
    maître et chacun de ses lots. Découpée : `--lot K` (par construction), ou un cycle qui porte un checkpoint
    `kind=plan` titré `lot <K> : Plan @ …` ou un verdict titré `lot <K> : plan-critic …` — ces deux titres, eux
    seuls (une note `kind=delta` « lot A : … » ne découpe rien). Détection en échec (SPECS illisible, `plan_cible`
    inimportable) : ligne 1 INCHANGÉE (`8 kit`), ligne 2 `ITERATION=? ALLOCATION=? ESCALADE=oui`, code 0. Chez
    l'adoptant, `--lot` garde son N et sa source.

LIGNE 2, avec `--task` : `ITERATION=<n> ALLOCATION=<a> ESCALADE=<oui|non>` — le CODE compte (L-00000403).
  * Cycle : les entrées SPECS de la tâche (toutes graphies de son id, `plan_cible.meme_tache`) après la DERNIÈRE
    décision `plafond critique : nouveau cycle`, sinon toutes (la création de la tâche n'a pas de trace SPECS).
  * n : verdicts du cycle dont le titre satisfait `plan_cible.PLAN_CRITIC_TITLE` (un titre suffixé n'est pas
    compté). Ceinture C1 : un verdict marqué `(iteration k/…)` compte par son k, les marqueurs DISTINCTS — une
    entrée doublée compte une fois ; un verdict sans marqueur compte pour lui-même.
  * a : N + décisions `prolongation plafond critique` du cycle, dédoublonnées par l'itération qu'elles ouvrent
    (une prolongation doublée n'accorde pas deux itérations : le sens sûr).
  * ESCALADE=oui : n ≥ a et le DERNIER verdict compté n'est ni GO, ni GO_AVEC_RESERVES, ni PASS, ni CONCERNS
    (`plan_cible.ELIGIBLE_STATUSES`) — un NO_GO, ou un titre dont le verdict ne se lit pas : le sens sûr.
  * C2 : SPECS illisible (`CibleError`) ou `plan_cible` inimportable → `ITERATION=? ALLOCATION=? ESCALADE=oui`
    + `AVERTISSEMENT` au pilote. Code de sortie 0 : un exécuteur sous `set -e` lit quand même les deux lignes.
  * Le compte est PAR PLAN. Avec `--lot K` (clé `LOT:` du plan maître, `[A-Z][A-Z0-9]{0,3}`) : n, a et ESCALADE
    ne lisent que les entrées titrées `lot K :` — verdicts `lot K : plan-critic …`, préfixe retiré avant
    `plan_cible.verdict_status`, prolongations `prolongation plafond critique lot K : itération n`. Sans `--lot`
    (le maître) : les entrées `lot … :` ne comptent pas, ni les prolongations `prolongation plafond critique lot …`
    (même malformées : une prolongation de lot n'accorde jamais une itération au maître, le sens sûr).

LIGNE 3, avec `--task` ET `--voie-courte` : `VOIE_COURTE=<oui|pilote|non> NO_GO=<k|?> FICHIERS=<w|?>` — la voie
courte R3 (décisions pilote S-01M4ZG7Q5FAHQFVKG10Y81ZYXH et S-01M51M3X9SFEZECT1QJ0XJ8GD6). Sans le flag, la sortie
reste celle des deux lignes, octet pour octet ; le flag sans `--task` est un usage invalide (rc 2).
  * k : verdicts plan-critic NO_GO du cycle POSTÉRIEURS à sa dernière approbation (verdict GO, GO_AVEC_RESERVES,
    PASS, CONCERNS, ou décision `plan approuvé` / `night-eligible: approved`), dédoublonnés comme n (un passage
    court COMPTE) : une tâche replanifiée sans `nouveau cycle` n'hérite pas des NO_GO d'un plan déjà approuvé.
  * w : chemins distincts des lignes `LOT:` + `INTÉGRATION:` (`plan_lots.lire`) du plan nommé par le `plan=` de la
    DERNIÈRE entrée du cycle qui en porte un (checkpoint `kind=plan` ou verdict plan-critic), à condition que le
    `sha256=` de cette entrée, si elle en porte, soit celui du fichier courant — sinon `?` + AVERTISSEMENT (une
    entrée sans `sha256=` n'est pas contrôlée). Un `plan=` refusé
    par `chemin_de_plan_sur` (absolu, scratchpad, hors racine, absent) → `?`, JAMAIS le repli board, remède sur
    stderr. Une ligne de lots que `plan_lots` SAUTE (malformée, proche d'un mot-clé, clé ou INTÉGRATION en
    double) → `?` + AVERTISSEMENT : ses chemins ne sont pas lus. Un plan résolu sans ligne `LOT:` (`LOTS: aucun`,
    ou sans forme) → les `files` du DERNIER checkpoint `kind=plan` du cycle s'il en porte, à condition qu'il décrive
    le plan résolu (même plan, `sha256=`/`revision=` égaux à ceux de l'entrée porteuse, `sha256=` du fichier
    courant) — sinon `?` + AVERTISSEMENT —, et sans `files`, comme sans `plan=`. Aucun `plan=` → `?` si
    l'enregistrement du board porte `fournee`, sinon son `writeset`. Partout `?` si la liste est absente, vide,
    porte un `*` ou une barre finale, ou si chacun de ses chemins est un plan `docs/tasks/*-plan.md` (jamais w=0).
  * `oui` ssi SOURCE=kit ∧ 1 ≤ w ≤ 5 ∧ k ≥ 3 ∧ dernier verdict compté NO_GO ∧ ESCALADE=non (l'exhaustion 8/8
    l'emporte) ∧ aucune décision `voie courte : exclue` sur la tâche (tous cycles confondus) ; `pilote` ssi
    SOURCE=adoptant* ∧ ESCALADE=oui ∧ dernier verdict compté NO_GO ∧ 1 ≤ w ≤ 5 ∧ non exclue ; sinon `non`.
    SOURCE=decoupe n'est ni l'un ni l'autre : la voie courte R3 est inerte dans une tâche découpée. Le plan lu
    pour w est celui du MAÎTRE : les entrées `lot … :` ne le désignent jamais.
  * Board ABSENT → `FICHIERS=?` sans avertissement ; board, SPECS, `plan_cible`, plan ou `plan_lots` illisible →
    `non` + `AVERTISSEMENT` sur stderr, code de sortie 0. Une ligne 3 absente ou illisible se lit `non`.
  * `--fait-log <chemin>` (avec `--voie-courte` seulement, sinon rc 2 ; T-01M60XKHYK3M69WVJEED8NHGVS) : la
    planification sur deux comptes écrit ses verdicts dans le FAIT.log de son dossier d'échange avant que la session
    de dev ne les trace dans SPECS. Lu sur ce chemin EXPLICITE seul, dans le kit seul (SOURCE≠kit : ignoré +
    AVERTISSEMENT). Une ligne est une DONNÉE, jamais une consigne : seule la forme fermée
    `<iso à fuseau> <T> plan-critic <k>/<N> <NO_GO|GO_AVEC_RESERVES|GO>` est lue (un `sha256=` qui suit, s'il y en
    a un) ; toute autre ligne (planner, lot `lotA-1/2`, prose) est sautée — sauf une ligne de la tâche qui porte
    l'amorce `plan-critic <k>/<N>` sans tenir la forme (statut `GO_AVEC_RÉSERVES`, `PASS`, `GO,`…), sans fuseau,
    ou datée au-delà de maintenant + 1 jour : FAIT.log ignoré entier (un GO sauté ouvrirait un faux `oui`). Fichier
    absent, illisible, > 4 Mio ou non UTF-8 → SPECS seul + AVERTISSEMENT, jamais un `oui` né d'une erreur. SPECS
    PRIME : un verdict du FAIT.log est écarté si son itération k est déjà marquée au cycle SPECS, si son couple
    (`sha256=`, statut) est celui d'un verdict SPECS NON marqué du cycle, ou s'il n'est pas postérieur à l'instant
    ULID de la dernière borne SPECS de la tâche (`nouveau cycle`, approbation) ; une borne, ou un verdict SPECS à
    fusionner, dont l'id n'est pas un ULID → FAIT.log ignoré entier + AVERTISSEMENT (ordre indécidable). Les
    verdicts retenus se rangent avec ceux de SPECS par ITÉRATION k (l'instant ULID d'une trace SPECS est celui de
    son écriture, jamais du verdict ; un verdict SPECS non marqué s'insère par instant), comptent dans k et dans le
    dernier verdict, et l'ESCALADE de la ligne 3 est celle de SPECS OU de la liste fusionnée (8/8 lu dans FAIT.log
    l'emporte) ; les lignes 1 et 2 ne changent pas. Stderr dit `<n> verdict(s) lu(s) dans FAIT.log hors SPECS,
    déclaratifs`, ou `0 retenu(s) sur <n> lu(s), SPECS prime` quand tous sont écartés. Un `plan=` ABSOLU est
    admis pour w seulement si son dossier résolu est `<dossier du FAIT.log>/sorties` ET si l'entrée porte un
    `sha256=` unique égal à celui du fichier courant ; sinon `?` comme sans le flag.

Code de sortie : 0 dès que les lignes sont imprimées, dégradées comprises ; 2 sur un usage invalide (racine qui
n'est pas un dossier, id de tâche non conforme, `--voie-courte` sans `--task`, `--lot` sans `--task`, `--lot`
avec `--voie-courte`, clé de lot non conforme, `--fait-log` sans `--voie-courte`) — rien sur stdout, et l'exécuteur lit alors 2 et l'escalade.
N'écrit rien, ne prend aucun verrou. `--root` par défaut : `CLAUDE_PROJECT_DIR`, sinon `.` — le store que
`specs.py add` écrit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KIT_MARKER = Path(".agents") / "IS_THE_KIT"
CHAIN_MARKER = Path(".agents") / "state" / "gates" / "PLAN_CHAIN_REQUIRED"
CLE = "plafond-critique"
PLAFOND_KIT = 8
PLAFOND_DEFAUT = 2

_LIGNE_VALIDE = re.compile(CLE + r"=([1-9][0-9]*)")
_NOUVEAU_CYCLE = re.compile(r"^\s*plafond\s+critique\s*:\s*nouveau\s+cycle\b", re.IGNORECASE)
_PROLONGATION = re.compile(r"^\s*prolongation\s+plafond\s+critique\b", re.IGNORECASE)
_MARQUEUR_ITERATION = re.compile(r"\(\s*it[eé]ration\s+([0-9]+)\s*(?:/\s*[0-9]+\s*)?\)", re.IGNORECASE)
_ITERATION_OUVERTE = re.compile(r"it[eé]ration\s+([0-9]+)", re.IGNORECASE)

# PLAN PAR LOT (T-01M54GE4K9EZRRQFD9TAVNWYKM, S-01M56T2BMTYFRSMEVGSWGD53CG, S-01M583Y4ZG42VFAEVS7X2647VF).
PLAFOND_DECOUPE = 2
SOURCE_DECOUPE = "decoupe"
# La clé `LOT:` de `plan_lots.CLE_RE`, RECOPIÉE : l'usage se valide avant tout import.
_CLE_LOT = re.compile(r"[A-Z][A-Z0-9]{0,3}")
# `lot <K> :` en tête de titre. Insensible à la casse : une graphie relâchée compte PLUS, jamais moins (sens sûr).
_PREFIXE_LOT = re.compile(r"^\s*lot\s+([A-Z][A-Z0-9]{0,3})\s*:\s*", re.IGNORECASE)
_PLAN_DE_LOT = re.compile(r"plan\s*@", re.IGNORECASE)  # `lot <K> : Plan @ <sha> - <objet>`, préfixe retiré
_PROLONGATION_DE_LOT = re.compile(r"^\s*prolongation\s+plafond\s+critique\s+lot\s+([A-Z][A-Z0-9]{0,3})\s*:",
                                  re.IGNORECASE)
# Toute prolongation qui nomme un lot, malformée comprise : elle n'accorde jamais une itération au maître.
_PROLONGATION_D_UN_LOT = re.compile(r"^\s*prolongation\s+plafond\s+critique\s+lot\b", re.IGNORECASE)

# LA VOIE COURTE R3 (S-01M4ZG7Q5FAHQFVKG10Y81ZYXH, S-01M51M3X9SFEZECT1QJ0XJ8GD6) — seuils et valeurs, lus par AST.
SEUIL_NO_GO = 3
SEUIL_FICHIERS = 5
VOIE_COURTE_VALEURS = ("oui", "pilote", "non")
_VOIE_COURTE_EXCLUE = re.compile(r"^\s*voie\s+courte\s*:\s*exclue\b", re.IGNORECASE)
_PLAN_SEUL = re.compile(r"docs/tasks/[^/]+-plan\.md", re.IGNORECASE)
_REVISION = re.compile(r"(?<![A-Za-z0-9_])revision=(\S+)")
REMEDE_PLAN = "écrire le plan sous docs/tasks/ puis relire"
# Les refus de `plan_lots.lire` qui SAUTENT une ligne (ses chemins ne sont pas lus) : un compte qui les ignore
# sous-compte en silence. Jamais tout `refus` : « NON JUGÉ » (sans racine ni prédicat) le remplit sur un plan sain.
_REFUS_QUI_SAUTENT = ("ligne malformée", "ligne proche d'un mot-clé", "clé `", "`INTÉGRATION:` écrite deux fois",
                      "`LOTS:` écrit deux fois")

# FAIT.log de la planification sur deux comptes (T-01M60XKHYK3M69WVJEED8NHGVS) : forme FERMÉE, une ligne est une
# DONNÉE. Une ligne de lot (`lotA-1/2`, `maitre-1/2`) ne porte pas `<k>/<N>` numérique : elle n'est jamais lue.
FAIT_LOG_MAX_OCTETS = 4 * 1024 * 1024
_LIGNE_FAIT = re.compile(r"(?P<iso>\S+) (?P<tache>T-[0-9A-Za-z]+) plan-critic (?P<k>[0-9]{1,4})/[0-9]{1,4} "
                         r"(?P<statut>NO_GO|GO_AVEC_RESERVES|GO)(?=\s|$)(?P<reste>.*)")
_SHA_FAIT = re.compile(r"(?<![A-Za-z0-9])sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])")
# L'AMORCE d'un verdict de boucle : une ligne de la tâche qui la porte mais que la forme fermée refuse (statut
# `GO_AVEC_RÉSERVES`, `PASS`, `GO,`…) ne se saute pas — sautée, un GO perdu ouvrirait un faux `oui`.
_AMORCE_FAIT = re.compile(r"\S+ (?P<tache>T-[0-9A-Za-z]+) plan-critic [0-9]{1,4}/[0-9]{1,4}\s")
# Au-delà de maintenant + 1 jour, un horodatage n'est pas un verdict passé : il resterait « postérieur » à
# toute borne future (advisory sécurité S-01M611VR0).
FAIT_LOG_AVANCE_MAX_MS = 24 * 3600 * 1000
# `tasks_graphe._ms_de_sid`, RECOPIÉ (ms entières des 10 premiers symboles Crockford d'un `S-<ULID>`).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SID_ULID = re.compile(r"S-([0-9A-HJKMNP-TV-Z]{26})")


@dataclass(frozen=True)
class Plafond:
    valeur: int
    source: str
    avertissement: str | None = None

    def ligne(self) -> str:
        return f"PLAFOND={self.valeur} SOURCE={self.source}"


@dataclass(frozen=True)
class Compte:
    iteration: int | None
    allocation: int | None
    escalade: bool
    avertissement: str | None = None

    def ligne(self) -> str:
        n = "?" if self.iteration is None else str(self.iteration)
        a = "?" if self.allocation is None else str(self.allocation)
        return f"ITERATION={n} ALLOCATION={a} ESCALADE={'oui' if self.escalade else 'non'}"


@dataclass(frozen=True)
class VoieCourte:
    valeur: str
    no_go: int | None
    fichiers: int | None
    avertissements: tuple[str, ...] = ()

    def ligne(self) -> str:
        k = "?" if self.no_go is None else str(self.no_go)
        w = "?" if self.fichiers is None else str(self.fichiers)
        return f"VOIE_COURTE={self.valeur} NO_GO={k} FICHIERS={w}"


def lire_plafond(root: str | Path) -> Plafond:
    """La ligne 1. Ne lève jamais : toute lecture ratée retombe sur 2, jamais sur « kit »."""
    racine = Path(root)
    if (racine / KIT_MARKER).exists():
        return Plafond(PLAFOND_KIT, "kit")
    marqueur = racine / CHAIN_MARKER
    try:
        texte = marqueur.read_text(encoding="utf-8-sig")  # un BOM de tête (éditeur Windows) n'est pas la clé
    except FileNotFoundError:
        return Plafond(PLAFOND_DEFAUT, "adoptant")
    except (OSError, UnicodeDecodeError) as exc:
        return Plafond(PLAFOND_DEFAUT, "adoptant-illisible",
                       f"{marqueur} illisible ({exc}) : plafond {PLAFOND_DEFAUT}.")
    lignes = [brut.strip() for brut in texte.splitlines()]
    candidates = [s for s in lignes if s.startswith(CLE)]
    if not candidates:
        return Plafond(PLAFOND_DEFAUT, "adoptant")
    if len(candidates) > 1:
        return Plafond(PLAFOND_DEFAUT, "adoptant-illisible",
                       f"{marqueur} porte {len(candidates)} lignes `{CLE}=` : plafond {PLAFOND_DEFAUT}. "
                       f"Remède : n'en garder qu'une, éditée à la main par le pilote du projet.")
    m = _LIGNE_VALIDE.fullmatch(candidates[0])
    valeur = None
    if m:
        try:
            valeur = int(m.group(1))
        except ValueError:  # plus de chiffres que `int` n'en convertit (sys.get_int_max_str_digits)
            valeur = None
    if valeur is None:
        return Plafond(PLAFOND_DEFAUT, "adoptant-illisible",
                       f"{marqueur} : ligne `{candidates[0][:80]}` illisible (attendu `{CLE}=N`, N entier ≥ 1) : "
                       f"plafond {PLAFOND_DEFAUT}.")
    return Plafond(valeur, "adoptant")


def _plan_cible() -> Any:
    """`plan_cible`, frère du dossier de CE fichier — importé à la DEMANDE : la ligne 1 n'en dépend jamais."""
    ici = str(Path(__file__).resolve().parent)
    if ici not in sys.path:
        sys.path.insert(0, ici)
    import plan_cible

    return plan_cible


def _titre(entree: dict[str, Any]) -> str:
    return unicodedata.normalize("NFC", str(entree.get("title") or ""))


def _lot_de(entree: dict[str, Any]) -> tuple[str | None, str]:
    """(clé du lot en majuscules, titre SANS le préfixe `lot <K> :`), ou (None, titre) pour une entrée du maître."""
    titre = _titre(entree)
    m = _PREFIXE_LOT.match(titre)
    return (m.group(1).upper(), titre[m.end():]) if m else (None, titre)


def _miennes_et_cycle(pc: Any, entrees: list[dict[str, Any]],
                      tache: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Les entrées de la tâche (toutes graphies), puis celles du cycle courant (après le dernier `nouveau cycle`)."""
    miennes = [e for e in entrees if isinstance(e, dict) and pc.meme_tache(e.get("task"), tache)]
    debut = 0
    for i, e in enumerate(miennes):
        if e.get("kind") == "decision" and _NOUVEAU_CYCLE.match(_titre(e)):
            debut = i + 1
    return miennes, miennes[debut:]


def _verdicts_du_cycle(pc: Any, cycle: list[dict[str, Any]], lot: str | None = None) -> list[dict[str, Any]]:
    """Les verdicts plan-critic du PLAN compté : le maître (`lot` None, titre nu), ou le lot `lot` (préfixe retiré)."""
    verdicts = []
    for e in cycle:
        cle, reste = _lot_de(e)
        if e.get("kind") == "verdict" and cle == lot and pc.PLAN_CRITIC_TITLE.match(reste):
            verdicts.append(e)
    return verdicts


def est_decoupee(pc: Any, cycle: list[dict[str, Any]]) -> bool:
    """Le cycle porte un checkpoint `kind=plan` `lot <K> : Plan @ …` ou un verdict `lot <K> : plan-critic …`."""
    for e in cycle:
        cle, reste = _lot_de(e)
        if cle is None:
            continue
        if e.get("kind") == "plan" and _PLAN_DE_LOT.match(reste):
            return True
        if e.get("kind") == "verdict" and pc.PLAN_CRITIC_TITLE.match(reste):
            return True
    return False


def plafond_de_tache(root: str | Path, tache: str, lot: str | None, plafond: Plafond) -> tuple[Plafond, str | None]:
    """La ligne 1 d'une tâche, et la cause d'une détection ratée (alors la ligne 1 est INCHANGÉE et la ligne 2 se
    lit `?`, ESCALADE=oui). Hors du kit, rien ne change : l'adoptant garde son N et sa source."""
    if plafond.source != "kit":
        return plafond, None
    if lot is not None:
        return Plafond(PLAFOND_DECOUPE, SOURCE_DECOUPE), None  # par construction : `--lot` nomme un plan de lot
    try:
        pc = _plan_cible()
        erreur_cible = pc.CibleError
    except (ImportError, AttributeError) as exc:
        return plafond, (f"`plan_cible` inutilisable ({exc}) : découpe indécidable, ligne 1 inchangée, compte "
                         f"impossible, ESCALADE=oui — le pilote tranche.")
    try:
        _miennes, cycle = _miennes_et_cycle(pc, pc.entrees_specs(root), tache)
        decoupee = est_decoupee(pc, cycle)
    except (erreur_cible, OSError, ValueError, TypeError, AttributeError) as exc:
        return plafond, (f"SPECS illisible ({type(exc).__name__}: {exc}) : découpe indécidable, ligne 1 inchangée, "
                         f"compte impossible, ESCALADE=oui — le pilote tranche.")
    return (Plafond(PLAFOND_DECOUPE, SOURCE_DECOUPE) if decoupee else plafond), None


def _cle_de_verdict(e: dict[str, Any], i: int) -> tuple[str, Any]:
    """Ceinture C1 : un verdict marqué compte par son k (une entrée doublée compte une fois), sinon pour lui-même."""
    m = _MARQUEUR_ITERATION.search(_titre(e))
    return ("k", int(m.group(1))) if m else ("id", e.get("id") or f"#{i}")


def _est_prolongation_de(titre: str, lot: str | None) -> bool:
    """Une prolongation du plan compté : `… lot K : itération n` pour le lot K ; pour le maître, toute prolongation
    qui ne nomme AUCUN lot (une prolongation de lot, même malformée, n'accorde rien au maître)."""
    if lot is None:
        return bool(_PROLONGATION.match(titre)) and not _PROLONGATION_D_UN_LOT.match(titre)
    m = _PROLONGATION_DE_LOT.match(titre)
    return bool(m) and m.group(1).upper() == lot


def compter(entrees: list[dict[str, Any]], tache: str, plafond: int, lot: str | None = None) -> Compte:
    """La ligne 2, calculée sur des entrées DÉJÀ lues, dans l'ordre chronologique de `entrees_specs` — pour le
    maître (`lot` None) ou pour le lot `lot` (clé en majuscules)."""
    pc = _plan_cible()

    _miennes, cycle = _miennes_et_cycle(pc, entrees, tache)

    verdicts = _verdicts_du_cycle(pc, cycle, lot)
    cles: set[tuple[str, Any]] = {_cle_de_verdict(e, i) for i, e in enumerate(verdicts)}
    n = len(cles)

    prolongations: set[tuple[str, Any]] = set()
    for i, e in enumerate(cycle):
        if e.get("kind") == "decision" and _est_prolongation_de(_titre(e), lot):
            m = _ITERATION_OUVERTE.search(_titre(e))
            prolongations.add(("k", int(m.group(1))) if m else ("id", e.get("id") or f"#{i}"))
    a = plafond + len(prolongations)

    escalade = False
    if verdicts and n >= a:
        # le préfixe `lot K :` retiré : `verdict_status` est ancré sur `plan-critic`, un GO de lot se lirait illisible
        escalade = pc.verdict_status(_lot_de(verdicts[-1])[1]) not in pc.ELIGIBLE_STATUSES
    return Compte(n, a, escalade)


def compte_de_tache(root: str | Path, tache: str, plafond: int, lot: str | None = None) -> Compte:
    """La ligne 2 lue sur le store. C2 : un store illisible ou un `plan_cible` cassé se lit ESCALADE=oui."""
    try:
        pc = _plan_cible()
        erreur_cible = pc.CibleError
    except (ImportError, AttributeError) as exc:
        return Compte(None, None, True,
                      f"`plan_cible` inutilisable ({exc}) : compte impossible, ESCALADE=oui — le pilote tranche.")
    try:
        return compter(pc.entrees_specs(root), tache, plafond, lot)
    except (erreur_cible, OSError, ValueError, TypeError, AttributeError) as exc:
        # `CibleError` (store absent de forme, corrompu, en deux formes) et toute lecture ratée : jamais un compte à 0
        return Compte(None, None, True,
                      f"SPECS illisible ({type(exc).__name__}: {exc}) : compte impossible, ESCALADE=oui — "
                      f"le pilote tranche.")


class _Illisible(Exception):
    """Une lecture ratée de la ligne 3 (board, plan, `plan_lots`) : `non` + AVERTISSEMENT, jamais un w calculé."""


def _plan_lots() -> Any:
    """`plan_lots`, frère du dossier — importé à la DEMANDE, seulement quand un `plan=` est résolu."""
    ici = str(Path(__file__).resolve().parent)
    if ici not in sys.path:
        sys.path.insert(0, ici)
    import plan_lots

    return plan_lots


def compte_de_chemins(chemins: Any) -> int | None:
    """w, ou `None` (`?`) : liste absente ou vide, un chemin qui n'est pas une chaîne, à `*` ou à barre finale, ou
    CHAQUE chemin un plan `docs/tasks/*-plan.md` (le parent d'une fournée ne déclare que son plan). Jamais 0."""
    if not isinstance(chemins, list):
        return None
    vus: set[str] = set()
    for brut in chemins:
        if not isinstance(brut, str):
            return None
        c = brut.strip().replace("\\", "/")
        while c.startswith("./"):
            c = c[2:]
        if not c:
            continue
        if "*" in c or c.endswith("/"):
            return None
        vus.add(c)
    if not vus or all(_PLAN_SEUL.fullmatch(c) for c in vus):
        return None
    return len(vus)


def _champs_de_revision(pc: Any, texte: str) -> tuple[set[str], set[str]]:
    """Les `sha256=` et `revision=` qu'une entrée cite — deux valeurs d'un même champ ne relient rien."""
    return {m.lower() for m in pc.SHA256_FIELD.findall(texte)}, set(_REVISION.findall(texte))


def _ecart_de_checkpoint(pc: Any, root: str | Path, chemin: Path, porteuse: dict[str, Any],
                         checkpoint: dict[str, Any]) -> str | None:
    """`None` si le checkpoint `kind=plan` décrit le plan RÉSOLU, sinon la cause : il nomme ce plan (ou est l'entrée
    porteuse), chaque champ `sha256=`/`revision=` porté des deux côtés y est égal et unique (au moins un, sauf s'il
    EST la porteuse), et son `sha256=`, s'il en porte un, est celui du fichier courant."""
    texte = str(checkpoint.get("text") or "")
    if checkpoint is not porteuse:
        m = pc.PLAN_FIELD.search(texte)
        if not m or pc.chemin_de_plan_sur(root, m.group(1)) != chemin:
            return "le dernier checkpoint `kind=plan` ne nomme pas le plan cité"
        relies = 0
        for a, b in zip(_champs_de_revision(pc, texte), _champs_de_revision(pc, str(porteuse.get("text") or ""))):
            if a and b:
                if a != b or len(a) != 1:
                    return "le dernier checkpoint `kind=plan` décrit une autre révision que l'entrée qui cite le plan"
                relies += 1
        if not relies:
            return ("aucun `sha256=` ni `revision=` ne relie le dernier checkpoint `kind=plan` à l'entrée qui cite "
                    "le plan")
    empreintes = _champs_de_revision(pc, texte)[0]
    if empreintes and empreintes != {hashlib.sha256(chemin.read_bytes()).hexdigest()}:
        return "le plan a changé depuis son dernier checkpoint `kind=plan` (sha256 différent)"
    return None


def _plan_des_sorties(pc: Any, brut: str, porteuse: dict[str, Any], sorties: Path) -> Path | None:
    """Le plan ABSOLU d'une entrée SPECS écrite depuis la planification sur deux comptes, ou `None` : admis
    seulement si son dossier résolu est `sorties` ET si l'entrée porte UN `sha256=`, celui du fichier courant."""
    candidat = Path(brut.rstrip(".,;:)»\"'"))
    if not candidat.is_absolute() or candidat.suffix.lower() != ".md":
        return None
    try:
        resolu = candidat.resolve(strict=True)
        if not resolu.is_file() or resolu.parent != sorties.resolve():
            return None
        empreintes = _champs_de_revision(pc, str(porteuse.get("text") or ""))[0]
        if len(empreintes) != 1 or empreintes != {hashlib.sha256(resolu.read_bytes()).hexdigest()}:
            return None
    except (OSError, ValueError):
        return None
    return resolu


def _fichiers(pc: Any, root: str | Path, tache: str, cycle: list[dict[str, Any]],
              sorties: Path | None = None) -> tuple[int | None, list[str]]:
    """w et ses avertissements. Lève `_Illisible` sur un plan, un `plan_lots` ou un board illisible, et sur une
    ligne de lots que `plan_lots` SAUTE (compte impossible). `sorties` (avec `--fait-log`) admet un `plan=` absolu
    de ce dossier (`_plan_des_sorties`)."""
    porteur: str | None = None
    porteuse: dict[str, Any] = {}
    # le plan du MAÎTRE : une entrée `lot <K> :` (checkpoint ou verdict d'un plan de lot) ne le désigne jamais
    cycle = [e for e in cycle if _lot_de(e)[0] is None]
    for e in cycle:
        if e.get("kind") == "plan" or (e.get("kind") == "verdict" and pc.PLAN_CRITIC_TITLE.match(_titre(e))):
            m = pc.PLAN_FIELD.search(str(e.get("text") or ""))
            if m:
                porteur, porteuse = m.group(1), e
    if porteur is not None:
        chemin = pc.chemin_de_plan_sur(root, porteur)
        if chemin is None and sorties is not None:
            chemin = _plan_des_sorties(pc, porteur, porteuse, sorties)
        if chemin is None:
            # C2 : jamais le repli board — un writeset périmé lirait petit un plan qui ne l'est pas
            return None, [f"`plan={porteur}` refusé (absolu, scratchpad, hors racine ou absent) : FICHIERS=?, "
                          f"jamais le write-set du board. Remède : {REMEDE_PLAN}."]
        try:
            texte = chemin.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _Illisible(f"plan {chemin} illisible ({exc})") from exc
        try:
            decoupe = _plan_lots().lire(texte)
        except (ImportError, AttributeError, ValueError, TypeError) as exc:
            raise _Illisible(f"`plan_lots` inutilisable ({type(exc).__name__}: {exc})") from exc
        sautees = [r for r in decoupe.refus if isinstance(r, str) and r.startswith(_REFUS_QUI_SAUTENT)]
        if sautees:
            raise _Illisible(f"plan {porteur} : {len(sautees)} ligne(s) de lots SAUTÉE(S) par `plan_lots` — "
                             f"{sautees[0][:200]} — compte impossible. Remède : `python .agents/bin/plan_lots.py "
                             f"check --plan {porteur}`, corriger la ligne, puis relire")
        if decoupe.lots:
            # le plan JUGÉ, pas un fichier réécrit depuis : le `sha256=` que porte l'entrée qui cite le plan (s'il en
            # porte) est celui du fichier courant, sinon `?` — même règle que le repli checkpoint
            empreintes = _champs_de_revision(pc, str(porteuse.get("text") or ""))[0]
            try:
                courante = hashlib.sha256(chemin.read_bytes()).hexdigest() if empreintes else None
            except OSError as exc:
                raise _Illisible(f"plan {chemin} illisible ({exc})") from exc
            if empreintes and empreintes != {courante}:
                return None, [f"le plan {porteur} a changé depuis l'entrée qui le cite (sha256 différent) : "
                              f"FICHIERS=?, jamais les lots d'une révision non jugée. Remède : journaliser la "
                              f"révision courante en checkpoint `kind=plan` avec `plan=`, `revision=`/`sha256=` et "
                              f"`--files`, puis relire."]
            chemins = [c for lot in decoupe.lots for c in lot.chemins] + list(decoupe.integration)
            return compte_de_chemins(chemins), []
        plans = [e for e in cycle if e.get("kind") == "plan"]
        if plans and plans[-1].get("files"):
            try:
                ecart = _ecart_de_checkpoint(pc, root, chemin, porteuse, plans[-1])
            except OSError as exc:
                raise _Illisible(f"plan {chemin} illisible ({exc})") from exc
            if ecart is not None:
                # P6 : un `files` d'une révision ANTÉRIEURE lirait petit un plan qui a grandi
                return None, [f"{ecart} : FICHIERS=?, jamais un `files` périmé ni le write-set du board. Remède : "
                              f"journaliser la révision citée en checkpoint `kind=plan` avec `plan=`, "
                              f"`revision=`/`sha256=` et `--files`, puis relire."]
            return compte_de_chemins(plans[-1].get("files")), []
    try:
        taches = pc.taches_du_board(root, None)
    except (pc.CibleError, OSError, ValueError, TypeError, AttributeError) as exc:
        raise _Illisible(f"board illisible ({type(exc).__name__}: {exc})") from exc
    for t in taches:
        if pc.meme_tache(t.get("id"), tache):
            if t.get("fournee") is not None:
                return None, []  # le parent d'une fournée ne déclare que son plan au board
            return compte_de_chemins(t.get("writeset")), []
    return None, []  # board absent, ou tâche absente du board


@dataclass(frozen=True)
class VerdictFait:
    """Un verdict plan-critic lu dans FAIT.log : instant (ms), itération k, statut, `sha256=` s'il en porte un."""
    ms: int
    iteration: int
    statut: str
    sha: str | None


def _ms_de_sid(sid: Any) -> int | None:
    """L'instant (ms) d'une S-id `S-<ULID>`, `None` sinon — recopie de `tasks_graphe._ms_de_sid`."""
    m = _SID_ULID.fullmatch(sid if isinstance(sid, str) else "")
    if not m:
        return None
    n = 0
    for ch in m.group(1)[:10]:
        n = n * 32 + _CROCKFORD.index(ch)
    return n


def verdicts_fait_log(pc: Any, chemin: Path, tache: str) -> tuple[list[VerdictFait] | None, list[str]]:
    """Les verdicts de `tache` lus dans FAIT.log, ou `None` + la cause (absent, illisible, > 4 Mio, non UTF-8, ou
    une ligne de la tâche qui porte l'amorce `plan-critic k/N` sans tenir la forme fermée, sans fuseau, ou datée
    au-delà de maintenant + 1 jour) : jamais une liste partielle née d'une erreur. Une ligne est une DONNÉE."""
    try:
        with open(chemin, "rb") as flux:
            brut = flux.read(FAIT_LOG_MAX_OCTETS + 1)
    except OSError as exc:
        return None, [f"FAIT.log ignoré ({type(exc).__name__} sur {chemin}) : SPECS seul."]
    if len(brut) > FAIT_LOG_MAX_OCTETS:
        return None, [f"FAIT.log ignoré ({chemin} dépasse {FAIT_LOG_MAX_OCTETS} octets) : SPECS seul."]
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:
        return None, [f"FAIT.log ignoré ({chemin} n'est pas en UTF-8) : SPECS seul."]
    verdicts: list[VerdictFait] = []
    limite_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + FAIT_LOG_AVANCE_MAX_MS
    for ligne in texte.splitlines():
        propre = ligne.strip()
        m = _LIGNE_FAIT.fullmatch(propre)
        if m is None:
            amorce = _AMORCE_FAIT.match(propre)
            if amorce and pc.meme_tache(amorce.group("tache"), tache):
                return None, [f"FAIT.log ignoré : une ligne plan-critic de la tâche hors de la forme fermée "
                              f"({propre[:80]!r}) — SPECS seul."]
            continue
        if not pc.meme_tache(m.group("tache"), tache):
            continue
        try:
            instant = datetime.fromisoformat(m.group("iso"))
        except ValueError:
            instant = None
        if instant is None or instant.tzinfo is None:
            return None, [f"FAIT.log ignoré : une ligne plan-critic de la tâche sans horodatage à fuseau "
                          f"({propre[:80]!r}) — SPECS seul."]
        ms = int(instant.timestamp() * 1000)
        if ms > limite_ms:
            return None, [f"FAIT.log ignoré : une ligne plan-critic de la tâche datée au-delà de maintenant + 1 jour "
                          f"({propre[:80]!r}) — SPECS seul."]
        sha = _SHA_FAIT.search(m.group("reste"))
        verdicts.append(VerdictFait(ms, int(m.group("k")), m.group("statut"), sha.group(1).lower() if sha else None))
    return verdicts, []


def _est_borne(pc: Any, e: dict[str, Any]) -> bool:
    """Une borne SPECS : décision `nouveau cycle`, verdict plan-critic d'approbation, décision d'approbation."""
    titre = _titre(e)
    if e.get("kind") == "decision":
        return bool(_NOUVEAU_CYCLE.match(titre)) or pc.normalise_titre(titre) in pc.TITRES_APPROBATION
    return (e.get("kind") == "verdict" and bool(pc.PLAN_CRITIC_TITLE.match(titre))
            and pc.verdict_status(titre) in pc.ELIGIBLE_STATUSES)


def fusion_fait_log(pc: Any, miennes: list[dict[str, Any]], verdicts: list[dict[str, Any]],
                    fait: list[VerdictFait]) -> tuple[list[VerdictFait], list[str]]:
    """Les verdicts du FAIT.log RETENUS à côté de SPECS, qui PRIME : écarté si son k est déjà marqué au cycle, si
    son couple (`sha256=`, statut) est celui d'un verdict SPECS non marqué du cycle (un même plan rejugé GO après
    un NO_GO n'est pas un doublon), ou s'il n'est pas postérieur à la dernière borne SPECS de la tâche. Borne à id
    non ULID : FAIT.log ignoré entier (coupure indécidable)."""
    borne_ms: int | None = None
    bornes = [e for e in miennes if _est_borne(pc, e)]
    if bornes:
        borne_ms = _ms_de_sid(bornes[-1].get("id"))
        if borne_ms is None:
            return [], [f"FAIT.log ignoré : la dernière borne SPECS de la tâche ({str(bornes[-1].get('id'))[:40]}) "
                        f"n'a pas d'id ULID, coupure indécidable — SPECS seul."]
    deja_k: set[int] = set()
    deja_sha: set[tuple[str, str | None]] = set()
    for e in verdicts:
        m = _MARQUEUR_ITERATION.search(_titre(e))
        if m:
            deja_k.add(int(m.group(1)))
        else:
            statut = pc.verdict_status(_titre(e))
            deja_sha |= {(s.lower(), statut) for s in pc.SHA256_FIELD.findall(str(e.get("text") or ""))}
    retenus = [v for v in fait
               if v.iteration not in deja_k
               and (v.sha is None or (v.sha, v.statut) not in deja_sha)
               and (borne_ms is None or v.ms > borne_ms)]
    return retenus, []


def _ordre_fusionne(pc: Any, suivants: list[dict[str, Any]], debut: int,
                    retenus: list[VerdictFait]) -> list[tuple[tuple[str, Any], str | None]]:
    """(clé, statut) des verdicts SPECS `suivants` et des verdicts RETENUS du FAIT.log, dans l'ordre des VERDICTS :
    par itération k pour tout verdict qui la porte (une ligne FAIT.log toujours, un verdict SPECS marqué
    `(iteration k/…)`) — l'instant d'une trace SPECS est celui de son ÉCRITURE, tardive sous deux comptes, jamais
    celui du verdict. Un verdict SPECS non marqué s'insère par instant (seule mesure qu'il porte)."""
    avec_k: list[tuple[int, int, tuple[str, Any], str | None]] = []
    sans_k: list[tuple[int, tuple[str, Any], str | None]] = []
    for j, e in enumerate(suivants):
        ms = _ms_de_sid(e.get("id")) or 0
        cle, statut = _cle_de_verdict(e, debut + j), pc.verdict_status(_titre(e))
        if cle[0] == "k":
            avec_k.append((cle[1], ms, cle, statut))
        else:
            sans_k.append((ms, cle, statut))
    avec_k += [(v.iteration, v.ms, ("k", v.iteration), v.statut) for v in retenus]
    avec_k.sort(key=lambda t: (t[0], t[1]))
    sans_k.sort(key=lambda t: t[0])
    suite: list[tuple[tuple[str, Any], str | None]] = []
    i = j = 0
    while i < len(avec_k) or j < len(sans_k):
        if j < len(sans_k) and (i >= len(avec_k) or sans_k[j][0] < avec_k[i][1]):
            suite.append(sans_k[j][1:])
            j += 1
        else:
            suite.append(avec_k[i][2:])
            i += 1
    return suite


def voie_courte(entrees: list[dict[str, Any]], root: str | Path, tache: str, plafond: Plafond,
                compte: Compte, fait: list[VerdictFait] | None = None,
                sorties: Path | None = None) -> VoieCourte:
    """La ligne 3, sur des entrées DÉJÀ lues et le compte de la ligne 2 — ESCALADE de la ligne 2, relevée par le
    FAIT.log. `fait` : les verdicts lus dans FAIT.log (`--fait-log`), fusionnés sans jamais primer sur SPECS et
    rangés par itération (`_ordre_fusionne`) ; `sorties` : leur dossier de plans."""
    pc = _plan_cible()
    miennes, cycle = _miennes_et_cycle(pc, entrees, tache)
    verdicts = _verdicts_du_cycle(pc, cycle)
    # k ne compte que les NO_GO POSTÉRIEURS à la dernière approbation du cycle : une tâche replanifiée sans
    # `nouveau cycle` (aucun verbe ne l'écrit) n'hérite jamais des NO_GO d'un plan déjà approuvé
    # (approbation : verdict plan-critic GO / GO_AVEC_RESERVES / PASS / CONCERNS, ou décision `plan approuvé` /
    # `night-eligible: approved`) ; `debut` est l'indice, dans `verdicts`, du premier verdict qui la suit
    debut = vus = 0
    for e in cycle:
        titre = _titre(e)
        est_verdict = e.get("kind") == "verdict" and bool(pc.PLAN_CRITIC_TITLE.match(titre))
        vus += est_verdict  # même prédicat que `_verdicts_du_cycle` : `vus` suit les indices de `verdicts`
        if ((est_verdict and pc.verdict_status(titre) in pc.ELIGIBLE_STATUSES)
                or (e.get("kind") == "decision" and pc.normalise_titre(titre) in pc.TITRES_APPROBATION)):
            debut = vus
    k = len({_cle_de_verdict(e, i) for i, e in enumerate(verdicts)
             if i >= debut and pc.verdict_status(_titre(e)) == "NO_GO"})
    # « dernier verdict compté NO_GO » : plus strict que l'escalade (un titre illisible n'ouvre jamais la voie)
    dernier_no_go = bool(verdicts) and pc.verdict_status(_titre(verdicts[-1])) == "NO_GO"
    escalade = compte.escalade
    notes: list[str] = []
    if fait:
        retenus, notes = fusion_fait_log(pc, miennes, verdicts, fait)
        suivants = verdicts[debut:]
        if retenus and any(_ms_de_sid(e.get("id")) is None for e in suivants):
            retenus = []
            notes = ["FAIT.log ignoré : un verdict SPECS du cycle n'a pas d'id ULID, ordre indécidable — SPECS seul."]
        if retenus:
            # les verdicts postérieurs à la dernière approbation SPECS et ceux du FAIT.log, dans l'ordre des verdicts
            suite = _ordre_fusionne(pc, suivants, debut, retenus)
            approbation = max((i for i, t in enumerate(suite) if t[1] in pc.ELIGIBLE_STATUSES), default=-1)
            k = len({t[0] for i, t in enumerate(suite) if i > approbation and t[1] == "NO_GO"})
            dernier_no_go = suite[-1][1] == "NO_GO"
            cles = {_cle_de_verdict(e, i) for i, e in enumerate(verdicts)} | {("k", v.iteration) for v in retenus}
            # l'exhaustion lue dans la liste fusionnée l'emporte : jamais `oui` à 8/8 parce que SPECS en est à 5
            escalade = escalade or (compte.allocation is not None and len(cles) >= compte.allocation
                                    and suite[-1][1] not in pc.ELIGIBLE_STATUSES)
            notes = [f"{len(retenus)} verdict(s) lu(s) dans FAIT.log hors SPECS, déclaratifs"]
        elif not notes:
            notes = [f"FAIT.log : 0 retenu(s) sur {len(fait)} lu(s), SPECS prime."]
    exclue = any(e.get("kind") == "decision" and _VOIE_COURTE_EXCLUE.match(_titre(e)) for e in miennes)
    try:
        w, avertissements = _fichiers(pc, root, tache, cycle, sorties)
    except _Illisible as exc:
        return VoieCourte("non", k, None, (*notes, f"{exc} : FICHIERS=?, VOIE_COURTE=non."))
    petit = w is not None and 1 <= w <= SEUIL_FICHIERS
    valeur = "non"
    if petit and dernier_no_go and not exclue:
        if plafond.source == "kit" and k >= SEUIL_NO_GO and not escalade:
            valeur = "oui"
        elif plafond.source.startswith("adoptant") and escalade:
            valeur = "pilote"
    return VoieCourte(valeur, k, w, (*notes, *avertissements))


def voie_courte_de_tache(root: str | Path, tache: str, plafond: Plafond, compte: Compte,
                         fait_log: Path | None = None) -> VoieCourte:
    """La ligne 3 lue sur le store (et sur FAIT.log avec `fait_log`, kit seul). Toute lecture ratée se lit `non`
    + AVERTISSEMENT, jamais `oui` ; un FAIT.log illisible retombe sur SPECS seul."""
    if compte.iteration is None:
        return VoieCourte("non", None, None, ("compte de la ligne 2 impossible : NO_GO=?, FICHIERS=?, "
                                              "VOIE_COURTE=non.",))
    try:
        pc = _plan_cible()
        erreur_cible = pc.CibleError
    except (ImportError, AttributeError) as exc:
        return VoieCourte("non", None, None, (f"`plan_cible` inutilisable ({exc}) : VOIE_COURTE=non.",))
    try:
        entrees = pc.entrees_specs(root)
        if fait_log is None or plafond.source != "kit":
            return voie_courte(entrees, root, tache, plafond, compte)
        fait, notes = verdicts_fait_log(pc, fait_log, tache)
        voie = voie_courte(entrees, root, tache, plafond, compte, fait,
                           None if fait is None else fait_log.parent / "sorties")
        return VoieCourte(voie.valeur, voie.no_go, voie.fichiers, (*notes, *voie.avertissements))
    except (erreur_cible, OSError, ValueError, TypeError, AttributeError) as exc:
        return VoieCourte("non", None, None, (f"SPECS illisible ou voie courte incalculable "
                                              f"({type(exc).__name__}: {exc}) : VOIE_COURTE=non.",))


# La graphie que `plan_cible.cle_de_tache` reconnaît, RECOPIÉE pour valider AVANT tout import : ULID en MAJUSCULES
# seul, legacy `T-`/`t-` + chiffres ASCII. Un id que `meme_tache` ne relierait à rien donnerait n=0, ESCALADE=non.
_ID_TACHE = re.compile(r"T-[0-9A-HJKMNP-TV-Z]{26}|[Tt]-0*[0-9]{1,15}")


def _id_conforme(tache: str) -> bool:
    return _ID_TACHE.fullmatch(tache.strip()) is not None


def main(argv: list[str] | None = None) -> int:
    # T-01M5QC86XN, lot P : `--short-path` en tete, `--voie-courte` garde en alias, `dest` ancien explicite.
    ap = argparse.ArgumentParser(prog="plan_plafond.py",
                                 description="Plan-critic cap: LLM-free reader of the cap, iteration and escalation.")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."), help="project root")
    ap.add_argument("--task", default=None, help="task id: adds the ITERATION / ALLOCATION / ESCALADE line")
    ap.add_argument("--short-path", "--voie-courte", dest="voie_courte", action="store_true",
                    help="with --task: adds the VOIE_COURTE / NO_GO / FICHIERS line (short path R3)")
    ap.add_argument("--lot", default=None,
                    help="with --task: counts the plan of lot K (key of its `LOT:` line); without, the master")
    ap.add_argument("--fait-log", default=None,
                    help="with --voie-courte, kit only: also reads the plan-critic verdicts of this FAIT.log "
                         "(two-account planning), never above SPECS")
    args = ap.parse_args(argv)
    if args.voie_courte and args.task is None:
        print("plan_plafond.py : --voie-courte exige --task (la voie courte se lit par tâche).", file=sys.stderr)
        return 2
    if args.fait_log is not None and not args.voie_courte:
        print("plan_plafond.py : --fait-log exige --voie-courte (FAIT.log ne sert que la ligne 3).", file=sys.stderr)
        return 2
    lot = None if args.lot is None else args.lot.strip()
    if lot is not None and args.task is None:
        print("plan_plafond.py : --lot exige --task (un plan de lot se compte dans sa tâche).", file=sys.stderr)
        return 2
    if lot is not None and args.voie_courte:
        print("plan_plafond.py : --lot et --voie-courte s'excluent (la voie courte R3 est inerte dans une tâche "
              "découpée).", file=sys.stderr)
        return 2
    if lot is not None and not _CLE_LOT.fullmatch(lot):
        print(f"plan_plafond.py : --lot {args.lot!r} n'est pas une clé de lot (`[A-Z][A-Z0-9]{{0,3}}`, celle de "
              f"la ligne `LOT:`).", file=sys.stderr)
        return 2
    if not Path(args.root).is_dir():
        print(f"plan_plafond.py : --root {args.root!r} n'est pas un dossier.", file=sys.stderr)
        return 2
    if args.task is not None and not _id_conforme(args.task):
        print(f"plan_plafond.py : --task {args.task!r} n'est pas un id de tâche (T-<ULID> ou T-<nombre>).",
              file=sys.stderr)
        return 2

    plafond = lire_plafond(args.root)
    echec_decoupe: str | None = None
    if args.task is not None:
        plafond, echec_decoupe = plafond_de_tache(args.root, args.task.strip(), lot, plafond)
    print(plafond.ligne())
    if plafond.avertissement:
        print(f"AVERTISSEMENT : {plafond.avertissement}", file=sys.stderr)
    if args.task is not None:
        if echec_decoupe is not None:
            # une découpe indécidable ne se compte jamais sous le plafond du kit : le pilote tranche
            compte = Compte(None, None, True, echec_decoupe)
        else:
            compte = compte_de_tache(args.root, args.task.strip(), plafond.valeur, lot)
        print(compte.ligne())
        if compte.avertissement:
            print(f"AVERTISSEMENT : {compte.avertissement}", file=sys.stderr)
        if args.voie_courte:
            fait_log = None if args.fait_log is None else Path(args.fait_log)
            if fait_log is not None and plafond.source != "kit":
                print(f"AVERTISSEMENT : --fait-log ignoré hors du kit (SOURCE={plafond.source}) : FAIT.log n'est "
                      f"jamais lu chez un adoptant ni dans une tâche découpée.", file=sys.stderr)
                fait_log = None
            voie = voie_courte_de_tache(args.root, args.task.strip(), plafond, compte, fait_log)
            print(voie.ligne())
            for avertissement in voie.avertissements:
                print(f"AVERTISSEMENT : {avertissement}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
