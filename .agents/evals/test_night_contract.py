"""Contract tests for `/night` (T-00000196), with zero LLM calls and free CI (L-002).

Checks the two workflow surfaces and the `/kickoff --defer-night` route. The
schedule test measures every minute and both documents' literal rows: a drifting
table or a minute without a regime fails. Style follows test_plan_critic_contract.py.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); import surface_kit as _SK  # noqa: E401,E402,E702 — T-01M54MWW5GH
ROOT = Path(__file__).resolve().parents[2]

COMMAND = ROOT / ".claude" / "commands" / "night.md"
SKILL = ROOT / ".agents" / "skills" / "night" / "SKILL.md"
KICKOFF_COMMAND = ROOT / ".claude" / "commands" / "kickoff.md"
KICKOFF_SKILL = ROOT / ".agents" / "skills" / "kickoff" / "SKILL.md"
KEEPAWAKE = ROOT / ".agents" / "bin" / "night_keepawake.sh"

NIGHT_SURFACES = (COMMAND, SKILL)
# The carrier line of the turn-boundary wakeup (T-00000410), BYTE-IDENTICAL in
# night.md, SKILL.md and night_keepawake.sh. Written at the weakest TRUE form:
# it promises a re-arm at every turn boundary and nothing about interrupting a
# tool call in flight — the clause `IN_FLIGHT` states that limit, and is
# required TWICE per surface so the carrier block alone cannot satisfy it.
WAKEUP_LINE = (
    "RÉVEIL ARMÉ : à chaque frontière de tour, au plus 30 min après le tick "
    "précédent — un appel d'outil en vol n'est pas interrompu"
)
IN_FLIGHT = "un appel d'outil en vol n'est pas interrompu"

# shutil.which is how this kit pins bash on Windows (System32 hides the WSL relay
# shim ahead of Git Bash — test_dashboard.py:5872-5877, L-00000166). None → skip.
BASH = shutil.which("bash")

# The kit's command-listing surfaces must state `/night` is Claude-only. The old
# "eight carry the refusal" claim was false: only three did. The assertion below
# now holds the exact refusal on four emitting surfaces (L-00000111).
DOC_SURFACES = (
    *((ROOT / "README.md",) if _SK.EST_LE_KIT or _SK.readme_du_kit() else ()),  # hors kit : le README du kit seul (T-01M54MWW5GH)
    ROOT / "README-CLAUDE.md",
    ROOT / "README-OTHER-HOSTS.md",
    ROOT / "QUICK-SETUP.md",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "GEMINI.md",
    ROOT / ".github" / "copilot-instructions.md",
    # `docs/usage.html` RETIRÉ le 2026-09-09, décision du pilote — page de
    # présentation pour les adoptants, pas une surface de doctrine. Elle VOYAGE
    # toujours (test_sync_template.py l'exige en FROZEN/OWN) ; elle ne fait
    # simplement plus rougir la porte sur son contenu. NE PAS REMETTRE.
)

REFUSAL_LINE = "COVERAGE DEGRADED — /night is Claude Code only; refuse autonomous overnight runs"
# H-K1 : la trace du matin (night.md, night/SKILL.md) — (jeton, présent ?) ; O1/O2 retirent le premier VRAI.
TRACE_MATIN = (("le traceur n'écrit que sur les membres non consommés de la portée active", True),
               ("la trace part sous `_sans-slot`, ne crédite personne, et le `done` refuse", True),
               ("hors portée, une trace estampillée ne crédite personne", True), ("l'emprunt marqué au board", True),
               ("une trace NON estampillée (ancien traceur) ne crédite pas non plus", True),
               ("sans relecture ni marque d'emprunt", False), ("hors portée, les traces DIRECTES", False))

# The surfaces where a host must be able to EMIT that line verbatim, so the line
# itself has to be present and not merely described. Measured (T-00000342): P4
# moved the night block out of the router into the skill, and the exact line left
# the always-loaded layer with no test noticing — the two DOC_SURFACES arms only
# require `/night` and "Claude Code only", both of which an invariant satisfies
# while saying "refused elsewhere by a fixed line" WITHOUT giving the line. A
# router is read every session on all six hosts; a skill is read on demand. When
# the line IS the deliverable, describing it is not carrying it.
EMITTING_SURFACES = (ROOT / "AGENTS.md", ROOT / "GEMINI.md", ROOT / ".github" / "copilot-instructions.md",
                     ROOT / "README-OTHER-HOSTS.md")

# Reserves and cap, in minutes. Named here so a test failure points at the rule
# rather than at a magic number.
LANDING = 90  # atterrissage
CLOSING = 120  # clôture
RESERVE = LANDING + CLOSING  # 3h30
FULL_CAP = 720  # 12h00
ATT_FLOOR = FULL_CAP + RESERVE  # 15h30 — beyond this, the night waits


def windows(d):
    """(attente, plein, atterrissage, clôture) in minutes for a night of `d`
    minutes, or None when the night is refused. This IS the rule the two
    documents print."""
    if d < CLOSING:
        return None
    if d < RESERVE:
        return (0, 0, d - CLOSING, CLOSING)
    if d <= ATT_FLOOR:
        return (0, d - RESERVE, LANDING, CLOSING)
    return (d - ATT_FLOOR, FULL_CAP, LANDING, CLOSING)


def hm(minutes):
    return f"{minutes // 60}h{minutes % 60:02d}"


# The literal rows both documents print, as (D, attente, plein, atterrissage,
# clôture) in minutes.
LITERAL_ROWS = (
    (120, 0, 0, 0, 120),
    (180, 0, 0, 60, 120),
    (210, 0, 0, 90, 120),
    (330, 0, 120, 90, 120),
    (480, 0, 270, 90, 120),
    (720, 0, 510, 90, 120),
    (930, 0, 720, 90, 120),
    (960, 30, 720, 90, 120), (1439, 509, 720, 90, 120),
)


class NightScheduleTests(unittest.TestCase):
    """The partition is total, disjoint, and sums to D — over every minute."""

    def test_every_minute_of_the_day_has_a_regime(self):
        for d in range(0, 1440):
            with self.subTest(d=d):
                w = windows(d)
                if d < CLOSING:
                    self.assertIsNone(w, f"D={d} must be refused, not scheduled")
                    continue
                self.assertIsNotNone(w, f"D={d} must be scheduled, not refused")
                self.assertEqual(sum(w), d, f"D={d}: windows {w} sum to {sum(w)}, not D — a gap or an overlap")
                for part in w:
                    self.assertGreaterEqual(part, 0, f"D={d}: negative window in {w}")

    def test_reserves_are_honoured_whenever_they_fit(self):
        for d in range(RESERVE, 1440):
            _, _, landing, closing = windows(d)
            self.assertEqual((landing, closing), (LANDING, CLOSING), f"D={d}")

    def test_short_nights_shrink_the_landing_never_the_closing(self):
        for d in range(CLOSING, RESERVE):
            attente, plein, landing, closing = windows(d)
            self.assertEqual((attente, plein), (0, 0), f"D={d} must carry no chantier")
            self.assertEqual(closing, CLOSING, f"D={d} must keep the full closing window")
            self.assertEqual(landing, d - CLOSING, f"D={d}")

    def test_full_window_is_capped_at_twelve_hours(self):
        for d in range(RESERVE, 1440):
            _, plein, _, _ = windows(d)
            self.assertLessEqual(plein, FULL_CAP, f"D={d}: full window exceeds the 12h cap")

    def test_literal_rows_match_the_rule(self):
        for d, att, plein, landing, closing in LITERAL_ROWS:
            self.assertEqual(windows(d), (att, plein, landing, closing), f"D={hm(d)}")

    def test_command_prints_every_literal_row(self):
        text = COMMAND.read_text(encoding="utf-8")
        for d, att, plein, landing, closing in LITERAL_ROWS:
            row = "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                hm(d), hm(att), hm(plein), hm(landing), hm(closing), hm(d)
            )
            self.assertIn(row, text, f"missing literal row for D={hm(d)}")

    def test_skill_prints_every_literal_row(self):
        text = SKILL.read_text(encoding="utf-8")
        for d, att, plein, landing, closing in LITERAL_ROWS:
            row = "`{}` → `{}/{}/{}/{}`".format(
                hm(d), hm(att), hm(plein), hm(landing), hm(closing)
            )
            self.assertIn(row, text, f"missing literal row for D={hm(d)}")

    def test_midnight_crossing_is_modular_arithmetic_on_both_surfaces(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("mod 1440", text, f"{path}: midnight crossing rule absent")


class NightSurfaceTests(unittest.TestCase):
    def test_claim_refusal_skipped(self):
        """A fresh Git claim refuses one night start without consuming the agenda."""
        for path in NIGHT_SURFACES:
            with self.subTest(surface=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                start = text.index("**Refus `REVENDICATION` au vrai `start` ou `fournee`**")
                refusal = " ".join(text[start:text.index("\n\n**", start)].split())
                for required in ("refetch les remotes à chaque appel réel", "rc 2 avec `REVENDICATION`", "la nuit SAUTE cette tâche", "reste `pending`", ".agents/state/local/night/sautees",
                                 "<tâche> <- REVENDICATION: <motif rendu par tasks.py>", "`VERDICT` du tour comme le rapport du matin", "relu avant le choix de chaque tour", "une autre tâche éligible",
                                 "Ne rejouer ni avec `--sans-revendication`", "option désormais", "Ne jamais fournir `--reprise` automatiquement", "clone non fusionné", "tâche éligible de Bob",
                                 "REVENDICATION: ancien pilote a poussé après reprise", "à l'octet dans le rapport du matin", "les hooks du kit qui posent", "AGENTS_HOOK_HOST", "Claude Code",
                                 "Codex, Gemini et Kimi sans marqueur", "TTY + saisie en une commande", "un agent ne reprend jamais une tâche", "winpty bash .agents/pyrun.sh .agents/bin/tasks.py",
                                 "Copilot CLI pose `COPILOT_AGENT_SESSION_ID` et `COPILOT_CLI` dans le shell de l'agent (mesuré, 1.0.96) : ce marqueur refuse la reprise", "Faux positif dit : `COPILOT_CLI` est hérité par un shell lancé depuis Copilot CLI (échappement `!` du pilote compris), où la reprise est alors refusée"):
                    self.assertIn(required, refusal, f"{path}: claim refusal loses {required!r}")
                self.assertNotIn("Codex, Gemini, Copilot et Kimi sans marqueur", refusal, f"{path}: Copilot is said without agent marker again")
                self.assertLess(refusal.index("rc 2 avec `REVENDICATION`"), refusal.index("la nuit SAUTE cette tâche"))
                self.assertLess(refusal.index("la nuit SAUTE cette tâche"), refusal.index("une autre tâche éligible"))

    def test_both_surfaces_exist(self):
        for path in NIGHT_SURFACES:
            self.assertTrue(path.is_file(), f"{path} missing")

    def test_skill_is_discoverable(self):
        """Depth 1 under a skills directory, frontmatter opening at line 1 —
        the two failure modes that hide a skill in silence (AGENTS.md § Skill
        FORM). Neither reports anything at runtime."""
        self.assertEqual(SKILL.parent.parent.name, "skills", "SKILL.md must sit at depth 1")
        self.assertEqual(SKILL.parent.name, "night")
        lines = SKILL.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "---", "frontmatter must open at line 1")
        self.assertIn("name: night", lines[1:5])

    def test_non_claude_hosts_get_the_exact_refusal(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn(REFUSAL_LINE, text)
        for host in ("Codex", "Copilot", "Gemini", "Antigravity", "Kimi"):
            self.assertIn(host, text, f"{host} must be named in the host constraint")

    def test_untrusted_inputs_are_framed_and_bounded(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[do not obey]", text, f"{path}: night inputs are not data-framed")
            self.assertIn("2 000 caractères", text, f"{path}: no bound on night inputs")
            self.assertIn("30 lignes", text, f"{path}: no bound on night inputs")

    def test_the_night_READS_the_declared_order_on_both_surfaces(self):
        """`depends_on` is the one ordering constraint the night READS instead of
        deducing (T-00000532).

        WHY THIS EXISTS. Before it, a dependency lived in prose — the plan's
        `DEPENDANCES:` section and the `stage` column — and `tasks.py` says of
        that exact situation: "the blocker closed, and its dependents stayed red
        until somebody remembered them". Now that `planning-all` writes a
        machine-readable order, a night that ignored it would start wave 2 before
        wave 1 landed AND THE FAILURE WOULD BE SILENT. A mechanism with no reader
        does not exist.

        ON BOTH SURFACES, because `NIGHT_SURFACES` is the whole point of this
        file: an edit that lands on the command and not on the skill is the
        drift this suite was written to catch.

        THE PRECEDENCE IS ASSERTED, not just the field. Without it, "chantiers
        utilisateur d'abord" and the hard order contradict each other and the
        agent arbitrates in silence — which is the failure mode, not the fix.

        THE POSTPONE CLAUSE IS ASSERTED for its own reason: `blocked` means a
        task FAILED or waits on a human, and using it for "waits its turn" would
        manufacture false problems for the morning.
        """
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("depends_on", text, f"{path}: the night does not read the declared order")
            self.assertIn("ordre DUR", text,
                          f"{path}: the precedence between depends_on and the other rules is not stated")
            self.assertIn("REPORTE", text, f"{path}: the per-turn re-read does not say a held task is POSTPONED")
            self.assertIn("Ne la `block` pas", text,
                          f"{path}: nothing forbids turning 'waits its turn' into 'blocked'")

    def test_unknown_argument_is_refused_never_ignored(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("night: argument inconnu", text, f"{path}: an unrecognised argument must be refused by name")
            self.assertIn("^([01][0-9]\\|2[0-3]):[0-5][0-9]$", text, f"{path}: HH:MM not validated")

    def test_dry_run_writes_nothing(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            section = text[text.index("--dry-run` —") :]
            section = section.split("\n## ", 1)[0]
            for tool in ("tasks.py", "specs.py", "ledger.py", ".agents/state/local/night/"):
                self.assertIn(tool, section, f"{path}: --dry-run must name {tool} among what it does NOT touch")

    def test_headless_is_fail_closed(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(".agents/state/gates/NIGHT_HEADLESS.allow", text, str(path))
            self.assertIn("--max-budget-usd", text, str(path))
            self.assertIn("--allowed-tools", text, str(path))
            self.assertIn("night: --headless refusé — .agents/state/gates/NIGHT_HEADLESS.allow absente ou vide",
                          text, f"{path}: the refusal must be a named message, not a degraded print")

    def test_permission_bypass_is_never_printed(self):
        """`--dangerously-skip-permissions` may appear only in the sentence that
        forbids it. The Lavande source printed it inside the runnable loop; the
        repatriated version must not."""
        for path in NIGHT_SURFACES:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "--dangerously-skip-permissions" in line:
                    self.assertIn("jamais", line, f"{path}: bypass flag appears outside its own prohibition: {line!r}")

    def test_post_dev_order_is_strict(self):
        """security -> deterministic index rebuild -> documenter -> indexer.
        Same sequence as /kickoff: the night has no pipeline of its own."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            section = text[text.index("## Tenue de la nuit") :]
            idx_sec = section.index("security-code-review")
            idx_build = section.index("build_index.py --root . --if-stale")
            idx_doc = section.index("documenter")
            idx_indexer = section.index("indexer")
            self.assertLess(idx_sec, idx_build, f"{path}: security must precede the index rebuild")
            self.assertLess(idx_build, idx_doc, f"{path}: the rebuild must precede documenter")
            self.assertLess(idx_doc, idx_indexer, f"{path}: documenter must precede indexer")

    def test_board_invariant_survives_parallel_chantiers(self):
        """THE NIGHT MAY NOT DECIDE ITS OWN PARALLELISM (T-00000188): it runs with NO human, so it
        declares its group TO THE TOOL, which proves DECLARED writesets disjoint, and serialises
        when it cannot — never a disjunction asserted to itself."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("tasks.py parallel", text,
                          f"{path}: the night no longer names the tool that PROVES the group")
            self.assertIn("DÉCLARÉS", text, f"{path}: the night no longer says the proof bears on DECLARED writesets")
            self.assertIn("SÉRIALIS", text,
                          f"{path}: the night no longer says what to do when the proof is impossible")

    def test_night_preserves_foreign_running(self):
        """C25/C46 (T-01M5F729719KX08RQQCVS1PX0T): `start` demotes nobody; « au plus une `running` » is gone."""
        for path in NIGHT_SURFACES:
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("Les `running` étrangers sont PRÉSERVÉS", flat, f"{path}: foreign running not preserved")
            self.assertIn("ne l'embarque dans aucun groupe", flat, f"{path}: a foreign running may be embarked")
            for gone in ("au plus une `running`", "n'en garde qu'une", "frees the running slot"):
                self.assertNotIn(gone, flat, f"{path}: the single-running invariant is back ({gone!r})")
            low = flat.lower()  # any case, French or English: only the negation may speak of demotion
            self.assertEqual(low.count("rétrograd") + low.count("demot"), low.count("ne rétrograde plus personne"),
                             f"{path}: a `start` that demotes is still described")

    def test_morning_review_declares_scope(self):
        """C41: each morning closing critic (night.md route and report template, night/SKILL.md)
        is preceded by its `review-scope` declaration — a removed call names its site."""
        for path, expected in ((COMMAND, 2), (SKILL, 1)):
            text = path.read_text(encoding="utf-8")
            sites = [m.start() for m in re.finditer("critic-opus", text)
                     if "git diff <a>..<b>" in text[m.start():m.start() + 300]]
            self.assertEqual(len(sites), expected, f"{path}: the morning critic sites moved")
            flat = " ".join(text.split())  # H-K1 : traceur sur la portée seule (O1, O2), règle C, emprunt marqué
            for needle, dit in TRACE_MATIN:
                self.assertEqual(needle in flat, dit, f"{path}: trace rule {'unsaid' if dit else 'back'}: {needle!r}")
            for i in sites:
                where, w = f"{path.relative_to(ROOT)}:{text.count(chr(10), 0, i) + 1}", text[max(0, i - 700):i].lower()
                self.assertIn("review-scope t-nnn", w, f"{where}: no scope declared")
                self.assertIn("avant le critique", w, f"{where}: the scope is not declared BEFORE the critic")

    def test_copilot_mirror_declares_scope(self):
        """C44 (1): the Copilot mirror declares the review scope before each closing critic."""
        flat = " ".join((ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8").split())
        for needle in ("tasks.py review-scope T-NNN [T-NNN ...]", "JUST BEFORE each closing critic", "credits nobody",
                       "The borrow follows the declared scope, never the chantier", "`portée consommée`",
                       "same active scope or the same declared `parallel_group`, never by chantier",
                       # H-K1 : traceur sur la portée seule (O3), port muet sans `running`, emprunt de groupe, règle C
                       "The trace lands ONLY on the non-consumed members of the ACTIVE review scope",
                       "on Copilot the port writes nothing and stays silent when no task is `running`",
                       "unless it borrows through a declared `parallel_group` from a `running` member covered",
                       "an unstamped trace (older tracer) credits nothing either"):
            self.assertIn(needle, flat, f"copilot-instructions.md: missing {needle!r}")
        for gone in ("demotes the slot", "under a chantier whose slot", "slot of its chantier",
                     "which credits nobody, and the `done` refuses", "`portee consommee`, `board illisible`)"):
            self.assertNotIn(gone, flat, f"copilot-instructions.md: stale demotion or chantier borrow ({gone!r})")

    def test_empty_blocker_block_is_mandatory(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("CE QUI BLOQUE", text, str(path))
            self.assertIn("bloc vide", text, f"{path}: an empty CE QUI BLOQUE must still be written")

    def test_verification_output_is_never_truncated(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("verify.sh --at HEAD --linux", text, f"{path}: the closing gate must run on a frozen checkout")
            self.assertIn("tail", text, f"{path}: the no-truncation rule (L-00000140) is absent")


# Every fenced block — backticks OR tildes (CommonMark), any info string (`sh`, `bash`,
# `text`, none), indented or not (the skill nests its `sh` block inside a list item);
# the closing fence must use the SAME character as the opening one. BOUND, said rather
# than hidden: an INDENTED code block (4 spaces, no fence) is NOT covered — it cannot be
# told apart from a list item's continuation without a Markdown parser.
_FENCE = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n(.*?)^[ \t]*\1", re.DOTALL | re.MULTILINE)


def _fenced_bodies(text):
    """The bodies of the fenced blocks — `findall` yields (fence, body) tuples."""
    return [body for _fence, body in _FENCE.findall(text)]
_BINOME_WAIT_BLOCK = 'tasks.py block T-NNN --note "NUIT : attente binôme du matin'
# A variable holding the CLI, however quoted or braced: `$T`, `"$T"`, `${T}`, `'${T}'`.
_VAR = r"[\"']?\$\{?\w+\}?[\"']?"
# Global options that may sit between the CLI and its verb (`tasks.py --root . done`).
_OPTS = r"(?:(?:--root|--lock-timeout)(?:[ \t]+|=)\S+[ \t]+|--statusline[ \t]+)*"
# CODE (fenced): any `tasks.py done`, whatever the path or the cwd (`cd .agents/bin &&
# python tasks.py done`), and any variable holding the CLI. `[ \t]` rather than `\s`
# so a `$var` at a line end never pairs with a shell loop's `done` below it — line
# continuations (`\` + newline) are normalised to a space BEFORE matching instead.
_DONE_IN_CODE = re.compile(rf"(?:tasks\.py[\"']?|{_VAR})[ \t]+{_OPTS}done\b")
# PROSE: the runnable forms only — a path, an interpreter, or a variable in front of
# `done`. Prose that FORBIDS the gesture names the bare `tasks.py done`, and the pilot's
# morning step gives the short form without an interpreter.
_DONE_RUNNABLE_IN_PROSE = re.compile(
    rf"(?:(?:\.agents/bin/|python3?[ \t]+|pyrun\.sh[ \t]+)tasks\.py[\"']?|{_VAR})[ \t]+{_OPTS}done\b"
)
_CONTINUATION = re.compile(r"\\\r?\n[ \t]*")


def _night_closing_violations(text):
    """What the night would EXECUTE to close a task — the forms this contract refuses.

    A fenced block is what the resolved prompt copies and the loop types: there, any
    `done` on the board CLI and any `--sans-binome` is refused. Outside the fences only
    the RUNNABLE forms are refused, so prose may still NAME `tasks.py done` /
    `--sans-binome` to forbid them, or give the pilot's morning `done`.
    """
    bad = []
    text = _CONTINUATION.sub(" ", text)
    blocks = _fenced_bodies(text)
    for block in blocks:
        m = _DONE_IN_CODE.search(block)
        if m:
            bad.append(f"fenced block runs {m.group(0)!r}: {block.strip()[:160]!r}")
        if "--sans-binome" in block:
            bad.append(f"fenced block runs '--sans-binome': {block.strip()[:160]!r}")
    prose = _FENCE.sub("", text)
    m = _DONE_RUNNABLE_IN_PROSE.search(prose)
    if m:
        bad.append(f"runnable `{m.group(0)}` present in prose")
    return bad


class NightDoesNotCloseTests(unittest.TestCase):
    """T-00000842 — pilot decision 2026-09-29, « binôme au matin ».

    `BINOME_REQUIRED` refuses a `done` without one traced closing critic (`BINOME_MIN`,
    S-00004500). A night that typed `tasks.py done` left the task `running` without a
    review — or an unattended agent reached for `--sans-binome`, an exit reserved for a duplicate, a stale ticket
    or a code-free decision. The night now BLOCKS a finished task with the note
    `NUIT : attente binôme du matin`; the closing review, fixes, gate and `done` run
    in the morning. ZERO LLM, text shape over both surfaces.
    """

    def test_no_surface_makes_the_night_run_done_or_sans_binome(self):
        for path in NIGHT_SURFACES:
            bad = _night_closing_violations(path.read_text(encoding="utf-8"))
            self.assertFalse(bad, f"{path}: the night still closes a task — {bad}")

    def test_the_binome_wait_block_is_the_runnable_end_of_a_finished_turn(self):
        for path in NIGHT_SURFACES:
            blocks = _fenced_bodies(path.read_text(encoding="utf-8"))
            self.assertTrue(
                any(_BINOME_WAIT_BLOCK in b for b in blocks),
                f"{path}: no fenced `block --note \"NUIT : attente binôme du matin …\"` line",
            )

    def test_the_morning_route_and_the_gate_reframing_are_written(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for needle in (
                "La nuit NE CLÔT PAS",
                "`start` directement depuis `blocked`",
                "jamais `unblock`",
                "Une tâche à la fois",
                "@ <a>..<b> ; fichiers <writeset> ; plan <chemin> verdict S-NNNNNNNN",
                "[SANS CHAÎNE DE PLAN : <preuve de nuit>]",
                "git diff <a>..<b> -- <writeset>",
                _NIGHT_PY + "tasks.py writeset T-NNN --clear",
                ".agents/state/local/binome/T-NNN.*.json",
                _NIGHT_PY + "tasks.py binome-purge T-NNN",
                "SEULEMENT si `.agents/state/gates/PLAN_CHAIN_REQUIRED` existe",
                "SANS sa queue `[SANS CHAÎNE …]`",
                # T-00001044: `tok=$(…)` + `case … esac` is refused by `claude -p`;
                # the closing is ONE `&&` chain of simple commands.
                _NIGHT_PY + "tasks.py commit-stores --exiger && "
                + _NIGHT_PY + "tasks.py commit-run-exports --exiger && ",
                "une tâche de jour bloquée `--on` une tâche de nuit",
                "critic-opus",
                "critic-fable",
                "critic-sonnet-max",
                "`blocked` ≠ `pending`",
                "JAMAIS `--on T-…`",
                "n'autorise AUCUNE clôture",
                "ATTENTE BINÔME DU MATIN",
            ):
                self.assertIn(needle, text, f"{path}: missing {needle!r}")
            # the morning purge goes through the verb: `safe-bash.sh` refuses an `rm`
            # on these files (« outside », rc 2), and `ls -l` + manual deletion was
            # the unrunnable prescription critic-fable measured.
            self.assertNotIn("ls -l .agents/state/local/binome", text, f"{path}: manual purge is back")
            self.assertIsNone(re.search(r"\brm\b[^\n]*state/local/binome", text), f"{path}: an `rm` purge is back")
            for gone in ("`critic-opus` " + "∥", "deux critiques " + "DISTINCTS", "closing pair"):  # S-00004500: ONE critic
                self.assertNotIn(gone, text, f"{path}: the closing pair is back ({gone!r})")

    def test_negative_control_the_old_night_done_line_reddens(self):
        old = (
            "```sh\n"
            'python .agents/bin/tasks.py done T-NNN --raison "<livré>" '
            '--sans-cible "nuit autonome — plan <chemin> approuvé @ <sha>, étapes non annotées"\n'
            "```\n"
        )
        self.assertTrue(_night_closing_violations(old), "the old night `done` line passes the arm")
        self.assertTrue(
            _night_closing_violations('  ```sh\n  tasks.py done T-1 --raison x --sans-binome "y"\n  ```\n'),
            "an indented fenced `done --sans-binome` passes the arm",
        )
        # F6 (critic-opus): the tick's own interpreter form, in prose, must redden too.
        self.assertTrue(
            _night_closing_violations(
                'finir à sa place, ou `bash .agents/pyrun.sh .agents/bin/tasks.py done T-1 --raison "x"`.\n'
            ),
            "the `pyrun.sh` runnable done form passes the arm",
        )
        # F6 (critic-fable): a `cd` that drops the path, and a variable holding the CLI.
        self.assertTrue(
            _night_closing_violations('```sh\ncd .agents/bin && python tasks.py done T-1 --raison "x"\n```\n'),
            "the `cd … && python tasks.py done` form passes the arm",
        )
        self.assertTrue(
            _night_closing_violations(
                '```sh\nT="python .agents/bin/tasks.py"\n$T done T-1 --raison "x"\n```\n'
            ),
            "the `$T done` form passes the arm",
        )
        self.assertTrue(
            _night_closing_violations('ou `$T done T-1 --raison "x"` en fin de tour.\n'),
            "the `$T done` form in prose passes the arm",
        )
        # critic-fable counter-review: global options, a line continuation, a quoted
        # and a braced variable must all redden.
        for form in (
            "python .agents/bin/tasks.py --root . done T-1 --raison x",
            "python .agents/bin/tasks.py \\\n  done T-1 --raison x",
            '"$T" done T-1 --raison x',
            "${T} done T-1 --raison x",
        ):
            self.assertTrue(
                _night_closing_violations("```sh\n" + form + "\n```\n"),
                f"{form!r} passes the arm",
            )
        # a tilde fence is a fence too (CommonMark).
        self.assertTrue(
            _night_closing_violations('~~~sh\npython .agents/bin/tasks.py done T-1 --raison "x"\n~~~\n'),
            "a `~~~sh` fenced done passes the arm",
        )
        # a READ of done tasks is not a closure.
        self.assertFalse(
            _night_closing_violations("```sh\npython .agents/bin/tasks.py list --state done\n```\n"),
            "`list --state done` reddens the arm",
        )
        # and the arm does not trip on a shell loop's `done` after a `$var` line end.
        self.assertFalse(
            _night_closing_violations('```bash\nwhile [ -n "$x" ]; do\n  echo "$x"\ndone\n```\n'),
            "a shell loop's `done` reddens the arm",
        )
        self.assertFalse(
            _night_closing_violations(
                "la nuit ne tape JAMAIS `tasks.py done`, JAMAIS `--sans-binome`.\n"
                "```sh\n" + _BINOME_WAIT_BLOCK + ' — x @ abc"\n```\n'
            ),
            "the arm refuses the prose that FORBIDS the gesture — it would be unwritable",
        )


# T-00001044: the night types the kit's scripts through the interpreter resolver
# (`python` is absent on many macOS/Linux hosts, rc 127), so every gesture the
# night surfaces copy is pinned in THAT form. The kickoff surfaces keep theirs.
_NIGHT_PY = "bash .agents/pyrun.sh .agents/bin/"
_NIGHT_DELIVERED_ADD = (
    _NIGHT_PY + 'specs.py add --task T-NNNNNNNN --kind decision '
    '"night-delivered: attente binome du matin"'
)
# T2 (critic-opus): the clearing is forbidden IN THE LINE COPIED INTO EVERY TURN,
# not only in prose the loop never copies.
_CLEARED_FORBIDDEN = "ni entrée `night-delivered: cleared` (geste du pilote seul)"
_NIGHT_DELIVERED_CLEAR_GESTURE = (
    _NIGHT_PY + 'specs.py add --task T-NNNNNNNN --kind decision "night-delivered: cleared"'
)
# critic-fable NO_GO (pilot decision): the night's relevé of the marker — in the
# kickoff surfaces' form (`_DELIVERED_READ`) and in the night's (`_NIGHT_…`).
_DELIVERED_READ = "python .agents/bin/night_approve.py --delivered T-NNNNNNNN"
_NIGHT_DELIVERED_READ = _NIGHT_PY + "night_approve.py --delivered T-NNNNNNNN"
_NIGHT_DELIVERED_CLEAR = '--kind decision "night-delivered: cleared"'


def _marker_before_block_violations(text):
    """The fenced gesture must journal the marker, THEN block — in one block."""
    for block in _fenced_bodies(text):
        if _BINOME_WAIT_BLOCK in block:
            add = block.find(_NIGHT_DELIVERED_ADD)
            if add < 0:
                return ["the fenced `block … attente binôme du matin` carries no night-delivered add"]
            if add > block.find(_BINOME_WAIT_BLOCK):
                return ["the night-delivered add comes AFTER the block"]
            return []
    return ["no fenced `block … attente binôme du matin`"]


class NightDeliveredMarkerTests(unittest.TestCase):
    """T-00000847 — the durable remedy critic-opus asked for on T-00000842.

    `blocked` keeps a delivered task out of the next night, but a state moves
    (`unblock`, an explicit exit from `running`, `reopen`). The night now
    journals a `night-delivered` decision right BEFORE its `block`, and the
    eligibility list refuses a task carrying one in force (condition 7 of
    `night_approve.py`). ZERO LLM, text shape over both surfaces.
    """

    def test_the_marker_is_journaled_before_the_block_in_the_same_fence(self):
        for path in NIGHT_SURFACES:
            bad = _marker_before_block_violations(path.read_text(encoding="utf-8"))
            self.assertFalse(bad, f"{path}: {bad}")

    def test_the_eligibility_list_names_the_marker_and_its_erasure(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for needle in (
                "6. **la tâche n'a PAS DÉJÀ ÉTÉ LIVRÉE par une nuit** (condition 7 de `night_approve.py`",
                # critic-fable NO_GO: the relevé is the numeric sub-command, never the
                # string-comparing `specs.py list --task`
                _NIGHT_DELIVERED_READ,
                "rc 2",
                # residue 3: the protect-paths bound is said on both surfaces
                "`sed -i`/`python -c` ne sont pas tenus, seule la redirection l'est"
                if path == SKILL else "(`python -c`, `sed -i`) n'est pas tenu",
                # GO_AVEC_RESERVES residue 1: only rc 0 establishes the condition
                "seul rc 0 établit la condition",
                # residue 2: both refusal motifs, exact strings of night_approve.py
                "`MARQUEUR night-delivered EN VIGUEUR — S-NNNNNNNN`",
                "`condition 7 : … deja livree par la nuit`",
                "SEULE délégation",
                "suivi d'un caractère hors `[A-Za-z0-9_-]`, casse ignorée",
                "refusé en Edit/Write par protect-paths",
                "règle `specs-journal`",
                "la plus récente prévaut",
                _NIGHT_DELIVERED_CLEAR,
                "`done` du matin SUFFIT",
                "MARQUEUR night-delivered ABSENT",
                # (2) the order is the id, never the date
                "(le plus grand `S-`, dernière ligne de `specs.py list` ; jamais la `date`)",
                # T1: numeric id, short form included
                "id NUMÉRIQUE",
                # T2: the clearing is forbidden in the copied line, and reported
                _CLEARED_FORBIDDEN,
                "datée de la nuit",
                # (3): the report derives the absence from the sub-command's rc
                "--delivered T-NNNNNNNN` rend rc 0",
                # T3: the measured divergence is written as a bound
                "17 des 95 contrats" if path == SKILL else "17 citent un autre verdict que le dernier",
            ):
                # whitespace-normalised: a needle must not break on a line wrap
                self.assertIn(" ".join(needle.split()), " ".join(text.split()), f"{path}: missing {needle!r}")
            self.assertNotIn("non\n  fait, tâche à ouvrir", text, f"{path}: the remedy is still « to open »")
            self.assertNotIn("serait le remède durable", text, f"{path}: the remedy is still conditional")
            # the string-comparing read must not come back as the night's relevé
            for launcher in ("python .agents/bin/", _NIGHT_PY):
                self.assertNotIn(
                    f"relevé par `{launcher}specs.py list --task", text,
                    f"{path}: the relevé cites the string-comparing specs.py list again",
                )

    def test_the_clearing_is_never_a_gesture_of_the_loop(self):
        """The pilot's clearing lives in prose, never in a fence the loop copies.

        Hardened (critic-fable): an absence alone was green on the old text, which
        had no clearing at all. The PRESENCE of the pilot's gesture in prose is
        asserted too, so the arm reddens on a surface that lost it."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for block in _fenced_bodies(text):
                self.assertNotIn("night-delivered: cleared", block, f"{path}: clearing in a fence")
            self.assertIn(_NIGHT_DELIVERED_CLEAR_GESTURE, _FENCE.sub("", text),
                          f"{path}: the pilot's clearing gesture is not written in prose")

    def test_every_night_delivered_template_uses_the_LONG_id_form(self):
        """T1: `specs.py` records the id as typed; the template gives the long form.

        Hardened (critic-fable): the long-form marker line must be PRESENT in a
        fence — an absence of the short form alone was green on a text without any
        marker at all."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r'specs\.py add --task T-NNN --kind decision "night-delivered', text),
                f"{path}: a short-form night-delivered template is back",
            )
            self.assertTrue(
                any(_NIGHT_DELIVERED_ADD in b for b in _fenced_bodies(text)),
                f"{path}: no fenced long-form night-delivered add",
            )

    def test_defer_night_reads_the_marker_before_writing_a_contract(self):
        """Point 2 (pilot decision): both kickoff surfaces read `--delivered` as a
        PRECONDITION of the contract, and send the pilot to the clearing."""
        for path in (KICKOFF_COMMAND, KICKOFF_SKILL):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            pre = flat.find("PRECONDITION (T-00000847): read `" + _DELIVERED_READ + "`")
            self.assertGreaterEqual(pre, 0, f"{path}: no --delivered precondition")
            self.assertLess(pre, flat.find('"night-eligible: approved" --text'),
                            f"{path}: the precondition comes after the contract")
            self.assertIn("NOT write the contract", flat)
            # residue 1: ANY rc other than 0 refuses — not only the two named ones
            self.assertIn("**any rc other than 0** (1 = marker in force, 2 = journal "
                          "unreadable, anything else = the read did not run)", flat)
            self.assertIn("`night-delivered: cleared` himself first", flat)

    def test_the_copied_line_forbids_the_clearing(self):
        """T2: in night.md the ban sits in the « Recopie VERBATIM » paragraph itself."""
        text = COMMAND.read_text(encoding="utf-8")
        start = text.index("**Recopie VERBATIM")
        end = text.index("```", start)
        self.assertIn(_CLEARED_FORBIDDEN, text[start:end].replace("\n", " "))

    def test_negative_control_the_old_fence_reddens(self):
        old = "```sh\n" + _BINOME_WAIT_BLOCK + ' — x @ a..b"\n```\n'
        self.assertTrue(_marker_before_block_violations(old), "a block without marker passes")
        swapped = (
            "```sh\n" + _BINOME_WAIT_BLOCK + ' — x"\n' + _NIGHT_DELIVERED_ADD + ' --text "x"\n```\n'
        )
        self.assertTrue(_marker_before_block_violations(swapped), "marker after block passes")
        good = (
            "```sh\n" + _NIGHT_DELIVERED_ADD + ' --text "x"\n' + _BINOME_WAIT_BLOCK + ' — x"\n```\n'
        )
        self.assertFalse(_marker_before_block_violations(good), "the right order reddens")


class DeferNightContractTests(unittest.TestCase):
    """`/kickoff --defer-night` is what makes a task night-eligible."""

    SURFACES = (KICKOFF_COMMAND, KICKOFF_SKILL)

    def test_defer_night_documented_on_both_kickoff_surfaces(self):
        for path in self.SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("--defer-night", text, f"{path}: the deferred-approval route is absent")

    def test_contract_fields_are_named(self):
        for path in self.SURFACES + NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for field in ("night-eligible: approved", "sha256=", "plan=", "verdict="):
                self.assertIn(field, text, f"{path}: contract field {field!r} missing")

    def test_deferred_task_stays_pending(self):
        for path in self.SURFACES:
            text = path.read_text(encoding="utf-8")
            section = text[text.index("--defer-night") :]
            self.assertIn(
                "`pending`",
                section,
                f"{path}: a deferred task must stay pending, never start",
            )

    def test_absent_contract_is_a_refusal_not_an_implicit_yes(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "refus, pas un oui implicite",
                text,
                f"{path}: backward compatibility must be stated as a refusal",
            )

    def test_modified_plan_loses_eligibility(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("hashlib.sha256", text, f"{path}: no way to prove the plan is unchanged")


class NightDocumentedEverywhereTests(unittest.TestCase):
    def test_night_is_listed_on_every_documentary_surface(self):
        for path in DOC_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("/night", text, f"{path}: /night is not listed")

    def test_claude_only_limit_is_stated_wherever_night_is_listed(self):
        pattern = re.compile(r"Claude Code (?:only|uniquement)|Claude Code seul", re.IGNORECASE)
        for path in DOC_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                pattern.search(text),
                f"{path}: lists /night without stating it is Claude Code only",
            )


class NightWakeupContractTests(unittest.TestCase):
    """The turn-boundary wakeup tick and the fail-loud fallback (T-00000410).

    ZERO LLM. Pure text-shape over the two surfaces. The carrier line is the
    load-bearing string; the ordering nets pin the launch sequence so the prompt
    is proven to carry the tick BEFORE the ledger is touched, and the wakeup is
    armed BEFORE the loop.
    """

    def _section(self, path, header):
        text = path.read_text(encoding="utf-8")
        return text[text.index(header) :].split("\n## ", 1)[0]

    def test_carrier_line_on_both_surfaces_and_in_the_reveil_section(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(WAKEUP_LINE, text, f"{path}: carrier line absent")
            self.assertIn(
                WAKEUP_LINE,
                self._section(path, "## Réveil armé"),
                f"{path}: carrier line is not inside the ## Réveil armé section",
            )

    def test_in_flight_clause_appears_at_least_twice_per_surface(self):
        # once in the carrier block, once in the honesty paragraph — the block
        # alone would satisfy an >=1 net vacuously (L-00000232 shape).
        for path in NIGHT_SURFACES:
            self.assertGreaterEqual(
                path.read_text(encoding="utf-8").count(IN_FLIGHT),
                2,
                f"{path}: in-flight clause must be in the block AND the honesty paragraph",
            )

    def test_does_not_fire_during_a_machine_sleep_on_both_surfaces(self):
        for path in NIGHT_SURFACES:
            self.assertIn(
                "ne tire pas pendant une veille",
                path.read_text(encoding="utf-8"),
                f"{path}: the honest limit (no fire during sleep) is absent",
            )

    def test_launch_orders_check_prompt_then_ledger_then_start_then_loop(self):
        for path in NIGHT_SURFACES:
            sec = self._section(path, "## Lancement")
            i_check = sec.index("--check-prompt")
            i_ledger = sec.index("ledger.py add")
            i_start = sec.index("night_keepawake.sh start")
            i_loop = sec.index("/loop 30m")
            self.assertLess(i_check, i_start, f"{path}: --check-prompt must precede start")
            self.assertLess(i_start, i_loop, f"{path}: start must precede /loop")
            self.assertTrue(
                i_check < i_ledger < i_start,
                f"{path}: ledger.py add must sit BETWEEN --check-prompt and start",
            )

    def test_fallback_and_degraded_are_named_in_launch(self):
        for path in NIGHT_SURFACES:
            sec = self._section(path, "## Lancement")
            self.assertIn("ScheduleWakeup", sec, f"{path}: no ScheduleWakeup fallback")
            self.assertIn(
                "COVERAGE DEGRADED — réveil indisponible",
                sec,
                f"{path}: no fail-loud when no wakeup mechanism is exposed",
            )

    def test_tick_names_its_moves(self):
        for path in NIGHT_SURFACES:
            sec = self._section(path, "## Réveil armé")
            for needle in (
                "date",
                "pyrun.sh .agents/bin/tasks.py list",
                "agents en vol",
                "> 30 min",
                "wakeup.log",
                "SendMessage",
                "kill -0",
            ):
                self.assertIn(needle, sec, f"{path}: the tick misses {needle!r}")

    def test_dry_run_arms_no_wakeup(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            section = text[text.index("--dry-run` —") :].split("\n## ", 1)[0]
            self.assertIn("n'arme aucun réveil", section, f"{path}")
            self.assertIn("--probe", section, f"{path}: --probe is the only permitted mode")

    def test_dry_run_sequence_is_still_unique(self):
        # test_dry_run_writes_nothing anchors on text.index("--dry-run` —");
        # that anchor is only unambiguous while the sequence occurs exactly once.
        for path in NIGHT_SURFACES:
            self.assertEqual(
                path.read_text(encoding="utf-8").count("--dry-run` —"),
                1,
                f"{path}: the --dry-run anchor is no longer unique",
            )

    def test_headless_block_arms_bounds_and_disarms(self):
        # The runnable loop lives in the command only, not the skill.
        sec = self._section(COMMAND, "## `--headless`")
        self.assertLess(
            sec.index("night_keepawake.sh start"),
            sec.index("while"),
            "the wakeup must be armed before the loop",
        )
        self.assertLess(
            sec.index("timeout"), sec.index("claude -p"), "the timeout bound must wrap claude -p"
        )
        self.assertIn("GNU coreutils", sec, "timeout must be probed for GNU coreutils (C24)")
        self.assertGreater(
            sec.rindex("night_keepawake.sh stop"),
            sec.index("done"),
            "the wakeup must be disarmed after the loop",
        )

    def test_sentinels_disarm_the_wakeup_on_both_surfaces(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("night_keepawake.sh stop", text, str(path))
            self.assertIn("ScheduleWakeup(stop: true)", text, str(path))

    def test_gate_states_the_three_wakeup_labels_in_the_command(self):
        text = COMMAND.read_text(encoding="utf-8")
        for label in ("ANTI-VEILLE :", "RÉVEIL :", "BORNE :"):
            self.assertIn(label, text, f"night.md gate misses the {label!r} line")

    def test_both_surfaces_carry_the_antisleep_probe(self):
        for path in NIGHT_SURFACES:
            self.assertIn(
                "night_keepawake.sh --probe", path.read_text(encoding="utf-8"), str(path)
            )

    def test_script_carries_the_line_and_the_named_refusal(self):
        text = KEEPAWAKE.read_text(encoding="utf-8")
        self.assertIn(WAKEUP_LINE, text, "the script must carry the carrier line (A7)")
        self.assertIn("night: prompt résolu sans consigne de réveil", text)

    def test_negative_control_old_and_rev1_phrasings_do_not_satisfy(self):
        old = (
            "boucle dans cette session via `/loop`, en te donnant à toi-même le "
            "contenu du prompt résolu comme consigne, avec `ScheduleWakeup` entre les tours"
        )
        rev1 = "toutes les 30 min, sans attendre la fin d'un tour"
        for described in (old, rev1):
            self.assertNotIn(
                WAKEUP_LINE,
                described,
                "a phrasing that only alludes to the wakeup must NOT match the carrier line",
            )
        for path in NIGHT_SURFACES:  # the witness: the real surfaces carry it
            self.assertIn(WAKEUP_LINE, path.read_text(encoding="utf-8"))


@unittest.skipIf(BASH is None, "no bash on this box — the degraded path covers the script")
class NightKeepawakeScriptTests(unittest.TestCase):
    """The script itself, 0-LLM, on stubs — three OS legs plus the refusals.

    Bash pinned via shutil.which and asserted not to be the System32 WSL shim, so
    the three CI legs (ubuntu/macOS/Windows, `shell: bash`) run the same code.
    Never spawns a real detached keep-awake: `start` proper is measured by the
    bash bench (`night_keepawake.test.sh`), the python arm stays on read-only and
    dry-run modes so it leaks no process.
    """

    @classmethod
    def setUpClass(cls):
        cls.stubs = tempfile.mkdtemp()
        for tool in ("caffeinate", "systemd-inhibit", "pwsh"):
            p = os.path.join(cls.stubs, tool)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("#!/usr/bin/env bash\nsleep 300\n")
            os.chmod(p, 0o755)

    def setUp(self):
        self.assertNotIn(
            "system32", BASH.lower(), "resolved the WSL relay shim, which cannot exec the script"
        )

    def _run(self, args, os_name=None, path=None, state=None):
        env = dict(os.environ)
        env["PATH"] = path if path is not None else self.stubs + os.pathsep + os.environ.get("PATH", "")
        if os_name is not None:
            env["NIGHT_KEEPAWAKE_OS"] = os_name
        if state is not None:
            env["NIGHT_KEEPAWAKE_STATE_DIR"] = state
        return subprocess.run(
            [BASH, str(KEEPAWAKE), *args], capture_output=True, text=True, env=env
        )

    def _absent(self):
        return os.path.join(tempfile.mkdtemp(), "state", "absent")

    def test_probe_darwin_names_caffeinate(self):
        state = self._absent()
        r = self._run(["--probe", "--minutes", "30"], os_name="darwin", state=state)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("caffeinate -dims -t 1800", r.stdout)
        self.assertFalse(os.path.exists(state))

    def test_probe_linux_names_systemd_inhibit(self):
        state = self._absent()
        r = self._run(["--probe", "--minutes", "30"], os_name="linux", state=state)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("systemd-inhibit", r.stdout)
        self.assertIn("sleep 1800", r.stdout)
        self.assertFalse(os.path.exists(state))

    def test_probe_windows_names_set_thread_execution_state(self):
        state = self._absent()
        r = self._run(["--probe", "--minutes", "30"], os_name="windows", state=state)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SetThreadExecutionState", r.stdout)
        self.assertFalse(os.path.exists(state))

    def test_absent_tool_is_rc3_and_degraded(self):
        state = self._absent()
        r = self._run(
            # PATH = un répertoire VIDE, jamais un PATH nu : `/usr/bin:/bin` rendrait ce contrôle
            # hôte-dépendant (Ubuntu porte /usr/bin/systemd-inhibit → rc 0 → faux rouge/vert).
            ["--probe", "--minutes", "30"], os_name="linux", path=tempfile.mkdtemp(), state=state
        )
        self.assertEqual(r.returncode, 3)
        out = r.stdout + r.stderr
        self.assertIn("COVERAGE DEGRADED — anti-veille indisponible (linux)", out)
        self.assertIn("ne tirera pas pendant une veille", out)
        self.assertFalse(os.path.exists(state))

    def test_unknown_os_is_rc3(self):
        r = self._run(["--probe", "--minutes", "30"], os_name="plan9")
        self.assertEqual(r.returncode, 3)

    def test_minutes_out_of_range_is_rc2(self):
        for m in ("0", "1441", "abc"):
            r = self._run(["--probe", "--minutes", m], os_name="darwin")
            self.assertEqual(r.returncode, 2, f"--minutes {m}: {r.stdout}{r.stderr}")

    def test_check_prompt_rc0_with_line_rc1_without(self):
        d = tempfile.mkdtemp()
        ok = os.path.join(d, "ok.md")
        with open(ok, "w", encoding="utf-8") as fh:
            fh.write("head\n" + WAKEUP_LINE + "\ntail\n")
        r = self._run(["--check-prompt", ok], os_name="darwin")
        self.assertEqual(r.returncode, 0, r.stderr)
        bad = os.path.join(d, "bad.md")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("head\naucune consigne\n")
        r = self._run(["--check-prompt", bad], os_name="darwin")
        self.assertEqual(r.returncode, 1)
        self.assertIn("night: prompt résolu sans consigne de réveil", r.stdout + r.stderr)

    def test_check_prompt_headless_on_the_blocks_the_surfaces_copy(self):
        """T-00001044 — end to end on the REAL blocks of night.md: the full tick
        passes the watched check and is REFUSED by `--headless` (it types
        `kill -0 "$(cat …)"`, refused by `claude -p`); the tick with the headless
        line swapped in passes `--headless`. On the old script `--headless` is an
        unknown argument (rc 2) — red."""
        text = COMMAND.read_text(encoding="utf-8")
        sec = text[text.index("## Réveil armé") :].split("\n## ", 1)[0]
        blocks = _fenced_bodies(sec)
        full = next(b for b in blocks if WAKEUP_LINE in b)
        headless_line = next(b for b in blocks if b.startswith("- les agents en vol") and "kill -0" not in b)
        kill_line = next(line for line in full.splitlines() if "kill -0" in line)
        d = tempfile.mkdtemp()
        p_full, p_hl = os.path.join(d, "full.md"), os.path.join(d, "hl.md")
        with open(p_full, "w", encoding="utf-8") as fh:
            fh.write(full)
        with open(p_hl, "w", encoding="utf-8") as fh:
            fh.write(full.replace(kill_line + "\n", headless_line))
        self.assertEqual(self._run(["--check-prompt", p_full], os_name="darwin").returncode, 0)
        # the full block lacks the replacement line (Opus T6): refused for that
        r = self._run(["--check-prompt", "--headless", p_full], os_name="darwin")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("ligne de remplacement", r.stderr)
        # replacement line present but the pid gesture kept: refused for the gesture
        p_both = os.path.join(d, "both.md")
        with open(p_both, "w", encoding="utf-8") as fh:
            fh.write(full + headless_line)
        r = self._run(["--check-prompt", "--headless", p_both], os_name="darwin")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("geste de réveil", r.stderr)
        r = self._run(["--check-prompt", "--headless", p_hl], os_name="darwin")
        self.assertEqual(r.returncode, 0, r.stderr)
        # the explicit option exists only right after --check-prompt
        r = self._run(["--probe", "--minutes", "30", "--headless"], os_name="darwin")
        self.assertEqual(r.returncode, 2)

    def test_reading_modes_create_no_state_directory(self):
        for args in (["--probe", "--minutes", "30"], ["start", "--minutes", "5", "--dry-run"]):
            state = self._absent()
            r = self._run(args, os_name="darwin", state=state)
            self.assertEqual(r.returncode, 0, f"{args}: {r.stderr}")
            self.assertFalse(os.path.exists(state), f"{args} created the state dir")
        ok = os.path.join(tempfile.mkdtemp(), "ok.md")
        with open(ok, "w", encoding="utf-8") as fh:
            fh.write(WAKEUP_LINE + "\n")
        state = self._absent()
        r = self._run(["--check-prompt", ok], os_name="darwin", state=state)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(state))


if __name__ == "__main__":
    unittest.main()


class NightRefusalLineIsCarriedNotDescribedTests(unittest.TestCase):
    """The exact refusal line lives on every surface a non-Claude host reads.

    Written at the WEAKEST TRUE form and one step above the measured state
    (L-00000253): three surfaces carried it when this was written, four carry it
    now. It deliberately does NOT demand it from the other five documentary
    surfaces — README, README-CLAUDE, QUICK-SETUP, CLAUDE.md and usage.html are
    read by a human or by Claude itself, where the line is not the deliverable.
    That exemption is stated rather than left as an omission.
    """

    def test_the_exact_line_is_present_where_a_host_must_emit_it(self):
        for path in EMITTING_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                REFUSAL_LINE, text,
                f"{path.name}: describes the refusal without CARRYING the line. A host "
                "that must emit it verbatim cannot, and no other arm sees this: the two "
                "DOC_SURFACES arms accept an invariant that merely mentions a fixed line.",
            )

    def test_non_vacuity_the_emitting_set_is_the_one_the_docstring_names(self):
        # A parametrised-by-tuple check with an emptied tuple passes vacuously
        # (L-00000232). Assert the population, and that it is a SUBSET of the
        # documentary surfaces rather than a second, drifting list.
        self.assertEqual(len(EMITTING_SURFACES), 4)
        for path in EMITTING_SURFACES:
            self.assertIn(path, DOC_SURFACES, f"{path} is not a documentary surface")

    def test_negative_control_the_arm_refuses_a_described_but_absent_line(self):
        # Replay the rule on text that DESCRIBES the refusal the way the router's
        # invariant did before this task, and require it to fail.
        described = (
            "**`/night`** existe sur **Claude Code seul** et est refusé ailleurs "
            "par une ligne fixe."
        )
        self.assertNotIn(
            REFUSAL_LINE, described,
            "the arm accepts a surface that only DESCRIBES the line, so its green "
            "proves nothing about a host being able to emit it",
        )
        # And the witness: the real router must pass the same check.
        self.assertIn(REFUSAL_LINE, (ROOT / "AGENTS.md").read_text(encoding="utf-8"))


class NightRunExportCommitTests(unittest.TestCase):
    """The night's closing commits the run exports ITSELF (T-00000677).

    THE DEFECT. The closing named the ``runs/`` commit as a manual gesture by the
    pilot — UNEXECUTABLE during an unattended night, so the pushed SHA never
    carried the night's events (closure pair S-00001808/S-00001809). And the
    morning pre-check read a ``M runs/`` as an un-committed export whose remedy
    was a hand commit — false every night, since nothing committed runs/ during
    it. The closing now runs a dedicated verb; these arms pin that the human
    gesture is GONE and the verb is NAMED, on BOTH surfaces (the skill TRAVELS,
    so an adopter without this repo must read the true story too).

    A doc that keeps asserting a remedy the code no longer needs is what stops
    anyone from seeing the fix (L-00000111), so absence is asserted, not assumed.
    """

    VERB = "tasks.py commit-run-exports"

    # The exact manual-remedy fragments this task removed. Scoped to the
    # run-export remedy: ``à la main`` legitimately appears elsewhere on these
    # surfaces (the anti-sleep teardown, the pilot-approved task), so a blanket
    # assertNotIn would be a false red — the test names WHAT must be gone.
    MANUAL_REMEDY_FRAGMENTS = (
        "à la main par le pilote",
        "À LA MAIN par le pilote",
        "À LA MAIN de ces fichiers",
        "plus de verbe dédié",
        "verbe de commit dédié",
    )

    #: B5 (critic-fable): the manual-remedy claim survived the previous fix in
    #: CHANGELOG.md because this witness only swept the two NIGHT_SURFACES. The
    #: CHANGELOG is added, but BOUND to its "Non publié" section — see
    #: `_changelog_unreleased_section` for why a journal cannot be swept whole.
    #: E3 : hors du kit, CHANGELOG.md devient une destination adoptant à E5.
    #: La skill de nuit reste une surface livrée et jugée.
    CHANGELOG = ROOT / "CHANGELOG.md"

    def test_the_commit_verb_is_named_on_both_surfaces(self):
        for path in NIGHT_SURFACES:
            self.assertIn(
                self.VERB,
                path.read_text(encoding="utf-8"),
                f"{path}: the closing does not name the run-export commit verb",
            )

    def test_no_manual_run_export_commit_survives(self):
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for frag in self.MANUAL_REMEDY_FRAGMENTS:
                self.assertNotIn(
                    frag,
                    text,
                    f"{path}: a manual run-export commit gesture survives: {frag!r}",
                )

    def test_db_vestige_is_gone_from_the_command_closing(self):
        # The `.db` the pushed SHA "must carry" was a vestige: the V3 base left
        # the repo with T-00000677; its versioned exports carry the history.
        text = COMMAND.read_text(encoding="utf-8")
        section = text[text.index("Clôture séquentielle") :].split("\n## ", 1)[0]
        self.assertNotIn(
            "porter le `.db`",
            section,
            "the closing still promises the pushed SHA carries the .db vestige",
        )

    def test_negative_control_the_old_manual_text_would_fail(self):
        # Replay the rule on the pre-task text and require it to trip: proves the
        # arm is not vacuous (L-00000232). This is the string the command carried
        # before the fix.
        old = (
            "commit des exports de run `runs/` (**à la main par le pilote** — le "
            "store V3 vit hors dépôt"
        )
        self.assertTrue(
            any(frag in old for frag in self.MANUAL_REMEDY_FRAGMENTS),
            "the fragment set no longer catches the manual gesture it was written for",
        )

    def _changelog_unreleased_section(self):
        # Seul « Non publié » décrit le geste actuel. Une version publiée est historique ;
        # une fausse consigne rangée sous cette version échappe donc à ce témoin.
        text = self.CHANGELOG.read_text(encoding="utf-8")
        tail = text[text.index("## Non publié") :]
        cut = tail.index("\n## ") if "\n## " in tail else len(tail)
        return tail[:cut]

    def test_no_manual_run_export_commit_survives_on_delivered_surface(self):
        # B5: the previous fix left "À LA MAIN par le pilote (option (b))" in
        # CHANGELOG.md because this witness swept only the two NIGHT_SURFACES — the
        # channel by which the false text survived (critic-fable). The CHANGELOG
        # unreleased section is now swept with the same augmented fragment set.
        surfaces = [SKILL.read_text(encoding="utf-8")]
        if _SK.EST_LE_KIT:
            surfaces.append(self._changelog_unreleased_section())
        self.assertTrue(surfaces and surfaces[0], "aucune surface de nuit livrée")
        for section in surfaces:
            for frag in self.MANUAL_REMEDY_FRAGMENTS:
                self.assertNotIn(
                    frag,
                    section,
                    f"une surface de nuit porte encore le geste manuel: {frag!r}",
                )

    def test_negative_control_the_changelog_fragment_would_fail(self):
        # Ancien texte : contrôle négatif du jeu de fragments.
        old = "`runs/` est commité À LA MAIN par le pilote en clôture (option (b))"
        self.assertTrue(
            any(frag in old for frag in self.MANUAL_REMEDY_FRAGMENTS),
            "the fragment set no longer catches the manual gesture the CHANGELOG carried",
        )

    # ---- T-00000677 follow-up (exec-critic on da699e8): the closing must TREAT
    #      the verb's tokens, and the morning pre-check must stop promising a
    #      single cause. A doc asserting a guarantee the code does not hold is
    #      what stops anyone from seeing the defect (L-00000111). ----

    # Success tokens are RELAYED from the shell section leg (post-task-done-index.sh:
    # `committed | nothing | busy | failed`), NOT literals in commit_run_exports, so
    # they are frozen here and named as the relay — not derivable from tasks.py.
    SUCCESS_TOKENS = ("committed", "nothing")

    # Failure tokens are the string literals RETURNED by commit_run_exports in
    # tasks.py. DERIVED from the source (below) rather than copied, so a fifth
    # failure `return "<token>"` appearing there reddens
    # test_failure_tokens_are_derived_from_tasks_py instead of drifting in silence.
    # If that function ever returns a failure via a VARIABLE rather than a literal
    # this derivation would miss it — stated, not hidden — and this frozen set stays
    # the authority the surfaces are checked against.
    FROZEN_FAILURE_TOKENS = frozenset({"bash-introuvable", "locked-out", "failed"})

    TASKS_PY = ROOT / ".agents" / "bin" / "tasks.py"

    @classmethod
    def _commit_run_exports_source(cls):
        text = cls.TASKS_PY.read_text(encoding="utf-8")
        marker = "def commit_run_exports("
        start = text.index(marker)
        rest = text[start + len(marker) :]
        m = re.search(r"\ndef ", rest)
        return text[start : start + len(marker) + (m.start() if m else len(rest))]

    @classmethod
    def _derived_failure_tokens(cls):
        return set(re.findall(r'return\s+"([a-z0-9-]+)"', cls._commit_run_exports_source()))

    def _closing_section(self, path):
        text = path.read_text(encoding="utf-8")
        tail = text[text.index("Clôture séquentielle") :]
        return tail[: tail.index("\n## ")] if "\n## " in tail else tail

    def _morning_section(self, path):
        text = path.read_text(encoding="utf-8")
        tail = text[text.index("` M runs/") :]  # anchor unique to the morning pre-check
        return tail[: tail.index("\n- ")] if "\n- " in tail else tail

    def test_failure_tokens_are_derived_from_tasks_py_not_copied(self):
        # The list READS itself out of commit_run_exports, so a fifth token cannot
        # slip in unnoticed: a new (or removed) `return "<token>"` breaks this
        # equality — the "cinquième jeton" the reviewer named.
        self.assertEqual(
            self._derived_failure_tokens(),
            set(self.FROZEN_FAILURE_TOKENS),
            "commit_run_exports gained/lost a return-literal token; update BOTH surfaces AND this set",
        )

    #: The FIFTH outcome, and the one the tasks.py derivation cannot see: the shell
    #: section leg prints `busy:<marker>` when a git operation is in progress or HEAD
    #: is detached. It emits it AFTER recognising the selector (`case`, :63) and
    #: BEFORE any add/commit (:89-96) — shared post-`case` code, so it reaches
    #: `run-exports` exactly as it reaches `stores` (B4: the earlier note said "before
    #: it branches on the selector", which is FALSE — the busy check sits AFTER the
    #: case block, not before it; the conclusion held, the reason did not). A catch-all
    #: ("any other token blocks the push") covers it in effect, but an unnamed outcome
    #: is how a doc starts asserting a guarantee the code does not hold (L-00000111).
    SECTION_LEG = ROOT / ".agents" / "bin" / "post-task-done-index.sh"

    def test_the_busy_token_is_emitted_by_the_leg_and_named_on_both_surfaces(self):
        leg = self.SECTION_LEG.read_text(encoding="utf-8")
        # Derived, not remembered: the emission SITE must exist, or this arm is
        # asserting doctrine about a token the code no longer produces.
        self.assertIn(
            "printf 'busy:%s'",
            leg,
            "post-task-done-index.sh no longer emits busy: — drop it from the night surfaces too",
        )
        # B4: the ORDER the surfaces now state, measured against the file rather than
        # remembered — the busy check runs AFTER the selector `case`, not before it.
        # A reversed doc claim ("before it branches on the selector") is then a lie
        # the code contradicts (L-00000111).
        self.assertLess(
            leg.index('case "$selector" in'),
            leg.index("printf 'busy:%s'"),
            "the busy check no longer sits AFTER the selector case — the surfaces' reasoning is now false",
        )
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "busy:",
                self._closing_section(path),
                f"{path}: the closing does not name the busy: outcome of the section leg",
            )
            self.assertNotIn(
                "brancher sur le sélecteur",
                text,
                f"{path}: the false 'before it branches on the selector' reasoning survives",
            )

    def test_the_four_verb_tokens_are_named_on_both_surfaces(self):
        # committed / nothing (success) + the three failure tokens = every token
        # the verb can hand the night, named where a night agent reads it.
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            for token in self.SUCCESS_TOKENS + tuple(sorted(self.FROZEN_FAILURE_TOKENS)):
                self.assertIn(
                    token, text, f"{path}: the closing does not name the verb token {token!r}"
                )

    def test_the_exiger_chaining_form_is_cited_on_both_surfaces(self):
        # B1 (T-00000677): "a failure token PREVENTS the push" is now MECHANISM, not
        # prose — `--exiger` turns the token into an exit code so the closing chains
        # the gate with `&&`. The surfaces must cite the runnable chaining form, or
        # the mechanism the code now holds is invisible to the night agent that types
        # it. (The EXIT-CODE effect itself is proven in the tasks.py unit suite, where
        # main() can be driven with a stubbed token; here we pin the doc contract.)
        chain = "commit-run-exports --exiger && bash core-scripts/verify.sh --at HEAD --linux"
        for path in NIGHT_SURFACES:
            self.assertIn(
                chain,
                path.read_text(encoding="utf-8"),
                f"{path}: the closing does not cite the --exiger chaining form",
            )

    def test_a_secret_caught_by_the_export_commit_has_a_local_remedy(self):
        # B3 (T-00000677): the gate runs AFTER the export commit, so a secret caught
        # by `git add -- runs` is already committed when the fresh secret bench trips
        # — but that commit is still LOCAL (not pushed). The remedy is therefore local
        # (`git reset --soft`, removal, credential ROTATION — class 0), never
        # the append-only rewrite of T-00000696, which only touches already-pushed
        # lines. COMMAND only: this is the night's operational sequence.
        #
        # Since T-00000703 every `done` of the night has its OWN `chore(runs):`,
        # so the offending exports commit is NOT necessarily HEAD: the remedy
        # must say how to FIND it (`git log -S` under `runs/`) and `reset --soft
        # HEAD~1` — which would keep the secret in place when it sits deeper —
        # is refused (critic-opus F1). Mutation that reddens: restore `HEAD~1`.
        section = self._closing_section(COMMAND)
        self.assertIn(
            "reset --soft",
            section,
            "the closing gives no local remedy for a secret caught by the export commit",
        )
        self.assertNotIn(
            "reset --soft HEAD~1",
            section,
            "the closing still prescribes `reset --soft HEAD~1` — since T-00000703 the "
            "offending exports commit is not necessarily HEAD",
        )
        self.assertIn(
            "-S'",
            section,
            "the closing does not say how to FIND the offending exports commit (git log -S)",
        )
        self.assertIn(
            "rotation",
            section.lower(),
            "the closing does not require rotating the credential (class 0) on such a secret",
        )

    def test_a_closure_failure_prevents_the_push_on_both_surfaces(self):
        # The guard chain is STATED in the closing SECTION (not merely elsewhere in
        # the file): each failure token is present AND tied to blocking the push,
        # so a frozen SHA without the night's events is never pushed.
        for path in NIGHT_SURFACES:
            section = self._closing_section(path)
            for token in sorted(self.FROZEN_FAILURE_TOKENS):
                self.assertIn(
                    token, section, f"{path}: failure token {token!r} absent from the closing sequence"
                )
            self.assertIn(
                "EMPÊCHE le push",
                section,
                f"{path}: the closing does not say a failure token blocks the push",
            )

    def test_morning_precheck_departs_three_causes_in_order(self):
        # ` M runs/` at morning is THREE possible causes, not two (B2, T-00000677):
        # a really INTERRUPTED night, a verb that FAILED its export commit, OR a
        # board write POSTERIOR to a SUCCESSFUL commit — every mutating verb replays
        # the V3 bridge and re-dirties runs/. The tiebreak ORDER is written, departed
        # by the exit sentinel and the report, never asserted as one (L-00000111).
        # This arm reddens if the count DRIFTS: the three cause discriminators must
        # ALL be present AND the stale "DEUX choses" claim gone, so dropping a cause
        # (or reverting to two) trips it — not one frozen count string swapped for
        # another (the reviewer's bar: "ne remplace pas un compte figé faux par un
        # compte figé juste sans témoin").
        for path in NIGHT_SURFACES:
            section = self._morning_section(path)
            self.assertNotIn(
                "DEUX choses", section, f"{path}: morning pre-check still asserts two causes"
            )
            self.assertIn(
                "TROIS", section, f"{path}: morning pre-check does not say three causes"
            )
            for discriminator in ("interrompue", "verbe en échec", "POSTÉRIEUR"):
                self.assertIn(
                    discriminator,
                    section,
                    f"{path}: morning pre-check drops the cause discriminator {discriminator!r}",
                )
            self.assertIn(
                "sentinelle",
                section,
                f"{path}: morning pre-check names no means to tell the causes apart",
            )
            for token in sorted(self.FROZEN_FAILURE_TOKENS):
                self.assertIn(
                    token, section, f"{path}: morning pre-check does not name failure token {token!r}"
                )

    def test_morning_precheck_says_the_day_done_commits_its_own_exports(self):
        # Since T-00000703 every day's `done` plays `commit-run-exports` after
        # its stores (second leg of post-task-done-index.sh), so a ` M runs/` at
        # morning reads as cause (3) in the LARGE sense — any V3 event write
        # posterior to the last exports commit, whatever its entry point — or as
        # a `done` whose exports leg was skipped or refused. The clause must sit
        # INSIDE the morning bullet: moved after the next `- ` it leaves the
        # slice `_morning_section` cuts, and this reddens. "T-00000703" is the
        # discriminator on BOTH surfaces (on night.md the verb was already in
        # the slice before this task, so it alone would be a weak witness).
        for path in NIGHT_SURFACES:
            section = self._morning_section(path)
            self.assertIn(
                "T-00000703",
                section,
                f"{path}: morning pre-check does not say the day's done commits its exports",
            )
            self.assertIn(
                "commit-run-exports",
                section,
                f"{path}: morning pre-check does not name the verb the day's done plays",
            )

    def test_the_verb_is_typeable_from_the_form_these_files_use(self):
        # Scorie: the verb was cited bare `tasks.py commit-run-exports` while these
        # files invoke the kit's scripts through ONE launcher everywhere else —
        # `bash .agents/pyrun.sh .agents/bin/tasks.py ...` since T-00001044. A night
        # agent must be able to type it without guessing the launcher.
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                _NIGHT_PY + "tasks.py commit-run-exports",
                text,
                f"{path}: the verb is not cited in the runnable form the files use",
            )

    def test_negative_control_the_new_arms_are_not_vacuous(self):
        # (1) the derivation actually finds tokens (an empty set matching an empty
        #     frozen set would pass vacuously — L-00000232);
        # (2) the frozen population is the three the docstring names;
        # (3) the section helpers return DISTINCT slices and the push-block phrase
        #     lives in the closing only, so neither arm reads the other's text.
        self.assertTrue(self._derived_failure_tokens(), "derivation returned an empty set — regex drifted")
        self.assertEqual(len(self.FROZEN_FAILURE_TOKENS), 3)
        for path in NIGHT_SURFACES:
            closing, morning = self._closing_section(path), self._morning_section(path)
            self.assertNotEqual(closing, morning, f"{path}: closing and morning slices collapsed to one")
            self.assertIn("EMPÊCHE le push", closing, f"{path}: closing slice lost its push-block phrase")
            self.assertNotIn(
                "EMPÊCHE le push", morning, f"{path}: morning slice bled into the closing sequence"
            )


# A bare interpreter in front of a kit script: `python .agents/bin/x.py`,
# `python3 .agents/bin/x.py`. Word-bounded on the left so `bash .agents/pyrun.sh`
# (whose path ends in `.sh`) and prose like `python`/`python3` do not match.
_BARE_LAUNCHER = re.compile(r"(?<![\w./-])python3? +\.agents/bin/[A-Za-z0-9_]+\.py")


class NightHeadlessRunnableFormsTests(unittest.TestCase):
    """T-00001044 — what the night TYPES must run on a host without `python` and
    pass `claude -p --allowed-tools` in headless. ZERO LLM, text shape."""

    def test_no_bare_interpreter_before_a_kit_script(self):
        for path in NIGHT_SURFACES:
            hits = _BARE_LAUNCHER.findall(path.read_text(encoding="utf-8"))
            self.assertFalse(hits, f"{path}: bare interpreter forms remain: {hits[:3]}")
            self.assertIn(_NIGHT_PY + "tasks.py list", path.read_text(encoding="utf-8"))

    def test_the_surfaces_say_pyrun_is_the_nights_form(self):
        for path in NIGHT_SURFACES:
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn(
                "La nuit appelle les scripts du kit par `bash .agents/pyrun.sh .agents/bin/<script>.py …`",
                flat, f"{path}: the launcher rule is not stated",
            )

    def test_the_closing_fence_is_one_chain_of_simple_commands(self):
        for path in NIGHT_SURFACES:
            fences = [b for b in _fenced_bodies(path.read_text(encoding="utf-8")) if "commit-stores" in b]
            self.assertEqual(len(fences), 1, f"{path}: expected ONE closing fence")
            body = fences[0].strip()
            for refused in ("case ", "esac", "$(", "tok="):
                self.assertNotIn(refused, body, f"{path}: `claude -p` refuses {refused!r} in headless")
            self.assertEqual(
                [c.strip() for c in body.split("&&")],
                [
                    _NIGHT_PY + "tasks.py commit-stores --exiger",
                    _NIGHT_PY + "tasks.py commit-run-exports --exiger",
                    "bash core-scripts/verify.sh --at HEAD --linux",
                ],
                f"{path}: the closing chain drifted",
            )

    def test_the_headless_tick_variant_is_written_and_checked(self):
        line = (
            "- les agents en vol, horodatés ; l'anti-veille est tenue par la boucle externe "
            "imprimée — ce tour ne la vérifie ni ne la ré-arme."
        )
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                any(b.strip() == line for b in _fenced_bodies(text)), f"{path}: no fenced headless tick line"
            )
            self.assertIn("--check-prompt --headless", text, f"{path}: the headless check is not named")
            # Fable 2: the sentinel's disarm instruction cites `night_keepawake.sh stop`,
            # which `--check-prompt --headless` refuses — a fenced replacement is given.
            self.assertTrue(
                any(
                    b.strip() == "Sentinelle seule en dernière ligne ; la boucle externe désarme."
                    for b in _fenced_bodies(text)
                ),
                f"{path}: no fenced headless sentinel line",
            )
            self.assertIn("NE RECOPIE PAS", text, f"{path}: the gate is not told what not to copy")

    def test_a_night_dev_checks_its_own_suite(self):
        """Pilot decision `--only` + Fable T3: the full bash run blows a turn's
        timeout, and `python` is absent — the night types these two forms."""
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("bash core-scripts/run-bash-tests.sh --only <chemin de la suite>", text, f"{path}")
            self.assertIn("bash .agents/pyrun.sh -m pytest <fichier de test>", text, f"{path}")

    def test_the_allowlist_is_built_by_a_command_not_by_prose(self):
        # Opus T4: the `tr -d '\r'` strips a CRLF gate's carriage return from every entry.
        cmd = (
            "grep -v -E '^[[:space:]]*#|^[[:space:]]*$|^max-budget-usd' "
            ".agents/state/gates/NIGHT_HEADLESS.allow | tr -d '\\r' | paste -sd, -"
        )
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(cmd, text, f"{path}: the build command is absent")
            self.assertNotIn("NIGHT_HEADLESS.allow | paste", text, f"{path}: a CRLF-blind build remains")
        sec = COMMAND.read_text(encoding="utf-8")
        sec = sec[sec.index("## `--headless`") :].split("\n## ", 1)[0]
        self.assertIn('--allowed-tools "$ALLOWED"', sec)
        self.assertNotIn("<liste issue de l'allowlist>", sec)
        self.assertIn(
            '[ -n "$ALLOWED" ] || { echo "night: allowlist vide — boucle non lancée" >&2; exit 1; }', sec
        )

    def test_the_gate_lists_the_inherited_permissions(self):
        """Pilot decision (document only): `claude -p` MERGES `.claude/settings.json`'s
        `permissions.allow` into `--allowed-tools` (measured: `gitleaks version` passes
        with `--allowed-tools "Read"`). The surfaces say so and the gate lists them."""
        listing = (
            "bash .agents/pyrun.sh -c \"import json,os;[print(f+': '+r) for f in "
            "('.claude/settings.json','.claude/settings.local.json',"
            "os.path.expanduser('~/.claude/settings.json')) if os.path.isfile(f) for p in "
            "[json.load(open(f,encoding='utf-8')).get('permissions',{})] for r in "
            "p.get('allow',[])+['defaultMode='+str(p.get('defaultMode'))]*('defaultMode' in p)]\""
        )
        for path in NIGHT_SURFACES:
            text = path.read_text(encoding="utf-8")
            flat = " ".join(text.split())
            self.assertIn(listing, text, f"{path}: the inherited-permissions listing is absent")
            self.assertIn("S'AJOUTE", flat, f"{path}")
            self.assertIn("`permissions.allow` de `.claude/settings.json`", flat, f"{path}")
            self.assertNotIn("aucune nuit headless ne pousse", flat, f"{path}: the push claim is back")
            self.assertNotIn("et de rien d'autre", flat, f"{path}: the 'nothing else' claim is back")
        # one `<file>: <rule>` line per rule, <file> EXACTLY one of the three sources (local one included)
        named = {".claude/settings.json", ".claude/settings.local.json", os.path.expanduser("~/.claude/settings.json")}
        # bound: the local source (settings.local.json) has a negative witness only on a host that carries one
        if BASH is not None:
            r = subprocess.run(
                [BASH, "-c", listing], capture_output=True, text=True, cwd=str(ROOT)
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual([x for x in r.stdout.splitlines() if x.split(": ", 1)[0] not in named], [])

    def _printed_loop(self):
        sec = COMMAND.read_text(encoding="utf-8")
        sec = sec[sec.index("## `--headless`") :].split("\n## ", 1)[0]
        return next(b for b in _fenced_bodies(sec) if "claude -p" in b)

    def test_the_printed_loop_computes_its_end_without_date_d(self):
        """Opus T1 + Fable (BLOCKING): `date -d "<cible>"` is TODAY's HH:MM on GNU
        (already past at night → 0 turn) and illegal on BSD (empty → 0 turn).
        N3 (Opus): ONE clock read — NOW, H and M of the same instant."""
        loop = self._printed_loop()
        self.assertNotIn("date -d", loop)
        self.assertIn("set -- $(date '+%s %H %M'); NOW=$1; H=${2#0}; M=${3#0}", loop)
        self.assertNotIn("date +%H", loop)
        self.assertNotIn("date +%M", loop)
        self.assertIn(
            '[ "$FIN" -gt "$NOW" ] || { echo "night: cible <cible> déjà atteinte — '
            'boucle non lancée (0 tour)" >&2; exit 1; }',
            loop,
        )
        self.assertIn(
            '[ "$RESTE" -le <D> ] || { echo "night: bloc collé après la fenêtre du gate '
            '(reste $RESTE min > <D>) — boucle non lancée" >&2; exit 1; }',
            loop,
        )
        # N2 (Opus): the anti-sleep is armed AFTER the computation, for $RESTE, before the loop.
        i_start = loop.index('night_keepawake.sh start --minutes "$RESTE"')
        self.assertLess(loop.index("RESTE="), i_start)
        self.assertLess(loop.index("FIN="), i_start)
        self.assertLess(i_start, loop.index("trap "))
        self.assertLess(loop.index("trap "), loop.index("while"))

    def _run_printed_loop(self, hh, mm, cible_min=510, d_gate=530):
        """Runs the REAL printed block with stubbed `date`/`claude`/keepawake.
        `date` answers `+%s %H %M`, `+%s`, `+%H`, `+%M` (so an older block runs
        too) and refuses anything else (BSD `-d`); each epoch read advances 3 h."""
        script = (
            self._printed_loop().replace("<cible_min>", str(cible_min)).replace("<cible>", "08:30")
            .replace("<AAAA-MM-JJ>", "2026-09-30").replace("<N>", "20").replace("<D>", str(d_gate))
        )
        d = Path(tempfile.mkdtemp())
        stubs = d / "stubs"
        stubs.mkdir()
        (stubs / "date").write_text(
            '#!/usr/bin/env bash\nC="' + str(d) + '/n"\n'
            'N=$(cat "$C" 2>/dev/null || echo 0); E=$((1000000000 + N * 10800))\n'
            'case "$1" in\n'
            '  "+%s %H %M") echo "$E ' + hh + ' ' + mm + '"; echo $((N + 1)) > "$C" ;;\n'
            '  +%s) echo "$E"; echo $((N + 1)) > "$C" ;;\n'
            '  +%H) echo ' + hh + ' ;;\n'
            '  +%M) echo ' + mm + ' ;;\n'
            '  *) echo "date: illegal option" >&2; exit 1 ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        (stubs / "claude").write_text(
            '#!/usr/bin/env bash\necho tour >> "' + str(d) + '/turns"\necho "tour ok"\n', encoding="utf-8"
        )
        for p in stubs.iterdir():
            p.chmod(0o755)
        (d / ".agents" / "bin").mkdir(parents=True)
        (d / ".agents" / "bin" / "night_keepawake.sh").write_text(
            'echo "$*" >> "' + str(d) + '/keepawake"\n', encoding="utf-8"
        )
        (d / ".agents" / "state" / "gates").mkdir(parents=True)
        (d / ".agents" / "state" / "gates" / "NIGHT_HEADLESS.allow").write_text(
            "# c\nmax-budget-usd: 1\nRead\r\nBash(date)\r\n", encoding="utf-8", newline=""
        )
        (d / ".agents" / "state" / "local" / "night").mkdir(parents=True)
        env = dict(os.environ, PATH=str(stubs) + os.pathsep + os.environ.get("PATH", ""))
        r = subprocess.run([BASH, "-c", script], cwd=str(d), capture_output=True, text=True, env=env, timeout=60)
        turns = (d / "turns").read_text().count("tour") if (d / "turns").exists() else 0
        ka = (d / "keepawake").read_text() if (d / "keepawake").exists() else ""
        return r, turns, ka

    @unittest.skipIf(BASH is None, "no bash on this box")
    def test_the_printed_loop_runs_turns_when_launched_before_midnight(self):
        """Target 08:30 launched « at 23:40 » (stubbed `date`): the loop MUST run
        turns. Red on the `date -d` form: the stub refuses `-d` like BSD → 0 turn."""
        r, turns, _ka = self._run_printed_loop("23", "40")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(turns, 0, f"0 turn launched: {r.stderr}")

    @unittest.skipIf(BASH is None, "no bash on this box")
    def test_the_printed_loop_refuses_a_block_pasted_after_the_target(self):
        """N1 (Opus): pasted at 08:31 for 08:30, `mod 1440` would make a ~24 h night.
        The `<D>` guard refuses, NAMED, with 0 turn and no anti-sleep armed."""
        r, turns, ka = self._run_printed_loop("08", "31")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(turns, 0)
        self.assertIn("bloc collé après la fenêtre du gate", r.stderr)
        self.assertNotIn("start", ka, "the anti-sleep was armed for a refused night")

    @unittest.skipIf(BASH is None, "no bash on this box")
    def test_the_printed_loop_arms_the_antisleep_for_the_real_remainder(self):
        """N2 (Opus): gate computed D=530 at 23:40, block pasted at 01:00 → 450 min
        remain; the anti-sleep is armed for 450, not for the stale 530."""
        r, turns, ka = self._run_printed_loop("01", "00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(turns, 0)
        self.assertIn("start --minutes 450", ka)
        self.assertIn("stop", ka)
