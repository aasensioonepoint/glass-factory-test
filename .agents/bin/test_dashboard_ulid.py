"""Le tableau de bord reconnaît les ids ULID (T-00001041, étape 5 / C1d du plan de T-00000726).

`_TASK_ID_RE` et `_SPECS_ID_RE` (dashboard.py) gardent les routes d'écriture `/api/actions/gate` et
`/api/actions/board` : un id qu'elles refusent rend un 400 `bad_task` / `bad_specs_id` AVANT toute CLI. Après la
bascule C2, `tasks.py new` et `specs.py add` frappent `T-<ULID>` / `S-<ULID>` (26 caractères Crockford, majuscules,
sans I L O U) et les ids numériques restent des alias GELÉS. Ces témoins tiennent les deux colonnes : la forme
élargie ACCEPTE l'ULID et l'ancien, et REFUSE ce qu'aucun écrivain ne frappe — 27 ou 25 caractères, minuscules,
I/L/O/U, suffixe, et le `\\n` final que le `$` de Python laisse passer et que `\\A…\\Z` refuse (M8, M8').
SAUF les chiffres Unicode non ASCII : `\\d` les admet sur la branche numérique (`T-\\u0663\\u0664`, `T-\\uff11` passent,
mesuré à la clôture du lot 95d6220a..c964c9a6, F8) — résidu NOMMÉ de T-00001070, que ces témoins ne tiennent pas.

1(f) (bascule C2) : `build_snapshot` sous les trois écrivains RÉELS (`new_task`, `specs.add_entry`,
`ledger.add_entry`) rend trois rangées `P-<ULID>` et aucun `next_id` ; un magasin qui porte encore la clé est relu sans.

Règle des 1600 lignes (S-00002684, S-00004034) et cliquet E23 : ces témoins vivent hors de `test_dashboard.py`,
dont ils importent les fixtures autouse (`_redirect`, `_drain_streams`), le serveur (`ui_server`) et les outils —
même isolation que le fichier d'origine (comme `test_dashboard_sans_dependances.py`).
"""
from __future__ import annotations

import json
import re

import pytest

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect, ui_server  # noqa: F401 — fixtures, ré-exposées pour CE module

dashboard, _post_json, _GATE, _BOARD = td.dashboard, td._post_json, td._GATE, td._BOARD
_seed_plan, _new_task, tasks_mod = td._seed_plan, td._new_task, td.tasks_mod

# Fixtures LITTÉRALES (table du plan, `front-temoins.md`), validées par le premier témoin.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"
U_ALLDIG = "02000000001234567890123456"
_ULID = re.compile(r"\A[0-9A-HJKMNP-TV-Z]{26}\Z")


def _etranger(ch: str) -> str:
    """26 caractères de [0-9A-Z] dont UN hors Crockford ; la queue reste une lettre."""
    return U_LETTER[:12] + ch + U_LETTER[13:]


# Corps qu'aucun écrivain ne frappe : chacun est refusé derrière `T-` comme derrière `S-`.
MAL_FORMES = [
    "0" + U_LETTER,  # 27 caractères
    U_LETTER[1:],  # 25 caractères
    U_LETTER.lower(),
    U_LETTER[:25] + "m",
    _etranger("I"), _etranger("L"), _etranger("O"), _etranger("U"),
    U_LETTER + "\n",  # M8' : `$` l'accepte, `\Z` non
    U_LETTER + "A",
    U_LETTER + " ",
    "00000001\n",  # M8' sur la branche numérique
    "1234567890123",  # la borne numérique {1,12} est gardée
    "",
]
ANCIENS = ["1", "012", "00000028", "123456789012"]


def test_les_fixtures_sont_des_ULID_et_les_contre_fixtures_n_en_sont_pas():
    for u in (U_LETTER, U_DIGIT, U_ALLDIG):
        assert _ULID.match(u), u
    for corps in MAL_FORMES:
        assert not _ULID.match(corps), corps


@pytest.mark.parametrize("nom,prefixe,autre", [("_TASK_ID_RE", "T-", "S-"), ("_SPECS_ID_RE", "S-", "T-")])
def test_les_deux_constantes_acceptent_l_ULID_et_l_ancien_et_refusent_le_reste(nom, prefixe, autre):
    """`.match`, comme aux sites d'appel (:4138, :4144, :4255). MUTANTS : ancres retirées -> `…A` accepté ;
    `\\Z` revenu à `$` -> `…\\n` accepté ; branche ULID absente ou en minuscules -> l'ULID refusé ou `…m` accepté."""
    rx = getattr(dashboard, nom)
    for corps in (U_LETTER, U_DIGIT, U_ALLDIG, *ANCIENS):
        assert rx.match(prefixe + corps), prefixe + corps
    for corps in MAL_FORMES:
        assert not rx.match(prefixe + corps), repr(prefixe + corps)
    assert not rx.match(autre + U_LETTER)
    assert not rx.match(U_LETTER)


def test_le_gate_laisse_passer_une_tache_ULID_jusqu_a_la_relecture_du_journal(ui_server, _redirect):
    """Une tâche `T-<ULID>` sans plan journalisé atteint la relecture de `specs.py` (:4150) : 409
    `no_plan_recorded`, et non un 400 `bad_task` — le refus vient du JOURNAL, pas de la forme de l'id."""
    port, token = ui_server
    resp = _post_json(port, _GATE, {"task": f"T-{U_LETTER}", "decision": "approved", "confirm": True},
                      token=token)
    assert resp.status == 409, resp.data
    assert json.loads(resp.data)["error"] == "no_plan_recorded"


def test_le_gate_laisse_passer_une_entree_S_ULID_jusqu_a_la_relecture_du_journal(ui_server, _redirect):
    """`specs_id = S-<ULID>` passe `_SPECS_ID_RE` : le serveur relit le journal et ne l'y trouve pas (C1 ne frappe
    aucun ULID) -> 409 `specs_id_not_in_plan`, jamais un 400 `bad_specs_id`."""
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    for corps in (U_LETTER, U_ALLDIG):
        resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved", "confirm": True,
                                        "specs_id": f"S-{corps}"}, token=token)
        assert resp.status == 409, resp.data
        assert json.loads(resp.data)["error"] == "specs_id_not_in_plan"


@pytest.mark.parametrize("corps", MAL_FORMES)
def test_le_gate_refuse_un_ULID_mal_forme_avant_toute_CLI(ui_server, _redirect, corps):
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    resp = _post_json(port, _GATE, {"task": f"T-{corps}", "decision": "approved", "confirm": True},
                      token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == "bad_task"
    resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved", "confirm": True,
                                    "specs_id": f"S-{corps}"}, token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == "bad_specs_id"
    assert not list(_redirect["events_dir"].glob("*.jsonl"))


def test_le_board_agit_sur_une_tache_ULID_et_refuse_un_ULID_mal_forme(ui_server, _redirect):
    """Après C2, `_new_task` rend un `T-<ULID>` : la route doit le passer à la CLI. Le magasin est écrit par
    `save` du VRAI module (C1 ne frappe pas d'ULID, la tâche y est donc RENOMMÉE) ; `start` réussit de bout en
    bout. MUTANT : `_TASK_ID_RE` laissée étroite -> 400 `bad_task`."""
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    data = tasks_mod.load(root)
    tache = next(t for t in data["tasks"] if t["id"] == tid)
    tache["id"] = f"T-{U_DIGIT}"
    tasks_mod.save(root, data)
    resp = _post_json(port, _BOARD, {"action": "start", "task": f"T-{U_DIGIT}"}, token=token)
    corps = json.loads(resp.data)
    assert resp.status == 200, corps
    assert corps["ok"] is True, corps
    assert tasks_mod.find(tasks_mod.load(root), f"T-{U_DIGIT}")["state"] == "running"
    for mal in MAL_FORMES:
        resp = _post_json(port, _BOARD, {"action": "start", "task": f"T-{mal}"}, token=token)
        assert resp.status == 400, repr(mal)
        assert json.loads(resp.data)["error"] == "bad_task"


# 1(f) (C2, T-00000726) — le snapshot SOUS LA BASCULE : les trois écrivains RÉELS frappent `P-<ULID>` et aucun
# magasin ne porte plus de compteur ; un magasin d'avant qui en porte encore un est relu SANS (`load` le retire).
_SECTIONS = (("board", "tasks", "T"), ("specs", "entries", "S"), ("ledger", "entries", "L"))


def test_1f_le_snapshot_rend_trois_rangees_ULID_et_aucun_next_id(_redirect):
    """MUTANT M11 (`setdefault("next_id")` restauré dans un `load`) ⇒ la clé revient dans `data`, rouge ; une frappe
    rendue au compteur ⇒ un id `T-0000000N`, rouge. M7 (`save()` qui garde `next_id`) n'est PAS tué ici — `load`
    retire la clé — mais par `test_state_atomic.py` et les `*SaveTrieLesClesTests`."""
    root = _redirect["project_root"]
    ids = {"board": _new_task(root)}
    ids["specs"] = dashboard._specs_mod.add_entry(root, ids["board"], "delta", "entrée de banc").split()[1]
    ids["ledger"] = dashboard._ledger_mod.add_entry(root, "lesson", "leçon de banc", related=ids["board"]).split()[1]
    snap = dashboard.build_snapshot(root)
    for section, cle, prefixe in _SECTIONS:
        assert snap[section]["status"] == "ok", snap[section]
        data = snap[section]["data"]
        assert "next_id" not in data, section
        assert [r["id"] for r in data[cle]] == [ids[section]], section
        assert re.fullmatch(prefixe + "-[0-9A-HJKMNP-TV-Z]{26}", ids[section]), ids[section]


def test_1f_un_magasin_qui_porte_encore_next_id_est_relu_sans(_redirect):
    """Un magasin écrit AVANT la bascule (G-BASCULE pas encore jouée) garde sa clé sur le disque : le snapshot la
    retire, les ids gelés restent tels quels. MUTANT : `load` qui tolère la clé sans la retirer ⇒ rouge."""
    root = _redirect["project_root"]
    anciens = {
        "board": {"next_id": 5, "tasks": [{"id": "T-00000004", "state": "pending", "task": "ancienne", "owner": "",
                                           "stage": "", "updated": "2026-10-01"}]},
        "specs": {"next_id": 5, "entries": [{"id": "S-00000004", "task": "T-00000004", "kind": "plan",
                                             "title": "ancienne", "text": "", "files": [], "date": "2026-10-01"}]},
        "ledger": {"next_id": 5, "entries": [{"id": "L-00000004", "category": "lesson", "title": "ancienne",
                                              "text": "", "created": "2026-10-01", "tags": [], "related": "",
                                              "status": "active"}]},
    }
    modules = {"board": tasks_mod, "specs": dashboard._specs_mod, "ledger": dashboard._ledger_mod}
    for section, donnees in anciens.items():
        chemin = modules[section].store_path(root)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(donnees), encoding="utf-8")
    snap = dashboard.build_snapshot(root)
    for section, cle, prefixe in _SECTIONS:
        data = snap[section]["data"]
        assert "next_id" not in data, section
        assert [r["id"] for r in data[cle]] == [f"{prefixe}-00000004"], section
