#!/usr/bin/env python3
"""Standalone OTLP/JSON receiver, stdlib only (T-00000025 shard 0).

WHY THIS MODULE EXISTS, SEPARATELY FROM THE FUTURE DASHBOARD: the plan's
blocking gate for the observability dashboard is "capture one real host
emission" (design doc, canal B). The instrument originally slated for that
capture was the spike's throwaway receiver at
`.agents/state/local/otel-spike/receiver.py` — which is git-ignored, and
therefore invisible to BOTH gitleaks (scans Edit/Write content + the
working-tree diff) and this task's cumulative security-review diff. Two
verified defects in that spike receiver made it unfit to be the gate:

  1. `REDACT_KEYS = {"user.email", "organization.id"}` was missing
     `user.id` — and per constraint L-00000040, all three (plus
     `user.account_uuid`) ride on EVERY metric of ALL FOUR hosts.
  2. Inside its `except Exception` handler it wrote the RAW, unredacted
     body to `<fname>.raw.txt` — i.e. the leak fires exactly when the
     payload is unexpected, which is the likely path for first contact with
     real telemetry, not an edge case.

This module supersedes it (the spike file is left in place, referenced by
docs/tasks/T-00000017.md:41 — not deleted) and is a TRACKED, reviewable
artifact: a separate module from the future `dashboard.py` so it (a) exists
before the dashboard does and can serve the capture gate, and (b) lands in
the tracked diff where gitleaks/security-code-review actually see it. Later
shards import THIS module rather than reimplementing capture/redaction.

REDACTION IS SHAPE-AWARE AND A DROP-LIST (L-00000040): OTLP attributes are
LIST ITEMS `{"key": "...", "value": {...}}`, never flat dict keys — matching
on `item["key"]` while walking the WHOLE parsed body recursively covers
every `resource`/`scope`/`logRecord`/`dataPoint` attribute list wherever it
appears, rather than hard-coding each path (see `redact()`). Per
L-00000043 ("audit what a field actually CONTAINS, not what its name
suggests, and cap per field"), this module also (a) redacts any attribute
value that merely LOOKS like an email regardless of its key name, and
(b) caps every surviving attribute string at `_ATTR_VALUE_CAP` chars with a
visible truncation marker — defense in depth against a prompt/response
smuggled under a key name this drop-list does not yet know about.

THERE IS NO RAW-BODY FALLBACK, EVER. A parse/redaction/schema failure
persists a BOUNDED, NON-REVERSIBLE record instead: byte length, content
type, a SHA-256 of the body, and the failure reason — never the body. This
replaces the spike's diagnosability (the reason its sidecar existed) without
reproducing its leak; `get_diagnostics()["parse_failures"]` makes a
systematic failure visible rather than silent.

BIND POLICY (finding B2): the collector binds a FIXED `127.0.0.1:4318`
because all four hosts hard-wire that endpoint
(docs/tasks/T-00000017.md:102-105) and none sends an auth header. That port
is machine-global while this kit is provisioned per project:

  - On EADDRINUSE (or any bind OSError), `serve()` fails OPEN with a loud,
    visible "DEGRADED" marker on stderr and returns without starting a
    listener — never a silent partial start, never a raised exception that
    would crash a caller.
  - Every persisted record carries a first-level `project_id` field, and a
    record whose payload declares a DIFFERENT project id is dropped rather
    than persisted (see `_find_project_attr` / `_ingest_parsed_body`).

    PROVENANCE — VERIFIED, NOT INVENTED: this shard checked
    code.claude.com/docs/en/monitoring-usage (the same source T-00000017
    verified §4.1 against) specifically for a project/cwd/repo identifier
    among Claude Code's resource or standard attributes. THERE IS NONE.
    Claude Code's only resource-level lever is the free-form
    `OTEL_RESOURCE_ATTRIBUTES` env var (operator-set custom key=value pairs
    at launch) — nothing built in. So `_PROJECT_ATTR_KEY` below
    (`agentkit.project_id`) is a KIT-DEFINED convention: V1-c (T-00000050)
    is the activation shard that makes an operator set it via
    `OTEL_RESOURCE_ATTRIBUTES` per project, and
    `project_init.py --print-otel-env` prints the paste-ready block. It is
    still NOT a real OTel/Claude-Code standard attribute, and no host emits
    it on its own.

V1-c — THE POSITIVE SENTINEL (T-00000050, plan-critic iteration 7, C1). Two
things changed here, and the second is the whole point:

  1. THE ATTRIBUTE CARRIES A `project_id`, NOT A PATH. `_PROJECT_ATTR_KEY`
     moved from `agentkit.project_root` (an absolute path) to
     `agentkit.project_id` (the uuid4 `project_init.py` froze in
     `.agents/state/project.json`). A path was ambiguous with the
     `provenance` field, could not survive a moved clone, and — being an
     absolute path under a home directory — was a PII surface every reader
     rendered (L-00000031; `.agents/evals/test_template_hygiene.py`'s
     home-path canary pins the shape).

  2. `persist()` ALWAYS WRITES A FIRST-LEVEL `project_id`: the declared id
     when the payload carries one, otherwise the literal sentinel
     `"unattributed"` — never a path, never an absent field. This is what
     makes attribution decidable downstream on ONE field: `== own id` ->
     attributed, `== another id` -> foreign, `== "unattributed"` ->
     structurally inattributable (Codex, any un-patched host). Before the
     sentinel, "absent" had to mean both "this host cannot declare" and
     "this line predates the mechanism", and the census had to fall back on
     `provenance` — where an unreadable neighbouring payload landed in the
     LOCAL bucket (the exact L-00000049 family).

     `_persist_failure` therefore stamps the sentinel too, and its
     `provenance` is the literal `"unattributed"` rather than
     `str(_project_root())`: a parse failure is by definition a payload we
     could not attribute, and stamping the local root on it both lied and
     wrote this machine's absolute path into a rendered field.

IDENTITY IS RESOLVED, AND RE-RESOLVED (iteration 1, C1). The receiver's own
project id comes from `.agents/state/project.json`, cached, and re-read
BEFORE any drop whenever a declared id does not match (bounded by a stat:
the file's own mtime/size, so a flood of foreign payloads costs one stat
each, not one read each). Without that, a daemon started BEFORE
`project_init.py` ran would freeze on `"unset"` and drop every event of the
pilot who just applied the env block. `"unset"` is never matchable: an
absent identity makes nothing foreign, it just cannot attribute.

ROUTE SEPARATION (finding B3): this module serves exactly
`POST /v1/logs` and `POST /v1/metrics`. Every other path or method —
including a wrong verb on one of those two paths — is a 404, enforced by
`OTLPHandler` overriding every non-POST verb to reject outright (a
`BaseHTTPRequestHandler` with no `do_X` defined would 501, not 404).
Token-exempt by necessity (the four hosts send no auth header), hence
loopback-only bind plus compensating controls, ALL enforced here:
POST-only, a content-type allowlist, a hard body-size cap, schema-checked
normalisation (anything that isn't a JSON object is a bounded failure, never
persisted-as-if-valid), and a request-rate cap with its own counter.
`OTLPHandler` is deliberately a STANDALONE handler class with nothing
shared with any future UI handler — a later dashboard port must be a
separate socket with its own handler class, never this one, so this
loopback/no-auth surface cannot be mounted there by accident.

WRITES: `.agents/state/local/otel/YYYY-MM-DD.<pid>.jsonl`, one file per
WRITER PROCESS — mirroring canal A's option C (`events.py`, constraint
L-00000041: `os.open(O_APPEND)` is NOT atomic across processes on Windows,
measured 10-22% line loss on a shared file). Two receiver processes can
coexist here too (stale-lock reclaim, a `/dash` respawn), hence the pid in
the filename rather than a shared day-file. `newline="\n"` is forced
explicitly (precedent `tasks.py:171`; deliberately NOT `build_index.py`'s
platform default — see that module for why the two differ).
`.agents/state/local/` is git-ignored (`.gitignore:11`); that is
containment, not the control — the redaction above is the control.

T-00000084 — THE HOLDER OF 4318 IS A ROUTER, NOT A SINK. The port is
machine-global while the kit is provisioned per project, so on a machine
with N projects exactly ONE daemon binds it and the other N-1 are
`served_elsewhere`. Until this task the holder DROPPED every payload
declaring a neighbour's `project_id` (`dropped_foreign`), which is silent
data loss for those N-1 projects. It now ROUTES instead, on the same single
decision point (`_ingest_parsed_body`, reached by BOTH the HTTP path and
`otel_normalize.py`'s file catch-up — one point of decision, deliberately):

  * declared id == ours          -> our own spool, unchanged;
  * declared id known to the machine registry (`dashboard_registry.py`,
    T-00000083) AND THE DESTINATION PROVES ITS IDENTITY -> appended to
    `<peer root>/.agents/state/local/otel/YYYY-MM-DD.<OUR pid>.jsonl`.
    The pid in that name is OURS, not the peer's: L-00000041 is "one file
    per WRITER process", and the peer's ingest globs `*.jsonl`, so it picks
    the file up on its next tick and deletes it under its own re-stat guard;
  * anything else                -> `<our otel dir>/orphans/`, a day-file
    keeping the DECLARED id. Never dropped, never relabelled, and counted
    (`orphaned_records`) — L-00000110, we declare what we omit. `orphans/`
    is a SUBDIRECTORY, which is exactly what keeps those lines out of our
    own ingest glob (`*.jsonl` + `exports/*/*.jsonl`, never `orphans/*`).

THE DESTINATION PROVES ITS IDENTITY, EVERY TTL, OR IT GETS NOTHING
(plan-critic, blocking): a registry entry is a claim written by another
process, and writing into a path it names is writing outside this project on
that claim alone. Before ANY write under a peer root we require
`<root>/.agents/state/project.json` to exist and to carry exactly the
`project_id` we are routing for, and `<root>/.agents/state/local/` to
PRE-EXIST (only `otel/` is ever created, `parents=False`). So a re-pointed,
truncated or absent root gets an orphan, never a directory tree conjured
under a stranger's path. The proof is bound to the cache entry and re-run on
every refresh (`_ROUTER_TTL_SECONDS`, 5 s): a root re-pointed after being
proven is not believed for longer than one TTL.

`dropped_foreign` SURVIVES AS A FROZEN COUNTER: nothing increments it any
more (it is structurally 0 since T-00000084), and it is kept because
`event_store.attribution_counters()` and the dashboard render it — a counter
that disappears from the payload reads as "no data", while a 0 next to
`routed_peer`/`orphaned_records` reads as what it is: nothing is dropped any
more.

This module never starts a listener on import — `serve()`/`main()` are the
only things that bind a socket, and only when invoked directly.
"""
from __future__ import annotations

import hashlib
import http.client
import http.server
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bind target (finding B2)
# ---------------------------------------------------------------------------

_HOST = "127.0.0.1"
_PORT = 4318

# ---------------------------------------------------------------------------
# Route separation (finding B3)
# ---------------------------------------------------------------------------

_ALLOWED_PATHS: frozenset[str] = frozenset({"/v1/logs", "/v1/metrics"})
_KIND_BY_PATH: dict[str, str] = {"/v1/logs": "log", "/v1/metrics": "metric"}
_ALLOWED_CONTENT_TYPE = "application/json"

_BODY_SIZE_CAP_DEFAULT = 1_048_576  # 1 MiB: generous for a 5s-interval batch
# export from one host, a hard ceiling against an abusive/malformed sender
# on a token-exempt route.
_RATE_LIMIT_MAX_DEFAULT = 200
_RATE_LIMIT_WINDOW_SECONDS_DEFAULT = 10.0

# Bound on how much of a REJECTED request's body this handler will ever read
# (see OTLPHandler._drain_request_body). Independent of _body_size_cap(): a
# request over that cap must still be drainable without paying its full
# declared cost.
_DRAIN_LIMIT_BYTES = 65536


def _body_size_cap() -> int:
    """`AGENTS_OTEL_BODY_CAP` escape hatch for tests — read live (not cached
    at import) so a test can shrink the cap to a few bytes and exercise the
    over-cap path without constructing a multi-MiB request."""
    override = os.environ.get("AGENTS_OTEL_BODY_CAP")
    if override:
        try:
            return int(override)
        except ValueError:
            pass
    return _BODY_SIZE_CAP_DEFAULT


def _rate_limit_max() -> int:
    override = os.environ.get("AGENTS_OTEL_RATE_LIMIT_MAX")
    if override:
        try:
            return int(override)
        except ValueError:
            pass
    return _RATE_LIMIT_MAX_DEFAULT


def _rate_limit_window_seconds() -> float:
    override = os.environ.get("AGENTS_OTEL_RATE_LIMIT_WINDOW")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return _RATE_LIMIT_WINDOW_SECONDS_DEFAULT


_rate_lock = threading.Lock()
_rate_window: list[float] = []


def _rate_limited() -> bool:
    """Sliding-window request-rate cap (finding B3 compensating control).
    Process-local, in-memory — matches every other counter in this module;
    a rate cap surviving a process restart is not a requirement here."""
    now = time.monotonic()
    with _rate_lock:
        cutoff = now - _rate_limit_window_seconds()
        while _rate_window and _rate_window[0] < cutoff:
            _rate_window.pop(0)
        if len(_rate_window) >= _rate_limit_max():
            return True
        _rate_window.append(now)
        return False


# ---------------------------------------------------------------------------
# Diagnostics (mirrors events.py's C13 pattern: bumped, never raised)
# ---------------------------------------------------------------------------

_DIAGNOSTICS: dict[str, int] = {
    "requests_total": 0,
    "route_rejected_404": 0,
    "bad_content_type": 0,
    "bad_request": 0,
    "body_too_large": 0,
    "rate_limited": 0,
    "parse_failures": 0,
    # V1-c: a payload declaring ANOTHER project's id, dropped server-side.
    # T-00000084 FROZE THIS AT 0 — nothing increments it any more, foreign
    # payloads are routed or orphaned (below). Kept, not deleted: it is part of
    # `event_store.attribution_counters()`'s rendered payload, and a field that
    # vanishes reads as "unknown" where a 0 reads as "none, by construction".
    "dropped_foreign": 0,
    # T-00000084. Both are "since this process started", like every counter
    # here — said out loud wherever displayed, because neither is a row count.
    #   routed_peer      — foreign payloads APPENDED to their own project's
    #                      spool, after that destination proved its identity.
    #   orphaned_records — foreign payloads written to `orphans/`: unknown to
    #                      the registry, or a destination that failed the proof.
    "routed_peer": 0,
    "orphaned_records": 0,
    "identity_reresolved": 0,
    "dropped_fields_by_name": 0,
    "dropped_fields_by_content": 0,
    "truncated_fields": 0,
    "persisted_records": 0,
    # T-00000025 shard 3 / L-00000052 additions below.
    "fingerprinted_content_fields": 0,
    "host_redaction_preserved": 0,
}


def get_diagnostics() -> dict[str, int]:
    """Snapshot of the in-memory counters. Process-local, resets on every
    fresh interpreter — same contract as `events.py.get_diagnostics()`."""
    return dict(_DIAGNOSTICS)


def _reset_state_for_tests() -> None:
    """Test-only helper: zeroes diagnostics, clears the rate-limit window, and
    unregisters the ingest doorbell (a module-level callback left over from one
    test would fire inside the next one). Never called from production code."""
    for key in _DIAGNOSTICS:
        _DIAGNOSTICS[key] = 0
    with _rate_lock:
        _rate_window.clear()
    set_dirty_notifier(None)
    _reset_identity_cache_for_tests()
    # T-00000084: a routing decision proven under one test's tmp roots must
    # never be reused by the next test (or by the next TTL, in production —
    # see `_reset_router_cache`).
    _reset_router_cache()


# ---------------------------------------------------------------------------
# Redaction (L-00000040, L-00000043)
# ---------------------------------------------------------------------------

# Minimum required drop-list, by exact attribute key name (verified against
# code.claude.com/docs/en/monitoring-usage: these ride on EVERY metric/log
# of every host per L-00000031/L-00000040). `user.account_id` is the tagged
# sibling of `user.account_uuid` found during that same verification pass —
# included for the same reason, not explicitly required but same shape of
# risk.
_DROP_KEYS: frozenset[str] = frozenset({
    "user.email",
    "user.id",
    "organization.id",
    "user.account_uuid",
    "user.account_id",
})

# Substring match (case-insensitive) for prompt/response/tool-content
# fields: a drop-LIST, not an allow-list, must not depend on guessing every
# host's exact key spelling (e.g. GenAI semantic-convention names like
# `gen_ai.prompt.0.content` from a non-Claude-Code host normalised through
# this same receiver).
_DROP_KEY_SUBSTRINGS: tuple[str, ...] = (
    "prompt",
    "completion",
    "tool_input",
    "tool_output",
    "tool_response",
    "tool_parameters",
    "message.content",
)

_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ATTR_VALUE_CAP = 500
_ATTR_TRUNC_MARKER = "...<truncated>"
_ATTR_REDACTED_VALUE = {"stringValue": "REDACTED"}

# L-00000052, fix 1/2 (the asymmetry): `_DROP_KEY_SUBSTRINGS` matches
# `prompt`/`tool_input`/etc by SUBSTRING, which also destroys harmless,
# useful integers that merely happen to share a word with a content field —
# `prompt_length` (destroyed) vs `response_length` (survived, no substring
# hit) was the asymmetry measured on GATE A's real traffic. A key ending in
# one of these suffixes is a count/size, never content, and survives
# regardless of which content substring it also happens to contain.
_LENGTH_COUNT_KEY_SUFFIXES: tuple[str, ...] = (
    "_length", "_count", "_size_bytes", "_size", "_bytes",
)

# L-00000052, fix 2/2 (the join key): `prompt.id` matches the `prompt`
# substring above and would otherwise be dropped like `prompt` itself — but
# it is an opaque id, not content, and it is canal A's join key (preserved
# per this task's brief). Exact-key exemption, checked before the
# substring scan.
_JOIN_KEY_EXEMPT: frozenset[str] = frozenset({"prompt.id"})

# The HOST's own redaction marker (Claude Code redacts response/prompt
# content itself, with angle brackets) is distinct from OURS (`REDACTED`,
# no brackets, `_ATTR_REDACTED_VALUE` above) — L-00000052. When a
# content-drop-listed field already carries this exact marker, this
# receiver must NOT re-redact it into our own flat marker: doing so would
# flatten two distinguishable facts ("the host redacted this" vs "we
# redacted this") into one, destroying the very distinction that lets a
# reader attribute a redaction to its author.
_HOST_REDACTED_MARKER = "<REDACTED>"


def _is_length_or_count_key(key: str) -> bool:
    return key.lower().endswith(_LENGTH_COUNT_KEY_SUFFIXES)


def _drop_reason(key: str) -> str | None:
    """`None` (never dropped) if `key` is the join key or a length/count
    field; `"identity"` for the exact PII-identity keys (flat `REDACTED`
    marker, unchanged from before this shard); `"content"` for a
    substring-matched content field (prompt/completion/tool_input/etc —
    fingerprinted, not flattened, see `_fingerprint_attr_value`)."""
    if key in _JOIN_KEY_EXEMPT or _is_length_or_count_key(key):
        return None
    if key in _DROP_KEYS:
        return "identity"
    lowered = key.lower()
    if any(marker in lowered for marker in _DROP_KEY_SUBSTRINGS):
        return "content"
    return None


def _already_host_redacted(value: Any) -> bool:
    return isinstance(value, dict) and value.get("stringValue") == _HOST_REDACTED_MARKER


def _fingerprint_attr_value(value: Any) -> dict[str, Any]:
    """L-00000052, fix 3: overwriting a content field with a flat marker
    destroys the evidence of what the host actually sent — we could no
    longer answer "does Claude Code transmit prompt text at all?". A
    non-reversible fingerprint (byte length + SHA-256) keeps that question
    answerable without retaining the content itself. Falls back to the
    flat marker for a non-string value shape (rare — a content-named field
    is a string in every record observed so far); the fallback is itself
    diagnosable via `dropped_fields_by_name` vs `fingerprinted_content_fields`
    staying at parity or not."""
    string_value = value.get("stringValue") if isinstance(value, dict) else None
    if not isinstance(string_value, str):
        return dict(_ATTR_REDACTED_VALUE)
    encoded = string_value.encode("utf-8", errors="surrogatepass")
    return {
        "agentkitFingerprint": {
            "byteLength": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    }


def _cap_and_flag_value(value: Any) -> Any:
    """L-00000043: audit what the value actually CONTAINS, not just what its
    key claims to be. Applies to every surviving (non-dropped-by-name)
    attribute value: an email-shaped string is redacted regardless of key,
    and any string is capped at `_ATTR_VALUE_CAP` with a visible marker —
    legitimate OTLP attribute values (ids, durations, enum-ish strings) are
    always short; anything longer is itself worth flagging."""
    if isinstance(value, dict):
        string_value = value.get("stringValue")
        if isinstance(string_value, str):
            if _EMAIL_RE.search(string_value):
                _DIAGNOSTICS["dropped_fields_by_content"] += 1
                return dict(_ATTR_REDACTED_VALUE)
            if len(string_value) > _ATTR_VALUE_CAP:
                _DIAGNOSTICS["truncated_fields"] += 1
                capped = dict(value)
                capped["stringValue"] = string_value[:_ATTR_VALUE_CAP] + _ATTR_TRUNC_MARKER
                return capped
    return value


def redact(obj: Any) -> Any:
    """Shape-aware, drop-list redaction (L-00000040). OTLP attributes are
    LIST ITEMS `{"key": "...", "value": {...}}`, never flat dict keys — this
    walks the WHOLE parsed body recursively, so every
    `resource`/`scope`/`logRecord`/`dataPoint` attribute list is covered
    wherever it appears, rather than hard-coding each path. That generic
    walk is what makes this robust to a fifth host, or a schema Claude Code
    adds tomorrow, without a code change here."""
    if isinstance(obj, dict):
        key = obj.get("key")
        if isinstance(key, str) and "value" in obj:
            # Attribute-item shape.
            reason = _drop_reason(key)
            if reason == "identity":
                _DIAGNOSTICS["dropped_fields_by_name"] += 1
                return {"key": key, "value": dict(_ATTR_REDACTED_VALUE)}
            if reason == "content":
                value = obj["value"]
                if _already_host_redacted(value):
                    # The host redacted this itself (L-00000052) — leave its
                    # own marker verbatim, never re-flatten it into ours.
                    _DIAGNOSTICS["host_redaction_preserved"] += 1
                    return {"key": key, "value": value}
                _DIAGNOSTICS["dropped_fields_by_name"] += 1
                _DIAGNOSTICS["fingerprinted_content_fields"] += 1
                return {"key": key, "value": _fingerprint_attr_value(value)}
            capped = _cap_and_flag_value(obj["value"])
            # Recurse into the (possibly capped) value too: arrayValue /
            # kvlistValue can carry NESTED attribute-shaped items even when
            # this item's own key was not dropped.
            return {"key": key, "value": redact(capped)}
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Provenance (finding B2) — see module docstring for the verified-not-
# invented disclosure.
# ---------------------------------------------------------------------------

# KIT-DEFINED convention, NOT a native OTel/Claude-Code attribute (verified
# against code.claude.com/docs/en/monitoring-usage: Claude Code's only
# resource-level lever is the free-form OTEL_RESOURCE_ATTRIBUTES env var,
# with nothing project/cwd related built in). V1-c is the activation shard:
# `project_init.py --print-otel-env` prints
# OTEL_RESOURCE_ATTRIBUTES=agentkit.project_id=<uuid4>, and an operator pastes
# it into the host's own env. THE VALUE IS THE `project_id`, NEVER A PATH —
# see the module docstring's V1-c section for the three reasons.
_PROJECT_ATTR_KEY = "agentkit.project_id"

# THE POSITIVE SENTINEL. Written into `project_id` whenever the payload
# declares nothing, so "this host cannot declare a project" is a VALUE and not
# an absent field. A uuid4 (`project_init.py:228`) can never collide with it.
PROJECT_UNATTRIBUTED = "unattributed"

# Mirrors `event_store.PROJECT_UNSET` — spelled here too because this module
# must never import the store (the store imports THIS one). "no identity yet"
# is deliberately NOT matchable: see `identity_matches`.
PROJECT_UNSET = "unset"


def _project_root() -> Path:
    """The project this RECEIVER PROCESS belongs to — resolved from this
    file's own location by default (`.agents/bin/otel_receiver.py` ->
    parent.parent.parent). `AGENTS_OTEL_PROJECT_ROOT` overrides for tests
    that need to simulate a different project's identity without touching
    a real filesystem tree.

    V1-c: this is NO LONGER an attribution input — nothing compares a
    declared value against it any more, and `_persist_failure` no longer
    stamps it (it was an absolute home path in a rendered field, L-00000031).
    It survives as the anchor the ONE-SHOT backfill uses to recognise
    pre-V1-c lines written by THIS repo (`event_store._backfill_*`)."""
    override = os.environ.get("AGENTS_OTEL_PROJECT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent


def project_json_path() -> Path:
    """`.agents/state/project.json` (T-00000048). `AGENTS_PROJECT_JSON`
    overrides the whole path — the SAME env var `event_store.py` honours, so
    one redirect pins the receiver's identity and the store's classifier to
    one file. Two identities for one process would be two answers to "is this
    line mine"."""
    override = os.environ.get("AGENTS_PROJECT_JSON")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "state" / "project.json"


_identity_lock = threading.Lock()
# (project.json fingerprint, resolved id). The fingerprint is what BOUNDS the
# re-resolution: a mismatch stats the file, and only a file that MOVED is
# re-read. A flood of foreign payloads therefore costs one stat each.
_identity_cache: tuple[tuple, str] | None = None


def _project_json_fingerprint(path: Path) -> tuple:
    try:
        stat_result = path.stat()
    except OSError:
        return (False, None, None)
    return (True, stat_result.st_mtime_ns, stat_result.st_size)


def _read_project_id(path: Path) -> str:
    """The frozen `project_id`, or `PROJECT_UNSET`. Never raises and NEVER
    invents an id (`event_store.resolve_project_id`'s contract, kept
    identical: a value generated here would be a second identity for one
    repo)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return PROJECT_UNSET
    if isinstance(data, dict):
        value = data.get("project_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return PROJECT_UNSET


def resolve_own_project_id(*, force: bool = False) -> str:
    """This process's own `project_id`, cached. `force=True` re-stats
    `project.json` and re-reads it only if it moved — the bounded
    re-resolution iteration 1's C1 asked for: a daemon launched BEFORE
    `project_init.py` ran must not spend its whole life frozen on `"unset"`,
    dropping the traffic of the pilot who just applied the env block."""
    global _identity_cache
    with _identity_lock:
        path = project_json_path()
        cached = _identity_cache
        if cached is not None and not force:
            return cached[1]
        fingerprint = _project_json_fingerprint(path)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        value = _read_project_id(path)
        if cached is not None:
            _DIAGNOSTICS["identity_reresolved"] += 1
        _identity_cache = (fingerprint, value)
        return value


def _reset_identity_cache_for_tests() -> None:
    global _identity_cache
    with _identity_lock:
        _identity_cache = None


def identity_matches(declared: str, own: str) -> bool:
    """Does `declared` name `own`? PURE, and deliberately asymmetric on
    `PROJECT_UNSET`: a store with no identity yet matches NOTHING (not even a
    payload literally declaring `"unset"`), because "I don't know who I am" is
    not a claim that a neighbour's events are mine. Making `unset` matchable
    would turn an un-inited repo into a RECEPTACLE for every neighbouring
    project on this machine — the L-00000049 bleed, made permanent by the
    open-time relabel that would then whiten those rows into the local id
    (plan-critic iteration 2, C1)."""
    if own == PROJECT_UNSET or declared == PROJECT_UNSET:
        return False
    return declared == own


def _find_project_attr(body: Any) -> str | None:
    """Walk `body` for an attribute item keyed `_PROJECT_ATTR_KEY` and
    return its `stringValue`, or None if absent — the case for every host on
    which the operator has not pasted the env block yet (see module
    docstring). Absent is answered with the POSITIVE SENTINEL at persist
    time, never with a path and never with a missing field."""
    if isinstance(body, dict):
        key = body.get("key")
        if isinstance(key, str) and key == _PROJECT_ATTR_KEY and "value" in body:
            value = body["value"]
            if isinstance(value, dict) and isinstance(value.get("stringValue"), str):
                return value["stringValue"]
            return None
        for value in body.values():
            found = _find_project_attr(value)
            if found is not None:
                return found
        return None
    if isinstance(body, list):
        for item in body:
            found = _find_project_attr(item)
            if found is not None:
                return found
        return None
    return None


# ---------------------------------------------------------------------------
# Peer routing (T-00000084) — the holder of 4318 routes for the machine
# ---------------------------------------------------------------------------

# Where a payload we cannot route lands, UNDER our own otel dir. A
# SUBDIRECTORY on purpose: `event_store._source_files` globs `*.jsonl` and
# `exports/*/*.jsonl` and nothing else, so an orphan is kept, readable and
# counted without ever being ingested as if it were ours.
_ORPHAN_DIRNAME = "orphans"

# How long a PROVEN destination stays proven. Same order as the identity
# cache's bound (one stat per foreign payload): a flood of foreign traffic
# costs one registry read per id per 5 s, not one per event — and a root
# re-pointed after being proven is disbelieved within one window.
_ROUTER_TTL_SECONDS = 5.0

# A cap on distinct ids remembered, so a sender looping over invented ids
# cannot grow this dict without bound. Cleared wholesale rather than evicted
# by age: the cache is a 5 s optimisation, not a data structure worth an LRU.
_ROUTER_CACHE_MAX = 256

_router_lock = threading.Lock()
# project_id -> (monotonic expiry, PROVEN spool dir or None). `None` is a
# CACHED NEGATIVE: "not routable right now", which is what bounds the cost of
# an unknown id.
_router_cache: dict[str, tuple[float, Path | None]] = {}

_registry_module: Any = None
_registry_module_failed = False


def _load_registry_module() -> Any:
    """`dashboard_registry.py`, loaded by EXPLICIT PATH — the sibling-load
    contract every module in this directory uses, never `sys.path[0]` (a hook
    feeding python from stdin has no useful one).

    Lazy and at most once: this module is imported by hooks that will never
    route anything, and a failed load is REMEMBERED so a stripped install pays
    one failed import rather than one per event. A failure degrades routing to
    orphans — never an exception on the write path."""
    global _registry_module, _registry_module_failed
    if _registry_module is not None or _registry_module_failed:
        return _registry_module
    try:
        import importlib.util

        path = Path(__file__).resolve().parent / "dashboard_registry.py"
        spec = importlib.util.spec_from_file_location("_otel_router_registry", path)
        if spec is None or spec.loader is None:
            raise ImportError(str(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - routing degrades, it never raises
        _registry_module_failed = True
        return None
    _registry_module = module
    return _registry_module


def _proven_spool_dir(project_id: str, root: Path) -> Path | None:
    """The peer's otel spool, or None — and None is the answer to EVERY doubt.

    A registry entry is a claim written by ANOTHER process; acting on it means
    writing outside this project on that claim alone. So the destination has to
    prove it is who the claim says (plan-critic, blocking finding):

      1. `<root>/.agents/state/project.json` must READ BACK exactly
         `project_id` (`_read_project_id`, which never raises and never
         invents an id — a missing/corrupt file answers `PROJECT_UNSET`,
         which cannot equal any real id);
      2. `<root>/.agents/state/local/` must ALREADY EXIST. A root that has
         been moved, wiped, or never provisioned fails here;
      3. only `otel/` is ever created, `parents=False`. That is what makes
         "we never conjure a directory tree under a stranger's path" a
         property of the call and not of the caller's care.

    Never raises: every failure is None, and None means orphan."""
    state = root / ".agents" / "state"
    if _read_project_id(state / "project.json") != project_id:
        return None
    local = state / "local"
    try:
        if not local.is_dir():
            return None
        target = local / "otel"
        target.mkdir(parents=False, exist_ok=True)
    except OSError:
        return None
    return target


def _peer_spool_for(project_id: str) -> Path | None:
    """The PROVEN spool dir for `project_id`, or None. Registry lookup +
    proof, memoised for `_ROUTER_TTL_SECONDS`.

    Returns the spool rather than the root deliberately: the proof, the
    `local/` pre-existence check and the single `otel/` mkdir are one
    indivisible step, and handing a caller a bare root would let a future
    caller write under it without having paid for that step.

    THE PROOF IS RE-RUN ON EVERY REFRESH, not stamped once: a root re-pointed
    (or wiped) after being proven is believed for at most one TTL. Both the
    positive and the negative answer are cached — that is what bounds a flood
    of unknown ids to one registry read per id per window."""
    now = time.monotonic()
    with _router_lock:
        entry = _router_cache.get(project_id)
        if entry is not None and entry[0] > now:
            return entry[1]
        target: Path | None = None
        registry = _load_registry_module()
        if registry is not None:
            try:
                projects = registry.read_registry().get("projects", {})
            except Exception:  # noqa: BLE001 - `read_registry` already
                projects = {}  # never raises; this is belt and braces
            record = projects.get(project_id) if isinstance(projects, dict) else None
            if isinstance(record, dict):
                root = record.get("project_root")
                if isinstance(root, str) and root.strip():
                    target = _proven_spool_dir(project_id, Path(root))
        if len(_router_cache) >= _ROUTER_CACHE_MAX:
            _router_cache.clear()
        _router_cache[project_id] = (now + _ROUTER_TTL_SECONDS, target)
        return target


def _reset_router_cache() -> None:
    """Forget every routing decision. Called by tests, and by the daemon when
    it RECLAIMS 4318 (`dashboard_daemon.retry_otel_bind`): a process that was
    not the holder has a cache built while it was routing nothing, and the
    machine's registry has necessarily moved since the previous holder died."""
    with _router_lock:
        _router_cache.clear()


def _route_or_orphan(envelope: dict[str, Any], project_id: str) -> None:
    """Append a FOREIGN envelope to its own project's spool, or to `orphans/`.

    The peer write is the only write in this module allowed to fail softly: the
    destination was proven up to `_ROUTER_TTL_SECONDS` ago and can vanish
    between the proof and the `os.open` (the peer's own retention, a moved
    clone, a permission change). Such a failure INVALIDATES the entry and falls
    through to an orphan, so the line is kept either way — losing it is the one
    outcome this whole task exists to remove."""
    target = _peer_spool_for(project_id)
    if target is not None:
        try:
            persist(envelope, target_dir=target)
        except OSError:
            with _router_lock:
                _router_cache.pop(project_id, None)
        else:
            _DIAGNOSTICS["routed_peer"] += 1
            return
    orphans = _otel_dir() / _ORPHAN_DIRNAME
    # OUR OWN tree, so `parents=True` here is the same freedom `_write_line`
    # takes for the local spool — and the reason `_write_line` itself creates
    # nothing when handed a base: whoever names a destination owns its
    # existence, which is what keeps the peer branch from re-creating a tree
    # the proof just found missing.
    orphans.mkdir(parents=True, exist_ok=True)
    persist(envelope, target_dir=orphans)
    _DIAGNOSTICS["orphaned_records"] += 1


# ---------------------------------------------------------------------------
# Writes — one file per writer process (option C, L-00000041)
# ---------------------------------------------------------------------------

_write_lock = threading.Lock()


def _otel_dir() -> Path:
    """`.agents/state/local/otel/` by default, resolved from this file's own
    location (independent of `_project_root()`'s override — a test
    simulating a different provenance must not also redirect real writes).
    `AGENTS_OTEL_DIR` overrides for tests."""
    override = os.environ.get("AGENTS_OTEL_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "state" / "local" / "otel"


def _day_file(now: datetime, pid: int, base: Path | None = None) -> Path:
    """This process's day-file, under `base` when one is given (T-00000084: a
    peer's spool, or our own `orphans/`) and under our own spool otherwise.

    THE NAME IS IDENTICAL IN BOTH CASES, and the pid in it is always OURS —
    L-00000041 is one file per WRITER process, not per owning project. That is
    also what makes a routed file indistinguishable from a locally-written one
    to the peer's ingest, which globs `*.jsonl` and knows nothing about us."""
    return (base or _otel_dir()) / f"{now.strftime('%Y-%m-%d')}.{pid}.jsonl"


def _write_line(line: str, now: datetime, pid: int, base: Path | None = None) -> None:
    """Exactly one O_APPEND write() of one line, to THIS PROCESS's own
    day-file. `os.O_BINARY` (Windows-only; 0 on POSIX) stops the CRT from
    rewriting every "\\n" as "\\r\\n" — same fix as events.py's own write
    path, same reason (precedent `tasks.py:171`).

    CREATES NOTHING WHEN GIVEN A BASE (T-00000084). Our own spool is ours to
    materialise; a destination someone else named is not. So a peer root whose
    `local/` was wiped between the proof and this write fails with an OSError
    the router demotes to an orphan, instead of this line silently rebuilding
    `.agents/state/local/otel/` under a path that is no longer a project."""
    payload = (line + "\n").encode("utf-8")
    target = _day_file(now, pid, base)
    if base is None:
        target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    with _write_lock:
        fd = os.open(str(target), flags, 0o644)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)


# T-00000049 — the ingest doorbell. Set by `dashboard_daemon` to
# `event_store.notify_dirty` when the daemon runs an ingest thread; None
# everywhere else (a hook process, a test, the standalone `--serve` mode).
#
# THIS CARRIES NO RANK AND NO CONTENT, on purpose. An earlier revision of the
# V1-b plan had the receiver hand its own in-memory line counter to the
# ingestion as a `line_index`; that counter restarts at 0 whenever the process
# does, so it drifted from the file's own truth and produced a SECOND identity
# for a line already stored — an ordinary double count (plan-critic iteration 5,
# C4). The single authority for a rank is the ingestion reading the file. This
# is a doorbell: "something grew, you may want to tick early".
_dirty_notifier: Any = None


def set_dirty_notifier(callback: Any) -> None:
    """Register (or clear, with None) the spool-grew callback. Not a hook
    registry: exactly one consumer, the daemon's ingest loop."""
    global _dirty_notifier
    _dirty_notifier = callback


def persist(envelope: dict[str, Any], *, target_dir: Path | None = None) -> None:
    """Append one envelope as a JSON line to this process's own day-file.
    Public and directly callable (not only via the HTTP handler) so tests —
    and the multi-process append probe — can exercise the write path
    without going through a socket.

    V1-c INVARIANT, ENFORCED HERE AND NOT ONLY IN THE CALLERS: every line
    this module ever writes carries a first-level `project_id`. A caller that
    supplies one keeps it (the declared id, or the id
    `attributed_by_construction` established); a caller that supplies none
    gets the POSITIVE SENTINEL. Enforcing it at the single write site is what
    makes "no canal-B line written after V1-c can lack the field" a property
    of the code rather than a habit of its callers — the promise the store's
    five-bucket census is a TOTAL partition rests on.

    `target_dir` (T-00000084) redirects the write to a PROVEN peer spool or to
    our `orphans/`; the directory must already exist (see `_write_line`), and
    the caller owns that. THE DOORBELL IS RUNG FOR OUR OWN SPOOL ONLY: it means
    "our spool grew, tick early" to OUR ingest loop, and handing it a path in
    another project's tree would make our store scan — and delete — files that
    are not ours. `persisted_records` still counts every line THIS PROCESS
    wrote, routed ones included: it measures this writer, not this store."""
    declared = envelope.get("project_id")
    if not isinstance(declared, str) or not declared:
        # A copy, never a mutation of the caller's dict.
        envelope = {**envelope, "project_id": PROJECT_UNATTRIBUTED}
    now = datetime.now(timezone.utc)
    line = json.dumps(envelope, ensure_ascii=False)
    _write_line(line, now, os.getpid(), target_dir)
    _DIAGNOSTICS["persisted_records"] += 1
    notifier = _dirty_notifier
    if notifier is not None and target_dir is None:
        try:
            notifier(_day_file(now, os.getpid()))
        except Exception:  # noqa: BLE001 - a doorbell may never break a writer
            pass


def _bounded_failure_record(body: bytes, content_type: str, reason: str) -> dict[str, Any]:
    """Byte length, content-type, a SHA-256 of the body, and the failure
    reason. NEVER the body itself — this is the direct fix for the spike's
    `except Exception: write raw body` defect."""
    return {
        "reason": reason,
        "byte_length": len(body),
        "content_type": content_type,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _persist_failure(body: bytes, content_type: str, reason: str) -> None:
    """A payload we could not parse is by definition a payload we could not
    attribute: SENTINEL, both in `project_id` and in `provenance`.

    NEVER `str(_project_root())` again (iteration 5, C4 + C4 of iteration 6).
    Two defects in one line: it claimed a neighbouring project's unreadable
    payload as LOCAL spend, and it wrote this machine's absolute home path
    into a field `cost.js` renders (L-00000031 — the shape
    `.agents/evals/test_template_hygiene.py`'s canary pins)."""
    _DIAGNOSTICS["parse_failures"] += 1
    envelope = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "failure",
        "path": None,
        "project_id": PROJECT_UNATTRIBUTED,
        "provenance": PROJECT_UNATTRIBUTED,
        "failure": _bounded_failure_record(body, content_type, reason),
    }
    persist(envelope)


def _envelope(kind: str, path: str, parsed: dict[str, Any], project_id: str) -> dict[str, Any]:
    """The one canal-B envelope shape, built at ONE place (T-00000084).

    Extracted so the routed branch cannot grow a second, subtly different
    shape — and, more to the point, so `redact()` is the only way a body ever
    enters an envelope, whichever project's spool that envelope ends up in."""
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "path": path,
        "project_id": project_id,
        # LEGACY DISPLAY FIELD from here on (iteration 5, C1): nothing
        # classifies on it any more. Kept because it is the only trace of
        # where a pre-V1-c line came from, and the one-shot backfill reads it.
        "provenance": project_id,
        "body": redact(parsed),
    }


def _ingest_parsed_body(kind: str, path: str, parsed: dict[str, Any],
                        *, attributed_by_construction: bool = False) -> None:
    """Attribution-check -> redact -> persist. The shared TAIL of ingestion,
    used by `process_request` (the HTTP path, below) AND by
    `otel_normalize.py`'s Gemini file catch-up (T-00000025 shard 3) — the
    file catch-up path calls this directly with its own already-parsed JSON
    object rather than reimplementing redaction, per that shard's own
    non-negotiable: no second, weaker redaction path outside this module.

    `attributed_by_construction=True` (single caller: `otel_normalize`'s file
    catch-up, one line) WRITES the local id. Gemini's export `outfile` lives
    INSIDE this repo, so a line found there belongs to this project as a
    FACT, not as a guess — and short-circuiting only the drop would have left
    those records in `unattributed` for ever while
    `HOST_ATTRIBUTION`/`HOST_METRICS_COVERAGE` declared Gemini attributable:
    the dashboard contradicting itself about one host (iteration 5, C2).

    T-00000084 — THE SINGLE POINT OF DECISION, and it now ROUTES. Both callers
    pass through here, so the file catch-up's foreign lines are routed exactly
    like the socket's: that is deliberate, one decision beats two policies that
    drift. Nothing is dropped any more (see the module docstring)."""
    declared = _find_project_attr(parsed)
    own = resolve_own_project_id()
    if declared is not None and not identity_matches(declared, own):
        # RE-RESOLVE BEFORE ROUTING AWAY (iteration 1, C1). The identity may
        # have been written by `project_init.py` after this process started; a
        # frozen `"unset"` would otherwise send exactly the traffic the pilot
        # just finished wiring up to a peer — or to `orphans/`.
        own = resolve_own_project_id(force=True)
        if not identity_matches(declared, own):
            # Another project's session. WAS: dropped server-side, which is
            # silent data loss for every non-holder on the machine. NOW: routed
            # to that project's own spool if it proves its identity, orphaned
            # otherwise. Redacted FIRST, either way — a peer's store is not a
            # reason to relax the one control this module has. An HTTP caller
            # still gets its normal 200 in both cases.
            _route_or_orphan(_envelope(kind, path, parsed, declared), declared)
            return

    if declared is not None:
        project_id = declared
    elif attributed_by_construction:
        # Same bounded re-resolution as the drop path above, for the same
        # reason: the file catch-up is exactly where a session that ran BEFORE
        # `project_init.py` gets picked up, and a frozen `"unset"` would
        # sentinel those lines for ever even though the file proves they are
        # ours.
        if own == PROJECT_UNSET:
            own = resolve_own_project_id(force=True)
        project_id = own if own != PROJECT_UNSET else PROJECT_UNATTRIBUTED
    else:
        project_id = PROJECT_UNATTRIBUTED
    persist(_envelope(kind, path, parsed, project_id))


def process_request(kind: str, path: str, body: bytes, content_type: str) -> None:
    """Parse -> schema-check -> `_ingest_parsed_body` (provenance-check ->
    redact -> persist). Never raises: every failure branch persists a
    bounded failure record and returns. Callable directly (used by tests
    and by `OTLPHandler`) so the core logic is exercised without a live
    socket."""
    try:
        text = body.decode("utf-8")
        parsed = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _persist_failure(body, content_type, "json_decode_error")
        return

    if not isinstance(parsed, dict):
        _persist_failure(body, content_type, "not_a_json_object")
        return

    _ingest_parsed_body(kind, path, parsed)


# ---------------------------------------------------------------------------
# HTTP handler (finding B3) — standalone, POST-only, two routes, nothing
# else. A future UI handler MUST be its own class on its own socket.
# ---------------------------------------------------------------------------

class OTLPHandler(http.server.BaseHTTPRequestHandler):
    """Serves ONLY `POST /v1/logs` and `POST /v1/metrics`. Every other verb
    is overridden here to reject outright (a `BaseHTTPRequestHandler` with
    no `do_X` defined replies 501, not 404 — this class must 404 on all of
    them, including a wrong verb on an otherwise-valid path)."""

    server_version = "agentkit-otel-receiver/1"

    def do_POST(self) -> None:
        self._handle_post()

    def do_GET(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def do_PUT(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def do_DELETE(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def do_PATCH(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def do_HEAD(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def do_OPTIONS(self) -> None:
        self._reject(404, "not_found", "route_rejected_404")

    def log_message(self, *args: Any) -> None:
        # Quiet by design (matches the spike's handler): failures are
        # observable via get_diagnostics(), not stderr chatter.
        pass

    def _drain_request_body(self) -> None:
        """Windows flake fix (reproduced 3x in dev, not theoretical):
        responding then closing a connection that STILL has unread request
        bytes sitting in the socket can make Windows send a hard RST instead
        of a graceful FIN, which the CLIENT then sees as
        `ConnectionAbortedError [WinError 10053]` while reading the
        response — intermittent, and easy to misdiagnose as test flakiness
        rather than a real defect in this handler. Draining clears it. Bound
        the drain to `_DRAIN_LIMIT_BYTES` regardless of the request's
        declared Content-Length so an attacker-declared multi-GB body still
        costs this handler at most that bound, never the full claimed size —
        the 413 path's whole point is to NOT pay for an oversized body."""
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

    def _reject(self, status: int, reason: str, count_key: str) -> None:
        self._drain_request_body()
        _DIAGNOSTICS[count_key] += 1
        body = json.dumps({"error": reason}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _accept(self) -> None:
        body = b'{"partialSuccess":{}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _handle_post(self) -> None:
        _DIAGNOSTICS["requests_total"] += 1

        if self.path not in _ALLOWED_PATHS:
            self._reject(404, "not_found", "route_rejected_404")
            return

        if _rate_limited():
            self._reject(429, "rate_limited", "rate_limited")
            return

        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != _ALLOWED_CONTENT_TYPE:
            self._reject(415, "unsupported_content_type", "bad_content_type")
            return

        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._reject(400, "missing_or_invalid_content_length", "bad_request")
            return
        if length < 0:
            self._reject(400, "missing_or_invalid_content_length", "bad_request")
            return
        if length > _body_size_cap():
            # Deliberately do NOT read the body: nothing persisted, nothing
            # hashed, no time spent on an oversized/abusive payload.
            self._reject(413, "body_too_large", "body_too_large")
            return

        body = self.rfile.read(length) if length else b""
        kind = _KIND_BY_PATH[self.path]
        process_request(kind, self.path, body, content_type)
        self._accept()


# ---------------------------------------------------------------------------
# Bind + serve (finding B2 — fail open with a visible degraded marker)
# ---------------------------------------------------------------------------

class _ExclusiveHTTPServer(http.server.HTTPServer):
    """HTTPServer that refuses to share its port — by the means each OS requires.

    THE INVARIANT, one sentence: no second listener on our address:port, ever,
    and a re-bind as soon as the previous holder is gone. SO_REUSEADDR helps one
    of those on POSIX and breaks the other on Windows, so it is set PER PLATFORM
    (T-00000055) — both facts below were measured, on this host and in the CI
    ubuntu image, not read off a man page.

    **Windows — SO_REUSEADDR must stay OFF (L-00000050).** `http.server.HTTPServer`
    defaults it ON, and on Windows SO_REUSEADDR permits a SECOND LIVE bind to the
    same address:port when the holder set it too — measured: `holder_reuse=True,
    second_reuse=True` -> the second bind SUCCEEDS; clear either side and the OS
    returns WinError 10048. Inheriting the default therefore made `serve()`'s
    EADDRINUSE branch — the whole fail-open-with-a-visible-degraded-marker control
    — UNREACHABLE on this kit's main dev platform, and let two receivers split one
    host's telemetry non-deterministically. Observed live, not theorised: a manual
    launch and a background launch coexisted on 4318, neither reporting a conflict.

    **POSIX — SO_REUSEADDR must be ON, and concedes nothing.** Measured in the CI
    image (linux 6.x, python:3-slim), all four combinations of holder/re-binder
    SO_REUSEADDR against a LIVE listener: EADDRINUSE every time. On POSIX stealing
    a live listener needs SO_REUSEPORT, which is a different option and stays off
    (`allow_reuse_port = False` below, pinned rather than inherited). What
    SO_REUSEADDR *does* buy is the re-bind over a TIME_WAIT residue — and the
    kernel requires it on BOTH the socket that entered TIME_WAIT and the re-binder
    (`inet_csk_bind_conflict`: no conflict only when both carry `sk_reuse` and the
    other socket is not LISTEN). That is exactly V1-c's dead-peer path: probing a
    peer leaves the PEER's accepted connection in TIME_WAIT on our port, so with
    this option off the survivor could not reclaim 4318 for a full TIME_WAIT
    window (~60 s) after the peer died — the port-reclaim mechanism was
    FUNCTIONALLY degraded on Linux, not merely under-tested, and the daemon's
    30 s poll spent that window logging EADDRINUSE against a dead peer.

    Layer two, unchanged: SO_EXCLUSIVEADDRUSE (Windows only) — ANOTHER process
    cannot hijack the port by setting SO_REUSEADDR itself, which the flag above
    cannot prevent on its own. This matters because the port is fixed at 4318
    (every host hard-wires it) and unauthenticated by necessity, so whoever holds
    it receives the telemetry. Combined with L-00000049 (no host stamps a project
    identifier), a hijack is not detectable after the fact — only preventable.
    POSIX needs no equivalent: the measurement above shows a live listener is
    never yielded there, whatever the challenger sets.
    """

    # Windows: OFF (a second live bind would be permitted). POSIX: ON (concedes
    # no live listener, and is REQUIRED to re-bind over TIME_WAIT).
    allow_reuse_address = os.name != "nt"

    # Pinned, not inherited: SO_REUSEPORT is the option that WOULD hand a live
    # POSIX listener to a challenger, i.e. the one thing allow_reuse_address is
    # measured not to do. Added to socketserver in 3.11+; harmless on older ones.
    allow_reuse_port = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:            # Windows only; absent on POSIX
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError:
                pass                         # best effort: layer 1 still holds
        super().server_bind()


# ---------------------------------------------------------------------------
# Who holds 4318? (V1-c / spec §A.4 — coexist, never fight.)
# ---------------------------------------------------------------------------

# `OTLPHandler.server_version` + "/" — matched by PREFIX so a future
# "agentkit-otel-receiver/2" is still recognised as one of ours (iteration 1,
# C7: an equality check would call the next version of this same kit a
# stranger and turn a civil coexistence into a fight).
_KIT_SERVER_PREFIX = "agentkit-otel-receiver/"

# The probe's whole budget. A holder that cannot answer a 5-line GET inside
# this is treated as `unreachable`, i.e. as a port worth re-binding — never as
# a peer to defer to for ever.
_PROBE_TIMEOUT_SECONDS = 1.0


def probe_port_holder(host: str | None = None, port: int | None = None,
                      timeout: float = _PROBE_TIMEOUT_SECONDS) -> dict[str, Any]:
    """WHO holds this port? `kit_peer` | `foreign` | `unreachable`.

    `host`/`port` default to `_HOST`/`_PORT` RESOLVED AT CALL TIME, not captured
    in the signature. Found by this module's own daemon test: a default argument
    is evaluated once at import, so a caller that had just failed to bind a
    DIFFERENT port would have been told, confidently, about whoever holds 4318 —
    a probe reporting on the wrong socket is worse than no probe. Callers that
    know which address they tried should pass it explicitly anyway.

    A short GET on `/`, classified on the response's `Server` header. NO NEW
    ROUTE IS ADDED FOR THIS, on purpose: `OTLPHandler` already 404s every GET
    (route separation, finding B3) and `BaseHTTPRequestHandler` already puts
    `Server: agentkit-otel-receiver/1` on that 404. A dedicated identity route
    would be a second unauthenticated surface on a token-exempt port, bought
    for information the 404 already carries.

    The three answers are three DIFFERENT decisions for the caller, which is
    why they are not collapsed:
      * `kit_peer`    — another provisioned project's daemon. It redacts and
        persists exactly like we do, so the honest report is "canal B is
        served elsewhere", NOT a failure. We never try to take the port from
        it: neither side CAN steal a live listener on either platform —
        SO_EXCLUSIVEADDRUSE on Windows (L-00000050), the kernel's own refusal
        on POSIX whatever SO_REUSEADDR says (measured, T-00000055) — and
        killing a peer would take down another project's trail.
      * `foreign`     — something else entirely owns 4318. Canal B is
        DEGRADED for this machine and the operator has to know: our hosts
        will keep POSTing telemetry into a process we know nothing about.
      * `unreachable` — nobody answered. The bind failure was a race, or the
        holder just died; the caller RE-TRIES the bind rather than recording
        a permanent verdict (iteration 1, C6).

    Never raises: every failure mode is `unreachable` with a reason."""
    host = _HOST if host is None else host
    port = _PORT if port is None else port
    conn = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", "/")
        response = conn.getresponse()
        server = response.getheader("Server") or ""
        try:
            response.read()
        except OSError:
            pass
        holder = "kit_peer" if server.startswith(_KIT_SERVER_PREFIX) else "foreign"
        return {"holder": holder, "server": server, "status": response.status,
                "reason": None}
    except Exception as exc:  # noqa: BLE001 - a probe may never raise past here
        return {"holder": "unreachable", "server": None, "status": None,
                "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def serve(host: str = _HOST, port: int = _PORT) -> dict[str, Any]:
    """Bind and serve forever. Returns a dict describing how the attempt
    ended: `{"status": "degraded", ...}` on a bind failure (EADDRINUSE or
    equivalent — no listener started, a loud stderr message, NEVER a raised
    exception) or `{"status": "stopped", ...}` once `serve_forever()`
    returns (shutdown() called, or KeyboardInterrupt). This function never
    starts a listener as a side effect of import — only when called."""
    try:
        httpd = _ExclusiveHTTPServer((host, port), OTLPHandler)
    except OSError as exc:
        message = (
            f"OTEL RECEIVER DEGRADED: bind {host}:{port} failed ({exc}) — "
            "no receiver started for this process"
        )
        print(message, file=sys.stderr, flush=True)
        return {"status": "degraded", "reason": str(exc), "host": host, "port": port}

    print(f"OTEL RECEIVER LISTENING {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return {"status": "stopped", "host": host, "port": port}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Standalone OTLP/JSON receiver (loopback-only, PII-redacting). "
        "Do not run this against a real host session outside a pilot-approved run."
    )
    parser.add_argument("--host", default=_HOST)
    parser.add_argument("--port", type=int, default=_PORT)
    args = parser.parse_args(argv)

    result = serve(host=args.host, port=args.port)
    return 0 if result["status"] != "degraded" else 2


if __name__ == "__main__":
    sys.exit(main())
