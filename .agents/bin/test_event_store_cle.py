"""La clé du store et la clé du mémo des vues (T-00000615, binôme octies : opus F1, F4, F6 ; fable F2).

Hors de `test_dashboard.py` et de `test_event_store.py`, tous deux au plafond du cliquet
(`.agents/evals/python_file_length_cliquet.json`). UNE seule base de fixtures, celle de `test_dashboard.py`
(`_redirect`, `_drain_streams`, autouse, ré-exposées ici comme `test_dashboard_degradations.py`) : deux
`_redirect` autouse dans un même module se disputeraient `AGENTS_EVENTS_DIR`. Cette base ne fige pas l'horloge
de la migration héritée (`merge_day_files`) : chaque ligne de spool s'écrit donc APRÈS `open_store(create=True)`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect  # noqa: F401 — fixtures autouse, ré-exposées pour CE module

dashboard, event_store, _write_line, _rec = td.dashboard, td.event_store, td._write_line, td._rec
_NOW = datetime.fromisoformat("2026-07-29T12:00:00+00:00")


def test_views_memo_key_is_read_before_the_store_rows(_redirect, monkeypatch):
    """Opus F1: a data commit landing while `build_snapshot` reads the store must not be pinned
    under a key that already contains it — the key is read BEFORE the rows, never after."""
    events, root = _redirect["events_dir"], _redirect["project_root"]
    with event_store.open_store(create=True) as store:  # held open, as the daemon holds it
        _write_line(events, "2026-07-29.claude.61.jsonl", _rec("2026-07-29T10:00:00Z", task="T-1"))
        assert store.ingest_once(now=_NOW)["rows_inserted"] == 1
        (events / "2026-07-29.claude.61.jsonl").unlink()
        assert dashboard.build_snapshot(root)["views_meta"]["canal_a_records_read"] == 1
        _write_line(events, "2026-07-29.claude.62.jsonl", _rec("2026-07-29T10:00:01Z", task="T-2"))
        real = dashboard._read_canal_a_trail

        def racing():
            trail = real()  # read BEFORE the commit below
            assert store.ingest_once(now=_NOW + timedelta(seconds=5))["rows_inserted"] == 1
            (events / "2026-07-29.claude.62.jsonl").unlink()  # drained, as the daemon leaves it
            return trail

        monkeypatch.setattr(dashboard, "_read_canal_a_trail", racing)
        dashboard.build_snapshot(root)
        monkeypatch.setattr(dashboard, "_read_canal_a_trail", real)
        assert dashboard.build_snapshot(root)["views_meta"]["canal_a_records_read"] == 2, (
            "a commit during build_snapshot pinned a stale view under a fresh key")


def test_views_memo_key_carries_the_clock_aged_late_flag(_redirect, monkeypatch):
    """Opus F6: `late` ages with the CLOCK (a pending spool file past `_LATE_SECONDS`), not with a
    file — no input moves when the threshold is crossed, so Couverture, the view whose job is
    saying the lag, served the cached `late=False` while `snapshot.ingestion.late` was True."""
    _write_line(_redirect["events_dir"], "2026-07-29.claude.63.jsonl", _rec("2026-07-29T10:00:00Z"))
    monkeypatch.setattr(event_store, "_LATE_SECONDS", 10.0 ** 9)
    first = dashboard.build_snapshot(_redirect["project_root"])
    assert (first["ingestion"]["late"], first["views"]["coverage"]["ingestion"]["late"]) == (False, False)
    monkeypatch.setattr(event_store, "_LATE_SECONDS", 0.0)  # the threshold is crossed, no file moved
    snap = dashboard.build_snapshot(_redirect["project_root"])
    assert snap["ingestion"]["late"] is True, "precondition: the lag is measured"
    assert snap["views"]["coverage"]["ingestion"]["late"] is True, "Couverture served a cached `late`"


def test_a_fold_only_tick_moves_the_store_key(_redirect):
    """Opus F4 / fable F2, the FOLD half of T-00000615: a tick that inserts nothing but folds
    retention commits a DELETE, and the key must move. A bump on insertion alone (`if inserted:`)
    survived 635 tests at octies."""
    events = _redirect["events_dir"]
    with event_store.open_store(create=True) as store:  # held open, as the daemon holds it
        _write_line(events, "2026-07-29.claude.61.jsonl", _rec("2026-07-29T10:00:00Z", task="T-1"))
        assert store.ingest_once(now=_NOW)["rows_inserted"] == 1
        (events / "2026-07-29.claude.61.jsonl").unlink()  # its source gone: the row may fold
        before = event_store.store_fingerprint()
        report = store.ingest_once(now=_NOW + timedelta(days=event_store.RETENTION_DAYS + 2))
        assert (report["rows_inserted"], report["retention"]["rows_folded"]) == (0, 1), report
        assert event_store.store_fingerprint() != before, "a fold-only commit left the key frozen"


def test_served_code_fingerprint_follows_the_store_modules(tmp_path, monkeypatch):
    """Fable F4: the daemon has `event_store.py` and `events.py` LOADED (what is ingested, the key
    every memo reads), so a change carried by either alone must read as STALE, never `current`."""
    monkeypatch.setattr(dashboard, "HERE", tmp_path)  # `HERE` is resolved at call time
    for name in ("event_store.py", "events.py"):
        before = dashboard.served_code_fingerprint()
        (tmp_path / name).write_text("# a newer copy\n", encoding="utf-8")
        assert dashboard.served_code_fingerprint() != before, f"{name} is not served code"
