#!/usr/bin/env python3
"""Query and annotate the SQLite index store -- THE agent-facing surface of
`index.db` (schema v3 -- `body_sha` since T-00000377). Since T-00000668 the store
is MACHINE state OUTSIDE the repository, `cadre.paths.index_db()` =
`state_project()/index/index.db`, located through `migrate_index_to_db.db_path`
alone: nothing here composes its path, and nothing here asks for it to be
committed. Where `cadre.paths` cannot be loaded (outside a kit clone, package not
installed) every subcommand REFUSES naming it; the `SYMBOLS*.md` files stay the
authority.

WHY THIS FILE EXISTS. `migrate_index_to_db.py` builds the store; until this CLI
nothing READ it, so agents kept grepping the `SYMBOLS_*.md` shards (10 of them on
one consumer project) for questions the shards cannot express at all -- "who calls
SYM-042" is a reverse edge, and the files say so themselves: *reverse edges are
NOT stored*. The DB has the `edges` table. This is how an agent reaches it.

RAW SQL STAYS FORBIDDEN TO AGENTS. This module is the only authorised surface:
one place to bound output, one place to check freshness, one place to keep the
journal append-only. A hand-written `sqlite3 index.db "SELECT ..."` bypasses all
three at once.

THE STORE IS ADVISORY AND CAN BE STALE, AND THAT IS THE WHOLE DIFFICULTY.
`build_index.py` keeps writing the FILES and no automatic resync exists in v1, so
every rebuild leaves the DB a generation behind. An agent that queries a stale DB
gets symbols from ANOTHER generation and believes them -- strictly worse than
grepping, because the answer is confidently wrong. So EVERY subcommand asks
`migrate_index_to_db.db_generation_behind()` (that module OWNS the comparison --
there is one freshness definition in this repo, not two) and:

  * by default prints an unmissable `!! DB STALE ...` banner at the HEAD of the
    output, naming `--resync`. `!!` is not a shape any data line can take;
  * with `--strict` it REFUSES to answer at all and exits non-zero.

WHICH POSTURE SHOULD AN AGENT ADOPT? Default (warn) for exploration, where you
are going to re-locate by symbol NAME anyway before trusting a line range.
`--strict` whenever the answer is about to become CODE or a decision, and in any
non-interactive consumer (a hook, a script, another tool) -- there, a banner
nobody reads is the same as no banner.

`index.db` IS NEVER CREATED HERE. `sqlite3.connect()` on a missing path creates
the file, so a missing store is detected with `exists()` BEFORE any connection,
and reads then open a `mode=ro` URI which cannot create a database either -- the
same two guards `migrate_index_to_db.read_db_generation()` documents.

`--source` SHOWS THE BODY AND SAYS WHETHER IT STILL MATCHES (T-00000377). The
store carries a `body_sha` per symbol; this flag slices `start..end` out of the
WORKING TREE, re-hashes what it just read, and prints a deterministic 0-LLM crux
with one of four verdicts — `FRESH @ <gen>`, `DRIFTED @ <gen>`, `UNKNOWN` (the
store holds no hash: a pre-v3 store, or one not resynced yet) or `MISSING` (the
file or the range is gone). THE VERDICT NAMES ITS REFERENCE because the store is
advisory: it compares the tree to the STORE, which after any rebuild is one
generation behind the index files — so a `DRIFTED` can come from the store's lag,
and a note says exactly that whenever the lag is real. Nothing here reads the
lateral `INDEX_BODIES.json`: that file feeds the migration, not this CLI, so
there is one generation in play and no second coupling.

THE FRESHNESS OVERLAY (T-00000378) — AND IT IS A BEHAVIOUR CHANGE, SAID SO.
`query` no longer answers from the store alone. It diffs the WORKING TREE against
the store's own generation (`git diff <anchor>`), re-extracts the changed files
with the builder's extractors, and REPAIRS the answer in flight: line ranges are
the tree's, a symbol the tree no longer holds is marked `[GONE dans l'arbre]`,
and a symbol the tree holds but the store does not is listed under `# HORS STORE`
— never invented into `results[]` with a fabricated id. NOT ONE BYTE IS WRITTEN:
no file of `.agents/state/index/` is opened for writing, the DB connection is
`mode=ro`, and the only staging any of it does is a ctags listfile in the SYSTEM
temp dir, on a branch this repo never takes.

IT IS ON BY DEFAULT, and that changes what every existing caller receives —
including a `--strict` one. `--strict` stays ORTHOGONAL and keeps its meaning: it
refuses a stale STORE (index.db vs the index FILES, exit 3). The overlay answers
a different question (the index FILES vs the working TREE) and neither implies
the other, so a `--strict` run that is allowed to answer now answers with tree
bounds. Turn it off with `--no-refresh`, or with `AGENTS_INDEX_NO_REFRESH=1` for
a whole non-interactive session; either way the answer SAYS it was disarmed,
because a silent overlay reads exactly like "nothing has changed" (L-00000136).
Availability has four named causes of refusal — no generation in the store, an
anchor that is not hexadecimal, an anchor `git cat-file -e` cannot resolve, and a
published directory scope that disagrees with this machine's — and an unavailable
overlay degrades to the baseline answer PLUS the line naming which one bit.

Subcommands:
    query     search symbols; follow `edges` both ways (`--callers`/`--callees`)
    annotate  write an authored `:: purpose` / module Role-Owner (table + journal)
    retire    retract an annotation that became false (the journal is APPENDED to)
    compact   report and tidy (never deletes a tombstone, never touches a file)

Usage:
    python .agents/bin/symbols.py query --name build [--limit 40] [--json] [--strict]
    python .agents/bin/symbols.py query --name build --source [--source-lines 8]
    python .agents/bin/symbols.py annotate --symbol SYM-042 --purpose "..."
    python .agents/bin/symbols.py retire --symbol SYM-042
    python .agents/bin/symbols.py compact

Exit codes: 0 = answered (possibly with a stale banner); 1 = a named refusal on
stderr, nothing written; 3 = `--strict` refused a stale store. argparse's own
usage errors keep exiting 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # run as a script OR imported from a test
    sys.path.insert(0, str(HERE))

import build_index as bi  # noqa: E402  -- path shim above must run first
import migrate_index_to_db as mig  # noqa: E402

Refusal = mig.Refusal  # one refusal type across the index tooling, not two


class StaleRefusal(Refusal):
    """`--strict` met a stale store. A SUBCLASS, so it carries its own exit code
    without the handler having to recognise a message string."""


# Bounds. A default that returns everything is a default that floods an agent's
# context; a truncation that stays quiet reads as full coverage, so both the cap
# and the fact that it bit are printed.
DEFAULT_LIMIT = 40
PURPOSE_WIDTH = 64
WARN = "!!"  # a prefix no data row can wear -- see the module docstring
EXIT_REFUSED = 1
EXIT_STALE_STRICT = 3
RESYNC_CMD = "python .agents/bin/migrate_index_to_db.py --resync"
APPLY_CMD = "python .agents/bin/migrate_index_to_db.py --apply"
# `--name` goes to FTS5 only for a plain identifier. Anything carrying a wildcard
# or FTS syntax (quotes, colons, NEAR, parentheses) takes the LIKE path, where
# the semantics are ours instead of the query parser's.
FTS_SAFE_RE = re.compile(r"[A-Za-z0-9_]+")
EDGES_CAVEAT = ("edges are APPROXIMATE (name-matched by build_index.py) -- "
                "leads, not proof")
ANNOTATION_FIELDS = ("purpose", "role", "owner")

# --- `--source` bounds. TWO UNITS, AND THEY ARE NOT THE SAME ONE (↯ C49) -----
# SOURCE_MAX_ROWS bounds the RESULT ROWS -- the symbols -- that get a crux TEXT.
# `--source-lines` bounds the SOURCE LINES inside one crux. Neither bounds the
# VERDICT: that costs one hash per symbol (105 ms for the 443 symbols of this
# repo) and is computed for EVERY row rendered, `--limit 0` included. A freshness
# answer covering the first 20 of 443 symbols would be a survey, not a check.
SOURCE_MAX_ROWS = 20
DEFAULT_SOURCE_LINES = 8
# The HARD ceiling on `--source-lines`, and the reason there is one: this bound
# is what keeps the bytes printed into an agent context finite. `crux()` treats
# `limit <= 0` as "no choice to make" and returns the body WHOLE, so
# `--source-lines 0` is NOT « unlimited » -- it is clamped to 1 at the CLI, and
# anything above the cap is clamped down to it. Only the CLI clamps; `crux()`
# stays a pure function of its arguments.
SOURCE_LINES_CAP = 200
# Signature lines kept before the carriers: up to the first line ending in `:` or
# `{`, and never more than this many.
SIGNATURE_CAP = 3
FRESH, DRIFTED, UNKNOWN, MISSING = "FRESH", "DRIFTED", "UNKNOWN", "MISSING"

# --- overlay bounds and vocabulary (T-00000378) ------------------------------
# How many CHANGED FILES one query may re-extract. Files, not symbols: the cost
# is one read + one parse per file, and the truncation is announced WITH the
# names it left out, so a bounded answer never reads as a complete one.
REFRESH_BUDGET = 40
# What the truncation line and the `refresh` payload will ENUMERATE before they
# switch to a count. An unbounded list of 400 paths in an agent's context is the
# same defect as no bound at all.
REFRESH_NAMES_MAX = 20
# `# HORS STORE` is bounded for the same reason -- a first rebuild after a big
# merge can find hundreds.
NEW_SYMBOLS_MAX = 20
# An interpolated value that comes from OUTSIDE the tool -- a store's generation
# column (machine state another kit version may have written), an environment
# variable three layers up -- is not ours to
# trust for length. Cap it before it reaches a message, marking any cut with `…`.
VALUE_BOUND = 64
NO_REFRESH_ENV = "AGENTS_INDEX_NO_REFRESH"
KINDS_ENV = "ABK_INDEX_KINDS"  # the builder's own override, mirrored
# The per-row overlay statuses. CLOSED, because `--json` publishes the string.
ST_NOT_REFRESHED = "not-refreshed"   # the row's file was not in the changed set
ST_UNCHANGED = "unchanged"
ST_MOVED = "moved"
ST_DRIFTED = "drifted"
ST_MOVED_DRIFTED = "moved+drifted"
ST_GONE = "gone"
ST_AMBIGUOUS = "ambiguous"
# A file suffix one of the stdlib extractors understands WITHOUT ctags. Used to
# decide COVERAGE, never to decide extraction: a file nothing could parse is
# reported NOT COVERED and its symbols keep the store's bounds -- they are never
# called GONE, which is the difference between "I did not look" and "it is not
# there" (§8 piège 3 of the plan, and the whole reason `_parse_rows`'s silent
# skip is a named trap).
STDLIB_EXT = bi.PY_EXT | bi.JS_EXT | bi.CSS_EXT
# Same shape the builder validates its own anchor with, and for the same reason:
# the generation reaches `git` as a positional argument.
HEX_ANCHOR_RE = re.compile(r"[0-9a-fA-F]{4,40}")
# The crux heuristic is PURE, DETERMINISTIC and 0-LLM: control flow and state,
# in the body's own order. Deliberately language-agnostic and deliberately
# APPROXIMATE -- it is a reading aid, never an authority on what the code does.
CARRIER_RE = re.compile(
    r"^\s*(return|raise|yield|assert|if|elif|else|while|for|with|match|case|"
    r"switch|break|continue|throw|panic|catch|except|finally)\b")
ASSIGN_RE = re.compile(r"^\s*[A-Za-z_$][\w$.\[\]'\"]*\s*(?::[^=]*)?[-+*/|&^%]?=(?!=)")


# ------------------------------------------------------------------- freshness
def files_generation(root: Path) -> str | None:
    """The `built @ <sha>` stamp of `SYMBOLS.md` -- the index FILES' generation.

    Read with the builder's own extractor, off the identity source, which is the
    exact generation `build_index.py --stale-check` compares the DB against.
    """
    return bi._generation(bi._read(bi.index_dir(root) / bi.MAIN_NAME))


def staleness(root: Path) -> tuple[str, str] | None:
    """`(db_generation, files_generation)` when the store is behind, else None.

    Delegates to `migrate_index_to_db.db_generation_behind()`: the comparison is
    owned there and nobody here reads `meta` by hand. Its two silences are kept --
    a DB with no `built_at_sha`, or files with no stamp, yield NO verdict rather
    than an invented one.
    """
    return mig.db_generation_behind(root, files_generation(root))


def stale_lines(behind: tuple[str, str]) -> list[str]:
    """The banner, in the one shape every subcommand prints it."""
    db_gen, file_gen = behind
    return [
        f"{WARN} DB STALE -- index.db was built from index generation "
        f"{db_gen or 'unknown'}, the index files are stamped {file_gen}.",
        f"{WARN} Symbols below may belong to another generation. Fix: {RESYNC_CMD}",
        f"{WARN} (advisory in v1 -- the index FILES remain the authority; "
        f"--strict refuses instead of warning)",
    ]


def check_freshness(root: Path, strict: bool, json_mode: bool) -> tuple[str, str] | None:
    """Emit the staleness banner, or refuse under `--strict`. Returns the verdict.

    In text mode the banner goes to the HEAD of stdout, where the agent reading
    the answer cannot miss it. In `--json` mode it goes to stderr AND into the
    payload's `stale` key: a warning printed into stdout would make the document
    unparseable, and an unparseable answer is how a warning gets stripped.
    """
    behind = staleness(root)
    if behind is None:
        return None
    if strict:
        raise StaleRefusal(
            f"--strict on a STALE store: index.db was built from generation "
            f"{behind[0] or 'unknown'}, the index files are stamped {behind[1]}. "
            f"Refusing to answer from another generation -- run {RESYNC_CMD} (a "
            f"machine store: nothing to commit), or drop --strict to get the answer "
            f"with a warning.")
    stream = sys.stderr if json_mode else sys.stdout
    for line in stale_lines(behind):
        print(line, file=stream)
    return behind


# ----------------------------------------------------------------- connections
def require_db(root: Path) -> Path:
    """The store's path, or a named refusal. Tests existence BEFORE connecting."""
    target = mig.db_path(root)
    if not target.exists():
        raise Refusal(
            f"{target} does not exist -- this project has no SQLite index store "
            f"yet. Create it with `{APPLY_CMD}` (nothing was created just now: a "
            f"read-only tool must never leave a 0-byte database behind), or fall "
            f"back to grepping .agents/state/index/SYMBOLS*.md.")
    return target


def connect_ro(root: Path) -> sqlite3.Connection:
    """A read-only connection that CANNOT create the file (`mode=ro` URI)."""
    target = require_db(root)
    conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw(root: Path) -> sqlite3.Connection:
    """A writable connection on an EXISTING store -- `annotate`/`retire`/`compact`."""
    return mig.connect(require_db(root))


def has_fts(conn: sqlite3.Connection) -> bool:
    return mig._table_exists(conn, "symbols_fts")


# ---------------------------------------------------------------------- reading
@dataclass
class Row:
    """One symbol as the query returns it -- a dataclass across the boundary."""

    id: int
    path: str | None
    name: str
    kind: str | None
    start: int | None
    end: int | None
    deleted: bool
    purpose: str | None
    # v3. NOT in `as_json()` on purpose: the raw hash answers no question an agent
    # asks. What travels is the VERDICT it produces, under the `source` key.
    body_sha: str | None = None
    # v3 overlay (T-00000378). `start`/`end` above are OVERWRITTEN with the tree's
    # bounds when the overlay repairs them, and the store's originals move in
    # here: the caller that wanted a location gets the usable one by default, and
    # the caller auditing the store can still see what it held.
    overlay: dict[str, Any] | None = None

    def location(self) -> str:
        if not self.path:
            return "DELETED" if self.deleted else "?"
        if self.start is None:
            return self.path
        if self.end is None or self.end == self.start:
            return f"{self.path}:{self.start}"
        return f"{self.path}:{self.start}-{self.end}"

    def as_json(self) -> dict[str, Any]:
        out = {"sym_id": bi.sid(self.id), "id": self.id, "kind": self.kind,
               "path": self.path, "start": self.start, "end": self.end,
               "name": self.name, "purpose": self.purpose, "deleted": self.deleted}
        if self.overlay is not None:
            # ADDITIVE, and only when the overlay actually ran: an existing
            # consumer sees the same keys, of the same types, that it saw before.
            out["overlay"] = dict(self.overlay)
        return out


@dataclass
class Query:
    """The filters, as parsed. `None` everywhere = an unfiltered, bounded listing."""

    name: str | None = None
    purpose: str | None = None
    module: str | None = None
    kind: str | None = None
    file: str | None = None
    callers: int | None = None
    callees: int | None = None
    include_deleted: bool = False
    no_fts: bool = False
    limit: int = DEFAULT_LIMIT


@dataclass
class Result:
    rows: list[Row] = field(default_factory=list)
    total: int = 0
    engine: str = "none"
    notes: list[str] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return self.total > len(self.rows)


SELECT_SQL = (
    'SELECT s.id AS id, s.path AS path, s.name AS name, s.kind AS kind,'
    ' s.start AS start, s."end" AS end, s.deleted AS deleted,'
    ' {body} AS body_sha,'
    ' a.purpose AS purpose'
    ' FROM symbols s'
    " LEFT JOIN annotations a ON a.scope = 'symbol' AND a.key = CAST(s.id AS TEXT)")


def select_sql(conn: sqlite3.Connection) -> str:
    """`SELECT_SQL` with the body column resolved for THIS store's schema.

    `body_sha` arrives at schema v3. A project whose machine store is still at
    v2 must keep getting answers -- with `UNKNOWN` body verdicts -- instead of an
    OperationalError on every query, which is the same guard, for the same
    reason, as `migrate_index_to_db._fetch_symbols`.
    """
    has_body = "body_sha" in mig._symbols_columns(conn)
    return SELECT_SQL.format(body="s.body_sha" if has_body else "NULL")


def parse_sym_id(raw: str) -> int:
    """`SYM-042`, `042` and `42` all mean 42. Anything else is a named refusal."""
    m = re.fullmatch(r"(?:SYM-)?0*(\d+)", raw.strip(), re.IGNORECASE)
    if not m:
        raise Refusal(f"{raw!r} is not a SYM-ID (expected SYM-042, 042 or 42)")
    return int(m.group(1))


def set_display_width(conn: sqlite3.Connection) -> None:
    """Render ids at the store's own width, with the BUILDER's formatter.

    Fixed width is what makes `grep SYM-102` safe in the files (at 3 digits it
    would also match SYM-1020...SYM-1029), so a CLI that printed a narrower id
    would hand the agent a grep that silently matches ten other symbols.
    """
    row = conn.execute("SELECT MAX(id) AS top FROM symbols").fetchone()
    bi.set_id_width((row["top"] if row and row["top"] else 1))


def fts_ids(conn: sqlite3.Connection, column: str, pattern: str) -> set[int] | None:
    """Prefix-match `pattern` in one FTS5 column. None = FTS could not serve it."""
    if not FTS_SAFE_RE.fullmatch(pattern) or not has_fts(conn):
        return None
    try:
        rows = conn.execute(
            "SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ?",
            (f"{column} : {pattern}*",)).fetchall()
    except sqlite3.OperationalError:
        return None  # a malformed MATCH degrades to LIKE, it never crashes a query
    return {int(r["rowid"]) for r in rows}


def text_filter(conn: sqlite3.Connection, column: str, pattern: str, q: Query,
                result: Result) -> set[int] | None:
    """Ids from FTS5, or None meaning "the caller must add the LIKE clause".

    THE ZERO-ROW RETRY IS THE POINT. FTS5 matches whole TOKENS with a prefix, so
    `build*` does not match `rebuild_fts` -- while an agent typing `--name build`
    plainly means a substring. An empty FTS answer would read as "no such symbol",
    which is the precise failure this whole CLI exists to remove, so an empty
    result falls back to LIKE and SAYS it did. Two engines are acceptable; a
    silent one is not.
    """
    if q.no_fts:
        return None
    if q.include_deleted:
        # symbols_fts holds LIVE rows only (tombstones are data, not something to
        # search); serving --include-deleted from it would drop them in silence.
        result.notes.append("symbols_fts holds live rows only -- --include-deleted "
                            f"forced the LIKE fallback for --{column}")
        return None
    ids = fts_ids(conn, column, pattern)
    if ids is None:
        return None
    if not ids:
        result.notes.append(
            f"fts5 matched 0 rows on the token prefix '{pattern}*' in {column} "
            f"-- retried with the LIKE substring fallback")
        return None
    return ids


def edge_ids(conn: sqlite3.Connection, sym_id: int, direction: str) -> set[int]:
    """Callers (`dst_id = id`) or callees (`src_id = id`) of one symbol.

    The relation the shards cannot express: the files store forward edges only and
    say so in their own header. A SYM-ID with no row at all is a false premise, so
    it is refused rather than answered with an empty set.
    """
    if conn.execute("SELECT 1 FROM symbols WHERE id = ?", (sym_id,)).fetchone() is None:
        raise Refusal(f"{bi.sid(sym_id)} has no row in `symbols` -- nothing to trace. "
                      f"Check the id against .agents/state/index/SYMBOLS.md (or the "
                      f"store may predate it: {RESYNC_CMD}).")
    if direction == "callers":
        rows = conn.execute("SELECT src_id AS other FROM edges WHERE dst_id = ?",
                            (sym_id,)).fetchall()
    else:
        rows = conn.execute("SELECT dst_id AS other FROM edges WHERE src_id = ?",
                            (sym_id,)).fetchall()
    return {int(r["other"]) for r in rows}


def module_ids(conn: sqlite3.Connection, module: str) -> set[int]:
    """Ids whose module is `module`, resolved with the BUILDER's `module_of()`.

    The Modules table of CODEBASE_INDEX.md is keyed by `module_of(path)` (`alpha`
    for `src/alpha/one.py`), so a naive path prefix would answer nothing for the
    very names the index displays. A path prefix is accepted too (`.agents/bin`),
    because that is the other spelling humans and agents actually type.
    """
    wanted = module.replace("\\", "/").rstrip("/")
    if wanted.endswith("/*"):
        wanted = wanted[:-2]
    wanted = wanted.rstrip("*").rstrip("/")
    out: set[int] = set()
    for row in conn.execute("SELECT id, path FROM symbols WHERE path IS NOT NULL"):
        path = str(row["path"]).replace("\\", "/")
        if bi.module_of(path) == wanted or path == wanted or path.startswith(wanted + "/"):
            out.add(int(row["id"]))
    return out


def run_query(conn: sqlite3.Connection, q: Query) -> Result:
    """Every filter, one SELECT, then the bound. Reports the engine that served.

    The row slice happens AFTER the full matching set is known, on purpose: the
    total is what makes the truncation notice honest, and a `LIMIT` in SQL would
    hide the very number the agent needs to decide whether to narrow.
    """
    result = Result()
    clauses: list[str] = []
    params: list[Any] = []
    restrict: set[int] | None = None

    def narrow(ids: set[int]) -> None:
        nonlocal restrict
        restrict = ids if restrict is None else (restrict & ids)

    if not q.include_deleted:
        clauses.append("s.deleted = 0")

    def engine(used: str) -> None:
        result.engine = used if result.engine in ("none", used) else "mixed"

    if q.name:
        ids = text_filter(conn, "name", q.name, q, result)
        if ids is None:
            engine("like")
            clauses.append("s.name LIKE ? ESCAPE '\\'")
            params.append(like_pattern(q.name))
        else:
            engine("fts5")
            narrow(ids)

    if q.purpose:
        ids = text_filter(conn, "purpose", q.purpose, q, result)
        if ids is None:
            engine("like")
            clauses.append("a.purpose LIKE ? ESCAPE '\\'")
            params.append(like_pattern(q.purpose))
        else:
            engine("fts5")
            narrow(ids)

    if q.kind:
        clauses.append("LOWER(s.kind) = LOWER(?)")
        params.append(q.kind)

    if q.file:
        wanted = q.file.replace("\\", "/")
        clauses.append("(s.path = ? OR s.path LIKE ? ESCAPE '\\')")
        params += [wanted, "%/" + escape_like(wanted)]

    if q.callers is not None:
        narrow(edge_ids(conn, q.callers, "callers"))
        result.notes.append(EDGES_CAVEAT)
    if q.callees is not None:
        narrow(edge_ids(conn, q.callees, "callees"))
        if EDGES_CAVEAT not in result.notes:
            result.notes.append(EDGES_CAVEAT)

    if q.module:
        narrow(module_ids(conn, q.module))

    if restrict is not None and not restrict:
        return result  # an empty restriction is a certain empty answer

    sql = select_sql(conn)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY s.id"

    rows: list[Row] = []
    for raw in conn.execute(sql, params):
        if restrict is not None and int(raw["id"]) not in restrict:
            continue
        rows.append(Row(id=int(raw["id"]), path=raw["path"], name=raw["name"],
                        kind=raw["kind"], start=raw["start"], end=raw["end"],
                        deleted=bool(raw["deleted"]), purpose=raw["purpose"],
                        body_sha=raw["body_sha"]))
    result.total = len(rows)
    result.rows = rows if q.limit <= 0 else rows[:q.limit]
    return result


def escape_like(raw: str) -> str:
    """Escape the LIKE metacharacters so a literal `_` cannot match any char."""
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(raw: str) -> str:
    """A user pattern as LIKE sees it: `*` is the wildcard, everything else literal.

    Substring by default (`build` -> `%build%`), because that is what an agent
    means when it types a fragment. `*` anywhere switches to an explicit shape
    (`build_*` -> `build\\_%`), so a caller can pin a prefix when it needs to.
    """
    if "*" in raw:
        return escape_like(raw).replace("*", "%")
    return "%" + escape_like(raw) + "%"


# ------------------------------------------------------------------- source
@dataclass
class Source:
    """One symbol's body verdict, plus the crux read from the WORKING TREE.

    `generation` is the STORE's, and it is carried rather than formatted in so
    the machine shape can keep the two apart: `--json` must be able to say
    `verdict == "FRESH"` without a caller parsing a suffix off it.
    """

    verdict: str
    generation: str | None = None
    lines: list[str] = field(default_factory=list)
    dropped: int = 0

    def as_json(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "generation": self.generation,
                "lines": list(self.lines), "dropped": self.dropped}

    def label(self) -> str:
        """`FRESH @ <gen>` / `DRIFTED @ <gen>`; the two unknowns name nothing.

        A generation on `UNKNOWN` or `MISSING` would suggest a comparison was
        made against it. None was.
        """
        if self.verdict in (FRESH, DRIFTED) and self.generation:
            return f"{self.verdict} @ {self.generation}"
        return self.verdict


def crux(body: Sequence[str], limit: int) -> tuple[list[str], int]:
    """`(kept lines, dropped count)` -- pure, deterministic, 0-LLM.

    A body of `limit` lines or fewer is shown WHOLE: there is nothing to choose.
    Beyond that: the signature (up to and including the first line ending in `:`
    or `{`, capped at `SIGNATURE_CAP`), then the carrier lines IN THE BODY'S OWN
    ORDER -- control flow, exits, and assignments to state. Never re-ordered, so
    the crux reads like the code and not like a ranking.
    """
    lines = [line.rstrip() for line in body]
    if limit <= 0 or len(lines) <= limit:
        return lines, 0

    kept: list[int] = []
    for i in range(min(SIGNATURE_CAP, len(lines))):
        kept.append(i)
        if lines[i].endswith((":", "{")):
            break
    for i, line in enumerate(lines):
        if len(kept) >= limit:
            break
        if i in kept or not line.strip():
            continue
        if CARRIER_RE.match(line) or ASSIGN_RE.match(line):
            kept.append(i)
    kept = sorted(set(kept))[:limit]
    return [lines[i] for i in kept], len(lines) - len(kept)


def tree_lines(root: Path, relpath: str, cache: dict) -> list[str] | None:
    """The working tree's lines for `relpath`, read ONCE per file, or None.

    THE TREE, NOT THE STORE. The whole point of `--source` is to compare what is
    on disk NOW against what the store recorded, so reading anything else would
    make every verdict `FRESH` by construction.

    CONFINED TO `root`, because `relpath` comes from the store's `path` column --
    a COMMITTED BINARY, forgeable by whoever can land a row. This is the ONLY
    place a store path is dereferenced on disk, so the check belongs here and
    nowhere else: an absolute path or one climbing out with `../` would print an
    arbitrary file into the agent's context. `resolve()` closes the symlink route
    too. An escape is cached as `None` -- the same value an unreadable file gets,
    which `source_for` already names `MISSING`. No new verdict, no new silence.
    """
    if relpath not in cache:
        try:
            target = (root / relpath).resolve()
            if Path(relpath).is_absolute() or not target.is_relative_to(root.resolve()):
                raise ValueError(f"store path escapes the root: {relpath!r}")
            text = target.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            cache[relpath] = None
        else:
            cache[relpath] = text.splitlines()
    return cache[relpath]


def source_for(root: Path, row: Row, generation: str | None, cache: dict,
               with_crux: bool, source_lines: int) -> Source:
    """The four verdicts, in the order that makes each of them mean something.

    `MISSING` comes FIRST and is NAMED -- an unreadable file or a range past EOF
    must never degrade into an empty crux that reads as "this symbol is short".
    `UNKNOWN` then covers the store that carries no hash (pre-v3, or not resynced
    since the build), which is a fact about the STORE, not about the code.
    """
    if not row.path or row.start is None or row.end is None:
        return Source(MISSING, generation)
    lines = tree_lines(root, row.path, cache)
    if lines is None:
        return Source(MISSING, generation)
    actual = bi.body_hash(lines, row.start, row.end)
    if actual is None:  # the range no longer fits the file
        return Source(MISSING, generation)
    if not row.body_sha:
        verdict = UNKNOWN
    else:
        verdict = FRESH if actual == row.body_sha else DRIFTED
    if not with_crux:
        return Source(verdict, generation)
    kept, dropped = crux(lines[row.start - 1:row.end], source_lines)
    return Source(verdict, generation, kept, dropped)


def attach_sources(root: Path, result: Result, generation: str | None,
                   source_lines: int) -> list[Source]:
    """A verdict for EVERY rendered row; a crux TEXT for the first N of them."""
    cache: dict = {}
    return [source_for(root, row, generation, cache, i < SOURCE_MAX_ROWS,
                       source_lines)
            for i, row in enumerate(result.rows)]


def source_truncation_line(shown: int) -> str:
    return (f"{WARN} SOURCE TRUNCATED — crux calculé pour {SOURCE_MAX_ROWS} des "
            f"{shown} symboles")


def source_lag_line(behind: tuple[str, str]) -> str:
    """Said out loud whenever the store is behind, because it changes the READING
    of a DRIFTED: the tree may be perfectly in step with the index files and
    still disagree with a store that has not been resynced since."""
    db_gen, file_gen = behind
    return (f"{WARN} le verdict de corps compare l'arbre au STORE (génération "
            f"{db_gen or 'inconnue'}), pas à l'index (génération {file_gen}) — un "
            f"DRIFTED peut venir du retard du store")


# ---------------------------------------------------------------------- overlay
# T-00000378. Everything below repairs the ANSWER; nothing below writes a byte.
NEW_IN_FILES = "hors store — lancer --resync"
NEW_NOWHERE = "pas encore de SYM-ID — reconstruis l'index"
NEW_AMBIGUOUS = "AMBIGU (décalage ordinal) — aucun SYM-ID rendu"


def refresh_disabled_by_env(environ: dict | None = None) -> str | None:
    """The env value that disarms the overlay, or None. ANY value but `` and `0`.

    Returned rather than tested, because the caller must be able to NAME it: an
    overlay disarmed by an environment variable three layers up is exactly the
    kind of silent disarming that reads as "nothing has changed".
    """
    raw = (os.environ if environ is None else environ).get(NO_REFRESH_ENV)
    if raw is None:
        return None
    return None if raw.strip() in ("", "0") else raw


def overlay_availability(root: Path) -> tuple[str | None, str | None]:
    """`(anchor, None)` when the overlay can run, else `(None, the CAUSE)`.

    ↯ C3 — THE ANCHOR IS THE STORE'S GENERATION, AND NOTHING ELSE. The rows being
    repaired come out of `index.db`, so the question is "does this interval still
    describe my tree?" and its starting point is `mig.read_db_generation` — the
    `meta.built_at_sha` that `write_state` copied from the FILES' `built @`, hence
    a sha `git diff` accepts.

    ↯ C15 — THERE IS NO FALLBACK ON `files_generation`. An earlier revision reached
    for it "if the base carries none": that is the two-generation comparison the
    sentence next door forbids, and it fires at the moment least is known. No
    generation in the store ⇒ overlay UNAVAILABLE, cause named, same shape as the
    other three guards.

    The other three REPRODUCE the guards `build_index._build` already applies
    before it trusts an anchor, because the failure modes are the builder's:
    a non-hexadecimal anchor would reach `git` as a flag; an anchor `cat-file -e`
    cannot resolve makes `changed_source_files` return a PARTIAL set in silence;
    and a published `dirscope` that disagrees with this machine's means the file
    set itself was computed under other rules.

    ↯ C23 — THE `dirscope` GUARD IS ADVISORY, AND THAT IS WRITTEN DOWN. The stamp
    lives in the FILES' header (`published_dirscope` reads `_header_line`); the
    STORE carries none. So this compares the scope the FILES published to the
    scope this machine computes — it catches a machine whose exclusion rules
    moved, NOT a disagreement of scope between store and files. Declared here
    rather than hidden behind a guard that would look stronger than it is.
    """
    anchor = mig.read_db_generation(root)
    if not anchor:
        return None, (f"index.db carries no `{mig.META_BUILT_AT_SHA}` — there is no "
                      f"generation to diff the working tree against (a pre-v1 store, "
                      f"or one written by hand). Fix: {RESYNC_CMD}")
    if not HEX_ANCHOR_RE.fullmatch(anchor):
        return None, (f"the store's generation {_bounded_value(anchor)!r} is not a "
                      f"hexadecimal sha — refusing to hand it to git as an argument")
    if bi.git(root, "cat-file", "-e", anchor) is None:
        return None, (f"git cannot resolve the store's generation {anchor} here (no "
                      f"git repository, a shallow clone, or a rewritten history) — "
                      f"the changed-file set would be PARTIAL and silently so")
    header_line = bi._header_line(bi._read(bi.index_dir(root) / bi.MAIN_NAME))
    if bi.published_dirscope(header_line) != bi.scope_fingerprint(bi.host_skip_dirs(root)):
        return None, ("the index files were published under a different directory "
                      "scope than this machine computes — rebuild the index "
                      "(python .agents/bin/build_index.py) before trusting a diff")
    return anchor, None


@dataclass
class Refresh:
    """What the overlay did, in the one shape text and `--json` both render from."""

    enabled: bool = False
    reason: str | None = None
    anchor: str | None = None
    changed: int = 0
    parsed: int = 0
    left_out: list[str] = field(default_factory=list)   # the budget bit here
    uncovered: list[str] = field(default_factory=list)  # nothing could parse these
    new_symbols: list[dict] = field(default_factory=list)
    new_total: int = 0
    bounds: dict[int, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        # The two lists are BOUNDED and their totals travel beside them: an
        # enumeration under a universal title is a delayed lie, so where the list
        # cannot be complete the count says how incomplete it is.
        return {"enabled": self.enabled, "reason": self.reason,
                "anchor": self.anchor, "changed_files": self.changed,
                "parsed": self.parsed,
                "truncated": self.left_out[:REFRESH_NAMES_MAX],
                "truncated_total": len(self.left_out),
                "uncovered": self.uncovered[:REFRESH_NAMES_MAX],
                "uncovered_total": len(self.uncovered),
                "new_symbols": [dict(n) for n in self.new_symbols],
                "new_symbols_total": self.new_total}


def baseline_live_rows(conn: sqlite3.Connection, paths: set[str]) -> list[dict]:
    """Every LIVE row of `paths`, as the store holds it.

    ↯ C24 — `deleted = 0`, AND THAT IS THE WHOLE POINT. `symbols` keeps its
    tombstones forever while the identity index is partial (`WHERE deleted = 0`),
    so counting tombstones would inflate every purged group's cardinal and turn
    it into a phantom `AMBIGU` on every query. The re-extraction has no tombstones
    to offer, so the two sides must count the same population or the guard fires
    on nothing.

    The column guard is `_symbols_columns`, the same one `select_sql` applies: a
    store still at schema v2 must keep answering, with no `body_sha` to compare.
    """
    if not paths:
        return []
    has_body = "body_sha" in mig._symbols_columns(conn)
    sql = ('SELECT s.id AS id, s.path AS path, s.name AS name, s.kind AS kind,'
           ' s.start AS start, s."end" AS end, ' +
           ("s.body_sha" if has_body else "NULL") + ' AS body_sha'
           ' FROM symbols s WHERE s.deleted = 0 AND s.path IS NOT NULL')
    return [dict(r) for r in conn.execute(sql)
            if str(r["path"]).replace("\\", "/") in paths]


def build_overlay(root: Path, conn: sqlite3.Connection, budget: int,
                  edges_only: bool = False) -> Refresh:
    """Diff the tree against the store's generation and repair what moved.

    ↯ C5 — THE PAIRING RULE IS PER HOMONYM GROUP, NOT PER FILE. `bi.identity_keys`
    numbers the homonyms of one `(path, name, kind)` group by increasing start
    line, with the store's own convention. Adding or removing one homonym shifts
    the ordinal of every later one, so a naive re-pairing would hand a NEW body to
    an OLD SYM-ID, silently, on every query. The guard: a group whose CARDINAL
    differs between baseline and re-extraction is NOT paired — its rows come out
    `AMBIGU (décalage ordinal)` with the cause, while every other group of the
    same file is repaired normally. A rule at FILE granularity would cancel the
    overlay the moment a function is added, which is the case the overlay exists
    for; the ambiguity is strictly local to the group that changed size.

    ONE SIDE EMPTY IS NOT AMBIGUOUS, and this reading is what makes the plan's own
    four markers reachable. Cardinal 0 → n has no pairing to get wrong: every
    fresh row is NEW (`# HORS STORE`). Cardinal n → 0 likewise: every baseline row
    is `[GONE dans l'arbre]`. Only a group non-empty on BOTH sides with differing
    cardinals can mis-pair, and only that one is refused.

    `edges_only` covers `--callers`/`--callees`/`--purpose` (§5.7): those answers
    derive from `edges` and from annotations keyed on a SYM-ID, neither of which a
    read-side re-extraction can recompute. Positions are still repaired; no new
    symbol is ever added under those flags.
    """
    anchor, reason = overlay_availability(root)
    if anchor is None:
        return Refresh(enabled=False, reason=reason)

    host_skip = bi.host_skip_dirs(root)
    # QUATRIÈME GARDE, de la même famille que les trois voisines (T-00000575).
    # La docstring ci-dessus annonçait déjà le risque — « un ancre que
    # `cat-file -e` ne résout pas fait rendre à `changed_source_files` un
    # ensemble PARTIEL en silence » — mais rien ne l'attrapait, et le cas réel
    # est plus large que l'ancre : un `git diff` qui ÉCHOUE (clone partiel hors
    # ligne, objet absent) rendait un ensemble VIDE, donc un overlay qui
    # n'ajoutait rien tout en se déclarant actif. Un overlay muet se lit « rien
    # n'a changé » — exactement le mensonge que cette surface existe pour éviter.
    brut = bi.changed_source_files(root, anchor, host_skip)
    if brut is None:
        return Refresh(enabled=False, reason=(
            f"git diff {anchor}..HEAD a échoué — l'ensemble des fichiers changés "
            "serait PARTIEL sans qu'on puisse le dire : overlay désarmé"))
    changed = [f.replace("\\", "/") for f in brut]
    parsed = changed if budget <= 0 else changed[:budget]
    ref = Refresh(enabled=True, anchor=anchor, changed=len(changed),
                  parsed=len(parsed),
                  left_out=([] if budget <= 0 else changed[budget:]))
    if not parsed:
        return ref

    raw_kinds = os.environ.get(KINDS_ENV)
    kinds = ({k.strip() for k in raw_kinds.split(",") if k.strip()}
             if raw_kinds else bi.CTAGS_KINDS)
    extracted = bi.extract_scope(root, parsed, bi.ctags_binary(), kinds)

    # THREE BUCKETS, and the third is the named trap. A file absent from the map
    # and absent from disk was DELETED — its symbols really are gone. A file that
    # parsed is covered. Everything else — a suffix no extractor knows, or a file
    # that would not read — is NOT COVERED: its symbols keep the store's bounds
    # and are never called GONE, because "I could not look" is not "it is not
    # there".
    cache: dict = {}
    covered, gone_files, uncovered = set(), set(), []
    for rel in parsed:
        if rel not in extracted:
            if (root / rel).exists():
                uncovered.append(rel)
            else:
                gone_files.add(rel)
            continue
        lignes = tree_lines(root, rel, cache)
        if lignes is None:
            uncovered.append(rel)
        elif not extracted[rel] and bi.is_machine_written(rel, "\n".join(lignes)):
            # ÉCARTÉ PAR FORME : `[]` dit ici « on a REFUSÉ de regarder », pas
            # « j'ai regardé et il n'y a rien ». Sans cette branche, un bundle
            # PRÉSENT dans l'arbre sortait `[GONE dans l'arbre]` — mesuré par le
            # binôme sur T-00000609 : 800 lignes sur 800 marquées disparues, et
            # la liste des NON COUVERTS vide, donc l'overlay affirmait avoir
            # regardé. C'est le piège que le commentaire des TROIS SEAUX, plus
            # haut, dit ne jamais devoir se produire. Le défaut préexistait pour
            # le CSS, dont l'extracteur rend `[]` de la même façon ; la garde de
            # forme du JS l'aurait élargi à 2 051 lignes sur ce dépôt.
            uncovered.append(rel)
        elif Path(rel).suffix in STDLIB_EXT or extracted[rel]:
            covered.add(rel)
        else:
            uncovered.append(rel)
    ref.uncovered = sorted(uncovered)

    base = baseline_live_rows(conn, covered | gone_files)
    base_groups: dict[tuple, dict[int, dict]] = {}
    for key, row in zip(bi.identity_keys(
            [(r["path"].replace("\\", "/"), r["name"], r["kind"], r["start"], r["id"])
             for r in base]), base):
        base_groups.setdefault(key[:3], {})[key[3]] = row

    fresh_groups: dict[tuple, dict[int, dict]] = {}
    for rel in sorted(covered):
        rows = extracted.get(rel) or []
        # Per file, with the extraction POSITION as tiebreak — the convention
        # `reconcile` applies to freshly extracted rows, mirrored here so the two
        # numberings cannot drift apart.
        for key, ex in zip(bi.identity_keys(
                [(rel, ex["name"], ex["kind"], ex["start"], pos)
                 for pos, ex in enumerate(rows)]), rows):
            fresh_groups.setdefault(key[:3], {})[key[3]] = ex

    news: list[dict] = []
    for group in sorted(set(base_groups) | set(fresh_groups)):
        old = base_groups.get(group, {})   # ↯ C29 — `.get()`, never a KeyError
        new = fresh_groups.get(group, {})
        if old and new and len(old) != len(new):
            for row in old.values():
                ref.bounds[int(row["id"])] = _entry(ST_AMBIGUOUS, row)
            continue
        if old and not new:
            for row in old.values():
                ref.bounds[int(row["id"])] = _entry(ST_GONE, row)
            continue
        if new and not old:
            if not edges_only:
                news += [{"path": group[0], "name": group[1], "kind": group[2],
                          "ordinal": ordinal, "start": ex["start"], "end": ex["end"],
                          "sym_id": None, "note": NEW_NOWHERE}
                         for ordinal, ex in sorted(new.items())]
            continue
        for ordinal, row in old.items():
            ex = new.get(ordinal)
            if ex is None:  # equal cardinals make this unreachable; trust nothing
                continue
            ref.bounds[int(row["id"])] = _paired_entry(root, group[0], row, ex, cache)

    if news:
        _name_the_new(root, news, fresh_groups)
        ref.new_total = len(news)
        ref.new_symbols = news[:NEW_SYMBOLS_MAX]
    return ref


def _entry(status: str, row: dict) -> dict:
    """A verdict that carries NO new bounds — the store's are kept, and said so."""
    return {"status": status, "shift": 0,
            "baseline": {"start": row["start"], "end": row["end"]}}


def _paired_entry(root: Path, rel: str, row: dict, ex: dict, cache: dict) -> dict:
    """A paired symbol's repaired bounds, plus whether its BODY moved on too.

    `moved` and `drifted` are independent and both are reported: a symbol pushed
    down by an insertion above it is `moved` and perfectly intact, while one
    edited in place is `drifted` and never moved. The hash is `bi.body_hash` over
    the REFRESHED range, so a pure move stops reading as a change — which is the
    single most common false alarm the overlay exists to remove.
    """
    lines = tree_lines(root, rel, cache)
    actual = bi.body_hash(lines, ex["start"], ex["end"]) if lines is not None else None
    moved = (ex["start"] != row["start"]) or (ex["end"] != row["end"])
    drifted = bool(row["body_sha"]) and actual is not None and actual != row["body_sha"]
    status = (ST_MOVED_DRIFTED if moved and drifted else ST_MOVED if moved
              else ST_DRIFTED if drifted else ST_UNCHANGED)
    entry = _entry(status, row)
    entry["shift"] = int(ex["start"]) - int(row["start"])
    entry["start"], entry["end"] = ex["start"], ex["end"]
    return entry


def _name_the_new(root: Path, news: list[dict], fresh_groups: dict) -> None:
    """§2C — a symbol the STORE does not know may already have an id in the FILES.

    The files are the authority this CLI's own docstring names ("advisory in v1 —
    the index FILES remain the authority"), so a symbol indexed since the last
    `--resync` gets its real `SYM-NNN` and a `--resync` to run, instead of being
    announced as having no identifier at all.

    ↯ C17 — THE PAIRING KEY IS WRITTEN DOWN, AND SO IS ITS GUARD. The lookup is on
    `(path, name, kind, ordinal)` computed by `bi.identity_keys`, the store's own
    convention, never a match by name — a second identity source without a stated
    key is somebody else's SYM-ID served with confidence. And the §5.4 cardinal
    guard applies to THIS reading too (↯ C24): a group whose size differs between
    `SYMBOLS.md` and the re-extraction yields NO id, it yields `AMBIGU`. Without
    the extension the guard would protect the pairing against the store and leave
    the pairing against the files with no net at all.

    A store AHEAD of the files is the named edge case: the lookup simply misses
    and the symbol degrades to "no SYM-ID yet" — the most cautious message, never
    an invented id.
    """
    by_key, _by_id, _max_id = bi.load_existing(root)
    file_groups: dict[tuple, set[int]] = {}
    for key in by_key:
        path = (key[0] or "").replace("\\", "/")
        file_groups.setdefault((path, key[1], key[2]), set()).add(key[3])
    for entry in news:
        group = (entry["path"], entry["name"], entry["kind"])
        ordinals = file_groups.get(group, set())
        if not ordinals:
            continue  # NEW_NOWHERE, already set
        if len(ordinals) != len(fresh_groups.get(group, {})):
            entry["note"] = NEW_AMBIGUOUS
            continue
        published = by_key.get((*group, entry["ordinal"]))
        if published is None:
            continue
        entry["sym_id"] = bi.sid(int(published["id"]))
        entry["note"] = NEW_IN_FILES


def apply_overlay(result: Result, ref: Refresh) -> None:
    """Move the repaired bounds ONTO the rows, keeping the store's as `baseline`.

    A row whose file was not in the changed set gets `not-refreshed` rather than
    nothing: the absence of a verdict and a verdict of "unchanged" are different
    facts, and only one of them is a measurement.
    """
    if not ref.enabled:
        return
    for row in result.rows:
        entry = ref.bounds.get(row.id)
        if entry is None:
            row.overlay = {"status": ST_NOT_REFRESHED, "shift": 0,
                           "baseline": {"start": row.start, "end": row.end}}
            continue
        row.overlay = {"status": entry["status"], "shift": entry["shift"],
                       "baseline": dict(entry["baseline"])}
        if "start" in entry:
            row.start, row.end = entry["start"], entry["end"]


def overlay_marker(overlay: dict | None) -> str:
    """The end-of-line marker for one row. Silent when there is nothing to say."""
    if not overlay:
        return ""
    status = overlay.get("status")
    if status == ST_GONE:
        return "  [GONE dans l'arbre]"
    if status == ST_AMBIGUOUS:
        return "  [AMBIGU décalage ordinal]"
    bits = []
    if status in (ST_MOVED, ST_MOVED_DRIFTED):
        bits.append(f"~moved({overlay.get('shift', 0):+d})")
    if status in (ST_DRIFTED, ST_MOVED_DRIFTED):
        bits.append("~drifted")
    return ("  " + " ".join(bits)) if bits else ""


def _bounded_value(value: str, limit: int = VALUE_BOUND) -> str:
    """Cap an UNTRUSTED interpolated value and MARK the cut with a trailing `…`.

    Anchors and env values reach the overlay's messages from outside the tool (a
    store column another kit version may have written, an environment variable
    three layers up), so a
    hostile 500-char value could drown the answer or push a warning off screen.
    """
    return value if len(value) <= limit else value[:limit] + "…"


def _bounded(names: Sequence[str]) -> str:
    """`a, b, c (+7 autres)` — a list that says how much of itself it is showing."""
    shown = list(names[:REFRESH_NAMES_MAX])
    rest = len(names) - len(shown)
    return ", ".join(shown) + (f" (+{rest} autres)" if rest > 0 else "")


def refresh_notes(ref: Refresh, disabled_by: str | None) -> list[str]:
    """Everything the overlay owes the reader — and it always owes SOMETHING.

    A quiet overlay reads as "nothing has changed" (L-00000136), so each of the
    three ways it can fail to answer prints its own line: disarmed by the flag,
    disarmed by the environment (with the variable NAMED — a disarming three
    layers up is the one nobody sees), or unavailable with its cause.
    """
    if disabled_by is not None:
        # The env value is UNTRUSTED and unbounded; give it its OWN bounded line
        # (value LAST, so a truncation ends it with a visible `…`) so a hostile
        # value cannot bloat the answer or push the store-bounds warning off the
        # reader's screen. The warning itself keeps its full wording.
        return ["overlay de fraîcheur DÉSACTIVÉ — les bornes ci-dessous sont "
                "celles du STORE, pas celles de l'arbre de travail",
                f"cause : {NO_REFRESH_ENV}={_bounded_value(disabled_by)}"]
    if not ref.enabled and ref.reason is None:
        return ["overlay de fraîcheur DÉSACTIVÉ par --no-refresh — les bornes "
                "ci-dessous sont celles du STORE, pas celles de l'arbre"]
    if not ref.enabled:
        return [f"{WARN} overlay de fraîcheur INDISPONIBLE — {ref.reason}"]
    out = [f"overlay de fraîcheur @ {ref.anchor} — {ref.changed} fichier(s) "
           f"changé(s), {ref.parsed} analysé(s)"]
    if ref.left_out:
        out.append(f"{WARN} REFRESH TRUNCATED — {ref.changed} fichier(s) changé(s), "
                   f"{ref.parsed} analysés ; non recouverts : "
                   f"{_bounded(ref.left_out)}")
    if ref.uncovered:
        out.append(f"{WARN} {len(ref.uncovered)} fichier(s) changé(s) sans "
                   f"extracteur — NON COUVERTS, jamais GONE : "
                   f"{_bounded(ref.uncovered)}")
    return out


def hors_store_lines(ref: Refresh) -> list[str]:
    """The `# HORS STORE` block — symbols the tree holds and the store does not.

    They are NEVER folded into `results[]`: a SYM-ID is not invented, and a
    `sym_id: null` row would be an id-shaped hole every consumer would have to
    learn about. §2C.
    """
    if not ref.new_symbols:
        return []
    out = [f"# HORS STORE — {ref.new_total} symbole(s) dans l'arbre, absent(s) du "
           f"store" + (f" (les {len(ref.new_symbols)} premiers)"
                       if ref.new_total > len(ref.new_symbols) else "")]
    for entry in ref.new_symbols:
        head = f"{entry['sym_id']} ({entry['note']})" if entry["sym_id"] else \
            f"({entry['note']})"
        out.append(f"  {entry['path']}:{entry['start']}-{entry['end']}  "
                   f"{entry['name']}  {entry['kind']}  {head}")
    return out


# -------------------------------------------------------------------- rendering
def truncate(text: str | None, width: int) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return text if len(text) <= width else text[:max(0, width - 3)].rstrip() + "..."


def render_rows(result: Result, width: int,
                sources: Sequence[Source] | None = None) -> list[str]:
    """One line per symbol, in the FILES' own field order plus the kind up front.

    `SYM-042  function  path:start-end  name  :: purpose` -- deliberately the
    grammar an agent already knows from `SYMBOLS.md`, two spaces as the separator
    so the line stays greppable and ASCII-safe on a cp1252 console.

    With `--source`, each row is FOLLOWED by its verdict and crux, indented and
    prefixed: the symbol line keeps its exact shape, so every grep and every
    reader written against it still works.
    """
    out = []
    for i, row in enumerate(result.rows):
        purpose = truncate(row.purpose, width)
        tail = f"  :: {purpose}" if purpose else ""
        # The overlay marker goes LAST, after the purpose: everything before it
        # keeps the exact grammar `SYMBOLS.md` uses, so the greps written against
        # that grammar still cut on the same fields.
        out.append(f"{bi.sid(row.id)}  {row.kind or '?'}  {row.location()}  "
                   f"{row.name}{'  [DELETED]' if row.deleted else ''}{tail}"
                   f"{overlay_marker(row.overlay)}")
        if sources is None:
            continue
        src = sources[i]
        out.append(f"    {src.label()}")
        out += [f"    | {line}" for line in src.lines]
        if src.dropped:
            out.append(f"    | … (+{src.dropped} lignes)")
    return out


def query_header(result: Result, q: Query) -> list[str]:
    engine = {"fts5": "fts5 (full text)", "like": "LIKE fallback",
              "mixed": "fts5 + LIKE", "none": "no text search"}[result.engine]
    shown = len(result.rows)
    lines = [f"# symbols.py query -- {result.total} match(es), showing {shown} "
             f"-- search: {engine}"]
    for note in result.notes:
        lines.append(f"# NOTE: {note}")
    return lines


def truncation_line(result: Result, q: Query) -> str:
    return (f"{WARN} TRUNCATED -- {len(result.rows)} of {result.total} matches shown "
            f"(--limit {q.limit}); raise --limit or narrow the query")


# --------------------------------------------------------------------- writing
def annotation_row(conn: sqlite3.Connection, scope: str, key: str) -> dict | None:
    row = conn.execute("SELECT purpose, role, owner FROM annotations"
                       " WHERE scope = ? AND key = ?", (scope, key)).fetchone()
    if row is None:
        return None
    return {"purpose": row["purpose"], "role": row["role"], "owner": row["owner"]}


def write_annotation(conn: sqlite3.Connection, scope: str, key: str,
                     values: dict[str, str | None]) -> None:
    """Upsert one authored annotation, then keep `symbols_fts` in step with it.

    ONE transaction for the three statements. `connect()` runs in true autocommit
    (`isolation_level=None`), so without the `with conn:` block a crash between
    the upsert and the FTS reinsert would leave the search index disagreeing with
    the authoritative table — a query would then answer from a stale purpose, or
    miss the symbol entirely, which is the one failure this CLI exists to remove.
    `compact` can rebuild the FTS index afterwards, but self-healing later is not
    a reason to be inconsistent in between.
    """
    with conn:
        conn.execute(
            "INSERT INTO annotations(scope, key, purpose, role, owner) VALUES(?, ?, ?, ?, ?)"
            " ON CONFLICT(scope, key) DO UPDATE SET purpose = excluded.purpose,"
            " role = excluded.role, owner = excluded.owner",
            (scope, key, values.get("purpose"), values.get("role"), values.get("owner")))
        if scope != "symbol" or not has_fts(conn):
            return
        sym = conn.execute('SELECT id, name, path, deleted FROM symbols WHERE id = ?',
                           (int(key),)).fetchone()
        if sym is None or sym["deleted"]:
            return
        conn.execute("DELETE FROM symbols_fts WHERE rowid = ?", (int(key),))
        conn.execute("INSERT INTO symbols_fts(rowid, name, path, purpose) VALUES(?, ?, ?, ?)",
                     (int(key), sym["name"], sym["path"], values.get("purpose") or ""))


def journal_state(root: Path, scope: str, key: str,
                  values: dict[str, str | None]) -> mig.State:
    """A one-annotation `State`, so the append goes through migrate's own writer."""
    return mig.State(root=root, generation=files_generation(root) or "",
                     annotations={(scope, key): dict(values)})


def append_retraction(root: Path, scope: str, key: str, fields: Sequence[str]) -> int:
    """Append ONE retraction line per retired field. The journal is never rewound.

    `migrate_index_to_db.append_log` cannot carry this: it skips `None` values by
    design (it publishes authored content), and a retraction IS the absence. The
    line it writes is the same record shape, so `mig.replay_log` folds it back to
    `None` and `--verify` keeps agreeing with the table; `"retired": true` is
    there for the human reading the journal, and is ignored by the replay.
    """
    log = mig.log_path(root)
    at_sha = files_generation(root) or ""
    lines = [json.dumps({"scope": scope, "key": key, "field": name, "value": None,
                         "retired": True, "at_sha": at_sha},
                        sort_keys=True, ensure_ascii=False) for name in fields]
    if not lines:
        return 0
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(lines)


#: The cell a human edits in the index FILES for each annotation field.
FILE_CELLS = {"purpose": "`:: purpose`", "role": "`Role`", "owner": "`Owner agent`"}


def files_override_note(root: Path, scope: str, key: str,
                        written: dict[str, str | None]) -> str | None:
    """The NOTE for `annotate`/`retire` on a field the index FILES carry with
    ANOTHER value (critic-opus T3 / critic-fable F3, T-00000668).

    A field the files carry wins at the next `--resync` (decision S-00002394,
    `mig.apply_log`), so the gesture lasts only until then unless the cell is
    edited in the files too — and that used to be silent. Read through
    `mig.read_state`, the very read `--resync` arbitrates with, so the NOTE
    predicts what `--resync` does. Files that cannot be read are SAID, never
    taken for "carry nothing".
    """
    try:
        carried = mig.read_state(root).annotations.get((scope, key), {})
    except (Refusal, OSError, ValueError) as exc:
        return (f"could not read the index FILES to tell whether they carry "
                f"{', '.join(written)} ({truncate(f'{type(exc).__name__}: {exc}', 160)})"
                f" -- if they do, the next --resync restores their value")
    fields = [name for name, value in written.items()
              if carried.get(name) is not None and carried.get(name) != value]
    if not fields:
        return None
    cells = ", ".join(FILE_CELLS[name] for name in fields)
    noun = "cell" if len(fields) == 1 else "cells"
    return (f"the index FILES still carry {', '.join(fields)} — the next --resync "
            f"restores it (a field the files carry wins, S-00002394); edit the "
            f"{cells} {noun} there too")


# ---------------------------------------------------------------------- modes
def mode_query(root: Path, args: argparse.Namespace) -> int:
    behind = check_freshness(root, args.strict, args.json)
    # A store left at the pre-T-00000668 in-repo path is NAMED, never read: on
    # stderr, so neither the text banner at the head of stdout nor `--json` moves.
    legacy = mig.legacy_note(root)
    if legacy:
        print(f"NOTE: {legacy}", file=sys.stderr)
    conn = connect_ro(root)
    try:
        set_display_width(conn)
        q = Query(name=args.name, purpose=args.purpose, module=args.module,
                  kind=args.kind, file=args.file,
                  callers=parse_sym_id(args.callers) if args.callers else None,
                  callees=parse_sym_id(args.callees) if args.callees else None,
                  include_deleted=args.include_deleted, no_fts=args.no_fts,
                  limit=args.limit)
        result = run_query(conn, q)
        # THE OVERLAY RUNS BEFORE `--source`, and the order is load-bearing: the
        # crux and its hash must be sliced out of the REFRESHED range, or a symbol
        # merely pushed down by an insertion above it would read DRIFTED — the
        # exact false alarm this overlay exists to remove.
        disabled_by = refresh_disabled_by_env()
        if args.no_refresh or disabled_by is not None:
            refresh = Refresh(enabled=False)
        else:
            refresh = build_overlay(root, conn, args.refresh_budget,
                                    edges_only=bool(args.callers or args.callees
                                                    or args.purpose))
        apply_overlay(result, refresh)
    finally:
        conn.close()

    result.notes += refresh_notes(refresh, disabled_by)
    if refresh.enabled and (args.callers or args.callees or args.purpose):
        result.notes.append(
            "les arêtes (`edges`) et les `:: purpose` sont clavetées sur un SYM-ID "
            "et ne se recalculent qu'au rebuild : l'overlay a rafraîchi les "
            "POSITIONS et n'a ajouté aucun symbole neuf")

    sources = None
    if getattr(args, "source", False):
        # The reference is the STORE's own generation, read through migrate --
        # this module never reads `meta` by hand, and never reads the lateral
        # INDEX_BODIES.json at all (↯ C2: one generation in play, not two).
        # CLAMPED HERE, at the single point where the flag is consumed: 0 (and
        # any negative) would reach `crux`'s `limit <= 0` branch and print every
        # body whole -- the opposite of a bound.
        source_lines = max(1, min(args.source_lines, SOURCE_LINES_CAP))
        sources = attach_sources(root, result, mig.read_db_generation(root),
                                 source_lines)
        if behind:
            result.notes.append(source_lag_line(behind))
        if len(result.rows) > SOURCE_MAX_ROWS:
            result.notes.append(source_truncation_line(len(result.rows)))

    if args.json:
        payload = {
            "db": str(mig.db_path(root)),
            "stale": ({"db_generation": behind[0], "files_generation": behind[1],
                       "fix": RESYNC_CMD} if behind else None),
            "engine": result.engine,
            "notes": result.notes,
            "total": result.total,
            "shown": len(result.rows),
            "truncated": result.truncated,
            "limit": args.limit,
            "refresh": refresh.as_json(),
            "results": [row.as_json() for row in result.rows],
        }
        if sources is not None:
            # ADDITIVE, and only when asked: an existing consumer of this payload
            # sees the same keys, of the same types, that it saw before.
            for entry, src in zip(payload["results"], sources):
                entry["source"] = src.as_json()
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    print("\n".join(query_header(result, q)))
    lines = render_rows(result, args.width, sources)
    if lines:
        print("\n".join(lines))
    else:
        print("# no match -- widen the pattern, or grep "
              ".agents/state/index/SYMBOLS*.md if the store is stale")
    if result.truncated:
        print(truncation_line(result, q))
    hors = hors_store_lines(refresh)
    if hors:
        print("\n".join(hors))
    return 0


def mode_annotate(root: Path, args: argparse.Namespace) -> int:
    check_freshness(root, args.strict, False)
    conn = connect_rw(root)
    try:
        set_display_width(conn)
        if args.symbol:
            if not args.purpose:
                raise Refusal("--symbol needs --purpose (a symbol annotation IS a "
                              "purpose; Role/Owner are module fields)")
            sym_id = parse_sym_id(args.symbol)
            row = conn.execute("SELECT name, path, deleted FROM symbols WHERE id = ?",
                               (sym_id,)).fetchone()
            if row is None:
                raise Refusal(f"{bi.sid(sym_id)} has no row in `symbols` -- refusing to "
                              f"author a purpose for a symbol the store does not know")
            if row["deleted"]:
                raise Refusal(f"{bi.sid(sym_id)} is a TOMBSTONE ({row['name']}) -- a "
                              f"retired id keeps its place so it is never reissued, "
                              f"but it has no purpose to describe")
            scope, key = "symbol", str(sym_id)
            before = annotation_row(conn, scope, key) or {}
            values = {"purpose": args.purpose, "role": before.get("role"),
                      "owner": before.get("owner")}
            label = f"{bi.sid(sym_id)} {row['name']}"
        else:
            scope, key = "module", args.module
            before = annotation_row(conn, scope, key) or {}
            if not (args.role or args.owner):
                raise Refusal("--module needs --role and/or --owner")
            values = {"purpose": before.get("purpose"),
                      "role": args.role or before.get("role"),
                      "owner": args.owner or before.get("owner")}
            label = f"module {key}"
            known = conn.execute("SELECT 1 FROM modules WHERE path = ?",
                                 (key,)).fetchone()
            if known is None:
                print(f"# NOTE: {key} is not a row of the `modules` mirror "
                      f"(CODEBASE_INDEX.md caps its table) -- annotating anyway")
        write_annotation(conn, scope, key, values)
    finally:
        conn.close()

    appended = mig.append_log(mig.log_path(root), journal_state(root, scope, key, values))
    print(f"symbols.py annotate -- {label}")
    for name in ANNOTATION_FIELDS:
        if values.get(name):
            print(f"  {name:<12} {truncate(values[name], 96)}")
    print(f"  annotations  1 row upserted (scope {scope}, key {key})")
    print(f"  log          {appended} line(s) appended to {mig.LOG_NAME}")
    if appended == 0:
        print("  unchanged -- the journal already ended on this value, nothing appended")
    print(f"  NOTE: the index FILES are not touched -- the DB is advisory, and "
          f"build_index.py owns SYMBOLS*.md. Write the `:: purpose` there too if it "
          f"must survive a rebuild.")
    authored = ({"purpose": args.purpose} if scope == "symbol" else
                {name: value for name, value in (("role", args.role),
                                                 ("owner", args.owner)) if value})
    override = files_override_note(root, scope, key, authored)
    if override:
        print(f"  NOTE: {override}")
    return 0


def mode_retire(root: Path, args: argparse.Namespace) -> int:
    check_freshness(root, args.strict, False)
    scope = "symbol" if args.symbol else "module"
    key = str(parse_sym_id(args.symbol)) if args.symbol else args.module
    conn = connect_rw(root)
    try:
        set_display_width(conn)
        before = annotation_row(conn, scope, key)
        if before is None:
            raise Refusal(f"no annotation on ({scope}, {key}) -- nothing to retire "
                          f"(the journal was NOT appended to)")
        wanted = ANNOTATION_FIELDS if args.field == "all" else (args.field,)
        retired = [name for name in wanted if before.get(name) is not None]
        if not retired:
            raise Refusal(f"({scope}, {key}) carries no {', '.join(wanted)} to retire "
                          f"-- the journal was NOT appended to")
        values = {name: (None if name in retired else before.get(name))
                  for name in ANNOTATION_FIELDS}
        write_annotation(conn, scope, key, values)
    finally:
        conn.close()

    appended = append_retraction(root, scope, key, retired)
    print(f"symbols.py retire -- ({scope}, {key})")
    for name in retired:
        print(f"  {name:<12} retired (was: {truncate(before.get(name), 60)})")
    print(f"  annotations  row KEPT with NULL field(s) -- the key is never deleted, so "
          f"the journal still replays onto it")
    print(f"  log          {appended} retraction line(s) APPENDED to {mig.LOG_NAME} "
          f"-- no line was ever removed (the journal is append-only)")
    override = files_override_note(root, scope, key, {name: None for name in retired})
    if override:
        print(f"  NOTE: {override}")
    return 0


def mode_compact(root: Path, args: argparse.Namespace) -> int:
    check_freshness(root, args.strict, False)
    target = require_db(root)
    size_before = target.stat().st_size
    conn = connect_rw(root)
    actions: list[str] = []
    try:
        counts = {
            "live": conn.execute("SELECT COUNT(*) AS n FROM symbols WHERE deleted = 0"
                                 ).fetchone()["n"],
            "tombstones": conn.execute("SELECT COUNT(*) AS n FROM symbols"
                                       " WHERE deleted = 1").fetchone()["n"],
            "edges": conn.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"],
            "modules": conn.execute("SELECT COUNT(*) AS n FROM modules").fetchone()["n"],
            "annotations": conn.execute("SELECT COUNT(*) AS n FROM annotations"
                                        ).fetchone()["n"],
        }
        dangling = [(r["src_id"], r["dst_id"]) for r in conn.execute(
            "SELECT src_id, dst_id FROM edges e WHERE NOT EXISTS"
            " (SELECT 1 FROM symbols WHERE id = e.src_id) OR NOT EXISTS"
            " (SELECT 1 FROM symbols WHERE id = e.dst_id)")]
        retired = conn.execute(
            "SELECT COUNT(*) AS n FROM annotations WHERE purpose IS NULL"
            " AND role IS NULL AND owner IS NULL").fetchone()["n"]

        if dangling and args.prune_dangling_edges:
            for src, dst in dangling:
                conn.execute("DELETE FROM edges WHERE src_id = ? AND dst_id = ?",
                             (src, dst))
            actions.append(f"pruned {len(dangling)} dangling edge(s)")
        elif dangling:
            actions.append(f"{len(dangling)} dangling edge(s) LEFT IN PLACE -- pass "
                           f"--prune-dangling-edges to remove them")

        if has_fts(conn):
            indexed = conn.execute("SELECT COUNT(*) AS n FROM symbols_fts").fetchone()["n"]
            if indexed != counts["live"]:
                conn.execute("DELETE FROM symbols_fts")
                conn.execute(
                    "INSERT INTO symbols_fts(rowid, name, path, purpose)"
                    " SELECT s.id, s.name, s.path,"
                    " COALESCE((SELECT purpose FROM annotations"
                    "           WHERE scope = 'symbol' AND key = CAST(s.id AS TEXT)), '')"
                    " FROM symbols s WHERE s.deleted = 0")
                actions.append(f"symbols_fts reindexed -- held {indexed} rows for "
                               f"{counts['live']} live symbols")
            else:
                actions.append(f"symbols_fts current ({indexed} rows)")
        else:
            actions.append("symbols_fts ABSENT -- searches degrade to LIKE "
                           "(this interpreter's sqlite3 had no FTS5 at --apply time)")

        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        if args.no_vacuum:
            actions.append(f"vacuum skipped (--no-vacuum) -- {free} free page(s)")
        elif free:
            conn.execute("VACUUM")
            actions.append(f"VACUUM reclaimed {free} free page(s)")
        else:
            actions.append("vacuum skipped -- 0 free pages, nothing to reclaim")
    finally:
        conn.close()

    size_after = target.stat().st_size
    print(f"symbols.py compact -- {target}")
    print("  symbols      " + f"{counts['live']} live / {counts['tombstones']} tombstone(s)")
    print(f"  edges        {counts['edges']}  ({len(dangling)} dangling)")
    print(f"  modules      {counts['modules']}")
    print(f"  annotations  {counts['annotations']}  ({retired} fully retired, kept)")
    for action in actions:
        print(f"  - {action}")
    print(f"  bytes        {size_before} -> {size_after}")
    print("  KEPT BY DESIGN: every tombstone (a retired SYM-ID is never reissued), "
          "every annotation key (the journal replays onto it), and every index "
          "SOURCE FILE -- compact touches nothing outside index.db.")
    if size_after != size_before:
        print(f"  NOTE: the file's bytes moved -- {mig.DB_NAME} is a machine store "
              f"outside the repository (T-00000668): nothing to commit.")
    return 0


# ------------------------------------------------------------------------- cli
def _nonneg_int(value: str) -> int:
    """argparse `type=` for a count that must be >= 0 (0 means 'no bound').

    A negative budget silently reached `changed[:budget]` and dropped files off
    the END of the sorted set -- a partial answer with no truncation line. Reject
    it at PARSE time instead, where argparse turns it into an exit-2 usage error.
    """
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}")
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="symbols.py",
        description="Query index.db -- the agent-facing surface of the SQLite index "
                    "store, machine state outside the repository (cadre.paths."
                    "index_db(), T-00000668; raw SQL stays forbidden).",
        epilog="POSTURE: default (warn) for exploration, where you re-locate by "
               "symbol NAME before trusting a line range; --strict whenever the "
               "answer becomes code or a decision, and in any non-interactive "
               "consumer. Exit 3 = --strict refused a stale store; 1 = a named "
               "refusal; 0 = answered. AND SINCE T-00000378 --strict IS NOT THE "
               "WHOLE POSTURE: the freshness overlay is ON by default and repairs "
               "line ranges from the WORKING TREE, so a --strict run that is "
               "allowed to answer no longer answers from the store alone. The two "
               "axes are orthogonal -- --strict is about index.db vs the index "
               "FILES, the overlay is about the index files vs the TREE -- and a "
               "consumer that must have store-only bytes passes --no-refresh (or "
               "sets AGENTS_INDEX_NO_REFRESH=1), which is SAID in the answer.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="project root (default: the git top level)")
    common.add_argument("--strict", action="store_true",
                        help="REFUSE (exit 3) instead of warning when index.db is a "
                             "generation behind the index files")
    sub = parser.add_subparsers(dest="mode", required=True)

    q = sub.add_parser("query", parents=[common],
                       help="search symbols and follow `edges` both ways")
    q.add_argument("--name", help="symbol name: FTS5 prefix match when available, "
                                  "else LIKE substring (`*` = wildcard)")
    q.add_argument("--purpose", help="match the authored `:: purpose` text")
    q.add_argument("--module", help="module key as CODEBASE_INDEX.md lists it "
                                    "(`module_of(path)`), or a path prefix")
    q.add_argument("--kind", help="symbol kind (function, class, ...)")
    q.add_argument("--file", help="exact path, or a path ending in this suffix")
    q.add_argument("--callers", metavar="SYM-ID",
                   help="symbols whose uses[] points AT this one (reverse edge)")
    q.add_argument("--callees", metavar="SYM-ID",
                   help="symbols this one's uses[] points at (forward edge)")
    q.add_argument("--include-deleted", action="store_true",
                   help="include tombstones (excluded by default)")
    q.add_argument("--no-fts", action="store_true",
                   help="force the LIKE fallback even when symbols_fts exists")
    q.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"max rows printed (default {DEFAULT_LIMIT}; 0 = no bound). "
                        f"A truncation is always announced, with the total.")
    q.add_argument("--width", type=int, default=PURPOSE_WIDTH,
                   help=f"purpose truncation width (default {PURPOSE_WIDTH})")
    q.add_argument("--source", action="store_true",
                   help="read each symbol's body from the WORKING TREE, print a "
                        "deterministic crux, and say whether it still matches the "
                        f"store: FRESH/DRIFTED @ <generation>, UNKNOWN or MISSING. "
                        f"The verdict is computed for every row; the crux TEXT for "
                        f"the first {SOURCE_MAX_ROWS} (announced when it bites).")
    q.add_argument("--source-lines", type=int, default=DEFAULT_SOURCE_LINES,
                   metavar="N",
                   help=f"crux length in SOURCE lines (default "
                        f"{DEFAULT_SOURCE_LINES}); a shorter body is shown whole "
                        f"and any drop is announced. CLAMPED to 1..{SOURCE_LINES_CAP}: "
                        f"0 is not 'unlimited', it is 1")
    q.add_argument("--json", action="store_true",
                   help="machine output; the staleness verdict moves to stderr AND "
                        "to the payload's `stale` key")
    q.add_argument("--no-refresh", action="store_true",
                   help="answer from the store ALONE: no working-tree diff, no "
                        f"repaired line ranges, no `# HORS STORE` block. Same "
                        f"effect as {NO_REFRESH_ENV}=1 for a whole session. Either "
                        f"way the answer SAYS it was disarmed.")
    q.add_argument("--refresh-budget", type=_nonneg_int, default=REFRESH_BUDGET,
                   metavar="N",
                   help=f"max CHANGED FILES the overlay re-extracts (default "
                        f"{REFRESH_BUDGET}; 0 = no bound). Files are taken in "
                        f"sorted order and a truncation is announced WITH the "
                        f"names it left uncovered.")

    a = sub.add_parser("annotate", parents=[common],
                       help="write an authored purpose / Role-Owner (table + journal)")
    target = a.add_mutually_exclusive_group(required=True)
    target.add_argument("--symbol", metavar="SYM-ID")
    target.add_argument("--module", metavar="PATH")
    a.add_argument("--purpose", help="what the symbol DOES, <= 10 words")
    a.add_argument("--role", help="module Role (with --module)")
    a.add_argument("--owner", help="module Owner agent (with --module)")

    r = sub.add_parser("retire", parents=[common],
                       help="retract an annotation; the journal is APPENDED to, never cut")
    rt = r.add_mutually_exclusive_group(required=True)
    rt.add_argument("--symbol", metavar="SYM-ID")
    rt.add_argument("--module", metavar="PATH")
    r.add_argument("--field", choices=[*ANNOTATION_FIELDS, "all"], default="all",
                   help="which field to retract (default: all of them)")

    c = sub.add_parser("compact", parents=[common],
                       help="report and tidy index.db; never deletes a source file")
    c.add_argument("--no-vacuum", action="store_true",
                   help="report free pages instead of reclaiming them")
    c.add_argument("--prune-dangling-edges", action="store_true",
                   help="delete edges whose src or dst has no `symbols` row "
                        "(off by default: they are re-derived by --resync)")
    return parser


def force_utf8_stdio() -> None:
    """Make stdio UTF-8, so a redirected answer is UTF-8 downstream.

    The output carries the builder's own vocabulary (`::`, `->`), the overlay's
    accented notes ("fraîcheur", "changé", "—") and whatever a human wrote in a
    purpose. `json.dumps` runs with ensure_ascii=False, so those bytes reach
    stdout RAW -- and a cp1252 console would encode them AS cp1252 (a lone 0xee
    for "î"), which `json.loads(bytes.decode("utf-8"))` cannot read back. The
    ENCODING change, not merely errors="replace", is what fixes that: replicate
    of the eleven sibling tools' `force_utf8_stdio` (ledger.py, events.py, ...).
    Keeps errors="replace" so a stray un-encodable char degrades a character,
    never the answer. `hasattr`-guarded for a stream with no `reconfigure`.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    force_utf8_stdio()

    root = mig.repo_root(args.root)
    modes = {"query": mode_query, "annotate": mode_annotate,
             "retire": mode_retire, "compact": mode_compact}
    try:
        return modes[args.mode](root, args)
    except StaleRefusal as exc:  # most specific first -- it is a Refusal subclass
        print(f"symbols.py: REFUSED -- {exc}", file=sys.stderr)
        return EXIT_STALE_STRICT
    except Refusal as exc:
        print(f"symbols.py: REFUSED -- {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
