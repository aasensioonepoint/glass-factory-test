"""LA DÉROGATION DE CHAÎNE DIT L'ÉTAT DU BOARD (T-00001177, S-00004106, S-00004157).

DÉFAUT MESURÉ (critic-fable, binôme du sync) : `start --sans-chaine "renommage"`
posait `[SANS CHAÎNE DE PLAN : renommage]` au stage, puis `done --raison …`
repartait de la raison et ne reportait que les marques de binôme et de cible —
la dérogation disparaissait du board à la clôture. La doc promet l'inverse
(`docs/usage.html` § gardes, graine `PLAN_CHAIN_REQUIRED` : la raison reste
VISIBLE au board) ; la décision pilote S-00004106 corrige le CODE, pas la doc.

ÉTAT, PAS HISTOIRE (décision pilote S-00004157, mots exacts « T-1177 : a ») : la
marque disparaît quand un `start` ultérieur PAIE la chaîne ; le board dit l'état
final, l'histoire reste au journal V3. Passe de correction du binôme bis :
S-00004148 B-3, S-00004149 A-1, A-2, A-3, A-8 et les mutants survivants M6, M7.

ZÉRO APPEL LLM. Board JETABLE (jamais le vrai), `tasks.py` en sous-processus,
comme `test_plan_chain_guard.py`. Témoins, chacun capable de rougir :
  w_01 `start --sans-chaine` puis `done` : le champ au `start`, la marque au
       `done` sous la forme EXACTE du `start` ;
  w_02 `done --sans-binome --sans-cible` : les TROIS marques, une fois chacune ;
  w_03 `reopen` efface la dérogation (précondition : la marque AVANT `reopen`) ;
  w_04 B-3/M6 : un `start` qui PAIE la chaîne efface le champ ET la marque du
       stage en vol ; au `done`, plus de marque ;
  w_05 A-1 : un `start` depuis `done` repart sans dérogation héritée — la garde
       est DÉSARMÉE avant ce `start`, pour qu'aucun paiement ne masque la règle ;
  w_06 A-2/M7 : un second `start --sans-chaine` REMPLACE la raison ;
  w_07 A-3 : la marque n'est jamais doublée, ni au `start` (`--stage` qui la
       porte déjà) ni au `done` (`--raison` qui la porte déjà) ;
  w_08 A-8 : board antérieur à T-1177 (champ absent, marque au stage) : la marque
       revient au `done`, reprise du stage ;
  w_09 A-8 SANS contredire B-3 : même board antérieur, puis un `start` qui paie :
       ni marque au stage en vol, ni marque au `done` ;
  w_10 S-00004170 : board antérieur AMBIGU (marque au stage, chaîne payée, champ
       absent) : il se lit comme B-3 — AUCUNE marque au `done`. Vert sur la base
       (comportement gardé par décision) ; il tue le mutant « condition
       `plan_chain_consumed` retirée », qui survivait (S-00004161).
MUTANTS : chaque mutant rejoue SON témoin sur une copie de `.agents/bin` dont une
ancre (fragment littéral présent UNE fois, asserté par `copie`) est remplacée — il
doit le faire rougir. Forme de `MUTANTS` dans `.agents/evals/test_direct_mode.py`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
#: Ce que `tasks.py` charge — la liste de `test_direct_mode.py`.
COPIES = ("tasks*.py", "plan_cible.py", "plan_depends.py", "plan_trace.py", "specs.py",
          "kickoff_guard.py", "events.py")


def marque(raison: str) -> str:
    return f"[SANS CHAÎNE DE PLAN : {raison}]"


MARQUE = marque("renommage")


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}


def copie(case: unittest.TestCase, source: Path, mutations: dict[str, list[tuple[str, str]]]) -> Path:
    """Une copie jetable de `source` (dossier bin), chaque ancre remplacée UNE fois."""
    base = Path(tempfile.mkdtemp(prefix="sans-chaine-mut-"))
    case.addCleanup(shutil.rmtree, base, True)
    dest = base / ".agents" / "bin"
    dest.mkdir(parents=True)
    for motif in COPIES:
        for f in source.glob(motif):
            shutil.copy2(f, dest / f.name)
    for nom, paires in mutations.items():
        cible = dest / nom
        texte = cible.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            case.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente dans {nom} : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        cible.write_text(texte, encoding="utf-8")
    return dest


class Temoins:
    """Les témoins, chacun joué sur le dossier `bin_` reçu : le vrai, ou une copie mutée."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        # La garde ARMÉE : `--sans-chaine` y est la sortie tracée d'un vrai refus.
        self._armer("PLAN_CHAIN_REQUIRED")
        self.bin = BIN
        self.t1 = self._nouvelle("tache de banc")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- outillage -----------------------------------------------------------
    def tasks(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.bin / "tasks.py"), "--root", str(self.d), *args],
            capture_output=True, text=True, env=_env(), timeout=60, check=False,
        )

    def ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        r = self.tasks(*args)
        self.assertEqual(r.returncode, 0, f"{args}: {r.stdout}{r.stderr}")
        return r

    def _nouvelle(self, titre: str) -> str:
        """`new`, puis l'id RENDU — jamais prédit (T-00000726)."""
        r = self.ok("new", titre)
        trouve = re.search(r"^TASKS: (\S+) → pending$", r.stdout, re.M)
        self.assertIsNotNone(trouve, r.stdout + r.stderr)
        return trouve.group(1)

    def _gate(self, nom: str) -> Path:
        return self.d / ".agents" / "state" / "gates" / nom

    def _armer(self, nom: str, contenu: str = "") -> None:
        self._gate(nom).write_text(contenu, encoding="utf-8")

    def _board(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    def tache(self, tid: str) -> dict:
        board = json.loads(self._board().read_text(encoding="utf-8"))
        return next(t for t in board["tasks"] if t["id"] == tid)

    def board_anterieur(self, tid: str, paye: bool = False) -> None:
        """Le board tel qu'un `start --sans-chaine` d'AVANT T-1177 l'écrivait : la
        marque au stage, PAS de champ `sans_chaine` ; `paye` : la chaîne payée aussi."""
        board = json.loads(self._board().read_text(encoding="utf-8"))
        for t in board["tasks"]:
            if t["id"] == tid:
                t.pop("sans_chaine", None)
                if paye:
                    t["plan_chain_consumed"] = True
        self._board().write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertNotIn("sans_chaine", self.tache(tid), "précondition : le champ est retiré")

    def poser_chaine(self) -> None:
        """Une chaîne de plan fraîche, comme le TRACEUR l'écrit (`role` compris)."""
        quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for nom, role in (("plan-critic", "reviewer"), ("planner", "planner")):
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": quand, "sha": "abc", "role": role}), encoding="utf-8")

    def payer(self, tid: str) -> None:
        """Un `start` qui PAIE la chaîne (précondition assertée : elle est consommée)."""
        self.poser_chaine()
        self.ok("start", tid)
        self.assertTrue(self.tache(tid).get("plan_chain_consumed"), "précondition : la chaîne est payée")

    # -- w_01 la marque du `start` se relit au `done` -------------------------
    def w_01(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "renommage")
        self.assertEqual(self.tache(self.t1)["stage"], MARQUE, "précondition : la marque du start")
        self.assertEqual(self.tache(self.t1).get("sans_chaine"), "renommage", "le start garde la raison")
        self.ok("done", self.t1, "--raison", "renommé")
        self.assertEqual(self.tache(self.t1)["stage"], f"renommé {MARQUE}")

    # -- w_02 les trois dérogations côte à côte -------------------------------
    def w_02(self, bin_: Path) -> None:
        self.bin = bin_
        self._armer("BINOME_REQUIRED")
        self._armer("PLAN_CIBLE_REQUIRED", "spec=docs/spec.md\nchantier=lot\n")
        self.ok("start", self.t1, "--sans-chaine", "renommage")
        self.ok("done", self.t1, "--raison", "renommé",
                "--sans-binome", "doublon", "--sans-cible", "hors chantier")
        stage = self.tache(self.t1)["stage"]
        self.assertTrue(stage.startswith("renommé "), stage)
        for m in ("[SANS BINÔME : doublon]", "[SANS CIBLE : hors chantier]", MARQUE):
            self.assertEqual(stage.count(m), 1, f"{m} une fois dans : {stage}")

    # -- w_03 `reopen` efface la dérogation -----------------------------------
    def w_03(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "renommage")
        self.ok("done", self.t1, "--raison", "renommé")
        self.assertIn(MARQUE, self.tache(self.t1)["stage"], "précondition : la marque au done")
        self.ok("reopen", self.t1, "--raison", "on y retourne")
        self.assertNotIn("sans_chaine", self.tache(self.t1), "reopen a gardé la dérogation")
        # Rouvrir redemande la chaîne : ce `start` la PAIE, sans dérogation.
        self.payer(self.t1)
        self.ok("done", self.t1, "--raison", "refait")
        self.assertEqual(self.tache(self.t1)["stage"], "refait")

    # -- w_04 B-3/M6 : la chaîne payée efface la dérogation -------------------
    def w_04(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.assertEqual(self.tache(self.t1).get("sans_chaine"), "a", "précondition : la dérogation posée")
        self.payer(self.t1)  # `--stage` omis : le stage en vol est GARDÉ, sa marque doit tomber
        t = self.tache(self.t1)
        self.assertNotIn("sans_chaine", t, "le start qui paie a gardé la dérogation (M6)")
        self.assertNotIn(marque("a"), t.get("stage", ""), "le stage en vol dit encore la dérogation")
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], "x")

    # -- w_05 A-1 : un `start` depuis `done` n'hérite pas ---------------------
    def w_05(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], f"x {marque('a')}", "précondition : la marque au done")
        # Garde DÉSARMÉE : ce `start` ne consomme rien, seule la règle A-1 peut effacer.
        self._gate("PLAN_CHAIN_REQUIRED").unlink()
        self.ok("start", self.t1)  # `--stage` omis : le stage du `done` est gardé
        t = self.tache(self.t1)
        self.assertFalse(t.get("plan_chain_consumed"), "précondition : aucune chaîne payée")
        self.assertNotIn("sans_chaine", t, "le start depuis done a hérité la dérogation (A-1)")
        self.assertNotIn(marque("a"), t.get("stage", ""), "le stage en vol dit encore la dérogation")
        self.ok("done", self.t1, "--raison", "y")
        self.assertEqual(self.tache(self.t1)["stage"], "y")

    # -- w_06 A-2/M7 : un second `--sans-chaine` remplace ---------------------
    def w_06(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.ok("start", self.t1, "--sans-chaine", "b")
        t = self.tache(self.t1)
        self.assertEqual(t.get("sans_chaine"), "b", "le second --sans-chaine a gardé la première raison (M7)")
        self.assertEqual(t["stage"], marque("b"))
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], f"x {marque('b')}")

    # -- w_07 A-3 : jamais doublée --------------------------------------------
    def w_07(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a", "--stage", f"étape {marque('a')}")
        self.assertEqual(self.tache(self.t1)["stage"], f"étape {marque('a')}", "doublée au start")
        self.ok("done", self.t1, "--raison", f"renommé {marque('a')}")
        self.assertEqual(self.tache(self.t1)["stage"], f"renommé {marque('a')}", "doublée au done")

    # -- w_08 A-8 : board antérieur, la marque revient au `done` --------------
    def w_08(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.board_anterieur(self.t1)
        self.assertEqual(self.tache(self.t1)["stage"], marque("a"), "précondition : la marque au stage")
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], f"x {marque('a')}")

    # -- w_09 A-8 sans contredire B-3 : board antérieur puis chaîne payée ------
    def w_09(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.board_anterieur(self.t1)
        self.payer(self.t1)
        self.assertNotIn(marque("a"), self.tache(self.t1).get("stage", ""), "le stage en vol dit encore la dérogation")
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], "x")

    # -- w_10 S-00004170 : board antérieur ambigu, chaîne payée → pas de marque --
    def w_10(self, bin_: Path) -> None:
        self.bin = bin_
        self.ok("start", self.t1, "--sans-chaine", "a")
        self.board_anterieur(self.t1, paye=True)
        t = self.tache(self.t1)
        self.assertEqual(t["stage"], marque("a"), "précondition : la marque au stage")
        self.assertTrue(t.get("plan_chain_consumed"), "précondition : la chaîne payée")
        self.ok("done", self.t1, "--raison", "x")
        self.assertEqual(self.tache(self.t1)["stage"], "x", "marque reprise d'un board antérieur à chaîne payée")


class SansChaineTests(Temoins, unittest.TestCase):
    """Chaque témoin sur le VRAI `.agents/bin`."""


for _nom in sorted(n for n in dir(Temoins) if n.startswith("w_")):
    setattr(SansChaineTests, "test_" + _nom[2:], (lambda n: lambda self: getattr(self, n)(BIN))(_nom))


#: Les mutants : `nom → ({fichier: [(ancre, remplacement)]}, témoin)`.
_ETATS, _VERBES = "tasks_etats.py", "tasks_verbes.py"
_PAIE = 'task["plan_chain_consumed"] = True\n                efface_derogation_chaine(task)\n'
_DEPUIS_DONE = '            if before["state"] == "done":\n                efface_derogation_chaine(task)\n'
_GARDE = '            task["sans_chaine"] = sans_chaine\n'
_AU_DONE = "        if raison_chaine:\n            stage = avec_marque_chaine(stage, raison_chaine)\n"
MUTANTS = {
    "M6 la chaîne payée n'efface pas": ({_ETATS: [(_PAIE, 'task["plan_chain_consumed"] = True\n')]}, "w_04"),
    "A-1 le start depuis done hérite": ({_ETATS: [(_DEPUIS_DONE, "")]}, "w_05"),
    "effacement sans le stage (B-3)": ({_ETATS: [('    if stage != avant:\n        task["stage"] = stage.strip()\n', "")]},
                                       "w_04"),
    "effacement sans le stage (A-1)": ({_ETATS: [('    if stage != avant:\n        task["stage"] = stage.strip()\n', "")]},
                                       "w_05"),
    "M7 le second --sans-chaine garde la première": ({_ETATS: [(_GARDE, _GARDE.replace(
        'task["sans_chaine"] = sans_chaine', 'task.setdefault("sans_chaine", sans_chaine)'))]}, "w_06"),
    "le start ne garde pas la raison": ({_ETATS: [(_GARDE, "            pass\n")]}, "w_01"),
    "le done ne reporte pas": ({_ETATS: [(_AU_DONE, "")]}, "w_01"),
    "A-3 marque doublée": ({_ETATS: [('    return stage if m in stage else f"{stage} {m}"\n',
                                      '    return f"{stage} {m}"\n')]}, "w_07"),
    "A-8 pas de reprise du stage": ({_ETATS: [("re.findall(_MARQUE_CHAINE_RE, before.get(\"stage\") or \"\")", "[]")]},
                                    "w_08"),
    "A-8 reprise après paiement, sans effacement": ({_ETATS: [
        (' and not task.get("plan_chain_consumed"):\n', ":\n"),
        ('    if stage != avant:\n        task["stage"] = stage.strip()\n', "")]}, "w_09"),
    "reopen n'efface pas": ({_VERBES: [('        task.pop("sans_chaine", None)\n', "")]}, "w_03"),
    "S-00004170 condition plan_chain_consumed retirée": ({_ETATS: [(' and not task.get("plan_chain_consumed"):\n', ":\n")]},
                                                         "w_10"),
}


class SansChaineMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant de `MUTANTS` rejoue SON témoin et doit le faire échouer."""

    def tuer(self, nom: str) -> None:
        mutations, temoin = MUTANTS[nom]
        variante = copie(self, BIN, mutations)  # HORS de assertRaises : une ancre absente n'est pas un meurtre
        with self.assertRaises(AssertionError, msg=f"mutant SURVIVANT : {nom}"):
            getattr(self, temoin)(variante)

    def test_la_variante_non_mutee_est_verte(self) -> None:
        """NON-VACUITÉ du harnais : une copie SANS mutation passe les témoins des
        mutants — un mutant n'est pas tué par la seule copie."""
        variante = copie(self, BIN, {})
        for temoin in sorted({t for _m, t in MUTANTS.values()}):
            self.tearDown()
            self.setUp()
            getattr(self, temoin)(variante)


_GENERES = {"test_mutant_" + re.sub(r"\W+", "_", n).strip("_"): n for n in MUTANTS}
# Deux mutants au MÊME nom de test : le second écraserait le premier en silence.
assert len(_GENERES) == len(MUTANTS), "noms de tests de mutants en collision"
for _test, _nom in _GENERES.items():
    setattr(SansChaineMutantsTests, _test, (lambda n: lambda self: self.tuer(n))(_nom))


if __name__ == "__main__":
    unittest.main()
