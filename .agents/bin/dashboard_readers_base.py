"""Part `base` of the `dashboard_readers.py` façade (T-00001051): closed vocabularies, bounds and primitives.
Moved byte for byte from that façade, which loads this file ONCE (`_load_part`); this file loads nothing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_readers_running_task_ids: Any  # injected by dashboard_readers.py before this part loads
_readers_dir_stats: Any  # injected likewise: (name, mtime_ns, size) per matching entry, sorted, read-only


# ---------------------------------------------------------------------------
# Closed vocabularies.
# ---------------------------------------------------------------------------

SECTION_STATUSES: tuple[str, ...] = (
    "ok", "no_events", "trail_absent", "unavailable", "degraded",
)

# The statuses under which the canal-A trail YIELDS NO MEASUREMENT, so a view
# must report the status instead of rendering counts. Named once (T-00000065)
# rather than repeated as a literal tuple at each of the four consumer sites:
# `unavailable` was added when the store became a source, and four tuples that
# have to be edited together are three chances to forget one — a view that
# missed it would render 0 deny / 0 call for an UNREADABLE database, which is
# the "a zero is a measurement, absence is not" rule inverted.
TRAIL_UNUSABLE: tuple[str, ...] = ("trail_absent", "degraded", "unavailable")

# ---------------------------------------------------------------------------
# MCP host configuration sources. Segment TUPLES of literals, joined onto the
# project root - the same "a request supplies a key, never a path" doctrine
# `dashboard._ALLOWED_STATIC_ROUTES` uses, applied to a table that is not even
# request-reachable. The four paths are exactly the four `protect-paths` and
# `permissions.deny` guard (AGENTS.md, MCP section).
# ---------------------------------------------------------------------------

MCP_CONFIG_SOURCES: tuple[dict[str, Any], ...] = (
    {"host": "claude", "segments": (".mcp.json",), "format": "json", "servers_key": "mcpServers"},
    {"host": "copilot", "segments": (".vscode", "mcp.json"), "format": "json", "servers_key": "servers"},
    {"host": "codex", "segments": (".codex", "config.toml"), "format": "toml", "servers_key": "mcp_servers"},
    {"host": "gemini", "segments": (".gemini", "settings.json"), "format": "json", "servers_key": "mcpServers"},
)

# ---------------------------------------------------------------------------
# Files whose (mtime_ns, size) make up the memoisation fingerprint. The board
# contributes only its sorted running IDs, which affect chrono ordering. A file
# absent from disk contributes a distinguishable "absent" marker.
# ---------------------------------------------------------------------------

_LEDGER_REL = (".agents", "state", "memory", "LEDGER.json")
_SPECS_REL = (".agents", "state", "specs", "SPECS.json")
_TASKS_REL = (".agents", "state", "board", "TASKS.json")
# Les formes ENREGISTREMENT (T-01M4KKMY43ZKCW1YD2Y8JX9MKH) : le journal SPECS, les dossiers du ledger et du board, et
# les intents O2 du board (un lease du pont réécrit son fichier, rien d'autre).
_SPECS_JOURNAL_REL = (".agents", "state", "specs", "SPECS.jsonl")
_LEDGER_ENTRIES_REL = (".agents", "state", "memory", "entries")
_BOARD_RECORD_DIRS_REL = tuple((".agents", "state", "board", d) for d in ("tasks", "epics", "sync_outbox"))
_INDEX_MD_REL = (".agents", "state", "index", "CODEBASE_INDEX.md")
_INDEX_DELTA_REL = (".agents", "state", "index", "INDEX_DELTA.json")
# T-00000379 lot E — l'artefact du graphe de specs. Meme repertoire que
# l'index parce que c'est la meme nature : un DERIVE des stores, publie par
# `.agents/bin/specs_graph.py` ou a la main par le projet. Son ABSENCE est un
# etat de repos legitime, jamais une degradation.
_SPECS_GRAPH_REL = (".agents", "state", "index", "SPECS_GRAPH.json")
_VERDICT_REL = (".agents", "state", "local", "sca-reports", "effective-verdict.json")
_RATES_REL = (".agents", "ref", "MODEL_RATES.json")
_AUDIT_LOG_JSONL_REL = (".agents", "state", "local", "sca-reports", "audit-log.jsonl")
_WAIVERS_REL = (".agents", "security", "sca-waivers.json")
_ALLOWLIST_REL = (".agents", "state", "gates", "MCP_ALLOWLIST.md")
_SKILLS_AUDIT_LOG_REL = (".agents", "state", "gates", "AUDIT_LOG")

_VIEW_SOURCE_FILES: tuple[tuple[str, ...], ...] = (
    _LEDGER_REL, _SPECS_REL, _SPECS_JOURNAL_REL, _INDEX_MD_REL, _INDEX_DELTA_REL, _VERDICT_REL,
    _AUDIT_LOG_JSONL_REL, _WAIVERS_REL, _ALLOWLIST_REL, _SKILLS_AUDIT_LOG_REL,
    _SPECS_GRAPH_REL,
) + tuple(source["segments"] for source in MCP_CONFIG_SOURCES)

_CLIP_MARKER = "...<clipped>"

# Bounds on every unbounded list that reaches the payload. The route is polled
# every 5 s; an unbounded "recent" list grows with the age of the stream.
_RECENT_LIMIT = 20
_DAY_SERIES_LIMIT = 30
_SAMPLE_LIMIT = 20
_SPECS_PER_TASK_LIMIT = 20
# Bornes du contrat SPECS_GRAPH (.agents/ref/SPECS_GRAPH_CONTRACT.md). Le
# generateur les applique DEJA de son cote, pour qu'un artefact genere ne
# rende jamais tronque ; elles sont re-appliquees ICI parce qu'une
# publication MANUELLE ne passe par aucun generateur.
_SPECS_GRAPH_NODES_LIMIT = 200
_SPECS_GRAPH_EDGES_LIMIT = 600
_SPECS_GRAPH_DECISIONS_LIMIT = 60
_SPECS_GRAPH_ARBITRAGES_LIMIT = 120
_SPECS_GRAPH_TEXT_CLIP = 240
_SHORT_CLIP = 200
_PREVIEW_CLIP = 160


# ---------------------------------------------------------------------------
# Primitives — the ONE JSONL reader, and the fingerprint helpers.
# ---------------------------------------------------------------------------

def read_new_records(path: Path, start_offset: int) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    """Read `path` from `start_offset` to EOF, but only ever PARSE up to the
    rightmost `b"\\n"` in what was read (shard-1 non-negotiable #2 - a line
    without its trailing newline yet is a write in flight, never touched).
    Returns `(records, malformed_count)` where each record is
    `(end_offset, dict)` - `end_offset` is the absolute byte position
    immediately after that record's line, i.e. the exact next seek position if
    this record is the last one a caller decides to keep for this file this
    poll.

    MOVED here from `dashboard.py` (T-00000026 shard A) so canal A and
    `sca-reports/audit-log.jsonl` share one reader instead of two;
    `dashboard._read_new_records` is now an alias of this function, so every
    prior call site and test is unaffected."""
    try:
        with open(path, "rb") as fh:
            fh.seek(start_offset)
            chunk = fh.read()
    except OSError:
        return [], 0
    if not chunk:
        return [], 0
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        return [], 0  # only a partial trailing line available - leave it alone
    consumable = chunk[:last_nl + 1]
    # `consumable` always ends with b"\n" by construction, so split(b"\n")'s
    # final element is always the empty trailing artifact of that fact, not
    # a real line - dropped explicitly rather than counted.
    parts = consumable.split(b"\n")[:-1]
    records: list[tuple[int, dict[str, Any]]] = []
    malformed = 0
    pos = start_offset
    for raw_line in parts:
        pos += len(raw_line) + 1  # +1 for the b"\n" this split consumed
        if not raw_line:
            continue  # a legitimate blank line - consumed, nothing to parse
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed += 1
            continue
        if isinstance(record, dict):
            records.append((pos, record))
        else:
            malformed += 1
    return records, malformed


def read_jsonl_file(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Whole-file convenience over `read_new_records` (offset 0). Same
    read-to-the-last-newline guarantee; a trailing partial line is skipped,
    not counted as malformed."""
    records, malformed = read_new_records(path, 0)
    return [record for _offset, record in records], malformed


def dir_fingerprint(directory: Path | None, pattern: str = "*.jsonl") -> tuple:
    """`(name, mtime_ns, size)` per matching file, sorted. Unreadable entries
    are skipped rather than raised on - this is a cache key, not a contract.
    Le relevé lui-même est la poignée injectée `_readers_dir_stats` (os.scandir, lecture seule)."""
    if directory is None:
        return ()
    return _readers_dir_stats(directory, pattern)


def _file_fingerprint(path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError:
        return ("absent", None, None)
    return ("present", stat.st_mtime_ns, stat.st_size)


def _git_head_fingerprint(project_root: Path) -> tuple:
    sha, source, reason = git_head_sha(project_root)
    return (sha, source, reason is None)


def _board_fingerprint(project_root: Path) -> tuple:
    """L'empreinte STAT du board, ses deux formes : TASKS.json et les dossiers d'enregistrements. Calculée UNE fois
    par appel d'empreinte : elle clé le mémo des ids running ET entre telle quelle dans `snapshot_fingerprint`."""
    return (_file_fingerprint(project_root.joinpath(*_TASKS_REL)),
            tuple(dir_fingerprint(project_root.joinpath(*rel), "*.json") for rel in _BOARD_RECORD_DIRS_REL))


# Les ids running ne se relisent (board entier chargé et validé, ~100 ms sur 1 900 tâches) que quand l'empreinte
# stat du board bouge : l'empreinte est sondée toutes les 0,5 s par flux ouvert (dashboard.py, contrat « Cheap »).
# Le stat précède la lecture : un enregistrement écrit entre les deux change la clé, et l'appel suivant relit.
_running_memo: dict[str, Any] = {"cle": None, "ids": ()}


def _running_ids_memo(project_root: Path, board_fp: tuple) -> tuple:
    cle = (str(project_root), board_fp)
    if _running_memo["cle"] != cle:
        _running_memo["ids"] = tuple(sorted(_readers_running_task_ids(project_root)))
        _running_memo["cle"] = cle
    return _running_memo["ids"]


def views_fingerprint(project_root: Path, events_dir: Path | None, otel_dir: Path | None,
                      store_fingerprint: tuple = ()) -> tuple:
    return _views_fingerprint(project_root, events_dir, otel_dir, store_fingerprint, _board_fingerprint(project_root))


def _views_fingerprint(project_root: Path, events_dir: Path | None, otel_dir: Path | None,
                       store_fingerprint: tuple, board_fp: tuple) -> tuple:
    """Full input set of `build_views`. The resolved PATHS are part of the
    key, which is what makes the module-level cache safe when two project
    trees are read in one process (pytest).

    `store_fingerprint` (T-00000049) is the SQLite projection's own
    `(path, present, mtime_ns, size)`, supplied by `dashboard.py`. It matters
    because an ingest tick can change what a view should say WITHOUT changing
    the spool directory — folding retention into the digests table touches only
    the database. Defaults to `()` so every pre-existing caller is unaffected."""
    return (
        str(project_root),
        tuple(("/".join(rel), *_file_fingerprint(project_root.joinpath(*rel)))
              for rel in _VIEW_SOURCE_FILES),
        str(events_dir) if events_dir is not None else None,
        dir_fingerprint(events_dir),
        str(otel_dir) if otel_dir is not None else None,
        dir_fingerprint(otel_dir),
        _git_head_fingerprint(project_root),
        tuple(store_fingerprint),
        dir_fingerprint(project_root.joinpath(*_LEDGER_ENTRIES_REL), "*.json"),
        # start, fournee, retour, done et review-scope (et chrono begin/step)
        # écrivent le journal task-chrono ; block
        # retire un ID running sans jalon. Unblock remet à pending et laisse
        # cette clé stable ; le prochain start réintroduit l'ID running.
        dir_fingerprint(project_root / ".agents" / "state" / "local" / "task-chrono"),
        _running_ids_memo(project_root, board_fp),
    )


def snapshot_fingerprint(project_root: Path, events_dir: Path | None, otel_dir: Path | None,
                         store_fingerprint: tuple = ()) -> tuple:
    """Everything `/api/snapshot` reads — the view inputs plus board records.
    Used by `/api/stream` to emit `snapshot_changed`."""
    board_fp = _board_fingerprint(project_root)
    return (
        _views_fingerprint(project_root, events_dir, otel_dir, store_fingerprint, board_fp),
        board_fp[0],
        dir_fingerprint(events_dir.joinpath("digest"), "*.json") if events_dir is not None else (),
        board_fp[1],
    )


def git_head_sha(project_root: Path) -> tuple[str | None, str | None, str | None]:
    """`(sha, source, reason)` for HEAD, read from git's own on-disk refs — no
    subprocess (see module docstring). `reason` is non-None exactly when `sha`
    is None. Handles a detached HEAD, a symbolic ref, `packed-refs`, and a
    `.git` FILE carrying a `gitdir:` indirection (worktree / submodule)."""
    git = project_root / ".git"
    try:
        if git.is_file():
            raw = git.read_text(encoding="utf-8").strip()
            if not raw.startswith("gitdir:"):
                return None, None, ".git is a file but carries no `gitdir:` indirection"
            candidate = Path(raw.split(":", 1)[1].strip())
            git = candidate if candidate.is_absolute() else (project_root / candidate)
        if not git.is_dir():
            return None, None, "no .git directory - this project root is not a git work tree"
        head_raw = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError as exc:
        return None, None, f"HEAD unreadable: {type(exc).__name__}"
    if not head_raw.startswith("ref:"):
        # Detached HEAD - the file holds the sha itself.
        return head_raw, ".git/HEAD (detached)", None
    ref = head_raw.split(":", 1)[1].strip()
    # CONTAINMENT (security review D4, MEDIUM): the ref name comes from a file
    # on disk, and its value is echoed over HTTP as `head_sha`. A tampered or
    # malformed ref carrying `..` segments would otherwise make this read — and
    # publish — an arbitrary local file. Requires prior write access to .git
    # internals, so not reachable from the HTTP surface, but a reader that
    # publishes what it reads has no business resolving outside its own tree.
    if ".." in ref.split("/") or ref.startswith("/") or "\\" in ref or ":" in ref:
        return None, None, f"HEAD points at a ref name this reader refuses to resolve: {ref[:60]!r}"
    try:
        git_resolved = git.resolve()
        loose = git.joinpath(*ref.split("/"))
        if loose.resolve().is_relative_to(git_resolved) and loose.is_file():
            return loose.read_text(encoding="utf-8").strip(), f".git/{ref}", None
    except (OSError, ValueError):
        pass
    try:
        packed = (git / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return None, None, f"{ref} has no loose ref file and packed-refs is unreadable"
    for line in packed.splitlines():
        if line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip() == ref:
            return parts[0].strip(), f".git/packed-refs ({ref})", None
    return None, None, f"{ref} found neither as a loose ref nor in packed-refs"


def _clip(value: Any, cap: int) -> Any:
    if not isinstance(value, str) or len(value) <= cap:
        return value
    return value[:cap] + _CLIP_MARKER


def _day_of(record: dict[str, Any]) -> str | None:
    stamp = record.get("ts")
    if isinstance(stamp, str) and len(stamp) >= 10:
        return stamp[:10]
    return None


def _bump(table: dict[str, int], key: str) -> None:
    table[key] = table.get(key, 0) + 1


def _percentile(sorted_values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile on an already-sorted list. Deliberately not an
    interpolating variant: with the handful of samples an MCP call log holds,
    an interpolated p95 invents a latency nobody measured."""
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, round(fraction * (len(sorted_values) - 1))))
    return sorted_values[index]
