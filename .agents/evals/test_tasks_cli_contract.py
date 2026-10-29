#!/usr/bin/env python3
"""T-01M4V7R7CCHA59Q8VZ0GFKX4R2 — LE CONTRAT CLI DE `tasks.py`, ET LE BANC QUI LE TIENT.

Source machine : `.agents/ref/TASKS_CLI_CONTRACT.json` ; lecture humaine :
`.agents/ref/TASKS_CLI_CONTRACT.md`. Ce banc confronte le contrat au parseur RÉELLEMENT
construit (`_construire_parseur([])`, partie `tasks_cli.py` exécutée par `tasks.py`), à la
répartition de `main` (lue par AST) et au comportement de la CLI, en processus et en
sous-processus, sur des racines et un environnement jetables.

  W1  verbes du parseur = verbes du contrat, dans les deux sens.
  W2  positionnels et options de chaque verbe, options globales comprises : drapeaux, action,
      requis, choix, nargs, type, défaut LITTÉRAL ; `--root` porte un défaut SYMBOLIQUE
      (`CLAUDE_PROJECT_DIR`, puis `.`), extrait variable RETIRÉE puis posée (C6).
  W3  le bloc GEN du MD = le rendu du JSON ; à l'écart, le bloc attendu est imprimé.
  W4  `mutant` = le verbe draine le rejeu V3 (ensemble `mutating` de `main`) : `replay_sync`
      remplacé par un enregistreur, chaque verbe joué en processus (C1).
  W5  rc 2 : option inconnue pour chaque verbe (en processus), argv COMPLET (positionnels et
      options requis fournis) et `unrecognized arguments: --zz-inconnu` exigé sur stderr —
      argparse refuse d'abord un positionnel manquant, l'option ne serait pas atteinte ;
      identifiant inconnu, argv COMPLET, en sous-processus : `unknown task id` sur TOUT stderr
      et une ligne `^tasks.py: ` (C8 — le bruit `event_store:` peut précéder).
  W6  rc 1 : chaque verbe dont le contrat porte 1 le rend RÉELLEMENT, avec un jumeau rc 0
      (C2, C10) ; plus le refus de pont injecté de `replay-sync`, en processus.
  W7  AST de `main` : verbes dont la branche peut rendre 1 (`return 1`, `return <nom>`,
      `rc_verbe = …1…`) = l'ensemble `rc:1` du contrat (C4).
  W8  sorties stables ; `tasks.py` sans verbe = l'aide en rc 0 ; aucun verbe ne retombe sur
      l'aide générale (AST de la répartition ET comportement) ; exceptions R2 du MD (C9).
  W9  les jetons de `deps-ready` (`DEPS_READY_JETONS`, S-01M4Z5VMP5E9YN8T6EMDTBAF0T) sont
      ceux de `definitions["deps-ready"]`, dans l'ordre de précédence, et chacun est au MD.
  M*  mutants EN MÉMOIRE (parseur, JSON, MD, source de `main`, observations) : chacun doit
      rendre son comparateur NON VIDE. Un mutant vert dirait un critère creux.

Environnement des sous-processus ET des jeux en processus (`patch.dict(..., clear=True)`) :
LISTE BLANCHE (C7), `HOME`, `CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR` jetables,
`CADRE_PROJECT_ROOT` ÉPINGLÉ sur la racine jetable (hérité, il braquerait le rejeu V3 sur le
vrai dépôt), `CLAUDE_PROJECT_DIR` absent. Témoin : un `HOME` et une variable plantés dans
l'environnement hôte ne sont pas vus par `main` (`ecarts_env`).

Hors pytest :
  python3 .agents/evals/test_tasks_cli_contract.py --squelette   # surface extraite + champs
        sémantiques recopiés du JSON courant (`A_REMPLIR` pour un verbe neuf)
  python3 .agents/evals/test_tasks_cli_contract.py --tableau     # le bloc GEN attendu du MD
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TASKS_PY = ROOT / ".agents" / "bin" / "tasks.py"
SCRIPT_COMMIT = ROOT / ".agents" / "bin" / "post-task-done-index.sh"
CONTRAT_JSON = ROOT / ".agents" / "ref" / "TASKS_CLI_CONTRACT.json"
CONTRAT_MD = ROOT / ".agents" / "ref" / "TASKS_CLI_CONTRACT.md"
GEN_DEBUT = "<!-- TASKS_CLI:GEN:verbes:debut -->"
GEN_FIN = "<!-- TASKS_CLI:GEN:verbes:fin -->"
ENV_RACINE = "CLAUDE_PROJECT_DIR"
SENTINELLE = "sentinelle-contrat-cli"
ID = "T-99999999"
ENTETE_AIDE = "[--root ROOT] [--statusline]"
STATUTS = ("promis", "noyau")
MUTANTS = ("oui", "non", "sauf --dry-run")
CLES_RACINE = {"schema", "outil", "parseur", "repartition", "doc", "banc", "definitions",
               "non_mutants_qui_ecrivent", "jetons_commit", "options_globales", "verbes"}
CLES_VERBE = {"statut", "mutant", "rc", "positionnels", "options"}
CLES_SORTIE = {"libelle", "derniere_ligne", "json", "jeton", "prefixe"}
# S-01M4JPBTF82G4PW7DDDYRSVZC1 (« B + reopen ») et l'arbitrage du plan (`fournee` noyau,
# candidat public, admission tranchée par T-00000797 / BK-159) : 23 promis, 6 noyau ;
# `livraison` (T-01M4WTYSCEYHC6KZF2DC1PXBRN, S-01M4X6K3JRR90VVWR4AFHT983G) entre au noyau : 7.
# `deps-ready` (T-01M4Z5VJ1DYQZM67AYHTACKFTA, S-01M4Z5VMP5E9YN8T6EMDTBAF0T) entre aux promis : 24.
# `responsable` (T-01M54GEHJBGA5996W0T48JXNQ4, E-48 D2, plan approuvé S-01M59FRJF58PVJ3DQ5NF5NYQ6T) : 25.
# `limite`, `conso`, `depassements` (T-01M54GEMCH3JWA95G61N2J70KS, E-48 C4, plan approuvé S-01M5AQM5542XTR0CGVJ7H5FJN8) : 28.
# `focus` et `review-scope` (T-01M5F7286N1EYGXAXA5244X86B, S-01M5E50AJX9V9AP8A8VBBHS6B4) entrent au noyau : 9 ;
# jira-import et jira-claim sont noyau par le plan TVRD : 11.
# `chrono` (T-01M5HST80E30DFMV3S7WM68Q7N, plan approuvé S-01M5JKBMKPNNMENNYTSAMGYQ0X, develop) : +1 ;
# `limite`, `conso`, `depassements` (T-01M54GEMCH3JWA95G61N2J70KS, branche reprise/2026-10-20) : +3 ;
# réunis à la fusion du 2026-10-25 : 25 + 1 + 3 = 29.
NOYAU_DECIDE = frozenset({"epic", "epic-new", "epic-list", "reassign", "delete", "fournee", "livraison",
                          "focus", "review-scope", "jira-import", "jira-claim"})
PROMIS_COMPTE = 29

# W4 : un argv COMPLET par verbe. Un identifiant inconnu fait échouer le verbe APRÈS le
# drain d'avant (rc 2), ce qui suffit à observer le drain sans préparer d'état.
SCENARIOS: dict[str, list[str]] = {
    "new": ["new", "banc contrat", "--pas-un-defaut", "banc"],
    "epic-new": ["epic-new", "E-99", "banc"],
    "epic": ["epic", ID, "--retirer"],
    "epic-list": ["epic-list"],
    "start": ["start", ID],
    "jira-import": ["jira-import", "--project", "PROJ"],
    "jira-claim": ["jira-claim", "--retry", ID],
    "stage": ["stage", ID, "banc"],
    "block": ["block", ID],
    "unblock": ["unblock", ID],
    "done": ["done", ID, "--raison", "banc"],
    "reopen": ["reopen", ID, "--raison", "banc"],
    "binome-purge": ["binome-purge", ID],
    "retitle": ["retitle", ID, "banc"],
    "reassign": ["reassign", ID, "banc"],
    "regroup": ["regroup", ID, "banc"],
    "responsable": ["responsable", ID, "banc"],
    "limite": ["limite", ID, "--jetons", "1k"],
    "conso": ["conso", ID, "1k"],
    "depassements": ["depassements"],
    "writeset": ["writeset", ID, "--clear"],
    "direct": ["direct", ID],
    "retour": ["retour", ID, "--base", "0000000", "--branche", "banc"],
    "livraison": ["livraison", ID, "--branche", "banc"],
    "fournee": ["fournee", ID],
    "depends": ["depends", ID, "--clear"],
    "depends-show": ["depends-show", ID],
    "deps-ready": ["deps-ready", ID],
    "chrono": ["chrono", ID, "step", "--etape", "dev", "--phase", "begin"],
    "parallel": ["parallel", ID, "T-99999998"],
    "focus": ["focus", ID],
    "review-scope": ["review-scope", ID],
    "delete": ["delete", ID],
    "purge": ["purge"],
    "list": ["list"],
    "render": ["render"],
    "replay-sync": ["replay-sync"],
    "commit-stores": ["commit-stores"],
    "commit-run-exports": ["commit-run-exports"],
    "cible-check": ["cible-check", "absent.md"],
}
LISTE_PAR_ID = ("--task", "--blocked-by", "--depends-on")
# W5 : l'argv COMPLET de `SCENARIOS` porte l'option inconnue jusqu'à argparse ; sans lui, 24
# verbes sur 31 s'arrêtent au positionnel manquant (mesuré, Python 3.14.7, après `deps-ready`)
# et l'option n'est jamais atteinte.
OPTION_INCONNUE_REFUSEE = "unrecognized arguments: --zz-inconnu"
# C7 en processus : plantés dans l'environnement HÔTE, ils ne doivent pas atteindre `main`.
HOME_HOTE = "/maison-hote-sentinelle-contrat-cli"
FUITE_HOTE = "CONTRAT_CLI_FUITE_HOTE"

# W6 : (scénario qui rend 1, jumeau qui rend 0), par verbe.
PAIRES_RC1 = {
    "commit-stores": ("commit_stores_sans_script", "commit_stores_script_sans_git"),
    "commit-run-exports": ("commit_run_exports_sans_script", "commit_run_exports_script_sans_git"),
    "retour": ("retour_git_refus", "retour_git_ok"),
    "cible-check": ("cible_check_sans_cible", "cible_check_avec_cible"),
    "replay-sync": ("replay_sync_refus", "replay_sync"),
    "deps-ready": ("deps_ready_ouvert", "deps_ready_clos"),
    "depassements": ("depassements_depasse", "depassements_rien"),
}
# Ce que chaque scénario en sous-processus doit rendre : (rc, flux, motif cherché).
ATTENDUS = {
    "nu": (0, "out", r"\Ausage: "),
    "usage_list": (2, "err", r"(?m)^usage: "),
    "new": (0, "out", r"(?m)^TASKS: T-[0-9A-Z]+ → pending$"),
    "list_json": (0, "out", r"\A\["),
    "list_json_vide": (0, "err", r"(?m)^tasks\.py: no task matching "),
    "render": (0, "out", r"(?m)^TASKS\.md regenerated"),
    "replay_sync": (0, "out", r"(?m)^TASKS: replayed \d+ sync intent\(s\)$"),
    "replay_sync_refus": (1, "err", r"(?m)^TASKS: pont V3 REFUS"),
    "statusline": (0, "out", r"\S"),
    "commit_stores_sans_script": (1, "out", r"(?m)^failed$"),
    "commit_run_exports_sans_script": (1, "out", r"(?m)^failed$"),
    "commit_stores_script_sans_git": (0, "out", r"(?m)^nothing$"),
    "commit_run_exports_script_sans_git": (0, "out", r"(?m)^nothing$"),
    "retour_sans_git": (1, "out", r"(?m)^RETOUR: refus$"),
    "retour_git_refus": (1, "out", r"(?m)^RETOUR: refus$"),
    "retour_git_ok": (0, "out", r"(?m)^RETOUR: ok$"),
    "cible_check_sans_cible": (1, "out", r"\Acible-check: "),
    "cible_check_avec_cible": (0, "out", r"\Acible-check: "),
    "cible_check_sans_spec": (2, "err", r"\Acible-check: "),
    "deps_ready_ouvert": (1, "out", r"\Adeps-ready: AMONT_OUVERT\n"),
    "deps_ready_clos": (0, "out", r"\Adeps-ready: AMONT_CLOS\n"),
    "depassements_rien": (0, "out", r"\ALIMITE: aucune tâche au-delà de sa limite"),
    "depassements_depasse": (1, "out", r"(?m)^LIMITE-DEPASSEE: T-[0-9A-Z]+ délai : échéance "
                                       r"2000-01-01T00:00:00Z dépassée de \d+h\d\d$"),
    "depassements_json_vide": (0, "out", r"\A\[\]\n\Z"),
    "depassements_json": (1, "out", r'"type": "delai"'),
}
# W8 : les scénarios où chaque sortie déclarée est éprouvée.
SOURCES_SORTIES = {
    "new": ("new",),
    "list": ("list_json", "list_json_vide"),
    "retour": ("retour_sans_git", "retour_git_refus", "retour_git_ok"),
    "commit-stores": ("commit_stores_sans_script", "commit_stores_script_sans_git"),
    "commit-run-exports": ("commit_run_exports_sans_script", "commit_run_exports_script_sans_git"),
    "replay-sync": ("replay_sync",),
    "render": ("render",),
    "cible-check": ("cible_check_sans_cible", "cible_check_avec_cible"),
    "deps-ready": ("deps_ready_ouvert", "deps_ready_clos"),
    "depassements": ("depassements_json_vide", "depassements_json"),
}
# T-01M5QC86XNEJ5NEX6DGZJ0AJZ5, annexe § A1 — liste FERMÉE : anglais en tête -> (ancien, verbes porteurs).
DRAPEAUX_ANGLAIS: dict[str, tuple[str, tuple[str, ...]]] = {
    "--branch": ("--branche", ("retour", "livraison")), "--workstream": ("--chantier", ("new", "list")),
    "--step": ("--etape", ("chrono",)), "--require": ("--exiger", ("commit-stores", "commit-run-exports")),
    "--replace": ("--maj", ("epic-new",)), "--measure": ("--mesure", ("new",)),
    "--motive": ("--motif", ("new", "depends")), "--not-a-defect": ("--pas-un-defaut", ("new",)),
    "--cap": ("--plafond", ("purge",)), "--priority": ("--priorite", ("epic-new",)),
    "--reason": ("--raison", ("done", "reopen")), "--takeover": ("--reprise", ("start", "fournee")),
    "--assignee": ("--responsable", ("new", "list")),
    "--remove": ("--retirer", ("epic", "direct", "livraison", "depends")),
    "--remove-pilot-order": ("--retirer-ordre-pilote", ("depends",)), "--risk": ("--risque", ("epic-new",)),
    "--without-review": ("--sans-binome", ("done",)),
    "--without-chain": ("--sans-chaine", ("start", "fournee")),
    "--without-target": ("--sans-cible", ("start", "done", "fournee")),
    "--without-deps": ("--sans-dependances", ("start", "done", "fournee")),
    "--without-reblock": ("--sans-rebloquer", ("reopen",)),
    "--without-claim": ("--sans-revendication", ("start", "fournee")),
    "--attempt": ("--tentative", ("chrono",)), "--wave": ("--vague", ("epic-new",)), "--into": ("--vers", ("retour",)),
}
VERBES_ANGLAIS = {"batch": "fournee", "return": "retour", "delivery": "livraison", "assignee": "responsable",
                  "target-check": "cible-check", "review-purge": "binome-purge"}
METAVARS_ANGLAIS = {("epic-new", "titre"): "TITLE", ("regroup", "chantier"): "WORKSTREAM",
                    ("responsable", "responsable"): "ASSIGNEE"}
LISTE_BLANCHE = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP",
                 "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")


@dataclass(frozen=True)
class Jeu:
    rc: int
    out: str
    err: str
    drains: int = -1


# --------------------------------------------------------------------------- chargement
_TASKS: list[Any] = []


def charger_tasks() -> Any:
    """`tasks.py` chargé UNE fois, sous un nom propre au banc, enregistré AVANT `exec_module`."""
    if not _TASKS:
        nom = "tasks_contrat_cli_banc"
        spec = importlib.util.spec_from_file_location(nom, TASKS_PY)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"banc : {TASKS_PY} ne se charge pas")
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        spec.loader.exec_module(module)
        _TASKS.append(module)
    return _TASKS[0]


def construire_parseur(valeur_env: str | None = None) -> argparse.ArgumentParser:
    """Le parseur réel, `CLAUDE_PROJECT_DIR` retiré (ou posé sur `valeur_env`) le temps de le bâtir."""
    module = charger_tasks()
    with mock.patch.dict(os.environ):
        os.environ.pop(ENV_RACINE, None)
        if valeur_env is not None:
            os.environ[ENV_RACINE] = valeur_env
        return module._construire_parseur([])


def lire_contrat() -> dict[str, Any]:
    return json.loads(CONTRAT_JSON.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- extraction
def _sous_parseurs(ap: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in ap._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _action(parseur: argparse.ArgumentParser, nom: str) -> argparse.Action:
    return next(a for a in parseur._actions if nom in a.option_strings or (not a.option_strings and a.dest == nom))


def _decrire(ap: argparse.ArgumentParser, ap_env: argparse.ArgumentParser) -> tuple[list, dict]:
    noms = {cls: nom for nom, cls in ap._registries["action"].items() if isinstance(nom, str)}
    defaut_env = {a.dest: a.default for a in ap_env._actions}
    positionnels: list[dict[str, Any]] = []
    options: dict[str, dict[str, Any]] = {}
    for action in ap._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        choix = list(action.choices) if action.choices is not None else None
        if not action.option_strings:
            positionnels.append({"nom": action.dest, "nargs": action.nargs, "choix": choix})
            continue
        defaut: Any = action.default
        if defaut_env.get(action.dest, defaut) != defaut:  # lu à la construction : symbolique (C6)
            defaut = {"env": ENV_RACINE, "repli": defaut}
        options[" ".join(action.option_strings)] = {
            "action": noms.get(type(action), type(action).__name__), "requis": bool(action.required),
            "choix": choix, "nargs": action.nargs,
            "type": getattr(action.type, "__name__", None) if action.type is not None else None,
            "defaut": defaut,
        }
    return positionnels, options


def replier_alias(choix: dict[str, argparse.ArgumentParser]) -> dict[str, tuple[argparse.ArgumentParser, str | None]]:
    """T-01M5QC86XNEJ5NEX6DGZJ0AJZ5 : `add_parser(<anglais>, aliases=[<ancien>])` met DEUX noms sur le
    MÊME sous-parseur. Le verbe du contrat est celui que `main` répartit, `set_defaults(cmd=…)` (le
    nom tapé sinon) ; `alias` = l'autre nom, l'anglais en tête. Sans `set_defaults`, les deux noms
    restent deux verbes sans alias, et W2 le dit."""
    replies: dict[str, tuple[argparse.ArgumentParser, str | None]] = {}
    for nom, sp in choix.items():
        cle = sp._defaults.get("cmd", nom)
        sp_vu, alias = replies.get(cle, (sp, None))
        replies[cle] = (sp_vu, alias if nom == cle else nom)
    return replies


def extraire_surface(ap: argparse.ArgumentParser | None = None,
                     ap_env: argparse.ArgumentParser | None = None) -> dict[str, Any]:
    """La FORME de la CLI : options globales, puis positionnels et options de chaque verbe."""
    ap = ap if ap is not None else construire_parseur()
    ap_env = ap_env if ap_env is not None else construire_parseur(SENTINELLE)
    positionnels_globaux, globales = _decrire(ap, ap_env)
    sous_env = _sous_parseurs(ap_env)
    verbes = {}
    for verbe, (sp, alias) in replier_alias(_sous_parseurs(ap)).items():
        positionnels, options = _decrire(sp, sous_env.get(verbe, sp))
        verbes[verbe] = ({"alias": alias} if alias else {}) | {"positionnels": positionnels, "options": options}
    surface = {"positionnels_globaux": positionnels_globaux, "options_globales": globales, "verbes": verbes}
    return json.loads(json.dumps(surface))  # tuples -> listes : la forme du JSON relu


# --------------------------------------------------------------------------- W1, W2
def _noms(verbes: dict[str, Any]) -> list[str]:
    """Chaque nom ACCEPTÉ : le verbe, puis son alias s'il en porte un."""
    return [n for v, d in verbes.items() for n in (v, d.get("alias")) if n]


def ecarts_verbes(surface: dict[str, Any], contrat: dict[str, Any]) -> list[str]:
    p, c = _noms(surface["verbes"]), _noms(contrat["verbes"])
    return ([f"W1 verbe au parseur, absent du contrat : {v}" for v in p if v not in c]
            + [f"W1 verbe au contrat, absent du parseur : {v}" for v in c if v not in p])


def _ecarts_options(ou: str, s: dict[str, Any], c: dict[str, Any]) -> list[str]:
    out = []
    for drapeau in sorted(set(s) | set(c)):
        if drapeau not in c:
            out.append(f"W2 {ou} {drapeau} : au parseur, absente du contrat")
        elif drapeau not in s:
            out.append(f"W2 {ou} {drapeau} : au contrat, absente du parseur")
        elif s[drapeau] != c[drapeau]:
            out.append(f"W2 {ou} {drapeau} : parseur {s[drapeau]} != contrat {c[drapeau]}")
    return out


def ecarts_forme(surface: dict[str, Any], contrat: dict[str, Any]) -> list[str]:
    out = [f"W2 positionnel global inattendu : {p}" for p in surface["positionnels_globaux"]]
    out += _ecarts_options("(global)", surface["options_globales"], contrat["options_globales"])
    for verbe, s in surface["verbes"].items():
        c = contrat["verbes"].get(verbe)
        if c is None:
            continue  # W1 le dit
        if s.get("alias") != c.get("alias"):
            out.append(f"W2 {verbe} alias : parseur {s.get('alias')!r} != contrat {c.get('alias')!r}")
        if s["positionnels"] != c.get("positionnels"):
            out.append(f"W2 {verbe} positionnels : parseur {s['positionnels']} != contrat {c.get('positionnels')}")
        out += _ecarts_options(verbe, s["options"], c.get("options", {}))
    return out


# --------------------------------------------------------------------------- schéma, statut
def ecarts_schema(contrat: dict[str, Any]) -> list[str]:
    out = []
    if set(contrat) != CLES_RACINE:
        out.append(f"clés racine {sorted(set(contrat) ^ CLES_RACINE)} hors schéma")
    verbes = contrat.get("verbes", {})
    for verbe, d in verbes.items():
        cles = set(d) - {"sorties", "alias"}
        if cles != CLES_VERBE:
            out.append(f"{verbe} : clés {sorted(cles ^ CLES_VERBE)} hors schéma")
        if "alias" in d and (not isinstance(d["alias"], str) or not d["alias"] or d["alias"] in verbes):
            out.append(f"{verbe} : alias {d['alias']!r} — un nom non vide, qui n'est pas un verbe du contrat")
        if d.get("statut") not in STATUTS:
            out.append(f"{verbe} : statut {d.get('statut')!r} hors {STATUTS}")
        if d.get("mutant") not in MUTANTS:
            out.append(f"{verbe} : mutant {d.get('mutant')!r} hors {MUTANTS}")
        rc = d.get("rc", [])
        if rc != sorted(set(rc)) or not {0, 2} <= set(rc) or not set(rc) <= {0, 1, 2}:
            out.append(f"{verbe} : rc {rc} — attendu une liste triée de {{0, 1, 2}} portant 0 et 2")
        sortie = d.get("sorties")
        if sortie is not None and (not set(sortie) <= CLES_SORTIE or "libelle" not in sortie
                                   or len(set(sortie) - {"libelle"}) != 1):
            out.append(f"{verbe} : sorties {sorted(sortie)} — un libellé et UNE clé de contrôle")
    for verbe in contrat.get("non_mutants_qui_ecrivent", {}):
        if verbes.get(verbe, {}).get("mutant") != "non":
            out.append(f"{verbe} : nommé parmi les non-mutants qui écrivent, mutant != non (C1)")
    return out


def ecarts_statut(contrat: dict[str, Any]) -> list[str]:
    noyau = {v for v, d in contrat["verbes"].items() if d.get("statut") == "noyau"}
    promis = [v for v, d in contrat["verbes"].items() if d.get("statut") == "promis"]
    out = []
    if noyau != NOYAU_DECIDE:
        out.append(f"noyau {sorted(noyau)} != décidé {sorted(NOYAU_DECIDE)}")
    if len(promis) != PROMIS_COMPTE:
        out.append(f"{len(promis)} promis, {PROMIS_COMPTE} décidés")
    return out


# --------------------------------------------------------------------------- W3 : rendu
def _cellule(texte: str) -> str:
    return texte.replace("|", "\\|")


def _positionnels(pos: list[dict[str, Any]]) -> str:
    suffixes = {None: "", "?": "?", "*": "*", "+": "+"}
    return " ".join(f"`<{p['nom']}>{suffixes.get(p['nargs'], '×' + str(p['nargs']))}`" for p in pos) or "—"


def _options(opts: dict[str, Any]) -> str:
    parts = []
    for drapeau, f in opts.items():
        txt = drapeau + ("{" + ",".join(map(str, f["choix"])) + "}" if f["choix"] else "")
        parts.append(f"`{txt}`" + ("★" if f["requis"] else ""))
    return " ".join(parts) or "—"


def rendre_bloc(contrat: dict[str, Any]) -> str:
    lignes = ["| verbe | statut | mutant | rc | positionnels | options (★ requise) | sortie stable |",
              "|---|---|---|---|---|---|---|"]
    for verbe, d in contrat["verbes"].items():
        sortie = d.get("sorties", {}).get("libelle", "—")
        nom = f"`{d['alias']}` (`{verbe}`)" if d.get("alias") else f"`{verbe}`"
        lignes.append(f"| {nom} | {d['statut']} | {d['mutant']} | {', '.join(map(str, d['rc']))} | "
                      f"{_positionnels(d['positionnels'])} | {_cellule(_options(d['options']))} | {_cellule(sortie)} |")
    v = contrat["verbes"]
    compte = {s: sum(1 for d in v.values() if d["statut"] == s) for s in STATUTS}
    mut = {m: sum(1 for d in v.values() if d["mutant"] == m) for m in MUTANTS}
    ecrivent = ", ".join(f"`{n}`" for n in contrat["non_mutants_qui_ecrivent"])
    rc1 = [n for n, d in v.items() if 1 in d["rc"]]
    globales = ", ".join(f"`{g}`" for g in contrat["options_globales"])
    lignes += ["", f"{len(v)} verbes au contrat : {compte['promis']} `promis`, {compte['noyau']} `noyau`. "
               f"Options globales : {globales}. Rejeu V3 (`mutant`) : {mut['oui']} `oui`, "
               f"{mut['sauf --dry-run']} `sauf --dry-run`, {mut['non']} `non` — dont "
               f"{len(contrat['non_mutants_qui_ecrivent'])} qui écrivent quand même : {ecrivent}. "
               f"rc 1 possible : {len(rc1)} verbes ({', '.join(f'`{n}`' for n in rc1)})."]
    return "\n".join(lignes)


def ecarts_md(md: str, contrat: dict[str, Any]) -> list[str]:
    if md.count(GEN_DEBUT) != 1 or md.count(GEN_FIN) != 1:
        return ["W3 marqueurs GEN absents ou doublés dans le MD"]
    present = md.split(GEN_DEBUT, 1)[1].split(GEN_FIN, 1)[0].strip("\n")
    attendu = rendre_bloc(contrat)
    return [] if present == attendu else ["W3 le bloc GEN du MD diffère du rendu du JSON — attendu :\n" + attendu]


# --------------------------------------------------------------------------- W7, W8 : AST
def _main_ast(source: str) -> ast.FunctionDef:
    for noeud in ast.parse(source).body:
        if isinstance(noeud, ast.FunctionDef) and noeud.name == "main":
            return noeud
    raise AssertionError("banc : `main` absente de tasks.py")


def _verbe_teste(test: ast.expr) -> str | None:
    """`args.cmd == "<verbe>"` nu (une conjonction n'est pas une branche de répartition)."""
    if (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and isinstance(test.left, ast.Attribute) and test.left.attr == "cmd"
            and isinstance(test.left.value, ast.Name) and test.left.value.id == "args"
            and isinstance(test.comparators[0], ast.Constant) and isinstance(test.comparators[0].value, str)):
        return test.comparators[0].value
    return None


def branches_de_main(source: str) -> dict[str, list[ast.stmt]]:
    branches: dict[str, list[ast.stmt]] = {}
    for noeud in ast.walk(_main_ast(source)):
        if isinstance(noeud, ast.If) and (verbe := _verbe_teste(noeud.test)) is not None:
            branches.setdefault(verbe, noeud.body)
    return branches


def _est_un(noeud: ast.AST) -> bool:
    return isinstance(noeud, ast.Constant) and type(noeud.value) is int and noeud.value == 1


def _peut_rendre_1(corps: list[ast.stmt]) -> bool:
    for instr in corps:
        for n in ast.walk(instr):
            if isinstance(n, ast.Return) and n.value is not None and (_est_un(n.value) or isinstance(n.value, ast.Name)):
                return True
            if (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id == "rc_verbe" for c in n.targets)
                    and any(_est_un(c) for c in ast.walk(n.value))):
                return True
    return False


def ecarts_rc1_ast(contrat: dict[str, Any], source: str) -> list[str]:
    ast_rc1 = {v for v, corps in branches_de_main(source).items() if _peut_rendre_1(corps)}
    c_rc1 = {v for v, d in contrat["verbes"].items() if 1 in d["rc"]}
    return ([f"W7 {v} : sa branche de main peut rendre 1, absent du contrat" for v in sorted(ast_rc1 - c_rc1)]
            + [f"W7 {v} : rc 1 au contrat, aucune branche de main ne le rend" for v in sorted(c_rc1 - ast_rc1)])


def ecarts_repartition(verbes: list[str], source: str) -> list[str]:
    reparti = set(branches_de_main(source))
    return ([f"W8 {v} : aucune branche dans main, retombe sur l'aide générale" for v in verbes if v not in reparti]
            + [f"W8 {v} : branche dans main, verbe absent du parseur" for v in sorted(reparti - set(verbes))])


# --------------------------------------------------------------------------- W4, W5 en processus
def jouer_en_processus(racine: Path, env: dict[str, str], argv: list[str], refus_pont: bool = False,
                       vu: dict[str, str] | None = None) -> Jeu:
    """`main` en processus, `replay_sync` remplacé par un enregistreur ; `drains` = appels hors `replay-sync`.

    `os.environ` est REMPLACÉ par `env` (`clear=True`) : rien de l'hôte n'est hérité. `vu`, s'il est
    fourni, reçoit l'environnement tel que `main` le trouve à son entrée (témoin de C7).
    """
    module = charger_tasks()
    appels: list[dict[str, Any] | None] = []

    def enregistreur(root: Any, *, pont_commande: dict[str, Any] | None = None) -> int:
        appels.append(dict(pont_commande) if pont_commande is not None else None)
        if refus_pont and pont_commande is not None:
            pont_commande["refus"] = True
        return 0

    sortie, erreur = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(module, "replay_sync", enregistreur), \
            contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
        os.environ.pop(ENV_RACINE, None)
        if vu is not None:
            vu.update(os.environ)
        try:
            rc = module.main(["--root", str(racine), *argv])
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    drains = sum(1 for a in appels if a is None or not a.get("explicite"))
    return Jeu(rc, sortie.getvalue(), erreur.getvalue(), drains)


def mutants_observes(jeux: dict[str, Jeu], surface: dict[str, Any]) -> dict[str, str]:
    obs = {}
    for verbe, forme in surface["verbes"].items():
        jeu = jeux.get(verbe)
        if jeu is None:
            obs[verbe] = "non joué"
            continue
        sec = jeux.get(verbe + " --dry-run") if "--dry-run" in forme["options"] else None
        obs[verbe] = ("sauf --dry-run" if jeu.drains and sec is not None and not sec.drains
                      else "oui" if jeu.drains else "non")
    return obs


def ecarts_mutant(contrat: dict[str, Any], obs: dict[str, str]) -> list[str]:
    return [f"W4 {v} : observé {obs.get(v)!r}, contrat {d['mutant']!r}"
            for v, d in contrat["verbes"].items() if obs.get(v) != d["mutant"]]


def ecarts_usage(verbes: list[str], usage: dict[str, Jeu]) -> list[str]:
    """W5 : l'option inconnue est ATTEINTE — un refus de positionnel manquant ne compte pas."""
    out = []
    for verbe in verbes:
        jeu = usage.get(verbe)
        if (jeu is None or jeu.rc != 2 or not re.search(r"(?m)^usage: ", jeu.err)
                or OPTION_INCONNUE_REFUSEE not in jeu.err):
            out.append(f"W5 {verbe} --zz-inconnu : attendu rc 2, `usage:` et "
                       f"`{OPTION_INCONNUE_REFUSEE}` sur stderr, obtenu {jeu}")
    return out


def ecarts_env(vu: dict[str, str], env: dict[str, str]) -> list[str]:
    """C7 en processus : `main` voit EXACTEMENT l'environnement du banc, rien d'hérité de l'hôte."""
    return ([f"env : {k} hérité de l'hôte" for k in sorted(set(vu) - set(env))]
            + [f"env : {k}={vu.get(k)!r}, attendu {v!r}" for k, v in sorted(env.items())
               if k != ENV_RACINE and vu.get(k) != v])


# --------------------------------------------------------------------------- sous-processus
def env_banc(base: Path, racine: Path) -> dict[str, str]:
    """LISTE BLANCHE (C7) ; `CADRE_PROJECT_ROOT` épinglé ; `CLAUDE_PROJECT_DIR` absent."""
    env = {k: os.environ[k] for k in LISTE_BLANCHE if k in os.environ}
    maison = base / "maison"
    maison.mkdir(exist_ok=True)
    (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@example.com\n", encoding="utf-8")
    env.update(HOME=str(maison), USERPROFILE=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"),
               GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(base), CADRE_STATE_DIR=str(base / "etat"),
               AGENTS_EVENTS_DIR=str(base / "evenements"), CADRE_PROJECT_ROOT=str(racine),
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


def jouer_sous_processus(racine: Path, env: dict[str, str], argv: list[str]) -> Jeu:
    r = subprocess.run([sys.executable, "-B", str(TASKS_PY), "--root", str(racine), *argv],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, cwd=str(racine), timeout=120, check=False)
    return Jeu(r.returncode, r.stdout, r.stderr)


def git(racine: Path, env: dict[str, str], *args: str) -> str:
    """git dans une racine du banc ; un échec est un DÉFAUT DU BANC (`RuntimeError`)."""
    r = subprocess.run(["git", *args], cwd=str(racine), env=env, capture_output=True, text=True,
                       timeout=120, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"banc : git {' '.join(args)} en échec : {r.stderr.strip()}")
    return r.stdout.strip()


def scenarios_id_inconnu() -> dict[str, list[str]]:
    jeux = {f"inconnu {v}": argv for v, argv in SCENARIOS.items() if ID in argv}
    jeux.update({f"inconnu list {o}": ["list", o, ID] for o in LISTE_PAR_ID})
    return jeux


def ecarts_id_inconnu(surface: dict[str, Any], obs: dict[str, Jeu]) -> list[str]:
    a_id = [v for v, d in surface["verbes"].items() if any(p["nom"] in ("tid", "tids") for p in d["positionnels"])]
    labels = [f"inconnu {v}" for v in a_id] + [f"inconnu list {o}" for o in LISTE_PAR_ID]
    out = []
    for label in labels:
        jeu = obs.get(label)
        if jeu is None:
            out.append(f"W5 {label} : non joué")
        elif jeu.rc != 2 or "unknown task id" not in jeu.err or not re.search(r"(?m)^tasks\.py: ", jeu.err):
            out.append(f"W5 {label} : attendu rc 2, `unknown task id` et une ligne `tasks.py: ` sur stderr — "
                       f"rc {jeu.rc}, stderr {jeu.err[-300:]!r}")
    return out


def ecarts_attendus(obs: dict[str, Jeu]) -> list[str]:
    out = []
    for nom, (rc, flux, motif) in ATTENDUS.items():
        jeu = obs.get(nom)
        if jeu is None:
            out.append(f"{nom} : non joué")
        elif jeu.rc != rc or not re.search(motif, jeu.out if flux == "out" else jeu.err):
            out.append(f"{nom} : attendu rc {rc} et /{motif}/ sur std{flux} — rc {jeu.rc}, "
                       f"stdout {jeu.out[-200:]!r}, stderr {jeu.err[-200:]!r}")
    statusline = obs.get("statusline")
    if statusline is not None and "unknown task id" in statusline.err:
        out.append("statusline : le verbe a tourné, --statusline devait l'avaler")
    return out


def ecarts_rc1(contrat: dict[str, Any], obs: dict[str, Jeu]) -> list[str]:
    rc1 = {v for v, d in contrat["verbes"].items() if 1 in d["rc"]}
    out = [f"W6 {v} : rc 1 au contrat, aucun scénario du banc ne le rend" for v in sorted(rc1 - set(PAIRES_RC1))]
    out += [f"W6 {v} : rend 1 au banc, 1 absent du contrat" for v in sorted(set(PAIRES_RC1) - rc1)]
    for verbe, (un, zero) in PAIRES_RC1.items():
        for nom, rc in ((un, 1), (zero, 0)):
            jeu = obs.get(nom)
            if jeu is None or jeu.rc != rc:
                out.append(f"W6 {verbe} {nom} : attendu rc {rc}, obtenu {None if jeu is None else jeu.rc}")
    return out


def ecarts_sorties(contrat: dict[str, Any], obs: dict[str, Jeu]) -> list[str]:
    jetons = contrat["jetons_commit"]
    out = []
    for verbe, d in contrat["verbes"].items():
        sortie = d.get("sorties")
        if sortie is None:
            continue
        sources = SOURCES_SORTIES.get(verbe)
        if not sources:
            out.append(f"W8 {verbe} : sortie déclarée, jamais éprouvée par le banc")
            continue
        for nom in sources:
            jeu = obs.get(nom)
            if jeu is None:
                out.append(f"W8 {verbe} {nom} : non joué")
                continue
            lignes = [ligne for ligne in jeu.out.splitlines() if ligne.strip()]
            derniere = lignes[-1] if lignes else ""
            if "derniere_ligne" in sortie and not re.fullmatch(sortie["derniere_ligne"], derniere):
                out.append(f"W8 {verbe} {nom} : dernière ligne {derniere!r} hors /{sortie['derniere_ligne']}/")
            if sortie.get("json"):
                try:
                    valeur = json.loads(jeu.out)
                except ValueError:
                    valeur = None
                if not isinstance(valeur, list):
                    out.append(f"W8 {verbe} {nom} : stdout n'est pas un tableau JSON")
            if sortie.get("jeton") and not (derniere in jetons["litteraux"]
                                            or derniere.startswith(tuple(jetons["prefixes"]))):
                out.append(f"W8 {verbe} {nom} : jeton {derniere!r} hors de l'ensemble déclaré")
            if "prefixe" in sortie and not jeu.out.startswith(sortie["prefixe"]):
                out.append(f"W8 {verbe} {nom} : stdout n'ouvre pas par {sortie['prefixe']!r}")
    return out


def ecarts_jetons_deps_ready(jetons: tuple[str, ...], contrat: dict[str, Any], md: str) -> list[str]:
    """W9 : le REGISTRE des jetons de `deps-ready` — le contrat les nomme TOUS, dans l'ordre de
    `DEPS_READY_JETONS` (sa précédence), et le MD aussi. Un lanceur qui perd REPRISE_DITE lirait
    un jeton que ni le contrat ni sa doc ne déclarent."""
    texte = contrat.get("definitions", {}).get("deps-ready", "")
    trouves = sorted((m.start(), m.group(0)) for m in re.finditer(r"\b[A-Z][A-Z_]+\b", texte)
                     if m.group(0) in jetons)
    ordre = list(dict.fromkeys(j for _p, j in trouves))
    out = [] if ordre == list(jetons) else [f"W9 definitions[deps-ready] : {ordre} != {list(jetons)} (précédence)"]
    section = md.split("## 4.", 1)[-1].split("## 5.", 1)[0]
    out += [f"W9 MD § 4 : jeton {j} absent" for j in jetons if not re.search(rf"\b{j}\b", section)]
    return out


# =========================================================================== les tests
class ContratForme(unittest.TestCase):
    """W1, W2, W3, schéma, statut — et leurs mutants, parseur et JSON en mémoire."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = lire_contrat()
        cls.surface = extraire_surface()

    def _rouge(self, ecarts: list[str]) -> None:
        self.assertTrue(ecarts, "mutant VERT : le comparateur ne voit pas la mutation")

    def _surface_mutee(self, muter: Any) -> dict[str, Any]:
        ap, ap_env = construire_parseur(), construire_parseur(SENTINELLE)
        muter(ap, ap_env)
        return extraire_surface(ap, ap_env)

    def test_w1_verbes(self) -> None:
        self.assertEqual([], ecarts_verbes(self.surface, self.contrat))

    def test_w2_forme(self) -> None:
        self.assertEqual([], ecarts_forme(self.surface, self.contrat))

    def test_w2_root_symbolique(self) -> None:
        """C6 : sans la variable `.`, avec elle sa valeur — le contrat porte les deux."""
        nu = _action(construire_parseur(), "--root").default
        pose = _action(construire_parseur(SENTINELLE), "--root").default
        self.assertEqual((".", SENTINELLE), (nu, pose))
        self.assertEqual({"env": ENV_RACINE, "repli": "."}, self.contrat["options_globales"]["--root"]["defaut"])

    def test_w3_md(self) -> None:
        ecarts = ecarts_md(CONTRAT_MD.read_text(encoding="utf-8"), self.contrat)
        self.assertEqual([], ecarts, "\n".join(ecarts))

    def test_claim_override_contract(self) -> None:
        """La reprise et le refus de l'ancienne levée appartiennent au moteur."""
        self.assertEqual([], ecarts_forme(self.surface, self.contrat))
        for verbe, statut in (("start", "promis"), ("fournee", "noyau")):
            attendu = self.contrat["verbes"][verbe]
            self.assertEqual(statut, attendu["statut"])
            self.assertEqual([0, 2], attendu["rc"])
            # `None` (lot A) : l'option ABSENTE se distingue d'une raison vide, refusée elle aussi.
            self.assertIsNone(attendu["options"]["--takeover --reprise"]["defaut"])
            self.assertIsNone(attendu["options"]["--without-claim --sans-revendication"]["defaut"])
            self.assertIn("--takeover --reprise", self.surface["verbes"][verbe]["options"])
            self.assertIn("--without-claim --sans-revendication", self.surface["verbes"][verbe]["options"])

    def test_reprise_doctrine_cli(self) -> None:
        """Le contrat décrit le transfert et la borne de ses hôtes, sans promettre une barrière TTY."""
        md = CONTRAT_MD.read_text(encoding="utf-8")
        section = md.split("- **Propriété et revendication Git** :", 1)[1].split("\n\n", 1)[0]
        for attendu in ("--reprise", "stdin et stderr TTY", "lot `blocked`", "friction",
                        "winpty bash .agents/pyrun.sh .agents/bin/tasks.py",
                        "Claude Code", "AGENTS_HOOK_HOST", "Codex", "Gemini", "Copilot", "Kimi",
                        "--sans-revendication` est refusé"):
            self.assertIn(attendu, section)
        self.assertNotIn("lève ce seul refus", section)

    def test_claim_override_mutant_removed(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            _sous_parseurs(ap)["start"]._actions.remove(_action(_sous_parseurs(ap)["start"], "--sans-revendication"))
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_reprise_mutant_option_retiree_du_md(self) -> None:
        md = CONTRAT_MD.read_text(encoding="utf-8")
        ligne = next(x for x in md.splitlines() if x.startswith("| `batch` (`fournee`) |"))
        self.assertEqual(1, ligne.count("`--takeover --reprise`"))
        self._rouge(ecarts_md(md.replace(ligne, ligne.replace(" `--takeover --reprise`", ""), 1), self.contrat))

    def test_schema(self) -> None:
        self.assertEqual([], ecarts_schema(self.contrat))

    def test_statut(self) -> None:
        self.assertEqual([], ecarts_statut(self.contrat))

    def test_mutant_m01_parseur_verbe_zz(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction)).add_parser("zz")
        self._rouge(ecarts_verbes(self._surface_mutee(muter), self.contrat))

    def test_mutant_m02_done_action_retiree(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            sp = _sous_parseurs(ap)["done"]
            sp._actions.remove(_action(sp, "--sans-binome"))
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m03_raison_facultative(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            _action(_sous_parseurs(ap)["done"], "--raison").required = False
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m04_list_state_choix_amputes(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            a = _action(_sous_parseurs(ap)["list"], "--state")
            a.choices = list(a.choices)[:-1]
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m05_defaut_plafond(self) -> None:
        def muter(ap: Any, env: Any) -> None:
            for p in (ap, env):
                _action(_sous_parseurs(p)["purge"], "--plafond").default = 51
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m06_nargs_parallel(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            _action(_sous_parseurs(ap)["parallel"], "tids").nargs = "*"
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m07_statusline_retiree(self) -> None:
        def muter(ap: Any, _env: Any) -> None:
            ap._actions.remove(_action(ap, "--statusline"))
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m08_root_defaut_fige(self) -> None:
        def muter(_ap: Any, env: Any) -> None:
            _action(env, "--root").default = "."
        self._rouge(ecarts_forme(self._surface_mutee(muter), self.contrat))

    def test_mutant_m09_verbe_retire_du_contrat(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        del contrat["verbes"]["render"]
        self._rouge(ecarts_verbes(self.surface, contrat))

    def test_mutant_m10_statut_bascule(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["reassign"]["statut"] = "promis"
        self._rouge(ecarts_statut(contrat))

    def test_mutant_m11_md_ligne_otee(self) -> None:
        md = CONTRAT_MD.read_text(encoding="utf-8")
        ligne = next(x for x in md.splitlines() if x.startswith("| `start` |"))
        self._rouge(ecarts_md(md.replace(ligne + "\n", "", 1), self.contrat))

    def test_mutant_m12_md_cellule_changee(self) -> None:
        md = CONTRAT_MD.read_text(encoding="utf-8")
        self.assertEqual(1, md.count("| `list` | promis |"))
        self._rouge(ecarts_md(md.replace("| `list` | promis |", "| `list` | noyau |"), self.contrat))

    def test_mutant_m13_schema_mutant_inconnu(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["render"]["mutant"] = "lecture"
        self._rouge(ecarts_schema(contrat))

    def test_w9_jetons_deps_ready(self) -> None:
        jetons = charger_tasks().DEPS_READY_JETONS
        self.assertIn("REPRISE_DITE", jetons)  # non-vacuité : le jeton que les lanceurs doivent lire
        ecarts = ecarts_jetons_deps_ready(jetons, self.contrat, CONTRAT_MD.read_text(encoding="utf-8"))
        self.assertEqual([], ecarts, "\n".join(ecarts))

    def test_mutant_m29_jeton_reprise_retire(self) -> None:
        """REPRISE_DITE ôté du registre (contrat, puis MD) : W9 rougit sur chacun."""
        jetons = charger_tasks().DEPS_READY_JETONS
        md = CONTRAT_MD.read_text(encoding="utf-8")
        contrat = copy.deepcopy(self.contrat)
        contrat["definitions"]["deps-ready"] = contrat["definitions"]["deps-ready"].replace("REPRISE_DITE", "REPRISE")
        self._rouge(ecarts_jetons_deps_ready(jetons, contrat, md))
        self._rouge(ecarts_jetons_deps_ready(jetons, self.contrat, md.replace("REPRISE_DITE", "REPRISE")))
        # Précédence inversée : AMONT_CLOS avant CYCLE, mêmes jetons.
        inverse = copy.deepcopy(self.contrat)
        inverse["definitions"]["deps-ready"] = "AMONT_CLOS " + inverse["definitions"]["deps-ready"]
        self._rouge(ecarts_jetons_deps_ready(jetons, inverse, md))


class ContratAst(unittest.TestCase):
    """W7 (rc 1 par AST de `main`) et la répartition de W8 — mutants sur la SOURCE."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = lire_contrat()
        cls.source = TASKS_PY.read_text(encoding="utf-8")
        cls.verbes = list(extraire_surface()["verbes"])

    def _muter(self, ancre: str, remplacement: str) -> str:
        self.assertEqual(1, self.source.count(ancre), f"ancre ambiguë ou absente : {ancre!r}")
        return self.source.replace(ancre, remplacement)

    def test_w7_rc1_ast(self) -> None:
        self.assertEqual([], ecarts_rc1_ast(self.contrat, self.source))

    def test_w8_repartition(self) -> None:
        self.assertEqual([], ecarts_repartition(self.verbes, self.source))

    def test_mutant_m14_rc1_ajoute_a_start(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["start"]["rc"] = [0, 1, 2]
        self.assertTrue(ecarts_rc1_ast(contrat, self.source))

    def test_mutant_m15_return_1_retire(self) -> None:
        ancre = '                return 1\n        elif args.cmd == "binome-purge":'
        source = self._muter(ancre, ancre.replace("return 1", "return 0"))
        self.assertTrue(ecarts_rc1_ast(self.contrat, source))

    def test_mutant_m16_return_nom_retire(self) -> None:
        self.assertTrue(ecarts_rc1_ast(self.contrat, self._muter("return rc_cible", "return 0")))

    def test_mutant_m17_rc_verbe_sans_1(self) -> None:
        source = self._muter('rc_verbe = 0 if releve["verdict"] == "ok" else 1', "rc_verbe = 0")
        self.assertTrue(ecarts_rc1_ast(self.contrat, source))

    def test_mutant_m18_branche_otee(self) -> None:
        source = self._muter('elif args.cmd == "render":', 'elif args.cmd == "render-zz":')
        self.assertTrue(ecarts_repartition(self.verbes, source))


class ContratEnProcessus(unittest.TestCase):
    """W4 (mutant), W5 (faute d'usage), W6 (pont injecté), W8 (aucun repli sur l'aide)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = lire_contrat()
        cls.surface = extraire_surface()
        cls.base = Path(tempfile.mkdtemp(prefix="contrat-cli-proc-"))
        try:
            racine = cls.base / "racine"
            racine.mkdir()
            env = cls.env = env_banc(cls.base, racine)
            cls.jeux = {v: jouer_en_processus(racine, env, argv) for v, argv in SCENARIOS.items()}
            for verbe, forme in cls.surface["verbes"].items():
                if "--dry-run" in forme["options"] and verbe in SCENARIOS:
                    cls.jeux[verbe + " --dry-run"] = jouer_en_processus(racine, env, SCENARIOS[verbe] + ["--dry-run"])
            cls.statusline = jouer_en_processus(racine, env, ["--statusline", "start", ID])
            cls.usage = {v: jouer_en_processus(racine, env, SCENARIOS[v] + ["--zz-inconnu"])
                         for v in cls.surface["verbes"] if v in SCENARIOS}
            cls.pont_injecte = jouer_en_processus(racine, env, ["replay-sync"], refus_pont=True)
            cls.nu = jouer_en_processus(racine, env, [])
            cls.env_vu: dict[str, str] = {}
            with mock.patch.dict(os.environ, {"HOME": HOME_HOTE, FUITE_HOTE: "1"}):
                cls.temoin_env = jouer_en_processus(racine, env, SCENARIOS["start"], vu=cls.env_vu)
        except BaseException:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_w4_mutant(self) -> None:
        self.assertEqual([], ecarts_mutant(self.contrat, mutants_observes(self.jeux, self.surface)))

    def test_w4_statusline_avale_le_verbe(self) -> None:
        self.assertEqual((0, 0), (self.statusline.rc, self.statusline.drains))
        self.assertNotIn("unknown task id", self.statusline.err)

    def test_w5_faute_usage(self) -> None:
        self.assertEqual([], ecarts_usage(list(self.surface["verbes"]), self.usage))

    def test_w6_pont_injecte(self) -> None:
        self.assertEqual(1, self.pont_injecte.rc)

    def test_w8_sans_verbe_aide_rc0(self) -> None:
        self.assertEqual(0, self.nu.rc)
        self.assertIn(ENTETE_AIDE, self.nu.out)

    def test_w8_aucun_repli_sur_aide(self) -> None:
        replis = [n for n, j in self.jeux.items() if ENTETE_AIDE in j.out]
        self.assertEqual([], replis)

    def test_mutant_m19_mutant_inverse_sur_list(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["list"]["mutant"] = "oui"
        self.assertTrue(ecarts_mutant(contrat, mutants_observes(self.jeux, self.surface)))

    def test_mutant_m20_sauf_dry_run_efface(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["purge"]["mutant"] = "oui"
        self.assertTrue(ecarts_mutant(contrat, mutants_observes(self.jeux, self.surface)))

    def test_mutant_m21_usage_rc0(self) -> None:
        usage = dict(self.usage, done=Jeu(0, "", ""))
        self.assertTrue(ecarts_usage(list(self.surface["verbes"]), usage))

    def test_mutant_m27_usage_positionnel_manquant(self) -> None:
        """Ce que l'ancien W5 acceptait : rc 2 et `usage:`, mais l'option inconnue jamais atteinte."""
        manquant = Jeu(2, "", "usage: tasks.py done [-h] tid\n"
                              "tasks.py done: error: the following arguments are required: tid, --raison\n")
        self.assertTrue(ecarts_usage(list(self.surface["verbes"]), dict(self.usage, done=manquant)))

    def test_c7_env_en_processus(self) -> None:
        self.assertEqual([], ecarts_env(self.env_vu, self.env))
        self.assertTrue(Path(self.env_vu["HOME"]).is_relative_to(self.base))
        self.assertEqual(2, self.temoin_env.rc)

    def test_mutant_m28_env_herite(self) -> None:
        self.assertTrue(ecarts_env(dict(self.env_vu, HOME=HOME_HOTE), self.env))
        self.assertTrue(ecarts_env(dict(self.env_vu, **{FUITE_HOTE: "1"}), self.env))


class ContratSousProcessus(unittest.TestCase):
    """W5 (identifiant inconnu), W6 (rc 1 réels et jumeaux), W8 (sorties), exceptions R2."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = lire_contrat()
        cls.surface = extraire_surface()
        cls.base = Path(tempfile.mkdtemp(prefix="contrat-cli-sp-"))
        try:
            cls.obs = cls._jouer_tout(cls.base)
        except BaseException:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.base, ignore_errors=True)

    @staticmethod
    def _jouer_tout(base: Path) -> dict[str, Jeu]:
        racine = base / "racine"
        racine.mkdir()
        env = env_banc(base, racine)
        obs: dict[str, Jeu] = {}

        def j(nom: str, argv: list[str], env_: dict[str, str] | None = None) -> Jeu:
            obs[nom] = jouer_sous_processus(racine, env_ or env, argv)
            return obs[nom]

        j("nu", [])
        j("usage_list", ["list", "--zz-inconnu"])
        trouve = re.search(r"T-[0-9A-Z]+", j("new", SCENARIOS["new"]).out)
        if trouve is None:
            raise RuntimeError(f"banc : `new` n'a pas rendu d'identifiant : {obs['new']}")
        tid = trouve.group(0)
        j("writeset", ["writeset", tid, "a.txt"])
        j("list_json", ["list", "--json"])
        j("list_json_vide", ["list", "--json", "--state", "blocked"])
        j("render", ["render"])
        j("replay_sync", ["replay-sync"])
        fichier = base / "etat-fichier"
        fichier.write_text("banc\n", encoding="utf-8")  # partition d'état occupée par un FICHIER (C10)
        j("replay_sync_refus", ["replay-sync"], dict(env, CADRE_STATE_DIR=str(fichier)))
        j("statusline", ["--statusline", "start", ID])
        for nom, argv in scenarios_id_inconnu().items():
            j(nom, argv)
        j("commit_stores_sans_script", ["commit-stores", "--exiger"])
        j("commit_run_exports_sans_script", ["commit-run-exports", "--exiger"])
        (racine / ".agents" / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT_COMMIT, racine / ".agents" / "bin" / SCRIPT_COMMIT.name)
        j("commit_stores_script_sans_git", ["commit-stores", "--exiger"])
        j("commit_run_exports_script_sans_git", ["commit-run-exports", "--exiger"])
        j("retour_sans_git", ["retour", tid, "--base", "0000000", "--branche", "banc"])
        (racine / "spec.md").write_text("# Spec\n\n**« Invariant banc »** : un nom.\n", encoding="utf-8")
        (racine / "plan.md").write_text("# Plan\n\n## Steps\n1. une étape\n", encoding="utf-8")
        (racine / "plan-cible.md").write_text("# Plan\n\n## Steps\n1. une étape — cible: « Invariant banc »\n",
                                              encoding="utf-8")
        j("cible_check_sans_cible", ["cible-check", "plan.md", "--spec", "spec.md"])
        j("cible_check_avec_cible", ["cible-check", "plan-cible.md", "--spec", "spec.md"])
        j("cible_check_sans_spec", ["cible-check", "plan.md"])
        # `deps-ready` : deux tâches NEUVES (jamais `tid`, lu par `retour`), rc 1 amont ouvert, rc 0 amont clos.
        amont, aval = (re.search(r"T-[0-9A-Z]+", jouer_sous_processus(racine, env, SCENARIOS["new"]).out).group(0)
                       for _ in range(2))
        jouer_sous_processus(racine, env, ["depends", aval, amont, "--motif", "banc : amont livre"])
        j("deps_ready_ouvert", ["deps-ready", aval])
        jouer_sous_processus(racine, env, ["done", amont, "--raison", "banc"])
        j("deps_ready_clos", ["deps-ready", aval])
        # `depassements` : jumeau rc 0 AVANT toute limite, puis une tâche NEUVE à l'échéance passée, rc 1.
        j("depassements_rien", ["depassements"])
        j("depassements_json_vide", ["depassements", "--json"])
        en_retard = re.search(r"T-[0-9A-Z]+", jouer_sous_processus(racine, env, SCENARIOS["new"]).out).group(0)
        jouer_sous_processus(racine, env, ["limite", en_retard, "--echeance", "2000-01-01T00:00Z"])
        j("depassements_depasse", ["depassements"])
        j("depassements_json", ["depassements", "--json"])
        # C10 : `retour` refusé DANS un dépôt git jetable (fichier hors write-set), jumeau ok.
        git(racine, env, "init", "-q", "-b", "main")
        (racine / ".git" / "info" / "exclude").write_text(".agents/\nruns/\n*.md\n", encoding="utf-8")
        (racine / "LISEZMOI").write_text("banc\n", encoding="utf-8")
        git(racine, env, "add", "LISEZMOI")
        git(racine, env, "commit", "-q", "-m", "base")
        base_sha = git(racine, env, "rev-parse", "HEAD")
        for branche, fichier_dev in (("wt/hors", "hors.txt"), ("wt/ok", "a.txt")):
            git(racine, env, "switch", "-q", "-c", branche, base_sha)
            (racine / fichier_dev).write_text("banc\n", encoding="utf-8")
            git(racine, env, "add", fichier_dev)
            git(racine, env, "commit", "-q", "-m", f"dev {branche}")
            git(racine, env, "switch", "-q", "main")
        j("retour_git_refus", ["retour", tid, "--base", base_sha, "--branche", "wt/hors", "--dry-run"])
        j("retour_git_ok", ["retour", tid, "--base", base_sha, "--branche", "wt/ok", "--dry-run"])
        return obs

    def test_w5_identifiant_inconnu(self) -> None:
        self.assertEqual([], ecarts_id_inconnu(self.surface, self.obs))

    def test_w6_rc1_et_jumeaux(self) -> None:
        self.assertEqual([], ecarts_rc1(self.contrat, self.obs))

    def test_w8_sorties(self) -> None:
        self.assertEqual([], ecarts_sorties(self.contrat, self.obs))

    def test_comportements_attendus(self) -> None:
        """Les exceptions R2 du MD (C9) : chaque scénario rend son rc, sur le flux dit."""
        self.assertEqual([], ecarts_attendus(self.obs))

    def test_mutant_m22_sortie_new(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["new"]["sorties"]["derniere_ligne"] = r"TASKS: T-[0-9A-Z]+ → running"
        self.assertTrue(ecarts_sorties(contrat, self.obs))

    def test_mutant_m23_jeton_retire(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["jetons_commit"]["litteraux"].remove("nothing")
        self.assertTrue(ecarts_sorties(contrat, self.obs))

    def test_mutant_m24_rc1_sans_scenario(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        contrat["verbes"]["list"]["rc"] = [0, 1, 2]
        self.assertTrue(ecarts_rc1(contrat, self.obs))

    def test_mutant_m25_id_inconnu_sans_ligne(self) -> None:
        obs = dict(self.obs)
        obs["inconnu start"] = Jeu(2, "", "event_store: bruit\nunknown task id\n")
        self.assertTrue(ecarts_id_inconnu(self.surface, obs))

    def test_mutant_m26_jumeau_rc1(self) -> None:
        obs = dict(self.obs, commit_stores_script_sans_git=Jeu(1, "failed\n", ""))
        self.assertTrue(ecarts_rc1(self.contrat, obs))

    def test_mutant_m30_depassements_ote_ou_sans_rc1(self) -> None:
        """C4 : `depassements` ôté du JSON (W1 et statut), ou son rc 1 retiré (W6) : rouge."""
        contrat = copy.deepcopy(self.contrat)
        del contrat["verbes"]["depassements"]
        self.assertTrue(ecarts_verbes(self.surface, contrat))
        self.assertTrue(ecarts_statut(contrat))
        sans_rc1 = copy.deepcopy(self.contrat)
        sans_rc1["verbes"]["depassements"]["rc"] = [0, 2]
        self.assertTrue(ecarts_rc1(sans_rc1, self.obs))


class AliasAnglais(unittest.TestCase):
    """T-01M5QC86XNEJ5NEX6DGZJ0AJZ5 (S-01M5S9S55X02Z3J0WATVQD0ZH9) : le nom ANGLAIS en tête, l'ancien
    accepté. Mutants (annexe § C) : `set_defaults` ôté sur `batch` (le verbe tapé ne se répartit plus) ;
    `dest` omise sur `--require` (`getattr(args, "exiger")` se tait, rc 0 sur `failed`) ; `--takeover`
    déclaré à part (le refus REVENDICATION ne mord plus) ; un alias ancien ôté (W2) — chacun rougit."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = lire_contrat()
        cls.ap = construire_parseur()
        cls.base = Path(tempfile.mkdtemp(prefix="contrat-cli-alias-"))
        try:
            racine = cls.base / "racine"
            racine.mkdir()
            env = env_banc(cls.base, racine)
            cls.jeux = {}
            for anglais, ancien in VERBES_ANGLAIS.items():
                for nom in (anglais, ancien):
                    cls.jeux[nom] = jouer_en_processus(racine, env, [nom, *SCENARIOS[ancien][1:]])
            for argv in (["commit-stores", "--require"], ["commit-run-exports", "--require"],
                         ["start", ID, "--takeover", "banc"], ["batch", ID, "--takeover", "banc"]):
                cls.jeux[" ".join(argv)] = jouer_en_processus(racine, env, argv)
        except BaseException:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_verbes_anglais_en_tete_repartis_sur_l_ancien(self) -> None:
        choix = list(_sous_parseurs(self.ap))
        alias = {d["alias"]: v for v, d in self.contrat["verbes"].items() if "alias" in d}
        self.assertEqual(VERBES_ANGLAIS, alias, "liste FERMÉE des verbes aliasés (annexe § A1)")
        for anglais, ancien in VERBES_ANGLAIS.items():
            with self.subTest(verbe=anglais):
                self.assertLess(choix.index(anglais), choix.index(ancien), "l'anglais en tête")
                self.assertEqual(ancien, self.ap.parse_args([anglais, *SCENARIOS[ancien][1:]]).cmd)

    def test_verbe_anglais_joue_comme_l_ancien(self) -> None:
        for anglais, ancien in VERBES_ANGLAIS.items():
            with self.subTest(verbe=anglais):
                en, fr = self.jeux[anglais], self.jeux[ancien]
                self.assertNotIn(ENTETE_AIDE, en.out, "le verbe anglais retombe sur l'aide générale")
                self.assertEqual((fr.rc, fr.out, fr.err, fr.drains), (en.rc, en.out, en.err, en.drains))

    def test_drapeaux_anglais_en_tete_dest_ancienne(self) -> None:
        sous = _sous_parseurs(self.ap)
        vus = {(a.option_strings[0], verbe) for verbe, sp in replier_alias(sous).items() for a in sp[0]._actions
               if len([o for o in a.option_strings if o.startswith("--")]) > 1}
        attendus = {(en, v) for en, (_ancien, verbes) in DRAPEAUX_ANGLAIS.items() for v in verbes}
        self.assertEqual(attendus, vus, "liste FERMÉE des drapeaux aliasés (annexe § A1)")
        for en, (ancien, verbes) in DRAPEAUX_ANGLAIS.items():
            for verbe in verbes:
                with self.subTest(drapeau=en, verbe=verbe):
                    action = _action(sous[verbe], en)
                    self.assertEqual([en, ancien], action.option_strings)
                    self.assertEqual(ancien[2:].replace("-", "_"), action.dest, "`dest` ancienne explicite")

    def test_metavars_anglais_des_positionnels(self) -> None:
        sous = _sous_parseurs(self.ap)
        for (verbe, dest), metavar in METAVARS_ANGLAIS.items():
            with self.subTest(verbe=verbe):
                self.assertEqual(metavar, _action(sous[verbe], dest).metavar)

    def test_aides_ascii_sans_metavar_francais_sur_tous_les_verbes(self) -> None:
        # Balaye CHAQUE verbe : un metavar implicite tiré d'une `dest` française échappe à un grep de `metavar=`.
        fr = re.compile(r"\b(POURQUOI|RAISON|NOM|GROUPE|CLE|AAAA-MM-JJ|ETAPE|TENTATIVE|MOTIF|OBSERVE|TITRE|CHANTIER|RESPONSABLE)\b")
        for verbe, sp in _sous_parseurs(self.ap).items():
            with self.subTest(verbe=verbe):
                aide = sp.format_help()
                self.assertTrue(aide.isascii(), f"{verbe} --help non ASCII (sort avant force_utf8_stdio)")
                self.assertIsNone(fr.search(aide), aide)

    def test_require_rend_1_sur_failed(self) -> None:
        for verbe in ("commit-stores", "commit-run-exports"):
            with self.subTest(verbe=verbe):
                jeu = self.jeux[f"{verbe} --require"]
                self.assertEqual((1, "failed"), (jeu.rc, jeu.out.strip().splitlines()[-1]), jeu)

    def test_takeover_garde_le_refus_revendication(self) -> None:
        for verbe in ("start", "batch"):
            with self.subTest(verbe=verbe):
                jeu = self.jeux[f"{verbe} {ID} --takeover banc"]
                self.assertEqual(2, jeu.rc, jeu)
                self.assertIn("REVENDICATION : reprise réservée au terminal du pilote", jeu.err)

    def test_aide_de_depends_cite_le_nom_anglais(self) -> None:
        """`plan_depends.AIDE_CLI` : seul le nom cité change (annexe § A1), l'ancien n'y est plus nommé."""
        aide = charger_tasks().plan_depends_module(lecture=True).AIDE_CLI
        for cle in ("depends_deps", "depends_retirer"):
            with self.subTest(cle=cle):
                self.assertIn("--remove-pilot-order", aide[cle])
                self.assertNotIn("--retirer-ordre-pilote", aide[cle])

    def test_mutant_alias_retire_du_contrat(self) -> None:
        contrat = copy.deepcopy(self.contrat)
        del contrat["verbes"]["fournee"]["alias"]
        self.assertIn("W1 verbe au parseur, absent du contrat : batch", ecarts_verbes(extraire_surface(), contrat))


# =========================================================================== hors pytest
def formater(valeur: Any, profondeur: int = 0) -> str:
    """JSON lisible : les trois premiers niveaux dépliés, une feuille courte sur une ligne."""
    en_ligne = json.dumps(valeur, ensure_ascii=False)
    scalaires = isinstance(valeur, list) and all(not isinstance(x, (dict, list)) for x in valeur)
    if not isinstance(valeur, (dict, list)) or not valeur or (
            len(en_ligne) <= 150 and (profondeur >= 3 or scalaires)):
        return en_ligne
    pad, dedans = "  " * profondeur, "  " * (profondeur + 1)
    if isinstance(valeur, dict):
        items = [f"{dedans}{json.dumps(k, ensure_ascii=False)}: {formater(v, profondeur + 1)}" for k, v in valeur.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    return "[\n" + ",\n".join(f"{dedans}{formater(v, profondeur + 1)}" for v in valeur) + "\n" + pad + "]"


def squelette() -> str:
    """La surface extraite, les champs sémantiques recopiés du JSON courant (`A_REMPLIR` sinon)."""
    actuel = lire_contrat() if CONTRAT_JSON.is_file() else {}
    surface = extraire_surface()
    sortie = {k: v for k, v in actuel.items() if k not in ("options_globales", "verbes")}
    sortie["options_globales"] = surface["options_globales"]
    verbes = {}
    for verbe, forme in surface["verbes"].items():
        ancien = actuel.get("verbes", {}).get(verbe, {})
        d = {k: ancien.get(k, "A_REMPLIR") for k in ("statut", "mutant", "rc")}
        d.update(forme)
        if "sorties" in ancien:
            d["sorties"] = ancien["sorties"]
        verbes[verbe] = d
    sortie["verbes"] = verbes
    return formater(sortie) + "\n"


if __name__ == "__main__":
    if sys.argv[1:] == ["--squelette"]:
        sys.stdout.write(squelette())
    elif sys.argv[1:] == ["--tableau"]:
        sys.stdout.write(rendre_bloc(lire_contrat()) + "\n")
    else:
        unittest.main()
