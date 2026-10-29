"""Dégradations de couverture du pont V3 vues par le dashboard (T-00001006).

`gate.coverage_degraded` a un second émetteur (`tasks_sync.py`) : l'onglet MCP ne compte plus que la famille `mcp_*` et les
dégradations qu'il ne sait pas attribuer ; la vue Couverture les compte toutes. Règle des 1600 lignes par `.py` (S-00002684, S-00004034) :
ces témoins vivent hors de `test_dashboard.py`, dont ils importent les fixtures autouse (`_redirect`, `_drain_streams`) et les
outils (`_views`, `_write_line`, `_rec`) — même isolation que le fichier d'origine.
"""
from __future__ import annotations

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect  # noqa: F401 — fixtures autouse, ré-exposées pour CE module

readers, _views, _write_line, _rec = td.readers, td._views, td._write_line, td._rec


def _ecrire_degradation(_redirect, heure: int, data, host="claude") -> None:
    record = _rec(f"2026-07-28T0{heure}:00:00Z", kind="gate.coverage_degraded")
    record["data"] = data
    record["host"] = host
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", record)


def test_mcp_usage_counts_only_mcp_family_degradations(_redirect):
    """`gate.coverage_degraded` a un second émetteur (le pont V3, T-00001006) : ses CINQ raisons (`pont-v3-refuse`,
    `pont-v3-panne`, `sync-outbox-deverse`, `sync-outbox-deverse-impossible`, `sync-outbox-rejeu-impossible`) ne sont PAS
    des dégradations MCP ; la vue Couverture, elle, les compte toutes.
    MUTATIONS : D1 (filtre retiré) et D7 (préfixe vidé) -> 6 != 1."""
    raisons = ["pont-v3-refuse", "pont-v3-panne", "sync-outbox-deverse", "sync-outbox-deverse-impossible",
               "sync-outbox-rejeu-impossible"]
    for i, reason in enumerate(["mcp_resolution_failed:audited-pkg", *raisons]):
        _ecrire_degradation(_redirect, i, {"reason": reason})
    views = _views(_redirect)
    assert views["mcp"]["usage"]["coverage_degraded_events"] == 1
    assert views["coverage"]["coverage_degraded"]["count"] == 6
    assert all(views["coverage"]["coverage_degraded"]["by_reason"][r] == 1 for r in raisons)


def test_mcp_usage_a_pont_v3_refusal_alone_leaves_the_mcp_count_at_zero(_redirect):
    """Un refus du pont seul : 0 dans l'onglet MCP. MUTATIONS : D1, D7."""
    _ecrire_degradation(_redirect, 0, {"reason": "pont-v3-refuse"})
    assert _views(_redirect)["mcp"]["usage"]["coverage_degraded_events"] == 0


def test_mcp_usage_keeps_reasonless_degradations_as_unattributed():
    """Sept enregistrements, lus par le VRAI `_mcp_usage` (chemins dégradés d'`events.emit` : `{"truncated": true}`
    `{"redaction_unavailable": true}`, `data` nul) : MCP 1, non attribuées 5 (troncature, rédaction,
    `data` nul, `data: []`, `reason: 7`), `coverage_degraded_events` 6. MUTATIONS : D2 (non-attribuées exclues :
    filtre de rév. 2 -> 1), D4 (`isinstance(data, dict)` -> `data is None` : `data: []` perdu -> 5), D5
    (`isinstance(reason, str)` -> `reason is None` : `7.startswith` lève)."""
    def enr(data):
        return {"kind": "gate.coverage_degraded", "data": data}
    flux = {"status": "ok", "records": [
        enr({"reason": "mcp_resolution_failed:audited-pkg"}), enr({"reason": "pont-v3-refuse"}),
        enr({"truncated": True}), enr({"redaction_unavailable": True}), enr(None), enr([]), enr({"reason": 7})]}
    usage = readers._mcp_usage(flux, {})
    assert usage["coverage_degraded_events"] == 6
    assert usage["coverage_degraded_unattributed"] == 5


def test_mcp_usage_unusable_trail_carries_both_degradation_counters(_redirect):
    """Flux inutilisable (`trail_absent`, aucun dossier d'événements) : les DEUX clés valent 0, dans la branche
    de retour courte. MUTATION D3 (clé absente de cette branche) -> KeyError."""
    usage = _views(_redirect)["mcp"]["usage"]
    assert usage["status"] == "trail_absent"
    assert usage["coverage_degraded_events"] == 0
    assert usage["coverage_degraded_unattributed"] == 0


def test_canal_a_emitters_names_both_emitters_of_gate_coverage_degraded():
    """MUTATION D6 (registre à un seul émetteur) -> rouge."""
    declared = readers.CANAL_A_EMITTERS["gate.coverage_degraded"]
    assert ".claude/hooks/mcp-events.sh" in declared and ".agents/bin/tasks_sync.py" in declared


def test_characterisation_a_pont_v3_event_without_host_leaves_the_claude_matrix_cell_empty(_redirect):
    """LIMITE NON LIVRÉE, CARACTÉRISÉE (critique B it.5 C5) : `tasks.py` ne pose `host` que sous un hook (`AGENTS_HOOK_HOST`) ; hors
    hook, l'événement est compté dans le panneau « Dégradations de couverture » (2) mais la cellule `claude` de la ligne
    `gate.coverage_degraded` de la matrice reste `no_data_yet`, `count 0`. Le jour où `host` est fiabilisé, ce témoin ROUGIT :
    il faut alors retirer la ligne « NON livré » du plan et du README, jamais le faire passer au vert en silence."""
    for i in range(2):
        _ecrire_degradation(_redirect, i, {"reason": "pont-v3-refuse"}, host=None)
    coverage = _views(_redirect)["coverage"]
    assert coverage["coverage_degraded"]["count"] == 2
    ligne = coverage["canal_a"]["matrix"]["gate.coverage_degraded"]
    assert ligne["claude"] == {"status": "no_data_yet", "count": 0}


def test_characterisation_a_pont_v3_event_without_host_is_listed_as_an_unexpected_host(_redirect):
    """LIMITE NON LIVRÉE, CARACTÉRISÉE (critique B it.5 C5) : le même événement sans `host` est rangé sous `unknown`, hors
    `CANAL_A_HOSTS` : `unexpected_hosts == ['unknown']`, ce que le bloc `unexpected_hosts` de `CoverageTab.jsx` rend en `StateBlock` « partial »
    (« hôte(s) observé(s) hors matrice : unknown », rendu CÂBLÉ, non regardé dans un navigateur)."""
    _ecrire_degradation(_redirect, 0, {"reason": "pont-v3-refuse"}, host=None)
    assert _views(_redirect)["coverage"]["canal_a"]["unexpected_hosts"] == ["unknown"]
