#!/usr/bin/env python3
"""Canal-B normalisation + host-generic file catch-up (T-00000025 shard 3).

WHAT THIS SHARD IS, AND IS NOT: shard 3 of the split in `docs/tasks/T-00000025.md`
covers ONLY: (a) mapping already-redacted, already-persisted OTLP envelopes
(`otel_receiver.py`, shard 0 — extended, not forked, by that module's own
redaction fixes below) into the frozen `CANAL_B_RECORD_SCHEMA` declared in
`dashboard.py` (shard 1), and (b) a host-generic file catch-up mechanism,
wired and tested for Gemini only. It does NOT touch the daemon lifecycle, the
lock file, `/dash`, `session-start.sh` (shard 2), the UI (shard 4), or
`dashboard.py`'s `/api/*` routes / frozen schema constant (shard 1, landed) —
this module normalises TO that schema, it does not redeclare it.

NORMALISATION NEVER RE-REDACTS (non-negotiable #1): every function below
reads a `body` that already went through `otel_receiver.redact()` at capture
time (either via the HTTP path — `process_request` — or via this module's
own file catch-up path — `_ingest_parsed_body`, both in `otel_receiver.py`).
This module only RESHAPES already-safe data; it never re-parses raw OTLP
attribute lists for PII the way `otel_receiver.redact()` does, and it must
never grow a second drop-list of its own.

TWO MEASURED DRIFTS AGAINST THE TASK BRIEF, FLAGGED HERE RATHER THAN
SILENTLY RESOLVED (see `_SCHEMA_FIELDS` and `normalize_log_record` below for
detail): (1) `dashboard.py`'s frozen schema lists `type` for BOTH
`claude_code.cost.usage` and `claude_code.token.usage`; on the 49 real
Claude Code records captured for GATE A, `token.usage` carries `type` on
56/56 dataPoints and `cost.usage` on 0/14 — cost is a single dollar total
per request, not per token-type, so it cannot structurally carry `type`.
(2) The brief (and `dashboard.py`'s own docstring) state "`prompt.id` is
present on EVERY log record"; measured on the same 49 records,
`hook_registered` (0/66) and `plugin_loaded` (0/24) never carry it, and
`hook_execution_start`/`_complete` (18/20) and `mcp_server_connection` (2/5)
carry it only some of the time — it IS present on every per-turn/cost event
this dashboard actually needs to join (`api_request`, `assistant_response`,
`tool_decision`, `tool_result`, `subagent_completed`, `user_prompt`: 100% in
this sample), just not on session-lifecycle events. Neither drift is
resolved here (the schema constant is frozen for this shard); both are
handled by never inventing a field that is not present — `fields`/
`prompt_id` are simply absent, never defaulted or fabricated.

NON-NEGOTIABLE #7 — CODEX METRICS ARE ABSENT, NOT EMPTY: `cost_summary_for_host`
below distinguishes "no cost.usage record for this host because the host
does not emit OTel metrics at all" (Codex, `openai/codex#12913` — verified
in `docs/tasks/T-00000017.md` §8, a documented fact, not something this
task could measure live) from "no cost.usage record observed YET" (the
`no_data_yet` status). Neither is ever silently rendered as a `$0` total —
this is the exact false-GO shape L-010 already named for a different gate.

HOST-GENERIC FILE CATCH-UP, GEMINI ONLY (non-negotiable #6): Gemini is
NO-GO on the HTTP collector (`docs/tasks/T-00000017.md` §8 — defaults to
grpc on :4317, json-vs-protobuf undocumented); its path is the file export
(`telemetry.target: "local"` + `outfile`). `PARSER_REGISTRY` is
HOST-GENERIC (a dict, not a Gemini-specific function signature) so a future
host slots in without reshaping this module, but only `"gemini"` has an
implemented parser — `"copilot"`'s slot is registered with `None` on
purpose: Copilot's primary path is HTTP (GO per the spike), and a tested
parser against its unobserved file format (if one even exists) would be
code written against a guess twice over.

GEMINI'S FORMAT IS UNOBSERVED — SAID PLAINLY, NOT GUESSED PAST: no session
in this task's history could relaunch the Gemini CLI with file export
enabled (the same limitation the T-00000017 spike hit). `_parse_gemini_line`
is written against the OTLP/JSON attribute shape Gemini's OTHER export
target uses, on the unverified assumption the file target serialises the
same envelope one line at a time. `catch_up_host_files` fails SOFT on this
uncertainty: a line that is not valid JSON, or valid JSON that is not an
object, is counted and skipped, never raised past; if EVERY line in a
non-empty set of files fails to parse, the result carries
`status: "degraded_no_lines_parsed"` — a visible degraded signal, not a
silent zero-ingested. CONFIRMING the assumed shape requires a live Gemini
session with file export enabled — flagged as a FOLLOW-UP, not resolved
here.

V1-c (T-00000050) ADDS TWO THINGS AND FORKS NOTHING: (a) both mappers now
copy the envelope's promoted `project_id` (+ `project_attributed_by`) into
the normalised record via `_attribution_of` — before this, the field the
receiver promotes stopped at the database and the display layer went on
classifying spend on `provenance`, an absolute path for pre-V1-c lines;
(b) `iter_normalized_records_from_bodies` reads canal B from the SQLite
store's `body` column. It is a VARIANT of the same mappers, not a second
implementation — only the source of the lines differs.

WINDOWS (non-negotiable #8): the catch-up cursor file
(`.catchup-cursor.<host>.json`, alongside the per-writer `.jsonl` files
under the same `AGENTS_OTEL_DIR`) is written with `newline="\n"` explicit,
same precedent as `otel_receiver.py`'s own writes (`tasks.py:171`).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Explicit-path module load (`events.py`'s IMPORT CONTRACT,
    `test_otel_receiver.py`'s own convention) — this module's ONLY
    dependency is `otel_receiver.py`. It deliberately does not import
    `dashboard.py`: that would pull in tasks/ledger/specs/build_index/
    events transitively for a module whose whole job is to stay a small,
    independently testable normaliser, and `dashboard.py`'s schema section
    is frozen for this shard anyway — nothing to read from it at runtime."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_otel_receiver = _load_sibling("_otel_normalize_receiver", "otel_receiver.py")


# ---------------------------------------------------------------------------
# Schema target — kept IN SYNC BY HAND with `dashboard.py`'s
# `CANAL_B_RECORD_SCHEMA` (frozen there, not imported from here — see
# module docstring). `_SCHEMA_FIELDS` is the ALLOWED set per family: a
# normalised record only ever carries fields it actually found present,
# never a fabricated/defaulted one for a field the schema lists but a real
# record does not carry (see the `type` drift in the module docstring).
# ---------------------------------------------------------------------------

# T-00000073: the 2 DIMENSIONED metrics summed by `metric_totals_for_host` are
# promoted here so their attributes reach `fields` (LOC's `type`, edit-tool's
# `decision`). The 3 SCALARS (session.count, active_time.total, commit.count)
# are deliberately NOT promoted — they are summed by `metric_name` alone with no
# per-dimension breakdown, mirroring the `mcp_server_connection` "counted by
# name, never promoted" precedent (dashboard.py:1469-1471). Promoting these 2
# makes them appear in the `hosts.families` census (dashboard.py:1481-1483)
# ahead of the T-00000186 display work — intended, not a regression.
_METRIC_FAMILIES = frozenset({
    "claude_code.cost.usage", "claude_code.token.usage",
    "claude_code.lines_of_code.count", "claude_code.code_edit_tool.decision",
})
_LOG_FAMILIES = frozenset({"api_request", "subagent_completed", "tool_decision"})

_SCHEMA_FIELDS: dict[str, tuple[str, ...]] = {
    # `session.id` (T-00000096): present on every real cost/token dataPoint
    # (measured on this repo's own store), NOT in any redaction drop-list, and
    # the ONLY key that lets a reader answer "what did THIS session cost" — the
    # number Claude Code itself displays. Before this, the allow-list silently
    # dropped it and the dashboard could only ever show the 30-day project
    # total, which its KPI then mislabelled "coût session". Normalisation
    # happens at READ time over stored raw bodies, so the field appears
    # retroactively on every already-ingested row.
    "claude_code.cost.usage": ("agent.name", "model", "effort", "query_source", "type", "session.id"),
    "claude_code.token.usage": ("agent.name", "model", "effort", "query_source", "type", "session.id"),
    # T-00000073 (C7): keyed by the FULL metric name, matching `_METRIC_FAMILIES`
    # and `by_metric_name`. The attribute names below are VENDOR-DOCUMENTED, not
    # yet observed in a real capture (no such dataPoint in the Gate A fixture) —
    # the epistemic grade is spelled out in dashboard.py's CANAL_B_RECORD_SCHEMA
    # header. NB: this map uses full names throughout, but the hand-synced
    # `CANAL_B_RECORD_SCHEMA` still carries one PRE-EXISTING short key,
    # `"token.usage"` (dashboard.py:785) — that divergence is out of this task's
    # scope and is left as-is.
    "claude_code.lines_of_code.count": ("type",),
    "claude_code.code_edit_tool.decision": ("decision", "tool_name", "language"),
    "api_request": (
        "cost_usd", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens", "duration_ms",
    ),
    "subagent_completed": ("agent_type", "total_tokens", "total_tool_uses", "duration_ms"),
    "tool_decision": ("decision", "source"),
}


def _attrs_to_dict(attrs: list[Any] | None) -> dict[str, Any]:
    """OTLP attribute LIST ITEMS (`{"key": ..., "value": {...}}` —
    L-00000040) to a flat lookup dict, scalar-typed where the shape is a
    plain OTLP scalar. A redacted/fingerprinted value (`{"agentkitFingerprint":
    {...}}`, `{"stringValue": "REDACTED"}`) has none of the scalar keys
    below and is preserved AS ITS DICT, never coerced or dropped — a
    normalised record must show that a field was present-but-redacted, not
    silently omit it (that would look identical to "field absent")."""
    out: dict[str, Any] = {}
    for item in attrs or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str):
            continue
        value = item.get("value")
        if not isinstance(value, dict):
            out[key] = value
            continue
        if "stringValue" in value:
            out[key] = value["stringValue"]
        elif "intValue" in value:
            out[key] = value["intValue"]
        elif "doubleValue" in value:
            out[key] = value["doubleValue"]
        elif "boolValue" in value:
            out[key] = value["boolValue"]
        else:
            out[key] = value  # e.g. agentkitFingerprint - preserved whole
    return out


def _resource_host(body: dict[str, Any], resource_key: str) -> str:
    """`service.name` off the FIRST resource entry found (e.g. "claude-code")
    - falls back to "unknown" rather than raising for a body shape that
    does not carry a resource at all (a Gemini file-catch-up line, most
    likely, given its format is unobserved)."""
    for entry in body.get(resource_key, []) or []:
        if not isinstance(entry, dict):
            continue
        attrs = _attrs_to_dict(entry.get("resource", {}).get("attributes", []))
        name = attrs.get("service.name")
        if isinstance(name, str):
            return name
    return "unknown"


def _attribution_of(envelope: dict[str, Any]) -> dict[str, Any]:
    """The attribution fields EVERY normalised record carries, extracted ONCE
    and spread into both mappers (V1-c, plan-critic iteration 4, C1).

    `project_id` is the decisive one: before V1-c the mappers copied only
    `provenance`, so the promoted field stopped at the database and the
    display layer — the very reason V1-c exists — went on classifying spend on
    a field the plan had just declared unreliable (an absolute path for
    pre-V1-c lines).

    `project_attributed_by` is the QUALITY OF THE PROOF, kept per row rather
    than as a global count (iteration 9, C3): `"backfill"` means the one-shot
    pass INFERRED this line's project from its path, next to lines attributed
    by DECLARATION. One counter holding two qualities of evidence is how an
    inference quietly becomes a measurement. `None` when absent — never
    defaulted to a value that would claim a declaration nobody made.

    `provenance` is passed through unchanged as a LEGACY DISPLAY field."""
    return {
        "provenance": envelope.get("provenance"),
        "project_id": envelope.get("project_id"),
        "project_attributed_by": envelope.get("project_attributed_by"),
    }


def normalize_log_record(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """One normalised record per `logRecord` found in this envelope's body.
    Never raises: a body that is not the expected `resourceLogs` shape
    (absent, wrong type, empty) yields an empty list, not an exception —
    the caller (`iter_normalized_records`) counts this as "nothing to
    normalise here", not a failure."""
    out: list[dict[str, Any]] = []
    body = envelope.get("body")
    if not isinstance(body, dict):
        return out
    host = _resource_host(body, "resourceLogs")
    for res_log in body.get("resourceLogs", []) or []:
        if not isinstance(res_log, dict):
            continue
        for scope_log in res_log.get("scopeLogs", []) or []:
            if not isinstance(scope_log, dict):
                continue
            for log_record in scope_log.get("logRecords", []) or []:
                if not isinstance(log_record, dict):
                    continue
                attrs = _attrs_to_dict(log_record.get("attributes", []))
                event_name = attrs.get("event.name")
                family = event_name if event_name in _LOG_FAMILIES else None
                allowed = _SCHEMA_FIELDS.get(family, ())
                fields = {k: attrs[k] for k in allowed if k in attrs}
                out.append({
                    "ts": envelope.get("ts"),
                    "kind": "log",
                    "host": host,
                    **_attribution_of(envelope),
                    "source": envelope.get("path"),
                    "event_name": event_name,
                    "schema_family": family,
                    # Canal-A join key - None (never fabricated), matching
                    # the measured absence on session-lifecycle events (see
                    # module docstring).
                    "prompt_id": attrs.get("prompt.id"),
                    "fields": fields,
                })
    return out


def normalize_metric_record(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """One normalised record per metric dataPoint. Same never-raises
    contract as `normalize_log_record`."""
    out: list[dict[str, Any]] = []
    body = envelope.get("body")
    if not isinstance(body, dict):
        return out
    host = _resource_host(body, "resourceMetrics")
    for res_met in body.get("resourceMetrics", []) or []:
        if not isinstance(res_met, dict):
            continue
        for scope_met in res_met.get("scopeMetrics", []) or []:
            if not isinstance(scope_met, dict):
                continue
            for metric in scope_met.get("metrics", []) or []:
                if not isinstance(metric, dict):
                    continue
                name = metric.get("name")
                family = name if name in _METRIC_FAMILIES else None
                allowed = _SCHEMA_FIELDS.get(family, ())
                for shape_key in ("sum", "gauge", "histogram"):
                    container = metric.get(shape_key)
                    if not isinstance(container, dict):
                        continue
                    for dp in container.get("dataPoints", []) or []:
                        if not isinstance(dp, dict):
                            continue
                        attrs = _attrs_to_dict(dp.get("attributes", []))
                        fields = {k: attrs[k] for k in allowed if k in attrs}
                        out.append({
                            "ts": envelope.get("ts"),
                            "kind": "metric",
                            "host": host,
                            **_attribution_of(envelope),
                            "source": envelope.get("path"),
                            "metric_name": name,
                            "schema_family": family,
                            "value": dp.get("asDouble", dp.get("asInt")),
                            "fields": fields,
                        })
    return out


def normalize_envelope(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispatch on `envelope["kind"]` - `"log"` and any `*_file` kind (the
    file catch-up path tags its envelopes `<host>_file`, e.g. `gemini_file`)
    are treated as log-shaped since Gemini's format is UNOBSERVED and this
    is the only shape we have evidence for (see module docstring); `"metric"`
    dispatches to the metric mapper; `"failure"` (a bounded parse-failure
    record from `otel_receiver.py`) and anything else normalise to nothing
    - a failure record has no schema-family content to extract, it is
    already fully represented by its own `failure` sub-record."""
    kind = envelope.get("kind")
    if kind == "metric":
        return normalize_metric_record(envelope)
    if kind == "log" or (isinstance(kind, str) and kind.endswith("_file")):
        return normalize_log_record(envelope)
    return []


def _parse_envelope_lines(lines: Any) -> tuple[list[dict[str, Any]], int]:
    """`(envelopes, malformed)` from an iterable of JSON TEXT lines. THE one
    parse step, shared by both sources below: a line that is not valid JSON, or
    valid JSON that is not an object, is counted and skipped — never raised
    past, matching every other reader in this kit's tolerance for a write caught
    mid-flush."""
    envelopes: list[dict[str, Any]] = []
    malformed = 0
    for line in lines:
        if not isinstance(line, str) or not line.strip():
            continue
        try:
            envelope = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            malformed += 1
            continue
        if not isinstance(envelope, dict):
            malformed += 1
            continue
        envelopes.append(envelope)
    return envelopes, malformed


def normalize_envelopes(envelopes: Any) -> list[dict[str, Any]]:
    """Every normalised record of every envelope, in order. The mappers, once."""
    records: list[dict[str, Any]] = []
    for envelope in envelopes:
        records.extend(normalize_envelope(envelope))
    return records


def iter_envelopes(otel_dir: Path) -> tuple[list[dict[str, Any]], int]:
    """Read every `*.jsonl` under `otel_dir` (glob, never assume one file -
    same reader-aggregates contract `events.py`/`dashboard.py` already use for
    their own per-writer files) and return the PARSED ENVELOPES.

    WHY THE ENVELOPE LEVEL IS EXPOSED (V1-c, found on real data): an envelope
    can be a real, stored ROW and still normalise to ZERO records — a `failure`
    record has no schema-family content, and a `kind` outside the known set
    normalises to nothing by design. A census of ROWS computed from normalised
    RECORDS therefore silently omits exactly those, including a QUARANTINED row
    whose kind is unknown: the silent subtraction the attribution block exists
    to prevent. The row census reads envelopes; the money reads records."""
    if not otel_dir.exists():
        return [], 0
    lines: list[str] = []
    for path in sorted(otel_dir.glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines.extend(text.splitlines())
    return _parse_envelope_lines(lines)


def iter_envelopes_from_bodies(bodies: Any) -> tuple[list[dict[str, Any]], int]:
    """The same, over envelope JSON TEXT coming from the SQLite store's `body`
    column instead of from a `*.jsonl` file (V1-c: canal B is read from
    `events.db`, its spool files are now consumed and deleted)."""
    return _parse_envelope_lines(bodies)


# The attribution census (`dashboard._canal_b_attribution`) reads exactly these
# two first-level envelope fields and nothing else — verified at its only two
# read sites. Keeping the WHOLE envelope alive just to serve them is what made
# the canal-B read cost the entire channel in RAM.
_CENSUS_FIELDS = ("project_id", "project_attributed_by")


def stream_bodies(bodies: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """`(census_envelopes, records, rows_read, malformed)` over envelope JSON
    TEXT, ONE LINE AT A TIME.

    THE SAME TWO STEPS AS `iter_normalized_records_from_bodies`, in the same
    order, through the same `normalize_envelope` mapper — NOT a second
    implementation, which is the doctrine this module states above and which a
    hand-rolled parse in the caller would have broken. Two things change, both
    about lifetime rather than meaning: no line's parsed envelope outlives its
    own iteration, and the envelopes kept for the census are reduced to the two
    fields the census actually reads.

    WHY (T-00000613, measured 2026-09-14): the eager form held THREE full
    materialisations of canal B alive at once — the body strings out of
    SQLite, the parsed envelopes, and the records — for a peak of 4,7 Gio on
    this repo's 545 Mo / 67 854-row channel. An OS kill took a verification
    gate with it, and a gate killed by the OS is indistinguishable from a green
    one unless somebody reads the reason for the stop. Streaming keeps the
    `records` list, which the cumulative aggregates genuinely need in full, and
    drops the other two.

    BLANK LINES ARE SKIPPED WITHOUT BEING COUNTED MALFORMED, and `rows_read`
    counts every row OFFERED including those — `_parse_envelope_lines`'s two
    tolerances, preserved deliberately so the `partial` flag and the
    `rows_read` figure keep meaning exactly what they meant before."""
    census: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    rows_read = 0
    malformed = 0
    for line in bodies:
        rows_read += 1
        if not isinstance(line, str) or not line.strip():
            continue
        try:
            envelope = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            malformed += 1
            continue
        if not isinstance(envelope, dict):
            malformed += 1
            continue
        census.append({field: envelope.get(field) for field in _CENSUS_FIELDS})
        records.extend(normalize_envelope(envelope))
    return census, records, rows_read, malformed


def iter_normalized_records(otel_dir: Path) -> tuple[list[dict[str, Any]], int]:
    """`(records, malformed_lines_skipped)` for the FILE source. Composed from
    `iter_envelopes` + `normalize_envelopes` so there is exactly ONE reader per
    source and ONE normaliser."""
    envelopes, malformed = iter_envelopes(otel_dir)
    return normalize_envelopes(envelopes), malformed


def iter_normalized_records_from_bodies(bodies: Any) -> tuple[list[dict[str, Any]], int]:
    """The SAME normalisation, over the store's bodies.

    A VARIANT OF THE MAPPERS, NEVER A SECOND IMPLEMENTATION (iteration 5, C5 —
    "pas de second chemin plus faible"). Only the SOURCE of the lines differs;
    both compose the same two functions, so a schema family, a `project_id` or a
    redaction rule can never mean one thing on the store path and another on the
    file path."""
    envelopes, malformed = iter_envelopes_from_bodies(bodies)
    return normalize_envelopes(envelopes), malformed


# ---------------------------------------------------------------------------
# Non-negotiable #7 - Codex metrics are absent, not empty.
# ---------------------------------------------------------------------------

# VERIFIED against docs/tasks/T-00000017.md §8 (GO/NO-GO matrix), not
# inferred from data - Codex/Gemini/Copilot have ZERO real captured records
# in this repo (GATE A only captured Claude Code). Extending this table to
# a 5th host is a one-line change, on purpose - it is the single place this
# module's cost view consults host coverage.
HOST_METRICS_COVERAGE: dict[str, str] = {
    "claude-code": "collected",
    "codex": "not_emitted_by_design",
    "gemini": "unknown",
    "copilot": "unknown",
}

_CODEX_COST_REASON = (
    "openai/codex#12913: Codex's metrics exporter defaults to statsig, not "
    "OTLP - `codex exec` emits no OTel metrics at all (logs/events only, "
    "per docs/tasks/T-00000017.md sec.8). Absence by design, not a $0 cost."
)


def cost_summary_for_host(host: str, normalized_metric_records: list[dict[str, Any]]) -> dict[str, Any]:
    """A cost VIEW must never render a bare `$0` for a host with no
    `claude_code.cost.usage` records - that is indistinguishable from "ran
    and cost nothing" (the L-010 false-GO shape, here inside a cost view).
    Three distinguishable statuses: `not_emitted_by_design` (Codex, a
    documented fact) / `no_data_yet` (no record observed for this host,
    but its metrics ARE expected to arrive eventually) / `collected` (a
    real total, summed from `value` on every `claude_code.cost.usage`
    record for this host)."""
    coverage = HOST_METRICS_COVERAGE.get(host, "unknown")
    if coverage == "not_emitted_by_design":
        return {
            "host": host, "status": "not_emitted_by_design",
            "cost_usd": None, "reason": _CODEX_COST_REASON,
        }
    cost_records = [
        r for r in normalized_metric_records
        if r.get("host") == host and r.get("schema_family") == "claude_code.cost.usage"
    ]
    if not cost_records:
        return {
            "host": host, "status": "no_data_yet", "cost_usd": None,
            "reason": "no claude_code.cost.usage record observed yet for this host - absence, not a zero",
        }
    total = sum(r.get("value") or 0 for r in cost_records)
    return {"host": host, "status": "collected", "cost_usd": total, "reason": None}


_CODEX_TOKEN_REASON = (
    "openai/codex#12913: Codex's metrics exporter defaults to statsig, not "
    "OTLP - `codex exec` emits no OTel metrics at all (logs/events only, "
    "per docs/tasks/T-00000017.md sec.8). No `claude_code.token.usage` "
    "dataPoint can exist for this host: absence by design, not a 0-token "
    "matrix."
)

_NO_TOKEN_DATA_REASON = (
    "no claude_code.token.usage record observed yet for this host - absence, "
    "not a zero matrix"
)


def token_matrix_for_host(host: str, normalized_metric_records: list[dict[str, Any]]) -> dict[str, Any]:
    """`{model: {token_type: tokens}}` for ONE host - the joint dimension a
    tokens x rate estimate needs (T-00000077), which neither `tokens_by_type`
    nor `by_model` can supply alone: a published rate is per (model, token
    type), and two marginals never reconstruct the joint distribution they
    were projected from.

    SAME THREE STATUSES AS `cost_summary_for_host`, READ FROM THE SAME SOURCE
    (`HOST_METRICS_COVERAGE`): `not_emitted_by_design` / `no_data_yet` /
    `collected`. AN EMPTY MATRIX IS NEVER RENDERED AS "0 tokens" - that is the
    exact L-010 false-GO shape non-negotiable #7 names for the cost view,
    here on the token side. `by_model_type` is therefore `None` for both
    absent statuses and a dict ONLY when `collected`; a caller that renders
    `by_model_type or {}` has reintroduced the defect.

    INPUT CONTRACT - THE CALLER OWNS ATTRIBUTION, THIS FUNCTION OWNS THE HOST
    FILTER. Pass the SAME attribution-filtered records the dashboard
    aggregates: `dashboard.py:1291` drops every `foreign_held` record BEFORE
    aggregating, and this function deliberately does not repeat that (it takes
    no `own_project_id` and must not grow one - two places deciding what
    belongs to this project is how they diverge). Filtering here by host alone
    is what makes the marginals reconcile with `tokens_by_type`/`by_model`;
    hand it UNFILTERED records and it will count a neighbouring project's
    tokens.

    BUCKETING MIRRORS `dashboard.py:1306` (type) AND `:1327` (model) EXACTLY -
    `str(<field> or "unspecified")` over `fields`, `int(value or 0)` - so the
    per-type marginal equals `tokens_by_type` and the per-model marginal
    equals `by_model`'s token totals, row for row. A record carrying neither
    `model` nor `type` is bucketed `"unspecified"`, NEVER dropped: totals are
    conserved, an unattributable token stays counted and stays visible.
    Consequence of mirroring rather than improving: a value the redactor
    replaced with a dict becomes its `str()` as a key, same as the dashboard
    does today - documented, not fixed here.

    `claude_code.cost.usage` RECORDS ARE IGNORED. They structurally carry no
    `type` (0/14 measured, pinned by
    `test_gate_a_fixture_cost_usage_never_carries_type_token_usage_always_does`
    - a cost dataPoint is one dollar total per request, not a per-token-type
    figure), so admitting them would pile every dollar into a single
    `unspecified` column of a matrix whose unit is tokens.

    DOUBLE COUNT (`dashboard.py`'s `_CANAL_B_DOUBLE_COUNT_NOTE`, same shape on
    the token side): this matrix sums THE METRIC ALONE. It is never added to
    the token figures carried by `api_request` logs - those are a SECOND VIEW
    of the same consumption, not a second consumption."""
    coverage = HOST_METRICS_COVERAGE.get(host, "unknown")
    if coverage == "not_emitted_by_design":
        return {
            "host": host, "status": "not_emitted_by_design",
            "by_model_type": None, "reason": _CODEX_TOKEN_REASON,
        }
    token_records = [
        r for r in normalized_metric_records
        if r.get("host") == host and r.get("schema_family") == "claude_code.token.usage"
    ]
    if not token_records:
        return {
            "host": host, "status": "no_data_yet",
            "by_model_type": None, "reason": _NO_TOKEN_DATA_REASON,
        }
    by_model_type: dict[str, dict[str, int]] = {}
    for record in token_records:
        fields = record.get("fields") or {}
        model = str(fields.get("model") or "unspecified")
        token_type = str(fields.get("type") or "unspecified")
        row = by_model_type.setdefault(model, {})
        row[token_type] = row.get(token_type, 0) + int(record.get("value") or 0)
    return {"host": host, "status": "collected", "by_model_type": by_model_type, "reason": None}


# T-00000073 - the 5 canal-B metrics summed into a net-new `metric_totals`
# payload field (display is the separate T-00000186). Membership is by EXACT
# metric name (mirrors the `name in _METRIC_FAMILIES` test at
# `normalize_metric_record`), NOT a prefix match: `pull_request.count` is
# deliberately absent (verified: no such dataPoint emitted). The 2 DIMENSIONED
# names also live in `_METRIC_FAMILIES` (their attributes reach `fields`); the 3
# SCALARS do not and carry an empty `fields` - both are summed here by
# `metric_name`, which every metric record carries.
_METRIC_TOTAL_NAMES: tuple[str, ...] = (
    "claude_code.session.count",
    "claude_code.active_time.total",
    "claude_code.lines_of_code.count",
    "claude_code.commit.count",
    "claude_code.code_edit_tool.decision",
)

_CODEX_METRIC_TOTALS_REASON = (
    "openai/codex#12913: Codex's metrics exporter defaults to statsig, not "
    "OTLP - `codex exec` emits no OTel metrics at all (logs/events only, per "
    "docs/tasks/T-00000017.md sec.8). None of the 5 canal-B count metrics can "
    "exist for this host: absence by design, not a set of 0 totals."
)

_NO_METRIC_TOTALS_REASON = (
    "no canal-B count metric observed yet for this host - absence, not a set "
    "of zero totals"
)


def metric_totals_for_host(host: str, normalized_metric_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the 5 canal-B COUNT metrics (`_METRIC_TOTAL_NAMES`) into per-metric
    totals for ONE host (T-00000073; display is the separate T-00000186).

    SAME THREE STATUSES AS `cost_summary_for_host`/`token_matrix_for_host`, read
    from the SAME source (`HOST_METRICS_COVERAGE`): `not_emitted_by_design` /
    `no_data_yet` / `collected`. `totals` is `None` for BOTH absent statuses -
    never a dict of bare zeros, which is the exact L-010 false-GO shape (a host
    that emitted nothing made indistinguishable from a host that counted zero).

    INPUT CONTRACT - THE CALLER OWNS ATTRIBUTION, THIS FUNCTION OWNS THE HOST
    FILTER (identical to `token_matrix_for_host`). Pass the same
    attribution-filtered records the dashboard aggregates (`dashboard.py:1291`
    drops `foreign_held` BEFORE aggregating); this function takes no
    `own_project_id` and filters by `host` alone. Hand it unfiltered records and
    it will count a neighbouring project's metrics.

    WHEN `collected`, `totals` is a dict keyed by ALL 5 full metric names:
      - `None` for a metric with ZERO records for this host - per-metric absence
        is not zero, same discipline as the host-level statuses one level up.
      - else `{"total": <sum of value>, "records": <n>}`, and for the 2
        DIMENSIONED metrics an extra breakdown: `by_type` for
        `lines_of_code.count` (bucketed `str(fields.get("type") or
        "unspecified")`) and `by_decision` for `code_edit_tool.decision`
        (keyed on `decision`), mirroring `token_matrix_for_host`'s bucketing -
        a record missing the field lands in `"unspecified"`, never dropped.

    VALUE=None SEMANTICS (C10): `sum(r.get("value") or 0 ...)` COERCES a present
    record whose `value` is None to 0, exactly as `cost_summary_for_host` does
    (:452). So a present-but-valueless dataPoint STILL COUNTS toward `records`
    (it is a real emission) but adds 0 to `total`. Absence of the record and a
    record with value=None are therefore distinct: the first drops the metric to
    `None`, the second keeps `records >= 1` with `total` unmoved.

    DELTA-TEMPORALITY ASSUMPTION (C5): summing dataPoints IS the period total
    because these are delta-temporality (aggregationTemporality=1), the same
    fact measured for `claude_code.cost.usage` and noted at
    dashboard.py:1333-1336. Normalisation drops temporality, so for the 3
    metrics absent from the Gate A fixture (session.count, active_time.total,
    commit.count) this is ASSUMED, not measured; should any arrive as cumulative
    the sum would over-count and this is the line that says where to look."""
    coverage = HOST_METRICS_COVERAGE.get(host, "unknown")
    if coverage == "not_emitted_by_design":
        return {
            "host": host, "status": "not_emitted_by_design",
            "totals": None, "reason": _CODEX_METRIC_TOTALS_REASON,
        }
    host_records = [
        r for r in normalized_metric_records
        if r.get("host") == host and r.get("metric_name") in _METRIC_TOTAL_NAMES
    ]
    if not host_records:
        return {
            "host": host, "status": "no_data_yet",
            "totals": None, "reason": _NO_METRIC_TOTALS_REASON,
        }
    totals: dict[str, Any] = {}
    for name in _METRIC_TOTAL_NAMES:
        records = [r for r in host_records if r.get("metric_name") == name]
        if not records:
            totals[name] = None  # per-metric absence != 0
            continue
        entry: dict[str, Any] = {
            "total": sum(r.get("value") or 0 for r in records),
            "records": len(records),
        }
        if name == "claude_code.lines_of_code.count":
            by_type: dict[str, Any] = {}
            for r in records:
                key = str((r.get("fields") or {}).get("type") or "unspecified")
                by_type[key] = by_type.get(key, 0) + (r.get("value") or 0)
            entry["by_type"] = by_type
        elif name == "claude_code.code_edit_tool.decision":
            by_decision: dict[str, Any] = {}
            for r in records:
                key = str((r.get("fields") or {}).get("decision") or "unspecified")
                by_decision[key] = by_decision.get(key, 0) + (r.get("value") or 0)
            entry["by_decision"] = by_decision
        totals[name] = entry
    return {"host": host, "status": "collected", "totals": totals, "reason": None}


# ---------------------------------------------------------------------------
# Host-generic file catch-up (non-negotiable #6) - Gemini implemented and
# tested, Copilot registered but not implemented (see module docstring).
# ---------------------------------------------------------------------------

def _parse_gemini_line(raw_line: bytes) -> dict[str, Any] | None:
    """Best-effort parse of ONE line from a Gemini file export.
    FORMAT UNOBSERVED (module docstring) - written against the OTLP/JSON
    shape Gemini documents for its HTTP/gRPC target, on the unconfirmed
    assumption the file target serialises one such envelope per line.
    Returns None (never raises) for anything that is not a JSON object -
    the caller counts and skips, this function never guesses past a
    parse failure."""
    try:
        parsed = json.loads(raw_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


PARSER_REGISTRY: dict[str, Callable[[bytes], dict[str, Any] | None] | None] = {
    "gemini": _parse_gemini_line,
    # Registered, deliberately unimplemented: Copilot's primary path is
    # HTTP (GO per docs/tasks/T-00000017.md sec.8); its file format, if any,
    # is unobserved - a tested parser here would be a guess about a guess.
    "copilot": None,
}


_CATCHUP_DIAGNOSTICS: dict[str, int] = {
    "files_scanned": 0,
    "lines_ingested": 0,
    "lines_skipped_malformed": 0,
    "files_unreadable": 0,
}


def get_catchup_diagnostics() -> dict[str, int]:
    return dict(_CATCHUP_DIAGNOSTICS)


def _reset_catchup_diagnostics_for_tests() -> None:
    """Test-only helper, mirroring `otel_receiver._reset_state_for_tests` -
    never called from a production code path in this module."""
    for key in _CATCHUP_DIAGNOSTICS:
        _CATCHUP_DIAGNOSTICS[key] = 0


def _source_dir_env_var(host: str) -> str:
    return f"AGENTS_OTEL_{host.upper()}_FILE_DIR"


def _default_source_dir(host: str) -> Path | None:
    """No BUILT-IN default directory - an operator must opt in by setting
    `AGENTS_OTEL_<HOST>_FILE_DIR` (this is a human-wired activation step,
    same as Gemini's telemetry config itself per L-00000039/T-00000017 sec.4.2
    - the guard on `.gemini/settings.json` already makes that a human
    action, not an agent one)."""
    override = os.environ.get(_source_dir_env_var(host))
    return Path(override) if override else None


def _cursor_path() -> Path:
    return _otel_receiver._otel_dir() / ".catchup-cursor.json"


def _load_cursor() -> dict[str, dict[str, int]]:
    path = _cursor_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cursor(cursor: dict[str, dict[str, int]]) -> None:
    path = _cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Windows: explicit newline="\n" (non-negotiable #8, precedent
    # tasks.py:171 / otel_receiver.py's own writes) - never the platform
    # default that would translate this into CRLF.
    path.write_text(json.dumps(cursor, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _read_new_lines(path: Path, start_offset: int) -> tuple[list[bytes], int]:
    """Same reasoning as `dashboard.py`'s `_read_new_records` (byte offset,
    only ever parse up to the rightmost trailing `b"\\n"` - a line without
    its newline yet is a write in flight, left alone) - duplicated rather
    than imported, for the same reason `otel_receiver.py` already gives for
    duplicating `_drain_request_body`: this module's only import is
    `otel_receiver.py` (module docstring), and `dashboard.py` is out of
    scope for this shard."""
    try:
        with open(path, "rb") as fh:
            fh.seek(start_offset)
            chunk = fh.read()
    except OSError:
        return [], start_offset
    if not chunk:
        return [], start_offset
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        return [], start_offset  # partial trailing line - leave it alone
    consumable = chunk[: last_nl + 1]
    lines = [ln for ln in consumable.split(b"\n")[:-1] if ln.strip()]
    return lines, start_offset + last_nl + 1


def catch_up_host_files(host: str, source_dir: Path | None = None) -> dict[str, Any]:
    """Scan `source_dir` (or the host's `AGENTS_OTEL_<HOST>_FILE_DIR`
    override) for `*.jsonl`/`*.log` files, parse each NEW line (per-file
    byte-offset cursor, persisted alongside the canal-B day-files - a
    second catch-up call never re-ingests a line already ingested) with the
    host's registered parser, and ingest every successfully-parsed line
    through `otel_receiver._ingest_parsed_body` - the SAME redact+persist
    pipeline the HTTP path uses (non-negotiable #1). NEVER raises: no
    parser registered, no directory configured, an absent directory, an
    unreadable file, or a parser returning None for every line all degrade
    to a `status` field, never an exception - a daemon calling this must
    keep running regardless of what a host's file export looks like."""
    parser = PARSER_REGISTRY.get(host)
    if parser is None:
        return {"status": "no_parser_registered", "host": host}

    target_dir = source_dir if source_dir is not None else _default_source_dir(host)
    if target_dir is None:
        return {"status": "not_configured", "host": host}
    if not target_dir.exists():
        return {"status": "source_dir_absent", "host": host, "path": str(target_dir)}

    cursor = _load_cursor()
    host_offsets = dict(cursor.get(host, {}))

    files = sorted(list(target_dir.glob("*.jsonl")) + list(target_dir.glob("*.log")))
    total_lines = 0
    ingested = 0
    skipped = 0
    for path in files:
        _CATCHUP_DIAGNOSTICS["files_scanned"] += 1
        start_offset = host_offsets.get(path.name, 0)
        lines, new_offset = _read_new_lines(path, start_offset)
        if new_offset == start_offset and not path.exists():
            _CATCHUP_DIAGNOSTICS["files_unreadable"] += 1
            continue
        host_offsets[path.name] = new_offset
        for raw_line in lines:
            total_lines += 1
            parsed = parser(raw_line)
            if parsed is None:
                skipped += 1
                _CATCHUP_DIAGNOSTICS["lines_skipped_malformed"] += 1
                continue
            # ATTRIBUTED BY CONSTRUCTION, and it WRITES the id (iteration 5,
            # C2). The `outfile` this line came from lives inside this repo,
            # so "this project" is a fact about where the file is, not a guess
            # about who emitted it. Short-circuiting only the drop would have
            # parked every Gemini record in `unattributed` for ever while
            # `HOST_METRICS_COVERAGE` declared the host attributable.
            _otel_receiver._ingest_parsed_body(
                f"{host}_file", str(path), parsed, attributed_by_construction=True)
            ingested += 1
            _CATCHUP_DIAGNOSTICS["lines_ingested"] += 1

    cursor[host] = host_offsets
    _save_cursor(cursor)

    status = "ok"
    if not files:
        status = "no_files_found"
    elif total_lines and ingested == 0:
        # Every line this call attempted failed to parse - a DEGRADED
        # signal, not a silent zero-ingested (non-negotiable #6).
        status = "degraded_no_lines_parsed"


    return {
        "status": status,
        "host": host,
        "path": str(target_dir),
        "files_scanned": len(files),
        "lines_total": total_lines,
        "lines_ingested": ingested,
        "lines_skipped": skipped,
    }
