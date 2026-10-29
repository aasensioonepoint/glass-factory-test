"""Part `governance` of the `dashboard_readers.py` façade (T-00001051): View 4 (Gouvernance).
Moved byte for byte; the façade loads this file ONCE (`_load_part`) and injects the handles declared below."""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Injected by dashboard_readers._load_part (T-00001051) — declared here, never assigned here:
_readers_base: Any
_readers_coverage_mcp: Any

# Names owned by another part, bound ONE PER LINE (the closure witness (j) judges this list):
TRAIL_UNUSABLE = _readers_base.TRAIL_UNUSABLE
_SKILLS_AUDIT_LOG_REL = _readers_base._SKILLS_AUDIT_LOG_REL
_RECENT_LIMIT = _readers_base._RECENT_LIMIT
_DAY_SERIES_LIMIT = _readers_base._DAY_SERIES_LIMIT
_SHORT_CLIP = _readers_base._SHORT_CLIP
_clip = _readers_base._clip
_day_of = _readers_base._day_of
_bump = _readers_base._bump
(CANAL_A_EMITTERS,) = (_readers_coverage_mcp.CANAL_A_EMITTERS,)


GOVERNANCE_KINDS: tuple[str, ...] = (
    "hook.deny", "hook.warn", "hook.check_fail", "gate.approval",
)


# ---------------------------------------------------------------------------
# View 4 — Gouvernance.
# ---------------------------------------------------------------------------

def build_governance(stream: dict[str, Any], project_root: Path,
                     canal_b_section: dict[str, Any]) -> dict[str, Any]:
    """`hook.deny|warn|check_fail` + `gate.approval`, aggregated per guard,
    per rule and per day. Carries the skills `AUDIT_LOG` gate state alongside,
    because design doc §F.3 makes that the canonical example of the
    distinction this view exists to draw: "aucun skill installé" and "trail
    perdu" must not render identically."""
    trail = {
        "status": stream["status"],
        "files": stream["files"],
        "malformed_lines_skipped": stream["malformed"],
        "reason": stream["reason"],
    }
    section: dict[str, Any] = {
        "trail": trail,
        "kinds_watched": list(GOVERNANCE_KINDS),
        "audit_log": _read_skills_audit_log(project_root),
        "emitters": {kind: CANAL_A_EMITTERS.get(kind) for kind in GOVERNANCE_KINDS},
        # Canal-B permission decisions are the OTHER half of design doc A.4
        # view 4. They are already aggregated by `_read_canal_b` - referenced
        # here by count, never re-read (one normaliser, one reader).
        "canal_b_tool_decisions": _canal_b_tool_decision_ref(canal_b_section),
    }
    if stream["status"] in TRAIL_UNUSABLE:
        section.update({"status": stream["status"], "reason": stream["reason"],
                        "totals": {}, "by_guard": {}, "by_rule": {}, "by_day": [],
                        "approvals": _approvals_unavailable(0), "recent": []})
        return section

    watched = set(GOVERNANCE_KINDS)
    matching = [r for r in stream["records"] if r.get("kind") in watched]

    totals: dict[str, int] = {kind: 0 for kind in GOVERNANCE_KINDS}
    by_guard: dict[str, dict[str, Any]] = {}
    by_rule: dict[str, int] = {}
    by_day: dict[str, dict[str, int]] = {}
    approvals: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []

    for record in matching:
        kind = str(record.get("kind"))
        totals[kind] = totals.get(kind, 0) + 1
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        day = _day_of(record)
        if day is not None:
            slot = by_day.setdefault(day, {k: 0 for k in GOVERNANCE_KINDS})
            slot[kind] = slot.get(kind, 0) + 1
        if kind == "gate.approval":
            approvals.append(record)
        else:
            guard = str(data.get("guard") or "unattributed")
            rule = str(data.get("rule") or "unspecified")
            guard_slot = by_guard.setdefault(
                guard, {kind_name: 0 for kind_name in GOVERNANCE_KINDS if kind_name != "gate.approval"}
            )
            guard_slot[kind] = guard_slot.get(kind, 0) + 1
            guard_slot.setdefault("rules", {})
            _bump(guard_slot["rules"], rule)
            _bump(by_rule, f"{guard}:{rule}")
        recent.append({
            "ts": record.get("ts"),
            "kind": kind,
            "host": record.get("host"),
            "task": record.get("task"),
            "agent": record.get("agent"),
            "guard": data.get("guard"),
            "rule": data.get("rule"),
            "path": _clip(data.get("path"), _SHORT_CLIP),
            "cmd_sha256": data.get("cmd_sha256"),
            "decision": data.get("decision"),
            "source": data.get("source"),
            "plan_hash": data.get("plan_hash"),
        })

    section["totals"] = totals
    section["by_guard"] = by_guard
    section["by_rule"] = by_rule
    section["by_day"] = [
        {"day": day, **counts} for day, counts in sorted(by_day.items())[-_DAY_SERIES_LIMIT:]
    ]
    section["recent"] = recent[-_RECENT_LIMIT:]
    section["approvals"] = _build_approvals(approvals)
    if matching:
        section["status"] = "ok"
        section["reason"] = None
    else:
        section["status"] = "no_events"
        section["reason"] = (
            f"the trail is PRESENT ({stream['files']} day-file(s), "
            f"{len(stream['records'])} event(s)) and holds none of "
            f"{', '.join(GOVERNANCE_KINDS)}. A real measurement: nothing was denied, "
            "warned on, failed a check, or recorded as an approval."
        )
    return section


def _approvals_unavailable(count: int) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "count": count,
        "decisions": {},
        "sources": {},
        "with_plan_hash": 0,
        "without_plan_hash": 0,
        "reason": (
            "`gate.approval` is a DECLARED kind with NO emitter (see the coverage "
            "view): no hook can observe a manual approval - design doc §G.2, "
            "PermissionRequest asks the hook to decide instead of reporting the "
            "human's decision, and PermissionDenied never fires on a manual deny. "
            "The plan hash that would make 'the plan approved' verifiable is "
            "T-00000028. Zero here is a blind spot, not a count."
        ),
    }


def _build_approvals(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return _approvals_unavailable(0)
    decisions: dict[str, int] = {}
    sources: dict[str, int] = {}
    with_hash = 0
    for record in records:
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        _bump(decisions, str(data.get("decision") or "unspecified"))
        _bump(sources, str(data.get("source") or "unspecified"))
        if data.get("plan_hash"):
            with_hash += 1
    return {
        "status": "ok",
        "count": len(records),
        "decisions": decisions,
        "sources": sources,
        "with_plan_hash": with_hash,
        "without_plan_hash": len(records) - with_hash,
        "reason": None if with_hash == len(records) else (
            "an approval without `plan_hash` records THAT a plan was approved, "
            "never WHICH one (design doc §G.2 - tier-2 fidelity until T-00000028)."
        ),
    }


def _canal_b_tool_decision_ref(canal_b_section: dict[str, Any]) -> dict[str, Any]:
    counts = canal_b_section.get("counts")
    if not isinstance(counts, dict):
        return {"status": "unavailable", "count": 0,
                "reason": "canal B is not collected in this tree - " + str(
                    canal_b_section.get("reason") or "no reason reported")}
    total = int(counts.get("tool_decision_logs") or 0)
    return {
        "status": "ok" if total else "no_events",
        "count": total,
        "source": "canal_b.counts.tool_decision_logs (already normalised; never re-read here)",
        "reason": None if total else (
            "no `tool_decision` log record in canal B yet. This is the ONLY channel "
            "that reports a real human permission decision (design doc §G.2)."
        ),
    }


def _read_skills_audit_log(project_root: Path) -> dict[str, Any]:
    """`state/gates/AUDIT_LOG` — the skills-install gate. Design doc §F.3: an
    ABSENT file and a file with zero rows are different facts, and
    `audit-gate.sh` blocks on absence, so the view must name which one it is."""
    path = project_root.joinpath(*_SKILLS_AUDIT_LOG_REL)
    if not path.exists():
        return {
            "status": "trail_absent",
            "rows": 0,
            "reason": (
                "state/gates/AUDIT_LOG does not exist. audit-gate.sh BLOCKS every "
                "skill install in that state, so this is 'no skill can be installed', "
                "not 'no skill was installed' - and it is indistinguishable from a "
                "lost trail (design doc §F.3)."
            ),
        }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "degraded", "rows": 0, "reason": f"AUDIT_LOG unreadable: {type(exc).__name__}"}
    rows = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    passing = sum(1 for line in rows if "audit=pass" in line)
    return {
        "status": "ok" if rows else "no_events",
        "rows": len(rows),
        "audit_pass_rows": passing,
        "reason": None if rows else (
            "AUDIT_LOG EXISTS and holds zero row: no skill has been audited. "
            "Present-and-empty, which is a measurement - not a lost trail."
        ),
    }
