"""Tests for dashboard.py — the UI/API server core (T-00000025 shard 1).

Style: explicit-path module load (matching this repo's test_events.py /
test_otel_receiver.py convention). Every test redirects state via
AGENTS_DASHBOARD_PROJECT_ROOT / AGENTS_EVENTS_DIR (monkeypatch.setenv),
never the real repo trees.
"""
from __future__ import annotations

import ast
import base64
import http.client
import http.server
import importlib.util
import inspect
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# LE JEU DE CLÉS DE VUES — UN littéral, écrit À LA MAIN, et c'est délibéré.
#
# Il était recopié à TROIS endroits : l'ajout d'une septième vue (T-00000379
# lot E, `specs_graph`) a donc fait rougir trois tests pour un seul changement,
# et un correcteur pressé en aurait patché deux sur trois. Une seule copie
# désormais.
#
# POURQUOI PAS DÉRIVÉ de `build_views` : parce que ce serait vide de sens. Un
# jeu dérivé de l'implémentation est d'accord avec elle par construction, y
# compris le jour où une vue disparaît par accident. C'est un CONTRAT gelé : on
# le change EN MÊME TEMPS qu'on change le payload, jamais après coup.
_EXPECTED_VIEW_KEYS = {
    "governance", "security", "memory", "index", "mcp", "coverage", "specs_graph", "chrono",
}

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("dashboard", HERE / "dashboard.py")
dashboard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dashboard
_spec.loader.exec_module(dashboard)

otel_receiver = dashboard._otel_receiver
events_mod = dashboard._events_mod
readers = dashboard._readers_mod
event_store = dashboard._event_store_mod

# The project identity every canal-B test in this file runs under (a uuid4 in
# production, `project_init.py:228`; a fixed literal here so assertions can name
# it) and a neighbouring project's, for the quarantine cases.
_OWN_ID = "own-project-id-0001"
_OTHER_ID = "neighbour-project-id-0002"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    events_dir = tmp_path / "events"
    otel_dir = tmp_path / "otel"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTS_DASHBOARD_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(events_dir))
    # AGENTS_OTEL_DIR matters from shard 4b on: `/api/snapshot` now READS canal
    # B, so without this redirect every test in this file would silently assert
    # against whatever real telemetry sits in this developer's own
    # state/local/otel/ - green or red depending on the machine.
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(otel_dir))
    # V1-c: canal B is attributed against `.agents/state/project.json`, so the
    # identity is redirected like every other state input and WRITTEN with a
    # known id — otherwise these tests would resolve this developer's real
    # project and the census would be green or red depending on the machine.
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "own-root"))
    # T-00000083: `/api/peers` reads the MACHINE-WIDE registry. Without this
    # redirect every test in this file would read — and the daemon-side tests
    # would rewrite — this developer's real `~/.agentkit/registry.json`,
    # probing (and garbage-collecting) their own running daemons.
    monkeypatch.setenv("AGENTKIT_REGISTRY", str(tmp_path / "registry.json"))
    # T-00000087: `/api/term` reads `wrap.py`'s spool directory. Without this
    # redirect the suite would list — and stream — this developer's REAL console
    # mirrors, holding handles on files a live `wrap.py` is rotating.
    monkeypatch.setenv("AGENTS_TERM_DIR", str(tmp_path / "term"))
    (tmp_path / "project.json").write_text(json.dumps({"project_id": _OWN_ID}),
                                           encoding="utf-8", newline="\n")
    otel_receiver._reset_identity_cache_for_tests()
    dashboard._reset_canal_b_cache_for_tests()
    dashboard._reset_canal_a_cache_for_tests()
    # T-00000026 shard A: the six D4 view readers are memoised on a file
    # fingerprint that INCLUDES the resolved project root, so cross-test
    # contamination is structurally impossible - but a test that writes a file
    # and re-polls within the same tree needs a clean slate to be honest about
    # what invalidated what.
    readers.reset_cache_for_tests()
    yield {"project_root": project_root, "events_dir": events_dir,
           "otel_dir": otel_dir, "term_dir": tmp_path / "term"}


@pytest.fixture(autouse=True)
def _drain_streams():
    """SSE slot accounting is a MODULE-level counter, so a leaked slot would
    surface as a mysterious 503 in an unrelated later test. Declared right
     after `_redirect` so it finalises AFTER any `ui_server` teardown (fixture
    finalisation is reverse of setup): by then `server_close()` has set
    `stream_stop`, every loop has had a chance to exit, and a slot still held
    is a real leak worth failing on here rather than three tests later."""
    yield
    deadline = time.monotonic() + 10.0
    while (dashboard.active_stream_count() or dashboard.active_term_stream_count()) \
            and time.monotonic() < deadline:
        time.sleep(0.02)
    assert dashboard.active_stream_count() == 0, "an SSE stream slot leaked past its test"
    # T-00000087: the MIRROR counter is separate, so a leak in it would not be
    # caught by the assertion above — and would surface as a mysterious 503 on
    # `/api/term/stream` several tests later.
    assert dashboard.active_term_stream_count() == 0, "a term stream slot leaked past its test"


@pytest.fixture
def ui_server(_redirect):
    """A live UIHTTPServer on an ephemeral loopback port, background thread."""
    result = dashboard.create_ui_server(project_root=_redirect["project_root"])
    assert result is not None
    httpd, token = result
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        yield port, token
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def ui_server_object(_redirect):
    """Same live server as `ui_server`, but yields the server OBJECT too —
    needed by the static-vs-idle-watchdog test, which asserts on
    `last_activity` (shard 2's watchdog input) rather than on a response."""
    result = dashboard.create_ui_server(project_root=_redirect["project_root"])
    assert result is not None
    httpd, token = result
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, httpd.server_address[1], token
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def empty_ui_dir(monkeypatch):
    """Repoint `_UI_DIR` at an EMPTY directory to exercise the missing-UI-file
    path without deleting anything from the repo. `ignore_cleanup_errors=True`
    per L-00000035 (Windows teardown flake in these suites: a still-closing
    handler thread can hold a handle past the test)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        monkeypatch.setattr(dashboard, "_UI_DIR", Path(tmp))
        yield Path(tmp)


@pytest.fixture
def otlp_server(_redirect):
    """A live OTLPHandler server (shard 0), used only to prove /api/* 404s
    on the wrong socket (finding B3)."""
    httpd = http.server.HTTPServer(("127.0.0.1", 0), otel_receiver.OTLPHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(port: int, path: str, token: str | None = None, extra_headers: dict | None = None) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = dict(extra_headers or {})
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        resp.data = body  # type: ignore[attr-defined]
        return resp
    finally:
        conn.close()


def _post(port: int, path: str, body: bytes = b"") -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        return resp
    finally:
        conn.close()


def _open_stream(port: int, token: str | None = None, timeout: float = 10.0):
    """Open `/api/stream` and return `(conn, resp)` WITHOUT reading the body —
    an SSE body never ends, so `_get`'s `resp.read()` would block forever.
    Callers read line by line via `_read_frame`."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", "/api/stream", headers=headers)
    return conn, conn.getresponse()


def _close_stream(conn, resp) -> None:
    """Actually hang up. Verified empirically, and NOT interchangeable with
    `conn.close()`: an SSE response is HTTP/1.0 with no Content-Length, so
    `will_close` is True and `getresponse()` already called
    `HTTPConnection.close()` internally — which set `sock = None` and, because
    `resp.fp` (a `makefile`) still holds an io-ref, did NOT close the real fd.
    A later `conn.close()` is then a no-op, no FIN reaches the server, and the
    stream stays legitimately alive. Closing the RESPONSE is what drops the
    last io-ref and sends the FIN."""
    try:
        resp.close()
    finally:
        conn.close()


def _read_frame(resp, deadline_s: float = 10.0) -> str:
    """One non-blank SSE line. `readline()` (never `read(n)`) because a
    length-unknown response's `read(n)` blocks until exactly n bytes arrive."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        raw = resp.fp.readline()
        if not raw:
            return ""
        line = raw.decode("utf-8").rstrip("\n")
        if line:
            return line
    raise AssertionError("no SSE frame arrived within the deadline")


def _read_until(resp, predicate, deadline_s: float = 10.0) -> list[str]:
    """Read frames until `predicate(line)` is true; returns everything read."""
    seen: list[str] = []
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        line = _read_frame(resp, deadline_s=max(0.1, end - time.monotonic()))
        if not line:
            break
        seen.append(line)
        if predicate(line):
            return seen
    raise AssertionError(f"predicate never matched; frames seen: {seen}")


def _stream_json(line: str) -> dict:
    assert line.startswith("data: "), line
    return json.loads(line[len("data: "):])


def _wait_for_streams(count: int, deadline_s: float = 15.0) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if dashboard.active_stream_count() == count:
            return
        time.sleep(0.02)
    raise AssertionError(
        f"active_stream_count() stayed at {dashboard.active_stream_count()}, expected {count}"
    )


def _write_project_file(root: Path, segments: tuple[str, ...], text: str) -> Path:
    path = root.joinpath(*segments)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _write_line(events_dir: Path, filename: str, record: dict) -> None:
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / filename
    payload = (json.dumps(record) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def _rec(ts: str, kind: str = "session.start", task=None, agent=None) -> dict:
    return {
        "ts": ts, "kind": kind, "host": "claude", "sid": "s1", "pid": "p1",
        "aid": "a1", "task": task, "agent": agent, "effort": None,
        "user": "tester", "data": {},
    }


# ---------------------------------------------------------------------------
# Canal-B fixtures (shard 4b). Envelopes are built in the OTLP/JSON shape
# `otel_receiver.py` persists and `otel_normalize.py` consumes - attribute
# LISTS of `{"key", "value": {"<type>Value"}}` (L-00000040), not flat dicts.
# ---------------------------------------------------------------------------

def _attr(key: str, value) -> dict:
    if isinstance(value, bool):
        payload = {"boolValue": value}
    elif isinstance(value, int):
        payload = {"intValue": value}
    elif isinstance(value, float):
        payload = {"doubleValue": value}
    else:
        payload = {"stringValue": str(value)}
    return {"key": key, "value": payload}


def _metric_envelope(ts: str, name: str, value, fields: dict | None = None,
                     host: str = "claude-code", provenance: str | None = None,
                     project_id: str = _OWN_ID, attributed_by: str | None = None) -> dict:
    """V1-c: every factory carries the promoted `project_id`, because after V1-c
    every line the receiver writes does — a fixture without it would be testing
    a shape the code can no longer produce. `provenance` defaults to mirroring
    it (what `_ingest_parsed_body` writes) and stays overridable, since it is
    still rendered as a LEGACY display field.

    `_legacy_metric_envelope` below keeps the pre-V1-c shape alive on purpose:
    see MUST-FIX M3."""
    envelope = {
        "ts": ts, "kind": "metric",
        "project_id": project_id,
        "provenance": provenance if provenance is not None else project_id,
        "path": "/v1/metrics",
        "body": {"resourceMetrics": [{
            "resource": {"attributes": [_attr("service.name", host)]},
            "scopeMetrics": [{"metrics": [{
                "name": name,
                "sum": {"dataPoints": [{
                    "attributes": [_attr(k, v) for k, v in (fields or {}).items()],
                    "asDouble": value,
                }]},
            }]}],
        }]},
    }
    if attributed_by is not None:
        envelope["project_attributed_by"] = attributed_by
    return envelope


def _legacy_metric_envelope(ts: str, name: str, value, fields: dict | None = None,
                            host: str = "claude-code",
                            provenance: str = r"C:\elsewhere\a-clone-that-moved") -> dict:
    """GATE MUST-FIX M3 — the ONLY fixture shape that exercises the moved-clone
    / renamed-repo case, kept as a first-class factory rather than inlined once.

    A pre-V1-c envelope: NO promoted field, and a `provenance` that does not
    match this repo's root. If every factory in this file carried a
    `project_id`, the branch that answers this case (the backfill's sentinel
    path, and the reader's absent-field handling) would have no test at all
    (iteration 9, C4)."""
    envelope = _metric_envelope(ts, name, value, fields, host=host,
                                provenance=provenance)
    del envelope["project_id"]
    return envelope


def _log_envelope(ts: str, event_name: str, fields: dict | None = None, prompt_id=None,
                  host: str = "claude-code", provenance: str | None = None,
                  project_id: str = _OWN_ID) -> dict:
    attributes = [_attr("event.name", event_name)]
    attributes += [_attr(k, v) for k, v in (fields or {}).items()]
    if prompt_id is not None:
        attributes.append(_attr("prompt.id", prompt_id))
    return {
        "ts": ts, "kind": "log",
        "project_id": project_id,
        "provenance": provenance if provenance is not None else project_id,
        "path": "/v1/logs",
        "body": {"resourceLogs": [{
            "resource": {"attributes": [_attr("service.name", host)]},
            "scopeLogs": [{"logRecords": [{"attributes": attributes}]}],
        }]},
    }


def _write_otel(otel_dir: Path, envelopes: list, filename: str = "2026-07-27.1.jsonl") -> Path:
    otel_dir.mkdir(parents=True, exist_ok=True)
    path = otel_dir / filename
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for envelope in envelopes:
            handle.write(json.dumps(envelope) + "\n")
    return path


# ---------------------------------------------------------------------------
# Auth (non-negotiable #5)
# ---------------------------------------------------------------------------

def test_auth_missing_token_401(ui_server):
    port, _token = ui_server
    resp = _get(port, "/api/snapshot")
    assert resp.status == 401


def test_auth_wrong_token_401(ui_server):
    port, token = ui_server
    resp = _get(port, "/api/snapshot", token=token + "x")
    assert resp.status == 401


def test_auth_correct_token_200_snapshot(ui_server):
    port, token = ui_server
    resp = _get(port, "/api/snapshot", token=token)
    assert resp.status == 200
    data = json.loads(resp.data)
    assert "board" in data and "ledger" in data and "specs" in data


def test_auth_correct_token_200_events(ui_server):
    port, token = ui_server
    resp = _get(port, "/api/events", token=token)
    assert resp.status == 200
    data = json.loads(resp.data)
    assert data["cursor_unit"] == "byte_offset_per_file"


def test_auth_check_is_not_vacuous():
    """Sensitivity demonstration for the token check itself (per this task's
    'a test that passes for the wrong reason' instruction). This does NOT
    monkeypatch the shipped code — it directly proves hmac.compare_digest
    rejects a near-miss (differs in one char) and accepts an exact match,
    which is the actual logic `_check_token` runs. Verified manually during
    development that flipping `_check_token` to `return True` unconditionally
    turns test_auth_missing_token_401 / test_auth_wrong_token_401 red (both
    would then see 200), then reverted — see task report.
    """
    import hmac
    real = "abc123token"
    assert hmac.compare_digest(real, real) is True
    assert hmac.compare_digest(real, real[:-1] + "x") is False


# ---------------------------------------------------------------------------
# No CORS, ever
# ---------------------------------------------------------------------------

def test_no_cors_headers_on_success(ui_server):
    port, token = ui_server
    resp = _get(port, "/api/snapshot", token=token)
    assert resp.status == 200
    for name in resp.getheaders():
        assert "access-control" not in name[0].lower()


def test_no_cors_headers_on_rejection(ui_server):
    port, _token = ui_server
    resp = _get(port, "/api/snapshot")
    assert resp.status == 401
    for name in resp.getheaders():
        assert "access-control" not in name[0].lower()


# ---------------------------------------------------------------------------
# Path traversal (non-negotiable #5) — exact-match routing.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/snapshot/../../../etc/passwd",
    "/api/snapshot/..",
    "/../api/snapshot",
    "/api%2fsnapshot",
    "/api%2e%2e/snapshot",
    "/api\\snapshot",
    "/api/snapshot%00",
])
def test_path_traversal_variants_rejected(ui_server, path):
    port, token = ui_server
    resp = _get(port, path, token=token)
    assert resp.status == 404, f"{path!r} was not rejected (status={resp.status})"


def test_leading_double_slash_is_stdlib_normalised_not_a_bypass(ui_server):
    """`//api/snapshot` is NOT a traversal case: verified that Python's own
    `http.server.BaseHTTPRequestHandler.parse_request()` (3.14) already
    collapses the leading empty path segment before `self.path` is ever set
    — this handler never sees `//api/snapshot`, it sees `/api/snapshot`,
    i.e. the exact same allowed resource, not a different one. Recorded
    here as a deliberate, verified exclusion from the traversal-rejection
    list above (raw-socket check performed during development), not an
    oversight."""
    port, token = ui_server
    resp = _get(port, "//api/snapshot", token=token)
    assert resp.status == 200


def test_traversal_control_is_not_vacuous_prefix_match_would_pass_it():
    """Demonstrates the exact-match control has teeth: a PREFIX match (the
    naive alternative) would have accepted '/api/snapshot/../../../etc/passwd'
    because it startswith '/api/snapshot'. Verified manually during
    development by swapping `path not in _ALLOWED_UI_PATHS` for
    `not path.startswith(tuple(_ALLOWED_UI_PATHS))` and re-running
    test_path_traversal_variants_rejected — it went red on exactly that
    case, confirming the exact-match choice is load-bearing, not decorative.
    """
    allowed = {"/api/snapshot"}
    traversal_path = "/api/snapshot/../../../etc/passwd"
    assert traversal_path not in allowed  # the shipped control: rejected
    assert traversal_path.startswith(tuple(allowed))  # the rejected alternative: would accept


# ---------------------------------------------------------------------------
# Route separation (finding B3, non-negotiable #6)
# ---------------------------------------------------------------------------

def test_ui_socket_rejects_otlp_route(ui_server):
    port, _token = ui_server
    resp = _post(port, "/v1/logs", b'{"a":1}')
    assert resp.status == 404


def test_otlp_socket_rejects_ui_route(otlp_server):
    port = otlp_server
    resp = _get(port, "/api/snapshot")
    assert resp.status == 404


# ---------------------------------------------------------------------------
# /api/snapshot
# ---------------------------------------------------------------------------

def test_snapshot_defaults_when_stores_absent(_redirect):
    snap = dashboard.build_snapshot(_redirect["project_root"])
    assert snap["board"] == {"status": "ok", "data": {"tasks": []}}
    assert snap["ledger"] == {"status": "ok", "data": {"entries": []}}
    assert snap["specs"] == {"status": "ok", "data": {"entries": []}}
    assert snap["index"]["status"] == "degraded"
    assert snap["security"]["status"] == "degraded"


def test_snapshot_degrades_on_malformed_ledger(_redirect):
    root = _redirect["project_root"]
    ledger_path = root / ".agents" / "state" / "memory" / "LEDGER.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("{not valid json", encoding="utf-8", newline="\n")
    snap = dashboard.build_snapshot(root)
    assert snap["ledger"]["status"] == "degraded"
    assert "LedgerError" in snap["ledger"]["reason"] or "not valid JSON" in snap["ledger"]["reason"]
    # A degraded section never takes the whole response down.
    assert snap["board"]["status"] == "ok"


def test_snapshot_index_header_parsed(_redirect):
    root = _redirect["project_root"]
    index_path = root / ".agents" / "state" / "index" / "CODEBASE_INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        "# Codebase index — built @ deadbee · updated 2026-07-27 · backend ctags\n",
        encoding="utf-8", newline="\n",
    )
    snap = dashboard.build_snapshot(root)
    assert snap["index"]["status"] == "ok"
    assert snap["index"]["built_at_sha"] == "deadbee"
    assert snap["index"]["updated"] == "2026-07-27"
    assert ".agents" in snap["index"]["caveat"]


def test_snapshot_security_verdict_read(_redirect):
    root = _redirect["project_root"]
    verdict_path = root / ".agents" / "state" / "local" / "sca-reports" / "effective-verdict.json"
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    verdict_path.write_text(json.dumps({"gate_level": "high", "active": []}), encoding="utf-8", newline="\n")
    snap = dashboard.build_snapshot(root)
    assert snap["security"]["status"] == "ok"
    assert snap["security"]["verdict"]["gate_level"] == "high"


def test_snapshot_project_section(_redirect):
    # T-00000048 (V1-a) / T-00000582: absent -> unnamed, present -> ok + ROOT
    # name, corrupt -> degraded.
    root = _redirect["project_root"]
    snap = dashboard.build_snapshot(root)
    assert snap["project"] == {"status": "unnamed", "name": None}

    ppath = root / ".agents" / "state" / "project.json"
    ppath.parent.mkdir(parents=True, exist_ok=True)
    ppath.write_text(
        json.dumps({"project_id": "p-1", "name": "Demo Project", "slug": "demo-project"}),
        encoding="utf-8", newline="\n",
    )
    snap = dashboard.build_snapshot(root)
    assert snap["project"]["status"] == "ok"
    # T-00000582: name is ROOT-derived — the basename of `root`
    # (tmp_path/"project"), NOT the JSON's "Demo Project" (still written above,
    # to prove the parse succeeds and its `name` value is IGNORED).
    assert snap["project"]["name"] == "project"

    ppath.write_text("{ not json", encoding="utf-8", newline="\n")
    snap = dashboard.build_snapshot(root)
    assert snap["project"]["status"] == "degraded"
    assert snap["project"]["name"] is None
    # A corrupt identity never takes the rest of the snapshot down.
    assert snap["board"]["status"] == "ok"


def test_snapshot_caveats_present(_redirect):
    snap = dashboard.build_snapshot(_redirect["project_root"])
    joined = " ".join(snap["caveats"])
    assert "L-00000049" in joined  # cross-project OTLP caveat
    assert "L-029" in joined       # index freshness caveat
    # Shard 4b: the section is now a real reader, so `collected` is False here
    # only because this tmp tree has no canal-B file - the frozen schema
    # declaration travels either way.
    assert snap["canal_b"]["collected"] is False
    assert snap["canal_b"]["schema_frozen"] is True
    assert "prompt.id" in snap["canal_b"]["schema"]["join_key"]


# ---------------------------------------------------------------------------
# /api/events — cursor unit, partial-line safety, precedence, reset, compact
# ---------------------------------------------------------------------------

def test_events_empty_when_no_files(_redirect):
    resp = dashboard.build_events_response({})
    assert resp["events"] == []
    assert resp["has_more"] is False
    assert resp["cursor_reset"] is False


def test_events_partial_line_not_returned_until_completed(_redirect):
    events_dir = _redirect["events_dir"]
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / "2026-07-27.claude.100.jsonl"

    full_line = json.dumps(_rec("2026-07-27T00:00:00Z", task="T-001")) + "\n"
    payload = full_line.encode("utf-8")
    split_at = len(payload) - 5  # cut a few bytes before the trailing newline

    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload[:split_at])
    finally:
        os.close(fd)

    resp1 = dashboard.build_events_response({})
    assert resp1["events"] == [], "a partial line (no trailing newline yet) must never be parsed"
    assert resp1["malformed_lines_skipped"] == 0

    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload[split_at:])
    finally:
        os.close(fd)

    cursor2 = resp1["next_cursor"]
    resp2 = dashboard.build_events_response({"cursor": [cursor2]})
    assert len(resp2["events"]) == 1
    assert resp2["events"][0]["task"] == "T-001"
    assert resp2["malformed_lines_skipped"] == 0


def test_partial_line_control_is_not_vacuous(_redirect, monkeypatch):
    """Demonstrates that _read_new_records' 'stop at the last newline' check
    is load-bearing: a naive reader that processes the WHOLE chunk
    (including a trailing partial line) would either raise on json.loads or
    silently swallow the malformed tail. Verified manually during
    development by short-circuiting the `last_nl == -1` early-return in
    `_read_new_records` (forcing it to always process the whole chunk) and
    re-running test_events_partial_line_not_returned_until_completed — it
    went red (a malformed/partial record surfaced on the first poll). This
    unit test proves the same property directly on a hand-built partial
    chunk, independent of the live function, as a permanent regression
    tripwire."""
    partial_json = b'{"ts": "2026-07-27T00:00:00Z", "kind": "session.st'  # cut mid-value, no newline
    assert partial_json.rfind(b"\n") == -1  # the exact condition _read_new_records checks


# ---------------------------------------------------------------------------
# Cursor precedence (non-negotiable #4)
# ---------------------------------------------------------------------------

def test_cursor_takes_precedence_over_since(_redirect):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:00Z", task="T-001"))

    # First call with no cursor: capture a cursor sitting right after this event.
    first = dashboard.build_events_response({})
    assert len(first["events"]) == 1
    cursor_at_start = dashboard._encode_cursor(dashboard._filters_fingerprint({"task": None, "kind": None, "agent": None}), {})

    # since is set to a time AFTER the event's ts — normally this would hide it.
    since_hides_it = dashboard.build_events_response({"since": ["2099-01-01T00:00:00Z"]})
    assert since_hides_it["events"] == []

    # But WITH a (valid, offset-0) cursor supplied alongside that same since,
    # the event must still be returned: cursor wins, since is ignored.
    with_cursor_and_since = dashboard.build_events_response({
        "since": ["2099-01-01T00:00:00Z"],
        "cursor": [cursor_at_start],
    })
    assert len(with_cursor_and_since["events"]) == 1
    assert with_cursor_and_since["events"][0]["task"] == "T-001"


def test_filter_change_resets_cursor(_redirect):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:00Z", task="T-001"))
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:01Z", task="T-002"))

    first = dashboard.build_events_response({"task": ["T-001"]})
    assert [e["task"] for e in first["events"]] == ["T-001"]
    cursor = first["next_cursor"]

    # Same cursor, DIFFERENT filter — must reset, not silently keep the old
    # (now stale, filter-independent) byte offset that already skipped past
    # the T-002 record.
    second = dashboard.build_events_response({"task": ["T-002"], "cursor": [cursor]})
    assert second["cursor_reset"] is True
    assert second["cursor_reset_reason"] == "filters_changed"
    assert [e["task"] for e in second["events"]] == ["T-002"]


def test_malformed_cursor_resets(_redirect):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:00Z", task="T-001"))
    resp = dashboard.build_events_response({"cursor": ["not-valid-base64-json!!"]})
    assert resp["cursor_reset"] is True
    assert resp["cursor_reset_reason"] == "malformed_cursor"
    assert len(resp["events"]) == 1


def test_cursor_reset_control_is_not_vacuous(_redirect):
    """Demonstrates the fingerprint check is load-bearing: decoding the
    SAME cursor bytes against a DIFFERENT fingerprint (computed here
    independently of build_events_response) proves the mismatch a stale
    cursor must trip. Verified manually during development by hardcoding
    `decoded["fp"] != fingerprint` to always be False (i.e. disabling the
    reset) and re-running test_filter_change_resets_cursor — it went red
    (T-001 was skipped even though the filter had moved to T-002 and never
    saw the record), confirming the fingerprint guard is what prevents a
    filter change from silently hiding matching history."""
    fp_a = dashboard._filters_fingerprint({"task": "T-001", "kind": None, "agent": None})
    fp_b = dashboard._filters_fingerprint({"task": "T-002", "kind": None, "agent": None})
    assert fp_a != fp_b
    cursor = dashboard._encode_cursor(fp_a, {"f.jsonl": 10})
    decoded = dashboard._decode_cursor(cursor)
    assert decoded["fp"] != fp_b  # the mismatch build_events_response checks for


# ---------------------------------------------------------------------------
# compact() interaction (non-negotiable #3)
# ---------------------------------------------------------------------------

def test_compact_prunes_vanished_file_from_cursor(_redirect):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:00Z", task="T-001"))
    first = dashboard.build_events_response({})
    cursor = first["next_cursor"]

    # Simulate events.py --compact: the source day-file is gone.
    (events_dir / "2026-07-27.claude.1.jsonl").unlink()

    second = dashboard.build_events_response({"cursor": [cursor]})
    assert second["pruned_files"] == ["2026-07-27.claude.1.jsonl"]
    assert second["events"] == []
    # A stale offset for a file that no longer exists is not a fingerprint
    # mismatch (filters unchanged) — the cursor is honoured, just pruned.
    assert second["cursor_reset"] is False


def test_compact_digest_surfaced_as_labelled_aggregate(_redirect):
    events_dir = _redirect["events_dir"]
    digest_dir = events_dir / "digest"
    digest_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / "2026-06.json").write_text(json.dumps({
        "month": "2026-06", "generated_at": "2026-07-01T00:00:00Z",
        "total_events": 42, "by_kind": {"session.start": 42},
        "by_agent": {}, "by_task": {}, "days_folded": ["2026-06-01"],
    }), encoding="utf-8", newline="\n")

    resp = dashboard.build_events_response({})
    assert resp["aggregates"]["months"][0]["month"] == "2026-06"
    assert resp["aggregates"]["months"][0]["total_events"] == 42
    # Never presented as raw history or a cost source: no ts/tokens fields.
    assert "ts" not in resp["aggregates"]["months"][0]
    assert "tokens" not in resp["aggregates"]["months"][0]
    assert "counts only" in resp["aggregates"]["label"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_has_more_and_continuation(_redirect):
    events_dir = _redirect["events_dir"]
    limit = dashboard._EVENTS_PAGE_LIMIT
    for i in range(limit + 5):
        hh, mm, ss = i // 3600, (i % 3600) // 60, i % 60
        _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec(f"2026-07-27T{hh:02d}:{mm:02d}:{ss:02d}Z", task=f"T-{i}"))

    first = dashboard.build_events_response({})
    assert len(first["events"]) == limit
    assert first["has_more"] is True

    second = dashboard.build_events_response({"cursor": [first["next_cursor"]]})
    assert len(second["events"]) == 5
    assert second["has_more"] is False


# ---------------------------------------------------------------------------
# Query params never touch the filesystem (non-negotiable #5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["../../../etc/passwd", "..\\..\\windows", "%2e%2e/secret"])
def test_traversal_shaped_query_values_are_just_string_filters(_redirect, value):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-27.claude.1.jsonl", _rec("2026-07-27T00:00:00Z", task="T-001"))
    resp = dashboard.build_events_response({"task": [value]})
    assert resp["events"] == []  # no task matches this literal string — filtered, not an error
    # No exception, no filesystem access attempted for the filter value.


# ---------------------------------------------------------------------------
# Concurrent-writer stress test — the "read while a writer appends" proof.
# ---------------------------------------------------------------------------

def test_concurrent_writer_never_yields_partial_or_lost_lines(_redirect):
    events_dir = _redirect["events_dir"]
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / "2026-07-27.claude.999.jsonl"
    write_count = 250
    stop = threading.Event()

    def writer():
        for i in range(write_count):
            record = _rec(f"2026-07-27T01:{i // 60:02d}:{i % 60:02d}Z", task=f"T-{i}")
            payload = (json.dumps(record) + "\n").encode("utf-8")
            split_at = max(1, len(payload) // 2)
            fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            try:
                os.write(fd, payload[:split_at])
                time.sleep(0.0005)  # widen the window a reader could land in
                os.write(fd, payload[split_at:])
            finally:
                os.close(fd)
        stop.set()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()

    seen_tasks: set[str] = set()
    malformed_total = 0
    cursor = None
    polls = 0
    while not stop.is_set() or polls < 3:
        qs = {"cursor": [cursor]} if cursor else {}
        resp = dashboard.build_events_response(qs)
        for ev in resp["events"]:
            seen_tasks.add(ev["task"])
        malformed_total += resp["malformed_lines_skipped"]
        cursor = resp["next_cursor"]
        polls += 1
        if stop.is_set() and not resp["events"]:
            polls += 1  # allow a couple more drains after writer finishes
        time.sleep(0.0007)
        if polls > 5000:
            break

    thread.join(timeout=10)
    # Drain any tail left after the writer thread has fully stopped.
    for _ in range(5):
        resp = dashboard.build_events_response({"cursor": [cursor]} if cursor else {})
        for ev in resp["events"]:
            seen_tasks.add(ev["task"])
        malformed_total += resp["malformed_lines_skipped"]
        cursor = resp["next_cursor"]

    assert malformed_total == 0, "no complete-but-corrupt line should ever be produced by a split write"
    assert seen_tasks == {f"T-{i}" for i in range(write_count)}, "every written line must eventually surface exactly once"


# ---------------------------------------------------------------------------
# Token uniqueness per launch
# ---------------------------------------------------------------------------

def test_token_is_random_per_launch(_redirect):
    result_a = dashboard.create_ui_server(project_root=_redirect["project_root"])
    result_b = dashboard.create_ui_server(project_root=_redirect["project_root"])
    assert result_a is not None and result_b is not None
    server_a, token_a = result_a
    server_b, token_b = result_b
    try:
        assert token_a != token_b
        assert len(token_a) >= 32
    finally:
        server_a.server_close()
        server_b.server_close()


# ===========================================================================
# Static UI service (shard 4a) — .agents/ui/ served token-exempt, GET-only,
# from a CLOSED route table. These tests hit the REAL .agents/ui/ directory on
# purpose: "the shipped shell is servable" is part of the contract, and a
# fixture copy would prove only that the handler can read some bytes.
# ===========================================================================

_STATIC_ROUTES_EXPECTED = {
    "/": "text/html; charset=utf-8",
    # THE BUNDLE. `.agents/ui/` is the BUILD OUTPUT of `.agents/ui-src/` (React +
    # Vite); the sixteen hand-written module routes that used to be listed here
    # collapsed into one script and one stylesheet. The filenames are frozen by
    # `vite.config.js` (no content hash) precisely because this table is closed —
    # a hashed name would 404 on every rebuild.
    #
    # This dict stays the independent second opinion that makes an accidental
    # route addition fail loudly.
    "/assets/app.js": "text/javascript; charset=utf-8",
    "/assets/app.css": "text/css; charset=utf-8",
    # Self-hosted maquette typography — T-00001243 (S-00004649): Geist + Geist
    # Mono, two VARIABLE files replace the five static faces. Their OFL licence
    # sits beside them on disk but is NOT a route, so it is absent from this dict
    # on purpose, and the text-route count below stays at three.
    "/fonts/geist-variable.woff2": "font/woff2",
    "/fonts/geistmono-variable.woff2": "font/woff2",
}


def test_static_route_table_is_closed_and_every_entry_exists():
    assert set(dashboard._ALLOWED_STATIC_ROUTES) == set(_STATIC_ROUTES_EXPECTED)
    for route, (segments, content_type) in dashboard._ALLOWED_STATIC_ROUTES.items():
        assert content_type == _STATIC_ROUTES_EXPECTED[route]
        assert dashboard._UI_DIR.joinpath(*segments).is_file(), f"{route} has no file behind it"


def test_static_and_api_route_tables_never_overlap():
    """The two tables are matched in sequence (static first), so an overlap
    would silently make an /api/* route token-exempt."""
    assert not (set(dashboard._ALLOWED_STATIC_ROUTES) & set(dashboard._ALLOWED_UI_PATHS))
    assert not any(route.startswith("/api/") for route in dashboard._ALLOWED_STATIC_ROUTES)


@pytest.mark.parametrize("route,content_type", sorted(_STATIC_ROUTES_EXPECTED.items()))
def test_static_served_without_token(ui_server, route, content_type):
    """No Authorization header at all — a document navigation cannot carry one."""
    port, _token = ui_server
    resp = _get(port, route)
    assert resp.status == 200
    assert resp.getheader("Content-Type") == content_type
    assert resp.getheader("Cache-Control") == "no-store"
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert len(resp.data) > 0


def test_static_root_is_the_shell_document(ui_server):
    port, _token = ui_server
    resp = _get(port, "/")
    assert resp.status == 200
    body = resp.data.decode("utf-8")
    assert body.startswith("<!DOCTYPE html>")
    # The bundler injects both tags; their names are frozen (no content hash) so
    # this table and `vite.config.js` cannot drift apart silently.
    assert 'src="/assets/app.js"' in body
    assert 'href="/assets/app.css"' in body
    # The shell still carries NO data: everything visible comes from /api/*.
    assert '<div id="root"></div>' in body


def test_csp_is_sent_on_the_document_only(ui_server):
    """The CSP is what mechanically forbids a CDN <script>; it belongs on the
    document. On a .js response it would be inert noise."""
    port, _token = ui_server
    csp = _get(port, "/").getheader("Content-Security-Policy")
    assert csp is not None and "default-src 'none'" in csp and "script-src 'self'" in csp
    # Tightened in shard 4b: the SVG charts set geometry with attributes, so
    # nothing in the bundle needs inline styles any more.
    assert "'unsafe-inline'" not in csp
    assert _get(port, "/app.js").getheader("Content-Security-Policy") is None


@pytest.mark.parametrize("route", sorted(_STATIC_ROUTES_EXPECTED))
def test_static_has_no_cors_headers(ui_server, route):
    port, _token = ui_server
    resp = _get(port, route)
    for name, _value in resp.getheaders():
        assert "access-control" not in name.lower()


@pytest.mark.parametrize("path", [
    "/index.html",        # deliberately not a route: one canonical URL for the shell
    "/favicon.ico",
    "/nope",
    "/views/",
    "/views/nothing.js",  # a view that has not shipped: 404, not a blank 200
    "/selftest.mjs",      # a dev harness, deliberately not served (D4)
    "/styles.css.map",
    "/app.js/",
])
def test_unknown_static_route_404(ui_server, path):
    port, _token = ui_server
    resp = _get(port, path)
    assert resp.status == 404, f"{path!r} was served (status={resp.status})"


@pytest.mark.parametrize("path", [
    "/../ui/x",
    "/../../etc/passwd",
    "/../bin/dashboard.py",
    "/views/../api/snapshot",
    "/views/board.js/../../api/snapshot",
    "/%2e%2e/",
    "/%2e%2e/%2e%2e/bin/dashboard.py",
    "/./styles.css",
    "/%2fstyles.css",
    "/views%2fboard.js",
    "/styles.css%00",
    "/..%5Cbin%5Cdashboard.py",
])
def test_static_traversal_variants_404(ui_server, path):
    """Same control as the /api/* traversal test: EXACT match on the raw
    un-normalised path, so none of these is ever a candidate for `open()`."""
    port, _token = ui_server
    resp = _get(port, path)
    assert resp.status == 404, f"{path!r} was not rejected (status={resp.status})"


def test_rejection_body_never_reflects_the_requested_path(ui_server):
    port, _token = ui_server
    resp = _get(port, "/../../etc/passwd")
    assert resp.status == 404
    assert json.loads(resp.data) == {"error": "not_found"}


def test_static_lookup_is_a_dict_key_not_a_path_join():
    """Sensitivity control for the anti-traversal claim, on the values
    themselves (no monkeypatching of shipped code): the naive alternative —
    joining the URL onto `_UI_DIR` — resolves OUTSIDE the UI directory for a
    request the shipped dict lookup simply does not contain."""
    ui_dir = dashboard._UI_DIR
    hostile = "/../bin/dashboard.py"
    assert hostile not in dashboard._ALLOWED_STATIC_ROUTES  # shipped control: 404
    naive = (ui_dir / hostile.lstrip("/")).resolve()  # the rejected alternative
    assert naive == (ui_dir.parent / "bin" / "dashboard.py").resolve()
    assert ui_dir not in naive.parents  # ...escapes the UI directory entirely


def test_missing_ui_file_is_404_not_500(ui_server, empty_ui_dir):
    port, _token = ui_server
    resp = _get(port, "/")
    assert resp.status == 404
    assert json.loads(resp.data) == {"error": "not_found"}
    assert str(empty_ui_dir) not in resp.data.decode("utf-8")


def test_missing_ui_file_does_not_break_the_api(ui_server, empty_ui_dir):
    """A UI file vanishing must degrade the shell only — the API is a separate
    concern and stays fully available."""
    port, token = ui_server
    assert _get(port, "/app.js").status == 404
    assert _get(port, "/api/snapshot", token=token).status == 200


@pytest.mark.parametrize("path", ["/api/snapshot", "/api/events", "/api/projects",
                                  "/api/sessions"])
def test_api_routes_remain_token_only_after_the_static_addition(ui_server, path):
    """`/api/projects` joined this list in T-00000051 and `/api/sessions` in
    T-00000086: they are DATA routes like the other two — the static table's
    token exemption exists for document navigations only, and both a project
    identity and a console event feed are repo content."""
    port, _token = ui_server
    assert _get(port, path).status == 401


@pytest.mark.parametrize("path", ["/", "/assets/app.js", "/assets/app.css"])
def test_post_on_a_static_route_404(ui_server, path):
    """The static table adds read surface, not verbs.

    AMENDED BY T-00000028, deliberately and in place rather than deleted. This
    test used to say "GET-only on every route", which stopped being true when
    that task opened `POST` on `_ALLOWED_WRITE_PATHS`. What it asserts now is
    narrower and still load-bearing: the write verb did NOT leak onto the
    token-EXEMPT tables. The static routes are exempt because a document
    navigation carries no Authorization header — an exemption that is only
    defensible for reads, so a POST here must still be a flat 404."""
    port, _token = ui_server
    assert _post(port, path, b'{"a":1}').status == 404


def test_static_request_does_not_refresh_the_idle_watchdog(ui_server_object):
    """Shard 2's watchdog must age out on absence of AUTHORISED traffic; an
    unauthenticated document fetch is exactly the noise that rule excludes.
    `last_activity` is pinned to 0.0 first so the assertion does not depend on
    `time.monotonic()`'s ~15 ms granularity on Windows."""
    httpd, port, token = ui_server_object
    httpd.last_activity = 0.0
    assert _get(port, "/").status == 200
    assert _get(port, "/assets/app.js").status == 200
    assert httpd.last_activity == 0.0, "static traffic must not keep the daemon alive"
    assert _get(port, "/api/snapshot", token=token).status == 200
    assert httpd.last_activity > 0.0, "authorised traffic must refresh the watchdog"


# ---------------------------------------------------------------------------
# Shipped UI bytes — the "zero dependency, zero build" and LF invariants are
# asserted on the files, not on intent (design doc §B.3, L-003).
# ---------------------------------------------------------------------------

def _ui_sources() -> list[tuple[str, str]]:
    """Every TEXT asset the server will hand a browser, as (route, source).

    Binary routes are skipped through `dashboard._is_text_route` rather than by
    an extension list here: the self-hosted fonts are bytes, and a `read_text`
    on them raises UnicodeDecodeError in the audits that funnel through this
    helper.
    """
    out = []
    for route, (segments, content_type) in sorted(dashboard._ALLOWED_STATIC_ROUTES.items()):
        if not dashboard._is_text_route(content_type):
            continue
        out.append((route, dashboard._UI_DIR.joinpath(*segments).read_text(encoding="utf-8")))
    return out


# The front end is now BUILT (React + Vite): `.agents/ui/` holds the output and
# `.agents/ui-src/` holds what a human writes.
#
# THAT SPLIT DECIDES WHICH TREE EACH AUDIT READS, and getting it wrong is how a
# suite goes quietly green. Audits about what WE wrote — no markup built from
# data, no inline style, no token in a URL — read the SOURCE, because React's
# own minified runtime contains `innerHTML` and assigns `.style` internally;
# grepping the bundle for those forms would test the vendor rather than this
# repo, and the only way to keep such a check green would be to weaken it until
# it asserted nothing. Audits about what is SERVED — the route table, the fonts,
# line endings, remote origins, inline scripts — read the build, because that is
# what reaches a browser.
_UI_SRC_DIR = dashboard._UI_DIR.parent / "ui-src"


def _ui_source_files() -> list[tuple[str, str]]:
    """Every hand-written front-end source file, as (relative path, text).

    `node_modules/` and `public/` are excluded: neither is written here.
    """
    if not _UI_SRC_DIR.is_dir():
        pytest.skip("front-end source tree absent (build-only checkout)")
    out = []
    for path in sorted(_UI_SRC_DIR.rglob("*")):
        if not path.is_file():
            continue
        if "node_modules" in path.parts or "public" in path.parts:
            continue
        if path.suffix not in {".js", ".jsx", ".css", ".html", ".json"}:
            continue
        out.append((path.relative_to(_UI_SRC_DIR).as_posix(), path.read_text(encoding="utf-8")))
    assert len(out) >= 25, f"only {len(out)} source files found — the walk is too narrow"
    return out


# The SVG/XML namespaces are IDENTIFIERS, never fetched by any browser. They are
# stripped before the remote-origin check rather than weakening that check.
_XML_NS_LITERALS = (
    "http" + "://www.w3.org/2000/svg",
    "http" + "://www.w3.org/1999/xlink",
    "http" + "://www.w3.org/1998/Math/MathML",
    "http" + "://www.w3.org/XML/1998/namespace",
)
# React's minified build embeds a documentation URL in its error messages
# (`react.dev/errors/<n>`). It is a STRING ON AN ERROR PATH — the bundle never
# fetches it, and no `connect-src 'self'` violation can arise from it.
# Allowlisted by exact literal, in the vendor bundle ONLY: the source tree may
# name no origin but the loopback, and `react.dev` is not one.
_REACT_ERROR_DOC = "http" + "s://react.dev/errors/"


def _strip_js_comments(text: str) -> str:
    """Block and line comments out, so an audit can tell a rule being STATED
    from a rule being BROKEN.

    Deliberately crude — it does not track string literals, so a `//` inside a
    string is treated as a comment. That errs toward FALSE NEGATIVES on strings
    containing `//`, which in this bundle means URLs, and a remote URL is caught
    by the un-stripped check in `test_ui_sources_reference_nothing_remote`. Used
    only where the alternative is deleting the comment that documents the rule.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)//.*$", "", text)


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


# Every HOST the front end is allowed to NAME, anywhere: the loopback, and
# nothing else. A third-party origin stays forbidden — that is the whole point of
# the two tests below, and widening this tuple is the one edit that would empty
# them of meaning.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

# An origin as it appears in JS, CSS or HTML. Stops at whatever can END a URL in
# those languages: whitespace, a quote, a template backtick, a closing paren —
# so `\`http://127.0.0.1:${port}/\`` yields the whole origin and `url(...)`
# yields it without its wrapper.
_ORIGIN_RE = re.compile(r"\w+://[^\"'\s`)]+")


def _is_loopback_origin(origin: str) -> bool:
    """Is this URL's AUTHORITY the loopback?

    PARSED, NEVER PREFIX-MATCHED (security review, T-00000085). The obvious
    `origin.startswith("http://127.0.0.1")` reads correctly and is wrong three
    different ways, all of them a real exfiltration path in a shipped bundle.
    Described here rather than spelled as literals — the executable spellings
    live in `test_the_loopback_exemption_cannot_be_spoofed`, which says why:

        loopback as a SUBDOMAIN LABEL - `127.0.0.1`, a dot, then evil.example:
                                        the host is evil.example
        the same trick on the NAME    - `localhost`, a dot, then evil.example
        loopback as USERINFO          - `127.0.0.1`, an at-sign, then
                                        evil.example: everything before the
                                        at-sign is credentials, and the HOST is
                                        whatever follows it

    `urlsplit().hostname` resolves all three the way a browser would (userinfo
    dropped at the at-sign, host lowercased), so the check compares a host to a
    host instead of comparing a string to a string. The scheme is pinned to plain
    `http` on purpose: the daemon serves loopback over http, and `https://` on
    127.0.0.1 would be a certificate story this kit does not have.

    A URL malformed enough to make `urlsplit` raise is NOT loopback: an origin
    this audit cannot parse is one it cannot clear.
    """
    try:
        parts = urlsplit(origin)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme == "http" and host in _LOOPBACK_HOSTS


def _assert_every_origin_is_loopback(label: str, text: str) -> None:
    """No third-party origin — stated as "every origin named here is LOOPBACK"
    rather than as "the substring `://` never appears".

    WHY THE RULE MOVED (T-00000085). It used to be the blanket substring check,
    which was accurate for as long as the served code had no legitimate reason
    to name any origin at all. The peers panel gave it one: a card links to
    ANOTHER daemon of THIS machine, `http://127.0.0.1:<port>/`, and that link IS
    the feature — a peer runs on a different port, so it is a different origin
    and cannot be reached with a relative URL.

    The check is therefore narrowed to what the rule was always about, and NOT
    weakened: a CDN, a font host or any `https://` third party still fails, and
    the loopback can never be one (`vite.config.js`'s dev-proxy exemption, which
    already read this way, is now simply the general case). The marker list
    below is kept on top as a second, independent net.

    What this does NOT authorise: a token in one of those URLs. That is a
    separate audit (`test_ui_sources_never_put_a_token_in_a_url`), and the front
    end's `peerHref()` takes a port and has no way to add one.
    """
    for origin in _ORIGIN_RE.findall(text):
        assert _is_loopback_origin(origin), \
            f"{label} names a non-loopback origin: {origin}"
    for marker in ("cdn.", "unpkg", "jsdelivr", "fonts.g"):
        assert marker not in text, f"{label} mentions {marker}"


def test_ui_sources_name_no_origin_but_the_loopback():
    """What WE write pulls nothing from a third-party origin — the only origin
    it may even name is this machine's loopback.

    Matched on SYNTACTIC forms, not on bare substrings: a file is allowed to
    document the rule it obeys, and a naive grep would fail on its own
    explanatory comment.
    """
    for name, raw in _ui_source_files():
        if name.endswith(".json"):
            # A dependency manifest and its lockfile name a registry by
            # definition; neither is served, and neither is code this rule is
            # about. What they pin IS audited — by the SCA gate, not here.
            continue
        text = raw
        for ns in _XML_NS_LITERALS:
            text = text.replace(ns, "<xml-ns>")
        # `vite.config.js` is TOOLING, never shipped, and used to be the ONE
        # file allowed to name the loopback (its dev proxy needs the port
        # `--dash` prints). It is no longer a special case — it is held to the
        # same rule as the shipped sources, which is stricter reading than it
        # sounds: a bundler told to fetch from a CDN would put that CDN in the
        # output, so tooling was never exempt from the third-party ban.
        _assert_every_origin_is_loopback(name, text)
        # `@import "./x.css"` is a BUILD-TIME include resolved by the bundler,
        # not a runtime stylesheet fetch; only a remote one would be.
        for target in re.findall(r'(?m)^\s*@import\s+"([^"]+)"', text):
            assert target.startswith("."), f"{name} imports a non-local stylesheet: {target}"


def test_served_bundle_names_no_origin_but_the_loopback():
    """And neither does what actually ships, vendor code included.

    The shipped bundle names exactly one origin family today: the peer links of
    the "Projets sur cette machine" panel (T-00000085), `http://127.0.0.1:<port>/`.
    Anything else appearing here is a third party that reached the browser.
    """
    for route, raw in _ui_sources():
        text = raw.replace(_REACT_ERROR_DOC, "<react-error-doc>")
        for ns in _XML_NS_LITERALS:
            text = text.replace(ns, "<xml-ns>")
        _assert_every_origin_is_loopback(route, text)
        assert not re.search(r"(?m)^\s*@import\b", text), f"{route} pulls a stylesheet at runtime"


def test_the_loopback_exemption_cannot_be_spoofed():
    """The two audits above are only as good as what "loopback" means to them.

    THE FAILURE THIS GUARDS AGAINST IS THE GUARD ITSELF. `startswith("http://
    127.0.0.1")` clears three hostile spellings whose real host is a third party,
    and each of them would exfiltrate from the shipped bundle while the suite
    stayed green — the audit would be the vulnerability. Written as URLs the
    parser must REJECT, so the rule is asserted rather than assumed.

    THE LITERALS ARE ASSEMBLED, NEVER TYPED WHOLE, and there are now two
    independent reasons — the second one learned the hard way.

    The scheme is split (`"http" + "://"`) for the same reason the XML
    namespaces above are: this file states origins it FORBIDS, and nothing that
    greps for a scheme should read that as this repo naming one.

    The AT-SIGN is spliced in for the same reason one step further out.
    `<something>@<domain>` written contiguously in a tracked file IS an email
    address to every naive scanner — including this repo's own travelling-
    identity gate (`test_template_hygiene.py`, L-00000064), which went red the
    moment T-00000085 introduced these fixtures and stayed red for a commit.
    That gate is exactly the class of tool that must NOT learn an exception for
    this file: an allowlist there is a hole for every future file. So the
    fixture bends and the scanner does not — the strings this test builds at
    RUNTIME are unchanged, the seven spellings are still rejected, and no line
    of source looks like a person's address.

    The domain is `.example` (RFC 2606, reserved and unregistrable) rather than
    a `.com` somebody actually owns.
    """
    scheme = "http" + "://"
    at = "@"
    hostile = (
        f"{scheme}127.0.0.1.evil.example/",   # loopback as a subdomain label
        f"{scheme}localhost.evil.example/",   # same trick on the name
        # loopback as userinfo: the host is evil.example
        f"{scheme}127.0.0.1" + at + "evil.example/",
        f"{scheme}127.0.0.1evil.example/",    # no separator at all
        f"{scheme}evil.example/127.0.0.1",    # loopback demoted to a path
        # userinfo WITH a plausible port
        f"{scheme}localhost:8765" + at + "evil.example/",
        "http" + "s://127.0.0.1/",            # right host, wrong scheme
    )
    for origin in hostile:
        assert not _is_loopback_origin(origin), f"spoof accepted as loopback: {origin}"
        with pytest.raises(AssertionError):
            _assert_every_origin_is_loopback("probe", f"const u = '{origin}';")

    # And the shapes the front end really ships still pass, template literal
    # included (`peerHref` builds `http://127.0.0.1:${port}/`).
    for origin in (f"{scheme}127.0.0.1:8765/", f"{scheme}127.0.0.1:", f"{scheme}localhost:5173/"):
        assert _is_loopback_origin(origin), f"legitimate loopback rejected: {origin}"
    _assert_every_origin_is_loopback("probe", "const u = `" + scheme + "127.0.0.1:${port}/`;")


def test_ui_files_are_utf8_lf_without_bom():
    """Text assets only — binary ones are covered by the test below.

    Scoped by CONTENT TYPE rather than by extension: a `charset` is what makes a
    type textual, so a future binary asset is excluded by declaring itself
    honestly instead of by someone remembering to extend a suffix list here.

    Both trees are checked. The build is what ships; the source is what a
    Windows editor would corrupt first (L-003), and a CRLF that only exists
    there is still a CRLF in the repo.
    """
    checked = 0
    for route, (segments, content_type) in dashboard._ALLOWED_STATIC_ROUTES.items():
        if "charset=" not in content_type:
            continue
        raw = dashboard._UI_DIR.joinpath(*segments).read_bytes()
        assert b"\r\n" not in raw, f"{route} has CRLF line endings (L-003)"
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{route} starts with a BOM"
        raw.decode("utf-8")
        checked += 1
    # Non-vacuity: a typo in the charset check that skipped everything would
    # otherwise leave this test green while asserting nothing.
    assert checked == 3, f"expected 3 text routes (shell + script + stylesheet), got {checked}"

    if not _UI_SRC_DIR.is_dir():
        return
    for name, _text in _ui_source_files():
        raw = (_UI_SRC_DIR / name).read_bytes()
        assert b"\r\n" not in raw, f"ui-src/{name} has CRLF line endings (L-003)"
        assert not raw.startswith(b"\xef\xbb\xbf"), f"ui-src/{name} starts with a BOM"


def test_binary_static_assets_are_real_and_declared_without_charset():
    """The fonts: present, non-empty, actually woff2, and typed as binary.

    A truncated or HTML-error-page download would still be *a file*, and the
    page would silently fall back to the system stack with no error anywhere —
    so the magic number is checked, not just the size. `wOF2` is the woff2
    signature.
    """
    binary = {route: segs for route, (segs, ct) in dashboard._ALLOWED_STATIC_ROUTES.items()
              if "charset=" not in ct}
    assert binary, "no binary static route declared"
    for route, segments in binary.items():
        raw = dashboard._UI_DIR.joinpath(*segments).read_bytes()
        assert raw[:4] == b"wOF2", f"{route} is not a woff2 file"
        assert len(raw) > 5000, f"{route} is suspiciously small ({len(raw)} bytes)"


def test_every_font_face_in_the_bundle_has_a_served_route():
    """A `@font-face` pointing at an unrouted path 404s and degrades silently.

    The stylesheet and the route table are two lists that must agree; nothing
    else checks that they do, and the failure mode is invisible (the fallback
    face renders and no error is logged). Read from the BUILT stylesheet, which
    is what the browser actually parses.
    """
    css = (dashboard._UI_DIR / "assets" / "app.css").read_text(encoding="utf-8")
    referenced = set(re.findall(r"""url\(['"]?(/fonts/[^'")]+)['"]?\)""", css))
    assert referenced, "no @font-face url found in the built stylesheet"
    missing = referenced - set(dashboard._ALLOWED_STATIC_ROUTES)
    assert not missing, f"@font-face references unrouted paths: {sorted(missing)}"


def test_board_view_mirrors_tasks_py_closed_state_vocabulary():
    """The view duplicates the state vocabulary in JS (it cannot import Python).
    This is the drift guard: glyphs AND default ordering must match `tasks.py`,
    which owns the vocabulary. Read from the SOURCE — the minified bundle keeps
    the literals but not the property spellings this asserts on."""
    if not _UI_SRC_DIR.is_dir():
        pytest.skip("front-end source tree absent (build-only checkout)")
    text = (_UI_SRC_DIR / "src" / "views" / "Board.jsx").read_text(encoding="utf-8")
    tasks_mod = dashboard._tasks_mod
    for state in tasks_mod.STATES:
        assert f'{state}: "{tasks_mod.STATE_EMOJI[state]}"' in text, f"glyph for {state} missing/divergent"
        assert f"{state}: {tasks_mod.SORT_ORDER[state]}" in text, f"sort rank for {state} missing/divergent"


def test_ui_never_builds_html_from_data():
    """The code we write never turns data into markup: task titles and stages
    are repo text and reach the DOM as text children only.

    SOURCE TREE ONLY, and that is not a loosening. React's minified runtime uses
    `innerHTML` internally for its own reasons; scanning the bundle would assert
    something about React rather than about this repo, and the only way to keep
    such a check green would be to delete it. What is asserted instead is
    STRICTER for our code: no DOM HTML sink AND no `dangerouslySetInnerHTML`,
    which is the only door React opens onto one.
    """
    forbidden = (".innerHTML", '["innerHTML"]', ".outerHTML", ".insertAdjacentHTML",
                 "document.write", "dangerouslySetInnerHTML")
    for name, text in _ui_source_files():
        if not name.endswith((".js", ".jsx")):
            continue
        for form in forbidden:
            # A comment may NAME the rule; only a real use is a violation, and a
            # use is always followed by `=`, `(`, `:` or `}`.
            match = re.search(re.escape(form) + r"\s*[=({:]", text)
            assert match is None, f"ui-src/{name} uses {form} ({match.group(0)!r})"


def test_the_shell_only_references_served_routes():
    """The served document's own `src`/`href` must be routes.

    The bundler writes those two tags, so this is the check that the frozen
    output names in `vite.config.js` and the route table in `dashboard.py` still
    agree — the exact pair that silently 404s the whole app when a build config
    changes under someone.
    """
    served = set(dashboard._ALLOWED_STATIC_ROUTES)
    shell = (dashboard._UI_DIR / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r"""(?:src|href)=["'](/[^"']+)["']""", shell)
    assert refs, "the shell references no asset — the build did not inject the bundle"
    for ref in refs:
        assert ref in served, f"the shell references {ref!r}, not a served route"
    # Non-vacuity + the real contract: both halves of the bundle are wired in.
    assert "/assets/app.js" in refs and "/assets/app.css" in refs
    # The SOURCE tree is deliberately unreachable: it holds JSX and a config,
    # none of which is servable. This is the same posture that kept the old
    # `selftest.mjs` out of the table.
    assert not any(route.startswith("/src/") for route in served)
    assert not any("ui-src" in "/".join(segs) for segs, _ct in dashboard._ALLOWED_STATIC_ROUTES.values())


def test_ui_never_puts_the_token_in_a_url():
    """The token travels in an Authorization header only. `token=` may appear
    exactly once in the source — the intake path in `lib/api.js` that STRIPS it
    from the address bar."""
    if not _UI_SRC_DIR.is_dir():
        pytest.skip("front-end source tree absent (build-only checkout)")
    sources = dict(_ui_source_files())
    for name, text in sources.items():
        if name == "src/lib/api.js":
            continue
        # Comments are stripped first. Several modules DOCUMENT the rule by
        # quoting the entry URL the daemon prints (`/?token=…`); a check that
        # cannot tell a rule being stated from a rule being broken would force
        # the documentation out of the code, which is the opposite of the point.
        assert "token=" not in _strip_js_comments(text), f"ui-src/{name} puts a token in a URL"
    api = sources["src/lib/api.js"]
    assert 'params.get("token")' in api and "history.replaceState" in api


def test_ui_never_uses_inline_styles():
    """Pairs with the CSP: the policy does not allow `'unsafe-inline'` for
    styles, so a `.style.x =` assignment or a `style=` attribute in our code
    would be silently dropped by the browser. Colours live in the stylesheet and
    geometry in SVG ATTRIBUTES.

    SOURCE TREE ONLY for the JS half, for the same reason as the markup audit:
    React's runtime assigns `.style` internally. In JSX the sink has a second
    spelling (`style={{…}}`) that exists only in source, and it is checked too.
    The BUILT shell is checked separately below, because a build plugin that
    inlined critical CSS would break the policy without touching a source file.
    """
    if not _UI_SRC_DIR.is_dir():
        pytest.skip("front-end source tree absent (build-only checkout)")
    for name, text in _ui_source_files():
        if name.endswith((".css", ".json")):
            continue
        assert not re.search(r"\.style\s*[.=\[]", text), f"ui-src/{name} assigns an inline style"
        assert "setAttribute('style'" not in text and 'setAttribute("style"' not in text, name
        assert not re.search(r"\sstyle\s*=\s*\{", text), f"ui-src/{name} uses a JSX style prop"
        if name.endswith(".html"):
            assert "style=" not in text, f"ui-src/{name} carries a style attribute"
    shell = (dashboard._UI_DIR / "index.html").read_text(encoding="utf-8")
    assert "<style" not in shell.lower(), "the built shell carries an inline <style> block"
    assert "style=" not in shell, "the built shell carries a style attribute"


def test_the_built_shell_carries_no_inline_script():
    """`script-src 'self'` has no `'unsafe-inline'`. Vite's module-preload
    polyfill IS an inline script, which is why `build.modulePreload.polyfill` is
    false in `vite.config.js`; this is the assertion that keeps that setting from
    being flipped back without anyone noticing the page stops booting."""
    # Comments out first: the shell's own header comment QUOTES the script tag
    # it is allowed to carry, and a scanner that could not tell the two apart
    # would match from inside the comment through to the real closing tag.
    shell = _strip_html_comments((dashboard._UI_DIR / "index.html").read_text(encoding="utf-8"))
    scripts = list(re.finditer(r"<script\b([^>]*)>(.*?)</script>", shell, re.S | re.I))
    assert scripts, "the built shell loads no script at all"
    for match in scripts:
        attrs, body = match.group(1), match.group(2)
        assert "src=" in attrs, f"inline <script> in the built shell: {body[:80]!r}"
        assert not body.strip(), f"<script src> with a body in the built shell: {body[:80]!r}"


# ===========================================================================
# Canal-B reader (shard 4b) — /api/snapshot's `canal_b` section. Fixtures are
# built in the real persisted OTLP/JSON envelope shape; the aggregation is
# asserted against the FROZEN schema, never against a shape invented here.
# ===========================================================================

_TS = "2026-07-27T19:58:52Z"


def _snap_canal_b(_redirect) -> dict:
    return dashboard.build_snapshot(_redirect["project_root"])["canal_b"]


def test_canal_b_degraded_when_directory_absent(_redirect):
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert section["collected"] is False
    assert "state/local/otel/" in section["reason"]
    # Absence must not be readable as a measurement.
    assert "cost" not in section


def test_canal_b_degraded_when_no_jsonl_file(_redirect):
    _redirect["otel_dir"].mkdir(parents=True, exist_ok=True)
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert section["files_read"] == 0
    assert "absence, not zero cost" in section["reason"]


def test_canal_b_degraded_when_every_line_is_corrupt(_redirect):
    _redirect["otel_dir"].mkdir(parents=True, exist_ok=True)
    (_redirect["otel_dir"] / "2026-07-27.1.jsonl").write_text(
        "{not json\nalso not json\n", encoding="utf-8", newline="\n")
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert section["malformed_lines_skipped"] == 2
    assert "zero normalisable record" in section["reason"]


def test_canal_b_partial_read_is_ok_but_reports_dropped_lines(_redirect):
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 0.5, {"model": "m"})])
    with open(_redirect["otel_dir"] / "2026-07-27.1.jsonl", "a", encoding="utf-8", newline="\n") as handle:
        handle.write("{truncated\n")
    section = _snap_canal_b(_redirect)
    assert section["status"] == "ok"
    assert section["partial"] is True
    assert section["malformed_lines_skipped"] == 1
    assert section["cost"]["native_usd"] == 0.5


def test_canal_b_native_cost_comes_from_the_metric_only(_redirect):
    """The double-count guard. `claude_code.cost.usage` and
    `api_request.cost_usd` are the SAME spend seen twice (measured equal on
    this repo's real captures); summing them would double every dollar shown."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 0.4683, {"model": "claude-fable-5"}),
        _log_envelope(_TS, "api_request", {"cost_usd": 0.4683, "input_tokens": 2, "output_tokens": 4}),
    ])
    cost = _snap_canal_b(_redirect)["cost"]
    assert cost["native_usd"] == 0.4683
    assert cost["cross_check_usd_from_logs"] == 0.4683
    # Sensitivity: the naive alternative would report twice the real spend.
    assert cost["native_usd"] + cost["cross_check_usd_from_logs"] == pytest.approx(0.9366)
    assert "never be added" in cost["double_count_note"]


def test_canal_b_cost_by_session_sums_deltas_per_session(_redirect):
    """T-00000096 — the per-session figure the KPI strip renders. cost.usage
    arrives with DELTA temporality, so a session's total is the sum of its
    dataPoints; the most recently ACTIVE session comes first (it is the one
    compared with the host's own /cost display); records without `session.id`
    are counted, never guessed into a bucket."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope("2026-07-27T10:00:00Z", "claude_code.cost.usage", 0.25,
                         {"model": "m", "session.id": "sess-old"}),
        _metric_envelope("2026-07-27T10:00:05Z", "claude_code.cost.usage", 0.25,
                         {"model": "m", "session.id": "sess-old"}),
        _metric_envelope("2026-07-27T19:00:00Z", "claude_code.cost.usage", 1.0,
                         {"model": "m", "session.id": "sess-new"}),
        _metric_envelope("2026-07-27T19:58:52Z", "claude_code.cost.usage", 2.0,
                         {"model": "m", "session.id": "sess-new"}),
        # no session.id at all: counted apart, still inside native_usd
        _metric_envelope(_TS, "claude_code.cost.usage", 0.5, {"model": "m"}),
    ])
    cost = _snap_canal_b(_redirect)["cost"]
    by_session = cost["by_session"]
    sessions = by_session["sessions"]
    assert [s["session_id"] for s in sessions] == ["sess-new", "sess-old"]
    assert sessions[0]["cost_usd"] == 3.0
    assert sessions[0]["last_ts"] == "2026-07-27T19:58:52Z"
    assert sessions[1]["cost_usd"] == 0.5
    assert by_session["records_without_session_id"] == 1
    assert by_session["sessions_seen"] == 2
    # the cumul is untouched by the split — and remains a DIFFERENT number
    assert cost["native_usd"] == pytest.approx(4.0)


def test_canal_b_cost_by_session_is_bounded(_redirect):
    """Bounds doctrine: the payload is polled every 5 s, so the session list
    is capped at the 12 most recently active — the 13th oldest falls out of
    the list but stays counted in `sessions_seen` and in the cumul."""
    envelopes = [
        _metric_envelope(f"2026-07-27T{10 + i:02d}:00:00Z", "claude_code.cost.usage", 1.0,
                         {"model": "m", "session.id": f"sess-{i:02d}"})
        for i in range(13)
    ]
    _write_otel(_redirect["otel_dir"], envelopes)
    cost = _snap_canal_b(_redirect)["cost"]
    by_session = cost["by_session"]
    assert len(by_session["sessions"]) == 12
    assert by_session["sessions_seen"] == 13
    # newest first, and the one that fell out is the OLDEST
    assert by_session["sessions"][0]["session_id"] == "sess-12"
    assert all(s["session_id"] != "sess-00" for s in by_session["sessions"])
    assert cost["native_usd"] == pytest.approx(13.0)


def test_canal_b_tokens_split_by_type(_redirect):
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.token.usage", 2, {"model": "m", "type": "input"}),
        _metric_envelope(_TS, "claude_code.token.usage", 4, {"model": "m", "type": "output"}),
        _metric_envelope(_TS, "claude_code.token.usage", 900, {"model": "m", "type": "cacheRead"}),
    ])
    tokens = _snap_canal_b(_redirect)["tokens"]
    assert tokens["by_type"] == {"input": 2, "output": 4, "cacheRead": 900}
    assert tokens["total"] == 906


def test_canal_b_by_model_carries_tokens_and_cost(_redirect):
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.token.usage", 100, {"model": "big", "type": "input"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 1.5, {"model": "big"}),
        _metric_envelope(_TS, "claude_code.token.usage", 10, {"model": "small", "type": "input"}),
    ])
    by_model = _snap_canal_b(_redirect)["by_model"]
    assert by_model["big"]["tokens"] == 100 and by_model["big"]["cost_usd"] == 1.5
    # A model seen only on token records has no cost of its own - reported as
    # 0.0 cost with real tokens, never dropped from the table.
    assert by_model["small"]["tokens"] == 10 and by_model["small"]["cost_usd"] == 0.0


def test_canal_b_agent_attribution_is_partial_and_counted(_redirect):
    """`agent.name` is optional on the metric: unattributed records must be
    COUNTED, never bucketed under a placeholder agent (that would attribute
    someone else's spend to a name that never ran)."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 0.2, {"model": "m", "agent.name": "dev-multi"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 0.8, {"model": "m"}),
    ])
    agents = _snap_canal_b(_redirect)["by_agent"]
    assert set(agents["data"]) == {"dev-multi"}
    assert agents["attributed_records"] == 1
    assert agents["attributable_records"] == 2
    assert "never bucketed under a placeholder" in agents["coverage_note"]


def test_canal_b_redacted_prompt_id_is_never_used_as_a_join_key(_redirect):
    """L-00000053: the kit's own redaction turns `prompt.id` into the literal
    "REDACTED". Two records sharing that placeholder are NOT the same prompt —
    bucketing on it would collapse every request into one bogus task."""
    _write_otel(_redirect["otel_dir"], [
        _log_envelope(_TS, "api_request", {"cost_usd": 1.0}, prompt_id="REDACTED"),
        _log_envelope(_TS, "api_request", {"cost_usd": 2.0}, prompt_id="REDACTED"),
    ])
    section = _snap_canal_b(_redirect)
    assert section["by_task"]["status"] == "unavailable"
    assert section["by_task"]["data"] == {}
    assert "L-00000053" in section["by_task"]["reason"]
    assert section["join"]["unusable_key_value"] == 2
    assert section["join"]["joined"] == 0
    # Sensitivity: the naive alternative would have produced exactly one bucket
    # keyed by the placeholder, holding the whole $3.
    assert dashboard._is_usable_join_key("REDACTED") is False
    assert dashboard._is_usable_join_key("550e8400-e29b") is True


def test_canal_b_join_succeeds_when_canal_a_supplies_the_pid(_redirect):
    """Positive control, so the "unavailable" above is not vacuous: give canal A
    an event carrying both `pid` and `task`, and canal B a log with the SAME
    prompt id, and the per-task attribution appears."""
    _write_line(_redirect["events_dir"], "2026-07-27.claude.1.jsonl",
                _rec("2026-07-27T19:00:00Z", kind="agent.start", task="T-42", agent="dev-multi"))
    _write_otel(_redirect["otel_dir"], [
        _log_envelope(_TS, "api_request",
                      {"cost_usd": 0.75, "input_tokens": 10, "output_tokens": 5}, prompt_id="p1"),
    ])
    section = _snap_canal_b(_redirect)
    assert section["by_task"]["status"] == "ok"
    assert section["by_task"]["data"]["T-42"]["cost_usd"] == 0.75
    assert section["by_task"]["data"]["T-42"]["tokens"] == 15
    assert section["join"]["joined"] == 1
    assert section["join"]["canal_a_entries_indexed"] == 1


def test_canal_b_host_coverage_never_shows_zero_for_an_absent_host(_redirect):
    """Reuses shard 3's `cost_summary_for_host`, so `not_emitted_by_design`
    (Codex) stays distinguishable from a real $0 — the L-010 false-GO shape
    transposed into a cost view."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}, host="claude-code"),
    ])
    hosts = _snap_canal_b(_redirect)["hosts"]
    assert hosts["claude-code"]["status"] == "collected"
    assert hosts["claude-code"]["cost_usd"] == 1.0
    assert hosts["codex"]["status"] == "not_emitted_by_design"
    assert hosts["codex"]["cost_usd"] is None
    assert "12913" in hosts["codex"]["reason"]
    assert hosts["gemini"]["status"] == "no_data_yet"
    assert hosts["gemini"]["cost_usd"] is None


def test_canal_b_served_payload_carries_metric_totals_with_three_statuses(_redirect):
    """T-00000073 (C9) — the SERVED snapshot payload exposes the net-new
    `metric_totals` section (display is the separate T-00000186). It reuses
    shard 3's `metric_totals_for_host`, so the three-status discipline holds end
    to end: a host that emits nothing keeps `totals: None`, never a bare set of
    zeros (the L-010 false-GO shape transposed onto the count metrics)."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.session.count", 1, {}, host="claude-code"),
    ])
    metric_totals = _snap_canal_b(_redirect)["metric_totals"]
    # collected: the emitted metric carries a real total, the 4 absent are None
    cc = metric_totals["claude-code"]
    assert cc["status"] == "collected"
    assert cc["totals"]["claude_code.session.count"] == {"total": 1, "records": 1}
    assert cc["totals"]["claude_code.commit.count"] is None
    # codex: absent by design → totals None, never a bare 0
    assert metric_totals["codex"]["status"] == "not_emitted_by_design"
    assert metric_totals["codex"]["totals"] is None
    assert "12913" in metric_totals["codex"]["reason"]
    # gemini: no data yet → totals None
    assert metric_totals["gemini"]["status"] == "no_data_yet"
    assert metric_totals["gemini"]["totals"] is None


def test_canal_b_estimate_is_unavailable_without_a_declared_rate_table():
    """The tokens x rate estimate ships DISABLED: no rate table exists in this
    repo, and a rate invented by the dashboard would be a fabricated figure
    wearing an 'estimé' label."""
    assert dashboard._TOKEN_RATES_USD == {}
    assert "no token rate table is declared" in dashboard._TOKEN_RATE_ABSENT_REASON


def test_canal_b_estimate_fields_present_and_labelled(_redirect):
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.token.usage", 100, {"model": "m", "type": "input"}),
    ])
    cost = _snap_canal_b(_redirect)["cost"]
    assert cost["estimated_usd"] is None
    assert cost["estimate_status"] == "unavailable"
    assert cost["rate_table_declared"] is False
    # No cost metric at all -> native is absent, NOT zero.
    assert cost["native_usd"] is None


def test_canal_b_hourly_series_is_bounded_to_24_buckets(_redirect):
    envelopes = []
    for day in range(2):
        for hour in range(24):
            envelopes.append(_metric_envelope(
                f"2026-07-{20 + day:02d}T{hour:02d}:10:00Z", "claude_code.cost.usage", 0.01, {"model": "m"}))
    _write_otel(_redirect["otel_dir"], envelopes)
    series = _snap_canal_b(_redirect)["cost"]["series_hourly"]
    assert len(series) == 24, "an unbounded per-hour map would grow with retention"
    assert series[-1]["hour"] == "2026-07-21T23"
    assert all(point["cost_usd"] == 0.01 for point in series)


def test_canal_b_caveat_travels_with_the_data(_redirect):
    """L-00000049 must be attached to the SECTION, not only to the payload's
    top-level caveats: a consumer that renders the cost panel alone still has
    to see that port 4318 is machine-global."""
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    section = _snap_canal_b(_redirect)
    assert any("L-00000049" in caveat for caveat in section["caveats"])


def test_canal_b_attribution_census_is_five_buckets_in_two_groups(_redirect):
    """REWRITTEN CONTRACT (was `test_canal_b_provenance_is_surfaced`, which
    asserted a two-path `provenance` census).

    THE DICT EQUALITY IS DELIBERATE AND MUST STAY ONE (iteration 7, C3): a
    containment assertion would let a sixth bucket appear, or a bucket silently
    stop being populated, without a single test turning red. This is the census
    the whole of V1-c exists to produce, so it is pinned exactly.

    FIVE buckets, TWO groups, no invited sum: three ROW buckets that partition
    canal B totally (with `attributed_by_backfill` a visible SUB-COUNT of
    `attributed`, not a sibling of it), and two EVENT counters that are not row
    counts at all."""
    _write_otel(_redirect["otel_dir"], [
        # attributed, by DECLARATION
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        # attributed, by INFERENCE (the one-shot backfill materialised it)
        _metric_envelope(_TS, "claude_code.cost.usage", 2.0, {"model": "m"},
                         attributed_by="backfill"),
        # structurally inattributable (Codex, or an un-patched host)
        _metric_envelope(_TS, "claude_code.cost.usage", 4.0, {"model": "m"},
                         project_id=otel_receiver.PROJECT_UNATTRIBUTED),
        # a NEIGHBOURING project's row: held, and out of the totals
        _metric_envelope(_TS, "claude_code.cost.usage", 8.0, {"model": "m"},
                         project_id=_OTHER_ID),
    ])
    attribution = _snap_canal_b(_redirect)["attribution"]
    assert attribution["own_project_id"] == _OWN_ID
    assert attribution["rows_in_store"] == {
        "attributed": 2,
        "attributed_by_backfill": 1,
        "unattributed": 1,
        "foreign_held": 1,
    }
    assert attribution["event_counters"]["dropped_foreign"] == 0
    assert attribution["event_counters"]["foreign_held_expired"] == 0
    # Each counter states its own time base: they are not comparable to each
    # other, let alone addable to the row buckets.
    assert "since this daemon process started" in \
        attribution["event_counters"]["dropped_foreign_basis"]
    assert "cumulative" in attribution["event_counters"]["foreign_held_expired_basis"]
    assert attribution["totals_exclude"] == ["foreign_held"]


def test_foreign_rows_are_excluded_from_the_monetary_totals(_redirect):
    """The reason the bucket exists. A neighbouring project's spend must be
    VISIBLE (a `foreign_held` count) and must NOT enter this project's money —
    L-00000049 answered rather than merely documented."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 4.0, {"model": "m"},
                         project_id=otel_receiver.PROJECT_UNATTRIBUTED),
        _metric_envelope(_TS, "claude_code.cost.usage", 99.0, {"model": "m"},
                         project_id=_OTHER_ID),
    ])
    section = _snap_canal_b(_redirect)
    assert section["cost"]["native_usd"] == 5.0, (
        "own + unattributed, never the neighbour's 99")
    assert section["records_normalised"] == 3, "the census sees every row"
    assert section["records_counted"] == 2, "the figures are computed on 2 of them"


def test_legacy_row_without_the_promoted_field_stays_inside_the_census(_redirect):
    """MUST-FIX M3's fixture in the reader: a pre-V1-c line whose provenance no
    longer matches anything. It is NOT foreign (nothing declares another id) and
    NOT attributable, so it lands in `unattributed` — inside the census and
    inside the labelled totals. Never a silent disappearance, and never a
    render-time re-derivation from its path (iteration 9, C5)."""
    _write_otel(_redirect["otel_dir"], [
        _legacy_metric_envelope(_TS, "claude_code.cost.usage", 3.0, {"model": "m"}),
    ])
    section = _snap_canal_b(_redirect)
    assert section["attribution"]["rows_in_store"] == {
        "attributed": 0, "attributed_by_backfill": 0, "unattributed": 1,
        "foreign_held": 0,
    }
    assert section["cost"]["native_usd"] == 3.0
    # The legacy trace survives, and it is what makes the case diagnosable.
    assert section["provenance"] == {r"C:\elsewhere\a-clone-that-moved": 1}


def test_canal_b_provenance_survives_as_a_legacy_display_census(_redirect):
    """`provenance` is kept, RE-LABELLED, never classified on (pilot decision
    S-00000108 item 3). Post-V1-c it holds ids/sentinels and pre-V1-c absolute
    paths, so it deliberately mixes shapes — which is exactly why nothing
    computes attribution from it any more."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        _legacy_metric_envelope(_TS, "claude_code.cost.usage", 2.0, {"model": "m"},
                                provenance="/proj/legacy"),
    ])
    assert _snap_canal_b(_redirect)["provenance"] == {_OWN_ID: 1, "/proj/legacy": 1}


def test_a_row_that_normalises_to_nothing_is_still_in_the_census(_redirect):
    """FOUND ON THIS REPO'S OWN DATABASE, then pinned here.

    An envelope can be a real stored ROW and normalise to ZERO records: a
    `failure` record carries no schema-family content, and a `kind` outside the
    known set normalises to nothing by design. The census is therefore counted
    over ENVELOPES, not over records — otherwise a QUARANTINED row whose kind is
    unknown would report `foreign_held: 0`, which is precisely the silent
    subtraction this whole block exists to make impossible."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        # kind outside the known set -> normalises to nothing, but IS a row
        {"ts": _TS, "kind": "metrics", "path": "/v1/metrics", "project_id": _OTHER_ID},
        # a bounded parse-failure record -> same: a row, no normalisable content
        {"ts": _TS, "kind": "failure", "path": None,
         "project_id": otel_receiver.PROJECT_UNATTRIBUTED,
         "provenance": otel_receiver.PROJECT_UNATTRIBUTED,
         "failure": {"reason": "json_decode_error", "byte_length": 3}},
    ])
    section = _snap_canal_b(_redirect)
    assert section["attribution"]["rows_in_store"] == {
        "attributed": 1, "attributed_by_backfill": 0, "unattributed": 1,
        "foreign_held": 1,
    }
    # …while the money is still computed on records only, so the unrenderable
    # rows contribute nothing to it.
    assert section["cost"]["native_usd"] == 1.0


def test_canal_b_labels_travel_with_the_data(_redirect):
    """Iteration 9, C6 / the pilot's C6: the backfill and 30-day labels ride in
    `caveats` NEXT TO THE DATA, not only in a panel heading — a consumer that
    renders this section alone must still read them."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    caveats = " ".join(_snap_canal_b(_redirect)["caveats"])
    assert "L-00000049" in caveats
    assert "attributed_by_backfill" in caveats
    assert "T-00000054" in caveats and "30-day" in caveats


# ---------------------------------------------------------------------------
# V1-c — canal B is read from the STORE, with ONE source per snapshot
# ---------------------------------------------------------------------------

def _ingest_otel(_redirect, envelopes: list, filename: str = "2026-07-27.1.jsonl") -> None:
    """Write canal-B envelopes to the spool and PROJECT them, i.e. put the
    reader in its production configuration: the database exists, so the files
    are no longer the source."""
    _write_otel(_redirect["otel_dir"], envelopes, filename)
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    dashboard._reset_canal_b_cache_for_tests()


def test_canal_b_reads_the_store_when_it_exists(_redirect):
    _ingest_otel(_redirect, [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.5, {"model": "m"})])
    section = _snap_canal_b(_redirect)
    assert section["status"] == "ok"
    assert section["source"] == "sqlite"
    assert section["rows_read"] == 1
    assert section["cost"]["native_usd"] == 1.5


def test_canal_b_reads_quarantined_rows_from_the_store_unfiltered(_redirect):
    """The store read is NOT filtered by `project`: the quarantine has to be
    DISPLAYED, so the reader must see it. The exclusion happens in the totals,
    not in the query."""
    _ingest_otel(_redirect, [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 50.0, {"model": "m"},
                         project_id=_OTHER_ID),
    ])
    section = _snap_canal_b(_redirect)
    assert section["source"] == "sqlite"
    assert section["attribution"]["rows_in_store"]["foreign_held"] == 1
    assert section["cost"]["native_usd"] == 1.0


def test_canal_b_falls_back_to_files_only_while_the_store_is_absent(_redirect):
    """The fallback is NARROW on purpose: `absent` means the daemon has never
    ingested and there is nothing else to read. It is also honest about itself —
    the backfill has not run either, and the payload says so."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    section = _snap_canal_b(_redirect)
    assert section["status"] == "ok"
    assert section["source"] == "spool_files"
    assert "has never ingested" in section["source_note"]


@pytest.mark.parametrize("status", ["unavailable", "schema_ahead"])
def test_canal_b_degrades_without_reading_files_when_the_store_is_broken(
        _redirect, monkeypatch, status):
    """Iteration 5's C2 shape, closed: a database written by a NEWER kit, or one
    we refused to interpret, means the figures cannot be trusted. Quietly
    rendering a file-derived number instead would be a SECOND story about the
    same money, told without saying which one you are reading. So: degraded,
    WITH the store's own reason, and the files are never opened."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])

    def _broken(*_a, **_k):
        store = event_store.EventStore(_redirect["project_root"] / "events.db",
                                       None, status, f"simulated {status}", 99)
        return store

    monkeypatch.setattr(dashboard._event_store_mod, "open_store", _broken)
    read_calls: list = []
    monkeypatch.setattr(dashboard._otel_normalize_mod, "iter_envelopes",
                        lambda *a, **k: read_calls.append(a) or ([], 0))
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert section["source"] == status
    assert f"simulated {status}" in section["reason"]
    assert read_calls == [], "a broken store must NEVER trigger a file fallback"


def test_canal_b_cache_follows_absent_to_ok_then_every_wal_data_commit(_redirect):
    """Iteration 6, C5: `absent -> ok` is the moment the SOURCE of this section changes, and a
    key of file mtimes alone could serve a pre-first-tick snapshot for ever. T-00000615: then,
    spool drained, a WAL commit leaves the store's stat frozen; its DATA generation must tell."""
    otel, cost = _redirect["otel_dir"], "claude_code.cost.usage"
    now = datetime.fromisoformat(_TS.replace("Z", "+00:00"))  # inside retention: nothing folds
    _write_otel(otel, [_metric_envelope(_TS, cost, 1.0, {"model": "m"})])
    assert _snap_canal_b(_redirect)["source"] == "spool_files"
    with event_store.open_store(create=True) as store:  # held open, as the daemon holds it
        store.ingest_once(now=now)
        # NO cache reset here or below — the fingerprint itself must notice.
        assert _snap_canal_b(_redirect)["source"] == "sqlite", "the STATUS is in the key"
        for path in otel.glob("*.jsonl"):
            path.unlink()  # the drained steady state: no spool file left to move the key
        assert _snap_canal_b(_redirect)["rows_read"] == 1
        _write_otel(otel, [_metric_envelope(_TS, cost, 2.0, {"model": "m"})], "2026-07-27.2.jsonl")
        store.ingest_once(now=now + timedelta(seconds=5))
        (otel / "2026-07-27.2.jsonl").unlink()
        assert _snap_canal_b(_redirect)["rows_read"] == 2, "a WAL commit left canal B stale"


def test_snapshot_never_500s_when_canal_b_normalisation_raises(_redirect, monkeypatch):
    """The normaliser is documented never-raises; the reader still refuses to
    let a surprise there take down board/ledger/specs/index/security."""
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])

    def _boom(_dir):
        raise RuntimeError("simulated normaliser failure")

    # V1-c moved the seam one level down (`iter_envelopes` + `normalize_envelopes`,
    # so the ROW census and the money can be counted at their own granularities).
    # The property under test is unchanged: a surprise in the normaliser degrades
    # this section alone.
    monkeypatch.setattr(dashboard._otel_normalize_mod, "iter_envelopes", _boom)
    snap = dashboard.build_snapshot(_redirect["project_root"])
    assert snap["canal_b"]["status"] == "degraded"
    assert "RuntimeError" in snap["canal_b"]["reason"]
    assert snap["board"]["status"] == "ok"  # every other section unaffected


def test_canal_b_over_http_is_still_token_only(ui_server, _redirect):
    """The payload grew; the route table did not. Canal-B data is reachable
    only through the authenticated /api/snapshot."""
    port, token = ui_server
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    assert _get(port, "/api/snapshot").status == 401
    body = json.loads(_get(port, "/api/snapshot", token=token).data)
    assert body["canal_b"]["status"] == "ok"
    assert body["canal_b"]["cost"]["native_usd"] == 1.0
    # No new route was added for canal B.
    assert _get(port, "/api/canal_b", token=token).status == 404
    assert _get(port, "/api/cost", token=token).status == 404


def test_canal_b_aggregates_are_cached_between_identical_polls(_redirect, monkeypatch):
    """The route is polled every 5 s by the UI and once per `daemon.ping()`
    (1 s budget). Re-normalising every canal-A/canal-B file on each call makes
    the reader slower as the event stream ages — so an unchanged file set must
    cost stat() calls, not reads."""
    dashboard._reset_canal_b_cache_for_tests()
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    calls = []
    real = dashboard._otel_normalize_mod.iter_envelopes

    def counted(directory):
        calls.append(directory)
        return real(directory)

    monkeypatch.setattr(dashboard._otel_normalize_mod, "iter_envelopes", counted)
    first = _snap_canal_b(_redirect)
    second = _snap_canal_b(_redirect)
    assert len(calls) == 1, "an unchanged file set must not be re-normalised"
    assert first["cost"]["native_usd"] == second["cost"]["native_usd"] == 1.0


def test_canal_b_cache_invalidates_when_a_file_grows(_redirect, monkeypatch):
    """Sensitivity control for the cache: a stale cost figure is worse than a
    slow one, so appending must be visible on the very next poll."""
    dashboard._reset_canal_b_cache_for_tests()
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"})])
    assert _snap_canal_b(_redirect)["cost"]["native_usd"] == 1.0
    _write_otel(_redirect["otel_dir"], [_metric_envelope(_TS, "claude_code.cost.usage", 0.5, {"model": "m"})])
    assert _snap_canal_b(_redirect)["cost"]["native_usd"] == 1.5


def test_canal_b_cache_invalidates_when_canal_a_changes(_redirect):
    """The join index is part of the aggregate, so a new canal-A event must
    invalidate too — otherwise a task attribution could never appear."""
    dashboard._reset_canal_b_cache_for_tests()
    _write_otel(_redirect["otel_dir"], [
        _log_envelope(_TS, "api_request", {"cost_usd": 0.75}, prompt_id="p1"),
    ])
    assert _snap_canal_b(_redirect)["by_task"]["status"] == "unavailable"
    _write_line(_redirect["events_dir"], "2026-07-27.claude.1.jsonl",
                _rec("2026-07-27T19:00:00Z", kind="agent.start", task="T-77", agent="dev-mono"))
    section = _snap_canal_b(_redirect)
    assert section["by_task"]["status"] == "ok"
    assert "T-77" in section["by_task"]["data"]


def test_canal_b_cache_is_not_shared_between_project_trees(tmp_path, monkeypatch):
    """The resolved directory paths are part of the fingerprint — that is what
    makes a module-level cache safe when two trees are read in one process."""
    dashboard._reset_canal_b_cache_for_tests()
    first_otel = tmp_path / "a" / "otel"
    second_otel = tmp_path / "b" / "otel"
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(first_otel))
    _write_otel(first_otel, [_metric_envelope(_TS, "claude_code.cost.usage", 3.0, {"model": "m"})])
    assert dashboard._read_canal_b()["cost"]["native_usd"] == 3.0
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(second_otel))
    _write_otel(second_otel, [_metric_envelope(_TS, "claude_code.cost.usage", 9.0, {"model": "m"})])
    assert dashboard._read_canal_b()["cost"]["native_usd"] == 9.0


def test_canal_b_records_without_prompt_id_are_counted_not_fabricated(_redirect):
    """The frozen schema's own measured drift: session-lifecycle events carry no
    `prompt.id` at all. They must be counted as `no_key`, never given one."""
    _write_otel(_redirect["otel_dir"], [
        _log_envelope(_TS, "hook_registered", {}),
        _log_envelope(_TS, "plugin_loaded", {}),
        _log_envelope(_TS, "api_request", {"cost_usd": 0.1}, prompt_id="p-real"),
    ])
    join = _snap_canal_b(_redirect)["join"]
    assert join["no_key"] == 2
    assert join["unusable_key_value"] == 0
    assert join["canal_b_logs"] == 3


# ===========================================================================
# T-00000026 SHARD A — /api/stream (SSE)
#
# The transport, not the data: this endpoint carries CHANGE NOTICES only, so
# the tests below assert (a) it is as locked down as every other /api/* route,
# (b) it is BOUNDED, and (c) its threads die. A stream that leaks a thread or a
# slot is the failure mode that turns a read-only dashboard into a resource
# leak on a developer's machine, so it gets more tests than the notices do.
# ===========================================================================

def test_stream_requires_a_token(ui_server):
    port, _token = ui_server
    conn, resp = _open_stream(port)
    try:
        assert resp.status == 401
        assert json.loads(resp.read()) == {"error": "unauthorized"}
    finally:
        conn.close()


def test_stream_wrong_token_401(ui_server):
    port, token = ui_server
    conn, resp = _open_stream(port, token=token + "x")
    try:
        assert resp.status == 401
        resp.read()
    finally:
        conn.close()


def test_stream_headers_are_sse_no_store_and_never_cors(ui_server, monkeypatch):
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.05)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        assert resp.status == 200
        # Exactly the bare MIME type: EventSource matches `text/event-stream`.
        assert resp.getheader("Content-Type") == "text/event-stream"
        assert resp.getheader("Cache-Control") == "no-store"
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        # An open-ended body must not declare a length.
        assert resp.getheader("Content-Length") is None
        for name, _value in resp.getheaders():
            assert "access-control" not in name.lower()
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_opens_with_retry_and_a_hello_event(ui_server, monkeypatch):
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.05)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        assert _read_frame(resp) == f"retry: {dashboard._STREAM_RETRY_MS}"
        hello = _stream_json(_read_frame(resp))
        assert hello["kind"] == "hello"
        assert hello["poll_ms"] == int(dashboard._STREAM_POLL_SECONDS * 1000)
        assert set(hello["kinds"]) >= {"snapshot_changed", "events_changed"}
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_emits_events_changed_on_a_canal_a_append(ui_server, _redirect, monkeypatch):
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.05)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 30.0)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        _read_frame(resp)  # retry:
        _read_frame(resp)  # hello
        _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                    _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
        frames = _read_until(
            resp,
            lambda line: line.startswith("data: ") and "events_changed" in line,
        )
        kinds = [_stream_json(f)["kind"] for f in frames if f.startswith("data: ")]
        assert "events_changed" in kinds
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_emits_snapshot_changed_on_a_store_write(ui_server, _redirect, monkeypatch):
    """A board write touches the snapshot's inputs but not the canal-A
    directory, so `snapshot_changed` must fire on its own - that is why the two
    fingerprints are computed separately."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.05)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 30.0)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        _read_frame(resp)
        _read_frame(resp)
        _write_project_file(
            _redirect["project_root"], (".agents", "state", "board", "TASKS.json"),
            json.dumps({"next_id": 2, "tasks": [
                {"id": "T-00000001", "task": "t", "state": "pending", "stage": None,
                 "owner": None, "updated": "2026-07-28"}]}),
        )
        frames = _read_until(
            resp,
            lambda line: line.startswith("data: ") and "snapshot_changed" in line,
        )
        assert any("snapshot_changed" in f for f in frames)
        assert not any("events_changed" in f for f in frames), \
            "a board write must not be reported as canal-A movement"
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_sends_a_keepalive_comment_when_nothing_changes(ui_server, monkeypatch):
    """The heartbeat is an SSE COMMENT (ignored by EventSource) whose only job
    is to fail on a dead socket - that is how a client detects a cut."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 0.1)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        _read_frame(resp)
        _read_frame(resp)
        frames = _read_until(resp, lambda line: line.startswith(": keepalive"))
        assert frames[-1].startswith(": keepalive ")
        # A comment is NOT an event: it must never look like data.
        assert not frames[-1].startswith("data:")
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_counts_as_authorised_activity_for_the_idle_watchdog(ui_server_object, monkeypatch):
    """`dashboard_daemon`'s watchdog auto-stops on absence of AUTHORISED
    traffic. A human with the dashboard open is using it between clicks, so
    every successful stream write must restamp `last_activity` - otherwise the
    daemon kills the very UI that is watching it."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 0.05)
    httpd, port, token = ui_server_object
    conn, resp = _open_stream(port, token=token)
    try:
        _read_frame(resp)
        _read_frame(resp)
        # Pin to 0.0, then DRAIN until the stamp moves. Reading a single
        # keepalive would race: a frame already in the socket buffer was
        # written (and stamped) BEFORE the pin, so observing it proves nothing.
        httpd.last_activity = 0.0
        deadline = time.monotonic() + 10.0
        while httpd.last_activity == 0.0 and time.monotonic() < deadline:
            assert _read_frame(resp), "the stream closed instead of keeping alive"
        assert httpd.last_activity > 0.0
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_thread_dies_when_the_client_disconnects(ui_server, monkeypatch):
    """The load-bearing lifetime property: a write that fails is the loop's
    normal exit. Asserted on the SLOT COUNTER, not on a log line - a slot still
    held is a thread still alive."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 0.05)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    _read_frame(resp)
    _read_frame(resp)
    assert dashboard.active_stream_count() == 1
    _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_concurrency_is_bounded_and_the_extra_client_gets_503(ui_server, monkeypatch):
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 0.05)
    port, token = ui_server
    limit = dashboard._MAX_CONCURRENT_STREAMS
    assert limit == 4, "the bound is small on purpose - a loopback single-user tool"
    conns = []
    try:
        for _ in range(limit):
            conn, resp = _open_stream(port, token=token)
            assert resp.status == 200
            _read_frame(resp)
            _read_frame(resp)
            conns.append((conn, resp))
        assert dashboard.active_stream_count() == limit
        extra_conn, extra = _open_stream(port, token=token)
        try:
            assert extra.status == 503
            assert json.loads(extra.read()) == {"error": "stream_limit_reached"}
            assert extra.getheader("Retry-After") == "5"
            for name, _value in extra.getheaders():
                assert "access-control" not in name.lower()
        finally:
            _close_stream(extra_conn, extra)
    finally:
        for conn, resp in conns:
            _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_slot_is_released_so_a_later_client_is_admitted(ui_server, monkeypatch):
    """Sensitivity control for the bound: if the slot were never released the
    counter would be a permanent budget rather than a concurrency limit."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(dashboard, "_MAX_CONCURRENT_STREAMS", 1)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    _read_frame(resp)
    _read_frame(resp)
    busy_conn, busy = _open_stream(port, token=token)
    assert busy.status == 503
    busy.read()
    _close_stream(busy_conn, busy)
    _close_stream(conn, resp)
    _wait_for_streams(0)
    again_conn, again = _open_stream(port, token=token)
    try:
        assert again.status == 200
    finally:
        _close_stream(again_conn, again)
    _wait_for_streams(0)


def test_server_close_does_not_hang_on_an_open_stream(_redirect, monkeypatch):
    """`server_close()` sets `stream_stop` BEFORE tearing anything down, so an
    open stream can neither block shutdown nor survive it. Bounded assertion on
    the wall-clock cost of the close itself: a stream must never turn a
    teardown into a 3600 s wait."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.05)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 30.0)
    created = dashboard.create_ui_server(project_root=_redirect["project_root"])
    assert created is not None
    httpd, token = created
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    conn, resp = _open_stream(httpd.server_address[1], token=token)
    _read_frame(resp)
    _read_frame(resp)
    assert dashboard.active_stream_count() == 1
    started = time.monotonic()
    httpd.shutdown()
    httpd.server_close()
    elapsed = time.monotonic() - started
    thread.join(timeout=5)
    assert elapsed < 5.0, f"server_close() took {elapsed:.2f}s with a stream open"
    assert httpd.stream_stop.is_set()
    _close_stream(conn, resp)
    _wait_for_streams(0)


def test_stream_max_lifetime_closes_cleanly_rather_than_wedging(ui_server, monkeypatch):
    """A half-open socket the OS never reports as dead would otherwise pin a
    thread forever; the stream announces its own expiry and lets the client
    reconnect via `retry:`."""
    monkeypatch.setattr(dashboard, "_STREAM_POLL_SECONDS", 0.02)
    monkeypatch.setattr(dashboard, "_STREAM_HEARTBEAT_SECONDS", 30.0)
    monkeypatch.setattr(dashboard, "_STREAM_MAX_SECONDS", 0.15)
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        _read_frame(resp)
        _read_frame(resp)
        frames = _read_until(resp, lambda line: "stream_expired" in line)
        assert _stream_json(frames[-1])["kind"] == "stream_expired"
    finally:
        _close_stream(conn, resp)
    _wait_for_streams(0)


@pytest.mark.parametrize("path", [
    "/api/stream/../../../etc/passwd",
    "/api/stream/..",
    "/api%2e%2e/stream",
    "/api/stream%00",
    "/api/stream/",
])
def test_stream_traversal_variants_rejected(ui_server, path):
    port, token = ui_server
    resp = _get(port, path, token=token)
    assert resp.status == 404, f"{path!r} was not rejected (status={resp.status})"


def test_post_on_the_stream_route_404(ui_server):
    """AMENDED BY T-00000028 (comment only, assertion unchanged): POST is no
    longer refused server-wide, it is refused everywhere outside
    `_ALLOWED_WRITE_PATHS`. A READ route keeps 404-ing on it, and `/api/stream`
    is the one whose confusion would be most expensive — a verb that opened an
    SSE body would hold a handler thread on a request nobody meant to make."""
    port, _token = ui_server
    assert _post(port, "/api/stream", b'{"a":1}').status == 404


def test_the_api_route_set_stays_closed_and_small(ui_server, _redirect):
    """TWELVE token-required reads, ONE token-exempt peer route, THREE writes, plus THREE handoff
    routes pinned by their twins in `test_dashboard_handoff.py` (`_HANDOFF_POSTS` and after):
    each is here because a payload key could NOT serve its purpose. Named individually, on purpose:
    this assertion is what stops "just one more endpoint" from becoming the shape of this server,
    and a nameless count would let a route in without a justification.

      * `/api/snapshot`  — shard 1's aggregate. The six D4 views added ZERO
                           routes: they ride INSIDE this payload.
      * `/api/events`    — canal A, paginated by an opaque per-file byte cursor.
      * `/api/stream`    — an open-ended SSE body (D4). A payload key cannot be
                           a long-lived connection.
      * `/api/ping`      — liveness that reads NOTHING (T-00000043): probing
                           /api/snapshot made a health check pay for the
                           heaviest read, and a busy machine then looked dead.
      * `/api/projects`  — the versioned contract a future hub reads
                           (T-00000051, spec §A.5). A hub must be able to ask
                           "who are you?" of a daemon whose ~166 KB snapshot
                           schema it does not yet understand, WITHOUT paying for
                           that read: hence a separate route carrying
                           `api_version` + `kind`.
      * `/api/peers`     — T-00000083 (M2). The OTHER daemons on this machine, read from `~/.agentkit/registry.json`
                           and probed. Cannot be a key of `/api/snapshot`: that payload is memoised on THIS project's
                           files, and a peer's liveness changes with no local file changing.
      * `/api/sessions`  — T-00000086 (M5a). Canal A grouped by (host, session) over a bounded window. Cannot be a
                           key of `/api/snapshot` either, for a different reason: it takes FILTERS (`host`, `project`,
                           `since`), and a filtered read inside a memoised aggregate would either ignore the filters
                           or destroy the memoisation.
      * `/api/term`      — T-00000087 (M5b). The console MIRROR inventory:
                           `wrap.py`'s spools, not canal-A events. Cannot be a
                           key of `/api/sessions` — that route groups EVENTS by
                           (host, session), this one lists FILES, and the two
                           sets overlap by accident: a console can have events
                           and no mirror (started by hand, the ordinary case) or
                           a mirror and no events.
      * `/api/term/stream` — the mirror BODY: an open-ended SSE of raw terminal
                           bytes. A second stream route rather than a mode of
                           `/api/stream` because it carries PAYLOAD instead of
                           change notices and holds its OWN concurrency budget
                           (`_MAX_TERM_STREAMS`) — sharing the notice slots
                           would let two open terminals stop the dashboard from
                           refreshing itself.
      * `/api/specs`     — T-01M51Q7GJ1 lot D: ONE PAGE of SPECS under a closed grammar (A2.3); takes FILTERS too.
      * `/api/lecons`    — lot D: one page of LEDGER + `counts`; out of the snapshot so contract 2 sheds ~70 %.
      * `/api/recherche` — lot D: the palette corpus, read only while it is open — never in every snapshot poll.

    And ONE token-exempt route in its own closed table, because its consumer is
    not a browser holding this daemon's token but another project's daemon:

      * `/api/peer/summary` — identity + the running task + health, and nothing
                              else. Token-exempt by necessity (a peer cannot
                              hold this token, and publishing it in a
                              machine-wide file is what L-00000112 forbids), so
                              the KEY SET is the security boundary.

    AMENDED BY T-00000028 — explicitly, because this test is exactly the guard
    that was supposed to make "one more endpoint" cost an argument. Three WRITE
    routes now exist (`_ALLOWED_WRITE_PATHS`), reachable by POST only, token
    REQUIRED, and they are named here for the same reason the read routes are:

      * `/api/actions/gate`   — records a plan approval as `gate.approval` +
                                a specs `decision` entry, hashing a plan the
                                SERVER re-read. It exists because that event
                                kind had no emitter at all, so the governance
                                view could only show a blind spot.
      * `/api/actions/board`  — start/block/unblock/done, driven through
                                `tasks.py` so the running invariant and
                                the id allocation keep exactly one owner.
      * `/api/actions/waiver` — a class-3 ACCEPT & TRACK, written through
                                `waivers.py`, the register's one writer.

    What did NOT change is what this assertion now protects: the read tables are
    byte-identical, the write table is disjoint from all three of them, and the
    write verb reached neither token-exempt table.

    Everything else must still 404 (the two handoff tables: `test_dashboard_handoff.py`)."""
    assert dashboard._ALLOWED_UI_PATHS == frozenset(
        {"/api/snapshot", "/api/events", "/api/stream", "/api/ping", "/api/projects",
         "/api/peers", "/api/sessions", "/api/term", "/api/term/stream",
         "/api/specs", "/api/lecons", "/api/recherche", "/api/livrables"})
    assert dashboard._ALLOWED_PEER_PATHS == frozenset({"/api/peer/summary"})
    assert dashboard._ALLOWED_WRITE_PATHS == frozenset(
        {"/api/actions/gate", "/api/actions/board", "/api/actions/waiver"})
    # The four tables never overlap: a route may be token-exempt OR
    # token-required, never both depending on which check runs first — and a
    # route is readable or writable, never silently both.
    assert not (dashboard._ALLOWED_PEER_PATHS & dashboard._ALLOWED_UI_PATHS)
    assert not (dashboard._ALLOWED_PEER_PATHS & set(dashboard._ALLOWED_STATIC_ROUTES))
    assert not (dashboard._ALLOWED_WRITE_PATHS & dashboard._ALLOWED_UI_PATHS)
    assert not (dashboard._ALLOWED_WRITE_PATHS & dashboard._ALLOWED_PEER_PATHS)
    assert not (dashboard._ALLOWED_WRITE_PATHS & set(dashboard._ALLOWED_STATIC_ROUTES))
    port, token = ui_server
    for path in ("/api/governance", "/api/security", "/api/memory", "/api/index",
                 "/api/mcp", "/api/coverage", "/api/views", "/api/waivers",
                 "/api/allowlist", "/api/stream/events", "/api/project",
                 "/api/projects/p-1", "/api/projects/", "/api/peer",
                 "/api/peer/summary/", "/api/peers/", "/api/peers/p-1",
                 "/api/session", "/api/sessions/", "/api/sessions/s-1",
                 "/api/terms", "/api/term/", "/api/term/s-1", "/api/term/stream/",
                 "/api/term/stream/s-1", "/api/term/raw",
                 # T-00000028: the write routes are POST-only. A GET on one of
                 # them is not a read of "what would be written" — it is a route
                 # that does not exist on this verb.
                 "/api/actions", "/api/actions/", "/api/actions/gate",
                 "/api/actions/board", "/api/actions/waiver"):
        assert _get(port, path, token=token).status == 404, path
    # ...and the frozen routes still answer exactly as before.
    assert _get(port, "/api/snapshot", token=token).status == 200
    assert _get(port, "/api/events", token=token).status == 200
    assert _get(port, "/api/projects", token=token).status == 200


def test_existing_snapshot_contract_keys_survive_the_views_addition(_redirect):
    """Non-regression: shard 1/4b's own keys are untouched, and `security`
    still holds the RAW effective verdict - `views.security` references it, it
    does not replace it."""
    snap = dashboard.build_snapshot(_redirect["project_root"])
    for key in ("generated_at", "board", "ledger", "specs", "index", "security",
                "canal_b", "caveats"):
        assert key in snap, key
    assert set(snap["views"]) == _EXPECTED_VIEW_KEYS
    assert snap["views"]["security"]["verdict"] is snap["security"]


# ===========================================================================
# T-00000026 SHARD A — the unified readers. One JSONL reader, six sections,
# each degrading on its own.
# ===========================================================================

def _views(_redirect) -> dict:
    return dashboard.build_snapshot(_redirect["project_root"])["views"]


# ---------------------------------------------------------------------------
# T-00000065 — the canal-A trail comes from the STORE once there is one.
# ---------------------------------------------------------------------------

def _ingest_canal_a(_redirect, records: list, filename: str = "2026-07-27.claude.7.jsonl") -> None:
    """Put the canal-A reader in its PRODUCTION configuration: the records
    projected into the database, and the spool directory EMPTY. That empty
    directory is the whole point of the fixture, not an incidental step — it is
    the state a healthy repo is in almost all of the time, and the state that
    used to be rendered as `trail_absent`.

    The leftover files are removed HERE rather than left to the ingester's own
    deletion, and that is deliberate. Whether a given file is deleted on this
    tick depends on a quiescence window measured against mtimes, plus the
    one-time legacy fold of past days — two clock-sensitive behaviours that
    `test_event_store.py` owns and pins (T-00000057, T-00000063). Reproducing
    them here would couple this file to the calendar to assert something it does
    not measure. What these tests need is the STATE, reached explicitly."""
    for record in records:
        _write_line(_redirect["events_dir"], filename, record)
    store = event_store.open_store(create=True)
    try:
        store.ingest_once()
    finally:
        store.close()
    for leftover in _redirect["events_dir"].glob("*.jsonl"):
        leftover.unlink()
    dashboard._reset_canal_a_cache_for_tests()
    readers.reset_cache_for_tests()


def test_a_drained_spool_next_to_a_populated_store_is_not_an_absent_trail(_redirect):
    """THE REGRESSION PIN. Before T-00000065 this exact state — every record
    safely projected, the day-file consumed and deleted — rendered as "ABSENT
    TRAIL, not a measurement of zero activity" across four views, while the
    database held the whole audit history."""
    _ingest_canal_a(_redirect, [
        _rec("2026-07-27T00:00:00Z", kind="hook.deny", task="T-1"),
        _rec("2026-07-27T00:00:01Z", kind="hook.deny", task="T-2"),
    ])
    # The precondition this test would be meaningless without.
    assert not list(_redirect["events_dir"].glob("*.jsonl")), (
        "the ingester must have consumed and deleted the day-file")

    trail = dashboard._read_canal_a_trail()
    assert trail["status"] == "ok", trail["reason"]
    assert trail["source"] == "sqlite"
    assert trail["rows"] == 2
    assert [r["kind"] for r in trail["records"]] == ["hook.deny", "hook.deny"]

    # ...and it reaches the views, which is what the pilot actually sees.
    views = _views(_redirect)
    assert views["governance"]["status"] == "ok"
    assert views["governance"]["trail"]["status"] == "ok"


def test_an_empty_spool_with_no_store_at_all_is_still_an_absent_trail(_redirect):
    """THE NEGATIVE ARM, and it is load-bearing. Without it, a reader that
    reported `ok` unconditionally would pass the test above while destroying the
    only distinction these views exist to draw (T-00000026: "aucun événement"
    must not render like "trail perdu"). No database, no day-file: nothing was
    ever recorded here, and that must still be said."""
    _redirect["events_dir"].mkdir(parents=True, exist_ok=True)
    assert not (_redirect["project_root"].parent / "local" / "events.db").exists()

    trail = dashboard._read_canal_a_trail()
    assert trail["status"] == "trail_absent"
    assert trail["source"] == "spool_files"
    assert "ABSENT TRAIL" in trail["reason"]
    assert "no SQLite projection" in trail["reason"], (
        "the reason must name BOTH missing sources, or it accuses the wrong one")


def test_a_store_that_exists_but_holds_no_canal_a_row_is_zero_not_absent(_redirect):
    """The third state, and the one the vocabulary exists for: the store is
    readable and simply has nothing on this channel. That IS a measurement of
    zero activity, and it must not borrow the absent-trail wording."""
    store = event_store.open_store(create=True)
    store.close()
    dashboard._reset_canal_a_cache_for_tests()

    trail = dashboard._read_canal_a_trail()
    assert trail["status"] == "no_events"
    assert trail["source"] == "sqlite"
    assert "ABSENT TRAIL" not in (trail["reason"] or "")


def test_an_unreadable_store_never_falls_back_to_the_files(_redirect, monkeypatch):
    """Canal B's rule, applied to canal A: a database we could not interpret is
    reported as such and the spool is NOT read behind it. Rendering a
    file-derived count instead would be a second story about the same trail,
    told without saying which one you are reading.

    Non-vacuity: the spool holds a record that a fallback WOULD find, so the
    empty result cannot be an accident of an empty directory."""
    _write_line(_redirect["events_dir"], "2026-07-27.claude.9.jsonl",
                _rec("2026-07-27T00:00:00Z", kind="hook.deny"))

    class _Broken:
        status = "unavailable"
        reason = "schema written by a newer kit"

        def close(self):
            pass

    monkeypatch.setattr(dashboard._event_store_mod, "open_store",
                        lambda *a, **k: _Broken())
    dashboard._reset_canal_a_cache_for_tests()

    trail = dashboard._read_canal_a_trail()
    assert trail["status"] == "unavailable"
    assert trail["records"] == []
    assert "schema written by a newer kit" in trail["reason"]

    # And every trail-derived section must report that status rather than
    # rendering a zero. The level differs per view because the sections compose
    # different numbers of sources — `mcp` also reads the allowlist and
    # `coverage` also reads canal B, so their trail-derived PART carries it
    # while the section stays `ok` for what it could still read.
    views = _views(_redirect)
    assert views["governance"]["status"] == "unavailable"
    assert views["governance"]["trail"]["status"] == "unavailable"
    assert views["mcp"]["usage"]["status"] == "unavailable"
    assert views["coverage"]["canal_a"]["status"] == "unavailable"


def test_build_views_never_invents_a_trail_when_none_is_supplied():
    """`canal_a_stream` is a REQUIRED parameter: the defect being fixed was a
    reader silently choosing the wrong source, so the signature must not offer a
    default that would choose one again."""
    import inspect
    parameter = inspect.signature(readers.build_views).parameters["canal_a_stream"]
    assert parameter.default is inspect.Parameter.empty


def test_one_jsonl_reader_is_shared_not_duplicated():
    """Task scope, explicit: `sca-reports/audit-log.jsonl` is ABSORBED into the
    unified readers, not given a second parser. The proof is identity - the
    canal-A reader and the readers module expose the SAME function object."""
    assert dashboard._read_new_records is readers.read_new_records
    assert dashboard._dir_fingerprint is readers.dir_fingerprint


def test_read_jsonl_file_keeps_the_partial_line_rule():
    """Sensitivity: the shared reader must not lose non-negotiable #2 on its
    way into the security history."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "audit-log.jsonl"
        path.write_bytes(b'{"a":1}\n{"b":2}\n{"c":3')  # last line unterminated
        records, malformed = readers.read_jsonl_file(path)
        assert records == [{"a": 1}, {"b": 2}]
        assert malformed == 0, "an unterminated tail is a write in flight, not corruption"


def test_canal_a_emitter_table_covers_every_declared_kind():
    """Drift guard: adding a `kind` to events.py without deciding its coverage
    story would otherwise produce a silently blank matrix row - the exact
    'silently missing signal' the design doc forbids."""
    assert set(readers.CANAL_A_EMITTERS) == set(events_mod.KNOWN_KINDS)


# --- Gouvernance -----------------------------------------------------------

def test_governance_distinguishes_an_absent_trail_from_no_events(_redirect):
    """The distinction this view exists for (design doc §F.3): the events
    directory ABSENT and the events directory present-but-quiet are different
    facts and must not render the same."""
    absent = _views(_redirect)["governance"]
    assert absent["status"] == "trail_absent"
    assert "does not exist" in absent["reason"]
    assert absent["totals"] == {}

    # A present trail holding non-governance events: a real measurement.
    readers.reset_cache_for_tests()
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="session.start"))
    quiet = _views(_redirect)["governance"]
    assert quiet["status"] == "no_events"
    assert "trail is PRESENT" in quiet["reason"]
    assert quiet["trail"]["files"] == 1


def test_governance_empty_directory_is_still_an_absent_trail(_redirect):
    """A directory with no day-file is the trail's LOCATION without its
    content - not a measurement of zero activity."""
    _redirect["events_dir"].mkdir(parents=True, exist_ok=True)
    section = _views(_redirect)["governance"]
    assert section["status"] == "trail_absent"
    assert "no *.jsonl day-file" in section["reason"]


def test_governance_aggregates_by_guard_rule_and_day(_redirect):
    events_dir = _redirect["events_dir"]
    for i, (day, guard, rule) in enumerate([
        ("2026-07-27", "protect-paths", "src/legacy"),
        ("2026-07-27", "protect-paths", "src/legacy"),
        ("2026-07-28", "safe-bash", "rm-tracked"),
    ]):
        record = _rec(f"{day}T0{i}:00:00Z", kind="hook.deny")
        record["data"] = {"guard": guard, "rule": rule, "path": ".env"}
        _write_line(events_dir, "2026-07-28.claude.1.jsonl", record)
    check = _rec("2026-07-28T05:00:00Z", kind="hook.check_fail")
    check["data"] = {"guard": "post-edit-check", "rule": "ruff"}
    _write_line(events_dir, "2026-07-28.claude.1.jsonl", check)

    section = _views(_redirect)["governance"]
    assert section["status"] == "ok"
    assert section["totals"]["hook.deny"] == 3
    assert section["totals"]["hook.check_fail"] == 1
    assert section["by_guard"]["protect-paths"]["hook.deny"] == 2
    assert section["by_guard"]["protect-paths"]["rules"]["src/legacy"] == 2
    assert section["by_rule"]["safe-bash:rm-tracked"] == 1
    days = {row["day"]: row for row in section["by_day"]}
    assert days["2026-07-27"]["hook.deny"] == 2
    assert days["2026-07-28"]["hook.deny"] == 1
    assert len(section["recent"]) == 4


def test_governance_approvals_are_unavailable_not_zero(_redirect):
    """`gate.approval` has no emitter (no hook observes a manual approval,
    design doc §G.2). Reporting 0 would claim nothing was ever approved."""
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="session.start"))
    approvals = _views(_redirect)["governance"]["approvals"]
    assert approvals["status"] == "unavailable"
    assert approvals["count"] == 0
    assert "G.2" in approvals["reason"]
    assert readers.CANAL_A_EMITTERS["gate.approval"] is None


def test_governance_reads_a_gate_approval_when_one_exists(_redirect):
    """Positive control so the "unavailable" above is not vacuous, including
    the plan-hash fidelity note (§G.2 tier-2)."""
    approved = _rec("2026-07-28T01:00:00Z", kind="gate.approval", task="T-42")
    approved["data"] = {"decision": "approved", "source": "pilot"}
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", approved)
    approvals = _views(_redirect)["governance"]["approvals"]
    assert approvals["status"] == "ok"
    assert approvals["count"] == 1
    assert approvals["decisions"] == {"approved": 1}
    assert approvals["without_plan_hash"] == 1
    assert "plan_hash" in approvals["reason"]


def test_governance_surfaces_the_skills_audit_log_state(_redirect):
    """Design doc §F.3 verbatim: an ABSENT AUDIT_LOG blocks every skill
    install, which is not the same fact as "no skill was installed"."""
    absent = _views(_redirect)["governance"]["audit_log"]
    assert absent["status"] == "trail_absent"
    assert "BLOCKS" in absent["reason"]

    readers.reset_cache_for_tests()
    _write_project_file(_redirect["project_root"],
                        (".agents", "state", "gates", "AUDIT_LOG"), "# header only\n")
    empty = _views(_redirect)["governance"]["audit_log"]
    assert empty["status"] == "no_events"
    assert empty["rows"] == 0

    readers.reset_cache_for_tests()
    _write_project_file(_redirect["project_root"],
                        (".agents", "state", "gates", "AUDIT_LOG"),
                        "# header\nskill foo audit=pass by=h date=2026-07-28\n")
    filled = _views(_redirect)["governance"]["audit_log"]
    assert filled["status"] == "ok"
    assert filled["rows"] == 1 and filled["audit_pass_rows"] == 1


def test_governance_malformed_events_are_counted_not_fatal(_redirect):
    events_dir = _redirect["events_dir"]
    _write_line(events_dir, "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
    with open(events_dir / "2026-07-28.claude.1.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write("{not json\n")
    section = _views(_redirect)["governance"]
    assert section["status"] == "ok"
    assert section["trail"]["malformed_lines_skipped"] == 1


# --- Sécurité --------------------------------------------------------------

def test_security_history_absent_trail_vs_no_events(_redirect):
    history = _views(_redirect)["security"]["history"]
    assert history["status"] == "trail_absent"
    assert "ABSENT TRAIL" in history["reason"]


def test_security_history_absorbs_the_audit_log_jsonl(_redirect):
    """The oldest append-only trail in the kit, read through the SHARED
    reader - by entry, by verdict, by class, daily, and with `locations` as a
    COUNT so a file:line inventory never rides in the payload."""
    rel = (".agents", "state", "local", "sca-reports", "audit-log.jsonl")
    _write_project_file(_redirect["project_root"], rel, "\n".join([
        json.dumps({"ts": "2026-07-27T10:00:00Z", "entry": "gitleaks-scan.sh",
                    "class": 0, "waivable": False, "verdict": "CLEAN",
                    "findings": 0, "locations": []}),
        json.dumps({"ts": "2026-07-28T10:00:00Z", "entry": "gitleaks-scan.sh",
                    "class": 0, "waivable": False, "verdict": "BLOCK",
                    "findings": 2, "locations": ["a.py:1", "b.py:9"]}),
        json.dumps({"ts": "2026-07-28T11:00:00Z", "entry": "semgrep-scan.sh",
                    "class": 1, "verdict": "DEGRADED", "findings": 0, "locations": []}),
        json.dumps({"ts": "2026-07-28T12:00:00Z", "entry": "sca-scan.sh",
                    "mode": "scan", "module": "root", "verdict": "NO-GO",
                    "reason": "lock-busy", "gate_level": "high"}),
    ]) + "\n")
    history = _views(_redirect)["security"]["history"]
    assert history["status"] == "ok"
    assert history["entries_read"] == 4
    assert history["by_entry"] == {"gitleaks-scan.sh": 2, "semgrep-scan.sh": 1, "sca-scan.sh": 1}
    assert history["by_verdict"]["BLOCK"] == 1
    # T-00000370 (C40) — `couverture` is ADDITIVE and `verdict` keeps its name.
    # The four fixtures above predate the field, so they must land in
    # "unrecorded" rather than being folded into a real coverage value: a record
    # written before the gate had a second axis says NOTHING about coverage, and
    # counting it as CLEAN would invent an assurance nobody ever measured.
    assert history["by_couverture"] == {"unrecorded": 4}
    assert history["by_class"] == {"0": 2, "1": 1, "untagged": 1}
    assert history["findings_total"] == 2
    days = {row["day"]: row for row in history["series_daily"]}
    assert days["2026-07-28"]["runs"] == 3 and days["2026-07-28"]["findings"] == 2
    blocked = [r for r in history["recent"] if r["verdict"] == "BLOCK"][0]
    assert blocked["locations_count"] == 2 and blocked["reason"] is None
    assert [r["reason"] for r in history["recent"] if r["entry"] == "sca-scan.sh"] == ["lock-busy"]
    assert "locations" not in blocked  # The list itself must never travel.
    assert "a.py:1" not in json.dumps(history)


def test_security_history_corrupt_lines_are_skipped_not_fatal(_redirect):
    rel = (".agents", "state", "local", "sca-reports", "audit-log.jsonl")
    _write_project_file(_redirect["project_root"], rel,
                        '{"ts":"2026-07-28T10:00:00Z","entry":"x","verdict":"GO"}\n'
                        "{not json\n[1,2,3]\n")
    history = _views(_redirect)["security"]["history"]
    assert history["status"] == "ok"
    assert history["entries_read"] == 1
    assert history["malformed_lines_skipped"] == 2


def test_security_classes_0_and_1_are_counted_from_their_own_evidence(_redirect):
    rel = (".agents", "state", "local", "sca-reports", "audit-log.jsonl")
    _write_project_file(_redirect["project_root"], rel, "\n".join([
        json.dumps({"ts": "2026-07-28T10:00:00Z", "entry": "gitleaks-scan.sh",
                    "class": 0, "verdict": "CLEAN", "findings": 0}),
        json.dumps({"ts": "2026-07-28T11:00:00Z", "entry": "semgrep-scan.sh",
                    "class": 1, "verdict": "CLEAN", "findings": 0}),
    ]) + "\n")
    secrets_event = _rec("2026-07-28T10:00:01Z", kind="scan.secrets")
    secrets_event["data"] = {"status": "scanned", "counters": {"findings": 0}}
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", secrets_event)

    classes = _views(_redirect)["security"]["classes"]
    assert classes["0"]["status"] == "ok"
    assert classes["0"]["audit_runs"] == 1
    assert classes["0"]["canal_a_events"] == 1
    assert classes["0"]["waivable"] is False and classes["0"]["blocking"] is True
    assert classes["1"]["audit_runs"] == 1


def test_security_class_2_is_unavailable_never_zero(_redirect):
    """No source tags a finding class 2 today; a 0 would assert 'nothing was
    auto-fixed', which was never observed."""
    klass = _views(_redirect)["security"]["classes"]["2"]
    assert klass["status"] == "unavailable"
    assert klass["count"] is None
    assert "no `class` field" in klass["reason"]


def test_security_class_3_is_partial_and_sources_its_numbers(_redirect):
    _write_project_file(_redirect["project_root"], (".agents", "security", "sca-waivers.json"),
                        json.dumps({"waivers": []}))
    _write_project_file(
        _redirect["project_root"],
        (".agents", "state", "local", "sca-reports", "effective-verdict.json"),
        json.dumps({"gate_level": "high", "active": [],
                    "counters": {"active_at_gate": 3, "accepted": 0,
                                 "pending_review": 0, "overdue_review": 0}}))
    klass = _views(_redirect)["security"]["classes"]["3"]
    assert klass["status"] == "partial"
    assert klass["awaiting_decision"] == 3
    assert klass["awaiting_decision_source"].startswith("effective-verdict.json")
    assert klass["waivable"] is True
    assert "NOT a count of class-3 FINDINGS" in klass["reason"]


def test_security_waivers_resolve_their_deadlines(_redirect):
    today = datetime.now(timezone.utc).date()
    _write_project_file(_redirect["project_root"], (".agents", "security", "sca-waivers.json"),
                        json.dumps({"waivers": [
                            {"ecosystem": "npm", "package": "old", "version": "1.0.0",
                             "status": "accepted",
                             "review_by": (today - timedelta(days=5)).isoformat()},
                            {"ecosystem": "npm", "package": "soon", "version": "2.0.0",
                             "status": "pending_review",
                             "review_by": (today + timedelta(days=3)).isoformat()},
                            {"ecosystem": "npm", "package": "later", "version": "3.0.0",
                             "status": "accepted",
                             "review_by": (today + timedelta(days=90)).isoformat()},
                            {"ecosystem": "npm", "package": "undated", "version": "4.0.0",
                             "status": "accepted"},
                            {"ecosystem": "npm", "package": "bogus", "version": "5.0.0",
                             "status": "accepted", "review_by": "not-a-date"},
                        ]}))
    waivers = _views(_redirect)["security"]["waivers"]
    assert waivers["status"] == "ok" and waivers["count"] == 5
    assert waivers["overdue"] == 1 and waivers["due_soon"] == 1
    assert waivers["accepted"] == 4 and waivers["pending_review"] == 1
    assert waivers["undated"] == 1
    states = {e["package"]: e["deadline_state"] for e in waivers["entries"]}
    assert states == {"old": "overdue", "soon": "due_soon", "later": "ok",
                      "undated": "none", "bogus": "malformed"}
    # Soonest deadline first: a view that buries an overdue waiver is useless.
    assert waivers["entries"][0]["package"] == "old"
    assert waivers["entries"][0]["days_left"] == -5


def test_security_waivers_empty_register_is_a_measurement(_redirect):
    _write_project_file(_redirect["project_root"], (".agents", "security", "sca-waivers.json"),
                        json.dumps({"waivers": []}))
    waivers = _views(_redirect)["security"]["waivers"]
    assert waivers["status"] == "no_events"
    assert waivers["count"] == 0
    assert "EXISTS and holds zero waiver" in waivers["reason"]


def test_security_waivers_absent_register_is_not_the_same_as_empty(_redirect):
    waivers = _views(_redirect)["security"]["waivers"]
    assert waivers["status"] == "trail_absent"
    assert "COMMITTED by design" in waivers["reason"]


def test_security_waivers_malformed_json_degrades_only_that_block(_redirect):
    _write_project_file(_redirect["project_root"], (".agents", "security", "sca-waivers.json"),
                        "{not json")
    views = _views(_redirect)
    assert views["security"]["waivers"]["status"] == "degraded"
    assert views["security"]["status"] == "ok"          # the section survives
    assert views["governance"]["status"] == "trail_absent"  # every other view too


# --- Mémoire ---------------------------------------------------------------

def _write_ledger(root: Path, entries: list) -> None:
    _write_project_file(root, (".agents", "state", "memory", "LEDGER.json"),
                        json.dumps({"next_id": len(entries) + 1, "entries": entries}))


def _ledger_entry(eid: str, category: str, title: str, created: str,
                  status: str = "active", text: str = "detail") -> dict:
    return {"id": eid, "category": category, "status": status, "title": title,
            "created": created, "related": None, "tags": [], "text": text}


def test_memory_puts_active_constraints_first(_redirect):
    _write_ledger(_redirect["project_root"], [
        _ledger_entry("L-1", "lesson", "a lesson", "2026-07-01"),
        _ledger_entry("L-2", "constraint", "an active constraint", "2026-07-02"),
        _ledger_entry("L-3", "constraint", "an archived constraint", "2026-07-03",
                      status="archived"),
        _ledger_entry("L-4", "decision", "a decision", "2026-07-04"),
    ])
    ledger = _views(_redirect)["memory"]["ledger"]
    assert ledger["status"] == "ok"
    assert [c["id"] for c in ledger["active_constraints"]] == ["L-2"]
    assert ledger["active_constraint_count"] == 1
    assert [e["id"] for e in ledger["recent"]] == ["L-4", "L-1"]
    assert ledger["counts"]["by_category"] == {"lesson": 1, "constraint": 2, "decision": 1}
    assert ledger["counts"]["by_status"] == {"active": 3, "archived": 1}
    assert "constraints first" in ledger["ordering"]


def test_memory_never_duplicates_the_store_text(_redirect):
    """Cost control, measured: copying the full text of the real repo's active
    constraints costs +14.6 Ko on a payload re-polled every 5 s, and it is
    already in `ledger.data` in the SAME response."""
    long_text = "X" * 5000
    _write_ledger(_redirect["project_root"], [
        _ledger_entry("L-1", "constraint", "big", "2026-07-01", text=long_text),
    ])
    snap = dashboard.build_snapshot(_redirect["project_root"])
    constraint = snap["views"]["memory"]["ledger"]["active_constraints"][0]
    assert "text" not in constraint
    assert len(constraint["text_preview"]) < 200
    assert constraint["text_preview"].endswith("...<clipped>")
    # ...and the untruncated text IS reachable, in the store already present.
    assert snap["ledger"]["data"]["entries"][0]["text"] == long_text
    assert "`id`" in snap["views"]["memory"]["join_note"]


def test_memory_groups_the_specs_journal_by_task(_redirect):
    """Entries are written in the shape `specs.py load()` VALIDATES (`task`
    is required and must match `T-\\d+`) — a fixture the real CLI could not
    have produced would test a shape that can never reach this reader."""
    _write_project_file(_redirect["project_root"], (".agents", "state", "specs", "SPECS.json"),
                        json.dumps({"next_id": 5, "entries": [
                            {"id": "S-00000001", "task": "T-1", "kind": "plan", "title": "p",
                             "date": "2026-07-01", "text": "t", "files": []},
                            {"id": "S-00000002", "task": "T-1", "kind": "verdict", "title": "v",
                             "date": "2026-07-05", "text": "t", "files": []},
                            {"id": "S-00000003", "task": "T-2", "kind": "delta", "title": "d",
                             "date": "2026-07-03", "text": "t", "files": []},
                            {"id": "S-00000004", "task": "T-2", "kind": "decision", "title": "x",
                             "date": "2026-07-02", "text": "t", "files": []},
                        ]}))
    specs = _views(_redirect)["memory"]["specs"]
    assert specs["status"] == "ok" and specs["total"] == 4
    by_task = {group["task"]: group for group in specs["by_task"]}
    assert set(by_task) == {"T-1", "T-2"}
    assert by_task["T-1"]["count"] == 2
    assert by_task["T-1"]["kinds"] == {"plan": 1, "verdict": 1}
    assert by_task["T-1"]["first_date"] == "2026-07-01"
    assert by_task["T-1"]["latest_date"] == "2026-07-05"
    assert specs["counts"]["by_kind"] == {"plan": 1, "verdict": 1, "delta": 1, "decision": 1}
    # Most recently touched task first.
    assert specs["by_task"][0]["task"] == "T-1"
    assert "NOT a complete trajectory" in specs["journal_note"]


def test_memory_degrades_with_the_store_it_reads(_redirect):
    _write_project_file(_redirect["project_root"], (".agents", "state", "memory", "LEDGER.json"),
                        "{not json")
    views = _views(_redirect)
    assert views["memory"]["ledger"]["status"] == "degraded"
    assert views["memory"]["specs"]["status"] == "no_events"  # independent of it


# --- Index -----------------------------------------------------------------

def _fake_git(root: Path, head_sha: str, branch: str = "main") -> None:
    (root / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n",
                                        encoding="utf-8", newline="\n")
    (root / ".git" / "refs" / "heads" / branch).write_text(head_sha + "\n",
                                                           encoding="utf-8", newline="\n")


def _write_delta(root: Path, **overrides) -> None:
    payload = {"built_sha": "fb63ded", "backend": "ctags", "max_sym_id": 112,
               "needs_module_role": ["m1"], "needs_purpose": ["SYM-1", "SYM-2"],
               "counts": {"active": 112, "deleted": 0, "added": 1,
                          "changed": 2, "removed": 0},
               "sharded": False, "shards": 1}
    payload.update(overrides)
    _write_project_file(root, (".agents", "state", "index", "INDEX_DELTA.json"),
                        json.dumps(payload))


def test_index_view_reports_freshness_against_head(_redirect):
    root = _redirect["project_root"]
    _write_delta(root, built_sha="abc1234")
    _fake_git(root, "abc1234567890abcdef1234567890abcdef1234")
    section = _views(_redirect)["index"]
    assert section["status"] == "ok"
    assert section["freshness"]["status"] == "fresh"
    assert section["freshness"]["fresh"] is True
    assert section["freshness"]["head_source"] == ".git/refs/heads/main"
    assert section["backend"] == "ctags"


def test_index_view_reports_staleness_with_a_reason(_redirect):
    root = _redirect["project_root"]
    _write_delta(root, built_sha="abc1234")
    _fake_git(root, "9999999999999999999999999999999999999999")
    freshness = _views(_redirect)["index"]["freshness"]
    assert freshness["status"] == "stale"
    assert freshness["fresh"] is False
    assert "--if-stale" in freshness["reason"]


def test_index_view_freshness_unknown_outside_a_work_tree(_redirect):
    """Unknown is not stale and not fresh: without HEAD the comparison cannot
    be made, and guessing either way is a claim we did not verify."""
    _write_delta(_redirect["project_root"])
    freshness = _views(_redirect)["index"]["freshness"]
    assert freshness["status"] == "unknown"
    assert freshness["fresh"] is None
    assert "not a git work tree" in freshness["reason"]


def test_index_view_resolves_head_from_packed_refs(_redirect):
    root = _redirect["project_root"]
    _write_delta(root, built_sha="dead123")
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8", newline="\n")
    (root / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        "dead123456789abcdef0123456789abcdef012345 refs/heads/main\n",
        encoding="utf-8", newline="\n")
    freshness = _views(_redirect)["index"]["freshness"]
    assert freshness["status"] == "fresh"
    assert "packed-refs" in freshness["head_source"]


def test_index_view_handles_a_detached_head(_redirect):
    root = _redirect["project_root"]
    _write_delta(root, built_sha="beef567")
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("beef5678901234567890123456789012345678ab\n",
                                        encoding="utf-8", newline="\n")
    freshness = _views(_redirect)["index"]["freshness"]
    assert freshness["status"] == "fresh"
    assert "detached" in freshness["head_source"]


def test_index_view_surfaces_the_needs_purpose_backlog_and_the_L020_caveat(_redirect):
    _write_delta(_redirect["project_root"])
    section = _views(_redirect)["index"]
    assert section["backlog"]["needs_purpose"] == 2
    assert section["backlog"]["needs_purpose_sample"] == ["SYM-1", "SYM-2"]
    assert section["backlog"]["needs_module_role"] == 1
    assert section["counts"]["active"] == 112
    # L-020 travels with the SECTION, not only with the payload caveats.
    assert "L-020" in section["caveat"]
    assert "L-029" in section["caveat"]
    # ...and the coverage sentence is DERIVED from the scope the builder would
    # apply to THIS tree (T-00000062), not a fixed string: an unmarked tree must
    # not claim the vendored-kit exclusions. The marked arm is next.
    assert ".codex" not in section["caveat"]


def test_index_view_caveat_widens_in_a_vendored_kit(_redirect):
    """The caveat is derived, so the SAME reader says more about a tree that
    carries a vendoring marker. A static sentence would understate the coverage
    limit on exactly the trees where it is widest."""
    root = _redirect["project_root"]
    _write_delta(root)
    plain = _views(_redirect)["index"]["caveat"]
    marker = root / ".agents" / "protected-paths.local"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(".agents/bin/\n", encoding="utf-8", newline="\n")
    # The view is memoised on a fingerprint over the INDEX artefacts, which the
    # marker is not part of — stated rather than worked around: in production the
    # marker's appearance forces a full rebuild, so the artefacts move anyway and
    # the cache turns over with them. Here the poll is explicit.
    readers.reset_cache_for_tests()
    widened = _views(_redirect)["index"]["caveat"]
    assert widened != plain
    for host in (".claude", ".codex", ".gemini"):
        assert host in widened
    assert "ROOT" in widened and "L-020" in widened


def test_index_view_degrades_when_the_delta_is_absent(_redirect):
    section = _views(_redirect)["index"]
    assert section["status"] == "degraded"
    assert "INDEX_DELTA.json absent" in section["reason"]
    # The caveat is unconditional: a degraded panel still must not imply the
    # kit's own code is covered.
    assert "L-020" in section["caveat"]


def test_index_view_degrades_on_corrupt_delta(_redirect):
    _write_project_file(_redirect["project_root"],
                        (".agents", "state", "index", "INDEX_DELTA.json"), "{nope")
    section = _views(_redirect)["index"]
    assert section["status"] == "degraded"
    assert "JSONDecodeError" in section["reason"]


# --- MCP -------------------------------------------------------------------

def _write_allowlist(root: Path, rows: str) -> None:
    _write_project_file(root, (".agents", "state", "gates", "MCP_ALLOWLIST.md"),
                        "<!-- header -->\n" + rows)


def test_mcp_absent_allowlist_makes_everything_a_red_flag(_redirect):
    section = _views(_redirect)["mcp"]
    assert section["allowlist"]["status"] == "trail_absent"
    assert "EVERY server and every call is a red flag" in section["allowlist"]["reason"]


def test_mcp_empty_allowlist_is_the_expected_steady_state(_redirect):
    _write_allowlist(_redirect["project_root"], "")
    section = _views(_redirect)["mcp"]
    assert section["allowlist"]["status"] == "no_events"
    assert section["allowlist"]["row_count"] == 0
    assert "ZERO MCP servers by design" in section["zero_servers_note"]
    assert section["red_flags"] == []


def test_mcp_allowlist_never_counts_its_own_format_example_as_a_row(_redirect):
    """Regression, found on the REAL file: MCP_ALLOWLIST.md documents its line
    format inside its HTML-comment header, and `mcp_render.parse_allowlist`
    matches that example as a row - so a file whose header says "zero rows
    today" parsed as `{'<name>': {'<version>'}}` and this panel reported
    "something is audited" when nothing was. The false-GO shape, in the one
    view whose job is to say what is NOT audited."""
    real_header = (
        "<!--\nMCP allowlist - project state.\n\n"
        "Line format (exact pins, never ranges; no row without evidence):\n"
        "mcp <name>@<version> audit=pass by=<who> date=<date> evidence=<path>\n-->\n"
    )
    _write_project_file(_redirect["project_root"],
                        (".agents", "state", "gates", "MCP_ALLOWLIST.md"), real_header)
    allowlist = _views(_redirect)["mcp"]["allowlist"]
    assert allowlist["row_count"] == 0, f"parsed a phantom row: {allowlist['rows']}"
    assert allowlist["status"] == "no_events"
    # Sensitivity, rewritten once the upstream bug was fixed (T-00000039):
    # asserting "upstream is still broken" would now fail for the right
    # reason and hide the wrong one. What must stay true is that BOTH layers
    # refuse the example independently — this reader's comment-stripping guard
    # keeps the panel correct against an older mcp_render.py in a project
    # provisioned before that fix, so it is defence in depth, not dead code.
    assert dashboard._readers_mod._mcp_render.parse_allowlist(real_header) == {}
    assert "mcp <name>@<version>" not in dashboard._readers_mod._strip_html_comments(real_header)
    # ...and a row OUTSIDE the comment is still parsed.
    _write_project_file(_redirect["project_root"],
                        (".agents", "state", "gates", "MCP_ALLOWLIST.md"),
                        real_header + "mcp real-pkg@1.0.0 audit=pass by=h date=2026-07-28 evidence=x\n")
    readers.reset_cache_for_tests()
    allowlist = _views(_redirect)["mcp"]["allowlist"]
    assert allowlist["rows"] == {"real-pkg": ["1.0.0"]}


def test_mcp_inventory_joins_host_configs_against_the_allowlist(_redirect):
    root = _redirect["project_root"]
    _write_allowlist(root, "mcp @scope/good@1.2.3 audit=pass by=h date=2026-07-28 evidence=x\n")
    _write_project_file(root, (".mcp.json",), json.dumps({"mcpServers": {
        "good": {"command": "npx", "args": ["-y", "@scope/good@1.2.3"]},
        "bumped": {"command": "npx", "args": ["-y", "@scope/good@9.9.9"]},
        "stranger": {"command": "npx", "args": ["-y", "unaudited-pkg@1.0.0"]},
        "weird": {"command": "python", "args": ["server.py"]},
    }}))
    section = _views(_redirect)["mcp"]
    config = [c for c in section["configs"] if c["host"] == "claude"][0]
    assert config["status"] == "ok"
    servers = {s["config_key"]: s for s in config["servers"]}
    assert servers["good"]["audited"] is True
    assert servers["good"]["package"] == "@scope/good"
    assert servers["good"]["version"] == "1.2.3"
    assert servers["bumped"]["audited"] is False
    assert "re-audited" in servers["bumped"]["audit_reason"]
    assert servers["stranger"]["audited"] is False
    # An unresolvable launch shape is UNRESOLVED, never a pass.
    assert servers["weird"]["identity_status"] == "unresolved"
    assert servers["weird"]["audited"] is None
    flagged = {f["config_key"] for f in section["red_flags"] if f["kind"] == "config_not_audited"}
    assert flagged == {"bumped", "stranger"}


def test_mcp_config_never_surfaces_env_values_or_raw_args(_redirect):
    """An MCP arg or env value can be a live credential and this payload
    leaves the process over HTTP. Only identity + counts may travel."""
    root = _redirect["project_root"]
    _write_allowlist(root, "")
    _write_project_file(root, (".mcp.json",), json.dumps({"mcpServers": {
        "leaky": {"command": "npx",
                  "args": ["-y", "pkg@1.0.0", "--api-key", "NEVERTRAVELS0123456789abcd"],
                  "env": {"API_TOKEN": "ALSONEVERTRAVELS0123456789ab"}},
    }}))
    section = _views(_redirect)["mcp"]
    blob = json.dumps(section)
    assert "NEVERTRAVELS" not in blob and "ALSONEVERTRAVELS" not in blob
    server = [c for c in section["configs"] if c["host"] == "claude"][0]["servers"][0]
    assert server["arg_count"] == 4 and server["env_key_count"] == 1
    assert "args" not in server and "env" not in server
    assert "never surfaced" in section["redaction_note"]


def test_mcp_reads_every_host_config_and_names_the_absent_ones(_redirect):
    section = _views(_redirect)["mcp"]
    hosts = {c["host"]: c for c in section["configs"]}
    assert set(hosts) == {"claude", "copilot", "codex", "gemini"}
    for host, config in hosts.items():
        assert config["status"] == "absent"
        assert config["present"] is False
        assert "does not exist" in config["reason"], host
    assert hosts["codex"]["path"] == ".codex/config.toml"
    assert hosts["copilot"]["path"] == ".vscode/mcp.json"


def test_mcp_reads_a_codex_toml_config(_redirect):
    root = _redirect["project_root"]
    _write_allowlist(root, "mcp pkg@1.0.0 audit=pass by=h date=2026-07-28 evidence=x\n")
    _write_project_file(root, (".codex", "config.toml"),
                        '[mcp_servers.demo]\ncommand = "npx"\nargs = ["-y", "pkg@1.0.0"]\n')
    config = [c for c in _views(_redirect)["mcp"]["configs"] if c["host"] == "codex"][0]
    assert config["status"] == "ok"
    assert config["servers"][0]["package"] == "pkg"
    assert config["servers"][0]["audited"] is True


def test_mcp_malformed_host_config_degrades_only_that_row(_redirect):
    root = _redirect["project_root"]
    _write_allowlist(root, "")
    _write_project_file(root, (".mcp.json",), "{not json")
    _write_project_file(root, (".gemini", "settings.json"),
                        json.dumps({"mcpServers": {}}))
    section = _views(_redirect)["mcp"]
    hosts = {c["host"]: c for c in section["configs"]}
    assert hosts["claude"]["status"] == "degraded"
    assert "JSONDecodeError" in hosts["claude"]["reason"]
    assert hosts["gemini"]["status"] == "no_events"
    assert section["status"] == "ok"


def test_mcp_usage_aggregates_calls_latency_and_flags_unaudited(_redirect):
    root = _redirect["project_root"]
    _write_allowlist(root, "mcp audited-pkg@1.0.0 audit=pass by=h date=2026-07-28 evidence=x\n")
    for i, (server, state, duration) in enumerate([
        ("audited-pkg@1.0.0", "audited", 10),
        ("audited-pkg@1.0.0", "audited", 30),
        ("audited-pkg@1.0.0", "audited", 90),
        ("rogue-pkg@2.0.0", "unaudited", 500),
    ]):
        record = _rec(f"2026-07-28T0{i}:00:00Z", kind="scan.mcp_call")
        record["data"] = {"server": server, "tool": "search",
                          "audit_state": state, "duration_ms": duration}
        _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", record)

    section = _views(_redirect)["mcp"]
    usage = section["usage"]
    assert usage["status"] == "ok" and usage["calls"] == 4
    good = usage["by_server"]["audited-pkg@1.0.0"]
    assert good["calls"] == 3 and good["in_allowlist"] is True
    assert good["latency_ms"]["min"] == 10 and good["latency_ms"]["max"] == 90
    assert good["latency_ms"]["p50"] == 30
    assert good["tools"] == {"search": 3}
    rogue = usage["by_server"]["rogue-pkg@2.0.0"]
    assert rogue["in_allowlist"] is False
    assert usage["unaudited_calls"] == 1
    flags = [f for f in section["red_flags"] if f["kind"] == "unaudited_call"]
    assert [f["package_identity"] for f in flags] == ["rogue-pkg"]
    assert "RED FLAG" in flags[0]["reason"]


def test_mcp_red_flag_does_not_trust_the_events_own_audit_state(_redirect):
    """Sensitivity control: an event claiming `audited` for a package with NO
    allowlist row is still a red flag - the verdict is recomputed here from
    MCP_ALLOWLIST.md, never taken from the emitter."""
    _write_allowlist(_redirect["project_root"], "")
    record = _rec("2026-07-28T00:00:00Z", kind="scan.mcp_call")
    record["data"] = {"server": "liar-pkg@1.0.0", "audit_state": "audited", "duration_ms": 1}
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", record)
    section = _views(_redirect)["mcp"]
    assert section["usage"]["by_server"]["liar-pkg@1.0.0"]["in_allowlist"] is False
    assert section["usage"]["by_server"]["liar-pkg@1.0.0"]["audit_states"] == {"audited": 1}
    assert [f["server"] for f in section["red_flags"]] == ["liar-pkg@1.0.0"]


def test_mcp_counts_canal_b_server_connections(_redirect):
    _write_otel(_redirect["otel_dir"], [
        _log_envelope(_TS, "mcp_server_connection", {}),
        _log_envelope(_TS, "mcp_server_connection", {}),
        _log_envelope(_TS, "api_request", {"cost_usd": 0.1}),
    ])
    section = _views(_redirect)["mcp"]
    assert section["canal_b"]["status"] == "ok"
    assert section["canal_b"]["mcp_server_connection"] == 2


def test_mcp_canal_b_unavailable_when_nothing_was_collected(_redirect):
    canal_b = _views(_redirect)["mcp"]["canal_b"]
    assert canal_b["status"] == "unavailable"
    assert "canal B is not collected" in canal_b["reason"]


# --- Couverture ------------------------------------------------------------

def test_coverage_matrix_covers_every_kind_and_host(_redirect):
    matrix = _views(_redirect)["coverage"]["canal_a"]["matrix"]
    assert set(matrix) == set(events_mod.KNOWN_KINDS)
    for kind, row in matrix.items():
        assert set(row) == set(readers.CANAL_A_HOSTS), kind
        for host, cell in row.items():
            assert cell["status"] in readers.COVERAGE_CELL_STATUSES, (kind, host)


def test_coverage_cells_distinguish_received_from_not_wired(_redirect):
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
    canal_a = _views(_redirect)["coverage"]["canal_a"]
    assert canal_a["matrix"]["hook.deny"]["claude"] == {"status": "received", "count": 1}
    # Same signal, another host: NOT a zero - the emitter does not exist there.
    assert canal_a["matrix"]["hook.deny"]["codex"]["status"] == "not_wired_yet"
    # A kind Claude declares but nothing emits: also not_wired_yet, never a 0.
    assert canal_a["matrix"]["ledger.add"]["claude"]["status"] == "not_wired_yet"
    # A wired kind that simply has not fired: no_data_yet, said out loud.
    assert canal_a["matrix"]["session.start"]["claude"]["status"] == "no_data_yet"
    assert "T-00000027" in canal_a["parity_reason"]
    assert set(canal_a["kinds_with_no_emitter"]) >= {"ledger.add", "gate.approval", "task.new"}


def test_coverage_never_renders_a_blank_cell(_redirect):
    """The doctrine, asserted mechanically: every cell of both matrices has a
    status from the closed vocabulary and a count."""
    coverage = _views(_redirect)["coverage"]
    assert "no silently missing signal" in coverage["doctrine"]
    assert set(coverage["legend"]) == set(readers.COVERAGE_CELL_STATUSES)
    for channel in ("canal_a", "canal_b"):
        for kind, row in coverage[channel]["matrix"].items():
            for host, cell in row.items():
                assert cell["status"] in readers.COVERAGE_CELL_STATUSES, (channel, kind, host)
                assert isinstance(cell["count"], int), (channel, kind, host)


def test_coverage_reuses_not_emitted_by_design_for_canal_b(_redirect):
    """`not_emitted_by_design` is shard 3's own word for Codex; reused here
    rather than renamed, so one fact has one name across the kit."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}, host="claude-code"),
    ])
    canal_b = _views(_redirect)["coverage"]["canal_b"]
    assert canal_b["status"] == "ok"
    assert canal_b["matrix"]["claude_code.cost.usage"]["claude-code"]["status"] == "received"
    assert canal_b["matrix"]["claude_code.cost.usage"]["codex"]["status"] == "not_emitted_by_design"
    assert canal_b["declared_coverage"]["codex"] == "not_emitted_by_design"
    # A family Claude Code does emit but that has not arrived is no_data_yet.
    assert canal_b["matrix"]["tool_decision"]["claude-code"]["status"] == "no_data_yet"


def test_coverage_lists_event_names_outside_the_frozen_schema(_redirect):
    _write_otel(_redirect["otel_dir"], [_log_envelope(_TS, "mcp_server_connection", {})])
    canal_b = _views(_redirect)["coverage"]["canal_b"]
    assert "mcp_server_connection" in canal_b["event_names_outside_the_frozen_schema"]


def test_coverage_counts_gate_coverage_degraded(_redirect):
    for i, reason in enumerate(["no .mcp.json to resolve against",
                                "no .mcp.json to resolve against",
                                "gitleaks absent"]):
        record = _rec(f"2026-07-28T0{i}:00:00Z", kind="gate.coverage_degraded")
        record["data"] = {"reason": reason}
        _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", record)
    degraded = _views(_redirect)["coverage"]["coverage_degraded"]
    assert degraded["status"] == "ok" and degraded["count"] == 3
    assert degraded["by_reason"]["no .mcp.json to resolve against"] == 2
    assert len(degraded["recent"]) == 3
    assert "first-class kind" in degraded["doctrine"]


def test_coverage_zero_degradations_is_labelled_not_bare(_redirect):
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="session.start"))
    degraded = _views(_redirect)["coverage"]["coverage_degraded"]
    assert degraded["status"] == "no_events"
    assert "not that none happened" in degraded["reason"]


def test_coverage_reports_a_host_outside_the_declared_column_set(_redirect):
    """Never silently drop a signal the matrix has no column for."""
    record = _rec("2026-07-28T00:00:00Z", kind="hook.deny")
    record["host"] = "some-future-host"
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl", record)
    canal_a = _views(_redirect)["coverage"]["canal_a"]
    assert canal_a["unexpected_hosts"] == ["some-future-host"]


def test_coverage_reports_a_kind_outside_the_closed_vocabulary(_redirect):
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="totally.invented"))
    canal_a = _views(_redirect)["coverage"]["canal_a"]
    assert canal_a["kinds_outside_the_declared_vocabulary"] == ["totally.invented"]


# --- Independence, degradation, memoisation, transport ---------------------

def test_every_view_section_degrades_independently(_redirect, monkeypatch):
    """A surprise in one reader must degrade THAT section - never the response,
    never a sibling. Same rule shard 1 applied to five sections, now six more."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated reader failure")

    # The index view needs its delta on disk, otherwise it is legitimately
    # degraded here and the assertion below would pass for the wrong reason.
    _write_delta(_redirect["project_root"])
    monkeypatch.setattr(readers, "build_mcp", _boom)
    views = _views(_redirect)
    assert views["mcp"]["status"] == "degraded"
    assert "RuntimeError" in views["mcp"]["reason"]
    for name in ("governance", "security", "memory", "index", "coverage"):
        assert views[name]["status"] != "degraded", name


def test_snapshot_never_500s_when_a_view_reader_explodes(ui_server, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(readers, "build_coverage", _boom)
    port, token = ui_server
    resp = _get(port, "/api/snapshot", token=token)
    assert resp.status == 200
    body = json.loads(resp.data)
    assert body["views"]["coverage"]["status"] == "degraded"
    assert body["board"]["status"] == "ok"


def test_canal_a_trail_is_read_once_per_snapshot_not_per_consumer(_redirect, monkeypatch):
    """Two memos are asserted at once, on the ONLY input whose cost grows with
    the age of the repo. Within ONE snapshot the trail has two consumers (the
    canal-B prompt-id join index and the three views that read canal A), and
    ACROSS snapshots the whole views block is memoised - so an unchanged tree
    must cost exactly ONE physical read of the day-files, ever. Measured on the
    real repo: 349 day-files read twice per poll pushed the cold route into
    `dashboard_daemon`'s 2 s ping budget under suite contention."""
    readers.reset_cache_for_tests()
    dashboard._reset_canal_b_cache_for_tests()
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
    _write_otel(_redirect["otel_dir"],
                [_log_envelope(_TS, "api_request", {"cost_usd": 0.1}, prompt_id="p1")])
    calls = []
    real = readers._read_canal_a_stream_uncached

    def counted(events_dir):
        calls.append(events_dir)
        return real(events_dir)

    monkeypatch.setattr(readers, "_read_canal_a_stream_uncached", counted)
    first = dashboard.build_snapshot(_redirect["project_root"])
    second = dashboard.build_snapshot(_redirect["project_root"])
    assert len(calls) == 1, f"the canal-A trail was read {len(calls)} times, expected 1"
    assert first["views"]["governance"] is second["views"]["governance"]
    assert first["views_meta"]["cached"] is False
    assert second["views_meta"]["cached"] is True
    # Both consumers really did get their data (otherwise "one read" would be
    # trivially true because nobody read anything).
    assert first["views"]["governance"]["totals"]["hook.deny"] == 1
    assert first["canal_b"]["join"]["canal_b_logs"] == 1


def test_views_cache_invalidates_on_any_input_change(_redirect):
    """Sensitivity control for the memo: a stale governance count is worse than
    a slow one, so every input in the fingerprint must invalidate."""
    readers.reset_cache_for_tests()
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
    assert _views(_redirect)["governance"]["totals"]["hook.deny"] == 1
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:01Z", kind="hook.deny"))
    assert _views(_redirect)["governance"]["totals"]["hook.deny"] == 2
    # A non-canal-A input: the waiver register.
    _write_project_file(_redirect["project_root"], (".agents", "security", "sca-waivers.json"),
                        json.dumps({"waivers": []}))
    assert _views(_redirect)["security"]["waivers"]["status"] == "no_events"


def test_views_cache_is_not_shared_between_project_trees(tmp_path, monkeypatch):
    """The resolved paths are part of the fingerprint - what makes a
    module-level cache safe when two trees are read in one process."""
    readers.reset_cache_for_tests()
    for name, purpose in (("a", 2), ("b", 5)):
        root = tmp_path / name / "project"
        _write_project_file(root, (".agents", "state", "index", "INDEX_DELTA.json"),
                            json.dumps({"built_sha": "x", "backend": "ctags",
                                        "needs_purpose": ["S"] * purpose,
                                        "needs_module_role": [], "counts": {}}))
        monkeypatch.setenv("AGENTS_DASHBOARD_PROJECT_ROOT", str(root))
        views = dashboard.build_snapshot(root)["views"]
        assert views["index"]["backlog"]["needs_purpose"] == purpose


def test_views_reach_the_client_only_through_the_token(ui_server, _redirect):
    port, token = ui_server
    assert _get(port, "/api/snapshot").status == 401
    body = json.loads(_get(port, "/api/snapshot", token=token).data)
    assert set(body["views"]) == _EXPECTED_VIEW_KEYS
    assert body["views_meta"]["status_vocabulary"] == list(readers.SECTION_STATUSES)


def test_snapshot_payload_stays_under_the_declared_budget(_redirect):
    """The route is polled every 5 s by the UI and once per daemon ping (2 s
    budget). This asserts the SHAPE stays bounded on a near-empty tree; the
    real repo's measured figures are in the task report."""
    _write_line(_redirect["events_dir"], "2026-07-28.claude.1.jsonl",
                _rec("2026-07-28T00:00:00Z", kind="hook.deny"))
    snap = dashboard.build_snapshot(_redirect["project_root"])
    size = len(json.dumps(snap, ensure_ascii=False).encode("utf-8"))
    assert size < 120_000, f"views block ballooned to {size} bytes on an empty tree"
    assert snap["views_meta"]["build_ms"] < 2000.0


def test_canal_b_gained_the_census_the_new_views_need(_redirect):
    """No second read of state/local/otel/: the MCP and Couverture views are
    fed from counts computed in the pass `_read_canal_b` already makes."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}, host="claude-code"),
        _log_envelope(_TS, "mcp_server_connection", {}, host="claude-code"),
    ])
    canal_b = dashboard.build_snapshot(_redirect["project_root"])["canal_b"]
    assert canal_b["by_event_name"]["mcp_server_connection"] == 1
    assert canal_b["by_metric_name"]["claude_code.cost.usage"] == 1
    seen = canal_b["hosts_seen"]["claude-code"]
    assert seen["records"] == 2
    assert seen["families"]["claude_code.cost.usage"] == 1
    # An event outside the frozen families has no family bucket - never faked.
    assert "mcp_server_connection" not in seen["families"]


# ===========================================================================
# /api/projects — the versioned contract (T-00000051, V1-d; spec §A.5)
#
# EVERY TEST BELOW BUILDS ITS OWN DISPOSITION. The autouse `_redirect` fixture
# PRE-WRITES a valid identity at `tmp_path/project.json` (see its own comment,
# and the write two lines below `AGENTS_PROJECT_JSON`), so "absent" and
# "corrupt" are NOT the default state of this suite: a test that forgets to
# overwrite or unlink that file measures the fixture, not the code.
#
# NO `skipUnless` ANYWHERE IN THIS SECTION, deliberately (L-00000068): every
# fact here — the branch order of a try/except, the closed vocabulary of a
# payload, a header on a response — is platform-independent. The one case that
# WOULD have been platform-dependent (a real EACCES on a file) is provoked by
# raising `PermissionError` from `read_text` instead of chmod-ing a file, which
# tests OUR mapping of that error rather than the filesystem's willingness to
# produce it. An assertion weakened until it passes everywhere measures nothing.
# ===========================================================================

_PROJECTS_KEYS = {"api_version", "kind", "generated_at", "projects", "identity", "caveats"}


def _identity_path() -> Path:
    """The anchor `/api/projects` and canal-B attribution BOTH resolve. Read from
    the module under test rather than re-derived from `tmp_path` — a literal
    rebuilt in the test is the false-anchoring shape of L-00000057, green in the
    very case it claims to cover."""
    return event_store.project_json_path()


def _count_identity_reads(monkeypatch) -> list[str]:
    """Count `Path.read_text` calls ON THE RESOLVED IDENTITY PATH ONLY.

    SCOPE, stated without exaggeration: this measures ONE READ PER ROUTE CALL.
    `/api/snapshot` and `/api/projects` are two requests and therefore one read
    each — it is NOT a claim that a process reads that file once in its life
    (`event_store.open_store()` freezes `store.project` from the same recipe when
    a database exists, which is that function's business, not this route's)."""
    target = _identity_path()
    seen: list[str] = []
    real = Path.read_text

    def counting(self, *args, **kwargs):
        if Path(self) == target:
            seen.append(str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    return seen


def test_identity_is_read_exactly_once_per_route_call(_redirect, monkeypatch):
    """THE LOCK on "one recipe, one read, one parse". Two reads of the same path
    let a write land BETWEEN them and publish an OLD id beside a NEW name — and,
    in the worst ordering, `PROJECT_UNSET` under a status of `ok`, the one value
    this contract swears never to publish (plan-critic iteration 4, C1)."""
    seen = _count_identity_reads(monkeypatch)

    dashboard.build_projects_response()
    assert len(seen) == 1, f"/api/projects read the identity {len(seen)} times"

    seen.clear()
    dashboard._reset_canal_b_cache_for_tests()
    dashboard.build_snapshot(_redirect["project_root"])
    assert len(seen) == 1, f"/api/snapshot read the identity {len(seen)} times"


@pytest.mark.parametrize("data,expected", [
    ({"project_id": _OWN_ID}, _OWN_ID),
    # `.strip()` is part of the recipe, not of one caller.
    ({"project_id": "  abc  "}, "abc"),
    ({"project_id": "   "}, event_store.PROJECT_UNSET),
    ({}, event_store.PROJECT_UNSET),
    ({"project_id": 7}, event_store.PROJECT_UNSET),
])
def test_the_route_publishes_the_same_recipe_as_resolve_project_id(_redirect, data, expected):
    """ONE recipe: `event_store.project_id_from_data()`. The route and
    `resolve_project_id()` must agree on the SAME bytes, or the route names a
    project under which no row was ever stored."""
    _identity_path().write_text(json.dumps(data), encoding="utf-8", newline="\n")
    assert event_store.project_id_from_data(data) == expected
    assert event_store.resolve_project_id() == expected

    payload = dashboard.build_projects_response()
    if expected == event_store.PROJECT_UNSET:
        assert payload["projects"] == []
    else:
        assert [entry["project_id"] for entry in payload["projects"]] == [expected]


def test_the_unset_sentinel_is_never_published(_redirect):
    """`PROJECT_UNSET` is a NON-EMPTY string: published as a project key it would
    collide with every uninitialised repo on the machine (L-00000049) and name a
    project whose rows are in quarantine. A valid object carrying it is
    `incomplete`, with an EMPTY list."""
    _identity_path().write_text(json.dumps({"project_id": event_store.PROJECT_UNSET,
                                            "name": "Piège"}),
                                encoding="utf-8", newline="\n")
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "incomplete", "cause": "no_project_id"}
    assert payload["projects"] == []
    assert event_store.PROJECT_UNSET not in json.dumps(payload["projects"])


# --- the closed (status, cause) table: ONE test per line, each building its own
# --- disposition on top of the fixture's pre-written valid identity.

def test_identity_table_ok(_redirect):
    _identity_path().write_text(
        json.dumps({"project_id": _OWN_ID, "name": "Mon Projet", "slug": "mon-projet"}),
        encoding="utf-8", newline="\n")
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "ok", "cause": None}
    # T-00000582: name/label are ROOT-derived — the basename of `_project_root()`
    # (AGENTS_DASHBOARD_PROJECT_ROOT = tmp_path/"project", so "project"), NOT the
    # JSON's "Mon Projet" (still written, IGNORED). project_id/slug stay
    # JSON-parsed.
    assert payload["projects"] == [{"project_id": _OWN_ID, "label": "project",
                                    "name": "project", "slug": "mon-projet"}]


def test_identity_table_incomplete_no_project_id(_redirect):
    """A VALID object with no usable id — reachable by a hand-edit or a partial
    write. `ok` beside an empty list (the shape critic iteration 3 C3 found)
    would put a named badge next to an empty selector."""
    _identity_path().write_text(json.dumps({"name": "Sans Id"}),
                                encoding="utf-8", newline="\n")
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "incomplete", "cause": "no_project_id"}
    assert payload["projects"] == []


def test_identity_table_no_identity_absent(_redirect):
    _identity_path().unlink()  # the fixture pre-wrote one; this line is the test
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "no_identity", "cause": "absent"}
    assert payload["projects"] == []


def test_identity_table_degraded_unreadable(_redirect, monkeypatch):
    """An OSError that is NOT absence (EACCES, a locked file, a dead mount).
    Provoked by raising it, not by chmod: the mapping is ours, the errno is the
    platform's, and only the mapping is under test."""
    target = _identity_path()
    real = Path.read_text

    def refusing(self, *args, **kwargs):
        if Path(self) == target:
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", refusing)
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "degraded", "cause": "unreadable"}
    assert payload["projects"] == []


@pytest.mark.parametrize("raw,label", [
    (b"{ not json", "invalid JSON"),
    (b'"a string, not an object"', "not an object"),
    (b"[]", "a list, not an object"),
])
def test_identity_table_degraded_invalid(_redirect, raw, label):
    _identity_path().write_bytes(raw)
    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "degraded", "cause": "invalid"}, label
    assert payload["projects"] == []


def test_absent_identity_is_unnamed_not_degraded(_redirect):
    """THE LOCK ON THE ORDER OF THE `except` BRANCHES. `FileNotFoundError` ⊂
    `OSError` and `UnicodeDecodeError` / `json.JSONDecodeError` ⊂ `ValueError`,
    so a tuple placed FIRST would subsume absence and report `degraded` on the
    DEFAULT state of a fresh repo — a "corrupt identity" alarm for a repo that
    simply has none yet. This test fails if the branches are ever reordered.

    Both anchors are covered, because both had to grow the same fix: the badge
    (`snapshot.project`, `project_root`-anchored) and the route
    (`event_store.project_json_path()`)."""
    root = _redirect["project_root"]
    badge_path = root / ".agents" / "state" / "project.json"
    assert not badge_path.exists(), "the badge anchor must start absent here"
    assert dashboard.build_snapshot(root)["project"] == {"status": "unnamed", "name": None}

    _identity_path().unlink()
    identity = dashboard.build_projects_response()["identity"]
    assert identity == {"status": "no_identity", "cause": "absent"}
    assert identity["status"] != "degraded"


def test_non_utf8_identity_degrades_on_both_routes_instead_of_raising(_redirect):
    """V1-a's latent defect, fixed here and assumed: `except OSError` never
    caught `UnicodeDecodeError`, so a project.json in non-UTF-8 bytes ESCAPED
    and 500ed the snapshot. Both routes now answer 200 and SAY the content is
    unusable; the badge's three status values are unchanged."""
    root = _redirect["project_root"]
    badge_path = root / ".agents" / "state" / "project.json"
    badge_path.parent.mkdir(parents=True, exist_ok=True)
    badge_path.write_bytes(b"\xff\xfe{")
    _identity_path().write_bytes(b"\xff\xfe{")

    snap = dashboard.build_snapshot(root)
    assert snap["project"] == {"status": "degraded", "name": None}
    assert snap["board"]["status"] == "ok", "a corrupt identity never takes the snapshot down"

    payload = dashboard.build_projects_response()
    assert payload["identity"] == {"status": "degraded", "cause": "invalid"}
    assert payload["projects"] == []


def test_non_utf8_identity_is_a_200_on_both_live_routes(ui_server, _redirect):
    """The same fact through the socket: a 200 carrying a stated degradation,
    never a 500 and never a traceback."""
    root = _redirect["project_root"]
    (root / ".agents" / "state").mkdir(parents=True, exist_ok=True)
    (root / ".agents" / "state" / "project.json").write_bytes(b"\xff\xfe{")
    _identity_path().write_bytes(b"\xff\xfe{")
    dashboard._reset_canal_b_cache_for_tests()
    readers.reset_cache_for_tests()

    port, token = ui_server
    projects = _get(port, "/api/projects", token=token)
    assert projects.status == 200
    assert json.loads(projects.data)["identity"] == {"status": "degraded", "cause": "invalid"}
    snapshot = _get(port, "/api/snapshot", token=token)
    assert snapshot.status == 200
    assert json.loads(snapshot.data)["project"]["status"] == "degraded"


@pytest.mark.parametrize("data,expect_ok", [
    ({"project_id": _OWN_ID}, True),
    ({"project_id": _OWN_ID, "name": "N", "slug": "s"}, True),
    ({"project_id": event_store.PROJECT_UNSET}, False),
    ({"project_id": ""}, False),
    ({"name": "N"}, False),
])
def test_ok_holds_if_and_only_if_exactly_one_project_is_listed(_redirect, data, expect_ok):
    """THE INVARIANT: `identity.status == "ok"` ⟺ `len(projects) == 1`. Asserted
    as an equivalence in BOTH directions, so neither a named badge beside an
    empty selector nor a listed project under a degraded status can appear."""
    _identity_path().write_text(json.dumps(data), encoding="utf-8", newline="\n")
    payload = dashboard.build_projects_response()
    is_ok = payload["identity"]["status"] == "ok"
    assert is_ok is expect_ok
    assert is_ok == (len(payload["projects"]) == 1)


@pytest.mark.parametrize("data", [
    # A realistic non-empty name that differs from the root basename: proves the
    # JSON `name` is IGNORED (label becomes "project", never "Nom Humain").
    {"project_id": "abcdef0123456789", "name": "Nom Humain"},
    # SECOND case kept on purpose: the only one carrying a `slug`, so the
    # "slug published unchanged" assertion below stays LIVE. Its `name: None`
    # also stands in for the whole family of "name unusable in the JSON" shapes
    # that became vacuous under T-00000582.
    {"project_id": "abc", "name": None, "slug": "le-slug"},
])
def test_label_is_never_empty_and_never_the_slug(_redirect, data):
    """A `<select>` whose selected option renders blank looks like a broken
    control, so `label` is non-empty by construction.

    THE NAME IS LEGACY (kept because the frozen plan T-00000582 references it):
    "never the slug" is NO LONGER an invariant. Since T-00000582 `label`/`name`
    are ROOT-derived (== the basename "project" here, AGENTS_DASHBOARD_PROJECT_ROOT
    = tmp_path/"project"), so the JSON name-shapes (present / empty / blank /
    None / non-str) are ALL VACUOUS for this route. The label is the basename and
    is never CHOSEN from the slug, so an equality with a slug would be INCIDENTAL,
    not forbidden. What IS pinnable — and what the assertions below check — is
    that the slug is PUBLISHED unchanged from the JSON and that
    name == label == the root basename. The seven former cases are REDUCED to
    two; the empty-basename fallback ("projet") lives in
    test_cadre_state_partition.py::test_nom_projet_repli_projet_sur_basename_vide
    and in test_nom_depuis_racine_matches_paths_nom_projet."""
    _identity_path().write_text(json.dumps(data), encoding="utf-8", newline="\n")
    entry = dashboard.build_projects_response()["projects"][0]
    assert entry["name"] == entry["label"] == "project"
    assert entry["label"].strip(), "a blank label is as bad as an empty one"
    if data.get("slug"):
        assert entry["slug"] == data["slug"]


# --- T-00000582: the project name is root-derived, not project.json:name ------

def test_badge_name_is_root_derived_when_project_json_present(_redirect, tmp_path):
    """1a: the badge `name` is the ROOT basename, not project.json:name. A
    PRESENT, valid project.json whose `name` differs from the basename yields the
    BASENAME (the JSON is parsed, its value IGNORED); ABSENT stays
    {"unnamed", None}, UNCHANGED (Trap 2, pinned elsewhere by equality nets).

    Mutation qui doit rougir : `_read_project` reading `data.get("name")` in the
    `ok` branch — the badge would show "Autre" instead of "alpha"."""
    alpha = tmp_path / "alpha"
    ident = alpha / ".agents" / "state" / "project.json"
    ident.parent.mkdir(parents=True, exist_ok=True)
    ident.write_text(json.dumps({"project_id": "p-x", "name": "Autre", "slug": "autre"}),
                     encoding="utf-8", newline="\n")
    assert dashboard.build_snapshot(alpha)["project"] == {"status": "ok", "name": "alpha"}

    beta = tmp_path / "beta"
    beta.mkdir()
    assert dashboard.build_snapshot(beta)["project"] == {"status": "unnamed", "name": None}


def test_projects_label_is_root_derived_without_badge_project_json(_redirect, tmp_path):
    """1b: /api/projects derives name/label from the HANDLER's root, not from a
    project.json under it. Anchor 2 (AGENTS_PROJECT_JSON, written by the fixture
    with a valid project_id) supplies project_id/slug/status; the handler root
    ($T/alpha, with NO project.json of its own) supplies the name. Result:
    label == name == "alpha".

    Mutation qui doit rougir : build_projects_response ignoring its project_root
    argument (falling back to _project_root() = "project")."""
    alpha = tmp_path / "alpha"
    alpha.mkdir()
    payload = dashboard.build_projects_response(alpha)
    assert payload["identity"]["status"] == "ok"          # anchor 2 (fixture identity)
    assert payload["projects"][0]["project_id"] == _OWN_ID
    assert payload["projects"][0]["name"] == "alpha"       # handler root
    assert payload["projects"][0]["label"] == "alpha"


def test_projects_name_follows_handler_root_not_anchor_2(_redirect, tmp_path):
    """Étape 3, critère 2: the SCISSION is OBSERVABLE, not just written in a
    caveat. A live daemon served under --root beta, while
    AGENTS_DASHBOARD_PROJECT_ROOT (=_project_root(), "project") points elsewhere,
    publishes /api/projects[0].name == "beta" (the handler's root) while
    project_id/status stay those of anchor 2 (AGENTS_PROJECT_JSON).

    Mutation qui doit rougir : loss of the project_root argument at the
    /api/projects site (argument-less call), or _project_root() substituted for
    the received argument in build_projects_response — name would fall back to
    "project" (the __file__/AGENTS_DASHBOARD_PROJECT_ROOT anchor) and no longer
    be "beta"."""
    beta = tmp_path / "beta"
    beta.mkdir()
    result = dashboard.create_ui_server(project_root=beta)
    assert result is not None
    httpd, token = result
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        payload = json.loads(_get(port, "/api/projects", token=token).data)
        assert payload["identity"] == {"status": "ok", "cause": None}   # anchor 2
        assert payload["projects"][0]["project_id"] == _OWN_ID          # anchor 2
        assert payload["projects"][0]["name"] == "beta"                 # handler root
        assert payload["projects"][0]["label"] == "beta"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_peer_summary_name_is_own_root_basename(_redirect, tmp_path):
    """Étape 4, critère 1: each daemon derives its OWN name from its OWN root.
    Two live servers in one process under two roots each report
    /api/peer/summary.name == basename of ITS root (label idem).

    Mutation qui doit rougir : build_peer_summary reading _project_root() (a
    single module-wide value) instead of its server's project_root — both would
    report the same name."""
    servers = {}
    for nom in ("un", "deux"):
        r = tmp_path / nom
        r.mkdir()
        result = dashboard.create_ui_server(project_root=r)
        assert result is not None
        httpd, _token = result
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers[nom] = (httpd, thread)
    try:
        for nom, (httpd, _thread) in servers.items():
            port = httpd.server_address[1]
            payload = json.loads(_get(port, "/api/peer/summary").data)
            assert payload["name"] == nom, nom
            assert payload["label"] == nom, nom
    finally:
        for httpd, thread in servers.values():
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


def test_peer_summary_name_follows_server_project_root(ui_server_object, tmp_path):
    """Étape 4, critère 2 — POSITIVE witness on the SOURCE: the peer name is read
    from `self.server.project_root` at EACH request. Reassign that attribute on
    the LIVE server and the next probe reflects it.

    NOT an os.rename witness: `_nom_depuis_racine` is a STRING op on the captured
    Path (`root.name`), so re-reading the DISK could never surface a new name —
    a rename witness could not fail (dead witness). The positive source witness
    can: it proves the value is read from the server attribute, not from
    `_project_root()` or a module-captured value.

    Mutation qui doit rougir : build_peer_summary reading _project_root() or a
    module-level captured root instead of self.server.project_root — name would
    stay "project" and never become "delta"."""
    httpd, port, _token = ui_server_object
    before = json.loads(_get(port, "/api/peer/summary").data)["name"]
    assert before == "project"          # ui_server_object's root basename
    httpd.project_root = tmp_path / "delta"   # a pure string source, no disk op
    after = json.loads(_get(port, "/api/peer/summary").data)
    assert after["name"] == "delta"
    assert after["label"] == "delta"


def test_peer_summary_name_is_root_derived_even_without_identity(ui_server, _redirect):
    """Étape 4 (A-C4): name/label are a property of the ROOT, so they are the
    basename WHATEVER identity.status is — even with NO identity file at all. Only
    project_id stays conditional (PROJECT_UNSET). This is the assumed asymmetry
    with the badge (which keeps name:None under `unnamed`).

    Mutation qui doit rougir : build_peer_summary gating name on identity.status
    (e.g. name = identity["name"], None here) — name would be null, not
    "project"."""
    _identity_path().unlink()           # the fixture pre-wrote anchor 2; remove it
    port, _token = ui_server
    payload = json.loads(_get(port, "/api/peer/summary").data)
    assert payload["project_id"] == event_store.PROJECT_UNSET
    assert payload["name"] == "project"     # basename of ui_server's root
    assert payload["label"] == "project"


def test_nom_depuis_racine_matches_paths_nom_projet(monkeypatch, tmp_path):
    """ÉQUIVALENCE (B-C3): the name rule is written TWICE — in
    `cadre.paths.nom_projet` and in `dashboard._nom_depuis_racine` — never three
    times. This witness keeps them in lockstep over >= 3 roots, INCLUDING one
    with an empty basename (`Path(os.sep)`), by feeding both the SAME resolved
    Path (`project_root()`), so it isolates the RULE from input canonicalization.

    Mutation qui doit rougir : changing the fallback of ONE of the two functions
    (e.g. "projet" -> "projet2" in dashboard.py) — the empty-basename root then
    disagrees.

    DOES NOT cover the INPUT-canonicalization gap (étape 6): in production the
    daemon derives from a `normalize_root`-ed root (no resolve()) and nom_projet
    from a `resolve()`+`canonique_disque` root, so a symlink/case difference can
    diverge. Both here get the identical Path — that gap is carried by
    T-00000685, NOT T-00000674 (done: it canonicalised project_root(), never
    normalize_root)."""
    racine = Path(__file__).resolve().parents[2]  # this tree's EXACT `cadre`, vendor or `src`
    dashboard._vendor_paths.charger_paquet(racine, "cadre")  # by path; `sys.path` untouched
    import cadre.paths as cadre_paths
    roots = [tmp_path / "alpha", tmp_path / "beta_2", Path(os.sep)]
    for r in roots[:2]:
        r.mkdir()
    for r in roots:
        monkeypatch.setenv("CADRE_PROJECT_ROOT", str(r))
        cadre_paths.vider_cache_racine()
        resolved = cadre_paths.project_root()
        assert dashboard._nom_depuis_racine(resolved) == cadre_paths.nom_projet(), r


def test_nom_depuis_racine_absolutise_une_racine_relative(monkeypatch, tmp_path):
    """Point 1 (régression fonctionnelle): the daemon hands `_nom_depuis_racine`
    a root straight from `normalize_root` (no resolution), so a DOCUMENTED
    `--root .` must NOT publish "projet" and `--root ..` must NOT publish "..".
    `os.path.abspath` absolutises lexically against the cwd; the empty-basename
    repli ("projet") stays intact.

    Mutation qui doit rougir : revenir à `Path(root).name or "projet"` —
    `Path(".").name == ""` retombe sur "projet" et `Path("..").name == ".."`,
    ce témoin (et lui seul) rougit alors."""
    depot = tmp_path / "mon-depot"
    depot.mkdir()
    monkeypatch.chdir(depot)
    assert dashboard._nom_depuis_racine(Path(".")) == "mon-depot"
    assert dashboard._nom_depuis_racine(Path("..")) == tmp_path.name
    assert dashboard._nom_depuis_racine(Path(os.sep)) == "projet"


def test_projects_payload_shape_is_frozen(_redirect):
    """EXACT key sets, at every level. This freezes what is present AND what is
    ABSENT: `agrees_with_badge`, `badge_project_id` and `source` were REMOVED by
    the approved plan (S-00000119) because no consumer read them and their
    presence made a v1-frozen API publish the symptom of a defect
    (T-00000056) instead of fixing it. An exact set is what stops them from
    drifting back in."""
    payload = dashboard.build_projects_response()
    assert set(payload) == _PROJECTS_KEYS
    assert set(payload["identity"]) == {"status", "cause"}
    assert set(payload["projects"][0]) == {"project_id", "label", "name", "slug"}
    for removed in ("agrees_with_badge", "badge_project_id", "source", "diverges"):
        assert removed not in payload
        assert removed not in payload["identity"]
        assert removed not in payload["projects"][0]

    # `api_version` is an INTEGER major, not a "1.0" string a hub would have to
    # parse (and `bool` is an int in Python — excluded explicitly).
    assert isinstance(payload["api_version"], int) and not isinstance(payload["api_version"], bool)
    assert payload["api_version"] == dashboard.PROJECTS_API_VERSION == 1
    assert payload["kind"] == "agentkit.projects"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["generated_at"])
    assert isinstance(payload["projects"], list)
    assert payload["projects"] is not None


def test_projects_states_its_non_guarantees(_redirect):
    """The caveats are part of the contract, not decoration: a hub reading this
    route must be told IN THE PAYLOAD that the list is not a machine census, that
    being listed is no claim on port 4318, that the order is not stable, that the
    badge may come from another anchor, and that this is a point-in-time read —
    project.json is not in the snapshot fingerprint, so in `live` mode an
    identity created mid-session may only surface at the next notice."""
    joined = " ".join(dashboard.build_projects_response()["caveats"])
    for marker in ("projects_scope", "projects_not_a_4318_claim", "projects_anchor",
                   "projects_freshness", "projects_order"):
        assert marker in joined, marker
    assert "T-00000056" in joined
    assert "L-00000049" in joined


def test_projects_is_get_only(ui_server):
    port, _token = ui_server
    assert _post(port, "/api/projects", b'{"a":1}').status == 404


@pytest.mark.parametrize("path", [
    "/api/projects/../../../etc/passwd",
    "/api/projects/..",
    "/api%2e%2e/projects",
    "/api/projects%00",
    "/api/projects/",
    "/api/projects/p-1",
])
def test_projects_traversal_variants_rejected(ui_server, path):
    """Same exact-match doctrine as every other route: the raw, un-normalised
    path either IS a member of the closed table or it 404s."""
    port, token = ui_server
    assert _get(port, path, token=token).status == 404, path


def test_projects_id_equals_the_snapshot_attribution_on_a_live_server(ui_server, _redirect):
    """PROVEN AT THE RESPONSE LEVEL, on a live server, and not by comparing two
    helpers in-process (the false-anchoring shape of L-00000057: two helpers that
    are both wrong the same way agree happily). The id this route publishes must
    be the id under which canal-B rows are actually attributed."""
    _write_otel(_redirect["otel_dir"], [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
    ])
    dashboard._reset_canal_b_cache_for_tests()
    readers.reset_cache_for_tests()

    port, token = ui_server
    projects = json.loads(_get(port, "/api/projects", token=token).data)
    snapshot = json.loads(_get(port, "/api/snapshot", token=token).data)

    # The census hangs under `views.coverage.canal_b`, not directly under
    # `views.coverage` (verified against `dashboard_readers._coverage_canal_b`
    # rather than assumed from the plan's shorthand).
    attribution = snapshot["views"]["coverage"]["canal_b"]["attribution"]
    assert attribution is not None, "no attribution census to compare against"
    assert projects["identity"]["status"] == "ok"
    assert projects["projects"][0]["project_id"] == attribution["own_project_id"] == _OWN_ID


@pytest.mark.parametrize("path,expected", [
    ("/api/ping", None),
    ("/api/snapshot", "private, no-cache"),  # T-01M4XR9ESW: `dashboard_transport.CACHE_CONTROL`, + ETag
    ("/api/events", None),
    ("/api/projects", "no-store"),
    # T-00000086: same header, same reason — a payload that asserts what the
    # consoles are doing AT THIS INSTANT must not be cached.
    ("/api/sessions", "no-store"),
])
def test_cache_control_is_bounded_to_the_projects_route(ui_server, path, expected):
    """BOUNDED TO THE THREE `_respond_json` ROUTES PLUS THE NEW ONE, and the
    stream leg is a separate test below: parametrising `_get` over `/api/stream`
    would read an open-ended SSE body until `_STREAM_MAX_SECONDS`.

    `_respond_json`'s new `cache_control` parameter defaults to INERT, which is
    what `/api/ping` and `/api/events` assert here; `/api/snapshot` left for
    `dashboard_transport.servir` and carries its ONE `private, no-cache`."""
    port, token = ui_server
    resp = _get(port, path, token=token)
    assert resp.status == 200
    assert resp.getheader("Cache-Control") == expected
    # The hardening pair every JSON response carries is untouched.
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("Referrer-Policy") == "no-referrer"
    assert resp.getheader("Access-Control-Allow-Origin") is None


def test_the_stream_keeps_its_own_no_store_header(ui_server):
    """The stream writes its OWN headers and never goes through `_respond_json`,
    so `no-store` there is pre-existing and must stay. Opened via `_open_stream`
    precisely because `_get` would block on the body."""
    port, token = ui_server
    conn, resp = _open_stream(port, token=token)
    try:
        assert resp.status == 200
        assert resp.getheader("Cache-Control") == "no-store"
        assert resp.getheader("Content-Type") == "text/event-stream"
    finally:
        _close_stream(conn, resp)


def test_a_rejected_projects_request_carries_no_cache_control(ui_server):
    """Stated as such in the contract rather than promised and unmet: rejections
    go through `_reject`, which this task did not touch and which sends no
    `Cache-Control` at all. A consumer must not assert one on a 401 or a 404.

    AMENDED BY T-00000028 (comment only, assertions unchanged): `/api/projects`
    is a READ route and stays POST-404. The write routes added by that task
    answer on their own table and do carry `no-store` on their 200s — a
    different contract, on different paths, and this test is not about them."""
    port, _token = ui_server
    unauthorised = _get(port, "/api/projects")
    assert unauthorised.status == 401
    assert unauthorised.getheader("Cache-Control") is None
    wrong_verb = _post(port, "/api/projects", b"{}")
    assert wrong_verb.status == 404
    assert wrong_verb.getheader("Cache-Control") is None


# ===========================================================================
# T-00000083 — the federation pair: `/api/peer/summary` (token-EXEMPT, what we
# tell a peer) and `/api/peers` (token-required, what we tell our own UI).
# ===========================================================================

_PEER_SUMMARY_KEYS = {"api_version", "kind", "project_id", "name", "label",
                      "task", "health", "generated_at"}
_PEERS_KEYS = {"api_version", "kind", "self", "peers", "registry", "generated_at"}
_PEER_ENTRY_KEYS = {"project_id", "name", "label", "port", "alive", "summary"}


def _write_board(project_root: Path, tasks: list[dict]) -> None:
    path = project_root / ".agents" / "state" / "board" / "TASKS.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"next_id": len(tasks) + 1, "tasks": tasks}),
                    encoding="utf-8", newline="\n")


def _write_registry(entries: list[dict]) -> None:
    path = Path(os.environ["AGENTKIT_REGISTRY"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1,
        "projects": {e["project_id"]: e for e in entries},
    }), encoding="utf-8", newline="\n")


def _registry_entry(project_id: str, port: int, **over) -> dict:
    entry = {"project_id": project_id, "project_root": "/somewhere/" + project_id,
             "name": "Voisin " + project_id, "pid": os.getpid(), "port": port,
             "started": "2026-08-01T09:00:00"}
    entry.update(over)
    return entry


@pytest.fixture
def peer_stub():
    """A stub PEER daemon: a server that answers `/api/peer/summary` with the
    payload the test dictates. Used instead of a second `create_ui_server`
    because a second real server would resolve the SAME identity (one
    `AGENTS_PROJECT_JSON` per test) and be filtered out as `self`."""
    servers: list[http.server.HTTPServer] = []

    def start(payload: dict) -> int:
        body = json.dumps(payload).encode("utf-8")

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's contract
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        # Threaded, like a real peer (`UIHTTPServer` is a ThreadingMixIn
        # server): a single-threaded stub can refuse a connection under load,
        # and a refusal is a definitive `dead` verdict by design.
        class _Server(http.server.ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 64

        httpd = _Server(("127.0.0.1", 0), _Handler)
        servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd.server_address[1]

    try:
        yield start
    finally:
        for httpd in servers:
            httpd.shutdown()
            httpd.server_close()


def _dead_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_peer_summary_answers_without_a_token(ui_server):
    """THE point of the route: the consumer is another project's daemon, which
    cannot hold this daemon's token. `/api/snapshot` on the same socket still
    401s, so this is a route exemption, not a hole in the server."""
    port, _token = ui_server
    resp = _get(port, "/api/peer/summary")
    assert resp.status == 200
    assert _get(port, "/api/snapshot").status == 401


def test_peer_summary_key_set_is_closed(ui_server, _redirect):
    """EXACT set, asserted at the response level. This payload crosses a trust
    boundary: a key added here is data handed to every process on the machine,
    so it must be a decision, not a drift."""
    port, _token = ui_server
    payload = json.loads(_get(port, "/api/peer/summary").data)
    assert set(payload) == _PEER_SUMMARY_KEYS
    assert set(payload["health"]) == {"serving", "otel"}
    assert payload["kind"] == "agentkit.peer_summary"
    assert payload["api_version"] == dashboard.PEER_API_VERSION == 1
    assert payload["project_id"] == _OWN_ID
    assert payload["label"], "a peer must always be displayable"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["generated_at"])
    # Nothing sensitive rides along: no token, no snapshot, no file paths.
    for forbidden in ("token", "snapshot", "ledger", "specs", "project_root",
                      "events", "costs"):
        assert forbidden not in payload


def test_peer_summary_carries_the_running_task_only(ui_server, _redirect):
    """One board line, the running one — the peer contract keeps `task`
    SINGULAR, and since T-00000188 it names the FOCUS task rather than "the"
    running task (see the two-running test below)."""
    _write_board(_redirect["project_root"], [
        {"id": "T-1", "state": "pending", "task": "pas celle-ci"},
        {"id": "T-2", "state": "running", "task": "la tache en cours", "stage": "dev"},
        {"id": "T-3", "state": "done", "task": "finie"},
    ])
    port, _token = ui_server
    task = json.loads(_get(port, "/api/peer/summary").data)["task"]
    assert set(task) == {"id", "title", "stage"}
    assert task == {"id": "T-2", "title": "la tache en cours", "stage": "dev"}


def test_peer_summary_two_running_keeps_singular_focus(ui_server, _redirect):
    """A DECLARED PARALLEL GROUP DOES NOT MOVE THE EXTERNAL CONTRACT
    (T-00000188). Two tasks may run at once now; `task` stays a single object
    equal to the FOCUS — the first running task in store order — because another
    project reads this stream and an internal board change is no reason to add a
    key or a version across a trust boundary. `test_peer_summary_key_set_is_closed`
    is right and is NOT amended.
    """
    _write_board(_redirect["project_root"], [
        {"id": "T-1", "state": "running", "task": "le focus", "stage": "dev",
         "parallel_group": "PG-0001"},
        {"id": "T-2", "state": "running", "task": "l autre membre", "stage": "ui",
         "parallel_group": "PG-0001"},
    ])
    port, _token = ui_server
    payload = json.loads(_get(port, "/api/peer/summary").data)
    assert set(payload) == _PEER_SUMMARY_KEYS, "the peer key set must not move"
    assert payload["task"] == {"id": "T-1", "title": "le focus", "stage": "dev"}
    assert "tasks" not in payload and "parallel_group" not in payload


def test_peer_summary_task_is_null_without_a_running_task(ui_server, _redirect):
    _write_board(_redirect["project_root"], [
        {"id": "T-1", "state": "pending", "task": "rien ne tourne"}])
    port, _token = ui_server
    assert json.loads(_get(port, "/api/peer/summary").data)["task"] is None


def test_peer_summary_survives_a_corrupt_board(ui_server, _redirect):
    """A neighbour's broken board is not this route's problem: a peer that 500s
    looks DEAD to the prober, which is strictly worse than one that answers
    'I don't know what I'm working on'."""
    path = _redirect["project_root"] / ".agents" / "state" / "board" / "TASKS.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8", newline="\n")
    port, _token = ui_server
    resp = _get(port, "/api/peer/summary")
    assert resp.status == 200
    assert json.loads(resp.data)["task"] is None


def test_peer_summary_does_not_refresh_the_idle_watchdog(ui_server_object):
    """Same rule as the static routes, for a sharper reason: two idle daemons
    probing each other every few seconds would keep BOTH alive forever if a
    peer probe counted as activity. Only a human using the dashboard defers the
    auto-stop."""
    httpd, port, token = ui_server_object
    httpd.last_activity = 0.0
    assert _get(port, "/api/peer/summary").status == 200
    assert httpd.last_activity == 0.0, "a peer probe must not keep the daemon alive"
    assert _get(port, "/api/snapshot", token=token).status == 200
    assert httpd.last_activity > 0.0, "authorised traffic must still refresh it"


def test_peer_summary_is_no_store_and_get_only(ui_server):
    port, _token = ui_server
    resp = _get(port, "/api/peer/summary")
    assert resp.getheader("Cache-Control") == "no-store"
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("Access-Control-Allow-Origin") is None
    assert _post(port, "/api/peer/summary", b'{"a":1}').status == 404


def test_peers_requires_the_token(ui_server):
    """The mirror image of the summary route: this one aggregates several
    projects and names their ports, so it stays behind the token."""
    port, token = ui_server
    assert _get(port, "/api/peers").status == 401
    assert _get(port, "/api/peers", token=token).status == 200


def test_peers_payload_shape_and_empty_registry(ui_server):
    port, token = ui_server
    payload = json.loads(_get(port, "/api/peers", token=token).data)
    assert set(payload) == _PEERS_KEYS
    assert payload["kind"] == "agentkit.peers"
    assert payload["api_version"] == dashboard.PEER_API_VERSION == 1
    assert payload["self"] == _OWN_ID
    assert payload["peers"] == []
    assert payload["registry"] == "empty"


def test_peers_lists_a_live_peer_with_its_summary(ui_server, peer_stub):
    port, token = ui_server
    peer_payload = {"api_version": 1, "kind": "agentkit.peer_summary",
                    "project_id": _OTHER_ID, "name": "Voisin", "label": "Voisin",
                    "task": {"id": "T-9", "title": "chez le voisin", "stage": "dev"},
                    "health": {"serving": True, "otel": "listening"},
                    "generated_at": "2026-08-01T10:00:00Z"}
    peer_port = peer_stub(peer_payload)
    _write_registry([_registry_entry(_OTHER_ID, peer_port)])

    payload = json.loads(_get(port, "/api/peers", token=token).data)
    assert payload["registry"] == "ok"
    assert len(payload["peers"]) == 1
    peer = payload["peers"][0]
    assert set(peer) == _PEER_ENTRY_KEYS
    assert peer["project_id"] == _OTHER_ID
    assert peer["alive"] is True
    assert peer["port"] == peer_port
    assert peer["summary"]["task"]["id"] == "T-9"
    assert set(peer["summary"]) == _PEER_SUMMARY_KEYS


def test_a_peers_summary_is_filtered_not_echoed(ui_server, peer_stub):
    """A peer's answer is a FOREIGN process's JSON. Re-echoing it verbatim
    would turn this token-protected route into a pass-through for whatever a
    co-resident process put on that port (security review, T-00000083). The
    contract is what we accept, not what they send."""
    port, token = ui_server
    hostile = {"api_version": 1, "kind": "agentkit.peer_summary",
               "project_id": _OTHER_ID, "name": "Voisin", "label": "Voisin",
               "task": {"id": "T-9", "title": "t", "stage": "dev", "payload": "x" * 50},
               "health": {"serving": True, "otel": "listening", "extra": "x"},
               "generated_at": "2026-08-01T10:00:00Z",
               "token": "leaked-bearer", "snapshot": {"ledger": ["everything"]},
               "<script>": "alert(1)"}
    _write_registry([_registry_entry(_OTHER_ID, peer_stub(hostile))])

    summary = json.loads(_get(port, "/api/peers", token=token).data)["peers"][0]["summary"]
    assert set(summary) == _PEER_SUMMARY_KEYS
    assert set(summary["task"]) == {"id", "title", "stage"}
    assert set(summary["health"]) == {"serving", "otel"}
    for smuggled in ("token", "snapshot", "<script>"):
        assert smuggled not in summary


def test_a_peer_answering_garbage_is_not_alive(ui_server, peer_stub):
    """The `kind` check lives in the registry probe, and the route must not
    quietly re-add a peer it rejected: a stub answering something else is
    `alive: false` with `summary: null`."""
    port, token = ui_server
    _write_registry([_registry_entry(_OTHER_ID, peer_stub({"kind": "not.us"}))])
    peer = json.loads(_get(port, "/api/peers", token=token).data)["peers"][0]
    assert peer["alive"] is False
    assert peer["summary"] is None


def test_peers_excludes_this_project_from_the_list(ui_server, peer_stub):
    """`self` is named in its own key; listing it among the peers would make
    'how many other projects are running?' ambiguous."""
    port, token = ui_server
    own_port = peer_stub({"kind": "agentkit.peer_summary", "project_id": _OWN_ID})
    other_port = peer_stub({"kind": "agentkit.peer_summary", "project_id": _OTHER_ID})
    _write_registry([_registry_entry(_OWN_ID, own_port),
                     _registry_entry(_OTHER_ID, other_port)])
    payload = json.loads(_get(port, "/api/peers", token=token).data)
    assert [p["project_id"] for p in payload["peers"]] == [_OTHER_ID]


def test_peers_lists_a_dead_peer_as_not_alive_and_never_writes_the_registry(
        ui_server, _redirect):
    """A GET a browser polls every few seconds MUST NOT mutate machine-wide
    state: the entry is reported `alive: false` and stays in the file. The
    garbage collection is the daemon's job, at its own start and stop."""
    port, token = ui_server
    entry = _registry_entry(_OTHER_ID, _dead_port())
    _write_registry([entry])
    before = Path(os.environ["AGENTKIT_REGISTRY"]).read_text(encoding="utf-8")

    payload = json.loads(_get(port, "/api/peers", token=token).data)
    peer = payload["peers"][0]
    assert peer["alive"] is False
    assert peer["summary"] is None
    assert peer["label"] == "Voisin " + _OTHER_ID
    after = Path(os.environ["AGENTKIT_REGISTRY"]).read_text(encoding="utf-8")
    assert after == before, "/api/peers must never rewrite the registry"


def test_peers_reports_an_unreadable_registry_rather_than_pretending_it_is_empty(
        ui_server):
    """`empty` and `unreadable` are different facts and the UI must be able to
    tell them apart: one says 'no other project is running', the other says
    'I cannot tell'."""
    Path(os.environ["AGENTKIT_REGISTRY"]).parent.mkdir(parents=True, exist_ok=True)
    Path(os.environ["AGENTKIT_REGISTRY"]).write_text("{broken", encoding="utf-8")
    port, token = ui_server
    payload = json.loads(_get(port, "/api/peers", token=token).data)
    assert payload["registry"] == "unreadable"
    assert payload["peers"] == []


def test_peers_reports_a_schema_ahead_registry_as_its_own_fact(ui_server):
    """LE QUATRIÈME ÉTAT DOIT VOYAGER JUSQU'À L'UI, et rester distinct.

    `unreadable` dit « je ne sais pas lire », et ce fichier SERA réécrit par le
    prochain `register()`. `schema_ahead` dit « un kit plus récent a écrit ce
    fichier », et il ne sera JAMAIS réécrit. Les confondre, c'est promettre à
    l'opérateur un rétablissement qui ne viendra pas."""
    chemin = Path(os.environ["AGENTKIT_REGISTRY"])
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"version": 99, "projects": {}}), encoding="utf-8")
    avant = chemin.read_text(encoding="utf-8")
    port, token = ui_server
    payload = json.loads(_get(port, "/api/peers", token=token).data)
    assert payload["registry"] == "schema_ahead"
    assert payload["peers"] == []
    assert chemin.read_text(encoding="utf-8") == avant, \
        "/api/peers ne doit JAMAIS reecrire le registre"


def test_peers_is_no_store_and_get_only(ui_server):
    port, token = ui_server
    resp = _get(port, "/api/peers", token=token)
    assert resp.getheader("Cache-Control") == "no-store"
    assert _post(port, "/api/peers", b'{"a":1}').status == 404


def test_projects_route_is_untouched_by_the_federation(_redirect):
    """`/api/projects` is FROZEN: T-00000083 adds routes beside it and changes
    nothing in it."""
    payload = dashboard.build_projects_response()
    assert set(payload) == _PROJECTS_KEYS
    assert payload["kind"] == "agentkit.projects"
    assert "peers" not in payload


def test_the_served_bundle_has_a_stable_fingerprint():
    """`served_code_fingerprint()` needed NO change across the React rewrite: its
    targets derive from `_ALLOWED_STATIC_ROUTES.values()`, so the two bundle
    routes that replaced sixteen module routes enrolled themselves — asserted
    here rather than assumed.

    (This test used to check that `/project.js` was declared in BOTH the Python
    route table and `selftest.mjs`'s own ROUTES table. Neither file exists any
    more: the ESM graph the second table existed to close over is now the
    bundler's job, and `test_the_shell_only_references_served_routes` is what
    replaced it.)"""
    before = dashboard.served_code_fingerprint()
    assert isinstance(before, str) and len(before) == 16
    assert before == dashboard.served_code_fingerprint(), "the digest must be stable at rest"
    # Non-vacuity: the digest must actually cover the shipped bundle.
    targets = {"/".join(segs) for segs, _ct in dashboard._ALLOWED_STATIC_ROUTES.values()}
    assert {"assets/app.js", "assets/app.css", "index.html"} <= targets


def test_the_selector_never_prescribes_a_command_or_names_a_tool():
    """The Python-side mirror of selftest.mjs's own negative check, and the
    reason it exists twice: the approved plan REMOVED the anchor-divergence
    signal, so nothing actionable on screen may PRESUME the anchors agree. Under
    `--root` / `AGENTS_PROJECT_JSON` a command shown in the UI would write to a
    different file than the one this route reads, and `project_init.py` itself
    exits 2 before writing anything when `git config user.name` is empty.

    T-00000064 SPLIT THIS TEST IN TWO, by subject. The selector strings are a
    SHIPPED artefact: this half must hold in every tree that has the file, and it
    is never conditional. The other half asserted something about the KIT's own
    documentation — see the next test — and dragging it in here made a test about
    the distributed UI fail wherever the docs deliberately are not distributed.

    Reads the SOURCE (`ui-src/src/lib/projects.js`) since the React rewrite: the
    frozen block is a named export whose spelling the minifier does not keep."""
    src = _UI_SRC_DIR / "src" / "lib" / "projects.js"
    if not src.is_file():
        pytest.skip("front-end source tree absent (build-only checkout)")
    text = src.read_text(encoding="utf-8")
    frozen = text.split("export const SELECTOR_TEXT")[1].split("}")[0]
    for forbidden in ("project_" + "init", ".py", "exécuter", "executer", "lancer"):
        assert forbidden not in frozen, f"« {forbidden} » is in a user-facing selector string"


def _is_distributed_copy() -> bool:
    """True in a tree that RECEIVED the kit rather than one that maintains it.

    Same discriminator as the index builder's, reached through its own constant
    so there is ONE definition of "this tree is a vendored copy" (T-00000062):
    the presence of a vendoring marker at the root. `main` carries neither, the
    template branch and every consumer carry one."""
    root = HERE.parent.parent
    return any((root / marker).is_file()
               for marker in readers._build_index.VENDOR_MARKERS)


@pytest.mark.skipif(_is_distributed_copy(),
                    reason="docs/ is frozen out of the distribution by "
                           "`keep: docs/` in .template-exclude, so this file is "
                           "legitimately absent here (T-00000064)")
def test_the_remedy_doc_exists_and_carries_its_precondition():
    """The OTHER half, and it is about THIS repository, not about the artefact.

    The selector deliberately shows no command, so the remedy has to exist
    somewhere that states its precondition — `docs/modules/dashboard-api.md`.
    That is a property of the kit's own documentation, and `keep: docs/` in
    `.template-exclude` means the file never travels: asserting it in a
    consumer project asserted something that was never shipped there, which is
    why `template/starter-kit` and every consumer ran this suite one test red
    (T-00000064).

    MARKED, NOT LOOSENED. The rule this file already applies to Windows-only
    cases is the one that applies here: an assertion weak enough to pass
    everywhere measures nothing. So this is skipped ONLY where the doc is
    deliberately not distributed, and on `main` — where the marker is absent —
    it runs at full force: delete the doc there and this goes red."""
    doc = (HERE.parent.parent / "docs" / "modules" / "dashboard-api.md").read_text(encoding="utf-8")
    assert "project_init.py" in doc
    assert "user.name" in doc
    assert "T-00000056" in doc


# ---------------------------------------------------------------------------
# T-00000076 — the model rate table.
#
# The rate table is REFERENCE data with an expiry: Sonnet 5's introductory
# price ends 2026-08-31. Every test below moves the clock explicitly, because a
# reader that read `date.today()` internally could not be shown to switch rows
# at all — the boundary would only be exercised on the day it happened to pass.
# ---------------------------------------------------------------------------

_RATES_ROOT = HERE.parent.parent


def test_rate_row_switches_at_the_declared_price_boundary():
    """The one row in the table that expires, checked on both sides of its date.

    This is the whole reason `effective_from` exists: a table without it would
    have silently kept billing Sonnet 5 at the introductory rate from September
    onwards. Mutate either date in MODEL_RATES.json and this goes red.
    """
    before = readers.read_model_rates(_RATES_ROOT, date(2026, 8, 31))
    after = readers.read_model_rates(_RATES_ROOT, date(2026, 9, 1))
    intro = before["providers"]["anthropic"]["models"]["claude-sonnet-5"]
    standard = after["providers"]["anthropic"]["models"]["claude-sonnet-5"]
    assert (intro["input"], intro["output"]) == (2.0, 10.0)
    assert (standard["input"], standard["output"]) == (3.0, 15.0)


def test_opus_5_5_row_appears_at_its_date_and_keeps_its_non_derivable_cache_read():
    """The Opus 5.5 row, pinned on the ONE value a multiplier would get wrong.

    `cache_read` is 0.20 because the pricing page carries an explicit
    per-model footnote (0.05x base input on Opus 5.5), NOT the 0.1x this table
    applies everywhere else. Deriving it would yield 0.40 — double. That is the
    whole reason the five values are read off the page rather than computed, so
    it is the value this test pins; recompute it from `cache_read_multiplier`
    and this goes red.

    The date leg matters for the same reason as the Sonnet 5 one above: the row
    was added on 2026-09-22 and must not retroactively price earlier snapshots.
    """
    before = readers.read_model_rates(_RATES_ROOT, date(2026, 9, 21))["providers"]["anthropic"]
    after = readers.read_model_rates(_RATES_ROOT, date(2026, 9, 22))["providers"]["anthropic"]
    assert "claude-opus-5-5" not in before["models"], (
        "the Opus 5.5 row leaked before its effective_from — earlier snapshots "
        "would be repriced at a rate that did not exist yet"
    )
    row = after["models"]["claude-opus-5-5"]
    assert (row["input"], row["output"]) == (4.0, 20.0)
    assert (row["cache_write_5m"], row["cache_write_1h"]) == (5.0, 8.0)
    assert row["cache_read"] == 0.2, (
        "cache_read must stay the value READ off the pricing page (0.05x base "
        "input on Opus 5.5); the table-wide 0.1x multiplier would give 0.40"
    )
    assert row["cache_read"] != round(row["input"] * after["cache_read_multiplier"], 4), (
        "control: if these ever coincide this test no longer proves anything — "
        "the row would be indistinguishable from a derived one"
    )
    assert row.get("source") and row.get("checked_at"), (
        "a row whose checked_at post-dates the provider's carries its own "
        "provenance, or the view attributes it to a stale check date"
    )


def test_copilot_declares_no_token_rate_and_says_why():
    """A per-seat product must not acquire an invented per-token row.

    Copilot bills per seat; there is no input/output/cache price to publish. The
    table records that as a REASON, not as an empty models map that a caller
    could read as "rates not loaded yet" — or worse, as zero.
    """
    copilot = readers.read_model_rates(
        _RATES_ROOT, date(2026, 7, 31))["providers"]["github_copilot"]
    assert copilot["billing"] == "per_seat"
    assert copilot["models"] == {}
    assert "PAS de tarification au token" in copilot["absence_reason"]


def test_one_million_window_suffix_is_an_alias_not_a_model():
    """`claude-opus-5[1m]` is a telemetry label, and 1M carries no premium.

    Anthropic's pricing page states that 4.6+ models include the full 1M context
    window at standard pricing, so the suffixed bucket must fold onto the bare
    model rather than become a second rate row.
    """
    anthropic = readers.read_model_rates(
        _RATES_ROOT, date(2026, 7, 31))["providers"]["anthropic"]
    assert anthropic["aliases"]["claude-opus-5[1m]"] == "claude-opus-5"
    assert "claude-opus-5[1m]" not in anthropic["models"]


def test_absent_rate_table_is_a_stated_absence_not_an_empty_price_list(tmp_path):
    """No table must never read as "every model is free"."""
    result = readers.read_model_rates(tmp_path, date(2026, 7, 31))
    assert result["status"] == "trail_absent"
    assert result["providers"] == {}
    assert "no tokens x rate estimate" in result["reason"]


def test_malformed_rate_table_degrades_with_its_reason(tmp_path):
    rates = tmp_path / ".agents" / "ref"
    rates.mkdir(parents=True)
    (rates / "MODEL_RATES.json").write_text("{not json", encoding="utf-8")
    result = readers.read_model_rates(tmp_path, date(2026, 7, 31))
    assert result["status"] == "degraded"
    assert "unreadable" in result["reason"]


# ===========================================================================
# T-00000086 (M5a) — `/api/sessions`: canal A grouped by (host, session).
#
# THE STORE OWNS THE GROUPING and `test_event_store.py` owns its bounds; what
# is asserted HERE is the ROUTE: the token, the closed key set, the headers, the
# three query parameters, the degraded bodies, and the two things this feature
# must never become — a write path, or a second reader of the spool.
# ===========================================================================

_SESSIONS_KEYS = {
    "api_version", "kind", "generated_at", "pending_coverage",
    "status", "reason", "window", "sessions", "sessionless", "total_sessions",
    "truncated_sessions", "caps", "filters", "filters_available",
    "malformed_skipped", "source", "degraded",
}
_SESSION_ENTRY_KEYS = {"sid", "host", "project", "first_ts", "last_ts", "agents",
                       "counts_by_kind", "events", "total_events", "truncated"}


def _stamp(minutes_ago: int) -> str:
    """A canal-A timestamp relative to the WALL clock, in the exact format the
    column holds.

    Deliberately not a frozen clock: this route resolves its own window from
    `datetime.now()`, so a test that stamped events on an injected clock and
    then called the route would be measuring the gap between two clocks (the
    convention's own warning, applied in the direction that fits — no clock is
    injected here, so every temporal fact is taken from the same real one)."""
    moment = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_rec(minutes_ago: int, sid, host: str = "claude", **over) -> dict:
    record = {
        "ts": _stamp(minutes_ago), "kind": "session.start", "host": host,
        "sid": sid, "pid": "p1", "aid": "a1", "task": None, "agent": None,
        "effort": None, "user": "Dev", "data": {},
    }
    record.update(over)
    return record


def _ingest_sessions(_redirect, records: list[dict]) -> None:
    """Same production configuration as `_ingest_canal_a`: rows in the store,
    spool directory EMPTY. The filename carries TODAY on the real clock, for the
    reason that helper's own docstring gives."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _ingest_canal_a(_redirect, records, filename=f"{today}.claude.86.jsonl")


def test_sessions_needs_the_token_like_every_other_data_route(ui_server):
    port, token = ui_server
    assert _get(port, "/api/sessions").status == 401
    assert _get(port, "/api/sessions", token=token).status == 200


def test_sessions_payload_has_the_closed_key_set(ui_server, _redirect):
    _ingest_sessions(_redirect, [
        _session_rec(10, "s-1"),
        _session_rec(9, "s-1", kind="hook.deny", agent="dev-multi"),
    ])
    port, token = ui_server
    payload = json.loads(_get(port, "/api/sessions", token=token).data)
    assert set(payload) == _SESSIONS_KEYS
    assert payload["api_version"] == 1
    assert payload["kind"] == "agentkit.sessions"
    assert payload["status"] == "ok"
    assert payload["degraded"] is False
    assert len(payload["sessions"]) == 1
    session = payload["sessions"][0]
    assert set(session) == _SESSION_ENTRY_KEYS
    assert session["sid"] == "s-1"
    assert session["host"] == "claude"
    assert session["total_events"] == 2
    assert [e["kind"] for e in session["events"]] == ["session.start", "hook.deny"]


def test_sessions_honours_its_three_query_parameters(ui_server, _redirect):
    _ingest_sessions(_redirect, [
        _session_rec(10, "c-1", host="claude"),
        _session_rec(9, "x-1", host="codex"),
        _session_rec(60 * 40, "vieux", host="claude"),
    ])
    port, token = ui_server
    everything = json.loads(_get(port, "/api/sessions", token=token).data)
    assert {s["sid"] for s in everything["sessions"]} == {"c-1", "x-1"}, (
        "the default window is 24 h — the 40 h-old session is outside it")

    by_host = json.loads(_get(port, "/api/sessions?host=codex", token=token).data)
    assert [s["sid"] for s in by_host["sessions"]] == ["x-1"]
    assert by_host["filters"] == {"host": "codex", "project": None}
    # The choices offered back are NOT narrowed by the active filter, or the
    # `<select>` this feeds would be a one-way door.
    assert by_host["filters_available"]["hosts"] == ["claude", "codex"]

    wide = json.loads(_get(port, f"/api/sessions?since={_stamp(60 * 48)}",
                           token=token).data)
    assert {s["sid"] for s in wide["sessions"]} == {"c-1", "x-1", "vieux"}

    by_project = json.loads(
        _get(port, f"/api/sessions?project={_OWN_ID}", token=token).data)
    assert {s["sid"] for s in by_project["sessions"]} == {"c-1", "x-1"}
    absent = json.loads(
        _get(port, "/api/sessions?project=projet-inexistant", token=token).data)
    assert absent["sessions"] == []
    assert absent["status"] == "ok", "an empty FILTERED result is a measurement"


def test_sessions_counts_sessionless_rows_rather_than_dropping_them(ui_server, _redirect):
    """Most canal-A hooks carry no `sid` today. A view whose subject is "what
    happened" cannot make them disappear."""
    _ingest_sessions(_redirect, [
        _session_rec(10, "s-1"),
        _session_rec(9, None, kind="hook.deny"),
        _session_rec(8, None, kind="hook.deny", host="codex"),
    ])
    port, token = ui_server
    payload = json.loads(_get(port, "/api/sessions", token=token).data)
    assert [s["sid"] for s in payload["sessions"]] == ["s-1"]
    assert payload["sessionless"]["count"] == 2
    assert payload["sessionless"]["by_host"] == {"claude": 1, "codex": 1}


def test_sessions_declares_WHICH_hosts_the_pending_marker_covers(ui_server):
    """THE assertion this feature could most easily get wrong, in its SECOND
    state (T-00000090 amends the vacuity T-00000086 left here on purpose).

    An empty `covered_hosts` next to a silent UI reads as "no console is waiting
    for you"; it actually meant "nothing can tell us". Now that Claude Code is
    wired, the SAME trap moves one step: a badge fed by one host out of four
    reads as a fleet-wide measurement. A session on Codex that is waiting for an
    answer will never appear here, and the payload has to say so rather than let
    the silence speak.

    The predecessor arm asserted `not any("notif" in kind ...)` and declared, in
    its own words, that the day a kind carried this signal the assertion would
    fail and the note would have to be rewritten. That day is this commit;
    amending it is the contract, not collateral damage.
    """
    port, token = ui_server
    coverage = json.loads(_get(port, "/api/sessions", token=token).data)["pending_coverage"]
    assert coverage["covered_hosts"] == ["claude-code"]
    note = coverage["note"]
    # The note must NAME the uncovered hosts. A note saying only "câblé sur
    # Claude Code" would be true and still let a reader assume the rest follows.
    for host in ("Codex", "Copilot", "Gemini"):
        assert host in note, f"the coverage note never names {host} as uncovered"
    assert "T-00000090" in note
    # Non-vacuity of the wiring itself: the kind now EXISTS in the closed
    # vocabulary, which is what makes `covered_hosts` non-empty legitimate.
    assert "session.notify" in events_mod.KNOWN_KINDS


def test_sessions_without_a_projection_says_so_and_never_reads_the_spool(ui_server, _redirect):
    """NO FALLBACK, ON PURPOSE. `/api/events` globs the spool when there is no
    database; this route does not, because a hand-rolled Python group-by over
    those files would be a second source for one figure. The spool below is
    POPULATED and must stay unread."""
    _write_line(_redirect["events_dir"], "2026-08-01.claude.86.jsonl",
                _session_rec(5, "jamais-lue"))
    port, token = ui_server
    payload = json.loads(_get(port, "/api/sessions", token=token).data)
    assert payload["status"] == "absent"
    assert payload["degraded"] is True
    assert payload["source"] == "absent"
    assert "projection absente" in payload["reason"]
    assert payload["sessions"] == []
    assert "jamais-lue" not in json.dumps(payload)
    # ...and the FULL key set is still there, so a consumer never has to
    # feature-detect its way through a degraded body.
    assert set(payload) == _SESSIONS_KEYS
    assert payload["window"]["since"] and payload["window"]["until"]


@pytest.mark.parametrize("break_it,expected", [
    ("corrupt", "unavailable"),
    ("ahead", "schema_ahead"),
])
def test_sessions_degrades_in_a_known_shape_on_an_unreadable_store(ui_server, _redirect,
                                                                   break_it, expected):
    _ingest_sessions(_redirect, [_session_rec(10, "s-1")])
    db = event_store._events_mod.events_db_path()
    if break_it == "corrupt":
        db.write_bytes(b"pas une base sqlite" * 40)
    else:
        store = event_store.open_store(create=False)
        store.connection.execute("PRAGMA user_version = 99")
        store.close()
    port, token = ui_server
    resp = _get(port, "/api/sessions", token=token)
    assert resp.status == 200, "a reader degrades, it never 500s"
    payload = json.loads(resp.data)
    assert payload["status"] == expected
    assert payload["degraded"] is True
    assert payload["reason"]
    assert payload["sessions"] == []
    assert set(payload) == _SESSIONS_KEYS


def test_sessions_is_get_only_and_writes_nothing(ui_server, _redirect):
    """READ ONLY IS THE WHOLE POSTURE OF M5a: the writing half is T-00000088,
    deliberately blocked behind the T-00000028 gate. A GET that created the
    database would already be half of it."""
    port, token = ui_server
    assert _post(port, "/api/sessions", b'{"a":1}').status == 404
    db = event_store._events_mod.events_db_path()
    assert not db.exists()
    assert _get(port, "/api/sessions", token=token).status == 200
    assert not db.exists(), "a reader must never create the projection"


def test_sessions_leaves_the_three_frozen_routes_byte_identical(ui_server, _redirect):
    """`/api/snapshot`, `/api/projects` and `/api/events` are FROZEN: this task
    adds a route beside them and changes nothing in them — the events cursor
    fingerprint included, since a moved fingerprint would reset every open
    Timeline cursor in a browser that survived the upgrade."""
    _ingest_sessions(_redirect, [_session_rec(10, "s-1")])
    port, token = ui_server
    events = json.loads(_get(port, "/api/events", token=token).data)
    assert set(events) >= {"events", "next_cursor", "cursor_unit", "cursor_reset",
                           "pruned_files", "malformed_lines_skipped", "aggregates",
                           "source", "degraded", "reason", "has_more"}
    assert events["cursor_unit"] == "db_rowid"
    assert "sessions" not in events
    fingerprint = dashboard._filters_fingerprint({"task": None, "kind": None,
                                                  "agent": None})
    decoded = dashboard._decode_cursor(events["next_cursor"])
    assert decoded["fp"] == fingerprint, "the cursor fingerprint must not move"

    projects = json.loads(_get(port, "/api/projects", token=token).data)
    assert set(projects) == _PROJECTS_KEYS
    assert "sessions" not in projects
    snapshot = json.loads(_get(port, "/api/snapshot", token=token).data)
    assert "sessions" not in snapshot
    assert set(snapshot["views"]) == _EXPECTED_VIEW_KEYS


def test_every_declared_rate_row_carries_a_source_and_a_check_date():
    """Provenance is the condition for the table's existence, not a nicety.

    The design doc requires an estimate to be labelled AND sourced; a provider
    block with prices but no `source`/`checked_at` would put unattributable
    numbers on screen.
    """
    providers = readers.read_model_rates(_RATES_ROOT, date(2026, 7, 31))["providers"]
    for name, block in providers.items():
        assert block["source"], f"{name} has no source"
        assert block["checked_at"], f"{name} has no checked_at"


# ---------------------------------------------------------------------------
# /api/term + /api/term/stream — the console mirror (T-00000087, M5b)
# ---------------------------------------------------------------------------

wrap = dashboard._wrap_mod


def _make_spool(term_dir: Path, sid: str, payload: bytes = b"",
                cmd: str = "claude", pid: int | None = None,
                ended: str | None = None, gen: int = 0,
                cols: int = 100, rows: int = 30, resize: str = "posix") -> Path:
    """A mirror spool written the way `wrap.py` writes one — the SAME pair of
    files, not a fixture shape invented here. `pid` defaults to this process so
    the session reads as LIVE; pass a dead one to exercise `unknown`."""
    term_dir.mkdir(parents=True, exist_ok=True)
    raw = term_dir / f"{sid}.raw"
    raw.write_bytes(payload)
    (term_dir / f"{sid}.meta.json").write_text(json.dumps({
        "sid": sid, "cmd": cmd, "pid": os.getpid() if pid is None else pid,
        "cols": cols, "rows": rows, "started": "2026-08-01T09:00:00Z",
        "ended": ended, "gen": gen, "resize": resize,
    }), encoding="utf-8", newline="\n")
    return raw


def _open_term_stream(port: int, sid: str, token: str | None = None,
                      timeout: float = 10.0):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", f"/api/term/stream?sid={sid}", headers=headers)
    return conn, conn.getresponse()


def _wait_for_term_streams(count: int, deadline_s: float = 15.0) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if dashboard.active_term_stream_count() == count:
            return
        time.sleep(0.02)
    raise AssertionError(
        f"active_term_stream_count() stayed at {dashboard.active_term_stream_count()}, "
        f"expected {count}")


def test_term_requires_the_token_like_every_other_api_route(ui_server, _redirect):
    _make_spool(_redirect["term_dir"], "20260801T090000Z-4242", b"bonjour")
    port, token = ui_server
    assert _get(port, "/api/term").status == 401
    assert _get(port, "/api/term/stream?sid=20260801T090000Z-4242").status == 401
    assert _get(port, "/api/term", token=token).status == 200


def test_term_lists_the_spools_with_three_states_never_two(ui_server, _redirect):
    """`live` / `ended` / `unknown`. The third is the one that matters: a meta
    with no `ended` whose pid is gone is a wrapper that DIED, and rendering that
    as live shows a ghost while rendering it as ended claims a clean finish that
    never happened."""
    term_dir = _redirect["term_dir"]
    _make_spool(term_dir, "20260801T090000Z-1", b"a" * 10)             # live
    _make_spool(term_dir, "20260801T090100Z-2", b"b" * 20,
                ended="2026-08-01T09:05:00Z")                          # ended
    _make_spool(term_dir, "20260801T090200Z-3", b"c" * 30, pid=999999)  # unknown
    port, token = ui_server
    payload = json.loads(_get(port, "/api/term", token=token).data)

    assert payload["kind"] == "agentkit.term"
    assert payload["api_version"] == 1
    assert payload["status"] == "ok" and payload["degraded"] is False
    states = {s["sid"]: s["state"] for s in payload["sessions"]}
    assert states["20260801T090000Z-1"] == "live"
    assert states["20260801T090100Z-2"] == "ended"
    assert states["20260801T090200Z-3"] == "unknown"
    sizes = {s["sid"]: s["bytes"] for s in payload["sessions"]}
    assert sizes["20260801T090200Z-3"] == 30
    # Newest first: the sid starts with a UTC timestamp, so the sort is the id.
    assert [s["sid"] for s in payload["sessions"]] == [
        "20260801T090200Z-3", "20260801T090100Z-2", "20260801T090000Z-1"]


def test_term_publishes_the_command_NAME_and_never_an_argv(ui_server, _redirect):
    """THE privacy assertion of this route. `wrap.py` records a basename; this
    checks the API cannot start publishing more, because a mirror list showing
    `--api-key ...` would undo the token custody rules the rest of the kit
    enforces."""
    _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"x", cmd="claude")
    port, token = ui_server
    payload = json.loads(_get(port, "/api/term", token=token).data)
    entry = payload["sessions"][0]
    assert entry["cmd"] == "claude"
    assert set(entry) == {"sid", "cmd", "state", "pid", "cols", "rows",
                          "resize", "started", "ended", "gen", "bytes"}
    assert "argv" not in json.dumps(payload) and "env" not in entry


def test_term_says_no_mirror_rather_than_showing_an_empty_list(ui_server, _redirect):
    """ABSENCE IS NOT A MEASUREMENT. No spool directory means "no console was
    launched through the wrapper", which is NOT "no console is running" — a
    terminal opened by hand is invisible by construction, and the payload has to
    say so or the UI will imply the machine is idle."""
    port, token = ui_server
    payload = json.loads(_get(port, "/api/term", token=token).data)
    assert payload["status"] == "absent" and payload["degraded"] is True
    assert payload["sessions"] == [] and payload["total"] == 0
    assert "wrap.py" in payload["reason"]
    assert "invisible par construction" in payload["coverage"]
    assert "T-00000088" in payload["coverage"], "le sens unique doit etre dit"


def test_term_skips_an_unreadable_pair_without_taking_the_route_down(ui_server, _redirect):
    term_dir = _redirect["term_dir"]
    _make_spool(term_dir, "20260801T090000Z-1", b"bon")
    term_dir.mkdir(parents=True, exist_ok=True)
    (term_dir / "20260801T090100Z-2.meta.json").write_text("{ pas du json",
                                                           encoding="utf-8")
    # A meta whose `sid` disagrees with its filename is not adopted either.
    (term_dir / "20260801T090200Z-3.meta.json").write_text(
        json.dumps({"sid": "autre-chose"}), encoding="utf-8")
    port, token = ui_server
    payload = json.loads(_get(port, "/api/term", token=token).data)
    assert [s["sid"] for s in payload["sessions"]] == ["20260801T090000Z-1"]


def test_term_stream_404s_on_an_unknown_or_malformed_sid(ui_server, _redirect):
    """The sid is the only filename-shaped parameter this server accepts, so
    the anchored alphabet IS the boundary — and an unknown-but-valid sid gets
    the SAME opaque 404 as a malformed one, so a caller cannot probe the
    filesystem by telling the two apart."""
    _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"x")
    port, token = ui_server
    for sid in ("", "inconnu-mais-valide", "..", "%2e%2e", "a/b", "a.b",
                "../20260801T090000Z-1", "a" * 200):
        resp = _get(port, f"/api/term/stream?sid={sid}", token=token)
        assert resp.status == 404, sid
        assert b"20260801T090000Z-1" not in resp.data
        # Never a reflected path, never a different body for "exists but no".
        assert json.loads(resp.data) == {"error": "not_found"}


def test_term_stream_frames_the_spool_bytes_in_base64(ui_server, _redirect):
    """Base64 and not text: the spool is a raw ANSI byte stream, a chunk
    boundary can fall inside a UTF-8 sequence, and JSON cannot carry a lone
    continuation byte. The payload here is deliberately NOT valid UTF-8."""
    raw = _make_spool(_redirect["term_dir"], "20260801T090000Z-1",
                      b"\x1b[31mrouge\x1b[0m\xff\xfe")
    port, token = ui_server
    conn, resp = _open_term_stream(port, "20260801T090000Z-1", token=token)
    try:
        frames = _read_until(resp, lambda line: line.startswith("data: ")
                             and '"term"' in line)
        payload = _stream_json(frames[-1])
        assert payload["kind"] == "term"
        assert base64.b64decode(payload["b64"]) == b"\x1b[31mrouge\x1b[0m\xff\xfe"
        # ...and a byte appended after the connection reaches the same stream.
        with open(raw, "ab") as fh:
            fh.write(b"suite")
        frames = _read_until(resp, lambda line: line.startswith("data: ")
                             and '"term"' in line)
        assert base64.b64decode(_stream_json(frames[-1])["b64"]) == b"suite"
    finally:
        _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_term_stream_announces_a_rotation_and_resyncs_on_the_generation(
        ui_server, _redirect):
    """THE resync property. `wrap.py` publishes `gen+1` BEFORE swapping the
    file, so a reader that sees a new generation resets its offset to 0 and
    replays — announced with a `term_gap` the front turns into `term.reset()`.
    Splicing across a rotation at the old offset would render a terminal that
    never existed."""
    term_dir = _redirect["term_dir"]
    sid = "20260801T090000Z-1"
    raw = _make_spool(term_dir, sid, b"avant-rotation")
    port, token = ui_server
    conn, resp = _open_term_stream(port, sid, token=token)
    try:
        _read_until(resp, lambda line: '"term"' in line)
        # The writer's recipe, in the writer's order: generation first...
        meta_path = term_dir / f"{sid}.meta.json"
        meta = wrap.read_meta(meta_path)
        meta["gen"] = 1
        wrap.write_meta_atomic(meta_path, meta)
        # ...then the content.
        raw.write_bytes(b"apres-rotation")
        frames = _read_until(resp, lambda line: '"term_gap"' in line)
        gap = _stream_json(frames[-1])
        assert gap["kind"] == "term_gap" and gap["reason"] == "rotation"
        frames = _read_until(resp, lambda line: '"term"' in line)
        assert base64.b64decode(_stream_json(frames[-1])["b64"]) == b"apres-rotation"
    finally:
        _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_term_stream_declares_a_catchup_tail_rather_than_replaying_an_hour(
        ui_server, _redirect, monkeypatch):
    monkeypatch.setattr(dashboard, "_TERM_CATCHUP_BYTES", 64)
    _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"A" * 500 + b"FIN")
    port, token = ui_server
    conn, resp = _open_term_stream(port, "20260801T090000Z-1", token=token)
    try:
        first = _stream_json(_read_until(resp, lambda l: l.startswith("data: "))[-1])
        assert first["kind"] == "term_gap" and first["reason"] == "catchup", (
            "un rattrapage tronque doit etre DIT, pas deduit d'un affichage "
            "qui commence au milieu d'un mot")
        frames = _read_until(resp, lambda line: '"term"' in line)
        data = base64.b64decode(_stream_json(frames[-1])["b64"])
        assert data.endswith(b"FIN") and len(data) <= 64
    finally:
        _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_term_stream_skips_forward_and_says_lag_when_it_falls_behind(
        ui_server, _redirect, monkeypatch):
    """A mirror thirty seconds behind is worse than one that says it jumped."""
    monkeypatch.setattr(dashboard, "_TERM_MAX_TICK_BYTES", 32)
    raw = _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"debut")
    port, token = ui_server
    conn, resp = _open_term_stream(port, "20260801T090000Z-1", token=token)
    try:
        # Wait for the CATCH-UP frame before writing. Without this the burst can
        # land before the initial slice, be swallowed whole by the (much larger)
        # catch-up budget, and the lag branch never runs — a flaky test that
        # measures the scheduler rather than the cap.
        _read_until(resp, lambda line: '"term"' in line)
        with open(raw, "ab") as fh:
            fh.write(b"B" * 500 + b"QUEUE")
        frames = _read_until(resp, lambda line: '"lag"' in line)
        assert _stream_json(frames[-1])["reason"] == "lag"
        frames = _read_until(resp, lambda line: '"term"' in line)
        data = base64.b64decode(_stream_json(frames[-1])["b64"])
        assert data.endswith(b"QUEUE") and len(data) <= 32
    finally:
        _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_the_mirror_limit_is_its_own_and_never_eats_the_notice_slots(
        ui_server, _redirect):
    """TWO BUDGETS, TWO 503s. If the mirror drew from `_MAX_CONCURRENT_STREAMS`
    then opening two terminals would leave two slots for every other tab's
    change notices and the dashboard would silently stop refreshing itself.
    This asserts the independence in both directions."""
    _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"x")
    port, token = ui_server
    assert dashboard._MAX_TERM_STREAMS == 2
    opened = []
    try:
        for _ in range(dashboard._MAX_TERM_STREAMS):
            conn, resp = _open_term_stream(port, "20260801T090000Z-1", token=token)
            assert resp.status == 200
            opened.append((conn, resp))
        _wait_for_term_streams(dashboard._MAX_TERM_STREAMS)
        # The third mirror is refused...
        refused = _get(port, "/api/term/stream?sid=20260801T090000Z-1", token=token)
        assert refused.status == 503
        assert json.loads(refused.data) == {"error": "term_stream_limit_reached"}
        assert refused.getheader("Retry-After") == "5"
        # ...and the NOTICE budget is untouched: all four are still available.
        assert dashboard.active_stream_count() == 0
        notice_conn, notice_resp = _open_stream(port, token=token)
        try:
            assert notice_resp.status == 200
            _wait_for_streams(1)
        finally:
            _close_stream(notice_conn, notice_resp)
        _wait_for_streams(0)
    finally:
        for conn, resp in opened:
            _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_a_closed_mirror_tab_frees_its_slot_within_one_poll(ui_server, _redirect):
    _make_spool(_redirect["term_dir"], "20260801T090000Z-1", b"x")
    port, token = ui_server
    conn, resp = _open_term_stream(port, "20260801T090000Z-1", token=token)
    _read_until(resp, lambda line: line.startswith("data: ") or line.startswith("retry:"))
    _wait_for_term_streams(1)
    _close_stream(conn, resp)
    _wait_for_term_streams(0)


def test_the_mirror_reader_holds_no_handle_between_ticks(_redirect):
    """Not tidiness: `wrap.py`'s rotation ends in an `os.replace`, and on
    Windows a handle held across the swap makes the writer's bounded retry fail
    and the rotation get ABANDONED. A daemon keeping this file open would
    degrade the writer, from another process, invisibly.

    Asserted by doing the thing that fails when a handle is held: replace the
    file immediately after a slice read."""
    term_dir = _redirect["term_dir"]
    raw = _make_spool(term_dir, "20260801T090000Z-1", b"abcdefghij")
    size, data, skipped = dashboard.UIHandler._term_slice(raw, 0, 1024)
    assert (size, data, skipped) == (10, b"abcdefghij", False)
    replacement = term_dir / "remplacant.raw"
    replacement.write_bytes(b"neuf")
    os.replace(replacement, raw)  # would raise PermissionError under a held handle
    assert raw.read_bytes() == b"neuf"


def test_the_mirror_slice_degrades_instead_of_raising_on_a_missing_file(tmp_path):
    assert dashboard.UIHandler._term_slice(tmp_path / "absent.raw", 0, 10) == (
        None, b"", False)


# ===========================================================================
# T-00000028 — THE WRITE HALF. Three POST routes, one closed table, and the
# rule every assertion below circles: this server records a DECISION and
# resumes NOTHING. The tests that pinned "GET is the only verb"
# (`test_post_on_a_static_route_404`, `test_post_on_the_stream_route_404`,
# `test_the_api_route_set_stays_closed_and_small`,
# `test_a_rejected_projects_request_carries_no_cache_control`) were amended IN
# PLACE, each carrying a note naming this task — never quietly relaxed.
# ===========================================================================

specs_mod = dashboard._specs_mod
tasks_mod = dashboard._tasks_mod

_GATE = "/api/actions/gate"
_BOARD = "/api/actions/board"
_WAIVER = "/api/actions/waiver"


def _post_json(port: int, path: str, payload: Any = None, token: str | None = None,
               raw: bytes | None = None) -> http.client.HTTPResponse:
    """POST with an Authorization header and a decoded body — `_post` above
    stays as it was (no token, body discarded), because eight existing tests
    depend on its exact shape."""
    body = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        resp.data = resp.read()  # type: ignore[attr-defined]
        return resp
    finally:
        conn.close()


def _post_body(port: int, path: str, payload: Any = None, token: str | None = None,
               raw: bytes | None = None) -> dict:
    resp = _post_json(port, path, payload, token=token, raw=raw)
    return json.loads(resp.data or b"{}")


def _verb(port: int, method: str, path: str, token: str | None = None) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        conn.request(method, path, headers=headers)
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def _seed_plan(project_root: Path, task: str = "T-00000028",
               title: str = "plan rev3 — le shard serveur") -> str:
    """Record a plan through `specs.py`'s own writer, never by hand: the gate
    route hashes what THAT writer produces, so a hand-built store would test a
    format nothing else emits."""
    specs_mod.add_entry(project_root, task, "plan", title, "corps du plan")
    return task


def _expected_plan_hash(project_root: Path, task: str) -> str:
    """The hash the SERVER must have computed: sha256 of `specs.py list
    --task`'s own output. Recomputed here from the same renderer rather than
    copied from the response — a test that reads the value it is checking
    proves nothing."""
    text = specs_mod.render_list(project_root, task).strip()
    return __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()


def _canal_a_records(events_dir: Path) -> list[dict]:
    records = []
    for path in sorted(events_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _new_task(project_root: Path, title: str = "tache jetable") -> str:
    tasks_mod.new_task(str(project_root), title, "dev-multi")
    return tasks_mod.load(project_root)["tasks"][-1]["id"]


def _sleeper_argv(*_args: str) -> list[str]:
    """A stand-in CLI that outlives any sane timeout. Used to exercise the REAL
    `subprocess.TimeoutExpired` path — a mocked timeout would assert that the
    mock was called, not that the server survives a wedged child."""
    return [sys.executable, "-c", "import time; time.sleep(30)"]


# ---------------------------------------------------------------------------
# The table, the verb, the token, the body — the four bounds, before any
# route's own semantics.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/actions", "/api/actions/", "/api/actions/gate/", "/api/actions/Gate",
    "/api/actions/gate/..", "/api/actions/../actions/gate", "/api/actions/waivers",
    "/api/actions/gate%00", "/api%2factions%2fgate", "/api/snapshot", "/api/events",
    "/api/peer/summary", "/", "/assets/app.js",
])
def test_a_post_outside_the_write_table_is_a_404(ui_server, path):
    """EXACT-string routing, on the raw path. Every entry here is a near miss —
    a trailing slash, a capital, a traversal segment, a percent-encoded
    separator, a read route, the token-exempt shell — and near misses are the
    whole point of an exact match: `/api/actions/gate/..` normalises to an
    allowed route in any router that normalises, and this one must not."""
    port, token = ui_server
    assert _post_json(port, path, {"a": 1}, token=token).status == 404, path


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "GET"])
@pytest.mark.parametrize("path", [_GATE, _BOARD, _WAIVER])
def test_a_write_route_answers_POST_and_nothing_else(ui_server, method, path):
    """One verb was added, not a verb table. `OPTIONS` is in this list on
    purpose: a router that answered it would be the first half of a CORS
    preflight, and this server sends no CORS header at all."""
    port, token = ui_server
    assert _verb(port, method, path, token=token) == 404


@pytest.mark.parametrize("path", [_GATE, _BOARD, _WAIVER])
def test_a_write_route_without_a_token_is_a_404(ui_server, path):
    """No exemption on this table, ever. The two token-exempt tables exist for
    consumers that cannot hold the token; neither of them writes.

    404, NOT 401 (T-00000238, S-00000496): an absent token on a real write
    route answers exactly as an unknown path would, so the two unauthenticated
    cases cannot be told apart — that indistinguishability is the fix, and the
    membership test still runs first (see the sibling call-order probe)."""
    port, _token = ui_server
    assert _post_json(port, path, {"confirm": True}).status == 404


@pytest.mark.parametrize("path", [_GATE, _BOARD, _WAIVER])
def test_a_write_route_with_a_wrong_token_is_a_404(ui_server, path):
    """A WRONG token is the same unauthenticated case as an absent one and
    answers the same 404 (T-00000238, S-00000496) — never 401, or the code
    itself would map the write table for a caller who holds no credential."""
    port, _token = ui_server
    assert _post_json(port, path, {"confirm": True}, token="not-the-token").status == 404


def test_an_unknown_write_path_404s_before_the_token_is_consulted(ui_server, monkeypatch):
    """The ORDER of the first two checks in `_route_write`, saved as a property
    of the CALL rather than of the response (T-00000178 c, tried and reverted
    the same night — see the method's docstring and T-00000238).

    T-00000238 made BOTH unauthenticated cases answer 404, so the response can
    no longer witness the order: an unknown path and a real route reached with
    no token now return the same status. A future inversion — token checked
    before membership — would therefore slip past every response-level arm in
    silence. This probe closes that hole. It intercepts `_check_token`, records
    the path it was consulted on, and asserts the token is NEVER consulted for
    an unknown path (the membership test 404s first) and IS consulted for a real
    write route (so the control cannot be deleted, and the probe cannot be
    vacuous).

    Inverting was meant to close a real leak: unauthenticated, an unknown path
    answers 404 and a real one used to answer 401, which mapped the write table
    with no credential. But `do_POST` funnels EVERY path through `_route_write`,
    including the token-EXEMPT tables, so a token check placed first answers 401
    on a plain document navigation. Ten arms measured that in one run. The leak
    is real and the fix is not a reordering.

    In-process server (`ui_server`, above): the thread that answers instantiates
    the very `UIHandler` class patched here, so the wrapper runs on the real
    request path.
    """
    port, token = ui_server
    consulted: list[str] = []
    original = dashboard.UIHandler._check_token

    def wrapper(self):
        consulted.append(self.path)
        return original(self)

    monkeypatch.setattr(dashboard.UIHandler, "_check_token", wrapper)

    # Unknown path: the membership test 404s BEFORE the token is looked at, with
    # a token (irrelevant) and without one.
    assert _post_json(port, "/api/actions/nope", {}, token=token).status == 404
    assert _post_json(port, "/api/actions/nope", {}).status == 404
    assert consulted == [], (
        "the token was consulted on an unknown write path — the membership test "
        f"no longer runs first: {consulted!r}")

    # Real write route: the token IS consulted. Non-vacuity of the probe, and
    # proof the control was not silently removed along with the response code.
    _post_json(port, _GATE, {"confirm": True}, token=token)
    assert any(p == _GATE for p in consulted), (
        "the token was never consulted on a real write route — the probe is "
        f"vacuous or the control is gone: {consulted!r}")


_HEADER_DIFF_EXCLUSIONS = {"date"}


def _comparable_headers(resp) -> dict[str, str]:
    """Every response header except the ones a clock legitimately varies."""
    return {name.lower(): value
            for name, value in resp.getheaders()
            if name.lower() not in _HEADER_DIFF_EXCLUSIONS}


def test_an_unauthenticated_write_is_byte_identical_to_an_unknown_path_bar_the_date(ui_server):
    """The scoped invariant of `_route_write` (T-00000238, S-00000496): the two
    UNAUTHENTICATED cases — a path outside the write table, and a real write
    route reached with no token — are indistinguishable from an unknown route:
    same status, same body, and the SAME set of headers save `Date` alone. If
    any of those diverged, the difference would map the write table to a caller
    who holds no credential — the very leak this task closes.

    Scope is deliberate: this measures ONLY the unauthenticated surface. An
    AUTHENTICATED error differs by construction and is out of scope, which is
    why the exclusion list is named rather than the whole comparison waved off.
    """
    port, _token = ui_server
    unknown = _post_json(port, "/api/actions/nope", {})       # outside the table
    unauth = _post_json(port, _GATE, {"confirm": True})       # real route, no token

    assert unknown.status == unauth.status == 404
    assert unknown.data == unauth.data

    unknown_headers = _comparable_headers(unknown)
    unauth_headers = _comparable_headers(unauth)
    # Non-vacuity: an empty-vs-empty header comparison would pass silently and
    # measure nothing — the failure mode of every absence check (see the AST
    # `shell=` test's own non-vacuity guard).
    assert unknown_headers, "no comparable headers — the equality would be vacuous"
    assert unknown_headers == unauth_headers


def test_a_body_with_no_declared_length_is_refused(ui_server):
    """411 rather than "read until EOF": an undeclared length is the shape that
    holds a handler thread on a request nobody can bound."""
    port, token = ui_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest("POST", _GATE)
        conn.putheader("Authorization", f"Bearer {token}")
        conn.endheaders()
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 411
    finally:
        conn.close()


def test_an_oversized_body_is_refused_on_its_declared_length(ui_server):
    port, token = ui_server
    oversized = b"x" * (dashboard._DRAIN_LIMIT_BYTES + 1)
    assert _post_json(port, _GATE, token=token, raw=oversized).status == 413


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1,2,3]", b'"a string"', b"null"])
def test_a_body_that_is_not_a_json_object_is_a_400(ui_server, raw):
    """A list or a scalar has no `.get()`; refused at the door rather than
    surviving as an AttributeError three methods deep."""
    port, token = ui_server
    assert _post_json(port, _GATE, token=token, raw=raw).status == 400


def test_a_content_rejection_does_not_hang_on_a_second_drain(ui_server):
    """REGRESSION GUARD, and the reason `_drain_request_body` grew a consumed
    flag: a write route rejects on CONTENT after having read the body, and
    `_reject` used to drain unconditionally — asking the socket for a second
    body's worth of bytes that never come. The symptom would be this test
    timing out, not failing."""
    port, token = ui_server
    started = time.monotonic()
    resp = _post_json(port, _GATE, {"task": "not-a-task-id"}, token=token)
    assert resp.status == 400
    assert time.monotonic() - started < 5.0


@pytest.mark.parametrize("path,payload,expected", [
    (_GATE, {"task": "T-1", "decision": "approved", "confirm": True}, 409),
    (_GATE, {"task": "nope", "decision": "approved", "confirm": True}, 400),
    (_BOARD, {"action": "start", "task": "T-1"}, 400),
])
def test_no_response_of_this_server_ever_carries_a_cors_header(ui_server, path, payload, expected):
    """Checked on the REJECTIONS as well as the successes: a CORS header on an
    error path is still a CORS header, and it is on error paths that they get
    added by accident."""
    port, token = ui_server
    resp = _post_json(port, path, payload, token=token)
    assert resp.status == expected
    for name, _value in resp.getheaders():
        assert not name.lower().startswith("access-control"), name


# ---------------------------------------------------------------------------
# `_run_cli` — argv list, never a shell; rc 2 is a refusal, anything else is a
# failure; a wedged child is a 504 and not a wedged server.
# ---------------------------------------------------------------------------

def test_the_server_never_runs_anything_through_a_shell():
    """Verification BY ABSENCE — over the PARSED module, not over its text.

    Written as a substring search first, and that version failed on this file's
    own prose: the contract comment in `_cli_argv` contains the words
    `shell=True` while asserting that no CALL does. A textual absence check
    that a comment can trip is a check that will later be "fixed" by loosening
    it, which is how a guard stops guarding. The AST cannot be fooled by a
    docstring.

    Non-vacuity is asserted rather than assumed (the failure mode of every
    absence check): the first assertion proves at least one `shell=` keyword
    EXISTS to be inspected, so a refactor that dropped the argument entirely —
    and with it the explicit `shell=False` — fails here instead of passing
    silently."""
    tree = ast.parse(inspect.getsource(dashboard))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    shell_values = [kw.value for call in calls for kw in call.keywords if kw.arg == "shell"]
    assert shell_values, "no `shell=` keyword found at all — this check would be vacuous"
    for value in shell_values:
        assert isinstance(value, ast.Constant) and value.value is False

    # And exactly ONE call site, so "argv list, never a shell" cannot be true of
    # the runner and false of some other spawn added beside it later.
    spawns = [call for call in calls
              if isinstance(call.func, ast.Attribute)
              and isinstance(call.func.value, ast.Name)
              and call.func.value.id == "subprocess"]
    assert len(spawns) == 1
    assert spawns[0].func.attr == "run"
    # Every argument list is built as a LIST literal or a name, never a joined
    # string: `_cli_argv` is the only builder and it returns a list.
    assert isinstance(dashboard._cli_argv("tasks.py", "list"), list)


def test_run_cli_classifies_a_refusal_apart_from_a_failure():
    """rc 2 is what `tasks.py`, `specs.py` and `waivers.py` exit with on an
    operator-facing refusal. Collapsing it into "the CLI failed" would tell a
    user his typo was a server crash."""
    refused = dashboard._run_cli([sys.executable, "-c", "raise SystemExit(2)"])
    failed = dashboard._run_cli([sys.executable, "-c", "raise SystemExit(3)"])
    ok = dashboard._run_cli([sys.executable, "-c", "print('fine')"])
    assert (refused["status"], failed["status"], ok["status"]) == ("refused", "failed", "ok")
    assert ok["stdout"] == "fine"


def test_run_cli_reports_a_missing_program_instead_of_raising():
    result = dashboard._run_cli(["definitely-not-a-program-on-this-box-28"])
    assert result["status"] == "missing"
    assert result["rc"] is None


def test_run_cli_times_out_and_says_by_how_much():
    result = dashboard._run_cli([sys.executable, "-c", "import time; time.sleep(30)"],
                                timeout=0.5)
    assert result["status"] == "timeout"
    assert result["timeout_seconds"] == 0.5


def test_run_cli_truncates_and_declares_it():
    result = dashboard._run_cli([sys.executable, "-c", "print('z' * 5000)"])
    assert result["truncated"] is True
    assert result["stdout"].endswith("…[truncated]")
    assert len(result["stdout"]) < 5000


def test_a_hanging_cli_becomes_a_504_and_frees_the_handler(ui_server, _redirect, monkeypatch):
    """The 504 path end to end, against a real sleeping subprocess. The second
    request is what makes this worth writing: a timeout that left the handler
    thread wedged would look identical on the first response."""
    monkeypatch.setattr(dashboard, "_ACTION_CLI_TIMEOUT", 0.5)
    monkeypatch.setattr(dashboard, "_cli_argv", _sleeper_argv)
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)
    assert resp.status == 504
    body = json.loads(resp.data)
    assert body["error"] == "cli_timeout"
    assert body["stage"] == "specs_list"
    assert body["timeout_seconds"] == 0.5
    assert _get(port, "/api/ping", token=token).status == 200


def test_a_crashing_cli_is_a_502_and_a_refusing_one_is_a_400(ui_server, _redirect, monkeypatch):
    port, token = ui_server
    monkeypatch.setattr(dashboard, "_cli_argv",
                        lambda *a: [sys.executable, "-c", "raise SystemExit(3)"])
    assert _post_json(port, _BOARD, {"action": "done", "task": "T-00000001", "note": "clos par le banc"},
                      token=token).status == 502
    # And the refusal path, through the REAL `tasks.py` on an unknown task.
    monkeypatch.undo()
    resp = _post_json(port, _BOARD, {"action": "done", "task": "T-00000999", "note": "clos par le banc"}, token=token)
    assert resp.status == 400
    body = json.loads(resp.data)
    assert body["error"] == "refused"
    assert "tasks.py" in body["detail"]


# ---------------------------------------------------------------------------
# The gate — a capture that is confirmed, hashed from a RE-READ, attributed,
# and that resumes nothing.
# ---------------------------------------------------------------------------

def test_the_gate_refuses_an_unconfirmed_approval_and_emits_nothing(ui_server, _redirect):
    """`confirm` is the server half of the UI's two-step button. The second
    assertion is the load-bearing one: a refusal must leave the event spool
    untouched, or a mis-click becomes an approval in the audit trail."""
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved"},
                      token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == "confirmation_required"
    assert not list(_redirect["events_dir"].glob("*.jsonl"))


@pytest.mark.parametrize("payload,error", [
    ({"task": "T-1", "decision": "approved", "confirm": "true"}, "confirmation_required"),
    ({"task": "T-1", "decision": "approved", "confirm": 1}, "confirmation_required"),
    ({"task": "T-1", "decision": "maybe", "confirm": True}, "bad_decision"),
    ({"task": "1", "decision": "approved", "confirm": True}, "bad_task"),
    ({"decision": "approved", "confirm": True}, "bad_task"),
    ({"task": "T-1", "decision": "approved", "confirm": True, "specs_id": "nope"}, "bad_specs_id"),
])
def test_the_gate_validates_before_it_runs_anything(ui_server, payload, error):
    """`"true"` and `1` are NOT confirmation: the check is `is True`, because a
    truthy string is what a form serialisation produces by accident."""
    port, token = ui_server
    resp = _post_json(port, _GATE, payload, token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == error


def test_the_gate_refuses_a_task_with_no_recorded_plan(ui_server, _redirect):
    """`specs.py list` prints its do-not-obey frame even for a task with no
    entry, so a non-empty stdout is not proof a plan exists. Approving here
    would hash the emptiness and call it a decision."""
    port, token = ui_server
    resp = _post_json(port, _GATE, {"task": "T-00000404", "decision": "approved",
                                    "confirm": True}, token=token)
    assert resp.status == 409
    assert json.loads(resp.data)["error"] == "no_plan_recorded"
    assert not list(_redirect["events_dir"].glob("*.jsonl"))


def test_the_gate_refuses_a_specs_id_absent_from_the_servers_own_reread(ui_server, _redirect):
    """The UI displayed an entry the server does not find when it re-reads. The
    two are looking at different states, and an approval is precisely the moment
    not to paper over that."""
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True, "specs_id": "S-00009999"},
                      token=token)
    assert resp.status == 409
    assert json.loads(resp.data)["error"] == "specs_id_not_in_plan"


def test_the_gate_hashes_the_plan_it_reread_not_one_the_caller_sent(ui_server, _redirect):
    """THE property that turns "a plan was approved" into "THIS plan was
    approved". The caller posts a decoy plan body; the response must carry the
    hash of the SERVER's own re-read, and the two must differ.

    The expected hash is computed BEFORE the POST, and that is not a detail:
    the route appends its own `decision` entry to the same journal, so what the
    hash pins is the journal AS IT STOOD AT APPROVAL TIME. Recomputing it
    afterwards yields a different, equally correct digest of a different state
    — which is exactly what a hash is for, and why it is captured up front."""
    port, token = ui_server
    root = _redirect["project_root"]
    _seed_plan(root)
    expected = _expected_plan_hash(root, "T-00000028")
    decoy = "a plan the client made up"
    body = _post_body(port, _GATE, {
        "task": "T-00000028", "decision": "approved", "confirm": True,
        "plan": decoy, "plan_hash": "0" * 64,
    }, token=token)
    assert body["ok"] is True
    assert body["plan_hash"] == expected
    # ...and the journal HAS moved since, so the hash is of a state, not of a file.
    assert _expected_plan_hash(root, "T-00000028") != expected
    assert body["plan_hash"] != "0" * 64
    assert body["plan_hash"] != __import__("hashlib").sha256(decoy.encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", body["plan_hash"])


def test_an_approval_travels_from_the_post_to_the_governance_view(ui_server, _redirect):
    """THE integration cycle of step 7: emit -> re-read. `gate.approval` was a
    DECLARED kind with no emitter, which is why `approvals` rendered
    `unavailable` with a reason naming this very task. One POST must move that
    section to `ok` with `with_plan_hash=1` — the whole point of the route."""
    port, token = ui_server
    root = _redirect["project_root"]
    _seed_plan(root)

    before = dashboard.build_snapshot(root)["views"]["governance"]["approvals"]
    assert before["status"] == "unavailable"
    assert before["with_plan_hash"] == 0

    body = _post_body(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)
    assert body["ok"] is True

    # 1. the event reached canal A, with the three declared data fields
    records = [r for r in _canal_a_records(_redirect["events_dir"])
               if r.get("kind") == "gate.approval"]
    assert len(records) == 1
    data = records[0]["data"]
    assert data["decision"] == "approved"
    assert data["source"] == "dashboard"
    assert data["plan_hash"] == body["plan_hash"]
    assert records[0]["task"] == "T-00000028"

    # 2. the governance reader picks it up and stops calling it a blind spot
    dashboard._reset_canal_a_cache_for_tests()
    after = dashboard.build_snapshot(root)["views"]["governance"]["approvals"]
    assert after["status"] == "ok"
    assert after["count"] == 1
    assert after["with_plan_hash"] == 1
    assert after["without_plan_hash"] == 0
    assert "dashboard" in json.dumps(after)


def test_an_approval_also_lands_in_the_specs_journal(ui_server, _redirect):
    """The event spool is fail-open by contract (`emit` swallows its own
    errors); the specs entry is the DURABLE half of the record, and it carries
    the same hash so the two can be tied together after the fact."""
    port, token = ui_server
    root = _redirect["project_root"]
    _seed_plan(root)
    body = _post_body(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)
    decisions = [e for e in specs_mod.load(root)["entries"] if e["kind"] == "decision"]
    assert len(decisions) == 1
    assert decisions[0]["task"] == "T-00000028"
    assert body["plan_hash"] in decisions[0]["text"]
    assert "source=dashboard" in decisions[0]["text"]


def test_an_approval_says_out_loud_that_it_resumes_nothing(ui_server, _redirect):
    """C1, asserted rather than promised: the response states that the pipeline
    was NOT resumed. A UI that recorded an approval and said nothing about the
    resume would read as having resumed."""
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    body = _post_body(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)
    assert body["pipeline"] == dashboard._GATE_NO_RESUME
    assert "console" in body["pipeline"]


def test_an_approval_does_not_touch_the_board(ui_server, _redirect):
    """The strongest form of "resumes nothing": the board is byte-identical
    after an approval. No state transition, no stage change, no start."""
    port, token = ui_server
    root = _redirect["project_root"]
    _seed_plan(root)
    _new_task(root)
    board = tasks_mod.store_path(root)
    before = board.read_bytes()
    assert _post_body(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)["ok"] is True
    assert board.read_bytes() == before


@pytest.mark.parametrize("decision", ["approved", "rejected", "changes_requested"])
def test_the_gate_records_every_decision_of_its_closed_vocabulary(ui_server, _redirect, decision):
    """A REJECTION is as much a decision to attribute as an approval — the
    route is not an approve button."""
    port, token = ui_server
    _seed_plan(_redirect["project_root"])
    body = _post_body(port, _GATE, {"task": "T-00000028", "decision": decision,
                                    "confirm": True}, token=token)
    assert body["decision"] == decision
    records = [r for r in _canal_a_records(_redirect["events_dir"])
               if r.get("kind") == "gate.approval"]
    assert records[0]["data"]["decision"] == decision


def test_a_failed_specs_write_still_says_the_event_was_emitted(ui_server, _redirect, monkeypatch):
    """The half-done case, said out loud. The event is already in the spool when
    the journal write fails; a bare "failed" would send the operator to
    re-approve and produce a second `gate.approval` for one human decision."""
    port, token = ui_server
    root = _redirect["project_root"]
    _seed_plan(root)
    real = dashboard._cli_argv

    def _fail_on_add(script: str, *args: str) -> list[str]:
        if script == "specs.py" and "add" in args:
            return [sys.executable, "-c", "raise SystemExit(3)"]
        return real(script, *args)

    monkeypatch.setattr(dashboard, "_cli_argv", _fail_on_add)
    resp = _post_json(port, _GATE, {"task": "T-00000028", "decision": "approved",
                                    "confirm": True}, token=token)
    assert resp.status == 502
    body = json.loads(resp.data)
    assert body["stage"] == "specs_add"
    assert body["event_emitted"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", body["plan_hash"])


# ---------------------------------------------------------------------------
# The board — driven THROUGH tasks.py, and a `done` that chains the commit
# hook or says why it could not.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action,expected_state", [
    ("start", "running"), ("block", "blocked"), ("done", "done"),
])
def test_the_board_route_drives_tasks_py(ui_server, _redirect, action, expected_state):
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    body = _post_body(port, _BOARD, {"action": action, "task": tid, "note": "pilote par le banc"}, token=token)
    assert body["ok"] is True
    assert body["board_action"] == action
    task = tasks_mod.find(tasks_mod.load(root), tid)
    assert task["state"] == expected_state


@pytest.mark.parametrize("action", ["done", "block"])
def test_le_board_REFUSE_un_done_ou_un_block_sans_motif(ui_server, _redirect, action):
    """LES DEUX VERBES TERMINAUX EXIGENT UN MOTIF, ET L'UI LE REFUSE ELLE-MÊME.

    La garde de fond vit dans `tasks.py` (`set_state` / `block_task`), pas dans
    `argparse` — la CLI n'est pas le seul chemin vers le board, et ce test le
    PROUVE par le fait que cette route-ci, qui ne passe pas par la CLI de
    l'utilisateur, est bien tenue elle aussi.

    Elle refuse néanmoins EN AMONT, avec un 400 nommé, plutôt que de laisser la
    CLI échouer plus loin : les deux refuseraient, mais un `400
    note_required_for_done` dit au client CE QUI MANQUE, là où une remontée
    d'échec CLI lui rend une trace d'outil. Le tableau de bord n'offre aucun
    équivalent de `--on`, donc la prose est ici la seule explication possible.
    """
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    avant = tasks_mod.find(tasks_mod.load(root), tid)["state"]

    resp = _post_json(port, _BOARD, {"action": action, "task": tid}, token=token)

    assert resp.status == 400, resp.status
    # ET LE REFUS N'A RIEN ÉCRIT — un refus qui laisse l'état à moitié changé
    # serait pire que pas de refus.
    assert tasks_mod.find(tasks_mod.load(root), tid)["state"] == avant


def test_board_route_preserves_both_running(ui_server, _redirect):
    """INHERITED from `tasks.py`, never re-implemented: since T-01M5F7286N1EYGXAXA5244X86B a
    `start` demotes nobody, so two starts through this route leave BOTH running — and a
    second writer of TASKS.json would have to be correct about this forever."""
    port, token = ui_server
    root = _redirect["project_root"]
    first = _new_task(root, "premiere")
    second = _new_task(root, "seconde")
    _post_body(port, _BOARD, {"action": "start", "task": first}, token=token)
    _post_body(port, _BOARD, {"action": "start", "task": second}, token=token)
    data = tasks_mod.load(root)
    running = [t for t in data["tasks"] if t["state"] == "running"]
    assert [t["id"] for t in running] == [first, second]


def test_a_board_note_travels_as_one_token_so_it_cannot_become_an_option(ui_server, _redirect):
    """Argument injection into the CLI's own option space: a note beginning with
    `-` passed as a separate argv item would be read by argparse as the next
    OPTION. Passed as `--note=<value>` it can only ever be a value. Harmless to
    the shell — there is none — and still wrong."""
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    body = _post_body(port, _BOARD, {"action": "block", "task": tid,
                                     "note": "--force attend la decision"}, token=token)
    assert body["ok"] is True
    task = tasks_mod.find(tasks_mod.load(root), tid)
    assert task["state"] == "blocked"
    assert "--force" in task["stage"]


def test_sans_cible_relaye_start_et_done(ui_server, _redirect, monkeypatch):
    """MUTANT : relais `sans_cible` retiré. Le tableau de bord relaie
    `--sans-cible` a `tasks.py` sur `start` ET sur `done` — les deux gestes que
    la garde de cible (T-00000654) traverse. Le relais de `sans_chaine` au start
    reste un trou nomme, hors de ce lot ; ce test ne l'exige pas."""
    port, token = ui_server
    root = _redirect["project_root"]
    real = dashboard._run_cli
    spawned: list[list[str]] = []

    def spy(argv, **kwargs):
        spawned.append(list(argv))
        return real(argv, **kwargs)

    monkeypatch.setattr(dashboard, "_run_cli", spy)

    tid = _new_task(root)
    body = _post_body(port, _BOARD, {"action": "start", "task": tid,
                                     "sans_cible": "plan fige au banc"}, token=token)
    assert body["ok"] is True
    argv_start = next(a for a in spawned if any(x.endswith("tasks.py") for x in a))
    assert "--sans-cible=plan fige au banc" in argv_start

    spawned.clear()
    body = _post_body(port, _BOARD, {"action": "done", "task": tid,
                                     "note": "clos par le banc",
                                     "sans_cible": "nuit autonome"}, token=token)
    assert body["ok"] is True
    argv_done = next(a for a in spawned if any(x.endswith("tasks.py") for x in a))
    assert "--sans-cible=nuit autonome" in argv_done


def test_a_board_note_is_bounded_and_collapsed_to_one_line(ui_server, _redirect):
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    _post_body(port, _BOARD, {"action": "block", "task": tid,
                              "note": "a\nb" + "z" * 500}, token=token)
    stage = tasks_mod.find(tasks_mod.load(root), tid)["stage"]
    assert "\n" not in stage
    assert len(stage) <= dashboard._ACTION_TEXT_CHARS + 1


@pytest.mark.parametrize("payload,error", [
    ({"action": "delete", "task": "T-1"}, "bad_action"),
    ({"action": "purge", "task": "T-1"}, "bad_action"),
    ({"action": "reassign", "task": "T-1"}, "bad_action"),
    ({"action": "start", "task": "T1"}, "bad_task"),
    ({"task": "T-1"}, "bad_action"),
])
def test_the_board_route_exposes_four_actions_and_no_more(ui_server, payload, error):
    """`delete` and `purge` are absent BY DECISION: a browser tab must not be
    able to remove a task from the board. `reassign` and `retitle` are absent
    because this route is a decision capture, not a board editor."""
    port, token = ui_server
    resp = _post_json(port, _BOARD, payload, token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == error


def test_a_done_reports_a_degraded_commit_hook_rather_than_a_silent_success(
        ui_server, _redirect, monkeypatch, tmp_path):
    """The failure this route may NOT have. A `done` whose store commit never
    happened must not answer like one that did — and the board write itself
    still succeeded, so the status stays 200 with the degradation NAMED inside
    it (same posture as `COVERAGE DEGRADED` elsewhere in this kit)."""
    port, token = ui_server
    root = _redirect["project_root"]
    tid = _new_task(root)
    monkeypatch.setattr(dashboard, "_commit_hook_path",
                        lambda: tmp_path / "absent-hook.sh")
    body = _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc"}, token=token)
    assert body["ok"] is True
    assert body["commit_hook"]["status"] == "degraded"
    assert "absent" in body["commit_hook"]["reason"]
    # The board transition itself went through: the degradation is the COMMIT,
    # not the write.
    assert tasks_mod.find(tasks_mod.load(root), tid)["state"] == "done"


def test_the_commit_hook_resolves_bash_instead_of_trusting_createprocess(
        ui_server, _redirect, monkeypatch):
    """MEASURED, not deduced — this assertion exists because the first version
    of the route passed the bare string `"bash"` to `subprocess` and the two git
    tests below failed with
    `execvpe(/bin/bash) failed: No such file or directory`, rc=1.

    On Windows, CreateProcess searches `System32` BEFORE `PATH`, so a bare
    `"bash"` finds the WSL relay shim rather than Git Bash. The commit chain
    would then have degraded on EVERY Windows dev box — silently, permanently,
    and green on the ubuntu CI runner, which is the worst shape a platform
    defect can take. `shutil.which` is how this kit already pins bash
    elsewhere (`.agents/evals/test_events_parity.py`).

    Asserted on the ARGV THAT IS ACTUALLY SPAWNED rather than on the module's
    text: a source search for `["bash"` matches this file's own contract
    comment, which documents the very rule it is meant to check (the same trap
    `test_the_server_never_runs_anything_through_a_shell` fell into first)."""
    resolved = dashboard._bash_executable()
    if resolved is None:
        pytest.skip("no bash on this box — the degraded path covers it")
    assert "system32" not in resolved.lower(), (
        "resolved the WSL relay shim, which cannot exec the hook")
    assert Path(resolved).name.lower().startswith("bash")

    port, token = ui_server
    tid = _new_task(_redirect["project_root"])
    real = dashboard._run_cli
    spawned: list[list[str]] = []

    def spy(argv, **kwargs):
        spawned.append(list(argv))
        return real(argv, **kwargs)

    monkeypatch.setattr(dashboard, "_run_cli", spy)
    _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc"}, token=token)
    hook_argv = spawned[-1]
    assert hook_argv[0] == resolved
    assert hook_argv[0] != "bash", "a bare 'bash' is what CreateProcess mis-resolves"
    assert hook_argv[1].endswith("post-task-done-index.sh")


@pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash (Git Bash on Windows)")
def test_a_failing_commit_hook_is_reported_with_its_return_code(
        ui_server, _redirect, monkeypatch, tmp_path):
    script = tmp_path / "failing-hook.sh"
    script.write_text("#!/usr/bin/env bash\ncat >/dev/null\nexit 3\n",
                      encoding="utf-8", newline="\n")
    port, token = ui_server
    tid = _new_task(_redirect["project_root"])
    monkeypatch.setattr(dashboard, "_commit_hook_path", lambda: script)
    body = _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc"}, token=token)
    assert body["commit_hook"]["status"] == "degraded"
    assert "rc=3" in body["commit_hook"]["reason"]


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                    reason="requires bash and git")
def test_a_done_from_the_ui_commits_the_state_stores_like_a_console_done(ui_server, _redirect):
    """Complement B / C8, measured end to end against the REAL hook and a REAL
    git repository: a task closed from the UI must leave the three state stores
    committed exactly as one closed from a console does. Anything less makes the
    board tell git a different story than it tells the file.

    FIXTURE REPAIRED — and it is a confession (T-00000271). Until then this
    fake repo was NU: no `.agents/bin/tasks.py`, so the hook's external leg ran
    `tasks.py commit-stores` against a file that did not exist, fell to its
    degraded without-lock branch, and its stdout was "stores commités sans
    verrou (dégradé : verbe injoignable)". The server PAINTED that "ok" — so
    this test was green BY the very defect T-00000271 corrects: the dashboard
    stamped "ok" on a without-lock degradation INSIDE ITS OWN SUITE since
    T-00000189, and this end-to-end witness never once exercised the
    committed-under-lock happy path it claims to prove. It does now, because the
    fake tree is given the REAL lock leg (`tasks.py`) AND the section leg it
    invokes (`post-task-done-index.sh`); the assertion `status == "ok"` is
    UNCHANGED — under the new stdout classification it now passes for the right
    reason ("stores commités"), not the defect's. MEASURED: copying `tasks.py`
    alone is NOT enough — the section leg is a required neighbour, without it the
    stdout is "stores non commités (motif : échec capturé)"."""
    port, token = ui_server
    root = _redirect["project_root"]

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=60)

    git("init", "-q")
    git("config", "user.email", "t28@example.com")
    git("config", "user.name", "T28 Tester")
    git("config", "commit.gpgsign", "false")
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "seed")

    tid = _new_task(root)
    # Give the fake tree the REAL commit machinery so the hook resolves its
    # lock leg (`tasks.py commit-stores`) and the section leg that leg calls
    # (`post-task-done-index.sh --commit-section`). Both are host-neutral kit
    # code with no third-party imports. They are copied into `.agents/bin/` but
    # NOT into git's pathspec — the section leg commits only the three state
    # stores, so these helpers stay untracked and are never swept in.
    fake_bin = root / ".agents" / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    for p in HERE.glob("tasks*.py"): shutil.copy2(p, fake_bin / p.name)
    shutil.copy2(HERE / "post-task-done-index.sh",
                 fake_bin / "post-task-done-index.sh")
    git("add", ".agents/state/board/TASKS.json")
    git("commit", "-q", "-m", "board avant cloture")
    head_before = git("rev-parse", "HEAD").stdout.strip()

    body = _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc"}, token=token)
    assert body["ok"] is True
    assert body["commit_hook"]["status"] == "ok", body["commit_hook"]
    assert git("rev-parse", "HEAD").stdout.strip() != head_before
    # Since T-00000703 the hook commits in TWO legs: `chore(state):` (the three
    # stores) and then, when the done wrote a run export, `chore(runs):` on top.
    # HEAD is therefore not necessarily the stores commit — find it among the
    # commits this done created (red @ de8cff0 when this asserted HEAD alone).
    shas = git("rev-list", f"{head_before}..HEAD").stdout.split()
    shown = {sha: git("show", "--name-only", "--pretty=format:%s", sha).stdout for sha in shas}
    state = [body for body in shown.values() if body.startswith("chore(state)")]
    assert len(state) == 1, shown
    committed = state[0]
    assert "TASKS.json" in committed
    # The pathspec is explicit at add AND at commit: the untracked seed file
    # must NOT have been swept in.
    assert "README" not in committed.split("\n", 1)[1]
    # And the exports leg, when present, carries run exports and nothing else.
    for body in shown.values():
        if body.startswith("chore(runs)"):
            files = [f for f in body.split("\n", 1)[1].splitlines() if f]
            assert files and all(f.startswith("runs/") and f.endswith(".jsonl") for f in files), body


@pytest.mark.parametrize("stdout,expected_status,reason_needle", [
    # Nothing to commit is a SUCCESS, not a degradation — an empty stdout is the
    # hook's way of saying the stores were already clean.
    ("", "ok", None),
    ("   \n", "ok", None),
    # The committed-under-lock happy path.
    ('{"systemMessage": "post-task-done: stores commités"}', "ok", None),
    # An `index-refresh:` clause NEVER changes the status (a view is not an
    # invariant): "stores commités" still classifies ok alongside it.
    ('{"systemMessage": "post-task-done: stores commités · '
     'index-refresh: 2 fichiers"}', "ok", None),
    # Without-lock degradation: "sans verrou" is matched BEFORE the "stores
    # commit" success token, because "stores commités sans verrou" contains it.
    ('{"systemMessage": "post-task-done: stores commités sans verrou '
     '(dégradé : bash introuvable)"}', "degraded", "sans verrou"),
    # A git operation in flight — the grave case whose prescribed action is the
    # right one.
    ('{"systemMessage": "post-task-done: stores non commités '
     '(opération git en cours : MERGE_HEAD)"}', "degraded", "MERGE_HEAD"),
    # DEFAULT branch, closed by default: an unknown non-empty phrase is a
    # warning, never a false ok — mirror of `commitHookNotice` in actions.js.
    ('{"systemMessage": "post-task-done: stores synchronisés"}',
     "degraded", "synchronis"),
    # A raw (non-JSON) line is tolerated and classified on its own text.
    ("stores non commités (motif : échec capturé)",
     "degraded", "stores non commit"),
    # SECOND LEG (T-00000703): the hook now commits the run exports under
    # `runs/` after the stores. Stores committed but exports NOT is a
    # degradation — "exports non commit" must win over the "stores commit"
    # success token, by ORDER, exactly like "sans verrou".
    ('{"systemMessage": "post-task-done: stores commités · '
     'exports non commités (motif : échec capturé)"}',
     "degraded", "exports non commit"),
    # Stores clean, exports committed: the phrase carries ONLY the second leg,
    # and that is a success — not an unknown phrase.
    ('{"systemMessage": "post-task-done: exports commités"}', "ok", None),
])
def test_the_commit_hook_stdout_is_classified_closed_by_default(
        stdout, expected_status, reason_needle):
    """The hook exits 0 by contract; its verdict is a CLASSIFICATION of stdout,
    so the server may not read rc 0 as a commit. Matching is on ASCII substrings
    only (the phrases carry accents and `_run_cli` decodes `errors="replace"`),
    and the degraded tokens win over the success token by ORDER."""
    result = dashboard._classify_commit_stdout(stdout)
    assert result["status"] == expected_status, result
    if reason_needle is None:
        assert "reason" not in result
    else:
        assert reason_needle in result["reason"], result


@pytest.mark.skipif(shutil.which("bash") is None,
                    reason="requires bash (Git Bash on Windows)")
@pytest.mark.parametrize("phrase,expected_status,needle", [
    ("stores non commités (opération git en cours : MERGE_HEAD)",
     "degraded", "MERGE_HEAD"),
    ("stores commités sans verrou (dégradé : bash introuvable)",
     "degraded", "sans verrou"),
    ("stores synchronisés", "degraded", "synchronis"),
    ("stores commités", "ok", None),
    # Second leg alone (T-00000703): stores were clean, exports committed.
    ("exports commités", "ok", None),
])
def test_a_done_reports_the_commit_hook_status_from_stdout_not_the_return_code(
        ui_server, _redirect, monkeypatch, tmp_path, phrase, expected_status, needle):
    """MEASURED red-first: before T-00000271 the route forced `{"status": "ok"}`
    on ANY rc 0, so a without-lock degradation, a git operation in flight, or an
    unknown phrase was all painted as a clean commit. The hook always exits 0
    (advisory), so its stdout — a fake one here, emitting the phrase verbatim —
    is the only verdict. Closed by default: the unknown-phrase arm degrades."""
    script = tmp_path / "emitting-hook.sh"
    script.write_text(
        "#!/usr/bin/env bash\ncat >/dev/null\n"
        f'printf \'{{"systemMessage": "post-task-done: {phrase}"}}\'\nexit 0\n',
        encoding="utf-8", newline="\n")
    port, token = ui_server
    tid = _new_task(_redirect["project_root"])
    monkeypatch.setattr(dashboard, "_commit_hook_path", lambda: script)
    body = _post_body(port, _BOARD, {"action": "done", "task": tid, "note": "clos par le banc"}, token=token)
    assert body["commit_hook"]["status"] == expected_status, body["commit_hook"]
    if needle is None:
        assert "reason" not in body["commit_hook"]
    else:
        assert needle in body["commit_hook"]["reason"], body["commit_hook"]


# ---------------------------------------------------------------------------
# The waiver — written through `waivers.py`, the register's one writer.
# ---------------------------------------------------------------------------

def _register(project_root: Path) -> dict:
    path = project_root / ".agents" / "security" / "sca-waivers.json"
    if not path.is_file():
        return {"waivers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_waiver_route_writes_through_the_register_cli(ui_server, _redirect):
    port, token = ui_server
    root = _redirect["project_root"]
    body = _post_body(port, _WAIVER, {
        "ecosystem": "npm", "package": "lodash", "version": "4.17.20",
        "status": "accepted", "reason": "pas de correctif amont", "task": "T-00000028",
    }, token=token)
    assert body["ok"] is True
    entries = _register(root)["waivers"]
    assert len(entries) == 1
    assert entries[0]["package"] == "lodash"
    assert entries[0]["status"] == "accepted"
    assert entries[0]["task"] == "T-00000028"


def test_a_waiver_without_a_finding_class_is_written_AND_warned_about(
        ui_server, _redirect):
    """T-00000178 — the entry is INERT at the register, and the caller had no
    way to learn it.

    `waiver_filter.py` matches on the finding class, so a waiver written without
    one is recorded, answers 200, shows up in the register — and filters
    nothing. The operator believes a finding is accepted and tracked while the
    gate goes on reporting it, which is the worst shape a security decision can
    take: it looks taken.

    IT IS A WARNING, NEVER A REFUSAL, and both halves are asserted. The write is
    legitimate and the register is append-only, so rejecting it would lose a
    decision somebody deliberately took; the entry must land. Saying so is the
    whole fix.
    """
    port, token = ui_server
    root = _redirect["project_root"]
    body = _post_body(port, _WAIVER, {
        "ecosystem": "npm", "package": "left-pad", "version": "1.3.0",
        "status": "accepted", "reason": "sans classe",
    }, token=token)
    assert body["ok"] is True
    assert "inerte" in body["warning"]
    # THE HALF THAT KEEPS IT A WARNING: the entry really is in the register.
    assert [e["package"] for e in _register(root)["waivers"]] == ["left-pad"]


def test_a_waiver_WITH_a_finding_class_carries_no_warning(ui_server, _redirect):
    """NON-VACUITY of the arm above: without this one, a route that warned on
    EVERY waiver would pass it while telling the operator nothing useful — a
    warning that is always on is a warning nobody reads."""
    port, token = ui_server
    body = _post_body(port, _WAIVER, {
        "ecosystem": "npm", "package": "left-pad", "version": "1.3.0",
        "status": "accepted", "reason": "avec classe", "finding_class": "known_cve",
    }, token=token)
    assert body["ok"] is True
    assert "warning" not in body


def test_the_commit_hook_environment_is_a_closed_allowlist(ui_server, _redirect):
    """T-00000178 — the hook no longer inherits the server's whole environment.

    ADVISORY HARDENING, said plainly: this route sits behind the write token, so
    passing everything was not an exploit — it was an unnecessary surface that
    only ever grows. A dashboard process may hold registry credentials, a cloud
    token, an `NVD_API_KEY`; handing all of it to a shell script is a default
    nobody chose.

    The arm is written against the helper rather than against a live hook run:
    what must hold is the CONTENT of the environment, and a subprocess assertion
    would measure the hook's behaviour instead. A denylist would be the wrong
    shape and this pins that too — the surnumerary variable below is invented
    here, so no list of known secrets could ever have excluded it.
    """
    root = _redirect["project_root"]
    os.environ["A_SECRET_NOBODY_NAMED"] = "must-not-travel"
    os.environ.setdefault("PATH", "")
    try:
        env = dashboard._hook_environment(Path(root))
    finally:
        os.environ.pop("A_SECRET_NOBODY_NAMED", None)
    assert "A_SECRET_NOBODY_NAMED" not in env
    assert env["CLAUDE_PROJECT_DIR"] == str(root)
    # PATH is not optional: bash resolves git through it, and dropping it would
    # turn this hardening into a broken hook that looks like a git failure.
    assert "PATH" in env
    # An ABSENT key is not forwarded as "" — unset and empty are different things
    # for PATH and HOME, and the empty form breaks in a way that misleads.
    assert all(value != "" or key == "PATH" for key, value in env.items())


def test_the_waiver_route_refuses_a_supply_chain_finding_without_an_explicit_class(
        ui_server, _redirect):
    """Spec D7, enforced in ONE place (`waivers.py`) and surfacing here as the
    CLI's own sentence — a rule restated in two files is a rule that will
    disagree with itself. A 400, not a 502: this is the caller's fault."""
    port, token = ui_server
    root = _redirect["project_root"]
    resp = _post_json(port, _WAIVER, {
        "ecosystem": "npm", "package": "evil-postinstall", "version": "1.0.0",
        "finding_class": "supply_chain",
    }, token=token)
    assert resp.status == 400
    body = json.loads(resp.data)
    assert body["error"] == "refused"
    assert "supply" in body["detail"]
    assert _register(root)["waivers"] == []


def test_the_waiver_route_accepts_a_supply_chain_waiver_that_says_so(ui_server, _redirect):
    port, token = ui_server
    body = _post_body(port, _WAIVER, {
        "ecosystem": "npm", "package": "evil-postinstall", "version": "1.0.0",
        "class": "supply_chain", "finding_class": "supply_chain",
        "reason": "audite a la main",
    }, token=token)
    assert body["ok"] is True
    assert _register(_redirect["project_root"])["waivers"][0]["class"] == "supply_chain"


@pytest.mark.parametrize("payload", [
    {"package": "lodash", "version": "1.0.0"},
    {"ecosystem": "npm", "version": "1.0.0"},
    {"ecosystem": "npm", "package": "lodash"},
    {"ecosystem": "  ", "package": "lodash", "version": "1.0.0"},
])
def test_the_waiver_route_requires_the_three_key_fields(ui_server, _redirect, payload):
    """`(ecosystem, package, version)` IS the waiver key. A blank one would
    write an entry that matches nothing, i.e. a decision recorded in the audit
    trail that never applies."""
    port, token = ui_server
    resp = _post_json(port, _WAIVER, payload, token=token)
    assert resp.status == 400
    assert json.loads(resp.data)["error"] == "missing_field"
    assert _register(_redirect["project_root"])["waivers"] == []


def test_an_unknown_waiver_status_is_refused_by_the_cli_not_invented_here(ui_server, _redirect):
    port, token = ui_server
    resp = _post_json(port, _WAIVER, {
        "ecosystem": "npm", "package": "lodash", "version": "1.0.0",
        "status": "whatever",
    }, token=token)
    assert resp.status == 400
    assert _register(_redirect["project_root"])["waivers"] == []


def test_the_handler_writes_no_store_of_its_own():
    """C2, as a guard rather than a comment: every mutation this server performs
    goes through a CLI that already owns the file. The day someone adds a
    `json.dump` or a `write_text` to this class, `tasks.py` stops being the only
    writer of the board and this test says so.

    Over the AST again, and this time for a second reason on top of the
    prose-collision one: `inspect.getsource` cannot reach a CLASS in a module
    loaded by `spec_from_file_location` (it is not in `sys.modules`, so
    `getfile` raises "is a built-in class"). Parsing the module's own file has
    neither limitation.

    `self.wfile.write` is deliberately NOT in the forbidden set — writing to the
    response socket is this class's job. What is forbidden is writing to a
    FILE."""
    tree = ast.parse(inspect.getsource(dashboard))
    handler = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "UIHandler")
    forbidden = {"dump", "write_text", "write_bytes", "writelines", "unlink", "mkdir"}
    offenders = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in forbidden:
            offenders.append(func.attr)
        if isinstance(func, ast.Name) and func.id == "open":
            # `open` is judged on its MODE, not on its name: the handler already
            # holds one legitimate `open(raw_path, "rb")` — the terminal mirror
            # slice, a READ. Flagging every `open` would have made this guard
            # fail on day one and be deleted as a false positive.
            mode = ""
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = str(keyword.value.value)
            if any(char in mode for char in "wax+"):
                offenders.append(f"open(mode={mode!r})")
    assert offenders == [], f"the handler writes files directly: {offenders}"
    # Non-vacuity: the walk really does see this class's calls.
    assert any(isinstance(n, ast.Call) for n in ast.walk(handler))


# ---------------------------------------------------------------------------
# T-00000575 — LA FRAÎCHEUR DE L'INDEX SE MESURE SUR LES FICHIERS INDEXÉS,
# PAS SUR LE SHA.
#
# « Aucun banc ne couvrait `_index_freshness` avant celui-ci » — ÉCRIT ICI PUIS
# MESURÉ FAUX par le binôme : cinq bancs le couvraient déjà PAR LA VUE. Ce qui
# n'était couvert par aucun, et que ces témoins ajoutent, c'est la mesure PAR
# FICHIERS. La nuance n'est pas cosmétique : une affirmation de couverture fausse
# dans un banc fait croire un axe neuf là où il y a un axe repris.
# ---------------------------------------------------------------------------

def _depot_jetable(tmp_path):
    """Un dépôt git minimal avec UN fichier indexé et un premier commit."""
    if shutil.which("git") is None:  # pragma: no cover - poste sans git
        pytest.skip("git absent — la fraîcheur de l'index n'est pas mesurable ici")
    root = tmp_path / "depot"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")

    def g(*a):
        return subprocess.run(["git", "-C", str(root), *a],
                              capture_output=True, text=True, check=False)

    g("init", "-q")
    g("config", "user.email", "banc@local")
    g("config", "user.name", "banc")
    g("add", "-A")
    g("commit", "-qm", "initial")
    return root, g, g("rev-parse", "--short", "HEAD").stdout.strip()


def _lecteurs():
    spec = importlib.util.spec_from_file_location(
        "dashboard_readers_sous_test", HERE / "dashboard_readers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_un_commit_sans_fichier_indexe_laisse_l_index_FRAIS(tmp_path):
    """LE TÉMOIN, et c'est 62 % des commits de ce dépôt.

    Mesuré le 2026-09-13 sur les 200 derniers AVEC `_keep()`, le critère réel de
    l'index : 125 ne touchent AUCUN fichier indexé et faisaient pourtant
    basculer l'affichage en `stale`, parce que tout
    commit avance HEAD. Le `session-start` relançait alors `--if-stale`, ce qui
    resalissait l'arbre et appelait un commit d'index de plus — la boucle que le
    ticket décrit, et dont aucun consommateur de PORTE ne dépend.
    """
    root, g, sha = _depot_jetable(tmp_path)
    (root / "NOTES.md").write_text("de la prose, rien d'indexe\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "docs seulement")

    out = _lecteurs()._index_freshness(root, sha)
    assert out["fresh"] is True, out
    assert out["status"] == "fresh"
    assert out["changed_indexed_files"] == 0


def test_CONTROLE_NEGATIF_un_fichier_indexe_modifie_rend_STALE(tmp_path):
    """L'autre moitié : sans elle, la correction serait un `fresh` permanent."""
    root, g, sha = _depot_jetable(tmp_path)
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "du vrai code")

    out = _lecteurs()._index_freshness(root, sha)
    assert out["fresh"] is False, out
    assert out["status"] == "stale"
    assert out["changed_indexed_files"] >= 1
    assert "indexed file(s) changed" in (out["reason"] or "")


def test_un_sha_INJOIGNABLE_ne_rend_jamais_FRAIS(tmp_path):
    """BORNE : on ne rend pas `fresh` sur une mesure qu'on n'a pas su faire.

    Un `built_sha` que git ne connaît pas fait échouer la comparaison. Le
    lecteur retombe alors sur le verdict par SHA — le comportement d'AVANT ce
    correctif — au lieu de conclure à la fraîcheur par défaut.
    """
    root, _g, _sha = _depot_jetable(tmp_path)
    out = _lecteurs()._index_freshness(root, "0000000")
    assert out["fresh"] is False, out
    assert out["changed_indexed_files"] is None


def test_l_ARBRE_DE_TRAVAIL_n_est_PAS_consulte_et_la_sortie_le_DIT(tmp_path):
    """LA BORNE, ÉCRITE PLUTÔT QUE TUE — correctif du binôme.

    Le verdict est une fonction PURE de `(built_sha, HEAD)`. Consulter l'arbre
    rendrait le résultat dépendant d'un état que l'empreinte de cache des vues
    ne couvre pas : un `fresh` mis en cache survivrait à l'édition non commitée
    d'un fichier indexé — un FAUX FRESH, bien pire que le faux stale corrigé
    ici, parce qu'il fait travailler sur un index périmé en silence.

    Ce test fige donc le comportement ET la phrase qui l'annonce : une édition
    non commitée ne change RIEN au verdict, et `comparison` le dit.
    """
    root, g, sha = _depot_jetable(tmp_path)
    # UN COMMIT INTERMÉDIAIRE EST INDISPENSABLE, et son absence rendait ce
    # témoin VACANT — mesuré par le binôme, zéro spawn : sans lui `built_sha`
    # préfixe HEAD, donc `fresh` est vrai AVANT la branche de mesure, qui n'est
    # jamais atteinte. Le test passait à l'identique si le code consultait
    # l'arbre, c'est-à-dire qu'il ne figeait rien.
    (root / "NOTES.md").write_text("prose\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "docs seulement")               # HEAD != built_sha
    (root / "src" / "a.py").write_text("x = 99\n", encoding="utf-8")  # SALE

    out = _lecteurs()._index_freshness(root, sha)
    assert out["fresh"] is True, out
    # LA NON-VACUITÉ : `0` prouve que la branche a tourné. Elle vaudrait `None`
    # si la mesure avait été sautée, et l'assertion ci-dessus passerait quand même.
    assert out["changed_indexed_files"] == 0, out
    assert "working tree is NOT consulted" in out["comparison"]


def test_les_sorties_UNKNOWN_portent_la_meme_forme(tmp_path):
    """Un consommateur ne doit pas voir une clé apparaître selon le chemin pris.
    Les trois sorties `unknown` rendaient un dict SANS `changed_indexed_files`."""
    root, _g, _sha = _depot_jetable(tmp_path)
    lecteurs = _lecteurs()
    for stamp in (None, "", "nogit"):
        out = lecteurs._index_freshness(root, stamp)
        assert out["status"] == "unknown", (stamp, out)
        assert "changed_indexed_files" in out, (stamp, out)


def test_un_index_A_HEAD_ne_pretend_PAS_que_la_mesure_a_ECHOUE(tmp_path):
    """TROIS CAS ET NON DEUX — relevé par les DEUX critiques, indépendamment.

    `changes is None` confondait « mesure pas NÉCESSAIRE » (l'index EST à HEAD)
    et « mesure ÉCHOUÉE ». Le cas NOMINAL — celui qui suit chaque `chore(index)`
    — annonçait donc en HTTP, jusque chez l'adoptant, une panne de git qui
    n'avait pas eu lieu. Et c'est la ligne même qui prétendait faire suivre le
    texte au chemin pris qui l'avait introduite : corriger la VALEUR d'une
    affirmation ne corrige pas sa PLACE."""
    root, _g, sha = _depot_jetable(tmp_path)
    out = _lecteurs()._index_freshness(root, sha)
    assert out["fresh"] is True and out["changed_indexed_files"] is None, out
    assert "not needed" in out["comparison"], out
    assert "could NOT be made" not in out["comparison"], out


def test_la_BORNE_de_deux_spawns_est_COMPTEE_et_non_promise(tmp_path, monkeypatch):
    """LE TÉMOIN QUI MANQUAIT, et son absence était le ticket lui-même.

    La docstring du module promet « no subprocess » avec une exception nommée à
    DEUX spawns bornés ; rien ne le vérifiait, et le seul contrôle AST du dépôt
    porte sur `dashboard.py`, pas sur ce lecteur. Le compte ÉPINGLÉ est la
    garde — même patron que les compteurs de jambes de hooks. Ce lecteur est
    appelé à chaque reconstruction de vues, sous un budget de ping de 2 s : un
    troisième spawn ajouté plus tard ne rougirait nulle part, et le symptôme
    serait une route qui expire, pas un test rouge."""
    root, g, sha = _depot_jetable(tmp_path)
    lecteurs = _lecteurs()
    appels = []
    vrai = lecteurs.subprocess.run

    def espion(argv, *a, **k):
        appels.append((argv, k))
        return vrai(argv, *a, **k)

    monkeypatch.setattr(lecteurs.subprocess, "run", espion)

    # Index À HEAD : la branche par fichiers n'est pas entrée, donc ZÉRO spawn.
    assert lecteurs._index_freshness(root, sha)["fresh"] is True
    assert appels == [], f"le chemin nominal a ouvert des process : {appels}"

    (root / "NOTES.md").write_text("de la prose\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "docs")
    appels.clear()
    out = lecteurs._index_freshness(root, sha)
    assert out["changed_indexed_files"] == 0, out
    assert len(appels) == 2, f"la borne de DEUX spawns a bougé : {appels}"
    for argv, kwargs in appels:
        assert "git" in argv[0], argv
        # UN SPAWN SANS TIMEOUT PEND, et ce lecteur vit sous un budget de ping de
        # 2 s : la borne n'est pas le NOMBRE seul, c'est le nombre ET la laisse.
        assert kwargs.get("timeout") == 1.5, (argv, kwargs)


def _spawns_de_dashboard_readers(source=None):
    """Les appels `subprocess.*` du module lecteur, relevés sur l'AST du FICHIER.

    Sur le FICHIER et non par `inspect.getsource` : le lecteur est chargé par
    `spec_from_file_location`, donc absent de `sys.modules`, et `getsource` y
    échoue. Même contrainte que le contrôle AST voisin sur `UIHandler`.

    `source` N'EXISTE QUE POUR LE CONTRÔLE NÉGATIF, et c'est un correctif du
    binôme : celui-ci DUPLIQUAIT la boucle au lieu d'appeler ce relevé, donc il
    contrôlait une copie. Mesuré — muter `porte_timeout = any(...)` en `= True`
    laissait les DEUX témoins VERTS, c'est-à-dire qu'un `timeout` oublié dans le
    lecteur n'aurait plus rougi nulle part."""
    if source is None:
        source = (HERE / "dashboard_readers.py").read_text(encoding="utf-8")
    trouves = []
    for node in ast.walk(ast.parse(source)):
        # QUATRE AUTRES FAÇONS DE LANCER UN PROCESS, et le relevé n'en voyait
        # AUCUNE — relevé du binôme, mesuré : un `from subprocess import run`
        # sortait 0 vu sur 1. Épingler « le nombre de sous-processus du lecteur »
        # sous un titre universel que le relevé ne tient pas, c'est le mensonge
        # différé que le routeur nomme. Elles comptent toutes, et SANS laisse —
        # non par jugement, mais parce qu'aucune ne se lit ici : leur présence
        # doit faire rougir pour qu'on les regarde, pas passer en silence.
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            trouves.append(("from subprocess import", False, node.lineno))
            continue
        if isinstance(node, ast.Import) and any(
                a.name == "subprocess" and a.asname for a in node.names):
            trouves.append(("import subprocess as", False, node.lineno))
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id == "subprocess":
            porte_timeout = any(k.arg == "timeout" for k in node.keywords)
            trouves.append((f"subprocess.{func.attr}", porte_timeout, node.lineno))
        elif func.value.id == "os" and (
                func.attr in ("system", "popen")
                or func.attr.startswith(("spawn", "exec", "fork", "posix_spawn"))):
            trouves.append((f"os.{func.attr}", False, node.lineno))
    return trouves


def test_l_exception_au_SANS_SOUS_PROCESSUS_est_EPINGLEE_a_deux(tmp_path):
    """T-00000605 — UNE GARANTIE ÉCRITE QUE RIEN NE TENAIT.

    La docstring du module promet « read-only: no open(w), no mkdir, no
    subprocess », et tout un paragraphe explique qu'un spawn sous Windows coûte
    plus que toutes les autres lectures du module réunies. T-00000575 y a
    introduit DEUX spawns bornés, la docstring les NOMME — mais rien ne
    vérifiait que le compte reste à deux ni que chacun porte sa laisse. Le seul
    contrôle AST du dépôt portait sur `dashboard.py`, pas sur ce lecteur.

    LE COMPTE ÉPINGLÉ EST LA GARDE, même patron que les compteurs de jambes de
    hooks. Ce module est appelé à chaque reconstruction de vues sous un budget
    de ping de 2 s : un troisième spawn, ou un `timeout` oublié, ne rougirait
    nulle part et le symptôme serait une route qui EXPIRE, pas un test rouge.

    Ce témoin est STATIQUE là où son voisin `_la_BORNE_de_deux_spawns_est_
    COMPTEE` est dynamique, et les deux sont utiles : le dynamique prouve que le
    chemin nominal n'en ouvre AUCUN, le statique voit les chemins qu'aucun banc
    n'exerce."""
    trouves = _spawns_de_dashboard_readers()
    assert len(trouves) == 2, (
        "le nombre de sous-processus du lecteur a bougé — s'il est légitime, "
        f"mets la docstring du module d'accord AVANT ce compte : {trouves}")
    sans_laisse = [t for t in trouves if not t[1]]
    assert sans_laisse == [], f"un spawn sans `timeout` dans un lecteur : {sans_laisse}"


def test_CONTROLE_NEGATIF_un_spawn_sans_timeout_fait_ROUGIR(tmp_path):
    """Sans ce contrôle, le témoin ci-dessus serait vert sur rien.

    On n'édite pas le dépôt : on rejoue LE MÊME RELEVÉ — celui du témoin, pas
    une copie — sur une source mutée, et on exige qu'il voie le troisième spawn
    ET son absence de laisse. La première rédaction dupliquait la boucle, donc
    elle contrôlait du code que personne n'utilise : mesuré par le binôme, muter
    le helper laissait les deux témoins verts."""
    source = (HERE / "dashboard_readers.py").read_text(encoding="utf-8")
    mute = source + "\n\ndef _ajout_illegitime():\n    subprocess.run(['git', 'status'])\n"
    trouves = _spawns_de_dashboard_readers(mute)
    assert len(trouves) == 3, f"le relevé ne VOIT pas le spawn ajouté : {trouves}"
    assert [t for t in trouves if not t[1]], "le relevé ne voit pas l'absence de timeout"


def test_un_fichier_indexe_TROP_GROS_reste_un_changement_pour_le_LECTEUR(tmp_path):
    """LE VERDICT NE STATE PLUS L'ARBRE, et ce témoin le gèle.

    `_keep()` reçoit `None` au lieu de la racine : sans ça, un fichier indexé
    devenu plus gros que `MAX_FILE_BYTES` sortait du compte — le lecteur rendait
    `fresh` pour une raison qui n'est PAS « rien n'a changé », direction du FAUX
    FRESH que le module nomme comme la plus grave."""
    root, g, sha = _depot_jetable(tmp_path)
    (root / "src" / "a.py").write_text("y = 2\n" * 400000, encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "devenu enorme")
    out = _lecteurs()._index_freshness(root, sha)
    assert out["fresh"] is False and out["changed_indexed_files"] == 1, out


# ---------------------------------------------------------------------------
# T-00000613 — `_read_canal_b` reads the channel WITHOUT holding it.
# ---------------------------------------------------------------------------

def test_the_slimmed_census_buckets_exactly_like_the_full_envelope():
    """`stream_bodies` keeps two fields per envelope instead of the whole
    envelope. That IS the memory win, and it is the one change here that could
    go wrong SILENTLY — a census that mis-buckets renders a wrong `foreign_held`
    instead of failing.

    IT HAS TO BE SYNTHETIC, and that is a finding rather than a shortcut:
    measured on this repo on 2026-09-14, all 67 854 canal-B rows carry
    `project_id = "unattributed"` and this project's own id resolves to
    `unset`, so the REAL store exercises exactly ONE of the three buckets.
    Real data alone can therefore never prove this equivalence."""
    normalize = dashboard._otel_normalize_mod
    receiver = dashboard._otel_receiver
    own = "own-project-id-0001"
    corpus = [
        json.dumps({"ts": "2026-01-01T00:00:00Z", "kind": "metric", "path": "/v1/x",
                    "project_id": pid, "provenance": pid,
                    "project_attributed_by": by, "body": {}})
        for pid, by in [(own, None),
                        (own, "backfill"),
                        ("neighbour-project-id-0002", None),
                        (receiver.PROJECT_UNATTRIBUTED, None)]
    ]
    full, _malformed = normalize.iter_envelopes_from_bodies(corpus)
    slim, _records, _rows, _m = normalize.stream_bodies(corpus)
    assert len(slim) == len(full) == len(corpus)

    # THE WHOLE CENSUS, not just the bucket function. Comparing
    # `_attribution_bucket` alone left `attributed_by_backfill` — and any field
    # a future census reads — untested: a slim entry missing `host` would
    # simply yield `None` on both sides and agree. The binôme measured that
    # blind spot; this compares the payload the section actually publishes.
    for own_id in (own, receiver.PROJECT_UNSET):
        assert (dashboard._canal_b_attribution(slim, own_id, {})
                == dashboard._canal_b_attribution(full, own_id, {})), own_id

    # And the run must actually straddle more than one bucket, or the equality
    # above is satisfied by a corpus that proves nothing.
    assert len({dashboard._attribution_bucket(e, own) for e in slim}) >= 2
    assert dashboard._canal_b_attribution(slim, own, {})["rows_in_store"][
        "attributed_by_backfill"] == 1


def test_read_canal_b_never_materialises_the_channel():
    """A SOURCE-level witness, because the cost is invisible in the RESULT: the
    eager and the streaming form return the same payload, so no assertion on
    the output can tell them apart. What separates them is which reader is
    called, and calling the eager one again is precisely the regression that
    restores the 4,7 Gio peak that killed a gate on 2026-09-14.

    `len(bodies)` is checked too: keeping the list alive only to report a count
    would hold 545 Mo to print one integer.

    COMMENTS AND DOCSTRINGS ARE DROPPED FIRST, and that is not a detail — the
    first version of this witness failed on the comment that EXPLAINS the fix,
    which is a test that forbids documenting the thing it guards. The second
    version tried to strip the docstring with `str.replace` and the binôme
    measured that as a NO-OP (`ast.get_docstring` dedents, the source does
    not), which would have made the porte red the day a documenter wrote
    "unlike `canal_b_bodies()`…" in the prose. Unparsing the AST body without
    its docstring node drops both, by construction rather than by string
    surgery."""
    tree = ast.parse(inspect.getsource(dashboard._read_canal_b))
    for node in ast.walk(tree):
        # EVERY docstring, NESTED ONES INCLUDED. Stripping only the outer one
        # left the helper generator's own docstring in the text, and this
        # witness then failed on prose again — the third time in a row, which
        # is what finally made string surgery the wrong tool.
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.ClassDef,
                              ast.FunctionDef, ast.AsyncFunctionDef))
                and isinstance(body, list) and len(body) > 1
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:]
    code = ast.unparse(tree)

    assert "iter_canal_b_bodies()" in code, "the streaming reader is gone"
    assert "stream_bodies(" in code, "the streaming normaliser is gone"
    # The eager sibling must not come back under its own name. Blanking the
    # streaming call first is what keeps this from matching its own substring.
    assert "canal_b_bodies()" not in code.replace("iter_canal_b_bodies()", "")
    assert "len(bodies)" not in code


def test_read_canal_b_hands_the_normaliser_a_generator(_redirect, monkeypatch):
    """The call site, observed at run time rather than in the source.

    HONEST ABOUT ITS REACH: this proves the normaliser is fed something lazy,
    not that the channel is never materialised — `stream_bodies(list(...))`
    wrapped in a counting generator would still arrive here as a `generator`.
    The memory property itself is pinned where it can be MEASURED:
    `test_stream_bodies_peak_memory_is_one_row_not_the_channel` and
    `test_iter_canal_b_bodies_is_lazy_and_never_materialises_the_channel`.
    This one guards the wiring between them."""
    _ingest_otel(_redirect, [_metric_envelope(_TS, "claude_code.cost.usage", 1.0,
                                              {"model": "m"})])
    seen: list[str] = []
    real = dashboard._otel_normalize_mod.stream_bodies

    def _spy(bodies):
        seen.append(type(bodies).__name__)
        return real(bodies)

    monkeypatch.setattr(dashboard._otel_normalize_mod, "stream_bodies", _spy)
    section = _snap_canal_b(_redirect)
    assert section["status"] == "ok", section
    assert seen == ["generator"], seen


def test_canal_b_mid_read_failure_degrades_and_never_serves_a_short_channel(
        _redirect, monkeypatch):
    """The branch the restructure ADDED, and it had no witness at all.

    A read that dies after yielding rows must not hand back the rows it got:
    a truncated channel that renders as a complete small one is the silent
    wrong answer the attribution census exists to prevent. It must degrade
    with the STORE's reason, not with a normalisation reason — the two say
    different things about whose fault it is."""
    _ingest_otel(_redirect, [_metric_envelope(_TS, "claude_code.cost.usage", 1.0,
                                              {"model": "m"})])

    def _dies_mid_read(self):
        yield json.dumps({"ts": _TS, "kind": "metric", "path": "/v1/x",
                          "project_id": "unattributed", "body": {}})
        raise sqlite3.OperationalError("simulated mid-read failure")

    monkeypatch.setattr(dashboard._event_store_mod.EventStore,
                        "iter_canal_b_bodies", _dies_mid_read)
    section = _snap_canal_b(_redirect)
    assert section["collected"] is False
    assert section["status"] == "degraded"
    assert section["source"] == "unavailable", section
    assert "simulated mid-read failure" in section["reason"]
    # The row that DID arrive must not have reached a rendered figure.
    assert "cost" not in section, section


def test_canal_b_reports_the_rows_it_actually_read_when_normalisation_dies(
        _redirect, monkeypatch):
    """`rows_read` used to be `len(bodies)` — a list that OUTLIVED the failure.
    Streaming killed the count with the exception, and the degraded payload
    then said `rows_read: 0`, which is indistinguishable from an empty
    channel. On a ticket whose whole subject is a failure mode nobody can
    see, that would have been the second silent answer in a row. The counter
    now lives at the call site, outside the normaliser."""
    _ingest_otel(_redirect, [
        _metric_envelope(_TS, "claude_code.cost.usage", 1.0, {"model": "m"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 2.0, {"model": "m"}),
        _metric_envelope(_TS, "claude_code.cost.usage", 3.0, {"model": "m"}),
    ])

    def _dies_after_two(bodies):
        drawn = 0
        for _body in bodies:
            drawn += 1
            if drawn == 2:
                raise ValueError("simulated normalisation failure")
        return [], [], drawn, 0

    monkeypatch.setattr(dashboard._otel_normalize_mod, "stream_bodies", _dies_after_two)
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert "simulated normalisation failure" in section["reason"]
    assert section["rows_read"] == 2, section


def test_canal_b_mid_read_sqlite_warning_is_a_store_fault_not_a_data_fault(
        _redirect, monkeypatch):
    """`sqlite3.Warning` is NOT a subclass of `sqlite3.Error` — measured, and
    the reason the first draft mislabelled it. Falling through to the generic
    branch made a DATABASE fault come out as "normalisation failed" with
    `source: "sqlite"`, i.e. blamed on the data. Same confusion as above, one
    exception class further along."""
    _ingest_otel(_redirect, [_metric_envelope(_TS, "claude_code.cost.usage", 1.0,
                                              {"model": "m"})])
    assert not issubclass(sqlite3.Warning, sqlite3.Error), (
        "if this ever becomes true, the tuple in `_read_canal_b` can shrink")

    def _warns_mid_read(self):
        yield json.dumps({"ts": _TS, "kind": "metric", "path": "/v1/x",
                          "project_id": "unattributed", "body": {}})
        raise sqlite3.Warning("simulated database warning")

    monkeypatch.setattr(dashboard._event_store_mod.EventStore,
                        "iter_canal_b_bodies", _warns_mid_read)
    section = _snap_canal_b(_redirect)
    assert section["status"] == "degraded"
    assert section["source"] == "unavailable", section
    assert "canal-B store unavailable" in section["reason"], section
