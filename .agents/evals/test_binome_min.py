"""Le binôme de clôture à UN critique : `BINOME_MIN` (T-00001226, décision pilote S-00004500).

POURQUOI CE BANC. La clôture exigeait DEUX critiques distincts (T-00000586), puis admettait
UN critique sous une passe de correction déclarée (T-00001222). S-00004500 tranche : UN
critique de clôture pour TOUTE clôture — `critic-opus`, repli `critic-fable` puis
`critic-sonnet-max` — et le drapeau de la passe est RETIRÉ, sans objet. Le nombre vit en UN
point, `BINOME_MIN` dans la façade `tasks.py`, doublé textuellement dans le hook `Stop`
`.claude/hooks/affirmation-guard.sh` ; ce banc lie les deux et éprouve les deux SENS.

POURQUOI UN FICHIER À PART. `test_binome_guard.py` est au plafond de son cliquet de taille
(`python_file_length_cliquet.json`, plafond = origine scellée). Ce banc le CHARGE donc par
`spec_from_file_location` et emprunte les montages de `BinomeRepriseTests` (dépôt git jetable,
variantes mutées) — par attribut du module chargé, JAMAIS par un nom de module : une classe
`TestCase` liée ici serait collectée une seconde fois.

CE QUE CE BANC LIE (critères A1-A3 du plan) : chacun des trois critiques SEUL clôt ; zéro
critique est refusé (« REVUE CRITIQUE ») ; `plan-critic` seul est refusé ; une trace fraîche
du slot `running` couvre ; une trace de 25 h sans borne de porte est refusée ; `BINOME_MIN`
vaut au moins 1 ; le défaut d'`exige` de `binome_reprise_refusal` vaut `BINOME_MIN` (appel
DIRECT, sans `exige` : via `set_state`, qui passe toujours `exige=`, le mutant du défaut
serait équivalent) ; parité hook/façade ; le drapeau retiré rend rc 2. Chaque mutant de
`MUTANTS_MIN` rend l'AUTRE issue sur son scénario ; la variante non mutée rend celle du réel.

CE QUE ÇA NE PROUVE PAS : la trace prouve que la déf a tourné, jamais son verdict — la garde
empêche d'OUBLIER, pas de TRICHER. L'indépendance de deux modèles est ABANDONNÉE par décision.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_PARTAGE = "test_binome_guard_partage_min"
_spec = importlib.util.spec_from_file_location(_PARTAGE, Path(__file__).with_name("test_binome_guard.py"))
_banc = importlib.util.module_from_spec(_spec)
sys.modules[_PARTAGE] = _banc
_spec.loader.exec_module(_banc)
ROOT, TASKS, il_y_a, nouvelle, tasks = _banc.ROOT, _banc.TASKS, _banc.il_y_a, _banc.nouvelle, _banc.tasks
HOOK = ROOT / ".claude" / "hooks" / "affirmation-guard.sh"
#: Le drapeau RETIRÉ par T-00001226 : ce banc asserte son refus par argparse (rc 2).
DRAPEAU_RETIRE = "--correction-de"
#: La constante, lue à la colonne 0 dans la façade comme dans le hook.
MOTIF_MIN = re.compile(r"^BINOME_MIN = (\d+)$", re.M)

#: Les mutants du nombre : nom → (fichier de `.agents/bin`, ancres → remplacements). Les deux
#: seuils `if len(vus) >= BINOME_MIN:` de `tasks_gardes.py` sont ancrés sur DEUX lignes, avec
#: le `return` qui suit (constat C5 du critique de plan) : `_variante` exige une ancre UNIQUE.
MUTANTS_MIN = {
    "MIN-1-2": ("tasks.py", [("BINOME_MIN = 1\n", "BINOME_MIN = 2\n")]),
    "EXIGE-2": ("tasks_etats.py", [("exige: int = BINOME_MIN)", "exige: int = 2)")]),
    # Le nombre que `set_state` PASSE à la jambe reprise (exec-critic S-00004521) : sans
    # ce mutant, `exige = 2` dans `set_state` ne rougissait aucun témoin.
    "SETSTATE-2": ("tasks_etats.py", [("            exige = BINOME_MIN\n", "            exige = 2\n")]),
    "PREUVE-0": ("tasks_gardes.py", [("    if len(vus) >= BINOME_MIN:\n        return vus, tid, None\n",
                                      "    if len(vus) >= 0:\n        return vus, tid, None\n")]),
    "REFUS-0": ("tasks_gardes.py", [("    if len(vus) >= BINOME_MIN:\n        return None\n",
                                     "    if len(vus) >= 0:\n        return None\n")]),
}


def parite(texte_facade: str, texte_hook: str) -> list[str]:
    """Les fautes de parité entre la façade et le hook : vide = un seul `BINOME_MIN` de
    chaque côté, même valeur, et le seuil du hook lit ce nom."""
    fautes = []
    facade, hook = MOTIF_MIN.findall(texte_facade), MOTIF_MIN.findall(texte_hook)
    if len(facade) != 1 or len(hook) != 1:
        fautes.append(f"BINOME_MIN : {len(facade)} définition(s) dans la façade, {len(hook)} dans le hook")
    elif facade != hook:
        fautes.append(f"BINOME_MIN diverge : façade {facade[0]}, hook {hook[0]}")
    if texte_hook.count("if len(vus) >= BINOME_MIN:\n") != 1:
        fautes.append("le seuil du hook ne lit pas BINOME_MIN (une fois exactement)")
    return fautes


class BinomeMinTests(unittest.TestCase):
    """La clôture à UN critique, sur le réel et sur les variantes de `MUTANTS_MIN`. Board
    jetable HORS git (jambe reprise inerte et muette), sauf le défaut d'`exige`, monté par le
    `_depot` git de `BinomeRepriseTests`. `set_state` EN PROCESSUS ; la CLI en sous-processus."""

    _charger = staticmethod(_banc.BinomeRepriseTests._charger)
    _armer = staticmethod(_banc.BinomeRepriseTests._armer)
    _git = staticmethod(_banc.BinomeRepriseTests._git)
    _variante = _banc.BinomeRepriseTests._variante
    _head = _banc.BinomeRepriseTests._head
    _commit = _banc.BinomeRepriseTests._commit
    _depot = _banc.BinomeRepriseTests._depot
    _trace_git = _banc.BinomeRepriseTests._trace

    def setUp(self) -> None:
        self.reel = self._charger(TASKS, "tasks_binome_min_reel")

    # ---- montages ------------------------------------------------------------
    def _board(self, chantier: str = "ch") -> Path:
        d = Path(tempfile.mkdtemp(prefix="binome-min-"))
        self.addCleanup(shutil.rmtree, d, True)
        self._armer(d)
        self.t1 = nouvelle(d, "la tache a clore", "--chantier", chantier)
        return d

    @staticmethod
    def _tracer(d: Path, tid: str, nom: str, heures: float = 1, sha: str = "abc1234") -> None:
        dd = d / ".agents" / "state" / "local" / "binome"
        dd.mkdir(parents=True, exist_ok=True)
        (dd / f"{tid}.{nom}.json").write_text(json.dumps({"sha": sha, "at": il_y_a(heures)}),
                                              encoding="utf-8")

    def _clore(self, mod, d: Path) -> tuple[str, str]:
        """(`passe`, stage au board) ou (`refus`, message)."""
        try:
            mod.set_state(str(d), self.t1, "done", stage="fini")
        except mod.BoardError as exc:
            return "refus", str(exc)
        board = json.loads((d / ".agents" / "state" / "board" / "TASKS.json").read_text(encoding="utf-8"))
        return "passe", next(t["stage"] for t in board["tasks"] if t["id"] == self.t1)

    # ---- scénarios : chacun monte son board et rend (issue, message) ----------
    def _s_un_critique(self, mod, nom: str = "critic-opus"):
        d = self._board()
        self._tracer(d, self.t1, nom)
        return self._clore(mod, d)

    def _s_zero_critique(self, mod, nom: str | None = None):
        d = self._board()
        if nom is not None:  # un nom HORS du vocabulaire clos : il ne compte pas
            self._tracer(d, self.t1, nom)
        return self._clore(mod, d)

    def _s_slot(self, mod, heures: float = 1):
        d = self._board()
        self.t2 = nouvelle(d, "le slot du lot", "--chantier", "ch")
        p = tasks(d, "start", self.t2)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        _banc.poser_portee(d, self.t2, [self.t2, self.t1])  # l'emprunt passe par la portée (T-01M5F728FGJ43QJX1RJKTWWKRB)
        self._tracer(d, self.t2, "critic-opus", heures=heures)
        return self._clore(mod, d)

    def _s_exige_defaut(self, mod):
        """La jambe reprise appelée DIRECTEMENT, SANS `exige` (son défaut), sur UN critique à
        jour : constat C6 — via `set_state`, le mutant du défaut serait équivalent."""
        d = self._depot()
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        self._trace_git(d, "critic-opus", self._head(d))
        racine = str(d)
        refus = mod.binome_reprise_refusal(racine, self.t1, mod.binome_preuve(racine, self.t1),
                                           mod.load(racine))
        return ("passe", "") if refus is None else ("refus", refus)

    def _s_reprise_set_state(self, mod):
        """La clôture PAR `set_state` dans un dépôt git : `PLAN-ETAT.md` commité, UNE trace
        `critic-opus` sur HEAD. Admise sous `BINOME_MIN` = 1 ; refusée si `set_state`
        passe `exige = 2` à la jambe reprise (1 critique à jour sur 1)."""
        d = self._depot()
        self._commit(d, {"PLAN-ETAT.md": "routeur\nligne\n"})
        self._trace_git(d, "critic-opus", self._head(d))
        return self._clore(mod, d)

    def test_la_cloture_git_a_UN_critique_a_jour_passe(self) -> None:
        issue, msg = self._s_reprise_set_state(self.reel)
        self.assertEqual(issue, "passe", msg)

    # ---- A1 : le module réel ---------------------------------------------------
    def test_chacun_des_trois_critiques_SEUL_clot(self) -> None:
        self.assertEqual(self.reel.BINOME_CRITIQUES, ("critic-opus", "critic-fable", "critic-sonnet-max"))
        for nom in self.reel.BINOME_CRITIQUES:
            with self.subTest(critique=nom):
                d = self._board()
                self._tracer(d, self.t1, nom)
                p = tasks(d, "done", self.t1, "--raison", "fini")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_zero_critique_est_REFUSE(self) -> None:
        d = self._board()
        p = tasks(d, "done", self.t1, "--raison", "fini")
        sortie = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, sortie)
        self.assertIn("REVUE CRITIQUE", sortie)
        self.assertIn("0 critique(s) tracé(s) — aucun ; il en faut 1.", sortie)
        self.assertIn("`critic-opus`, repli `critic-fable` puis", sortie)

    def test_plan_critic_seul_est_REFUSE(self) -> None:
        issue, msg = self._s_zero_critique(self.reel, nom="plan-critic")
        self.assertEqual(issue, "refus", msg)
        self.assertIn("REVUE CRITIQUE", msg)

    def test_la_trace_FRAICHE_du_slot_couvre(self) -> None:
        issue, stage = self._s_slot(self.reel)
        self.assertEqual(issue, "passe", stage)
        self.assertIn(f"binôme relevé sur {self.t2}", stage)

    def test_25_h_sans_borne_de_porte_est_REFUSE(self) -> None:
        issue, msg = self._s_slot(self.reel, heures=25)
        self.assertEqual(issue, "refus", msg)
        self.assertIn("preuve empruntée PÉRIMÉE", msg)
        self.assertIn("1 critique(s) distinct(s) daté(s) de moins de 24 h", msg)

    def test_BINOME_MIN_vaut_au_moins_un(self) -> None:
        self.assertIsInstance(self.reel.BINOME_MIN, int)
        self.assertGreaterEqual(self.reel.BINOME_MIN, 1, "BINOME_MIN < 1 : la garde ne garde plus rien")

    def test_le_defaut_d_exige_vaut_BINOME_MIN(self) -> None:
        defaut = inspect.signature(self.reel.binome_reprise_refusal).parameters["exige"].default
        self.assertEqual(defaut, self.reel.BINOME_MIN)
        self.assertEqual(self._s_exige_defaut(self.reel)[0], "passe")

    def test_parite_hook_facade(self) -> None:
        facade, hook = TASKS.read_text(encoding="utf-8"), HOOK.read_text(encoding="utf-8")
        self.assertEqual(parite(facade, hook), [])
        self.assertEqual(MOTIF_MIN.findall(hook), [str(self.reel.BINOME_MIN)])
        # Les deux sens : un hook à 2 (A3), ou dont le seuil a perdu le nom, rougit la parité.
        self.assertTrue(parite(facade, hook.replace("BINOME_MIN = 1\n", "BINOME_MIN = 2\n")))
        self.assertTrue(parite(facade, hook.replace("if len(vus) >= BINOME_MIN:\n", "if len(vus) >= 1:\n")))

    def test_le_drapeau_retire_rend_rc_2(self) -> None:
        d = self._board()
        self._tracer(d, self.t1, "critic-opus")
        p = tasks(d, "done", self.t1, "--raison", "fini", DRAPEAU_RETIRE, self.t1)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn(DRAPEAU_RETIRE, p.stderr)
        self.assertNotIn(DRAPEAU_RETIRE, tasks(d, "done", "--help").stdout)
        self.assertIn("pending", tasks(d, "list", "--task", self.t1).stdout, "le refus a clos la tâche")

    # ---- A2, A3 : les mutants rendent l'AUTRE issue ------------------------------
    def test_mutants_du_nombre_rougissent(self) -> None:
        cibles = {
            "MIN-1-2": [(self._s_un_critique, {}), (self._s_un_critique, {"nom": "critic-sonnet-max"})],
            "EXIGE-2": [(self._s_exige_defaut, {})],
            "SETSTATE-2": [(self._s_reprise_set_state, {})],
            "PREUVE-0": [(self._s_slot, {})],
            "REFUS-0": [(self._s_zero_critique, {}), (self._s_zero_critique, {"nom": "plan-critic"})],
        }
        self.assertEqual(sorted(cibles), sorted(MUTANTS_MIN), "chaque mutant a ses cibles")
        temoins = {f: self._variante(fichier=f) for f in {f for f, _ in MUTANTS_MIN.values()}}
        for nom, (fichier, paires) in MUTANTS_MIN.items():
            mod = self._variante(*paires, fichier=fichier)
            for scenario, kw in cibles[nom]:
                with self.subTest(mutant=nom, scenario=scenario.__name__, **kw):
                    reel = scenario(self.reel, **kw)[0]
                    self.assertEqual(scenario(temoins[fichier], **kw)[0], reel, "la variante non mutée diverge")
                    attendu = "refus" if reel == "passe" else "passe"
                    issue, msg = scenario(mod, **kw)
                    self.assertEqual(issue, attendu, f"{nom} survit sur {scenario.__name__} : {msg}")


if __name__ == "__main__":
    unittest.main()
