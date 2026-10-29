"""Tests for migrate_index_to_db.py — the file index -> SQLite migration (v1).

FIXTURES ARE BUILT BY THE REAL WRITERS. Every temp state in this file comes out
of `bi.reserve_watermark` -> `bi.write_index` -> `bi.write_codebase_index` ->
`bi.write_delta`, the same four calls `build_index._build` makes, so the bytes
under test are the bytes the builder publishes: a real ToC, two real module
shards (`SYMBOLS_alpha.md`, `SYMBOLS_beta.md`), the real catch-all tombstone
shard (`SYMBOLS_deleted.md`), a real `CODEBASE_INDEX.md` and a real
`INDEX_DELTA.json`. Hand-fabricated files would test this suite's idea of the
grammar, not the producer's — the exact drift the migration refuses to allow.
Only two artefacts are hand-written, and both ARE the thing under test: a
corrupted row (case 7) and an orphan shard (case 10).

The extraction stage is deliberately NOT exercised: symbol dicts are passed
straight to the writers, so no test here depends on ctags being installed.

Covers the plan's 13 cases:
   1 `--check` writes nothing                  7  count reconciliation, 4 shapes
   2 `--apply` + `--verify`, exact counts      7b identity-lost refuses on every flag
   3 guarded upserts -> stable bytes           8  FTS5 absent -> declared degradation
   4 watermark lowered -> loud refusal         9  annotations_log replays both scopes
   5 tombstone kept, id never reissued        10  orphan shard is watermark-only (L-023)
   6 optional file absent -> note, not fail   11  INDEX_DELTA bound preserved (L-022)
                                              12 `DB STALE` on a generation mismatch

Style aligned with test_build_index_atomic.py: direct import (pytest puts this
file's directory on sys.path), a temp root per case, never the tracked index.
"""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Iterator, Sequence
from unittest import mock

import build_index as bi
import migrate_index_to_db as mig
import vendor_paths

SHA = "aaaa111"
SHA_NEXT = "bbbb222"
BACKEND = "stdlib"


def sym(sym_id: int, path: str, name: str, kind: str = "function",
        uses: Sequence[int] = (), purpose: str = "", start: int = 1,
        end: int = 9) -> dict:
    """One live row, in the shape `build_index`'s writers consume.

    `start`/`end` are explicit because the homonym cases turn on them: several
    symbols of the same name and kind in one file are told apart by their START
    line, and nothing else.
    """
    return {"id": sym_id, "path": path, "start": start, "end": end, "name": name,
            "kind": kind, "uses": list(uses), "purpose": purpose, "deleted": False}


def tomb(sym_id: int, name: str, kind: str = "function") -> dict:
    """One tombstone — a retired id, kept forever so it is never reissued."""
    return {"id": sym_id, "name": name, "kind": kind, "deleted": True}


# 6 live symbols over 2 modules + 1 tombstone. 5 `uses[]` edges, 3 purposes.
FIXTURE = [
    sym(1, "src/alpha/one.py", "alpha_one", uses=[2], purpose="entry point of alpha"),
    sym(2, "src/alpha/one.py", "alpha_two"),
    sym(3, "src/alpha/two.py", "AlphaBox", kind="class", uses=[2],
        purpose="holds alpha state"),
    sym(4, "src/beta/one.py", "beta_one", uses=[1, 3]),
    sym(5, "src/beta/one.py", "BetaBox", kind="class", purpose="beta container"),
    sym(6, "src/beta/two.py", "beta_two", uses=[5]),
    tomb(7, "alpha_gone"),
]
LIVE = 6
TOMBSTONES = 1
EDGES = 5
SYMBOL_PURPOSES = 3
MODULES = 2
JOURNAL_ROWS = 1  # the `snapshot` row; added/changed/removed are empty in the fixture
MODULE_ROLE = "Core domain"
MODULE_OWNER = "dev-mono"

# --- the homonym shape, copied from the real defect -------------------------
# Three symbols with the SAME (path, name, kind) at three different start lines,
# which is what a test file carrying a local constant per block actually produces
# (the measured case: `motif-remplissage.test.ts` / `backgroundColor` / constant).
# Schema v1's UNIQUE(path, name, kind) refused this outright.
HOM_PATH = "src/alpha/three.py"
HOM_NAME = "backgroundColor"
HOM_KIND = "constant"
HOM_IDS = (11, 12, 13)
HOM_STARTS = (10, 20, 30)
MIDDLE_PURPOSE = "the middle block's own fill"


def homonyms(starts: Sequence[int] = HOM_STARTS, purposes: Sequence[str] = ("", "", ""),
             ) -> list[dict]:
    """The three homonyms, at `starts`, in ASCENDING id order."""
    return [sym(sym_id, HOM_PATH, HOM_NAME, kind=HOM_KIND, start=start,
                end=start + 2, purpose=purpose)
            for sym_id, start, purpose in zip(HOM_IDS, starts, purposes)]


# `src/alpha/three.py` keeps the module count at 2: alpha and beta.
FIXTURE_HOM = FIXTURE + homonyms()

# The v1 schema, FROZEN. A migration test needs the real historical shape, and
# `mig.SCHEMA_SQL` is now v2 — reusing it would test nothing. Never edit this to
# match a newer version: it is the past, by definition.
V1_SCHEMA_SQL = (
    "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE symbols("
    " id INTEGER PRIMARY KEY, path TEXT, name TEXT, kind TEXT,"
    " start INTEGER, \"end\" INTEGER,"
    " deleted INTEGER NOT NULL DEFAULT 0, generation TEXT)",
    "CREATE UNIQUE INDEX symbols_live_key"
    " ON symbols(path, name, kind) WHERE deleted = 0",
    "CREATE TABLE edges("
    " src_id INTEGER, dst_id INTEGER, PRIMARY KEY(src_id, dst_id))",
    "CREATE TABLE modules("
    " path TEXT PRIMARY KEY, role TEXT, depends_on TEXT, owner TEXT)",
    "CREATE TABLE annotations("
    " scope TEXT NOT NULL CHECK(scope IN ('symbol','module')), key TEXT NOT NULL,"
    " purpose TEXT, role TEXT, owner TEXT, PRIMARY KEY(scope, key))",
    "CREATE TABLE journal("
    " seq INTEGER PRIMARY KEY, at_sha TEXT, kind TEXT, payload TEXT)",
)
# An annotation NO index file carries: written by a human straight into the store.
# Its survival is what proves the upgrade preserves authored content.
AUTHORED_KEY = ("symbol", "2")
AUTHORED_PURPOSE = "hand-written, absent from every index file"


@contextlib.contextmanager
def no_fts5() -> Iterator[None]:
    """Run as if this interpreter's sqlite3 had been compiled without FTS5.

    The substitution keeps the real code path: an unknown virtual-table module
    raises exactly the `sqlite3.OperationalError` a missing FTS5 raises.
    """
    real = mig.FTS_SQL
    mig.FTS_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts"
                   " USING fts_not_compiled_in(name, path, purpose)")
    try:
        yield
    finally:
        mig.FTS_SQL = real


@contextlib.contextmanager
def kit_at_schema(version: int) -> Iterator[None]:
    """Run as if THIS kit implemented schema `version`.

    The version negotiation has two directions and only one of them can be
    staged by editing the store: a kit meeting a NEWER store is a kit that moved
    backwards, which no fixture can produce by writing meta. So the kit is what
    moves here.
    """
    before = mig.SCHEMA_VERSION
    mig.SCHEMA_VERSION = version
    try:
        yield
    finally:
        mig.SCHEMA_VERSION = before


class _Case(unittest.TestCase):
    """Temp root + real-writer fixture + CLI driver. Holds no test of its own."""

    def setUp(self) -> None:
        # ignore_cleanup_errors: on Windows a just-written file can still be held
        # at teardown (AV/indexer); cleanup robustness is not what we measure.
        self._tmpdir = tempfile.TemporaryDirectory(prefix="abk_mig_",
                                                   ignore_cleanup_errors=True)
        self.root = Path(self._tmpdir.name).resolve()
        self.idx = bi.index_dir(self.root)
        # T-00000668 — THE STORE IS MACHINE STATE NOW, under `state_home()`, and
        # this suite drives the CLI IN-PROCESS: without this patch every run would
        # create `index.db` files under the pilot's real `~/.local/state/cadre`.
        # A SIBLING temp dir (never under `self.root`, whose tree is the index
        # under test), `$CADRE_STATE_DIR` pointed at it, `$CADRE_PROJECT_ROOT`
        # removed so `db_path(self.root)` resolves THIS root. `state_home()`
        # re-reads the environment at every call, and every `subprocess` of the
        # suite inherits the patched `os.environ`. Tenu par
        # `.agents/evals/test_index_machine.py` (T9).
        self._statedir = tempfile.TemporaryDirectory(prefix="cadre-state-",
                                                     ignore_cleanup_errors=True)
        self.addCleanup(self._statedir.cleanup)
        self._env = mock.patch.dict(os.environ,
                                    {"CADRE_STATE_DIR": self._statedir.name})
        self._env.start()
        self.addCleanup(self._env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    @staticmethod
    def _store_vide(chemin: Path) -> Path:
        """Le fichier VIDE d'un store à semer à la main, parent compris : depuis
        T-00000770 `mig.connect` n'ouvre qu'un store EXISTANT (il refusait déjà de
        suivre, il refuse désormais de créer). Un fichier vide est une base
        SQLite vide valide — ce que `sqlite3.connect` créait avant."""
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.touch()
        return chemin

    # --- fixture, written by build_index's own publishers -------------------
    def write_fixture(self, symbols: Sequence[dict] = FIXTURE, sha: str = SHA,
                      threshold: int = 2, reserve: int | None = None) -> None:
        """Publish a complete index state with the REAL writers.

        `threshold` below the live count gives the sharded shape (ToC + one shard
        per module); above it gives the monolithic one. `reserve` is the SYM-ID
        bound reserved in phase 1 — raise it above every id on disk to exercise
        L-022's upper-bound property.
        """
        symbols = list(symbols)
        max_id = max(s["id"] for s in symbols)
        bi.set_id_width(max_id)
        pub = bi._Publisher()
        bi.reserve_watermark(self.root, reserve if reserve is not None else max_id, pub)
        shard_info = bi.write_index(self.root, symbols, sha, BACKEND, threshold, pub)
        files = sorted({s["path"] for s in symbols if not s.get("deleted")})
        cb_info = bi.write_codebase_index(self.root, symbols, files, sha, BACKEND,
                                          threshold, pub)
        bi.write_delta(self.root, symbols, sha, BACKEND,
                       {"added": [], "changed": [], "removed": []},
                       shard_info, cb_info, pub)

    def annotate_module(self, module: str = "alpha", role: str = MODULE_ROLE,
                        owner: str = MODULE_OWNER) -> None:
        """Fill a module's Role/Owner cells, the way the indexer agent does.

        `build_index` writes `—` placeholders and PRESERVES whatever a human or
        the indexer put there, so this is authored content in its authored place.
        """
        path = self.idx / mig.CODEBASE_NAME
        out, hit = [], False
        for line in path.read_text(encoding="utf-8").splitlines():
            m = bi.ROW_RE.match(line)
            if m and m.group(1).strip() == module:
                out.append(f"| {module} | {role} | {m.group(3).strip()} | {owner} |")
                hit = True
            else:
                out.append(line)
        self.assertTrue(hit, f"fixture has no module row for {module!r}")
        path.write_text("\n".join(out) + "\n", encoding="utf-8")

    def full_fixture(self, **kwargs) -> None:
        self.write_fixture(**kwargs)
        self.annotate_module()

    def corrupt_row(self, name: str, sym_id: int) -> None:
        """Mangle one active row so `bi._parse_rows` SKIPS it, silently.

        That silent skip is the whole reason the count reconciliation exists.
        """
        path = self.idx / name
        before = sum(1 for r in bi._parse_rows(bi._read(path)) if not r["deleted"])
        marker = bi.sid(sym_id)
        out = [line.replace("uses[", "USES[") if line.startswith(marker) else line
               for line in path.read_text(encoding="utf-8").splitlines()]
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        after = sum(1 for r in bi._parse_rows(bi._read(path)) if not r["deleted"])
        self.assertEqual(before - 1, after,
                         "the corruption did not actually hide a row from the parser")

    def write_orphan_shard(self, name: str = "SYMBOLS_gamma.md",
                           rows: Sequence[dict] = (), sha: str = SHA) -> None:
        """A shard the ToC does not reference, stamped with the SAME generation."""
        text = "\n".join(bi.header(len([r for r in rows if not r.get("deleted")]),
                                   sha, BACKEND)
                         + [bi.sym_line(r) for r in rows]) + "\n"
        (self.idx / name).write_text(text, encoding="utf-8")

    def seed_v1_db(self) -> None:
        """Create an index.db on the FROZEN v1 schema, populated the v1 way.

        This is the store two real projects already carry. It is built from the
        current index files (a v1 store could only ever hold a collision-free
        set — its own unique index forbade the rest), plus one annotation no file
        carries, so the upgrade has authored content to preserve or lose.

        The annotations land in the DB AND in `annotations_log.jsonl`, because
        that is what v1's `--apply` did: the journal doubles the authored half so
        a binary merge conflict can be resolved by replay. Seeding only the DB
        would build a store no run ever produced, and `--verify` would rightly
        call the missing log lines a divergence.
        """
        state = mig.read_state(self.root)
        state.annotations[AUTHORED_KEY] = {"purpose": AUTHORED_PURPOSE, "role": None,
                                           "owner": None}
        # `db_path` creates nothing (T-00000668): the machine partition's
        # `index/` directory is created by `_atomic_create` only, so a store
        # seeded BY HAND must create its parent first — and, since T-00000770,
        # its empty file too: `connect` no longer creates it.
        conn = mig.connect(self._store_vide(mig.db_path(self.root)))
        try:
            for stmt in V1_SCHEMA_SQL:
                conn.execute(stmt)
            for s in state.symbols.values():
                conn.execute(
                    'INSERT INTO symbols(id, path, name, kind, start, "end",'
                    " deleted, generation) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (s["id"], s["path"], s["name"], s["kind"], s["start"], s["end"],
                     int(s["deleted"]), s["generation"]))
            for src, dst in sorted(state.edges):
                conn.execute("INSERT INTO edges(src_id, dst_id) VALUES(?, ?)",
                             (src, dst))
            for mod in state.modules:
                conn.execute("INSERT INTO modules(path, role, depends_on, owner)"
                             " VALUES(?, ?, ?, ?)",
                             (mod.path, mod.role, mod.depends_on, mod.owner))
            for (scope, key), values in state.annotations.items():
                conn.execute("INSERT INTO annotations(scope, key, purpose, role, owner)"
                             " VALUES(?, ?, ?, ?, ?)",
                             (scope, key, values["purpose"], values["role"],
                              values["owner"]))
            for seq, sha, kind, payload in state.journal:
                conn.execute("INSERT INTO journal(seq, at_sha, kind, payload)"
                             " VALUES(?, ?, ?, ?)", (seq, sha, kind, payload))
            for key, value in (("schema_version", "1"),
                               ("built_at_sha", state.generation or ""),
                               ("watermark", str(state.watermark))):
                conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (key, value))
        finally:
            conn.close()
        mig.append_log(mig.log_path(self.root), state)

    def seed_v2_db(self) -> None:
        """The store a project carries TODAY: v1 that climbed exactly one rung.

        Built with the REAL rung rather than a frozen copy of the v2 DDL — a
        second spelling of the past would drift from the one that actually ran on
        the two stores this upgrade has to meet.
        """
        self.seed_v1_db()
        conn = mig.connect(mig.db_path(self.root))
        try:
            mig._upgrade_v1_to_v2(conn)
            conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', '2')"
                         " ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        finally:
            conn.close()

    def resync_counts(self) -> tuple[dict, mig.State]:
        """What one real resync WOULD write, then rolled back.

        The property under test is the COUNT `write_state` returns — "zero symbol
        rows" — so this drives the real writer and throws the transaction away
        rather than asserting on a printed line.
        """
        state = mig.read_state(self.root)
        with self.open_db() as conn:
            fts = mig._table_exists(conn, "symbols_fts")
            conn.execute("BEGIN")
            try:
                counts = mig.write_state(conn, state, fts)
            finally:
                conn.execute("ROLLBACK")
        return counts, state

    def set_meta(self, key: str, value: str) -> None:
        conn = mig.connect(mig.db_path(self.root))
        try:
            conn.execute("INSERT INTO meta(key, value) VALUES(?, ?)"
                         " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (key, value))
        finally:
            conn.close()

    def ordinals(self) -> dict:
        """`{id: ordinal}` over the LIVE stored symbols."""
        return {i: s["ordinal"] for i, s in self.symbols_by_id().items()
                if not s["deleted"]}

    # --- run ---------------------------------------------------------------
    def run_cli(self, *argv: str, expect: int = 0) -> str:
        """Run the real CLI in-process; returns stdout+stderr, asserts the code."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mig.cli(["--root", str(self.root), *argv])
        text = out.getvalue() + err.getvalue()
        self.assertEqual(expect, code, f"output={text!r}")
        return text

    # --- inspect -----------------------------------------------------------
    def snapshot(self) -> dict:
        return {p.name: p.read_bytes() for p in sorted(self.idx.iterdir()) if p.is_file()}

    def digest(self, name: str) -> str:
        # The store no longer sits among the index files (T-00000668): its name
        # is resolved through the module's single resolution point.
        target = mig.db_path(self.root) if name == mig.DB_NAME else self.idx / name
        return hashlib.sha256(target.read_bytes()).hexdigest()

    @contextlib.contextmanager
    def open_db(self) -> Iterator[sqlite3.Connection]:
        conn = mig.connect(mig.db_path(self.root))
        try:
            yield conn
        finally:
            conn.close()

    def table_counts(self) -> dict:
        with self.open_db() as conn:
            # SAST false positive (repatriated from a consumer repo, T-00000310). A table name is an SQL
            # IDENTIFIER: it cannot be bound with `?`. The names come from the
            # closed literal tuple in the comprehension below; this helper
            # takes no argument and reads no external input.
            # nosemgrep: agents.security.python-sql-injection-string-format
            return {t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
                    for t in ("symbols", "edges", "modules", "annotations", "journal")}

    def meta(self) -> dict:
        with self.open_db() as conn:
            return mig._fetch_meta(conn)

    def symbols_by_id(self) -> dict:
        with self.open_db() as conn:
            return mig._fetch_symbols(conn)

    def symbol_columns(self) -> list:
        """The `symbols` columns, in declaration order — read via the module's
        own accessor so the test cannot spell the PRAGMA a second way."""
        with self.open_db() as conn:
            return list(mig._symbols_columns(conn))

    def write_bodies(self, symbols: Sequence[dict] = FIXTURE, sha: str = SHA,
                     generation: str | None = None) -> dict:
        """Publish INDEX_BODIES.json for `symbols`, with the BUILDER's writer.

        The migration fixtures pass symbol dicts straight to the writers, so they
        carry no `body_sha` until this puts one there. The hash values are
        synthetic on purpose: what is under test here is the store's round trip,
        not `bi.body_hash`, which owns its own cases in
        test_build_index_atomic.py.
        """
        rows = [{**s, "body_sha": f"{s['id']:016x}"} for s in symbols]
        payload = bi.write_bodies(self.root, rows, sha)
        if generation is not None:  # a lateral that DISAGREES with the files
            payload["generation"] = generation
            (self.idx / bi.BODIES_NAME).write_text(
                json.dumps(payload, sort_keys=True, indent=2) + "\n",
                encoding="utf-8")
        return payload

    def assert_no_db(self) -> None:
        self.assertFalse(mig.db_path(self.root).exists(), "a DB was written")


class CheckTests(_Case):
    """Case 1 — `--check` is a plan, and a plan writes nothing."""

    def test_check_writes_nothing_at_all(self):
        self.full_fixture()
        before = self.snapshot()
        out = self.run_cli("--check")
        self.assertEqual(before, self.snapshot(), "--check modified the index files")
        self.assert_no_db()
        self.assertFalse(mig.log_path(self.root).exists(), "--check wrote the log")
        self.assertIn("nothing is written", out)
        self.assertIn("--apply would create", out)

    def test_check_reports_the_counts_it_would_write(self):
        self.full_fixture()
        out = self.run_cli("--check")
        self.assertIn(f"symbols      {7:>6}", out)
        self.assertIn(f"edges        {EDGES:>6}", out)
        self.assertNotIn("REFUSED", out)


class ApplyAndVerifyTests(_Case):
    """Case 2 — the migration itself: exact counts, then a green round trip."""

    def test_apply_then_verify_with_exact_per_table_counts(self):
        self.full_fixture()
        out = self.run_cli("--apply")
        self.assertIn("created", out)
        self.assertEqual(
            {"symbols": LIVE + TOMBSTONES, "edges": EDGES, "modules": MODULES,
             "annotations": SYMBOL_PURPOSES + 1, "journal": JOURNAL_ROWS},
            self.table_counts())

        meta = self.meta()
        self.assertEqual(str(mig.SCHEMA_VERSION), meta["schema_version"])
        self.assertEqual(SHA, meta["built_at_sha"])
        self.assertEqual("7", meta["watermark"])

        with self.open_db() as conn:
            edges = {(r["src_id"], r["dst_id"])
                     for r in conn.execute("SELECT src_id, dst_id FROM edges")}
            annotations = mig._fetch_annotations(conn)
        self.assertEqual({(1, 2), (3, 2), (4, 1), (4, 3), (6, 5)}, edges)
        self.assertEqual({"purpose": "entry point of alpha", "role": None, "owner": None},
                         annotations[("symbol", "1")])
        self.assertEqual({"purpose": None, "role": MODULE_ROLE, "owner": MODULE_OWNER},
                         annotations[("module", "alpha")])

        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_apply_preserves_the_real_start_end_range_and_the_kind(self):
        self.full_fixture()
        self.run_cli("--apply")
        row = self.symbols_by_id()[3]
        self.assertEqual(("src/alpha/two.py", "AlphaBox", "class", 1, 9),
                         (row["path"], row["name"], row["kind"], row["start"], row["end"]))
        self.assertEqual(SHA, row["generation"])

    def test_apply_refuses_to_overwrite_an_existing_db(self):
        self.full_fixture()
        self.run_cli("--apply")
        before = self.digest(mig.DB_NAME)
        out = self.run_cli("--apply", expect=1)
        self.assertIn("--resync", out)
        self.assertEqual(before, self.digest(mig.DB_NAME))

    def test_the_migration_never_deletes_a_source_file(self):
        self.full_fixture()
        sources = set(self.snapshot())
        self.run_cli("--apply")
        self.assertTrue(sources <= set(self.snapshot()),
                        "an index source file disappeared during the migration")


class IdempotenceTests(_Case):
    """Case 3 — guarded upserts: an unchanged resync must not move a byte."""

    def test_resync_on_unchanged_state_leaves_the_bytes_alone(self):
        self.full_fixture()
        self.run_cli("--apply")
        db_before = self.digest(mig.DB_NAME)
        log_before = self.digest(mig.LOG_NAME)

        out = self.run_cli("--resync")

        self.assertEqual(db_before, self.digest(mig.DB_NAME),
                         "an unchanged resync rewrote pages — commit noise at every run")
        self.assertEqual(log_before, self.digest(mig.LOG_NAME),
                         "an unchanged resync appended to the annotations log")
        self.assertIn("unchanged", out)
        self.assertIn("log               0", out)

    def test_a_real_change_does_move_the_bytes(self):
        """Non-vacuity of the test above: the guard must not be a no-op writer."""
        self.full_fixture()
        self.run_cli("--apply")
        before = self.digest(mig.DB_NAME)
        self.write_fixture(symbols=list(FIXTURE) + [sym(8, "src/beta/two.py", "beta_three")])
        self.annotate_module()
        out = self.run_cli("--resync")
        self.assertNotEqual(before, self.digest(mig.DB_NAME))
        self.assertNotIn("unchanged", out)
        self.assertEqual(LIVE + 1 + TOMBSTONES, self.table_counts()["symbols"])


class WatermarkTests(_Case):
    """Cases 4 and 11 — the SYM-ID bound is an upper bound, and monotone (L-022)."""

    def test_a_bound_above_every_id_on_disk_is_preserved_as_is(self):
        self.full_fixture(reserve=900)
        self.run_cli("--apply")
        self.assertEqual("900", self.meta()["watermark"])
        self.assertEqual(7, max(self.symbols_by_id()), "an id above the disk max appeared")
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_resync_refuses_to_lower_the_watermark(self):
        self.full_fixture(reserve=900)
        self.run_cli("--apply")
        # A restored/merged older INDEX_DELTA.json: the bound regressed. Written
        # by hand because reserve_watermark itself refuses to go down.
        delta_path = self.idx / bi.DELTA_NAME
        payload = json.loads(delta_path.read_text(encoding="utf-8"))
        payload[bi.WATERMARK_KEY] = 7
        delta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        out = self.run_cli("--resync", expect=1)
        self.assertIn("refusing to lower the SYM-ID watermark", out)
        self.assertIn("L-022", out)
        self.assertEqual("900", self.meta()["watermark"],
                         "the refused resync still degraded the stored bound")


class TombstoneTests(_Case):
    """Cases 5 and 10 — a retired id stays retired, whatever a shard claims."""

    def test_tombstone_survives_a_resync_and_its_id_is_never_reused(self):
        self.full_fixture()
        self.run_cli("--apply")
        self.write_fixture(symbols=list(FIXTURE) + [sym(8, "src/beta/two.py", "beta_three")])
        self.annotate_module()
        self.run_cli("--resync")

        rows = self.symbols_by_id()
        self.assertTrue(rows[7]["deleted"], "the tombstone was resurrected")
        self.assertEqual("alpha_gone", rows[7]["name"])
        self.assertEqual("beta_three", rows[8]["name"])
        self.assertEqual("8", self.meta()["watermark"])

    def test_an_orphan_shard_feeds_the_bound_and_nothing_else(self):
        """L-023: an unreferenced shard of the same generation is watermark-only."""
        self.full_fixture()
        self.write_orphan_shard(rows=[
            sym(777, "src/gamma/x.py", "gamma_one"),
            # Contradicts the tombstone: this row claims SYM-007 is alive again.
            sym(7, "src/alpha/one.py", "alpha_gone"),
        ])
        out = self.run_cli("--apply")

        rows = self.symbols_by_id()
        self.assertNotIn(777, rows, "an orphan shard's rows were ingested")
        self.assertTrue(rows[7]["deleted"],
                        "an orphan shard resurrected a tombstone (L-023)")
        self.assertEqual("777", self.meta()["watermark"],
                         "the orphan's ids did not feed the bound")
        self.assertEqual(LIVE + TOMBSTONES, self.table_counts()["symbols"])
        self.assertIn("watermark-only", out)
        self.assertIn("verify       OK", self.run_cli("--verify"))


class OptionalFileTests(_Case):
    """Case 6 — an absent OPTIONAL file is a printed note, never a failure."""

    def test_codebase_index_absent_gives_a_note_and_an_empty_modules_table(self):
        self.write_fixture()
        (self.idx / mig.CODEBASE_NAME).unlink()
        out = self.run_cli("--check")
        self.assertIn(f"NOTE: {mig.CODEBASE_NAME} absent", out)
        self.run_cli("--apply")
        self.assertEqual(0, self.table_counts()["modules"])
        self.assertEqual(LIVE + TOMBSTONES, self.table_counts()["symbols"])

    def test_delta_absent_gives_a_note_and_an_empty_journal(self):
        self.full_fixture()
        (self.idx / bi.DELTA_NAME).unlink()
        out = self.run_cli("--apply")
        self.assertIn(f"NOTE: {bi.DELTA_NAME} absent", out)
        self.assertEqual(0, self.table_counts()["journal"])
        # No bound on disk: the watermark falls back to the largest id SEEN,
        # never to zero.
        self.assertEqual("7", self.meta()["watermark"])


class ReconciliationTests(_Case):
    """Case 7 — a row the parser skips must surface as a COUNT gap, loudly."""

    def test_a_healthy_sharded_tree_never_trips_the_reconciliation(self):
        self.full_fixture()
        out = self.run_cli("--check")
        self.assertNotIn("REFUSED", out)
        self.assertNotIn("reconciliation", out)

    def test_a_corrupted_row_in_a_monolithic_file_is_named_with_both_counts(self):
        self.full_fixture(threshold=99)  # one SYMBOLS.md, no shards
        self.assertEqual([], list(self.idx.glob(bi.SHARD_GLOB)), "fixture is not monolithic")
        self.corrupt_row(bi.MAIN_NAME, 2)
        out = self.run_cli("--apply", expect=1)
        self.assertIn("count reconciliation failed", out)
        self.assertIn(f"{bi.MAIN_NAME}: header declares {LIVE} entries, "
                      f"{LIVE - 1} active rows parsed", out)
        self.assert_no_db()

    def test_a_corrupted_row_in_a_shard_is_named_with_both_counts(self):
        self.full_fixture()
        self.corrupt_row("SYMBOLS_alpha.md", 2)
        out = self.run_cli("--apply", expect=1)
        self.assertIn("SYMBOLS_alpha.md: header declares 3 entries, 2 active rows parsed",
                      out)
        self.assert_no_db()

    def test_a_toc_that_over_declares_is_reconciled_against_the_shard_sum(self):
        """The third case: a sharded ToC carries no parsable row by design."""
        main = self.idx / bi.MAIN_NAME
        self.full_fixture()
        text = main.read_text(encoding="utf-8")
        main.write_text(text.replace(f"Symbols — {LIVE} entries",
                                     f"Symbols — {LIVE + 1} entries"), encoding="utf-8")
        out = self.run_cli("--apply", expect=1)
        self.assertIn(f"{bi.MAIN_NAME}: ToC header declares {LIVE + 1} entries, "
                      f"referenced shards parse {LIVE} active rows", out)
        self.assert_no_db()

    def test_the_grand_total_is_reconciled_against_the_delta(self):
        self.full_fixture()
        delta_path = self.idx / bi.DELTA_NAME
        payload = json.loads(delta_path.read_text(encoding="utf-8"))
        payload["counts"]["active"] = 99
        delta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        out = self.run_cli("--apply", expect=1)
        self.assertIn(f"{bi.DELTA_NAME}: counts.active is 99, {LIVE} live symbols "
                      f"ingested", out)
        self.assert_no_db()


class IdentityLostTests(_Case):
    """Case 7bis — SYMBOLS.md gone while shards remain: every flag refuses."""

    def test_every_flag_exits_non_zero_with_identity_lost_and_writes_no_db(self):
        self.full_fixture()
        self.run_cli("--apply")  # a valid DB first, so --verify/--resync could run
        db_before = self.digest(mig.DB_NAME)
        (self.idx / bi.MAIN_NAME).unlink()
        self.assertTrue(list(self.idx.glob(bi.SHARD_GLOB)), "no shard left to lose")

        for flag in ("--check", "--apply", "--verify", "--resync"):
            with self.subTest(flag=flag):
                out = self.run_cli(flag, expect=1)
                self.assertIn(bi.IDENTITY_LOST, out)
                self.assertEqual(db_before, self.digest(mig.DB_NAME),
                                 f"{flag} touched the DB after identity was lost")

    def test_identity_lost_before_any_apply_leaves_no_db_behind(self):
        self.full_fixture()
        (self.idx / bi.MAIN_NAME).unlink()
        out = self.run_cli("--apply", expect=1)
        self.assertIn("REFUSED", out)
        self.assert_no_db()


class Fts5Tests(_Case):
    """Case 8 — FTS5 is feature-detected: absent means declared, never fatal."""

    def test_absent_fts5_degrades_out_loud_and_still_migrates(self):
        self.full_fixture()
        with no_fts5():
            out = self.run_cli("--apply")
        self.assertIn("ABSENT", out)
        self.assertIn("no symbols_fts", out)
        self.assertEqual(LIVE + TOMBSTONES, self.table_counts()["symbols"])
        with self.open_db() as conn:
            self.assertFalse(mig._table_exists(conn, "symbols_fts"))

    def test_a_search_index_created_by_a_later_resync_is_backfilled(self):
        """A DB migrated WITHOUT fts5, resynced on an interpreter that HAS it.

        The guarded upserts write only CHANGED rows, so the freshly created
        `symbols_fts` would stay EMPTY while existing — and an empty search index
        answers every query with "no match", which reads exactly like a correct
        answer. A silence that looks like a result is what this whole script
        refuses elsewhere; it must not appear here.
        """
        if not mig.fts_probe():
            self.skipTest("this interpreter's sqlite3 has no FTS5")
        self.full_fixture()
        with no_fts5():
            self.run_cli("--apply")
        with self.open_db() as conn:
            self.assertFalse(mig._table_exists(conn, "symbols_fts"), "fixture is wrong")

        out = self.run_cli("--resync")  # nothing else changed

        with self.open_db() as conn:
            self.assertTrue(mig._table_exists(conn, "symbols_fts"))
            total = conn.execute("SELECT COUNT(*) AS n FROM symbols_fts").fetchone()["n"]
            hits = conn.execute("SELECT rowid FROM symbols_fts"
                                " WHERE symbols_fts MATCH 'entry'").fetchall()
        self.assertEqual(LIVE, total, "the new search index was left silently empty")
        self.assertEqual([1], [r["rowid"] for r in hits])
        self.assertIn("fts", out)

    def test_present_fts5_indexes_the_live_symbols_with_their_purpose(self):
        if not mig.fts_probe():
            self.skipTest("this interpreter's sqlite3 has no FTS5")
        self.full_fixture()
        self.run_cli("--apply")
        with self.open_db() as conn:
            # `entry` lives only in SYM-001's purpose — a name/path term would not
            # prove the purpose column is searchable (the default tokenizer splits
            # `alpha_one` into `alpha`+`one`, which every alpha row's PATH matches).
            hits = conn.execute("SELECT rowid FROM symbols_fts"
                                " WHERE symbols_fts MATCH 'entry'").fetchall()
            total = conn.execute("SELECT COUNT(*) AS n FROM symbols_fts").fetchone()["n"]
        self.assertEqual([1], [r["rowid"] for r in hits])
        self.assertEqual(LIVE, total, "a tombstone was indexed for search")


class AnnotationsLogTests(_Case):
    """Case 9 — the authored half is replayable from the tracked jsonl journal."""

    def test_the_log_replays_into_the_same_annotations_table_for_both_scopes(self):
        self.full_fixture()
        self.run_cli("--apply")
        replayed = mig.replay_log(mig.read_log(mig.log_path(self.root)))
        with self.open_db() as conn:
            stored = mig._fetch_annotations(conn)
        self.assertEqual(SYMBOL_PURPOSES + 1, len(replayed))
        self.assertEqual(stored, replayed)

        # Replayed onto a VIRGIN db, through the production writer, the table is
        # rebuilt identically — this is the merge-conflict recovery path.
        virgin = self._store_vide(self.root / "virgin.db")
        conn = mig.connect(virgin)
        try:
            fts = mig.ensure_schema(conn)
            mig.write_state(conn, mig.State(root=self.root, annotations=replayed), fts)
            rebuilt = mig._fetch_annotations(conn)
        finally:
            conn.close()
        self.assertEqual(stored, rebuilt)

    def test_every_logged_line_carries_the_documented_schema(self):
        self.full_fixture()
        self.run_cli("--apply")
        entries = [json.loads(line) for line in
                   mig.log_path(self.root).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(SYMBOL_PURPOSES + 2, len(entries))  # role AND owner for alpha
        for entry in entries:
            self.assertEqual({"scope", "key", "field", "value", "at_sha"}, set(entry))
            self.assertIn(entry["scope"], ("symbol", "module"))
            self.assertIn(entry["field"], ("purpose", "role", "owner"))
            self.assertEqual(SHA, entry["at_sha"])


class ApplyLogTests(_Case):
    """T8 (T-00000668) — `apply_log` ISOLATED, on a real store built by `--apply`.

    The journal -> store direction exists in ONE place, and its rule is: A FIELD
    THE FILES CARRY WINS; OTHERWISE THE LOG'S LAST VALUE, RETRACTION INCLUDED
    (critic-opus F1 / exec-critic, decision S-00002394 — the plan's COALESCE
    "store first" never propagated a change or a retraction made on another
    machine). Each property with the mutation that reddens it: the guard
    re-reads the store, so a second call on the same folded log writes NOTHING
    (drop the `merged == before` guard: the second call writes again); a scope
    outside symbol/module is SKIPPED and counted, never raised, never written
    (drop the filter: the table's CHECK raises); a field the FILES carry is never
    overwritten by the log (let the log win: the file's purpose is lost); the
    log's last value overwrites a stale STORE field (store first: the old value
    stays); a logged retraction writes the NULL row `retire` keeps (skip the
    all-NULL merge: no row, and `--verify` fails forever on a fresh machine).
    """

    UNANNOTATED = "2"   # `alpha_two`: no purpose in any index file
    FILE_OWNED = "1"    # `alpha_one`: purpose "entry point of alpha" in the files
    NULL_ROW = {"purpose": None, "role": None, "owner": None}

    def _apply(self, replayed: dict, files: dict | None = None,
               overridden: list | None = None) -> tuple[int, int]:
        with self.open_db() as conn:
            conn.execute("BEGIN")
            try:
                result = mig.apply_log(conn, replayed, files, overridden)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        return result

    def _log_line(self, scope: str, key: str, field_name: str,
                  value: str | None) -> None:
        """One line of the journal, in the shape `append_log` / `retire` write."""
        entry = {"scope": scope, "key": key, "field": field_name, "value": value,
                 "at_sha": SHA}
        if value is None:
            entry["retired"] = True
        log = mig.log_path(self.root)
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")

    def _annotation(self, scope: str, key: str) -> dict | None:
        with self.open_db() as conn:
            return mig._fetch_annotations(conn).get((scope, key))

    def test_a_second_call_on_the_same_log_writes_nothing(self):
        self.full_fixture()
        self.run_cli("--apply")
        replayed = {("symbol", self.UNANNOTATED): {
            "purpose": "posé par annotate", "role": None, "owner": None}}
        self.assertEqual((1, 0), self._apply(replayed))
        self.assertEqual((0, 0), self._apply(replayed),
                         "the guard did not re-read the store: a second call wrote")
        self.assertEqual("posé par annotate",
                         self._annotation("symbol", self.UNANNOTATED)["purpose"])

    def test_an_unknown_scope_is_skipped_and_counted_never_written(self):
        self.full_fixture()
        self.run_cli("--apply")
        replayed = {("bogus", "x"): {"purpose": "p", "role": None, "owner": None}}
        self.assertEqual((0, 1), self._apply(replayed))
        self.assertIsNone(self._annotation("bogus", "x"))

    def test_a_file_field_is_never_overwritten_by_the_log(self):
        """Renamed from `test_a_stored_field_is_never_overwritten_by_the_log`: it
        is the FILE that wins, not the store — see the next case."""
        self.full_fixture()
        self.run_cli("--apply")
        files = mig.read_state(self.root).annotations
        self.assertEqual("entry point of alpha",
                         files[("symbol", self.FILE_OWNED)]["purpose"],
                         "fixture not armed: the files carry no purpose here")
        replayed = {("symbol", self.FILE_OWNED): {
            "purpose": "a DIFFERENT log value", "role": None, "owner": None}}
        self.assertEqual((0, 0), self._apply(replayed, files))
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", self.FILE_OWNED)["purpose"])

    def test_the_last_log_value_overwrites_a_stale_store_field(self):
        """critic-opus F1 — another machine annotated P2 after P1: the log's LAST
        value reaches a store still holding P1 when no file carries the field."""
        self.full_fixture()
        self.run_cli("--apply")
        files = mig.read_state(self.root).annotations
        self.assertEqual((1, 0), self._apply(
            {("symbol", self.UNANNOTATED): dict(self.NULL_ROW, purpose="P1")}, files))
        self.assertEqual((1, 0), self._apply(
            {("symbol", self.UNANNOTATED): dict(self.NULL_ROW, purpose="P2")}, files),
            "store first: the stale P1 was kept over the log's last value")
        self.assertEqual("P2", self._annotation("symbol", self.UNANNOTATED)["purpose"])

    def test_a_store_value_replaced_by_the_log_is_collected(self):
        """critic-opus T2 / critic-fable F2 — after a `git pull --no-rebase`,
        union puts UPSTREAM's line last, so the journal's last value can replace
        what this machine holds IN SILENCE. `overridden` names every stored
        non-NULL field the LOG replaces (a retraction included). NOT collected:
        a field filled from NULL, and a field the FILES carry (the file wins, it
        is not "the journal's value"). Mutation: never append to `overridden` →
        empty list."""
        self.full_fixture()
        self.run_cli("--apply")
        files = mig.read_state(self.root).annotations
        rempli: list = []
        self._apply({("symbol", self.UNANNOTATED): dict(self.NULL_ROW, purpose="P1")},
                    files, rempli)
        self.assertEqual([], rempli, "a field filled from NULL was reported as replaced")
        remplace: list = []
        self._apply({("symbol", self.UNANNOTATED): dict(self.NULL_ROW, purpose="P2")},
                    files, remplace)
        self.assertEqual([f"(symbol, {self.UNANNOTATED}) purpose 'P1' -> 'P2'"], remplace)
        retire: list = []
        self._apply({("symbol", self.UNANNOTATED): dict(self.NULL_ROW)}, files, retire)
        self.assertEqual([f"(symbol, {self.UNANNOTATED}) purpose 'P2' -> None"], retire)
        # ARMED: the stored FILE-owned purpose is made stale first, so the merge
        # (the file's value) DIFFERS from the store and the row IS rewritten —
        # otherwise `merged == before` would skip it and this arm prove nothing.
        with self.open_db() as conn:
            conn.execute("UPDATE annotations SET purpose = 'stale' WHERE scope = "
                         "'symbol' AND key = ?", (self.FILE_OWNED,))
            conn.commit()
        fichier: list = []
        self.assertEqual((1, 0), self._apply(
            {("symbol", self.FILE_OWNED): dict(self.NULL_ROW, purpose="log")},
            files, fichier), "fixture not armed: the file-owned row was not rewritten")
        self.assertEqual([], fichier, "a FILE-owned field was reported as the journal's")
        self.assertEqual("entry point of alpha",
                         self._annotation("symbol", self.FILE_OWNED)["purpose"])

    def test_the_overridden_note_shows_ten_then_counts_the_rest(self):
        self.assertIsNone(mig._overridden_note([]))
        items = [f"(symbol, {n}) purpose 'a' -> 'b'" for n in range(12)]
        note = mig._overridden_note(items)
        self.assertTrue(note.startswith("replaced by the journal's last value: "), note)
        for shown in items[:10]:
            self.assertIn(shown, note)
        self.assertNotIn(items[10], note)
        self.assertIn("… 2 more", note)
        self.assertNotIn("more", mig._overridden_note(items[:10]))

    def test_a_logged_retraction_writes_the_null_row(self):
        """exec-critic BLOQUANT — `retire` KEEPS the row with NULL fields; the
        replay of the same retraction must write that row, and only once."""
        self.full_fixture()
        self.run_cli("--apply")
        replayed = {("symbol", self.UNANNOTATED): dict(self.NULL_ROW)}
        self.assertEqual((1, 0), self._apply(replayed, {}))
        self.assertEqual(self.NULL_ROW, self._annotation("symbol", self.UNANNOTATED))
        self.assertEqual((0, 0), self._apply(replayed, {}),
                         "the NULL row was rewritten by a second call")

    def test_a_fresh_apply_replays_a_retraction_and_verifies(self):
        """The machine that never saw the annotation: annotate then retract are
        both in the log, `--apply` builds the store, `--verify` exits 0. Before,
        no row was written and `--verify` failed forever (log NULLs vs DB None)."""
        self.full_fixture()
        self._log_line("symbol", self.UNANNOTATED, "purpose", "posé puis retiré")
        self._log_line("symbol", self.UNANNOTATED, "purpose", None)
        self.run_cli("--apply")
        self.assertEqual(self.NULL_ROW, self._annotation("symbol", self.UNANNOTATED))
        self.run_cli("--verify")

    def test_a_replayed_symbol_purpose_is_searchable(self):
        """`write_annotation` keeps `symbols_fts` in step; so does the replay."""
        self.full_fixture()
        self.run_cli("--apply")
        with self.open_db() as conn:
            if not mig._table_exists(conn, "symbols_fts"):
                self.skipTest("FTS5 absent from this interpreter's sqlite3")
        self._apply({("symbol", self.UNANNOTATED): {
            "purpose": "quetzalcoatl", "role": None, "owner": None}})
        with self.open_db() as conn:
            rows = conn.execute("SELECT rowid FROM symbols_fts WHERE symbols_fts "
                                "MATCH ?", ("quetzalcoatl",)).fetchall()
        self.assertEqual([int(self.UNANNOTATED)], [r[0] for r in rows])


class StalenessTests(_Case):
    """Case 12 — the DB is advisory: a generation gap is said out loud."""

    def test_verify_fails_loudly_when_the_files_moved_on(self):
        self.full_fixture()
        self.run_cli("--apply")
        self.full_fixture(sha=SHA_NEXT)  # build_index ran again; the DB did not

        out = self.run_cli("--verify", expect=1)
        self.assertIn(mig.STALE_MARKER, out)
        self.assertIn(SHA, out)
        self.assertIn(SHA_NEXT, out)

    def test_check_says_stale_without_failing_and_resync_clears_it(self):
        self.full_fixture()
        self.run_cli("--apply")
        self.full_fixture(sha=SHA_NEXT)

        self.assertIn(mig.STALE_MARKER, self.run_cli("--check"))
        self.run_cli("--resync")
        self.assertEqual(SHA_NEXT, self.meta()["built_at_sha"])
        self.assertNotIn(mig.STALE_MARKER, self.run_cli("--check"))
        self.assertIn("verify       OK", self.run_cli("--verify"))


class HomonymTests(_Case):
    """Case 13 — several symbols of the same name AND kind in ONE file.

    THE REPRODUCTION ARM of the measured defect: schema v1's
    UNIQUE(path, name, kind) refused a real consumer index outright, so its
    committed DB could no longer be resynced at all. The files are legitimate;
    the schema could not represent them.
    """

    def test_three_homonyms_migrate_and_coexist_with_distinct_ids(self):
        self.full_fixture(symbols=FIXTURE_HOM)
        out = self.run_cli("--apply")

        rows = self.symbols_by_id()
        self.assertEqual(
            [(11, 10, 0), (12, 20, 1), (13, 30, 2)],
            [(i, rows[i]["start"], rows[i]["ordinal"]) for i in HOM_IDS],
            "the three homonyms did not survive as three distinct symbols")
        for i in HOM_IDS:
            self.assertEqual((HOM_PATH, HOM_NAME, HOM_KIND),
                             (rows[i]["path"], rows[i]["name"], rows[i]["kind"]))
        self.assertEqual(LIVE + 3 + TOMBSTONES, self.table_counts()["symbols"])
        self.assertIn("homonyms          1  identities carrying 3 symbols", out)

        # The refusal was on --resync, so that is the flag that must come back.
        self.assertNotIn("REFUSED", self.run_cli("--resync"))
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_the_ordinal_follows_the_start_order_not_the_id_order(self):
        """Non-vacuity of the ordinal: it is assigned by LINE, not by SYM-ID.

        The ids are handed out in DESCENDING line order here, so an ordinal that
        merely counted ids would come out reversed.
        """
        self.full_fixture(symbols=FIXTURE + homonyms(starts=(30, 20, 10)))
        self.run_cli("--apply")
        rows = self.symbols_by_id()
        self.assertEqual([(11, 30, 2), (12, 20, 1), (13, 10, 0)],
                         [(i, rows[i]["start"], rows[i]["ordinal"]) for i in HOM_IDS])

    def test_a_healthy_index_without_homonyms_says_nothing_about_them(self):
        self.full_fixture()
        self.assertNotIn("homonyms", self.run_cli("--check"))


class HomonymStabilityTests(_Case):
    """Case 13b — the property that protects annotations and past sessions.

    The identity key holds the ordinal and NOT the start line, so code moving
    down a file must not renumber anything. If the line were in the key, every
    SYM-ID below an inserted function would change and every `SYM-NNNN` written
    in a past session would point at the wrong symbol.
    """

    def test_a_rebuild_that_touches_nothing_leaves_the_homonym_ids_alone(self):
        self.full_fixture(symbols=FIXTURE_HOM)
        self.run_cli("--apply")
        before = self.ordinals()

        # build_index ran again over an untouched tree: a new generation stamp,
        # the same symbols.
        self.full_fixture(symbols=FIXTURE_HOM, sha=SHA_NEXT)
        self.run_cli("--resync")

        self.assertEqual(before, self.ordinals(), "a no-op rebuild moved an identity")
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_shifting_every_homonym_down_the_file_moves_no_id_and_no_ordinal(self):
        """The load-bearing case: the lines all change, the relative order does not."""
        self.full_fixture(symbols=FIXTURE_HOM)
        self.run_cli("--apply")
        keys_before = mig.read_state(self.root).by_key()

        # 200 lines of new code inserted above the three blocks.
        shifted = FIXTURE + homonyms(starts=tuple(s + 200 for s in HOM_STARTS))
        self.full_fixture(symbols=shifted, sha=SHA_NEXT)
        self.run_cli("--resync")

        rows = self.symbols_by_id()
        self.assertEqual([(11, 210, 0), (12, 220, 1), (13, 230, 2)],
                         [(i, rows[i]["start"], rows[i]["ordinal"]) for i in HOM_IDS],
                         "a pure line shift renumbered the homonyms")
        self.assertEqual(keys_before, mig.read_state(self.root).by_key(),
                         "the identity key moved when only the lines moved — the "
                         "start line has leaked into the key")
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_the_identity_key_carries_the_ordinal_and_never_the_line(self):
        self.full_fixture(symbols=FIXTURE_HOM)
        keys = mig.read_state(self.root).by_key()
        self.assertEqual({11: 0, 12: 1, 13: 2},
                         {sym_id: key[3] for key, sym_id in keys.items()
                          if sym_id in HOM_IDS})
        for key in keys:
            self.assertEqual(4, len(key), "the identity key changed arity")
            self.assertNotIn(key[3], HOM_STARTS[1:],
                             "a start line appears where the ordinal belongs")


class HomonymAnnotationTests(_Case):
    """Case 13c — the point of the whole exercise: an annotation must stay put.

    A purpose written against the MIDDLE homonym must never drift onto one of its
    neighbours. Annotations are keyed by SYM-ID, so this is what proves the
    disambiguation actually buys something.
    """

    def _fixture_with_annotated_middle(self, starts: Sequence[int] = HOM_STARTS
                                       ) -> list[dict]:
        return FIXTURE + homonyms(starts=starts,
                                  purposes=("", MIDDLE_PURPOSE, ""))

    def test_an_annotation_stays_on_its_own_homonym_across_a_resync(self):
        self.full_fixture(symbols=self._fixture_with_annotated_middle())
        self.run_cli("--apply")

        with self.open_db() as conn:
            stored = mig._fetch_annotations(conn)
        self.assertEqual(MIDDLE_PURPOSE, stored[("symbol", "12")]["purpose"])
        self.assertNotIn(("symbol", "11"), stored, "the annotation spread to a neighbour")
        self.assertNotIn(("symbol", "13"), stored, "the annotation spread to a neighbour")

        # The blocks move down the file; the annotation must follow SYM-012.
        self.full_fixture(symbols=self._fixture_with_annotated_middle(
            starts=tuple(s + 200 for s in HOM_STARTS)), sha=SHA_NEXT)
        self.run_cli("--resync")

        with self.open_db() as conn:
            after = mig._fetch_annotations(conn)
        self.assertEqual(MIDDLE_PURPOSE, after[("symbol", "12")]["purpose"],
                         "the annotation left the symbol it was written for")
        self.assertNotIn(("symbol", "11"), after)
        self.assertNotIn(("symbol", "13"), after)
        self.assertEqual(220, self.symbols_by_id()[12]["start"])

    def test_the_annotations_log_ties_the_purpose_to_the_middle_id_alone(self):
        self.full_fixture(symbols=self._fixture_with_annotated_middle())
        self.run_cli("--apply")
        replayed = mig.replay_log(mig.read_log(mig.log_path(self.root)))
        self.assertEqual(MIDDLE_PURPOSE, replayed[("symbol", "12")]["purpose"])
        self.assertEqual(
            [("symbol", "12")],
            [k for k, v in replayed.items() if v["purpose"] == MIDDLE_PURPOSE],
            "the replayable journal cannot tell the homonyms apart")

    def test_the_search_index_points_the_purpose_at_the_right_homonym(self):
        if not mig.fts_probe():
            self.skipTest("this interpreter's sqlite3 has no FTS5")
        self.full_fixture(symbols=self._fixture_with_annotated_middle())
        self.run_cli("--apply")
        with self.open_db() as conn:
            hits = conn.execute("SELECT rowid FROM symbols_fts"
                                " WHERE symbols_fts MATCH 'fill'").fetchall()
        self.assertEqual([12], [r["rowid"] for r in hits])


class IrreducibleAmbiguityTests(_Case):
    """Case 13d — the refusal SURVIVES where no ordering can help, and says what to do."""

    def _twins(self) -> list[dict]:
        """Two live rows identical down to the start line — a contradictory index."""
        return FIXTURE + [
            sym(11, HOM_PATH, HOM_NAME, kind=HOM_KIND, start=10, end=12),
            sym(12, HOM_PATH, HOM_NAME, kind=HOM_KIND, start=10, end=12),
        ]

    def test_two_live_rows_at_the_same_start_line_are_refused_on_every_flag(self):
        self.full_fixture(symbols=self._twins())
        for flag in ("--check", "--apply"):
            with self.subTest(flag=flag):
                out = self.run_cli(flag, expect=1)
                self.assertIn("REFUSED", out)
                self.assertIn("same line", out)
                self.assert_no_db()

    def test_the_refusal_names_the_symbols_the_line_and_the_next_step(self):
        self.full_fixture(symbols=self._twins())
        out = self.run_cli("--apply", expect=1)
        self.assertIn(f"{HOM_PATH} {HOM_NAME} {HOM_KIND}", out)
        self.assertIn("line 10", out)
        self.assertIn(bi.sid(11), out)
        self.assertIn(bi.sid(12), out)
        self.assertIn("build_index.py --full", out)
        self.assertIn("nothing was written", out.lower())
        # ET LE REFUS N'ACCUSE PLUS L'EXTRACTEUR (T-00000609). Il affirmait
        # « not a legitimate pair of homonyms » et envoyait le lecteur chercher
        # un symbole émis deux fois. Reproduit en 46 octets : `ctags` sur
        # `class A{f(){}}class B{f(){}}` émet DEUX tags `f` scopés A et B — deux
        # homonymes sur une même ligne sont LÉGITIMES en JavaScript, et un
        # bundle minifié en met des centaines sur une seule. Le refus reste,
        # puisque l'ordinal ne peut pas les départager ; ce qui change est ce
        # qu'il en DIT et la première piste qu'il donne.
        self.assertNotIn("not a legitimate pair of homonyms", out)
        self.assertIn("NOT NECESSARILY AN EXTRACTOR BUG", out)
        self.assertIn("bundle", out.lower())

    def test_the_refusal_does_not_fire_on_legitimate_homonyms(self):
        """Non-vacuity in the other direction: the guard must not be a blanket no."""
        self.full_fixture(symbols=FIXTURE_HOM)
        self.assertNotIn("REFUSED", self.run_cli("--check"))


class SchemaMigrationTests(_Case):
    """Case 14 — the stores that already exist must reach the current version
    without loss.

    The chosen path is an IN-PLACE upgrade: additive DDL, so every SYM-ID,
    annotation, edge, journal row and tombstone survives and
    `annotations_log.jsonl` needs no replay. Re-creating the store would have
    worked too — the DB is advisory — but it would have thrown away nothing for
    no reason.

    RE-CALIBRATED FOR v3 (T-00000377): the rungs are climbed one at a time, so a
    v1 store now reaches v3 in a SINGLE `--resync` and the upgrade line names
    both ends of the climb, not the first rung.
    """

    def test_a_v1_store_is_upgraded_in_place_to_v1_to_v3_keeping_every_id_and_annotation(self):
        self.full_fixture()
        self.seed_v1_db()
        self.assertEqual("1", self.meta()["schema_version"], "fixture is not v1")
        ids_before = set(self.symbols_by_id())

        # The files now carry the homonyms a v1 store could never have held.
        self.full_fixture(symbols=FIXTURE_HOM, sha=SHA_NEXT)
        out = self.run_cli("--resync")

        self.assertIn("MIGRATION: schema upgraded in place v1 -> v3", out)
        self.assertIn("body_sha", self.symbol_columns(),
                      "the v2 -> v3 rung did not run on the way")
        self.assertEqual(str(mig.SCHEMA_VERSION), self.meta()["schema_version"])
        rows = self.symbols_by_id()
        self.assertTrue(ids_before <= set(rows), "the upgrade dropped a SYM-ID")
        self.assertTrue(rows[7]["deleted"], "the upgrade lost a tombstone")
        self.assertEqual([0, 1, 2], [rows[i]["ordinal"] for i in HOM_IDS])

        with self.open_db() as conn:
            stored = mig._fetch_annotations(conn)
        self.assertEqual(AUTHORED_PURPOSE, stored[AUTHORED_KEY]["purpose"],
                         "the upgrade destroyed an annotation no file could restore")
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_the_upgrade_drops_the_v1_index_instead_of_leaving_it_beside(self):
        """The old 3-column key is what refuses the homonyms — it must GO."""
        self.full_fixture()
        self.seed_v1_db()
        with self.open_db() as conn:
            self.assertTrue(mig._table_exists(conn, mig.LEGACY_LIVE_KEY_INDEX))

        self.run_cli("--resync")

        with self.open_db() as conn:
            self.assertFalse(mig._table_exists(conn, mig.LEGACY_LIVE_KEY_INDEX),
                             "the v1 identity index survived the upgrade")
            self.assertTrue(mig._table_exists(conn, mig.LIVE_KEY_INDEX))

    def test_a_v1_store_is_named_by_check_and_not_written_to(self):
        self.full_fixture()
        self.seed_v1_db()
        before = self.digest(mig.DB_NAME)
        out = self.run_cli("--check")
        self.assertIn(f"schema       v1 in the store, v{mig.SCHEMA_VERSION} in this kit",
                      out)
        self.assertIn("--resync would upgrade it IN PLACE", out)
        self.assertEqual(before, self.digest(mig.DB_NAME), "--check wrote to the store")

    def test_verify_on_a_v1_store_reports_it_instead_of_crashing(self):
        self.full_fixture()
        self.seed_v1_db()
        out = self.run_cli("--verify", expect=1)
        self.assertIn("meta.schema_version is '1'", out)
        self.assertIn("run --resync", out)
        self.assertIn(mig.LEGACY_LIVE_KEY_INDEX, out)

    def test_a_store_from_a_newer_kit_is_refused_and_left_untouched(self):
        self.full_fixture()
        self.run_cli("--apply")
        self.set_meta("schema_version", "99")
        before = self.digest(mig.DB_NAME)

        out = self.run_cli("--resync", expect=1)

        self.assertIn("declares schema v99", out)
        self.assertIn("NEWER kit", out)
        self.assertEqual(before, self.digest(mig.DB_NAME),
                         "a store from a newer kit was written to anyway")

    def test_an_unversioned_store_is_refused_rather_than_assumed_to_be_v1(self):
        self.full_fixture()
        self.seed_v1_db()
        conn = mig.connect(mig.db_path(self.root))
        try:
            conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
        finally:
            conn.close()
        before = self.digest(mig.DB_NAME)

        out = self.run_cli("--resync", expect=1)

        self.assertIn("declares no readable meta.schema_version", out)
        self.assertIn("cannot be upgraded safely", out)
        self.assertIn(mig.LOG_NAME, out, "the refusal does not say what replays")
        self.assertEqual(before, self.digest(mig.DB_NAME))

    def test_a_fresh_store_and_an_upgraded_one_have_the_same_column_order(self):
        """Same version, same shape — or two projects diff for no reason."""
        self.full_fixture()
        self.seed_v1_db()
        self.run_cli("--resync")
        with self.open_db() as conn:
            upgraded = [r[1] for r in conn.execute("PRAGMA table_info(symbols)")]

        fresh = self._store_vide(self.root / "fresh.db")
        conn = mig.connect(fresh)
        try:
            mig.ensure_schema(conn)
            created = [r[1] for r in conn.execute("PRAGMA table_info(symbols)")]
        finally:
            conn.close()
        self.assertEqual(created, upgraded)


# --- T-00000377: schema v3, `body_sha`, and the lateral it comes from -------
class BodyShaSchemaTests(_Case):
    """v2 -> v3, and the two things the new column must not break."""

    def test_a_v2_store_is_upgraded_in_place_and_keeps_every_id_and_annotation(self):
        self.full_fixture()
        self.seed_v2_db()
        self.assertEqual("2", self.meta()["schema_version"], "fixture is not v2")
        self.assertNotIn("body_sha", self.symbol_columns(), "fixture is already v3")
        ids_before = set(self.symbols_by_id())
        edges_before = self.table_counts()["edges"]

        out = self.run_cli("--resync")

        self.assertIn("MIGRATION: schema upgraded in place v2 -> v3", out)
        self.assertEqual(str(mig.SCHEMA_VERSION), self.meta()["schema_version"])
        self.assertIn("body_sha", self.symbol_columns())
        rows = self.symbols_by_id()
        self.assertTrue(ids_before <= set(rows), "the upgrade dropped a SYM-ID")
        self.assertTrue(rows[7]["deleted"], "the upgrade lost a tombstone")
        self.assertEqual(edges_before, self.table_counts()["edges"])
        with self.open_db() as conn:
            stored = mig._fetch_annotations(conn)
        self.assertEqual(AUTHORED_PURPOSE, stored[AUTHORED_KEY]["purpose"],
                         "the upgrade destroyed an annotation no file could restore")
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_verify_on_v2_reports_the_schema_gap_instead_of_raising(self):
        """↯ C4 — the guarded SELECT is what lets the nudge be PRINTED.

        An unguarded `SELECT body_sha` would raise OperationalError on the way to
        saying the store is a version behind: the report would die of the very
        condition it exists to report.
        """
        self.full_fixture()
        self.seed_v2_db()
        out = self.run_cli("--verify", expect=1)  # a raise would not be exit 1
        self.assertIn("meta.schema_version is '2'", out)
        self.assertIn("run --resync", out)
        # And the read itself survives the missing column, which is the mechanism.
        self.assertTrue(all(s["body_sha"] is None
                            for s in self.symbols_by_id().values()))

    def test_a_v3_store_is_refused_by_a_kit_that_declares_v2(self):
        """The other direction: a kit that went BACKWARDS reads nothing."""
        self.full_fixture()
        self.run_cli("--apply")
        before = self.digest(mig.DB_NAME)
        with kit_at_schema(2):
            out = self.run_cli("--resync", expect=1)
        self.assertIn("declares schema v3", out)
        self.assertIn("NEWER kit", out)
        self.assertEqual(before, self.digest(mig.DB_NAME),
                         "a store from a newer kit was written to anyway")

    def test_apply_then_verify_is_green_with_a_body_sha_on_every_live_symbol(self):
        self.full_fixture()
        published = self.write_bodies()
        self.run_cli("--apply")
        stored = {i: s["body_sha"] for i, s in self.symbols_by_id().items()
                  if not s["deleted"]}
        self.assertEqual(len(published["bodies"]), len(stored),
                         "the arm is vacuous — the column did not get populated")
        self.assertTrue(all(stored.values()))
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_verify_names_a_body_sha_the_store_lost(self):
        """The armed control of the `verify()` edit (↯ C14).

        Before it, `--verify` compared identity, counts and annotations and no
        symbol FIELD at all — so an entirely NULL column came back green. This is
        the case that must now be RED.
        """
        self.full_fixture()
        self.write_bodies()
        self.run_cli("--apply")
        self.assertIn("verify       OK", self.run_cli("--verify"))
        conn = mig.connect(mig.db_path(self.root))
        try:
            conn.execute("UPDATE symbols SET body_sha = NULL")
        finally:
            conn.close()

        out = self.run_cli("--verify", expect=1)

        self.assertIn("body_sha diverges", out)
        self.assertIn("--resync", out)

    def test_resync_with_the_lateral_ABSENT_writes_zero_symbol_rows(self):
        """↯ C29/C42 — not knowing does not authorise erasing.

        The store holds REAL hashes and the lateral is gone, so `read_state`
        carries None for every symbol. Without the fusion in `write_state` every
        row would compare unequal and the whole store — 274 Ko on this repo —
        would be rewritten at every resync, ending the stable-bytes property.
        """
        self.full_fixture()
        self.write_bodies()
        self.run_cli("--apply")
        stored = {i: s["body_sha"] for i, s in self.symbols_by_id().items()
                  if not s["deleted"]}
        self.assertTrue(stored and all(stored.values()),
                        "the arm is vacuous — the store holds no hash to lose")

        (self.idx / bi.BODIES_NAME).unlink()

        counts, state = self.resync_counts()
        self.assertIsNotNone(state.bodies_note, "the absence was not detected")
        self.assertTrue(all(s["body_sha"] is None for s in state.live),
                        "the arm is vacuous — the files still carry the hashes")
        self.assertEqual(0, counts["symbols"])

    def test_resync_with_the_lateral_DISAGREEING_writes_zero_symbol_rows(self):
        """Same property, the OTHER unusable shape: a map from another build."""
        self.full_fixture()
        self.write_bodies()
        self.run_cli("--apply")
        stored = {i: s["body_sha"] for i, s in self.symbols_by_id().items()
                  if not s["deleted"]}
        self.assertTrue(stored and all(stored.values()),
                        "the arm is vacuous — the store holds no hash to lose")

        self.write_bodies(generation="deadbee")

        counts, state = self.resync_counts()
        self.assertIsNotNone(state.bodies_note, "the disagreement was not detected")
        self.assertEqual(0, counts["symbols"])

    def test_an_unusable_lateral_is_NAMED_in_every_report(self):
        """A field declared non-comparable must not be a silence."""
        self.full_fixture()
        self.run_cli("--apply")  # no lateral at all
        for flag in ("--check", "--verify", "--resync"):
            with self.subTest(flag=flag):
                self.assertIn(bi.BODIES_NAME, self.run_cli(flag))

    def test_a_usable_lateral_prints_no_such_note(self):
        """Non-vacuity of the line above: it must not appear on a healthy tree."""
        self.full_fixture()
        self.write_bodies()
        self.run_cli("--apply")
        self.assertNotIn(bi.BODIES_NAME, self.run_cli("--verify"))


CSS_FILE = "src/styles/theme.css"
CSS_IDS = (21, 22, 23, 24, 25)


def css_symbols() -> list[dict]:
    """The four CSS kinds the builder emits, with a HOMONYM pair on `--brand`.

    The pair is the point, not decoration: a design system declares the same
    custom property twice — once in the light block, once in the dark one — so
    `--brand` is exactly the shape that made schema v1 refuse a real consumer
    index outright. Here it also proves the ordinals survive the round trip for a
    vocabulary nobody thought about when the identity key was designed.
    """
    return [
        sym(21, CSS_FILE, "--brand", kind=bi.CSS_VAR_KIND, start=2, end=2),
        sym(22, CSS_FILE, "--brand", kind=bi.CSS_VAR_KIND, start=40, end=40),
        sym(23, CSS_FILE, "fade-in", kind=bi.CSS_KEYFRAMES_KIND, start=60, end=64),
        sym(24, CSS_FILE, "tokens", kind=bi.CSS_LAYER_KIND, start=1, end=1),
        sym(25, CSS_FILE, ".card", kind=bi.CSS_SELECTOR_KIND, start=70, end=72),
    ]


class StylesheetRoundTripTests(_Case):
    """T-00000144 — the CSS vocabulary crosses the store and comes back INTACT.

    WHY THIS TEST IS THE FIX, AND WHY IT LOOKED UNNECESSARY. The `kind` column is
    `TEXT` and therefore agnostic: the CSS kinds round-trip today by ACCIDENT, not
    by contract, and this whole suite carried no mention of any of them — measured
    before writing this class, zero occurrences of `cssvar`, `keyframes`, `layer`
    or `selector`. A vocabulary that works by accident is a vocabulary the next
    schema change may drop without a single test going red; nothing here is
    "already covered by the generic case", because the generic case only ever
    exercised `function`, `class` and `constant`.

    It is also where the two features MEET: stylesheet extraction (T-00000102)
    and the v2 identity key `(path, name, kind, ordinal)` (T-00000107) were built
    independently, and their intersection — a homonym pair whose kind is a CSS
    kind — was never once exercised end to end.
    """

    def test_every_css_kind_survives_apply_and_verify(self):
        self.full_fixture(symbols=FIXTURE + css_symbols())
        self.run_cli("--apply")

        rows = self.symbols_by_id()
        self.assertEqual(
            [(21, "--brand", bi.CSS_VAR_KIND),
             (22, "--brand", bi.CSS_VAR_KIND),
             (23, "fade-in", bi.CSS_KEYFRAMES_KIND),
             (24, "tokens", bi.CSS_LAYER_KIND),
             (25, ".card", bi.CSS_SELECTOR_KIND)],
            [(i, rows[i]["name"], rows[i]["kind"]) for i in CSS_IDS],
            "a CSS kind or name did not survive the migration verbatim")
        # NAMES ARE ASSERTED CHARACTER FOR CHARACTER on purpose: `--brand` opens
        # with two dashes and `.card` with a dot, and any writer or parser that
        # trimmed leading punctuation would still produce plausible-looking rows.
        self.assertEqual(LIVE + 5 + TOMBSTONES, self.table_counts()["symbols"])
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_the_homonym_ordinals_hold_for_a_css_kind_too(self):
        """The light/dark `--brand` pair keeps ordinals 0 and 1, ordered by LINE.

        Paired with the arm below, which reverses the line order against the id
        order: an implementation that numbered by SYM-ID instead of by start line
        passes one of the two and fails the other, so neither is vacuous alone.
        """
        self.full_fixture(symbols=FIXTURE + css_symbols())
        self.run_cli("--apply")
        rows = self.symbols_by_id()
        self.assertEqual([(21, 2, 0), (22, 40, 1)],
                         [(i, rows[i]["start"], rows[i]["ordinal"]) for i in (21, 22)])

    def test_the_css_ordinal_follows_the_line_not_the_id(self):
        """The same pair with the lines REVERSED against the id order."""
        reversed_pair = [
            sym(21, CSS_FILE, "--brand", kind=bi.CSS_VAR_KIND, start=40, end=40),
            sym(22, CSS_FILE, "--brand", kind=bi.CSS_VAR_KIND, start=2, end=2),
        ]
        self.full_fixture(symbols=FIXTURE + reversed_pair)
        self.run_cli("--apply")
        rows = self.symbols_by_id()
        self.assertEqual([(21, 40, 1), (22, 2, 0)],
                         [(i, rows[i]["start"], rows[i]["ordinal"]) for i in (21, 22)])

    def test_a_resync_leaves_the_css_identities_alone(self):
        """THE PROPERTY THAT PROTECTS ANNOTATIONS, on the CSS vocabulary.

        A `:: purpose` authored against `--brand` ordinal 1 must still point at
        the dark declaration after a rebuild that touched nothing. If the ordinal
        moved, every annotation on a design-system token would silently retarget —
        and a token file is exactly where a team writes the most annotations.
        """
        self.full_fixture(symbols=FIXTURE + css_symbols())
        self.run_cli("--apply")
        before = {i: (self.symbols_by_id()[i]["ordinal"]) for i in (21, 22)}

        self.full_fixture(symbols=FIXTURE + css_symbols(), sha=SHA_NEXT)
        self.assertNotIn("REFUSED", self.run_cli("--resync"))
        after = {i: (self.symbols_by_id()[i]["ordinal"]) for i in (21, 22)}
        self.assertEqual(before, after)
        self.assertIn("verify       OK", self.run_cli("--verify"))


#: La sonde d'I2 (T-00000770) : `migrate_index_to_db` importé depuis `.agents/bin`
#: SEUL (`-I`, ni `src/` ni le cwd sur `sys.path`), donc la couture passe par son
#: repli PAR CHEMIN. Rend le type et le message du refus.
_SONDE_I2 = r'''
import importlib.util, json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
arme = importlib.util.find_spec("cadre") is None
import migrate_index_to_db as mig
d = Path(sys.argv[2]).resolve()
tiers = d / "tiers.db"
c = sqlite3.connect(str(tiers))
c.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
c.commit()
c.close()
os.symlink(tiers, d / "index.db")
try:
    mig.connect(d / "index.db")
    refus = None
except mig.Refusal as exc:
    refus = str(exc)
print(json.dumps({"arme": arme, "refus": refus}))
'''


#: La sonde de F2 (binôme de clôture de T-00000770) : un paquet `cadre` PÉRIMÉ (son
#: `cadre.ledger.store` ne porte que `connect`) en tête de `sys.path`, le paquet du clone
#: complet (vendor ou `src`) — `connect` retente PAR CHEMIN ; si la copie par chemin échoue aussi, le
#: `Refusal` nomme le module périmé (`__name__` ET `__file__`).
_SONDE_F2 = r'''
import json, sys
from pathlib import Path
faux, bin_, d = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(faux))
import cadre.ledger.store as perime
arme = hasattr(perime, "connect") and not hasattr(perime, "ouvrir_sans_suivre")
sys.path.insert(1, str(bin_))
import migrate_index_to_db as mig
(d / "index.db").touch()
rapport = {"arme": arme, "perime": [perime.__name__, perime.__file__]}
try:
    mig.connect(d / "index.db").close()
    rapport["ok"] = [True, mig._MODULES_CADRE["ledger.store"].__file__]
except mig.Refusal as exc:
    rapport["ok"] = [False, str(exc)]
mig._MODULES_CADRE.clear()
mig._SRC_CADRE = d / "vide"
try:
    mig.connect(d / "index.db").close()
    rapport["echec"] = None
except mig.Refusal as exc:
    rapport["echec"] = str(exc)
print(json.dumps(rapport))
'''


class CoutureLedgerStorePerimeeTests(_Case):
    def test_un_paquet_cadre_perime_est_rattrape_par_la_copie_par_chemin_t770(self):
        """F2 — un paquet `cadre` installé antérieur à T-00000770 (sans la primitive) ne coupe pas
        `connect` quand le paquet du clone est là (`vendor_paths` : `.agents/vendor/cadre`, sinon
        `src/cadre`) : la couture retente PAR CHEMIN, ouvre par SA copie de `ledger/store.py` ; si
        elle échoue AUSSI, `Refusal` qui nomme le module périmé (`__name__`, `__file__`). Mord : repli ôté."""
        faux = self.root / "faux" / "cadre" / "ledger"
        faux.mkdir(parents=True)
        (faux.parent / "__init__.py").write_text("", encoding="utf-8")
        (faux / "__init__.py").write_text("", encoding="utf-8")
        (faux / "store.py").write_text(
            "import sqlite3\n\n\ndef connect(chemin, **_):\n"
            "    return sqlite3.connect(str(chemin))\n", encoding="utf-8")
        d = self.root / "f2"
        d.mkdir()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "CADRE_STATE_DIR": str(self.root / "f2-state"),
               "CADRE_PROJECT_ROOT": str(self.root / "f2-racine"),
               "AGENTS_EVENTS_DIR": str(self.root / "f2-events")}
        bin_ = Path(mig.__file__).resolve().parent
        fini = subprocess.run(
            [sys.executable, "-I", "-c", _SONDE_F2, str(self.root / "faux"), str(bin_), str(d)],
            cwd=str(d), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        rapport = json.loads(fini.stdout.strip().splitlines()[-1])
        self.assertTrue(rapport["arme"], "banc non armé : le paquet périmé n'est pas importé")
        ouvert, detail = rapport["ok"]
        self.assertTrue(ouvert, detail)
        self.assertEqual(detail, str(vendor_paths.exiger(bin_.parents[1], "cadre") / "ledger" / "store.py"))
        nom_perime, fichier_perime = rapport["perime"]
        self.assertIsNotNone(rapport["echec"], "connect a ouvert sans primitive")
        self.assertIn(nom_perime, rapport["echec"])
        self.assertIn(fichier_perime, rapport["echec"])


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (R3 de T-00000759)")
class LinkRefusalTests(_Case):
    """T-00000770 — `connect` ouvre l'index SANS SUIVRE, par la primitive de
    `cadre.ledger.store` (couture `_cadre_module`), et ne CRÉE plus rien : un lien
    à l'emplacement, ou un store absent, est un `Refusal` nommé."""

    def test_connect_refuse_un_lien_vers_un_index_etranger_t770(self):
        """I1 — `connect(<lien vers un index étranger>)` : `Refusal` nommé (« lien
        symbolique »), le fichier étranger inchangé. BASE suivait le lien et
        rendait une connexion sur l'index d'un autre projet. Mord : Mj."""
        dehors = self.root / "dehors"
        dehors.mkdir()
        tiers = dehors / "tiers.db"
        conn = sqlite3.connect(str(tiers))
        conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()
        avant = hashlib.sha256(tiers.read_bytes()).hexdigest()
        lien = self.root / "index.db"
        os.symlink(tiers, lien)
        with self.assertRaises(mig.Refusal) as ctx:
            mig.connect(lien)
        self.assertIn("lien symbolique", str(ctx.exception))
        self.assertEqual(hashlib.sha256(tiers.read_bytes()).hexdigest(), avant)
        self.assertEqual(sorted(p.name for p in dehors.iterdir()), ["tiers.db"])

    def test_connect_ne_cree_pas_un_store_absent_t770(self):
        """Ik — `connect(<chemin jamais existant>)` : `Refusal` « … n'existe pas —
        rien n'a été créé », le chemin toujours absent. BASE : `sqlite3.connect`
        CRÉAIT une base vide. Mord : Mk (création implicite rétablie) — que
        `seed_v1_db` ne voit pas, d'où ce témoin."""
        jamais = self.root / "jamais" / "index.db"
        jamais.parent.mkdir()
        with self.assertRaises(mig.Refusal) as ctx:
            mig.connect(jamais)
        self.assertIn("n'existe pas — rien n'a été créé", str(ctx.exception))
        self.assertFalse(jamais.exists(), "connect a créé le store")

    def test_une_couture_introuvable_est_un_Refusal_qui_nomme_le_module_t770(self):
        """A-C1 — `cadre.ledger.store` introuvable par les DEUX branches (paquet
        masqué, repli par chemin pointé sur un dossier VIDE, mémo vidé) : `connect`
        lève un `Refusal` qui nomme `cadre.ledger.store`, rien n'est créé. Rouge
        sur BASE (aucune couture : `_SRC_CADRE` absent)."""
        cible = self.root / "index.db"
        masques = {nom: None for nom in ("cadre", "cadre.ledger", "cadre.ledger.store",
                                         "cadre.workspace")}
        with mock.patch.dict(sys.modules, masques), \
                mock.patch.object(mig, "_SRC_CADRE", self.root / "cadre-absent"), \
                mock.patch.object(mig, "_MODULES_CADRE", {}):
            with self.assertRaises(mig.Refusal) as ctx:
                mig.connect(cible)
        self.assertRegex(str(ctx.exception), "cadre.ledger.store.*cadre-kit.*README du kit, § Install the core")
        self.assertFalse(cible.exists())

    def test_connect_hors_paquet_refuse_un_lien_par_la_couture_par_chemin_t770(self):
        """I2 (+ B-C1) — dans un enfant `sys.executable -I` où `cadre` est
        INTROUVABLE (armement asserté) : `mig.connect(<lien>)` lève `Refusal` dont
        le MESSAGE contient « lien symbolique » et NE contient PAS
        « cadre.ledger.store ». Le TYPE ne distingue pas un refus de lien d'une
        couture introuvable (deux `Refusal`) : seul le message le fait — c'est le
        canal par lequel Mq' (repli par chemin retiré) rougit ce témoin."""
        d = self.root / "i2"
        d.mkdir()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "CADRE_STATE_DIR": str(self.root / "i2-state"),
               "CADRE_PROJECT_ROOT": str(self.root / "i2-racine"),
               "AGENTS_EVENTS_DIR": str(self.root / "i2-events")}
        fini = subprocess.run(
            [sys.executable, "-I", "-c", _SONDE_I2, str(Path(mig.__file__).resolve().parent),
             str(d)],
            cwd=str(d), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        rapport = json.loads(fini.stdout.strip().splitlines()[-1])
        self.assertTrue(rapport["arme"], "banc non armé : `cadre` importable dans l'enfant")
        self.assertIsNotNone(rapport["refus"], "le lien a été suivi")
        self.assertIn("lien symbolique", rapport["refus"])
        self.assertNotIn("cadre.ledger.store", rapport["refus"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
