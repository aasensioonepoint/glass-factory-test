"""Crash-safety tests for build_index.py — atomicity and SYM-ID identity.

The bash suite (build_index.test.sh) covers extraction, sharding and the CLI
surface. This file covers what only fault injection can reach: a build killed
between two writes. Every case owns a temp repo, and `os.replace` is the single
injection point, because after T-014 it is the ONLY way an artefact reaches its
final name.

Guards the three lessons this file exists for:
  L-021 — a build interrupted mid-write must never re-issue SYM-IDs at exit 0.
  L-022 — the id watermark is an upper bound, reserved BEFORE the first publish,
          monotone, and a missing key means "unknown", never zero.
  L-023 — a shard the ToC does not vouch for is not authoritative on identity,
          unless its generation stamp shows it is mid-publish residue.

Style aligned with test_ledger.py: direct import (pytest puts this file's
directory on sys.path), temp roots, never the tracked index.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import build_index as bi
import migrate_index_to_db as mig

SOURCE = Path(bi.__file__).resolve()
GIT = shutil.which("git")
# The KIT's own repository — `.agents/bin/build_index.py`, two levels up. Named
# KIT_ROOT and not ROOT on purpose: every `_Case` owns a `self.root` temp tree,
# and exactly two cells below (T-00000513) read the real repo instead.
KIT_ROOT = SOURCE.parents[2]

FIXTURE = {
    "src/alpha/one.py": (
        "def alpha_one(x):\n"
        "    return alpha_two(x)\n"
        "\n"
        "\n"
        "def alpha_two(x):\n"
        "    return x\n"
    ),
    "src/beta/two.py": (
        "def beta_one(x):\n"
        "    return x\n"
        "\n"
        "\n"
        "class BetaBox:\n"
        "    def put(self, value):\n"
        "        return value\n"
    ),
}


@contextlib.contextmanager
def replace_failing(at: int = None, target: str = None):
    """Make `os.replace` raise — at the Nth call, or when publishing `target`.

    Simulates the kill this whole design exists for: the process dies with some
    artefacts of the new generation on disk and some of the old one still there.
    """
    real = os.replace
    calls = {"n": 0}

    def fake(src, dst, *a, **kw):
        calls["n"] += 1
        hit = (at is not None and calls["n"] == at) or (
            target is not None and Path(str(dst)).name == target)
        if hit:
            raise OSError(5, "injected publish failure")
        return real(src, dst, *a, **kw)

    os.replace = fake
    try:
        yield calls
    finally:
        os.replace = real


class _Case(unittest.TestCase):
    """Temp-repo fixture + build driver. Holds no test of its own."""

    def setUp(self):
        # ignore_cleanup_errors: on Windows the AV/indexer briefly holds fresh
        # files (measured: WinError 32 unlinking a just-written .py at teardown);
        # cleanup robustness is not what these tests measure. Same idiom as
        # test_migrate_layout.py.
        self._tmpdir = tempfile.TemporaryDirectory(prefix="abk_bi_",
                                                   ignore_cleanup_errors=True)
        self.root = Path(self._tmpdir.name).resolve()
        self.idx = self.root / bi.STATE_INDEX_REL
        # T-00000668 — the SQLite index store is MACHINE state under
        # `state_home()`, and `DbStalenessProbeTests` drives `mig.cli` IN-PROCESS:
        # without this patch it would create `index.db` files under the pilot's
        # real `~/.local/state/cadre`. Same isolation as
        # `test_migrate_index_to_db._Case`: a SIBLING temp dir, `$CADRE_STATE_DIR`
        # on it, `$CADRE_PROJECT_ROOT` removed so `db_path(self.root)` resolves
        # THIS root; the builder subprocesses inherit the patched environment.
        # Tenu par `.agents/evals/test_index_machine.py` (T9).
        self._statedir = tempfile.TemporaryDirectory(prefix="cadre-state-",
                                                     ignore_cleanup_errors=True)
        self.addCleanup(self._statedir.cleanup)
        self._env = mock.patch.dict(os.environ,
                                    {"CADRE_STATE_DIR": self._statedir.name})
        self._env.start()
        self.addCleanup(self._env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)
        self.write_sources(FIXTURE)

    def tearDown(self):
        self._tmpdir.cleanup()

    # --- fixture ----------------------------------------------------------
    def write_sources(self, mapping: dict) -> None:
        for rel, text in mapping.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def git_init(self) -> None:
        if not GIT:
            self.skipTest("git not available")
        for args in (("init", "-q"), ("config", "user.email", "t@t"),
                     ("config", "user.name", "t")):
            self._git(*args)
        self.commit("init")

    def commit(self, message: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-qm", message)

    def _git(self, *args: str) -> None:
        subprocess.run([GIT, "-C", str(self.root), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- run --------------------------------------------------------------
    def build(self, *argv: str, expect: int = 0) -> str:
        """Run the real CLI in-process; returns stdout. Asserts the exit code.

        `self.derniere_err` retient STDERR, où vivent les notes PAR FICHIER —
        les exclusions par forme, par exemple. Elles ont quitté stdout parce que
        `symbols.py --json` écrit sa charge sur ce flux et appelle le même
        extracteur : une seule note rendait sa sortie non parsable (T-00000609,
        reproduit de bout en bout). Les VERDICTS du constructeur restent sur
        stdout, et c'est ce que rend cette méthode."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bi.cli(["--root", str(self.root), *argv])
        self.assertEqual(expect, code,
                         f"stdout={out.getvalue()!r} stderr={err.getvalue()!r}")
        self.derniere_err = err.getvalue()
        return out.getvalue()

    # --- inspect ----------------------------------------------------------
    def snapshot(self) -> dict:
        return {p.name: p.read_bytes() for p in sorted(self.idx.iterdir()) if p.is_file()}

    def shard_bytes(self) -> dict:
        return {p.name: p.read_bytes() for p in sorted(self.idx.glob(bi.SHARD_GLOB))}

    def rows(self) -> list:
        """Every row published on disk, active and tombstoned, in file order."""
        found = []
        for path in sorted(self.idx.glob("SYMBOLS*.md")):
            found += list(bi._parse_rows(bi._read(path)))
        return found

    def ids(self) -> dict:
        """{(path, name, kind): id} over every active row on disk.

        Keyed on the TRIPLE, so it collapses homonyms — harmless for the fixtures
        that carry none, which is every case above. A test about homonyms reads
        `identities()` instead.
        """
        return {(s["path"], s["name"], s["kind"]): s["id"]
                for s in self.rows() if not s["deleted"]}

    def identities(self) -> dict:
        """{(path, name, kind, ordinal): id} over every active row on disk.

        The 4-element identity the builder actually re-pairs on (T-00000122),
        computed with the builder's own `identity_keys` — a second, hand-rolled
        ordinal convention in the test would drift from the one under test.
        """
        live = [s for s in self.rows() if not s["deleted"]]
        keys = bi.identity_keys([(s["path"], s["name"], s["kind"], s["start"], s["id"])
                                 for s in live])
        return {key: sym["id"] for key, sym in zip(keys, live)}

    def tombstoned(self) -> set:
        return {s["id"] for s in self.rows() if s["deleted"]}

    def delta(self) -> dict:
        return json.loads((self.idx / bi.DELTA_NAME).read_text(encoding="utf-8"))

    def delta_ids(self, field: str) -> list:
        """The `added` / `changed` / `removed` list of INDEX_DELTA.json as ids.

        `added` carries objects, the other two carry bare `SYM-NNN` strings.
        """
        return [row["id"] if isinstance(row, dict) else row
                for row in self.delta()[field]]

    def assert_no_residue(self) -> None:
        left = sorted(p.name for p in self.idx.glob(bi.TMP_PREFIX + "*"))
        self.assertEqual([], left, "staging files left behind")


class PrePublishFailureTests(_Case):
    def test_failure_before_the_first_publish_keeps_the_index_byte_intact(self):
        self.build()
        before = self.snapshot()
        # Change a source file, so a SUCCESSFUL publish would change the bytes:
        # without this, "unchanged" would prove nothing.
        self.write_sources({"src/alpha/one.py": FIXTURE["src/alpha/one.py"]
                            + "\n\ndef alpha_three(x):\n    return x\n"})
        with replace_failing(at=1):
            out = self.build(expect=0)
        self.assertIn(bi.FAILED_BEFORE, out)
        self.assertEqual(before, self.snapshot())
        self.assert_no_residue()


class MidPublishFailureTests(_Case):
    def test_failure_after_a_publish_exits_1_and_a_rerun_converges(self):
        self.build()
        before = self.ids()
        before_max = max(before.values())
        self.write_sources({"src/beta/two.py": FIXTURE["src/beta/two.py"]
                            + "\n\ndef beta_two(x):\n    return x\n"})
        # Target the symbol file BY NAME, never by call ordinal. `at=2` used to
        # mean "the first symbol file, right after the watermark reservation",
        # and it silently stopped meaning that the day the publish sequence
        # gained a write: the injected failure then landed BEFORE the publish,
        # so the run exited 0 with FAILED_BEFORE and this test reported a
        # regression it had itself invented. Measured when CSS indexing was
        # added (T-00000102), and on Windows only — the same ordinal still
        # happened to land mid-publish on Linux, which is the worst kind of
        # flake: one platform green, one red, same commit. A name cannot drift
        # when a neighbouring write appears.
        with replace_failing(target="SYMBOLS.md"):
            out = self.build(expect=1)
        self.assertIn(bi.FAILED_MID, out)
        self.assertNotIn(bi.FAILED_BEFORE, out)
        self.assert_no_residue()

        self.build()  # the re-run converges
        after = self.ids()
        for key, sym_id in before.items():
            self.assertEqual(sym_id, after.get(key), f"id moved for {key}")
        fresh = [i for key, i in after.items() if key not in before]
        self.assertTrue(fresh, "the new symbol was never indexed")
        self.assertGreater(min(fresh), before_max,
                           "a new symbol took an id at or below the watermark")


class ShardGenerationTests(_Case):
    def test_shards_newer_than_the_toc_stay_authoritative(self):
        """Crash between publishing shards and publishing the ToC (L-023 / C9).

        The new module's shard is not in the old ToC, but its generation stamp
        differs from it: that makes it mid-publish residue, not a leftover, and it
        must keep its ids instead of being demoted to watermark-only.
        """
        self.git_init()
        self.build("--threshold", "1")
        toc_before = bi._read(self.idx / bi.MAIN_NAME)
        self.write_sources({"src/gamma/three.py": "def gamma_one(x):\n    return x\n"})
        self.commit("gamma")  # a new sha ⇒ a new generation stamp

        with replace_failing(target=bi.MAIN_NAME):
            out = self.build("--threshold", "1", expect=1)
        self.assertIn(bi.FAILED_MID, out)
        self.assert_no_residue()
        self.assertEqual(toc_before, bi._read(self.idx / bi.MAIN_NAME),
                         "the ToC must be the OLD one — that is the crash we model")

        gamma = self.idx / "SYMBOLS_gamma.md"
        self.assertTrue(gamma.is_file(), "the new shard was never published")
        published = self.ids()[("src/gamma/three.py", "gamma_one", "function")]
        authoritative, orphans, status = bi.classify_index_files(self.root)
        self.assertEqual("ok", status)
        self.assertIn(gamma, authoritative)
        self.assertEqual([], orphans)

        self.build("--threshold", "1")
        self.assertEqual(published,
                         self.ids()[("src/gamma/three.py", "gamma_one", "function")],
                         "a re-run re-IDed a symbol published by the crashed build")

    def test_same_generation_orphan_is_watermark_only_then_dropped(self):
        self.build("--threshold", "1")
        ids_before = self.ids()
        live = next(p for p in sorted(self.idx.glob(bi.SHARD_GLOB))
                    if any(not s["deleted"] for s in bi._parse_rows(bi._read(p))))
        orphan = self.idx / "SYMBOLS_zzorphan.md"  # sorts AFTER every live shard
        orphan.write_bytes(live.read_bytes())

        authoritative, orphans, status = bi.classify_index_files(self.root)
        self.assertEqual("ok", status)
        self.assertEqual([orphan], orphans)
        self.assertNotIn(orphan, authoritative)

        self.build("--threshold", "1")
        self.assertFalse(orphan.exists(), "orphan shard survived a successful publish")
        self.assertEqual(ids_before, self.ids())


class IdentityRefusalTests(_Case):
    def test_shards_without_symbols_md_refuse_to_reid(self):
        self.build("--threshold", "1")
        (self.idx / bi.MAIN_NAME).unlink()
        shards = self.shard_bytes()

        out = self.build("--threshold", "1", expect=1)
        self.assertIn("identity source lost", out)
        self.assertNotIn(bi.FAILED_MID, out)  # own marker, same exit code
        self.assertEqual(shards, self.shard_bytes(), "shards touched while refusing")
        self.assertFalse((self.idx / bi.MAIN_NAME).exists())
        self.assert_no_residue()

    def test_full_is_the_deliberate_escape_hatch_and_says_citations_die(self):
        self.build("--threshold", "1")
        ids_before = self.ids()
        (self.idx / bi.MAIN_NAME).unlink()

        out = self.build("--threshold", "1", "--full")
        self.assertIn("dangle", out)
        self.assertTrue((self.idx / bi.MAIN_NAME).is_file())
        after = self.ids()
        self.assertTrue(after)
        # Dangling is allowed, COLLIDING is not: a rebuilt identity still starts
        # above the reserved bound, so no old citation resolves to a new symbol.
        self.assertGreater(min(after.values()), max(ids_before.values()))


class WatermarkTests(_Case):
    def test_emptied_symbol_files_never_reallocate_below_the_bound(self):
        """The L-021 defect, reproduced by hand: empty shards, then rebuild."""
        self.build()
        before = self.ids()
        before_max = max(before.values())
        for path in self.idx.glob("SYMBOLS*.md"):
            path.write_text("", encoding="utf-8")  # exactly what the old truncate left

        self.build()
        after = self.ids()
        self.assertTrue(after)
        self.assertGreater(min(after.values()), before_max,
                           f"an id at or below {before_max} was re-issued")
        self.assertGreaterEqual(self.delta()[bi.WATERMARK_KEY], max(after.values()))

    def test_corrupt_delta_reads_as_no_bound_and_is_restored(self):
        self.build()
        before = self.ids()
        (self.idx / bi.DELTA_NAME).write_text("{ not json at all", encoding="utf-8")
        self.assertIsNone(bi.read_delta_bound(self.root))

        self.build()
        self.assertEqual(before, self.ids(), "identity comes from SYMBOLS.md, not the delta")
        self.assertGreaterEqual(self.delta()[bi.WATERMARK_KEY], max(before.values()))

    def test_missing_key_is_unknown_never_zero_and_reservation_is_monotone(self):
        self.idx.mkdir(parents=True, exist_ok=True)
        (self.idx / bi.DELTA_NAME).write_text('{"built_sha": "abc"}\n', encoding="utf-8")
        self.assertIsNone(bi.read_delta_bound(self.root))  # absent ≠ 0

        pub = bi._Publisher()
        self.assertEqual(9, bi.reserve_watermark(self.root, 9, pub))
        self.assertEqual("abc", self.delta()["built_sha"], "payload not preserved")
        self.assertEqual(9, bi.reserve_watermark(self.root, 4, pub), "bound went down")
        self.assertEqual(1, len(list(self.idx.glob(bi.DELTA_NAME))))

    def test_publish_refuses_when_the_bound_was_not_reserved_first(self):
        symbols = [{"id": 7, "path": "src/alpha/one.py", "name": "alpha_one",
                    "kind": "function", "start": 1, "end": 2, "uses": [],
                    "purpose": "", "deleted": False}]
        with self.assertRaises(RuntimeError):
            bi.write_index(self.root, symbols, "abc123", "fallback", 500)
        self.assertFalse((self.idx / bi.MAIN_NAME).exists(),
                         "a symbol file was published without a reserved bound")


class BareTreeTests(_Case):
    def test_phase_one_creates_the_index_dir_itself(self):
        self.assertFalse(self.idx.exists())
        self.assertEqual(3, bi.reserve_watermark(self.root, 3, bi._Publisher()))
        self.assertEqual(3, self.delta()[bi.WATERMARK_KEY])

    def test_bare_tree_build_publishes_and_reserves(self):
        self.assertFalse(self.idx.exists())
        out = self.build()
        self.assertIn("INDEX BUILT @", out)
        self.assertTrue((self.idx / bi.MAIN_NAME).is_file())
        self.assertGreater(self.delta()[bi.WATERMARK_KEY], 0)
        self.assert_no_residue()


class PublishHygieneTests(_Case):
    def test_published_artefacts_are_readable_and_leave_nothing_behind(self):
        self.build()
        self.assert_no_residue()
        for name in (bi.MAIN_NAME, bi.DELTA_NAME, "CODEBASE_INDEX.md"):
            path = self.idx / name
            self.assertTrue(os.access(path, os.R_OK), f"{name} not readable")
            if os.name != "nt":  # mode bits are not meaningful on win32
                self.assertTrue(stat.S_IMODE(path.stat().st_mode) & 0o044,
                                f"{name} published owner-only (mkstemp 0600 leaked)")

    def test_the_truncate_before_write_idiom_is_gone(self):
        """Pin the L-021 root cause itself: emptying a shard before rewriting it."""
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn('write_text("", encoding="utf-8")', source)
        self.assertNotIn(".write_text(\"\")", source)

    def test_staging_prefix_cannot_be_read_as_a_shard(self):
        self.assertFalse(Path(bi.TMP_PREFIX + "x.md").match(bi.SHARD_GLOB))
        self.assertFalse(bi.TMP_PREFIX.startswith("SYMBOLS"))


class ReplaceRetryTests(_Case):
    """L-00000054 / T-00000036: since the dashboard polls /api/snapshot every
    5s, CODEBASE_INDEX.md has a frequent concurrent reader — the publisher's
    os.replace must absorb the transient PermissionError that profile causes
    on Windows, boundedly, without ever tearing."""

    def test_transient_permission_errors_are_retried_then_converge(self):
        pub = bi._Publisher()
        target = self.root / "artefact.md"
        target.write_text("old", encoding="utf-8")
        real_replace = os.replace
        failures = [0]

        def flaky(src_, dst_):
            if failures[0] < 3:
                failures[0] += 1
                raise PermissionError("simulated sharing violation (L-00000054)")
            real_replace(src_, dst_)

        bi.os.replace = flaky
        try:
            pub.write(target, "new")
        finally:
            bi.os.replace = real_replace
        self.assertEqual(failures[0], 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual(pub.replaced, 1)
        self.assert_no_residue()

    def test_exhausted_retry_reraises_and_discards_the_staged_temp(self):
        pub = bi._Publisher()
        target = self.root / "artefact.md"
        target.write_text("old", encoding="utf-8")
        real_replace = os.replace
        real_delay = bi._REPLACE_DELAY_SECONDS
        calls = [0]

        def always_fails(src_, dst_):
            calls[0] += 1
            raise PermissionError("permanent")

        bi.os.replace = always_fails
        bi._REPLACE_DELAY_SECONDS = 0.0
        try:
            with self.assertRaises(PermissionError):
                pub.write(target, "new")
        finally:
            bi.os.replace = real_replace
            bi._REPLACE_DELAY_SECONDS = real_delay
        self.assertEqual(calls[0], bi._REPLACE_ATTEMPTS, "retry must be bounded")
        self.assertEqual(target.read_text(encoding="utf-8"), "old",
                         "previous generation must stay whole on failure")
        self.assertEqual(pub.replaced, 0)
        self.assert_no_residue()


class StaleCheckTests(_Case):
    """--stale-check (T-00000033): the Stop-hook nudge's read-only signal.
    One staleness definition — these tests pin that the probe (a) agrees
    with --if-stale in both directions, (b) never writes, (c) reports a
    lost identity source as STALE at exit 0 (a Stop hook must never see a
    non-zero marker it would loop on)."""

    def _index_bytes(self):
        return {f.name: f.read_bytes() for f in sorted(self.idx.glob("*"))}

    def test_current_then_stale_then_current_again(self):
        self.git_init()
        self.build()
        out = self.build("--stale-check")
        self.assertIn("INDEX CURRENT", out)
        # An in-scope untracked file flips the answer...
        (self.root / "zz_new.py").write_text("x = 1\n", encoding="utf-8")
        before = self._index_bytes()
        out = self.build("--stale-check")
        self.assertIn("INDEX STALE", out)
        self.assertEqual(self._index_bytes(), before, "--stale-check must write NOTHING")
        # ...and once the change is committed, the refresh the nudge
        # recommends extinguishes it (the T-00000033 property: probe and
        # refresh share ONE definition, so they converge).
        self.commit("add zz_new")
        self.build("--if-stale")
        out = self.build("--stale-check")
        self.assertIn("INDEX CURRENT", out)

    def test_un_non_suivi_seul_ne_fait_plus_reconstruire_mais_reste_nomme(self):
        """T-00000608, option (b) du pilote — LES DEUX DESSEINS SURVIVENT.

        LE DÉFAUT MESURÉ : `_changed_names` verse les non suivis dans le scope,
        `all_source_files` bâtit l'index depuis `git ls-files` SEUL. Un fichier
        non suivi entre donc dans le scope et, en incrémental, dans l'index
        (T-00000230) — un `--full` seul le laisse dehors — et `_changed_names`
        le renomme à CHAQUE sonde : `STALE` pour toujours, et
        `session-start.sh --if-stale` reconstruit à CHAQUE
        démarrage en salissant l'arbre, sans jamais converger. Reproduit sur le
        dépôt le 2026-09-14 — un résidu de banc de 319 Ko a tenu neuf heures.

        CE QUE CET ARM ÉPINGLE, ET POURQUOI IL EN FAUT UN SEUL POUR LES DEUX :
        la sonde et le rafraîchissement lisent le MÊME prédicat. Les tester
        séparément laisserait passer le cas où ils divergent — c'est-à-dire
        exactement le défaut d'origine, où une seule question servait aux deux.
        """
        self.git_init()
        self.build()
        # Un non suivi DANS le périmètre indexé, et rien d'autre qui bouge.
        (self.root / "zz_orphelin.py").write_text("y = 2\n", encoding="utf-8")

        # (1) LA SONDE NE CÈDE PAS : elle dit toujours STALE — c'est le nudge de
        # T-00000033, qui existe pour pousser à commiter le fichier.
        out = self.build("--stale-check")
        self.assertIn("INDEX STALE", out, "la sonde a perdu son nudge")
        # ...et elle NOMME désormais, au lieu d'affirmer un effet qu'elle n'a pas.
        self.assertIn("zz_orphelin.py", out,
                      "la sonde ne nomme pas le fichier : on ne peut pas agir")
        self.assertIn("NON SUIVI", out)
        for faux in ("a rebuild would change the index files", "changerait RIEN"):
            self.assertNotIn(faux, out, "MENT : un build l'AJOUTE, un --full le RETIRE")

        # (2) LE RAFRAÎCHISSEMENT CÈDE : il ne reconstruit plus sur ce seul motif.
        avant = self._index_bytes()
        out = self.build("--if-stale")
        self.assertIn("INDEX CURRENT", out,
                      "--if-stale reconstruit encore sur un non suivi seul")
        self.assertNotIn("ls-files` seul", out, "MENT : un build incrémental l'AJOUTE")
        self.assertEqual(self._index_bytes(), avant,
                         "--if-stale a RÉÉCRIT l'index sur un non suivi seul")

        # (3) CONTRÔLE DE NON-VACUITÉ : un fichier SUIVI qui bouge fait toujours
        # reconstruire. Sans cet arm, rendre `--if-stale` inerte passerait.
        self.commit("add zz_orphelin")
        (self.root / "zz_orphelin.py").write_text("y = 3\nz = 4\n", encoding="utf-8")
        self.commit("change zz_orphelin")
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT", out,
                      "un fichier SUIVI qui change ne déclenche plus de "
                      "reconstruction : --if-stale est devenu inerte")

    def test_identity_lost_reports_stale_at_exit_zero(self):
        self.build()
        (self.idx / bi.MAIN_NAME).unlink()
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = bi.cli(["--root", str(self.root), "--stale-check"])
        self.assertEqual(code, 0, "the probe must never exit non-zero (Stop-hook path)")
        self.assertIn("INDEX STALE", buf.getvalue())


class DbStalenessProbeTests(_Case):
    """--stale-check's SECOND, independent verdict (T-00000108): the ADVISORY
    SQLite store — a MACHINE store outside the repository since T-00000668, at
    `mig.db_path(root)` (`cadre.paths.index_db()`), which is where every arm
    below looks for it. `_index_bytes` therefore no longer sees the store at all.

    The store goes stale at every rebuild — measured on this kit's own repo, files
    stamped 43e44a3 against a DB at f483129 — and nothing said so, because the
    SessionStart hooks throw the builder's stdout away and `--verify` only speaks
    when a human runs it. These arms pin that the probe now SAYS it, in the one
    channel that reaches the pilot, WITHOUT resyncing, marking or writing anything.

    The negative arms come FIRST on purpose. The whole feature is a print, and a
    print that fires when there is nothing to say is worse than the silence it
    replaced (T-00000033: the inextinguishable nudge). And `sqlite3.connect()`
    CREATES its file, so "a repo without a DB still has none afterwards" is a
    property, not a detail.
    """

    def _index_bytes(self):
        return {p.name: p.read_bytes() for p in sorted(self.idx.iterdir()) if p.is_file()}

    def _apply_db(self):
        """Create index.db from the CURRENT index files, via the REAL migration —
        a hand-built meta row could agree with a comparison that the real writer
        would have populated differently."""
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = mig.cli(["--root", str(self.root), "--apply"])
        self.assertEqual(0, code, out.getvalue())
        self.assertTrue(mig.db_path(self.root).exists())

    # --- NEGATIVE ARMS ----------------------------------------------------
    def test_a_repo_without_a_db_is_silent_and_never_gains_one(self):
        self.git_init()
        self.build()
        before = self._index_bytes()
        out = self.build("--stale-check")
        self.assertIn("INDEX CURRENT", out)
        self.assertNotIn("DB STALE", out)
        self.assertFalse(mig.db_path(self.root).exists(),
                         "the probe must never CREATE index.db — sqlite3.connect() "
                         "would, so existence is tested before connecting")
        self.assertEqual(before, self._index_bytes(),
                         "--stale-check must leave the index directory byte-identical")
        # The reader itself, asked directly: still None, still no file.
        self.assertIsNone(mig.read_db_generation(self.root))
        self.assertFalse(mig.db_path(self.root).exists())

    def test_a_db_at_the_same_generation_is_silent(self):
        self.git_init()
        self.build()
        self._apply_db()
        before = self._index_bytes()
        out = self.build("--stale-check")
        self.assertIn("INDEX CURRENT", out)
        self.assertNotIn("DB STALE", out)
        self.assertEqual(before, self._index_bytes())

    def test_files_without_a_generation_stamp_yield_no_verdict(self):
        # Nothing to compare against is NOT evidence of staleness. An invented
        # verdict here would fire at every Stop forever.
        self.git_init()
        self.build()
        self._apply_db()
        self.assertIsNone(mig.db_generation_behind(self.root, None))
        self.assertIsNone(mig.db_generation_behind(self.root, ""))
        self.assertIsNone(bi.db_staleness_line(self.root, None))

    # --- POSITIVE ARM: the measured case ---------------------------------
    def test_a_db_one_generation_behind_is_named_with_the_resync_command(self):
        self.git_init()
        self.build()
        self._apply_db()
        db_generation = mig.read_db_generation(self.root)
        # The real-world sequence: commit, rebuild, and the machine DB is behind
        # while the index FILES are perfectly current.
        self.write_sources({"src/gamma/three.py": "def gamma_one(x):\n    return x\n"})
        self.commit("gamma")
        self.build()
        files_generation = bi._generation(bi._read(self.idx / bi.MAIN_NAME))
        self.assertNotEqual(db_generation, files_generation)
        before = self._index_bytes()
        out = self.build("--stale-check")
        # Both verdicts, independent: the index is current, the DB is not.
        self.assertIn("INDEX CURRENT", out)
        self.assertIn(bi.DB_STALE_PREFIX + db_generation, out)
        self.assertIn(f"vs files @ {files_generation}", out)
        self.assertIn("migrate_index_to_db.py --resync", out)
        self.assertEqual(before, self._index_bytes(),
                         "--stale-check must write NOTHING, DB present or not")

    # --- DEGRADATION: loud about the index, silent about the DB ----------
    def test_a_corrupt_db_degrades_in_silence_at_exit_zero(self):
        self.git_init()
        self.build()
        # `db_path` creates nothing (T-00000668): a store seeded by hand makes its
        # machine-partition parent first.
        mig.db_path(self.root).parent.mkdir(parents=True, exist_ok=True)
        mig.db_path(self.root).write_bytes(b"this is not a sqlite database\n")
        out = self.build("--stale-check")   # build() asserts the exit code is 0
        self.assertIn("INDEX CURRENT", out)
        self.assertNotIn("DB STALE", out)

    def test_a_db_without_a_meta_table_degrades_in_silence(self):
        self.git_init()
        self.build()
        mig.db_path(self.root).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(mig.db_path(self.root)))
        try:
            conn.execute("CREATE TABLE unrelated(x)")
            conn.commit()
        finally:
            conn.close()
        out = self.build("--stale-check")
        self.assertIn("INDEX CURRENT", out)
        self.assertNotIn("DB STALE", out)

    def test_a_raising_db_reader_cannot_escape_or_silence_the_index_verdict(self):
        """The containment property, exercised rather than asserted in prose.

        Every DB-side failure mode ends in an exception somewhere (no sqlite3, an
        unreadable file, a migrate that refuses); this arm injects one at the
        boundary the probe actually calls. The probe is a PROBE: it must still
        print the index verdict, print no DB line, and exit 0 — a Stop hook that
        sees a non-zero exit loops the host.

        The injection point is the module cache the probe reads before loading
        (`sys.modules[PROBE_MODULE]`), which is exactly how the real loader
        resolves migrate a second time.
        """
        self.git_init()
        self.build()

        class _Exploding:
            DB_NAME = mig.DB_NAME

            @staticmethod
            def db_generation_behind(root, files_generation):
                raise RuntimeError("injected DB read failure")

        name = bi.PROBE_MODULE
        saved = sys.modules.get(name)
        sys.modules[name] = _Exploding
        try:
            out = self.build("--stale-check")   # build() asserts exit code 0
        finally:
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved
        self.assertIn("INDEX CURRENT", out)
        self.assertNotIn("DB STALE", out)


# The host wiring a kit vendors into a consumer project. Names are deliberately
# disjoint from FIXTURE's, so removing these symbols cannot move a `uses[…]` edge
# of the surviving ones — that is what lets the "byte-identical elsewhere"
# assertion below mean "the purge touched nothing else" rather than "nothing else
# happened to change".
VENDORED = {
    ".codex/hooks/x.py": "def codex_hook_entry(payload):\n    return payload\n",
    ".gemini/hooks/y.py": "def gemini_hook_entry(payload):\n    return payload\n",
    # A monorepo workspace that merely SHARES the name. Root-only exclusion must
    # leave it indexed; a per-segment rule would delete a real layer.
    "packages/app/.codex/deep.py": "def workspace_helper(value):\n    return value\n",
    # `.github` is deliberately NOT in HOST_DIRS: a consumer's own JS action is
    # plausible there and is real source.
    ".github/actions/a/index.js": "export function ghActionMain() { return 1; }\n",
    # Both V3 locations are kit code; the marker excludes them in adopted trees.
    "agentic_v3/engine.py": "def kit_engine_entry(event):\n    return event\n",
    ".agents/vendor/agentic_v3/engine.py": "def vendor_engine_entry(event):\n    return event\n",
}
HOST_ROOTS = (".codex/", ".gemini/", "agentic_v3/", ".agents/vendor/agentic_v3/")


class VendoredKitScopeTests(_Case):
    """T-00000062: the SAME directory is source in the kit's repo and vendored
    plumbing in a consumer, so the scope is decided by a VENDORING MARKER, never
    by the directory name."""

    def setUp(self):
        super().setUp()
        self.write_sources(VENDORED)

    # --- fixture helpers --------------------------------------------------
    def add_marker(self, rel=".agents/protected-paths.local", body="# vendored\n.agents/bin/\n"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def paths(self):
        return {path for (path, _name, _kind) in self.ids()}

    def rows_outside_host_roots(self):
        """Every active symbol row, VERBATIM, for files outside the host roots.

        Rows, not counts: "the other modules are untouched" has to be an
        assertion about bytes, otherwise a purge that silently re-ranked or
        re-numbered them would still pass.
        """
        out = {}
        for path in sorted(self.idx.glob("SYMBOLS*.md")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("SYM-"):
                    continue
                cells = line.split()
                # ACTIVE rows only. A tombstone carries no path (reconcile drops
                # it), so it cannot be attributed to a root here — and it is
                # exactly what `payload["removed"]` already asserts, id by id.
                if len(cells) < 2 or cells[1] == "DELETED":
                    continue
                if cells[1].startswith(HOST_ROOTS):
                    continue
                out[cells[0]] = line
        return out

    def strip_dirscope(self):
        """Rewrite the header as an index published BEFORE the field existed."""
        target = self.idx / bi.MAIN_NAME
        text = target.read_text(encoding="utf-8")
        head, rest = text.split("\n", 1)
        head = re.sub(r" · dirscope \S+", "", head)
        self.assertNotIn("dirscope", head)
        target.write_text(head + "\n" + rest, encoding="utf-8", newline="")

    # --- C10: the discriminator itself, both arms, one repo ----------------
    def test_host_dirs_are_indexed_without_a_marker_and_dropped_with_one(self):
        # NEGATIVE ARM FIRST, and it is the load-bearing one. Without a marker —
        # the kit's OWN repository — `.codex/hooks/*.py` IS the source code and
        # must stay indexed. Skip this arm and a host_skip_dirs() that ignored
        # the discriminator and returned the set unconditionally would leave
        # every positive assertion below green, i.e. green in exactly the case
        # that blinds the kit to itself (L-00000025: evaluate a guard on data
        # that CAN match).
        self.build("--full")
        before = self.paths()
        self.assertIn(".codex/hooks/x.py", before)
        self.assertIn(".gemini/hooks/y.py", before)
        # The kit indexes its engine at either location.
        self.assertIn("agentic_v3/engine.py", before)
        self.assertIn(".agents/vendor/agentic_v3/engine.py", before)

        # POSITIVE ARM, same toy repo, one file added.
        self.add_marker()
        self.build("--full")
        after = self.paths()
        self.assertNotIn(".codex/hooks/x.py", after)
        self.assertNotIn(".gemini/hooks/y.py", after)
        self.assertNotIn("agentic_v3/engine.py", after)
        self.assertNotIn(".agents/vendor/agentic_v3/engine.py", after)
        # ROOT ONLY: the identically-named workspace directory survives.
        self.assertIn("packages/app/.codex/deep.py", after)
        # `.github` is out of the default set on purpose.
        self.assertIn(".github/actions/a/index.js", after)

    def test_either_marker_file_counts(self):
        # A consumer who followed README-CLAUDE.md's enforcement table created the
        # Claude-only file; a consumer who followed T-00000031 created the shared
        # one. Both are vendoring evidence, or the fix reaches only half of them.
        for rel in (".agents/protected-paths.local",
                    ".claude/hooks/protected-paths.local"):
            with self.subTest(marker=rel):
                self.assertEqual(set(), bi.host_skip_dirs(self.root),
                                 "no marker on disk must mean no exclusion")
                marker = self.add_marker(rel)
                # The marker gates BOTH sets, so the equality is over their union
                # (T-00000388 widened it; the equality itself is the contract).
                self.assertEqual(set(bi.HOST_DIRS) | set(bi.KIT_CODE_DIRS),
                                 bi.host_skip_dirs(self.root))
                marker.unlink()  # back to the no-marker arm for the next case

    def test_presence_is_the_signal_content_is_not_read(self):
        # An EMPTY marker protects zero paths for the path guards, yet it is still
        # truthful evidence that this tree is a vendored kit (the file only ever
        # ships to consumers). Pinned so the loose coupling stays deliberate.
        self.add_marker(body="")
        self.assertEqual(set(bi.HOST_DIRS) | set(bi.KIT_CODE_DIRS),
                         bi.host_skip_dirs(self.root))

    def test_agents_is_never_reachable_and_unskip_is_closed(self):
        self.add_marker()
        # 'agentic_v3' joins the refused values: a KIT CODE root is the kit's own
        # code in every tree that carries a marker, so unlike a host directory it
        # is never something a consumer could want back (L-020's reasoning).
        for value in (".agents", ".claude,src", "srC", "agentic_v3",
                      ".codex,agentic_v3"):
            with self.subTest(unskip=value):
                buf = io.StringIO()
                with contextlib.redirect_stderr(buf), self.assertRaises(SystemExit) as cm:
                    bi.cli(["--root", str(self.root), "--unskip", value])
                self.assertEqual(2, cm.exception.code)
                self.assertIn("--unskip", buf.getvalue())
        # `.agents` stays excluded IN A VENDORED TREE whatever happens — mais le
        # MÉCANISME a changé le 2026-09-09 (T-00000251). Il était dans
        # `SKIP_DIRS`, donc élagué par NOM à toute profondeur POUR TOUT LE MONDE,
        # y compris pour le kit : son propre outillage n'avait aucune entrée
        # symbolique, et un planificateur planifiait contre un index aveugle sur
        # le code qu'il modifiait. Il est maintenant un `KIT_CODE_DIRS` : exclu à
        # la RACINE d'un arbre qui porte un marqueur de vendoring, indexé dans le
        # dépôt du kit.
        #
        # Ce que L-020 exigeait tient donc toujours, et l'assertion le dit
        # maintenant dans l'autre sens : chez un adoptant, `.agents` EST dans
        # l'ensemble exclu, et `--unskip` continue de refuser de le nommer (les
        # sous-cas ci-dessus le prouvent).
        self.assertIn(".agents", bi.host_skip_dirs(self.root, [".codex"]))
        # A legal value re-includes exactly one directory, nothing else.
        self.build("--full", "--unskip", ".codex")
        after = self.paths()
        self.assertIn(".codex/hooks/x.py", after)
        self.assertNotIn(".gemini/hooks/y.py", after)

    def test_unskip_also_reads_its_environment_variable(self):
        self.add_marker()
        old = os.environ.get("ABK_INDEX_UNSKIP")
        os.environ["ABK_INDEX_UNSKIP"] = ".codex"
        try:
            self.build("--full")
        finally:
            if old is None:
                os.environ.pop("ABK_INDEX_UNSKIP", None)
            else:
                os.environ["ABK_INDEX_UNSKIP"] = old
        self.assertIn(".codex/hooks/x.py", self.paths())

    # --- T-00000388: the kit's OWN code, on the path a consumer actually takes --
    def test_kit_code_root_tracked_by_git_is_dropped_under_marker(self):
        """Case (a), the nominal one: the kit ships `agentic_v3/` TRACKED.

        This arm exists because `all_source_files` asks `git ls-files` FIRST and
        only falls back to `_walk_sources` in a tree with no `.git`. The other
        tests in this class run on the walk path, so a fix applied there alone
        would leave every consumer — all of whom have a git repo — still indexing
        the engine. Here the repo IS initialised, which is the difference.
        """
        self.git_init()
        self.build("--full")
        self.assertIn("agentic_v3/engine.py", self.paths(),
                      "no marker: this is the kit's own repo, the engine is source")

        self.add_marker()
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out, "a narrowed scope must force a FULL build")
        after = self.paths()
        self.assertNotIn("agentic_v3/engine.py", after,
                         "under a marker the engine is KIT code, not the consumer's")
        # ROOT ONLY, and the neighbouring rule is untouched: a same-named
        # workspace directory deeper in the tree is still the consumer's source.
        self.assertIn("packages/app/.codex/deep.py", after)
        self.assertIn("src/alpha/one.py", after, "the consumer's own code is untouched")

    def test_kit_code_root_ignored_by_git_is_purged_by_the_forced_full_build(self):
        """Case (b): the consumer already git-ignored `agentic_v3/` — EEF S-806.

        Untracking a directory does NOT purge the rows a previous build published:
        incrementals only ever revisit CHANGED files, so those rows would sit in
        the index forever as symbols pointing at code the consumer never sees.
        What closes it is not a new purge path but the SCOPE FINGERPRINT moving —
        the marker changes `host_skip`, `reconcile` runs with `purge=True` over
        the whole source set, and the stale rows are tombstoned. Asserted as a
        TOMBSTONE, not as an absence: a row that merely vanished would leave every
        past `SYM-NNNN` reference dangling with nothing to explain it.
        """
        self.git_init()
        self.build("--full")
        published = self.ids()
        stale_ids = {bi.sid(i) for (path, _n, _k), i in published.items()
                     if path.startswith("agentic_v3/")}
        excluded_ids = {bi.sid(i) for (path, _n, _k), i in published.items()
                        if path.startswith(HOST_ROOTS)}
        self.assertTrue(stale_ids, "fixture must publish the engine before untracking it")

        (self.root / ".gitignore").write_text("/agentic_v3/\n", encoding="utf-8")
        self._git("rm", "-r", "--cached", "-q", "agentic_v3")
        self.commit("untrack the vendored engine")
        self.add_marker()

        out = self.build("--if-stale")
        self.assertIn("full", out, "the scope moved: this must be a full build")
        self.assertNotIn("agentic_v3/engine.py", self.paths())
        removed = set(self.delta()["removed"])
        # The case-(b) property: rows for a path git no longer tracks, which no
        # incremental would ever revisit, are TOMBSTONED rather than left behind.
        self.assertTrue(stale_ids <= removed,
                        f"untracked kit-code rows must be purged: {stale_ids - removed}")
        # ...and the purge stayed EXACT: the roots the marker excludes, no more
        # (the consumer's own code) and no fewer (a partial purge leaves orphans).
        self.assertEqual(excluded_ids, removed)

    # --- C11: the purge is exact, and the ORDER that makes it exact --------
    def test_migration_purges_exactly_the_newly_excluded_ids(self):
        self.git_init()
        self.build()
        excluded_ids = {bi.sid(i) for (path, _n, _k), i in self.ids().items()
                        if path.startswith(HOST_ROOTS)}
        self.assertTrue(excluded_ids, "fixture must actually carry excludable symbols")
        surviving_rows = self.rows_outside_host_roots()

        self.add_marker()
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out, "a narrowed scope must force a FULL build, not an "
                                   "incremental one (purge needs the whole source set)")
        payload = self.delta()
        # The PROPERTY, not a repo-specific number: removed is exactly the ids
        # under the excluded roots — no more (the rest of the codebase) and no
        # fewer (a partial purge would leave orphan rows behind).
        self.assertEqual(excluded_ids, set(payload["removed"]))
        self.assertEqual(len(excluded_ids), payload["counts"]["removed"])
        # ...and everything else is byte-for-byte what it was, ids included.
        self.assertEqual(surviving_rows, self.rows_outside_host_roots())

    def test_purge_is_never_reached_with_a_partial_scope(self):
        """purge=True ⇒ scope IS the full source set — the structural invariant.

        `skip_fp` is computed BEFORE the `incremental` predicate and folded INTO
        it, so `incremental=False` is decided before `scope` is assigned. Fold the
        comparison in later instead and `reconcile(purge=True)` would tombstone
        every symbol of every UNCHANGED file. Two independent pins here: the
        changed-file list is never even consulted on a scope-disagreement run, and
        every purging call received exactly `all_source_files()`.
        """
        self.git_init()
        self.build()
        self.add_marker()

        seen, changed_calls = [], []
        real_reconcile, real_changed = bi.reconcile, bi.changed_source_files

        def spy_reconcile(root, scope, *a, **kw):
            seen.append((list(scope), kw.get("purge", False)))
            return real_reconcile(root, scope, *a, **kw)

        def spy_changed(*a, **kw):
            changed_calls.append(a)
            return real_changed(*a, **kw)

        bi.reconcile, bi.changed_source_files = spy_reconcile, spy_changed
        try:
            self.build("--if-stale")
        finally:
            bi.reconcile, bi.changed_source_files = real_reconcile, real_changed

        self.assertEqual([], changed_calls,
                         "a scope disagreement must skip the incremental path "
                         "entirely, not compute a partial scope and purge over it")
        full = bi.all_source_files(self.root, bi.host_skip_dirs(self.root))
        purging = [scope for scope, purge in seen if purge]
        self.assertEqual(1, len(purging))
        self.assertEqual(full, purging[0])

    # --- C12: the legacy header, split by what the tree actually is -------
    def test_legacy_header_with_a_marker_rebuilds_once_then_reports_current(self):
        self.git_init()
        self.build()
        self.strip_dirscope()          # an index published before the field existed
        self.add_marker()              # ...in a tree that IS a vendored kit
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out)
        # Exactly once: the migration is self-healing, not self-repeating.
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))

    def test_legacy_header_without_a_marker_is_current_and_writes_nothing(self):
        # The kit's own repository, and every consumer that never created a
        # marker. An ABSENT dirscope field means "the empty root-only set", which
        # is what such a tree really was built with — so it must NOT pay a forced
        # full rebuild. This is the arm that keeps "the kit's index is unchanged"
        # true rather than merely intended.
        self.git_init()
        self.build()
        self.strip_dirscope()
        before = self.snapshot()
        out = self.build("--if-stale")
        self.assertIn("INDEX CURRENT", out)
        self.assertEqual(before, self.snapshot(), "--if-stale wrote to a current index")
        self.assertEqual(bi.scope_fingerprint(set()),
                         bi.published_dirscope("# ... backend ctags · kinds abc"))

    # --- agreement + idempotence -----------------------------------------
    def test_stale_check_agrees_with_if_stale_across_the_migration(self):
        self.git_init()
        self.build()
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))
        self.add_marker()
        before = self.snapshot()
        self.assertIn("INDEX STALE", self.build("--stale-check"))
        self.assertEqual(before, self.snapshot(), "--stale-check must write NOTHING")
        self.build("--if-stale")
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))

    def test_migrated_index_is_idempotent_and_keeps_its_ids(self):
        self.git_init()
        self.add_marker()
        self.build()
        ids_first = self.ids()
        self.build("--full")
        self.assertEqual(ids_first, self.ids(),
                         "a second full build must not re-attribute SYM-IDs")

    # --- T-00000513: the NEGATIVE marker, and the precedence it carries ------
    def add_kit_marker(self, body="# this tree IS the kit\n"):
        """`.agents/IS_THE_KIT` — presence is the signal, content is never read."""
        path = self.root / bi.KIT_MARKER
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def header(self):
        return (self.idx / bi.MAIN_NAME).read_text(encoding="utf-8").split("\n", 1)[0]

    def test_kit_marker_wins_over_a_vendor_marker(self):
        """Both markers on disk ⇒ KIT wins, nothing is excluded.

        This is the case the kit's own repository was measured in on 2026-09-05:
        `.agents/protected-paths.local` was there for the guard patterns of the
        since-retired local dev route (T-00000493) AND this is the kit, so the vendoring reading was wrong and
        cost 418 of 482 symbols. Asserted on both sets the marker gates — a host
        root and a kit-code root — because the defect dropped both.
        """
        self.add_marker()
        self.add_kit_marker()
        self.assertEqual(set(), bi.host_skip_dirs(self.root),
                         "the kit marker must override the vendoring marker")

        self.build("--full")
        after = self.paths()
        self.assertIn(".codex/hooks/x.py", after, "host wiring is SOURCE in the kit")
        self.assertIn("agentic_v3/engine.py", after, "the V3 engine is SOURCE in the kit")
        # ...and the published scope is the EMPTY one, byte-for-byte in the header.
        # Asserted on the raw header rather than through `published_dirscope`,
        # whose absent-field fallback IS `scope_fingerprint(set())` and would make
        # this pass on an index carrying no field at all.
        self.assertIn("dirscope " + bi.scope_fingerprint(set()), self.header())

    def test_kit_marker_alone_moves_no_scope(self):
        """Adding the marker to an already-built kit index must cost NOTHING.

        `set()` with the marker and `set()` without it are the same scope, so the
        fingerprint must not move — otherwise every kit repo pays one forced FULL
        rebuild the day it lands, and a full rebuild over an index whose rows were
        tombstoned is precisely how ~418 SYM-IDs get re-issued (S6 of the plan).
        Pinned as `INDEX CURRENT` **and** as unchanged bytes: "current" is the
        decision, the bytes are the consequence.
        """
        self.git_init()
        self.build()
        before, ids_before = self.snapshot(), self.ids()

        self.add_kit_marker()
        out = self.build("--if-stale")
        self.assertIn("INDEX CURRENT", out,
                      "the kit marker changed the effective scope — it must not")
        self.assertEqual(before, self.snapshot(), "--if-stale wrote to a current index")
        self.assertEqual(ids_before, self.ids(), "no SYM-ID may move")

    def test_this_repository_is_indexed_as_the_kit(self):
        """THE cell that would have gone red on 2026-09-05, on the real repo.

        Guarded like the neighbouring evals, on the LITERAL marker path (`strip:`,
        never ships); the former probe `main:.agents/ui-src` skipped everywhere
        (T-00000803). The `assertTrue` on `bi.KIT_MARKER` is NOT redundant: on a
        clean clone (no untracked `protected-paths.local`) `host_skip_dirs` returns
        `set()` marker or no marker, so without it a drift of the constant away
        from the literal would stay green on every machine but this one
        (L-00000395). A DELETED marker skips here; `test_template_hygiene`'s
        `KitDiscriminantTests` is the net that reddens on it.
        """
        # adopting-tree: the kit marker never travels; its absence IS the adopting tree
        if not (KIT_ROOT / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("no .agents/IS_THE_KIT — not the kit's own repo")
        self.assertTrue((KIT_ROOT / bi.KIT_MARKER).is_file(),
                        f"{bi.KIT_MARKER} is missing: this repo would be read as a "
                        "vendored kit and stop indexing its own source (T-00000513)")
        self.assertEqual(set(), bi.host_skip_dirs(KIT_ROOT),
                         "the kit's own repository must exclude nothing at its root")

    def test_kit_marker_is_stripped_from_the_template(self):
        """The marker must never travel through the template channel.

        File scope on purpose (`.agents/IS_THE_KIT`, no trailing `/`), and
        unguarded — same shape as `test_the_template_rule_is_declared` in
        `test_protected_paths_extension.py`, which already reads this file
        directly. It bounds the mirror-image defect: a consumer carrying the
        marker would index THEIR vendored plumbing as their own code.
        """
        text = (KIT_ROOT / ".template-exclude").read_text(encoding="utf-8")
        self.assertIn("strip: .agents/IS_THE_KIT", text,
                      "the rule that keeps the kit's identity marker from "
                      "travelling to an adopting project is missing")


# --- T-00000122: homonyms, and the identity that must survive them -----------
# Three methods of the SAME name and kind in ONE file — the legitimate shape the
# defect was measured on (homonymous locals across test blocks; here the same
# helper on three classes, which the stdlib .py extractor reproduces on every
# host, ctags or not, since PY_EXT never goes to ctags).
HOMONYM_PATH = "src/homonym/blocks.py"
_BLOCK = ("class Block{n}:\n"
          "    def helper(self, value):\n"
          "        return value + {n}\n")


def homonym_source(*blocks: int) -> str:
    """`blocks` in the given order; each contributes one `helper` symbol.

    Three blocks put `helper` at lines 2, 7 and 12 — same path, same name, same
    kind, three different start lines.
    """
    return "\n\n".join(_BLOCK.format(n=n) for n in blocks)


@contextlib.contextmanager
def legacy_key():
    """Run the builder with the PRE-T-00000122 identity key, `(path, name, kind)`.

    The key is NEVER persisted — it is derived from the published rows at load
    time — so "an index written under the old key" is precisely "an index a legacy
    build produced". Reproducing it with the legacy producer is therefore the
    faithful fixture; a hand-written SYMBOLS.md would only be a guess at what that
    producer wrote. This is also the mutation the non-vacuity check uses: under it,
    the reproduction arm below must go red.
    """
    real = bi.identity_keys
    bi.identity_keys = lambda rows: [key[:3] for key in real(rows)]
    try:
        yield
    finally:
        bi.identity_keys = real


class HomonymIdentityTests(_Case):
    """A file may legitimately carry several symbols of the same name AND kind.

    THE INVARIANT, and the only reason this class exists: no live symbol ever
    leaves the index without a tombstone. It is either still live, or spelled
    `DELETED` — never evaporated. Keyed on `(path, name, kind)` the homonyms of a
    group collapsed into one dict entry, and the tombstoning loop — which can only
    see what that dict holds — could not reach the others: 2 of 3 ids vanished per
    rebuild, invisible even in SYMBOLS_deleted.md, while `changed` listed the
    survivor twice and hid the loss in the counters.

    THE RESIDUAL IS WRITTEN HERE, NOT DISCOVERED LATER: identity follows the
    ORDINAL (rank by start line inside the group), so re-ordering the homonyms, or
    deleting one that is not the last, re-points ids WITHIN the group. See
    `test_reordering_homonyms_swaps_their_ids_and_says_so` and
    `test_removing_the_middle_homonym_retires_the_LAST_ordinal`.
    """

    def setUp(self):
        super().setUp()
        self.write_sources({HOMONYM_PATH: homonym_source(1, 2, 3)})

    # --- helpers ----------------------------------------------------------
    def helpers(self) -> dict:
        """The homonym group only: {(path, name, kind, ordinal): id}."""
        return {key: sym_id for key, sym_id in self.identities().items()
                if key[0] == HOMONYM_PATH and key[1] == "helper"}

    def helper_id(self, ordinal: int) -> int:
        return self.helpers()[(HOMONYM_PATH, "helper", "function", ordinal)]

    def helper_ids(self) -> set:
        """The live ids of the group, read straight off the rows.

        Deliberately independent of `identity_keys`: under `legacy_key()` the
        4-element helper above is patched too, so it would collapse the group in
        the INSTRUMENT and hide what the arm is measuring.
        """
        return {s["id"] for s in self.rows() if not s["deleted"]
                and s["path"] == HOMONYM_PATH and s["name"] == "helper"}

    def helper_starts(self) -> list:
        return sorted(s["start"] for s in self.rows()
                      if not s["deleted"] and s["name"] == "helper"
                      and s["path"] == HOMONYM_PATH)

    def sym_lines(self) -> dict:
        """{'SYM-NNN': the published row, verbatim} — ranges and purposes included."""
        out = {}
        for path in sorted(self.idx.glob("SYMBOLS*.md")):
            for line in bi._read(path).splitlines():
                if line.startswith("SYM-"):
                    out[line.split()[0]] = line
        return out

    def annotate(self, sym_id: int, purpose: str) -> None:
        """Write a `:: purpose` onto a published row, the way `indexer` does."""
        target = self.idx / bi.MAIN_NAME
        lines = target.read_text(encoding="utf-8").splitlines()
        marker = bi.sid(sym_id)
        for n, line in enumerate(lines):
            if line.startswith(marker + "  ") and line.endswith("  ::"):
                lines[n] = line + " " + purpose
                break
        else:
            self.fail(f"no annotatable row for {marker}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

    def purpose_of(self, sym_id: int) -> str:
        return next(s["purpose"] for s in self.rows() if s["id"] == sym_id)

    def assert_nothing_evaporated(self, before: set) -> None:
        """THE invariant: gone means TOMBSTONED, never absent from both sets."""
        after = set(self.identities().values()) | self.tombstoned()
        self.assertEqual(set(), before - after,
                         "ids left the index neither live nor tombstoned — they "
                         "evaporated, which is the T-00000122 data loss")

    # --- the reproduction arm (red before the fix) ------------------------
    def test_three_homonyms_all_survive_a_second_build_with_their_ids(self):
        """The measured case, replayed: build, rebuild unchanged, count the losses.

        Under `legacy_key()` this arm reports live 1 of 3 and two evaporated ids —
        it is the mutation that proves the arm is not vacuous.
        """
        self.build()
        # ROW-LEVEL FIRST, deliberately: `helper_ids()` does not go through
        # `identity_keys`, so the two assertions that matter are readable even
        # when the key itself is the thing that is wrong. Non-vacuity of the
        # FIXTURE lives here too — three distinct ids in one file, or the rest of
        # this class measures nothing.
        first_ids = self.helper_ids()
        self.assertEqual(3, len(first_ids), "the fixture carries no homonym group")
        self.assertEqual([2, 7, 12], self.helper_starts())
        first = self.helpers()
        before = set(self.identities().values())

        self.build()
        # THE red under the 3-element-key mutation, and it reads as what it is:
        # `1 != 3`, live rows dropped by a rebuild that changed nothing.
        self.assertEqual(3, len(self.helper_ids()),
                         "a no-op rebuild dropped live homonym rows")
        self.assertEqual(first_ids, self.helper_ids(), "the ids themselves moved")
        self.assertEqual(set(), self.tombstoned() & first_ids,
                         "a live symbol was tombstoned by a no-op rebuild")
        self.assert_nothing_evaporated(before)
        # ...and the key level: three distinct ordinals, each pinned to its id.
        self.assertEqual([0, 1, 2], sorted(key[3] for key in first))
        self.assertEqual(first, self.helpers(),
                         "a rebuild over an unchanged file moved a homonym's id")

    def test_a_vanished_homonym_is_tombstoned_and_the_others_keep_their_ids(self):
        self.git_init()
        self.build()
        before = self.helpers()
        retired = self.helper_id(2)          # the LAST block, the one removed below

        self.write_sources({HOMONYM_PATH: homonym_source(1, 2)})
        self.commit("drop the third block")
        out = self.build()
        self.assertIn("incremental", out, "the realistic path for a one-file edit")

        after = self.helpers()
        self.assertEqual(2, len(after))
        for ordinal in (0, 1):
            key = (HOMONYM_PATH, "helper", "function", ordinal)
            self.assertEqual(before[key], after[key],
                             f"ordinal {ordinal} was re-IDed by a sibling's removal")
        self.assertIn(retired, self.tombstoned(), "the disappeared symbol has no "
                                                  "tombstone — it evaporated")
        self.assertIn(bi.sid(retired), self.delta_ids("removed"))
        self.assert_nothing_evaporated(set(before.values()))

    # --- line shift: the property SYM-ID stability rests on ---------------
    def test_two_hundred_inserted_lines_move_no_id_and_no_ordinal(self):
        """A shift changes the start lines and nothing else — the reason the start
        line is in the ORDER and not in the key."""
        self.git_init()
        self.build()
        before = self.helpers()

        self.write_sources({HOMONYM_PATH: "\n" * 200 + homonym_source(1, 2, 3)})
        self.commit("insert 200 lines at the top")
        self.build()

        self.assertEqual([202, 207, 212], self.helper_starts(),
                         "the fixture did not actually shift — the arm would be vacuous")
        # The key CARRIES the ordinal, so one equality pins both: same ids, same
        # ordinals, same group.
        self.assertEqual(before, self.helpers())
        self.assertEqual(set(), self.tombstoned() & set(before.values()))

    # --- the assumed residual, written down -------------------------------
    def test_reordering_homonyms_swaps_their_ids_and_says_so(self):
        """RESIDUAL, BY DESIGN: identity follows the ordinal, so swapping the
        relative order of two homonyms swaps their SYM-IDs — and the hand-written
        annotation travels with the ID, i.e. it lands on the OTHER symbol.

        The alternative — putting the start line in the key — would move every id
        below an inserted line, which is the far worse failure (it invalidates
        every annotation and every cited SYM-NNNN in the repo, at every edit).
        A swap is rare, is confined to one (path, name, kind) group, and is
        INVISIBLE in the counters: the ranges are unchanged, so `changed` is empty.
        That silence is the reason this is written here rather than left to be
        discovered.
        """
        self.git_init()
        self.build()
        first = self.helper_id(0)
        self.annotate(first, "block one, annotated by hand")
        self.build()   # the annotation is now carried by the builder itself
        self.assertEqual("block one, annotated by hand", self.purpose_of(first))

        self.write_sources({HOMONYM_PATH: homonym_source(3, 2, 1)})
        self.commit("swap the first and last blocks")
        self.build()

        self.assertEqual(first, self.helper_id(0),
                         "ordinal 0 keeps its id — identity follows the ordinal")
        # ...and that id now describes a DIFFERENT body. Read the source at the
        # range the row publishes: this is the swap, made observable.
        row = next(s for s in self.rows() if s["id"] == first)
        body = "\n".join((self.root / HOMONYM_PATH).read_text(encoding="utf-8")
                         .splitlines()[row["start"] - 1:row["end"]])
        self.assertIn("return value + 3", body,
                      "the id should now sit on the block that moved into ordinal 0")
        self.assertEqual("block one, annotated by hand", self.purpose_of(first),
                         "the annotation follows the ID, so it now describes the "
                         "other symbol — the residual, stated")
        # And the swap is INVISIBLE in the counters: the group's ranges are
        # {2, 7, 12} before and after, so not one homonym id is reported changed.
        # (The two distinctly-named `class` rows around them DO move and ARE
        # reported — that is the normal case, where identity follows the name.)
        changed = self.delta_ids("changed")
        self.assertEqual([], [i for i in changed
                              if i in {bi.sid(v) for v in self.helpers().values()}],
                         "a reorder inside the group is invisible in the counters")
        self.assertEqual([2, 7, 12], self.helper_starts())
        self.assertEqual(set(), self.tombstoned(), "a reorder retires nothing")

    def test_removing_the_middle_homonym_retires_the_LAST_ordinal(self):
        """RESIDUAL, same root: ids are bound to ordinals, not to bodies. Delete
        the MIDDLE of three and the survivors keep ordinals 0 and 1 — so the third
        block inherits the second's id, and it is the LAST ordinal's id that is
        tombstoned. The invariant still holds (nothing evaporates); what moves is
        confined to the group.
        """
        self.git_init()
        self.build()
        before = self.helpers()
        self.write_sources({HOMONYM_PATH: homonym_source(1, 3)})
        self.commit("drop the middle block")
        self.build()

        after = self.helpers()
        self.assertEqual([0, 1], sorted(key[3] for key in after))
        self.assertEqual(before[(HOMONYM_PATH, "helper", "function", 0)],
                         after[(HOMONYM_PATH, "helper", "function", 0)])
        self.assertEqual(before[(HOMONYM_PATH, "helper", "function", 1)],
                         after[(HOMONYM_PATH, "helper", "function", 1)],
                         "ordinal 1 keeps its id and now describes block 3")
        self.assertEqual({before[(HOMONYM_PATH, "helper", "function", 2)]},
                         self.tombstoned() & set(before.values()))
        self.assert_nothing_evaporated(set(before.values()))

    # --- counters ---------------------------------------------------------
    def test_the_counters_never_list_the_same_id_twice(self):
        """`changed` listed the survivor once per collapsed homonym, which is how
        the loss stayed invisible in the summary line."""
        self.git_init()
        self.build()
        for field in ("added", "changed", "removed"):
            listed = self.delta_ids(field)
            self.assertEqual(len(set(listed)), len(listed), f"{field} has duplicates")
        self.assertEqual(3, sum(1 for row in self.delta()["added"]
                                if row["name"] == "helper"),
                         "the three homonyms must each be counted once as added")

        self.write_sources({HOMONYM_PATH: "\n" * 200 + homonym_source(1, 2, 3)})
        self.commit("shift")
        self.build()
        changed = self.delta_ids("changed")
        self.assertEqual(len(set(changed)), len(changed), "changed has duplicates")
        self.assertEqual(3, len([i for i in changed
                                 if i in {bi.sid(v) for v in self.helpers().values()}]),
                         "each shifted homonym is reported changed exactly once")
        for field in ("added", "removed"):
            self.assertEqual([], self.delta_ids(field),
                             f"a pure line shift must not {field} anything")

    # --- an index published under the OLD key ----------------------------
    def test_a_legacy_index_without_homonyms_is_not_re_ided_at_all(self):
        """The load-bearing compatibility arm, and the common case: every index
        published before this fix whose files carry no homonym group — this kit's
        own included. Each group is a singleton, a singleton's ordinal is 0, so the
        4-element key equals the old 3-element one and the first build after the
        fix rewrites nothing.
        """
        self.write_sources({HOMONYM_PATH: homonym_source(1)})
        self.git_init()
        with legacy_key():
            self.build()
        before = self.sym_lines()
        self.assertTrue(before, "the legacy build published nothing")

        self.build("--full")   # the first build after the fix, worst case for ids
        self.assertEqual(before, self.sym_lines(),
                         "a legacy index without homonyms must come through "
                         "byte-identical, row for row")
        self.assertEqual([], self.delta_ids("added"))
        self.assertEqual([], self.delta_ids("removed"))

    def test_a_legacy_index_that_already_collapsed_never_reuses_the_lost_ids(self):
        """NAMED, NOT PRESERVED: an index whose homonyms the legacy builder ALREADY
        evaporated cannot get those ids back — they are absent from the files, and
        the fix stops the loss, it does not undo it.

        What IS guaranteed, and is the part that matters for citations: the
        surviving id is not re-issued to anything, the resurrected homonyms take
        FRESH ids above the watermark (so no past `SYM-NNNN` silently resolves to a
        different symbol), and nothing outside the group moves. The survivor is
        re-paired at the ordinal its STALE start line puts it at, which need not be
        the block it originally described — that is the same in-group residual as
        the reorder arm, and it is bounded to the group.
        """
        with legacy_key():
            self.build()
            lost = self.helper_ids()
            self.assertEqual(3, len(lost), "the legacy build indexed fewer than 3")
            self.build()          # ...and the collapse happens here, on disk
        collapsed = self.helper_ids()
        self.assertEqual(1, len(collapsed),
                         "the legacy fixture did not lose anything — nothing to test")
        survivor = next(iter(collapsed))
        lost -= {survivor}
        self.assertEqual(2, len(lost))
        self.assertEqual(set(), lost & self.tombstoned(),
                         "the legacy loss is silent by definition: no tombstones")
        outside = {sid_: line for sid_, line in self.sym_lines().items()
                   if HOMONYM_PATH not in line}

        self.build("--full")
        after = self.helpers()
        self.assertEqual(3, len(after), "the homonyms are indexed again")
        self.assertIn(survivor, set(after.values()), "the survivor lost its id")
        fresh = set(after.values()) - {survivor}
        self.assertGreater(min(fresh), max(lost),
                           "a resurrected homonym took an id that a past session "
                           "may have cited — the watermark must forbid it")
        self.assertEqual(outside, {sid_: line for sid_, line in self.sym_lines().items()
                                   if HOMONYM_PATH not in line},
                         "the churn must stay inside the homonym group")

    # --- one convention, two modules -------------------------------------
    def test_the_ordinal_convention_is_the_sqlite_stores_convention(self):
        """The producer and the store MUST number identically. Two divergent
        conventions would be worse than the collapse this fixes: the DB would
        re-pair SYM-IDs one way and the builder another, and `--verify` would
        report identities that "moved" on an index nobody touched.

        `build_index.identity_keys` mirrors `migrate_index_to_db.assign_ordinals`
        (it cannot import it — migrate imports build_index). This arm is what makes
        the mirror a checked fact instead of a comment.
        """
        self.git_init()
        self.build()
        by_key, _by_id, _max_id = bi.load_existing(self.root)
        builder = {key: sym["id"] for key, sym in by_key.items()}
        store = mig.read_state(self.root).by_key()
        self.assertTrue(any(key[3] for key in builder),
                        "no homonym in the fixture — the arm would be vacuous")
        self.assertEqual(builder, store,
                         "the builder and the SQLite store disagree on the ordinal")


# --- T-00000102: stylesheets, and the volume that made them a risk -----------
# A front-end project's stylesheets were invisible to the index, so the index
# described an application it could not see half of. The fixture is deliberately
# NOT a token dump: it carries every shape the extractor has to arbitrate — a
# token set, a dark-theme override of the SAME token names (the homonym case the
# ordinal exists for), a simple selector, a comma list, a descendant selector, a
# `@media` prelude, `@keyframes`, `@layer`, a nested rule and a `var()` reference.
CSS_PATH = "src/styles/theme.css"
CSS_FIXTURE = """@layer base {
  :root {
    --brand: #3355ff;
    --ink: #101010;
    --gap: 8px;
  }
}

.card, .panel {
  color: var(--ink);
  border: 1px solid var(--brand);
}

.card code {
  padding: var(--gap);
}

.card > .title { font-weight: 600; }

.stack {
  gap: var(--gap);
  .nested-child { color: red; }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (prefers-color-scheme: dark) {
  :root {
    --brand: #99aaff;
    --ink: #f0f0f0;
  }
  .card { border-color: var(--brand); }
}
"""
DIRSCOPE_BYTES = re.compile(rb" \xc2\xb7 dirscope \S+")


@contextlib.contextmanager
def src_ext_without_css():
    """Restore `SRC_EXT` to its pre-T-00000102 value, for the negative arm.

    Patched on the MODULE, because that is where `_keep` and `scope_fingerprint`
    both read it at call time — which is exactly what lets ONE temp repo be built
    under both configurations and compared byte for byte.
    """
    original = bi.SRC_EXT
    bi.SRC_EXT = frozenset(original) - bi.CSS_EXT
    try:
        yield
    finally:
        bi.SRC_EXT = original


class StylesheetScopeTests(_Case):
    """The NEGATIVE arm, and it is the load-bearing one."""

    def wipe_index(self):
        for path in sorted(self.idx.iterdir()):
            if path.is_file():
                path.unlink()

    def test_a_repo_without_css_is_byte_identical_except_for_the_scope_stamp(self):
        """No stylesheet in the tree => the CSS work is inert, to the byte.

        Skip this arm and an extractor that emitted a spurious row on a .py file,
        a changed edge set or a shifted count would leave every positive assertion
        below green — green in exactly the case that covers every BACK-END project
        the kit indexes. So the comparison is the whole published artefact set, in
        bytes, not a count.

        The ONE intended difference is asserted rather than excused: `dirscope` now
        digests SRC_EXT, because widening the extension set must invalidate a
        published index or an incremental build would only ever pick up a
        stylesheet somebody happened to edit. That difference is measured HERE too,
        so the mechanism that makes the fix land is proven in the same case that
        proves nothing else moved.
        """
        self.git_init()
        with src_ext_without_css():
            self.build("--full")
            before = self.snapshot()
        self.wipe_index()
        self.build("--full")
        after = self.snapshot()

        self.assertEqual(sorted(before), sorted(after), "the artefact SET moved")
        for name in sorted(before):
            self.assertEqual(DIRSCOPE_BYTES.sub(b"", before[name]),
                             DIRSCOPE_BYTES.sub(b"", after[name]),
                             f"{name} changed on a repo with no stylesheet")
        # Non-vacuity of that substitution: the stamps really do differ, so the
        # forced rebuild that carries CSS into an existing consumer index is real.
        self.assertNotEqual(before[bi.MAIN_NAME], after[bi.MAIN_NAME],
                            "the dirscope stamp did NOT move — a consumer's "
                            "published index would never learn about .css")

    def test_widening_the_extension_set_forces_exactly_one_full_rebuild(self):
        """The self-healing path, and that it does not self-repeat."""
        self.git_init()
        with src_ext_without_css():
            self.build()
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out)
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))


class StylesheetExtractionTests(_Case):
    def setUp(self):
        super().setUp()
        self.write_sources({CSS_PATH: CSS_FIXTURE})

    def css_rows(self):
        return [s for s in self.rows()
                if not s["deleted"] and s.get("path") == CSS_PATH]

    def named(self, kind):
        return sorted(s["name"] for s in self.css_rows() if s["kind"] == kind)

    def test_tokens_and_simple_selectors_are_indexed_and_the_rest_is_not(self):
        self.git_init()
        self.build()
        self.assertTrue(self.css_rows(), "the stylesheet produced no symbol at all")

        # 1. The tokens. Highest-value rows, and the ones ctags cannot see at all.
        self.assertEqual(["--brand", "--brand", "--gap", "--ink", "--ink"],
                         self.named(bi.CSS_VAR_KIND))
        # 2/3. Named at-rules.
        self.assertEqual(["spin"], self.named(bi.CSS_KEYFRAMES_KIND))
        self.assertEqual(["base"], self.named(bi.CSS_LAYER_KIND))
        # 4. Simple selectors, a comma list split into its parts.
        selectors = self.named(bi.CSS_SELECTOR_KIND)
        for kept in (".card", ".panel", ".stack"):
            self.assertIn(kept, selectors)

        # ...and what is DELIBERATELY not a symbol.
        for rejected in (".card code", ".card > .title", ".card>.title", ":root",
                         ".nested-child", "from", "to", "0%",
                         "(prefers-color-scheme: dark)"):
            self.assertNotIn(rejected, selectors, f"{rejected!r} is not a symbol")
        self.assertEqual([], [n for n in self.named(bi.CSS_LAYER_KIND) if n != "base"])

    def test_every_row_starts_on_the_line_that_actually_declares_it(self):
        """The start line must be the REAL one, and indentation is the trap.

        Found by mutation: with the leading whitespace of a line buffered, the
        prelude buffer is never empty when the first real character arrives, so
        `buf_line` never advances and every INDENTED symbol inherits the start line
        of an earlier one. Measured on the fixture below, `--brand` was reported at
        line 1 instead of 3 — i.e. the defect landed squarely on the token rows,
        the highest-value thing this extractor exists to produce, and on nothing
        else. A wrong start line is not cosmetic: `resolve_edges` reads
        `lines[start-1:end]` to find `var()` references, `identity_keys` orders a
        homonym group by start, and the index's whole contract is "read only this
        range".

        Asserted as a property rather than as a table of line numbers, so the
        fixture can grow without the test needing an edit. It holds because no
        prelude in the fixture spans two lines.
        """
        lines = CSS_FIXTURE.splitlines()
        syms = bi.extract_css(CSS_FIXTURE, CSS_PATH)
        self.assertTrue(syms, "nothing extracted — the arm would be vacuous")
        for sym in syms:
            self.assertIn(sym["name"], lines[sym["start"] - 1],
                          f"{sym['name']} is reported at line {sym['start']}, "
                          f"which reads {lines[sym['start'] - 1]!r}")
            self.assertGreaterEqual(sym["end"], sym["start"])
        # Non-vacuity: the fixture must actually contain an INDENTED symbol below
        # line 1, or a builder that reported 1 for everything would pass.
        indented = [s for s in syms
                    if s["start"] > 1 and lines[s["start"] - 1].startswith(" ")]
        self.assertTrue(indented, "no indented symbol — the trap is not covered")
        self.assertGreater(len({s["start"] for s in syms}), 3,
                           "every symbol shares one start line")

    def test_every_published_row_survives_the_symbols_md_grammar(self):
        """The hard constraint behind "simple, whitespace-free" selectors.

        The name field of a row is read back as `\\S+` (ACTIVE_RE). A row named
        `.card code` would not parse on reload, its identity would be
        unrecoverable, and the next build would re-ID it — silently, at exit 0. So
        the property under test is a ROUND TRIP: every stylesheet row written is a
        row `_parse_rows` gives back.
        """
        self.git_init()
        self.build()
        text = bi._read(self.idx / bi.MAIN_NAME)
        written = [line for line in text.splitlines() if CSS_PATH in line]
        self.assertTrue(written, "no stylesheet row was published")
        parsed = [s for s in bi._parse_rows(text) if s.get("path") == CSS_PATH]
        self.assertEqual(len(written), len(parsed),
                         "a published stylesheet row does not parse back")
        for row in parsed:
            self.assertNotIn(" ", row["name"])

    def test_a_token_overridden_in_a_media_block_gets_its_own_ordinal_and_id(self):
        """The `@media` homonym — the case the 4-part identity exists for.

        Not a contrived one: measured on this repo's own `tokens.css`, 32 of 34
        distinct tokens are declared TWICE, once in `:root` and once in a
        dark-scheme override. Under a (path, name, kind) key that pair collapses
        and one of the two leaves the index with no tombstone (T-00000122).
        """
        self.git_init()
        self.build()
        keys = {k: i for k, i in self.identities().items() if k[0] == CSS_PATH}
        light = keys.get((CSS_PATH, "--brand", bi.CSS_VAR_KIND, 0))
        dark = keys.get((CSS_PATH, "--brand", bi.CSS_VAR_KIND, 1))
        self.assertIsNotNone(light, "no ordinal 0 for the light-theme token")
        self.assertIsNotNone(dark, "no ordinal 1 for the dark-theme override")
        self.assertNotEqual(light, dark, "the two declarations collapsed into one id")

        # And the pair must survive a rebuild with BOTH ids intact.
        self.build("--full")
        after = {k: i for k, i in self.identities().items() if k[0] == CSS_PATH}
        self.assertEqual(light, after.get((CSS_PATH, "--brand", bi.CSS_VAR_KIND, 0)))
        self.assertEqual(dark, after.get((CSS_PATH, "--brand", bi.CSS_VAR_KIND, 1)))

    def test_a_rule_resolves_an_edge_to_the_token_it_references(self):
        """`var(--brand)` in a rule must reach the row DECLARING `--brand`.

        Without the `--name` alternative in TOKEN_RE the stylesheet would be in the
        index and connected to nothing: `--brand` is not an identifier under the
        original pattern, and the bare `brand` it yields matches no symbol.
        """
        self.git_init()
        self.build()
        cards = [s for s in self.css_rows()
                 if s["name"] == ".card" and s["kind"] == bi.CSS_SELECTOR_KIND]
        self.assertTrue(cards, "no .card row to resolve an edge from")
        brand_ids = {s["id"] for s in self.css_rows()
                     if s["name"] == "--brand" and s["kind"] == bi.CSS_VAR_KIND}
        reached = set().union(*(set(c["uses"]) for c in cards))
        self.assertTrue(brand_ids & reached,
                        f"{sorted(reached)} does not reach --brand "
                        f"{sorted(brand_ids)}")

    def test_shifting_the_stylesheet_down_moves_no_id_and_no_ordinal(self):
        """The start line is in the ORDER, never in the KEY."""
        self.git_init()
        self.build()
        before = {k: i for k, i in self.identities().items() if k[0] == CSS_PATH}
        self.assertTrue(before, "nothing to keep stable")
        self.write_sources({CSS_PATH: "/* pad */\n" * 200 + CSS_FIXTURE})
        self.commit("shift")
        self.build()
        after = {k: i for k, i in self.identities().items() if k[0] == CSS_PATH}
        self.assertEqual(before, after, "a pure line shift re-ID'd a stylesheet row")
        self.assertEqual(set(), self.tombstoned(), "a shift tombstoned a row")


class StylesheetBoundTests(_Case):
    """The volume bound, and the exclusions that keep machine-written CSS out."""

    def test_a_huge_stylesheet_is_capped_and_the_tokens_are_what_survives(self):
        big = ":root{\n" + "".join(f"  --t{n}: {n}px;\n" for n in range(20)) + "}\n"
        big += "".join(f".gen-{n} {{ margin: {n}px; }}\n" for n in range(400))
        self.write_sources({"src/styles/big.css": big})
        self.git_init()
        out = self.build()

        rows = [s for s in self.rows()
                if not s["deleted"] and s.get("path") == "src/styles/big.css"]
        self.assertEqual(bi.MAX_CSS_SYMBOLS, len(rows),
                         "the per-stylesheet bound was not applied")
        # The bound is RANKED, not a head-of-file cut: every token survives it.
        self.assertEqual({f"--t{n}" for n in range(20)},
                         {s["name"] for s in rows if s["kind"] == bi.CSS_VAR_KIND},
                         "the cap dropped design tokens to keep selectors")
        # A silent truncation reads as full coverage, so it is logged.
        self.assertIn("capped at", out)
        self.assertIn(str(bi.MAX_CSS_SYMBOLS), out)

    def test_a_minified_bundle_is_excluded_by_name_and_by_shape(self):
        """Both rules, because neither is sufficient alone.

        Measured on this repo: the built bundle is `ui/assets/app.css` — it matches
        no `.min.`/`.bundle.` name rule at all, and is ONE line of 36 334
        characters yielding 390 ctags tags. So the NAME rule keeps such a file out
        of the source count when it is named conventionally, and the SHAPE rule
        catches the one that is not.
        """
        minified = "".join(f".c{n}{{margin:{n}px;padding:{n}px;color:#0{n % 10}0}}"
                           for n in range(600))
        self.write_sources({"src/styles/site.min.css": minified,
                            "src/styles/vendor.css": minified,
                            "src/styles/hand.css": ".ok { color: red; }\n"})
        self.git_init()
        out = self.build()

        files = bi.all_source_files(self.root)
        self.assertNotIn("src/styles/site.min.css", files,
                         "a .min.css file reached the source set")
        self.assertIn("src/styles/vendor.css", files)  # caught by shape, not name
        paths = {s.get("path") for s in self.rows() if not s["deleted"]}
        self.assertNotIn("src/styles/vendor.css", paths,
                         "a minified stylesheet produced rows")
        self.assertIn("src/styles/hand.css", paths,
                      "the hand-written arm produced nothing — the test is vacuous")
        # SUR STDERR depuis T-00000609 : la note par fichier a quitte
        # stdout, que `symbols.py --json` utilise pour sa charge.
        self.assertIn("minified/built stylesheet", self.derniere_err)

    def test_a_minified_JS_bundle_is_excluded_by_shape_not_only_by_name(self):
        """LE JS N'AVAIT QUE LA RÈGLE DE NOM, et c'est ce qui a coûté 26 % de
        l'index (T-00000609).

        `SKIP_FILE_RE` saute déjà `.min.js` et `.bundle.js` ; le bundle de ce
        dépôt, `.agents/ui/assets/app.js`, ne porte AUCUN de ces noms — 717 397
        octets sur 33 lignes — et produisait 2 051 des ~7 928 lignes d'index. Il
        bloquait aussi `migrate_index_to_db --resync`, donc la base advisory est
        restée figée plusieurs jours.

        LA GARDE PASSE AVANT `ctags_syms`, et c'est le point d'implémentation qui
        rend ce témoin non trivial : le CSS est dans `CTAGS_SKIP_EXT`, donc sa
        garde peut vivre dans son extracteur ; le JS est COUVERT par ctags, donc
        une garde placée après serait INERTE tout en ayant l'air d'exister."""
        minifie = "".join(f"class C{n}{{m{n}(){{return {n}}}}}" for n in range(400))
        self.assertGreater(len(minifie), bi.JS_MIN_BYTES_FOR_SHAPE_TEST,
                           "la fixture est sous le plancher — l'arm ne mesure rien")
        self.write_sources({
            "src/app/vendor.min.js": minifie,   # pris par le NOM
            "src/app/bundle.js": minifie,       # pris par la FORME seule
            "src/app/real.js": "export function ok() {\n  return 1;\n}\n",
        })
        self.git_init()
        out = self.build()

        fichiers = bi.all_source_files(self.root)
        self.assertNotIn("src/app/vendor.min.js", fichiers,
                         "un .min.js a atteint l'ensemble des sources")
        self.assertIn("src/app/bundle.js", fichiers)  # pris par la forme, pas le nom
        chemins = {s.get("path") for s in self.rows() if not s["deleted"]}
        self.assertNotIn("src/app/bundle.js", chemins,
                         "un bundle minifié a produit des lignes d'index")
        self.assertIn("src/app/real.js", chemins,
                      "l'arm écrit à la main n'a rien produit — le témoin est vacant")
        self.assertIn("minified/built bundle", self.derniere_err,
                      "la note d exclusion doit vivre sur STDERR")

    @unittest.skipUnless(bi.ctags_binary(), "universal-ctags absent")
    def test_la_garde_JS_passe_AVANT_le_retour_anticipe_de_ctags(self):
        """LE CONTRÔLE ARMÉ QUI MANQUAIT AU TÉMOIN CI-DESSUS (binôme, T-00000609).

        MESURÉ PAR MUTATION : la garde déplacée APRÈS `if ctags_syms: return
        ctags_syms`, le témoin ci-dessus ROUGIT avec ctags et passe VERT sans
        lui. Sur une CI ou chez un adoptant qui n'a pas ctags, il ne prouvait
        donc rien — et un refactor futur qui redescend la garde atterrirait vert
        pendant qu'elle redeviendrait inerte « en ayant l'air d'exister ».

        Ici on EXIGE d'abord que ctags ait émis quelque chose : sans ça
        l'assertion suivante est satisfaite par le vide."""
        minifie = "".join(f"class C{n}{{m{n}(){{return {n}}}}}" for n in range(400))
        self.write_sources({"src/app/bundle.js": minifie})
        tags = bi.extract_ctags_batch(self.root, ["src/app/bundle.js"],
                                      bi.ctags_binary(), bi.CTAGS_KINDS)
        self.assertTrue(
            tags.get("src/app/bundle.js"),
            "ctags n'a rien émis — le placement AVANT ctags n'est pas mesuré")
        self.assertEqual(
            [], bi.extract_file(self.root / "src/app/bundle.js",
                                "src/app/bundle.js", tags["src/app/bundle.js"]),
            "la garde n'a pas mordu alors que ctags avait couvert le fichier")

    def test_un_gros_LITTERAL_ne_fait_pas_passer_un_module_pour_un_bundle(self):
        """LA MOYENNE SEULE ÉTAIT UNE FAUSSE MARGE, et c'est le binôme qui l'a
        mesuré. J'annonçais « ~3× de marge » : c'était la marge contre les
        fichiers du dépôt tels qu'ils sont, pas contre la CLASSE des fichiers
        légitimes. Un module de 9 212 caractères sur 140 lignes bascule au-dessus
        de 200 dès qu'on y ajoute UNE ligne de 19 000 caractères — un SVG inline,
        une police base64, une sourcemap. Tous ses symboles disparaîtraient, avec
        pour seule trace un stdout que les hooks jettent.

        Le critère mesure donc où sont les SYMBOLES, pas où sont les octets."""
        corps = "".join(f"export function f{n}() {{\n  return {n};\n}}\n"
                        for n in range(60))
        blob = "export const DATA = '" + ("x" * 20000) + "';\n"
        self.write_sources({"src/app/avec_blob.js": corps + blob})
        self.git_init()
        self.build()
        chemins = {s.get("path") for s in self.rows() if not s["deleted"]}
        self.assertIn("src/app/avec_blob.js", chemins,
                      "un module écrit à la main a été pris pour un bundle "
                      "à cause d'UN gros littéral")

    def test_CONTROLE_NEGATIF_un_JS_minifie_SOUS_le_plancher_reste_indexe(self):
        """Sans lui, `JS_MIN_BYTES_FOR_SHAPE_TEST` n'est prouvé par rien — et une
        garde sans plancher retirerait de l'index le moindre fichier dense."""
        petit = "".join(f"class D{n}{{m{n}(){{return {n}}}}}" for n in range(40))
        self.assertLess(len(petit), bi.JS_MIN_BYTES_FOR_SHAPE_TEST,
                        "la fixture dépasse le plancher — le contrôle est vacant")
        self.write_sources({"src/app/dense.js": petit})
        self.git_init()
        self.build()
        chemins = {s.get("path") for s in self.rows() if not s["deleted"]}
        self.assertIn("src/app/dense.js", chemins,
                      "un fichier SOUS le plancher d'octets a été écarté")

    def test_a_stylesheet_is_never_reported_as_an_entry_point(self):
        self.write_sources({"src/index.css": ":root { --x: 1px; }\n",
                            "src/index.py": "def main():\n    return 1\n"})
        self.git_init()
        self.build()
        text = (self.idx / "CODEBASE_INDEX.md").read_text(encoding="utf-8")
        section = text.split("## Entry points")[1].split("##")[0]
        self.assertNotIn("index.css", section)
        self.assertIn("index.py", section, "the arm is vacuous — nothing matched")


# --------------------------------------------------------- T-00000541: shell
SH_PATH = "tools/deploy.sh"
# MEASURED on Universal Ctags 6.2.1, 2026-09-10, and the fixture is shaped BY
# that measurement rather than by the mechanism the plan assumed: a heredoc —
# quoted `<<'PYEOF'` OR bare `<<PYEOF` — leaks NOTHING but a `heredoc`-kind tag
# named after its delimiter. The dotted names come from Python embedded as an
# INLINE `-c '…'` argument, which ctags reads as ordinary shell text. So the
# fixture carries BOTH forms: the heredoc keeps the delimiter arm honest, the
# `-c '…'` block keeps the dotted-name arm from being vacuous.
SH_FIXTURE = '''#!/usr/bin/env bash
set -euo pipefail

deploy_release() {
  local target="$1"
  echo "deploying $target"
}

function rollback_release {
  echo "rolling back"
}

render_report() {
  "$PY" - <<'PYEOF'
import json
print(json.dumps({"ok": True}))
PYEOF
  "$PY" -c '
import hashlib
rows = [r.strip() for r in open("in.txt").read().splitlines()]
key = hashlib.sha256(rows[0].encode()).hexdigest()
'
}
'''
SH_PLAIN_PATH = "tools/plain.sh"
SH_PLAIN_FIXTURE = '''#!/usr/bin/env bash
set -euo pipefail
echo "this file declares no function at all"
'''
JS_ITER_PATH = "src/stream/reader.js"
# NOT a generator (`async *[Symbol.asyncIterator]()`): ctags kinds it `generator`,
# which CTAGS_KINDS drops for reasons that have nothing to do with T-00000541, so
# that shape would make the bound arm below pass on a technicality. This shape is
# kinded `method` — MEASURED. SYM-5496 carried that same kind in this repo's
# published index UNTIL T-00000609 removed the minified bundle from it; the shape
# is still the right one, and the arm below proves it on a FIXTURE, never on that
# row.
JS_ITER_FIXTURE = '''export class Reader {
  [Symbol.asyncIterator]() {
    return this;
  }
}
'''
SH_DOTTED_PATH = "tools/probe.sh"
SH_DOTTED_FIXTURE = '''#!/usr/bin/env bash
probe_once() {
  "$PY" -c '
import hashlib
digest = hashlib.sha256(b"x").hexdigest()
'
}
'''


@contextlib.contextmanager
def src_ext_without_sh():
    """Restore `SRC_EXT` to its pre-T-00000541 value, for the negative arm.

    Patched on the MODULE, exactly like `src_ext_without_css` and for the same
    reason: `_keep` and `scope_fingerprint` both read it at call time, which is
    what lets ONE temp repo be built under both configurations and compared.
    Subtraction rather than a literal set, so a future entry on `SRC_EXT` cannot
    make this helper silently narrow the scope it is meant to leave untouched.
    """
    original = bi.SRC_EXT
    bi.SRC_EXT = frozenset(original) - {".sh"}
    try:
        yield
    finally:
        bi.SRC_EXT = original


def _ctags_tags(path):
    """Raw ctags tags for ONE file — the armed control of every arm below.

    Every "X never reaches the index" assertion is satisfied by a parser that
    emitted nothing at all, so each such arm first proves ctags DID emit the
    thing it claims is filtered. Measured, not assumed: ctags' Sh output is
    version-dependent (BORNE 4), and a fixture that stops leaking must turn this
    file red rather than turn its assertions vacuous.
    """
    binary = bi.ctags_binary()
    proc = subprocess.run([binary, "--output-format=json", "--fields=+ne",
                           "-f", "-", str(path)],
                          capture_output=True, text=True)
    out = []
    for line in proc.stdout.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("_type") == "tag":
            out.append(j)
    return out


class ShellScopeTests(_Case):
    """The NEGATIVE arm, and it is the load-bearing one (same shape as CSS)."""

    def wipe_index(self):
        for path in sorted(self.idx.iterdir()):
            if path.is_file():
                path.unlink()

    def test_a_repo_without_shell_is_byte_identical_except_for_the_scope_stamp(self):
        """No `.sh` in the tree => the shell work is inert, to the byte.

        The base FIXTURE is pure Python, i.e. exactly the BACK-END project shape
        the kit indexes most often. If widening SRC_EXT moved a row, an edge set
        or a count on such a tree, every positive assertion below would still be
        green. So the comparison is the whole published artefact set, in bytes.

        The ONE intended difference is asserted rather than excused: `dirscope`
        digests SRC_EXT (`scope_fingerprint`), because widening the extension set
        MUST invalidate a published index — otherwise an incremental build would
        only ever pick up a shell script somebody happened to edit, which is the
        ghost-symbol defect T-00000543 documents.
        """
        self.git_init()
        with src_ext_without_sh():
            self.build("--full")
            before = self.snapshot()
        self.wipe_index()
        self.build("--full")
        after = self.snapshot()

        self.assertEqual(sorted(before), sorted(after), "the artefact SET moved")
        for name in sorted(before):
            self.assertEqual(DIRSCOPE_BYTES.sub(b"", before[name]),
                             DIRSCOPE_BYTES.sub(b"", after[name]),
                             f"{name} changed on a repo with no shell script")
        # Non-vacuity of that substitution: the stamps really do differ, so the
        # forced rebuild that carries .sh into an existing consumer index is real.
        self.assertNotEqual(before[bi.MAIN_NAME], after[bi.MAIN_NAME],
                            "the dirscope stamp did NOT move — a consumer's "
                            "published index would never learn about .sh")

    def test_widening_the_extension_set_forces_exactly_one_full_rebuild(self):
        """The self-healing path, and that it does not self-repeat.

        The anti-T-00000543 arm: an INCREMENTAL rebuild after a scope change
        leaves ghost symbols with duplicate SYM-IDs, so the one thing that must
        be proven is that `--if-stale` answers a widened SRC_EXT with a FULL.
        `assertIn("full", out)` would also pass on the word appearing anywhere in
        the summary, hence the anchored regex.
        """
        self.git_init()
        with src_ext_without_sh():
            self.build()
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertRegex(out, r"INDEX BUILT @ \S+ \[\w+, full,")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))


@unittest.skipUnless(bi.ctags_binary(), "universal-ctags not available")
class ShellExtractionTests(_Case):
    def setUp(self):
        super().setUp()
        self.write_sources({SH_PATH: SH_FIXTURE, SH_PLAIN_PATH: SH_PLAIN_FIXTURE})

    def sh_rows(self):
        return [s for s in self.rows()
                if not s["deleted"] and s.get("path") == SH_PATH]

    def test_a_bash_function_is_indexed_with_a_usable_range(self):
        """The positive arm: both bash function syntaxes, with `end > start`.

        ctags' Sh parser reports no `end` field, so the range comes from
        `_derive_ends`/`_block_end`. A collapsed one-line range is not cosmetic:
        the index's whole contract is "read only this range", and `resolve_edges`
        scans `lines[start-1:end]` for references.
        """
        self.git_init()
        self.build()
        rows = self.sh_rows()
        self.assertTrue(rows, "the shell script produced no symbol at all")
        by_name = {s["name"]: s for s in rows}
        for name in ("deploy_release", "rollback_release", "render_report"):
            self.assertIn(name, by_name, f"{name} is missing from the index")
            self.assertGreater(by_name[name]["end"], by_name[name]["start"],
                               f"{name} collapsed to a single line")
        lines = SH_FIXTURE.splitlines()
        for name, row in by_name.items():
            self.assertIn(name, lines[row["start"] - 1],
                          f"{name} is reported at line {row['start']}, which "
                          f"reads {lines[row['start'] - 1]!r}")

    def test_heredoc_delimiters_never_reach_the_index(self):
        """FORM: a heredoc delimiter is not a symbol, and ctags does emit one."""
        emitted = _ctags_tags(self.root / SH_PATH)
        self.assertTrue([j for j in emitted if j.get("kind") == "heredoc"],
                        "ctags emitted no heredoc tag — the arm is vacuous")
        self.git_init()
        self.build()
        published = {s["name"] for s in self.sh_rows()}
        for delimiter in ("PYEOF", "EOF", "SH"):
            self.assertNotIn(delimiter, published,
                             f"{delimiter} was published as a symbol")

    def test_dotted_names_from_embedded_python_are_dropped(self):
        """FORM: no published shell symbol carries `.`, `[` or `]`.

        ctags attributes the method calls it finds inside embedded Python to the
        HOST .sh file — `.hexdigest`, `[r.strip`, `rows[0].encode` all arrive as
        kind `function`. They are Python, they are not addressable in the shell
        file, and left in they would be ~14 % of this repo's shell rows.
        """
        leaked = [j for j in _ctags_tags(self.root / SH_PATH)
                  if j.get("kind") in bi.CTAGS_KINDS
                  and any(c in str(j.get("name") or "") for c in ".[]")]
        self.assertTrue(leaked, "ctags leaked no dotted name — the arm is vacuous")
        self.git_init()
        self.build()
        for row in self.sh_rows():
            for char in ".[]":
                self.assertNotIn(char, row["name"],
                                 f"{row['name']!r} is embedded Python, not shell")

    def test_a_shell_file_without_functions_counts_as_a_file_not_a_symbol(self):
        """A `.sh` with no function widens the FILE count and nothing else."""
        self.git_init()
        self.build()
        self.assertIn(SH_PLAIN_PATH, bi.all_source_files(self.root),
                      "a function-free .sh fell out of the scope entirely")
        self.assertEqual([], [s for s in self.rows()
                              if s.get("path") == SH_PLAIN_PATH],
                         "a function-free .sh produced a symbol row")


@unittest.skipUnless(bi.ctags_binary(), "universal-ctags not available")
class BareIdentifierPredicateBoundTests(_Case):
    """The ONE arm that can see the predicate overflow onto another language.

    The two `ShellScopeTests` arms vary SRC_EXT and never `_tag_to_sym`: they are
    green whether the guard is bounded to `.sh` or deletes dotted names from
    every ctags language. `_tag_to_sym` is the single filter for ALL of them, and
    the named victim WAS real — SYM-5496, `[Symbol.asyncIterator]` in
    `.agents/ui/assets/app.js`, was a published row of this repo's own index
    until T-00000609 took that minified bundle out. The victim class is unchanged
    (any bracketed JS member name), and this arm has always proved it on a
    FIXTURE, so nothing here depended on that row surviving — it is named now as
    the measurement that MOTIVATED the arm, not as a live citation.
    """

    def test_the_bare_identifier_predicate_is_shell_only(self):
        self.write_sources({JS_ITER_PATH: JS_ITER_FIXTURE,
                            SH_DOTTED_PATH: SH_DOTTED_FIXTURE})
        self.git_init()
        self.build()
        rows = [s for s in self.rows() if not s["deleted"]]
        js_names = {s["name"] for s in rows if s.get("path") == JS_ITER_PATH}
        self.assertIn("[Symbol.asyncIterator]", js_names,
                      "the guard deleted a JavaScript row it must never see")
        sh_names = {s["name"] for s in rows if s.get("path") == SH_DOTTED_PATH}
        self.assertNotIn(".hexdigest", sh_names,
                         "a dotted name survived on the shell side")
        self.assertFalse([n for n in sh_names
                          if any(c in n for c in ".[]")],
                         f"dotted names survived on the shell side: {sh_names}")


# --- T-00000104: the summary must not promise a trigger that does not exist ---
class AnnotationBacklogWordingTests(_Case):
    def test_the_backlog_line_states_a_count_and_a_deliberate_step(self):
        """`indexer` is a CONDITIONAL, annotation-only stage nobody schedules.

        The line used to read `needs purpose: N symbol(s) -> indexer annotates the
        delta`. Measured on a consumer project N was 5947: a five-digit number in
        front of an arrow promising automatic work that never happens, which reads
        as a queue draining itself. The count is useful and stays; the false
        trigger goes.
        """
        self.git_init()
        out = self.build()
        self.assertIn("carry no ':: purpose'", out)
        self.assertIn("DELIBERATE step, nothing triggers it", out)
        self.assertIn("indexer", out)
        self.assertIn(bi.DELTA_NAME, out)
        # The count is still there, and it is the real one.
        expected = len(self.delta()["needs_purpose"])
        self.assertTrue(expected, "no unannotated symbol — the arm is vacuous")
        self.assertIn(f"- {expected} symbol(s) carry no", out)
        # And the promise is gone.
        self.assertNotIn("indexer annotates the delta", out)
        self.assertNotIn("indexer fills Role/Owner", out)
        self.assertNotIn("needs purpose:", out)
        self.assertNotIn("needs module role:", out)

    def test_the_module_role_line_says_the_same_thing(self):
        self.git_init()
        out = self.build()
        expected = len(self.delta()["needs_module_role"])
        self.assertTrue(expected, "no unannotated module — the arm is vacuous")
        self.assertIn(f"- {expected} module(s) carry no Role/Owner", out)
        self.assertIn("same deliberate step, not triggered", out)


# --- T-00000377: body_sha, the lateral map, and the rebuild it forces --------
class BodyHashTests(unittest.TestCase):
    """`body_hash` alone — a pure function, tested without a repo.

    Each immunity is asserted WITH ITS ARMED CONTROL in the same class: an
    always-equal hash would satisfy every "identical" case above and prove
    nothing, so the case that must DIFFER sits next to them.
    """

    BODY = ["def f(x):", "    if x:", "        return 1", "    return 0"]

    def test_body_hash_is_identical_in_LF_and_CRLF(self):
        """The `--linux` replay of verify.sh reads the same tree with LF."""
        crlf = [line + "\r" for line in self.BODY]  # what splitlines() leaves
        self.assertEqual(bi.body_hash(self.BODY, 1, 4), bi.body_hash(crlf, 1, 4))

    def test_body_hash_ignores_trailing_space_but_not_leading_indentation(self):
        padded = [line + "   \t" for line in self.BODY]
        self.assertEqual(bi.body_hash(self.BODY, 1, 4), bi.body_hash(padded, 1, 4))
        # The armed control of THIS immunity: indentation is content, and moving a
        # function into a class must not read as "unchanged".
        indented = ["    " + line for line in self.BODY]
        self.assertNotEqual(bi.body_hash(self.BODY, 1, 4),
                            bi.body_hash(indented, 1, 4))

    def test_one_changed_character_in_the_body_changes_the_sha(self):
        """The armed control (L-00000133): a hash that never moves proves nothing."""
        changed = list(self.BODY)
        changed[2] = "        return 2"
        self.assertNotEqual(bi.body_hash(self.BODY, 1, 4),
                            bi.body_hash(changed, 1, 4))

    def test_a_range_outside_the_file_is_None_and_never_the_empty_hash(self):
        empty_hash = bi.body_hash([""], 1, 1)
        for start, end in ((1, 99), (0, 2), (5, 4), (None, 4), (1, None)):
            with self.subTest(start=start, end=end):
                value = bi.body_hash(self.BODY, start, end)
                self.assertIsNone(value, f"{start}-{end} produced {value!r}")
                self.assertNotEqual(empty_hash, value)


class BodyMapTests(_Case):
    """The lateral `INDEX_BODIES.json`: coverage, carry-over, and its refusals."""

    def bodies(self) -> dict:
        return json.loads((self.idx / bi.BODIES_NAME).read_text(encoding="utf-8"))

    def live_ids(self) -> set:
        return {s["id"] for s in self.rows() if not s["deleted"]}

    def test_a_build_hashes_every_live_symbol_and_stamps_its_generation(self):
        self.git_init()
        self.build()
        payload = self.bodies()
        self.assertEqual(bi.BODY_ALGO, payload["algo"])
        self.assertEqual(bi._generation(bi._read(self.idx / bi.MAIN_NAME)),
                         payload["generation"])
        self.assertTrue(self.live_ids(), "no live symbol — the arm is vacuous")
        self.assertEqual({str(i) for i in self.live_ids()}, set(payload["bodies"]))

    def test_write_bodies_emits_no_entry_for_a_tombstone(self):
        self.git_init()
        self.build()
        gone = {(p, n, k): i for (p, n, k), i in self.ids().items()
                if n == "alpha_two"}
        self.assertEqual(1, len(gone), "fixture changed — the arm is vacuous")
        doomed = next(iter(gone.values()))
        self.write_sources({"src/alpha/one.py": "def alpha_one(x):\n    return x\n"})
        self.commit("drop alpha_two")
        self.build()
        self.assertIn(doomed, self.tombstoned(), "setup: nothing was tombstoned")
        self.assertNotIn(str(doomed), self.bodies()["bodies"],
                         "a tombstone carries a body hash")

    def test_a_ten_line_shift_keeps_body_sha_and_the_sym_id(self):
        """The identity property, measured on the HASH as well as on the id.

        Ten blank lines above a function move its `start`/`end` and nothing else.
        The SYM-ID must not move (L-00000138, the ordinal keeps the line out of
        the key) and neither must the hash — otherwise every unrelated insertion
        would report the whole file below it as DRIFTED.
        """
        self.git_init()
        self.build()
        before_ids = self.ids()
        before = self.bodies()["bodies"]
        self.write_sources({"src/alpha/one.py":
                            "\n" * 10 + FIXTURE["src/alpha/one.py"]})
        self.commit("shift alpha down")
        self.build()
        after_ids, after = self.ids(), self.bodies()["bodies"]
        self.assertEqual(before_ids, after_ids, "a SYM-ID moved on a pure shift")
        shifted = [i for (path, _n, _k), i in after_ids.items()
                   if path == "src/alpha/one.py"]
        self.assertTrue(shifted, "the arm is vacuous — nothing in the shifted file")
        for sym_id in shifted:
            with self.subTest(sym_id=sym_id):
                start = [s["start"] for s in self.rows() if s["id"] == sym_id][0]
                self.assertGreater(start, 10, "the shift did not actually happen")
                self.assertEqual(before[str(sym_id)], after[str(sym_id)])

    def test_missing_body_map_forces_ONE_full_rebuild_that_covers_every_live_symbol(self):
        """↯ C1 — the count is of HASHES, not of files.

        A PRESENT artefact is not a POPULATED one: were the condition read from
        `index_is_current` instead, the forced rebuild would stay incremental over
        an empty scope and publish a valid, EMPTY map that nothing would ever fix.
        So this asserts coverage, then asserts the rebuild happened exactly once.
        """
        self.git_init()
        self.build()
        expected = self.live_ids()
        self.assertTrue(expected, "no live symbol — the arm is vacuous")
        (self.idx / bi.BODIES_NAME).unlink()
        # Nothing else is stale: without the lateral, this would say CURRENT.
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out)
        self.assertIn("full", out, "the forced rebuild stayed incremental")
        self.assertEqual({str(i) for i in expected}, set(self.bodies()["bodies"]),
                         "the rebuilt map does not cover every live symbol")
        # Exactly ONE: self-healing, not self-repeating.
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.assertIn("INDEX CURRENT", self.build("--stale-check"))

    def test_a_lateral_from_another_generation_is_UNKNOWN_in_bulk(self):
        """Not partially believed — the whole map, or none of it."""
        self.git_init()
        self.build()
        payload = self.bodies()
        real = dict(payload["bodies"])
        self.assertTrue(real, "the arm is vacuous — an empty map proves nothing")
        stamp = payload["generation"]
        payload["generation"] = "deadbee"
        (self.idx / bi.BODIES_NAME).write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        bodies, note = bi.read_bodies(self.root, stamp)
        self.assertEqual({}, bodies)
        self.assertIsNotNone(note)
        self.assertIn("UNKNOWN", note)
        # ...and the same disagreement forces the full rebuild, like an absence.
        self.assertIn("full", self.build("--if-stale"))
        self.assertEqual(real, self.bodies()["bodies"], "the rebuild lost a hash")

    def test_a_wrong_algo_is_refused_whole_even_at_the_right_generation(self):
        self.git_init()
        self.build()
        payload = self.bodies()
        payload["algo"] = "sha1-8"
        (self.idx / bi.BODIES_NAME).write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        bodies, note = bi.read_bodies(self.root, payload["generation"])
        self.assertEqual({}, bodies)
        self.assertIn(bi.BODY_ALGO, note or "")

    def test_an_incremental_build_carries_untouched_files_hashes_forward(self):
        """The out-of-scope half: a hash nobody recomputed must not be dropped."""
        self.git_init()
        self.build()
        before = dict(self.bodies()["bodies"])
        beta_ids = {str(i) for (path, _n, _k), i in self.ids().items()
                    if path == "src/beta/two.py"}
        self.assertTrue(beta_ids, "the arm is vacuous — beta is not indexed")
        self.write_sources({"src/alpha/one.py": FIXTURE["src/alpha/one.py"]
                            + "\n\ndef alpha_three(x):\n    return x\n"})
        self.commit("touch alpha only")
        out = self.build()
        self.assertIn("incremental", out, "the arm is vacuous — it rebuilt in full")
        after = self.bodies()["bodies"]
        for sym_id in sorted(beta_ids):
            with self.subTest(sym_id=sym_id):
                self.assertEqual(before[sym_id], after[sym_id])


class ExtractScopeParityTests(_Case):
    """T-00000378 -- THE PARITY NET, and why it is a net and not a refactor.

    `extract_scope` is the extraction half of `reconcile`, LIFTED into a pure
    function so the read side (`symbols.py`'s freshness overlay) can call it
    without dragging identity, tombstoning and edge resolution along. The two
    copies are deliberate: `reconcile` is the Stop-hook WRITE path, and routing it
    through a function whose other caller is a query would put a read-side bug on
    the builder's critical path. What keeps a deliberate duplication honest is a
    test that runs BOTH over the same file set and compares (L-00000221:
    unification PAR FILET). Without this class the two drift and nothing says so.
    """

    def rows_from_reconcile(self, rels) -> dict:
        symbols, _delta = bi.reconcile(self.root, list(rels), bi.ctags_binary(),
                                       bi.CTAGS_KINDS)
        out: dict = {}
        for s in symbols:
            if s.get("deleted") or s.get("path") not in rels:
                continue
            out.setdefault(s["path"], set()).add(
                (s["name"], s["kind"], s["start"], s["end"]))
        return out

    def rows_from_scope(self, rels) -> dict:
        extracted = bi.extract_scope(self.root, list(rels), bi.ctags_binary(),
                                     bi.CTAGS_KINDS)
        return {rel: {(s["name"], s["kind"], s["start"], s["end"]) for s in rows}
                for rel, rows in extracted.items() if rows}

    def test_extract_scope_returns_exactly_what_reconcile_extracts(self):
        rels = sorted(FIXTURE)
        mine, theirs = self.rows_from_scope(rels), self.rows_from_reconcile(rels)
        self.assertTrue(mine, "both sides empty -- the parity would be vacuous")
        self.assertEqual(theirs, mine)

    def test_parity_holds_after_an_insertion_shifts_every_range(self):
        """The case the overlay exists for: if the two paths disagreed only once
        a line moved, a parity taken on a pristine tree would prove nothing."""
        self.write_sources({"src/alpha/one.py": "# probe\n# probe\n"
                            + FIXTURE["src/alpha/one.py"]})
        rels = sorted(FIXTURE)
        self.assertEqual(self.rows_from_reconcile(rels), self.rows_from_scope(rels))

    def test_a_file_absent_from_disk_is_absent_from_the_map_not_empty_in_it(self):
        """`{}` and `{rel: []}` are different claims. An entry means "read and
        understood, holds no symbol"; an ABSENCE means "there was nothing to
        read". A caller that cannot tell them apart tombstones a file it never
        opened -- which is exactly what the read side must never do."""
        rels = sorted(FIXTURE) + ["src/alpha/never_written.py"]
        extracted = bi.extract_scope(self.root, rels, bi.ctags_binary(),
                                     bi.CTAGS_KINDS)
        self.assertNotIn("src/alpha/never_written.py", extracted)
        self.assertIn("src/alpha/one.py", extracted)

    def test_a_suffix_no_extractor_knows_gets_an_EMPTY_entry_not_an_absence(self):
        """The lift stays FAITHFUL: `extract_file` answers `[]` for an unknown
        suffix inside `reconcile` too. Deciding that `[]` means NOT COVERED is
        the caller's judgement, and it is made in `symbols.py`, on the read side
        that must stay conservative -- not smuggled in here, where it would
        change what the builder sees."""
        self.write_sources({"src/alpha/thing.rb": "def ruby_thing\n  1\nend\n"})
        extracted = bi.extract_scope(self.root, ["src/alpha/thing.rb"],
                                     None, bi.CTAGS_KINDS)
        self.assertEqual({"src/alpha/thing.rb": []}, extracted)

    def test_a_rel_escaping_the_root_is_reported_empty_and_never_read(self):
        """T-00000378 hardening -- a `rel` is a store `path` column, a committed
        binary forgeable by whoever lands a row. An absolute path or a `../`
        climber must be confined BEFORE ctags or read_text dereferences it, or a
        query prints an arbitrary file into an agent's context. The escape is NOT
        read: it gets an EMPTY entry (NOT COVERED), never GONE, never a raise."""
        sub = self.root / "sub"
        sub.mkdir()
        outside = self.root / "outside_secret.py"
        outside.write_text("def outside_secret(x):\n    return x\n",
                           encoding="utf-8")
        rels = ["../outside_secret.py", str(outside.resolve())]
        extracted = bi.extract_scope(sub, rels, bi.ctags_binary(), bi.CTAGS_KINDS)
        for rel in rels:
            self.assertIn(rel, extracted, f"{rel!r} was dropped, not reported")
            self.assertEqual([], extracted[rel],
                             f"{rel!r} was READ -- confinement failed")

        # Witness: the SAME source held INSIDE the root does extract a symbol, so
        # `[]` above means "not read", never "a .py holds nothing to read".
        (sub / "inside.py").write_text("def outside_secret(x):\n    return x\n",
                                       encoding="utf-8")
        within = bi.extract_scope(sub, ["inside.py"], bi.ctags_binary(),
                                  bi.CTAGS_KINDS)
        self.assertTrue(within["inside.py"],
                        "witness: the same source extracts a symbol INSIDE root")


# --- T-00000386: LF at publication (Windows CRLF regression) -----------------
# `.gitattributes` pins `eol=lf` for the published index artefacts, but a
# text-mode write with the DEFAULT `newline` translates `\n` to the platform
# separator on write — CRLF under Windows — so every index build on Windows
# dirtied the whole working tree (L-00000277). `_Publisher.write` now forces
# `newline="\n"`, the single publication channel through which MAIN, shards,
# annotate targets, DELTA and BODIES all pass.
#
# PLATFORM SCOPE, stated so the coverage is not misread (L-00000079): the defect
# is Windows-ONLY. On POSIX the text-mode default never emits CRLF — verified:
# monkeypatching `os.linesep` does NOT change TextIOWrapper's write translation,
# it is fixed at the C level per platform — so a bare "no CR after a build"
# assertion is trivially green here and would stay green even with the fix
# reverted. `_WindowsFdopen` arms the net on ANY host: it reproduces Windows'
# translation at the exact `os.fdopen` call the publisher makes, so the focused
# arm below goes RED on a reverted publisher even on Linux/macOS.
class _WindowsFdopen:
    """A stand-in for `os.fdopen` that translates like a Windows text stream.

    Windows opens a text-mode stream whose `newline` is unset as CRLF-translating
    on write. This mirrors exactly that: passed no `newline`, the returned stream
    writes `\n` as `\r\n`; passed `newline="\n"` (the fix), that is honoured
    verbatim. So it fails a publisher that dropped the kwarg and passes the fixed
    one, on every platform — which is what makes the Linux CI arm non-vacuous.
    """

    def __init__(self):
        self._real = os.fdopen  # captured before the module attribute is patched

    def __call__(self, fd, mode="r", *args, **kwargs):
        if "b" not in mode and "newline" not in kwargs:
            kwargs["newline"] = "\r\n"
        return self._real(fd, mode, *args, **kwargs)


class LineEndingPublishTests(_Case):
    """T-00000386 / L-00000277: the published index is LF on every platform."""

    # index.db is BINARY — a `\r` byte there is legitimate payload, so scanning it
    # for CR would be a near-certain false positive (reserve C1). Excluded by name.
    # It no longer lives in this directory at all (machine store outside the
    # repository, T-00000668) and a plain build never writes it, so this is
    # defensive — a legacy duplicate left at the old path — and documentary; the
    # scan is BOUNDED to the published TEXT artefacts.
    _BINARY = {mig.DB_NAME}

    def _text_artefacts(self):
        return [p for p in sorted(self.idx.iterdir())
                if p.is_file() and p.name not in self._BINARY
                and not p.name.startswith(bi.TMP_PREFIX)]

    def test_a_real_build_publishes_no_CR_on_any_text_artefact(self):
        self.build("--threshold", "1")  # a small threshold forces shards too
        published = {p.name for p in self._text_artefacts()}
        # The four published families must be present, or the scan proves nothing.
        for expected in (bi.MAIN_NAME, bi.DELTA_NAME, bi.BODIES_NAME,
                         "CODEBASE_INDEX.md"):
            self.assertIn(expected, published, f"{expected} was not published")
        for path in self._text_artefacts():
            self.assertNotIn(b"\r", path.read_bytes(),
                             f"{path.name} carries a CR — LF was not forced")

    def test_the_publisher_forces_LF_even_when_the_platform_would_add_CR(self):
        """The non-vacuous arm — RED on a reverted fix, on Linux/macOS too.

        With `os.fdopen` translating like Windows, a publisher that omitted
        `newline="\n"` would write CRLF here; the fix keeps the output LF. This is
        the arm reserve C4 asks for, using an `os.fdopen` Windows-simulator rather
        than an `os.linesep` monkeypatch (which, measured, does not arm the net —
        TextIOWrapper's translation is platform-fixed, not read from os.linesep).
        """
        target = self.root / "artefact.md"
        text = "line one\nline two\n"
        saved = bi.os.fdopen
        bi.os.fdopen = _WindowsFdopen()
        try:
            bi._Publisher().write(target, text)
        finally:
            bi.os.fdopen = saved
        raw = target.read_bytes()
        self.assertNotIn(b"\r", raw, "the publisher did not force LF under a "
                                     "CRLF-translating platform")
        self.assertEqual(text.encode("utf-8"), raw)
        self.assert_no_residue()


class CommitSansImpactTests(_Case):
    """UN COMMIT QUI NE TOUCHE AUCUN FICHIER INDEXÉ NE PÉRIME PLUS L'INDEX.

    T-00000575, décision pilote « option C » du 2026-09-13. `index_is_current`
    exigeait `built @ == HEAD` ; or TOUT commit avance HEAD. Un commit de docs,
    de board ou de plan rendait donc l'index « périmé », `--if-stale`
    reconstruisait, la reconstruction réécrivait les fichiers d'index, l'arbre
    devenait sale, un `chore(index)` suivait — qui avançait HEAD à son tour.
    Mesuré avec `_keep()` : **125 des 200 derniers commits du kit, soit 62 %**,
    ne touchent aucun fichier indexé — 125 à l'ancre `6ffd81c`, le compte
    glissant entre 124 et 127 selon le commit d'où l'on mesure.

    CE PRÉDICAT GOUVERNE LE DÉMARRAGE DE SESSION (`session-start.sh --if-stale`)
    et n'avait AUCUN banc avant celui-ci — relevé du binôme. C'est la raison
    d'être de cette classe : un changement de sémantique sur ce chemin-là ne
    peut pas reposer sur une vérification manuelle.

    LES QUATRE TÉMOINS QUI SUIVENT LES DEUX PREMIERS VIENNENT DU BINÔME, et
    chacun ferme une façon d'être « à jour » pour une raison qui n'est PAS
    « rien n'a changé ». C'est la classe de défaut que le retrait du SHA a
    ouverte : tant que `built @ == HEAD` décidait aussi, un scope vide par
    accident était rattrapé par le sha. Il ne l'est plus par rien.
    """

    def test_un_commit_docs_ne_declenche_PLUS_de_reconstruction(self):
        self.git_init()
        self.build()
        (self.root / "NOTES.md").write_text("de la prose\n", encoding="utf-8")
        self.commit("docs seulement")
        out = self.build("--if-stale")
        self.assertIn("INDEX CURRENT", out,
                      "un commit sans fichier indexé a relancé une reconstruction")

    def test_CONTROLE_NEGATIF_un_fichier_indexe_declenche_TOUJOURS(self):
        """Sans lui, la correction serait indistinguable d'un `--if-stale` mort."""
        self.git_init()
        self.build()
        (self.root / "zz_neuf.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        self.commit("du vrai code")
        out = self.build("--if-stale")
        self.assertIn("INDEX BUILT @", out,
                      "un fichier indexé neuf n'a PAS déclenché de reconstruction")

    def test_un_fichier_indexe_DEVENU_TROP_GROS_perime_quand_meme(self):
        """SCOPE VIDE POUR UNE RAISON QUI N'EST PAS « RIEN N'A CHANGÉ » — nº 1.

        Mesuré par le binôme sur un dépôt jetable : `_keep(f, root, …)` STATE
        l'arbre, donc un fichier indexé qui franchit `MAX_FILE_BYTES` sort du
        scope, le scope devient vide, et l'index se déclare à jour en gardant
        les symboles MORTS du fichier — définitivement, `--if-stale` étant le
        seul chemin automatisé. Le prédicat de fraîcheur filtre donc désormais
        SANS la racine ; la construction, elle, la garde."""
        self.git_init()
        (self.root / "gros.py").write_text("def petit():\n    return 1\n", encoding="utf-8")
        self.commit("petit")
        self.build()
        (self.root / "gros.py").write_text(
            "def autre():\n    return 2\n" + "# rembourrage\n" * 150000, encoding="utf-8")
        self.commit("devenu enorme")
        self.assertIn("INDEX BUILT @", self.build("--if-stale"),
                      "un fichier sorti du périmètre par sa TAILLE a laissé ses symboles morts")

    def test_un_DIFF_EN_ECHEC_ne_se_lit_PAS_rien_n_a_change(self):
        """SCOPE VIDE POUR UNE RAISON QUI N'EST PAS « RIEN N'A CHANGÉ » — nº 2.

        `git()` rend `None` sur rc≠0 et le `if out:` d'origine l'avalait. Le
        binôme a exhibé le cas réel : clone partiel hors ligne, `cat-file -e`
        rend 0 sur le commit tamponné mais `git diff <built> HEAD` échoue sur un
        arbre absent. Ancien code : STALE. Nouveau code sans garde : CURRENT,
        avec des fichiers indexés hors de l'index. On simule l'échec là où il
        se produit — la première jambe, celle qui porte la mesure."""
        self.git_init()
        self.build()
        (self.root / "NOTES.md").write_text("de la prose\n", encoding="utf-8")
        self.commit("docs seulement")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"), "prémisse fausse")

        vrai_git = bi.git

        def git_qui_echoue(root, *args):
            if args[:2] == ("diff", "--name-only") and len(args) > 3:
                return None  # rc != 0 : l'arbre n'est pas là
            return vrai_git(root, *args)

        bi.git = git_qui_echoue
        try:
            out = self.build("--if-stale")
        finally:
            bi.git = vrai_git
        self.assertIn("INDEX BUILT @", out,
                      "un `git diff` en ÉCHEC a été lu comme « aucun fichier n'a bougé »")

    def test_un_changement_du_BUILDER_perime_l_index_MEME_hors_perimetre(self):
        """T-00000606 — LA RÉGRESSION ADOPTANT, fermée et gelée.

        Depuis que le sha ne décide plus (T-00000575), rien ne portait un
        changement du BUILDER : `SKIP_FILE_RE`, `MAX_FILE_BYTES`, un extracteur
        n'entrent ni dans `SRC_EXT`, ni dans `SKIP_DIRS`, ni dans
        `SKIP_PREFIXES`. Sur le kit c'était masqué — `.agents/bin/*.py` est
        indexé, donc dans le scope. Sur un ADOPTANT, où `.agents` est dans
        `host_skip`, un upgrade du kit n'atterrissait JAMAIS par `--if-stale`.

        CE TÉMOIN SE PLACE DU CÔTÉ ADOPTANT, le seul où le défaut est visible :
        `host_skip` reçoit `.agents`, donc le builder est HORS périmètre indexé,
        et c'est bien son DIGEST — pas son chemin — qui doit périmer l'index.

        SUR UNE COPIE, JAMAIS SUR LE FICHIER DU DÉPÔT. La première rédaction
        écrivait dans `build_index.py` puis le restaurait sous `finally` : un
        `finally` ne survit ni à un kill, ni à une porte qui tourne en même
        temps, ni à une exécution parallèle. Un banc n'a aucune raison de
        pouvoir corrompre l'outil qu'il mesure."""
        import importlib.util

        source = Path(bi.__file__).read_bytes()
        copie = self.root / "builder_copie.py"

        def empreinte_de(octets):
            copie.write_bytes(octets)
            spec = importlib.util.spec_from_file_location("bi_copie", copie)
            mod = importlib.util.module_from_spec(spec)
            # unregistered on purpose: cette copie est une SOURCE MUTÉE du
            # builder, chargée pour comparer deux empreintes. L'inscrire dans
            # `sys.modules` la laisserait derrière elle pour les tests suivants,
            # et `scope_fingerprint` digère `Path(__file__)` — donc le module
            # enregistré rendrait l'empreinte de la MUTATION, pas celle du
            # dépôt. C'est exactement le contraire de ce que ce banc mesure.
            spec.loader.exec_module(mod)
            return mod.scope_fingerprint({".agents"})

        avant = empreinte_de(source)
        apres = empreinte_de(source + b"\n# un extracteur a change\n")
        self.assertNotEqual(
            avant, apres,
            "un changement du builder ne périme pas l'index — la régression "
            "adoptant est rouverte")
        # ET LE FICHIER DU DÉPÔT N'A PAS BOUGÉ : la borne du banc, gelée.
        self.assertEqual(source, Path(bi.__file__).read_bytes(),
                         "le banc a écrit dans le builder du dépôt")

    def test_CONTROLE_NEGATIF_l_empreinte_est_STABLE_a_builder_constant(self):
        """Sans lui, une empreinte qui changerait à CHAQUE appel passerait le
        témoin ci-dessus tout en forçant une reconstruction complète à chaque
        démarrage de session — un remède pire que le mal."""
        vues = {bi.scope_fingerprint({".agents"}) for _ in range(5)}
        self.assertEqual(len(vues), 1, f"l'empreinte n'est pas stable : {vues}")
        self.assertNotEqual(bi.scope_fingerprint({".agents"}),
                            bi.scope_fingerprint(set()),
                            "l'empreinte ne distingue plus les périmètres d'hôte")

    def test_le_RESTE_DE_L_EMPREINTE_perime_toujours(self):
        """Depuis le retrait du sha, backend / seuil / kinds sont TOUT ce qui
        reste de l'empreinte. Le binôme a mesuré qu'un `return True` à leur
        place passait le banc : aucun témoin ne les couvrait."""
        self.git_init()
        self.build("--threshold", "1")
        self.assertIn("INDEX BUILT @", self.build("--threshold", "100", "--if-stale"),
                      "un --threshold différent n'a PAS périmé l'index")


class GhostRowTests(_Case):
    """T-00000681 — UNE LIGNE DONT LE FICHIER N'EXISTE PLUS SORT DE L'INDEX, EN
    INCRÉMENTAL AUSSI.

    Le fantôme mesuré sur le kit : un fichier que git n'a JAMAIS suivi, entré
    en incrémental par `ls-files --others` (T-00000230), puis effacé du disque.
    Plus aucun canal de `_changed_names` ne le nommait, donc `reconcile`
    recopiait ses lignes à chaque build : seul `--full` les tombstonait.
    Désormais la ligne meurt au prochain build RÉEL, incrémental compris. Ce
    que la règle NE change PAS : `--if-stale` lit les mêmes canaux, donc il
    répond encore CURRENT jusque-là — la sonde ne voit pas le fantôme.

    DEUX BORNES, témoins du binôme de clôture : « absent » veut dire PROUVÉ
    absent (ENOENT/ENOTDIR — un répertoire illisible n'est pas une absence), et
    un fichier SUIVI absent du disque (skip-worktree, sparse-checkout) n'est
    pas un fantôme : l'index est commité, le tombstoner sur un clone
    l'effacerait pour tous.

    PIÈGE NOMMÉ : `_Case.commit` fait `git add -A`, qui RE-SUIT ce qu'un
    `git rm --cached` vient de dé-suivre. Un témoin qui l'appellerait ferait
    tombstoner le fantôme par la branche ORDINAIRE (le chemin revient dans
    `git diff built..HEAD`) et ne discriminerait plus la règle. Ces témoins
    commitent donc par `_git("commit", …)` après un `_git("add", …)` NOMMÉ, et
    contrôlent la fixture avant d'asserter.
    """

    GHOST = "src/alpha/ghost.py"
    CALLER = "src/alpha/caller.py"
    GHOST_TEXT = "def ghost_a():\n    return 1\n\n\ndef ghost_b():\n    return 2\n"

    # Chaque helper filtre `not s["deleted"]` AVANT de lire `s["path"]` : une
    # ligne tombstonée n'a que id/name/kind/deleted (`_parse_rows`).
    def _ghost_ids(self) -> set:
        return {s["id"] for s in self.rows()
                if not s["deleted"] and s["path"] == self.GHOST}

    def _caller_uses(self) -> list:
        rows = [s for s in self.rows()
                if not s["deleted"] and s["path"] == self.CALLER
                and s["name"] == "call_ghost"]
        self.assertEqual(1, len(rows), f"call_ghost vivant attendu une fois : {rows}")
        return rows[0]["uses"]

    def _ls_files(self, *args: str, path: str = None) -> str:
        # `_git` jette stdout : lecture directe.
        return subprocess.run(
            [GIT, "-C", str(self.root), "ls-files", *args, "--", path or self.GHOST],
            capture_output=True, text=True, check=True).stdout.strip()

    def _ids_at(self, path: str) -> set:
        return {s["id"] for s in self.rows()
                if not s["deleted"] and s["path"] == path}

    def test_ghost_row_is_tombstoned_incrementally_and_pruned_from_uses(self):
        self.git_init()
        self.build("--full")
        self.write_sources({
            self.GHOST: self.GHOST_TEXT,
            self.CALLER: "def call_ghost():\n    return ghost_a()\n",
        })
        self._git("add", self.GHOST, self.CALLER)
        self.build()
        ghost_ids = self._ghost_ids()
        self.assertEqual(2, len(ghost_ids), "prémisse : le fantôme n'est pas entré")
        ghost_a = self.ids()[(self.GHOST, "ghost_a", "function")]
        self.assertEqual([ghost_a], self._caller_uses(),
                         "prémisse : call_ghost ne cite pas ghost_a")
        avant = self.tombstoned()

        self._git("rm", "--cached", "-q", self.GHOST)
        # JAMAIS self.commit() : son `add -A` re-suivrait le fantôme.
        self._git("commit", "-qm", "caller")
        self.assertEqual("", self._ls_files(),
                         "fixture : le fantôme est encore suivi avant unlink")
        (self.root / self.GHOST).unlink()

        out = self.build()
        self.assertIn("incremental", out)
        self.assertLessEqual({bi.sid(i) for i in ghost_ids},
                             set(self.delta_ids("removed")),
                             "la ligne fantome n'est pas tombstonee en incremental")
        self.assertEqual(ghost_ids, self.tombstoned() - avant,
                         "autre chose que le fantôme a été tombstoné")
        self.assertEqual([], self._caller_uses(),
                         "une ligne vivante cite encore le fantôme")
        self.assertIn("INDEX CURRENT", self.build("--if-stale"))
        self.build("--full")
        self.assertEqual([], self.delta()["removed"],
                         "le plein a trouvé ce que l'incrémental avait laissé")

    def test_present_file_out_of_scope_is_not_tombstoned(self):
        self.git_init()
        self.build("--full")
        self.write_sources({self.GHOST: self.GHOST_TEXT})
        self._git("add", self.GHOST)
        self.build()
        ghost_ids = self._ghost_ids()
        self.assertEqual(2, len(ghost_ids), "prémisse : le fichier n'est pas entré")

        self._git("rm", "--cached", "-q", self.GHOST)
        (self.root / ".gitignore").write_text(self.GHOST + "\n", encoding="utf-8")
        self._git("add", ".gitignore")
        self._git("commit", "-qm", "untrack+ignore ghost")
        self.build()  # tour de règlement, pas l'assertion
        self.assertEqual("", self._ls_files("--others", "--exclude-standard"),
                         "fixture : le fichier est encore nommé par ls-files --others")
        self.assertTrue((self.root / self.GHOST).exists(),
                        "fixture : le fichier doit rester sur le disque")

        out = self.build()
        self.assertIn("0 files scanned", out)
        self.assertEqual(ghost_ids, self._ghost_ids(),
                         "un fichier PRESENT hors scope a ete tombstone — "
                         "l'admission des non-suivis est l'objet de T-00000230")

    HIDDEN = "src/alpha/hidden.py"
    LOCKED_DIR = "src/locked"
    LOCKED = "src/locked/held.py"
    LOOSE = "src/locked/loose.py"

    def test_tracked_skip_worktree_file_absent_from_disk_keeps_its_ids(self):
        """Un fichier SUIVI que git cache (`update-index --skip-worktree`, la
        mécanique du sparse-checkout) et absent du disque n'est PAS un fantôme.
        Aucun canal de scope ne le nomme — git le tient pour inchangé — donc
        l'ancienne règle, « absent du disque », le tombstonait : un
        `chore(index)` d'un collègue en sparse effaçait ses lignes pour tous,
        et ses SYM-ID changeaient au retour du fichier."""
        self.write_sources({self.HIDDEN: self.GHOST_TEXT})
        self.git_init()
        self.build("--full")
        ids = self._ids_at(self.HIDDEN)
        self.assertEqual(2, len(ids), "prémisse : le fichier suivi n'est pas entré")
        avant = self.tombstoned()

        self._git("update-index", "--skip-worktree", self.HIDDEN)
        (self.root / self.HIDDEN).unlink()
        self.assertEqual(f"S {self.HIDDEN}", self._ls_files("-v", path=self.HIDDEN),
                         "fixture : le fichier n'est pas suivi en skip-worktree")
        self.assertFalse((self.root / self.HIDDEN).exists(),
                         "fixture : le fichier doit avoir quitté le disque")

        out = self.build()
        self.assertIn("incremental", out)
        self.assertEqual(ids, self._ids_at(self.HIDDEN),
                         "un fichier SUIVI (skip-worktree) absent du disque a été "
                         "tombstoné — la règle ne vise que les non-suivis")
        self.assertEqual(avant, self.tombstoned(), "une ligne a été tombstonée")

    def test_present_file_under_unreadable_directory_keeps_its_ids(self):
        """EACCES n'est pas une absence. `Path.exists()` rend False sur toute
        OSError depuis Python 3.12 : sous un répertoire `chmod 000`, un fichier
        suivi et PRÉSENT passait pour effacé. `git diff` n'en dit rien sur
        stdout (rc 0, la plainte va sur stderr), donc il reste hors scope et
        c'est la règle des absents qui décidait — mesuré : 16 lignes perdues.

        UN NON SUIVI À CÔTÉ DU SUIVI, et c'est lui qui discrimine : pour le
        fichier suivi, la garde « git le suit » suffirait seule, et ce témoin
        passerait sans la règle EACCES. Le non suivi (entré par `ls-files
        --others`, T-00000230) n'a que `_absent_du_disque` pour le sauver."""
        self.write_sources({self.LOCKED: self.GHOST_TEXT})
        self.git_init()
        self.build("--full")
        self.write_sources({self.LOOSE: "def loose_a():\n    return 3\n"})
        self.build()
        self.assertEqual("", self._ls_files(path=self.LOOSE),
                         "fixture : le non-suivi est suivi")
        ids = self._ids_at(self.LOCKED) | self._ids_at(self.LOOSE)
        self.assertEqual(3, len(ids), "prémisse : suivi + non-suivi ne sont pas entrés")
        avant = self.tombstoned()

        locked = self.root / self.LOCKED_DIR
        os.chmod(locked, 0)
        try:
            try:
                os.stat(self.root / self.LOCKED)
            except PermissionError:
                pass
            else:
                self.skipTest("chmod 000 ne retire pas l'accès ici (root, ou "
                              "système sans permissions POSIX) : rien à mesurer")
            out = self.build()
            self.assertIn("incremental", out)
            self.assertEqual(ids, self._ids_at(self.LOCKED) | self._ids_at(self.LOOSE),
                             "un fichier PRÉSENT sous un répertoire illisible a "
                             "été tombstoné — EACCES lu comme une absence")
            self.assertEqual(avant, self.tombstoned(), "une ligne a été tombstonée")
        finally:
            os.chmod(locked, 0o755)


if __name__ == "__main__":
    unittest.main()
