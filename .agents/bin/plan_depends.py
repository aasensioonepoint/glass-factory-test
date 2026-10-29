#!/usr/bin/env python3
"""DÉPENDANCES MÉCANIQUES — T-00000765 (STDLIB SEULE + `plan_cible`, module frère).

Décide si les dépendances qu'un plan APPROUVÉ déclare sont INSCRITES au board, et porte
TOUTE la logique neuve du verbe `tasks.py depends` (`--add`, `--retirer`,
`--retirer-ordre-pilote`, protection des motifs `ORDRE PILOTE`, remèdes qui ne détruisent
rien). N'écrit JAMAIS, ne prend JAMAIS de verrou : `tasks.py`/`specs.py` le chargent
PARESSEUSEMENT (modèle de `plan_cible_module`) et gardent des sites minces ; ce module-ci reste soumis à la
règle de taille des `.py` (S-00002684 : 800 lignes, relevée à 1600 par S-00004034).

*** ISOLATION (M13). *** Stdlib et `plan_cible` seulement ; JAMAIS `tasks`, `specs` ni
`night_approve` (sous `python3 tasks.py`, un import de `tasks` créerait un SECOND module
dont le compteur de verrou ignore le verrou tenu). `find`/`dependency_cycle` arrivent PAR
ARGUMENT dans `appliquer_verbe`. Témoin W16, en sous-processus.

GRAMMAIRE FERMÉE (plan T-00000765 § Grammaire). Une ligne par arête, HORS bloc de code,
en tête de ligne (puce `- ` tolérée) :

    ARÊTE: <aval> <- <amont> | <motif>        (`ARETE` accepté ; ids T-\\d{1,12})
    ARÊTES: aucune                            (le plan déclare n'avoir aucune arête)

Motif sur UNE ligne, 1 à 500 caractères, ouvert ni par un espace ni par `/`. MAJUSCULES
seulement sur le mot-clé. REFUSÉES en nommant la ligne : mot-clé sans parse complet, ligne
PROCHE du mot-clé (`ARÊTE :`, autre puce, gras, NFD — fable F5), `ARÊTES: aucune` à côté
d'une `ARÊTE:`, aval non ENRÔLÉ, auto-arête, et À LA TRACE SEULE un id inconnu du board —
à `start`/`done` un amont absent est une tâche PURGÉE depuis, DITE sur stderr (`non
contrôlée — <amont> absent du board (purgé ?)`, fable F2), jamais un refus perpétuel.
Regex ANCRÉES et BORNÉES, balayage linéaire (précédent ReDoS de T-00000654).

LA GARDE COMPARE L'AMONT À `depends_on` DE L'AVAL, JAMAIS LE MOTIF, et elle est
ASYMÉTRIQUE : une arête du board absente du plan n'est jamais un refus. Elle contrôle
l'INSCRIPTION ; la SATISFACTION est tenue par la jambe d'amont de `set_state`
(`tasks_graphe.releve_amont`, verbe `deps-ready`, S-01M4Z5VMP5E9YN8T6EMDTBAF0T), qui pose
aussi la marque d'un `start --sans-dependances` — `jambe_start` n'en pose plus.

TROIS JAMBES, UN SEUL RÉGIME (`plan_cible._arme_pour_tache`, l'UNIQUE lecteur — W8c) :
`PLAN_CIBLE_REQUIRED` armé ET tâche du chantier nommé. `start` (R1) et `done` (R1 puis
R2) refusent une `ARÊTE:` dont l'amont manque ; un plan sans AUCUNE des deux formes y
reste INERTE. À la trace `plan approuvé` — JAMAIS `night-eligible: approved` (asymétrie
ASSUMÉE, M10/A-C3) — `specs.py` refuse la même arête pour TOUT aval enrôlé, et EN PLUS
l'absence des deux formes. Un ORDRE PILOTE manquant n'est JAMAIS prescrit en `--add`
exécutable (fable F1 : levé, le réinscrire annulerait la décision sans trace) — ligne `#`
qui nomme les deux cas ; commandes dédoublonnées par arête (F7).

MODE DIRE au `done` sous `--sans-cible` (pont V3, tableau de bord, humain) : `jambe_done`
ne lève JAMAIS ; une ligne `TASKS: <tid> close SANS contrôle des dépendances du plan …` et
une marque `[SANS DÉPENDANCES : …]` DANS CHAQUE CAS où le contrôle n'a pas eu lieu en
entier — manquante, fautive, lecture impossible (opus T3). Plan non UTF-8 ⇒ `CibleError`
NOMMÉE (`_lire_plan`), et les sites captent aussi `ValueError` (opus T2).

ORDRE PILOTE. Motif canonique `ORDRE PILOTE S-<ULID ou 8 chiffres>` (`ORDRE_PILOTE_CANONIQUE`,
RECOPIÉE dans `core-scripts/plan_waves.py` — parité W14, deux copies et pas trois). Un
motif NEUF ouvrant par `ordre pilote` (casse ignorée) est canonique ET cite une
`kind=decision` existante qui n'est pas une trace d'approbation (M3, fable F4) ; `ordre…`
non canonique : AVERTISSEMENT stderr seul. Réécriture totale ou `--clear` qui PERDRAIT ou
RE-MOTIVERAIT un `ORDRE PILOTE` : REFUSÉE sans rien écrire (M1). `--retirer` le refuse et
renvoie vers `--retirer-ordre-pilote <amont> S-<id>`, S-id DISTINCTE de TOUTES celles du motif.
Ces contrôles du VERBE valent QUEL QUE SOIT le marqueur (opus T1, borne écrite). AVEU :
aucun test de PERTINENCE, trace et décision auto-déclaratives — ça empêche d'OUBLIER une
arête, pas d'en inscrire une fausse.

SUGGESTION : `kind=delta`, titre fermé `SUGGESTION: ajouter|retirer T-<aval> <- T-<amont>`,
`--text` non vide ; aucun `kind` neuf (M8). Le pilote tranche par une `kind=decision`.

MODULE ABSENT (lui, ou son import `plan_cible.py` — opus T4). Un verbe NEUF n'a aucun
comportement d'avant sur lequel retomber, et un marqueur ARMÉ sans module ne rend jamais
la garde MUETTE (T-00000654 C3/T6) : refus décidés DANS `tasks.py`/`specs.py`, au site
d'appel, par un test de SYSTÈME DE FICHIERS. Remède : `REMEDE_MODULE`.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_BIN = str(Path(__file__).resolve().parent)
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)
import plan_cible  # noqa: E402 — frère stdlib ; JAMAIS `tasks`/`specs` (M13)

CibleError = plan_cible.CibleError

# ---------------------------------------------------------------------------
# CONSTANTES. `ORDRE_PILOTE_CANONIQUE` est recopiée VERBATIM dans plan_waves.py.
# ---------------------------------------------------------------------------
# T-00001040 : la S-id d'un ordre pilote est un `S-<ULID>` (EN PREMIER) ou l'ancien
# `S-<8 chiffres>` ; témoins : `GrammaireUlidTests` et W14 de test_depends_add.py.
ORDRE_PILOTE_CANONIQUE = re.compile(r"^ORDRE PILOTE S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\b")
_SID_DU_MOTIF = re.compile(r"^ORDRE PILOTE (S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8}))\b")
_ORDRE_PREFIXE = re.compile(r"^ordre\b", re.IGNORECASE)
_ORDRE_PILOTE_PREFIXE = re.compile(r"^ordre\s+pilote\b", re.IGNORECASE)
# T-00001085 : jugé par `fullmatch`, ASCII seul (`[0-9]`, jamais `\d`) ; témoin
# test_plan_depends_sid. T-00001040 (E24) : `S-<ULID>` en premier, même jugement.
_SID = re.compile(r"S-(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9]{1,12})")
# T-00001062 : TOUTE citation `S-<alnum>` du motif, bornée à gauche ; bornes : W27.
_SIDS_CITES = re.compile(r"(?<![0-9A-Za-z])S-([0-9A-Za-z]+)")

MOTIF_MAX = 500
_MOT_CLE = re.compile(r"^(?:- )?AR[EÊ]TES?:")
# Corps capturé GLOUTON (`(.*)$`, linéaire), contrôlé ensuite en Python. Un id :
# `T-<ULID>` EN PREMIER, borné à droite, puis l'ancien `T-<chiffres>` (T-00001040).
_ARETE = re.compile(
    r"^(?:- )?AR[EÊ]TE:[ \t]*(T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d{1,12}))[ \t]*<-"
    r"[ \t]*(T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d{1,12}))[ \t]*\|(.*)$")
_AUCUNE = re.compile(r"^(?:- )?AR[EÊ]TES:[ \t]*aucune[ \t]*$")
ARETE_RE = _ARETE
# F5 (binôme T-765) : le mot-clé PROCHE, lu APRÈS un décapage linéaire en Python
# (`_proche_du_mot_cle`) — jamais deux classes d'espaces enchaînées dans une regex.
_PROCHE = re.compile(r"AR[EÊ]TES?[ \t]*:")
_PUCE = re.compile(r"(?:[-*+]|\d{1,3}[.)])[ \t]")

TITRE_APPROBATION = plan_cible.normalise_titre("plan approuvé")
_SUGGESTION_PREFIXE = re.compile(r"^\s*SUGGESTION\s*:", re.IGNORECASE)
SUGGESTION_RE = re.compile(
    r"^SUGGESTION:\s*(ajouter|retirer)\s+(T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d{1,12}))"
    r"\s*<-\s*(T-(?:[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z])|\d{1,12}))\s*$")
_RAISON_AMBIGUE = re.compile(r"(?i)(?<![A-Za-z0-9])(plan|sha256)=")

REMEDE_MODULE = "git checkout -- .agents/bin/plan_depends.py .agents/bin/plan_cible.py"
REFUS_RAISON_SANS_DEPENDANCES = (
    "SPECS: refus — la raison de `--sans-dependances` ({raison!r}) contient `plan=` "
    "ou `sha256=` : jointe au texte de la trace, elle rendrait l'empreinte AMBIGUË "
    "(`_empreinte_unique`) et la trace invisible au `done`. Dis pourquoi sans citer "
    "un plan ni un sha."
)

# Chaînes d'aide argparse (R3 : lues par `tasks.py`/`specs.py` derrière le
# chargeur paresseux). ASCII PUR : `--help` sort AVANT `force_utf8_stdio`.
AIDE_CLI = {
    "depends_deps": (
        "task ids this one must wait for. TOTAL REWRITE by default, like writeset, "
        "but GUARDED since T-00000765: an edge whose motif is a canonical "
        "`ORDRE PILOTE S-<id>` is never erased nor re-motived this way (use "
        "--remove-pilot-order). This is an ORDER, not a state: the task stays "
        "pending, so it stays night-eligible - but its start is refused while one "
        "is open (`tasks.py deps-ready <id>`). A done dependency is ADMITTED - it "
        "is a SATISFIED one. A cycle is refused and the whole path is named"
    ),
    "depends_add": (
        "ADD these edges instead of rewriting: existing edges and motifs stay. An id "
        "already declared with the SAME motif is left as is and said; with ANOTHER "
        "motif it is refused, naming the motif in place"
    ),
    "depends_retirer": (
        "drop EXACTLY this technical edge (one upstream id); every other edge and "
        "motif stays. Refused on an edge whose motif is a canonical ORDRE PILOTE "
        "(use --remove-pilot-order) and on an edge that is not declared"
    ),
    "depends_retirer_ordre_pilote": (
        "drop an ORDRE PILOTE edge under a pilot decision: <upstream> <S-ID>, where "
        "S-ID is an EXISTING kind=decision entry of SPECS.json (never a `plan approuve` "
        "trace), DIFFERENT from every S-ID the motif cites (written S-<alnum>, capital S, "
        "nothing glued on its left). No relevance test: the decision is named, never judged"
    ),
    "start_sans_dependances": (
        "start WITHOUT the two dependency legs, and SAY WHY. (1) The upstream leg, "
        "armed EVERYWHERE (S-01M4Z5VMP5E9YN8T6EMDTBAF0T): a start from pending, "
        "blocked or done is refused while `tasks.py deps-ready <id>` says anything "
        "but AMONT_CLOS or REPRISE_DITE. (2) The ARETE: leg, ARMED by "
        "PLAN_CIBLE_REQUIRED for the chantier it names: an ARETE: of the approved "
        "plan whose upstream is absent from depends_on refuses the start. Pilot "
        "only. The mark [SANS DEPENDANCES : arete + amont - <why>] lands in "
        "`stage` whatever the marker and stays VISIBLE on the board"
    ),
    "done_sans_dependances": (
        "close WITHOUT the approved plan's ARETE: control, and SAY WHY. Same regime "
        "as at start; under --sans-cible the leg only REPORTS (one line and a mark), "
        "it never refuses. The reason lands in `stage` and stays VISIBLE on the board"
    ),
    "specs_sans_dependances": (
        "record the `plan approuve` trace WITHOUT the plan's ARETE: control, and SAY "
        "WHY. Refused if the reason carries plan= or sha256= (it would blur the "
        "fingerprint); the reason joins the entry text, visible wherever it is read"
    ),
}


@dataclass(frozen=True)
class Arete:
    aval: str
    amont: str
    motif: str

    def commande_add(self) -> str:
        return (f"python .agents/bin/tasks.py depends {shlex.quote(self.aval)} {shlex.quote(self.amont)} "
                f"--add --motif {shlex.quote(self.motif)}")


@dataclass
class Releve:
    """Ce qu'une jambe a lu : `refus` (fautives ou manquantes), la liste brute des
    `manquantes` pour le mode DIRE, le plan résolu et la note d'emprunt R2."""
    refus: str | None
    manquantes: list[Arete]
    plan: Path
    note: str = ""


@dataclass
class Sortie:
    """Ce que `appliquer_verbe` rend à `tasks.py` pour imprimer : la ligne de
    succès, les avertissements (stderr) et les arêtes retirées."""
    texte: str
    avertissements: list[str] = field(default_factory=list)
    retirees: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LECTURES PURES (mêmes règles que `tasks.py`, recopiées — jamais importées).
# ---------------------------------------------------------------------------
def depends_on_de(task: dict[str, Any]) -> list[str]:
    """La déclaration, `[]` si absente — la règle de `tasks.depends_on_of`."""
    declared = task.get("depends_on")
    if not isinstance(declared, list):
        return []
    return [d for d in declared if isinstance(d, str) and d]


def motifs_de(task: dict[str, Any]) -> dict[str, str]:
    """Les motifs NON VIDES des arêtes déclarées, par amont."""
    bruts = task.get("depends_motif") or {}
    return {d: str(m).strip() for d, m in bruts.items()
            if d in depends_on_de(task) and str(m or "").strip()}


def classe_motif(motif: str | None) -> str:
    """`ordre pilote` (canonique) · `ordre (non canonique)` · `technique`."""
    m = (motif or "").strip()
    if ORDRE_PILOTE_CANONIQUE.match(m):
        return "ordre pilote"
    if _ORDRE_PREFIXE.match(m):
        return "ordre (non canonique)"
    return "technique"


def est_ordre_pilote(motif: str | None) -> bool:
    return classe_motif(motif) == "ordre pilote"


def _board_hors_verrou(root: str | Path) -> dict[str, Any] | None:
    """Le board BRUT hors verrou, dans sa forme (monolithe OU dossier d'enregistrements) : `plan_cible._board_brut`,
    l'UNIQUE lecteur (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) — `None` si absent ; deux formes ou illisible ⇒ `CibleError`
    nommée (passe de correction F5), que `specs.py` rend en refus rc 2. Licite hors verrou : écritures atomiques du
    monolithe, lot validé du dossier."""
    return plan_cible._board_brut(root)


def _taches(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {t["id"]: t for t in (data or {}).get("tasks", [])
            if isinstance(t, dict) and t.get("id")}


def decisions_du_journal(root: str | Path) -> set[str]:
    """Les S-id `kind=decision` MOINS les traces d'approbation (fable F4 : un titre dans
    `plan_cible.TITRES_APPROBATION` dit un plan approuvé, jamais un ordre posé ou LEVÉ)."""
    entrees = plan_cible.entrees_specs(root)
    traces = {e.get("id") for e in entrees
              if plan_cible.normalise_titre(e.get("title") or "") in plan_cible.TITRES_APPROBATION}
    return plan_cible.decisions_existantes(entrees) - traces


def _decisions(decisions: Any) -> set[str]:
    """`decisions` est un ensemble OU une fonction paresseuse (SPECS n'est relu
    que si un motif `ordre pilote` neuf ou un retrait l'exige)."""
    try:
        return set(decisions() if callable(decisions) else decisions)
    except (CibleError, OSError) as exc:
        raise ValueError(str(exc)) from exc


# ---------------------------------------------------------------------------
# GRAMMAIRE — `aretes_du_plan(texte, enrolle, connus)` -> (arêtes, fautives, aucune).
# ---------------------------------------------------------------------------
def aretes_du_plan(
    texte: str,
    enrolle: Callable[[str], bool],
    connus: set[str] | None,
) -> tuple[list[Arete], list[str], bool]:
    """Les arêtes lues HORS bloc de code, les lignes FAUTIVES nommées, et le
    drapeau `ARÊTES: aucune`. `enrolle(tid)` dit si le plan enrôle l'aval ;
    `connus` = ids du board (`None` = pas de board sous la main, contrôle sauté)."""
    aretes: list[Arete] = []
    fautives: list[str] = []
    aucune = False
    for ligne in plan_cible.lignes_hors_code(texte):
        if not _MOT_CLE.match(ligne):
            if _proche_du_mot_cle(ligne):
                fautives.append(
                    f"ligne proche du mot-clé {ligne.strip()!r} — ni lue ni ignorée : écris "
                    f"`ARÊTE: …` ou `ARÊTES: aucune` en tête de ligne (seule la puce `- ` est tolérée)")
            continue
        if _AUCUNE.match(ligne):
            aucune = True
            continue
        m = _ARETE.match(ligne)
        if not m:
            fautives.append(
                f"ligne malformée {ligne.strip()!r} — forme attendue "
                f"`ARÊTE: T-<aval> <- T-<amont> | <motif>` ou `ARÊTES: aucune`")
            continue
        aval, amont, motif = m.group(1), m.group(2), m.group(3).strip()
        arete = f"{aval} <- {amont}"
        if not motif:
            fautives.append(f"{arete} : motif vide (1 à {MOTIF_MAX} caractères)")
        elif motif.startswith("/"):
            fautives.append(f"{arete} : un motif ne commence pas par `/` (lu comme un chemin)")
        elif len(motif) > MOTIF_MAX:
            fautives.append(f"{arete} : motif de {len(motif)} caractères, borne {MOTIF_MAX}")
        elif aval == amont:
            fautives.append(f"{arete} : auto-arête, rien ne la satisferait jamais")
        elif not enrolle(aval):
            fautives.append(f"{arete} : le plan n'ENRÔLE pas {aval} (ligne 1 ou première ligne `Tâches :`)")
        elif connus is not None and (aval not in connus or amont not in connus):
            inconnu = aval if aval not in connus else amont
            fautives.append(f"{arete} : {inconnu} est inconnu du board")
        else:
            aretes.append(Arete(aval, amont, motif))
    if aucune and aretes:
        fautives.append("`ARÊTES: aucune` à côté d'une `ARÊTE:` — le plan dit deux choses")
    return aretes, fautives, aucune


def _proche_du_mot_cle(ligne: str) -> bool:
    """F5 : `ARÊTE :`, `* ARÊTE:`, puce indentée, `**ARÊTE:**`, `>`, NFD — voulue, non lue
    par la forme stricte, donc NOMMÉE. MAJUSCULES seules : `arête :` reste de la prose (W9)."""
    s = unicodedata.normalize("NFC", ligne).lstrip(" \t>")
    puce = _PUCE.match(s)
    if puce:
        s = s[puce.end():].lstrip(" \t")
    return bool(_PROCHE.match(s.lstrip("*_").lstrip(" \t")))


def _lire_plan(chemin: Path) -> str:
    """Le texte du plan ; non UTF-8 ⇒ `CibleError` NOMMÉE (opus T2) — un
    `UnicodeDecodeError` nu échappait aux sites et figeait le pont V3 en échec."""
    try:
        return chemin.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CibleError(
            f"plan approuvé {chemin.name} illisible en UTF-8 ({exc.reason}, octet {exc.start}) : "
            f"réécris-le en UTF-8, recalcule son sha256 et rejoue l'approbation") from exc


def _cause(exc: Exception, root: str | Path | None = None) -> str:
    """`CibleError`/`OSError` tels quels ; tout autre `ValueError` (dont un `UnicodeDecodeError`
    de la garde R2 de `plan_cible`) NOMMÉ — jamais un message de codec seul. Avec `root`, la RACINE
    est retirée (avis de sécurité S-01M5072DQ863DE4RKPMKE9K4G1, même forme que la jambe cible de
    `set_state`) : chemin relatif et remède restent, et rien d'absolu n'atteint le `stage` du board."""
    texte = str(exc) if isinstance(exc, (CibleError, OSError)) else (
        f"garde des dépendances de plan : lecture impossible ({type(exc).__name__} : {exc})")
    if root is None:
        return texte
    # Telle quelle ET résolue (macOS : /var → /private/var), la PLUS LONGUE d'abord : retirer d'abord
    # `/var/…/` dans `/private/var/…/x` laisserait `/privatex`.
    for racine in sorted({os.path.abspath(str(root)), str(Path(root).resolve())}, key=len, reverse=True):
        texte = texte.replace(racine + os.sep, "")
    return texte


def _uniques(aretes: list[Arete]) -> list[Arete]:
    """Une arête par `(aval, amont)` (fable F7) ; un doublon `ORDRE PILOTE`
    l'emporte sur un doublon technique — jamais un `--add` prescrit à sa place."""
    vues: dict[tuple[str, str], Arete] = {}
    for a in aretes:
        cle = (a.aval, a.amont)
        if cle not in vues or (est_ordre_pilote(a.motif) and not est_ordre_pilote(vues[cle].motif)):
            vues[cle] = a
    return list(vues.values())


def _commande(a: Arete) -> str:
    """Remède d'une arête manquante ; ORDRE PILOTE ⇒ JAMAIS un `--add` exécutable (fable F1 :
    levé, le réinscrire annulerait la décision sans trace) — un commentaire `#` à deux cas."""
    if not est_ordre_pilote(a.motif):
        return a.commande_add()
    return (f"# ORDRE PILOTE {a.aval} <- {a.amont} : s'il a été LEVÉ, le plan est PÉRIMÉ "
            f"(révision ré-approuvée ou --sans-dependances) ; sinon {a.commande_add()}")


def _refus_fautives(surface: str, geste: str, tid: str, chemin: Path,
                    fautives: list[str], note: str) -> str:
    liste = "\n".join(f"  - {f}" for f in fautives)
    emprunt = f" {note}" if note else ""
    return (
        f"{surface}: refus de {geste} {tid} — le plan approuvé {chemin.name}{emprunt} "
        f"porte des lignes `ARÊTE:` fautives :\n{liste}\n"
        f"Forme fermée : `ARÊTE: T-<aval> <- T-<amont> | <motif>` (une par ligne, hors "
        f"bloc de code), ou `ARÊTES: aucune`. Corrige le plan, recalcule son sha256 et "
        f"rejoue l'approbation.\n"
        f"Sortie tracée : `--sans-dependances \"<pourquoi>\"`, visible au board."
    )


def _refus_manquantes(surface: str, geste: str, tid: str, chemin: Path,
                      manquantes: list[Arete], note: str) -> str:
    manquantes = _uniques(manquantes)
    liste = "\n".join(f"  - {a.aval} <- {a.amont} | {a.motif!r}" for a in manquantes)
    commandes = "\n".join(f"  {_commande(a)}" for a in manquantes)
    emprunt = f" {note}" if note else ""
    return (
        f"{surface}: refus de {geste} {tid} — le plan approuvé {chemin.name}{emprunt} "
        f"porte {len(manquantes)} ARÊTE(S) que le board n'inscrit pas :\n{liste}\n"
        f"Inscris chaque arête (commande prête ; une ligne `#` se lit avant d'agir), puis rejoue :\n{commandes}\n"
        f"La garde compare l'AMONT à `depends_on` de l'aval, jamais le motif ; une "
        f"arête du board absente du plan n'est jamais un refus.\n"
        f"Sortie tracée : `--sans-dependances \"<pourquoi>\"`, visible au board."
    )


# --- LES JAMBES `start` / `done`. ---
def refus_dependances(
    root: str | Path, tid: str, data: dict[str, Any], *, slot: bool
) -> Releve | None:
    """L'UNIQUE lecteur du régime et du plan pour `start` (`slot=False`, R1 seule)
    et `done` (`slot=True`, R1 puis R2). `None` = inerte : marqueur absent, tâche
    hors chantier, aucun plan résolu (la cible nomme déjà R3), ou plan sans
    AUCUNE des deux formes (plan figé). `CibleError`/`OSError`/`ValueError`
    remontent ; un amont absent du board est DIT sur stderr (F2), pas refusé."""
    if plan_cible._arme_pour_tache(root, tid, data, avertir=False) is None:
        return None
    resolu = plan_cible.resoudre_plan(root, tid, data, slot=slot)
    if resolu is None:
        return None
    chemin, note = resolu
    texte = _lire_plan(chemin)
    taches = _taches(data)
    # `connus=None` (fable F2) : les ids ont été contrôlés à la TRACE ; un id absent
    # ICI est une tâche purgée depuis, DITE ci-dessous, jamais un refus perpétuel.
    aretes, fautives, aucune = aretes_du_plan(
        texte, lambda t: plan_cible.enrolling_line(texte, t), None)
    geste = "clore" if slot else "démarrer"
    if fautives:
        return Releve(_refus_fautives("TASKS", geste, tid, chemin, fautives, note), [], chemin, note)
    if not aretes and not aucune:
        return None
    declarees = set(depends_on_de(taches.get(tid, {})))
    manquantes: list[Arete] = []
    for a in _uniques([a for a in aretes if a.aval == tid]):
        if a.amont not in taches:
            print(f"TASKS: {tid} — ARÊTE {a.aval} <- {a.amont} du plan {chemin.name} non contrôlée — "
                  f"{a.amont} absent du board (purgé ?)", file=sys.stderr)
        elif a.amont not in declarees:
            manquantes.append(a)
    refus = _refus_manquantes("TASKS", geste, tid, chemin, manquantes, note) if manquantes else None
    return Releve(refus, manquantes, chemin, note)


def _marque_derogation(root: str | Path, pourquoi: str) -> str | None:
    """`[SANS DÉPENDANCES : …]` SEULEMENT si le marqueur est armé (même règle que
    `[SANS CIBLE]` : pas de dérogation affichée sur un dépôt désarmé)."""
    if not (Path(root) / plan_cible.MARQUEUR).exists():
        return None
    return f"[SANS DÉPENDANCES : {pourquoi}]"


def jambe_start(
    root: str | Path, tid: str, data: dict[str, Any], *, sans_dependances: str = ""
) -> tuple[str | None, list[str], str | None]:
    """Site unique de `set_state` au `running` : `(refus, lignes, marque)`.
    Aucune décision propre — mise en forme de `refus_dependances(slot=False)`.
    `--sans-cible` ne change rien à cette jambe au `start`. Sous `--sans-dependances`
    elle saute et ne MARQUE plus : la marque `arête + amont` est celle de la jambe
    d'amont de `set_state`, posée quel que soit le marqueur (S-01M4Z5VMP5E9YN8T6EMDTBAF0T)."""
    if sans_dependances:
        return (None, [], None)
    try:
        releve = refus_dependances(root, tid, data, slot=False)
    except (CibleError, OSError, ValueError) as exc:  # ValueError ⊃ UnicodeDecodeError (opus T2)
        return (_cause(exc, root), [], None)
    return (releve.refus if releve else None, [], None)


def jambe_done(
    root: str | Path, tid: str, data: dict[str, Any], *,
    sans_dependances: str, sans_cible: str,
) -> tuple[str | None, list[str], str | None]:
    """Site unique de `set_state` au `done` : `(refus, lignes, marque)`. Sous
    `sans_cible` (pont V3 M9, tableau de bord, humain) c'est le MODE DIRE : ne
    lève JAMAIS, une ligne après `TASKS: <tid> → done` et une marque au `stage`
    DANS CHAQUE CAS où le contrôle n'a pas eu lieu en entier (opus T3) — arête
    manquante, lignes fautives, exception (cause bornée à 200 caractères)."""
    if sans_dependances:
        return (None, [], _marque_derogation(root, sans_dependances))
    prefixe = f"TASKS: {tid} close SANS contrôle des dépendances du plan (sous --sans-cible) : "
    try:
        releve = refus_dependances(root, tid, data, slot=True)
    except (CibleError, OSError, ValueError) as exc:  # ValueError ⊃ UnicodeDecodeError (opus T2)
        if sans_cible:
            court = " ".join(_cause(exc, root).split())[:200]
            return (None, [f"{prefixe}contrôle impossible — {_cause(exc, root)}"],
                    f"[SANS DÉPENDANCES : contrôle impossible sous --sans-cible — {court}]")
        return (_cause(exc, root), [], None)
    if releve is None:
        return (None, [], None)
    if not sans_cible:
        return (releve.refus, [], None)
    if releve.manquantes:
        liste = ", ".join(f"{a.aval} <- {a.amont}" for a in releve.manquantes)
        return (None, [f"{prefixe}{liste}"],
                f"[SANS DÉPENDANCES : relevé sous --sans-cible — {liste}]")
    if releve.refus:
        fautif = f"lignes ARÊTE: fautives dans {releve.plan.name}"
        return (None, [f"{prefixe}lignes `ARÊTE:` fautives dans {releve.plan.name}"],
                f"[SANS DÉPENDANCES : relevé sous --sans-cible — {fautif}]")
    return (None, [], None)


# --- LA JAMBE D'APPROBATION (`specs.py add`, titre `plan approuvé` SEUL). ---
def refus_dependances_a_lapprobation(
    root: str | Path, task: str, kind: str, title: str, text: str
) -> str | None:
    """Mord SEULEMENT sur `kind=decision` titré `plan approuvé` (normalisé) —
    jamais `night-eligible: approved` (M10/A-C3, asymétrie assumée : trace R1
    valide pour la CIBLE, jamais recontrôlée ici). Refuse les fautives, les
    arêtes manquantes pour TOUT aval enrôlé, ET l'absence des deux formes."""
    if kind != "decision" or plan_cible.normalise_titre(title or "") != TITRE_APPROBATION:
        return None
    if plan_cible._arme_pour_tache(root, task) is None:
        return None
    chemin = plan_cible._plan_de_trace(root, text or "")
    if chemin is None:
        return None
    texte = _lire_plan(chemin)
    board = _board_hors_verrou(root)
    taches = _taches(board)
    aretes, fautives, aucune = aretes_du_plan(
        texte, lambda t: plan_cible.enrolling_line(texte, t),
        set(taches) if board is not None else None)
    geste = "tracer l'approbation de"
    if fautives:
        return _refus_fautives("SPECS", geste, task, chemin, fautives, "")
    if not aretes and not aucune:
        return (
            f"SPECS: refus de {geste} {task} — le plan {chemin.name} ne porte NI "
            f"`ARÊTE:` NI `ARÊTES: aucune`. Une trace `plan approuvé` neuve exige "
            f"l'une des deux formes (une ligne par arête, hors bloc de code, ou "
            f"`ARÊTES: aucune`) ; ajoute-la, recalcule le sha256 et rejoue.\n"
            f"Sortie tracée pour un plan figé avant l'exigence des arêtes : "
            f"`--sans-dependances \"<pourquoi>\"`, jointe au texte de la trace."
        )
    manquantes = [a for a in aretes
                  if a.amont not in set(depends_on_de(taches.get(a.aval, {})))]
    if manquantes:
        return _refus_manquantes("SPECS", geste, task, chemin, manquantes, "")
    return None


# --- VALIDATIONS PURES. ---
def valider_motif_neuf(motif: str, decisions: Any) -> str | None:
    """Un motif NEUF ouvrant par `ordre pilote` (casse ignorée) doit être
    canonique ET citer une `kind=decision` existante (M3). Sinon `None`."""
    m = (motif or "").strip()
    if not _ORDRE_PILOTE_PREFIXE.match(m):
        return None
    if not ORDRE_PILOTE_CANONIQUE.match(m):
        return (f"motif {m!r} ouvre par `ordre pilote` sans être canonique — forme "
                f"fermée `ORDRE PILOTE S-<id> : <pourquoi>` (majuscules, S-id de la "
                f"décision pilote : `S-<ULID>` ou l'ancienne forme sur 8 chiffres)")
    sid = _SID_DU_MOTIF.match(m).group(1)
    if sid not in _decisions(decisions):
        return (f"motif {m!r} cite {sid}, qui n'est pas une entrée `kind=decision` de "
                f"SPECS.json (une trace `plan approuvé` n'en est pas une) — un ORDRE PILOTE "
                f"nomme une décision du pilote qui EXISTE")
    return None


def _cle_sid(corps: str) -> tuple[str, str]:
    """Clé d'un corps de S-id (T-00001062) ; bornes et mutants : W27 (test_plan_depends_guard)."""
    return ("n", corps.lstrip("0") or "0") if corps.isdigit() else ("s", corps.upper())


def sids_cites(motif: str | None) -> set[tuple[str, str]]:
    """Les clés de TOUTES les S-id que le motif cite (T-00001062) ; témoins : W26, W27."""
    return {_cle_sid(c) for c in _SIDS_CITES.findall(motif or "")}


def valider_retrait_ordre_pilote(
    avant: dict[str, Any], amont: str, sid: str, decisions: Any
) -> str | None:
    """`--retirer-ordre-pilote <amont> <S-id>` : arête ORDRE PILOTE, S-id d'une
    `kind=decision` existante ET différente de TOUTES celles du motif (`sids_cites`).
    AVEU : aucun test de PERTINENCE — la décision est nommée, jamais jugée."""
    tid = avant.get("id", "?")
    motif = motifs_de(avant).get(amont)
    if amont not in depends_on_de(avant):
        return f"depends {tid} --retirer-ordre-pilote {amont}: no such edge"
    if not est_ordre_pilote(motif):
        return (f"depends {tid} --retirer-ordre-pilote {amont}: this edge is not an "
                f"ORDRE PILOTE (motif : {repr(motif) if motif else 'héritée'}) — use `tasks.py depends "
                f"{shlex.quote(tid)} --retirer {shlex.quote(amont)}`")
    if not _SID.fullmatch(sid or ""):
        return f"depends {tid} --retirer-ordre-pilote: S-ID malformé ({sid!r}), attendu `S-<chiffres>` ou `S-<ULID>`"
    if _cle_sid(sid[2:]) in sids_cites(motif):
        return (f"depends {tid} --retirer-ordre-pilote {amont} {sid}: {sid} est citée par "
                f"le motif — une décision citée par le motif ne peut pas autoriser son propre "
                f"retrait — il faut une décision pilote DISTINCTE de TOUTES celles du motif "
                f"(kind=decision) qui lève l'ordre")
    if sid not in _decisions(decisions):
        return (f"depends {tid} --retirer-ordre-pilote {amont} {sid}: {sid} n'est pas une "
                f"entrée `kind=decision` de SPECS.json (une trace `plan approuvé` ou "
                f"`night-eligible: approved` ne lève pas un ordre)")
    return None


def motif_ordre_pilote_refus(
    avant: dict[str, Any], apres: list[str], motifs_apres: dict[str, str]
) -> str | None:
    """Réécriture totale / `--clear` : refuse, sans rien écrire, toute arête
    ORDRE PILOTE PERDUE ou dont le motif CHANGE."""
    tid = avant.get("id", "?")
    for amont, motif in motifs_de(avant).items():
        if not est_ordre_pilote(motif):
            continue
        if amont not in apres:
            return (f"depends {tid}: this would ERASE the ORDRE PILOTE edge {tid} <- {amont} "
                    f"({motif!r}). Nothing was written. Keep it with `--add`, or lift it "
                    f"under a pilot decision: `tasks.py depends {shlex.quote(tid)} "
                    f"--retirer-ordre-pilote {shlex.quote(amont)} S-<decision>`")
        if motifs_apres.get(amont) != motif:
            return (f"depends {tid}: this would CHANGE the motif of the ORDRE PILOTE edge "
                    f"{tid} <- {amont} (in place : {motif!r}). Nothing was written. "
                    f"Re-state it verbatim, or use `--add` for the other edges")
    return None


def valider_suggestion(kind: str, title: str, text: str) -> str | None:
    """Un `kind=delta` titré `SUGGESTION:` parse la grammaire fermée et porte un
    `--text` non vide. Tout autre titre ou kind : `None`."""
    if kind != "delta" or not _SUGGESTION_PREFIXE.match(title or ""):
        return None
    m = SUGGESTION_RE.match((title or "").strip())
    if not m:
        return (f"SPECS: refus — titre `SUGGESTION:` malformé ({title!r}) ; forme fermée "
                f"`SUGGESTION: ajouter|retirer T-<aval> <- T-<amont>`")
    if m.group(2) == m.group(3):
        return f"SPECS: refus — SUGGESTION sur une auto-arête ({m.group(2)} <- {m.group(3)})"
    if not (text or "").strip():
        return ("SPECS: refus — une SUGGESTION porte un `--text` non vide : le pilote "
                "tranche sur une raison, pas sur un titre")
    return None


def raison_sans_dependances_valide(raison: str) -> bool:
    """Faux si la raison contient `plan=` ou `sha256=` (empreinte ambiguë)."""
    return not _RAISON_AMBIGUE.search(raison or "")


# --- REMÈDES QUI NE DÉTRUISENT RIEN. ---
def remede_coupe(data: dict[str, Any], chemin: list[str]) -> str:
    """Parmi les arêtes du chemin DÉJÀ inscrites au board, la PREMIÈRE dont le
    motif n'est pas ORDRE PILOTE → `depends <aval> --retirer <amont>` en nommant
    ce qui reste ; toutes ordre pilote → la route SUGGESTION puis
    `--retirer-ordre-pilote` « après décision »."""
    taches = _taches(data)
    inscrites: list[tuple[str, str, str | None]] = []
    for aval, amont in zip(chemin, chemin[1:]):
        t = taches.get(aval)
        if t is None or amont not in depends_on_de(t):
            continue  # l'arête qu'on DÉCLARE, pas encore au board
        inscrites.append((aval, amont, motifs_de(t).get(amont)))
    for aval, amont, motif in inscrites:
        if est_ordre_pilote(motif):
            continue
        t = taches[aval]
        restes = [f"{d} ({repr(motifs_de(t)[d]) if d in motifs_de(t) else 'héritée'})"
                  for d in depends_on_de(t) if d != amont]
        suite = f" (restent : {', '.join(restes)})" if restes else " (c'était sa seule arête)"
        # Ids du board = DONNÉES : chaque commande imprimée les passe par `shlex.quote`
        # (la SUGGESTION entière aussi). Bornes : quotage POSIX seul ; un id qui commence
        # par `-` est lu comme une option (refus argparse, jamais une écriture) ; un
        # caractère de contrôle (ESC) dans un id n'est pas neutralisé — non couvert ici.
        return f"`tasks.py depends {shlex.quote(aval)} --retirer {shlex.quote(amont)}`{suite}"
    if not inscrites:
        return "(aucune arête du chemin n'est inscrite au board)"
    aval, amont, _motif = inscrites[0]
    suggestion = shlex.quote(f"SUGGESTION: retirer {aval} <- {amont}")
    return (
        f"every edge of this path is an ORDRE PILOTE — an agent never drops one. Route : "
        f"`specs.py add --task {shlex.quote(aval)} --kind delta {suggestion} "
        f"--text \"<pourquoi>\"`, then, after the pilot's decision, "
        f"`tasks.py depends {shlex.quote(aval)} --retirer-ordre-pilote {shlex.quote(amont)} S-<decision du pilote>`"
    )


# --- LE VERBE — PUR, sur une COPIE ; helpers de `tasks.py` reçus en ARGUMENTS. ---
def appliquer_verbe(
    avant: dict[str, Any],
    deps: list[str],
    motifs: list[str],
    *,
    mode: str,
    resoudre: Callable[[str], str | None],
    cycle_de: Callable[[list[str]], list[str] | None],
    decisions: Any,
    taches: list[dict[str, Any]],
    retrait: tuple[str, str | None] | None = None,
) -> tuple[list[str], dict[str, str], Sortie]:
    """`(wanted, motif_by_dep, sortie)` pour `mode` ∈ {reecriture, clear, add,
    retirer, retirer_ordre_pilote}. `resoudre(raw) -> id | None` (résolution
    EXACTE, `tasks.find`), `cycle_de(wanted) -> chemin | None`
    (`tasks.dependency_cycle`), `decisions` (ensemble ou fonction paresseuse),
    `taches` = le board (lecture, pour `remede_coupe`). Lève `ValueError` nommée
    que `tasks.py` rend en `BoardError`. Aucune écriture, aucun verrou."""
    tid = avant["id"]
    existants = depends_on_de(avant)
    motifs_avant = motifs_de(avant)
    avert: list[str] = []

    if mode in ("retirer", "retirer_ordre_pilote"):
        brut, sid = retrait or ("", None)
        amont = brut if brut in existants else (resoudre(brut) or brut)
        drapeau = "--retirer" if mode == "retirer" else "--retirer-ordre-pilote"
        if amont not in existants:
            raise ValueError(
                f"depends {tid} {drapeau} {brut}: no such edge — {tid} depends on "
                f"{', '.join(existants) or 'nothing'}")
        motif = motifs_avant.get(amont)
        if mode == "retirer":
            if est_ordre_pilote(motif):
                raise ValueError(
                    f"depends {tid} --retirer {amont}: this edge is an ORDRE PILOTE "
                    f"({motif!r}) — an agent never drops one; under a pilot decision use "
                    f"`tasks.py depends {shlex.quote(tid)} --retirer-ordre-pilote {shlex.quote(amont)} S-<decision>`")
        else:
            refus = valider_retrait_ordre_pilote(avant, amont, sid or "", decisions)
            if refus:
                raise ValueError(refus)
        wanted = [d for d in existants if d != amont]
        motif_by_dep = {d: motifs_avant[d] for d in wanted if d in motifs_avant}
        detail = f"retirée : {amont} ({repr(motif) if motif else 'héritée'})"
        if mode == "retirer_ordre_pilote":
            detail += f" sous {sid}"
        if wanted:
            texte = f"{_ligne_declaration(tid, wanted)} ({detail})"
        else:
            texte = f"TASKS: {tid} depends_on cleared ({detail}, la dernière)"
        return wanted, motif_by_dep, Sortie(texte, avert, [amont])

    wanted: list[str] = list(existants) if mode == "add" else []
    motif_by_dep: dict[str, str] = dict(motifs_avant) if mode == "add" else {}
    inchangees: list[str] = []
    motivees: list[str] = []
    deduped = 0
    if mode != "clear":
        for i, raw in enumerate(deps):
            dep = resoudre(raw)
            if dep is None:
                raise ValueError(f"unknown task id: {raw}")
            if dep == tid:
                raise ValueError(f"{tid} cannot depend on itself: nothing would ever satisfy it")
            motif = motifs[0] if len(motifs) == 1 else motifs[i]
            if dep in wanted:
                if mode == "add" and dep in existants and dep not in inchangees + motivees:
                    en_place = motifs_avant.get(dep)
                    if en_place is None:
                        motif_by_dep[dep] = motif
                        motivees.append(dep)
                    elif en_place == motif:
                        inchangees.append(dep)
                    else:
                        raise ValueError(
                            f"depends {tid} --add {dep}: edge already declared with motif "
                            f"{en_place!r} — keep it as is, or `--retirer {shlex.quote(dep)}` first "
                            f"(an ORDRE PILOTE needs --retirer-ordre-pilote)")
                    continue
                deduped += 1  # doublon DANS l'appel : le motif de la première occurrence reste
                continue
            wanted.append(dep)
            motif_by_dep[dep] = motif
        for dep, motif in motif_by_dep.items():
            if dep in existants and motifs_avant.get(dep) == motif:
                continue
            refus = valider_motif_neuf(motif, decisions)
            if refus:
                raise ValueError(f"depends {tid}: {refus}")
            if classe_motif(motif) == "ordre (non canonique)":
                avert.append(
                    f"depends {tid}: AVERTISSEMENT — motif {motif[:80]!r} ouvre par `ordre` "
                    f"sans être un `ORDRE PILOTE S-<id>` canonique : il est traité comme "
                    f"TECHNIQUE (retirable par --retirer, non protégé)")
        cycle = cycle_de(wanted)
        if cycle is not None:
            raise ValueError(
                f"declaring this would close a cycle: {' → '.join(cycle)}. Nothing was "
                f"written — the edge that closes it is {cycle[-2]} → {cycle[-1]}; drop "
                f"it, or cut the cycle with {remede_coupe({'tasks': taches}, cycle)}")

    if mode in ("reecriture", "clear"):
        refus = motif_ordre_pilote_refus(avant, wanted, motif_by_dep)
        if refus:
            raise ValueError(refus)
    perdues = [d for d in existants if d not in wanted]
    for d in perdues:
        if classe_motif(motifs_avant.get(d)) == "ordre (non canonique)":
            avert.append(f"depends {tid}: AVERTISSEMENT — arête `ordre…` non canonique "
                         f"perdue : {tid} <- {d} ({motifs_avant[d]!r})")
    for d in wanted:
        if d in existants and d in motifs_avant and motif_by_dep.get(d) != motifs_avant[d] \
                and classe_motif(motifs_avant[d]) == "ordre (non canonique)":
            avert.append(f"depends {tid}: AVERTISSEMENT — motif `ordre…` non canonique "
                         f"changé sur {tid} <- {d} (était : {motifs_avant[d]!r})")
    tails: list[str] = []
    if deduped:
        tails.append(f"({deduped} duplicate id{'' if deduped == 1 else 's'} dropped)")
    if perdues:
        tails.append(f"(retirée{'' if len(perdues) == 1 else 's'} : {', '.join(perdues)})")
    if inchangees:
        tails.append(f"(inchangée{'' if len(inchangees) == 1 else 's'} : {', '.join(inchangees)})")
    if motivees:
        tails.append(f"(motivée{'' if len(motivees) == 1 else 's'} : {', '.join(motivees)})")
    suite = (" " + " ".join(tails)) if tails else ""
    if mode == "clear" or not wanted:
        texte = f"TASKS: {tid} depends_on cleared{suite}"
    else:
        texte = f"{_ligne_declaration(tid, wanted)}{suite}"
    return wanted, motif_by_dep, Sortie(texte, avert, perdues)


def _ligne_declaration(tid: str, wanted: list[str]) -> str:
    plural = "y" if len(wanted) == 1 else "ies"
    return f"TASKS: {tid} depends_on = {len(wanted)} dependenc{plural}: {', '.join(wanted)}"
