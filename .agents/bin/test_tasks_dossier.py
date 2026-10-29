#!/usr/bin/env python3
"""T-00001009 (BK-416, E-26) : le board en un fichier par tâche — `board/tasks/<id>.json` et `board/epics/<id>.json`
— lu et écrit par `tasks.py` dans la forme qu'il trouve, migré par `migrate_store` (aucun appelant de production, aucun
verbe CLI), sans clé racine `sync_correlations` ; une tombe pour TOUT id disparu ; le plafond de `purge` (50 tâches par
appel, relevable par `--plafond`, décision pilote S-01M4NFRZS1XK1BEQVGH43Z3EDN).

Témoins WD1 à WD13b du plan `docs/tasks/T-00001009-plan.md` rév. 3, plus WD13b (vii) (réserve C1 du plan-critic,
it. 3/8 : le plafond vaut pour TOUS les états). Chacun est ROUGE à la BASE — `AttributeError` (`store_form`,
`migrate_store`), rc 2 « unrecognized arguments » pour `--plafond`, purge de 51 tâches acceptée ; le mutant que chacun
tue est nommé dans sa docstring et se joue sur une COPIE jetable des parties (L-00000487), jamais sur le fichier que
`tasks.py` charge. Un témoin de REFUS convertit toute issue autre qu'un `BoardError` qui nomme sa garde en échec.

Montage : `tasks.py` chargé par chemin (`spec_from_file_location`, inscrit dans `sys.modules` avant `exec_module`), une
racine jetable par témoin, `CADRE_STATE_DIR` / `AGENTS_EVENTS_DIR` / `TMPDIR` posés, `CLAUDE_PROJECT_DIR` et
`CADRE_PROJECT_ROOT` retirés (de l'environnement enfant aussi) ; la CLI reçoit `--root <racine>`. Fixtures
SYNTHÉTIQUES ; aucun parcours d'arbre : `iterdir()` sur des dossiers connus. Git (WD10, WD12) : dépôt jetable,
identité en config LOCALE, hooks coupés, configs système et globale écartées.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("tasks_dossier_banc", HERE / "tasks.py")
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

TACHES = ("tasks", "epics")
BOARD_REL = Path(".agents") / "state" / "board"
TASKS_REL = BOARD_REL / "TASKS.json"
OUTBOX_REL = BOARD_REL / "sync_outbox"
LOTS_REL = Path(".agents") / "state" / "local" / "sync_outbox_lots"
QUARANTAINE_REL = Path(".agents") / "state" / "local" / "sync_outbox_quarantaine"
ULID_A = "T-01AAAAAAAAAAAAAAAAAAAAAAAA"
ULID_B = "T-01BBBBBBBBBBBBBBBBBBBBBBBB"
JOUR = "2026-10-11"


class _Crash(BaseException):
    """Une mort de processus : traverse les `except Exception` / `except OSError` du code."""


def canon(objet: Any) -> bytes:
    """La sérialisation de `save()` et des enregistrements : indent 2, clés triées, UTF-8 brut, LF."""
    return (json.dumps(objet, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def tache(tid: str, titre: str, state: str = "pending", stage: str = "", updated: str = JOUR) -> dict[str, Any]:
    return {"id": tid, "owner": "", "stage": stage, "state": state, "task": titre, "updated": updated}


def vivante(tid: str) -> dict[str, Any]:
    return {"board_task_id": tid, "tombstoned": False}


def tombee(tid: str) -> dict[str, Any]:
    return {"board_task_id": tid, "tombstoned": True}


def monolithe() -> dict[str, Any]:
    """Board synthétique de WD2 : `T-012` (alias court), `T-00000057`, `T-999` et `T-1000` (l'ordre NUMÉRIQUE n'est pas
    celui des chaînes), deux ULID, deux epics, une tâche SUPPRIMÉE dont les clés sont tombées (`T-00000177`), des
    corrélations acquittées (aucune outbox). Les tâches sont stockées HORS de l'ordre `sort_key`."""
    return {
        "epics": [{"id": "E-01", "titre": "un"}, {"id": "E-02", "titre": "deux"}],
        "sync_correlations": {
            "op-012": vivante("T-012"), "op-057": vivante("T-00000057"), "op-1000": vivante("T-1000"),
            "op-a": vivante(ULID_A), "op-177-c": tombee("T-00000177"), "op-177-s": tombee("T-00000177"),
        },
        "tasks": [tache(ULID_B, "ulid b"), tache("T-1000", "mille", state="running"), tache("T-999", "neuf cent"),
                  tache("T-012", "douze — été"), tache(ULID_A, "ulid a"), tache("T-00000057", "cinquante-sept")],
    }


def ids(data: dict[str, Any]) -> list[str]:
    return [t["id"] for t in data["tasks"]]


def stages(data: dict[str, Any]) -> dict[str, str]:
    return {t["id"]: t.get("stage", "") for t in data["tasks"]}


def env_enfant(base: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT") and not k.startswith("GIT_")}
    env.update(CADRE_STATE_DIR=str(base / "state"), AGENTS_EVENTS_DIR=str(base / "events"), TMPDIR=str(base / "tmp"))
    return env


def git(depot: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    p = subprocess.run(["git", "-C", str(depot), "-c", f"core.hooksPath={os.devnull}", *args],
                       capture_output=True, text=True, env=env, timeout=120)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : rc={p.returncode} {p.stderr[-400:]}")
    return p


def depot_git(depot: Path) -> None:
    depot.mkdir(parents=True, exist_ok=True)
    git(depot, "-c", "init.defaultBranch=main", "init", "-q")
    for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"), ("commit.gpgsign", "false")):
        git(depot, "config", cle, valeur)
    (depot / ".gitignore").write_text("/.agents/state/local/\n", encoding="utf-8")


class _Racine(unittest.TestCase):
    """Une racine jetable et un environnement d'état isolé."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        (self.root / BOARD_REL).mkdir(parents=True)
        for sous in ("state", "events", "tmp"):
            (self.base / sous).mkdir()
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(self.base / "state"),
            "AGENTS_EVENTS_DIR": str(self.base / "events"),
            "TMPDIR": str(self.base / "tmp"),
        })
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def poser(self, data: dict[str, Any], racine: Path | None = None) -> bytes:
        """Un monolithe canonique ; rend ses octets."""
        chemin = (racine or self.root) / TASKS_REL
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(canon(data))
        return chemin.read_bytes()

    def migrer(self, racine: Path | None = None) -> str:
        return tasks.migrate_store(str(racine or self.root))

    def cliche(self, racine: Path | None = None) -> dict[str, bytes]:
        """Chaque fichier du board (TASKS.json, `tasks/`, `epics/`, `sync_outbox/`, noms réservés) et des lots locaux."""
        racine = racine or self.root
        board, vue = racine / BOARD_REL, {}
        for p in sorted(board.iterdir()) if board.is_dir() else ():
            if p.is_file():
                vue[p.name] = p.read_bytes()
            elif p.is_dir():
                vue[f"{p.name}/"] = b"<dir>"
                for q in sorted(p.iterdir()):
                    vue[f"{p.name}/{q.name}"] = q.read_bytes() if q.is_file() else b"<dir>"
        lots = racine / LOTS_REL
        for q in sorted(lots.iterdir()) if lots.is_dir() else ():
            vue[f"lots/{q.name}"] = q.read_bytes()
        return vue

    def refus(self, appel: Any, *attendus: str) -> str:
        """`appel()` lève `BoardError` et son message nomme chaque attendu ; toute autre issue est un ÉCHEC nommé."""
        try:
            rendu = appel()
        except tasks.BoardError as exc:
            message = str(exc)
            for attendu in attendus:
                self.assertIn(attendu, message)
            return message
        except Exception as exc:  # converti en échec d'assertion, jamais avalé
            self.fail(f"{type(exc).__name__} au lieu de BoardError : {exc}")
        self.fail(f"accepté au lieu d'un refus nommé, rendu {rendu!r}")

    def cli(self, *argv: str, racine: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HERE / "tasks.py"), "--root", str(racine or self.root), *argv],
                              capture_output=True, text=True, env=env_enfant(self.base), timeout=300)

    def nouvelle(self, titre: str, racine: Path | None = None) -> str:
        return tasks.new_task(str(racine or self.root), titre, "banc").split()[1]

    def enregistrement(self, tid: str, collection: str = "tasks", racine: Path | None = None) -> dict[str, Any]:
        return json.loads(((racine or self.root) / BOARD_REL / collection / f"{tid}.json").read_bytes())

    def sans_commande_destructive(self, message: str) -> None:
        """Aucune ligne du refus n'est une commande qui EFFACE (`rm`, `rmdir`, `git clean`, `unlink`) : copiée-collée,
        elle détruirait le côté juste (Piège 2)."""
        for ligne in message.splitlines():
            mots = ligne.split()
            self.assertFalse(mots and (mots[0] in ("rm", "rmdir", "unlink") or mots[:2] == ["git", "clean"]),
                             f"commande destructive exécutable telle quelle dans le refus : {ligne}")

    def commente_ou_garde(self, message: str) -> None:
        """T1 (clôture fournée 4) : collé ENTIER dans un shell, le refus n'exécute que des lignes GARDÉES — un
        commentaire `# …`, une mise de côté `test -e … && test ! -e … && mv -n …`, ou la ligne `python3 -c` qui
        re-vérifie les deux formes ; jamais du texte libre (un chemin à apostrophe y ouvrirait une quote)."""
        for ligne in message.splitlines():
            self.assertTrue(ligne.startswith("# ") or ligne.startswith("python3 -c ")
                            or (ligne.startswith("test -e ") and " && test ! -e " in ligne and " && mv -n " in ligne),
                            f"ligne ni commentée ni gardée dans le refus : {ligne}")

    @staticmethod
    def source_mv(ligne: str) -> str:
        """Le nom de la SOURCE du `mv -n` d'une ligne gardée."""
        return Path(shlex.split(ligne.split(" && ")[-1])[2]).name

    def jouer_garde(self, ligne: str) -> tuple[int, str]:
        """Une ligne gardée jouée SANS shell : chaque maillon `&&` par `shlex.split`, dans l'ordre, arrêt au premier
        rc non nul (la sémantique de `&&`) ; rend (rc, stderr) du dernier maillon joué."""
        for maillon in ligne.split(" && "):
            fait = subprocess.run(shlex.split(maillon), capture_output=True, text=True, cwd=str(self.base), timeout=60)
            if fait.returncode != 0:
                return fait.returncode, fait.stderr
        return 0, ""

    def bash(self, message: str) -> subprocess.CompletedProcess:
        """Le refus collé ENTIER dans bash, tel que le CLI l'imprime (`tasks.py: <message>`)."""
        return subprocess.run(["bash"], input=f"tasks.py: {message}\n", capture_output=True, text=True,
                              cwd=str(self.base), env=env_enfant(self.base), timeout=120)

    def definitifs(self, racine: Path | None = None) -> list[str]:
        dossier = (racine or self.root) / OUTBOX_REL
        return sorted(p.name for p in dossier.iterdir()) if dossier.is_dir() else []


class FormeEtLectureTests(_Racine):
    def test_wd1_store_form_et_noms_reserves(self) -> None:
        """WD1 : `store_form` rend `absent`, `monolithe`, `dossier` ou `les deux` ; le dossier est PRÉSENT ssi un
        `<id>.json` conforme existe sous `board/tasks/` ou `board/epics/` — des dossiers vides ou à noms pointés seuls,
        `board/archive/tasks/T-1.json`, `board/tombes.jsonl` et `board/retention.json` (réservés à la tâche d'archive)
        laissent la forme `absent` et `load` vide. Tue M-dossier-nu, M-archive-lue, M-registre-lu, M-réglage-lu."""
        r, board = str(self.root), self.root / BOARD_REL
        self.assertEqual(tasks.store_form(r), "absent")
        (board / "tasks").mkdir()
        (board / "epics").mkdir()
        (board / "tasks" / ".T-1.json").write_bytes(b"{")
        (board / "tasks" / ".tasks-x.tmp").write_bytes(b"")
        self.assertEqual(tasks.store_form(r), "absent", "dossiers vides ou à noms pointés seuls")
        (board / "archive" / "tasks").mkdir(parents=True)
        (board / "archive" / "tasks" / "T-1.json").write_bytes(
            canon({"format": 1, "id": "T-1", "record": tache("T-1", "archivée"), "sync_operations": []}))
        (board / "tombes.jsonl").write_bytes(b'{"id": "T-2", "sync_operations": ["op-2"]}\n')
        (board / "retention.json").write_bytes(b'{"archive_apres_jours": 30}\n')
        self.assertEqual(tasks.store_form(r), "absent", "noms réservés à la tâche d'archive")
        self.assertEqual(tasks.load(r)["tasks"], [])
        self.poser({"tasks": [tache("T-1", "un")]})
        self.assertEqual(tasks.store_form(r), "monolithe")
        (board / "TASKS.json").unlink()
        (board / "epics" / "E-01.json").write_bytes(canon({"format": 1, "id": "E-01", "record": {"id": "E-01"}}))
        self.assertEqual(tasks.store_form(r), "dossier", "une epic seule suffit")
        (board / "tasks" / "T-1.json").write_bytes(
            canon({"format": 1, "id": "T-1", "record": tache("T-1", "un"), "sync_operations": []}))
        self.assertEqual(tasks.store_form(r), "dossier")
        self.assertEqual(ids(tasks.load(r)), ["T-1"])
        self.poser({"tasks": [tache("T-1", "un")], "epics": [{"id": "E-01"}]})
        self.assertEqual(tasks.store_form(r), "les deux")

    def test_wd2_load_dossier_egale_load_monolithe(self) -> None:
        """WD2 : sur un board synthétique, `load` dossier == `load` monolithe — tâches (rangées par `sort_key` :
        `T-012`, `T-00000057`, `T-999`, `T-1000`, puis les ULID), epics, projection des corrélations (tombées
        comprises) ; une tombe SANS clé (suppression sous `suppress_sync` d'une tâche sans corrélation) est relue
        absente, sans clé ajoutée ; `load` relève les noms vivants UNE fois (défaut trouvé en dev : un relevé par
        fichier rendait la lecture du board réel quadratique, 3,7 s). Tue M-sans-projection, M-ordre-chaîne et
        M-tombes-quadratique."""
        mono = self.base / "mono"
        self.poser(monolithe(), mono)
        self.poser(monolithe())
        self.migrer()
        with mock.patch.object(tasks, "_noms_vivants", wraps=tasks._noms_vivants) as espion:
            a, b = tasks.load(str(mono)), tasks.load(str(self.root))
        self.assertEqual(espion.call_count, 1, "noms vivants relevés par fichier : lecture quadratique (3,7 s mesurés)")
        self.assertEqual(tasks.store_form(str(self.root)), "dossier")
        self.assertEqual(ids(b), ["T-012", "T-00000057", "T-999", "T-1000", ULID_A, ULID_B])
        self.assertEqual(sorted(a["tasks"], key=lambda t: tasks.sort_key(t["id"])), b["tasks"])
        self.assertEqual(a["epics"], b["epics"])
        self.assertEqual(a["sync_correlations"], b["sync_correlations"])
        self.assertEqual(b["sync_outbox"], [])
        with tasks.suppress_sync("op-v3-wd2"):
            tasks.delete_task(str(self.root), "T-999")
        self.assertEqual(self.enregistrement("T-999"),
                         {"format": 1, "id": "T-999", "record": None, "sync_operations": []})
        c = tasks.load(str(self.root))
        self.assertNotIn("T-999", ids(c))
        self.assertEqual(c["sync_correlations"], a["sync_correlations"])

    def test_wd2b_cle_reindexee_revient_dans_l_enregistrement(self) -> None:
        """WD2b (exec-critic de T-00001009, mineur) : en forme dossier, une clé qu'une fusion a retirée de
        l'enregistrement de sa tâche (intent encore en vol) est ré-indexée à la lecture et revient au save suivant
        dans le `sync_operations` de CET enregistrement — et la ligne stderr dit cela, jamais « dans TASKS.json ».
        Tue M-libellé-monolithe."""
        r, board = str(self.root), self.root / BOARD_REL
        self.poser({"tasks": [tache("T-1", "un")]})
        self.migrer()
        tid = self.nouvelle("clé perdue à la fusion")
        enveloppe = self.enregistrement(tid)
        (op,) = enveloppe["sync_operations"]
        enveloppe["sync_operations"] = []
        (board / "tasks" / f"{tid}.json").write_bytes(canon(enveloppe))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tasks.stage_task(r, "T-1", "x")
        self.assertEqual(self.enregistrement(tid)["sync_operations"], [op])
        self.assertIn("sync_operations de l'enregistrement", err.getvalue())
        self.assertNotIn("dans TASKS.json", err.getvalue())

    def test_wd3_un_verbe_reecrit_un_seul_fichier(self) -> None:
        """WD3 : en forme dossier, `stage` réécrit UN fichier — les autres gardent inode, date et octets ; aucun
        fichier ne porte `sync_correlations`, aucun fichier racine sous `board/` ; chaque temporaire publié par
        `os.replace` vient d'HORS de `board/` ; la garde de commit du pont (`guard_board_commit`) qui refuse ⇒ rien
        d'écrit, ni lot. Tue M-tout-réécrire, M-clé-racine, M-tmp-dans-board, M-garde-ignorée."""
        self.poser(monolithe())
        self.migrer()
        board = self.root / BOARD_REL

        def etat() -> dict[str, tuple[int, int, bytes]]:
            return {f"{c}/{p.name}": (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
                    for c in TACHES for p in (board / c).iterdir()}

        avant, sources, vrai = etat(), [], os.replace

        def espion(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
            sources.append(str(src))
            vrai(src, dst, *args, **kwargs)

        with mock.patch.object(os, "replace", espion):
            tasks.stage_task(str(self.root), "T-012", "revue")
        apres = etat()
        self.assertEqual(sorted(nom for nom in avant if avant[nom] != apres.get(nom)), ["tasks/T-012.json"])
        self.assertEqual(self.enregistrement("T-012")["record"]["stage"], "revue")
        self.assertEqual(sorted(p.name for p in board.iterdir()), ["epics", "sync_outbox", "tasks"])
        for nom, (_ino, _date, octets) in apres.items():
            self.assertNotIn("sync_correlations", json.loads(octets), nom)
        self.assertTrue(sources, "aucun os.replace relevé : le témoin serait vide")
        for src in sources:
            self.assertFalse(Path(src).resolve().is_relative_to(board.resolve()), f"temporaire sous board/ : {src}")
        avant = self.cliche()
        with tasks.guard_board_commit(lambda: False):
            self.refus(lambda: tasks.stage_task(str(self.root), "T-012", "refusée"), "commit guard")
        self.assertEqual(self.cliche(), avant, "la garde de commit du pont a laissé publier un save en dossier")

    def test_wd4_tout_id_disparu_recoit_une_tombe(self) -> None:
        """WD4 : (a) `delete` d'une tâche à clé ⇒ tombe portant ses clés ; (b) `delete` d'une tâche SANS clé sous
        `suppress_sync` ⇒ tombe à `sync_operations: []` (écrite par `record_bytes_pour(…, "tasks")`), l'ancien
        fichier ne revient pas ; (c) `delete` d'une tâche à clé NON tombée sous `suppress_sync` ⇒ `BoardError`
        « dangling correlation », RIEN d'écrit, la tâche se relit vivante ; (d) une tombe réécrite en tâche vivante ⇒
        refus nommé, rien d'écrit ; (e) défaut trouvé en dev, mesuré : un intent de création ORPHELIN (l'enregistrement
        de sa tâche retiré du dossier) gelait toute écriture, `delete` compris, sans remède — le refus reste et nomme
        les deux sorties (restaurer l'enregistrement, écarter le fichier d'intent) ; l'intent écarté, le board s'écrit.
        Tue M-tombe-si-clé, M-retrait-fichier, M-tombe-par-déduction, M-dangling-avalé, M-orphelin-sans-remède."""
        r = str(self.root)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux"), tache("T-3", "trois")],
                    "sync_correlations": {"op-3": vivante("T-3")}})
        self.migrer()
        tid = self.nouvelle("à clé")
        tasks.delete_task(r, tid)
        tombe = self.enregistrement(tid)
        self.assertIsNone(tombe["record"])
        self.assertEqual(len(tombe["sync_operations"]), 2, "création et suppression")
        with tasks.suppress_sync("op-v3-b"):
            tasks.delete_task(r, "T-1")
        self.assertEqual(self.enregistrement("T-1"), {"format": 1, "id": "T-1", "record": None, "sync_operations": []})
        self.assertNotIn("T-1", ids(tasks.load(r)))
        avant = self.cliche()
        with tasks.suppress_sync("op-v3-c"):
            self.refus(lambda: tasks.delete_task(r, "T-3"), "op-3", "T-3", "dangling")
        self.assertEqual(self.cliche(), avant)
        self.assertIn("T-3", ids(tasks.load(r)))
        d = tasks.load(r)
        d["tasks"].append(tache("T-1", "revenue"))
        self.refus(lambda: tasks.save(r, d), "T-1", "tombstone")
        d = tasks.load(r)
        d["tasks"].append(tache("T-00000001", "revenue sous un autre alias"))
        self.refus(lambda: tasks.save(r, d), "T-00000001", "T-1")
        self.assertEqual(self.cliche(), avant)
        orpheline = self.nouvelle("orpheline")
        (self.root / BOARD_REL / "tasks" / f"{orpheline}.json").unlink()
        (intent,) = [p for p in (self.root / OUTBOX_REL).iterdir()
                     if json.loads(p.read_bytes())["correlation"]["board_task_id"] == orpheline]
        avant = self.cliche()
        self.refus(lambda: tasks.stage_task(r, "T-2", "x"), "dangling", orpheline, "restore the record", str(intent))
        self.assertEqual(self.cliche(), avant)
        intent.rename(self.base / intent.name)
        tasks.stage_task(r, "T-2", "x")
        self.assertEqual(stages(tasks.load(r))["T-2"], "x")

    def test_wd5_f5_en_forme_dossier(self) -> None:
        """WD5 : en forme dossier, une suppression EN VOL (intent `after: null` dans `sync_outbox/`) à côté d'un
        enregistrement RESTAURÉ vivant ⇒ toute écriture refusée, l'id nommé, rien d'écrit ; `list` (`load`) vit ;
        `delete <id>` passe et repose la tombe ; le board s'écrit de nouveau. Tue M-f5-dossier."""
        r, board = str(self.root), self.root / BOARD_REL
        self.poser({"tasks": [tache("T-1", "un")]})
        self.migrer()
        tid = self.nouvelle("revenante")
        tasks.drain_sync_outbox(r, lambda _intent: True)
        vivant = (board / "tasks" / f"{tid}.json").read_bytes()
        tasks.delete_task(r, tid)
        self.assertTrue(self.definitifs(), "la suppression doit être EN VOL")
        (board / "tasks" / f"{tid}.json").write_bytes(vivant)
        avant = self.cliche()
        self.refus(lambda: tasks.new_task(r, "bloquée", "banc"), tid)
        self.refus(lambda: tasks.stage_task(r, "T-1", "x"), tid)
        self.assertEqual(self.cliche(), avant)
        self.assertIn(tid, ids(tasks.load(r)))
        self.assertIn("deleted", tasks.delete_task(r, tid))
        self.assertIsNone(self.enregistrement(tid)["record"])
        tasks.stage_task(r, "T-1", "x")
        self.assertEqual(stages(tasks.load(r))["T-1"], "x")


class EcritureEtReprisesTests(_Racine):
    def test_wd6_reprise_apres_crash(self) -> None:
        """WD6 : (a) mort APRÈS le lot, avant toute application ⇒ le disque est ancien, la lecture voit le save (lot
        validé en surcouche), le save suivant l'applique et retire le lot ; (b) mort au MILIEU (un enregistrement
        posé sur deux) ⇒ même chose, application idempotente, disque lu SANS lot == état du save ; (c) un lot TRONQUÉ,
        et un lot dont l'empreinte ne couvre pas son contenu, sont ignorés à la lecture, mis en quarantaine au save
        suivant, jamais appliqués. Tue M-sans-lot, M-lot-non-repris, M-lot-tronqué-appliqué."""
        r, board, lots = str(self.root), self.root / BOARD_REL, self.root / LOTS_REL
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux"), tache("T-3", "trois")]})
        self.migrer()

        def mort(apres: int) -> Any:
            vrai, appels = tasks._poser_definitif, []

            def poser(*args: Any, **kwargs: Any) -> None:
                if len(appels) == apres:
                    raise _Crash(f"mort après {apres} enregistrement(s)")
                appels.append(args[1])
                vrai(*args, **kwargs)

            return mock.patch.object(tasks, "_poser_definitif", poser)

        with mort(0), self.assertRaises(_Crash):
            tasks.stage_task(r, "T-1", "a")
        self.assertEqual(len(list(lots.iterdir())), 1, "le lot est le point de validation : il reste")
        self.assertEqual(self.enregistrement("T-1")["record"]["stage"], "")
        self.assertEqual(stages(tasks.load(r))["T-1"], "a", "la lecture ne voit pas le save validé")
        tasks.stage_task(r, "T-3", "c")
        self.assertFalse(lots.is_dir() and any(lots.iterdir()), "lot non repris")
        self.assertEqual(self.enregistrement("T-1")["record"]["stage"], "a")

        d = tasks.load(r)
        for t in d["tasks"]:
            t["stage"] = {"T-1": "m1", "T-2": "m2"}.get(t["id"], t["stage"])
        with mort(1), self.assertRaises(_Crash):
            tasks.save(r, d)
        self.assertEqual(stages(tasks.read_records(board, TACHES)), {"T-1": "m1", "T-2": "", "T-3": "c"})
        self.assertEqual(stages(tasks.load(r)), {"T-1": "m1", "T-2": "m2", "T-3": "c"})
        tasks.new_task(r, "après la reprise", "banc")
        self.assertFalse(lots.is_dir() and any(lots.iterdir()), "lot non repris")
        relu = stages(tasks.read_records(board, TACHES))
        self.assertEqual((relu["T-1"], relu["T-2"], relu["T-3"]), ("m1", "m2", "c"))

        lots.mkdir(parents=True, exist_ok=True)
        (lots / "00000000000000000001.json").write_bytes(b'{"cible": "ab", "forme": "dossier", "enregistr')
        pirate = {"forme": "dossier", "intents": [], "enregistrements": {"tasks/T-2.json": {
            "format": 1, "id": "T-2", "record": tache("T-2", "pirate", stage="pirate"), "sync_operations": []}}}
        pirate["cible"] = "0" * 64
        (lots / "00000000000000000002.json").write_bytes(json.dumps(pirate).encode("utf-8"))
        self.assertEqual(stages(tasks.load(r))["T-2"], "m2", "un lot non validé a été lu")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tasks.stage_task(r, "T-3", "d")
        self.assertEqual(stages(tasks.read_records(board, TACHES))["T-2"], "m2", "un lot non validé a été appliqué")
        self.assertFalse(any(lots.iterdir()) if lots.is_dir() else False)
        self.assertEqual(sorted(p.name for p in (self.root / QUARANTAINE_REL).iterdir()),
                         ["00000000000000000001.json", "00000000000000000002.json"])
        self.assertIn("quarantaine", err.getvalue())

    def test_wd7_lecture_concurrente_jamais_un_demi_save(self) -> None:
        """WD7 : (a) une lecture injectée ENTRE deux `_poser_definitif` d'un save voit le save ENTIER (lot validé en
        surcouche) ; (b) un save ENTIER écrit pendant la lecture du dossier (après le premier fichier lu, sans lot
        visible avant ni après) ⇒ la lecture le DÉTECTE et relit, jamais un mélange. Tue M-sans-relecture."""
        r = str(self.root)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]})
        self.migrer()
        vrai_poser, vus = tasks._poser_definitif, []

        def entre(*args: Any, **kwargs: Any) -> None:
            vrai_poser(*args, **kwargs)
            if not vus and str(args[1]).startswith("T-"):
                vus.append(stages(tasks.load(r)))

        d = tasks.load(r)
        d["tasks"][0]["stage"], d["tasks"][1]["stage"] = "x1", "x2"
        with mock.patch.object(tasks, "_poser_definitif", entre):
            tasks.save(r, d)
        self.assertEqual(vus, [{"T-1": "x1", "T-2": "x2"}])

        vrai_lire, tir = tasks._lire_plafonne, []

        def lire(fichier: Any, plafond: int) -> bytes:
            octets = vrai_lire(fichier, plafond)
            if not tir and plafond == tasks._PLAFOND_ENREGISTREMENT_OCTETS:
                tir.append(True)
                e = tasks.load(r)
                e["tasks"][0]["stage"], e["tasks"][1]["stage"] = "y1", "y2"
                tasks.save(r, e)
            return octets

        with mock.patch.object(tasks, "_lire_plafonne", lire):
            lu = stages(tasks.load(r))
        self.assertTrue(tir, "l'injection n'a pas tiré")
        self.assertEqual(lu, {"T-1": "y1", "T-2": "y2"}, "lecture mélangée")

    def test_wd8_migrate_store_compte_outbox_et_relecture(self) -> None:
        """WD8 : `migrate_store` monolithe ⇒ dossier, les triplets (op, tâche, tombée) AVANT == APRÈS avec une outbox
        NON vide (création + suppression en vol), la même vue d'outbox, les mêmes tâches et epics, TASKS.json retiré ;
        rejoué ⇒ « already migrated » ; un TASKS.json d'avant T-1058 (`sync_outbox` EN LIGNE) ⇒ ses intents passent
        en fichiers, puis le dossier ; une relecture fausse ⇒ `BoardError`, dossier retiré, monolithe intact. Tue
        M-clé-perdue, M-outbox-ignorée, M-unlink-avant-relecture."""
        r = str(self.root)
        self.poser({"tasks": [tache("T-1", "un")], "epics": [{"id": "E-01", "titre": "e"}],
                    "sync_correlations": {"op-acquittee": vivante("T-1"), "op-9": tombee("T-9")}})
        tid = self.nouvelle("supprimée en vol")
        tasks.delete_task(r, tid)
        avant = tasks.load(r)
        triplets = sorted((op, c["board_task_id"], c["tombstoned"]) for op, c in avant["sync_correlations"].items())
        self.assertEqual((len(avant["sync_outbox"]), len(triplets)), (2, 4))
        intents = self.definitifs()
        message = self.migrer()
        self.assertEqual(tasks.store_form(r), "dossier")
        self.assertFalse((self.root / TASKS_REL).exists())
        apres = tasks.load(r)
        self.assertEqual(sorted((op, c["board_task_id"], c["tombstoned"])
                                for op, c in apres["sync_correlations"].items()), triplets)
        self.assertEqual(apres["sync_outbox"], avant["sync_outbox"])
        self.assertEqual(self.definitifs(), intents)
        self.assertEqual((apres["tasks"], apres["epics"]), (avant["tasks"], avant["epics"]))
        self.assertIn(f"{len(triplets)} correlation", message)
        self.assertIn("already migrated", self.migrer())

        enligne = self.base / "enligne"
        self.poser({"tasks": [tache("T-1", "un")]}, enligne)
        self.nouvelle("intent en ligne", enligne)
        (fichier,) = (enligne / OUTBOX_REL).iterdir()
        intent = json.loads(fichier.read_bytes())["intent"]
        texte = json.loads((enligne / TASKS_REL).read_bytes())
        texte["sync_outbox"] = [intent]
        self.poser(texte, enligne)
        fichier.unlink()
        self.migrer(enligne)
        self.assertEqual(tasks.store_form(str(enligne)), "dossier")
        self.assertEqual(tasks.load(str(enligne))["sync_outbox"], [intent])
        self.assertEqual(len(self.definitifs(enligne)), 1)

        relu = self.base / "relu"
        octets = self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]}, relu)
        vrai = tasks.read_records
        with mock.patch.object(tasks, "read_records", lambda d, c: {**vrai(d, c), "tasks": []}):
            self.refus(lambda: self.migrer(relu), "read back")
        self.assertEqual((relu / TASKS_REL).read_bytes(), octets)
        self.assertEqual(tasks.store_form(str(relu)), "monolithe")
        self.assertFalse((relu / BOARD_REL / "tasks").exists())

    def test_wd9_refus_deux_formes_f5_et_id_hostile(self) -> None:
        """WD9 : deux formes DIFFÉRENTES ⇒ `load` et `migrate_store` refusent en nommant les ids d'un seul côté, rien
        d'écrit, AUCUNE commande `rm` ; la mise de côté des DOSSIERS (`mv -n` vers un nom daté), EXÉCUTÉE telle quelle
        (racine à espace et apostrophe), rend le monolithe seul, et les dossiers restent à côté, intacts ; deux formes
        ÉGALES ⇒ lisibles, toute écriture refusée avec la ligne `python3 -c` qui, exécutée, finit la migration ; F5
        présent ⇒ `migrate_store` refuse, rien d'écrit ; un id hostile (`../T-1`) ⇒ refusé, rien d'écrit. Tue
        M-both-sans-contrôle, M-nom-libre, M-remède-destructif."""
        racine = self.base / "s17 it's"
        r = str(racine)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]}, racine)
        self.migrer(racine)
        dossier = self.cliche(racine)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-3", "trois")]}, racine)
        avant = self.cliche(racine)
        message = self.refus(lambda: tasks.load(r), "T-2", "T-3")
        self.refus(lambda: self.migrer(racine), "T-2", "T-3")
        self.assertEqual(self.cliche(racine), avant)
        self.sans_commande_destructive(message)
        self.commente_ou_garde(message)
        lignes = [ligne for ligne in message.splitlines()
                  if " mv -n " in ligne and self.source_mv(ligne) != "TASKS.json"]
        self.assertEqual(len(lignes), 1, message)
        cible = Path(shlex.split(lignes[0].split(" && ")[-1])[3])
        cible.mkdir()  # T1 : une cible datée qui EXISTE refuse la ligne — jamais le dossier imbriqué dedans
        self.assertNotEqual(self.jouer_garde(lignes[0])[0], 0)
        self.assertEqual((list(cible.iterdir()), tasks.store_form(r)), ([], "les deux"), "dossier imbriqué")
        cible.rmdir()
        rc, err = self.jouer_garde(lignes[0])
        self.assertEqual(rc, 0, err)
        self.assertEqual((tasks.store_form(r), ids(tasks.load(r))), ("monolithe", ["T-1", "T-3"]))
        (de_cote,) = [p for p in (racine / BOARD_REL).iterdir() if p.name.startswith("tasks.mis-de-cote-")]
        self.assertEqual({p.name: p.read_bytes() for p in de_cote.iterdir()},
                         {nom.partition("/")[2]: octets for nom, octets in dossier.items() if nom.startswith("tasks/")
                          and octets != b"<dir>"}, "le dossier mis de côté n'est pas intact")

        egales = self.base / "égales it's"
        self.poser({"tasks": [tache("T-1", "un")]}, egales)
        self.migrer(egales)
        self.poser({"tasks": [tache("T-1", "un")]}, egales)
        self.assertEqual(ids(tasks.load(str(egales))), ["T-1"])
        avant = self.cliche(egales)
        message = self.refus(lambda: tasks.stage_task(str(egales), "T-1", "x"), "migrate_store")
        self.assertEqual(self.cliche(egales), avant)
        self.sans_commande_destructive(message)
        lignes = [ligne for ligne in message.splitlines() if ligne.startswith("python3 -c ")]
        self.assertEqual(len(lignes), 1, message)
        fait = subprocess.run(shlex.split(lignes[0]), capture_output=True, text=True, cwd=str(self.base),
                              env=env_enfant(self.base), timeout=120)
        self.assertEqual(fait.returncode, 0, fait.stderr)
        self.assertEqual(tasks.store_form(str(egales)), "dossier")
        tasks.stage_task(str(egales), "T-1", "x")

        f5 = self.base / "f5"
        self.poser({"tasks": [tache("T-9", "revenue")], "sync_correlations": {"op-9": tombee("T-9")}}, f5)
        avant = self.cliche(f5)
        self.refus(lambda: self.migrer(f5), "T-9")
        self.assertEqual((self.cliche(f5), tasks.store_form(str(f5))), (avant, "monolithe"))

        hostile = self.base / "hostile"
        self.poser({"tasks": [tache("../T-1", "évadée")]}, hostile)
        avant = self.cliche(hostile)
        self.refus(lambda: self.migrer(hostile), "../T-1")
        self.assertEqual((self.cliche(hostile), tasks.store_form(str(hostile))), (avant, "monolithe"))


    def test_wd9b_piege_2_un_vieux_tasks_json_a_cote_d_un_dossier_migre(self) -> None:
        """WD9b (angle mort de l'exec-critic, Piège 2 du plan, de bout en bout) : un tasks.py d'AVANT T-1009 lit un board
        migré comme vide et pose à côté un TASKS.json quasi vide (une tâche) ⇒ `load`, un verbe et `migrate_store`
        refusent, le board reste INTACT, et le refus n'imprime AUCUNE commande destructive — la ligne `rm -r` d'avant,
        collée, effaçait le board entier ; la mise de côté de TASKS.json (`mv -n` vers un nom daté), EXÉCUTÉE telle
        quelle, rend le dossier seul, toutes ses tâches, et TASKS.json reste à côté, octet pour octet. Tue
        M-remède-destructif."""
        racine = self.base / "piège 2 it's"
        r = str(racine)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")], "epics": [{"id": "E-01", "titre": "e"}],
                    "sync_correlations": {"op-1": vivante("T-1"), "op-7": tombee("T-7")}}, racine)
        self.migrer(racine)
        vieux = self.poser({"tasks": [tache(ULID_A, "posée par un tasks.py d'avant T-1009")],
                            "sync_correlations": {"op-vieux": vivante(ULID_A)}}, racine)
        avant = self.cliche(racine)
        message = self.refus(lambda: tasks.load(r), ULID_A, "T-1", "T-2", "set TASKS.json aside",
                             "already delivered: V3 may keep them linked")
        self.sans_commande_destructive(message)
        self.commente_ou_garde(message)
        self.sans_commande_destructive(self.refus(lambda: tasks.stage_task(r, "T-1", "x"), "set TASKS.json aside"))
        self.sans_commande_destructive(self.refus(lambda: self.migrer(racine), ULID_A))
        self.assertEqual(self.cliche(racine), avant)
        (ligne,) = [ligne for ligne in message.splitlines()
                    if " mv -n " in ligne and self.source_mv(ligne) == "TASKS.json"]
        rc, err = self.jouer_garde(ligne)
        self.assertEqual(rc, 0, err)
        self.assertEqual((tasks.store_form(r), ids(tasks.load(r))), ("dossier", ["T-1", "T-2"]))
        (de_cote,) = [p for p in (racine / BOARD_REL).iterdir() if p.name.startswith("TASKS.json.mis-de-cote-")]
        self.assertEqual(de_cote.read_bytes(), vieux)

    def _piege_2(self, nom: str) -> tuple[Path, bytes]:
        """Le Piège 2 : un board migré (T-1, T-2), puis un TASKS.json quasi vide posé à côté par un vieux tasks.py."""
        racine = self.base / nom
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")], "epics": [{"id": "E-01", "titre": "e"}],
                    "sync_correlations": {"op-1": vivante("T-1"), "op-7": tombee("T-7")}}, racine)
        self.migrer(racine)
        return racine, self.poser({"tasks": [tache(ULID_A, "posée par un tasks.py d'avant T-1009")],
                                   "sync_correlations": {"op-vieux": vivante(ULID_A)}}, racine)

    def test_wd9c_le_refus_colle_entier_dans_bash_ne_joue_qu_une_alternative(self) -> None:
        """WD9c (T1, clôture fournée 4) : le refus du Piège 2 collé ENTIER dans bash (préfixe du CLI compris), DEUX
        fois, ne joue qu'UNE alternative — TASKS.json mis de côté, les dossiers restent : (forme, ids) = (dossier,
        [T-1, T-2]) — et n'imbrique rien. Avant : des `mv -n` nus sous du texte libre mettaient de côté les DEUX
        formes (board absent). Tue M-garde-retirée."""
        racine, vieux = self._piege_2("piège 2c it's")
        r = str(racine)
        message = self.refus(lambda: tasks.load(r), ULID_A)
        for _passe in range(2):
            self.bash(message)
        self.assertEqual((tasks.store_form(r), ids(tasks.load(r))), ("dossier", ["T-1", "T-2"]))
        de_cote = [p for p in (racine / BOARD_REL).iterdir() if ".mis-de-cote-" in p.name]
        self.assertEqual([p.name.partition(".mis-de-cote-")[0] for p in de_cote], ["TASKS.json"])
        self.assertEqual((de_cote[0].is_file(), de_cote[0].read_bytes()), (True, vieux), "rien d'imbriqué")

    def test_wd9f_un_id_hostile_ne_sort_jamais_brut_dans_le_refus(self) -> None:
        """WD9f (avis MEDIUM de la revue sécurité, clôture fournée 4) : `numeric_id` n'ancre que les chiffres de fin,
        un clone hostile peut poser dans TASKS.json un id — et une clé de corrélation — portant \\r, ESC et U+2028.
        Collé dans un terminal sans bracketed paste, un \\r brut ferait exécuter la suite d'une ligne `# …`. Le refus
        n'en porte AUCUN brut (Cc, Cf, Zl, Zp échappés `\\xNN` / `\\uNNNN`), reste commenté ou gardé, et collé entier
        dans bash ne joue qu'une alternative. Tue M-sans-échappement."""
        racine = self.base / "hostile it's"
        r = str(racine)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]}, racine)
        self.migrer(racine)
        hostile, cle = "T-\r\x1b[2K touch PWN 9", "op-\r\x1b x"
        self.poser({"tasks": [tache(hostile, "posée par un clone hostile")],
                    "sync_correlations": {cle: vivante(hostile)}}, racine)
        message = self.refus(lambda: tasks.load(r), "T-\\x0d\\x1b[2K\\u2028touch PWN 9", "op-\\x0d\\x1b\\u2028x")
        for brut in ("\r", "\x1b", " "):
            self.assertNotIn(brut, message)
        self.commente_ou_garde(message)
        self.bash(message)
        self.assertEqual((tasks.store_form(r), ids(tasks.load(r))), ("dossier", ["T-1", "T-2"]))
        self.assertFalse((self.base / "PWN").exists() or (racine / "PWN").exists())

    def test_wd9d_un_refus_sur_mille_ids_reste_borne(self) -> None:
        """WD9d (N1) : deux formes qui divergent sur ~1 300 ids — 650 seulement dans le dossier, 650 seulement dans
        TASKS.json, 650 différents, 1 300 corrélations — ⇒ chaque liste nomme 20 ids puis « … and N more » ; le refus
        tient sous 4 Ko (avant : plus de 20 Ko). Tue M-liste-non-bornée."""
        r = str(self.root)
        self.poser({"tasks": [tache(f"T-{i}", "x") for i in range(1, 1301)],
                    "sync_correlations": {f"op-{i}": vivante(f"T-{i}") for i in range(1, 1301)}})
        self.migrer()
        self.poser({"tasks": [tache(f"T-{i}", "y") for i in range(651, 1951)],
                    "sync_correlations": {f"op-{i}": vivante(f"T-{i}") for i in range(651, 1951)}})
        message = self.refus(lambda: tasks.load(r), "T-1, T-2, ", "T-1301, ", "T-651, ", "op-1, ")
        self.assertEqual((message.count("… and 630 more"), message.count("… and 1280 more")), (3, 1), message)
        self.assertNotIn("T-21,", message)
        self.assertLess(len(message.encode("utf-8")), 4096, f"{len(message.encode('utf-8'))} octets")
        self.commente_ou_garde(message)

    def test_wd9e_piege_2_avec_intent_o2_les_deux_remedes_au_premier_refus(self) -> None:
        """WD9e (T2, décision S-01M4PNVY23WGEA1HZRX6BZE1MX : ni réimportation ni tombe automatique) : le vieux tasks.py
        a AUSSI laissé l'intent O2 de sa tâche sous sync_outbox/. Le PREMIER refus nomme la tâche seulement dans
        TASKS.json ET la mise de côté gardée de son fichier d'intent ; collé entier dans bash : dossier seul, T-1 et
        T-2, l'outbox vide, et une ÉCRITURE passe (sans le second remède, la clé orpheline la refusait). Avant : le
        fichier d'intent n'était nommé qu'au refus SUIVANT, celui de l'écriture. Tue M-intents-non-nommés."""
        racine, _ = self._piege_2("piège 2e it's")
        r, vieille = str(racine), self.base / "vieux"
        self.poser({"tasks": [tache("T-9", "neuf")]}, vieille)
        neuve = self.nouvelle("posée par un tasks.py d'avant T-1009", vieille)
        (intent,) = (vieille / OUTBOX_REL).iterdir()
        self.poser(json.loads((vieille / TASKS_REL).read_bytes()), racine)
        (racine / OUTBOX_REL).mkdir(parents=True, exist_ok=True)
        shutil.copy2(intent, racine / OUTBOX_REL / intent.name)
        message = self.refus(lambda: tasks.load(r), neuve, intent.name)
        self.commente_ou_garde(message)
        self.assertEqual(len([ligne for ligne in message.splitlines()
                              if " mv -n " in ligne and self.source_mv(ligne) == intent.name]), 1, message)
        self.bash(message)
        self.assertEqual((tasks.store_form(r), ids(tasks.load(r)), self.definitifs(racine)),
                         ("dossier", ["T-1", "T-2"], []))
        tasks.stage_task(r, "T-1", "x")
        (de_cote,) = [p for p in (racine / BOARD_REL).iterdir() if p.name.startswith(f"{intent.name}.mis-de-cote-")]
        self.assertEqual(de_cote.read_bytes(), intent.read_bytes())


class FusionKitEtBoutEnBoutTests(_Racine):
    def test_wd10_deux_clones_fusionnent_des_taches_differentes(self) -> None:
        """WD10 : deux clones d'un board migré et commité ENTIER — `stage` de T-1 ici, `done` de T-2 là ⇒ `git merge`
        rc 0 et `load` == l'union ; la même tâche modifiée sur deux champs VOISINS (`stage` ici, `state` là : la borne
        S-01M4JN56NB05914VWW942W214X) ⇒ CONFLIT sur ce seul fichier. Tue M-un-fichier."""
        ici, la = self.base / "ici", self.base / "la"
        depot_git(ici)
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux"), tache("T-3", "trois")]}, ici)
        self.migrer(ici)
        git(ici, "add", "-A")
        git(ici, "commit", "-q", "-m", "board migré")
        git(self.base, "clone", "-q", str(ici), str(la))
        for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"), ("commit.gpgsign", "false")):
            git(la, "config", cle, valeur)
        tasks.stage_task(str(ici), "T-1", "ici")
        git(ici, "add", "-A")
        git(ici, "commit", "-q", "-m", "stage ici")
        tasks.set_state(str(la), "T-2", "done", stage="fini là")
        git(la, "add", "-A")
        git(la, "commit", "-q", "-m", "done là")
        git(ici, "fetch", "-q", str(la), "main")
        self.assertEqual(git(ici, "merge", "-q", "--no-edit", "FETCH_HEAD", check=False).returncode, 0)
        lu = {t["id"]: (t["state"], t["stage"]) for t in tasks.load(str(ici))["tasks"]}
        self.assertEqual(lu, {"T-1": ("pending", "ici"), "T-2": ("done", "fini là"), "T-3": ("pending", "")})

        tasks.stage_task(str(ici), "T-3", "a")
        git(ici, "add", "-A")
        git(ici, "commit", "-q", "-m", "T-3 ici")
        git(la, "pull", "-q", "--no-rebase", str(ici), "main")
        tasks.set_state(str(la), "T-3", "running")
        git(la, "add", "-A")
        git(la, "commit", "-q", "-m", "T-3 là")
        tasks.stage_task(str(ici), "T-3", "b")
        git(ici, "add", "-A")
        git(ici, "commit", "-q", "-m", "T-3 ici encore")
        git(ici, "fetch", "-q", str(la), "main")
        self.assertNotEqual(git(ici, "merge", "-q", "--no-edit", "FETCH_HEAD", check=False).returncode, 0)
        conflits = git(ici, "diff", "--name-only", "--diff-filter=U").stdout.split()
        self.assertEqual(conflits, [".agents/state/board/tasks/T-3.json"])
        git(ici, "merge", "--abort")

    def test_wd11_kit_sans_agentic_v3(self) -> None:
        """WD11 : racine SANS `agentic_v3/`, SIMULÉE par `mock.patch.object(tasks, "__file__", …)` et `sys.modules`
        purgé des `agentic_v3*` — `migrate_store`, `new`, `done`, `delete` et F5 marchent et RIEN n'importe
        `agentic_v3` (vérifié après). CONTRÔLE : le résolveur trouve le paquet hors simulation, et aucun des deux
        emplacements sous la racine simulée. Tue M-import-v3."""
        kit = self.base / "bac" / "kit"
        faux = kit / ".agents" / "bin" / "tasks.py"
        faux.parent.mkdir(parents=True)
        shutil.copy2(HERE / "record_id.py", faux.parent / "record_id.py")
        resolveur = tasks._RESOLVEUR_V3
        # `ids.py` pris où le paquet `cadre` vit (vendor d'abord), posé au repli du `record_id.py` copié (le kit ne
        # copie pas `vendor_paths.py`) : `<kit>/src/cadre/ledger/ids.py` (S-01M5BXT85VP4JBBMXVXR9STP5F).
        (kit / "src" / "cadre" / "ledger").mkdir(parents=True)
        shutil.copy2(resolveur.exiger(REPO, "cadre") / "ledger" / "ids.py", kit / "src" / "cadre" / "ledger" / "ids.py")
        self.assertIsNotNone(resolveur.dossier_paquet(REPO, "agentic_v3"), "contrôle hors simulation")
        sans_v3 = {k: v for k, v in sys.modules.items() if not k.startswith("agentic_v3")}
        r, board = str(self.root), self.root / BOARD_REL
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]})
        with mock.patch.dict(sys.modules, sans_v3, clear=True), mock.patch.object(tasks, "__file__", str(faux)):
            self.assertIsNone(resolveur.dossier_paquet(kit, "agentic_v3"))
            self.assertIn("migrated", tasks.migrate_store(r))
            tid = self.nouvelle("sans v3")
            tasks.set_state(r, "T-1", "done", stage="fini")
            tasks.drain_sync_outbox(r, lambda _intent: True)
            vivant = (board / "tasks" / f"{tid}.json").read_bytes()
            tasks.delete_task(r, tid)
            (board / "tasks" / f"{tid}.json").write_bytes(vivant)
            self.refus(lambda: tasks.stage_task(r, "T-2", "x"), tid)
            tasks.delete_task(r, tid)
            importes = sorted(k for k in sys.modules if k.startswith("agentic_v3"))
        self.assertEqual(importes, [], "agentic_v3 importé sous la simulation")
        self.assertEqual({t["id"]: t["state"] for t in tasks.load(r)["tasks"]}, {"T-1": "done", "T-2": "pending"})

    def test_wd12_le_hook_stores_commite_la_migration(self) -> None:
        """WD12 de bout en bout : dépôt jetable, `migrate_store`, puis la jambe `stores` RÉELLE du hook de `done`
        (`post-task-done-index.sh --commit-section <dépôt> stores`) ⇒ `committed` ; le commit porte `D TASKS.json`,
        chaque enregistrement et la tombe ; `status -- .agents/state` est vide. Tue M-forme-hors-contrat."""
        depot = self.base / "hook"
        depot_git(depot)
        self.poser({"tasks": [tache("T-1", "un")], "epics": [{"id": "E-01", "titre": "e"}],
                    "sync_correlations": {"op-1": vivante("T-1"), "op-7": tombee("T-7")}}, depot)
        git(depot, "add", "-A")
        git(depot, "commit", "-q", "-m", "monolithe")
        self.migrer(depot)
        env = {k: v for k, v in env_enfant(self.base).items()}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        p = subprocess.run(["bash", str(HERE / "post-task-done-index.sh"), "--commit-section", str(depot), "stores"],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(p.stdout.strip().splitlines()[-1:], ["committed"], p.stdout + p.stderr)
        noms = git(depot, "show", "--name-status", "--format=", "HEAD").stdout.splitlines()
        attendus = {"D\t.agents/state/board/TASKS.json", "A\t.agents/state/board/tasks/T-1.json",
                    "A\t.agents/state/board/tasks/T-7.json", "A\t.agents/state/board/epics/E-01.json"}
        self.assertEqual(attendus - set(noms), set(), noms)
        self.assertEqual(git(depot, "status", "--porcelain", "--untracked-files=all", "--", ".agents/state").stdout, "")


class RetentionEtPlafondTests(_Racine):
    def test_wd13_purge_pose_une_tombe_par_tache_et_ne_compacte_rien(self) -> None:
        """WD13 (rétention, intérim) : en forme dossier, `purge --before` pose une TOMBE par tâche purgée (ses clés de
        suppression dedans) et ne retire AUCUNE tombe, même vieille de plus de 182 jours ; un fichier sous
        `board/archive/`, une ligne de `board/tombes.jsonl` et `board/retention.json` ne changent ni `load` ni
        `store_form`, et la purge ne les touche pas. Tue M-purge-sans-tombe, M-compaction-précoce."""
        r, board = str(self.root), self.root / BOARD_REL
        vieux = "2025-01-01"
        self.poser({"tasks": [tache(f"T-{n}", f"t{n}", state="done", updated=vieux) for n in (1, 2, 3)]
                    + [tache("T-4", "vivante")], "sync_correlations": {"op-9": tombee("T-9")}})
        self.migrer()
        reference = (tasks.load(r)["tasks"], tasks.store_form(r))
        (board / "archive" / "tasks").mkdir(parents=True)
        reserves = {board / "archive" / "tasks" / "T-5.json": canon({"format": 1, "id": "T-5", "record": tache(
                        "T-5", "archivée", state="done"), "sync_operations": []}),
                    board / "tombes.jsonl": b'{"id": "T-8", "sync_operations": ["op-8"]}\n',
                    board / "retention.json": b'{"archive_apres_jours": 30}\n'}
        for chemin, octets in reserves.items():
            chemin.write_bytes(octets)
        self.assertEqual((tasks.load(r)["tasks"], tasks.store_form(r)), reference)
        self.assertIn("purged 3", tasks.purge_tasks(r, before="2026-01-01"))
        for n in (1, 2, 3):
            tombe = self.enregistrement(f"T-{n}")
            self.assertIsNone(tombe["record"], f"T-{n}")
            self.assertEqual(len(tombe["sync_operations"]), 1, f"T-{n} : sa clé de suppression")
        self.assertEqual(self.enregistrement("T-9"), {"format": 1, "id": "T-9", "record": None,
                                                      "sync_operations": ["op-9"]})
        self.assertEqual({chemin: chemin.read_bytes() for chemin in reserves}, reserves)
        self.assertEqual(ids(tasks.load(r)), ["T-4"])

    def board_purgeable(self, racine: Path, dossier: bool, done: int = 51, pending: int = 51) -> None:
        self.poser({"tasks": [tache(f"T-{n}", f"fait {n}", state="done", updated="2026-01-01") for n in range(1, done + 1)]
                    + [tache(f"T-{100 + n}", f"attente {n}") for n in range(1, pending + 1)]}, racine)
        if dossier:
            self.migrer(racine)

    def test_wd13b_plafond_de_purge_aux_deux_formes(self) -> None:
        """WD13b (S-01M4NFRZS1XK1BEQVGH43Z3EDN), aux DEUX formes : (i) PAR LA CLI, `purge` sans `--plafond` sur 51
        tâches `done` ⇒ rc ≠ 0, stderr « above the per-call cap of 50 » et 51, board et outbox identiques ; (ii)
        `purge --plafond 51` ⇒ « purged 51 » ; (iii) 50 sans option ⇒ passe ; (iv) `purge --dry-run` sur 51 ⇒ rc 0,
        « would remove 51 » et « would be refused », rien d'écrit ; (v) `--plafond 0` PAR LA CLI (argparse rend l'entier
        0, la fonction le refuse : rc ≠ 0) et, en direct, 0, -1, "50", 2.5, True ⇒ refus nommé ;
        (vi) `purge_tasks(root)` direct sur 51 ⇒ `BoardError` ; (vii) réserve C1 : `purge --state pending` sur 51
        `pending`, sans `--plafond`, PAR LA CLI ⇒ refus nommé, board et outbox intacts. Tue M-sans-plafond,
        M-plafond-décalé, M-dry-run-refuse, M-écrit-avant-refus, M-argparse-None ((i) seul), M-dispatch-oublié ((ii)),
        M-plafond-done-seul ((vii))."""
        for dossier in (False, True):
            racine = self.base / f"purge-{'dossier' if dossier else 'monolithe'}"
            r = str(racine)
            self.board_purgeable(racine, dossier)
            with self.subTest(forme="dossier" if dossier else "monolithe"):
                avant = self.cliche(racine)
                p = self.cli("purge", racine=racine)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertIn("above the per-call cap of 50", p.stderr)
                self.assertIn("51", p.stderr)
                self.assertIn("--plafond 51", p.stderr)
                self.assertEqual((self.cliche(racine), self.definitifs(racine)), (avant, []))
                p = self.cli("purge", "--state", "pending", racine=racine)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertIn("above the per-call cap of 50", p.stderr)
                self.assertEqual((self.cliche(racine), self.definitifs(racine)), (avant, []))
                sortie = io.StringIO()
                with contextlib.redirect_stdout(sortie):
                    rc = tasks.main(["--root", r, "purge", "--dry-run"])
                self.assertEqual(rc, 0)
                self.assertIn("would remove 51", sortie.getvalue())
                self.assertIn("would be refused", sortie.getvalue())
                self.refus(lambda: tasks.purge_tasks(r), "above the per-call cap of 50", "51")
                for valeur in (0, -1, "50", 2.5, True):
                    self.refus(lambda: tasks.purge_tasks(r, plafond=valeur), "plafond")
                p = self.cli("purge", "--plafond", "0", racine=racine)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertIn("--plafond expects a whole number", p.stderr)
                self.assertEqual((self.cliche(racine), self.definitifs(racine)), (avant, []))
                p = self.cli("purge", "--plafond", "51", racine=racine)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("purged 51", p.stdout)
                self.assertEqual(len(tasks.load(r)["tasks"]), 51)
        for dossier in (False, True):
            racine = self.base / f"cinquante-{'dossier' if dossier else 'monolithe'}"
            self.board_purgeable(racine, dossier, done=50, pending=0)
            self.assertIn("purged 50", tasks.purge_tasks(str(racine)))


@unittest.skipIf(os.name == "nt", "liens symboliques : POSIX")
class AvisSecuriteTests(_Racine):
    """Avis de la revue de sécurité de T-00001009 : dossiers en lien symbolique, lot trop profond, garde de commit à
    l'unlink de `migrate_store`. Chaque garde est jouée SEULE (appel direct), pour qu'un mutant qui en retire une ne
    soit pas couvert par une autre."""

    def lien(self, dossier: Path, cible: Path) -> None:
        if dossier.exists():
            dossier.rename(cible)
        else:
            cible.mkdir(parents=True)
        dossier.parent.mkdir(parents=True, exist_ok=True)
        dossier.symlink_to(cible, target_is_directory=True)

    def contenu(self, dossier: Path) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in dossier.iterdir()}

    def test_wd14_un_dossier_d_enregistrements_en_lien_est_refuse(self) -> None:
        """WD14 : `board/tasks/` remplacé par un LIEN vers un dossier hors du board ⇒ `store_form`, `read_records`,
        un verbe, `_save_dossier` (données chargées avant, `vue_dossier` présente) et la reprise d'un lot
        (`_appliquer_lot_dossier`) refusent nommément ; RIEN n'est écrit dans la cible du lien, aucun lot ne reste.
        Tue M-lien-store-form, M-lien-lecture, M-lien-save, M-lien-reprise."""
        r, board = str(self.root), self.root / BOARD_REL
        self.poser({"tasks": [tache("T-1", "un"), tache("T-2", "deux")]})
        self.migrer()
        d = tasks.load(r)
        d["tasks"][0]["stage"] = "par le lien"
        ailleurs = self.base / "ailleurs"
        self.lien(board / "tasks", ailleurs)
        avant = self.contenu(ailleurs)
        self.refus(lambda: tasks.store_form(r), "symbolic link")
        self.refus(lambda: tasks.read_records(board, TACHES), "symbolic link")
        self.refus(lambda: tasks.stage_task(r, "T-1", "x"), "symbolic link")
        self.refus(lambda: tasks._save_dossier(r, d), "symbolic link")
        lots = self.root / LOTS_REL
        self.assertFalse(lots.is_dir() and any(lots.iterdir()), "un lot a été écrit avant le refus")
        contenu = {"forme": "dossier", "intents": [], "enregistrements": {"tasks/T-2.json": {
            "format": 1, "id": "T-2", "record": tache("T-2", "deux", stage="par le lien"), "sync_operations": []}}}
        lots.mkdir(parents=True, exist_ok=True)
        (lots / "00000000000000000001.json").write_text(json.dumps(dict(contenu, cible=tasks._empreinte_lot(contenu))),
                                                        encoding="utf-8")
        self.refus(lambda: tasks._reprendre_lots(r), "symbolic link")
        self.assertEqual(self.contenu(ailleurs), avant, "écrit hors du board, à travers le lien")

    def test_wd14b_les_dossiers_de_lots_et_de_staging_en_lien_sont_refuses(self) -> None:
        """WD14b : le dossier LOCAL des lots en lien ⇒ un verbe en forme dossier refuse, aucun lot écrit dans la cible ;
        le dossier de staging de `migrate_store` en lien ⇒ la migration refuse, rien écrit dans la cible, le monolithe
        reste. Tue M-lien-lots, M-lien-staging."""
        r = str(self.root)
        self.poser({"tasks": [tache("T-1", "un")]})
        self.migrer()
        cible_lots = self.base / "lots ailleurs"
        self.lien(self.root / LOTS_REL, cible_lots)
        self.refus(lambda: tasks.stage_task(r, "T-1", "x"), "symbolic link")
        self.assertEqual(self.contenu(cible_lots), {})
        mono = self.base / "mono"
        octets = self.poser({"tasks": [tache("T-1", "un")]}, mono)
        cible_stage = self.base / "staging ailleurs"
        self.lien(mono / ".agents" / "state" / "local" / "board-staging", cible_stage)
        self.refus(lambda: self.migrer(mono), "symbolic link")
        self.assertEqual(self.contenu(cible_stage), {})
        self.assertEqual(((mono / TASKS_REL).read_bytes(), tasks.store_form(str(mono))), (octets, "monolithe"))

    def test_wd14c_migrate_store_refuse_un_dossier_de_lots_en_lien(self) -> None:
        """WD14c (T4, clôture fournée 4) : le dossier LOCAL des lots en lien (forme de WD14b) ⇒ `migrate_store` refuse
        nommément AVANT tout geste : la cible du lien reste vide, TASKS.json intact, forme `monolithe`, aucun dossier
        d'enregistrements. Tue M-lien-lots-migration (`lots=True` retiré du `_refus_liens` de `migrate_store`)."""
        octets = self.poser({"tasks": [tache("T-1", "un")]})
        cible_lots = self.base / "lots ailleurs"
        self.lien(self.root / LOTS_REL, cible_lots)
        self.refus(lambda: self.migrer(), "symbolic link")
        self.assertEqual(self.contenu(cible_lots), {})
        self.assertEqual(((self.root / TASKS_REL).read_bytes(), tasks.store_form(str(self.root))),
                         (octets, "monolithe"))
        self.assertFalse((self.root / BOARD_REL / "tasks").exists())

    def test_wd15_un_lot_trop_profond_n_est_pas_valide_et_ne_bloque_pas_load(self) -> None:
        """WD15 : un lot local dont l'empreinte lève `RecursionError` (imbrication trop profonde) n'est PAS validé —
        `_lot_dossier_valide` rend faux, `load` vit, le lot n'est pas appliqué. CONTRÔLE : le même lot sans la levée
        est valide. Tue M-recursion-avalee-pas (RecursionError retiré de l'except)."""
        r = str(self.root)
        self.poser({"tasks": [tache("T-1", "un")]})
        self.migrer()
        contenu = {"forme": "dossier", "intents": [], "enregistrements": {"tasks/T-1.json": {
            "format": 1, "id": "T-1", "record": tache("T-1", "un", stage="profond"), "sync_operations": []}}}
        lot = dict(contenu, cible=tasks._empreinte_lot(contenu))
        self.assertTrue(tasks._lot_dossier_valide(lot), "contrôle : le lot est valide")
        lots = self.root / LOTS_REL
        lots.mkdir(parents=True)
        (lots / "00000000000000000001.json").write_text(json.dumps(lot), encoding="utf-8")
        with mock.patch.object(tasks, "_empreinte_lot", side_effect=RecursionError("trop profond")):
            self.assertFalse(tasks._lot_dossier_valide(lot))
            self.assertEqual(stages(tasks.load(r)), {"T-1": ""})

    def test_wd15b_un_lot_dossier_sur_un_board_sans_dossier_va_en_quarantaine(self) -> None:
        """WD15b (N2, clôture fournée 4) : les dossiers mis de côté (TASKS.json était le bon côté), un lot VALIDÉ de la
        forme dossier resté sous les lots locaux ⇒ un verbe ne le rejoue PAS — il recréerait `board/tasks/` et
        rouvrirait les deux formes — : le lot va en quarantaine, nommé sur stderr, le board reste `monolithe` et le
        verbe s'applique. Tue M-lot-dossier-sans-forme (la condition de forme retirée)."""
        r, board = str(self.root), self.root / BOARD_REL
        self.poser({"tasks": [tache("T-1", "un")]})
        self.migrer()
        self.poser({"tasks": [tache("T-1", "un")]})
        (board / "tasks").rename(board / "tasks.mis-de-cote-20261012T000000Z")
        contenu = {"forme": "dossier", "intents": [], "enregistrements": {"tasks/T-1.json": {
            "format": 1, "id": "T-1", "record": tache("T-1", "un", stage="par le lot"), "sync_operations": []}}}
        lots = self.root / LOTS_REL
        lots.mkdir(parents=True, exist_ok=True)
        (lots / "00000000000000000001.json").write_text(json.dumps(dict(contenu, cible=tasks._empreinte_lot(contenu))),
                                                        encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tasks.stage_task(r, "T-1", "x")
        self.assertFalse((board / "tasks").exists(), "le lot a recréé board/tasks/")
        self.assertEqual((tasks.store_form(r), stages(tasks.load(r))), ("monolithe", {"T-1": "x"}))
        self.assertEqual(list(lots.iterdir()) if lots.is_dir() else [], [])
        self.assertEqual([p.name for p in (self.root / QUARANTAINE_REL).iterdir()], ["00000000000000000001.json"])
        self.assertIn("00000000000000000001.json", err.getvalue())

    def test_wd16_migrate_store_demande_la_garde_avant_l_unlink(self) -> None:
        """WD16 : `migrate_store` demande la garde de commit (`guard_board_commit`) AVANT l'unlink de TASKS.json —
        point de validation — : une garde qui accepte les deux renommages de dossiers puis refuse ⇒ `BoardError`, les
        dossiers retirés, TASKS.json intact, forme `monolithe` ; aux deux formes égales, la garde qui refuse ⇒ la
        migration ne finit pas. Tue M-unlink-sans-garde, M-unlink-deux-formes-sans-garde."""
        r = str(self.root)
        octets = self.poser({"tasks": [tache("T-1", "un")], "epics": [{"id": "E-01", "titre": "e"}]})
        appels: list[int] = []

        def garde() -> bool:
            appels.append(1)
            return len(appels) <= 2

        with tasks.guard_board_commit(garde):
            self.refus(lambda: self.migrer(), "commit guard")
        self.assertEqual(len(appels), 3, "le refus doit venir de la garde demandée à l'unlink")
        self.assertEqual(((self.root / TASKS_REL).read_bytes(), tasks.store_form(r)), (octets, "monolithe"))
        self.assertFalse((self.root / BOARD_REL / "tasks").exists() or (self.root / BOARD_REL / "epics").exists())
        self.migrer()
        self.poser({"tasks": [tache("T-1", "un")], "epics": [{"id": "E-01", "titre": "e"}]})
        with tasks.guard_board_commit(lambda: False):
            self.refus(lambda: self.migrer(), "commit guard")
        self.assertEqual(tasks.store_form(r), "les deux")


if __name__ == "__main__":
    unittest.main()
