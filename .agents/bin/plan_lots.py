#!/usr/bin/env python3
"""LES LOTS D'UN PLAN — la grammaire de la fournée (STDLIB SEULE + `plan_cible`, module frère).

Un plan qui se découpe en lots parallèles l'ÉCRIT, en lignes fermées, HORS bloc de
code, en tête de ligne (seule la puce `- ` est tolérée) :

    LOT: <clé> | <dev-mono|dev-multi|frontend-fidelity|terraform-deployer> | <libellé> | <chemin exact>, …
    INTÉGRATION: <chemin>, … | aucune      (UNE ligne dès qu'un LOT existe)
    LOTS: aucun [| <pourquoi>]             (fournée dégénérée : le parent seul)

La clé suit `[A-Z][A-Z0-9]{0,3}` ; le libellé fait 1 à 80 caractères, sans `|`.
L'INTÉGRATION est écrite par l'orchestrateur APRÈS la fusion des lots : elle n'entre
dans AUCUN write-set déclaré, mais elle ne doit recouvrir aucun lot. Un plan sans
aucune des trois formes est une fournée dégénérée, ANNONCÉE comme telle.

REFUS, TOUS LISTÉS, RIEN D'ÉCRIT (`Decoupe.refus`) : un seul lot ; une clé en
double ; une ligne PROCHE d'un mot-clé (`LOT :`, autre puce, gras, citation, NFD —
même forme que les arêtes de `plan_depends.py`) ; `LOTS: aucun` à côté d'un LOT ;
un chemin à `*` ou à barre finale ; un recouvrement lot/lot ou lot/intégration (le
prédicat de `parallel`, reçu en ARGUMENT) ; un lockfile ou un manifeste dans un lot
(liste FERMÉE et BORNÉE, `MANIFESTES`) ; `.agents/state/` n'importe où (le code
seul l'écrit) ; un roster orphelin (`<hôte>/agents/<nom>.*` dans un lot SANS
`src/cadre/data/roster/<nom>.json` — ou `.agents/vendor/cadre/data/roster/<nom>.json` —
alors que ce roster existe sur disque).
BORNE, DITE : un fichier partagé hors de ces listes n'est vu que par plan-critic.

*** ISOLATION. *** Ce module ne prend aucun verrou, n'écrit rien et n'importe
JAMAIS `tasks` au chargement : le verbe `tasks.py fournee` lui passe le prédicat de
recouvrement et l'admission des chemins en ARGUMENTS. Seule la commande `check`,
lancée hors du board, charge la façade `tasks` PAR CHEMIN (via `plan_cible`) pour
lire ces deux prédicats et la liste de garde — jamais une seconde copie.

`check --plan <chemin|-> [--parent <T>]` : LECTURE SEULE, rc 0 (grammaire tenue) ou
1 (refus) ; rc 2 pour une erreur d'usage ou un plan illisible. Il prédit la route
de chaque lot — planifiée (un chemin de garde), directe prédite (C1 et C2 seuls :
titre, stage et motif ne se lisent qu'au board), ou « À REDÉCOUPER » pour un lot
sans garde au-delà du seuil de la voie directe. Le planificateur et le critique de
plan l'appellent ; ils n'appellent jamais `tasks.py`.

LE PLAFOND DE LIGNES (décision pilote S-01M52Y43BA, mesuré : 80 lignes en médiane pour
un gabarit de 45) : `check` SEUL refuse un plan de plus de `PLAFOND_LIGNES_PLAN` lignes
NON VIDES (une ligne blanche ne compte pas) et dit où déporter le reste — l'annexe
`docs/tasks/<T>-annexe.md`, lue à la demande, que `check` ne lit jamais. `lire()` ne
juge pas la longueur : la fournée et le plafond du critique ne refusent jamais un plan
approuvé long.

LE MAÎTRE CONSOLIDÉ (T-01M54GE4K9EZRRQFD9TAVNWYKM, plan par lot) : quand chaque lot a reçu
son planner et son plan-critic, le maître porte UNE ligne par lot,

    PLAN-LOT: <clé> | docs/tasks/<T>-lot-<clé>-plan.md | sha256=<64 hex>

STRICTE — en tête de ligne, SANS puce, hors bloc de code ; `PLAN-LOT :`, `- PLAN-LOT:`,
`**PLAN-LOT:**` sont des formes PROCHES, refusées et nommées. Lue par `rapport_check` SEUL :
ni `lire()` ni `_PROCHE` ne la voient, la fournée et le plafond lisent le maître comme avant.
Dès UNE ligne écrite, chaque `LOT:` en porte une, une seule, et chaque clé est celle d'un
`LOT:` ; le plan de lot est un chemin exact PRÉSENT sous la racine, d'empreinte ÉGALE, qui
ENRÔLE le parent, porte `LOTS: aucun | lot <clé>` et n'est plus un brouillon (statut lu
TOLÉRANT, copie de `plan_pool.draft_marker`). BORNES, DITES : aucune ligne = maître non
consolidé, rien de vérifié (la sortie le dit) ; sans `--parent`, l'enrôlement n'est pas jugé
(dit) ; `check` prouve la forme et l'empreinte, jamais qu'un plan de lot reste dans les
chemins de son `LOT:` — c'est le plan-critic du lot qui le juge.

UN LOT `dev-mono` = UN CHEMIN (décision pilote S-01M54WQE1K4VQKJ9STTJ7A1DQ2) : `check` SEUL
refuse un lot `dev-mono` qui déclare plus d'un chemin, sauf la paire « source + son test
colocalisé » (`est_test_colocalise`, liste FERMÉE : même dossier, `test_<nom>.py` pour une
source `.py`, `<nom>_test.<ext>`, `<nom>.test.<ext>`, `<nom>.spec.<ext>`, casse exacte) ; tout
autre lot va à `dev-multi`. BORNE, DITE : toute AUTRE convention de nommage ou d'emplacement
— Java/Kotlin (`src/test/java/…/FooTest.java`), .NET (`Foo.Tests/FooTests.cs`), Vue/Jest
(`__tests__/Foo.spec.ts`), Go d'un autre paquet — n'est PAS une exception : le lot va à
`dev-multi` (prudent par choix : un faux refus coûte un re-routage). `lire()` ne juge pas ce
routage : la fournée et le plafond du critique ne refusent jamais un plan approuvé historique.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import posixpath
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_BIN = str(Path(__file__).resolve().parent)
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)
import plan_cible  # noqa: E402 — frère stdlib ; JAMAIS `tasks` au chargement

# ---------------------------------------------------------------------------
# GRAMMAIRE. Regex ANCRÉES et BORNÉES ; le corps est découpé en Python.
# ---------------------------------------------------------------------------
CLE_RE = re.compile(r"[A-Z][A-Z0-9]{0,3}")
#: T-01M52X1W3WPKCWX1DC36NMKJB6 : `terraform-deployer` est le slot dev d'une tâche IaC
#: (décision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG, Q2 (b)), comme `frontend-fidelity` l'est
#: d'une tâche d'écran.
DEVS = ("dev-mono", "dev-multi", "frontend-fidelity", "terraform-deployer")
LIBELLE_MAX = 80
_LOT = re.compile(r"^(?:- )?LOT:(.*)$")
_INTEGRATION = re.compile(r"^(?:- )?INT[EÉ]GRATION:(.*)$")
_LOTS = re.compile(r"^(?:- )?LOTS:(.*)$")
# Le mot-clé PROCHE, lu après un décapage linéaire (forme F5 de `plan_depends`) :
# MAJUSCULES seules, `lot :` en minuscules reste de la prose.
_PROCHE = re.compile(r"(?:LOTS?|INT[EÉ]GRATION)[ \t]*:")
_PUCE = re.compile(r"(?:[-*+]|\d{1,3}[.)])[ \t]")

#: Les lockfiles et manifestes de dépendances, par NOM DE FICHIER — liste FERMÉE et
#: BORNÉE : un manifeste d'un autre écosystème n'y est pas, plan-critic le voit.
MANIFESTES = (
    "uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml",
    "yarn.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock",
    "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml",
)
#: `build.gradle*` : `build.gradle`, `build.gradle.kts`.
MANIFESTE_PREFIXE = "build.gradle"
ETAT_PREFIXE = ".agents/state/"
#: Lignes NON VIDES qu'un plan ne dépasse pas (décision pilote S-01M52Y43BA) — le gabarit
#: des défs `planner` ; `check` seul le fait respecter, et le dépassement va à l'annexe.
PLAFOND_LIGNES_PLAN = 45
ANNEXE = "docs/tasks/<T>-annexe.md"
#: Une déf d'agent sur l'un des cinq hôtes, et le roster qui la double.
_DEF_HOTE = re.compile(r"^\.(?:claude|codex|gemini|github|kimi-code)/agents/([A-Za-z0-9_-]+?)(?:\.agent)?\.(?:md|toml)$")
#: Les DEUX emplacements du roster, en union STATIQUE (T-01M5BXTGX5YN8XEXTG1PP7A5ZX) : l'ancien
#: et `.agents/vendor/cadre` ; chacun qui EXISTE est exigé dans le lot, jamais par le résolveur.
ROSTERS = ("src/cadre/data/roster/{}.json", ".agents/vendor/cadre/data/roster/{}.json")


@dataclass
class Lot:
    cle: str
    dev: str
    libelle: str
    chemins: list[str]
    ligne: str


@dataclass
class Decoupe:
    """Ce que le plan déclare. `forme` : au moins une des trois formes est écrite."""
    lots: list[Lot] = field(default_factory=list)
    integration: list[str] = field(default_factory=list)
    integration_ecrite: bool = False
    aucun: str | None = None
    forme: bool = False
    refus: list[str] = field(default_factory=list)

    @property
    def degeneree(self) -> bool:
        """Le parent seul : `LOTS: aucun`, ou aucune forme (annoncée)."""
        return not self.lots


def _proche(ligne: str) -> bool:
    """`LOT :`, `* LOT:`, puce indentée, `**LOT:**`, `>`, NFD — voulue, non lue par la
    forme stricte, donc NOMMÉE (même décapage que `plan_depends._proche_du_mot_cle`)."""
    s = unicodedata.normalize("NFC", ligne).lstrip(" \t>")
    puce = _PUCE.match(s)
    if puce:
        s = s[puce.end():].lstrip(" \t")
    return bool(_PROCHE.match(s.lstrip("*_").lstrip(" \t")))


def _canon(chemin: str) -> str:
    """Forme de COMPARAISON textuelle (barres obliques, casse repliée) — pour les
    listes fermées de ce module seulement ; le recouvrement passe par le prédicat reçu."""
    return chemin.replace("\\", "/").casefold()


def est_manifeste(chemin: str) -> bool:
    nom = chemin.replace("\\", "/").rsplit("/", 1)[-1]
    return nom in MANIFESTES or nom.startswith(MANIFESTE_PREFIXE)


#: La décision pilote qui borne un lot `dev-mono` à UN chemin (+ son test colocalisé).
DECISION_DEV_MONO = "S-01M54WQE1K4VQKJ9STTJ7A1DQ2"


def est_test_colocalise(source: str, test: str) -> bool:
    """`test` est-il LE test colocalisé de `source` ? Liste FERMÉE, casse exacte, chemins
    normalisés en `/` et en NFC (un nom accentué NFD, celui que rend macOS, égale sa forme
    NFC) : même dossier ; `source` porte une extension `<ext>` et `<nom>` est
    son nom sans `.<ext>` ; `test` s'appelle `test_<nom>.py` (si `<ext>` = `py`),
    `<nom>_test.<ext>`, `<nom>.test.<ext>` ou `<nom>.spec.<ext>`. Toute autre convention
    (Java `FooTest.java`, .NET `Foo.Tests/`, `__tests__/`) rend `False` — borne du module."""
    s, t = (unicodedata.normalize("NFC", p.replace("\\", "/")) for p in (source, test))
    if posixpath.dirname(s) != posixpath.dirname(t):
        return False
    nom, point, ext = posixpath.basename(s).rpartition(".")
    if not point or not nom or not ext:
        return False
    formes = {f"{nom}_test.{ext}", f"{nom}.test.{ext}", f"{nom}.spec.{ext}"}
    if ext == "py":
        formes.add(f"test_{nom}.{ext}")
    return posixpath.basename(t) in formes


def refus_dev_mono(lot: Lot) -> str | None:
    """Le refus d'un lot `dev-mono` de plusieurs chemins, ou `None` : un autre dev, un seul
    chemin, ou deux chemins dont l'un est le test colocalisé de l'autre (dans un sens ou
    dans l'autre). `check` SEUL l'appelle — jamais `lire()` (plans approuvés historiques)."""
    if lot.dev != "dev-mono" or len(lot.chemins) <= 1:
        return None
    if len(lot.chemins) == 2:
        a, b = lot.chemins
        if est_test_colocalise(a, b) or est_test_colocalise(b, a):
            return None
    return (f"lot {lot.cle} : dev-mono déclare {len(lot.chemins)} chemins — route-le vers dev-multi "
            f"({DECISION_DEV_MONO})")


def _refus_chemin(chemin: str, ou: str, admis: Callable[[str], str | None] | None) -> list[str]:
    """Les refus d'UN chemin déclaré (`ou` : `lot <clé>` ou `INTÉGRATION`)."""
    refus: list[str] = []
    brut = chemin.replace("\\", "/")
    if "*" in brut or brut.endswith("/"):
        refus.append(f"{ou} : `{chemin}` n'est pas un chemin exact (glob ou répertoire)")
    elif admis is not None and admis(chemin) is not None:
        refus.append(f"{ou} : `{chemin}` est inadmissible au write-set — {admis(chemin)}")
    if _canon(brut).startswith(ETAT_PREFIXE) or _canon(brut) == ETAT_PREFIXE.rstrip("/"):
        refus.append(f"{ou} : `{chemin}` est sous `{ETAT_PREFIXE}` — le code seul écrit l'état, "
                     "jamais un lot ni l'intégration")
    return refus


def _liste_chemins(corps: str) -> list[str]:
    vus: list[str] = []
    for brut in corps.split(","):
        c = brut.strip()
        if c and c not in vus:
            vus.append(c)
    return vus


def lire(
    texte: str,
    *,
    racine: str | Path | None = None,
    chevauche: Callable[[list[str], list[str]], tuple[str, str] | None] | None = None,
    admis: Callable[[str], str | None] | None = None,
) -> Decoupe:
    """La découpe du plan, et TOUS ses refus. `chevauche(gauche, droite)` rend la
    première paire qui se recouvre ou `None` (le prédicat de `parallel`) ; absent,
    le recouvrement n'est pas jugé et le refus le DIT. `admis(chemin)` rend la cause
    d'un chemin inadmissible au write-set, ou `None`. `racine` sert au roster
    orphelin (existence sur disque) ; absente, ce contrôle le DIT."""
    d = Decoupe()
    lignes_lot: list[str] = []
    for ligne in plan_cible.lignes_hors_code(texte):
        ligne = ligne.rstrip("\r")
        m_lot, m_int, m_lots = _LOT.match(ligne), _INTEGRATION.match(ligne), _LOTS.match(ligne)
        if not (m_lot or m_int or m_lots):
            if _proche(ligne):
                d.refus.append(f"ligne proche d'un mot-clé {ligne.strip()!r} — ni lue ni ignorée : écris "
                               "`LOT:`, `INTÉGRATION:` ou `LOTS:` en tête de ligne (seule la puce `- ` est tolérée)")
            continue
        d.forme = True
        if m_lots:
            corps = m_lots.group(1).strip()
            tete, _sep, raison = corps.partition("|")
            if tete.strip() != "aucun" or (_sep and not raison.strip()):
                d.refus.append(f"ligne malformée {ligne.strip()!r} — forme attendue `LOTS: aucun` "
                               "ou `LOTS: aucun | <pourquoi>`")
            elif d.aucun is not None:
                d.refus.append(f"`LOTS:` écrit deux fois — {ligne.strip()!r}")
            else:
                d.aucun = raison.strip()
            continue
        if m_int:
            corps = m_int.group(1).strip()
            if d.integration_ecrite:
                d.refus.append(f"`INTÉGRATION:` écrite deux fois — {ligne.strip()!r}")
                continue
            d.integration_ecrite = True
            if corps == "aucune":
                continue
            chemins = _liste_chemins(corps)
            if not chemins or "|" in corps:
                d.refus.append(f"ligne malformée {ligne.strip()!r} — forme attendue "
                               "`INTÉGRATION: <chemin>, …` ou `INTÉGRATION: aucune`")
                continue
            for c in chemins:
                d.refus += _refus_chemin(c, "INTÉGRATION", admis)
            d.integration = chemins
            continue
        champs = [c.strip() for c in m_lot.group(1).split("|")]
        forme = f"`LOT: <clé> | <{'|'.join(DEVS)}> | <libellé> | <chemin exact>, …`"
        if len(champs) != 4:
            d.refus.append(f"ligne malformée {ligne.strip()!r} — {len(champs)} champ(s) séparés par `|`, "
                           f"4 attendus : {forme} (le libellé ne porte pas de `|`)")
            continue
        cle, dev, libelle, corps = champs
        fautes = []
        if not CLE_RE.fullmatch(cle):
            fautes.append(f"clé {cle!r} hors de `[A-Z][A-Z0-9]{{0,3}}`")
        if dev not in DEVS:
            fautes.append(f"dev {dev!r} hors de {', '.join(DEVS)}")
        if not libelle or len(libelle) > LIBELLE_MAX:
            fautes.append(f"libellé de {len(libelle)} caractère(s), 1 à {LIBELLE_MAX} attendus")
        chemins = _liste_chemins(corps)
        if not chemins:
            fautes.append("aucun chemin déclaré")
        if fautes:
            d.refus.append(f"ligne malformée {ligne.strip()!r} — {' ; '.join(fautes)}")
            continue
        if cle in lignes_lot:
            d.refus.append(f"clé `{cle}` en double — chaque lot porte une clé unique")
            continue
        lignes_lot.append(cle)
        for c in chemins:
            d.refus += _refus_chemin(c, f"lot {cle}", admis)
            if est_manifeste(c):
                d.refus.append(f"lot {cle} : `{c}` est un lockfile ou un manifeste de dépendances — il "
                               "va à l'INTÉGRATION, écrite après la fusion (deux lots qui l'écriraient "
                               "se recouvriraient)")
        d.lots.append(Lot(cle, dev, libelle, chemins, ligne.strip()))
    if d.aucun is not None and d.lots:
        d.refus.append("`LOTS: aucun` à côté d'un `LOT:` — le plan dit deux choses")
    if len(d.lots) == 1:
        d.refus.append(f"un seul lot ({d.lots[0].cle}) : une fournée d'un lot est le parent seul — "
                       "écris `LOTS: aucun | <pourquoi>`, ou découpe en deux lots au moins")
    if d.lots and not d.integration_ecrite:
        d.refus.append("aucune ligne `INTÉGRATION:` alors qu'un `LOT:` existe — écris "
                       "`INTÉGRATION: <chemin>, …` ou `INTÉGRATION: aucune`")
    if d.integration_ecrite and not d.lots and d.aucun is None:
        d.refus.append("`INTÉGRATION:` sans aucun `LOT:` — rien ne se fusionne")
    d.refus += _refus_rosters(d.lots, racine)
    d.refus += _refus_recouvrements(d, chevauche)
    return d


def _refus_rosters(lots: list[Lot], racine: str | Path | None) -> list[str]:
    """Le roster orphelin : une déf d'hôte dans un lot SANS son roster, qui EXISTE."""
    if racine is None:
        return ["roster orphelin NON JUGÉ : aucune racine pour lire `src/cadre/data/roster/` "
                "ni `.agents/vendor/cadre/data/roster/`"] if lots else []
    refus: list[str] = []
    for lot in lots:
        dans_lot = {_canon(c) for c in lot.chemins}
        for nom in sorted({m.group(1) for c in lot.chemins
                           if (m := _DEF_HOTE.match(c.replace("\\", "/")))}):
            for roster in (modele.format(nom) for modele in ROSTERS):
                if not (Path(racine) / roster).is_file() or _canon(roster) in dans_lot:
                    continue
                refus.append(f"lot {lot.cle} : roster orphelin — une déf `{nom}` y est écrite, mais pas "
                             f"`{roster}`, qui existe et se régénère avec elle")
    return refus


def _refus_recouvrements(d: Decoupe, chevauche: Any) -> list[str]:
    if chevauche is None:
        return ["recouvrement NON JUGÉ : le prédicat de `parallel` n'a pas été fourni"] if d.lots else []
    refus: list[str] = []
    for i, un in enumerate(d.lots):
        for autre in d.lots[i + 1:]:
            paire = chevauche(un.chemins, autre.chemins)
            if paire is not None:
                refus.append(f"recouvrement : lot {un.cle} (`{paire[0]}`) et lot {autre.cle} (`{paire[1]}`)")
        if d.integration:
            paire = chevauche(un.chemins, d.integration)
            if paire is not None:
                refus.append(f"recouvrement : lot {un.cle} (`{paire[0]}`) et l'INTÉGRATION (`{paire[1]}`) — "
                             "un partagé va à l'intégration SEULE")
    return refus


def predire_route(lot: Lot, est_garde: Callable[[str], bool], seuil: int) -> tuple[str, str]:
    """`(route, détail)` d'un lot : `planifiée` (un chemin de garde), `À REDÉCOUPER`
    (sans garde, au-delà de `seuil`), ou `directe prédite` (C1 et C2 seuls)."""
    gardes = [c for c in lot.chemins if est_garde(c)]
    if gardes:
        return ("planifiée", f"garde : {gardes[0]}" + (f" (+{len(gardes) - 1})" if len(gardes) > 1 else ""))
    if len(lot.chemins) > seuil:
        return ("À REDÉCOUPER", f"{len(lot.chemins)} fichiers sans garde, au-delà de {seuil} : "
                                f"découpe en lots de {seuil} au plus")
    return ("directe prédite", "C1 et C2 seuls — titre, stage et motif se jugent au board")


def empreinte(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def compter_lignes(texte: str) -> int:
    """Les lignes NON VIDES du plan — la mesure du plafond."""
    return sum(1 for ligne in texte.splitlines() if ligne.strip())


# ---------------------------------------------------------------------------
# LE MAÎTRE CONSOLIDÉ (T-01M54GE4K9EZRRQFD9TAVNWYKM) — `PLAN-LOT:`, lu par `rapport_check` SEUL.
# ---------------------------------------------------------------------------
#: STRICTE : en tête de ligne, SANS puce (au contraire de `LOT:`).
_PLAN_LOT = re.compile(r"^PLAN-LOT:(.*)$")
#: La forme PROCHE, après le même décapage que `_proche` : voulue, non lue, donc NOMMÉE.
_PLAN_LOT_PROCHE = re.compile(r"PLAN-LOT[ \t  ]*:")
_SHA256_PLAN_LOT = re.compile(r"sha256=([0-9a-f]{64})")
FORME_PLAN_LOT = "`PLAN-LOT: <clé> | docs/tasks/<T>-lot-<clé>-plan.md | sha256=<64 hex minuscules>`"
#: COPIE de `core-scripts/plan_pool.py` `DRAFT_MARKERS` et `_STATUS_ORNEMENTS` (SYM-07718) :
#: `plan_lots` n'importe rien de `core-scripts`.
_BROUILLONS = frozenset({"IN_PROGRESS", "CRITIC_REJECTED"})
_STATUS_ORNEMENTS = "*_# -\t"


def _proche_plan_lot(ligne: str) -> bool:
    """`PLAN-LOT :`, `- PLAN-LOT:`, `**PLAN-LOT:**`, citation, indentation, NFC."""
    s = unicodedata.normalize("NFC", ligne).lstrip(" \t>")
    puce = _PUCE.match(s)
    if puce:
        s = s[puce.end():].lstrip(" \t")
    return bool(_PLAN_LOT_PROCHE.match(s.lstrip("*_").lstrip(" \t")))


def marqueur_brouillon(texte: str) -> str:
    """COPIE de `plan_pool.draft_marker` (SYM-07718) : le marqueur de brouillon d'un plan, ou "".
    Lecture TOLÉRANTE (`STATUS : IN_PROGRESS`, `**STATUS:** CRITIC_REJECTED`, casse, indentation,
    suffixe de révision) ; TOUTE ligne `STATUS` est lue, un plan amendé empile ses statuts."""
    for ligne in texte.splitlines():
        nu = ligne.strip().lstrip(_STATUS_ORNEMENTS).strip()
        if not nu.upper().startswith("STATUS"):
            continue
        _, _, valeur = nu.partition(":")
        mots = valeur.strip().strip(_STATUS_ORNEMENTS).upper().split()
        if mots and mots[0] in _BROUILLONS:
            return mots[0]
    return ""


def _faute_chemin_plan_de_lot(chemin: str) -> str | None:
    brut = chemin.replace("\\", "/")
    if not brut or "*" in brut or brut.endswith("/"):
        return "n'est pas un chemin exact (glob ou répertoire)"
    if brut.startswith("/") or re.match(r"[A-Za-z]:", brut) or ".." in brut.split("/"):
        return "n'est pas relatif à la racine du dépôt (absolu ou `..`)"
    return None


def _juger_un_plan_de_lot(cle: str, chemin: str, sha: str, parent: str | None,
                          racine: str | Path, tasks: Any) -> list[str]:
    """Les refus d'UN plan de lot cité par `PLAN-LOT:` (présent, empreinte, enrôlement,
    `LOTS: aucun | lot <clé>`, grammaire du plan de lot, statut fini)."""
    tete = f"PLAN-LOT {cle} : `{chemin}`"
    base = Path(racine).resolve()
    cible = (base / chemin).resolve()
    try:
        cible.relative_to(base)
    except ValueError:
        return [f"{tete} sort de la racine du dépôt"]
    if not cible.is_file():
        return [f"{tete} absent sous la racine — le plan de lot n'existe pas"]
    try:
        octets = cible.read_bytes()
    except OSError as exc:
        return [f"{tete} illisible ({exc})"]
    refus: list[str] = []
    calcule = empreinte(octets)
    if calcule != sha:
        refus.append(f"{tete} a l'empreinte sha256={calcule}, le maître porte sha256={sha} — le plan "
                     "de lot a changé depuis la consolidation : reconsolide")
    try:
        lot_texte = octets.decode("utf-8")
    except UnicodeDecodeError as exc:
        return refus + [f"{tete} n'est pas de l'UTF-8 ({exc})"]
    if parent and not plan_cible.enrolling_line(lot_texte, parent):
        refus.append(f"{tete} n'ENRÔLE pas {parent} (ligne 1 ou première ligne `Tâches :`)")
    dl = lire(lot_texte, racine=racine, chevauche=tasks.writeset_paths_overlap,
              admis=tasks.writeset_path_refusal)
    if dl.lots or dl.aucun is None or " ".join(dl.aucun.split()) != f"lot {cle}":
        refus.append(f"{tete} ne porte pas `LOTS: aucun | lot {cle}` — un plan de lot ne se redécoupe pas")
    refus += [f"{tete} : {r}" for r in dl.refus]
    brouillon = marqueur_brouillon(lot_texte)
    if brouillon:
        refus.append(f"{tete} est encore un brouillon (`STATUS: {brouillon}`) — un lot se consolide à "
                     "GO ou GO_AVEC_RESERVES")
    return refus


def juger_plans_de_lot(texte: str, d: Decoupe, parent: str | None, racine: str | Path,
                       tasks: Any) -> tuple[list[str], list[str]]:
    """`(refus, sortie)` des lignes `PLAN-LOT:` du maître. Aucune ligne stricte : rien à juger
    (maître non consolidé), DIT dès que le maître porte des lots. Une ligne ou plus : TOUS les
    lots couverts, chacun une fois, et chaque plan de lot jugé par `_juger_un_plan_de_lot`."""
    refus: list[str] = []
    sortie: list[str] = []
    cles_lot = [lot.cle for lot in d.lots]
    vues: list[str] = []
    ecrites = 0
    for ligne in plan_cible.lignes_hors_code(texte):
        ligne = ligne.rstrip("\r")
        m = _PLAN_LOT.match(ligne)
        if not m:
            if _proche_plan_lot(ligne):
                refus.append(f"ligne proche de `PLAN-LOT:` {ligne.strip()!r} — ni lue ni ignorée : écris "
                             f"{FORME_PLAN_LOT} en tête de ligne, SANS puce")
            continue
        ecrites += 1
        champs = [c.strip() for c in m.group(1).split("|")]
        if len(champs) != 3:
            refus.append(f"ligne malformée {ligne.strip()!r} — {len(champs)} champ(s) séparés par `|`, "
                         f"3 attendus : {FORME_PLAN_LOT}")
            continue
        cle, chemin, champ_sha = champs
        fautes: list[str] = []
        if not CLE_RE.fullmatch(cle):
            fautes.append(f"clé {cle!r} hors de `[A-Z][A-Z0-9]{{0,3}}`")
        faute = _faute_chemin_plan_de_lot(chemin)
        if faute:
            fautes.append(f"`{chemin}` {faute}")
        m_sha = _SHA256_PLAN_LOT.fullmatch(champ_sha)
        if not m_sha:
            fautes.append(f"empreinte {champ_sha!r} hors de `sha256=<64 hex minuscules>`")
        if fautes or m_sha is None:
            refus.append(f"ligne malformée {ligne.strip()!r} — {' ; '.join(fautes)}")
            continue
        if cle not in cles_lot:
            refus.append(f"PLAN-LOT {cle} : aucun `LOT: {cle}` au maître — la clé d'un plan de lot est "
                         "celle d'un lot déclaré")
            continue
        if cle in vues:
            refus.append(f"PLAN-LOT {cle} écrit deux fois — un plan de lot par lot")
            continue
        vues.append(cle)
        refus_lot = _juger_un_plan_de_lot(cle, chemin, m_sha.group(1), parent, racine, tasks)
        refus += refus_lot
        if not refus_lot:
            sortie.append(f"PLAN-LOT {cle} — {chemin} — présent, empreinte égale, `LOTS: aucun | lot {cle}`, "
                          "fini")
    if ecrites:
        manquants = [c for c in cles_lot if c not in vues]
        if manquants:
            refus.append(f"lot(s) {', '.join(manquants)} sans ligne `PLAN-LOT:` valide — un maître consolidé "
                         "couvre TOUS ses lots")
        if not parent:
            sortie.append("PLAN-LOT: enrôlement des plans de lot NON JUGÉ (`--parent` absent)")
    elif d.lots:
        sortie.append("PLAN-LOT: aucune ligne — maître non consolidé : aucun plan de lot vérifié")
    return refus, sortie


# ---------------------------------------------------------------------------
# LA COMMANDE `check` — lecture seule, pour le planificateur et le critique.
# ---------------------------------------------------------------------------
def _facade() -> Any:
    """La façade `tasks`, chargée par `plan_cible` (une instance déjà chargée
    d'abord, sinon `tasks.py` de CE dossier, par chemin)."""
    return plan_cible._tasks_module()


def rapport_check(texte: str, parent: str | None, racine: str | Path, tasks: Any) -> tuple[int, str]:
    """`(rc, sortie)` de `check` : rc 0 grammaire tenue, 1 refus."""
    d = lire(texte, racine=racine, chevauche=tasks.writeset_paths_overlap,
             admis=tasks.writeset_path_refusal)
    refus = list(d.refus)
    refus += [r for lot in d.lots if (r := refus_dev_mono(lot)) is not None]
    if parent and not plan_cible.enrolling_line(texte, parent):
        refus.append(f"le plan n'ENRÔLE pas {parent} (ligne 1 ou première ligne `Tâches :`)")
    refus_plans_de_lot, sortie_plans_de_lot = juger_plans_de_lot(texte, d, parent, racine, tasks)
    refus += refus_plans_de_lot
    lignes = compter_lignes(texte)
    if lignes > PLAFOND_LIGNES_PLAN:
        refus.append(f"plan de {lignes} lignes non vides, plafond {PLAFOND_LIGNES_PLAN} (décision pilote "
                     f"S-01M52Y43BA) — déporte mesures, couverture détaillée et tables dans `{ANNEXE}`, lue à "
                     "la demande (jamais par `check`) ; le plan garde étapes, lots, risques, tests et rollback")
    sortie: list[str] = [f"LIGNES: {lignes}/{PLAFOND_LIGNES_PLAN}"]
    if not d.forme:
        sortie.append("LOTS: aucune forme écrite — fournée DÉGÉNÉRÉE annoncée : le parent seul "
                      f"(un plan de {tasks.MAX_FICHIERS_DIRECT + 1} fichiers ou plus sans forme de lots "
                      "est refusé par plan-critic)")
    elif d.degeneree:
        sortie.append(f"LOTS: aucun — fournée dégénérée : le parent seul"
                      + (f" ({d.aucun})" if d.aucun else ""))
    else:
        integ = ", ".join(d.integration) if d.integration else "aucune"
        sortie.append(f"LOTS: {len(d.lots)} lot(s) ; INTÉGRATION : {integ}")
        for lot in d.lots:
            route, detail = predire_route(lot, tasks.est_chemin_de_garde, tasks.MAX_FICHIERS_DIRECT)
            sortie.append(f"LOT {lot.cle} — {lot.dev} — {len(lot.chemins)} fichier(s) — route : {route} ({detail})")
    sortie += sortie_plans_de_lot
    sortie += [f"REFUS: {r}" for r in refus]
    sortie.append("CHECK: refus" if refus else "CHECK: ok")
    return (1 if refus else 0, "\n".join(sortie))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lots of a plan: grammar check, read-only (rc 0 ok, 1 refused).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="check the LOT / INTEGRATION / LOTS lines of a plan, read-only")
    p.add_argument("--plan", required=True, help="the plan .md, or - for stdin")
    p.add_argument("--parent", default=None, metavar="T-ID", help="the parent task the plan must enrol")
    p.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."),
                   help="repository root (rosters are read there)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    try:
        octets = sys.stdin.buffer.read() if args.plan == "-" else Path(args.plan).read_bytes()
        texte = octets.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"plan_lots: plan illisible ({exc})", file=sys.stderr)
        return 2
    try:
        tasks = _facade()
    except (OSError, ImportError) as exc:
        print(f"plan_lots: façade `tasks.py` introuvable ({exc}) — recouvrement et garde non jugeables",
              file=sys.stderr)
        return 2
    rc, sortie = rapport_check(texte, args.parent, args.root, tasks)
    print(sortie)
    return rc


if __name__ == "__main__":
    sys.exit(main())
