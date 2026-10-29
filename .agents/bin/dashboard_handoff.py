#!/usr/bin/env python3
"""Access handoff between the dashboards of ONE machine (T-01M4XKCTGEW9MDAYNCBK6R7SD9).

THE NEED. A peer card opens `http://127.0.0.1:<port>/` bare: the neighbour's tab
holds no token, every `/api/*` answers 401 and its action buttons never render.
Its token lives in ONE place, the neighbour's own `state/local/dashboard.lock`,
and must never reach the machine-wide registry (L-00000112).

THE DESIGN — a single-use ticket MINTED BY THE PEER, REQUESTED BY THE HUB:

  1. the hub tab A (holding token A) asks its own daemon, `POST /api/peers/handoff`;
  2. daemon A verifies the registry entry (`verify_peer`), reads B's lock ON ITS
     SIDE OF THE PROCESS BOUNDARY, and calls `POST /api/handoff/mint` on
     `127.0.0.1:<lock.port>` with `Bearer <token B>` (`mint_on_peer`);
  3. daemon B mints a ticket (`TicketBook`: 32 random bytes, 60 s, single use,
     held in memory by THAT server instance, dead with its process);
  4. A hands `{port, ticket}` — never token B — back to its tab, which opens
     `http://127.0.0.1:<port>/#handoff=<ticket>`; B's client trades the ticket for
     its session token at `GET /api/handoff/redeem` (`Authorization: Handoff <t>`).

WHO GETS WHAT. Tab A: `{port, ticket}`. Daemon A: token B, read from the lock and
sent ONLY to `127.0.0.1:<lock.port>` — never to the registry's port, never through
a proxy, never after a redirect (`dashboard_registry._PROBE_OPENER`). Tab B: token
B, against the ticket. Token A never leaves origin A. NEW POWER, assumed and named:
whoever holds token A obtains full access to every live peer of the registry — a
compromise of A becomes transitive. A process of the SAME user already reads every
lock, so it gains nothing.

THE PEER IS THE REGISTRY'S PEER, OR NOTHING IS SENT. The registry is writable by
any process of this user, so an entry proves nothing alone: `project_id` is the
dictionary KEY, compared in memory (never a path); the entry's `project_root`
must be absolute, free of `..` and an existing directory; its pid must be alive;
its port must answer the summary probe with the SAME `project_id`; the lock under
that root must be a regular file, owned by the current uid and not writable by
group or others; and the lock's pid AND port must equal the entry's. A poisoned
entry (B's root, a stub's port) therefore stops at `lock_mismatch` and the token
is never emitted. Nothing here ever runs on a request-derived path.

WINDOWS, NAMED RATHER THAN IMPLIED. `os.getuid` does not exist there and a
writable file reports `0o666`; the owner/mode check is SKIPPED when
`getattr(os, "getuid", None)` is None — never a 500. What protects a Windows box
against another LOCAL USER squatting a port is therefore NOT MEASURED here.

THE LOCK IS READ HERE, NOT THROUGH `dashboard_daemon`: that module loads
`dashboard.py`, which loads this one, so the import would close a cycle. The
lock's relative path is therefore spelled a SECOND time (`_LOCK_RELPATH`, next to
`dashboard_daemon._LOCK_RELPATH`), and its accepted shape is held equal to
`dashboard_daemon.read_lock` by a test (`test_dashboard_handoff.py`, M12).

THE TOKEN NEVER APPEARS in a log (this module logs nothing; failures are closed
reason codes), in a repr (`PeerLock.token`, `HandoffOutcome.ticket` are
`repr=False`), or in an exception message. stdlib only.
"""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Explicit-path load, the convention of `dashboard.py` (never a bare
    `import` that would depend on `sys.path[0]`)."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# The registry, NEVER the daemon (see the module docstring). The registry holds
# no in-memory state, so this second module instance cannot disagree with the
# one `dashboard.py` loads.
_registry = _load_sibling("_dashboard_handoff_registry", "dashboard_registry.py")

HANDOFF_API_VERSION = 1
PEER_HANDOFF_KIND = "agentkit.peer_handoff"
HANDOFF_TICKET_KIND = "agentkit.handoff_ticket"
HANDOFF_SESSION_KIND = "agentkit.handoff_session"

MINT_PATH = "/api/handoff/mint"
TICKET_TTL_SECONDS = 60
MAX_TICKETS = 16
_TICKET_BYTES = 32
# `secrets.token_urlsafe(32)` is 43 characters of the URL-safe alphabet. A
# redeem whose credential does not have that shape is refused before hashing.
TICKET_RE = re.compile(r"\A[A-Za-z0-9_-]{43}\Z")

# The mint is a dictionary insert on the peer; two seconds is generous on a
# loaded machine and short enough not to pin the hub's handler thread.
MINT_TIMEOUT_SECONDS = 2.0
_MINT_READ_LIMIT_BYTES = 4096
_LOCK_READ_LIMIT_BYTES = 64 * 1024

# SECOND spelling of `dashboard_daemon._LOCK_RELPATH` — see the module docstring.
_LOCK_RELPATH = (".agents", "state", "local", "dashboard.lock")

# The closed vocabularies of the hub route's refusals (contract: 409 / 502).
PEER_UNVERIFIED = "peer_unverified"
PEER_MINT_FAILED = "peer_mint_failed"
UNVERIFIED_REASONS = frozenset({
    "not_registered", "self", "pid_dead", "probe_not_alive",
    "lock_unreadable", "lock_foreign_owner", "lock_mismatch",
})
MINT_FAILURE_REASONS = frozenset({"too_old", "refused", "bad_answer", "timeout"})


# ---------------------------------------------------------------------------
# The peer side — tickets, per server instance.
# ---------------------------------------------------------------------------

class TicketBook:
    """The tickets ONE server instance has minted and not yet seen redeemed.

    Keyed by the sha256 of the ticket, never the ticket itself: the book holds
    nothing that would let a reader of this process's memory forge a redeem.
    Bounded at `MAX_TICKETS`: a mint first purges the expired entries, then
    evicts the OLDEST live one (insertion order, which is expiry order under a
    constant TTL). A redeem is an atomic pop under the lock — two concurrent
    redeems of one ticket cannot both win.

    `clock` is an attribute read at CALL time, so a test can move it after the
    mint (conventions: nothing that can change is frozen at import)."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self.clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()
        self._expiry: dict[str, float] = {}

    @staticmethod
    def _key(ticket: str) -> str:
        return hashlib.sha256(ticket.encode("ascii")).hexdigest()

    def mint(self) -> str:
        ticket = secrets.token_urlsafe(_TICKET_BYTES)
        with self._lock:
            now = self.clock()
            for key in [k for k, expiry in self._expiry.items() if expiry <= now]:
                del self._expiry[key]
            while len(self._expiry) >= MAX_TICKETS:
                del self._expiry[next(iter(self._expiry))]
            self._expiry[self._key(ticket)] = now + TICKET_TTL_SECONDS
        return ticket

    def redeem(self, ticket: Any) -> bool:
        """True exactly once per minted, unexpired ticket; False otherwise."""
        if not isinstance(ticket, str) or not TICKET_RE.match(ticket):
            return False
        key = self._key(ticket)
        with self._lock:
            expiry = self._expiry.pop(key, None)
            now = self.clock()
        return expiry is not None and now < expiry

    def __len__(self) -> int:
        with self._lock:
            return len(self._expiry)


# ---------------------------------------------------------------------------
# The hub side — verify the peer, read its lock, ask it to mint.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PeerLock:
    """The three fields of a peer's lock this module uses. `token` is kept out
    of the repr, so a traceback or a debug print cannot show it."""
    pid: int
    port: int
    token: str = field(repr=False)


@dataclass(frozen=True)
class HandoffOutcome:
    """`error` is None on success, else `PEER_UNVERIFIED` or `PEER_MINT_FAILED`
    with `reason` in the matching closed vocabulary."""
    error: str | None
    reason: str | None
    port: int | None = None
    ticket: str | None = field(default=None, repr=False)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_lock(data: Any) -> PeerLock | None:
    """The SAME acceptance as `dashboard_daemon.read_lock` (SYM-00628): a dict
    carrying `pid` and `port` ints and a non-empty `token` string. Held equal
    to it by M12, so a lock the daemon trusts is a lock this module trusts."""
    if not isinstance(data, dict):
        return None
    if not all(k in data for k in ("pid", "port", "token")):
        return None
    if not isinstance(data["pid"], int) or not isinstance(data["port"], int):
        return None
    if not isinstance(data["token"], str) or not data["token"]:
        return None
    return PeerLock(pid=data["pid"], port=data["port"], token=data["token"])


def lock_path(project_root: Path) -> Path:
    return project_root.joinpath(*_LOCK_RELPATH)


def lock_health(project_root: Path) -> str:
    """The `otel` status this project's daemon lock advertises, or `"unknown"`
    — the `health.otel` of `/api/peer/summary`.

    MOVED HERE from `dashboard._lock_health` (T-01M4XKCTGEW9MDAYNCBK6R7SD9), body
    unchanged: it spelled the lock path a THIRD time, and this module is now
    the server's one reader of the lock (`lock_path`). Read STRAIGHT off the
    lock file rather than through `dashboard_daemon`: that module loads
    `dashboard.py`, so importing it back would close a cycle. The lock's shape
    is stable and this read is tolerant of every way it can be missing (no
    daemon, older lock, corrupt bytes) — deliberately WITHOUT the owner/mode
    checks of `read_peer_lock`: it reads this daemon's own lock, never a
    peer's, and hands out nothing but one status word."""
    path = lock_path(project_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    otel = data.get("otel")
    return otel if isinstance(otel, str) and otel else "unknown"


def read_peer_lock(project_root: Path) -> tuple[PeerLock | None, str | None]:
    """`(lock, None)` or `(None, reason)`, reason in `lock_unreadable` |
    `lock_foreign_owner`. Never raises.

    `lstat` first (a symlink is not a regular file), then `open` without
    following a link where the platform can say so, then `fstat` on the SAME
    descriptor — the identity of what was checked is the identity of what is
    read. Owner and mode are checked only where `os.getuid` exists."""
    path = lock_path(project_root)
    try:
        before = os.lstat(path)
    except (OSError, ValueError):
        return None, "lock_unreadable"
    if not stat.S_ISREG(before.st_mode):
        return None, "lock_unreadable"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None, "lock_unreadable"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (before.st_dev, before.st_ino):
            return None, "lock_unreadable"
        getuid = getattr(os, "getuid", None)
        if getuid is not None:
            if st.st_uid != getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                return None, "lock_foreign_owner"
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 8192)
            if not chunk:
                break
            total += len(chunk)
            if total > _LOCK_READ_LIMIT_BYTES:
                return None, "lock_unreadable"
            chunks.append(chunk)
    except OSError:
        return None, "lock_unreadable"
    finally:
        os.close(fd)
    try:
        data = json.loads(b"".join(chunks).decode("utf-8"))
    except ValueError:  # UnicodeDecodeError and JSONDecodeError both
        return None, "lock_unreadable"
    lock = parse_lock(data)
    return (lock, None) if lock is not None else (None, "lock_unreadable")


def _registry_root(raw: Any) -> Path | None:
    """The entry's `project_root` as a directory this module may look under, or
    None: a string, absolute, without a `..` segment, naming an existing
    directory. Only the registry supplies it — never the request."""
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return None
    root = Path(raw)
    if not root.is_absolute() or ".." in root.parts:
        return None
    try:
        return root if root.is_dir() else None
    except (OSError, ValueError):
        return None


def verify_peer(project_id: str, own_project_id: str | None) -> tuple[PeerLock | None, str | None]:
    """`(lock, None)` when the registry entry for `project_id` is the peer that
    holds that lock, else `(None, reason)` — see the module docstring for the
    chain. The probe and the pid check are `dashboard_registry`'s own, looked up
    at call time (a test injects the probe there)."""
    if project_id == own_project_id:
        return None, "self"
    registry, _state = _registry.read_registry_state()
    entry = None
    for key, candidate in registry["projects"].items():
        if key == project_id:
            entry = candidate
            break
    if not isinstance(entry, dict) or entry.get("project_id") != project_id:
        return None, "not_registered"
    pid = entry.get("pid")
    port = entry.get("port")
    if not _is_int(pid) or not _registry.pid_alive(pid):
        return None, "pid_dead"
    if not _is_int(port) or not 0 < port < 65536:
        return None, "probe_not_alive"
    verdict, _summary = _registry.probe_peer(port, project_id)
    if verdict != _registry.ALIVE:
        return None, "probe_not_alive"
    root = _registry_root(entry.get("project_root"))
    if root is None:
        return None, "lock_unreadable"
    lock, reason = read_peer_lock(root)
    if lock is None:
        return None, reason
    if lock.pid != pid or lock.port != port:
        return None, "lock_mismatch"
    return lock, None


def mint_on_peer(lock: PeerLock, timeout: float | None = None) -> tuple[str | None, str | None]:
    """`(ticket, None)` or `(None, reason)`, reason in `MINT_FAILURE_REASONS`.

    Sent to `127.0.0.1:<lock.port>` ONLY, through the registry's opener (no
    proxy, no redirect followed), and the final URL is re-checked. A 404 is
    `too_old`: a peer on older code has no mint route — and a peer whose token
    does not match answers the same uniform 404, so the two read alike on
    purpose. Never raises; never puts the token in what it returns."""
    url = f"http://127.0.0.1:{int(lock.port)}{MINT_PATH}"
    request = urllib.request.Request(url, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {lock.token}",
        "Content-Type": "application/json",
    })
    bound = timeout if timeout is not None else MINT_TIMEOUT_SECONDS
    try:
        with _registry._PROBE_OPENER.open(request, timeout=bound) as resp:
            if resp.status != 200 or not _registry._is_loopback_url(resp.geturl()):
                return None, "bad_answer"
            raw = resp.read(_MINT_READ_LIMIT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        return None, ("too_old" if code == 404 else "refused")
    except urllib.error.URLError as exc:
        return None, ("refused" if _registry._is_definitive_refusal(exc.reason) else "timeout")
    except OSError as exc:
        # `TimeoutError` ⊂ OSError; HTTPError ⊂ URLError ⊂ OSError precede it.
        return None, ("refused" if _registry._is_definitive_refusal(exc) else "timeout")
    except (ValueError, http.client.HTTPException):
        # HTTPException (BadStatusLine…) derives from neither OSError nor ValueError (critic-opus T1).
        return None, "bad_answer"
    if len(raw) > _MINT_READ_LIMIT_BYTES:
        return None, "bad_answer"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None, "bad_answer"
    if not isinstance(payload, dict) or payload.get("kind") != HANDOFF_TICKET_KIND:
        return None, "bad_answer"
    ticket = payload.get("ticket")
    if not isinstance(ticket, str) or not TICKET_RE.match(ticket):
        return None, "bad_answer"
    return ticket, None


def request_peer_handoff(project_id: str, own_project_id: str | None) -> HandoffOutcome:
    """The hub route's whole decision: verify, then mint. See the module
    docstring; `respond_peer_handoff` maps `PEER_UNVERIFIED` to 409,
    `PEER_MINT_FAILED` to 502 and success to 200."""
    lock, reason = verify_peer(project_id, own_project_id)
    if lock is None:
        return HandoffOutcome(error=PEER_UNVERIFIED, reason=reason)
    ticket, reason = mint_on_peer(lock)
    if ticket is None:
        return HandoffOutcome(error=PEER_MINT_FAILED, reason=reason)
    return HandoffOutcome(error=None, reason=None, port=lock.port, ticket=ticket)


# ---------------------------------------------------------------------------
# The three routes, driven from `dashboard.UIHandler`.
#
# THE SPLIT (file-length ratchet, 1600 lines per `.py`): `dashboard.py` keeps the
# two route TABLES — the source of truth of the route set, pinned by equality
# in the tests — and ONE dispatch line per route; everything the routes DO
# lives here. `dashboard.py` loads this module, never the reverse: what a route
# needs from the server is passed in — the HANDLER (its `headers`, its
# `server` with `server_address`, `token`, `handoff_tickets`, `last_activity`,
# and its `_reject`, `_respond_json`, `_check_token`, `_read_json_body`, the
# server's ONE implementation of each) and, for the hub route, the identity
# resolver.
#
# THE TABLES, and why there are two (T-01M4XKCTGEW9MDAYNCBK6R7SD9):
#
#   * `_ALLOWED_HANDOFF_PATHS` (GET `/api/handoff/redeem`) is the FIRST
#     token-exempt route that hands out a SECRET — the server's own session
#     token, against a single-use ticket it minted itself. The peer table's
#     rule ("an unauthenticated route is acceptable by the SIZE OF WHAT IT
#     SAYS") does not cover it: its guard is the ticket's entropy (256 bits),
#     single use and the 60 s TTL. Dispatched BEFORE `_ALLOWED_PEER_PATHS`,
#     which answers its summary to any member. It never stamps
#     `last_activity`: an exchange is not yet use, and the tab's first
#     authorised read stamps it.
#   * `_ALLOWED_HANDOFF_WRITE_PATHS` (POST `/api/peers/handoff`, `/api/handoff/
#     mint`), token REQUIRED, the same membership -> token flow as
#     `_ALLOWED_WRITE_PATHS` with the same uniform 404 for both unauthenticated
#     cases, but a table of their own: they write NO store and shell out to no
#     CLI (the mint inserts in this instance's memory, the hub route writes
#     nothing), so the write table's store doctrine stays true of every member
#     it has. A mint is an authorised write and stamps `last_activity`.
#
# THE HOST RULE, on these three routes only: exactly one `Host` header, equal to
# `127.0.0.1:<bound port>`, or the uniform 404 — a page reaching loopback under
# a rebound name (DNS rebinding) sends that name. Checked BEFORE the token.
# ---------------------------------------------------------------------------

HUB_PATH = "/api/peers/handoff"
REDEEM_PATH = "/api/handoff/redeem"
_LOOPBACK = "127.0.0.1"
# A `project_id` is a uuid4 in production; this bound only keeps an oversized
# request from being carried into a registry lookup.
PROJECT_ID_MAX_CHARS = 200


def host_is_own(handler: Any) -> bool:
    """True iff the request carries EXACTLY ONE `Host` header equal to
    `127.0.0.1:<the port the handler's server is bound to>`."""
    hosts = handler.headers.get_all("Host") or []
    if len(hosts) != 1:
        return False
    return hosts[0] == f"{_LOOPBACK}:{handler.server.server_address[1]}"


def respond_redeem(handler: Any) -> None:
    """`GET /api/handoff/redeem` — trade a ticket the handler's server minted
    for that server's session token.

    The ticket travels in `Authorization: Handoff <ticket>`, never in the URL.
    Every refusal — foreign Host, no ticket, unknown, already used, expired —
    is the uniform `404 not_found` of an unknown route, so the route cannot be
    told apart from absence without a valid ticket. The 200 is `no-store`.
    `last_activity` is NOT stamped (see the tables above)."""
    if not host_is_own(handler):
        handler._reject(404, "not_found")
        return
    auth = handler.headers.get("Authorization") or ""
    if not auth.startswith("Handoff "):
        handler._reject(404, "not_found")
        return
    book = getattr(handler.server, "handoff_tickets", None)
    token = getattr(handler.server, "token", None)
    if book is None or not token or not book.redeem(auth[len("Handoff "):]):
        handler._reject(404, "not_found")
        return
    handler._respond_json(200, {"kind": HANDOFF_SESSION_KIND, "token": token},
                          cache_control="no-store")


def route_write(handler: Any, path: str, resolve_identity: Callable[[Path], dict[str, Any]],
                identity_path: Callable[[], Path]) -> None:
    """POST on `_ALLOWED_HANDOFF_WRITE_PATHS` — `path` has passed that table's
    exact-match membership test in `dashboard.UIHandler._route_write`, which
    runs it BEFORE the write table's own and hands the request over whole.

    Host, THEN token, both refused with the uniform 404 of an unknown path
    (byte-identical bar `Date`); then the authorised-traffic stamp, the
    bounded body read (`_read_json_body`, which answers its own 411/413/400),
    and the route. The identity (`dashboard._resolve_identity_once` on
    `event_store.project_json_path()`, passed in so this module imports
    neither) is resolved by the hub route only."""
    if not host_is_own(handler) or not handler._check_token():
        handler._reject(404, "not_found")
        return
    handler.server.last_activity = time.monotonic()
    payload = handler._read_json_body()
    if payload is None:
        return  # `_read_json_body` has already answered
    if path == MINT_PATH:
        respond_mint(handler)
    elif path == HUB_PATH:
        respond_peer_handoff(handler, payload, resolve_identity(identity_path())["project_id"])
    else:  # unreachable while the table and these two constants agree (tested)
        handler._reject(404, "not_found")


def respond_mint(handler: Any) -> None:
    """`POST /api/handoff/mint` (Bearer: the peer's OWN token) — mint one
    single-use, 60 s ticket in the server's book. The caller is a hub daemon
    that read this daemon's lock; the body is read and bounded like every POST
    (`{}` is what `mint_on_peer` sends) and its content is ignored. Writes no
    store, starts nothing. `no-store`."""
    book = getattr(handler.server, "handoff_tickets", None)
    if book is None:
        handler._reject(404, "not_found")
        return
    handler._respond_json(200, {
        "kind": HANDOFF_TICKET_KIND,
        "ticket": book.mint(),
        "expires_in": TICKET_TTL_SECONDS,
    }, cache_control="no-store")


def respond_peer_handoff(handler: Any, payload: dict[str, Any], own_project_id: str | None) -> None:
    """`POST /api/peers/handoff {project_id}` (Bearer: the hub's token) —
    verify the registry's peer, read its lock HERE, ask it to mint, and hand
    `{port, ticket}` back. Token B never enters the response; the refusals are
    closed reason codes (`UNVERIFIED_REASONS` -> 409, `MINT_FAILURE_REASONS`
    -> 502), never a peer's body or a path. The `project_id` echoed by the 200
    is, by then, a registry key that passed `verify_peer`."""
    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id or len(project_id) > PROJECT_ID_MAX_CHARS:
        handler._reject(400, "bad_request")
        return
    outcome = request_peer_handoff(project_id, own_project_id)
    if outcome.error is not None:
        status = 409 if outcome.error == PEER_UNVERIFIED else 502
        handler._respond_json(status, {"error": outcome.error, "reason": outcome.reason},
                              cache_control="no-store")
        return
    handler._respond_json(200, {
        "api_version": HANDOFF_API_VERSION,
        "kind": PEER_HANDOFF_KIND,
        "project_id": project_id,
        "port": outcome.port,
        "ticket": outcome.ticket,
        "expires_in": TICKET_TTL_SECONDS,
    }, cache_control="no-store")
