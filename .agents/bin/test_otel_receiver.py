"""Tests for otel_receiver.py — the standalone OTLP/JSON receiver
(T-00000025 shard 0). The plant-PII test is the point of this shard: it
must be green BEFORE the pilot ever relaunches a session with real
telemetry pointed at this module.

Style: explicit-path module load (matching this repo's test_events.py
convention). Every test that writes redirects via AGENTS_OTEL_DIR
(monkeypatch.setenv), never the real .agents/state/local/otel/.
"""
from __future__ import annotations

import errno
import hashlib
import http.client
import http.server
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent

# Generous ceiling (seconds) for loopback probes and request round-trips. A
# fixed short timeout (5 s / 0.25 s / 1.0 s) tripped under container load on a
# perfectly healthy server (T-00000176: TimeoutError on a socket op). It is a
# patience bound, not a measured threshold — a genuinely hung or unreachable
# server still fails at the deadline. The request helpers below WIDEN their
# timeout but do NOT retry: POST must stay exactly-once, or test_rate_cap_* and
# the `len(records) == 1` assertions would double-count. The two socket probes
# further down loop-and-retry within this ceiling instead.
_GENEROUS_TIMEOUT = 30.0


def _load_sibling_module(name: str, filename: str):
    """The explicit-path load this whole directory uses. Kept as a function so
    the T-00000084 end-to-end test can pull in `event_store.py` LAZILY — a
    sqlite-opening module has no business being imported by the 40 tests in
    this file that only need a socket."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


otel_receiver = _load_sibling_module("otel_receiver", "otel_receiver.py")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# The project identity every test in this file runs under. A uuid4 in
# production (`project_init.py:228`); a fixed literal here so an assertion can
# name it.
_OWN_ID = "own-project-id-0001"
_OTHER_ID = "neighbour-project-id-0002"


def _write_project_json(path: Path, project_id: str | None) -> None:
    """Write (or remove) the identity the receiver resolves. `None` removes it,
    which is the pre-`project_init` state — `resolve_own_project_id()` then
    returns `PROJECT_UNSET`."""
    if project_id is None:
        if path.exists():
            path.unlink()
        otel_receiver._reset_identity_cache_for_tests()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"project_id": project_id}), encoding="utf-8", newline="\n")
    otel_receiver._reset_identity_cache_for_tests()


@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    otel_dir = tmp_path / "otel"
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(otel_dir))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "fake-project"))
    # V1-c: attribution reads `.agents/state/project.json`, so it is redirected
    # exactly like every other state input — a test must never resolve this
    # developer's real project id.
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    # T-00000084: the router reads the MACHINE-WIDE registry. Redirected here
    # for every test in this file, autouse, and deliberately not per-test: an
    # un-redirected router would read this developer's real
    # `~/.agentkit/registry.json` and a foreign-id test would then APPEND into
    # a real neighbouring project's spool.
    monkeypatch.setenv("AGENTKIT_REGISTRY", str(tmp_path / "registry.json"))
    _write_project_json(tmp_path / "project.json", _OWN_ID)
    otel_receiver._reset_state_for_tests()
    yield otel_dir


@pytest.fixture
def server(_redirect):
    """A live HTTPServer bound to an ephemeral loopback port, running in a
    background thread — used for the true end-to-end (socket-level) tests.
    Never binds the real 4318 port."""
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


def _post(port: int, path: str, body: bytes, content_type: str = "application/json") -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=_GENEROUS_TIMEOUT)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": content_type})
        resp = conn.getresponse()
        resp_body = resp.read()
        resp.data = resp_body  # type: ignore[attr-defined]
        return resp
    finally:
        conn.close()


def _get(port: int, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=_GENEROUS_TIMEOUT)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        return resp
    finally:
        conn.close()


def _put(port: int, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=_GENEROUS_TIMEOUT)
    try:
        conn.request("PUT", path, body=b"{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        return resp
    finally:
        conn.close()


def _all_lines(otel_dir: Path) -> list[str]:
    out: list[str] = []
    for f in sorted(otel_dir.glob("*.jsonl")):
        text = f.read_bytes().decode("utf-8")
        assert "\r\n" not in text, f"CRLF leaked into {f.name}"
        out.extend(ln for ln in text.split("\n") if ln)
    return out


def _all_records(otel_dir: Path) -> list[dict]:
    return [json.loads(ln) for ln in _all_lines(otel_dir)]


def _attr(key: str, string_value: str) -> dict:
    return {"key": key, "value": {"stringValue": string_value}}


# ---------------------------------------------------------------------------
# THE plant-PII test — this shard's whole purpose.
# ---------------------------------------------------------------------------

def test_plant_pii_is_absent_from_persisted_file_and_response(server, _redirect):
    otel_dir = _redirect
    port = server

    planted = {
        "email": "real.person@example.com",
        "user_id": "uid-super-secret-12345",
        "org_id": "org-999-classified",
        "account_uuid": "uuid-abc-def-000",
        "prompt": "SYSTEM PROMPT: my api key is sk-live-should-never-leak",
    }

    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        _attr("user.email", planted["email"]),
                        _attr("user.id", planted["user_id"]),
                        _attr("organization.id", planted["org_id"]),
                        _attr("user.account_uuid", planted["account_uuid"]),
                        _attr("terminal.type", "vscode"),
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"attributes": [_attr("session.id", "sess-1")]},
                        "logRecords": [
                            {
                                "attributes": [
                                    _attr("gen_ai.prompt", planted["prompt"]),
                                    _attr("tool_name", "Bash"),
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }

    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    resp_text = resp.data.decode("utf-8")  # type: ignore[attr-defined]

    for value in planted.values():
        assert value not in resp_text, f"planted PII leaked into the HTTP response: {value!r}"

    records = _all_records(otel_dir)
    assert len(records) == 1
    raw_file_text = "\n".join(_all_lines(otel_dir))
    for value in planted.values():
        assert value not in raw_file_text, f"planted PII leaked into the persisted file: {value!r}"

    rec = records[0]
    resource_attrs = rec["body"]["resourceLogs"][0]["resource"]["attributes"]
    by_key = {a["key"]: a["value"] for a in resource_attrs}
    # Explicit regression guard for the spike's exact defect: user.id must be
    # redacted (the old REDACT_KEYS set omitted it).
    assert by_key["user.id"] == {"stringValue": "REDACTED"}
    assert by_key["user.email"] == {"stringValue": "REDACTED"}
    assert by_key["organization.id"] == {"stringValue": "REDACTED"}
    assert by_key["user.account_uuid"] == {"stringValue": "REDACTED"}
    # Non-PII attribute must survive untouched.
    assert by_key["terminal.type"] == {"stringValue": "vscode"}

    log_attrs = rec["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    log_by_key = {a["key"]: a["value"] for a in log_attrs}
    # L-00000052 fix 3: a content field (matched by the `prompt` substring)
    # is fingerprinted, not flattened to a plain marker — this keeps "did
    # the host send real content here" answerable without retaining it.
    prompt_value = log_by_key["gen_ai.prompt"]
    assert "agentkitFingerprint" in prompt_value
    expected_encoded = planted["prompt"].encode("utf-8")
    assert prompt_value["agentkitFingerprint"]["byteLength"] == len(expected_encoded)
    assert prompt_value["agentkitFingerprint"]["sha256"] == hashlib.sha256(expected_encoded).hexdigest()
    assert log_by_key["tool_name"] == {"stringValue": "Bash"}


# ---------------------------------------------------------------------------
# L-00000052 — the asymmetry fix, the join-key exemption, and the
# host-marker-preservation control. All new for T-00000025 shard 3.
# ---------------------------------------------------------------------------

def test_prompt_id_join_key_is_never_redacted(server, _redirect):
    """`prompt.id` matches the `prompt` substring like `gen_ai.prompt` above,
    but it is canal A's join key, not content — it must survive untouched,
    never fingerprinted, never flattened."""
    otel_dir = _redirect
    port = server
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": []},
                "scopeLogs": [
                    {
                        "scope": {},
                        "logRecords": [
                            {"attributes": [_attr("prompt.id", "turn-abc-123"), _attr("prompt", "real content")]}
                        ],
                    }
                ],
            }
        ]
    }
    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    log_attrs = rec["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    by_key = {a["key"]: a["value"] for a in log_attrs}
    assert by_key["prompt.id"] == {"stringValue": "turn-abc-123"}
    # The sibling `prompt` field (real content, same event) IS fingerprinted —
    # proves the exemption is join-key-specific, not a blanket "prompt*" pass.
    assert "agentkitFingerprint" in by_key["prompt"]


def test_length_and_count_suffixed_fields_survive_despite_content_substring(server, _redirect):
    """L-00000052's measured asymmetry: `prompt_length` (an int) was
    destroyed by the `prompt` substring match while `response_length`
    (no substring hit) survived. Fix: any `_length`/`_count`/`_size_bytes`
    suffixed key survives regardless of a content-substring hit —
    `tool_input_size_bytes` is the second real example GATE A captured."""
    otel_dir = _redirect
    port = server
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": []},
                "scopeLogs": [
                    {
                        "scope": {},
                        "logRecords": [
                            {
                                "attributes": [
                                    _attr("prompt_length", "42"),
                                    _attr("tool_input_size_bytes", "1024"),
                                    _attr("response_length", "7"),
                                    _attr("prompt", "actual content, must still be fingerprinted"),
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }
    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    log_attrs = rec["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    by_key = {a["key"]: a["value"] for a in log_attrs}
    assert by_key["prompt_length"] == {"stringValue": "42"}
    assert by_key["tool_input_size_bytes"] == {"stringValue": "1024"}
    assert by_key["response_length"] == {"stringValue": "7"}
    assert "agentkitFingerprint" in by_key["prompt"]


def test_host_own_redaction_marker_is_preserved_verbatim(server, _redirect):
    """L-00000052: `<REDACTED>` (with angle brackets) is the HOST's own
    marker. A content-drop-listed field that already carries it must be
    left byte-for-byte alone, not re-flattened into our own marker — doing
    so would destroy the one signal that lets a reader attribute a
    redaction to its author."""
    otel_dir = _redirect
    port = server
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": []},
                "scopeLogs": [
                    {
                        "scope": {},
                        "logRecords": [{"attributes": [_attr("tool_response", "<REDACTED>")]}],
                    }
                ],
            }
        ]
    }
    before = otel_receiver.get_diagnostics()["host_redaction_preserved"]
    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    log_attrs = rec["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]
    by_key = {a["key"]: a["value"] for a in log_attrs}
    assert by_key["tool_response"] == {"stringValue": "<REDACTED>"}
    assert otel_receiver.get_diagnostics()["host_redaction_preserved"] == before + 1


def test_email_shaped_value_redacted_regardless_of_key_name(server, _redirect):
    """L-00000043: audit the CONTENT, not just the key name."""
    otel_dir = _redirect
    port = server
    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [_attr("some.unlisted.field", "sneaky@leak.example")]
                },
                "scopeLogs": [],
            }
        ]
    }
    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    raw = "\n".join(_all_lines(otel_dir))
    assert "sneaky@leak.example" not in raw
    assert otel_receiver.get_diagnostics()["dropped_fields_by_content"] == 1


def test_long_attribute_value_is_capped_and_counted(server, _redirect):
    otel_dir = _redirect
    port = server
    long_value = "x" * 2000
    payload = {
        "resourceLogs": [
            {"resource": {"attributes": [_attr("some.field", long_value)]}, "scopeLogs": []}
        ]
    }
    resp = _post(port, "/v1/logs", json.dumps(payload).encode("utf-8"))
    assert resp.status == 200
    records = _all_records(otel_dir)
    written = records[0]["body"]["resourceLogs"][0]["resource"]["attributes"][0]["value"]["stringValue"]
    assert written != long_value
    assert written.endswith("...<truncated>")
    assert len(written) < len(long_value)
    assert otel_receiver.get_diagnostics()["truncated_fields"] == 1


# ---------------------------------------------------------------------------
# Malformed body -> bounded failure record, never raw body, counter bumped.
# ---------------------------------------------------------------------------

def test_malformed_body_persists_bounded_failure_never_raw_body(server, _redirect):
    otel_dir = _redirect
    port = server
    junk = b"this is not json { definitely not"

    resp = _post(port, "/v1/logs", junk)
    assert resp.status == 200  # accepted at the transport level; failure is internal

    records = _all_records(otel_dir)
    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "failure"
    failure = rec["failure"]
    assert failure["reason"] == "json_decode_error"
    assert failure["byte_length"] == len(junk)
    assert failure["content_type"] == "application/json"
    assert failure["sha256"] == hashlib.sha256(junk).hexdigest()

    raw = "\n".join(_all_lines(otel_dir))
    assert junk.decode("utf-8") not in raw
    assert "definitely not" not in raw

    assert otel_receiver.get_diagnostics()["parse_failures"] == 1


def test_non_object_json_is_also_a_bounded_failure(server, _redirect):
    otel_dir = _redirect
    port = server
    resp = _post(port, "/v1/logs", b'["just", "a", "list"]')
    assert resp.status == 200
    records = _all_records(otel_dir)
    assert records[0]["kind"] == "failure"
    assert records[0]["failure"]["reason"] == "not_a_json_object"


# ---------------------------------------------------------------------------
# Route separation (finding B3)
# ---------------------------------------------------------------------------

def test_root_path_post_is_404(server):
    resp = _post(server, "/", b"{}")
    assert resp.status == 404


def test_unrelated_path_post_is_404(server):
    resp = _post(server, "/api/snapshot", b"{}")
    assert resp.status == 404


def test_get_on_valid_path_is_404(server):
    resp = _get(server, "/v1/logs")
    assert resp.status == 404


def test_put_on_valid_path_is_404(server):
    resp = _put(server, "/v1/logs")
    assert resp.status == 404


def test_valid_routes_accept_post(server, _redirect):
    resp_logs = _post(server, "/v1/logs", b'{"resourceLogs": []}')
    resp_metrics = _post(server, "/v1/metrics", b'{"resourceMetrics": []}')
    assert resp_logs.status == 200
    assert resp_metrics.status == 200


# ---------------------------------------------------------------------------
# Content-type allowlist
# ---------------------------------------------------------------------------

def test_wrong_content_type_is_rejected_and_not_persisted(server, _redirect):
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", b"<xml/>", content_type="application/xml")
    assert resp.status == 415
    assert _all_lines(otel_dir) == []
    assert otel_receiver.get_diagnostics()["bad_content_type"] == 1


def test_content_type_with_charset_suffix_is_accepted(server, _redirect):
    resp = _post(server, "/v1/logs", b'{"resourceLogs": []}', content_type="application/json; charset=utf-8")
    assert resp.status == 200


# ---------------------------------------------------------------------------
# Body-size cap
# ---------------------------------------------------------------------------

def test_body_over_cap_is_rejected_counted_and_nothing_persisted(server, _redirect, monkeypatch):
    otel_dir = _redirect
    monkeypatch.setenv("AGENTS_OTEL_BODY_CAP", "100")
    oversized = json.dumps({"resourceLogs": [], "padding": "y" * 200}).encode("utf-8")
    assert len(oversized) > 100

    resp = _post(server, "/v1/logs", oversized)
    assert resp.status == 413
    assert _all_lines(otel_dir) == []
    assert otel_receiver.get_diagnostics()["body_too_large"] == 1


def test_body_under_cap_is_accepted(server, _redirect, monkeypatch):
    monkeypatch.setenv("AGENTS_OTEL_BODY_CAP", "100000")
    resp = _post(server, "/v1/logs", b'{"resourceLogs": []}')
    assert resp.status == 200


# ---------------------------------------------------------------------------
# Rate cap
# ---------------------------------------------------------------------------

def test_rate_cap_rejects_past_the_limit_and_counts(server, _redirect, monkeypatch):
    monkeypatch.setenv("AGENTS_OTEL_RATE_LIMIT_MAX", "3")
    monkeypatch.setenv("AGENTS_OTEL_RATE_LIMIT_WINDOW", "5")
    otel_receiver._reset_state_for_tests()

    statuses = [_post(server, "/v1/logs", b'{"resourceLogs": []}').status for _ in range(5)]
    assert statuses.count(200) == 3
    assert statuses.count(429) == 2
    assert otel_receiver.get_diagnostics()["rate_limited"] == 2


# ---------------------------------------------------------------------------
# Attribution (V1-c, T-00000050) — REWRITTEN CONTRACTS, not loosened ones.
#
# The three tests below replace the V1-b provenance trio. Each one now asserts a
# STRONGER fact than it did, because the operand changed meaning: the attribute
# carries a `project_id` (not an absolute path), and absence is answered with a
# POSITIVE SENTINEL (not with this machine's own root, which was both a lie
# about a neighbour's payload and a PII surface — L-00000031).
# ---------------------------------------------------------------------------

def _project_attrs(project_id: str) -> dict:
    return {"resourceLogs": [
        {"resource": {"attributes": [_attr("agentkit.project_id", project_id)]},
         "scopeLogs": []}
    ]}


def test_absent_attribute_is_persisted_with_the_positive_sentinel(server, _redirect):
    """WAS: absent -> stamp our own project ROOT (an absolute path).
    NOW: absent -> the literal sentinel, in BOTH `project_id` and `provenance`.

    This is the whole hinge of V1-c (plan-critic iteration 7, C1): with a
    positive sentinel, "this host declares nothing" is a VALUE, so the census
    is decidable on one field. With a path there, the display layer had to fall
    back on `provenance` — where an unreadable NEIGHBOURING payload landed in
    the LOCAL bucket."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", b'{"resourceLogs": []}')
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    assert rec["project_id"] == otel_receiver.PROJECT_UNATTRIBUTED == "unattributed"
    assert rec["provenance"] == "unattributed"
    # The regression this file must never re-accept: no absolute path anywhere
    # in a persisted envelope's attribution fields.
    assert os.environ["AGENTS_OTEL_PROJECT_ROOT"] not in json.dumps(rec)


def test_declared_foreign_project_id_never_lands_in_our_own_spool(server, _redirect):
    """WAS (V1-c): a declared PROJECT ID != our own id -> DROPPED,
    `dropped_foreign` += 1.
    NOW (T-00000084): never dropped. With no registry entry for it — the case
    here, the registry is empty — it is ORPHANED. What has not moved, and is
    the point of this test, is that it never lands in OUR spool: routing must
    not become the L-00000049 bleed by another route."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_OTHER_ID)).encode("utf-8"))
    assert resp.status == 200  # host still gets a normal 200
    assert _all_lines(otel_dir) == []
    diag = otel_receiver.get_diagnostics()
    assert diag["orphaned_records"] == 1
    assert diag["dropped_foreign"] == 0, "T-00000084 froze this counter at 0"


def test_declared_own_project_id_is_persisted_with_that_id(server, _redirect):
    """WAS: declared == own ROOT -> persisted with the declared path.
    NOW: declared == own ID -> persisted with that id, which is what makes the
    row `attributed` (by DECLARATION, the strongest evidence there is)."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_OWN_ID)).encode("utf-8"))
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    assert rec["project_id"] == _OWN_ID


def test_persist_always_writes_project_id_even_for_a_bare_envelope(_redirect):
    """The invariant lives at the single WRITE site, not in the callers: an
    envelope handed to `persist()` without the field comes back with the
    sentinel. That is what makes "no canal-B line written after V1-c can lack
    the field" a property of the code — the promise the store's five-bucket
    census is a TOTAL partition rests on."""
    otel_dir = _redirect
    envelope = {"ts": "2026-07-29T10:00:00Z", "kind": "metric", "path": "/v1/metrics"}
    otel_receiver.persist(envelope)
    assert "project_id" not in envelope, "persist() must not mutate its caller's dict"
    assert _all_records(otel_dir)[0]["project_id"] == "unattributed"


def test_parse_failure_is_sentinelled_and_carries_no_local_path(server, _redirect):
    """`_persist_failure` used to stamp `str(_project_root())` — an absolute
    home path, written into a field `cost.js` renders, for a payload we could
    not even parse. Two defects in one line: a neighbour's unreadable payload
    counted as LOCAL spend, and this machine's identity travelling
    (L-00000031, the shape `.agents/evals/test_template_hygiene.py`'s canary
    pins). Both are closed by the sentinel."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", b"{not json")
    assert resp.status == 200
    rec = _all_records(otel_dir)[0]
    assert rec["kind"] == "failure"
    assert rec["project_id"] == "unattributed"
    assert rec["provenance"] == "unattributed"
    assert os.environ["AGENTS_OTEL_PROJECT_ROOT"] not in json.dumps(rec)


def test_identity_is_reresolved_before_a_drop(server, tmp_path, _redirect):
    """The transition case, and the first user is the one it betrays
    (iteration 1, C1): a daemon started BEFORE `project_init.py` ran resolves
    `"unset"`. If that were frozen, the pilot who has just pasted the env block
    would watch every single event be dropped as foreign. A mismatch therefore
    RE-READS `project.json` before dropping anything."""
    otel_dir = _redirect
    _write_project_json(tmp_path / "project.json", None)
    assert otel_receiver.resolve_own_project_id() == otel_receiver.PROJECT_UNSET

    # project_init.py runs now — after the receiver already cached "unset".
    _write_project_json(tmp_path / "project.json", _OWN_ID)
    otel_receiver._identity_cache = (
        otel_receiver._project_json_fingerprint(tmp_path / "nonexistent"),
        otel_receiver.PROJECT_UNSET,
    )

    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_OWN_ID)).encode("utf-8"))
    assert resp.status == 200
    assert _all_records(otel_dir)[0]["project_id"] == _OWN_ID, (
        "the payload of a freshly-inited project must not be dropped as foreign")
    assert otel_receiver.get_diagnostics()["dropped_foreign"] == 0


def test_unset_identity_never_matches_and_never_becomes_a_receptacle(server, tmp_path,
                                                                    _redirect):
    """`PROJECT_UNSET` is not matchable, by either side (iteration 2, C1).

    An un-inited repo holding the machine-global port must not become a
    RECEPTACLE for its neighbours: were `"unset"` allowed to match, those rows
    would be persisted and then WHITENED into the local id by the open-time
    relabel, making the L-00000049 bleed permanent."""
    otel_dir = _redirect
    _write_project_json(tmp_path / "project.json", None)
    assert otel_receiver.identity_matches(_OTHER_ID, otel_receiver.PROJECT_UNSET) is False
    assert otel_receiver.identity_matches("unset", "unset") is False, (
        "two 'unset' identities are not one identity")

    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_OTHER_ID)).encode("utf-8"))
    assert resp.status == 200
    assert _all_lines(otel_dir) == []
    # T-00000084: the neighbour's line is kept (orphaned), but "not a
    # receptacle" is unchanged — an un-inited repo still absorbs nothing into
    # its OWN spool.
    assert otel_receiver.get_diagnostics()["orphaned_records"] == 1


# ---------------------------------------------------------------------------
# T-00000084 — the holder of 4318 ROUTES for the machine
#
# The N-1 projects that do not hold the port used to lose every event
# (`dropped_foreign`). These tests pin the three outcomes that replace the
# drop: routed to a PROVEN peer, orphaned, and — the one the plan-critic made
# blocking — NEVER written under a root that failed the proof.
# ---------------------------------------------------------------------------

_PEER_ID = "peer-project-id-0003"


def _peer_root(tmp_path, name: str, project_id: str | None, *, local: bool = True) -> Path:
    """A tmp tree shaped like a provisioned project. `project_id=None` writes
    no `project.json` at all, and `local=False` omits `.agents/state/local/` —
    the two ways a registry entry can name a path that is not (or is no longer)
    the project it claims."""
    root = tmp_path / name
    state = root / ".agents" / "state"
    state.mkdir(parents=True, exist_ok=True)
    if project_id is not None:
        (state / "project.json").write_text(
            json.dumps({"project_id": project_id}), encoding="utf-8", newline="\n")
    if local:
        (state / "local").mkdir(parents=True, exist_ok=True)
    return root


def _peer_spool(root: Path) -> Path:
    return root / ".agents" / "state" / "local" / "otel"


def _register(tmp_path, entries: dict[str, Path]) -> None:
    """Write the machine registry the way `dashboard_registry.register` would,
    then drop the router cache so the next event re-reads it."""
    projects = {
        project_id: {"project_id": project_id, "project_root": str(root),
                     "name": "Peer", "pid": os.getpid(), "port": 61000,
                     "started": "2026-08-01T00:00:00Z"}
        for project_id, root in entries.items()
    }
    (tmp_path / "registry.json").write_text(
        json.dumps({"version": 1, "projects": projects}), encoding="utf-8", newline="\n")
    otel_receiver._reset_router_cache()


def _orphan_records(otel_dir: Path) -> list[dict]:
    orphans = otel_dir / "orphans"
    if not orphans.is_dir():
        return []
    return _all_records(orphans)


def test_a_peers_event_is_routed_into_that_peers_own_spool(server, tmp_path, _redirect):
    """The whole task in one case: the holder of 4318 receives an event
    declaring ANOTHER provisioned project's id and appends it to THAT project's
    spool — where that project's own ingest will find it — instead of dropping
    it. Our own spool stays empty: routing is not a licence to mix stores."""
    otel_dir = _redirect
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})

    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert resp.status == 200

    routed = _all_records(_peer_spool(peer))
    assert len(routed) == 1
    assert routed[0]["project_id"] == _PEER_ID
    assert _all_lines(otel_dir) == [], "a routed event never touches our spool"
    assert _orphan_records(otel_dir) == []
    diag = otel_receiver.get_diagnostics()
    assert diag["routed_peer"] == 1
    assert diag["orphaned_records"] == 0
    assert diag["dropped_foreign"] == 0


def test_a_routed_file_is_named_with_OUR_pid_not_the_peers(server, tmp_path, _redirect):
    """L-00000041 is one file per WRITER PROCESS — `os.open(O_APPEND)` is not
    atomic across processes on Windows (10-22% line loss measured). We are the
    writer, so the pid in the name is OURS even though the store is the peer's.
    The peer's ingest globs `*.jsonl` and never parses that pid, so nothing on
    its side needs to know."""
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    names = [p.name for p in _peer_spool(peer).glob("*.jsonl")]
    assert len(names) == 1
    assert names[0].endswith(f".{os.getpid()}.jsonl"), names


def test_an_id_unknown_to_the_registry_is_orphaned_never_dropped(server, _redirect):
    """L-00000110 — we declare what we omit. An id no daemon has registered
    (a project whose dashboard never ran, a stale env block) is kept, with its
    DECLARED id intact, in a store an operator can read — and counted."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_OTHER_ID)).encode("utf-8"))
    assert resp.status == 200
    orphans = _orphan_records(otel_dir)
    assert len(orphans) == 1
    assert orphans[0]["project_id"] == _OTHER_ID, "an orphan keeps what it declared"
    diag = otel_receiver.get_diagnostics()
    assert diag["orphaned_records"] == 1
    assert diag["dropped_foreign"] == 0


def test_orphans_live_in_a_subdirectory_the_local_ingest_never_globs(server, _redirect):
    """`event_store._source_files` globs `*.jsonl` and `exports/*/*.jsonl`.
    `orphans/` is neither, which is the ONLY thing keeping a neighbour's
    unroutable event out of this project's database."""
    otel_dir = _redirect
    _post(server, "/v1/logs", json.dumps(_project_attrs(_OTHER_ID)).encode("utf-8"))
    assert sorted(otel_dir.glob("*.jsonl")) == []
    assert sorted(otel_dir.glob("exports/*/*.jsonl")) == []
    assert len(sorted((otel_dir / "orphans").glob("*.jsonl"))) == 1


def test_a_registered_root_that_vanished_orphans_without_raising(server, tmp_path,
                                                                 _redirect):
    """The registry is a claim written by another process and is allowed to be
    stale: the peer's clone was deleted or moved after it registered. The event
    must land in `orphans/`, and the HTTP caller must still get its 200 — an
    exception here would be a 500 on a host's telemetry export."""
    otel_dir = _redirect
    gone = tmp_path / "deleted-peer"
    _register(tmp_path, {_PEER_ID: gone})
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert resp.status == 200
    assert not gone.exists(), "nothing may be created under a root that is gone"
    assert len(_orphan_records(otel_dir)) == 1
    assert otel_receiver.get_diagnostics()["routed_peer"] == 0


@pytest.mark.parametrize("flaw", ["no_project_json", "divergent_id", "no_local_dir"])
def test_a_root_that_fails_the_proof_receives_ZERO_bytes(server, tmp_path, _redirect, flaw):
    """THE BLOCKING FINDING (plan-critic iteration 2). A registry entry names a
    path; writing there on that claim alone is writing outside this project on
    a stranger's say-so. Each flaw below is a way the claim can be false —
    never provisioned, re-pointed at someone else's tree, or wiped — and the
    verdict is identical in all three: orphan, and NOT ONE BYTE under the root,
    not even a created directory."""
    otel_dir = _redirect
    root = _peer_root(
        tmp_path, "trap",
        None if flaw == "no_project_json" else (
            "some-other-project-id" if flaw == "divergent_id" else _PEER_ID),
        local=(flaw != "no_local_dir"),
    )
    _register(tmp_path, {_PEER_ID: root})
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))

    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert resp.status == 200

    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert after == before, f"the router wrote under an unproven root: {set(after) - set(before)}"
    assert not _peer_spool(root).exists()
    assert len(_orphan_records(otel_dir)) == 1
    assert otel_receiver.get_diagnostics()["routed_peer"] == 0


def test_the_proof_is_re_run_at_every_ttl_refresh_not_stamped_once(server, tmp_path,
                                                                   _redirect):
    """A root proven at 10:00 is not proven for ever (concern iteration 2): a
    project can be re-inited, restored from a backup, or re-pointed under the
    same path. So the proof is bound to the CACHE ENTRY and re-run whenever
    that entry expires.

    The entry is AGED rather than the TTL shrunk (the first thing this test
    tried, and it passed for the wrong reason): `_ROUTER_TTL_SECONDS` is read
    when an entry is WRITTEN, so lowering it afterwards leaves the already
    proven entry valid for its original 5 s and the assertion below measured
    nothing. Rewriting the expiry into the past is exactly what a 5 s-old entry
    looks like, without sleeping for one."""
    otel_dir = _redirect
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert otel_receiver.get_diagnostics()["routed_peer"] == 1

    # The root is re-pointed at another project, WITHOUT touching the registry.
    (peer / ".agents" / "state" / "project.json").write_text(
        json.dumps({"project_id": "someone-else-entirely"}), encoding="utf-8", newline="\n")
    with otel_receiver._router_lock:
        _expiry, proven = otel_receiver._router_cache[_PEER_ID]
        otel_receiver._router_cache[_PEER_ID] = (time.monotonic() - 1.0, proven)

    _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert len(_all_records(_peer_spool(peer))) == 1, (
        "the second event must NOT have been written to a root that no longer proves itself")
    assert len(_orphan_records(otel_dir)) == 1
    diag = otel_receiver.get_diagnostics()
    assert (diag["routed_peer"], diag["orphaned_records"]) == (1, 1)


def test_the_file_catchup_path_routes_by_the_same_decision(tmp_path, _redirect):
    """`otel_normalize.py`'s Gemini file catch-up calls `_ingest_parsed_body`
    directly (that module, l.608) — the SAME single decision point as the
    socket. A foreign line found in a catch-up file is therefore routed too,
    which is deliberate: one point of decision beats two policies that drift.
    `attributed_by_construction=True` is what that caller passes, and it must
    NOT override an explicit foreign declaration."""
    otel_dir = _redirect
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})

    otel_receiver._ingest_parsed_body(
        "gemini_file", str(tmp_path / "gemini.json"), _project_attrs(_PEER_ID),
        attributed_by_construction=True)

    routed = _all_records(_peer_spool(peer))
    assert len(routed) == 1
    assert routed[0]["project_id"] == _PEER_ID
    assert routed[0]["kind"] == "gemini_file"
    assert _all_lines(otel_dir) == []
    assert otel_receiver.get_diagnostics()["routed_peer"] == 1


def test_a_routed_event_is_redacted_exactly_like_a_local_one(server, tmp_path, _redirect):
    """Writing into a peer's store is not a reason to relax the ONE control
    this module has (L-00000040). The redaction happens before the routing
    decision's write, at the single envelope-building site."""
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    body = {"resourceLogs": [{"resource": {"attributes": [
        _attr("agentkit.project_id", _PEER_ID),
        _attr("user.email", "plant@example.com"),
        _attr("gen_ai.prompt.0.content", "secret plant"),
    ]}, "scopeLogs": []}]}
    _post(server, "/v1/logs", json.dumps(body).encode("utf-8"))
    text = json.dumps(_all_records(_peer_spool(peer)))
    assert "plant@example.com" not in text
    assert "secret plant" not in text
    assert "REDACTED" in text


def test_the_doorbell_never_rings_for_another_projects_spool(server, tmp_path, _redirect):
    """The doorbell means "OUR spool grew, tick early" to OUR ingest loop.
    Ringing it with a path inside another project's tree would make this
    project's store scan — and, once consumed, DELETE — files that are not
    its own."""
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    rung: list = []
    otel_receiver.set_dirty_notifier(rung.append)
    try:
        _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
        assert rung == [], "a routed write must not ring our own ingest doorbell"
        _post(server, "/v1/logs", json.dumps(_project_attrs(_OWN_ID)).encode("utf-8"))
        assert len(rung) == 1, "a local write still rings it"
    finally:
        otel_receiver.set_dirty_notifier(None)


def test_an_unknown_id_costs_one_registry_read_per_ttl_not_one_per_event(server, tmp_path,
                                                                        _redirect):
    """The bound the identity cache already has, applied to the registry: a
    flood of foreign payloads must not become a flood of file reads. Both the
    positive and the NEGATIVE answer are cached, which is what makes an
    unknown id cheap."""
    reads = []
    registry_mod = otel_receiver._load_registry_module()
    real_read = registry_mod.read_registry

    def counting_read():
        reads.append(1)
        return real_read()

    registry_mod.read_registry = counting_read
    try:
        for _ in range(5):
            _post(server, "/v1/logs", json.dumps(_project_attrs(_OTHER_ID)).encode("utf-8"))
    finally:
        registry_mod.read_registry = real_read
    assert len(reads) == 1, f"5 events, {len(reads)} registry reads"
    assert otel_receiver.get_diagnostics()["orphaned_records"] == 5


def test_the_router_cache_cannot_grow_without_bound(server, _redirect):
    """A sender looping over invented ids (a mis-set `OTEL_RESOURCE_ATTRIBUTES`
    with a per-session uuid) must not turn a 5 s optimisation into a leak."""
    for i in range(otel_receiver._ROUTER_CACHE_MAX + 20):
        otel_receiver._peer_spool_for(f"invented-{i}")
    assert len(otel_receiver._router_cache) <= otel_receiver._ROUTER_CACHE_MAX


def test_a_peer_spool_deleted_between_the_proof_and_the_write_orphans(tmp_path, _redirect):
    """The race the proof cannot close, because no proof can: the destination
    was valid microseconds ago. The write fails, the line is KEPT as an orphan,
    and the entry is invalidated so the next event re-proves rather than
    re-failing."""
    otel_dir = _redirect
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    target = otel_receiver._peer_spool_for(_PEER_ID)
    assert target is not None

    # `local/` and everything under it disappear AFTER the proof.
    import shutil
    shutil.rmtree(peer / ".agents" / "state" / "local")

    otel_receiver._ingest_parsed_body("log", "/v1/logs", _project_attrs(_PEER_ID))
    assert len(_orphan_records(otel_dir)) == 1
    assert not _peer_spool(peer).exists(), (
        "a failed routed write must not re-create the tree it just failed to write to")
    assert _PEER_ID not in otel_receiver._router_cache


@pytest.mark.parametrize("evil_id", ["../../evil", "..\\..\\evil", "/etc/evil",
                                     "C:\\Windows\\evil"])
def test_a_wire_supplied_project_id_never_reaches_a_FILE_PATH(server, tmp_path,
                                                              _redirect, evil_id):
    """SECURITY NON-REGRESSION (security gate, advisory LOW). `project_id`
    arrives from the WIRE — a resource attribute on a token-exempt loopback
    route, i.e. attacker-controllable free text — and T-00000084 is the first
    task where a foreign one influences WHERE we write. It must never be a path
    component, in either spelling of the separator.

    It is not, BY CONSTRUCTION, and this test pins the construction: the
    declared id is only ever (a) a lookup KEY in the registry dict and in the
    router cache, and (b) a VALUE inside the JSON line. Every path segment comes
    from elsewhere — the destination from the registry's own `project_root`
    (itself proven), the file name from `strftime` + our pid. A traversal id is
    therefore just an id nobody registered: orphan, 200, no exception, and not
    one byte outside the two directories this module owns."""
    otel_dir = _redirect
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(evil_id)).encode("utf-8"))
    assert resp.status == 200

    orphans = _orphan_records(otel_dir)
    assert len(orphans) == 1
    assert orphans[0]["project_id"] == evil_id, (
        "the declared id is DATA in the line, kept verbatim — never a path")

    written = sorted((otel_dir / "orphans").glob("*.jsonl"))
    assert len(written) == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+\.jsonl", written[0].name), written[0].name
    assert str(os.getpid()) in written[0].name

    # NOTHING outside the redirected otel dir — this catches an escape upward
    # (`../../evil`) as well as one into a sibling of the spool.
    strays = [p for p in tmp_path.rglob("*")
              if p.is_file() and otel_dir not in p.parents and p.name != "project.json"]
    assert strays == [], f"the router wrote outside its own tree: {strays}"
    assert not any("evil" in p.name for p in tmp_path.rglob("*")), (
        "no path segment may come from the wire")
    assert otel_receiver.get_diagnostics()["orphaned_records"] == 1


def test_a_missing_registry_module_degrades_to_orphans(server, tmp_path, _redirect,
                                                       monkeypatch):
    """Fail-open, like every other degradation in this module: if the registry
    module cannot be loaded at all (a stripped install), routing stops and
    every foreign event becomes an orphan — never an exception on a host's
    export."""
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    monkeypatch.setattr(otel_receiver, "_load_registry_module", lambda: None)
    resp = _post(server, "/v1/logs", json.dumps(_project_attrs(_PEER_ID)).encode("utf-8"))
    assert resp.status == 200
    assert len(_orphan_records(_redirect)) == 1
    assert not _peer_spool(peer).exists()


def test_a_routed_day_file_is_ingested_and_deleted_by_the_PEERS_own_store(tmp_path,
                                                                         _redirect,
                                                                         monkeypatch):
    """END TO END, the claim that makes this task worth anything: a file this
    process wrote into ANOTHER project's spool is picked up by THAT project's
    ingest — one tick, no coordination — and then deleted under the store's own
    re-stat guard. The lag is one tick, and it is the peer's tick.

    The store is driven on the REAL clock on purpose: the routed file's name
    carries `datetime.now()`'s day (nothing injects a clock into a live
    receiver), and a frozen clock would make that day look like a PAST one and
    fold it (the T-00000063 time bomb, twice landed in this repo)."""
    event_store = _load_sibling_module("event_store_for_router", "event_store.py")
    peer = _peer_root(tmp_path, "peer", _PEER_ID)
    _register(tmp_path, {_PEER_ID: peer})
    otel_receiver._ingest_parsed_body("metric", "/v1/metrics", _project_attrs(_PEER_ID))
    written = sorted(_peer_spool(peer).glob("*.jsonl"))
    assert len(written) == 1

    # Now BE the peer: its store, its identity, its spool.
    peer_state = peer / ".agents" / "state"
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(_peer_spool(peer)))
    monkeypatch.setenv("AGENTS_EVENTS_DIR", str(peer_state / "events"))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(peer_state / "project.json"))
    monkeypatch.setenv("AGENTS_EVENTS_DB", str(peer_state / "local" / "events.db"))
    (peer_state / "events").mkdir(parents=True, exist_ok=True)

    store = event_store.open_store(create=True)
    try:
        assert store.status == "ok", store.reason

        # LA PRÉCONDITION SE POSE, ELLE NE S'ESPÈRE PAS. La première ingestion ne
        # doit PAS supprimer le fichier : c'est la seconde, après vieillissement,
        # qui prouve la suppression. Or la suppression n'est sautée que tant que
        # `now - st_mtime < _QUIESCENCE_SECONDS` (2 s, `event_store.py:173,965`),
        # et rien ne garantit que moins de 2 s séparent l'écriture ci-dessus de
        # cette ligne — sur un runner lent, créer le dépôt pair puis le store
        # SQLite prend davantage. Le fichier était alors déjà quiescent, supprimé
        # DÈS la première ingestion, et le test tombait plus bas sur un
        # `FileNotFoundError` qui ne dit rien de la propriété testée (mesuré sur
        # windows-latest, run 33787995440 — vert sur les deux autres jambes, donc
        # invisible hors de la plus lente).
        os.utime(written[0], None)          # mtime = maintenant : DANS la fenêtre
        report = store.ingest_once()
        assert report["rows_inserted"] == 1, report
        assert written[0].exists(), (
            "une ingestion ne supprime pas un fichier encore dans la fenêtre de "
            "quiescence — sans quoi l'arm de suppression ci-dessous ne mesure rien")
        rows = store._conn.execute(
            "SELECT project FROM events WHERE channel = 'b'").fetchall()
        assert [r[0] for r in rows] == [_PEER_ID], (
            "the peer's store must attribute the routed line to ITSELF, not quarantine it")

        # Quiescence (2 s) without sleeping, on the same clock the store reads.
        stamp = time.time() - 30
        os.utime(written[0], (stamp, stamp))
        store.ingest_once()
        assert not written[0].exists(), (
            "the peer deletes a fully-consumed routed file like any other")
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Port-holder probe (V1-c, spec §A.4) — who has 4318?
# ---------------------------------------------------------------------------

def test_probe_classifies_a_kit_peer_by_server_header_prefix(server):
    """A peer is recognised on the `Server` header of the 404 the handler
    ALREADY sends — no new route on a token-exempt port. Matched by PREFIX so
    a future `agentkit-otel-receiver/2` is still a peer and not a stranger
    (iteration 1, C7)."""
    result = otel_receiver.probe_port_holder(port=server)
    assert result["holder"] == "kit_peer"
    assert result["server"].startswith("agentkit-otel-receiver/")
    assert result["status"] == 404, "the probe rides the existing 404, not a new route"


def test_probe_classifies_a_foreign_holder(_redirect):
    class _Foreign(http.server.BaseHTTPRequestHandler):
        server_version = "SomeOtherCollector/9"
        sys_version = ""

        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Foreign)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        result = otel_receiver.probe_port_holder(port=httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    assert result["holder"] == "foreign"
    assert result["server"].startswith("SomeOtherCollector/9")


def test_probe_reports_unreachable_when_nobody_answers(_redirect):
    """`unreachable` is a THIRD answer, not a flavour of failure: the caller
    re-tries the bind instead of recording a permanent verdict (iteration 1,
    C6). Never an exception."""
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_sock.bind(("127.0.0.1", 0))
    port = probe_sock.getsockname()[1]
    probe_sock.close()
    result = otel_receiver.probe_port_holder(port=port, timeout=0.5)
    assert result["holder"] == "unreachable"
    assert result["reason"]


# ---------------------------------------------------------------------------
# Bind-conflict path (finding B2) — fail open, visible marker, no crash.
# ---------------------------------------------------------------------------

def test_bind_conflict_returns_degraded_marker_no_crash(_redirect):
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    try:
        result = otel_receiver.serve(host="127.0.0.1", port=port)
        assert result["status"] == "degraded"
        assert "reason" in result
    finally:
        occupied.close()


def test_two_real_serves_on_one_port_second_is_degraded(_redirect):
    """The regression the test above CANNOT catch, and why it exists separately.

    `test_bind_conflict_returns_degraded_marker_no_crash` occupies the port with a
    plain socket that does NOT set SO_REUSEADDR. On Windows a second bind is only
    permitted when the FIRST holder set SO_REUSEADDR too — so that fixture is the
    one configuration in which the conflict is always refused, and it passed both
    before and after the real defect was fixed. Production has the opposite shape:
    the first holder is our own receiver.

    `http.server.HTTPServer` defaults to `allow_reuse_address = True`, so before
    `_ExclusiveHTTPServer` a second receiver bound the SAME port successfully and
    silently — observed live on 4318, two listeners, neither reporting a conflict,
    one host's telemetry split non-deterministically between them and the degraded
    marker unreachable. This test drives two REAL `serve()` calls, which is the
    only shape that reproduces it.
    """
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_sock.bind(("127.0.0.1", 0))
    port = probe_sock.getsockname()[1]
    probe_sock.close()   # released WITHOUT SO_REUSEADDR, so serve() binds it clean
    started = threading.Event()
    outcome: dict[str, object] = {}

    def _first() -> None:
        started.set()
        outcome["first"] = otel_receiver.serve(host="127.0.0.1", port=port)

    t = threading.Thread(target=_first, daemon=True)
    t.start()
    started.wait(timeout=5)
    # serve() blocks in serve_forever once bound; poll until the port answers,
    # under a generous deadline so a slow cold start in a loaded container is
    # retried, not declared unreachable (T-00000176).
    deadline = time.time() + _GENEROUS_TIMEOUT
    while time.time() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.settimeout(5.0)
            probe.connect(("127.0.0.1", port))
            break
        except OSError:
            time.sleep(0.05)
        finally:
            probe.close()
    else:
        pytest.fail("first serve() never became reachable — cannot test the conflict")

    # Bounded on purpose. Under a regression the second serve() BINDS and enters
    # serve_forever(), which never returns — so calling it directly would HANG the
    # suite instead of failing it. Verified by re-enabling the defect at runtime:
    # "OTEL RECEIVER LISTENING …:65472" printed twice and the probe never came back.
    # A hanging test is not a regression signal, it is a broken CI, so the timeout
    # is the assertion: not having returned IS the failure.
    conflict: dict[str, object] = {}
    t2 = threading.Thread(
        target=lambda: conflict.update(
            result=otel_receiver.serve(host="127.0.0.1", port=port)
        ),
        daemon=True,
    )
    t2.start()
    t2.join(timeout=10)
    assert "result" in conflict, (
        "the second serve() never returned — it bound the same port and entered "
        "serve_forever(), i.e. allow_reuse_address regressed to True and the "
        "degraded path is unreachable again (two live listeners, telemetry split)"
    )
    second = conflict["result"]
    assert isinstance(second, dict) and second["status"] == "degraded", (
        f"a second serve() did not degrade on a taken port: {second}"
    )
    assert "reason" in second


# ---------------------------------------------------------------------------
# Bind exclusivity is PER-PLATFORM (T-00000055). Windows and POSIX need
# OPPOSITE settings of SO_REUSEADDR to hold the SAME invariant, so each branch
# is asserted where it is a measured fact — never loosened to "passes anywhere".
# ---------------------------------------------------------------------------

def _free_loopback_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()          # released WITHOUT SO_REUSEADDR, so a bind gets it clean
    return port


def test_reuseaddr_is_set_per_platform_not_globally():
    """The configuration itself, both branches, so a "simplifying" revert to a
    single value fails here with the reason attached rather than as a puzzling
    EADDRINUSE in a 15 s daemon test on one OS only."""
    cls = otel_receiver._ExclusiveHTTPServer
    if os.name == "nt":
        assert cls.allow_reuse_address is False, (
            "Windows: SO_REUSEADDR permits a SECOND LIVE bind on the same "
            "address:port (L-00000050), which makes the degraded path "
            "unreachable and splits telemetry between two receivers"
        )
    else:
        assert cls.allow_reuse_address is True, (
            "POSIX: SO_REUSEADDR concedes no live listener (that needs "
            "SO_REUSEPORT) and is REQUIRED to re-bind over the TIME_WAIT left "
            "by a dead peer's connections — without it V1-c's port reclaim is "
            "dead for a full TIME_WAIT window (T-00000055)"
        )
    assert cls.allow_reuse_port is False, (
        "SO_REUSEPORT is the option that WOULD hand a live POSIX listener to a "
        "challenger — it must never be inherited on"
    )


@pytest.mark.skipif(os.name == "nt", reason="measures a POSIX kernel fact: "
                    "SO_REUSEADDR does not yield a live listener. On Windows it "
                    "DOES, which is why the flag is off there (L-00000050) and "
                    "why the Windows counterpart is "
                    "test_two_real_serves_on_one_port_second_is_degraded.")
def test_posix_exclusivity_holds_even_with_so_reuseaddr_enabled(_redirect):
    """The guarantee T-00000055 must NOT have traded away.

    Enabling SO_REUSEADDR on POSIX is only admissible if a second bind on a port
    we are already LISTENING on still fails. Measured across all four
    holder/challenger combinations in the CI ubuntu image: EADDRINUSE every
    time. Asserted here with the PRODUCTION class on both sides — the one
    configuration that actually ships — and with the option's presence verified
    on the live socket, so the test cannot pass vacuously by the flag having
    silently reverted to off.
    """
    port = _free_loopback_port()
    holder = otel_receiver._ExclusiveHTTPServer(("127.0.0.1", port), otel_receiver.OTLPHandler)
    try:
        assert holder.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) != 0, (
            "fixture invalid: the holder has no SO_REUSEADDR, so this would be "
            "the easy case instead of the one under test"
        )
        reuseport = getattr(socket, "SO_REUSEPORT", None)
        if reuseport is not None:
            assert holder.socket.getsockopt(socket.SOL_SOCKET, reuseport) == 0, (
                "SO_REUSEPORT on the holder WOULD let a challenger share the port"
            )
        with pytest.raises(OSError) as caught:
            otel_receiver._ExclusiveHTTPServer(("127.0.0.1", port), otel_receiver.OTLPHandler)
        assert caught.value.errno == errno.EADDRINUSE, (
            f"expected EADDRINUSE on a live listener, got {caught.value!r}"
        )
    finally:
        holder.server_close()


@pytest.mark.skipif(os.name == "nt", reason="TIME_WAIT does not block a re-bind "
                    "on Windows (measured: the re-bind succeeds with or without "
                    "SO_REUSEADDR), so there is nothing to regress there.")
def test_posix_rebinds_immediately_over_a_dead_peers_time_wait(_redirect):
    """The regression that broke `--linux` (T-00000055), at socket level.

    V1-c's flow leaves TIME_WAIT on OUR port before the re-bind is attempted:
    the daemon probes the holder with a GET, `OTLPHandler` 404s it and CLOSES
    the connection, so the PEER's accepted socket lingers in TIME_WAIT bound to
    that port. When the peer then dies the probe correctly says
    ECONNREFUSED — but on POSIX the bind stays EADDRINUSE for ~60 s unless both
    sides carry SO_REUSEADDR. This is the same shape as
    CivilisedPortTests.test_a_dead_peer_is_reclaimed_at_the_poll_and_the_lock_is_rewritten,
    without that test's 15 s poll window, so a re-break is diagnosed here first.
    """
    port = _free_loopback_port()
    peer = otel_receiver._ExclusiveHTTPServer(("127.0.0.1", port), otel_receiver.OTLPHandler)
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 404, "the probe's shape is a GET the handler rejects"
        conn.close()
    finally:
        peer.shutdown()
        peer.server_close()          # the peer dies, TIME_WAIT survives it
        thread.join(timeout=5)

    # Nobody should be listening any more — exactly what the daemon's probe
    # observes. This loop's sense is INVERTED versus the positive probe above:
    # it is still being reachable AT THE DEADLINE that IS the failure, so a
    # naive "break on success" would be vacuous. A dead peer whose socket
    # lingered a moment under load is retried away; a port that never frees
    # fails (T-00000176).
    deadline = time.time() + _GENEROUS_TIMEOUT
    while time.time() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.settimeout(5.0)
            probe.connect(("127.0.0.1", port))
        except OSError:
            break  # refused — the port is free, exactly what the daemon needs
        finally:
            probe.close()
        time.sleep(0.05)
    else:
        pytest.fail(
            "the port stayed reachable after the peer died — its listening "
            "socket never went away, so the daemon's vacancy probe would never "
            "see the port free to reclaim"
        )

    try:
        reclaimed = otel_receiver._ExclusiveHTTPServer(("127.0.0.1", port), otel_receiver.OTLPHandler)
    except OSError as exc:
        pytest.fail(
            f"the port was not reclaimable after the peer died ({exc}) — a dead "
            f"peer's TIME_WAIT still blocks the re-bind, i.e. allow_reuse_address "
            f"regressed to False on POSIX and canal B stays dark for a full "
            f"TIME_WAIT window (T-00000055)"
        )
    reclaimed.server_close()


# ---------------------------------------------------------------------------
# Two-process concurrent append — zero line loss (L-00000041, the reason
# filenames carry the pid).
# ---------------------------------------------------------------------------

_WORKER_TEMPLATE = textwrap.dedent(
    """
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("otel_receiver", r"{module_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for i in range({n_events}):
        mod.persist({{
            "ts": "2026-01-01T00:00:00Z",
            "kind": "log",
            "path": "/v1/logs",
            "provenance": "p",
            "body": {{"i": i}},
        }})
    """
)

N_WORKERS = 2
N_EVENTS_PER_WORKER = 150


def test_two_process_concurrent_append_zero_line_loss(_redirect):
    otel_dir = _redirect
    module_path = str(HERE / "otel_receiver.py")
    code = _WORKER_TEMPLATE.format(module_path=module_path, n_events=N_EVENTS_PER_WORKER)

    env = dict(os.environ)
    env["AGENTS_OTEL_DIR"] = str(otel_dir)

    procs = []
    for _ in range(N_WORKERS):
        p = subprocess.Popen(
            [sys.executable, "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True,
        )
        p.stdin.write(code)
        p.stdin.close()
        procs.append(p)

    for p in procs:
        rc = p.wait(timeout=60)
        err = p.stderr.read()
        assert rc == 0, f"worker failed rc={rc} stderr={err}"

    files = sorted(otel_dir.glob("*.jsonl"))
    assert len(files) == N_WORKERS, f"expected one file per writer, got {len(files)}: {files}"

    total_lines = 0
    seen_pids = set()
    for f in files:
        text = f.read_bytes().decode("utf-8")
        assert "\r\n" not in text
        lines = [ln for ln in text.split("\n") if ln]
        assert len(lines) == N_EVENTS_PER_WORKER, (
            f"{f.name}: expected {N_EVENTS_PER_WORKER} lines, got {len(lines)} — "
            "a per-writer file should never lose a line"
        )
        for ln in lines:
            json.loads(ln)  # every surviving line must parse
        total_lines += len(lines)
        parts = f.name.split(".")  # YYYY-MM-DD.<pid>.jsonl
        assert parts[-1] == "jsonl"
        seen_pids.add(parts[-2])

    assert total_lines == N_WORKERS * N_EVENTS_PER_WORKER
    assert len(seen_pids) == N_WORKERS


# ---------------------------------------------------------------------------
# redact() unit-level coverage (no server needed)
# ---------------------------------------------------------------------------

def test_redact_walks_nested_shapes_generically():
    body = {
        "resourceMetrics": [
            {
                "resource": {"attributes": [_attr("user.email", "a@example.com")]},
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "sum": {
                                    "dataPoints": [
                                        {"attributes": [_attr("user.id", "u1")]}
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }
    redacted = otel_receiver.redact(body)
    dp_attrs = redacted["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["sum"]["dataPoints"][0]["attributes"]
    assert dp_attrs[0]["value"] == {"stringValue": "REDACTED"}
    res_attrs = redacted["resourceMetrics"][0]["resource"]["attributes"]
    assert res_attrs[0]["value"] == {"stringValue": "REDACTED"}


def test_redact_non_dict_leaf_passthrough():
    assert otel_receiver.redact(42) == 42
    assert otel_receiver.redact("plain string") == "plain string"
    assert otel_receiver.redact(None) is None
