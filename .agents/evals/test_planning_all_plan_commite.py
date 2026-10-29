"""Témoin D5 de T-01M5T4NRDNZ0ESYGFR3154RRJM (lot Q) : /planning-all rend la
ligne de commit des plans AVANT `night_approve.py --apply`.

`night_approve.py` saute (condition 8, la DERNIÈRE évaluée) un plan absent de
HEAD ou modifié depuis HEAD. `/planning-all` ne commite jamais : son `--check`
de phase 4 voit donc chaque plan frais SAUTÉ par la condition 8. La phrase S3
(annexe § 8 du plan) le dit au pilote, et ouvre la ligne rendue par le commit.

Le banc exige S3, à l'octet, DANS le point 6 (entre « 6. » et « 7. ») de la
source `commands/planning-all.md` et de ses trois rendus, puis la parité du
point 6 entre la source et chaque rendu (un rendu non rejoué rougit).
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "commands" / "planning-all.md"
MIROIR = ROOT / ".agents" / "skills" / "source-command-planning-all" / "SKILL.md"
RENDUS = (
    ROOT / ".claude" / "commands" / "planning-all.md",
    ROOT / ".cursor" / "commands" / "planning-all.md",
    MIROIR,
)

S3 = (
    "**Un plan non commité sort SAUTÉ par la condition 8** (absent de HEAD, ou "
    "modifié depuis HEAD), la DERNIÈRE évaluée : sauté pour ce seul motif, il est "
    "approuvable une fois commité. La ligne rendue s'ouvre donc par "
    "`git add -- <plans>` puis "
    '`git commit -m "docs(tasks): plans T-… T-…" -- <plans>`, '
    "gestes du pilote — `/planning-all` ne commite rien."
)

DEBUT = "6. **Tu n'écris JAMAIS `night-eligible: approved`"
FIN = "7. **L'ordre des `--lot` n'ordonne pas la nuit**"


def point_6(path: Path) -> str:
    """Le point 6, borné par ses deux ancres ; une ancre absente rougit."""
    text = path.read_text(encoding="utf-8")
    debut = text.find(DEBUT)
    if debut < 0:
        raise AssertionError(f"{path} : ancre du point 6 absente")
    fin = text.find(FIN, debut)
    if fin < 0:
        raise AssertionError(f"{path} : ancre du point 7 absente après le point 6")
    return text[debut:fin]


def forme_hote(texte: str, rendu: Path) -> str:
    """Le miroir cross-hôte écrit `$planning-all` là où la source écrit
    `/planning-all` (convention `$name` des miroirs, mesurée au rendu)."""
    return texte.replace("`/planning-all`", "`$planning-all`") if rendu == MIROIR else texte


class PlanningAllPlanCommiteTests(unittest.TestCase):
    def test_s3_is_in_point_6_of_the_source(self) -> None:
        self.assertIn(S3, point_6(SOURCE), f"{SOURCE} : S3 absente du point 6")

    def test_s3_is_in_point_6_of_every_render(self) -> None:
        for rendu in RENDUS:
            with self.subTest(rendu=str(rendu.relative_to(ROOT))):
                self.assertIn(
                    forme_hote(S3, rendu), point_6(rendu), f"{rendu} : S3 absente du point 6"
                )

    def test_point_6_renders_match_the_source(self) -> None:
        attendu = point_6(SOURCE)
        for rendu in RENDUS:
            with self.subTest(rendu=str(rendu.relative_to(ROOT))):
                self.assertEqual(
                    point_6(rendu),
                    forme_hote(attendu, rendu),
                    f"{rendu} : point 6 différent de la source — rejouer render_hosts.py --ecrire",
                )


if __name__ == "__main__":
    unittest.main()
