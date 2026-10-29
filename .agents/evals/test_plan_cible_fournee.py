"""LE LIEN DE LOT de la cible de plan (`plan_cible._resoudre`, T-01M4V1JD628K07PXF7FFDSN0Q3).

Une tâche qui porte `fournee = {parent, lot, sha256, …}` (écrit par `tasks.py
fournee`, jamais à la main) résout le plan de la trace `plan approuvé` ÉLUE de son
parent — au `start` comme au `done`, sans enrôlement, parent `running` ou non — si
l'empreinte du plan est celle du lien et qu'il porte `LOT: <clé>`. La note posée au
board : `[cible relevée sur <parent> — lot <clé>]`. Sinon R3, la cause NOMMÉE.

Témoins joués ARMÉS (`PLAN_CIBLE_REQUIRED`, `chantier=*`) et DÉSARMÉS. Le module est
chargé PAR CHEMIN, en processus, sur une racine jetable ; un mutant est une copie
jetable de `plan_cible.py` dont une ancre (présente UNE fois) est remplacée, et il
doit rougir son témoin par une ASSERTION. Un témoin de bout en bout passe par la CLI
(`fournee`, puis `done` d'un lot planifié). ZÉRO APPEL LLM.
"""

from __future__ import annotations

import hashlib
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
BIN = ROOT / ".agents" / "bin"
SPEC = "# Spec du banc\n\n**« contrat déclaré »** — le contrat du banc.\n"
PARENT, LOT = "T-01M4V1JD628K07PXF7FFDSN0AA", "T-01M4V1JD628K07PXF7FFDSN0BB"
PLAN = "docs/tasks/plan.md"


def plan_texte(parent: str, annote: bool = True) -> str:
    etape = "cible: « contrat déclaré »" if annote else "sans annotation"
    return (f"# PLAN — {parent}\n\n## Steps\n1. faire — {etape}\n\n## Lots\n"
            "LOT: A | dev-multi | moteur | .agents/bin/tasks_x.py, src/a.py\n"
            "LOT: B | dev-mono | doc | docs/b.md, docs/c.md\nINTÉGRATION: CHANGELOG.md\n")


def charger_pc(source: Path, nom: str):
    spec = importlib.util.spec_from_file_location(nom, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


class Racine:
    """Une racine jetable : plan, trace `plan approuvé` du parent, marqueur au choix."""

    def __init__(self, case: unittest.TestCase, armee: bool = True, annote: bool = True):
        self.d = Path(tempfile.mkdtemp(prefix="cible-fournee-"))
        case.addCleanup(shutil.rmtree, self.d, True)
        for sous in ("board", "gates", "local/plan", "specs"):
            (self.d / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        (self.d / "docs" / "tasks").mkdir(parents=True)
        (self.d / "docs" / "spec.md").write_text(SPEC, encoding="utf-8")
        if armee:
            (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
                "spec=docs/spec.md\nchantier=*\n", encoding="utf-8")
        self.entrees: list[dict] = []
        self.ecrire_plan(PARENT, annote)

    def ecrire_plan(self, parent: str, annote: bool = True) -> None:
        (self.d / PLAN).write_text(plan_texte(parent, annote), encoding="utf-8")
        self.sha = hashlib.sha256((self.d / PLAN).read_bytes()).hexdigest()

    def approuver(self, tid: str) -> None:
        self.entrees.append({"id": f"S-{len(self.entrees) + 1:08d}", "task": tid, "kind": "decision",
                             "title": "plan approuvé", "text": f"plan={PLAN} sha256={self.sha}",
                             "files": [], "date": "2026-10-13"})
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"entries": self.entrees}), encoding="utf-8")

    def data(self, lien: dict | None, etat_parent: str = "pending") -> dict:
        lot = {"id": LOT, "state": "pending", "task": "lot", "owner": "", "stage": "", "updated": "2026-10-13"}
        if lien is not None:
            lot["fournee"] = lien
        return {"tasks": [{"id": PARENT, "state": etat_parent, "task": "parent", "owner": "", "stage": "",
                           "updated": "2026-10-13"}, lot]}

    def lien(self, **surcharge) -> dict:
        lien = {"parent": PARENT, "lot": "A", "plan": PLAN, "sha256": self.sha, "trace": "S-00000001"}
        lien.update(surcharge)
        return lien


class Temoins:
    """Les témoins, chacun paramétré par le `plan_cible` qu'il éprouve."""

    def w_resout(self, pc) -> None:
        r = Racine(self)
        r.approuver(PARENT)
        note = f"[cible relevée sur {PARENT} — lot A]"
        for etat in ("pending", "running"):
            data = r.data(r.lien(), etat_parent=etat)
            res = pc._resoudre(str(r.d), LOT, data, slot=False)
            self.assertIsNotNone(res, f"au start, parent {etat} : le lien ne résout pas")
            self.assertEqual((res[0].name, res[1], res[2]), ("plan.md", note, PARENT))
            self.assertIsNone(pc.refus_au_start(str(r.d), LOT, data))
            self.assertEqual(pc.evaluer_done(str(r.d), LOT, data), (None, note), f"au done, parent {etat}")

    def w_controle(self, pc) -> None:
        """Le plan résolu par le lien est CONTRÔLÉ, au start comme au done."""
        r = Racine(self, annote=False)
        r.approuver(PARENT)
        data = r.data(r.lien())
        refus = pc.refus_au_start(str(r.d), LOT, data)
        self.assertIsNotNone(refus, "au start, le plan du lien n'est pas contrôlé")
        self.assertIn("plan.md", refus)
        self.assertIn(f"[cible relevée sur {PARENT} — lot A]", refus)
        self.assertIsNotNone(pc.evaluer_done(str(r.d), LOT, data)[0])

    def w_sha(self, pc) -> None:
        r = Racine(self)
        r.approuver(PARENT)
        data = r.data(r.lien(sha256="0" * 64))
        self.assertIsNone(pc._resoudre(str(r.d), LOT, data, slot=True), "un lien d'empreinte périmée résout")
        refus, note = pc.evaluer_done(str(r.d), LOT, data)
        self.assertIsNotNone(refus, "un lien d'empreinte périmée a passé le done")
        self.assertIn("aucun plan approuvé", refus)
        self.assertIn("le plan a changé depuis la découpe", refus)
        self.assertEqual(note, "")

    def w_cle(self, pc) -> None:
        r = Racine(self)
        r.approuver(PARENT)
        refus, _note = pc.evaluer_done(str(r.d), LOT, r.data(r.lien(lot="Z")))
        self.assertIsNotNone(refus, "un lot absent du plan a passé le done")
        self.assertIn("ne porte plus `LOT: Z`", refus)

    def w_sans_lien(self, pc) -> None:
        r = Racine(self)
        r.approuver(PARENT)
        refus, _note = pc.evaluer_done(str(r.d), LOT, r.data(None))
        self.assertIsNotNone(refus, "sans lien, le plan du parent a été emprunté")
        self.assertIn("aucune trace d'approbation", refus)
        incomplet = r.lien()
        incomplet.pop("sha256")
        self.assertIsNotNone(pc.evaluer_done(str(r.d), LOT, r.data(incomplet))[0], "un lien sans sha256 résout")

    def w_desarme(self, pc) -> None:
        r = Racine(self, armee=False)
        r.approuver(PARENT)
        data = r.data(r.lien())
        self.assertIsNone(pc.refus_au_start(str(r.d), LOT, data))
        self.assertEqual(pc.evaluer_done(str(r.d), LOT, data), (None, ""), "désarmé, la jambe a parlé")
        self.assertIsNotNone(pc._resoudre(str(r.d), LOT, data, slot=False), "le résolveur dépend du marqueur")


_PC = BIN / "plan_cible.py"
MUTANTS = {
    "lien sans sha": ([('    if hashlib.sha256(chemin.read_bytes()).hexdigest() != lien["sha256"].lower():\n'
                        "        return None\n", "")], "w_sha"),
    "lien sans clé de lot": ([('    if lien["lot"] not in cles_de_lots(chemin.read_text(encoding="utf-8")):\n'
                               "        return None\n", "")], "w_cle"),
    "lien au done seulement": ([("    lien = _lien_de_lot(root, tid, data, index)\n",
                                 "    lien = _lien_de_lot(root, tid, data, index) if slot else None\n")], "w_resout"),
}


class LienDeLotTests(Temoins, unittest.TestCase):
    """Les témoins sur le VRAI `plan_cible.py`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pc = charger_pc(_PC, "plan_cible_fournee_banc")


for _nom in [n for n in dir(Temoins) if n.startswith("w_")]:
    setattr(LienDeLotTests, "test_" + _nom[2:], (lambda nom: lambda self: getattr(self, nom)(self.pc))(_nom))


class LienDeLotMutantsTests(Temoins, unittest.TestCase):
    """Chaque mutant ROUGIT son témoin, par une assertion."""


def _test_mutant(nom: str, paires: list[tuple[str, str]], temoin: str):
    def test(self: LienDeLotMutantsTests) -> None:
        texte = _PC.read_text(encoding="utf-8")
        for ancre, remplacement in paires:
            self.assertEqual(texte.count(ancre), 1, f"ancre ambiguë ou absente : {ancre!r}")
            texte = texte.replace(ancre, remplacement)
        base = Path(tempfile.mkdtemp(prefix="cible-fournee-mut-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "plan_cible.py").write_text(texte, encoding="utf-8")
        pc = charger_pc(base / "plan_cible.py", f"plan_cible_fournee_mutant_{abs(hash(nom))}")
        with self.assertRaises(AssertionError, msg=f"le mutant « {nom} » SURVIT à {temoin}"):
            getattr(self, temoin)(pc)
    return test


for _i, (_nom, (_paires, _temoin)) in enumerate(MUTANTS.items()):
    setattr(LienDeLotMutantsTests, f"test_mutant_{_i}_{_temoin[2:]}", _test_mutant(_nom, _paires, _temoin))


class BoutEnBoutTests(unittest.TestCase):
    """CLI réelle, cible ARMÉE : `fournee` démarre les lots par le lien, et le `done`
    d'un lot planifié pose la note de lot au board."""

    def test_le_done_d_un_lot_planifie_pose_la_note(self) -> None:
        r = Racine(self)
        etat, maison = (Path(tempfile.mkdtemp(prefix="cible-fournee-etat-")) for _ in range(2))
        for d in (etat, maison):
            self.addCleanup(shutil.rmtree, d, True)
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@exemple.invalid\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        env.update(HOME=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"), CADRE_STATE_DIR=str(etat),
                   AGENTS_EVENTS_DIR=str(etat / "events"))

        def t(*args: str) -> subprocess.CompletedProcess:
            res = subprocess.run([sys.executable, str(BIN / "tasks.py"), "--root", str(r.d), *args],
                                 capture_output=True, text=True, timeout=180, env=env)
            self.assertEqual(res.returncode, 0, f"{args} : {res.stdout}{res.stderr}")
            return res
        parent = re.search(r"TASKS: (\S+) →", t("new", "parent").stdout).group(1)
        r.ecrire_plan(parent)
        r.approuver(parent)
        t("fournee", parent)
        lots = {x["fournee"]["lot"]: x for x in json.loads(t("list", "--json").stdout)
                if (x.get("fournee") or {}).get("parent") == parent}
        self.assertEqual({x["state"] for x in lots.values()}, {"running"})
        t("done", lots["A"]["id"], "--raison", "fin du lot")
        stage = json.loads(t("list", "--task", lots["A"]["id"], "--json").stdout)[0]["stage"]
        self.assertIn(f"[cible relevée sur {parent} — lot A]", stage)


if __name__ == "__main__":
    unittest.main()
