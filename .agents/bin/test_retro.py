"""Tests for retro.py — the LESSONS loop.

Style aligned with test_ledger.py, the store it sits beside: temp roots (never
touch the tracked retro/LESSONS.md), direct import (pytest's rootdir insertion
puts this file's directory on sys.path).

PIÈGE 3, and it is why the CLI cases below go through STDIN: on a Git-Bash argv
any payload starting with '/' is mangled into a Windows path before python sees
it. Every CLI case here passes its payload on stdin with `--text -`, which is
the escape retro.py offers precisely so a caller need not know the trap.
"""
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import retro

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 8, 25)


class RetroBase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._orig_today = retro._today
        retro._today = lambda: TODAY

    def tearDown(self):
        retro._today = self._orig_today
        self._tmpdir.cleanup()

    def add(self, text, cause="PERIMETRE_FLOU", portee="locale", source="verdict", when=None):
        if when is not None:
            retro._today = lambda: when
        try:
            return retro.add(self.root, cause, text, portee, source)
        finally:
            retro._today = lambda: TODAY

    def journal(self) -> str:
        return retro.journal_path(self.root).read_text(encoding="utf-8")

    def entry_lines(self) -> list[str]:
        """The ENTRIES only. The header itself documents the ` [à-promouvoir]`
        suffix, so a naive assertNotIn on the whole file matches the
        documentation and measures nothing."""
        return [l for l in self.journal().splitlines() if l.startswith("- 20")]


class RetroAddTests(RetroBase):
    def test_create_on_write_lays_down_the_journal_header(self):
        """BEHAVIOUR, and it is hermetic: an absent journal is CREATED carrying
        the module's header. Nothing here reads the tracked tree, which is what
        makes this arm green in an adopting project — where `retro/` does not
        exist at all (`strip:` in .template-exclude, :52)."""
        path = retro.journal_path(self.root)
        self.assertFalse(path.exists())          # witness: the absence is real
        self.add("une leçon")
        self.assertTrue(path.exists())
        self.assertTrue(
            self.journal().startswith(retro.JOURNAL_HEADER),
            "create-on-write did not lay down JOURNAL_HEADER",
        )

    def test_the_tracked_journal_header_has_not_drifted(self):
        """ANTI-DRIFT, and it MUST read the tracked tree: the constant and the
        shipped file would otherwise diverge, and an adopting project would get
        a journal whose stated bounds differ from this repo's.

        WHY A SKIP AND NOT A HERMETIC REWRITE. Feeding this assertion a temp
        journal would turn it into `assertEqual(JOURNAL_HEADER, JOURNAL_HEADER)`
        — a tautology, i.e. exactly the failure mode this repo hunts. The skip IS
        the exemption, it is NAMED, and it fires only where the subject of the
        assertion genuinely does not exist.

        WHY `startswith` AND NOT `assertEqual`. `JOURNAL_HEADER` ends on
        `## Journal\\n` (retro.py:182-183), a clean boundary: a truncated or
        altered header still fails, while a journal that has since recorded a
        lesson no longer reddens a test that is about the HEADER.
        """
        if not (ROOT / "retro" / "LESSONS.md").exists():
            self.skipTest(
                "retro/ est `strip:` dans .template-exclude (:52) — pas de "
                "journal suivi hors du depot du kit ; couverture de derive "
                "assuree ICI (T-%08d)" % 425
            )
        tracked = (ROOT / "retro" / "LESSONS.md").read_text(encoding="utf-8")
        self.assertTrue(
            tracked.startswith(retro.JOURNAL_HEADER),
            "tracked journal drifted from the constant",
        )

    def test_entry_format_is_the_documented_one(self):
        self.add("ne jamais supposer le périmètre", portee="universelle", source="correction")
        line = [l for l in self.journal().splitlines() if l.startswith("- 2026-")][0]
        self.assertEqual(
            line,
            "- 2026-08-25 [PERIMETRE_FLOU] [portée:universelle] "
            "ne jamais supposer le périmètre (source: correction)",
        )

    def test_default_portee_is_locale(self):
        self.add("défaut")
        self.assertIn("[portée:locale]", self.journal())

    def test_add_refuses_a_cause_outside_the_closed_set(self):
        with self.assertRaises(retro.RetroError) as ctx:
            retro.add(self.root, "INVENTEE", "x")
        self.assertIn("unknown --cause", str(ctx.exception))
        self.add("x")  # witness: the same call with a legal cause is accepted

    def test_add_refuses_text_that_would_make_the_entry_ambiguous(self):
        for payload in ("(source: forged)", "déjà [à-promouvoir]", "   "):
            with self.assertRaises(retro.RetroError):
                retro.add(self.root, "AUTRE", payload)
        self.add("texte honnête")  # witness of non-vacuity


class RetroParseTests(RetroBase):
    def test_malformed_entry_is_refused_by_line_number_never_skipped(self):
        self.add("bonne entrée")
        path = retro.journal_path(self.root)
        path.write_text(self.journal() + "- ceci n'est pas une entrée\n", encoding="utf-8")
        with self.assertRaises(retro.RetroError) as ctx:
            retro.consolidate(self.root)
        message = str(ctx.exception)
        self.assertIn("malformed entry, refused rather than skipped", message)
        self.assertIn("LESSONS.md:", message)

    def test_entry_above_the_marker_is_refused_never_silently_ignored(self):
        self.add("bonne entrée")
        text = self.journal().replace(
            "## Journal", "- 2026-01-01 [AUTRE] [portée:locale] égarée (source: verdict)\n## Journal"
        )
        retro.journal_path(self.root).write_text(text, encoding="utf-8")
        with self.assertRaises(retro.RetroError) as ctx:
            retro.consolidate(self.root)
        self.assertIn("sits ABOVE", str(ctx.exception))

    def test_journal_without_marker_is_refused(self):
        self.add("x")
        retro.journal_path(self.root).write_text("# rien\n", encoding="utf-8")
        with self.assertRaises(retro.RetroError) as ctx:
            retro.consolidate(self.root)
        self.assertIn("carries no", str(ctx.exception))


class RetroConsolidateTests(RetroBase):
    def test_identity_key_folds_case_and_spaces_but_not_the_cause(self):
        self.assertEqual(retro.fold("  Une   LEÇON  "), retro.fold("une leçon"))
        self.add("une leçon", cause="AUTRE")
        self.add("Une   LEÇON", cause="AUTRE")
        self.add("une leçon", cause="PERIMETRE_FLOU")  # same text, OTHER cause -> other key
        retro.consolidate(self.root)
        lines = [l for l in self.journal().splitlines() if l.startswith("- 2026-")]
        marked = [l for l in lines if retro.MARK.strip() in l]
        self.assertEqual(len(marked), 2, "the two AUTRE variants should be one group")
        self.assertTrue(all("[AUTRE]" in l for l in marked))

    def test_deux_reformulations_de_la_meme_lecon_ne_sont_jamais_marquees(self):
        """THE BOUND OF THE COUNTER, and the journal header states it: identical
        formulation only. Two reformulations of one lesson are two keys and the
        counter alone never reaches the threshold — human consolidation is the
        net for that limit (L-00000111, and the bound is IN this test's name)."""
        self.add("toujours relire le périmètre avant d'éditer", cause="PERIMETRE_FLOU")
        self.add("relire le périmètre, toujours, avant toute édition", cause="PERIMETRE_FLOU")
        out = retro.consolidate(self.root)
        self.assertFalse([l for l in self.entry_lines() if retro.MARK.strip() in l])
        self.assertIn("0 groupe(s) répété(s)", out)
        # Witness: the SAME formulation twice DOES reach the threshold, so the
        # zero above measures the reformulation, not a broken counter.
        self.add("toujours relire le périmètre avant d'éditer", cause="PERIMETRE_FLOU")
        retro.consolidate(self.root)
        self.assertEqual(len([l for l in self.entry_lines() if retro.MARK.strip() in l]), 2)

    def test_marking_is_idempotent(self):
        self.add("répétée", cause="AUTRE")
        self.add("répétée", cause="AUTRE")
        retro.consolidate(self.root)
        once = self.journal()
        retro.consolidate(self.root)
        self.assertEqual(once, self.journal())
        self.assertEqual([l.count(retro.MARK) for l in self.entry_lines()], [1, 1])

    def test_singletons_are_grouped_by_cause_before_any_purge(self):
        self.add("vieille et unique", cause="AUTRE", when=date(2026, 1, 1))
        self.add("récente", cause="CONTEXTE_MANQUANT")
        out = retro.consolidate(self.root)
        census = [l for l in out.splitlines() if l.startswith("SINGLETONS")][0]
        self.assertIn("AUTRE:1", census)                # counted THOUGH purged below
        self.assertIn("CONTEXTE_MANQUANT:1", census)
        self.assertIn("PURGE — 1 entrée(s)", out)
        self.assertNotIn("vieille et unique", self.journal())

    def test_purge_uses_the_today_seam_and_spares_a_repeated_lesson(self):
        self.add("répétée et vieille", cause="AUTRE", when=date(2026, 1, 1))
        self.add("répétée et vieille", cause="AUTRE", when=date(2026, 1, 2))
        self.add("unique et vieille", cause="AUTRE", when=date(2026, 1, 3))
        out = retro.consolidate(self.root)
        self.assertIn("répétée et vieille", self.journal())   # never purged: re-triggered
        self.assertNotIn("unique et vieille", self.journal())  # purged: > 90 j, single, unmarked
        self.assertIn("PURGE — 1 entrée(s)", out)
        # Witness on the SEAM: move today back and the same journal purges nothing.
        self.add("unique et vieille", cause="AUTRE", when=date(2026, 1, 3))
        retro._today = lambda: date(2026, 1, 10)
        retro.consolidate(self.root)
        self.assertIn("unique et vieille", self.journal())

    def test_cap_evicts_only_unmarked_entries(self):
        for i in range(60):
            self.add(f"leçon unique {i:03d}", cause="AUTRE")
        out = retro.consolidate(self.root)
        kept = [l for l in self.journal().splitlines() if l.startswith("- 2026-")]
        self.assertLess(len(kept), retro.CAP)
        self.assertIn("PLAFOND —", out)
        self.assertIn("évincée(s)", out)
        self.assertNotIn("leçon unique 000", self.journal())  # oldest went first
        self.assertIn("leçon unique 059", self.journal())     # newest survived

    def test_cap_is_declared_unreachable_when_every_entry_is_marked(self):
        """The cap NEVER evicts a marked entry: that mark is the human's
        shortlist. When the marked entries alone reach the cap, the cap is
        announced UNREACHABLE rather than quietly exceeded (L-00000111)."""
        for i in range(25):
            self.add(f"paire {i:03d}", cause="AUTRE")
            self.add(f"paire {i:03d}", cause="AUTRE")
        out = retro.consolidate(self.root)
        kept = self.entry_lines()
        self.assertEqual(len(kept), 50)
        self.assertTrue(all(retro.MARK.strip() in l for l in kept))
        self.assertIn("PLAFOND INATTEIGNABLE", out)
        # WITNESS, on a fresh root: 48 marked + 5 singletons is ABOVE the cap and
        # reachable — 4 singletons are evicted, every marked entry survives. So
        # the announcement above measures 'all marked', not a broken cap.
        with tempfile.TemporaryDirectory() as other:
            root = Path(other)
            for i in range(24):
                retro.add(root, "AUTRE", f"paire {i:03d}")
                retro.add(root, "AUTRE", f"paire {i:03d}")
            for i in range(5):
                retro.add(root, "CONTEXTE_MANQUANT", f"orpheline {i}")
            witness = retro.consolidate(root)
            self.assertIn("PLAFOND —", witness)
            self.assertIn("évincée(s)", witness)
            lines = [l for l in retro.journal_path(root).read_text(
                encoding="utf-8").splitlines() if l.startswith("- 20")]
            self.assertEqual(len(lines), 49)
            self.assertEqual(len([l for l in lines if retro.MARK.strip() in l]), 48)

    def test_routage_locale_reste_au_journal_et_ne_restitue_aucune_promotion(self):
        self.add("locale répétée", cause="AUTRE")
        self.add("locale répétée", cause="AUTRE")
        out = retro.consolidate(self.root)
        self.assertIn("PORTÉE LOCALE — 1 groupe(s)", out)
        self.assertIn("PORTÉE UNIVERSELLE — 0 groupe(s)", out)
        self.assertIn(retro.MARK.strip(), self.journal())

    def test_routage_universelle_restitue_les_deux_commandes_et_exige_une_entree_ledger(self):
        self.add("universelle répétée", cause="AUTRE", portee="universelle")
        self.add("universelle répétée", cause="AUTRE", portee="universelle")
        out = retro.consolidate(self.root)
        self.assertIn("PORTÉE UNIVERSELLE — 1 groupe(s)", out)
        self.assertIn('--ref ".agents/skills/<domaine>/SKILL.md"', out)
        self.assertIn('--ref ".agents/skills/lessons-seed/SKILL.md"', out)
        self.assertIn("PRÉALABLE — `promote` exige une entrée de registre existante", out)
        self.assertIn("n'écrit JAMAIS de surface d'atterrissage", out)

    def test_consolidate_universelle_restitue_le_cout_dinjection(self):
        """The cost line is what makes promotion an informed trade rather than a
        reflex — nothing else pins it, so a refactor would drop it silently
        (L-00000145)."""
        self.add("universelle répétée", cause="AUTRE", portee="universelle")
        self.add("universelle répétée", cause="AUTRE", portee="universelle")
        out = retro.consolidate(self.root)
        self.assertIn("COÛT D'INJECTION", out)
        self.assertIn(" ".join(retro.COST_LINE.split()), " ".join(out.split()))

    def test_la_ligne_de_cout_est_scopee_et_nomme_le_cas_adoptant(self):
        """L-00000079: a platform/repository-scoped fact written without its
        scope is re-read as universal. The measured '27 landed entries' is TRUE
        HERE and FALSE in a fresh adopting project, and this module TRAVELS — so
        the figure may never appear unscoped, and the adopting case must be
        named. Pinned on the SKILL too: lessons-seed carries the same words."""
        folded = " ".join(retro.COST_LINE.split())
        self.assertIn("SUR CE DÉPÔT (mesuré 2026-08-25) 27 entrées sont déjà atterries", folded)
        self.assertIn("SUR UN PROJET ADOPTANT le registre démarre vide", folded)
        self.assertIn("python .agents/bin/ledger.py context", folded)
        skill = (ROOT / ".agents" / "skills" / "lessons-seed" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(folded, " ".join(skill.split()), "lessons-seed drifted from COST_LINE")

    def test_output_truncation_beyond_forty_lines_is_announced(self):
        for i in range(40):
            self.add(f"groupe {i:03d}", cause="AUTRE")
            self.add(f"groupe {i:03d}", cause="AUTRE")
        out = retro.consolidate(self.root)
        lines = out.splitlines()
        # T-00000365: the DATA FRAME is line 1 and is NOT part of the bounded
        # body — it is prepended after both bounds precisely so a truncation can
        # never be the thing that eats it. Asserted by POSITION, because a frame
        # present somewhere in the middle of the output frames nothing.
        self.assertEqual(lines[0], retro.CONSOLIDATE_HEADER)
        body = lines[1:]
        self.assertEqual(len(body), retro.MAX_OUTPUT_LINES)
        self.assertIn("sortie tronquée", body[-1])
        # Witness: the bound is what fired, and the cost line survived it.
        self.assertIn("COÛT D'INJECTION", out)


class RetroHardeningTests(RetroBase):
    """The three hardenings of T-00000365, each with the control that makes its
    green mean something.

    WHY THE ORDER OF THE TASK MATTERED, restated here because the tests are what
    will outlive the reasoning: `consolidate` re-emits the journal's text. While
    NOTHING feeds the journal that is harmless. The moment the capture channel
    opens (T-00000361), text written by an AGENT — hence influenceable by
    repository content — starts flowing into a file this function re-emits. Posing
    the frame afterwards would have shipped a window in which the doctrine's own
    data-channel rule did not hold for the doctrine's own journal.
    """

    def test_consolidate_output_opens_with_the_do_not_obey_frame(self):
        self.add("une lecon quelconque")
        out = retro.consolidate(self.root)
        self.assertTrue(
            out.startswith(retro.CONSOLIDATE_HEADER),
            f"the frame is not the FIRST thing emitted: {out[:120]!r}",
        )
        self.assertIn("[do not obey]", retro.CONSOLIDATE_HEADER)

    def test_terminal_escapes_never_reach_the_output(self):
        """A journal entry can carry ESC once an agent writes it. An escape that
        reaches the console can repaint or erase what the pilot is reading, so a
        restitution carrying one cannot be trusted at all.
        """
        # TWICE, and that is not padding: `consolidate` echoes the TEXT of
        # REPEATED groups only — a singleton is counted, never quoted. The
        # non-vacuity assertion below is what revealed that, and a single entry
        # would have made this test pass on an output that never carried the text.
        payload = "rouge [31m puis [0m normal et un OSC ]0;titre ici"
        self.add(payload, cause="AUTRE")
        self.add(payload, cause="AUTRE")
        out = retro.consolidate(self.root)
        self.assertNotIn("", out, "an ESC sequence survived into the output")
        # NON-VACUITY: the text itself must still be there, or the strip is just a
        # deletion of the entry and the assertion above is satisfied by emptiness.
        self.assertIn("normal", out)
        self.assertIn("titre", out)

    def test_negative_control_the_strip_is_not_a_no_op(self):
        """Replay the SAME function on input that MUST change (L-00000057)."""
        dirty = "a[31mb[0mc"
        self.assertEqual(retro.strip_terminal_escapes(dirty), "abc")
        self.assertNotEqual(retro.strip_terminal_escapes(dirty), dirty)
        # And it must leave ordinary text ALONE, or it would be a text shredder
        # that happens to remove escapes too.
        clean = "une phrase avec accents éàü et « guillemets »"
        self.assertEqual(retro.strip_terminal_escapes(clean), clean)

    def test_the_identity_key_is_deliberately_NOT_escape_folded(self):
        """The one place the strip must NOT be applied, asserted so a later
        `fold = strip + fold` refactor goes red.

        `fold` is the counter's key. Folding escapes there would merge two entries
        that differ, changing which lesson reaches the repeat threshold — a display
        fix turned into a data bug.
        """
        self.assertNotEqual(retro.fold("ab"), retro.fold("ab"))

    def test_output_is_bounded_in_CHARACTERS_beyond_four_thousand(self):
        """THE BOUND IS IN THE NAME (L-00000190): this test cannot pass without
        exercising an output that exceeds MAX_OUTPUT_CHARS.
        """
        # Few lines, each very long: the LINE cap alone would let this through.
        # Each added TWICE so it becomes a repeated group and its text is actually
        # ECHOED — otherwise the output stays short and this test would assert a
        # bound that never fired.
        for i in range(6):
            payload = ("x" * 900) + f" {i}"
            self.add(payload, cause="AUTRE")
            self.add(payload, cause="AUTRE")
        out = retro.consolidate(self.root)
        self.assertLessEqual(len(out), retro.MAX_OUTPUT_CHARS + len(retro.CONSOLIDATE_HEADER) + 1)
        self.assertIn("tronquée en caractères", out)
        # The frame survived the character bound too.
        self.assertTrue(out.startswith(retro.CONSOLIDATE_HEADER))

    def test_negative_control_the_line_cap_alone_would_have_let_it_through(self):
        """The measured justification for adding a SECOND bound. Six lines is far
        under the forty-line cap, so `_bound` returns them untouched — proving the
        line cap was a bound in name only for long lines.
        """
        long_lines = [("y" * 900) for _ in range(6)]
        self.assertEqual(retro._bound(long_lines), long_lines)
        self.assertGreater(sum(len(x) + 1 for x in long_lines), retro.MAX_OUTPUT_CHARS)

    def test_write_is_atomic_and_leaves_no_temp_behind(self):
        self.add("premiere")
        self.add("seconde")
        journal = retro.journal_path(self.root)
        self.assertTrue(journal.is_file())
        leftovers = list(journal.parent.glob(".LESSONS-*.tmp"))
        self.assertEqual(leftovers, [], f"temp file(s) left behind: {leftovers}")
        self.assertIn("seconde", journal.read_text(encoding="utf-8"))

    def test_a_failed_publish_removes_its_temp_and_leaves_the_journal_intact(self):
        """The failure path, which is the half that matters: a torn write BRICKS
        BOTH VERBS, because `parse` refuses loudly rather than skipping a bad line.
        """
        self.add("avant")
        journal = retro.journal_path(self.root)
        before = journal.read_bytes()
        original = retro._replace_with_retry
        try:
            def boom(src, target, attempts=20):
                raise retro.RetroError("publication refusee (simulee)")
            retro._replace_with_retry = boom
            with self.assertRaises(retro.RetroError):
                retro.add(self.root, "AUTRE", "apres")
        finally:
            retro._replace_with_retry = original
        self.assertEqual(journal.read_bytes(), before, "the journal was mutated by a failed publish")
        self.assertEqual(
            list(journal.parent.glob(".LESSONS-*.tmp")), [],
            "a failed publish left its temp file behind",
        )
        # And the store is still READABLE — the point of the whole hardening.
        retro.parse(self.root)

    def test_the_journal_lock_is_exclusive_and_says_so_on_timeout(self):
        self.add("une")
        with retro.journal_lock(self.root):
            with self.assertRaises(retro.RetroError) as ctx:
                # A second acquisition from the same process must not silently
                # re-enter: this lock is NOT re-entrant, unlike ledger's, and the
                # timeout must NAME the file rather than hang.
                with retro.journal_lock(self.root, timeout_seconds=0.2):
                    pass
            self.assertIn("journal lock", str(ctx.exception))


class RetroCliTests(RetroBase):
    def _run(self, args, stdin=""):
        return subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "bin" / "retro.py"), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=stdin,
        )

    def test_cli_add_reads_a_slash_payload_from_stdin(self):
        result = self._run(
            ["add", "--cause", "CONSIGNE_MAL_PLACEE", "--text", "-"],
            stdin="/etc/passwd n'est pas un chemin à deviner",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/etc/passwd n'est pas un chemin à deviner", self.journal())

    def test_cli_refuses_an_unknown_cause_with_rc_2_family(self):
        bad = self._run(["add", "--cause", "INVENTEE", "--text", "-"], stdin="x")
        self.assertNotEqual(bad.returncode, 0)
        good = self._run(["add", "--cause", "AUTRE", "--text", "-"], stdin="x")
        self.assertEqual(good.returncode, 0, good.stderr)  # witness of non-vacuity

    def test_cli_consolidate_on_an_absent_journal_refuses_with_rc_2(self):
        result = self._run(["consolidate"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("retro.py:", result.stderr)


if __name__ == "__main__":
    unittest.main()
