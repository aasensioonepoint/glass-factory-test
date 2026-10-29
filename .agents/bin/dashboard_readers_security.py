"""Part `security` of the `dashboard_readers.py` façade (T-00001051): View 5 (Sécurité) and the model rates.
Moved byte for byte; the façade loads this file ONCE (`_load_part`) and injects the handles declared below."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Injected by dashboard_readers._load_part (T-00001051) — declared here, never assigned here:
_readers_base: Any

# Names owned by another part, bound ONE PER LINE (the closure witness (j) judges this list):
_RATES_REL = _readers_base._RATES_REL
_AUDIT_LOG_JSONL_REL = _readers_base._AUDIT_LOG_JSONL_REL
_WAIVERS_REL = _readers_base._WAIVERS_REL
_RECENT_LIMIT = _readers_base._RECENT_LIMIT
_DAY_SERIES_LIMIT = _readers_base._DAY_SERIES_LIMIT
_SAMPLE_LIMIT = _readers_base._SAMPLE_LIMIT
_SHORT_CLIP = _readers_base._SHORT_CLIP
read_jsonl_file = _readers_base.read_jsonl_file
_clip = _readers_base._clip
_day_of = _readers_base._day_of
_bump = _readers_base._bump


# ---------------------------------------------------------------------------
# Security classes 0-3 (AGENTS.md "Security gate"). The table declares, per
# class, WHERE its count can legitimately come from - because two of the four
# have no class-tagged source at all today and must say so instead of
# reporting 0.
# ---------------------------------------------------------------------------

SECURITY_CLASS_ORDER: tuple[str, ...] = ("0", "1", "2", "3")

SECURITY_CLASSES: dict[str, dict[str, Any]] = {
    "0": {
        "label": "secrets",
        "waivable": False,
        "blocking": True,
        "doctrine": (
            "ABSOLUTE, NON-WAIVABLE, blocking - above every dependency class. "
            "No waiver register, no accepted-and-tracked path, no bypass. "
            "Resolved by removing AND rotating the credential."
        ),
        "sources": ("audit-log.jsonl entry=gitleaks-scan.sh (class 0)", "canal-A scan.secrets"),
    },
    "1": {
        "label": "produced code (SAST + manual review)",
        "waivable": False,
        "blocking": True,
        "doctrine": "HIGH/CRITICAL fixed by dev agents and re-reviewed until clean; the pipeline holds.",
        "sources": ("audit-log.jsonl entry=semgrep-scan.sh (class 1)", "canal-A scan.sast"),
    },
    "2": {
        "label": "actionable dependency (auto-fixed under sca-policy.json)",
        "waivable": False,
        "blocking": False,
        "doctrine": "fix <= minor, not never_auto, class known_cve -> auto-fixed by security-remediation, no human needed.",
        "sources": (),
    },
    "3": {
        "label": "non-actionable dependency (pilot decision: fix now, or accept & track)",
        "waivable": True,
        "blocking": False,
        "doctrine": "no fix / major-only / never_auto / supply-chain -> FIX NOW or ACCEPT & TRACK in sca-waivers.json.",
        "sources": ("sca-waivers.json (every entry IS a class-3 decision)",
                    "effective-verdict.json counters.active_at_gate (awaiting a decision)"),
    },
}

_CLASS_2_UNAVAILABLE = (
    "no source tags a finding as class 2 today. `sca-scan.sh`'s audit-log rows "
    "carry no `class` field (only gitleaks/semgrep do), and the canal-A kinds "
    "that would record a remediation - `scan.waiver`, and any auto-fix event - "
    "have no emitter (see the coverage view). Reporting 0 here would assert "
    "'nothing was auto-fixed', which we did not observe."
)

_CLASS_3_PARTIAL = (
    "counted from the waiver register and from the effective verdict's "
    "active_at_gate, which is what a class-3 decision leaves behind. It is NOT "
    "a count of class-3 FINDINGS: sca-scan.sh's audit rows carry no `class` "
    "field, so a class-3 finding that was fixed rather than waived leaves no "
    "class-tagged trace."
)

# A waiver whose `review_by` falls inside this window is surfaced as due soon
# rather than only once it is already overdue.
WAIVER_DUE_SOON_DAYS = 14


# ---------------------------------------------------------------------------
# View 5 — Sécurité. Absorbs `sca-reports/audit-log.jsonl` through the shared
# canal-A reader (task scope: absorb, never duplicate).
# ---------------------------------------------------------------------------

def build_security(project_root: Path, verdict_section: dict[str, Any],
                   stream: dict[str, Any]) -> dict[str, Any]:
    history = _read_security_history(project_root)
    waivers = _read_waivers(project_root)
    return {
        "status": "ok",
        "reason": None,
        # The already-read effective verdict, referenced not re-read.
        "verdict": verdict_section,
        "classes": _build_security_classes(history, waivers, verdict_section, stream),
        "class_order": list(SECURITY_CLASS_ORDER),
        "waivers": waivers,
        "history": history,
    }


def _read_security_history(project_root: Path) -> dict[str, Any]:
    """`state/local/sca-reports/audit-log.jsonl` — the kit's oldest
    append-only trail (design doc A.1: "le seul flux append-only existant";
    B.1: "à absorber, pas à dupliquer"). Read with `read_jsonl_file`, i.e. the
    SAME reader canal A uses, so the read-to-the-last-newline rule applies to
    a scanner appending mid-poll too."""
    path = project_root.joinpath(*_AUDIT_LOG_JSONL_REL)
    if not path.exists():
        return {"status": "trail_absent", "entries_read": 0, "reason": (
            "sca-reports/audit-log.jsonl does not exist: no scan has ever appended "
            "to the audit trail in this tree. ABSENT TRAIL, not a clean history."
        )}
    records, malformed = read_jsonl_file(path)
    if not records:
        return {"status": "no_events", "entries_read": 0, "malformed_lines_skipped": malformed,
                "reason": (
                    "audit-log.jsonl EXISTS and holds no parsable record "
                    f"({malformed} malformed line(s) skipped)."
                )}
    by_entry: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    # T-00000370 (C40) — the gate's output became TWO fields: `findings` and
    # `couverture`. The field is ADDITIVE and `verdict` keeps its name and its
    # meaning: renaming it would collapse this histogram to "unknown" for every
    # record ever written, and the Security view reads it. Records predating the
    # change simply carry no `couverture` — they are counted as "unrecorded",
    # never folded into a real coverage value, so the two eras stay separable.
    by_couverture: dict[str, int] = {}
    by_class: dict[str, int] = {}
    by_day: dict[str, dict[str, int]] = {}
    findings_total = 0
    recent: list[dict[str, Any]] = []
    for record in records:
        _bump(by_entry, str(record.get("entry") or "unknown"))
        _bump(by_verdict, str(record.get("verdict") or "unknown"))
        _bump(by_couverture, str(record.get("couverture") or "unrecorded"))
        klass = record.get("class")
        _bump(by_class, "untagged" if klass is None else str(klass))
        findings = record.get("findings")
        if isinstance(findings, int):
            findings_total += findings
        day = _day_of(record)
        if day is not None:
            slot = by_day.setdefault(day, {"runs": 0, "findings": 0})
            slot["runs"] += 1
            if isinstance(findings, int):
                slot["findings"] += findings
    for record in records[-_RECENT_LIMIT:]:
        locations = record.get("locations")
        recent.append({
            "ts": record.get("ts"),
            "entry": record.get("entry"),
            "mode": record.get("mode"),
            "module": record.get("module"),
            "class": record.get("class"),
            "waivable": record.get("waivable"),
            "verdict": record.get("verdict"),
            # lock-busy / aborted: a NO-GO that obtained NO verdict, not a count of findings.
            "reason": record.get("reason"),
            "gate_level": record.get("gate_level"),
            "findings": record.get("findings"),
            # COUNT ONLY, never the list — see the module docstring.
            "locations_count": len(locations) if isinstance(locations, list) else None,
        })
    return {
        "status": "ok",
        "entries_read": len(records),
        "malformed_lines_skipped": malformed,
        "findings_total": findings_total,
        "by_entry": by_entry,
        "by_verdict": by_verdict,
        "by_couverture": by_couverture,
        "by_class": by_class,
        "series_daily": [
            {"day": day, **counts} for day, counts in sorted(by_day.items())[-_DAY_SERIES_LIMIT:]
        ],
        "recent": recent,
        "locations_note": (
            "`locations` is surfaced as a COUNT, never as the list: gitleaks runs "
            "--redact so no value is at stake, but a file:line inventory does not "
            "belong in a payload polled every 5 s."
        ),
        "reason": None,
    }


def _read_waivers(project_root: Path) -> dict[str, Any]:
    """`.agents/security/sca-waivers.json` with its deadlines resolved. The
    register is COMMITTED on purpose (it is the audit trail), so an empty
    `waivers` list is a real state - "nothing accepted" - and a missing file
    is a different one."""
    path = project_root.joinpath(*_WAIVERS_REL)
    if not path.exists():
        return {"status": "trail_absent", "count": 0, "entries": [], "reason": (
            "sca-waivers.json does not exist. The register is COMMITTED by design "
            "(it IS the audit trail), so its absence means the security assets are "
            "not provisioned in this tree - not that nothing was waived."
        )}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "degraded", "count": 0, "entries": [],
                "reason": f"sca-waivers.json unreadable: {type(exc).__name__}: {str(exc)[:200]}"}
    raw = data.get("waivers") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return {"status": "degraded", "count": 0, "entries": [],
                "reason": "sca-waivers.json has no `waivers` list at the top level"}
    today = datetime.now(timezone.utc).date()
    entries: list[dict[str, Any]] = []
    accepted = pending = overdue = due_soon = undated = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "accepted")
        review_by = item.get("review_by")
        days_left: int | None = None
        deadline_state = "none"
        if isinstance(review_by, str) and review_by:
            try:
                days_left = (date.fromisoformat(review_by) - today).days
            except ValueError:
                deadline_state = "malformed"
            else:
                if days_left < 0:
                    deadline_state = "overdue"
                    overdue += 1
                elif days_left <= WAIVER_DUE_SOON_DAYS:
                    deadline_state = "due_soon"
                    due_soon += 1
                else:
                    deadline_state = "ok"
        else:
            undated += 1
        if status == "pending_review":
            pending += 1
        else:
            accepted += 1
        advisories = item.get("advisories", "*")
        entries.append({
            "ecosystem": item.get("ecosystem"),
            "package": item.get("package"),
            "version": item.get("version"),
            "class": item.get("class"),
            "status": status,
            "review_by": review_by,
            "days_left": days_left,
            "deadline_state": deadline_state,
            "advisories": advisories if advisories == "*" else (
                advisories[:_SAMPLE_LIMIT] if isinstance(advisories, list) else advisories
            ),
            "reason": _clip(item.get("reason"), _SHORT_CLIP),
        })
    entries.sort(key=lambda e: (e["days_left"] if e["days_left"] is not None else 10 ** 6))
    return {
        "status": "ok" if entries else "no_events",
        "count": len(entries),
        "accepted": accepted,
        "pending_review": pending,
        "overdue": overdue,
        "due_soon": due_soon,
        "undated": undated,
        "due_soon_window_days": WAIVER_DUE_SOON_DAYS,
        "entries": entries,
        "reason": None if entries else (
            "the register EXISTS and holds zero waiver: nothing has been accepted or "
            "flagged pending_review. A measurement, not a missing file."
        ),
        "note": (
            "a waiver with no `review_by` never becomes overdue - counted as "
            "`undated` rather than silently treated as fine."
        ),
    }


def read_model_rates(project_root: Path, today: date) -> dict[str, Any]:
    """`.agents/ref/MODEL_RATES.json`, reduced to the rows in force on `today`.

    T-00000076. This table exists ONLY for the tokens x rate ESTIMATE. The native
    cost the dashboard already shows is a MEASUREMENT and needs no rate at all —
    the two must never be conflated, which is why every provider carries its
    `source` and `checked_at` through to the payload for the view to print.

    `today` is a parameter, not `date.today()` read inside: a rate row is chosen
    by date, so a test that cannot move the clock could not exercise the Sonnet 5
    introductory-price boundary — the one row in the table that expires.

    An absent or malformed table degrades to a stated absence. It never degrades
    to an empty rate set, which a caller could mistake for "every model is free".
    """
    path = project_root.joinpath(*_RATES_REL)
    if not path.exists():
        return {"status": "trail_absent", "providers": {}, "reason": (
            "MODEL_RATES.json does not exist: no rate table is declared in this tree, "
            "so no tokens x rate estimate can be computed. The measured native cost is "
            "unaffected."
        )}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "degraded", "providers": {}, "reason":
                f"MODEL_RATES.json unreadable: {type(exc).__name__}: {str(exc)[:200]}"}
    raw = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {"status": "degraded", "providers": {}, "reason":
                "MODEL_RATES.json has no `providers` object at the top level"}

    stamp = today.isoformat()
    providers: dict[str, Any] = {}
    for name, block in raw.items():
        if not isinstance(block, dict):
            continue
        models: dict[str, Any] = {}
        for model, rows in (block.get("models") or {}).items():
            if not isinstance(rows, list):
                continue
            active = _active_rate_row(rows, stamp)
            if active is not None:
                models[str(model)] = active
        providers[str(name)] = {
            "billing": block.get("billing"),
            "source": block.get("source"),
            "checked_at": block.get("checked_at"),
            "models": models,
            "aliases": block.get("aliases") or {},
            "alias_note": block.get("alias_note"),
            "cache_write_multipliers": block.get("cache_write_multipliers") or {},
            "cache_read_multiplier": block.get("cache_read_multiplier"),
            "unmodelled_multipliers": block.get("unmodelled_multipliers") or [],
            "absence_reason": block.get("absence_reason"),
            "seat_pricing_usd_per_user_month": block.get("seat_pricing_usd_per_user_month"),
        }
    return {
        "status": "ok",
        "unit": data.get("unit"),
        "as_of": stamp,
        "providers": providers,
        "doctrine": (
            "Cette table sert l'ESTIMATION, jamais la mesure. La telemetrie ne distingue "
            "pas le TTL des ecritures de cache (5 min vs 1 h, facteur 1,6), d'ou une "
            "fourchette plutot qu'une valeur unique."
        ),
    }


def _active_rate_row(rows: list[Any], stamp: str) -> dict[str, Any] | None:
    """The row whose [effective_from, effective_until] window contains `stamp`.

    ISO dates compare correctly as strings, so no parsing is needed — and a
    malformed date therefore fails the comparison rather than raising, which is
    the desired outcome: an unreadable window means the row is not selected, not
    that the whole table is discarded.
    """
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = row.get("effective_from")
        end = row.get("effective_until")
        if isinstance(start, str) and stamp < start:
            continue
        if isinstance(end, str) and stamp > end:
            continue
        return row
    return None


def _build_security_classes(history: dict[str, Any], waivers: dict[str, Any],
                            verdict_section: dict[str, Any],
                            stream: dict[str, Any]) -> dict[str, Any]:
    """One entry per class 0-3. Each carries its own `status` + `sources` so a
    number is never readable without knowing where it came from - and classes
    2/3, which no source tags, say `unavailable`/`partial` instead of 0."""
    by_entry = history.get("by_entry") if isinstance(history.get("by_entry"), dict) else {}
    by_class = history.get("by_class") if isinstance(history.get("by_class"), dict) else {}
    canal_a_kinds: dict[str, int] = {}
    for record in stream.get("records") or []:
        kind = record.get("kind")
        if isinstance(kind, str) and kind.startswith("scan."):
            _bump(canal_a_kinds, kind)

    out: dict[str, dict[str, Any]] = {}
    for key in SECURITY_CLASS_ORDER:
        meta = SECURITY_CLASSES[key]
        out[key] = {
            "label": meta["label"],
            "waivable": meta["waivable"],
            "blocking": meta["blocking"],
            "doctrine": meta["doctrine"],
            "sources": list(meta["sources"]),
        }

    history_absent = history.get("status") in ("trail_absent", "degraded")

    out["0"].update({
        "status": "unavailable" if history_absent else "ok",
        "audit_runs": int(by_entry.get("gitleaks-scan.sh") or 0),
        "class_tagged_rows": int(by_class.get("0") or 0),
        "canal_a_events": int(canal_a_kinds.get("scan.secrets") or 0),
        "reason": history.get("reason") if history_absent else None,
    })
    out["1"].update({
        "status": "unavailable" if history_absent else "ok",
        "audit_runs": int(by_entry.get("semgrep-scan.sh") or 0),
        "class_tagged_rows": int(by_class.get("1") or 0),
        "canal_a_events": int(canal_a_kinds.get("scan.sast") or 0),
        "reason": history.get("reason") if history_absent else None,
    })
    out["2"].update({
        "status": "unavailable",
        "count": None,
        "reason": _CLASS_2_UNAVAILABLE,
    })

    verdict = verdict_section.get("verdict") if isinstance(verdict_section, dict) else None
    counters = verdict.get("counters") if isinstance(verdict, dict) else None
    active_at_gate = counters.get("active_at_gate") if isinstance(counters, dict) else None
    waivers_ok = waivers.get("status") in ("ok", "no_events")
    out["3"].update({
        "status": "partial" if waivers_ok else "unavailable",
        "waived_accepted": waivers.get("accepted") if waivers_ok else None,
        "waived_pending_review": waivers.get("pending_review") if waivers_ok else None,
        "overdue_review": waivers.get("overdue") if waivers_ok else None,
        "awaiting_decision": active_at_gate,
        "awaiting_decision_source": (
            "effective-verdict.json counters.active_at_gate"
            if active_at_gate is not None else None
        ),
        "sca_audit_runs": int(by_entry.get("sca-scan.sh") or 0),
        "reason": _CLASS_3_PARTIAL if waivers_ok else waivers.get("reason"),
    })
    return out
