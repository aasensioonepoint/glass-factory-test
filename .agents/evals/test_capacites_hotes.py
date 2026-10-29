#!/usr/bin/env python3
"""LA TABLE DES CAPACITES PAR HOTE TIENT SA PROPRE REGLE (CONTRAT-v0.md, section 3.10).

CE QUE CE BANC FERME. `src/cadre/data/capacites_hotes.json` porte, hote par
hote, un `niveau` (`enforce` ou `assiste`) ET la cellule qui le justifie. Rien
n'empechait d'editer le niveau seul : `codex.niveau` passe a `enforce`, la table
restait un JSON valide et aucun test ne rougissait. La regle du contrat (« un
hote ne change de niveau que par une mesure nouvelle, inscrite dans la cellule
qui la porte ») n'etait tenue que par la relecture.

LA REGLE, telle que la table l'ecrit (`regle_de_classement`) : un hote est
`enforce` si et seulement si sa capacite decisive est `mesure` de portee
`bout-en-bout` ; tout autre cas le classe `sinon` (`assiste`). Trois temoins :
  1. le niveau de chaque hote se RECALCULE depuis sa cellule decisive ;
  2. chaque cellule reste dans les vocabulaires fermes de la table (capacites,
     statuts, portees) — une portee si et seulement si le statut est `mesure` —
     et porte au moins une source `chemin:ligne` ;
  3. la colonne `activable` egale la liste fermee `HOTES` du noyau
     (`src/cadre/config.py`), lue par l'arbre syntaxique, sans import.

CE QU'IL NE PROUVE PAS : qu'une source DISE ce que la cellule affirme, ni
qu'une cellule `mesure` le soit vraiment. Le banc juge la coherence de la table,
jamais la verite d'une mesure — celle-ci reste a la revue.

VOYAGE. Ce fichier part avec `.agents/evals/`, et son sujet aussi : aucune
regle `strip:` de `.template-exclude` ne retire `src/cadre/`. Si la table ou
`config.py` manque, le test saute EN LE DISANT, jamais en silence.

OU VIT LE PAQUET (T-01M5BXTPQE, lot F). `src/cadre/` nomme le paquet `cadre`
ou qu'il vive : son dossier est celui que rend `vendor_paths.dossier_paquet`
(`.agents/vendor/cadre` d'abord, `src/cadre` ensuite), charge par chemin. Le
temoin `test_vendor_seul_f` rejoue ce banc dans un kit jetable qui ne porte
le paquet que sous `.agents/vendor/cadre` et y exige ZERO saut : un chemin en
dur vers `src/cadre` y sauterait les trois tests, un faux vert.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_capacites_hotes_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
PAQUET = _VENDOR.dossier_paquet(ROOT, "cadre")
TABLE = None if PAQUET is None else PAQUET / "data" / "capacites_hotes.json"
CONFIG = None if PAQUET is None else PAQUET / "config.py"

# Une source est `chemin:ligne` ou `chemin:debut-fin` ; le chemin n'a ni blanc
# ni deux-points. Le numero vaut au sha du releve de la table.
SOURCE = re.compile(r"^[^\s:]+:\d+(?:-\d+)?$")


def hotes_du_noyau(source: str) -> tuple[str, ...] | None:
    """La valeur de `HOTES = (...)` au niveau module, ou None si absente."""
    for noeud in ast.parse(source).body:
        if (
            isinstance(noeud, ast.Assign)
            and len(noeud.targets) == 1
            and isinstance(noeud.targets[0], ast.Name)
            and noeud.targets[0].id == "HOTES"
        ):
            return tuple(ast.literal_eval(noeud.value))
    return None


class CapacitesHotesTests(unittest.TestCase):
    def setUp(self) -> None:
        if TABLE is None or not TABLE.is_file():
            self.skipTest(
                "SAUT ANNONCE : capacites_hotes.json absent du paquet cadre "
                "(ni .agents/vendor/cadre ni src/cadre) — "
                "la regle de la section 3.10 n'est PAS mesuree ici")
        self.d = json.loads(TABLE.read_text(encoding="utf-8"))

    def test_le_niveau_derive_de_la_cellule_decisive(self) -> None:
        regle = self.d["regle_de_classement"]
        self.assertIn(regle["capacite"], self.d["capacites"])
        self.assertIn("enforce", self.d["niveaux"])
        self.assertIn(regle["sinon"], self.d["niveaux"])
        decisives = [c for c, v in self.d["capacites"].items() if v["decide_le_niveau"]]
        self.assertEqual(
            decisives, [regle["capacite"]],
            "une seule capacite decide du niveau : celle de regle_de_classement")
        for hote, ligne in self.d["hotes"].items():
            with self.subTest(hote=hote):
                cellule = ligne["capacites"][regle["capacite"]]
                calcule = (
                    "enforce"
                    if all(cellule.get(k) == x for k, x in regle["enforce_si"].items())
                    else regle["sinon"])
                self.assertEqual(
                    ligne["niveau"], calcule,
                    f"{hote} : niveau edite sans la cellule {regle['capacite']} qui le justifie")

    def test_chaque_cellule_reste_dans_les_vocabulaires_fermes(self) -> None:
        capacites = set(self.d["capacites"])
        statuts = set(self.d["statuts"])
        portees = set(self.d["portees"])
        for hote, ligne in self.d["hotes"].items():
            with self.subTest(hote=hote):
                self.assertIn(ligne["niveau"], self.d["niveaux"])
                self.assertEqual(
                    set(ligne["capacites"]), capacites,
                    f"{hote} : capacites differentes de la liste bornee")
            for nom, cellule in ligne["capacites"].items():
                with self.subTest(hote=hote, capacite=nom):
                    self.assertIn(cellule["statut"], statuts)
                    self.assertEqual(
                        "portee" in cellule, cellule["statut"] == "mesure",
                        "une portee si et seulement si la cellule est `mesure`")
                    if "portee" in cellule:
                        self.assertIn(cellule["portee"], portees)
                    self.assertIsInstance(cellule["source"], list)
                    self.assertTrue(cellule["source"], "cellule sans source")
                    for source in cellule["source"]:
                        self.assertRegex(source, SOURCE)

    def test_activable_egale_la_liste_fermee_HOTES(self) -> None:
        if CONFIG is None or not CONFIG.is_file():
            self.skipTest(
                "SAUT ANNONCE : config.py absent du paquet cadre — la colonne activable "
                "n'est PAS confrontee a HOTES ici")
        hotes = hotes_du_noyau(CONFIG.read_text(encoding="utf-8"))
        self.assertIsNotNone(hotes, f"HOTES introuvable au niveau module de {CONFIG}")
        activables = {h for h, ligne in self.d["hotes"].items() if ligne["activable"]}
        self.assertEqual(activables, set(hotes))


class VendorSeulTests(unittest.TestCase):
    def test_vendor_seul_f(self) -> None:
        """Kit jetable « vendor seul » : le paquet sous `.agents/vendor/cadre`
        SEUL ; les trois tests du banc y passent, ZERO saut."""
        if PAQUET is None:
            self.skipTest("SAUT ANNONCE : paquet cadre absent de cette racine — "
                          "le temoin vendor seul n'a rien a copier")
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "kit"
            evals = kit / ".agents" / "evals"
            evals.mkdir(parents=True)
            shutil.copyfile(__file__, evals / "test_capacites_hotes.py")
            (kit / ".agents" / "bin").mkdir()
            shutil.copyfile(ROOT / ".agents" / "bin" / "vendor_paths.py",
                            kit / ".agents" / "bin" / "vendor_paths.py")
            paquet = kit / ".agents" / "vendor" / "cadre"
            (paquet / "data").mkdir(parents=True)
            (paquet / "__init__.py").write_text("", encoding="utf-8")
            source = _VENDOR.exiger(ROOT, "cadre")
            shutil.copyfile(source / "config.py", paquet / "config.py")
            shutil.copyfile(source / "data" / "capacites_hotes.json",
                            paquet / "data" / "capacites_hotes.json")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            r = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "-v",
                 "test_capacites_hotes.CapacitesHotesTests"],
                cwd=str(evals), env=env, capture_output=True, text=True,
                timeout=120, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Ran 3 tests", r.stderr)
        self.assertNotIn("skipped", r.stderr, f"saut en vendor seul :\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()
