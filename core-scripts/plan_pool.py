#!/usr/bin/env python3
"""Relevé de fraîcheur sur le pool de plans préparés par `/planning` — lecture seule ; écrit le jalon chrono local (avis, jamais bloquant), 0 LLM.

REPRIS de `op-agentic-builder-kit/core-scripts/plan_pool.py`, avec UNE correction
qui n'est pas cosmétique : leur grammaire de verdicts ne reconnaît que
`PASS|CONCERNS|FAIL` APRÈS UN DEUX-POINTS obligatoire. Mesuré sur nos 182
verdicts `plan-critic` réels : **6 reconnus, soit 3 %**. Adoptée telle quelle,
elle aurait classé 97 % de notre journal en `PLAN_SANS_VERDICT` et le pool
aurait tout refusé — un déni de service qui aurait l'air d'une prudence.

Et la cause dominante n'est pas celle qu'on croit. Le vocabulaire compte pour
peu (14 `NO_GO` + 5 `GO_AVEC_RESERVES`) ; **155 titres sur 182 ne portent
simplement PAS de deux-points** — `plan-critic FAIL 2/2 (rev2)`,
`plan-critic CONCERNS (iteration 1/3)`. C'est le SÉPARATEUR qui rejetait, pas
le mot. Une grammaire adoptée se mesure sur le corpus CIBLE, jamais sur celui
de l'auteur d'origine.

CE SCRIPT NE FAIT PAS AUTORITÉ SUR L'ÉLIGIBILITÉ D'UNE NUIT
------------------------------------------------------------
Il y a DEUX machines à verdict dans ce dépôt et elles ne mesurent pas la même
chose. Confondre les deux donnerait soit une nuit qui part sur un plan périmé,
soit un pool qui refuse tout.

  `/night`        AUTORITÉ. Éligibilité d'UNE tâche approuvée : état `pending`,
                  contrat présent, **sha256 du SNAPSHOT `docs/tasks/T-NNN-plan.md`
                  recalculé et identique**, plan commité (identique à HEAD),
                  verdict cité GO/GO_AVEC_RESERVES, plan ENRÔLANT. Voir `.claude/commands/night.md`
                  § Contrat d'éligibilité. Ce script n'est appelé nulle part
                  dans cette chaîne, et il ne doit pas l'être.

  `plan_pool.py`  RELEVÉ AMONT. Fraîcheur d'un plan préparé par `/planning` :
                  le write-set déclaré au checkpoint a-t-il bougé depuis le sha
                  qui le tamponne (`git diff --name-only <sha>..HEAD` ∩ write-set) ?
                  Il PRÉPARE et n'ADMET rien. Un `READY` ici ne rend aucune
                  tâche éligible à la nuit ; un code non nul dit seulement
                  « replanifie avant d'y toucher ». Un plan portant
                  `STATUS: IN_PROGRESS` ou `STATUS: CRITIC_REJECTED` reste un
                  brouillon de reprise : il n'est jamais admis comme READY.

Le premier fige un FICHIER par empreinte, le second surveille un ENSEMBLE DE
FICHIERS par diff git. Un plan peut être READY ici et refusé par `/night`
(pas de contrat), ou éligible là-bas et STALE ici (le snapshot n'a pas bougé
mais le code qu'il décrit, si).

L'ÉCRIVAIN, LE LECTEUR, ET LEURS DÉCLENCHEURS — nommés, parce qu'un mécanisme
sans lecteur n'existe pas (L-00000136)
-------------------------------------------------------------------------------
  écrivain : le workflow `/planning` (`.agents/skills/planning/SKILL.md`), via
             `specs.py add` aux titres canoniques. Déclencheur : le pilote.
  lecteur 1: `plan_pool.py status`, à la fin de `/planning` et chaque fois que
             le pilote demande ce qui est prêt.
  lecteur 2: `plan_pool.py check T-NNNNNNNN`, À LA CONSOMMATION — avant de
             démarrer une tâche du pool. Tout code non nul → on replanifie.
  NON-lecteur, dit pour que personne ne le suppose : `/night`. Ses
             conditions sont les siennes et ne passent pas par ici — dont
             `condition_draft`, ajoutée le 2026-09-12 : le refus du brouillon
             vivait ICI SEULEMENT, sur la surface qui PRÉPARE, alors que la
             surface qui ADMET l'ignorait.

DEUX STORES LUS, JAMAIS ÉCRITS, JAMAIS IMPORTÉS
-----------------------------------------------
Lecture DIRECTE du board et du journal SPECS, chacun dans SA forme
(T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : `.agents/state/board/TASKS.json` OU les
enregistrements `board/tasks/<id>.json` (enveloppe `{"format", "id", "record"}`,
tombe `record: null` écartée) ; `.agents/state/specs/SPECS.json` OU le journal
`SPECS.jsonl`, lu selon les règles de `specs._parse_journal` RECOPIÉES (découpe
sur `\\n` seul, en-tête, union de fusion), pas sa validation de champs (écart
nommé). Les DEUX formes d'un magasin ⇒ refus nommé, jamais une préférence muette.
On n'importe AUCUN code de `.agents/bin/` :
c'est du code vendored chez un adoptant (protected-paths), et un import
coupleraient la survie de ce script à des réorganisations qui ne lui
appartiennent pas (une exception bornée : `jalon_chrono`, chargé par chemin
après un `check` READY, dont la panne n'est qu'un avis). Un store MALFORMÉ est un échec franc (exit 1, stderr) :
dégrader silencieusement un journal cassé en « pas de plan » ferait replanifier
des tâches qui en ont un — la pire des lectures, en sens inverse du risque.
BORNE : un lot du dossier EN VOL (`.agents/state/local/`) n'est pas superposé.

LE CONTRAT — TOUT ÉCART EST UN NON-READY, JAMAIS UNE SUPPOSITION
-----------------------------------------------------------------
READY exige les SEPT conditions, dans cet ordre :

  1. le write-set (`files`) du dernier checkpoint `kind=plan` est clos et NON
     VIDE (sinon WRITE_SET_ABSENT) ;
  2. ce checkpoint porte l'un des DEUX titres CANONIQUES admis (sinon
     SHA_ABSENT — un plan non tamponné n'a pas de date de péremption) :
     « Plan @ <sha> - <objet> », le canon, celui qu'écrit `/planning` ;
     « Plan de reserve @ <sha> - <objet> », l'ancien préfixe, gardé pour la
     COMPAT ADOPTANTS — fixtures du banc et journaux des dépôts qui ont vécu
     sous l'ancien nom (mesuré : 0 titre de cette forme dans le SPECS.json
     d'ici, donc ce n'est PAS une non-régression du passé de ce dépôt) ;
  3. un checkpoint `kind=verdict` POSTÉRIEUR au plan (clé d'id plus grande :
     `S-` ancien par NUMÉRO, puis tout `S-<ULID>` dans l'ordre de frappe —
     `sort_key`, T-00000726) dont le titre rentre dans la GRAMMAIRE ci-dessous
     (sinon PLAN_SANS_VERDICT) ;
  4. ce verdict n'est ni NO_GO ni FAIL (sinon VERDICT_FAIL) ;
  5. NI le fichier canonique `docs/tasks/<tid>-plan.md`, NI le plan RÉELLEMENT
     CITÉ par le verdict, ne porte un marqueur de brouillon — `IN_PROGRESS` ou
     `CRITIC_REJECTED` (sinon PLAN_SANS_VERDICT). Le marqueur est lu par
     `draft_marker`, qui tolère l'ornementation ; et les DEUX chemins sont
     examinés parce qu'ils peuvent désigner des fichiers différents — une tâche
     enrôlée dans un plan de LOT n'a pas de fichier canonique du tout ;
  6. quand le verdict cite `plan=`, QUEL QUE SOIT LE CHEMIN, ce chemin est sûr
     — relatif, sans `..`, d'extension `.md` — et son `sha256=`, s'il en porte
     un, est celui des octets relus là (sinon STALE). Deux empreintes
     contradictoires sont un refus ; AUCUNE empreinte reste admis, c'est la
     forme des journaux antérieurs au contrat progressif ;
  7. le sha est résoluble (`git cat-file -e <sha>^{commit}`) ET le write-set
     est intact depuis — sinon STALE : sha introuvable (rebase/amend/shallow)
     OU fichier bougé, les deux se disent.

(1) est prononcé AVANT (2) : un write-set vide est un défaut structurel,
mesurable sans le titre. READY exige TOUTES les conditions ci-dessus ; l'ordre
ne choisit que le diagnostic. **Le nombre n'est pas répété en prose** — un
cardinal recopié à côté d'une liste devient faux à la première condition
ajoutée, et c'est exactement ce qui s'est produit ici : la liste disait SEPT et
la phrase disait CINQ, dans le même docstring.

GRAMMAIRE DES TITRES — ANCRÉE, JAMAIS UN BALAYAGE DE SOUS-CHAÎNE
------------------------------------------------------------------
Notre journal porte des titres libres (`plan-critic FAIL 1/2 puis FAIL 2/2
(3 blocking chacun)`). Chercher « GO » n'importe où dedans classerait READY un
plan que son critique a envoyé au tapis — et pire : `NO_GO` CONTIENT `GO`.

  plan    : ^Plan( de reserve)? @ <sha-hexa 4..40> - <objet>$
            alternance CLOSE : `Plan @ …` (le canon, écrit par `/planning`) ou
            `Plan de reserve @ …` (compat adoptants). Rien d'autre — ni
            `Planning @ …`, ni un double espace avant l'arobase.
  verdict : ^plan-critic … <séparateur> <VERDICT>
            séparateur = deux-points OU espace(s) — les DEUX, parce que 155 de
            nos 182 titres réels n'ont pas de deux-points.
            VERDICT   = GO_AVEC_RESERVES | NO_GO | GO | PASS | CONCERNS | FAIL

L'alternance est ordonnée du plus long au plus court. Ce n'est pas une
précaution de style : `NO_GO` et `GO_AVEC_RESERVES` contiennent tous deux la
sous-chaîne `GO`, et une alternance qui essaierait `GO` d'abord lirait
« NO_GO » comme un feu vert sur un plan refusé. Le `\\b` final ne rattrape pas
tout — `_` est un caractère de mot, donc `GO\\b` ne mord pas sur `GO_AVEC…`,
mais l'ordre rend la propriété VISIBLE au lieu de la laisser dépendre d'une
subtilité de la classe `\\w`.

VOCABULAIRE VIVANT ET VOCABULAIRE HISTORIQUE — les deux sont admis
-------------------------------------------------------------------
Le vivant est `GO` / `GO_AVEC_RESERVES` / `NO_GO` (AGENTS.md § Golden rules).
`PASS` / `CONCERNS` / `FAIL` sont HISTORIQUES : 80 entrées de notre journal les
portent, et `/night` les tient explicitement pour éligibles. Les refuser
périmerait le passé d'un coup. Les fixtures du banc, elles, sont écrites dans
le vocabulaire VIVANT : dans le vocabulaire mort, un test passerait sans rien
prouver de ce que le pool rencontrera demain.

CODES DE SORTIE DE `check` (documentés aussi dans --help)
-----------------------------------------------------------
  0  READY                  1  erreur d'exécution (store malformé, git absent)
  2  réservé à argparse     10 NO_PLAN · 11 PLAN_SANS_VERDICT · 12 SHA_ABSENT
  13 WRITE_SET_ABSENT       14 STALE (write-set bougé OU sha introuvable)
  15 VERDICT_FAIL           16 tâche absente du board ou non `pending`

Un sha introuvable n'est JAMAIS un crash ni un exit 1 : c'est une péremption
comme une autre (le sha tamponnait un arbre qui n'existe plus), exit 14 avec
mention explicite sur stderr.

RÉSIDUEL — `moved_since` (documenté, NON corrigé)
---------------------------------------------------
`moved_since` compare deux COMMITS (`git diff --name-only <sha>..HEAD`). Une
modification NON COMMITÉE d'un fichier du write-set n'y est donc PAS vue : le
relevé SOUS-détecte la péremption et peut rendre READY sur un arbre de travail
déjà divergent. Corriger est HORS périmètre de T-00000383 — c'est une dette
NOMMÉE, pas un oubli. La voie de reprise de `/kickoff` la DIVULGUE à la porte
(« relevé READY — les modifications non commitées du write-set ne sont pas
vues »), pour qu'un READY vert ne se lise jamais comme une preuve d'arbre
propre.

Usage :
    python core-scripts/plan_pool.py status [--json] [--root .]
    python core-scripts/plan_pool.py check T-00000379 [--json] [--root .]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BOARD_REL = Path(".agents") / "state" / "board" / "TASKS.json"
SPECS_REL = Path(".agents") / "state" / "specs" / "SPECS.json"
# LES FORMES ENREGISTREMENT (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : dossiers du board, journal SPECS.
BOARD_DIR_REL = BOARD_REL.parent
BOARD_COLLECTIONS = ("tasks", "epics")
SPECS_JOURNAL_REL = SPECS_REL.with_name("SPECS.jsonl")
# RECOPIES (jamais importées) : `RECORD_FORMAT` et `_ID_ENREGISTREMENT` de `tasks_stockage.py`, l'en-tête du journal
# de `specs.py`.
RECORD_FORMAT = 1
_ID_ENREGISTREMENT = re.compile(r"\A[TSLE]-[0-9]{1,15}\Z", re.ASCII)
JOURNAL_FORMAT = 1
JOURNAL_HEADER = {"format": JOURNAL_FORMAT, "store": "specs"}

# Les deux grammaires du contrat — voir l'en-tête. Ancrées (`^`), jamais
# recherchées en sous-chaîne : un titre libre qui CONTIENT « GO » ne dit rien,
# et `NO_GO` en contient un.
#
# DEUX préfixes, en alternance ANCRÉE et CLOSE. Le canon est `Plan @ <sha> -
# <objet>`, celui qu'écrit `/planning` (`.agents/skills/planning/SKILL.md`).
# `Plan de reserve @ …` reste reconnu pour la COMPAT ADOPTANTS : fixtures du banc
# et journaux des dépôts qui ont vécu sous l'ancien nom — mesuré 0 titre de cette
# forme dans le SPECS.json d'ici, donc ce n'est PAS une non-régression du passé de
# ce dépôt. L'alternance est CLOSE : ni `Planning @ …`, ni un double espace.
# `reserve` SANS ACCENT, délibérément : c'est la chaîne EXACTE que la consigne dit
# de taper. Un accent dans la regex et pas dans la consigne (ou l'inverse) produit
# un SHA_ABSENT que personne ne relie à un é.
PLAN_TITLE_RE = re.compile(r"^Plan(?: de reserve)? @ (?P<sha>[0-9a-f]{4,40}) - (?P<objet>.+)$")

# La forme NOMMÉE quand un titre de plan est refusé (T-00000673) — une EXPLICATION,
# jamais une grammaire : `PLAN_TITLE_RE` ci-dessus reste le seul juge, et le plancher
# de corpus du banc (`plan_pool.test.sh`, taux de reconnaissance) ne bouge pas.
FORME_PLAN = "forme attendue `Plan @ <sha court> - <objet>` + --files"
# Le mot « paire » d'un titre de verdict hors grammaire — regex RECOPIÉE de
# `night_approve.PAIR_VERDICT_TITLE` (`plan_pool` n'importe rien de `.agents/bin`) ;
# la parité est épinglée par `test_night_approve.py` (lue en TEXTE, jamais chargée).
# Le pluriel `paires` n'est PAS lu (résidu nommé dans `night_approve`, 2 titres vivants).
PAIRE_RE = re.compile(r"\bpaire\b")


def _titre_affichable(t: str) -> str:
    """Un titre LIBRE (note, verdict) rendu imprimable AVANT d'être cité dans un détail :
    chaque caractère non imprimable — ESC `\\x1b`, CSI C1 `\\x9b`, saut de ligne — devient
    une espace, AVANT la troncature (S-00003335). Un titre de journal est tapé par
    n'importe quel agent ; `check` l'écrit sur un terminal. COPIE de
    `night_approve._titre_affichable` (`plan_pool` n'importe rien de `.agents/bin`)."""
    return "".join(c if c.isprintable() else " " for c in t)


# Le séparateur admet les DEUX formes mesurées dans notre journal : `: ` (27
# titres) et l'espace nu (155 titres). `[^:]{0,60}?` reste non-gourmand pour que
# le mot de verdict soit cherché AU PLUS TÔT après `plan-critic`.
VERDICT_TITLE_RE = re.compile(
    r"^plan-critic\b[^:]{0,60}?(?::\s*|\s+)"
    r"(?P<verdict>GO_AVEC_RESERVES|NO_GO|GO|PASS|CONCERNS|FAIL)\b"
)

# Les verdicts qui REFUSENT. `NO_GO` est le vivant, `FAIL` l'historique.
VERDICTS_REFUS = frozenset({"NO_GO", "FAIL"})

#: Les marqueurs que `/planning` pose sur un plan TANT QU'IL N'EST PAS FINI.
DRAFT_MARKERS = frozenset({"IN_PROGRESS", "CRITIC_REJECTED"})

_STATUS_ORNEMENTS = "*_# -\t"


def draft_marker(text: str) -> str:
    """Le marqueur de brouillon porté par un plan, ou la chaîne vide.

    LECTURE TOLÉRANTE, ET ELLE EST NÉCESSAIRE PLUTÔT QUE CONFORTABLE. La
    première rédaction faisait `line.startswith("STATUS:")` puis comparait la
    valeur à l'identique : mesuré le 2026-09-12, `STATUS : IN_PROGRESS` —
    l'espace avant les deux-points, c'est-à-dire la typographie française que ce
    dépôt emploie partout, et que `night_approve` accepte déjà par `^Tâches\\s*:`
    — sortait `READY`. Passaient aussi `**STATUS:**`, une indentation, une casse
    minuscule et un suffixe de révision. Un marqueur manqué ne se voit pas : il
    se lit « plan fini », et c'est un plan non jugé qui part en nuit autonome.

    TOUTE ligne `STATUS` est examinée, pas seulement la première : un plan
    amendé EMPILE ses statuts, et ne lire que le plus ancien reviendrait à juger
    une révision qui n'est plus la bonne.
    """
    for ligne in text.splitlines():
        nu = ligne.strip().lstrip(_STATUS_ORNEMENTS).strip()
        if not nu.upper().startswith("STATUS"):
            continue
        _, _, valeur = nu.partition(":")
        mots = valeur.strip().strip(_STATUS_ORNEMENTS).upper().split()
        if mots and mots[0] in DRAFT_MARKERS:
            return mots[0]
    return ""

# Borne d'affichage de `status` : une table qui déborde l'écran ne sera pas lue
# à 3 h du matin. La troncature est TOUJOURS dite, avec le total — une
# troncature silencieuse se lit comme une couverture complète.
STATUS_MAX_ROWS = 30
DETAIL_MAX_CHARS = 72

EXIT = {
    "READY": 0,
    "NO_PLAN": 10,
    "PLAN_SANS_VERDICT": 11,
    "SHA_ABSENT": 12,
    "WRITE_SET_ABSENT": 13,
    "STALE": 14,
    "VERDICT_FAIL": 15,
    "TASK_ABSENT": 16,
}


class PoolError(Exception):
    """Store malformé ou git indisponible : échec franc, exit 1, jamais de dégradé."""


@dataclass
class Verdict:
    """Le verdict d'UNE tâche — `code` est la clé d'EXIT, le reste explique."""

    task: str
    code: str
    sha: str = ""
    detail: str = ""
    moved: list[str] = field(default_factory=list)


def force_utf8_stdio() -> None:
    """Consoles Windows en cp1252 : le journal est UTF-8 par construction,
    stdio doit suivre (même discipline que specs.py)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", newline="\n")


def numeric_id(id_str: str) -> int:
    """Valeur NUMÉRIQUE d'un id ANCIEN — queue de 1 à 15 chiffres non précédée
    d'un chiffre, jamais la chaîne (un changement de padding ne doit ni réordonner
    ni fusionner). Étage `(0, n)` de `sort_key`, seul appelant."""
    match = re.search(r"(?<!\d)(\d{1,15})\Z", id_str or "")
    if not match:
        raise PoolError(f"id de journal malformé : {id_str!r}")
    return int(match.group(1))


# LA FORME `P-<ULID>` (T-00000726, forme A) — RECOPIE de `ULID_BODY` / `_ULID_ID` de
# `.agents/bin/tasks_stockage.py`, jamais importée (voir l'en-tête : ce script
# n'importe rien de `.agents/bin/`) : 26 symboles Crockford MAJUSCULES, ancrés.
ULID_BODY = "[0-9A-HJKMNP-TV-Z]{26}"
_ULID_ID = re.compile(r"\A[TSL]-(" + ULID_BODY + r")\Z")


def sort_key(id_str: str) -> tuple[int, int | str]:
    """Ordre du journal et du board, à DEUX ÉTAGES : `(0, n)` pour un ancien,
    `(1, ulid)` pour un `P-<ULID>`, après tout ancien et dans l'ordre de frappe ;
    tout autre id lève `PoolError`. PARITÉ avec `tasks.sort_key`, tenue par (31d)
    de `plan_pool.test.sh` sur CE domaine : ids de 1 à 15 chiffres et ULID T/S/L à
    queue lettre ou chiffre, rangés ; ids de 16 chiffres, levés des DEUX côtés."""
    ulid = _ULID_ID.match(id_str or "")
    return (1, ulid.group(1)) if ulid else (0, numeric_id(id_str))


def load_store(path: Path, required_key: str) -> dict[str, Any]:
    """Lit et VALIDE la forme minimale d'un store. Un JSON malformé lève — il
    ne se dégrade jamais en « store vide »."""
    if not path.exists():
        raise PoolError(f"{path} absent — le store n'existe pas sur cette racine")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PoolError(f"{path} n'est pas un JSON valide : {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get(required_key), list):
        raise PoolError(f"{path} : objet avec une liste « {required_key} » attendu")
    return data


def _est_id_enregistrement(rid: str) -> bool:
    """Un nom de fichier d'enregistrement : `P-<ULID>` ou `[TSLE]-<1 à 15 chiffres>` (parité tasks_stockage)."""
    return bool(_ULID_ID.match(rid) or _ID_ENREGISTREMENT.match(rid))


def _dossier_present(root: Path) -> bool:
    """La forme dossier du board est PRÉSENTE ssi un `<id d'enregistrement>.json` non pointé existe sous
    `board/tasks/` ou `board/epics/` — la définition de `tasks.store_form`. Un dossier en lien symbolique est refusé."""
    for collection in BOARD_COLLECTIONS:
        sous = root / BOARD_DIR_REL / collection
        if sous.is_symlink():
            raise PoolError(f"{sous} est un lien symbolique — refusé, jamais traversé")
        if sous.is_dir() and any(not p.name.startswith(".") and p.name.endswith(".json")
                                 and _est_id_enregistrement(p.name[: -len(".json")]) for p in sous.iterdir()):
            return True
    return False


def _taches_du_dossier(root: Path) -> list[dict[str, Any]]:
    """Les tâches VIVANTES de `board/tasks/`, rangées par `sort_key` : chaque nom non pointé est `<id>.json`, un
    fichier régulier, une enveloppe `{"format": 1, "id": <son nom>, "record", …}` ; `record: null` (une TOMBE) est
    ÉCARTÉ. Tout écart ⇒ `PoolError` nommant le fichier, jamais sauté."""
    sous = root / BOARD_DIR_REL / "tasks"
    taches: list[dict[str, Any]] = []
    for chemin in sorted(sous.iterdir()) if sous.is_dir() else ():
        if chemin.name.startswith("."):
            continue
        rid = chemin.name[: -len(".json")] if chemin.name.endswith(".json") else ""
        if not _est_id_enregistrement(rid) or chemin.is_symlink() or not chemin.is_file():
            raise PoolError(f"{chemin} : pas un fichier d'enregistrement <id>.json régulier — refusé, jamais sauté")
        try:
            enveloppe = json.loads(chemin.read_bytes().decode("utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            raise PoolError(f"{chemin} : enregistrement illisible ({exc})") from exc
        version = enveloppe.get("format") if isinstance(enveloppe, dict) else None
        if type(version) is not int or not 1 <= version <= RECORD_FORMAT:
            raise PoolError(f"{chemin} : enveloppe d'enregistrement sans format {RECORD_FORMAT} ({version!r})")
        if enveloppe.get("id") != rid:
            raise PoolError(f"{chemin} : porte l'id {enveloppe.get('id')!r}, pas {rid!r} que son nom annonce")
        record = enveloppe.get("record")
        if record is None:
            continue
        if not isinstance(record, dict) or record.get("id") != rid:
            raise PoolError(f"{chemin} : son record ne porte pas l'id {rid!r}")
        taches.append(record)
    return sorted(taches, key=lambda t: sort_key(t["id"]))


def lire_board_forme(root: Path) -> dict[str, Any]:
    """Le board dans SA forme : `{"tasks": [...]}` du monolithe (`load_store`) OU des enregistrements de
    `board/tasks/`. Les DEUX ⇒ `PoolError` nommant les deux chemins ; aucun ⇒ `PoolError` « absent »."""
    mono, dossier = root / BOARD_REL, _dossier_present(root)
    if dossier and mono.exists():
        raise PoolError(
            f"deux formes du board : {mono} ET {root / BOARD_DIR_REL / 'tasks'} — une vieille branche a ramené le "
            f"monolithe (ou une migration s'est interrompue) ; rien n'est lu. Remède : celui de `tasks.py`, qui refuse "
            f"aussi d'écrire et l'imprime (finir la migration, ou mettre le monolithe de côté)")
    if not dossier:
        return load_store(mono, "tasks")
    return {"tasks": _taches_du_dossier(root)}


def _ligne_journal(obj: dict[str, Any]) -> str:
    """La ligne canonique de `specs.journal_line` (clés triées, sans espace, UTF-8 brut), RECOPIÉE."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canon_journal(obj: dict[str, Any]) -> str:
    """`specs._canon`, RECOPIÉ : `text`/`files` mis par défaut — une ligne sans `text` égale sa forme chargée."""
    normal = dict(obj)
    normal.setdefault("text", "")
    normal.setdefault("files", [])
    return _ligne_journal(normal)


def lire_journal(chemin: Path) -> list[dict[str, Any]]:
    """Le journal `SPECS.jsonl` selon les règles de `specs._parse_journal`, RECOPIÉES : découpe sur `\\n` SEUL
    (jamais `splitlines` : U+2028 reste dans une valeur), lignes vides ignorées, PREMIÈRE ligne non vide = l'en-tête
    `{"format", "store": "specs"}`, en-tête répété identique ignoré, ligne tombe (`record`) refusée, même `id` et même
    contenu canonique = UNE entrée (l'union de fusion), même `id` et contenu DIFFÉRENT ⇒ refus nommant les deux
    lignes ; ligne non UTF-8, non JSON, non objet ou sans `id` ⇒ refus nommant la ligne. La validation de CHAMPS de
    `specs._validate_entries` n'est PAS reproduite (écart nommé ; `load_specs` garde ses contrôles)."""
    try:
        brut = chemin.read_bytes()
    except OSError as exc:
        raise PoolError(f"{chemin} : journal illisible ({exc})") from exc
    entrees: list[dict[str, Any]] = []
    lignes: list[int] = []
    gardees: dict[str, int] = {}
    entete = ""
    for numero, morceau in enumerate(brut.split(b"\n"), start=1):
        if not morceau.strip():
            continue
        ou = f"{chemin}:{numero}"
        try:
            obj = json.loads(morceau.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise PoolError(f"{ou} : pas de l'UTF-8 ({exc})") from exc
        except (ValueError, RecursionError) as exc:
            raise PoolError(f"{ou} : pas un JSON valide ({exc})") from exc
        if not isinstance(obj, dict):
            raise PoolError(f"{ou} : pas un objet JSON")
        if not entete:
            version = obj.get("format")
            if set(obj) != set(JOURNAL_HEADER) or obj.get("store") != "specs" or type(version) is not int \
                    or not 1 <= version <= JOURNAL_FORMAT:
                raise PoolError(f"{ou} : en-tête de journal absent, étranger ou d'un format inconnu — attendu "
                                f"{_ligne_journal(JOURNAL_HEADER)} en première ligne")
            entete = _ligne_journal(obj)
            continue
        if _ligne_journal(obj) == entete:
            continue
        if "record" in obj:
            raise PoolError(f"{ou} : ligne tombe/enveloppe (`record`) — un journal append-only n'a pas de canal "
                            f"de suppression")
        sid = obj.get("id")
        if not isinstance(sid, str) or not sid or not isinstance(obj.get("task", ""), str):
            raise PoolError(f"{ou} : entrée sans id (ou id/task non texte)")
        if sid in gardees:
            if _canon_journal(entrees[gardees[sid]]) != _canon_journal(obj):
                raise PoolError(f"{chemin} : l'entrée {sid} diffère entre les lignes {lignes[gardees[sid]]} et "
                                f"{numero} — journal append-only, décision pilote")
            continue
        gardees[sid] = len(entrees)
        entrees.append(obj)
        lignes.append(numero)
    if not entete:
        raise PoolError(f"{chemin} : aucun en-tête de journal — attendu {_ligne_journal(JOURNAL_HEADER)} d'abord")
    return entrees


def lire_specs_forme(root: Path) -> dict[str, Any]:
    """Le journal SPECS dans SA forme : `{"entries": [...]}` du journal `SPECS.jsonl` (`lire_journal`) OU du
    monolithe (`load_store`). Les DEUX ⇒ `PoolError` nommant les deux chemins et le remède ; aucun ⇒ « absent »."""
    journal, mono = root / SPECS_JOURNAL_REL, root / SPECS_REL
    if not journal.exists():
        return load_store(mono, "entries")
    if mono.exists():
        raise PoolError(
            f"deux formes du journal SPECS : {mono} ET {journal} — une vieille branche a ramené le monolithe ; rien "
            f"n'est lu. Remède : `python3 .agents/bin/specs.py migrate --apply` (replie le monolithe dans le journal)")
    return {"entries": lire_journal(journal)}


def load_board(root: Path) -> list[dict[str, Any]]:
    tasks = lire_board_forme(root)["tasks"]
    for i, t in enumerate(tasks):
        if not isinstance(t, dict) or not t.get("id") or not t.get("state"):
            raise PoolError(f"{root / BOARD_REL} : tâche #{i} sans id ou sans state")
    return tasks


def load_specs(root: Path) -> list[dict[str, Any]]:
    entries = lire_specs_forme(root)["entries"]
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or not all(e.get(f) for f in ("id", "task", "kind", "title")):
            raise PoolError(f"{root / SPECS_REL} : entrée #{i} incomplète (id/task/kind/title)")
        if not isinstance(e.get("files", []), list):
            raise PoolError(f"{root / SPECS_REL} : entrée {e['id']} a un files non-liste")
    return sorted(entries, key=lambda e: sort_key(e["id"]))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """git, ou rien : un git absent du PATH est une erreur d'EXÉCUTION (exit 1),
    pas un verdict — il faut distinguer « plan périmé » de « outil cassé »."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        raise PoolError("git introuvable sur le PATH") from exc


def sha_resolvable(root: Path, sha: str) -> bool:
    return _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def moved_since(root: Path, sha: str) -> list[str]:
    """RÉSIDUEL ASSUMÉ (voir l'en-tête) : ce diff est COMMIT-à-COMMIT, donc une
    modification NON COMMITÉE d'un fichier du write-set n'est PAS vue et le
    relevé SOUS-détecte la péremption. Corriger est hors périmètre de
    T-00000383 (dette nommée) ; la reprise `/kickoff` la divulgue à la porte."""
    proc = _git(root, "diff", "--name-only", f"{sha}..HEAD")
    if proc.returncode != 0:
        raise PoolError(f"git diff {sha}..HEAD a échoué : {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def classify(root: Path, task: dict[str, Any], entries: list[dict[str, Any]]) -> Verdict:
    """Le contrat de l'en-tête, dans l'ordre — le PREMIER écart prononcé clôt le
    verdict. Aucune branche ne suppose ce qu'une autre n'a pas établi."""
    tid = task["id"]
    mine = [e for e in entries if e["task"] == tid]
    plans = [e for e in mine if e["kind"] == "plan"]
    if not plans:
        return Verdict(tid, "NO_PLAN", detail="aucun checkpoint kind=plan")

    plan = plans[-1]
    # WRITE_SET_ABSENT est prononcé AVANT SHA_ABSENT : un write-set vide est un
    # défaut structurel, mesurable SANS le titre. Un titre canonique avec files
    # vide tombe dans le même cas.
    m = PLAN_TITLE_RE.match(plan["title"])
    sha = m.group("sha") if m else ""

    write_set = [f for f in plan.get("files", []) if f]
    if not write_set:
        # Un titre AUSSI non canonique est dit ici : WRITE_SET_ABSENT parle AVANT
        # SHA_ABSENT, et 4 des 11 notes non canoniques en attente (M3, T-00000673)
        # n'atteindraient jamais le message SHA_ABSENT.
        return Verdict(tid, "WRITE_SET_ABSENT", sha=sha,
                       detail=f"files vide sur {plan['id']} — write-set non clos"
                              + ("" if m else f" ; titre aussi non canonique : {FORME_PLAN}"))

    if not m:
        # La note NON CANONIQUE est `plans[-1]` : elle MASQUE tout checkpoint
        # antérieur de la tâche, canonique ou non — d'où la S-id nommée.
        return Verdict(tid, "SHA_ABSENT",
                       detail=f"titre du plan non canonique : {_titre_affichable(plan['title'])[:DETAIL_MAX_CHARS]} "
                              f"({plan['id']} MASQUE tout checkpoint anterieur ; {FORME_PLAN})"
                              + (" ; une approbation s'ecrit --kind decision « plan approuvé »"
                                 if plan["title"].lstrip().lower().startswith("plan approuv") else ""))

    # Le chemin unitaire de `/planning` existe dès la première sortie du
    # planner. Sa présence est optionnelle pour la compatibilité des anciens
    # checkpoints, mais ses marqueurs intermédiaires sont un refus explicite :
    # même un vieux GO postérieur ne transforme jamais un draft en READY.
    canonical_path = root / "docs" / "tasks" / f"{tid}-plan.md"
    if canonical_path.exists():
        try:
            canonical_text = canonical_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return Verdict(tid, "STALE", sha=sha,
                           detail=f"plan illisible ({canonical_path}): {exc}")
        if (marqueur := draft_marker(canonical_text)):
            return Verdict(tid, "PLAN_SANS_VERDICT", sha=sha,
                           detail=f"brouillon {marqueur} — verdict final absent")

    posterior = [e for e in mine
                 if e["kind"] == "verdict" and sort_key(e["id"]) > sort_key(plan["id"])]
    if not posterior:
        return Verdict(tid, "PLAN_SANS_VERDICT", sha=sha,
                       detail=f"aucun verdict postérieur à {plan['id']}")
    verdict = posterior[-1]
    vm = VERDICT_TITLE_RE.match(verdict["title"])
    if not vm:
        return Verdict(tid, "PLAN_SANS_VERDICT", sha=sha,
                       detail=f"verdict {verdict['id']} hors grammaire : "
                              f"{_titre_affichable(verdict['title'])[:DETAIL_MAX_CHARS]}"
                              # Le suffixe est une ACCUSATION : il mord la paire et
                              # rien d'autre (un `security-code-review …` n'est pas une paire).
                              + (" — verdict de PAIRE : cette voie lit un titre « plan-critic <VERDICT> »"
                                 if PAIRE_RE.search(verdict["title"]) else ""))
    if vm.group("verdict") in VERDICTS_REFUS:
        return Verdict(tid, "VERDICT_FAIL", sha=sha,
                       detail=f"{verdict['id']} : {vm.group('verdict')} — replanifier, jamais exécuter")

    # Le pont progressif persiste l'empreinte dans le verdict. Valider ce champ
    # quand `plan=` est présent ferme la fenêtre « fichier amendé, vieux GO
    # encore postérieur ». L'absence totale de `plan=` reste le bras de
    # compatibilité des journaux antérieurs au contrat progressif.
    verdict_text = verdict.get("text", "")
    # LE MOTIF CAPTURE N'IMPORTE QUEL CHEMIN, ET C'EST UNE CORRECTION.
    # Il exigeait `docs/tasks/…\.md` : un `plan=` écrit autrement ne matchait
    # donc PAS, et le code retombait EN SILENCE dans le bras de compatibilité,
    # sans contrôle d'empreinte ni trace. Mesuré le 2026-09-12 — cinq formes sur
    # six passaient sans aucun contrôle : `plan=plans/ailleurs.md`,
    # `plan=/etc/passwd`, `plan=../../outside.md`, une extension en capitales,
    # et une virgule collée. La condition 6 se contournait donc en écrivant le
    # chemin autrement, ce qui est l'exact contraire de ce qu'un verrou fait.
    # Corollaire : `relative_plan.is_absolute()` était du CODE MORT, puisque le
    # motif imposait un préfixe relatif ; il redevient atteignable ici.
    #
    # ON REFUSE, ON N'ADMET PLUS. Un `plan=` cité est désormais contrôlé ou
    # refusé — jamais ignoré. La doc du module promet « quand le verdict cite
    # `plan=<chemin>` », sans restriction de préfixe : le code la rejoint.
    path_match = re.search(r"(?:^|\s)plan=(?P<plan>\S+)(?=\s|$)", verdict_text)
    if path_match:
        # La ponctuation collée en fin de citation est une faute de frappe, pas
        # un chemin : on la retire avant de juger, plutôt que de refuser un plan
        # réel pour une virgule.
        relative_plan = Path(path_match.group("plan").rstrip(".,;:)»\"'"))
        if (relative_plan.is_absolute()
                or ".." in relative_plan.parts
                or relative_plan.suffix.lower() != ".md"):
            return Verdict(tid, "STALE", sha=sha,
                           detail=f"chemin de plan non sûr dans {verdict['id']} : "
                                  f"{str(relative_plan)[:DETAIL_MAX_CHARS]}")
        try:
            resolved_root = root.resolve()
            resolved_plan = (root / relative_plan).resolve(strict=True)
            resolved_plan.relative_to(resolved_root)
            plan_bytes = resolved_plan.read_bytes()
        except (OSError, ValueError) as exc:
            return Verdict(tid, "STALE", sha=sha,
                           detail=f"plan cité introuvable ou hors racine : {exc}")
        # LE MARQUEUR SE LIT SUR LE PLAN RÉELLEMENT CITÉ, pas seulement sur le
        # chemin canonique deviné plus haut. Les deux peuvent désigner des
        # fichiers différents : une tâche enrôlée dans un plan de LOT
        # (`docs/tasks/LOT-9-plan.md`) n'a pas de `T-<id>-plan.md`, donc le
        # contrôle canonique était SAUTÉ et un brouillon de lot ressortait READY.
        # Mesuré le 2026-09-12.
        if (marqueur := draft_marker(plan_bytes.decode("utf-8", "replace"))):
            return Verdict(tid, "PLAN_SANS_VERDICT", sha=sha,
                           detail=f"brouillon {marqueur} dans {relative_plan} — "
                                  "verdict final absent")
        recorded_hashes = {
            found.lower()
            for found in re.findall(
                r"(?<![A-Za-z0-9])sha256=([0-9a-fA-F]{64})(?![0-9a-fA-F])",
                verdict_text,
            )
        }
        # DEUX CAS QUI NE SE TRAITENT PAS PAREIL, et les confondre était une
        # RÉGRESSION de compatibilité ascendante. Le bras de compatibilité
        # n'exempte que l'absence de `plan=` ; or `len(...) != 1` frappait aussi
        # un checkpoint qui cite `plan=` SANS empreinte, forme parfaitement
        # légitime avant le contrat progressif. Mesuré sur les données réelles :
        # 90 verdicts citent `plan=`, et S-00001101 (T-00000459) écrit « sha256
        # du plan » en PROSE, donc zéro empreinte — il passait de READY à STALE
        # sans qu'aucune édition n'ait eu lieu. Une empreinte AMBIGUË, elle,
        # reste un refus : deux valeurs contradictoires ne se départagent pas.
        if len(recorded_hashes) > 1:
            return Verdict(tid, "STALE", sha=sha,
                           detail=f"empreintes sha256 contradictoires dans {verdict['id']}")
        if recorded_hashes:
            recorded_hash = recorded_hashes.pop()
            actual_hash = hashlib.sha256(plan_bytes).hexdigest()
            if recorded_hash != actual_hash:
                return Verdict(tid, "STALE", sha=sha,
                               detail=f"plan modifié depuis {verdict['id']} "
                                      f"({recorded_hash[:12]}… != {actual_hash[:12]}…)")

    if not sha_resolvable(root, sha):
        return Verdict(tid, "STALE", sha=sha,
                       detail="sha introuvable (rebase/amend/shallow) — le plan tamponne un arbre disparu")
    moved = sorted(set(moved_since(root, sha)) & set(write_set))
    if moved:
        shown = ", ".join(moved[:3]) + (f" (+{len(moved) - 3})" if len(moved) > 3 else "")
        return Verdict(tid, "STALE", sha=sha, moved=moved,
                       detail=f"write-set touché depuis {sha} : {shown}")
    return Verdict(tid, "READY", sha=sha,
                   detail=f"plan {plan['id']} + verdict {verdict['id']} "
                          f"({vm.group('verdict')}), write-set intact")


def verdicts_for_pending(root: Path) -> list[Verdict]:
    board = load_board(root)
    entries = load_specs(root)
    pending = sorted(
        (t for t in board if t["state"] == "pending"),
        key=lambda t: sort_key(t["id"]),
    )
    return [classify(root, t, entries) for t in pending]


def cmd_status(root: Path, as_json: bool) -> int:
    verdicts = verdicts_for_pending(root)
    if as_json:
        print(json.dumps([vars(v) for v in verdicts], indent=2, ensure_ascii=False))
        return 0
    if not verdicts:
        print("(aucune tâche pending au board)")
        return 0
    ready = sum(1 for v in verdicts if v.code == "READY")
    print(f"{'TÂCHE':<12} {'VERDICT':<18} {'SHA':<10} DÉTAIL")
    for v in verdicts[:STATUS_MAX_ROWS]:
        print(f"{v.task:<12} {v.code:<18} {v.sha or '—':<10} {v.detail}")
    if len(verdicts) > STATUS_MAX_ROWS:
        print(f"… tronqué : {STATUS_MAX_ROWS} lignes affichées sur {len(verdicts)} tâches pending"
              f" — --json pour la totalité")
    # Le relevé dit ce qu'il EST, à chaque appel : sans cette ligne un READY se
    # lit comme un feu vert de nuit, ce qu'il n'est pas (voir l'en-tête).
    #
    # `NON-AUTORITATIF` est en ASCII et en un seul morceau DÉLIBÉRÉMENT : c'est
    # le marqueur sur lequel le banc asserte, et un motif accentué se compare mal
    # sous une console Windows en cp1252. Le reste de la phrase reste en français
    # accentué, pour le lecteur.
    print(f"\n{ready} READY sur {len(verdicts)} pending. RELEVE AMONT, NON-AUTORITATIF : il ne "
          f"décide pas de l'éligibilité /night, qui recalcule ses propres conditions elle-même.")
    return 0


def cmd_check(root: Path, task_id: str, as_json: bool) -> int:
    board = load_board(root)
    entries = load_specs(root)
    task = next((t for t in board if t["id"] == task_id), None)
    if task is None:
        v = Verdict(task_id, "TASK_ABSENT", detail="absente du board")
    elif task["state"] != "pending":
        v = Verdict(task_id, "TASK_ABSENT", detail=f"state={task['state']} — seul pending est consommable")
    else:
        v = classify(root, task, entries)
    if as_json:
        print(json.dumps(vars(v), indent=2, ensure_ascii=False))
    else:
        print(f"{v.task} {v.code}" + (f" @ {v.sha}" if v.sha else "") + (f" — {v.detail}" if v.detail else ""))
    # Le sha introuvable est dit sur stderr EN PLUS du verdict : un consommateur
    # machine lit le code, un humain doit pouvoir distinguer la péremption par
    # rebase de la péremption par fichier bougé sans relancer quoi que ce soit.
    if v.code == "STALE" and "sha introuvable" in v.detail:
        print(f"plan_pool: {v.task} STALE — sha {v.sha} introuvable dans ce dépôt", file=sys.stderr)
    if v.code == "READY":
        jalon_chrono(root, task_id)
    return EXIT[v.code]


TASK_CHRONO = Path(__file__).resolve().parents[1] / ".agents" / "bin" / "task_chrono.py"


def charger_task_chrono(chemin: Path = TASK_CHRONO) -> Any:
    """Le frère `task_chrono.py`, chargé PAR CHEMIN (jamais un import de `.agents/bin/`) ; absent ⇒ OSError."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_plan_pool_task_chrono", chemin)
    if spec is None or spec.loader is None or not chemin.is_file():
        raise FileNotFoundError(f"frère {chemin} absent")
    tc = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = tc
    try:
        spec.loader.exec_module(tc)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return tc


def jalon_chrono(root: Path, task_id: str, charger: Any = charger_task_chrono) -> None:
    """LE CHRONO DU TOUR (T-01M5VZF47T9RT1YM9KC67HCQPP) : un `check` READY joue « plan-pret » de
    `task_chrono.jalon_de_planification` — ferme `planification`, ouvre `attente-pilote`, idempotent ; un
    lot n'écrit rien (le `check` READY de son maître suffit). SEULE exception à « aucun import de
    `.agents/bin/` » : le frère est chargé PAR CHEMIN, après le verdict, et son absence ou sa panne ne
    devient qu'un avis sur STDERR (`CHRONO: avis`) — stdout et rc de `check` inchangés, la survie de ce
    script n'en dépend pas. Une racine jetable (`AGENTS_EVENTS_DIR`, dossier temporaire) n'écrit rien."""
    try:
        tc = charger()
        base = tc.racine_de_jalon(root)
        if base is None:
            return
        avis = tc.jalon_de_planification(base, {"tasks": load_board(base)}, task_id, "plan-pret")
    except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne change jamais le verdict
        avis = [f"CHRONO: avis {task_id} — attente-pilote non relevée ({type(exc).__name__}: {exc})"]
    for ligne in avis:
        print(ligne, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Freshness reading of the pool of plans prepared by /planning (read only on board and "
                    "SPECS; a READY `check` records the local chrono milestone, advisory). "
                    "NOT AUTHORITATIVE on /night eligibility - see the file header.",
        epilog="`check` exit codes: 0 READY - 1 runtime error - 2 usage - "
               "10 NO_PLAN - 11 PLAN_SANS_VERDICT - 12 SHA_ABSENT - 13 WRITE_SET_ABSENT - "
               "14 STALE - 15 VERDICT_FAIL - 16 task absent or not pending",
    )
    ap.add_argument("--root", default=".", help="repository root (default: .) - used by the tests")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="bounded table of the pending tasks")
    p_status.add_argument("--json", action="store_true", help="full JSON, not truncated")

    p_check = sub.add_parser("check", help="machine verdict for ONE task")
    p_check.add_argument("task", help="task id, e.g. T-00000379")
    p_check.add_argument("--json", action="store_true", help="full JSON")

    args = ap.parse_args(argv)
    force_utf8_stdio()
    root = Path(os.fspath(args.root))
    try:
        if args.cmd == "status":
            return cmd_status(root, args.json)
        return cmd_check(root, args.task, args.json)
    except PoolError as exc:
        print(f"plan_pool: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
