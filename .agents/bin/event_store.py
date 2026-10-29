#!/usr/bin/env python3
"""event_store.py — the SQLite projection of the canal-A/canal-B spool (V1-b).

Task `docs/tasks/T-00000049.md`; spec `docs/design/2026-07-28-spec-v1-projection.md`
§A.2 (authoritative, §B.3 lists the rejected options). Approved plan revision 6,
journal entries S-00000089..S-00000097. stdlib only (`sqlite3`), by kit doctrine.

WHAT THIS MODULE IS. The hooks keep writing their mini-JSONL exactly as before
(proven path, fail-open, one file per writer — L-00000041). This module reads
that spool and projects it into `.agents/state/local/events.db`, git-ignored.
**The daemon is the SOLE WRITER of the database**; the UI only reads it. No
lock contention is possible by construction, which is why direct SQLite writes
from the hooks were rejected (§B.3: short-lived fail-open processes contending
for a write lock is the L-00000041 family of problems all over again).

THE ORDER IS THE DESIGN — read -> INSERT batch in ONE transaction -> COMMIT ->
delete the files. Every one of the four exit criteria falls out of it:

  1. `kill -9` mid-ingestion, zero loss AND zero duplicate. Killed before the
     COMMIT: the transaction rolls back and the spool files are still there, so
     the next tick re-reads them. Killed after the COMMIT but before the
     deletion: the files are still there, the rows are already in, and the
     re-read is absorbed by `INSERT OR IGNORE` on the identity below. There is
     no third window. The in-memory resume offsets die with the process, which
     is harmless for the same reason: a re-read is free.

  2. Deletion is RETRY-OR-SKIP, NEVER an error (L-00000035, L-00000054). A file
     Windows will not let go of waits for the next tick. `_unlink_with_retry`
     returns a bool and raises nothing.

  3. Boot catch-up (the dimensioning case: daemon dead a whole day = hundreds of
     files) is one batch, bounded by `_BATCH_ROW_CAP` rows per transaction, and
     the resulting lag is DISPLAYED — `ingestion_status()` feeds the Couverture
     view with `behind_since` / `late`. Never silent.

  4. A partial line is never ingested truncated: `_read_spool_lines` parses only
     up to the RIGHTMOST b"\\n" of what it read, and — the other half of the
     rule — a file whose size exceeds our consumed offset is by definition not
     fully consumed, so it is never deleted either.

DEDUPLICATION IS PER RECORD, NEVER PER FILE OR PER DAY (L-00000060, §B.3).

    UNIQUE (project, src_file, line_index, line_hash)

  * `project`    — the `project_id` from `.agents/state/project.json`, or the
    literal `"unset"` when identity has not been initialised yet. The column
    exists FROM DAY ONE even though a database is per-project (§B.2.3: the
    future hub is a copy, not a transformation). It is resolved ONCE at open
    time and FROZEN for the life of the store object, and the `unset -> id`
    catch-up UPDATE runs at open BEFORE the first tick — that ordering is the
    whole fix: a project value that could flip mid-session would let one
    physical line be counted under two `project` values across a failed delete
    (plan-critic iteration 5, C1), which is a duplicate, not a partition.
  * `src_file`   — `"<channel>/<name>"`, e.g. `a/2026-07-29.claude.8123.jsonl`.
    The WRITER'S IDENTITY IS IN THIS STRING (host + pid, by `events._day_file`'s
    construction), which is what stops a burst of byte-identical `hook.deny`
    events in the same second from collapsing into one row (iteration 1, C1).
  * `line_index` — the 0-based rank of the line inside its file, counting every
    `\\n`-separated line including blank and malformed ones so a rank never
    shifts. **Assigned by the INGESTION ALONE, never by a writer and never by
    the receiver** (iteration 5, C4): a rank derived by a producer that started
    counting at a different point diverges from the file's own truth, and a
    divergent rank is a new identity, i.e. a double count. `notify_dirty()` is
    a latency hint and carries no rank.
  * `line_hash`  — `sha256` of the line's raw BYTES as read from disk, EXCLUDING
    the trailing b"\\n", hex-encoded. Pinned here on purpose (iteration 3, C4):
    "hash of the line" is ambiguous between str and bytes, and two recipes mean
    two identities for one event.

WHAT WAS DELIBERATELY REMOVED. Re-homing (`events.merge_day_files` folding a
day's per-writer files into `D.merged.jsonl`) is retired as an operator action
the moment this store exists — `events.main()` no-ops both flags under
`maintenance_lock()`. A file that was ingested but not yet deleted (the Windows
handle window) would come back under a NEW `(src_file, line_index)` identity
that `INSERT OR IGNORE` cannot match: one audit line, two rows, permanently
over-counted (iteration 6, C1). `merge_day_files` survives for exactly ONE
caller, `_migrate_legacy_spool()`, one time in the life of a project, under that
same lock, on a still-absent database (iteration 5, C2 — folding legacy crash
residue BEFORE anything is ingested is what keeps a stale `D.merged.jsonl` and
its surviving originals from double-homing).

A DATABASE FROM THE FUTURE IS NEVER TOUCHED. `PRAGMA user_version` > 1 means a
newer kit wrote this file and the operator rolled back (T-00000040's doctrine
applied to data). We do not rename it, we do not "repair" it, and above all we
never run v1 SQL against a v2 schema — the connection is CLOSED immediately and
every reader gets a known-shape degraded payload carrying the reason (iteration
2, C1: "the API still serves" is unfalsifiable when any v1 statement raises).
The rollback path is `--export-spool`, below.

CHANNEL B IS INGESTED, AND SINCE V1-c ITS FILES ARE DELETED TOO. Canal-B
envelopes land in the same transaction as canal A (spec §A.2: no spool detour —
the collector already lives in the daemon, and `otel_receiver.persist()` is one
`json.dumps` + one `os.write`, so its file is readable line-by-rank exactly like
canal A's). V1-b froze the otel READERS (`dashboard._read_canal_b`,
`otel_normalize`) on the files and therefore had to retain them
(`_DELETE_CHANNELS = {"a"}`); V1-c (T-00000050) moves those readers onto THIS
store, so `_DELETE_CHANNELS` is `{"a", "b"}` and one figure has exactly one
live source again.

═══════════════════════════════════════════════════════════════════════════════
V1-c — PROJECT ATTRIBUTION OF CANAL B (T-00000050, spec §A.3, journal
S-00000100..S-00000113). Four points in a row's life cycle touch its `project`,
and the whole design is that they AGREE:

  1. BIRTH (`_row`) — a canal-B line whose body declares another project's
     `project_id` is stamped `PROJECT_UNSET`, i.e. QUARANTINED, at the single
     insertion site. See `declares_foreign_project` for the non-negotiable
     purity invariant and for why each of its four "never"s is a named defect.
  2. OPEN (`_relabel_unset_locked`) — rows written before `project.json` existed
     are adopted onto the real id; QUARANTINED rows are left alone, and only
     ids we classified in Python are deleted (as proven duplicates).
  3. OPEN (`_backfill_promote_project_field`) — the ONE-SHOT materialising pass
     that gives every pre-V1-c canal-B row a promoted field, so the display's
     five buckets partition the rows totally. Idempotent and journalled.
  4. FOLD (`_fold_retention_locked`) — a quarantined row reaching the 30-day
     cutoff is deleted WITHOUT bumping a local digest, and counted into the
     cumulative `meta` key `foreign_held_expired`.

Out of scope here, on purpose (pilot decision S-00000110): the digests grow no
cost/token sums and no `provenance` dimension in V1-c — that is T-00000054.
Nothing in this shard changes `user_version` or `_apply_migrations`.
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from array import array
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Explicit-path module load — `events.py`'s IMPORT CONTRACT, dogfooded.
    A bare `import events` would resolve against `sys.path[0]`, which is the
    invoking shell's cwd for the hooks that feed Python from stdin."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# One-way import: this module depends on events.py (path + maintenance lock +
# the legacy merger), events.py never depends on this one, so `emit()`'s
# fail-open hot path cannot be affected by anything here.
_events_mod = _load_sibling("_store_events", "events.py")
_otel_receiver_mod = _load_sibling("_store_otel_receiver", "otel_receiver.py")

# --- T-00000770 : la couture `cadre.ledger.store` (patron S-00001655) -----------
# `open_store` ouvre `events.db` par la primitive NON SUIVIE du paquet
# (`cadre.ledger.store.refuser_les_liens` / `ouvrir_sans_suivre`, qui reçoit un
# `cadre.workspace.Workspace`) : (1) le paquet importé s'il vient du dossier de `cadre` (ou sans dossier),
# sinon (2) PAR CHEMIN depuis ce dossier — sûr : `ledger/store.py`, `workspace.py` stdlib-seule (U0).
# `sys.modules` relu seulement si la copie vient du fichier ATTENDU (T-00000691). Succès mémoïsé, échec
# jamais : chaque `open_store` réessaie. Sans le paquet : `absent` + `seam_missing`, store NON LU, aucune
# jambe stdlib (S-00001655). Le dossier vient du RÉSOLVEUR `vendor_paths.py` (`.agents/vendor/cadre`,
# sinon `src/cadre`), chargé PAR CHEMIN sous le nom partagé ; absent, incomplet ou illisible : `src/cadre`.
_NOM_RESOLVEUR = "_cadre_vendor_paths_bin"
_API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _executer(nom_module: str, chemin: Path, existant: Any) -> Any:
    """`chemin` exécuté sous `nom_module`, enregistré AVANT `exec_module` ; s'il lève, la copie
    d'avant (`existant`) est rendue ou le nom retiré — jamais une copie à moitié exécutée."""
    spec = importlib.util.spec_from_file_location(nom_module, chemin)
    if spec is None or spec.loader is None:  # pragma: no cover - défensif
        raise ImportError(f"{nom_module} introuvable ({chemin})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if existant is not None:
            sys.modules[spec.name] = existant
        else:
            sys.modules.pop(spec.name, None)
        raise
    return module


def _resolveur() -> Any:
    """`vendor_paths.py`, frère de ce fichier, s'il porte toute `_API_RESOLVEUR`, sinon `None` ;
    la copie de `sys.modules` n'est relue que si elle vient du fichier ATTENDU. Illisible
    (`SyntaxError`…) = ABSENT, et le repli le DIT en une ligne sur stderr (S-01M5CAG0HC)."""
    chemin = HERE / "vendor_paths.py"
    try:
        module = sys.modules.get(_NOM_RESOLVEUR)
        fichier = getattr(module, "__file__", None)
        if module is None or not fichier or Path(fichier).resolve() != chemin:
            if not chemin.is_file():
                return None
            module = _executer(_NOM_RESOLVEUR, chemin, module)
    except Exception as exc:
        print(f"event_store: résolveur {chemin} illisible ({type(exc).__name__}: "
              f"{' '.join(str(exc).split())}) — repli sur src/cadre", file=sys.stderr)
        return None
    return module if all(hasattr(module, nom) for nom in _API_RESOLVEUR) else None


def _dossier_cadre(racine: Path) -> Path:
    resolveur = _resolveur()
    dossier = None if resolveur is None else resolveur.dossier_paquet(racine, "cadre")
    return dossier if dossier is not None else racine / "src" / "cadre"


_SRC_CADRE = _dossier_cadre(HERE.parents[1])
_MODULES_CADRE: dict[str, Any] = {}


def _charger_par_chemin(nom: str) -> Any:
    """Branche (2) de `_cadre_module` : `<_SRC_CADRE>/<nom>.py` chargé PAR CHEMIN sous
    `_cadre_<nom>_event_store`, sans mémo ; `sys.modules` relu seulement si la copie vient
    du fichier ATTENDU, une exécution ratée y rend la copie d'avant (`_executer`)."""
    chemin = _SRC_CADRE.joinpath(*nom.split(".")).with_suffix(".py")
    nom_module = "_cadre_" + nom.replace(".", "_") + "_event_store"
    existant = sys.modules.get(nom_module)
    fichier_existant = getattr(existant, "__file__", None)
    if existant is not None and fichier_existant is not None and Path(fichier_existant) == chemin:
        return existant
    return _executer(nom_module, chemin, existant)  # (2) repli PAR CHEMIN, déclaré


def _cadre_d_ici() -> bool:
    """(1) admise : aucun `<_SRC_CADRE>`, ou le `cadre` chargé en vient (`verifier_charge`)."""
    if not (_SRC_CADRE / "__init__.py").is_file():
        return True
    try:  # résolveur absent (None), `cadre` non chargé ou chargé d'un autre arbre : (2)
        return _resolveur().verifier_charge(HERE.parents[1], "cadre") is not None
    except Exception:
        return False


def _cadre_module(nom: str) -> Any:
    """`cadre.<nom>`, mémoïsé sur succès. Jamais `import_module` d'abord (S-01M5CN1KM2) : (1) si
    `_cadre_d_ici()`, sinon ou s'il lève (2) `<_SRC_CADRE>/<nom>.py` (`_charger_par_chemin`)."""
    module = _MODULES_CADRE.get(nom)
    if module is not None:
        return module
    try:
        module = importlib.import_module(f"cadre.{nom}") if _cadre_d_ici() else _charger_par_chemin(nom)
    except Exception:
        module = _charger_par_chemin(nom)
    _MODULES_CADRE[nom] = module
    return module


#: Ce que la couture EXIGE de chaque module — un module qui n'en porte pas un est
#: un paquet `cadre` antérieur à T-00000770.
_PRIMITIVE_CADRE = (("ledger.store", ("refuser_les_liens", "ouvrir_sans_suivre",
                                      "EmplacementRefuse")),
                    ("workspace", ("Workspace",)))


def _manque(module: Any, attributs: tuple[str, ...]) -> list[str]:
    return [a for a in attributs if not callable(getattr(module, a, None))]


def _decrire(module: Any) -> str:
    return f"{getattr(module, '__name__', module)} ({getattr(module, '__file__', '?')})"


def _couture_ledger_store() -> tuple[Any, Any]:
    """`(cadre.ledger.store, cadre.workspace)`, ou l'exception qui dit pourquoi
    la couture manque. Un module TROUVÉ sans la primitive — un paquet `cadre`
    installé antérieur à T-00000770 — n'arrête PAS la couture : elle retente
    PAR CHEMIN (`_charger_par_chemin`, binôme F2) et mémoïse la copie qui répond ;
    elle ne lève que si la copie par chemin échoue AUSSI, en nommant le module
    périmé (`__name__` ET `__file__`). L'appelant range la levée sous
    `seam_missing`, jamais sous `unavailable`."""
    modules = []
    for nom, attributs in _PRIMITIVE_CADRE:
        module = _cadre_module(nom)
        manque = _manque(module, attributs)
        if manque:
            perime = f"{_decrire(module)} does not carry {', '.join(manque)} (older than T-00000770?)"
            try:
                module = _charger_par_chemin(nom)
            except Exception as exc:
                raise AttributeError(f"{perime}; the copy by path failed too: "
                                     f"{type(exc).__name__}: {exc}") from exc
            encore = _manque(module, attributs)
            if encore:
                raise AttributeError(f"{perime}; the copy by path {_decrire(module)} does "
                                     f"not carry {', '.join(encore)} either")
            _MODULES_CADRE[nom] = module
        modules.append(module)
    return modules[0], modules[1]

SCHEMA_VERSION = 1

# Tick interval (spec §A.2: 5 s, inside the daemon's existing loop — no second
# process). A tick that hit `_BATCH_ROW_CAP` reschedules immediately instead of
# sleeping, so boot catch-up drains at I/O speed rather than 5 s per batch.
TICK_SECONDS = 5.0

# Quiescence (spec §A.2, ~2 s) applies to DELETION, not to reading. Reading is
# already safe at any instant because it stops at the last complete line, and
# gating the READ on mtime would add up to one tick of latency to the receiver
# file that is appended to seconds before every tick (iteration 6, C2). What
# needs the quiet window is the unlink: a file still being appended to must not
# be removed under its writer.
_QUIESCENCE_SECONDS = 2.0

# Rows per transaction. Bounds memory and transaction size during the
# dimensioning boot catch-up; the remainder is picked up by the next tick.
_BATCH_ROW_CAP = 20_000

# Deletion retries INSIDE a tick. Deliberately tiny: a skip costs nothing (the
# next tick retries), so there is no reason to block the loop on a handle that
# Windows may hold for a while (L-00000035).
_DELETE_ATTEMPTS = 3
_DELETE_DELAY_SECONDS = 0.01

# os.replace under a concurrent reader on Windows (L-00000054): same bound as
# every other publisher in the kit.
_REPLACE_ATTEMPTS = 30
_REPLACE_DELAY_SECONDS = 0.01

RETENTION_DAYS = 30  # L-00000032

# --- `session_feed` bounds (T-00000086) ------------------------------------
# The session feed is a WINDOW, and every one of its edges is a declared number
# rather than an implicit "everything". Three of them, spelled here because the
# response repeats them back to the caller and the two must not drift.
#
# WHY A WINDOW AT ALL. The question this read answers is "what is happening in
# the consoles", which is a question about the recent past; a store holding 30
# days of rows would otherwise be grouped in full to answer it.
SESSION_FEED_WINDOW_HOURS = 24
# Sessions per response, ranked by `last_ts` DESC — the most recently ACTIVE
# ones, because a feed that dropped the newest sessions when it filled up would
# be showing the wrong end of the window.
SESSION_FEED_MAX_SESSIONS = 50
# Events per session, keeping the LAST ones (they are returned chronologically;
# see `session_feed`). Same reasoning: the tail of a session is what a reader
# watching a console wants.
SESSION_FEED_MAX_EVENTS = 50
# Hard ceilings on a caller-supplied `caps`. A cap exists to bound memory, so a
# caller must not be able to lift it to "all of it" — it may only lower it, or
# raise it inside these walls (the tests raise nothing; they LOWER, which is how
# truncation gets exercised on three rows instead of on fifty-one).
_SESSION_FEED_CAP_CEILING = 500
# Distinct `host` / `project` values offered back as filter choices. Bounded for
# the same reason as everything else here, and the truncation is declared.
_SESSION_FEED_MAX_FACETS = 50

# The `by_host` key standing in for a row whose `host` column is NULL. A bucket
# keyed `null` is not expressible in JSON and a bucket keyed `""` renders as a
# blank line that looks like a bug, so the absence is NAMED — and named
# distinctly enough that a real host called "unknown" could never collide with
# it.
SESSION_HOST_ABSENT = "(hôte non déclaré)"

# SQLite knobs (spec §A.2). `busy_timeout` in ms.
_BUSY_TIMEOUT_MS = 5000
_CONNECT_TIMEOUT_SECONDS = 5.0

# "ingestion en retard depuis X" threshold — 12 ticks. Below it, pending spool
# files are simply a tick in flight, not a lag worth shouting about.
_LATE_SECONDS = 60.0

PROJECT_UNSET = "unset"

# The receiver's POSITIVE SENTINEL, referenced rather than re-spelled: the two
# modules must agree on what "this line declares no project" looks like, and a
# second literal is how they would stop agreeing (same reasoning as
# `_MERGED_SUFFIX` below).
PROJECT_UNATTRIBUTED = _otel_receiver_mod.PROJECT_UNATTRIBUTED

# The envelope field the receiver promotes to first level at `persist()`.
_PROJECT_FIELD = "project_id"
_ATTRIBUTED_BY_FIELD = "project_attributed_by"

# `events._MERGED_SUFFIX`, referenced rather than re-spelled: the two modules
# must agree on what a merged legacy file looks like, and a second literal is how
# they would stop agreeing.
_MERGED_SUFFIX = _events_mod._MERGED_SUFFIX

# V1-c: BOTH channels' spools are consumed and removed. Channel B's files were
# retained through V1-b for exactly one reason — `dashboard._read_canal_b` and
# `otel_normalize` still globbed them — and V1-c moves those readers onto this
# store. Keeping the files after that would mean two live sources for one
# figure, which is the shape every duplication defect in this module came from.
_DELETE_CHANNELS = frozenset({"a", "b"})

# T-00000769 (S-00002496/S-00002503): where `export_spool` PREPARES its files,
# next to `exports/` under each channel's spool directory. No ingester glob
# reaches it (`*.jsonl`, `exports/*/*.jsonl`), and it is promoted to
# `exports/<stamp>/` only once the database is retired — see `export_spool`.
_EXPORTS_PARTIAL = "exports.partial"

# Windows has no `ps`: the daemon pid's command line cannot be read there.
_IS_WINDOWS = os.name == "nt"

# The daemon states `main --export-spool` refuses under (T1 of critic-opus,
# S-00002502 — pre-existing, CRITICAL on the one rescue path). `unresponsive` is
# a `stale` verdict whose pid is ALIVE: the ping is silent, but the process may
# still hold the store (HIGH of both critics, round 2, S-00002536).
_DAEMON_REFUSED_STATES = frozenset({"alive", "unresponsive"})


def _daemon_refusal_reason(state: str, pid: int | None) -> str:
    """What `main --export-spool` says when it refuses under a daemon — with a
    remedy that works for BOTH states: `dashboard_daemon.py --stop` answers
    `not-running` for a daemon whose ping is silent, so the pid is PRINTED,
    with the check that tells a recycled pid apart (round 3, S-00002562: the
    remedy used to make the operator kill whatever process held that pid)."""
    what = ("ALIVE (pid alive, ping answered)" if state == "alive" else
            "UNRESPONSIVE (pid alive, ping unanswered — it may still hold the store)")
    shown = str(pid) if pid is not None else "<pid>"
    if _IS_WINDOWS:
        # No `ps` here (T3 of critic-fable, final): `tasklist` names the image
        # only, the command line is in the Task Manager's Details tab.
        check = (f"look pid {shown} up — `tasklist /FI \"PID eq {shown}\"`, and its "
                 f"command line in the Task Manager (Details tab, Command line "
                 f"column)")
    else:
        check = f"read its command line with `ps -p {shown} -o command=`"
    return (
        f"the dashboard daemon of this project is {what}, pid {shown}: it ingests "
        f"exports/*/*.jsonl and deletes the files, keeps events.db open (its WAL "
        f"would stay behind under the old name at the retire) and re-creates an "
        f"empty store — an export under it loses the history it exists to keep. "
        f"Stop it first (`python3 .agents/bin/dashboard_daemon.py --stop`). If "
        f"`--stop` answers not-running, {check}: if it IS this project's daemon "
        f"(dashboard_daemon.py with --root <this project>), end pid {shown}; if it "
        f"does not show dashboard_daemon.py, the pid was recycled: delete "
        f".agents/state/local/dashboard.lock — never kill a process that is not the "
        f"daemon, never delete the lock of a live daemon. Make sure no session "
        f"restarts it meanwhile: the SessionStart hook relaunches it"
    )

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY,
        project     TEXT NOT NULL,
        "user"      TEXT,
        channel     TEXT NOT NULL,
        src_file    TEXT NOT NULL,
        line_index  INTEGER NOT NULL,
        line_hash   TEXT NOT NULL,
        day         TEXT NOT NULL,
        ts          TEXT,
        kind        TEXT,
        host        TEXT,
        sid         TEXT,
        -- `prompt_id`, NOT os.getpid(): the canal-B join key that the JSONL
        -- envelope calls `pid`. Renamed in the schema precisely because that
        -- short name is conflated with the process id twice in events.py's own
        -- comments; a column name is a good place to stop the confusion.
        prompt_id   TEXT,
        aid         TEXT,
        task        TEXT,
        agent       TEXT,
        effort      TEXT,
        body        TEXT NOT NULL,
        ingested_at TEXT NOT NULL
    )
    """,
    # THE identity. See the module docstring for why each of the four columns
    # is in it; removing any one of them reopens a named, tested defect.
    'CREATE UNIQUE INDEX IF NOT EXISTS events_identity '
    'ON events (project, src_file, line_index, line_hash)',
    "CREATE INDEX IF NOT EXISTS events_day ON events (day)",
    "CREATE INDEX IF NOT EXISTS events_channel_id ON events (channel, id)",
    "CREATE INDEX IF NOT EXISTS events_ts ON events (ts)",
    "CREATE INDEX IF NOT EXISTS events_task ON events (task)",
    "CREATE INDEX IF NOT EXISTS events_kind ON events (kind)",
    "CREATE INDEX IF NOT EXISTS events_agent ON events (agent)",
    # Digests are a DEDICATED TABLE, not the `state/events/digest/*.json` files
    # (iteration 1, C3: those files freeze the moment the ingestion empties the
    # spool, and a frozen aggregate that still renders is worse than an absent
    # one). Folded from the exact rows the retention pass deletes, in the same
    # transaction — so a day can never be counted twice nor lost.
    """
    CREATE TABLE IF NOT EXISTS digests (
        month     TEXT NOT NULL,
        dimension TEXT NOT NULL,
        key       TEXT NOT NULL DEFAULT '',
        count     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (month, dimension, key)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS digest_days (
        month TEXT NOT NULL,
        day   TEXT NOT NULL,
        PRIMARY KEY (month, day)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    ) WITHOUT ROWID
    """,
)

_INSERT_SQL = (
    'INSERT OR IGNORE INTO events '
    '(project, "user", channel, src_file, line_index, line_hash, day, ts, '
    ' kind, host, sid, prompt_id, aid, task, agent, effort, body, ingested_at) '
    'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
)

_DIGEST_LABEL = (
    "monthly digests folded from events older than 30 days (L-00000032). COUNTS "
    "ONLY — a digest is a summary, never a second archive. Folded from the exact "
    "rows the retention pass deletes, inside the same transaction."
)


# ---------------------------------------------------------------------------
# Spool reading — the one place a rank and a hash are assigned.
# ---------------------------------------------------------------------------

class _SpoolState:
    """Resume point for one spool file, IN MEMORY ONLY.

    Deliberately not persisted. A persisted offset would be a second anchor for
    an identity the database already owns, and the rollback path removes the
    database while leaving the spool — the exact false-anchor shape L-00000057
    describes. Losing these on a restart costs one re-read, which `INSERT OR
    IGNORE` makes free.

    Resume-by-offset is SAFE here, and only here, because a spool file is
    append-only and single-writer by construction (`events._day_file` /
    `otel_receiver._day_file` give each process its own filename). The
    truncate-then-rewrite hazard that would make an offset lie does not exist;
    the residual — a file that SHRANK — is detected and answered with a full
    re-read from zero (iteration 6, C3).
    """

    __slots__ = ("offset", "line_index", "identity")

    def __init__(self, offset: int, line_index: int, identity: int | None) -> None:
        self.offset = offset
        self.line_index = line_index
        self.identity = identity


def _file_identity(stat_result: os.stat_result) -> int | None:
    """`st_ino` — the file index on Windows, the inode on POSIX. A recreated
    file gets a new one, which is the second, independent way this module
    notices that a NAME has been reused by a fresh incarnation. Not used as the
    primary guard (see `_purge_after_delete`); `None` on a filesystem that does
    not report it, in which case shrink detection carries the load alone.

    Deliberately NOT `st_ctime`: on POSIX that changes on every write, so
    keying on it would force a full re-read every tick — O(day^2) I/O, the
    exact cost iteration 6's C3 rejected."""
    ino = getattr(stat_result, "st_ino", 0)
    return int(ino) if ino else None


def _read_spool_lines(
    path: Path, start_offset: int, start_index: int
) -> tuple[list[tuple[int, bytes]], int, int, int]:
    """Read `path` from `start_offset` to EOF and return
    `(items, end_offset, next_index, unreadable)` where each item is
    `(line_index, raw_line_bytes)` with the trailing b"\\n" stripped.

    Only the bytes up to the RIGHTMOST b"\\n" in what was read are consumed:
    a trailing line without its newline is a write in flight and is left
    entirely alone, offset included, so the next tick sees it whole (exit
    criterion 4, and the same rule as `dashboard_readers.read_new_records`).

    Blank lines consume a rank and yield no item — a rank must not shift
    depending on what happened to parse, or the identity moves under the row.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(start_offset)
            chunk = handle.read()
    except OSError:
        return [], start_offset, start_index, 1
    if not chunk:
        return [], start_offset, start_index, 0
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        return [], start_offset, start_index, 0
    consumable = chunk[: last_nl + 1]
    # `consumable` ends with b"\n" by construction, so split()'s last element is
    # always the empty artifact of that fact, never a real line.
    parts = consumable.split(b"\n")[:-1]
    items: list[tuple[int, bytes]] = []
    index = start_index
    for raw in parts:
        rank = index
        index += 1
        if not raw:
            continue
        items.append((rank, raw))
    return items, start_offset + len(consumable), index, 0


def _line_hash(raw: bytes) -> str:
    """sha256 of the raw line BYTES, newline excluded. Pinned recipe — see the
    module docstring's `line_hash` bullet (iteration 3, C4)."""
    return hashlib.sha256(raw).hexdigest()


def _unlink_with_retry(path: Path) -> bool:
    """True if the file is gone, False if it is not — NEVER an exception.
    Exit criterion 2: a `PermissionError` from a still-open Windows handle
    (L-00000035, L-00000054) is a skip, and a skip is free because the next
    tick retries and a re-read is deduplicated."""
    for attempt in range(_DELETE_ATTEMPTS):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return True  # someone else got there first — same end state
        except OSError:
            if attempt + 1 < _DELETE_ATTEMPTS:
                time.sleep(_DELETE_DELAY_SECONDS)
    return not path.exists()


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


# ---------------------------------------------------------------------------
# Project identity.
# ---------------------------------------------------------------------------

def project_json_path() -> Path:
    """`.agents/state/project.json` (T-00000048), resolved through the same
    anchor as the database so one env redirect moves both. `AGENTS_PROJECT_JSON`
    overrides the whole path — the SAME env var `otel_receiver.py` honours, so
    one redirect pins the writer's identity and this classifier to one file."""
    override = os.environ.get("AGENTS_PROJECT_JSON")
    if override:
        return Path(override)
    return _events_mod.events_db_path().parent.parent / "project.json"


def project_id_from_data(data: Any) -> str:
    """THE recipe for "which `project_id` does this identity object declare",
    as a PURE function of ALREADY-PARSED data: no read, no parse, no exception.

    Extracted from `resolve_project_id()` verbatim (T-00000051, V1-d) with NO
    change of behaviour — `.strip()` is required and applied, and anything else
    (absent key, non-str, blank-only) is `PROJECT_UNSET`. It became a function
    of its own because `/api/projects` must publish the id AND the `name`/`slug`
    read from the SAME parse: a second reader re-deriving the strip and the
    fallback would be a SECOND recipe, and two recipes are how a route starts
    naming an id under which no row was ever stored (plan-critic iteration 4,
    C1). `resolve_project_id()` below is now the thin read+parse wrapper around
    this, so there is one recipe and one place it can change."""
    if isinstance(data, dict):
        value = data.get("project_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return PROJECT_UNSET


def resolve_project_id() -> str:
    """The `project_id` written by `project_init.py`, or `PROJECT_UNSET`.

    Never raises and never invents an id: a generated-here value would be a
    second identity for the same repo, and `project_id` is the ONE
    infalsifiable key a future distant merge has (spec §A.1).

    Thin by design since V1-d: read + parse + `project_id_from_data()`. The
    capture below stays exactly as it was — `UnicodeDecodeError` and
    `json.JSONDecodeError` are both subclasses of `ValueError`, so a project.json
    in non-UTF-8 bytes has always landed on `PROJECT_UNSET` here rather than
    escaping."""
    try:
        data = json.loads(project_json_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return PROJECT_UNSET
    return project_id_from_data(data)


# ---------------------------------------------------------------------------
# Foreign-project quarantine (V1-c, T-00000050) — ONE pure classifier, used at
# all four points of a row's life cycle.
# ---------------------------------------------------------------------------

def declared_project_of(body: str | dict[str, Any] | None) -> str | None:
    """The promoted first-level `project_id` of one spool line, or None when
    the line does not carry the field (pre-V1-c, canal A, an operator-written
    fixture). Takes the raw body TEXT — the same bytes the row stores — so no
    caller has to reproduce the parse."""
    record: Any = body
    if isinstance(body, str):
        try:
            record = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(record, dict):
        return None
    value = record.get(_PROJECT_FIELD)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def classifier_reads_body(channel: str, own_project_id: str) -> bool:
    """True iff `declares_foreign_project` parses `body` (T-00000616).

    Its early return, named ONCE so that a caller who wants to skip reading a
    body it does not need — the retention fold, which reads a body by id only
    for a row this returns True for — cannot drift from the classifier. When
    this is False the classifier returns False whatever the body holds, which
    is exactly what `test_classifier_reads_body_is_the_classifiers_own_early_return`
    pins over every channel x own-id combination."""
    return channel == "b" and own_project_id != PROJECT_UNSET


def declares_foreign_project(channel: str, body: str | dict[str, Any] | None,
                             own_project_id: str) -> bool:
    """Does this line belong to ANOTHER project? THE classifier — and the one
    place the V1-c invariant lives.

    ═══ INVARIANT, NON-NEGOTIABLE (plan-critic iteration 4, C2) ═══
    This is a PURE FUNCTION of (a) the line's own bytes and (b) the immutable
    `project_id` of `.agents/state/project.json`. It NEVER consults the store's
    runtime identity, the current working directory, a path, or a clock.

    WHY that is not a stylistic preference: `project` is one of the four
    columns of the UNIQUE index (`events_identity`, see the module docstring),
    and the resume offsets do NOT survive the process. So the same physical
    line WILL be offered again after a restart, and if its `project` value
    could differ between the two readings, `INSERT OR IGNORE` has nothing to
    match and the audit trail gains a second row for one event. A classifier
    that depended on a mutable runtime identity would re-open, by a new road,
    the double-count V1-b spent seven plan iterations closing.

    THE FOUR CASES, and each "never" is a named defect if inverted:
      * field ABSENT        -> never foreign. Canal A carries no such field at
        all, and a pre-V1-c canal-B line predates the mechanism. Reading
        absence as "not mine" would quarantine the entire history at the first
        restart after the flip (iteration 3, C1).
      * NOT A REAL ID       -> never foreign. Two literals qualify: the
        SENTINEL `"unattributed"` ("this host cannot declare a project" —
        Codex; any host whose env block is not pasted yet) and `PROJECT_UNSET`
        `"unset"` ("no identity"). Neither NAMES another project, so neither can
        mean "not mine". Reading the sentinel as foreign would send EVERY
        un-patched host's spend into quarantine, out of the totals — silent and
        massive (iteration 8, C4; the gate's MUST-FIX M1 pins BOTH literals by
        name in `test_sentinel_is_never_foreign`, asserting the VALUE stamped
        and not merely the absence of a quarantine).
      * own id is UNSET     -> never foreign. A repo with no identity cannot
        own anything, so it cannot disown anything either. (It also cannot be
        a receptacle: nothing is whitened into a local id that does not exist.)
      * declared != own id  -> FOREIGN. The only positive case.

    Channel A is excluded outright: its envelopes are the kit's OWN hook
    events, written by this repo's hooks into this repo's spool.

    Both "never" guards above that need no body — channel A, own id UNSET — are
    `classifier_reads_body`, so the fold's by-id body read follows this
    function by construction rather than by a copy of its condition.
    """
    if not classifier_reads_body(channel, own_project_id):
        return False
    declared = declared_project_of(body)
    if declared is None or declared in (PROJECT_UNATTRIBUTED, PROJECT_UNSET):
        return False
    return declared != own_project_id


# ---------------------------------------------------------------------------
# Dirty-file notices — a LATENCY HINT and nothing else.
# ---------------------------------------------------------------------------

_dirty_lock = threading.Lock()
_dirty_files: set[str] = set()
_dirty_event = threading.Event()


def notify_dirty(path: str | Path | None = None) -> None:
    """"A spool file just grew." Wakes the tick early; carries NO rank and NO
    content. The receiver used to keep its own in-memory line counter and hand
    it over — that counter started at 0 whenever the process did, so it drifted
    from the file's own truth and produced a second identity for the same line
    (iteration 5, C4). The authority is the ingestion reading the file; this is
    a doorbell.

    Fail-open: called from `otel_receiver.persist()`, which must never raise."""
    try:
        if path is not None:
            with _dirty_lock:
                _dirty_files.add(str(path))
        _dirty_event.set()
    except Exception:  # noqa: BLE001 - a doorbell must never break the writer
        pass


def take_dirty_notices() -> set[str]:
    with _dirty_lock:
        taken = set(_dirty_files)
        _dirty_files.clear()
    _dirty_event.clear()
    return taken


# ---------------------------------------------------------------------------
# `session_feed` pure helpers — the window and the caps, resolved OUTSIDE the
# database so both are testable without a store and so a malformed input can
# never reach an SQL parameter as anything but a bounded string/int.
# ---------------------------------------------------------------------------

def _session_ts(moment: datetime) -> str:
    """The EXACT stamp format canal A writes (`events.py:480`). Spelled here
    rather than derived with `isoformat()`, which would emit `+00:00` and
    compare wrong against a column full of `Z` — the window is a STRING range
    over an index, and a second format is a silently empty result."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_feed_window(since: str | datetime | None,
                         now: datetime) -> dict[str, Any]:
    """`{since, until, requested_since, clamped_to_retention, hours,
    retention_days}`.

    An UNPARSEABLE `since` is not an error and not a silent default either: it
    falls back to the default window and says so through `requested_since`,
    which keeps the caller's own string visible in the response. The clamp is
    the interesting one — see `session_feed`'s docstring."""
    default_since = now - timedelta(hours=SESSION_FEED_WINDOW_HOURS)
    requested: str | None = None
    resolved = default_since
    if isinstance(since, datetime):
        resolved = since
        requested = _session_ts(since)
    elif isinstance(since, str) and since.strip():
        requested = since.strip()
        try:
            parsed = datetime.fromisoformat(requested.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            resolved = parsed
    floor = now - timedelta(days=RETENTION_DAYS)
    clamped = resolved < floor
    if clamped:
        resolved = floor
    return {
        "since": _session_ts(resolved),
        "until": _session_ts(now),
        "requested_since": requested,
        "clamped_to_retention": clamped,
        "hours": SESSION_FEED_WINDOW_HOURS,
        "retention_days": RETENTION_DAYS,
    }


def _session_feed_caps(caps: dict[str, Any] | None) -> dict[str, int]:
    """The two caps, sanitised. A non-integer, a zero or a negative falls back
    to the default rather than becoming an unbounded `LIMIT`; anything above
    `_SESSION_FEED_CAP_CEILING` is lowered to it. A caller may narrow this
    read; it may not turn it into a full-table group-by."""
    resolved = {"sessions": SESSION_FEED_MAX_SESSIONS,
                "events_per_session": SESSION_FEED_MAX_EVENTS}
    for key in resolved:
        value = (caps or {}).get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value < 1:
            continue
        resolved[key] = min(value, _SESSION_FEED_CAP_CEILING)
    return resolved


# ---------------------------------------------------------------------------
# The store.
# ---------------------------------------------------------------------------

class EventStore:
    """A handle on `events.db`. `status` is a CLOSED vocabulary:

      * `ok`           — schema v1, readable and writable.
      * `absent`       — no database yet (the honest first-run state).
      * `schema_ahead` — `user_version` > 1: a NEWER kit wrote this file. The
        connection is already closed; no v1 statement will ever touch it.
      * `unavailable`  — unreadable, corrupt, or a version-0 non-empty file we
        refused to interpret.

    Every method is safe to call in every status: a non-`ok` store returns a
    known-shape degraded payload rather than raising (iteration 2, C1).
    """

    def __init__(self, path: Path, conn: sqlite3.Connection | None,
                 status: str, reason: str | None, user_version: int | None) -> None:
        self.path = path
        self._conn = conn
        self.status = status
        self.reason = reason
        self.user_version = user_version
        self.project = PROJECT_UNSET
        self._offsets: dict[str, _SpoolState] = {}
        self._boot_backlog: int | None = None
        # V1-c: what the two one-time passes at open actually did — the
        # JOURNAL half of the backfill's must-fix (M2). Empty on a reader open
        # (`create=False`), which runs neither pass.
        self.open_report: dict[str, Any] = {}
        # `(first id, last id, rows, last line_hash)` of the last COMPLETE `iter_canal_b_bodies` (T-01M5T5G6MR).
        self.canal_b_lu: tuple[Any, Any, int, Any] | None = None
        # Test seams — named because plan-critic iteration 1, C6 asked for one:
        # the daemon-side mechanics are untestable if the only entry point is a
        # 5 s thread. `before_commit_hook` / `after_commit_hook` let a test
        # stand exactly in the two crash windows the ordering argument names.
        self.before_commit_hook: Callable[[], None] | None = None
        self.after_commit_hook: Callable[[], None] | None = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection | None:
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def degraded_reason(self) -> str | None:
        return self.reason

    # -- ingestion ---------------------------------------------------------

    def ingest_once(self, now: datetime | None = None) -> dict[str, Any]:
        """One tick: read -> INSERT batch in one transaction -> COMMIT ->
        delete. THE NAMED SEAM (iteration 1, C6): the 5 s thread only calls
        this, so every mechanism above is reachable from a test synchronously.

        Never raises for a data-shaped problem. A genuine sqlite failure is
        reported in the returned dict (`error`), the transaction is rolled
        back, and no offset advances — so the next tick simply retries."""
        started = time.perf_counter()
        now = now or datetime.now(timezone.utc)
        now_epoch = now.timestamp()
        report: dict[str, Any] = {
            "status": self.status,
            "files_scanned": 0,
            "files_read": 0,
            "rows_offered": 0,
            "rows_inserted": 0,
            "duplicates_ignored": 0,
            "unreadable_files": 0,
            "reread_from_zero": 0,
            "deleted": 0,
            "delete_deferred": 0,
            "delete_skipped_appended": 0,
            "delete_skipped_quiescence": 0,
            "batch_truncated": False,
            "residue_skipped": 0,
            "delete_skipped_residue_pending": 0,
            "retention": {"rows_folded": 0, "days_folded": [],
                          "rows_retained_pending_spool": 0,
                          "foreign_held_expired": 0},
            "boot_backlog_files": self._boot_backlog,
            "error": None,
        }
        if self.status != "ok" or self._conn is None:
            report["reason"] = self.reason
            report["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
            return report

        take_dirty_notices()  # the doorbell has been answered by this very tick

        sources, residue = self._source_files()
        report["files_scanned"] = len(sources)
        report["residue_skipped"] = len(residue)
        if self._boot_backlog is None:
            # The dimensioning case, measured ONCE and remembered: a daemon that
            # was dead for a day comes back to hundreds of files. Recorded so
            # the Couverture view can say how far behind this boot started.
            self._boot_backlog = len(sources)
            report["boot_backlog_files"] = self._boot_backlog

        rows: list[tuple] = []
        processed: list[tuple[str, str, Path, int, int, int | None]] = []
        user = _resolve_user()
        ingested_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for channel, key, path in sources:
            if len(rows) >= _BATCH_ROW_CAP:
                report["batch_truncated"] = True
                break
            try:
                stat_result = path.stat()
            except OSError:
                report["unreadable_files"] += 1
                continue
            state = self._offsets.get(key)
            offset, index, identity = 0, 0, _file_identity(stat_result)
            if state is not None:
                offset, index = state.offset, state.line_index
                if self._is_new_incarnation(state, stat_result, identity):
                    offset, index = 0, 0
                    report["reread_from_zero"] += 1
            items, end_offset, next_index, unreadable = _read_spool_lines(path, offset, index)
            report["unreadable_files"] += unreadable
            if unreadable:
                continue
            report["files_read"] += 1
            for rank, raw in items:
                rows.append(self._row(channel, key, rank, raw, user, ingested_at, path))
            processed.append((channel, key, path, end_offset, next_index, identity))

        report["rows_offered"] = len(rows)

        cursor_before = self._conn.total_changes
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                if rows:
                    self._conn.executemany(_INSERT_SQL, rows)
                inserted = self._conn.total_changes - cursor_before
                # The retention pass must know which spool files are STILL ON
                # DISK, because a row whose source can still be re-offered must
                # not be folded away (see `_fold_retention_locked`). Taken from
                # this tick's own scan — one glob, two uses.
                fold = self._fold_retention_locked(
                    now, frozenset(key for _channel, key, _path in sources))
                # `inserted` predates the fold's DELETE (it counts too). T-00000615: a row
                # in or out moves the cache key; the per-tick meta write below never does.
                if inserted or fold["rows_folded"]:
                    self._bump_meta_counter_locked("data_generation", 1)
                if fold["rows_folded"]:  # T-01M5T5G6MR: rows left from below the dashboard's watermark
                    self._bump_meta_counter_locked("rewrite_generation", 1)
                self._write_meta_locked(now, report, fold)
                if self.before_commit_hook is not None:
                    # Crash window #1: killed here, the whole transaction is
                    # rolled back and the spool files are untouched.
                    self.before_commit_hook()
                self._conn.execute("COMMIT")
            except BaseException:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        except sqlite3.Error as exc:
            report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            report["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
            return report

        report["rows_inserted"] = inserted
        report["duplicates_ignored"] = len(rows) - inserted
        report["retention"] = fold

        # Offsets advance ONLY after a successful COMMIT. Before it, a crash
        # must leave the reader exactly where it was.
        for channel, key, path, end_offset, next_index, identity in processed:
            self._offsets[key] = _SpoolState(end_offset, next_index, identity)

        if self.after_commit_hook is not None:
            # Crash window #2: killed here, the rows are durable and the files
            # are still on disk. The re-read is absorbed by INSERT OR IGNORE.
            self.after_commit_hook()

        # RESIDUE FIRST, AND IT GATES THE MERGED FILE. Residue carries no unread
        # bytes by construction (see `_source_files`), so it needs no re-stat and
        # no quiescence window — but it is still retry-or-skip.
        #
        # The ordering is load-bearing, and the third defect this module's own
        # tests found: residue is only RECOGNISABLE as residue while its day's
        # `D.merged.jsonl` still exists. Delete the merged file first and a
        # stuck original becomes, on the next tick, an ordinary new source with
        # its own `src_file` — a second row for every event of that day. So a
        # merged file whose day still has residue is NOT deleted. Bounded (one
        # day's merged file), visible (`residue_skipped`), and no double count.
        blocked_days: set[str] = set()
        for path in residue:
            if _unlink_with_retry(path):
                report["deleted"] += 1
            else:
                report["delete_deferred"] += 1
                blocked_days.add(path.name[:_DAY_LEN])
        self._delete_consumed(processed, now_epoch, report, blocked_days)
        report["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return report

    def _is_new_incarnation(self, state: _SpoolState, stat_result: os.stat_result,
                            identity: int | None) -> bool:
        """Has the NAME been reused by a different file since we last read it?

        Two independent signals, because one is not enough:
          * the file SHRANK below our offset — an append-only file cannot do
            that, so the name now points at something else;
          * `st_ino` changed — catches the case shrink cannot, a file recreated
            at a size at or beyond the old offset (a reused pid recreating the
            same filename), which would otherwise silently skip its first bytes.

        The PRIMARY guard is neither of these: it is that a SUCCESSFUL delete
        purges the entry outright, so a reappearing name has no residual offset
        to cross in the first place. See `_delete_consumed`."""
        if stat_result.st_size < state.offset:
            return True
        if (state.identity is not None and identity is not None
                and identity != state.identity):
            return True
        return False

    def _delete_consumed(self, processed: list[tuple[str, str, Path, int, int, int | None]],
                         now_epoch: float, report: dict[str, Any],
                         blocked_days: set[str] | None = None) -> None:
        """Post-COMMIT deletion of FULLY CONSUMED, QUIESCENT channel-A spool
        files. Three refusals, each a named defect if dropped:

          * size != our consumed offset -> the writer appended between our read
            and now, and those bytes were never read. Deleting here would lose
            them (iteration 1, C2 — re-stat before every unlink).
          * modified less than `_QUIESCENCE_SECONDS` ago -> a writer may still
            be mid-append; wait a tick.
          * unlink failed -> skip, never raise (exit criterion 2).

        MUST-FIX C1 lives here: on a SUCCESSFUL delete the resume entry is
        PURGED. Any later reappearance of that name is therefore a brand-new
        incarnation read from zero, and cannot inherit an offset that would make
        it skip its own first lines."""
        blocked_days = blocked_days or set()
        for channel, key, path, end_offset, _next_index, _identity in processed:
            if channel not in _DELETE_CHANNELS:
                continue
            if (path.name.endswith(_MERGED_SUFFIX)
                    and path.name[:_DAY_LEN] in blocked_days):
                # Keeping this file is what keeps its day's stuck original
                # RECOGNISABLE as residue instead of ingestable as a new source.
                report["delete_skipped_residue_pending"] = (
                    report.get("delete_skipped_residue_pending", 0) + 1)
                continue
            try:
                stat_result = path.stat()
            except OSError:
                # Already gone — same end state as a successful delete, so the
                # same purge applies.
                self._offsets.pop(key, None)
                continue
            if stat_result.st_size != end_offset:
                report["delete_skipped_appended"] += 1
                continue
            if now_epoch - stat_result.st_mtime < _QUIESCENCE_SECONDS:
                report["delete_skipped_quiescence"] += 1
                continue
            if _unlink_with_retry(path):
                self._offsets.pop(key, None)  # MUST-FIX C1
                report["deleted"] += 1
            else:
                report["delete_deferred"] += 1

    def _row(self, channel: str, key: str, rank: int, raw: bytes,
             user: str | None, ingested_at: str, path: Path) -> tuple:
        """One INSERT tuple. `_INSERT_SQL` is the store's ONLY insertion site
        and this method its only feed, which is what makes the quarantine below
        a property of the schema rather than of a code path.

        QUARANTINE AT BIRTH (V1-c, plan-critic iteration 3, C2). A canal-B line
        whose body declares ANOTHER project's id is stamped `PROJECT_UNSET`
        instead of this store's project, at the moment it becomes a row.
        Defining the quarantine anywhere later does not work: a pre-init
        day-file that survived a failed delete (L-00000035) and is re-read
        after the identity exists would be re-inserted under the real id with
        NO dedup collision (`project` is in the UNIQUE key) — one duplicate row
        AND a foreign event whitened into local spend. Same leak on the
        export -> re-ingestion round trip.

        `_row` reads `project_id`, NEVER `provenance` (iteration 3, C1): the
        provenance of every pre-V1-c envelope is an absolute PATH, so
        classifying on it would call the whole history foreign at the first
        restart after the flip."""
        body = raw.decode("utf-8", errors="replace")
        record: dict[str, Any] = {}
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                record = parsed
        except (json.JSONDecodeError, ValueError):
            record = {}
        ts = record.get("ts") if isinstance(record.get("ts"), str) else None
        kind = record.get("kind") if isinstance(record.get("kind"), str) else None
        if channel == "b" and kind:
            # Canal-B envelopes use `metrics` / `logs` / `failure`, which are
            # NOT members of canal A's closed KNOWN_KINDS vocabulary. Namespaced
            # so one column can hold both without a reader ever mistaking an
            # OTLP payload kind for a hook event kind.
            kind = f"otel.{kind}"
        # `self.project` is the project.json id, resolved ONCE at open and
        # FROZEN for the life of this object (see `open_store`) — which is why
        # handing it to a pure classifier keeps the invariant above intact.
        project = self.project
        if declares_foreign_project(channel, record, self.project):
            project = PROJECT_UNSET
        return (
            project,
            record.get("user") if isinstance(record.get("user"), str) else user,
            channel,
            key,
            rank,
            _line_hash(raw),
            _day_of(ts, path, ingested_at),
            ts,
            kind,
            _text_or_none(record.get("host")),
            _text_or_none(record.get("sid")),
            _text_or_none(record.get("pid")),  # prompt_id — never os.getpid()
            _text_or_none(record.get("aid")),
            _text_or_none(record.get("task")),
            _text_or_none(record.get("agent")),
            _text_or_none(record.get("effort")),
            body,
            ingested_at,
        )

    def _source_files(self) -> tuple[list[tuple[str, str, Path]], list[Path]]:
        """`(sources, residue)` where a source is `(channel, src_file_key, path)`.

        `exports/*/` is included: `--export-spool` writes there, and an export
        re-ingested is idempotent by the same identity as everything else (its
        `src_file` key is stable, and `export_spool` never exports a row whose
        original file is still on disk — so an original and its export can never
        both count). `exports.partial/` is NOT, deliberately (T-00000769): it
        holds an export whose database is not retired yet, and ingesting it
        would count its rows a second time on top of the database's own.

        RESIDUE — a per-writer file for a PAST day that sits next to that day's
        `D.merged.jsonl` — is NOT a source. It is skipped and queued for
        deletion. Found by this module's own retention test, which forced the
        migration's unlink of an original to fail: the merged file and its
        surviving original are two `src_file`s carrying the SAME lines, so
        ingesting both double-counts every event of that day — precisely the
        legacy triangle of plan-critic iteration 5, C2, arriving through a failed
        unlink instead of a crash.

        Skipping needs no line-by-line comparison, because `merge_day_files`
        publishes the merged file (fsync -> replace) BEFORE unlinking any source,
        and a file named `D.*` is only ever appended by a process whose own clock
        still says day D (events.py's `_day_file`). So once D has passed, the
        existence of `D.merged.jsonl` PROVES every `D.<host>.<pid>.jsonl` line is
        already inside it."""
        out: list[tuple[str, str, Path]] = []
        residue: list[Path] = []
        for channel, base in (("a", _events_dir()), ("b", _otel_dir())):
            if base is None:
                continue
            try:
                if not base.exists():
                    continue
                names = sorted(base.glob("*.jsonl"))
                exported = sorted(base.glob("exports/*/*.jsonl"))
            except OSError:
                continue
            merged_days = {
                path.name[:_DAY_LEN] for path in names
                if path.name.endswith(_MERGED_SUFFIX) and _looks_like_day(path.name[:_DAY_LEN])
            }
            for path in names:
                if (merged_days and not path.name.endswith(_MERGED_SUFFIX)
                        and path.name[:_DAY_LEN] in merged_days):
                    residue.append(path)
                    continue
                out.append((channel, f"{channel}/{path.name}", path))
            for path in exported:
                try:
                    rel = path.relative_to(base).as_posix()
                except ValueError:  # pragma: no cover - glob guarantees it
                    continue
                out.append((channel, f"{channel}/{rel}", path))
        return out, residue

    # -- retention + digests ----------------------------------------------

    def _fold_retention_locked(self, now: datetime,
                               live_sources: frozenset[str]) -> dict[str, Any]:
        """Fold rows older than `RETENTION_DAYS` into the digests table and
        delete exactly those rows — same transaction, same statement scope.

        Folding the ROWS WE DELETE (rather than "a day not yet in `days_folded`") is what makes this both
        idempotent and complete: a late spool file carrying a very old day is folded when it is deleted, not
        skipped because its day was already marked. `digest_days` is a display list, never a guard.

        A ROW WHOSE SPOOL FILE IS STILL ON DISK IS NEVER FOLDED. Found by this
        module's own retention test, and it is the same class of defect
        plan-critic spent seven iterations on, arriving by a new road: fold and
        delete a row, and its identity leaves the UNIQUE index; the spool file
        that produced it is then re-read after a restart (a delete that keeps
        failing, L-00000035), `INSERT OR IGNORE` has nothing left to match, the
        row comes back, and the next fold counts it AGAIN. Unbounded
        over-counting of the audit trail from a single stuck file.

        The invariant, stated positively: a row may be folded only once its
        source can no longer re-offer it, and "can no longer re-offer it" means
        the file is gone. Bounded and visible — the count of rows held back is
        reported as `rows_retained_pending_spool`. Under V1-b that also meant
        channel-B rows were never folded, because their files were retained by
        design; V1-c consumes and deletes channel B's spool too, so those rows
        now fold like any other.

        A `foreign_held` ROW IS DELETED WITHOUT BUMPING ANY LOCAL DIGEST
        (V1-c, iteration 9's re-opened C3 — iteration 3's C3 arriving by a
        change of scope). The quarantined rows are a NEIGHBOURING project's
        events; letting them expire through the ordinary path would fold them
        into the LOCAL monthly digests (`total`, `kind:otel.*`), i.e. inflate
        this project's own durable audit trail with another project's traffic —
        permanently, since a digest is all that survives the 30-day window.
        They are counted instead into the cumulative `meta` key
        `foreign_held_expired`, which SURVIVES A RESTART (a per-tick counter
        would say nothing the morning after, iteration 4, C5).

        What is deliberately NOT here, and where it went: the digests carry no
        cost/token SUMS and no `provenance` dimension, so an expired foreign row
        leaves a COUNT and not a trace of what it cost. Declared, not
        discovered — that is T-00000054's charter (pilot decision S-00000110),
        and it is why the cost view's 30-day truncation is displayed as
        temporary rather than presented as complete.

        STREAMED, NEVER fetchall() (T-00000616 — the THIRD site of
        T-00000613's defect, after `iter_canal_b_bodies` and
        `_backfill_promote_project_field`). This runs on EVERY tick, inside the
        daemon's `BEGIN IMMEDIATE`, and it used to pull every row past the
        cutoff WITH its `body` into one list: measured at 2,000 rows x 20 KB, a
        40.82 MB peak during the fold against 0.11 MB for a streamed loop over
        the same rows. The bound of that figure, stated rather than implied: it
        is the PYTHON HEAP as `tracemalloc` sees it — RSS and SQLite's own page
        cache are NOT measured.
        `body` cannot simply leave the fold, and that was measured too: the
        classifier (`declares_foreign_project`) parses it for every channel-`b`
        row once the own id is set — it is how an expired `foreign_held` row
        stays out of the local digests
        (`test_expired_foreign_row_is_deleted_without_bumping_a_local_digest`).
        So the candidate SELECT carries NO body, and a row that is about to be
        folded AND for which `classifier_reads_body` holds (channel `b`, own id
        set) reads its own body by id, one row at a time. That predicate is the
        classifier's own early return, SHARED rather than copied, so the rows
        that pay the read cannot drift from the rows the classifier parses.
        A HELD row (its spool file still on disk) never has its body read at
        all — it would otherwise be re-read on every tick until the file goes.
        What stays O(rows) by design: the `ids` array (`array("q")`, 8 bytes a row instead of one int object
        each), which the DELETE needs after the cursor is exhausted.
        Why iterating the cursor while issuing the by-id reads is safe: NOTHING is written before the
        candidate cursor is exhausted — the meta counter, the digests, `digest_days` and the DELETE all come
        after the loop, so no deleted row is ever under an open cursor (the witness's watcher fails on any
        write statement issued before exhaustion). A `sqlite3.Error` raised mid-iteration propagates to the
        caller's ROLLBACK with nothing yet written: `git grep -n "_fold_retention_locked"` shows a single
        PRODUCTION caller (`ingest_once`); tests call it directly under BEGIN IMMEDIATE, and every other hit
        is prose.
        That transaction is REQUIRED, not assumed: called outside one, this raises
        `sqlite3.ProgrammingError` before reading anything. The connection is `isolation_level=None`, so
        without it every statement would commit on its own, and a failure between the digest upsert and the
        last DELETE chunk would leave rows counted in a digest yet still present — folded again, i.e.
        counted twice, on the next tick.
        A candidate whose by-id read finds NOTHING raises `sqlite3.OperationalError` instead of being
        skipped: under the caller's IMMEDIATE lock only another writer — which the sole-writer design
        excludes — could have removed it, and a silent skip would hide the one symptom of that broken
        invariant. The caller rolls the tick back and reports the error.
        Family closed by T-00000769: `_relabel_unset_locked` and `export_spool` streamed, `canal_a_bodies`
        kept eager by measure (its docstring says why)."""
        assert self._conn is not None
        if not self._conn.in_transaction:
            raise sqlite3.ProgrammingError(
                "_fold_retention_locked requires the caller's BEGIN IMMEDIATE")
        cutoff = (now.date() - timedelta(days=RETENTION_DAYS)).isoformat()
        counts: dict[tuple[str, str, str], int] = {}
        days: set[tuple[str, str]] = set()
        ids = array("q")
        held = 0
        foreign_expired = 0

        def bump(month: str, dimension: str, key: str) -> None:
            slot = (month, dimension, key)
            counts[slot] = counts.get(slot, 0) + 1

        candidates = self._conn.execute(
            "SELECT id, day, kind, agent, task, src_file, channel "
            "FROM events WHERE day < ?",
            (cutoff,),
        )
        for rowid, day, kind, agent, task, src_file, channel in candidates:
            if str(src_file) in live_sources:
                held += 1
                continue
            body: str | None = None
            if classifier_reads_body(str(channel), self.project):
                # Only a row the classifier will actually parse pays the by-id
                # read — the predicate IS its early return (see the docstring).
                found = self._conn.execute(
                    "SELECT body FROM events WHERE id = ?", (rowid,)).fetchone()
                if found is None:
                    # NOISY, never skipped: nothing is written yet, so the
                    # caller's ROLLBACK leaves the store exactly as it was.
                    raise sqlite3.OperationalError(
                        f"events row {rowid} vanished under BEGIN IMMEDIATE: "
                        "another writer holds this store")
                body = found[0]
            ids.append(int(rowid))
            if declares_foreign_project(str(channel), body, self.project):
                # Deleted with everything else below — but its count goes to
                # the neighbour's tally, never into a local digest dimension.
                foreign_expired += 1
                continue
            month = str(day)[:7]
            days.add((month, str(day)))
            bump(month, "total", "")
            if kind:
                bump(month, "kind", str(kind))
            if agent:
                bump(month, "agent", str(agent))
            if task:
                bump(month, "task", str(task))
        # The candidate cursor is exhausted: writes may start.
        if not ids:
            return {"rows_folded": 0, "days_folded": [], "cutoff": cutoff,
                    "rows_retained_pending_spool": held,
                    "foreign_held_expired": 0}
        if foreign_expired:
            self._bump_meta_counter_locked("foreign_held_expired", foreign_expired)
        self._conn.executemany(
            "INSERT INTO digests (month, dimension, key, count) VALUES (?,?,?,?) "
            "ON CONFLICT (month, dimension, key) DO UPDATE SET count = count + excluded.count",
            [(month, dimension, key, n) for (month, dimension, key), n in counts.items()],
        )
        self._conn.executemany(
            "INSERT OR IGNORE INTO digest_days (month, day) VALUES (?,?)", sorted(days)
        )
        # Delete by id, in chunks: an `IN (...)` list is bounded by SQLite's
        # host-parameter limit, and the fold has no reason to be one statement.
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500].tolist()
            self._conn.execute(
                f"DELETE FROM events WHERE id IN ({','.join('?' * len(chunk))})", chunk
            )
        return {"rows_folded": len(ids),
                "days_folded": sorted({day for _month, day in days}),
                "cutoff": cutoff,
                "rows_retained_pending_spool": held,
                "foreign_held_expired": foreign_expired}

    def _bump_meta_counter_locked(self, key: str, delta: int) -> int:
        """Add `delta` to a CUMULATIVE integer counter in `meta`, inside the caller's
        `BEGIN IMMEDIATE` (read-modify-write is safe: the daemon is the SOLE WRITER). A
        malformed or absent value restarts from 0 rather than raising: losing a tally must
        never abort the transaction that was inserting or deleting rows."""
        assert self._conn is not None
        try:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            current = int(row[0]) if row and row[0] is not None else 0
        except (sqlite3.Error, TypeError, ValueError):
            current = 0
        total = current + int(delta)
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?,?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, str(total)),
        )
        return total

    def meta_counter(self, key: str) -> int:
        """A cumulative `meta` counter as an int, 0 when absent/unreadable —
        the reader-side half of `_bump_meta_counter_locked`."""
        raw = self.meta(key)
        try:
            return int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return 0

    def _write_meta_locked(self, now: datetime, report: dict[str, Any],
                           fold: dict[str, Any]) -> None:
        """Last-tick summary, DISPLAY ONLY (Couverture's lag), written EVERY tick: never an
        ingestion anchor (offsets live in memory, identity is the UNIQUE index), and never a
        cache key — it would reload every view every 5 s (T-00000615)."""
        assert self._conn is not None
        payload = {
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files_scanned": report["files_scanned"],
            "files_read": report["files_read"],
            "rows_offered": report["rows_offered"],
            "boot_backlog_files": self._boot_backlog,
            "batch_truncated": report["batch_truncated"],
            "retention_rows_folded": fold.get("rows_folded", 0),
        }
        self._conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?,?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [
                ("last_ingest_at", payload["at"]),
                ("last_tick", json.dumps(payload, ensure_ascii=False)),
                ("schema_version", str(SCHEMA_VERSION)),
            ],
        )

    # -- reads -------------------------------------------------------------

    def max_rowid(self, channel: str = "a") -> int:
        if self.status != "ok" or self._conn is None:
            return 0
        try:
            row = self._conn.execute(
                "SELECT MAX(id) FROM events WHERE channel = ?", (channel,)
            ).fetchone()
        except sqlite3.Error:
            return 0
        return int(row[0]) if row and row[0] is not None else 0

    def query_events(self, after_rowid: int = 0, *, task: str | None = None,
                     kind: str | None = None, agent: str | None = None,
                     since: str | None = None, limit: int = 200,
                     channel: str = "a") -> dict[str, Any]:
        """`WHERE id > ?` — the whole point of the store (spec §A.2: "SSE and
        drill-down move to `WHERE rowid > cursor` — end of the glob over
        hundreds of files", the cost of L-00000055 finally absorbed).

        `next_rowid` keeps the file reader's semantics exactly: a row that was
        EXAMINED and filtered out is still "seen" and must not be rescanned
        forever, so when the page is not truncated the cursor jumps to the
        table's current maximum rather than to the last MATCHED row."""
        empty = {"records": [], "next_rowid": after_rowid, "has_more": False,
                 "status": self.status, "reason": self.reason}
        if self.status != "ok" or self._conn is None:
            return empty
        # The ceiling is read BEFORE the page and pinned INTO the query. Without
        # it, an ingest tick committing between the SELECT and the "where did we
        # get to" read would push the cursor past rows this page never returned —
        # a silent hole in the drill-down, in the one place the whole store
        # exists to make holes impossible.
        ceiling = self.max_rowid(channel)
        clauses = ["channel = ?", "id > ?", "id <= ?"]
        params: list[Any] = [channel, after_rowid, ceiling]
        if task:
            clauses.append("task = ?")
            params.append(task)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        params.append(limit + 1)
        try:
            rows = self._conn.execute(
                f"SELECT id, body FROM events WHERE {' AND '.join(clauses)} "
                f"ORDER BY id LIMIT ?",
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            return {**empty, "status": "unavailable",
                    "reason": f"query failed: {type(exc).__name__}: {str(exc)[:200]}"}
        has_more = len(rows) > limit
        rows = rows[:limit]
        records: list[dict[str, Any]] = []
        malformed = 0
        for _rowid, body in rows:
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                malformed += 1
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                malformed += 1
        if has_more:
            next_rowid = int(rows[-1][0])
        else:
            # Everything up to the pinned ceiling has now been EXAMINED, matched
            # or not — the same "a filtered-out record has still been seen"
            # semantics the byte-offset reader has always had.
            next_rowid = max(after_rowid, ceiling)
        return {"records": records, "next_rowid": next_rowid, "has_more": has_more,
                "status": "ok", "reason": None, "malformed_lines_skipped": malformed}

    def canal_a_bodies(self, limit: int | None = None) -> dict[str, Any]:
        """Every canal-A record body, oldest first — the source of the D4 views
        (`dashboard._read_canal_a_trail`). The exact sibling of
        `canal_b_bodies` below, and its ABSENCE is what T-00000065 was:
        `/api/events` moved to the store while the four views that aggregate the
        same channel kept globbing a spool the ingester now DELETES, so a trail
        of thousands of rows sitting safely here rendered as "ABSENT TRAIL".

        Returns raw BODIES, not parsed dicts, for the same reason
        `canal_b_bodies` does: the reader owns the one parse, so its
        `malformed` counter keeps counting something real. A row whose body is
        not valid JSON is stored verbatim by the ingester (a projection
        relocates, it does not summarise) and must stay countable downstream.

        Same known-shape degraded payload as every other reader here: never
        raises, never returns a bare list.

        NOT STREAMED — MEASURED, AND LEFT EAGER ON PURPOSE (T-00000769). The
        one site of T-00000613's family kept as a list, by decision rather than
        oversight. Its sole caller asks for no `limit`
        (`dashboard._read_canal_a_trail`, memoised), parses every body into a
        record list and KEEPS that list in its cache, so a streaming twin would
        save the bodies' own footprint and nothing of the records rebuilt from
        them: measured on a 5,250-row bench, 7.37 MB eager against 5.05 MB
        streamed, the caller's records included — a constant factor of 1.46,
        not an order. And a canal-A line is capped when written
        (`events._DATA_CAP_BYTES`, 4 KiB), where a canal-B body is not (123,584
        bytes for the largest measured here). Scale, with its correction: this
        repo's store held 3,850 canal-A rows / 1.24 MB of body, over 5 distinct
        days (the plan first counted 22 and read the bench as "30 days"); at
        the corrected rate 30 days is nearer 23,000 rows / 7.4 MB of body —
        arithmetic, not a measurement, and it scales both sides of the ratio
        alike. The bound is the PYTHON HEAP as `tracemalloc` sees it.
        REOPEN THIS when the caller stops keeping every record: the saving
        then becomes an order, and the view should move to an `iter_` twin
        like `iter_canal_b_bodies`."""
        payload: dict[str, Any] = {"status": self.status, "reason": self.reason,
                                   "bodies": [], "rows": 0, "truncated": False}
        if self.status != "ok" or self._conn is None:
            return payload
        sql = "SELECT body FROM events WHERE channel = 'a' ORDER BY id"
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit) + 1)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            return {**payload, "status": "unavailable",
                    "reason": f"canal-A read failed: {type(exc).__name__}: {str(exc)[:200]}"}
        if limit is not None and len(rows) > limit:
            payload["truncated"] = True
            rows = rows[:limit]
        payload["bodies"] = [str(row[0]) for row in rows]
        payload["rows"] = len(payload["bodies"])
        return payload

    def canal_b_bodies(self, limit: int | None = None) -> dict[str, Any]:
        """Every canal-B envelope body, oldest first, AS A LIST.

        NO LONGER THE SOURCE OF THE COST/COVERAGE VIEWS since T-00000613: the dashboard streams through
        `iter_canal_b_bodies()`; this form survives for the tests pinning the two readers together.
        DELIBERATELY NOT FILTERED BY `project`: the rows a foreign session left are QUARANTINED under
        `PROJECT_UNSET`, never made invisible — `foreign_held` is a displayed fact, not a silent subtraction.
        Returns the known-shape degraded payload (`status`/`reason`, empty
        `bodies`) in every non-`ok` status, like every other reader here."""
        payload: dict[str, Any] = {"status": self.status, "reason": self.reason,
                                   "bodies": [], "rows": 0, "truncated": False}
        if self.status != "ok" or self._conn is None:
            return payload
        sql = "SELECT body FROM events WHERE channel = 'b' ORDER BY id"
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit) + 1)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            return {**payload, "status": "unavailable",
                    "reason": f"canal-B read failed: {type(exc).__name__}: {str(exc)[:200]}"}
        if limit is not None and len(rows) > limit:
            payload["truncated"] = True
            rows = rows[:limit]
        payload["bodies"] = [str(row[0]) for row in rows]
        payload["rows"] = len(payload["bodies"])
        return payload

    def iter_canal_b_bodies(self, apres: int | None = None) -> Iterator[str]:
        """`canal_b_bodies()`'s rows ONE AT A TIME (same `ORDER BY id`, never a list) — only `id > apres` when
        given. A COMPLETE read sets `canal_b_lu = (first id, last id, rows, last line_hash)`, None until then:
        the dashboard's incremental watermark (T-01M5T5G6MR), never set by a read that died or was abandoned.
        WHY THIS TWIN EXISTS (T-00000613): the eager form held every row tuple, then every body string — 545 Mo
        on 67 854 rows under a 4,7 Gio peak, and an OS kill took a gate with it; streaming measured 414 Mio.
        THAT 414 Mio IS NOT A CEILING: it bounds the BODY TEXT, never the `records` the caller keeps, which grow
        with the 30 retention days. DELIBERATELY NO `limit`: a `LIMIT` here would freeze every cumulative total
        at a past date; the dashboard bounds its RE-READ (`apres`). `sqlite3.Error` PROPAGATES, unlike the
        sibling: a read dead halfway has yielded rows, and swallowing it would hand back a SHORT channel."""
        self.canal_b_lu = None
        if self.status != "ok" or self._conn is None:
            return
        if apres is None:
            rows = self._conn.execute("SELECT id, body, line_hash FROM events WHERE channel = 'b' ORDER BY id")
        else:
            rows = self._conn.execute(
                "SELECT id, body, line_hash FROM events WHERE channel = 'b' AND id > ? ORDER BY id", (int(apres),))
        premier, dernier, lignes, empreinte = None, None, 0, None
        for rowid, body, empreinte in rows:
            premier = rowid if premier is None else premier
            dernier, lignes = rowid, lignes + 1
            yield str(body)
        self.canal_b_lu = (premier, dernier, lignes, empreinte)

    def canal_b_bornes(self, jusqu_a: int) -> tuple[Any, int, Any]:
        """`(first canal-B id, rows with id <= jusqu_a, line_hash of row jusqu_a)`, a watermark's twin unless rows
        moved since — the hash names the row: ids are reused (no AUTOINCREMENT) once the tail folds. Raises."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT MIN(id), COUNT(*), (SELECT line_hash FROM events WHERE id = ?1) FROM events "
            "WHERE channel = 'b' AND id <= ?1", (int(jusqu_a),)).fetchone()
        return (row[0], int(row[1] or 0), row[2])

    def canal_b_reecriture(self) -> int:
        """`rewrite_generation`, 0 when absent — and RAISES on a read error, unlike `meta_counter`, whose 0 would
        pass for "nothing rewritten" and let the dashboard append to a stale cumul (T-01M5T5G6MR)."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT CAST(value AS INTEGER) FROM meta WHERE key = 'rewrite_generation'").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def session_feed(self, since: str | datetime | None = None,
                     host: str | None = None, project: str | None = None,
                     caps: dict[str, Any] | None = None,
                     now: datetime | None = None) -> dict[str, Any]:
        """CANAL A ONLY, grouped by (host, sid) over a bounded time window — the
        source of the dashboard's "what is happening in the consoles" section
        (T-00000086).

        WHY THIS IS NOT `canal_a_bodies` + a `for` LOOP. That reader returns
        EVERY canal-A body and lets the caller group them; at 30 days of
        retention that is the whole table in the daemon's RSS to answer a
        question about the last 24 hours. Here the grouping is done by SQLite,
        over an `ts` range the `events_ts` index already covers, and NOTHING
        unbounded is ever materialised: the group-by is `LIMIT`ed, the per-
        session event pages are `LIMIT`ed, and the facet lists are `LIMIT`ed.
        No new index is created — this read must not change the write path's
        cost, and the range scan plus a grouping sort over a day of rows is not
        the shape that needs one.

        THE WINDOW HAS TWO FLOORS AND BOTH ARE DECLARED. `since` (default: now
        minus `SESSION_FEED_WINDOW_HOURS`) is what the caller asked for; the
        retention floor (`RETENTION_DAYS`) is what the store can actually
        answer. A `since` below the floor is CLAMPED and said so
        (`window.clamped_to_retention`), because silently returning 24 h of rows
        for a 90-day question is the "absence read as a measurement" shape.

        EVERY TRUNCATION IS A FIELD, never a silent slice:
          * `truncated_sessions` — more sessions matched than `caps.sessions`;
            the ones kept are the most recently active (`last_ts` DESC).
          * `sessions[].truncated` — that session had more events in the window
            than `caps.events_per_session`; the ones kept are the LAST ones, and
            they are returned CHRONOLOGICALLY (the SQL takes the tail with
            `ORDER BY ts DESC`, then the tail is reversed — a reader scanning a
            console reads forwards).
          * `filters_available.truncated` — more distinct hosts/projects than
            the facet cap.
        `sessions[].counts_by_kind`, `agents` and `total_events` are computed
        over the WHOLE window for that session, NOT over the truncated page:
        counts derived from a truncated page would be a plausible, wrong number.

        A ROW WITH NO `sid` IS NOT DROPPED. It cannot join a session — the hooks
        that emit it did not carry one — so it is counted, per host, into
        `sessionless`. Dropping it would make a whole class of events vanish
        from a view whose entire subject is "what happened"; grouping it under a
        fabricated session id would be worse.

        Never raises: a non-`ok` store and a failing statement both return the
        SAME known shape (empty `sessions`, `status`/`reason` set), like every
        other reader on this class."""
        now_dt = now or datetime.now(timezone.utc)
        limits = _session_feed_caps(caps)
        window = _session_feed_window(since, now_dt)
        payload: dict[str, Any] = {
            "status": self.status,
            "reason": self.reason,
            "window": window,
            "sessions": [],
            "sessionless": {"count": 0, "by_host": {}},
            "total_sessions": 0,
            "truncated_sessions": False,
            "caps": dict(limits),
            "filters": {"host": host or None, "project": project or None},
            "filters_available": {"hosts": [], "projects": [], "truncated": False},
            "malformed_skipped": 0,
        }
        if self.status != "ok" or self._conn is None:
            return payload

        # The window + optional filters, spelled ONCE: four statements below
        # share them, and a fifth spelling is how they would stop agreeing about
        # what "this window" means.
        where = ["channel = 'a'", "ts >= ?", "ts <= ?"]
        params: list[Any] = [window["since"], window["until"]]
        if host:
            where.append("host = ?")
            params.append(host)
        if project:
            where.append("project = ?")
            params.append(project)
        scope = " AND ".join(where)

        try:
            return self._session_feed_locked(payload, scope, params, limits)
        except sqlite3.Error as exc:
            return {**payload, "status": "unavailable",
                    "reason": f"session feed failed: {type(exc).__name__}: {str(exc)[:200]}"}

    def _session_feed_locked(self, payload: dict[str, Any], scope: str,
                             params: list[Any],
                             limits: dict[str, int]) -> dict[str, Any]:
        """The four bounded statements behind `session_feed`. Split out so the
        `sqlite3.Error` handler above covers all of them with one known-shape
        return instead of four try blocks that could each forget one."""
        assert self._conn is not None  # guarded by the caller
        conn = self._conn

        # 1. The groups. `LIMIT cap + 1` is the truncation probe: one extra row
        #    is the cheapest possible "there were more".
        groups = conn.execute(
            f"SELECT host, sid, MIN(ts), MAX(ts), COUNT(*) FROM events "
            f"WHERE {scope} AND sid IS NOT NULL AND sid != '' "
            f"GROUP BY host, sid ORDER BY MAX(ts) DESC, sid DESC LIMIT ?",
            [*params, limits["sessions"] + 1],
        ).fetchall()
        truncated_sessions = len(groups) > limits["sessions"]
        groups = groups[:limits["sessions"]]

        # 2. The rows that carry no session, counted per host rather than
        #    dropped. `GROUP BY host` is bounded by the number of hosts, which
        #    is the closed set of agent CLIs plus whatever a malformed line
        #    claims — small either way, and capped by the same facet ceiling.
        sessionless_rows = conn.execute(
            f"SELECT host, COUNT(*) FROM events "
            f"WHERE {scope} AND (sid IS NULL OR sid = '') "
            f"GROUP BY host ORDER BY COUNT(*) DESC LIMIT ?",
            [*params, _SESSION_FEED_MAX_FACETS],
        ).fetchall()
        by_host: dict[str, int] = {}
        for raw_host, count in sessionless_rows:
            key = str(raw_host) if raw_host else SESSION_HOST_ABSENT
            by_host[key] = by_host.get(key, 0) + int(count)
        payload["sessionless"] = {"count": sum(by_host.values()), "by_host": by_host}

        # 3. The filter choices, read WITHOUT the host/project predicates that
        #    the caller may already have applied — a `<select>` built from a
        #    filtered payload can only ever offer the value already selected,
        #    which is a one-way door for the reader.
        payload["filters_available"] = self._session_feed_facets(payload["window"])

        # 4. Per kept session: the aggregate over the whole window, then the
        #    tail page. Both bounded, both scoped to ONE (host, sid) pair, so
        #    the memory held at any instant is one session's page.
        sessions: list[dict[str, Any]] = []
        malformed = 0
        for raw_host, sid, first_ts, last_ts, total in groups:
            session_scope = f"{scope} AND host IS ? AND sid = ?"
            session_params = [*params, raw_host, sid]
            agents, counts_by_kind = self._session_breakdown(session_scope, session_params)
            events, page_truncated, skipped = self._session_events(
                session_scope, session_params, limits["events_per_session"])
            malformed += skipped
            sessions.append({
                "sid": str(sid),
                "host": str(raw_host) if raw_host else None,
                # The project a session's rows were attributed to. Read from the
                # rows themselves rather than from the request: a filter says
                # what was ASKED, the column says what was FOUND.
                "project": self._session_project(session_scope, session_params),
                "first_ts": str(first_ts) if first_ts else None,
                "last_ts": str(last_ts) if last_ts else None,
                "agents": agents,
                "counts_by_kind": counts_by_kind,
                "events": events,
                "total_events": int(total),
                "truncated": page_truncated,
            })
        payload["sessions"] = sessions
        payload["total_sessions"] = len(sessions)
        payload["truncated_sessions"] = truncated_sessions
        payload["malformed_skipped"] = malformed
        return payload

    def _session_facet(self, column: str, window: dict[str, Any]) -> tuple[list[str], bool]:
        rows = self._conn.execute(  # type: ignore[union-attr]
            f"SELECT DISTINCT {column} FROM events "
            f"WHERE channel = 'a' AND ts >= ? AND ts <= ? AND {column} IS NOT NULL "
            f"AND {column} != '' ORDER BY {column} LIMIT ?",
            [window["since"], window["until"], _SESSION_FEED_MAX_FACETS + 1],
        ).fetchall()
        truncated = len(rows) > _SESSION_FEED_MAX_FACETS
        return [str(row[0]) for row in rows[:_SESSION_FEED_MAX_FACETS]], truncated

    def _session_feed_facets(self, window: dict[str, Any]) -> dict[str, Any]:
        hosts, hosts_cut = self._session_facet("host", window)
        projects, projects_cut = self._session_facet("project", window)
        return {"hosts": hosts, "projects": projects,
                "truncated": hosts_cut or projects_cut}

    def _session_project(self, scope: str, params: list[Any]) -> str | None:
        """The project id this session's rows carry, or None when they carry
        more than one. `LIMIT 2` is the whole test: two distinct values means
        the session spans projects, and naming one of them would be a coin
        toss presented as a fact."""
        rows = self._conn.execute(  # type: ignore[union-attr]
            f"SELECT DISTINCT project FROM events WHERE {scope} LIMIT 2", params,
        ).fetchall()
        if len(rows) != 1:
            return None
        return str(rows[0][0]) if rows[0][0] else None

    def _session_breakdown(self, scope: str,
                           params: list[Any]) -> tuple[list[str], dict[str, int]]:
        """`agents` and `counts_by_kind` for ONE session, over the whole window.
        Bounded by (kinds × agents) for a single session, which the closed
        `events.KNOWN_KINDS` vocabulary keeps small."""
        rows = self._conn.execute(  # type: ignore[union-attr]
            f"SELECT kind, agent, COUNT(*) FROM events WHERE {scope} "
            f"GROUP BY kind, agent LIMIT ?",
            [*params, _SESSION_FEED_CAP_CEILING],
        ).fetchall()
        agents: list[str] = []
        counts: dict[str, int] = {}
        for kind, agent, count in rows:
            key = str(kind) if kind else "(sans kind)"
            counts[key] = counts.get(key, 0) + int(count)
            if agent and str(agent) not in agents:
                agents.append(str(agent))
        return sorted(agents), counts

    def _session_events(self, scope: str, params: list[Any],
                        limit: int) -> tuple[list[dict[str, Any]], bool, int]:
        """The LAST `limit` events of one session, returned CHRONOLOGICALLY.

        `ORDER BY ts DESC, id DESC` then reverse — not `ORDER BY ts` with an
        offset: the tail is what a console reader wants and the offset form
        would have to count the whole session first. `id` breaks the tie
        because canal-A stamps to the second and a busy hook emits several
        events inside one."""
        rows = self._conn.execute(  # type: ignore[union-attr]
            f"SELECT body FROM events WHERE {scope} ORDER BY ts DESC, id DESC LIMIT ?",
            [*params, limit + 1],
        ).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        records: list[dict[str, Any]] = []
        malformed = 0
        for (body,) in reversed(rows):
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                malformed += 1
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                malformed += 1
        return records, truncated, malformed

    def attribution_counters(self) -> dict[str, Any]:
        """The two EVENT counters that are not row counts, with their own time
        bases — kept apart from the row buckets on purpose (iteration 7, C2: a
        UI that invites the reader to add them is a UI that lies).

          * `dropped_foreign`      — records REFUSED at the receiver, so they
            never became rows at all. In-memory, "since this process started".
          * `foreign_held_expired` — quarantined rows the 30-day fold deleted.
            Cumulative in `meta`, survives restarts.
        """
        try:
            dropped = int(_otel_receiver_mod.get_diagnostics().get("dropped_foreign", 0))
        except Exception:  # noqa: BLE001 - a counter may never take a view down
            dropped = 0
        return {
            "dropped_foreign": dropped,
            "dropped_foreign_basis": "since this daemon process started (in-memory)",
            "foreign_held_expired": self.meta_counter("foreign_held_expired"),
            "foreign_held_expired_basis": "cumulative since the store was created (meta)",
        }

    def digest_aggregates(self) -> dict[str, Any]:
        """The digests table in the SAME SHAPE the JSON digest files produced,
        so `/api/events`'s `aggregates` contract does not move under the UI."""
        if self.status != "ok" or self._conn is None:
            return {"months": [], "label": _DIGEST_LABEL, "source": self.status,
                    "reason": self.reason}
        try:
            rows = self._conn.execute(
                "SELECT month, dimension, key, count FROM digests ORDER BY month"
            ).fetchall()
        except sqlite3.Error as exc:
            return {"months": [], "label": _DIGEST_LABEL, "source": "unavailable",
                    "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
        by_month: dict[str, dict[str, Any]] = {}
        for month, dimension, key, count in rows:
            slot = by_month.setdefault(str(month), {
                "month": str(month), "total_events": 0,
                "by_kind": {}, "by_agent": {}, "by_task": {},
            })
            if dimension == "total":
                slot["total_events"] = int(count)
            elif dimension == "kind":
                slot["by_kind"][str(key)] = int(count)
            elif dimension == "agent":
                slot["by_agent"][str(key)] = int(count)
            elif dimension == "task":
                slot["by_task"][str(key)] = int(count)
        return {"months": [by_month[m] for m in sorted(by_month)],
                "label": _DIGEST_LABEL, "source": "sqlite", "reason": None}

    def meta(self, key: str) -> str | None:
        if self.status != "ok" or self._conn is None:
            return None
        try:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        except sqlite3.Error:
            return None
        return str(row[0]) if row and row[0] is not None else None

    # -- rollback ----------------------------------------------------------

    def export_spool(self, now: datetime | None = None, *,
                     before_retire: Callable[[], str | None] | None = None
                     ) -> dict[str, Any]:
        """Rollback path: re-emit the store as spool JSONL + digest JSON, then
        RETIRE the database by renaming it `events.db.exported-<ts>`.

        Why the rename is not optional (iteration 2, C5): leaving `events.db` in
        place means a later re-upgrade finds a populated database AND the export
        files, and ingests the second on top of the first.

        Why an export never overlaps a surviving original (iteration 3, C1): a row whose `src_file` is STILL
        ON DISK is skipped — that file will be re-read from its own bytes, under its own identity. Exports
        therefore carry only what no longer exists anywhere else, so no line can be counted twice under two
        names.

        Exports land in `exports/<ts>/` under each channel's own spool directory: nested, so
        `events._events_dir().glob("*.jsonl")` — which is what `merge_day_files` and `compact` glob — can
        never see them (iteration 3, C2). ACCEPTED COST, stated plainly at the gate: a rollback AFTER
        ingestion does not restore the deleted spool files in place, so a pre-V1-b kit will not display this
        history; the data is preserved in `exports/`, not re-homed (iteration 7, C5).

        STREAMED TO DISK, NEVER fetchall() (T-00000769, the family of T-00000613). The volume here is the
        WHOLE store, and the eager form held every body twice — the fetched rows, then one `"".join` per
        file: measured at 41.12 MB for 1,000 small `a` rows + 1,000 `b` rows of 20 KB, against 0.19 MB
        streamed row by row into the file. A flush per FILE would not have been enough: the largest spool
        file measured on this repo is 123.2 MB by itself. So the cursor is `ORDER BY channel, src_file,
        line_index, id`, `groupby` cuts it into one group per file — the grouping is only correct because
        that ORDER BY makes each file's rows contiguous — and each group goes straight into
        `_publish_lines`. The bound is the PYTHON HEAP as `tracemalloc` sees it; RSS and SQLite's page cache
        are not measured.

        PREPARED, THEN PROMOTED AFTER THE COMMIT POINT (T-00000769, decisions S-00002496 and S-00002503).
        Every file — each root's spool files and root `a`'s digests — is written under
        `exports.partial/<stamp>/`, which no ingester glob reaches. The COMMIT POINT is the rename that
        retires the database: before it, the database alone carries the history; after it, each root's
        staging is promoted to `exports/<stamp>/` (target refused if it exists, even empty — a POSIX rename
        replaces an empty directory in silence; directories fsynced). So at no instant are the rows both in
        a live database AND in an ingestable export — the double count exec-critic measured (9 rows for 6
        events, S-00002495) when an interrupted export left files under `exports/`. And a death between the
        retire and a promotion is recovered: `_promote_retired_staging`, run by the next
        `open_store(create=True)` under `.maintenance.lock`, promotes a staging iff `<db>.exported-<stamp>`
        exists.

        ON ERROR BEFORE THE COMMIT POINT — read (`sqlite3.Error`) or write (`OSError`, e.g. ENOSPC: this
        used to escape as a traceback) — nothing is retired, the file in flight leaves no trace
        (`_publish_lines` unlinks its temp file), THIS RUN'S PREPARATION IS REMOVED (S-00002537: one full
        copy of the store per failed attempt was kept forever), and `reason` says so and that re-running is
        safe. A process DEATH cleans nothing: its preparation stays invisible under `exports.partial/`. A
        DIGEST READ counts: the digests are the only copy of the history the fold already deleted, so a
        `digest_aggregates()` payload that did not come from SQLite, or a `_digest_days()` that raised,
        stops the export before the retire exactly like a spool-row read error.

        ORPHANS (S-00002537). Before writing, under `.maintenance.lock`, every `exports.partial/` entry no
        retired database proves is removed — a symlink unlinked, never followed — and named in
        `unproven_stagings_removed`; a proven one is the recovery's, left alone. Because that cleanup can
        reach a preparation still being WRITTEN by another export, the commit phase first checks, under the
        lock, that every file this export wrote is still there — else nothing is retired.

        THE COMMIT PHASE RUNS UNDER `.maintenance.lock` — from the last daemon check to the last promotion
        (F3 of critic-opus, round 2: two overlapping exports gave 12 rows for 6). Lock held elsewhere ⇒
        nothing retired, preparation removed, re-run. And if the database is ALREADY gone at the retire —
        another export retired it first — this export is `void`: its preparation removed, and nothing to
        rename by hand. NEVER removed, on any path, is a preparation `<db>.exported-<stamp>` proves: it is
        LEFT for the recovery, and said. Since the final pass the stamp carries the pid (`_export_stamp`),
        so only two exports of the SAME process in the same second can still share it. A root whose
        preparation vanished after the pre-retire check is named: its rows live only in the retired
        database. The spool directories of every preparation (staging, `digest/`, `exports.partial/`, spool
        root) are fsynced BEFORE the last daemon probe, so the probe is the last step before the retire;
        `roots` names only what this run promoted, `staged` exactly what it leaves in preparation.

        THE DAEMON MUST BE STOPPED. A live one ingests `exports/*/*.jsonl` and deletes the files, keeps the
        database open (its WAL stays behind under the old name at the retire) and re-creates an empty store:
        history lost (T1 of critic-opus, S-00002502). `main --export-spool` refuses — on `alive` and on
        `unresponsive` (pid alive, ping silent) — before exporting, and passes `before_retire` so the state
        is read AGAIN just before the retire — a session starting mid-export relaunches the daemon. A
        non-None answer is a refusal: status `refused`, nothing retired, the preparation removed.

        TIES. `ORDER BY …, id`: the identity is `(project, src_file, line_index, line_hash)`, so two rows of
        one file can share a `line_index`; without `id` their order was whatever plan SQLite chose.

        UNSAFE KEYS. A `src_file` whose file part is empty, `.` or `..`, or still carries `\\`, NUL or `:`
        after the `/`→`__` replacement is never turned into a path (security advisory, S-00002491): it is
        skipped, counted in `rows_skipped_unsafe_name` and named in `unsafe_src_files`. The ingester never
        stores such a key; only a damaged or hand-edited database can. After the retire those rows live ONLY
        in the retired database, so `reason` says so and the CLI exits 1 (F7, round 2)."""
        now = now or datetime.now(timezone.utc)
        stamp = _export_stamp(now)
        result: dict[str, Any] = {
            "status": self.status, "files_written": 0, "rows_exported": 0,
            "rows_skipped_still_on_disk": 0, "rows_skipped_unsafe_name": 0,
            "unsafe_src_files": [], "digests_written": 0,
            "db_retired_to": None, "reason": self.reason, "roots": [], "staged": [],
            "unproven_stagings_removed": [],
        }
        if self.status != "ok" or self._conn is None:
            return result
        bases = {"a": _events_dir(), "b": _otel_dir()}
        staged = {channel: base / _EXPORTS_PARTIAL / stamp
                  for channel, base in bases.items() if base is not None}
        finals = {channel: base / "exports" / stamp
                  for channel, base in bases.items() if base is not None}
        staged_names = ", ".join(str(path) for path in dict.fromkeys(staged.values()))
        retired = _retired_proof(self.path, stamp)
        if retired.exists() or retired.is_symlink():
            # A database was already retired under THIS stamp: renaming onto it
            # would destroy it, and its staging is the recovery's to promote.
            result["reason"] = (
                f"{retired} already exists — a database was already retired under "
                f"this stamp; nothing written, nothing retired. Re-run in a second."
            )
            return result

        def finish(outcome: dict[str, Any]) -> dict[str, Any]:
            # `staged` is EXACTLY what this run leaves in preparation (F5 of
            # critic-fable, round 2): normally nothing, the prepared export only
            # when a failed retire needs it for the hand rename it advises.
            outcome["staged"] = sorted(str(path) for path in dict.fromkeys(staged.values())
                                       if path.exists() or path.is_symlink())
            return outcome

        def drop_preparation() -> str:
            if retired.exists() or retired.is_symlink():
                # Round 3: another export in the SAME second retired the database
                # under this very stamp — this preparation directory is now ITS
                # only copy of the rows (the recovery promotes it). Never removed.
                return f"preparation LEFT: {retired} proves it"
            errors = [error for error in (_remove_prepared(path)
                                          for path in dict.fromkeys(staged.values())) if error]
            for path in staged.values():
                _rmdir_if_empty(path.parent)
            if errors:
                return (f"preparation NOT removed ({'; '.join(errors)}) — invisible to "
                        f"the ingester, and the next export removes it")
            return f"preparation removed ({staged_names})"

        # UNDER THE LOCK, before anything is written: no retire and no promotion
        # can run while unproven preparations are being removed.
        locked, cleanup = _under_maintenance_lock(lambda: _remove_unproven_stagings(
            self.path, [base for base in bases.values() if base is not None]))
        if not locked:
            result["reason"] = (
                f".maintenance.lock could not be taken ({cleanup}) — another export, the "
                f"daemon's recovery or a maintenance run holds it: nothing written, "
                f"nothing retired; re-run once it is released"
            )
            return finish(result)
        result["unproven_stagings_removed"] = cleanup["removed"]
        if cleanup["errors"]:
            result["reason"] = (
                f"unproven preparation(s) could not be removed: "
                f"{'; '.join(cleanup['errors'])} — nothing written, nothing retired"
            )
            return finish(result)

        def file_of(row: tuple[Any, ...]) -> tuple[str, str]:
            return str(row[0]), str(row[1])

        written: list[Path] = []
        stage = "spool rows"   # named in `reason` when the export stops
        try:
            rows = self._conn.execute(
                "SELECT channel, src_file, line_index, body FROM events "
                "ORDER BY channel, src_file, line_index, id"
            )
            for (channel, key), group in groupby(rows, key=file_of):
                base = bases.get(channel)
                if base is None:
                    continue  # resolver failed: neither exported nor counted
                relative = key.split("/", 1)[1] if "/" in key else key
                name = relative.replace("/", "__")
                if _unsafe_export_name(name):
                    result["rows_skipped_unsafe_name"] += sum(1 for _row in group)
                    result["unsafe_src_files"].append(key)
                    continue
                if (base / relative).exists():
                    result["rows_skipped_still_on_disk"] += sum(1 for _row in group)
                    continue
                target = staged[channel] / name
                exported = [0]

                def lines(group: Iterable[tuple[Any, ...]] = group,
                          exported: list[int] = exported) -> Iterator[str]:
                    for row in group:
                        exported[0] += 1
                        yield str(row[3]) + "\n"

                _publish_lines(target, lines())
                written.append(target)
                result["files_written"] += 1
                result["rows_exported"] += exported[0]

            stage = "digests"
            digests = self.digest_aggregates()
            if digests.get("source") != "sqlite":
                # `digest_aggregates` turns a `sqlite3.Error` into a degraded
                # payload with NO months — exporting that, then retiring, would
                # drop the only copy of the history the fold already deleted.
                raise sqlite3.OperationalError(
                    f"digests unreadable ({digests.get('reason')})")
            if "a" in staged:
                for month in digests.get("months") or []:
                    target = staged["a"] / "digest" / f"{month['month']}.json"
                    payload = {
                        "month": month["month"],
                        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "total_events": month["total_events"],
                        "by_kind": month["by_kind"],
                        "by_agent": month["by_agent"],
                        "by_task": month["by_task"],
                        "days_folded": self._digest_days(month["month"]),
                    }
                    _publish_text(target,
                                  json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
                    written.append(target)
                    result["digests_written"] += 1
        except (sqlite3.Error, OSError) as exc:
            result["reason"] = (
                f"{type(exc).__name__}: {str(exc)[:200]} — export interrupted while "
                f"exporting the {stage}: {result['files_written']} file(s) already "
                f"written; database NOT retired; {drop_preparation()}. Re-running the "
                f"export is safe."
            )
            return finish(result)

        # FROM THE LAST DAEMON CHECK TO THE LAST PROMOTION, UNDER THE LOCK (F3
        # of critic-opus, round 2): a second export, the daemon's recovery or a
        # legacy migration can no longer interleave with the retire.
        locked, committed = _under_maintenance_lock(lambda: self._commit_prepared_export(
            result, stamp, staged, finals, retired, written, before_retire, drop_preparation))
        if not locked:
            result["reason"] = (
                f".maintenance.lock could not be taken ({committed}) — another export, "
                f"the daemon's recovery or a maintenance run holds it: nothing retired, "
                f"the database keeps every row; {drop_preparation()}. Re-run once it is "
                f"released."
            )
            return finish(result)
        return finish(committed)

    def _commit_prepared_export(self, result: dict[str, Any], stamp: str,
                                staged: dict[str, Path], finals: dict[str, Path],
                                retired: Path, written: list[Path],
                                before_retire: Callable[[], str | None] | None,
                                drop_preparation: Callable[[], str]) -> dict[str, Any]:
        """`export_spool`'s commit phase — called UNDER `.maintenance.lock`
        only. Checks, re-asks the daemon, fsyncs, retires, promotes."""
        missing = [str(path) for path in written if not path.is_file()]
        if missing:
            # Another run's orphan cleanup reached this preparation while it
            # was being written (that cleanup holds the lock; the writing does
            # not). Retiring now would retire rows the export no longer has.
            result["reason"] = (
                f"{len(missing)} prepared file(s) vanished before the retire (first: "
                f"{missing[0]}) — another export's cleanup reached this preparation: "
                f"database NOT retired; {drop_preparation()}. Re-run."
            )
            return result
        # BEFORE the last daemon probe (round 3): the slowest step of this phase
        # must not sit between the probe and the retire it guards.
        _fsync_preparation(staged.values())
        if before_retire is not None:
            refusal = before_retire()
            if refusal:
                result["status"] = "refused"
                result["reason"] = (
                    f"{refusal} — nothing retired, the database keeps every row; "
                    f"{drop_preparation()}. Re-run once the daemon is stopped."
                )
                return result

        # The connection must be closed BEFORE the rename: an open handle makes
        # os.replace fail on Windows (the same hard requirement every publisher
        # in this kit documents).
        self.close()
        try:
            _replace_with_retry(self.path, retired)
        except OSError as exc:
            if isinstance(exc, FileNotFoundError) and not (
                    self.path.exists() or self.path.is_symlink()):
                # The database is ALREADY gone: another export retired it first
                # (it opened before this one, read the same rows) — or a hand
                # rename did. Its rows are in THAT export. Keeping this copy,
                # or advising a hand rename, is how a second copy got promoted
                # on top of the first (12 rows for 6, S-00002536).
                self.status = "absent"
                self.reason = "export void: the database was already retired"
                result["status"] = "void"
                result["reason"] = (
                    f"{self.path} was already gone when this export reached its "
                    f"retire — another export (or a hand rename) retired it first, "
                    f"and its rows are in THAT export. This one is VOID: nothing "
                    f"retired by it; {drop_preparation()}. Rename nothing by hand."
                )
                return result
            result["reason"] = (
                f"export prepared under {', '.join(map(str, staged.values()))} but the "
                f"database could not be retired ({type(exc).__name__}: "
                f"{str(exc)[:200]}) — rename {self.path} to exactly {retired} by hand: "
                f"the next daemon start then promotes the prepared export into "
                f"exports/{stamp}/. Until then nothing of this export is ingested and "
                f"the database keeps every row."
            )
            return result
        result["db_retired_to"] = str(retired)
        # THE COMMIT POINT is behind us: make the rename durable before any
        # export becomes visible to the ingester.
        _fsync_dir(self.path.parent)
        self.status = "absent"
        self.reason = "exported and retired"
        result["status"] = "exported"
        notes: list[str] = []
        failures: list[str] = []
        promoted: list[str] = []
        vanished: list[str] = []
        for channel, staging in staged.items():
            if not staging.exists():
                if any(staging in path.parents for path in written):
                    # Prepared, checked before the retire, gone now (another
                    # process, a hand `rm`): the database is retired, so these
                    # rows exist nowhere else. Never a silent "nothing here".
                    vanished.append(str(staging))
                continue  # otherwise nothing was prepared for this root
            try:
                _promote_staged(staging, finals[channel])
            except OSError as exc:
                failures.append(f"{staging} ({type(exc).__name__}: {str(exc)[:200]})")
                continue
            promoted.append(str(finals[channel]))
        # `roots` names only what THIS export promoted (F5 of critic-fable).
        result["roots"] = sorted(promoted)
        if vanished:
            notes.append(
                f"{len(vanished)} prepared export(s) vanished after the pre-retire "
                f"check ({'; '.join(vanished)}) — its rows live only in {retired}"
            )
        if failures:
            notes.append(
                f"database retired to {retired}, but {len(failures)} prepared "
                f"export(s) could not be promoted into exports/{stamp}/: "
                f"{'; '.join(failures)} — the next daemon start promotes it (the "
                f"retired database is its proof; it keeps the store absent and "
                f"retries every tick until it can); if the cause persists (an "
                f"existing exports/{stamp}/ is never replaced), move it aside"
            )
        if result["rows_skipped_unsafe_name"]:
            notes.append(
                f"{result['rows_skipped_unsafe_name']} row(s) under "
                f"{len(result['unsafe_src_files'])} unsafe src_file key(s) were NOT "
                f"exported (named in unsafe_src_files) — they now live only in the "
                f"retired database {retired}"
            )
        result["reason"] = " | ".join(notes) or None
        return result

    def _digest_days(self, month: str) -> list[str]:
        """The days folded into `month`. RAISES `sqlite3.Error` (T-00000769):
        its one caller is `export_spool`, where an `[]` swallowed here became
        a digest with an empty `days_folded` — and a retired database behind
        it. The export treats the raise as a read error and retires nothing."""
        if self._conn is None:
            return []
        rows = self._conn.execute(
            "SELECT day FROM digest_days WHERE month = ? ORDER BY day", (month,)
        ).fetchall()
        return [str(row[0]) for row in rows]


# ---------------------------------------------------------------------------
# Helpers the store leans on.
# ---------------------------------------------------------------------------

def _events_dir() -> Path | None:
    try:
        return _events_mod._events_dir()
    except Exception:  # noqa: BLE001 - a broken resolver degrades, never raises
        return None


def _otel_dir() -> Path | None:
    try:
        return _otel_receiver_mod._otel_dir()
    except Exception:  # noqa: BLE001 - same contract
        return None


def _resolve_user() -> str | None:
    """`git config user.name`, via events.py's own cached resolver — one recipe
    for `user` in the kit, not a second one here (spec §A.1: never a tracked
    user file; git already exposes the author)."""
    try:
        return _events_mod._resolve_user()
    except Exception:  # noqa: BLE001
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


_DAY_LEN = len("YYYY-MM-DD")


def _day_of(ts: str | None, path: Path, ingested_at: str) -> str:
    """Retention key. Fallback chain, pinned so it cannot drift (iteration 4,
    C3): the record's own `ts`, then the date prefix of the file name (every
    spool file is `YYYY-MM-DD.*`), then the ingestion date. Never empty — a
    NULL here would make a row invisible to `DELETE WHERE day < cutoff` and it
    would live forever."""
    if isinstance(ts, str) and len(ts) >= _DAY_LEN and _looks_like_day(ts[:_DAY_LEN]):
        return ts[:_DAY_LEN]
    name = path.name
    if len(name) >= _DAY_LEN and _looks_like_day(name[:_DAY_LEN]):
        return name[:_DAY_LEN]
    return ingested_at[:_DAY_LEN]


def _looks_like_day(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _publish_text(target: Path, text: str) -> None:
    """`_publish_lines` with a single element: one publish recipe, not two."""
    _publish_lines(target, (text,))


def _publish_lines(target: Path, lines: Iterable[str]) -> None:
    """mkstemp in the target directory -> write each element -> fsync -> close
    fd -> os.replace(retry). The kit's one publish recipe
    (build_index._Publisher, events._publish_digest, project_init), newline
    pinned to "\\n" (L-003).

    FED ONE ELEMENT AT A TIME (T-00000769): `export_spool` hands it a generator
    over a SQLite cursor, so a spool file of any size reaches the disk without
    being held in memory — the largest one measured on this repo is 123.2 MB
    on its own. What that changes, stated: the SOURCE can now fail mid-file,
    after bytes reached the temp file. Any exception, the source's included,
    unlinks the temp file and is re-raised; the replace never runs, so the
    target is either absent or intact, never half-written
    (`test_publish_lines_a_source_failing_mid_write_leaves_no_part_file_and_no_target`)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="._tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for chunk in lines:
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, 0o644)
        except OSError:
            pass
        _replace_with_retry(tmp, str(target))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Characters that make a file name a PATH once joined (T-00000769, security
# advisory S-00002491): a separator of either platform, NUL (`os.replace` raises
# ValueError on it — not an OSError), and a drive colon (`base / "C:x"` leaves
# `base` on Windows).
_UNSAFE_NAME_CHARS = ("/", "\\", "\x00", ":")


def _unsafe_export_name(name: str) -> bool:
    """True when `name`, the export file name derived from a stored `src_file`,
    would not stay a single entry inside the export directory."""
    return name in ("", ".", "..") or any(char in name for char in _UNSAFE_NAME_CHARS)


def _fsync_dir(path: Path) -> None:
    """Make a rename inside `path` durable. POSIX only in effect: Windows
    cannot open a directory for fsync (NTFS journals its metadata), so the open
    fails there and this returns — best effort, never raises."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _promote_staged(staging: Path, final: Path) -> None:
    """Promote one prepared export directory to its ingestable name, AFTER the
    database was retired (`export_spool`, `_promote_retired_staging`).

    REFUSES an existing target, even EMPTY: on POSIX a directory rename
    replaces an empty target in silence, and a target nobody expected is not
    ours to drop. The rename is one `os.replace` on one filesystem (both
    directories live under the same spool root), retried on PermissionError
    like every publish here, then both parents are fsynced. `exports.partial/`
    is removed when it is left empty — `rmdir` refuses otherwise."""
    if final.exists() or final.is_symlink():
        raise FileExistsError(errno.EEXIST,
                              "an export directory already exists and is never replaced",
                              str(final))
    final.parent.mkdir(parents=True, exist_ok=True)
    _replace_with_retry(staging, final)
    _fsync_dir(final.parent)
    _fsync_dir(final.parent.parent)   # `exports/` itself may have just been created
    _fsync_dir(staging.parent)
    _rmdir_if_empty(staging.parent)


def _rmdir_if_empty(path: Path) -> None:
    """`exports.partial/` is left behind by nobody: removed once empty, and
    `rmdir` refuses a directory that still holds anything."""
    try:
        path.rmdir()
    except OSError:
        pass


def _remove_prepared(path: Path) -> str | None:
    """Remove ONE preparation entry: a symlink or a file is UNLINKED — never
    followed, and `rmtree` refuses a symlink, which made a linked preparation
    unremovable for good (F4 of critic-fable, round 2) — a directory is
    removed whole. `None`, or the failure in words; never raises."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
    except OSError as exc:
        return f"{path}: {type(exc).__name__}: {str(exc)[:200]}"
    return None


def _export_stamp(now: datetime, pid: int | None = None) -> str:
    """`<%Y%m%dT%H%M%SZ>-p<pid>` — the name of one export's preparation, of its
    proof `<db>.exported-<stamp>` and of its final `exports/<stamp>/`.

    UNIQUE PER PROCESS (decision S-00002576, reversing S-00002563's stamp to
    the second): two `--export-spool` processes started in the same second
    shared ONE preparation directory and ONE proof name, and each defence
    built since then (clean-up of a failed attempt, `LEFT` under a proof)
    could hit the other's copy — measured 0/6 rows, and a daemon blocked by a
    partial copy left under the other's proof (S-00002575, F1)."""
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-p{os.getpid() if pid is None else int(pid)}"


def _retired_proof(db_path: Path, stamp: str) -> Path:
    """`<db>.exported-<stamp>` — the ONE proof that the export prepared under
    `exports.partial/<stamp>/` crossed its commit point. Every rule about a
    preparation (promote it, keep it, remove it, name it) reads this name."""
    return db_path.with_name(f"{db_path.name}.exported-{stamp}")


def _proven_stagings(db_path: Path) -> list[Path]:
    """The preparations waiting for promotion: a real directory (not a
    symlink) under a spool root's `exports.partial/`, whose `_retired_proof`
    exists. Never raises: an unreadable spool root contributes nothing."""
    found: list[Path] = []
    for base in dict.fromkeys(base for base in (_events_dir(), _otel_dir()) if base is not None):
        partial = base / _EXPORTS_PARTIAL
        try:
            if partial.is_symlink() or not partial.is_dir():
                continue
            found.extend(sorted(
                entry for entry in partial.iterdir()
                if entry.is_dir() and not entry.is_symlink()
                and _retired_proof(db_path, entry.name).exists()))
        except OSError:
            continue
    return found


def _remove_unproven_stagings(db_path: Path, bases: Iterable[Path]) -> dict[str, list[str]]:
    """Remove every `exports.partial/` entry that no retired database proves
    (T-00000769, S-00002537 — F6 of critic-opus / F3 of critic-fable, round 2:
    one full copy of the store per failed attempt, kept forever). An entry is
    PROVEN when it is a real directory and `<db>.exported-<name>` exists: its
    rows live nowhere else, it is the recovery's to promote, and it is left
    alone. Everything else — an export that never reached its retire, a file,
    a symlink (unlinked, never followed), even `exports.partial` itself when
    it is not a real directory — is removed and named. Run by `export_spool`
    UNDER `.maintenance.lock`, so it can never race a retire or a promotion."""
    report: dict[str, list[str]] = {"removed": [], "errors": []}
    for base in dict.fromkeys(bases):
        partial = base / _EXPORTS_PARTIAL
        if partial.is_symlink() or partial.is_file():
            entries = [partial]
        elif partial.is_dir():
            try:
                entries = sorted(partial.iterdir())
            except OSError as exc:
                report["errors"].append(f"{partial}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
        else:
            continue
        for entry in entries:
            proven = (entry is not partial and entry.is_dir() and not entry.is_symlink()
                      and _retired_proof(db_path, entry.name).exists())
            if proven:
                continue
            error = _remove_prepared(entry)
            if error is None:
                report["removed"].append(str(entry))
            else:
                report["errors"].append(error)
        if partial.is_dir() and not partial.is_symlink():
            _rmdir_if_empty(partial)
    return report


def _fsync_preparation(staged: Iterable[Path]) -> None:
    """Make every directory ENTRY of a preparation durable before the commit
    point (F5 of critic-opus, round 2): `_publish_lines` fsyncs each FILE, but
    the entries naming them — the staging, its `digest/`, `exports.partial/`,
    the spool root — were fsynced by nobody, so a power cut right after the
    retire could leave a retired database and a preparation that never reached
    the disk."""
    for staging in staged:
        if not staging.is_dir() or staging.is_symlink():
            continue
        for directory in sorted(path for path in staging.rglob("*")
                                if path.is_dir() and not path.is_symlink()):
            _fsync_dir(directory)
        _fsync_dir(staging)
        _fsync_dir(staging.parent)
        _fsync_dir(staging.parent.parent)


def _under_maintenance_lock(action: Callable[[], Any]) -> tuple[bool, Any]:
    """Run `action` under `events.maintenance_lock()` — the lock the daemon's
    recovery and the legacy migration take. `(True, its result)`, or
    `(False, "<why>")` when the lock could not be TAKEN (a live holder, or an
    unusable lock file). An exception raised by `action` itself is never
    mistaken for a lock problem: it propagates."""
    locked = False
    try:
        with _events_mod.maintenance_lock():
            locked = True
            return True, action()
    except Exception as exc:  # noqa: BLE001 - classified right below
        if locked:
            raise
        if isinstance(exc, _events_mod.MaintenanceLockBusy):
            return False, f"held by another run: {exc}"
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


# ---------------------------------------------------------------------------
# Opening, versioning, and the one-time legacy migration.
# ---------------------------------------------------------------------------

def _location_refused(target: Path, exc: BaseException) -> EventStore:
    """`absent` + cause, for a store location that `cadre.ledger.store` refuses
    (T-00000770): a link (pending or not) at `events.db` or at a side file, a
    second hard name, a non-regular file, a name that changed between the check
    and the open. `absent` and not `unavailable` ON PURPOSE: `IngestLoop.tick`
    re-opens only an `absent` store, so the daemon starts again by itself once
    the link is removed, and the dashboard readers of `absent` fall back to the
    spool, which IS the truth while nothing is ingested. The cause is in
    `reason` and in `open_report["location_refused"]`."""
    store = EventStore(target, None, "absent", (
        f"{target}: store location refused — {exc}. Nothing was followed, created "
        f"or removed; the daemon retries on every tick"
    ), None)
    store.open_report["location_refused"] = str(exc)
    return store


def _seam_missing(target: Path, exc: BaseException) -> EventStore:
    """`absent` + cause when the `cadre.ledger.store` seam cannot be loaded by
    either branch (A-C1/A-C5 of T-00000770): the store is neither opened nor
    created without the non-following primitive — opening it by a bare
    `sqlite3.connect` would reopen the window. Distinct from a refused location
    (`open_report["seam_missing"]`), and never worded « nothing ingested yet »:
    an existing `events.db` may hold everything."""
    detail = f"{type(exc).__name__}: {str(exc)[:200]}"
    store = EventStore(target, None, "absent", (
        f"{target}: couture cadre.ledger.store absente ({detail}) — the store is "
        f"neither opened nor created without it (a copy of .agents/ without "
        f"its cadre package?). An existing store is left untouched but NOT read, and the "
        f"ingester deletes the spool files it ingests, so the spool left on disk is "
        f"not the whole history; retried on every tick"
    ), None)
    store.open_report["seam_missing"] = detail
    return store


def open_store(path: str | Path | None = None, *, create: bool = False) -> EventStore:
    """Open (and, with `create=True`, create + migrate) the store.

    `create=True` is the DAEMON's call and nobody else's — the daemon is the
    sole writer. A reader passes `create=False` and gets `status="absent"` when
    there is no database, which is a first-class, displayable state, not an
    error. `absent` has other causes too, each named in its reason: a
    maintenance run holding `.maintenance.lock`, or a retired export whose
    promotion is refused, blocking the one-time migration (below); a store
    location REFUSED (T-00000770, `open_report["location_refused"]`); the
    `cadre.ledger.store` seam MISSING (`open_report["seam_missing"]`); a store
    that VANISHED between the existence check and the open (« vanished before
    the open », no `location_refused`: nothing is at the name any more); and a
    file that exists but carries no schema yet.

    T-00000770 — the store is opened WITHOUT FOLLOWING, through
    `cadre.ledger.store` (`_cadre_module`: provenance, then by path). Order is
    load-bearing: the seam first, in its OWN `except` (its path fallback raises
    `FileNotFoundError`, an `OSError` the open's channel would call
    `unavailable`); then `refuser_les_liens` BEFORE `existed` and the legacy
    migration — on a PENDING link `exists()` says False, so the reader returned
    « nothing ingested » and the daemon migrated the spool and let SQLite create
    the link's target. The open itself is `ouvrir_sans_suivre`: a new store is
    born EMPTY by exclusive creation, in 0o600, and every open is `mode=rw`
    (never creating), checked by `PRAGMA database_list` and a second identity.
    An EXISTING store whose location is unchanged but that SQLite cannot open
    (permissions) is an access failure, `unavailable` with SQLite's cause —
    not a refused location (decision of the orchestrator, pilot delegation).
    `IngestLoop.tick` re-opens an `absent` store on every tick but NEVER an
    `unavailable` one (S-00002817): once the access is fixed, restart the
    daemon.

    Before the version is known, two statements run, both version-agnostic and
    neither a write: the primitive's `PRAGMA database_list` (identity check),
    then `PRAGMA user_version`. A file from a NEWER kit is closed untouched (see
    the class docstring)."""
    target = Path(path) if path is not None else _events_mod.events_db_path()
    try:
        store_mod, workspace_mod = _couture_ledger_store()
    except Exception as exc:  # noqa: BLE001 - any seam failure is named, never raised
        return _seam_missing(target, exc)
    try:
        atelier = workspace_mod.Workspace(target.parent)
        store_mod.refuser_les_liens(atelier, target.name)
    except ValueError as exc:
        return _location_refused(target, exc)
    except (sqlite3.Error, OSError) as exc:
        return EventStore(target, None, "unavailable",
                          f"cannot check {target}: {type(exc).__name__}: {str(exc)[:200]}",
                          None)
    existed = target.exists()
    if not existed and not create:
        waiting = _proven_stagings(target)
        if waiting:
            # T-00000769 round 3: `recovery_pending` seen from a READER — the
            # daemon keeps the store absent and ingests nothing while these wait.
            items = "; ".join(
                f"{staging} (blocked by the existing {staging.parent.parent / 'exports' / staging.name})"
                if (staging.parent.parent / "exports" / staging.name).exists() else str(staging)
                for staging in waiting)
            return EventStore(target, None, "absent", (
                f"no SQLite store at {target}: {len(waiting)} retired export(s) wait for "
                f"promotion — {items}. The daemon ingests NOTHING until they are "
                f"promoted; move the blocking exports/<stamp>/ aside (it is never "
                f"replaced)"
            ), None)
        return EventStore(target, None, "absent", (
            f"no SQLite store at {target}: the daemon has not ingested anything yet "
            "(the spool files are the source of truth until it does)"
        ), None)
    migration: dict[str, Any] | None = None
    if not existed and create:
        migration = _migrate_legacy_spool(target)
        if migration.get("status") == "busy":
            return EventStore(target, None, "absent", (
                "a maintenance run (--merge-days/--compact) holds "
                ".maintenance.lock — the store will be created on the next tick"
            ), None)
        if migration.get("status") == "recovery_pending":
            # T-00000769 (S-00002537): accepted cost — while a retired export
            # cannot be promoted, nothing is ingested; nothing is lost either,
            # the spool waits, and `IngestLoop.tick` re-opens on every tick.
            pending = EventStore(target, None, "absent", (
                f"a retired export's prepared files could not be promoted "
                f"({migration.get('error')}) — the store is not created until they "
                f"are, so no row is ingested without them. Move the blocking "
                f"directory aside (an existing exports/<stamp>/ is never replaced); "
                f"retried on every tick"
            ), None)
            pending.open_report["export_recovery"] = {
                "promoted": list(migration.get("promoted") or []),
                "promotion_errors": list(migration.get("promotion_errors") or [])}
            return pending
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn, _ident, _cree = store_mod.ouvrir_sans_suivre(
            atelier, target.name, creer=create, mode=0o600,
            connecter=lambda uri: sqlite3.connect(
                uri, uri=True, timeout=_CONNECT_TIMEOUT_SECONDS, isolation_level=None))
    except ValueError as exc:
        # Binôme F4: nothing at the name any more (neither a file nor a link) — the
        # store VANISHED between the existence check and the open. That is an
        # absent store, not a refused location.
        try:
            parti = atelier.identite(target.name) is None
        except OSError:
            parti = False
        if parti:
            return EventStore(target, None, "absent", (
                f"{target} vanished before the open ({exc}) — nothing was followed or "
                f"created; retried on every tick"
            ), None)
        return _location_refused(target, exc)
    except (sqlite3.Error, OSError) as exc:
        # T-00000770 (decision of the orchestrator, pilot delegation): a store at
        # an UNCHANGED location that SQLite cannot open (permissions, CANTOPEN)
        # raises `OuvertureImpossible`, an `sqlite3.OperationalError` — an ACCESS
        # failure, so `unavailable`, never a refused location. Its SQLite cause is
        # named FIRST: the 200-char bound below must not cut it off a long path.
        sqlite_cause = f"{exc.__cause__} — " if exc.__cause__ is not None else ""
        return EventStore(target, None, "unavailable",
                          f"cannot open {target}: {type(exc).__name__}: {sqlite_cause}"
                          f"{str(exc)[:200]}",
                          None)
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        conn.close()
        return EventStore(target, None, "unavailable",
                          f"{target} is not a readable SQLite database "
                          f"({type(exc).__name__}) — move it aside to let the daemon "
                          f"rebuild from the spool", None)
    if version > SCHEMA_VERSION:
        # NEVER a rename, NEVER a v1 statement (iteration 1, C4): this is the
        # only local copy of data written by a newer daemon.
        conn.close()
        return EventStore(target, None, "schema_ahead", (
            f"{target} carries user_version={version} but this kit implements "
            f"v{SCHEMA_VERSION}: a NEWER kit wrote it and was rolled back. Nothing "
            "here will read or write it. Roll forward, or run `--export-spool` "
            "with the newer kit to get the data back as spool files."
        ), version)
    if version == 0:
        empty = _is_empty(conn)
        if not empty:
            conn.close()
            return EventStore(target, None, "unavailable", (
                f"{target} has user_version=0 but is not empty: an unversioned "
                "store cannot be migrated safely. Move it aside; the daemon "
                "rebuilds from whatever spool remains."
            ), 0)
        if not create:
            conn.close()
            return EventStore(target, None, "absent",
                              f"{target} exists but carries no schema yet", 0)
        try:
            _create_schema(conn)
            version = SCHEMA_VERSION
        except sqlite3.Error as exc:
            conn.close()
            return EventStore(target, None, "unavailable",
                              f"schema creation failed: {type(exc).__name__}: "
                              f"{str(exc)[:200]}", 0)
    elif version < SCHEMA_VERSION:
        # An older schema: walk the ladder. Unreachable today (v1 is the floor),
        # wired now so a v2 lands as one entry in `_MIGRATIONS`.
        version, error = _apply_migrations(conn, version)
        if error is not None:
            conn.close()
            return EventStore(target, None, "unavailable", error, version)
    # v1: apply the runtime knobs. WAL is set OUTSIDE any transaction —
    # `isolation_level=None` means this connection never has one implicitly
    # open, which is exactly why journal_mode takes effect (iteration 3, C7).
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # SAST false positive (repatriated from a consumer repo, T-00000310). Parameter binding is IMPOSSIBLE
        # here: SQLite accepts no bound `?` inside a PRAGMA. And the value is
        # not attacker-reachable -- `_BUSY_TIMEOUT_MS` is an int literal at
        # module scope, assigned once, never rebound, never derived from a
        # file, an argument or the environment. Exempted by rule name only.
        # nosemgrep: agents.security.python-sql-injection-string-format
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    except sqlite3.Error:
        pass  # a filesystem that refuses WAL still gives a correct, slower store

    store = EventStore(target, conn, "ok", None, version)
    # ORDERING IS LOAD-BEARING (iteration 5, C1): resolve + freeze the project
    # id, then catch up any rows written while identity was still `unset`, and
    # only then let a tick run. A project value that moved mid-session would
    # count one physical line under two projects across a failed delete.
    store.project = resolve_project_id()
    if create:
        # BOTH keys are always present in the journal, even when the pass is
        # deferred for want of an identity: "not run, and here is why" and "ran,
        # and found nothing to do" are different facts, and a missing key would
        # make them indistinguishable to whoever is diagnosing attribution.
        if store.project == PROJECT_UNSET:
            deferred = {"skipped": "project identity unresolved (project.json absent "
                                   "or unreadable) — retried at the next open"}
            store.open_report["relabel"] = dict(deferred)
            store.open_report["backfill"] = dict(deferred)
        else:
            store.open_report["relabel"] = _relabel_unset_locked(conn, store.project)
            store.open_report["backfill"] = _backfill_promote_project_field(conn, store.project)
        # T-00000769: the recovery of a retired export (`_promote_retired_staging`,
        # run by the legacy migration) is journalled beside the two passes, on the
        # same rule — always present, "not run, and why" distinct from "ran".
        # A promotion REFUSED here leaves a prepared export on disk; this key is
        # what names it (`--ingest-once` prints it).
        if migration is None:
            store.open_report["export_recovery"] = {
                "skipped": "database already present — the recovery runs only on "
                           "an absent database, i.e. right after an export retired it"}
        elif "promoted" in migration:
            store.open_report["export_recovery"] = {
                "promoted": list(migration["promoted"]),
                "promotion_errors": list(migration["promotion_errors"])}
        else:
            store.open_report["export_recovery"] = {
                "skipped": f"legacy migration ended '{migration.get('status')}' before "
                           f"the recovery ran: {migration.get('error') or 'no detail'}"}
    return store


# ---------------------------------------------------------------------------
# Two one-time passes at open, BOTH before the first tick.
# ---------------------------------------------------------------------------

# Rows per transaction for both passes. Short transactions on purpose: this is
# the store's FIRST write-side data migration, it runs at daemon start, and a
# single statement over a whole table would hold the write lock for as long as
# the table is big.
_OPEN_PASS_CHUNK = 500
# T-01M5T5G6MR: in each batch's transaction, before COMMIT — rows rewritten in place and the counter, or neither.
_SQL_REECRITURE = ("INSERT INTO meta (key, value) VALUES ('rewrite_generation', '1') ON CONFLICT (key) "
                   "DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)")


def _relabel_unset_locked(conn: sqlite3.Connection, project: str) -> dict[str, Any]:
    """Move rows stamped `PROJECT_UNSET` onto the now-known project id.

    `PROJECT_UNSET` in the `project` column has TWO meanings after V1-c, and
    telling them apart is this function's entire job:
      * "written before `project.json` existed" -> must be adopted;
      * "QUARANTINED: the body declares another project's id" -> must be left
        exactly where it is.

    THE CLASSIFICATION IS DONE IN PYTHON, AND THE `DELETE` IS SCOPED TO WHAT WE
    CLASSIFIED (plan-critic iteration 3, C1). V1-b ended this block with a bare
    `DELETE FROM events WHERE project = 'unset'`, which would destroy the
    quarantine at the very open that creates it — a foreign row, silently gone,
    two lines after being carefully preserved. Inside one chunk, `UPDATE OR
    IGNORE` moves what it can; a row still at `unset` afterwards is BY
    CONSTRUCTION a duplicate of a row already present under the real id (it was
    re-read after a failed delete), so deleting exactly those ids is
    de-duplication and never loss.

    Idempotent: a second call finds no adoptable row and reports zeroes.

    STREAMED, NEVER fetchall() (T-00000769 — the family of T-00000613, off the
    tick). This runs inside `open_store(create=True)`, i.e. at every daemon
    start and every `--ingest-once` once the identity resolves, and it used to
    pull every `unset` row WITH its body into one list: measured at 20.78 MB
    for 1,000 small `a` rows + 1,000 `b` rows of 20 KB, against 0.05 MB for a
    streamed cursor over the same rows (same report). On this repo every row
    is `unset` until `project.json` exists — 14,483 rows, 123.2 MB of channel-b
    body when measured — so the first open after the identity appears would
    have materialised the whole store. The bound is the PYTHON HEAP as
    `tracemalloc` sees it; RSS and SQLite's page cache are not measured.
    `body` stays IN the cursor, deliberately: the classifier parses it for
    every channel-`b` row once the own id is set, and a channel-`a` line is
    capped when written (`events._DATA_CAP_BYTES`, 4 KiB) — a by-id read would
    add one query per row and a "row vanished" case, for no gain.
    What stays O(rows) by design: `movable` (`array("q")`, 8 bytes a row),
    which the chunked writes need after the cursor is exhausted. NOTHING is
    written before that — every `BEGIN IMMEDIATE` comes after the loop — and
    the `except` spans the whole loop, since a cursor can fail on any row:
    `scanned` then counts the rows read before the error, and nothing moved."""
    report: dict[str, Any] = {"scanned": 0, "adopted": 0, "duplicates_deleted": 0,
                              "foreign_held": 0, "error": None}
    movable = array("q")
    try:
        for rowid, channel, body in conn.execute(
                "SELECT id, channel, body FROM events WHERE project = ?", (PROJECT_UNSET,)):
            report["scanned"] += 1
            if declares_foreign_project(str(channel), body, project):
                report["foreign_held"] += 1
                continue
            movable.append(int(rowid))
    except sqlite3.Error as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return report
    for start in range(0, len(movable), _OPEN_PASS_CHUNK):
        chunk = movable[start:start + _OPEN_PASS_CHUNK].tolist()
        placeholders = ",".join("?" * len(chunk))
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                f"UPDATE OR IGNORE events SET project = ? WHERE id IN ({placeholders})",
                [project, *chunk],
            )
            cursor = conn.execute(
                f"DELETE FROM events WHERE project = ? AND id IN ({placeholders})",
                [PROJECT_UNSET, *chunk],
            )
            deleted = int(cursor.rowcount or 0)
            conn.execute(_SQL_REECRITURE)
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return report
        report["duplicates_deleted"] += deleted
        report["adopted"] += len(chunk) - deleted
    return report


def _backfill_promote_project_field(conn: sqlite3.Connection, project: str) -> dict[str, Any]:
    """THE ONE-SHOT MATERIALISING BACKFILL (V1-c, iteration 9, C1 + C5).

    Every canal-B row whose body lacks the promoted `project_id` field is a
    PRE-V1-c line. This pass gives each one a field, once, by the only evidence
    such a line carries — its `provenance`, which V1-b wrote as
    `str(_project_root())`:

        provenance == this repo's current root  ->  the current `project_id`
                                                    (+ `project_attributed_by:
                                                    "backfill"`)
        anything else                           ->  the SENTINEL

    WHY MATERIALISE INSTEAD OF EVALUATING THE RULE AT RENDER TIME (C5): a rule
    evaluated on read would be permanent, not one-shot — every snapshot would
    compare paths for ever, and the "no path sniffing in steady state" promise
    would be false. Written once, the five display buckets partition the rows
    TOTALLY: after this pass no canal-B row lacks the field, and `persist()`
    guarantees no future line can.

    WHY THE SENTINEL RATHER THAN A SIXTH BUCKET (C1): a pre-V1-c line whose
    provenance does NOT equal the current root — a moved clone, a renamed repo,
    a Windows path re-cased, all compared against an exact
    `str(Path.resolve())` — has no evidence left. It is not foreign (nothing
    declares another id) and it is not attributable. `"unattributed"` is the
    honest answer, it keeps the row inside the census and inside the labelled
    totals, and no row leaves the partition without a trace.

    ONLY THE BODY IS REWRITTEN — NEVER A COLUMN OF THE UNIQUE KEY (`project`,
    `src_file`, `line_index`, `line_hash`, index `events_identity`). Moving one
    of those would mint a second identity for a line already stored, which is
    the double count this module exists to prevent.

    ACCEPTED, DECLARED COST: the rewritten body no longer matches its own
    `line_hash` (`_line_hash` hashes the raw bytes as read, `:351-354`), so
    `export_spool` is no longer byte-fidèle for these rows. Bounded, because the
    export retires the database in the same operation — nothing re-ingests the
    old bytes afterwards and no identity moves.

    IDEMPOTENT AND JOURNALLED (gate MUST-FIX M2). Restarted mid-pass — a chunk
    committed, the next not — the second run simply finds fewer rows without the
    field and finishes the job; run again after that it finds NONE and is a
    no-op reporting zeroes. So `rows_materialised == 0` means "already done",
    NOT "failed", and the two are distinguishable in the report because
    `scanned` is reported next to it."""
    report: dict[str, Any] = {"scanned": 0, "rows_materialised": 0, "concordant": 0,
                             "sentinelled": 0, "chunks": 0, "error": None}
    if project == PROJECT_UNSET:
        # Nothing to materialise TO. Left for the next open, which is exactly
        # what happens on the first daemon start of an un-inited repo.
        report["error"] = "project identity unresolved — backfill deferred"
        return report
    try:
        own_root = str(_otel_receiver_mod._project_root())
    except Exception:  # noqa: BLE001 - a resolver failure defers, never raises
        report["error"] = "project root unresolved — backfill deferred"
        return report
    # STREAMED, NEVER `fetchall()` (T-00000613, second site of the same defect).
    # This pass runs inside `open_store(create=True)`, which the dashboard
    # daemon's ingest thread calls AT START-UP — the very process the OS killed
    # while it held 3,5 Go. Materialising channel B here cost that process
    # 545 339 280 octets over 67 854 rows (measured 2026-09-14) before it had
    # served a single request, and it paid that to discover it had NOTHING to
    # do: the same day, `json_extract(body,'$.project_id') IS NULL` counted
    # ZERO rows. The peak was always the READ, never the work — `updates` holds
    # only the rows this pass actually amends, and stays small by construction.
    #
    # SAFE TO ITERATE: the write loop below begins only once this cursor is
    # exhausted, so no `UPDATE` ever runs against an open read. The `except`
    # now spans the whole loop rather than the `execute` alone, because with a
    # cursor the error can surface on any row — and a half-scanned pass that
    # reported success would leave rows unpromoted with nothing saying so.
    updates: list[tuple[str, int, bool]] = []
    try:
        for rowid, body in conn.execute(
                "SELECT id, body FROM events WHERE channel = 'b'"):
            try:
                record = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                continue  # a body we cannot parse is a body we cannot amend
            if not isinstance(record, dict):
                continue
            existing = record.get(_PROJECT_FIELD)
            if isinstance(existing, str) and existing.strip():
                continue  # already promoted: post-V1-c, or a previous run of this pass
            report["scanned"] += 1
            provenance = record.get("provenance")
            concordant = isinstance(provenance, str) and provenance == own_root
            if concordant:
                record[_PROJECT_FIELD] = project
                record[_ATTRIBUTED_BY_FIELD] = "backfill"
            else:
                record[_PROJECT_FIELD] = PROJECT_UNATTRIBUTED
            updates.append((json.dumps(record, ensure_ascii=False), int(rowid), concordant))
    except sqlite3.Error as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return report

    # Counted AFTER the commit, per chunk: a pass interrupted between two chunks
    # must report what it actually wrote, not what it intended to write.
    for start in range(0, len(updates), _OPEN_PASS_CHUNK):
        chunk = updates[start:start + _OPEN_PASS_CHUNK]
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany("UPDATE events SET body = ? WHERE id = ?",
                             [(payload, rowid) for payload, rowid, _c in chunk])
            conn.execute(_SQL_REECRITURE)
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return report
        report["chunks"] += 1
        report["rows_materialised"] += len(chunk)
        report["concordant"] += sum(1 for _p, _r, concordant in chunk if concordant)
        report["sentinelled"] += sum(1 for _p, _r, concordant in chunk if not concordant)
    return report


# THE MIGRATION LADDER, present from v1 (spec §A.2: "`PRAGMA user_version` + chemin
# de migration DÈS LA V1 — la v2 changera le schéma, une base sans version se
# jette"). Empty today because there is no version below 1 to come from, and that
# is the point: the mechanism exists before it is needed, so v2 lands as one entry
# here instead of as a rewrite of `open_store`.
#
# CONTRACT for a future entry, keyed by the version it upgrades FROM:
#   * it receives an open connection with NO transaction in flight;
#   * it opens its own `BEGIN IMMEDIATE`, does its DDL/DML, bumps
#     `PRAGMA user_version`, and COMMITs — so an interrupted upgrade leaves the
#     OLD version stamped and is retried, never a half-migrated schema;
#   * it never deletes a row it cannot re-derive from the spool.
_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {}


def _apply_migrations(conn: sqlite3.Connection, version: int) -> tuple[int, str | None]:
    """Walk the ladder from `version` up to `SCHEMA_VERSION`. Returns
    `(reached_version, error)`; a missing rung is reported rather than skipped —
    a silently un-migrated schema is the L-00000057 false-anchor shape."""
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            return version, (
                f"no migration registered from user_version={version} to "
                f"{SCHEMA_VERSION}: this store cannot be upgraded in place. Move it "
                f"aside and let the daemon rebuild from the spool."
            )
        try:
            step(conn)
        except sqlite3.Error as exc:
            return version, f"migration from v{version} failed: {type(exc).__name__}: {str(exc)[:200]}"
        reached = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if reached <= version:
            return version, (
                f"migration from v{version} did not bump user_version — refusing to "
                f"loop"
            )
        version = reached
    return version, None


def _is_empty(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row) and int(row[0]) == 0


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in _SCHEMA_STATEMENTS:
            conn.execute(statement)
        # `PRAGMA user_version` does not accept a bound parameter; the value is
        # a module constant, never external input.
        # SAST false positive (repatriated from a consumer repo, T-00000310): binding is impossible in a PRAGMA,
        # and `SCHEMA_VERSION` is an int literal at module scope, coerced with
        # int() here on top. Exempted by rule name only.
        # nosemgrep: agents.security.python-sql-injection-string-format
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def _migrate_legacy_spool(db_target: Path) -> dict[str, Any]:
    """ONE-TIME, on a still-ABSENT database, under `events.maintenance_lock()`.

    Folds every PAST day's per-writer files into `D.merged.jsonl` exactly once,
    BEFORE anything is ingested. This is the only surviving caller of
    `merge_day_files` (see events.py's deprecation-surface comment). Doing it
    here and only here is what disarms the legacy triangle: a `D.merged.jsonl`
    left behind by a crashed merger plus its surviving originals would
    otherwise be ingested as two independent `src_file`s carrying the same
    lines (iteration 5, C2). The merger's own line-containment check removes
    that residue instead.

    Taking the SAME lock as the `--merge-days` gate is MUST-FIX C2: the gate
    reads "does events.db exist" and this function creates it, so the two must
    not be able to interleave (iteration 7, C2).

    Nothing is recorded in the database to remember that this ran — that guard
    would live in the very file a rollback removes (iteration 5, C3). The guard
    is the ABSENCE of the database, checked under the lock, plus the merger's
    own idempotence."""
    report: dict[str, Any] = {"status": "skipped", "merge": None}
    try:
        with _events_mod.maintenance_lock():
            if db_target.exists():
                # Someone created it while we waited for the lock.
                report["status"] = "already_present"
                return report
            # T-00000769: an `--export-spool` that retired the database but died
            # before promoting its prepared export. Here, on a still-ABSENT
            # database and under the lock, is the one place that can finish it.
            try:
                promotion = _promote_retired_staging(db_target)
            except Exception as exc:  # noqa: BLE001 - a recovery never blocks the store
                promotion = {"promoted": [],
                             "errors": [f"{type(exc).__name__}: {str(exc)[:200]}"]}
            report["promoted"] = promotion["promoted"]
            report["promotion_errors"] = promotion["errors"]
            if promotion["errors"]:
                # NOT a skip (F2 of both critics, round 2): creating the store
                # now would end the recovery for good — the next open finds a
                # database and never looks again. `open_store` answers `absent`
                # instead, and the daemon retries on every tick.
                report["status"] = "recovery_pending"
                report["error"] = "; ".join(promotion["errors"])[:1000]
                return report
            try:
                report["merge"] = _events_mod.merge_day_files()
                report["status"] = "merged"
            except Exception as exc:  # noqa: BLE001 - a legacy fold must not
                # block the store; unmerged files are ingested as themselves.
                report["status"] = "merge_failed"
                report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    except _events_mod.MaintenanceLockBusy:
        report["status"] = "busy"
    except Exception as exc:  # noqa: BLE001
        report["status"] = "lock_failed"
        report["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return report


def _promote_retired_staging(db_path: Path) -> dict[str, Any]:
    """RECOVERY of `export_spool`'s window between the retire and the
    promotion (T-00000769, T2 of critic-opus). Called on a still-absent
    database, under `.maintenance.lock`, by `_migrate_legacy_spool` (every
    create=True open until it succeeds: `recovery_pending`) and by
    `main --export-spool` on an absent store — the path an operator still has
    after rolling back to a kit that never runs this recovery (F4 of
    critic-opus, round 2).

    A prepared export `<spool>/exports.partial/<stamp>/` is promoted to
    `<spool>/exports/<stamp>/` IFF `<db>.exported-<stamp>` exists: that file is
    the proof the export crossed its commit point, so its rows live nowhere
    else any more. Without it, the staging belongs to an export that never
    retired its database (interrupted, refused) — promoting it would count its
    rows a second time — and it is left alone. DELETES NOTHING: a refused
    promotion (existing target, I/O error) keeps its staging and is reported."""
    report: dict[str, Any] = {"promoted": [], "errors": []}
    for base in (_events_dir(), _otel_dir()):
        if base is None:
            continue
        partial = base / _EXPORTS_PARTIAL
        try:
            stagings = (sorted(path for path in partial.iterdir()
                               if path.is_dir() and not path.is_symlink())
                        if partial.is_dir() else [])
        except OSError as exc:
            report["errors"].append(f"{partial}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        for staging in stagings:
            if not _retired_proof(db_path, staging.name).exists():
                continue
            final = base / "exports" / staging.name
            try:
                _promote_staged(staging, final)
            except OSError as exc:
                report["errors"].append(
                    f"{staging}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            report["promoted"].append(str(final))
    return report


# ---------------------------------------------------------------------------
# What the Couverture view renders: "ingestion en retard depuis X".
# ---------------------------------------------------------------------------

def ingestion_status(now: datetime | None = None,
                     store: EventStore | None = None) -> dict[str, Any]:
    """Reader-side, memory-free lag report — exit criterion 3's visible half.

    Computed from facts on disk plus the store's own last-tick note, never from
    the daemon's in-memory offsets: the HTTP thread does not have them, and a
    lag the UI cannot compute is a lag nobody sees."""
    now = now or datetime.now(timezone.utc)
    owned = store is None
    store = store or open_store(create=False)
    try:
        pending = _pending_spool(now)
        payload: dict[str, Any] = {
            "source": "sqlite" if store.status == "ok" else store.status,
            "schema_version": store.user_version,
            "schema_supported": SCHEMA_VERSION,
            "db": str(store.path),
            "reason": store.reason,
            "last_ingest_at": store.meta("last_ingest_at"),
            "rows_max_id": store.max_rowid("a"),
            "tick_seconds": TICK_SECONDS,
            **pending,
        }
        late = bool(pending["spool_files_pending"]) and (
            pending["oldest_pending_age_seconds"] or 0.0) >= _LATE_SECONDS
        payload["late"] = late
        payload["message"] = (
            f"ingestion en retard depuis {pending['behind_since']} "
            f"({pending['spool_files_pending']} fichier(s) de spool en attente)"
            if late else None
        )
        if store.status == "schema_ahead":
            payload["message"] = (
                "ingestion arrêtée : la base a été écrite par une version plus "
                "récente du kit (mode dégradé, aucune écriture v1)"
            )
        payload["doctrine"] = (
            "a spool file still on disk is normal for up to one tick; past "
            f"{int(_LATE_SECONDS)}s it is a LAG and is said out loud. Absence of "
            "an ingestion is never rendered as zero activity."
        )
        return payload
    finally:
        if owned:
            store.close()


def _pending_spool(now: datetime) -> dict[str, Any]:
    """Count + oldest mtime of the spool files still on disk. CHANNEL A ONLY,
    and that stays a deliberate scope choice in V1-c: under V1-b channel B's
    files were retained by design, so counting them would have reported a
    permanent, meaningless lag; now that they are consumed and deleted, adding
    them would change what `late` MEANS for every existing consumer of this
    payload. Widening the lag report is its own change, not a side effect of
    this one."""
    base = _events_dir()
    count = 0
    total_bytes = 0
    oldest: float | None = None
    if base is not None:
        try:
            candidates = sorted(base.glob("*.jsonl")) + sorted(base.glob("exports/*/*.jsonl"))
        except OSError:
            candidates = []
        for path in candidates:
            try:
                stat_result = path.stat()
            except OSError:
                continue
            count += 1
            total_bytes += stat_result.st_size
            if oldest is None or stat_result.st_mtime < oldest:
                oldest = stat_result.st_mtime
    behind_since = None
    age = None
    if oldest is not None:
        behind_since = datetime.fromtimestamp(oldest, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        age = max(0.0, now.timestamp() - oldest)
    return {
        "spool_files_pending": count,
        "spool_bytes_pending": total_bytes,
        "behind_since": behind_since,
        "oldest_pending_age_seconds": round(age, 1) if age is not None else None,
    }


def store_fingerprint(path: str | Path | None = None) -> tuple:
    """`(path, present, mtime_ns, size, (status, data_generation))`, every memo's key; never
    raises. T-00000615: in WAL the main file moves only at a checkpoint, so the key reads the
    DATA generation — not the `-wal` stat nor `data_version`: the idle tick moves both."""
    target = Path(path) if path is not None else _events_mod.events_db_path()
    try:
        stat_result = target.stat()
    except OSError:
        return (str(target), False, None, None, None)
    try:  # `open_store` keeps T-00000770's no-follow open: never a bare `sqlite3.connect`
        with open_store(target, create=False) as store:
            generation = (store.status, store.meta_counter("data_generation"))
    except Exception:  # noqa: BLE001 - a cache key must never raise
        generation = None
    return (str(target), True, stat_result.st_mtime_ns, stat_result.st_size, generation)


def store_footprint(now: datetime | None = None,
                    path: str | Path | None = None) -> dict[str, Any]:
    """T-00000612's instrument, and NOTHING else: it makes `events.db`'s growth
    VISIBLE so the pilot can decide what to do about it. It decides nothing and
    it does not extrapolate — two points are not a curve.

    The RAW footprint on disk: the row count of the `events` table, the RAW
    timestamp of the OLDEST row plus its age in seconds, and the RAW byte size of
    the file (with the `-wal` sidecar reported SEPARATELY when it exists). Bytes
    are raw — the conversion belongs to whoever DISPLAYS them (`T-00000613` cost a
    unit-conversion fix); nothing here is divided, rounded or scaled.

    READ-ONLY BY CONSTRUCTION. The connection is opened `mode=ro`, so this path
    can neither ingest nor fold (`_fold_retention_locked`), and it runs no
    retention, no VACUUM, no purge and no spool migration — a read-only handle
    may not write. It is therefore safe to call against the live daemon's store.

    `ts` is the `events` table's raw event-timestamp column (read from the schema
    of `events.db`); `MIN(ts)` is SQLite-native and skips NULLs, so the oldest is
    the oldest STAMPED row. An absent database, or one whose table the daemon has
    not created yet (`T-00000206`'s half-created window), is a first-class state
    — `present`/`event_count` stay `None` — never an error."""
    now = now or datetime.now(timezone.utc)
    target = Path(path) if path is not None else _events_mod.events_db_path()
    footprint: dict[str, Any] = {
        "db": str(target),
        "present": False,
        "event_count": None,
        "oldest_ts": None,
        "oldest_age_seconds": None,
        "bytes": None,
        "wal_bytes": None,
    }
    try:
        footprint["bytes"] = target.stat().st_size
    except OSError:
        return footprint  # absent store is a displayable state, not an error
    footprint["present"] = True
    wal = target.with_name(target.name + "-wal")
    try:
        footprint["wal_bytes"] = wal.stat().st_size
    except OSError:
        footprint["wal_bytes"] = None
    # `mode=ro`: never creates the file, never writes a WAL frame, never
    # checkpoints. `as_uri()` percent-encodes the path so a space or `?` in it
    # cannot break the URI (and cannot be read back as a query parameter).
    try:
        uri = f"{target.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=_CONNECT_TIMEOUT_SECONDS)
    except (sqlite3.Error, ValueError, OSError):
        return footprint
    try:
        try:
            row = conn.execute("SELECT COUNT(*), MIN(ts) FROM events").fetchone()
        except sqlite3.OperationalError as exc:
            # The file can exist a tick before its table does (T-00000206); that
            # is the same "nothing ingested yet" state as an absent database.
            if "no such table" in str(exc):
                return footprint
            raise
        footprint["event_count"] = int(row[0])
        oldest = row[1]
        if isinstance(oldest, str) and oldest:
            footprint["oldest_ts"] = oldest
            try:
                parsed = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                footprint["oldest_age_seconds"] = (now - parsed).total_seconds()
    finally:
        conn.close()
    return footprint


# ---------------------------------------------------------------------------
# The 5 s tick, inside the daemon's existing process.
# ---------------------------------------------------------------------------

class IngestLoop:
    """The daemon's ingestion thread. One `EventStore` for its whole life (its
    resume offsets live there), one `ingest_once()` per tick.

    Why a thread and not a process: the spec is explicit — "tick d'ingestion 5 s
    dans la boucle existante du démon (pas de nouveau processus)". The single
    writer is the daemon, and a second process would be a second writer."""

    def __init__(self, interval: float = TICK_SECONDS,
                 on_report: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.interval = interval
        self.on_report = on_report
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.store: EventStore | None = None
        self.ticks = 0
        self.last_report: dict[str, Any] | None = None

    def start(self) -> bool:
        if self.thread is not None:
            return False
        self.thread = threading.Thread(target=self._run, daemon=True, name="event-ingest")
        self.thread.start()
        return True

    def _run(self) -> None:
        try:
            self.store = open_store(create=True)
        except Exception:  # noqa: BLE001 - the daemon must survive a bad store
            self.store = None
        while not self.stop_event.is_set():
            report = self.tick()
            # A truncated batch means there is more waiting RIGHT NOW: drain at
            # I/O speed instead of one `_BATCH_ROW_CAP` slice per interval, so a
            # boot catch-up of hundreds of files does not take minutes.
            if report is not None and report.get("batch_truncated"):
                continue
            # `Event.wait` rather than sleep: a `stop()` during an interval ends
            # the loop at once, and `notify_dirty` can cut the wait short.
            self.stop_event.wait(self.interval)

    def tick(self) -> dict[str, Any] | None:
        if self.store is None or self.store.status == "absent":
            # `absent` after a create=True open means the one-time legacy
            # migration found `.maintenance.lock` held by an operator run, or
            # (T-00000769) a retired export whose promotion is still refused, or
            # (T-00000770) the store location was REFUSED — a link at
            # `events.db` or a side file, a second hard name, a non-regular file
            # (`open_report["location_refused"]`) — or the `cadre.ledger.store`
            # seam could not be loaded (`open_report["seam_missing"]`), or the
            # store vanished before the open. Retry on the next tick rather than
            # giving up for the daemon's lifetime: the daemon starts again by
            # itself once the cause is removed.
            #
            # An `unavailable` store is NEVER re-opened here (S-00002817, stated,
            # not changed): a corrupt file, an unversioned non-empty store, or
            # (T-00000770) an EXISTING store SQLite cannot open — permissions,
            # CANTOPEN — keeps its status for the daemon's lifetime. Fix the
            # cause, then RESTART the daemon.
            try:
                if self.store is not None:
                    self.store.close()
                self.store = open_store(create=True)
            except Exception:  # noqa: BLE001 - the daemon survives a bad store
                self.store = None
        if self.store is None:
            return None
        try:
            report = self.store.ingest_once()
        except Exception as exc:  # noqa: BLE001 - a tick may never kill the daemon
            report = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        self.ticks += 1
        self.last_report = report
        if self.on_report is not None:
            try:
                self.on_report(report)
            except Exception:  # noqa: BLE001
                pass
        return report

    def stop(self, timeout: float = 10.0) -> bool:
        """True when the thread is confirmed stopped. A False here means the
        SOLE-WRITER invariant is still held by this process, and the caller must
        NOT release the daemon lock (iteration 2, C10) — a second daemon
        starting while this thread still writes would be a second writer."""
        self.stop_event.set()
        thread = self.thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        if thread.is_alive():
            return False
        if self.store is not None:
            self.store.close()
        self.thread = None
        return True


def _pid_runs_dashboard_daemon(pid: int, root: Path) -> bool | None:
    """Does `pid` run THIS project's `dashboard_daemon.py`? (Round 3,
    S-00002562: a live pid is not the daemon's — pids are recycled.) Read from
    `ps -ww -p <pid> -o command=` (`-ww`: never truncated to a width):

      * `True`  — the line shows `dashboard_daemon.py` AND its `--root`
                  (the daemon is spawned as `… --daemon --root <root>`, root
                  last) resolves to `root`;
      * `False` — the line does not show `dashboard_daemon.py` (a recycled
                  pid), or its `--root` resolves to ANOTHER existing directory
                  (another project's daemon inherited the pid);
      * `None`  — cannot tell, so the caller fails CLOSED (final pass, F2 of
                  critic-opus / T1 of critic-fable: these used to read as
                  `False`, i.e. `stale`, i.e. an export under a live daemon):
                  an empty answer (`ps` refused, or the pid gone between two
                  probes), a non-zero exit with a stderr, a daemon line whose
                  `--root` is missing or does not resolve, Windows (no `ps`),
                  `ps` missing, failing or slow. Never raises."""
    if _IS_WINDOWS:
        return None
    try:
        completed = subprocess.run(["ps", "-ww", "-p", str(int(pid)), "-o", "command="],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, timeout=5, check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    line = (completed.stdout or "").strip()
    if completed.returncode != 0 and (completed.stderr or "").strip():
        return None
    if not line:
        return None
    if "dashboard_daemon.py" not in line:
        return False
    marker = line.rfind("--root")
    if marker < 0:
        return None
    named = line[marker + len("--root"):].lstrip(" =").strip()
    try:
        named_path = Path(named)
        if not named or not named_path.is_dir():
            return None
        return named_path.resolve() == Path(root).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _dashboard_daemon_state() -> tuple[str, int | None]:
    """`(state, pid)`. `state` is `alive` · `stale` · `absent` —
    `dashboard_daemon.daemon_status`'s own verdict for this project's root
    (pid alive AND tokenised ping answered) — refined into `unresponsive` when
    that verdict is `stale` but the lock's pid is ALIVE (S-00002536: the state
    a daemon can sit in while it still holds the store) AND, round 3, its
    command line shows `dashboard_daemon.py` or cannot be read (fail closed);
    a live pid running something else is a recycled pid, i.e. `stale`. Or
    `unknown` on ANY failure to load or probe, never a raise. `pid` is the
    lock's, printed by the refusal; None when there is no readable lock.

    LOADED LAZILY, in the CLI path only (T-00000769): `dashboard_daemon.py`
    pulls in `dashboard.py` and its readers, a weight neither the daemon's own
    import of this module nor the hooks should pay. `unknown` does not refuse:
    `--export-spool` is the rescue path when a newer kit is broken, and a
    broken dashboard must not lock the operator out of it — the printed
    payload carries the state instead."""
    try:
        daemon = _load_sibling("_store_dashboard_daemon", "dashboard_daemon.py")
        root = daemon._project_root()
        state, lock = daemon.daemon_status(root)
        pid = int(lock["pid"]) if isinstance(lock, dict) else None
        if state == "stale" and pid is not None and daemon.pid_alive(pid):
            if _pid_runs_dashboard_daemon(pid, root) is False:
                return "stale", pid
            return "unresponsive", pid
        return str(state), pid
    except Exception:  # noqa: BLE001 - a probe that cannot run says so
        return "unknown", None


def _refuse_export_under_live_daemon(seen: list | None = None) -> str | None:
    """`export_spool`'s `before_retire`: read the daemon state AGAIN just
    before the retire — a session that started mid-export has relaunched it.
    `seen` receives the `(state, pid)` read, so the payload reports THIS
    probe's pid (final pass: `daemon_pid` in every result)."""
    state, pid = _dashboard_daemon_state()
    if seen is not None:
        seen.append((state, pid))
    if state in _DAEMON_REFUSED_STATES:
        return _daemon_refusal_reason(state, pid)
    return None


def main(argv: list[str] | None = None) -> int:
    """Operator surface. `--ingest-once` and `--status` are diagnostics;
    `--export-spool` is the rollback path: rc 0 exported cleanly, rc 1 not
    exported (or exported with a promotion left to the next daemon start, or
    with unsafe `src_file` keys skipped), rc 2 refused because the dashboard
    daemon is alive or unresponsive. On an ABSENT store it finishes a pending
    promotion instead (rc 0 when nothing failed, 1 otherwise) — unless the store
    location is REFUSED or the `cadre.ledger.store` seam is MISSING (T-00000770):
    then rc 1, nothing exported, promoted or removed, and the reason says why."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="event_store.py",
        description="SQLite projection of the canal-A/B spool (V1-b, T-00000049).",
    )
    parser.add_argument("--status", action="store_true",
                        help="Print the store's status and ingestion lag.")
    parser.add_argument("--ingest-once", action="store_true",
                        help="Run ONE ingest tick synchronously (diagnostics).")
    parser.add_argument("--export-spool", action="store_true",
                        help="Rollback: re-emit the store as spool JSONL + digests, "
                             "then retire events.db. Refused (rc 2) while the "
                             "dashboard daemon is alive or unresponsive; rc 1 when "
                             "not cleanly exported. On an absent store: finish a "
                             "pending promotion.")
    args = parser.parse_args(argv)

    _events_mod.force_utf8_stdio()
    if args.export_spool:
        daemon, daemon_pid = _dashboard_daemon_state()
        if daemon in _DAEMON_REFUSED_STATES:
            print(json.dumps({
                "status": "refused", "daemon": daemon, "daemon_pid": daemon_pid,
                "reason": f"{_daemon_refusal_reason(daemon, daemon_pid)}. Nothing was "
                          f"written and the database is untouched.",
            }, ensure_ascii=False, indent=2))
            return 2
        store = open_store(create=False)
        if store.status == "absent" and (store.open_report.get("location_refused")
                                         or store.open_report.get("seam_missing")):
            # T-00000770: a REFUSED location (a link, pending or not — a link to
            # a real third-party base was followed, exported and retired before)
            # or a MISSING seam: nothing is exported, promoted or removed, and the
            # reason says which — never « carries no schema ». rc 1: not exported.
            store.close()
            print(json.dumps({
                "status": "absent", "reason": store.reason,
                "daemon": daemon, "daemon_pid": daemon_pid,
            }, ensure_ascii=False, indent=2))
            return 1
        if store.status == "absent" and (store.path.exists() or store.path.is_symlink()):
            # T-00000770: this `is_symlink()` stays reachable by a RACE only — a
            # link planted after an `open_store` that refused nothing; its message
            # ("carries no schema") predates it and is kept.
            # Round 3 (critic-fable): a file that opens as `absent` exists but
            # carries no schema (user_version 0, empty). There is nothing to
            # export and nothing to promote next to a database file — and the
            # absent-store path below would have called it "appeared meanwhile".
            store.close()
            print(json.dumps({
                "status": "absent", "daemon": daemon, "daemon_pid": daemon_pid,
                "reason": f"{store.path} exists but carries no schema: nothing to "
                          f"export. Left untouched.",
            }, ensure_ascii=False, indent=2))
            return 1
        if store.status == "absent":
            # Nothing to export — but maybe an export to FINISH: a retire whose
            # promotion was cut short, on a kit (an older one, after the very
            # rollback this exports for) that never runs the recovery at open.
            store.close()
            db_path = store.path
            locked, recovery = _under_maintenance_lock(
                lambda: {"promoted": [], "errors": [],
                         "skipped": "the database appeared meanwhile"}
                if db_path.exists() else _promote_retired_staging(db_path))
            if not locked:
                recovery = {"promoted": [], "errors": [
                    f".maintenance.lock could not be taken ({recovery}) — re-run"]}
            print(json.dumps({"status": "absent", "reason": store.reason,
                              "daemon": daemon, "daemon_pid": daemon_pid,
                              "recovery": recovery},
                             ensure_ascii=False, indent=2))
            return 0 if not recovery["errors"] else 1
        seen: list = []
        try:
            result = store.export_spool(
                before_retire=lambda: _refuse_export_under_live_daemon(seen))
        finally:
            store.close()
        # The LAST probe is the one the outcome is about: the re-check when it
        # ran (its pid is the one a re-check refusal names), else the first.
        result["daemon"], result["daemon_pid"] = seen[-1] if seen else (daemon, daemon_pid)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "refused":
            return 2
        clean = (result.get("status") == "exported" and result.get("reason") is None
                 and not result.get("rows_skipped_unsafe_name"))
        return 0 if clean else 1
    if args.ingest_once:
        store = open_store(create=True)
        try:
            # `open_report` is printed WITH the tick: the two one-time passes
            # (relabel + V1-c backfill) run at open, so an operator diagnosing
            # attribution needs their counts next to the tick's own.
            print(json.dumps({"open": store.open_report,
                              "project": store.project,
                              "tick": store.ingest_once()},
                             ensure_ascii=False, indent=2))
        finally:
            store.close()
        return 0
    if args.status:
        # T-00000612 + correctif binôme PORTE 3 (C3): the store's RAW footprint,
        # added as its OWN key so the existing keys and their order are untouched.
        # `ingestion_status()` is left intact on purpose (R-A9) — `dashboard.py` /
        # `dashboard_readers.py` read it directly, never this CLI's JSON.
        #
        # ORDER IS LOAD-BEARING: `store_footprint` FIRST. It opens `mode=ro`, so
        # it never creates the file, never writes a WAL frame and never
        # checkpoints — it reports `-wal` exactly as it is on disk.
        # `ingestion_status()` opens the store READ-WRITE (`open_store` →
        # `journal_mode=WAL`, `isolation_level=None`) and, when its connection is
        # the last one to close, SQLite CHECKPOINTS the WAL — folding `-wal` back
        # into the `.db` and truncating/removing it. It may also let SQLite create
        # empty `-wal`/`-shm` sidecars. Taken in the other order, the footprint
        # would lose the WAL a KILLED writer left behind (measured by the critic:
        # 3 712 152 bytes reported as None). Captured FIRST, it renders the state
        # BEFORE any read-write open.
        footprint = store_footprint()
        payload = ingestion_status()
        payload["store_footprint"] = footprint
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
