"""Les deux miroirs de /specs-sync portent la même consigne de codes de sortie (T-00001059).

Les phrases-clés vivent dans `doctrine_registre.py`, règle `REGLE` ci-dessous, et nulle part
ici (T-01M4V7R89VZ5SP3NXZ32SNNDZ2) : `test_doctrine_registre.py` (4d) refuse une phrase
recopiée en constante. Les MEMBRES des surfaces restent épinglés ici, les phrases ont un
plancher.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import doctrine_registre as R  # noqa: E402

REGLE = "specs-sync-codes-sortie"
SKILL = ROOT / ".agents" / "skills" / "specs-sync" / "SKILL.md"
COMMANDE = ROOT / ".claude" / "commands" / "specs-sync.md"
SURFACES = tuple(ROOT / rel for rel in R.chemins(REGLE, "miroirs"))
PHRASES = R.jetons(REGLE, "miroirs")


class MiroirsSpecsSyncTests(unittest.TestCase):
    def test_les_deux_miroirs_portent_les_memes_phrases_cles(self) -> None:
        for chemin in SURFACES:
            self.assertTrue(chemin.is_file(), chemin)
            texte = chemin.read_text(encoding="utf-8")
            for phrase in PHRASES:
                self.assertIn(phrase, texte, f"{chemin.name} : {phrase!r}")

    def test_controle_negatif_surfaces_et_plancher(self) -> None:
        """Un balayage qui perd une surface ou une phrase passe à vide (L-00000232) : les
        MEMBRES sont épinglés (un compte laisserait substituer une surface à taille égale),
        les phrases ont un plancher (7 d'origine + 2 jetons d'arrêt de T-00001230)."""
        self.assertEqual(SURFACES, (SKILL, COMMANDE), "les miroirs ont changé au registre")
        self.assertGreaterEqual(len(PHRASES), 9, "le registre a perdu une phrase-clé")


if __name__ == "__main__":
    unittest.main()
