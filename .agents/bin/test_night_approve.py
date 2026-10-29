"""Tests for night_approve.py — block approval of `/night` eligibility contracts.

Style aligned with test_specs.py / test_ledger.py: temp roots (the tracked
`TASKS.json` and `SPECS.json` are NEVER touched), direct import (pytest's
default rootdir insertion puts this file's directory on sys.path).

THE SHAPE OF THIS SUITE IS THE POINT. Every one of the eligibility conditions gets a
REFUSAL case **and its twin negative control** — the same fixture with the one
broken knob repaired. A refusal alone does not distinguish "the guard works"
from "the guard refuses everything", which is the failure mode a fail-closed
tool is most likely to have and least likely to notice.

Non-vacuity is proven BY MUTATION, outside this file: neutralise
`condition_state`, `condition_plan_exists`, `condition_verdict`,
`condition_fingerprint`, `condition_roster`, `condition_draft`,
`condition_night_delivered`, `condition_pair_form` in turn and check that the matching test
reddens while the negative controls stay green (`condition_committed`: _suivi.py). The
pair-form witnesses (`PairFormTests`, `PlanPoolNamedFormTests`, T-00000673)
each NAME their own mutant in their docstring (« MUTANT <id> »), and the header
of their block lists them — a witness that does not name what turns it red is
not a witness.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

import night_approve
import specs
import tasks

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / ".agents" / "bin" / "night_approve.py"
KICKOFF = ROOT / ".claude" / "commands" / "kickoff.md"
NIGHT = ROOT / ".claude" / "commands" / "night.md"
POOL = ROOT / "core-scripts" / "plan_pool.py"

TASK = "T-00000001"
OTHER = "T-00000002"
STRANGER = "T-00000009"
PLAN_REL = "docs/tasks/LOT-X-plan.md"

TITLE_LINE = "# PLAN — LOT X : deux corrections mecaniques"
ROSTER_LINE = f"Tâches : {TASK} · {OTHER}"
BODY = (
    "Corps du plan.\n\n"
    f"{STRANGER} est cite ICI, dans le CORPS, pour dire qu'il n'est PAS traite —\n"
    "exactement la forme de LOT-3-plan.md:62 et LOT-1-plan.md:93.\n"
)


def plan_text(title: str = TITLE_LINE, roster: str | None = ROSTER_LINE, body: str = BODY) -> str:
    parts = [title, ""]
    if roster is not None:
        parts += [roster, ""]
    parts.append(body)
    return "\n".join(parts)


def default_verdict(sha: str, plan_rel: str = PLAN_REL) -> dict:
    return {
        "title": f"plan-critic CONCERNS (iteration 1/8) sur {plan_rel}",
        "text": f"critique du plan {plan_rel} sha256={sha}",
    }


class Repo:
    """A throwaway repo root carrying a board, a journal and a plan file."""

    def __init__(self, tmp: Path):
        self.root = Path(tmp)
        self.states = {TASK: "pending", OTHER: "pending"}
        self.plan_rel = PLAN_REL
        self.plan = plan_text()
        self.write_plan = True
        # A `None` sha slot = the plan's ACTUAL fingerprint, resolved at build time.
        self.verdicts: list[dict] = [{"title": None, "text": None, "sha": None}]
        self.contracts: list[tuple[str, str]] = []  # (task, text)
        # Raw (task, kind, title) entries AFTER the contracts; titles HARD-CODED, never a module
        # constant, so old code reddens on APPROVE, not on an AttributeError (T-00000847).
        self.extra: list[tuple[str, str, str]] = []

    # -- construction -----------------------------------------------------
    def plan_path(self) -> Path:
        return self.root / self.plan_rel

    def sha(self) -> str:
        import hashlib

        return hashlib.sha256(self.plan.encode("utf-8")).hexdigest()

    def build(self) -> "Repo":
        if self.write_plan:
            path = self.plan_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.plan.encode("utf-8"))

        board = {
            "next_id": 100,
            "tasks": [
                {"id": tid, "state": state, "task": f"tache {tid}"}
                for tid, state in self.states.items()
            ],
        }
        bpath = tasks.store_path(self.root)
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(json.dumps(board), encoding="utf-8")

        entries = []
        n = 0
        actual = self.sha()
        for v in self.verdicts:
            n += 1
            sha = v.get("sha") or actual
            entries.append(
                {
                    "id": f"S-{n:08d}",
                    # Optional per-verdict `task` (T-00000673: a pair is attached
                    # to a task by its key); the default is unchanged.
                    "task": v.get("task") or TASK,
                    "kind": "verdict",
                    "title": v.get("title") or default_verdict(sha, self.plan_rel)["title"],
                    "text": v.get("text") or default_verdict(sha, self.plan_rel)["text"],
                    "files": [],
                    "date": "2026-08-19",
                }
            )
        for task_id, text in self.contracts:
            n += 1
            entries.append(
                {
                    "id": f"S-{n:08d}",
                    "task": task_id,
                    "kind": "decision",
                    "title": night_approve.CONTRACT_TITLE,
                    "text": text,
                    "files": [],
                    "date": "2026-08-19",
                }
            )
        for task_id, kind, title in self.extra:
            n += 1
            entries.append(
                {
                    "id": f"S-{n:08d}",
                    "task": task_id,
                    "kind": kind,
                    "title": title,
                    "text": "livre @ abc..def ; fichiers x.py",
                    "files": [],
                    "date": "2026-09-30",
                }
            )
        jpath = specs.store_path(self.root)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps({"next_id": n + 1, "entries": entries}), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}  # condition 8 : COMMITTED (C2, :1842)
        for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "--allow-empty", "-m", "chore: banc")):
            subprocess.run(["git", "-C", str(self.root), "-c", "user.name=banc", "-c", "user.email=banc@local",
                            "-c", "commit.gpgsign=false", *args], capture_output=True, env=env, check=True)
        return self

    # -- exercise ---------------------------------------------------------
    def lot(self, *task_ids: str) -> night_approve.Lot:
        return night_approve.Lot(plan=self.plan_rel, tasks=list(task_ids) or [TASK])

    def run(self, *task_ids: str, apply: bool = False):
        return night_approve.run(
            self.root, [self.lot(*task_ids)], apply=apply, approved_on="2026-08-19"
        )

    def outcome(self, *task_ids: str, apply: bool = False) -> night_approve.TaskOutcome:
        return self.run(*task_ids, apply=apply)[0].outcomes[0]

    def journal(self) -> list[dict]:
        return specs.load(self.root)["entries"]

    def contracts_for(self, task_id: str) -> list[dict]:
        return night_approve.existing_contracts(self.journal(), task_id)


# --- LE BROUILLON N'ENTRE PAS EN NUIT — condition 6 -------------------------
#
# CES DEUX TESTS ÉTAIENT INERTES, et c'est la revue de clôture du 2026-09-12 qui
# l'a montré. Le premier posait `verdicts = []` : il passait donc parce
# qu'AUCUN verdict n'existait — condition 3 — et le marqueur `STATUS:` n'y jouait
# aucun rôle. Le second posait un `NO_GO` : il passait sur le STATUT du verdict,
# toujours pas sur le marqueur. Le témoin décisif est qu'un plan SANS marqueur et
# sans verdict rend exactement le même refus, mot pour mot.
#
# Ils sont donc réécrits sur le seul montage qui isole la condition : un verdict
# `GO`, présent et concordant, et le marqueur pour seule différence. Sous cette
# forme ils ROUGISSENT sur le code d'avant — mesuré : `APPROVE`.

def test_in_progress_is_not_eligible():
    """Un plan interrompu AVANT la fin de la critique n'entre pas en nuit.

    LA FENÊTRE EST RÉELLE : `plan-critic` rend `GO`, le verdict est tracé, et le
    planner est interrompu avant de réécrire le plan sans son marqueur. Le
    fichier reste `IN_PROGRESS`, son empreinte concorde donc avec celle du
    verdict, et les cinq conditions d'origine sont TOUTES satisfaites.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.plan = plan_text(body="STATUS: IN_PROGRESS\nREVISION: 1\n")
        repo.verdicts = [
            {"title": f"plan-critic GO (iteration 1/8) sur {PLAN_REL}"}
        ]
        repo.build()

        outcome = repo.outcome()

    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 6" in outcome.reason, outcome.reason
    assert "IN_PROGRESS" in outcome.reason, outcome.reason


def test_critic_rejected_is_not_eligible():
    """Une révision REFUSÉE par le critic n'entre pas davantage, même si un
    verdict `GO` plus ancien traîne encore au journal."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.plan = plan_text(body="STATUS: CRITIC_REJECTED\nREVISION: 1\n")
        repo.verdicts = [
            {"title": f"plan-critic GO (iteration 1/8) sur {PLAN_REL}"}
        ]
        repo.build()

        outcome = repo.outcome()

    assert outcome.decision == night_approve.SKIP, outcome.reason
    assert "condition 6" in outcome.reason, outcome.reason
    assert "CRITIC_REJECTED" in outcome.reason, outcome.reason


def test_le_marqueur_est_lu_sous_ses_formes_ORNEES():
    """CONTRÔLE DE NON-VACUITÉ DE L'ANALYSEUR. Un `startswith("STATUS:")` strict
    laisserait passer toutes ces formes, et un marqueur manqué ne se voit pas —
    il se lit « plan fini ». Ce dépôt écrit ses plans à la main et en français,
    donc ces formes sont plausibles, pas exotiques."""
    for corps in (
        "**STATUS:** IN_PROGRESS\n",
        "  STATUS: IN_PROGRESS\n",
        "STATUS : IN_PROGRESS\n",
        "STATUS: in_progress\n",
        "STATUS: IN_PROGRESS (revision 2)\n",
        "# STATUS: CRITIC_REJECTED\n",
        "STATUS: DONE\nSTATUS: IN_PROGRESS\n",  # empile : le plus recent compte
    ):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = Repo(Path(tmp))
            repo.plan = plan_text(body=corps)
            repo.verdicts = [
                {"title": f"plan-critic GO (iteration 1/8) sur {PLAN_REL}"}
            ]
            repo.build()
            outcome = repo.outcome()
        assert outcome.decision == night_approve.SKIP, f"{corps!r} -> {outcome.reason}"
        assert "condition 6" in outcome.reason, f"{corps!r} -> {outcome.reason}"


def test_un_STATUS_qui_n_est_PAS_un_brouillon_laisse_passer():
    """L'AUTRE SENS, sans quoi la condition 6 refuserait tout plan portant une
    ligne `STATUS` quelconque et serait désarmée le jour où elle gênerait."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.plan = plan_text(body="STATUS: FINAL\nREVISION: 2\n")
        repo.verdicts = [
            {"title": f"plan-critic GO (iteration 2/8) sur {PLAN_REL}"}
        ]
        repo.build()

        outcome = repo.outcome()

    assert outcome.decision == night_approve.APPROVE, outcome.reason


def test_final_verdict_remains_eligible():
    """Removing the draft marker and recording GO preserves the green arm."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Repo(Path(tmp))
        repo.plan = plan_text(body="REVISION: 2\nPlan final.\n")
        repo.verdicts = [
            {"title": f"plan-critic GO (iteration 2/8) sur {PLAN_REL}"}
        ]
        repo.build()

        outcome = repo.outcome()

    assert outcome.decision == night_approve.APPROVE, outcome.reason


class AnchoredVerdictGrammarTests(unittest.TestCase):
    """The verdict is READ from an anchored grammar, never FOUND in the prose
    (T-00000345)."""

    def test_a_negative_sentence_no_longer_reads_permissive(self):
        """THE FAIL-OPEN THIS CLOSES, in one line: a REFUSED plan made eligible
        for unattended overnight execution by the very word it used to refuse."""
        self.assertIsNone(night_approve.verdict_status("plan-critic : refus, pas de GO"))
        self.assertIsNone(night_approve.verdict_status("plan-critic: aucun GO possible"))

    def test_fail_closed_outside_the_grammar_means_INELIGIBLE_not_approved(self):
        """None must not be eligible, or the fail-closed is a fail-open wearing
        its name."""
        self.assertNotIn(None, night_approve.ELIGIBLE_STATUSES)

    def test_the_real_corpus_shapes_still_parse(self):
        """NON-VACUITY, and the guard against over-tightening: the grammar was
        DERIVED from the real corpus, and a first version that omitted the
        optional ITERATION MARKER sent five genuine CONCERNS titles to None.
        These shapes are taken verbatim from SPECS.json.
        """
        cases = {
            "plan-critic CONCERNS 0 bloquant (iteration 3/8)": "CONCERNS",
            "plan-critic CONCERNS (iteration 3/8) - 0 bloquant": "CONCERNS",
            "plan-critic it.2: CONCERNS (0 bloquant)": "CONCERNS",
            "plan-critic iteration 2: CONCERNS (0 bloquant)": "CONCERNS",
            "plan-critic CONCERNS 1/8 - 0 bloquant": "CONCERNS",
            "plan-critic FAIL (iteration 1/8)": "FAIL",
            "plan-critic GO_AVEC_RESERVES (iteration 1/8)": "GO_AVEC_RESERVES",
            "plan-critic NO_GO": "NO_GO",
        }
        for title, expected in cases.items():
            self.assertEqual(night_approve.verdict_status(title), expected, title)

    def test_another_agents_verdict_is_not_read_as_a_plan_critic_one(self):
        """The prefix anchor, replayed: `design-review GO` and the security gate
        both write `GO` into the same journal."""
        for title in ("design-review GO", "security-code-review GO", "exec-critic GO"):
            self.assertIsNone(night_approve.verdict_status(title), title)

    def test_negative_control_the_grammar_is_not_refusing_everything(self):
        """A grammar that returned None for every input would satisfy every
        assertion above (L-00000232). Name inputs that MUST parse."""
        parsed = [t for t in (
            "plan-critic GO", "plan-critic PASS", "plan-critic NO_GO",
            "plan-critic CONCERNS", "plan-critic FAIL",
        ) if night_approve.verdict_status(t) is not None]
        self.assertEqual(len(parsed), 5, "the grammar refuses inputs it must accept")


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self._tmp.name))

    def tearDown(self):
        # Windows: temp teardown can fail on handles still held (antivirus,
        # git). Never let an assertion depend on cleanup having succeeded.
        try:
            self._tmp.cleanup()
        except OSError:
            pass

    def assertApproved(self, outcome, msg=""):
        self.assertEqual(
            outcome.decision, night_approve.APPROVE, f"{msg} (raison: {outcome.reason})"
        )

    def assertSkipped(self, outcome, condition, msg=""):
        self.assertEqual(outcome.decision, night_approve.SKIP, msg)
        self.assertIn(condition, outcome.reason, f"{msg}: refus impute a la mauvaise condition")


# ---------------------------------------------------------------------------
# Roster extraction — the mechanism condition 5 rests on
# ---------------------------------------------------------------------------


class RosterExtractionTests(unittest.TestCase):
    def test_only_line_1_and_the_first_tache_line_are_read(self):
        text = plan_text()
        places = [(r.source, r.lineno) for r in night_approve.roster_lines(text)]
        self.assertEqual(places, [("titre", 1), ("roster", 3)])

    def test_a_second_roster_line_is_not_read(self):
        text = (
            "# PLAN — LOT Y\n\nTâches : T-00000001\n\ncorps\n\nTâches : T-00000009\n"
        )
        self.assertIsNotNone(night_approve.enrolling_line(text, "T-00000001"))
        self.assertIsNone(
            night_approve.enrolling_line(text, "T-00000009"),
            "une seconde ligne roster elargirait l'appariement sans que personne l'ait voulu",
        )

    def test_separator_is_never_split_on(self):
        """`LOT-8A-plan.md:1` separates by COMMAS, the others by `·`. A parser
        assuming a separator breaks on one of the two; the pattern does not."""
        commas = "# PLAN — LOT 8A : quatre corrections (T-00000001, T-00000002, T-00000003)\n"
        middots = "# PLAN — LOT 1 : pins (T-00000001 · T-00000002 · T-00000003)\n"
        for text in (commas, middots):
            for tid in ("T-00000001", "T-00000002", "T-00000003"):
                self.assertIsNotNone(
                    night_approve.enrolling_line(text, tid), f"{tid} absent de {text!r}"
                )

    def test_a_body_mention_does_not_enrol(self):
        """The exact shape this repo's own plans carry: an id cited in the BODY
        precisely to say it is NOT treated."""
        self.assertIsNone(night_approve.enrolling_line(plan_text(), STRANGER))
        self.assertIn(STRANGER, plan_text(), "le controle serait vide si l'id n'y etait pas")

    def test_a_longer_digit_run_does_not_enrol(self):
        """`findall` returns the longest match it can START, never the whole
        token: an unanchored `T-\\d{8}` truncates a 9-digit run and hands back
        `T-00000209` for a plan that only ever wrote `T-000002099`. That is a
        false positive INSIDE the authorised line — the exact inverse of what
        condition 5 exists to guarantee."""
        text = "Titre libre\n\nTâches : T-000002099\n\ncorps\n"
        self.assertIsNone(
            night_approve.enrolling_line(text, "T-00000209"),
            "un jeton a 9 chiffres qui CONTIENT l'id en prefixe ne le nomme pas",
        )

    def test_control_the_exact_eight_digit_run_still_enrols(self):
        """The twin of the test above: bounding the pattern must not cost the
        ordinary match it exists for."""
        text = "Titre libre\n\nTâches : T-00000209\n\ncorps\n"
        line = night_approve.enrolling_line(text, "T-00000209")
        self.assertIsNotNone(line, "la suite exacte de 8 chiffres doit toujours enroler")
        self.assertEqual((line.source, line.lineno), ("roster", 3))

    def test_a_plan_with_no_roster_line_still_matches_by_title(self):
        text = "# PLAN — LOT 6 : chaine (T-00000001) + unification (T-00000002)\n\ncorps\n"
        self.assertEqual(night_approve.enrolling_line(text, TASK).source, "titre")


# ---------------------------------------------------------------------------
# Condition 1 — the task is `pending`
# ---------------------------------------------------------------------------


class Condition1Tests(RepoCase):
    def test_refuses_done_running_blocked(self):
        for state in ("done", "running", "blocked"):
            with self.subTest(state=state):
                self.repo.states = {TASK: state, OTHER: "pending"}
                self.repo.build()
                self.assertSkipped(self.repo.outcome(), "condition 1", state)
                self.assertIn(state, self.repo.outcome().reason)

    def test_refuses_a_task_absent_from_the_board(self):
        self.repo.states = {OTHER: "pending"}
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 1")
        self.assertIn("inconnue", self.repo.outcome().reason)

    def test_control_a_pending_task_is_approvable(self):
        """Twin control: the SAME fixture with the one broken knob repaired."""
        self.repo.states = {TASK: "pending", OTHER: "pending"}
        self.repo.build()
        self.assertApproved(self.repo.outcome())


# ---------------------------------------------------------------------------
# Condition 2 — the plan file exists
# ---------------------------------------------------------------------------


class Condition2Tests(RepoCase):
    def test_refuses_an_absent_plan(self):
        self.repo.write_plan = False
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 2")

    def test_control_a_present_plan_is_approvable(self):
        self.repo.write_plan = True
        self.repo.build()
        self.assertApproved(self.repo.outcome())


# ---------------------------------------------------------------------------
# Condition 3 — a PASS/CONCERNS plan-critic verdict cites this plan
# ---------------------------------------------------------------------------


class Condition3Tests(RepoCase):
    def test_refuses_when_no_verdict_cites_the_plan(self):
        self.repo.verdicts = [
            {
                "title": "plan-critic PASS (iteration 1/8) sur docs/tasks/AUTRE-plan.md",
                "text": "critique du plan docs/tasks/AUTRE-plan.md sha256=" + "0" * 64,
                "sha": "0" * 64,
            }
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")

    def test_refuses_when_the_latest_verdict_is_fail(self):
        self.repo.verdicts = [
            {"title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}"},
            {"title": f"plan-critic FAIL (iteration 2/8) sur {PLAN_REL}"},
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")
        self.assertIn("FAIL", self.repo.outcome().reason)

    def test_refuses_a_verdict_whose_title_carries_no_readable_status(self):
        self.repo.verdicts = [{"title": f"plan-critic relu sur {PLAN_REL}"}]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")

    def test_control_concerns_is_approvable(self):
        self.repo.verdicts = [{"title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}"}]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_control_pass_is_approvable(self):
        self.repo.verdicts = [{"title": f"plan-critic PASS (iteration 5/8) sur {PLAN_REL}"}]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_control_a_concerns_AFTER_a_fail_is_approvable(self):
        """The most recent verdict prevails — in BOTH directions, or the rule
        would just be 'any FAIL anywhere disqualifies', which is a different
        rule that happens to pass the refusal test above."""
        self.repo.verdicts = [
            {"title": f"plan-critic FAIL (iteration 1/8) sur {PLAN_REL}"},
            {"title": f"plan-critic CONCERNS (iteration 2/8) sur {PLAN_REL}"},
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.assertEqual(self.repo.run()[0].verdict_id, "S-00000002")

    # -- new vocabulary (GO / GO_AVEC_RESERVES / NO_GO), double-read with the
    # historic PASS / CONCERNS / FAIL kept eligible (brief §1.2, §H) ---------

    def test_control_go_is_approvable(self):
        self.repo.verdicts = [{"title": f"plan-critic GO (iteration 1/2) sur {PLAN_REL}"}]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_control_go_avec_reserves_is_approvable(self):
        """GO_AVEC_RESERVES is eligible AND is not misread as the bare GO — the
        conservative-first probe order means `\\bGO\\b` never bites first."""
        self.repo.verdicts = [
            {"title": f"plan-critic GO_AVEC_RESERVES (iteration 1/2) sur {PLAN_REL}"}
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.assertEqual(self.repo.run()[0].verdict_status, "GO_AVEC_RESERVES")

    def test_refuses_when_the_latest_verdict_is_no_go(self):
        self.repo.verdicts = [
            {"title": f"plan-critic GO_AVEC_RESERVES (iteration 1/2) sur {PLAN_REL}"},
            {"title": f"plan-critic NO_GO (iteration 2/2) sur {PLAN_REL}"},
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")
        self.assertIn("NO_GO", self.repo.outcome().reason)

    def test_a_title_carrying_both_no_go_and_go_reads_no_go(self):
        """A mixed title reads as the conservative token — the pin of the probe
        ORDER (C8 / L-00000143): a decision on structure AND order, never on a
        fragment found somewhere in the string."""
        self.repo.verdicts = [
            {"title": f"plan-critic NO_GO puis GO (iteration 2/2) sur {PLAN_REL}"}
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")
        self.assertIn("NO_GO", self.repo.outcome().reason)

    def test_control_a_go_AFTER_a_fail_is_approvable(self):
        """Cross-vocabulary: the most recent verdict prevails across the two
        vocabularies — a new-vocab GO after a historic FAIL is eligible."""
        self.repo.verdicts = [
            {"title": f"plan-critic FAIL (iteration 1/8) sur {PLAN_REL}"},
            {"title": f"plan-critic GO (iteration 2/2) sur {PLAN_REL}"},
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.assertEqual(self.repo.run()[0].verdict_id, "S-00000002")

    def test_a_title_writing_no_dash_go_never_reads_go(self):
        """« NO-GO » and « NO GO » are ordinary prose in a bilingual repo; a bare
        `\\bGO\\b` read them GO (fail-open toward night eligibility, worse than
        today's fail-closed None). The separator-variant NO_GO probe runs BEFORE
        any GO probe (C2 it.1), so both spellings read NO_GO and never eligible."""
        for spelling in ("NO-GO", "NO GO"):
            self.repo.verdicts = [
                {"title": f"plan-critic {spelling} (iteration 2/2) sur {PLAN_REL}"}
            ]
            self.repo.build()
            outcome = self.repo.outcome()
            self.assertSkipped(outcome, "condition 3", msg=spelling)
            self.assertIn("NO_GO", outcome.reason, msg=spelling)

    # -- HIGH-1 (T-00000323) : l'énumération de séparateurs était un fail-open
    # d'AUTORISATION. Le nom porte la borne (L-00000190) : ce test ne peut pas
    # passer sans exercer les onze orthographes, U+2014/U+2013/U+2011 comprises.
    ELEVEN_REFUSALS = (
        ("NO_GO", "underscore (pin historique)"),
        ("NO-GO", "trait d'union ASCII (pin historique)"),
        ("NO GO", "espace (pin historique)"),
        ("NO—GO", "U+2014 tiret cadratin"),
        ("NO–GO", "U+2013 tiret demi-cadratin"),
        ("NO‑GO", "U+2011 trait d'union insecable"),
        ("NO/GO", "barre oblique"),
        ("NO.GO", "point"),
        ("NOGO", "aucun separateur"),
        ("NON GO", "francais, espace"),
        ("NON-GO", "francais, trait d'union"),
    )

    FIVE_ELIGIBLES = ("GO", "GO_AVEC_RESERVES", "GO AVEC RÉSERVES", "PASS", "CONCERNS")

    def test_eleven_refusal_spellings_incl_U2014_U2013_U2011_slash_dot_and_french_NON_never_read_go(
        self,
    ):
        """MESURÉ AVANT correction : sept de ces onze orthographes rendaient
        `decision='approve'` sur un plan dont le dernier verdict est un REFUS —
        un plan refusé par le plan-critic devenait éligible à l'exécution
        autonome de nuit, sans humain. La cause n'était pas un séparateur oublié
        mais l'ÉNUMÉRATION elle-même (`[\\s_-]*`), qui fait tomber tout autre
        séparateur sur la sonde `\\bGO\\b` (L-00000187). La classe est désormais
        fermée sur « ni lettre ni chiffre », bornée à 3 caractères."""
        for spelling, quoi in self.ELEVEN_REFUSALS:
            with self.subTest(spelling=spelling, forme=quoi):
                self.repo.verdicts = [
                    {"title": f"plan-critic {spelling} (iteration 2/2) sur {PLAN_REL}"}
                ]
                self.repo.build()
                outcome = self.repo.outcome()
                self.assertSkipped(outcome, "condition 3", msg=quoi)
                self.assertIn("NO_GO", outcome.reason, msg=quoi)

    def test_control_the_five_eligible_spellings_survive_the_widened_NO_GO_probe(self):
        """Le jumeau négatif, sans lequel le test précédent ne distingue pas
        « la sonde marche » de « la sonde refuse tout » : les cinq orthographes
        éligibles restent approuvées ET gardent leur ÉTIQUETTE."""
        expected = {
            "GO": "GO",
            "GO_AVEC_RESERVES": "GO_AVEC_RESERVES",
            "GO AVEC RÉSERVES": "GO_AVEC_RESERVES",
            "PASS": "PASS",
            "CONCERNS": "CONCERNS",
        }
        for spelling in self.FIVE_ELIGIBLES:
            with self.subTest(spelling=spelling):
                self.repo.verdicts = [
                    {"title": f"plan-critic {spelling} (iteration 1/2) sur {PLAN_REL}"}
                ]
                self.repo.build()
                self.assertApproved(self.repo.outcome(), msg=spelling)
                self.assertEqual(
                    self.repo.run()[0].verdict_status, expected[spelling], msg=spelling
                )

    def test_go_avec_reserves_in_NFD_decomposed_form_still_reads_go_avec_reserves(self):
        """« RÉSERVES » saisi en forme DÉCOMPOSÉE (E + U+0301) ne matchait pas
        `R[EÉ]SERVES` et retombait sur `\\bGO\\b` : même éligibilité, mais une
        étiquette fausse dans le rapport que lit le pilote. NFC avant la sonde.
        Le contrôle `assertNotEqual` sur les octets est ce qui empêche ce test
        de devenir vert par recomposition accidentelle de la source."""
        decomposed = unicodedata.normalize("NFD", "GO AVEC RÉSERVES")
        self.assertNotEqual(decomposed, "GO AVEC RÉSERVES", "le cas NFD n'est pas exercé")
        self.repo.verdicts = [
            {"title": f"plan-critic {decomposed} (iteration 1/2) sur {PLAN_REL}"}
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.assertEqual(self.repo.run()[0].verdict_status, "GO_AVEC_RESERVES")

    # -- HIGH-2 (T-00000323) : `kind=verdict` ne dit rien de l'AUTEUR ---------

    def test_a_verdict_from_ANOTHER_agent_never_overrides_the_plan_critic_NO_GO(self):
        """MESURÉ AVANT correction : `plan-critic NO_GO` puis `design-review GO`
        citant le même plan rendait `decision='approve'`. `GO` est le mot de
        `design-review` ET du gate sécurité, qui écrivent dans le même journal ;
        seul le plan-critic fait autorité sur l'éligibilité nuit. L'assertion
        sur `verdict_id` est la charge : elle pin que le verdict RETENU est
        celui du plan-critic, pas le plus récent tous auteurs confondus."""
        self.repo.verdicts = [
            {"title": f"plan-critic NO_GO (iteration 2/2) sur {PLAN_REL}"},
            {"title": f"design-review GO — 0 blocker sur {PLAN_REL}"},
        ]
        self.repo.build()
        outcome = self.repo.outcome()
        self.assertSkipped(outcome, "condition 3")
        self.assertIn("NO_GO", outcome.reason)
        self.assertEqual(self.repo.run()[0].verdict_id, "S-00000001")

    def test_control_a_later_verdict_from_another_agent_does_not_disqualify_an_eligible_plan(self):
        """Le jumeau, dans l'autre sens : le filtre n'est pas « tout refuser ».
        Un `GO_AVEC_RESERVES` du plan-critic reste éligible même suivi d'un
        verdict d'un autre agent — et c'est bien le verdict du plan-critic qui
        est retenu."""
        self.repo.verdicts = [
            {"title": f"plan-critic GO_AVEC_RESERVES (iteration 1/2) sur {PLAN_REL}"},
            {"title": f"security-code-review NO_GO sur {PLAN_REL}"},
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.assertEqual(self.repo.run()[0].verdict_id, "S-00000001")

    def test_a_plan_cited_ONLY_by_a_non_plan_critic_verdict_has_no_authoritative_verdict(self):
        """Résidu mesuré : un titre d'un autre agent portant « LOT GO-live » se
        lisait `GO` et suffisait à l'éligibilité. Aucun verdict plan-critic ne
        cite ce plan — le refus doit le DIRE, pas inventer un statut."""
        self.repo.verdicts = [{"title": f"documenter LOT GO-live sur {PLAN_REL}"}]
        self.repo.build()
        outcome = self.repo.outcome()
        self.assertSkipped(outcome, "condition 3")
        self.assertIn("aucun verdict plan-critic", outcome.reason)

    def test_a_prefix_extension_plan_critic_lite_is_not_the_plan_critic(self):
        """La frontière est `(?![\\w-])` et non `\\b` : le nom contient déjà un
        tiret, donc `\\b` admettrait l'EXTENSION DE PRÉFIXE `plan-critic-<autre>`
        — le « ce qui ressemble est admis » de L-00000143, mesuré trois fois
        ailleurs dans ce dépôt."""
        self.repo.verdicts = [{"title": f"plan-critic-lite GO sur {PLAN_REL}"}]
        self.repo.build()
        outcome = self.repo.outcome()
        self.assertSkipped(outcome, "condition 3")
        self.assertIn("aucun verdict plan-critic", outcome.reason)

    def test_control_the_agent_anchor_tolerates_case_leading_space_and_a_colon(self):
        """L'ancrage ne doit pas devenir plus strict que les titres RÉELS du
        journal : 170 des 258 verdicts de ce dépôt sont des titres plan-critic,
        et ils varient en casse, en espace de tête et en ponctuation."""
        for title in (
            f"PLAN-CRITIC GO (iteration 1/2) sur {PLAN_REL}",
            f"  plan-critic GO (iteration 1/2) sur {PLAN_REL}",
            f"plan-critic: GO (iteration 1/2) sur {PLAN_REL}",
        ):
            with self.subTest(title=title):
                self.repo.verdicts = [{"title": title}]
                self.repo.build()
                self.assertApproved(self.repo.outcome(), msg=title)

    def test_a_sentence_final_dot_still_cites(self):
        """A verdict whose TEXT cites the plan followed by a SENTENCE-ENDING dot
        (`…LOT-X-plan.md.`) must still count as citing the plan. Before the fix
        the right-boundary of `MD_PATH` refused the final `.`, `findall` came
        back empty, and condition 3 dropped an eligible task.

        The citation lives in the TEXT, not the title, ON PURPOSE (C1): the
        fixture backfills a CLEAN default `text` that cites the path WITHOUT a
        dot, so leaving `text` to default — or moving the dotted path into the
        title, which condition 3 never reads — would make this case green BEFORE
        the fix and prove nothing. So the text is set explicitly, and it is the
        ONLY place the plan is cited, with the trailing dot."""
        sha = self.repo.sha()
        self.repo.verdicts = [
            {
                "title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}",
                "text": f"critique du plan {PLAN_REL}. sha256={sha}",
                "sha": sha,
            }
        ]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_a_path_continuing_past_md_still_does_not_cite(self):
        """The twin the fix must NOT cost: a token that CONTINUES past `.md`
        (`…LOT-X-plan.md.bak`) is a different path and does not cite this plan.
        Before the fix this was guaranteed by the boundary alone; the second
        lookahead keeps it closed after the fix, and this test PINS it in code
        rather than in prose. Green both before and after."""
        sha = self.repo.sha()
        self.repo.verdicts = [
            {
                "title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}",
                "text": f"critique du plan {PLAN_REL}.bak sha256={sha}",
                "sha": sha,
            }
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 3")


# ---------------------------------------------------------------------------
# Condition 3, FORME PAIRE NOMMÉE (T-00000673)
#
# CE QUE CE BLOC ÉPINGLE. La sonde de paire est une EXPLICATION : elle refuse et
# elle nomme, elle n'autorise JAMAIS, elle ne lit JAMAIS un statut, et elle associe
# par la CLÉ DE TÂCHE seule (`_same_task`, numérique), jamais par un chemin cité.
#
# MUTANTS — chacun rougit AU MOINS les témoins qui le nomment ; un rouge de plus
# est une ligne de SUR-REFUS, relevée par la preuve de mutation, jamais un échec :
#   MP1  `condition_pair_form` neutralisée (rend None)
#   MP2  l'association est abandonnée (toute paire du journal compte)
#   MP3  une patte « chemin cité » s'ajoute à la clé de tâche
#   MP4  la patte « clé de tâche » est abandonnée (chemin seul)
#   MP5  la clé est comparée en chaîne (`==`) au lieu de `_same_task`
#   MP6  la règle « paire plus récente » est retirée (seul verdict None nommé)
#   MP7  la comparaison est inversée (`<` au lieu de `>`)
#   MP8  la règle lit un STATUT (ne refuse qu'une paire NO_GO)
#   MP9  le filtre `not is_plan_critic_verdict` est retiré
#   MP10 le filtre `kind=verdict` est retiré (N1 de la critique B)
#   MP11 la paire la plus ANCIENNE est gardée (`min` au lieu de `max`, N2)
#   MP12 la sonde passe AVANT les conditions 1 et 2 (N9)
#   MP13 `PAIR_VERDICT_TITLE` perd ses bornes de mot (N5)
#   MP14 la borne d'affichage du titre est élargie ou rétrécie (N3)
#   MP15 la garde d'enrôlement est retirée : la sonde masque la condition 5 (F2, critique A)
#   MP16 l'assainisseur `_titre_affichable` est retiré, ou court-circuité au site (S-00003335)
#   MP17 `ITERATION_VERDICT_TITLE` ignoré : l'itération du critique UNIQUE ne refuse plus (S-00003871)
# ---------------------------------------------------------------------------

PAIR_GAR ="T-00000001 itération 3/8 : paire GO_AVEC_RESERVES (A GAR 0 bloquant / B GAR 0 bloquant)"
PAIR_NO_GO = "T-00000001 itération 4/8 : paire NO_GO (A GAR / B NO_GO 1 bloquant)"


class PairFormTests(RepoCase):
    def cites(self):
        return f"plan={PLAN_REL} sha256={self.repo.sha()}"

    def final(self, title="plan-critic GO"):
        return {"title": title, "text": self.cites()}

    def reason(self, *tasks):
        self.repo.build()
        return self.repo.outcome(*tasks)

    def append_entry(self, **entry):
        """Le journal AJOUTÉ après `Repo.build` — une entrée à la fois, à la suite,
        `kind=verdict` par défaut. Jamais un second montage."""
        j = specs.load(self.repo.root)
        n = len(j["entries"]) + 1
        e = {"id": f"S-{n:08d}", "files": [], "date": "2026-09-30", "kind": "verdict", "text": ""}
        e.update(entry)
        j["entries"].append(e)
        j["next_id"] = n + 1
        specs.store_path(self.repo.root).write_text(json.dumps(j), encoding="utf-8")

    # -- le verdict de paire SEUL : refuse, nomme, n'autorise jamais -------------------
    def test_a_pair_alone_is_skipped_and_named(self):
        """MUTANT MP1 (condition_pair_form -> None) : le refus retombe sur le message
        générique, « forme PAIRE » disparaît."""
        self.repo.verdicts = [{"title": PAIR_GAR, "text": self.cites()}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("aucun verdict plan-critic", o.reason)  # sous-chaîne d'origine conservée
        self.assertIn("forme PAIRE", o.reason)
        self.assertIn("S-00000001", o.reason)
        self.assertIn("plan-critic <VERDICT>", o.reason)

    def test_control_the_same_content_titled_plan_critic_is_approvable(self):
        """Le jumeau : même texte, titre « plan-critic GO_AVEC_RESERVES » -> APPROVE. Sans
        lui « la paire est refusée » ne se distingue pas de « tout est refusé »."""
        self.repo.verdicts = [self.final("plan-critic GO_AVEC_RESERVES")]
        self.assertApproved(self.reason())

    def test_a_pair_without_any_path_in_its_text_is_still_named(self):
        """MUTANT MP4 (patte « clé de tâche » abandonnée) : 106 des 222 paires vivantes ne
        citent AUCUN chemin .md, une sonde par chemin seul ne les voit pas."""
        self.repo.verdicts = [{"title": PAIR_GAR, "text": "A = entrée précédente ; 19 réserves appliquées."}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("forme PAIRE", o.reason)

    def test_a_short_form_task_key_is_the_same_task(self):
        """MUTANT MP5 (comparaison `==` sur la chaîne) : `specs.py add` enregistre l'id TEL
        QUE TAPÉ, `T-1` et `T-00000001` sont une seule tâche (`_same_task`)."""
        self.repo.verdicts = [{"title": PAIR_GAR, "text": "x", "task": "T-1"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("forme PAIRE", o.reason)

    def test_the_title_is_shown_whole_up_to_its_bound_and_cut_after(self):
        """MUTANT MP14 (borne `[:80]` élargie à 800, ou rétrécie à 5) : le titre d'une paire
        est de la prose libre, il est montré BORNÉ — assez pour le reconnaître, jamais en
        entier."""
        title = "T-00000001 itération 1/8 : paire GO_AVEC_RESERVES — " + "y" * 70 + " QUEUE-HORS-BORNE"
        self.repo.verdicts = [{"title": title, "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("« T-00000001 itération 1/8 : paire GO_AVEC_RESERVES", o.reason)
        self.assertNotIn("QUEUE-HORS-BORNE", o.reason)

    # -- la paire PLUS RÉCENTE que le dernier verdict plan-critic : refuse, quel que soit son statut
    def test_a_newer_pair_refuses_a_plan_critic_go_and_names_both_ids(self):
        """MUTANT MP6 (règle retirée) : APPROVE. MUTANT MP7 (`<`) : APPROVE aussi."""
        self.repo.verdicts = [self.final(), {"title": PAIR_NO_GO, "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("S-00000001", o.reason)
        self.assertIn("S-00000002", o.reason)
        self.assertIn("verdict FINAL", o.reason)

    def test_a_newer_FAVOURABLE_pair_refuses_too_the_rule_reads_no_status(self):
        """MUTANT MP8 (la règle ne refuse qu'une paire NO_GO). Une paire GAR après le final
        dit que l'itération a REPRIS : le final ne décrit plus l'état critiqué. Le titre
        d'une paire est de la prose libre : le lire pour AUTORISER est la classe fermée par
        T-00000345, le lire pour refuser reste le même pari."""
        self.repo.verdicts = [self.final("plan-critic GO_AVEC_RESERVES"), {"title": PAIR_GAR, "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("S-00000002", o.reason)

    def test_the_NEWEST_pair_is_the_one_compared(self):
        """MUTANT MP11 (`min` au lieu de `max`) : paire, PUIS final, PUIS paire — la paire
        la plus ancienne précède le final et ne refuserait rien ; c'est la plus récente
        qui dit que l'itération a repris. Une paire seule ne distingue pas `min` de `max`."""
        self.repo.verdicts = [{"title": PAIR_NO_GO, "text": "x"}, self.final(), {"title": PAIR_GAR, "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("S-00000003", o.reason)
        self.assertNotIn("S-00000001", o.reason)

    def test_a_newer_SINGLE_CRITIC_iteration_refuses_like_a_pair(self):
        """MUTANT MP17 (titre d'itération du critique UNIQUE ignoré, S-00003871) : « T-… itération 2/8 :
        plan-critic NO_GO » APRÈS le final dit que l'itération a repris, comme une paire."""
        self.repo.verdicts = [self.final(), {"title": "T-00000001 itération 2/8 : plan-critic NO_GO", "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("S-00000002", o.reason)

    def test_control_the_NOMINAL_order_pair_then_final_is_approvable(self):
        """MUTANT MP7 (`<`) : refuse l'ordre nominal de /kickoff (paire d'itération, PUIS
        verdict FINAL). Sans ce jumeau la règle « paire plus récente » refuserait tout plan
        passé par la paire."""
        self.repo.verdicts = [{"title": PAIR_GAR, "text": "x"}, self.final()]
        self.assertApproved(self.reason())
        self.assertEqual(self.repo.run()[0].verdict_id, "S-00000002")

    def test_control_no_pair_at_all_keeps_the_original_message(self):
        """Jumeau de « rien » : aucun verdict plan-critic, aucune paire -> message
        d'origine, sans suffixe."""
        self.repo.verdicts = [{"title": f"documenter LOT GO-live sur {PLAN_REL}"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("aucun verdict plan-critic", o.reason)
        self.assertNotIn("PAIRE", o.reason)

    def test_a_plan_critic_title_carrying_the_word_paire_is_not_a_pair(self):
        """MUTANT MP9 (filtre `not is_plan_critic_verdict` retiré) : un FINAL titré
        « plan-critic GO (verdict de paire GO) » qui ne cite pas le plan serait nommé
        « forme PAIRE » — c'est pourtant la forme attendue."""
        self.repo.verdicts = [{"title": "plan-critic GO (verdict de paire GO)", "text": "aucun chemin ici"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertNotIn("PAIRE", o.reason)

    # -- ce qui n'est PAS une paire ne refuse rien ------------------------------------
    def test_control_a_NON_verdict_entry_carrying_the_word_is_not_a_pair(self):
        """MUTANT MP10 (filtre `kind=verdict` retiré) : 40 entrées vivantes plan/decision/
        delta portent le mot « paire » dans leur titre (32 notes `kind=plan`). Journalisée
        APRÈS le final, l'une d'elles ferait refuser un plan approuvé."""
        self.repo.verdicts = [self.final()]
        self.repo.build()
        self.append_entry(task=TASK, kind="plan", title=PAIR_GAR)
        self.assertApproved(self.repo.outcome())

    def test_control_a_word_merely_CONTAINING_paire_is_not_a_pair(self):
        """MUTANT MP13 (`PAIR_VERDICT_TITLE` sans bornes de mot). Deux formes, journalisées
        APRÈS le final : un mot qui contient « paire » (`impaire`), et le pluriel `paires`
        — RÉSIDU R-d ÉPINGLÉ, NON CLOS (2 titres vivants, S-00001622 et S-00001624) : le
        pluriel n'est pas lu ; l'élargir est une décision, pas une dérive."""
        for title in ("security-code-review : nombre impaire de findings",
                      "T-00000001 itérations 1 et 2 : paires -- NO_GO"):
            with self.subTest(title=title):
                self.repo.verdicts = [self.final()]
                self.repo.build()
                self.append_entry(task=TASK, title=title)
                self.assertApproved(self.repo.outcome(), msg=title)

    def test_the_probe_never_speaks_before_conditions_1_and_2(self):
        """MUTANT MP12 (sonde avant `condition_state` / `condition_plan_exists`) : une tâche
        `done`, ou un plan absent, est refusé par SA condition — un refus nomme la PREMIÈRE
        condition non tenue, jamais la paire."""
        self.repo.states[TASK] = "done"
        self.repo.verdicts = [{"title": PAIR_GAR, "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 1")
        self.assertNotIn("PAIRE", o.reason)

        self.repo.states[TASK] = "pending"
        self.repo.write_plan = False
        self.repo.plan_rel = "docs/tasks/ABSENT-plan.md"
        o = self.reason()
        self.assertSkipped(o, "condition 2")
        self.assertNotIn("PAIRE", o.reason)

    def test_the_probe_never_masks_condition_5_on_a_task_the_plan_does_not_enrol(self):
        """MUTANT MP15 (garde d'enrôlement retirée) : le plan ne fait que MENTIONNER
        STRANGER dans son corps (le cas de `Condition5Tests`), un verdict final cite le plan,
        et une paire de STRANGER est journalisée APRÈS — la règle « plus récente » la
        mordrait. Le vrai refus est la condition 5 : une paire ne masque pas un
        non-enrôlement."""
        self.repo.states = {TASK: "pending", OTHER: "pending", STRANGER: "pending"}
        self.repo.verdicts = [self.final()]
        self.repo.build()
        self.append_entry(task=STRANGER, title="T-00000009 itération 2/8 : paire NO_GO", text="x")
        o = self.repo.outcome(STRANGER)
        self.assertSkipped(o, "condition 5")
        self.assertTrue(o.reason.startswith("condition 5"), o.reason)
        self.assertNotIn("PAIRE", o.reason)
        self.assertNotIn("paire", o.reason)

    def test_a_pair_title_with_control_characters_is_shown_without_them(self):
        """MUTANT MP16 (assainisseur `_titre_affichable` retiré, ou court-circuité au site) :
        un titre de paire est de la prose LIBRE, tapée par n'importe quel agent, et la raison
        s'imprime sur un terminal — `\\x1b[2J` efface l'écran, `\\x9b` est le CSI C1. Chaque
        caractère non imprimable devient une espace AVANT `split()` et la borne ; la partie
        visible du titre reste montrée (sinon « retirer le titre » passerait)."""
        self.repo.verdicts = [{"title": "T-00000001 itération 3/8 : paire GO\x1b[2J\x9bAVEC", "text": "x"}]
        o = self.reason()
        self.assertSkipped(o, "condition 3")
        self.assertIn("forme PAIRE", o.reason)
        self.assertNotIn("\x1b", o.reason)
        self.assertNotIn("\x9b", o.reason)
        self.assertEqual([c for c in o.reason if not c.isprintable()], [])
        self.assertIn("« T-00000001 itération 3/8 : paire GO [2J AVEC »", o.reason)

    # -- LES TROIS CONTRÔLES NÉGATIFS de l'association ---------------------------------
    def test_control_a_pair_of_ANOTHER_task_citing_this_plan_does_not_mask_it(self):
        """MUTANT MP3 (patte « chemin cité » ajoutée) : 11 paires vivantes citent en prose
        le plan d'UNE AUTRE tâche ; rattachée par le chemin, l'une d'elles ferait passer un
        plan APPROUVÉ à SKIP. Journalisée APRÈS le verdict final, pour que la règle « plus
        récente » la morde si elle l'associait."""
        self.repo.verdicts = [self.final()]
        self.repo.build()
        self.append_entry(task=STRANGER, title="T-00000009 itération 2/8 : paire GO_AVEC_RESERVES",
                          text=f"chevauchement : {PLAN_REL}:44,76 prévoit un consommateur à nommer")
        self.assertApproved(self.repo.outcome())

    def test_control_a_pair_of_another_task_without_any_citation_does_not_mask_it(self):
        """MUTANT MP2 (association abandonnée : toute paire du journal compte)."""
        self.repo.verdicts = [self.final()]
        self.repo.build()
        self.append_entry(task=STRANGER, title="T-00000009 itération 2/8 : paire NO_GO", text="sans chemin")
        self.assertApproved(self.repo.outcome())

    def test_control_a_pair_on_one_task_of_a_two_task_lot_spares_the_other(self):
        """MUTANT MP2 encore, en variante « par lot » : le verdict est par PLAN, la paire
        par TÂCHE — le refus est porté par la ligne de la tâche, jamais par l'en-tête du lot."""
        self.repo.verdicts = [self.final()]
        self.repo.build()
        self.append_entry(task=TASK, title=PAIR_NO_GO, text="x")
        by = {o.task: o for o in self.repo.run(TASK, OTHER)[0].outcomes}
        self.assertEqual(by[TASK].decision, night_approve.SKIP)
        self.assertIn("condition 3", by[TASK].reason)
        self.assertEqual(by[OTHER].decision, night_approve.APPROVE, by[OTHER].reason)


# ---------------------------------------------------------------------------
# Condition 4 — the recomputed fingerprint is the recorded one
# ---------------------------------------------------------------------------


class Condition4Tests(RepoCase):
    def test_refuses_a_plan_edited_since_its_critique(self):
        self.repo.build()
        # One added line — even a comment — is enough. That is the whole point:
        # withdrawing an eligibility is done BY TOUCHING THE PLAN.
        self.repo.plan_path().write_bytes((self.repo.plan + "\n<!-- une ligne -->\n").encode("utf-8"))
        self.assertSkipped(self.repo.outcome(), "condition 4")
        self.assertIn("modifie", self.repo.outcome().reason)

    def test_refuses_a_verdict_carrying_no_fingerprint(self):
        self.repo.verdicts = [
            {
                "title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}",
                "text": f"critique du plan {PLAN_REL}, sans empreinte",
            }
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 4")

    def test_refuses_a_verdict_carrying_two_different_fingerprints(self):
        self.repo.build()
        sha = self.repo.sha()
        self.repo.verdicts = [
            {
                "title": f"plan-critic CONCERNS (iteration 1/8) sur {PLAN_REL}",
                "text": f"{PLAN_REL} sha256={sha} puis sha256={'1' * 64}",
            }
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 4")

    def test_control_an_untouched_plan_is_approvable(self):
        self.repo.build()
        self.assertApproved(self.repo.outcome())


# ---------------------------------------------------------------------------
# Condition 5 — the plan ENROLS the task
# ---------------------------------------------------------------------------


class Condition5Tests(RepoCase):
    def test_refuses_a_task_the_plan_only_mentions_in_its_body(self):
        """R4: a pilot typo naming a task that is not the lot's. The four
        historical conditions do not catch it — every one of them passes here."""
        self.repo.states = {TASK: "pending", OTHER: "pending", STRANGER: "pending"}
        self.repo.build()
        outcome = self.repo.outcome(STRANGER)
        self.assertSkipped(outcome, "condition 5")
        self.assertIsNone(outcome.matched)

    def test_refuses_a_task_the_plan_never_mentions_at_all(self):
        self.repo.states = {TASK: "pending", "T-00000077": "pending"}
        self.repo.build()
        self.assertSkipped(self.repo.outcome("T-00000077"), "condition 5")

    def test_control_a_task_enrolled_by_the_roster_is_approvable(self):
        self.repo.states = {TASK: "pending", OTHER: "pending", STRANGER: "pending"}
        self.repo.build()
        outcome = self.repo.outcome(OTHER)
        self.assertApproved(outcome)
        self.assertEqual(outcome.matched.source, "roster")

    def test_control_a_task_enrolled_by_the_title_is_approvable(self):
        self.repo.plan = plan_text(title=f"# PLAN — LOT X ({STRANGER})", roster=None)
        self.repo.states = {STRANGER: "pending"}
        self.repo.build()
        outcome = self.repo.outcome(STRANGER)
        self.assertApproved(outcome)
        self.assertEqual(outcome.matched.source, "titre")


# ---------------------------------------------------------------------------
# The contract itself — format pinned against the two files that read it
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Condition 7 et `--delivered` : le marqueur night-delivered AFFICHÉ (T-00001057)
#
# CE QUE CE BLOC ÉPINGLE. Le titre d'un marqueur est de la prose LIBRE, tapée par
# n'importe quel agent, et son id n'est contrôlé par `specs.load` que sur son
# SUFFIXE numérique (`specs.numeric_id`) : un store édité à la main fait passer
# `S-\x1b[2J…\n…00000099`. Les deux champs passent par `_titre_affichable` AVANT
# d'être imprimés, aux deux sites — la raison de la condition 7 et la ligne de
# `--delivered`. UN SEUL bloc pour les deux classes (`Condition7NightDeliveredTests`,
# `DeliveredSubcommandTests`) : chaque mutant garde l'un des deux sites d'un même
# champ, le tableau se lit d'un tenant.
#
# MUTANTS — chacun rougit AU MOINS les témoins qui le nomment, par AssertionError :
#   MR1  le titre est brut au site condition 7 (assainisseur court-circuité)
#   MR2  le titre est brut au site `--delivered`
#   MR3  l'assainisseur est trop large (`c.isascii() and c.isprintable()`) ; rougit
#        AUSSI le témoin de paire MP16 et la borne MP14 (titres accentués) — attendu
#   MR4  l'assainissement passe APRÈS `split()` au site condition 7 (espaces doubles)
#   MR4b l'assainissement passe APRÈS `split()` au site `--delivered`
#   MR5  le titre est RETIRÉ de la raison de la condition 7 (« » vide)
#   MR6  l'id du marqueur est brut au site condition 7 (S-00003403)
#   MR6b l'id du marqueur est brut au site `--delivered` (S-00003403)
# ---------------------------------------------------------------------------

# Un id que `specs.load` admet (suffixe numérique 99, sans collision) et qui, imprimé
# brut, efface l'écran ET forge une ligne de rapport pour OTHER (M14, critique B).
FORGED_MARKER_ID = "S-\x1b[2Jx\nT-00000002 : aucun marqueur night-delivered en vigueur\nS-00000099"
FORGED_MARKER_ID_SHOWN = "S- [2Jx T-00000002 : aucun marqueur night-delivered en vigueur S-00000099"
# Les blancs de `str.split()` que `_titre_affichable` doit aussi remplacer sur l'id, qu'aucun
# `split()` ne replie : CR, TAB, VT, FF, NEL, U+2028, U+2029 (le titre, lui, les perd au repli).
BLANK_CLASS_MARKER_ID = "S-a\rb\tc\x0bd\x0ce\x85f\u2028g\u2029h00000099"
BLANK_CLASS_MARKER_ID_SHOWN = "S-a b c d e f g h00000099"


def forge_entry_id(repo: Repo, old: str, forged: str) -> None:
    """Réécrit l'id d'UNE entrée du journal APRÈS `Repo.build` — le store édité à la
    main, seul porteur d'un id forgé (`specs.py add` génère l'id)."""
    path = specs.store_path(repo.root)
    journal = json.loads(path.read_text(encoding="utf-8"))
    [entry] = [e for e in journal["entries"] if e["id"] == old]
    entry["id"] = forged
    path.write_text(json.dumps(journal), encoding="utf-8")


class Condition7NightDeliveredTests(RepoCase):
    """T-00000847 — a task the night DELIVERED is refused while it is not closed.

    The fixture satisfies conditions 1-6 (pending, plan present, GO-family
    verdict, fingerprint, roster, no draft marker): the journal entry is the ONE
    knob. On the code before condition 7 every refusal case here reads APPROVE.
    Titles are literal strings — the night's exact form — never the module
    constant, so a missing constant cannot turn the red into an error."""

    DELIVERED = "night-delivered: attente binome du matin"
    CLEARED = "night-delivered: cleared"

    def test_a_pending_task_carrying_the_marker_is_refused_and_the_reason_names_it(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        outcome = self.repo.outcome()
        self.assertSkipped(outcome, "condition 7")
        self.assertIn("night-delivered", outcome.reason)
        self.assertIn("S-00000002", outcome.reason, "le motif doit nommer l'entree qui refuse")

    def test_control_without_the_marker_the_same_task_is_approvable(self):
        """Twin control — non-regression: the same fixture, no marker."""
        self.repo.extra = []
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_a_done_task_carrying_the_marker_is_out_of_play_by_condition_1_without_error(self):
        self.repo.states = {TASK: "done", OTHER: "pending"}
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        outcome = self.repo.outcome()  # no exception
        self.assertSkipped(outcome, "condition 1")
        self.assertIn("done", outcome.reason)

    def test_another_tasks_marker_does_not_affect_this_one(self):
        self.repo.extra = [(OTHER, "decision", self.DELIVERED)]
        self.repo.build()
        mine, other = self.repo.run(TASK, OTHER)[0].outcomes
        self.assertApproved(mine, "le marqueur de OTHER a deteint sur TASK")
        self.assertSkipped(other, "condition 7")

    def test_the_marker_refuses_through_check_and_apply_and_writes_nothing(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        before = len(self.repo.journal())
        self.assertSkipped(self.repo.outcome(apply=True), "condition 7")
        self.assertEqual(len(self.repo.journal()), before, "--apply a ecrit un contrat")

    def test_a_marker_spelled_otherwise_or_under_another_kind_still_refuses(self):
        """Fail-closed: the probe is WIDER than the exact title."""
        for kind, title in (
            ("delta", self.DELIVERED),
            ("decision", "Night-Delivered : livre, attente binome"),
            ("decision", "  night-delivered"),
        ):
            with self.subTest(kind=kind, title=title):
                self.repo.extra = [(TASK, kind, title)]
                self.repo.build()
                self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_control_a_prefix_extension_is_not_the_marker(self):
        self.repo.extra = [(TASK, "decision", "night-delivered-lite: autre chose")]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_a_marker_journaled_under_the_SHORT_id_form_still_refuses(self):
        """T1 (critic-opus): `tasks.py` accepts `T-848` for `T-00000848` and
        `specs.py add` records the id AS TYPED — here `T-1` for `T-00000001`."""
        self.repo.extra = [("T-1", "decision", self.DELIVERED)]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_the_short_form_of_ANOTHER_task_does_not_leak(self):
        """Control: `T-2` is OTHER's short form, not TASK's. (A non-`T-` id never
        reaches here: `specs.load` refuses such a store outright.)"""
        self.repo.extra = [("T-2", "decision", self.DELIVERED)]
        self.repo.build()
        mine, other = self.repo.run(TASK, OTHER)[0].outcomes
        self.assertApproved(mine)
        self.assertSkipped(other, "condition 7")

    def test_a_clearing_under_the_short_id_form_clears(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED), ("T-1", "decision", self.CLEARED)]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_a_clearing_spelled_otherwise_does_NOT_clear(self):
        """T4 (critic-opus): the clearing is compared to the EXACT title."""
        for title in ("NIGHT-DELIVERED:   Cleared", "night-delivered: Cleared", " night-delivered: cleared"):
            with self.subTest(title=title):
                self.repo.extra = [(TASK, "decision", self.DELIVERED), (TASK, "decision", title)]
                self.repo.build()
                self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_a_pilot_clearing_after_the_marker_restores_eligibility(self):
        """The `reopen` route: done → pending, the pilot clears explicitly."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED), (TASK, "decision", self.CLEARED)]
        self.repo.build()
        self.assertApproved(self.repo.outcome())

    def test_a_delivery_AFTER_a_clearing_re_arms_the_marker(self):
        self.repo.extra = [
            (TASK, "decision", self.DELIVERED),
            (TASK, "decision", self.CLEARED),
            (TASK, "decision", self.DELIVERED),
        ]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_a_clearing_under_another_kind_does_not_clear(self):
        """The clearing is read NARROWLY — a lax one would be the fail-open side."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED), (TASK, "delta", self.CLEARED)]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_another_tasks_clearing_does_not_clear_this_one(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED), (OTHER, "decision", self.CLEARED)]
        self.repo.build()
        self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_the_constants_are_the_night_md_gesture(self):
        """The title the tool reads is the one the night's fenced gesture writes."""
        self.assertEqual(night_approve.NIGHT_DELIVERED_TITLE, self.DELIVERED)
        self.assertEqual(night_approve.NIGHT_DELIVERED_CLEARED_TITLE, self.CLEARED)
        self.assertEqual(night_approve.NIGHT_DELIVERED_KIND, "decision")
        night = NIGHT.read_text(encoding="utf-8")
        self.assertIn(
            # T-00001044: the night types its scripts through `pyrun.sh`.
            f'bash .agents/pyrun.sh .agents/bin/specs.py add --task T-NNNNNNNN --kind decision "{self.DELIVERED}"',
            night,
        )
        self.assertIn(f'--kind decision "{self.CLEARED}"', night)

    def test_the_night_md_gesture_goes_through_specs_add_without_refusal(self):
        """The exact gesture is accepted by the real `specs.py add` (no guard bites)."""
        self.repo.build()
        msg = specs.add_entry(self.repo.root, TASK, "decision", self.DELIVERED, text="x @ a..b")
        self.assertIn("added", msg)
        self.assertSkipped(self.repo.outcome(), "condition 7")

    def test_a_marker_title_with_control_characters_is_shown_without_them(self):
        """MUTANTS MR1 (titre brut au site), MR4 (assaini APRÈS `split()` : « binome  du
        matin », espaces doubles — l'ordre est la propriété), MR5 (titre retiré : sans le
        fragment visible exact, « supprimer le titre » passerait, la raison portant encore
        « night-delivered: cleared » par sa clause de sortie). La fixture porte un
        représentant de chaque sous-classe non imprimable sans espace au sens de `split()` :
        ESC, CSI C1 `\\x9b`, BEL, BS `\\x08`, DEL `\\x7f`, et U+202E (format, inversion
        bidi) — ces trois derniers COLLÉS aux lettres, pour qu'un assainisseur qui les
        exempte, ou qui SUPPRIME au lieu de remplacer, rougisse. Pas de `\\r` : `split()`
        le replie, le mutant qui l'exempterait serait équivalent."""
        self.repo.extra = [
            (TASK, "decision", "night-delivered: attente\x1b[2J binome\x9b du\x07 matin\x08de\x7fla\u202enuit")
        ]
        self.repo.build()
        o = self.repo.outcome()
        self.assertSkipped(o, "condition 7")  # la décision est inchangée : l'affichage seul
        self.assertIn("S-00000002", o.reason)
        self.assertEqual([c for c in o.reason if not c.isprintable()], [])
        self.assertIn("« night-delivered: attente [2J binome du matin de la nuit »", o.reason)

    def test_a_forged_marker_id_cannot_forge_lines_in_the_reason(self):
        """MUTANT MR6 (id brut au site condition 7). `specs.load` ne contrôle que le
        SUFFIXE numérique de l'id : un store édité à la main y loge un ESC et des sauts de
        ligne qui, imprimés bruts, forgent une ligne de rapport. L'id reste MONTRÉ,
        assaini — jamais retiré (le refus doit nommer l'entrée qui refuse)."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        forge_entry_id(self.repo, "S-00000002", FORGED_MARKER_ID)
        o = self.repo.outcome()
        self.assertSkipped(o, "condition 7")
        self.assertNotIn("\n", o.reason)
        self.assertEqual([c for c in o.reason if not c.isprintable()], [])
        self.assertIn(f"({FORGED_MARKER_ID_SHOWN} « night-delivered: attente binome du matin »)", o.reason)

    def test_a_forged_marker_id_with_blank_class_controls_is_shown_without_them(self):
        """MUTANTS MR7 (l'assainisseur exempte `\\r`) et MR8 (il exempte `\\t \\x0b \\x0c
        \\x85` U+2028 U+2029). L'id n'est PAS replié par `split()` comme l'est le titre : seul
        `_titre_affichable` le garde. `\\r` ramène le curseur en colonne 0 et le texte qui suit
        RECOUVRE le début de la ligne imprimée ; `FORGED_MARKER_ID` ne porte que ESC et `\\n`."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        forge_entry_id(self.repo, "S-00000002", BLANK_CLASS_MARKER_ID)
        o = self.repo.outcome()
        self.assertSkipped(o, "condition 7")
        self.assertEqual([c for c in o.reason if not c.isprintable()], [])
        self.assertIn(f"({BLANK_CLASS_MARKER_ID_SHOWN} « night-delivered: attente binome du matin »)", o.reason)


class ContractFormatTests(RepoCase):
    def test_contract_is_the_kickoff_form_including_approved(self):
        self.repo.build()
        outcome = self.repo.outcome()
        self.assertRegex(
            outcome.contract,
            r"^plan=docs/tasks/LOT-X-plan\.md sha256=[0-9a-f]{64} "
            r"verdict=S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8}) approved=\d{4}-\d{2}-\d{2}$",
        )

    def test_the_title_is_the_one_the_night_greps_for(self):
        self.assertEqual(night_approve.CONTRACT_TITLE, "night-eligible: approved")
        self.assertEqual(night_approve.CONTRACT_KIND, "decision")

    def test_the_field_ORDER_is_the_one_kickoff_documents(self):
        """Surveyed from `kickoff.md`, never recopied from memory (R1)."""
        text = KICKOFF.read_text(encoding="utf-8")
        self.assertIn(
            "plan=docs/tasks/T-NNN-plan.md sha256=<hex> verdict=S-NNNNNNNN approved=<YYYY-MM-DD>",
            text,
            "kickoff.md a change de forme de contrat — l'outil doit suivre",
        )
        self.repo.build()
        skeleton = re.sub(r"=\S+", "=<x>", self.repo.outcome().contract)
        self.assertEqual(skeleton, "plan=<x> sha256=<x> verdict=<x> approved=<x>")

    def test_the_contract_carries_every_field_the_night_rereads(self):
        """Inclusion, said rather than suffered: the night reads
        {title, plan=, sha256=, verdict=}; kickoff adds `approved=`."""
        night = NIGHT.read_text(encoding="utf-8")
        for field in ("night-eligible: approved", "plan=", "sha256=", "verdict="):
            self.assertIn(field, night, f"{field} n'est plus exige par night.md")
        self.repo.build()
        contract = self.repo.outcome().contract
        for field in ("plan=", "sha256=", "verdict="):
            self.assertIn(field, contract)


# ---------------------------------------------------------------------------
# Idempotence — identity on the EXTRACTED FIELDS, never on the byte (D5)
# ---------------------------------------------------------------------------


class IdempotenceTests(RepoCase):
    def prose_contract(self, sha: str) -> str:
        """The MEASURED shape of the 14 contracts already in this repo: a
        sentence, and NO `approved=` field. A byte comparison classes it as
        different and appends a duplicate."""
        return (
            "Approuve par le pilote le 2026-08-18 a 04h20 pour la nuit du 2026-08-18 "
            f"(fenetre 04:16 -> 16:30). plan={PLAN_REL} sha256={sha} verdict=S-00000001"
        )

    def test_a_prose_contract_with_the_same_fields_counts_as_already_approved(self):
        self.repo.build()
        self.repo.contracts = [(TASK, self.prose_contract(self.repo.sha()))]
        self.repo.build()
        self.assertEqual(self.repo.outcome().decision, night_approve.ALREADY)

    def test_already_approved_writes_nothing_even_under_apply(self):
        self.repo.build()
        self.repo.contracts = [(TASK, self.prose_contract(self.repo.sha()))]
        self.repo.build()
        before = len(self.repo.journal())
        self.repo.run(apply=True)
        self.assertEqual(len(self.repo.journal()), before)

    def test_a_contract_for_a_DIFFERENT_fingerprint_is_appended_never_substituted(self):
        stale = self.prose_contract("2" * 64)
        self.repo.contracts = [(TASK, stale)]
        self.repo.build()
        self.assertApproved(self.repo.outcome())
        self.repo.run(apply=True)
        contracts = self.repo.contracts_for(TASK)
        self.assertEqual(len(contracts), 2, "l'ancien contrat doit RESTER au journal")
        self.assertIn(stale, [c["text"] for c in contracts])
        self.assertIn("2" * 64, contracts[0]["text"])

    def test_replaying_apply_is_safe(self):
        """R2 — an interrupted write is replayed without duplicating."""
        self.repo.build()
        self.repo.run(apply=True)
        after_first = len(self.repo.journal())
        self.repo.run(apply=True)
        self.assertEqual(len(self.repo.journal()), after_first)


# ---------------------------------------------------------------------------
# Modes, and what each one is allowed to touch
# ---------------------------------------------------------------------------


class ModeTests(RepoCase):
    def test_check_writes_nothing_at_all(self):
        self.repo.build()
        before = specs.store_path(self.repo.root).read_bytes()
        board_before = tasks.store_path(self.repo.root).read_bytes()
        results = self.repo.run(apply=False)
        self.assertApproved(results[0].outcomes[0])
        self.assertEqual(specs.store_path(self.repo.root).read_bytes(), before)
        self.assertEqual(tasks.store_path(self.repo.root).read_bytes(), board_before)

    def test_apply_writes_exactly_one_contract_per_approved_task(self):
        self.repo.build()
        self.repo.run(TASK, OTHER, apply=True)
        self.assertEqual(len(self.repo.contracts_for(TASK)), 1)
        self.assertEqual(len(self.repo.contracts_for(OTHER)), 1)

    def test_apply_leaves_the_task_pending(self):
        """A deferred task is not in flight — the tool never touches the board."""
        self.repo.build()
        self.repo.run(apply=True)
        board = tasks.load(self.repo.root)
        self.assertEqual(tasks.find(board, TASK)["state"], "pending")

    def test_apply_reports_the_id_it_wrote(self):
        self.repo.build()
        outcome = self.repo.run(apply=True)[0].outcomes[0]
        self.assertRegex(outcome.written_id, r"^S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})$")


# ---------------------------------------------------------------------------
# D4 — a bad lot is skipped and NAMED, it does not block the others
# ---------------------------------------------------------------------------


class BadLotDoesNotBlockTests(RepoCase):
    def test_a_lot_whose_plan_is_absent_does_not_stop_a_healthy_lot(self):
        self.repo.build()
        lots = [
            night_approve.Lot(plan="docs/tasks/DISPARU-plan.md", tasks=[TASK]),
            self.repo.lot(TASK, OTHER),
        ]
        results = night_approve.run(self.repo.root, lots, apply=True, approved_on="2026-08-19")
        self.assertSkipped(results[0].outcomes[0], "condition 2")
        self.assertApproved(results[1].outcomes[0])
        self.assertEqual(len(self.repo.contracts_for(OTHER)), 1)

    def test_the_recap_names_every_skip_with_its_reason(self):
        self.repo.states = {TASK: "done", OTHER: "pending"}
        self.repo.build()
        text = "\n".join(night_approve.report(self.repo.run(TASK, OTHER), apply=False))
        self.assertIn("RECAPITULATIF", text)
        self.assertIn(f"{TASK} ({PLAN_REL}) — condition 1", text)
        self.assertIn("sautees         : 1", text)


# ---------------------------------------------------------------------------
# The report PRINTS the matched line — in --check as in --apply
# ---------------------------------------------------------------------------


class ReportTests(RepoCase):
    def test_the_matched_line_is_printed_in_both_modes(self):
        self.repo.build()
        for apply in (False, True):
            with self.subTest(apply=apply):
                text = "\n".join(
                    night_approve.report(self.repo.run(TASK, apply=apply), apply=apply)
                )
                self.assertIn("appariee sur roster (ligne 3)", text)
                self.assertIn(ROSTER_LINE, text)

    def test_a_task_matched_by_nothing_says_so(self):
        self.repo.states = {TASK: "pending", STRANGER: "pending"}
        self.repo.build()
        text = "\n".join(night_approve.report(self.repo.run(STRANGER), apply=False))
        self.assertIn("AUCUNE ligne (ni titre, ni roster)", text)

    def test_a_pathological_line_is_bounded_and_the_truncation_announced(self):
        self.repo.plan = plan_text(roster=f"Tâches : {TASK} " + "x" * 5000)
        self.repo.build()
        text = "\n".join(night_approve.report(self.repo.run(TASK), apply=False))
        self.assertIn("tronquee", text)
        self.assertTrue(all(len(line) < 600 for line in text.splitlines()))


# ---------------------------------------------------------------------------
# The agenda stays CLOSED — no discovery, no "approve all"
# ---------------------------------------------------------------------------


class ClosedAgendaTests(RepoCase):
    def test_a_task_not_named_is_never_approved_even_when_it_qualifies(self):
        """OTHER is pending, enrolled by the roster, and its plan is critiqued
        and unchanged — it satisfies every eligibility condition. It is not approved,
        because it was not NAMED."""
        self.repo.build()
        self.repo.run(TASK, apply=True)
        self.assertEqual(len(self.repo.contracts_for(TASK)), 1)
        self.assertEqual(self.repo.contracts_for(OTHER), [])

    def test_the_cli_offers_no_approve_all_flag(self):
        actions = night_approve.build_arg_parser()._actions
        flags = {opt for a in actions for opt in a.option_strings}
        # `--delivered` (T-00000847) is a READ-ONLY query on NAMED tasks — it
        # writes nothing and discovers nothing (DeliveredSubcommandTests).
        self.assertEqual(
            flags, {"-h", "--help", "--root", "--check", "--apply", "--lot", "--delivered"}
        )

    def test_a_task_named_twice_in_one_lot_gets_one_contract(self):
        self.repo.build()
        result = self.repo.run(TASK, TASK, apply=True)[0]
        self.assertEqual(result.duplicates, [TASK])
        self.assertEqual(len(self.repo.contracts_for(TASK)), 1)

    def test_a_task_named_in_two_lots_gets_one_contract(self):
        self.repo.build()
        lots = [self.repo.lot(TASK), self.repo.lot(TASK)]
        results = night_approve.run(self.repo.root, lots, apply=True, approved_on="2026-08-19")
        self.assertApproved(results[0].outcomes[0])
        self.assertEqual(results[1].outcomes[0].decision, night_approve.ALREADY)
        self.assertEqual(len(self.repo.contracts_for(TASK)), 1)


# ---------------------------------------------------------------------------
# Argument refusals — D6, and the id form condition 5 rests on
# ---------------------------------------------------------------------------


class ArgumentRefusalTests(unittest.TestCase):
    def test_a_lot_naming_no_task_is_refused_loudly(self):
        with self.assertRaises(night_approve.NightApproveError) as ctx:
            night_approve.parse_lots([[PLAN_REL]])
        self.assertIn("ne nomme aucune tache", str(ctx.exception))

    def test_no_lot_at_all_is_refused(self):
        with self.assertRaises(night_approve.NightApproveError) as ctx:
            night_approve.parse_lots([])
        self.assertIn("agenda ouvert", str(ctx.exception))

    def test_a_malformed_task_id_is_refused(self):
        for bad in ("T-206", "206", "T-000002066", "TT-00000206"):
            with self.subTest(bad=bad):
                with self.assertRaises(night_approve.NightApproveError):
                    night_approve.parse_lots([[PLAN_REL, bad]])

    def test_control_a_well_formed_lot_parses(self):
        lots = night_approve.parse_lots([[PLAN_REL, TASK, OTHER]])
        self.assertEqual(lots[0].plan, PLAN_REL)
        self.assertEqual(lots[0].tasks, [TASK, OTHER])


class CliTests(RepoCase):
    def cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.repo.root), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_check_is_the_default_mode(self):
        self.repo.build()
        before = specs.store_path(self.repo.root).read_bytes()
        proc = self.cli("--lot", PLAN_REL, TASK)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mode : check", proc.stdout)
        self.assertEqual(specs.store_path(self.repo.root).read_bytes(), before)

    def test_empty_lot_exits_2_and_says_why(self):
        self.repo.build()
        proc = self.cli("--lot", PLAN_REL)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ne nomme aucune tache", proc.stderr)

    def test_apply_writes_and_reports(self):
        self.repo.build()
        proc = self.cli("--apply", "--lot", PLAN_REL, TASK)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("APPROUVEE", proc.stdout)
        self.assertEqual(len(self.repo.contracts_for(TASK)), 1)

    def test_check_and_apply_are_mutually_exclusive(self):
        self.repo.build()
        proc = self.cli("--check", "--apply", "--lot", PLAN_REL, TASK)
        self.assertEqual(proc.returncode, 2)


class DeliveredSubcommandTests(RepoCase):
    """`--delivered` (T-00000847, critic-fable NO_GO, pilot decision): the read
    the night delegates, because `specs.py list --task` compares the STRING and
    misses a marker journaled under the short form. Real CLI, real rc."""

    cli = CliTests.cli

    DELIVERED = "night-delivered: attente binome du matin"
    CLEARED = "night-delivered: cleared"

    def test_no_marker_rc_0(self):
        self.repo.build()
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("aucun marqueur", proc.stdout)

    def test_a_short_form_marker_is_SEEN_rc_1_and_named(self):
        self.repo.extra = [("T-1", "decision", self.DELIVERED)]
        self.repo.build()
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("EN VIGUEUR", proc.stdout)
        self.assertIn("S-00000002", proc.stdout)
        # and the string-comparing read the night used to cite does miss it
        self.assertNotIn("S-00000002", specs.render_list(self.repo.root, TASK, "decision"))

    def test_the_short_form_asked_sees_a_long_form_marker(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        self.assertEqual(self.cli("--delivered", "T-1").returncode, 1)

    def test_an_exact_clearing_rc_0_a_near_miss_rc_1(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED), (TASK, "decision", self.CLEARED)]
        self.repo.build()
        self.assertEqual(self.cli("--delivered", TASK).returncode, 0)
        self.repo.extra = [(TASK, "decision", self.DELIVERED), (TASK, "decision", "NIGHT-DELIVERED:   Cleared")]
        self.repo.build()
        self.assertEqual(self.cli("--delivered", TASK).returncode, 1)

    def test_one_task_in_force_among_several_rc_1(self):
        self.repo.extra = [(OTHER, "decision", self.DELIVERED)]
        self.repo.build()
        proc = self.cli("--delivered", TASK, OTHER)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"{TASK} : aucun marqueur", proc.stdout)
        self.assertIn(f"{OTHER} : MARQUEUR", proc.stdout)

    def test_an_unreadable_journal_is_rc_2_fail_closed(self):
        self.repo.build()
        specs.store_path(self.repo.root).write_text("{ pas du json", encoding="utf-8")
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("illisible", proc.stderr)

    def test_a_non_utf8_journal_is_rc_2_not_a_traceback(self):
        self.repo.build()
        specs.store_path(self.repo.root).write_bytes(b"\xff\xfe\x00garbage")
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_an_absent_journal_is_rc_2_fail_closed(self):
        self.repo.build()
        specs.store_path(self.repo.root).unlink()
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("journal absent", proc.stderr)

    def test_a_malformed_id_and_a_mixed_mode_are_rc_2(self):
        self.repo.build()
        self.assertEqual(self.cli("--delivered", "848").returncode, 2)
        self.assertEqual(self.cli("--delivered", TASK, "--lot", PLAN_REL, TASK).returncode, 2)
        self.assertEqual(self.cli("--delivered", TASK, "--apply").returncode, 2)

    def test_delivered_writes_nothing(self):
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        before = specs.store_path(self.repo.root).read_bytes()
        self.cli("--delivered", TASK)
        self.assertEqual(specs.store_path(self.repo.root).read_bytes(), before)

    def test_apply_refuses_a_marked_task_via_the_cli(self):
        """Point 2: `--apply` already refuses (principle: the tool never writes a
        contract the night will refuse) — proven on the real CLI."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        before = len(self.repo.journal())
        proc = self.cli("--apply", "--lot", PLAN_REL, TASK)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("condition 7", proc.stdout)
        self.assertEqual(len(self.repo.journal()), before)

    def test_delivered_shows_a_marker_title_without_its_control_characters(self):
        """MUTANTS MR2 (titre brut au site `--delivered`), MR4b (assaini APRÈS `split()` :
        « ]0;pwn  binome », espace double). Par le CLI RÉEL : c'est la seule lecture que
        `/night` délègue à cet outil, et elle s'imprime sur un terminal — `\\x1b]0;…\\x07`
        réécrit le titre de la fenêtre, `\\x9b` ouvre un CSI C1. rc et forme de ligne
        inchangés."""
        self.repo.extra = [(TASK, "decision", "night-delivered: attente\x1b]0;pwn\x07 binome\x9b2J")]
        self.repo.build()
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("EN VIGUEUR", proc.stdout)
        self.assertIn("S-00000002", proc.stdout)
        self.assertEqual([c for c in proc.stdout if not c.isprintable() and c != "\n"], [])
        self.assertIn("« night-delivered: attente ]0;pwn binome 2J »", proc.stdout)

    def test_control_a_printable_non_ascii_marker_title_is_shown_byte_for_byte(self):
        """MUTANTS MR3 (assainisseur trop large : « ô », « — », « « » » mangés) et MR5
        (titre retiré de la raison). Contrôle négatif aux DEUX sites — la raison de la
        condition 7 et le stdout `--delivered` — qu'aucun autre témoin ne lit ensemble.
        Jamais d'espace insécable ici : U+00A0 et U+202F ne sont pas imprimables au sens
        de `str.isprintable` et DEVIENNENT des espaces — comportement voulu, hérité de
        T-00000673."""
        title = "night-delivered: attente binôme — matin « nuit »"
        self.repo.extra = [(TASK, "decision", title)]
        self.repo.build()
        o = self.repo.outcome()
        self.assertSkipped(o, "condition 7")
        self.assertIn(f"« {title} »", o.reason)
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"« {title} »", proc.stdout)

    def test_delivered_a_forged_marker_id_cannot_forge_report_lines(self):
        """MUTANT MR6b (id brut au site `--delivered`). Mesuré avant le correctif (M14) :
        l'id forgé imprime TROIS lignes pour UNE tâche, dont une fausse « T-00000002 :
        aucun marqueur » — invisible à une sonde qui exclut `\\n`. Une ligne par tâche
        nommée, l'id montré assaini."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        forge_entry_id(self.repo, "S-00000002", FORGED_MARKER_ID)
        proc = self.cli("--delivered", TASK)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        self.assertEqual([c for c in proc.stdout if not c.isprintable() and c != "\n"], [])
        self.assertIn(f"EN VIGUEUR — {FORGED_MARKER_ID_SHOWN} (task={TASK})", proc.stdout)

    def test_delivered_a_forged_marker_id_with_blank_class_controls_prints_no_raw_byte(self):
        """MUTANTS MR7/MR8 au site `--delivered`, lus en OCTETS : `self.cli` (`text=True`)
        traduit `\\r` en `\\n` avant que le test ne lise, et la sonde `c != "\\n"` des autres
        témoins ne voit donc JAMAIS un CR brut."""
        self.repo.extra = [(TASK, "decision", self.DELIVERED)]
        self.repo.build()
        forge_entry_id(self.repo, "S-00000002", BLANK_CLASS_MARKER_ID)
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.repo.root), "--delivered", TASK],
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual([b for b in proc.stdout if b < 0x20 and b != 0x0A], [])
        for brut in ("\x85", "\u2028", "\u2029"):
            self.assertNotIn(brut.encode("utf-8"), proc.stdout)
        self.assertIn(f"EN VIGUEUR — {BLANK_CLASS_MARKER_ID_SHOWN} (task={TASK})".encode("utf-8"), proc.stdout)


# ---------------------------------------------------------------------------
# plan_pool : la forme refusée NOMMÉE (T-00000673) — témoins portés par le CLI réel
#
# POURQUOI ICI ET PAS DANS `plan_pool.test.sh`. Ce fichier est le banc de la VOIE
# D'APPROBATION (il porte déjà `KICKOFF`, `NIGHT`, `TOOL`) ; le banc natif de
# `plan_pool` est un banc bash tenu par T-00000671 et T-00000726, et le toucher
# ferait de cette tâche une tâche Python + bash. Le CLI est lancé en SOUS-PROCESSUS :
# aucun `exec_module` (le filet `test_modload_registration.py` balaie `.agents/`),
# aucun import de `plan_pool` dans le processus. L'ABSENCE du script est un ÉCHEC,
# jamais un skip — un skip rendrait ce banc vert sans avoir rien mesuré.
#
# MUTANTS — chacun rougit AU MOINS les témoins qui le nomment :
#   MQ1 le suffixe « PAIRE » s'ajoute à TOUT verdict hors grammaire
#   MQ2 le suffixe « PAIRE » est retiré
#   MQ3 le message SHA_ABSENT retombe à l'original (ni S-id, ni forme, ni indice)
#   MQ4 le message WRITE_SET_ABSENT retombe à l'original (titre non canonique tu)
#   MQ5 la précision WRITE_SET_ABSENT s'ajoute même à un titre CANONIQUE
#   MQ6 l'indice « decision » s'ajoute à tout titre non canonique
#   MQ7 la copie `PAIRE_RE` dérive de `night_approve.PAIR_VERDICT_TITLE`
#   MQ8 `PAIRE_RE` perd ses bornes de mot (N6 de la critique B)
#   MQ9 la précision WRITE_SET_ABSENT perd la forme attendue (N13)
#   MQ10 l'assainisseur `_titre_affichable` de `plan_pool` est retiré (S-00003335)
#   MQ11 l'assainisseur est court-circuité au site SHA_ABSENT (titre de note)
#   MQ12 l'assainisseur est court-circuité au site PLAN_SANS_VERDICT (titre de verdict)
# ---------------------------------------------------------------------------


class PlanPoolNamedFormTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(POOL.is_file(), f"{POOL} absent : ce banc ne peut rien mesurer (jamais un skip)")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        try:
            self._tmp.cleanup()
        except OSError:
            pass

    @staticmethod
    def _env():
        # Un `GIT_DIR` hérité (hook pre-push, worktree) ferait lire AU MAUVAIS DÉPÔT : on le vide.
        return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def _git(self, *args):
        # `commit.gpgsign=false` : un poste qui signe par défaut ferait échouer le commit
        # du banc (agent gpg absent, phrase de passe) — jamais une propriété de plan_pool.
        return subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=banc", "-c", "user.email=banc@local",
             "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True, env=self._env(), check=True,
        ).stdout.strip()

    def repo(self, plan_title, files, verdict_title=None):
        """Un VRAI dépôt git à un commit (sha court réel, comme `plan_pool.test.sh`)."""
        self._git("init", "-q")
        (self.root / "b.txt").write_text("stable\n", encoding="utf-8")
        self._git("add", "b.txt")
        self._git("commit", "-q", "-m", "chore: banc")
        sha = self._git("rev-parse", "--short", "HEAD")
        (self.root / ".agents" / "state" / "board").mkdir(parents=True)
        (self.root / ".agents" / "state" / "specs").mkdir(parents=True)
        tasks.store_path(self.root).write_text(json.dumps(
            {"next_id": 2, "tasks": [{"id": TASK, "state": "pending", "task": "banc", "owner": "dev-mono"}]}),
            encoding="utf-8")
        entries = [{"id": "S-00000001", "task": TASK, "kind": "plan", "title": plan_title.replace("<sha>", sha),
                    "text": "", "files": files, "date": "2026-09-30"}]
        if verdict_title:
            entries.append({"id": "S-00000002", "task": TASK, "kind": "verdict", "title": verdict_title,
                            "text": "", "files": [], "date": "2026-09-30"})
        specs.store_path(self.root).write_text(json.dumps({"next_id": 4, "entries": entries}), encoding="utf-8")

    def check(self):
        p = subprocess.run([sys.executable, "-B", str(POOL), "--root", str(self.root), "check", TASK],
                           capture_output=True, text=True, env=self._env())
        return p.returncode, p.stdout

    def test_the_pair_word_copy_is_the_one_night_approve_judges_with(self):
        """MUTANT MQ7 (la copie dérive) et MQ8 (bornes de mot perdues) : `plan_pool` ne peut
        pas importer `.agents/bin`, il RECOPIE le motif — lu ici en TEXTE, jamais chargé.
        Les drapeaux comptent aussi : un `re.I` d'un seul côté est une dérive."""
        pool = POOL.read_text(encoding="utf-8")
        m = re.search(r'^PAIRE_RE = re\.compile\(r"(?P<p>[^"]+)"\)$', pool, re.MULTILINE)
        self.assertIsNotNone(m, "PAIRE_RE introuvable (ou porteur de drapeaux) dans plan_pool.py")
        self.assertEqual(night_approve.PAIR_VERDICT_TITLE.pattern, m.group("p"))
        self.assertEqual(night_approve.PAIR_VERDICT_TITLE.flags, re.compile(m.group("p")).flags)

    def test_a_pair_verdict_is_named_in_the_PLAN_SANS_VERDICT_detail(self):
        """MUTANT MQ2 (suffixe retiré)."""
        self.repo("Plan @ <sha> - objet", ["b.txt"], "T-00000001 itération 1/8 : paire GO_AVEC_RESERVES (A / B)")
        rc, out = self.check()
        self.assertEqual(rc, 11, out)
        self.assertIn("hors grammaire", out)  # sous-chaîne épinglée (plan_pool.test.sh)
        self.assertIn("verdict de PAIRE", out)
        self.assertIn("plan-critic <VERDICT>", out)

    def test_control_a_non_pair_verdict_outside_the_grammar_carries_NO_pair_suffix(self):
        """MUTANT MQ1 (filtre `\\bpaire\\b` retiré) : « security-code-review aucun finding »
        (S-00003317, T-00001043, vivant) serait dit « verdict de PAIRE » — le suffixe est une
        ACCUSATION, il doit mordre la paire et rien d'autre."""
        self.repo("Plan @ <sha> - objet", ["b.txt"], "security-code-review aucun finding — CLEAN")
        rc, out = self.check()
        self.assertEqual(rc, 11, out)
        self.assertIn("hors grammaire", out)
        self.assertNotIn("PAIRE", out)

    def test_control_a_word_merely_containing_paire_carries_NO_pair_suffix(self):
        """MUTANT MQ8 (`PAIRE_RE` sans bornes de mot) : le pluriel `paires` (RÉSIDU R-d,
        2 titres vivants) n'est pas lu ici non plus — la copie suit l'original."""
        self.repo("Plan @ <sha> - objet", ["b.txt"], "T-00000001 itérations 1 et 2 : paires -- NO_GO")
        rc, out = self.check()
        self.assertEqual(rc, 11, out)
        self.assertIn("hors grammaire", out)
        self.assertNotIn("PAIRE", out)

    def test_control_the_twin_plan_critic_go_is_READY(self):
        """Le jumeau, sur un vrai dépôt : même plan, verdict `plan-critic GO` -> READY (rc 0)."""
        self.repo("Plan @ <sha> - objet", ["b.txt"], "plan-critic GO")
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("READY", out)

    def test_a_non_canonical_plan_note_is_named_with_its_id_and_the_expected_form(self):
        """MUTANT MQ3 (message d'origine)."""
        self.repo("plan approuve T-00000001 — objet", ["b.txt"])
        rc, out = self.check()
        self.assertEqual(rc, 12, out)
        self.assertIn("titre du plan non canonique", out)  # sous-chaîne d'origine conservée
        self.assertIn("S-00000001", out)
        self.assertIn("MASQUE", out)
        self.assertIn("Plan @ <sha court> - <objet>", out)
        self.assertIn("--kind decision", out)

    def test_control_a_non_canonical_title_that_is_not_an_approval_gets_no_decision_hint(self):
        """MUTANT MQ6."""
        self.repo("Planning @ <sha> - objet", ["b.txt"])
        rc, out = self.check()
        self.assertEqual(rc, 12, out)
        self.assertIn("Plan @ <sha court> - <objet>", out)
        self.assertNotIn("--kind decision", out)

    def test_an_empty_write_set_on_a_non_canonical_note_names_the_title_too(self):
        """MUTANT MQ4 et MQ9. WRITE_SET_ABSENT est prononcé AVANT SHA_ABSENT : 4 des 11 notes
        non canoniques en attente (T-110, 406, 414, 416) ne verraient jamais le message
        SHA_ABSENT — la précision doit donc porter la forme attendue elle-même."""
        self.repo("plan approuve T-00000001 — objet", [])
        rc, out = self.check()
        self.assertEqual(rc, 13, out)
        self.assertIn("write-set non clos", out)  # sous-chaîne d'origine conservée
        self.assertIn("titre aussi non canonique", out)
        self.assertIn("Plan @ <sha court> - <objet>", out)

    def test_control_an_empty_write_set_on_a_CANONICAL_title_says_nothing_about_the_title(self):
        """MUTANT MQ5."""
        self.repo("Plan @ <sha> - objet", [])
        rc, out = self.check()
        self.assertEqual(rc, 13, out)
        self.assertIn("write-set non clos", out)
        self.assertNotIn("non canonique", out)

    def _assert_printable(self, out):
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x9b", out)
        self.assertEqual([c for c in out if not c.isprintable() and c != "\n"], [], out)

    def test_a_note_title_with_control_characters_is_cited_without_them(self):
        """MUTANT MQ10 (assainisseur retiré) et MQ11 (court-circuité au site SHA_ABSENT) :
        le détail cite un titre de NOTE libre et `check` l'écrit sur un terminal —
        `\\x1b[2J` et `\\x9b` y deviennent des espaces ; la partie visible reste citée."""
        self.repo("plan approuve\x1b[2J\x9bT-00000001 — objet", ["b.txt"])
        rc, out = self.check()
        self.assertEqual(rc, 12, out)
        self.assertIn("titre du plan non canonique : plan approuve [2J T-00000001 — objet", out)
        self._assert_printable(out)

    def test_a_verdict_title_with_control_characters_is_cited_without_them(self):
        """MUTANT MQ10 et MQ12 (court-circuité au site PLAN_SANS_VERDICT) : même règle pour
        un titre de VERDICT hors grammaire."""
        self.repo("Plan @ <sha> - objet", ["b.txt"], "relecture\x1b[2J\x9bFINALE")
        rc, out = self.check()
        self.assertEqual(rc, 11, out)
        self.assertIn("hors grammaire : relecture [2J FINALE", out)
        self._assert_printable(out)


if __name__ == "__main__":
    unittest.main()
