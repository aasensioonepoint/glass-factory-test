"""Tests for otel_normalize.py — canal-B normalisation + host-generic file
catch-up (T-00000025 shard 3).

FIXTURES: `otel_gate_a_fixture.jsonl` (colocated, TRACKED — unlike
`state/local/otel/`, which is git-ignored and cannot be a CI fixture) is a
byte-for-byte subset of the 49 real Claude Code records captured for GATE A
on 2026-07-27: one real envelope per distinct metric name and log
`event.name` observed, selected programmatically from the two real
`state/local/otel/*.jsonl` files, never hand-invented. Gemini/Copilot file
catch-up tests use SYNTHETIC lines instead — there is no real captured
Gemini/Copilot record anywhere (GATE A only captured Claude Code) — and are
labelled as such throughout; see `test_catch_up_host_files_gemini_*` below
and the report for what would need to happen to replace them with real
fixtures.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import sys

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("otel_normalize", HERE / "otel_normalize.py")
otel_normalize = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = otel_normalize
_spec.loader.exec_module(otel_normalize)

_otel_receiver = otel_normalize._otel_receiver  # the SAME module instance normalize uses internally

GATE_A_FIXTURE = HERE / "otel_gate_a_fixture.jsonl"


_OWN_ID = "own-project-id-0001"


@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    otel_dir = tmp_path / "otel"
    monkeypatch.setenv("AGENTS_OTEL_DIR", str(otel_dir))
    monkeypatch.setenv("AGENTS_OTEL_PROJECT_ROOT", str(tmp_path / "fake-project"))
    monkeypatch.setenv("AGENTS_PROJECT_JSON", str(tmp_path / "project.json"))
    (tmp_path / "project.json").write_text(json.dumps({"project_id": _OWN_ID}),
                                           encoding="utf-8", newline="\n")
    _otel_receiver._reset_state_for_tests()
    otel_normalize._reset_catchup_diagnostics_for_tests()
    yield otel_dir


def _attr(key: str, string_value: str) -> dict:
    return {"key": key, "value": {"stringValue": string_value}}


# ---------------------------------------------------------------------------
# Normalisation against the REAL GATE A fixture.
# ---------------------------------------------------------------------------

def test_gate_a_fixture_normalises_every_known_family(_redirect):
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    (otel_dir / "fixture.1234.jsonl").write_bytes(GATE_A_FIXTURE.read_bytes())

    records, malformed = otel_normalize.iter_normalized_records(otel_dir)
    assert malformed == 0

    families = {r["schema_family"] for r in records if r.get("schema_family")}
    # T-00000073 leaves this equality UNCHANGED on purpose: the 2 metrics it
    # promotes into `_METRIC_FAMILIES` (`lines_of_code.count`,
    # `code_edit_tool.decision`) are BOTH absent from the Gate A fixture (only
    # session.count / active_time.total / cost.usage / token.usage appear), so
    # neither can show up as a schema_family here. Their promotion is proven by
    # the synthetic-envelope tests below, not against this real fixture — and the
    # fixture is deliberately NOT touched.
    assert families == {
        "claude_code.cost.usage", "claude_code.token.usage",
        "api_request", "subagent_completed", "tool_decision",
    }

    event_names = {r["event_name"] for r in records if r.get("kind") == "log"}
    # Events with no declared schema family (hook_registered, plugin_loaded,
    # user_prompt, ...) still normalise - schema_family is None, never
    # dropped from the output (drift is flagged, not silently resolved).
    assert "hook_registered" in event_names
    assert "user_prompt" in event_names


def test_gate_a_fixture_cost_usage_never_carries_type_token_usage_always_does(_redirect):
    """The measured schema drift (module docstring): dashboard.py's frozen
    schema lists `type` for BOTH families; real data only ever carries it
    on token.usage."""
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    (otel_dir / "fixture.1234.jsonl").write_bytes(GATE_A_FIXTURE.read_bytes())
    records, _ = otel_normalize.iter_normalized_records(otel_dir)

    cost_records = [r for r in records if r["schema_family"] == "claude_code.cost.usage"]
    token_records = [r for r in records if r["schema_family"] == "claude_code.token.usage"]
    assert cost_records and token_records
    assert all("type" not in r["fields"] for r in cost_records)
    assert all("type" in r["fields"] for r in token_records)


def test_gate_a_fixture_prompt_id_present_on_per_turn_events_absent_on_lifecycle_events(_redirect):
    """The measured drift against "prompt.id is on EVERY log record"
    (module docstring): present on api_request, absent on hook_registered /
    plugin_loaded in this fixture, matching the full-corpus measurement."""
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    (otel_dir / "fixture.1234.jsonl").write_bytes(GATE_A_FIXTURE.read_bytes())
    records, _ = otel_normalize.iter_normalized_records(otel_dir)

    by_event = {r["event_name"]: r for r in records if r.get("kind") == "log"}
    assert by_event["api_request"]["prompt_id"] is not None
    assert by_event["tool_decision"]["prompt_id"] is not None
    assert by_event["hook_registered"]["prompt_id"] is None
    assert by_event["plugin_loaded"]["prompt_id"] is None


def test_gate_a_fixture_cost_summary_is_collected_with_real_dollar_total(_redirect):
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    (otel_dir / "fixture.1234.jsonl").write_bytes(GATE_A_FIXTURE.read_bytes())
    records, _ = otel_normalize.iter_normalized_records(otel_dir)

    cost_records = [r for r in records if r["schema_family"] == "claude_code.cost.usage"]
    expected_total = sum(r["value"] for r in cost_records)
    assert expected_total > 0  # the fixture's one real cost.usage dataPoint is non-zero

    summary = otel_normalize.cost_summary_for_host("claude-code", records)
    assert summary == {"host": "claude-code", "status": "collected", "cost_usd": expected_total, "reason": None}


# ---------------------------------------------------------------------------
# Malformed-line tolerance (never raise past a mid-flush write).
# ---------------------------------------------------------------------------

def test_malformed_line_is_skipped_and_counted_not_raised(_redirect):
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    good = json.dumps({
        "ts": "2026-01-01T00:00:00Z", "kind": "log", "path": "/v1/logs",
        "provenance": "p", "body": {"resourceLogs": []},
    })
    (otel_dir / "day.111.jsonl").write_text(good + "\nthis is not json\n", encoding="utf-8", newline="\n")

    records, malformed = otel_normalize.iter_normalized_records(otel_dir)
    assert malformed == 1
    assert records == []  # the one good line has an empty resourceLogs - nothing to normalise, not an error


def test_empty_otel_dir_normalises_to_nothing(_redirect):
    otel_dir = _redirect
    records, malformed = otel_normalize.iter_normalized_records(otel_dir)
    assert records == []
    assert malformed == 0


# ---------------------------------------------------------------------------
# V1-c — project_id reaches the RECORD, through BOTH mappers (T-00000050)
# ---------------------------------------------------------------------------

def _metric_body() -> dict:
    return {"resourceMetrics": [{
        "resource": {"attributes": [_attr("service.name", "claude-code")]},
        "scopeMetrics": [{"metrics": [{
            "name": "claude_code.cost.usage",
            "sum": {"dataPoints": [{"attributes": [], "asDouble": 1.5}]},
        }]}],
    }]}


def _log_body() -> dict:
    return {"resourceLogs": [{
        "resource": {"attributes": [_attr("service.name", "claude-code")]},
        "scopeLogs": [{"logRecords": [{"attributes": [_attr("event.name", "api_request")]}]}],
    }]}


@pytest.mark.parametrize("kind,body", [("metric", _metric_body()), ("log", _log_body())])
def test_the_sentinel_crosses_both_mappers(kind, body):
    """Iteration 4, C1 — the defect this closes. Before V1-c the two mappers
    copied `{ts, host, provenance, source, ...}` and NOT the promoted field, so
    `project_id` never reached the normalised record: the census and the
    watertight totals fell back on `provenance`, i.e. on an absolute path for
    every pre-V1-c line — exactly the ambiguity the promotion had just removed.

    Both mappers, one parametrised test, because "we fixed the metric mapper"
    is how the log mapper stays broken."""
    envelope = {"ts": "2026-01-01T00:00:00Z", "kind": kind, "path": "/v1/x",
                "project_id": "unattributed", "provenance": "unattributed",
                "body": body}
    records = otel_normalize.normalize_envelope(envelope)
    assert records, f"the {kind} mapper produced nothing to check"
    for record in records:
        assert record["project_id"] == "unattributed"
        assert record["project_attributed_by"] is None
        assert record["provenance"] == "unattributed"


@pytest.mark.parametrize("kind,body", [("metric", _metric_body()), ("log", _log_body())])
def test_backfill_marker_crosses_both_mappers(kind, body):
    """`project_attributed_by` carries the QUALITY OF THE PROOF per row
    (iteration 9, C3): a row attributed by INFERENCE must stay countable apart
    from one attributed by DECLARATION, all the way to the display."""
    envelope = {"ts": "2026-01-01T00:00:00Z", "kind": kind, "path": "/v1/x",
                "project_id": _OWN_ID, "project_attributed_by": "backfill",
                "provenance": r"C:\some\root", "body": body}
    for record in otel_normalize.normalize_envelope(envelope):
        assert record["project_id"] == _OWN_ID
        assert record["project_attributed_by"] == "backfill"


def test_store_variant_is_the_same_mappers_not_a_second_implementation(_redirect):
    """Iteration 5, C5 (non-negotiable "no second, weaker path"). The store
    reader and the file reader must produce IDENTICAL records for identical
    lines — asserted by equality, which is the only form of this claim that
    cannot rot."""
    otel_dir = _redirect
    otel_dir.mkdir(parents=True, exist_ok=True)
    envelopes = [
        {"ts": "2026-01-01T00:00:00Z", "kind": "metric", "path": "/v1/metrics",
         "project_id": _OWN_ID, "provenance": _OWN_ID, "body": _metric_body()},
        {"ts": "2026-01-01T00:00:01Z", "kind": "log", "path": "/v1/logs",
         "project_id": "unattributed", "provenance": "unattributed", "body": _log_body()},
    ]
    bodies = [json.dumps(e) for e in envelopes]
    (otel_dir / "day.1.jsonl").write_text("\n".join(bodies) + "\n",
                                          encoding="utf-8", newline="\n")

    from_files, malformed_files = otel_normalize.iter_normalized_records(otel_dir)
    from_store, malformed_store = otel_normalize.iter_normalized_records_from_bodies(bodies)
    assert from_store == from_files
    assert malformed_store == malformed_files == 0


def test_store_variant_counts_a_malformed_body_and_never_raises(_redirect):
    records, malformed = otel_normalize.iter_normalized_records_from_bodies(
        ["not json at all", json.dumps([1, 2, 3]), "   ", None])
    assert records == []
    assert malformed == 2, "a non-object and a non-JSON body are counted, blanks are not"


# ---------------------------------------------------------------------------
# Non-negotiable #7 - Codex metrics are absent, not empty.
# ---------------------------------------------------------------------------

def test_cost_summary_codex_is_not_emitted_by_design_never_a_bare_zero():
    summary = otel_normalize.cost_summary_for_host("codex", [])
    assert summary["status"] == "not_emitted_by_design"
    assert summary["cost_usd"] is None
    assert "openai/codex#12913" in summary["reason"]


def test_cost_summary_unknown_host_with_no_records_is_no_data_yet_not_zero():
    summary = otel_normalize.cost_summary_for_host("gemini", [])
    assert summary["status"] == "no_data_yet"
    assert summary["cost_usd"] is None


def test_cost_summary_distinguishes_absence_from_zero_cost():
    """The exact false-GO shape this non-negotiable calls out: a host that
    DID emit a cost.usage record whose value happens to be 0.0 must show
    `collected` / `$0.0`, never be confused with `no_data_yet`."""
    zero_cost_record = {"host": "claude-code", "schema_family": "claude_code.cost.usage", "value": 0.0}
    summary = otel_normalize.cost_summary_for_host("claude-code", [zero_cost_record])
    assert summary["status"] == "collected"
    assert summary["cost_usd"] == 0.0
    no_record_summary = otel_normalize.cost_summary_for_host("claude-code", [])
    assert no_record_summary["status"] == "no_data_yet"
    assert no_record_summary["cost_usd"] is None
    assert summary["cost_usd"] != no_record_summary["cost_usd"] or summary["status"] != no_record_summary["status"]


# ---------------------------------------------------------------------------
# token_matrix_for_host (T-00000077) — the model x type joint, same
# three-status discipline as cost_summary_for_host, marginals reconciled
# against the REAL fixture. The expected values here re-implement the
# bucketing rather than importing dashboard.py (accepted drift, critic C3:
# T-00000073 is editing that file in parallel).
# ---------------------------------------------------------------------------

def _fixture_records(otel_dir):
    otel_dir.mkdir(parents=True, exist_ok=True)
    (otel_dir / "fixture.1234.jsonl").write_bytes(GATE_A_FIXTURE.read_bytes())
    records, malformed = otel_normalize.iter_normalized_records(otel_dir)
    assert malformed == 0
    return records


def test_gate_a_fixture_token_usage_always_carries_model(_redirect):
    """Critic C1 — `model` was allow-listed but never MEASURED the way `type`
    was (56/56 in the module docstring). This is the symmetric assertion on
    the real records: if a fixture refresh ever ships a token.usage dataPoint
    without `model`, the matrix silently grows an `unspecified` row and this
    test is what says so."""
    records = _fixture_records(_redirect)
    token_records = [r for r in records if r["schema_family"] == "claude_code.token.usage"]
    assert token_records
    assert all("model" in r["fields"] for r in token_records)


def test_gate_a_fixture_token_matrix_marginals_reconcile_and_cost_dollars_stay_out(_redirect):
    """Both marginals of the joint must equal the sums the dashboard's flat
    views (`tokens_by_type` / `by_model`) would compute from the same records
    — same buckets, same totals. And the fixture's cost.usage dollars must be
    nowhere in a matrix whose unit is tokens."""
    records = _fixture_records(_redirect)
    token_records = [r for r in records if r["schema_family"] == "claude_code.token.usage"]

    expected_by_type: dict[str, int] = {}
    expected_by_model: dict[str, int] = {}
    for r in token_records:
        fields = r["fields"]
        value = int(r["value"] or 0)
        expected_by_type[str(fields.get("type") or "unspecified")] = (
            expected_by_type.get(str(fields.get("type") or "unspecified"), 0) + value)
        expected_by_model[str(fields.get("model") or "unspecified")] = (
            expected_by_model.get(str(fields.get("model") or "unspecified"), 0) + value)
    assert sum(expected_by_type.values()) > 0  # non-vacuous: real dataPoints

    matrix = otel_normalize.token_matrix_for_host("claude-code", records)
    assert matrix["status"] == "collected"
    assert matrix["reason"] is None
    by_model_type = matrix["by_model_type"]

    marginal_by_model = {m: sum(row.values()) for m, row in by_model_type.items()}
    marginal_by_type: dict[str, int] = {}
    for row in by_model_type.values():
        for token_type, tokens in row.items():
            marginal_by_type[token_type] = marginal_by_type.get(token_type, 0) + tokens
    assert marginal_by_model == expected_by_model
    assert marginal_by_type == expected_by_type
    # Totals conserved, and token-only: the fixture's cost.usage values are
    # dollars — had they leaked in, the grand total would no longer equal the
    # token records' own sum.
    assert sum(marginal_by_model.values()) == sum(int(r["value"] or 0) for r in token_records)


def test_token_matrix_codex_is_not_emitted_by_design_never_a_zero_matrix():
    matrix = otel_normalize.token_matrix_for_host("codex", [])
    assert matrix["status"] == "not_emitted_by_design"
    assert matrix["by_model_type"] is None
    assert "openai/codex#12913" in matrix["reason"]


def test_token_matrix_unknown_host_with_no_records_is_no_data_yet_not_zero():
    matrix = otel_normalize.token_matrix_for_host("gemini", [])
    assert matrix["status"] == "no_data_yet"
    assert matrix["by_model_type"] is None


def test_token_matrix_distinguishes_absence_from_zero_tokens():
    """Non-negotiable #7 on the token side: a host that DID emit a token.usage
    record whose value happens to be 0 shows `collected` with a real 0 cell,
    never `no_data_yet` — and the reverse."""
    zero_token_record = {"host": "claude-code", "schema_family": "claude_code.token.usage",
                         "value": 0, "fields": {"model": "claude-fable-5", "type": "input"}}
    matrix = otel_normalize.token_matrix_for_host("claude-code", [zero_token_record])
    assert matrix["status"] == "collected"
    assert matrix["by_model_type"] == {"claude-fable-5": {"input": 0}}
    absent = otel_normalize.token_matrix_for_host("claude-code", [])
    assert absent["status"] == "no_data_yet"
    assert absent["by_model_type"] is None


def test_token_matrix_filters_by_host_from_a_non_empty_mixed_pool():
    """Critic C2 — the host filter proved on an input where it has something
    to EXCLUDE, not just on a single-host fixture where filtering and not
    filtering are indistinguishable."""
    pool = [
        {"host": "claude-code", "schema_family": "claude_code.token.usage",
         "value": 10, "fields": {"model": "claude-fable-5", "type": "input"}},
        {"host": "gemini", "schema_family": "claude_code.token.usage",
         "value": 7, "fields": {"model": "gemini-3-pro", "type": "input"}},
    ]
    matrix = otel_normalize.token_matrix_for_host("claude-code", pool)
    assert matrix["by_model_type"] == {"claude-fable-5": {"input": 10}}
    gemini_matrix = otel_normalize.token_matrix_for_host("gemini", pool)
    assert gemini_matrix["by_model_type"] == {"gemini-3-pro": {"input": 7}}


def test_token_matrix_buckets_missing_model_and_type_as_unspecified_never_dropped():
    """Totals are conserved: a record carrying neither field stays counted
    under `unspecified`, exactly as dashboard.py buckets its flat views."""
    pool = [
        {"host": "claude-code", "schema_family": "claude_code.token.usage",
         "value": 5, "fields": {}},
        {"host": "claude-code", "schema_family": "claude_code.token.usage",
         "value": 3, "fields": {"model": "claude-fable-5", "type": "output"}},
    ]
    matrix = otel_normalize.token_matrix_for_host("claude-code", pool)
    assert matrix["by_model_type"] == {
        "unspecified": {"unspecified": 5},
        "claude-fable-5": {"output": 3},
    }


def test_token_matrix_ignores_cost_usage_records_even_when_they_are_the_only_ones():
    """cost.usage structurally carries no `type` (0/14 measured): admitting it
    would pile dollars into an `unspecified` token column. A host with ONLY
    cost records has no token data — `no_data_yet`, not a fabricated matrix."""
    cost_only = [{"host": "claude-code", "schema_family": "claude_code.cost.usage",
                  "value": 1.5, "fields": {"model": "claude-fable-5"}}]
    matrix = otel_normalize.token_matrix_for_host("claude-code", cost_only)
    assert matrix["status"] == "no_data_yet"
    assert matrix["by_model_type"] is None


# ---------------------------------------------------------------------------
# metric_totals_for_host (T-00000073) — sum the 5 canal-B count metrics.
# Membership is by EXACT metric name; the 2 dimensioned families also normalise
# with their documented fields. Same three-status discipline as
# cost_summary_for_host / token_matrix_for_host, totals=None on both absent
# statuses (never a bare 0 — the L-010 false-GO shape).
# ---------------------------------------------------------------------------

def _dimensioned_metric_body(name: str, value, attrs: dict, host: str = "claude-code") -> dict:
    return {"resourceMetrics": [{
        "resource": {"attributes": [_attr("service.name", host)]},
        "scopeMetrics": [{"metrics": [{
            "name": name,
            "sum": {"dataPoints": [{
                "attributes": [_attr(k, v) for k, v in attrs.items()],
                "asDouble": value,
            }]},
        }]}],
    }]}


def test_lines_of_code_count_normalises_with_its_type_field():
    """The DIMENSIONED metric is promoted into `_METRIC_FAMILIES`, so its
    `type` attribute reaches `fields` (T-00000073 step 1-2)."""
    envelope = {"ts": "2026-01-01T00:00:00Z", "kind": "metric", "path": "/v1/metrics",
                "project_id": _OWN_ID, "provenance": _OWN_ID,
                "body": _dimensioned_metric_body(
                    "claude_code.lines_of_code.count", 42, {"type": "added"})}
    records = otel_normalize.normalize_envelope(envelope)
    assert len(records) == 1
    rec = records[0]
    assert rec["schema_family"] == "claude_code.lines_of_code.count"
    assert rec["metric_name"] == "claude_code.lines_of_code.count"
    assert rec["value"] == 42
    assert rec["fields"] == {"type": "added"}


def test_code_edit_tool_decision_normalises_with_its_decision_fields():
    envelope = {"ts": "2026-01-01T00:00:00Z", "kind": "metric", "path": "/v1/metrics",
                "project_id": _OWN_ID, "provenance": _OWN_ID,
                "body": _dimensioned_metric_body(
                    "claude_code.code_edit_tool.decision", 3,
                    {"decision": "accept", "tool_name": "Edit", "language": "python"})}
    records = otel_normalize.normalize_envelope(envelope)
    assert len(records) == 1
    rec = records[0]
    assert rec["schema_family"] == "claude_code.code_edit_tool.decision"
    assert rec["fields"] == {"decision": "accept", "tool_name": "Edit", "language": "python"}


def test_metric_totals_codex_is_not_emitted_by_design_never_bare_zeros():
    result = otel_normalize.metric_totals_for_host("codex", [])
    assert result["status"] == "not_emitted_by_design"
    assert result["totals"] is None
    assert "openai/codex#12913" in result["reason"]


def test_metric_totals_unknown_host_with_no_records_is_no_data_yet_not_zero():
    result = otel_normalize.metric_totals_for_host("gemini", [])
    assert result["status"] == "no_data_yet"
    assert result["totals"] is None


def test_metric_totals_collected_sums_the_five_and_absent_metric_is_none_not_zero():
    """A collected host that emitted only SOME of the 5 metrics: the ones seen
    carry a real total, the ones absent are `None` — per-metric absence is not a
    measured zero, the same discipline as the host-level statuses."""
    pool = [
        {"host": "claude-code", "metric_name": "claude_code.session.count",
         "value": 1, "fields": {}},
        {"host": "claude-code", "metric_name": "claude_code.session.count",
         "value": 1, "fields": {}},
        {"host": "claude-code", "metric_name": "claude_code.lines_of_code.count",
         "value": 30, "fields": {"type": "added"}},
        {"host": "claude-code", "metric_name": "claude_code.lines_of_code.count",
         "value": 4, "fields": {"type": "removed"}},
        {"host": "claude-code", "metric_name": "claude_code.code_edit_tool.decision",
         "value": 2, "fields": {"decision": "accept"}},
    ]
    result = otel_normalize.metric_totals_for_host("claude-code", pool)
    assert result["status"] == "collected"
    totals = result["totals"]
    # every one of the 5 names is a KEY, present-or-None
    assert set(totals) == set(otel_normalize._METRIC_TOTAL_NAMES)
    assert totals["claude_code.session.count"] == {"total": 2, "records": 2}
    assert totals["claude_code.lines_of_code.count"] == {
        "total": 34, "records": 2, "by_type": {"added": 30, "removed": 4}}
    assert totals["claude_code.code_edit_tool.decision"] == {
        "total": 2, "records": 1, "by_decision": {"accept": 2}}
    # absent metrics: None, NEVER 0 or an empty dict
    assert totals["claude_code.active_time.total"] is None
    assert totals["claude_code.commit.count"] is None


def test_metric_totals_filters_by_host_from_a_mixed_pool():
    pool = [
        {"host": "claude-code", "metric_name": "claude_code.commit.count",
         "value": 5, "fields": {}},
        {"host": "gemini", "metric_name": "claude_code.commit.count",
         "value": 9, "fields": {}},
    ]
    cc = otel_normalize.metric_totals_for_host("claude-code", pool)
    assert cc["totals"]["claude_code.commit.count"] == {"total": 5, "records": 1}
    gem = otel_normalize.metric_totals_for_host("gemini", pool)
    assert gem["totals"]["claude_code.commit.count"] == {"total": 9, "records": 1}


def test_metric_totals_present_record_with_value_none_counts_but_adds_zero():
    """C10 — `sum(value or 0)` coerces a PRESENT-but-valueless dataPoint to 0.
    It still counts toward `records` (it is a real emission) but moves `total` by
    0; that is distinct from the metric being ABSENT, which yields None."""
    pool = [
        {"host": "claude-code", "metric_name": "claude_code.session.count",
         "value": None, "fields": {}},
        {"host": "claude-code", "metric_name": "claude_code.session.count",
         "value": 3, "fields": {}},
    ]
    result = otel_normalize.metric_totals_for_host("claude-code", pool)
    assert result["totals"]["claude_code.session.count"] == {"total": 3, "records": 2}


def test_metric_totals_delta_sum_over_the_real_fixture(_redirect):
    """Fixture-backed: the Gate A capture carries session.count (=1) and
    active_time.total (=13.611) as delta-temporality dataPoints, so summing them
    IS the period total. The other 3 of the 5 are absent from the fixture and so
    are None — proving per-metric absence on REAL data, not just synthetic."""
    records = _fixture_records(_redirect)
    result = otel_normalize.metric_totals_for_host("claude-code", records)
    assert result["status"] == "collected"
    totals = result["totals"]
    assert totals["claude_code.session.count"] == {"total": 1, "records": 1}
    assert totals["claude_code.active_time.total"] == {"total": 13.611, "records": 1}
    assert totals["claude_code.lines_of_code.count"] is None
    assert totals["claude_code.commit.count"] is None
    assert totals["claude_code.code_edit_tool.decision"] is None


# ---------------------------------------------------------------------------
# Host-generic file catch-up — Gemini implemented + tested (SYNTHETIC
# lines: no real Gemini capture exists anywhere, see module docstring).
# Copilot: registered, no parser, tested only for the no-op path.
# ---------------------------------------------------------------------------

def _gemini_payload(email: str = "leak@example.com") -> dict:
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": [_attr("user.email", email), _attr("service.name", "gemini-cli")]},
                "scopeLogs": [
                    {
                        "scope": {},
                        "logRecords": [{"attributes": [_attr("event.name", "gemini_turn"), _attr("prompt.id", "g-1")]}],
                    }
                ],
            }
        ]
    }


def test_catch_up_host_files_gemini_ingests_via_shared_redact_persist_pipeline(_redirect, tmp_path):
    otel_dir = _redirect
    source_dir = tmp_path / "gemini-source"
    source_dir.mkdir()
    (source_dir / "out.jsonl").write_text(
        json.dumps(_gemini_payload()) + "\nnot valid json at all\n", encoding="utf-8", newline="\n"
    )

    result = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert result["status"] == "ok"
    assert result["files_scanned"] == 1
    assert result["lines_total"] == 2
    assert result["lines_ingested"] == 1
    assert result["lines_skipped"] == 1

    persisted_files = list(otel_dir.glob("*.jsonl"))
    assert len(persisted_files) == 1
    lines = [ln for ln in persisted_files[0].read_text(encoding="utf-8").split("\n") if ln]
    assert len(lines) == 1
    envelope = json.loads(lines[0])
    assert envelope["kind"] == "gemini_file"
    # The SAME redaction pipeline the HTTP path uses (non-negotiable #1) —
    # proof: the planted email is gone, replaced by our marker, not a
    # second/weaker mechanism this module might have invented.
    attrs = {a["key"]: a["value"] for a in envelope["body"]["resourceLogs"][0]["resource"]["attributes"]}
    assert attrs["user.email"] == {"stringValue": "REDACTED"}
    assert "leak@example.com" not in json.dumps(envelope)
    # V1-c: ATTRIBUTED BY CONSTRUCTION, and the id is WRITTEN (iteration 5, C2).
    # The outfile lives inside this repo, so "this project" is a fact about
    # where the file is. Short-circuiting only the drop would have parked every
    # Gemini record in `unattributed` for ever while HOST_METRICS_COVERAGE
    # declared the host attributable — the dashboard contradicting itself about
    # one host.
    assert envelope["project_id"] == _OWN_ID


def test_catch_up_attributes_by_construction_even_after_a_late_project_init(
        _redirect, tmp_path, monkeypatch):
    """The catch-up is where a Gemini session that ran BEFORE `project_init.py`
    gets picked up. The identity is re-resolved rather than frozen, so the
    catch-up attributes those lines instead of sentinelling them for ever."""
    source_dir = tmp_path / "gemini-source"
    source_dir.mkdir()
    (source_dir / "out.jsonl").write_text(json.dumps(_gemini_payload()) + "\n",
                                          encoding="utf-8", newline="\n")
    (tmp_path / "project.json").unlink()
    _otel_receiver._reset_identity_cache_for_tests()
    assert _otel_receiver.resolve_own_project_id() == _otel_receiver.PROJECT_UNSET

    (tmp_path / "project.json").write_text(json.dumps({"project_id": _OWN_ID}),
                                           encoding="utf-8", newline="\n")
    result = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert result["lines_ingested"] == 1
    lines = [ln for ln in (list(_redirect.glob("*.jsonl"))[0]
                           ).read_text(encoding="utf-8").split("\n") if ln]
    assert json.loads(lines[0])["project_id"] == _OWN_ID


def test_catch_up_host_files_gemini_is_idempotent_across_two_calls(_redirect, tmp_path):
    source_dir = tmp_path / "gemini-source"
    source_dir.mkdir()
    (source_dir / "out.jsonl").write_text(json.dumps(_gemini_payload()) + "\n", encoding="utf-8", newline="\n")

    first = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert first["lines_ingested"] == 1

    second = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert second["lines_ingested"] == 0
    assert second["lines_total"] == 0  # the cursor already advanced past this content


def test_catch_up_host_files_gemini_picks_up_appended_lines_after_first_call(_redirect, tmp_path):
    source_dir = tmp_path / "gemini-source"
    source_dir.mkdir()
    path = source_dir / "out.jsonl"
    path.write_text(json.dumps(_gemini_payload("first@example.com")) + "\n", encoding="utf-8", newline="\n")

    first = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert first["lines_ingested"] == 1

    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(_gemini_payload("second@example.com")) + "\n")

    second = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert second["lines_ingested"] == 1  # only the NEW line, not a re-ingest of the first


def test_catch_up_host_files_gemini_degrades_visibly_when_nothing_parses(_redirect, tmp_path):
    """Non-negotiable #6: an unobserved-format assumption that turns out
    wrong must be VISIBLE, not a silent zero-ingested."""
    source_dir = tmp_path / "gemini-source"
    source_dir.mkdir()
    (source_dir / "out.log").write_text("not json\nstill not json\n", encoding="utf-8", newline="\n")

    result = otel_normalize.catch_up_host_files("gemini", source_dir=source_dir)
    assert result["status"] == "degraded_no_lines_parsed"
    assert result["lines_ingested"] == 0
    assert result["lines_skipped"] == 2


def test_catch_up_host_files_gemini_source_dir_absent_degrades_not_raises(_redirect, tmp_path):
    result = otel_normalize.catch_up_host_files("gemini", source_dir=tmp_path / "does-not-exist")
    assert result["status"] == "source_dir_absent"


def test_catch_up_host_files_gemini_not_configured_when_no_env_and_no_arg(_redirect, monkeypatch):
    monkeypatch.delenv("AGENTS_OTEL_GEMINI_FILE_DIR", raising=False)
    result = otel_normalize.catch_up_host_files("gemini")
    assert result["status"] == "not_configured"


def test_catch_up_host_files_copilot_has_registration_slot_but_no_parser(_redirect, tmp_path):
    """Copilot: registered, deliberately unimplemented (module docstring) —
    a directory full of real-looking lines must still be a no-op, never a
    guess."""
    source_dir = tmp_path / "copilot-source"
    source_dir.mkdir()
    (source_dir / "out.jsonl").write_text('{"anything": "here"}\n', encoding="utf-8", newline="\n")

    result = otel_normalize.catch_up_host_files("copilot", source_dir=source_dir)
    assert result["status"] == "no_parser_registered"
    assert otel_normalize.get_catchup_diagnostics()["files_scanned"] == 0


# ---------------------------------------------------------------------------
# redact() sensitivity, exercised via the fingerprint helper directly
# (unit-level, no server) — confirms the fingerprint is a genuine SHA-256
# of the exact bytes, not a placeholder.
# ---------------------------------------------------------------------------

def test_fingerprint_helper_matches_hand_computed_sha256():
    raw = "some content the host actually sent"
    fp = _otel_receiver._fingerprint_attr_value({"stringValue": raw})
    encoded = raw.encode("utf-8")
    assert fp["agentkitFingerprint"]["byteLength"] == len(encoded)
    assert fp["agentkitFingerprint"]["sha256"] == hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# T-00000613 — `stream_bodies`: the same two steps, without the channel in RAM.
#
# The eager pair held the body strings, the parsed envelopes AND the records
# alive at once. Measured on this repo on 2026-09-14: 67 854 rows, 545 Mo of
# body text, a 4,7 Gio peak, and an OS kill that took a verification gate with
# it. These witnesses pin the two things the cheap path must NOT buy that with:
# a different answer, or a quietly re-materialised list.
# ---------------------------------------------------------------------------

_NEIGHBOUR_ID = "neighbour-project-id-0002"


def _canal_b_line(kind: str, project_id: str, attributed_by=None) -> str:
    """One `body` column value, shaped as `otel_receiver.persist()` writes it."""
    return json.dumps({
        "ts": "2026-01-01T00:00:00Z", "kind": kind, "path": "/v1/x",
        "project_id": project_id, "provenance": project_id,
        "project_attributed_by": attributed_by,
        "body": _metric_body() if kind == "metric" else _log_body(),
    })


# Four well-formed rows covering the fields the census reads, then the three
# tolerances that must not drift: invalid JSON, valid JSON that is not an
# object, and blank rows.
_STREAM_CORPUS = [
    _canal_b_line("metric", _OWN_ID),
    _canal_b_line("log", _OWN_ID, attributed_by="backfill"),
    _canal_b_line("metric", _NEIGHBOUR_ID),
    _canal_b_line("log", "unattributed"),
    "{ not json",
    json.dumps([1, 2, 3]),
    "",
    "   ",
]


def test_stream_bodies_produces_the_same_records_as_the_eager_pair():
    """THE EQUIVALENCE that makes this a VARIANT of the mappers and not a
    second normaliser — the distinction this module states about itself. Same
    corpus, same records, same malformed count. Anything else would mean
    canal-B money means one thing on the cheap path and another on the old
    one, which is the failure mode the single-normaliser rule exists for."""
    eager_envelopes, eager_malformed = otel_normalize.iter_envelopes_from_bodies(_STREAM_CORPUS)
    eager_records = otel_normalize.normalize_envelopes(eager_envelopes)

    census, records, rows_read, malformed = otel_normalize.stream_bodies(_STREAM_CORPUS)

    assert records == eager_records
    assert records, "the corpus must actually normalise to something"
    assert malformed == eager_malformed == 2
    assert len(census) == len(eager_envelopes) == 4
    # `rows_read` replaces the `len(bodies)` the payload used to report, so it
    # must count every row OFFERED — blank and malformed ones included.
    assert rows_read == len(_STREAM_CORPUS) == 8


def test_stream_bodies_census_keeps_exactly_the_two_fields_the_census_reads():
    """The slimming is the memory win AND the risk: drop a field the
    attribution census consults and the buckets go wrong SILENTLY. This pins
    the contract to the two first-level fields `dashboard._attribution_bucket`
    and its `backfill` counter actually read, so widening the census without
    widening this set fails here rather than in a rendered figure."""
    census, _records, _rows, _malformed = otel_normalize.stream_bodies(_STREAM_CORPUS)
    assert all(set(entry) == {"project_id", "project_attributed_by"} for entry in census)
    assert [e["project_id"] for e in census] == [
        _OWN_ID, _OWN_ID, _NEIGHBOUR_ID, "unattributed"]
    assert [e["project_attributed_by"] for e in census] == [None, "backfill", None, None]


def test_stream_bodies_accepts_a_generator_and_never_indexes_it():
    """The production caller feeds it `EventStore.iter_canal_b_bodies()`, whose
    entire purpose is that no list of the channel exists. This one only proves
    the argument may be a bare iterator — a `len()` or a subscript added inside
    would fail here.

    IT DOES **NOT** CATCH A `list(bodies)` AT THE TOP, and the first draft of
    this witness claimed it did. Measured: a re-implementation that starts with
    `lines = list(bodies)` passes every assertion below. The two witnesses that
    follow are the ones that bite; this docstring said otherwise until the
    binôme built the mutant and showed it green."""
    census, _records, rows_read, malformed = otel_normalize.stream_bodies(iter(_STREAM_CORPUS))
    assert rows_read == 8
    assert malformed == 2
    assert len(census) == 4


def test_stream_bodies_parses_each_row_before_pulling_the_next(monkeypatch):
    """THE INTERLEAVING, which is the property the fix actually buys. A
    `list(bodies)` in the first line satisfies every count-based assertion in
    this file and re-materialises the whole channel; only the ORDER of
    producer and consumer separates the two.

    Measured on the mutant: real code gives `[0, 1, 2, 3]`, the eager form
    gives `[0, 0, 0, 0]`."""
    normalised: list[int] = []
    real_normalize = otel_normalize.normalize_envelope
    monkeypatch.setattr(otel_normalize, "normalize_envelope",
                        lambda env: (normalised.append(1), real_normalize(env))[1])
    pulls: list[int] = []

    def producer():
        for line in _STREAM_CORPUS[:4]:   # the four well-formed rows
            pulls.append(len(normalised))
            yield line

    otel_normalize.stream_bodies(producer())
    assert pulls == [0, 1, 2, 3], pulls


def test_stream_bodies_peak_memory_is_one_row_not_the_channel():
    """THE MEMORY WITNESS, and the reason this whole lot exists. Every other
    assertion here is about MEANING; a regression that restored the 4,7 Gio
    peak would keep all of them green.

    2 000 rows of 20 Ko is a 40 Mo corpus. `kind: "failure"` normalises to zero
    records by design, so the `records` list — which legitimately grows and is
    NOT what this bounds — stays empty and the peak measures the read alone.
    Measured: 0,6 Mo on the real code, 40,9 Mo on a mutant that materialises."""
    import tracemalloc

    pad = "x" * 20_000

    def corpus(count):
        for _ in range(count):
            yield json.dumps({"ts": "2026-01-01T00:00:00Z", "kind": "failure",
                              "project_id": "unattributed", "provenance": "p",
                              "project_attributed_by": None, "body": {"pad": pad}})

    tracemalloc.start()
    try:
        _census, records, rows_read, _malformed = otel_normalize.stream_bodies(corpus(2000))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert rows_read == 2000
    assert records == [], "the corpus must normalise to nothing, or this measures the wrong thing"
    assert peak < 8_000_000, f"peak {peak / 1e6:.1f} Mo — the channel was materialised"


def test_stream_bodies_counts_blank_rows_as_read_but_never_as_malformed():
    """`_parse_envelope_lines`'s two tolerances, preserved deliberately: a
    blank row is a row that EXISTS (so `rows_read` counts it) and is not
    corrupt (so it must not raise the `partial` flag the dashboard renders).
    Losing either would move a figure the pilot reads."""
    census, records, rows_read, malformed = otel_normalize.stream_bodies(["", "   "])
    assert rows_read == 2
    assert malformed == 0
    assert census == []
    assert records == []
