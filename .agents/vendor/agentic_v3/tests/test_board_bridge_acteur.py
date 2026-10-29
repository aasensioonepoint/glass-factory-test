"""Banc FRÈRE de `test_board_bridge.py` (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot B : l'acteur du pont V3).

Déplacé À L'IDENTIQUE depuis `test_board_bridge.py`, qui est à son plafond de longueur (cliquet) ;
seule la source de l'instantané change : `_snapshot`, recopie de `BoardBridgeTests.snapshot`.
Aucun parcours d'arbre ici (`test_repo_walk_census.py`).
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """Recopie de `test_board_bridge.py::_isolation_export_run` : l'export sous une racine de TEST
    (`CADRE_PROJECT_ROOT`), la base machine sous `CADRE_STATE_DIR`, l'auteur fixé par la porte UNIQUE
    `conftest.greffe_email_git_franchissable` (franchissable, L-00000500)."""
    from conftest import greffe_email_git_franchissable
    from agentic_v3.db import run_export

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)


def _snapshot(task_id: str, state: str, *, title: str = "Task", stage: str = "") -> dict[str, str]:
    """Recopie de `test_board_bridge.BoardBridgeTests.snapshot`."""
    return {
        "id": task_id,
        "state": state,
        "task": title,
        "owner": "dev-multi",
        "stage": stage,
        "updated": "2026-08-07",
    }


def test_pont_v3_acteur_explicite(tmp_path, monkeypatch) -> None:
    """LE PONT V3 SIGNE « pont V3 », JAMAIS L'IDENTITÉ DU CLONE (T-01M5DBFK3XKKM2VHQM5RE4TP6K,
    lot B). Ses deux écritures de stage — ``stage_running_task`` (Sdev) et ``set_state`` (D) —
    posent ``stage_actor = {auteur:{nom:"pont V3",email:null},copie:null}`` ; ``start_actor``
    (Alice, qui a démarré) n'est jamais touché ; aucune identité locale n'est lue (C25 : chaque
    lecture est ENREGISTRÉE ici, jamais levée — une levée serait avalée). Un ``tasks.py`` d'avant
    le lot A, sans ``acteur=``, n'en reçoit pas.
    MUTANTS rouges : acteur omis sur l'un des appels ; ``tasks.acteur_courant`` lu à la place ;
    copie ou email non nuls ; ``_acteur_si_accepte`` qui passe l'acteur sans regarder la signature."""
    from agentic_v3.reconciliation.board_bridge import BoardBridge

    root = tmp_path / "racine"
    alice = {"auteur": {"nom": "Alice", "email": "alice@example.test"}, "copie": "0123456789abcdef"}
    attendu = {"auteur": {"nom": "pont V3", "email": None}, "copie": None}
    board_path = root / ".agents" / "state" / "board" / "TASKS.json"
    board_path.parent.mkdir(parents=True)
    tache = dict(_snapshot("T-00000001", "running", stage="plan-critic"),
                 start_actor=alice, stage_actor=alice)
    board_path.write_text(json.dumps({"next_id": 2, "tasks": [tache], "sync_outbox": [],
                                      "sync_correlations": {}}), encoding="utf-8")
    bridge = BoardBridge(root / "v3.db", root)
    tasks = bridge._tasks_module()

    # Sondes qui ENREGISTRENT (revue de clôture FK3X, C5) : une sonde qui lève serait avalée par un
    # `except Exception` du pont et passerait pour « rien lu » ; celles-ci rendent une valeur factice
    # plausible et notent chaque lecture, puis `lus == []` est exigé après chaque reconcile.
    lus: list = []
    factice = {"auteur": {"nom": "Intrus", "email": "intrus@example.test"}, "copie": "fedcba9876543210"}
    monkeypatch.setattr(tasks, "acteur_courant",
                        lambda *a, **k: lus.append("acteur_courant") or (dict(factice), []))
    monkeypatch.setattr(tasks, "acteur_de_la_commande",
                        lambda *a, **k: lus.append("acteur_de_la_commande") or dict(factice))
    monkeypatch.setattr(tasks, "_acteur_git", lambda *a, **k: lus.append("_acteur_git") or None)

    def _tache() -> dict:
        return {t["id"]: t for t in tasks.load(root)["tasks"]}["T-00000001"]

    assert bridge.reconcile_v3_to_board("T-00000001", "IN_DEV", operation_id="v3-op-dev") == "Sdev"
    assert lus == [], f"le pont V3 a lu l'identité locale (C25) : {lus}"
    apres_stage = _tache()
    assert (apres_stage["stage"], apres_stage.get("stage_actor")) == ("dev", attendu)
    assert apres_stage["start_actor"] == alice

    assert bridge.reconcile_v3_to_board("T-00000001", "COMPLETED", operation_id="v3-op-fin") == "D"
    assert lus == [], f"le pont V3 a lu l'identité locale (C25) : {lus}"
    apres_fin = _tache()
    assert apres_fin["state"] == "done"
    assert apres_fin["stage"].startswith("clos par le pont V3")
    assert apres_fin.get("stage_actor") == attendu
    assert apres_fin["start_actor"] == alice

    def _ecrivain_avant_lot_a(root, tid, stage):  # signature d'un tasks.py sans `acteur=`
        return None

    assert BoardBridge._acteur_si_accepte(_ecrivain_avant_lot_a) == {}
    assert BoardBridge._acteur_si_accepte(tasks.set_state) == {"acteur": attendu}
    assert BoardBridge._acteur_si_accepte(object()) == {}  # signature illisible : rien, jamais un TypeError
