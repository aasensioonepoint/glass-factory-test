#!/usr/bin/env python3
"""MOTEUR GÉNÉRIQUE DE FEUILLE DE ROUTE — les sections DÉRIVABLES du board, pour un
chantier QUELCONQUE. Lecture seule, 0 LLM, stdlib seule.

T-00001016, partie (a) de T-00000772. Le générateur du chantier de refonte
(`docs/interne/chantier/gen_feuille_de_route.py`, de l'outillage qui ne voyage pas)
mêle deux choses : ce que le board DIT (arêtes, motifs, ordres pilote, vagues,
cycles) et ce qu'un rédacteur ÉCRIT (libellés, niveaux, étapes, ordres en prose).
Ce moteur porte la première moitié, et elle seule. La seconde vit dans un fichier
de données par chantier, dont le format et la migration sont la partie (b),
T-00001017 : une instance s'y branche par `compute()` ou `deriver()` et par les
fonctions de section, jamais par un dictionnaire écrit ici.

CE QU'IL DÉRIVE, ET D'OÙ
------------------------
Tout vient du board `.agents/state/board/TASKS.json`, lu DIRECTEMENT comme le lit
`plan_waves.py`, et de `plan_waves.py` lui-même :
  - SYNTHÈSE         — tâches du chantier par état ; les ouvertes, avec leur titre.
  - AMONTS OUVERTS   — arêtes `depends_on` des ouvertes dont l'amont n'est pas clos ;
                       un amont d'un AUTRE chantier est rendu, et marqué tel.
  - ARÊTES ET MOTIFS — chaque arête d'une ouverte, le statut de son amont (ouvert,
                       satisfaite, pendante) et la nature de son motif ; puis les
                       closes qui attendent encore une non close.
  - ORDRES PILOTE    — arêtes au motif canonique `ORDRE PILOTE S-<id>`, par
                       décision ; les `ordre…` non canoniques à part, techniques.
  - VAGUES           — la sortie de `plan_waves.compute()` sur le périmètre `pending`
                       du chantier, REPRISE telle quelle et jamais recalculée ; plus
                       le chemin le plus long qui remonte depuis la dernière vague.
  - CYCLES           — ceux de `plan_waves.py`, et le remède qui retire UNE arête.

AUCUNE RECOPIE DE `plan_waves.py`. Le module frère est chargé PAR CHEMIN depuis ce
répertoire (jamais depuis `.agents/bin/`) : la clé d'ordre à deux étages
(`numeric_id`), le lecteur du store, `depends_on_of` et le motif canonique
`ORDRE_PILOTE_CANONIQUE` sont LES SIENS. Une troisième copie de ce motif serait une
surface de parité de plus, sans témoin. Une seule chose est recopiée, et elle est
dite : le préfixe `ordre` non canonique (`_ORDRE_PREFIXE`, de
`.agents/bin/plan_depends.py`), que `plan_waves.py` ne porte pas ; le banc tient sa
parité de LECTURE sur un motif que `tasks.py depends` déclare non canonique. La
décision d'un ordre pilote se lit dans la correspondance du motif canonique
lui-même (son dernier jeton) : aucun préfixe `ORDRE PILOTE` n'est recopié.

CE QU'IL NE FAIT PAS
--------------------
  - Il ne porte AUCUNE donnée éditoriale : ni libellé (le titre affiché est celui
    du board), ni niveau, ni étape, ni ordre en prose, ni nom de chantier. Le banc
    le vérifie sur la source, par l'arbre syntaxique.
  - Il n'écrit RIEN : la sortie va sur stdout, et le frère est chargé sans cache de
    bytecode. Ni horodatage ni HEAD : deux rendus du même board sont identiques à
    l'octet, ce qu'un `--check` d'instance exige.
  - Il ne fait pas autorité : le board a raison contre ce relevé, `/night`
    reconstruit son ordre lui-même, et seule `tasks.py parallel` prouve une botte.
  - DEUX LECTURES du store : la sienne, puis celle de `plan_waves.compute()`. Un
    board réécrit entre les deux rendrait des vagues d'un autre instant ; c'est un
    relevé, pas une preuve.

    python core-scripts/feuille_de_route.py [--root DIR] --workstream X [--json]
    (`--chantier X`, l'ancien nom, reste accepté)

Codes de sortie :
    0  sections rendues — un CYCLE compris : c'est une section, qui nomme le chemin
       et son remède, et la section des vagues dit qu'aucune n'est produite
    1  erreur : store malformé, ou chantier qu'aucune tâche du board ne porte —
       un refus nommé, jamais une feuille vide
    2  usage (argparse)
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

EXIT_OK = 0
EXIT_ERROR = 1

# RECOPIE de `.agents/bin/plan_depends._ORDRE_PREFIXE`, jamais importée : ce script ne
# dépend d'aucun code de `.agents/bin/`. Un motif qui OUVRE par `ordre` sans être un
# `ORDRE PILOTE S-<id>` canonique est TECHNIQUE (retirable, non protégé) — c'est ce
# que `tasks.py depends` en dit dans son AVERTISSEMENT.
_ORDRE_PREFIXE = re.compile(r"^ordre\b", re.IGNORECASE)

# Nature d'un motif d'arête — vocabulaire FERMÉ : celui de
# `plan_depends.classe_motif`, plus l'absence de motif.
ORDRE_PILOTE = "ordre pilote"
ORDRE_NON_CANONIQUE = "ordre (non canonique)"
TECHNIQUE = "technique"
SANS_MOTIF = "motif absent"

# Statut d'une arête, vu depuis son aval. `pendante` = amont absent du board :
# SATISFAITE pour `plan_waves.py` (lien pendant), et dite à part pour qu'on la voie.
OUVERT = "ouvert"
SATISFAITE = "satisfaite"
PENDANTE = "pendante"

# Bornes de CELLULE, jamais de liste : un titre ou un motif trop long est coupé et
# porte « … » ; aucune rangée n'est jamais retirée d'une table.
TITRE_MAX = 90
MOTIF_MAX = 120
CHANTIERS_MAX = 20


class FeuilleError(Exception):
    """Refus ou store malformé : exit 1, jamais une feuille vide."""


def _charger_plan_waves() -> ModuleType:
    """Le frère `plan_waves.py`, chargé par CHEMIN — aucun `sys.path` modifié, et
    SANS cache de bytecode : `exec_module` déposait `__pycache__/plan_waves.*.pyc`
    à côté du frère (mesuré, le 2026-10-09), ce qui démentait « il n'écrit rien ».
    Le réglage de l'interpréteur est rendu tel qu'il était trouvé."""
    chemin = Path(__file__).resolve().parent / "plan_waves.py"
    if not chemin.is_file():
        raise ImportError(f"{chemin} : module frère introuvable — le moteur en dépend")
    spec = importlib.util.spec_from_file_location("_feuille_de_route_plan_waves", chemin)
    if spec is None or spec.loader is None:
        raise ImportError(f"{chemin} : module frère illisible")
    module = importlib.util.module_from_spec(spec)
    avant = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = avant
    return module


PW = _charger_plan_waves()


def _cle(tid: str) -> tuple[int, int | str]:
    return PW.numeric_id(tid)


def _du_chantier(task: dict[str, Any], chantier: str) -> bool:
    return (task.get("chantier") or "") == chantier


def nature_du_motif(motif: str | None) -> tuple[str, str | None]:
    """``(nature, décision)`` : la décision est l'id `S-…` d'un ordre pilote
    canonique, ``None`` sinon. Même lecture que `plan_depends.classe_motif`. La
    décision est le DERNIER jeton de la correspondance du motif canonique (qui
    s'arrête au `\\b` après l'id) : aucun préfixe recopié ici."""
    texte = (motif or "").strip()
    if not texte:
        return SANS_MOTIF, None
    canon = PW.ORDRE_PILOTE_CANONIQUE.match(texte)
    if canon:
        return ORDRE_PILOTE, canon.group(0).split()[-1]
    if _ORDRE_PREFIXE.match(texte):
        return ORDRE_NON_CANONIQUE, None
    return TECHNIQUE, None


def _arete(aval: str, amont: str, motif: str | None,
           by_id: dict[str, dict[str, Any]], chantier: str) -> dict[str, Any]:
    nature, decision = nature_du_motif(motif)
    cible = by_id.get(amont)
    if cible is None:
        statut = PENDANTE
    elif cible["state"] == "done":
        statut = SATISFAITE
    else:
        statut = OUVERT
    return {
        "aval": aval,
        "amont": amont,
        "motif": motif or None,
        "nature": nature,
        "decision": decision,
        "statut": statut,
        "amont_etat": cible["state"] if cible is not None else None,
        "amont_chantier": (cible.get("chantier") or None) if cible is not None else None,
        "hors_chantier": cible is not None and not _du_chantier(cible, chantier),
    }


def _aretes_de(task: dict[str, Any], by_id: dict[str, dict[str, Any]],
               chantier: str) -> list[dict[str, Any]]:
    """Les arêtes d'une tâche. Un store malformé est refusé en NOMMANT la tâche qui
    le porte — jamais une trace de pile, jamais un id seul qu'il faudrait rechercher."""
    motifs = task.get("depends_motif") or {}
    if not isinstance(motifs, dict):
        raise FeuilleError(f"{task['id']} : `depends_motif` n'est pas une table "
                           f"({type(motifs).__name__}) — store malformé")
    amonts = PW.depends_on_of(task)
    for amont in amonts:
        try:
            _cle(amont)
        except PW.WavesError as exc:
            raise FeuilleError(f"{task['id']} : `depends_on` porte un id malformé, "
                               f"{amont!r} — store malformé") from exc
    return [_arete(task["id"], amont, motifs.get(amont), by_id, chantier)
            for amont in sorted(amonts, key=_cle)]


def chemins_longs(vagues: dict[str, Any],
                  by_id: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Une chaîne par tâche de la DERNIÈRE vague : on remonte par `depends_on` vers
    un amont placé dans la vague immédiatement précédente (le plus petit par la clé
    d'ordre), jusqu'à la vague 1. Kahn garantit qu'un tel amont existe à chaque cran."""
    if vagues.get("cycles") or not vagues.get("vagues"):
        return []
    rang = {tid: v["rang"] for v in vagues["vagues"] for tid in v["taches"]}
    chemins = []
    for fin in sorted(vagues["vagues"][-1]["taches"], key=_cle):
        chemin = [fin]
        while rang.get(chemin[-1], 0) > 1:
            voulu = rang[chemin[-1]] - 1
            amonts = [x for x in PW.depends_on_of(by_id.get(chemin[-1]) or {})
                      if rang.get(x) == voulu]
            if not amonts:
                break
            chemin.append(min(amonts, key=_cle))
        chemins.append(list(reversed(chemin)))
    return chemins


def _refus_chantier(board: list[dict[str, Any]], chantier: str) -> FeuilleError:
    presents = sorted({t.get("chantier") or "" for t in board} - {""})
    if not presents:
        liste = "aucun chantier n'est porté par le board"
    else:
        liste = f"chantiers présents ({len(presents)}) : " + ", ".join(presents[:CHANTIERS_MAX])
        if len(presents) > CHANTIERS_MAX:
            liste += f" … tronqué : {CHANTIERS_MAX} sur {len(presents)}"
    return FeuilleError(
        f"chantier inconnu au board : {chantier!r} — aucune tâche ne le porte ; {liste}. "
        f"Un chantier qui ne résout pas est un refus, jamais une feuille vide."
    )


def deriver(board: list[dict[str, Any]], chantier: str,
            vagues: dict[str, Any]) -> dict[str, Any]:
    """PURE : le board ENTIER (les amonts se résolvent hors du chantier), le nom du
    chantier, et la sortie de `plan_waves.compute()` pour ce chantier. Lève
    `FeuilleError` sur un chantier vide ou inconnu, `PW.WavesError` sur un id
    malformé."""
    if not chantier:
        raise FeuilleError("chantier vide : --chantier attend un nom")
    by_id = {t["id"]: t for t in board}
    du = sorted((t for t in board if _du_chantier(t, chantier)), key=lambda t: _cle(t["id"]))
    if not du:
        raise _refus_chantier(board, chantier)
    ouvertes = [t for t in du if t["state"] != "done"]
    closes = [t for t in du if t["state"] == "done"]

    aretes = [a for t in ouvertes for a in _aretes_de(t, by_id, chantier)]
    closes_en_attente = [a for t in closes for a in _aretes_de(t, by_id, chantier)
                         if a["statut"] == OUVERT]
    par_decision: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for a in aretes:
        if a["nature"] == ORDRE_PILOTE:
            par_decision[a["decision"]].append({"aval": a["aval"], "amont": a["amont"]})

    # Les TIRÉES sont les tâches du périmètre HORS demande. Depuis T-00001249,
    # `close_perimeter` n'inscrit plus un amont DÉJÀ demandé dans `tirees_par` (avant :
    # 97 des 100 « tirées » du board du kit, mesuré le 2026-10-09) : ce filtre et l'écart
    # de `section_vagues` sont GARDÉS mais désormais inertes — ils ne retirent plus rien.
    demandees = set(vagues.get("demandees") or [])
    tirees_par = vagues.get("tirees_par") or {}
    tirees = [{"tache": t, "par": tirees_par[t]}
              for t in sorted(tirees_par, key=_cle) if t not in demandees]

    cites = {t["id"] for t in du}
    cites |= {a["amont"] for a in aretes + closes_en_attente}
    cites |= set(vagues.get("perimetre") or [])
    cites |= {tid for cycle in vagues.get("cycles") or [] for tid in cycle}
    repertoire = {
        tid: {
            "titre": by_id[tid].get("task") or "",
            "etat": by_id[tid]["state"],
            "chantier": by_id[tid].get("chantier") or None,
        }
        for tid in sorted(cites, key=_cle)
        if tid in by_id
    }
    return {
        "chantier": chantier,
        "taches": [t["id"] for t in du],
        "etats": dict(sorted(collections.Counter(t["state"] for t in du).items())),
        "ouvertes": [t["id"] for t in ouvertes],
        "closes": [t["id"] for t in closes],
        "aretes": aretes,
        "amonts_ouverts": [a for a in aretes if a["statut"] == OUVERT],
        "ordres_pilote": [{"decision": d, "aretes": par_decision[d]}
                          for d in sorted(par_decision, key=_cle)],
        "ordres_non_canoniques": [a for a in aretes if a["nature"] == ORDRE_NON_CANONIQUE],
        "closes_en_attente": closes_en_attente,
        "vagues": vagues,
        "tirees": tirees,
        "cycles": vagues.get("cycles") or [],
        "chemins_longs": chemins_longs(vagues, by_id),
        "repertoire": repertoire,
    }


def compute(root: Path, chantier: str) -> dict[str, Any]:
    """Lit le board sous `root`, demande ses vagues à `plan_waves.compute()` (état
    `pending`, comme son CLI par défaut), puis dérive. Lève `FeuilleError`."""
    if not chantier:
        raise FeuilleError("chantier vide : --chantier attend un nom")
    try:
        board = PW.load_board(root)
        vagues = PW.compute(root, "pending", chantier, None)
        return deriver(board, chantier, vagues)
    except PW.WavesError as exc:
        raise FeuilleError(str(exc)) from exc


# ---------------------------------------------------------------- rendu Markdown
def _cellule(texte: str, borne: int) -> str:
    """Une cellule de table : blancs aplatis, « | » échappé, coupure DITE par « … »."""
    plat = " ".join(str(texte).split())
    if len(plat) > borne:
        plat = plat[: borne - 1].rstrip() + "…"
    return plat.replace("|", "\\|")


def _libelle(tid: str, d: dict[str, Any]) -> str:
    """Jamais un identifiant sans sa substance : l'id, puis le titre du board."""
    fiche = d["repertoire"].get(tid)
    if fiche is None:
        return f"{tid} — absente du board"
    if not fiche["titre"]:
        return tid
    return f"{tid} — {_cellule(fiche['titre'], TITRE_MAX)}"


def _hors(tid: str, d: dict[str, Any]) -> str:
    fiche = d["repertoire"].get(tid)
    if fiche is None or fiche["chantier"] == d["chantier"]:
        return ""
    if fiche["chantier"] is None:
        return " (hors chantier : sans chantier)"
    return f" (hors chantier `{fiche['chantier']}`)"


def _nature(a: dict[str, Any]) -> str:
    return f"{ORDRE_PILOTE} ({a['decision']})" if a["nature"] == ORDRE_PILOTE else a["nature"]


def _resume_vagues(d: dict[str, Any]) -> str:
    v = d["vagues"]
    if d["cycles"]:
        return f"{len(d['cycles'])} CYCLE(S) : aucune vague n'est produite"
    if not v.get("perimetre"):
        return "aucune tâche `pending` au périmètre : aucune vague"
    tailles = " / ".join(str(len(w["taches"])) for w in v["vagues"])
    return (f"{len(v['vagues'])} vague(s) de {tailles} tâche(s), {len(v['demandees'])} "
            f"demandée(s), {len(d['tirees'])} tirée(s) par dépendance, aucun cycle")


def section_synthese(d: dict[str, Any]) -> list[str]:
    aretes = d["aretes"]
    natures = collections.Counter(a["nature"] for a in aretes)
    statuts = collections.Counter(a["statut"] for a in aretes)
    nb_hors = sum(1 for a in d["amonts_ouverts"] if a["hors_chantier"])
    ouvertes_par_etat = " + ".join(f"{n} `{e}`" for e, n in d["etats"].items() if e != "done")
    out = [
        "Dérivé du board à la lecture par `core-scripts/feuille_de_route.py`, sans aucune "
        "donnée éditoriale : le board a raison contre ce relevé.",
        "",
        "| Compte | Valeur |",
        "|---|---|",
        f"| Tâches du chantier | {len(d['taches'])} |",
        f"| Closes (`done`) | {len(d['closes'])} |",
        f"| Ouvertes | {len(d['ouvertes'])}" + (f" = {ouvertes_par_etat}" if ouvertes_par_etat else "") + " |",
        f"| Arêtes portées par les ouvertes | {len(aretes)} : {natures[ORDRE_PILOTE]} {ORDRE_PILOTE}, "
        f"{natures[ORDRE_NON_CANONIQUE]} {ORDRE_NON_CANONIQUE}, {natures[TECHNIQUE]} {TECHNIQUE}, "
        f"{natures[SANS_MOTIF]} {SANS_MOTIF} |",
        f"| Amonts encore ouverts | {statuts[OUVERT]}, dont {nb_hors} hors chantier |",
        f"| Arêtes satisfaites / pendantes | {statuts[SATISFAITE]} / {statuts[PENDANTE]} |",
        f"| Closes qui attendent une non close | {len(d['closes_en_attente'])} |",
        f"| Vagues (`plan_waves.py`) | {_resume_vagues(d)} |",
        "",
    ]
    if d["ouvertes"]:
        out += ["| Ouverte | État |", "|---|---|"]
        out += [f"| {_libelle(tid, d)} | `{d['repertoire'][tid]['etat']}` |" for tid in d["ouvertes"]]
    else:
        out.append("Aucune tâche ouverte dans ce chantier.")
    return out


def section_amonts_ouverts(d: dict[str, Any]) -> list[str]:
    rangs = d["amonts_ouverts"]
    if not rangs:
        return ["Aucune ouverte n'attend un amont encore ouvert."]
    nb_hors = sum(1 for a in rangs if a["hors_chantier"])
    out = [f"{len(rangs)} arête(s) dont l'amont est encore ouvert, dont {nb_hors} vers un "
           f"autre chantier :", "",
           "| Aval | Amont ouvert | État de l'amont | Nature (motif au board) |",
           "|---|---|---|---|"]
    for a in rangs:
        out.append(f"| {_libelle(a['aval'], d)} | {_libelle(a['amont'], d)}{_hors(a['amont'], d)} "
                   f"| `{a['amont_etat']}` | {_nature(a)} |")
    return out


def _motif(a: dict[str, Any]) -> str:
    return _cellule(a["motif"], MOTIF_MAX) if a["motif"] else "—"


def section_aretes(d: dict[str, Any]) -> list[str]:
    out = ["Chaque arête `depends_on` portée par une ouverte, le statut de son amont "
           f"(`{OUVERT}` ; `{SATISFAITE}` : amont clos ; `{PENDANTE}` : amont absent du board, "
           "satisfaite pour `plan_waves.py`) et la nature de son motif.", ""]
    if d["aretes"]:
        out += ["| Aval | Amont | Statut | Nature | Motif (tel qu'au board) |", "|---|---|---|---|---|"]
        for a in d["aretes"]:
            out.append(f"| {_libelle(a['aval'], d)} | {_libelle(a['amont'], d)}{_hors(a['amont'], d)} "
                       f"| {a['statut']} | {_nature(a)} | {_motif(a)} |")
    else:
        out.append("Aucune ouverte ne porte d'arête.")
    out.append("")
    attente = d["closes_en_attente"]
    if not attente:
        out.append("Aucune close n'attend une non close.")
        return out
    out += [f"{len(attente)} close(s) qui attendent encore une non close :", "",
            "| Close | Attend | État de l'amont | Motif |", "|---|---|---|---|"]
    for a in attente:
        out.append(f"| {_libelle(a['aval'], d)} | {_libelle(a['amont'], d)}{_hors(a['amont'], d)} "
                   f"| `{a['amont_etat']}` | {_motif(a)} |")
    return out


def section_ordres_pilote(d: dict[str, Any]) -> list[str]:
    ordres = d["ordres_pilote"]
    nb = sum(len(o["aretes"]) for o in ordres)
    out = [f"{nb} ordre(s) pilote inscrit(s) en arête sur les ouvertes (motif canonique "
           f"`ORDRE PILOTE S-<id>`, protégé par `tasks.py depends`), porté(s) par {len(ordres)} "
           "décision(s)" + (" : " + ", ".join(f"{o['decision']} ×{len(o['aretes'])}" for o in ordres)
                            if ordres else "") + ".", ""]
    if ordres:
        out += ["| Décision | Aval | Amont |", "|---|---|---|"]
        for o in ordres:
            for a in o["aretes"]:
                out.append(f"| {o['decision']} | {_libelle(a['aval'], d)} | "
                           f"{_libelle(a['amont'], d)}{_hors(a['amont'], d)} |")
        out.append("")
    non = d["ordres_non_canoniques"]
    if not non:
        out.append("Aucune arête au motif `ordre…` non canonique.")
        return out
    out += [f"{len(non)} arête(s) au motif `ordre…` NON canonique : TECHNIQUES, retirables par "
            "`tasks.py depends --retirer`, jamais protégées comme un ordre pilote.", "",
            "| Aval | Amont | Motif |", "|---|---|---|"]
    for a in non:
        out.append(f"| {_libelle(a['aval'], d)} | {_libelle(a['amont'], d)}{_hors(a['amont'], d)} "
                   f"| {_motif(a)} |")
    return out


def section_vagues(d: dict[str, Any]) -> list[str]:
    v = d["vagues"]
    if d["cycles"]:
        return ["Le périmètre porte un cycle : aucune vague n'est produite (section Cycles). "
                "Un ordre partiel qui a l'air complet serait pire que pas d'ordre du tout."]
    if not v.get("perimetre"):
        return ["Aucune tâche `pending` dans ce chantier : aucune vague."]
    tirees = {r["tache"]: r["par"] for r in d["tirees"]}
    out = [f"{len(v['vagues'])} vague(s) sur {len(v['perimetre'])} tâche(s) du périmètre — les "
           f"`pending` du chantier ({len(v['demandees'])} demandée(s)), fermé sur `depends_on` "
           f"({len(tirees)} tirée(s) par dépendance). Relevé de `plan_waves.py`, repris tel quel : "
           "NON-AUTORITATIF, `/night` reconstruit son ordre et seule `tasks.py parallel` prouve "
           "une botte."]
    ecart = len(v["tirees_par"]) - len(tirees)
    if ecart:
        out.append(f"Son champ `tirees_par` en nomme {len(v['tirees_par'])} : {ecart} y sont des "
                   "tâches DEMANDÉES, rangées là quand leur aval est dépilé avant elles ; elles "
                   "sont rendues « demandée » ici.")
    out += ["", "| Vague | Tâche | Entrée au périmètre |", "|---|---|---|"]
    for w in v["vagues"]:
        for tid in w["taches"]:
            entree = f"tirée par {tirees[tid]}" if tid in tirees else "demandée"
            out.append(f"| {w['rang']} | {_libelle(tid, d)}{_hors(tid, d)} | {entree} |")
    if v["murs"]:
        out += ["", f"Murs — {len(v['murs'])} branche(s) arrêtée(s) sur une tâche `blocked` :"]
        out += [f"- {_libelle(dep, d)} attend {_libelle(mur, d)} (`blocked` — attend une décision)"
                for dep, mur in v["murs"]]
    if v["hors_vagues"]:
        out += ["", f"Hors vagues — {len(v['hors_vagues'])} tâche(s) :"]
        out += [f"- {_libelle(r['tache'], d)} dépend de {r['dependance']} — {r['raison']}"
                for r in v["hors_vagues"]]
    if d["chemins_longs"]:
        out += ["", f"Chemin le plus long (une chaîne par tâche de la dernière vague, rang "
                f"{v['vagues'][-1]['rang']}, un amont par vague) : "
                + " ; ".join(" → ".join(c) for c in d["chemins_longs"]) + "."]
    return out


def section_cycles(d: dict[str, Any]) -> list[str]:
    cycles = d["cycles"]
    if not cycles:
        return ["Aucun cycle sur le périmètre fermé (`plan_waves.py`)."]
    out = [f"{len(cycles)} cycle(s) sur le périmètre fermé (`plan_waves.py`) — aucune vague n'est "
           "produite tant qu'il tient. Le board charge un cycle par choix, pour que le remède "
           "TOURNE ; il retire UNE arête, jamais la déclaration entière :", ""]
    for cycle, coupe in zip(cycles, d["vagues"].get("coupes") or []):
        out.append(f"- `{' → '.join(cycle)}`")
        aval, amont = coupe["aval"], coupe["amont"]
        # Un id du board est une DONNÉE : chaque commande imprimée le passe par
        # `shlex.quote`, la SUGGESTION entière aussi (entre `"…"`, un `$(…)` vivrait).
        # Borne : quotage POSIX — collé dans PowerShell ou cmd, `'…'` n'est pas leur échappement.
        q_aval, q_amont = shlex.quote(aval), shlex.quote(amont)
        if coupe["ordre_pilote_seul"]:
            suggestion = shlex.quote(f"SUGGESTION: retirer {aval} <- {amont}")
            out.append(f"  - toutes ses arêtes sont des ORDRE PILOTE — route SUGGESTION : "
                       f"`python .agents/bin/specs.py add --task {q_aval} --kind delta "
                       f"{suggestion} --text \"<pourquoi>\"`, puis, "
                       f"après décision du pilote, `python .agents/bin/tasks.py depends {q_aval} "
                       f"--retirer-ordre-pilote {q_amont} S-<décision du pilote>`")
            continue
        restes = ", ".join(f"{dep} ({_cellule(m, MOTIF_MAX) if m else 'héritée'})"
                           for dep, m in coupe["restes"])
        suite = f" (restent : {restes})" if restes else " (c'était sa seule arête)"
        out.append(f"  - remède : `python .agents/bin/tasks.py depends {q_aval} --retirer {q_amont}`{suite}")
    return out


# L'ordre des sections ; une instance peut appeler chaque fonction seule.
SECTIONS: tuple[tuple[str, Callable[[dict[str, Any]], list[str]]], ...] = (
    ("Synthèse", section_synthese),
    ("Amonts ouverts", section_amonts_ouverts),
    ("Arêtes et motifs", section_aretes),
    ("Ordres pilote inscrits en arête", section_ordres_pilote),
    ("Vagues (`plan_waves.py`)", section_vagues),
    ("Cycles", section_cycles),
)


def render(d: dict[str, Any]) -> str:
    """Le Markdown des six sections, déterministe : aucun horodatage, aucun HEAD."""
    out: list[str] = []
    for titre, section in SECTIONS:
        entete = f"## {titre}"
        if section is section_synthese:
            entete += f" — chantier `{d['chantier']}`"
        out += [entete, "", *section(d), ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Board-derivable sections for one workstream (read only): "
        "open upstreams, edges and motives, pilot orders, plan_waves.py waves, cycles. "
        "No editorial data - see the file header.",
        epilog="exit codes: 0 sections rendered (a cycle included) - 1 malformed store or unknown "
        "workstream - 2 usage",
    )
    ap.add_argument("--root", default=".", help="repository root (default: .) - used by the tests")
    ap.add_argument("--workstream", "--chantier", dest="chantier", required=True, metavar="WORKSTREAM",
                    help="the workstream to render (board field `chantier`; old name: --chantier)")
    ap.add_argument("--json", action="store_true", help="the derivations as JSON, not truncated")
    args = ap.parse_args(argv)
    PW.force_utf8_stdio()
    try:
        derive = compute(Path(os.fspath(args.root)), args.chantier)
    except FeuilleError as exc:
        print(f"feuille_de_route: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(derive, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render(derive))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
