#!/usr/bin/env python3
"""LE VERBE `depends` ET SES REMÈDES — T-00000765 (W1-W4f, W11, W14).

ZÉRO APPEL LLM : `tasks.py`, `plan_cible.py` et `plan_depends.py` sont chargés
par chemin (`spec_from_file_location`, comme `test_plan_cible_guard.py`) et
appelés sur un board jetable sous `tmp_path`. Les bancs CLI passent
`CADRE_STATE_DIR`/`CADRE_PROJECT_ROOT`/`AGENTS_EVENTS_DIR` sur un `mktemp`.

*** CHAQUE TÉMOIN PORTE SON MUTANT *** — le docstring nomme la mutation du code
réel qui doit le faire rougir (jouée sur COPIE jetable, L-00000487).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
TASKS = BIN / "tasks.py"
WAVES = ROOT / "core-scripts" / "plan_waves.py"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


pc = _charger("plan_cible", BIN / "plan_cible.py")
pd = _charger("plan_depends", BIN / "plan_depends.py")
tasks = _charger("tasks_depends_add", TASKS)
# UN SEUL objet module par nom, quel que soit l'ordre de collecte de pytest :
# les caches paresseux de CE `tasks` pointent sur les objets chargés ci-dessus.
tasks._PLAN_CIBLE_MOD = pc
tasks._PLAN_DEPENDS_MOD = pd

OP1 = "ORDRE PILOTE S-00000001 : a avant c"
TECH = "amont livre ce que aval consomme"
REMEDE = "git checkout -- .agents/bin/plan_depends.py"
# opus T4 : « absent » couvre l'import `plan_cible.py`, et le remède restaure les DEUX.
REMEDE_DEUX = "git checkout -- .agents/bin/plan_depends.py .agents/bin/plan_cible.py"
ABSENT_DEUX = "`.agents/bin/plan_depends.py` ou son import `plan_cible.py` est ABSENT"


class _Banc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "specs"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        self.root = str(self.d)
        self.store = self.d / ".agents" / "state" / "board" / "TASKS.json"
        self.specs([])

    def tearDown(self):
        self._tmp.cleanup()

    def new(self, n: int) -> list[str]:
        return [tasks.new_task(self.root, f"tache {i}", "").split()[1] for i in range(n)]

    def read(self, tid: str) -> dict:
        data = json.loads(self.store.read_text(encoding="utf-8"))
        return next(t for t in data["tasks"] if t["id"] == tid)

    def inject(self, tid: str, deps: list[str], motifs: dict[str, str] | None = None):
        """Un board ÉDITÉ À LA MAIN (arêtes héritées SANS motif, cycle) — la seule
        façon de produire ce que `set_depends` refuse d'écrire."""
        data = json.loads(self.store.read_text(encoding="utf-8"))
        for t in data["tasks"]:
            if t["id"] == tid:
                t["depends_on"] = list(deps)
                t.pop("depends_motif", None)
                if motifs:
                    t["depends_motif"] = dict(motifs)
        self.store.write_text(json.dumps(data), encoding="utf-8")

    def specs(self, decisions: list[str], plans: list[str] = ()):
        entrees = [{"id": s, "task": "T-00000001", "kind": "decision", "title": "d",
                    "text": "", "files": [], "date": "2026-09-27"} for s in decisions]
        entrees += [{"id": s, "task": "T-00000001", "kind": "plan", "title": "p",
                     "text": "", "files": [], "date": "2026-09-27"} for s in plans]
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 99999, "entries": entrees}), encoding="utf-8")

    def armer(self):
        (self.d / "spec.md").write_text("**« un invariant »**\n", encoding="utf-8")
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            "spec=spec.md\nchantier=refonte\n", encoding="utf-8")

    def dep(self, tid: str, deps: list[str], motif="", **kw) -> str:
        return tasks.set_depends(self.root, tid, deps, motif=motif, **kw)

    def refus(self, fn, *args, **kw) -> str:
        with self.assertRaises(tasks.BoardError) as caught:
            fn(*args, **kw)
        return str(caught.exception)

    def cli(self, *args: str):
        env = {**os.environ, "CADRE_STATE_DIR": self._tmp.name, "CADRE_PROJECT_ROOT": self._tmp.name,
               "AGENTS_EVENTS_DIR": self._tmp.name, "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run([sys.executable, str(TASKS), "--root", self.root, *args],
                              capture_output=True, text=True, timeout=120, env=env)


# ===========================================================================
# W1-W4 — `--add`, la réécriture GARDÉE, les motifs ORDRE PILOTE neufs.
# ===========================================================================
class VerbeTests(_Banc):
    def test_w1_add_garde_deux_aretes_et_leurs_motifs_en_ajoute_une(self):
        """W1. MUTANT : `--add` traité comme une réécriture (`wanted = []` en mode
        add) ⇒ les deux arêtes existantes disparaissent, rouge."""
        a, b, c, d = self.new(4)
        self.specs(["S-00000001"])
        self.dep(d, [a, b], motif=[OP1, TECH])
        msg = self.dep(d, [c], motif="technique : c", add=True)
        self.assertEqual(self.read(d)["depends_on"], [a, b, c])
        self.assertEqual(self.read(d)["depends_motif"], {a: OP1, b: TECH, c: "technique : c"})
        self.assertIn("depends_on = 3 dependencies", msg)
        # id déjà présent, même motif : inchangé et DIT ; autre motif : refusé en nommant celui en place.
        self.assertIn(f"inchangée : {b}", self.dep(d, [b], motif=TECH, add=True))
        self.assertIn(TECH, self.refus(self.dep, d, [b], motif="autre", add=True))
        self.assertEqual(self.read(d)["depends_on"], [a, b, c])

    def test_w1bis_cli_add_et_retirer_sont_reconnus(self):
        """M2 refermé. MUTANT : `--add` retiré du parseur ⇒ rc 2 `unrecognized`."""
        a, b, c = self.new(3)
        self.assertEqual(self.cli("depends", c, a, "--motif", TECH).returncode, 0)
        r = self.cli("depends", c, b, "--add", "--motif", "technique : b")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(c)["depends_on"], [a, b])
        r = self.cli("depends", c, "--retirer", a)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"retirée : {a}", r.stdout)
        self.assertEqual(self.read(c)["depends_on"], [b])
        self.assertNotIn("Traceback", r.stderr)

    def test_w2_reecriture_perdant_un_ordre_pilote_refusee_store_identique(self):
        """W2 (M1 refermé). MUTANT : `motif_ordre_pilote_refus` non appelé sur la
        réécriture ⇒ l'ordre pilote est effacé sans un mot, rouge."""
        a, b, c = self.new(3)
        self.specs(["S-00000001"])
        self.dep(c, [a, b], motif=[OP1, TECH])
        avant = self.store.read_bytes()
        msg = self.refus(self.dep, c, [b], motif="nouveau")
        self.assertIn("ORDRE PILOTE", msg)
        self.assertIn("--retirer-ordre-pilote", msg)
        self.assertEqual(self.store.read_bytes(), avant)
        # `--clear` aussi.
        self.assertIn("ORDRE PILOTE", self.refus(self.dep, c, [], clear=True))
        self.assertEqual(self.store.read_bytes(), avant)
        # Une arête TECHNIQUE perdue passe, et la sortie le DIT.
        self.assertIn(f"retirée : {b}", self.dep(c, [a], motif=OP1))
        self.assertEqual(self.read(c)["depends_on"], [a])

    def test_w3_motif_unique_recopie_sur_un_ordre_pilote_garde_refuse(self):
        """W3. MUTANT : comparer les IDS seuls (motif changé ignoré) ⇒ un
        `--motif "nouveau"` uniforme écrase l'ordre pilote, rouge."""
        a, b, c = self.new(3)
        self.specs(["S-00000001"])
        self.dep(c, [a, b], motif=[OP1, TECH])
        msg = self.refus(self.dep, c, [a, b], motif="nouveau")
        self.assertIn("CHANGE the motif", msg)
        self.assertEqual(self.read(c)["depends_motif"][a], OP1)
        # Restitué VERBATIM, la réécriture passe.
        self.dep(c, [a, b], motif=[OP1, "technique : b2"])
        self.assertEqual(self.read(c)["depends_motif"], {a: OP1, b: "technique : b2"})

    def test_w4_ordre_pilote_sans_decision_ou_non_canonique_refuse(self):
        """W4 (M3 refermé). MUTANT : `decisions_existantes` sauté dans
        `valider_motif_neuf` ⇒ `S-99999999` accepté, rouge."""
        a, b = self.new(2)
        self.specs(["S-00000001"])
        self.assertIn("S-99999999", self.refus(self.dep, b, [a], motif="ORDRE PILOTE S-99999999 : x"))
        self.assertIn("canonique", self.refus(self.dep, b, [a], motif="ordre pilote s-1"))
        self.assertNotIn("depends_on", self.read(b))
        # Un motif `ordre…` non canonique n'est JAMAIS refusé : avertissement seul.
        r = self.cli("depends", b, a, "--motif", "ordre revise par le pilote")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("AVERTISSEMENT", r.stderr)

    def test_w4b_retirer_ordre_pilote_sous_decision_distincte(self):
        """W4b. MUTANT : « différente de la S-id du motif » sauté ⇒ S-00000001
        lève son propre ordre, rouge ; MUTANT 2 : contrôle de décision sauté ⇒
        une S-id `kind=plan` passe, rouge."""
        a, b = self.new(2)
        self.specs(["S-00000001", "S-00000002"], plans=["S-00000003"])
        self.dep(b, [a], motif=OP1)
        self.assertIn("propre retrait", self.refus(self.dep, b, [], retirer_ordre_pilote=[a, "S-00000001"]))
        self.assertIn("kind=decision", self.refus(self.dep, b, [], retirer_ordre_pilote=[a, "S-00000003"]))
        self.assertEqual(self.read(b)["depends_on"], [a])
        msg = self.dep(b, [], retirer_ordre_pilote=[a, "S-00000002"])
        self.assertIn(a, msg)
        self.assertIn("S-00000002", msg)
        self.assertNotIn("depends_on", self.read(b))
        self.assertNotIn("depends_motif", self.read(b))
        # Sur une arête technique : renvoi vers `--retirer`.
        self.dep(b, [a], motif=TECH)
        self.assertIn("--retirer", self.refus(self.dep, b, [], retirer_ordre_pilote=[a, "S-00000002"]))

    def test_w4b_bis_une_trace_d_approbation_ne_leve_ni_ne_pose_un_ordre(self):
        """W4b bis (fable F4). Une `kind=decision` titrée `plan approuvé` ou
        `night-eligible: approved` (titre NORMALISÉ, `TITRES_APPROBATION`) ne vaut ni
        décision de levée ni S-id d'un motif neuf. MUTANT : filtre des traces retiré de
        `decisions_du_journal` ⇒ la trace lève l'ordre, rouge."""
        a, b, c = self.new(3)
        self.specs(["S-00000001", "S-00000002"])
        entrees = json.loads((self.d / ".agents/state/specs/SPECS.json").read_text(encoding="utf-8"))
        for sid, titre in (("S-00000004", " Plan  Approuvé"), ("S-00000005", "night-eligible: approved")):
            entrees["entries"].append({"id": sid, "task": b, "kind": "decision", "title": titre,
                                       "text": "plan=x sha256=y", "files": [], "date": "2026-09-27"})
        (self.d / ".agents/state/specs/SPECS.json").write_text(json.dumps(entrees), encoding="utf-8")
        self.dep(b, [a], motif=OP1)
        for sid in ("S-00000004", "S-00000005"):
            msg = self.refus(self.dep, b, [], retirer_ordre_pilote=[a, sid])
            self.assertIn("ne lève pas un ordre", msg)
            msg = self.refus(self.dep, b, [c], motif=f"ORDRE PILOTE {sid} : c avant b", add=True)
            self.assertIn("une trace `plan approuvé` n'en est pas une", msg)
        self.assertEqual(self.read(b)["depends_motif"], {a: OP1})
        self.assertIn("S-00000002", self.dep(b, [], retirer_ordre_pilote=[a, "S-00000002"]))  # une VRAIE décision lève

    def test_w4c_retirer_une_arete_technique_heritee(self):
        """W4c. MUTANT : `--retirer` en réécriture (wanted = []) ⇒ l'autre arête
        disparaît ; MUTANT 2 : test ordre pilote retiré ⇒ l'OP part ; MUTANT 3 :
        affectation `depends_motif` non gardée ⇒ clé `{}` créée (R4)."""
        a, b, c = self.new(3)
        self.inject(c, [a, b], {b: TECH})  # a HÉRITÉE (sans motif), b motivée
        self.assertIn(f"retirée : {a}", self.dep(c, [], retirer=a))
        self.assertEqual(self.read(c)["depends_on"], [b])
        self.assertEqual(self.read(c)["depends_motif"], {b: TECH})
        # Entièrement héritée : `depends_motif` N'APPARAÎT PAS après.
        self.inject(c, [a, b])
        self.dep(c, [], retirer=a)
        self.assertEqual(self.read(c)["depends_on"], [b])
        self.assertNotIn("depends_motif", self.read(c))
        # Dernière arête retirée : déclaration retirée, dite.
        self.assertIn("la dernière", self.dep(c, [], retirer=b))
        self.assertNotIn("depends_on", self.read(c))
        # Ordre pilote : refus nommant `--retirer-ordre-pilote` ; absente : refus.
        self.specs(["S-00000001"])
        self.dep(c, [a], motif=OP1)
        self.assertIn("--retirer-ordre-pilote", self.refus(self.dep, c, [], retirer=a))
        self.assertIn("no such edge", self.refus(self.dep, c, [], retirer=b))
        self.assertEqual(self.read(c)["depends_on"], [a])


# ===========================================================================
# W4d — CONTRÔLE STRUCTUREL : `plan_depends` forcé à None par monkeypatch.
# ===========================================================================
class ControleStructurelTests(_Banc):
    def _sans_module(self):
        return mock.patch.object(tasks, "plan_depends_module", return_value=None)

    def test_w4d_marqueur_present_toute_mutation_refusee_octet_identique(self):
        """W4d (i)-(iii). MUTANT : le contrôle en tête de `set_depends` retiré ⇒
        (i) `--retirer` d'un ORDRE PILOTE passe sans module, rouge ; MUTANT 2 :
        marqueur ignoré (jamais refuser) ⇒ (i) rouge."""
        a, b, c = self.new(3)
        self.specs(["S-00000001"])
        self.dep(c, [a, b], motif=[OP1, TECH])
        self.armer()
        avant = self.store.read_bytes()
        with self._sans_module():
            msg = self.refus(self.dep, c, [], retirer=a)                 # (i) verbe neuf : refusé quel que soit le marqueur
            self.assertIn(REMEDE, msg)
            self.assertIn(REMEDE_DEUX, msg)                              # opus T4 : ancien texte ⇒ rouge
            self.assertIn(ABSENT_DEUX, msg)
            for kw in ({"clear": True}, {"motif": TECH}):                # (iii), (ii) verbes anciens : refusés PARCE QUE le marqueur est armé
                msg = self.refus(self.dep, c, [b] if "motif" in kw else [], **kw)
                self.assertIn("INEXPLOITABLE", msg)
                self.assertIn(REMEDE, msg)
                self.assertIn(REMEDE_DEUX, msg)
                self.assertIn(ABSENT_DEUX, msg)
        self.assertEqual(self.store.read_bytes(), avant)

    def test_w4d_marqueur_absent_verbe_neuf_refuse_verbe_ancien_inerte(self):
        """W4d (iv)-(v). MUTANT 3 : `verbe_neuf` réduit à deux verbes ⇒ (iv)
        rouge sur le troisième ; MUTANT 2 (toujours refuser) ⇒ (v) rouge."""
        a, b, c = self.new(3)
        self.dep(c, [a, b], motif=TECH)
        avant = self.store.read_bytes()
        with self._sans_module():
            for kw in ({"add": True}, {"retirer": a}, {"retirer_ordre_pilote": [a, "S-00000002"]}):
                msg = self.refus(self.dep, c, [b] if "add" in kw else [], motif=TECH if "add" in kw else "", **kw)
                self.assertIn(REMEDE, msg)                                # (iv)
            self.assertEqual(self.store.read_bytes(), avant)
            self.assertIn("depends_on = 1 dependency", self.dep(c, [b], motif=TECH))  # (v) comme AVANT T-765
        self.assertEqual(self.read(c)["depends_on"], [b])
        self.assertEqual(self.read(c)["depends_motif"], {b: TECH})

    def test_w4d_sans_dependances_sans_module_refuse_marqueur_ou_non(self):
        """W4d (vi) (R8). MUTANT : le contrôle `--sans-dependances` non vide +
        `plan_depends_module() is None` retiré aux deux sites start/done ⇒ le
        drapeau neuf passe en silence, rouge."""
        a, b = self.new(2)
        for armer in (False, True):
            if armer:
                self.armer()
            with self._sans_module():
                msg = self.refus(tasks.set_state, self.root, a, "running", sans_dependances="x")
                self.assertIn(REMEDE, msg)
                msg = self.refus(tasks.set_state, self.root, b, "done", stage="clos", sans_dependances="x")
                self.assertIn(REMEDE, msg)
        self.assertEqual(self.read(a)["state"], "pending")


# ===========================================================================
# W4e — les remèdes qui ne détruisent rien, et leur REPLI sans module.
# ===========================================================================
class RemedesTests(_Banc):
    def _writesets(self, *tids: str):
        for i, tid in enumerate(tids):
            tasks.set_writeset(self.root, tid, [f"src/{i}/"])

    def test_w4e_groupe_parallele_retirer_puis_rejoue(self):
        """W4e. MUTANT : `declare_parallel_group` revient à `--motif "…"`/`--clear`
        ⇒ `--retirer <chain[1]>` absent, rouge."""
        a, b, c = self.new(3)
        self._writesets(a, b, c)
        self.dep(a, [b, c], motif=[TECH, "technique : c"])
        msg = self.refus(tasks.declare_parallel_group, self.root, [a, b])
        self.assertIn(f"depends {a} --retirer {b}", msg)
        self.assertIn(c, msg)
        self.assertNotIn("--clear", msg)
        self.dep(a, [], retirer=b)  # rejoué
        self.assertEqual(self.read(a)["depends_on"], [c])
        self.assertEqual(self.read(a)["depends_motif"], {c: "technique : c"})
        self.assertIn("declared", tasks.declare_parallel_group(self.root, [a, b]))

    def test_w4e_chemin_tout_ordre_pilote_route_suggestion(self):
        """W4e. MUTANT : `remede_coupe` ne saute plus les ORDRE PILOTE ⇒ un
        `--retirer T-` sur un ordre pilote est prescrit, rouge."""
        a, b = self.new(2)
        self._writesets(a, b)
        self.specs(["S-00000001"])
        self.dep(a, [b], motif=OP1)
        msg = self.refus(tasks.declare_parallel_group, self.root, [a, b])
        self.assertIn("SUGGESTION:", msg)
        self.assertIn(f"--retirer-ordre-pilote {b}", msg)
        self.assertNotIn("--retirer T-", msg)

    def test_w4e_refus_de_cycle_de_set_depends_prescrit_retirer(self):
        """W4e. MUTANT : le refus de cycle revient à `--clear` ⇒ rouge."""
        a, b, c = self.new(3)
        self.dep(b, [a], motif=TECH)
        self.dep(c, [b], motif=TECH)
        avant = self.store.read_bytes()
        msg = self.refus(self.dep, a, [c], motif=TECH)
        self.assertIn("cycle", msg)
        self.assertIn(f"depends {c} --retirer {b}", msg)
        self.assertNotIn("--clear", msg)
        self.assertEqual(self.store.read_bytes(), avant)

    def test_w4e_repli_sans_module_textes_d_avant_a_l_octet(self):
        """W4e BRAS REPLI (A-C4). MUTANT : un repli qui appelle
        `_pd.remede_coupe` sans tester `_pd` ⇒ `AttributeError`, rouge."""
        a, b, c = self.new(3)
        self._writesets(a, b, c)
        self.dep(b, [a], motif=TECH)
        self.dep(c, [b], motif=TECH)
        with mock.patch.object(tasks, "plan_depends_module", return_value=None):
            # marqueur ABSENT : refus de cycle d'AVANT T-765, à l'octet (:3493, `cycle[-2]` = b).
            msg = self.refus(self.dep, a, [c], motif=TECH)
            self.assertIn(f"clear the declaration with `tasks.py depends {b} --clear`", msg)
            # `declare_parallel_group` rend le texte d'AVANT (:3650-3652).
            msg = self.refus(tasks.declare_parallel_group, self.root, [b, a])
            self.assertIn(f"`tasks.py depends {b} --clear`", msg)
            self.dep(c, [b, a], motif=TECH)
            msg = self.refus(tasks.declare_parallel_group, self.root, [c, b])
            self.assertIn(f"`tasks.py depends {c} {a} --motif \"…\"`", msg)
            # marqueur PRÉSENT : même texte d'avant, et le `--clear` prescrit ⇒ refusé (W4d iii).
            self.armer()
            msg = self.refus(tasks.declare_parallel_group, self.root, [b, a])
            self.assertIn("--clear", msg)
            self.assertIn(REMEDE, self.refus(self.dep, b, [], clear=True))
        self.assertEqual(self.read(b)["depends_on"], [a])


# ===========================================================================
# W4f, W11, W14 — `delete`, `depends-show`, parité de la constante.
# ===========================================================================
class LecturesTests(_Banc):
    def test_w4f_delete_de_l_amont_d_un_ordre_pilote_avertit_en_plus(self):
        """W4f (R4). MUTANT : la ligne supplémentaire supprimée ⇒ rouge ; la
        ligne existante (:3770-3773) survit à l'octet dans les deux cas."""
        a, b = self.new(2)
        self.specs(["S-00000001"])
        self.dep(b, [a], motif=OP1)
        sortie = tasks.delete_task(self.root, a)
        self.assertIn(f"warning: {b} depended on deleted {a} — link cleared; {b} is NOT released, it was never held", sortie)
        self.assertIn("loses an ORDRE PILOTE edge", sortie)
        self.assertIn(OP1, sortie)
        self.assertNotIn("depends_on", self.read(b))
        # Module absent : la ligne existante survit, la supplémentaire ne peut pas s'imprimer.
        c, d = self.new(2)
        self.dep(d, [c], motif=OP1)
        with mock.patch.object(tasks, "plan_depends_module", return_value=None):
            sortie = tasks.delete_task(self.root, c)
        self.assertIn(f"warning: {d} depended on deleted {c} — link cleared", sortie)
        self.assertNotIn("loses an ORDRE PILOTE", sortie)

    def test_w11_depends_show_rend_les_trois_classes(self):
        """W11. MUTANT : `classe_motif` rendu constant ⇒ une classe manque, rouge."""
        a, b, c, d = self.new(4)
        self.specs(["S-00000001"])
        self.cli("depends", d, a, b, c, "--motif", OP1, "--motif", "ordre revise (S-1)", "--motif", TECH)
        vue = tasks.render_depends_show(self.root, d)
        self.assertIn(f"{a} → pending : EN ATTENTE (motif : {OP1}) · ordre pilote", vue)
        self.assertIn("· ordre (non canonique)", vue)
        self.assertIn(f"(motif : {TECH}) · technique", vue)
        self.inject(d, [a])
        self.assertIn("(SANS MOTIF (héritée)) · technique", tasks.render_depends_show(self.root, d))
        with mock.patch.object(tasks, "plan_depends_module", return_value=None):
            self.assertNotIn("·", tasks.render_depends_show(self.root, d))

    def test_w14_ordre_pilote_canonique_deux_copies_identiques_pas_trois(self):
        """W14. MUTANT : changer l'une des deux copies ⇒ rouge (M24 : une seule copie
        élargie au `S-<ULID>`, T-00001040). `tasks.py` n'en porte AUCUNE (S-00002684) :
        il lit celle de `plan_depends`."""
        pw = _charger("plan_waves_parite", WAVES)
        self.assertEqual(pw.ORDRE_PILOTE_CANONIQUE.pattern, pd.ORDRE_PILOTE_CANONIQUE.pattern)
        self.assertEqual(pd.ORDRE_PILOTE_CANONIQUE.pattern,
                         r"^ORDRE PILOTE S-(?:[0-9A-HJKMNP-TV-Z]{26}|\d{8})\b")
        self.assertFalse(hasattr(tasks, "ORDRE_PILOTE_CANONIQUE"))
        lus = sorted(BIN.glob("tasks*.py"))
        self.assertIn(TASKS, lus, f"filet à vide : la façade n'est pas lue ({lus})")
        self.assertGreaterEqual(len(lus), 2, f"filet à vide : façade sans ses parties ({lus})")
        texte = "".join(p.read_text(encoding="utf-8") for p in lus)
        # Négatif NON contournable (clôture du lot 95d6220a..c964c9a6, F7) : `S-[0-9]{8}`
        # échappait à un `assertNotIn(r"S-\d{8}")` littéral.
        self.assertIsNone(re.search(r"S-(?:\\d|\[0-9\])\{8\}", texte))
        self.assertNotIn("ORDRE PILOTE S-(?:", texte)


# T-00001040 — GRAMMAIRE D'ID DE `plan_depends`, DEUX COLONNES (étape 4 du plan de
# T-00000726, réserve B-C8). Fixtures FIXES : U_LETTER finit par une lettre, U8 ouvre
# par HUIT chiffres puis des lettres (un motif qui lirait l'ancien d'abord le
# couperait), U10 par DIX chiffres.
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U8 = "01234567ABCDEFGHJKMNPQRSTV"
U10 = "0123456789ABCDEFGHJKMNPQRS"


class GrammaireUlidTests(unittest.TestCase):
    def test_ordre_pilote_canonique_et_son_sid(self):
        """ORDRE_PILOTE_CANONIQUE et _SID_DU_MOTIF (ancrés en tête, bornés par `\\b`).
        MUTANTS : branche ULID retirée, branche `\\d{8}` retirée (R2), `(?i)` (R3) ⇒ rouge."""
        for sid in (f"S-{U_LETTER}", f"S-{U8}", f"S-{U10}", "S-00000001"):
            with self.subTest(sid=sid):
                motif = f"ORDRE PILOTE {sid} : a avant c"
                self.assertIsNotNone(pd.ORDRE_PILOTE_CANONIQUE.match(motif), motif)
                self.assertEqual(pd._SID_DU_MOTIF.match(motif).group(1), sid)
        for sid in (f"S-0{U_LETTER}", f"S-{U_LETTER}A", f"S-{U_LETTER.lower()}", "S-1", "S-000000001"):
            with self.subTest(refuse=sid):
                motif = f"ORDRE PILOTE {sid} : a avant c"
                self.assertIsNone(pd.ORDRE_PILOTE_CANONIQUE.match(motif), motif)
                self.assertIsNone(pd._SID_DU_MOTIF.match(motif), motif)

    def test_sid_ancre_par_fullmatch_ascii(self):
        """_SID (E24 : forme T-00001085 gardée, `fullmatch`, ASCII). MUTANTS : R1
        (`[0-9]{1,12}` → `[0-9]{8}`) ⇒ `S-1` refusé ; `[0-9]` → `\\d` ⇒ `S-١٢٣` accepté ;
        R3 `(?i)` ⇒ minuscules acceptées ; R4 (`{1,13}`) ⇒ 13 chiffres acceptés."""
        for sid in (f"S-{U_LETTER}", f"S-{U8}", "S-00000001", "S-1", "S-" + "9" * 12):
            with self.subTest(sid=sid):
                self.assertIsNotNone(pd._SID.fullmatch(sid), sid)
        for sid in ("S-00001\n", f"S-{U_LETTER}\n", "S-١٢٣", f"S-0{U_LETTER}", f"S-{U_LETTER.lower()}",
                    f"S-{U_LETTER[:-1]}", "S-" + "9" * 13, f"T-{U_LETTER}", ""):
            with self.subTest(refuse=sid):
                self.assertIsNone(pd._SID.fullmatch(sid), repr(sid))

    def test_arete_extrait_les_deux_ids_entiers(self):
        """_ARETE : ULID et ancien (court compris) lus ENTIERS ; `T-0<ULID>` et
        `T-<ULID>A` ne font pas une ligne conforme. MUTANTS : branche ULID retirée,
        borne `(?![0-9A-Za-z])` retirée ⇒ rouge."""
        for aval, amont in ((f"T-{U_LETTER}", "T-00000002"), ("T-012", f"T-{U8}"), (f"T-{U10}", f"T-{U_LETTER}")):
            with self.subTest(aval=aval, amont=amont):
                m = pd._ARETE.match(f"ARÊTE: {aval} <- {amont} | technique : amont livre")
                self.assertIsNotNone(m)
                self.assertEqual((m.group(1), m.group(2)), (aval, amont))
        for aval in (f"T-0{U_LETTER}", f"T-{U_LETTER}A", f"T-{U_LETTER.lower()}"):
            with self.subTest(refuse=aval):
                self.assertIsNone(pd._ARETE.match(f"ARÊTE: {aval} <- T-00000002 | technique"))

    def test_suggestion_extrait_les_deux_ids_entiers(self):
        """SUGGESTION_RE : même grammaire que `_ARETE`. MUTANT : branche ULID retirée ⇒ rouge."""
        for aval, amont in ((f"T-{U_LETTER}", "T-00000002"), ("T-012", f"T-{U8}")):
            with self.subTest(aval=aval, amont=amont):
                m = pd.SUGGESTION_RE.match(f"SUGGESTION: retirer {aval} <- {amont}")
                self.assertIsNotNone(m)
                self.assertEqual((m.group(2), m.group(3)), (aval, amont))
        self.assertIsNone(pd.SUGGESTION_RE.match(f"SUGGESTION: ajouter T-0{U_LETTER} <- T-00000002"))
        self.assertIsNone(pd.valider_suggestion("delta", f"SUGGESTION: ajouter T-{U_LETTER} <- T-00000002", "raison"))


# E17 (T-00001040) — LES OUTILS DU BACKLOG, versionnés (5206b580), RECOPIENT la grammaire
# d'id. Lus en TEXTE, jamais importés (`board_import.py` importe PyYAML, absent de la porte).
# adopting-tree: docs/interne ne voyage pas — OutilsBacklogGrammaireTests saute, nommé
OUTILS_BACKLOG = ROOT / "docs" / "interne" / "chantier" / "backlog" / "tools"
# Littéraux d'id attendus par fichier et par colonne : un site NEUF non élargi, ou un
# site perdu, change le compte (filet à vide refusé).
SITES_BACKLOG = {
    "board_import.py": {"canon": 2, "ancree": 2, "recherche": 1},
    "backlog_gen.py": {"canon": 1},
    "merge_fragments.py": {"recherche": 1},
}


def _litteraux_d_id(chemin: Path) -> list[tuple[str, int]]:
    """`(motif, drapeaux)` de chaque `re.compile|search|match|fullmatch` dont le motif
    littéral nomme un id `S-`/`T-` — extrait par `ast`, sans rien exécuter du fichier."""
    import ast
    import re

    trouves = []
    for noeud in ast.walk(ast.parse(chemin.read_text(encoding="utf-8"))):
        if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                and isinstance(noeud.func.value, ast.Name) and noeud.func.value.id == "re"
                and noeud.func.attr in ("compile", "search", "match", "fullmatch") and noeud.args):
            continue
        motif = noeud.args[0]
        if not (isinstance(motif, ast.Constant) and isinstance(motif.value, str)):
            continue
        if "S-" not in motif.value and "T-" not in motif.value:
            continue
        drapeaux = 0
        for d in [*noeud.args[1:], *(k.value for k in noeud.keywords if k.arg == "flags")]:
            if isinstance(d, ast.Attribute) and d.attr in ("I", "IGNORECASE"):
                drapeaux |= re.IGNORECASE
        trouves.append((motif.value, drapeaux))
    return trouves


def _colonne(motif: str) -> str:
    if motif.startswith("^ORDRE PILOTE"):
        return "canon"
    if motif.startswith("\\A"):
        return "ancree"
    return "recherche"


class OutilsBacklogGrammaireTests(unittest.TestCase):
    """MUTANTS : M3b (ULID posé en SECOND dans une copie backlog) ⇒ parité ou
    extraction de `T-<U8>` rouge ; M24b (une seule copie backlog élargie) ⇒
    `test_chaque_site_est_elargi_et_compte` et parité rouges."""

    def _lire(self, nom: str) -> list[tuple[str, int]]:
        chemin = OUTILS_BACKLOG / nom
        if not chemin.is_file():
            self.skipTest(f"docs/interne ne voyage pas : {nom} absent (arbre adoptant)")
        return _litteraux_d_id(chemin)

    def test_chaque_site_est_elargi_et_compte(self):
        for nom, attendu in SITES_BACKLOG.items():
            with self.subTest(outil=nom):
                lits = self._lire(nom)
                compte: dict[str, int] = {}
                for motif, _ in lits:
                    compte[_colonne(motif)] = compte.get(_colonne(motif), 0) + 1
                    self.assertIn("[0-9A-HJKMNP-TV-Z]{26}", motif, f"{nom} : site non élargi {motif!r}")
                self.assertEqual(compte, attendu, f"{nom} : {lits}")

    def test_quatre_copies_de_l_ordre_pilote_identiques(self):
        """Parité : `plan_depends` (ORDRE_PILOTE_CANONIQUE, _SID_DU_MOTIF), `plan_waves`,
        `board_import` (CANON, CANON_ID), `backlog_gen` (CANON)."""
        pw = _charger("plan_waves_parite_backlog", WAVES)
        canons = [pd.ORDRE_PILOTE_CANONIQUE.pattern, pw.ORDRE_PILOTE_CANONIQUE.pattern]
        captures = [pd._SID_DU_MOTIF.pattern]
        for nom in ("board_import.py", "backlog_gen.py"):
            for motif, _ in self._lire(nom):
                if _colonne(motif) == "canon":
                    (captures if "(S-" in motif else canons).append(motif)
        self.assertEqual(len(canons), 4, canons)
        self.assertEqual(len(captures), 2, captures)
        self.assertEqual(len(set(canons)), 1, canons)
        self.assertEqual(len(set(captures)), 1, captures)

    def test_deux_colonnes_sur_les_fixtures(self):
        import re

        for nom in SITES_BACKLOG:
            for motif, drapeaux in self._lire(nom):
                colonne = _colonne(motif)
                with self.subTest(outil=nom, motif=motif):
                    if colonne == "canon":
                        for sid in (f"S-{U_LETTER}", f"S-{U8}", "S-00000001"):
                            m = re.match(motif, f"ORDRE PILOTE {sid} : a avant c", drapeaux)
                            self.assertIsNotNone(m, sid)
                            if m.groups():
                                self.assertEqual(m.group(1), sid)
                        for sid in (f"S-0{U_LETTER}", f"S-{U_LETTER.lower()}", "S-1"):
                            self.assertIsNone(re.match(motif, f"ORDRE PILOTE {sid} : a", drapeaux), sid)
                    elif colonne == "ancree":
                        for tid in (f"T-{U_LETTER}", f"T-{U8}", "T-00000001"):
                            self.assertIsNotNone(re.match(motif, tid, drapeaux), tid)
                        for tid in ("T-00000001\n", f"T-{U_LETTER}\n", f"T-0{U_LETTER}",
                                    f"T-{U_LETTER.lower()}", "T-012"):
                            self.assertIsNone(re.match(motif, tid, drapeaux), repr(tid))
                    elif "T-" in motif:
                        for tid in (f"T-{U_LETTER}", f"T-{U8}", "T-00000001"):
                            m = re.search(motif, f"TASKS: {tid} → pending", drapeaux)
                            self.assertIsNotNone(m, tid)
                            self.assertEqual(m.group(1), tid)
                        for tid in (f"T-0{U_LETTER}", f"T-{U_LETTER}A"):
                            self.assertIsNone(re.search(motif, f"TASKS: {tid} → pending", drapeaux), tid)
                    else:
                        # Détecteur de mots d'ordre (merge_fragments, `re.I`) : il SIGNALE, il ne
                        # refuse pas — la sur-détection sous `re.I` est acceptée, nommée (plan).
                        for sid in (f"S-{U_LETTER}", f"S-{U8}", "S-00000001"):
                            m = re.search(motif, f"selon {sid}", drapeaux)
                            self.assertIsNotNone(m, sid)
                            self.assertEqual(m.group(0), sid)


if __name__ == "__main__":
    unittest.main()
