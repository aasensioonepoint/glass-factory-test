"""Le tableau de bord relaie `--sans-dependances` à `tasks.py` (T-00000951).

`tasks.py start|done` portent la sortie tracée `--sans-dependances "<pourquoi>"` de la garde des arêtes du plan
(T-00000765). `_action_board` relayait déjà `sans_cible` sur ces deux gestes, mais AVALAIT `sans_dependances` : un
client qui la demandait voyait le refus de la garde remonter sans issue. Règle des 1600 lignes (S-00002684, S-00004034) : ces témoins
vivent hors de `test_dashboard.py`, dont ils importent les fixtures autouse (`_redirect`, `_drain_streams`), le serveur
(`ui_server`) et les outils — même isolation que le fichier d'origine.
"""
from __future__ import annotations

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect, ui_server  # noqa: F401 — fixtures, ré-exposées pour CE module

dashboard, _post_body, _BOARD, _new_task = td.dashboard, td._post_body, td._BOARD, td._new_task


def _espion(monkeypatch) -> list[list[str]]:
    """Note chaque argv passé à `_run_cli`, qui reste le VRAI : c'est la CLI qui juge l'option relayée."""
    reel = dashboard._run_cli
    lances: list[list[str]] = []

    def spy(argv, **kwargs):
        lances.append(list(argv))
        return reel(argv, **kwargs)

    monkeypatch.setattr(dashboard, "_run_cli", spy)
    return lances


def _argv_tasks(lances: list[list[str]]) -> list[str]:
    return next(a for a in lances if any(x.endswith("tasks.py") for x in a))


def test_sans_dependances_relaye_start_et_done(ui_server, _redirect, monkeypatch):
    """MUTANT : relais `sans_dependances` retiré (l'option AVALÉE) -> l'élément manque à l'argv de `tasks.py`.
    `ok True` prouve en plus que la CLI ACCEPTE l'option sous cette forme : un drapeau mal nommé serait refusé.
    Au `done`, `sans_cible` est demandé AVEC elle : les deux partent (MUTANT : un seul relais par geste)."""
    port, token = ui_server
    lances = _espion(monkeypatch)
    tid = _new_task(_redirect["project_root"])
    body = _post_body(port, _BOARD, {"action": "start", "task": tid,
                                     "sans_dependances": "arete levee au banc"}, token=token)
    assert body["ok"] is True
    assert "--sans-dependances=arete levee au banc" in _argv_tasks(lances)

    lances.clear()
    body = _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc",
                                     "sans_cible": "nuit autonome",
                                     "sans_dependances": "plan perime"}, token=token)
    assert body["ok"] is True
    argv_done = _argv_tasks(lances)
    assert "--sans-dependances=plan perime" in argv_done
    assert "--sans-cible=nuit autonome" in argv_done


def test_sans_dependances_jamais_supposee_ni_relayee_hors_start_done(ui_server, _redirect, monkeypatch):
    """La dérogation n'est JAMAIS supposée : sans le champ, ou avec un champ vide ou non textuel, aucun
    `--sans-dependances` ne part (MUTANT : relais inconditionnel). `block` ne la relaie pas : son parseur n'a pas ce
    drapeau, et le relayer ferait refuser le geste (MUTANT : relais sur toute action -> `ok False`)."""
    port, token = ui_server
    lances = _espion(monkeypatch)
    root = _redirect["project_root"]
    for champ in ({}, {"sans_dependances": "   "}, {"sans_dependances": 7}):
        lances.clear()
        body = _post_body(port, _BOARD, {"action": "start", "task": _new_task(root), **champ}, token=token)
        assert body["ok"] is True
        assert not any(x.startswith("--sans-dependances") for x in _argv_tasks(lances)), champ

    lances.clear()
    body = _post_body(port, _BOARD, {"action": "block", "task": _new_task(root), "note": "attend une decision",
                                     "sans_dependances": "hors propos"}, token=token)
    assert body["ok"] is True
    assert not any(x.startswith("--sans-dependances") for x in _argv_tasks(lances))
