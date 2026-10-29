"""Contrat de `planning-all` — ce qu'il promet, et ce qu'il ne recopie PAS (T-00000533).

POURQUOI CE FICHIER EXISTE. `planning-all` vit à côté de `/planning` et partage
son étape de planification. La tentation, en écrivant une seconde skill, est de
recopier le contrat de traçage « pour qu'elle soit autoportante ». C'est
exactement ce qu'il ne faut pas : deux copies d'un contrat DÉRIVENT, et comme
les deux voyagent chez l'adoptant, c'est lui qui hérite du désaccord.

Le banc asserte donc une ABSENCE autant qu'une présence — ce qui est inhabituel
et délibéré. Un test qui ne vérifierait que la présence des bonnes phrases
passerait au vert sur une skill qui a recopié tout `/planning`.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "planning-all" / "SKILL.md"
COMMAND = ROOT / ".claude" / "commands" / "planning-all.md"
PLANNING_SKILL = ROOT / ".agents" / "skills" / "planning" / "SKILL.md"

# Les DEUX surfaces, comme `test_night_contract.NIGHT_SURFACES` : une édition
# qui n'atterrit que sur l'une est la dérive que ce fichier attrape.
SURFACES = (SKILL, COMMAND)


class PlanningAllFormTests(unittest.TestCase):
    """La forme d'une skill — deux fautes la cachent EN SILENCE (AGENTS.md)."""

    def test_the_skill_is_at_depth_one_with_frontmatter_on_line_one(self) -> None:
        self.assertTrue(SKILL.is_file(), f"{SKILL} absent — une skill à profondeur 2 est INVISIBLE")
        first = SKILL.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(
            first, "---", "le frontmatter doit ouvrir en LIGNE 1, sinon la skill est ignorée"
        )

    def test_both_surfaces_exist(self) -> None:
        for path in SURFACES:
            self.assertTrue(path.is_file(), f"{path} absent")


class PlanningAllContractTests(unittest.TestCase):
    def test_the_tracing_contract_is_NOT_copied(self) -> None:
        """L'assertion porteuse : la skill RENVOIE à `/planning`, elle ne le
        recopie pas. Mesuré sur la ligne `specs.py add … --kind verdict`, qui est
        le cœur du contrat de traçage : elle doit apparaître dans `planning`, et
        JAMAIS dans `planning-all`."""
        verdict_line = re.compile(r"specs\.py add .*--kind verdict")
        self.assertRegex(
            PLANNING_SKILL.read_text(encoding="utf-8"),
            verdict_line,
            "le contrat de traçage a disparu de `planning` — ce banc mesure la mauvaise chose",
        )
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotRegex(
            text,
            verdict_line,
            "planning-all a RECOPIÉ le contrat de traçage : deux copies dérivent, "
            "et l'adoptant hérite du désaccord — renvoie à planning/SKILL.md § Étape 2",
        )
        self.assertIn(
            "planning/SKILL.md",
            text,
            "planning-all doit RENVOYER au contrat plutôt que de le redire",
        )

    def test_it_never_writes_the_night_contract_nor_applies(self) -> None:
        """L'invariant T-00000233, sur les deux surfaces : la porte est un geste
        du pilote. Un outil qui écrit son propre contrat est un agenda ouvert."""
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "night-eligible: approved",
                text,
                f"{path}: la skill doit NOMMER ce qu'elle n'écrit pas",
            )
            self.assertIn(
                "--check",
                text,
                f"{path}: la phase de vérification doit passer par --check, qui n'écrit rien",
            )
            self.assertRegex(
                text,
                r"jamais\s+`--apply`|ne lance jamais `--apply`|JAMAIS `--apply`",
                f"{path}: rien n'interdit explicitement de lancer --apply",
            )

    def test_the_closure_and_its_two_stops_are_stated(self) -> None:
        """La fermeture transitive est CE QUI REND le mode utile plutôt que
        descriptif ; et son expansion doit être annoncée AVANT le go, pas
        découverte à l'arrivée."""
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("depends_on", text, f"{path}: la fermeture n'est pas nommée")
            self.assertIn(
                "blocked",
                text,
                f"{path}: le mur — une dépendance blocked arrête la branche — n'est pas dit",
            )
            self.assertRegex(
                text,
                r"DEUX arrêts|deux fois|ARRÊT DUR",
                f"{path}: les deux points d'arrêt ne sont pas déclarés",
            )

    def test_the_specs_graph_is_a_candidate_generator_never_an_authority(self) -> None:
        """La leçon la plus chère du lot : une arête du graphe est une CITATION,
        et une citation peut vouloir dire l'inverse d'une dépendance. Le dépôt a
        déjà payé ce piège (LOT-3-plan.md cite T-00000209 pour dire qu'il ne le
        traite PAS)."""
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "CITATION",
                text.upper(),
                f"{path}: rien ne dit qu'une arête du graphe est une citation, pas une dépendance",
            )
            self.assertIn(
                "AMBIGU",
                text,
                f"{path}: le verdict AMBIGU — celui qu'on n'écrit JAMAIS — n'est pas nommé",
            )

    def test_the_lot_order_is_declared_NOT_to_order_the_night(self) -> None:
        """Le malentendu le plus coûteux du mécanisme : l'ordre des `--lot`
        n'ordonne rien, la nuit reconstruit le sien."""
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                r"n'ordonne (PAS|pas) la nuit",
                f"{path}: rien ne prévient que l'ordre des --lot ne commande rien",
            )


PLANNING_COMMAND = ROOT / ".claude" / "commands" / "planning.md"
#: Lettres accentuées du français : une description anglaise n'en porte aucune.
ACCENTS = re.compile(r"[éèêàâùûçîïôÉÈÊÀÇ]")


def _description(path: Path) -> str:
    """La ligne `description:` du frontmatter, telle que l'hôte l'affiche."""
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line == "---":
            break
        if line.startswith("description:"):
            return line
    raise AssertionError(f"{path}: aucune ligne description: dans le frontmatter")


class UsageAnglais(unittest.TestCase):
    """T-01M5QC86XN, lot C2 (décision pilote S-01M5S9NJN15HT7KVHZHZYM8DM8) : le nom
    anglais EN TÊTE, l'ancien nom français toujours accepté ET DIT."""

    PLANNING = (PLANNING_COMMAND, PLANNING_SKILL)
    PLANNING_ALL = (COMMAND, SKILL)

    def test_descriptions_are_in_english(self) -> None:
        for path in self.PLANNING + self.PLANNING_ALL:
            desc = _description(path)
            self.assertNotRegex(desc, ACCENTS, f"{path}: description encore en français : {desc}")

    def test_planning_usage_names_all_first(self) -> None:
        for path in self.PLANNING:
            desc = _description(path)
            self.assertIn("Usage — /planning [N|all]", desc, f"{path}: Usage sans `[N|all]`")
            self.assertNotIn("[N|tout]", desc, f"{path}: l'ancien Usage `[N|tout]` est revenu")
            self.assertIn(
                "the former tout and --tout are still accepted", desc,
                f"{path}: la description ne dit plus l'alias `tout`/`--tout`",
            )

    def test_planning_all_triggers_keep_the_french_alias(self) -> None:
        """Le mode « all » : `all`/`--all` en tête, `tout`/`--tout` toujours acceptés."""
        for path in self.PLANNING:
            text = " ".join(path.read_text(encoding="utf-8").split())  # le retour à la ligne ne compte pas
            self.assertTrue("`/planning all` (or `--all`)" in text, f"{path}: déclencheur anglais absent")
            self.assertTrue("`/planning tout` and `--tout`" in text, f"{path}: l'alias `tout` n'est plus dit")
            self.assertTrue("« planifie tout »" in text, f"{path}: la phrase française n'est plus acceptée")

    def test_planning_all_usage_names_workstream_first(self) -> None:
        for path in self.PLANNING_ALL:
            text = path.read_text(encoding="utf-8")
            self.assertTrue("/planning-all [T-NNN …|--workstream X]" in text, f"{path}: Usage sans --workstream")
            self.assertTrue("`--chantier X` still accepted" in text, f"{path}: l'alias --chantier n'est plus dit")
        self.assertNotIn("--chantier X]", _description(COMMAND), "l'ancien Usage `--chantier X` est revenu")


if __name__ == "__main__":
    unittest.main()
