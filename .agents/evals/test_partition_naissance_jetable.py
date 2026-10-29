#!/usr/bin/env python3
"""T-00000753 — la NAISSANCE d'une partition d'état pour une racine JETABLE est refusée
quand `CADRE_STATE_DIR` est absent, par chacun des NEUF créateurs nommés ci-dessous
(mesure C du plan T-00000753, S-00003815 : neuf créateurs du paquet naissaient une
partition pour une racine posée sous un dossier temporaire).

Cinq familles : le prédicat PUR (chaque zone, chaque borne, chaque levée évitée) ; les
créateurs EN PROCESSUS (une ligne par créateur, refus ET témoin positif isolé : un « 0
partition » sans témoin positif ne distingue pas « refusé » de « n'a pas tourné »), plus les
deux filtres du garde de store ; deux canaux DE BOUT EN BOUT (`tasks.py`, `agentic_v3
resume`) ; un RECENSEMENT des appels qui créent un dossier dans `agentic_v3/` ; le bloc
d'isolation des quatre suites bash qui naissaient une partition en lancement direct.
Chaque test tourne sous un HOME, un TMPDIR et un état jetables : un défaut du correctif
naît sa partition SOUS `<t>/`, jamais sous le vrai `~/.local/state/cadre`.

BORNES, écrites :
  * le recensement lit les fichiers `.py` SUIVIS du paquet V3 résolu (à la racine
    ou sous `.agents/vendor/`), hors `tests/`, et conserve leurs noms logiques
    `agentic_v3/…` dans la liste close des sites ;
    (`git ls-files`) : un fichier neuf n'y entre qu'après `git add` ; il ne voit ni
    `migrate_index_to_db`, ni `project_init`, ni `src/cadre/`, que la tâche NOMME hors
    périmètre ;
  * il reconnaît les GRAPHIES d'appel dont le nom appelé est `mkdir` ou `makedirs` — en
    attribut (`x.parent.mkdir(...)`, `partition.mkdir(...)`, `os.mkdir(...)`,
    `os.makedirs(...)`) ou nu (`makedirs(...)` importé) ; il ne voit PAS un dossier créé par
    un autre nom (`Workspace`, `os.open`, `shutil.copytree`, un sous-processus) ;
  * le prédicat compare des chaînes après `realpath` : sur un système de fichiers
    insensible à la casse, une racine tapée dans une autre casse que sa zone n'est pas
    refusée (ouvert-échec, dit par le module).
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path, PureWindowsPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_partition_naissance_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "agentic_v3")
#: Parent du paquet `cadre` que la règle désigne (`.agents/vendor`, sinon `src`) : EN QUEUE, comme le conftest.
PARENT_CADRE = _VENDOR.exiger(ROOT, "cadre").parent
_VENDOR.ajouter_en_queue(PARENT_CADRE)


def test_provenance_v3_en_processus():
    attendu = _VENDOR.exiger(ROOT, "agentic_v3")
    assert Path(sys.modules["agentic_v3"].__file__).resolve().parent == attendu.resolve()

POSIX = os.name == "posix"
VARIABLES_D_ETAT = ("CADRE_STATE_DIR", "XDG_STATE_HOME", "CADRE_PROJECT_ROOT", "CLAUDE_PROJECT_DIR")
REFUS = ("EmplacementRefuse", "StoreV3Refuse")  # `refus_nomme` renomme le second pour trois constructeurs


def dossier_v3() -> Path:
    from agentic_v3.db import run_export

    return run_export._vendor_paths().exiger(ROOT, "agentic_v3")


def np():
    from agentic_v3.db import naissance_partition

    return naissance_partition


def nombre(base: Path) -> int:
    projets = base / "projets"
    return sum(1 for e in projets.iterdir() if e.is_dir()) if projets.is_dir() else 0


class _Bac(unittest.TestCase):
    """`t/home` et `t/zone` sont DISJOINTS : une zone qui contient le domicile n'est pas
    retenue (borne du prédicat), donc le domicile jetable ne doit pas être sous la zone."""

    def setUp(self) -> None:
        self.t = Path(os.path.realpath(tempfile.mkdtemp(prefix="t753_")))
        self.addCleanup(shutil.rmtree, str(self.t), True)
        for d in ("home", "zone", "ev"):
            (self.t / d).mkdir()
        self.racine = self.t / "zone" / "racine"
        (self.racine / ".agents").mkdir(parents=True)

    def etat_defaut(self) -> Path:
        return self.t / "home" / ".local" / "state" / "cadre"

    def env(self, **plus: str) -> dict:
        # GIT_CEILING_DIRECTORIES : sans lui un `<t>` posé sous un arbre git se résout à cet
        # arbre, et le témoin rougit pour une raison étrangère au correctif.
        env = {k: v for k, v in os.environ.items()
               if k not in VARIABLES_D_ETAT and not k.startswith("GIT_")}
        env.update(HOME=str(self.t / "home"), TMPDIR=str(self.t / "zone"),
                   GIT_CEILING_DIRECTORIES=str(self.t), AGENTS_EVENTS_DIR=str(self.t / "ev"),
                   PYTHONPATH=os.pathsep.join((str(dossier_v3().parent), str(PARENT_CADRE))))
        env.update(plus)
        return env


class TestPredicatPur(unittest.TestCase):
    DOMICILE = "/home/user"

    def refus(self, racine, *, environ=None, zones=None, temporaire=lambda: "/inexistant-gt"):
        return np().refus_naissance(racine, environ={} if environ is None else environ,
                                    zones=zones, domicile=self.DOMICILE, temporaire=temporaire)

    def test_le_repli_cwd_de_gettempdir_n_est_pas_une_zone(self) -> None:
        # `gettempdir()` retombe sur le cwd quand aucun dossier n'est inscriptible
        cwd = os.path.realpath(os.getcwd())
        self.assertNotIn(cwd, np().zones_temporaires({}, temporaire=os.getcwd))
        self.assertIn(cwd, np().zones_temporaires({"TMPDIR": cwd}, temporaire=os.getcwd))

    def test_chaque_zone_par_defaut_a_son_temoin(self) -> None:
        lignes = [
            ("gettempdir", {}, lambda: "/zz/gt", "/zz/gt/p"),
            ("TMPDIR", {"TMPDIR": "/zz/a"}, None, "/zz/a/p"),
            ("TEMP", {"TEMP": "/zz/b"}, None, "/zz/b/p"),
            ("TMP", {"TMP": "/zz/c"}, None, "/zz/c/p"),
            ("/tmp", {}, None, "/tmp/x/p"),
            ("/var/tmp", {}, None, "/var/tmp/x/p"),
            ("/var/folders", {}, None, "/var/folders/ab/T/p"),
        ]
        for nom, environ, temporaire, racine in lignes:
            with self.subTest(zone=nom):
                kw = {"temporaire": temporaire} if temporaire else {}
                self.assertIn("REFUSÉE", self.refus(racine, environ=environ, **kw) or "")

    def test_hors_zone_isolation_et_bornes(self) -> None:
        self.assertIsNone(self.refus("/srv/app"))
        self.assertIsNone(self.refus("/tmp/x", environ={"CADRE_STATE_DIR": "/e"}))
        self.assertIn("REFUSÉE", self.refus("/tmp/x", environ={"CADRE_STATE_DIR": "  "}) or "")
        self.assertIsNone(self.refus("/home/user/proj", environ={"TMPDIR": "/"}))
        self.assertIsNone(self.refus("/home/user/proj", environ={"TMPDIR": "/home"}))
        self.assertIsNone(self.refus("/home/user/proj", environ={"TMPDIR": "/home/user"}))

    def test_XDG_STATE_HOME_n_isole_pas(self) -> None:
        # `XDG_STATE_HOME` est l'état RÉEL d'un poste XDG, jamais une isolation de banc.
        self.assertFalse(np().isole({"XDG_STATE_HOME": "/e"}))
        self.assertIn("REFUSÉE", self.refus("/tmp/x", environ={"XDG_STATE_HOME": "/e"}) or "")

    def test_une_zone_illisible_ne_masque_pas_les_autres_et_le_predicat_ne_leve_jamais(self) -> None:
        self.assertIn("REFUSÉE", self.refus("/tmp/x", zones=[None, "/tmp"]) or "")
        for brut in (object(), None, "a\0b", b"\xff"):
            with self.subTest(racine=repr(brut)):
                self.assertIsNone(self.refus(brut))

    def test_la_comparaison_ne_leve_pas_entre_lecteurs_windows(self) -> None:
        sous = np()._sous
        self.assertFalse(sous("D:\\work\\repo", "C:\\Users\\user\\AppData\\Local\\Temp", PureWindowsPath))
        self.assertTrue(sous("c:\\users\\USER\\appdata\\local\\temp\\a",
                             "C:\\Users\\user\\AppData\\Local\\Temp", PureWindowsPath))

    @unittest.skipUnless(POSIX, "lien symbolique")
    def test_une_racine_atteinte_par_un_lien_est_jugee_sur_sa_cible(self) -> None:
        with tempfile.TemporaryDirectory() as brut:
            t = Path(os.path.realpath(brut))
            (t / "zone" / "p").mkdir(parents=True)
            os.symlink(t / "zone", t / "lien")
            self.assertIn("REFUSÉE", self.refus(t / "lien" / "p", zones=[str(t / "zone")]) or "")


def _sondes():
    from agentic_v3.checkpoints.session_checkpoint import SessionCheckpointManager
    from agentic_v3.db import run_export
    from agentic_v3.db.event_store import EventStore
    from agentic_v3.db.lessons_store import LessonsStore
    from agentic_v3.db.schema import get_db_connection
    from agentic_v3.ingestion.parse_specs import SpecParser

    def verrou(r, t):
        with run_export._verrou_export(depuis=r):
            pass

    def append(r, t):
        EventStore(db_path=t / "v3.db", project_root=r).append_event(
            "T-SONDE", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op-sonde")

    # (appel, cwd) : `True` = le cwd EST la racine (créateurs à zéro argument) ; `False` = la racine
    # est EXPLICITE et le cwd ailleurs — sans quoi un créateur qui ignore la racine passée (mutant
    # M10f : `create_tables(self.db_path)` sans `racine=`) retomberait par hasard sur la bonne.
    return {
        "EventStore(racine)": (lambda r, t: EventStore(project_root=r), False),
        "EventStore(db explicite).append_event [journal d'attente]": (append, False),
        "SessionCheckpointManager()": (lambda r, t: SessionCheckpointManager(), True),
        "LessonsStore()": (lambda r, t: LessonsStore(), True),
        "SpecParser()": (lambda r, t: SpecParser(), True),
        "get_db_connection()": (lambda r, t: get_db_connection(), True),
        "identifiant_de_copie": (lambda r, t: run_export.identifiant_de_copie(depuis=r), False),
        "_verrou_export": (verrou, False),
        "preparer_journal_attente": (lambda r, t: run_export.preparer_journal_attente(
            "01ARZ3NDEKTSV4RRFFQ69G5FAV", depuis=r), False),
    }


@unittest.skipUnless(POSIX, "HOME et TMPDIR posés par l'environnement : POSIX")
class TestCreateursEnProcessus(_Bac):
    def lance(self, sonde, *, isole: bool, cwd_racine: bool = True, **plus: str):
        with contextlib.ExitStack() as pile:
            pile.enter_context(mock.patch.dict(os.environ, {"HOME": str(self.t / "home"),
                                                            "TMPDIR": str(self.t / "zone"),
                                                            "GIT_CEILING_DIRECTORIES": str(self.t),
                                                            "AGENTS_EVENTS_DIR": str(self.t / "ev")}))
            for nom in [k for k in os.environ if k in VARIABLES_D_ETAT or (k.startswith("GIT_") and k != "GIT_CEILING_DIRECTORIES")]:
                os.environ.pop(nom)
            os.environ.update(plus)
            if isole:
                os.environ["CADRE_STATE_DIR"] = str(self.t / "etat")
            pile.enter_context(mock.patch.object(tempfile, "tempdir", str(self.t / "zone")))
            pile.enter_context(contextlib.chdir(self.racine if cwd_racine else self.t))
            pile.enter_context(contextlib.redirect_stderr(io.StringIO()))
            try:
                sonde(self.racine, self.t)
            except BaseException as exc:  # noqa: BLE001 — on RAPPORTE la classe
                return exc
        return None

    def test_chaque_createur_refuse_sans_isolation_et_naitre_avec(self) -> None:
        for nom, (sonde, cwd_racine) in _sondes().items():
            with self.subTest(createur=nom, bras="sans isolation"):
                exc = self.lance(sonde, isole=False, cwd_racine=cwd_racine)
                self.assertIn(type(exc).__name__, REFUS, f"{nom} : {exc!r}")
                self.assertIn("CADRE_STATE_DIR", str(exc))
                self.assertEqual(nombre(self.etat_defaut()), 0)
            with self.subTest(createur=nom, bras="CADRE_STATE_DIR posé (témoin positif)"):
                exc = self.lance(sonde, isole=True, cwd_racine=cwd_racine)
                self.assertNotIn(type(exc).__name__, REFUS, f"{nom} : {exc!r}")
                self.assertGreaterEqual(nombre(self.t / "etat"), 1)
                shutil.rmtree(self.t / "etat", ignore_errors=True)

    def test_CADRE_PROJECT_ROOT_gagne_sur_depuis(self) -> None:
        # la partition est clé sur `project_root(depuis)`, où `$CADRE_PROJECT_ROOT` gagne : la garde juge
        # la MÊME racine (mutant M14 : elle jugerait `depuis`, ici HORS zone, et ne refuserait rien).
        from agentic_v3.db import run_export

        exc = self.lance(lambda r, t: run_export.identifiant_de_copie(depuis=t / "home"), isole=False,
                         CADRE_PROJECT_ROOT=str(self.racine))
        self.assertIn(type(exc).__name__, REFUS, repr(exc))
        self.assertEqual(nombre(self.etat_defaut()), 0)

    def test_XDG_STATE_HOME_pose_n_isole_pas_un_createur(self) -> None:
        from agentic_v3.db.event_store import EventStore

        xdg = self.t / "xdg"
        exc = self.lance(lambda r, t: EventStore(project_root=r), isole=False, cwd_racine=False,
                         XDG_STATE_HOME=str(xdg))
        self.assertIn(type(exc).__name__, REFUS, repr(exc))
        self.assertEqual(nombre(xdg / "cadre"), 0)
        self.assertEqual(nombre(self.etat_defaut()), 0)

    def test_le_garde_de_store_ne_resout_rien_hors_du_chemin_par_defaut(self) -> None:
        # Filtre de NOM de `garder_store` : seul `<…>/run/v3_event_store.db` est jugé ; ailleurs
        # le garde sort AVANT toute résolution de partition (chemin chaud de `get_db_connection`).
        from agentic_v3.db import run_export

        for base in (Path("zone", "neuf", "run", "base.db"), Path("zone", "neuf", "autre", "v3_event_store.db")):
            with self.subTest(base=str(base)):
                with mock.patch.object(run_export, "state_project", return_value=self.t / "ailleurs") as resolu:
                    exc = self.lance(lambda r, t: np().garder_store(t / base, r), isole=False)
                self.assertIsNone(exc)
                resolu.assert_not_called()

    def test_une_base_explicite_hors_de_la_partition_de_sa_racine_n_est_pas_refusee(self) -> None:
        # Filtre d'AUTRE RACINE de `garder_store` : une base au chemin de forme par défaut mais
        # hors de la partition de SA racine ne fait naître aucune partition — elle n'est pas jugée.
        from agentic_v3.db.schema import create_tables

        base = self.t / "zone" / "neuf" / "run" / "v3_event_store.db"
        exc = self.lance(lambda r, t: create_tables(base, racine=r), isole=False)
        self.assertIsNone(exc, repr(exc))
        self.assertTrue(base.is_file())
        self.assertEqual(nombre(self.etat_defaut()), 0)


@unittest.skipUnless(POSIX, "HOME et TMPDIR posés par l'environnement : POSIX")
class TestDeBoutEnBout(_Bac):
    def sh(self, argv, env, cwd=ROOT):
        return subprocess.run([str(a) for a in argv], cwd=str(cwd), env=env, capture_output=True,
                              text=True, timeout=120)

    def tasks(self, env, *verbe):
        return self.sh([sys.executable, ROOT / ".agents" / "bin" / "tasks.py", "--root", self.racine, *verbe], env)

    def test_cli_enfant_recoit_le_parent_reel_du_paquet_v3(self) -> None:
        from agentic_v3.db import run_export

        attendu = run_export._vendor_paths().exiger(ROOT, "agentic_v3").parent
        recu = Path(self.env()["PYTHONPATH"].split(os.pathsep)[0])
        self.assertEqual(recu, attendu)

    def test_cli_enfant_recoit_le_parent_que_la_regle_designe_pour_cadre(self) -> None:
        # lot R de T-01M5BXTPQE3JZV3KZA6WD9P5XC : jamais `ROOT/src` en dur (rouge en vendor seul)
        recu = Path(self.env()["PYTHONPATH"].split(os.pathsep)[1])
        self.assertEqual(recu, _VENDOR.parent_import(ROOT, "cadre"))

    def setUp(self) -> None:
        super().setUp()
        shutil.rmtree(self.racine)  # le banc `tasks.py` part d'une racine NUE, comme les suites bash
        self.racine.mkdir()

    def test_tasks_new_sur_racine_jetable_refuse_annonce_et_ne_cree_rien(self) -> None:
        r = self.tasks(self.env(), "new", "sonde W1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REFUSÉ (emplacement", r.stderr)
        self.assertIn("CADRE_STATE_DIR", r.stderr)
        self.assertIn("sonde W1", self.tasks(self.env(), "list").stdout)  # le board est ÉCRIT
        self.assertEqual(nombre(self.etat_defaut()), 0)

    def test_meme_appel_avec_CADRE_STATE_DIR_naitre_sous_l_etat_isole(self) -> None:
        env = self.env(CADRE_STATE_DIR=str(self.t / "etat"))
        r = self.tasks(env, "new", "sonde W2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("REFUSÉ", r.stderr)
        self.assertEqual(nombre(self.t / "etat"), 1)
        self.assertEqual(nombre(self.etat_defaut()), 0)

    def test_une_partition_preexistante_est_adoptee_jamais_refusee(self) -> None:
        (self.racine / ".agents").mkdir()  # `state_project` ne résout pas une racine sans marqueur
        code = "import sys; from cadre.paths import state_project; print(state_project(depuis=sys.argv[1]))"
        partition = Path(self.sh([sys.executable, "-c", code, self.racine], self.env()).stdout.strip())
        self.assertEqual(partition.parent, self.etat_defaut() / "projets")
        partition.mkdir(parents=True)
        r = self.tasks(self.env(), "new", "sonde W3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("REFUSÉ", r.stderr)
        self.assertTrue((partition / "run" / "v3_event_store.db").is_file())

    def test_agentic_v3_resume_depuis_une_racine_jetable_rend_4_et_ne_cree_rien(self) -> None:
        (self.racine / ".agents").mkdir()
        refuse = self.sh([sys.executable, "-m", "agentic_v3", "resume"], self.env(), cwd=self.racine)
        self.assertEqual(refuse.returncode, 4, refuse.stderr)
        self.assertIn("CADRE_STATE_DIR", refuse.stderr)
        self.assertEqual(nombre(self.etat_defaut()), 0)
        isole = self.sh([sys.executable, "-m", "agentic_v3", "resume"],
                        self.env(CADRE_STATE_DIR=str(self.t / "etat")), cwd=self.racine)
        self.assertEqual(isole.returncode, 0, isole.stderr)
        self.assertEqual(nombre(self.t / "etat"), 1)


class TestRecensementDesCreateurs(unittest.TestCase):
    """Tout appel `mkdir`/`makedirs` des `.py` SUIVIS de `agentic_v3/` hors `tests/` (graphies et
    portée : docstring du module) appartient à un ensemble CLOS et nommé de HUIT sites : cinq
    gardés — le garde de leur fonction les précède — et trois exemptés. Un neuvième site, de
    n'importe quelle graphie reconnue et dans n'importe quel fichier du paquet, rougit ce banc."""

    APPELS = {"mkdir", "makedirs"}
    GARDES = {"garder_store", "_sonder_partition"}
    #: `_preparer_dossiers_export` crée sous `runs/`, versionné DANS le dépôt : pas l'état machine.
    #: `_dossier_sans_lien` (T-01M5DBFRT546XQVFDQSTBY1KN3) crée `run/v3-auto-sync/` et ses
    #: `backups/` SOUS une partition déjà née (base ouverte), sans `parents=True` : il ne peut
    #: jamais faire naître une partition.
    EXEMPTES = Counter({("agentic_v3/db/run_export.py", "_preparer_dossiers_export"): 2,
                        ("agentic_v3/db/event_store_sync.py", "_dossier_sans_lien"): 1})
    GARDES_ATTENDUS = Counter({
        ("agentic_v3/db/schema.py", "get_db_connection"): 1,
        ("agentic_v3/db/schema.py", "create_tables"): 1,
        ("agentic_v3/db/run_export.py", "identifiant_de_copie"): 1,
        ("agentic_v3/db/run_export.py", "preparer_journal_attente"): 1,
        ("agentic_v3/db/run_export.py", "_verrou_export"): 1,
    })

    @staticmethod
    def _nom_appele(appel: ast.Call) -> str:
        f = appel.func
        return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")

    def _appels(self, arbre: ast.AST):
        """`(fonction englobante la plus proche, nom appelé, ligne)` de chaque appel ;
        `<module>` hors de toute fonction."""
        vus = []

        def visite(noeud, fonction):
            for enfant in ast.iter_child_nodes(noeud):
                if isinstance(enfant, ast.Call):
                    vus.append((fonction, self._nom_appele(enfant), enfant.lineno))
                dedans = enfant.name if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef)) else fonction
                visite(enfant, dedans)

        visite(arbre, "<module>")
        return vus

    def _fichiers(self):
        prefixe = dossier_v3().relative_to(ROOT).as_posix()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        r = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files", "-z", "--", prefixe],
                           cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"git ls-files a échoué : le périmètre est inconnu — {r.stderr}")
        noms = [n for n in r.stdout.split("\0") if n.endswith(".py") and not n.startswith(prefixe + "/tests/")]
        self.assertIn(prefixe + "/db/schema.py", noms, "périmètre vide ou déplacé : le recensement ne lit rien")
        return [("agentic_v3/" + n[len(prefixe) + 1:], n) for n in noms]

    def test_chaque_creation_de_dossier_du_paquet_est_gardee_ou_exemptee(self) -> None:
        sites, gardes = Counter(), {}
        lignes_mkdir = {}
        for rel, disque in self._fichiers():
            arbre = ast.parse((ROOT / disque).read_text(encoding="utf-8"))
            for fonction, nom, ligne in self._appels(arbre):
                cle = (rel, fonction)
                if nom in self.APPELS:
                    sites[cle] += 1
                    lignes_mkdir.setdefault(cle, []).append(ligne)
                elif nom in self.GARDES:
                    gardes.setdefault(cle, []).append(ligne)
        self.assertEqual(sites, self.GARDES_ATTENDUS + self.EXEMPTES,
                         "un appel mkdir/makedirs du paquet a changé : le classer (gardé, ou hors état machine)")
        for cle in self.GARDES_ATTENDUS:
            with self.subTest(site="::".join(cle)):
                avant = gardes.get(cle, [])
                self.assertTrue(avant and min(avant) < min(lignes_mkdir[cle]),
                                f"{cle} : mkdir sans garde avant lui")


class TestSuitesBashIsolentLeurEtat(unittest.TestCase):
    """Les quatre suites qui naissaient une partition en lancement DIRECT posent
    `CADRE_STATE_DIR` sous leur `$TMP` (valeur déjà posée RESPECTÉE), juste après le `trap`
    qui nettoie `$TMP`. Le runner isole déjà : sans ce témoin, retirer le bloc d'une suite ne
    rougirait rien sous la porte."""

    SUITES = (".agents/bin/tasks.test.sh", "core-scripts/plan_waves.test.sh",
              ".claude/hooks/binome-trace.test.sh", ".claude/hooks/context-retro.test.sh")
    TRAP = "trap 'rm -rf \"$TMP\"' EXIT"
    ISOLE = 'if [ -z "${CADRE_STATE_DIR:-}" ]; then export CADRE_STATE_DIR="$TMP/cadre-etat"; fi'

    def test_chaque_suite_isole_son_etat_juste_apres_son_trap(self) -> None:
        for suite in self.SUITES:
            with self.subTest(suite=suite):
                lignes = [l.strip() for l in (ROOT / suite).read_text(encoding="utf-8").splitlines()]
                self.assertEqual(lignes.count(self.TRAP), 1)
                self.assertEqual(lignes.count(self.ISOLE), 1)
                i, j = lignes.index(self.TRAP), lignes.index(self.ISOLE)
                self.assertLess(i, j)
                self.assertTrue(all(l.startswith("#") for l in lignes[i + 1:j]),
                                "seuls des commentaires séparent le trap du bloc d'isolation")


if __name__ == "__main__":
    unittest.main()
