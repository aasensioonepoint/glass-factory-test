"""Access handoff between dashboards — `dashboard_handoff.py` and its three routes
(T-01M4XKCTGEW9MDAYNCBK6R7SD9, plan M1-M15).

Fixtures are IMPORTED from `test_dashboard.py` (`_redirect`, `_drain_streams`
autouse; `ui_server`, `ui_server_object`), the same isolation as that file: env
redirected to `tmp_path`, registry included, so nothing here reads or probes this
developer's real daemons.

WHAT IS REAL AND WHAT IS INJECTED, said once. Hub A and peer B are both REAL
`UIHTTPServer` instances, and the mint, the redeem and the session that follows
go over real loopback sockets. The ONE injection is the summary probe: two
servers in one test process resolve the SAME identity (one `AGENTS_PROJECT_JSON`
per test), so B's real `/api/peer/summary` names A's project id and the real
probe would call B dead. Where the probe is the property under test (M1, M10,
the 502 arms), a stub peer answers it for real instead. The Windows owner/mode
branch (M14) is SIMULATED on this platform by removing `os.getuid`, never measured
on Windows itself.
"""
from __future__ import annotations

import http.client
import http.server
import importlib.util
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

import test_dashboard as td
from test_dashboard import _drain_streams, _redirect, ui_server, ui_server_object  # noqa: F401 — fixtures, ré-exposées pour CE module

dashboard = td.dashboard
handoff = dashboard._handoff_mod
registry = handoff._registry

_OWN_ID, _OTHER_ID = td._OWN_ID, td._OTHER_ID
_HUB = "/api/peers/handoff"
_MINT = "/api/handoff/mint"
_REDEEM = "/api/handoff/redeem"
_HUB_KEYS = {"api_version", "kind", "project_id", "port", "ticket", "expires_in"}


# ---------------------------------------------------------------------------
# HTTP, servers, locks
# ---------------------------------------------------------------------------

def _request(port: int, method: str, path: str, *, headers: dict | None = None,
             payload=None, raw: bytes | None = None, host: list[str] | None = None):
    """One request. `host=None` lets http.client send its own `Host:
    127.0.0.1:<port>`; a list sends exactly those Host headers (empty: none)."""
    body = raw if raw is not None else (json.dumps(payload).encode("utf-8") if payload is not None else None)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        conn.putrequest(method, path, skip_host=host is not None, skip_accept_encoding=True)
        for value in host or []:
            conn.putheader("Host", value)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        if body is not None:
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        resp = conn.getresponse()
        resp.data = resp.read()  # type: ignore[attr-defined]
        return resp
    finally:
        conn.close()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _hub(port: int, token: str | None, project_id=_OTHER_ID, **kw):
    headers = _bearer(token) if token is not None else {}
    return _request(port, "POST", _HUB, headers=headers, payload={"project_id": project_id}, **kw)


def _mint(port: int, token: str | None, **kw):
    headers = _bearer(token) if token is not None else {}
    return _request(port, "POST", _MINT, headers=headers, payload={}, **kw)


def _redeem(port: int, ticket: str | None, **kw):
    headers = {"Authorization": f"Handoff {ticket}"} if ticket is not None else {}
    return _request(port, "GET", _REDEEM, headers=headers, **kw)


def _json(resp) -> dict:
    return json.loads(resp.data)


@pytest.fixture
def servers(_redirect):
    """Factory of REAL extra `UIHTTPServer` instances (the peers), each on its
    own project root; all shut down at teardown, a second shutdown harmless."""
    started: list[tuple] = []

    def start(root: Path):
        root.mkdir(parents=True, exist_ok=True)
        result = dashboard.create_ui_server(project_root=root)
        assert result is not None
        httpd, token = result
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        started.append((httpd, thread))
        return httpd, httpd.server_address[1], token

    try:
        yield start
    finally:
        for httpd, thread in started:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


def _stop(httpd) -> None:
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def stub_peer():
    """A RECORDING stub peer: answers `/api/peer/summary` for the project id it
    is given (so the REAL probe passes) and POST with the status/body asked —
    404 by default, which is what an older daemon's `_route_write` answers to an
    unknown path. Every request is recorded as (method, path, Authorization)."""
    servers_: list[http.server.HTTPServer] = []

    def start(project_id: str, *, post_status: int = 404, post_body: bytes | None = None,
              post_delay: float = 0.0):
        seen: list[tuple[str, str, str | None]] = []
        summary = json.dumps({"api_version": 1, "kind": registry.PEER_SUMMARY_KIND,
                              "project_id": project_id}).encode("utf-8")

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _send(self, status: int, body: bytes) -> None:
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the client gave up (timeout arm): nothing to answer

            def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's contract
                seen.append(("GET", self.path, self.headers.get("Authorization")))
                if self.path == registry.PEER_SUMMARY_PATH:
                    self._send(200, summary)
                else:
                    self._send(404, b'{"error": "not_found"}')

            def do_POST(self):  # noqa: N802
                seen.append(("POST", self.path, self.headers.get("Authorization")))
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                if post_delay:
                    time.sleep(post_delay)
                self._send(post_status, post_body if post_body is not None else b'{"error": "not_found"}')

            def log_message(self, *args):
                pass

        class _Server(http.server.ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 64

        httpd = _Server(("127.0.0.1", 0), _Handler)
        servers_.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd.server_address[1], seen

    try:
        yield start
    finally:
        for httpd in servers_:
            httpd.shutdown()
            httpd.server_close()


def _write_lock(root: Path, *, pid: int, port: int, token: str, mode: int = 0o600,
                raw: bytes | None = None) -> Path:
    """A lock in the daemon's shape. `chmod` EXPLICIT: a developer umask of 002
    would otherwise write 0o664 and every test would read `lock_foreign_owner`."""
    path = handoff.lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = raw if raw is not None else json.dumps({
        "pid": pid, "port": port, "token": token, "otel": "ok",
        "started": "2026-10-14T09:00:00", "code": "0" * 16}).encode("utf-8")
    path.write_bytes(data)
    os.chmod(path, mode)
    return path


def _register(project_id: str, root: Path | str, port: int, pid: int | None = None) -> None:
    td._write_registry([td._registry_entry(project_id, port, project_root=str(root),
                                           pid=os.getpid() if pid is None else pid)])


def _inject_probe(monkeypatch, verdict: str = registry.ALIVE) -> list[tuple]:
    """Replace the summary probe IN THE HANDOFF MODULE'S registry instance only
    (`/api/peers` keeps the real one) and record every call."""
    calls: list[tuple] = []

    def fake(port, project_id=None, timeout=registry.PROBE_TIMEOUT_SECONDS):
        calls.append((port, project_id))
        return verdict, ({"kind": registry.PEER_SUMMARY_KIND, "project_id": project_id}
                         if verdict == registry.ALIVE else None)

    monkeypatch.setattr(registry, "probe_peer", fake)
    return calls


@pytest.fixture
def chain(ui_server, servers, _redirect, monkeypatch, tmp_path):
    """Hub A (`ui_server`) + a REAL peer B registered under `_OTHER_ID`, its lock
    under its own root, the probe injected (see the module docstring)."""
    port_a, token_a = ui_server
    root_b = tmp_path / "peer-b"
    httpd_b, port_b, token_b = servers(root_b)
    _register(_OTHER_ID, root_b, port_b)
    lock = _write_lock(root_b, pid=os.getpid(), port=port_b, token=token_b)
    probes = _inject_probe(monkeypatch)
    return {"port_a": port_a, "token_a": token_a, "root_b": root_b, "httpd_b": httpd_b,
            "port_b": port_b, "token_b": token_b, "lock": lock, "probes": probes}


# ---------------------------------------------------------------------------
# The whole chain, then M1-M15
# ---------------------------------------------------------------------------

def test_the_hub_hands_a_ticket_that_the_peer_trades_for_its_session(chain):
    """The contract end to end: A answers `{port, ticket}` and never token B;
    B trades the ticket for token B, which then authenticates a real read."""
    resp = _hub(chain["port_a"], chain["token_a"])
    assert resp.status == 200, resp.data
    assert resp.getheader("Cache-Control") == "no-store"
    body = _json(resp)
    assert set(body) == _HUB_KEYS
    assert body["api_version"] == 1 and body["kind"] == "agentkit.peer_handoff"
    assert body["project_id"] == _OTHER_ID and body["port"] == chain["port_b"]
    assert body["expires_in"] == 60 and handoff.TICKET_RE.match(body["ticket"])
    assert chain["token_b"] not in resp.data.decode("utf-8")
    assert chain["probes"] == [(chain["port_b"], _OTHER_ID)]

    session = _redeem(chain["port_b"], body["ticket"])
    assert session.status == 200
    assert session.getheader("Cache-Control") == "no-store"
    assert _json(session) == {"kind": "agentkit.handoff_session", "token": chain["token_b"]}
    assert _request(chain["port_b"], "GET", "/api/ping", headers=_bearer(chain["token_b"])).status == 200


def test_m1_a_registry_port_that_is_not_the_lock_port_is_refused_and_the_stub_hears_no_token(
        ui_server, servers, stub_peer, tmp_path):
    """M1 — the poisoned registry: B's root, a STUB's port. The stub answers the
    real probe with the right `project_id`, so only `lock.port == entry.port`
    stands between it and the token. MUTANT (port equality removed): the mint
    reaches the real B behind the lock and the route answers 200."""
    port_a, token_a = ui_server
    root_b = tmp_path / "peer-b"
    _httpd_b, port_b, token_b = servers(root_b)
    stub_port, seen = stub_peer(_OTHER_ID)
    _register(_OTHER_ID, root_b, stub_port)
    _write_lock(root_b, pid=os.getpid(), port=port_b, token=token_b)

    resp = _hub(port_a, token_a)
    assert resp.status == 409
    assert _json(resp) == {"error": "peer_unverified", "reason": "lock_mismatch"}
    assert seen, "the stub was never probed — the refusal came from elsewhere"
    assert all(method == "GET" for method, _p, _a in seen), seen
    assert all(auth is None for _m, _p, auth in seen), seen


def test_m2_a_lock_pid_that_is_not_the_entry_pid_is_refused(chain):
    """M2 — MUTANT (pid equality removed): same port, so the mint succeeds -> 200."""
    _write_lock(chain["root_b"], pid=os.getpid() + 1, port=chain["port_b"], token=chain["token_b"])
    resp = _hub(chain["port_a"], chain["token_a"])
    assert resp.status == 409
    assert _json(resp) == {"error": "peer_unverified", "reason": "lock_mismatch"}


def test_m3_a_ticket_is_good_once(ui_server):
    """M3 — MUTANT (the redeem reads instead of popping): the second redeem is 200."""
    port, token = ui_server
    ticket = _json(_mint(port, token))["ticket"]
    assert _redeem(port, ticket).status == 200
    second = _redeem(port, ticket)
    assert second.status == 404
    assert _json(second) == {"error": "not_found"}


def test_m4_a_ticket_dies_after_its_ttl(ui_server_object):
    """M4 — the clock moved past 60 s: 404. Bracketed by a ticket redeemed at
    +59 s, so the 404 is the TTL and not some other refusal."""
    httpd, port, token = ui_server_object
    late = _json(_mint(port, token))["ticket"]
    early = _json(_mint(port, token))["ticket"]
    now = time.monotonic()
    httpd.handoff_tickets.clock = lambda: now + 59
    assert _redeem(port, early).status == 200
    httpd.handoff_tickets.clock = lambda: now + 61
    assert _redeem(port, late).status == 404


@pytest.mark.parametrize("token", [None, "not-the-token"])
def test_m5_the_hub_route_without_its_token_is_a_404_that_consults_nothing(chain, token):
    """M5 — no token or a wrong one: the uniform 404, and neither the registry
    probe nor the peer was touched."""
    resp = _hub(chain["port_a"], token)
    assert resp.status == 404 and _json(resp) == {"error": "not_found"}
    assert chain["probes"] == []
    assert len(chain["httpd_b"].handoff_tickets) == 0


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX owner check; Windows: NOT MEASURED (M14)")
def test_m6_a_lock_owned_by_another_uid_or_writable_by_others_is_refused(chain, monkeypatch):
    """M6 — the owner/mode check, POSIX only. First the control (200), then a
    foreign uid, then a group/other-writable lock: both `lock_foreign_owner`."""
    assert _hub(chain["port_a"], chain["token_a"]).status == 200
    real = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real + 1)
    resp = _hub(chain["port_a"], chain["token_a"])
    assert resp.status == 409
    assert _json(resp) == {"error": "peer_unverified", "reason": "lock_foreign_owner"}
    monkeypatch.setattr(os, "getuid", lambda: real)
    for mode in (0o620, 0o602, 0o666):
        os.chmod(chain["lock"], mode)
        resp = _hub(chain["port_a"], chain["token_a"])
        assert _json(resp) == {"error": "peer_unverified", "reason": "lock_foreign_owner"}, oct(mode)


def test_m7_no_token_and_no_ticket_reaches_a_log(chain, stub_peer, capfd):
    """M7 — success, a 409 and a 502 driven through the real servers; neither
    token A, token B nor the ticket appears on stdout/stderr (fd level), nor
    in a refusal body."""
    ok = _hub(chain["port_a"], chain["token_a"])
    ticket = _json(ok)["ticket"]
    assert _redeem(chain["port_b"], ticket).status == 200
    _write_lock(chain["root_b"], pid=os.getpid() + 1, port=chain["port_b"], token=chain["token_b"])
    refused = _hub(chain["port_a"], chain["token_a"])
    assert refused.status == 409
    stub_port, _seen = stub_peer(_OTHER_ID, post_status=500)
    _register(_OTHER_ID, chain["root_b"], stub_port)
    _write_lock(chain["root_b"], pid=os.getpid(), port=stub_port, token=chain["token_b"])
    failed = _hub(chain["port_a"], chain["token_a"])
    assert failed.status == 502
    out, err = capfd.readouterr()
    for secret in (chain["token_a"], chain["token_b"], ticket):
        assert secret not in out and secret not in err
        assert secret.encode() not in refused.data and secret.encode() not in failed.data


def test_m8_a_relaunched_peer_does_not_honour_its_predecessor_s_ticket(chain, servers, tmp_path):
    """M8 — tickets live in the INSTANCE. B relaunched (a new server, the lock
    and the registry rewritten): the old ticket is 404, a new one is 200."""
    old = _json(_hub(chain["port_a"], chain["token_a"]))["ticket"]
    _stop(chain["httpd_b"])
    _httpd_b2, port_b2, token_b2 = servers(chain["root_b"])
    _register(_OTHER_ID, chain["root_b"], port_b2)
    _write_lock(chain["root_b"], pid=os.getpid(), port=port_b2, token=token_b2)
    new = _hub(chain["port_a"], chain["token_a"])
    assert new.status == 200 and _json(new)["port"] == port_b2
    assert _redeem(port_b2, old).status == 404
    assert _redeem(port_b2, _json(new)["ticket"]).status == 200


def test_m9_asking_for_oneself_is_refused_before_anything_is_read(chain):
    """M9 — `self`, and the probe never ran."""
    resp = _hub(chain["port_a"], chain["token_a"], project_id=_OWN_ID)
    assert resp.status == 409
    assert _json(resp) == {"error": "peer_unverified", "reason": "self"}
    assert chain["probes"] == []


def test_m10_a_peer_without_the_mint_route_is_too_old_and_got_only_its_own_token(
        ui_server, stub_peer, tmp_path):
    """M10 — a peer on older code answers 404 to the mint: 502 `too_old`. The
    stub, behind a real probe, also proves where the token went: ONE POST, to
    the mint path, carrying the lock's token and nothing else."""
    port_a, token_a = ui_server
    root_b = tmp_path / "old-peer"
    stub_port, seen = stub_peer(_OTHER_ID)
    _register(_OTHER_ID, root_b, stub_port)
    _write_lock(root_b, pid=os.getpid(), port=stub_port, token="old-peer-token")
    resp = _hub(port_a, token_a)
    assert resp.status == 502
    assert resp.getheader("Cache-Control") == "no-store"
    assert _json(resp) == {"error": "peer_mint_failed", "reason": "too_old"}
    posts = [entry for entry in seen if entry[0] == "POST"]
    assert posts == [("POST", _MINT, "Bearer old-peer-token")]


def test_m11_crossed_verbs_are_404s_and_consume_nothing(chain):
    """M11 — GET on the two POSTs, every other verb on redeem: 404. A POST on
    redeem carrying a VALID ticket does not spend it."""
    for path in (_HUB, _MINT):
        assert _request(chain["port_a"], "GET", path, headers=_bearer(chain["token_a"])).status == 404
    ticket = _json(_hub(chain["port_a"], chain["token_a"]))["ticket"]
    handoff_auth = {"Authorization": f"Handoff {ticket}"}
    for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        payload = {} if method in ("POST", "PUT", "PATCH") else None
        resp = _request(chain["port_b"], method, _REDEEM, headers=handoff_auth, payload=payload)
        assert resp.status == 404, method
    assert _redeem(chain["port_b"], ticket).status == 200


_LOCK_SAMPLES = [
    {"pid": 1, "port": 2, "token": "t"},
    {"pid": 1, "port": 2, "token": "t", "extra": [1]},
    {"pid": 1, "port": 2},
    {"pid": 1, "port": 2, "token": ""},
    {"pid": 1, "port": 2, "token": 7},
    {"pid": "1", "port": 2, "token": "t"},
    {"pid": 1, "port": "2", "token": "t"},
    {"pid": True, "port": 2, "token": "t"},
    {"pid": 1.0, "port": 2, "token": "t"},
    [1, 2, "t"],
    None,
    "not json",
]


def test_m12_the_lock_is_read_with_the_daemon_s_own_acceptance(tmp_path):
    """M12 — the SECOND spelling of the lock (path + shape) agrees with
    `dashboard_daemon` (SYM-00628 `read_lock`): same path, same accepted and
    refused samples, same fields when accepted. The daemon is loaded HERE,
    never by the module (it would close an import cycle)."""
    spec = importlib.util.spec_from_file_location("_test_handoff_daemon", td.HERE / "dashboard_daemon.py")
    daemon = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = daemon
    spec.loader.exec_module(daemon)
    root = tmp_path / "lock-shape"
    root.mkdir()
    assert daemon.lock_path(root) == handoff.lock_path(root)
    accepted = 0
    for sample in _LOCK_SAMPLES:
        raw = sample.encode() if isinstance(sample, str) else json.dumps(sample).encode()
        _write_lock(root, pid=0, port=0, token="", raw=raw)
        theirs = daemon.read_lock(root)
        ours, reason = handoff.read_peer_lock(root)
        assert (theirs is None) == (ours is None), sample
        if ours is not None:
            accepted += 1
            assert (ours.pid, ours.port, ours.token) == (theirs["pid"], theirs["port"], theirs["token"])
        else:
            assert reason == "lock_unreadable", sample
    assert accepted >= 2, "no sample was accepted — the comparison would be vacuous"


_FOREIGN_HOSTS = [
    ["localhost:{port}"], ["127.0.0.1:{other}"], ["127.0.0.1"], ["evil.example"],
    ["[::1]:{port}"], ["127.0.0.1:{port}", "127.0.0.1:{port}"], [],
]


def _hosts(template: list[str], port: int) -> list[str]:
    return [h.format(port=port, other=port + 1) for h in template]


@pytest.mark.parametrize("template", _FOREIGN_HOSTS)
def test_m13_a_foreign_host_is_the_uniform_404_on_all_three_routes(chain, template):
    """M13 — DNS rebinding: every Host but `127.0.0.1:<port>`, missing or doubled
    included, is the 404 of an unknown route, on valid credentials, and spends
    nothing. Bracketed: the same requests with the right Host succeed."""
    port_a, port_b = chain["port_a"], chain["port_b"]
    unknown = _request(port_a, "POST", "/api/actions/nope", payload={})
    hub = _hub(port_a, chain["token_a"], host=_hosts(template, port_a))
    assert hub.status == 404 and hub.data == unknown.data
    assert chain["probes"] == []
    mint = _mint(port_b, chain["token_b"], host=_hosts(template, port_b))
    assert mint.status == 404 and mint.data == unknown.data
    assert len(chain["httpd_b"].handoff_tickets) == 0
    ticket = _json(_hub(port_a, chain["token_a"]))["ticket"]
    redeem = _redeem(port_b, ticket, host=_hosts(template, port_b))
    assert redeem.status == 404 and redeem.data == unknown.data
    assert _redeem(port_b, ticket).status == 200


def test_m14_without_getuid_a_0666_lock_still_hands_off(chain, monkeypatch):
    """M14 (plan-critic C2) — the Windows branch, SIMULATED: `os.getuid` absent
    AND a lock whose mode is 0o100666 (what Windows reports for a writable
    file). The handoff must SUCCEED — 200, a ticket, the port, and a redeem
    that works — not merely avoid a 500. MUTANT (mode check kept without
    getuid): 409 `lock_foreign_owner`."""
    os.chmod(chain["lock"], 0o666)
    if os.name != "nt":
        assert os.stat(chain["lock"]).st_mode == 0o100666
    monkeypatch.delattr(os, "getuid", raising=False)
    resp = _hub(chain["port_a"], chain["token_a"])
    assert resp.status == 200, resp.data
    body = _json(resp)
    assert body["port"] == chain["port_b"] and handoff.TICKET_RE.match(body["ticket"])
    assert _redeem(chain["port_b"], body["ticket"]).status == 200


def test_m15_the_book_purges_the_expired_then_evicts_the_oldest():
    """M15 — at most 16 live tickets. A mint first drops the expired (no live
    one is evicted while an expired one remains), then the oldest live one:
    the 17th evicts the 1st."""
    now = [0.0]
    book = handoff.TicketBook(clock=lambda: now[0])
    stale = [book.mint() for _ in range(8)]
    now[0] = 30.0
    live = [book.mint() for _ in range(8)]
    now[0] = 61.0
    fresh = book.mint()
    assert len(book) == 9, "the expired were not purged first"
    assert not any(book.redeem(t) for t in stale)
    assert all(book.redeem(t) for t in live + [fresh])

    book = handoff.TicketBook(clock=lambda: 0.0)
    tickets = [book.mint() for _ in range(handoff.MAX_TICKETS + 1)]
    assert len(book) == handoff.MAX_TICKETS == 16
    assert book.redeem(tickets[0]) is False
    assert all(book.redeem(t) for t in tickets[1:])


# ---------------------------------------------------------------------------
# The route tables and the write-flow nets, for the two handoff tables.
#
# These are the handoff arms of SYM-01473 (`test_the_api_route_set_stays_closed_
# and_small`) and of SYM-01616/01617/01618/01620 in `test_dashboard.py`, held
# HERE rather than amended in place: that file sits at its ratchet ceiling
# (T-01M4XKCTGEW9MDAYNCBK6R7SD9 split). SYM-01473's docstring points here.
# ---------------------------------------------------------------------------

_HANDOFF_POSTS = [_HUB, _MINT]


def test_the_handoff_tables_stay_closed_disjoint_and_404_on_get(ui_server):
    """SYM-01473's handoff arm. The two tables, by EQUALITY; the six tables of
    the server pairwise disjoint (a route is exempt OR token-required, readable
    OR writable, never both by check order); the module's dispatch constants
    equal to the tables (`route_write` would otherwise 404 a member); and GET on
    either POST, or on redeem WITHOUT a ticket (a Bearer token is not one), is
    the 404 of an absent route — near misses included."""
    assert dashboard._ALLOWED_HANDOFF_PATHS == frozenset({"/api/handoff/redeem"})
    assert dashboard._ALLOWED_HANDOFF_WRITE_PATHS == frozenset({"/api/peers/handoff", "/api/handoff/mint"})
    assert dashboard._ALLOWED_HANDOFF_PATHS == {handoff.REDEEM_PATH}
    assert dashboard._ALLOWED_HANDOFF_WRITE_PATHS == {handoff.HUB_PATH, handoff.MINT_PATH}
    tables = {"ui": dashboard._ALLOWED_UI_PATHS, "peer": dashboard._ALLOWED_PEER_PATHS,
              "static": frozenset(dashboard._ALLOWED_STATIC_ROUTES),
              "write": dashboard._ALLOWED_WRITE_PATHS,
              "handoff": dashboard._ALLOWED_HANDOFF_PATHS,
              "handoff_write": dashboard._ALLOWED_HANDOFF_WRITE_PATHS}
    names = sorted(tables)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            assert not (tables[left] & tables[right]), (left, right)
    port, token = ui_server
    for path in (_HUB, _MINT, _REDEEM, "/api/handoff", "/api/handoff/", "/api/handoff/redeem/",
                 "/api/handoff/Redeem", "/api/peers/handoff/", "/api/handoff/mint/"):
        assert _request(port, "GET", path, headers=_bearer(token)).status == 404, path


_ROUTE_TABLE_NAMES = frozenset({
    "_ALLOWED_UI_PATHS", "_ALLOWED_STATIC_ROUTES", "_ALLOWED_PEER_PATHS",
    "_ALLOWED_WRITE_PATHS", "_ALLOWED_HANDOFF_PATHS", "_ALLOWED_HANDOFF_WRITE_PATHS",
})


def _route_table_names(module) -> set[str]:
    return {name for name in vars(module) if name.startswith("_ALLOWED_")}


def test_the_server_has_exactly_these_six_route_tables(monkeypatch):
    """The SET of tables, not only their contents (exec-critic blind spot): each
    table is pinned by equality somewhere, but a SEVENTH `_ALLOWED_*` table
    would be pinned by nothing and the disjointness net above would not even
    see it. Non-vacuity in the same test: with a seventh table injected, the
    witness no longer matches."""
    assert _route_table_names(dashboard) == _ROUTE_TABLE_NAMES
    monkeypatch.setattr(dashboard, "_ALLOWED_SEVENTH_PATHS", frozenset({"/api/x"}), raising=False)
    assert _route_table_names(dashboard) != _ROUTE_TABLE_NAMES, "a seventh table must turn this red"


def test_every_redeem_refusal_is_byte_identical_to_an_unknown_route_bar_the_date(ui_server):
    """The redeem's refusals — no ticket, a spent one, an unknown one of the
    right shape, a Bearer token instead of a ticket, a foreign Host — answer
    what an unknown GET answers: status, body and every header save `Date`.
    Measured equal before; now held."""
    port, token = ui_server
    unknown = _request(port, "GET", "/api/nope")
    unknown_headers = td._comparable_headers(unknown)
    assert unknown.status == 404 and unknown_headers, "no comparable headers — the equality would be vacuous"
    ticket = _json(_mint(port, token))["ticket"]
    other = _json(_mint(port, token))["ticket"]
    assert _redeem(port, ticket).status == 200
    refusals = [_redeem(port, None), _redeem(port, ticket), _redeem(port, "A" * 43),
                _request(port, "GET", _REDEEM, headers=_bearer(token)),
                _redeem(port, other, host=["evil.example"])]
    for resp in refusals:
        assert resp.status == 404 and resp.data == unknown.data
        assert td._comparable_headers(resp) == unknown_headers


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "GET"])
@pytest.mark.parametrize("path", _HANDOFF_POSTS)
def test_a_handoff_post_answers_POST_and_nothing_else(ui_server, method, path):
    """SYM-01616's handoff arm: the two POSTs add no verb either."""
    port, token = ui_server
    assert td._verb(port, method, path, token=token) == 404


@pytest.mark.parametrize("token", [None, "not-the-token"])
@pytest.mark.parametrize("path", _HANDOFF_POSTS)
def test_a_handoff_post_without_its_token_is_a_404(ui_server, path, token):
    """SYM-01617/01618's handoff arm: no token or a wrong one is the uniform
    404 — a mint without the peer's own token would hand a ticket, hence the
    token, to anyone."""
    port, _token = ui_server
    assert td._post_json(port, path, {"confirm": True}, token=token).status == 404


@pytest.mark.parametrize("path", _HANDOFF_POSTS)
def test_an_unauthenticated_handoff_post_is_byte_identical_to_an_unknown_path_bar_the_date(ui_server, path):
    """SYM-01620's handoff arm, the same scoped invariant: unauthenticated, the
    two POSTs answer exactly what an unknown path answers — status, body and
    every header save `Date` — with no token AND with a foreign Host."""
    port, _token = ui_server
    unknown = td._post_json(port, "/api/actions/nope", {})
    unknown_headers = td._comparable_headers(unknown)
    assert unknown_headers, "no comparable headers — the equality would be vacuous"
    for resp in (td._post_json(port, path, {"confirm": True}),
                 _request(port, "POST", path, payload={}, host=["localhost:%d" % port])):
        assert resp.status == unknown.status == 404
        assert resp.data == unknown.data
        assert td._comparable_headers(resp) == unknown_headers


def test_the_host_is_checked_before_the_token_is_consulted(ui_server, monkeypatch):
    """The ORDER inside `route_write`, saved as a property of the CALL (the
    SYM-01619 shape): a foreign Host never reaches `_check_token`; the right
    Host does (non-vacuity), and so does nothing on an unknown path."""
    port, token = ui_server
    consulted: list[str] = []
    original = dashboard.UIHandler._check_token

    def wrapper(self):
        consulted.append(self.path)
        return original(self)

    monkeypatch.setattr(dashboard.UIHandler, "_check_token", wrapper)
    assert _mint(port, token, host=["evil.example"]).status == 404
    assert consulted == []
    assert _mint(port, token).status == 200
    assert consulted == [_MINT]


@pytest.mark.parametrize("raw, expected", [
    (None, "served_elsewhere"), (b"not json", "unknown"), (b"[1]", "unknown"), (b'{"otel": ""}', "unknown"),
])
def test_the_peer_summary_reads_its_otel_status_off_the_moved_lock_reader(ui_server, _redirect, raw, expected):
    """`lock_health` moved from `dashboard._lock_health` with its body: the
    `health.otel` of `/api/peer/summary` is the lock's `otel`, and every way the
    lock can be unusable degrades to `unknown`, never an error. Absent lock:
    `unknown` too (asserted first, so the 200 arm cannot pass by default)."""
    port, _token = ui_server
    root = _redirect["project_root"]
    assert _json(_request(port, "GET", "/api/peer/summary"))["health"]["otel"] == "unknown"
    path = handoff.lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else json.dumps({"pid": 1, "port": 2, "token": "t",
                                                               "otel": "served_elsewhere"}).encode())
    assert _json(_request(port, "GET", "/api/peer/summary"))["health"]["otel"] == expected


# ---------------------------------------------------------------------------
# The rest of the contract
# ---------------------------------------------------------------------------

def test_mint_answers_the_ticket_contract_and_redeem_does_not_stamp_activity(ui_server_object):
    """Mint: `{kind, ticket, expires_in}`, no-store. Redeem: `last_activity`
    untouched (pinned to 0.0 so the assertion does not hang on clock
    granularity); a Bearer read afterwards does stamp it (non-vacuity)."""
    httpd, port, token = ui_server_object
    resp = _mint(port, token)
    assert resp.status == 200 and resp.getheader("Cache-Control") == "no-store"
    body = _json(resp)
    assert set(body) == {"kind", "ticket", "expires_in"}
    assert body["kind"] == "agentkit.handoff_ticket" and body["expires_in"] == 60
    httpd.last_activity = 0.0
    assert _redeem(port, body["ticket"]).status == 200
    assert httpd.last_activity == 0.0, "a redeem must not keep the daemon alive"
    assert _request(port, "GET", "/api/ping", headers=_bearer(token)).status == 200
    assert httpd.last_activity > 0.0


@pytest.mark.parametrize("auth", [None, "Bearer {token}", "Handoff ", "Handoff short",
                                  "handoff {ticket}", "Handoff {ticket}x", "Handoff  {ticket}"])
def test_redeem_refuses_every_other_credential_with_the_uniform_404(ui_server, auth):
    """Only `Handoff <the exact ticket>` redeems; the session token itself, a
    wrong scheme case, a padded or extended ticket are all the unknown-route
    404 — and none of them spends the real ticket."""
    port, token = ui_server
    ticket = _json(_mint(port, token))["ticket"]
    headers = {"Authorization": auth.format(token=token, ticket=ticket)} if auth is not None else {}
    resp = _request(port, "GET", _REDEEM, headers=headers)
    assert resp.status == 404 and _json(resp) == {"error": "not_found"}
    assert _redeem(port, ticket).status == 200


@pytest.mark.parametrize("payload", [{}, {"project_id": 7}, {"project_id": ""},
                                     {"project_id": "x" * 201}, {"project_id": None}])
def test_the_hub_route_refuses_a_malformed_project_id(chain, payload):
    resp = _request(chain["port_a"], "POST", _HUB, headers=_bearer(chain["token_a"]), payload=payload)
    assert resp.status == 400 and _json(resp) == {"error": "bad_request"}
    assert chain["probes"] == []


def test_each_unverified_reason_is_reachable(chain, monkeypatch, tmp_path):
    """The 409 vocabulary, one arm per reason not covered above, each on the
    otherwise-valid chain so the reason named is the only fault."""
    port_a, token_a = chain["port_a"], chain["token_a"]

    def reason() -> str:
        resp = _hub(port_a, token_a)
        assert resp.status == 409, resp.data
        return _json(resp)["reason"]

    assert _json(_hub(port_a, token_a, project_id="nobody"))["reason"] == "not_registered"
    _register(_OTHER_ID, chain["root_b"], chain["port_b"], pid=2 ** 22 + 12345)
    monkeypatch.setattr(registry, "pid_alive", lambda pid: pid == os.getpid())
    assert reason() == "pid_dead"
    _register(_OTHER_ID, chain["root_b"], chain["port_b"])
    _inject_probe(monkeypatch, verdict=registry.INDETERMINATE)
    assert reason() == "probe_not_alive"
    _inject_probe(monkeypatch)
    for bad_root in ("relative/root", str(chain["root_b"] / ".." / "peer-b"), str(tmp_path / "absent")):
        _register(_OTHER_ID, bad_root, chain["port_b"])
        assert reason() == "lock_unreadable", bad_root
    _register(_OTHER_ID, chain["root_b"], chain["port_b"])
    lock = chain["lock"]
    target = lock.with_name("real.lock")
    lock.rename(target)
    try:
        lock.symlink_to(target)
    except OSError:
        pass  # no symlink privilege (Windows without developer mode): arm not measured here
    else:
        assert reason() == "lock_unreadable", "a symlinked lock must not be followed"
        lock.unlink()
    assert reason() == "lock_unreadable"
    assert set(handoff.UNVERIFIED_REASONS) == {"not_registered", "self", "pid_dead", "probe_not_alive",
                                               "lock_unreadable", "lock_foreign_owner", "lock_mismatch"}


@pytest.mark.parametrize("post_status, post_body, expected", [
    (500, None, "refused"),
    (200, b'{"kind": "something.else", "ticket": "x"}', "bad_answer"),
    (200, b'{"kind": "agentkit.handoff_ticket", "ticket": "too-short"}', "bad_answer"),
    (200, b"not json", "bad_answer"),
])
def test_each_mint_failure_reason_is_reachable(ui_server, stub_peer, tmp_path, post_status, post_body, expected):
    """The 502 vocabulary through a stub peer behind the REAL probe."""
    port_a, token_a = ui_server
    root = tmp_path / "stub-root"
    stub_port, _seen = stub_peer(_OTHER_ID, post_status=post_status, post_body=post_body)
    _register(_OTHER_ID, root, stub_port)
    _write_lock(root, pid=os.getpid(), port=stub_port, token="stub-token")
    resp = _hub(port_a, token_a)
    assert resp.status == 502
    assert _json(resp) == {"error": "peer_mint_failed", "reason": expected}


def test_a_mint_that_hangs_or_finds_nobody_is_timeout_or_refused(ui_server, stub_peer, tmp_path, monkeypatch):
    port_a, token_a = ui_server
    root = tmp_path / "slow-root"
    monkeypatch.setattr(handoff, "MINT_TIMEOUT_SECONDS", 0.3)
    stub_port, _seen = stub_peer(_OTHER_ID, post_status=200, post_delay=2.0)
    _register(_OTHER_ID, root, stub_port)
    _write_lock(root, pid=os.getpid(), port=stub_port, token="stub-token")
    assert _json(_hub(port_a, token_a)) == {"error": "peer_mint_failed", "reason": "timeout"}
    dead = td._dead_port()
    _inject_probe(monkeypatch)
    _register(_OTHER_ID, root, dead)
    _write_lock(root, pid=os.getpid(), port=dead, token="stub-token")
    assert _json(_hub(port_a, token_a)) == {"error": "peer_mint_failed", "reason": "refused"}
    assert set(handoff.MINT_FAILURE_REASONS) == {"too_old", "refused", "bad_answer", "timeout"}


def test_the_lock_token_never_appears_in_a_repr():
    lock = handoff.PeerLock(pid=1, port=2, token="secret-token-value")
    outcome = handoff.HandoffOutcome(error=None, reason=None, port=2, ticket="secret-ticket-value")
    assert "secret-token-value" not in repr(lock)
    assert "secret-ticket-value" not in repr(outcome)


# ---------------------------------------------------------------------------
# Bounded freshness witness of the bundle
# ---------------------------------------------------------------------------

_API_LITERAL_RE = re.compile(r"""["'`](/api/[A-Za-z0-9/_-]+)""")
_HANDOFF_MARKERS = ("#handoff=", "Handoff ")


def test_the_bundle_carries_every_api_literal_of_the_client_source():
    """BOUNDED, and that bound is the whole claim: every `/api/...` literal of
    `ui-src/src/lib/api.js`, plus `#handoff=` and `Handoff ` WHEN api.js carries
    them, is present in the served `.agents/ui/assets/app.js`. It proves those
    literals and NOTHING ELSE of the logic. Conditional on purpose: green before
    the client lands (lot B1), red the day it lands without a rebuild."""
    api_js = dashboard._UI_DIR.parent / "ui-src" / "src" / "lib" / "api.js"
    app_js = dashboard._UI_DIR / "assets" / "app.js"
    if not api_js.is_file():
        pytest.skip("ui-src absent from this copy — nothing to compare the bundle with")
    source = api_js.read_text(encoding="utf-8")
    bundle = app_js.read_text(encoding="utf-8")
    literals = set(_API_LITERAL_RE.findall(source))
    assert literals, "no /api/ literal found in api.js — the witness would be vacuous"
    literals |= {marker for marker in _HANDOFF_MARKERS if marker in source}
    missing = sorted(lit for lit in literals if lit not in bundle)
    assert not missing, f"the bundle is older than api.js — rebuild it: {missing}"


def test_the_bundle_names_exactly_the_server_refusal_reasons():
    """The client says the CLOSED refusal reason (peers.js HANDOFF_REASON_TEXT,
    design-review E-37) only when it equals a server reason: the two closed lists
    must stay EQUAL, or a server rename turns every refusal into « (http_409) » in
    silence (critic-opus T2). Bounded: reads the esbuild-minified `Object.freeze`
    form of the served bundle — a change of that form reddens, never passes."""
    bundle = (dashboard._UI_DIR / "assets" / "app.js").read_text(encoding="utf-8")
    for block, server in (("unverified", handoff.UNVERIFIED_REASONS),
                          ("mint_failed", handoff.MINT_FAILURE_REASONS)):
        found = re.search(block + r":Object\.freeze\(\{([^}]*)\}", bundle)
        assert found, f"{block}: reason table not found in the served bundle"
        client = set(re.findall(r'(?:^|,)([a-z_]+):"', found.group(1)))
        assert client == set(server), f"{block}: client {sorted(client)} != server {sorted(server)}"


def test_a_peer_answering_non_http_is_a_closed_bad_answer_never_a_traceback():
    """`http.client.HTTPException` (BadStatusLine…) derives from neither OSError
    nor ValueError: before critic-opus T1 it escaped `mint_on_peer` to the default
    `handle_error` (traceback, connection cut, contract 502 broken)."""
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def answer_garbage():
        conn, _ = srv.accept()
        conn.recv(65536)
        conn.sendall(b"NOT-HTTP\r\n\r\n")
        conn.close()

    worker = threading.Thread(target=answer_garbage, daemon=True)
    worker.start()
    try:
        lock = handoff.PeerLock(pid=1, port=srv.getsockname()[1], token="t")
        assert handoff.mint_on_peer(lock) == (None, "bad_answer")
    finally:
        worker.join(timeout=5)
        srv.close()


def test_the_served_fingerprint_covers_the_handoff_module(monkeypatch, tmp_path):
    """`served_code_fingerprint` reads `dashboard_handoff.py`: a daemon on an
    older copy must read as stale. Witnessed by repointing `HERE` at a copy in
    which ONLY that file changes."""
    copy = tmp_path / "bin"
    copy.mkdir()
    for path in td.HERE.glob("*.py"):
        if path.name.startswith("dashboard") or path.name in ("wrap.py", "event_store.py", "events.py"):
            (copy / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(dashboard, "HERE", copy)
    first = dashboard.served_code_fingerprint()
    assert dashboard.served_code_fingerprint() == first, "the fingerprint is not stable"
    (copy / "dashboard_handoff.py").write_bytes(b"# changed\n")
    assert dashboard.served_code_fingerprint() != first
