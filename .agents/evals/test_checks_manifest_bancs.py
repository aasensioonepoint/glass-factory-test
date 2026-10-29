#!/usr/bin/env python3
"""CHAQUE BANC DU CONTRAT EST CITE PAR L'ENTREE `contract_diff` DU MANIFESTE.

CE QUE CE BANC FERME. `test_checks_manifest.py` rejoue les `implementation` et
les `bancs` de chaque check `actif` et refuse ceux qui sautent — mais il ne
rejoue QUE ce que le manifeste cite. Rien n'exigeait que l'entree
`contract_diff` cite ses bancs : sa ligne `bancs` retiree, la porte restait
verte (mesure du binome de T-00000798 : 39 passed), et `test_contract_index.py`
sortait en silence du balayage des sauts comme du futur script de release.

LA REGLE. Tout `.agents/evals/test_contract_*.py` SUIVI (`git ls-files -z`,
jamais le disque : un fichier non suivi n'est pas un banc du depot) figure dans
l'`implementation` ou dans les `bancs` de `contract_diff`. Un banc de contrat
neuf rougit ici tant qu'il n'est pas declare — c'est l'objet.

CE QU'IL NE PROUVE PAS : que le banc cite TOURNE sans sauter. C'est le travail
de `test_checks_manifest.py`, qui le fait des qu'il est cite.

VOYAGE. Ce fichier part avec `.agents/evals/` ; son sujet, `checks.manifest.json`,
est `strip:` (`.template-exclude`). Chez un adoptant le manifeste manque et ce
banc saute nommement, jamais en silence.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: sujet `strip:` (.template-exclude), saute nommement quand il manque.
MANIFESTE = ROOT / "checks.manifest.json"

ENTREE = "contract_diff"
BANC_DE_CONTRAT = re.compile(r"^\.agents/evals/test_contract_[^/]*\.py$")


def bancs_de_contrat_suivis() -> list[str]:
    """Les `.agents/evals/test_contract_*.py` suivis, filtres par regex : le
    `*` d'un pathspec git traverse les `/`, celui-ci non."""
    sortie = subprocess.run(
        ["git", "ls-files", "-z", "--", ".agents/evals"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(p for p in sortie.split("\0") if BANC_DE_CONTRAT.match(p))


def cites_par_l_entree(manifeste: dict) -> set[str]:
    entrees = [c for c in manifeste.get("checks", []) if c.get("nom") == ENTREE]
    if len(entrees) != 1:
        raise AssertionError(
            f"entree `{ENTREE}` du manifeste : {len(entrees)} trouvee(s), une attendue")
    entree = entrees[0]
    bancs = entree.get("bancs") or []
    if not isinstance(bancs, list):
        raise AssertionError(f"`bancs` de `{ENTREE}` : une LISTE, jamais une chaine")
    return {entree.get("implementation") or "", *bancs} - {""}


class BancsDuContratCitesTests(unittest.TestCase):
    """Les bancs du contrat, lus dans l'arbre suivi, contre l'entree
    `contract_diff` du manifeste."""

    @classmethod
    def setUpClass(cls):
        if not MANIFESTE.is_file():
            raise unittest.SkipTest(
                "arbre d'adoptant : checks.manifest.json est `strip:`, ce banc n'a "
                "pas de sujet ici")
        cls.suivis = bancs_de_contrat_suivis()
        cls.cites = cites_par_l_entree(json.loads(MANIFESTE.read_text(encoding="utf-8")))

    def test_la_lecture_mord(self):
        """Non-vacuite : au moins le banc `implementation` est trouve suivi, et
        l'entree cite au moins un chemin."""
        self.assertTrue(self.suivis, "aucun test_contract_*.py suivi : la lecture ne mord plus")
        self.assertTrue(self.cites, f"`{ENTREE}` ne cite aucun banc")

    def test_chaque_banc_de_contrat_suivi_est_cite_par_contract_diff(self):
        oublies = [p for p in self.suivis if p not in self.cites]
        self.assertEqual(
            [], oublies,
            f"banc(s) de contrat suivi(s) absent(s) de `{ENTREE}` (`implementation` "
            "ou `bancs`) dans checks.manifest.json : test_checks_manifest.py ne les "
            "rejoue pas et ne verra jamais qu'ils sautent")


if __name__ == "__main__":
    unittest.main()
