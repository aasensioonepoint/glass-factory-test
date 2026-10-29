#!/usr/bin/env python3
"""T-00001069 — hors isolation, un worktree LIÉ ne fait plus NAÎTRE de partition d'état V3 ;
ses intents board restent dans l'outbox de SA branche et ne rejoignent la partition du principal
QUE si son board est fusionné (plan T-00001069 rév. 1, option C ; décision pilote S-00003484 ;
mesures m1-m6 du plan : un `tasks.py new` lancé dans un worktree lié faisait naître une
partition à lui, et ses événements n'atteignaient jamais celle du principal, 0 sur 5020).

Quatre familles :
  * `TestPrincipalDuWorktree` — le prédicat `principal_du_worktree`, git RÉEL (P1-P11 ; P11 :
    les `GIT_*` hérités ne détournent plus le jugement de la racine, T-01M4MC2949AVM2X2HEK92DDVSG) ;
  * `TestPurgeDesGitHerites` — la purge de ces `GIT_*`, PURE, `subprocess.run` remplacé (P12) :
    hors de la classe POSIX-seule, elle se joue aussi sous Windows (réserve C2,
    S-01M4NQ9K1VQ92GF8F7E68Y46EV) ;
  * `TestRefusNaissanceWorktree` — la jambe neuve de `refus_naissance`, PURE, par injection
    de `principal=` (R1-R5) ;
  * `TestDeBoutEnBout` — le `tasks.py` du kit en sous-processus sur un dépôt jetable et son
    worktree, HOME et TMPDIR jetables, SANS `CADRE_STATE_DIR` (E0-E3).

COMPTE DES INTENTS EN ATTENTE (précondition 2(c) du plan) : depuis T-00001058 (outbox O2, un
fichier par intent, SUIVI par git), `TASKS.json` ne porte plus `sync_outbox` ; le banc compte
par l'accès que T-00001058 expose — `load(root)["sync_outbox"]`, la VUE que `tasks.py`
assemble —, chargé dans un processus enfant, jamais en listant un dossier deviné.

ENVIRONNEMENT construit DE ZÉRO (réserve A-C4 du critique), jamais une purge par préfixe : un
`commit.gpgsign` ou un `core.hooksPath` global ferait rougir les `commit` jetables sans rapport
avec le code. Le prédicat, appelé EN PROCESSUS, tourne sous ce même environnement
(`mock.patch.dict(os.environ, ..., clear=True)`) : son `git` hérite de `os.environ`.

FORME DU BANC E (mesure m4 du plan) : les racines `<t>/depot/k` et `<t>/depot/w` sont HORS de
`TMPDIR=<t>/zone`, et la zone littérale qui les contient (macOS : /var/folders ; Linux : /tmp,
ASSUMÉ) contient aussi le HOME jetable — une zone qui contient le domicile n'est pas retenue
(T-00000753) : seule la jambe « worktree lié » peut refuser. Le dépôt jetable porte la ligne
`/.agents/state/local/` du `.gitignore` du kit (verrou, lots, quarantaine : jamais versionnés).

BORNES, écrites :
  * familles P1-P11 et E : POSIX et git présents seulement (liens symboliques, HOME par
    l'environnement) ; mesurées sous macOS, Linux NON MESURÉ ; P12 et R, purs, partout ;
  * E2 OUVRE le canal « par la fusion » en commitant le board du worktree (`git add -A` sur un
    dépôt JETABLE) : la procédure du kit, qui commite par NOM et jamais le board d'une branche
    de dev, ne l'ouvre pas d'elle-même — le banc prouve le canal, pas son usage ;
  * sous `CADRE_STATE_DIR` posé, le worktree fait encore naître sa partition, isolée, et y
    DRAINE ses intents, qui quittent son outbox : E3 FIGE cette borne, il ne la juge pas ;
  * M4 (jambe avant `isole`, donc aussi avant les zones) est tué par R2 et R4, jamais par E3 :
    sous isolation, `garder_store` sort sur
    `isole()` avant tout `refus_naissance`, donc E3 ne voit pas l'ordre interne du prédicat.
"""
from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_partition_worktree_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "agentic_v3")
if str(ROOT / "src") not in sys.path:
    sys.path.append(str(ROOT / "src"))


def test_provenance_v3_en_processus():
    attendu = _VENDOR.exiger(ROOT, "agentic_v3")
    assert Path(sys.modules["agentic_v3"].__file__).resolve().parent == attendu.resolve()

POSIX = os.name == "posix"
GIT = shutil.which("git")
TASKS_PY = ROOT / ".agents" / "bin" / "tasks.py"
ID_CREE = re.compile(r"TASKS: (T-[0-9A-Za-z]+) ")

#: Lecteur du board, en processus ENFANT : `load()` de `tasks.py` (la VUE O2 de T-00001058),
#: aucun verrou pris, aucun pont construit — le modèle de `test_board_bridge_identite.py`.
LECTEUR_BOARD = (
    "import importlib.util, json, sys\n"
    "spec = importlib.util.spec_from_file_location('tasks_lecteur_t1069', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec)\n"
    "sys.modules[spec.name] = m\n"
    "spec.loader.exec_module(m)\n"
    "d = m.load(sys.argv[2])\n"
    "print(json.dumps({'attente': len(d.get('sync_outbox') or []),"
    " 'taches': [t['id'] for t in d.get('tasks', [])]}))\n"
)

#: Lecteur du store V3 de la racine, en processus ENFANT et sous le même environnement.
LECTEUR_EVENEMENTS = (
    "import json, sys\n"
    "from agentic_v3.db.event_store import EventStore\n"
    "ev = EventStore(project_root=sys.argv[1]).get_task_events(sys.argv[2])\n"
    "print(json.dumps([e.get('event_type') for e in ev]))\n"
)


def np() -> Any:
    """Résolu PARESSEUSEMENT : un symbole absent rougit SON témoin, jamais la collecte."""
    from agentic_v3.db import naissance_partition

    return naissance_partition


def parent_v3() -> Path:
    from agentic_v3.db import run_export

    return run_export._vendor_paths().exiger(ROOT, "agentic_v3").parent


def nombre(base: Path) -> int:
    projets = base / "projets"
    return sum(1 for e in projets.iterdir() if e.is_dir()) if projets.is_dir() else 0


def env_de_zero(t: Path, **plus: str) -> dict:
    """L'environnement COMPLET des sous-processus (git, `tasks.py`, lecteurs) — construit, pas purgé."""
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(t / "home"),
        "TMPDIR": str(t / "zone"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CEILING_DIRECTORIES": str(t),
        "LC_ALL": "C",
        "PYTHONUTF8": "1",
        "AGENTS_EVENTS_DIR": str(t / "ev"),
        "PYTHONPATH": os.pathsep.join((str(parent_v3()), str(ROOT / "src"))),
    }
    env.update(plus)
    return env


class _Bac(unittest.TestCase):
    """`<t>` passé par `realpath` (macOS : /var est /private/var), sinon la borne « zone qui
    contient le domicile » ne joue pas sur le HOME jetable et le principal serait refusé."""

    def setUp(self) -> None:
        self.t = Path(os.path.realpath(tempfile.mkdtemp(prefix="t1069_")))
        self.addCleanup(shutil.rmtree, str(self.t), True)
        for d in ("home", "zone", "ev", "depot"):
            (self.t / d).mkdir()

    def git(self, *args: Any, cwd: Optional[Path] = None) -> str:
        r = subprocess.run([GIT, *(str(a) for a in args)], cwd=str(cwd or self.t), env=env_de_zero(self.t),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                           check=False)
        self.assertEqual(r.returncode, 0, f"git {args!r} : {r.stderr}")
        return r.stdout

    def depot(self, nom: str, *, commit: bool = True) -> Path:
        racine = self.t / "depot" / nom
        racine.mkdir()
        self.git("init", "-q", "-b", "main", racine)
        self.git("-C", racine, "config", "user.email", "banc@example.invalid")
        self.git("-C", racine, "config", "user.name", "banc")
        (racine / ".gitignore").write_text("/.agents/state/local/\n", encoding="utf-8")
        if commit:
            self.git("-C", racine, "add", ".gitignore")
            self.git("-C", racine, "commit", "-q", "-m", "racine")
        return racine


@unittest.skipUnless(POSIX and GIT, "git réel et liens symboliques : POSIX avec git")
class TestPrincipalDuWorktree(_Bac):
    def principal(self, racine: Any, **plus: str) -> Optional[str]:
        with mock.patch.dict(os.environ, env_de_zero(self.t, **plus), clear=True):
            return np().principal_du_worktree(racine)

    def assertMemeDossier(self, rendu: Optional[str], attendu: Path) -> None:
        self.assertIsNotNone(rendu)
        self.assertEqual(os.path.realpath(rendu), os.path.realpath(attendu))

    def test_P1_le_principal_n_a_pas_de_principal(self) -> None:
        self.assertIsNone(self.principal(self.depot("k")))

    def test_P2_un_sous_dossier_du_principal_n_est_pas_lie(self) -> None:
        # m6 : sans `--path-format=absolute`, `--git-dir` et `--git-common-dir` y rendent deux graphies
        k = self.depot("k")
        (k / "sous").mkdir()
        self.assertIsNone(self.principal(k / "sous"))

    def test_P3_un_worktree_lie_rend_son_principal(self) -> None:
        k = self.depot("k")
        w = self.t / "depot" / "w"
        self.git("-C", k, "worktree", "add", "-q", w, "-b", "wt/sonde")
        self.assertMemeDossier(self.principal(w), k)

    def test_P4_un_sous_dossier_du_worktree_lie_rend_le_principal(self) -> None:
        k = self.depot("k")
        w = self.t / "depot" / "w"
        self.git("-C", k, "worktree", "add", "-q", w, "-b", "wt/sonde")
        (w / "sous").mkdir()
        self.assertMemeDossier(self.principal(w / "sous"), k)

    def test_P5_un_worktree_imbrique_sous_le_principal_rend_le_principal(self) -> None:
        k = self.depot("k")
        n = k / ".claude" / "worktrees" / "n"
        self.git("-C", k, "worktree", "add", "-q", n, "-b", "wt/n")
        self.assertMemeDossier(self.principal(n), k)

    def test_P6_le_worktree_d_un_depot_nu_n_a_pas_de_principal(self) -> None:
        k = self.depot("k")
        nu = self.t / "depot" / "nu.git"
        self.git("clone", "-q", "--bare", k, nu)
        lie = self.t / "depot" / "nu-w"
        self.git("-C", nu, "worktree", "add", "-q", lie, "-b", "wt/nu")
        self.assertIsNone(self.principal(lie))

    def test_P7_un_lien_est_juge_sur_sa_cible(self) -> None:
        k = self.depot("k")
        w = self.t / "depot" / "w"
        self.git("-C", k, "worktree", "add", "-q", w, "-b", "wt/sonde")
        os.symlink(k, self.t / "lien-k")
        os.symlink(w, self.t / "lien-w")
        with self.subTest(lien="vers le principal"):
            self.assertIsNone(self.principal(self.t / "lien-k"))
        with self.subTest(lien="vers le worktree lié"):
            self.assertMemeDossier(self.principal(self.t / "lien-w"), k)

    def test_P8_hors_git_et_chemin_absent(self) -> None:
        (self.t / "sans-git").mkdir()
        self.assertIsNone(self.principal(self.t / "sans-git"))
        self.assertIsNone(self.principal(self.t / "absent"))

    def test_P9_git_introuvable_rend_None_sans_lever(self) -> None:
        k = self.depot("k")
        w = self.t / "depot" / "w"
        self.git("-C", k, "worktree", "add", "-q", w, "-b", "wt/sonde")
        self.assertIsNone(self.principal(w, PATH=""))

    def test_P10_un_git_dir_separe_n_est_pas_un_worktree_lie(self) -> None:
        sep = self.t / "depot" / "sep"
        self.git("init", "-q", "--separate-git-dir", self.t / "depot" / "sep.git", sep)
        self.assertIsNone(self.principal(sep))

    def test_P11_un_GIT_herite_ne_detourne_pas_le_jugement_de_la_racine(self) -> None:
        # T-01M4MC2949AVM2X2HEK92DDVSG — un hook git exporte `GIT_DIR` ; `git -c` exporte
        # `GIT_CONFIG_PARAMETERS` (réserve C1 du plan-critic, S-01M4NQ9K1VQ92GF8F7E68Y46EV) : le
        # prédicat juge la RACINE, jamais le dépôt ni la config que l'environnement hérité désigne
        k = self.depot("k")
        w = self.t / "depot" / "w"
        self.git("-C", k, "worktree", "add", "-q", w, "-b", "wt/sonde")
        with self.subTest(herite="GIT_DIR du principal, racine = le worktree lié"):
            self.assertMemeDossier(self.principal(w, GIT_DIR=str(k / ".git")), k)
        with self.subTest(herite="GIT_DIR du worktree lié, racine = le principal"):
            self.assertIsNone(self.principal(k, GIT_DIR=str(k / ".git" / "worktrees" / "w")))
        with self.subTest(herite="GIT_CONFIG_PARAMETERS core.bare=true, racine = le worktree lié"):
            self.assertMemeDossier(self.principal(w, GIT_CONFIG_PARAMETERS="'core.bare'='true'"), k)
        with self.subTest(herite="GIT_CONFIG_COUNT/KEY_0/VALUE_0 core.bare=true, racine = le worktree lié"):
            self.assertMemeDossier(self.principal(w, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.bare",
                                                  GIT_CONFIG_VALUE_0="true"), k)


class TestPurgeDesGitHerites(unittest.TestCase):
    """P12 — PUR : `subprocess.run` remplacé, aucun git lancé, aucune E/S. HORS de la classe
    POSIX-seule (réserve C2 du plan-critic, S-01M4NQ9K1VQ92GF8F7E68Y46EV) : la purge a un témoin
    sur la jambe Windows aussi."""

    #: Recopiés EN DUR, jamais lus du module : une liste amputée AU MODULE rougit ce témoin.
    HERITEES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX",
                "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_KEY_12", "GIT_CONFIG_VALUE_12")
    #: Gardées, valeur comprise : les EMPLACEMENTS de config et la borne de découverte passent.
    GARDEES = {"PATH": os.pathsep.join(("/zz12/bin", "/zz12/usr/bin")), "HOME": "/zz12/home",
               "GIT_CEILING_DIRECTORIES": "/zz12", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": "/zz12/gitconfig-global"}
    K = "/zz12/k"

    def test_P12_les_deux_appels_git_recoivent_un_environnement_purge_sans_toucher_os_environ(self) -> None:
        appels: list = []
        rendus = (
            subprocess.CompletedProcess([], 0, f"{self.K}/.git/worktrees/w\n{self.K}/.git\n", ""),
            subprocess.CompletedProcess([], 0, f"worktree {self.K}\nHEAD 0\nbranch refs/heads/main\n\n"
                                               "worktree /zz12/w\nHEAD 0\nbranch refs/heads/wt/sonde\n", ""),
        )

        def run(argv: Any, **kw: Any) -> subprocess.CompletedProcess:
            appels.append(kw)
            return rendus[len(appels) - 1]

        pose = {nom: f"/zz12/{nom.lower()}" for nom in self.HERITEES}
        pose.update(self.GARDEES)
        with mock.patch.dict(os.environ, pose), mock.patch.object(np().subprocess, "run", side_effect=run):
            avant = dict(os.environ)
            rendu = np().principal_du_worktree("/zz12/w")
            apres = dict(os.environ)
        self.assertEqual(rendu, self.K)
        self.assertEqual(apres, avant)  # `os.environ` jamais muté
        self.assertEqual(len(appels), 2)
        for numero, kw in enumerate(appels, 1):
            env = kw.get("env")
            with self.subTest(appel=numero):
                self.assertIsInstance(env, dict)
                self.assertEqual([nom for nom in self.HERITEES if nom in env], [])
                self.assertEqual({nom: env.get(nom) for nom in self.GARDEES}, self.GARDEES)


class TestRefusNaissanceWorktree(unittest.TestCase):
    """Prédicat PUR : zones injectées, domicile fictif, principal injecté — aucun git, aucune E/S."""

    RACINE = "/zz1069/depot/w"
    PRINCIPAL = "/zz1069/depot/k"

    def refus(self, racine: Any = RACINE, *, environ: Optional[dict] = None, zones: tuple = (),
              principal: Any = None) -> Optional[str]:
        sonde = principal if principal is not None else (lambda r: self.PRINCIPAL)
        return np().refus_naissance(racine, environ={} if environ is None else environ, zones=list(zones),
                                    domicile="/home/user", principal=sonde)

    def test_R1_un_worktree_lie_sans_isolation_est_refuse_et_nomme(self) -> None:
        vus: list = []

        def sonde(r: Any) -> str:
            vus.append(r)
            return self.PRINCIPAL

        message = self.refus(principal=sonde) or ""
        for jeton in ("REFUSÉE", "worktree LIÉ", os.path.realpath(self.RACINE), self.PRINCIPAL, "T-00001069",
                      "n'a pas de pont V3 — travaille depuis un clone"):
            with self.subTest(jeton=jeton):
                self.assertIn(jeton, message)
        # T-01M4MC28WDHJ301H9C4P3JC8WP — assertion INVERSÉE, pas retirée (décision pilote
        # S-01M4N0NGM16BYEYYB3VT7X69WJ) : CADRE_STATE_DIR reste publique (CONTRAT-v0 § 3.4), mais
        # le refus ne la propose plus comme issue
        self.assertNotIn("CADRE_STATE_DIR", message)
        self.assertEqual(vus, [os.path.realpath(self.RACINE)])  # la sonde INJECTÉE a jugé la racine résolue

    def test_R2_sous_CADRE_STATE_DIR_rien_n_est_refuse(self) -> None:
        self.assertIsNone(self.refus(environ={"CADRE_STATE_DIR": "/e"}))

    def test_R3_une_racine_sans_principal_n_est_pas_refusee(self) -> None:
        self.assertIsNone(self.refus(principal=lambda r: None))

    def test_R4_la_zone_temporaire_garde_la_priorite_de_son_message(self) -> None:
        message = self.refus("/zz1069/zone/w", zones=("/zz1069/zone",)) or ""
        self.assertIn("T-00000753", message)
        self.assertNotIn("worktree LIÉ", message)

    def test_R5_une_sonde_qui_leve_ne_refuse_rien(self) -> None:
        def leve(r: Any) -> str:
            raise RuntimeError("sonde en panne")

        self.assertIsNone(self.refus(principal=leve))


@unittest.skipUnless(POSIX and GIT, "HOME et TMPDIR posés par l'environnement, git réel : POSIX avec git")
class TestDeBoutEnBout(_Bac):
    def setUp(self) -> None:
        super().setUp()
        self.k = self.t / "depot" / "k"
        self.w = self.t / "depot" / "w"

    def etat_defaut(self) -> Path:
        return self.t / "home" / ".local" / "state" / "cadre"

    def test_lecteur_enfant_recoit_le_parent_reel_du_paquet_v3(self) -> None:
        from agentic_v3.db import run_export

        attendu = run_export._vendor_paths().exiger(ROOT, "agentic_v3").parent
        recu = Path(env_de_zero(self.t)["PYTHONPATH"].split(os.pathsep)[0])
        self.assertEqual(recu, attendu)

    def lance(self, argv: list, racine: Path, **plus: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(a) for a in argv], cwd=str(racine), env=env_de_zero(self.t, **plus),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                              check=False)

    def tasks(self, racine: Path, *verbe: str, **plus: str) -> subprocess.CompletedProcess:
        # cwd = la racine, sans `--root` : la forme d'un appel réel depuis un worktree (m1)
        return self.lance([sys.executable, TASKS_PY, *verbe], racine, **plus)

    def board(self, racine: Path) -> dict:
        r = self.lance([sys.executable, "-c", LECTEUR_BOARD, TASKS_PY, racine], racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def evenements(self, racine: Path, tid: str) -> list:
        r = self.lance([sys.executable, "-c", LECTEUR_EVENEMENTS, racine, tid], racine)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def cree(self, racine: Path, titre: str, **plus: str) -> tuple:
        r = self.tasks(racine, "new", titre, **plus)
        self.assertEqual(r.returncode, 0, r.stderr)
        trouve = ID_CREE.search(r.stdout)
        self.assertIsNotNone(trouve, r.stdout)
        return trouve.group(1), r

    def principal_puis_worktree(self) -> str:
        """E0, rejoué en tête de chaque test E : `new` au principal fait naître SA partition
        (témoin positif), le board est commité, puis le worktree lié est ajouté."""
        self.depot("k", commit=False)
        tid, r = self.cree(self.k, "sonde principal")
        self.assertNotIn("REFUSÉ", r.stderr)
        self.assertEqual(nombre(self.etat_defaut()), 1)
        self.assertEqual(self.board(self.k)["attente"], 0)
        self.git("-C", self.k, "add", "-A")
        self.git("-C", self.k, "commit", "-q", "-m", "E0 : board du principal")
        self.git("-C", self.k, "worktree", "add", "-q", self.w, "-b", "wt/sonde")
        return tid

    def test_E0_le_principal_fait_naitre_sa_partition_et_y_draine(self) -> None:
        tid = self.principal_puis_worktree()
        self.assertTrue(self.evenements(self.k, tid))

    def test_E1_E2_le_worktree_ne_fait_rien_naitre_et_ses_intents_rejoignent_le_principal_par_la_fusion(self) -> None:
        self.principal_puis_worktree()
        # E1 — refus annoncé, aucune partition neuve, l'intent attend dans l'outbox DU WORKTREE
        tid, r = self.cree(self.w, "sonde worktree")
        self.assertIn("REFUSÉ (emplacement", r.stderr)
        self.assertIn("worktree LIÉ", r.stderr)
        self.assertEqual(nombre(self.etat_defaut()), 1)
        vu = self.board(self.w)
        self.assertEqual(vu["attente"], 1)
        self.assertIn(tid, vu["taches"])
        statut = self.git("-C", self.w, "status", "--porcelain", "--untracked-files=all")
        self.assertIn(".agents/state/board/sync_outbox/", statut)  # visible au `git status` : il peut voyager
        self.assertNotIn(".agents/state/local/", statut)
        # E2 — board du worktree commité, fusion au principal, drain : l'événement atteint SA partition
        self.git("-C", self.w, "add", "-A")
        self.git("-C", self.w, "commit", "-q", "-m", "E1 : board du worktree")
        self.git("-C", self.k, "merge", "--no-ff", "-q", "-m", "E2 : fusion", "wt/sonde")
        self.assertEqual(self.board(self.k)["attente"], 1)
        rejeu = self.tasks(self.k, "replay-sync")
        self.assertEqual(rejeu.returncode, 0, rejeu.stderr)
        self.assertEqual(self.board(self.k)["attente"], 0)
        self.assertIn("BOARD_TASK_OBSERVED", self.evenements(self.k, tid))
        self.assertEqual(nombre(self.etat_defaut()), 1)

    def test_E3_sous_CADRE_STATE_DIR_le_worktree_fait_naitre_sa_partition_isolee(self) -> None:
        self.principal_puis_worktree()
        etat = self.t / "etat"
        _tid, r = self.cree(self.w, "sonde isolee", CADRE_STATE_DIR=str(etat))
        self.assertNotIn("REFUSÉ", r.stderr)
        self.assertEqual(nombre(etat), 1)
        self.assertEqual(nombre(self.etat_defaut()), 1)  # rien de neuf sous le HOME jetable
        # drainé dans la partition isolée : l'intent a quitté l'outbox du worktree, il n'atteindra
        # jamais le principal (delta S-01M4M2E7DWB4SWDR02GPSSQ0JV ; borne écrite au module)
        self.assertEqual(self.board(self.w)["attente"], 0)


if __name__ == "__main__":
    unittest.main()
