#!/usr/bin/env python3
"""LES JAMBES DE DÉPENDANCES — grammaire `ARÊTE:`, `start`/`done`, trace
`plan approuvé`, SUGGESTION, `--sans-dependances` — T-00000765
(W5-W10, W12, W13, W8b, W8c, W16, W16b).

ZÉRO APPEL LLM : `tasks.py`, `specs.py`, `plan_cible.py`, `plan_depends.py`
chargés par chemin (`spec_from_file_location`, comme `test_plan_cible_guard.py`),
board/SPECS/marqueur posés sous `tmp_path`. Les bancs CLI passent
`CADRE_STATE_DIR`/`CADRE_PROJECT_ROOT`/`AGENTS_EVENTS_DIR` sur un `mktemp`.

*** CHAQUE TÉMOIN PORTE SON MUTANT *** (joué sur COPIE jetable, L-00000487).
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / ".agents" / "bin"
TASKS = BIN / "tasks.py"
SPECS = BIN / "specs.py"

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
tasks = _charger("tasks_depends_guard", TASKS)
specs = _charger("specs_depends_guard", SPECS)
# Le résolveur du kit, chargé PAR CHEMIN (patron v3prep) : la source de `ids.py` est le paquet
# `cadre` de la racine, où qu'il vive (`.agents/vendor/cadre` ou `src/cadre`).
_VENDOR = _charger("_plan_depends_guard_vendor_paths", BIN / "vendor_paths.py")
# UN SEUL objet module par nom, quel que soit l'ordre de collecte de pytest.
tasks._PLAN_CIBLE_MOD = pc
tasks._PLAN_DEPENDS_MOD = pd
specs._PLAN_CIBLE_MOD = pc
specs._PLAN_DEPENDS_MOD = pd

CHANTIER = "refonte"
PLAN = (
    "# Plan de banc\n"
    "Tâches : {roster}\n"
    "{aretes}"
    "## Steps\n"
    "1. étape une\n"
    "   décision pilote: S-00001558\n"
)


class _Banc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "specs", "local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        (self.d / "plans").mkdir()
        (self.d / "spec.md").write_text("**« un invariant »**\n", encoding="utf-8")
        self.root = str(self.d)

    def tearDown(self):
        self._tmp.cleanup()

    # -- outillage ------------------------------------------------------------
    def new(self, chantier: str | None = CHANTIER) -> str:
        return tasks.new_task(self.root, "tache de banc", "", chantier or "").split()[1]

    def armer(self):
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            f"spec=spec.md\nchantier={CHANTIER}\n", encoding="utf-8")

    def plan(self, rel: str, roster: str, aretes: str = "", queue: bytes = b"") -> str:
        """`queue` : octets BRUTS ajoutés (un plan non UTF-8, opus T2)."""
        p = self.d / rel
        p.write_bytes(PLAN.format(roster=roster, aretes=aretes).encode("utf-8") + queue)
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def specs_json(self, entrees: list[dict]):
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 99999, "entries": entrees}, ensure_ascii=False),
            encoding="utf-8")

    def entrees(self) -> list[dict]:
        return json.loads((self.d / ".agents" / "state" / "specs" / "SPECS.json")
                          .read_text(encoding="utf-8"))["entries"]

    @staticmethod
    def decision(sid: str, tid: str) -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": "une décision",
                "text": "", "date": "2026-09-27"}

    @staticmethod
    def trace(sid: str, tid: str, rel: str, sha: str, title: str = "plan approuvé") -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": title,
                "text": f"plan={rel} sha256={sha}", "date": "2026-09-27"}

    def approuve(self, tid: str, aretes: str = "", roster: str | None = None,
                 rel: str = "plans/p.md", sid: str = "S-00002000") -> str:
        """Plan approuvé pour `tid` (trace R1 propre), marqueur armé."""
        sha = self.plan(rel, roster or tid, aretes)
        self.specs_json([self.decision("S-00001558", tid), self.trace(sid, tid, rel, sha)])
        self.armer()
        return sha

    def data(self) -> dict:
        return tasks.load(self.root)

    def stage(self, tid: str) -> str:
        return next(t for t in self.data()["tasks"] if t["id"] == tid).get("stage") or ""

    def start(self, tid: str, **kw) -> str:
        return tasks.set_state(self.root, tid, "running", **kw)

    def done(self, tid: str, **kw) -> str:
        return tasks.set_state(self.root, tid, "done", stage="clos par le banc", **kw)

    def refus(self, fn, *args, exc=None, **kw) -> str:
        with self.assertRaises(exc or tasks.BoardError) as caught:
            fn(*args, **kw)
        return str(caught.exception)

    def cli(self, script: Path, *args: str):
        env = {**os.environ, "CADRE_STATE_DIR": self._tmp.name, "CADRE_PROJECT_ROOT": self._tmp.name,
               "AGENTS_EVENTS_DIR": self._tmp.name, "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run([sys.executable, str(script), "--root", self.root, *args],
                              capture_output=True, text=True, timeout=120, env=env)


def arete(aval: str, amont: str, motif: str = "technique : amont livre") -> str:
    return f"ARÊTE: {aval} <- {amont} | {motif}\n"


# ===========================================================================
# W5-W7 — les jambes `start` et `done`.
# ===========================================================================
class JambesTests(_Banc):
    def test_w5_start_refuse_arete_non_inscrite_puis_passe_apres_add(self):
        """W5. MUTANT : `jambe_start` non appelée dans `set_state` ⇒ le start
        passe avec une ARÊTE: non inscrite, rouge. Depuis S-01M4Z5VMP5E9YN8T6EMDTBAF0T
        l'amont inscrit est CLOS avant le `start` (jambe d'amont), et la trace re-datée
        au jour de sa clôture (S- numérique, jugée à la journée) — jamais `--sans-dependances`."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, arete(t1, t2))
        msg = self.refus(self.start, t1)
        self.assertIn(f"{t1} <- {t2}", msg)
        self.assertIn(f"depends {t1} {t2} --add --motif", msg)
        self.assertIn("--sans-dependances", msg)
        tasks.set_depends(self.root, t1, [t2], motif="technique : amont livre", add=True)
        self.assertIn("deps-ready: AMONT_OUVERT", self.refus(self.start, t1))
        self.done(t2, sans_cible="banc : amont clos hors de son plan")
        self.specs_json([dict(e, date=datetime.now().date().isoformat()) for e in self.entrees()])
        self.assertIn("→ running", self.start(t1))

    def test_w5_le_refus_ne_consomme_aucune_trace_de_chaine(self):
        """W5 (chaîne). MUTANT : jambe placée APRÈS `consume_plan_chain` ⇒ les
        traces sont effacées par un start refusé, rouge."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, arete(t1, t2))
        (self.d / ".agents" / "state" / "gates" / "PLAN_CHAIN_REQUIRED").touch()
        quand = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for nom in ("plan-critic", "plan-critic-sonnet-max", "planner"):
            role = "reviewer" if "critic" in nom else "planner"
            (self.d / ".agents" / "state" / "local" / "plan" / f"{nom}.json").write_text(
                json.dumps({"at": quand, "sha": "abc", "role": role}), encoding="utf-8")
        r = self.cli(TASKS, "start", t1)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(f"{t1} <- {t2}", r.stderr)
        traces = sorted(p.name for p in (self.d / ".agents/state/local/plan").glob("*.json"))
        self.assertEqual(traces, ["plan-critic-sonnet-max.json", "plan-critic.json", "planner.json"])

    def test_w6_done_refuse_par_r1_et_par_r2(self):
        """W6. MUTANT : `jambe_done` non appelée ⇒ rouge ; MUTANT 2 : `slot=False`
        au `done` ⇒ le plan du slot n'est plus lu, le bras R2 rougit."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, arete(t1, t2))
        self.assertIn(f"{t1} <- {t2}", self.refus(self.done, t1))
        tasks.set_depends(self.root, t1, [t2], motif="technique : amont livre", add=True)
        self.assertIn("→ done", self.done(t1))
        # R2 : le plan du slot `running` NOMME la tâche ; elle n'a pas de trace propre.
        slot, t3, t4 = self.new(), self.new(), self.new()
        sha = self.plan("plans/slot.md", f"{slot} {t3}", arete(t3, t4))
        self.specs_json([self.decision("S-00001558", slot), self.trace("S-00002001", slot, "plans/slot.md", sha)])
        self.start(slot, sans_dependances="slot de banc")
        msg = self.refus(self.done, t3)
        self.assertIn(f"{t3} <- {t4}", msg)
        self.assertIn("[cible relevée sur", msg)

    def test_w7_pont_v3_ne_leve_jamais_dit_et_marque(self):
        """W7. MUTANT : la jambe lève sous `sans_cible` ⇒ le pont V3 est refusé,
        rouge ; MUTANT 2 : la marque omise ⇒ rouge."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, arete(t1, t2))
        sortie = tasks.set_state(
            self.root, t1, "done",
            stage="clos par le pont V3 — statut done (op 1)",
            sans_binome="clôture automatique du pont V3 : aucun sous-agent critique",
            sans_cible="clôture automatique du pont V3 : aucun plan approuvé à relire")
        self.assertIn(f"TASKS: {t1} → done\nTASKS: {t1} close SANS contrôle des dépendances du plan "
                      f"(sous --sans-cible) : {t1} <- {t2}", sortie)
        self.assertIn(f"[SANS DÉPENDANCES : relevé sous --sans-cible — {t1} <- {t2}]", self.stage(t1))
        # CLI humain `done --sans-cible` : même marque.
        t3, t4 = self.new(), self.new()
        self.approuve(t3, arete(t3, t4), sid="S-00002002")
        r = self.cli(TASKS, "done", t3, "--raison", "x", "--sans-cible", "humain")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[SANS DÉPENDANCES : relevé sous --sans-cible", self.stage(t3))
        # Rien ne manque : ni ligne ni marque.
        t5, t6 = self.new(), self.new()
        self.approuve(t5, arete(t5, t6), sid="S-00002003")
        tasks.set_depends(self.root, t5, [t6], motif="technique : amont livre", add=True)
        self.assertNotIn("SANS contrôle", self.done(t5, sans_cible="x"))
        self.assertNotIn("SANS DÉPENDANCES", self.stage(t5))

    def test_w7_r1_module_absent_sous_sans_cible_jamais_refuse(self):
        """W7 bras R1. MUTANT : le refus « module absent » au `done` non gardé
        par `not sans_cible` ⇒ le pont V3 est refusé, rouge."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, arete(t1, t2))
        with mock.patch.object(tasks, "plan_depends_module", return_value=None):
            self.assertIn("INEXPLOITABLE", self.refus(self.done, t1))
            self.assertIn("→ done", self.done(t1, sans_cible="pont V3"))


# ===========================================================================
# W8, W8b, W8c — la trace `plan approuvé`, le régime, l'unique lecteur.
# ===========================================================================
class ApprobationTests(_Banc):
    def test_w8_plan_approuve_refuse_night_eligible_passe(self):
        """W8. MUTANT : filtre de titre retiré ⇒ `night-eligible: approved` est
        recontrôlé et refusé, rouge (A-C3 : asymétrie ASSUMÉE). MUTANT 2 (exec-critic
        T-765) : pré-filtre de `specs.py` plus étroit que `normalise_titre` (ex.
        `lower().split()`) ⇒ « plàn approuvé », trace R1 VALIDE, échappe, rouge."""
        t1, t2 = self.new(), self.new()
        sha = self.plan("plans/p.md", t1, arete(t1, t2))
        self.specs_json([self.decision("S-00001558", t1)])
        self.armer()
        texte = f"plan=plans/p.md sha256={sha} verdict=S-00001558 approved=2026-09-27"
        msg = self.refus(specs.add_entry, self.root, t1, "decision", "plan approuvé", texte, exc=specs.SpecsError)
        self.assertIn(f"{t1} <- {t2}", msg)
        self.assertIn("--add --motif", msg)
        # Pré-filtre = `normalise_titre` (NFD, combinants retirés, casefold, espaces) : AUCUNE
        # trace R1 valide n'y échappe — accent ajouté, ṕ précomposé, forme toute décomposée.
        for titre in (" Plan \t approuvé", "plàn approuvé", "ṕlan approuvé", "ṕlan approuvé"):
            self.assertIn(pc.normalise_titre(titre), pc.TITRES_APPROBATION, titre)  # R1 pour `resoudre_plan`
            self.refus(specs.add_entry, self.root, t1, "decision", titre, texte, exc=specs.SpecsError)
        self.assertIn("added", specs.add_entry(self.root, t1, "decision", "night-eligible: approved", texte))
        # Le filtre de la JAMBE, seul (le pré-filtre de `specs.py` le masquerait sinon) :
        self.assertIsNone(pd.refus_dependances_a_lapprobation(self.root, t1, "decision", "night-eligible: approved", texte))
        r = self.cli(SPECS, "add", "--task", t1, "--kind", "decision", "plan approuvé", "--text", texte)
        self.assertEqual(r.returncode, 2, r.stdout)
        tasks.set_depends(self.root, t1, [t2], motif="technique : amont livre", add=True)
        r = self.cli(SPECS, "add", "--task", t1, "--kind", "decision", "plan approuvé", "--text", texte)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_w8_approbation_controle_tout_aval_enrole(self):
        """W8 (TOUT aval). MUTANT : seules les arêtes de `task` contrôlées ⇒ une
        arête d'un AUTRE aval enrôlé manque sans refus, rouge."""
        t1, t2, t3 = self.new(), self.new(), self.new()
        sha = self.plan("plans/p.md", f"{t1} {t2}", arete(t1, t3) + arete(t2, t3))
        self.specs_json([self.decision("S-00001558", t1)])
        self.armer()
        tasks.set_depends(self.root, t1, [t3], motif="technique : amont livre", add=True)
        msg = self.refus(specs.add_entry, self.root, t1, "decision", "plan approuvé",
                         f"plan=plans/p.md sha256={sha}", exc=specs.SpecsError)
        self.assertIn(f"{t2} <- {t3}", msg)
        self.assertNotIn(f"{t1} <- {t3}", msg)

    def test_w8b_hors_chantier_ou_marqueur_absent_cinq_jambes_inertes(self):
        """W8b. MUTANT : test de chantier retiré ⇒ une tâche hors chantier est
        refusée, rouge ; MUTANT 2 : retour sur marqueur absent retiré ⇒ rouge."""
        t1, t2, t3 = self.new(chantier="autre"), self.new(), self.new()  # t3 DANS le chantier
        sha = self.plan("plans/p.md", f"{t1} {t3}", arete(t1, t2) + arete(t3, t2))
        self.specs_json([self.decision("S-00001558", t1), self.trace("S-00002000", t1, "plans/p.md", sha),
                         self.trace("S-00002001", t3, "plans/p.md", sha)])
        self.armer()
        self.assertIsNotNone(pd.jambe_start(self.root, t3, self.data())[0])  # non-vacuité : armé, t3 mord
        for armer in (True, False):
            if not armer:
                (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").unlink()
            data = self.data()
            for tid in ((t1,) if armer else (t1, t3)):  # marqueur absent : même t3 se tait
                self.assertEqual(pd.jambe_start(self.root, tid, data), (None, [], None))
                self.assertEqual(pd.jambe_done(self.root, tid, data, sans_dependances="", sans_cible=""), (None, [], None))
                self.assertIsNone(pd.refus_dependances_a_lapprobation(
                    self.root, tid, "decision", "plan approuvé", f"plan=plans/p.md sha256={sha}"))
                self.assertIsNone(pc.refus_au_start(self.root, tid, data))
                self.assertEqual(pc.evaluer_done(self.root, tid, data), (None, ""))
                self.assertIsNone(pc.refus_au_verdict(self.root, tid, "verdict", "plan-critic GO", "plan=plans/p.md"))

    def test_w8c_un_seul_lecteur_du_regime(self):
        """W8c. `_arme_pour_tache` forcé à None sur marqueur ARMÉ ⇒ les CINQ
        jambes inertes. MUTANT : une jambe garde sa lecture inline du marqueur ⇒
        elle mord encore, rouge."""
        t1, t2 = self.new(), self.new()
        sha = self.approuve(t1, arete(t1, t2))
        self.plan("plans/incomplet.md", t1)
        data = self.data()
        # Témoin de non-vacuité : sans le patch, les jambes MORDENT.
        self.assertIsNotNone(pd.jambe_start(self.root, t1, data)[0])
        with mock.patch.object(pc, "_arme_pour_tache", return_value=None):
            self.assertEqual(pd.jambe_start(self.root, t1, data), (None, [], None))
            self.assertEqual(pd.jambe_done(self.root, t1, data, sans_dependances="", sans_cible=""), (None, [], None))
            self.assertIsNone(pd.refus_dependances_a_lapprobation(
                self.root, t1, "decision", "plan approuvé", f"plan=plans/p.md sha256={sha}"))
            self.assertIsNone(pc.refus_au_start(self.root, t1, data))
            self.assertEqual(pc.evaluer_done(self.root, t1, data), (None, ""))
            self.assertIsNone(pc.refus_au_verdict(self.root, t1, "verdict", "plan-critic GO",
                                                  "plan=plans/incomplet.md"))


# ===========================================================================
# W9, W10 — grammaire fermée, SUGGESTION.
# ===========================================================================
class GrammaireTests(_Banc):
    def test_w9_grammaire_fermee(self):
        """W9. MUTANT : mot-clé rendu insensible à la casse ⇒ `arête : …` est lu,
        rouge (le compte d'arêtes passe à 3)."""
        t1, t2 = "T-00000001", "T-00000002"
        texte = (
            f"# P\nTâches : {t1}\n"
            f"ARÊTE: {t1} <- {t2} | technique : x\n"
            f"- ARETE: {t1} <- {t2} | ordre\n"
            f"```\nARÊTE: {t1} <- T-00000009 | dans un bloc, ignorée\n```\n"
            f"arête : {t1} <- {t2} | non lu\n"
            f"arête: {t1} <- {t2} | non lu non plus (MAJUSCULES seulement)\n"
            f"DEPENDANCES: {t1} avant {t2}, prose libre\n"
        )
        enrolle = lambda tid: pc.enrolling_line(texte, tid)  # noqa: E731
        aretes, fautives, aucune = pd.aretes_du_plan(texte, enrolle, {t1, t2})
        self.assertEqual([(a.aval, a.amont, a.motif) for a in aretes],
                         [(t1, t2, "technique : x"), (t1, t2, "ordre")])
        self.assertEqual(fautives, [])
        self.assertFalse(aucune)
        fautif = (
            f"Tâches : {t1}\nARÊTE: bidule\nARÊTE: {t1} <- {t2} | /chemin\n"
            f"ARÊTE: {t1} <- {t2} | {'m' * 501}\nARÊTE: {t1} <- {t1} | auto\n"
            f"ARÊTE: T-00000005 <- {t2} | non enrôlé\nARÊTE: {t1} <- T-00000077 | inconnu\n"
            f"ARÊTES: aucune\nARÊTE: {t1} <- {t2} | ok\n"
        )
        enrolle = lambda tid: pc.enrolling_line(fautif, tid)  # noqa: E731
        aretes, fautives, aucune = pd.aretes_du_plan(fautif, enrolle, {t1, t2})
        self.assertEqual(len(aretes), 1)
        self.assertTrue(aucune)
        attendu = ["ligne malformée", "ne commence pas par `/`", "501 caractères", "auto-arête",
                   "n'ENRÔLE pas T-00000005", "T-00000077 est inconnu", "`ARÊTES: aucune` à côté"]
        self.assertEqual(len(fautives), len(attendu), fautives)
        for f, a in zip(fautives, attendu):
            self.assertIn(a, f)
        # Et au `start`, les fautives sont NOMMÉES dans le refus.
        t1, t2 = self.new(), self.new()
        self.approuve(t1, "ARÊTE: bidule\n")
        self.assertIn("ligne malformée 'ARÊTE: bidule'", self.refus(self.start, t1))

    def test_w10_suggestion_grammaire_et_texte(self):
        """W10. MUTANT : `valider_suggestion` retirée de `specs.add_entry` ⇒
        `SUGGESTION: blabla` s'écrit, rouge."""
        t1 = self.new()
        self.specs_json([])
        for titre, texte in (("SUGGESTION: blabla", "raison"),
                             ("SUGGESTION: ajouter T-00000001 <- T-00000002", ""),
                             ("SUGGESTION: retirer T-00000001 <- T-00000001", "raison")):
            self.refus(specs.add_entry, self.root, t1, "delta", titre, texte, exc=specs.SpecsError)
        self.assertEqual(self.entrees(), [])
        self.assertIn("added", specs.add_entry(self.root, t1, "delta",
                                               "SUGGESTION: retirer T-00000001 <- T-00000002", "le pilote tranche"))
        self.assertIsNone(pd.valider_suggestion("decision", "SUGGESTION: blabla", ""))  # kind ≠ delta : hors champ
        r = self.cli(SPECS, "add", "--task", t1, "--kind", "delta", "SUGGESTION: n'importe quoi", "--text", "x")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("malformé", r.stderr)


# ===========================================================================
# W12, W13 — `--sans-dependances`, séparation de la phrase.
# ===========================================================================
class DerogationTests(_Banc):
    def test_w12_sans_dependances_marque_start_done_et_trace(self):
        """W12. MUTANT : `text = marque` (remplace au lieu de joindre) ⇒ plus de
        `plan=`, `resoudre_plan` ne résout plus, rouge ; MUTANT 2 : `sha256=`
        accepté dans la raison ⇒ rouge. Les deux épingles du `start` (texte de la
        marque, marque sur racine désarmée) CÈDENT à S-01M4Z5VMP5E9YN8T6EMDTBAF0T : la
        marque est celle de la jambe d'amont, `arête + amont`, posée quel que soit le
        marqueur ; celle du `done` (pas de jambe d'amont) ne change pas."""
        t1, t2 = self.new(), self.new()
        sha = self.approuve(t1, arete(t1, t2))
        self.start(t1, sans_dependances="banc : arête volontairement absente")
        self.assertIn("[SANS DÉPENDANCES : arête + amont — banc : arête volontairement absente]", self.stage(t1))
        self.done(t1, sans_dependances="banc, au done")
        self.assertIn("[SANS DÉPENDANCES : banc, au done]", self.stage(t1))
        # Sur la trace `specs.py` : texte conservé, `resoudre_plan` résout TOUJOURS le même plan.
        t3, t4 = self.new(), self.new()
        sha3 = self.plan("plans/p3.md", t3, arete(t3, t4))
        texte = f"plan=plans/p3.md sha256={sha3} verdict=S-00001558 approved=2026-09-27"
        specs.add_entry(self.root, t3, "decision", "plan approuvé", texte,
                        sans_dependances="plan figé avant T-765")
        derniere = self.entrees()[-1]
        self.assertEqual(derniere["text"], f"{texte} [SANS DÉPENDANCES : plan figé avant T-765]")
        resolu = pc.resoudre_plan(self.root, t3, self.data(), slot=False)
        self.assertIsNotNone(resolu)
        self.assertEqual(resolu[0].name, "p3.md")
        msg = self.refus(specs.add_entry, self.root, t3, "decision", "plan approuvé", texte,
                         sans_dependances=f"voir sha256={sha}", exc=specs.SpecsError)
        self.assertIn("sha256=", msg)
        # Marqueur ABSENT : la marque d'amont est posée quand même (la jambe d'amont n'est pas armée par lui).
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").unlink()
        self.start(t3, sans_dependances="x")
        self.assertIn("[SANS DÉPENDANCES : arête + amont — x]", self.stage(t3))

    def test_w13_separation_de_la_phrase(self):
        """W13. MUTANT (a) : absence des deux formes traitée comme un manque ⇒
        `start` refuse un plan figé, rouge ; MUTANT (b) : absence traitée comme
        inerte à la trace ⇒ la NOUVELLE trace passe, rouge."""
        t1 = self.new()
        sha = self.approuve(t1)  # aucune des deux formes
        self.assertIn("→ running", self.start(t1))
        self.assertIn("→ done", self.done(t1))
        msg = self.refus(specs.add_entry, self.root, t1, "decision", "plan approuvé",
                         f"plan=plans/p.md sha256={sha}", exc=specs.SpecsError)
        self.assertIn("NI `ARÊTE:` NI `ARÊTES: aucune`", msg)
        self.assertIn("--sans-dependances", msg)
        # `ARÊTES: aucune` : la forme vide passe partout.
        t2 = self.new()
        sha2 = self.approuve(t2, "ARÊTES: aucune\n", rel="plans/p2.md", sid="S-00002004")
        self.assertIn("→ running", self.start(t2))
        self.assertIn("added", specs.add_entry(self.root, t2, "decision", "plan approuvé",
                                               f"plan=plans/p2.md sha256={sha2}"))


# ===========================================================================
# W17-W24 — passe de correction du binôme de clôture T-765 (S-00002827).
# ===========================================================================
OP = "ORDRE PILOTE S-00001558 : amont avant aval"


class BinomeClotureTests(_Banc):
    def test_w17_ordre_pilote_leve_jamais_reinscrit_par_add_et_commandes_uniques(self):
        """W17 (fable F1 BLOQUANT, F7). Un ORDRE PILOTE levé par `--retirer-ordre-pilote`,
        puis `start` : le remède ne porte AUCUNE ligne `--add` exécutable pour cette arête.
        MUTANT : `_commande` rend `commande_add()` pour un ordre pilote ⇒ rouge ; MUTANT 2 :
        `_uniques` sauté ⇒ deux lignes pour une arête déclarée deux fois, rouge."""
        t1, t2, t3 = self.new(), self.new(), self.new()
        sha = self.plan("plans/p.md", t1, arete(t1, t2, OP) + arete(t1, t2, OP) + arete(t1, t3) + arete(t1, t3))
        self.specs_json([self.decision("S-00001558", t1), self.decision("S-00001559", t1),
                         self.trace("S-00002000", t1, "plans/p.md", sha)])
        self.armer()
        tasks.set_depends(self.root, t1, [t2], motif=OP, add=True)
        tasks.set_depends(self.root, t1, [], retirer_ordre_pilote=[t2, "S-00001559"])  # LEVÉ par le pilote
        msg = self.refus(self.start, t1)
        lignes = [ligne.strip() for ligne in msg.split("\n")]
        op = [ligne for ligne in lignes if f"depends {t1} {t2} --add" in ligne]
        self.assertEqual(len(op), 1, msg)
        self.assertTrue(op[0].startswith(f"# ORDRE PILOTE {t1} <- {t2} : s'il a été LEVÉ, le plan est PÉRIMÉ"), op[0])
        tech = [ligne for ligne in lignes if f"depends {t1} {t3} --add" in ligne]
        self.assertEqual(len(tech), 1, msg)
        self.assertTrue(tech[0].startswith("python .agents/bin/tasks.py depends"), tech[0])  # technique : exécutable
        self.assertIn("porte 2 ARÊTE(S)", msg)

    def test_w18_plan_non_utf8_refus_nomme_ou_dire_jamais_d_exception(self):
        """W18 (opus T2 BLOQUANT). Plan approuvé non UTF-8 : `start` refuse NOMMÉ, la trace
        refuse NOMMÉ, le `done` du pont V3 (`--sans-cible`) passe et MARQUE. MUTANT :
        `_lire_plan` rendu à `read_text` nu ET `ValueError` retiré des captures ⇒
        `UnicodeDecodeError` au `done`, rouge ; MUTANT 2 : `ValueError` seul retiré de
        `jambe_done` ⇒ le bras R2 (garde d'enrôlement de `plan_cible`, lecture NUE) lève."""
        t1, t2 = self.new(), self.new()
        sha = self.plan("plans/latin1.md", t1, arete(t1, t2), queue=b"# caf\xe9\n")
        self.specs_json([self.decision("S-00001558", t1), self.trace("S-00002000", t1, "plans/latin1.md", sha)])
        self.armer()
        self.assertIn("latin1.md illisible en UTF-8", self.refus(self.start, t1, sans_cible="la cible saute"))
        self.assertIn("latin1.md illisible en UTF-8", self.refus(
            specs.add_entry, self.root, t1, "decision", "plan approuvé", f"plan=plans/latin1.md sha256={sha}",
            exc=specs.SpecsError))
        self.assertIn("contrôle impossible", self.done(t1, sans_cible="pont V3"))
        self.assertIn("[SANS DÉPENDANCES : contrôle impossible sous --sans-cible — plan approuvé latin1.md "
                      "illisible en UTF-8", self.stage(t1))
        # R2 : le plan du SLOT est lu nu par `plan_cible` (garde d'enrôlement) — seule la capture `ValueError` tient.
        slot, t3 = self.new(), self.new()
        sha2 = self.plan("plans/slot.md", f"{slot} {t3}", arete(t3, t2), queue=b"\xff\n")
        self.specs_json(self.entrees() + [self.trace("S-00002001", slot, "plans/slot.md", sha2)])
        self.start(slot, sans_dependances="slot de banc", sans_cible="slot de banc")
        self.done(t3, sans_cible="pont V3")
        self.assertIn("contrôle impossible sous --sans-cible — garde des dépendances de plan : lecture "
                      "impossible (UnicodeDecodeError", self.stage(t3))

    def test_w19_mode_dire_marque_dans_chaque_cas_jamais_ne_leve(self):
        """W19 (opus T3 ; M26, M27). Sous `--sans-cible` : lignes fautives ⇒ ligne ET marque ;
        exception ⇒ ligne ET marque bornée ; module absent sous marqueur ⇒ marque. MUTANT M26 :
        la branche `releve.refus` du DIRE retirée ⇒ fautives tues, rouge ; MUTANT M27 : la
        capture sous `sans_cible` rend un refus ⇒ le pont V3 est refusé, rouge ; MUTANT 3 :
        marque « module absent » retirée de `set_state` ⇒ rouge."""
        t1, t2 = self.new(), self.new()
        self.approuve(t1, "ARÊTE: bidule\n")
        sortie = self.done(t1, sans_cible="pont V3")
        self.assertIn(f"TASKS: {t1} close SANS contrôle des dépendances du plan (sous --sans-cible) : "
                      f"lignes `ARÊTE:` fautives dans p.md", sortie)
        self.assertIn("[SANS DÉPENDANCES : relevé sous --sans-cible — lignes ARÊTE: fautives dans p.md]", self.stage(t1))
        data = self.data()
        for exc in (pd.CibleError("marqueur\nmalformé " + "x" * 400), OSError("disque"), ValueError("codec")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(pd, "refus_dependances", side_effect=exc):
                refus, lignes, marque = pd.jambe_done(self.root, t2, data, sans_dependances="", sans_cible="pont")
                self.assertIsNone(refus)
                self.assertIn("contrôle impossible", lignes[0])
                self.assertTrue(marque.startswith("[SANS DÉPENDANCES : contrôle impossible sous --sans-cible — "))
                self.assertLessEqual(len(marque), len("[SANS DÉPENDANCES : contrôle impossible sous --sans-cible — ]") + 200)
                self.assertNotIn("\n", marque)
                self.assertIsNotNone(pd.jambe_done(self.root, t2, data, sans_dependances="", sans_cible="")[0])
        with mock.patch.object(tasks, "plan_depends_module", return_value=None):
            self.done(t2, sans_cible="pont V3")
        self.assertIn("[SANS DÉPENDANCES : plan_depends absent, relevé sous --sans-cible]", self.stage(t2))

    def test_w20_amont_purge_dit_jamais_refuse_la_trace_refuse_toujours(self):
        """W20 (fable F2). Un amont PURGÉ après l'approbation : `start`/`done` passent et le
        DISENT sur stderr ; la trace `plan approuvé` refuse toujours l'id inconnu. MUTANT :
        `connus=set(taches)` rendu à `refus_dependances` ⇒ refus perpétuel, rouge."""
        t1, t2 = self.new(), self.new()
        sha = self.approuve(t1, arete(t1, t2))
        tasks.delete_task(self.root, t2)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIn("→ running", self.start(t1))
            self.assertIn("→ done", self.done(t1))
        self.assertIn(f"non contrôlée — {t2} absent du board (purgé ?)", err.getvalue())
        msg = self.refus(specs.add_entry, self.root, t1, "decision", "plan approuvé",
                         f"plan=plans/p.md sha256={sha}", exc=specs.SpecsError)
        self.assertIn(f"{t2} est inconnu du board", msg)

    def test_w21_ligne_proche_du_mot_cle_nommee_la_prose_reste_ignoree(self):
        """W21 (fable F5). MUTANT : `_proche_du_mot_cle` rendu constant `False` ⇒ les sept
        variantes sont ignorées en silence, rouge ; MUTANT 2 : `_PROCHE` insensible à la
        casse ⇒ la prose `arête :` devient fautive, rouge."""
        t1, t2 = "T-00000001", "T-00000002"
        corps = f"{t1} <- {t2} | technique"
        variantes = [f"ARÊTE : {corps}", f"* ARÊTE: {corps}", f"  - ARÊTE: {corps}", f"**ARÊTE:** {corps}",
                     f"> ARÊTE: {corps}", "ARÊTE: " + corps, "1. ARÊTES : aucune"]
        prose = [f"arête : {corps}", f"Arête: {corps}", "ARÊTES-TU ?", f"voir `ARÊTE: {corps}`"]
        texte = f"# P\nTâches : {t1}\n" + "\n".join(variantes + prose) + "\n"
        aretes, fautives, aucune = pd.aretes_du_plan(texte, lambda t: pc.enrolling_line(texte, t), {t1, t2})
        self.assertEqual((aretes, aucune), ([], False))
        self.assertEqual(len(fautives), len(variantes), fautives)
        self.assertTrue(all(f.startswith("ligne proche du mot-clé") for f in fautives), fautives)
        # Et au `start` d'un plan approuvé, la ligne est NOMMÉE dans le refus.
        a, b = self.new(), self.new()
        self.approuve(a, f"**ARÊTE:** {a} <- {b} | technique\n")
        self.assertIn("ligne proche du mot-clé", self.refus(self.start, a))

    def test_w22_aucune_sauf_fautive_et_filtre_d_aval(self):
        """W22 (fable F6 : M1, M2). MUTANT M1 : `_AUCUNE` sans ancre `$` ⇒ `ARÊTES: aucune
        sauf …` lu comme la forme vide, rouge ; MUTANT M2 : filtre `a.aval == tid` retiré de
        `refus_dependances` ⇒ `start` d'une tâche refusé pour l'arête d'une AUTRE, rouge."""
        t1, t2 = "T-00000001", "T-00000002"
        texte = f"# P\nTâches : {t1}\nARÊTES: aucune sauf {t2}\n"
        aretes, fautives, aucune = pd.aretes_du_plan(texte, lambda t: pc.enrolling_line(texte, t), {t1, t2})
        self.assertFalse(aucune)
        self.assertEqual(len(fautives), 1)
        self.assertIn("ligne malformée", fautives[0])
        a, b, c = self.new(), self.new(), self.new()
        self.approuve(a, arete(b, c), roster=f"{a} {b}")  # l'arête manquante est celle de b, pas de a
        self.assertIn("→ running", self.start(a))
        self.assertIn("→ done", self.done(a))

    def test_w23_frere_casse_desarme_ne_fait_pas_planter_start_done(self):
        """W23 (opus T5). `plan_depends_module` qui LÈVE (frère cassé), marqueur ABSENT : `start`
        et `done` passent sans le charger. MUTANT : chargement inconditionnel rétabli ⇒ rouge."""
        t1 = self.new()
        with mock.patch.object(tasks, "plan_depends_module", side_effect=SyntaxError("frère cassé")):
            self.assertIn("→ running", self.start(t1))
            self.assertIn("→ done", self.done(t1))

    def test_w24_specs_module_absent_nomme_plan_cible(self):
        """W24 (opus T4). Module absent : le refus de `specs.py` dit « ou son import
        `plan_cible.py` » et prescrit la restauration des DEUX. MUTANT : ancien texte ⇒ rouge."""
        t1 = self.new()
        self.armer()
        with mock.patch.object(specs, "_plan_depends_module", return_value=None):
            for kw in ({"sans_dependances": "x"}, {}):
                msg = self.refus(specs.add_entry, self.root, t1, "decision", "plan approuvé", "plan=x", exc=specs.SpecsError, **kw)
                self.assertIn("ou son import `plan_cible.py` est ABSENT", msg)
                self.assertIn("git checkout -- .agents/bin/plan_depends.py .agents/bin/plan_cible.py", msg)

    def test_w25_plan_non_utf8_sans_derogation_refus_de_la_garde_de_cible(self):
        """W25 (frère de W18, SANS `--sans-cible`). Plan approuvé non UTF-8 : `start`, `done`
        et le verdict `plan-critic` sortent rc 2 par le refus de la garde de CIBLE, jamais par
        un traceback, et n'écrivent rien. MUTANT : `ValueError` retiré d'une des trois captures
        (`tasks.py` start/done, `specs.py` verdict) ⇒ `UnicodeDecodeError` rc 1 + Traceback, rouge."""
        t1, t2 = self.new(), self.new()
        sha = self.plan("plans/latin1.md", t1, arete(t1, t2), queue=b"# caf\xe9\n")
        self.specs_json([self.decision("S-00001558", t1), self.trace("S-00002000", t1, "plans/latin1.md", sha)])
        self.armer()
        for script, *args in ((TASKS, "start", t1), (TASKS, "done", t1, "--raison", "banc"),
                              (SPECS, "add", "--task", t1, "--kind", "verdict", "plan-critic GO",
                               "--text", "plan=plans/latin1.md")):
            with self.subTest(geste=args[0]):
                r = self.cli(script, *args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("can't decode", r.stderr)
        self.assertEqual(next(t for t in self.data()["tasks"] if t["id"] == t1)["state"], "pending")
        self.assertEqual(len(self.entrees()), 2)


# ===========================================================================
# W26-W27 — T-00001062 : `--retirer-ordre-pilote` compare la décision à TOUTES
# les S-id que le motif cite, jamais à la première seule.
# ===========================================================================
OP_RATIFIE = "ORDRE PILOTE S-00001558 : amont avant aval (ratifié, S-00001559)"
OP_T1008 = ("ORDRE PILOTE S-00003347 : le correctif réducteur précède toute migration de "
            "sync_correlations (portée BK-415..419 ratifiée, S-00003364)")


class RetraitOrdrePiloteTests(_Banc):
    def test_w26_une_decision_citee_par_le_motif_ne_leve_jamais_son_ordre(self):
        """W26. Ratification citée en 2e S-id : le retrait sous elle est REFUSÉ (CLI rc 2,
        puis API), l'arête et son motif restent ; une décision NON citée lève. MUTANT 1 :
        première S-id seule (HEAD d8138a24) ⇒ rouge ; MUTANT 3 : refus dès que le motif
        cite 2 S-id ⇒ la levée sous S-00001560 rougit."""
        t1, t2 = self.new(), self.new()
        self.specs_json([self.decision(s, t1) for s in ("S-00001558", "S-00001559", "S-00001560")])
        tasks.set_depends(self.root, t1, [t2], motif=OP_RATIFIE, add=True)
        r = self.cli(TASKS, "depends", t1, "--retirer-ordre-pilote", t2, "S-00001559")  # le geste mesuré
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("propre retrait", r.stderr)
        for sid in ("S-00001558", "S-00001559"):
            msg = self.refus(tasks.set_depends, self.root, t1, [], retirer_ordre_pilote=[t2, sid])
            self.assertIn("propre retrait", msg)
            self.assertIn(sid, msg)
        tache = next(t for t in self.data()["tasks"] if t["id"] == t1)
        self.assertEqual(tache["depends_on"], [t2])
        self.assertEqual(tache["depends_motif"], {t2: OP_RATIFIE})
        msg = tasks.set_depends(self.root, t1, [], retirer_ordre_pilote=[t2, "S-00001560"])
        self.assertIn("sous S-00001560", msg)
        self.assertNotIn("depends_on", next(t for t in self.data()["tasks"] if t["id"] == t1))

    def test_w27_table_pure_des_citations(self):
        """W27. `valider_retrait_ordre_pilote` sur une table : motif réel de T-1008 (board,
        2026-10-02), forme courte, ULID cité, décision distincte, 3e citation sur 4, corps
        de 5000 chiffres. MUTANT 2 : égalité de CHAÎNE au lieu de la clé numérique ⇒ la
        forme courte `S-1559` rougit ; MUTANT 4 : extraction `S-(\\d{8})` ⇒ forme courte
        et ULID rougissent ; M5 (classe `[0-9A-Z]+`) et M6 (`.upper()` retiré) ⇒ l'ULID
        en minuscules rougit ; M7 (borne à gauche retirée) ⇒ `BKS-12` rougit ; `int(corps)`
        (rév. 1 du plan) ⇒ la ligne à 5000 chiffres LÈVE ; X9 (clé numérique par préfixe
        de chiffres) ⇒ la clé ULID rougit ; X10/X11 (première-ou-dernière citation, deux
        premières) ⇒ la 3e citation sur 4 rougit.

        BORNES de `plan_depends._SIDS_CITES` / `_cle_sid` (écrites ICI, S-00002684 : le module
        reste sous 800 lignes ; borne relevée à 1600 par S-00004034). Citation = `S-<alnum>`, S majuscule, tiret ASCII, bornée à
        gauche : `BKS-12` n'en est pas une, `s-12` non lue, `S-12a` lue en clé chaîne `12A`.
        Clé : chiffres ⇒ zéros de tête ôtés, JAMAIS `int()` (un corps de 5000 chiffres lèverait,
        et sur-capturer doit seulement REFUSER davantage) ; sinon chaîne en majuscules (ULID).
        Un ULID n'échappe à la collision avec `S-<chiffres>` que si son corps porte une lettre :
        un corps de 26 chiffres se clé comme un entier (T-1040 tranche, R19)."""
        decisions = {"S-00003347", "S-00003364", "S-00009999", "S-00001558", "S-00001559",
                     "S-00000001"}
        ulid = "S-01J9ZQ4M8XKTB2V7R5N3HWPDFC"
        cas = (
            (OP_T1008, "S-00003364", True),
            (OP_T1008, "S-00003347", True),
            (OP_T1008, "S-00009999", False),
            ("ORDRE PILOTE S-00001558 : x (S-1559)", "S-00001559", True),
            ("ORDRE PILOTE S-00001558 : x (S-00001559)", "S-00009999", False),
            ("ORDRE PILOTE S-00001558 : a (S-00003347) b (S-00001559) c (S-00009999)", "S-00001559", True),
            ("ORDRE PILOTE S-00001558 : x (S-01J9ZQ4M8XKTB2V7R5N3HWPDFC)", "S-00000001", False),
            ("ORDRE PILOTE S-00001558 : x S-" + "9" * 5000, "S-00001559", False),
        )
        for motif, sid, refuse in cas:
            with self.subTest(motif=motif[:90], sid=sid):
                avant = {"id": "T-00000001", "depends_on": ["T-00000002"],
                         "depends_motif": {"T-00000002": motif}}
                refus = pd.valider_retrait_ordre_pilote(avant, "T-00000002", sid, decisions)
                if refuse:
                    self.assertIsNotNone(refus)
                    self.assertIn("propre retrait", refus)
                else:
                    self.assertIsNone(refus)
        self.assertIn(pd._cle_sid(ulid[2:]), pd.sids_cites(f"ORDRE PILOTE S-00001558 : x ({ulid})"))
        self.assertEqual(pd._cle_sid(ulid[2:])[0], "s")
        self.assertIn(("s", ulid[2:]), pd.sids_cites(f"ORDRE PILOTE S-00001558 : x (S-{ulid[2:].lower()})"))
        self.assertEqual(pd.sids_cites("ORDRE PILOTE S-00001558 : x BKS-12"), {("n", "1558")})


# ===========================================================================
# W16 — isolation d'import (M13), en sous-processus réel.
# ===========================================================================
class IsolationTests(unittest.TestCase):
    def _run(self, script: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-c", script], cwd=cwd,
                                  capture_output=True, text=True, timeout=60)

    def test_w16_tasks_et_specs_ne_tirent_ni_plan_cible_ni_plan_depends(self):
        """W16. MUTANT : `import plan_depends` remonté en tête de `tasks.py` ou
        de `specs.py` ⇒ rouge."""
        r = self._run(
            "import sys\n"
            f"sys.path.insert(0, {str(BIN)!r})\n"
            "import tasks, specs\n"
            "assert 'plan_cible' not in sys.modules and 'plan_depends' not in sys.modules, sys.modules.keys()\n"
            "print('LAZY-OK')\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LAZY-OK", r.stdout)

    def test_w16_plan_depends_ne_tire_ni_tasks_ni_specs_ni_night_approve(self):
        """W16. MUTANT : `import tasks` ajouté à `plan_depends.py` ⇒ rouge."""
        r = self._run(
            "import sys\n"
            f"sys.path.insert(0, {str(BIN)!r})\n"
            "import plan_depends\n"
            "interdits = [m for m in ('tasks', 'specs', 'night_approve') if m in sys.modules]\n"
            "assert not interdits, interdits\n"
            "print('ISOLE-OK')\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ISOLE-OK", r.stdout)

    def test_w16b_frere_casse_ne_fait_planter_aucune_lecture(self):
        """W16b (exec-critic T-765). SyntaxError dans une COPIE de `plan_cible.py`
        puis de `plan_depends.py` : `list`, `--statusline`, `depends-show` (tâche
        AVEC arête), `specs.py list` et les deux `--help` rendent rc 0 sans
        traceback ; l'aide retombe sur la chaîne courte. MUTANTS : `AIDE_CLI` lu
        hors -h/--help, ou `lecture=True` retiré (aide ou depends-show) ⇒ rouge.
        HARNAIS QUI ALLOUE (E13, T-00001040) : disposition `<tmp>/.agents/bin/`, avec
        `record_id.py` et `<tmp>/src/cadre/ledger/ids.py` provisionnés — dès la
        bascule de T-00000726, `new` exige le générateur (MUTANT M29' : `ids.py`
        non provisionné ⇒ rouge sous le simulacre de C2)."""
        for casse in ("plan_cible.py", "plan_depends.py"):
            with self.subTest(casse=casse), tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                bin_ = d / ".agents" / "bin"
                bin_.mkdir(parents=True)
                for sub in ("board", "specs"):
                    (d / ".agents" / "state" / sub).mkdir(parents=True)
                for nom in ("specs.py", "plan_cible.py", "plan_depends.py", "record_id.py",
                            *(p.name for p in BIN.glob("tasks*.py"))):
                    (bin_ / nom).write_bytes((BIN / nom).read_bytes())
                generateur = d / "src" / "cadre" / "ledger"
                generateur.mkdir(parents=True)
                # Destination : le repli `src/cadre` du `record_id.py` copié (aucun `vendor_paths.py` ici).
                (generateur / "ids.py").write_bytes((_VENDOR.exiger(ROOT, "cadre") / "ledger" / "ids.py").read_bytes())
                env = {**os.environ, "CADRE_STATE_DIR": tmp, "CADRE_PROJECT_ROOT": tmp,
                       "AGENTS_EVENTS_DIR": tmp, "PYTHONDONTWRITEBYTECODE": "1"}

                def run(script: str, *args: str) -> subprocess.CompletedProcess:
                    return subprocess.run([sys.executable, str(bin_ / script), "--root", tmp, *args],
                                          capture_output=True, text=True, timeout=120, env=env)

                amont = run("tasks.py", "new", "amont").stdout.split()[1]
                aval = run("tasks.py", "new", "aval").stdout.split()[1]
                r = run("tasks.py", "depends", aval, amont, "--motif", "technique : amont livre")
                self.assertEqual(r.returncode, 0, r.stderr)
                # Module SAIN : l'aide porte bien `AIDE_CLI` (sinon le repli serait le seul chemin).
                self.assertIn("No relevance test", " ".join(run("tasks.py", "depends", "--help").stdout.split()))
                self.assertIn("carries plan= or sha256=", " ".join(run("specs.py", "add", "--help").stdout.split()))
                chemin = bin_ / casse
                chemin.write_text(chemin.read_text(encoding="utf-8") + "\ndef (:\n", encoding="utf-8")
                sorties = {}
                for script, *args in (("tasks.py", "list"), ("tasks.py", "--statusline"),
                                      ("tasks.py", "depends-show", aval), ("specs.py", "list"),
                                      ("tasks.py", "depends", "--help"), ("specs.py", "add", "--help")):
                    r = run(script, *args)
                    self.assertEqual(r.returncode, 0, f"{script} {args}: {r.stdout}{r.stderr}")
                    self.assertNotIn("Traceback", r.stderr, f"{script} {args}")
                    sorties[(script, *args)] = " ".join(r.stdout.split())
                self.assertIn(amont, sorties[("tasks.py", "depends-show", aval)])
                self.assertIn("(help: .agents/bin/plan_depends.py)", sorties[("tasks.py", "depends", "--help")])


class RemedesQuotesTests(unittest.TestCase):
    """T-01M5CS8B2EJR8P4D4TSVJ2GJYZ — un id du board est une DONNÉE : chaque commande
    que `plan_depends` imprime (span entre accents graves qui ouvre par `tasks.py`,
    `specs.py`, `python .agents/bin/` ou `--retirer `) passe l'id ENTIER, sans
    l'exécuter. Fonctions PURES, aucun board. Oracle par site : NOMBRE de spans du
    message, aucune expansion vivante (`$ ; | & < >` et accent grave hors `'…'`, seuls
    les placeholders `"<pourquoi>"`, `S-<decision>`, `S-<decision du pilote>` exemptés),
    `shlex.split` ÉGAL au découpage attendu (id entier à sa place, SUGGESTION en UN
    argument). Les HUIT sites de l'étape 2 du plan (lignes de la base bfa51a8f) sont
    couverts, ni plus ni moins. Borne : shell POSIX seul ; un caractère de contrôle
    dans un id n'est pas couvert. MUTANT : un site rendu brut ⇒ son `subTest` rouge ;
    un quotage maison qui entoure de `'…'` sans échapper l'apostrophe ⇒ rouge aussi :
    les DEUX ids portent une apostrophe ET un `$(…)`, donc à chaque place d'id ; un id
    passé entre `"…"` (où `$(…)` vit) ⇒ rouge."""

    X, W = "x'; echo $(echo PWN); echo '7", "w'$(echo PWN)'8"
    SITES = ("Arete.commande_add:191", "valider_retrait_ordre_pilote:596",
             "motif_ordre_pilote_refus:624", "remede_coupe:674", "remede_coupe:680",
             "remede_coupe:682", "appliquer_verbe:724", "appliquer_verbe:764")
    PLACEHOLDERS = ('"<pourquoi>"', "S-<decision du pilote>", "S-<decision>")
    TETES = ("tasks.py ", "specs.py ", "python .agents/bin/", "--retirer ")

    @classmethod
    def _spans(cls, texte: str) -> list[str]:
        return [s for s in texte.split("`")[1::2] if s.startswith(cls.TETES)]

    @classmethod
    def _vivant(cls, commande: str) -> bool:
        for p in cls.PLACEHOLDERS:
            commande = commande.replace(p, "")
        etat, i = "", 0
        while i < len(commande):
            ch = commande[i]
            if etat == "'":
                etat = "" if ch == "'" else etat
            elif ch == "\\":
                i += 1
            elif etat == '"':
                if ch in "$`":
                    return True
                etat = "" if ch == '"' else etat
            elif ch in "'\"":
                etat = ch
            elif ch in "$;|&<>`":
                return True
            i += 1
        return False

    def _refus(self, appel) -> str:
        with self.assertRaises(ValueError) as ctx:
            appel()
        return str(ctx.exception)

    def _cas(self) -> list[tuple[str, str, int, int, list[str]]]:
        """(site, message, spans attendus dans le message, rang du span du site, découpage attendu)."""
        x, w = self.X, self.W
        technique = {"id": x, "depends_on": [w], "depends_motif": {w: "technique : banc"}}
        ordre = {"id": x, "depends_on": [w], "depends_motif": {w: "ORDRE PILOTE S-00000001 : banc"}}
        coupe_tech = pd.remede_coupe({"tasks": [technique, {"id": w}]}, [x, w])
        coupe_ordre = pd.remede_coupe({"tasks": [ordre, {"id": w}]}, [x, w])

        def verbe(avant, mode, deps=(), motifs=(), retrait=None):
            return lambda: pd.appliquer_verbe(
                avant, list(deps), list(motifs), mode=mode, resoudre=lambda r: r,
                cycle_de=lambda _w: None, decisions=set(), taches=[], retrait=retrait)

        retrait_op = ["tasks.py", "depends", x, "--retirer-ordre-pilote", w, "S-<decision>"]
        return [
            ("Arete.commande_add:191", "`" + pd.Arete(x, w, "technique : banc").commande_add() + "`", 1, 0,
             ["python", ".agents/bin/tasks.py", "depends", x, w, "--add", "--motif", "technique : banc"]),
            ("valider_retrait_ordre_pilote:596",
             pd.valider_retrait_ordre_pilote(technique, w, "S-00000001", set()), 1, 0,
             ["tasks.py", "depends", x, "--retirer", w]),
            ("motif_ordre_pilote_refus:624", pd.motif_ordre_pilote_refus(ordre, [], {}), 1, 0, retrait_op),
            ("remede_coupe:674", coupe_tech, 1, 0, ["tasks.py", "depends", x, "--retirer", w]),
            ("remede_coupe:680", coupe_ordre, 2, 0,
             ["specs.py", "add", "--task", x, "--kind", "delta", f"SUGGESTION: retirer {x} <- {w}",
              "--text", "<pourquoi>"]),
            ("remede_coupe:682", coupe_ordre, 2, 1,
             ["tasks.py", "depends", x, "--retirer-ordre-pilote", w, "S-<decision", "du", "pilote>"]),
            ("appliquer_verbe:724", self._refus(verbe(ordre, "retirer", retrait=(w, None))), 1, 0, retrait_op),
            ("appliquer_verbe:764",
             self._refus(verbe(technique, "add", deps=[w], motifs=["technique : autre"])), 1, 0,
             ["--retirer", w]),
        ]

    def test_chaque_remede_imprime_passe_l_id_entier(self) -> None:
        couverts = []
        for site, message, n_spans, rang, attendu in self._cas():
            with self.subTest(site=site):
                spans = self._spans(message)
                self.assertEqual(len(spans), n_spans, f"{len(spans)} commande(s), {n_spans} attendue(s) : {message}")
                span = spans[rang]
                self.assertFalse(self._vivant(span), f"expansion vivante : {span}")
                try:
                    decoupe = shlex.split(span)
                except ValueError as exc:
                    self.fail(f"indécoupable {exc} : {span}")
                self.assertEqual(decoupe, attendu, f"id coupé ou déplacé : {span}")
            couverts.append(site)
        self.assertEqual(tuple(couverts), self.SITES, "les HUIT sites de l'étape 2, ni plus ni moins")


if __name__ == "__main__":
    unittest.main()
