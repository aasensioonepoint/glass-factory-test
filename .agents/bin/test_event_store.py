"""Tests for event_store.py — the SQLite projection of the spool (T-00000049).

Style: explicit-path module load (this repo's test_events.py / test_dashboard.py
convention). Every test redirects AGENTS_EVENTS_DIR / AGENTS_OTEL_DIR, so the
database path — derived from the spool directory on purpose — lands in tmp_path
and never near this developer's real `.agents/state/local/events.db`.

THE FOUR EXIT CRITERIA of docs/tasks/T-00000049.md have a section each, named,
below. They are not incidental coverage: each one is a data-loss or
double-counting path that plan-critic named across seven iterations, and the
test is the only thing that keeps the answer from being re-litigated by the next
edit.

  1. `kill -9` mid-ingestion       -> zero loss, zero duplicate
  2. PermissionError at delete     -> retry-or-skip, never an error
  3. 500-file boot catch-up        -> batched, lag displayed, no timeout
  4. partial line (no `\\n` yet)   -> left for the next tick, never truncated

Plus the two must-fixes the human gate attached to the approved plan:
  C1  a successful delete PURGES the resume entry (+ the recreate-crossing-
      offset case that rule exists for)
  C2  the merge/compact "events.db absent" gate is evaluated UNDER
      `.maintenance.lock`, and the legacy migration takes the SAME lock

WINDOWS-ONLY tests are marked `skipUnless(os.name == "nt")` and never loosened
(L-00000068): an assertion weak enough to pass on ubuntu measures nothing about
the Windows handle semantics it exists to pin.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


event_store = _load("event_store", "event_store.py")
events = event_store._events_mod
# T-00000769: the REAL dashboard-daemon probe, kept before `_redirect` replaces
# it for every test — so the one test that exercises its wiring can reach it,
# and no other test can ever ping this developer's live daemon.
_REAL_DAEMON_STATE = getattr(event_store, "_dashboard_daemon_state", None)


# ---------------------------------------------------------------------------
# THE ONE CLOCK — T-00000063
# ---------------------------------------------------------------------------
# A spool file's NAME carries a day, and `merge_day_files()` folds every PAST
# day into `D.merged.jsonl`, sparing only its own "today". So a day written into
# a filename here is a temporal fact, and the convention that governs it is the
# canonical one (CONVENTIONS_python.md): a test that injects a clock stamps
# EVERY temporal fact it fabricates on that same clock — mtimes, file dates,
# timestamps.
#
# That was violated by omission, not by intent. The clock the retention and
# export cases already inject is 2026-07-29T12:00Z, and this file's spool names
# were written as `2026-07-29.<host>.<pid>.jsonl` — the same day, but sourced
# from the WALL CLOCK of the afternoon they were typed rather than from the
# injected one. `open_store(create=True)` runs the one-time legacy migration,
# which called `merge_day_files()` with no clock at all, i.e. the real one. On
# 2026-07-29 the two agreed by coincidence and every test passed; on 2026-07-30
# the coincidence expired, those files became a PAST day, the migration folded
# all of them into `2026-07-29.merged.jsonl`, and 19 tests went red at once —
# identically on every machine and at every commit in history, including commits
# that predate the code they accuse.
#
# It is the SECOND time bomb of this exact shape in this file: `_touch_old`'s
# docstring below tells the story of the first one (T-00000057) and states the
# lesson — a test whose verdict depends on the wall-clock time of day measures
# the calendar, not the code. It fixed the quiescence window and left the day
# names on the real clock.
#
# So the clock is injected ONCE, here, and `_redirect` hands it to the migration
# too. `_TODAY` is the string those filenames already contain, and `_FROZEN_NOW`
# is DERIVED from it rather than restated, so the two cannot drift apart. Every
# spool file these tests write is dated `_TODAY` — today on the injected clock,
# never folded — except where a test deliberately exercises the fold, which uses
# an explicitly older day (2026-07-20, 2026-01-05).
_TODAY = "2026-07-29"
_FROZEN_NOW = datetime.fromisoformat(f"{_TODAY}T12:00:00+00:00")


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    otel_dir = tmp_path / "otel"
    events_dir.mkdir(parents=True, exist_ok=True)
    otel_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(otel_dir))
    # V1-c: the attribution classifier reads `project.json`, and the one-shot
    # backfill compares a recorded provenance against the project ROOT. Both are
    # redirected, so no test can resolve this developer's real identity — and
    # `project.json` is deliberately ABSENT by default (`resolve_project_id()`
    # returns `PROJECT_UNSET`), the state every pre-V1-c test ran under.
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "own-root"))
    monkeypatch.delenv("AGENTS_EVENTS_DB", raising=False)
    # The legacy fold runs from `open_store(create=True)`, which takes no clock —
    # so the clock is injected HERE, at the one place it is reachable, and the
    # REAL merger still runs behind it (a stub would stop covering the migration
    # this file has four tests for). `now` passed explicitly still wins, so
    # `events.main(["--merge-days"])` and the fold tests keep driving it.
    _real_merge_day_files = events.merge_day_files
    monkeypatch.setattr(
        events, "merge_day_files",
        lambda now=None: _real_merge_day_files(now or _FROZEN_NOW))
    # T-00000769: `main --export-spool` probes the dashboard daemon (pid + a
    # tokenised HTTP ping on the port its lock names). No test may reach this
    # developer's LIVE daemon, so the probe answers "absent" unless a test says
    # otherwise; `_REAL_DAEMON_STATE` is the one door to the real function.
    monkeypatch.setattr(event_store, "_dashboard_daemon_state", lambda: ("absent", None),
                        raising=False)
    event_store.take_dirty_notices()  # module-level doorbell state
    yield {"root": tmp_path, "events": events_dir, "otel": otel_dir,
           "db": tmp_path / "local" / "events.db",
           "own_root": tmp_path / "own-root",
           "project_json": tmp_path / "project.json"}


# --- V1-c attribution helpers ----------------------------------------------

_OWN_ID = "own-project-id-0001"
_OTHER_ID = "neighbour-project-id-0002"


def _init_identity(_redirect, project_id: str = _OWN_ID) -> str:
    """Write the identity `project_init.py` would have written."""
    _redirect["project_json"].write_text(
        json.dumps({"project_id": project_id}), encoding="utf-8", newline="\n")
    return project_id


def _otel_envelope(**fields) -> dict:
    """A canal-B envelope. `project_id` is passed explicitly (or omitted, for
    the pre-V1-c shape) so each test states which of the five buckets it is
    exercising."""
    base = {"ts": "2026-07-29T10:00:00Z", "kind": "metrics", "path": "/v1/metrics"}
    base.update(fields)
    return base


def _legacy_otel_envelope(provenance: str, **fields) -> dict:
    """MUST-FIX M3's fixture, kept as a first-class factory: a pre-V1-c canal-B
    line with NO promoted field and a provenance that may or may not match the
    current root. It is the ONLY shape that exercises the moved-clone / renamed-
    repo case, which is the case the sentinel branch of the backfill exists
    for. If every factory in this file carried a `project_id`, that branch would
    have no test at all (iteration 9, C4)."""
    return _otel_envelope(provenance=provenance, **fields)


def _write_otel_spool(directory: Path, name: str, envelopes: list[dict]) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write("".join(json.dumps(e, ensure_ascii=False) + "\n"
                             for e in envelopes).encode("utf-8"))
    return path


def _project_bodies(db: Path) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return [(str(p), json.loads(b)) for p, b in conn.execute(
            "SELECT project, body FROM events WHERE channel = 'b' ORDER BY id").fetchall()]
    finally:
        conn.close()


def _rec(ts: str = "2026-07-29T10:00:00Z", **fields) -> dict:
    base = {"ts": ts, "kind": "hook.deny", "host": "claude", "sid": None,
            "pid": None, "aid": None, "task": None, "agent": None,
            "effort": None, "user": "Dev", "data": {}}
    base.update(fields)
    return base


def _write_spool(directory: Path, name: str, records, *, partial_tail: str | None = None) -> Path:
    """One spool file, written the way `events._write_line` writes: one JSON
    object per line, "\\n" only, no CRLF (L-003)."""
    path = directory / name
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    if partial_tail is not None:
        payload += partial_tail  # deliberately NO trailing newline
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload.encode("utf-8"))
    return path


def _rows(db: Path) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            "SELECT project, src_file, line_index, line_hash, body FROM events "
            "ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _count(db: Path) -> int:
    # Two states, not one, and treating only the first as legitimate is what made
    # this helper flaky (T-00000206). The daemon creates the FILE and the TABLE in
    # two steps, so a poller that starts between them finds a database that exists
    # and has no `events` table yet. That window is narrow — it opened on a loaded
    # machine, on the frozen checkout of a `verify.sh --at` run, while the same
    # revision passed a bare `python -m pytest` minutes earlier — which is exactly
    # what makes it worth closing in code rather than re-running until it is green.
    # Both readings mean the same thing to the caller: nothing has been ingested
    # YET. The caller is a deadline loop; returning 0 lets it wait, where raising
    # turns a normal startup race into a red suite.
    if not db.exists():
        return 0
    conn = sqlite3.connect(str(db))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    except sqlite3.OperationalError as exc:
        # NARROW on purpose: only the missing table is a state. Any other
        # operational error (corrupt file, locked beyond timeout, disk failure) is
        # a real defect and must still fail the test loudly — swallowing them all
        # would replace a flaky test with a blind one.
        if "no such table" in str(exc):
            return 0
        raise
    finally:
        conn.close()


def test_count_treats_the_half_created_database_as_empty_not_as_an_error():
    """T-00000206: the window between CREATE FILE and CREATE TABLE is a state."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "events.db"
        # absent: already handled before this fix, kept so the arm covers both states
        assert _count(db) == 0
        # present but tableless — this is the shape that reddened verify.sh --at
        sqlite3.connect(str(db)).close()
        assert db.exists()
        assert _count(db) == 0
        # and once the table exists the helper counts for real, so the tolerance
        # above cannot be hiding a helper that always answers 0
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, body TEXT)")
        conn.execute("INSERT INTO events (body) VALUES ('x')")
        conn.commit()
        conn.close()
        assert _count(db) == 1


def test_count_still_raises_on_an_operational_error_that_is_not_a_missing_table():
    """The tolerance is narrow: a corrupt database must still fail loudly."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "events.db"
        db.write_bytes(b"this is not a sqlite database" * 8)
        try:
            _count(db)
        except sqlite3.DatabaseError:
            pass  # expected: the helper did not swallow it
        else:
            raise AssertionError("_count swallowed a non-missing-table error")


def _bodies(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return [str(r[0]) for r in
                conn.execute("SELECT body FROM events ORDER BY id").fetchall()]
    finally:
        conn.close()


def _touch_old(path: Path, seconds: float = 600.0, *,
               now: datetime | None = None) -> None:
    """Push mtime into the past so the quiescence window (2 s) is satisfied —
    tests must never actually sleep for it.

    `now` IS NOT OPTIONAL DECORATION: it must be the SAME clock the test drives
    the store with, and passing it is what keeps this helper from rotting.
    `_delete_consumed` compares `now_epoch - st_mtime` against
    `_QUIESCENCE_SECONDS`, where `now_epoch` comes from the `now=` handed to
    `ingest_once()`. A test that FREEZES that clock in the past while stamping
    mtimes off the real wall clock hands the store a file whose mtime is in its
    FUTURE, so the diff is negative, so "not quiescent yet" is the verdict on
    every tick forever: the file is never deleted, it stays in `live_sources`,
    and `_fold_retention_locked` correctly refuses to fold rows a live source
    could still re-offer (L-00000072). Retention then looks broken while the
    store is behaving exactly as designed.

    That was T-00000057, and it was a TIME BOMB, not a regression: the five
    retention tests froze `now` at 2026-07-29T12:00Z and armed themselves at
    2026-07-29T11:49:58Z real UTC (12:00:00 minus the 600 s default minus the
    2 s window). Before that instant they passed on any machine; after it they
    fail on every machine, identically on Windows and Linux, and at every commit
    in history — which is why replaying an older commit reproduced them and made
    a dormant test defect look like a live data defect. A test whose verdict
    depends on the wall-clock time of day measures the calendar, not the code.

    Leave `now` unset ONLY when the test also lets `ingest_once()` default to
    the real clock; then both sides read `time.time()` and agree."""
    base = time.time() if now is None else now.timestamp()
    stamp = base - seconds
    os.utime(path, (stamp, stamp))


def _drain(store, directory: Path, now: datetime, ticks: int = 4) -> list[dict]:
    """Tick until the spool is drained AND retention has folded.

    Deliberately more than one tick, because the pipeline genuinely has stages: a
    file is ingested on one tick, deleted after that tick's COMMIT, and its old
    rows become foldable only on the FOLLOWING tick — a row is never folded while
    its spool file could still re-offer it (see
    `test_retention_holds_back_rows_whose_spool_file_is_still_on_disk`). mtimes
    are pushed into the past between ticks so the 2 s quiescence window is met
    without the test sleeping — RELATIVE TO `now`, the clock this drain hands the
    store, never the wall clock (see `_touch_old`: mixing the two is what stalled
    every deletion, and therefore every fold, in T-00000057)."""
    reports = []
    for _ in range(ticks):
        for path in list(directory.glob("*.jsonl")):
            _touch_old(path, now=now)
        reports.append(store.ingest_once(now=now))
    return reports


# ---------------------------------------------------------------------------
# Schema, versioning, and the identity that everything else rests on
# ---------------------------------------------------------------------------

def test_schema_is_versioned_from_day_one(_redirect):
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok"
        assert store.user_version == event_store.SCHEMA_VERSION == 1
        version = store.connection.execute("PRAGMA user_version").fetchone()[0]
        assert version == 1, "a store without a version is a store that must be thrown away"
    finally:
        store.close()


def test_identity_is_exactly_the_four_columns(_redirect):
    """Regression guard on the dedup key itself. Dropping any one of these four
    reopens a named defect: `project` (hub copy collides two projects, iteration
    4 C5), `src_file` (a burst of identical hook.deny events collapses to one
    row, iteration 1 C1), `line_index` (multiplicity of legitimate byte-identical
    duplicates, iteration 3 C3), `line_hash` (content is not checked at all)."""
    store = event_store.open_store(create=True)
    try:
        info = store.connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'events_identity'"
        ).fetchone()[0]
        columns = info[info.index("(") + 1: info.rindex(")")]
        assert [c.strip() for c in columns.split(",")] == [
            "project", "src_file", "line_index", "line_hash"]
    finally:
        store.close()


def test_wal_and_busy_timeout_are_configured(_redirect):
    """Spec §A.2 names WAL, `busy_timeout` and `synchronous=NORMAL`. WAL is also
    the reason a hard kill mid-transaction recovers cleanly, so this is not
    cosmetic configuration — criterion 1 rests on it."""
    store = event_store.open_store(create=True)
    try:
        conn = store.connection
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert int(conn.execute("PRAGMA busy_timeout").fetchone()[0]) > 0
        assert int(conn.execute("PRAGMA synchronous").fetchone()[0]) == 1  # NORMAL
    finally:
        store.close()


def test_the_migration_ladder_exists_and_refuses_a_gap(_redirect):
    """Spec §A.2 asks for a migration PATH from v1, not just a version stamp. The
    ladder is empty today (v1 is the floor) — so what is asserted is the
    mechanism: a version below ours with no registered rung is REFUSED, loudly,
    rather than silently opened and written to with the wrong schema."""
    assert event_store._MIGRATIONS == {}, "v1 is the floor; nothing to migrate FROM yet"
    conn = sqlite3.connect(":memory:")
    try:
        reached, error = event_store._apply_migrations(conn, event_store.SCHEMA_VERSION)
        assert (reached, error) == (event_store.SCHEMA_VERSION, None), "already current"
        # A hypothetical older store with no rung registered.
        reached, error = event_store._apply_migrations(conn, -1)
        assert reached == -1
        assert "no migration registered" in error
    finally:
        conn.close()


def test_a_migration_that_forgets_to_bump_the_version_is_refused(_redirect, monkeypatch):
    """The anti-loop clause. A rung that runs but leaves `user_version` alone
    would spin forever; it is reported instead."""
    monkeypatch.setitem(event_store._MIGRATIONS, 0, lambda _conn: None)
    conn = sqlite3.connect(":memory:")
    try:
        reached, error = event_store._apply_migrations(conn, 0)
        assert reached == 0
        assert "did not bump user_version" in error
    finally:
        conn.close()


def test_absent_store_is_a_first_class_state_never_an_error(_redirect):
    store = event_store.open_store(create=False)
    try:
        assert store.status == "absent"
        assert store.connection is None
        assert "spool files are the source of truth" in (store.reason or "")
        # Every method answers in a known shape rather than raising.
        assert store.query_events(0)["records"] == []
        assert store.digest_aggregates()["months"] == []
        assert store.max_rowid() == 0
        assert store.ingest_once()["status"] == "absent"
    finally:
        store.close()


def test_todays_spool_survives_the_migration_and_a_later_clock_folds_it(_redirect):
    """T-00000063's regression pin — the foundation every other case here rests on.

    Almost every test in this file names its spool files `_TODAY.<host>.<pid>`
    and then asserts on that name: `src_file`, the resume key, the file still
    being on disk after a kill. All of it is void if `open_store(create=True)`'s
    one-time legacy migration folds those files into `_TODAY.merged.jsonl`
    first, which is precisely what it did on 2026-07-30 — 19 red tests, no code
    change, a wall clock that had simply moved past the day the names were typed.

    BOTH ARMS, because the positive one alone would stay green for the wrong
    reason (L-00000025: evaluate the guard on data that CAN match):

      POSITIVE — under the injected clock, a file dated `_TODAY` is today's, so
      the migration leaves it alone and it is ingested under its own name.
      NEGATIVE — the SAME file, handed to the SAME real merger one day later, IS
      folded. So what spares it is the injected clock, not some property of the
      file, and removing the injection in `_redirect` turns the positive arm red.

    The later clock is `_FROZEN_NOW + 1 day`, never `datetime.now()`: a test that
    reached for the wall clock to prove a wall-clock bug would be the bug.
    """
    directory = _redirect["events"]
    name = f"{_TODAY}.claude.7.jsonl"
    _write_spool(directory, name, [_rec(task="T-1"), _rec(task="T-2")])

    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 2
    finally:
        store.close()
    assert not (directory / f"{_TODAY}{events._MERGED_SUFFIX}").exists(), (
        "the migration folded today's spool — every name-based assertion in this "
        "file is void")
    assert {r[1] for r in _rows(_redirect["db"])} == {f"a/{name}"}, (
        "rows are attributed to the file the test wrote, not to a merged one")

    # NEGATIVE ARM: same merger, same file shape, a clock one day later.
    later = _write_spool(directory, f"{_TODAY}.claude.8.jsonl", [_rec(task="T-3")])
    report = events.merge_day_files(now=_FROZEN_NOW + timedelta(days=1))
    assert report["days_merged"] == [_TODAY] and report["files_folded"] >= 1
    assert not later.exists(), "a past day IS folded — the injected clock is the guard"
    assert (directory / f"{_TODAY}{events._MERGED_SUFFIX}").exists()


def test_ingest_assigns_rank_and_hash_from_the_file_itself(_redirect):
    _write_spool(_redirect["events"], "2026-07-29.claude.11.jsonl",
                 [_rec(task="T-1"), _rec(task="T-2"), _rec(task="T-3")])
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_inserted"] == 3
    finally:
        store.close()
    rows = _rows(_redirect["db"])
    assert [r[2] for r in rows] == [0, 1, 2], "rank is the line's position in its file"
    assert [r[1] for r in rows] == ["a/2026-07-29.claude.11.jsonl"] * 3
    # The hash recipe is PINNED (iteration 3, C4): sha256 of the raw line bytes,
    # trailing newline excluded. Recomputed here from the record, not read back
    # from the module, so a change of recipe fails this test.
    import hashlib
    expected = hashlib.sha256(
        json.dumps(_rec(task="T-1"), ensure_ascii=False).encode("utf-8")).hexdigest()
    assert rows[0][3] == expected


def test_blank_lines_consume_a_rank_so_ranks_never_shift(_redirect):
    path = _redirect["events"] / "2026-07-29.claude.12.jsonl"
    path.write_bytes(
        json.dumps(_rec(task="T-1")).encode() + b"\n\n"
        + json.dumps(_rec(task="T-2")).encode() + b"\n")
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    ranks = [r[2] for r in _rows(_redirect["db"])]
    assert ranks == [0, 2], "a blank line is consumed, not skipped — rank 1 belongs to it"


# ---------------------------------------------------------------------------
# EXIT CRITERION 1 — kill -9 during ingestion: zero loss, zero duplicate
# ---------------------------------------------------------------------------

class _Boom(Exception):
    """Stands in for the process disappearing, for the two in-process variants."""


def test_criterion1_crash_before_commit_loses_nothing(_redirect):
    """Window #1. Killed before COMMIT: the transaction rolls back and the spool
    file is untouched, so the next tick re-reads it and nothing is lost."""
    _write_spool(_redirect["events"], "2026-07-29.claude.21.jsonl",
                 [_rec(task=f"T-{i}") for i in range(5)])
    store = event_store.open_store(create=True)
    try:
        store.before_commit_hook = lambda: (_ for _ in ()).throw(_Boom())
        with pytest.raises(_Boom):
            store.ingest_once()
        assert _count(_redirect["db"]) == 0, "an uncommitted batch must leave no row"
        assert (_redirect["events"] / "2026-07-29.claude.21.jsonl").exists(), (
            "the spool file is the only remaining source — it must not be deleted")
        # The offset must NOT have advanced: a crash before COMMIT leaves the
        # reader exactly where it was.
        store.before_commit_hook = None
        report = store.ingest_once()
        assert report["rows_inserted"] == 5
    finally:
        store.close()
    assert _count(_redirect["db"]) == 5


def test_criterion1_crash_after_commit_before_delete_duplicates_nothing(_redirect):
    """Window #2. Killed after COMMIT but before the delete: the rows are
    durable AND the files are still there, so the next tick re-reads them —
    which is free, because dedup is per record (L-00000060), not per file."""
    _write_spool(_redirect["events"], "2026-07-29.claude.22.jsonl",
                 [_rec(task=f"T-{i}") for i in range(5)])
    store = event_store.open_store(create=True)
    try:
        store.after_commit_hook = lambda: (_ for _ in ()).throw(_Boom())
        with pytest.raises(_Boom):
            store.ingest_once()
        assert _count(_redirect["db"]) == 5
        assert (_redirect["events"] / "2026-07-29.claude.22.jsonl").exists()
        store.after_commit_hook = None
    finally:
        store.close()
    # A FRESH store: the in-memory offsets are gone too, exactly as after a real
    # kill, so this re-reads the whole file from zero.
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_offered"] == 5
        assert report["rows_inserted"] == 0
        assert report["duplicates_ignored"] == 5
    finally:
        store.close()
    assert _count(_redirect["db"]) == 5, "zero duplicate after a re-read from zero"


_CHILD_SCRIPT = textwrap.dedent(
    """
    import importlib.util, os, sys, time
    from datetime import datetime
    from pathlib import Path

    store_path, marker, window = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    spec = importlib.util.spec_from_file_location("event_store", store_path)
    es = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = es
    spec.loader.exec_module(es)

    # THE SAME INJECTED CLOCK AS THE PARENT (T-00000063), re-applied by hand: a
    # monkeypatch does not cross a process boundary, and this child calls
    # `open_store(create=True)` — so it runs the one-time legacy migration too.
    # Without this it folds, on the real clock, the very spool file the parent
    # then asserts on, and the assertion goes back to measuring the calendar.
    _frozen_now = datetime.fromisoformat(sys.argv[4])
    _real_merge_day_files = es._events_mod.merge_day_files
    es._events_mod.merge_day_files = (
        lambda now=None: _real_merge_day_files(now or _frozen_now))

    def park():
        marker.write_text("at-window", encoding="utf-8")
        time.sleep(120)  # the parent kills us right here

    store = es.open_store(create=True)
    if window == "before_commit":
        store.before_commit_hook = park
    else:
        store.after_commit_hook = park
    store.ingest_once()
    """
)


def _kill_during_ingestion(tmp_path: Path, window: str) -> None:
    """Spawn a real child, let it park inside `window`, then HARD-kill it.

    `Popen.kill()` is SIGKILL on POSIX and TerminateProcess on Windows — in both
    cases no cleanup, no atexit, no chance to commit or roll back in userspace,
    which is what "kill -9 pendant l'ingestion" means. Deterministic rather than
    timing-based: the child announces via a marker file that it has reached the
    exact window before it parks."""
    script = tmp_path / "child_kill.py"
    script.write_text(_CHILD_SCRIPT, encoding="utf-8")
    marker = tmp_path / f"marker-{window}"
    proc = subprocess.Popen(
        [sys.executable, str(script), str(HERE / "event_store.py"), str(marker),
         window, _FROZEN_NOW.isoformat()],
        env=dict(os.environ),
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 60.0
        while not marker.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr = (proc.stderr.read() or b"").decode("utf-8", "replace")
                raise AssertionError(f"child exited before reaching {window}: {stderr}")
            time.sleep(0.02)
        assert marker.exists(), f"child never reached the {window} window"
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_criterion1_real_kill_before_commit_loses_nothing(_redirect):
    _write_spool(_redirect["events"], "2026-07-29.claude.23.jsonl",
                 [_rec(task=f"T-{i}") for i in range(20)])
    _kill_during_ingestion(_redirect["root"], "before_commit")
    # Non-vacuity control: the child really did the work (it created the database
    # and reached the pre-COMMIT window, marker-confirmed above), and WAL
    # recovery really did discard the uncommitted batch.
    assert _redirect["db"].exists(), "the child created the store before being killed"
    assert _count(_redirect["db"]) == 0, "an uncommitted transaction leaves nothing"
    # Reopening must recover to the last committed state, which is "empty".
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok", store.reason
        report = store.ingest_once()
        assert report["rows_inserted"] == 20, "nothing survived the rollback, so all 20 land now"
    finally:
        store.close()
    assert _count(_redirect["db"]) == 20


def test_criterion1_real_kill_after_commit_duplicates_nothing(_redirect):
    _write_spool(_redirect["events"], "2026-07-29.claude.24.jsonl",
                 [_rec(task=f"T-{i}") for i in range(20)])
    _kill_during_ingestion(_redirect["root"], "after_commit")
    assert _count(_redirect["db"]) == 20, "the COMMIT was durable before the kill"
    assert (_redirect["events"] / "2026-07-29.claude.24.jsonl").exists(), (
        "the kill landed before the delete, so the file is still there")
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_offered"] == 20
        assert report["rows_inserted"] == 0
    finally:
        store.close()
    assert _count(_redirect["db"]) == 20, "zero duplicate across a real hard kill"


# ---------------------------------------------------------------------------
# EXIT CRITERION 2 — PermissionError at delete: retry-or-skip, never an error
# ---------------------------------------------------------------------------

def test_criterion2_permission_error_on_delete_is_a_skip_not_an_error(_redirect, monkeypatch):
    path = _write_spool(_redirect["events"], "2026-07-29.claude.31.jsonl",
                        [_rec(task="T-1")])
    _touch_old(path)
    real_unlink = Path.unlink

    def refuse(self, *a, **k):
        if self.name == "2026-07-29.claude.31.jsonl":
            raise PermissionError(13, "handle still open (simulated)")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", refuse)
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()  # must NOT raise
        assert report["rows_inserted"] == 1
        assert report["delete_deferred"] == 1
        assert report["deleted"] == 0
        assert report["error"] is None
        assert path.exists(), "an undeletable file waits for the next tick"
        # And the next tick, still unable to delete, still does not raise and
        # still does not duplicate: the file's bytes have not grown, so there is
        # nothing new to read.
        again = store.ingest_once()
        assert again["error"] is None
        assert again["rows_inserted"] == 0
    finally:
        store.close()
    assert _count(_redirect["db"]) == 1


def test_criterion2_unlink_helper_returns_false_and_never_raises(_redirect, monkeypatch):
    """The primitive itself, isolated: `_unlink_with_retry` is the single place
    the retry-or-skip contract lives, so it is asserted directly rather than
    only through a tick."""
    path = _write_spool(_redirect["events"], "2026-07-29.claude.32.jsonl", [_rec()])
    calls = {"n": 0}

    def refuse(self, *a, **k):
        calls["n"] += 1
        raise PermissionError(13, "nope")

    monkeypatch.setattr(Path, "unlink", refuse)
    assert event_store._unlink_with_retry(path) is False
    assert calls["n"] == event_store._DELETE_ATTEMPTS, "it retries, bounded, then skips"


@pytest.mark.skipif(os.name != "nt", reason=(
    "measures a Windows fact (L-00000068): an open handle makes unlink fail with "
    "PermissionError there, while POSIX unlinks a file that is still open. An "
    "assertion weakened to pass on both platforms would measure nothing."))
def test_criterion2_real_open_windows_handle_defers_the_delete(_redirect):
    """L-00000035 / L-00000054, unsimulated: hold a real handle on the spool file
    and prove the tick reports a deferral instead of raising."""
    path = _write_spool(_redirect["events"], "2026-07-29.claude.33.jsonl",
                        [_rec(task="T-1")])
    _touch_old(path)
    store = event_store.open_store(create=True)
    handle = open(path, "rb")
    try:
        report = store.ingest_once()
        assert report["error"] is None
        assert report["rows_inserted"] == 1
        assert report["delete_deferred"] == 1, (
            "on Windows an open handle must block the unlink — if this reports a "
            "successful delete, the platform semantics this guard exists for have "
            "changed and the guard needs re-measuring, not relaxing")
        assert path.exists()
    finally:
        handle.close()
        store.close()


@pytest.mark.skipif(os.name != "nt", reason=(
    "the closing half of the Windows-handle fact above; POSIX never defers, so "
    "there is nothing to observe recovering (L-00000068)."))
def test_criterion2_deferred_delete_succeeds_once_the_handle_closes(_redirect):
    path = _write_spool(_redirect["events"], "2026-07-29.claude.34.jsonl",
                        [_rec(task="T-1")])
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        handle = open(path, "rb")
        assert store.ingest_once()["delete_deferred"] == 1
        handle.close()
        _touch_old(path)
        report = store.ingest_once()
        assert report["deleted"] == 1
        assert not path.exists()
        assert report["rows_inserted"] == 0, "the retry deleted, it did not re-ingest"
    finally:
        store.close()
    assert _count(_redirect["db"]) == 1


# ---------------------------------------------------------------------------
# EXIT CRITERION 3 — 500-file boot catch-up: batched, lag displayed, no timeout
# ---------------------------------------------------------------------------

def test_criterion3_boot_catch_up_of_500_files_is_one_batch(_redirect):
    """The dimensioning case named in spec §A.2: the daemon was dead for a day,
    so a day's worth of per-invocation hook processes (one file each,
    L-00000041) is waiting. It must drain as ONE batched transaction, not 500,
    and it must not blow a timeout."""
    directory = _redirect["events"]
    # TODAY's date on purpose: `merge_day_files` never touches today, so these
    # 500 files reach the ingestion as 500 files. Dating them in the past would
    # have the one-time legacy migration fold them first and this test would
    # measure that instead (which is what it did on the first run). TODAY is the
    # INJECTED clock's day (`_TODAY`), not the wall clock's: reading the wall
    # clock here was half of the T-00000063 bomb, and it is also what made this
    # one test survive it while its 19 neighbours did not.
    for i in range(500):
        _write_spool(directory, f"{_TODAY}.claude.{1000 + i}.jsonl",
                     [_rec(ts=f"{_TODAY}T10:00:00Z", task=f"T-{i}"),
                      _rec(ts=f"{_TODAY}T10:00:01Z", task=f"T-{i}")])
    store = event_store.open_store(create=True)
    try:
        started = time.monotonic()
        report = store.ingest_once()
        elapsed = time.monotonic() - started
    finally:
        store.close()
    assert report["files_scanned"] == 500
    assert report["files_read"] == 500
    assert report["rows_inserted"] == 1000
    assert report["batch_truncated"] is False, "1000 rows is well under the batch cap"
    assert report["boot_backlog_files"] == 500, "the size of the backlog is remembered"
    assert report["error"] is None
    assert _count(_redirect["db"]) == 1000
    # Generous by design — this asserts "one batch, not 500 round trips", not a
    # performance number that would flake on a loaded CI runner.
    assert elapsed < 60.0, f"boot catch-up took {elapsed:.1f}s"


def test_criterion3_lag_is_displayed_never_silent(_redirect):
    directory = _redirect["events"]
    for i in range(3):
        path = _write_spool(directory, f"2026-07-29.claude.{40 + i}.jsonl", [_rec()])
        _touch_old(path, seconds=3600.0)
    event_store.open_store(create=True).close()  # a store exists, nothing ingested
    status = event_store.ingestion_status()
    assert status["source"] == "sqlite"
    assert status["spool_files_pending"] == 3
    assert status["late"] is True
    assert status["behind_since"] is not None
    assert "en retard depuis" in status["message"]
    assert status["oldest_pending_age_seconds"] >= event_store._LATE_SECONDS


def test_criterion3_one_tick_in_flight_is_not_reported_as_a_lag(_redirect):
    """The control that keeps the assertion above from being vacuous: a spool
    file that has just been written is NORMAL for up to a tick, and crying lag on
    every poll would make the signal worthless."""
    _write_spool(_redirect["events"], "2026-07-29.claude.45.jsonl", [_rec()])
    event_store.open_store(create=True).close()
    status = event_store.ingestion_status()
    assert status["spool_files_pending"] == 1
    assert status["late"] is False
    assert status["message"] is None


def test_criterion3_batch_cap_truncates_and_says_so(_redirect, monkeypatch):
    """The bound that makes "batch" a bound rather than a hope. A truncated batch
    is reported, and `IngestLoop` re-ticks immediately on it instead of sleeping."""
    monkeypatch.setattr(event_store, "_BATCH_ROW_CAP", 4)
    for i in range(6):
        _write_spool(_redirect["events"], f"2026-07-29.claude.{50 + i}.jsonl",
                     [_rec(task=f"T-{i}"), _rec(task=f"T-{i}-b")])
    store = event_store.open_store(create=True)
    try:
        first = store.ingest_once()
        assert first["batch_truncated"] is True
        assert first["rows_inserted"] == 4
        drained = first["rows_inserted"]
        for _ in range(10):
            report = store.ingest_once()
            drained += report["rows_inserted"]
            if not report["batch_truncated"]:
                break
        assert drained == 12, "every row is eventually ingested, in bounded slices"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# EXIT CRITERION 4 — a partial line is never ingested truncated
# ---------------------------------------------------------------------------

def test_criterion4_partial_line_is_left_for_the_next_tick(_redirect):
    directory = _redirect["events"]
    complete = [_rec(task="T-1"), _rec(task="T-2")]
    tail = json.dumps(_rec(task="T-3"), ensure_ascii=False)
    path = _write_spool(directory, "2026-07-29.claude.61.jsonl", complete,
                        partial_tail=tail[:-5])  # cut before the closing brace
    store = event_store.open_store(create=True)
    try:
        first = store.ingest_once()
        assert first["rows_inserted"] == 2, "only the two COMPLETE lines"
        bodies = _bodies(_redirect["db"])
        assert all(body.endswith("}") for body in bodies), "no truncated JSON was stored"
        assert not any('"T-3"' in body for body in bodies)
        # Finish the line the way a live writer would, then tick again.
        with open(path, "ab") as handle:
            handle.write((tail[-5:] + "\n").encode("utf-8"))
        second = store.ingest_once()
        assert second["rows_inserted"] == 1
    finally:
        store.close()
    bodies = _bodies(_redirect["db"])
    assert len(bodies) == 3
    assert json.loads(bodies[2])["task"] == "T-3", (
        "the third event arrives WHOLE on the following tick — never half-written, "
        "never dropped")


def test_criterion4_incomplete_file_is_never_deleted(_redirect):
    """The other half of the rule, and the one that turns "we did not parse it"
    into "we did not lose it": a file whose size exceeds what we consumed is by
    definition not fully consumed, so it must survive the delete pass (iteration
    1, C2 — re-stat before every unlink)."""
    path = _write_spool(_redirect["events"], "2026-07-29.claude.62.jsonl",
                        [_rec(task="T-1")], partial_tail='{"ts":"2026-07-29')
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_inserted"] == 1
        assert report["delete_skipped_appended"] == 1
        assert report["deleted"] == 0
        assert path.exists(), "deleting here would destroy unread bytes"
    finally:
        store.close()


def test_criterion4_bytes_appended_between_read_and_delete_are_not_lost(_redirect):
    """The race the re-stat exists for, forced open with the post-commit seam: a
    writer appends AFTER the read and BEFORE the unlink. Without the re-stat
    those bytes would be deleted having never been read."""
    path = _write_spool(_redirect["events"], "2026-07-29.claude.63.jsonl",
                        [_rec(task="T-1")])
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        def append_late():
            with open(path, "ab") as handle:
                handle.write((json.dumps(_rec(task="T-late")) + "\n").encode("utf-8"))
            _touch_old(path)

        store.after_commit_hook = append_late
        report = store.ingest_once()
        assert report["delete_skipped_appended"] == 1
        assert path.exists()
        store.after_commit_hook = None
        second = store.ingest_once()
        assert second["rows_inserted"] == 1
        assert second["deleted"] == 1
    finally:
        store.close()
    assert any('"T-late"' in body for body in _bodies(_redirect["db"]))


# ---------------------------------------------------------------------------
# MUST-FIX C1 — a successful delete purges the resume entry
# ---------------------------------------------------------------------------

def test_c1_successful_delete_purges_the_resume_entry(_redirect):
    path = _write_spool(_redirect["events"], "2026-07-29.claude.71.jsonl",
                        [_rec(task="T-1")])
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["deleted"] == 1
        assert "a/2026-07-29.claude.71.jsonl" not in store._offsets, (
            "a deleted file must leave NO residual offset behind")
    finally:
        store.close()


def test_c1_recreate_crossing_offset_neither_loses_nor_duplicates(_redirect):
    """THE named must-fix test. A spool file is ingested and deleted; the same
    NAME is then recreated (a reused pid on the same day is entirely possible)
    with different content whose size REACHES OR EXCEEDS the old consumed
    offset. Without the purge rule, the resume entry would say "already read
    N bytes", the new file's first N bytes would be skipped, and those events
    would be lost silently — the shrink guard cannot see it, because the file did
    not shrink."""
    directory = _redirect["events"]
    name = "2026-07-29.claude.72.jsonl"
    first_batch = [_rec(task=f"OLD-{i}") for i in range(4)]
    path = _write_spool(directory, name, first_batch)
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        first = store.ingest_once()
        assert first["rows_inserted"] == 4
        assert first["deleted"] == 1
        assert not path.exists()
        consumed = 4  # rows; the byte offset is what matters below

        # Recreate the SAME name, deliberately at a size >= the old one, with
        # entirely new content.
        second_batch = [_rec(task=f"NEW-{i}") for i in range(6)]
        recreated = _write_spool(directory, name, second_batch)
        assert recreated.stat().st_size >= sum(
            len(json.dumps(r, ensure_ascii=False)) + 1 for r in first_batch), (
            "the point of this test is a recreation that CROSSES the old offset")
        _touch_old(recreated)
        second = store.ingest_once()
        assert second["reread_from_zero"] == 0, (
            "there is no residual entry to detect a shrink against — the purge "
            "already made this a brand-new incarnation read from zero")
        assert second["rows_inserted"] == 6, (
            f"all 6 new events must land; got {second['rows_inserted']} — a "
            f"residual offset would have skipped the first {consumed}")
    finally:
        store.close()
    bodies = _bodies(_redirect["db"])
    assert len(bodies) == 10, "4 old + 6 new, no loss and no duplicate"
    assert sum(1 for b in bodies if "OLD-" in b) == 4
    assert sum(1 for b in bodies if "NEW-" in b) == 6


def test_c1_shrink_after_a_failed_delete_forces_a_full_reread(_redirect, monkeypatch):
    """The path the purge rule does NOT cover, and its own guard: the delete
    failed, so the entry survives; the name is then reused by a SMALLER file.
    An append-only file cannot shrink, so a shrink means a new incarnation."""
    directory = _redirect["events"]
    name = "2026-07-29.claude.73.jsonl"
    path = _write_spool(directory, name, [_rec(task=f"OLD-{i}") for i in range(5)])
    _touch_old(path)
    real_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (
        (_ for _ in ()).throw(PermissionError(13, "held")) if self.name == name
        else real_unlink(self, *a, **k)))
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["delete_deferred"] == 1
        assert store._offsets["a/" + name].offset > 0, "the entry survives a failed delete"
        monkeypatch.setattr(Path, "unlink", real_unlink)
        real_unlink(path)
        smaller = _write_spool(directory, name, [_rec(task="NEW-0")])
        _touch_old(smaller)
        report = store.ingest_once()
        assert report["reread_from_zero"] == 1
        assert report["rows_inserted"] == 1
    finally:
        store.close()
    assert sum(1 for b in _bodies(_redirect["db"]) if "NEW-0" in b) == 1


def test_c1_reused_name_at_equal_size_is_caught_by_file_identity(_redirect, monkeypatch):
    """Belt to the purge rule's braces, and ONLY a belt.

    A failed delete followed by a recreation at the SAME size is invisible to
    shrink detection, so `st_ino` is what notices it. That guard is real but not
    universal, and this test refuses to pretend otherwise (L-00000068): a
    filesystem that reports no inode, or one that hands the freed inode straight
    back (ext4 routinely does, for an immediate recreate in the same directory),
    leaves shrink detection and the purge-on-successful-delete rule as the only
    guards. Where the platform actually reuses the number there is nothing to
    assert, so this SKIPS with the fact named rather than asserting something
    weaker that would pass everywhere and measure nothing."""
    directory = _redirect["events"]
    name = "2026-07-29.claude.74.jsonl"
    path = _write_spool(directory, name, [_rec(task="OLD-0")])
    old_identity = event_store._file_identity(path.stat())
    if old_identity is None:
        pytest.skip("this filesystem does not report st_ino — shrink detection alone applies")
    _touch_old(path)
    real_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (
        (_ for _ in ()).throw(PermissionError(13, "held")) if self.name == name
        else real_unlink(self, *a, **k)))
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["delete_deferred"] == 1
        monkeypatch.setattr(Path, "unlink", real_unlink)
        real_unlink(path)
        # Same byte length, different content: shrink cannot see this.
        recreated = _write_spool(directory, name, [_rec(task="NEW-0")])
        assert recreated.stat().st_size == store._offsets["a/" + name].offset
        if event_store._file_identity(recreated.stat()) == old_identity:
            pytest.skip(
                "this filesystem reused the freed inode, so st_ino cannot "
                "distinguish the incarnations here — the purge-on-delete rule and "
                "shrink detection are the guards that apply")
        _touch_old(recreated)
        report = store.ingest_once()
        assert report["reread_from_zero"] == 1, (
            "st_ino changed, so the name points at a different file")
        assert report["rows_inserted"] == 1
    finally:
        store.close()


def test_c1_byte_identical_rebirth_at_the_same_rank_is_the_accepted_residual(_redirect):
    """ACCEPTED COST, asserted so it is documented rather than discovered.

    A file deleted and reborn under the same name whose line at rank R is
    BYTE-IDENTICAL to the dead file's line at rank R is absorbed by INSERT OR
    IGNORE. That is not a bug to fix here: it is the same mechanism that makes
    crash recovery free (a re-read must be idempotent), and it cannot both
    absorb a re-read and distinguish a coincidence. The coincidence requires the
    same day, host, pid, second and full payload. Recorded as the residual the
    gate accepted, with the shape it actually has."""
    directory = _redirect["events"]
    name = "2026-07-29.claude.75.jsonl"
    identical = _rec(ts="2026-07-29T10:00:00Z", task="SAME")
    path = _write_spool(directory, name, [identical])
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["deleted"] == 1
        reborn = _write_spool(directory, name, [identical])
        _touch_old(reborn)
        report = store.ingest_once()
        assert report["rows_offered"] == 1
        assert report["rows_inserted"] == 0
        assert report["duplicates_ignored"] == 1
    finally:
        store.close()
    assert _count(_redirect["db"]) == 1


# ---------------------------------------------------------------------------
# MUST-FIX C2 — the DB-absent gate is evaluated UNDER `.maintenance.lock`
# ---------------------------------------------------------------------------

def test_c2_merge_days_is_a_noop_once_the_store_exists(_redirect, capsys):
    """Re-homing is retired as an operator action (iteration 6, C1): a spool file
    already ingested but not yet deleted would come back under a NEW
    (src_file, line_index) and INSERT OR IGNORE could not match it."""
    directory = _redirect["events"]
    # Files dated TODAY — on the INJECTED clock (`_TODAY`), the same day the rest
    # of this file dates its spools: the one-time legacy migration deliberately
    # leaves today's files alone, so what happens to them afterwards is
    # attributable to the CLI and to nothing else.
    _write_spool(directory, f"{_TODAY}.claude.81.jsonl", [_rec(ts=f"{_TODAY}T10:00:00Z")])
    _write_spool(directory, "2026-01-05.claude.82.jsonl", [_rec(ts="2026-01-05T11:00:00Z")])
    event_store.open_store(create=True).close()
    assert _redirect["db"].exists()
    before = sorted(p.name for p in directory.iterdir())

    assert events.main(["--merge-days"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == "events.db present — the daemon owns retention"
    assert "merge" not in out

    assert events.main(["--compact"]) == 0
    assert "skipped" in json.loads(capsys.readouterr().out)
    assert sorted(p.name for p in directory.iterdir()) == before, (
        "a no-op must not re-home, fold or delete ANYTHING — an ingested-but-not-"
        "yet-deleted file coming back under a new (src_file, line_index) is the "
        "double-count this gate exists to prevent")


def test_c2_the_gate_is_evaluated_under_the_lock_not_before_it(_redirect, capsys):
    """MUST-FIX C2, first half. With `.maintenance.lock` held by a live rival,
    the CLI must report the LOCK, never the gate — which is only possible if the
    lock is acquired before the `events.db` check is even evaluated. If the gate
    were check-then-act ahead of the lock, an operator run could interleave with
    the migration that creates the file."""
    lock = _redirect["events"] / ".maintenance.lock"
    lock.write_text("", encoding="utf-8")  # fresh => a LIVE holder
    event_store.open_store(create=True).close()  # the DB exists too
    assert events.main(["--merge-days"]) == 0
    assert json.loads(capsys.readouterr().out) == {"skipped": "maintenance already running"}


def test_c2_legacy_migration_takes_the_same_lock(_redirect):
    """MUST-FIX C2, second half. The migration that CREATES `events.db` must
    hold the very lock the gate is evaluated under, so the two cannot interleave.
    Proven by holding the lock and observing that the store is NOT created and
    the legacy fold did NOT run."""
    directory = _redirect["events"]
    _write_spool(directory, "2026-07-20.claude.83.jsonl", [_rec(ts="2026-07-20T10:00:00Z")])
    lock = directory / ".maintenance.lock"
    lock.write_text("", encoding="utf-8")
    store = event_store.open_store(create=True)
    try:
        assert store.status == "absent"
        assert ".maintenance.lock" in (store.reason or "")
        assert not (directory / "2026-07-20.merged.jsonl").exists(), (
            "the migration must not fold anything while a rival holds the lock")
    finally:
        store.close()
    # Release it: the next attempt migrates and creates the store.
    lock.unlink()
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok"
    finally:
        store.close()


def test_c2_a_busy_lock_only_delays_the_store_it_never_disables_it(_redirect):
    """The recovery half: `IngestLoop.tick` retries `open_store(create=True)`
    while the store is still `absent`, so an operator run holding the lock at
    boot costs a tick, not the daemon's lifetime."""
    _write_spool(_redirect["events"], "2026-07-29.claude.84.jsonl", [_rec()])
    lock = _redirect["events"] / ".maintenance.lock"
    lock.write_text("", encoding="utf-8")
    loop = event_store.IngestLoop(interval=0.01)
    loop.store = event_store.open_store(create=True)
    try:
        assert loop.store.status == "absent"
        assert loop.tick() is not None
        assert loop.store.status == "absent", "still blocked, still not giving up"
        lock.unlink()
        report = loop.tick()
        assert loop.store.status == "ok"
        assert report["rows_inserted"] == 1
    finally:
        if loop.store is not None:
            loop.store.close()


def test_c2_legacy_migration_folds_past_days_exactly_once(_redirect):
    """The one surviving caller of `merge_day_files`, doing its one job: folding
    a crashed merger's residue BEFORE anything is ingested, so a stale
    `D.merged.jsonl` and its surviving originals cannot double-home (iteration
    5, C2)."""
    directory = _redirect["events"]
    record = _rec(ts="2026-07-20T10:00:00Z", task="T-LEGACY")
    # Crash residue: the merged file exists AND its source survived.
    _write_spool(directory, "2026-07-20.merged.jsonl", [record])
    _write_spool(directory, "2026-07-20.claude.85.jsonl", [record])
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok"
        assert not (directory / "2026-07-20.claude.85.jsonl").exists(), (
            "the residue source was folded away by the migration")
        store.ingest_once()
    finally:
        store.close()
    bodies = [b for b in _bodies(_redirect["db"]) if "T-LEGACY" in b]
    assert len(bodies) == 1, "one legacy event, one row — not one per surviving name"


def test_c2_a_stuck_original_is_residue_and_never_a_second_source(_redirect):
    """FOUND BY THIS SUITE, third defect. The legacy fold publishes
    `D.merged.jsonl` and then unlinks its sources; if one unlink FAILS
    (L-00000035 — the whole reason deletion is retry-or-skip), the day is
    represented twice on disk. Ingesting both gives every event of that day two
    rows under two `src_file`s, which no `INSERT OR IGNORE` can catch.

    Two rules close it, and both are asserted here: the surviving original is
    RESIDUE (skipped as a source, since the merged file provably contains it),
    and the merged file is NOT deleted while that residue remains — because the
    merged file's existence is the only thing that makes the original
    recognisable as residue rather than as a fresh source."""
    directory = _redirect["events"]
    # YESTERDAY: a past day (so the legacy fold applies to it) that is still
    # inside the 30-day retention window, so this test measures the residue rule
    # and not the retention fold.
    day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    stuck_name = f"{day}.claude.104.jsonl"
    record = _rec(ts=f"{day}T09:00:00Z", task="T-STUCK")
    _write_spool(directory, f"{day}{events._MERGED_SUFFIX}", [record])
    stuck = _write_spool(directory, stuck_name, [record])
    real_unlink = Path.unlink

    def refuse_stuck(self, *a, **k):
        if self.name == stuck_name:
            raise PermissionError(13, "handle held")
        return real_unlink(self, *a, **k)

    Path.unlink = refuse_stuck  # type: ignore[method-assign]
    try:
        store = event_store.open_store(create=True)
        try:
            for _ in range(3):
                for path in directory.glob("*.jsonl"):
                    _touch_old(path)
                report = store.ingest_once()
                assert report["residue_skipped"] == 1
                assert report["delete_skipped_residue_pending"] == 1
            assert stuck.exists()
            assert (directory / f"{day}{events._MERGED_SUFFIX}").exists(), (
                "the merged file must survive while its residue does")
        finally:
            store.close()
    finally:
        Path.unlink = real_unlink  # type: ignore[method-assign]
    bodies = [b for b in _bodies(_redirect["db"]) if "T-STUCK" in b]
    assert len(bodies) == 1, (
        "one legacy event, one row — never one per surviving filename, however "
        "many ticks a stuck handle survives")

    # The handle is released: residue goes, then the merged file, and still one row.
    for path in directory.glob("*.jsonl"):
        _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        for path in directory.glob("*.jsonl"):
            _touch_old(path)
        store.ingest_once()
    finally:
        store.close()
    assert sorted(directory.glob("*.jsonl")) == []
    assert len([b for b in _bodies(_redirect["db"]) if "T-STUCK" in b]) == 1


# ---------------------------------------------------------------------------
# Dedup identity — the four regression guards behind the four columns
# ---------------------------------------------------------------------------

def test_identical_events_from_two_writers_in_the_same_second_are_two_rows(_redirect):
    """Iteration 1's first blocker, kept closed. A burst of `hook.deny` from the
    same guard and rule in the same second is NORMAL operation (N hook
    processes, N files, L-00000041), not a rare coincidence — collapsing it
    would silently under-count the audit trail."""
    directory = _redirect["events"]
    same = _rec(ts="2026-07-29T10:00:00Z", data={"guard": "protect-paths", "rule": "deny"})
    for pid in (901, 902, 903):
        _write_spool(directory, f"2026-07-29.claude.{pid}.jsonl", [same])
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 3
    finally:
        store.close()
    assert _count(_redirect["db"]) == 3


def test_byte_identical_lines_in_one_file_are_two_rows(_redirect):
    """Multiplicity, not set semantics (iteration 3, C3): two legitimate
    identical events in one file are two events. `line_index` is what carries
    that, which is why a set-shaped key was rejected."""
    same = _rec(ts="2026-07-29T10:00:00Z")
    _write_spool(_redirect["events"], "2026-07-29.claude.91.jsonl", [same, same, same])
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 3
    finally:
        store.close()
    assert [r[2] for r in _rows(_redirect["db"])] == [0, 1, 2]


def test_reingesting_an_untouched_file_is_free(_redirect, monkeypatch):
    """Why the delete can be a mere retry-or-skip: re-reading an already-ingested
    file costs nothing but I/O."""
    path = _write_spool(_redirect["events"], "2026-07-29.claude.92.jsonl",
                        [_rec(task=f"T-{i}") for i in range(3)])
    _touch_old(path)
    real_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (
        (_ for _ in ()).throw(PermissionError(13, "held")) if self.name == path.name
        else real_unlink(self, *a, **k)))
    for _ in range(3):
        store = event_store.open_store(create=True)  # fresh offsets each time
        try:
            store.ingest_once()
        finally:
            store.close()
    assert _count(_redirect["db"]) == 3


def test_project_column_is_populated_and_frozen_for_the_session(_redirect):
    """Spec §A.2: `project` exists from day one even in mono-project. Iteration
    5, C1: it is resolved ONCE and frozen, and the `unset -> id` catch-up runs at
    open BEFORE the first tick — a value that could move mid-session would count
    one physical line under two projects."""
    _write_spool(_redirect["events"], "2026-07-29.claude.93.jsonl", [_rec(task="T-1")])
    store = event_store.open_store(create=True)
    try:
        assert store.project == event_store.PROJECT_UNSET, "no project.json yet"
        store.ingest_once()
        # project.json appears mid-session: the FROZEN value must not move.
        _write_project_json(_redirect["root"], "proj-abc")
        assert store.project == event_store.PROJECT_UNSET
        store.ingest_once()
    finally:
        store.close()
    assert {r[0] for r in _rows(_redirect["db"])} == {event_store.PROJECT_UNSET}

    # A REOPEN resolves it, and the catch-up relabels the existing rows without
    # duplicating them.
    store = event_store.open_store(create=True)
    try:
        assert store.project == "proj-abc"
        store.ingest_once()
    finally:
        store.close()
    rows = _rows(_redirect["db"])
    assert {r[0] for r in rows} == {"proj-abc"}
    assert len(rows) == 1, "relabelled, not re-ingested"


def _write_project_json(root: Path, project_id: str) -> None:
    target = root / "project.json"  # sibling of local/, per project_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "project_id": project_id, "name": "T", "slug": "t",
        "created": "2026-07-29T00:00:00Z",
    }), encoding="utf-8")


# ---------------------------------------------------------------------------
# Degraded mode — a database from the future is never touched
# ---------------------------------------------------------------------------

def test_schema_ahead_database_is_never_read_with_v1_sql(_redirect):
    """Iteration 1, C4 + iteration 2, C1. A `user_version` above ours means a
    NEWER kit wrote this file and was rolled back — it is the only local copy of
    that data. No rename, no repair, and above all no v1 statement (every one of
    them would raise against a changed schema, so "the API still serves" would be
    unfalsifiable)."""
    store = event_store.open_store(create=True)
    store.connection.execute("PRAGMA user_version = 2")
    store.close()
    before = _redirect["db"].stat()

    store = event_store.open_store(create=False)
    try:
        assert store.status == "schema_ahead"
        assert store.user_version == 2
        assert store.connection is None, "no connection means no v1 SQL is possible"
        assert "rolled back" in (store.reason or "")
        assert store.query_events(0)["records"] == []
        assert store.ingest_once()["status"] == "schema_ahead"
        assert store.digest_aggregates()["months"] == []
        assert store.export_spool()["status"] == "schema_ahead"
    finally:
        store.close()
    after = _redirect["db"].stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns), (
        "the file must be byte-identical: never renamed, never .discarded")
    status = event_store.ingestion_status()
    assert status["source"] == "schema_ahead"
    assert "version plus récente" in status["message"]


def test_version_zero_non_empty_is_refused_rather_than_interpreted(_redirect):
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE mystery (x INTEGER)")
    conn.commit()
    conn.close()
    store = event_store.open_store(create=True)
    try:
        assert store.status == "unavailable"
        assert "user_version=0 but is not empty" in (store.reason or "")
        assert store.connection is None
    finally:
        store.close()
    assert db.exists(), "refusing is not deleting"


def test_a_corrupt_file_degrades_and_is_left_alone(_redirect):
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"this is not a SQLite database at all" * 10)
    store = event_store.open_store(create=True)
    try:
        assert store.status == "unavailable"
        assert store.connection is None
    finally:
        store.close()
    assert db.exists()


# ---------------------------------------------------------------------------
# Retention + digests
# ---------------------------------------------------------------------------

def test_retention_folds_old_rows_into_the_digests_table(_redirect):
    directory = _redirect["events"]
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    _write_spool(directory, f"{old_day}.claude.101.jsonl", [
        _rec(ts=f"{old_day}T09:00:00Z", kind="hook.deny", agent="dev-multi", task="T-9"),
        _rec(ts=f"{old_day}T09:00:01Z", kind="hook.warn", agent="dev-multi", task="T-9"),
    ])
    _write_spool(directory, "2026-07-29.claude.102.jsonl", [_rec(task="T-fresh")])
    store = event_store.open_store(create=True)
    try:
        reports = _drain(store, directory, now)
        folded = [r["retention"] for r in reports if r["retention"]["rows_folded"]]
        assert len(folded) == 1, "folded on exactly one tick, never re-folded"
        assert folded[0]["rows_folded"] == 2
        assert folded[0]["days_folded"] == [old_day]
        aggregates = store.digest_aggregates()
    finally:
        store.close()
    month = old_day[:7]
    assert aggregates["source"] == "sqlite"
    entry = next(m for m in aggregates["months"] if m["month"] == month)
    assert entry["total_events"] == 2
    assert entry["by_kind"] == {"hook.deny": 1, "hook.warn": 1}
    assert entry["by_agent"] == {"dev-multi": 2}
    assert entry["by_task"] == {"T-9": 2}
    remaining = _bodies(_redirect["db"])
    assert len(remaining) == 1 and "T-fresh" in remaining[0], (
        "the folded rows are gone; the fresh one stays")


def test_retention_holds_back_rows_whose_spool_file_is_still_on_disk(_redirect, monkeypatch):
    """FOUND BY THIS TEST, fixed in the source. A fold deletes rows, so their
    identity leaves the UNIQUE index; if the spool file that produced them is
    STILL THERE (a delete that keeps failing, L-00000035) a later restart
    re-reads it, `INSERT OR IGNORE` has nothing to match, the rows come back and
    the next fold counts them AGAIN — unbounded over-counting from one stuck
    file. Three restarts used to give a digest total of 4 for a single event.

    The invariant now: a row is foldable only once its source can no longer
    re-offer it, i.e. once the file is gone. Rows held back are counted out loud
    rather than silently retained."""
    directory = _redirect["events"]
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    path = _write_spool(directory, f"{old_day}.claude.103.jsonl",
                        [_rec(ts=f"{old_day}T09:00:00Z", kind="hook.deny")])
    _touch_old(path, now=now)  # quiescent on the clock the ticks below use
    real_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (
        (_ for _ in ()).throw(PermissionError(13, "held")) if self.name == path.name
        else real_unlink(self, *a, **k)))
    for _ in range(3):
        store = event_store.open_store(create=True)  # fresh offsets: a restart
        try:
            report = store.ingest_once(now=now)
            assert report["retention"]["rows_folded"] == 0
            assert report["retention"]["rows_retained_pending_spool"] == 1
        finally:
            store.close()
    assert _count(_redirect["db"]) == 1, "three restarts, one row, never folded away"

    # The stuck original also HELD BACK its day's merged file from deletion — on
    # purpose: a merged file is what makes a surviving original recognisable as
    # residue rather than ingestable as a fresh source.
    assert (directory / f"{old_day}{events._MERGED_SUFFIX}").exists()

    # Once the original finally goes, the merged file may go too, and the fold
    # happens on the tick after that — exactly once, ever.
    monkeypatch.setattr(Path, "unlink", real_unlink)
    real_unlink(path)
    store = event_store.open_store(create=True)
    try:
        reports = _drain(store, directory, now)
        folded = [r["retention"]["rows_folded"] for r in reports]
        assert sum(folded) == 1, f"one event, one fold, ever — got {folded}"
        entry = next(m for m in store.digest_aggregates()["months"]
                     if m["month"] == old_day[:7])
        assert entry["total_events"] == 1
    finally:
        store.close()
    assert _count(_redirect["db"]) == 0


def test_a_restart_across_the_fold_boundary_neither_loses_nor_duplicates(_redirect):
    """THE INVARIANT L-00000072 EXISTS FOR, pinned end to end so that a future
    "fix" to the fold cannot trade it away silently (T-00000057, requirement 2).

    The defect it guards is a conservation failure, not a crash: fold a row and
    its identity leaves the UNIQUE dedup index, so if the spool file that
    produced it is STILL on disk, the next process re-reads it, `INSERT OR
    IGNORE` has nothing left to match, the row comes back, and the following fold
    counts the SAME audit event a second time. Seven review iterations closed
    that hole; this test measures that it is still closed.

    Stated as the conservation law it is: one event on the spool must produce
    EXACTLY ONE unit of durable history — never zero (lost), never two
    (duplicated) — no matter how many times the daemon restarts on either side
    of the 30-day boundary.

    Deliberately NOT a copy of the held-back test above: that one forces an
    unlink to FAIL (a stuck file, L-00000035). Here the file is simply NOT
    QUIESCENT YET, the ordinary case that occurs on every tick of every live
    daemon, and the store is restarted while it is in that state. No monkeypatch
    — the frozen clock makes the quiescence arithmetic exact, which is only true
    because `_touch_old` now stamps on that same clock."""
    directory = _redirect["events"]
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    # The database is created FIRST, on an empty spool, so the one-time legacy
    # migration is behind us and the file written next stays the file we wrote.
    # That is also the realistic shape: a live daemon receiving a LATE old-day
    # file, not a first-ever boot over legacy residue (which the merge tests own).
    event_store.open_store(create=True).close()
    path = _write_spool(directory, f"{old_day}.claude.104.jsonl",
                        [_rec(ts=f"{old_day}T09:00:00Z", kind="hook.deny",
                              agent="dev-multi", task="T-conserve")])
    folds = 0

    # PHASE 1 — the source is on disk and not yet quiescent. Two full restarts.
    # The row must be ingested, then HELD: a source that can still re-offer it
    # is a source that forbids the fold.
    for _ in range(2):
        store = event_store.open_store(create=True)  # fresh offsets: a restart
        try:
            for _tick in range(2):
                _touch_old(path, seconds=0.0, now=now)  # age 0 < 2 s: not quiescent
                report = store.ingest_once(now=now)
                folds += report["retention"]["rows_folded"]
                assert report["retention"]["rows_folded"] == 0, (
                    "a row whose source is still on disk must never be folded")
                assert report["retention"]["rows_retained_pending_spool"] == 1, (
                    "and being held back must be COUNTED, not silent")
        finally:
            store.close()
        assert path.exists(), "not quiescent means not deleted — the premise holds"
        assert _count(_redirect["db"]) == 1, "one event, one row, across restarts"

    # PHASE 2 — the writer goes quiet, the file is deleted, and only then does
    # the row become foldable. Restart again afterwards: the digest must not move.
    store = event_store.open_store(create=True)
    try:
        for report in _drain(store, directory, now):
            folds += report["retention"]["rows_folded"]
    finally:
        store.close()
    assert not path.exists(), "quiescent and fully consumed: the source is gone"

    for _ in range(2):
        store = event_store.open_store(create=True)  # restarts AFTER the fold
        try:
            for report in _drain(store, directory, now):
                folds += report["retention"]["rows_folded"]
        finally:
            store.close()

    assert folds == 1, (
        f"ONE event folded exactly ONCE over its whole life — got {folds}. "
        "More than one is the double count L-00000072 forbids; zero means the "
        "30-day retention silently stopped applying.")
    store = event_store.open_store(create=False)
    try:
        entry = next(m for m in store.digest_aggregates()["months"]
                     if m["month"] == old_day[:7])
        assert entry["total_events"] == 1, "the durable trail counts it once"
        assert entry["by_task"] == {"T-conserve": 1}, (
            "every dimension is folded once too — a duplicated row inflates "
            "by_task/by_agent just as permanently as it inflates the total")
    finally:
        store.close()
    assert _count(_redirect["db"]) == 0, "folded rows leave the table, nothing lingers"


# ---------------------------------------------------------------------------
# Canal B — ingested in the same tick, its files deliberately retained
# ---------------------------------------------------------------------------

def test_canal_b_is_ingested_in_the_same_tick_and_its_files_are_now_deleted(_redirect):
    """Spec §A.2: canal B goes straight into the database in the tick's own
    transaction.

    V1-c FLIPS THE SECOND HALF OF THIS RULE, and the flip is the point. V1-b
    RETAINED channel B's spool for exactly one reason — `_read_canal_b` and
    `otel_normalize` still globbed those files. V1-c moves those readers onto
    this store, so retaining the files would leave TWO live sources for one
    figure, which is the shape every duplication defect in this module came
    from. `_DELETE_CHANNELS` is `{"a", "b"}` from here on."""
    envelope = {"ts": "2026-07-29T10:00:00Z", "kind": "metrics",
                "path": "/v1/metrics", "provenance": str(_redirect["root"])}
    otel_file = _redirect["otel"] / "2026-07-29.4321.jsonl"
    otel_file.write_bytes((json.dumps(envelope) + "\n").encode("utf-8"))
    _touch_old(otel_file)
    _write_spool(_redirect["events"], "2026-07-29.claude.111.jsonl", [_rec(task="T-a")])
    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_inserted"] == 2, "both channels, one transaction"
    finally:
        store.close()
    conn = sqlite3.connect(str(_redirect["db"]))
    try:
        rows = dict(conn.execute("SELECT channel, kind FROM events").fetchall())
    finally:
        conn.close()
    assert rows["a"] == "hook.deny"
    assert rows["b"] == "otel.metrics", (
        "canal-B kinds are namespaced: `metrics` is not a member of canal A's "
        "closed KNOWN_KINDS vocabulary and must never be mistaken for one")
    assert not otel_file.exists(), (
        "V1-c: channel B's spool is CONSUMED AND DELETED — the readers moved "
        "onto the store, so a retained file would be a second live source")


def test_canal_b_retained_file_is_not_re_ingested_every_tick(_redirect):
    envelope = {"ts": "2026-07-29T10:00:00Z", "kind": "metrics", "path": "/v1/metrics"}
    otel_file = _redirect["otel"] / "2026-07-29.4322.jsonl"
    otel_file.write_bytes((json.dumps(envelope) + "\n").encode("utf-8"))
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 1
        second = store.ingest_once()
        assert second["rows_offered"] == 0, (
            "resume-by-offset means a retained file costs a stat, not a re-read")
    finally:
        store.close()


def test_dirty_notice_is_a_doorbell_carrying_no_rank(_redirect):
    """Iteration 5, C4: the receiver hands over NO `line_index`. If it ever did
    again, its counter would restart with its process and diverge from the file."""
    event_store.notify_dirty(_redirect["otel"] / "x.jsonl")
    taken = event_store.take_dirty_notices()
    assert taken == {str(_redirect["otel"] / "x.jsonl")}
    assert event_store.take_dirty_notices() == set(), "notices are consumed once"
    # And it never raises, whatever it is handed.
    event_store.notify_dirty(None)
    event_store.notify_dirty(object())  # type: ignore[arg-type]


def test_receiver_persist_rings_the_doorbell_without_a_rank(_redirect):
    receiver = _load("_probe_otel_receiver", "otel_receiver.py")
    seen: list[Any] = []
    receiver.set_dirty_notifier(seen.append)
    try:
        receiver.persist({"ts": "2026-07-29T10:00:00Z", "kind": "metrics"})
    finally:
        receiver.set_dirty_notifier(None)
    assert len(seen) == 1
    assert Path(seen[0]).parent == _redirect["otel"]
    # A doorbell that breaks the writer would break canal B's fail-open contract.
    receiver.set_dirty_notifier(lambda _p: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        receiver.persist({"ts": "2026-07-29T10:00:01Z", "kind": "metrics"})
    finally:
        receiver.set_dirty_notifier(None)


# ---------------------------------------------------------------------------
# Rollback — --export-spool
# ---------------------------------------------------------------------------

def test_export_spool_retires_the_database_and_reingests_without_duplicating(_redirect):
    """Iteration 2, C5 (the rename) + iteration 3, C1 (no overlap with a
    surviving original) + iteration 3, C2 (a nested directory the legacy globs
    cannot see)."""
    directory = _redirect["events"]
    path = _write_spool(directory, "2026-07-29.claude.121.jsonl",
                        [_rec(task=f"T-{i}") for i in range(3)])
    _touch_old(path)
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["deleted"] == 1
        result = store.export_spool(now=datetime(2026, 7, 29, 13, 0, tzinfo=timezone.utc))
    finally:
        store.close()
    assert result["status"] == "exported"
    assert result["rows_exported"] == 3
    assert result["db_retired_to"] is not None
    assert not _redirect["db"].exists(), (
        "leaving events.db in place would let a re-upgrade ingest the export ON TOP")
    assert Path(result["db_retired_to"]).exists()

    exported = sorted(directory.glob("exports/*/*.jsonl"))
    assert len(exported) == 1
    # Nested on purpose: merge/compact glob `*.jsonl` non-recursively.
    assert exported[0] not in set(directory.glob("*.jsonl"))

    store = event_store.open_store(create=True)
    try:
        report = store.ingest_once()
        assert report["rows_inserted"] == 3, "the export is re-ingested once"
        second = store.ingest_once()
        assert second["rows_inserted"] == 0
    finally:
        store.close()
    assert _count(_redirect["db"]) == 3, "a rollback then re-upgrade duplicates nothing"


def test_export_skips_rows_whose_original_is_still_on_disk(_redirect, monkeypatch):
    """The overlap that would double-count on re-upgrade: a surviving original
    plus its export are two `src_file`s carrying the same lines. Closed at the
    source — a row whose original file still exists is not exported at all."""
    directory = _redirect["events"]
    path = _write_spool(directory, "2026-07-29.claude.122.jsonl", [_rec(task="T-1")])
    _touch_old(path)
    real_unlink = Path.unlink
    monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: (
        (_ for _ in ()).throw(PermissionError(13, "held")) if self.name == path.name
        else real_unlink(self, *a, **k)))
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["delete_deferred"] == 1
        monkeypatch.setattr(Path, "unlink", real_unlink)
        result = store.export_spool(now=datetime(2026, 7, 29, 13, 0, tzinfo=timezone.utc))
    finally:
        store.close()
    assert result["rows_skipped_still_on_disk"] == 1
    assert result["rows_exported"] == 0
    assert sorted(directory.glob("exports/*/*.jsonl")) == []
    assert path.exists(), "the original is the surviving copy — it is re-read as itself"

    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 1
    finally:
        store.close()
    assert _count(_redirect["db"]) == 1, "one event, one row, no export/original overlap"


def test_export_reemits_digests_so_a_rollback_keeps_folded_history(_redirect):
    """Iteration 2, C4: without this, everything older than 30 days is lost at
    rollback — the fold deleted the rows, and only the digests table remembers."""
    directory = _redirect["events"]
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    _write_spool(directory, f"{old_day}.claude.123.jsonl",
                 [_rec(ts=f"{old_day}T09:00:00Z", kind="hook.deny")])
    store = event_store.open_store(create=True)
    try:
        _drain(store, directory, now)
        result = store.export_spool(now=now)
    finally:
        store.close()
    assert result["digests_written"] == 1
    digest = next(iter(directory.glob("exports/*/digest/*.json")))
    payload = json.loads(digest.read_text(encoding="utf-8"))
    assert payload["month"] == old_day[:7]
    assert payload["total_events"] == 1
    assert payload["days_folded"] == [old_day]


# ---------------------------------------------------------------------------
# The reader side — /api/events, digests, and the Couverture view
# ---------------------------------------------------------------------------

dashboard = _load("dashboard_for_store", "dashboard.py")


@pytest.fixture
def _dashboard_root(_redirect, monkeypatch):
    root = _redirect["root"] / "project"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTS_DASHBOARD_PROJECT_ROOT", str(root))
    dashboard._readers_mod.reset_cache_for_tests()
    dashboard._reset_canal_b_cache_for_tests()
    yield root


def test_api_events_switches_to_the_rowid_cursor_when_the_store_exists(
        _redirect, _dashboard_root):
    _write_spool(_redirect["events"], "2026-07-29.claude.131.jsonl",
                 [_rec(task="T-1"), _rec(task="T-2")])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    resp = dashboard.build_events_response({})
    assert resp["source"] == "sqlite"
    assert resp["cursor_unit"] == "db_rowid"
    assert [e["task"] for e in resp["events"]] == ["T-1", "T-2"]
    # `pruned_files` keeps its name and its emptiness rather than disappearing —
    # the contract's fields do not move under a consumer (iteration 1, C7).
    assert resp["pruned_files"] == []
    assert resp["aggregates"]["source"] == "sqlite"

    follow = dashboard.build_events_response({"cursor": [resp["next_cursor"]]})
    assert follow["events"] == [], "the cursor is honoured: nothing new"
    assert follow["cursor_reset"] is False


def test_api_events_falls_back_to_files_while_no_store_exists(_redirect, _dashboard_root):
    _write_spool(_redirect["events"], "2026-07-29.claude.132.jsonl", [_rec(task="T-1")])
    resp = dashboard.build_events_response({})
    assert resp["source"] == "spool_files"
    assert resp["cursor_unit"] == "byte_offset_per_file"
    assert len(resp["events"]) == 1


def test_a_cursor_from_the_other_unit_is_reset_never_reinterpreted(_redirect, _dashboard_root):
    """Two cursor units exist during the transition; a byte-offset cursor read as
    a rowid (or the reverse) would silently skip or replay. It travels through
    the ALREADY EXISTING reset path instead."""
    _write_spool(_redirect["events"], "2026-07-29.claude.133.jsonl", [_rec(task="T-1")])
    file_cursor = dashboard.build_events_response({})["next_cursor"]
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    resp = dashboard.build_events_response({"cursor": [file_cursor]})
    assert resp["cursor_reset"] is True
    assert resp["cursor_reset_reason"] == "cursor_unit_changed"
    assert len(resp["events"]) == 1, "a reset re-serves from the start, it never skips"


def test_api_events_degrades_on_a_schema_ahead_store_without_running_v1_sql(
        _redirect, _dashboard_root):
    store = event_store.open_store(create=True)
    store.connection.execute("PRAGMA user_version = 2")
    store.close()
    resp = dashboard.build_events_response({})
    assert resp["degraded"] is True
    assert resp["source"] == "schema_ahead"
    assert resp["events"] == []
    assert resp["cursor_unit"] == "db_rowid"
    assert "rolled back" in (resp["reason"] or "")


def test_digest_aggregates_come_from_the_table_once_the_store_exists(
        _redirect, _dashboard_root):
    """Iteration 1, C3: the JSON digest files FREEZE once the ingestion empties
    the spool, so a live store must never serve them. Both exist here; the table
    must win."""
    digest_dir = _redirect["events"] / "digest"
    digest_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / "2026-06.json").write_text(json.dumps({
        "month": "2026-06", "total_events": 4242, "by_kind": {}, "by_agent": {},
        "by_task": {}, "days_folded": [],
    }), encoding="utf-8")
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now - timedelta(days=45)).strftime("%Y-%m-%d")
    _write_spool(_redirect["events"], f"{old_day}.claude.134.jsonl",
                 [_rec(ts=f"{old_day}T09:00:00Z")])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=now)
    finally:
        store.close()
    aggregates = dashboard.build_events_response({})["aggregates"]
    assert aggregates["source"] == "sqlite"
    assert 4242 not in [m["total_events"] for m in aggregates["months"]], (
        "the frozen JSON digest must not be served alongside a live table")


def test_coverage_view_shows_the_ingestion_lag(_redirect, _dashboard_root):
    for i in range(4):
        path = _write_spool(_redirect["events"], f"2026-07-29.claude.{140 + i}.jsonl",
                            [_rec()])
        _touch_old(path, seconds=7200.0)
    event_store.open_store(create=True).close()
    snapshot = dashboard.build_snapshot(_dashboard_root)
    ingestion = snapshot["views"]["coverage"]["ingestion"]
    assert ingestion["status"] == "late"
    assert ingestion["spool_files_pending"] == 4
    assert "en retard depuis" in ingestion["message"]
    assert snapshot["ingestion"]["late"] is True


def test_coverage_says_unknown_rather_than_ok_when_nobody_supplied_a_status(_redirect):
    """Absence of a measurement is never a measurement of zero — the kit's rule,
    applied to this new section."""
    section = dashboard._readers_mod.build_coverage(
        {"status": "no_events", "records": [], "files": 0, "malformed": 0},
        {"collected": False}, dashboard._otel_normalize_mod, None)
    assert section["ingestion"]["status"] == "unknown"
    assert section["ingestion"]["late"] is None


def test_store_fingerprint_moves_with_the_data_never_with_the_tick(_redirect):
    """T-00000615: in WAL a commit lands in `-wal` and the main file's stat stays frozen, so
    every memo keyed on it served stale rows. Move on a DATA commit, never on an idle tick."""
    absent = event_store.store_fingerprint()
    with event_store.open_store(create=True) as store:  # held open, as the daemon holds it
        assert store.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert store.ingest_once(now=_FROZEN_NOW)["rows_inserted"] == 0
        empty = event_store.store_fingerprint()
        _write_spool(_redirect["events"], f"{_TODAY}.claude.61.jsonl", [_rec(task="T-1")])
        assert store.ingest_once(now=_FROZEN_NOW + timedelta(seconds=5))["rows_inserted"] == 1
        data = event_store.store_fingerprint()
        assert store.ingest_once(now=_FROZEN_NOW + timedelta(seconds=10))["rows_inserted"] == 0
        assert (absent[1], empty[1], empty != data) == (False, True, True), "DATA left it frozen"
        assert event_store.store_fingerprint() == data, "an idle 5 s tick moved the key"


# ---------------------------------------------------------------------------
# The tick loop itself
# ---------------------------------------------------------------------------

def test_ingest_loop_ticks_and_stops_cleanly(_redirect):
    _write_spool(_redirect["events"], "2026-07-29.claude.151.jsonl", [_rec(task="T-1")])
    loop = event_store.IngestLoop(interval=0.05)
    assert loop.start() is True
    try:
        deadline = time.monotonic() + 20.0
        while _count(_redirect["db"]) < 1 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _count(_redirect["db"]) == 1
    finally:
        assert loop.stop(timeout=10.0) is True
    assert loop.ticks >= 1


def test_ingest_loop_stop_reports_failure_rather_than_lying(_redirect):
    """`stop()` returning False is what tells `run_daemon` NOT to release the
    daemon lock: a thread still inside a transaction plus a second daemon
    starting would be two writers of a single-writer database (iteration 2,
    C10)."""
    loop = event_store.IngestLoop(interval=0.05)
    started = event_store.threading.Event()
    release = event_store.threading.Event()

    def _stuck() -> None:
        started.set()
        release.wait(30.0)

    loop.thread = event_store.threading.Thread(target=_stuck, daemon=True)
    loop.thread.start()
    assert started.wait(10.0)
    try:
        assert loop.stop(timeout=0.2) is False, (
            "a join that timed out must be reported, never papered over")
    finally:
        release.set()
        loop.thread.join(timeout=10.0)


def test_ingest_loop_survives_a_raising_tick(_redirect, monkeypatch):
    loop = event_store.IngestLoop(interval=0.05)
    loop.store = event_store.open_store(create=True)
    try:
        monkeypatch.setattr(loop.store, "ingest_once",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        report = loop.tick()
        assert report["status"] == "error"
        assert "RuntimeError" in report["error"]
    finally:
        loop.store.close()


# ---------------------------------------------------------------------------
# V1-c — PROJECT ATTRIBUTION OF CANAL B (T-00000050)
#
# Four points of a row's life cycle touch its `project`, and this section holds
# them to the SAME answer. Each test names the defect it pins; every one of them
# was a plan-critic blocker before it was a test.
# ---------------------------------------------------------------------------

def test_sentinel_is_never_foreign(_redirect):
    """GATE MUST-FIX M1 — the single most consequential rule in V1-c.

    A dev reading the rule as "field PRESENT and != own id -> foreign" would
    send EVERY host that declares nothing — Codex structurally, and any host
    whose env block the operator has not pasted yet — into `foreign_held`,
    i.e. straight out of the monetary totals. Silent, and massive: the
    dashboard would keep rendering a total, just a wrong and shrinking one
    (iteration 8, C4).

    THIS TEST ASSERTS THE VALUE STAMPED, not merely the absence of a
    quarantine (iteration 9, C4): a bug that stamped `PROJECT_UNSET` for the
    sentinel would pass a "was it quarantined?" test while producing exactly
    the outage above at the next open, when the relabel adopts it. Both
    literals are covered here — `"unattributed"` (the sentinel) and `"unset"`
    (PROJECT_UNSET), which are DIFFERENT strings and must never be conflated.
    """
    own = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=event_store.PROJECT_UNATTRIBUTED),
        _otel_envelope(project_id=event_store.PROJECT_UNSET, ts="2026-07-29T10:00:01Z"),
        _otel_envelope(project_id=own, ts="2026-07-29T10:00:02Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once()["rows_inserted"] == 3
    finally:
        store.close()

    stamped = [project for project, _body in _project_bodies(_redirect["db"])]
    assert stamped == [own, own, own], (
        "the sentinel and the literal 'unset' are NEVER foreign: each must be "
        f"stamped with the own project id, got {stamped}")

    # And the pure classifier says so directly, which is where the rule lives.
    assert event_store.declares_foreign_project(
        "b", json.dumps({"project_id": "unattributed"}), own) is False
    assert event_store.declares_foreign_project(
        "b", json.dumps({"project_id": "unset"}), own) is False
    assert event_store.declares_foreign_project(
        "b", json.dumps({}), own) is False, "an ABSENT field is never foreign either"
    assert event_store.declares_foreign_project(
        "b", json.dumps({"project_id": _OTHER_ID}), own) is True, (
        "the negative control: without this, the three assertions above could "
        "pass on a classifier that never returns True at all")


def test_foreign_row_is_quarantined_at_birth_and_never_whitened(_redirect):
    """Quarantine at BIRTH, at the single insertion site (iteration 3, C2).

    Defined any later, a pre-init day-file that survived a failed delete
    (L-00000035) and is re-read once the identity exists would be inserted
    under the real id with NO dedup collision — `project` is in the UNIQUE key
    — giving one duplicate row AND a neighbour's event whitened into local
    spend."""
    own = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=_OTHER_ID),
        _otel_envelope(project_id=own, ts="2026-07-29T10:00:01Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    rows = _project_bodies(_redirect["db"])
    assert [p for p, _b in rows] == [event_store.PROJECT_UNSET, own]

    # The open-time relabel must NOT adopt it — that is the defect the
    # Python-side classification of the DELETE exists to prevent.
    store = event_store.open_store(create=True)
    try:
        assert store.open_report["relabel"]["foreign_held"] == 1
        assert store.open_report["relabel"]["adopted"] == 0
        assert store.open_report["relabel"]["duplicates_deleted"] == 0
    finally:
        store.close()
    assert [p for p, _b in _project_bodies(_redirect["db"])] == [
        event_store.PROJECT_UNSET, own], "a quarantined row is never whitened"


def test_open_relabel_deletes_only_true_duplicates_never_a_foreign_row(_redirect):
    """V1-b ended the open block with a bare
    `DELETE FROM events WHERE project = 'unset'`, which would destroy the
    quarantine at the very open that creates it (iteration 3, C1).

    Here one physical line is ingested TWICE under two different `project`
    values — once before the identity exists, once after — which is the only
    way a genuine duplicate arises. The relabel must collapse those two into
    one and leave the foreign row alone."""
    own_line = _otel_envelope(project_id=None)
    del own_line["project_id"]
    path = _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        own_line, _otel_envelope(project_id=_OTHER_ID, ts="2026-07-29T10:00:01Z")])

    store = event_store.open_store(create=True)   # identity still absent
    try:
        store.ingest_once()
    finally:
        store.close()
    assert _count(_redirect["db"]) == 2

    # The identity appears; the SAME file is re-read from zero (offsets die with
    # the process), so both lines are offered again under the real id.
    own = _init_identity(_redirect)
    assert path.exists()
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        report = store.open_report["relabel"]
        assert report["foreign_held"] == 1, "the foreign row was NOT a candidate"
    finally:
        store.close()

    rows = _project_bodies(_redirect["db"])
    projects = sorted(p for p, _b in rows)
    assert projects == [own, event_store.PROJECT_UNSET], (
        f"exactly one row per physical line, foreign one still held: {rows}")


def test_pre_v1c_history_reread_after_the_flip_keeps_its_project_and_does_not_double(
        _redirect):
    """Iteration 3, C1 — the defect that made the classifier read `project_id`
    and never `provenance`.

    The provenance of every pre-V1-c envelope is an absolute PATH. Had the
    classifier compared THAT against the store's identity, the whole canal-B
    history would have been called foreign at the first restart after the flip,
    re-stamped `unset` — a new value in the UNIQUE key, hence a duplicate of
    every historical event, with one copy quarantined out of the totals for
    good. Same file, two reads across the flip: same `project`, one row."""
    own = _init_identity(_redirect)
    _redirect["own_root"].mkdir(parents=True, exist_ok=True)
    path = _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(str(_redirect["own_root"])),
        _legacy_otel_envelope(r"C:\elsewhere\moved", ts="2026-07-29T10:00:01Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    before = _project_bodies(_redirect["db"])
    assert [p for p, _b in before] == [own, own], "no legacy line is ever foreign"

    # The file is still on disk (the delete deferred by quiescence), so the next
    # process re-reads it from zero — AFTER the backfill rewrote the bodies.
    assert path.exists()
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    after = _project_bodies(_redirect["db"])
    assert len(after) == 2, f"a re-read must not duplicate: {after}"
    assert [p for p, _b in after] == [own, own]


def test_two_restarts_across_an_identity_transition_keep_exactly_one_row(_redirect):
    """The INVARIANT, stated as a test (iteration 4, C2): the same physical
    line, read across two restarts that straddle an identity transition, is
    exactly ONE row.

    `project` is in the UNIQUE key and the resume offsets do not survive the
    process, so a `project` value that moved between the two readings would
    make `INSERT OR IGNORE` unable to match — a second row for one audit
    line."""
    envelope = _otel_envelope(project_id=event_store.PROJECT_UNATTRIBUTED)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [envelope])

    store = event_store.open_store(create=True)      # restart 1: no identity
    try:
        store.ingest_once()
    finally:
        store.close()
    own = _init_identity(_redirect)
    store = event_store.open_store(create=True)      # restart 2: identity exists
    try:
        store.ingest_once()
    finally:
        store.close()

    rows = _project_bodies(_redirect["db"])
    assert len(rows) == 1, f"one physical line, one row, across the transition: {rows}"
    assert rows[0][0] == own


# --- the one-shot materialising backfill (M2) -------------------------------

def test_backfill_materialises_a_concordant_legacy_row_onto_the_current_id(_redirect):
    own = _init_identity(_redirect)
    _redirect["own_root"].mkdir(parents=True, exist_ok=True)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(str(_redirect["own_root"]))])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    store = event_store.open_store(create=True)
    try:
        report = store.open_report["backfill"]
        assert report["scanned"] == 1
        assert report["rows_materialised"] == 1
        assert report["concordant"] == 1
        assert report["sentinelled"] == 0
    finally:
        store.close()

    rows = _project_bodies(_redirect["db"])
    assert len(rows) == 1, "materialising a body must never mint a second row"
    project, body = rows[0]
    assert project == own
    assert body["project_id"] == own
    assert body["project_attributed_by"] == "backfill", (
        "attribution by INFERENCE must stay distinguishable from attribution by "
        "declaration — one counter holding both is how an inference becomes a "
        "measurement (iteration 9, C3)")


def test_backfill_sentinels_a_legacy_row_whose_provenance_does_not_match(_redirect):
    """MUST-FIX M3's case: a moved clone / renamed repo / re-cased Windows
    path. `provenance` was written as an exact `str(Path.resolve())`, so such a
    line has NO evidence left. It is not foreign (nothing declares another id)
    and not attributable — the sentinel keeps it inside the census and inside
    the labelled totals instead of dropping it out of the partition without a
    trace (iteration 9, C1)."""
    _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(r"C:\elsewhere\a-clone-that-moved")])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    store = event_store.open_store(create=True)
    try:
        report = store.open_report["backfill"]
        assert (report["concordant"], report["sentinelled"]) == (0, 1)
    finally:
        store.close()
    _project, body = _project_bodies(_redirect["db"])[0]
    assert body["project_id"] == event_store.PROJECT_UNATTRIBUTED
    assert "project_attributed_by" not in body, (
        "the sentinel is self-describing; claiming a backfill attribution here "
        "would assert an inference nobody made")


def test_backfill_is_idempotent_and_says_so(_redirect):
    """MUST-FIX M2. Re-run after a mid-pass restart, the backfill finds no row
    without the field and is a NO-OP — so `rows_materialised == 0` next to
    `scanned == 0` means ALREADY DONE, not FAILED. Distinguishable in the
    journal, which is the whole point of journalling it."""
    _init_identity(_redirect)
    _redirect["own_root"].mkdir(parents=True, exist_ok=True)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(str(_redirect["own_root"])),
        _legacy_otel_envelope(r"C:\elsewhere\moved", ts="2026-07-29T10:00:01Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    first = None
    for expected in (2, 0):
        store = event_store.open_store(create=True)
        try:
            report = store.open_report["backfill"]
            assert report["rows_materialised"] == expected
            assert report["scanned"] == expected
            assert report["error"] is None
            if first is None:
                first = _project_bodies(_redirect["db"])
        finally:
            store.close()
    assert _project_bodies(_redirect["db"]) == first, (
        "a second pass must not touch a single byte")
    assert _count(_redirect["db"]) == 2, "no duplicate, ever"


def test_backfill_leaves_the_unique_key_columns_untouched(_redirect):
    """ONLY THE BODY IS REWRITTEN. Moving `project`, `src_file`, `line_index` or
    `line_hash` would mint a second identity for a line already stored — the
    double count this module exists to prevent. The `line_hash` therefore no
    longer matches the rewritten body: an ACCEPTED, DECLARED cost (the export is
    no longer byte-fidèle for these rows, and it retires the database in the
    same operation, so nothing re-ingests the old bytes)."""
    _init_identity(_redirect)
    _redirect["own_root"].mkdir(parents=True, exist_ok=True)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(str(_redirect["own_root"]))])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    def _key_columns() -> list[tuple]:
        conn = sqlite3.connect(str(_redirect["db"]))
        try:
            return conn.execute(
                "SELECT src_file, line_index, line_hash FROM events "
                "WHERE channel = 'b' ORDER BY id").fetchall()
        finally:
            conn.close()

    before = _key_columns()
    store = event_store.open_store(create=True)
    try:
        assert store.open_report["backfill"]["rows_materialised"] == 1
    finally:
        store.close()
    assert _key_columns() == before, "a UNIQUE-key column moved — identity drift"


def test_after_the_backfill_no_canal_b_row_lacks_the_promoted_field(_redirect):
    """The property the five display buckets rest on: a TOTAL partition. After
    the pass, "field absent" is not a state any row is in — and
    `otel_receiver.persist()` guarantees no future line can be."""
    _init_identity(_redirect)
    _redirect["own_root"].mkdir(parents=True, exist_ok=True)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(str(_redirect["own_root"])),
        _legacy_otel_envelope(r"C:\elsewhere\moved", ts="2026-07-29T10:00:01Z"),
        _otel_envelope(project_id=_OTHER_ID, ts="2026-07-29T10:00:02Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    store = event_store.open_store(create=True)
    try:
        pass
    finally:
        store.close()
    bodies = [body for _p, body in _project_bodies(_redirect["db"])]
    assert len(bodies) == 3
    assert all(isinstance(b.get("project_id"), str) and b["project_id"] for b in bodies)


# --- the fold (iteration 9, C2) ---------------------------------------------

def test_expired_foreign_row_is_deleted_without_bumping_a_local_digest(_redirect):
    """A quarantined row reaching the 30-day cutoff must NOT fold into the local
    digests. Otherwise a neighbouring project's events inflate this project's
    only durable audit trail — permanently, since the digest is all that
    survives the window (iteration 3's C3, re-opened by a scope cut at
    iteration 9's C2)."""
    own = _init_identity(_redirect)
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now.date() - timedelta(days=40)).isoformat()
    _write_otel_spool(_redirect["otel"], f"{old_day}.1.jsonl", [
        _otel_envelope(project_id=_OTHER_ID, ts=f"{old_day}T10:00:00Z"),
        _otel_envelope(project_id=own, ts=f"{old_day}T10:00:01Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        reports = _drain(store, _redirect["otel"], now)
        folded = [r["retention"]["rows_folded"] for r in reports]
        expired = [r["retention"]["foreign_held_expired"] for r in reports]
        assert sum(folded) == 2, f"both rows leave the table: {folded}"
        assert sum(expired) == 1, f"exactly one of them was foreign: {expired}"
        months = store.digest_aggregates()["months"]
        entry = next(m for m in months if m["month"] == old_day[:7])
        assert entry["total_events"] == 1, (
            "the LOCAL digest counts the local row only — a foreign row must "
            "never bump `total` nor `kind:otel.*`")
        assert entry["by_kind"] == {"otel.metrics": 1}
        assert store.meta_counter("foreign_held_expired") == 1
    finally:
        store.close()
    assert _count(_redirect["db"]) == 0


def test_foreign_held_expired_is_cumulative_and_survives_a_restart(_redirect):
    """A per-tick counter says nothing the morning after (iteration 4, C5), so
    the tally lives in `meta` and accumulates across processes."""
    own = _init_identity(_redirect)
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    old_day = (now.date() - timedelta(days=40)).isoformat()

    for index in (1, 2):
        _write_otel_spool(_redirect["otel"], f"{old_day}.{index}.jsonl", [
            _otel_envelope(project_id=_OTHER_ID, ts=f"{old_day}T10:00:0{index}Z")])
        store = event_store.open_store(create=True)
        try:
            _drain(store, _redirect["otel"], now)
        finally:
            store.close()

    store = event_store.open_store(create=False)
    try:
        assert store.meta_counter("foreign_held_expired") == 2, (
            "the cumulative tally must survive the restart between the two folds")
        assert store.attribution_counters()["foreign_held_expired"] == 2
    finally:
        store.close()
    assert own  # the local id is irrelevant to the tally, and that is the point


# --- the store-side reader --------------------------------------------------

def test_canal_b_bodies_returns_quarantined_rows_too(_redirect):
    """The reader is NOT filtered by `project`: a quarantined row must be
    VISIBLE (a displayed `foreign_held` fact) and not silently subtracted. The
    census keys on the body; the money totals exclude the bucket. Two
    questions, one read."""
    own = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=own),
        _otel_envelope(project_id=_OTHER_ID, ts="2026-07-29T10:00:01Z"),
        _otel_envelope(project_id=event_store.PROJECT_UNATTRIBUTED, ts="2026-07-29T10:00:02Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        read = store.canal_b_bodies()
        assert read["status"] == "ok"
        assert read["rows"] == 3
        declared = [json.loads(b)["project_id"] for b in read["bodies"]]
        assert declared == [own, _OTHER_ID, event_store.PROJECT_UNATTRIBUTED]
    finally:
        store.close()


def test_canal_b_bodies_degrades_in_every_non_ok_status(_redirect):
    store = event_store.open_store(create=False)   # absent
    try:
        read = store.canal_b_bodies()
        assert read["status"] == "absent"
        assert read["bodies"] == []
        assert read["reason"]
    finally:
        store.close()


# --- T-00000613: the same reader, without the channel in RAM ----------------

def test_iter_canal_b_bodies_yields_exactly_what_the_eager_reader_returns(_redirect):
    """The streaming twin bounds MEMORY and must change nothing about WHAT is
    read — same rows, same `ORDER BY id`, quarantined rows included. A
    divergence here would have made the cheap path a second, weaker reader,
    which is the one thing this module's doctrine forbids."""
    own = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=own),
        _otel_envelope(project_id=_OTHER_ID, ts="2026-07-29T10:00:01Z"),
        _otel_envelope(project_id=event_store.PROJECT_UNATTRIBUTED, ts="2026-07-29T10:00:02Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        eager = store.canal_b_bodies()["bodies"]
        streamed = list(store.iter_canal_b_bodies())
        assert streamed == eager
        assert [json.loads(b)["project_id"] for b in streamed] == [
            own, _OTHER_ID, event_store.PROJECT_UNATTRIBUTED]
    finally:
        store.close()


def test_iter_canal_b_bodies_is_lazy_and_never_materialises_the_channel(_redirect):
    """THE WHOLE POINT, and it took two drafts to make it bite.

    The first version asserted `isinstance(..., GeneratorType)`, then `next()`,
    then the length of the rest — and the binôme showed all three GREEN on
    `for row in conn.execute(...).fetchall(): yield str(row[0])`, which is the
    exact regression this is here to catch. Protocol shape says nothing about
    WHEN SQLite does the work.

    So this measures the work instead, through the progress handler: after the
    FIRST `next()` a streaming cursor has done no measurable work, while
    `fetchall()` has done all of it. Measured on the mutant: 0 ticks streaming,
    200 eager."""
    own = _init_identity(_redirect)
    # The step is 50 VM instructions, so the corpus has to be big enough for an
    # eager read to cross it. A three-row fixture cannot tell the two apart.
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=own, ts=f"2026-07-29T10:00:{i % 60:02d}Z")
        for i in range(2000)
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        ticks = [0]
        store._conn.set_progress_handler(
            lambda: ticks.__setitem__(0, ticks[0] + 1) or 0, 50)
        try:
            iterator = store.iter_canal_b_bodies()
            assert isinstance(iterator, types.GeneratorType)
            next(iterator)
            after_first = ticks[0]
            rest = len(list(iterator))
        finally:
            store._conn.set_progress_handler(None, 0)
        assert after_first == 0, (
            f"{after_first} progress ticks before the second row: the channel "
            "was read eagerly")
        assert ticks[0] > 0, "no work measured at all — the handler never fired"
        assert rest == 1999
    finally:
        store.close()


def test_the_open_pass_backfill_streams_the_channel_too(_redirect):
    """THE SECOND SITE OF THE SAME DEFECT, found by the binôme and easy to
    miss: `_backfill_promote_project_field` runs inside
    `open_store(create=True)`, which the daemon's INGEST THREAD calls at
    start-up — in the very process the OS killed. It used to `fetchall()` the
    whole of channel B before serving a single request.

    `fetchall` is made to raise rather than asserted about afterwards, because
    the failure has to be attributable to THIS pass and not to a peak measured
    somewhere downstream."""
    own = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _legacy_otel_envelope(provenance="/somewhere/else", ts="2026-07-29T10:00:00Z"),
        _legacy_otel_envelope(provenance="/somewhere/else", ts="2026-07-29T10:00:01Z"),
    ])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    class _NoFetchAllCursor:
        def __init__(self, cursor): self._cursor = cursor
        def __iter__(self): return iter(self._cursor)
        def fetchall(self):
            raise AssertionError("fetchall() re-materialises the whole channel")
        def __getattr__(self, name): return getattr(self._cursor, name)

    class _NoFetchAllConn:
        def __init__(self, conn): self._conn = conn
        def execute(self, *args, **kwargs):
            return _NoFetchAllCursor(self._conn.execute(*args, **kwargs))
        def executemany(self, *args, **kwargs):
            return self._conn.executemany(*args, **kwargs)
        def __getattr__(self, name): return getattr(self._conn, name)

    conn = sqlite3.connect(_redirect["db"])
    try:
        report = event_store._backfill_promote_project_field(_NoFetchAllConn(conn), own)
    finally:
        conn.close()
    assert report.get("error") is None, report
    assert report["scanned"] == 2, report
    assert report["sentinelled"] == 2, report


# --- T-00000616: the fold's watched connection -------------------------------

_FOLD_CANDIDATES_SQL = "SELECT id, day, kind, agent, task, src_file, channel"
_FOLD_BODY_BY_ID_SQL = "SELECT body FROM events WHERE id"
_FOLD_WRITE_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
_FOLD_INSERT_SQL = ("INSERT INTO events (project, channel, src_file, line_index,"
                    " line_hash, day, ts, kind, body, ingested_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)")


class _WatchedCandidates:
    """The fold's candidate cursor, iterated THROUGH: it records the id the
    fold has just been handed, and the moment the cursor is exhausted."""

    def __init__(self, cursor, watch: dict):
        self._cursor = cursor
        self._watch = watch

    def __iter__(self):
        for row in self._cursor:
            self._watch["pulled"] = row[0]
            yield row
        self._watch["exhausted"] = True

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _WatchedFoldConn:
    """A connection proxy for `_fold_retention_locked`, recording in `watch`:
      * `opened`       — the candidate SELECT was issued;
      * `reads`        — (id read by id, id the candidate cursor had JUST
                         yielded), one per by-id body read;
      * `early_writes` — every INSERT/UPDATE/DELETE/REPLACE issued through
                         `execute` OR `executemany` while the candidate cursor
                         is not yet exhausted (before it is opened counts too).
    `vanish=True` makes every by-id body read find nothing — the one state the
    fold must refuse noisily.
    `candidates` is the SQL prefix that marks THE candidate cursor. Its default
    is the fold's, so the T-00000616 witnesses call it unchanged; the relabel
    witness (T-00000769) passes its own SELECT and reuses the same
    `exhausted` / `early_writes` bookkeeping.
    Fail-closed on SQL it does not recognise: a renamed candidate SELECT never
    marks the cursor exhausted, so every later write is reported early; a
    renamed by-id read is never recorded, so the read counts go wrong."""

    def __init__(self, conn, *, vanish: bool = False,
                 candidates: str = _FOLD_CANDIDATES_SQL):
        self._conn = conn
        self._vanish = vanish
        self._candidates = candidates
        self.watch: dict = {"opened": False, "pulled": None, "exhausted": False,
                            "reads": [], "early_writes": []}

    def _note_write(self, sql: str) -> None:
        if not self.watch["exhausted"] and _FOLD_WRITE_RE.search(sql):
            self.watch["early_writes"].append(sql)

    def execute(self, sql, *args):
        self._note_write(sql)
        if sql.startswith(self._candidates):
            self.watch["opened"] = True
            return _WatchedCandidates(self._conn.execute(sql, *args), self.watch)
        if sql.startswith(_FOLD_BODY_BY_ID_SQL):
            self.watch["reads"].append((args[0][0], self.watch["pulled"]))
            if self._vanish:
                return self._conn.execute("SELECT NULL WHERE 0")
        return self._conn.execute(sql, *args)

    def executemany(self, sql, *args):
        self._note_write(sql)
        return self._conn.executemany(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_fold_retention_streams_the_candidates_never_materialises_body(_redirect):
    """THE THIRD SITE (T-00000616): the retention fold runs on EVERY tick and
    used to pull every expired row WITH its body into one list — measured at
    40.82 MB for 2,000 rows x 20 KB. It now streams a body-less candidate
    cursor and reads a body by id only for a channel-`b` row it is about to
    fold, because the classifier needs it (R5).

    What each fixture element is here to catch, so none of it reads as noise:
      * 1,000 channel-`a` + 1,000 channel-`b` rows of ~20 KB past the cutoff:
        a `fetchall()`/`list(cursor)` or a loop that keeps rows with their
        bodies crosses the bound.
      * 500 of the `b` rows declare `_OTHER_ID` AT THE TOP LEVEL OF THE BODY
        (the column stays the own id — the classifier reads the body): a fold
        that no longer reads the body counts 0 foreign rows instead of 500.
      * ONE HELD row (its spool file still "on disk") with a ~12 MB body: a
        streamed loop that still projects `body` in the candidate SELECT reads
        it on every tick; the by-id read never does.
      * A WATCHED CONNECTION, because the heap bound cannot see everything:
        once the candidate SELECT is body-less, `list(cursor)` materialises
        only small tuples — measured 0.70 MB against 0.13 MB streamed on this
        fixture, both far under the body bound. So the streaming itself is
        pinned deterministically: every by-id body read must be for the row
        the candidate cursor has JUST yielded (no row pulled ahead), there
        are exactly 1,000 of them (the non-held `b` rows), and the held row's
        body is never read. And NO WRITE before the candidate cursor is
        exhausted: an INSERT/UPDATE/DELETE issued mid-loop — a per-row
        `DELETE FROM events WHERE id = ?`, say — would delete under an open
        cursor, and the watcher reports it. An SQL text the watcher does not
        recognise fails these asserts rather than passing them.
    The functional asserts come BEFORE the peak, so a red on the peak alone
    also proves the reports equal what the eager code produced.

    The bound is the PYTHON HEAP as `tracemalloc` sees it — RSS and SQLite's
    page cache are not measured."""
    import tracemalloc

    own = _init_identity(_redirect)
    now = _FROZEN_NOW
    old_day = (now.date() - timedelta(days=40)).isoformat()
    ts = f"{old_day}T10:00:00Z"
    held_src = "otel/held.jsonl"
    pad = "x" * 20_000

    def fixture_rows():
        # A generator handed to `executemany`, not a list: the fixture itself
        # does not hold ~52 MB of bodies alive while the store is written.
        for i in range(1000):
            yield (own, "a", f"events/{old_day}.merged.jsonl", i, f"a{i}",
                   old_day, ts, "hook.deny",
                   json.dumps(_rec(ts=ts, data={"pad": pad})), ts)
        for i in range(1000):
            declared = _OTHER_ID if i < 500 else own
            yield (own, "b", f"otel/{old_day}.merged.jsonl", i, f"b{i}",
                   old_day, ts, "otel.metrics",
                   json.dumps(_otel_envelope(project_id=declared, ts=ts, pad=pad)), ts)
        yield (own, "b", held_src, 0, "held", old_day, ts, "otel.metrics",
               json.dumps(_otel_envelope(project_id=own, pad="y" * 12_000_000)), ts)

    store = event_store.open_store(create=True)
    try:
        assert store.project == own
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, fixture_rows())
        conn.execute("COMMIT")
        held_id = conn.execute(
            "SELECT id FROM events WHERE src_file = ?", (held_src,)).fetchone()[0]

        watched = _WatchedFoldConn(conn)
        store._conn = watched
        tracemalloc.start()
        try:
            conn.execute("BEGIN IMMEDIATE")
            baseline, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            fold = store._fold_retention_locked(now, frozenset({held_src}))
            _, peak = tracemalloc.get_traced_memory()
            conn.execute("COMMIT")
        finally:
            tracemalloc.stop()
            store._conn = conn
        peak -= baseline

        assert fold["rows_folded"] == 2000, fold
        assert fold["foreign_held_expired"] == 500, (
            f"the classifier must still read the body of a channel-b row: {fold}")
        assert fold["rows_retained_pending_spool"] == 1, fold
        assert fold["days_folded"] == [old_day], fold
        entry = next(m for m in store.digest_aggregates()["months"]
                     if m["month"] == old_day[:7])
        assert entry["total_events"] == 1500, entry
        assert entry["by_kind"] == {"hook.deny": 1000, "otel.metrics": 500}, entry
        assert store.meta_counter("foreign_held_expired") == 500
        left = store._conn.execute("SELECT src_file FROM events").fetchall()
        assert left == [(held_src,)], "only the held row may survive the fold"
        assert peak < 8_000_000, (
            f"fold peak {peak / 1e6:.2f} MB: bodies were materialised (eager "
            "candidates, or the held row's 12 MB body read on this tick)")
        reads = watched.watch["reads"]
        assert len(reads) == 1000, (
            f"{len(reads)} by-id body reads: exactly the 1,000 non-held "
            "channel-b rows must read their body, one at a time")
        assert all(read == pulled for read, pulled in reads), (
            "a body was read for a row other than the one the candidate cursor "
            "had just yielded: the candidates were pulled ahead (materialised)")
        assert held_id not in {read for read, _pulled in reads}, (
            "the held row's body was read on this tick")
        assert watched.watch["exhausted"], (
            "the candidate cursor was never drained (or its SELECT was renamed)")
        assert watched.watch["early_writes"] == [], (
            "written before the candidate cursor was exhausted — a row deleted "
            f"under an open cursor: {watched.watch['early_writes'][:3]}")
    finally:
        store.close()


def test_fold_retention_reads_no_body_when_the_own_id_is_unset(_redirect):
    """The witness's twin with NO identity (`project.json` absent, this file's
    default): `classifier_reads_body` is False for every row, so the fold reads
    NO body at all — and still counts a row declaring another id LOCALLY, since
    a repo with no identity cannot disown anything (`declares_foreign_project`,
    case "own id is UNSET"). Keyed on the channel alone, as the first cut of
    T-00000616 was, the fold paid a by-id read for each of the four non-held
    channel-`b` rows here for a body the classifier then ignored."""
    now = _FROZEN_NOW
    old_day = (now.date() - timedelta(days=40)).isoformat()
    ts = f"{old_day}T10:00:00Z"
    held_src = "otel/held.jsonl"
    unset = event_store.PROJECT_UNSET

    def fixture_rows():
        for i in range(3):
            yield (unset, "a", f"events/{old_day}.merged.jsonl", i, f"a{i}",
                   old_day, ts, "hook.deny", json.dumps(_rec(ts=ts)), ts)
        declared_ids = (_OTHER_ID, _OTHER_ID, _OWN_ID, None)
        for i, declared in enumerate(declared_ids):
            envelope = (_otel_envelope(ts=ts) if declared is None
                        else _otel_envelope(project_id=declared, ts=ts))
            yield (unset, "b", f"otel/{old_day}.merged.jsonl", i, f"b{i}",
                   old_day, ts, "otel.metrics", json.dumps(envelope), ts)
        yield (unset, "b", held_src, 0, "held", old_day, ts, "otel.metrics",
               json.dumps(_otel_envelope(project_id=_OTHER_ID, ts=ts)), ts)

    store = event_store.open_store(create=True)
    try:
        assert store.project == unset
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, fixture_rows())
        conn.execute("COMMIT")

        watched = _WatchedFoldConn(conn)
        store._conn = watched
        try:
            conn.execute("BEGIN IMMEDIATE")
            fold = store._fold_retention_locked(now, frozenset({held_src}))
            conn.execute("COMMIT")
        finally:
            store._conn = conn

        assert fold["rows_folded"] == 7, fold
        assert fold["foreign_held_expired"] == 0, fold
        assert fold["rows_retained_pending_spool"] == 1, fold
        entry = next(m for m in store.digest_aggregates()["months"]
                     if m["month"] == old_day[:7])
        assert entry["total_events"] == 7, entry
        assert entry["by_kind"] == {"hook.deny": 3, "otel.metrics": 4}, entry
        assert store.meta_counter("foreign_held_expired") == 0
        assert len(watched.watch["reads"]) == 0, (
            f"{len(watched.watch['reads'])} by-id body reads with the own id "
            "unset: the classifier parses no body here, so the fold must read none")
        assert watched.watch["exhausted"], watched.watch
        assert watched.watch["early_writes"] == [], watched.watch["early_writes"]
        left = conn.execute("SELECT src_file FROM events").fetchall()
        assert left == [(held_src,)], "only the held row may survive the fold"
    finally:
        store.close()


def test_classifier_reads_body_is_the_classifiers_own_early_return():
    """`classifier_reads_body` decides which rows the fold pays a by-id body
    read for; `declares_foreign_project` decides which rows are foreign. Let
    them drift — the classifier widened to another channel while the fold keeps
    the old guard — and an expired foreign row is folded into the LOCAL digests
    with its body never read. So, over every channel x own-id combination:
      * predicate False -> the classifier is False for EVERY body, a foreign
        declaration included: no body the fold skips could have mattered;
      * predicate True  -> the body DOES matter (foreign -> True, own -> False):
        the fold reads no body it did not need.
    The last assert pins the one combination that reads, so the loop cannot
    pass vacuously on a predicate that is never True."""
    unset = event_store.PROJECT_UNSET
    foreign_text = json.dumps(_otel_envelope(project_id=_OTHER_ID))
    bodies = (None, "", "not json", "[]", "42",
              json.dumps(_otel_envelope()),
              json.dumps(_otel_envelope(project_id=_OWN_ID)),
              json.dumps(_otel_envelope(project_id=event_store.PROJECT_UNATTRIBUTED)),
              json.dumps(_otel_envelope(project_id=unset)),
              foreign_text,
              _otel_envelope(project_id=_OTHER_ID))
    reading = set()
    for own in (unset, _OWN_ID):
        for channel in ("a", "b", "", "c", "B"):
            if event_store.classifier_reads_body(channel, own):
                reading.add((channel, own))
                assert event_store.declares_foreign_project(channel, foreign_text, own), (
                    channel, own)
                assert not event_store.declares_foreign_project(
                    channel, json.dumps(_otel_envelope(project_id=own)), own), (channel, own)
                continue
            for body in bodies:
                assert not event_store.declares_foreign_project(channel, body, own), (
                    f"channel {channel!r}, own id {own!r}: the classifier reads a "
                    f"body the fold never fetches ({body!r})")
    assert reading == {("b", _OWN_ID)}, reading


def test_fold_retention_refuses_to_run_outside_the_callers_transaction(_redirect):
    """The connection is `isolation_level=None`: outside the caller's BEGIN
    IMMEDIATE every statement of the fold would commit on its own, and a
    failure between the digest upsert and a DELETE chunk would leave rows
    counted AND still present — counted again on the next tick. So the fold
    refuses before it even opens its candidate cursor, and the store is left
    exactly as it was."""
    now = _FROZEN_NOW
    old_day = (now.date() - timedelta(days=40)).isoformat()
    ts = f"{old_day}T10:00:00Z"
    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(_FOLD_INSERT_SQL, (event_store.PROJECT_UNSET, "a",
                                        f"events/{old_day}.merged.jsonl", 0, "a0",
                                        old_day, ts, "hook.deny",
                                        json.dumps(_rec(ts=ts)), ts))
        conn.execute("COMMIT")
        assert not conn.in_transaction

        watched = _WatchedFoldConn(conn)
        store._conn = watched
        try:
            with pytest.raises(sqlite3.ProgrammingError, match="BEGIN IMMEDIATE"):
                store._fold_retention_locked(now, frozenset())
        finally:
            store._conn = conn

        assert not watched.watch["opened"], "the candidate cursor was opened first"
        assert watched.watch["early_writes"] == [], watched.watch["early_writes"]
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 0
    finally:
        store.close()


def test_fold_retention_a_candidate_vanishing_mid_fold_is_an_error_not_a_skip(_redirect):
    """A candidate whose by-id body read finds nothing can only mean ANOTHER
    writer removed it under the daemon's BEGIN IMMEDIATE — the sole-writer
    invariant broken. A silent `continue` hid it: the tick folded the rest,
    that row neither counted nor deleted, and reported success. It now raises
    `sqlite3.OperationalError`, which `ingest_once` rolls back and reports —
    driven here THROUGH `ingest_once`, the one production caller, so the
    ROLLBACK proven is the real one and not a test's."""
    own = _init_identity(_redirect)
    now = _FROZEN_NOW
    old_day = (now.date() - timedelta(days=40)).isoformat()
    ts = f"{old_day}T10:00:00Z"
    store = event_store.open_store(create=True)
    try:
        assert store.project == own
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, (
            (own, "a", f"events/{old_day}.merged.jsonl", 0, "a0",
             old_day, ts, "hook.deny", json.dumps(_rec(ts=ts)), ts),
            (own, "b", f"otel/{old_day}.merged.jsonl", 0, "b0", old_day, ts,
             "otel.metrics", json.dumps(_otel_envelope(project_id=_OTHER_ID, ts=ts)), ts),
            (own, "b", f"otel/{old_day}.merged.jsonl", 1, "b1", old_day, ts,
             "otel.metrics", json.dumps(_otel_envelope(project_id=own, ts=ts)), ts),
        ))
        conn.execute("COMMIT")

        def snapshot() -> dict:
            return {query: sorted(conn.execute(query).fetchall(), key=repr)
                    for query in ("SELECT * FROM events", "SELECT * FROM digests",
                                  "SELECT * FROM digest_days", "SELECT * FROM meta")}

        before = snapshot()
        watched = _WatchedFoldConn(conn, vanish=True)
        store._conn = watched
        try:
            report = store.ingest_once(now=now)
        finally:
            store._conn = conn

        assert watched.watch["reads"], (
            "the by-id read was never reached: this test would prove nothing")
        assert (report["error"] or "").startswith("OperationalError: events row "), report
        assert "vanished under BEGIN IMMEDIATE" in report["error"], report
        assert not conn.in_transaction, "the tick left its transaction open"
        assert snapshot() == before, "the tick wrote something despite the error"
    finally:
        store.close()


# --- T-00000769: the same family off the tick — relabel and export ----------

_RELABEL_CANDIDATES_SQL = "SELECT id, channel, body FROM events WHERE project"
_EXPORT_ROWS_SQL = "SELECT channel, src_file, line_index, body FROM events"


class _FailingCursor:
    """A cursor iterated THROUGH that raises `sqlite3.OperationalError` on its
    `after`-th row (0-based): a read error surfacing MID-loop, after the caller
    has already acted on some rows. `read` is the number of rows actually
    handed over before the raise, `rows` those rows."""

    def __init__(self, cursor, after: int, error: BaseException | None = None):
        self._cursor = cursor
        self._after = after
        self._error = error
        self.read = 0
        self.rows: list[tuple] = []

    def __iter__(self):
        for n, row in enumerate(self._cursor):
            if n == self._after:
                raise self._error or sqlite3.OperationalError("disk I/O error (simulated)")
            self.read += 1
            self.rows.append(tuple(row))
            yield row

    def fetchall(self):
        raise sqlite3.OperationalError("disk I/O error (simulated)")


class _FailingConn:
    """A connection whose ONE statement starting with `prefix` returns a
    `_FailingCursor`; everything else passes through. `opened` proves the
    watched SELECT ran — a renamed SELECT would otherwise make the test vacuous."""

    def __init__(self, conn, prefix: str, after: int, error: BaseException | None = None):
        self._conn = conn
        self._prefix = prefix
        self._after = after
        self._error = error
        self.cursor: _FailingCursor | None = None

    @property
    def opened(self) -> bool:
        return self.cursor is not None

    def execute(self, sql, *args):
        cursor = self._conn.execute(sql, *args)
        if sql.startswith(self._prefix):
            self.cursor = _FailingCursor(cursor, self._after, self._error)
            return self.cursor
        return cursor

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _Crash(BaseException):
    """A process death, as close as a test gets: a BaseException, so no
    `except Exception`/`except OSError` on the way out can tidy up after it."""


def _insert_export_fixture(store, srcs, per_file: int = 3) -> int:
    """`per_file` stored rows per `src_file`, none of whose originals is on
    disk — so every one of them is exportable. Bodies are distinct, so a line
    exported twice or out of order is visible. Returns the row count."""
    unset = event_store.PROJECT_UNSET
    ts = f"{_TODAY}T10:00:00Z"
    conn = store._conn
    conn.execute("BEGIN IMMEDIATE")
    conn.executemany(_FOLD_INSERT_SQL, (
        (unset, src.split("/", 1)[0], src, i, f"{src}-{i}", _TODAY, ts, "hook.deny",
         json.dumps(_rec(ts=ts, task=f"{src}#{i}")), ts)
        for src in srcs for i in range(per_file)))
    conn.execute("COMMIT")
    return len(srcs) * per_file


def test_open_relabel_streams_the_unset_rows_never_materialises_body(_redirect):
    """`_relabel_unset_locked` runs inside `open_store(create=True)` — every
    daemon (re)start and every `--ingest-once` once the identity resolves — and
    it used to `fetchall()` every `unset` row WITH its body: measured at
    20.78 MB on this fixture, against 0.05 MB for a streamed cursor. On this
    repo, where every row is `unset` until `project.json` exists, the first open
    after it appears would have materialised the whole store.

    `body` cannot leave the SELECT: the classifier parses it for every
    channel-`b` row once the own id is set — that is how a quarantined row is
    told apart from one written before the identity existed.

    What each fixture element is here to catch:
      * 1,000 small `a` rows + 1,000 `b` rows of ~20 KB, all `unset`: a
        `fetchall()` or a loop that keeps `(rowid, body)` crosses the bound.
      * 500 of the `b` rows declare `_OTHER_ID`: a relabel that stops handing
        the body to the classifier adopts them (`foreign_held` 0, not 500).
      * THE WATCHED CONNECTION (`candidates` = this SELECT): the cursor must be
        drained (`exhausted`) and NO write may be issued before that — an
        `UPDATE` per row inside the loop would write under an open cursor.
    Functional asserts come first, so a red on the peak alone also proves the
    report equals what the eager code produced. The bound is the PYTHON HEAP as
    `tracemalloc` sees it — RSS and SQLite's page cache are not measured."""
    import tracemalloc

    own = _init_identity(_redirect)
    unset = event_store.PROJECT_UNSET
    ts = f"{_TODAY}T10:00:00Z"
    pad = "x" * 20_000

    def fixture_rows():
        # A generator handed to `executemany`: the fixture does not keep ~20 MB
        # of bodies alive while the store is written.
        for i in range(1000):
            yield (unset, "a", f"a/{_TODAY}.claude.1.jsonl", i, f"a{i}",
                   _TODAY, ts, "hook.deny", json.dumps(_rec(ts=ts, task=f"T-{i}")), ts)
        for i in range(1000):
            declared = _OTHER_ID if i < 500 else own
            yield (unset, "b", f"b/{_TODAY}.1.jsonl", i, f"b{i}",
                   _TODAY, ts, "otel.metrics",
                   json.dumps(_otel_envelope(project_id=declared, ts=ts, pad=pad)), ts)

    store = event_store.open_store(create=True)
    try:
        assert store.project == own
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, fixture_rows())
        conn.execute("COMMIT")

        watched = _WatchedFoldConn(conn, candidates=_RELABEL_CANDIDATES_SQL)
        tracemalloc.start()
        try:
            baseline, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            report = event_store._relabel_unset_locked(watched, own)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        peak -= baseline

        assert report == {"scanned": 2000, "adopted": 1500, "duplicates_deleted": 0,
                          "foreign_held": 500, "error": None}, report
        by_project = dict(conn.execute(
            "SELECT project, COUNT(*) FROM events GROUP BY project").fetchall())
        assert by_project == {own: 1500, unset: 500}, by_project
        held = conn.execute(
            "SELECT COUNT(*) FROM events WHERE project = ? AND channel = 'b' "
            "AND json_extract(body, '$.project_id') = ?", (unset, _OTHER_ID)).fetchone()[0]
        assert held == 500, "the rows left `unset` must be exactly the foreign ones"
        assert peak < 4_000_000, (
            f"relabel peak {peak / 1e6:.2f} MB: the unset rows were materialised "
            "with their bodies")
        assert watched.watch["exhausted"], (
            "the candidate cursor was never drained (fetchall(), or its SELECT renamed)")
        assert watched.watch["early_writes"] == [], (
            "written before the candidate cursor was exhausted: "
            f"{watched.watch['early_writes'][:3]}")
    finally:
        store.close()


def test_open_relabel_cursor_error_moves_nothing_and_reports_partial_scan(_redirect):
    """F2 of the closing pair (T-00000769): streaming moved the relabel's read
    error from BEFORE the loop (a failed `fetchall()`) to the MIDDLE of it,
    after some rows were already classified. A NON-REGRESSION PIN, not a red
    witness — the streamed code already behaves this way; nothing tested it:
      * nothing moves — `adopted` and `duplicates_deleted` stay 0 and every
        `unset` row is still `unset` (a write issued with a half-classified
        `movable` would adopt rows whose neighbours were never looked at);
      * the counts are PARTIAL and say so — `scanned` equals the rows the
        cursor actually handed over, `foreign_held` the foreign ones among
        them, and `error` names the cause."""
    own = _init_identity(_redirect)
    unset = event_store.PROJECT_UNSET
    ts = f"{_TODAY}T10:00:00Z"
    store = event_store.open_store(create=True)
    try:
        assert store.project == own
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        rows = []
        for i in range(10):
            if i % 3 == 0:   # channel b, alternately foreign and own-declared
                declared = _OTHER_ID if i % 2 == 0 else own
                rows.append((unset, "b", f"b/{_TODAY}.1.jsonl", i, f"b{i}", _TODAY, ts,
                             "otel.metrics",
                             json.dumps(_otel_envelope(project_id=declared, ts=ts)), ts))
            else:
                rows.append((unset, "a", f"a/{_TODAY}.claude.1.jsonl", i, f"a{i}", _TODAY,
                             ts, "hook.deny", json.dumps(_rec(ts=ts, task=f"T-{i}")), ts))
        conn.executemany(_FOLD_INSERT_SQL, rows)
        conn.execute("COMMIT")

        failing = _FailingConn(conn, _RELABEL_CANDIDATES_SQL, after=4)
        report = event_store._relabel_unset_locked(failing, own)
        assert failing.opened, "the relabel SELECT was renamed: this test proves nothing"
        read = failing.cursor.rows
        foreign_seen = sum(
            1 for _id, channel, body in read
            if event_store.declares_foreign_project(str(channel), body, own))
        by_project = dict(conn.execute(
            "SELECT project, COUNT(*) FROM events GROUP BY project").fetchall())
    finally:
        store.close()

    assert failing.cursor.read == 4
    assert report["scanned"] == failing.cursor.read, report
    assert report["foreign_held"] == foreign_seen, (report, foreign_seen)
    assert report["adopted"] == 0 and report["duplicates_deleted"] == 0, report
    assert (report["error"] or "").startswith("OperationalError: disk I/O error"), report
    assert by_project == {unset: 10}, f"a failed scan moved rows: {by_project}"


def test_export_spool_streams_rows_to_disk_never_materialises_the_store(_redirect):
    """`export_spool` — the manual rollback — re-emits the WHOLE store, and it
    used to `fetchall()` every row with its body and then `"".join` each file:
    measured at 41.12 MB on this fixture (the bodies held twice) against
    0.19 MB streamed row by row to disk. A flush per FILE would not be enough:
    the largest spool file measured on this repo is 123.2 MB on its own.

    What each fixture element is here to catch:
      * 1,000 small `a` rows in one file + 1,000 `b` rows of ~20 KB: a
        `fetchall()` of the store crosses the bound.
      * The `b` ids ALTERNATE between two files (~10 MB each): accumulating a
        file before publishing it crosses the bound, and an export that groups
        by `id` order instead of `(channel, src_file)` breaks both files into
        one-row fragments — `files_written` and the sha256 go wrong.
      * ONE `a` file still on disk: its rows are counted as skipped and never
        exported (iteration 3, C1 — an original and its export never both count).
      * The sha256 of each export is compared with the sha256 computed, in
        flux, over the store's own rows in `line_index` order: byte fidelity,
        not only a row count.
    Functional asserts first; the bound is the PYTHON HEAP (`tracemalloc`)."""
    import hashlib
    import tracemalloc

    unset = event_store.PROJECT_UNSET
    ts = f"{_TODAY}T10:00:00Z"
    pad = "x" * 20_000
    a_src = f"a/{_TODAY}.claude.1.jsonl"
    a_on_disk_src = f"a/{_TODAY}.claude.2.jsonl"
    b_srcs = (f"b/{_TODAY}.1.jsonl", f"b/{_TODAY}.2.jsonl")

    def fixture_rows():
        for i in range(1000):
            yield (unset, "a", a_src, i, f"a{i}", _TODAY, ts, "hook.deny",
                   json.dumps(_rec(ts=ts, task=f"T-{i}")), ts)
        for i in range(5):
            yield (unset, "a", a_on_disk_src, i, f"d{i}", _TODAY, ts, "hook.deny",
                   json.dumps(_rec(ts=ts, task=f"D-{i}")), ts)
        for i in range(1000):
            yield (unset, "b", b_srcs[i % 2], i // 2, f"b{i}", _TODAY, ts,
                   "otel.metrics", json.dumps(_otel_envelope(ts=ts, seq=i, pad=pad)), ts)

    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, fixture_rows())
        conn.execute("COMMIT")
        expected: dict[tuple[str, str], str] = {}
        for channel, src in (("a", a_src), ("b", b_srcs[0]), ("b", b_srcs[1])):
            digest = hashlib.sha256()
            for (body,) in conn.execute(
                    "SELECT body FROM events WHERE channel = ? AND src_file = ? "
                    "ORDER BY line_index", (channel, src)):
                digest.update((body + "\n").encode("utf-8"))
            expected[(channel, src.split("/", 1)[1])] = digest.hexdigest()
        # Created AFTER the open, so the legacy migration never sees it.
        (_redirect["events"] / a_on_disk_src.split("/", 1)[1]).write_text(
            "{}\n", encoding="utf-8", newline="\n")

        tracemalloc.start()
        try:
            baseline, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            result = store.export_spool(now=_FROZEN_NOW)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        peak -= baseline
    finally:
        store.close()

    assert result["status"] == "exported", result
    assert result["files_written"] == 3, result
    assert result["rows_exported"] == 2000, result
    assert result["rows_skipped_still_on_disk"] == 5, result
    assert result["db_retired_to"] is not None and not _redirect["db"].exists(), result
    actual: dict[tuple[str, str], str] = {}
    for channel, root in (("a", _redirect["events"]), ("b", _redirect["otel"])):
        for path in sorted(root.glob("exports/*/*.jsonl")):
            with open(path, "rb") as handle:
                actual[(channel, path.name)] = hashlib.file_digest(handle, "sha256").hexdigest()
        assert not list(root.rglob("._tmp_*.part")), "a temp file survived a clean export"
    assert actual == expected, "each export must carry its file's rows, in order, byte for byte"
    assert peak < 4_000_000, (
        f"export peak {peak / 1e6:.2f} MB: rows (or a whole file) were "
        "materialised before reaching the disk")


def test_export_spool_interrupted_read_does_not_retire_the_database(_redirect):
    """A NON-REGRESSION ARM, not a red witness: the eager export did not retire
    the database on a read error either (it returned before writing anything).
    What streaming changes is WHEN the error can surface — mid-loop, after some
    files are already on disk — so this pins what the operator is left with:
      * the database is NOT retired and still readable;
      * the files completed before the error are counted, and were written in
        the PREPARATION directory `exports.partial/<stamp>/` (S-00002496),
        which the ingester never globs — never under `exports/`, where they
        would be ingested on top of the rows still stored; since S-00002537
        that preparation is REMOVED on the way out (no orphan copy per failed
        attempt), `reason` names it, says the database was not retired and
        that a re-run is safe, and `staged` is exactly what is left: nothing;
      * the file IN FLIGHT when the error hit leaves nothing: no target, and no
        `._tmp_*.part` under either export root (R1 — `_publish_lines`
        unlinks its temp file on any exception).
    The cursor is a proxy that raises `sqlite3.OperationalError` on its 6th
    row, i.e. in the middle of the second file's group."""
    unset = event_store.PROJECT_UNSET
    ts = f"{_TODAY}T10:00:00Z"
    stamp = event_store._export_stamp(_FROZEN_NOW)
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl", f"b/{_TODAY}.2.jsonl")

    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(_FOLD_INSERT_SQL, (
            (unset, src[0], src, i, f"{src}-{i}", _TODAY, ts, "hook.deny",
             json.dumps(_rec(ts=ts, task=f"T-{i}")), ts)
            for src in srcs for i in range(3)))
        conn.execute("COMMIT")

        failing = _FailingConn(conn, _EXPORT_ROWS_SQL, after=5)
        store._conn = failing
        try:
            result = store.export_spool(now=_FROZEN_NOW)
        finally:
            store._conn = conn
        assert failing.opened, "the export SELECT was renamed: this test proves nothing"
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 9
    finally:
        store.close()

    assert result["status"] != "exported", result
    assert result["db_retired_to"] is None, result
    assert _redirect["db"].exists(), "the database was retired after a failed read"
    assert result["files_written"] == 1 and result["rows_exported"] == 3, result
    reason = result["reason"] or ""
    assert reason.startswith("OperationalError: disk I/O error (simulated)"), reason
    assert "1 file(s) already written" in reason, reason
    assert str(_redirect["events"] / "exports.partial" / stamp) in reason, reason
    assert "preparation removed" in reason, reason
    assert "database NOT retired" in reason, reason
    assert "re-running the export is safe" in reason.lower(), reason
    assert result["staged"] == [] and result["roots"] == [], result
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports").exists(), (
            f"an interrupted export published under {root / 'exports'}: the "
            "ingester reads it on top of the rows still stored")
        assert not (root / "exports.partial" / stamp).exists(), (
            f"the interrupted preparation was left under {root}")
    for root in (_redirect["events"], _redirect["otel"]):
        assert not list(root.rglob("._tmp_*.part")), (
            f"a temp file survived the interrupted export under {root}")


def test_publish_lines_a_source_failing_mid_write_leaves_no_part_file_and_no_target(_redirect):
    """R1 — `_publish_lines`' OWN witness of its failure path. It writes an
    iterable one element at a time, so its source can now fail AFTER bytes
    reached the temp file (the export's cursor does exactly that). On any
    exception the temp file is unlinked and re-raised: no `._tmp_*.part` is left
    behind, a new target is never created, and an existing target keeps its
    bytes (the replace never ran). The generator checks that the temp file DID
    exist before it raises, so the cleanup asserted is not vacuous."""
    root = _redirect["root"] / "publish"
    new_target = root / "new" / "file.jsonl"
    old_target = root / "old" / "file.jsonl"
    event_store._publish_lines(old_target, ("old\n",))
    seen: list[int] = []

    def failing_source(directory: Path):
        yield "first\n"
        yield "x" * 100_000 + "\n"   # past any text buffer: bytes hit the temp file
        seen.append(len(list(directory.glob("._tmp_*.part"))))
        raise sqlite3.OperationalError("read failed mid-file (simulated)")

    for target in (new_target, old_target):
        with pytest.raises(sqlite3.OperationalError, match="mid-file"):
            event_store._publish_lines(target, failing_source(target.parent))
    assert seen == [1, 1], f"the temp file was not there to clean up: {seen}"
    assert not new_target.exists(), "a failed publish created its target"
    assert old_target.read_text(encoding="utf-8") == "old\n", (
        "a failed publish touched an existing target")
    assert not list(root.rglob("._tmp_*.part")), "a temp file survived a failed publish"


# --- T-00000769, closing-pair pass: staging, commit point, recovery ---------
#
# The export's COMMIT POINT is the rename that retires `events.db`. Before it,
# every file lives in `exports.partial/<stamp>/`, which no ingester glob reaches
# (`*.jsonl`, `exports/*/*.jsonl`); after it, each root's staging is promoted to
# `exports/<stamp>/`. So at every instant exactly one of {the database, the
# ingestable export} carries the history — never both (double count), never
# neither for longer than the next daemon start (the recovery promotes what a
# retired database proves).

@pytest.mark.parametrize("interruption", ["read_error", "process_death"])
def test_export_spool_interrupted_then_ticked_counts_every_row_once(_redirect, interruption):
    """S-00002496 — the MAJOR of exec-critic (S-00002495), as a witness. RED on
    332b24a7: the completed file of an interrupted export sat in
    `exports/<stamp>/`, the next tick ingested it under a NEW `src_file` key
    (`a/exports/<stamp>/…`) on top of the rows still stored — 9 rows for 6
    events. Prepared under `exports.partial/`, it is invisible: still 6.

    Two interruptions, because since S-00002537 a CAUGHT error also removes
    the preparation — which alone would keep this count right even with a
    preparation under `exports/`. A process DEATH cleans nothing up: there,
    only the preparation's location keeps the tick from counting it twice."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        conn = store._conn
        error = _Crash("killed mid-export (simulated)") if interruption == "process_death" else None
        failing = _FailingConn(conn, _EXPORT_ROWS_SQL, after=4, error=error)  # mid 2nd file
        store._conn = failing
        try:
            if error is None:
                result = store.export_spool(now=_FROZEN_NOW)
                assert result["files_written"] == 1 and result["db_retired_to"] is None, result
            else:
                with pytest.raises(_Crash):
                    store.export_spool(now=_FROZEN_NOW)
        finally:
            store._conn = conn
        assert failing.opened, "the export SELECT was renamed: this test proves nothing"
        tick = store.ingest_once(now=_FROZEN_NOW)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        store.close()
    assert count == stored == 6, (
        f"{count} rows after one tick for {stored} events: the interrupted export's "
        "completed file was ingested on top of the rows still stored")
    assert tick["rows_inserted"] == 0, tick


def test_export_spool_crash_between_retire_and_promotion_is_recovered_at_the_next_open(
        _redirect, monkeypatch):
    """T2 of critic-opus (S-00002502): the promotion comes AFTER the retire, and
    a death between the two is recovered by the next `open_store(create=True)`
    — the daemon's start — under `.maintenance.lock`.

    The crash is injected INSIDE the promotion: the first root (`a`) is really
    promoted, then the process "dies" (a BaseException nothing catches). So
    the state left is the worst mixed one — `a` published, `b` still staged,
    the database retired. The recovery must promote `b` (its retired database
    is the proof) and the next tick must count each event ONCE.

    Promoting BEFORE the retire would leave `a` published NEXT TO a live
    database here: the open finds the database, runs no recovery, and the tick
    ingests `a`'s export on top of its rows (9, not 6) — the count comes first
    for that reason."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    stamp = event_store._export_stamp(_FROZEN_NOW)
    real_promote = getattr(event_store, "_promote_staged", None)
    promoted: list[Path] = []

    def crash_after_the_first(staging, final):
        promoted.append(Path(final))
        if real_promote is not None:
            real_promote(staging, final)
        if len(promoted) == 1:
            raise _Crash("killed right after the first promotion (simulated)")

    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        monkeypatch.setattr(event_store, "_promote_staged", crash_after_the_first,
                            raising=False)
        with pytest.raises(_Crash):
            store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()

    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok", store.reason
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events after a crash mid-export")
    assert _redirect["db"].with_name(f"events.db.exported-{stamp}").exists()
    assert [p.parent.parent.name for p in promoted] == ["events", "otel"], (
        "the recovery did not promote the staging the crash left behind")
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports.partial" / stamp).exists()


def test_export_spool_a_write_error_mid_export_is_a_result_and_publishes_nothing(
        _redirect, monkeypatch):
    """F1 of critic-fable / T4 of critic-opus (S-00002502): an `OSError` while
    WRITING (here ENOSPC on the second file) escaped `export_spool` on
    332b24a7 — `except sqlite3.Error` only — so the CLI died with a traceback
    and whatever was already written sat under `exports/`. Now: a dict result,
    the database kept, NOTHING under `exports/` on either root, and the
    prepared part REMOVED and named in `reason` (S-00002537).

    Then the promise of that reason is kept: a RE-RUN at the SAME stamp starts
    from a clean staging — a stale one a crashed attempt could not clean is
    planted, and removed first because no retired database proves it — and
    ends exported, with each event counted once."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl", f"b/{_TODAY}.2.jsonl")
    stamp = event_store._export_stamp(_FROZEN_NOW)
    real_publish = event_store._publish_lines
    calls: list[Path] = []

    def enospc_on_the_second(target, lines):
        calls.append(Path(target))
        if len(calls) == 2:
            raise OSError(errno.ENOSPC, "No space left on device (simulated)")
        return real_publish(target, lines)

    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs, per_file=2)
        monkeypatch.setattr(event_store, "_publish_lines", enospc_on_the_second)
        result = store.export_spool(now=_FROZEN_NOW)
        assert isinstance(result, dict)
        assert result["status"] != "exported" and result["db_retired_to"] is None, result
        assert _redirect["db"].exists()
        reason = result["reason"] or ""
        assert reason.startswith("OSError"), reason
        assert "No space left on device" in reason, reason
        assert "database NOT retired" in reason, reason
        assert str(_redirect["events"] / "exports.partial" / stamp) in reason, reason
        assert "preparation removed" in reason, reason
        staging = _redirect["events"] / "exports.partial" / stamp
        for root in (_redirect["events"], _redirect["otel"]):
            assert not (root / "exports").exists(), f"published under {root}/exports"
            assert not (root / "exports.partial" / stamp).exists(), (
                f"the failed preparation was left under {root}")

        staging.mkdir(parents=True)
        (staging / "leftover.jsonl").write_text('{"kind": "stale"}\n', encoding="utf-8",
                                                newline="\n")
        monkeypatch.setattr(event_store, "_publish_lines", real_publish)
        again = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert again["status"] == "exported" and again["reason"] is None, again
    assert again["unproven_stagings_removed"] == [str(staging)], again
    assert again["files_written"] == 3 and again["rows_exported"] == stored, again
    names = {root.name: sorted(p.name for p in (root / "exports" / stamp).glob("*.jsonl"))
             for root in (_redirect["events"], _redirect["otel"])}
    assert names == {"events": [srcs[0].split("/", 1)[1]],
                     "otel": sorted(s.split("/", 1)[1] for s in srcs[1:])}, names

    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6


@pytest.mark.parametrize("failing_select", [
    "SELECT month, dimension, key, count FROM digests",
    "SELECT day FROM digest_days",
], ids=["digest_aggregates", "digest_days"])
def test_export_spool_an_unreadable_digest_is_a_read_error_and_retires_nothing(
        _redirect, failing_select):
    """The digests are the ONLY copy of the history older than 30 days (the fold
    deleted its rows), and both readers SWALLOWED `sqlite3.Error`:
    `digest_aggregates()` into a degraded payload with no months,
    `_digest_days()` into `[]`. On 1589aa0e the export then went on and
    RETIRED the database — 0 digests, or a digest whose `days_folded` is empty
    — so the folded history was lost without a word. A digest read that did
    not come from SQLite is now a READ error before the commit point: the
    database is NOT retired, `reason` names the digests, and the preparation
    is removed (S-00002537). The same stamp then re-runs cleanly once the read
    works, which also proves the fixture's digest is real."""
    src = f"a/{_TODAY}.claude.1.jsonl"
    stamp = event_store._export_stamp(_FROZEN_NOW)
    store = event_store.open_store(create=True)
    try:
        _insert_export_fixture(store, (src,), per_file=2)
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO digests (month, dimension, key, count) "
                     "VALUES ('2026-06', 'total', '', 5)")
        conn.execute("INSERT INTO digest_days (month, day) VALUES ('2026-06', '2026-06-01')")
        conn.execute("COMMIT")

        failing = _FailingConn(conn, failing_select, after=0)
        store._conn = failing
        try:
            result = store.export_spool(now=_FROZEN_NOW)
        finally:
            store._conn = conn
        assert failing.opened, f"{failing_select!r} was renamed: this test proves nothing"
        assert result["status"] != "exported" and result["db_retired_to"] is None, result
        assert _redirect["db"].exists(), "the database was retired over an unreadable digest"
        reason = result["reason"] or ""
        assert "digest" in reason.lower(), reason
        assert "database NOT retired" in reason, reason
        staging = _redirect["events"] / "exports.partial" / stamp
        assert str(staging) in reason and "preparation removed" in reason, reason
        assert not staging.exists(), "the failed preparation was left behind"
        for root in (_redirect["events"], _redirect["otel"]):
            assert not (root / "exports").exists(), f"published under {root}/exports"

        again = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert again["status"] == "exported" and again["digests_written"] == 1, again
    digest = _redirect["events"] / "exports" / stamp / "digest" / "2026-06.json"
    payload = json.loads(digest.read_text(encoding="utf-8"))
    assert payload["total_events"] == 5 and payload["days_folded"] == ["2026-06-01"], payload


def test_export_spool_breaks_line_index_ties_by_id_whatever_index_the_planner_picks(
        _redirect):
    """F3 of critic-fable (S-00002502): the identity is `(project, src_file,
    line_index, line_hash)`, so two rows of ONE file can share a `line_index`
    (an own row and a quarantined one, or a byte-different rebirth). Their
    order in the export was whatever SQLite's plan produced. Today's plan
    (scan `events_channel_id`, then a stable sort) happens to give id order —
    so the fixture adds an index that orders those ties by `project DESC`,
    exactly what any future index on those columns could do, and asserts
    that the export still writes them in `id` order."""
    src = f"a/{_TODAY}.claude.1.jsonl"
    ts = f"{_TODAY}T10:00:00Z"
    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        for project, line_index, task in (("aaa", 0, "first"), ("zzz", 0, "second"),
                                          ("aaa", 1, "third")):
            conn.execute(_FOLD_INSERT_SQL, (project, "a", src, line_index, task, _TODAY, ts,
                                            "hook.deny", json.dumps(_rec(ts=ts, task=task)),
                                            ts))
        conn.execute("COMMIT")
        conn.execute("CREATE INDEX test_tie_order "
                     "ON events (channel, src_file, line_index, project DESC)")
        planner_order = [json.loads(b)["task"] for (b,) in conn.execute(
            "SELECT body FROM events ORDER BY channel, src_file, line_index")]
        assert planner_order == ["second", "first", "third"], (
            f"the fixture no longer makes ties leave id order ({planner_order}): "
            "this test would prove nothing")
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert result["status"] == "exported", result
    stamp = event_store._export_stamp(_FROZEN_NOW)
    exported = _redirect["events"] / "exports" / stamp / src.split("/", 1)[1]
    tasks = [json.loads(line)["task"]
             for line in exported.read_text(encoding="utf-8").splitlines()]
    assert tasks == ["first", "second", "third"], (
        f"ties on line_index left id order: {tasks}")


def test_export_spool_never_builds_a_path_from_an_unsafe_src_file(_redirect):
    """Security advisory of S-00002491: an export target is built from the
    stored `src_file` key. A key whose file part is empty, `.` or `..`, or
    still carries a separator (`\\`), a NUL or a drive colon AFTER the
    `/`→`__` replacement would aim at the export directory itself, at its
    parent, or somewhere else entirely on Windows. Such a key cannot come
    from the ingester (it stores `<channel>/<file name>`); it can only come
    from a damaged or hand-edited database — so it is SKIPPED, counted, and
    named in the report, never written and never miscounted.

    On 332b24a7 the `..`/`.`/empty keys were silently counted as "original
    still on disk" (`base/..` exists), which told the operator a lie about
    where those rows live; the backslash key was exported as-is, and the NUL
    key raised a ValueError out of the export."""
    unsafe = ["a/..", "a/.", "a/", "..", "a/x\\y", "a/x\x00y", "a/C:x", "b/.."]
    safe = f"a/{_TODAY}.claude.1.jsonl"
    ts = f"{_TODAY}T10:00:00Z"
    unset = event_store.PROJECT_UNSET
    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        conn.execute("BEGIN IMMEDIATE")
        for n, key in enumerate(unsafe):
            channel = key.split("/", 1)[0] if "/" in key else "a"
            conn.execute(_FOLD_INSERT_SQL, (unset, channel, key, 0, f"u{n}", _TODAY, ts,
                                            "hook.deny", json.dumps(_rec(ts=ts)), ts))
        for i in range(2):
            conn.execute(_FOLD_INSERT_SQL, (unset, "a", safe, i, f"s{i}", _TODAY, ts,
                                            "hook.deny", json.dumps(_rec(ts=ts)), ts))
        conn.execute("COMMIT")
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert result["status"] == "exported", result
    assert result["rows_skipped_unsafe_name"] == len(unsafe), result
    assert sorted(result["unsafe_src_files"]) == sorted(unsafe), result
    assert result["rows_skipped_still_on_disk"] == 0, (
        "an unsafe key was miscounted as an original still on disk", result)
    assert result["files_written"] == 1 and result["rows_exported"] == 2, result
    stamp = event_store._export_stamp(_FROZEN_NOW)
    for root in (_redirect["events"], _redirect["otel"]):
        written = sorted(p.relative_to(root).as_posix()
                         for p in (root / "exports").rglob("*") if p.is_file())
        expected = [f"exports/{stamp}/{safe.split('/', 1)[1]}"] if root.name == "events" else []
        assert written == expected, written


def test_promote_retired_staging_promotes_only_what_a_retired_database_proves(_redirect):
    """The recovery half of T2 (S-00002503), unit by unit. A staging is promoted
    IFF `<db>.exported-<stamp>` exists — that file is the proof the commit
    point was crossed. Otherwise it is an export that never retired its
    database (interrupted, refused), and promoting it would double count.
    It DELETES NOTHING: an unproven staging stays, and a target that already
    exists — even empty — is never replaced (a POSIX rename would replace an
    empty directory silently). And `_migrate_legacy_spool` runs it only on a
    still-ABSENT database, under its lock."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    events_dir = _redirect["events"]

    def stage(stamp: str, retired: bool) -> Path:
        staging = events_dir / "exports.partial" / stamp
        staging.mkdir(parents=True)
        (staging / "x.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
        if retired:
            db.with_name(f"events.db.exported-{stamp}").write_bytes(b"")
        return staging

    proven = stage("20260729T120000Z", retired=True)
    unproven = stage("20260729T120001Z", retired=False)
    blocked = stage("20260729T120002Z", retired=True)
    (events_dir / "exports" / "20260729T120002Z").mkdir(parents=True)

    report = event_store._promote_retired_staging(db)
    assert report["promoted"] == [str(events_dir / "exports" / "20260729T120000Z")], report
    assert len(report["errors"]) == 1 and "20260729T120002Z" in report["errors"][0], report
    assert not proven.exists()
    assert (events_dir / "exports" / "20260729T120000Z" / "x.jsonl").exists()
    assert (unproven / "x.jsonl").exists(), "an unproven staging was touched"
    assert (blocked / "x.jsonl").exists(), "a refused promotion lost its staging"
    assert list((events_dir / "exports" / "20260729T120002Z").iterdir()) == [], (
        "an existing export directory was replaced")

    late = stage("20260729T120003Z", retired=True)
    db.write_bytes(b"")   # a database exists: the migration does not run at all
    assert event_store._migrate_legacy_spool(db)["status"] == "already_present"
    assert (late / "x.jsonl").exists(), "promoted next to an existing database"
    db.unlink()
    migration = event_store._migrate_legacy_spool(db)
    assert migration["promoted"] == [str(events_dir / "exports" / "20260729T120003Z")], (
        migration)


def test_the_export_recovery_is_reported_at_open_so_a_refused_promotion_is_visible(
        _redirect, capsys):
    """The recovery runs inside `open_store(create=True)` — the daemon's start,
    or `--ingest-once` — and its report used to stop inside
    `_migrate_legacy_spool`: a promotion REFUSED there (an `exports/<stamp>/`
    already present, never replaced) left a prepared export on disk that no
    output mentioned. It is now `open_report["export_recovery"]`, printed by
    `--ingest-once` next to the relabel and backfill journals. Like them it
    is present on EVERY create=True open: "not run, and why" (the database
    already exists) is a different fact from "ran, nothing to promote".
    Since S-00002537 a refused promotion also keeps the store ABSENT (status
    `recovery_pending`): creating it would end the recovery for good."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    events_dir = _redirect["events"]
    for stamp in ("20260729T120000Z", "20260729T120002Z"):
        staging = events_dir / "exports.partial" / stamp
        staging.mkdir(parents=True)
        (staging / f"{_TODAY}.claude.9.jsonl").write_text(
            json.dumps(_rec(task=f"T-{stamp}")) + "\n", encoding="utf-8", newline="\n")
        db.with_name(f"events.db.exported-{stamp}").write_bytes(b"")
    (events_dir / "exports" / "20260729T120002Z").mkdir(parents=True)

    assert event_store.main(["--ingest-once"]) == 0
    recovery = json.loads(capsys.readouterr().out)["open"]["export_recovery"]
    assert recovery["promoted"] == [str(events_dir / "exports" / "20260729T120000Z")], recovery
    assert len(recovery["promotion_errors"]) == 1, recovery
    assert str(events_dir / "exports.partial" / "20260729T120002Z") in (
        recovery["promotion_errors"][0]), recovery
    assert not db.exists(), "the store was created over a pending recovery"

    blocker = events_dir / "exports" / "20260729T120002Z"
    blocker.rename(events_dir / "moved-aside")
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok", store.reason
        assert store.open_report["export_recovery"] == {
            "promoted": [str(blocker)], "promotion_errors": []}, store.open_report
    finally:
        store.close()
    store = event_store.open_store(create=True)   # the database exists now
    try:
        assert "already" in store.open_report["export_recovery"]["skipped"], (
            store.open_report)
    finally:
        store.close()


# --- T-00000769, round-2 pass (S-00002536 → decision S-00002537) -------------

def test_a_refused_recovery_keeps_the_store_absent_and_is_retried_every_tick(_redirect):
    """F2 of both critics, round 2: the recovery ran ONCE. A promotion refused
    at the daemon's start (here an `exports/<stamp>/` already present, never
    replaced) left that root's rows in a preparation no later open looked at:
    the store was created, so the recovery never ran again — 3 of 6 rows, for
    good. Now the migration answers `recovery_pending`, the store stays
    `absent`, and `IngestLoop.tick` retries the open on every tick: once the
    blocker is moved aside, the next tick promotes and every row is there.
    Accepted cost (S-00002537): while blocked nothing is ingested — nothing is
    lost either, the spool waits. And `roots` names only what this export
    really promoted (F5 of critic-fable)."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    stamp = event_store._export_stamp(_FROZEN_NOW)
    blocker = _redirect["events"] / "exports" / stamp
    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        blocker.mkdir(parents=True)
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()

    loop = event_store.IngestLoop(interval=0.01)
    loop.store = event_store.open_store(create=True)
    try:
        pending = (loop.store.status, loop.store.open_report.get("export_recovery"))
        loop.tick()
        still = (loop.store.status, _redirect["db"].exists())
        blocker.rename(_redirect["events"] / "moved-aside")
        loop.tick()
        after = loop.store.status
    finally:
        if loop.store is not None:
            loop.store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events once the blocker moved: "
        "the refused promotion was never retried")
    assert pending[0] == "absent" and len(pending[1]["promotion_errors"]) == 1, pending
    assert still == ("absent", False), still
    assert after == "ok"
    assert result["status"] == "exported" and result["db_retired_to"], result
    assert result["roots"] == [str(_redirect["otel"] / "exports" / stamp)], (
        "roots must name only what this export actually promoted", result)


def test_two_concurrent_exports_the_second_is_refused_while_the_first_holds_the_lock(
        _redirect):
    """F3 of critic-opus, round 2: two `--export-spool` runs overlapping,
    OUTSIDE `.maintenance.lock`. The second is played at the worst instant —
    inside the first's `before_retire`, i.e. between its preparation and its
    retire. On b3d1655c it retired the database under its own stamp and
    promoted its export; the first then found no database, kept its
    preparation and told the operator to rename a file that no longer existed.
    Now the retire and the promotion run under the lock (and so does the
    cleanup that opens every export): the second finds it held, retires
    nothing, says re-run; the first completes; every event counts once."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    second_result: dict = {}
    first = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(first, srcs)
        second = event_store.open_store(create=False)
        try:
            def run_the_second() -> None:
                second_result.update(
                    second.export_spool(now=_FROZEN_NOW + timedelta(seconds=1)))
                return None

            result = first.export_spool(now=_FROZEN_NOW, before_retire=run_the_second)
        finally:
            second.close()
    finally:
        first.close()
    assert second_result["status"] != "exported", second_result
    assert second_result["db_retired_to"] is None, second_result
    assert "nothing retired" in second_result["reason"], second_result
    assert "re-run" in second_result["reason"], second_result
    assert result["status"] == "exported" and result["reason"] is None, result

    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports.partial").exists(), f"a preparation was left under {root}"


def test_two_concurrent_exports_the_second_is_void_once_the_database_is_gone(_redirect):
    """The other overlap: the second export reaches its retire AFTER the first
    finished (it opened the database before, and read it through its
    still-open connection). There is no database left to retire. On b3d1655c
    that fell into the generic "could not be retired" branch — rename the
    database "to exactly <db>.exported-<stamp> by hand" — about a file that no
    longer exists, and it KEPT a complete second copy in preparation.
    Following that advice with the only database left (the first's retired
    one) made the proof exist, and the next open promoted the copy on top of
    the first export: 12 rows for 6. Now the export is VOID: its preparation
    is removed and the reason says to rename nothing — so even the old
    advice, followed, finds nothing to promote."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    second_stamp = event_store._export_stamp(_FROZEN_NOW + timedelta(seconds=1))
    first = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(first, srcs)
        second = event_store.open_store(create=False)
        try:
            result = first.export_spool(now=_FROZEN_NOW)
            voided = second.export_spool(now=_FROZEN_NOW + timedelta(seconds=1))
        finally:
            second.close()
    finally:
        first.close()
    assert result["status"] == "exported", result

    Path(result["db_retired_to"]).rename(
        _redirect["db"].with_name(f"events.db.exported-{second_stamp}"))
    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events: the second export's "
        "preparation survived and was promoted on top of the first")
    assert voided["status"] == "void", voided
    assert "rename nothing by hand" in voided["reason"].lower(), voided
    assert voided["staged"] == [] and voided["db_retired_to"] is None, voided


def test_export_spool_fsyncs_every_preparation_directory_before_the_retire(
        _redirect, monkeypatch):
    """F5 of critic-opus, round 2: `_publish_lines` fsyncs each FILE, but the
    directory ENTRIES naming them — the staging, its `digest/`,
    `exports.partial/`, the spool root — were fsynced by nobody before the
    commit point. A power cut right after the retire could leave a retired
    database and a preparation whose entries never reached the disk. Now every
    one of them is fsynced BEFORE the retire, and after each promotion the
    spool root is fsynced too (`exports/` may have just been created in it)."""
    events_dir, otel_dir = _redirect["events"], _redirect["otel"]
    stamp = event_store._export_stamp(_FROZEN_NOW)
    calls: list[tuple] = []
    real_replace = event_store._replace_with_retry

    def replace(src, dst):
        calls.append(("replace", Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(event_store, "_fsync_dir", lambda path: calls.append(("fsync", Path(path))))
    monkeypatch.setattr(event_store, "_replace_with_retry", replace)
    store = event_store.open_store(create=True)
    try:
        _insert_export_fixture(store, (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl"))
        store._conn.execute("INSERT INTO digests (month, dimension, key, count) "
                            "VALUES ('2026-06', 'total', '', 5)")
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert result["status"] == "exported", result
    retire = next(i for i, call in enumerate(calls)
                  if call[0] == "replace" and call[1] == _redirect["db"])
    before = {call[1] for call in calls[:retire] if call[0] == "fsync"}
    expected = {events_dir / "exports.partial" / stamp,
                events_dir / "exports.partial" / stamp / "digest",
                otel_dir / "exports.partial" / stamp,
                events_dir / "exports.partial", otel_dir / "exports.partial",
                events_dir, otel_dir}
    assert expected <= before, (
        "not fsynced before the retire: " + ", ".join(sorted(map(str, expected - before))))
    after = calls[retire + 1:]
    for root in (events_dir, otel_dir):
        promotion = next(i for i, call in enumerate(after)
                         if call[0] == "replace" and call[2] == root / "exports" / stamp)
        assert ("fsync", root) in after[promotion + 1:], f"{root} not fsynced after promotion"


def test_export_spool_removes_unproven_preparations_before_writing_and_names_them(
        _redirect, tmp_path):
    """F6 of critic-opus / F3+F4 of critic-fable, round 2: a preparation an
    interrupted or refused export left behind was never removed — one full
    copy of the store per failed attempt — and one that is a SYMLINK made
    `rmtree` fail forever, so "re-running is safe" was false. Before writing,
    under `.maintenance.lock`, every entry of `exports.partial/` that no
    retired database proves is removed — a symlink UNLINKED, never followed —
    and named in `unproven_stagings_removed`. A PROVEN one (its
    `<db>.exported-<name>` exists) belongs to the recovery and is left alone."""
    events_partial = _redirect["events"] / "exports.partial"
    otel_partial = _redirect["otel"] / "exports.partial"
    store = event_store.open_store(create=True)   # created BEFORE the proof exists
    try:
        _insert_export_fixture(store, (f"a/{_TODAY}.claude.1.jsonl",), per_file=2)
        unproven = [events_partial / "20260101T000000Z", otel_partial / "20260101T000000Z"]
        for staging in unproven:
            staging.mkdir(parents=True)
            (staging / "x.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "keep.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
        linked = events_partial / "20260101T000001Z"
        try:
            linked.symlink_to(elsewhere, target_is_directory=True)
        except OSError as exc:  # pragma: no cover - Windows without the privilege
            pytest.skip(f"cannot create a symlink here: {exc}")
        proven = events_partial / "20260101T000002Z"
        proven.mkdir()
        (proven / "y.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
        _redirect["db"].with_name("events.db.exported-20260101T000002Z").write_bytes(b"")
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    assert result["status"] == "exported", result
    assert sorted(result["unproven_stagings_removed"]) == sorted(
        map(str, [*unproven, linked])), result
    assert not linked.exists() and not linked.is_symlink(), "the symlink was left"
    assert (elsewhere / "keep.jsonl").exists(), "the symlink was FOLLOWED"
    assert (proven / "y.jsonl").exists(), "a proven preparation was removed"
    assert not any(path.exists() for path in unproven)


def test_an_export_whose_preparation_was_cleaned_under_it_retires_nothing(
        _redirect, monkeypatch):
    """The HAZARD the orphan cleanup brings, closed in the same pass: the
    cleanup runs under `.maintenance.lock`, the preparation does not — so a
    second export OPENING while this one is still writing sees this
    preparation as unproven (no retired database yet) and removes it. The
    writer recreates its directory for the next file and would then retire
    the database with only PART of its rows prepared: rows lost. Under the
    lock, before the retire, every file this export wrote is checked; one
    missing ⇒ nothing retired, the rest of the preparation removed."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    real_publish = event_store._publish_lines
    published: list[Path] = []

    def publish_then_a_rival_cleans(target, lines):
        real_publish(target, lines)
        published.append(Path(target))
        if len(published) == 1:   # another export opens right now
            locked, _report = event_store._under_maintenance_lock(
                lambda: event_store._remove_unproven_stagings(
                    _redirect["db"], [_redirect["events"], _redirect["otel"]]))
            assert locked

    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        monkeypatch.setattr(event_store, "_publish_lines", publish_then_a_rival_cleans)
        result = store.export_spool(now=_FROZEN_NOW)
    finally:
        store.close()
    monkeypatch.setattr(event_store, "_publish_lines", real_publish)
    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events: the export retired the "
        "database over a preparation another run had emptied")
    assert result["db_retired_to"] is None and "vanished" in result["reason"], result
    assert result["staged"] == [], result


# --- T-00000769, round-3 pass (S-00002562 → decision S-00002563) -------------

def test_an_absent_store_names_the_proven_exports_waiting_for_promotion(_redirect):
    """Round 3, both critics: `recovery_pending` was INVISIBLE — a reader
    (`ingestion_status`, hence `--status` and the Couverture view) opens with
    `create=False` and only said "the daemon has not ingested anything yet",
    while the daemon, blocked, ingested nothing at all. Now an absent store
    whose spool holds PROVEN preparations (a real directory, and its
    `<db>.exported-<name>` exists) says they wait, that the daemon ingests
    nothing until they are promoted, and which `exports/<stamp>/` blocks. An
    unproven preparation or a symlink is not named: neither is waiting."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    events_dir = _redirect["events"]
    stamp = "20260729T120000Z"
    proven = events_dir / "exports.partial" / stamp
    proven.mkdir(parents=True)
    (proven / "x.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
    db.with_name(f"events.db.exported-{stamp}").write_bytes(b"")
    unproven = events_dir / "exports.partial" / "20260729T120001Z"
    unproven.mkdir()
    blocker = events_dir / "exports" / stamp
    blocker.mkdir(parents=True)

    reason = event_store.ingestion_status()["reason"] or ""
    assert str(proven) in reason, reason
    assert "ingests NOTHING until they are promoted" in reason, reason
    assert str(blocker) in reason, reason
    assert str(unproven) not in reason, reason
    assert [str(p) for p in event_store._proven_stagings(db)] == [str(proven)]


def test_a_void_export_never_removes_a_preparation_a_retired_database_proves(_redirect):
    """Round 3, critic-opus: two exports sharing a stamp share a preparation
    directory and a proof name. Since the final pass the stamp carries the pid
    (`_export_stamp`), so only two exports of the SAME PROCESS in the same
    second can still share one — a library caller, a test. When the first
    retires the database under `<db>.exported-<stamp>`, the second finds no
    database — void — and must not remove `exports.partial/<stamp>/`: the
    FIRST export's only copy of the rows. Played by retiring the database
    under that exact name from the export's own `before_retire`. A
    preparation that proof covers is never removed: it is LEFT, said so, and
    the next open promotes it — every row is there."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    stamp = event_store._export_stamp(_FROZEN_NOW)
    proof = _redirect["db"].with_name(f"events.db.exported-{stamp}")
    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)

        def the_other_export_retires_first() -> None:
            _redirect["db"].rename(proof)
            return None

        result = store.export_spool(now=_FROZEN_NOW,
                                    before_retire=the_other_export_retires_first)
    finally:
        store.close()
    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events: a void export removed "
        "the preparation a retired database proves")
    assert result["status"] == "void", result
    assert f"preparation LEFT: {proof} proves it" in result["reason"], result


# --- T-00000769, final pass (S-00002575/S-00002577 → decision S-00002576) ----

def test_the_export_stamp_is_unique_per_process():
    """S-00002576 reverses S-00002563: the stamp is `<second>-p<pid>`. Two
    `--export-spool` processes in the same second no longer share a
    preparation directory, a proof name or a final directory."""
    assert event_store._export_stamp(_FROZEN_NOW, pid=1111) == "20260729T120000Z-p1111"
    assert (event_store._export_stamp(_FROZEN_NOW)
            == f"20260729T120000Z-p{os.getpid()}")
    assert (event_store._export_stamp(_FROZEN_NOW, pid=1111)
            != event_store._export_stamp(_FROZEN_NOW, pid=2222))


def test_a_void_export_removes_its_own_preparation_when_another_export_retired_the_db(
        _redirect):
    """The `void` case as it happens between two PROCESSES: the other export
    retired the database under ITS stamp. This export's preparation is proved
    by nothing — no row lives only there (they are in the other export) — so
    it is removed, and never LEFT to block the recovery."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    own = event_store._export_stamp(_FROZEN_NOW)
    other = event_store._export_stamp(_FROZEN_NOW, pid=os.getpid() + 1)
    store = event_store.open_store(create=True)
    try:
        _insert_export_fixture(store, srcs)

        def another_process_retires_first() -> None:
            _redirect["db"].rename(_redirect["db"].with_name(f"events.db.exported-{other}"))
            return None

        result = store.export_spool(now=_FROZEN_NOW,
                                    before_retire=another_process_retires_first)
    finally:
        store.close()
    assert result["status"] == "void", result
    assert "preparation removed" in result["reason"], result
    assert "preparation LEFT" not in result["reason"], result
    assert result["staged"] == [], result
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports.partial" / own).exists(), root


class _PausingCursor:
    """A cursor that, on its `pause_at`-th row, signals `reached`, waits for
    `release` (bounded), then raises `error` if one is given — a second
    export frozen mid-preparation while the first one runs."""

    def __init__(self, cursor, pause_at, reached, release, error=None):
        self._cursor, self._pause_at = cursor, pause_at
        self._reached, self._release, self._error = reached, release, error

    def __iter__(self):
        for n, row in enumerate(self._cursor):
            if n == self._pause_at:
                self._reached.set()
                assert self._release.wait(20), "the first export never released the second"
                if self._error is not None:
                    raise self._error
            yield row


def _run_second_export_in_a_thread(pause_at, error, outcome):
    """A SECOND `--export-spool` process, played by a thread with its own
    connection and its own pid in the stamp (`_export_stamp` is patched per
    thread by the caller). Returns (thread, reached, release)."""
    import threading

    reached, release = threading.Event(), threading.Event()

    def run() -> None:
        second = event_store.open_store(create=False)
        try:
            real = second._conn

            class _Conn:
                def execute(self, sql, *args):
                    cursor = real.execute(sql, *args)
                    if sql.startswith(_EXPORT_ROWS_SQL):
                        return _PausingCursor(cursor, pause_at, reached, release, error)
                    return cursor

                def __getattr__(self, name):
                    return getattr(real, name)

            second._conn = _Conn()
            try:
                outcome.update(second.export_spool(now=_FROZEN_NOW))
            finally:
                second._conn = real
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            outcome["raised"] = repr(exc)
            reached.set()
        finally:
            second.close()

    thread = threading.Thread(target=run, name="t769-second-export", daemon=True)
    return thread, reached, release


def _patch_stamp_per_thread(monkeypatch):
    import threading

    real = getattr(event_store, "_export_stamp", None)

    def per_thread(now, pid=None):
        if real is None:   # the code under test predates the per-process stamp
            return now.strftime("%Y%m%dT%H%M%SZ")
        fake = 2222 if threading.current_thread().name == "t769-second-export" else 1111
        return real(now, pid=fake if pid is None else pid)

    monkeypatch.setattr(event_store, "_export_stamp", per_thread, raising=False)


def test_two_exports_in_the_same_second_a_failing_second_never_empties_the_first(
        _redirect, monkeypatch):
    """F1 (a) of the final binôme (S-00002575), measured 0/6: two processes in
    the SAME second shared `exports.partial/<stamp>/`. The second, interrupted
    by a read error, cleans its preparation up OUTSIDE the lock — while the
    first, inside its commit phase, has not retired yet (no proof) — and so
    removes the FIRST export's whole preparation; the first then retires the
    database and has nothing to promote: 0 rows, rc 0. With a stamp per
    process the two never share a directory: 6/6."""
    _patch_stamp_per_thread(monkeypatch)
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        outcome: dict = {}
        thread, reached, release = _run_second_export_in_a_thread(
            pause_at=4, error=sqlite3.OperationalError("disk I/O error (simulated)"),
            outcome=outcome)
        thread.start()
        assert reached.wait(20), "the second export never reached its pause"

        def let_the_second_fail_now() -> None:
            release.set()
            thread.join(20)
            return None

        result = store.export_spool(now=_FROZEN_NOW, before_retire=let_the_second_fail_now)
    finally:
        store.close()
    store = event_store.open_store(create=True)
    try:
        store.ingest_once(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored == 6, (
        f"{_count(_redirect['db'])} rows for {stored} events: the second export's "
        "clean-up removed the first export's preparation", result, outcome)
    assert result["status"] == "exported", result
    assert outcome.get("status") != "exported", outcome


def test_two_exports_in_the_same_second_a_void_second_never_blocks_the_daemon(
        _redirect, monkeypatch):
    """F1 (b) of the final binôme, a regression of the round-3 pass: the
    second export (same second, same stamp) prepared AFTER the first had
    retired and promoted, found no database — void — and its partial
    preparation was LEFT because the FIRST export's proof carries the same
    name. The next open then tried to promote it onto the first's complete
    `exports/<stamp>/`, failed, and kept the store absent: the daemon ingested
    nothing, and the remedy had the operator move the COMPLETE export aside.
    With a stamp per process nothing proves the second preparation: it is
    removed, and the daemon opens `ok` with every row."""
    _patch_stamp_per_thread(monkeypatch)
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    store = event_store.open_store(create=True)
    try:
        stored = _insert_export_fixture(store, srcs)
        outcome: dict = {}
        thread, reached, release = _run_second_export_in_a_thread(
            pause_at=0, error=None, outcome=outcome)
        thread.start()
        assert reached.wait(20), "the second export never reached its pause"
        result = store.export_spool(now=_FROZEN_NOW)   # the first, all the way
    finally:
        store.close()
    release.set()
    thread.join(20)
    reopened = event_store.open_store(create=True)
    try:
        status, why = reopened.status, reopened.reason
        reopened.ingest_once(now=_FROZEN_NOW)
    finally:
        reopened.close()
    assert status == "ok", (why, result, outcome)
    assert _count(_redirect["db"]) == stored == 6
    assert result["status"] == "exported", result
    assert outcome.get("status") == "void", outcome


def test_export_spool_names_a_preparation_that_vanished_after_the_last_check(_redirect):
    """Defence (S-00002576): once the database is retired, a root whose
    preparation vanished after the pre-retire check (another process, a hand
    `rm`) has its rows ONLY in the retired database. Skipping it as "nothing
    prepared" said exported and clean; it is now named in the result."""
    srcs = (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl")
    stamp = event_store._export_stamp(_FROZEN_NOW)
    store = event_store.open_store(create=True)
    try:
        _insert_export_fixture(store, srcs)

        def something_removes_one_root() -> None:
            shutil.rmtree(_redirect["otel"] / "exports.partial" / stamp)
            return None

        result = store.export_spool(now=_FROZEN_NOW, before_retire=something_removes_one_root)
    finally:
        store.close()
    assert result["status"] == "exported", result
    reason = result["reason"] or ""
    assert f"its rows live only in {result['db_retired_to']}" in reason, result
    assert str(_redirect["otel"] / "exports.partial" / stamp) in reason, result
    assert result["roots"] == [str(_redirect["events"] / "exports" / stamp)], result


def test_export_spool_fsyncs_the_preparation_before_the_last_daemon_probe(
        _redirect, monkeypatch):
    """Round 3, critic-opus: the fsync of the preparation ran AFTER the last
    daemon probe, so the slowest step of the commit phase sat between the
    probe and the retire it is meant to guard. Now every preparation
    directory is fsynced first; the probe is the last thing before the
    connection closes and the database is retired."""
    events_dir, otel_dir = _redirect["events"], _redirect["otel"]
    stamp = event_store._export_stamp(_FROZEN_NOW)
    calls: list[tuple] = []
    real_replace = event_store._replace_with_retry

    def replace(src, dst):
        calls.append(("replace", Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(event_store, "_fsync_dir", lambda path: calls.append(("fsync", Path(path))))
    monkeypatch.setattr(event_store, "_replace_with_retry", replace)

    def probe() -> None:
        calls.append(("probe",))
        return None

    store = event_store.open_store(create=True)
    try:
        _insert_export_fixture(store, (f"a/{_TODAY}.claude.1.jsonl", f"b/{_TODAY}.1.jsonl"))
        result = store.export_spool(now=_FROZEN_NOW, before_retire=probe)
    finally:
        store.close()
    assert result["status"] == "exported", result
    probed = calls.index(("probe",))
    retire = next(i for i, call in enumerate(calls)
                  if call[0] == "replace" and call[1] == _redirect["db"])
    preparation = {events_dir / "exports.partial" / stamp, otel_dir / "exports.partial" / stamp,
                   events_dir / "exports.partial", otel_dir / "exports.partial"}
    fsynced_before = {call[1] for call in calls[:probed] if call[0] == "fsync"}
    between = [call for call in calls[probed + 1:retire] if call[0] == "fsync"]
    assert preparation <= fsynced_before, (
        "fsynced after the last daemon probe: "
        + ", ".join(sorted(map(str, preparation - fsynced_before))))
    assert between == [], f"work between the last probe and the retire: {between}"


def test_iter_canal_b_bodies_yields_nothing_in_every_non_ok_status(_redirect):
    """The same degraded posture as its eager sibling, expressed the only way a
    generator can express it: an empty iteration, never a raise. The sibling
    carries `status`/`reason` in its payload; here the CALLER has already read
    `store.status` before it iterates, which is why an empty run is honest and
    not a silent zero."""
    store = event_store.open_store(create=False)   # absent
    try:
        assert store.status == "absent"
        assert list(store.iter_canal_b_bodies()) == []
    finally:
        store.close()


def test_two_roots_keep_two_intact_databases(_redirect, tmp_path, monkeypatch):
    """Spec §A.4's exit criterion, on the data side: two provisioned repos on
    one machine each keep their OWN store. Nothing here is shared but the port,
    and the port is not what the store is keyed on."""
    own_a = _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=own_a)])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()

    second = tmp_path / "second"
    (second / "events").mkdir(parents=True, exist_ok=True)
    (second / "otel").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(second / "events"))
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(second / "otel"))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(second / "project.json"))
    (second / "project.json").write_text(json.dumps({"project_id": _OTHER_ID}),
                                         encoding="utf-8", newline="\n")
    _write_otel_spool(second / "otel", "2026-07-29.1.jsonl", [
        _otel_envelope(project_id=_OTHER_ID)])
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
        assert store.project == _OTHER_ID
    finally:
        store.close()

    assert _count(_redirect["db"]) == 1
    assert _count(second / "local" / "events.db") == 1
    assert [p for p, _b in _project_bodies(_redirect["db"])] == [own_a]
    assert [p for p, _b in _project_bodies(second / "local" / "events.db")] == [_OTHER_ID]


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_status_and_ingest_once(_redirect, capsys):
    _write_spool(_redirect["events"], "2026-07-29.claude.161.jsonl", [_rec(task="T-1")])
    assert event_store.main(["--ingest-once"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["tick"]["rows_inserted"] == 1
    # V1-c: the two one-time passes run at OPEN, so an operator diagnosing
    # attribution gets their counts next to the tick's own (must-fix M2 — a
    # backfill has to be journalled to be re-runnable without fear). T-00000769
    # adds the third one-time step of an open: the recovery of a retired export.
    assert set(printed["open"]) == {"relabel", "backfill", "export_recovery"}
    assert event_store.main(["--status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["source"] == "sqlite"
    assert status["rows_max_id"] == 1


def test_status_rend_compte_age_octets_bruts(_redirect, capsys):
    """T-00000612 — `--status` rend AUSSI, pour `events.db`, le compte
    d'événements, l'âge de la plus ancienne ligne et les octets BRUTS du fichier,
    en LECTURE SEULE.

    Store temporaire réel, trois événements insérés par l'API vivante. Le compte
    est relu INDÉPENDAMMENT (`SELECT COUNT(*)` par sa propre connexion), l'âge est
    calé sur l'horodatage le plus ancien inséré, les octets sur `os.path.getsize`.

    Les mutations qui doivent ROUGIR ce témoin — la seule preuve que l'instrument
    MESURE et ne récite pas une constante :
      * un compte qui diverge (`COUNT(*) - 1`, un `LIMIT`) casse `event_count == 3` ;
      * une conversion d'unité (`bytes / 1024`) casse `bytes == os.path.getsize`.
    Et `--status` ne doit MODIFIER ni les octets ni la mtime du fichier."""
    directory = _redirect["events"]
    db = _redirect["db"]
    oldest_ts = "2026-07-29T08:00:00Z"
    _write_spool(directory, f"{_TODAY}.claude.612.jsonl", [
        _rec(ts=oldest_ts, task="T-1"),
        _rec(ts="2026-07-29T09:30:00Z", task="T-2"),
        _rec(ts="2026-07-29T11:00:00Z", task="T-3"),
    ])
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once(now=_FROZEN_NOW)["rows_inserted"] == 3
        # `-wal` rendu SÉPARÉMENT tant que l'écrivain le tient ouvert : 3 lignes
        # sont très en deçà de l'autocheckpoint (1000 pages), donc le sidecar est
        # bien sur le disque, et la lecture `mode=ro` passe DEVANT l'écrivain.
        wal = Path(str(db) + "-wal")
        assert wal.exists()
        open_footprint = event_store.store_footprint(now=_FROZEN_NOW)
        assert open_footprint["wal_bytes"] == os.path.getsize(wal)
        assert open_footprint["event_count"] == 3
    finally:
        store.close()

    # COMPTE — relu INDÉPENDAMMENT, pas via l'instrument sous test.
    independent_count = _count(db)
    assert independent_count == 3

    now = datetime.fromisoformat("2026-07-29T17:00:00+00:00")  # 08:00 -> 17:00
    footprint = event_store.store_footprint(now=now)

    assert footprint["present"] is True
    # (1) COMPTE : égale SELECT COUNT(*). Un COUNT(*)-1 ou un LIMIT rougit ici.
    assert footprint["event_count"] == independent_count == 3
    # (2) LA PLUS ANCIENNE : l'horodatage BRUT verbatim (un MAX(ts) le renverse).
    assert footprint["oldest_ts"] == oldest_ts
    expected_age = (now - datetime.fromisoformat(
        oldest_ts.replace("Z", "+00:00"))).total_seconds()
    assert expected_age == 9 * 3600  # 9 h, sans extrapolation
    assert footprint["oldest_age_seconds"] == pytest.approx(expected_age)
    # (3) OCTETS : os.path.getsize brut, jamais converti. Un `/ 1024` rougit ici.
    raw_bytes = os.path.getsize(db)
    assert raw_bytes > 1024  # pour qu'une division octets->Kio donne un AUTRE entier
    assert footprint["bytes"] == raw_bytes

    # `--status` expose l'empreinte SANS modifier le fichier (octets + mtime).
    size_before = os.path.getsize(db)
    mtime_before = os.stat(db).st_mtime_ns
    assert event_store.main(["--status"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert os.path.getsize(db) == size_before
    assert os.stat(db).st_mtime_ns == mtime_before
    # Ajouté sous SA PROPRE clé ; la charge existante reste présente et non réordonnée.
    assert "store_footprint" in printed
    assert list(printed)[:2] == ["source", "schema_version"]
    assert printed["store_footprint"]["event_count"] == 3
    assert printed["store_footprint"]["bytes"] == raw_bytes
    assert printed["store_footprint"]["oldest_ts"] == oldest_ts


_WAL_WRITER_CHILD = textwrap.dedent(
    """
    import os, sqlite3, sys
    db = sys.argv[1]
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")  # jamais de checkpoint automatique
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts TEXT, body TEXT)")
    conn.execute("BEGIN")
    for i in range(20000):
        conn.execute("INSERT INTO events (ts, body) VALUES (?, ?)",
                     ("2026-07-29T08:00:00Z", "x" * 180))
    conn.execute("COMMIT")
    sys.stdout.write("done")
    sys.stdout.flush()
    os._exit(0)  # kill dur : ni close ni checkpoint, le -wal reste sur le disque
    """
)


def test_status_prend_l_empreinte_AVANT_ingestion_status_wal_orphelin(
        _redirect, capsys, tmp_path):
    """T-00000612 + correctif binôme PORTE 3 (C3) — `--status` prend
    `store_footprint` (mode=ro) AVANT `ingestion_status`, qui ouvre le store en
    ÉCRITURE et, à la fermeture de sa connexion (la dernière : l'écrivain est
    mort), CHECKPOINTE puis SUPPRIME le WAL. Un écrivain TUÉ (`os._exit`) laisse un
    `-wal` orphelin non vide ; `store_footprint` dans la charge de `--status` le
    rend TEL QU'AVANT — mesuré par le critique : 3 712 152 o si l'ordre est bon,
    None si `store_footprint` passait APRÈS `ingestion_status`."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "wal_writer.py"
    script.write_text(_WAL_WRITER_CHILD, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(db)],
        env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdout.decode() == "done", proc.stderr.decode("utf-8", "replace")
    wal = Path(str(db) + "-wal")
    wal_size = wal.stat().st_size
    assert wal_size > 0, "l'écrivain tué n'a pas laissé de WAL orphelin non vide"

    # store_footprint SEUL (mode=ro) lit la taille du WAL sur le disque sans le
    # toucher — pas de checkpoint, le sidecar reste.
    fp = event_store.store_footprint(now=_FROZEN_NOW)
    assert fp["wal_bytes"] == wal_size
    assert wal.exists(), "store_footprint (mode=ro) a modifié le WAL"

    # `--status` : l'empreinte est prise AVANT ingestion_status, donc wal_bytes
    # survit à l'ouverture read-write qui suit.
    assert event_store.main(["--status"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["store_footprint"]["wal_bytes"] == wal_size, (
        "wal_bytes perdu : store_footprint pris APRÈS ingestion_status, qui a "
        "checkpointé/supprimé le WAL orphelin")


def test_cli_without_a_flag_prints_help_and_fails(_redirect, capsys):
    assert event_store.main([]) == 1
    assert "export-spool" in capsys.readouterr().out


# --- T-00000769: `--export-spool` under a live daemon, and its exit codes ----

def _cli_store_with_rows(_redirect, n: int = 3) -> int:
    """A store holding `n` ingested canal-A rows whose spool file is gone —
    exactly what `--export-spool` exists to re-emit."""
    path = _write_spool(_redirect["events"], f"{_TODAY}.claude.170.jsonl",
                        [_rec(task=f"T-{i}") for i in range(n)])
    _touch_old(path, now=_FROZEN_NOW)
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once(now=_FROZEN_NOW)["deleted"] == 1
    finally:
        store.close()
    assert _count(_redirect["db"]) == n
    return n


def test_cli_export_spool_refuses_while_the_dashboard_daemon_is_alive(
        _redirect, monkeypatch, capsys):
    """T1 of critic-opus (S-00002502), CRITICAL although pre-existing: an
    export under a LIVE daemon loses the history it exists to keep — the
    daemon ingests `exports/*/*.jsonl` and deletes the files, its open handle
    leaves the WAL under the old name at the rename, and it re-creates an
    empty store. So the CLI refuses, rc 2, BEFORE writing anything: not one
    file published (the re-check before the retire would refuse too, but only
    after preparing a whole export — and now removing it, so the directories
    alone no longer tell the two apart), no `exports/`, no `exports.partial/`,
    the database untouched."""
    stored = _cli_store_with_rows(_redirect)
    monkeypatch.setattr(event_store, "_dashboard_daemon_state", lambda: ("alive", 4242),
                        raising=False)
    published: list = []
    real_publish = event_store._publish_lines
    monkeypatch.setattr(event_store, "_publish_lines",
                        lambda target, lines: (published.append(target),
                                               real_publish(target, lines))[1])
    assert event_store.main(["--export-spool"]) == 2
    printed = json.loads(capsys.readouterr().out)
    assert published == [], f"prepared {len(published)} file(s) before refusing"
    assert printed["status"] == "refused", printed
    assert "daemon" in printed["reason"] and "--stop" in printed["reason"], printed
    assert _redirect["db"].exists() and _count(_redirect["db"]) == stored
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports").exists(), f"published under {root} while refusing"
        assert not (root / "exports.partial").exists(), (
            "prepared an export before refusing: the daemon was checked too late")


def test_cli_export_spool_rechecks_the_daemon_just_before_retiring(
        _redirect, monkeypatch, capsys):
    """A session starting DURING the export relaunches the daemon (SessionStart
    hook), so the first check is not enough: the state is read again just
    before the database is retired. Alive then ⇒ rc 2, nothing retired,
    nothing published, the prepared export named and REMOVED (S-00002537),
    and `roots`/`staged` say exactly that: nothing promoted, nothing left."""
    stored = _cli_store_with_rows(_redirect)
    answers = iter([("absent", None), ("alive", 4242)])
    monkeypatch.setattr(event_store, "_dashboard_daemon_state", lambda: next(answers),
                        raising=False)
    assert event_store.main(["--export-spool"]) == 2
    printed = json.loads(capsys.readouterr().out)
    assert next(answers, None) is None, "the daemon was not probed a second time"
    assert printed["status"] == "refused" and printed["db_retired_to"] is None, printed
    assert "daemon" in printed["reason"] and "exports.partial" in printed["reason"], printed
    assert "preparation removed" in printed["reason"], printed
    assert printed["roots"] == [] and printed["staged"] == [], printed
    assert _redirect["db"].exists() and _count(_redirect["db"]) == stored
    assert not (_redirect["events"] / "exports").exists()
    assert not (_redirect["events"] / "exports.partial").exists()


def test_cli_export_spool_fails_when_the_export_did_not_end_exported(_redirect, capsys):
    """rc 0 used to be printed whatever happened — a store that cannot be
    read, a failed read, a database that could not be retired. A rollback
    script chaining on the exit code would proceed on a non-export. (An ABSENT
    store stopped being such a case in S-00002537: see
    `test_cli_export_spool_on_an_absent_store_finishes_a_pending_promotion`.)"""
    store = event_store.open_store(create=True)
    store.connection.execute("PRAGMA user_version = 2")
    store.close()
    assert event_store.main(["--export-spool"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "schema_ahead"
    assert _redirect["db"].exists()


def test_cli_export_spool_a_failed_promotion_is_reported_and_the_next_start_recovers_it(
        _redirect, monkeypatch, capsys):
    """After the commit point (the retire), a promotion that fails is NOT a
    rollback — the database is gone by design — it is reported in `reason`
    with what happens next (the next daemon start promotes it), rc 1; and the
    next `open_store(create=True)` does exactly that."""
    stored = _cli_store_with_rows(_redirect)
    real_promote = getattr(event_store, "_promote_staged", None)

    def refuse(staging, final):
        raise OSError(errno.EACCES, "Permission denied (simulated)")

    monkeypatch.setattr(event_store, "_promote_staged", refuse, raising=False)
    assert event_store.main(["--export-spool"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "exported" and printed["db_retired_to"], printed
    assert "next daemon start promotes it" in (printed["reason"] or ""), printed
    assert not _redirect["db"].exists()
    assert list(_redirect["events"].glob("exports/*/*.jsonl")) == []

    monkeypatch.setattr(event_store, "_promote_staged", real_promote, raising=False)
    store = event_store.open_store(create=True)
    try:
        assert store.ingest_once(now=_FROZEN_NOW)["rows_inserted"] == stored
    finally:
        store.close()
    assert _count(_redirect["db"]) == stored


def test_dashboard_daemon_state_asks_the_daemon_module_and_is_unknown_on_any_error(
        _redirect, monkeypatch):
    """The probe's WIRING, without ever touching a real daemon: it loads
    `dashboard_daemon.py` through `_load_sibling` (lazily — the CLI path only)
    and returns that module's own `daemon_status` verdict for this project's
    root, with the lock's pid (T-00000769 round 3: the refusal prints it);
    any failure — load or probe — is `unknown`, never a raise."""
    assert _REAL_DAEMON_STATE is not None, "event_store._dashboard_daemon_state is gone"
    seen: list = []
    fake = types.SimpleNamespace(
        _project_root=lambda: _redirect["root"],
        daemon_status=lambda root: (seen.append(root), ("alive", {"pid": 1}))[1])
    monkeypatch.setattr(event_store, "_load_sibling",
                        lambda name, filename: (seen.append(filename), fake)[1])
    assert _REAL_DAEMON_STATE() == ("alive", 1)
    assert seen == ["dashboard_daemon.py", _redirect["root"]], seen

    def cannot_load(name, filename):
        raise ImportError("dashboard.py is broken (simulated)")

    monkeypatch.setattr(event_store, "_load_sibling", cannot_load)
    assert _REAL_DAEMON_STATE() == ("unknown", None)

    def probe_raises(root):
        raise OSError("lock unreadable (simulated)")

    fake.daemon_status = probe_raises
    monkeypatch.setattr(event_store, "_load_sibling", lambda name, filename: fake)
    assert _REAL_DAEMON_STATE() == ("unknown", None)


def test_dashboard_daemon_state_reports_a_live_pid_without_ping_as_unresponsive(
        _redirect, monkeypatch):
    """HIGH of both critics, round 2 (S-00002536): `daemon_status` answers
    `stale` when the pid is alive but the tokenised ping goes unanswered —
    a state a daemon can sit in while still holding the store — and the
    refusal only bit on `alive`. A `stale` whose pid is ALIVE is now
    `unresponsive`; a stale lock of a dead pid, or an unreadable lock, stays
    `stale`. ROUND 3 (S-00002562): an alive pid is not proof of the daemon —
    pids are recycled — so its command line must show `dashboard_daemon.py`:
    a live pid running something else is `stale` (a lock to delete, never a
    process to kill); a probe that cannot tell (Windows, no `ps`) keeps
    `unresponsive`. The daemon module and the probe are faked: no real
    daemon and no real process are touched."""
    lock = {"pid": 4242, "port": 1, "token": "t"}
    live_pids = {4242}
    runs_daemon: list = [True]
    probed_roots: list = []
    fake = types.SimpleNamespace(
        _project_root=lambda: _redirect["root"],
        daemon_status=lambda root: ("stale", lock),
        pid_alive=lambda pid: pid in live_pids)
    monkeypatch.setattr(event_store, "_load_sibling", lambda name, filename: fake)

    def probe(pid, root):
        probed_roots.append(root)
        return runs_daemon[0]

    monkeypatch.setattr(event_store, "_pid_runs_dashboard_daemon", probe, raising=False)
    assert _REAL_DAEMON_STATE() == ("unresponsive", 4242)
    assert probed_roots == [_redirect["root"]], "the probe was not given THIS project's root"
    runs_daemon[0] = False            # the pid was recycled by another program
    assert _REAL_DAEMON_STATE() == ("stale", 4242)
    runs_daemon[0] = None             # cannot tell: fail closed
    assert _REAL_DAEMON_STATE() == ("unresponsive", 4242)
    live_pids.clear()
    assert _REAL_DAEMON_STATE() == ("stale", 4242)
    fake.daemon_status = lambda root: ("stale", None)
    assert _REAL_DAEMON_STATE() == ("stale", None)


def test_pid_runs_dashboard_daemon_reads_the_command_line_and_is_none_where_it_cannot(
        monkeypatch, tmp_path):
    """The identity probe itself. Round 3: `ps -p <pid> -o command=` must show
    `dashboard_daemon.py`. FINAL PASS (F2 of critic-opus, T1 of critic-fable,
    S-00002576): an EMPTY answer — `ps` refused, or the pid gone between two
    probes — and a non-zero exit with a stderr are `None` (cannot tell ⇒ fail
    closed), no longer `False` (⇒ `stale` ⇒ export under a live daemon). And
    `True` needs BOTH `dashboard_daemon.py` AND `--root <THIS project root>`:
    another project's daemon that inherited the pid is `False`; a daemon line
    whose root cannot be read (no `--root`, truncated, unresolvable) is `None`.
    `None` also on Windows (no `ps`) and when `ps` is missing — never a raise.
    `subprocess.run` is faked: no process is inspected."""
    root = tmp_path / "my project"          # a space: the root is the line's tail
    root.mkdir()
    other = tmp_path / "other project"
    other.mkdir()
    calls: list = []
    answer: list = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        returncode, stdout, stderr = answer[0]
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(event_store.subprocess, "run", fake_run)
    probe = event_store._pid_runs_dashboard_daemon
    daemon_line = "/usr/bin/python3 /repo/.agents/bin/dashboard_daemon.py --daemon --root "

    answer[:] = [(0, f"{daemon_line}{root}\n", "")]
    assert probe(4242, root) is True
    assert calls[0] == ["ps", "-ww", "-p", "4242", "-o", "command="], calls
    answer[:] = [(0, f"{daemon_line}{other}\n", "")]
    assert probe(4242, root) is False, "another project's daemon holds the pid"
    answer[:] = [(0, "/usr/bin/python3 /repo/.agents/bin/dashboard_daemon.py --daemon\n", "")]
    assert probe(4242, root) is None, "a daemon line without --root cannot be told apart"
    answer[:] = [(0, f"{daemon_line}{tmp_path / 'trunc'}\n", "")]
    assert probe(4242, root) is None, "an unresolvable --root cannot be told apart"
    answer[:] = [(0, "vim notes.txt\n", "")]
    assert probe(4242, root) is False
    answer[:] = [(1, "", "")]                              # the pid vanished
    assert probe(4242, root) is None
    answer[:] = [(1, "", "ps: operation not permitted\n")]  # ps refused
    assert probe(4242, root) is None
    answer[:] = [(1, f"{daemon_line}{other}\n", "ps: partial read\n")]
    assert probe(4242, root) is None, "a failing ps is never read as an answer"

    def no_ps(argv, **kwargs):
        raise FileNotFoundError("ps")

    monkeypatch.setattr(event_store.subprocess, "run", no_ps)
    assert probe(4242, root) is None
    monkeypatch.setattr(event_store.subprocess, "run", fake_run)
    monkeypatch.setattr(event_store, "_IS_WINDOWS", True)
    calls.clear()
    assert probe(4242, root) is None
    assert calls == [], "ps was run on Windows"


def test_the_refusal_remedy_on_windows_does_not_tell_to_run_ps(monkeypatch):
    """T3 of critic-fable (final): Windows has no `ps`, so the remedy printed
    there must name what exists there — `tasklist /FI "PID eq <pid>"` or the
    Task Manager — with the same safe order: end the pid only if it IS this
    project's daemon, otherwise delete the stale lock, never kill another
    process."""
    monkeypatch.setattr(event_store, "_IS_WINDOWS", True, raising=False)
    reason = event_store._daemon_refusal_reason("unresponsive", 4242)
    assert 'tasklist /FI "PID eq 4242"' in reason, reason
    assert "Task Manager" in reason, reason
    assert "ps -p" not in reason, reason
    assert "never kill a process that is not the daemon" in reason, reason
    monkeypatch.setattr(event_store, "_IS_WINDOWS", False)
    posix = event_store._daemon_refusal_reason("unresponsive", 4242)
    assert "ps -p 4242 -o command=" in posix and "tasklist" not in posix, posix
    # The SAFE ORDER, on both platforms — the same one the doc must hold:
    # stop; if not-running, read the pid's command line; end it only if it IS
    # this project's daemon; otherwise the pid was recycled: delete the lock.
    for text in (reason, posix):
        steps = ["dashboard_daemon.py --stop", "not-running", "IS this project's daemon",
                 "end pid 4242", "the pid was recycled: delete .agents/state/local/dashboard.lock",
                 "never delete the lock of a live daemon"]
        positions = [text.find(step) for step in steps]
        assert -1 not in positions and positions == sorted(positions), (
            dict(zip(steps, positions)))


# T-00001065, pilot decision S-00003418 (Q2 = A): MARK, never loosen. The module
# doc lives under `docs/modules/`, frozen by `keep: docs/modules/` in
# `.template-exclude`: it does not travel. In an adopting tree (kit marker absent,
# `strip:`) this case is SKIPPED with its reason; in the kit, full force.
# `KIT_MARKER` is RELATIVE: never tested without the repo root in front of it.
# `build_index` goes through this file's own `_load`, under a name of its own.
_KIT_ONLY_MODULE_DOC = pytest.mark.skipif(
    not (HERE.parent.parent / _load("build_index_t1065_event_store", "build_index.py").KIT_MARKER).is_file(),
    reason="kit-only: reads docs/modules/event_store.md, frozen by `keep: docs/modules/` "
           "(.template-exclude) — it does not travel to an adopting project (T-00001065, S-00003418)",
)


@_KIT_ONLY_MODULE_DOC
def test_the_documented_refusal_remedy_is_complete_and_in_the_safe_order():
    """F3 of critic-opus / T3 of critic-fable (final): `docs/modules/event_store.md`
    told the operator to DELETE the lock when `--stop` answers not-running —
    without the branch "if that pid IS this project's daemon, end it" — i.e.
    an export under a live daemon; it was silent on Windows, and named
    `daemon_pid` as a field the result did not carry. The documented remedy
    must hold every step in the SAFE order, both "never"s, the Windows case,
    the stamp format, and where `daemon_pid` really is."""
    text = (HERE.parent.parent / "docs" / "modules" / "event_store.md").read_text(
        encoding="utf-8")
    steps = ["dashboard_daemon.py\n  --stop", "`not-running`", "ps -p <pid> -o command=",
             "terminer ce pid", "supprimer `.agents/state/local/dashboard.lock`"]
    positions = [text.find(step) for step in steps]
    assert -1 not in positions, dict(zip(steps, positions))
    assert positions == sorted(positions), (
        "the remedy steps are out of the safe order: " + repr(dict(zip(steps, positions))))
    for needed in ("Jamais tuer un autre process", "jamais supprimer le verrou d'un démon vivant",
                   "**Sous Windows**", 'tasklist /FI "PID eq <pid>"',
                   "AAAAMMJJTHHMMSSZ-p<pid>", "`daemon_pid` sur TOUS ses chemins"):
        assert needed in text, needed


@pytest.mark.parametrize("path", ["exported", "refused_first", "refused_recheck",
                                  "absent_store", "schemaless"])
def test_cli_export_spool_reports_daemon_pid_on_every_path(
        _redirect, monkeypatch, capsys, path):
    """F4 of critic-opus / T2 of critic-fable (final): `daemon_pid` was
    announced by the documentation but printed only by the first-check
    refusal. It is in EVERY `--export-spool` payload now — and after a
    re-check it is the RE-CHECK's pid, the one the refusal is about."""
    answers = {
        "exported": [("absent", None), ("absent", None)],
        "refused_first": [("alive", 4242)],
        "refused_recheck": [("absent", None), ("alive", 5151)],
        "absent_store": [("stale", 7777)],
        "schemaless": [("stale", 7777)],
    }[path]
    expected = {"exported": None, "refused_first": 4242, "refused_recheck": 5151,
                "absent_store": 7777, "schemaless": 7777}[path]
    if path in ("exported", "refused_recheck"):
        _cli_store_with_rows(_redirect)
    elif path == "schemaless":
        _redirect["db"].parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(str(_redirect["db"])).close()
    sequence = iter(answers)
    monkeypatch.setattr(event_store, "_dashboard_daemon_state", lambda: next(sequence),
                        raising=False)
    event_store.main(["--export-spool"])
    printed = json.loads(capsys.readouterr().out)
    assert "daemon_pid" in printed, (path, printed)
    assert printed["daemon_pid"] == expected, (path, printed)


@pytest.mark.parametrize("answers", [[("unresponsive", 4242)],
                                     [("absent", None), ("unresponsive", 4242)]],
                         ids=["first_check", "recheck"])
def test_cli_export_spool_refuses_an_unresponsive_daemon_at_both_checks(
        _redirect, monkeypatch, capsys, answers):
    """The same refusal as for `alive`, at BOTH checks, and a remedy that
    works: `dashboard_daemon.py --stop` answers `not-running` for a daemon
    whose ping is silent, so the reason names the pid to end instead — and,
    round 3, PRINTS it with the check that tells a recycled pid apart: if its
    command line does not show `dashboard_daemon.py`, delete the lock, never
    kill a process that is not the daemon."""
    stored = _cli_store_with_rows(_redirect)
    monkeypatch.setattr(event_store, "_IS_WINDOWS", False, raising=False)  # POSIX wording
    sequence = iter(answers)
    monkeypatch.setattr(event_store, "_dashboard_daemon_state", lambda: next(sequence),
                        raising=False)
    assert event_store.main(["--export-spool"]) == 2
    printed = json.loads(capsys.readouterr().out)
    assert next(sequence, None) is None, "a daemon check was skipped"
    assert printed["status"] == "refused", printed
    assert "not-running" in printed["reason"], printed
    assert ".agents/state/local/dashboard.lock" in printed["reason"], printed
    assert "ps -p 4242 -o command=" in printed["reason"], printed
    assert "never kill a process that is not the daemon" in printed["reason"], printed
    assert "never delete the lock of a live daemon" in printed["reason"], printed
    assert _redirect["db"].exists() and _count(_redirect["db"]) == stored
    for root in (_redirect["events"], _redirect["otel"]):
        assert not (root / "exports").exists() and not (root / "exports.partial").exists()


@pytest.mark.parametrize("blocked", [False, True], ids=["promotable", "blocked"])
def test_cli_export_spool_on_an_absent_store_finishes_a_pending_promotion(
        _redirect, capsys, blocked):
    """F4 of critic-opus, round 2: the recovery lived only in THIS kit's
    `open_store(create=True)`. After a rollback — the very reason to export —
    an older kit never runs it, so a prepared export whose promotion was cut
    short stayed invisible for good. `--export-spool` on an absent store now
    finishes it, under `.maintenance.lock`, without creating the store:
    rc 0 when every proven preparation is promoted, rc 1 when one is refused."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    stamp = "20260729T120000Z"
    staging = _redirect["events"] / "exports.partial" / stamp
    staging.mkdir(parents=True)
    (staging / "x.jsonl").write_text("{}\n", encoding="utf-8", newline="\n")
    db.with_name(f"events.db.exported-{stamp}").write_bytes(b"")
    final = _redirect["events"] / "exports" / stamp
    if blocked:
        final.mkdir(parents=True)
    rc = event_store.main(["--export-spool"])
    printed = json.loads(capsys.readouterr().out)
    assert rc == (1 if blocked else 0), printed
    assert printed["status"] == "absent", printed
    recovery = printed["recovery"]
    if blocked:
        assert recovery["promoted"] == [] and len(recovery["errors"]) == 1, recovery
        assert (staging / "x.jsonl").exists()
    else:
        assert recovery == {"promoted": [str(final)], "errors": []}, recovery
        assert (final / "x.jsonl").exists() and not staging.exists()
    assert not db.exists(), "the recovery created the store"


def test_cli_export_spool_on_a_schemaless_database_says_so_and_fails(_redirect, capsys):
    """Round 3, critic-fable: an `events.db` that exists but carries no schema
    (user_version 0, empty) opens as `absent`, so `--export-spool` took the
    absent-store path, found the file and printed "the database appeared
    meanwhile" with rc 0 — a false sentence and a success for an export that
    exported nothing. Now: rc 1, and the message says what is true."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(str(db)).close()
    assert db.exists()
    assert event_store.main(["--export-spool"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "absent", printed
    assert "exists but carries no schema: nothing to export" in printed["reason"], printed
    assert "meanwhile" not in json.dumps(printed), printed
    assert db.exists(), "the schemaless file was touched"


def test_cli_export_spool_fails_when_unsafe_src_files_were_skipped(_redirect, capsys):
    """F7 of critic-opus, round 2: rows under an unsafe `src_file` key are
    skipped — never turned into a path — so after the retire they live ONLY
    in the retired database. That is not a clean export: rc 1, and `reason`
    names where those rows are."""
    ts = f"{_TODAY}T10:00:00Z"
    store = event_store.open_store(create=True)
    try:
        conn = store._conn
        for key, line_index in ((f"a/{_TODAY}.claude.1.jsonl", 0),
                                (f"a/{_TODAY}.claude.1.jsonl", 1), ("a/..", 0)):
            conn.execute(_FOLD_INSERT_SQL, (event_store.PROJECT_UNSET, "a", key, line_index,
                                            f"{key}{line_index}", _TODAY, ts, "hook.deny",
                                            json.dumps(_rec(ts=ts)), ts))
    finally:
        store.close()
    assert event_store.main(["--export-spool"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "exported" and printed["rows_skipped_unsafe_name"] == 1, printed
    assert printed["db_retired_to"] and printed["db_retired_to"] in (printed["reason"] or ""), (
        printed)


# ---------------------------------------------------------------------------
# T-00000086 — `session_feed`: canal A grouped by (host, sid) over a bounded
# window.
#
# WHAT THIS BLOCK IS REALLY GUARDING. Not "does it return rows" — that is the
# easy half. It guards the four ways this read could quietly lie:
#   * a window that silently answers a different question than the one asked
#     (retention clamp, `since` in a format the column does not use);
#   * a truncation that looks like a measurement (caps that slice without
#     saying so, counts derived from a truncated page);
#   * a row with no `sid` disappearing instead of being counted;
#   * a degraded store rendering as "no session".
# Every test below is one of those four.
# ---------------------------------------------------------------------------

def _sess(ts: str, sid: str | None, host: str = "claude", **fields) -> dict:
    """A canal-A record with a session id. `sid=None` is the SESSIONLESS case,
    which is a first-class shape here, not a malformed record: the hooks that
    emit `hook.deny` from a bare shell genuinely have no session to name."""
    return _rec(ts=ts, sid=sid, host=host, **fields)


def _ingest(_redirect, records: list[dict], name: str | None = None):
    """Write one spool file and project it, returning an OPEN store. The
    filename is dated `_TODAY` for the reason the module header gives: any other
    day is a PAST day to the injected clock and gets folded by the migration."""
    _write_spool(_redirect["events"], name or f"{_TODAY}.claude.700.jsonl", records)
    store = event_store.open_store(create=True)
    store.ingest_once(now=_FROZEN_NOW)
    return store


def _sids(feed: dict) -> list[str]:
    return [s["sid"] for s in feed["sessions"]]


def test_session_feed_groups_canal_a_by_host_and_sid(_redirect):
    """The nominal shape. TWO hosts sharing a session id is deliberate: the key
    is the PAIR, and a feed keyed on `sid` alone would merge two consoles."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T10:00:00Z", "s-1", host="claude", kind="session.start"),
        _sess("2026-07-29T10:00:05Z", "s-1", host="claude", kind="hook.deny", agent="dev-multi"),
        _sess("2026-07-29T10:01:00Z", "s-1", host="codex", kind="session.start"),
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["status"] == "ok"
    assert feed["total_sessions"] == 2
    pairs = {(s["host"], s["sid"]) for s in feed["sessions"]}
    assert pairs == {("claude", "s-1"), ("codex", "s-1")}
    claude = next(s for s in feed["sessions"] if s["host"] == "claude")
    assert claude["total_events"] == 2
    assert claude["counts_by_kind"] == {"session.start": 1, "hook.deny": 1}
    assert claude["agents"] == ["dev-multi"]
    assert claude["first_ts"] == "2026-07-29T10:00:00Z"
    assert claude["last_ts"] == "2026-07-29T10:00:05Z"
    assert claude["truncated"] is False


def test_session_feed_ranks_by_last_activity_not_by_id(_redirect):
    """`last_ts` DESC, because the cap keeps the HEAD of this list: ranked any
    other way, filling up would drop the sessions a reader is watching."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T09:00:00Z", "old"),
        _sess("2026-07-29T11:30:00Z", "fresh"),
        _sess("2026-07-29T10:00:00Z", "middle"),
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _sids(feed) == ["fresh", "middle", "old"]


def test_session_feed_window_excludes_what_is_outside_it(_redirect):
    """The window is a MEASUREMENT boundary, not a display preference: a session
    whose last event predates `since` is not in the answer at all."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T11:00:00Z", "inside"),
        _sess("2026-07-27T11:00:00Z", "outside"),
    ])
    try:
        default_window = store.session_feed(now=_FROZEN_NOW)
        wide = store.session_feed("2026-07-26T00:00:00Z", now=_FROZEN_NOW)
    finally:
        store.close()
    assert _sids(default_window) == ["inside"], "the default window is 24 h"
    assert default_window["window"]["since"] == "2026-07-28T12:00:00Z"
    assert default_window["window"]["until"] == "2026-07-29T12:00:00Z"
    assert sorted(_sids(wide)) == ["inside", "outside"]


def test_session_feed_since_below_retention_is_clamped_and_says_so(_redirect):
    """A 90-day question against a 30-day store must not come back looking
    answered. The floor is applied AND declared."""
    store = _ingest(_redirect, [_sess("2026-07-29T11:00:00Z", "s-1")])
    try:
        feed = store.session_feed("2026-01-01T00:00:00Z", now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["window"]["clamped_to_retention"] is True
    assert feed["window"]["requested_since"] == "2026-01-01T00:00:00Z"
    assert feed["window"]["since"] == "2026-06-29T12:00:00Z"
    assert feed["window"]["retention_days"] == event_store.RETENTION_DAYS


def test_session_feed_unparseable_since_falls_back_without_swallowing_it(_redirect):
    """Not an error, not a silent default: the caller's own string comes back in
    `requested_since` so a UI can tell it was not honoured."""
    store = _ingest(_redirect, [_sess("2026-07-29T11:00:00Z", "s-1")])
    try:
        feed = store.session_feed("hier matin", now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["window"]["requested_since"] == "hier matin"
    assert feed["window"]["since"] == "2026-07-28T12:00:00Z"
    assert _sids(feed) == ["s-1"]


def test_session_feed_caps_the_session_count_and_declares_the_cut(_redirect):
    # 08:00 → 11:00, all INSIDE the window: `until` is the injected now
    # (12:00Z), and an event stamped after it would be excluded by the window
    # rather than by the cap — which would make this test pass for the wrong
    # reason.
    store = _ingest(_redirect, [
        _sess(f"2026-07-29T{hour}:00:00Z", f"s-{i}")
        for i, hour in enumerate(("08", "09", "10", "11"))
    ])
    try:
        capped = store.session_feed(now=_FROZEN_NOW, caps={"sessions": 2})
        whole = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _sids(capped) == ["s-3", "s-2"], "the cap keeps the most recent"
    assert capped["truncated_sessions"] is True
    assert capped["total_sessions"] == 2
    assert whole["truncated_sessions"] is False
    assert len(whole["sessions"]) == 4


def test_session_feed_keeps_the_last_events_and_returns_them_chronologically(_redirect):
    """TWO properties in one test because they are one decision: the SQL takes
    the tail (`ORDER BY ts DESC`) and the response reverses it. Asserting only
    the count would pass on a page that reads backwards."""
    store = _ingest(_redirect, [
        _sess(f"2026-07-29T10:0{i}:00Z", "s-1", data={"n": i}) for i in range(6)
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW, caps={"events_per_session": 3})
    finally:
        store.close()
    session = feed["sessions"][0]
    assert [e["ts"] for e in session["events"]] == [
        "2026-07-29T10:03:00Z", "2026-07-29T10:04:00Z", "2026-07-29T10:05:00Z"]
    assert session["truncated"] is True


def test_session_feed_counts_span_the_window_not_the_truncated_page(_redirect):
    """The defect this pins: `total_events` and `counts_by_kind` derived from a
    3-event page would report 3 for a 6-event session — a plausible number that
    is wrong, which is worse than an absent one."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T10:00:00Z", "s-1", kind="session.start"),
        *[_sess(f"2026-07-29T10:0{i}:00Z", "s-1", kind="hook.deny", agent="dev-mono")
          for i in range(1, 5)],
        _sess("2026-07-29T10:05:00Z", "s-1", kind="session.stop", agent="planner"),
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW, caps={"events_per_session": 2})
    finally:
        store.close()
    session = feed["sessions"][0]
    assert len(session["events"]) == 2
    assert session["total_events"] == 6
    assert session["counts_by_kind"] == {
        "session.start": 1, "hook.deny": 4, "session.stop": 1}
    assert session["agents"] == ["dev-mono", "planner"]


def test_session_feed_caps_are_bounded_and_never_liftable_to_unbounded(_redirect):
    """A cap exists to bound memory, so a caller may lower it, not remove it.
    Garbage falls back to the default rather than becoming an open LIMIT."""
    assert event_store._session_feed_caps({"sessions": 10 ** 9})["sessions"] == 500
    for junk in ({"sessions": 0}, {"sessions": -3}, {"sessions": "beaucoup"},
                 {"sessions": None}, {"sessions": True}, {}, None):
        assert (event_store._session_feed_caps(junk)["sessions"]
                == event_store.SESSION_FEED_MAX_SESSIONS), junk


def test_session_feed_filters_by_host_and_by_project(_redirect):
    _init_identity(_redirect)
    store = _ingest(_redirect, [
        _sess("2026-07-29T10:00:00Z", "c-1", host="claude"),
        _sess("2026-07-29T10:01:00Z", "x-1", host="codex"),
    ])
    try:
        claude = store.session_feed(now=_FROZEN_NOW, host="claude")
        mine = store.session_feed(now=_FROZEN_NOW, project=store.project)
        foreign = store.session_feed(now=_FROZEN_NOW, project="un-autre-projet")
    finally:
        store.close()
    assert _sids(claude) == ["c-1"]
    assert claude["filters"] == {"host": "claude", "project": None}
    assert sorted(_sids(mine)) == ["c-1", "x-1"]
    assert foreign["sessions"] == []
    assert foreign["total_sessions"] == 0


def test_session_feed_offers_filter_choices_the_active_filter_cannot_hide(_redirect):
    """A `<select>` built from a filtered payload can only ever offer the value
    already selected — a one-way door. The facets are read without the caller's
    own host/project predicates for exactly that reason."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T10:00:00Z", "c-1", host="claude"),
        _sess("2026-07-29T10:01:00Z", "x-1", host="codex"),
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW, host="claude")
    finally:
        store.close()
    assert feed["filters_available"]["hosts"] == ["claude", "codex"]
    assert feed["filters_available"]["truncated"] is False


def test_session_feed_counts_sessionless_rows_per_host_instead_of_dropping_them(_redirect):
    """The hooks that fire outside a session are the MAJORITY of canal A today.
    Dropping them would delete a whole class of events from a view whose subject
    is "what happened"; inventing a session id for them would be worse."""
    store = _ingest(_redirect, [
        _sess("2026-07-29T10:00:00Z", "s-1", host="claude"),
        _sess("2026-07-29T10:01:00Z", None, host="claude"),
        _sess("2026-07-29T10:02:00Z", "", host="claude"),
        _sess("2026-07-29T10:03:00Z", None, host="codex"),
        _sess("2026-07-29T10:04:00Z", None, host=None),
    ])
    try:
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _sids(feed) == ["s-1"]
    assert feed["sessionless"]["count"] == 4
    assert feed["sessionless"]["by_host"] == {
        "claude": 2, "codex": 1, event_store.SESSION_HOST_ABSENT: 1}


def test_session_feed_never_names_a_project_for_a_session_that_spans_two(_redirect):
    """`project` on a session is what the ROWS carry, and when they carry two
    different values naming one of them would be a coin toss presented as a
    fact."""
    _init_identity(_redirect)
    store = _ingest(_redirect, [_sess("2026-07-29T10:00:00Z", "s-1")])
    try:
        store.connection.execute(
            "UPDATE events SET project = 'autre' WHERE id = "
            "(SELECT MIN(id) FROM events)")
        store.connection.commit()
        _write_spool(_redirect["events"], f"{_TODAY}.claude.701.jsonl",
                     [_sess("2026-07-29T10:01:00Z", "s-1")])
        store.ingest_once(now=_FROZEN_NOW)
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["sessions"][0]["project"] is None


def test_session_feed_ignores_canal_b(_redirect):
    """Canal B has no `sid` and a completely different envelope; letting it into
    this group-by would invent sessions out of OTLP payloads."""
    _init_identity(_redirect)
    _write_otel_spool(_redirect["otel"], f"{_TODAY}.1.jsonl", [
        _otel_envelope(ts="2026-07-29T10:00:00Z", project_id=_OWN_ID)])
    store = _ingest(_redirect, [_sess("2026-07-29T10:00:00Z", "s-1")])
    try:
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert _sids(feed) == ["s-1"]
    assert feed["sessionless"]["count"] == 0


def test_session_feed_counts_a_body_it_cannot_parse_instead_of_hiding_it(_redirect):
    """A row whose body is not JSON is stored verbatim by the ingester (a
    projection relocates, it does not summarise), so the counter that says how
    many were skipped has to keep counting something real."""
    store = _ingest(_redirect, [_sess("2026-07-29T10:00:00Z", "s-1")])
    try:
        store.connection.execute("UPDATE events SET body = 'pas du json'")
        store.connection.commit()
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["sessions"][0]["events"] == []
    assert feed["sessions"][0]["total_events"] == 1
    assert feed["malformed_skipped"] == 1


@pytest.mark.parametrize("break_it,expected", [
    (lambda db: db.write_bytes(b"not a database" * 20), "unavailable"),
    (None, "schema_ahead"),
])
def test_session_feed_degrades_in_a_known_shape_and_runs_no_sql(_redirect, break_it,
                                                                expected):
    """The same posture as every other reader here: a non-`ok` store returns the
    FULL key set, empty, with its reason — never a bare list, never a raise, and
    never one v1 statement against a schema it cannot read."""
    db = _redirect["db"]
    if break_it is None:
        store = event_store.open_store(create=True)
        store.connection.execute("PRAGMA user_version = 2")
        store.close()
    else:
        db.parent.mkdir(parents=True, exist_ok=True)
        break_it(db)
    store = event_store.open_store(create=False)
    try:
        assert store.status == expected
        assert store.connection is None, "no connection means no SQL is possible"
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["status"] == expected
    assert feed["reason"]
    assert feed["sessions"] == []
    assert feed["total_sessions"] == 0
    assert feed["truncated_sessions"] is False
    assert feed["sessionless"] == {"count": 0, "by_host": {}}
    assert feed["filters_available"] == {"hosts": [], "projects": [],
                                         "truncated": False}
    # The window is still stated: "we could not read" is a different fact from
    # "we did not look", and only the second one has no window.
    assert feed["window"]["since"] == "2026-07-28T12:00:00Z"


def test_session_feed_on_an_absent_store_is_a_state_never_an_error(_redirect):
    store = event_store.open_store(create=False)
    try:
        assert store.status == "absent"
        feed = store.session_feed(now=_FROZEN_NOW)
    finally:
        store.close()
    assert feed["status"] == "absent"
    assert feed["sessions"] == []


def test_session_feed_creates_no_index(_redirect):
    """The bound is the EXISTING `events_ts` index plus the caps, not a new one:
    this read must not change the write path's cost. A future index is a
    deliberate decision, not a drive-by of a display task."""
    before = _ingest(_redirect, [_sess("2026-07-29T10:00:00Z", "s-1")])
    try:
        names = {row[0] for row in before.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name NOT LIKE 'sqlite_%'").fetchall()}
        before.session_feed(now=_FROZEN_NOW)
        after = {row[0] for row in before.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name NOT LIKE 'sqlite_%'").fetchall()}
    finally:
        before.close()
    assert names == after
    assert "events_ts" in names


# ---------------------------------------------------------------------------
# T-00000770 — `open_store` ouvre `events.db` SANS SUIVRE, par la primitive de
# `cadre.ledger.store` (couture `_cadre_module` : paquet, puis chemin). Un lien à
# l'emplacement sort sous `absent` + cause nommée (`location_refused`), jugé AVANT
# `existed` et la migration du spool ; une couture introuvable sort sous `absent`
# + `seam_missing` ; un store neuf naît en 0o600.
# ---------------------------------------------------------------------------

_SANS_O_NOFOLLOW = pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"),
                                      reason="O_NOFOLLOW absent (R3 de T-00000759)")


def _sha_t770(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _empreinte_t770(d: Path) -> dict[str, str]:
    """`{nom -> sha256}` des fichiers de `d` (liens exclus : ils ne sont pas lus)."""
    return {p.name: _sha_t770(p) for p in sorted(d.iterdir())
            if p.is_file() and not p.is_symlink()}


def _base_events_tierce_t770(_redirect, chemin: Path, n: int = 2) -> None:
    """Une VRAIE base events (schéma + `n` lignes ingérées) à `chemin`, hors de
    l'emplacement d'`events.db` — la base qu'un lien planté ferait lire."""
    path = _write_spool(_redirect["events"], f"{_TODAY}.claude.171.jsonl",
                        [_rec(task=f"T-{i}") for i in range(n)])
    _touch_old(path, now=_FROZEN_NOW)
    store = event_store.open_store(chemin, create=True)
    try:
        assert store.status == "ok", store.reason
        assert store.ingest_once(now=_FROZEN_NOW)["deleted"] == 1
    finally:
        store.close()
    assert _count(chemin) == n


def _masquer_la_couture_t770(m, dossier_vide: Path) -> None:
    """`cadre.ledger.store` introuvable par les DEUX branches de `_cadre_module` :
    le paquet masqué dans `sys.modules`, le repli par chemin pointé sur un dossier
    VIDE, le mémo vidé — patron de `_couture_executor_absente`
    (`agentic_v3/tests/test_run_export.py`)."""
    for nom in ("cadre", "cadre.ledger", "cadre.ledger.store", "cadre.workspace"):
        m.setitem(sys.modules, nom, None)
    m.setattr(event_store, "_SRC_CADRE", dossier_vide)
    m.setattr(event_store, "_MODULES_CADRE", {})


@_SANS_O_NOFOLLOW
def test_un_lien_pendant_a_la_place_d_events_db_est_refuse_avant_la_migration_t770(
        _redirect, monkeypatch, tmp_path):
    """E1 (+ A-C2) — lecteur ET démon sur un `events.db` qui est un lien
    PENDANT : `absent`, `open_report["location_refused"]` porte le refus de
    `store.py` (« lien symbolique »), la cible n'est jamais créée, le lien reste.
    Le jugement tombe AVANT `existed` et `_migrate_legacy_spool` : la migration
    n'est PAS appelée. BASE : le lecteur disait « rien ingéré » sans cause, le
    démon migrait le spool puis SQLite créait la cible au bout du lien. Mord :
    Mh ; et Mq (jugement déplacé après la migration) par l'espion."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    os.symlink(dehors / "cible.db", db)
    appels: list = []
    reel = event_store._migrate_legacy_spool
    monkeypatch.setattr(event_store, "_migrate_legacy_spool",
                        lambda cible: (appels.append(cible), reel(cible))[1])
    for create in (False, True):
        store = event_store.open_store(create=create)
        try:
            assert store.status == "absent", (create, store.status, store.reason)
            refus = store.open_report.get("location_refused")
            assert refus and "lien symbolique" in refus, (create, store.open_report)
            assert "lien symbolique" in (store.reason or ""), store.reason
        finally:
            store.close()
    assert appels == [], "la migration du spool a tourné AVANT le jugement du lien"
    assert not (dehors / "cible.db").exists(), "SQLite a créé la cible du lien"
    assert db.is_symlink(), "le lien a été retiré"


@_SANS_O_NOFOLLOW
def test_un_lien_vers_une_vraie_base_events_est_refuse_sans_la_lire_t770(
        _redirect, tmp_path):
    """E2 — `events.db` = lien vers une VRAIE base events (schéma + lignes) :
    `absent` + cause, jamais `ok` ; la base tierce reste octet pour octet
    (aucun `-wal`/`-shm` n'apparaît). BASE la SUIVAIT et l'ouvrait `ok`. Mord : Mh."""
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    _base_events_tierce_t770(_redirect, dehors / "tierce.db")
    avant = _empreinte_t770(dehors)
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(dehors / "tierce.db", db)
    for create in (False, True):
        store = event_store.open_store(create=create)
        try:
            assert store.status == "absent", (create, store.status, store.reason)
            assert "lien symbolique" in store.open_report.get("location_refused", "")
        finally:
            store.close()
    assert _empreinte_t770(dehors) == avant, "la base tierce a été touchée"


def test_un_events_db_neuf_nait_en_0o600_t770(_redirect):
    """E3 — `open_store(create=True)` fait naître `events.db` en 0o600 (création
    exclusive) ; BASE : 0o644 sous umask 022. Mord : Mi (`mode=0o644`)."""
    ancien = os.umask(0o022)
    try:
        store = event_store.open_store(create=True)
    finally:
        os.umask(ancien)
    try:
        assert store.status == "ok", store.reason
    finally:
        store.close()
    assert oct(_redirect["db"].stat().st_mode & 0o777) == "0o600"


@_SANS_O_NOFOLLOW
def test_export_spool_sur_un_lien_rend_1_et_nomme_le_lien_t770(_redirect, capsys, tmp_path):
    """E4 — `main(["--export-spool"])` sur un `events.db` lien : rc 1, JSON
    `absent`, `reason` nomme le lien et JAMAIS « carries no schema » (la clause
    `is_symlink` d'avant le disait d'un lien pendant) ; le lien reste, sa cible
    n'est pas créée. Sous-cas, lien vers une VRAIE base tierce : rc 1, rien
    exporté ni retiré, base tierce intacte (BASE l'exportait puis retirait le
    lien). Mord : Mo (branche `location_refused` retirée) et Mh."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    os.symlink(dehors / "cible.db", db)
    assert event_store.main(["--export-spool"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "absent", printed
    assert str(db) in printed["reason"] and "lien symbolique" in printed["reason"], printed
    assert "carries no schema" not in printed["reason"], printed
    assert db.is_symlink() and not (dehors / "cible.db").exists()

    db.unlink()
    _base_events_tierce_t770(_redirect, dehors / "tierce.db")
    avant = _empreinte_t770(dehors)
    noms_events = sorted(p.name for p in _redirect["events"].iterdir())
    noms_local = sorted(p.name for p in db.parent.iterdir())
    os.symlink(dehors / "tierce.db", db)
    assert event_store.main(["--export-spool"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "absent" and "lien symbolique" in printed["reason"], printed
    assert db.is_symlink(), "le lien a été retiré"
    assert _empreinte_t770(dehors) == avant, "la base tierce a été touchée"
    assert sorted(p.name for p in _redirect["events"].iterdir()) == noms_events, "exporté"
    assert sorted(p.name for p in db.parent.iterdir()) == sorted(noms_local + ["events.db"])


@_SANS_O_NOFOLLOW
def test_le_demon_repart_seul_une_fois_le_lien_retire_t770(_redirect, tmp_path):
    """E5 — `IngestLoop.tick()` avec le lien : store `absent` (refus nommé) ; le
    lien retiré, le tick SUIVANT rouvre et rend `ok` — `tick` ne rouvre que sur
    `absent`, c'est pourquoi le refus sort sous ce statut. BASE : le premier tick
    créait la cible au bout du lien et rendait `ok`. Mord : Mh."""
    db = _redirect["db"]
    db.parent.mkdir(parents=True, exist_ok=True)
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    os.symlink(dehors / "cible.db", db)
    loop = event_store.IngestLoop(interval=0.01)
    try:
        loop.tick()
        assert loop.store is not None and loop.store.status == "absent", (
            loop.store and loop.store.reason)
        assert "location_refused" in loop.store.open_report
        assert not (dehors / "cible.db").exists()
        db.unlink()
        loop.tick()
        assert loop.store is not None and loop.store.status == "ok", loop.store.reason
    finally:
        if loop.store is not None:
            loop.store.close()


#: La sonde d'E6 : `event_store` importé depuis `.agents/bin` SEUL (ni `src/` ni le
#: cwd sur `sys.path`, `-I`), donc la couture passe par son repli PAR CHEMIN.
_SONDE_E6 = r'''
import importlib.util, json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
arme = importlib.util.find_spec("cadre") is None
import event_store
d = Path(sys.argv[2]).resolve()
os.umask(0o022)
cible = d / "x" / "events.db"
neuf = event_store.open_store(cible, create=True)
rapport = {"arme": arme, "neuf": [neuf.status, neuf.reason,
                                  oct(cible.stat().st_mode & 0o777) if cible.exists() else None]}
neuf.close()
os.symlink(d / "cible_du_lien.db", d / "lien.db")
lien = event_store.open_store(d / "lien.db", create=True)
rapport["lien"] = [lien.status, lien.reason, lien.open_report.get("location_refused"),
                   (d / "cible_du_lien.db").exists()]
lien.close()
print(json.dumps(rapport))
'''


@_SANS_O_NOFOLLOW
def test_open_store_hors_paquet_passe_par_la_couture_par_chemin_t770(tmp_path):
    """E6 (+ B-C1) — dans un enfant `sys.executable -I` où `cadre` est
    INTROUVABLE (armement asserté), `event_store` importé depuis `.agents/bin` :
    `open_store(create=True)` sur un chemin neuf rend `ok` en 0o600 ; sur un lien,
    `absent` + cause dont le MESSAGE contient « lien symbolique » et NE contient
    PAS « cadre.ledger.store » — c'est le message, pas le statut, qui distingue un
    refus de lien d'une couture introuvable (Mq', repli par chemin retiré : le
    statut reste `absent`, seul le message change ; le cas neuf, lui, rougit par
    le statut). BASE : 0o644, et le lien était suivi (`ok`)."""
    d = tmp_path / "d"
    d.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "CADRE_STATE_DIR": str(tmp_path / "state"),
           "CADRE_PROJECT_ROOT": str(tmp_path / "racine"),
           "AGENTS_EVENTS_DIR": str(tmp_path / "events"),
           "AGENTS_OTEL_DIR": str(tmp_path / "otel"),
           "AGENTS_PROJECT_JSON": str(tmp_path / "project.json"),
           "AGENTS_OTEL_PROJECT_ROOT": str(tmp_path / "own-root")}
    (tmp_path / "events").mkdir(exist_ok=True)  # `_redirect` (autouse) le crée déjà
    fini = subprocess.run([sys.executable, "-I", "-c", _SONDE_E6, str(HERE), str(d)],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True,
                          timeout=120)
    assert fini.returncode == 0, fini.stderr
    rapport = json.loads(fini.stdout.strip().splitlines()[-1])
    assert rapport["arme"], "banc non armé : `cadre` importable dans l'enfant"
    assert rapport["neuf"][0] == "ok" and rapport["neuf"][2] == "0o600", rapport["neuf"]
    statut, raison, refus, cible_creee = rapport["lien"]
    assert statut == "absent", rapport["lien"]
    assert refus and "lien symbolique" in refus, rapport["lien"]
    assert "lien symbolique" in raison and "cadre.ledger.store" not in raison, raison
    assert not cible_creee, "la cible du lien a été créée"


def _faux_paquet_cadre_perime_t770(racine: Path) -> Path:
    """Un paquet `cadre` INSTALLÉ mais antérieur à T-00000770 : son
    `cadre.ledger.store` ne porte que `connect` — ni `refuser_les_liens`, ni
    `ouvrir_sans_suivre`, ni `EmplacementRefuse`. Rend le dossier à mettre en tête
    de `sys.path`."""
    ledger = racine / "faux" / "cadre" / "ledger"
    ledger.mkdir(parents=True)
    (ledger.parent / "__init__.py").write_text("", encoding="utf-8")
    (ledger / "__init__.py").write_text("", encoding="utf-8")
    (ledger / "store.py").write_text(
        "import sqlite3\n\n\ndef connect(chemin, **_):\n"
        "    return sqlite3.connect(str(chemin))\n", encoding="utf-8")
    return racine / "faux"


#: La sonde de F2 (binôme de clôture de T-00000770) : un paquet `cadre` PÉRIMÉ en
#: tête de `sys.path`, le paquet du clone (vendor ou `src`) complet. La couture doit retenter
#: PAR CHEMIN au lieu de se déclarer absente ; si la copie par chemin échoue AUSSI,
#: le refus nomme le module périmé (`__name__` ET `__file__`).
_SONDE_F2 = r'''
import json, sys
from pathlib import Path
faux, bin_, d = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(faux))
import cadre.ledger.store as perime
arme = hasattr(perime, "connect") and not hasattr(perime, "ouvrir_sans_suivre")
sys.path.insert(1, str(bin_))
import event_store
s = event_store.open_store(d / "events.db", create=True)
module = event_store._MODULES_CADRE.get("ledger.store")
rapport = {"arme": arme, "perime": [perime.__name__, perime.__file__],
           "ok": [s.status, s.reason, getattr(module, "__file__", None)]}
s.close()
event_store._MODULES_CADRE.clear()
event_store._SRC_CADRE = d / "vide"
s = event_store.open_store(d / "events2.db", create=True)
rapport["echec"] = [s.status, s.open_report.get("seam_missing"), (d / "events2.db").exists()]
s.close()
print(json.dumps(rapport))
'''


def test_un_paquet_cadre_perime_est_rattrape_par_la_copie_par_chemin_t770(tmp_path):
    """F2 — un paquet `cadre` installé, antérieur à T-00000770 (sans la primitive),
    ne coupe pas l'ouverture quand le paquet du clone est là (`.agents/vendor/cadre`,
    sinon `src/cadre`, selon `vendor_paths`) : la couture retente PAR CHEMIN, `ok`
    par SA copie de `ledger/store.py`. Si cette copie échoue AUSSI (repli pointé sur
    un dossier vide) : `absent` + `seam_missing` qui nomme le module périmé, son
    `__name__` et son `__file__`, rien créé. Rouge avant F2 (le paquet périmé menait
    droit à `seam_missing`). Mord : le repli par chemin retiré de `_couture_ledger_store`."""
    faux = _faux_paquet_cadre_perime_t770(tmp_path)
    d = tmp_path / "d"
    d.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "CADRE_STATE_DIR": str(tmp_path / "state"),
           "CADRE_PROJECT_ROOT": str(tmp_path / "racine"),
           "AGENTS_EVENTS_DIR": str(tmp_path / "events"),
           "AGENTS_OTEL_DIR": str(tmp_path / "otel"),
           "AGENTS_PROJECT_JSON": str(tmp_path / "project.json"),
           "AGENTS_OTEL_PROJECT_ROOT": str(tmp_path / "own-root")}
    fini = subprocess.run([sys.executable, "-I", "-c", _SONDE_F2, str(faux), str(HERE), str(d)],
                          cwd=str(tmp_path), env=env, capture_output=True, text=True,
                          timeout=120)
    assert fini.returncode == 0, fini.stderr
    rapport = json.loads(fini.stdout.strip().splitlines()[-1])
    assert rapport["arme"], "banc non armé : le paquet périmé n'est pas celui importé"
    statut, raison, fichier = rapport["ok"]
    assert statut == "ok", raison
    paquet = _load("_t770_vendor_paths", "vendor_paths.py").exiger(HERE.parents[1], "cadre")
    assert fichier == str(paquet / "ledger" / "store.py"), fichier
    statut, manque, cree = rapport["echec"]
    nom_perime, fichier_perime = rapport["perime"]
    assert statut == "absent" and manque, rapport["echec"]
    assert nom_perime in manque and fichier_perime in manque, manque
    assert not cree, "un store a été créé sans primitive"


@_SANS_O_NOFOLLOW
@pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 0)() == 0,
                    reason="root ouvre un fichier en mode 000, Windows n'a pas ce mode")
def test_un_events_db_illisible_est_une_panne_d_acces_pas_un_refus_t770(_redirect):
    """Décision de l'orchestrateur (délégation pilote) sur T-00000770 : un
    `events.db` EXISTANT, fichier régulier, pas un lien, identité inchangée, que
    SQLite ne peut pas ouvrir (mode 000, CANTOPEN) est une PANNE D'ACCÈS :
    `unavailable`, la raison nomme le chemin ET l'échec d'ouverture de SQLite,
    jamais `absent` + `location_refused` — le refus d'emplacement reste aux vrais
    cas (lien, identité changée, non-régulier). Lecteur comme démon. Rouge avant
    le correctif (la primitive traduisait ce CANTOPEN en `EmplacementRefuse`).
    Mord : CANTOPEN d'un fichier inchangé retraduit en `EmplacementRefuse`."""
    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok", store.reason
    finally:
        store.close()
    db = _redirect["db"]
    os.chmod(db, 0)
    try:
        for create in (False, True):
            store = event_store.open_store(create=create)
            try:
                assert store.status == "unavailable", (create, store.status, store.reason)
                assert "location_refused" not in store.open_report, store.open_report
                assert str(db) in store.reason, store.reason
                assert "unable to open" in store.reason, store.reason
            finally:
                store.close()
    finally:
        os.chmod(db, 0o600)


def test_un_events_db_disparu_avant_l_ouverture_n_est_pas_un_refus_t770(
        _redirect, monkeypatch):
    """F4 (binôme de clôture) — `events.db` existait au test d'existence puis a
    DISPARU avant l'ouverture (ni fichier ni lien à sa place) : ce n'est pas un
    refus d'emplacement, c'est un store absent — `absent` « vanished before the
    open », sans `location_refused`, rien créé. La course est jouée par
    `Path.exists` lui-même : il répond, PUIS le fichier est retiré. Rouge avant F4
    (la primitive disait « a disparu » et `open_store` le rangeait en refus)."""
    store = event_store.open_store(create=True)
    store.close()
    db = _redirect["db"]
    reel = Path.exists
    joue: list = []

    def exists_puis_retire(self, *args, **kwargs):
        rendu = reel(self, *args, **kwargs)
        if not joue and rendu and self == db:
            joue.append(self)
            db.unlink()
        return rendu

    monkeypatch.setattr(Path, "exists", exists_puis_retire)
    store = event_store.open_store(create=False)
    try:
        statut, raison, rapport = store.status, store.reason or "", dict(store.open_report)
    finally:
        store.close()
    monkeypatch.undo()
    assert joue, "banc non armé : la course n'a pas été jouée"
    assert statut == "absent", (statut, raison)
    assert "location_refused" not in rapport, rapport
    assert "vanished before the open" in raison, raison
    assert not db.exists() and not db.is_symlink(), "un store a été recréé"


def test_la_raison_d_une_couture_absente_ne_promet_pas_le_spool_t770(
        _redirect, monkeypatch, tmp_path):
    """F3 (binôme de clôture) — la raison d'une couture absente sur un
    `events.db` EXISTANT disait « The spool files stay the source of truth » :
    faux, l'ingesteur SUPPRIME le spool qu'il ingère, donc le store existant
    porte l'histoire et le spool n'en garde que la queue. Elle dit désormais ce
    qui est vrai : le store est laissé intact mais NON LU, et c'est retenté à
    chaque tick."""
    store = event_store.open_store(create=True)
    store.close()
    with monkeypatch.context() as m:
        _masquer_la_couture_t770(m, tmp_path / "cadre-absent")
        store = event_store.open_store(create=False)
        try:
            raison = store.reason or ""
        finally:
            store.close()
    assert "source of truth" not in raison, raison
    assert "left untouched but NOT read" in raison, raison
    assert "deletes the spool files it ingests" in raison, raison
    assert "retried on every tick" in raison, raison


def test_une_couture_introuvable_sort_sous_absent_et_se_nomme_t770(
        _redirect, monkeypatch, capsys, tmp_path):
    """A-C1 + A-C5 — `cadre.ledger.store` introuvable par les DEUX branches de la
    couture. Store ABSENT, démon : `absent`, `open_report["seam_missing"]`, rien
    créé. Store EXISTANT (A-C5), lecteur comme démon : `absent`, `seam_missing`
    DISTINCT de `location_refused`, raison « couture cadre.ledger.store
    absente » et jamais « rien ingéré » ; `--export-spool` rend 1 en le disant,
    jamais « carries no schema » ; la base reste octet pour octet. Rouge sur
    BASE (aucune couture : `_SRC_CADRE` absent). Mord : l'`except` de la couture
    fondu dans `except (sqlite3.Error, OSError)` (`FileNotFoundError` y tomberait
    en `unavailable`)."""
    db = _redirect["db"]
    with monkeypatch.context() as m:
        _masquer_la_couture_t770(m, tmp_path / "cadre-absent")
        store = event_store.open_store(create=True)
        try:
            assert store.status == "absent", (store.status, store.reason)
            assert store.open_report.get("seam_missing"), store.open_report
            assert "couture cadre.ledger.store absente" in (store.reason or ""), store.reason
        finally:
            store.close()
        assert not db.exists(), "un store a été créé sans la couture"

    store = event_store.open_store(create=True)  # un events.db RÉEL, couture présente
    try:
        assert store.status == "ok", store.reason
    finally:
        store.close()
    avant = _sha_t770(db)
    with monkeypatch.context() as m:
        _masquer_la_couture_t770(m, tmp_path / "cadre-absent")
        for create in (False, True):
            store = event_store.open_store(create=create)
            try:
                assert store.status == "absent", (create, store.status, store.reason)
                assert store.open_report.get("seam_missing"), store.open_report
                assert "location_refused" not in store.open_report
                assert "couture cadre.ledger.store absente" in store.reason, store.reason
                assert "not ingested anything" not in store.reason, store.reason
            finally:
                store.close()
        assert event_store.main(["--export-spool"]) == 1
        printed = json.loads(capsys.readouterr().out)
        assert "couture cadre.ledger.store absente" in printed["reason"], printed
        assert "carries no schema" not in printed["reason"], printed
    assert _sha_t770(db) == avant, "la base a été touchée sans couture"
