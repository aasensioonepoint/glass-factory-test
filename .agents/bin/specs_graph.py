#!/usr/bin/env python3
"""Default specs graph — derive `.agents/state/index/SPECS_GRAPH.json` from the
three tracked state stores, so the dashboard's `#/specs` view works on any
project that uses the kit, without a hand-published artifact (T-00000379 lot E).

ADOPTED FROM `op-agentic-builder-kit`, GENERATOR VERBATIM, PAGE REFUSED. Their
kit lost the React source of its bundle, so their specs page is HAND-WRITTEN
outside it, with manual patches to `index.html` and `app.css` that their own
contract lists as debt to re-apply on any rebuild. We do not have that defect:
`.agents/ui-src/` is the maintained source and `vite.config.js` empties `../ui`
on every build. Their four hand-written files (`specs.html`, `assets/specs.js`,
`assets/specs.css`, `assets/nav.js`) are therefore NOT taken — a workaround for
a lost source is a defect of theirs, not a gap of ours. The page enters as a
route of the SPA, built from source like every other view.

WHAT THIS IS. The specs-graph contract (`.agents/ref/SPECS_GRAPH_CONTRACT.md`)
lets a project publish a deterministic JSON artifact that the dashboard renders
as a radial decision graph. Publishing by hand is still the richest path — a
project that owns a structured spec corpus (epics, DEC-NN.k decisions) can map
it 1:1. But a project that only uses the kit's own machinery ALREADY accumulates
graph-shaped data: the board (`TASKS.json`), the per-task journal (`SPECS.json`,
kinds plan/verdict/delta/decision) and the ledger (`LEDGER.json`, decisions and
constraints). This tool projects those three stores into the contract shape, so
the page lights up "au fur et à mesure" of the project instead of staying dark
until someone writes an artifact by hand.

PRECEDENCE — a hand-published artifact ALWAYS wins. Every file this tool writes
carries a top-level ``"generator": "specs_graph.py v1"`` marker (the dashboard
reader ignores unknown fields). ``generate`` writes only when the target is
absent or carries that marker; a file WITHOUT the marker — including one that no
longer parses as JSON, which may be a hand-publication mid-edit — is preserved
and reported, never overwritten (``--force`` is the explicit human override).
This keeps the contract's opt-in story intact: the kit still never parses a
project's own spec sources; it reads only its own state.

MAPPING (documented in the contract file, kept in sync by hand):

- node        = one board task (+ one synthetic node per task id referenced by
                journal entries but absent from the board — real work must not
                vanish from the graph because its board row was purged);
- release     = ring by state: done R0 (center: acquired) / running R1 /
                blocked R2 / pending R3 (rim) — the center grows as the
                project progresses;
- decisions   = journal entries of the task: kind=decision -> "prise";
                plan/verdict -> "en_analyse" while the task is open, "prise"
                once it is done (an open question on a closed task is closed);
                deltas are activity, not decisions — they size the node instead;
                active ledger decisions related to the task -> "prise";
                a blocked task synthesizes ONE "a_prendre" item from its stage
                (AGENTS.md: blocked == waiting on a human decision);
- edges       = cross-citations: a journal or ledger text that names another
                task id links the two nodes; weight = citation count;
- arbitrages  = active ledger constraints related to a task on the graph.

Task identity is the IDENTITY KEY of tasks.py (`identity_key`, T-00000726): a
legacy id by its NUMBER — `T-1`, `T-001` and `T-00000001` are the same task, so a
citation's zero-padding never forks a node — and a `T-<ULID>` by its exact
26-symbol body, so a ULID whose tail is digits never merges with the legacy task
of that number.

Bounds are applied HERE, generator-side, at the same values the dashboard
reader enforces (200 nodes / 600 edges / 60 decisions per node / 120
arbitrages / 240-char texts), so a generated artifact never renders with
"graphe tronqué" warnings; anything dropped is SAID on stdout AND recorded in
the artifact's top-level ``notes`` field (the reader ignores unknown fields) —
the automated callers discard stdout, the artifact keeps the trace. Node order
feeds the reader's first-200 cut: running, blocked, pending, done — NEWEST
first within each state, same priority as the board view (every `T-<ULID>` is
newer than every legacy id; ULIDs among themselves by minting time) — so when
the cap bites, the oldest tasks of the least-priority state present go first.

The generator is IDEMPOTENT: when the target already carries the marker and
the graph is unchanged (everything but ``generated_at`` equal), nothing is
rewritten — a tracked artifact does not go dirty at every session start, and
committing it stays a project choice with no churn penalty, like the index.

WHERE THIS RUNS AUTOMATICALLY, and where it does NOT. One trigger is wired:
`.agents/bin/post-task-done-index.sh` refreshes the graph after each
`tasks.py … done`, on the four hosts that register that hook (Claude Code,
Codex, Copilot, Kimi Code) — advisory, exit 0 whatever happens, and it inherits the
never-overwrite rule above. The upstream kit also wires `session-start.sh`; we
do NOT, and the reason is measured rather than an omission: our session-start
already runs the board injection, the ledger context and a guarded index
rebuild, and a fourth store-walking pass at every session start buys a refresh
that the closure hook has already produced. A project that wants the bootstrap
runs `specs_graph.py generate` once by hand.

The consequence is stated instead of implied: on a repository where no task has
been closed since this landed, the artifact is ABSENT, the view answers
`no_events`, and the SPA hides its nav entry. That is the contract's rest
state, not a failure.

CLI::

    python specs_graph.py generate            # create if absent, refresh if kit-generated
    python specs_graph.py generate --force    # overwrite even a hand-published artifact
    python specs_graph.py generate --stdout   # print the artifact, write nothing
    python specs_graph.py status              # absent | manuel | généré (+ counts)

Exit code is 0 unless a store is malformed (their own loaders validate hard and
raise — a broken board must fail loudly, not render as an empty graph).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The three store CLIs own their schemas and validation; this tool deliberately
# IMPORTS their loaders instead of duplicating read logic the way the (fail-soft)
# dashboard readers do — the generator wants their exact fail-LOUD semantics,
# with zero drift when a store schema evolves. They live in this same directory
# on every host and in every consumer project (template sync ships .agents/bin/
# wholesale), so a plain sibling import is the stable path. The three stores are
# READ through `etat_lecture`, the common reading interface, imported as a public
# sibling like its owners: it resolves the public siblings imported here (for the
# board, `__main__` first when it is the tasks.py facade), so the error classes
# caught in `main` are those its readers raise.
_BIN_DIR = str(Path(__file__).resolve().parent)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import etat_lecture  # noqa: E402
import ledger  # noqa: E402,F401  (owner of the ledger, resolved by etat_lecture)
import specs  # noqa: E402
import tasks  # noqa: E402

ARTIFACT_REL = Path(".agents") / "state" / "index" / "SPECS_GRAPH.json"
CONTRACT_REL = ".agents/ref/SPECS_GRAPH_CONTRACT.md"

# The marker that distinguishes a kit-generated artifact from a hand-published
# one. Presence (prefix-matched) authorizes refresh; absence forbids overwrite.
GENERATOR_NAME = "specs_graph.py"
GENERATOR_VALUE = "specs_graph.py v1"

# Same bounds as dashboard_readers.py (_SPECS_GRAPH_*_LIMIT): applied here so a
# generated artifact renders whole, without reader-side truncation flags.
MAX_NODES = 200
MAX_EDGES = 600
MAX_DECISIONS_PER_NODE = 60
MAX_ARBITRAGES = 120
TEXT_CLIP = 240

# Closed status vocabulary of the contract; RING maps the board's closed state
# vocabulary onto the contract's layout rings (R0 center -> R3 rim).
PRISE, EN_ANALYSE, A_PRENDRE, PRISE_A_CLORE = "prise", "en_analyse", "a_prendre", "prise_a_clore"
RING = {"done": "R0", "running": "R1", "blocked": "R2", "pending": "R3"}

# A task citation inside prose: `T-` + digits or a `T-<ULID>` (T-00000726), not
# embedded in a longer word or id — `RT-12`, `T-12a` and `DEC-T-1x` never count,
# while a branch-style suffix (`feat/T-00000008-specs-graph-view`) still cites its
# task. The ULID alternative comes FIRST and the ULID body is the one tasks.py
# reads (`tasks.ULID_BODY`): a malformed ULID (25 symbols, lower case) cites
# nothing at all — never its leading digits (`T-01`).
TASK_REF_RE = re.compile(r"(?<![\w-])T-(" + tasks.ULID_BODY + r"|\d+)(?![A-Za-z\d])")
# A whole task id, same two alternatives, ULID first.
_TASK_ID_RE = re.compile(r"T-(?:(" + tasks.ULID_BODY + r")|(\d+))")

_STATE_ORDER = {"running": 0, "blocked": 1, "pending": 2, "done": 3}


class SpecsGraphError(Exception):
    """A store failed validation, or the target artifact cannot be written."""


def force_utf8_stdio() -> None:
    """Windows consoles default to cp1252; the artifact and every message here
    are UTF-8 by construction — same rationale as specs.py/tasks.py/ledger.py."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace", newline="\n")


def artifact_path(root: str | os.PathLike[str]) -> Path:
    return Path(root) / ARTIFACT_REL


def clip(text: str, width: int = TEXT_CLIP) -> str:
    text = " ".join((text or "").split())
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def _task_num(task_id: str) -> tuple[int, int | str] | None:
    """IDENTITY key of a task id, the value `tasks.identity_key` gives (T-00000726):
    ``(0, n)`` for a legacy `T-NNN` — `T-1`, `T-001` and `T-00000001` are the SAME
    task (tasks.py enforces numeric-collision uniqueness on the board) — and
    ``(1, ulid)`` for a `T-<ULID>`, by its exact body, so `T-<ULID ending in 2>` is
    NOT `T-00000002`. The graph keys nodes on it and keeps the store's spelling
    for display. Computed HERE for journal and ledger ids rather than through
    `tasks.identity_key`, whose legacy branch caps at 15 digits: specs.py accepts
    an unbounded `T-\\d+`, and the graph must too. Returns ``None`` for anything
    else instead of raising: loader-valid data must never freeze the whole graph
    (the hooks discard stderr, so an exception here would silence refresh
    forever) — the caller skips the one datum, with a note."""
    match = _TASK_ID_RE.fullmatch(task_id or "")
    if not match:
        return None
    return (1, match.group(1)) if match.group(1) is not None else (0, int(match.group(2)))


def _cited_tasks(text: str) -> set[tuple[int, int | str]]:
    cited = (_task_num("T-" + m.group(1)) for m in TASK_REF_RE.finditer(text or ""))
    return {key for key in cited if key is not None}


def build_graph(root: str | os.PathLike[str]) -> tuple[dict[str, Any] | None, list[str]]:
    """Project the three stores into the contract shape.

    Returns ``(artifact, notes)`` — ``artifact`` is ``None`` when there is
    nothing to publish (no task, no journal entry): absence stays the
    contract's legitimate `no_events` rest state, an EMPTY graph is never
    published in its place. ``notes`` names whatever a bound dropped, because a
    silent cap reads as "covered everything" when it didn't.
    """
    board = etat_lecture.taches(root)
    journal = etat_lecture.entrees_specs(root)
    memory = etat_lecture.entrees_ledger(root)
    notes: list[str] = []

    # ledger `related` is validated on ADD (T-\d+ or T-<ULID>) but NOT on load —
    # a store migrated by hand may carry e.g. "T-2,T-3". One malformed
    # rattachement must cost that one entry, never the graph: resolve them all
    # up front, note the rejects once, and treat them as unrelated below.
    ledger_rel: dict[str, tuple[int, int | str]] = {}
    for entry in memory:
        if not entry["related"]:
            continue
        rel = _task_num(entry["related"])
        if rel is None:
            notes.append(
                f"{entry['id']}: related {entry['related']!r} hors format T-NNN / T-<ULID> — rattachement ignoré"
            )
            continue
        ledger_rel[entry["id"]] = rel

    # --- nodes: board tasks + journal-only (synthetic) tasks ----------------
    # Keyed on the IDENTITY key (`by_num` keeps its name): a board row passed
    # `tasks.load`, so `tasks.identity_key` keys it — a `T-<ULID>` by its body,
    # never re-keyed on its trailing digits, never raising (T-00000726).
    by_num: dict[tuple[int, int | str], dict[str, Any]] = {}
    for row in board:
        num = tasks.identity_key(row["id"])
        by_num[num] = {
            "id": row["id"],
            "num": num,
            "title": clip(row["task"]),
            "state": row["state"],
            "updated": row.get("updated", ""),
            "stage": row.get("stage", ""),
            "entries": [],
            "decisions": [],
            "counts": {},
        }
    for entry in specs.sorted_entries(journal):
        # specs.load admits `T-\d+` or `T-<ULID>` (specs._TASK_ID) and `_task_num`
        # keys both: None only for a store that bypassed the loader — skipped.
        num = _task_num(entry["task"])
        if num is None:
            continue
        if num not in by_num:
            # Journal references a task the board no longer carries (purged or
            # never registered). The work happened — keep it visible on the rim
            # rather than dropping entries on the floor.
            by_num[num] = {
                "id": entry["task"],
                "num": num,
                "title": clip(entry["title"]),
                "state": "pending",
                "updated": entry.get("date", ""),
                "stage": "",
                "entries": [],
                "decisions": [],
                "counts": {},
            }
            notes.append(f"{entry['task']} cité par le journal mais absent du board — nœud synthétique")
        by_num[num]["entries"].append(entry)

    if not by_num:
        return None, notes

    # --- decisions per node --------------------------------------------------
    def add_decision(node: dict[str, Any], did: str, status: str, q: str, when: str) -> None:
        item: dict[str, Any] = {"id": did, "status": status, "q": clip(q)}
        if when:
            item["date"] = when
        node["decisions"].append(item)
        node["counts"][status] = node["counts"].get(status, 0) + 1

    for node in by_num.values():
        closed = node["state"] == "done"
        for entry in node["entries"]:
            q = entry["title"] if not entry.get("text") else f"{entry['title']} — {entry['text']}"
            if entry["kind"] == "decision":
                add_decision(node, entry["id"], PRISE, q, entry["date"])
            elif entry["kind"] in ("plan", "verdict"):
                add_decision(node, entry["id"], PRISE if closed else EN_ANALYSE, q, entry["date"])
            # deltas are activity, not decisions — they only size the node below

    for entry in memory:
        if entry["category"] != "decision" or entry["status"] != "active":
            continue
        num = ledger_rel.get(entry["id"])
        if num is None or num not in by_num:
            continue
        node = by_num[num]
        q = entry["title"] if not entry.get("text") else f"{entry['title']} — {entry['text']}"
        add_decision(node, entry["id"], PRISE, q, entry["created"])

    for node in by_num.values():
        if node["state"] == "blocked":
            reason = node["stage"] or "raison non renseignée"
            add_decision(
                node,
                f"{node['id']}#blocage",
                A_PRENDRE,
                f"Arbitrage humain attendu — {reason}",
                node["updated"],
            )

    # --- edges: cross-citations, keyed on identity-key pairs -----------------
    Key = tuple[int, int | str]
    weights: dict[tuple[Key, Key], int] = {}
    directions: dict[tuple[Key, Key], tuple[Key, Key]] = {}

    def cite(src: Key, text: str) -> None:
        for dst in _cited_tasks(text):
            if dst == src or src not in by_num or dst not in by_num:
                continue
            key = (min(src, dst), max(src, dst))
            weights[key] = weights.get(key, 0) + 1
            directions.setdefault(key, (src, dst))

    for entry in journal:
        src = _task_num(entry["task"])
        if src is not None:
            cite(src, f"{entry['title']} {entry.get('text', '')}")
    for entry in memory:
        if entry["status"] == "active" and entry["id"] in ledger_rel:
            cite(ledger_rel[entry["id"]], f"{entry['title']} {entry.get('text', '')}")

    # --- arbitrages: active constraints anchored to a graphed task -----------
    arbitrages = [
        {
            "section": entry["id"],
            "refs": [by_num[ledger_rel[entry["id"]]]["id"]],
            "text": clip(entry["title"] if not entry.get("text") else f"{entry['title']} — {entry['text']}"),
        }
        for entry in memory
        if entry["category"] == "constraint"
        and entry["status"] == "active"
        and ledger_rel.get(entry["id"]) in by_num
    ]

    # --- bounds (reader values, applied here so nothing renders truncated) ---
    # Priority mirrors the board view: active states before done, NEWEST first
    # within each state — so the cap drops the oldest tasks of the last state
    # present, never the recent open work. TWO passes, because the identity key
    # is a tuple and cannot be negated (T-00000726): newest first on the key —
    # every ULID before every legacy id —, then a STABLE sort on the state order
    # keeps that order within each state.
    ordered = sorted(by_num.values(), key=lambda n: n["num"], reverse=True)
    ordered.sort(key=lambda n: _STATE_ORDER.get(n["state"], 2))
    if len(ordered) > MAX_NODES:
        notes.append(
            f"{len(ordered) - MAX_NODES} nœud(s) au-delà de la borne de {MAX_NODES} — "
            "conservation par priorité (running, blocked, pending, done ; récents d'abord), "
            "les plus anciens du dernier état omis"
        )
        ordered = ordered[:MAX_NODES]
    kept_nums = {n["num"] for n in ordered}
    num_of = {node["id"]: num for num, node in by_num.items()}

    for node in ordered:
        if len(node["decisions"]) > MAX_DECISIONS_PER_NODE:
            dropped = len(node["decisions"]) - MAX_DECISIONS_PER_NODE
            notes.append(
                f"{node['id']}: {dropped} décision(s) au-delà de la borne de {MAX_DECISIONS_PER_NODE} — plus anciennes omises"
            )
            # counts stay on the FULL tally: the number is true even when the
            # list is bounded, same doctrine as the sample's stats block.
            node["decisions"] = node["decisions"][-MAX_DECISIONS_PER_NODE:]

    edge_rows = sorted(
        (
            {
                "source": by_num[directions[key][0]]["id"],
                "target": by_num[directions[key][1]]["id"],
                "weight": weight,
            }
            for key, weight in weights.items()
            if key[0] in kept_nums and key[1] in kept_nums
        ),
        key=lambda e: (-e["weight"], num_of[e["source"]], num_of[e["target"]]),
    )
    if len(edge_rows) > MAX_EDGES:
        notes.append(f"{len(edge_rows) - MAX_EDGES} arête(s) au-delà de la borne de {MAX_EDGES} — plus faibles omises")
        edge_rows = edge_rows[:MAX_EDGES]

    arbitrages = [a for a in arbitrages if num_of[a["refs"][0]] in kept_nums]
    if len(arbitrages) > MAX_ARBITRAGES:
        notes.append(
            f"{len(arbitrages) - MAX_ARBITRAGES} arbitrage(s) au-delà de la borne de {MAX_ARBITRAGES} — plus anciens omis"
        )
        arbitrages = arbitrages[-MAX_ARBITRAGES:]

    # --- assemble -------------------------------------------------------------
    stats: dict[str, int] = {PRISE: 0, PRISE_A_CLORE: 0, A_PRENDRE: 0, EN_ANALYSE: 0}
    nodes_out = []
    for node in ordered:
        for status_name, count in node["counts"].items():
            stats[status_name] = stats.get(status_name, 0) + count
        nodes_out.append(
            {
                "id": node["id"],
                "title": node["title"],
                "release": RING.get(node["state"], "R3"),
                "size": {"tasks": max(1, len(node["entries"]))},
                "counts": node["counts"],
                "decisions": node["decisions"],
            }
        )
    stats_out = {"decisions": sum(stats.values()), **stats}

    artifact = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": GENERATOR_VALUE,
        "title": f"{Path(root).resolve().name} — tâches & décisions du kit",
        "source": ".agents/state (TASKS.json, SPECS.json, LEDGER.json)",
        "stats": stats_out,
        "nodes": nodes_out,
        "edges": edge_rows,
        "arbitrages": arbitrages,
    }
    if notes:
        # The automated callers (hooks) discard stdout — the artifact itself
        # keeps the trace of everything a bound or a skip dropped. The reader
        # ignores unknown top-level fields, so this costs nothing at render.
        artifact["notes"] = notes
    return artifact, notes


def published_state(path: Path) -> str:
    """``absent`` | ``generated`` | ``manual``. Anything unreadable or without
    the generator marker is ``manual``: when in doubt, the file is somebody's
    publication and this tool has no business replacing it."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "absent"
    except OSError:
        # Unreadable is NOT absent: a permission-broken, locked, or
        # cloud-dehydrated file EXISTS and may be somebody's hand publication.
        # Classifying it "absent" would let generate() write over it without
        # --force — the exact inversion of the precedence rule (measured:
        # mode-000 file, directory at the path, OneDrive placeholder).
        return "manual"
    try:
        data = json.loads(raw)
    except ValueError:
        return "manual"
    generator = data.get("generator") if isinstance(data, dict) else None
    if isinstance(generator, str) and generator.startswith(GENERATOR_NAME):
        return "generated"
    return "manual"


# Same atomic-write recipe and Windows retry bound as every other publisher in
# the kit (specs.py, tasks.py, build_index.py — L-00000054): the dashboard
# daemon reads this artifact on every snapshot, so the concurrent reader is
# not hypothetical here either.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01


def _replace_with_retry(src: str | Path, target: str | Path) -> None:
    last: OSError | None = None
    for _ in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(_REPLACE_DELAY_SECONDS)
    assert last is not None
    raise last


def write_artifact(root: str | os.PathLike[str], artifact: dict[str, Any]) -> None:
    path = artifact_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".specs-graph-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n")
        os.chmod(tmp_name, 0o644)
        _replace_with_retry(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def generate(root: str | os.PathLike[str], force: bool = False, to_stdout: bool = False) -> str:
    """The one entry point hooks call. Never destroys a hand publication."""
    artifact, notes = build_graph(root)
    path = artifact_path(root)
    state = published_state(path)

    if to_stdout:
        if artifact is None:
            return "SPECS_GRAPH: rien à publier (aucune tâche, aucune entrée de journal)"
        return json.dumps(artifact, indent=2, ensure_ascii=False)

    if artifact is None:
        kept = " — l'artefact existant est conservé tel quel" if state != "absent" else ""
        return f"SPECS_GRAPH: rien à publier (aucune tâche, aucune entrée de journal){kept}"

    if state == "manual" and not force:
        return (
            f"SPECS_GRAPH: publication manuelle préservée ({path.as_posix()} sans marqueur "
            f"'{GENERATOR_NAME}') — --force pour écraser"
        )

    # Idempotence: an unchanged graph is not rewritten. Without this, every
    # session start and every task closure would stamp a fresh generated_at on
    # identical content — and a project that chose to TRACK the artifact would
    # see it dirty forever, the exact noise the store-commit hook exists to
    # avoid. --force stays a real overwrite, explicitly asked for.
    if state == "generated" and not force:
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
        if isinstance(previous, dict):
            prev, new = dict(previous), dict(artifact)
            prev.pop("generated_at", None)
            new.pop("generated_at", None)
            if prev == new:
                return (
                    f"SPECS_GRAPH: inchangé — {len(artifact['nodes'])} nœud(s), non réécrit "
                    f"(généré le {previous.get('generated_at', '?')})"
                )

    write_artifact(root, artifact)
    verb = {"absent": "publié", "generated": "rafraîchi"}.get(state, "écrasé (--force)")
    summary = (
        f"SPECS_GRAPH: {verb} — {len(artifact['nodes'])} nœud(s), {len(artifact['edges'])} arête(s), "
        f"{artifact['stats']['decisions']} décision(s)"
    )
    return "\n".join([summary] + [f"  note: {n}" for n in notes])


def status(root: str | os.PathLike[str]) -> str:
    path = artifact_path(root)
    state = published_state(path)
    if state == "absent":
        return f"SPECS_GRAPH: absent ({path.as_posix()}) — `specs_graph.py generate` le publiera depuis les stores"
    if state == "manual":
        return f"SPECS_GRAPH: publication manuelle (pas de marqueur '{GENERATOR_NAME}') — jamais écrasée sans --force"
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or []
    return (
        f"SPECS_GRAPH: généré par le kit le {data.get('generated_at', '?')} — "
        f"{len(nodes)} nœud(s), {len(data.get('edges') or [])} arête(s)"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate the default specs graph from the kit's state stores."
    )
    ap.add_argument("--root", default=os.environ.get("CLAUDE_PROJECT_DIR", "."))
    sub = ap.add_subparsers(dest="cmd")

    p_gen = sub.add_parser("generate", help="publish/refresh the graph (hand publications preserved)")
    p_gen.add_argument("--force", action="store_true", help="overwrite even a hand-published artifact")
    p_gen.add_argument("--stdout", action="store_true", help="print the artifact instead of writing it")

    sub.add_parser("status", help="say whether the artifact is absent, manual, or kit-generated")

    args = ap.parse_args(argv)
    force_utf8_stdio()

    try:
        if args.cmd == "generate":
            print(generate(args.root, force=args.force, to_stdout=args.stdout))
        elif args.cmd == "status":
            print(status(args.root))
        else:
            ap.print_help()
    except (SpecsGraphError, *etat_lecture.erreurs_de_lecture("board", "specs", "ledger"), OSError, ValueError) as exc:
        # The owners' error classes come from the interface that raised them
        # (resolved at the moment of the failure, the public siblings above).
        # OSError/ValueError last, most-specific first (CONVENTIONS_python.md):
        # a directory squatting the artifact path, a permission failure at
        # replace time, or a race re-reading the artifact must exit 2 with the
        # cause named — never a raw traceback out of a hook.
        print(f"specs_graph.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
