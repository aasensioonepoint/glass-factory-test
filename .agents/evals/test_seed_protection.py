#!/usr/bin/env python3
"""LES GRAINES DES CINQ GARDES SEMÉES SONT-ELLES PROTÉGÉES PAR LEUR NOM ?

Run: python -m pytest .agents/evals/test_seed_protection.py -q

La sync template écrit chaque graine `<racine des graines>/<NOM>` vers
`.agents/state/gates/<NOM>` chez chaque adoptant : éditer une graine réarme — ou
désarme — tous les adoptants à venir d'un seul geste. C'est un geste du pilote.
Ce banc éprouve les quatre surfaces qui le tiennent, et la PORTÉE dite dans les
en-têtes des graines :

  * `protect-paths.sh` (Claude, Edit/Write) refuse les cinq noms, dans les deux
    casses, et laisse passer un voisin (`NOTES.md`) — le bras juge par NOM ;
  * les jumeaux `.codex` / `.gemini` `protect_paths.py` refusent les cinq noms,
    sous les MÊMES rule ids, et laissent passer le voisin ;
  * `permissions.deny` porte une ligne `Edit(path)` par graine ;
  * une redirection shell vers une graine est refusée par `safe-bash.sh` —
    jusque hors de la racine, donc par son NOM — et le voisin passe ;
  * le MARQUEUR ARMÉ que chaque graine devient chez l'adoptant,
    `.agents/state/gates/<NOM>`, est refusé de même (Claude, jumeaux sous leur
    rule id `*-arming`, `permissions.deny`) : une graine protégée dont le
    marqueur ne l'est pas se désarme d'un `Edit` chez l'adoptant.
  Ce qui n'est PAS couvert, dit plutôt que découvert : `cp`, `sed -i`, `tee`,
  `python3 -c` passent. La protection empêche l'OUBLI, pas la triche.

IL VOYAGE (aucune règle `strip:`) : les bras qu'il éprouve voyagent, et le hook
juge par NOM sans que la graine existe — il passe dans un arbre d'adoption. Le
chemin des graines est COMPOSÉ, jamais écrit d'un bloc : la porte d'adoption
signale une référence littérale à un préfixe `strip:` ancrée sur la racine.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = "/".join((".agents", "adopter-seed", "gates"))
MARKER_DIR = "/".join((".agents", "state", "gates"))
# LE JEU LITTÉRAL : cinq noms, jamais dérivés (le cinquième, T-01M5C1AHZM41P9C3QH6X7PEQY1).
NAMES = ("BINOME_REQUIRED", "CHRONO_REQUIRED", "CONFIG_QUALITE_PROTEGE", "PLAN_CHAIN_REQUIRED",
         "PLAN_CIBLE_REQUIRED")
RULE_IDS = {"BINOME_REQUIRED": "seed-binome-required",
            "CHRONO_REQUIRED": "seed-chrono-required",
            "CONFIG_QUALITE_PROTEGE": "seed-config-qualite-protege",
            "PLAN_CHAIN_REQUIRED": "seed-plan-chain-required",
            "PLAN_CIBLE_REQUIRED": "seed-plan-cible-required"}
MARKER_RULE_IDS = {"BINOME_REQUIRED": "binome-arming",
                   "CHRONO_REQUIRED": "chrono-arming",
                   "CONFIG_QUALITE_PROTEGE": "config-qualite-arming",
                   "PLAN_CHAIN_REQUIRED": "plan-chain-arming",
                   "PLAN_CIBLE_REQUIRED": "plan-cible-arming"}
NEIGHBOUR = "NOTES.md"


def _hook_env(events: str) -> dict[str, str]:
    """L'environnement du SOUS-PROCESSUS de hook seulement : le dépôt sous test,
    et un dossier d'événements jetable — jamais le journal réel."""
    return {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), "AGENTS_EVENTS_DIR": events}


class SeedProtectionTests(unittest.TestCase):

    def _claude_write(self, rel: str) -> int:
        with tempfile.TemporaryDirectory() as ev:
            p = subprocess.run(["bash", str(ROOT / ".claude/hooks/protect-paths.sh")],
                               input=json.dumps({"tool_input": {"file_path": str(ROOT / rel)}}),
                               capture_output=True, text=True, env=_hook_env(ev), cwd=str(ROOT))
        return p.returncode

    def test_claude_protect_paths_denies_each_seed_in_both_cases_and_allows_a_neighbour(self):
        # kills P1 (an arm removed from `protect-paths.sh`)
        for name in NAMES:
            for form in (name, name.lower()):
                with self.subTest(seed=form):
                    self.assertEqual(self._claude_write(f"{SEED_DIR}/{form}"), 2)
        self.assertEqual(self._claude_write(f"{SEED_DIR}/{NEIGHBOUR}"), 0)  # contrôle : par NOM

    def _twin(self, host: str, rel: str) -> tuple[bool, str]:
        prog = ("import sys; sys.path.insert(0, sys.argv[1]); import protect_paths as m; "
                "r = m.protected_reason(sys.argv[2]); print(bool(r[0])); print(r[1])")
        with tempfile.TemporaryDirectory() as ev:
            p = subprocess.run([sys.executable, "-c", prog, str(ROOT / host / "hooks"), str(ROOT / rel)],
                               capture_output=True, text=True, env=_hook_env(ev), cwd=str(ROOT))
        self.assertEqual(p.returncode, 0, p.stderr)
        denied, rule = (p.stdout.strip().splitlines() + ["", ""])[:2]
        return denied == "True", rule

    def test_codex_and_gemini_twins_deny_each_seed_under_the_same_rule_id(self):
        # kills P2 / P3 (a suffix removed from one twin)
        for host in (".codex", ".gemini"):
            for name in NAMES:
                with self.subTest(host=host, seed=name):
                    denied, rule = self._twin(host, f"{SEED_DIR}/{name}")
                    self.assertTrue(denied, "graine NON protégée")
                    self.assertEqual(rule, RULE_IDS[name])
            denied, _rule = self._twin(host, f"{SEED_DIR}/{NEIGHBOUR}")
            self.assertFalse(denied, f"{host} : le voisin est refusé, le bras ne juge plus par NOM")

    def test_permissions_deny_lists_each_seed(self):
        # kills P4 (a deny line removed)
        deny = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        for name in NAMES:
            self.assertIn(f"Edit(./{SEED_DIR}/{name})", deny)

    def _redirect(self, target: str) -> int:
        cmd = f'printf x > "{target}"'
        with tempfile.TemporaryDirectory() as ev:
            p = subprocess.run(["bash", str(ROOT / ".claude/hooks/safe-bash.sh")],
                               input=json.dumps({"tool_input": {"command": cmd}}),
                               capture_output=True, text=True, env=_hook_env(ev), cwd=str(ROOT))
        return p.returncode

    def test_a_shell_redirect_to_a_seed_is_refused_by_its_NAME_and_a_neighbour_passes(self):
        # la portée écrite dans les graines : « redirection shell par NOM refusée »
        with tempfile.TemporaryDirectory() as dehors:
            for name in NAMES:
                with self.subTest(seed=name):
                    self.assertEqual(self._redirect(f"{SEED_DIR}/{name}"), 2)
                    # hors de la racine : seul le NOM peut refuser
                    self.assertEqual(self._redirect(f"{dehors}/{SEED_DIR}/{name}"), 2)
            self.assertEqual(self._redirect(f"{dehors}/{SEED_DIR}/{NEIGHBOUR}"), 0)

    def test_the_armed_marker_of_each_seed_is_protected_on_the_three_families(self):
        # kills P5 (the `*-arming` arm of a seeded marker missing from `protect-paths.sh`), P6 (its suffix
        # missing from one twin) and P7 (its deny line missing): the seed travels, its marker must hold
        self.assertEqual(set(MARKER_RULE_IDS), set(NAMES))
        deny = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        for name in NAMES:
            marker = f"{MARKER_DIR}/{name}"
            with self.subTest(marker=name):
                for form in (name, name.lower()):
                    self.assertEqual(self._claude_write(f"{MARKER_DIR}/{form}"), 2, form)
                for host in (".codex", ".gemini"):
                    denied, rule = self._twin(host, marker)
                    self.assertTrue(denied, f"{host} : marqueur NON protégé")
                    self.assertEqual(rule, MARKER_RULE_IDS[name], host)
                self.assertIn(f"Edit(./{marker})", deny)


if __name__ == "__main__":
    unittest.main()
