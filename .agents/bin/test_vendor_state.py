#!/usr/bin/env python3
"""Témoin T-01M5BXTGX5YN8XEXTG1PP7A5ZX, phase E : L'ÉTAT DE CHARGE, LA PROJECTION ET
LA GARDE DE KICKOFF VOIENT `.agents/vendor/cadre` COMME L'ANCIEN `src/cadre`.

Run: python -m pytest .agents/bin/test_vendor_state.py -q

Chaque arbre est une copie JETABLE des seuls fichiers que `charge_poste.py` et
`etat_projection.py` chargent (mesuré : `etat_projection` lit quatre frères), plus
`cadre/__init__.py` et le VRAI `cadre/paths.py` du kit, posés selon la disposition.
Une sonde, processus neuf sous `-I` (ni `PYTHONPATH` ni site utilisateur), interdit
l'import de `cadre` (`sys.modules["cadre"] = None`) : seul le repli PAR CHEMIN répond,
c'est lui que la phase E déplace.

  E1 neuf seul       `.agents/vendor/cadre` sans `src/cadre` : `charge_poste` et
                     `etat_projection` chargent le `paths.py` vendor, l'état et la base
                     se placent sous `CADRE_STATE_DIR`. Rouge à la base (chemin figé).
  E2 les deux        le neuf gagne, comme le résolveur ; E3 ancien seul : `src/cadre`.
  E4 src/ adoptant   ancien arbre dont le `src/` porte `token.py` (sortie 95) : aucune
                     entrée de la racine n'est ajoutée à `sys.path`, `token` reste standard.
  E5 sans résolveur  `vendor_paths.py` absent : repli `src/cadre` d'avant ; sur l'arbre
                     neuf seul, refus DIT (avertissement, base `None`), jamais une trace.
  E6 kickoff_guard   `armed_by_class` classe chaque chemin vendor comme son ancien
                     (garde → armée ; hors garde → non armée). Union STATIQUE de
                     `tasks_direct.CHEMINS_GARDE` (phase C) : vert dès la base.
  E7 illisible       `vendor_paths.py` tronqué ou levant : repli `src/cadre` DIT sur stderr par les
                     deux modules (S-01M5CN1KBT), nom du résolveur retiré de `sys.modules`, ou son
                     entrée d'avant rendue (S-01M5CQ823N) ; PARTIEL (un nom de l'API manque) :
                     ABSENT, repli `src/cadre` muet, comme les quatre autres producteurs.

BORNES, DITES : la branche (1) « paquet `cadre` installé » n'est pas exercée ici (bloquée
par la sonde) ; `kickoff_guard.py` ne porte aucun chemin `src/cadre` en code — sa
classification passe par `tasks.est_chemin_de_garde`, dont la liste est jugée en phase C.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
#: Mesuré : les fichiers de `.agents/bin` présents dans `sys.modules` après le chargement des deux modules.
FICHIERS = ("charge_poste.py", "etat_projection.py", "vendor_paths.py", "dashboard_readers_base.py",
            "dashboard_transport.py", "ledger.py", "specs.py")
MASQUE = "STDLIB-MASQUEE"


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


VP = _charger("vendor_paths_banc_state", HERE / "vendor_paths.py")
PATHS_DU_KIT = VP.exiger(REPO, "cadre") / "paths.py"

_SONDE = r'''
import importlib.util, json, sys
from pathlib import Path
racine = Path(sys.argv[1]).resolve()
sys.modules["cadre"] = None  # aucun `cadre` installé ne répond : le repli par chemin seul
NOMS = ("_vendor_paths_charge_poste", "_vendor_paths_etat_projection")
if sys.argv[2:] == ["sentinelle"]:  # une entrée d'AVANT sous chaque nom de résolveur : rendue s'il lève
    import types
    for n in NOMS:
        sys.modules[n] = types.ModuleType("sentinelle")
avant = list(sys.path)
def charger(nom):
    spec = importlib.util.spec_from_file_location("sonde_" + nom, racine / ".agents" / "bin" / (nom + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod
cp, ep = charger("charge_poste"), charger("etat_projection")
etat, decl, avert = cp.emplacements()
try:
    proj = ep._cadre_paths().__file__
except Exception as exc:
    proj = "ERREUR " + type(exc).__name__
base = ep.chemin_base(racine)
ajouts = [e for e in sys.path if e not in avant]
sys.modules.pop("token", None)
import token
inscrits = [n for n in NOMS if n in sys.modules]
sentinelles = [n for n in NOMS if getattr(sys.modules.get(n), "__name__", None) == "sentinelle"]
print(json.dumps({"charge": getattr(cp._CADRE_PATHS, "__file__", None), "etat": etat and str(etat),
                  "decl": decl and str(decl), "avert": avert, "proj": proj, "base": base and str(base),
                  "ajouts": ajouts, "token": token.__file__, "inscrits": inscrits, "sentinelles": sentinelles}))
'''
#: Les deux modules dont le repli DIT un résolveur illisible (S-01M5CN1KBT), au format de `event_store`.
DISENT = ("charge_poste", "etat_projection")


class EtatTests(unittest.TestCase):
    """E1 à E5 : la sonde sur des arbres jetables, une disposition par cas."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="vendor_state_")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _arbre(self, nom: str, *, neuf: bool, ancien: bool, resolveur: bool = True) -> Path:
        racine = self.tmp / nom
        (racine / ".agents" / "bin").mkdir(parents=True)
        for fichier in FICHIERS:
            if resolveur or fichier != "vendor_paths.py":
                shutil.copy2(HERE / fichier, racine / ".agents" / "bin" / fichier)
        for present, dossier in ((neuf, racine / ".agents" / "vendor" / "cadre"), (ancien, racine / "src" / "cadre")):
            if present:
                dossier.mkdir(parents=True)
                (dossier / "__init__.py").write_text("", encoding="utf-8")
                shutil.copy2(PATHS_DU_KIT, dossier / "paths.py")
        return racine

    def _sonder(self, racine: Path, *mode: str) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("PYTHON", "PYTEST", "CADRE_")) and k != "AGENTS_ETAT_DB"}
        env.update(PYTHONDONTWRITEBYTECODE="1", CADRE_STATE_DIR=str(self.tmp / "state"),
                   CADRE_CONFIG_HOME=str(self.tmp / "config"), CADRE_PROJECT_ROOT=str(racine))
        out = subprocess.run([sys.executable, "-I", "-B", "-c", _SONDE, str(racine), *mode], cwd=self.tmp,
                             env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, out.returncode, f"sonde rc {out.returncode}\n{out.stdout}\n{out.stderr}")
        self.stderr = out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])

    def _place(self, racine: Path, attendu: Path) -> None:
        vu = self._sonder(racine)
        self.assertEqual(str(attendu / "paths.py"), vu["charge"], vu)
        self.assertEqual(str(attendu / "paths.py"), vu["proj"], vu)
        self.assertEqual(str(self.tmp / "state" / "charge_poste"), vu["etat"], vu)
        self.assertEqual(str(self.tmp / "config" / "parallelisme.json"), vu["decl"], vu)
        self.assertTrue(vu["base"] and vu["base"].startswith(str(self.tmp / "state") + os.sep), vu)
        self.assertTrue(vu["base"].endswith("etat.db"), vu)
        self.assertEqual([], vu["ajouts"], vu)

    def test_e1_neuf_seul(self) -> None:
        racine = self._arbre("neuf", neuf=True, ancien=False)
        self._place(racine, racine / ".agents" / "vendor" / "cadre")
        self.assertEqual(["_vendor_paths_charge_poste", "_vendor_paths_etat_projection"],
                         self._sonder(racine)["inscrits"], "résolveur lisible : inscrit dans sys.modules")

    def test_e2_les_deux_le_neuf_gagne(self) -> None:
        racine = self._arbre("deux", neuf=True, ancien=True)
        self._place(racine, racine / ".agents" / "vendor" / "cadre")

    def test_e3_ancien_seul(self) -> None:
        racine = self._arbre("ancien", neuf=False, ancien=True)
        self._place(racine, racine / "src" / "cadre")

    def test_e4_src_de_l_adoptant_ne_masque_pas_la_stdlib(self) -> None:
        racine = self._arbre("adoptant", neuf=False, ancien=True)
        (racine / "src" / "token.py").write_text(
            f"import sys\nsys.stderr.write({MASQUE!r})\nraise SystemExit(95)\n", encoding="utf-8")
        self._place(racine, racine / "src" / "cadre")
        self.assertNotIn(str(racine), self._sonder(racine)["token"])

    def test_e5_sans_resolveur(self) -> None:
        ancien = self._arbre("ancien_nu", neuf=False, ancien=True, resolveur=False)
        self._place(ancien, ancien / "src" / "cadre")
        neuf = self._arbre("neuf_nu", neuf=True, ancien=False, resolveur=False)
        vu = self._sonder(neuf)
        self.assertIsNone(vu["etat"], vu)
        self.assertIsNone(vu["base"], vu)
        self.assertTrue(any("paths.py" in a for a in vu["avert"]), vu)
        self.assertNotIn("illisible", self.stderr, "résolveur ABSENT : le repli reste muet")

    def test_e7_resolveur_illisible_le_repli_le_dit(self) -> None:
        """S-01M5CN1KBT : résolveur TRONQUÉ en pleine instruction (`SyntaxError` à l'exécution) ou qui LÈVE
        (`RuntimeError` en fin de module) = ABSENT ; le repli `src/cadre` le DIT, une ligne par module au format de
        `event_store`. Tronqué sans entrée d'avant : le nom n'est pas laissé dans `sys.modules` ; levant sur une
        entrée d'avant (sentinelle) : CETTE entrée est rendue (avis S-01M5CQ823N). Mutants : ligne retirée d'un
        module, `pop` retiré, ou `pop` sec au lieu de rendre l'entrée d'avant → rouge."""
        for variante, classe, mode in (("tronque", "SyntaxError", ()), ("leve", "RuntimeError", ("sentinelle",))):
            with self.subTest(variante=variante):
                racine = self._arbre(f"illisible_{variante}", neuf=True, ancien=True)
                resolveur = racine / ".agents" / "bin" / "vendor_paths.py"
                texte = resolveur.read_text(encoding="utf-8")
                self.assertEqual(1, texte.count("def verifier_charge("), "ancre du résolveur tronqué introuvable")
                resolveur.write_text(texte[:texte.index("def verifier_charge(")] + "def verifier_charge(racine,\n"
                                     if variante == "tronque" else texte + "\nraise RuntimeError('leve E7')\n",
                                     encoding="utf-8")
                vu = self._sonder(racine, *mode)
                self.assertEqual(str(racine / "src" / "cadre" / "paths.py"), vu["charge"], vu)
                self.assertEqual(str(racine / "src" / "cadre" / "paths.py"), vu["proj"], vu)
                attendus = ["_vendor_paths_charge_poste", "_vendor_paths_etat_projection"] if mode else []
                self.assertEqual(attendus, vu["sentinelles"], "l'entrée d'avant n'a pas été rendue")
                self.assertEqual(attendus, vu["inscrits"], "un résolveur qui lève est resté dans sys.modules")
                lignes = [ligne for ligne in self.stderr.splitlines() if "illisible" in ligne]
                for module in DISENT:
                    with self.subTest(module=module):
                        dites = [ligne for ligne in lignes
                                 if ligne.startswith(f"{module}: résolveur {resolveur} illisible ({classe}: ")
                                 and ligne.endswith(") — repli sur src/cadre")]
                        self.assertEqual(1, len(dites), self.stderr)
                self.assertEqual(len(DISENT), len(lignes), self.stderr)

    def test_e7_resolveur_partiel_compte_absent(self) -> None:
        """Résolveur PARTIEL (lisible, mais un nom de l'API manque : `ProvenanceRefusee` retiré) = ABSENT, comme
        chez les quatre autres producteurs : repli `src/cadre` MUET, même quand `.agents/vendor/cadre` existe.
        Mutant : contrôle d'API retiré de l'un des deux modules → son `dossier_paquet` désigne le vendor → rouge."""
        racine = self._arbre("partiel", neuf=True, ancien=True)
        resolveur = racine / ".agents" / "bin" / "vendor_paths.py"
        resolveur.write_text(resolveur.read_text(encoding="utf-8") + "\ndel ProvenanceRefusee\n", encoding="utf-8")
        vu = self._sonder(racine)
        self.assertEqual(str(racine / "src" / "cadre" / "paths.py"), vu["charge"], vu)
        self.assertEqual(str(racine / "src" / "cadre" / "paths.py"), vu["proj"], vu)
        self.assertNotIn("illisible", self.stderr, "résolveur PARTIEL : le repli reste muet, comme `event_store`")


class KickoffTests(unittest.TestCase):
    """E6 : la garde de kickoff, par son canal réel `armed_by_class`."""

    PAIRES = (  # (ancien, neuf, armée ?)
        ("src/cadre/data/gabarits/pytest.ini.tmpl", ".agents/vendor/cadre/data/gabarits/pytest.ini.tmpl", True),
        ("agentic_v3/reconciliation/board_bridge.py",
         ".agents/vendor/agentic_v3/reconciliation/board_bridge.py", True),
        ("src/cadre/paths.py", ".agents/vendor/cadre/paths.py", False),
    )

    def test_e6_vendor_classe_comme_l_ancien(self) -> None:
        kg = _charger("kickoff_guard_banc_state", HERE / "kickoff_guard.py")
        for ancien, neuf, armee in self.PAIRES:
            for chemin in (ancien, neuf):
                with self.subTest(chemin=chemin):
                    board = kg.BoardReading({"T-E6": {"state": "running", "writeset": [chemin]}})
                    self.assertEqual(armee, "T-E6" in kg.armed_by_class(board))


if __name__ == "__main__":
    unittest.main()
