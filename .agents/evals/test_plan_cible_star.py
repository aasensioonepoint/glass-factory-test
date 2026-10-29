#!/usr/bin/env python3
"""`chantier=*` — LE JOKER DE LA CIBLE DE PLAN, ET LUI SEUL.

Run: python -m pytest .agents/evals/test_plan_cible_star.py -q

La graine que la sync template pose chez l'adoptant porte `chantier=*` : toute
tâche PRÉSENTE au board, AVEC OU SANS chantier, est sous la garde de cible — sur
ses trois morsures (`start` avec trace d'approbation, `done`, verdict
`plan-critic`) et sur les jambes ARÊTES qui passent par le même lecteur
(`plan_cible._arme_pour_tache`). Tout autre nom reste une ÉGALITÉ EXACTE : ni
préfixe, ni motif. Sous `*`, l'avertissement « chantier fantôme » se tait sur
les deux chemins (`tasks.py` et `specs.py`) — sa prémisse est fausse par
construction — et la règle d'emprunt R2 est inchangée : le plan du slot doit
NOMMER la tâche.

UN MODULE NEUF, PAS UN AMENDEMENT : `test_plan_cible_guard.py` reste intact et
tient le régime à nom exact ; ce module en hérite l'outillage (`_BaseDone`, un
board jetable par test) et voyage avec lui.

Chaque témoin nomme, en commentaire, le mutant qu'il tue ; chaque mutant a été
rejoué sur une copie jetable de `plan_cible.py` et l'a rendu rouge.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_plan_cible_guard as G  # noqa: E402 — a besoin du chemin inséré ci-dessus

# Identifiant ASSEMBLÉ : la décision que les plans de banc citent comme cible.
DEC = "S-%08d" % 1558
ABSENTE = "T-%08d" % 9999


class StarTests(G._BaseDone):

    def specs_cli(self, *args, timeout=120):
        return subprocess.run([sys.executable, str(G.SPECS), "--root", str(self.d), *args],
                              capture_output=True, text=True, timeout=timeout)

    def verdict(self, tid, plan_rel):
        return self.specs_cli("add", "plan-critic it.1 : GO", "--task", tid,
                              "--kind", "verdict", "--text", f"plan={plan_rel}")

    # -- `*` mord les DEUX moitiés : sans chantier, et avec -------------------

    def test_W9_star_bites_a_task_with_no_chantier_at_done(self):
        # kills M0 (no `*`), M10 (`*` compared literally), MC (`*` = with chantier only)
        tid = self.new(chantier=None)
        self.armer(chantier="*")
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("aucun plan approuvé", r.stderr)

    def test_W9e_star_bites_a_task_WITH_a_named_chantier(self):
        # kills MB (`*` = tasks WITHOUT chantier only)
        tid = self.new(chantier="x")
        self.armer(chantier="*")
        r = self.done(tid)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("aucun plan approuvé", r.stderr)

    def test_W9f_star_leaves_a_task_ABSENT_from_the_board_inert(self):
        # kills MA (`*` arming a task the board does not carry)
        self.new(chantier=None)
        self.armer(chantier="*")
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=ABSENTE))
        r = self.verdict(ABSENTE, "plans/incomplet.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_W9b_a_bare_done_under_star_needs_exactly_sans_cible(self):
        # the exit is `--sans-cible`, VISIBLE on the board — never `--sans-dependances`
        tid = self.new(chantier=None)
        self.armer(chantier="*")
        r = self.done(tid, "--sans-cible", "banc")
        self.assertEqual(r.returncode, 0, r.stderr)
        stage = self.board_stage(tid)
        self.assertIn("[SANS CIBLE : banc]", stage)
        self.assertNotIn("[SANS DÉPENDANCES", stage)

    # -- les trois jambes de la cible, et les ARÊTES --------------------------

    def test_W9c_the_verdict_leg_bites_under_star_and_a_named_marker_stays_exact(self):
        # kills M0, M10, M12 (every chantier treated as a joker)
        tid = self.new(chantier=None)
        self.armer(chantier="*")
        self.ecrire_specs([self.decision(DEC, tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        r = self.verdict(tid, "plans/incomplet.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("étape deux SANS cible", r.stderr)
        # contrôle : le MÊME verdict, tâche d'un AUTRE chantier, marqueur NOMMÉ → inerte
        t2 = self.new(chantier="autre")
        self.armer(chantier=self.CHANTIER)
        self.ecrire_specs([self.decision(DEC, t2)])
        self.ecrire_plan("plans/incomplet2.md", self.PLAN_INCOMPLET.format(tid=t2))
        r2 = self.verdict(t2, "plans/incomplet2.md")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_W9d_the_cible_start_leg_bites_under_star_with_an_approval_trace(self):
        # kills M0
        tid = self.new(chantier=None)
        sha = self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        self.ecrire_specs([self.decision(DEC, tid),
                           self.trace_approuve("S-%08d" % 2000, tid, "plans/incomplet.md", sha)])
        self.armer(chantier="*")
        r = self.tasks("start", tid)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("étape deux SANS cible", r.stderr)

    def test_W12_the_aretes_start_leg_bites_under_star(self):
        # kills M0: the ARÊTES legs read the same regime
        aval = self.new(chantier=None)
        amont = self.new(chantier=None)
        plan = (f"# Plan\nTâches : {aval}\nARÊTE: {aval} <- {amont} | technique : banc\n"
                f"## Steps\n1. une\n   décision pilote: {DEC}\n")
        sha = self.ecrire_plan("plans/p.md", plan)
        self.ecrire_specs([self.decision(DEC, aval),
                           self.trace("S-%08d" % 2000, aval, "plans/p.md", sha)])
        self.armer(chantier="*")
        r = self.tasks("start", aval)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("depends", r.stderr)

    # -- l'avertissement de chantier fantôme se tait, sur les DEUX chemins ----

    def test_W10_star_is_mute_on_the_phantom_warning_and_the_control_is_not_vacuous(self):
        # kills M11 (the warning not short-circuited under `*`)
        tid = self.new(chantier=None)
        self.armer(chantier="*")
        r = self.done(tid)  # refusé : la jambe MORD, l'avertissement s'imprimerait
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("ne nomme AUCUNE tâche", r.stderr)
        # contrôle : un chantier NOMMÉ qui ne désigne aucune tâche AVERTIT, même chemin
        tid2 = self.new(chantier=None)
        self.armer(chantier="fantome")
        r2 = self.done(tid2)
        self.assertIn("ne nomme AUCUNE tâche", r2.stderr)

    def test_W10b_star_is_mute_on_the_specs_verdict_path_too(self):
        # kills MD (`*` muted on the `tasks.py` path only) and M11
        tid = self.new(chantier=None)
        self.armer(chantier="*")
        self.ecrire_specs([self.decision(DEC, tid)])
        self.ecrire_plan("plans/incomplet.md", self.PLAN_INCOMPLET.format(tid=tid))
        r = self.verdict(tid, "plans/incomplet.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # la jambe mord…
        self.assertNotIn("ne nomme AUCUNE tâche", r.stderr)     # … et se tait

    # -- tout autre nom : égalité EXACTE ---------------------------------------

    def test_W11_a_named_marker_leaves_a_task_of_another_chantier_inert(self):
        # kills M12
        tid = self.new(chantier="autre-chantier")
        self.armer(chantier=self.CHANTIER)
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_W11b_a_named_marker_leaves_a_task_without_chantier_inert(self):
        # kills M12
        tid = self.new(chantier=None)
        self.armer(chantier=self.CHANTIER)
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_W11c_a_marker_naming_a_star_suffixed_chantier_is_no_pattern(self):
        # kills M12 and M13 (`rstrip("*")` + `startswith`)
        tid = self.new(chantier="ab")
        self.armer(chantier="a*")
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_W11d_a_marker_naming_a_plain_chantier_is_no_prefix(self):
        # kills M13b (a plain `startswith`)
        tid = self.new(chantier="ab")
        self.armer(chantier="a")
        r = self.done(tid)
        self.assertEqual(r.returncode, 0, r.stderr)

    # -- R2 : l'emprunt reste conditionné par l'enrôlement ---------------------

    def test_R2_the_borrow_under_star_still_requires_the_enrolling_line(self):
        # kills M0
        sub = self.new(chantier=None)
        slot = self.new(chantier=None)
        sha = self.ecrire_plan("plans/slot_enrole.md", self.PLAN_SLOT_ENROLE.format(sub=sub))
        self.ecrire_specs([self.decision(DEC, sub),
                           self.trace("S-%08d" % 2000, slot, "plans/slot_enrole.md", sha)])
        self.armer(chantier="*")
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"[cible relevée sur {slot} : slot_enrole.md (S-%08d)]" % 2000,
                      self.board_stage(sub))

    def test_R2b_a_slot_plan_that_does_not_name_the_task_is_refused_under_star(self):
        # kills M0. DEC est tracée sur le SLOT (décision pilote S-00004057, T-00000909) :
        # tracée sur `sub`, que ce plan n'enrôle pas, elle ne serait pas pertinente pour
        # le slot (sans chantier) et refuserait déjà son `start`. Le refus du `done` doit
        # venir du NON-ENRÔLEMENT de `sub`, et l'assertion le dit.
        sub = self.new(chantier=None)
        slot = self.new(chantier=None)
        sha = self.ecrire_plan("plans/slot_autre.md", self.PLAN_SLOT_AUTRE)
        self.ecrire_specs([self.decision(DEC, slot),
                           self.trace("S-%08d" % 2000, slot, "plans/slot_autre.md", sha)])
        self.armer(chantier="*")
        self.assertEqual(self.tasks("start", slot).returncode, 0)
        r = self.done(sub)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"n'enrôle pas {sub}", r.stderr)


if __name__ == "__main__":
    unittest.main()
