#!/usr/bin/env python3
"""Témoin du verbe `tasks.py chrono` (T-01M5HST80E30DFMV3S7WM68Q7N, lot B), par la CLI RÉELLE en
sous-processus : (1) un id inconnu, pour chacune des quatre actions, et un `--lot` inconnu rendent
rc 2 `tasks.py: unknown task id` ; (2) depuis un worktree LIÉ, un lot créé au board commun APRÈS la
branche du worktree est vu : `step` rc 0, la ligne est écrite sous la racine COMMUNE, jamais dans le
worktree — `CLAUDE_PROJECT_DIR` absent, puis égal au principal. Mutants qui le rougissent : valider
au board de `--root` au lieu de la racine commune ; valider à la forme seule (sans load + find).
Environnement en liste blanche, HOME, état et événements jetables, git sans config globale."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent
TASKS_PY = ICI / "tasks.py"
INCONNU = "T-99999999"
LISTE_BLANCHE = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT", "WINDIR", "PATHEXT")
GIT = shutil.which("git")


class Banc(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="tasks-chrono-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        maison = self.base / "maison"
        maison.mkdir()
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@example.com\n", encoding="utf-8")
        self.env = {k: os.environ[k] for k in LISTE_BLANCHE if k in os.environ}
        self.env.update(HOME=str(maison), USERPROFILE=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(self.base),
                        CADRE_STATE_DIR=str(self.base / "etat"), AGENTS_EVENTS_DIR=str(self.base / "evenements"),
                        PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

    def tasks(self, cwd: Path, *argv: str, root: Path | None = None, env: dict | None = None):
        tete = ["--root", str(root)] if root is not None else []
        return subprocess.run([sys.executable, "-B", str(TASKS_PY), *tete, *argv], cwd=str(cwd),
                              env=env or self.env, capture_output=True, text=True, encoding="utf-8",
                              timeout=120, check=False)

    def nouvelle(self, racine: Path, titre: str) -> str:
        r = self.tasks(racine, "new", titre, "--pas-un-defaut", "banc", root=racine,
                       env=dict(self.env, CADRE_PROJECT_ROOT=str(racine)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return next(m for m in r.stdout.split() if m.startswith("T-"))

    def git(self, racine: Path, *args: str) -> None:
        r = subprocess.run(["git", *args], cwd=str(racine), env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)


class IdInconnu(Banc):
    def test_quatre_actions_et_lot_inconnus_rc2(self):
        racine = self.base / "r"
        racine.mkdir()
        connu = self.nouvelle(racine, "connue")
        argvs = {"estimate": ["--etape", "dev"], "begin": [], "step": ["--etape", "dev", "--phase", "begin"],
                 "show": []}
        for action, opts in argvs.items():
            with self.subTest(action=action):
                r = self.tasks(racine, "chrono", INCONNU, action, *opts, root=racine)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertRegex(r.stderr, rf"(?m)^tasks\.py: unknown task id: {INCONNU}")
        r = self.tasks(racine, "chrono", connu, "step", "--etape", "dev", "--phase", "begin", "--lot", INCONNU,
                       root=racine)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(f"unknown task id: {INCONNU}", r.stderr)
        self.assertFalse((racine / ".agents" / "state" / "local" / "task-chrono").exists(), "un refus n'écrit rien")
        r = self.tasks(racine, "chrono", connu, "step", "--etape", "dev", "--phase", "begin", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)


class FormeDeLot(Banc):
    """M4 de la passe de correction : `chrono <lot> …` d'un lot de fournée joue au journal du PARENT,
    clé `lot` ; le `done` du parent clôt le cycle, qui nourrit l'historique de la taille du lot.
    MUTANT qui le rougit : la redirection retirée de `chrono_verbe` (le lot écrit son propre journal)."""

    def test_lot_de_fournee_ecrit_au_parent_et_nourrit_l_historique(self):
        racine = self.base / "r"
        racine.mkdir()
        parent = self.nouvelle(racine, "parent")
        lot = self.nouvelle(racine, "lot")
        self.assertEqual(self.tasks(racine, "writeset", lot, "a.py", root=racine).returncode, 0)
        board = racine / ".agents" / "state" / "board" / "TASKS.json"
        donnees = json.loads(board.read_text(encoding="utf-8"))
        next(t for t in donnees["tasks"] if t["id"] == lot)["fournee"] = {"parent": parent, "lot": "A"}
        board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        for argv in (("begin",), ("estimate", "--etape", "dev"), ("step", "--etape", "dev", "--phase", "begin"),
                     ("step", "--etape", "dev", "--phase", "end"), ("show",)):
            r = self.tasks(racine, "chrono", lot, *argv, root=racine)
            self.assertEqual(r.returncode, 0, (argv, r.stderr))
        self.assertIn(lot[-8:], r.stdout, "show du lot = cycle du parent, ligne du lot")
        dossier = racine / ".agents" / "state" / "local" / "task-chrono"
        self.assertEqual(sorted(p.stem for p in dossier.glob("*.jsonl")), [parent], "aucun journal propre au lot")
        lignes = [json.loads(l) for l in (dossier / f"{parent}.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l.get("lot") for l in lignes if l["ev"] == "etape"], [lot, lot])
        for phase in ("begin", "end"):
            self.assertEqual(self.tasks(racine, "chrono", parent, "step", "--etape", "done", "--phase", phase,
                                        root=racine).returncode, 0)
        r = self.tasks(racine, "chrono", lot, "estimate", "--etape", "dev", root=racine)
        self.assertIn("historique, n=1", r.stdout, r.stderr)


class JalonDuParent(Banc):
    """F1 de la clôture : le jalon `done` se joue sur le PARENT seul. `chrono <lot> step --etape done`
    rend rc 2 sans rien écrire, et le cycle du parent reste OUVERT (une étape suivante du parent reste au
    cycle 1) ; une ligne `done` de lot déjà au journal ne le clôt pas non plus.
    MUTANTS qui le rougissent : le refus du jalon sous `--lot` retiré de `etape()` ; la condition
    `lot is None` retirée de `est_clos`."""

    def fournee(self, racine: Path) -> tuple[str, str]:
        parent = self.nouvelle(racine, "parent")
        lot = self.nouvelle(racine, "lot")
        board = racine / ".agents" / "state" / "board" / "TASKS.json"
        donnees = json.loads(board.read_text(encoding="utf-8"))
        next(t for t in donnees["tasks"] if t["id"] == lot)["fournee"] = {"parent": parent, "lot": "A"}
        board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        return parent, lot

    def test_done_sous_un_lot_refuse_et_le_cycle_du_parent_reste_ouvert(self):
        racine = self.base / "r"
        racine.mkdir()
        parent, lot = self.fournee(racine)
        for argv in (("begin",), ("step", "--etape", "dev", "--phase", "begin"),
                     ("step", "--etape", "dev", "--phase", "end")):
            self.assertEqual(self.tasks(racine, "chrono", lot, *argv, root=racine).returncode, 0, argv)
        journal = racine / ".agents" / "state" / "local" / "task-chrono" / f"{parent}.jsonl"
        avant = journal.read_text(encoding="utf-8")
        for phase in ("begin", "end"):
            r = self.tasks(racine, "chrono", lot, "step", "--etape", "done", "--phase", phase, root=racine)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("PARENT seul", r.stderr)
        self.assertEqual(journal.read_text(encoding="utf-8"), avant, "un refus n'écrit rien")
        r = self.tasks(racine, "chrono", parent, "step", "--etape", "porte", "--phase", "begin", root=racine)
        self.assertIn("cycle 1 porte", r.stdout, r.stderr)
        b = json.loads(self.tasks(racine, "chrono", parent, "show", "--json", root=racine).stdout)
        self.assertEqual((b["cycle"], b["clos"]), (1, False))

    def test_ligne_done_de_lot_au_journal_ne_clot_pas_le_cycle(self):
        racine = self.base / "r"
        racine.mkdir()
        parent, lot = self.fournee(racine)
        self.assertEqual(self.tasks(racine, "chrono", parent, "begin", root=racine).returncode, 0)
        journal = racine / ".agents" / "state" / "local" / "task-chrono" / f"{parent}.jsonl"
        ts = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])["ts"]
        with journal.open("a", encoding="utf-8") as f:
            for phase in ("begin", "end"):
                f.write(json.dumps({"ev": "etape", "tid": parent, "cycle": 1, "etape": "done", "lot": lot,
                                    "tentative": 1, "phase": phase, "ts": ts, "taille": None,
                                    "estimation": {"source": "jalon", "n": 0}}) + "\n")
        b = json.loads(self.tasks(racine, "chrono", parent, "show", "--json", root=racine).stdout)
        self.assertEqual((b["cycle"], b["clos"]), (1, False))
        r = self.tasks(racine, "chrono", parent, "begin", root=racine)
        self.assertNotIn("cycle 2", r.stdout, "le begin reprend le cycle 1, il n'en ouvre pas un second")


class TrouDOuverture(Banc):
    """F2 de la clôture : plus de 60 s entre l'ouverture du cycle et sa première étape sont DITS dans
    `incomplet`, et l'écart total n'est pas rendu. MUTANT qui le rougit : le contrôle retiré de `bilan`
    (ou son seuil porté au-delà de trois heures)."""

    def journal(self, racine: Path, tid: str, decalage_s: int) -> None:
        chemin = racine / ".agents" / "state" / "local" / "task-chrono" / f"{tid}.jsonl"
        chemin.parent.mkdir(parents=True)
        t0 = 1_000_000
        lignes = [{"ev": "cycle", "tid": tid, "cycle": 1, "ts": t0}]
        for etape, debut in (("dev", t0 + decalage_s * 1000), ("done", t0 + decalage_s * 1000 + 60_000)):
            for phase, ts in (("begin", debut), ("end", debut + (0 if etape == "done" else 60_000))):
                lignes.append({"ev": "etape", "tid": tid, "cycle": 1, "etape": etape, "lot": None, "tentative": 1,
                               "phase": phase, "ts": ts, "taille": None,
                               "estimation": {"source": "historique", "n": 1, "mediane_s": 60, "p90_s": 60}})
        chemin.write_text("".join(json.dumps(l) + "\n" for l in lignes), encoding="utf-8")

    def test_trois_heures_avant_la_premiere_etape_dites_non_relevees(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.journal(racine, tid, 3 * 3600)
        b = json.loads(self.tasks(racine, "chrono", tid, "show", "--json", root=racine).stdout)
        trou = [i for i in b["incomplet"] if "entre l'ouverture du cycle et la première étape, non relevés" in i]
        self.assertEqual(len(trou), 1, b["incomplet"])
        self.assertTrue(trou[0].startswith("3"), trou)
        self.assertNotIn("ecart_s", b["total"])

    def test_soixante_secondes_ne_sont_pas_un_trou(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.journal(racine, tid, 60)
        b = json.loads(self.tasks(racine, "chrono", tid, "show", "--json", root=racine).stdout)
        self.assertFalse([i for i in b["incomplet"] if "première étape" in i], b["incomplet"])
        self.assertIn("ecart_s", b["total"])


def charger_tasks():
    """Le module `tasks` du bin, chargé sous un nom propre au banc (appels en processus)."""
    nom = "_banc_tasks_chrono_tasks"
    if nom not in sys.modules:
        spec = importlib.util.spec_from_file_location(nom, TASKS_PY)
        module = importlib.util.module_from_spec(spec)
        sys.modules[nom] = module
        spec.loader.exec_module(module)
    return sys.modules[nom]


class JalonsParLesVerbes(Banc):
    """T-01M5KKFBCXXEVYR8GJPYFEH3C8 lot A, par la CLI RÉELLE : `start` ouvre le cycle et le dev, `done`
    pose le jalon et DIT l'étape restée sans fin, `--statusline` montre l'étape ouverte AVANT le détail ;
    le stdout du verbe n'a jamais une ligne CHRONO (W1, W3, W6 de bout en bout)."""

    def journal(self, racine: Path, tid: str) -> Path:
        return racine / ".agents" / "state" / "local" / "task-chrono" / f"{tid}.jsonl"

    def test_start_puis_done_relevent_le_cycle_sur_stderr_seul(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        r = self.tasks(racine, "start", tid, "--stage", "dev-mono", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("CHRONO", r.stdout + r.stderr, "un start qui relève ne dit rien")
        lignes = [json.loads(l) for l in self.journal(racine, tid).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(l["ev"], l.get("etape"), l.get("phase")) for l in lignes],
                         [("cycle", None, None), ("etape", "dev", "begin")])
        sl = self.tasks(racine, "--statusline", root=racine).stdout.rstrip("\n")
        self.assertRegex(sl, rf"^▶ {tid} · ⏱ dev \d+s/\? · dev-mono · ⏸0 ✓0$")
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("CHRONO", r.stdout)
        self.assertRegex(r.stderr, rf"(?m)^CHRONO: avis {tid} cycle 1 clos avec 1 étape\(s\) sans fin, "
                                   r"bornée\(s\) au done : dev$")
        b = json.loads(self.tasks(racine, "chrono", tid, "show", "--json", root=racine).stdout)
        self.assertEqual((b["clos"], [l["statut"] for l in b["etapes"]]), (True, ["incomplète", "finie"]))
        self.assertEqual(self.tasks(racine, "--statusline", root=racine).stdout.strip(), "no active task · ⏸0 ✓1")

    def test_w5_erreur_du_chrono_ne_change_ni_rc_ni_stdout(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        temoin = self.nouvelle(racine, "témoin")
        dossier = racine / ".agents" / "state" / "local" / "task-chrono"
        dossier.parent.mkdir(parents=True, exist_ok=True)
        dossier.write_text("un fichier là où le journal attend un dossier\n", encoding="utf-8")
        r = self.tasks(racine, "start", tid, root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stderr, r"(?m)^CHRONO: non relevé \(ChronoErreur: .*journal chrono")
        self.assertNotIn("CHRONO", r.stdout)
        dossier.unlink()
        r2 = self.tasks(racine, "start", temoin, root=racine)
        self.assertEqual(r.stdout.replace(tid, "<T>"), r2.stdout.replace(temoin, "<T>"), "stdout inchangé")
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"CHRONO: avis {tid} — aucun cycle", r.stderr)

    def test_w9_le_cablage_ne_releve_qu_un_verbe_abouti(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        tasks = charger_tasks()

        def apres(rc=0, **kw):
            ns = argparse.Namespace(**dict({"cmd": "start", "tid": tid, "tids": [tid], "statusline": False,
                                            "dry_run": False}, **kw))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                tasks._chrono_apres(str(racine), ns, rc)
            return err.getvalue()

        for kw, rc in (({"cmd": "retour", "dry_run": True}, 0), ({"cmd": "fournee", "dry_run": True}, 0),
                       ({"statusline": True}, 0), ({"cmd": "retour"}, 1), ({"cmd": "stage"}, 0)):
            with self.subTest(kw=kw, rc=rc):
                self.assertEqual(apres(rc, **kw), "")
                self.assertFalse(self.journal(racine, tid).exists(), (kw, rc))
        self.assertEqual(apres(), "")
        self.assertTrue(self.journal(racine, tid).exists(), "un start abouti relève")
        # cycle et dev OUVERTS : un `retour` refusé ou à blanc pourrait écrire — il ne le fait pas
        avant = self.journal(racine, tid).read_bytes()
        for kw, rc in (({"cmd": "retour"}, 1), ({"cmd": "retour", "dry_run": True}, 0)):
            with self.subTest(ouvert=kw, rc=rc):
                self.assertEqual(apres(rc, **kw), "")
                self.assertEqual(self.journal(racine, tid).read_bytes(), avant, (kw, rc))
        self.assertEqual(apres(0, cmd="retour"), "")
        self.assertNotEqual(self.journal(racine, tid).read_bytes(), avant, "un retour abouti ferme le dev")

    def test_f2_done_puis_fournee_intercalee_le_cycle_repris_reste_ouvert(self):
        """F2 de la clôture : `done P` abouti, puis une `fournee P` s'intercale avant la relecture du board
        par le chrono (P y est `running`) : aucun jalon, avis `reprise depuis le done`, cycle OUVERT. Et
        la relecture se fait SOUS le verrou du board. MUTANTS qui le rougissent : le contrôle de l'état
        retiré de `jalons_du_verbe` ; le `with board_lock` retiré de `_chrono_apres`."""
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        # Le board que relit le chrono du `done` : P rendu `done` par le verbe puis repris `running` par la
        # fournée intercalée — soit, au board relu, P `running` avec son cycle et son dev ouverts.
        tasks = charger_tasks()
        verrou = tasks.board_lock
        tenu = []

        @contextlib.contextmanager
        def verrou_espion(*a, **k):
            with verrou(*a, **k):
                tenu.append(True)
                try:
                    yield
                finally:
                    tenu.pop()

        def load_espion(*a, **k):
            self.assertTrue(tenu, "le board est relu SOUS le verrou")
            return charge(*a, **k)

        charge = tasks.load
        ns = argparse.Namespace(cmd="done", tid=tid, tids=[tid], statusline=False, dry_run=False)
        err = io.StringIO()
        with mock.patch.object(tasks, "board_lock", verrou_espion), mock.patch.object(tasks, "load", load_espion), \
                contextlib.redirect_stderr(err):
            tasks._chrono_apres(str(racine), ns, 0)
        self.assertEqual(err.getvalue(), f"CHRONO: avis {tid} — reprise depuis le done, jalon non posé\n")
        b = json.loads(self.tasks(racine, "chrono", tid, "show", "--json", root=racine).stdout)
        self.assertEqual((b["cycle"], b["clos"]), (1, False))


class QueueParLaCli(Banc):
    """T-01M5PVWHM8KRNRF960PTBV4FE7 lot A, par la CLI RÉELLE : `review-scope` abouti relève `juges` et
    ouvre `cloture` (A5) ; refusé (rc 2), il n'écrit rien. MUTANTS qui le rougissent : `review-scope` retiré
    de `_VERBES_CHRONO` ; `tids = [args.tid]` (AttributeError → « CHRONO: non relevé »)."""

    def journal(self, racine: Path, tid: str) -> list[dict]:
        chemin = racine / ".agents" / "state" / "local" / "task-chrono" / f"{tid}.jsonl"
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]

    def test_c20_tuple_litteral_egal_aux_verbes_jalonnes(self):
        tasks = charger_tasks()
        self.assertEqual(tasks._VERBES_CHRONO, tasks.task_chrono_module().VERBES_JALONNES)

    def test_a5_focus_puis_review_scope_juges_et_cloture_au_journal(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "chrono", tid, "step", "--etape", "dev", "--phase", "end",
                                    root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "focus", tid, root=racine).returncode, 0)
        r = self.tasks(racine, "review-scope", tid, root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertNotIn("CHRONO", r.stdout)
        poses = [(l.get("etape"), l.get("phase")) for l in self.journal(racine, tid) if l["ev"] == "etape"]
        self.assertEqual(poses[2:], [("juges", "begin"), ("juges", "end"), ("cloture", "begin")])

    def test_a5_review_scope_refuse_rien_d_ecrit(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        clos = self.nouvelle(racine, "close")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "done", clos, "--raison", "banc", root=racine).returncode, 0)
        avant = self.journal(racine, tid)
        r = self.tasks(racine, "review-scope", tid, clos, root=racine)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertNotIn("CHRONO", r.stderr)
        self.assertEqual(self.journal(racine, tid), avant, "un review-scope refusé n'écrit rien")
        tasks = charger_tasks()
        ns = argparse.Namespace(cmd="review-scope", tids=[tid], statusline=False, dry_run=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tasks._chrono_apres(str(racine), ns, 2)
        self.assertEqual((err.getvalue(), self.journal(racine, tid)), ("", avant))

    def test_a2c_done_finit_la_cloture_a_l_at_de_la_trace_reelle(self):
        """Angle mort de la revue : la trace `binome/<T>.critic-opus.json`, à la forme qu'écrit
        `.claude/hooks/binome-trace.sh` (`sha`, `at` ISO UTC à la seconde), est lue par le `done` de la
        CLI via `binome_trace`, et `cloture` finit à son `at`. MUTANT qui le rougit : dans `_chrono_apres`,
        `lambda t: binome_trace(str(base), t)` → `lambda t: {}` (clôture bornée au done, avis « sans fin »)."""
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "chrono", tid, "step", "--etape", "dev", "--phase", "end",
                                    root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "focus", tid, root=racine).returncode, 0)
        self.assertEqual(self.tasks(racine, "review-scope", tid, root=racine).returncode, 0)
        debut = next(l["ts"] for l in self.journal(racine, tid) if l.get("etape") == "cloture")
        at_ms = -(-debut // 1000) * 1000  # la seconde pleine suivante : dans la fenêtre de la clôture
        while time.time() * 1000 <= at_ms:
            time.sleep(0.05)
        trace = racine / ".agents" / "state" / "local" / "binome" / f"{tid}.critic-opus.json"
        trace.parent.mkdir(parents=True, exist_ok=True)
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at_ms / 1000))
        trace.write_text(json.dumps({"sha": "d" * 40, "at": at}), encoding="utf-8")
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("clôture sans fin", r.stderr)
        fins = [l["ts"] for l in self.journal(racine, tid) if l.get("etape") == "cloture" and l.get("phase") == "end"]
        self.assertEqual(fins, [at_ms], r.stderr)


class TextesDuLotA(unittest.TestCase):
    """A7 : routeur, miroir Copilot et contrat nomment `review-scope` parmi les verbes qui écrivent le
    journal task-chrono, et ce que `done` complète. MUTANT : texte privé de `review-scope` → faute nommée."""

    RACINE = ICI.parents[1]
    PHRASE_ROUTEUR = "`done` and `review-scope` lay the chrono milestones"

    def textes(self) -> dict[str, str]:
        noms = ("AGENTS.md", ".github/copilot-instructions.md", ".agents/ref/TASKS_CLI_CONTRACT.md",
                ".agents/ref/TASKS_CLI_CONTRACT.json")
        return {n: (self.RACINE / n).read_text(encoding="utf-8") for n in noms}

    def fautes(self, textes: dict[str, str]) -> list[str]:
        out = []
        for nom in ("AGENTS.md", ".github/copilot-instructions.md"):
            t = textes[nom]
            if self.PHRASE_ROUTEUR not in t or "`done` completes `cloture`, `correction` and `porte`" not in t:
                out.append(nom)
        md = textes[".agents/ref/TASKS_CLI_CONTRACT.md"]
        if "`review-scope` abouti écrit aussi le journal `task-chrono`" not in md \
                or "`done` y complète `cloture`, `correction` et `porte`" not in md:
            out.append(".agents/ref/TASKS_CLI_CONTRACT.md")
        try:
            texte_json = json.loads(textes[".agents/ref/TASKS_CLI_CONTRACT.json"])["non_mutants_qui_ecrivent"]["review-scope"]
        except (ValueError, KeyError, TypeError):
            texte_json = ""
        if "task-chrono" not in texte_json or "juges" not in texte_json:
            out.append(".agents/ref/TASKS_CLI_CONTRACT.json")
        return out

    def test_a7_les_quatre_textes_nomment_review_scope(self):
        self.assertEqual(self.fautes(self.textes()), [])

    def test_a7_mutant_texte_prive_de_review_scope_rougit(self):
        for nom in self.textes():
            with self.subTest(nom=nom):
                textes = self.textes()
                textes[nom] = textes[nom].replace("review-scope", "revue")
                self.assertEqual(self.fautes(textes), [nom])


class LigneDEtatTronquee(Banc):
    """F3 de la clôture (décision S-01M5KZ4HSR) : sous le suffixe ⏱, le détail tient en 24 caractères.
    MUTANTS qui le rougissent : la troncature retirée (pire cas : +37) ; la troncature appliquée aussi
    sans suffixe (la ligne d'avant change)."""

    LONG = "dev-multi lot B, passe de correction de la revue de clôture du chantier"

    def ligne(self, racine: Path, chrono: str | None) -> str:
        tasks = charger_tasks()
        if chrono is None:
            return tasks.statusline(str(racine))
        with mock.patch.object(tasks, "_statusline_chrono", lambda _root, _task: chrono):
            return tasks.statusline(str(racine))

    def test_pire_cas_au_plus_36_de_plus_que_la_ligne_d_avant(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        tc = charger_tasks().task_chrono_module()
        pire = tc.suffixe("attente-pilote", 99 * 3600 + 59 * 60, 99 * 3600 + 59 * 60, 50)
        self.assertEqual(len(pire), 35, pire)
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        for n in (25, 26, 40, len(self.LONG)):
            with self.subTest(detail=n):
                self.assertEqual(self.tasks(racine, "stage", tid, self.LONG[:n], root=racine).returncode, 0)
                avant = self.ligne(racine, "")
                apres = self.ligne(racine, pire)
                self.assertEqual(avant, f"▶ {tid} {self.LONG[:n]}".rstrip() + " · ⏸0 ✓0")
                self.assertLessEqual(len(apres), len(avant) + 36, apres)
                self.assertIn(f"{pire} · {self.LONG[:23]}… · ", apres)

    def test_sans_etape_ouverte_ligne_identique_octet_pour_octet(self):
        racine = self.base / "r"
        racine.mkdir()
        tid = self.nouvelle(racine, "tâche")
        self.assertEqual(self.tasks(racine, "start", tid, "--stage", self.LONG, root=racine).returncode, 0)
        r = self.tasks(racine, "chrono", tid, "step", "--etape", "dev", "--phase", "end", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        sl = self.tasks(racine, "--statusline", root=racine).stdout
        self.assertEqual(sl.encode("utf-8"), f"▶ {tid} {self.LONG} · ⏸0 ✓0\n".encode("utf-8"))
        self.assertEqual(self.ligne(racine, None), self.ligne(racine, ""))


@unittest.skipIf(GIT is None, "SAUT ANNONCE : git absent, le worktree lié n'est pas mesuré")
class WorktreeLie(Banc):
    def test_lot_cree_apres_la_branche_vu_a_la_racine_commune(self):
        principal = self.base / "principal"
        principal.mkdir()
        self.git(principal, "init", "-q", "-b", "main")
        parent = self.nouvelle(principal, "parent")
        (principal / "LISEZMOI").write_text("banc\n", encoding="utf-8")
        self.git(principal, "add", "-A")
        self.git(principal, "commit", "-q", "-m", "base", "--no-verify")
        wt = self.base / "wt"
        self.git(principal, "worktree", "add", "-q", "--detach", str(wt))
        lot = self.nouvelle(principal, "lot créé après la branche")
        self.assertEqual(self.tasks(wt, "deps-ready", lot, root=wt).returncode, 2,
                         "prémisse : le board du worktree ne connaît pas le lot")
        journal = Path(".agents") / "state" / "local" / "task-chrono" / f"{parent}.jsonl"
        r = self.tasks(wt, "chrono", parent, "step", "--etape", "dev", "--phase", "begin", "--lot", lot, root=wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((principal / journal).is_file(), r.stdout)
        self.assertFalse((wt / journal).exists(), "le worktree n'a pas son propre journal")
        r = self.tasks(wt, "chrono", parent, "step", "--etape", "dev", "--phase", "end", "--lot", lot,
                       env=dict(self.env, CLAUDE_PROJECT_DIR=str(principal)))
        self.assertEqual(r.returncode, 0, r.stderr)
        lignes = [json.loads(l) for l in (principal / journal).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(l["ev"], l.get("phase"), l.get("lot")) for l in lignes],
                         [("cycle", None, None), ("etape", "begin", lot), ("etape", "end", lot)])
        r = self.tasks(wt, "chrono", parent, "show", "--json", root=wt)
        self.assertEqual(json.loads(r.stdout)["etapes"][0]["statut"], "finie", r.stderr)


@unittest.skipIf(GIT is None, "SAUT ANNONCE : git absent, la fin de fusion par le commit n'est pas mesurée")
class FinDeFusionParLeCommit(Banc):
    """T-01M5PFPSCG0GXM12SK1MRYGZDY : au `retour` et au `done`, la fusion ouverte d'un lot (ou d'une tâche)
    se ferme à l'heure du commit de fusion dont sa pointe relevée est le second parent, sur la chaîne
    `--first-parent` de HEAD ; git hors du verrou ; chaque fin relue sous verrou avant d'être écrite.
    Dates de commit FIXÉES une heure dans le futur : la fin lue est celle du commit, jamais l'horloge.
    MUTANTS qui le rougissent : W1 `done` retiré des verbes de fusion ; W2 premier parent au lieu du second ;
    W3 repli sur l'horloge ; W4 git sous le verrou ; W5 validation du sha retirée ; W6 `retour` retiré des
    verbes de fusion ; W7 `--first-parent` retiré ; W8 relecture sous verrou retirée, cycle ignoré, ou
    clause `est_clos(c)` retirée ; W9 `ref="HEAD"` (voie livraison) ; W10 motif de `vers` retiré ; W11
    et W12 `except ZeroDivisionError` au git, à l'écriture de la fin."""

    def setUp(self) -> None:
        super().setUp()
        self.t = int(time.time()) + 3600

    def sortie(self, racine: Path, *args: str, date: int | None = None) -> str:
        env = dict(self.env)
        if date is not None:
            env.update(GIT_COMMITTER_DATE=f"@{date} +0000", GIT_AUTHOR_DATE=f"@{date} +0000")
        r = subprocess.run(["git", *args], cwd=str(racine), env=env, capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0, (args, r.stderr))
        return r.stdout.strip()

    def depot(self, nom: str = "r") -> Path:
        racine = self.base / nom
        racine.mkdir()
        self.git(racine, "init", "-q", "-b", "main")
        (racine / ".gitignore").write_text(".agents/state/\n", encoding="utf-8")
        (racine / "LISEZMOI").write_text("banc\n", encoding="utf-8")
        self.git(racine, "add", "-A")
        self.git(racine, "commit", "-q", "-m", "base", "--no-verify")
        return racine

    def tache(self, racine: Path, titre: str, fichier: str, parent: str | None = None) -> str:
        tid = self.nouvelle(racine, titre)
        self.assertEqual(self.tasks(racine, "writeset", tid, fichier, root=racine).returncode, 0)
        if parent:
            board = racine / ".agents" / "state" / "board" / "TASKS.json"
            donnees = json.loads(board.read_text(encoding="utf-8"))
            next(t for t in donnees["tasks"] if t["id"] == tid)["fournee"] = {"parent": parent, "lot": titre}
            board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        return tid

    def branche_et_retour(self, racine: Path, tid: str, fichier: str) -> str:
        base = self.sortie(racine, "rev-parse", "HEAD")
        self.git(racine, "checkout", "-q", "-b", f"wt/{tid}")
        (racine / fichier).write_text(f"# {tid}\n", encoding="utf-8")
        self.git(racine, "add", fichier)
        self.git(racine, "commit", "-q", "-m", f"feat: {fichier}", "--no-verify")
        tip = self.sortie(racine, "rev-parse", "HEAD")
        self.git(racine, "checkout", "-q", "main")
        r = self.tasks(racine, "retour", tid, "--base", base, "--branche", f"wt/{tid}", root=racine)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return tip

    def fusionner(self, racine: Path, quoi: str, date: int) -> None:
        self.sortie(racine, "merge", "--no-ff", "-q", quoi, "-m", f"merge: {quoi}", date=date)

    def lignes(self, racine: Path, journal: str) -> list[dict]:
        chemin = racine / ".agents" / "state" / "local" / "task-chrono" / f"{journal}.jsonl"
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]

    def fins_de_fusion(self, racine: Path, journal: str) -> list[tuple]:
        return [(l["cycle"], l.get("lot"), l["ts"]) for l in self.lignes(racine, journal)
                if l["ev"] == "etape" and l.get("etape") == "fusion" and l.get("phase") == "end"]

    def test_w1_lot_ferme_chez_la_mere_au_done_du_lot(self):
        racine = self.depot()
        parent = self.nouvelle(racine, "mère")
        lot = self.tache(racine, "A", "a.py", parent)
        for tid in (parent, lot):
            self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, lot, "a.py")
        self.assertEqual(self.fins_de_fusion(racine, parent), [], "pas encore fusionné : aucune fin")
        self.fusionner(racine, f"wt/{lot}", self.t)
        r = self.tasks(racine, "done", lot, "--raison", "banc", root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.fins_de_fusion(racine, parent), [(1, lot, self.t * 1000)])
        r = self.tasks(racine, "done", parent, "--raison", "banc", root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""), "plus aucune étape sans fin au done de la mère")
        b = json.loads(self.tasks(racine, "chrono", parent, "show", "--json", root=racine).stdout)
        self.assertTrue(b["clos"])

    def test_w2_sans_lot_fin_au_commit_par_le_second_parent(self):
        racine = self.depot()
        tid = self.tache(racine, "tâche", "a.py")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, tid, "a.py")
        self.fusionner(racine, f"wt/{tid}", self.t)
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, self.t * 1000)])

    def test_w3_avance_rapide_aucune_fin_l_avis_reste(self):
        racine = self.depot()
        tid = self.tache(racine, "tâche", "a.py")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, tid, "a.py")
        self.git(racine, "merge", "--ff-only", "-q", f"wt/{tid}")
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, f"CHRONO: avis {tid} cycle 1 clos avec 1 étape(s) sans fin, "
                                   "bornée(s) au done : fusion\n")
        self.assertEqual(self.fins_de_fusion(racine, tid), [], "aucune fin fictive")

    def en_processus(self, racine: Path, tid: str, *, git_espion=None, verrou_espion=None, cmd: str = "retour",
                     maintenant_s: int | None = None) -> str:
        tasks = charger_tasks()
        ns = argparse.Namespace(cmd=cmd, tid=tid if cmd == "done" else None, tids=[tid], statusline=False,
                                dry_run=False)
        err = io.StringIO()
        with contextlib.ExitStack() as pile:
            if maintenant_s is not None:
                tc = tasks.task_chrono_module()
                pile.enter_context(mock.patch.object(tc, "_maintenant_ms", lambda: maintenant_s * 1000))
            if git_espion is not None:
                pile.enter_context(mock.patch.object(tasks, "retour_git", git_espion))
            if verrou_espion is not None:
                pile.enter_context(mock.patch.object(tasks, "board_lock", verrou_espion))
            pile.enter_context(contextlib.redirect_stderr(err))
            tasks._chrono_apres(str(racine), ns, 0)
        return err.getvalue()

    def prete(self, nom: str = "r") -> tuple[Path, str]:
        """Une tâche démarrée, relevée, fusionnée (commit à `self.t`), sans verbe après la fusion."""
        racine = self.depot(nom)
        tid = self.tache(racine, "tâche", "a.py")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, tid, "a.py")
        self.fusionner(racine, f"wt/{tid}", self.t)
        return racine, tid

    def test_w4_git_hors_du_verrou_entre_deux_verrous(self):
        racine, tid = self.prete()
        tasks = charger_tasks()
        verrou, git_reel, ordre, tenu = tasks.board_lock, tasks.retour_git, [], []

        @contextlib.contextmanager
        def verrou_espion(*a, **k):
            with verrou(*a, **k):
                ordre.append("verrou")
                tenu.append(True)
                try:
                    yield
                finally:
                    tenu.pop()
                    ordre.append("libre")

        def git_espion(*a):
            ordre.append("git sous verrou" if tenu else "git")
            return git_reel(*a)

        self.assertEqual(self.en_processus(racine, tid, git_espion=git_espion, verrou_espion=verrou_espion), "")
        self.assertEqual(ordre, ["verrou", "libre", "git", "verrou", "libre"])
        self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, self.t * 1000)])

    def test_w5_pointe_forgee_aucun_appel_git(self):
        racine, tid = self.prete()
        board = racine / ".agents" / "state" / "board" / "TASKS.json"
        donnees = json.loads(board.read_text(encoding="utf-8"))
        next(t for t in donnees["tasks"] if t["id"] == tid)["retour"]["tip"] = "--output=x"
        board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        appels = []
        self.assertEqual(self.en_processus(racine, tid, git_espion=lambda *a: appels.append(a) or ""), "")
        self.assertEqual(appels, [])
        self.assertEqual(self.fins_de_fusion(racine, tid), [])

    def test_w6_le_retour_d_un_lot_ferme_la_fusion_d_un_autre(self):
        racine = self.depot()
        parent = self.nouvelle(racine, "mère")
        lot_a = self.tache(racine, "A", "a.py", parent)
        lot_b = self.tache(racine, "B", "b.py", parent)
        for tid in (parent, lot_a, lot_b):
            self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, lot_a, "a.py")
        self.fusionner(racine, f"wt/{lot_a}", self.t)
        self.branche_et_retour(racine, lot_b, "b.py")
        self.assertEqual(self.fins_de_fusion(racine, parent), [(1, lot_a, self.t * 1000)], "avant tout done")

    def test_w7_seule_la_chaine_first_parent_compte(self):
        racine = self.depot()
        tid = self.tache(racine, "tâche", "a.py")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, tid, "a.py")
        self.git(racine, "checkout", "-q", "-b", "X")
        self.fusionner(racine, f"wt/{tid}", self.t)  # t1 : la pointe entre dans X, hors de main
        self.git(racine, "checkout", "-q", "main")
        self.fusionner(racine, f"wt/{tid}", self.t + 60)  # t2 : la pointe entre dans main
        self.fusionner(racine, "X", self.t + 120)  # X entre dans HEAD : t1 est désormais un ancêtre
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, (self.t + 60) * 1000)])

    def test_w8_fin_relue_sous_verrou_avant_d_etre_ecrite(self):
        tasks = charger_tasks()
        tc = tasks.task_chrono_module()
        git_reel = tasks.retour_git

        def deja_finie(base, tid):
            tc.etape(base, tid, "fusion", "end", now_ms=(self.t + 5) * 1000)

        def cycle_change(base, tid):
            tc._jalon_done(base, tid, (self.t - 10) * 1000)
            tc.commencer(base, tid, (self.t - 5) * 1000)

        def meme_fusion_au_cycle_suivant(base, tid):
            cycle_change(base, tid)
            tc.etape(base, tid, "fusion", "begin", now_ms=(self.t - 5) * 1000)

        def clos_sans_reprise(base, tid):
            tc._jalon_done(base, tid, (self.t - 10) * 1000)

        attendu = {"deja_finie": [(1, None, (self.t + 5) * 1000)], "cycle_change": [],
                   "meme_fusion_au_cycle_suivant": [], "clos_sans_reprise": []}
        for course in (deja_finie, cycle_change, meme_fusion_au_cycle_suivant, clos_sans_reprise):
            with self.subTest(course=course.__name__):
                racine, tid = self.prete(course.__name__)

                def git_espion(*a, _racine=racine, _tid=tid, _course=course):
                    _course(tc.racine(_racine), _tid)  # entre la pré-mesure et l'écriture
                    return git_reel(*a)

                self.assertEqual(self.en_processus(racine, tid, git_espion=git_espion), "", "aucun avis")
                self.assertEqual(self.fins_de_fusion(racine, tid), attendu[course.__name__])

    def test_w9_voie_livraison_fusion_dans_L_finie_au_done(self):
        """Un relevé `--vers L` : la fusion du lot entre dans L, jamais dans HEAD ; le `done` la ferme à
        l'heure du commit de fusion dans L. Mutant `ref="HEAD"` : aucune fin, l'avis « sans fin » sort."""
        racine = self.depot()
        tid = self.tache(racine, "tâche", "a.py")
        self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        r = self.tasks(racine, "livraison", tid, "--branche", "integ/l", root=racine)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        base = self.sortie(racine, "rev-parse", "HEAD")
        self.git(racine, "branch", "integ/l", base)
        self.git(racine, "checkout", "-q", "-b", f"wt/{tid}")
        (racine / "a.py").write_text(f"# {tid}\n", encoding="utf-8")
        self.git(racine, "add", "a.py")
        self.git(racine, "commit", "-q", "-m", "feat: a.py", "--no-verify")
        self.git(racine, "checkout", "-q", "main")
        r = self.tasks(racine, "retour", tid, "--base", base, "--branche", f"wt/{tid}", "--vers", "integ/l",
                       root=racine)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.git(racine, "checkout", "-q", "integ/l")
        self.fusionner(racine, f"wt/{tid}", self.t)
        self.git(racine, "checkout", "-q", "main")
        r = self.tasks(racine, "done", tid, "--raison", "banc", root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, self.t * 1000)])

    def test_w10_livraison_hors_motif_repli_sur_head_avec_avis(self):
        """Un `retour.vers` forgé (option, `..`) n'atteint jamais git comme ref : repli sur HEAD, un avis."""
        for forge in ("--output=x", "a..b"):
            with self.subTest(vers=forge):
                racine, tid = self.prete(f"v{len(forge)}")
                board = racine / ".agents" / "state" / "board" / "TASKS.json"
                donnees = json.loads(board.read_text(encoding="utf-8"))
                next(t for t in donnees["tasks"] if t["id"] == tid)["retour"]["vers"] = forge
                board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
                tasks = charger_tasks()
                appels, git_reel = [], tasks.retour_git
                err = self.en_processus(racine, tid, git_espion=lambda *a: appels.append(a) or git_reel(*a))
                self.assertEqual(err, f"CHRONO: avis {tid} — livraison {forge!r} hors du motif d'un nom de "
                                      "branche : fin de fusion cherchée dans HEAD\n")
                self.assertTrue(appels and all(a[-1].endswith("..HEAD") for a in appels), appels)
                self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, self.t * 1000)])

    def test_w11_panne_git_un_avis_et_les_jalons_du_verbe_poses(self):
        """`git` qui lève : l'avis EXACT, et le `retour` du lot B pose quand même ses jalons (dev fini,
        fusion ouverte). Mutant `except ZeroDivisionError` : « CHRONO: non relevé », aucun jalon."""
        racine = self.depot()
        parent = self.nouvelle(racine, "mère")
        lot_a = self.tache(racine, "A", "a.py", parent)
        lot_b = self.tache(racine, "B", "b.py", parent)
        for tid in (parent, lot_a, lot_b):
            self.assertEqual(self.tasks(racine, "start", tid, root=racine).returncode, 0)
        self.branche_et_retour(racine, lot_a, "a.py")

        def git_en_panne(*a):
            raise RuntimeError("x")

        self.assertEqual(self.en_processus(racine, lot_b, git_espion=git_en_panne),
                         "CHRONO: avis — fin de fusion non mesurée (1 pointe(s)) : RuntimeError: x\n")
        poses = {(l.get("etape"), l.get("phase")) for l in self.lignes(racine, parent)
                 if l["ev"] == "etape" and l.get("lot") == lot_b}
        self.assertIn(("dev", "end"), poses)
        self.assertIn(("fusion", "begin"), poses)

    def test_w12_ecriture_de_fin_en_echec_un_avis(self):
        """L'écriture de la fin qui lève (OSError) : un avis nommant le journal, le verbe aboutit.
        Mutant `except ZeroDivisionError` à `_fermer_fusions` : « CHRONO: non relevé »."""
        racine, tid = self.prete()
        tasks = charger_tasks()
        tc = tasks.task_chrono_module()
        etape_reelle = tc.etape

        def etape_en_panne(base, journal, nom, phase, *a, **k):
            if nom == "fusion" and phase == "end":
                raise OSError("disque")
            return etape_reelle(base, journal, nom, phase, *a, **k)

        with mock.patch.object(tc, "etape", etape_en_panne):
            err = self.en_processus(racine, tid)
        self.assertEqual(err, f"CHRONO: avis {tid} — fin de fusion non écrite (disque)\n")
        self.assertEqual(self.fins_de_fusion(racine, tid), [])

    # LA QUEUE APRÈS LE DEV (T-01M5PVWHM8KRNRF960PTBV4FE7 lot A) : horloge du chrono fixée (`_maintenant_ms`),
    # git RÉEL. MUTANTS qui les rougissent : RS1 `review-scope` retiré de VERBES_DE_FUSION ; A3c filtre par sha
    # retiré ; W4d `rev-list` sous le second verrou ; W4e `except ZeroDivisionError` au `rev-list`.

    def cloture_finie(self, racine: Path, tid: str, debut_s: int, fin_s: int) -> None:
        tc = charger_tasks().task_chrono_module()
        tc.etape(tc.racine(racine), tid, "cloture", "begin", now_ms=debut_s * 1000)
        tc.etape(tc.racine(racine), tid, "cloture", "end", now_ms=fin_s * 1000)

    def porte_tsv(self, racine: Path, *lignes: tuple) -> None:
        chemin = racine / ".agents" / "state" / "local" / "porte-chrono.tsv"
        chemin.write_text("".join("\t".join(map(str, l)) + "\n" for l in lignes), encoding="utf-8")

    def marquer_done(self, racine: Path, tid: str) -> None:
        board = racine / ".agents" / "state" / "board" / "TASKS.json"
        donnees = json.loads(board.read_text(encoding="utf-8"))
        next(t for t in donnees["tasks"] if t["id"] == tid)["state"] = "done"
        board.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")

    def mesures(self, racine: Path, tid: str, nom: str) -> list[tuple]:
        debuts, fins = {}, {}
        for l in self.lignes(racine, tid):
            if l["ev"] == "etape" and l.get("etape") == nom:
                (debuts if l["phase"] == "begin" else fins).setdefault(l["tentative"], l["ts"])
        return [(debuts[k], fins.get(k)) for k in sorted(debuts)]

    @staticmethod
    def iso(s: int) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s))

    def test_rs1_review_scope_ferme_la_fusion_avant_les_juges(self):
        racine, tid = self.prete()
        self.assertEqual(self.tasks(racine, "focus", tid, root=racine).returncode, 0)
        r = self.tasks(racine, "review-scope", tid, root=racine)
        self.assertEqual((r.returncode, r.stderr), (0, ""), "aucun avis « chevauche »")
        self.assertEqual(self.fins_de_fusion(racine, tid), [(1, None, self.t * 1000)])
        self.assertEqual(self.mesures(racine, tid, "juges")[0][0], self.t * 1000, "juges commence à la fin de fusion")

    def test_a3c_seule_la_porte_dont_le_sha_contient_la_pointe(self):
        racine, tid = self.prete()
        avant = self.sortie(racine, "rev-list", "--max-parents=0", "HEAD")
        tete = self.sortie(racine, "rev-parse", "HEAD")
        self.cloture_finie(racine, tid, self.t + 100, self.t + 200)
        self.porte_tsv(racine, (self.iso(self.t + 300), 30, avant, "frozen", 0, "-"),
                       (self.iso(self.t + 400), 40, tete, "frozen", 0, "-"))
        self.marquer_done(racine, tid)
        self.assertEqual(self.en_processus(racine, tid, cmd="done", maintenant_s=self.t + 600), "")
        self.assertEqual(self.mesures(racine, tid, "porte"), [((self.t + 400) * 1000, (self.t + 440) * 1000)])
        self.assertEqual(self.mesures(racine, tid, "correction"), [((self.t + 200) * 1000, (self.t + 400) * 1000)])

    def test_w4d_rev_list_hors_du_verrou_entre_deux_verrous(self):
        racine, tid = self.prete()
        tasks = charger_tasks()
        verrou, git_reel, ordre, tenu = tasks.board_lock, tasks.retour_git, [], []

        @contextlib.contextmanager
        def verrou_espion(*a, **k):
            with verrou(*a, **k):
                ordre.append("verrou")
                tenu.append(True)
                try:
                    yield
                finally:
                    tenu.pop()
                    ordre.append("libre")

        def git_espion(*a):
            ordre.append("git sous verrou" if tenu else "git")
            return git_reel(*a)

        self.cloture_finie(racine, tid, self.t + 100, self.t + 200)
        self.porte_tsv(racine, (self.iso(self.t + 300), 30, self.sortie(racine, "rev-parse", "HEAD"), "frozen", 0))
        self.marquer_done(racine, tid)
        self.assertEqual(self.en_processus(racine, tid, cmd="done", maintenant_s=self.t + 600,
                                           git_espion=git_espion, verrou_espion=verrou_espion), "")
        self.assertEqual(ordre, ["verrou", "libre", "git", "git", "verrou", "libre"])
        self.assertEqual(self.mesures(racine, tid, "porte"), [((self.t + 300) * 1000, (self.t + 330) * 1000)])

    def test_w4e_panne_git_au_rev_list_un_avis_le_jalon_pose(self):
        racine, tid = self.prete()
        git_reel = charger_tasks().retour_git

        def git_en_panne(*a):
            if a[1] == "rev-list":  # a[0] : la racine que `_chrono_apres` passe à `retour_git`
                raise RuntimeError("x")
            return git_reel(*a)

        self.cloture_finie(racine, tid, self.t + 100, self.t + 200)
        self.porte_tsv(racine, (self.iso(self.t + 300), 30, self.sortie(racine, "rev-parse", "HEAD"), "frozen", 0))
        self.marquer_done(racine, tid)
        err = self.en_processus(racine, tid, cmd="done", maintenant_s=self.t + 600, git_espion=git_en_panne)
        self.assertEqual(err, f"CHRONO: avis {tid} — porte non filtrée (1 ligne(s) exclue(s), git en panne) : "
                              "RuntimeError: x\n")
        self.assertEqual(self.mesures(racine, tid, "porte"), [])
        b = json.loads(self.tasks(racine, "chrono", tid, "show", "--json", root=racine).stdout)
        self.assertTrue(b["clos"], "le jalon done est posé")


if __name__ == "__main__":
    unittest.main()
