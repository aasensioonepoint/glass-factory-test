"""Tests for symbols.py -- the agent-facing query surface over index.db (v1).

THE FIXTURES ARE NOT REINVENTED. Every temp state comes from
`test_migrate_index_to_db._Case`, which builds its index with `build_index`'s OWN
writers (real ToC, real shards, real CODEBASE_INDEX.md, real INDEX_DELTA.json) and
then migrates it with the real `migrate_index_to_db` CLI. A second fixture builder
here would test this file's idea of the store instead of the store.

ARMS, NEGATIVE FIRST -- because the two ways this CLI can do real harm are both
negatives, and a suite that opens on its happy path tends to stop before them:

  1  store ABSENT      every subcommand refuses, names --apply, and CREATES NOTHING
                       (the index directory is compared byte for byte)
  2  store STALE       the banner is the FIRST line of the answer; --strict exits 3;
                       --json keeps stdout parseable and puts the verdict inside;
                       a FRESH store prints no banner at all (non-vacuity)
  3  query             --name finds / does not find / respects --limit and SAYS the
                       truncation; --kind/--module/--file; tombstones excluded
  4  edges             --callers and --callees on REAL edges, both directions;
                       an unknown SYM-ID is a refused false premise
  5  fts fallback      a store built without FTS5 answers via LIKE, says so, and
                       returns the SAME ids as the FTS5 path
  6  annotate          lands in the TABLE *and* is APPENDED to the journal (both
                       checked); a tombstone and an unknown id are refused
  7  retire            appends a retraction and removes NO journal line (the line
                       list before is a PREFIX of the line list after); the
                       annotation key survives; `migrate --verify` stays green
  8  compact           keeps every tombstone, every annotation key and every index
                       SOURCE FILE; prunes dangling edges only when asked
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import build_index as bi
import migrate_index_to_db as mig
import symbols as sym
import test_migrate_index_to_db as tmig

SHA = tmig.SHA
SHA_NEXT = tmig.SHA_NEXT
SUBCOMMANDS = ("query", "annotate", "retire", "compact")
# Arm 11 needs a REAL repository (see its header). Resolved once: a machine
# without git skips that arm and runs the other ten, rather than failing them.
GIT = shutil.which("git")
# The CLI as a SCRIPT -- the encoding arm below must cross a real process
# boundary, not the in-process `cli()` call the rest of this file uses.
SYMBOLS = Path(sym.__file__).resolve()


class _SymbolsCase(tmig._Case):
    """The migration suite's fixture, plus a driver for THIS CLI."""

    # --- run ---------------------------------------------------------------
    def run_sym(self, *argv: str, expect: int = 0) -> str:
        """stdout+stderr of one real CLI run, with the exit code asserted."""
        out, err = self.run_streams(*argv, expect=expect)
        return out + err

    def run_streams(self, *argv: str, expect: int = 0) -> tuple[str, str]:
        """The two streams kept APART -- `--json` puts them to different uses."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sym.cli([argv[0], "--root", str(self.root), *argv[1:]])
        text = out.getvalue() + err.getvalue()
        self.assertEqual(expect, code, f"output={text!r}")
        return out.getvalue(), err.getvalue()

    # --- states ------------------------------------------------------------
    def fresh_store(self) -> None:
        """A migrated store whose generation IS the files' generation."""
        self.full_fixture()
        self.run_cli("--apply")

    def stale_store(self) -> None:
        """The common case: build_index ran again, the advisory DB did not move."""
        self.fresh_store()
        self.full_fixture(sha=SHA_NEXT)

    # --- inspect -----------------------------------------------------------
    def log_lines(self) -> list[str]:
        path = mig.log_path(self.root)
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def annotations(self) -> dict:
        with self.open_db() as conn:
            return mig._fetch_annotations(conn)

    def edges(self) -> set:
        with self.open_db() as conn:
            return {(r["src_id"], r["dst_id"])
                    for r in conn.execute("SELECT src_id, dst_id FROM edges")}

    def sources(self) -> dict:
        """The index files `build_index.py` OWNS -- what no subcommand may touch.

        The annotations journal is excluded because it is this tool's one
        legitimate write target IN THIS DIRECTORY; the DB, its other target, no
        longer lives here at all (machine store, T-00000668), so it is NOT
        excluded any more — a store reappearing among the index files would be a
        write this snapshot must see. Everything else belongs to the builder, and
        a query CLI that edited a shard would be corrupting the authority to serve
        the advisory copy.
        """
        return {name: body for name, body in self.snapshot().items()
                if name != mig.LOG_NAME}

    def ids_in(self, text: str) -> list[int]:
        return [int(line.split()[0][4:]) for line in text.splitlines()
                if line.startswith("SYM-")]


# ------------------------------------------------------------------- arm 1
class AbsentStoreTests(_SymbolsCase):
    """Arm 1 -- no store at all. The one path that must not leave a file behind."""

    def test_every_subcommand_refuses_and_creates_no_database(self):
        self.full_fixture()  # index FILES exist; index.db does not
        before = self.snapshot()
        for mode in SUBCOMMANDS:
            with self.subTest(mode=mode):
                out = self.run_sym(mode, *self._args_for(mode), expect=1)
                self.assertIn("does not exist", out)
                self.assertIn("--apply", out, "the refusal must name the way out")
                self.assert_no_db()
                self.assertEqual(before, self.snapshot(),
                                 f"{mode} modified the index directory")

    def test_the_refusal_points_at_the_migration_and_at_grep(self):
        self.full_fixture()
        out = self.run_sym("query", "--name", "alpha", expect=1)
        self.assertIn("migrate_index_to_db.py --apply", out)
        self.assertIn("SYMBOLS", out, "an agent with no store still has the shards")

    def test_a_missing_store_is_never_probed_into_existence(self):
        """`sqlite3.connect()` CREATES; the freshness probe must not."""
        self.full_fixture()
        self.assertIsNone(sym.staleness(self.root))
        self.assertIsNone(mig.read_db_generation(self.root))
        self.assert_no_db()

    @staticmethod
    def _args_for(mode: str) -> tuple[str, ...]:
        return {"query": ("--name", "alpha"),
                "annotate": ("--symbol", "SYM-002", "--purpose", "x"),
                "retire": ("--symbol", "SYM-002"),
                "compact": ()}[mode]


# ------------------------------------------------------------------- arm 2
class StaleStoreTests(_SymbolsCase):
    """Arm 2 -- an advisory store a generation behind: warn loudly, or refuse."""

    def test_the_banner_is_the_first_line_of_the_answer(self):
        self.stale_store()
        out, _err = self.run_streams("query", "--name", "alpha")
        first = out.splitlines()[0]
        self.assertTrue(first.startswith(sym.WARN), f"head of output was {first!r}")
        self.assertIn("DB STALE", first)
        self.assertIn(SHA, out)
        self.assertIn(SHA_NEXT, out)
        self.assertIn("--resync", out)
        self.assertTrue(self.ids_in(out), "the warning replaced the answer")

    def test_strict_refuses_a_stale_store_with_its_own_exit_code(self):
        self.stale_store()
        out = self.run_sym("query", "--name", "alpha", "--strict",
                           expect=sym.EXIT_STALE_STRICT)
        self.assertIn("REFUSED", out)
        self.assertIn("--resync", out)
        self.assertEqual([], self.ids_in(out), "--strict answered anyway")

    def test_strict_refuses_on_every_subcommand(self):
        self.stale_store()
        for mode in SUBCOMMANDS:
            with self.subTest(mode=mode):
                args = AbsentStoreTests._args_for(mode)
                self.run_sym(mode, *args, "--strict", expect=sym.EXIT_STALE_STRICT)

    def test_json_stays_parseable_and_carries_the_verdict(self):
        self.stale_store()
        out, err = self.run_streams("query", "--name", "alpha", "--json")
        payload = json.loads(out)  # would raise if the banner had polluted stdout
        self.assertEqual(SHA, payload["stale"]["db_generation"])
        self.assertEqual(SHA_NEXT, payload["stale"]["files_generation"])
        self.assertIn("--resync", payload["stale"]["fix"])
        self.assertIn("DB STALE", err, "the banner must still be SAID, on stderr")

    def test_a_fresh_store_says_nothing_about_staleness(self):
        """Non-vacuity: the banner is a verdict, not decoration."""
        self.fresh_store()
        out, err = self.run_streams("query", "--name", "alpha")
        self.assertNotIn("DB STALE", out + err)
        self.assertNotIn(sym.WARN + " DB", out)
        self.assertEqual([1, 2, 3], self.ids_in(out))

    def test_a_resync_clears_the_banner_and_unblocks_strict(self):
        self.stale_store()
        self.run_cli("--resync")
        out, _err = self.run_streams("query", "--name", "alpha", "--strict")
        self.assertNotIn("DB STALE", out)
        self.assertEqual([1, 2, 3], self.ids_in(out))


# ------------------------------------------------------------------- arm 3
class QueryTests(_SymbolsCase):
    """Arm 3 -- finds, does not find, and never truncates in silence."""

    def setUp(self) -> None:
        super().setUp()
        self.fresh_store()

    def test_name_finds_the_matching_symbols(self):
        out, _err = self.run_streams("query", "--name", "alpha")
        self.assertEqual([1, 2, 3], self.ids_in(out))
        self.assertIn("alpha_one", out)
        self.assertIn("3 match(es)", out)

    def test_the_line_carries_id_kind_location_name_and_purpose(self):
        out, _err = self.run_streams("query", "--name", "AlphaBox")
        line = [ln for ln in out.splitlines() if ln.startswith("SYM-")][0]
        self.assertIn("SYM-003", line)
        self.assertIn("class", line)
        self.assertIn("src/alpha/two.py:1-9", line)
        self.assertIn("AlphaBox", line)
        self.assertIn(":: holds alpha state", line)

    def test_a_pattern_that_matches_nothing_answers_zero_not_an_error(self):
        out, _err = self.run_streams("query", "--name", "zzz_nothing_here")
        self.assertEqual([], self.ids_in(out))
        self.assertIn("0 match(es)", out)
        self.assertIn("no match", out)

    def test_limit_bounds_the_output_and_announces_the_truncation(self):
        out, _err = self.run_streams("query", "--name", "alpha", "--limit", "1")
        self.assertEqual(1, len(self.ids_in(out)))
        self.assertIn("TRUNCATED", out)
        self.assertIn("1 of 3", out, "the total must be named, not just the slice")
        self.assertIn("--limit", out)

    def test_an_untruncated_answer_says_nothing_about_truncation(self):
        out, _err = self.run_streams("query", "--name", "alpha", "--limit", "3")
        self.assertEqual(3, len(self.ids_in(out)))
        self.assertNotIn("TRUNCATED", out)

    def test_limit_zero_removes_the_bound(self):
        out, _err = self.run_streams("query", "--limit", "0")
        self.assertEqual(tmig.LIVE, len(self.ids_in(out)))
        self.assertNotIn("TRUNCATED", out)

    def test_kind_module_and_file_filter_as_the_index_names_them(self):
        by_kind, _ = self.run_streams("query", "--kind", "class")
        self.assertEqual([3, 5], self.ids_in(by_kind))

        # `alpha` is the module key CODEBASE_INDEX.md lists (`module_of(path)`),
        # not a path prefix -- resolving it any other way would answer nothing.
        by_module, _ = self.run_streams("query", "--module", "alpha")
        self.assertEqual([1, 2, 3], self.ids_in(by_module))

        by_file, _ = self.run_streams("query", "--file", "src/beta/one.py")
        self.assertEqual([4, 5], self.ids_in(by_file))

        by_suffix, _ = self.run_streams("query", "--file", "one.py")
        self.assertEqual([1, 2, 4, 5], self.ids_in(by_suffix))

    def test_filters_intersect_instead_of_accumulating(self):
        out, _err = self.run_streams("query", "--module", "beta", "--kind", "class")
        self.assertEqual([5], self.ids_in(out))

    def test_tombstones_are_excluded_until_they_are_asked_for(self):
        hidden, _ = self.run_streams("query", "--name", "alpha_gone")
        self.assertEqual([], self.ids_in(hidden))

        shown, _ = self.run_streams("query", "--name", "alpha_gone",
                                    "--include-deleted")
        self.assertEqual([7], self.ids_in(shown))
        self.assertIn("[DELETED]", shown)
        self.assertIn("live rows only", shown, "the forced fallback must be said")

    def test_purpose_is_searchable_and_truncated_to_the_width(self):
        out, _err = self.run_streams("query", "--purpose", "container")
        self.assertEqual([5], self.ids_in(out))

        narrow, _ = self.run_streams("query", "--name", "AlphaBox", "--width", "8")
        self.assertIn(":: holds...", narrow)
        self.assertNotIn("alpha state", narrow)

    def test_json_carries_the_machine_fields(self):
        out, _err = self.run_streams("query", "--name", "AlphaBox", "--json")
        payload = json.loads(out)
        self.assertIsNone(payload["stale"])
        self.assertEqual(1, payload["total"])
        self.assertFalse(payload["truncated"])
        row = payload["results"][0]
        self.assertEqual({"SYM-003", "class", "src/alpha/two.py", "AlphaBox",
                          "holds alpha state"},
                         {row["sym_id"], row["kind"], row["path"], row["name"],
                          row["purpose"]})


# ------------------------------------------------------------------- arm 4
class EdgeTests(_SymbolsCase):
    """Arm 4 -- the relation the shards cannot express, on the fixture's REAL edges.

    The fixture's `uses[]` are (1,2) (3,2) (4,1) (4,3) (6,5); the files store the
    forward direction only and say reverse edges are NOT stored.
    """

    def setUp(self) -> None:
        super().setUp()
        self.fresh_store()
        self.assertEqual({(1, 2), (3, 2), (4, 1), (4, 3), (6, 5)}, self.edges())

    def test_callers_walks_the_edge_backwards(self):
        out, _err = self.run_streams("query", "--callers", "SYM-002")
        self.assertEqual([1, 3], self.ids_in(out))
        self.assertIn("APPROXIMATE", out, "name-matched edges are leads, not proof")

    def test_callees_walks_the_edge_forwards(self):
        out, _err = self.run_streams("query", "--callees", "SYM-004")
        self.assertEqual([1, 3], self.ids_in(out))

    def test_a_leaf_has_no_callers_and_that_is_an_answer(self):
        out, _err = self.run_streams("query", "--callers", "SYM-006")
        self.assertEqual([], self.ids_in(out))
        self.assertIn("0 match(es)", out)

    def test_a_bare_id_and_a_padded_id_mean_the_same_symbol(self):
        for spelling in ("SYM-002", "002", "2"):
            with self.subTest(spelling=spelling):
                out, _err = self.run_streams("query", "--callers", spelling)
                self.assertEqual([1, 3], self.ids_in(out))

    def test_an_unknown_id_is_a_refused_false_premise(self):
        out = self.run_sym("query", "--callers", "SYM-999", expect=1)
        self.assertIn("no row in `symbols`", out)
        self.assertIn("SYM-999", out)

    def test_an_edge_walk_composes_with_the_other_filters(self):
        out, _err = self.run_streams("query", "--callers", "SYM-002",
                                     "--kind", "class")
        self.assertEqual([3], self.ids_in(out))


# ------------------------------------------------------------------- arm 5
class FtsFallbackTests(_SymbolsCase):
    """Arm 5 -- FTS5 when it is there, LIKE when it is not, and it SAYS which."""

    def test_a_store_built_without_fts5_answers_through_like(self):
        self.full_fixture()
        with tmig.no_fts5():
            self.run_cli("--apply")
        with self.open_db() as conn:
            self.assertFalse(mig._table_exists(conn, "symbols_fts"),
                             "the fixture failed to suppress FTS5")

        out, _err = self.run_streams("query", "--name", "alpha")
        self.assertIn("LIKE fallback", out)
        self.assertEqual([1, 2, 3], self.ids_in(out))

    def test_both_engines_return_the_same_ids(self):
        self.fresh_store()
        with_fts, _ = self.run_streams("query", "--name", "alpha")
        without, _ = self.run_streams("query", "--name", "alpha", "--no-fts")
        self.assertIn("LIKE fallback", without)
        self.assertEqual(self.ids_in(with_fts), self.ids_in(without))
        if mig.fts_probe():
            self.assertIn("fts5", with_fts)

    def test_a_zero_row_fts_match_retries_on_like_and_says_so(self):
        """FTS5 matches whole tokens: `contain*` never matches `BetaContainer`.

        Left alone that is an answer of "no such symbol", which is exactly the
        confident wrong answer this CLI exists to remove.
        """
        if not mig.fts_probe():
            self.skipTest("this interpreter's sqlite3 has no FTS5 to fall back FROM")
        self.fresh_store()
        out, _err = self.run_streams("query", "--name", "eta_one")
        self.assertEqual([4], self.ids_in(out))
        self.assertIn("retried with the LIKE substring fallback", out)

    def test_a_star_is_the_wildcard_and_an_underscore_is_literal(self):
        self.fresh_store()
        prefix, _ = self.run_streams("query", "--name", "alpha_*")
        self.assertEqual([1, 2], self.ids_in(prefix))
        literal, _ = self.run_streams("query", "--name", "alph_", "--no-fts")
        self.assertEqual([], self.ids_in(literal),
                         "`_` was treated as the LIKE single-char wildcard")


# ------------------------------------------------------------------- arm 6
class AnnotateTests(_SymbolsCase):
    """Arm 6 -- authored content lands in BOTH stores, or it is not durable."""

    def setUp(self) -> None:
        super().setUp()
        self.fresh_store()

    def test_a_symbol_purpose_reaches_the_table_and_the_journal(self):
        before = self.log_lines()
        out = self.run_sym("annotate", "--symbol", "SYM-002",
                           "--purpose", "second entry point of alpha")
        self.assertIn("1 row upserted", out)

        self.assertEqual("second entry point of alpha",
                         self.annotations()[("symbol", "2")]["purpose"])

        after = self.log_lines()
        self.assertEqual(len(before) + 1, len(after))
        entry = json.loads(after[-1])
        self.assertEqual({"scope": "symbol", "key": "2", "field": "purpose",
                          "value": "second entry point of alpha"},
                         {k: entry[k] for k in ("scope", "key", "field", "value")})
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_an_annotated_purpose_is_then_searchable(self):
        self.run_sym("annotate", "--symbol", "SYM-002",
                     "--purpose", "cactus of the second kind")
        out, _err = self.run_streams("query", "--purpose", "cactus")
        self.assertEqual([2], self.ids_in(out))

    def test_a_module_role_and_owner_reach_both_stores(self):
        before = self.log_lines()
        self.run_sym("annotate", "--module", "beta", "--role", "Edge adapters",
                     "--owner", "dev-multi")
        self.assertEqual({"purpose": None, "role": "Edge adapters",
                          "owner": "dev-multi"},
                         self.annotations()[("module", "beta")])
        fields = [json.loads(line)["field"] for line in self.log_lines()[len(before):]]
        self.assertEqual(["owner", "role"], sorted(fields))
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_an_unknown_id_is_refused_and_nothing_is_appended(self):
        before = self.log_lines()
        out = self.run_sym("annotate", "--symbol", "SYM-999", "--purpose", "x",
                           expect=1)
        self.assertIn("no row in `symbols`", out)
        self.assertEqual(before, self.log_lines())
        self.assertNotIn(("symbol", "999"), self.annotations())

    def test_a_tombstone_is_refused_and_nothing_is_appended(self):
        before = self.log_lines()
        out = self.run_sym("annotate", "--symbol", "SYM-007", "--purpose", "x",
                           expect=1)
        self.assertIn("TOMBSTONE", out)
        self.assertEqual(before, self.log_lines())

    def test_re_annotating_the_same_value_appends_nothing(self):
        self.run_sym("annotate", "--symbol", "SYM-002", "--purpose", "same words")
        mid = self.log_lines()
        out = self.run_sym("annotate", "--symbol", "SYM-002", "--purpose", "same words")
        self.assertIn("unchanged", out)
        self.assertEqual(mid, self.log_lines())

    def test_annotating_never_writes_an_index_source_file(self):
        before = self.sources()
        self.run_sym("annotate", "--symbol", "SYM-002", "--purpose", "a purpose")
        self.assertEqual(before, self.sources(),
                         "an index source file changed -- build_index.py owns those")


# ------------------------------------------------------------------- arm 7
class RetireTests(_SymbolsCase):
    """Arm 7 -- a retraction is APPOSED. The journal is never rewound."""

    def setUp(self) -> None:
        super().setUp()
        self.fresh_store()
        self.run_sym("annotate", "--symbol", "SYM-002", "--purpose", "wrong on purpose")

    def test_retire_removes_no_journal_line_and_appends_one(self):
        before = self.log_lines()
        out = self.run_sym("retire", "--symbol", "SYM-002")
        after = self.log_lines()

        self.assertEqual(before, after[:len(before)],
                         "a pre-existing journal line moved or vanished")
        self.assertEqual(len(before) + 1, len(after))
        entry = json.loads(after[-1])
        self.assertIsNone(entry["value"])
        self.assertTrue(entry["retired"])
        self.assertEqual(("symbol", "2", "purpose"),
                         (entry["scope"], entry["key"], entry["field"]))
        self.assertIn("APPENDED", out)

    def test_the_annotation_key_survives_with_a_null_field(self):
        self.run_sym("retire", "--symbol", "SYM-002")
        stored = self.annotations()
        self.assertIn(("symbol", "2"), stored, "the key was deleted, not retired")
        self.assertIsNone(stored[("symbol", "2")]["purpose"])
        self.assertIn("verify       OK", self.run_cli("--verify"),
                      "the journal no longer replays onto the table")

    def test_a_retired_purpose_stops_answering_queries(self):
        found, _ = self.run_streams("query", "--purpose", "wrong")
        self.assertEqual([2], self.ids_in(found))
        self.run_sym("retire", "--symbol", "SYM-002")
        gone, _ = self.run_streams("query", "--purpose", "wrong")
        self.assertEqual([], self.ids_in(gone))

    def test_one_field_can_be_retired_without_the_others(self):
        self.run_sym("annotate", "--module", "alpha", "--role", "Core domain",
                     "--owner", "dev-mono")
        self.run_sym("retire", "--module", "alpha", "--field", "owner")
        stored = self.annotations()[("module", "alpha")]
        self.assertEqual("Core domain", stored["role"])
        self.assertIsNone(stored["owner"])

    def test_nothing_to_retire_is_refused_with_the_journal_untouched(self):
        before = self.log_lines()
        out = self.run_sym("retire", "--symbol", "SYM-006", expect=1)
        self.assertIn("nothing to retire", out)
        self.assertEqual(before, self.log_lines())

        again = self.run_sym("retire", "--symbol", "SYM-002", "--field", "owner",
                             expect=1)
        self.assertIn("carries no owner", again)
        self.assertEqual(before, self.log_lines())


# ------------------------------------------------------------------- arm 8
class CompactTests(_SymbolsCase):
    """Arm 8 -- conservative housekeeping: it reports far more than it removes."""

    def setUp(self) -> None:
        super().setUp()
        self.fresh_store()

    def test_compact_touches_no_index_source_file_and_no_journal(self):
        before, journal = self.sources(), self.log_lines()
        out = self.run_sym("compact")
        self.assertEqual(before, self.sources())
        self.assertEqual(journal, self.log_lines(),
                         "compact appended to the append-only journal")
        self.assertIn("SOURCE FILE", out)

    def test_compact_keeps_every_tombstone(self):
        self.run_sym("compact")
        deleted = [s for s in self.symbols_by_id().values() if s["deleted"]]
        self.assertEqual(tmig.TOMBSTONES, len(deleted))
        self.assertEqual("alpha_gone", deleted[0]["name"])

    def test_compact_keeps_a_retired_annotation_key(self):
        self.run_sym("annotate", "--symbol", "SYM-002", "--purpose", "to be retired")
        self.run_sym("retire", "--symbol", "SYM-002")
        out = self.run_sym("compact")
        self.assertIn("1 fully retired, kept", out)
        self.assertIn(("symbol", "2"), self.annotations())
        self.assertIn("verify       OK", self.run_cli("--verify"))

    def test_a_dangling_edge_is_reported_and_kept_until_asked_for(self):
        with self.open_db() as conn:
            conn.execute("INSERT INTO edges(src_id, dst_id) VALUES(1, 999)")
        self.assertIn((1, 999), self.edges())

        report = self.run_sym("compact")
        self.assertIn("1 dangling edge(s) LEFT IN PLACE", report)
        self.assertIn((1, 999), self.edges())

        pruned = self.run_sym("compact", "--prune-dangling-edges")
        self.assertIn("pruned 1 dangling edge(s)", pruned)
        self.assertNotIn((1, 999), self.edges())
        self.assertEqual(tmig.EDGES, len(self.edges()))

    def test_compact_rebuilds_a_search_index_that_drifted(self):
        if not mig.fts_probe():
            self.skipTest("no FTS5 in this interpreter's sqlite3")
        with self.open_db() as conn:
            conn.execute("DELETE FROM symbols_fts")
        out = self.run_sym("compact")
        self.assertIn("symbols_fts reindexed", out)
        found, _ = self.run_streams("query", "--name", "alpha")
        self.assertEqual([1, 2, 3], self.ids_in(found),
                         "the rebuilt search index answers nothing")

    def test_no_vacuum_reports_instead_of_reclaiming(self):
        out = self.run_sym("compact", "--no-vacuum")
        self.assertIn("vacuum skipped (--no-vacuum)", out)


# ------------------------------------------------------------------- arm 9
# T-00000377 -- `--source`: the crux, and the four verdicts.
def body_text(name: str) -> str:
    """NINE lines exactly, which is what the migration fixture's 1-9 ranges want.

    Long enough that a `--source-lines 4` crux has something to drop, and shaped
    so the carriers (`raise`, `for`, an assignment, `return`) are not all in the
    first four lines -- otherwise "the crux picks carriers" would be true by
    accident of position.
    """
    return (f"def {name}(value):\n"
            f"    total = 0\n"
            f"    if value is None:\n"
            f"        raise ValueError('{name}')\n"
            f"    for item in value:\n"
            f"        total += item\n"
            f"    # a comment nobody reads\n"
            f"    label = '{name}'\n"
            f"    return total, label\n")


# The two markers of arm 10. They are ASSIGNMENTS on purpose: an assignment is a
# CARRIER, so the crux keeps it and any body that reaches the renderer prints it.
# That is what makes `assertNotIn(OUTSIDE_MARKER, ...)` a measurement instead of
# a line that would pass on an empty answer.
INSIDE_MARKER = "inside_the_root = 'this one is printable'"
OUTSIDE_MARKER = "outside_the_root = 'must never reach the agent'"


def marked_body(name: str, marker: str) -> str:
    """`body_text` with its dead comment swapped for a marker line."""
    return body_text(name).replace("    # a comment nobody reads", f"    {marker}")


class SourceTests(_SymbolsCase):
    """Arm 9 -- the body verdict. Every arm carries the state it measures."""

    def materialise(self, symbols=None) -> dict:
        """Write the source files the index RANGES point into, then publish the
        lateral with the REAL hashes of what was just written.

        Both halves matter: without the files every verdict would be `MISSING`
        (a green nobody asked for), and without the lateral every verdict would
        be `UNKNOWN` -- so a suite that skipped either would never once exercise
        `FRESH`.
        """
        symbols = list(tmig.FIXTURE if symbols is None else symbols)
        rows, hashes = [], {}
        for s in symbols:
            if s.get("deleted"):
                rows.append(s)
                continue
            path = self.root / s["path"]
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body_text(Path(s["path"]).stem), encoding="utf-8")
            lines = path.read_text(encoding="utf-8").splitlines()
            digest = bi.body_hash(lines, s["start"], s["end"])
            self.assertIsNotNone(digest, f"the fixture range misses {s['path']}")
            hashes[s["id"]] = digest
            rows.append({**s, "body_sha": digest})
        bi.write_bodies(self.root, rows, tmig.SHA)
        return hashes

    def store_with_tree(self, symbols=None) -> dict:
        self.full_fixture(**({} if symbols is None else {"symbols": symbols}))
        hashes = self.materialise(symbols)
        self.run_cli("--apply")
        return hashes

    def verdicts(self, text: str) -> list[str]:
        return [line.strip().split(" @ ")[0] for line in text.splitlines()
                if line.startswith("    ")
                and line.strip().split(" @ ")[0] in
                (sym.FRESH, sym.DRIFTED, sym.UNKNOWN, sym.MISSING)]

    # --- the four verdicts ------------------------------------------------
    def test_source_prints_a_crux_and_a_FRESH_verdict_on_an_intact_tree(self):
        self.store_with_tree()
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertEqual([sym.FRESH], self.verdicts(out))
        self.assertIn(f"{sym.FRESH} @ {tmig.SHA}", out,
                      "the verdict does not name the generation it compared to")
        self.assertIn("| def one(value):", out, "no crux was printed")

    def test_source_says_DRIFTED_after_one_edited_line(self):
        self.store_with_tree()
        self.assertEqual([sym.FRESH], self.verdicts(
            self.run_sym("query", "--name", "alpha_one", "--source")))
        target = self.root / "src/alpha/one.py"
        target.write_text(target.read_text(encoding="utf-8")
                          .replace("total = 0", "total = 1"), encoding="utf-8")

        out = self.run_sym("query", "--name", "alpha_one", "--source")

        self.assertEqual([sym.DRIFTED], self.verdicts(out))
        self.assertIn("total = 1", out, "the crux shown is not the TREE's")
        self.assertNotIn("total = 0", out, "the crux came from the store's copy")

    def test_source_says_MISSING_when_the_file_is_gone(self):
        self.store_with_tree()
        (self.root / "src/alpha/one.py").unlink()
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertEqual([sym.MISSING], self.verdicts(out))
        self.assertNotIn(f"{sym.MISSING} @", out, "MISSING named a reference")

    def test_source_says_MISSING_when_the_range_runs_past_the_end_of_file(self):
        """A truncated file must be NAMED, never hashed as an empty body."""
        self.store_with_tree()
        (self.root / "src/alpha/one.py").write_text("def one(v):\n    return v\n",
                                                    encoding="utf-8")
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertEqual([sym.MISSING], self.verdicts(out))

    def test_source_says_UNKNOWN_when_the_store_carries_no_body_sha(self):
        """The store's fault, not the code's -- and it must say so, not DRIFTED."""
        self.full_fixture()
        self.materialise()
        (self.idx / bi.BODIES_NAME).unlink()  # apply with nothing to store
        self.run_cli("--apply")
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertEqual([sym.UNKNOWN], self.verdicts(out))
        self.assertIn("| def one(value):", out, "UNKNOWN dropped the crux too")

    def test_source_survives_a_store_that_predates_the_body_column(self):
        """A v2 store answers, with UNKNOWN -- it does not die of a missing column."""
        self.full_fixture()
        self.materialise()
        self.seed_v2_db()
        self.assertNotIn("body_sha", self.symbol_columns(), "fixture is not v2")
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertEqual([sym.UNKNOWN], self.verdicts(out))

    # --- the reference, and its lag ---------------------------------------
    def test_the_lag_note_appears_on_a_stale_store_and_not_on_a_fresh_one(self):
        """Non-vacuity in one case: the same query, both states."""
        self.store_with_tree()
        fresh = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertNotIn("retard du store", fresh)

        self.full_fixture(sha=SHA_NEXT)  # the files moved, the store did not

        stale = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertIn("retard du store", stale)
        self.assertIn(tmig.SHA, stale)
        self.assertIn(SHA_NEXT, stale)

    def test_the_note_is_absent_when_source_was_not_asked_for(self):
        """It explains a verdict; with no verdict it would be noise."""
        self.store_with_tree()
        self.full_fixture(sha=SHA_NEXT)
        self.assertNotIn("retard du store",
                         self.run_sym("query", "--name", "alpha_one"))

    # --- the two bounds, which are NOT the same unit (↯ C49) ---------------
    def test_source_truncation_is_announced_beyond_twenty_rows(self):
        many = [tmig.sym(i, "src/alpha/one.py", f"fn_{i:02d}")
                for i in range(1, sym.SOURCE_MAX_ROWS + 6)]
        self.store_with_tree(many)

        out = self.run_sym("query", "--kind", "function", "--source", "--limit", "0")

        self.assertIn("SOURCE TRUNCATED", out)
        self.assertIn(f"crux calculé pour {sym.SOURCE_MAX_ROWS} des {len(many)} "
                      f"symboles", out)
        # THE BOUND IS ON THE CRUX TEXT, NOT ON THE VERDICT: every row keeps one.
        self.assertEqual([sym.FRESH] * len(many), self.verdicts(out))
        self.assertEqual(sym.SOURCE_MAX_ROWS,
                         sum(1 for line in out.splitlines()
                             if line.startswith("    | def ")))

    def test_a_short_body_is_shown_whole_and_a_long_one_says_what_it_dropped(self):
        body = body_text("probe").splitlines()
        whole, dropped = sym.crux(body, len(body))
        self.assertEqual([line.rstrip() for line in body], whole)
        self.assertEqual(0, dropped)

        kept, dropped = sym.crux(body, 4)
        self.assertEqual(4, len(kept))
        self.assertEqual(len(body) - 4, dropped)
        self.assertEqual("def probe(value):", kept[0], "the signature was dropped")
        self.assertEqual(kept, sorted(kept, key=body.index),
                         "the crux re-ordered the body")
        self.assertNotIn("    # a comment nobody reads", kept,
                         "a non-carrier line won a slot")

    def test_the_crux_is_a_pure_function_of_its_input(self):
        body = body_text("probe").splitlines()
        self.assertEqual(sym.crux(body, 4), sym.crux(body, 4))

    # --- the machine shape -------------------------------------------------
    def test_json_gains_an_additive_source_key_per_row(self):
        self.store_with_tree()
        out, _err = self.run_streams("query", "--name", "alpha_one", "--source",
                                     "--source-lines", "20", "--json")
        payload = json.loads(out)
        row = payload["results"][0]
        self.assertEqual(sym.FRESH, row["source"]["verdict"],
                         "the verdict must be the bare word, not 'FRESH @ sha'")
        self.assertEqual(tmig.SHA, row["source"]["generation"])
        self.assertEqual(0, row["source"]["dropped"], "a 9-line body under -n 20")
        self.assertEqual(9, len(row["source"]["lines"]))
        # Additive: the row keys of a --source-less answer are all still there.
        plain, _ = self.run_streams("query", "--name", "alpha_one", "--json")
        before = set(json.loads(plain)["results"][0])
        self.assertTrue(before <= set(row), f"a row key vanished: {before - set(row)}")
        self.assertEqual({"source"}, set(row) - before)

    def test_json_without_source_carries_no_source_key_at_all(self):
        self.store_with_tree()
        out, _ = self.run_streams("query", "--name", "alpha_one", "--json")
        self.assertNotIn("source", json.loads(out)["results"][0])

    # --- arm 10: the two bounds that make `--source` SAFE (S-00000782) ------
    # The store's `path` column is an INPUT, not an authority: index.db is a
    # committed binary, so a forged row is a file anyone can land. And
    # `--source-lines` is the only per-line bound on what gets printed into an
    # agent's context. Each test below carries its own ARMED CONTROL -- a
    # neighbouring row, or the same query under a real bound -- so a green here
    # can never come from a fixture that had nothing to show in the first place.
    def stage_store_paths(self, *rows: tuple[str, str]) -> None:
        """One store row per `(path, marker)`, with a REAL 9-line file where that
        path points -- including outside the root.

        The escaping rows therefore carry a VALID `body_sha`, computed from a
        file that EXISTS: what the refusal is measured against is the
        confinement, never an absence that would have said MISSING anyway.
        """
        symbols = []
        for i, (relpath, marker) in enumerate(rows, start=1):
            name = f"probe_{i}"
            target = self.root / relpath  # absolute `relpath` wins, by pathlib
            self.addCleanup(target.unlink, True)  # tearDown owns only the root
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(marked_body(name, marker), encoding="utf-8")
            symbols.append(tmig.sym(i, relpath, name))
        self.store_with_tree(symbols)

    def test_source_refuses_a_store_path_that_escapes_the_root(self):
        """A `path` of `../…` climbs out of the repo and prints an arbitrary file.

        The armed control is the row NEXT to it, in the same store and the same
        answer: a path that stays inside, whose marker MUST appear.
        """
        self.stage_store_paths(("src/alpha/inside.py", INSIDE_MARKER),
                               ("../abk_escape_probe.py", OUTSIDE_MARKER))

        out = self.run_sym("query", "--kind", "function", "--source", "--limit", "0")

        self.assertIn(INSIDE_MARKER, out,
                      "the control never armed: no body reached the renderer")
        self.assertNotIn(OUTSIDE_MARKER, out,
                         "a file OUTSIDE the root was read into the answer")
        self.assertEqual([sym.FRESH, sym.MISSING], sorted(self.verdicts(out)),
                         "the escape must land on the SAME verdict as a gone file")
        self.assertNotIn(f"{sym.MISSING} @", out, "MISSING named a reference")

    def test_source_refuses_an_absolute_store_path(self):
        """`root / '/etc/passwd'` IS `/etc/passwd`: pathlib hands the whole join
        to the absolute side, so this escapes without a single `..`."""
        outside = (self.root.parent / "abk_absolute_probe.py").as_posix()
        self.stage_store_paths(("src/alpha/inside.py", INSIDE_MARKER),
                               (outside, OUTSIDE_MARKER))

        out = self.run_sym("query", "--kind", "function", "--source", "--limit", "0")

        self.assertIn(INSIDE_MARKER, out, "the control never armed")
        self.assertNotIn(OUTSIDE_MARKER, out,
                         "an ABSOLUTE store path was dereferenced")
        self.assertEqual([sym.FRESH, sym.MISSING], sorted(self.verdicts(out)))

    def long_body_store(self, length: int) -> None:
        """A `length`-line body of pure carriers, so the crux keeps exactly its
        limit and the drop count is a function of the BOUND, not of the fixture."""
        body = [f"def big(value):"] + [f"    slot_{i:03d} = {i}"
                                       for i in range(1, length)]
        target = self.root / "src/alpha/big.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(body) + "\n", encoding="utf-8")
        self.store_with_tree([tmig.sym(1, "src/alpha/big.py", "big",
                                       start=1, end=length)])

    def body_lines(self, text: str) -> list[str]:
        """The crux TEXT lines only -- the `… (+N lignes)` tail is not a body line."""
        return [line for line in text.splitlines()
                if line.startswith("    | ") and not line.startswith("    | …")]

    def test_source_lines_zero_is_clamped_to_one_not_unlimited(self):
        """`crux()` reads `limit <= 0` as "nothing to choose" and returns the body
        WHOLE, so an unclamped `0` would be the exact opposite of a bound."""
        self.long_body_store(40)
        control = self.run_sym("query", "--name", "big", "--source",
                               "--source-lines", "5")
        self.assertEqual(5, len(self.body_lines(control)),
                         "the control never armed: the bound does not bite at all")
        self.assertIn("(+35 lignes)", control)

        out = self.run_sym("query", "--name", "big", "--source",
                           "--source-lines", "0")

        self.assertEqual(1, len(self.body_lines(out)),
                         "--source-lines 0 printed 40 lines: the bound is OFF")
        self.assertIn("| def big(value):", out, "the clamp dropped the signature")
        self.assertIn("(+39 lignes)", out, "the drop was not announced")

    def test_source_lines_above_cap_is_clamped(self):
        """The ceiling is the CLI's, not the caller's: `crux` stays pure."""
        over = sym.SOURCE_LINES_CAP + 50
        self.long_body_store(over)
        control = self.run_sym("query", "--name", "big", "--source",
                               "--source-lines", str(sym.SOURCE_LINES_CAP - 1))
        self.assertEqual(sym.SOURCE_LINES_CAP - 1, len(self.body_lines(control)),
                         "the control never armed below the cap")

        out = self.run_sym("query", "--name", "big", "--source",
                           "--source-lines", str(over))

        self.assertEqual(sym.SOURCE_LINES_CAP, len(self.body_lines(out)),
                         f"--source-lines {over} was honoured above the cap")
        self.assertIn("(+50 lignes)", out, "the drop was not announced")


# ------------------------------------------------------------------ arm 11
# T-00000378 -- the freshness overlay: the ANSWER is repaired, nothing is written.
#
# THIS ARM PAYS FOR A REAL REPOSITORY, AND IT HAS TO. `tmig._Case` writes its
# index with the publishers directly and never runs `git init`, so `git cat-file
# -e <anchor>` cannot resolve there and the overlay could only ever declare
# itself UNAVAILABLE -- which is a fine test of one branch and no test at all of
# the other seven. The overlay's whole subject is `git diff <the store's own
# generation>`, so the arm that measures it builds a git repo, real sources, a
# real `build_index.py` run and a real `--apply`.
ALPHA_SRC = """def alpha_one(value):
    total = 0
    if value is None:
        raise ValueError('alpha_one')
    for item in value:
        total += item
    return total
"""

BETA_SRC = """def beta_one(value):
    label = 'beta'
    if not value:
        return label
    return value
"""

# A `.ts` file, because `CTAGS_SKIP_EXT = PY_EXT | CSS_EXT` means every Python
# source in this kit takes the stdlib branch and the ctags branch of the overlay
# would otherwise be covered by nothing at all (plan §7, criterion 15).
TS_SRC = """export function tsAlpha(value: number): number {
  let total = 0;
  if (value > 0) {
    total = value;
  }
  return total;
}

export function tsBeta(value: string): string {
  return value.trim();
}
"""


def index_fingerprint(folder: Path) -> dict:
    """`(size, mtime_ns, sha256)` per file -- the §5.8 witness, in one place.

    THE THREE FIELDS ARE NOT REDUNDANT. A rewrite with identical content still
    moves `mtime_ns`, and that is a WRITE even when the bytes agree: a query that
    republished a file byte-for-byte would still have taken the publish path, and
    a fingerprint that could not see it would certify a discipline it never
    measured.
    """
    out = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        stat = path.stat()
        out[path.name] = (stat.st_size, stat.st_mtime_ns,
                          hashlib.sha256(path.read_bytes()).hexdigest())
    return out


class _OverlayCase(_SymbolsCase):
    """A real repo: git, real sources, the real builder, the real store."""

    def setUp(self) -> None:
        super().setUp()
        if not GIT:
            self.skipTest("git not available")

    # --- fixture ------------------------------------------------------------
    def repo(self, files: dict | None = None) -> None:
        """Write sources, COMMIT them, build the index, migrate the store.

        The commit is what makes the store's generation an anchor `git cat-file
        -e` resolves -- the second of the four availability guards.
        """
        self.write(files or {"src/alpha.py": ALPHA_SRC, "src/beta.py": BETA_SRC})
        for args in (("init", "-q"), ("config", "user.email", "t@t"),
                     ("config", "user.name", "t")):
            self._git(*args)
        self._git("add", "-A")
        self._git("commit", "-qm", "init")
        self.build_index()
        self.run_cli("--apply")

    def write(self, files: dict) -> None:
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")

    def _git(self, *args: str) -> None:
        subprocess.run([GIT, "-C", str(self.root), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def build_index(self, *argv: str) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bi.cli(["--root", str(self.root), *argv])
        self.assertEqual(0, code, f"builder failed: {out.getvalue()}{err.getvalue()}")

    # --- inspect ------------------------------------------------------------
    def payload(self, *argv: str) -> dict:
        out, _err = self.run_streams("query", *argv, "--json")
        return json.loads(out)

    def row_named(self, payload: dict, name: str) -> dict:
        rows = [r for r in payload["results"] if r["name"] == name]
        self.assertEqual(1, len(rows), f"{name!r} is not a single row: {rows}")
        return rows[0]

    def poke_meta(self, value: str | None) -> None:
        """Set or DELETE the store's `built_at_sha` -- the overlay's only anchor."""
        conn = mig.connect(mig.db_path(self.root))
        try:
            if value is None:
                conn.execute("DELETE FROM meta WHERE key = ?", (mig.META_BUILT_AT_SHA,))
            else:
                conn.execute("UPDATE meta SET value = ? WHERE key = ?",
                             (value, mig.META_BUILT_AT_SHA))
            conn.commit()
        finally:
            conn.close()


class OverlayBoundsTests(_OverlayCase):
    """The branch A2 exists for: an insertion ABOVE a symbol moved its range."""

    def test_a_symbol_pushed_down_gets_the_TREE_bounds_and_says_how_far(self):
        self.repo()
        before = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        self.assertEqual(1, before["start"], "fixture: alpha_one does not start at 1")

        self.write({"src/alpha.py": "# probe line 1\n# probe line 2\n" + ALPHA_SRC})
        after = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")

        self.assertEqual(3, after["start"], "the overlay did not move the range")
        self.assertEqual(before["end"] + 2, after["end"])
        self.assertEqual(sym.ST_MOVED, after["overlay"]["status"])
        self.assertEqual(2, after["overlay"]["shift"])
        self.assertEqual({"start": before["start"], "end": before["end"]},
                         after["overlay"]["baseline"],
                         "the STORE's own bounds must survive as `baseline`")
        self.assertIn("~moved(+2)", self.run_sym("query", "--name", "alpha_one"))

    def test_a_move_alone_is_not_a_drift_and_the_two_are_reported_apart(self):
        """A pure shift keeps the body identical -- that is the false alarm the
        overlay removes. An edit IN PLACE keeps the range and is a real drift."""
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC})
        moved = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        self.assertEqual(sym.ST_MOVED, moved["overlay"]["status"],
                         "a pure move was reported as a drift")

        self.write({"src/alpha.py": ALPHA_SRC.replace("total = 0", "total = 99")})
        drifted = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        self.assertEqual(sym.ST_DRIFTED, drifted["overlay"]["status"])
        self.assertEqual(0, drifted["overlay"]["shift"])
        self.assertIn("~drifted", self.run_sym("query", "--name", "alpha_one"))

    def test_a_row_whose_file_did_not_change_is_not_refreshed_and_says_so(self):
        """`not-refreshed` and `unchanged` are different facts; only one of them
        is a measurement, so the overlay never spells the first as the second."""
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC})
        payload = self.payload("--limit", "0")
        self.assertEqual(sym.ST_MOVED,
                         self.row_named(payload, "alpha_one")["overlay"]["status"])
        self.assertEqual(sym.ST_NOT_REFRESHED,
                         self.row_named(payload, "beta_one")["overlay"]["status"])

    def test_the_source_crux_is_sliced_out_of_the_REFRESHED_range(self):
        """Ordering, measured: `--source` must run AFTER the overlay, or a symbol
        merely pushed down would hash the WRONG lines and read DRIFTED."""
        self.repo()
        self.assertIn(f"{sym.FRESH} @", self.run_sym("query", "--name", "alpha_one",
                                                     "--source"))
        self.write({"src/alpha.py": "# probe\n# probe\n" + ALPHA_SRC})
        out = self.run_sym("query", "--name", "alpha_one", "--source")
        self.assertIn(f"{sym.FRESH} @", out,
                      "a pure move was hashed against the stale range")
        self.assertIn("| def alpha_one(value):", out, "the crux missed the new range")


class OverlayGoneAndAmbiguousTests(_OverlayCase):
    """The two conservative verdicts, and the guard that produces the second."""

    def test_a_symbol_the_tree_no_longer_holds_is_marked_GONE(self):
        self.repo()
        self.write({"src/alpha.py": "# every symbol of this file is gone\n"})
        out = self.run_sym("query", "--name", "alpha_one")
        self.assertIn("[GONE dans l'arbre]", out)
        row = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        self.assertEqual(sym.ST_GONE, row["overlay"]["status"])
        self.assertEqual(1, row["start"], "a GONE row must keep the STORE's bounds")

    def test_un_fichier_ECARTE_PAR_FORME_n_est_PAS_declare_GONE(self):
        """LE PIÈGE DES TROIS SEAUX, mesuré par le binôme sur T-00000609.

        `extract_file` rend `[]` pour TROIS prétentions qui ne se ressemblent
        pas : aucun extracteur pour ce suffixe, fichier illisible, et — depuis la
        garde de forme — ÉCARTÉ DÉLIBÉRÉMENT. Cette dernière ne doit JAMAIS
        s'épeler GONE : le fichier est là, intact, on a seulement refusé de le
        lire. Sans la branche que ce témoin gèle, le binôme a mesuré 800 lignes
        sur 800 marquées disparues, avec la liste des NON COUVERTS **vide** —
        c'est-à-dire un overlay qui affirme avoir regardé.

        LE DÉFAUT PRÉEXISTAIT POUR LE CSS, dont l'extracteur rend `[]` de la même
        façon ; la garde JS l'aurait élargi à 2 051 lignes sur ce dépôt."""
        # LE FICHIER EST D'ABORD INDEXÉ — c'est le scénario réel : le bundle
        # était dans le store, puis la garde de forme arrive (montée de version
        # du kit) et l'arbre cesse d'être lu. Sans ce premier temps, le store est
        # vide pour ce chemin et le témoin ne mesurerait rien.
        self.repo({"src/alpha.py": ALPHA_SRC,
                   "src/bundle.js": "export function lisible() {\n  return 1;\n}\n"})
        charge = self.payload("--file", "src/bundle.js")
        self.assertTrue(charge.get("results"),
                        "le store ne porte aucune ligne — la prémisse est fausse")

        minifie = "".join(f"class C{n}{{m{n}(){{return {n}}}}}" for n in range(400))
        self.write({"src/bundle.js": minifie})
        charge = self.payload("--file", "src/bundle.js")
        rangs = {(r.get("overlay") or {}).get("status") for r in charge.get("results", [])}
        self.assertNotIn(sym.ST_GONE, rangs,
                         "un fichier PRÉSENT, écarté par forme, a été déclaré "
                         "disparu de l'arbre")
        self.assertIn("src/bundle.js", (charge.get("refresh") or {}).get("uncovered", []),
                      "l'overlay se dit COUVERT sur un fichier qu'il a refusé de lire")
        # ET LA CHARGE RESTE PARSABLE : la note d'exclusion partait sur STDOUT,
        # donc elle précédait le JSON et `json.loads` levait. `self.payload`
        # parse — si la note revenait sur stdout, ce témoin tomberait ici.
        self.assertTrue((self.root / "src" / "bundle.js").exists(),
                        "le fichier a disparu : la mise en scène est fausse")

    def test_a_homonym_group_that_changed_size_is_AMBIGU_not_mispaired(self):
        """↯ C5 -- the defect this guard exists for: a second `alpha_one` above
        the first shifts every ordinal after it, and a naive re-pairing would
        hand the NEW body to the OLD SYM-ID, silently, on every query."""
        self.repo()
        self.write({"src/alpha.py": "def alpha_one(x):\n    return x\n\n\n" + ALPHA_SRC})
        out = self.run_sym("query", "--name", "alpha_one")
        self.assertIn("[AMBIGU décalage ordinal]", out)
        row = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        self.assertEqual(sym.ST_AMBIGUOUS, row["overlay"]["status"])
        self.assertEqual((1, 7), (row["start"], row["end"]),
                         "an AMBIGU row must keep the STORE's bounds, not guess")

    def test_the_ambiguity_is_local_to_its_group_not_to_the_whole_file(self):
        """A rule at FILE granularity would cancel the overlay the moment a
        function is added -- the very case A2 exists for. Same file, two groups:
        one ambiguous, the other repaired."""
        self.repo({"src/alpha.py": ALPHA_SRC + "\n\n" + BETA_SRC})
        self.write({"src/alpha.py": "def alpha_one(x):\n    return x\n\n\n"
                                    + ALPHA_SRC + "\n\n" + BETA_SRC})
        payload = self.payload("--limit", "0")
        self.assertEqual(sym.ST_AMBIGUOUS,
                         self.row_named(payload, "alpha_one")["overlay"]["status"])
        self.assertEqual(sym.ST_MOVED,
                         self.row_named(payload, "beta_one")["overlay"]["status"],
                         "the untouched group of the same file was collaterally lost")


class OverlayNewSymbolTests(_OverlayCase):
    """§2C -- a SYM-ID is never invented, and never spelled `null` in a row."""

    def test_a_symbol_absent_from_the_store_lands_in_HORS_STORE_never_in_results(self):
        self.repo()
        self.write({"src/alpha.py": "def probe_new(x):\n    return x\n\n\n" + ALPHA_SRC})
        out = self.run_sym("query", "--name", "alpha_one")
        self.assertIn("# HORS STORE", out)
        self.assertIn("probe_new", out)
        self.assertIn(sym.NEW_NOWHERE, out)

        payload = self.payload("--name", "alpha_one")
        self.assertNotIn("probe_new", [r["name"] for r in payload["results"]])
        self.assertTrue(all(isinstance(r["sym_id"], str) for r in payload["results"]),
                        "a sym_id stopped being a string")
        self.assertEqual(["probe_new"],
                         [n["name"] for n in payload["refresh"]["new_symbols"]])
        self.assertIsNone(payload["refresh"]["new_symbols"][0]["sym_id"])

    def test_a_new_symbol_the_index_FILES_already_carry_is_named_with_its_id(self):
        """The files are the authority this CLI's docstring names, so a symbol
        indexed since the last `--resync` gets its REAL id and the resync to run,
        instead of 'no identifier' -- which would be false."""
        self.repo()
        self.write({"src/alpha.py": "def probe_new(x):\n    return x\n\n\n" + ALPHA_SRC})
        self.build_index()  # the FILES learn probe_new; the STORE does not

        out = self.run_sym("query", "--name", "alpha_one")
        self.assertIn(sym.NEW_IN_FILES, out)
        entry = [n for n in self.payload("--name", "alpha_one")["refresh"]["new_symbols"]
                 if n["name"] == "probe_new"]
        self.assertEqual(1, len(entry))
        self.assertRegex(entry[0]["sym_id"] or "", r"^SYM-\d+$",
                         "the id published in SYMBOLS.md was not recovered")

    def test_edge_queries_refresh_positions_and_invent_no_symbol(self):
        """§5.7 -- `edges` are recomputed only by a global rebuild, so under
        --callers/--callees the overlay moves ranges and adds nothing."""
        self.repo()
        self.write({"src/alpha.py": "def probe_new(x):\n    return x\n\n\n" + ALPHA_SRC})
        target = self.row_named(self.payload("--name", "alpha_one"), "alpha_one")
        payload = self.payload("--callees", target["sym_id"])
        self.assertEqual([], payload["refresh"]["new_symbols"])
        self.assertNotIn("# HORS STORE", self.run_sym("query", "--callees",
                                                      target["sym_id"]))


class OverlaySwitchTests(_OverlayCase):
    """↯ C11 -- a behaviour change, and both ways of disarming it SAY so."""

    def test_no_refresh_answers_from_the_store_alone_and_announces_it(self):
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC})
        out = self.run_sym("query", "--name", "alpha_one", "--no-refresh")
        self.assertIn("--no-refresh", out)
        self.assertNotIn("~moved", out)
        payload = self.payload("--name", "alpha_one", "--no-refresh")
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertEqual(1, payload["results"][0]["start"], "the store's bounds moved")
        self.assertNotIn("overlay", payload["results"][0])

    def test_the_env_switch_is_never_a_silent_disarming(self):
        """A disarming three layers up is the one nobody sees, so the variable is
        NAMED in the answer -- criterion 11 reddens on exactly that silence."""
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC})
        with mock.patch.dict(os.environ, {sym.NO_REFRESH_ENV: "1"}):
            out = self.run_sym("query", "--name", "alpha_one")
            payload = self.payload("--name", "alpha_one")
        self.assertIn(sym.NO_REFRESH_ENV, out)
        self.assertNotIn("~moved", out)
        self.assertFalse(payload["refresh"]["enabled"])

    def test_only_a_non_empty_non_zero_env_value_disarms(self):
        """Non-vacuity: if any value disarmed, the test above would pass on a
        variable that happened to be set to `0` somewhere in CI."""
        for value, armed in (("1", False), ("yes", False), ("0", True), ("", True)):
            with self.subTest(value=value):
                self.assertEqual(
                    armed, sym.refresh_disabled_by_env({sym.NO_REFRESH_ENV: value})
                    is None)
        self.assertIsNone(sym.refresh_disabled_by_env({}), "unset must stay armed")

    def test_the_refresh_budget_announces_the_files_it_left_uncovered(self):
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC,
                    "src/beta.py": "# probe\n" + BETA_SRC})
        out = self.run_sym("query", "--name", "one", "--refresh-budget", "1")
        self.assertIn("!! REFRESH TRUNCATED", out)
        self.assertIn("2 fichier(s) changé(s), 1 analysés", out)
        self.assertIn("src/beta.py", out, "the uncovered file was not named")
        payload = self.payload("--name", "one", "--refresh-budget", "1")
        self.assertEqual(2, payload["refresh"]["changed_files"])
        self.assertEqual(1, payload["refresh"]["parsed"])
        self.assertEqual(["src/beta.py"], payload["refresh"]["truncated"])


class OverlayAvailabilityTests(_OverlayCase):
    """Four named causes, never a silence -- a mute overlay reads as 'nothing
    changed' (L-00000136)."""

    def test_unresolvable_anchor_refuses_instead_of_diffing_a_partial_set(self):
        """`changed_source_files` degrades in SILENCE when the anchor does not
        resolve, so `cat-file -e` is the guard that keeps a partial answer from
        being served as a complete one."""
        self.repo()
        self.poke_meta("deadbee")
        out = self.run_sym("query", "--name", "alpha_one")
        payload = self.payload("--name", "alpha_one")
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertIn("INDISPONIBLE", out)
        self.assertIn("deadbee", payload["refresh"]["reason"])
        self.assertNotIn("overlay", payload["results"][0])

    def test_no_db_generation_makes_the_overlay_unavailable_with_no_fallback(self):
        """↯ C15 -- and this is NOT a vacuous check. The index files here carry a
        `built @` that git resolves perfectly, so the deleted `files_generation`
        fallback would make the overlay run. `enabled is False` measures the
        removal, not merely the presence of a line."""
        self.repo()
        self.assertTrue(bi.git(self.root, "cat-file", "-e",
                               sym.files_generation(self.root) or "") is not None,
                        "witness: the files' generation must be resolvable, or this "
                        "test could not tell a removed fallback from a broken one")
        self.poke_meta(None)
        payload = self.payload("--name", "alpha_one")
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertIn(mig.META_BUILT_AT_SHA, payload["refresh"]["reason"])
        self.assertIn("INDISPONIBLE", self.run_sym("query", "--name", "alpha_one"))

    def test_a_non_hexadecimal_anchor_never_reaches_git_as_an_argument(self):
        self.repo()
        self.poke_meta("--upload-pack=touch pwned")
        payload = self.payload("--name", "alpha_one")
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertIn("hexadecimal", payload["refresh"]["reason"])

    def test_a_repository_less_tree_says_which_guard_bit(self):
        """The `tmig._Case` shape: index files, a store, and no git at all."""
        self.fresh_store()
        payload = json.loads(self.run_streams("query", "--name", "alpha_one",
                                              "--json")[0])
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertIn("git cannot resolve", payload["refresh"]["reason"])

    def test_a_disagreeing_dirscope_is_an_ADVISORY_guard_and_still_refuses(self):
        self.repo()
        main = self.idx / bi.MAIN_NAME
        lines = main.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("dirscope ", "dirscope ff") if "dirscope " in \
            lines[0] else lines[0] + " · dirscope ffffffff"
        main.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        payload = self.payload("--name", "alpha_one")
        self.assertFalse(payload["refresh"]["enabled"])
        self.assertIn("directory scope", payload["refresh"]["reason"])


class OverlayWritesNothingTests(_OverlayCase):
    """§5.8 -- the property A2 is only allowed to ship WITH, plus its witness."""

    def test_a_series_of_queries_writes_nothing_in_the_index_directory(self):
        self.repo()
        self.write({"src/alpha.py": "# probe\n" + ALPHA_SRC,
                    "src/beta.py": "def brand_new(x):\n    return x\n\n\n" + BETA_SRC})
        before = index_fingerprint(self.idx)
        self.assertTrue(before, "population VIDE -- instrument invalide, rien conclu")

        self.run_sym("query", "--name", "one")                       # text
        self.run_sym("query", "--name", "one", "--json")             # machine
        self.run_sym("query", "--name", "one", "--source")           # tree read
        self.run_sym("query", "--name", "one", "--refresh-budget", "1")  # truncated
        self.run_sym("query", "--name", "one", "--no-refresh")       # disarmed
        self.poke_meta("deadbee")
        self.run_sym("query", "--name", "one")                       # UNAVAILABLE
        after = index_fingerprint(self.idx)

        # `poke_meta` legitimately writes index.db — which is a MACHINE store
        # outside this directory since T-00000668, so NOTHING is excluded any
        # more: every file here must be identical in size, mtime AND bytes, and
        # the store must not have reappeared among them.
        self.assertNotIn(mig.DB_NAME, before, "index.db sits among the index files")
        self.assertNotIn(mig.DB_NAME, after, "a query recreated index.db in the index directory")
        self.assertEqual(before, after, "a query touched an index artefact")

    def test_the_fingerprint_witness_reddens_on_a_tree_that_did_move(self):
        """L-00000232 -- without this, a BLIND instrument and an intact tree
        return the same green, and the test above would certify its own
        existence instead of the discipline it claims to measure."""
        self.repo()
        before = index_fingerprint(self.idx)
        target = self.idx / bi.MAIN_NAME
        target.write_text(target.read_text(encoding="utf-8") + "\n",
                          encoding="utf-8", newline="\n")
        after = index_fingerprint(self.idx)
        self.assertNotEqual(before, after,
                            "the fingerprint cannot see a byte being appended")
        self.assertNotEqual(before[bi.MAIN_NAME], after[bi.MAIN_NAME])


class OverlayCtagsParityTests(_OverlayCase):
    """Criterion 15 -- the branch this repo's own sources can never exercise.

    `CTAGS_SKIP_EXT = PY_EXT | CSS_EXT`, so every Python file takes the stdlib
    branch and the ctags path of `extract_scope` is covered by nothing here. A
    `.ts` fixture is the cheapest file that reaches it.
    """

    def test_overlay_parity_on_a_ctags_fixture(self):
        self.repo({"src/alpha.py": ALPHA_SRC, "src/mod.ts": TS_SRC})
        rels = ["src/mod.ts"]
        ctags_bin = bi.ctags_binary()

        # The PARITY NET (L-00000221): the lifted extraction and the builder's own
        # `reconcile` must agree on the same file set. Unification by a test, not
        # by a refactor of the Stop-hook write path.
        lifted = bi.extract_scope(self.root, rels, ctags_bin, bi.CTAGS_KINDS)
        symbols, _delta = bi.reconcile(self.root, rels, ctags_bin, bi.CTAGS_KINDS)
        from_reconcile = {(s["name"], s["kind"], s["start"], s["end"])
                          for s in symbols
                          if not s.get("deleted") and s.get("path") in rels}
        from_lifted = {(s["name"], s["kind"], s["start"], s["end"])
                       for s in lifted[rels[0]]}
        self.assertTrue(from_lifted, "the .ts fixture extracted NOTHING -- the "
                                     "parity would be true of two empty sets")
        self.assertEqual(from_reconcile, from_lifted,
                         f"extract_scope diverges from reconcile on {rels[0]} "
                         f"(backend: {'ctags' if ctags_bin else 'stdlib fallback'})")

        # ... and end to end, through the overlay, on the same file.
        self.write({"src/mod.ts": "// probe\n// probe\n" + TS_SRC})
        row = self.row_named(self.payload("--name", "tsAlpha"), "tsAlpha")
        self.assertEqual(sym.ST_MOVED, row["overlay"]["status"])
        self.assertEqual(2, row["overlay"]["shift"])


class OverlayStdioEncodingTests(_OverlayCase):
    """T-00000378 hardening -- the overlay's own notes carry non-ASCII
    ("fraîcheur", "—", "changé") and `json.dumps` runs with ensure_ascii=False,
    so they reach stdout RAW. On a cp1252 console the process must still emit
    UTF-8, or a redirected --json payload is undecodable downstream
    (`json.loads(bytes.decode("utf-8"))` fails on the lone 0xee/0x97 bytes).

    PROVEN ACROSS A PROCESS BOUNDARY. Every other test here parses in-process,
    where the PARENT's stdout encoding hides the child's -- the exact blind spot
    this arm closes: only a real subprocess with PYTHONIOENCODING=cp1252 forces
    the child onto a cp1252 console and reads back its bytes.
    """

    def _run_cp1252(self, *argv: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        return subprocess.run(
            [sys.executable, str(SYMBOLS), argv[0], "--root", str(self.root),
             *argv[1:]],
            capture_output=True, env=env, cwd=str(SYMBOLS.parent))

    def test_json_payload_is_utf8_decodable_under_a_cp1252_console(self):
        self.repo()
        proc = self._run_cp1252("query", "--name", "alpha_one", "--json")
        self.assertEqual(0, proc.returncode, f"stderr={proc.stderr!r}")
        text = proc.stdout.decode("utf-8")   # must not raise UnicodeDecodeError
        payload = json.loads(text)           # must not raise JSONDecodeError
        self.assertTrue(any("fraîcheur" in n for n in payload["notes"]),
                        "witness: the accented overlay note must be present, or "
                        "the arm would pass on an ASCII-only payload")

    def test_human_output_carries_utf8_bytes_under_a_cp1252_console(self):
        self.repo()
        proc = self._run_cp1252("query", "--name", "alpha_one")
        self.assertEqual(0, proc.returncode, f"stderr={proc.stderr!r}")
        self.assertIn(b"fra\xc3\xaecheur", proc.stdout)  # UTF-8 of "fraîcheur"


class BoundedInterpolatedValueTests(unittest.TestCase):
    """T-00000378 hardening -- an anchor and an env value reach the overlay's
    messages from OUTSIDE the tool, so their length is bounded before they are
    interpolated (a hostile 500-char value must not drown the answer)."""

    def test_a_500_char_env_value_is_bounded_and_ends_with_an_ellipsis(self):
        notes = sym.refresh_notes(sym.Refresh(), "x" * 500)
        value_line = next(n for n in notes if sym.NO_REFRESH_ENV in n)
        self.assertTrue(value_line.endswith("…"),
                        f"the bounded value must mark its cut: {value_line!r}")
        self.assertLessEqual(len(value_line), 120,
                             f"the value line is not bounded: {len(value_line)} chars")
        self.assertTrue(any("STORE" in n for n in notes),
                        "the store-bounds warning (L-00000136) must survive the "
                        "value's isolation onto its own line")

    def test_a_short_env_value_is_shown_whole_with_no_ellipsis(self):
        notes = sym.refresh_notes(sym.Refresh(), "1")
        value_line = next(n for n in notes if sym.NO_REFRESH_ENV in n)
        self.assertFalse(value_line.endswith("…"))
        self.assertIn(f"{sym.NO_REFRESH_ENV}=1", value_line)

    def test_a_500_char_non_hexadecimal_anchor_is_bounded_before_the_message(self):
        self.assertEqual("y" * 64 + "…", sym._bounded_value("y" * 500))
        self.assertEqual("abc", sym._bounded_value("abc"))


class RefreshBudgetValidationTests(unittest.TestCase):
    """T-00000378 hardening -- a negative --refresh-budget silently dropped files
    off the END of the sorted changed set; reject it at PARSE time instead."""

    def test_the_validator_accepts_zero_and_positive_and_refuses_negative(self):
        self.assertEqual(0, sym._nonneg_int("0"))
        self.assertEqual(40, sym._nonneg_int("40"))
        with self.assertRaises(argparse.ArgumentTypeError):
            sym._nonneg_int("-1")

    def test_a_negative_budget_is_an_exit_2_usage_error_across_the_boundary(self):
        proc = subprocess.run(
            [sys.executable, str(SYMBOLS), "query", "--name", "x",
             "--refresh-budget", "-1", "--root", "."],
            capture_output=True, cwd=str(SYMBOLS.parent))
        self.assertEqual(2, proc.returncode, f"stderr={proc.stderr!r}")
        self.assertIn(b"must be >= 0", proc.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
