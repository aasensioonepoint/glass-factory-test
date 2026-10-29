"""Chrono des plans préparés — `/planning` et `/planning-all` ouvrent le cycle (T-01M5HST80E30DFMV3S7WM68Q7N, lot D).

POURQUOI CE FICHIER EXISTE. Le tour de planification est la première étape mesurée
d'une tâche : `tasks.py chrono <T> begin` l'ouvre, `/kickoff` reprend ensuite le
cycle ouvert. Mais les quatre surfaces de planification (la liste PLANIFICATION de
`.agents/bin/test_plan_plafond.py`) bornent leurs écritures par une liste FERMÉE :
un appel qui n'y figure pas est un appel interdit, et un appel câblé sans y figurer
contredit sa propre garde. Le banc tient les deux bouts : la permission, dans la
tranche des écritures autorisées de chaque surface, et l'appel, dans le tour de
`/planning` (Étape 2) et dans la phase 3 de `planning-all`, avec ce que le tour
promet (idempotence, rc jamais bloquant, historique d'un autre poste incomplet).

Il ne juge que la DOCTRINE. Le verbe lui-même (lot B) a ses propres témoins.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAFOND = ROOT / ".agents" / "bin" / "test_plan_plafond.py"
PLANNING_SKILL = ".agents/skills/planning/SKILL.md"
PLANNING_CMD = ".claude/commands/planning.md"
PLANNING_ALL_SKILL = ".agents/skills/planning-all/SKILL.md"
PLANNING_ALL_CMD = ".claude/commands/planning-all.md"

BEGIN = "python .agents/bin/tasks.py chrono T-NNNNNNNN begin"
# La tranche des écritures autorisées de chaque surface : (début UNIQUE, fin, première après le début).
# Les fins de planning.md et planning-all.md sont les débuts des tranches que test_fournee_doctrine épingle :
# l'appel se pose AVANT elles, jamais dedans.
AUTORISEES: dict[str, tuple[str, str]] = {
    PLANNING_SKILL: ("Les **seules écritures autorisées**", "- Interdits :"),
    PLANNING_CMD: ("Les seules écritures autorisées", "Jamais d'agent de dev"),
    PLANNING_ALL_SKILL: ("1. **Le périmètre d'écriture.**", "2. **Le point d'arrêt.**"),
    PLANNING_ALL_CMD: ("5. **Écritures autorisées**", "**Rien d'autre.**"),
}
# Les deux tours qui ouvrent le cycle : (surface, début UNIQUE, fin).
TOURS: dict[str, tuple[str, str, str]] = {
    "planning": (PLANNING_SKILL, "## Étape 2 — Par tâche validée", "### Plan par lot"),
    "planning-all": (PLANNING_ALL_SKILL, "### Phase 3 — planifier, vague par vague", "### Phase 4"),
}
APRES_DEPS_READY = "une fois `deps-ready` admis, avant le premier `planner` du tour"
JOURNAL = "journal local du chrono sous la racine commune, ni board ni code"
IDEMPOTENT = "`begin` est idempotent"
SANS_SECOND_CYCLE = "ne rouvre jamais un second cycle, il reprend le cycle ouvert"
NON_BLOQUANT = "Un rc non nul de `chrono` ne bloque jamais le tour : le plan continue et le rapport dit le rc."
AUTRE_POSTE = ("Un historique venu d'un autre poste n'est pas au journal local : ses étapes restent inconnues, "
               "`chrono show` signale le cycle incomplet et ne donne aucun écart total.")
# Depuis T-01M5KKFBCXXEVYR8GJPYFEH3C8, start et fournee ouvrent le cycle eux aussi : la doctrine le dit.
NI_START = "`tasks.py start` et `tasks.py fournee` l'ouvrent aussi s'il ne l'est pas"
# planning/SKILL.md:139, la commande du verdict, cité par le plan : aucune ligne insérée avant elle.
LIGNE_139 = 'python .agents/bin/specs.py add "plan-critic <VERDICT>" --task T-NNNNNNNN --kind verdict'


def _normalise(texte: str) -> str:
    return " ".join(texte.split())


def _texte(rel: str) -> str:
    return _normalise((ROOT / rel).read_text(encoding="utf-8"))


def _tranche(rel: str, debut: str, fin: str) -> str:
    texte = _texte(rel)
    debut, fin = _normalise(debut), _normalise(fin)
    assert texte.count(debut) == 1, f"{rel} : début de tranche non unique ou absent : {debut!r}"
    i = texte.index(debut)
    j = texte.find(fin, i + len(debut))
    assert j != -1, f"{rel} : fin de tranche absente après le début : {fin!r}"
    return texte[i:j]


def _planification() -> tuple[str, ...]:
    """La liste PLANIFICATION de test_plan_plafond.py, lue sans importer le banc."""
    arbre = ast.parse(PLAFOND.read_text(encoding="utf-8"))
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "PLANIFICATION" for c in noeud.targets):
            return tuple(ast.literal_eval(noeud.value))
    raise AssertionError("PLANIFICATION absente de test_plan_plafond.py")


class ChronoPlanningTests(unittest.TestCase):

    def test_the_four_surfaces_are_the_planification_list(self):
        # kills « surface ajoutée ou retirée de PLANIFICATION sans que ce banc la lise »
        self.assertEqual(set(_planification()), set(AUTORISEES))
        self.assertEqual(len(AUTORISEES), 4)

    def test_each_surface_allows_begin_in_its_allowed_writes(self):
        # kills « `tasks.py chrono … begin` retiré des écritures autorisées d'UNE surface » and « appel posé
        # après la fin de la tranche » (dans la tranche épinglée par test_fournee_doctrine ou hors de la liste)
        for rel, (debut, fin) in AUTORISEES.items():
            with self.subTest(surface=rel):
                self.assertIn(BEGIN, _tranche(rel, debut, fin))

    def test_the_planning_turn_and_phase_3_open_the_cycle(self):
        # kills « appel retiré de l'Étape 2 de /planning » and « appel retiré de la phase 3 de planning-all »
        for tour, (rel, debut, fin) in TOURS.items():
            section = _tranche(rel, debut, fin)
            with self.subTest(tour=tour):
                self.assertIn(BEGIN, section)
                self.assertIn(APRES_DEPS_READY, section)
                self.assertIn(JOURNAL, section)

    def test_begin_is_idempotent_on_both_turns(self):
        # kills « idempotence tue sur un tour » : une révision rouvrirait un cycle et doublerait la mesure
        for tour, (rel, debut, fin) in TOURS.items():
            section = _tranche(rel, debut, fin)
            with self.subTest(tour=tour):
                self.assertIn(IDEMPOTENT, section)
                self.assertIn(SANS_SECOND_CYCLE, section)
        # /planning et /planning-all ouvrent ; `tasks.py start` et `fournee` l'ouvrent aussi s'il ne l'est pas
        self.assertIn(NI_START, _tranche(*TOURS["planning"]))

    def test_a_non_zero_chrono_rc_never_blocks_the_turn(self):
        # kills « rc de chrono devenu bloquant » (réserve C28 du plan-critic 6/8)
        for tour, (rel, debut, fin) in TOURS.items():
            with self.subTest(tour=tour):
                self.assertIn(_normalise(NON_BLOQUANT), _tranche(rel, debut, fin))

    def test_another_station_history_is_reported_incomplete(self):
        # kills « historique d'un autre poste lu comme complet » (un écart total faux)
        for tour, (rel, debut, fin) in TOURS.items():
            with self.subTest(tour=tour):
                self.assertIn(_normalise(AUTRE_POSTE), _tranche(rel, debut, fin))

    def test_planning_skill_line_139_is_still_the_verdict_command(self):
        # kills « ligne insérée avant planning/SKILL.md:139 » (repère cité par le plan)
        lignes = (ROOT / PLANNING_SKILL).read_text(encoding="utf-8").splitlines()
        self.assertTrue(lignes[138].startswith(LIGNE_139), lignes[138])


if __name__ == "__main__":
    unittest.main()
