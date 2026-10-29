#!/usr/bin/env python3
"""LE PRÉFLIGHT DE FORME D'UN PLAN — avant `plan-critic` (T-01M572N5Q3JVJWJDXC0D734ZDE, STDLIB SEULE).

Décision pilote S-01M57JCYTZWRR3D3Z593SMFDZ4 (« Forme seule ») : ce module ne contrôle que la
FORME du plan, n'exécute AUCUNE donnée du plan et ne rejoue aucun banc — le rejeu reste à la
porte, le fond au critique. Il n'importe ni `subprocess` ni `shlex`, ne prend aucun verrou ; un
texte du plan n'est jamais qu'une chaîne comparée à des formes fermées. Sa SEULE écriture est
le jalon `planification` du chrono local (`jalon_chrono`, après le rapport, rc 0 ou 1) : hors
de sa sortie, avis sur stderr, rc inchangé ; `racine_commune` y lit git (`rev-parse`).

    plan_preflight.py --plan "<chemin>" --task <T-ID> [--root <racine>]

Le chemin relatif du plan se lit sous `--root` (défaut : `$CLAUDE_PROJECT_DIR`, sinon le
dossier courant), comme `plan_cible.cible_check`. HUIT CONTRÔLES, tous joués, tous listés :

* `lots` — `plan_lots.rapport_check` TEL QUEL : lignes `LOT:`/`INTÉGRATION:`/`LOTS:`, plafond
  de 45 lignes non vides, lot `dev-mono` à un chemin (+ son test colocalisé), enrôlement de
  `--task`, recouvrements et chemins de garde par la façade `tasks` (jamais une copie).
* `cibles` — `plan_cible.cible_check` TEL QUEL, sous le même régime que `start`/`done`
  (`plan_cible._arme_pour_tache`) : marqueur `PLAN_CIBLE_REQUIRED` absent ou tâche hors du
  chantier armé ⇒ NON JUGÉ, et la sortie le DIT.
* `aretes` — `plan_depends.aretes_du_plan` TEL QUEL (ids contrôlés contre le board quand il
  existe) ; sous le régime armé, un plan sans `ARÊTE:` ni `ARÊTES: aucune` est refusé, comme à
  la trace `plan approuvé`. L'INSCRIPTION des arêtes au board n'est pas jugée ici.
* `write-set` — chaque chemin de `LOT:` et d'`INTÉGRATION:` existe comme FICHIER sous la racine
  après résolution (un lien sortant est refusé), sinon il est déclaré par UNE ligne
  `- SYM-new \\`<chemin relatif exact>\\` (create)` ; ni glob, ni segment vide, `.` ou `..`.
* `bancs` — sous `## Tests`, au moins une ligne `BANCS:` ; chaque item (`<chemin>[::<test>]`)
  suit la liste FERMÉE du hook `bancs-mandat` (grammaire d'item et noms de base RECOPIÉS, parité
  tenue par le témoin) et existe comme fichier sous la racine ; ou `BANCS: aucun | <pourquoi>`
  (10 caractères au moins, sans gabarit `<…>`).
* `changelog` — FACULTATIVE, au plus une ligne hors bloc de code : `CHANGELOG: <rubrique> |
  <titre> | <impact>` ou `CHANGELOG: sans objet | <motif>`, champs non vides, séparateur exact
  ` | `. Le préflight juge la forme du plan, jamais le futur `CHANGELOG.md`.
* preflight — la ligne exacte PREFLIGHT: à jouer par l’exécuteur apparaît une fois hors bloc de code ; sa présence ne prouve pas que l'outil a tourné.
* `interaction` — un plan d'ÉCRAN porte UNE ligne `INTERACTION:` hors bloc de code (décision pilote
  S-01M5N24P2Y0SH6S0W0YNG3TAN6). Signal d'écran : une ligne qui ouvre sur `mockup:` ou
  `mockup not reproduced:` (`no mockup:` seul n'en est pas un), ou un chemin de `LOT:`, de
  `- SYM-new` ou de ligne de symbole impacté (`SYM-<n> \\`chemin[:lignes]\\``) dont le suffixe est dans `FRONT_SUFFIXES` (RECOPIÉ de `test_mockup_plan_line.py`,
  parité tenue par le témoin). Formes : `INTERACTION: focus=… ; echap=… ; modal=… ; empilement=… ;
  wcag=… ; largeurs=… ; etats=…` (les sept clés d'`INTERACTION_CLES`, dans cet ordre ; découpe sur
  `;` puis au PREMIER `=` ; valeurs non vides, sans gabarit `<…>`) ou `INTERACTION: sans objet |
  <motif>` (10 à 500 caractères, sans gabarit). Présente sans signal, sa forme est jugée aussi.
  Borne : un chemin d'écran cité ailleurs qu'en `LOT:`, `SYM-new` ou ligne de symbole n'est pas un
  signal ; la VÉRITÉ
  des valeurs reste au critique.

RC NOMMÉS (dernière ligne `RESULTAT:`) : 0 forme tenue · 1 refus de forme (TOUS listés) · 2 erreur
de configuration (plan illisible, non UTF-8 ou de plus de `MAX_PLAN_OCTETS` = 2 Mio, racine
absente, façade `tasks` introuvable, marqueur, board ou spec illisible ; usage invalide). Les fins
de ligne CRLF ou CR sont normalisées en LF avant les contrôles, comme `start`/`done` les lisent ;
la ligne `PLAN:` porte le sha256 des octets BRUTS lus : la sortie se rattache au plan jugé. La ligne `PREFLIGHT: à jouer par l’exécuteur` est contrôlée comme FORME ; seule la sortie réelle de cette commande prouve que le préflight a tourné.

CE QU'IL NE PROUVE PAS : qu'une prémisse est vraie, qu'un banc passe, qu'une commande prescrite
est admise par les gardes, que le write-set suffit — c'est le travail du critique et de la porte.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

_BIN = str(Path(__file__).resolve().parent)
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)
import plan_cible  # noqa: E402 — frères stdlib ; `tasks` n'est chargé que par `plan_lots._facade`
import plan_depends  # noqa: E402
import plan_lots  # noqa: E402

CONTROLES = ("lots", "cibles", "aretes", "write-set", "bancs", "changelog", "preflight", "interaction")
PREFLIGHT_LIGNE = "PREFLIGHT: à jouer par l’exécuteur"
TACHE_RE = re.compile(r"T-[0-9A-Za-z]{1,40}")

# --- write-set : la déclaration d'un chemin à créer (annexe T-01M572N5Q3, grammaire § 5). ---
SYM_NEW_RE = re.compile(r"^- SYM-new[ \t]+`([^`]{1,400})`[ \t]+\(create\)[ \t]*$")
SYM_NEW_FORME = "- SYM-new `<chemin relatif exact>` (create)"
SYM_IMPACT_RE = re.compile(r"^SYM-\d+\s+`([^`:]{1,400})(?::[^`]{0,80})?`")  # symbole impacté, `:lignes` optionnel
_PUCE = re.compile(r"(?:[-*+]|\d{1,3}[.)])[ \t]")
_GLOB = ("*", "?", "[")

# --- bancs : RECOPIÉ du hook `.claude/hooks/bancs-mandat.sh` (parité : test_plan_preflight). ---
BANC_ITEM_RE = re.compile(r"^[A-Za-z0-9._/-]+(::[A-Za-z0-9_][A-Za-z0-9_.\[\]-]*)*$")
BANC_NOM_RE = re.compile(r"^(test_[^/]*\.py|[^/]*_test\.(?:py|go)|[^/]*\.(?:test|spec)\.[A-Za-z0-9]+"
                         r"|[^/]*_spec\.rb|[^/]*(?:Test|Tests|IT)\.(?:java|kt|cs))$")
BANC_RUST_RE = re.compile(r"^[^/]+\.rs$")
GABARIT_RE = re.compile(r"<[^<>]*>")  # sans `<` intérieur : linéaire sur une ligne non bornée
RAISON_MIN = 10
RAISON_MAX = 500
MAX_PLAN_OCTETS = 2 * 1024 * 1024  # lecture bornée : au-delà, rc 2 sans lire la suite
_TESTS_HEAD = re.compile(r"^##\s+Tests\b")
_SECTION_2 = re.compile(r"^##\s")

# --- changelog : une ligne facultative, deux formes. ---
CHANGELOG_RE = re.compile(r"^(?:- )?CHANGELOG:(.*)$")
_CHANGELOG_PROCHE = re.compile(r"CHANGELOG[ \t]*:")
CHANGELOG_FORMES = "`CHANGELOG: <rubrique> | <titre> | <impact>` ou `CHANGELOG: sans objet | <motif>`"
SANS_OBJET = "sans objet"

# --- interaction : la spec d'interaction d'un plan d'écran (S-01M5N24P2Y0SH6S0W0YNG3TAN6). ---
# RECOPIÉ de `.agents/evals/test_mockup_plan_line.py` (parité : test_plan_preflight).
FRONT_SUFFIXES = frozenset(
    {".html", ".htm", ".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
)
INTERACTION_CLES = ("focus", "echap", "modal", "empilement", "wcag", "largeurs", "etats")
INTERACTION_TETE = "INTERACTION:"
INTERACTION_FORMES = ("`INTERACTION: " + " ; ".join(f"{k}=<…>" for k in INTERACTION_CLES)
                      + "` ou `INTERACTION: sans objet | <motif>`")
SIGNAUX_MOCKUP = ("mockup:", "mockup not reproduced:")


@dataclass
class Controle:
    """Le résultat d'UN contrôle. `etat` : `ok`, `refus`, `non jugé` ou `erreur`."""
    nom: str
    refus: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    note: str = ""
    details: list[str] = field(default_factory=list)
    juge: bool = True

    @property
    def etat(self) -> str:
        if self.erreurs:
            return "erreur"
        if self.refus:
            return "refus"
        return "ok" if self.juge else "non jugé"


def _decape(ligne: str) -> str:
    """La ligne sans citation, puce ni gras de tête (forme F5 de `plan_depends`)."""
    s = unicodedata.normalize("NFC", ligne).lstrip(" \t>")
    puce = _PUCE.match(s)
    if puce:
        s = s[puce.end():].lstrip(" \t")
    return s.lstrip("*_").lstrip(" \t")


def _lignes(texte: str) -> list[str]:
    return [ligne.rstrip("\r") for ligne in plan_cible.lignes_hors_code(texte)]


def _canon(chemin: str) -> str:
    return unicodedata.normalize("NFC", chemin.replace("\\", "/"))


def resoudre_sous_racine(racine: Path, chemin: str) -> tuple[Path | None, str | None]:
    """`(cible résolue, None)` si `chemin` reste sous `racine` (déjà résolue), sinon
    `(None, cause)`. Aucun accès autre que la résolution des liens ; rien n'est exécuté."""
    brut = _canon(chemin)
    if any(c in brut for c in _GLOB):
        return None, "n'est pas un chemin exact (glob)"
    segments = brut.split("/")
    if any(s in ("", ".", "..") for s in segments):
        return None, "porte un segment vide, `.` ou `..` (ou un chemin absolu)"
    try:
        cible = (racine / brut).resolve()
        cible.relative_to(racine)
    except ValueError:
        return None, "sort de la racine (lien sortant ou chemin hors racine)"
    except (OSError, RuntimeError):  # boucle de liens (RuntimeError avant 3.13), nom trop long
        return None, "ne se résout pas (boucle de liens ou nom trop long)"
    return cible, None


# ---------------------------------------------------------------------------
# LES HUIT CONTRÔLES — fonctions de module, appelées par leur nom à chaque `preflight`.
# ---------------------------------------------------------------------------
def controle_lots(texte: str, tache: str, racine: Path, tasks: Any) -> Controle:
    c = Controle("lots")
    if tasks is None:
        c.erreurs.append("façade `tasks.py` introuvable — recouvrements et chemins de garde non jugeables")
        return c
    _rc, sortie = plan_lots.rapport_check(texte, tache, racine, tasks)
    for ligne in sortie.splitlines():
        if ligne.startswith("REFUS: "):
            c.refus.append(ligne[len("REFUS: "):])
        elif not ligne.startswith("CHECK: "):
            c.details.append(ligne)
    c.note = c.details[0] if c.details else ""
    return c


def controle_cibles(racine: Path, plan: Path, tache: str) -> Controle:
    c = Controle("cibles")
    try:
        arme = plan_cible._arme_pour_tache(racine, tache, avertir=False)
    except plan_cible.CibleError as exc:
        c.erreurs.append(str(exc))
        return c
    if arme is None:
        c.juge = False
        c.note = (f"PLAN_CIBLE_REQUIRED absent, ou {tache} hors du chantier armé ou absente du board — "
                  "start et done ne la contrôlent pas non plus")
        return c
    try:
        rc, message = plan_cible.cible_check(racine, str(plan), None)
    except (plan_cible.CibleError, OSError, ValueError) as exc:
        c.erreurs.append(f"cible-check : {exc}")
        return c
    if rc == 2:
        c.erreurs.append(message)
    elif rc == 1:
        c.refus += [ligne.strip()[2:] for ligne in message.splitlines() if ligne.strip().startswith("- ")]
        if not c.refus:
            c.refus.append(message)
    else:
        c.note = message.splitlines()[0]
    return c


def controle_aretes(texte: str, racine: Path, tache: str) -> Controle:
    c = Controle("aretes")
    try:
        board = plan_cible._board_brut(racine)
        arme = plan_cible._arme_pour_tache(racine, tache, avertir=False)
    except plan_cible.CibleError as exc:
        c.erreurs.append(str(exc))
        return c
    connus = {t["id"] for t in board.get("tasks", []) if isinstance(t, dict) and t.get("id")} \
        if board is not None else None
    aretes, fautives, aucune = plan_depends.aretes_du_plan(
        texte, lambda t: plan_cible.enrolling_line(texte, t), connus)
    c.refus += fautives
    if not aretes and not aucune and arme is not None:
        c.refus.append("ni `ARÊTE: T-<aval> <- T-<amont> | <motif>` ni `ARÊTES: aucune` — la trace "
                       "`plan approuvé` exige l'une des deux formes sous le régime armé")
    c.note = ("ARÊTES: aucune" if aucune else f"{len(aretes)} arête(s)") + (
        " ; ids NON contrôlés : board absent" if connus is None else "")
    return c


def declarations_sym_new(texte: str) -> tuple[list[str], list[str]]:
    """`(chemins déclarés, lignes fautives)` — les lignes `- SYM-new` hors bloc de code."""
    chemins: list[str] = []
    fautives: list[str] = []
    for ligne in _lignes(texte):
        m = SYM_NEW_RE.match(ligne)
        if m:
            chemins.append(m.group(1))
        elif _decape(ligne).startswith("SYM-new"):
            fautives.append(f"ligne SYM-new malformée {ligne.strip()!r} — forme attendue `{SYM_NEW_FORME}`")
    return chemins, fautives


def controle_write_set(texte: str, racine: Path) -> Controle:
    c = Controle("write-set")
    declares, c.refus = declarations_sym_new(texte)
    a_creer: set[str] = set()
    for chemin in declares:
        _cible, cause = resoudre_sous_racine(racine, chemin)
        if cause:
            c.refus.append(f"SYM-new `{chemin}` {cause}")
        else:
            a_creer.add(_canon(chemin))
    d = plan_lots.lire(texte)
    chemins = [(f"lot {lot.cle}", p) for lot in d.lots for p in lot.chemins]
    chemins += [("INTÉGRATION", p) for p in d.integration]
    for ou, chemin in chemins:
        cible, cause = resoudre_sous_racine(racine, chemin)
        if cause:
            c.refus.append(f"{ou} : `{chemin}` {cause}")
        elif cible is not None and cible.is_file():
            continue
        elif cible is not None and cible.exists():
            c.refus.append(f"{ou} : `{chemin}` existe mais n'est pas un fichier")
        elif _canon(chemin) not in a_creer:
            c.refus.append(f"{ou} : `{chemin}` absent du disque et sans `{SYM_NEW_FORME}`")
    c.note = f"{len(chemins)} chemin(s), {len(a_creer)} déclaré(s) SYM-new"
    if not chemins:
        c.juge = False
        c.note = "aucun chemin de `LOT:` ni d'`INTÉGRATION:` — rien à juger"
    return c


def _refus_item(racine: Path, item: str) -> str | None:
    if "`" in item or not BANC_ITEM_RE.fullmatch(item):
        return "hors de la liste fermée `<chemin>[::<test>]` (backtick, mot, glob ou caractère interdit)"
    chemin = item.split("::", 1)[0]
    segments = chemin.split("/")
    if any(s in ("", ".", "..") for s in segments):
        return "porte un segment vide, `.` ou `..`"
    rust = len(segments) >= 2 and segments[-2] == "tests" and BANC_RUST_RE.fullmatch(segments[-1])
    if not (BANC_NOM_RE.fullmatch(segments[-1]) or rust):
        return "n'a pas un nom de banc de la liste fermée du hook `bancs-mandat`"
    cible, cause = resoudre_sous_racine(racine, chemin)
    if cause:
        return cause
    if cible is None or not cible.is_file():
        return "absent du disque — un témoin neuf se nomme hors `BANCS:` jusqu'à sa création"
    return None


def controle_bancs(texte: str, racine: Path) -> Controle:
    c = Controle("bancs")
    lignes = _lignes(texte)
    debut = next((i for i, ligne in enumerate(lignes) if _TESTS_HEAD.match(ligne)), None)
    if debut is None:
        c.refus.append("aucune section `## Tests` — chaque lot y porte sa ligne `BANCS:`")
        return c
    fin = next((i for i in range(debut + 1, len(lignes)) if _SECTION_2.match(lignes[i])), len(lignes))
    valeurs = [ligne.split("BANCS:", 1)[1].strip() for ligne in lignes[debut + 1:fin] if "BANCS:" in ligne]
    if not valeurs:
        c.refus.append("aucune ligne `BANCS:` sous `## Tests` — forme `- <lot> — témoin neuf <chemin> ; "
                       "BANCS: <chemin exact>[::<test>], …` ou `BANCS: aucun | <pourquoi>`")
    items = 0
    for valeur in valeurs:
        if valeur.startswith("aucun | "):
            raison = valeur[len("aucun | "):]
            if len(raison) < RAISON_MIN:
                c.refus.append(f"`BANCS: aucun | {raison}` — raison de {RAISON_MIN} caractères au moins")
            elif GABARIT_RE.search(raison[:RAISON_MAX]):
                c.refus.append(f"`BANCS: aucun | {raison}` — gabarit `<…>` recopié")
            continue
        for brut in valeur.split(","):
            item = brut.strip()
            items += 1
            cause = _refus_item(racine, item)
            if cause:
                c.refus.append(f"banc `{item}` {cause}")
    c.note = f"{len(valeurs)} ligne(s) BANCS:, {items} item(s)"
    return c


def controle_changelog(texte: str) -> Controle:
    c = Controle("changelog")
    vues = 0
    for ligne in _lignes(texte):
        m = CHANGELOG_RE.match(ligne)
        if not m:
            if _CHANGELOG_PROCHE.match(_decape(ligne)):
                c.refus.append(f"ligne proche de `CHANGELOG:` {ligne.strip()!r} — écris `CHANGELOG:` en tête "
                               "de ligne (seule la puce `- ` est tolérée)")
            continue
        vues += 1
        champs = [x.strip() for x in m.group(1).strip().split(" | ")]
        attendus = 2 if champs[0] == SANS_OBJET else 3
        if len(champs) != attendus or any(not x or "|" in x for x in champs):
            c.refus.append(f"ligne malformée {ligne.strip()!r} — {CHANGELOG_FORMES}, champs non vides, "
                           "séparateur exact ` | `")
    if vues > 1:
        c.refus.append(f"`CHANGELOG:` écrite {vues} fois — au plus une")
    c.note = "ligne présente" if vues else "absente (facultative)"
    return c


def controle_preflight(texte: str) -> Controle:
    c = Controle("preflight")
    vues = [_decape(ligne) for ligne in _lignes(texte)
            if _decape(ligne).startswith("PREFLIGHT:")]
    if vues != [PREFLIGHT_LIGNE]:
        c.refus.append(f"`{PREFLIGHT_LIGNE}` attendu une fois hors bloc de code")
    return c


def est_chemin_ecran(chemin: str) -> bool:
    """Un chemin est un fichier d'écran par son suffixe (`.scss` seul n'a pas de suffixe)."""
    return PurePosixPath(_canon(chemin)).suffix.lower() in FRONT_SUFFIXES


def signal_ecran(texte: str) -> str | None:
    """Ce qui fait d'un plan un plan d'écran, ou `None` : une ligne `mockup:` ou `mockup not
    reproduced:` (jamais `no mockup:` seul), ou un chemin d'écran de `LOT:`, de `- SYM-new` ou
    de ligne de symbole impacté (`SYM-<n> `chemin[:lignes]``)."""
    for ligne in _lignes(texte):
        tete = _decape(ligne).lower()
        if any(tete.startswith(s) for s in SIGNAUX_MOCKUP):
            return f"ligne {ligne.strip()[:80]!r}"
    d = plan_lots.lire(texte)
    for lot in d.lots:
        for chemin in lot.chemins:
            if est_chemin_ecran(chemin):
                return f"lot {lot.cle} : `{chemin}`"
    for chemin in declarations_sym_new(texte)[0]:
        if est_chemin_ecran(chemin):
            return f"SYM-new `{chemin}`"
    for ligne in _lignes(texte):
        m = SYM_IMPACT_RE.match(_decape(ligne))
        if m and est_chemin_ecran(m.group(1)):
            return f"symbole impacté `{m.group(1)}`"
    return None


def fautes_interaction(valeur: str) -> list[str]:
    """Les fautes de forme de la valeur d'une ligne `INTERACTION:` (après la tête)."""
    if valeur.startswith(SANS_OBJET):
        reste = valeur[len(SANS_OBJET):]
        if not reste.startswith(" | "):
            return ["`sans objet` sans son séparateur exact ` | <motif>`"]
        motif = reste[len(" | "):].strip()
        if not RAISON_MIN <= len(motif) <= RAISON_MAX:
            return [f"motif de {len(motif)} caractère(s) — {RAISON_MIN} à {RAISON_MAX} attendus"]
        if GABARIT_RE.search(motif):
            return ["gabarit `<…>` recopié dans le motif"]
        return []
    segments = [s.strip() for s in valeur.split(";")]
    if len(segments) != len(INTERACTION_CLES):
        return [f"{len(segments)} segment(s) séparés par `;` — {len(INTERACTION_CLES)} clés attendues, "
                "aucune valeur ne porte de `;`"]
    fautes: list[str] = []
    for attendue, segment in zip(INTERACTION_CLES, segments):
        cle, egal, contenu = segment.partition("=")
        cle, contenu = cle.strip(), contenu.strip()
        if not egal or cle != attendue:
            fautes.append(f"clé `{cle or segment[:30]}` là où `{attendue}=` est attendue (sept clés, cet ordre)")
        elif not contenu:
            fautes.append(f"clé `{attendue}` vide")
        elif GABARIT_RE.search(contenu):
            fautes.append(f"clé `{attendue}` : gabarit `<…>` recopié")
    return fautes


def controle_interaction(texte: str) -> Controle:
    c = Controle("interaction")
    vues = [(ligne.strip(), _decape(ligne)) for ligne in _lignes(texte)
            if _decape(ligne).startswith(INTERACTION_TETE)]
    signal = signal_ecran(texte)
    if len(vues) > 1:
        c.refus.append(f"`{INTERACTION_TETE}` écrite {len(vues)} fois — une seule ligne")
    for brute, ligne in vues:
        for faute in fautes_interaction(ligne[len(INTERACTION_TETE):].strip()):
            c.refus.append(f"ligne malformée {brute[:80]!r} — {faute} ; {INTERACTION_FORMES}")
    if signal and not vues:
        c.refus.append(f"plan d'écran ({signal}) sans ligne `{INTERACTION_TETE}` hors bloc de code — "
                       f"{INTERACTION_FORMES}")
    c.note = (f"plan d'écran ({signal})" if signal else "aucun signal d'écran — ligne non exigée") + (
        ", ligne présente" if vues else "")
    return c


# ---------------------------------------------------------------------------
# L'ASSEMBLAGE ET LA COMMANDE.
# ---------------------------------------------------------------------------
def _charger_tasks() -> Any:
    try:
        return plan_lots._facade()
    except (OSError, ImportError, SyntaxError):
        return None


def preflight(texte: str, plan: Path, tache: str, racine: Path, tasks: Any) -> list[Controle]:
    """Les huit contrôles, dans l'ordre de `CONTROLES` — tous joués, aucun court-circuit."""
    return [
        controle_lots(texte, tache, racine, tasks),
        controle_cibles(racine, plan, tache),
        controle_aretes(texte, racine, tache),
        controle_write_set(texte, racine),
        controle_bancs(texte, racine),
        controle_changelog(texte),
        controle_preflight(texte),
        controle_interaction(texte),
    ]


def rapport(controles: list[Controle], entete: str) -> tuple[int, str]:
    """`(rc, sortie)` : rc 2 dès une erreur, sinon 1 dès un refus, sinon 0."""
    sortie = [entete]
    for c in controles:
        sortie.append(f"[{c.nom}] {c.etat}" + (f" — {c.note}" if c.note else ""))
        sortie += [f"  {d}" for d in c.details[1:]]
    sortie += [f"REFUS [{c.nom}]: {r}" for c in controles for r in c.refus]
    sortie += [f"ERREUR [{c.nom}]: {e}" for c in controles for e in c.erreurs]
    erreurs = sum(len(c.erreurs) for c in controles)
    refus = sum(len(c.refus) for c in controles)
    borne = "forme seule : aucun banc rejoué, aucune donnée du plan exécutée"
    if erreurs:
        sortie.append(f"RESULTAT: erreur de configuration — rc 2 ({erreurs} cause(s)) — {borne}")
        return 2, "\n".join(sortie)
    if refus:
        sortie.append(f"RESULTAT: refus de forme — rc 1 ({refus} refus) — {borne}")
        return 1, "\n".join(sortie)
    sortie.append(f"RESULTAT: forme tenue — rc 0 — {borne}")
    return 0, "\n".join(sortie)


def _tache(valeur: str) -> str:
    if not TACHE_RE.fullmatch(valeur):
        raise argparse.ArgumentTypeError(f"{valeur!r} n'est pas un identifiant T-<id>")
    return valeur


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shape-only preflight of a plan before plan-critic, read-only on the "
                                             "plan; writes the local chrono milestone (advisory, never "
                                             "blocking) (rc 0 shape held, 1 shape refused, 2 configuration error).")
    ap.add_argument("--plan", required=True, help="the plan .md (a relative path is read under --root)")
    ap.add_argument("--task", required=True, type=_tache, metavar="T-ID", help="the task the plan must enrol")
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."), help="repository root")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    racine = Path(args.root).resolve()
    if not racine.is_dir():
        print(f"RESULTAT: erreur de configuration — rc 2 — racine {args.root!r} absente")
        return 2
    plan = Path(args.plan)
    if not plan.is_absolute():
        plan = racine / plan
    try:
        with plan.open("rb") as flux:
            octets = flux.read(MAX_PLAN_OCTETS + 1)
        if len(octets) > MAX_PLAN_OCTETS:
            print(f"RESULTAT: erreur de configuration — rc 2 — plan trop volumineux "
                  f"(plus de {MAX_PLAN_OCTETS} octets)")
            return 2
        texte = octets.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"RESULTAT: erreur de configuration — rc 2 — plan illisible ({type(exc).__name__} : {exc})")
        return 2
    entete = f"PLAN: {args.plan} sha256={plan_lots.empreinte(octets)} tâche={args.task}"
    try:
        rc, sortie = rapport(preflight(texte, plan, args.task, racine, _charger_tasks()), entete)
    except Exception as exc:  # noqa: BLE001 — un plantage n'est jamais un refus de forme (rc 1)
        print(f"{entete}\nRESULTAT: erreur de configuration — rc 2 — préflight planté "
              f"({type(exc).__name__} : {exc})")
        return 2
    print(sortie)
    if rc in (0, 1):
        jalon_chrono(racine, args.task, _charger_tasks())
    return rc


def jalon_chrono(racine: Path, tache: str, tasks: Any) -> None:
    """LE CHRONO DU TOUR (T-01M5VZF47T9RT1YM9KC67HCQPP) : un plan soumis au critique ouvre `planification`
    au journal local du chrono de `tache` (`task_chrono.jalon_de_planification`, « plan-soumis », idempotent),
    sous la racine COMMUNE. Une racine jetable (`AGENTS_EVENTS_DIR`, dossier temporaire : banc, clone /tmp)
    n'écrit rien. Seule écriture du préflight, hors de sa sortie : avis sur STDERR (`CHRONO: avis`), jamais
    sur stdout, rc inchangé ; aucune donnée du plan n'y entre, seul l'id de tâche validé."""
    if tasks is None:
        return
    try:
        tc = tasks.task_chrono_module()
        base = tc.racine_de_jalon(racine)
        if base is None:
            return
        avis = tc.jalon_de_planification(base, tasks.load(str(base)), tache, "plan-soumis")
    except Exception as exc:  # noqa: BLE001 — le chrono observe, il ne change jamais le verdict de forme
        avis = [f"CHRONO: avis {tache} — planification non relevée ({type(exc).__name__}: {exc})"]
    for ligne in avis:
        print(ligne, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
