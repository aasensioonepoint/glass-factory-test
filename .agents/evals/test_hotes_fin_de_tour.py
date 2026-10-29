"""Banc des gardes de FIN DE TOUR sur Codex et Copilot (alignement des hotes, lot L-C ; H-48, H-50).

POURQUOI. `affirmation-guard.sh` (Stop) n'etait cable que sur Claude Code, alors que Codex
(X3/X3b) et Copilot (P3) honorent TOUS DEUX `{"decision":"block"}` en fin de tour et portent
`stop_hook_active` (mesure du 2026-10-12, dans un clone jetable). `plan_trace.py` n'etait cable
que sur Claude et Codex ; Copilot nomme le sous-agent en `agentType` (P4 : le nom de la def).

CE QUE CE BANC TIENT :
  * le registre de chaque hote porte la jambe, avec la RACINE en argument et une jambe Windows
    de la forme que `test_python_hook_launchers.py` impose a cet hote ;
  * la jambe ENREGISTREE, rejouee telle quelle depuis un sous-dossier d'un depot jetable, REFUSE
    (`decision: block`) quand la garde a de quoi refuser, et rend ZERO OCTET sur
    `stop_hook_active: true` (le garde-fou anti-boucle) — les deux sens ;
  * la jambe `Stop` de `.claude/settings.json`, que Copilot execute AUSSI (MESURE P4, 2026-10-13),
    se tait en fin de sous-agent, juge la racine tant que `agentStop` ne cable pas la garde (se tait
    ensuite, la jambe native jugeant la racine) et juge une charge Codex.

CE QU'IL NE PROUVE PAS : que l'hote appelle le hook (mesure ailleurs, X3b/P3) ; la logique de la
garde elle-meme (`affirmation-guard.test.sh`). Aucun hote n'est lance.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GARDE = ".claude/hooks/affirmation-guard.sh"
CODEX = ROOT / ".codex" / "hooks.json"
COPILOT = ROOT / ".github" / "hooks" / "agent-guardrails.json"
CLAUDE = ROOT / ".claude" / "settings.json"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="bash et git requis")


def _codex_stop() -> list[dict]:
    d = json.loads(CODEX.read_text(encoding="utf-8"))
    return [h for g in d["hooks"]["Stop"] for h in g["hooks"]]


def _claude_stop() -> list[dict]:
    d = json.loads(CLAUDE.read_text(encoding="utf-8"))
    return [h for g in d["hooks"]["Stop"] for h in g["hooks"]]


def _copilot(event: str) -> list[dict]:
    return json.loads(COPILOT.read_text(encoding="utf-8"))["hooks"][event]


def _one(entries: list[dict], needle: str, key: str) -> dict:
    found = [e for e in entries if needle in str(e.get(key, ""))]
    assert len(found) == 1, f"{needle!r} attendu UNE fois dans {key}, vu {len(found)}"
    return found[0]


def test_codex_stop_porte_la_garde_avec_la_racine_et_une_jambe_windows():
    h = _one(_codex_stop(), "affirmation-guard.sh", "command")
    assert "AGENTS_HOOK_HOST=codex" in h["command"]
    assert h["command"].count("git rev-parse --show-toplevel") == 2   # chemin ET argument 1
    assert " 'bash' $r '.claude/hooks/affirmation-guard.sh'" in h["commandWindows"]
    assert (ROOT / GARDE).is_file()


def test_copilot_agentstop_porte_la_garde_en_forme_native():
    h = _one(_copilot("agentStop"), "affirmation-guard.sh", "bash")
    assert h["bash"] == 'AGENTS_HOOK_HOST=copilot bash .claude/hooks/affirmation-guard.sh "$PWD"'
    assert h["cwd"] == "."
    ps = h["powershell"]
    assert ps.startswith("$ErrorActionPreference='Stop'; try {")
    assert "& bash ($r+'/.claude/hooks/affirmation-guard.sh') $r;" in ps
    assert "$childExitCode=$LASTEXITCODE; exit $childExitCode" in ps
    assert "pyrun.ps1" not in ps


def test_copilot_subagentstop_porte_plan_trace_sous_le_marqueur_copilot():
    h = _one(_copilot("subagentStop"), "plan_trace.py", "bash")
    assert h["bash"].startswith("AGENTS_HOOK_HOST=copilot ")
    assert " 'module' $r '.agents/bin/plan_trace.py'" in h["powershell"]
    assert (ROOT / ".agents/bin/plan_trace.py").is_file()


def _fixture(tmp: Path) -> Path:
    """Depot jetable ARME dont le PLAN-ETAT est sale, sans aucune trace de critique."""
    repo = tmp / "depot"
    (repo / ".agents/state/gates").mkdir(parents=True)
    (repo / ".agents/state/local/binome").mkdir(parents=True)
    (repo / ".agents/state/board").mkdir(parents=True)
    (repo / ".claude/hooks").mkdir(parents=True)
    (repo / "sous/dossier").mkdir(parents=True)
    shutil.copy2(ROOT / GARDE, repo / GARDE)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    git("init", "-q", ".")
    git("config", "user.email", "banc@local")
    git("config", "user.name", "banc")
    (repo / "PLAN-ETAT.md").write_text("plan initial\n", encoding="utf-8")
    (repo / ".agents/state/board/TASKS.json").write_text(
        '{"tasks":[{"id":"T-001","task":"a","state":"pending"}]}\n', encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")
    (repo / ".agents/state/gates/AFFIRMATION_REQUIRED").write_text("", encoding="utf-8")
    (repo / "PLAN-ETAT.md").write_text("plan initial\naffirmation neuve\n", encoding="utf-8")
    return repo


def _jouer(leg: str, cwd: Path, payload: dict) -> str:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "AGENTS_HOOK_HOST") and not k.startswith("GIT_")}
    run = subprocess.run(["bash", "-c", leg], cwd=cwd, env=env, input=json.dumps(payload),
                         capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stderr
    return run.stdout


@pytest.mark.parametrize("registre", ("codex", "copilot"))
def test_la_jambe_enregistree_refuse_puis_se_tait_sur_la_relance(tmp_path, registre):
    if registre == "codex":
        leg = _one(_codex_stop(), "affirmation-guard.sh", "command")["command"]
        sous = "sous/dossier"          # Codex lance ses hooks depuis le dossier de la session
    else:
        leg = _one(_copilot("agentStop"), "affirmation-guard.sh", "bash")["bash"]
        sous = "."                     # `cwd: "."` du registre Copilot = la racine
    repo = _fixture(tmp_path)
    sortie = _jouer(leg, repo / sous, {"stop_hook_active": False})
    verdict = json.loads(sortie)
    assert verdict.get("decision") == "block", f"{registre}: pas de refus, sortie {sortie!r}"
    assert "PLAN-ETAT.md" in verdict.get("reason", "")
    # le sens inverse : le MEME arbre, mais l'hote rejoue un Stop deja bloque
    assert _jouer(leg, repo / sous, {"stop_hook_active": True}) == ""


# Les charges RÉELLES d'`agentStop` Copilot (canari P4, 2026-10-12, `rt/copilot/P4/agentStop-152029`
# et `-152036`), chemins personnels remplacés par des valeurs neutres. Copilot émet `agentStop`
# AUSSI à la fin de chaque SOUS-AGENT : la charge porte alors le `sessionId` du sous-agent (l'`agentId`
# de son `subagentStop`, `-152032`, `critic-sonnet-max`), mais le `transcriptPath` de la session RACINE.
SESSION_RACINE = "412fbc8b-fdbe-4a0f-837e-085056ae4429"
SOUS_AGENT = "af8e4d9a-0536-414f-9d0f-9eea7fda1a67"
TRANSCRIPT_P4 = "/home/user/.copilot/session-state/" + SESSION_RACINE + "/events.jsonl"
P4_AGENTSTOP_SOUS_AGENT = {
    "sessionId": SOUS_AGENT, "timestamp": 1791811229849, "cwd": "/depot",
    "transcriptPath": TRANSCRIPT_P4, "stopReason": "end_turn", "stop_hook_active": False,
}
P4_AGENTSTOP_RACINE = {
    "sessionId": SESSION_RACINE, "timestamp": 1791811236760, "cwd": "/depot",
    "transcriptPath": TRANSCRIPT_P4, "stopReason": "end_turn", "stop_hook_active": False,
}


def test_copilot_agentstop_d_un_sous_agent_passe_celui_de_la_racine_refuse(tmp_path):
    """Un sous-agent Copilot (un critique en lecture seule compris) n'est pas bloqué par la jambe
    `agentStop` de `agent-guardrails.json` ; l'`agentStop` de la session racine, sur le MÊME arbre, l'est
    toujours. La jambe `Stop` de `.claude/settings.json`, que Copilot exécute AUSSI sans marqueur, est
    MESURÉE (P4, 2026-10-13 : deux tirs, snake_case, transcript sous `~/.copilot/session-state/`) ; elle se
    tait en fin de sous-agent, et à la racine SEULEMENT si la jambe `agentStop` est câblée : test suivant, et
    `affirmation-guard.test.sh` 17l à 17q''."""
    leg = _one(_copilot("agentStop"), "affirmation-guard.sh", "bash")["bash"]
    repo = _fixture(tmp_path)
    assert _jouer(leg, repo, P4_AGENTSTOP_SOUS_AGENT) == "", "le sous-agent Copilot est bloqué"
    verdict = json.loads(_jouer(leg, repo, P4_AGENTSTOP_RACINE))
    assert verdict.get("decision") == "block"
    assert "PLAN-ETAT.md" in verdict.get("reason", "")


def test_le_discriminant_du_sous_agent_ne_vaut_que_sous_copilot(tmp_path):
    """La jambe Codex reçoit la charge du sous-agent Copilot telle quelle : elle refuse quand même — le
    filtre est borné à `AGENTS_HOOK_HOST=copilot`, jamais une sortie offerte aux autres hôtes."""
    leg = _one(_codex_stop(), "affirmation-guard.sh", "command")["command"]
    repo = _fixture(tmp_path)
    verdict = json.loads(_jouer(leg, repo, P4_AGENTSTOP_SOUS_AGENT))
    assert verdict.get("decision") == "block"


# Les charges RÉELLES du `Stop` de `.claude/settings.json` exécuté par Copilot (canari P4, 2026-10-13,
# Copilot CLI 1.0.95, `rt/copilot-via-claude/P4/Stop-081646-60919.json` puis `Stop-081652-61445.json`),
# home -> /home/user, identifiants -> SESSION_RACINE / SOUS_AGENT. Copilot TRADUIT la charge en snake_case,
# sans marqueur d'hôte ; le transcript est celui de la session RACINE aux deux tirs.
_P4_CWD = "/home/user/.local/state/cadre/semaine/clones/rt-copilot"
P4_REGISTRE_CLAUDE_SOUS_AGENT = {
    "hook_event_name": "Stop", "session_id": SOUS_AGENT, "timestamp": "2026-10-13T06:16:44.740Z",
    "cwd": _P4_CWD, "transcript_path": TRANSCRIPT_P4, "stop_reason": "end_turn", "stop_hook_active": False,
}
P4_REGISTRE_CLAUDE_RACINE = {
    "hook_event_name": "Stop", "session_id": SESSION_RACINE, "timestamp": "2026-10-13T06:16:50.747Z",
    "cwd": _P4_CWD, "transcript_path": TRANSCRIPT_P4, "stop_reason": "end_turn", "stop_hook_active": False,
}
# La charge RÉELLE du `Stop` Codex (X1, 2026-10-12, `rt/codex/X1/Stop-140349-93563.json`), home -> /home/user,
# model -> gpt-6-sol, `last_assistant_message` abrégé (la garde ne lit ni l'un ni l'autre).
CODEX_X1_STOP = {
    "session_id": "01a12fff-13e9-7311-87d6-2bddb11e8d81", "turn_id": "01a12fff-1477-7fe3-bd9b-ac93d3ce22d1",
    "transcript_path": "/home/user/.codex/sessions/2026/10/12/"
                       "rollout-2026-10-12T14-03-28-01a12fff-13e9-7311-87d6-2bddb11e8d81.jsonl",
    "cwd": "/home/user/.local/state/cadre/semaine/clones/rt-codex", "hook_event_name": "Stop",
    "model": "gpt-6-sol", "permission_mode": "bypassPermissions", "stop_hook_active": False,
    "last_assistant_message": "COVERAGE DEGRADED — restitution directe, sous-agent interdit.",
}


def _jouer_claude(leg: str, repo: Path, payload: dict) -> str:
    """La jambe du registre Claude telle que l'hôte la lance : racine dans `CLAUDE_PROJECT_DIR`, AUCUN
    marqueur `AGENTS_HOOK_HOST` (Copilot n'en pose pas sur ce registre, P4)."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "AGENTS_HOOK_HOST") and not k.startswith("GIT_")}
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    run = subprocess.run(["bash", "-c", leg], cwd=repo, env=env, input=json.dumps(payload),
                         capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stderr
    return run.stdout


def test_registre_claude_sous_copilot_tait_le_sous_agent_juge_la_racine_sans_agentstop_et_codex(tmp_path):
    """La jambe `Stop` ENREGISTRÉE de `.claude/settings.json` (entrée `affirmation-guard.sh`), rejouée telle
    quelle : la fin de sous-agent MESURÉE sous Copilot rend ZÉRO OCTET ; la racine MESURÉE est REFUSÉE tant
    que `.github/hooks/agent-guardrails.json` ne câble pas la garde sur `agentStop` (cette jambe est alors la
    SEULE à juger la racine), puis rend ZÉRO OCTET une fois le registre natif posé (il juge alors la racine) ;
    la charge Codex X1, sur le MÊME arbre armé et sale, est REFUSÉE (contrôle apparié : le filtre ne tait pas
    toute charge sans marqueur)."""
    leg = _one(_claude_stop(), "affirmation-guard.sh", "command")["command"]
    repo = _fixture(tmp_path)
    assert _jouer_claude(leg, repo, P4_REGISTRE_CLAUDE_SOUS_AGENT) == "", "fin de sous-agent jugée"
    # Sans `.github/hooks/`, la jambe du registre Claude est la SEULE à juger la racine.
    sans = json.loads(_jouer_claude(leg, repo, P4_REGISTRE_CLAUDE_RACINE))
    assert sans.get("decision") == "block", "racine sans jambe agentStop : plus aucune garde"
    (repo / ".github" / "hooks").mkdir(parents=True)
    shutil.copy2(COPILOT, repo / ".github" / "hooks" / "agent-guardrails.json")
    assert _jouer_claude(leg, repo, P4_REGISTRE_CLAUDE_RACINE) == "", "racine jugée deux fois sous Copilot"
    verdict = json.loads(_jouer_claude(leg, repo, CODEX_X1_STOP))
    assert verdict.get("decision") == "block"
    assert "PLAN-ETAT.md" in verdict.get("reason", "")


# La charge RÉELLE de `subagentStop` Copilot (canari P4, 2026-10-12) : `agentType` porte le nom de la déf.
P4_SUBAGENT_STOP = {
    "sessionId": "412fbc8b-fdbe-4a0f-837e-085056ae4429", "timestamp": 1791811232346, "cwd": "/x",
    "agentId": "af8e4d9a-0536-414f-9d0f-9eea7fda1a67", "agentType": "plan-critic",
    "agentName": "plan-critic", "agentDisplayName": "plan-critic", "response": "OK", "stopReason": "end_turn",
}


def test_la_jambe_subagentstop_enregistree_ecrit_la_trace_du_critique_de_plan(tmp_path):
    leg = _one(_copilot("subagentStop"), "plan_trace.py", "bash")["bash"]
    repo = tmp_path / "depot"
    (repo / ".agents/bin").mkdir(parents=True)
    shutil.copy2(ROOT / ".agents/pyrun.sh", repo / ".agents/pyrun.sh")
    shutil.copy2(ROOT / ".agents/bin/plan_trace.py", repo / ".agents/bin/plan_trace.py")
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "AGENTS_HOOK_HOST") and not k.startswith("GIT_")}
    run = subprocess.run(["bash", "-c", leg], cwd=repo, env=env, input=json.dumps(P4_SUBAGENT_STOP),
                         capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stderr
    trace = repo / ".agents/state/local/plan/plan-critic.json"
    assert trace.is_file(), "aucune trace écrite : la jambe Copilot ne nourrit pas la chaîne de plan"
    charge = json.loads(trace.read_text(encoding="utf-8"))
    assert charge["role"] == "reviewer"
    # L'ARBRE NE PORTE PAS `agent_chrono.py` (T-01M55Z3ZCS34CDR2EQN1CEBHR7) : son chargement est sous
    # `try`, donc la trace s'écrit quand même, et la charge reste EXACTEMENT celle d'avant le chrono.
    assert set(charge) == {"at", "sha", "role"}, charge
