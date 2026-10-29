"""L'ACTEUR DE `start`/`stage` (T-01M5DBFK3XKKM2VHQM5RE4TP6K) — banc FRÈRE de `test_tasks.py`.

Déplacé À L'IDENTIQUE depuis `test_tasks.py` (cliquet de longueur : le banc d'origine est à son
plafond, tout nouveau témoin de l'acteur vient ici). `tasks.py` chargé par chemin, comme dans le banc
d'origine ; `_id_rendu` en est une recopie (aide de module, huit lignes). Aucun parcours d'arbre.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


TASKS_PATH = Path(__file__).with_name("tasks.py")
SPEC = importlib.util.spec_from_file_location("tasks_acteur_banc", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)
tasks._RESOLVEUR_V3.charger_paquet(Path(__file__).resolve().parents[2], "agentic_v3")


def _id_rendu(message: str) -> str:
    """L'id que ``new_task`` a RENDU (``TASKS: <id> → pending``), jamais un id prédit (recopie de
    ``test_tasks._id_rendu``)."""
    trouve = re.fullmatch(r"TASKS: (\S+) → pending", message)
    assert trouve, f"unexpected `new` message: {message!r}"
    return trouve.group(1)


ACTEUR_A = {"auteur": {"nom": "Alice", "email": "alice@exemple.invalid"}, "copie": "0123456789abcdef"}
ACTEUR_B = {"auteur": {"nom": "Bob", "email": "bob@exemple.invalid"}, "copie": "fedcba9876543210"}
_KIT_ACTEUR = Path(__file__).resolve().parents[2]


def _env_identite_isolee(**en_plus: str) -> dict[str, str]:
    """L'environnement d'un sous-processus dont l'identité Git ne vient QUE du dépôt de banc :
    aucune `GIT_*` héritée, configurations globale et système coupées."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "CLAUDE_PROJECT_DIR"}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    env.update(en_plus)
    return env


class ActeurBoardTests(unittest.TestCase):
    """L'ACTEUR DE `start`/`stage` (T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot A) : `start_actor` posé à la
    première prise avec un auteur, gardé d'un cycle à l'autre, changé par une reprise prouvée seule ; `stage_actor` écrit ou RETIRÉ à chaque réécriture du stage,
    gardé avec un stage préservé ; l'identité résolue par la CLI HORS du verrou, caviardée puis plafonnée ;
    la copie de V3, ou un tirage frère de la partition quand V3 est absent ; jamais un refus."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "depot"
        self.root.mkdir()
        self.etat = self.base / "etat"
        self.etat.mkdir()
        self.r = str(self.root)
        subprocess.run(["git", "init", "-q", self.r], check=True, capture_output=True,
                       env=_env_identite_isolee())
        env = mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(self.etat),
                                           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        for cle in [k for k in os.environ if k.startswith("GIT_") and k not in (
                "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")]:
            del os.environ[cle]  # rendu par `env.stop`

    def git_config(self, cle: str, valeur: str) -> None:
        subprocess.run(["git", "-C", self.r, "config", cle, valeur], check=True, capture_output=True)

    def nouvelle(self, titre: str = "tâche d'acteur") -> str:
        return _id_rendu(tasks.new_task(self.r, titre, "dev-multi"))

    def tache(self, tid: str) -> dict[str, Any]:
        return tasks.find(tasks.load(self.r), tid)

    def test_block_note_et_unblock_ne_laissent_pas_de_stage_actor_perime(self) -> None:
        """MUTANTS : retirer un `pop("stage_actor")` de `block --note`, de `block --on` sans note,
        d'`unblock`, de `reopen` ou du rebloquage d'`autre` laisse l'acteur du stage précédent."""
        a, b, c, d = (self.nouvelle(f"t{i}") for i in range(4))
        tasks.set_state(self.r, a, "running", stage="dev", acteur=ACTEUR_A)
        self.assertEqual(ACTEUR_A, self.tache(a)["stage_actor"])
        tasks.block_task(self.r, a, note="attente pilote")
        self.assertNotIn("stage_actor", self.tache(a), "block --note")

        tasks.set_state(self.r, c, "blocked", stage="motif signé", acteur=ACTEUR_A)
        self.assertEqual(ACTEUR_A, self.tache(c)["stage_actor"])
        tasks.unblock_task(self.r, c)
        self.assertEqual("", self.tache(c)["stage"])
        self.assertNotIn("stage_actor", self.tache(c), "unblock")

        tasks.stage_task(self.r, d, "", acteur=ACTEUR_A)
        tasks.block_task(self.r, d, blocked_on=c)
        self.assertEqual(f"on {c}", self.tache(d)["stage"])
        self.assertNotIn("stage_actor", self.tache(d), "block --on sans note sur un stage vide")

        tasks.block_task(self.r, b, note="attend a", blocked_on=a)
        tasks.set_state(self.r, a, "done", stage="fini", acteur=ACTEUR_A)
        self.assertEqual(ACTEUR_A, self.tache(a)["stage_actor"])
        tasks.stage_task(self.r, b, "reprise", acteur=ACTEUR_B)
        self.assertEqual(ACTEUR_B, self.tache(b)["stage_actor"])
        tasks.reopen_task(self.r, a, "clôture fausse")
        self.assertNotIn("stage_actor", self.tache(a), "reopen")
        self.assertEqual(("blocked", f"re-bloquee : {a} rouverte"),
                         (self.tache(b)["state"], self.tache(b)["stage"]))
        self.assertNotIn("stage_actor", self.tache(b), "rebloquage du dépendant par reopen")

    def test_stage_kept_et_nettoyage_marque_preservent_acteur(self) -> None:
        """Un stage PRÉSERVÉ garde son acteur (`stage_kept` à travers `unblock`, `start` et la
        libération) ; un stage VIDÉ ou NETTOYÉ le perd (`tasks_etats.py` : sortie de `blocked`,
        libération au `done`, `efface_derogation_chaine`). MUTANTS : effacer l'acteur sous
        `stage_kept`, ou le garder à l'un des trois vidages, rompt l'égalité stage/acteur."""
        t, u, x, y, k = (self.nouvelle(f"t{i}") for i in range(5))
        tasks.set_state(self.r, t, "running", stage="review", acteur=ACTEUR_A)
        tasks.block_task(self.r, t, blocked_on=u)
        self.assertTrue(self.tache(t).get("stage_kept"))
        self.assertEqual(("review", ACTEUR_A), (self.tache(t)["stage"], self.tache(t)["stage_actor"]))
        tasks.unblock_task(self.r, t)
        self.assertEqual(("review", ACTEUR_A), (self.tache(t)["stage"], self.tache(t)["stage_actor"]))
        tasks.block_task(self.r, t, blocked_on=u)
        tasks.set_state(self.r, t, "running", acteur=ACTEUR_B)
        self.assertEqual(("review", ACTEUR_A), (self.tache(t)["stage"], self.tache(t)["stage_actor"]))
        self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"], "la propriété survit au blocage")

        tasks.set_state(self.r, x, "blocked", stage="motif", acteur=ACTEUR_A)
        tasks.set_state(self.r, x, "running", acteur=ACTEUR_B)
        self.assertEqual("", self.tache(x)["stage"])
        self.assertNotIn("stage_actor", self.tache(x), "sortie de blocked par start : motif vidé")

        tasks.block_task(self.r, y, blocked_on=u)
        tasks.stage_task(self.r, y, "motif signé", acteur=ACTEUR_A)
        tasks.set_state(self.r, k, "running", stage="critic", acteur=ACTEUR_B)
        tasks.block_task(self.r, k, blocked_on=u)
        tasks.set_state(self.r, u, "done", stage="fini", acteur=ACTEUR_A)
        self.assertEqual(("pending", ""), (self.tache(y)["state"], self.tache(y)["stage"]))
        self.assertNotIn("stage_actor", self.tache(y), "libération au done : motif vidé")
        self.assertEqual(("critic", ACTEUR_B), (self.tache(k)["stage"], self.tache(k)["stage_actor"]))

        marquee = {"stage": tasks.avec_marque_chaine("dev", "banc"), "sans_chaine": "banc",
                   "stage_actor": dict(ACTEUR_A)}
        tasks.efface_derogation_chaine(marquee)
        self.assertEqual("dev", marquee["stage"])
        self.assertNotIn("stage_actor", marquee, "nettoyage de la marque de dérogation")
        intacte = {"stage": "dev", "stage_actor": dict(ACTEUR_A)}
        tasks.efface_derogation_chaine(intacte)
        self.assertEqual(ACTEUR_A, intacte["stage_actor"], "rien nettoyé : l'acteur reste")

    def test_restart_running_garde_start_actor(self) -> None:
        """LA PROPRIÉTÉ EST DURABLE (S-01M5HH8QMC4E7SYN4K6AP2SMKE) : seul un transfert prouvé
        (`preuve_reprise`) la change. MUTANTS : écrire `start_actor` à chaque entrée dans `running`,
        ou l'effacer sur un cycle sans acteur, ou ignorer la preuve de reprise."""
        t = self.nouvelle()
        tasks.set_state(self.r, t, "running", stage="dev", acteur=ACTEUR_A)
        tasks.set_state(self.r, t, "running", stage="review", acteur=ACTEUR_B)
        self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"])
        self.assertEqual(ACTEUR_B, self.tache(t)["stage_actor"])
        tasks.set_state(self.r, t, "done", stage="fini", acteur=ACTEUR_A)
        tasks.set_state(self.r, t, "running", stage="relance", acteur=ACTEUR_B)
        self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"], "un nouveau cycle garde le propriétaire")
        tasks.set_state(self.r, t, "done", stage="fini 2", acteur=ACTEUR_B)
        tasks.set_state(self.r, t, "running", stage="sans acteur")
        self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"], "un cycle sans acteur garde le propriétaire")
        self.assertNotIn("stage_actor", self.tache(t))
        tasks.set_state(self.r, t, "done", stage="fini 3", acteur=ACTEUR_A)
        tasks.set_state(self.r, t, "running", stage="reprise", acteur=ACTEUR_B,
                        preuve_reprise={"ancien": dict(ACTEUR_A), "nouveau": dict(ACTEUR_B)})
        self.assertEqual(ACTEUR_B, self.tache(t)["start_actor"], "seule la reprise prouvée transfère")

    def test_block_unblock_du_pont_sans_identite_locale(self) -> None:
        """C25 — le pont V3 appelle `block_task`, `unblock_task` et `stage_running_task` SANS acteur :
        aucune identité locale n'est lue (ni `acteur_courant` ni git), le stage réécrit PERD son acteur,
        `start_actor` n'est pas touché. MUTANT : retirer le `pop` de `block --note` ou d'`unblock`."""
        t, r2 = self.nouvelle("t"), self.nouvelle("r2")
        tasks.set_state(self.r, t, "running", stage="dev", acteur=ACTEUR_A)
        with mock.patch.object(tasks, "acteur_courant", side_effect=AssertionError("identité lue")), \
                mock.patch.object(tasks, "_acteur_git", side_effect=AssertionError("git lu")):
            tasks.block_task(self.r, t, "statut V3 BLOCKED (op banc)")
            self.assertNotIn("stage_actor", self.tache(t))
            self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"])
            tasks.unblock_task(self.r, t)
            self.assertNotIn("stage_actor", self.tache(t))
            self.assertEqual(ACTEUR_A, self.tache(t)["start_actor"])
            tasks.set_state(self.r, r2, "running", stage="dev", acteur=ACTEUR_A)
            tasks.stage_running_task(self.r, r2, "critic")
            self.assertEqual("critic", self.tache(r2)["stage"])
            self.assertNotIn("stage_actor", self.tache(r2))
            self.assertEqual(ACTEUR_A, self.tache(r2)["start_actor"])

    def test_auteur_git_hostile_redige_et_plafonne(self) -> None:
        """L'auteur est `git config --get`, caviardé PUIS plafonné à `ACTEUR_PLAFOND` avec marque.
        MUTANTS : tronquer avant de caviarder (le jeton coupé n'est plus reconnu : `ghp_` fuit) ;
        garder la valeur brute ; `git var` (sans identité configurée, il rend l'hôte ou l'utilisateur
        système au lieu de None)."""
        if tasks._acteur_module_cadre("cadre.ledger.redaction", ("ledger", "redaction.py")) is None:
            self.skipTest("cadre.ledger.redaction introuvable sous le moteur : rédaction non jouable ici")
        jeton = "ghp" + "_" + "aB3" * 12
        tete = "A" * 84 + " "  # le jeton commence au 86e caractère : le plafond le coupe s'il passe d'abord
        self.git_config("user.name", tete + jeton + " " + "z" * 30)
        self.git_config("user.email", "e" * 150 + "@exemple.invalid")
        acteur, _avis = tasks.acteur_courant(self.r)
        nom, email = acteur["auteur"]["nom"], acteur["auteur"]["email"]
        self.assertNotIn("ghp_", nom)
        self.assertTrue(nom.startswith(tete + "[SECRET"), nom)
        self.assertEqual(tasks.ACTEUR_PLAFOND + len(tasks.ACTEUR_MARQUE), len(nom))
        self.assertTrue(nom.endswith(tasks.ACTEUR_MARQUE))
        self.assertEqual("e" * tasks.ACTEUR_PLAFOND + tasks.ACTEUR_MARQUE, email)
        for cle in ("user.name", "user.email"):
            subprocess.run(["git", "-C", self.r, "config", "--unset", cle], check=True, capture_output=True)
        acteur, _avis = tasks.acteur_courant(self.r)
        self.assertEqual({"nom": None, "email": None}, acteur["auteur"])

    def test_partition_non_nee_copie_stable_hors_v3(self) -> None:
        """V3 ABSENT : la copie est un tirage de 16 hex, STABLE, gardé dans `<partition>.copie` sous
        `CADRE_STATE_DIR` — la partition V3 ne naît pas ; sans `CADRE_STATE_DIR`, une racine jetable
        n'écrit rien dans le vrai état machine. MUTANTS : écrire DANS la partition, la créer, omettre
        `CADRE_STATE_DIR` de la fixture, ou tirer à chaque appel."""
        paths = tasks._acteur_module_cadre("cadre.paths", ("paths.py",))
        if paths is None:
            self.skipTest("cadre.paths introuvable sous le moteur : repli non jouable ici")
        reel = tasks._RESOLVEUR_V3
        sans_v3 = types.SimpleNamespace(
            resoudre=lambda *_a: None,
            dossier_paquet=(reel.dossier_paquet if reel is not None else (lambda *_a: None)))
        with mock.patch.object(tasks, "_RESOLVEUR_V3", sans_v3), \
                mock.patch.object(tasks, "_importer_pont_v3", side_effect=AssertionError("V3 chargé")):
            c1, avis1 = tasks._acteur_copie(self.r)
            c2, avis2 = tasks._acteur_copie(self.r)
            self.assertRegex(c1 or "", r"\A[0-9a-f]{16}\Z", avis1)
            self.assertEqual((c1, None, None), (c2, avis1, avis2))
            partition = Path(paths.state_project(depuis=self.r))
            self.assertTrue(Path(os.path.realpath(partition)).is_relative_to(os.path.realpath(self.etat)),
                            f"partition hors de CADRE_STATE_DIR : {partition}")
            self.assertFalse(partition.exists(), "la partition V3 est née")
            frere = partition.with_name(partition.name + ".copie")
            self.assertEqual(c1, frere.read_text(encoding="utf-8").strip())
            self.assertEqual([frere.name], sorted(p.name for p in partition.parent.iterdir()))
            # Sans `CADRE_STATE_DIR` : l'état machine « par défaut » est redirigé par `XDG_STATE_HOME`
            # vers le temporaire, qu'un mutant qui écrirait ne touche jamais le vrai.
            del os.environ["CADRE_STATE_DIR"]  # rendu par `env.stop`
            os.environ["XDG_STATE_HOME"] = str(self.base / "xdg-etat")  # idem
            vrai = Path(paths.state_project(depuis=self.r))
            vrai_frere = vrai.with_name(vrai.name + ".copie")
            avant = (vrai.exists(), vrai_frere.exists())
            c3, avis3 = tasks._acteur_copie(self.r)
            self.assertIsNone(c3)
            self.assertIn("zone temporaire", avis3 or "")
            self.assertEqual(avant, (vrai.exists(), vrai_frere.exists()), "le vrai état machine a été écrit")

    def test_refus_v3_ne_declenche_pas_le_repli(self) -> None:
        """Un REFUS de V3 (provenance) n'est pas une absence : copie None et avis, aucun fichier de
        repli. MUTANT : traiter `ProvenanceRefusee` comme un V3 absent fait naître `<partition>.copie`."""
        resolveur = tasks._RESOLVEUR_V3
        if resolveur is None or resolveur.resoudre(_KIT_ACTEUR, "agentic_v3") is None:
            self.skipTest("agentic_v3 absent sous le moteur : aucun refus V3 à jouer")
        refus = resolveur.ProvenanceRefusee("agentic_v3 chargé d'un autre arbre (banc)")
        with mock.patch.object(tasks, "_importer_pont_v3", side_effect=refus):
            copie, avis = tasks._acteur_copie(self.r)
        self.assertIsNone(copie)
        self.assertIn("ProvenanceRefusee", avis or "")
        self.assertEqual([], [str(p) for p in self.etat.rglob("*.copie")], "un repli a été tiré")

    def test_acteur_cli_et_copie_absente(self) -> None:
        """CLI réelle, identité ABSENTE : configurations Git coupées, aucune `CADRE_STATE_DIR`, racine
        jetable (l'état machine redirigé par `XDG_STATE_HOME`, jamais le vrai) : `start` et `stage`
        rendent 0, le stage porte un acteur à None, aucune propriété n'est écrite et un avis le DIT.
        MUTANT : rendre l'absence bloquante.
        `HOME` reste le vrai : un domicile sous la zone temporaire la rendrait non jetable."""
        env = _env_identite_isolee(XDG_STATE_HOME=str(self.base / "xdg-etat"),
                                   AGENTS_EVENTS_DIR=str(self.base / "events"))
        env.pop("CADRE_STATE_DIR", None)

        def cli(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-B", str(TASKS_PATH), "--root", self.r, *args],
                                  capture_output=True, text=True, timeout=180, env=env)

        r = cli("new", "sonde d'acteur")
        self.assertEqual(0, r.returncode, r.stderr)
        tid = _id_rendu(r.stdout.strip().splitlines()[0])
        r = cli("start", tid, "--stage", "dev")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("TASKS: acteur — copie", r.stderr)
        r = cli("stage", tid, "review")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        vide = {"auteur": {"nom": None, "email": None}, "copie": None}
        tache = self.tache(tid)
        self.assertNotIn("start_actor", tache, "sans propriétaire ni identité : aucune propriété écrite")
        self.assertEqual(vide, tache["stage_actor"])

    def test_fournee_et_done_portent_acteur_hors_verrou(self) -> None:
        """`done` et `fournee` résolvent l'acteur HORS du verrou du board, une fois par commande, et
        le transmettent : stage du lot refusé en directe (étape 3), `start` du parent et des lots
        (5) (6) ; `--dry-run` ne résout rien. MUTANTS : résoudre sous le verrou, oublier `acteur=`
        à l'une des étapes ou au `done`."""
        from contextlib import redirect_stderr, redirect_stdout

        vus: list[bool] = []

        def faux(_root: str) -> tuple[dict[str, Any], list[str]]:
            vus.append(any(getattr(tasks._BOARD_LOCK_DEPTH, "paths", {}).values()))
            return json.loads(json.dumps(ACTEUR_A)), ["avis de banc"]

        def cli(*args: str) -> tuple[int, str]:
            err = io.StringIO()
            with mock.patch.object(tasks, "acteur_courant", faux), redirect_stderr(err), \
                    redirect_stdout(io.StringIO()):
                rc = tasks.main(["--root", self.r, *args])
            return rc, err.getvalue()

        t = self.nouvelle()
        tasks.set_state(self.r, t, "running", stage="dev")
        rc, err = cli("done", t, "--raison", "fini")
        self.assertEqual(0, rc, err)
        self.assertEqual(([False], ACTEUR_A), (vus, self.tache(t)["stage_actor"]))
        self.assertIn("TASKS: acteur — avis de banc", err)

        for sous in ("gates", "specs", "local/plan"):
            (self.root / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        p = self.nouvelle("parent de fournée")
        plan = self.root / "docs" / "tasks" / "plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text(f"# PLAN — {p}\n\n## Steps\n1. faire — angle mort: banc ?\n\n## Lots\n"
                        "LOT: A | dev-multi | moteur | .agents/bin/tasks_x.py, src/a.py\n"
                        "LOT: B | dev-multi | doc | docs/b.md, docs/c.md\nINTÉGRATION: CHANGELOG.md\n",
                        encoding="utf-8")
        sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        (self.root / ".agents" / "state" / "specs" / "SPECS.json").write_text(json.dumps({"entries": [
            {"id": "S-00000001", "task": p, "kind": "decision", "title": "plan approuvé",
             "text": f"plan=docs/tasks/plan.md sha256={sha}", "files": [], "date": "2026-10-13"}]}),
            encoding="utf-8")
        rc, err = cli("fournee", p, "--dry-run")
        self.assertEqual((0, [False]), (rc, vus), err)

        pv = tasks.fournee_prevol(self.r, p, tasks.load(self.r), **tasks.fournee_sans("", "", ""))
        self.assertEqual([], pv["refus"])
        tasks.fournee_etape_lots(self.r, pv)
        tasks.fournee_etape_writesets(self.r, pv)
        tasks.fournee_etape_direct(self.r, pv, ACTEUR_B)
        lots = tasks.fournee_lots_existants(tasks.load(self.r), p)
        self.assertTrue(lots["A"]["stage"].startswith(tasks.FOURNEE_STAGE_PLANIFIE), lots["A"]["stage"])
        self.assertEqual(ACTEUR_B, lots["A"]["stage_actor"], "étape (3)")

        rc, err = cli("fournee", p)
        self.assertEqual(0, rc, err)
        self.assertEqual([False, False], vus)
        lots = tasks.fournee_lots_existants(tasks.load(self.r), p)
        self.assertEqual(ACTEUR_A, self.tache(p)["start_actor"], "étape (5)")
        for cle, lot in sorted(lots.items()):
            self.assertEqual(("running", ACTEUR_A), (lot["state"], lot.get("start_actor")), f"étape (6), lot {cle}")
        self.assertEqual(ACTEUR_A, lots["A"]["stage_actor"], "étape (6), stage gardé et resigné")

    def test_fournee_reprise_transfere_parent_et_lots(self) -> None:
        """`fournee --reprise` (S-01M5HH8QMC) : la preuve PAR TÂCHE (raison, identifiant confirmé au
        terminal, propriétaire lu APRÈS le drain V3) arrive à `set_state` sous `preuve_reprise` /
        `propriete_attendue`, pour le parent ET chaque lot `running`. Sans preuve : rc 2, rien
        d'écrit. MUTANTS : rétablir `reprise=` vers `set_state` (TypeError), ou ne pas transmettre
        la preuve à un lot ⇒ lot resté à Alice."""
        from contextlib import redirect_stderr, redirect_stdout

        if tasks._acteur_module_cadre("cadre.ledger.redaction", ("ledger", "redaction.py")) is None:
            self.skipTest("cadre.ledger.redaction introuvable sous le moteur : reprise refusée par conception")

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        spec = importlib.util.spec_from_file_location(
            "tracabilite_banc_acteur", Path(__file__).with_name("tracabilite_jira.py"))
        assert spec is not None and spec.loader is not None
        trac = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = trac
        spec.loader.exec_module(trac)
        sans_marqueur = {k: v for k, v in os.environ.items() if k not in trac.AGENT_CALLER_MARKERS}

        def cli(acteur: dict[str, Any], *args: str, entree: str = "") -> tuple[int, str]:
            err = Terminal()
            with mock.patch.object(tasks, "acteur_courant", return_value=(json.loads(json.dumps(acteur)), [])), \
                    mock.patch.dict(os.environ, sans_marqueur, clear=True), \
                    mock.patch.object(tasks.sys, "stdin", Terminal(entree)), \
                    redirect_stderr(err), redirect_stdout(io.StringIO()):
                rc = tasks.main(["--root", self.r, *args])
            return rc, err.getvalue()

        p = self.parent_de_fournee()
        rc, err = cli(ACTEUR_A, "fournee", p)
        self.assertEqual(0, rc, err)
        lots = tasks.fournee_lots_existants(tasks.load(self.r), p)
        self.assertEqual(2, len(lots))
        board = self.root / ".agents" / "state" / "board"

        def instantane() -> dict[str, bytes]:
            return {str(f): f.read_bytes() for f in sorted(board.rglob("*")) if f.is_file()}

        avant = instantane()
        rc, err = cli(ACTEUR_B, "fournee", p)
        self.assertEqual(2, rc, err)
        self.assertIn("REVENDICATION", err)
        rc, err = cli(ACTEUR_B, "fournee", p, "--reprise", "passation", entree="T-mauvais\n")
        self.assertEqual(2, rc, err)
        self.assertIn("identifiant non confirmé", err)
        self.assertEqual(avant, instantane(), "sans preuve valide, rien n'est écrit")

        rc, err = cli(ACTEUR_B, "fournee", p, "--reprise", "passation\x1b[31m", entree=p + "\n")
        self.assertEqual(0, rc, err)
        self.assertNotIn("TypeError", err)
        self.assertEqual(ACTEUR_B, self.tache(p)["start_actor"], "parent transféré")
        self.assertIn("[REPRISE : passation [31m]", self.tache(p)["stage"], "raison sans contrôle")
        for cle, lot in sorted(tasks.fournee_lots_existants(tasks.load(self.r), p).items()):
            self.assertEqual(("running", ACTEUR_B), (lot["state"], lot.get("start_actor")), f"lot {cle}")

    def test_fournee_revalide_la_propriete_sous_verrou(self) -> None:
        """Le propriétaire lu après le drain V3 est REVALIDÉ sous le verrou de la fournée, comme au
        `start` : une prise d'Alice posée entre le précontrôle et le verrou refuse Bob, rc 2.
        MUTANT : ne pas transmettre `proprietes_attendues` ⇒ Bob démarre une tâche d'Alice."""
        from contextlib import redirect_stderr, redirect_stdout

        p = self.parent_de_fournee()
        vrai_prevol = tasks.fournee_prevol

        def prise_concurrente(root: str, tid: str, data: dict[str, Any], **sans: str) -> dict[str, Any]:
            courant = tasks.load(root)
            tasks.find(courant, p)["start_actor"] = json.loads(json.dumps(ACTEUR_A))
            tasks.save(root, courant)
            return vrai_prevol(root, tid, tasks.load(root), **sans)

        err = io.StringIO()
        with mock.patch.object(tasks, "acteur_courant", return_value=(json.loads(json.dumps(ACTEUR_B)), [])), \
                mock.patch.object(tasks, "fournee_prevol", prise_concurrente), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = tasks.main(["--root", self.r, "fournee", p])
        self.assertEqual(2, rc, err.getvalue())
        self.assertIn(f"REVENDICATION: propriété de {p} changée depuis le précontrôle", err.getvalue())
        self.assertEqual((ACTEUR_A, "pending"), (self.tache(p)["start_actor"], self.tache(p)["state"]))

    def test_raison_de_reprise_nettoyee_caviardee_bornee(self) -> None:
        """La raison écrite au stage : contrôles retirés, caviardée PUIS plafonnée ; vide une fois
        nettoyée ou rédaction absente : refus. MUTANTS : garder les contrôles, tronquer avant de
        caviarder (le jeton coupé fuit), retirer le plafond, écrire sans rédaction."""
        if tasks._acteur_module_cadre("cadre.ledger.redaction", ("ledger", "redaction.py")) is None:
            self.skipTest("cadre.ledger.redaction introuvable sous le moteur : rédaction non jouable ici")
        jeton = "ghp" + "_" + "aB3" * 12
        tete = "A" * 190 + " "  # le jeton franchit le plafond : le couper d'abord le rendrait méconnaissable
        raison = tasks.raison_reprise_propre(tete + jeton + "\x07‮" + "z" * 40)
        self.assertNotIn("ghp_", raison)
        self.assertTrue(raison.startswith(tete + "[SECRET"), raison)
        self.assertEqual(tasks.RAISON_REPRISE_PLAFOND + len(tasks.ACTEUR_MARQUE), len(raison))
        self.assertEqual("a b", tasks.raison_reprise_propre("a\x1b\nb"))
        with self.assertRaises(tasks.BoardError):
            tasks.raison_reprise_propre("\x00\x1b\t")
        with mock.patch.object(tasks, "_acteur_module_cadre", return_value=None), \
                self.assertRaises(tasks.BoardError) as cm:
            tasks.raison_reprise_propre("passation")
        self.assertIn("rédaction indisponible", str(cm.exception))

    def parent_de_fournee(self) -> str:
        """Un parent au plan approuvé de deux lots (A, B), prêt pour `fournee`."""
        for sous in ("gates", "specs", "local/plan"):
            (self.root / ".agents" / "state" / sous).mkdir(parents=True, exist_ok=True)
        p = self.nouvelle("parent de fournée")
        plan = self.root / "docs" / "tasks" / "plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text(f"# PLAN — {p}\n\n## Steps\n1. faire — angle mort: banc ?\n\n## Lots\n"
                        "LOT: A | dev-multi | moteur | src/a.py, src/b.py\n"
                        "LOT: B | dev-multi | doc | docs/b.md, docs/c.md\nINTÉGRATION: CHANGELOG.md\n",
                        encoding="utf-8")
        sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        (self.root / ".agents" / "state" / "specs" / "SPECS.json").write_text(json.dumps({"entries": [
            {"id": "S-00000001", "task": p, "kind": "decision", "title": "plan approuvé",
             "text": f"plan=docs/tasks/plan.md sha256={sha}", "files": [], "date": "2026-10-13"}]}),
            encoding="utf-8")
        return p

    def test_acteur_voyage_chez_adoptant(self) -> None:
        """Le canal template : un projet INSTALLÉ avec ce qui voyage (`.template-exclude` appliqué au
        moteur, à `agentic_v3` et à `cadre`) signe `start` puis `stage` de son auteur Git et d'une copie
        de 16 hex. MUTANTS : un fichier moteur exclu du template, ou l'acteur perdu au `start`/`stage`."""
        exclusions = _KIT_ACTEUR / ".template-exclude"
        regle = _KIT_ACTEUR / ".agents" / "bin" / "sync_template.py"
        if not ((_KIT_ACTEUR / ".agents" / "IS_THE_KIT").is_file() and exclusions.is_file() and regle.is_file()):
            self.skipTest("hors du kit : le canal template (.template-exclude, sync_template.py) ne voyage "
                          "pas — le voyage de l'acteur se juge dans le kit")
        spec = importlib.util.spec_from_file_location("_sync_template_banc_acteur", regle)
        st = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = st  # ses dataclasses relisent leur module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(st)
        regles = st.parse_exclude(exclusions.read_text(encoding="utf-8"))
        suivis = subprocess.run(
            ["git", "-C", str(_KIT_ACTEUR), "ls-files", "-z", "--", ".agents/bin", "agentic_v3",
             ".agents/vendor", "src/cadre"], check=True, capture_output=True).stdout.decode("utf-8")
        projet = self.base / "adoptant"
        for rel in filter(None, suivis.split("\0")):
            source = _KIT_ACTEUR / rel
            regle_rel = st.match_rule(rel, regles)
            if Path(rel).name.startswith("test_") or not source.is_file() or (
                    regle_rel is not None and regle_rel.polarity == "strip"):
                continue
            (projet / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, projet / rel)
        moteur = projet / ".agents" / "bin" / "tasks.py"
        self.assertTrue(moteur.is_file(), "le moteur du board ne voyage pas")
        subprocess.run(["git", "init", "-q", str(projet)], check=True, capture_output=True,
                       env=_env_identite_isolee())
        for cle, valeur in (("user.name", "Adoptante"), ("user.email", "adoptante@exemple.invalid")):
            subprocess.run(["git", "-C", str(projet), "config", cle, valeur], check=True, capture_output=True)
        maison = self.base / "maison-adoptant"
        maison.mkdir()
        env = _env_identite_isolee(CADRE_STATE_DIR=str(self.base / "etat-adoptant"), HOME=str(maison),
                                   AGENTS_EVENTS_DIR=str(self.base / "events-adoptant"))

        def cli(*args: str) -> subprocess.CompletedProcess:
            r = subprocess.run([sys.executable, "-B", str(moteur), "--root", str(projet), *args],
                               capture_output=True, text=True, timeout=180, env=env)
            self.assertEqual(0, r.returncode, f"{args} : {r.stdout}{r.stderr}")
            return r

        tid = _id_rendu(cli("new", "sonde adoptant").stdout.strip().splitlines()[0])
        cli("start", tid, "--stage", "dev")
        cli("stage", tid, "review")
        tache = tasks.find(tasks.load(str(projet)), tid)
        auteur = {"nom": "Adoptante", "email": "adoptante@exemple.invalid"}
        self.assertEqual((auteur, auteur), (tache["start_actor"]["auteur"], tache["stage_actor"]["auteur"]))
        self.assertRegex(tache["start_actor"]["copie"] or "", r"\A[0-9a-f]{16}\Z")
        self.assertEqual(tache["start_actor"]["copie"], tache["stage_actor"]["copie"])
        # V3 voyage : la copie EST celle de V3 (`<state_project>/run/copie`, celle de `runs/<auteur>/<copie>`),
        # jamais un tirage de repli. MUTANT : la branche V3 remplacée par le repli.
        projets = self.base / "etat-adoptant" / "projets"
        copies_v3 = sorted(projets.glob("*/run/copie"))
        self.assertEqual(1, len(copies_v3), copies_v3)
        self.assertEqual(copies_v3[0].read_text(encoding="utf-8").strip(), tache["start_actor"]["copie"])
        self.assertEqual([], sorted(p.name for p in projets.glob("*.copie")), "un tirage de repli est né")

    def sans_v3(self) -> types.SimpleNamespace:
        """Un résolveur qui ne trouve pas `agentic_v3`, mais trouve encore `cadre` : la branche de repli."""
        reel = tasks._RESOLVEUR_V3
        return types.SimpleNamespace(
            resoudre=lambda *_a: None,
            dossier_paquet=(reel.dossier_paquet if reel is not None else (lambda *_a: None)))

    def test_copie_de_repli_illisible_n_est_ni_ecrite_ni_reecrite(self) -> None:
        """Un `<partition>.copie` qui n'est pas 16 hex n'atteint pas le board et n'est pas écrasé :
        copie None, avis « copie illisible ». MUTANT : la validation `fullmatch` retirée."""
        paths = tasks._acteur_module_cadre("cadre.paths", ("paths.py",))
        if paths is None:
            self.skipTest("cadre.paths introuvable sous le moteur : repli non jouable ici")
        partition = Path(paths.state_project(depuis=self.r))
        frere = partition.with_name(partition.name + ".copie")
        frere.parent.mkdir(parents=True, exist_ok=True)
        frere.write_text("pas une copie\n", encoding="utf-8")
        with mock.patch.object(tasks, "_RESOLVEUR_V3", self.sans_v3()):
            copie, avis = tasks._acteur_copie(self.r)
        self.assertIsNone(copie)
        self.assertIn("copie illisible", avis or "")
        self.assertEqual("pas une copie\n", frere.read_text(encoding="utf-8"))

    def test_copie_lue_ne_suit_ni_lien_ni_fifo_et_borne_sa_lecture(self) -> None:
        """Avis de sécurité 2 : `_acteur_copie_lue` ne suit pas un lien symbolique, n'attend pas sur un
        FIFO et refuse un fichier de plus de `ACTEUR_COPIE_OCTETS` octets. MUTANTS : `O_NOFOLLOW`,
        `O_NONBLOCK` ou la borne retirés."""
        bon = "0123456789abcdef"
        cible = self.base / "cible"
        cible.write_text(bon + "\n", encoding="utf-8")
        self.assertEqual(bon, tasks._acteur_copie_lue(cible), "témoin de lecture nominale")
        if hasattr(os, "O_NOFOLLOW"):  # POSIX seul : sous Windows, le lien est suivi (docstring)
            lien = self.base / "lien.copie"
            lien.symlink_to(cible)
            self.assertIsNone(tasks._acteur_copie_lue(lien), "lien symbolique suivi")
        gros = self.base / "gros.copie"
        gros.write_text(bon + "\n" + " " * tasks.ACTEUR_COPIE_OCTETS, encoding="utf-8")
        self.assertIsNone(tasks._acteur_copie_lue(gros), "lecture non bornée")
        if not hasattr(os, "mkfifo"):
            return
        fifo = self.base / "fifo.copie"
        os.mkfifo(fifo)
        rendu: list[Any] = []
        lecteur = threading.Thread(target=lambda: rendu.append(tasks._acteur_copie_lue(fifo)), daemon=True)
        lecteur.start()
        lecteur.join(timeout=5)
        if lecteur.is_alive():  # débloque le lecteur avant d'échouer
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
            lecteur.join(timeout=5)
            self.fail("lecture bloquée sur un FIFO")
        self.assertEqual([None], rendu)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO POSIX")
    def test_copie_lue_refuse_un_fifo_nourri(self) -> None:
        """Revue de clôture FK3X (C4) : un FIFO qu'un écrivain tient ouvert, nourri de 16 hex, n'est
        PAS lu comme un tirage — seul un fichier ordinaire l'est. MUTANT : le contrôle `S_ISREG` retiré."""
        fifo = self.base / "plein.copie"
        os.mkfifo(fifo)
        fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)  # un écrivain tient le FIFO, 16 hex en attente
        try:
            os.write(fd, b"0123456789abcdef\n")
            self.assertIsNone(tasks._acteur_copie_lue(fifo), "FIFO lu comme un fichier ordinaire")
        finally:
            os.close(fd)

    def test_copie_v3_non_conforme_n_est_pas_ecrite(self) -> None:
        """Avis de sécurité 1 : la copie rendue par V3 est validée comme le repli (16 hex), sinon None et
        avis. MUTANT : la validation de la branche V3 retirée."""
        resolveur = tasks._RESOLVEUR_V3
        if resolveur is None or resolveur.resoudre(_KIT_ACTEUR, "agentic_v3") is None:
            self.skipTest("agentic_v3 absent sous le moteur : branche V3 non jouable ici")
        from agentic_v3.db import run_export

        with mock.patch.object(run_export, "identifiant_de_copie", return_value="../pas-une-copie"):
            copie, avis = tasks._acteur_copie(self.r)
        self.assertIsNone(copie)
        self.assertIn("non conforme", avis or "")

    def test_panne_imprevue_de_l_acteur_n_est_jamais_un_refus(self) -> None:
        """Une exception imprévue de la résolution ne refuse pas le `start` : acteur vide, sans propriété, avis.
        MUTANT : le `try/except` d'`acteur_de_la_commande` retiré."""
        from contextlib import redirect_stderr, redirect_stdout

        t = self.nouvelle()
        err = io.StringIO()
        with mock.patch.object(tasks, "acteur_courant", side_effect=RuntimeError("panne de banc")), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = tasks.main(["--root", self.r, "start", t, "--stage", "dev"])
        self.assertEqual(0, rc, err.getvalue())
        vide = {"auteur": {"nom": None, "email": None}, "copie": None}
        self.assertNotIn("start_actor", self.tache(t), "acteur vide : aucune propriété écrite")
        self.assertEqual(vide, self.tache(t)["stage_actor"])
        self.assertIn("TASKS: acteur — acteur indisponible (RuntimeError)", err.getvalue())

    def test_proprietaire_lu_apres_le_drain_v3(self) -> None:
        """Le rejeu V3 pose Alice propriétaire d'une tâche sans propriétaire ; Bob la démarre : refus
        NOMMÉ « appartient à un autre pilote », car `ancien` est lu sur le board REJOUÉ (contrat W4).
        MUTANT : lire `ancien` avant `_replay_v3` ⇒ « changée depuis le précontrôle »."""
        from contextlib import redirect_stderr, redirect_stdout

        t = self.nouvelle()

        def rejeu(root: Any, *, pont_commande: Any = None) -> int:
            data = tasks.load(root)
            tasks.find(data, t)["start_actor"] = dict(ACTEUR_A)
            tasks.save(root, data)
            return 0

        err = io.StringIO()
        with mock.patch.object(tasks, "replay_sync", rejeu), \
                mock.patch.object(tasks, "acteur_courant", return_value=(dict(ACTEUR_B), [])), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = tasks.main(["--root", self.r, "start", t, "--stage", "dev"])
        self.assertEqual(2, rc, err.getvalue())
        self.assertIn(f"REVENDICATION: {t} appartient à un autre pilote", err.getvalue())
        self.assertEqual((ACTEUR_A, "pending"), (self.tache(t)["start_actor"], self.tache(t)["state"]))


SITE_JIRA = "https://jira.exemple.invalid"


class FusionProprieteTests(unittest.TestCase):
    """LOT D de T-01M5G7RTQ9RY3WGZ8T9W6ZX9RS — la propriété (`start_actor`) et son intention Jira
    (`jira_claim_*`) fusionnent comme UN ensemble (`fusion_enregistrement.cles_propriete`). Les côtés
    sont écrits par les VRAIS producteurs : `set_state` + `jira_prepare_claim` (prise, transfert),
    `jira_claim_retry` derrière un faux `PUT` 204 (accusé). Seul le geste de transfert du lot A
    (`start_actor` réécrit sous verrou) est rejoué à la main, suivi de son `jira_prepare_claim` réel.
    MUTANTS tués : le jugement de `cles_propriete` retiré de `_juger_acteurs` (intention panachée
    fusionnée), un `Conflit` au lieu de `ConflitActeur` (la chimère reste dans %A), le préfixe
    `jira_claim_` hors du groupe."""

    setUp = ActeurBoardTests.setUp
    nouvelle = ActeurBoardTests.nouvelle
    tache = ActeurBoardTests.tache

    @classmethod
    def setUpClass(cls) -> None:
        chemin = Path(__file__).with_name("fusion_enregistrement.py")
        spec = importlib.util.spec_from_file_location("fusion_propriete_banc", chemin)
        assert spec is not None and spec.loader is not None
        cls.P = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.P
        spec.loader.exec_module(cls.P)

    def socle(self) -> tuple[str, dict[str, Any]]:
        """Une tâche Jira prise par Alice, intention en attente : la BASE commune des deux clones."""
        os.environ.pop("JIRA_AGENT_CLAIM", None)  # rendu par `env.stop` de setUp
        tid = self.nouvelle("tâche Jira")
        with tasks.board_lock(self.r):
            data = tasks.load(self.r)
            tasks.find(data, tid).update(jira_site=SITE_JIRA, jira_key="GNTC-7")
            tasks.save(self.r, data)
        tasks.set_state(self.r, tid, "running", stage="dev", acteur=ACTEUR_A)
        base = self.tache(tid)
        self.assertEqual(("attente", ACTEUR_A), (base["jira_claim_status"], base["jira_claim_actor"]))
        return tid, base

    def accuse(self, tid: str) -> dict[str, Any]:
        """L'accusé RÉEL de `jira_claim_retry` (PUT simulé 204) sur le board : le côté de l'ancien pilote."""
        with mock.patch.object(tasks, "_jira_config", return_value=(SITE_JIRA, False, "jeton")), \
                mock.patch.object(tasks, "jira_request", return_value=(204, b"")):
            self.assertIn("acquittee", tasks.jira_claim_retry(self.r, tid))
        return self.tache(tid)

    @staticmethod
    def transfert(base: dict[str, Any], acteur: dict[str, Any]) -> dict[str, Any]:
        """Le transfert du lot A (`start_actor` réécrit) suivi de son `jira_prepare_claim` réel."""
        cote = json.loads(json.dumps(base))
        cote["start_actor"] = json.loads(json.dumps(acteur))
        tasks.jira_prepare_claim(cote, acteur)
        return cote

    @staticmethod
    def env(tid: str, record: dict[str, Any]) -> dict[str, Any]:
        return {"format": 1, "id": tid, "record": record, "sync_operations": []}

    def conflit(self, tid: str, base: dict, nous: dict, eux: dict) -> str:
        with self.assertRaises(self.P.ConflitActeur) as cm:
            self.P.fusionner(self.env(tid, base), self.env(tid, nous), self.env(tid, eux))
        return str(cm.exception)

    def test_transfert_contre_accuse_de_l_ancien_pilote_conflit_jamais_panache(self) -> None:
        """Transfert vers Bob ici, accusé d'Alice là : champ par champ, ce serait le label de Bob
        marqué `acquitte` sans PUT (et `jira_claim_after_start` dirait la prise acquittée). Conflit
        NOMMÉ, dans les deux sens, les deux pilotes cités."""
        tid, base = self.socle()
        bob, alice_acquitte = self.transfert(base, ACTEUR_B), self.accuse(tid)
        self.assertNotEqual(bob["jira_claim_label"], alice_acquitte["jira_claim_acquitte"])
        for nous, eux in ((bob, alice_acquitte), (alice_acquitte, bob)):
            with self.subTest(transfert_ici=nous is bob):
                message = self.conflit(tid, base, nous, eux)
                self.assertTrue(message.startswith(
                    "record/start_actor+jira_claim_* (propriété et intention Jira changées des deux côtés : "),
                    message)
                for nom in ("Alice <alice@exemple.invalid>", "Bob <bob@exemple.invalid>", "acquitte"):
                    self.assertIn(nom, message)

    def test_transferts_concurrents_et_acquittement_seul_conflit_explicite(self) -> None:
        """Deux transferts (Bob ici, Xavier là) : « double démarrage », nommé AVANT l'intention. Même
        pilote des deux côtés, intentions différentes (une acquittée, l'autre non) : l'ensemble
        conflicte, jamais l'acteur commun avec l'accusé d'un seul clone."""
        tid, base = self.socle()
        xavier = {"auteur": {"nom": "Xavier", "email": "xavier@exemple.invalid"}, "copie": "c0c0c0c0c0c0c0c0"}
        message = self.conflit(tid, base, self.transfert(base, ACTEUR_B), self.transfert(base, xavier))
        self.assertTrue(message.startswith("record/start_actor (double démarrage : "), message)
        bob = self.transfert(base, ACTEUR_B)
        bob_acquitte = dict(bob, jira_claim_status="acquitte", jira_claim_acquitte=bob["jira_claim_label"])
        self.assertIn("propriété et intention Jira", self.conflit(tid, base, bob, dict(bob_acquitte, owner="o")))

    def test_un_seul_cote_pris_entier_sans_faux_conflit(self) -> None:
        """POLARITÉ : transfert d'un côté et un champ voisin de l'autre ⇒ l'ensemble du transfert,
        le voisin compris ; accusé d'un côté seul ⇒ pris entier."""
        tid, base = self.socle()
        bob = self.transfert(base, ACTEUR_B)
        res = self.P.fusionner(self.env(tid, base), self.env(tid, bob), self.env(tid, dict(base, owner="o")))
        self.assertEqual(dict(bob, owner="o"), res["record"])
        alice = self.accuse(tid)
        res = self.P.fusionner(self.env(tid, base), self.env(tid, dict(base, owner="o")), self.env(tid, alice))
        self.assertEqual(dict(alice, owner="o"), res["record"])

    def test_reprise_levee_du_meme_ensemble_que_la_propriete(self) -> None:
        """`reprise_levee` (prises levées par la reprise qui a posé `start_actor`) est de l'ensemble :
        même pilote des deux côtés, levées différentes ⇒ `ConflitActeur` nommé, jamais une levée
        d'une reprise collée au pilote d'une autre ; un seul côté ⇒ pris entier.
        MUTANT : `reprise_levee` hors de `cles_propriete` ⇒ conflit générique, pas `ConflitActeur`."""
        tid, base = self.socle()
        alice = {"nom": "Alice", "email": "alice@exemple.invalid"}
        ici = dict(self.transfert(base, ACTEUR_B), reprise_levee=[{"auteur": alice, "transition": "a" * 40}])
        la = dict(self.transfert(base, ACTEUR_B), reprise_levee=[{"auteur": alice, "transition": "b" * 40}])
        message = self.conflit(tid, base, ici, la)
        self.assertTrue(message.startswith("record/start_actor+jira_claim_* (propriété et intention Jira "), message)
        self.assertIn("reprise_levee=", message)
        res = self.P.fusionner(self.env(tid, base), self.env(tid, ici), self.env(tid, dict(base, owner="o")))
        self.assertEqual(dict(ici, owner="o"), res["record"])

    def test_canal_main_fusion_texte_propre_remet_nous(self) -> None:
        """Canal réel `main` : merge-file simulé PROPRE (rc 0) qui écrit la chimère « acteur de Bob,
        accusé d'Alice » ⇒ rc 3 et %A remis à « nous » ENTIER, stderr nomme l'ensemble."""
        tid, base = self.socle()
        bob, alice = self.transfert(base, ACTEUR_B), self.accuse(tid)
        chimere = dict(bob, jira_claim_status="acquitte", jira_claim_acquitte=alice["jira_claim_acquitte"])
        d = self.base / "fusion"
        d.mkdir()
        chemins = []
        for nom, record in (("O", base), ("A", bob), ("B", alice)):
            (d / nom).write_bytes(self.P.canonique(self.env(tid, record)))
            chemins.append(str(d / nom))

        def merge_file_propre(argv: list[str], **_: Any) -> subprocess.CompletedProcess:
            Path(argv[-3]).write_bytes(self.P.canonique(self.env(tid, chimere)))
            return subprocess.CompletedProcess(argv, 0)

        err = io.StringIO()
        with mock.patch.object(self.P.subprocess, "run", side_effect=merge_file_propre), \
                mock.patch("sys.stderr", err):
            rc = self.P.main(["fusion_enregistrement.py", *chemins, "7", "S", "X", "Y"])
        self.assertEqual(3, rc, err.getvalue())
        self.assertEqual(self.P.canonique(self.env(tid, bob)), (d / "A").read_bytes(), "chimère restée dans %A")
        self.assertIn("conflit sur record/start_actor+jira_claim_*", err.getvalue())


if __name__ == "__main__":
    unittest.main()
