#!/usr/bin/env python3
"""SubagentStop — TRACE MÉCANIQUE DE LA CHAÎNE DE PLAN (T-00000624).

POURQUOI CE FICHIER EXISTE. `T-00000586` a rendu MÉCANIQUE la règle « aucune
tâche fermée sans revue critique » (UN critique depuis S-00004500) : le binôme de CLÔTURE est tracé par
l'hôte et `tasks.py done` refuse sans lui. Rien d'équivalent ne tenait l'AUTRE
bout de la chaîne — `planner` → `plan-critic` → porte humaine. Cette moitié-là
restait tenue par la seule mémoire de l'orchestrateur, exactement l'état que le
binôme de clôture a quitté. Demande pilote du 2026-09-14.

CE QU'IL NE FAIT PAS, ET NE FERA JAMAIS : lancer les agents. AUCUN hook de ce
dépôt n'invoque de modèle — le banc `test_hooks_zero_llm` le prouve et c'est un
invariant. Ce script MESURE ce qui a tourné ; c'est `tasks.py start` qui REFUSE.

NE RECOLLE PAS LE CHEMIN COMPLET DE CE BANC DANS CETTE DOCSTRING, et la raison
n'est pas cosmétique — mesurée le 2026-09-14, en rouge. Ce banc suit les
références de chemin des scripts qu'un hook atteint, et il SAUTE les lignes de
commentaire (`_is_comment`, un `#` en tête). Le frère shell de ce fichier cite
le même chemin sans dommage parce que tout son en-tête est en `#` ; une
docstring Python, elle, n'est PAS une ligne de commentaire. Écrire
`.agents/evals/test_hooks_zero_llm` suivi de son extension crée donc une ARÊTE
vers ce banc, qui est tout entier fait de littéraux de formes LLM — et le filet
rougit sur son propre vocabulaire. Le nom nu suffit à informer le lecteur.

LE SIGNAL, ET IL EST MESURÉ SUR CE DÉPÔT. La charge `SubagentStop` porte
`agent_type` — le NOM de la def qui vient de finir —, et le 2026-09-14 les deux
critiques de clôture ont écrit leurs traces à 20:50:30Z et 20:51:02Z au sha
`5b5c206` : le canal est prouvé sur un cas d'existence certaine, pas supposé.
Même champ que celui que `log-agent-usage.sh` consomme déjà pour les tokens.

*** UN DOSSIER SÉPARÉ, ET C'EST DÉLIBÉRÉ. ***
Les traces de plan vivent sous `.agents/state/local/plan/`, JAMAIS sous
`binome/`. Ce n'est pas du rangement. `affirmation-guard.sh` et `tasks.py`
lisent le dossier `binome/` et n'acceptent qu'un vocabulaire clos de trois noms
— mais ce vocabulaire a DÉJÀ été un `startswith("critic-")` trop large, et le
dépôt l'a corrigé après avoir mesuré qu'un fichier posé à la main suffisait
alors à satisfaire la garde. `plan-critic-sonnet-max` contient la sous-chaîne
`critic`. Deux dossiers rendent la confusion IMPOSSIBLE plutôt que seulement
interdite : une revue de PLAN ne pourra jamais valoir revue de CLÔTURE, même si
un futur vocabulaire se relâche.

CE QUE ÇA EMPÊCHE, ET CE QUE ÇA N'EMPÊCHE PAS — dit ici plutôt que découvert.
Ça empêche d'OUBLIER. Ça n'empêche pas de TRICHER : la trace est un fichier
d'état ordinaire, qu'un agent déterminé peut écrire à la main. Le mode de
défaillance visé est l'oubli, qui est celui qu'on a MESURÉ.

CE QU'IL NE PROUVE PAS NON PLUS, ET IL FAUT LE LIRE AVANT DE S'EN SERVIR :
il prouve que les defs ont TOURNÉ, jamais que leur travail était bon, et jamais
sur QUELLE tâche. La charge `SubagentStop` ne porte pas d'identifiant de tâche
— et la lecture du prompt n'a PAS été mesurée sur cet hôte, donc on ne la
suppose pas. L'attribution est portée autrement : `tasks.py start` CONSOMME les
traces, donc une chaîne de verdicts autorise EXACTEMENT UN démarrage, et la
consommation est journalisée. C'est une comptabilité, pas une signature.

ADVISORY, TOUJOURS `exit 0`. Un hook `SubagentStop` qui échoue fermé coûterait
un sous-agent ; le refus, lui, vit dans `tasks.py`, au seul endroit que tous les
hôtes traversent.

COUVERTURE, À CITER TELLE QUELLE : 1 MESURÉ (Claude) / 2 CÂBLÉS AU REGISTRE (Codex —
événement et champ `agent_type` MESURÉS sur le traceur du binôme, X4, 2026-10-12 ;
Copilot — `subagentStop` porte `agentType` = le nom de la déf, MESURÉ P4 sur le
traceur du binôme ; l'émission de CE traceur n'a été rejouée sur aucun des deux) /
2 NON CÂBLÉS (Gemini — aucun événement de fin de sous-agent, scénario G5 non joué ;
Kimi) + 1 HÉRITÉ NON CÂBLÉ (Antigravity). Le fichier vit dans `.agents/bin/` et les
registres Codex et Copilot l'appellent sans seconde copie. Jamais « trois hôtes
couverts ».
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# LES DEUX VOCABULAIRES SONT CLOS ET SÉPARÉS, et ils vivent ici ET dans
# `tasks.py` — les deux moitiés d'un même contrat, liées par un banc pour
# qu'elles ne divergent pas : une trace écrite sous un nom que le refus ne
# reconnaît pas serait une preuve invisible, donc un démarrage refusé sans
# raison compréhensible.
#
# POURQUOI DEUX TUPLES ET NON UN. La garde exige UN relecteur (`plan-critic` —
# décision pilote S-00003871 ; DEUX avant elle) et UN plan (`planner`). Un tuple
# unique confondrait les deux rôles, et un planner compterait alors comme
# critique — la règle doit être LISIBLE dans le code.
#
# POURQUOI CHAQUE TUPLE GARDE DEUX NOMS (décision pilote S-01M4TZZ13Y,
# 2026-10-13 : planification sur Opus seul). `planner-sonnet` et
# `plan-critic-sonnet-max` sont DÉBRANCHÉS, pas supprimés : l'orchestrateur ne
# les invoque plus, mais leur trace s'écrit encore et reste ACCEPTÉE par la
# garde (`tasks_gardes.py`), sans échéance ; chaque trace expire 24 h après son
# écriture, comme toute trace — une chaîne lancée avant la décision finit.
PLAN_REVIEWERS = ("plan-critic", "plan-critic-sonnet-max")
PLAN_PLANNERS = ("planner", "planner-sonnet")

TIMEOUT_SECONDS = 5


def _run(*args: str, cwd: str) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=TIMEOUT_SECONDS)
        return p.stdout.strip()
    except Exception:
        return ""


def _chrono(root: str, payload: dict) -> dict:
    """LE CHRONO RÉEL, EN PLUS ET JAMAIS À LA PLACE (T-01M55Z3ZCS34CDR2EQN1CEBHR7). `aid`,
    `duration_ms`, `tokens` du frère `agent_chrono.py`, clés posées SEULEMENT quand elles sont
    connues. CHARGEMENT ET APPEL SOUS `try` : ce traceur est une garde armée par graine chez
    l'adoptant — un module absent, cassé ou qui lève rend `{}`, et la charge de base reste
    exactement `{at, sha, role}` (même idiome de chargement que `specs.record_id_module`)."""
    try:
        import importlib.util

        nom = "_cadre_agent_chrono_trace"
        spec = importlib.util.spec_from_file_location(nom, Path(__file__).resolve().with_name("agent_chrono.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        spec.loader.exec_module(module)
        chrono = module.chrono_de(root, payload)
        return {k: chrono[k] for k in ("aid", "duration_ms", "tokens") if k in chrono}
    except Exception:
        return {}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    # LES DEUX GRAPHIES, ET CE N'EST PAS DE LA COURTOISIE (leçon T-00000589).
    # Le traceur du binôme ne lisait que le snake_case : sur un hôte qui envoie
    # du camelCase il sortait 0 EN SILENCE — aucune trace, donc refus
    # systématique, donc la sortie tracée comme seule issue. Un hook qui ne
    # trouve pas son champ se tait exactement comme un sous-agent non concerné,
    # et l'écart est invisible. Les deux graphies dès le premier jour.
    agent = str(payload.get("agent_type") or payload.get("agentType") or "").strip()
    if agent not in PLAN_REVIEWERS and agent not in PLAN_PLANNERS:
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    dossier = Path(root) / ".agents" / "state" / "local" / "plan"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0

    # UN FICHIER PAR DEF, ET RIEN NE LIT AVANT D'ÉCRIRE — correctif hérité du
    # binôme de clôture, dont la première version tenait UN fichier lu-modifié-
    # réécrit : la doctrine lançait deux critiques EN PARALLÈLE avant S-00004500,
    # et un critique et son repli peuvent encore s'arrêter dans la même fenêtre ;
    # deux arrêts lisaient tous deux l'état vide et le second écrasait le premier. Le mécanisme échouait exactement sur le cas
    # qu'il existe pour servir, et l'échec avait l'air d'un oubli.
    #
    # PAS D'IDENTIFIANT DE TÂCHE DANS LE NOM, contrairement au binôme : au
    # moment où ces defs tournent la tâche n'est pas encore `running` (la chaîne
    # précède `tasks.py start`), et viser la `running` du moment attribuerait
    # les verdicts d'une tâche à une AUTRE — mesuré sur ce dépôt, où le chantier
    # T-012 tourne en permanence et aurait tout absorbé.
    charge = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha": _run("git", "rev-parse", "--short", "HEAD", cwd=root) or "?",
        "role": "reviewer" if agent in PLAN_REVIEWERS else "planner",
    }
    charge.update(_chrono(root, payload))
    try:
        (dossier / f"{agent}.json").write_text(
            json.dumps(charge, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
