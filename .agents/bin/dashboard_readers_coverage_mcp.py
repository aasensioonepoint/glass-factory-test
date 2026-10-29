"""Part `coverage_mcp` of the `dashboard_readers.py` façade (T-00001051): View 9 (MCP) and View 8 (coverage).
Moved byte for byte; the façade loads this file ONCE (`_load_part`) and injects the handles declared below."""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

# Injected by dashboard_readers._load_part (T-00001051) — declared here, never assigned here:
_readers_base: Any
_mcp_render: Any

# Names owned by another part, bound ONE PER LINE (the closure witness (j) judges this list):
TRAIL_UNUSABLE = _readers_base.TRAIL_UNUSABLE
MCP_CONFIG_SOURCES = _readers_base.MCP_CONFIG_SOURCES
_ALLOWLIST_REL = _readers_base._ALLOWLIST_REL
_RECENT_LIMIT = _readers_base._RECENT_LIMIT
_SHORT_CLIP = _readers_base._SHORT_CLIP
_clip = _readers_base._clip
_bump = _readers_base._bump
_percentile = _readers_base._percentile


# Coverage matrix cell statuses. `not_emitted_by_design` is REUSED from
# `otel_normalize.cost_summary_for_host` (task instruction) rather than
# renamed — one word for one fact across the whole kit.
COVERAGE_CELL_STATUSES: tuple[str, ...] = (
    "received", "off", "not_emitted_by_design", "not_wired_yet",
    "no_data_yet", "unknown",
)

COVERAGE_LEGEND: dict[str, str] = {
    "received": "at least one record of this signal was read for this host",
    "off": (
        "the host CAN emit this signal and the operator disabled it. RESERVED "
        "AND CURRENTLY UNREACHABLE, declared rather than faked: telemetry "
        "enablement lives in USER-scope config (~/.claude.json, "
        "~/.codex/config.toml, ~/.gemini/settings.json) which this reader "
        "deliberately does not read - AGENTS.md names that surface as "
        "uncovered. Absence therefore reports `no_data_yet`, never `off`, "
        "because guessing `off` would claim a fact about the operator's "
        "machine we did not observe."
    ),
    "not_emitted_by_design": (
        "this host structurally cannot emit this signal - a documented fact, "
        "never a zero (e.g. Codex emits no OTel metrics at all)"
    ),
    "not_wired_yet": (
        "the kit DECLARES this signal but no emitter calls it for this host "
        "yet. A gap in the kit, not in the host, and not a measurement"
    ),
    "no_data_yet": (
        "an emitter exists and nothing has been observed. Could be a quiet "
        "repo, could be a broken emitter - indistinguishable from here, said "
        "out loud rather than rendered as a clean zero"
    ),
    "unknown": "coverage for this host/signal pair has never been established",
}

COVERAGE_DOCTRINE = (
    "design doc G.4: the target is NOT 'every signal', it is 'no silently "
    "missing signal'. A dashboard showing 85% of the signal while being "
    "explicit about the other 15% is more useful than one showing 85% and "
    "letting the reader believe 100%. Every cell below carries a status from "
    "a CLOSED vocabulary; no cell is ever blank."
)

# ---------------------------------------------------------------------------
# Canal-A emitter registry (the coverage matrix's own source of truth).
#
# VERIFIED by grep over `.claude/hooks/`, `.agents/security/` and
# `.agents/bin/` on 2026-07-28, not inferred: the value is the emitting
# script, or None for a kind `events.py` DECLARES in `KNOWN_KINDS` while no
# call site emits it. Those Nones are the honest content of the Couverture
# view - `task.*` / `ledger.add` / `index.build` are phase-0 item 3 of the
# design doc (tasks.py/ledger.py/build_index.py were never wired), and
# `gate.plan_verdict` / `gate.approval` / `gate.security` are the tier-2
# agent-discipline signals of §G.1-G.2.
#
# `test_dashboard.py` asserts this table's KEYS equal `events.KNOWN_KINDS`
# exactly, so adding a kind without deciding its coverage story fails a test
# rather than silently producing a blank matrix row.
# ---------------------------------------------------------------------------

CANAL_A_EMITTERS: dict[str, str | None] = {
    "session.start": ".claude/hooks/session-start.sh",
    "session.stop": ".claude/hooks/agent-events.sh",
    "session.compact": ".claude/hooks/pre-compact.sh",
    "session.notify": ".claude/hooks/notify-event.sh",
    "task.new": None,
    "task.state": None,
    "task.stage": None,
    "agent.start": ".claude/hooks/agent-events.sh",
    "agent.stop": ".claude/hooks/log-agent-usage.sh",
    "gate.forecast": ".claude/hooks/run-recap.sh",
    "gate.plan_verdict": None,
    "gate.approval": None,
    "gate.security": None,
    "gate.coverage_degraded": ".claude/hooks/mcp-events.sh, .agents/bin/tasks_sync.py",
    "hook.deny": ".claude/hooks/protect-paths.sh, safe-bash.sh, audit-gate.sh",
    "hook.warn": None,
    "hook.check_fail": ".claude/hooks/post-edit-check.sh",
    "scan.secrets": ".agents/security/gitleaks-scan.sh",
    "scan.sast": ".agents/security/semgrep-scan.sh",
    "scan.sca": ".agents/security/sca-scan.sh, .claude/hooks/emit-event.sh",
    "scan.iac": None,
    "scan.waiver": None,
    "scan.mcp_call": ".claude/hooks/mcp-events.sh",
    "index.build": None,
    "index.stale": ".claude/hooks/stop-reindex.sh",
    "ledger.add": None,
}

# Canal A per host. Claude Code is the only host whose hooks call `events.py`
# today; the other three are T-00000027 (D5), not a host limitation - their
# `_common.py` `emit()` is the hook-OUTPUT protocol (a JSON object on stdout),
# a different thing that happens to share a verb.
CANAL_A_HOSTS: tuple[str, ...] = ("claude", "codex", "copilot", "gemini")

CANAL_A_HOST_WIRING: dict[str, str] = {
    "claude": "wired",
    "codex": "not_wired_yet",
    "copilot": "not_wired_yet",
    "gemini": "not_wired_yet",
}

_CANAL_A_PARITY_REASON = (
    "canal-A parity for this host is T-00000027 (design doc phase 3): "
    "events.py is not called from .codex/hooks/, .gemini/hooks/ or "
    ".github/hooks/ yet. Their _common.py `emit()` writes the host's own hook "
    "RESPONSE to stdout - it is not this kit's event stream."
)

_MCP_ZERO_SERVERS_NOTE = (
    "the kit ships ZERO MCP servers by design (.agents/ref/MCP_REGISTRY.md): "
    "an empty inventory here is the expected steady state, not a read failure. "
    "The procedure that must exist BEFORE the first server does is in that "
    "registry; audited rows are appended to MCP_ALLOWLIST.md by a human only."
)

_MCP_UNAUDITED_FLAG = (
    "RED FLAG: an MCP tool call whose package identity has no audit=pass row "
    "in .agents/state/gates/MCP_ALLOWLIST.md. Tool descriptions are "
    "third-party free text entering the model's instruction channel every "
    "session and are mutable server-side without a commit."
)


# ---------------------------------------------------------------------------
# View 9 — MCP. Inventory (allowlist join host configs) x usage (canal-A
# `scan.mcp_call`, canal-B `mcp_server_connection`), red flag on any call
# whose package identity is not audited.
# ---------------------------------------------------------------------------

def build_mcp(project_root: Path, stream: dict[str, Any],
              canal_b_section: dict[str, Any]) -> dict[str, Any]:
    allowlist = _read_mcp_allowlist(project_root)
    configs = _read_mcp_configs(project_root, allowlist)
    usage = _mcp_usage(stream, allowlist)
    red_flags: list[dict[str, Any]] = list(usage.pop("red_flags", []))
    for config in configs:
        for server in config["servers"]:
            if server.get("audited") is False:
                red_flags.append({
                    "kind": "config_not_audited",
                    "host": config["host"],
                    "config_key": server.get("config_key"),
                    "package": server.get("package"),
                    "version": server.get("version"),
                    "reason": server.get("audit_reason"),
                })
    return {
        "status": "ok",
        "reason": None,
        "allowlist": allowlist,
        "configs": configs,
        "usage": usage,
        "canal_b": _mcp_canal_b(canal_b_section),
        "red_flags": red_flags,
        "red_flag_doctrine": _MCP_UNAUDITED_FLAG,
        "zero_servers_note": _MCP_ZERO_SERVERS_NOTE,
        "redaction_note": (
            "host configs are read for PACKAGE IDENTITY only. `env` values and the "
            "raw `args` list are never surfaced - an MCP arg or env value can be a "
            "live credential (mcp_render.py's own literal-secret scan exists for "
            "exactly that), and this payload leaves the process over HTTP."
        ),
    }


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_html_comments(text: str) -> str:
    """Remove `<!-- ... -->` blocks before the allowlist row parser sees them.

    NOT cosmetic, and NOT a re-derivation of the row parser (that stays
    `mcp_render.parse_allowlist`, the single definition of "which package
    identity is audited"). MEASURED on the real file: `MCP_ALLOWLIST.md`'s
    header comment documents its own line format with the literal example

        mcp <name>@<version> audit=pass by=<who> date=<date> evidence=<path>

    and `parse_allowlist` matches it as a ROW — it advertises tolerance of the
    HTML-comment header but only skips lines that do not start with `mcp `.
    So a file whose own header states "This file has zero rows today" parses as
    `{'<name>': {'<version>'}}`: this view would report `status: ok`,
    `row_count: 1`, i.e. "something is audited" when nothing is. That is the
    false-GO shape, in the one panel whose whole job is to say what is NOT
    audited.

    UPDATE (T-00000039, fixed upstream since): `parse_allowlist` now strips
    HTML comments and refuses placeholder identities itself, so this call is
    belt-and-braces rather than the only guard. Kept deliberately: it costs one
    regex, and it keeps this panel correct against an OLDER `mcp_render.py` in a
    project provisioned before that fix. The upstream gate was never exploitable
    by the phantom row (an npm identity cannot contain `<` or `>`, so no REAL
    package was authorised) — only its row COUNT was wrong."""
    return _HTML_COMMENT_RE.sub("", text)


def _read_mcp_allowlist(project_root: Path) -> dict[str, Any]:
    path = project_root.joinpath(*_ALLOWLIST_REL)
    if not path.exists():
        return {"status": "trail_absent", "rows": {}, "row_count": 0, "reason": (
            "MCP_ALLOWLIST.md does not exist. Nothing is audited, so EVERY server "
            "and every call is a red flag - not 'no servers configured'."
        )}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "degraded", "rows": {}, "row_count": 0,
                "reason": f"MCP_ALLOWLIST.md unreadable: {type(exc).__name__}"}
    try:
        rows = _mcp_render.parse_allowlist(_strip_html_comments(text))
    except Exception as exc:  # noqa: BLE001 - a parser surprise must not take the view down
        return {"status": "degraded", "rows": {}, "row_count": 0,
                "reason": f"allowlist parse failed: {type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "status": "ok" if rows else "no_events",
        "rows": {name: sorted(versions) for name, versions in sorted(rows.items())},
        "row_count": len(rows),
        "reason": None if rows else (
            "MCP_ALLOWLIST.md EXISTS and holds zero audit=pass row - the expected "
            "steady state for a kit that ships zero MCP servers. Present-and-empty, "
            "not a lost trail."
        ),
        "identity_note": (
            "a row's <name> is the PACKAGE IDENTITY extracted from the launch args, "
            "never the human-chosen config key: a row for the config key does not "
            "authorise the real package."
        ),
    }


def _read_mcp_configs(project_root: Path, allowlist: dict[str, Any]) -> list[dict[str, Any]]:
    audited = allowlist.get("rows") if isinstance(allowlist.get("rows"), dict) else {}
    allowlist_usable = allowlist.get("status") in ("ok", "no_events")
    out: list[dict[str, Any]] = []
    for source in MCP_CONFIG_SOURCES:
        rel = "/".join(source["segments"])
        path = project_root.joinpath(*source["segments"])
        entry: dict[str, Any] = {"host": source["host"], "path": rel, "servers": []}
        if not path.exists():
            entry.update({"status": "absent", "present": False, "reason": (
                f"{rel} does not exist - no project-scope MCP server declared for "
                "this host"
            )})
            out.append(entry)
            continue
        entry["present"] = True
        try:
            if source["format"] == "toml":
                data: Any = tomllib.loads(path.read_text(encoding="utf-8"))
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            entry.update({"status": "degraded", "reason": (
                f"{rel} unreadable or malformed: {type(exc).__name__}: {str(exc)[:200]}"
            )})
            out.append(entry)
            continue
        servers = data.get(source["servers_key"]) if isinstance(data, dict) else None
        if not isinstance(servers, dict) or not servers:
            entry.update({"status": "no_events", "reason": (
                f"{rel} exists and declares no `{source['servers_key']}` entry"
            )})
            out.append(entry)
            continue
        for key, spec in servers.items():
            entry["servers"].append(
                _describe_mcp_server(str(key), spec, audited, allowlist_usable)
            )
        entry.update({"status": "ok", "reason": None})
        out.append(entry)
    return out


def _describe_mcp_server(config_key: str, spec: Any, audited: dict[str, Any],
                         allowlist_usable: bool) -> dict[str, Any]:
    """Package identity + audit verdict for ONE configured server. Emits the
    command NAME and an arg COUNT, never an arg value and never `env`."""
    if not isinstance(spec, dict):
        return {"config_key": config_key, "command": None, "package": None, "version": None,
                "identity_status": "unresolved", "audited": None,
                "audit_reason": "the config entry is not an object"}
    command = spec.get("command")
    raw_args = spec.get("args") if isinstance(spec.get("args"), list) else []
    out: dict[str, Any] = {
        "config_key": config_key,
        "command": command if isinstance(command, str) else None,
        "arg_count": len(raw_args),
        "env_key_count": len(spec.get("env")) if isinstance(spec.get("env"), dict) else 0,
    }
    pin = _mcp_render.npx_shape(command if isinstance(command, str) else "", raw_args)
    if pin is None:
        out.update({
            "package": None, "version": None, "identity_status": "unresolved",
            "audited": None,
            "audit_reason": (
                "package identity cannot be extracted from this launch shape "
                "(mcp_render.py resolves `npx [-y] <pkg>@<version>` only). Audit "
                "state is UNRESOLVED - a normal outcome, never itself a pass."
            ),
        })
        return out
    name, version = _mcp_render.split_pin(pin)
    out.update({"package": name, "version": version, "identity_status": "resolved"})
    if not allowlist_usable:
        out.update({"audited": None, "audit_reason": "the allowlist could not be read"})
        return out
    versions = audited.get(name)
    if versions is None:
        out.update({"audited": False, "audit_reason": (
            f"no audit=pass row for '{name}' in MCP_ALLOWLIST.md"
        )})
    elif version not in versions:
        out.update({"audited": False, "audit_reason": (
            f"'{name}' is pinned at '{version}' but the allowlist audits "
            f"{sorted(versions)} - a version bump must be re-audited"
        )})
    else:
        out.update({"audited": True, "audit_reason": None})
    return out


# `gate.coverage_degraded` a DEUX émetteurs (mcp-events.sh, tasks_sync.py — T-00001006) : l'onglet MCP ne compte que
# les raisons de sa famille (`mcp_resolution_failed:<serveur>`) et celles qu'il ne sait pas attribuer.
_MCP_DEGRADED_REASON_PREFIX = "mcp_"


def _mcp_usage(stream: dict[str, Any], allowlist: dict[str, Any]) -> dict[str, Any]:
    """`scan.mcp_call` aggregated per server: calls, audit states, latency,
    failures. A call whose `server` identity has no audit=pass row is a RED
    FLAG regardless of what the emitting hook thought."""
    if stream.get("status") in TRAIL_UNUSABLE:
        return {"status": stream["status"], "calls": 0, "by_server": {},
                "unaudited_calls": 0, "unresolved_calls": 0,
                "coverage_degraded_events": 0, "coverage_degraded_unattributed": 0,
                "red_flags": [],
                "reason": stream.get("reason")}
    audited = allowlist.get("rows") if isinstance(allowlist.get("rows"), dict) else {}
    calls = [r for r in stream["records"] if r.get("kind") == "scan.mcp_call"]
    degraded_events: list[dict[str, Any]] = []
    degraded_unattributed = 0
    for record in stream["records"]:
        if record.get("kind") != "gate.coverage_degraded":
            continue
        data = record.get("data")
        reason = data.get("reason") if isinstance(data, dict) else None
        if not isinstance(reason, str):
            degraded_unattributed += 1  # chemins dégradés d'`events.emit` (rédaction, troncature) : gardés, non attribués
            degraded_events.append(record)
        elif reason.startswith(_MCP_DEGRADED_REASON_PREFIX):
            degraded_events.append(record)
    by_server: dict[str, dict[str, Any]] = {}
    latencies: dict[str, list[float]] = {}
    unaudited = unresolved = 0
    for record in calls:
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        server = str(data.get("server") or "unattributed")
        slot = by_server.setdefault(server, {
            "calls": 0, "audit_states": {}, "tools": {}, "failures": 0,
            "in_allowlist": None,
        })
        slot["calls"] += 1
        state = str(data.get("audit_state") or "unresolved")
        _bump(slot["audit_states"], state)
        tool = data.get("tool")
        if isinstance(tool, str) and tool:
            _bump(slot["tools"], tool)
        duration = data.get("duration_ms")
        if isinstance(duration, (int, float)):
            latencies.setdefault(server, []).append(float(duration))
        else:
            # No duration is not a failure; a MISSING duration on a call that
            # should carry one is worth counting rather than averaging away.
            slot["failures"] += 0
        if state == "unaudited":
            unaudited += 1
        elif state == "unresolved":
            unresolved += 1
    red_flags: list[dict[str, Any]] = []
    for server, slot in by_server.items():
        name, _, version = server.rpartition("@")
        identity = name or server
        versions = audited.get(identity)
        in_allowlist = bool(versions) and (not version or version in versions)
        slot["in_allowlist"] = in_allowlist
        samples = sorted(latencies.get(server, []))
        slot["latency_ms"] = {
            "samples": len(samples),
            "min": samples[0] if samples else None,
            "p50": _percentile(samples, 0.50),
            "p95": _percentile(samples, 0.95),
            "max": samples[-1] if samples else None,
            "note": "nearest-rank percentiles; an interpolated p95 on a handful of "
                    "samples would invent a latency nobody measured",
        }
        if not in_allowlist:
            red_flags.append({
                "kind": "unaudited_call",
                "server": server,
                "package_identity": identity,
                "calls": slot["calls"],
                "audit_states": dict(slot["audit_states"]),
                "reason": _MCP_UNAUDITED_FLAG,
            })
    return {
        "status": "ok" if calls else "no_events",
        "calls": len(calls),
        "by_server": by_server,
        "unaudited_calls": unaudited,
        "unresolved_calls": unresolved,
        "coverage_degraded_events": len(degraded_events),
        "coverage_degraded_unattributed": degraded_unattributed,
        "red_flags": red_flags,
        "reason": None if calls else (
            "the trail is present and holds no `scan.mcp_call`: no MCP tool was "
            "invoked. Expected for a kit that ships zero MCP servers."
        ),
        "audit_state_note": (
            "`audit_state` is 3-state at the emitter: audited | unaudited | "
            "unresolved. `unresolved` is a NORMAL outcome (e.g. no .mcp.json in "
            "this repo), never itself a degradation. `in_allowlist` below is this "
            "reader's OWN verdict, recomputed from MCP_ALLOWLIST.md rather than "
            "trusted from the event."
        ),
    }


def _mcp_canal_b(canal_b_section: dict[str, Any]) -> dict[str, Any]:
    by_event = canal_b_section.get("by_event_name")
    if not isinstance(by_event, dict):
        return {"status": "unavailable", "mcp_server_connection": 0,
                "reason": "canal B is not collected in this tree - " + str(
                    canal_b_section.get("reason") or "no reason reported")}
    count = int(by_event.get("mcp_server_connection") or 0)
    return {
        "status": "ok" if count else "no_events",
        "mcp_server_connection": count,
        "source": "canal_b.by_event_name (already normalised; never re-read here)",
        "reason": None if count else (
            "no `mcp_server_connection` record in canal B. Note it is NOT in the "
            "frozen schema families, so it normalises with `schema_family: null` "
            "and is counted by event name only."
        ),
    }


# ---------------------------------------------------------------------------
# View 8 — Session & couverture. The signal x host matrix, plus the count of
# `gate.coverage_degraded` (a first-class kind, not an error sub-case).
# ---------------------------------------------------------------------------

def build_coverage(stream: dict[str, Any], canal_b_section: dict[str, Any],
                   normalize_mod: Any,
                   ingestion_section: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "reason": None,
        "doctrine": COVERAGE_DOCTRINE,
        "legend": COVERAGE_LEGEND,
        "cell_statuses": list(COVERAGE_CELL_STATUSES),
        "canal_a": _coverage_canal_a(stream),
        "canal_b": _coverage_canal_b(canal_b_section, normalize_mod),
        "coverage_degraded": _coverage_degraded(stream),
        # T-00000049 exit criterion 3. A trail that exists but has not been
        # PROJECTED yet is a coverage fact, so it belongs in the coverage view
        # rather than in a corner of the payload: "rattrapage au boot, batch, et
        # retard d'ingestion AFFICHÉ, jamais silencieux" (spec §A.2).
        "ingestion": _coverage_ingestion(ingestion_section),
    }


def _coverage_ingestion(ingestion_section: dict[str, Any] | None) -> dict[str, Any]:
    """Shape the lag report `event_store.ingestion_status()` produced, or say
    plainly that nobody supplied one. `None` here means "this caller did not
    pass an ingestion section" — which is NOT the same claim as "the ingestion
    is up to date", and must never render as one."""
    if not isinstance(ingestion_section, dict):
        return {
            "status": "unknown",
            "late": None,
            "message": None,
            "reason": (
                "no ingestion status was supplied to this view. UNKNOWN, not "
                "up-to-date: absence of a measurement is never a measurement of "
                "zero lag."
            ),
        }
    source = ingestion_section.get("source")
    if source == "sqlite":
        status = "late" if ingestion_section.get("late") else "ok"
    elif source == "absent":
        status = "not_projected_yet"
    else:
        status = "degraded"
    return {"status": status, **ingestion_section}


def _coverage_canal_a(stream: dict[str, Any]) -> dict[str, Any]:
    observed: dict[str, dict[str, int]] = {}
    trail_absent = stream.get("status") in TRAIL_UNUSABLE
    for record in stream.get("records") or []:
        kind = record.get("kind")
        host = record.get("host")
        if not isinstance(kind, str):
            continue
        observed.setdefault(kind, {})
        key = str(host) if isinstance(host, str) and host else "unknown"
        _bump(observed[kind], key)

    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    summary: dict[str, int] = {status: 0 for status in COVERAGE_CELL_STATUSES}
    for kind in sorted(CANAL_A_EMITTERS):
        emitter = CANAL_A_EMITTERS[kind]
        row: dict[str, dict[str, Any]] = {}
        for host in CANAL_A_HOSTS:
            count = observed.get(kind, {}).get(host, 0)
            if count:
                status = "received"
            elif CANAL_A_HOST_WIRING.get(host) != "wired":
                status = "not_wired_yet"
            elif emitter is None:
                status = "not_wired_yet"
            elif trail_absent:
                status = "unknown"
            else:
                status = "no_data_yet"
            row[host] = {"status": status, "count": count}
            summary[status] = summary.get(status, 0) + 1
        matrix[kind] = row

    unexpected_hosts = sorted(
        {host for counts in observed.values() for host in counts} - set(CANAL_A_HOSTS)
    )
    unknown_kinds = sorted(set(observed) - set(CANAL_A_EMITTERS))
    return {
        "status": stream.get("status"),
        "hosts": list(CANAL_A_HOSTS),
        "host_wiring": dict(CANAL_A_HOST_WIRING),
        "parity_reason": _CANAL_A_PARITY_REASON,
        "emitters": dict(CANAL_A_EMITTERS),
        "matrix": matrix,
        "summary": summary,
        "records_read": len(stream.get("records") or []),
        "files_read": stream.get("files", 0),
        "malformed_lines_skipped": stream.get("malformed", 0),
        # Never silently drop something the matrix has no row/column for.
        "unexpected_hosts": unexpected_hosts,
        "kinds_outside_the_declared_vocabulary": unknown_kinds,
        "reason": stream.get("reason"),
        "declared_kinds": len(CANAL_A_EMITTERS),
        "kinds_with_no_emitter": sorted(k for k, v in CANAL_A_EMITTERS.items() if v is None),
    }


def _coverage_canal_b(canal_b_section: dict[str, Any], normalize_mod: Any) -> dict[str, Any]:
    coverage_table: dict[str, str] = dict(getattr(normalize_mod, "HOST_METRICS_COVERAGE", {}) or {})
    hosts = sorted(coverage_table)
    families = sorted(
        set(getattr(normalize_mod, "_METRIC_FAMILIES", frozenset()))
        | set(getattr(normalize_mod, "_LOG_FAMILIES", frozenset()))
    )
    hosts_seen = canal_b_section.get("hosts_seen")
    if not isinstance(hosts_seen, dict):
        hosts_seen = {}
    collected = bool(canal_b_section.get("collected"))

    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    summary: dict[str, int] = {status: 0 for status in COVERAGE_CELL_STATUSES}
    for family in families:
        row: dict[str, dict[str, Any]] = {}
        for host in hosts:
            seen = hosts_seen.get(host) or {}
            count = int((seen.get("families") or {}).get(family, 0))
            declared = coverage_table.get(host, "unknown")
            if count:
                status = "received"
            elif declared == "not_emitted_by_design":
                status = "not_emitted_by_design"
            elif not collected:
                status = "unknown"
            elif declared == "collected":
                status = "no_data_yet"
            else:
                status = "unknown"
            row[host] = {"status": status, "count": count}
            summary[status] = summary.get(status, 0) + 1
        matrix[family] = row
    attribution = canal_b_section.get("attribution")
    return {
        "status": "ok" if collected else "unavailable",
        "hosts": hosts,
        "declared_coverage": coverage_table,
        "signals": families,
        "matrix": matrix,
        "summary": summary,
        "hosts_seen": hosts_seen,
        # V1-c (T-00000050): the project-attribution census, PASSED THROUGH
        # from `_aggregate_canal_b` and never re-derived here. It is deliberately
        # NOT folded into `matrix`/`summary`: those speak the CLOSED cell
        # vocabulary (`COVERAGE_CELL_STATUSES`), and `attributed` /
        # `unattributed` / `foreign_held` are not coverage statuses — widening a
        # closed vocabulary to host a different question is how both questions
        # get answered badly (iteration 3, C6: prefer two vocabularies to one
        # stretched).
        "attribution": attribution if isinstance(attribution, dict) else None,
        # The caveats travel with the DATA into this view too, so a reader who
        # only ever opens Couverture still sees the backfill/inference label.
        "attribution_caveats": [
            c for c in (canal_b_section.get("caveats") or []) if isinstance(c, str)
        ],
        "event_names_outside_the_frozen_schema": sorted(
            name for name in (canal_b_section.get("by_event_name") or {})
            if name not in families
        ),
        "reason": None if collected else canal_b_section.get("reason"),
        "schema_note": (
            "rows are the FROZEN schema families of otel_normalize.py. A record "
            "whose event name is outside them still normalises (schema_family: "
            "null) and is listed separately rather than dropped."
        ),
        "cross_host_note": (
            "design doc G.4: all four hosts have native OTel, but the SCHEMAS "
            "differ (claude_code.* / codex.* / gemini_cli.* / github.copilot.*). "
            "A row that is `not_emitted_by_design` for one host is a fact about "
            "that host's exporter, never a zero."
        ),
    }


def _coverage_degraded(stream: dict[str, Any]) -> dict[str, Any]:
    if stream.get("status") in TRAIL_UNUSABLE:
        return {"status": stream["status"], "count": 0, "by_reason": {}, "recent": [],
                "reason": stream.get("reason")}
    records = [r for r in stream["records"] if r.get("kind") == "gate.coverage_degraded"]
    by_reason: dict[str, int] = {}
    for record in records:
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        _bump(by_reason, str(_clip(data.get("reason") or "unspecified", _SHORT_CLIP)))
    return {
        "status": "ok" if records else "no_events",
        "count": len(records),
        "by_reason": by_reason,
        "recent": [
            {"ts": r.get("ts"), "host": r.get("host"), "task": r.get("task"),
             "reason": _clip((r.get("data") or {}).get("reason"), _SHORT_CLIP)}
            for r in records[-_RECENT_LIMIT:]
        ],
        "reason": None if records else (
            "no `gate.coverage_degraded` event. The kit treats degraded mode as a "
            "LEGITIMATE state and counts it as a first-class kind, so zero here "
            "means no degradation was reported - not that none happened."
        ),
        "doctrine": (
            "`gate.coverage_degraded` is a first-class kind, not an error sub-case: "
            "COVERAGE DEGRADED is never a false GO and never a frozen pipeline."
        ),
    }
