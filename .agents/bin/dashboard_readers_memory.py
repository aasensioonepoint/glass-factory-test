"""Part `memory` of the `dashboard_readers.py` façade (T-00001051): View 6 (Mémoire) and the specs graph.
Moved byte for byte; the façade loads this file ONCE (`_load_part`) and injects the handles declared below."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Injected by dashboard_readers._load_part (T-00001051) — declared here, never assigned here:
_readers_base: Any

# Names owned by another part, bound ONE PER LINE (the closure witness (j) judges this list):
_SPECS_GRAPH_REL = _readers_base._SPECS_GRAPH_REL
_CLIP_MARKER = _readers_base._CLIP_MARKER
_SPECS_PER_TASK_LIMIT = _readers_base._SPECS_PER_TASK_LIMIT
_SPECS_GRAPH_NODES_LIMIT = _readers_base._SPECS_GRAPH_NODES_LIMIT
_SPECS_GRAPH_EDGES_LIMIT = _readers_base._SPECS_GRAPH_EDGES_LIMIT
_SPECS_GRAPH_DECISIONS_LIMIT = _readers_base._SPECS_GRAPH_DECISIONS_LIMIT
_SPECS_GRAPH_ARBITRAGES_LIMIT = _readers_base._SPECS_GRAPH_ARBITRAGES_LIMIT
_SPECS_GRAPH_TEXT_CLIP = _readers_base._SPECS_GRAPH_TEXT_CLIP
_PREVIEW_CLIP = _readers_base._PREVIEW_CLIP
_clip = _readers_base._clip
_bump = _readers_base._bump


# ---------------------------------------------------------------------------
# View 6 — Mémoire. Pure function of the already-loaded stores: active
# constraints FIRST, then the specs journal grouped by task.
# ---------------------------------------------------------------------------

def build_memory(ledger_section: dict[str, Any], specs_section: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "reason": None,
        "ledger": _memory_ledger(ledger_section),
        "specs": _memory_specs(specs_section),
        "join_note": (
            "this view carries ORDERING and GROUPING, never a copy of the stores: "
            "entries are id + title (+ a 160-char preview for active constraints). "
            "The FULL text is already in this same payload under `ledger.data` / "
            "`specs.data` - measured, copying it here costs +14.6 Ko on a payload "
            "re-polled every 5 s. Join on `id`."
        ),
        "why_both": (
            "design doc addendum v3: the Mémoire view shows the DURABLE why (ledger) "
            "and the TASK-LOCAL why (specs journal). Neither substitutes for the "
            "other, and no telemetry produces either (§G.3)."
        ),
    }


def _memory_ledger(ledger_section: dict[str, Any]) -> dict[str, Any]:
    if ledger_section.get("status") != "ok":
        return {"status": "degraded", "reason": ledger_section.get("reason"),
                "active_constraints": [], "recent": [], "counts": {}, "total": 0}
    entries = (ledger_section.get("data") or {}).get("entries")
    if not isinstance(entries, list):
        return {"status": "degraded", "reason": "LEDGER.json holds no `entries` list",
                "active_constraints": [], "recent": [], "counts": {}, "total": 0}
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    constraints: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("category") or "unknown")
        status = str(entry.get("status") or "unknown")
        _bump(by_category, category)
        _bump(by_status, status)
        if status != "active":
            continue
        if category == "constraint":
            constraints.append({
                "id": entry.get("id"),
                "title": entry.get("title"),
                "created": entry.get("created"),
                "related": entry.get("related"),
                "tags": entry.get("tags"),
                # PREVIEW, not the text. Measured: carrying the full text of
                # this repo's 21 active constraints costs 14.6 Ko in a payload
                # re-polled every 5 s, and every byte of it is already in
                # `ledger.data.entries` in the SAME payload. A card needs a
                # first line; the panel joins on `id` for the rest.
                "text_preview": _clip(entry.get("text"), _PREVIEW_CLIP),
            })
        else:
            others.append({
                "id": entry.get("id"),
                "category": category,
                "title": entry.get("title"),
                "created": entry.get("created"),
                "related": entry.get("related"),
            })
    constraints.sort(key=lambda e: str(e.get("created") or ""), reverse=True)
    others.sort(key=lambda e: str(e.get("created") or ""), reverse=True)
    return {
        "status": "ok" if entries else "no_events",
        "reason": None if entries else "LEDGER.json exists and holds zero entry",
        # FIRST, and in full: an agent must read active constraints before
        # planning in the same area (AGENTS.md, institutional memory).
        "active_constraints": constraints,
        "active_constraint_count": len(constraints),
        "recent": others[:5],
        "recent_note": "the 5 most recent ACTIVE lesson/decision entries, id + title only",
        "counts": {"by_category": by_category, "by_status": by_status},
        "total": len(entries),
        "ordering": "active constraints first, then the 5 most recent active lesson/decision",
    }


def _memory_specs(specs_section: dict[str, Any]) -> dict[str, Any]:
    if specs_section.get("status") != "ok":
        return {"status": "degraded", "reason": specs_section.get("reason"),
                "by_task": [], "counts": {}, "total": 0}
    entries = (specs_section.get("data") or {}).get("entries")
    if not isinstance(entries, list):
        return {"status": "degraded", "reason": "SPECS.json holds no `entries` list",
                "by_task": [], "counts": {}, "total": 0}
    by_kind: dict[str, int] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "unknown")
        _bump(by_kind, kind)
        task = entry.get("task")
        key = task if isinstance(task, str) and task else "(no task)"
        grouped.setdefault(key, []).append({
            "id": entry.get("id"),
            "kind": kind,
            "title": entry.get("title"),
            "date": entry.get("date"),
        })
    tasks: list[dict[str, Any]] = []
    for task, items in grouped.items():
        items.sort(key=lambda e: str(e.get("date") or ""))
        kinds: dict[str, int] = {}
        for item in items:
            _bump(kinds, item["kind"])
        tasks.append({
            "task": task,
            "count": len(items),
            "kinds": kinds,
            "first_date": items[0].get("date"),
            "latest_date": items[-1].get("date"),
            "entries": items[-_SPECS_PER_TASK_LIMIT:],
            "entries_truncated": len(items) > _SPECS_PER_TASK_LIMIT,
        })
    tasks.sort(key=lambda t: str(t.get("latest_date") or ""), reverse=True)
    return {
        "status": "ok" if entries else "no_events",
        "reason": None if entries else "SPECS.json exists and holds zero entry",
        "by_task": tasks,
        "counts": {"by_kind": by_kind},
        "total": len(entries),
        "journal_note": (
            "append-when-remembered, NOT a complete trajectory (decision L-017): a "
            "task with few entries was not necessarily quiet - it may simply not "
            "have been journalled. Never read a gap here as an absence of work."
        ),
    }


# ---------------------------------------------------------------------------
# specs_graph — le graphe radial des décisions (T-00000379 lot E)
# ---------------------------------------------------------------------------
# CE LECTEUR NE DÉRIVE RIEN. Il lit UN artefact, `.agents/state/index/
# SPECS_GRAPH.json`, et le borne. La dérivation depuis les trois stores est le
# travail de `.agents/bin/specs_graph.py`, et c'est délibéré : le contrat
# (`.agents/ref/SPECS_GRAPH_CONTRACT.md`) ouvre DEUX chemins de publication —
# manuel (un projet qui possède un corpus de specs structuré le mappe 1:1) et
# généré. Un lecteur qui dériverait lui-même fermerait le premier chemin, et le
# kit se mettrait à parser les specs d'un projet, ce que le contrat interdit.
#
# TROIS ÉTATS, ET L'ABSENCE N'EST PAS UNE PANNE :
#   `no_events`  l'artefact n'existe pas — état de REPOS légitime (projet neuf,
#                aucune génération lancée). La SPA n'affiche pas l'entrée de
#                menu ; rien ne casse et rien ne ment.
#   `degraded`   présent mais hors contrat, avec la raison DITE.
#   `ok`         rendu, éventuellement borné, et toute borne appliquée est
#                annoncée dans `truncated` — une troncature silencieuse se lit
#                comme une couverture complète.
def _sg_clip(value: Any) -> str:
    text = value if isinstance(value, str) else ("" if value is None else str(value))
    if len(text) <= _SPECS_GRAPH_TEXT_CLIP:
        return text
    return text[:_SPECS_GRAPH_TEXT_CLIP] + _CLIP_MARKER


def _sg_nodes(raw: Any, truncated: dict[str, int]) -> list[dict[str, Any]]:
    rows = [n for n in raw if isinstance(n, dict) and n.get("id")] if isinstance(raw, list) else []
    if len(rows) > _SPECS_GRAPH_NODES_LIMIT:
        truncated["nodes"] = len(rows) - _SPECS_GRAPH_NODES_LIMIT
        rows = rows[:_SPECS_GRAPH_NODES_LIMIT]
    out = []
    for node in rows:
        decisions = node.get("decisions")
        decisions = [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []
        if len(decisions) > _SPECS_GRAPH_DECISIONS_LIMIT:
            truncated["decisions"] = truncated.get("decisions", 0) + (
                len(decisions) - _SPECS_GRAPH_DECISIONS_LIMIT)
            decisions = decisions[-_SPECS_GRAPH_DECISIONS_LIMIT:]
        counts = node.get("counts")
        size = node.get("size")
        out.append({
            "id": str(node["id"]),
            "title": _sg_clip(node.get("title")),
            # Anneau de layout : une valeur inconnue tombe sur l'anneau externe
            # plutôt que de faire disparaître le nœud (règle du contrat).
            "release": node.get("release") if node.get("release") in ("R0", "R1", "R2", "R3") else "R3",
            "size": size if isinstance(size, dict) else {"tasks": 1},
            "counts": counts if isinstance(counts, dict) else {},
            "decisions": [{
                "id": str(d.get("id", "")),
                "status": d.get("status", ""),
                "q": _sg_clip(d.get("q")),
                **({"date": d["date"]} if d.get("date") else {}),
            } for d in decisions],
        })
    return out


def build_specs_graph(project_root: Path) -> dict[str, Any]:
    """Read and bound the published specs graph. Never derives, never raises."""
    path = project_root.joinpath(*_SPECS_GRAPH_REL)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"status": "no_events",
                "reason": "aucun graphe publié — `python .agents/bin/specs_graph.py generate` "
                          "le dérive des trois stores d'état"}
    except OSError as exc:
        return {"status": "degraded",
                "reason": f"SPECS_GRAPH.json illisible : {type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return {"status": "degraded", "reason": f"SPECS_GRAPH.json n'est pas un JSON valide : {exc}"}
    if not isinstance(data, dict):
        return {"status": "degraded", "reason": "SPECS_GRAPH.json : objet attendu à la racine"}
    if data.get("version") != 1:
        return {"status": "degraded",
                "reason": f"version {data.get('version')!r} hors contrat — seule la version 1 est rendue"}

    truncated: dict[str, int] = {}
    nodes = _sg_nodes(data.get("nodes"), truncated)
    known = {n["id"] for n in nodes}

    # Une arête vers un nœud écarté (par une borne ou par une publication
    # incohérente) est ÉCARTÉE, jamais rendue pendante.
    raw_edges = data.get("edges")
    edges = [e for e in raw_edges
             if isinstance(e, dict) and e.get("source") in known and e.get("target") in known
             ] if isinstance(raw_edges, list) else []
    if len(edges) > _SPECS_GRAPH_EDGES_LIMIT:
        truncated["edges"] = len(edges) - _SPECS_GRAPH_EDGES_LIMIT
        edges = edges[:_SPECS_GRAPH_EDGES_LIMIT]

    raw_arb = data.get("arbitrages")
    arbitrages = [a for a in raw_arb if isinstance(a, dict)] if isinstance(raw_arb, list) else []
    if len(arbitrages) > _SPECS_GRAPH_ARBITRAGES_LIMIT:
        truncated["arbitrages"] = len(arbitrages) - _SPECS_GRAPH_ARBITRAGES_LIMIT
        arbitrages = arbitrages[-_SPECS_GRAPH_ARBITRAGES_LIMIT:]

    generator = data.get("generator")
    return {
        "status": "ok",
        "generated_at": data.get("generated_at", ""),
        "title": _sg_clip(data.get("title")),
        "source": _sg_clip(data.get("source")),
        # Qui a publié : la page le dit, parce qu'un graphe généré et un graphe
        # écrit à la main ne se lisent pas avec la même confiance.
        "published_by": "generator" if isinstance(generator, str) and generator else "manual",
        "stats": data.get("stats") if isinstance(data.get("stats"), dict) else {},
        "nodes": nodes,
        "edges": [{"source": e["source"], "target": e["target"],
                   "weight": e.get("weight", 1)} for e in edges],
        "arbitrages": [{"section": _sg_clip(a.get("section")),
                        "refs": [str(r) for r in a.get("refs", []) if isinstance(r, (str, int))],
                        "text": _sg_clip(a.get("text"))} for a in arbitrages],
        "truncated": truncated,
    }
