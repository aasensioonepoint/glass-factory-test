"""AUCUN CARACTÈRE INVISIBLE DANS CE QUE LES AGENTS LISENT COMME INSTRUCTION
(T-01M5BZBZ849P61Y6471JZMMPRD).

CE QU'IL TIENT. Les fichiers SUIVIS (`git ls-files`, jamais un parcours du disque) dont le
chemin tombe sous un motif de `PREFIXES` ou dans `FICHIERS` — défs d'agents des cinq hôtes,
commandes, skills, règles, workflows, `.agents/ref/`, instructions Copilot, doctrines
racine — passent `unicode_scan.scanner` sans constat ni erreur (allowlist du dépôt
appliquée). Le témoin plante U+2066 dans un dépôt git jetable sous trois motifs et hors
périmètre : seuls les trois du périmètre sortent, à la ligne et à la colonne justes.

CE QU'IL NE TIENT PAS — LES BORNES. Le périmètre est un ENSEMBLE DE MOTIFS, pas la fermeture
de ce que lisent les défs : `docs/tech/`, `docs/tasks/`, `.agents/vendor/cadre/data/roster/` et les
stores injectés de `.agents/state/` (ledger, index) ne sont PAS lus. Un fichier non suivi
n'est pas lu. Les homoglyphes ne sont pas repérés (borne de unicode_scan.py).

adopting-tree: le fichier VOYAGE ; le bras de l'arbre réel SAUTE NOMMÉMENT sans
`.agents/IS_THE_KIT` (seule son EXISTENCE est lue au chargement) ; le témoin jetable tourne
partout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: marque du kit (strip: .agents/IS_THE_KIT), seule son EXISTENCE est lue au chargement
_KIT = ROOT / ".agents" / "IS_THE_KIT"
sys.path.insert(0, str(ROOT / ".agents" / "security"))
import unicode_scan as us  # noqa: E402

PREFIXES = (
    ".claude/agents/", ".codex/agents/", ".github/agents/", ".gemini/agents/",
    ".kimi-code/agents/", ".claude/commands/", ".claude/skills/", ".claude/rules/",
    ".claude/workflows/", ".agents/skills/", ".agents/ref/", ".github/instructions/",
    ".github/skills/", "agents/", "commands/",
)
FICHIERS = frozenset(("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"))


def _git(racine: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", "-C", str(racine), *args], capture_output=True, check=True,
                          timeout=60, env=env).stdout


def surfaces(racine: Path) -> list[str]:
    noms = _git(racine, "ls-files", "-z").decode("utf-8").split("\0")
    return sorted(n for n in noms if n and (n.startswith(PREFIXES) or n in FICHIERS))


class SurfacesDuKit(unittest.TestCase):
    @unittest.skipUnless(_KIT.exists(), "adoptant : .agents/IS_THE_KIT absent, arbre réel non jugé")
    def test_aucune_surface_d_instruction_ne_porte_d_invisible(self):
        fichiers = surfaces(ROOT)
        self.assertIn("AGENTS.md", fichiers)
        self.assertTrue(any(f.startswith(".agents/ref/") for f in fichiers))
        sorties, erreurs = us.scanner(fichiers, ROOT)
        self.assertEqual(([], []), (sorties, erreurs))


class TemoinJetable(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp(prefix="unicode-surfaces-"))
        self.addCleanup(shutil.rmtree, self.racine, True)
        _git(self.racine, "init", "-q")

    def poser(self, rel: str, texte: str) -> None:
        chemin = self.racine / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(texte.encode("utf-8"))

    def test_seuls_les_motifs_du_perimetre_sortent(self):
        isolat = chr(0x2066)
        self.poser(".claude/agents/a.md", "ligne\nx" + isolat + "\n")
        self.poser(".agents/ref/b.md", isolat)
        self.poser("agents/c.md", "ab" + isolat)
        self.poser("AGENTS.md", "propre " + chr(0x26A0) + chr(0xFE0F) + "\n")
        self.poser("docs/tech/hors.md", isolat)
        self.poser("non-suivi.md", isolat)
        _git(self.racine, "add", "--", ".claude", ".agents", "agents", "AGENTS.md", "docs")
        fichiers = surfaces(self.racine)
        self.assertEqual([".agents/ref/b.md", ".claude/agents/a.md", "AGENTS.md", "agents/c.md"],
                         fichiers)
        sorties, erreurs = us.scanner(fichiers, self.racine)
        self.assertEqual([], erreurs)
        self.assertEqual([".agents/ref/b.md:1:1:U+2066:LEFT-TO-RIGHT ISOLATE",
                          ".claude/agents/a.md:2:2:U+2066:LEFT-TO-RIGHT ISOLATE",
                          "agents/c.md:1:3:U+2066:LEFT-TO-RIGHT ISOLATE"], sorties)


if __name__ == "__main__":
    unittest.main()
