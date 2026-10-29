"""Tests for ledger.py — the institutional memory store.

Style aligned with .codex/hooks/test_hook_contracts.py and the tasks.py store
it mirrors: temp roots (never touch the tracked LEDGER.json), direct import
(pytest's default rootdir insertion puts this file's directory on sys.path,
same trick .codex/hooks/test_hook_contracts.py relies on for `import _common`).
"""
import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ledger

ROOT = Path(__file__).resolve().parents[2]

# Written as chr(10) rather than an escape: several of the cases below FORGE a
# newline inside a payload, and a literal escape in a test that is itself about
# newline handling is one re-read away from being mistaken for the two-character
# sequence it is testing against.
NL = chr(10)


def make_root(tmp_path: Path) -> Path:
    ledger.store_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    ledger.view_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    return tmp_path


def write_store(tmp_path: Path, data: dict) -> None:
    ledger.store_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")


# R-BANCS (T-00001039, plan de T-00000726) : (i) un banc qui crée PUIS vise l'id
# CAPTURE celui que `add_entry` a rendu — jamais un littéral prédit (`L-00000001`) :
# l'allocateur change à la bascule C2 et le banc doit rester vrai AVANT et APRÈS
# elle ; (ii) une extraction d'id lit la grammaire ULID — une classe de CHIFFRES
# seuls capterait EN SILENCE `L-01` dans un `L-<ULID>`.
ID_RE = r"L-[0-9A-HJKMNP-TV-Z]+"
_ADDED = re.compile(r"\ALEDGER: (" + ID_RE + r") added \(")


def add(root, *args, **kwargs) -> str:
    """`ledger.add_entry`, et l'id qu'il a RENDU (règle (i))."""
    msg = ledger.add_entry(root, *args, **kwargs)
    found = _ADDED.match(msg)
    assert found, f"add_entry n'a pas rendu d'id lisible : {msg!r}"
    return found.group(1)


def cell_id(lid: str) -> str:
    """L'id tel que la TABLE le rend (`fit` à `WIDTHS["id"]`) : la largeur de la
    colonne est l'affaire de C2 (M31'), pas de ce banc."""
    return ledger.fit(lid, ledger.WIDTHS["id"])


class LedgerRoundTripTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_add_then_list_round_trips(self):
        msg = ledger.add_entry(self.root, "lesson", "first lesson", tags_csv="a,b", related="T-001")
        lid = _ADDED.match(msg).group(1)
        self.assertEqual(msg, f"LEDGER: {lid} added (lesson)")
        data = ledger.load(self.root)
        self.assertEqual(len(data["entries"]), 1)
        entry = data["entries"][0]
        self.assertEqual(entry["id"], lid)
        self.assertEqual(entry["category"], "lesson")
        self.assertEqual(entry["title"], "first lesson")
        self.assertEqual(entry["tags"], ["a", "b"])
        self.assertEqual(entry["related"], "T-001")
        self.assertEqual(entry["status"], "active")
        rendered = ledger.render_list(self.root)
        self.assertIn(cell_id(lid), rendered)
        self.assertIn("first lesson", rendered)

    def test_title_flag_pushes_positional_content_into_text(self):
        ledger.add_entry(self.root, "decision", "the text body", title="the title")
        entry = ledger.load(self.root)["entries"][0]
        self.assertEqual(entry["title"], "the title")
        self.assertEqual(entry["text"], "the text body")

    def test_add_requires_a_title(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.add_entry(self.root, "lesson", content="")

    def test_add_rejects_unknown_category(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.add_entry(self.root, "todo", "bad category")

    def test_add_rejects_malformed_related(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.add_entry(self.root, "lesson", "x", related="not-a-task")

    def test_ids_are_monotonic_and_never_reused(self):
        """R-BANCS (iii) : la PROPRIÉTÉ, jamais la valeur du compteur — un id rendu
        n'est aucun des ids déjà rendus, et les ids se rangent dans l'ordre de leur
        émission (`sort_key`), sous l'allocateur d'aujourd'hui comme sous celui de C2."""
        seen = [add(self.root, "lesson", "one"), add(self.root, "lesson", "two")]
        data = ledger.load(self.root)
        self.assertEqual([e["id"] for e in data["entries"]], seen)
        self.assertEqual(len(set(seen)), 2)

        # Simulate an entry having been removed from the store by hand: the
        # list shrinks but the next id must NOT reissue either id already handed out.
        data["entries"].pop(0)
        ledger.save(self.root, data)
        third = add(self.root, "lesson", "three")
        self.assertNotIn(third, seen)
        self.assertEqual(seen + [third], sorted(seen + [third], key=ledger.sort_key))

    def test_render_table_escapes_pipe_in_title(self):
        ledger.add_entry(self.root, "lesson", "a | b")
        rendered = ledger.render_list(self.root)
        self.assertIn("a \\| b", rendered)
        # exactly 2 pipes per data row (leading/trailing table delimiters) plus
        # the escaped one — i.e. the literal pipe must not add a table column.
        rows = [line for line in rendered.splitlines() if "a \\| b" in line]
        self.assertEqual(len(rows), 1)

    def test_render_view_regenerates_ledger_md(self):
        lid = add(self.root, "constraint", "keep this")
        ledger.render_view(self.root)
        view = ledger.view_path(self.root).read_text(encoding="utf-8")
        self.assertIn(cell_id(lid), view)
        self.assertIn("keep this", view)


class LedgerLoadValidationTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_load_rejects_malformed_json(self):
        ledger.store_path(self.root).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_load_rejects_unknown_category(self):
        write_store(
            self.root,
            {
                "next_id": 2,
                "entries": [
                    {
                        "id": "L-001",
                        "category": "todo",
                        "title": "x",
                        "text": "x",
                        "created": "2026-07-24",
                        "tags": [],
                        "related": "",
                        "status": "active",
                    }
                ],
            },
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_load_rejects_unknown_status(self):
        write_store(
            self.root,
            {
                "next_id": 2,
                "entries": [
                    {
                        "id": "L-001",
                        "category": "lesson",
                        "title": "x",
                        "text": "x",
                        "created": "2026-07-24",
                        "tags": [],
                        "related": "",
                        "status": "gone",
                    }
                ],
            },
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_load_rejects_non_string_tag(self):
        write_store(
            self.root,
            {
                "next_id": 2,
                "entries": [
                    {
                        "id": "L-001",
                        "category": "lesson",
                        "title": "x",
                        "text": "x",
                        "created": "2026-07-24",
                        "tags": ["ok", 42],
                        "related": "",
                        "status": "active",
                    }
                ],
            },
        )
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_load_rejects_duplicate_id(self):
        entry = {
            "id": "L-001",
            "category": "lesson",
            "title": "x",
            "text": "x",
            "created": "2026-07-24",
            "tags": [],
            "related": "",
            "status": "active",
        }
        write_store(self.root, {"next_id": 2, "entries": [entry, dict(entry)]})
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_load_rejects_numeric_duplicate_across_different_padding(self):
        # Same numeric value, different zero-padding (legacy vs new format)
        # — must still be treated as a collision, not two distinct entries.
        base = {
            "category": "lesson",
            "title": "x",
            "text": "x",
            "created": "2026-07-24",
            "tags": [],
            "related": "",
            "status": "active",
        }
        entries = [dict(base, id="L-005"), dict(base, id="L-00000005")]
        write_store(self.root, {"next_id": 6, "entries": entries})
        with self.assertRaises(ledger.LedgerError):
            ledger.load(self.root)

    def test_mixed_width_ids_sort_numerically_and_allocation_continues_above_max(self):
        # An old 3-digit entry alongside a new 8-digit one: the view must
        # order them numerically, load() must not raise a duplicate error,
        # and the next minted id must continue above the highest number seen.
        base = {
            "category": "lesson",
            "title": "x",
            "text": "x",
            "created": "2026-07-20",
            "tags": [],
            "related": "",
            "status": "active",
        }
        entries = [dict(base, id="L-005", title="legacy"), dict(base, id="L-00000016", title="new")]
        write_store(self.root, {"next_id": 6, "entries": entries})
        data = ledger.load(self.root)  # must not raise
        ordered = ledger.sorted_entries(data["entries"])
        self.assertEqual([e["id"] for e in ordered], ["L-005", "L-00000016"])
        # R-BANCS (iii) : l'id rendu n'en NOMME aucun déjà vu et se range après le plus haut.
        lid = add(self.root, "lesson", "after mixed-width store")
        self.assertNotIn(ledger.identity_key(lid), {ledger.identity_key(i) for i in ("L-005", "L-00000016")})
        self.assertGreater(ledger.sort_key(lid), ledger.sort_key("L-00000016"))

    def test_cli_exits_2_on_malformed_store(self):
        ledger.store_path(self.root).write_text("{not json", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "bin" / "ledger.py"), "--root", str(self.root), "list"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ledger.py:", result.stderr)


# Trois corps ULID figés (mêmes valeurs que test_record_id.py) : U_LETTER finit par
# une LETTRE (`numeric_id` lève dessus), U_DIGIT par un CHIFFRE (`numeric_id` y lit 2
# EN SILENCE), U_ALLDIG n'a que des chiffres. Ce sont des ULID, jamais des nombres ;
# en ASCII, U_ALLDIG < U_LETTER < U_DIGIT.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"
U_ALLDIG = "01234567890123456789012345"


def entry_of(lid: str, **fields) -> dict:
    """Une entrée VALIDE écrite à la main dans le magasin (fixture d'ENTRÉE)."""
    entry = {"id": lid, "category": "lesson", "title": f"titre {lid}", "text": "",
             "created": "2026-07-20", "tags": [], "related": "", "status": "active"}
    entry.update(fields)
    return entry


class LedgerUlidLectureTests(unittest.TestCase):
    """T-00001039 (plan de T-00000726, forme A, S-00003552) — un ledger MIXTE se
    LIT : `L-<ULID>` et `related: T-<ULID>` chargent, se rangent APRÈS les anciens
    (un ancien par valeur, un ULID par corps), entrent dans `context()` ; les
    anciens `L-001` / `L-0000…` restent lus à l'identique. ROUGES sur le code
    d'avant la tranche : `numeric_id` lève sur `L-<U_LETTER>` et lit 2 dans
    `L-<U_DIGIT>`. L'ALLOCATION ne change pas ici : elle est à la bascule C2."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "bin" / "ledger.py"), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=60,
        )

    def test_un_ledger_mixte_charge_et_chaque_id_reste_tel_quel(self):
        ids = ["L-00000030", f"L-{U_LETTER}", "L-001", f"L-{U_DIGIT}"]
        entries = [entry_of(i) for i in ids]
        entries[1]["related"] = f"T-{U_DIGIT}"
        write_store(self.root, {"next_id": 31, "entries": entries})
        data = ledger.load(self.root)
        self.assertEqual(ids, [e["id"] for e in data["entries"]])
        self.assertEqual(f"T-{U_DIGIT}", data["entries"][1]["related"])

    def test_un_ULID_se_range_apres_les_anciens_dans_chaque_statut(self):
        entries = [
            entry_of(f"L-{U_DIGIT}"), entry_of("L-00000030"), entry_of(f"L-{U_ALLDIG}", status="archived"),
            entry_of(f"L-{U_LETTER}"), entry_of("L-00000002", status="archived"), entry_of("L-005"),
        ]
        write_store(self.root, {"next_id": 31, "entries": entries})
        attendu = ["L-005", "L-00000030", f"L-{U_LETTER}", f"L-{U_DIGIT}", "L-00000002", f"L-{U_ALLDIG}"]
        ordered = ledger.sorted_entries(ledger.load(self.root)["entries"])
        self.assertEqual(attendu, [e["id"] for e in ordered])
        listed = self._cli("list")
        self.assertEqual(0, listed.returncode, listed.stderr)
        positions = [listed.stdout.index(f"titre {lid}") for lid in attendu]
        self.assertEqual(sorted(positions), positions, "la vue CLI ne suit pas l'ordre de sorted_entries")

    def test_context_lit_un_ULID_actif_et_le_tient_pour_le_plus_recent(self):
        """M12 : `select_for_context` départage par `sort_key`, jamais par `numeric_id`
        — qui lèverait sur U_LETTER et rangerait U_DIGIT (« 2 ») sous L-00000030."""
        entries = [
            entry_of("L-00000030", category="constraint"),
            entry_of(f"L-{U_DIGIT}", category="constraint"),
            entry_of(f"L-{U_LETTER}"),
        ]
        write_store(self.root, {"next_id": 31, "entries": entries})
        out = ledger.context(self.root)
        self.assertIn(f"- [L-{U_LETTER}] (lesson", out)
        self.assertLess(out.index(f"[L-{U_DIGIT}]"), out.index("[L-00000030]"), "un ULID est plus récent qu'un ancien")
        cli = self._cli("context")
        self.assertEqual(0, cli.returncode, cli.stderr)
        self.assertIn(f"[L-{U_LETTER}]", cli.stdout)

    def test_add_sur_un_ledger_mixte_rend_un_id_neuf(self):
        ids = ["L-00000030", f"L-{U_LETTER}"]
        write_store(self.root, {"next_id": 31, "entries": [entry_of(i) for i in ids]})
        lid = add(self.root, "lesson", "après un ULID")
        self.assertNotIn(ledger.identity_key(lid), {ledger.identity_key(i) for i in ids})
        self.assertEqual(ids + [lid], [e["id"] for e in ledger.load(self.root)["entries"]])

    def test_related_accepte_T_ULID_et_garde_les_anciens(self):
        for related in (f"T-{U_LETTER}", f"T-{U_DIGIT}", f"T-{U_ALLDIG}", "T-001", "T-00000726"):
            lid = add(self.root, "lesson", f"r {related}", related=related)
            stored = next(e for e in ledger.load(self.root)["entries"] if e["id"] == lid)
            self.assertEqual(related, stored["related"])
        for bad in (f"T-{U_LETTER.lower()}", f"T-{U_LETTER[:-1]}", f"T-{U_LETTER}0", f"T-{U_LETTER}\n",
                    f"L-{U_LETTER}", f"T-{U_LETTER[:-1]}U", "T-", "T-1a"):
            with self.subTest(related=bad), self.assertRaises(ledger.LedgerError):
                ledger.add_entry(self.root, "lesson", "refusé", related=bad)
        cli = self._cli("add", "par la CLI", "--category", "lesson", "--related", f"T-{U_LETTER}")
        self.assertEqual(0, cli.returncode, cli.stderr)

    def test_v_un_ULID_en_double_est_refuse_par_son_nom(self):
        """(v)-ledger, M36l : le saut ULID du contrôle de collision NUMÉRIQUE se pose
        APRÈS le contrôle d'id exact — jamais avant, sinon un doublon passerait."""
        write_store(self.root, {"next_id": 1, "entries": [entry_of(f"L-{U_LETTER}"), entry_of(f"L-{U_LETTER}")]})
        with self.assertRaisesRegex(ledger.LedgerError, "duplicate entry id"):
            ledger.load(self.root)
        cli = self._cli("list")
        self.assertEqual(2, cli.returncode)
        self.assertIn(f"duplicate entry id L-{U_LETTER}", cli.stderr)

    def test_les_anciens_sont_lus_a_l_identique(self):
        self.assertEqual((0, 1), ledger.sort_key("L-001"))
        self.assertEqual(ledger.identity_key("L-001"), ledger.identity_key("L-00000001"))
        self.assertFalse(ledger.is_ulid_id("L-00000001"))
        entries = [entry_of("L-010"), entry_of("L-00000002"), entry_of("L-001")]
        write_store(self.root, {"next_id": 11, "entries": entries})
        ordered = ledger.sorted_entries(ledger.load(self.root)["entries"])
        self.assertEqual(["L-001", "L-00000002", "L-010"], [e["id"] for e in ordered])
        with self.assertRaises(ledger.LedgerError):
            ledger.sort_key("L-abc")

    def test_load_refuse_un_ULID_sous_un_prefixe_etranger(self):
        """S-00004584 : la grammaire ULID recopiée accepte `[TSL]-` ; sans ce refus,
        un `S-<ULID>` ou un `T-<ULID>` égaré dans le ledger se chargeait en silence."""
        for etranger in (f"S-{U_LETTER}", f"T-{U_DIGIT}"):
            with self.subTest(etranger=etranger):
                write_store(self.root, {"next_id": 1, "entries": [entry_of(f"L-{U_LETTER}"), entry_of(etranger)]})
                with self.assertRaisesRegex(ledger.LedgerError, "foreign prefix"):
                    ledger.load(self.root)


class LedgerArchiveTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_archive_flips_status_and_restore_brings_it_back(self):
        lid = add(self.root, "lesson", "to retire")
        msg = ledger.set_status(self.root, lid, "archived")
        self.assertEqual(msg, f"LEDGER: {lid} archived (lesson)")
        self.assertEqual(ledger.load(self.root)["entries"][0]["status"], "archived")
        msg = ledger.set_status(self.root, lid, "active")
        self.assertEqual(msg, f"LEDGER: {lid} restored (lesson)")
        self.assertEqual(ledger.load(self.root)["entries"][0]["status"], "active")

    def test_archive_is_idempotent_and_says_so_without_writing(self):
        lid = add(self.root, "lesson", "x")
        ledger.set_status(self.root, lid, "archived")
        before = ledger.store_path(self.root).read_text(encoding="utf-8")
        msg = ledger.set_status(self.root, lid, "archived")
        self.assertEqual(msg, f"LEDGER: {lid} already archived")
        self.assertEqual(ledger.store_path(self.root).read_text(encoding="utf-8"), before)

    def test_archived_constraint_drops_out_of_context(self):
        lid = add(self.root, "constraint", "was binding")
        ledger.add_entry(self.root, "lesson", "still relevant")
        ledger.set_status(self.root, lid, "archived")
        out = ledger.context(self.root)
        self.assertNotIn("was binding", out)
        self.assertIn("still relevant", out)

    def test_archived_entry_stays_in_view_sorted_after_active(self):
        first = add(self.root, "lesson", "will archive")
        second = add(self.root, "lesson", "stays active")
        ledger.set_status(self.root, first, "archived")
        ordered = ledger.sorted_entries(ledger.load(self.root)["entries"])
        self.assertEqual([e["id"] for e in ordered], [second, first])
        rendered = ledger.render_list(self.root)
        self.assertIn("will archive", rendered)

    def test_archive_unknown_id_raises(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.set_status(self.root, "L-999", "archived")

    def test_cli_archive_and_restore_round_trip(self):
        lid = add(self.root, "decision", "cli round trip")
        script = str(ROOT / ".agents" / "bin" / "ledger.py")
        result = subprocess.run(
            [sys.executable, script, "--root", str(self.root), "archive", lid],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("archived", result.stdout)
        result = subprocess.run(
            [sys.executable, script, "--root", str(self.root), "restore", lid],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("restored", result.stdout)

    def test_cli_archive_unknown_id_exits_2(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "bin" / "ledger.py"), "--root", str(self.root), "archive", "L-404"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown entry id", result.stderr)


class LedgerContextTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_context_is_empty_when_store_has_no_entries(self):
        self.assertEqual(ledger.context(self.root), "")

    def test_context_always_includes_active_constraints(self):
        cid = add(self.root, "constraint", "must keep")
        for i in range(3):
            ledger.add_entry(self.root, "lesson", f"lesson {i}")
        out = ledger.context(self.root)
        self.assertIn(cid, out)
        self.assertIn("must keep", out)
        self.assertTrue(out.startswith(ledger.CONTEXT_HEADER))

    def test_context_caps_lesson_decision_entries_to_five_most_recent(self):
        ids = [add(self.root, "lesson", f"lesson {i}") for i in range(8)]
        out = ledger.context(self.root)
        # 8 lessons added -> only the 5 most recent (the 5 last ids) survive selection.
        for recent_id in ids[3:]:
            self.assertIn(recent_id, out)
        for old_id in ids[:3]:
            self.assertNotIn(f"[{old_id}]", out)

    def test_context_respects_the_hard_char_cap(self):
        ledger.add_entry(self.root, "constraint", "c0", text="x" * 50)
        for i in range(10):
            ledger.add_entry(self.root, "lesson", f"lesson {i}", text="y" * 400)
        out = ledger.context(self.root, max_chars=500)
        self.assertLessEqual(len(out), 500)
        # The cap is now honoured by SHORTENING each entry's text and, if that
        # is not enough, by dropping WHOLE entries and saying so — never by
        # slicing the concatenation mid-word (L-00000109).
        self.assertNotIn("[truncated]", out)

    # -- L-00000109: the injection used to go silently blind ----------------
    #
    # These tests exist at REALISTIC SCALE on purpose. The suite already had
    # `test_context_always_includes_active_constraints`, and it passed with ONE
    # constraint while the real store held twenty-eight and injected six — the
    # exact shape L-00000025 warns about: a guardrail evaluated on data that
    # cannot fail it. Every test below seeds enough entries to overflow.

    def _seed_overflow(self, constraints=28, lessons=8):
        for i in range(constraints):
            ledger.add_entry(self.root, "constraint", f"contrainte numero {i:02d}", text="c" * 200)
        for i in range(lessons):
            ledger.add_entry(self.root, "lesson", f"lecon numero {i:02d}", text="l" * 200)

    def test_no_entry_is_ever_cut_mid_sentence(self):
        """The old failure mode: the body was sliced as one string, so the last
        entry shown ended mid-word and the reader could not tell that anything
        had been lost at all."""
        self._seed_overflow()
        out = ledger.context(self.root)
        self.assertLessEqual(len(out), ledger.MAX_CONTEXT_CHARS)
        self.assertNotIn("[truncated]", out)
        for line in out.splitlines():
            if line.startswith("- [L-"):
                # Every rendered entry is structurally complete.
                self.assertIn("(tags:", line, f"entry cut before its metadata: {line[-60:]!r}")
                self.assertTrue(line.rstrip().endswith(")"), f"entry cut mid-line: {line[-60:]!r}")

    def test_what_does_not_fit_is_named_by_id(self):
        """A dropped constraint is an ABSENCE THAT IS STATED, with the command
        that reads it — the kit refuses a silent missing signal everywhere else
        and this mechanism is no exception."""
        self._seed_overflow()
        out = ledger.context(self.root)
        self.assertIn("[omission]", out)
        notice = [l for l in out.splitlines() if l.startswith("- [omission]")][0]
        self.assertIn("ledger.py list", notice)
        self.assertRegex(notice, ID_RE)
        shown = set(re.findall(r"- \[(" + ID_RE + r")\]", out))
        named = set(re.findall("(" + ID_RE + ")", notice))
        total = {e["id"] for e in ledger.load(self.root)["entries"]
                 if e["category"] == "constraint" or e["id"] in shown}
        # Nothing vanishes: every constraint is either rendered or named.
        self.assertTrue(total <= (shown | named), f"lost silently: {sorted(total - shown - named)}")

    def test_recent_constraints_are_not_starved_by_ancient_ones(self):
        """THE defect. Constraints were ranked oldest-first and the body was
        tail-truncated, so the first constraints ever written held the whole
        budget for good and nothing written later could ever be seen."""
        self._seed_overflow()
        out = ledger.context(self.root)
        # R-BANCS (ii) : l'id n'est jamais DÉCOUPÉ en nombre — il se compare par la clé
        # du module (`sort_key`), qui range un ancien par valeur et un ULID par corps.
        shown = [ledger.sort_key(i) for i in re.findall(r"- \[(" + ID_RE + r")\] \(constraint", out)]
        self.assertTrue(shown, "no constraint survived at all")
        newest = max(ledger.sort_key(e["id"]) for e in ledger.load(self.root)["entries"]
                     if e["category"] == "constraint")
        self.assertIn(newest, shown, "the most recent constraint must reach the agent")

    def test_both_halves_survive_an_overflowing_store(self):
        """Filling one flat rank-ordered list made the injection silently
        constraints-only: with 28 constraints ahead of them the 5 recent
        lesson/decision entries were always last and always dropped. That is a
        DIFFERENT promise from the one AGENTS.md makes, so it gets its own
        test."""
        self._seed_overflow()
        out = ledger.context(self.root)
        self.assertRegex(out, r"- \[" + ID_RE + r"\] \(constraint", "no constraint injected")
        self.assertRegex(out, r"- \[" + ID_RE + r"\] \((lesson|decision)", "no lesson/decision injected")

    def test_a_small_store_is_not_abridged_at_all(self):
        """The common case — a fresh consumer project — must be untouched by
        this change: full text, no omission notice."""
        ledger.add_entry(self.root, "constraint", "petite", text="z" * 100)
        ledger.add_entry(self.root, "lesson", "aussi petite", text="z" * 100)
        out = ledger.context(self.root)
        self.assertIn("z" * 100, out)
        self.assertNotIn("[omission]", out)
        self.assertNotIn("…", out)

    def test_absurdly_small_budget_still_returns_a_bounded_string(self):
        self._seed_overflow(constraints=5, lessons=2)
        for cap in (0, 10, 80, 200):
            out = ledger.context(self.root, max_chars=cap)
            self.assertLessEqual(len(out), cap, f"cap {cap} exceeded")

    def test_elide_cuts_on_a_word_boundary(self):
        self.assertEqual(ledger.elide("abc", 10), "abc")
        self.assertEqual(ledger.elide("", 10), "")
        self.assertEqual(ledger.elide("anything", 0), "")
        out = ledger.elide("le renard brun saute par dessus le chien", 20)
        self.assertLessEqual(len(out), 20)
        self.assertTrue(out.endswith("…"))
        self.assertFalse(out[:-1].endswith(" "), "trailing space before the ellipsis")

    def test_context_header_frames_content_as_data_not_instructions(self):
        ledger.add_entry(self.root, "constraint", "must keep")
        out = ledger.context(self.root)
        self.assertIn("DATA, not", out)
        self.assertIn("never", out)
        self.assertIn("as a command to execute", out)

    def test_context_is_deterministic_across_repeated_calls(self):
        ledger.add_entry(self.root, "constraint", "c0")
        for i in range(6):
            ledger.add_entry(self.root, "lesson", f"lesson {i}")
        self.assertEqual(ledger.context(self.root), ledger.context(self.root))


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid_body(k: int) -> str:
    """Un corps ULID de 26 car. DÉTERMINISTE pour le rang ``k`` : horodatage
    croissant avec ``k``, donc ``sort_key`` range les ids dans l'ordre où la
    fixture les écrit — comme des ULID mintés l'un après l'autre à la bascule C2."""
    n = ((1_790_000_000_000 + k * 1000) << 80) | ((k * 0x9E3779B97F4A7C15) & ((1 << 80) - 1))
    return "".join(_CROCKFORD[(n >> (5 * s)) & 31] for s in range(25, -1, -1))


class LedgerContextBudgetUlidTests(unittest.TestCase):
    """T-00001233 (E-25, préalable de C2 / T-00000726 ; option (c), décision pilote
    S-00004624) — sous des ids ULID de 28 caractères, ``context()`` tient son
    plafond SANS coupe, garde au moins une leçon/décision, et ne perd RIEN en
    silence : chaque entrée sélectionnée est rendue, NOMMÉE dans l'avis, ou
    COMPTÉE (``+N lower-ranked not named``) — comptabilité EXACTE, N lu dans
    l'avis. « lower-ranked », jamais « older » : le rang (contraintes d'abord,
    puis étiquette, puis récence) n'est pas l'âge — T5 le prouve sous étiquette.

    ROUGES sur le code d'avant : l'avis non plafonné s'allongeait de 29 car. à
    chaque éviction, la boucle vidait les leçons (``kept.pop()`` frappait la
    queue, donc les leçons d'abord) puis le clamp terminal coupait l'avis
    lui-même — mesuré sur le ledger réel tout-ULID : ``[truncated]``, 0 entrée
    rendue, 36 perdues en silence.

    Fixtures d'ENTRÉE écrites par ``write_store`` (R-BANCS (i)), ids extraits par
    ``ID_RE`` (R-BANCS (ii)), comparés par ``sort_key`` (R-BANCS (iii)). Les titres
    de 100 car. sont PLUS COURTS que les vrais (104 contraintes actives : médiane
    175, max 260 — relevé du plan-critic S-00004628, re-balayage à 175 et 260 :
    0 violation) ; le balayage joue donc aussi 175 et 260.

    La « nouvelle » promesse (comptée quand la place manque) est épinglée ICI,
    jamais en assouplissant ``test_what_does_not_fit_is_named_by_id`` (piège 2
    de PLANNING_TRAPS) : sur la fixture 28+8, tout tient encore et tout est nommé."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _seed(self, constraints, lessons, ulid=True):
        """Contraintes puis leçons, ``(titre, texte)`` chacune ; ids croissants
        dans cet ordre, ``created`` constant : le rang tombe sur ``sort_key``."""
        entries = []
        for category, rows in (("constraint", constraints), ("lesson", lessons)):
            for title, text in rows:
                k = len(entries) + 1
                lid = f"L-{ulid_body(k)}" if ulid else f"L-{k:08d}"
                entries.append(entry_of(lid, category=category, title=title, text=text, created="2026-10-08"))
        write_store(self.root, {"next_id": len(entries) + 1, "entries": entries})

    @staticmethod
    def _rows(prefix, n, length):
        return [((f"{prefix} {i:03d} " + "x" * length)[:length], "") for i in range(n)]

    def _assert_bounded_and_accounted(self, out, cap, tags=None):
        """Pas de coupe, plafond tenu, et rendus + nommés + N == sélectionnés,
        sans recouvrement ni id étranger ; les NOMMÉS sont la tête, dans l'ordre de
        la sélection, des non-rendus (les comptés sont donc les moins bien classés) ;
        un avis qui nomme ET compte tient dans le tiers du budget. Rend (rendus,
        nommés, N, leçons rendues). Fixtures sans surface d'atterrissage : pas
        d'avis de promotion, le budget disponible est ``cap`` moins l'en-tête."""
        self.assertLessEqual(len(out), cap)
        self.assertNotIn("[truncated]", out)
        constraints, recent = ledger.select_for_context(ledger.load(self.root)["entries"], tags)
        order = [e["id"] for e in constraints + recent]
        selected = set(order)
        rendered = re.findall(r"^- \[(" + ID_RE + r")\] \((?:constraint|lesson|decision)/", out, re.M)
        lessons = re.findall(r"^- \[" + ID_RE + r"\] \((?:lesson|decision)/", out, re.M)
        notices = [l for l in out.splitlines() if l.startswith("- [omission]")]
        named, counted = [], 0
        if notices:
            self.assertEqual(1, len(notices))
            named = re.findall(ID_RE, notices[0])
            found = re.search(r"\+(\d+) lower-ranked not named", notices[0])
            counted = int(found.group(1)) if found else 0
            declared = int(re.match(r"- \[omission\] (\d+) active", notices[0]).group(1))
            self.assertEqual(declared, len(named) + counted, "l'avis annonce un total qui n'est pas le sien")
            self.assertIn("ledger.py list", notices[0])
            if named and counted:
                # S-00004624 : « un tiers » du budget restant, écrit en dur ici —
                # jamais lu sur ledger.OMISSION_SHARE, qu'il doit pouvoir contredire.
                self.assertLessEqual(len(notices[0]), (cap - len(ledger.CONTEXT_HEADER)) // 3,
                                     "l'avis dépasse le tiers du budget")
        self.assertFalse(set(rendered) & set(named), "un id rendu ET nommé")
        self.assertTrue((set(rendered) | set(named)) <= selected, "un id hors sélection")
        self.assertEqual(len(selected), len(rendered) + len(named) + counted,
                         f"perdu en silence : {len(selected) - len(rendered) - len(named) - counted}")
        self.assertEqual([i for i in order if i not in rendered][:len(named)], named,
                         "les nommés ne sont pas les mieux classés des omis, dans l'ordre de la sélection")
        return rendered, named, counted, lessons

    def _assert_newest_constraint_rendered(self, out):
        """C4 (S-00004628) : l'éviction retire la MOINS bien classée — la contrainte
        de plus grand ``sort_key`` (la plus récente, à ``created`` égal) est RENDUE."""
        newest = max((e["id"] for e in ledger.load(self.root)["entries"] if e["category"] == "constraint"),
                     key=ledger.sort_key)
        self.assertIn(f"- [{newest}] (constraint/", out, "la contrainte la plus récente a été évincée")

    def test_un_magasin_ULID_de_69_contraintes_tient_sans_coupe_ni_silence(self):
        """T1 — 69 contraintes ULID + 8 leçons, plafond 2500. Avant : coupe, LD=0, 1 en silence."""
        self._seed(self._rows("contrainte", 69, 100), self._rows("lecon", 8, 70))
        out = ledger.context(self.root, max_chars=2500)
        _rendered, _named, _counted, lessons = self._assert_bounded_and_accounted(out, 2500)
        self.assertTrue(lessons, "aucune leçon/décision injectée")

    def test_le_plafond_500_tient_sous_ULID(self):
        """T2 — jumeau ULID de ``test_context_respects_the_hard_char_cap`` (1 contrainte
        + 10 leçons longues), plafonds 400 ET 500 (C3, S-00004628) : à 500 l'avis
        d'un plafond oublié au 2e appel (clamp terminal) ne se voit pas, à 400 il
        coupe. À ces plafonds l'avis ne nomme AUCUN id (son texte fixe dépasse le
        tiers) : il COMPTE."""
        self._seed([("contrainte numero 00", "x" * 50)],
                   [(f"lecon numero {i:02d}", "l" * 400) for i in range(10)])
        for cap in (400, 500):
            with self.subTest(cap=cap):
                out = ledger.context(self.root, max_chars=cap)
                self._assert_bounded_and_accounted(out, cap)

    def test_tout_id_omis_est_nomme_quand_la_liste_tient_ULID(self):
        """T3 — jumeau ULID de ``_seed_overflow`` (28 + 8) : la liste tient dans son
        tiers, donc TOUT omis est NOMMÉ (aucun ``+N``), au moins une leçon reste,
        et la contrainte la plus récente est rendue. Avant : LD=0."""
        self._seed([(f"contrainte numero {i:02d}", "c" * 200) for i in range(28)],
                   [(f"lecon numero {i:02d}", "l" * 200) for i in range(8)])
        out = ledger.context(self.root)
        _rendered, _named, counted, lessons = self._assert_bounded_and_accounted(out, ledger.MAX_CONTEXT_CHARS)
        self.assertEqual(0, counted)
        self.assertNotIn("not named", out)
        self.assertTrue(lessons, "aucune leçon/décision injectée")
        self._assert_newest_constraint_rendered(out)

    def test_balayage_ULID_et_anciens(self):
        """T4 — N contraintes + 8 leçons, plafond 2500, ids anciens ET ULID, titres
        de 100, 175 et 260 car. Avant (titres 100) : rouge à 9 cas sur 10."""
        for title_len in (100, 175, 260):
            for ulid in (False, True):
                for n in (25, 44, 67, 69, 200):
                    with self.subTest(n=n, ulid=ulid, title_len=title_len):
                        self._seed(self._rows("contrainte", n, title_len), self._rows("lecon", 8, 70), ulid=ulid)
                        out = ledger.context(self.root, max_chars=2500)
                        _r, _n, _c, lessons = self._assert_bounded_and_accounted(out, 2500)
                        self.assertTrue(lessons, "aucune leçon/décision injectée")
                        self._assert_newest_constraint_rendered(out)

    def test_sous_context_tags_le_rang_commande_nommes_et_comptes(self):
        """T5 — chemin ``--context-tags`` (exec-critic de T-00001233) : 80 contraintes
        ULID aux dates étalées, les 30 PLUS ANCIENNES étiquetées ``ledger`` ; 8 leçons,
        les 2 plus anciennes étiquetées. Sous l'étiquette, le rang (étiquette, puis
        récence) n'est PAS l'âge : l'avis doit nommer les mieux CLASSÉES des omises
        et compter les autres — d'où le libellé « lower-ranked », jamais « older ».
        Bornage, comptabilité, ordre ; la mieux classée des contraintes est rendue ;
        la CLI ``--context-tags`` rend la même chose que ``context()``."""
        entries = []
        for i in range(80):
            entries.append(entry_of(
                f"L-{ulid_body(len(entries) + 1)}", category="constraint",
                title=(f"contrainte {i:03d} " + "x" * 175)[:175],
                created=f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", tags=["ledger"] if i < 30 else []))
        for i in range(8):
            entries.append(entry_of(
                f"L-{ulid_body(len(entries) + 1)}", title=(f"lecon {i:03d} " + "y" * 70)[:70],
                created=f"2026-05-{1 + i:02d}", tags=["ledger"] if i < 2 else []))
        write_store(self.root, {"next_id": len(entries) + 1, "entries": entries})
        out = ledger.context(self.root, context_tags=["ledger"])
        _rendered, named, counted, lessons = self._assert_bounded_and_accounted(
            out, ledger.MAX_CONTEXT_CHARS, tags=["ledger"])
        self.assertTrue(named and counted, "le cas doit à la fois nommer et compter")
        self.assertTrue(lessons, "aucune leçon/décision injectée")
        best = entries[29]["id"]  # étiquetée et la plus récente des étiquetées : rang 0
        self.assertIn(f"- [{best}] (constraint/", out, "la contrainte la mieux classée a été évincée")
        cli = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "bin" / "ledger.py"), "--root", str(self.root),
             "context", "--context-tags", "ledger"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, cli.returncode, cli.stderr)
        self.assertEqual(out, cli.stdout.rstrip("\n"))

    def test_la_part_de_l_avis_est_un_tiers_S_00004624(self):
        """La part de l'avis est une DÉCISION pilote, pas un réglage : elle est
        écrite en toutes lettres dans les surfaces qui la décrivent."""
        self.assertEqual(3, ledger.OMISSION_SHARE,
                         "S-00004624 : « un tiers » est écrit dans SKILL.md, "
                         "CADRE/index.html et deux docstrings")


class LedgerPromoteTests(unittest.TestCase):
    """T-00000282 — promotion of a universal lesson into the doctrine.

    The verb MARKS an entry and RESTITUTES a paste block; it never writes
    AGENTS.md. A promoted-and-landed entry then drops out of context(), matched
    on its per-promotion TOKEN (never the bare id) read from AGENTS.md in RAW
    BYTES with a NARROW fail-open."""

    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _seam(self, token):
        """Install a fixed-token seam and return the original to restore. This
        is what makes _new_token load-bearing: it governs the REAL path, so the
        printed marker carries exactly this token."""
        orig = ledger._new_token
        ledger._new_token = lambda: token
        return orig

    def _write_doctrine(self, content: bytes) -> None:
        (self.root / "AGENTS.md").write_bytes(content)

    def _write_skill(self, name: str, content: bytes) -> Path:
        """Sibling of _write_doctrine, for the OTHER landing surface class
        (T-00000330). Without it no test can fabricate a skill surface at all."""
        path = self.root / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _marker(self, lid: str, token: str) -> bytes:
        return ledger._promotion_marker(lid, token).encode("ascii")

    @staticmethod
    def _fold(text: str) -> str:
        """Whitespace-folded comparison: a phrase split across source lines is
        still the same phrase, and three of the eight redirected restitutions are
        multiline (L-00000237 — a line-by-line check would miss them)."""
        return " ".join(text.split())

    def test_promote_marks_and_prints_signed_block(self):
        lid = add(self.root, "lesson", "a universal lesson")
        orig = self._seam("deadbeef")
        try:
            out = ledger.promote_entry(self.root, lid, ref="§ Institutional memory")
        finally:
            ledger._new_token = orig
        # The printed marker carries the SEAM's token — proof the seam governs
        # the real path rather than decorating a direct secrets call.
        self.assertIn(f"[promu-du-ledger:{lid}:deadbeef]", out)
        entry = ledger.load(self.root)["entries"][0]
        self.assertEqual(entry["promoted"]["token"], "deadbeef")
        self.assertEqual(entry["promoted"]["ref"], "§ Institutional memory")
        self.assertIn("date", entry["promoted"])

    def test_landing_matches_token_not_id(self):
        lid = add(self.root, "constraint", "must survive")
        orig = self._seam("0a1b2c3d")
        try:
            ledger.promote_entry(self.root, lid, ref="§ X")
        finally:
            ledger._new_token = orig
        self._write_doctrine(b"... [promu-du-ledger:" + lid.encode("ascii") + b":0a1b2c3d] some doctrine ...")
        out = ledger.context(self.root)
        self.assertNotIn("must survive", out)  # excluded from injection
        self.assertIn("[promoted]", out)       # but announced
        self.assertIn(lid, out)                # named in the announcement

    def test_incidental_citation_does_not_exclude(self):
        """C1: six real L-ids live in AGENTS.md as citations in passing. Matching
        the bare id would exclude the most-cited (best) entries the instant they
        were promoted — the negative test pins that only the marker excludes.

        ENTRY AMENDED (T-00000330), polarity and both asserts UNCHANGED. The
        surface now carries a marker OF ANOTHER ENTRY while citing this one's id
        in prose. Without that amendment the pre-filter would drop a
        prefix-less surface, `_has_landed` would answer False WITHOUT EVER
        COMPARING THE ID, and this test would stay green while measuring nothing
        — a vacuity that survives the death of the test carrying it."""
        lid = add(self.root, "constraint", "cited in passing")
        orig = self._seam("feedface")
        try:
            ledger.promote_entry(self.root, lid, ref="§ Y")
        finally:
            ledger._new_token = orig
        self._write_doctrine(
            b"see " + lid.encode("ascii") + b" for the rationale, but no marker of ITS own here; what this "
            b"surface does carry is another entry's marker: "
            + self._marker("L-00000099", "0badc0de")
        )
        out = ledger.context(self.root)
        self.assertIn("cited in passing", out)  # still injected
        self.assertNotIn("[promoted]", out)     # nothing excluded

    def test_doc_placeholder_never_excludes(self):
        """C9: AGENTS.md documents the marker FORMAT with the L-NNN placeholder,
        never a real id — so the detector's own documentation cannot become a
        false positive of the detector."""
        lid = add(self.root, "constraint", "real one")
        orig = self._seam("12345678")
        try:
            ledger.promote_entry(self.root, lid, ref="§ Z")
        finally:
            ledger._new_token = orig
        self._write_doctrine(b"format example: [promu-du-ledger:L-NNN:<8-hex-token>]")
        out = ledger.context(self.root)
        self.assertIn("real one", out)
        self.assertNotIn("[promoted]", out)

    def test_repromote_keeps_token_and_reprints_same_block(self):
        lid = add(self.root, "lesson", "x")
        calls = []

        def seam():
            calls.append(1)
            return "cafebabe"

        orig = ledger._new_token
        ledger._new_token = seam
        try:
            first = ledger.promote_entry(self.root, lid, ref="§ first")
            second = ledger.promote_entry(self.root, lid, ref="§ second")
        finally:
            ledger._new_token = orig
        marker = f"[promu-du-ledger:{lid}:cafebabe]"
        self.assertIn(marker, first)
        self.assertIn(marker, second)  # identical marker — token kept, block reprinted verbatim
        self.assertEqual(len(calls), 1, "token was regenerated on re-promote — would orphan a pasted block")
        self.assertIn("re-promoted", second)
        self.assertIn("first", second)   # announces the old ref
        self.assertIn("second", second)  # ... and the new one
        promoted = ledger.load(self.root)["entries"][0]["promoted"]
        self.assertEqual(promoted["token"], "cafebabe")
        self.assertEqual(promoted["ref"], "§ second")

    def test_promote_refuses_archived(self):
        lid = add(self.root, "lesson", "x")
        ledger.set_status(self.root, lid, "archived")
        with self.assertRaises(ledger.LedgerError):
            ledger.promote_entry(self.root, lid, ref="§ nope")

    def test_archive_of_promoted_prints_runnable_retraction(self):
        lid = add(self.root, "constraint", "binding")
        ledger.promote_entry(self.root, lid, ref="§ Institutional memory")
        msg = ledger.set_status(self.root, lid, "archived")
        self.assertIn("§ Institutional memory", msg)
        self.assertIn("tasks.py new", msg)
        self.assertIn("Rétracter le marqueur", msg)
        self.assertIn(f"({lid})", msg)
        self.assertIn("--chantier registres", msg)

    def test_landed_promoted_are_announced_bounded_mixed_overflow(self):
        """C10 at realistic scale — a MIXED population over the budget: 7 landed
        promoted constraints, 3 promoted-but-not-pasted, and enough ordinary
        live constraints to overflow the title-only budget. The announcement is
        bounded (5 ids then +N), the landed titles never inject, live
        constraints survive, and the residual omission is still named."""
        landed_ids = []
        tokens = iter(f"{i:08x}" for i in range(1, 200))
        orig = ledger._new_token
        ledger._new_token = lambda: next(tokens)
        try:
            for i in range(7):
                lid = add(self.root, "constraint", f"landed {i}", text="c" * 200)
                ledger.promote_entry(self.root, lid, ref=f"§ s{i}")
                landed_ids.append(lid)
            for i in range(3):  # promoted but NOT pasted: has a token, no marker in AGENTS.md
                lid = add(self.root, "constraint", f"promoted-not-pasted {i}", text="p" * 200)
                ledger.promote_entry(self.root, lid, ref=f"§ np{i}")
        finally:
            ledger._new_token = orig
        for i in range(45):  # ordinary live constraints, enough to overflow titles-only
            ledger.add_entry(self.root, "constraint", f"ordinary {i:02d}", text="o" * 200)

        by_id = {e["id"]: e for e in ledger.load(self.root)["entries"]}
        doctrine = b"\n".join(
            ledger._promotion_marker(lid, by_id[lid]["promoted"]["token"]).encode("ascii")
            for lid in landed_ids
        )
        self._write_doctrine(doctrine)

        out = ledger.context(self.root)
        self.assertLessEqual(len(out), ledger.MAX_CONTEXT_CHARS)
        notice = [l for l in out.splitlines() if l.startswith("- [promoted]")][0]
        # `older`, not `others` (T-00000351): the five NEWEST are named and the
        # two OLDEST are counted. The word changed with the polarity, and it says
        # WHICH two were dropped rather than merely that two were.
        self.assertIn("+2 older", notice)  # 7 landed, 5 shown, +2
        self.assertIn("ledger.py list", notice)
        self.assertLessEqual(len(re.findall(ID_RE, notice)), 5)
        for i in range(7):
            self.assertNotIn(f"landed {i}", out)  # no landed title injected
        self.assertRegex(out, r"- \[" + ID_RE + r"\] \(constraint")  # live constraints survive
        self.assertIn("[omission]", out)  # residual overflow still named

    def test_landing_check_reads_bytes_fail_open(self):
        """The fail-open is NARROW — only OSError around the read. An absent
        AGENTS.md means 'nothing promoted' (entry stays injected); but a BUG in
        the matcher must PROPAGATE, never decay into a permanent silent 'no
        exclusion' — the exact failure class the byte read exists to close."""
        lid = add(self.root, "constraint", "keeps")
        orig = self._seam("abadcafe")
        try:
            ledger.promote_entry(self.root, lid, ref="§ w")
        finally:
            ledger._new_token = orig

        # (a) fail-open: no AGENTS.md -> OSError swallowed -> entry stays in.
        self.assertFalse((self.root / "AGENTS.md").exists())
        out = ledger.context(self.root)
        self.assertIn("keeps", out)
        self.assertNotIn("[promoted]", out)

        # (b) a matcher exception PROPAGATES rather than being read as no exclusion.
        self._write_doctrine(b"any content at all")

        def boom(*_a, **_k):
            raise RuntimeError("matcher boom")

        orig_marker = ledger._promotion_marker
        ledger._promotion_marker = boom
        try:
            with self.assertRaises(RuntimeError):
                ledger.context(self.root)
        finally:
            ledger._promotion_marker = orig_marker


class LedgerRestitutionFoldingTests(unittest.TestCase):
    """Every site that RESTITUTES a runnable command folds its whitespace, and the
    scope of the guarantee is named rather than left universal (T-00000366).

    THE DISTINCTION THIS SUITE EXISTS TO PIN: `shlex.quote` seals for the LEXER,
    never for the EYE. A `ref` carrying a newline is perfectly safe when the
    command is pasted WHOLE — the newline sits inside the single quotes — but the
    restitution breaks into two visual lines, and copying HALF of it is the common
    gesture. Two readers, two functions, both applied.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _promoted(self, ref):
        ledger.add_entry(self.root, "lesson", "titre")
        entries = ledger.load(self.root)["entries"]
        lid = entries[0]["id"]
        ledger.promote_entry(self.root, lid, ref)
        return lid

    def test_fold_removes_newlines_tabs_and_runs_of_spaces(self):
        self.assertEqual(ledger.fold_for_display("a" + NL + "b" + chr(9) + "c"), "a b c")
        self.assertEqual(ledger.fold_for_display("  x   y  "), "x y")
        self.assertEqual(ledger.fold_for_display(""), "")
        self.assertEqual(ledger.fold_for_display(None), "")

    def test_negative_control_the_fold_is_not_a_no_op_and_not_a_shredder(self):
        """Replay the SAME function on input that MUST change, and on input that
        must NOT (L-00000057). A fold that changed everything would be as wrong as
        one that changed nothing."""
        dirty = "x" + NL + "y"
        self.assertNotEqual(ledger.fold_for_display(dirty), dirty)
        clean = "§ AGENTS.md — la doctrine"
        self.assertEqual(ledger.fold_for_display(clean), clean)

    def test_archive_warning_stays_on_ONE_line_for_a_forged_ref(self):
        """THE LINE FORGERY, on the two lines that had just been quote-hardened."""
        lid = self._promoted("surface" + NL + "SECONDE LIGNE FORGEE")
        msg = ledger.set_status(self.root, lid, "archived")
        # The whole restitution must carry no forged break. Counting the lines the
        # WARNING block occupies is the measurement: the block is designed to be
        # two lines, and a forged newline would make it three.
        warn = msg[msg.index("WARNING:"):]
        self.assertIn("SECONDE LIGNE FORGEE", warn, "non-vacuity: the ref text is still shown")
        # THE ANCHOR THAT ACTUALLY MEASURES IT, and the first one I wrote did NOT
        # (L-00000057 in this very test, caught by removing the fold and watching
        # nothing go red). Counting the lines that contain "tasks.py new" is useless:
        # with a newline inside the quoted argument the command still STARTS on one
        # line, so that count stays 1 whether folded or not. What moves is whether
        # the command's TAIL is on the SAME line as its head.
        runnable = [l for l in warn.split(NL) if "tasks.py new" in l]
        self.assertEqual(len(runnable), 1, "the command head vanished")
        self.assertIn(
            "--chantier registres", runnable[0],
            "the runnable command is SPLIT ACROSS LINES: its head and its tail are on "
            "different lines, so a partial copy yields a different command. `shlex.quote` "
            "seals it for the lexer; only the fold keeps it readable as one line.",
        )

    def test_paste_target_line_folds_too(self):
        """Site 3: no shell here and no deferred replay, so this is a DISPLAY
        defect only — which is exactly why it would have been left out of a fix
        bounded on "is it a shell injection?"."""
        ledger.add_entry(self.root, "lesson", "t")
        lid = ledger.load(self.root)["entries"][0]["id"]
        out = ledger.promote_entry(self.root, lid, "cible" + NL + "FORGEE")
        header = out.split(NL)[0]
        self.assertIn("FORGEE", header, "the ref must still be displayed")

    def test_the_archive_id_is_quoted_so_a_falsified_store_cannot_forge_a_command(self):
        """Site 4, and the honest framing of it: NOT GATING, because the id comes
        from the STORE and never from the CLI. The vector presupposes an already
        falsified LEDGER.json — and whoever can write that tracked file can write
        ledger.py itself. Quoted anyway: a restitution should not depend on the
        store being honest.
        """
        ledger.add_entry(self.root, "lesson", "t")
        data = ledger.load(self.root)
        forged = "L-1 ; touch PWN #  42"
        data["entries"][0]["id"] = forged
        ledger.save(self.root, data)
        out = ledger.promote_entry(self.root, forged, ".agents/skills/lessons-seed/SKILL.md")
        line = [l for l in out.split(NL) if "ledger.py" in l and "archive" in l]
        self.assertTrue(line, "the retraction line vanished")
        self.assertNotIn("; touch PWN", line[0].replace(shlex.quote(forged), ""),
                         "the semicolon reached the command unquoted")
        self.assertIn(shlex.quote(forged), line[0],
                      "the id is not quoted — a falsified store forges a runnable command")

    def test_scope_of_the_quoting_guarantee_is_POSIX_and_the_code_says_so(self):
        """L-00000079: a platform-scoped constraint must carry its scope or it is
        re-read as universal. `shlex.quote` emits POSIX single quotes and this kit
        runs on Windows boxes. Measured across three shells on the corrected line:
        Git Bash SAFE, PowerShell SAFE, **cmd.exe STILL INJECTS** (its `&` still
        separates). This test pins that the SOURCE says so, because the guarantee
        without its scope is the defect.
        """
        src = (ROOT / ".agents" / "bin" / "ledger.py").read_text(encoding="utf-8")
        self.assertIn("cmd.exe STILL INJECTS", src,
                      "the POSIX scope of shlex.quote is no longer named in the source")
        self.assertIn("L-00000079", src, "the lesson that demands the scope is not cited")


class LedgerSaveTrieLesClesTests(unittest.TestCase):
    """`save()` sérialise à clés triées, et deux cycles save/load sont idempotents.

    Fixture SYNTHÉTIQUE, jamais les données du dépôt : le témoin voyage tel quel
    chez un adoptant. Elle porte TOUTES les clés que `load()` pose par
    `setdefault` (`next_id` à la racine ; `text`, `tags`, `related` par entrée)
    — sur une fixture incomplète, `setdefault` APPEND la clé en fin de dict et
    l'égalité d'octets tomberait entre les deux cycles AVEC le bon code. Et UNE
    entrée est construite avec ses clés dans un ordre NON alphabétique : sans
    `sort_keys`, `json.dumps` conserve l'ordre d'insertion, donc l'égalité
    d'octets et l'égalité d'ids resteraient vertes avec ou sans la propriété —
    seule l'assertion de tri tombe, et c'est elle qui porte le témoin.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_save_est_idempotent_et_trie_les_cles_sur_un_store_synthetique(self):
        # Clés de racine ET de l'entrée L-00000002 insérées HORS ordre : à la
        # racine, `next_id` AVANT `entries` — l'ordre alphabétique inverse, sans
        # quoi l'assertion de racine ci-dessous ne pourrait jamais échouer.
        fixture = {
            "next_id": 3,
            "entries": [
                {
                    "id": "L-00000001",
                    "category": "lesson",
                    "title": "a",
                    "created": "2026-01-01",
                    "status": "active",
                    "text": "",
                    "tags": [],
                    "related": "",
                },
                {
                    "title": "b",
                    "id": "L-00000002",
                    "status": "active",
                    "text": "",
                    "category": "decision",
                    "tags": ["x"],
                    "created": "2026-01-02",
                    "related": "",
                },
            ],
        }
        store = ledger.store_path(self.root)

        ledger.save(self.root, fixture)
        premier = store.read_text(encoding="utf-8")
        relu = ledger.load(self.root)
        ledger.save(self.root, relu)
        second = store.read_text(encoding="utf-8")

        self.assertEqual(premier, second, "deux cycles save()/load() divergent en octets")
        depuis_octets = json.loads(second)
        # LISTE ordonnée, jamais un ensemble : l'ordre d'une liste porte du sens,
        # et un `save()` qui la retrierait resterait vert sur un ensemble d'ids.
        self.assertEqual(
            ["L-00000001", "L-00000002"],
            [e["id"] for e in depuis_octets["entries"]],
            "sort_keys ne doit jamais retrier une liste",
        )
        # Le tri se lit depuis les OCTETS du fichier, jamais depuis le dict que
        # `load()` rend — ce sont les deux assertions qui tombent sans `sort_keys`
        # (la racine grâce à `next_id` inséré avant `entries`).
        self.assertEqual(list(depuis_octets), sorted(depuis_octets))
        rec = next(e for e in depuis_octets["entries"] if e["id"] == "L-00000002")
        self.assertEqual(list(rec), sorted(rec))


if __name__ == "__main__":
    unittest.main()
