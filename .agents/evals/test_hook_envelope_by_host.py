"""Banc d'ENVELOPPE PAR HOTE (alignement des hotes, lot L-A ; H-25, H-26, H-63).

CE QUE LES BANCS DE PARITE NE JUGENT PAS. `test_guard_decision_parity.py` et
`test_events_parity.py` jugent la DECISION d'une garde (refuser ou laisser passer)
et FIGENT l'enveloppe a rc 0 ; aucun ne juge l'enveloppe TELLE QUE L'HOTE LA LIT.
Mesure du 2026-10-12 (Copilot CLI 1.0.95, P1) : l'enveloppe imbriquee
`hookSpecificOutput.permissionDecision` est IGNOREE par Copilot (le fichier est
cree), et `permissionDecision` a la RACINE est honoree (P1v : `denied`). Meme
ecart pour `additionalContext` de `sessionStart` (a la racine dans la doc ; le
contexte imbrique n'est jamais livre, P3).

CE QUE CE BANC TIENT, hote par hote :
  * copilot : la RACINE ET l'objet imbrique portent la decision / le contexte ;
  * codex, gemini : AUCUNE cle racine (octets inchanges) ;
  * `kickoff_guard.emit_refusal` suit les memes cellules ;
  * `kickoff_guard.main` ATTEINT ce refus sous copilot : la charge reelle P1
    (`create`, `toolArgs` objet ou chaine JSON) sur un depot jetable arme est
    refusee a la racine, et un `create` hors du perimetre arme passe.

CE QU'IL NE PROUVE PAS : que Copilot lit la racine `additionalContext` (documentee
par le SDK 1.0.95, jamais rejouee) ; la decision de refus, elle, a ete mesuree au
runtime (P1v) pour protect_paths — le kickoff, lui, n'est rejoue que
STATIQUEMENT dans le module. Il ne lance aucun hote.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOSSIERS = (".codex", ".gemini")

P1 = {"toolName": "create",
      "toolArgs": {"path": f"{ROOT}/src/legacy/x.py", "file_text": "x"}}
P2 = {"toolName": "bash", "toolArgs": {"command": "rm README-OTHER-HOSTS.md"}}


def _env(host: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "AGENTS_HOOK_HOST"}
    if host:
        env["AGENTS_HOOK_HOST"] = host
    return env


def _hook(dossier: str, script: str, payload: dict, host: str) -> dict:
    run = subprocess.run(
        [sys.executable, str(ROOT / dossier / "hooks" / script)],
        input=json.dumps(payload), capture_output=True, text=True,
        cwd=ROOT, env=_env(host), timeout=60, check=False,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip(), f"{dossier}/{script} : sortie vide sous {host or 'absent'}"
    return json.loads(run.stdout)


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("dossier", DOSSIERS)
@pytest.mark.parametrize("script,payload", (("protect_paths.py", P1), ("safe_bash.py", P2)))
def test_copilot_refus_a_la_racine_et_imbrique(dossier, script, payload):
    out = _hook(dossier, script, payload, "copilot")
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"]
    nested = out["hookSpecificOutput"]
    assert nested["permissionDecision"] == "deny"
    assert nested["permissionDecisionReason"] == out["permissionDecisionReason"]


@pytest.mark.parametrize("dossier", DOSSIERS)
@pytest.mark.parametrize("host", ("codex", "gemini"))
@pytest.mark.parametrize("script,payload", (("protect_paths.py", P1), ("safe_bash.py", P2)))
def test_hors_copilot_aucune_cle_racine(dossier, host, script, payload):
    out = _hook(dossier, script, payload, host)
    assert set(out) == {"hookSpecificOutput"}, f"cle racine sous {host}: {sorted(out)}"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("dossier", DOSSIERS)
def test_contexte_de_session_racine_sous_copilot_seulement(dossier, monkeypatch):
    common = _load(f"{dossier}/hooks/_common.py", f"_common_{dossier[1:]}")
    for host, racine in (("copilot", True), ("codex", False), ("gemini", False)):
        # monkeypatch restaure la valeur d'origine (presente ou absente) a la fin
        # du cas : le banc ne touche jamais l'environnement des cas suivants.
        monkeypatch.setenv("AGENTS_HOOK_HOST", host)
        buf = io.StringIO()
        with redirect_stdout(buf):
            common.additional_context("BOARD-OK")
        out = json.loads(buf.getvalue())
        assert out["hookSpecificOutput"]["additionalContext"] == "BOARD-OK"
        assert ("additionalContext" in out) is racine, f"{host}: {sorted(out)}"
        if racine:
            assert out["additionalContext"] == "BOARD-OK"
    # session_context.py PASSE par ce helper (lecture statique : aucun hote lance,
    # aucune reconstruction d'index dans l'arbre juge).
    src = (ROOT / dossier / "hooks" / "session_context.py").read_text(encoding="utf-8")
    assert "additional_context(" in src


def test_emit_refusal_par_hote():
    kg = _load(".agents/bin/kickoff_guard.py", "kickoff_guard_envelope_banc")
    decision = kg.Decision(allowed=False, rule="r", reason="MOTIF-DE-REFUS")
    sortie = {}
    for host in ("copilot", "codex", "gemini", "claude"):
        out, err = io.StringIO(), io.StringIO()
        rc = kg.emit_refusal(decision, host, out=out, err=err)
        sortie[host] = (rc, out.getvalue(), err.getvalue())
    rc, out, _err = sortie["copilot"]
    env = json.loads(out)
    assert rc == 0
    assert env["permissionDecision"] == "deny"
    assert env["permissionDecisionReason"] == "MOTIF-DE-REFUS"
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    for host in ("codex", "gemini"):
        rc, out, _err = sortie[host]
        assert rc == 0
        assert set(json.loads(out)) == {"hookSpecificOutput"}
    rc, out, err = sortie["claude"]
    assert rc == 2 and out == "" and "MOTIF-DE-REFUS" in err


# --- LE KICKOFF SOUS COPILOT, DE BOUT EN BOUT DANS LE MODULE (delta S-01M4RWVN2K) ---
# `emit_refusal` ci-dessus ne prouve rien si `main()` n'y arrive jamais : sous
# Copilot l'outil d'ecriture s'appelle `create`, et un nom absent de
# WRITE_TOOL_NAMES fait sortir `main()` a rc 0 AVANT la porte. La charge est la
# charge REELLE P1 (Copilot CLI 1.0.95, 2026-10-12, capture
# `rt/copilot/P1/preToolUse-151821-74589.json`) : memes cles, meme forme
# (`toolArgs` objet {path, file_text}) ; sessionId, timestamp et chemins
# personnels remplaces par des valeurs neutres, le chemin pointe dans un depot
# JETABLE. Rejeu STATIQUE dans le module : aucun hote lance.


def _depot_arme(racine: Path, kg) -> Path:
    """Depot jetable ARME : T-1 a la porte, `pending` (pas `running`), write-set
    `src/`, un plan au journal — toute ecriture sous `src/` est refusee
    (`not-running`), toute ecriture hors de `src/` passe."""
    for sous in ("board", "specs", "gates"):
        (racine / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
    (racine / kg.GATE_RELPATH).write_text("T-1\n", encoding="utf-8")
    (racine / ".agents" / "state" / "board" / "TASKS.json").write_text(json.dumps(
        {"next_id": 2, "tasks": [{"id": "T-1", "state": "pending", "task": "t",
                                  "writeset": ["src/"]}]}), encoding="utf-8")
    (racine / ".agents" / "state" / "specs" / "SPECS.json").write_text(json.dumps(
        {"next_id": 2, "entries": [{"id": "S-00000001", "task": "T-1", "kind": "plan",
                                    "title": "p", "text": "", "files": [],
                                    "date": "2026-10-12"}]}), encoding="utf-8")
    return racine


def _charge_p1_create(racine: Path, rel: str, args_en_chaine: bool = False) -> dict:
    args = {"path": str(racine / rel), "file_text": "ok\n"}
    return {
        "sessionId": "00000000-0000-0000-0000-000000000000",
        "timestamp": 0,
        "cwd": str(racine),
        "toolName": "create",
        # Copilot peut livrer toolArgs en CHAINE JSON : tool_args() la decode.
        "toolArgs": json.dumps(args) if args_en_chaine else args,
    }


def _kickoff_main(kg, racine: Path, charge: dict, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENTS_HOOK_HOST", "copilot")
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setattr(kg, "repo_root", lambda: racine)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(charge)))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = kg.main()
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("args_en_chaine", (False, True), ids=("toolArgs-objet", "toolArgs-chaine"))
def test_kickoff_charge_reelle_create_refusee_a_la_racine(args_en_chaine, monkeypatch, tmp_path):
    kg = _load(".agents/bin/kickoff_guard.py", "kickoff_guard_create_banc")
    racine = _depot_arme((tmp_path / "depot").resolve(), kg)
    charge = _charge_p1_create(racine, "src/ok.txt", args_en_chaine)
    rc, out, err = _kickoff_main(kg, racine, charge, monkeypatch, tmp_path)
    assert rc == 0 and err == "", (rc, err)
    assert out.strip(), "aucun refus : main() est sorti avant la porte"
    assert kg.is_write_form(charge), "`create` (Copilot) doit etre une forme d'ecriture"
    env = json.loads(out)
    assert env["permissionDecision"] == "deny"
    assert "kickoff" in env["permissionDecisionReason"]
    assert env["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert env["hookSpecificOutput"]["permissionDecisionReason"] == env["permissionDecisionReason"]


def test_kickoff_create_hors_perimetre_arme_passe(monkeypatch, tmp_path):
    kg = _load(".agents/bin/kickoff_guard.py", "kickoff_guard_create_banc")
    racine = _depot_arme((tmp_path / "depot").resolve(), kg)
    charge = _charge_p1_create(racine, "docs/ok.txt")
    assert _kickoff_main(kg, racine, charge, monkeypatch, tmp_path) == (0, "", "")
