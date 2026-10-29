#!/usr/bin/env python3
"""LE PLAFOND DE LIGNES D'UN PLAN — `plan_lots.py check` (T-01M52XW8XNSN865QTNS0Z0KK7P,
décision pilote S-01M52Y43BA).

Mesuré sur 38 tâches (S-01M52XZTXS) : plans de 80 lignes en médiane, alors que la déf du
planner plafonne à 45 lignes sans que rien le fasse respecter. Depuis cette tâche, `check`
REFUSE un plan de plus de `PLAFOND_LIGNES_PLAN` lignes NON VIDES et dit où déporter le
reste : `docs/tasks/<T>-annexe.md`, lue à la demande, jamais par `check`.

TÉMOINS CAPABLES DE ROUGIR : 46 lignes -> rc 1 ; 45 lignes -> rc 0 (contrôle négatif) ;
le plafond abaissé d'une unité rend le contrôle négatif rouge (le témoin mord sur le seuil,
pas sur un hasard de fixture) ; `lire()` ne juge PAS la longueur (borne : `tasks.py fournee`
et `plan_plafond.py`, qui lisent par `lire`, ne refusent jamais un plan approuvé long).

LE MAÎTRE CONSOLIDÉ (T-01M54GE4K9EZRRQFD9TAVNWYKM, lot L) : `PLAN-LOT: <clé> | <chemin> | sha256=<hex>`,
lue par `rapport_check` SEUL. Témoins : maître consolidé juste -> rc 0 (contrôle négatif) ; formes
proches `PLAN-LOT :`, `- PLAN-LOT:`, `**PLAN-LOT:**` -> rc 1 ; clé hors `LOT:`, clé doublée, chemin
absent, empreinte autre, plan de lot qui n'enrôle pas le parent, sans `LOTS: aucun | lot <clé>`,
brouillon `STATUS : IN_PROGRESS` / `**STATUS:** CRITIC_REJECTED`, lot non couvert -> rc 1 chacun ;
`lire()` ne voit AUCUNE ligne `PLAN-LOT` (fournée et plafond inchangés).
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BIN = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("plan_lots", BIN / "plan_lots.py")
assert _spec is not None and _spec.loader is not None
plan_lots = importlib.util.module_from_spec(_spec)
sys.modules["plan_lots"] = plan_lots
_spec.loader.exec_module(plan_lots)

#: Une façade `tasks` SYNTHÉTIQUE : les quatre prédicats que `rapport_check` lit, et rien d'autre.
FACADE = SimpleNamespace(
    writeset_paths_overlap=lambda gauche, droite: None,
    writeset_path_refusal=lambda chemin: None,
    est_chemin_de_garde=lambda chemin: False,
    MAX_FICHIERS_DIRECT=5,
)


def plan(lignes_non_vides: int, vides_inserees: int = 0) -> str:
    """Un plan sans lot, de `lignes_non_vides` lignes de contenu, plus `vides_inserees`
    lignes blanches réparties entre elles (elles ne comptent pas)."""
    assert lignes_non_vides >= 3
    corps = ["# PLAN — T-00000001", "## Steps", "1. faire — angle mort: banc ?"]
    corps += [f"- note {i}" for i in range(lignes_non_vides - 3)]
    if vides_inserees:
        avec_vides: list[str] = []
        for i, ligne in enumerate(corps):
            avec_vides.append(ligne)
            if i < vides_inserees:
                avec_vides.append("")
        corps = avec_vides
    return "\n".join(corps) + "\n"


def compter(texte: str) -> int:
    return sum(1 for l in texte.splitlines() if l.strip())


class PlafondLignesTests(unittest.TestCase):
    def test_le_plafond_est_quarante_cinq(self) -> None:
        self.assertEqual(plan_lots.PLAFOND_LIGNES_PLAN, 45)

    def test_quarante_cinq_lignes_passent(self) -> None:
        texte = plan(45)
        self.assertEqual(compter(texte), 45, "fixture : 45 lignes non vides attendues")
        rc, sortie = plan_lots.rapport_check(texte, None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("LIGNES: 45/45", sortie)
        self.assertNotIn("annexe", sortie)

    def test_quarante_six_lignes_rouges_et_le_message_nomme_l_annexe(self) -> None:
        texte = plan(46)
        self.assertEqual(compter(texte), 46)
        rc, sortie = plan_lots.rapport_check(texte, None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("LIGNES: 46/45", sortie)
        self.assertIn("REFUS: plan de 46 lignes non vides, plafond 45", sortie)
        self.assertIn("docs/tasks/<T>-annexe.md", sortie)
        self.assertIn("CHECK: refus", sortie)

    def test_les_lignes_vides_ne_comptent_pas(self) -> None:
        texte = plan(45, vides_inserees=20)
        self.assertEqual(compter(texte), 45)
        self.assertGreater(len(texte.splitlines()), 45, "fixture : des lignes vides doivent exister")
        rc, sortie = plan_lots.rapport_check(texte, None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 0, sortie)

    def test_mutant_plafond_abaisse_rougit_le_controle_negatif(self) -> None:
        """Le témoin mord sur le SEUIL : à 44, le plan de 45 lignes est refusé."""
        with mock.patch.object(plan_lots, "PLAFOND_LIGNES_PLAN", 44):
            rc, sortie = plan_lots.rapport_check(plan(45), None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("REFUS: plan de 45 lignes non vides, plafond 44", sortie)

    def test_la_longueur_s_ajoute_aux_autres_refus_sans_les_masquer(self) -> None:
        texte = plan(46) + "LOT: A | dev-mono | seul | docs/a.md\nINTÉGRATION: aucune\n"
        rc, sortie = plan_lots.rapport_check(texte, "T-00000002", BIN.parent.parent, FACADE)
        self.assertEqual(rc, 1)
        self.assertIn("un seul lot (A)", sortie)
        self.assertIn("n'ENRÔLE pas T-00000002", sortie)
        self.assertIn("plafond 45", sortie)

    def test_lire_ne_juge_pas_la_longueur(self) -> None:
        """BORNE : `lire()` (fournée, plafond) ne porte aucun refus de longueur."""
        d = plan_lots.lire(plan(200), racine=BIN.parent.parent, chevauche=FACADE.writeset_paths_overlap,
                           admis=FACADE.writeset_path_refusal)
        self.assertEqual(d.refus, [])

    def test_compter_lignes_est_celui_du_module(self) -> None:
        self.assertEqual(plan_lots.compter_lignes("a\n\n  \nb\n"), 2)
        self.assertEqual(plan_lots.compter_lignes(""), 0)
        self.assertEqual(plan_lots.compter_lignes("x\r\n\r\ny"), 2)


PARENT = "T-00000009"


def plan_de_lot(cle: str, *, entete: str = f"# PLAN de lot — {PARENT}", statut: str = "",
                lots: str | None = None) -> str:
    """Un plan de lot FINI : enrôle le parent en ligne 1, porte `LOTS: aucun | lot <clé>`."""
    lignes = [entete, f"Tâches : {PARENT}"]
    if statut:
        lignes.append(statut)
    lignes += ["1. faire — angle mort: banc ?", f"LOTS: aucun | lot {cle}" if lots is None else lots]
    return "\n".join(lignes) + "\n"


class PlanLotTests(unittest.TestCase):
    """`PLAN-LOT:` — la consolidation du plan par lot, jugée par `check` seul."""

    CLES = ("A", "B")

    def setUp(self) -> None:
        self.racine = Path(tempfile.mkdtemp(prefix="plan-lot-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.racine, True))

    def ecrire_lot(self, cle: str, texte: str | None = None) -> tuple[str, str]:
        """Écrit le plan de lot sous la racine ; rend (chemin relatif, sha256)."""
        rel = f"docs/tasks/{PARENT}-lot-{cle}-plan.md"
        cible = self.racine / rel
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes((plan_de_lot(cle) if texte is None else texte).encode("utf-8"))
        return rel, plan_lots.empreinte(cible.read_bytes())

    def maitre(self, lignes_plan_lot: list[str]) -> str:
        corps = [f"# PLAN — {PARENT}", f"Tâches : {PARENT}", "STATUS: IN_PROGRESS",
                 "1. faire — angle mort: banc ?"]
        corps += [f"LOT: {c} | dev-mono | lot {c} | src/{c.lower()}.py" for c in self.CLES]
        corps.append("INTÉGRATION: aucune")
        return "\n".join(corps + lignes_plan_lot) + "\n"

    def ligne(self, cle: str, texte: str | None = None) -> str:
        """Écrit le plan de lot de `cle` et rend SA ligne `PLAN-LOT:` stricte."""
        rel, sha = self.ecrire_lot(cle, texte)
        return f"PLAN-LOT: {cle} | {rel} | sha256={sha}"

    def consolide(self) -> list[str]:
        return [self.ligne(c) for c in self.CLES]

    def check(self, texte: str, parent: str | None = PARENT) -> tuple[int, str]:
        return plan_lots.rapport_check(texte, parent, self.racine, FACADE)

    def refuse(self, texte: str, attendu: str, parent: str | None = PARENT) -> str:
        rc, sortie = self.check(texte, parent)
        self.assertEqual(rc, 1, sortie)
        self.assertIn(attendu, sortie)
        self.assertIn("CHECK: refus", sortie)
        return sortie

    # -- contrôles négatifs ------------------------------------------------
    def test_maitre_consolide_juste_passe(self) -> None:
        rc, sortie = self.check(self.maitre(self.consolide()))
        self.assertEqual(rc, 0, sortie)
        for c in self.CLES:
            self.assertIn(f"PLAN-LOT {c} — docs/tasks/{PARENT}-lot-{c}-plan.md — présent, empreinte égale", sortie)
        self.assertIn("CHECK: ok", sortie)

    def test_maitre_non_consolide_passe_et_le_dit(self) -> None:
        rc, sortie = self.check(self.maitre([]))
        self.assertEqual(rc, 0, sortie)
        self.assertIn("PLAN-LOT: aucune ligne — maître non consolidé", sortie)

    def test_statut_fini_passe(self) -> None:
        lignes = [self.ligne("A", plan_de_lot("A", statut="STATUS: GO_AVEC_RESERVES")), self.ligne("B")]
        rc, sortie = self.check(self.maitre(lignes))
        self.assertEqual(rc, 0, sortie)

    def test_ligne_dans_un_bloc_de_code_n_est_pas_lue(self) -> None:
        texte = self.maitre(["```", "- PLAN-LOT: A | x | sha256=0", "PLAN-LOT: Z | y | sha256=1", "```"])
        rc, sortie = self.check(texte)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("maître non consolidé", sortie)

    def test_lire_ne_voit_aucune_ligne_plan_lot(self) -> None:
        """BORNE : la fournée et le plafond lisent par `lire()` — ni la forme stricte ni la proche."""
        texte = self.maitre(["PLAN-LOT: A | absent.md | sha256=" + "0" * 64, "- PLAN-LOT: B | x.md | y",
                             "**PLAN-LOT:** C", "PLAN-LOT : D"])
        d = plan_lots.lire(texte, racine=self.racine, chevauche=FACADE.writeset_paths_overlap,
                           admis=FACADE.writeset_path_refusal)
        self.assertEqual(d.refus, [])
        self.assertEqual([lot.cle for lot in d.lots], list(self.CLES))

    # -- la forme stricte --------------------------------------------------
    def test_formes_proches_refusees(self) -> None:
        stricte = self.consolide()
        for proche in (stricte[0].replace("PLAN-LOT:", "PLAN-LOT :"), "- " + stricte[0],
                       stricte[0].replace("PLAN-LOT:", "**PLAN-LOT:**"), "  " + stricte[0]):
            with self.subTest(proche=proche):
                self.refuse(self.maitre([proche, stricte[1]]), "ligne proche de `PLAN-LOT:`")

    def test_ligne_malformee_refusee(self) -> None:
        rel, sha = self.ecrire_lot("A")
        for ligne in (f"PLAN-LOT: A | {rel}", f"PLAN-LOT: A | {rel} | {sha}",
                      f"PLAN-LOT: A | {rel} | sha256={sha.upper()}", f"PLAN-LOT: a | {rel} | sha256={sha}",
                      f"PLAN-LOT: A | docs/tasks/*.md | sha256={sha}", f"PLAN-LOT: A | ../{rel} | sha256={sha}"):
            with self.subTest(ligne=ligne):
                self.refuse(self.maitre([ligne, self.ligne("B")]), "ligne malformée")

    # -- la clé ------------------------------------------------------------
    def test_cle_hors_lot_refusee(self) -> None:
        self.refuse(self.maitre(self.consolide() + [self.ligne("C")]), "PLAN-LOT C : aucun `LOT: C` au maître")

    def test_cle_doublee_refusee(self) -> None:
        lignes = self.consolide()
        self.refuse(self.maitre(lignes + [lignes[0]]), "PLAN-LOT A écrit deux fois")

    def test_lot_non_couvert_refuse(self) -> None:
        self.refuse(self.maitre(self.consolide()[:1]), "lot(s) B sans ligne `PLAN-LOT:` valide")

    # -- le plan de lot ----------------------------------------------------
    def test_chemin_absent_refuse(self) -> None:
        lignes = self.consolide()
        (self.racine / f"docs/tasks/{PARENT}-lot-A-plan.md").unlink()
        self.refuse(self.maitre(lignes), "absent sous la racine")

    def test_empreinte_autre_refusee(self) -> None:
        lignes = self.consolide()
        (self.racine / f"docs/tasks/{PARENT}-lot-A-plan.md").write_bytes(
            (plan_de_lot("A") + "2. un ajout après consolidation\n").encode("utf-8"))
        self.refuse(self.maitre(lignes), "le plan de lot a changé depuis la consolidation")

    def test_plan_de_lot_qui_n_enrole_pas_le_parent_refuse(self) -> None:
        autre = plan_de_lot("A", entete="# PLAN de lot A — T-00000008").replace(
            f"Tâches : {PARENT}", "Tâches : T-00000008")
        self.refuse(self.maitre([self.ligne("A", autre), self.ligne("B")]), f"n'ENRÔLE pas {PARENT}")

    def test_sans_parent_l_enrolement_n_est_pas_juge_et_le_dit(self) -> None:
        rc, sortie = self.check(self.maitre(self.consolide()), parent=None)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("enrôlement des plans de lot NON JUGÉ", sortie)

    def test_plan_de_lot_sans_lots_aucun_lot_k_refuse(self) -> None:
        for lots in ("LOTS: aucun | lot B", "LOTS: aucun", "", "LOTS: aucun | lot"):
            with self.subTest(lots=lots):
                self.refuse(self.maitre([self.ligne("A", plan_de_lot("A", lots=lots)), self.ligne("B")]),
                            "ne porte pas `LOTS: aucun | lot A`")

    def test_plan_de_lot_brouillon_refuse_lecture_tolerante(self) -> None:
        for statut, marque in (("STATUS : IN_PROGRESS", "IN_PROGRESS"),
                               ("**STATUS:** CRITIC_REJECTED", "CRITIC_REJECTED"),
                               ("STATUS: in_progress (rév. 2)", "IN_PROGRESS")):
            with self.subTest(statut=statut):
                self.refuse(self.maitre([self.ligne("A", plan_de_lot("A", statut=statut)), self.ligne("B")]),
                            f"est encore un brouillon (`STATUS: {marque}`)")

    def test_marqueur_brouillon_est_la_copie_de_draft_marker(self) -> None:
        """La COPIE de `plan_pool.draft_marker` (SYM-07718) rend la même chose sur les témoins."""
        racine = BIN.parent.parent
        spec = importlib.util.spec_from_file_location("plan_pool_copie", racine / "core-scripts" / "plan_pool.py")
        if spec is None or spec.loader is None or not (racine / "core-scripts" / "plan_pool.py").is_file():
            self.skipTest("core-scripts/plan_pool.py absent de cet arbre")
        plan_pool = importlib.util.module_from_spec(spec)
        sys.modules["plan_pool_copie"] = plan_pool
        spec.loader.exec_module(plan_pool)
        for texte in ("STATUS : IN_PROGRESS", "**STATUS:** CRITIC_REJECTED", "  - status: in_progress",
                      "STATUS: READY", "STATUS:", "rien", "STATUS: GO\nSTATUS : CRITIC_REJECTED"):
            with self.subTest(texte=texte):
                self.assertEqual(plan_lots.marqueur_brouillon(texte), plan_pool.draft_marker(texte))


class RenvoiPlanningTests(unittest.TestCase):
    """`/planning` RENVOIE au planning SKILL § « Plan par lot (T-01M54GE4K9) » et nomme `PLAN-LOT:` et
    `plan_lots.py check` (lot L). Le titre de la section naît au lot D : sa présence se juge au banc de D."""

    COMMANDE = BIN.parent.parent / ".claude" / "commands" / "planning.md"

    def test_planning_renvoie_au_plan_par_lot(self) -> None:
        if not self.COMMANDE.is_file():
            self.skipTest(".claude/commands/planning.md absent de cet arbre (adoptant sans la commande)")
        texte = " ".join(self.COMMANDE.read_text(encoding="utf-8").split())
        for jeton in ("planning SKILL § « Plan par lot (T-01M54GE4K9) »",
                      "`PLAN-LOT: <K> | docs/tasks/T-NNNNNNNN-lot-<K>-plan.md | sha256=<hex>`",
                      "`python .agents/bin/plan_lots.py check --plan <maître> --parent T-NNNNNNNN`",
                      "`lot <K> : plan-critic <VERDICT> (iteration <n>/<N>)`"):
            with self.subTest(jeton=jeton):
                self.assertIn(jeton, texte)


def plan_a_lots_iac(dev: str) -> str:
    """Un plan de deux lots dont le premier est confié à `dev` (aucun chemin de garde,
    aucune déf d'hôte : seule la colonne du dev peut faire refuser). Renommé (CORR-5a,
    2026-10-19) : le `plan_a_lots(dev_b, chemins_b)` de develop, défini plus bas, le masquait."""
    return ("# PLAN — T-00000003\n## Steps\n1. faire — angle mort: banc ?\n"
            f"LOT: A | {dev} | IaC du projet | infra/main.tf, infra/variables.tf\n"
            "LOT: B | dev-mono | documentation | docs/a.md\n"
            "INTÉGRATION: aucune\n")


class DevsDesLotsTests(unittest.TestCase):
    """T-01M52X1W3WPKCWX1DC36NMKJB6 (lot F2, décision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG) :
    `terraform-deployer` est le slot dev d'une tâche IaC, donc un dev admis par la grammaire
    `LOT:` ; la liste reste FERMÉE — un dev inconnu est toujours refusé."""

    def temoin_terraform_deployer_admis(self) -> None:
        rc, sortie = plan_lots.rapport_check(plan_a_lots_iac("terraform-deployer"), None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("LOT A — terraform-deployer — 2 fichier(s)", sortie)
        self.assertIn("CHECK: ok", sortie)
        d = plan_lots.lire(plan_a_lots_iac("terraform-deployer"), racine=BIN.parent.parent,
                           chevauche=FACADE.writeset_paths_overlap, admis=FACADE.writeset_path_refusal)
        self.assertEqual(d.refus, [])
        self.assertEqual([(lot.cle, lot.dev) for lot in d.lots], [("A", "terraform-deployer"), ("B", "dev-mono")])

    def test_terraform_deployer_est_un_dev_admis(self) -> None:
        self.temoin_terraform_deployer_admis()

    def test_un_dev_inconnu_reste_refuse(self) -> None:
        rc, sortie = plan_lots.rapport_check(plan_a_lots_iac("terraform-inconnu"), None, BIN.parent.parent, FACADE)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("dev 'terraform-inconnu' hors de dev-mono, dev-multi, frontend-fidelity, terraform-deployer",
                      sortie)
        self.assertIn("CHECK: refus", sortie)

    def test_mutant_sans_terraform_deployer_rougit_le_temoin(self) -> None:
        """MUTATION : retirer `terraform-deployer` de `DEVS` rend le témoin rouge."""
        sans = tuple(d for d in plan_lots.DEVS if d != "terraform-deployer")
        self.assertEqual(len(sans), len(plan_lots.DEVS) - 1, "fixture : terraform-deployer absent de DEVS")
        with mock.patch.object(plan_lots, "DEVS", sans):
            with self.assertRaises(AssertionError, msg="mutant SURVIVANT : DEVS sans terraform-deployer"):
                self.temoin_terraform_deployer_admis()


class CliTests(unittest.TestCase):
    """Le témoin de bout en bout demandé par le pilote : un plan de 46 lignes -> `check` rouge."""

    def _check(self, texte: str, *extra: str, d: Path | None = None) -> subprocess.CompletedProcess:
        if d is None:
            d = Path(tempfile.mkdtemp(prefix="plan-lots-"))
            self.addCleanup(lambda: __import__("shutil").rmtree(d, True))
        chemin = d / "plan.md"
        chemin.write_text(texte, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR" and not k.startswith("GIT_")}
        env.update(HOME=str(d), CADRE_STATE_DIR=str(d / "etat"), AGENTS_EVENTS_DIR=str(d / "etat" / "events"))
        return subprocess.run([sys.executable, str(BIN / "plan_lots.py"), "check", "--plan", str(chemin),
                               "--root", str(d), *extra], capture_output=True, text=True, timeout=120, env=env)

    def test_maitre_consolide_check_de_bout_en_bout(self) -> None:
        """`PLAN-LOT:` par la commande, avec la VRAIE façade `tasks` : juste -> 0, un lot retouché -> 1."""
        d = Path(tempfile.mkdtemp(prefix="plan-lots-pl-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(d, True))
        lignes = [f"# PLAN — {PARENT}", "LOT: A | dev-mono | a | src/a.py", "LOT: B | dev-mono | b | src/b.py",
                  "INTÉGRATION: aucune"]
        for c in ("A", "B"):
            rel = f"docs/tasks/{PARENT}-lot-{c}-plan.md"
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_bytes(plan_de_lot(c).encode("utf-8"))
            lignes.append(f"PLAN-LOT: {c} | {rel} | sha256={plan_lots.empreinte((d / rel).read_bytes())}")
        texte = "\n".join(lignes) + "\n"
        r = self._check(texte, "--parent", PARENT, d=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PLAN-LOT B — ", r.stdout)
        (d / f"docs/tasks/{PARENT}-lot-B-plan.md").write_bytes(plan_de_lot("B", statut="STATUS: IN_PROGRESS")
                                                               .encode("utf-8"))
        r = self._check(texte, "--parent", PARENT, d=d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUS: PLAN-LOT B : `docs/tasks/", r.stdout)
        self.assertIn("le plan de lot a changé depuis la consolidation", r.stdout)

    def test_quarante_six_lignes_check_rouge(self) -> None:
        r = self._check(plan(46))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUS: plan de 46 lignes non vides, plafond 45", r.stdout)
        self.assertIn("-annexe.md", r.stdout)

    def test_quarante_cinq_lignes_check_vert(self) -> None:
        r = self._check(plan(45))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CHECK: ok", r.stdout)


def plan_a_lots(dev_b: str, chemins_b: list[str]) -> str:
    """Un plan court à deux lots : A `dev-multi` d'un chemin, B `<dev_b>` sur `chemins_b`."""
    return "\n".join([
        "# PLAN — T-00000001", "## Steps", "1. faire — angle mort: banc ?", "## Lots",
        "LOT: A | dev-multi | moteur | src/a.py",
        f"LOT: B | {dev_b} | doc | {', '.join(chemins_b)}",
        "INTÉGRATION: aucune",
    ]) + "\n"


class DevMonoTests(unittest.TestCase):
    """UN LOT `dev-mono` = UN CHEMIN, son test colocalisé en plus (T-01M54WMA3WGQ2CSFG218SHAC7M,
    décision pilote S-01M54WQE1K4VQKJ9STTJ7A1DQ2) : `check` SEUL le refuse, `lire()` jamais.

    TÉMOINS CAPABLES DE ROUGIR : deux chemins non colocalisés -> rc 1 ; les cinq formes admises
    -> rc 0 (contrôle négatif) ; test dans un AUTRE dossier, source + test + tiers, `FooTest.java`
    (borne) -> rc 1 ; le mutant « `est_test_colocalise` forcé à True » rend le témoin « autre
    dossier » vert à tort (il mord sur le prédicat, pas sur le compte de chemins)."""

    def _rapport(self, dev_b: str, chemins_b: list[str]) -> tuple[int, str]:
        return plan_lots.rapport_check(plan_a_lots(dev_b, chemins_b), None, BIN.parent.parent, FACADE)

    def test_deux_chemins_non_colocalises_refuses(self) -> None:
        rc, sortie = self._rapport("dev-mono", ["docs/b.md", "docs/c.md"])
        self.assertEqual(rc, 1, sortie)
        self.assertIn("REFUS: lot B : dev-mono déclare 2 chemins — route-le vers dev-multi "
                      "(S-01M54WQE1K4VQKJ9STTJ7A1DQ2)", sortie)
        self.assertIn("CHECK: refus", sortie)

    def test_source_et_son_test_colocalise_admis(self) -> None:
        for source, test in (("x.py", "test_x.py"), ("web/a.ts", "web/a.test.ts"),
                             ("core-scripts/s.sh", "core-scripts/s.test.sh"), ("cmd/g.go", "cmd/g_test.go"),
                             ("lib/c.js", "lib/c.spec.js")):
            for chemins in ([source, test], [test, source]):
                with self.subTest(chemins=chemins):
                    rc, sortie = self._rapport("dev-mono", chemins)
                    self.assertEqual(rc, 0, sortie)
                    self.assertNotIn("dev-mono déclare", sortie)

    def test_test_dans_un_autre_dossier_refuse(self) -> None:
        rc, sortie = self._rapport("dev-mono", [".agents/bin/x.py", ".agents/evals/test_x.py"])
        self.assertEqual(rc, 1, sortie)
        self.assertIn("lot B : dev-mono déclare 2 chemins", sortie)

    def test_source_test_et_tiers_refuses(self) -> None:
        rc, sortie = self._rapport("dev-mono", ["src/x.py", "src/test_x.py", "docs/x.md"])
        self.assertEqual(rc, 1, sortie)
        self.assertIn("lot B : dev-mono déclare 3 chemins", sortie)

    def test_borne_java_footest_refuse(self) -> None:
        """BORNE : une convention hors liste (Java, même dossier ou `src/test/java`) va à dev-multi."""
        for chemins in (["src/Foo.java", "src/FooTest.java"],
                        ["src/main/java/a/Foo.java", "src/test/java/a/FooTest.java"]):
            with self.subTest(chemins=chemins):
                rc, sortie = self._rapport("dev-mono", chemins)
                self.assertEqual(rc, 1, sortie)
                self.assertIn("dev-mono déclare 2 chemins", sortie)

    def test_meme_lot_sous_un_autre_dev_admis(self) -> None:
        for dev in ("dev-multi", "frontend-fidelity"):
            with self.subTest(dev=dev):
                rc, sortie = self._rapport(dev, ["docs/b.md", "docs/c.md", "src/d.py"])
                self.assertEqual(rc, 0, sortie)

    def test_lire_ne_juge_pas_le_routage(self) -> None:
        """BORNE (jumeau de `test_lire_ne_juge_pas_la_longueur`) : la fournée et le plafond du
        critique lisent par `lire()`, qui ne refuse jamais un lot dev-mono multi-chemins."""
        d = plan_lots.lire(plan_a_lots("dev-mono", ["docs/b.md", "docs/c.md"]), racine=BIN.parent.parent,
                           chevauche=FACADE.writeset_paths_overlap, admis=FACADE.writeset_path_refusal)
        self.assertEqual(d.refus, [])
        self.assertEqual([lot.dev for lot in d.lots], ["dev-multi", "dev-mono"])

    def test_est_test_colocalise_liste_fermee(self) -> None:
        self.assertTrue(plan_lots.est_test_colocalise("a\\b\\x.py", "a/b/test_x.py"))
        for source, test in (("x.ts", "test_x.ts"), ("X.py", "test_x.py"), ("Makefile", "test_Makefile.py"),
                             ("a/x.py", "b/test_x.py"), ("x.py", "x_tests.py"), ("x.py", "x.py")):
            with self.subTest(source=source, test=test):
                self.assertFalse(plan_lots.est_test_colocalise(source, test))

    def test_est_test_colocalise_nfd_egale_nfc(self) -> None:
        """Un nom accentué NFD (celui que rend macOS) contre sa forme NFC : même fichier.
        Mutant « NFC retiré » de `est_test_colocalise` -> rouge."""
        self.assertTrue(plan_lots.est_test_colocalise(unicodedata.normalize("NFD", "a/café.py"), "a/test_café.py"))

    def test_mutant_colocalise_force_a_vrai_rougit_le_temoin_autre_dossier(self) -> None:
        with mock.patch.object(plan_lots, "est_test_colocalise", lambda source, test: True):
            rc, sortie = self._rapport("dev-mono", [".agents/bin/x.py", ".agents/evals/test_x.py"])
        self.assertEqual(rc, 0, f"le mutant aurait dû rendre le témoin « autre dossier » vert à tort : {sortie}")

    def test_cli_dev_mono_de_deux_chemins_check_rouge(self) -> None:
        r = CliTests._check(self, plan_a_lots("dev-mono", ["docs/b.md", "docs/c.md"]))  # type: ignore[arg-type]
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("REFUS: lot B : dev-mono déclare 2 chemins", r.stdout)


#: Les six surfaces qui portent la règle dev-mono (cinq défs `planner` + la skill planning).
SURFACES_DEV_MONO = (
    ".claude/agents/planner.md",
    ".codex/agents/planner.toml",
    ".gemini/agents/planner.md",
    ".github/agents/planner.agent.md",
    ".kimi-code/agents/planner.md",
    ".agents/skills/planning/SKILL.md",
)

#: Ancre courte et stable : le début de la phrase, puis l'id de décision qui la ferme, sur la
#: même ligne — le milieu (la liste des formes) peut évoluer sans rougir le témoin.
#: La skill planning garde la phrase française ; les cinq défs `planner` la portent en anglais
#: (T-01M5S9338BJP1B5RM3TG14AMYT) — chaque surface est tenue par l'ancre de SA langue, jamais
#: par l'autre (témoin `test_mutant_forme_de_l_autre_langue_rougit`).
ANCRE_DEV_MONO_FR = re.compile(
    r"Un lot `dev-mono` ne déclare qu'UN chemin, son test colocalisé en plus"
    r"[^\n]*?\(décision pilote " + plan_lots.DECISION_DEV_MONO + r"\)\."
)
ANCRE_DEV_MONO_EN = re.compile(
    r"A `dev-mono` lot declares only ONE path, plus its colocated test"
    r"[^\n]*?\(pilot decision " + plan_lots.DECISION_DEV_MONO + r"\)\."
)
SURFACE_FRANCAISE_DEV_MONO = ".agents/skills/planning/SKILL.md"


def ancre_dev_mono(rel: str) -> re.Pattern[str]:
    return ANCRE_DEV_MONO_FR if rel == SURFACE_FRANCAISE_DEV_MONO else ANCRE_DEV_MONO_EN


def surfaces_sans_regle_dev_mono(racine: Path) -> list[str]:
    """Les surfaces où la phrase dev-mono n'apparaît pas EXACTEMENT une fois (absente,
    illisible ou doublée), avec le compte observé."""
    ecarts: list[str] = []
    for rel in SURFACES_DEV_MONO:
        try:
            texte = unicodedata.normalize("NFC", (racine / rel).read_text(encoding="utf-8"))
        except OSError as exc:
            ecarts.append(f"{rel}: illisible ({exc.__class__.__name__})")
            continue
        n = len(ancre_dev_mono(rel).findall(texte))
        if n != 1:
            ecarts.append(f"{rel}: {n} occurrence(s)")
    return ecarts


class PresenceRegleDevMonoTests(unittest.TestCase):
    """TÉMOIN DE PRÉSENCE (angle mort exec-critic, T-01M54WMA3WGQ2CSFG218SHAC7M) : la règle
    « un lot dev-mono = un chemin + son test colocalisé » que `check` fait respecter est DITE
    exactement une fois dans chacune des six surfaces du planner. Vérifié DANS LE KIT seul :
    chez l'adoptant ces défs sont réécrites par lui, le témoin s'y saute (motif dit).

    TÉMOINS CAPABLES DE ROUGIR : la phrase retirée d'UNE seule surface (copie jetable) -> cette
    surface, et elle seule, est nommée ; la phrase doublée -> `2 occurrence(s)`."""

    RACINE = BIN.parent.parent

    def setUp(self) -> None:
        if not (self.RACINE / ".agents" / "IS_THE_KIT").is_file():
            self.skipTest("hors du kit (pas de .agents/IS_THE_KIT) : les défs planner sont celles de l'adoptant")

    def test_phrase_presente_une_fois_par_surface(self) -> None:
        self.assertEqual(surfaces_sans_regle_dev_mono(self.RACINE), [])

    def _copie(self, dossier: Path) -> Path:
        for rel in SURFACES_DEV_MONO:
            cible = dossier / rel
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.RACINE / rel, cible)
        return dossier

    def test_mutant_phrase_retiree_d_une_seule_surface_rougit(self) -> None:
        for rel in SURFACES_DEV_MONO:
            with self.subTest(surface=rel), tempfile.TemporaryDirectory() as d:
                racine = self._copie(Path(d))
                cible = racine / rel
                texte = unicodedata.normalize("NFC", cible.read_text(encoding="utf-8"))
                cible.write_text(ancre_dev_mono(rel).sub("", texte), encoding="utf-8")
                self.assertEqual(surfaces_sans_regle_dev_mono(racine), [f"{rel}: 0 occurrence(s)"])

    def test_mutant_phrase_doublee_rougit(self) -> None:
        rel = SURFACES_DEV_MONO[-1]
        with tempfile.TemporaryDirectory() as d:
            racine = self._copie(Path(d))
            cible = racine / rel
            texte = cible.read_text(encoding="utf-8")
            phrase = ancre_dev_mono(rel).search(unicodedata.normalize("NFC", texte))
            assert phrase is not None
            cible.write_text(texte + "\n" + phrase.group(0) + "\n", encoding="utf-8")
            self.assertEqual(surfaces_sans_regle_dev_mono(racine), [f"{rel}: 2 occurrence(s)"])

    def test_mutant_forme_de_l_autre_langue_rougit(self) -> None:
        """La phrase de la skill (française) posée à la place de l'anglaise dans une déf, et
        l'anglaise à la place de la française dans la skill : chaque surface est nommée."""
        fr_skill = ANCRE_DEV_MONO_FR.search(unicodedata.normalize(
            "NFC", (self.RACINE / SURFACE_FRANCAISE_DEV_MONO).read_text(encoding="utf-8")))
        en_def = ANCRE_DEV_MONO_EN.search(unicodedata.normalize(
            "NFC", (self.RACINE / SURFACES_DEV_MONO[0]).read_text(encoding="utf-8")))
        assert fr_skill is not None and en_def is not None
        for rel in SURFACES_DEV_MONO:
            with self.subTest(surface=rel), tempfile.TemporaryDirectory() as d:
                racine = self._copie(Path(d))
                cible = racine / rel
                texte = unicodedata.normalize("NFC", cible.read_text(encoding="utf-8"))
                autre = en_def.group(0) if rel == SURFACE_FRANCAISE_DEV_MONO else fr_skill.group(0)
                cible.write_text(ancre_dev_mono(rel).sub(lambda _m: autre, texte), encoding="utf-8")
                self.assertEqual(surfaces_sans_regle_dev_mono(racine), [f"{rel}: 0 occurrence(s)"])


if __name__ == "__main__":
    unittest.main()
