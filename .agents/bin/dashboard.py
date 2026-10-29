#!/usr/bin/env python3
"""Dashboard UI/API server — server core + the frozen `/api/*` contract
(T-00000025 shard 1). stdlib only.

WHAT THIS SHARD IS, AND IS NOT: `docs/tasks/T-00000025.md` splits D3 into 4
shards. This module is shard 1 ONLY — `GET /api/snapshot`, `GET /api/events`,
and the security posture every `/api/*` route shares (that list grew to five
since: see the V1-d addendum at the end of this docstring — `_ALLOWED_UI_PATHS`
is the source of truth, never a prose enumeration). It deliberately does NOT
contain:
the daemon lifecycle / `state/local/dashboard.lock` (shard 2, behind a probe
gate), the `/dash` command or the `SessionStart` launch wiring (shard 2), or
the OTLP collector or canal-B normalisation/file-catch-up (shard 3 — the
receiver on 4318 is `otel_receiver.py`, shard 0, already landed).
`main()`/`serve_ui()` below are a dev-invocable entry point for THIS shard's
own tests and manual smoke checks, not the production launch path — that is
shard 2's job.

SHARD 4a ADDENDUM — STATIC UI SERVICE: the front-end files themselves live in
`.agents/ui/` (shard 4a for the shell/router/board, 4b for timeline/cost);
this module gained ONLY the handful of lines needed to hand them to a
browser (`_ALLOWED_STATIC_ROUTES`, `UIHandler._respond_static`). Two
properties of that addition are load-bearing:
  - the static routes are served WITHOUT a token, because a browser cannot
    attach an `Authorization` header to a top-level document navigation. The
    document is inert public shell code (no data, no secret); every byte of
    actual repo content still comes from `/api/*`, which stays token-only.
    The token reaches the page once, as the `?token=` of the entry URL
    printed by `dashboard_daemon.py --dash`, and `app.js` strips it from the
    address bar on boot.
  - static routing reuses the `/api/*` anti-traversal doctrine verbatim: a
    CLOSED dict, EXACT match on the raw un-normalised path, and — the part
    that matters most here, since this IS the module's only `open()` of a
    request-adjacent file — the on-disk path is built from the dict's own
    literal path segments joined onto the constant `_UI_DIR`, never from any
    byte of the URL. A request supplies a KEY to look up, never a path.
Static responses do NOT refresh `last_activity`: shard 2's idle watchdog
must age out on absence of AUTHORISED traffic, and an unauthenticated
document fetch is exactly the noise that rule excludes.

ROUTE SEPARATION (finding B3, same doctrine as `otel_receiver.py`): the OTLP
listener on 4318 is token-EXEMPT by necessity (every host hard-wires that
endpoint and sends no auth header). If the UI socket and the OTLP socket
ever shared a handler, `/api/snapshot` would become unauthenticated local
disclosure of board + ledger + specs. So `UIHandler` is a STANDALONE handler
class, on its own socket, sharing nothing with `OTLPHandler` — not even the
small request-body-drain helper (duplicated deliberately, see
`_drain_request_body` below). `_ExclusiveHTTPServer` (the bind-exclusivity
class — L-00000050: Windows SO_REUSEADDR lets a SECOND process bind the same
port, so `HTTPServer`'s default must never be inherited un-hardened) IS
reused from `otel_receiver.py`, per this shard's own instructions — it is
bind policy, not routing, and re-deriving it would risk exactly the
regression L-00000050 documents.

SECURITY POSTURE (non-negotiable, sheet :17 / design doc §B.2), enforced on
EVERY `/api/*` route, no exceptions:
  - bind `127.0.0.1` strict (inherited from `_ExclusiveHTTPServer`'s caller
    contract — this module never binds `0.0.0.0`);
  - a random `secrets.token_urlsafe` per launch, compared with
    `hmac.compare_digest` (`UIHandler._check_token`) — and returned by ONE
    exempt route only, against a single-use ticket (`dashboard_handoff.py`);
  - zero CORS headers, ever (including on every static response);
  - two verbs only: GET, and POST on the two POST tables ALONE (five routes,
    see `UIHandler`) — every other verb 404s on every route, `/api/*` and
    static alike, and any path outside the closed route tables 404s;
  - no request-derived path is ever opened, echoed, or reflected — `task=`
    / `kind=` / `agent=` / `since=` / `cursor=` are compared in memory
    against parsed JSON fields only, never joined into a filesystem path,
    never passed to `open()`. That list is EXHAUSTIVE for the whole `/api/*`
    surface: `/api/stream`, `/api/ping` and `/api/projects` accept NO query
    parameter at all, so they add zero request-derived input to this rule.
    Route matching itself is an EXACT string
    comparison against a closed set (`_ALLOWED_UI_PATHS`) on the untouched,
    un-normalised `urlsplit(self.path).path` — no `posixpath.normpath`, no
    percent-decoding step that could collapse a `..` into an accepted route.
    That absence of normalisation IS the traversal control: any of
    `/api/snapshot/../..`, `/api%2e%2e/snapshot`, `/api\\snapshot` fails the
    exact-match and 404s before auth is even checked.

CURSOR — the unit is a BYTE OFFSET PER FILE, not a line count. Chosen because
canal A is one-file-per-writer (`events.py`, L-00000041: `os.open(O_APPEND)`
is not atomic across processes on Windows) and files grow mid-session as new
writer pids appear. A byte offset lets a poll `seek()` straight to the last
read position and read only the new bytes (cost: O(new bytes) per poll,
independent of file size). A line-count unit would force re-reading a file
from byte 0 every poll just to count lines up to N (cost: O(file size) per
poll, growing without bound as a day-file accumulates) — strictly worse for
the exact access pattern (poll, read tail, remember position) this endpoint
exists for. The cursor is opaque to the client (base64 of a small JSON
object: `{"fp": <filters fingerprint>, "offsets": {filename: byte_offset}}`)
so the filter fingerprint travels WITH the offsets and the server can detect
a stale cursor structurally (see `_filters_fingerprint` / non-negotiable #4)
rather than trusting the caller's filter query to still match what the
cursor was issued for.

READ ONLY UP TO THE LAST NEWLINE (non-negotiable #2): a reader can observe a
line whose bytes have been written but whose trailing `"\n"` has not yet
landed (or vice versa, in-between the two facts on a filesystem that does
not guarantee single-write atomicity for the class of writer L-00000041
already found non-atomic). `_read_new_records` below reads from the stored
offset to EOF, finds the RIGHTMOST `b"\n"` in what it just read, and only
ever parses bytes up to and including that boundary — a trailing partial
line is left completely alone (not counted, not advanced past, not touched)
and is picked up whole on a later poll once its own writer finishes it. This
is provable, not assumed: `test_dashboard.py` writes a partial line with no
trailing newline, polls (asserts nothing new), then completes the line and
polls again (asserts exactly one well-formed record) — plus a
background-thread stress variant.

`compact()` INTERACTION (non-negotiable #3): `events.py --compact` deletes a
day-file once it has been folded into a monthly digest
(`state/events/digest/YYYY-MM.json`, counters only — `total_events`,
`by_kind`, `by_agent`, `by_task`; no timestamps, no tokens; see
`_read_digest_aggregates`). A cursor's `offsets` map can therefore reference
a filename that no longer exists. Every poll re-globs the events directory
(`_events_mod._events_dir()`) and any offset key not among the files
currently on disk is PRUNED and surfaced in the response's `pruned_files`
list — never silently dropped, never treated as an error. Pre-retention
history is exposed ONLY via `aggregates`, explicitly labelled as counts, and
is never merged into `events` (which stays raw per-record history) and
never used as a cost source (a digest has no token/cost fields to source
from in the first place).

CURSOR PRECEDENCE (non-negotiable #4): `cursor=` wins over `since=`
unconditionally whenever a cursor is supplied — including a cursor that
turns out to be stale (wrong filter fingerprint or malformed). A stale
cursor does not fall back to trusting `since`; it resets to a fresh cursor
(every referenced file's offset back to 0) for the CURRENT filters, and the
response says so (`cursor_reset` / `cursor_reset_reason`) rather than
silently guessing. Rationale: per-file byte offsets are filter-independent
counters of "how far this file has been read" — retaining them across a
filter CHANGE would silently hide matching history that arrived before the
old cursor's position, the exact failure this non-negotiable calls out.

SHARD 4b ADDENDUM — CANAL B IS NOW READ (`_read_canal_b`): the aggregates the
Coût view needs are computed here, THROUGH shard 3's normaliser
(`otel_normalize.iter_normalized_records` / `cost_summary_for_host`) — never a
second normalisation of the frozen schema, and NO new route: the payload of
`/api/snapshot` grew, the route table did not. Three measured properties of
the real data shape that section, documented at `_read_canal_b`'s own comment
block: `prompt_id` is unusable today (L-00000053 destroyed it), cost arrives
twice for the same spend (metric + log) and must never be summed, and
`agent.name` covers a minority of records. The `$`-estimate path ships
DISABLED because this repo declares no token rate table anywhere — an
invented rate would be the unlabelled figure the design doc forbids.

CANAL-B SCHEMA FREEZE (non-negotiable #7, review finding C6): the record
shapes below are declared here anyway,
verbatim as OBSERVED on real host emissions (not guessed), specifically so
shard 3 has a fixed contract to normalise against rather than inventing one
against a schema this sibling shard could still be revising. `prompt.id` is
called out separately because it is the canal-A join key (envelope field
`pid` in `events.py`'s schema — NOT the OS process id used for filenames,
see that module's own repeated warning about the name collision).

CROSS-PROJECT CAVEAT (non-negotiable #8, L-00000049): no host attaches a
project identifier to its OTLP payload, and port 4318 is machine-global
while this kit is provisioned per project. `build_snapshot()` always
surfaces this in `caveats`, unconditionally — not only once canal-B cost
data is actually wired (shard 3), because the structural limitation is true
today regardless of whether this shard renders any cost figure yet.

INDEX FRESHNESS (non-negotiable #9, L-029): this reader does not refresh
`CODEBASE_INDEX.md` — refreshing is a separate, deterministic, 0-LLM
pipeline step that runs BEFORE the reader, not a job the reader does for
itself. The response carries the index's own `built @ <sha>` / `updated`
header fields verbatim (reusing `build_index.py`'s own header-parsing
helpers rather than re-deriving the regex) so a caller can show staleness,
plus the coverage caveat — DERIVED from the builder's own effective scope
(`build_index.scope_caveat(host_skip_dirs(root))`), never restated here:
`.agents` is always excluded, and in a tree the builder detects as a
VENDORED kit `.claude`/`.codex`/`.gemini` are excluded at its root as well.
Coverage is over the PROJECT, not the kit.

T-00000026 SHARD A ADDENDUM — SSE + THE SIX D4 VIEWS. Two additions, and the
frozen contract is intact in the way that matters: `/api/stream` was the ONE
new route of that task and the six view sections added NO route at all — they
ride inside `/api/snapshot`'s payload under a single new `views` key, exactly as
canal B did in shard 4b. (The member COUNT that used to be quoted here is
deliberately gone: it went stale twice, at `/api/ping` and again at
`/api/projects`. `_ALLOWED_UI_PATHS` is the count.) Three properties are
load-bearing:
  - `/api/stream` is token-only like every other `/api/*` route, matched by
    the SAME exact-string rule on the raw un-normalised path, and sends
    `Content-Type: text/event-stream` + `Cache-Control: no-store` and no CORS
    header. It carries CHANGE NOTICES ONLY (`snapshot_changed` /
    `events_changed` / a `: keepalive` comment) — never repo data, so the
    stream is not a second, differently-shaped disclosure surface for the same
    content. Concurrency is BOUNDED (`_MAX_CONCURRENT_STREAMS`, 503 beyond);
    see that constant's own comment block for the thread lifetime, the
    `server_close()` interaction and why an open stream counts as authorised
    activity for shard 2's idle watchdog.
  - the tail-safe JSONL reader that WAS defined here is now
    `dashboard_readers.read_new_records`, aliased back as `_read_new_records`.
    Reason: this task's scope requires absorbing
    `sca-reports/audit-log.jsonl` into the unified readers "pas le dupliquer",
    and a second JSONL parser would have been a second place for
    non-negotiable #2 (read only up to the last newline) to rot. There is one
    implementation; the alias keeps every prior call site and test intact.
  - `_aggregate_canal_b` gained `by_event_name` / `by_metric_name` /
    `hosts_seen`, computed in the pass it already makes over the normalised
    records. The MCP view needs `mcp_server_connection` counts and the
    Couverture view needs a per-host signal census; both were already in
    `records`, so neither triggered a second read of `state/local/otel/`.

WINDOWS: this module has ZERO write routes and writes nothing to disk on
its own account (no lock file, no log file — that is shard 2's lock and
shard 3's `state/local/otel/*.jsonl`), so the `newline="\n"` precedent
(`tasks.py:171`) does not apply to any code path here. What DOES apply,
per L-00000048, is draining an unread request body before an early
rejection (401/404) so a still-open socket does not get an RST on close on
this platform — `_drain_request_body` mirrors `otel_receiver.py`'s helper,
duplicated rather than imported (see the route-separation note above: the
whole point of "separate handler class" is nothing shared, including this).

T-00000051 ADDENDUM (V1-d) — `/api/projects`. Token-only, GET-only, zero query
parameter, and the FIRST response in this
module to carry `Cache-Control: no-store` through `_respond_json`
(parameterised with an INERT default, so `/api/ping` and `/api/events` keep their
headers, `/api/snapshot` left for `dashboard_transport`; `/api/stream` writes its own; `_reject` sends
none). That header has since been reached for twice more, by `/api/peers`
(T-00000083) and `/api/sessions` (T-00000086), for the same reason each time: a
payload asserting what is true AT THIS INSTANT must not be cached. This
paragraph called the route "THE FIFTH AND LAST `/api/*` ROUTE OF v1" until
T-00000086 — it had been false since T-00000083 added a sixth, which is the
third time a member count written into this docstring went stale and precisely
why the count itself is not restated here. `_ALLOWED_UI_PATHS` is the count.
Two properties are load-bearing and both are tested:
  - ONE READ, ONE PARSE per route call. `_resolve_identity_once()` is the single
    identity-resolution path in this module for the attribution anchor, and
    `_read_canal_b` was REWRITTEN to consume it rather than calling
    `event_store.resolve_project_id()` beside it. The id itself comes from
    `event_store.project_id_from_data()` — one recipe, shared with
    `resolve_project_id()`, so the route and canal-B attribution cannot name two
    different projects from the same bytes.
  - `identity` is a CLOSED (status, cause) pair and `ok` ⟺ exactly one entry in
    `projects`. The full non-guarantee register (no project may exist, the list
    is not a machine census, no claim on 4318, no stable order, rejection
    headers, the badge anchor may differ — T-00000056 — and FRESHNESS) sits at
    `build_projects_response`'s own comment block, and the OPERATOR-FACING
    remedy lives in `docs/modules/dashboard-api.md`, never in a UI node: nothing
    actionable in this kit presumes the two anchors agree.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import http.server
import importlib.util
import json
import os
import re
import secrets
import select
import shutil
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Explicit-path module load (the convention of `test_otel_receiver.py` and `events.py`'s
    IMPORT CONTRACT), not a bare `import` that needs `sys.path[0]` to be this directory — true when
    this file runs directly, not for every caller (e.g. a hook feeding Python from stdin)."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_vendor_paths = _load_sibling("_dashboard_vendor_paths", "vendor_paths.py")  # T-01M5BXTGX5YN8XEXTG1PP7A5ZX D
with contextlib.suppress(_vendor_paths.PaquetIntrouvable):  # no `cadre` package: siblings' fallbacks, as before
    _vendor_paths.charger_paquet(HERE.parent.parent, "cadre")  # EXACT tree; stdlib never masked by `src/`
_otel_receiver = _load_sibling("_dashboard_otel_receiver", "otel_receiver.py")
_tasks_mod = _load_sibling("_dashboard_tasks", "tasks.py")
_ledger_mod = _load_sibling("_dashboard_ledger", "ledger.py")
_specs_mod = _load_sibling("_dashboard_specs", "specs.py")
_build_index_mod = _load_sibling("_dashboard_build_index", "build_index.py")
_events_mod = _load_sibling("_dashboard_events", "events.py")
# Shard 4b: canal-B normalisation belongs to shard 3's module. This reader
# CONSUMES it (`iter_normalized_records`, `cost_summary_for_host`) and
# re-derives none of it - the frozen schema has exactly one normaliser.
_otel_normalize_mod = _load_sibling("_dashboard_otel_normalize", "otel_normalize.py")
# T-00000026 shard A: the six D4 view readers, plus the ONE JSONL reader they
# now share with this module (see this file's own T-00000026 addendum below).
_readers_mod = _load_sibling("_dashboard_readers", "dashboard_readers.py")
# T-00000049 (V1-b): the SQLite projection of the spool. This module READS it and
# never writes it — the daemon's ingest thread is its sole writer. Loaded here
# rather than in `dashboard_daemon.py` so the HTTP routes and the ingest loop
# share ONE module instance (the `notify_dirty` doorbell would otherwise ring in
# a store nobody ticks).
_event_store_mod = _load_sibling("_dashboard_event_store", "event_store.py")
# T-00000083 (M1/M2): the machine-wide daemon registry. This module READS it
# (for `/api/peers`) and NEVER writes it — `dashboard_daemon.py` is its sole
# writer, at daemon start and stop. A GET that garbage-collected the registry
# would let a browser poll mutate machine-wide state.
_registry_mod = _load_sibling("_dashboard_registry", "dashboard_registry.py")
# T-00000087 (M5b): the console-mirror launcher. This module READS its spool
# (`/api/term`, `/api/term/stream`) and NEVER writes it — `wrap.py`'s own output
# loop is its sole writer, one process per mirrored session. Loaded here rather
# than re-deriving the paths so the spool directory, the meta parser and the
# liveness probe have exactly ONE recipe: two literals that "obviously" resolve
# to the same file is the L-00000057 false-anchor shape, and a second copy of
# the pid probe would be worse still (on Windows `os.kill(pid, 0)` TERMINATES
# what it probes — see `wrap.pid_alive`).
_wrap_mod = _load_sibling("_dashboard_wrap", "wrap.py")
# T-01M4XKCTGEW9MDAYNCBK6R7SD9: the access handoff (loads the registry, never the daemon).
_handoff_mod = _load_sibling("_dashboard_handoff", "dashboard_handoff.py")
# T-01M4XR9ESWKJ8G545AJBJQNC7Q: `/api/snapshot`'s transport — one build per key, body + gzip memoised, ETag/304.
_transport_mod = _load_sibling("_dashboard_transport", "dashboard_transport.py")
_routes_mod = _load_sibling("_dashboard_routes_etat", "dashboard_routes_etat.py")  # T-01M51Q7GJ1 lot D: journaux
_canal_b_mod = _load_sibling("_dashboard_canal_b", "dashboard_canal_b.py")  # T-01M5T5G6MR: borne, date, incrément
# `dashboard_transport` reads THIS module's handles (a second `event_store` counts 0); "vivant": shown LIVE, per send.
_SNAPSHOT_SOURCES: dict[str, Any] = {
    "store_fingerprint": lambda: _store_fingerprint(), "events_dir": lambda: _resolved_events_dir(),
    "otel_dir": lambda: _resolved_otel_dir(), "ingestion": lambda: _read_ingestion_status(),
    "inputs": _readers_mod.snapshot_fingerprint, "identity_path": lambda: _event_store_mod.project_json_path(),
    "dropped_foreign": lambda: _transport_mod.rejets_etrangers(_event_store_mod),
    "canal_b": lambda: _canal_b_mod.jeton(),
    "vivant": {("generated_at",): lambda: _now_iso(), ("ingestion",): lambda: _read_ingestion_status()}}

# Reused, not re-derived (per this shard's own instructions) — the
# bind-exclusivity policy (L-00000050) belongs to shard 0.
_ExclusiveHTTPServer = _otel_receiver._ExclusiveHTTPServer

# ---------------------------------------------------------------------------
# Bind target — UI/API socket, distinct from the OTLP socket (4318, owned by
# otel_receiver.py). Design doc §B.2 / risk table: "port ephemere + lock dans
# state/local/" — the lock file itself is shard 2; this shard defaults to
# port 0 (OS-assigned) so a caller (a test, or shard 2's lock writer) reads
# the ACTUAL bound port off the server object rather than this module
# guessing a fixed number that could collide across two provisioned
# projects on one machine.
# ---------------------------------------------------------------------------

_UI_HOST = "127.0.0.1"
_UI_PORT_DEFAULT = 0

_ALLOWED_UI_PATHS: frozenset[str] = frozenset(
    {"/api/snapshot", "/api/events", "/api/stream", "/api/ping", "/api/projects",
     "/api/peers", "/api/sessions", "/api/term", "/api/term/stream"}
    | _routes_mod.ROUTES)  # T-01M51Q7GJ1 lot D: `/api/specs`, `/api/lecons`, `/api/recherche` (dashboard_routes_etat)

# T-00000083 — the THIRD route table, and the second token-EXEMPT one (the
# static shell being the first). A route here is answered WITHOUT an
# Authorization header, because its consumer is ANOTHER PROJECT'S DAEMON, which
# by construction cannot hold this daemon's token: publishing that token in the
# machine-wide registry so peers could authenticate is exactly what L-00000112
# forbids (it would hand every project on the box full read access to this
# one's ~166 KB snapshot).
#
# What makes an unauthenticated route acceptable is the SIZE OF WHAT IT SAYS,
# so this table is CLOSED and stays at one entry: `/api/peer/summary` answers
# "who am I, what am I working on, am I healthy" — the identity `/api/projects`
# already publishes, plus one board line. No ledger, no specs, no costs, no
# file paths, no token. Anything richer belongs behind the token. (The one
# exempt route that RETURNS a secret has its own table: `_ALLOWED_HANDOFF_PATHS`.)
_ALLOWED_PEER_PATHS: frozenset[str] = frozenset({"/api/peer/summary"})

# ---------------------------------------------------------------------------
# T-00000028 — the FOURTH route table, and the first one that WRITES.
#
# Until this task every table on this server was read-only and `do_POST` was a
# flat 404: "GET is the only verb" was the contract, asserted by
# `test_the_api_route_set_stays_closed_and_small`. That contract is REOPENED
# here, deliberately and narrowly, and the tests that pinned it are amended by
# name rather than deleted — a guard that disappears in a diff is a guard
# nobody re-argues.
#
# What justifies reopening it: `gate.approval` has been a DECLARED canal-A kind
# with NO emitter since D4 (`dashboard_readers._approvals_unavailable` says so
# in its own `reason` string, and names this task). A human approving a plan in
# a console leaves no machine trace, so the governance view could only ever show
# a blind spot. These routes create that trace — and nothing more (C1 of the
# approved plan): the UI produces an ATTRIBUTED CAPTURE of a decision, never a
# pipeline resume. No route here starts an agent, and none ever will.
#
# The four properties that make a write route acceptable on this server, all
# enforced below in `do_POST` and asserted in the tests:
#
#   1. CLOSED TABLE, EXACT-STRING ROUTING. Same posture as `_route`: the raw
#      path, never normalised, never percent-decoded, compared by equality.
#      Everything else 404s — including every path that merely resembles one of
#      these three.
#   2. TOKEN REQUIRED, no exemption, ever. The token-exempt tables exist for
#      consumers that cannot hold the token (a document navigation, a peer
#      daemon, a tab trading a handoff ticket); none of those ever writes, so
#      the exemption has no reason to exist here and its absence is the boundary.
#   3. BOUNDED BODY. `_DRAIN_LIMIT_BYTES`, the same bound the reject-drain uses,
#      applied to the DECLARED length before a byte is read.
#   4. NO CORS, still — not one header, on any response. Combined with a token
#      the browser must attach by hand, that is what makes a cross-site POST
#      from a page the user happens to have open a non-event: it cannot read the
#      token, and the request it could forge carries no Authorization at all.
#
# THE SERVER NEVER WRITES A STORE OF ITS OWN (C2). Every route here shells out
# to the CLI that already owns the file — `specs.py`, `tasks.py`, `waivers.py`
# — through `_run_cli`. That is not indirection for its own sake: `tasks.py`
# holds the state transitions and the never-reused id allocation, and a
# second writer would have to re-implement both correctly, forever. (The two
# handoff POSTs share this FLOW, not this table: they write no store — below.)
# ---------------------------------------------------------------------------

_ALLOWED_WRITE_PATHS: frozenset[str] = frozenset(
    {"/api/actions/gate", "/api/actions/board", "/api/actions/waiver"}
)

# T-01M4XKCTGEW9MDAYNCBK6R7SD9 — 5th and 6th tables (access handoff): `dashboard_handoff.py` § "The three routes".
_ALLOWED_HANDOFF_PATHS: frozenset[str] = frozenset({"/api/handoff/redeem"})
_ALLOWED_HANDOFF_WRITE_PATHS: frozenset[str] = frozenset({"/api/peers/handoff", "/api/handoff/mint"})

# Wall-clock bound on any CLI this server spawns. Generous for a store write
# (these CLIs read a small JSON, append, rewrite) and short enough that a wedged
# subprocess cannot pin a handler thread for the length of a session. A breach
# is a 504 with the bound named, never a hang and never a silent kill.
_ACTION_CLI_TIMEOUT = 20.0

# The commit hook is a git operation on three files; it gets its own, larger
# bound because a cold `git commit` on Windows is measurably slower than a JSON
# rewrite, and a timeout here degrades the RESPONSE rather than failing the
# board write that already succeeded.
_ACTION_HOOK_TIMEOUT = 60.0

# How much of a failed CLI's stderr travels back in the response. Enough to name
# the refusal ("tasks.py: unknown task T-00000999"), never enough to make an
# error path a data-exfiltration path.
_CLI_EXCERPT_CHARS = 400

# Closed vocabularies for the write routes. Each one is the reason a malformed
# request is a 400 here instead of a confusing rc=2 from a CLI three layers
# down.
_BOARD_ACTIONS: frozenset[str] = frozenset({"start", "block", "unblock", "done"})
# `gate.approval`'s `decision` field is free text in `events.py`'s allowlist —
# closed HERE, because a governance view that counts decisions cannot count a
# vocabulary that grows by typo.
_GATE_DECISIONS: frozenset[str] = frozenset({"approved", "rejected", "changes_requested"})

_TASK_ID_RE = re.compile(r"\AT-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{1,12})\Z")
_SPECS_ID_RE = re.compile(r"\AS-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{1,12})\Z")

# Free text reaching a tracked store through this server: a board note, a
# waiver field. Bounded HERE as well as in the CLI - the CLI's bound protects
# the file, this one keeps an oversized request from being carried three
# processes deep before anyone refuses it.
_ACTION_TEXT_CHARS = 200

# The plan re-read that gets hashed. See `_run_cli`'s `stdout_limit`.
_PLAN_READ_CHARS = 100_000

# The one sentence this server is allowed to say about what it did NOT do.
# Repeated in every gate response on purpose (C1 / complement A): a UI that
# records an approval and stays silent about the resume is a UI that reads as
# having resumed.
_GATE_NO_RESUME = (
    "decision recorded and attributed here; resuming the pipeline stays a "
    "console gesture — this route starts nothing"
)

# ---------------------------------------------------------------------------
# SSE (`/api/stream`) — T-00000026 shard A. Design doc §B.2: "un thread qui
# poll les mtime toutes les 500 ms. Pas de watchdog, pas d'asyncio."
#
# THE POLL THREAD *IS* THE HANDLER THREAD. `UIHTTPServer` is a
# ThreadingMixIn server, so every connection already owns a thread; spawning a
# second one per stream would only add a lifetime to manage and a way to
# outlive its socket. The consequence that makes this safe is deliberate: the
# loop's only exit conditions are (a) `_client_gone()` — an EOF peek on the
# socket, checked EVERY tick — (b) a write that fails, the backstop for a peer
# that vanished without a FIN, (c) `stream_stop`, set by
# `UIHTTPServer.server_close()` before it closes anything, and (d)
# `_STREAM_MAX_SECONDS`. So a stream can neither impede `server_close()` nor
# survive it, and a closed tab frees its slot in ≤ one poll interval rather
# than waiting up to a heartbeat for a write to fail.
#
# BOUNDED, not unlimited: `_MAX_CONCURRENT_STREAMS` slots, and the 4th+1st
# request gets a 503 with `Retry-After` rather than a thread. A browser tab
# opens one EventSource; four is generous for a loopback single-user tool and
# it leaves the ThreadingMixIn free for the ordinary polls.
#
# SSE COUNTS AS AUTHORISED ACTIVITY: `dashboard_daemon`'s idle watchdog reads
# `httpd.last_activity` and auto-stops after `--idle-hours` without it. A human
# with the dashboard open is USING it even while clicking nothing, so every
# successful write on a stream (event or keepalive) restamps `last_activity`.
# The converse is what makes that safe: a closed tab stops absorbing writes,
# the next keepalive fails, the thread exits, and the daemon ages out normally.
#
# The heartbeat is an SSE COMMENT (`: keepalive`), not an event: a comment is
# ignored by `EventSource` yet still traverses every proxy and still fails on a
# dead socket, which is exactly the "client detects a cut" property wanted
# without inventing a data shape the UI has to filter.
# ---------------------------------------------------------------------------

_MAX_CONCURRENT_STREAMS = 4
_STREAM_POLL_SECONDS = 0.5
_STREAM_HEARTBEAT_SECONDS = 15.0
# Client-side reconnect delay advertised via the SSE `retry:` field.
_STREAM_RETRY_MS = 3000
# A stream is closed cleanly after this long so no handler thread can wedge
# forever on a half-open socket the OS never reports as dead; the client
# reconnects on its own via `retry:`.
_STREAM_MAX_SECONDS = 3600.0

_stream_lock = threading.Lock()
_stream_slots_used = 0


def _acquire_stream_slot() -> bool:
    global _stream_slots_used
    with _stream_lock:
        if _stream_slots_used >= _MAX_CONCURRENT_STREAMS:
            return False
        _stream_slots_used += 1
        return True


def _release_stream_slot() -> None:
    global _stream_slots_used
    with _stream_lock:
        _stream_slots_used = max(0, _stream_slots_used - 1)


def active_stream_count() -> int:
    """Live slot count — the observable a test uses to prove a disconnected
    client's thread actually died rather than lingering."""
    with _stream_lock:
        return _stream_slots_used


# ---------------------------------------------------------------------------
# /api/term/stream — the console MIRROR (T-00000087, M5b). A second SSE family,
# reusing the transport above and NOTHING of its accounting.
#
# A SEPARATE SLOT COUNTER, AND THAT IS THE POINT. A mirror is a long-lived
# stream that pushes real payload, not a change notice; if it drew from
# `_MAX_CONCURRENT_STREAMS` then opening two terminals would leave two slots for
# every OTHER tab's change notices, and the dashboard would silently stop
# refreshing itself. Two counters, two limits, two 503s: a saturated mirror can
# never starve the notices, and vice versa. `_MAX_TERM_STREAMS = 2` because a
# human watches one console at a time and two is already a comparison.
#
# WHAT IT CARRIES, and the two frame kinds it is allowed to carry:
#   {"kind":"term","b64":…}                base64 of raw spool bytes. Base64 and
#                                          not text: the payload is an ANSI byte
#                                          stream that is NOT guaranteed to be
#                                          valid UTF-8 mid-chunk, and JSON has no
#                                          way to carry a lone continuation byte.
#   {"kind":"term_gap","reason":…}         bytes were SKIPPED, and why —
#                                          "catchup" (joined mid-session),
#                                          "lag" (the reader fell behind the
#                                          per-tick cap), "rotation" (the ring
#                                          rolled), "expired" (the deadline).
# A gap is announced rather than silently spliced: a terminal is a state machine
# driven by escape sequences, and quietly dropping a run of bytes produces a
# plausible-looking screen that never existed.
#
# THE READER HOLDS NO HANDLE BETWEEN TICKS. Open, seek, read, close — every
# 500 ms. That is not tidiness: `wrap.py`'s ring rotation ends in an
# `os.replace`, and on Windows a handle held across the swap makes the writer's
# bounded retry fail and the rotation get abandoned. A daemon that kept a file
# open would degrade the WRITER, from another process, invisibly.
# ---------------------------------------------------------------------------

TERM_API_VERSION = 1
TERM_KIND = "agentkit.term"

_MAX_TERM_STREAMS = 2
# Catch-up handed to a client on connection. 256 KiB is far more than any
# viewport shows and small enough to render in one frame; anything older is a
# declared gap, never a silent one.
_TERM_CATCHUP_BYTES = 256 * 1024
# Per-tick ceiling. A burst bigger than this is skipped forward to the newest
# bytes with a `lag` gap — a mirror that is 30 s behind is worse than one that
# says it jumped.
_TERM_MAX_TICK_BYTES = 64 * 1024
# The listing is bounded like every other reader in this file.
_TERM_MAX_SESSIONS = 50
# A sid is a filename component. ANCHORED and narrow: `wrap.py` builds it as
# `<utc-timestamp>-<pid>`, so letters, digits and hyphens is the complete
# alphabet. This is what keeps a request byte out of `open()` on the one route
# of this server that takes a path-shaped parameter.
_TERM_SID_RE = re.compile(r"^[A-Za-z0-9-]{1,80}$")

_term_stream_lock = threading.Lock()
_term_slots_used = 0


def _acquire_term_slot() -> bool:
    global _term_slots_used
    with _term_stream_lock:
        if _term_slots_used >= _MAX_TERM_STREAMS:
            return False
        _term_slots_used += 1
        return True


def _release_term_slot() -> None:
    global _term_slots_used
    with _term_stream_lock:
        _term_slots_used = max(0, _term_slots_used - 1)


def active_term_stream_count() -> int:
    """Live MIRROR slot count. Deliberately a second function rather than a
    parameter on `active_stream_count()`: a test that proves the two limits are
    independent has to be able to read them independently."""
    with _term_stream_lock:
        return _term_slots_used

# ---------------------------------------------------------------------------
# Static UI service (shard 4a). The UI directory is a CONSTANT derived from
# this file's own location — `.agents/bin/dashboard.py` -> `.agents/ui` — and
# is never influenced by a request.
#
# `_ALLOWED_STATIC_ROUTES` is CLOSED, exactly like `_ALLOWED_UI_PATHS`, and
# matched the same way: exact string comparison on the raw, un-normalised
# `urlsplit(self.path).path`. The value carries the on-disk location as a
# TUPLE OF LITERAL PATH SEGMENTS, not a string to be parsed: `_UI_DIR` is
# joined with those literals only, so no request byte can reach `open()`.
# A route absent from this table 404s before anything is read, which is what
# makes `/../ui/x`, `/views/../api/snapshot` and `/%2e%2e/` non-events rather
# than traversal candidates.
#
# Deliberately NOT routes: `/index.html` (one canonical URL for the shell,
# `/`), `/favicon.ico` (a 404 for it is correct and costs a browser nothing),
# and anything under `/api/` (the two tables must never overlap — asserted in
# test_dashboard.py).
# ---------------------------------------------------------------------------

_UI_DIR = HERE.parent / "ui"


def served_code_fingerprint() -> str:
    """Digest of the code this PROCESS would serve — the route table plus the
    mtime/size of every file it points at, and of the two server modules
    themselves.

    Why (T-00000040, found the hard way): a daemon holds its route table in
    memory. After a kit upgrade adds front-end modules, an already-running
    daemon 404s them; `app.js` imports them, the ESM graph dies, and the user
    sees a blank page with no error anywhere — while `/dash` happily returns
    the existing URL because the lock is alive and the ping answers. The lock
    records this digest at launch so `--status` can compare it to the digest
    of the code on disk NOW and say plainly "restart me", instead of leaving
    a silent, self-confident stale daemon."""
    parts = [",".join(sorted(_ALLOWED_STATIC_ROUTES))]
    targets = [_UI_DIR.joinpath(*segs) for segs, _ct in _ALLOWED_STATIC_ROUTES.values()]
    # `dashboard_registry.py` joined the list in T-00000083: it is served code
    # like the other three (it decides what `/api/peers` says and what the
    # daemon publishes about itself), and a daemon running an older copy of it
    # must read as STALE rather than as merely alive.
    # `wrap.py` joined the list in T-00000087 for the same reason
    # `dashboard_registry.py` did: this process has it LOADED, and it decides
    # where the mirror spool lives, how a meta is parsed and whether a pid is
    # alive. A daemon running an older copy answers `/api/term` differently and
    # must read as STALE rather than as merely alive. So do `event_store.py` and `events.py`
    # (T-00000615, binôme octies): they decide what is ingested and the key every memo reads.
    targets += [HERE / "dashboard.py", HERE / "dashboard_readers.py", HERE / "dashboard_daemon.py",
                HERE / "dashboard_registry.py", HERE / "wrap.py", HERE / "event_store.py", HERE / "events.py",
                HERE / "dashboard_handoff.py",  # T-01M4XKCTGEW9MDAYNCBK6R7SD9: it decides whom a token goes to
                HERE / "dashboard_transport.py",  # T-01M4XR9ESWKJ8G545AJBJQNC7Q: it decides when a body is rebuilt
                HERE / "dashboard_routes_etat.py", HERE / "etat_projection.py"]  # lot D: what the journal routes say
    # T-00001051: the five parts of the `dashboard_readers.py` façade (its closed `PARTIES` list) are served code
    # like the façade itself — a daemon running an older copy of one of them must read as STALE, never as `current`.
    targets += [HERE / name for name in _readers_mod.PARTIES]
    for path in sorted(targets, key=str):
        try:
            st = path.stat()
            parts.append(f"{path.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path.name}:absent")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


_CT_HTML = "text/html; charset=utf-8"
_CT_CSS = "text/css; charset=utf-8"
_CT_JS = "text/javascript; charset=utf-8"
# T-00000080: the only BINARY content type served. No charset — a charset on a
# binary type is meaningless, and it is the marker `_TEXT_ROUTES` uses to tell
# the font files apart from everything else in the route table.
_CT_WOFF2 = "font/woff2"


def _is_text_route(content_type: str) -> bool:
    """Whether a static route's bytes are meant to be read as UTF-8 text.

    A `charset=` parameter is precisely the declaration that a payload is text,
    so that is the discriminator rather than a list of file extensions someone
    has to remember to extend. Every audit that greps the served bundle — no
    remote references, no innerHTML, no inline styles, no token in a URL —
    iterates the text routes through this, so adding a binary asset cannot
    silently break them (T-00000080).
    """
    return "charset=" in content_type

_ALLOWED_STATIC_ROUTES: dict[str, tuple[tuple[str, ...], str]] = {
    "/": (("index.html",), _CT_HTML),
    # THE BUNDLE IS BUILT, AND ITS FILENAMES ARE FROZEN ON PURPOSE.
    #
    # `.agents/ui/` is no longer hand-written ES modules: it is the OUTPUT of
    # `.agents/ui-src/` (React + Vite, `npm run build`). That replaced sixteen
    # module routes with two, and the two are only safe because the build is
    # configured NOT to hash them (`vite.config.js`, `rollupOptions.output`):
    # this table is CLOSED, so a content hash would rename the bundle on every
    # build and 404 it until someone remembered to edit this dict.
    #
    # The source tree is deliberately NOT a route. `.agents/ui-src/` holds JSX,
    # `node_modules/` and a config; none of it is servable and serving any of it
    # would widen the read surface for zero user-facing benefit — the same
    # reasoning that kept `selftest.mjs` out of this table.
    "/assets/app.js": (("assets", "app.js"), _CT_JS),
    "/assets/app.css": (("assets", "app.css"), _CT_CSS),
    # Self-hosted maquette typography (T-00000080). Enumerated one by one like
    # every other asset: the route table is CLOSED by design, so a directory
    # rule for `/fonts/*` would reintroduce exactly the path-derived-from-the-
    # request that this server refuses to have.
    # T-00001243 (S-00004649): Geist + Geist Mono, VARIABLE (weights 100-900),
    # npm `geist` 1.7.2, SIL OFL 1.1. `fonts/OFL-Geist.txt` ships beside them and
    # is NOT a route: a text no browser asks for stays off the read surface.
    "/fonts/geist-variable.woff2": (("fonts", "geist-variable.woff2"), _CT_WOFF2),
    "/fonts/geistmono-variable.woff2": (("fonts", "geistmono-variable.woff2"), _CT_WOFF2),
    # The sixteen hand-written module routes that used to sit here (`/app.js`,
    # `/router.js`, `/api.js`, `/dom.js`, `/svg.js`, `/stream.js`,
    # `/project.js`, `/styles.css` and the nine `/views/*.js`) are GONE: the
    # bundler emits one script and one stylesheet, both declared above.
    # `served_code_fingerprint()` needed no change — its targets derive from
    # `_ALLOWED_STATIC_ROUTES.values()`, so the new routes enrol themselves.
}
_EMPREINTE_CODE = served_code_fingerprint()  # lot D: the code THIS process serves, taken ONCE, in the routes' ETag

# The session token changes at every launch and the shell reads it from the
# entry URL, so a cached document is a document holding a dead token: never
# store a static response.
_STATIC_CACHE_CONTROL = "no-store"

# Belt to the "zero CDN, zero remote font" rule of design doc §B.3: the
# document declares mechanically that it may only load code from its own
# origin, so a future edit that pastes in a CDN <script> fails in the browser
# instead of silently shipping a remote dependency.
#
# TIGHTENED IN SHARD 4b: shard 4a kept `'unsafe-inline'` in `style-src` in
# anticipation of computed bar widths. The graphs landed as hand-written SVG
# whose geometry is set with ATTRIBUTES (`createElementNS` + `setAttribute`),
# not with style attributes, so nothing in the shipped bundle needs inline
# styles and the allowance is gone. `test_ui_never_uses_inline_styles` keeps
# that honest — reintroducing a `.style.x =` assignment now fails a test
# rather than silently relying on a loosened policy.
_STATIC_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

# Same bound as otel_receiver.py's own drain limit, for the same reason
# (L-00000048) — deliberately NOT imported, see module docstring.
_DRAIN_LIMIT_BYTES = 65536

# A page of raw events per /api/events call. Deliberately small and fixed
# (not yet a query parameter — the task's contract is
# `?task=&kind=&agent=&since=&cursor=`, nothing more, for this shard).
_EVENTS_PAGE_LIMIT = 200


# ---------------------------------------------------------------------------
# Canal-B normalised record schema (non-negotiable #7 / review finding C6) —
# FROZEN HERE for shard 3 to normalise against. This shard does not read canal
# B (state/local/otel/) at all; this constant is a contract declaration only.
#
# TWO EPISTEMIC GRADES (T-00000073, C8): the entries carry field names of two
# provenances, and the constant no longer claims a single one.
#   - OBSERVED: cost.usage / token.usage / api_request / subagent_completed /
#     tool_decision field names were seen on real host emissions during this
#     task's own review, not guessed.
#   - VENDOR-DOCUMENTED: the 2 metrics added for T-00000073
#     (`lines_of_code.count`, `code_edit_tool.decision`) carry attribute names
#     taken from Claude Code's published telemetry docs, NOT yet observed in a
#     real capture (no such dataPoint exists in the Gate A fixture). They are
#     marked inline so a reader never mistakes a documented name for a measured
#     one — the honest form of "frozen against a schema".
# ---------------------------------------------------------------------------

CANAL_B_RECORD_SCHEMA: dict[str, Any] = {
    "_contract": (
        "Declared in dashboard.py (T-00000025 shard 1, review finding C6) so "
        "shard 3's OTLP normalisation has a fixed target instead of inventing "
        "one against a schema a sibling shard could still be revising."
    ),
    "join_key": (
        "prompt.id is the canal-A join key (it matches events.py's envelope "
        "field `pid` — a prompt id, NOT the OS process id events.py also uses "
        "in its filenames). CORRECTED against measurement: it is NOT on every "
        "log record. Counted over the 49 real GATE-A captures it is on 100% of "
        "the per-turn events a join actually needs (api_request, "
        "assistant_response, tool_decision, tool_result, subagent_completed, "
        "user_prompt) and ABSENT from session-lifecycle events "
        "(hook_registered 0/66, plugin_loaded 0/24, hook_execution_* 18/20, "
        "mcp_server_connection 2/5). A normaliser must leave prompt_id None "
        "there, never fabricate one. Second correction, worse: our own "
        "redaction destroyed this value on all 49 captures because the "
        "drop-list matched the substring `prompt` (L-00000053) — the key was "
        "present while its value read REDACTED, so 'the join key exists' was "
        "true of the key and false of the data. Now exempted by exact key in "
        "otel_receiver._JOIN_KEY_EXEMPT."
    ),
    # `type` deliberately absent here: measured 0/14 on real cost.usage
    # dataPoints versus 56/56 on token.usage. cost.usage is one dollar total
    # per request and structurally cannot carry a per-token-type breakdown.
    # `session.id` (T-00000096): the per-session join key — present on every
    # real cost/token dataPoint, survives redaction, and is what lets the Coût
    # view show the figure Claude Code itself displays instead of only the
    # 30-day project total. Kept IN SYNC BY HAND with
    # `otel_normalize._SCHEMA_FIELDS`, like the rest of this constant.
    "claude_code.cost.usage": ["agent.name", "model", "effort", "query_source", "session.id"],
    # NOTE: this short key `token.usage` is a PRE-EXISTING divergence from
    # otel_normalize._SCHEMA_FIELDS, which keys the same family by its FULL name
    # `claude_code.token.usage`. Out of T-00000073's scope; left as-is (C7).
    "token.usage": ["agent.name", "model", "effort", "query_source", "type", "session.id"],
    # T-00000073 — VENDOR-DOCUMENTED (see the two-grade header above), full
    # names to match otel_normalize._SCHEMA_FIELDS. Fields documented from
    # Claude Code telemetry docs, NOT observed on a real emission in this repo.
    "claude_code.lines_of_code.count": ["type"],  # documented, not observed
    "claude_code.code_edit_tool.decision": ["decision", "tool_name", "language"],  # documented, not observed
    "api_request": [
        "cost_usd", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens", "duration_ms",
    ],
    "subagent_completed": ["agent_type", "total_tokens", "total_tool_uses", "duration_ms"],
    "tool_decision": ["decision", "source"],
}

_CROSS_PROJECT_CAVEAT = (
    "canal_b_attribution: port 4318 is machine-global while this kit is "
    "provisioned per project, so a neighbouring project's session can reach "
    "this collector (L-00000049). Since V1-c every canal-B record carries a "
    "first-level `project_id` — the id declared via "
    "OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=... , or the literal "
    "sentinel 'unattributed' when the host declares nothing (Codex is "
    "structurally inattributable; so is any host whose env block the operator "
    "has not pasted yet). A record declaring ANOTHER project's id is refused "
    "at the receiver, and one already in the database is HELD in quarantine "
    "and excluded from the monetary totals. So the totals below are 'this "
    "project + what could not be attributed', never 'this machine'."
)

_BACKFILL_CAVEAT = (
    "canal_b_attributed_by_backfill: rows counted under "
    "`attributed_by_backfill` were attributed by INFERENCE, not by "
    "declaration — a one-shot pre-V1-c pass matched the line's recorded "
    "provenance path against this repo's current root. A pre-V1-c line whose "
    "path no longer matches (moved clone, renamed repo) carries the "
    "'unattributed' sentinel instead: inside the census and the labelled "
    "totals, never silently dropped and never claimed as declared."
)

_COST_TRUNCATION_CAVEAT = (
    "canal_b_cost_truncated_30d: the monthly digests carry COUNTS ONLY (no "
    "cost/token sums, no provenance dimension), so this cost view covers the "
    "30-day retention window and nothing before it. TEMPORARY AND DISPLAYED, "
    "not a property of the design — extending the digests is T-00000054. An "
    "expired quarantined row therefore leaves a count "
    "(`foreign_held_expired`) and no trace of what it cost."
)

_INDEX_CAVEAT_HEAD = (
    "This endpoint does not refresh the index (L-029: refresh happens "
    "before the reader, via the deterministic build_index.py --if-stale "
    "step, never after — inside this reader). "
)


def _index_caveat(project_root: Path | None = None) -> str:
    """The index-coverage caveat, DERIVED from the builder's effective scope for
    the tree being read (T-00000062) instead of hardcoding one scope here.

    A vendored kit also drops `.claude`/`.codex`/`.gemini` at its root, so a fixed
    sentence naming only `.agents` would understate the limit on exactly the trees
    where it is widest. `.agents` alone is the honest fallback: that exclusion is
    unconditional (L-020).
    """
    try:
        host_skip = _build_index_mod.host_skip_dirs(project_root or _project_root())
        tail = _build_index_mod.scope_caveat(host_skip)
    except Exception:  # a reader must never raise over a caveat string
        tail = ("'.agents' (L-020) is excluded from the index, so this kit's OWN "
                "tooling is invisible to it.")
    return _INDEX_CAVEAT_HEAD + tail + " Coverage is over the project's code."

_DIGEST_LABEL = (
    "aggregate counts only - no timestamps, no tokens; produced by "
    "events.py compact() for events older than the 30-day retention window "
    "(L-00000032). Never a substitute for raw per-event history, never a "
    "cost source (a digest carries no token/cost fields to source from)."
)


def _project_root() -> Path:
    """The project this dashboard reads. Resolved from this file's own
    location by default (`.agents/bin/dashboard.py` -> parent.parent.parent),
    same convention as `otel_receiver.py`'s `_project_root()`.
    `AGENTS_DASHBOARD_PROJECT_ROOT` overrides for tests that need an
    isolated tmp tree with its own TASKS.json/LEDGER.json/SPECS.json/
    CODEBASE_INDEX.md/effective-verdict.json."""
    override = os.environ.get("AGENTS_DASHBOARD_PROJECT_ROOT")
    if override:
        return Path(override)
    return HERE.parent.parent


def _nom_depuis_racine(root: Path) -> str:
    """The project display name: the BASENAME of `root`, `"projet"` on an empty
    basename (`Path("/").name == ""`). Root-derived, NEVER `project.json:name`
    (T-00000582, S-00001541).

    Same TAIL as `cadre.paths.nom_projet()` (`.name or "projet"`), NOT the same
    rule: `nom_projet` resolves its input through `project_root()`, whereas here
    the ABSOLUTISATION below stands in for that — and the case/symlink divergence
    stays open (debt, T-00000685, point 2 of the closing review).

    ABSOLUTISE A RELATIVE ROOT FIRST, and this is the fix for a functional
    regression. `.name` is a pure string op, and the daemon hands this function a
    root straight from `normalize_root` (`dashboard_daemon.py:151`, `Path(text)`
    with NO resolution), so a DOCUMENTED launch `--root .`
    (`T-00000025-shard2-hook-patch.md:74`) would publish `"projet"` and `--root
    ..` would publish `".."` — on the badge, `/api/projects`,
    `/api/peer/summary` AND the machine-wide registry entry, i.e. at every peer
    on the machine. `os.path.abspath` absolutises and normalises LEXICALLY
    (against the cwd) WITHOUT following symlinks: it fixes the relative case
    without changing the name of a project whose directory IS a symlink, and
    leaves the case/symlink gap exactly where it is (T-00000685). NOT `resolve()`,
    which would follow links and move that boundary.

    DUPLICATED ON PURPOSE, not imported. `.agents/bin/` loads its neighbours by
    explicit path (`_load_sibling`); `charger_paquet` (top of file) loads the EXACT `cadre`
    package by path, sys.path untouched, for the siblings that import it; importing
    `cadre.paths` here would add a FIFTH root anchor (the defect T-00000582 avoids). The shared
    TAIL is kept in lockstep by an equivalence witness
    (`test_dashboard.py::test_nom_depuis_racine_matches_paths_nom_projet`), not
    by a text net. Unifying by import is the Phase 4 debt, named."""
    p = Path(root)
    if not p.is_absolute():
        p = Path(os.path.abspath(p))
    return p.name or "projet"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_today() -> date:
    """UTC calendar day, used to pick the rate row in force (T-00000076).

    UTC and not local time on purpose: a price boundary is a published date, and
    a dashboard in Auckland must not switch tariffs sixteen hours before one in
    Los Angeles.
    """
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# /api/snapshot — board + ledger + specs + index + security, each degrading
# independently (never a 500 for one section's failure).
# ---------------------------------------------------------------------------

def _safe_load_store(loader_mod, project_root: Path) -> dict[str, Any]:
    """`loader_mod.load(project_root)` wrapped so a malformed store (which
    tasks.py/ledger.py/specs.py deliberately raise on — "a malformed board
    raises, it never degrades into silently losing a task") degrades this
    READ-ONLY view instead of taking the whole response down. A missing
    store file is not an error at all: `load()` itself already returns the
    empty default shape for that case."""
    try:
        return {"status": "ok", "data": loader_mod.load(project_root)}
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        return {"status": "degraded", "reason": reason}


def _read_index_snapshot(project_root: Path) -> dict[str, Any]:
    path = project_root / ".agents" / "state" / "index" / "CODEBASE_INDEX.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"status": "degraded", "reason": "CODEBASE_INDEX.md not found or unreadable",
                "caveat": _index_caveat(project_root)}
    header = _build_index_mod._header_line(text)
    return {
        "status": "ok",
        "header": header,
        "built_at_sha": _build_index_mod._header_field(header, "built @"),
        "updated": _build_index_mod._header_field(header, "updated"),
        "caveat": _index_caveat(project_root),
    }


def _read_project(project_root: Path) -> dict[str, Any]:
    """Project identity for the UI badge (T-00000048, V1-a). Reads
    `.agents/state/project.json` for its PRESENCE/readability (which drives
    `status`), and derives `name` from the ROOT, no longer from the file
    (T-00000582, S-00001541):
      * absent               -> {"status": "unnamed", "name": None}
      * present & parseable  -> {"status": "ok", "name": <root basename>}
      * unparsable / unreadable / not an object -> {"status": "degraded", ...}
    Degrades, never raises (C2): a corrupt identity must not take the snapshot
    down. `name` is the basename of `project_root` (never the slug, C4; and
    since T-00000582 never `project.json:name` either — the JSON is parsed but
    its `name` value is IGNORED). `unnamed`/`degraded` keep `name: None`: a
    missing or corrupt file yields no derived name (Trap 2 — two equality nets
    pin those two shapes, test_dashboard.py:599,3883).

    V1-d BUG FIX, ASSUMED (T-00000051): the `except OSError` below used to let a
    project.json in NON-UTF-8 bytes escape as `UnicodeDecodeError` — that class
    is not an `OSError`, so "degrades, never raises" was a latent lie inherited
    from V1-a. The three `status` values are UNCHANGED (`ok` / `unnamed` /
    `degraded`); only the right to raise disappears.

    THE ORDER OF THE `except` BRANCHES IS LOAD-BEARING and must not be
    "simplified" into a single tuple: `FileNotFoundError` ⊂ `OSError` and
    `UnicodeDecodeError` / `json.JSONDecodeError` ⊂ `ValueError`, so a tuple
    placed first would SUBSUME the absent case and return `degraded` on the
    DEFAULT state of a fresh repo — pinned by
    `test_absent_identity_is_unnamed_not_degraded`.

    THIS IS THE BADGE ANCHOR, not the attribution anchor: the path is derived
    from `project_root`, while `/api/projects` and canal-B attribution resolve
    `event_store.project_json_path()` (anchored on `__file__`, overridable by
    `AGENTS_PROJECT_JSON`). Under `--root` or that env var the two differ; that
    divergence is a DEFECT tracked as T-00000056, not a fact this module
    publishes."""
    path = project_root / ".agents" / "state" / "project.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"status": "unnamed", "name": None}
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return {"status": "degraded", "name": None}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"status": "degraded", "name": None}
    if not isinstance(data, dict):
        return {"status": "degraded", "name": None}
    # T-00000582: the file was parsed (its readability set `status` to `ok`),
    # but its `name` is NO LONGER the source. The badge name is DERIVED from the
    # root, exactly like `/api/projects` and the peer summary.
    return {"status": "ok", "name": _nom_depuis_racine(project_root)}


# ---------------------------------------------------------------------------
# Project identity, ONE read and ONE parse (T-00000051, V1-d).
#
# WHY THIS EXISTS AT ALL. `/api/projects` publishes an id AND a human label. The
# id has exactly one legitimate source — `event_store.project_id_from_data()`,
# the recipe `resolve_project_id()` itself now calls — and the label lives in
# the same file. Reading that file twice (once through `resolve_project_id()`,
# once for `name`/`slug`) is not a cosmetic waste: a write landing BETWEEN the
# two reads publishes an OLD id next to a NEW name, and in the worst ordering an
# id of `PROJECT_UNSET` under a `status` of `ok` — the one value this contract
# swears never to publish. So: one function, one `read_text`, one `json.loads`,
# feeding the id, the slug, the status and the cause — `name` published by
# `/api/projects`/`/api/peer/summary` is now root-derived (T-00000582,
# S-00001541), not part of this parse. `_identity_result` still JSON-parses
# `name` (shape unchanged), but it is an INTERNAL value no route publishes.
#
# TWO CLOSED VOCABULARIES, and the pair is the whole contract:
#   ok         / None            -> a usable project_id; EXACTLY one entry
#   incomplete / "no_project_id" -> a valid object with no usable id (which
#                                   INCLUDES the literal `PROJECT_UNSET`, a
#                                   non-empty string that would otherwise
#                                   collide with every uninitialised repo on the
#                                   machine — L-00000049)
#   no_identity/ "absent"        -> no file (the pre-`project_init.py` state)
#   degraded   / "unreadable"    -> an OSError that is NOT absence (EACCES…)
#   degraded   / "invalid"       -> non-UTF-8 bytes, invalid JSON, or not an
#                                   object
# `ok` ⟺ `len(projects) == 1` is an invariant, tested, not a comment.
# ---------------------------------------------------------------------------

def _identity_result(status: str, cause: str | None, *,
                     project_id: str | None = None,
                     name: Any = None, slug: Any = None) -> dict[str, Any]:
    """One shape for every branch below, so no branch can forget a key."""
    return {
        "project_id": project_id if project_id is not None
        else _event_store_mod.PROJECT_UNSET,
        "name": name if isinstance(name, str) and name.strip() else None,
        "slug": slug if isinstance(slug, str) and slug.strip() else None,
        "status": status,
        "cause": cause,
    }


def _resolve_identity_once(path: Path) -> dict[str, Any]:
    """ONE read, ONE parse of the identity file at `path` -> the id, the name,
    the slug, and the (status, cause) pair. Never raises.

    `project_id` comes from `event_store.project_id_from_data()` — the SAME pure
    recipe `event_store.resolve_project_id()` calls — so this function and that
    one cannot disagree about the same bytes. It is the ONLY identity-resolution
    path in this module for the attribution anchor: `_read_canal_b` consumes
    this parse instead of calling `resolve_project_id()` itself.

    THE ORDER OF THE `except` BRANCHES IS LOAD-BEARING, for the same subsumption
    reason spelled out in `_read_project`: `FileNotFoundError` FIRST and
    DISTINCT (-> `absent`), and `UnicodeDecodeError` before the tuple that
    contains `ValueError` (-> `invalid`, because non-UTF-8 bytes are a content
    problem, not an access problem)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _identity_result("no_identity", "absent")
    except UnicodeDecodeError:
        # ⊂ ValueError, so this branch MUST precede the tuple below or be
        # silently subsumed by it — and it maps to `invalid`, not `unreadable`.
        return _identity_result("degraded", "invalid")
    except (OSError, ValueError, json.JSONDecodeError):
        return _identity_result("degraded", "unreadable")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _identity_result("degraded", "invalid")
    if not isinstance(data, dict):
        return _identity_result("degraded", "invalid")
    project_id = _event_store_mod.project_id_from_data(data)
    name, slug = data.get("name"), data.get("slug")
    if project_id == _event_store_mod.PROJECT_UNSET:
        # A valid object that declares no usable id. NOT `ok`: publishing
        # `PROJECT_UNSET` as a project key would name a project whose rows are
        # in quarantine and collide with every other uninitialised repo.
        return _identity_result("incomplete", "no_project_id", name=name, slug=slug)
    return _identity_result("ok", None, project_id=project_id, name=name, slug=slug)


def _read_security_verdict(project_root: Path) -> dict[str, Any]:
    path = project_root / ".agents" / "state" / "local" / "sca-reports" / "effective-verdict.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"status": "ok", "verdict": data}
    except FileNotFoundError:
        return {"status": "degraded", "reason": "effective-verdict.json absent - no SCA scan has run yet"}
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "degraded", "reason": f"effective-verdict.json unreadable: {exc}"}


# ---------------------------------------------------------------------------
# Canal-B aggregation (shard 4b). Reads `state/local/otel/*.jsonl` THROUGH
# shard 3's normaliser (`otel_normalize.iter_normalized_records`) - this
# module adds aggregation, never a second normalisation of the frozen schema.
#
# THREE MEASURED FACTS drive the shape below. All three were measured on this
# repo's own 271 real normalised records (2 files, 2026-07-27), not assumed:
#
#  1. `prompt_id` is NEVER usable today: 97 records carry None and 78 carry the
#     literal string "REDACTED" (L-00000053 - our own OTLP drop-list matched
#     the substring `prompt` and destroyed the value). So the per-task cost
#     join is IMPOSSIBLE, and "REDACTED" must never be used as a bucket key or
#     every record collapses into one bogus task. `by_task` therefore reports
#     `status: "unavailable"` with that reason - never an empty table, which a
#     reader would take for "these tasks cost nothing".
#  2. Cost arrives TWICE for the same spend: `claude_code.cost.usage` (metric)
#     and `api_request.cost_usd` (log) summed to the same $1.7399 over the same
#     14 requests. The native total sums the METRIC only; the log total sits
#     beside it as a cross-check and is never added.
#  3. `agent.name` is on 10 of 70 cost/token metric records. A `by_agent`
#     table built from those alone would silently attribute 6/7 of the spend to
#     nobody, so the section carries its own coverage counter.
# ---------------------------------------------------------------------------

_CANAL_B_JOIN_UNAVAILABLE = (
    "L-00000053: the kit's own OTLP redaction drop-list matches the substring "
    "`prompt`, so `prompt.id` - the documented canal-A join key - arrives as "
    'the literal string "REDACTED". The field is PRESENT and its value '
    "DESTROYED, which is strictly worse than absent: it looks joinable. Cost "
    "cannot be attributed per task until the drop-list is fixed at the "
    "capture end (otel_receiver.redact), and this view must not pretend "
    "otherwise by bucketing every record under one shared placeholder."
)

_CANAL_B_DOUBLE_COUNT_NOTE = (
    "`claude_code.cost.usage` (metric) and `api_request.cost_usd` (log) are "
    "TWO VIEWS OF THE SAME SPEND, not two spends - measured equal on this "
    "repo's captures ($1.7399 each, 14 requests). `native_usd` sums the METRIC "
    "only; `cross_check_usd_from_logs` is reported for comparison and must "
    "never be added to it."
)

# Ships EMPTY on purpose. A `tokens x rate` estimate needs a rate, and this
# repo declares one NOWHERE (grepped: no pricing table in .agents/, docs/, or
# any manifest - the kit has no package manifest by design). Inventing
# per-model dollar rates here would manufacture the very "unlabelled figure"
# the design doc forbids, so the estimate reports itself UNAVAILABLE until a
# human declares rates. Filling this dict is the only change needed - every
# consumer already handles both branches.
_TOKEN_RATES_USD: dict[str, dict[str, float]] = {}

_TOKEN_RATE_ABSENT_REASON = (
    "no token rate table is declared anywhere in this repo, so no "
    "tokens x rate estimate can be computed. A rate invented by the dashboard "
    "would be an unlabelled fabrication (design doc: an estimate must be "
    "labelled as such AND sourced). Native $ from claude_code.cost.usage is "
    "unaffected - it is measured, not estimated."
)

# Values that LOOK like a join key but are not one. Compared case-folded.
_UNUSABLE_JOIN_VALUES: frozenset[str] = frozenset({"redacted", "none", "null", "unknown", ""})


def _is_usable_join_key(value: Any) -> bool:
    """A join key must be a non-empty string that is not a redaction
    placeholder. Fact 1 above is the whole reason this predicate exists."""
    return isinstance(value, str) and value.strip().casefold() not in _UNUSABLE_JOIN_VALUES


def _canal_a_prompt_index() -> dict[str, Any]:
    """`prompt id -> task` from canal A, for the documented `prompt.id` join.

    T-00000026 shard A: now consumes `dashboard_readers.read_canal_a_stream`,
    the MEMOISED whole-trail read the six D4 views also use, instead of
    re-globbing and re-parsing every day-file itself. Same underlying reader
    (`read_new_records`, so non-negotiable #2 still applies), one read per poll
    instead of two - measured: 349 day-files read twice per `/api/snapshot`
    pushed the cold route into `dashboard_daemon`'s ping budget.

    Never raises: an unreadable events dir yields an empty index with a
    reason, never an exception into `/api/snapshot`."""
    index: dict[str, str] = {}
    with_pid = 0
    unusable = 0
    # T-00000065: the store-aware read, not the spool glob. This index was going
    # empty for the same reason the four views went `trail_absent` — the records
    # it joins on had already been projected and their files deleted.
    stream = _read_canal_a_trail()
    if stream["status"] in ("trail_absent", "degraded", "unavailable"):
        return {"map": {}, "canal_a_with_pid": 0, "canal_a_unusable_pid": 0,
                "reason": stream["reason"]}
    for record in stream["records"]:
        pid = record.get("pid")
        if not _is_usable_join_key(pid):
            if pid is not None:
                unusable += 1
            continue
        with_pid += 1
        task = record.get("task")
        if isinstance(task, str) and task:
            index[pid] = task
    reason = None
    if not index:
        reason = (
            "no canal-A event carries both a usable `pid` and a `task`: on this "
            "repo's own stream the hooks emit `pid: null` (the prompt id is not "
            "wired into the envelope yet), so there is nothing to join canal B "
            "against even once L-00000053 is fixed."
        )
    return {"map": index, "canal_a_with_pid": with_pid,
            "canal_a_unusable_pid": unusable, "reason": reason}


def _bucket_add(bucket: dict[str, Any], key: str, tokens: float, cost: float, records: int) -> None:
    slot = bucket.setdefault(key, {"tokens": 0, "cost_usd": 0.0, "records": 0})
    slot["tokens"] += tokens
    slot["cost_usd"] += cost
    slot["records"] += records


def _round_usd(value: float) -> float:
    """6 dp: enough to keep a fraction of a cent, short enough that JSON does
    not carry float noise like 1.7399141499999998 into a UI."""
    return round(float(value), 6)


def _attribution_bucket(record: dict[str, Any], own_project_id: str) -> str:
    """Which of the THREE ROW BUCKETS does this envelope-or-record fall in?
    `attributed` | `unattributed` | `foreign_held`. Takes either shape, because
    the promoted field has the SAME name at both levels — the envelope's
    first-level `project_id`, which both mappers copy verbatim into the record.
    PURE, and it reads ONLY the
    promoted `project_id` — never `provenance`, which is an absolute path on
    every pre-V1-c line and a legacy display field from V1-c on.

    Absent field -> `unattributed`, NOT a fourth bucket and NEVER foreign. In
    the database the case cannot occur (the one-shot backfill materialised the
    field on every canal-B row, and `otel_receiver.persist()` guarantees every
    new line has one), so this branch is reached only on the FILE FALLBACK —
    when the store is `absent` because the daemon has never ingested, hence no
    backfill has run. Counting those in `unattributed` keeps them inside the
    census and inside the labelled totals; re-deriving their project from a
    path here would be the render-time path comparison V1-c deliberately
    materialised away (iteration 9, C5)."""
    declared = record.get("project_id")
    if not isinstance(declared, str) or not declared:
        return "unattributed"
    if declared == _otel_receiver.PROJECT_UNATTRIBUTED:
        return "unattributed"
    if own_project_id == _otel_receiver.PROJECT_UNSET:
        # No identity: nothing can be foreign, and nothing can be claimed.
        return "unattributed"
    if declared == own_project_id:
        return "attributed"
    return "foreign_held"


def _canal_b_attribution(envelopes: list[dict[str, Any]], own_project_id: str,
                         counters: dict[str, Any]) -> dict[str, Any]:
    """The V1-c attribution block: FIVE buckets, in TWO GROUPS, with no invited
    sum (plan-critic iteration 7, C2).

    COUNTED OVER ENVELOPES, I.E. OVER ROWS — never over normalised records.
    Found on this repo's own database: an envelope can be a real stored row and
    normalise to ZERO records (a `failure` record carries no schema-family
    content; a `kind` outside the known set normalises to nothing by design). A
    "rows in store" census computed from records would have omitted exactly
    those — including a QUARANTINED row whose kind is unknown, which is the
    silent subtraction this block exists to make impossible.

    `rows_in_store` counts ROWS THAT EXIST: `attributed` (with
    `attributed_by_backfill` as a visible SUB-COUNT of it, not a sibling —
    inference next to declaration in one number is how an inference becomes a
    measurement), `unattributed`, `foreign_held`. Those three DO partition the
    canal-B rows, totally, which is what the one-shot backfill bought.

    `event_counters` counts EVENTS THAT ARE NOT ROWS, each with its time base
    spelled out: `dropped_foreign` never became a row (refused at the
    receiver, since this process started), `foreign_held_expired` stopped being
    one (deleted by the 30-day fold, cumulative). Adding a bucket from one
    group to a bucket from the other is meaningless, so they are never
    presented as one list.

    `keyed_on` is stated in the payload because the whole point of V1-c is that
    this census is keyed on `project_id` and no longer on `provenance`."""
    buckets = {"attributed": 0, "unattributed": 0, "foreign_held": 0}
    by_backfill = 0
    for envelope in envelopes:
        bucket = _attribution_bucket(envelope, own_project_id)
        buckets[bucket] = buckets.get(bucket, 0) + 1
        if bucket == "attributed" and envelope.get("project_attributed_by") == "backfill":
            by_backfill += 1
    return {
        "own_project_id": own_project_id,
        "keyed_on": "project_id (first-level envelope field); `provenance` is a "
                    "legacy display field and is never classified on",
        "rows_in_store": {
            **buckets,
            "attributed_by_backfill": by_backfill,
        },
        "event_counters": dict(counters),
        "totals_include": ["attributed", "unattributed"],
        "totals_exclude": ["foreign_held"],
        "note": (
            "TWO GROUPS, NEVER ONE SUM: `rows_in_store` are rows that exist and "
            "partition canal B totally; `event_counters` are events that never "
            "became rows or stopped being rows, each with its own time base."
        ),
    }


def _aggregate_canal_b(records: list[dict[str, Any]], prompt_index: dict[str, Any],
                       own_project_id: str | None = None,
                       counters: dict[str, Any] | None = None,
                       envelopes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Turn normalised canal-B records into the aggregates the Coût view needs.
    Pure function of its inputs (no I/O) so tests can drive it with fixtures.

    V1-c, TWO GRANULARITIES ON PURPOSE: the attribution census counts ROWS (the
    `envelopes`, since a stored row can normalise to zero records), and EVERY
    OTHER aggregate is computed over the non-`foreign_held` RECORDS. That split
    is the point — a neighbouring project's quarantined rows must be VISIBLE (a
    displayed fact, not a silent subtraction) and must not enter this project's
    money, tokens, per-agent or per-task figures.

    `envelopes=None` falls back to `records`; the single production caller
    (`_read_canal_b`) always passes them."""
    own = own_project_id or _otel_receiver.PROJECT_UNSET
    attribution = _canal_b_attribution(
        records if envelopes is None else envelopes, own, counters or {})
    all_records = records
    records = [r for r in records if _attribution_bucket(r, own) != "foreign_held"]
    metrics = [r for r in records if r.get("kind") == "metric"]
    logs = [r for r in records if r.get("kind") == "log"]

    cost_metrics = [r for r in metrics if r.get("schema_family") == "claude_code.cost.usage"]
    token_metrics = [r for r in metrics if r.get("schema_family") == "claude_code.token.usage"]
    api_logs = [r for r in logs if r.get("schema_family") == "api_request"]
    subagent_logs = [r for r in logs if r.get("schema_family") == "subagent_completed"]
    decision_logs = [r for r in logs if r.get("schema_family") == "tool_decision"]

    native_usd = sum(r.get("value") or 0 for r in cost_metrics)
    logs_usd = sum((r.get("fields") or {}).get("cost_usd") or 0 for r in api_logs)

    tokens_by_type: dict[str, int] = {}
    for record in token_metrics:
        token_type = str((record.get("fields") or {}).get("type") or "unspecified")
        tokens_by_type[token_type] = tokens_by_type.get(token_type, 0) + int(record.get("value") or 0)
    tokens_total = sum(tokens_by_type.values())

    # Hourly cost series, LAST 24 BUCKETS ONLY. Bounded on purpose: retention
    # is 30 days (L-00000032), so an unbounded per-hour map would grow to ~720
    # entries in a payload polled every 5 s. Buckets are the emitter's own UTC
    # hour prefix - no local-timezone conversion is invented here.
    hourly: dict[str, float] = {}
    for record in cost_metrics:
        stamp = record.get("ts")
        if not isinstance(stamp, str) or len(stamp) < 13:
            continue
        hourly[stamp[:13]] = hourly.get(stamp[:13], 0.0) + float(record.get("value") or 0)
    cost_series = [
        {"hour": hour, "cost_usd": _round_usd(value)}
        for hour, value in sorted(hourly.items())[-24:]
    ]

    by_model: dict[str, Any] = {}
    for record in token_metrics:
        model = str((record.get("fields") or {}).get("model") or "unspecified")
        _bucket_add(by_model, model, int(record.get("value") or 0), 0.0, 1)
    for record in cost_metrics:
        model = str((record.get("fields") or {}).get("model") or "unspecified")
        _bucket_add(by_model, model, 0, float(record.get("value") or 0), 1)

    # Per-SESSION cost (T-00000096). `claude_code.cost.usage` arrives with
    # DELTA temporality (aggregationTemporality=1, measured on this repo's
    # store), so summing a session's dataPoints IS that session's total — the
    # same number Claude Code's own /cost displays, within one 5 s export lag.
    # Before this aggregate existed the only dollar figure the payload carried
    # was the 30-day project total, which the front then labelled "coût
    # session": a ~$540 cumul gaining $0.30 per turn reads as frozen, and can
    # never match the session figure the host shows. Bounded like every other
    # list in this payload: the 12 most recently ACTIVE sessions, newest
    # first, and a count of what fell outside — never an unbounded map in a
    # payload polled every 5 s. Records without the key are counted, not
    # guessed at: rows ingested before `session.id` entered the allow-list
    # would land there if any reader ever bypasses read-time normalisation.
    session_buckets: dict[str, dict[str, Any]] = {}
    cost_without_sid = 0
    for record in cost_metrics:
        sid = (record.get("fields") or {}).get("session.id")
        if not isinstance(sid, str) or not sid:
            cost_without_sid += 1
            continue
        stamp = record.get("ts")
        slot = session_buckets.setdefault(sid, {"cost_usd": 0.0, "records": 0,
                                                "first_ts": stamp, "last_ts": stamp})
        slot["cost_usd"] += float(record.get("value") or 0)
        slot["records"] += 1
        if isinstance(stamp, str):
            if not isinstance(slot["first_ts"], str) or stamp < slot["first_ts"]:
                slot["first_ts"] = stamp
            if not isinstance(slot["last_ts"], str) or stamp > slot["last_ts"]:
                slot["last_ts"] = stamp
    _SESSIONS_CAP = 12
    sessions_sorted = sorted(
        session_buckets.items(),
        key=lambda item: item[1].get("last_ts") or "",
        reverse=True,
    )
    by_session = [
        {"session_id": sid, "cost_usd": _round_usd(slot["cost_usd"]),
         "records": slot["records"], "first_ts": slot["first_ts"], "last_ts": slot["last_ts"]}
        for sid, slot in sessions_sorted[:_SESSIONS_CAP]
    ]

    # Fact 3: agent attribution is PARTIAL. Records without `agent.name` are
    # counted as unattributed rather than bucketed under a fake agent.
    by_agent: dict[str, Any] = {}
    attributed = 0
    for record in token_metrics + cost_metrics:
        fields = record.get("fields") or {}
        agent = fields.get("agent.name")
        if not isinstance(agent, str) or not agent:
            continue
        attributed += 1
        is_cost = record.get("schema_family") == "claude_code.cost.usage"
        _bucket_add(
            by_agent, agent,
            0 if is_cost else int(record.get("value") or 0),
            float(record.get("value") or 0) if is_cost else 0.0,
            1,
        )
    for record in subagent_logs:
        fields = record.get("fields") or {}
        agent = fields.get("agent_type")
        if isinstance(agent, str) and agent:
            _bucket_add(by_agent, agent, int(fields.get("total_tokens") or 0), 0.0, 1)

    # Fact 1: the per-task join. Attempted honestly, reported honestly.
    joinable = 0
    unusable_key = 0
    no_key = 0
    by_task: dict[str, Any] = {}
    mapping = prompt_index.get("map") or {}
    for record in logs:
        prompt_id = record.get("prompt_id")
        if prompt_id is None:
            no_key += 1
            continue
        if not _is_usable_join_key(prompt_id):
            unusable_key += 1
            continue
        task = mapping.get(prompt_id)
        if task is None:
            continue
        joinable += 1
        fields = record.get("fields") or {}
        _bucket_add(
            by_task, task,
            int(fields.get("input_tokens") or 0) + int(fields.get("output_tokens") or 0)
            + int(fields.get("total_tokens") or 0),
            float(fields.get("cost_usd") or 0),
            1,
        )

    if joinable:
        task_section: dict[str, Any] = {"status": "ok", "reason": None, "data": by_task}
    elif unusable_key:
        task_section = {"status": "unavailable", "reason": _CANAL_B_JOIN_UNAVAILABLE, "data": {}}
    else:
        task_section = {
            "status": "unavailable",
            "reason": prompt_index.get("reason")
            or "no canal-B log record carries a prompt id to join on",
            "data": {},
        }

    for bucket in (by_model, by_agent, by_task):
        for slot in bucket.values():
            slot["cost_usd"] = _round_usd(slot["cost_usd"])

    hosts = {
        host: _otel_normalize_mod.cost_summary_for_host(host, metrics)
        for host in sorted(_otel_normalize_mod.HOST_METRICS_COVERAGE)
    }
    for summary in hosts.values():
        if isinstance(summary.get("cost_usd"), (int, float)):
            summary["cost_usd"] = _round_usd(summary["cost_usd"])

    # T-00000073 — the 5 canal-B count metrics summed per host, over the SAME
    # sorted host set and the SAME `metrics` list `cost_summary_for_host` sees.
    # NO renderer consumes this yet (display is the separate T-00000186). C12:
    # promoting `lines_of_code.count` and `code_edit_tool.decision` into
    # `_METRIC_FAMILIES` (so their attributes reach `fields`) also makes them
    # appear in the `hosts_seen[...]["families"]` census below (:families) ahead
    # of T-00000186 — intended, not a regression.
    metric_totals = {
        host: _otel_normalize_mod.metric_totals_for_host(host, metrics)
        for host in sorted(_otel_normalize_mod.HOST_METRICS_COVERAGE)
    }

    # LEGACY DISPLAY CENSUS (V1-c). Nothing classifies on `provenance` any
    # more: post-V1-c it holds a project id or the sentinel, pre-V1-c an
    # absolute path — so this dict deliberately MIXES shapes and is rendered
    # under an explicit "provenance legacy / pré-V1-c" heading. It is kept
    # rather than removed because it is the only surviving trace of where a
    # pre-V1-c line came from (pilot decision, S-00000108 item 3). Computed over
    # ALL records, quarantined ones included: as a legacy trace it must not
    # silently hide what the attribution block shows.
    provenance: dict[str, int] = {}
    for record in all_records:
        key = str(record.get("provenance") or "unknown")
        provenance[key] = provenance.get(key, 0) + 1

    models_seen = sorted({str((r.get("fields") or {}).get("model")) for r in token_metrics + cost_metrics
                          if isinstance((r.get("fields") or {}).get("model"), str)})

    # T-00000026 shard A additions. The MCP view needs `mcp_server_connection`
    # counts and the Couverture view needs a per-host signal census; BOTH are
    # already inside `records`, so they are computed HERE, in the one pass this
    # module already makes, rather than by a second read of state/local/otel/.
    # `mcp_server_connection` is deliberately NOT in the frozen schema
    # families, so it appears in `by_event_name` with `schema_family: null` —
    # counted by name, never promoted into the frozen contract.
    by_event_name: dict[str, int] = {}
    by_metric_name: dict[str, int] = {}
    hosts_seen: dict[str, Any] = {}
    for record in records:
        host = str(record.get("host") or "unknown")
        slot = hosts_seen.setdefault(
            host, {"records": 0, "families": {}, "event_names": {}, "metric_names": {}}
        )
        slot["records"] += 1
        family = record.get("schema_family")
        if isinstance(family, str):
            slot["families"][family] = slot["families"].get(family, 0) + 1
        name = record.get("event_name") if record.get("kind") == "log" else record.get("metric_name")
        if isinstance(name, str):
            target = by_event_name if record.get("kind") == "log" else by_metric_name
            target[name] = target.get(name, 0) + 1
            bucket = "event_names" if record.get("kind") == "log" else "metric_names"
            slot[bucket][name] = slot[bucket].get(name, 0) + 1

    return {
        "attribution": attribution,
        "by_event_name": by_event_name,
        "by_metric_name": by_metric_name,
        "hosts_seen": hosts_seen,
        "records_normalised": len(all_records),
        # The subset every figure below is computed on. Named, so the gap
        # between it and `records_normalised` is readable as the quarantine
        # rather than as an inconsistency.
        "records_counted": len(records),
        "cost": {
            "native_usd": _round_usd(native_usd) if cost_metrics else None,
            "native_source": "claude_code.cost.usage (metric)",
            "cross_check_usd_from_logs": _round_usd(logs_usd) if api_logs else None,
            "double_count_note": _CANAL_B_DOUBLE_COUNT_NOTE,
            "estimated_usd": None,
            "estimate_status": "unavailable",
            "estimate_reason": _TOKEN_RATE_ABSENT_REASON,
            "rate_table_declared": bool(_TOKEN_RATES_USD),
            "series_hourly": cost_series,
            "series_note": "UTC hour buckets from claude_code.cost.usage, last 24 only",
            # T-00000096 — the per-session split the KPI strip renders.
            # `sessions[0]` is the most recently active session; its
            # `cost_usd` is the figure comparable to the host's own /cost
            # display (delta temporality, so the sum IS the session total).
            "by_session": {
                "sessions": by_session,
                "sessions_seen": len(session_buckets),
                "sessions_cap": _SESSIONS_CAP,
                "records_without_session_id": cost_without_sid,
                "note": (
                    "cost.usage deltas summed per session.id, newest activity first, "
                    f"{_SESSIONS_CAP} most recent kept. `native_usd` above remains the "
                    "30-day project cumul — a DIFFERENT number, never to be compared "
                    "with the host's per-session display."
                ),
            },
        },
        "tokens": {
            "total": tokens_total,
            "by_type": tokens_by_type,
            "source": "claude_code.token.usage (metric), one dataPoint per model x type",
        },
        "by_model": by_model,
        "by_agent": {
            "data": by_agent,
            "attributed_records": attributed,
            "attributable_records": len(token_metrics) + len(cost_metrics),
            "coverage_note": (
                "`agent.name` is optional on cost/token metrics: records without it are "
                "counted as unattributed, never bucketed under a placeholder agent."
            ),
        },
        "by_task": task_section,
        # Per-host coverage comes from shard 3's own table (never re-derived):
        # `not_emitted_by_design` / `no_data_yet` / `collected` stay
        # distinguishable, so a host that emits nothing is never a $0.
        "hosts": hosts,
        # T-00000073 — per-host totals of the 5 canal-B count metrics, same
        # three-status discipline as `hosts`; rendered by CoverageTab's
        # "valeurs sommées" table since T-00000186.
        "metric_totals": metric_totals,
        "join": {
            "key": "prompt.id (canal B) = pid (canal A envelope)",
            "canal_b_logs": len(logs),
            "joined": joinable,
            "unusable_key_value": unusable_key,
            "no_key": no_key,
            "canal_a_entries_indexed": len(mapping),
            "canal_a_with_pid": prompt_index.get("canal_a_with_pid", 0),
            "reason": None if joinable else task_section["reason"],
        },
        "counts": {
            "cost_metrics": len(cost_metrics),
            "token_metrics": len(token_metrics),
            "api_request_logs": len(api_logs),
            "subagent_completed_logs": len(subagent_logs),
            "tool_decision_logs": len(decision_logs),
        },
        "models_seen": models_seen,
        "provenance": provenance,
    }


# ---------------------------------------------------------------------------
# Aggregate cache (shard 4b, performance — measured, not speculative).
#
# WHY: canal B made `/api/snapshot` re-read and re-normalise every canal-B file
# AND every canal-A day-file on EVERY call — 169 files / ~20 ms steady-state on
# this repo then, 3.4-4.4 s per build on the real store since (T-01M4XR9ESW's
# measure). A reader that gets slower the longer the kit is used is a defect.
#
# HOW: the STORE's key, which moves with its DATA generation and not with its main
# file's stat — frozen in WAL between checkpoints (T-00000615) — plus its STATUS and,
# while no projection exists (`absent`), the (name, size) of both spool directories
# (`dashboard_transport.part_du_spool`, T-01M4XR9ESWKJ8G545AJBJQNC7Q): the spool is
# then the source, and an append-only file cannot gain a line without gaining bytes.
# A poll that finds nothing changed costs stat() calls and one meta read.
#
# The resolved directory PATHS are part of the fingerprint, which is what makes
# a module-level cache safe under pytest: every test gets its own tmp dirs, so
# one test's aggregates can never be served to another.
# ---------------------------------------------------------------------------

# Same move as `_read_new_records`: one fingerprint helper, in the module that
# now needs it for eleven more inputs (T-00000026 shard A).
_dir_fingerprint = _readers_mod.dir_fingerprint


def _canal_b_fingerprint(otel_dir: Path, store_status: str = "unknown") -> tuple:
    """V1-c adds the STORE's fingerprint AND ITS STATUS (iteration 6, C5): `absent -> ok` is the moment the
    SOURCE of this section changes (spool files -> database), and the status also picks the spool's share —
    `(name, size)` under `absent`, nothing otherwise (`dashboard_transport.part_du_spool`, T-01M4XR9ESW)."""
    try:
        events_dir = _events_mod._events_dir()
    except Exception:  # noqa: BLE001 - fingerprint must never raise
        events_dir = None
    return (
        str(otel_dir),
        _transport_mod.part_du_spool(otel_dir, store_status),
        str(events_dir) if events_dir is not None else None,
        _transport_mod.part_du_spool(events_dir, store_status),
        store_status,
        _store_fingerprint(),
    )


def _reset_canal_b_cache_for_tests() -> None:
    _canal_b_mod.oublier()


_canal_a_cache: dict[str, Any] = {"fingerprint": None, "value": None}


def _canal_a_fingerprint(events_dir: Path | None, store_status: str = "unknown") -> tuple:
    """Same shape, same reasoning as `_canal_b_fingerprint`: the store's STATUS
    is an input on its own, because `absent -> ok` is the moment this section's
    SOURCE changes and no file mtime necessarily moves with it."""
    return (
        str(events_dir) if events_dir is not None else None,
        _dir_fingerprint(events_dir) if events_dir is not None else (),
        store_status,
        _store_fingerprint(),
    )


def _reset_canal_a_cache_for_tests() -> None:
    _canal_a_cache["fingerprint"] = None
    _canal_a_cache["value"] = None


def _read_canal_a_trail() -> dict[str, Any]:
    """The canal-A trail, from the SQLite projection when there is one.

    T-00000065 — THE SAME DOCTRINE AS `_read_canal_b`, FOR THE OTHER CHANNEL.
    T-00000049 moved `/api/events` to the store and left this side globbing the
    spool; since that same task made the ingester DELETE a file once projected,
    an empty `state/events/` became the NORMAL state of a healthy repo — and the
    four views fed from here rendered it as `trail_absent`, "ABSENT TRAIL, not a
    measurement of zero activity". Measured on this repo the day it was found:
    8246 rows in the database, 1008 of them `hook.deny`, and a Governance view
    reporting a lost trail. The inversion is worse than a blank panel: that view
    exists (design doc T-00000026) precisely to keep "no events" and "trail
    lost" from rendering alike.

    Three branches, and they are `_read_canal_b`'s branches:
      * store `ok`        -> the database is the source (`source: "sqlite"`).
      * store `absent`    -> no projection has ever been written, so the spool
                             files ARE the truth, not a fallback.
      * anything else     -> DEGRADED with the store's own reason and NO file
                             fallback: a database we refused to interpret must
                             not be silently replaced by a second story about
                             the same trail.

    NOT A MERGE, deliberately. A spool file still on disk may already have its
    first N lines projected (the ingester resumes by offset), so concatenating
    the two sources would double-count exactly the records that are mid-flight.
    The bounded price is that events younger than one ingest tick (5 s) are not
    in these views yet — a lag `ingestion_status()` already reports as `late` /
    `behind_since` and the Coverage view already displays, rather than a silence.

    Never raises. Memoised like its sibling; the returned dict is READ-ONLY for
    callers, since an unchanged poll gets the same object back."""
    events_dir = _resolved_events_dir()
    store_status, store_reason = "unknown", None
    store = None
    try:
        try:
            store = _event_store_mod.open_store(create=False)
            store_status, store_reason = store.status, store.reason
        except Exception as exc:  # noqa: BLE001 - a store surprise degrades, never 500s
            store_status = "unavailable"
            store_reason = f"{type(exc).__name__}: {str(exc)[:200]}"

        fingerprint = _canal_a_fingerprint(events_dir, store_status)
        if _canal_a_cache["fingerprint"] == fingerprint and _canal_a_cache["value"] is not None:
            return _canal_a_cache["value"]

        value: dict[str, Any]
        if store_status == "ok" and store is not None:
            read = store.canal_a_bodies()
            if read["status"] != "ok":
                value = {"status": "unavailable", "records": [], "files": 0,
                         "malformed": 0, "source": "sqlite",
                         "reason": f"canal-A store read failed: {read['reason']}"}
            else:
                records, malformed = _parse_canal_a_bodies(read["bodies"])
                value = {
                    "status": "ok" if records else "no_events",
                    "records": records,
                    # `files` keeps its name and its MEANING: day-files read.
                    # In store mode that is zero by construction, and `rows` is
                    # the count that matters — a consumer must not read a 0 here
                    # as "nothing was read".
                    "files": 0, "rows": read["rows"], "malformed": malformed,
                    "source": "sqlite",
                    "reason": None if records else (
                        "the SQLite projection holds no canal-A row yet: the store "
                        "exists and is readable, so this IS a measurement of zero "
                        "activity, not an absent trail"
                    ),
                }
        elif store_status == "absent":
            value = {**_readers_mod.read_canal_a_stream(events_dir),
                     "source": "spool_files"}
        else:
            value = {"status": "unavailable", "records": [], "files": 0,
                     "malformed": 0, "source": store_status,
                     "reason": f"canal-A store {store_status}: {store_reason}"}
    finally:
        if store is not None:
            store.close()

    _canal_a_cache["fingerprint"] = fingerprint
    _canal_a_cache["value"] = value
    return value


def _parse_canal_a_bodies(bodies: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Bodies -> records, counting what will not parse. Same discipline as the
    spool reader's `read_jsonl_file`: a malformed line is SKIPPED AND COUNTED,
    never dropped silently, and never allowed to take the read down."""
    records: list[dict[str, Any]] = []
    malformed = 0
    for body in bodies:
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            malformed += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            malformed += 1
    records.sort(key=lambda r: (r.get("ts") or ""))
    return records, malformed


def _read_canal_b() -> dict[str, Any]:
    """Canal-B aggregates, degrading independently of every other snapshot
    section. Absent source, no data, or data whose every line is malformed all
    yield `status: "degraded"` WITH a reason - never a 500, and never an `ok`
    section holding zeros (a zero is a measurement, absence is not).

    V1-c — ONE SOURCE PER SNAPSHOT, AND THE FALLBACK IS NARROW. The projection
    (`events.db`, `WHERE channel = 'b'`) is the source. The spool files are read
    ONLY when the store's status is `absent`, i.e. the daemon has never ingested
    anything and there is nothing else to read. `unavailable` / `schema_ahead`
    are reported as DEGRADED with the store's own reason and NEVER fall back to
    the files: a database written by a newer kit, or one we refused to interpret,
    means the figures cannot be trusted — and quietly rendering a file-derived
    number instead would be a second story about the same money, told without
    saying which one you are reading (the shape iteration 5's C2 named).

    Memoised on a fingerprint that includes the store's STATUS (`_canal_b_fingerprint`), then BOUNDED,
    DATED and INCREMENTAL (`dashboard_canal_b`, T-01M5T5G6MR): the returned dict is READ-ONLY for callers,
    since an unchanged poll gets the same object back."""
    base = {
        "schema_frozen": True,
        "schema": CANAL_B_RECORD_SCHEMA,
        # THE LABELS TRAVEL WITH THE DATA, not only in the payload's top-level
        # caveats: a consumer that renders only this section must still see that
        # 4318 is machine-global (L-00000049), that some rows were attributed by
        # inference, and that the cost view stops at 30 days.
        "caveats": [_CROSS_PROJECT_CAVEAT, _BACKFILL_CAVEAT, _COST_TRUNCATION_CAVEAT],
    }
    try:
        otel_dir = _otel_receiver._otel_dir()
    except Exception as exc:  # noqa: BLE001 - see docstring
        return {**base, "collected": False, "status": "degraded",
                "reason": f"canal-B directory could not be resolved: {type(exc).__name__}"}

    # The store is opened FIRST but read LAST: its status and this process's
    # drop counter are both fingerprint inputs, and a poll that finds nothing
    # changed must still cost only that — never a full read of channel B.
    store_status, store_reason, source, files = "unknown", None, "sqlite", []
    # T-00000613. THE `bodies` LIST IS GONE: the store path streams rows into the three names below (the
    # FILE fallback reads whole spool files through `iter_envelopes`). `rows_read` replaces every
    # `len(bodies)`, counted as the rows go by — a list kept "just for the count" held 545 Mo.
    rows_read, apres = 0, None  # `apres`: the incremental watermark, None for a full read (`rows_read_scope`)
    streamed: tuple[list[Any], list[dict[str, Any]], int, int] | None = None
    stream_error: str | None = None
    store = None
    # The own id comes from `_resolve_identity_once()` — ONE recipe for "who am
    # I" (`event_store.project_id_from_data()`, the same one
    # `resolve_project_id()` calls) reached through the ONE resolution path this
    # module has since V1-d, and not `store.project`: an `absent` store never
    # resolved one, and the FILE FALLBACK below has to classify anyway. When the
    # store is `ok` the two are the same value by construction (`open_store`
    # freezes `store.project` from the same recipe).
    #
    # T-00000051 rewrote this call site rather than adding a second reader beside
    # it: `/api/projects` needs the name and the slug from the same parse as the
    # id, and leaving `resolve_project_id()` here would have made this module
    # hold two resolution paths over the same file.
    try:
        own_project_id = _resolve_identity_once(
            _event_store_mod.project_json_path())["project_id"]
    except Exception:  # noqa: BLE001 - an identity resolver may never 500 a route
        own_project_id = _otel_receiver.PROJECT_UNSET
    try:
        try:
            store = _event_store_mod.open_store(create=False)
            store_status, store_reason = store.status, store.reason
            counters = store.attribution_counters()
        except Exception as exc:  # noqa: BLE001 - a store surprise degrades, never 500s
            store_status = "unavailable"
            store_reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            counters = {}

        fingerprint = _canal_b_fingerprint(otel_dir, store_status) + (
            # `dropped_foreign` lives in memory and the identity is re-read per call: neither moves a file.
            counters.get("dropped_foreign", 0), own_project_id,
        )
        # T-01M5T5G6MR: the memo, else the cached value DEFERRED while only the store's data moved
        # (`dashboard_canal_b.differer`); never on a non-ok status, a changed base, spool or identity.
        servie = _canal_b_mod.servir(fingerprint, store_status)
        if servie is not None:
            return servie
        debut = _canal_b_mod.top()

        if store_status == "ok" and store is not None:
            # READ *AND* NORMALISE INSIDE THIS `try`, because the `finally`
            # below closes the store: a generator handed further down would be
            # drained after its own connection had gone. That coupling is the
            # whole reason this is a restructure and not a swapped call.
            def _counted(rows: Any) -> Any:
                """Count the rows HERE, not inside the normaliser.

                `rows_read` used to be `len(bodies)` — a list that survived a
                failure. A counter living inside `stream_bodies` dies with the
                exception, and the degraded payload then reports `rows_read: 0`,
                which is indistinguishable from an EMPTY channel. On the exact
                failure mode this ticket exists to make visible, that would be
                the second silent answer in a row."""
                nonlocal rows_read
                for row in rows:
                    rows_read += 1
                    yield row

            try:
                # `closing()`: drain-before-close is an invariant of the CODE — an abandoned generator
                # would otherwise finalise in a race with the `store.close()` below. T-01M5T5G6MR: only
                # the rows after the watermark when `suite` allows it, else everything (`oublier` first);
                # the lot joins the cumul only AFTER the whole flux — a flux that dies leaves it as it was.
                apres = _canal_b_mod.suite(store)
                with contextlib.closing(store.iter_canal_b_bodies() if apres is None
                                        else store.iter_canal_b_bodies(apres=apres)) as rows:
                    lot = _otel_normalize_mod.stream_bodies(_counted(rows))
                streamed = _canal_b_mod.cumuler(lot, store)
            except (sqlite3.Error, sqlite3.Warning) as exc:
                # Mid-read failure. The generator has already yielded rows, so
                # keeping them would serve a TRUNCATED channel that reads as a
                # complete small one — the silent wrong answer this section's
                # attribution census exists to prevent.
                #
                # `sqlite3.Warning` IS NOT A SUBCLASS OF `sqlite3.Error`
                # (measured). Without it here, a database failure raised as a
                # Warning fell through to the generic branch below and came out
                # labelled "normalisation failed" with `source: "sqlite"` —
                # i.e. a STORE fault reported as a DATA fault, which is exactly
                # the truncated-versus-short confusion named just above.
                store_status = "unavailable"
                store_reason = (f"canal-B read failed: {type(exc).__name__}: "
                                f"{str(exc)[:200]}")
            except Exception as exc:  # noqa: BLE001 - same belt as the file path
                stream_error = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        if store is not None:
            store.close()

    if store_status not in ("ok", "absent"):
        # `unavailable` / `schema_ahead`: degraded WITH the store's reason, and
        # deliberately NO file fallback.
        return {**base, "collected": False, "status": "degraded",
                "source": store_status,
                "reason": f"canal-B store {store_status}: {store_reason}"}

    if store_status == "absent":
        source = "spool_files"
        _canal_b_mod.oublier()  # no store: no watermark, and no resident cumul kept beside the files
        if not otel_dir.exists():
            return {**base, "collected": False, "status": "degraded", "source": source,
                    "reason": "no SQLite projection yet AND state/local/otel/ does not exist - no OTLP "
                              "payload has ever been persisted (the collector is launched by the "
                              "SessionStart daemon; absence, not zero cost)"}
        files = sorted(otel_dir.glob("*.jsonl"))
        if not files:
            return {**base, "collected": False, "status": "degraded", "source": source,
                    "files_read": 0,
                    "reason": "no SQLite projection yet and state/local/otel/ holds no *.jsonl file - "
                              "absence, not zero cost"}
        try:
            envelopes, malformed = _otel_normalize_mod.iter_envelopes(otel_dir)
            records = _otel_normalize_mod.normalize_envelopes(envelopes)
        except Exception as exc:  # noqa: BLE001 - never-raises by contract; belt anyway
            return {**base, "collected": False, "status": "degraded", "source": source,
                    "files_read": len(files),
                    "reason": f"canal-B normalisation failed: {type(exc).__name__}: {str(exc)[:200]}"}
    else:
        # Already read and normalised above, inside the store's lifetime. The
        # failure is reported HERE so the degraded payload keeps the exact
        # shape and wording it had when the work happened at this line.
        if stream_error is not None:
            return {**base, "collected": False, "status": "degraded", "source": source,
                    "rows_read": rows_read, "rows_read_scope": "full" if apres is None else "increment",
                    "reason": f"canal-B normalisation failed: {stream_error}"}
        envelopes, records, rows_read, malformed = streamed or ([], [], 0, 0)

    if not records:
        read_note = (f"{len(files)} canal-B file(s)" if source == "spool_files"
                     else f"{rows_read} canal-B row(s)")
        return {**base, "collected": False, "status": "degraded", "source": source,
                "files_read": len(files), "rows_read": rows_read,
                "malformed_lines_skipped": malformed,
                "reason": (
                    f"{read_note} read, {malformed} malformed line(s), zero normalisable "
                    "record - either every line is corrupt or none matches the frozen schema"
                )}
    aggregates = _aggregate_canal_b(records, _canal_a_prompt_index(),
                                   own_project_id=own_project_id, counters=counters,
                                   envelopes=envelopes)
    value = {
        **base,
        "collected": True,
        "status": "ok",
        "source": source,
        "source_note": (
            "the SQLite projection (events.db, channel b) - the single source"
            if source == "sqlite" else
            "the spool files, because the projection does not exist yet (the "
            "daemon has never ingested); the one-shot attribution backfill has "
            "therefore not run either"
        ),
        "files_read": len(files),
        "rows_read": rows_read,
        "malformed_lines_skipped": malformed,
        # A partial read is still `ok` (the records that parsed are real), but a
        # consumer must be able to say "N lines were dropped" out loud.
        "partial": malformed > 0,
        "reason": None,
        **aggregates,
    }
    # Dated (`fraicheur`) and cached, with its duration: ok values only — a degraded one is never cached.
    return _canal_b_mod.dater(value, fingerprint, debut)


def _resolved_events_dir() -> Path | None:
    """`events.py`'s own resolution (its location or `AGENTS_EVENTS_DIR`) —
    NOT derived from `project_root`, matching `_canal_a_prompt_index`. None
    when the helper itself fails, so a caller degrades rather than raises."""
    try:
        return _events_mod._events_dir()
    except Exception:  # noqa: BLE001 - a broken helper must not take the route down
        return None


def _resolved_otel_dir() -> Path | None:
    try:
        return _otel_receiver._otel_dir()
    except Exception:  # noqa: BLE001 - same contract as above
        return None


def build_snapshot(project_root: Path | None = None) -> dict[str, Any]:
    """Aggregate TASKS.json / LEDGER.json / SPECS.json / CODEBASE_INDEX.md / the effective SCA verdict / canal-B
    cost aggregates / the six D4 view sections. Callable directly (no socket needed) so tests exercise the
    aggregation logic without a live server, mirroring `otel_receiver.process_request`'s directly-callable design.

    T-00000026 shard A: `views` is ONE new top-level key holding six independently-degrading sections
    (governance / security / memory / index / mcp / coverage) built by `dashboard_readers.build_views`. The
    pre-existing keys are untouched on purpose — `security` remains the raw effective verdict shard 1 froze, and
    `views.security` is the enriched view that REFERENCES it rather than replacing it."""
    root = Path(project_root) if project_root is not None else _project_root()
    store_fp = _store_fingerprint()  # octies F1: BEFORE any store read — at worst a rebuild, never stale
    journaux = {"empreinte": _routes_mod.empreinte_journaux(root, _EMPREINTE_CODE)}  # lot D: BEFORE them too
    ledger = _safe_load_store(_ledger_mod, root)
    specs = _safe_load_store(_specs_mod, root)
    index = _read_index_snapshot(root)
    verdict = _read_security_verdict(root)
    canal_b = _canal_b_mod.sous_verrou(_read_canal_b)()  # canal B's state is process-wide: ONE lock for it
    ingestion = _read_ingestion_status()
    built = _readers_mod.build_views(
        project_root=root,
        events_dir=_resolved_events_dir(),
        otel_dir=_resolved_otel_dir(),
        normalize_mod=_otel_normalize_mod,
        ledger_section=ledger,
        specs_section=specs,
        index_section=index,
        verdict_section=verdict,
        canal_b_section=canal_b,
        # T-00000065: the trail is READ HERE, by the module that owns the store handle, and handed down —
        # the same idiom as `normalize_mod`. The views module must not grow a second `event_store` instance
        # of its own beside this one (`_load_sibling` builds a fresh module object every call, so a second
        # load would mean two copies of that module's state).
        canal_a_stream=_read_canal_a_trail(),
        ingestion_section=ingestion,
        # octies F6: `late` ages with the clock, not with a file — it joins the key, or Couverture hides the lag.
        store_fingerprint=store_fp + (ingestion.get("late") if isinstance(ingestion, dict) else None,),
    )
    return {
        "generated_at": _now_iso(),
        "project": _read_project(root),
        "board": _safe_load_store(_tasks_mod, root),
        # S-00004739 (b): the board's verbs DROP an emptied `depends_on`, so a task served without it has none
        # declared; without this key (older server, fixture) the client cannot tell « none » from « not served ».
        "board_serves": ["depends_on"],
        "ledger": ledger,
        "specs": specs, "journaux": journaux,  # lot D: both contracts; the client re-reads the routes on it
        "index": index,
        "security": verdict,
        "canal_b": canal_b,
        "ingestion": ingestion, "setup": _readers_mod.read_setup_bilan(root),  # T-01M5A1244Z: hors `views`
        # T-00000076: reference data, not a measurement. Read here so the rate
        # table has ONE source of truth (`.agents/ref/MODEL_RATES.json`) that a
        # human maintains and the view merely prints, with its provenance.
        "rates": _readers_mod.read_model_rates(root, _utc_today()),
        "views": built["views"],
        "views_meta": built["meta"],
        "caveats": [_CROSS_PROJECT_CAVEAT, _index_caveat(root)],
    }


def _read_ingestion_status() -> dict[str, Any]:
    """Exit criterion 3's VISIBLE half: "ingestion en retard depuis X", never
    silent. Surfaced twice on purpose — at `snapshot.ingestion` for a consumer
    that wants the raw fact, and inside `views.coverage.ingestion`, because
    Couverture is the view whose entire job is saying what the trail does and
    does not cover."""
    try:
        return _event_store_mod.ingestion_status()
    except Exception as exc:  # noqa: BLE001 - a lag report must not 500 a route
        return {"source": "degraded", "late": None, "message": None,
                "reason": f"ingestion status unavailable: {type(exc).__name__}: "
                          f"{str(exc)[:200]}"}


def _store_fingerprint() -> tuple:
    """`event_store.store_fingerprint()`: a memo is invalidated by a commit that inserts or
    folds rows (its DATA generation), never by an idle tick. The stat ALONE was frozen in WAL,
    so every memo served stale rows until a restart (T-00000615); the spool alone misses a
    tick that only folds retention."""
    try:
        return _event_store_mod.store_fingerprint()
    except Exception:  # noqa: BLE001 - a cache key must never raise
        return ()


# ---------------------------------------------------------------------------
# /api/events — paginated canal-A reader. Cursor unit: BYTE OFFSET PER FILE
# (see module docstring for the line-count-vs-byte-offset cost tradeoff).
# ---------------------------------------------------------------------------

def _filters_fingerprint(filters: dict[str, str | None]) -> str:
    blob = json.dumps(filters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _encode_cursor(fingerprint: str, offsets: dict[str, int]) -> str:
    payload = json.dumps({"fp": fingerprint, "offsets": offsets}, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _encode_rowid_cursor(fingerprint: str, rowid: int) -> str:
    """T-00000049: the store's cursor is ONE integer, not a per-file offset map
    — that is the whole economy of spec §A.2's "`WHERE rowid > cursor`, end of
    the glob over hundreds of files" (the assumed cost of L-00000055, absorbed).
    A DIFFERENT payload key (`rowid`, not `offsets`) so a cursor minted in one
    mode is detectably not usable in the other rather than silently
    misinterpreted."""
    payload = json.dumps({"fp": fingerprint, "rowid": int(rowid)},
                         sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(raw: str) -> dict[str, Any] | None:
    """Returns the decoded cursor — `{"fp": ..., "offsets": {...}}` (byte-offset
    unit, file readers) or `{"fp": ..., "rowid": N}` (store unit) — or None for
    ANY malformation: bad base64, bad JSON, wrong shape. None is the single
    signal `build_events_response` needs to trigger a reset; it never raises out
    to the caller."""
    try:
        payload = base64.urlsafe_b64decode(raw.encode("ascii"))
        data = json.loads(payload.decode("utf-8"))
    except Exception:  # noqa: BLE001 - any decode failure means "invalid cursor"
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("fp"), str):
        return None
    if "rowid" in data:
        try:
            return {"fp": data["fp"], "rowid": int(data["rowid"])}
        except (TypeError, ValueError):
            return None
    if not isinstance(data.get("offsets"), dict):
        return None
    try:
        offsets = {str(k): int(v) for k, v in data["offsets"].items()}
    except (TypeError, ValueError):
        return None
    return {"fp": data["fp"], "offsets": offsets}


# T-00000026 shard A — the tail-safe canal-A reader MOVED to
# `dashboard_readers.read_new_records` and aliased back here, so canal A and
# `sca-reports/audit-log.jsonl` share ONE implementation of non-negotiable #2
# instead of two that can drift (task scope: "absorb, don't duplicate"). Every
# prior call site (`build_events_response`, `_canal_a_prompt_index`) and every
# prior test keeps referring to `dashboard._read_new_records`.
_read_new_records = _readers_mod.read_new_records


def _open_store():
    """A short-lived READ-ONLY handle on the SQLite projection, or a store whose
    `status` says why there is none. `create=False` without exception: creating
    the database is the DAEMON's job (sole writer), never a reader's."""
    try:
        return _event_store_mod.open_store(create=False)
    except Exception:  # noqa: BLE001 - a reader degrades, never 500s
        return None


def _read_digest_aggregates(store: Any = None) -> dict[str, Any]:
    """Digests from the `digests` TABLE when the store is live, from the legacy
    `state/events/digest/*.json` files otherwise.

    Not a preference, a correctness rule (plan-critic iteration 1, C3): once the
    ingestion starts emptying the spool, those JSON files stop being written and
    FREEZE. Serving a frozen aggregate that still renders as a number is worse
    than serving none — it is the L-00000010 false-GO shape applied to counts."""
    if store is not None and getattr(store, "status", None) == "ok":
        return _read_digest_aggregates_from_store(store)
    digest_dir = _events_mod._digest_dir()
    months: list[dict[str, Any]] = []
    if digest_dir.exists():
        for path in sorted(digest_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            months.append({
                "month": data.get("month"),
                "total_events": data.get("total_events"),
                "by_kind": data.get("by_kind"),
                "by_agent": data.get("by_agent"),
                "by_task": data.get("by_task"),
            })
    return {"months": months, "label": _DIGEST_LABEL, "source": "digest_files"}


def _read_digest_aggregates_from_store(store: Any) -> dict[str, Any]:
    try:
        return store.digest_aggregates()
    except Exception as exc:  # noqa: BLE001 - see _read_digest_aggregates
        return {"months": [], "label": _DIGEST_LABEL, "source": "unavailable",
                "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _first(qs: dict[str, list[str]], name: str) -> str | None:
    values = qs.get(name)
    return values[0] if values else None


def build_events_response(qs: dict[str, list[str]]) -> dict[str, Any]:
    """Paginated canal-A read. `qs` is the already-parsed query string
    (`urllib.parse.parse_qs` output) - never a raw path, never opened as a
    file. Callable directly (no socket) for the same reason as
    `build_snapshot`.

    T-00000049 — TWO SOURCES, ONE CONTRACT. When the SQLite projection exists
    this reads `WHERE rowid > cursor`; otherwise it globs the spool files
    exactly as before. Every field of the response keeps its name AND its
    meaning, which is why `cursor_unit` was a self-describing field from day one
    (plan-critic iteration 1, C7): it now reads `db_rowid` instead of
    `byte_offset_per_file`, `source` names the source out loud, and
    `pruned_files` stays present-and-empty in store mode rather than
    disappearing from the payload. A cursor minted under the other unit is
    rejected through the ALREADY EXISTING reset path
    (`cursor_reset_reason: "cursor_unit_changed"`), never silently
    reinterpreted as an integer or an offset map."""
    task = _first(qs, "task") or None
    kind = _first(qs, "kind") or None
    agent = _first(qs, "agent") or None
    since = _first(qs, "since") or None
    cursor_raw = _first(qs, "cursor") or None

    filters = {"task": task, "kind": kind, "agent": agent}
    fingerprint = _filters_fingerprint(filters)

    store = _open_store()
    if store is not None and store.status == "absent":
        # No database yet: the spool files ARE the truth, not a fallback.
        store.close()
        store = None
    if store is not None:
        # `_events_from_store` owns the handle from here (it closes it, in every
        # branch including the degraded ones).
        return _events_from_store(
            store, fingerprint, cursor_raw,
            task=task, kind=kind, agent=agent, since=since,
        )
    return _events_from_spool_files(
        None, fingerprint, cursor_raw,
        task=task, kind=kind, agent=agent, since=since,
    )


def _events_from_store(store: Any, fingerprint: str, cursor_raw: str | None, *,
                       task: str | None, kind: str | None, agent: str | None,
                       since: str | None) -> dict[str, Any]:
    """`WHERE rowid > cursor` — one indexed range scan instead of a glob plus a
    read of every file (spec §A.2). A store in `schema_ahead` / `unavailable`
    status serves a KNOWN-SHAPE degraded payload and runs no SQL at all
    (iteration 2, C1: "the API still serves" is unfalsifiable if any v1
    statement against a v2 schema raises a 500)."""
    try:
        after = 0
        cursor_reset = False
        cursor_reset_reason: str | None = None
        since_effective = since
        if cursor_raw:
            # Non-negotiable #4 unchanged: a supplied cursor, valid or not, wins
            # over `since` absolutely.
            since_effective = None
            decoded = _decode_cursor(cursor_raw)
            if decoded is None:
                cursor_reset = True
                cursor_reset_reason = "malformed_cursor"
            elif decoded["fp"] != fingerprint:
                cursor_reset = True
                cursor_reset_reason = "filters_changed"
            elif "rowid" not in decoded:
                cursor_reset = True
                cursor_reset_reason = "cursor_unit_changed"
            else:
                after = max(0, int(decoded["rowid"]))

        if store.status != "ok":
            return {
                "events": [], "next_cursor": _encode_rowid_cursor(fingerprint, after),
                "has_more": False, "cursor_unit": "db_rowid",
                "cursor_reset": cursor_reset, "cursor_reset_reason": cursor_reset_reason,
                "pruned_files": [], "malformed_lines_skipped": 0,
                "aggregates": _read_digest_aggregates(store),
                "source": store.status, "degraded": True, "reason": store.reason,
            }

        page = store.query_events(
            after, task=task, kind=kind, agent=agent, since=since_effective,
            limit=_EVENTS_PAGE_LIMIT,
        )
        return {
            "events": page["records"],
            "next_cursor": _encode_rowid_cursor(fingerprint, page["next_rowid"]),
            "has_more": page["has_more"],
            "cursor_unit": "db_rowid",
            "cursor_reset": cursor_reset,
            "cursor_reset_reason": cursor_reset_reason,
            # Kept in the payload, deliberately empty: the store's identity is
            # per RECORD, so a consumed spool file being removed no longer
            # invalidates anything a cursor points at. Nothing to prune, and the
            # field says so instead of vanishing.
            "pruned_files": [],
            "malformed_lines_skipped": page.get("malformed_lines_skipped", 0),
            "aggregates": _read_digest_aggregates(store),
            "source": "sqlite",
            "degraded": False,
            "reason": None,
        }
    finally:
        store.close()


def _events_from_spool_files(store: Any, fingerprint: str, cursor_raw: str | None, *,
                             task: str | None, kind: str | None, agent: str | None,
                             since: str | None) -> dict[str, Any]:
    """The pre-V1-b path, byte offsets per file — still the truth before the
    daemon has ever ingested anything, and after an `--export-spool` rollback."""
    offsets: dict[str, int] = {}
    cursor_reset = False
    cursor_reset_reason: str | None = None
    since_effective = since

    if cursor_raw:
        # Non-negotiable #4: cursor precedence is absolute whenever supplied,
        # valid or not - `since` is never consulted once a cursor is present.
        since_effective = None
        decoded = _decode_cursor(cursor_raw)
        if decoded is None:
            cursor_reset = True
            cursor_reset_reason = "malformed_cursor"
        elif decoded["fp"] != fingerprint:
            cursor_reset = True
            cursor_reset_reason = "filters_changed"
        elif "offsets" not in decoded:
            cursor_reset = True
            cursor_reset_reason = "cursor_unit_changed"
        else:
            offsets = decoded["offsets"]

    events_dir = _events_mod._events_dir()
    files_on_disk = sorted(p.name for p in events_dir.glob("*.jsonl")) if events_dir.exists() else []
    files_on_disk_set = set(files_on_disk)

    # Non-negotiable #3: compact() may have deleted a file this cursor still
    # references - prune, and say so, never silently drop.
    pruned_files = sorted(name for name in offsets if name not in files_on_disk_set)
    for name in pruned_files:
        offsets.pop(name, None)

    candidates: list[dict[str, Any]] = []
    malformed_total = 0
    for name in files_on_disk:
        start = offsets.get(name, 0)
        records, malformed = _read_new_records(events_dir / name, start)
        malformed_total += malformed
        for end_offset, record in records:
            candidates.append({"file": name, "end_offset": end_offset, "record": record})

    candidates.sort(key=lambda c: (c["record"].get("ts") or "", c["file"], c["end_offset"]))

    def _matches(record: dict[str, Any]) -> bool:
        if task and record.get("task") != task:
            return False
        if kind and record.get("kind") != kind:
            return False
        if agent and record.get("agent") != agent:
            return False
        if since_effective and (record.get("ts") or "") < since_effective:
            return False
        return True

    page_events: list[dict[str, Any]] = []
    new_offsets = dict(offsets)
    has_more = False
    for cand in candidates:
        if len(page_events) >= _EVENTS_PAGE_LIMIT:
            has_more = True
            break
        # Advance the offset for EVERY candidate considered, matched or not -
        # a filtered-out record has still been "seen" and must not be
        # re-scanned forever on every subsequent poll.
        new_offsets[cand["file"]] = cand["end_offset"]
        if _matches(cand["record"]):
            page_events.append(cand["record"])

    return {
        "events": page_events,
        "next_cursor": _encode_cursor(fingerprint, new_offsets),
        "has_more": has_more,
        "cursor_unit": "byte_offset_per_file",
        "cursor_reset": cursor_reset,
        "cursor_reset_reason": cursor_reset_reason,
        "pruned_files": pruned_files,
        "malformed_lines_skipped": malformed_total,
        "aggregates": _read_digest_aggregates(store),
        "source": "spool_files",
        "degraded": False,
        "reason": None,
    }


# ---------------------------------------------------------------------------
# /api/projects — the versioned contract a future hub reads (T-00000051, V1-d;
# spec §A.5). GET only, token-only, ZERO query parameter, no write path.
#
# WHY A ROUTE AND NOT A SNAPSHOT KEY. `/api/snapshot` is ~166 KB of this
# project's own state. A hub asking "which projects does this daemon speak for,
# and can I still talk to it?" must not pay that read, and must be able to ask
# it of a daemon whose payload version it does not yet understand — hence
# `api_version` (an INTEGER, the MAJOR only: a minor addition is additive by
# definition and a consumer that pinned a minor would break on a new key it was
# free to ignore) and `kind`, a literal a hub can match before parsing anything
# else. Doctrine T-00000040: a v1.x hub must be able to interrogate a v1 daemon
# without breaking it.
#
# WHAT THIS ROUTE DOES **NOT** GUARANTEE — every line here is a real,
# reachable limitation, and the register is part of the frozen contract:
#   - THAT A PROJECT EXISTS. `projects` is legitimately empty. `identity` says
#     why, in a closed vocabulary; an empty list is never an error and never a
#     500.
#   - THAT THE LIST COVERS THE MACHINE. It is 0 or 1 entry: THIS daemon's own
#     identity. There is no discovery, no disk scan (rejected, design doc §B.3),
#     no registry yet — the hub and its push registration are V1.x+ (§B.4).
#   - THAT THIS DAEMON HOLDS PORT 4318. The OTLP receiver is machine-global and
#     elected by bind; a neighbouring project's daemon may hold it. Being listed
#     here says nothing about who collects canal B.
#   - A STABLE ORDER. With at most one entry the question is moot today, and a
#     consumer that starts depending on position would break the day the hub
#     merges several daemons. Match on `project_id`, never on index.
#   - THE HEADERS OF A REJECTION. The 200 carries `Cache-Control: no-store`; a
#     401 or a wrong-verb 404 goes through `_reject`, which sends no
#     `Cache-Control` at all. Said plainly because the alternative is a consumer
#     asserting a header it will not get.
#   - THAT THE HEADER BADGE'S NAME COMES FROM THE SAME FILE. `snapshot.project`
#     is read from `project_root` while this route reads
#     `event_store.project_json_path()` (anchored on `__file__`, overridden by
#     `AGENTS_PROJECT_JSON`). Under `--root` or that env var the two anchors
#     differ. That is a DEFECT, tracked as T-00000056 and to be fixed at the
#     root — not a field to publish, and NOT presumed absent by anything
#     actionable: no node of the UI selector claims a success or prescribes a
#     command (`docs/modules/dashboard-api.md` carries the actionable remedy,
#     where it can be qualified).
#   - FRESHNESS. In `live` mode the SSE stream is the UI's clock
#     (`app.js:startPolling()` hands back when a stream is open) and
#     `project.json` is NOT part of the snapshot fingerprint, so an identity
#     created DURING a session may only be picked up at the next change notice.
#     No loop is possible from this: a GET here never changes
#     `identity.status`.
# ---------------------------------------------------------------------------

# MAJOR only, by contract. Bumped ONLY for a breaking change; a new key is
# additive and does not touch it.
PROJECTS_API_VERSION = 1

# `kind` is matched by consumers BEFORE they trust any other key, so it is a
# literal with a namespace, not a bare word that could collide.
PROJECTS_KIND = "agentkit.projects"

_PROJECTS_SCOPE_CAVEAT = (
    "projects_scope: this list is THIS daemon's OWN identity, 0 or 1 entry — "
    "never a census of the machine. There is no discovery and no disk scan "
    "(rejected by design, spec §B.3); the multi-project hub and its push "
    "registration are explicitly out of v1 (§B.4). An empty list means 'this "
    "daemon has no usable project_id', which `identity` explains — never 'this "
    "machine has no project'."
)

_PROJECTS_PORT_CAVEAT = (
    "projects_not_a_4318_claim: the OTLP receiver on 4318 is machine-global and "
    "elected by bind, so being listed here says NOTHING about which daemon "
    "collects canal B for this machine (L-00000049)."
)

_PROJECTS_ANCHOR_CAVEAT = (
    "projects_anchor: this route resolves event_store.project_json_path() (the "
    "anchor rows are actually stored under), while the header badge of "
    "/api/snapshot reads project_root/.agents/state/project.json. Under --root "
    "or AGENTS_PROJECT_JSON those two paths differ — a defect tracked as "
    "T-00000056, not a property to rely on. Nothing here presumes they agree. "
    "Since T-00000582 the split is now INSIDE one response: project_id comes from "
    "project_json_path() (anchor 2), but name and label are derived from the "
    "root this handler received (the daemon's --root), so under "
    "--root/AGENTS_PROJECT_JSON the two can describe different repositories. "
    "T-00000056 is moved inside the payload, not closed."
)

_PROJECTS_FRESHNESS_CAVEAT = (
    "projects_freshness: project.json is not part of the snapshot fingerprint "
    "and, in `live` mode, the SSE stream is the UI's clock — so an identity "
    "created during a session may only be observed at the next change notice. "
    "This response is a point-in-time read, never a subscription."
)

_PROJECTS_ORDER_CAVEAT = (
    "projects_order: no stable order is promised. Match on `project_id`, never "
    "on position — a future hub merging several daemons would break any "
    "consumer that indexed."
)


def build_projects_response(project_root: Path | None = None) -> dict[str, Any]:
    """The `/api/projects` payload. ONE read of the identity file, no query
    parameter, no exception (a resolver that 500s a route is the bug this
    function exists to avoid).

    `name`/`label` are DERIVED from `project_root` (T-00000582, S-00001541): the
    basename of the HANDLER's root (the daemon's --root), or `_project_root()`
    when called without an argument (existing tests, direct calls). `label` is
    ALWAYS a non-empty string a UI can render as-is (the basename, or the literal
    `"projet"` on an empty basename), so a `<select>` never renders a blank
    option. NEVER `project.json:name` (parsed by `_resolve_identity_once`, but
    ignored here). "Never the slug" is NO LONGER an invariant (T-00000582): the
    label is the root basename, so a repo cloned into a directory that happens to
    carry its own slug would give `label == slug` INCIDENTALLY — the slug is
    never CHOSEN as a source, it is simply a basename that coincides.
    `project_id`/`slug` still come from the project.json parse (anchor 2), so the
    two anchors can diverge under --root — T-00000056, moved INSIDE this response
    (see _PROJECTS_ANCHOR_CAVEAT).

    `projects` holds an entry IF AND ONLY IF `identity.status == "ok"`, i.e. a
    usable `project_id`: never `null`, never the `PROJECT_UNSET` sentinel — the
    latter is a NON-EMPTY string that would collide with every uninitialised
    repo on the machine, so it maps to `incomplete` + `[]`."""
    identity = _resolve_identity_once(_event_store_mod.project_json_path())
    projects: list[dict[str, Any]] = []
    if identity["status"] == "ok":
        project_id = identity["project_id"]
        # ROOT-derived, never `identity["name"]`. Always non-empty, so
        # `label == name`; no `"projet #<id>"` fallback branch (it would be dead
        # code — the one branch a mutation could hide behind).
        name = _nom_depuis_racine(project_root if project_root is not None
                                  else _project_root())
        projects.append({
            "project_id": project_id,
            "label": name,
            "name": name,
            "slug": identity["slug"],
        })
    return {
        "api_version": PROJECTS_API_VERSION,
        "kind": PROJECTS_KIND,
        "generated_at": _now_iso(),
        "projects": projects,
        "identity": {"status": identity["status"], "cause": identity["cause"]},
        "caveats": [
            _PROJECTS_SCOPE_CAVEAT, _PROJECTS_PORT_CAVEAT, _PROJECTS_ANCHOR_CAVEAT,
            _PROJECTS_FRESHNESS_CAVEAT, _PROJECTS_ORDER_CAVEAT,
        ],
    }


# ---------------------------------------------------------------------------
# T-00000083 — the federation pair: what THIS daemon tells its peers
# (`/api/peer/summary`, unauthenticated) and what it tells its OWN UI about
# them (`/api/peers`, token required).
#
# THE ASYMMETRY IS THE DESIGN. A peer summary crosses a trust boundary, so it
# is a FIXED, CLOSED key set that a reviewer can read in ten seconds; the peers
# list stays behind the token because it aggregates several projects and names
# their ports. `/api/projects` is FROZEN and untouched by this task — a hub
# that only wants "who are you?" keeps reading it.
#
# NEITHER FUNCTION WRITES ANYTHING. In particular `/api/peers` applies the
# registry's tri-state liveness but never garbage-collects: a GET a browser
# polls every few seconds must not be able to delete another project's entry
# (the daemon does that, at its own start and stop).
# ---------------------------------------------------------------------------

PEER_API_VERSION = 1
PEER_SUMMARY_KIND = "agentkit.peer_summary"
PEERS_KIND = "agentkit.peers"

# THE key sets of the peer contract, spelled ONCE so the producing side
# (`build_peer_summary`) and the consuming side (`build_peers_response`, which
# re-publishes what a peer said) cannot drift apart.
_PEER_SUMMARY_FIELDS = ("api_version", "kind", "project_id", "name", "label",
                        "task", "health", "generated_at")
_PEER_TASK_FIELDS = ("id", "title", "stage")
_PEER_HEALTH_FIELDS = ("serving", "otel")


def _peer_label(project_id: str, name: Any) -> str:
    """The SAME rule as `build_projects_response`: the human `name` when
    usable, else `"projet #" + project_id[:8]`. Never the slug (a filesystem
    key, not a display name) and NEVER `""`, which a `<select>` renders as a
    blank selected option that looks like a bug."""
    return name if isinstance(name, str) and name.strip() else f"projet #{project_id[:8]}"


def _running_task(project_root: Path) -> dict[str, Any] | None:
    """The FOCUS task of this project's board, reduced to `{id, title, stage}`
    — or None (nothing running, or a board this function refuses to fail on).

    ONE FOCUS, NAMED ONCE. A board may carry several `running` tasks,
    independent or grouped; `tasks.py parallel` proves a group's declared
    write-set disjunction. `tasks.focus_task` selects the FIRST running task in store
    order, which is creation order. The rule is IMPORTED rather than re-coded
    here, so the statusline and this payload can never name a different task.

    THE PEER CONTRACT DOES NOT MOVE. `task` stays SINGULAR and equal to the
    focus: another project reads this stream, and adding a key or a version to
    describe an internal board change would cross a trust boundary for nothing.
    A group's other members are simply not part of what a peer is told.

    Deliberately NOT `_safe_load_store` + the whole board: a peer gets one
    line, not a census, and `tasks.load()` raises on a malformed board by
    design. Here that must degrade to `null`, because the consumer is another
    project and "your neighbour's board is corrupt" is not its problem."""
    try:
        board = _tasks_mod.load(project_root)
        task = _tasks_mod.focus_task(board.get("tasks", []))
    except Exception:  # noqa: BLE001 - a neighbour's broken board is not an error here
        return None
    if task is None:
        return None
    return {
        "id": task.get("id"),
        "title": task.get("task"),
        "stage": task.get("stage") or None,
    }


def build_peer_summary(project_root: Path | None = None) -> dict[str, Any]:
    """The `/api/peer/summary` payload — the ONLY thing this daemon says to a
    process that holds no token.

    THE KEY SET IS CLOSED AND ASSERTED IN THE TESTS: `api_version`, `kind`,
    `project_id`, `name`, `label`, `task`, `health`, `generated_at`. A key
    added here crosses a trust boundary, so it must be a deliberate decision,
    not a drive-by.

    Never raises: every input degrades to a null/`unknown` rather than a 500
    (a peer that 500s looks *dead* to the prober, which is worse than a peer
    that answers "I don't know")."""
    root = Path(project_root) if project_root is not None else _project_root()
    identity = _resolve_identity_once(_event_store_mod.project_json_path())
    project_id = identity["project_id"]  # PROJECT_UNSET when there is no usable id
    # T-00000582: name/label are a property of the ROOT, not of the identity
    # file (S-00001541), so they are the basename WHATEVER identity.status is —
    # even with no usable project_id (PROJECT_UNSET), where the old code
    # published name=None + "projet #<id>". `project_id` alone stays
    # conditional. Asymmetry with the badge (which keeps name:None under
    # `unnamed`, pinned by two equality nets) is assumed, written in the plan.
    nom = _nom_depuis_racine(root)
    return {
        "api_version": PEER_API_VERSION,
        "kind": PEER_SUMMARY_KIND,
        "project_id": project_id,
        "name": nom,
        "label": nom,
        "task": _running_task(root),
        # `serving` is a tautology ON PURPOSE: this payload only ever exists
        # because a request was served, and a prober that can read it has its
        # answer. `otel` is the one nuance a peer can act on (L-00000049: 4318
        # is machine-global and elected by bind).
        "health": {"serving": True, "otel": _handoff_mod.lock_health(root)},
        "generated_at": _now_iso(),
    }


def _sanitised_peer_summary(payload: Any) -> dict[str, Any] | None:
    """A peer's answer, reduced to the SAME closed key set this daemon itself
    publishes — nested `task` and `health` included.

    WHY (security review, T-00000083): what comes back from `/api/peer/summary`
    is a foreign process's JSON. Re-echoing it verbatim under `peers[].summary`
    would make this token-protected route a pass-through for whatever a
    co-resident process decided to put on that port, straight into this
    project's UI. The contract is what we accept, not what they send: unknown
    keys are DROPPED (never merely ignored downstream), and every declared key
    is present so a consumer never has to feature-detect.

    Returns None for anything that is not an object."""
    if not isinstance(payload, dict):
        return None
    task = payload.get("task")
    health = payload.get("health")
    clean: dict[str, Any] = {field: payload.get(field) for field in _PEER_SUMMARY_FIELDS}
    clean["task"] = ({field: task.get(field) for field in _PEER_TASK_FIELDS}
                     if isinstance(task, dict) else None)
    clean["health"] = ({field: health.get(field) for field in _PEER_HEALTH_FIELDS}
                       if isinstance(health, dict) else None)
    return clean


def build_peers_response() -> dict[str, Any]:
    """The `/api/peers` payload — this machine's OTHER dashboards, as seen
    through `~/.agentkit/registry.json`.

    `self` is this daemon's own project id (or `PROJECT_UNSET`), and its entry
    is EXCLUDED from `peers`: the UI already knows about itself, and listing it
    would make "how many peers?" ambiguous.

    LIVENESS IS TRI-STATE UPSTREAM, BOOLEAN HERE: `dead` and `indeterminate`
    both render as `alive: false`, and the difference only ever matters to the
    registry's GC (which runs in the daemon, not here — this route never
    writes). So a peer whose port timed out is listed, dimmed, and comes back
    by itself on the next poll if it was merely busy.

    Sequential probing, 0.5 s each: a machine with a handful of projects is the
    case this serves, and a thread pool would buy milliseconds at the cost of a
    concurrency story in a read-only route."""
    identity = _resolve_identity_once(_event_store_mod.project_json_path())
    own = identity["project_id"]
    registry, state = _registry_mod.read_registry_state()
    peers: list[dict[str, Any]] = []
    for project_id, entry in sorted(registry["projects"].items()):
        if project_id == own:
            continue
        verdict, summary = _registry_mod.inspect_entry(entry)
        port = entry.get("port")
        peers.append({
            "project_id": project_id,
            "name": entry.get("name"),
            "label": _peer_label(project_id, entry.get("name")),
            "port": port if isinstance(port, int) else None,
            "alive": verdict == _registry_mod.ALIVE,
            # FILTERED, never echoed raw: see `_sanitised_peer_summary`.
            "summary": _sanitised_peer_summary(summary),
        })
    return {
        "api_version": PEER_API_VERSION,
        "kind": PEERS_KIND,
        "self": own,
        "peers": peers,
        "registry": state,
        "generated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# /api/sessions — the console event feed (T-00000086, M5a). READ ONLY, GET only,
# token-required, three query parameters, ZERO write path.
#
# WHY IT IS NOT A KEY OF `/api/snapshot`. That payload is memoised on this
# project's FILES and is already ~166 KB; this one is a windowed group-by over
# the event store with its own filters, refreshed on canal-A change notices
# rather than on the 5 s snapshot tick. Folding it in would make every snapshot
# poll pay for a query nobody asked for, and would leave the filters nowhere to
# live.
#
# WHAT THIS ROUTE CANNOT DO, STATED RATHER THAN IMPLIED. It cannot answer a
# question posed in a console, it cannot inject a keystroke, and it cannot even
# TELL you that a console is waiting for one — see `_PENDING_COVERAGE`. The
# writing half is T-00000088, deliberately blocked behind the T-00000028 gate;
# the sensing half is T-00000090. A section that quietly rendered "no session is
# waiting" out of an unwired sensor would be the L-010 false-GO shape applied to
# a human's attention, so the coverage note travels IN the payload.
#
# NO SPOOL FALLBACK, ON PURPOSE. `/api/events` globs the spool when there is no
# database, because before the first ingestion those files ARE the truth. This
# route does not: its whole shape is a SQL group-by, and a hand-rolled Python
# re-implementation over globbed files would be a second source for one figure —
# the shape every duplication defect in the store came from. No projection means
# "no projection", said out loud.
# ---------------------------------------------------------------------------

SESSIONS_API_VERSION = 1
SESSIONS_KIND = "agentkit.sessions"

# A query value longer than this is truncated before it reaches a bound
# parameter. Not a safety property (every value below is bound, never
# interpolated) — a bound: a 4 MB `host=` is a pointless allocation on a route
# that answers in milliseconds.
_SESSIONS_PARAM_MAX = 200

# THE HONEST ANSWER TO "which console is waiting for me?", which is: we cannot
# tell yet, and here is why.
#
# `covered_hosts` is EMPTY and that is a measurement of the wiring, not of the
# consoles. No host registers a Notification-class hook today, and
# `events.KNOWN_KINDS` — the closed vocabulary canal A validates against —
# contains no member a "waiting for input" signal could be emitted under. So the
# marker is not merely unlit: it is structurally unlightable, and the UI is told
# so rather than being left to infer silence from an empty list.
_PENDING_COVERAGE = {
    "covered_hosts": ["claude-code"],
    "note": (
        "« question en attente » est câblé sur Claude Code SEUL (T-00000090) : "
        "son hook Notification émet `session.notify`. Les trois autres hosts ne "
        "sont PAS couverts, et pas par oubli — Codex, Copilot et "
        "Gemini/Antigravity n'exposent aucun événement de classe Notification, "
        "donc il n'y a rien à y enregistrer. Sur eux le marqueur reste "
        "structurellement éteint : une session Codex qui attend une réponse ne "
        "s'affichera pas ici, et ce n'est PAS la mesure « aucune session "
        "n'attend ». Lire ce badge comme une couverture des quatre hosts serait "
        "exactement le faux-GO de L-010 appliqué à l'attention d'un humain."
    ),
}


def _sessions_param(qs: dict[str, list[str]], name: str) -> str | None:
    raw = _first(qs, name)
    if raw is None:
        return None
    value = raw.strip()[:_SESSIONS_PARAM_MAX]
    return value or None


def build_sessions_response(qs: dict[str, list[str]]) -> dict[str, Any]:
    """The `/api/sessions` payload — canal-A events grouped by (host, session)
    over a bounded window. `qs` is the parsed query string
    (`urllib.parse.parse_qs` output): `host`, `project`, `since` (ISO). Callable
    directly, no socket, like `build_snapshot` and `build_events_response`.

    THE STORE DOES THE WORK. Every bound (window, sessions, events per session,
    facets) lives in `EventStore.session_feed` and is declared in its own
    response; this function adds the route's contract fields
    (`api_version`/`kind`/`generated_at`), the coverage note, and ONE degraded
    branch for "there is no projection to read".

    Never raises. Three distinct absences, three distinct payloads, none of them
    an empty list:
      * no database at all      → `source: "absent"`, and the reason says the
                                  daemon has not ingested rather than implying
                                  no sessions exist;
      * a database this build   → `source: <store.status>` (`schema_ahead` /
        cannot read              `unavailable`), reason carried through, and NO
                                  SQL is attempted (the same posture as
                                  `_events_from_store`: "the API still serves"
                                  is unfalsifiable if a v1 statement against a
                                  v2 schema raises a 500);
      * a readable store        → the feed, with its own truncation flags.
    """
    host = _sessions_param(qs, "host")
    project = _sessions_param(qs, "project")
    since = _sessions_param(qs, "since")

    envelope: dict[str, Any] = {
        "api_version": SESSIONS_API_VERSION,
        "kind": SESSIONS_KIND,
        "generated_at": _now_iso(),
        "pending_coverage": dict(_PENDING_COVERAGE),
    }

    store = _open_store()
    if store is not None and store.status == "absent":
        store.close()
        store = None
    if store is None:
        return {**envelope, **_sessions_degraded(
            "absent",
            "projection absente — le démon dashboard n'a encore rien ingéré "
            "(cette section n'a pas de seconde source : elle ne retombe jamais "
            "sur les fichiers spool)",
            host, project, since)}
    try:
        if store.status != "ok":
            return {**envelope, **_sessions_degraded(
                store.status, store.reason, host, project, since)}
        feed = store.session_feed(since, host=host, project=project)
    except Exception as exc:  # noqa: BLE001 - a reader degrades, never 500s
        return {**envelope, **_sessions_degraded(
            "unavailable", f"{type(exc).__name__}: {str(exc)[:200]}",
            host, project, since)}
    finally:
        store.close()
    return {**envelope, **feed, "source": "sqlite", "degraded": False}


def _sessions_degraded(source: str, reason: str | None, host: str | None,
                       project: str | None, since: str | None) -> dict[str, Any]:
    """The KNOWN-SHAPE degraded body: every key the nominal payload carries is
    present and empty, so a consumer never has to feature-detect and an absent
    section can never be mistaken for a measured zero. Same discipline as
    `_events_from_store`'s degraded branch."""
    return {
        "status": source,
        "reason": reason,
        # The SAME window resolver the nominal path uses, so a degraded payload
        # still states which window was asked for instead of dropping the one
        # field that says "we looked HERE and could not read".
        "window": _event_store_mod._session_feed_window(
            since, datetime.now(timezone.utc)),
        "sessions": [],
        "sessionless": {"count": 0, "by_host": {}},
        "total_sessions": 0,
        "truncated_sessions": False,
        "caps": _event_store_mod._session_feed_caps(None),
        "filters": {"host": host, "project": project},
        "filters_available": {"hosts": [], "projects": [], "truncated": False},
        "malformed_skipped": 0,
        "source": source,
        "degraded": True,
    }


# ---------------------------------------------------------------------------
# /api/term — the mirror INVENTORY (T-00000087, M5b). READ ONLY, GET only,
# token-required, no parameter, ZERO write path.
#
# WHY IT IS NOT A KEY OF `/api/sessions`. That route groups canal-A EVENTS by
# (host, session): structured records emitted by hooks. This one lists SPOOLS:
# files written by `wrap.py` for the consoles that happen to have been launched
# through it. The two sets overlap by accident, not by construction — a session
# can have events and no mirror (started by hand, the ordinary case today) or a
# mirror and no events (a CLI this kit ships no hooks for). Folding one into the
# other would force a join on a key neither side owns, and would let an absent
# mirror read as an absent session.
#
# A MIRROR EXISTS ONLY FOR WHAT WENT THROUGH THE WRAPPER, and that is the one
# thing this payload must never let a reader forget. There is no way to attach
# to an already-open terminal; `Sessions.jsx` badges the sessions with no spool
# « événements seulement » rather than rendering silence.
#
# THREE STATES, NOT TWO. `ended` present → "ended". `ended` absent and the pid
# alive → "live". `ended` absent and the pid gone (or unresolvable) → "unknown":
# the wrapper died without closing its spool. Calling that "live" shows a ghost
# and calling it "ended" claims a clean finish that did not happen, so it gets
# its own word — the same doctrine `_PENDING_COVERAGE` applies to an unlit
# marker one route above.
# ---------------------------------------------------------------------------

def _term_dir() -> Path | None:
    """`wrap.py`'s OWN resolution, never a second derivation of the same path
    (L-00000057). None when the helper itself fails, so a route degrades rather
    than raises."""
    try:
        return _wrap_mod.term_dir()
    except Exception:  # noqa: BLE001 - a broken helper must not take a route down
        return None


def _term_state(meta: dict[str, Any]) -> str:
    if meta.get("ended"):
        return "ended"
    alive = _wrap_mod.pid_alive(meta.get("pid"))
    if alive is True:
        return "live"
    if alive is False:
        return "unknown"
    return "unknown"


def _term_entry(directory: Path, sid: str) -> dict[str, Any] | None:
    """One inventory row, or None when the pair is unreadable. Never raises."""
    meta = _wrap_mod.read_meta(directory / f"{sid}.meta.json")
    if meta is None or meta.get("sid") != sid:
        return None
    try:
        size = (directory / f"{sid}.raw").stat().st_size
    except OSError:
        size = 0
    return {
        "sid": sid,
        # BASENAME ONLY — `wrap.py` never records the argv, so there is nothing
        # here to leak even if a reader wanted it.
        "cmd": str(meta.get("cmd") or "")[:120],
        "state": _term_state(meta),
        "pid": meta.get("pid"),
        "cols": meta.get("cols"),
        "rows": meta.get("rows"),
        # "posix" | "poll" | "frozen" — a UI that draws a fixed-size terminal
        # must be able to SAY it is fixed instead of implying it follows.
        "resize": meta.get("resize"),
        "started": meta.get("started"),
        "ended": meta.get("ended"),
        "gen": meta.get("gen", 0),
        "bytes": size,
    }


def build_term_response() -> dict[str, Any]:
    """The `/api/term` payload — the mirror spools this project can serve.
    Callable directly, no socket, like every other `build_*` in this file.

    Never raises. Two distinct absences, two distinct payloads, neither of them
    an empty list without a reason:
      * no spool directory at all → `status: "absent"`, and the reason says NO
        CONSOLE HAS BEEN LAUNCHED THROUGH THE WRAPPER rather than implying no
        console is running;
      * an unreadable directory   → `status: "unavailable"` with the exception
                                    class, same posture as every other reader.
    """
    envelope: dict[str, Any] = {
        "api_version": TERM_API_VERSION,
        "kind": TERM_KIND,
        "generated_at": _now_iso(),
        "caps": {
            "sessions": _TERM_MAX_SESSIONS,
            "catchup_bytes": _TERM_CATCHUP_BYTES,
            "tick_bytes": _TERM_MAX_TICK_BYTES,
            "concurrent_streams": _MAX_TERM_STREAMS,
        },
        "coverage": (
            "un miroir n'existe QUE pour les consoles lancées via "
            "`python .agents/bin/wrap.py <cli>` : un terminal déjà ouvert est "
            "invisible par construction, ce n'est pas une mesure « rien ne "
            "tourne ». Sens unique strict — aucune frappe ne remonte "
            "(l'injection est T-00000088, derrière le gate T-00000028)."
        ),
    }
    directory = _term_dir()
    if directory is None or not directory.is_dir():
        return {**envelope, "status": "absent", "degraded": True,
                "reason": ("aucun spool de miroir — aucune console n'a encore été "
                           "lancée via wrap.py sur ce projet"),
                "sessions": [], "total": 0, "truncated": False}
    try:
        sids = sorted(
            (path.name[: -len(".meta.json")] for path in directory.glob("*.meta.json")),
            reverse=True,  # the sid starts with a UTC timestamp: newest first
        )
    except OSError as exc:
        return {**envelope, "status": "unavailable", "degraded": True,
                "reason": f"{type(exc).__name__}", "sessions": [], "total": 0,
                "truncated": False}
    entries = []
    for sid in sids:
        if len(entries) >= _TERM_MAX_SESSIONS:
            break
        entry = _term_entry(directory, sid)
        if entry is not None:
            entries.append(entry)
    return {**envelope, "status": "ok", "degraded": False, "reason": None,
            "sessions": entries, "total": len(sids),
            "truncated": len(sids) > len(entries)}


# ---------------------------------------------------------------------------
# HTTP handler (finding B3) - standalone, GET-only, the token-required `/api/*`
# routes of `_ALLOWED_UI_PATHS` (the count) plus the closed static table and the
# closed token-exempt peer table, nothing shared with OTLPHandler.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# T-00000028 — the ONE way this server runs anything. Every write route goes
# through here and nothing else does.
# ---------------------------------------------------------------------------

def _cli_argv(script: str, *args: str) -> list[str]:
    """`[interpreter, <this directory>/<script>, *args]`.

    A LIST, always — `shell=True` appears nowhere in this module and must not:
    every argument below carries request-controlled text (a task id, a package
    name, a waiver reason), and a shell in that path turns a bounded 400 into
    command injection. Argv-list execution has no shell to inject into.

    The script is resolved from THIS FILE's directory (`HERE`), never from the
    request and never from cwd: the set of programs this server can start is
    fixed at import time, and `script` is only ever one of three literals
    written in the calls below.

    Split out as a module function rather than inlined so a test can substitute
    a slow or failing stand-in and exercise the 504/502 paths against a REAL
    subprocess instead of a mocked one."""
    return [sys.executable, str(HERE / script), *args]


def _bash_executable() -> str | None:
    """The bash that will actually run the commit hook, RESOLVED — never the
    bare string `"bash"` handed to `subprocess`.

    MEASURED on this repo's own Windows dev box, and the reason this function
    exists rather than a literal: `subprocess.run(["bash", ...])` goes through
    CreateProcess, which searches `System32` BEFORE `PATH` and therefore finds
    the WSL relay shim instead of Git Bash. That shim then dies with
    `execvpe(/bin/bash) failed: No such file or directory` and rc=1 — so the
    commit chain would have degraded on EVERY Windows box, silently and
    permanently, while passing on the ubuntu CI runner. `shutil.which` searches
    `PATH` the way a dev shell does and returns the real interpreter; this kit
    already pins bash exactly this way for the same measured reason
    (`.agents/evals/test_events_parity.py`, `test_ledger_parity.py`).

    None means no bash at all, which is a legitimate state (a Windows box
    without Git Bash) and becomes a NAMED degradation, never a crash."""
    return shutil.which("bash")


def _commit_hook_path() -> Path:
    """`.agents/bin/post-task-done-index.sh` — the ONE commit hook, resolved
    beside this file rather than under the served project root: it is host-
    neutral kit code that takes its target tree from `CLAUDE_PROJECT_DIR`, which
    `_run_commit_hook` sets. Split out for the same reason as `_cli_argv` — a
    test must be able to point it at an absent or failing script and exercise
    the DEGRADED branch for real, rather than trusting a mock."""
    return HERE / "post-task-done-index.sh"


# The variables the commit hook actually needs, and NOTHING else (T-00000178).
# ADVISORY HARDENING, said plainly: this route is already behind the write
# token, so passing the server's whole environment was not an exploit — it was
# an unnecessary surface. A dashboard process may hold anything its operator
# exported (registry credentials, cloud tokens, an `NVD_API_KEY`), and handing
# all of it to a shell script is a default that gets worse over time without
# anyone changing a line.
# The list is a CLOSED allowlist rather than a denylist of secrets, for the
# reason denylists fail: the next secret-shaped variable is one nobody has named
# yet. What is here is what git and bash cannot run without.
_HOOK_ENV_KEYS = (
    "PATH",           # bash resolves git, python, and its own utilities with it
    "HOME",           # git reads ~/.gitconfig — the author identity lives there
    "USERPROFILE",    # the Windows spelling of the same thing
    "SYSTEMROOT",     # Windows: without it Python's socket/ssl init can fail
    "COMSPEC",        # Windows: subprocess fallbacks reach for it
    "TMPDIR", "TEMP", "TMP",   # git writes index locks and objects through these
    "LANG", "LC_ALL", "LC_CTYPE",   # decoding of git output; a wrong locale mangles paths
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",   # honoured when the caller set them
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",       # test harnesses isolate git with these
    "GIT_SSH_COMMAND",    # a repo whose remote needs a specific key still works
    "SSH_AUTH_SOCK",
)


def _hook_environment(root: Path) -> dict[str, str]:
    """The minimal environment handed to the commit hook, plus the project root.

    Absent keys are simply not passed — an empty string is NOT the same as unset
    for `PATH` or `HOME`, and forwarding `""` would break the hook in a way that
    looks like a git failure rather than an environment one.
    """
    env = {key: os.environ[key] for key in _HOOK_ENV_KEYS if key in os.environ}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return env


def _classify_commit_stdout(stdout: str | None) -> dict[str, str]:
    """Read the commit hook's real verdict off its STDOUT, closed by default.

    The hook ALWAYS exits 0 by contract (it is advisory), so an rc of 0 is not
    evidence a commit happened — the verdict is a classification of stdout. This
    is the server mirror of the browser's rule in `commitHookNotice`
    (`src/lib/actions.js`): an unknown status is a WARNING, never a silent
    success. Anything non-empty that is not a recognised success therefore
    degrades.

    The hook emits `{"systemMessage": "post-task-done: <phrase>"}` (or nothing
    when there was nothing to commit); a raw non-JSON line is tolerated and
    classified on its own text. Matching is on ASCII substrings ONLY, because
    `_run_cli` decodes with `errors="replace"` and the phrases carry accents
    (`commités`, `dégradé`, `opération`) — a byte-level mojibake must not flip a
    verdict. The DEGRADED tokens are tested BEFORE the success token, because
    "stores commités sans verrou" contains "stores commit": that order is the
    whole correctness of the without-lock case.

    Since T-00000703 the hook has a SECOND leg (the run exports under `runs/`,
    committed after the stores), so the phrase may carry two clauses joined by
    ` · `, and the DEGRADED tokens of either leg win over the success token of
    the other: "stores commités · exports non commités" is a degradation.

    - empty stdout                            → ok (nothing to commit)
    - "stores commit"… / "exports commit"…    → ok, unless a degraded token is
      without any degraded token                present (an `index-refresh:`
                                                clause never changes the status)
    - "sans verrou" / "stores non commit"
      / "exports non commit"                  → degraded, phrase in `reason`
    - any other non-empty stdout              → degraded, phrase in `reason`
    """
    text = (stdout or "").strip()
    if not text:
        return {"status": "ok"}
    message = text
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("systemMessage"), str):
        message = payload["systemMessage"]
    if ("sans verrou" in message or "stores non commit" in message
            or "exports non commit" in message):
        return {"status": "degraded", "reason": message}
    if "stores commit" in message or "exports commit" in message:
        return {"status": "ok"}
    return {"status": "degraded", "reason": message}


def _run_cli(argv: list[str], timeout: float | None = None,
             cwd: Path | None = None, stdin_text: str | None = None,
             env: dict[str, str] | None = None,
             stdout_limit: int | None = None) -> dict[str, Any]:
    """Run one CLI and describe the outcome; never raises, never blocks past
    `timeout`.

    Returns `{"status", "rc", "stdout", "stderr", "truncated"}` where `status`
    is one of `ok` · `failed` · `refused` · `timeout` · `missing`.

    `refused` versus `failed` is the distinction that makes the HTTP mapping
    honest: this repo's CLIs exit **2** on an operator-facing refusal
    (`BoardError`, `SpecsError`, `WaiverError` — "unknown task", "unknown
    status") and that is a 400, the caller's fault. Any other non-zero rc is an
    unhandled failure of a program this server chose to run, which is a 502.
    Collapsing the two would tell a user his typo was a server crash.

    `timeout` defaults to `_ACTION_CLI_TIMEOUT` read AT CALL TIME, not bound as
    a default argument value — a test that lowers the module constant must
    actually lower the bound.

    Output is decoded with `errors="replace"` and truncated to
    `_CLI_EXCERPT_CHARS`; a truncation is DECLARED (`truncated`) rather than
    silently trimmed, per this repo's bound-reporting rule.

    `stdout_limit` raises that bound for the ONE caller that hashes what it
    reads (the gate's plan re-read): a hash computed over a 400-char excerpt
    would be a hash of the excerpt, silently pinning the wrong thing. It is a
    LARGER bound, never an absent one — `specs.py list` caps its own output at
    ~4000 chars, so the real ceiling is upstream and this one only has to be
    generous enough not to bite."""
    limit = _ACTION_CLI_TIMEOUT if timeout is None else timeout
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, never shell=True
            argv,
            capture_output=True,
            timeout=limit,
            cwd=str(cwd) if cwd is not None else None,
            input=stdin_text.encode("utf-8") if stdin_text is not None else None,
            env=env,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "rc": None, "stdout": "", "stderr": "",
                "truncated": False, "timeout_seconds": limit}
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        # The interpreter or the script is not where this module expects it.
        # Named, never guessed at: a missing program and a failing one need
        # different remedies.
        return {"status": "missing", "rc": None, "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}", "truncated": False}
    except OSError as exc:
        return {"status": "missing", "rc": None, "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}", "truncated": False}

    stdout, out_cut = _excerpt(completed.stdout, stdout_limit)
    stderr, err_cut = _excerpt(completed.stderr)
    rc = completed.returncode
    if rc == 0:
        status = "ok"
    elif rc == 2:
        status = "refused"
    else:
        status = "failed"
    return {"status": status, "rc": rc, "stdout": stdout, "stderr": stderr,
            "truncated": out_cut or err_cut}


def _excerpt(raw: bytes | None, limit: int | None = None) -> tuple[str, bool]:
    """Bytes off a subprocess pipe -> a bounded, single-block str. `replace`
    rather than `strict`: a CLI that emits a stray byte must not turn a 400 into
    a 500 on this side."""
    bound = _CLI_EXCERPT_CHARS if limit is None else limit
    text = (raw or b"").decode("utf-8", errors="replace").strip()
    if len(text) <= bound:
        return text, False
    return text[:bound] + " …[truncated]", True


class UIHandler(http.server.BaseHTTPRequestHandler):
    """Serves ONLY `GET` on four closed route tables: `_ALLOWED_UI_PATHS`
    (`/api/snapshot`, `/api/events`, `/api/stream`, `/api/ping`,
    `/api/projects`, `/api/peers`, `/api/sessions`, `/api/term`,
    `/api/term/stream`, `dashboard_routes_etat.ROUTES` - token required),
    `_ALLOWED_STATIC_ROUTES` (the `.agents/ui/` shell - token exempt, shard 4a),
    `_ALLOWED_HANDOFF_PATHS` (redeem, ticket-bound: `dashboard_handoff.py`) and
    `_ALLOWED_PEER_PATHS` (`/api/peer/summary` - token exempt, T-00000083:
    its consumer is another project's daemon, which probes without this token).
    The enumeration in this
    docstring said "two routes" until T-00000051 - it had been stale since
    `/api/stream` and `/api/ping` landed, which is precisely why the route
    tables, not a comment, are the source of truth (asserted by
    `test_the_api_route_set_stays_closed_and_small`).

    T-00000028 ADDS ONE VERB, on one table: `POST` on `_ALLOWED_WRITE_PATHS`
    (`/api/actions/gate`, `/api/actions/board`, `/api/actions/waiver` - token
    REQUIRED, bounded body, no CORS). "GET is the only verb" was true of this
    server until that task and is no longer; see that table's own contract
    block for what justifies the exception and for the four properties that
    bound it; `_ALLOWED_HANDOFF_WRITE_PATHS` is the second POST table
    (`dashboard_handoff.py`). Every other verb still 404s outright on every
    route, and POST itself 404s outside those two tables - including the static
    shell and the peer route, whose token exemption exists for READS (a bare
    `BaseHTTPRequestHandler` with no `do_X` defined would 501, not 404 -
    matching `OTLPHandler`'s own defensive style, independently
    re-implemented here per the route-separation finding: nothing shared
    between the two handler classes)."""

    server_version = "agentkit-dashboard-ui/1"

    def do_GET(self) -> None:
        self._route()

    def do_POST(self) -> None:
        self._route_write()

    def do_PUT(self) -> None:
        self._reject(404, "not_found")

    def do_DELETE(self) -> None:
        self._reject(404, "not_found")

    def do_PATCH(self) -> None:
        self._reject(404, "not_found")

    def do_HEAD(self) -> None:
        self._reject(404, "not_found")

    def do_OPTIONS(self) -> None:
        self._reject(404, "not_found")

    def log_message(self, *args: Any) -> None:
        pass  # quiet by design, matching otel_receiver.py's handler

    def _drain_request_body(self) -> None:
        """L-00000048: an early reject (401/404) on a request that still has
        unread body bytes sitting in the socket can make Windows send a hard
        RST instead of a graceful FIN on close, surfacing to the client as
        `ConnectionAbortedError [WinError 10053]`. Bounded to
        `_DRAIN_LIMIT_BYTES` regardless of the declared Content-Length, same
        reasoning as `otel_receiver.py`'s helper: an oversized/abusive
        declared length must not make a REJECTED request cost more than this
        bound to drain.

        T-00000028: a write route has ALREADY consumed its body by the time it
        can reject on the CONTENT (a bad decision value, an unknown board
        action). Draining again would ask the socket for a second body's worth
        of bytes that will never come, and hang the handler until the client
        times out — so `_read_json_body` marks the body consumed and this
        returns immediately. The unread-body case (a 401/404/413 decided before
        any read) is unchanged, which is the case L-00000048 is about."""
        if getattr(self, "_body_consumed", False):
            return
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else 0
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return
        try:
            self.rfile.read(min(length, _DRAIN_LIMIT_BYTES))
        except OSError:
            pass

    def _reject(self, status: int, reason: str, retry_after: int | None = None) -> None:
        self._drain_request_body()
        body = json.dumps({"error": reason}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            # 503 on the stream-slot bound only: a client that backs off and
            # retries is the correct behaviour, and saying so beats making it
            # guess (or hammer).
            self.send_header("Retry-After", str(retry_after))
        # No CORS header, ever - not Access-Control-Allow-Origin, not any
        # other CORS response header, on ANY response this handler sends.
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _respond_json(self, status: int, payload: dict[str, Any],
                      cache_control: str | None = None) -> None:
        """`cache_control` DEFAULTS TO INERT (T-00000051): `/api/ping` and `/api/events` pass nothing and
        keep their headers. `/api/snapshot` left for `dashboard_transport.servir` (T-01M4XR9ESWKJ8G545AJBJQNC7Q:
        memoised body, gzip, ETag/304); `/api/stream` writes its own headers; `_reject` sends no `Cache-Control`."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Same hardening pair the static routes carry (security review
        # advisory): consumed by fetch, never rendered, but cheap and uniform.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _respond_static(self, route: str) -> None:
        """Serve one entry of the CLOSED static table. `route` has already
        passed an exact-match lookup, so the only thing this reads is a
        constant path: `_UI_DIR` joined with the table's own literal
        segments. A missing or unreadable file is a 404 with the same opaque
        body every other rejection uses — never a 500, and never a response
        that reflects the attempted filesystem path back to the caller."""
        segments, content_type = _ALLOWED_STATIC_ROUTES[route]
        try:
            body = _UI_DIR.joinpath(*segments).read_bytes()
        except OSError:
            self._reject(404, "not_found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", _STATIC_CACHE_CONTROL)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type == _CT_HTML:
            self.send_header("Content-Security-Policy", _STATIC_CSP)
        # No CORS header here either - see _reject's note.
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    # -----------------------------------------------------------------------
    # /api/stream (SSE). Token-only like every other /api/* route; see the
    # `_MAX_CONCURRENT_STREAMS` comment block for the thread/lifetime design.
    # -----------------------------------------------------------------------

    def _stream_write(self, text: str) -> bool:
        """One SSE frame (or comment). False means the client is gone — the
        ONLY normal way a stream loop ends.

        SEMANTICS, decided deliberately: this is the SINGLE write path for both
        `data:` events and `: keepalive` comments, and EVERY successful write
        restamps `last_activity`. A keepalive therefore counts as authorised
        activity, on purpose — a live SSE stream proves a browser is watching
        this daemon right now, and `dashboard_daemon`'s 4 h auto-stop must not
        kill a dashboard someone is looking at just because it happens to be
        quiet. The converse is what keeps that safe: a closed tab stops
        absorbing writes, `_client_gone()` sees the EOF within one poll tick,
        the loop exits, and the daemon ages out normally.

        A stalled peer — connection open, TCP receive window full, nothing
        being read — would otherwise block this write FOREVER, and a blocked
        write cannot be preempted by the deadline or the slot accounting that
        only run between calls. That silently defeats both documented bounds
        (`_STREAM_MAX_SECONDS`, `_MAX_CONCURRENT_STREAMS`): four frozen tabs
        would hold every slot until the daemon restarts (security review D4,
        MEDIUM). Hence the socket timeout set in `_respond_stream` and the
        `socket.timeout` branch below: a peer that cannot absorb one frame
        within a few poll intervals is treated as gone, which is what it is
        for a stream whose whole purpose is timely notification."""
        try:
            self.wfile.write(text.encode("utf-8"))
            self.wfile.flush()
        except socket.timeout:
            return False  # stalled peer: force-close rather than block a slot
        except (OSError, ValueError):
            return False
        self.server.last_activity = time.monotonic()
        return True

    def _stream_event(self, payload: dict[str, Any]) -> bool:
        return self._stream_write(
            "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        )

    def _client_gone(self) -> bool:
        """True when the peer has closed. Checked on EVERY poll tick, so a
        closed browser tab frees its slot within one poll interval instead of
        waiting for the next heartbeat to fail — which matters twice: a slot is
        one of only four, and an open stream restamps `last_activity`, so a
        tab that is gone must stop looking like a user watching the dashboard.

        An SSE client sends nothing after its request, so a socket that is
        READABLE has either EOF (closed) or unexpected bytes. `MSG_PEEK` keeps
        the check non-destructive. Any surprise here returns False — the failed
        write remains the backstop, and a false "gone" would kill a healthy
        stream, which is the worse error."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True  # the socket itself is unusable: the stream is over
        except Exception:  # noqa: BLE001 - never let a probe end a healthy stream
            return False

    def _respond_stream(self) -> None:
        if not _acquire_stream_slot():
            # Bounded, never an unlimited thread pool. `Retry-After` in
            # seconds; the body stays the same opaque `{"error": ...}` shape
            # every other rejection uses.
            self._reject(503, "stream_limit_reached", retry_after=5)
            return
        # A stalled peer must not be able to block a write forever and hold
        # one of the four slots past every documented bound (see
        # `_stream_write`'s docstring). Three poll intervals is generous for a
        # peer that is merely busy and decisive about one that is frozen.
        # Restored in `finally` because this handler's socket goes back to the
        # server's normal (blocking) request handling afterwards.
        previous_timeout = None
        try:
            previous_timeout = self.connection.gettimeout()
            self.connection.settimeout(_STREAM_POLL_SECONDS * 3)
        except OSError:
            pass  # exotic socket: the failed-write backstop still applies
        try:
            self._stream_loop()
        finally:
            try:
                self.connection.settimeout(previous_timeout)
            except OSError:
                pass
            _release_stream_slot()

    def _stream_loop(self) -> None:
        project_root = getattr(self.server, "project_root", None) or _project_root()
        events_dir = _resolved_events_dir()
        otel_dir = _resolved_otel_dir()
        stop: threading.Event = getattr(self.server, "stream_stop", None) or threading.Event()

        def fingerprints() -> tuple[tuple, tuple]:
            """Cheap: `stat()` over the input set plus ONE `open_store` and meta read (T-00000615:
            0.3 ms at the dev's measure, 1.3-1.6 ms under load at binôme octies), never a file's bytes —
            the reason the design doc chose polling over re-serialising a 108 Ko snapshot every 500 ms.

            T-00000049: the SQLite projection's key joins BOTH tuples. The events
            notice has to fire when a tick moves rows into the database (its data
            generation: its stat stays frozen in WAL), and once the spool is drained
            the directory alone would go quiet exactly when there is most to report."""
            try:
                store_fp = _store_fingerprint()
                return (
                    (_readers_mod.dir_fingerprint(events_dir), store_fp),
                    _readers_mod.snapshot_fingerprint(
                        Path(project_root), events_dir, otel_dir, store_fp),
                )
            except Exception:  # noqa: BLE001 - a fingerprint must never end a stream
                return ((), ())

        self.send_response(200)
        # Exactly `text/event-stream` (no parameters): EventSource matches the
        # bare MIME type, and SSE is UTF-8 by specification.
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        # No Content-Length: the body is open-ended and the client reads until
        # the server closes. No CORS header here either.
        self.end_headers()

        events_fp, snapshot_fp = fingerprints()
        if not self._stream_write(f"retry: {_STREAM_RETRY_MS}\n\n"):
            return
        if not self._stream_event({
            "kind": "hello",
            "at": _now_iso(),
            "poll_ms": int(_STREAM_POLL_SECONDS * 1000),
            "heartbeat_s": _STREAM_HEARTBEAT_SECONDS,
            "max_stream_s": _STREAM_MAX_SECONDS,
            "kinds": ["hello", "snapshot_changed", "events_changed", "stream_expired"],
            "note": (
                "a `: keepalive` SSE COMMENT arrives every heartbeat_s so a client "
                "can detect a cut; comments are ignored by EventSource. This stream "
                "carries CHANGE NOTICES only — never repo data. Refetch the "
                "token-only data routes (/api/snapshot, /api/events) on a notice. "
                "NOT covered by any notice: /api/projects — project.json is not part "
                "of the snapshot fingerprint, so an identity created mid-session may "
                "only be picked up at the next notice a DIFFERENT input triggers."
            ),
        }):
            return

        deadline = time.monotonic() + _STREAM_MAX_SECONDS
        last_write = time.monotonic()
        while not stop.is_set():
            if time.monotonic() >= deadline:
                # Clean, announced close — the client reconnects via `retry:`.
                self._stream_event({"kind": "stream_expired", "at": _now_iso(),
                                    "after_s": _STREAM_MAX_SECONDS})
                return
            # `Event.wait` rather than `sleep`: a `server_close()` during a
            # poll interval ends the stream immediately instead of after a
            # further 500 ms.
            if stop.wait(_STREAM_POLL_SECONDS):
                return
            if self._client_gone():
                return
            new_events_fp, new_snapshot_fp = fingerprints()
            wrote = False
            if new_events_fp != events_fp:
                events_fp = new_events_fp
                if not self._stream_event({"kind": "events_changed", "at": _now_iso()}):
                    return
                wrote = True
            if new_snapshot_fp != snapshot_fp:
                snapshot_fp = new_snapshot_fp
                if not self._stream_event({"kind": "snapshot_changed", "at": _now_iso()}):
                    return
                wrote = True
            now = time.monotonic()
            if wrote:
                last_write = now
            elif now - last_write >= _STREAM_HEARTBEAT_SECONDS:
                if not self._stream_write(f": keepalive {_now_iso()}\n\n"):
                    return
                last_write = now

    # -----------------------------------------------------------------------
    # /api/term/stream (SSE, T-00000087). Same transport as `/api/stream`, its
    # own slot counter, and a body that carries BYTES rather than notices — see
    # the `_MAX_TERM_STREAMS` comment block for why the two are separated.
    # -----------------------------------------------------------------------

    def _term_gap(self, reason: str) -> bool:
        """A run of bytes was SKIPPED and the client is told which run and why.
        Never silent: a terminal is a state machine driven by escape sequences,
        so quietly splicing across a hole produces a screen that looks right and
        never existed. The front resets its emulator on `rotation`."""
        return self._stream_event({"kind": "term_gap", "reason": reason,
                                   "at": _now_iso()})

    def _term_bytes(self, data: bytes) -> bool:
        """Base64, not text. The spool is a raw ANSI byte stream and a chunk
        boundary can fall inside a UTF-8 sequence; JSON cannot carry a lone
        continuation byte, and a lossy decode here would corrupt the emulator's
        state for everything that follows."""
        return self._stream_event(
            {"kind": "term", "b64": base64.b64encode(data).decode("ascii")})

    def _respond_term_stream(self, qs: dict[str, list[str]]) -> None:
        sid = _first(qs, "sid") or ""
        # ANCHORED match on a narrow alphabet, BEFORE anything is joined to a
        # path. This is the only route on this server that takes a
        # filename-shaped parameter, so the validation is the boundary: a sid
        # that does not match never reaches `open()`, and an unknown-but-valid
        # sid gets the SAME opaque 404 — a reader cannot probe the filesystem
        # by watching the two apart.
        if not _TERM_SID_RE.match(sid):
            self._reject(404, "not_found")
            return
        directory = _term_dir()
        if directory is None:
            self._reject(404, "not_found")
            return
        meta_path = directory / f"{sid}.meta.json"
        raw_path = directory / f"{sid}.raw"
        try:
            known = meta_path.is_file()
        except OSError:
            known = False
        if not known:
            self._reject(404, "not_found")
            return
        if not _acquire_term_slot():
            # The MIRROR limit, which is not the notice limit: a saturated
            # mirror must never cost the dashboard its change notices.
            self._reject(503, "term_stream_limit_reached", retry_after=5)
            return
        previous_timeout = None
        try:
            previous_timeout = self.connection.gettimeout()
            self.connection.settimeout(_STREAM_POLL_SECONDS * 3)
        except OSError:
            pass
        try:
            self._term_stream_loop(meta_path, raw_path)
        finally:
            try:
                self.connection.settimeout(previous_timeout)
            except OSError:
                pass
            _release_term_slot()

    @staticmethod
    def _term_slice(raw_path: Path, offset: int, limit: int):
        """OPEN, seek, read, CLOSE — every tick, no handle kept.

        That is not tidiness. `wrap.py`'s ring rotation ends in an
        `os.replace`, and on Windows a handle held across the swap makes the
        writer's bounded retry fail and the rotation get abandoned. A daemon
        that kept this file open would degrade the WRITER, from another
        process, invisibly.

        Returns `(size, data, skipped)` — `skipped` True when the backlog
        exceeded `limit` and the read jumped to the newest bytes. `(None, b"",
        False)` when the file cannot be read at all, which is a normal
        transient during a swap and never an error the stream ends on."""
        try:
            with open(raw_path, "rb") as fh:
                size = fh.seek(0, os.SEEK_END)
                if offset >= size:
                    return size, b"", False
                start = offset
                skipped = False
                if size - offset > limit:
                    start = size - limit
                    skipped = True
                fh.seek(start, os.SEEK_SET)
                return size, fh.read(limit), skipped
        except OSError:
            return None, b"", False

    def _term_stream_loop(self, meta_path: Path, raw_path: Path) -> None:
        stop: threading.Event = getattr(self.server, "stream_stop", None) or threading.Event()

        def generation() -> Any:
            meta = _wrap_mod.read_meta(meta_path)
            return None if meta is None else meta.get("gen", 0)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

        if not self._stream_write(f"retry: {_STREAM_RETRY_MS}\n\n"):
            return

        gen = generation()
        # CATCH-UP IS A TAIL, AND SAYS SO. Joining a console that has been
        # running for an hour cannot mean replaying an hour; it means the last
        # screenful-and-then-some, with the truncation announced rather than
        # implied by a display that starts mid-word.
        size, _data, _skipped = self._term_slice(raw_path, 0, 0)
        offset = 0 if size is None else max(0, size - _TERM_CATCHUP_BYTES)
        if offset > 0 and not self._term_gap("catchup"):
            return
        size, data, skipped = self._term_slice(raw_path, offset, _TERM_CATCHUP_BYTES)
        if data:
            if skipped and not self._term_gap("lag"):
                return
            if not self._term_bytes(data):
                return
        offset = size if size is not None else offset

        deadline = time.monotonic() + _STREAM_MAX_SECONDS
        last_write = time.monotonic()
        while not stop.is_set():
            if time.monotonic() >= deadline:
                self._term_gap("expired")
                return
            if stop.wait(_STREAM_POLL_SECONDS):
                return
            if self._client_gone():
                return
            # THE META IS RE-READ EVERY TICK, and it is the generation — not the
            # size — that decides a reset. A ring that rolled twice between two
            # ticks can land on a file the same length as before; comparing
            # sizes alone would splice two different files at one offset.
            new_gen = generation()
            rotated = new_gen is not None and gen is not None and new_gen != gen
            gen = new_gen if new_gen is not None else gen
            size, data, skipped = self._term_slice(raw_path, offset, _TERM_MAX_TICK_BYTES)
            if size is not None and size < offset:
                rotated = True  # shrank under us: same conclusion, other evidence
            if rotated:
                offset = 0
                if not self._term_gap("rotation"):
                    return
                size, data, skipped = self._term_slice(
                    raw_path, offset, _TERM_MAX_TICK_BYTES)
            wrote = False
            if skipped and not self._term_gap("lag"):
                return
            if data:
                if not self._term_bytes(data):
                    return
                wrote = True
            if size is not None:
                offset = size
            now = time.monotonic()
            if wrote or skipped:
                last_write = now
            elif now - last_write >= _STREAM_HEARTBEAT_SECONDS:
                if not self._stream_write(f": keepalive {_now_iso()}\n\n"):
                    return
                last_write = now

    def _check_token(self) -> bool:
        expected = getattr(self.server, "token", None)
        if not expected:
            return False
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            return False
        provided = auth[len("Bearer "):]  # bytes: a non-ASCII str makes compare_digest RAISE (TypeError), not refuse
        return hmac.compare_digest(provided.encode("utf-8"), str(expected).encode("utf-8"))

    def _route(self) -> None:
        # EXACT match only, on the raw (never normalised, never
        # percent-decoded) path component - see module docstring's
        # traversal-control note. Query string is split off first so
        # filters live in `qs`, never in path matching.
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path in _ALLOWED_STATIC_ROUTES:
            # Token-EXEMPT by necessity (a document navigation carries no
            # Authorization header) and data-free by construction; see the
            # module docstring's shard-4a addendum. Deliberately does NOT
            # stamp `last_activity`: only authorised traffic keeps shard 2's
            # daemon alive.
            self._respond_static(path)
            return
        if path in _ALLOWED_HANDOFF_PATHS:  # BEFORE the peer table: `dashboard_handoff.respond_redeem`
            _handoff_mod.respond_redeem(self)
            return
        if path in _ALLOWED_PEER_PATHS:
            # T-00000083 — token-EXEMPT by necessity (a peer daemon probes without
            # this daemon's token; publishing it in the shared registry is what
            # L-00000112 forbids) and bounded by construction: one closed key
            # set, identity + one board line + health.
            #
            # Deliberately does NOT stamp `last_activity`, for the same reason
            # the static routes do not: a neighbour's liveness probe is not a
            # HUMAN using this dashboard, and letting it defer shard 2's 4 h
            # auto-stop would keep two idle daemons alive forever by mutual
            # pinging.
            #
            # `no-store`, like `/api/projects`: this names what is running AT
            # THIS INSTANT, and a cached copy is the shape that makes a peer
            # display a task that finished an hour ago.
            project_root = getattr(self.server, "project_root", None)
            self._respond_json(200, build_peer_summary(project_root),
                               cache_control="no-store")
            return
        if path not in _ALLOWED_UI_PATHS:
            self._reject(404, "not_found")
            return
        if not self._check_token():
            self._reject(401, "unauthorized")
            return
        # Authorised traffic only — shard 2's idle watchdog reads this;
        # unauthenticated noise must never keep the daemon alive.
        self.server.last_activity = time.monotonic()
        qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if path == "/api/ping":
            # LIVENESS ONLY (T-00000043). Deliberately the cheapest possible authenticated response: it reads nothing,
            # builds nothing, and carries no repo data — just proof that THIS daemon, holding THIS token, is
            # answering. `dashboard_daemon.ping()` used to probe `/api/snapshot` to avoid adding a route; that was
            # fine when the snapshot was five small JSON reads, and became wrong when D4 grew it to ~166 KB: a health
            # check that pays the cost of the heaviest read misjudges a HEALTHY daemon as stale whenever the machine
            # is busy, and the daemon's own lock then gets reclaimed. Observed as an intermittent test failure across
            # full-suite runs; the tests were the messenger, the coupling was the defect.
            self._respond_json(200, {"ok": True, "pid": os.getpid()})
        elif path == "/api/snapshot" or path in _routes_mod.ROUTES:  # lot D: + the three journal routes
            # T-01M4XR9ESW: ONE build per key, live fields grafted at send. Lot D: `contrat` absent, 1 or 2, else 400.
            root = Path(getattr(self.server, "project_root", None) or _project_root())
            if path in _routes_mod.ROUTES:  # grammar A2.3: an up-to-date etat.db, else the journals read directly
                _routes_mod.traiter(self, path, qs, root, _EMPREINTE_CODE)
            elif (variante := _routes_mod.variante(qs)) is None:
                self._reject(400, "bad_request")
            else:
                _transport_mod.servir(self, construire=lambda v: _routes_mod.alleger(build_snapshot(root), v),
                                      variante=variante, vivant=_SNAPSHOT_SOURCES["vivant"],
                                      avant_cle=lambda: _routes_mod.empreinte_journaux(root, _EMPREINTE_CODE),
                                      empreinte=lambda: _transport_mod.empreinte_snapshot(root, _SNAPSHOT_SOURCES))
        elif path == "/api/stream":
            self._respond_stream()
        elif path == "/api/projects":
            # T-00000051 (V1-d). `no-store`, the FIRST route to carry it (peers, sessions, term, the journal routes
            # followed): the payload names the identity this daemon resolved AT THIS INSTANT, and a cached copy is the
            # shape that makes a hub believe a stale identity. Rejections do NOT carry it: they go through `_reject`.
            # T-00000582: pass the handler's root (the daemon's --root) so `name`/`label` follow the SERVED repo,
            # exactly like /api/snapshot and /api/peer/summary above. Without it, a daemon under --root X would show
            # ONE daemon under TWO names (the badge from X, the selector from __file__).
            project_root = getattr(self.server, "project_root", None)
            self._respond_json(200, build_projects_response(project_root),
                               cache_control="no-store")
        elif path == "/api/peers":
            # T-00000083 (M2). `no-store` for the same reason as `/api/projects` and more so: this payload asserts
            # which OTHER daemons are alive right now, and a cached copy is a list of ghosts.
            self._respond_json(200, build_peers_response(), cache_control="no-store")
        elif path == "/api/sessions":
            # T-00000086 (M5a). `no-store` for the third time and the same
            # reason: this payload asserts what the consoles are doing AT THIS
            # INSTANT, and a cached copy is a session that ended an hour ago
            # still shown as the newest thing on the machine.
            self._respond_json(200, build_sessions_response(qs),
                               cache_control="no-store")
        elif path == "/api/term":
            # T-00000087 (M5b). `no-store` for the fourth time: this payload asserts which consoles have a LIVE mirror
            # right now, and a cached copy is a terminal that closed twenty minutes ago still offered for viewing.
            self._respond_json(200, build_term_response(), cache_control="no-store")
        elif path == "/api/term/stream":
            self._respond_term_stream(qs)
        else:  # "/api/events" - the last remaining member of _ALLOWED_UI_PATHS
            self._respond_json(200, build_events_response(qs))

    # -----------------------------------------------------------------------
    # T-00000028 — the write half. Three routes, one verb, and a hard rule
    # every method below obeys: this server records a DECISION, it never
    # resumes work. Nothing here starts an agent, a pipeline or a shard.
    # -----------------------------------------------------------------------

    def _route_write(self) -> None:
        """POST. Same exact-match, never-normalised, never-percent-decoded
        matching as `_route`, on `_ALLOWED_WRITE_PATHS`.

        THE ORDER OF THE FIRST TWO CHECKS IS DELIBERATE AND UNCHANGED — the
        membership test runs FIRST, an unknown path is answered before the
        token is looked at. What T-00000238 changed (pilot decision S-00000496,
        2026-08-21) is ONLY the code of the authenticated-table rejection: an
        absent-or-wrong token now yields 404 `not_found`, the same answer as an
        unknown path, where it used to yield 401 `unauthorized`.

        The order was NOT inverted, and inverting it was the shape T-00000178
        (c) asked for — tried, measured, and reverted the same night
        (2026-08-19, ten red arms), the reason written here so nobody spends
        the same hours twice. Checking the token first would close a real leak:
        unauthenticated, an unknown path answered 404 and a real one 401, which
        maps the write table with no credential. But `do_POST` funnels EVERY
        path through this method, including the token-EXEMPT tables (static
        documents, stream, peers, projects, sessions). A token check placed
        before the membership test therefore answers 401 on a document
        navigation — imposing the write table's credential requirement on tables
        whose exemption IS their contract, and that exemption exists because a
        document navigation carries no Authorization header at all. Ten arms of
        this suite pinned that, one stating in its own words that the write verb
        must not leak onto the exempt tables. So the leak is closed the only way
        that leaves the exempt tables intact — the membership test stays first,
        and the two UNAUTHENTICATED cases are made indistinguishable by giving
        BOTH the unknown-path answer. This is not a reordering.

        INVARIANT, scoped and measured: for the TWO NON-AUTHENTICATED cases
        (path outside the write table, token absent or wrong) the response is
        byte-identical to that of an unknown route — status, body and every
        header — save `Date` alone. It says nothing of an AUTHENTICATED error,
        which differs by construction; the net
        `test_an_unauthenticated_write_is_byte_identical_to_an_unknown_path_bar_the_date`
        measures exactly this scope.

        The security delta against the served bundle is NULL: `GET /assets/app.js`
        is token-exempt (see `_route`'s static table) and its JavaScript already
        carries the write paths it calls in clear, so 404-ing an unauthenticated
        POST hides nothing a reader cannot already read from the app itself. The
        change buys a uniform unauthenticated surface, not secrecy.

        The token is MANDATORY here: there is no exemption on this table, unlike
        the static and peer tables, and no code path below can be reached
        without it."""
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path in _ALLOWED_HANDOFF_WRITE_PATHS:  # its own table, FIRST: Host, then token, in `route_write`
            _handoff_mod.route_write(self, path, _resolve_identity_once, _event_store_mod.project_json_path)
            return
        if path not in _ALLOWED_WRITE_PATHS:
            self._reject(404, "not_found")
            return
        if not self._check_token():
            # T-00000238 (S-00000496): 404, NOT 401 — the two unauthenticated
            # cases (unknown path above, absent/wrong token here) must answer
            # identically, or the difference maps the write table with no
            # credential. Membership test still runs first; only the code moved.
            self._reject(404, "not_found")
            return
        # A write is authorised traffic by definition — shard 2's idle watchdog
        # must not age out a daemon somebody is actively driving.
        self.server.last_activity = time.monotonic()
        payload = self._read_json_body()
        if payload is None:
            return  # `_read_json_body` has already answered
        if path == "/api/actions/gate":
            self._action_gate(payload)
        elif path == "/api/actions/board":
            self._action_board(payload)
        else:  # "/api/actions/waiver" — the last member of the table
            self._action_waiver(payload)

    def _read_json_body(self) -> dict[str, Any] | None:
        """The bounded body read. Returns the decoded object, or None after
        having answered.

        The bound is checked against the DECLARED `Content-Length` before a
        single byte is read, so an oversized request costs a header parse rather
        than 64 KiB of socket traffic — and a request with no declared length at
        all is refused outright (411) rather than read until EOF, which is how a
        bodyless-but-chunked client would otherwise hold a handler thread."""
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except (TypeError, ValueError):
            length = -1
        if length < 0:
            self._reject(411, "length_required")
            return None
        if length > _DRAIN_LIMIT_BYTES:
            self._reject(413, "body_too_large")
            return None
        try:
            raw = self.rfile.read(length) if length else b""
        except OSError:
            self._body_consumed = True
            self._reject(400, "body_unreadable")
            return None
        # From here on the socket has been read to the declared length: every
        # subsequent rejection must NOT try to drain it again (see
        # `_drain_request_body`).
        self._body_consumed = True
        if len(raw) != length:
            self._reject(400, "body_truncated")
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._reject(400, "bad_json")
            return None
        if not isinstance(payload, dict):
            # A top-level list or scalar is not a request this server has any
            # shape for; refused here rather than surviving as a `.get()` on
            # something that has no `.get()`.
            self._reject(400, "bad_json")
            return None
        return payload

    def _action_root(self) -> Path:
        root = getattr(self.server, "project_root", None)
        return Path(root) if root is not None else _project_root()

    def _respond_cli_failure(self, stage: str, result: dict[str, Any],
                             extra: dict[str, Any] | None = None) -> None:
        """Map one `_run_cli` outcome to a status, and SAY which stage failed.

        `refused` (rc 2) is a 400 and not a 502 — see `_run_cli` for why the
        distinction is load-bearing. A timeout is a 504 carrying the bound it
        broke, so the operator reads a number rather than guessing one. These
        go through `_respond_json` rather than `_reject` because a bare
        `{"error": ...}` would hide the CLI's own message, which is the only
        thing that says WHY ("tasks.py: unknown task T-00000999")."""
        status_map = {"timeout": 504, "missing": 502, "refused": 400, "failed": 502}
        error_map = {"timeout": "cli_timeout", "missing": "cli_missing",
                     "refused": "refused", "failed": "cli_failed"}
        outcome = str(result.get("status"))
        payload: dict[str, Any] = {
            "ok": False,
            "error": error_map.get(outcome, "cli_failed"),
            "stage": stage,
            "rc": result.get("rc"),
            "detail": result.get("stderr") or result.get("stdout") or "",
            "output_truncated": bool(result.get("truncated")),
        }
        if outcome == "timeout":
            payload["timeout_seconds"] = result.get("timeout_seconds")
        if extra:
            payload.update(extra)
        self._respond_json(status_map.get(outcome, 502), payload,
                           cache_control="no-store")

    def _action_gate(self, payload: dict[str, Any]) -> None:
        """Record a plan approval as an ATTRIBUTED, VERIFIABLE capture.

        Three properties, in the order they are established:

        1. CONFIRMED. `confirm` must be the boolean `true` — not "true", not 1.
           This is the server half of the UI's two-step button: a request that
           reaches here without it is a request nobody meant to send.
        2. HASHED FROM A RE-READ, never from what the caller sent. The server
           re-runs `specs.py list --task T-NNN` and hashes THAT text. A hash
           computed over a plan body posted by the client would certify the
           client's copy — i.e. certify nothing, since the client is what we are
           trying to attribute. `plan_hash` is what turns "a plan was approved"
           into "THIS plan was approved" (design doc §G.2, tier-2 → tier-1).
        3. ATTRIBUTED. `events.emit` derives `user` from `git config user.name`
           in its own envelope (`events._resolve_user`), which is why this
           route passes no identity of its own: one resolver, one answer.

        And then it STOPS. No pipeline resume, no agent launch, no board
        transition — C1 of the approved plan, restated in `_GATE_NO_RESUME` and
        echoed in the response so the UI cannot quietly imply otherwise."""
        task = payload.get("task")
        decision = payload.get("decision")
        specs_id = payload.get("specs_id") or ""
        if not isinstance(task, str) or not _TASK_ID_RE.match(task):
            self._reject(400, "bad_task")
            return
        if not isinstance(decision, str) or decision not in _GATE_DECISIONS:
            self._reject(400, "bad_decision")
            return
        if not isinstance(specs_id, str) or (specs_id and not _SPECS_ID_RE.match(specs_id)):
            self._reject(400, "bad_specs_id")
            return
        if payload.get("confirm") is not True:
            self._reject(400, "confirmation_required")
            return

        root = self._action_root()
        read = _run_cli(
            _cli_argv("specs.py", f"--root={root}", "list", f"--task={task}"),
            cwd=root, stdout_limit=_PLAN_READ_CHARS,
        )
        if read["status"] != "ok":
            self._respond_cli_failure("specs_list", read)
            return
        plan_text = read["stdout"]
        # `specs.py list` on a task with no journal entry still prints its
        # do-not-obey frame header, so a non-empty stdout is NOT proof that a
        # plan exists. The entry line shape is what proves it — and approving a
        # plan that was never recorded would hash the emptiness and call it a
        # decision.
        if "- [S-" not in plan_text:
            self._respond_json(409, {
                "ok": False, "error": "no_plan_recorded", "task": task,
                "detail": "no specs entry for this task — nothing to hash, so "
                          "nothing to attribute an approval to",
            }, cache_control="no-store")
            return
        if specs_id and f"[{specs_id}]" not in plan_text:
            # The UI displayed an entry that the server does not find in its own
            # re-read: the two are looking at different states, and an approval
            # is exactly the moment not to paper over that.
            self._respond_json(409, {
                "ok": False, "error": "specs_id_not_in_plan", "task": task,
                "specs_id": specs_id,
                "detail": "the entry the caller approved is absent from the "
                          "server's re-read of this task's journal",
            }, cache_control="no-store")
            return
        plan_hash = hashlib.sha256(plan_text.encode("utf-8")).hexdigest()

        try:
            user = _events_mod._resolve_user()
        except Exception:  # pragma: no cover - _resolve_user is itself guarded
            user = None

        # Fail-open by contract (`events.emit` returns None always, and swallows
        # its own errors): the capture is best-effort at the SPOOL level, which
        # is why the specs entry below is the durable half of the record.
        _events_mod.emit("gate.approval", decision=decision, source="dashboard",
                         plan_hash=plan_hash, task=task)

        # Title is composed here from a CLOSED vocabulary, never from caller
        # text: `specs.py add` takes it POSITIONALLY, and a positional beginning
        # with `-` would be read as an option. Every caller-controlled value
        # below travels as `--opt=value`, a single token argparse can only read
        # as a value.
        title = f"gate {decision} from the dashboard"
        text = (
            f"decision={decision} source=dashboard plan_hash={plan_hash} "
            f"specs_id={specs_id or '-'} user={user or '-'} — {_GATE_NO_RESUME}"
        )
        written = _run_cli(
            _cli_argv("specs.py", f"--root={root}", "add", title,
                      f"--task={task}", "--kind=decision", f"--text={text}"),
            cwd=root,
        )
        if written["status"] != "ok":
            # The event is ALREADY in the spool. Saying "failed" without saying
            # that would send the operator to re-approve, producing a second
            # `gate.approval` for one human decision.
            self._respond_cli_failure("specs_add", written, extra={
                "event_emitted": True,
                "event_kind": "gate.approval",
                "plan_hash": plan_hash,
                "task": task,
            })
            return

        self._respond_json(200, {
            "ok": True,
            "action": "gate",
            "task": task,
            "decision": decision,
            "specs_id": specs_id or None,
            "plan_hash": plan_hash,
            "plan_chars": len(plan_text),
            "plan_truncated": bool(read["truncated"]),
            "user": user,
            "event": "gate.approval",
            "specs_entry": written["stdout"],
            "pipeline": _GATE_NO_RESUME,
        }, cache_control="no-store")

    def _action_board(self, payload: dict[str, Any]) -> None:
        """Drive the board through `tasks.py`, and NEVER around it.

        The state transitions and the never-reused id allocation live in
        that CLI; this route re-implements neither, which is the whole reason it
        is a subprocess rather than a `json.dump` — a second writer of
        `TASKS.json` would have to be correct about both, forever.

        A `done` additionally chains the commit hook, so a task closed from the
        UI leaves the three state stores committed exactly as a task closed from
        a console does. That chain can degrade, and when it does it is SAID —
        see `_run_commit_hook`."""
        action = payload.get("action")
        task = payload.get("task")
        if not isinstance(action, str) or action not in _BOARD_ACTIONS:
            self._reject(400, "bad_action")
            return
        if not isinstance(task, str) or not _TASK_ID_RE.match(task):
            self._reject(400, "bad_task")
            return
        note = self._bounded_text(payload.get("note"))

        # LE MOTIF EST OBLIGATOIRE SUR `done` ET SUR `block` DEPUIS LE
        # 2026-09-12, et l'UI le refuse ICI plutôt que de laisser la CLI le
        # refuser plus loin. Les deux refuseraient — la garde est dans
        # `set_state`/`block_task`, pas dans `argparse`, précisément pour que ce
        # chemin ne l'esquive pas — mais un 400 nommé dit au client CE QUI
        # MANQUE, là où une remontée d'échec CLI lui rend une trace d'outil.
        # Le tableau de bord n'offre aucun équivalent de `--on`, donc la prose
        # est ici la seule explication possible.
        if action in {"done", "block"} and not note:
            self._reject(400, f"note_required_for_{action}")
            return

        root = self._action_root()
        tail: list[str] = [action, task]
        if action == "start" and note:
            tail.append(f"--stage={note}")
        elif action == "block":
            tail.append(f"--note={note}")
        elif action == "done":
            tail.append(f"--raison={note}")
            # LA DÉROGATION AU BINÔME PASSE, MAIS ELLE N'EST JAMAIS SUPPOSÉE
            # (T-00000586, correctif du binôme de clôture). Depuis que `done`
            # exige `BINOME_MIN` critique(s) — un depuis S-00004500 —, ce chemin se faisait refuser toute
            # clôture SANS ISSUE : l'échappatoire n'existait que dans `argparse`.
            # On l'ouvre — mais uniquement si le client l'a DEMANDÉE et motivée.
            # La dériver d'office ferait de la garde une décoration vue du
            # tableau de bord, et un humain qui clique « terminé » n'a pas plus
            # lancé la revue critique qu'un autre. Sans ce champ, le refus de la
            # CLI remonte tel quel, avec son remède nommé.
            sans = self._bounded_text(payload.get("sans_binome"))
            if sans:
                tail.append(f"--sans-binome={sans}")
        # LES RELAIS DE `sans_cible` (T-00000654) ET DE `sans_dependances` (T-00000951) VALENT POUR
        # `start` ET `done`, les deux gestes que ces gardes traversent (`block` n'a aucun des deux
        # drapeaux). `sans_chaine` au `start` n'est PAS relayé : résidu déjà nommé, hors de ce lot.
        # Comme `sans_binome`, une dérogation n'est JAMAIS supposée — elle ne part que DEMANDÉE et
        # motivée par le client, sinon le refus de la CLI remonte tel quel avec son remède nommé.
        if action in {"start", "done"}:
            for champ in ("sans_cible", "sans_dependances"):
                sans_c = self._bounded_text(payload.get(champ))
                if sans_c:
                    tail.append(f"--{champ.replace('_', '-')}={sans_c}")
        result = _run_cli(_cli_argv("tasks.py", f"--root={root}", *tail), cwd=root)
        if result["status"] != "ok":
            self._respond_cli_failure(f"tasks_{action}", result, extra={"task": task})
            return

        body: dict[str, Any] = {
            "ok": True,
            "action": "board",
            "board_action": action,
            "task": task,
            "detail": result["stdout"],
        }
        if action == "done":
            body["commit_hook"] = self._run_commit_hook(root, task)
        self._respond_json(200, body, cache_control="no-store")

    def _run_commit_hook(self, root: Path, task: str) -> dict[str, Any]:
        """Chain `.agents/bin/post-task-done-index.sh` after a successful
        `done`, and report what happened — success, or degradation with its
        reason. NEVER a silent success.

        The hook is a PostToolUse hook: it reads the host's event JSON on stdin
        and matches the COMMAND SHAPE `tasks.py [--opts] done`. The payload fed
        here is CANONICALISED to exactly that shape rather than echoing the real
        argv, and that choice is disclosed in the response (`trigger`) because
        it is the kind of thing that must not be discovered later: the real argv
        carries `--root=<absolute path>`, and a project path containing a space
        would not match the hook's regex — the hook would then exit 0 having
        done nothing, which is indistinguishable from "nothing to commit". A
        silent no-op is precisely the failure this route may not have.

        `CLAUDE_PROJECT_DIR` is set to the served project root so the hook
        commits THIS project's stores; the hook's own fallback
        (`git rev-parse --show-toplevel`) would otherwise resolve against this
        server's cwd, which is not necessarily the same tree.

        The hook is advisory and always exits 0 by design, so an rc of 0 is NOT
        evidence the commit happened: the real verdict is a CLASSIFICATION of
        stdout (`_classify_commit_stdout`), closed by default. A without-lock
        degradation, a git operation in flight, or any unrecognised phrase comes
        back on stdout and lands in `status: degraded` with the phrase in
        `reason` — never a painted "ok". A non-zero rc still means `bash` itself
        failed, not that the commit was refused, and the raw stdout always
        travels in `message`."""
        script = _commit_hook_path()
        if not script.is_file():
            return {"status": "degraded",
                    "reason": f"commit hook absent: {script.name} not found next to dashboard.py"}
        bash = _bash_executable()
        if bash is None:
            return {"status": "degraded",
                    "reason": "bash unavailable on PATH — the commit hook is a "
                              "shell script and cannot run without one"}
        trigger_command = f"python .agents/bin/tasks.py done {task}"
        trigger = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": trigger_command}})
        env = _hook_environment(root)
        result = _run_cli([bash, str(script)], timeout=_ACTION_HOOK_TIMEOUT,
                          cwd=root, stdin_text=trigger, env=env)
        if result["status"] == "timeout":
            return {"status": "degraded", "trigger": trigger_command,
                    "reason": f"commit hook exceeded {result.get('timeout_seconds')}s"}
        if result["status"] == "missing":
            return {"status": "degraded", "trigger": trigger_command,
                    "reason": f"bash unavailable: {result['stderr']}"}
        if result["rc"] != 0:
            return {"status": "degraded", "trigger": trigger_command,
                    "reason": f"commit hook rc={result['rc']}: "
                              f"{result['stderr'] or result['stdout']}"}
        return {"trigger": trigger_command, "message": result["stdout"],
                **_classify_commit_stdout(result["stdout"])}

    def _bounded_text(self, value: Any) -> str:
        """One physical line, `_ACTION_TEXT_CHARS` max, truncation marked. A
        non-string is not an error here — it is simply not text, so it becomes
        the empty string and the caller's optional field stays absent."""
        if not isinstance(value, str):
            return ""
        text = " ".join(value.split())
        if len(text) > _ACTION_TEXT_CHARS:
            return text[:_ACTION_TEXT_CHARS] + "…"
        return text

    def _action_waiver(self, payload: dict[str, Any]) -> None:
        """Record a class-3 dependency decision (ACCEPT & TRACK) through
        `waivers.py`, the register's ONE writer.

        This server assembles no JSON entry of its own: `sca-waivers.json` is a
        committed security artefact, and a second writer would drift from
        `waiver_filter.py`'s matching rules the first day either side gained a
        field. The supply-chain refusal (spec D7) therefore lives in
        `waivers.py` too — it comes back here as rc 2, i.e. a 400 carrying the
        CLI's own sentence, not a rule re-stated in two places that could
        disagree."""
        eco = self._bounded_text(payload.get("ecosystem"))
        package = self._bounded_text(payload.get("package"))
        version = self._bounded_text(payload.get("version"))
        if not eco or not package or not version:
            self._reject(400, "missing_field")
            return
        status = payload.get("status") or "accepted"
        klass = payload.get("class") or "known_cve"
        finding_class = payload.get("finding_class") or ""
        if not isinstance(status, str) or not isinstance(klass, str) \
                or not isinstance(finding_class, str):
            self._reject(400, "bad_field")
            return
        advisories = payload.get("advisories") or "*"
        if isinstance(advisories, list):
            advisories = ",".join(str(item) for item in advisories)
        advisories = self._bounded_text(advisories) or "*"
        reason = self._bounded_text(payload.get("reason"))
        task = self._bounded_text(payload.get("task"))

        root = self._action_root()
        # Every value below is caller-controlled, so every one travels as a
        # SINGLE `--opt=value` token: passed as two tokens, a value beginning
        # with `-` would be read by argparse as the next option (argument
        # injection into the CLI's own option space — harmless to the shell,
        # since there is none, and still wrong).
        argv = _cli_argv(
            "waivers.py", f"--root={root}", "add",
            f"--ecosystem={eco}", f"--package={package}", f"--version={version}",
            f"--status={status}", f"--class={klass}", f"--advisories={advisories}",
            f"--reason={reason}", f"--task={task}",
        )
        if finding_class:
            argv.append(f"--finding-class={finding_class}")
        else:
            # AN ENTRY WITHOUT A FINDING CLASS IS INERT AT THE REGISTER, and the
            # caller had no way to learn that (T-00000178). `waiver_filter.py`
            # matches on the class, so a waiver written without one is recorded,
            # returns 200, appears in the register — and filters nothing. The
            # operator believes a finding is accepted and tracked; the gate goes
            # on reporting it.
            # IT IS A WARNING, NEVER A REFUSAL: the write is legitimate and the
            # register is append-only, so rejecting it would lose a decision
            # somebody deliberately took. Saying it is the whole fix.
            # stderr, not `log_message`: this handler is quiet by design (see
            # its `log_message`), and stderr is where this file already puts its
            # degradations (`DASHBOARD UI DEGRADED`). A request log would be a
            # different decision, taken here by accident.
            print(f"DASHBOARD WAIVER INERT: {eco}/{package}@{version} written "
                  f"without finding_class — it filters nothing until one is set",
                  file=sys.stderr, flush=True)
        result = _run_cli(argv, cwd=root)
        if result["status"] != "ok":
            self._respond_cli_failure("waivers_add", result, extra={
                "ecosystem": eco, "package": package, "version": version,
            })
            return
        body = {
            "ok": True,
            "action": "waiver",
            "ecosystem": eco,
            "package": package,
            "version": version,
            "status": status,
            "class": klass,
            "detail": result["stdout"],
        }
        if not finding_class:
            # The field the CALLER sees. The stderr line above reaches whoever
            # watches the server; this reaches whoever made the decision, which
            # is the person who can still fix it.
            body["warning"] = ("entrée inerte au registre : sans finding_class, "
                               "waiver_filter.py ne l'appariera à aucun constat "
                               "et la porte continuera de le signaler")
        self._respond_json(200, body, cache_control="no-store")


class UIHTTPServer(socketserver.ThreadingMixIn, _ExclusiveHTTPServer):
    """`ThreadingHTTPServer` (design doc §B.2) built on `_ExclusiveHTTPServer`
    (bind-exclusivity, L-00000050) rather than plain `HTTPServer` -
    `ThreadingMixIn` only changes how a connection is dispatched, never
    `server_bind()`, so the exclusivity guarantee is unaffected. Carries the
    per-launch token and project root as INSTANCE attributes (not a module
    global) so two independent server instances in the same test process
    never share a token."""

    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type, token: str, project_root: Path) -> None:
        super().__init__(server_address, handler_cls)
        self.token = token
        self.project_root = project_root
        # Monotonic stamp of the last AUTHORISED request (shard 2 idle
        # watchdog). Initialised at bind so a daemon nobody ever queries
        # still ages out from its start, not from epoch.
        self.last_activity = time.monotonic()
        self.handoff_tickets = _handoff_mod.TicketBook()  # per INSTANCE: dies with the process
        self.snapshot_memo = _transport_mod.MemoCorps()  # per INSTANCE: a case per contract, one lock (T-01M4XR9ESW)
        self.recherche_memo = _routes_mod.MemoRecherche()  # per INSTANCE too: the ~2 MB palette corpus, per ETag
        # T-00000026 shard A: every `/api/stream` poll loop waits on this. Set by `server_close()` BEFORE anything is
        # torn down, so a live SSE stream can never impede shutdown (and never survive it).
        self.stream_stop = threading.Event()

    def server_close(self) -> None:
        """Signal every open SSE loop first, THEN close. Without this the
        streams would still exit — `daemon_threads = True` means
        `ThreadingMixIn` never joins them, and a write to a closed socket
        fails — but they would exit by accident on a timing coincidence
        rather than deterministically, which is not something a test can
        assert on."""
        self.stream_stop.set()
        super().server_close()


def create_ui_server(
    host: str = _UI_HOST,
    port: int = _UI_PORT_DEFAULT,
    project_root: Path | str | None = None,
) -> tuple[UIHTTPServer, str] | None:
    """Bind and return `(server, token)`, or None on a bind failure - never
    raises. Split from `serve_ui()` (the blocking CLI entry point) so a
    caller (this shard's own tests, or shard 2's future lock-file writer)
    can retrieve the token and the actually-bound port WITHOUT scraping
    stdout or entering `serve_forever()`."""
    token = secrets.token_urlsafe(32)
    root = Path(project_root) if project_root is not None else _project_root()
    try:
        httpd = UIHTTPServer((host, port), UIHandler, token, root)
    except OSError:
        return None
    return httpd, token


def serve_ui(host: str = _UI_HOST, port: int = _UI_PORT_DEFAULT) -> dict[str, Any]:
    """Blocking CLI entry point for THIS SHARD's own manual smoke-testing -
    the production launch path (SessionStart hook, singleton lock) is
    shard 2. Fail-open on a bind conflict, mirroring
    `otel_receiver.serve()`: a loud stderr message, never a raised
    exception."""
    result = create_ui_server(host, port)
    if result is None:
        print(f"DASHBOARD UI DEGRADED: bind {host}:{port} failed - no UI server started", file=sys.stderr, flush=True)
        return {"status": "degraded", "host": host, "port": port}
    httpd, token = result
    bound_port = httpd.server_address[1]
    print(f"DASHBOARD UI LISTENING {host}:{bound_port}", flush=True)
    print(f"DASHBOARD UI TOKEN {token}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return {"status": "stopped", "host": host, "port": bound_port}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Dashboard UI/API server (read-only, loopback-only, stdlib). "
        "Server core + /api/* contract (shard 1) + the .agents/ui/ static "
        "service (shard 4a) - no daemon lifecycle, no /dash, no OTLP "
        "collector/normalisation here."
    )
    parser.add_argument("--host", default=_UI_HOST)
    parser.add_argument("--port", type=int, default=_UI_PORT_DEFAULT)
    args = parser.parse_args(argv)

    result = serve_ui(host=args.host, port=args.port)
    return 0 if result["status"] != "degraded" else 2


if __name__ == "__main__":
    sys.exit(main())
