#!/usr/bin/env python3
"""Unified snapshot readers for the six remaining D4 views — Gouvernance,
Sécurité, Mémoire, Index, MCP, Couverture (T-00000026 shard A). stdlib only.

WHAT THIS MODULE IS: the READ side of `/api/snapshot`'s new `views` block.
`dashboard.py` owns the socket, the token, the route table and the frozen
`/api/*` contract; it calls `build_views()` once per snapshot and drops the
result under a single new top-level key. **No route was added for any of
these six views** — the payload grew, `_ALLOWED_UI_PATHS` gained exactly one
member (`/api/stream`, the SSE endpoint, which lives in `dashboard.py`
because it is transport, not reading).

ONE JSONL READER, NOT SIX (task scope, explicit): `read_new_records()` below
is the SAME tail-safe reader `dashboard.py` has always used for canal A —
moved here, not copied, and re-exported there as `_read_new_records` so every
existing call site and every existing test keeps working. It is now ALSO the
reader for `state/local/sca-reports/audit-log.jsonl`, which design doc §B.1
calls "le prototype de ce mécanisme : à absorber, pas à dupliquer". A second
JSONL parser for the security history would have been a second place for the
read-to-the-last-newline rule (non-negotiable #2 of the shard-1 docstring) to
rot out of sync. There is one.

STATUS IS A CLOSED VOCABULARY, AND ABSENCE IS NEVER ZERO. Every section
degrades INDEPENDENTLY (a section carries `status` + `reason`; a failure there
never reaches the HTTP layer) and every section distinguishes:
  - `ok`            — data was read
  - `no_events`     — the trail EXISTS and holds zero matching record. A
                      measurement: nothing was denied / nothing was waived.
  - `trail_absent`  — the trail does not exist (never written, or deleted).
                      NOT the same fact, and the design doc calls this out by
                      name for the governance view (§F.3: "la vue 4 doit
                      distinguer « aucun skill installé » de « trail perdu »").
  - `unavailable`   — the signal is structurally unobtainable today, with the
                      reason naming what is missing (an unwired emitter, a
                      class the source never tags).
  - `degraded`      — a read failed; the reason says how.
Collapsing the middle three into "empty" is the exact L-010 false-GO shape the
kit already refuses in its security gate, transposed into an observability
view: a zero that means "clean" and a zero that means "blind" must never
render the same.

SECURITY POSTURE (inherited, non-negotiable): this module opens files at
paths built from PROJECT ROOT + literal segment tuples declared as module
constants — never from a request byte, never from a value found inside a file
it read. It is read-only: no `open(..., "w")`, no `mkdir`, and no subprocess —
**with ONE named exception since T-00000575**: `_index_freshness` spawns git
TWICE, each bounded at 1.5 s (`cat-file -e` to prove the stamped sha is
reachable, then `diff --name-only <built_sha> HEAD`). Without that, an index was
declared stale by any commit at all, since every commit moves HEAD. The
exception is NAMED rather than silent because the sentence above is what a
reader trusts when budgeting this module inside the daemon's ping window. Two
specific redactions matter and are enforced by tests:
  - MCP host configs are read for PACKAGE IDENTITY ONLY. `env` values and the
    raw `args` list are NEVER surfaced — `mcp_render.py`'s own literal-secret
    scan exists precisely because an MCP arg or env value can be a live
    credential, and this payload leaves the process over HTTP. What ships is
    the config key, the command NAME, the package name, the pinned version
    and an ARG COUNT.
  - the security history surfaces `locations` as a COUNT, never as the list.
    gitleaks runs `--redact` so the list is already value-free, but a bounded
    counter is what a view needs and it keeps `file:line` inventories out of a
    100 Ko payload.

COST (task requirement, measured not asserted): `build_views()` is memoised on
a `(name, mtime_ns, size)` fingerprint over its ENTIRE input set — the same
mechanism `dashboard._read_canal_b` already uses, extended to the individual
files (`LEDGER.json`, `SPECS.json`, `INDEX_DELTA.json`, `sca-waivers.json`,
`audit-log.jsonl`, `MCP_ALLOWLIST.md`, the four host MCP configs, `.git/HEAD`
and its resolved ref) plus the two directories. An unchanged poll costs
`len(inputs)` `stat()` calls. The resolved paths are PART of the fingerprint,
which is what makes a module-level cache safe under pytest — one test's views
can never be served to another tree.

PAYLOAD DISCIPLINE: `/api/snapshot` already ships ~108 Ko, of which ~95 Ko is
the raw `ledger` + `specs` stores, and it is re-polled every 5 s. So the
Mémoire view deliberately does NOT copy those entries: it ships the ORDERING
and the GROUPING (active constraints first, full but text-clipped; everything
else as id + title), and a consumer joins on `id` against the store already
present in the same payload. Same reasoning for the coverage matrix: a cell is
`{status, count}` and the human-readable explanation of each status lives ONCE
in a section-level `legend`, not 100 times in 100 cells.

GIT WITHOUT SUBPROCESS — **EXCEPT THE TWO NAMED ABOVE (T-00000575)**, and this
paragraph used to promise the opposite forty lines below its own exception. HEAD
itself is still read WITHOUT a spawn; the PER-FILE measure spawns twice. The
Windows cost argued here is precisely what keeps that number at two: it is the
standing argument against a third.

Index freshness compares `INDEX_DELTA.json`'s
`built_sha` against HEAD. HEAD is read from `.git/HEAD` -> `.git/refs/...` ->
`.git/packed-refs` (and through a `gitdir:` indirection for a worktree or
submodule) rather than by spawning `git rev-parse`. Reason: this runs inside a
route whose warm budget is bounded by `dashboard_daemon._PING_TIMEOUT_SECONDS`
and a process spawn on Windows costs more than every other read in this module
combined. A HEAD that cannot be resolved degrades the FRESHNESS field alone,
with a reason — never the section, never the route.

T-00001051 — THIS FILE IS NOW A FAÇADE (the 1600-line rule, S-00002684, S-00004034). Everything said above holds for it
AND for each part listed in `PARTIES` (`dashboard_readers_*.py`): `read_new_records()` and the other primitives
live in `dashboard_readers_base.py`, each view reader lives in its own part, and this module re-exposes every
one of them under its own name. The ONE subprocess exception stays in THIS file: `_index_freshness` spawns git
twice, once via its private helper `_sha_joignable`. `test_dashboard_readers_decoupe.py` pins that no part spawns
a process and that neither this file nor a part writes a file, AMONG THE IDIOMS IT SCANS — not a general guarantee
— and that each part imports only from the stdlib whitelist `__future__ datetime json pathlib re tomllib typing`.
"""
from __future__ import annotations

import errno
import fnmatch
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Explicit-path module load — the same IMPORT CONTRACT `dashboard.py`,
    `events.py` and `dashboard_daemon.py` use, never a bare import that would
    depend on `sys.path[0]` resolving to this directory."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# The MCP allowlist parser, the npx package-pin extractor and the
# scoped-package `@` split are `mcp_render.py`'s, reused verbatim. Re-deriving
# them here would mean two definitions of "which package identity is audited"
# — the exact mismatch `mcp_render.py`'s own docstring refuses (a row for the
# config KEY does not authorise the real package).
_mcp_render = _load_sibling("_readers_mcp_render", "mcp_render.py")

# The index's coverage limit is DERIVED from the builder, never restated here
# (T-00000062): the scope now depends on the tree being read — a vendored kit also
# drops `.claude`/`.codex`/`.gemini` at its root — and a caveat that hardcodes one
# scope becomes the misleading kind of caveat the day the scope moves.
_build_index = _load_sibling("_readers_build_index", "build_index.py")
_task_chrono = None
_specs_chrono = None
_tasks_chrono = None


def _chrono_module():
    global _task_chrono
    if _task_chrono is None:
        _task_chrono = _load_sibling("_readers_task_chrono", "task_chrono.py")
    return _task_chrono


def _chrono_specs_module():
    global _specs_chrono
    if _specs_chrono is None:
        _specs_chrono = _load_sibling("_readers_specs_chrono", "specs.py")
    return _specs_chrono


def _chrono_tasks_module():
    global _tasks_chrono
    if _tasks_chrono is None:
        _tasks_chrono = _load_sibling("_readers_tasks_chrono", "tasks.py")
    return _tasks_chrono


def _running_task_ids(project_root: Path) -> set[str]:
    """Running IDs shared by the chrono ordering and the views cache key."""
    try:
        return {task["id"] for task in _chrono_tasks_module().load(project_root)["tasks"]
                if task["state"] == "running"}
    except Exception:  # noqa: BLE001 — an unreadable board leaves chronological ordering available
        return set()


# T-00001051 — LES PARTIES. Cinq fichiers chargés UNE fois chacun, par ce module, dans l'ordre de dépendance ; il leur
# INJECTE les poignées qu'ils déclarent (`nom: Any`), aucun n'en charge un autre. Liste fermée : elle nourrit
# `served_code_fingerprint`, `must_travel` et le banc `test_dashboard_readers_decoupe.py`.
PARTIES = (
    "dashboard_readers_base.py",
    "dashboard_readers_coverage_mcp.py",
    "dashboard_readers_governance.py",
    "dashboard_readers_security.py",
    "dashboard_readers_memory.py",
)


def _load_part(filename: str, **handles: Any):
    """`_load_sibling` plus l'injection : poignées posées AVANT `exec_module`, module enregistré avant lui."""
    if filename not in PARTIES:
        raise ValueError(f"{filename} n'est pas dans PARTIES")
    spec = importlib.util.spec_from_file_location("_readers_part_" + filename[len("dashboard_readers_"):-3], HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    for key, value in handles.items():
        setattr(mod, key, value)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _dir_stats(directory: Path, pattern: str) -> tuple:
    """`(name, mtime_ns, size)` des entrées de `directory` qui répondent à `pattern`, triées ; LECTURE SEULE.
    Même ensemble que `Path.glob(pattern)` (noms cachés compris, `fnmatch` à la casse du système), par
    `os.scandir` : 10,3 → 3,2 ms mesurés sur 1 878 enregistrements du board, sondés toutes les 0,5 s. Injecté
    dans la partie `base`, à qui la liste blanche d'imports refuse `os` (banc de découpe, test (l))."""
    entries: list[tuple[str, int, int]] = []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if not fnmatch.fnmatch(entry.name, pattern):
                    continue
                try:
                    etat = entry.stat()
                except OSError:
                    continue
                entries.append((entry.name, etat.st_mtime_ns, etat.st_size))
    except OSError:
        return ()
    entries.sort()
    return tuple(entries)


_readers_base = _load_part("dashboard_readers_base.py", _readers_running_task_ids=_running_task_ids,
                           _readers_dir_stats=_dir_stats)
_readers_coverage_mcp = _load_part("dashboard_readers_coverage_mcp.py",
                                   _readers_base=_readers_base, _mcp_render=_mcp_render)
_readers_governance = _load_part("dashboard_readers_governance.py",
                                 _readers_base=_readers_base, _readers_coverage_mcp=_readers_coverage_mcp)
_readers_security = _load_part("dashboard_readers_security.py", _readers_base=_readers_base)
_readers_memory = _load_part("dashboard_readers_memory.py", _readers_base=_readers_base)

# Ré-exposition : tout nom de tête d'une partie devient un nom de CE module, celui que lisent `dashboard.py`,
# `sca-watch.test.sh` et les bancs (`test_dashboard`, `test_event_store`, `test_specs_graph`, `test_tasks`).
# `setdefault` : un nom déjà ici (imports communs, poignées) garde SON objet ; chaque partie reçoit les MÊMES
# poignées, donc un nom présent dans deux fichiers est le même objet (témoins (c) et (d)).
for _part in (_readers_base, _readers_coverage_mcp, _readers_governance, _readers_security, _readers_memory):
    for _name, _value in vars(_part).items():
        if not (_name.startswith("__") and _name.endswith("__")):
            globals().setdefault(_name, _value)
del _part, _name, _value


# ---------------------------------------------------------------------------
# Canal-A stream — read ONCE per snapshot, shared by governance / MCP /
# coverage. Reading it three times would triple the only cost in this module
# that grows with the age of the repo.
# ---------------------------------------------------------------------------

_stream_cache: dict[str, Any] = {"fingerprint": None, "value": None}


def read_canal_a_stream(events_dir: Path | None) -> dict[str, Any]:
    """`{status, records, files, malformed, reason}` for the whole canal-A
    trail, MEMOISED on `(dir, dir_fingerprint)`.

    Why the memo lives here and not in each caller: `/api/snapshot` needs this
    stream TWICE per call - once for `dashboard._canal_a_prompt_index` (the
    canal-B join key index) and once for the governance / MCP / coverage views.
    On this repo that is 349 day-files, and reading them twice per poll was
    measured pushing the cold route past `dashboard_daemon`'s 2 s ping budget
    under full-suite contention (the flake class that module's own docstring
    already documents). One read, two consumers.

    The returned dict must be treated as READ-ONLY: an unchanged poll gets the
    same object, `records` list included."""
    fingerprint = (
        str(events_dir) if events_dir is not None else None,
        dir_fingerprint(events_dir),
    )
    if _stream_cache["fingerprint"] == fingerprint and _stream_cache["value"] is not None:
        return _stream_cache["value"]
    value = _read_canal_a_stream_uncached(events_dir)
    _stream_cache["fingerprint"] = fingerprint
    _stream_cache["value"] = value
    return value


def _read_canal_a_stream_uncached(events_dir: Path | None) -> dict[str, Any]:
    """The SPOOL read. Never raises. Distinguishes an ABSENT trail (the
    directory does not exist, or holds no day-file) from an EMPTY one - the
    design doc calls this out for the governance view by name.

    T-00000065 — THIS IS NO LONGER THE WHOLE ANSWER, AND ITS VERDICTS ARE ONLY
    VALID WHERE IT IS THE ONLY SOURCE. Since T-00000049 the spool is a BUFFER
    the ingester drains and deletes, so "no day-file" stopped meaning "no
    trail". `dashboard._read_canal_a_trail` therefore calls this ONLY when the
    store's status is `absent` (no projection has ever been written); with a
    store present the database is read instead. The reasons below are worded for
    that caller: each one now states that there is no projection either, because
    an empty spool NEXT TO a populated database is a healthy repo, not a lost
    audit trail."""
    if events_dir is None:
        return {"status": "trail_absent", "records": [], "files": 0, "malformed": 0,
                "reason": "the canal-A events directory could not be resolved"}
    if not events_dir.exists():
        return {"status": "trail_absent", "records": [], "files": 0, "malformed": 0,
                "reason": (
                    "no SQLite projection AND state/events/ does not exist: no hook has "
                    "ever emitted a canal-A event in this tree. ABSENT TRAIL, not an "
                    "empty one - nothing can be concluded about what was denied or "
                    "approved."
                )}
    try:
        paths = sorted(events_dir.glob("*.jsonl"))
    except OSError as exc:
        return {"status": "degraded", "records": [], "files": 0, "malformed": 0,
                "reason": f"state/events/ unreadable: {type(exc).__name__}"}
    if not paths:
        return {"status": "trail_absent", "records": [], "files": 0, "malformed": 0,
                "reason": (
                    "no SQLite projection, and state/events/ exists but holds no *.jsonl "
                    "day-file: the trail's location is there and its content is not. "
                    "ABSENT TRAIL, not a measurement of zero activity. (With a "
                    "projection present this state means the opposite - the ingester "
                    "drained the spool into the database - and this reader is not the "
                    "one consulted.)"
                )}
    records: list[dict[str, Any]] = []
    malformed = 0
    for path in paths:
        parsed, bad = read_jsonl_file(path)
        records.extend(parsed)
        malformed += bad
    records.sort(key=lambda r: (r.get("ts") or ""))
    return {"status": "ok" if records else "no_events", "records": records,
            "files": len(paths), "malformed": malformed,
            "reason": None if records else (
                f"{len(paths)} day-file(s) present and no parsable record in any of them"
            )}


# ---------------------------------------------------------------------------
# View 7 — Index & dérive.
# ---------------------------------------------------------------------------

def build_index_view(project_root: Path, index_section: dict[str, Any]) -> dict[str, Any]:
    delta_path = project_root.joinpath(*_INDEX_DELTA_REL)
    delta: dict[str, Any] | None = None
    delta_reason: str | None = None
    try:
        loaded = json.loads(delta_path.read_text(encoding="utf-8"))
        delta = loaded if isinstance(loaded, dict) else None
        if delta is None:
            delta_reason = "INDEX_DELTA.json is not a JSON object"
    except FileNotFoundError:
        delta_reason = "INDEX_DELTA.json absent - build_index.py has never published in this tree"
    except (OSError, json.JSONDecodeError) as exc:
        delta_reason = f"INDEX_DELTA.json unreadable: {type(exc).__name__}: {str(exc)[:200]}"

    built_sha = None
    if isinstance(delta, dict):
        built_sha = delta.get("built_sha")
    if not built_sha and isinstance(index_section, dict):
        built_sha = index_section.get("built_at_sha")

    section: dict[str, Any] = {
        "status": "ok" if delta is not None else "degraded",
        "reason": delta_reason,
        "header": {
            "built_at_sha": index_section.get("built_at_sha") if isinstance(index_section, dict) else None,
            "updated": index_section.get("updated") if isinstance(index_section, dict) else None,
            "raw": _clip(index_section.get("header"), _SHORT_CLIP) if isinstance(index_section, dict) else None,
            "status": index_section.get("status") if isinstance(index_section, dict) else None,
        },
        "freshness": _index_freshness(project_root, built_sha),
        # The coverage limit travels WITH this section, not only in the payload's
        # top-level caveats: a consumer rendering the index panel alone must still
        # see that the kit's own code is invisible here. DERIVED from the builder's
        # effective scope for this very tree, so a vendored kit says so too.
        "caveat": _index_view_caveat(project_root),
    }
    if delta is None:
        section.update({"backend": None, "counts": {}, "backlog": {}, "sharding": {}})
        return section

    needs_purpose = delta.get("needs_purpose") if isinstance(delta.get("needs_purpose"), list) else []
    needs_role = delta.get("needs_module_role") if isinstance(delta.get("needs_module_role"), list) else []
    section.update({
        "backend": delta.get("backend"),
        "backend_note": (
            "`ctags` is the real parser; `fallback` is the regex path - a fallback "
            "index is thinner by construction, not a smaller codebase."
        ),
        "counts": delta.get("counts") if isinstance(delta.get("counts"), dict) else {},
        "max_sym_id": delta.get("max_sym_id"),
        "backlog": {
            "needs_purpose": len(needs_purpose),
            "needs_purpose_sample": [str(x) for x in needs_purpose[:_SAMPLE_LIMIT]],
            "needs_module_role": len(needs_role),
            "needs_module_role_sample": [str(x) for x in needs_role[:_SAMPLE_LIMIT]],
            "owner": (
                "the `indexer` agent annotates this backlog (`:: purpose` / "
                "Role-Owner). It is a CONDITIONAL, annotation-only pipeline stage - "
                "never the index freshness mechanism (AGENTS.md)."
            ),
        },
        "sharding": {
            "sharded": delta.get("sharded"),
            "shards": delta.get("shards"),
        },
    })
    return section


_INDEX_VIEW_CAVEAT_TAIL = (
    " Coverage below is over the PROJECT's code. An agent looking for a kit test "
    "via SYMBOLS.md will not find it and must use glob/grep. Separately (L-029), "
    "this reader never refreshes the index: refreshing is a deterministic 0-LLM "
    "step that runs BEFORE the reader."
)


def _index_view_caveat(project_root: Path) -> str:
    """The coverage limit, DERIVED from the scope the builder would actually apply
    to THIS tree (T-00000062) rather than asserted statically.

    Degrades to the `.agents`-only statement if the scope cannot be resolved: that
    exclusion is unconditional (L-020), so the fallback is still true, only less
    specific. A reader never raises.
    """
    try:
        host_skip = _build_index.host_skip_dirs(project_root)
    except OSError:
        host_skip = set()
    try:
        head = _build_index.scope_caveat(host_skip)
    except Exception:  # pragma: no cover - the reader must not raise
        head = ("'.agents' (L-020) is excluded from the index, so this KIT's own "
                "tooling and tests have no symbolic entry AT ALL.")
    return head + _INDEX_VIEW_CAVEAT_TAIL


def _sha_joignable(project_root: Path, sha: str) -> bool:
    """Le dépôt connaît-il ce commit ? Sans cette question, un `fresh` FAUX.

    TROUVÉ PAR MON PROPRE TÉMOIN, et c'est le défaut que le commentaire d'à côté
    prétendait éviter. `changed_source_files` lance QUATRE commandes git et
    ignore celles qui échouent : sur un `built_sha` que le dépôt ne connaît pas
    — index venu d'un autre clone, historique réécrit, `shallow` —, le
    `git diff <sha> HEAD` échoue en silence, les trois autres rendent vide sur
    un arbre propre, et la fonction conclut « rien n'a changé ». On rendait donc
    `fresh` sur une mesure qu'on n'avait PAS su faire, c'est-à-dire un faux vert.

    On pose donc la question séparément, et une réponse négative fait retomber
    sur le verdict par SHA — le comportement d'avant ce correctif.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "cat-file", "-e", f"{sha}^{{commit}}"],
            # 1,5 s et non 5 : la docstring du module PROMET « each bounded at
            # 1.5 s », et les deux critiques ont relevé que le code disait 5 —
            # pire cas 6,5 s contre un poll d'interface à 5 s. Mesuré ici : 13 à
            # 18 ms. La doc ne ment plus, et la borne reste large.
            capture_output=True, text=True, check=False, timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return False
    return r.returncode == 0


def _index_freshness(project_root: Path, built_sha: Any) -> dict[str, Any]:
    head, source, reason = git_head_sha(project_root)
    out: dict[str, Any] = {
        "built_sha": built_sha if isinstance(built_sha, str) else None,
        "head_sha": head,
        "head_source": source,
        # PRÉSENT DÈS L'INITIALISATION, et c'est un correctif du binôme : les
        # trois sorties `unknown` rendaient auparavant un dict SANS cette clé,
        # donc un consommateur qui la lit voyait une forme variable selon le
        # chemin pris. `None` y dit « pas mesuré », ce qui est exact.
        "changed_indexed_files": None,
        "comparison": "prefix (build_index.py stamps a SHORT sha; HEAD is full)",
    }
    if not isinstance(built_sha, str) or not built_sha:
        out.update({"status": "unknown", "fresh": None,
                    "reason": "no `built_sha` on disk - nothing to compare HEAD against"})
        return out
    if built_sha == "nogit":
        out.update({"status": "unknown", "fresh": None,
                    "reason": "the index was built outside a git work tree (`built @ nogit`)"})
        return out
    if head is None:
        out.update({"status": "unknown", "fresh": None, "reason": reason})
        return out
    fresh = head.startswith(built_sha) or built_sha.startswith(head)

    # LE SHA N'EST QU'UN INDICE — CE QUI DÉCIDE, C'EST QU'UN FICHIER INDEXÉ AIT
    # BOUGÉ (T-00000575). Mesuré le 2026-09-13 avec `_keep()`, le critère RÉEL
    # de l'index, sur les 200 derniers commits du kit : **125, soit 62 %, ne
    # touchent AUCUN fichier indexé** et faisaient pourtant basculer l'affichage
    # en `stale`, parce que tout commit avance HEAD.
    #
    # LE PREMIER CHIFFRE ÉCRIT ICI ÉTAIT 82 %, ET IL ÉTAIT INVENTÉ : le script
    # de mesure excluait `.agents/`, que l'index du kit INCLUT — 39 commits
    # touchant `.agents/bin/` et `.agents/evals/` étaient comptés comme sans
    # impact. Un chiffre approché par un critère approchant, publié en HTTP
    # jusque chez l'adoptant. Le relevé qui fait foi appelle `_keep()`.
    #
    # LES DEUX SURFACES SONT D'ACCORD SUR LE PRINCIPE DEPUIS T-00000575 : ce qui
    # décide est le fichier INDEXÉ, ici comme dans `index_is_current` — le
    # verdict de `--if-stale`, appelé par `session-start.sh`. La décision de
    # sémantique que le ticket réclamait a été prise par le pilote (option C) et
    # elle est DESCENDUE dans le constructeur ; ce commentaire décrivait
    # l'implémentation d'avant, ce qui est pire qu'aucun commentaire.
    #
    # ELLES DIFFÈRENT SUR UN POINT, et `comparison` le DIT : ici les COMMITS
    # seuls ; là-bas l'arbre de travail aussi. Un `fresh` ici ne promet donc pas
    # qu'une reconstruction serait un no-op.
    #
    # POURQUOI PAS « TOLÉRER QUE HEAD SOIT UN COMMIT D'INDEX », l'autre option
    # que le ticket posait : le faux stale ne vient PAS des commits d'index — il
    # vient de TOUT commit. Cette tolérance-là n'aurait couvert qu'une fraction
    # du problème tout en masquant les cas vrais. Mesure à l'appui : sur 200
    # commits, 5 seulement sont des `chore(index)`.
    #
    # ON NE REND JAMAIS `fresh` SUR UNE MESURE QU'ON N'A PAS SU FAIRE : git
    # absent, sha injoignable ou timeout font retomber sur le verdict par SHA,
    # c'est-à-dire sur le comportement d'avant ce correctif — et `comparison` le
    # DIT alors, au lieu d'annoncer une méthode qui n'a pas tourné.
    #
    # (Le bloc qui vivait ici décrivait un appel à `changed_source_files` que ce
    # code ne fait plus, et lui prêtait une exclusion de `.agents/` qui n'existe
    # pas sur le kit — `SKIP_DIRS` ne la porte plus depuis le 2026-09-09. Un
    # commentaire qui décrit l'implémentation précédente est pire qu'aucun.)
    changes: list[str] | None = None
    if not fresh and _sha_joignable(project_root, built_sha):
        try:
            host_skip = _build_index.host_skip_dirs(project_root)
        except Exception:  # pragma: no cover - a reader never raises
            host_skip = set()
        # ON NE CONSULTE QUE LES COMMITS, JAMAIS L'ARBRE DE TRAVAIL, et c'est un
        # correctif du binôme. La première rédaction appelait
        # `changed_source_files`, qui lance QUATRE commandes git — dont trois sur
        # l'arbre vivant — sans timeout, dans un LECTEUR dont la docstring promet
        # « aucun sous-processus » et sous un budget de ping de 2 s. Pire, elle
        # rendait le verdict dépendant de l'arbre alors que l'empreinte de cache
        # des vues ne couvre PAS l'arbre : un `fresh` mis en cache survivait donc
        # à l'édition non commitée d'un fichier indexé — un FAUX FRESH, bien plus
        # grave que le faux stale qu'on corrige, parce qu'il fait travailler sur
        # un index périmé en silence.
        #
        # ICI LE VERDICT NE CONSULTE PLUS L'ARBRE POUR LES FICHIERS — mais il
        # N'EST PAS PUR, et l'écrire « fonction PURE de `(built_sha, HEAD)` »
        # était faux : `host_skip_dirs` STATE l'arbre (`.agents/IS_THE_KIT`,
        # `protected-paths.local`). Mesuré par le binôme, `built_sha` et HEAD
        # constants, un seul fichier NON COMMITÉ créé : sans le marqueur
        # `stale`/1 changement, avec le marqueur `fresh`/0. La troisième entrée
        # du verdict n'est donc pas dans la clé du cache de vues, et la direction
        # de l'erreur est celle du FAUX FRESH que le paragraphe ci-dessus nomme
        # comme la plus grave. Ce que ça vaut en pratique : poser ou retirer un
        # marqueur de vendoring est un geste RARE et délibéré, alors qu'éditer un
        # fichier indexé — ce que l'ancienne forme laissait passer — est le geste
        # le plus courant du dépôt. On a donc échangé un faux fresh permanent
        # contre un faux fresh de transition, dit plutôt que découvert.
        #
        # Le coût tombe à deux `spawn` bornés, et ce que la mesure NE couvre pas
        # est écrit dans `comparison` plutôt que tu.
        try:
            r = subprocess.run(
                ["git", "-C", str(project_root), "diff", "--name-only",
                 built_sha, "HEAD"],
                capture_output=True, text=True, check=False, timeout=1.5,
            )
            if r.returncode == 0:
                # `project_root` et NON `str(...)` : `_keep()` fait de
                # l'arithmétique de chemin, et une chaîne lèverait un
                # `TypeError` que le `except` avalerait — la mesure échouerait
                # en SILENCE et on retomberait sur le verdict par SHA, donc sur
                # le défaut qu'on corrige. Mesuré.
                changes = [
                    f for f in r.stdout.splitlines()
                    # `None` ET NON `project_root`, et c'est un correctif du
                    # binôme : `_keep()` reçoit la racine pour STAT l'arbre de
                    # travail — taille du fichier, détection d'un répertoire de
                    # build. Le verdict cessait donc d'être une fonction pure de
                    # `(built_sha, HEAD)`, ce que la ligne du dessus promet, et
                    # un fichier indexé devenu trop gros rendait `fresh` alors
                    # qu'une reconstruction l'aurait effacé. Avec `None`,
                    # `_is_build_output` rend `False` : la direction est
                    # CONSERVATRICE — au pire on garde un chemin de trop, donc
                    # on penche vers `stale`, jamais vers un faux `fresh`.
                    if f.strip() and _build_index._keep(f, None, host_skip)
                ]
        except Exception:  # pragma: no cover - git absent, timeout…
            changes = None
        if changes is not None and not changes:
            fresh = True

    # AUCUN CHIFFRE DANS LA CHARGE PUBLIÉE, et c'est un correctif du binôme. La
    # première rédaction y mettait un taux mesuré sur LE DÉPÔT DU KIT — une
    # statistique qui ne s'applique pas à l'adoptant, affichée dans son panneau
    # d'index. Corriger sa VALEUR (82 → 62) ne corrigeait pas le défaut : c'est
    # sa PRÉSENCE qui était fautive. Le taux reste au commentaire ci-dessus.
    # LE TEXTE SUIT LE CHEMIN RÉELLEMENT PRIS, et c'est un correctif des DEUX
    # critiques. La rédaction précédente l'écrivait sans condition : un adoptant
    # sans git, ou dont le sha tamponné est injoignable, lisait « mesuré par
    # fichiers » alors que le verdict venait du seul préfixe de SHA — une
    # méthode ANNONCÉE et jamais appliquée.
    # TROIS CAS, ET NON DEUX — relevé par les DEUX critiques, indépendamment.
    # `changes is None` confondait « mesure pas NÉCESSAIRE » (l'index EST à HEAD,
    # la branche par fichiers n'est pas entrée) et « mesure ÉCHOUÉE ». Le cas
    # nominal — celui qui suit chaque `chore(index)` — annonçait donc « sha
    # unreachable, git absent or timed out » en HTTP, jusque chez l'adoptant.
    # Mesuré. Et c'est la ligne même qui prétendait faire suivre le texte au
    # chemin pris qui l'a introduit : corriger une valeur ne corrige pas sa place.
    if changes is not None:
        out["comparison"] = (
            "indexed files changed between `built @` and HEAD — committed changes "
            "only, the working tree is NOT consulted, so an uncommitted edit to an "
            "indexed file does NOT show here. `build_index.py --if-stale` uses a "
            "DIFFERENT predicate (it does consult the tree): `fresh` here does not "
            "mean a rebuild would be a no-op.")
    elif fresh:
        out["comparison"] = (
            "`built @` prefixes HEAD — the index IS at HEAD, so the per-file "
            "measure was not needed (it runs only when the shas differ)")
    else:
        out["comparison"] = (
            "prefix (build_index.py stamps a SHORT sha; HEAD is full) — the "
            "per-file measure could NOT be made (sha unreachable, git absent or "
            "timed out), so this verdict is the SHA's")
    # DEUX BRANCHES AU CORPS IDENTIQUE se lisaient ici comme si deux cas devaient
    # différer — relevé du binôme. Un seul cas existe : frais, donc pas de raison.
    if fresh:
        raison = None
    else:
        combien = "an unknown number of" if changes is None else str(len(changes))
        raison = (
            f"the index was built at {built_sha} and HEAD is {head[:12]}, and "
            f"{combien} indexed file(s) changed since. Refresh is "
            "`build_index.py --if-stale` (deterministic, 0 LLM), not a job this "
            "reader does."
        )
    out.update({
        "status": "fresh" if fresh else "stale",
        "fresh": fresh,
        "changed_indexed_files": None if changes is None else len(changes),
        "reason": raison,
    })
    return out


# ---------------------------------------------------------------------------
# Entry point + memoisation.
# ---------------------------------------------------------------------------

_views_cache: dict[str, Any] = {"fingerprint": None, "value": None}

_CHRONO_NOM = re.compile(r"^T-[0-9A-Z]+$")
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _chrono_plan(entries: list[dict[str, Any]], tid: str, debut_ms: int) -> dict[str, int] | None:
    specs_chrono = _chrono_specs_module()
    plan = {"tours": 0, "mesures": 0, "planner_s": 0, "critic_s": 0,
            "planner_jetons": 0, "critic_jetons": 0}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("task") != tid or not specs_chrono.est_verdict_de_boucle(
                entry.get("kind"), entry.get("title")):
            continue
        identifiant = entry.get("id")
        instant = None
        if isinstance(identifiant, str) and len(identifiant) == 28 and identifiant.startswith("S-"):
            try:
                instant = 0
                for caractere in identifiant[2:12]:
                    instant = instant * 32 + _ULID_ALPHABET.index(caractere)
            except ValueError:
                instant = None
        if instant is None:
            try:
                jour = date.fromisoformat(entry["date"])
                instant = int(datetime(jour.year, jour.month, jour.day, tzinfo=timezone.utc).timestamp() * 1000)
                debut = datetime.fromtimestamp(debut_ms / 1000, timezone.utc).date()
                if jour == debut:
                    instant = debut_ms
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if instant < debut_ms:
            continue
        plan["tours"] += 1
        mesure = specs_chrono.lire_chrono(entry.get("text") or "")
        if mesure is None:
            continue
        plan["mesures"] += 1
        for role, prefix in (("planner", "planner"), ("plan-critic", "critic")):
            plan[f"{prefix}_s"] += mesure[role][0]
            plan[f"{prefix}_jetons"] += mesure[role][1]
    return plan if plan["tours"] else None


def _lots_durees(cycle: dict[str, Any], clos: bool, now_ms: int) -> list[dict[str, Any]]:
    """La durée de chaque lot du cycle COURANT de la mère, sur les mesures déjà analysées (aucune lecture).

    Une mesure FINIE compte de son début à sa fin, fusion comprise. Une mesure OUVERTE ne compte jusqu'à
    `now_ms` que si elle court : mère ouverte ET étape autre que `fusion` ; sinon elle sort de la durée et
    est nommée dans `non_bornees` — jamais bornée à `now_ms` ni au done. La fin de fusion d'un lot s'écrit
    seule au `retour` et au `done` suivants, à l'heure du commit de fusion (`task_chrono.fusions_premesurees`) ;
    borne : une avance rapide, un squash, un rebase ou une fusion hors de la chaîne `--first-parent` de HEAD
    (ou de `refs/heads/<vers>` pour un relevé `retour --vers`)
    n'en écrivent aucune, et la `fusion` reste ouverte, dite, non comptée, tant qu'aucun verbe ne suit.
    `etapes` = étapes COMPTÉES dans `reel_s` (vide : rien de borné). Le board du lot n'est pas lu ici :
    pause et gel d'un lot clos au board sont l'affaire du front (`dureeLotDe`)."""
    par_lot: dict[str, list[dict[str, Any]]] = {}
    for mesure in cycle["etapes"].values():
        if mesure["lot"] and mesure["etape"] not in _task_chrono.NON_MESUREES:
            par_lot.setdefault(mesure["lot"], []).append(mesure)
    ordre = {nom: rang for rang, nom in enumerate(_task_chrono.ETAPES)}
    durees = []
    for lot in sorted(par_lot):
        intervalles, comptees, ouvertes, non_bornees = [], set(), set(), set()
        for mesure in par_lot[lot]:
            if "fin" in mesure:
                intervalles.append((mesure["debut"], mesure["fin"]))
            elif not clos and mesure["etape"] != "fusion":
                intervalles.append((mesure["debut"], max(mesure["debut"], now_ms)))
                ouvertes.add(mesure["etape"])
            else:
                non_bornees.add(mesure["etape"])
                continue
            comptees.add(mesure["etape"])
        live = bool(ouvertes)
        statut = "en cours" if live else ("incomplète" if non_bornees else "finie")
        durees.append({"lot": lot, "reel_s": _task_chrono._union_s(intervalles), "statut": statut, "live": live,
                       "etapes": sorted(comptees, key=ordre.__getitem__),
                       "ouvertes": sorted(ouvertes, key=ordre.__getitem__),
                       "non_bornees": sorted(non_bornees, key=ordre.__getitem__)})
    return durees


def _chrono_ligne(root: Path, tid: str, entries: list[dict[str, Any]], now_ms: int) -> dict[str, Any]:
    ligne: dict[str, Any] = {"tid": tid, "cycle": None, "debut_ms": None, "clos": False,
                             "etapes": [], "plan": None, "total": None, "incomplet": [], "erreur": None,
                             "lots_journalises": [], "lots_durees": []}
    chemin = _task_chrono.chemin_journal(root, tid)
    if not _SANS_SUIVRE and os.path.islink(chemin):
        ligne["erreur"] = "journal lien symbolique : non suivi"
        return ligne
    # UNE lecture contrôlée (dossier et journal sans lien, fichier régulier, LIRE_MAX) ; `bilan` et `lire`
    # analysent CES octets sans rouvrir le chemin : aucune fenêtre entre le contrôle et l'analyse.
    try:
        brut = _task_chrono.lire_brut(root, tid)
    except _task_chrono.ChronoErreur as exc:
        cause = exc.__cause__
        if isinstance(cause, OSError) and cause.errno in (errno.ELOOP, errno.EMLINK):
            ligne["erreur"] = "journal lien symbolique : non suivi"
        elif "lien symbolique" in str(exc):
            ligne["erreur"] = "dossier du journal lien symbolique : non suivi"
        elif "régulier" in str(exc):
            ligne["erreur"] = "journal non régulier : non lu"
        elif "au-delà" in str(exc):
            ligne["erreur"] = "journal dépasse 1 Mio : non lu"
        else:
            ligne["erreur"] = f"journal illisible : {type(cause or exc).__name__}"
        return ligne
    try:
        releve = _task_chrono.bilan(root, tid, now_ms=now_ms, octets=brut)
        tous = _task_chrono.cycles(_task_chrono.lire(root, tid, brut))
    except Exception as exc:  # noqa: BLE001 — une ligne cassée ne casse pas le snapshot
        ligne["erreur"] = f"bilan indisponible : {type(exc).__name__}"
        return ligne
    if not tous or releve.get("cycle") is None:
        ligne["incomplet"] = ["aucun cycle relevé"]
        return ligne
    cycle = tous[max(tous)]
    clos = _task_chrono.est_clos(cycle)
    fin_done = min((e["fin"] for e in cycle["etapes"].values()
                    if e["etape"] == _task_chrono.ETAPE_FINALE and e["lot"] is None and "fin" in e),
                   default=now_ms)
    borne = fin_done if clos else now_ms
    try:
        plan = _chrono_plan(entries, tid, cycle["debut"])
    except Exception as exc:  # noqa: BLE001 — une entrée SPECS mal formée reste sur sa ligne
        ligne["erreur"] = f"plan indisponible : {type(exc).__name__}"
        return ligne
    # Les LOTS journalisés dans CE cycle de la mère (champ `lot` de ses lignes d'étape) : leurs
    # identifiants, pour que la frise ne classe « sans journal » que les lots qui n'en ont aucun
    # (e2e-dashboard B2 : un simple compte par étape les rendait tous « sans journal »).
    ligne.update(cycle=max(tous), debut_ms=cycle["debut"], clos=clos,
                plan=plan, incomplet=releve.get("incomplet", []),
                lots_journalises=sorted({e["lot"] for e in cycle["etapes"].values() if e["lot"]}),
                lots_durees=_lots_durees(cycle, clos, now_ms))
    if clos:
        ligne["done_at"] = fin_done
    total_intervalles: list[tuple[int, int]] = []
    for nom in _task_chrono.ETAPES:
        mesures = [e for e in cycle["etapes"].values() if e["etape"] == nom]
        if not mesures:
            continue
        intervalles = [(e["debut"], max(e["debut"], e.get("fin", borne))) for e in mesures]
        if nom not in _task_chrono.NON_MESUREES:
            total_intervalles.extend(intervalles)
        estime_par_lot: dict[str, int] = {}
        estimations = [e.get("estimation") or {} for e in mesures]
        for e in mesures:
            estimation = e.get("estimation") or {}
            if "mediane_s" in estimation:
                lot = e["lot"] or ""
                estime_par_lot[lot] = estime_par_lot.get(lot, 0) + estimation["mediane_s"]
        statut = "finie" if all("fin" in e for e in mesures) else ("incomplète" if clos else "en cours")
        ligne["etapes"].append({"etape": nom, "statut": statut,
            "reel_s": _task_chrono._union_s(intervalles),
            "estime_s": max(estime_par_lot.values(), default=None),
            "p90_s": max((est["p90_s"] for est in estimations if "p90_s" in est), default=None),
            "source": next((est.get("source") for est in estimations if est.get("source")), "inconnu"),
            "tentatives": len(mesures), "lots": len({e["lot"] for e in mesures})})
    estimations_etapes = [e["estime_s"] for e in ligne["etapes"] if e["estime_s"] is not None]
    ligne["total"] = {"reel_s": _task_chrono._union_s(total_intervalles),
                      "estime_s": sum(estimations_etapes) if estimations_etapes else None}
    return ligne


def build_chrono(project_root: Path, specs_section: dict[str, Any], now_ms: int | None = None) -> dict[str, Any]:
    """Tous les journaux locaux sont servis ; une erreur reste sur sa ligne.

    Chaque ligne close porte `done_at` en millisecondes ; une ligne ouverte n'a pas cette clé.
    Borne connue : les journaux ne sont jamais purgés. À 1 000 journaux,
    le bilan mesuré prend 451 ms et produit 820 Ko de données ; le coût croît sans limite.
    """
    _chrono_module()
    if not callable(getattr(_task_chrono, "bilan", None)):
        raise RuntimeError("task_chrono.bilan absent")
    now = int(time.time() * 1000) if now_ms is None else now_ms
    base = {"reason": None, "mesure_le_ms": now, "etapes_ordre": list(_task_chrono.ETAPES),
            "taches": [], "tronque": 0}
    dossier = project_root / _task_chrono.JOURNAL_DIR_REL
    if not dossier.is_dir():
        return {"status": "no_events", **base}
    try:
        fichiers = [p for p in dossier.iterdir() if p.suffix == ".jsonl" and _CHRONO_NOM.fullmatch(p.stem)]
        fichiers.sort(key=lambda p: (p.lstat().st_mtime_ns, p.name), reverse=True)
    except OSError as exc:
        return {"status": "degraded", **base, "reason": f"dossier chrono illisible : {type(exc).__name__}"}
    running = _running_task_ids(project_root)
    fichiers.sort(key=lambda p: p.stem in running, reverse=True)
    entries = (specs_section.get("data") or {}).get("entries", []) if specs_section.get("status") == "ok" else []
    if not isinstance(entries, list):
        entries = []
    return {"status": "ok" if fichiers else "no_events", **base,
            "taches": [_chrono_ligne(project_root, p.stem, entries, now) for p in fichiers]}


def reset_cache_for_tests() -> None:
    _views_cache["fingerprint"] = None
    _views_cache["value"] = None
    _stream_cache["fingerprint"] = None
    _stream_cache["value"] = None


def build_views(
    project_root: Path,
    events_dir: Path | None,
    otel_dir: Path | None,
    normalize_mod: Any,
    ledger_section: dict[str, Any],
    specs_section: dict[str, Any],
    index_section: dict[str, Any],
    verdict_section: dict[str, Any],
    canal_b_section: dict[str, Any],
    canal_a_stream: dict[str, Any],
    ingestion_section: dict[str, Any] | None = None,
    store_fingerprint: tuple = (),
) -> dict[str, Any]:
    """The D4 view sections plus `chrono` and a `meta` block, memoised on
    `views_fingerprint`. Never raises: an unexpected failure in ANY section
    degrades that section (or, for a failure outside every section, the whole
    `views` block) with a reason - `/api/snapshot` never 500s for a view.

    The returned dict must be treated as READ-ONLY by callers: an unchanged
    poll gets the same object back."""
    started = time.perf_counter()
    fingerprint = views_fingerprint(project_root, events_dir, otel_dir, store_fingerprint)
    cached = _views_cache["value"]
    if _views_cache["fingerprint"] == fingerprint and cached is not None:
        # Meta is rewritten (cheaply) so a consumer can see the hit; the six
        # sections are the same objects, unmodified.
        return {
            "views": cached["views"],
            "meta": {**cached["meta"], "cached": True,
                     "build_ms": round((time.perf_counter() - started) * 1000.0, 3)},
        }

    # T-00000065 — THE TRAIL ARRIVES, IT IS NOT RE-READ HERE. `canal_a_stream` is
    # a REQUIRED parameter with no default on purpose: a default that fell back
    # to `read_canal_a_stream(events_dir)` would silently restore the defect this
    # task fixed (globbing a spool the ingester deletes, and calling the result
    # an absent trail) for any caller that forgot the argument.
    stream = canal_a_stream if isinstance(canal_a_stream, dict) else {
        "status": "degraded", "records": [], "files": 0, "malformed": 0,
        "reason": "canal-A stream was not supplied as a mapping",
    }
    views = {
        "governance": _guard(
            lambda: build_governance(stream, project_root, canal_b_section),
            _degraded_section("governance")),
        "security": _guard(
            lambda: build_security(project_root, verdict_section, stream),
            _degraded_section("security")),
        "memory": _guard(
            lambda: build_memory(ledger_section, specs_section),
            _degraded_section("memory")),
        "index": _guard(
            lambda: build_index_view(project_root, index_section),
            _degraded_section("index")),
        "mcp": _guard(
            lambda: build_mcp(project_root, stream, canal_b_section),
            _degraded_section("mcp")),
        # T-00000379 lot E. Une vue de PLUS, pas une route de plus : le contrat de
        # routes de `dashboard.py` est CLOS et gele depuis T-00000051, et toute
        # donnee neuve voyage sous `views` — la meme decision que les six autres.
        "specs_graph": _guard(
            lambda: build_specs_graph(project_root),
            _degraded_section("specs_graph")),
        "coverage": _guard(
            lambda: build_coverage(stream, canal_b_section, normalize_mod,
                                   ingestion_section),
            _degraded_section("coverage")),
        "chrono": _guard(
            lambda: build_chrono(project_root, specs_section),
            {"status": "degraded", "reason": "lecteur chrono indisponible",
             "mesure_le_ms": int(time.time() * 1000), "etapes_ordre": [],
             "taches": [], "tronque": 0}),
    }
    meta = {
        "sections": sorted(views),
        "canal_a_files_read": stream.get("files", 0),
        "canal_a_records_read": len(stream.get("records") or []),
        "canal_a_malformed_lines_skipped": stream.get("malformed", 0),
        "section_statuses": {name: section.get("status") for name, section in views.items()},
        "status_vocabulary": list(SECTION_STATUSES),
        "cached": False,
        "build_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "memoised_on": (
            "(name, mtime_ns, size) over every input file plus the canal-A and "
            "canal-B and task-chrono directories; an unchanged poll costs stat() calls, not reads"
        ),
    }
    _views_cache["fingerprint"] = fingerprint
    _views_cache["value"] = {"views": views, "meta": meta}
    return {"views": views, "meta": meta}


def _degraded_section(name: str) -> dict[str, Any]:
    return {"status": "degraded", "reason": f"the {name} reader raised - section unavailable"}


def _guard(builder, fallback: dict[str, Any]) -> dict[str, Any]:
    """Every section is built behind this: one section's surprise degrades
    that section only, never the response (the shard-1 rule, applied to six
    more readers)."""
    try:
        return builder()
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        return {**fallback,
                "reason": f"{fallback.get('reason')}: {type(exc).__name__}: {str(exc)[:300]}"}


# ---------------------------------------------------------------------------
# T-01M5A1244ZHSSA8RPCZYDJ49XE (lot S de T-01M54GEA4BNFC7QDJVK6P53Y4B) : le dernier bilan de setup.
# ---------------------------------------------------------------------------

# Le CONTRAT qu'écrit `setup_bilan.py` (lot B) ; `dashboard_transport.FICHIERS_HORS_VUES` le porte aussi.
SETUP_BILAN_REL = (".agents", "state", "local", "setup-bilan.json")
SETUP_BILAN_MAX = 64 * 1024
SETUP_ETATS = ("OK", "KO", "SANS OBJET")
_SETUP_ENTETE = frozenset({"schema", "genere_le", "rc", "jambes", "commande"})
_SETUP_JAMBE = frozenset({"jambe", "etat", "detail", "remede"})
# Un lien n'est jamais suivi, une FIFO ne bloque jamais le snapshot. Sans `O_NOFOLLOW` (Windows) : `islink` d'abord.
_SANS_SUIVRE = getattr(os, "O_NOFOLLOW", 0)
_SANS_BLOQUER = getattr(os, "O_NONBLOCK", 0)


def _ouvrir_sans_suivre(chemin: str, drapeaux: int) -> int:
    """`opener` de `open(..., "rb")` : les drapeaux de lecture seule qu'il reçoit, plus les deux refus ci-dessus.
    Mots-clés : le relevé d'écritures (f) de `test_dashboard_readers_decoupe` lit un `x.open(<mode>)` positionnel."""
    return os.open(path=chemin, flags=drapeaux | _SANS_SUIVRE | _SANS_BLOQUER)


def _refus_constante(nom: str) -> Any:
    """`parse_constant` de `json.loads` : NaN / Infinity refusés (idiome de `fusion_enregistrement.py`) — servis,
    ils rendraient le corps du snapshot illisible au `response.json()` du navigateur."""
    raise ValueError(f"constante non JSON {nom}")


def read_setup_bilan(project_root: Path) -> dict[str, Any]:
    """Le dernier bilan de `setup_bilan.py`, servi sous la clé RACINE `setup` du snapshot (hors `views`).

    `{status: ok|absent|degraded, reason, genere_le, rc, jambes, commande}`. Absent : aucun bilan écrit dans
    cet arbre. Degraded, jamais une liste vide qui se lirait « tout va bien » : lien symbolique, fichier non
    régulier (FIFO…), plus de 64 Kio, JSON illisible, non UTF-8, trop imbriqué ou à constante NaN / Infinity,
    forme fausse, aucune jambe, `etat` hors de `SETUP_ETATS` (dit par un `repr` tronqué à 40 caractères), clé
    inconnue ou type hors du CONTRAT (`schema` 1, `genere_le` chaîne, `rc` 0|1, `commande` chaîne ; par jambe
    `jambe`, `detail` chaînes, `remede` chaîne ou null), substitut UTF-16 isolé dans une chaîne servie,
    `genere_le` hors ISO (`fromisoformat`), `rc` autre que 1 au moindre KO, 0 sinon — aucun conteneur ni
    substitut n'atteint donc l'encodeur du transport. `open` d'emblée, sans `exists()` préalable :
    le témoin d'audit du transport relève ainsi un bilan CHERCHÉ et absent, et exige qu'il compte dans la clé."""
    vide: dict[str, Any] = {"genere_le": None, "rc": None, "jambes": [], "commande": None}
    chemin = project_root.joinpath(*SETUP_BILAN_REL)
    if not _SANS_SUIVRE and os.path.islink(chemin):
        return {"status": "degraded", "reason": "setup-bilan.json est un lien symbolique : non suivi", **vide}
    try:
        with open(chemin, "rb", opener=_ouvrir_sans_suivre) as fichier:
            if not stat.S_ISREG(os.fstat(fichier.fileno()).st_mode):
                return {"status": "degraded", "reason": "setup-bilan.json n'est pas un fichier régulier", **vide}
            brut = fichier.read(SETUP_BILAN_MAX + 1)
    except FileNotFoundError:
        return {"status": "absent", "reason": "setup-bilan.json absent : aucun bilan écrit dans cet arbre "
                "(python3 .agents/bin/setup_bilan.py)", **vide}
    except OSError as exc:
        if _SANS_SUIVRE and exc.errno in (errno.ELOOP, errno.EMLINK):  # EMLINK : le refus d'O_NOFOLLOW sous FreeBSD
            return {"status": "degraded", "reason": "setup-bilan.json est un lien symbolique : non suivi", **vide}
        return {"status": "degraded", "reason": f"setup-bilan.json illisible : {type(exc).__name__}", **vide}
    if len(brut) > SETUP_BILAN_MAX:
        return {"status": "degraded", "reason": "setup-bilan.json dépasse 64 Kio : non lu", **vide}
    try:
        data = json.loads(brut.decode("utf-8"), parse_constant=_refus_constante)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:  # RecursionError : imbrication, 3.11 et 3.12
        return {"status": "degraded", "reason": f"setup-bilan.json illisible : {type(exc).__name__}", **vide}
    jambes = data.get("jambes") if isinstance(data, dict) else None
    if not isinstance(jambes, list) or not all(isinstance(j, dict) for j in jambes):
        return {"status": "degraded", "reason": "setup-bilan.json : forme inattendue (jambes)", **vide}
    if not jambes:
        return {"status": "degraded", "reason": "setup-bilan.json : aucune jambe", **vide}
    # `repr` tronqué : un `etat` de 60 000 caractères ne gonfle jamais la raison servie.
    hors = sorted({repr(e)[:40] if e is None or isinstance(e, (str, int, float)) else f"<{type(e).__name__}>"
                   for e in (j.get("etat") for j in jambes) if e not in SETUP_ETATS})
    if hors:
        return {"status": "degraded", "reason": f"setup-bilan.json : état hors vocabulaire {', '.join(hors)}",
                **vide}
    # Le CONTRAT typé, clé pour clé : aucune clé inconnue, aucun conteneur dans un champ servi. Le décodeur C
    # accepte une imbrication que l'encodeur pur Python de `serialiser` ne sait pas réécrire (RecursionError).
    if set(data) != _SETUP_ENTETE or type(data["schema"]) is not int or data["schema"] != 1 \
            or not isinstance(data["genere_le"], str) or type(data["rc"]) is not int or data["rc"] not in (0, 1) \
            or not isinstance(data["commande"], str):
        return {"status": "degraded", "reason": "setup-bilan.json : en-tête hors contrat (clés ou types)", **vide}
    if not all(set(j) == _SETUP_JAMBE and isinstance(j["jambe"], str) and isinstance(j["detail"], str)
               and (j["remede"] is None or isinstance(j["remede"], str)) for j in jambes):
        return {"status": "degraded", "reason": "setup-bilan.json : jambe hors contrat (clés ou types)", **vide}
    servis = [data["genere_le"], data["commande"], *(v for j in jambes for v in j.values() if v is not None)]
    try:  # un substitut UTF-16 isolé (`"\ud800"`, JSON valide) ferait lever l'encodeur UTF-8 de `serialiser`
        "".join(servis).encode("utf-8")
    except UnicodeEncodeError:
        return {"status": "degraded", "reason": "setup-bilan.json : substitut UTF-16 isolé, non servi", **vide}
    try:
        datetime.fromisoformat(data["genere_le"])
    except ValueError:
        return {"status": "degraded", "reason": "setup-bilan.json : genere_le hors contrat (ISO)", **vide}
    if data["rc"] != (1 if any(j["etat"] == "KO" for j in jambes) else 0):
        return {"status": "degraded", "reason": "setup-bilan.json : rc incohérent avec les jambes", **vide}
    return {"status": "ok", "reason": None, "genere_le": data["genere_le"], "rc": data["rc"],
            "jambes": jambes, "commande": data["commande"]}
