#!/usr/bin/env python3
"""L'EPIC OPTIONNELLE AU BOARD — T-00001043 : registre racine `epics`, champ
`epic`, verbes `epic-new` / `epic` / `epic-list`, lecture `list --epic`, rendu
par `cell`, refus R10 au `retitle`, et garde de plan `EPIC:` au `done`.

ZÉRO APPEL LLM. `tasks.py`, `plan_cible.py`, `plan_depends.py` chargés par
chemin (`spec_from_file_location`, comme `test_plan_depends_guard.py`) ; board,
SPECS et marqueur posés sous une racine JETABLE. `replay_sync` est patché sur le
module (le pont V3 n'est pas l'objet de ce banc) et l'environnement V3
(`CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR`, `CADRE_PROJECT_ROOT`) pointe la racine
jetable. Fixtures SYNTHÉTIQUES, jamais les données du dépôt.

*** CHAQUE TÉMOIN NOMME SON MUTANT *** (joué sur une COPIE jetable, L-00000487).

LIMITE ÉCRITE : `SYNC_SNAPSHOT_FIELDS` est GELÉ (la validation de `load` compare
chaque snapshot de l'outbox à cet ensemble exact) ; l'intention de sync d'un
`epic` dit donc le GESTE, jamais la valeur, qui se lit sur la tâche — comme
`regroup`. Le témoin `test_epic_une_intention_de_sync_au_snapshot_gele` le fige.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks.py"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


pc = _charger("plan_cible", HERE / "plan_cible.py")
pd = _charger("plan_depends", HERE / "plan_depends.py")
tasks = _charger("tasks_epics_banc", TASKS)
# UN SEUL objet module par nom : le patch W8c posé sur `pc` atteint la garde.
tasks._PLAN_CIBLE_MOD = pc
tasks._PLAN_DEPENDS_MOD = pd

CHANTIER = "refonte"
PLAN = (
    "# Plan de banc\n"
    "Tâches : {roster}\n"
    "{epics}"
    "## Steps\n"
    "1. étape une\n"
    "   décision pilote: S-00001558\n"
)
LONG = "Une tâche au titre assez long pour dépasser quarante-quatre caractères. Référence : x."


class _Banc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.d = Path(self._tmp.name)
        for sub in ("board", "gates", "specs", "local/plan", "local/binome"):
            (self.d / ".agents" / "state" / sub).mkdir(parents=True, exist_ok=True)
        (self.d / "plans").mkdir()
        (self.d / "spec.md").write_text("**« un invariant »**\n", encoding="utf-8")
        self.root = str(self.d)
        for patcher in (
            mock.patch.dict(os.environ, {"CADRE_STATE_DIR": self.root, "AGENTS_EVENTS_DIR": self.root,
                                         "CADRE_PROJECT_ROOT": self.root}),
            mock.patch.object(tasks, "replay_sync", return_value=0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- outillage ------------------------------------------------------------
    @property
    def store_path(self) -> Path:
        return self.d / ".agents" / "state" / "board" / "TASKS.json"

    def store(self) -> dict:
        """TASKS.json BRUT, son `sync_outbox` lue par la VUE (T-00001058, O2 : un fichier par intent)."""
        return {**json.loads(self.store_path.read_text(encoding="utf-8")),
                "sync_outbox": tasks.load(str(self.d))["sync_outbox"]}

    def write_store(self, data: dict) -> None:
        self.store_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def task(self, tid: str) -> dict:
        return next(t for t in self.store()["tasks"] if t["id"] == tid)

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = tasks.main(["--root", self.root, *args])
            except SystemExit as exc:  # `ap.error` : usage, rc 2
                rc = exc.code
        return rc, out.getvalue(), err.getvalue()

    def new(self, title: str = "tache de banc", chantier: str = CHANTIER, epic: str | None = None) -> str:
        return tasks.new_task(self.root, title, "", chantier, epic=epic).split()[1]

    def epic_new(self, eid: str = "E-01", titre: str = "Durcir le board", **kw) -> str:
        return tasks.new_epic(self.root, eid, titre, **kw)

    def refus(self, fn, *args, **kw) -> str:
        with self.assertRaises(tasks.BoardError) as caught:
            fn(*args, **kw)
        return str(caught.exception)

    @staticmethod
    def legacy(tid: str = "T-00000001", title: str = "Legacy", **extra) -> dict:
        return {"id": tid, "state": "pending", "task": title, "owner": "", "stage": "",
                "updated": "2026-09-30", **extra}


# ===========================================================================
# Chargement — PRÉSENCE ET FORME SEULEMENT, référent non exigé, aucun setdefault.
# ===========================================================================
class ChargementTests(_Banc):
    def test_store_ancien_sans_epics_se_charge_et_ne_gagne_aucune_cle(self):
        """MUTANT : `data.setdefault("epics", [])` dans `load` ⇒ la clé apparaît, rouge."""
        self.write_store({"next_id": 2, "tasks": [self.legacy()]})
        self.assertNotIn("epics", tasks.load(self.root))
        self.new()
        self.assertNotIn("epics", self.store())

    def test_epic_hors_registre_se_charge(self):
        """MUTANT : `load` qui exige le référent au registre ⇒ refus, rouge."""
        self.write_store({"next_id": 2, "tasks": [self.legacy(epic="E-99")]})
        self.assertEqual(tasks.load(self.root)["tasks"][0]["epic"], "E-99")

    def test_epic_non_chaine_refusee(self):
        """MUTANT : `load` qui accepte `epic: 42` ⇒ chargé, rouge."""
        self.write_store({"next_id": 2, "tasks": [self.legacy(epic=42)]})
        self.assertIn("invalid epic", self.refus(tasks.load, self.root))

    def test_epic_vide_refusee(self):
        self.write_store({"next_id": 2, "tasks": [self.legacy(epic="")]})
        self.assertIn("invalid epic", self.refus(tasks.load, self.root))

    def test_registre_id_en_double_refuse(self):
        self.write_store({"next_id": 1, "tasks": [], "epics": [{"id": "E-01"}, {"id": "E-01"}]})
        self.assertIn("duplicate id E-01", self.refus(tasks.load, self.root))

    def test_registre_qui_n_est_pas_une_liste_refuse(self):
        self.write_store({"next_id": 1, "tasks": [], "epics": {"E-01": {}}})
        self.assertIn("epics must be a list", self.refus(tasks.load, self.root))

    def test_entree_sans_id_refusee(self):
        self.write_store({"next_id": 1, "tasks": [], "epics": [{"titre": "sans id"}]})
        self.assertIn("has no id", self.refus(tasks.load, self.root))

    def test_entree_a_titre_non_chaine_refusee(self):
        self.write_store({"next_id": 1, "tasks": [], "epics": [{"id": "E-01", "titre": 3}]})
        self.assertIn("non-string titre", self.refus(tasks.load, self.root))

    def test_entree_sans_titre_se_charge(self):
        self.write_store({"next_id": 1, "tasks": [], "epics": [{"id": "E-1"}]})
        self.assertEqual(tasks.load(self.root)["epics"], [{"id": "E-1"}])


# ===========================================================================
# Verbes — UNE règle pour le vide : `""` refusé partout en écriture.
# ===========================================================================
class EpicNewTests(_Banc):
    def test_titre_vide_refuse(self):
        rc, _, err = self.cli("epic-new", "E-01", "")
        self.assertNotEqual(rc, 0)
        self.assertIn("one non-empty line", err)
        self.assertFalse(self.store_path.exists() and "epics" in self.store())

    def test_sans_id_est_une_erreur_d_usage(self):
        self.assertEqual(self.cli("epic-new")[0], 2)

    def test_id_hors_forme_refuse(self):
        for eid in ("E-1", "X-01", "e-01"):
            with self.subTest(eid=eid):
                rc, _, err = self.cli("epic-new", eid, "titre")
                self.assertNotEqual(rc, 0)
                self.assertIn("is not an epic id", err)

    def test_doublon_refuse_et_maj_remplace(self):
        self.epic_new(vague=1)
        rc, _, err = self.cli("epic-new", "E-01", "autre titre")
        self.assertNotEqual(rc, 0)
        self.assertIn("--maj", err)
        self.assertEqual(self.store()["epics"], [{"id": "E-01", "titre": "Durcir le board", "vague": 1}])
        rc, out, _ = self.cli("epic-new", "E-01", "autre titre", "--maj")
        self.assertEqual(rc, 0)
        self.assertIn("replaced", out)
        # `--maj` REMPLACE l'entrée : `vague` n'est pas reportée.
        self.assertEqual(self.store()["epics"], [{"id": "E-01", "titre": "autre titre"}])

    def test_registre_trie_par_numero_et_non_par_texte(self):
        for eid in ("E-20", "E-100", "E-03"):
            self.epic_new(eid, f"epic {eid}")
        self.assertEqual([e["id"] for e in self.store()["epics"]], ["E-03", "E-20", "E-100"])

    def test_attributs_stockes_seulement_s_ils_sont_donnes(self):
        rc, _, _ = self.cli("epic-new", "E-01", "t", "--vague", "2", "--priorite", "P1",
                            "--exclusive", "--risque", "un risque")
        self.assertEqual(rc, 0)
        self.epic_new("E-02", "nu")
        self.assertEqual(self.store()["epics"], [
            {"id": "E-01", "titre": "t", "vague": 2, "priorite": "P1", "exclusive": True, "risque": "un risque"},
            {"id": "E-02", "titre": "nu"},
        ])

    def test_aucune_intention_de_sync_et_maj_identique_n_ecrit_rien(self):
        self.new()
        avant = len(self.store()["sync_outbox"])
        self.epic_new()
        self.assertEqual(len(self.store()["sync_outbox"]), avant)
        mtime = self.store_path.stat().st_mtime_ns
        self.assertIn("unchanged", self.epic_new(maj=True))
        self.assertEqual(self.store_path.stat().st_mtime_ns, mtime)


class NewEpicTests(_Banc):
    def test_epic_inconnue_ne_cree_aucune_tache(self):
        """Depuis C2 (T-00000726) aucun compteur n'est stocké : l'égalité porte sur
        les tâches seules, et le magasin n'a toujours pas de `next_id`."""
        self.new()
        avant = self.store()
        rc, _, err = self.cli("new", "t", "--epic", "E-99")
        self.assertNotEqual(rc, 0)
        self.assertIn("unknown epic E-99", err)
        apres = self.store()
        self.assertEqual(apres["tasks"], avant["tasks"])
        self.assertNotIn("next_id", apres)

    def test_la_validation_precede_l_allocation(self):
        """MUTANT : l'id frappé (`record_id_module()`) AVANT la validation de l'epic dans
        `new_task` ⇒ l'allocateur est appelé sur un refus, rouge. (Un contrôle du
        store seul serait VACANT : un refus ne sauve rien dans les deux ordres.)"""
        with mock.patch.object(tasks, "record_id_module", wraps=tasks.record_id_module) as alloc:
            self.refus(tasks.new_task, self.root, "t", "", "", epic="E-99")
            alloc.assert_not_called()
            self.epic_new()
            self.new(epic="E-01")
            alloc.assert_called_once()

    def test_epic_vide_refusee_en_ecriture(self):
        rc, _, err = self.cli("new", "t", "--epic", "")
        self.assertNotEqual(rc, 0)
        self.assertIn("--retirer", err)
        self.assertFalse(self.store_path.exists())

    def test_epic_valide_pose_le_champ_et_new_nu_n_en_pose_pas(self):
        self.epic_new()
        rc, out, _ = self.cli("new", "t", "--epic", "E-01")
        self.assertEqual(rc, 0, out)
        tid = out.split()[1]
        self.assertEqual(self.task(tid)["epic"], "E-01")
        self.assertNotIn("epic", self.task(self.new()))

    def test_titre_qui_ouvre_sur_sa_propre_epic_refuse(self):
        """R10 à la création. MUTANT : contrôle du titre retiré de `new_task` ⇒ créée, rouge."""
        self.epic_new()
        msg = self.refus(tasks.new_task, self.root, "[E-01][BK-001] t", "", "", epic="E-01")
        self.assertIn("print twice", msg)
        self.assertFalse(self.store()["tasks"])


class EpicSousUlidTests(_Banc):
    """1(i) (bascule C2 de T-00000726) — sous le VRAI `mint`, une tâche NOUVELLE est
    un `T-<ULID>` et l'epic la suit de bout en bout : `new --epic` la pose,
    `list --epic` la rend, `epic <id> --retirer` la détache ; aucun `next_id` n'est
    écrit. MUTANT : la frappe rendue au compteur ⇒ un `T-0000000N`, rouge."""

    def test_i_une_tache_ULID_porte_son_epic_se_liste_et_se_detache(self):
        self.epic_new()
        rc, out, err = self.cli("new", "t", "--epic", "E-01")
        self.assertEqual(rc, 0, err)
        tid = out.split()[1]
        self.assertTrue(tasks.is_ulid_id(tid), tid)
        self.assertEqual(self.task(tid)["epic"], "E-01")
        rc, out, err = self.cli("list", "--epic", "E-01", "--json")
        self.assertEqual(rc, 0, err)
        self.assertEqual([t["id"] for t in json.loads(out)], [tid])
        rc, _, err = self.cli("epic", tid, "--retirer")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("epic", self.task(tid))
        self.assertNotIn("next_id", self.store())


class EpicVerbeTests(_Banc):
    def setUp(self):
        super().setUp()
        self.epic_new()
        self.t = self.new()

    def test_epic_inconnue_refusee(self):
        """MUTANT : registre non vérifié dans `set_epic` ⇒ `E-99` posée, rouge."""
        rc, _, err = self.cli("epic", self.t, "E-99")
        self.assertNotEqual(rc, 0)
        self.assertIn("unknown epic E-99", err)
        self.assertNotIn("epic", self.task(self.t))

    def test_epic_vide_refusee_et_le_message_nomme_retirer(self):
        rc, _, err = self.cli("epic", self.t, "")
        self.assertNotEqual(rc, 0)
        self.assertIn("--retirer", err)

    def test_epic_sans_valeur_ni_retirer_rc2(self):
        self.assertEqual(self.cli("epic", self.t)[0], 2)

    def test_epic_et_retirer_ensemble_rc2(self):
        tasks.set_epic(self.root, self.t, "E-01")
        rc, _, err = self.cli("epic", self.t, "E-01", "--retirer")
        self.assertEqual(rc, 2)
        self.assertIn("not both", err)
        self.assertEqual(self.task(self.t)["epic"], "E-01")

    def test_retirer_retire_la_cle(self):
        tasks.set_epic(self.root, self.t, "E-01")
        rc, out, _ = self.cli("epic", self.t, "--retirer")
        self.assertEqual(rc, 0)
        self.assertIn("epic cleared", out)
        self.assertNotIn("epic", self.task(self.t))

    def test_vaut_pour_une_tache_running(self):
        tasks.set_state(self.root, self.t, "running")
        self.assertIn("→ epic E-01", tasks.set_epic(self.root, self.t, "E-01"))
        self.assertEqual((self.task(self.t)["state"], self.task(self.t)["epic"]), ("running", "E-01"))

    def test_epic_une_intention_de_sync_au_snapshot_gele(self):
        """MUTANT : `enqueue_sync_intent` retiré de `set_epic` ⇒ l'outbox ne
        grandit pas, rouge. Le snapshot GELÉ ne porte jamais `epic` (limite dite)."""
        avant = len(self.store()["sync_outbox"])
        tasks.set_epic(self.root, self.t, "E-01")
        outbox = self.store()["sync_outbox"]
        self.assertEqual(len(outbox), avant + 1)
        self.assertEqual(outbox[-1]["affected_task_ids"], [self.t])
        self.assertEqual(set(outbox[-1]["after"]), set(tasks.SYNC_SNAPSHOT_FIELDS))
        self.assertNotIn("epic", tasks.SYNC_SNAPSHOT_FIELDS)

    def test_epic_sur_un_titre_deja_prefixe_avertit_sans_refuser(self):
        """L'ordre de l'importeur (`epic` PUIS `retitle`) tient : rc 0, epic posée,
        et STDERR donne le `retitle` prêt à lancer. MUTANT : `set_epic` silencieux
        (avertissement jamais imprimé) ⇒ rouge."""
        ancien = self.new("[E-01][BK-001] ancien titre")
        rc, out, err = self.cli("epic", ancien, "E-01")
        self.assertEqual(rc, 0, err)
        self.assertIn(f"{ancien} → epic E-01", out)
        self.assertEqual(self.task(ancien)["epic"], "E-01")
        self.assertIn("warning", err)
        self.assertIn(f"tasks.py retitle {ancien} '[BK-001] ancien titre'", err)
        # Le geste répété, sans effet, le redit : le double affichage persiste.
        self.assertIn(f"tasks.py retitle {ancien} ", self.cli("epic", ancien, "E-01")[2])
        # La commande donnée passe R10 et rend le titre une seule fois préfixé.
        self.assertIn("retitled", tasks.retitle_task(self.root, ancien, "[BK-001] ancien titre"))
        self.assertEqual(tasks.cell(self.task(ancien), "task"), "[E-01][BK-001] ancien titre")
        # Non-vacuité du silence : un titre ordinaire n'avertit pas.
        self.assertEqual(self.cli("epic", self.t, "E-01")[2], "")

    def test_retitle_refuse_le_prefixe_de_sa_propre_epic(self):
        """R10. MUTANT : `retitle` qui stocke le préfixe ⇒ `[E-01]` stocké, rouge."""
        tasks.set_epic(self.root, self.t, "E-01")
        rc, _, err = self.cli("retitle", self.t, "[E-01][BK-001] nouveau")
        self.assertEqual(rc, 2)
        self.assertIn("print twice", err)
        self.assertEqual(self.task(self.t)["task"], "tache de banc")
        # Une AUTRE epic en tête reste du texte ; une tâche sans epic retitre librement.
        self.assertIn("retitled", tasks.retitle_task(self.root, self.t, "[E-02] texte libre"))
        autre = self.new()
        self.assertIn("retitled", tasks.retitle_task(self.root, autre, "[E-01][BK-001] ancien"))


# ===========================================================================
# Lectures — `epic-list`, `list --epic`, vues à largeur fixe, `--json` nu.
# ===========================================================================
class LecturesTests(_Banc):
    def setUp(self):
        super().setUp()
        self.epic_new("E-01", "Durcir le board", vague=2, priorite="P1", exclusive=True)
        self.epic_new("E-02", "Vide")
        self.a = self.new("a", epic="E-01")
        self.b = self.new("b", epic="E-01")
        self.c = self.new("c", epic="E-01")
        self.nu = self.new("sans epic")
        tasks.set_state(self.root, self.a, "running")
        tasks.set_state(self.root, self.c, "done", stage="clos")
        data = self.store()
        data["tasks"].append(self.legacy("T-00000099", "porte une epic hors registre", epic="E-99"))
        self.write_store(data)

    def test_epic_list_une_ligne_par_epic_et_compte_par_etat(self):
        rc, out, _ = self.cli("epic-list")
        self.assertEqual(rc, 0)
        lignes = out.strip().splitlines()
        self.assertEqual([l.split(" | ")[0] for l in lignes], ["E-01", "E-02", "E-99"])
        self.assertEqual(lignes[0], "E-01 | Durcir le board | vague=2 P1 exclusive | "
                                    "pending=1 running=1 blocked=0 done=1")
        self.assertEqual(lignes[1], "E-02 | Vide | — | pending=0 running=0 blocked=0 done=0")
        self.assertIn("(hors registre)", lignes[2])

    def test_epic_list_json(self):
        rc, out, _ = self.cli("epic-list", "--json")
        self.assertEqual(rc, 0)
        par_id = {l["id"]: l for l in json.loads(out)}
        self.assertEqual(par_id["E-01"]["compte"], {"pending": 1, "running": 1, "blocked": 0, "done": 1})
        self.assertEqual((par_id["E-01"]["total"], par_id["E-01"]["exclusive"]), (3, True))
        self.assertTrue(par_id["E-99"]["hors_registre"])

    def test_epic_list_sur_un_board_sans_epic_dit_une_phrase(self):
        self.write_store({"next_id": 2, "tasks": [self.legacy()]})
        rc, out, _ = self.cli("epic-list")
        self.assertEqual((rc, out.strip()), (0, "(no epic: the registry is empty and no task carries one)"))

    def test_list_epic_filtre_et_compte(self):
        rc, out, _ = self.cli("list", "--epic", "E-01")
        self.assertEqual(rc, 0)
        self.assertIn("filter: epic=E-01 (3 tasks)", out)
        self.assertNotIn(self.nu, out)
        rc, out, _ = self.cli("list", "--epic", "E-01", "--state", "pending")
        self.assertIn("(1 task)", out)
        self.assertIn(self.b, out)

    def test_list_epic_vide_rend_les_taches_sans_epic(self):
        rc, out, _ = self.cli("list", "--epic", "")
        self.assertEqual(rc, 0)
        self.assertIn("epic=(sans epic) (1 task)", out)
        self.assertIn(self.nu, out)

    def test_list_epic_inconnue_refusee_mais_hors_registre_portee_lue(self):
        rc, _, err = self.cli("list", "--epic", "E-77")
        self.assertEqual(rc, 2)
        self.assertIn("unknown epic 'E-77'", err)
        rc, out, _ = self.cli("list", "--epic", "E-99")
        self.assertEqual(rc, 0)
        self.assertIn("T-00000099", out)

    def test_list_json_epic_rend_moins_que_le_board(self):
        """C6. MUTANT : branche `--epic` placée APRÈS la branche `--json` nue ⇒ le
        board entier, rouge."""
        rc, out, _ = self.cli("list", "--json", "--epic", "E-01")
        self.assertEqual(rc, 0)
        rendu = json.loads(out)
        self.assertLess(len(rendu), len(self.store()["tasks"]))
        self.assertEqual({t["epic"] for t in rendu}, {"E-01"})
        rc, out, err = self.cli("list", "--json", "--epic", "E-02")
        self.assertEqual((rc, json.loads(out)), (0, []))
        self.assertIn("no task matching epic=E-02", err)

    def test_list_json_nu_garde_la_forme_exacte(self):
        """Consommateur : binome-trace.sh lit `list --json` NU. Titre brut, clé `epic`."""
        rc, out, _ = self.cli("list", "--json")
        self.assertEqual(rc, 0)
        attendu = json.dumps(tasks.sorted_tasks(tasks.load(self.root)["tasks"]), indent=2, ensure_ascii=False)
        self.assertEqual(out, attendu + "\n")
        a = next(t for t in json.loads(out) if t["id"] == self.a)
        self.assertEqual((a["task"], a["epic"]), ("a", "E-01"))

    def test_matrice_fermee_de_list_epic(self):
        """MUTANT : troisième boucle de refus retirée de `main` ⇒ rc 0, rouge."""
        for extra in (["--group"], ["--session"], ["--task", self.a], ["--chantier", CHANTIER],
                      ["--blocked-by", self.a], ["--depends-on", self.a]):
            with self.subTest(extra=extra):
                rc, _, err = self.cli("list", "--epic", "E-01", *extra)
                self.assertEqual(rc, 2)
                self.assertIn("list --epic does not combine with", err)

    def test_list_task_prefixe_le_titre_et_ajoute_la_ligne_epic(self):
        rc, out, _ = self.cli("list", "--task", self.b)
        self.assertEqual(rc, 0)
        lignes = {l.split(" : ")[0].strip(): l.split(" : ", 1)[1] for l in out.splitlines() if " : " in l}
        self.assertEqual((lignes["task"], lignes["epic"]), ("[E-01]b", "E-01"))


class RenduTests(_Banc):
    def test_une_ligne_de_table_egale_l_ancien_titre(self):
        """MUTANT : `cell` sans préfixe ⇒ la ligne migrée perd `[E-01]`, rouge."""
        ancien = self.legacy(title=f"[E-01][BK-001][P1] {LONG}")
        migre = self.legacy(title=f"[BK-001][P1] {LONG}", epic="E-01")
        self.assertEqual(tasks.render_table([ancien]), tasks.render_table([migre]))

    def test_vues_a_largeur_fixe_identiques_a_l_octet(self):
        """`list`, `list --session`, TASKS.md : le board d'avant migration et celui
        d'après (préfixe dans le champ) rendent les mêmes octets, date comprise
        (même jour). MUTANT : `cell` sans préfixe ⇒ rouge."""
        def rendus(taches: list[dict], epics: list[dict] | None) -> tuple[str, str, str]:
            data = {"next_id": 9, "tasks": taches}
            if epics is not None:
                data["epics"] = epics
            self.write_store(data)
            tasks.render_view(self.root)
            vue = (self.d / ".agents" / "state" / "local" / "TASKS.md").read_text(encoding="utf-8")
            return self.cli("list")[1], self.cli("list", "--session")[1], vue
        avant = rendus([self.legacy("T-00000001", f"[E-01][BK-001] {LONG}"),
                        self.legacy("T-00000002", "sans epic")], None)
        apres = rendus([self.legacy("T-00000001", f"[BK-001] {LONG}", epic="E-01"),
                        self.legacy("T-00000002", "sans epic")], [{"id": "E-01", "titre": "t"}])
        self.assertEqual(avant, apres)

    def test_une_epic_non_chaine_ne_rend_jamais_de_prefixe(self):
        self.assertEqual(tasks.cell(self.legacy(title="t", epic=42), "task"), "t")
        self.assertEqual(tasks.cell(self.legacy(title="t", epic="E-05"), "task"), "[E-05]t")


class FiletsTests(_Banc):
    def test_mutating_porte_epic_et_epic_new_et_pas_epic_list(self):
        """Trap 1 : les filets lisent le TEXTE du littéral. MUTANT : `"epic"`
        retiré du littéral `mutating` ⇒ rouge."""
        source = TASKS.read_text(encoding="utf-8")
        debut = source.index("mutating = args.cmd in {")
        bloc = source[debut:][: source[debut:].index("} and not")]
        self.assertIn('"done"', bloc)  # non-vacuité du bloc extrait
        self.assertIn('"epic"', bloc)
        self.assertIn('"epic-new"', bloc)
        self.assertNotIn('"epic-list"', bloc)
        self.assertNotIn('"commit-run-exports"', bloc)
        # T-00000724 — `commit-stores` est HORS du littéral lui aussi : existence
        # d'abord (un verbe retiré ne doit pas se lire « bien exclu »), absence ensuite.
        self.assertIn('"commit-stores"', source)
        self.assertNotIn('"commit-stores"', bloc)

    def test_save_reste_a_cles_triees_avec_epics(self):
        data = {"tasks": [dict(reversed(list(self.legacy(epic="E-01").items())))],
                "epics": [{"titre": "t", "id": "E-01", "exclusive": True}],
                "sync_outbox": [], "sync_correlations": {}, "next_id": 2}
        tasks.save(self.root, data)
        paires: list[list[str]] = []
        json.loads(self.store_path.read_text(encoding="utf-8"),
                   object_pairs_hook=lambda p: paires.append([k for k, _ in p]) or dict(p))
        self.assertTrue(any("epics" in cles for cles in paires))
        for cles in paires:
            self.assertEqual(cles, sorted(cles))


# ===========================================================================
# La garde de plan `EPIC:` au `done` — dans `set_state`, juste après les arêtes.
# ===========================================================================
class GardeTests(_Banc):
    def armer(self):
        (self.d / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED").write_text(
            f"spec=spec.md\nchantier={CHANTIER}\n", encoding="utf-8")

    def plan(self, rel: str, roster: str, epics: str = "") -> str:
        p = self.d / rel
        p.write_text(PLAN.format(roster=roster, epics=epics), encoding="utf-8")
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def specs_json(self, entrees: list[dict]):
        (self.d / ".agents" / "state" / "specs" / "SPECS.json").write_text(
            json.dumps({"next_id": 99999, "entries": entrees}, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def decision(sid: str, tid: str) -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": "une décision",
                "text": "", "date": "2026-09-27"}

    @staticmethod
    def trace(sid: str, tid: str, rel: str, sha: str) -> dict:
        return {"id": sid, "task": tid, "kind": "decision", "title": "plan approuvé",
                "text": f"plan={rel} sha256={sha}", "date": "2026-09-27"}

    def approuve(self, tid: str, epics: str = "", roster: str | None = None, armer: bool = True) -> None:
        sha = self.plan("plans/p.md", roster or tid, epics)
        self.specs_json([self.decision("S-00001558", tid), self.trace("S-00002000", tid, "plans/p.md", sha)])
        if armer:
            self.armer()

    def done(self, tid: str, **kw) -> str:
        return tasks.set_state(self.root, tid, "done", stage="clos par le banc", **kw)

    def test_ligne_conforme_et_epic_posee_passe(self):
        self.epic_new()
        t = self.new(epic="E-01")
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        self.assertIn("→ done", self.done(t))

    def test_epic_absente_refus_qui_donne_la_commande(self):
        """MUTANT : jambe epic retirée de `set_state` ⇒ le `done` passe, rouge."""
        self.epic_new()
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        msg = self.refus(self.done, t)
        self.assertIn(f"tasks.py epic {t} E-01", msg)
        self.assertNotIn("epic-new", msg)
        self.assertIn("--sans-cible", msg)
        self.assertEqual(self.task(t)["state"], "pending")

    def test_epic_differente_refus_qui_nomme_l_actuelle(self):
        self.epic_new()
        self.epic_new("E-02", "autre")
        t = self.new(epic="E-02")
        self.approuve(t, f"- EPIC: {t} -> E-01\n")  # puce `- ` tolérée
        msg = self.refus(self.done, t)
        self.assertIn("la range sous E-02", msg)
        self.assertIn(f"tasks.py epic {t} E-01", msg)

    def test_plan_sans_ligne_passe_l_epic_reste_optionnelle(self):
        # Chaque tâche porte SA trace : sans elle, `evaluer_done` refuserait en amont
        # (chantier armé sans plan), et le témoin rougirait pour une autre raison.
        self.epic_new()
        for epic in (None, "E-01"):
            with self.subTest(epic=epic):
                t = self.new(epic=epic)
                self.approuve(t)
                self.assertIn("→ done", self.done(t))

    def test_ligne_fautive_refus_qui_la_nomme(self):
        """MUTANT : `releve_epic` qui ignore les lignes fautives ⇒ inerte, rouge."""
        t = self.new()
        self.approuve(t, f"EPIC: {t} => E-01\n")
        msg = self.refus(self.done, t)
        self.assertIn("ligne malformée", msg)
        self.assertIn(f"EPIC: {t} => E-01", msg)

    def test_ligne_proche_indentee_nommee_jamais_ignoree(self):
        t = self.new()
        self.approuve(t, f"   EPIC: {t} -> E-01\n")
        self.assertIn("ligne proche du mot-clé", self.refus(self.done, t))

    def test_deux_epics_pour_une_tache_refus(self):
        self.epic_new()
        self.epic_new("E-02", "autre")
        t = self.new(epic="E-01")
        self.approuve(t, f"EPIC: {t} -> E-01\nEPIC: {t} -> E-02\n")
        self.assertIn("deux epics", self.refus(self.done, t))

    def test_sans_cible_par_la_cli_passe_et_se_voit(self):
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        rc, out, err = self.cli("done", t, "--raison", "clos", "--sans-cible", "pont de banc")
        self.assertEqual(rc, 0, err)
        self.assertIn("[SANS CIBLE : pont de banc]", self.task(t)["stage"])

    def test_marqueur_absent_inerte(self):
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n", armer=False)
        self.assertIn("→ done", self.done(t))

    def test_epic_hors_registre_le_message_donne_epic_new(self):
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-05\n")
        msg = self.refus(self.done, t)
        self.assertIn('tasks.py epic-new E-05 "<titre>"', msg)
        self.assertLess(msg.index("epic-new E-05"), msg.index(f"tasks.py epic {t} E-05"))

    def test_ligne_d_une_autre_tache_ignoree(self):
        self.epic_new()
        t, u = self.new(), self.new()
        self.approuve(t, f"EPIC: {u} -> E-01\n", roster=f"{t} {u}")
        self.assertIn("→ done", self.done(t))

    def test_w8c_un_seul_lecteur_du_regime(self):
        """W8c propre. `_arme_pour_tache` forcé à None sur marqueur ARMÉ ⇒ garde
        inerte. MUTANT : garde qui relit le marqueur en direct ⇒ elle mord, rouge."""
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        data = tasks.load(self.root)
        self.assertIsNotNone(tasks.refus_epic_au_done(self.root, t, data))  # non-vacuité
        with mock.patch.object(pc, "_arme_pour_tache", return_value=None):
            self.assertIsNone(tasks.refus_epic_au_done(self.root, t, data))

    def test_de_bout_en_bout_main_rc2(self):
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        rc, _, err = self.cli("done", t, "--raison", "clos")
        self.assertEqual(rc, 2)
        self.assertIn("EPIC:", err)
        self.assertEqual(self.task(t)["state"], "pending")

    def test_set_state_direct_hors_cli_refuse_et_sans_cible_passe_marque(self):
        """Le pont V3 appelle `set_state` en direct AVEC `sans_cible` : il franchit la
        garde, et la marque le dit. Sans `sans_cible`, le chemin hors CLI refuse."""
        t = self.new()
        self.approuve(t, f"EPIC: {t} -> E-01\n")
        self.refus(tasks.set_state, self.root, t, "done", stage="clos")
        self.assertIn("→ done", tasks.set_state(self.root, t, "done", stage="clos", sans_cible="pont V3"))
        self.assertIn("[SANS CIBLE : pont V3]", self.task(t)["stage"])

    def test_plan_du_slot_running_r2(self):
        self.epic_new()
        slot, t = self.new(), self.new()
        sha = self.plan("plans/slot.md", f"{slot} {t}", f"EPIC: {t} -> E-01\n")
        self.specs_json([self.decision("S-00001558", slot), self.trace("S-00002001", slot, "plans/slot.md", sha)])
        self.armer()
        tasks.set_state(self.root, slot, "running")
        msg = self.refus(self.done, t)
        self.assertIn("[cible relevée sur", msg)
        self.assertIn(f"tasks.py epic {t} E-01", msg)


# ===========================================================================
# Parité CLI ↔ dashboard : `cell` (tasks_rendu.py) et `epicPrefixed` (epics.js)
# rendent le MÊME titre sur un fixture JSON commun.
# ===========================================================================
NODE = shutil.which("node")
EPICS_JS = HERE.parent / "ui-src" / "src" / "lib" / "epics.js"
# DOMAINE : des tâches que `load` accepte, donc à titre NON VIDE. Hors fixture, et
# dit : un titre vide (refusé par `load`) rend `—` par `cell`, `""` par le JS.
PARITE = [
    {"task": "[BK-001][P1] titre migré", "epic": "E-01"},
    {"task": "sans epic"},
    {"task": "epic non chaîne", "epic": 42},
    {"task": "epic objet", "epic": {"id": "E-01"}},
    {"task": "epic nulle", "epic": None},
    {"task": "epic vide", "epic": ""},
    {"task": "id non rogné", "epic": " E-01"},
    {"task": "Référence : docs/interne/chantier/backlog/backlog.yaml.", "epic": "E-100"},
    {"task": 42, "epic": "E-02"},
]


class PariteCellEpicPrefixedTests(unittest.TestCase):
    def test_cell_et_epic_prefixed_rendent_le_meme_titre(self):
        """MUTANT : `cell` avec un séparateur (`[E-NN] titre`) ⇒ les deux rendus
        divergent, rouge. SAUTÉ, et dit, si `node` manque ou si le module UI est
        absent de l'arbre (copie partielle, adoptant sans `ui-src`)."""
        if NODE is None:
            self.skipTest("node absent du PATH : parité cell ↔ epicPrefixed NON jouée")
        if not EPICS_JS.exists():
            self.skipTest(f"{EPICS_JS} absent : parité cell ↔ epicPrefixed NON jouée")
        # L'URL du module passe en ARGUMENT, jamais interpolée dans le code.
        script = ("const { epicPrefixed } = await import(process.argv[1]);"
                  "let s = ''; for await (const c of process.stdin) s += c;"
                  "process.stdout.write(JSON.stringify(JSON.parse(s).map(epicPrefixed)));")
        p = subprocess.run([NODE, "--input-type=module", "-e", script, EPICS_JS.as_uri()],
                           input=json.dumps(PARITE, ensure_ascii=False), capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        rendu_js = json.loads(p.stdout)
        rendu_py = [tasks.cell(t, "task") for t in PARITE]
        self.assertEqual(rendu_py, rendu_js)
        self.assertEqual(rendu_py[0], "[E-01][BK-001][P1] titre migré")  # non-vacuité


class ReleveEpicTests(unittest.TestCase):
    def test_grammaire_fermee_et_pure(self):
        texte = (
            "EPIC: T-00000007 -> E-01\n"
            "- EPIC: T-7 -> E-01\n"             # id court = même tâche, doublon dédoublonné
            "epic : T-00000007 -> E-09\n"       # minuscules = prose (W9)
            "```\nEPIC: T-00000007 -> E-08\n```\n"  # bloc de code ignoré
            "prose qui cite `EPIC: T-<id> -> E-NN` au milieu d'une ligne\n"
            "EPIC: T-00000008 -> E-03\n"         # autre tâche
        )
        self.assertEqual(tasks.releve_epic(texte, "T-00000007"), (["E-01"], []))
        self.assertEqual(tasks.releve_epic(texte, "T-00000008"), (["E-03"], []))
        self.assertEqual(tasks.releve_epic("", "T-00000007"), ([], []))

    def test_lignes_fautives_nommees_quelle_que_soit_la_tache(self):
        for ligne in ("EPIC : T-00000009 -> E-01", "EPICS: T-00000009 -> E-01",
                      "EPIC: T-00000009 -> E-1", "* EPIC: T-00000009 -> E-01", "**EPIC:** T-00000009 -> E-01"):
            with self.subTest(ligne=ligne):
                epics, fautives = tasks.releve_epic(ligne + "\n", "T-00000007")
                self.assertEqual(epics, [])
                self.assertEqual(len(fautives), 1, fautives)


# T-00001040 — `EPIC: T-<ULID> -> E-NN` (étape 4 du plan de T-00000726). Fixtures
# FIXES (réserve B-C8) : un corps ULID qui finit par une LETTRE (`numeric_id` y
# lève) et un qui finit par un CHIFFRE (`numeric_id` le lit 2, comme T-00000002).
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"


class ReleveEpicUlidTests(unittest.TestCase):
    def test_constante_extrait_l_id_entier_ulid_et_ancien(self):
        """MUTANTS R2 (numérique retiré), branche ULID retirée ⇒ rouge."""
        for tid in (f"T-{U_LETTER}", f"T-{U_DIGIT}", "T-00000007", "T-012"):
            with self.subTest(tid=tid):
                m = tasks._EPIC_LIGNE.match(f"EPIC: {tid} -> E-01")
                self.assertIsNotNone(m, tid)
                self.assertEqual(m.group(1), tid)

    def test_constante_ne_lit_aucun_ulid_voisin(self):
        """`T-0<ULID>`, `T-<ULID>A`, corps minuscule : aucune ligne conforme."""
        for tid in (f"T-0{U_LETTER}", f"T-{U_LETTER}A", f"T-{U_LETTER.lower()}", f"T-{U_LETTER[:-1]}"):
            with self.subTest(tid=tid):
                self.assertIsNone(tasks._EPIC_LIGNE.match(f"EPIC: {tid} -> E-01"), tid)

    def test_une_tache_ulid_a_son_epic(self):
        """MUTANT : :357 laissé sur `numeric_id` ⇒ `BoardError` sur un corps qui
        finit par une lettre, rouge."""
        texte = f"EPIC: T-{U_LETTER} -> E-01\n"
        self.assertEqual(tasks.releve_epic(texte, f"T-{U_LETTER}"), (["E-01"], []))
        self.assertEqual(tasks.releve_epic(texte, "T-00000001"), ([], []))

    def test_mixte_un_ulid_n_est_jamais_l_ancien_de_meme_chiffre_final(self):
        """MUTANT : :357 laissé sur `numeric_id` ⇒ `T-<U_DIGIT>` vaut T-00000002,
        deux epics pour T-00000002, rouge (comparaison par `identity_key`)."""
        texte = f"EPIC: T-{U_DIGIT} -> E-02\nEPIC: T-00000002 -> E-03\n"
        self.assertEqual(tasks.releve_epic(texte, "T-00000002"), (["E-03"], []))
        self.assertEqual(tasks.releve_epic(texte, f"T-{U_DIGIT}"), (["E-02"], []))
        self.assertEqual(tasks.releve_epic(texte, "T-2"), (["E-03"], []))

    def test_une_ligne_t_0_ulid_est_fautive_et_nommee(self):
        epics, fautives = tasks.releve_epic(f"EPIC: T-0{U_LETTER} -> E-01\n", f"T-{U_LETTER}")
        self.assertEqual(epics, [])
        self.assertEqual(len(fautives), 1, fautives)


if __name__ == "__main__":
    unittest.main()
