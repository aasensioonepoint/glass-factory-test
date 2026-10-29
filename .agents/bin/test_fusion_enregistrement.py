"""T-01M4JN4ZSWAX5MGSGQNPPYZG68 (E-26) — banc du pilote de fusion git PAR CHAMP `fusion_enregistrement.py` (plan
`docs/tasks/T-01M4JN4ZSWAX5MGSGQNPPYZG68-plan.md` rév. 3, § Tests).

F1-F17, F4b, F12e et T-imports jugent des fonctions PURES et l'AST : aucun git n'y est exécuté, toute demande de repli
s'y constate sur l'argv d'un `subprocess.run` SIMULÉ, comparé à `argv_repli` de la PRODUCTION ; ils ne sautent JAMAIS.
G1-G9, G9b-G9d et I1-I9b exécutent git dans des dépôts jetables ; eux seuls SAUTENT, quand `sonder_git()` du
pilote — jouée UNE fois par module — nomme une capacité absente (jamais sur un numéro de version). G6, I7 et I9c :
dépôt-kit seul (`.agents/IS_THE_KIT`). I9c ne saute jamais sur une absence : au kit, `git --version` ≥ 2.44 (ou
illisible) et une absence dite ⇒ ÉCHEC, l'étape en défaut nommée.

Environnement du module : `GIT_CONFIG_NOSYSTEM=1` ; `GIT_CONFIG_GLOBAL` = fichier jetable, relu octet pour octet (I2) ;
`CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR`, `TMPDIR` (et `tempfile.tempdir`, rétabli au démontage) jetables ; tout `GIT_*`
d'autre, `EMAIL`, `CLAUDE_PROJECT_DIR` et `CADRE_PROJECT_ROOT` retirés — `installer()` appelé en processus compris ;
le cwd est un dossier jetable (un mutant qui perdrait `git -C` viserait ce dossier, jamais le dépôt du banc) ;
`installer()` et `verifier()` reçoivent TOUJOURS une racine jetable. Deux copies d'un même dépôt : `git clone`.
Module absent (la BASE) : chaque témoin ROUGE, « pilote absent : FileNotFoundError » nommé, aucun saut.
Mutants m1-m33 (§ Tests du plan) : chaque docstring nomme ceux que le témoin tue. Hors plan, le mutant F1 (décision
S-01M4R8Y48QVARQT92YW6ACD9RG : `return rc` au lieu de 3 quand un REFUS retombe sur une fusion texte propre) est tué
par F16, G9b et G9c ; le mutant « refus dont merge-file échoue ⇒ 4 » (NO_GO de l'exec-critic de F1), par F16 et G9d.
"""

import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PILOTE = HERE / "fusion_enregistrement.py"
MARQUEUR_KIT = REPO / ".agents" / "IS_THE_KIT"
PROTECT_PATHS = REPO / ".claude" / "hooks" / "protect-paths.sh"
BOARD_REL = Path(".agents") / "state" / "board"
SUIVI_REL = Path(".agents") / "bin" / "fusion_enregistrement.py"
JOUR = "2026-10-11"
#: G9b/G9d : chacun valide seul sur le socle de `_g9b`, combinés par la fusion texte ⇒ motif hors des arêtes.
G9B_ICI, G9B_LA = {"depends_motif": {"T-1": "m", "T-5": "n"}}, {"depends_on": ["T-1"]}
ATTR = "".join(f"/.agents/state/{motif} merge=cadre-enregistrement\n"
               for motif in ("board/tasks/*.json", "board/epics/*.json", "memory/entries/*.json"))
ENTREE_ID = "L-00000001"
HOSTILE = "b$(touch${IFS}PWNED)"

P: Any = None
ERREUR_PILOTE = ""
tasks: Any = None
ledger: Any = None
SONDE: dict[str, str] = {}
BASE = Path()
GLOBAL_GIT = Path()
_RESTAURER: list[Any] = []


def _charger(nom: str, chemin: Path) -> Any:
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def setUpModule() -> None:
    global P, ERREUR_PILOTE, tasks, ledger, SONDE, BASE, GLOBAL_GIT
    try:
        tmp = tempfile.TemporaryDirectory(prefix="fe-", ignore_cleanup_errors=True)
        _RESTAURER.append(tmp.cleanup)
        BASE = Path(tmp.name)
        for sous in ("state", "events", "tmp"):
            (BASE / sous).mkdir()
        GLOBAL_GIT = BASE / "gitconfig-global"
        GLOBAL_GIT.write_bytes(b"")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GIT_") and k not in ("EMAIL", "CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(GLOBAL_GIT), CADRE_STATE_DIR=str(BASE / "state"),
                   AGENTS_EVENTS_DIR=str(BASE / "events"), TMPDIR=str(BASE / "tmp"))
        for patch in (mock.patch.dict(os.environ, env, clear=True),
                      mock.patch.object(tempfile, "tempdir", str(BASE / "tmp"))):
            patch.start()
            _RESTAURER.append(patch.stop)
        cwd = os.getcwd()
        _RESTAURER.append(lambda: os.chdir(cwd))
        os.chdir(BASE)
        tasks = _charger("tasks_fusion_banc", HERE / "tasks.py")
        ledger = _charger("ledger_fusion_banc", HERE / "ledger.py")
        try:
            P = _charger("fusion_enregistrement_banc", PILOTE)
        except FileNotFoundError:
            ERREUR_PILOTE = f"pilote absent : FileNotFoundError ({PILOTE.name})"
            return
        SONDE = P.sonder_git()  # UNE fois par module : la décision de SAUT des G et des I
    except BaseException:
        tearDownModule()
        raise


def tearDownModule() -> None:
    while _RESTAURER:
        _RESTAURER.pop()()


def canon(objet: Any) -> bytes:
    return (json.dumps(objet, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def rec(tid: str = "T-3", **champs: Any) -> dict[str, Any]:
    """Un enregistrement de tâche ; un champ à `None` est RETIRÉ."""
    r: dict[str, Any] = {"id": tid, "owner": "", "stage": "", "state": "pending", "task": tid, "updated": JOUR}
    r.update(champs)
    return {k: v for k, v in r.items() if v is not None}


def env(record: Any, ops: Any = (), tid: str = "T-3") -> dict[str, Any]:
    return {"format": 1, "id": tid, "record": record, "sync_operations": list(ops)}


def entree(**champs: Any) -> dict[str, Any]:
    r = {"id": ENTREE_ID, "category": ledger.CATEGORIES[0], "status": ledger.STATUSES[0], "title": "t",
         "created": JOUR, "tags": [], "text": "", "related": ""}
    r.update(champs)
    return {k: v for k, v in r.items() if v is not None}


def env_git() -> dict[str, str]:
    """L'environnement du module, sans aucun `GIT_*` hors des deux clés de config du banc."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith("GIT_") or k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}


def git(depot: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", str(depot), *args], capture_output=True, text=True, timeout=120,
                       env=env_git(), check=False)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} : rc={p.returncode} {p.stderr[-400:]}")
    return p


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class _Banc(unittest.TestCase):
    """Exige le module sous test : absent, chaque témoin est ROUGE, jamais sauté."""

    def setUp(self) -> None:
        if P is None:
            self.fail(ERREUR_PILOTE or "pilote non chargé")
        self.tmp = Path(tempfile.mkdtemp(dir=BASE / "tmp"))

    def exiger_kit(self) -> None:
        if not MARQUEUR_KIT.is_file():
            self.skipTest("dépôt-kit seul (.agents/IS_THE_KIT absent)")

    def jouer_main(self, base: Any, nous: Any, eux: Any, rc_repli: int = 1, ecrit: bytes | None = None,
                   leve: BaseException | None = None) -> dict[str, Any]:
        """`main` sur trois fichiers jetables ; le repli est un `subprocess.run` SIMULÉ (aucun git exécuté) qui, au
        besoin, ÉCRIT `ecrit` dans %A (`argv[-3]`, ordre de `argv_repli`) puis rend `rc_repli`, ou LÈVE `leve`."""
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        chemins = []
        for nom, contenu in (("O", base), ("A", nous), ("B", eux)):
            (d / nom).write_bytes(contenu if isinstance(contenu, bytes) else canon(contenu))
            chemins.append(str(d / nom))
        err = io.StringIO()

        def simule(argv: list[str], **_: Any) -> subprocess.CompletedProcess:
            if ecrit is not None:
                Path(argv[-3]).write_bytes(ecrit)
            if leve is not None:
                raise leve
            return subprocess.CompletedProcess(argv, rc_repli)

        with mock.patch.object(P.subprocess, "run", side_effect=simule) as run, contextlib.redirect_stderr(err):
            rc = P.main(["fusion_enregistrement.py", *chemins, "7", "S", "X", "Y"])
        return {"rc": rc, "A": (d / "A").read_bytes(), "run": run, "err": err.getvalue(), "chemins": chemins, "d": d}

    def assert_repli(self, jeu: dict[str, Any], avant: bytes) -> None:
        self.assertEqual(3, jeu["rc"], jeu["err"])
        self.assertEqual(1, jeu["run"].call_count)
        self.assertEqual(P.argv_repli(*jeu["chemins"], "7", "S", "X", "Y"), jeu["run"].call_args.args[0])
        self.assertEqual(avant, jeu["A"], "%A modifié alors que le repli a été demandé")


class FusionParChampTests(_Banc):
    def test_F1_champs_voisins_fusionnent(self) -> None:
        """F1 : `stage` ici, `state` là ⇒ les deux pris, opérations unies."""
        res = P.fusionner(env(rec()), env(rec(stage="revue"), ["o1"]), env(rec(state="running"), ["o2"]))
        self.assertEqual(env(rec(stage="revue", state="running"), ["o1", "o2"]), res)

    def test_F2_meme_champ_valeurs_differentes_conflit_nomme(self) -> None:
        """F2 : même champ, deux valeurs ⇒ `Conflit("record/stage")`. Tue m3 (`max` sur toute chaîne)."""
        with self.assertRaises(P.Conflit) as cm:
            P.fusionner(env(rec()), env(rec(stage="a")), env(rec(stage="b")))
        self.assertEqual("record/stage", str(cm.exception))

    def test_F3_meme_valeur_des_deux_cotes(self) -> None:
        self.assertEqual(env(rec(stage="a")), P.fusionner(env(rec()), env(rec(stage="a")), env(rec(stage="a"))))

    def test_F4_tombe_contre_modification_et_l_inverse(self) -> None:
        """F4 : tombe d'un côté, `record` modifié de l'autre ⇒ conflit, dans les deux sens. Tue m4."""
        tombe, modif = env(None, ["o1"]), env(rec(stage="x"), ["o2"])
        for nous, eux in ((tombe, modif), (modif, tombe)):
            with self.subTest(tombe_ici=nous is tombe), self.assertRaises(P.Conflit):
                P.fusionner(env(rec()), nous, eux)

    def test_F4b_tombe_contre_operations_seules_epingle(self) -> None:
        """F4b (MT, angle mort I, ÉPINGLÉ) : tombe ici, seul `sync_operations` changé là ⇒ la tombe, opérations unies."""
        res = P.fusionner(env(rec(), ["o1"]), env(None, ["o1", "o2"]), env(rec(), ["o1", "o3"]))
        self.assertEqual(env(None, ["o1", "o2", "o3"]), res)

    def test_F5_updated_la_plus_recente_et_dates_refusees(self) -> None:
        """F5 : `updated` 12 / 13 ⇒ 13 ; non-date, `20261012` (que `fromisoformat` seul accepte), date impossible
        ⇒ conflit. Tue m2 (règle retirée) et m2b (`fromisoformat` seul)."""
        res = P.fusionner(env(rec()), env(rec(stage="a", updated="2026-10-12")),
                          env(rec(state="running", updated="2026-10-13")))
        self.assertEqual(rec(stage="a", state="running", updated="2026-10-13"), res["record"])
        for mauvaise in ("hier", "20261012", "2026-02-30", "2026-10-12 "):
            with self.subTest(mauvaise=mauvaise):
                with self.assertRaises(P.Conflit) as cm:
                    P.fusionner(env(rec()), env(rec(updated=mauvaise)), env(rec(updated="2026-10-13")))
                self.assertEqual("record/updated", str(cm.exception))

    def test_F6_sync_operations_ensemble_a_trois_voies(self) -> None:
        """F6 : ajouts des deux côtés unis ; un retrait d'un côté tenu ; un côté sans la clé ⇒ conflit. Tue m1."""
        base = env(rec(), ["a"])
        self.assertEqual(["a", "b", "c"], P.fusionner(base, env(rec(), ["a", "b"]), env(rec(), ["a", "c"]))["sync_operations"])
        self.assertEqual(["c"], P.fusionner(base, env(rec(), []), env(rec(), ["a", "c"]))["sync_operations"])
        sans = {k: v for k, v in env(rec(), ["a"]).items() if k != "sync_operations"}
        for eux in (env(rec(), ["a", "c"]), env(rec(), ["a"])):
            with self.subTest(eux=eux["sync_operations"]), self.assertRaises(P.Conflit):
                P.fusionner(base, sans, eux)

    def test_F10_ids_differents_conflit(self) -> None:
        autre = {"format": 1, "id": "T-4", "record": rec("T-4"), "sync_operations": []}
        with self.assertRaises(P.Conflit):
            P.fusionner(env(rec()), env(rec(stage="a")), autre)

    def test_F12_champs_couples(self) -> None:
        """F12 (a)-(d), (f) : chaque groupe de `COUPLES` est un ATOME, et la table de conflits SUIT `COUPLES` (C42 :
        `parallel_group` + `state`, sans lecteur commun au `load`/`save`, se fusionnent champ par champ). Tue m13."""
        lien = {"depends_on": ["T-1"], "depends_motif": {"T-1": "m"}}
        cas_conflit = (
            ("(a) arête+motif retirés ici, motif réécrit là", rec(**lien),
             rec(), rec(depends_on=["T-1"], depends_motif={"T-1": "autre"}), "record/depends_on+depends_motif"),
            ("(a') MB : arête retirée ici, motif ajouté là", rec(depends_on=["T-1"]),
             rec(), rec(depends_on=["T-1"], depends_motif={"T-1": "m"}), "record/depends_on+depends_motif"),
            ("(d) record.id ≠ id", rec(), rec("T-9"), rec(stage="x"), "id/record.id"),
        )
        self.assertEqual({"record/" + "+".join(c) for _p, c in P.COUPLES}, {c[-1] for c in cas_conflit if "+" in c[-1]})
        for nom, b, n, e, attendu in cas_conflit:
            with self.subTest(nom):
                with self.assertRaises(P.Conflit) as cm:
                    P.fusionner(env(b), env(n), env(e))
                self.assertEqual(attendu, str(cm.exception))
        nouveau = {"depends_on": ["T-1", "T-9"], "depends_motif": {"T-1": "m", "T-9": "n"}}
        cas_pris = (
            ("(b) groupe entier d'un seul côté", rec(**lien), rec(**nouveau), rec(**lien, stage="s"),
             rec(**nouveau, stage="s")),
            ("(b) un champ du groupe d'un seul côté", rec(**lien), rec(depends_on=["T-1"], depends_motif={"T-1": "x"}),
             rec(**lien, state="blocked"), rec(depends_on=["T-1"], depends_motif={"T-1": "x"}, state="blocked")),
            ("(c) groupe identique des deux côtés", rec(**lien), rec(**nouveau, stage="a"), rec(**nouveau, owner="o"),
             rec(**nouveau, stage="a", owner="o")),
            ("(f) state ici, parallel_group là : champ par champ", rec(parallel_group="PG-0001"),
             rec(parallel_group="PG-0001", state="running"), rec(parallel_group="PG-0002"),
             rec(parallel_group="PG-0002", state="running")),
            ("(f) state seul d'un côté", rec(parallel_group="PG-0001"), rec(parallel_group="PG-0001", state="running"),
             rec(parallel_group="PG-0001", stage="s"), rec(parallel_group="PG-0001", state="running", stage="s")),
            ("(f) parallel_group seul d'un côté", rec(parallel_group="PG-0001"), rec(parallel_group="PG-0002"),
             rec(parallel_group="PG-0001", owner="o"), rec(parallel_group="PG-0002", owner="o")),
        )
        for nom, b, n, e, attendu in cas_pris:
            with self.subTest(nom):
                self.assertEqual(attendu, P.fusionner(env(b), env(n), env(e))["record"])


def acteur(nom: str | None, email: str | None, copie: str | None) -> dict[str, Any]:
    """La forme FERMÉE des acteurs du lot A (`tasks_etats.poser_acteur_stage`)."""
    return {"auteur": {"nom": nom, "email": email}, "copie": copie}


ALICE = acteur("Alice", "alice@example.invalid", "a1a1a1a1a1a1a1a1")
BOB = acteur("Bob", "bob@example.invalid", "b2b2b2b2b2b2b2b2")
XAVIER = acteur("Xavier", "xavier@example.invalid", "c0c0c0c0c0c0c0c0")
#: Un jeton à la forme d'une clé GitHub : jamais relu dans un message de conflit.
SECRET = "ghp_" + "Z9" * 18


class ActeursAtomesTests(_Banc):
    """T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot C : `start_actor` / `stage_actor` jugés ENTIERS avant la descente. Mutants
    tués : appel de `_juger_acteurs` retiré (fusion champ par champ = chimère), entrée `start_actor` retirée
    d'`ACTEURS`, stage égal traité comme accord, caviardage retiré, refus rendu 0."""

    def conflit(self, base: dict, nous: dict, eux: dict) -> str:
        with self.assertRaises(P.Conflit) as cm:
            P.fusionner(env(base), env(nous), env(eux))
        return str(cm.exception)

    def assert_double_demarrage(self, message: str, nous: dict, eux: dict) -> None:
        self.assertTrue(message.startswith("record/start_actor (double démarrage : "), message)
        for cote, a in (("nous", nous), ("eux", eux)):
            self.assertIn(f"{cote} {a['auteur']['nom']} <{a['auteur']['email']}> copie {a['copie']}", message)

    def test_double_demarrage_depuis_base_attribuee(self) -> None:
        """Base déjà attribuée à Xavier ; Xavier redémarre sur une autre copie ici, Bob sur la copie de base là :
        champ par champ, ce serait la chimère « auteur de Bob, copie d'ici » sans conflit. Stage égal, puis stage
        différent : le double démarrage est nommé AVANT `record/stage`."""
        ici = acteur("Xavier", "xavier@example.invalid", "d3d3d3d3d3d3d3d3")
        la = acteur("Bob", "bob@example.invalid", "c0c0c0c0c0c0c0c0")
        base = rec(start_actor=XAVIER)
        for stages in (("revue", "revue"), ("revue", "dev")):
            with self.subTest(stages=stages):
                nous = rec(state="running", stage=stages[0], start_actor=ici)
                eux = rec(state="running", stage=stages[1], start_actor=la)
                self.assert_double_demarrage(self.conflit(base, nous, eux), ici, la)

    def test_double_demarrage_depuis_base_vide(self) -> None:
        """Base sans `start_actor` : Alice ici, Bob là ⇒ « double démarrage », jamais le seul `record/start_actor`."""
        nous = rec(state="running", start_actor=ALICE)
        eux = rec(state="running", start_actor=BOB)
        self.assert_double_demarrage(self.conflit(rec(), nous, eux), ALICE, BOB)

    def test_double_demarrage_stage_identique(self) -> None:
        """Même `state`, même `stage`, même `stage_actor` absent : seuls les acteurs de démarrage diffèrent."""
        nous = rec(state="running", stage="dev", start_actor=ALICE)
        eux = rec(state="running", stage="dev", start_actor=BOB)
        self.assert_double_demarrage(self.conflit(rec(stage="dev"), nous, eux), ALICE, BOB)

    def test_stage_actor_atomique(self) -> None:
        """Stage égal, `stage_actor` changé des deux côtés vers une chimère possible ⇒ conflit nommé ; un acteur changé
        d'un seul côté, ou identique des deux, est pris ENTIER (aucun faux conflit)."""
        base = rec(stage="revue", stage_actor=XAVIER)
        ici = acteur("Xavier", "xavier@example.invalid", "d3d3d3d3d3d3d3d3")
        message = self.conflit(base, rec(stage="revue", stage_actor=ici), rec(stage="revue", stage_actor=BOB))
        self.assertTrue(message.startswith("record/stage_actor (stage signé par deux acteurs : "), message)
        pris = (
            ("un seul côté", rec(stage="revue", stage_actor=ALICE), rec(stage="revue", stage_actor=XAVIER, owner="o"),
             rec(stage="revue", stage_actor=ALICE, owner="o")),
            ("identique", rec(state="running", stage="revue", stage_actor=XAVIER, start_actor=ALICE),
             rec(state="running", stage="revue", stage_actor=XAVIER, start_actor=ALICE, owner="o"),
             rec(state="running", stage="revue", stage_actor=XAVIER, start_actor=ALICE, owner="o")),
        )
        for nom, nous, eux, attendu in pris:
            with self.subTest(nom):
                self.assertEqual(attendu, P.fusionner(env(base), env(nous), env(eux))["record"])

    def test_stage_repris_sous_une_autre_signature(self) -> None:
        """Couple `STAGE_SIGNE` : ici un stage neuf signé par l'acteur de base (P1a) ou sans acteur (P1b), là le MÊME
        stage signé Bob ⇒ conflit `record/stage+stage_actor`, jamais « dev signé Bob » en silence ; deux stages
        différents gardent `record/stage`. Tue le mutant « vérification du couple retirée »."""
        base = rec(stage="revue", stage_actor=XAVIER)
        eux = rec(stage="dev", stage_actor=BOB)
        message = self.conflit(base, rec(stage="dev", stage_actor=XAVIER), eux)
        self.assertTrue(message.startswith("record/stage+stage_actor (stage repris sous une autre signature : nous "
                                           "\"dev\" signé Xavier <"), message)
        self.assertIn("eux \"dev\" signé Bob <bob@example.invalid>", message)
        # P1b : l'acteur retiré ici, Bob là, c'est déjà l'atome `stage_actor` changé des deux côtés.
        message = self.conflit(base, rec(stage="dev"), eux)
        self.assertTrue(message.startswith("record/stage_actor (stage signé par deux acteurs : nous (aucun) ; "), message)
        self.assertEqual("record/stage", self.conflit(base, rec(stage="a", stage_actor=XAVIER), eux))

    def test_caviarde_puis_plafonne_et_bornes(self) -> None:
        """Ordre caviardé PUIS plafonné : un secret à cheval sur le 100e caractère sort `[caviardé]`, aucun fragment
        (plafonné d'abord, ses 10 premiers caractères passeraient). Bornes ÉPINGLÉES : un secret de moins de 20
        caractères passe EN CLAIR ; un nom sans espace de 20 caractères ou plus est masqué en entier."""
        a_cheval = P._dire_acteur(acteur("ab " * 30 + SECRET, None, None))
        self.assertIn("[caviardé]", a_cheval)
        self.assertNotIn("ghp_", a_cheval)
        court = "hunter2-Pw9"
        self.assertEqual(f"pw {court} <?> copie ?", P._dire_acteur(acteur(f"pw {court}", None, None)))
        self.assertEqual("[caviardé] <?> copie ?", P._dire_acteur(acteur("Jean-Christophe-Dupontel", None, None)))

    def test_double_demarrage_message_caviarde_par_main(self) -> None:
        """Canal réel `main` : merge-file propre (rc 0) ⇒ rc 3 quand même ; stderr nomme le double démarrage, la clé
        en forme de secret sort `[caviardé]`, un champ trop long porte le marqueur, un ESC sort échappé."""
        long = "x." * P.ACTEUR_PLAFOND  # des points : aucun jeton caviardé, seul le plafond mord
        hostile = acteur(f"Alice {SECRET}", f"{long}@example.invalid", "a1a1a1a1a1a1a1a1\x1b")
        nous = env(rec(state="running", start_actor=hostile))
        jeu = self.jouer_main(env(rec()), nous, env(rec(state="running", start_actor=BOB)), rc_repli=0)
        self.assertEqual(3, jeu["rc"], jeu["err"])
        self.assertIn("double démarrage : nous Alice [caviardé] <", jeu["err"])
        self.assertIn(P.ACTEUR_MARQUE + ">", jeu["err"])
        self.assertIn("eux Bob <bob@example.invalid> copie b2b2b2b2b2b2b2b2", jeu["err"])
        self.assertNotIn(SECRET, jeu["err"])
        self.assertNotIn("\x1b", jeu["err"])

    def test_couple_stage_signe_par_main_remet_nous(self) -> None:
        """Revue de clôture FK3X (C6) : le couple `STAGE_SIGNE` par le canal réel `main`, merge-file propre (rc 0)
        qui écrit la chimère « dev signé Bob » ⇒ rc 3 et %A remis à « nous » ENTIER. MUTANT : le couple lève
        `Conflit` au lieu de `ConflitActeur` (la chimère resterait dans %A)."""
        base = env(rec(stage="revue", stage_actor=XAVIER))
        nous = env(rec(stage="dev", stage_actor=XAVIER))
        eux = env(rec(stage="dev", stage_actor=BOB))
        jeu = self.jouer_main(base, nous, eux, rc_repli=0, ecrit=canon(eux))
        self.assertEqual(3, jeu["rc"], jeu["err"])
        self.assertIn("record/stage+stage_actor", jeu["err"])
        self.assertEqual(canon(nous), jeu["A"], "la chimère « dev signé Bob » est restée dans %A")

    def test_refus_acteurs_remise_impossible_le_dit(self) -> None:
        """Revue de clôture FK3X (C7) : refus des acteurs, merge-file propre, « nous » non instantané ⇒ rc 3 et stderr
        dit que %A n'a pas été remis ET qu'il porte la combinaison refusée. MUTANT : l'ancien message, muet sur la
        combinaison."""
        nous = env(rec(state="running", start_actor=ALICE))
        with mock.patch.object(P, "_instantane", return_value=None):
            jeu = self.jouer_main(env(rec()), nous, env(rec(state="running", start_actor=BOB)), rc_repli=0)
        self.assertEqual(3, jeu["rc"], jeu["err"])
        self.assertIn("%A n'a pas pu être remis à « nous »", jeu["err"])
        self.assertIn("combinaison refusée", jeu["err"])


class LectureEtEcritureTests(_Banc):
    def test_F7_un_cote_indente_a_4_repli(self) -> None:
        """F7 : hors forme canonique ⇒ repli texte demandé. Tue m5."""
        nous = (json.dumps(env(rec(stage="a")), indent=4, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        self.assert_repli(self.jouer_main(env(rec()), nous, env(rec(state="running"))), nous)

    def test_F8_un_mio_plus_un_repli(self) -> None:
        """F8 : une enveloppe CANONIQUE de PLAFOND + 1 octets ⇒ repli. Tue m6."""
        gros = env(rec(stage="a", task=""))
        gros["record"]["task"] = "x" * (P.PLAFOND + 1 - len(canon(gros)))
        self.assertEqual(P.PLAFOND + 1, len(canon(gros)))
        self.assert_repli(self.jouer_main(env(rec()), gros, env(rec(state="running"))), canon(gros))

    def test_F9_entrees_hostiles_repli_sans_exception(self) -> None:
        """F9 : NaN, Infinity, UTF-8 invalide, 100 000 `[` ouverts, imbrication FERMÉE profonde ⇒ repli, aucune exception."""
        hostiles = {
            "NaN": canon(env(rec())).replace(b'"format": 1', b'"format": NaN'),
            "Infinity": canon(env(rec())).replace(b'"format": 1', b'"format": Infinity'),
            "UTF-8 invalide": canon(env(rec(stage="é"))).replace("é".encode("utf-8"), b"\xff"),
            "100 000 [": b"[" * 100_000,
            "imbrication fermée": b'{"a": ' + b"[" * 100_000 + b"]" * 100_000 + b"}\n",
        }
        for nom, octets in hostiles.items():
            with self.subTest(nom):
                self.assert_repli(self.jouer_main(env(rec()), octets, env(rec(state="running"))), octets)

    def test_F10_ids_differents_repli(self) -> None:
        autre = {"format": 1, "id": "T-4", "record": rec("T-4"), "sync_operations": []}
        self.assert_repli(self.jouer_main(env(rec()), env(rec(stage="a")), autre), canon(env(rec(stage="a"))))

    def test_F11_parite_d_octets_avec_les_ecrivains(self) -> None:
        """F11 : la sortie == `tasks._octets_enveloppe` == `tasks.record_bytes_pour` ; == `ledger.record_bytes`."""
        jeu = self.jouer_main(env(rec(stage="é")), env(rec(stage="é", owner="ø"), ["o1"]), env(rec(state="running")))
        self.assertEqual(0, jeu["rc"], jeu["err"])
        lu = json.loads(jeu["A"])
        self.assertEqual(jeu["A"], tasks._octets_enveloppe(lu))
        self.assertEqual(jeu["A"], tasks.record_bytes_pour(lu, "tasks"))
        base = {"format": 1, "id": ENTREE_ID, "record": entree()}
        res = P.fusionner(base, {**base, "record": entree(title="ici")}, {**base, "record": entree(tags=["là"])})
        self.assertEqual(P.canonique(res), ledger.record_bytes(res))

    def test_F13_format_autre_que_l_entier_1_repli(self) -> None:
        """F13 : `format` 2, absent, `"1"`, `true` sur un côté ⇒ repli. Tue m17."""
        for nom, valeur in (("2", 2), ("absent", None), ('"1"', "1"), ("true", True)):
            nous = env(rec(stage="a"))
            if valeur is None:
                del nous["format"]
            else:
                nous["format"] = valeur
            with self.subTest(format=nom):
                self.assert_repli(self.jouer_main(env(rec()), nous, env(rec(state="running"))), canon(nous))

    def test_F14_echec_de_os_replace_A_intact_repli_aucun_residu(self) -> None:
        """F14 : `os.replace` en échec ⇒ %A inchangé, repli demandé, aucun temporaire résiduel. Tue m16."""
        nous = env(rec(stage="a"))
        with mock.patch.object(P.os, "replace", side_effect=OSError("simulé")):
            jeu = self.jouer_main(env(rec()), nous, env(rec(state="running")))
        self.assert_repli(jeu, canon(nous))
        self.assertEqual(["A", "B", "O"], sorted(p.name for p in jeu["d"].iterdir()))

    def test_F15_copie_divergente_une_ligne_sans_prescription(self) -> None:
        """F15 (S8) : fichier du worktree ≠ copie ⇒ UNE ligne « diffère de la copie installée », sans `--installer` ;
        identique ou absent ⇒ aucune ; la fusion est la même. Tue m18 et m32."""
        sorties = []
        for nom, contenu in (("diverge", PILOTE.read_bytes() + b"# autre\n"), ("identique", PILOTE.read_bytes()),
                             ("absent", None)):
            racine = Path(tempfile.mkdtemp(dir=self.tmp))
            if contenu is not None:
                (racine / SUIVI_REL).parent.mkdir(parents=True)
                (racine / SUIVI_REL).write_bytes(contenu)
            with contextlib.chdir(racine):
                jeu = self.jouer_main(env(rec()), env(rec(stage="a")), env(rec(state="running")))
            self.assertEqual(0, jeu["rc"], jeu["err"])
            sorties.append(jeu["A"])
            lignes = [ligne for ligne in jeu["err"].splitlines() if "copie installée" in ligne]
            with self.subTest(nom):
                if nom == "diverge":
                    self.assertEqual(1, len(lignes), jeu["err"])
                    self.assertIn("diffère de la copie installée", lignes[0])
                    self.assertNotIn("--installer", jeu["err"])
                else:
                    self.assertEqual([], lignes)
        self.assertEqual(1, len(set(sorties)))

    def test_F16_refus_puis_fusion_texte_propre_rend_un_conflit(self) -> None:
        """F16 (F1, S-01M4R8Y48QVARQT92YW6ACD9RG) : un REFUS — groupe couplé, même champ, tombe — dont la fusion texte
        rend 0 ⇒ code 3, %A laissé à la fusion texte, stderr nommant la combinaison ; une entrée HORS FORME garde le
        code de la fusion texte (0, et 4 sur un échec) ; un refus à rc 1 reste 3 ; un refus dont merge-file ÉCHOUE (rc
        129, %A abîmé, délai, lancement impossible) ⇒ 3, %A == « nous » (NO_GO de l'exec-critic de F1, option a). Tue
        le mutant F1 (`return rc`), le mutant « refus en échec ⇒ 4 » et le mutant « %A = nous aussi à rc 0 »."""
        refus = (
            ("groupe couplé", env(rec(depends_on=["T-1"], depends_motif={"T-1": "m"})), env(rec()),
             env(rec(depends_on=["T-1"], depends_motif={"T-1": "autre"}), ["o1"]), "record/depends_on+depends_motif"),
            ("même champ", env(rec(writeset=["a", "b", "c"])), env(rec(writeset=["A", "b", "c"])),
             env(rec(writeset=["a", "b", "C"])), "record/writeset"),
            ("tombe", env(rec()), env(None), env(rec(stage="x")), "record (tombe contre modification)"),
        )
        texte = b"fusion texte de merge-file, sans marqueur\n"
        for nom, b, n, e, combinaison in refus:
            with self.subTest(nom):
                jeu = self.jouer_main(b, n, e, rc_repli=0)
                self.assert_repli(jeu, canon(n))
                lignes = [ligne for ligne in jeu["err"].splitlines() if combinaison in ligne]
                self.assertEqual(2, len(lignes), jeu["err"])
                self.assertIn("rendue en CONFLIT", lignes[1])
                # Le CONTENU de %A à rc 0 : la fusion texte que merge-file y a écrite, GARDÉE — jamais remise
                # à « nous ». Tue le mutant « %A = nous aussi à rc 0 » (passe de correction finale de F1).
                jeu = self.jouer_main(b, n, e, rc_repli=0, ecrit=texte)
                self.assertEqual(3, jeu["rc"], jeu["err"])
                self.assertEqual(texte, jeu["A"], "%A remis à « nous » alors que merge-file a rendu 0")
        hors = (json.dumps(env(rec(stage="a")), indent=4, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        jeu = self.jouer_main(env(rec()), hors, env(rec(state="running")), rc_repli=0)
        self.assertEqual((0, 1), (jeu["rc"], jeu["run"].call_count), jeu["err"])
        self.assertNotIn("CONFLIT", jeu["err"])
        self.assertEqual(4, self.jouer_main(env(rec()), hors, env(rec(state="running")), rc_repli=129)["rc"])
        nous = env(rec(stage="a"))
        self.assertEqual(3, self.jouer_main(env(rec()), nous, env(rec(stage="b")), rc_repli=1)["rc"])
        echecs = (("rc 129", {"rc_repli": 129}), ("rc 129, %A abîmé", {"rc_repli": 129, "ecrit": b"<<<<<<< partiel"}),
                  ("délai", {"leve": subprocess.TimeoutExpired("git", 120)}),
                  ("lancement impossible", {"leve": OSError("simulé")}))
        for nom, effet in echecs:
            with self.subTest(nom):
                jeu = self.jouer_main(env(rec()), nous, env(rec(stage="b")), **effet)
                self.assertEqual(3, jeu["rc"], jeu["err"])
                self.assertEqual(canon(nous), jeu["A"], "%A n'est plus « nous » après un échec de merge-file")
                self.assertIn("conflit sur record/stage — la fusion texte a échoué", jeu["err"])

    def test_F17_cle_hostile_neutralisee_sur_stderr(self) -> None:
        """F17 (avis sécurité de F1) : une clé `\\x1b]0;PWNED\\x07` (ESC, BEL) ou porteuse de CR / LF, en conflit, à rc
        0 comme à rc 1 ⇒ AUCUN octet 0x1b, 0x07 ni CR sur stderr, une ligne par message, la clé nommée ÉCHAPPÉE. Tue
        le mutant « `_stderr` écrit le texte brut »."""
        for cle in ("\x1b]0;PWNED\x07", "x\rfusion par champ : fusion ecrite\nfaux"):
            echappee = cle.encode("unicode_escape").decode("ascii")
            for rc_repli, lignes in ((0, 2), (1, 1)):
                with self.subTest(cle=echappee, rc_repli=rc_repli):
                    jeu = self.jouer_main(*(env(rec(**{cle: v})) for v in ("o", "n", "e")), rc_repli=rc_repli)
                    self.assertEqual(3, jeu["rc"], jeu["err"])
                    for octet in ("\x1b", "\x07", "\r"):
                        self.assertNotIn(octet, jeu["err"])
                    self.assertEqual(lignes, jeu["err"].count("\n"), jeu["err"])
                    self.assertIn(f"conflit sur record/{echappee} —", jeu["err"])

    def test_T_imports_stdlib_seule_aucun_cadre(self) -> None:
        """T-imports : l'AST du pilote n'importe que la stdlib, jamais `cadre`. Tue m23."""
        noms: set[str] = set()
        for noeud in ast.walk(ast.parse(PILOTE.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Import):
                noms.update(a.name.split(".")[0] for a in noeud.names)
            elif isinstance(noeud, ast.ImportFrom):
                self.assertEqual(0, noeud.level, "import relatif")
                noms.add((noeud.module or "").split(".")[0])
        self.assertNotIn("cadre", noms)
        self.assertEqual([], sorted(n for n in noms if n not in sys.stdlib_module_names))


class BalayageParPairesTests(_Banc):
    """F12e (D2) : paires ORDONNÉES de mutations VALIDES SEULES d'un enregistrement, contre les validateurs RÉELS."""

    VOISIN = {"id": "T-1", "task": "T-1", "state": "running", "parallel_group": "PG-0001", "writeset": ["a.py"],
              "updated": JOUR}

    def valide(self, record: dict[str, Any]) -> bool:
        try:
            tasks._valider_board(Path("f12e"), {"tasks": [copy.deepcopy(self.VOISIN), copy.deepcopy(record)]})
        except tasks.BoardError:
            return False
        return True

    @staticmethod
    def muter(base: dict[str, Any], **champs: Any) -> dict[str, Any]:
        r = copy.deepcopy(base)
        for cle, valeur in champs.items():
            if valeur is None:
                r.pop(cle, None)
            else:
                r[cle] = valeur
        return r

    def mutations(self, b: dict[str, Any]) -> dict[str, dict[str, Any]]:
        m = self.muter
        return {
            "state=running": m(b, state="running"), "state=blocked": m(b, state="blocked"),
            "state=done": m(b, state="done"), "groupe=PG-0002": m(b, parallel_group="PG-0002"),
            "groupe retiré": m(b, parallel_group=None), "stage": m(b, stage="revue"), "owner": m(b, owner="o"),
            "writeset": m(b, writeset=["c.py"]), "blocked_on": m(b, blocked_on="T-7"), "chantier": m(b, chantier="c"),
            "epic": m(b, epic="E-01"), "updated": m(b, updated="2026-10-12"), "task": m(b, task="autre"),
            "depends+motif": m(b, depends_on=["T-1", "T-9"], depends_motif={"T-1": "m", "T-9": "n"}),
            "depends_on seul": m(b, depends_on=["T-1", "T-9"]), "motif réécrit": m(b, depends_motif={"T-1": "autre"}),
            "arête retirée": m(b, depends_on=None, depends_motif=None), "depends_on vidé": m(b, depends_on=[]),
            "motif ajouté": m(b, depends_motif={"T-1": "m"}),
        }

    def test_F12e_aucune_fusion_ne_produit_un_enregistrement_que_load_refuse(self) -> None:
        """Tue m13 (8 fusions refusées au prototype) ; m25 sans objet depuis C42 (couple `parallel_group`+`state`).
        Borne : un invariant sans mutation dans la table, ou inter-fichiers, n'est pas vu."""
        b1 = {"id": "T-3", "task": "T-3", "state": "pending", "parallel_group": "PG-0001", "writeset": ["b.py"],
              "stage": "", "owner": "", "depends_on": ["T-1"], "depends_motif": {"T-1": "m"}, "updated": JOUR}
        b2 = {k: v for k, v in b1.items() if k != "depends_motif"}
        compte = {"paires": 0, "conflits": 0, "valides": 0}
        refusees = []
        tailles = {}
        for nom_base, base in (("arête+motif", b1), ("arête sans motif", b2)):
            self.assertTrue(self.valide(base))
            table = {k: v for k, v in self.mutations(base).items() if v != base and self.valide(v)}
            tailles[nom_base] = len(table)
            for (i, ri), (j, rj) in itertools.permutations(table.items(), 2):
                compte["paires"] += 1
                try:
                    res = P.fusionner(env(base), env(ri), env(rj))
                except P.Conflit:
                    compte["conflits"] += 1
                    continue
                if self.valide(res["record"]):
                    compte["valides"] += 1
                else:
                    refusees.append(f"{nom_base} : {i} × {j}")
        self.assertEqual([], refusees, compte)
        # ÉPINGLÉ (réserve de l'exec-critic de T-01M4JN4ZSWAX5MGSGQNPPYZG68, passe de correction F5) : un validateur qui
        # change rétrécissait la table EN SILENCE sous un seuil `> 400`. 17 et 19 mutations valides seules, soit
        # 17×16 + 19×18 = 614 paires ordonnées : un écart ici se relit, il ne se corrige pas par le nombre.
        self.assertEqual({"arête+motif": 17, "arête sans motif": 19}, tailles, compte)
        self.assertEqual(614, compte["paires"], compte)
        self.assertGreater(compte["valides"], 0, compte)
        self.assertGreater(compte["conflits"], 0, compte)

    def test_F12e_ledger_aucun_couple(self) -> None:
        """Au ledger, chaque invariant d'entrée lit UN champ : toute fusion sans conflit passe `_validate_entries`."""
        base = entree()
        table = {"category": entree(category=ledger.CATEGORIES[1]), "status": entree(status=ledger.STATUSES[1]),
                 "title": entree(title="autre"), "tags": entree(tags=["x"]), "text": entree(text="t"),
                 "related": entree(related="T-1"), "created": entree(created="2026-10-12")}
        env_l = lambda r: {"format": 1, "id": ENTREE_ID, "record": r}  # noqa: E731
        refusees = []
        for (i, ri), (j, rj) in itertools.permutations(table.items(), 2):
            try:
                res = P.fusionner(env_l(base), env_l(ri), env_l(rj))
            except P.Conflit:
                continue
            try:
                ledger._validate_entries([copy.deepcopy(res["record"])], ["f12e"])
            except ledger.LedgerError:
                refusees.append(f"{i} × {j}")
        self.assertEqual([], refusees)


def libelle_saut(sonde: dict[str, str]) -> str:
    """Le libellé du saut des témoins git, fidèle au VERDICT (réserve de l'exec-critic, passe de correction F5) : une
    sonde « impossible » (préparation ratée) n'est jamais dite « capacité absente »."""
    verdict = sonde.get("verdict")
    nature = "capacité git absente" if verdict == "absent" else f"sonde git {verdict or 'sans verdict'}, capacité NON jugée"
    return f"{nature} selon sonder_git() : {P.raison_sonde(sonde)}"


class _Depots(_Banc):
    """Témoins qui EXÉCUTENT git : ils SAUTENT si `sonder_git()` ne rend pas « tout présent », et seulement alors —
    libellé fidèle au verdict (`libelle_saut`)."""

    def setUp(self) -> None:
        super().setUp()
        if SONDE.get("verdict") != "tout présent":
            self.skipTest(libelle_saut(SONDE))

    @staticmethod
    def identite(d: Path) -> None:
        for cle, valeur in (("user.email", "banc@example.invalid"), ("user.name", "banc"),
                            ("commit.gpgsign", "false"), ("core.hooksPath", os.devnull)):
            git(d, "config", cle, valeur)

    def depot(self, nom: str, *, pilote_suivi: bool = True, attributs: str = ATTR) -> Path:
        d = self.tmp / nom
        d.mkdir(parents=True)
        git(d, "-c", "init.defaultBranch=main", "init", "-q")
        self.identite(d)
        (d / ".gitignore").write_text("/.agents/state/local/\n", encoding="utf-8")
        (d / ".gitattributes").write_text(attributs, encoding="utf-8")
        if pilote_suivi:
            (d / SUIVI_REL).parent.mkdir(parents=True)
            (d / SUIVI_REL).write_bytes(PILOTE.read_bytes())
        return d

    @staticmethod
    def board(d: Path, taches: list[dict[str, Any]]) -> None:
        (d / BOARD_REL).mkdir(parents=True, exist_ok=True)
        (d / BOARD_REL / "TASKS.json").write_bytes(canon({"tasks": taches}))
        tasks.migrate_store(str(d))

    @staticmethod
    def commit(d: Path, message: str) -> None:
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", message)

    def clone(self, origine: Path, nom: str) -> Path:
        c = self.tmp / nom
        git(self.tmp, "clone", "-q", str(origine), str(c))
        self.identite(c)
        return c

    def socle(self, nom: str, taches: list[dict[str, Any]] | None = None, **kw: Any) -> Path:
        d = self.depot(nom, **kw)
        self.board(d, taches or [rec("T-1"), rec("T-3"), rec("T-5")])
        self.commit(d, "socle")
        return d

    def s1(self, d: Path) -> None:
        """S1 de M3 : `stage` de T-3 sur main, `state` de T-3 sur b ; retour sur main."""
        git(d, "branch", "b")
        tasks.stage_task(str(d), "T-3", "revue")
        self.commit(d, "A : stage")
        git(d, "checkout", "-q", "b")
        tasks.set_state(str(d), "T-3", "running")
        self.commit(d, "B : state")
        git(d, "checkout", "-q", "main")

    def installer(self, racine: Path, depuis: str | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", _Terminal()), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            rc = P.installer(racine=str(racine), depuis=depuis)
        return rc, out.getvalue(), err.getvalue()

    def verifier(self, racine: Path) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = P.verifier(racine=str(racine))
        return rc, out.getvalue()

    @staticmethod
    def armer(d: Path, valeur: str) -> None:
        git(d, "config", "merge.cadre-enregistrement.driver", valeur)

    def copie(self) -> Path:
        octets = PILOTE.read_bytes()
        c = self.tmp / "hors-arbre" / f"fusion_enregistrement-{hashlib.sha256(octets).hexdigest()[:16]}.py"
        c.parent.mkdir(exist_ok=True)
        c.write_bytes(octets)
        return c

    @staticmethod
    def record(d: Path, tid: str) -> Any:
        return json.loads((d / BOARD_REL / "tasks" / f"{tid}.json").read_bytes())["record"]

    @staticmethod
    def t3(d: Path) -> bytes:
        return (d / BOARD_REL / "tasks" / "T-3.json").read_bytes()

    @staticmethod
    def non_fusionnes(d: Path) -> list[str]:
        return [Path(c).name for c in git(d, "diff", "--name-only", "--diff-filter=U").stdout.split()]

    @staticmethod
    def commun(d: Path) -> Path:
        return Path(git(d, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())

    def rien_ecrit(self, d: Path) -> None:
        self.assertEqual("", git(d, "config", "--local", "--get-regexp", r"^merge\.", check=False).stdout)
        self.assertFalse((self.commun(d) / "cadre").exists())


class FusionGitTests(_Depots):
    def test_G1_S1_fusionne_avec_la_copie_installee_et_conflicte_sans(self) -> None:
        """G1 : S1 + copie installée ⇒ rc 0, `load` == T-3 running / revue ; BRAS DE CONTRÔLE, attribut sans config
        ⇒ rc 1 (M2). Tue m1."""
        d = self.socle("g1")
        self.s1(d)
        rc, _, err = self.installer(d)
        self.assertEqual(0, rc, err)
        m = git(d, "merge", "--no-edit", "b", check=False)
        self.assertEqual(0, m.returncode, m.stdout + m.stderr)
        charge = {t["id"]: (t["state"], t["stage"]) for t in tasks.load(str(d))["tasks"]}
        self.assertEqual(("running", "revue"), charge["T-3"])
        controle = self.socle("g1-controle")
        self.s1(controle)
        self.assertEqual(1, git(controle, "merge", "--no-edit", "b", check=False).returncode)

    def test_G2_conflit_reel_memes_octets_que_sans_pilote_trois_styles(self) -> None:
        """G2 (a) (MG3) : même `stage`, deux valeurs ; deux `git clone`, un seul armé ⇒ rc 1, octets == sans pilote,
        styles merge, diff3, zdiff3. Tue m11."""
        o = self.socle("g2-origine", [rec("T-3")])
        git(o, "branch", "b")
        tasks.stage_task(str(o), "T-3", "ici")
        self.commit(o, "ici")
        git(o, "checkout", "-q", "b")
        tasks.stage_task(str(o), "T-3", "là")
        self.commit(o, "là")
        git(o, "checkout", "-q", "main")
        avec, sans = self.clone(o, "g2-avec"), self.clone(o, "g2-sans")
        rc, _, err = self.installer(avec)
        self.assertEqual(0, rc, err)
        for style in ("merge", "diff3", "zdiff3"):
            res = {}
            for nom, c in (("avec", avec), ("sans", sans)):
                m = git(c, "-c", f"merge.conflictStyle={style}", "merge", "--no-edit", "origin/b", check=False)
                res[nom] = (m.returncode, self.t3(c))
                git(c, "merge", "--abort")
            with self.subTest(style=style):
                self.assertEqual(1, res["avec"][0])
                self.assertEqual(res["sans"], res["avec"])

    def test_G2b_fixture_discriminante_histogram(self) -> None:
        """G2 (b) (MG2) : fixture de 11 lignes hors forme ⇒ repli ⇒ octets == `git merge` sans pilote ; la fixture
        DISCRIMINE (merge-file par défaut ≠ histogram), sinon rouge au kit, saut ailleurs. Tue m14."""
        lignes = {"base": ["x", "  [", "}", "},"], "nous": ["x", "  [", "}"], "eux": ["},", "x", "x", "},"]}
        fichiers = {}
        for nom, contenu in lignes.items():
            fichiers[nom] = self.tmp / f"mg2-{nom}"
            fichiers[nom].write_text("\n".join(contenu) + "\n", encoding="utf-8")
        sorties = [git(self.tmp, "merge-file", "-p", *algo, str(fichiers["nous"]), str(fichiers["base"]),
                       str(fichiers["eux"]), check=False).stdout for algo in ([], ["--diff-algorithm=histogram"])]
        if sorties[0] == sorties[1]:
            if MARQUEUR_KIT.is_file():
                self.fail("la fixture MG2 ne discrimine plus myers / histogram sous ce git : G2b serait vacuous")
            self.skipTest("fixture MG2 non discriminante sous ce git")
        o = self.depot("g2b-origine")
        cible = o / BOARD_REL / "tasks" / "T-9.json"
        cible.parent.mkdir(parents=True)
        cible.write_bytes(fichiers["base"].read_bytes())
        self.commit(o, "base")
        git(o, "branch", "b")
        cible.write_bytes(fichiers["nous"].read_bytes())
        self.commit(o, "nous")
        git(o, "checkout", "-q", "b")
        cible.write_bytes(fichiers["eux"].read_bytes())
        self.commit(o, "eux")
        git(o, "checkout", "-q", "main")
        avec, sans = self.clone(o, "g2b-avec"), self.clone(o, "g2b-sans")
        rc, _, err = self.installer(avec)
        self.assertEqual(0, rc, err)
        res = [(git(c, "merge", "--no-edit", "origin/b", check=False).returncode,
                (c / BOARD_REL / "tasks" / "T-9.json").read_bytes()) for c in (avec, sans)]
        self.assertEqual(1, res[0][0])
        self.assertEqual(res[1], res[0])

    def test_G3_tombe_contre_modification_conflicte(self) -> None:
        """G3 : `delete` de T-3 ici, `stage` de T-3 là ⇒ rc 1. Tue m4."""
        d = self.socle("g3", [rec("T-1"), rec("T-3")])
        rc, _, err = self.installer(d)
        self.assertEqual(0, rc, err)
        git(d, "branch", "b")
        tasks.delete_task(str(d), "T-3")
        self.commit(d, "tombe")
        git(d, "checkout", "-q", "b")
        tasks.stage_task(str(d), "T-3", "x")
        self.commit(d, "stage")
        git(d, "checkout", "-q", "main")
        self.assertEqual(1, git(d, "merge", "--no-edit", "b", check=False).returncode)
        self.assertIn("T-3.json", self.non_fusionnes(d))

    def test_G4_rebase_de_S1(self) -> None:
        """G4 : `rebase` de S1 ⇒ rc 0 (EFFET : la fusion texte conflicte)."""
        d = self.socle("g4")
        rc, _, err = self.installer(d)
        self.assertEqual(0, rc, err)
        self.s1(d)
        git(d, "checkout", "-q", "b")
        r = git(d, "rebase", "main", check=False)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(("running", "revue"), (self.record(d, "T-3")["state"], self.record(d, "T-3")["stage"]))

    def _g5(self, nom: str, relatif: bool) -> tuple[int, bool, Any]:
        d = self.socle(f"{nom} o'ri %A", [rec("T-1"), rec("T-3")])
        if relatif:
            self.armer(d, P.commande_driver(sys.executable, SUIVI_REL.as_posix()))
        else:
            rc, _, err = self.installer(d)
            self.assertEqual(0, rc, err)
        git(d, "branch", "b")
        sentinelle = self.tmp / f"{nom}-SENTINELLE"
        texte = (d / SUIVI_REL).read_text(encoding="utf-8")
        ancre = 'if __name__ == "__main__":'
        self.assertEqual(1, texte.count(ancre))
        marque = f"Path({str(sentinelle)!r}).write_text('amont', encoding='utf-8')\n"
        (d / SUIVI_REL).write_text(texte.replace(ancre, marque + ancre), encoding="utf-8")
        tasks.stage_task(str(d), "T-3", "revue")
        self.commit(d, "amont : pilote modifié + stage")
        lie = self.tmp / f"{nom} l'ie %A"
        git(d, "worktree", "add", "-q", str(lie), "b")
        tasks.set_state(str(lie), "T-3", "running")
        self.commit(lie, "b : state")
        r = git(lie, "rebase", "main", check=False)
        return r.returncode, sentinelle.exists(), (self.record(lie, "T-3") if r.returncode == 0 else None)

    def test_G5_la_copie_tourne_jamais_la_version_de_l_amont(self) -> None:
        """G5 (K6) : worktree LIÉ, chemins à espace, apostrophe ET `%A` ; l'amont réécrit le pilote suivi en une
        version à SENTINELLE ; `rebase` ⇒ rc 0 ET sentinelle ABSENTE (deux EFFETS) ; BRAS DE CONTRÔLE, chemin relatif
        suivi ⇒ sentinelle PRÉSENTE. Tue m7 et m22."""
        rc, sentinelle, record = self._g5("g5", relatif=False)
        self.assertEqual(0, rc)
        self.assertEqual(("running", "revue"), (record["state"], record["stage"]))
        self.assertFalse(sentinelle, "la version du pilote apportée par l'amont a tourné")
        self.assertTrue(self._g5("g5c", relatif=True)[1], "contrôle : le chemin relatif suivi doit exécuter l'amont")

    def test_G6_attributs_reels_trois_motifs_et_rien_d_autre(self) -> None:
        """G6 (kit) : `check-attr merge` sur une copie du VRAI `.gitattributes`. Tue m10."""
        self.exiger_kit()
        d = self.depot("g6", pilote_suivi=False, attributs=(REPO / ".gitattributes").read_text(encoding="utf-8"))
        vises = ["board/tasks/T-1.json", "board/epics/E-01.json", "memory/entries/L-1.json"]
        hors = ["board/archive/tasks/T-1.json", "board/TASKS.json", "board/sync_outbox/0001-op.json",
                "board/tombes.jsonl"]
        chemins = [f".agents/state/{c}" for c in vises + hors]
        lu = git(d, "check-attr", "merge", "--", *chemins).stdout.splitlines()
        attendu = [f"{c}: merge: {'cadre-enregistrement' if i < len(vises) else 'unspecified'}"
                   for i, c in enumerate(chemins)]
        self.assertEqual(attendu, lu)


class ActeursGitTests(_Depots):
    def test_stage_actor_atomique_et_git_uu(self) -> None:
        """T-01M5DBFK3XKKM2VHQM5RE4TP6K, lot C, dans git : Alice démarre T-3 ici, Bob là, MÊME stage, par l'API du
        lot A ⇒ `git merge` rc 1, T-3 `UU`, versions :2: et :3: portant chacune SON acteur entier, stderr « double
        démarrage » caviardé. Tue : appel de `_juger_acteurs` retiré, caviardage retiré."""
        d = self.socle("acteurs-uu", [rec("T-1"), rec("T-3")])
        rc, _, err = self.installer(d)
        self.assertEqual(0, rc, err)
        alice = acteur(f"Alice {SECRET}", "alice@example.invalid", "a1a1a1a1a1a1a1a1")
        git(d, "branch", "b")
        tasks.set_state(str(d), "T-3", "running", stage="dev", acteur=alice)
        self.commit(d, "Alice : start")
        git(d, "checkout", "-q", "b")
        tasks.set_state(str(d), "T-3", "running", stage="dev", acteur=BOB)
        self.commit(d, "Bob : start")
        git(d, "checkout", "-q", "main")
        m = git(d, "merge", "--no-edit", "b", check=False)
        self.assertEqual(1, m.returncode, m.stdout + m.stderr)
        self.assertEqual(["T-3.json"], self.non_fusionnes(d))
        chemin = (BOARD_REL / "tasks" / "T-3.json").as_posix()
        for etage, attendu in ((2, alice), (3, BOB)):
            record = json.loads(git(d, "show", f":{etage}:{chemin}").stdout)["record"]
            with self.subTest(etage=etage):
                self.assertEqual((attendu, attendu), (record["start_actor"], record["stage_actor"]))
        self.assertIn("conflit sur record/start_actor (double démarrage : nous Alice [caviardé] <", m.stderr)
        self.assertNotIn(SECRET, m.stderr)

    def test_double_demarrage_base_attribuee_git_jamais_de_chimere(self) -> None:
        """Base attribuée à Xavier ; Xavier redémarre sur une autre copie ici, Bob sur la copie de base là. Les hunks
        texte ne se touchent pas : merge-file fusionnerait PROPREMENT la chimère « auteur de Bob, copie d'ici ».
        `git merge` ⇒ rc 1, `UU`, et %A == notre version ENTIÈRE (aucun marqueur à attendre). Tue le mutant « %A
        laissé à la fusion texte sur un refus des acteurs »."""
        ici = acteur("Xavier", "xavier@example.invalid", "d3d3d3d3d3d3d3d3")
        la = acteur("Bob", "bob@example.invalid", "c0c0c0c0c0c0c0c0")
        d = self.depot("acteurs-chimere")
        cible = d / BOARD_REL / "tasks" / "T-3.json"
        cible.parent.mkdir(parents=True)
        cible.write_bytes(canon(env(rec(state="running", stage="dev", start_actor=XAVIER))))
        self.commit(d, "base attribuée")
        rc, _, err = self.installer(d)
        self.assertEqual(0, rc, err)
        git(d, "branch", "b")
        nous = canon(env(rec(state="running", stage="dev", start_actor=ici)))
        cible.write_bytes(nous)
        self.commit(d, "ici : Xavier, autre copie")
        git(d, "checkout", "-q", "b")
        cible.write_bytes(canon(env(rec(state="running", stage="dev", start_actor=la))))
        self.commit(d, "là : Bob, copie de base")
        git(d, "checkout", "-q", "main")
        m = git(d, "merge", "--no-edit", "b", check=False)
        self.assertEqual(1, m.returncode, m.stdout + m.stderr)
        self.assertEqual(["T-3.json"], self.non_fusionnes(d))
        self.assertIn("%A garde « nous » ENTIER", m.stderr)
        self.assertEqual(nous, cible.read_bytes())


class FailClosedTests(_Depots):
    def test_G7_commande_fail_closed_trois_bras_controle_et_branche_hostile(self) -> None:
        """G7 : copie ABSENTE, CASSÉE, interpréteur ABSENT ⇒ rc 1, `UU`, MARQUEURS, octets == sans pilote ; CONTRÔLE
        (commande sans son segment de repli) ⇒ `UU` SANS marqueurs, fichier == « nous » ; sain ⇒ rc 0 ; branche
        `b$(touch${IFS}PWNED)` ⇒ PWNED absent, label verbatim. Tue m12."""
        o = self.socle("g7")
        self.s1(o)
        git(o, "branch", HOSTILE, "b")
        absente = self.tmp / "absente" / "fusion_enregistrement.py"
        cassee = self.tmp / "cassee.py"
        cassee.write_text("def (:\n", encoding="utf-8")
        sans = self.clone(o, "g7-sans")
        self.assertEqual(1, git(sans, "merge", "--no-edit", "origin/b", check=False).returncode)
        attendu = self.t3(sans)
        bras = (("copie absente", sys.executable, absente), ("copie cassée", sys.executable, cassee),
                ("interpréteur absent", str(self.tmp / "absent" / "python3"), self.copie()))
        for i, (nom, py, copie) in enumerate(bras):
            c = self.clone(o, f"g7-{i}")
            self.armer(c, P.commande_driver(str(py), str(copie)))
            with self.subTest(nom):
                self.assertEqual(1, git(c, "merge", "--no-edit", "origin/b", check=False).returncode)
                self.assertIn("UU ", git(c, "status", "--porcelain").stdout)
                self.assertIn(b"<<<<<<< ", self.t3(c))
                self.assertEqual(attendu, self.t3(c))
        c = self.clone(o, "g7-controle")
        self.armer(c, P.commande_driver(sys.executable, str(absente)).split("; rc=$?", 1)[0])
        self.assertEqual(1, git(c, "merge", "--no-edit", "origin/b", check=False).returncode)
        self.assertIn("UU ", git(c, "status", "--porcelain").stdout)
        self.assertNotIn(b"<<<<<<<", self.t3(c))
        self.assertEqual(git(c, "show", f"HEAD:{(BOARD_REL / 'tasks' / 'T-3.json').as_posix()}").stdout.encode("utf-8"),
                         self.t3(c))
        c = self.clone(o, "g7-sain")
        self.armer(c, P.commande_driver(sys.executable, str(self.copie())))
        self.assertEqual(0, git(c, "merge", "--no-edit", "origin/b", check=False).returncode)
        c = self.clone(o, "g7-hostile")
        self.armer(c, P.commande_driver(sys.executable, str(absente)))
        self.assertEqual(1, git(c, "merge", "--no-edit", f"origin/{HOSTILE}", check=False).returncode)
        self.assertFalse((c / "PWNED").exists())
        self.assertIn(f">>>>>>> origin/{HOSTILE}\n", self.t3(c).decode("utf-8"))

    def test_G7_bras_rebase_sujet_hostile_en_diff3(self) -> None:
        """G7, bras `rebase` (S5) : sujet `x'$(touch PWNED)'` sur l'amont ET le rejoué, copie absente, diff3 ⇒ conflit
        AVEC marqueurs, PWNED absent, `%S` et `%Y` verbatim. Tue m33."""
        d = self.socle("g7-rebase", [rec("T-1"), rec("T-3")])
        git(d, "branch", "b")
        sujet = "x'$(touch PWNED)'"
        tasks.stage_task(str(d), "T-3", "revue")
        self.commit(d, sujet)
        git(d, "checkout", "-q", "b")
        tasks.set_state(str(d), "T-3", "running")
        self.commit(d, sujet)
        rejoue = git(d, "rev-parse", "--short", "b").stdout.strip()
        self.armer(d, P.commande_driver(sys.executable, str(self.tmp / "absente" / "fusion_enregistrement.py")))
        r = git(d, "-c", "merge.conflictStyle=diff3", "rebase", "main", check=False)
        texte = self.t3(d).decode("utf-8")
        git(d, "rebase", "--abort", check=False)
        self.assertNotEqual(0, r.returncode)
        self.assertFalse((d / "PWNED").exists(), "le sujet hostile a été exécuté par le segment de repli")
        self.assertIn(f"||||||| parent of {rejoue} ({sujet})\n", texte)
        self.assertIn(f">>>>>>> {rejoue} ({sujet})\n", texte)

    def _g8(self, installe: bool) -> tuple[subprocess.CompletedProcess, list[str]]:
        d = self.socle(f"g8-{installe}", [rec("T-1"), rec("T-2"), rec("T-3", depends_on=["T-1"])])
        if installe:
            rc, _, err = self.installer(d)
            self.assertEqual(0, rc, err)
        git(d, "branch", "b")
        tasks.delete_task(str(d), "T-1")
        self.commit(d, "A : delete T-1")
        git(d, "checkout", "-q", "b")
        tasks.set_depends(str(d), "T-3", ["T-1"], motif="raison donnée après coup")
        self.commit(d, "B : motif")
        git(d, "checkout", "-q", "main")
        m = git(d, "merge", "--no-edit", "b", check=False)
        return m, self.non_fusionnes(d)

    def test_G8_groupe_depends_de_bout_en_bout(self) -> None:
        """G8 (MB) : `delete` de l'amont ici, `set_depends --motif` de l'aval là ⇒ rc 1, `UU` sur T-3, stderr du
        pilote nommant `depends_on+depends_motif` ; sans pilote ⇒ rc 1 aussi. Tue m13."""
        m, conflits = self._g8(True)
        self.assertEqual(1, m.returncode)
        self.assertIn("T-3.json", conflits)
        self.assertIn("depends_on+depends_motif", m.stderr + m.stdout)
        self.assertEqual(1, self._g8(False)[0].returncode)

    def _g9(self, installe: bool) -> tuple[subprocess.CompletedProcess, list[str], int]:
        taches = [rec(t, writeset=[f"{t}.py"]) for t in ("T-1", "T-3", "T-5")]
        d = self.depot(f"g9-{installe}")
        self.board(d, taches)
        tasks.declare_parallel_group(str(d), ["T-1", "T-3"])
        tasks.set_state(str(d), "T-1", "running")
        self.commit(d, "socle")
        if installe:
            rc, _, err = self.installer(d)
            self.assertEqual(0, rc, err)
        git(d, "branch", "b")
        tasks.set_state(str(d), "T-3", "running")
        self.commit(d, "A : start T-3")
        git(d, "checkout", "-q", "b")
        tasks.declare_parallel_group(str(d), ["T-3", "T-5"])
        self.commit(d, "B : parallel T-3 T-5")
        git(d, "checkout", "-q", "main")
        m = git(d, "merge", "--no-edit", "b", check=False)
        parents = len(git(d, "rev-list", "--parents", "-n1", "HEAD").stdout.split()) - 1
        return m, self.non_fusionnes(d), parents

    def test_G9_groupe_state_parallel_group_de_bout_en_bout(self) -> None:
        """G9 (C42) : `start T-3` ici, `parallel T-3 T-5` là ⇒ pilote : rc 0, commit de fusion, T-3 `running` dans le
        groupe neuf, relu par `load` ; sans pilote ⇒ rc 1. Tue le mutant « couple (parallel_group, state) rétabli »."""
        m, conflits, parents = self._g9(True)
        self.assertEqual((0, 2, []), (m.returncode, parents, conflits), m.stdout + m.stderr)
        t3, t5 = (self.record(self.tmp / "g9-True", t) for t in ("T-3", "T-5"))
        self.assertEqual(("running", t5["parallel_group"]), (t3["state"], t3["parallel_group"]))
        tasks.load(str(self.tmp / "g9-True"))
        self.assertEqual(1, self._g9(False)[0].returncode)

    def _g9b(self, nom: str, installe: bool, ici: dict[str, Any], la: dict[str, Any],
             armer: str | None = None) -> tuple[Any, Path]:
        """Socle : T-3 dépend de T-1 et T-5, motif sur T-1 seul ; chaque côté RÉÉCRIT l'enveloppe de T-3 en forme
        canonique, sans verbe de `tasks` : `ici` sur main, `la` sur b PLUS une opération (b SEUL) — aucune ligne ne se
        touche. `armer` : une valeur `driver` posée TELLE QUELLE au lieu de `--installer`."""
        d = self.depot(f"{nom}-{installe}")
        self.board(d, [rec("T-1", writeset=["T-1.py"]), rec("T-3", writeset=["a.py", "b.py", "c.py", "d.py"],
                       depends_on=["T-1", "T-5"], depends_motif={"T-1": "m"}), rec("T-5", writeset=["T-5.py"])])
        self.commit(d, "socle")
        if installe:
            rc, _, err = self.installer(d)
            self.assertEqual(0, rc, err)
        elif armer is not None:
            self.armer(d, armer)
        git(d, "branch", "b")
        chemin = d / BOARD_REL / "tasks" / "T-3.json"
        for branche, champs, ops in (("main", ici, []), ("b", la, ["op-la"])):
            git(d, "checkout", "-q", branche)
            enveloppe = json.loads(chemin.read_bytes())
            enveloppe["record"].update(champs)
            enveloppe["sync_operations"].extend(ops)
            chemin.write_bytes(canon(enveloppe))
            self.commit(d, f"{branche} : T-3 réécrit")
        git(d, "checkout", "-q", "main")
        return git(d, "merge", "--no-edit", "b", check=False), d

    def test_G9b_groupe_couple_operations_d_un_seul_cote(self) -> None:
        """G9b (F1, S-01M4R8Y48QVARQT92YW6ACD9RG) : motif ajouté sur T-5 ici, arête T-5 retirée + une opération LÀ
        SEULEMENT ⇒ la fusion texte rend 0 ; avec la copie ⇒ rc 1, AUCUN commit de fusion, T-3 non fusionné (étages
        1-2-3, sans marqueur, `git commit` refusé), stderr nommant `depends_on+depends_motif` ; CONTRÔLE sans pilote ⇒
        rc 0 et `load` refuse le board (motif hors des arêtes) : la fixture reproduit le défaut. Tue le mutant F1."""
        ici, la = G9B_ICI, G9B_LA
        m, d = self._g9b("g9b", True, ici, la)
        self.assertEqual(1, m.returncode, m.stdout + m.stderr)
        self.assertEqual(1, len(git(d, "rev-list", "--parents", "-n1", "HEAD").stdout.split()) - 1)
        self.assertIn("T-3.json", self.non_fusionnes(d))
        etages = sorted(ligne.split()[2] for ligne in git(d, "ls-files", "-u").stdout.splitlines())
        self.assertEqual(["1", "2", "3"], etages)
        self.assertNotIn(b"<<<<<<<", self.t3(d))
        self.assertIn("depends_on+depends_motif", m.stderr + m.stdout)
        self.assertNotEqual(0, git(d, "commit", "--no-edit", check=False).returncode)
        m, d = self._g9b("g9b", False, ici, la)
        self.assertEqual(0, m.returncode, m.stdout + m.stderr)
        with self.assertRaises(tasks.BoardError) as cm:
            tasks.load(str(d))
        self.assertIn("invalid depends_motif", str(cm.exception))

    def test_G9c_meme_champ_aux_deux_bouts_d_une_liste(self) -> None:
        """G9c (F1) : `writeset` changé au PREMIER élément ici, au DERNIER là ⇒ fusion texte propre ; avec la copie ⇒
        rc 1, T-3 non fusionné, stderr nommant `record/writeset` ; CONTRÔLE sans pilote ⇒ rc 0, les deux bouts
        combinés. Tue le mutant F1."""
        ici, la = {"writeset": ["A.py", "b.py", "c.py", "d.py"]}, {"writeset": ["a.py", "b.py", "c.py", "D.py"]}
        m, d = self._g9b("g9c", True, ici, la)
        self.assertEqual(1, m.returncode, m.stdout + m.stderr)
        self.assertIn("T-3.json", self.non_fusionnes(d))
        self.assertIn("record/writeset", m.stderr + m.stdout)
        m, d = self._g9b("g9c", False, ici, la)
        self.assertEqual(0, m.returncode, m.stdout + m.stderr)
        self.assertEqual(["A.py", "b.py", "c.py", "D.py"], self.record(d, "T-3")["writeset"])

    def test_G9d_refus_et_merge_file_en_echec_dans_le_pilote(self) -> None:
        """G9d (NO_GO de l'exec-critic de F1, option a) : fixture de G9b, commande armée par `commande_driver` dont
        l'interpréteur est une ENVELOPPE qui met un `git` factice (merge-file ⇒ 129) en tête du PATH du SEUL pilote —
        git place son exec-path, qui porte un `git`, devant tout PATH : le repli shell garde le vrai git. ⇒ rc 1, AUCUN
        commit de fusion, T-3 non fusionné et == « nous », stderr nommant `depends_on+depends_motif`. L'ancien code
        (refus en échec ⇒ 4) laissait le repli shell fusionner : motif hors des arêtes. Tue ce mutant."""
        faux = self.tmp / "faux-bin"
        faux.mkdir()
        trace = self.tmp / "merge-file-du-pilote"
        vrai = shlex.quote(shutil.which("git") or "git")
        (faux / "git").write_text(f'#!/bin/sh\nif [ "$1" = merge-file ]; then\n  : > {shlex.quote(str(trace))}\n'
                                  f'  exit 129\nfi\nexec {vrai} "$@"\n', encoding="utf-8")
        enveloppe = faux / "python-du-pilote"
        enveloppe.write_text(f'#!/bin/sh\nPATH={shlex.quote(str(faux))}:"$PATH"\nexport PATH\n'
                             f'exec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8")
        for script in (faux / "git", enveloppe):
            script.chmod(0o755)
        armee = P.commande_driver(str(enveloppe), str(self.copie()))
        m, d = self._g9b("g9d", False, G9B_ICI, G9B_LA, armer=armee)
        self.assertTrue(trace.exists(), "le merge-file du pilote n'a pas touché le git factice : témoin vacuous")
        self.assertEqual(1, m.returncode, m.stdout + m.stderr)
        self.assertEqual(1, len(git(d, "rev-list", "--parents", "-n1", "HEAD").stdout.split()) - 1)
        self.assertIn("T-3.json", self.non_fusionnes(d))
        nous = git(d, "show", f"HEAD:{(BOARD_REL / 'tasks' / 'T-3.json').as_posix()}").stdout.encode("utf-8")
        self.assertEqual(nous, self.t3(d))
        self.assertIn("depends_on+depends_motif", m.stderr + m.stdout)


class InstallationTests(_Depots):
    def test_I1_sans_terminal_refus_rien_d_ecrit(self) -> None:
        """I1 : `--installer` en sous-processus, stdin = `os.devnull` ⇒ rc 2, message nommé, rien d'écrit. Tue m8."""
        d = self.socle("i1")
        p = subprocess.run([sys.executable, "-I", "-B", str(d / SUIVI_REL), "--installer"], cwd=d,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300, env=env_git(),
                           check=False)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertIn("à lancer depuis un terminal", p.stderr)
        self.rien_ecrit(d)

    def etat(self, d: Path) -> tuple[str, list[tuple[str, int, bytes]]]:
        cadre = self.commun(d) / "cadre"
        return (git(d, "config", "--local", "--get-regexp", r"^merge\.").stdout,
                sorted((p.name, stat.S_IMODE(p.stat().st_mode), p.read_bytes()) for p in cadre.iterdir()))

    def test_I2_config_locale_copie_0400_idempotent_et_worktree_lie(self) -> None:
        """I2 : quatre clés (board puis index) en config LOCALE seule (global relu octet pour octet), copie 0o400
        dans un dossier 0o700 sous `<git-common-dir>/cadre/`, deux appels ⇒ même état ; depuis un worktree LIÉ ⇒ même
        copie, même config. Tue m9 et m15."""
        d = self.socle("i2")
        avant = GLOBAL_GIT.read_bytes()
        rc, out, err = self.installer(d)
        self.assertEqual(0, rc, err)
        self.assertEqual(avant, GLOBAL_GIT.read_bytes(), "la config GLOBALE a été écrite")
        config, fichiers = self.etat(d)
        self.assertEqual([P.CLE_DRIVER, P.CLE_NOM, P.CLE_INDEX_DRIVER, P.CLE_INDEX_NOM],  # board PUIS index
                         [ligne.split(" ", 1)[0] for ligne in config.splitlines()])
        cadre = self.commun(d) / "cadre"
        self.assertEqual(0o700, stat.S_IMODE(cadre.stat().st_mode))
        self.assertEqual([(f"fusion_enregistrement-{hashlib.sha256(PILOTE.read_bytes()).hexdigest()[:16]}.py", 0o400,
                           PILOTE.read_bytes())], fichiers)
        valeur = git(d, "config", "--local", "--get", "merge.cadre-enregistrement.driver").stdout.strip()
        self.assertEqual(P.commande_driver(sys.executable, str(cadre / fichiers[0][0])), valeur)
        self.assertEqual(0, self.installer(d)[0])
        self.assertEqual((config, fichiers), self.etat(d))
        lie = self.tmp / "i2-lie"
        git(d, "worktree", "add", "-q", "--detach", str(lie))
        self.assertEqual(0, self.installer(lie, depuis="main")[0])
        self.assertEqual((config, fichiers), self.etat(d))
        self.assertEqual(avant, GLOBAL_GIT.read_bytes())

    def test_I3_verifier_contre_le_blob_de_HEAD(self) -> None:
        """I3 (K4) : absent rc 1 ; installé rc 0 ; worktree modifié SANS commit ⇒ rc 0 ; commit qui change le pilote
        ⇒ « périmé », puis `--installer` pose la copie de HEAD, `--verifier` rc 0 (lot D de T-01M5G7RTQ9) ; copie
        altérée ⇒ « altérée » (et remplacée, DITE) ; valeur réécrite ⇒ « forme inconnue ». Tue m28 et le contrôle
        de copie retiré de `_verifier`."""
        d = self.socle("i3")
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "absent" in sortie.splitlines()[-1]), sortie)
        self.assertEqual(0, self.installer(d)[0])
        self.assertEqual(0, self.verifier(d)[0])
        (d / SUIVI_REL).write_bytes(PILOTE.read_bytes() + b"# diff non commite\n")
        rc, sortie = self.verifier(d)
        self.assertEqual((0, True), (rc, "installé" in sortie.splitlines()[-1]), sortie)
        self.commit(d, "le pilote change")
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "périmé" in sortie.splitlines()[-1]), sortie)
        neuf = (d / SUIVI_REL).read_bytes()
        copie = self.commun(d) / "cadre" / f"fusion_enregistrement-{hashlib.sha256(neuf).hexdigest()[:16]}.py"
        rc, out, err = self.installer(d)
        self.assertEqual((0, True, 0), (rc, f"copie posée : {copie}" in out, self.verifier(d)[0]), out + err)
        copie.chmod(0o600)
        copie.write_bytes(b"# altere\n")
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "altérée" in sortie.splitlines()[-1]), sortie)
        rc, out, err = self.installer(d)
        self.assertEqual((0, True, neuf), (rc, "altérée" in out, copie.read_bytes()), out + err)
        valeur = git(d, "config", "--local", "--get", "merge.cadre-enregistrement.driver").stdout.strip()
        self.armer(d, valeur + " ")
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "forme inconnue" in sortie.splitlines()[-1]), sortie)

    def test_I3c_copie_en_lien_symbolique_refusee_puis_reposee(self) -> None:
        """S-01M5F950RA : la copie remplacée par un LIEN vers un contenu identique (refusé par `.githooks/post-merge`)
        ⇒ `--verifier` rc 1 « lien symbolique », jamais « installé » ; `--installer` repose une VRAIE copie, DITE."""
        d = self.socle("i3c")
        self.assertEqual(0, self.installer(d)[0])
        copie = next((self.commun(d) / "cadre").iterdir())
        copie.unlink()
        copie.symlink_to(self.copie())
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "lien symbolique" in sortie), sortie)
        rc, out, err = self.installer(d)
        self.assertEqual((0, True), (rc, "lien symbolique" in out), out + err)
        self.assertEqual((False, PILOTE.read_bytes(), 0), (copie.is_symlink(), copie.read_bytes(), self.verifier(d)[0]))

    def test_I3b_verifier_dit_a_moitie_arme_et_interpreteur_absent(self) -> None:
        """Passe de correction F5. (a) N4 : `.name` sans `.driver` ⇒ « à moitié armé », rc 1, remède `--unset` — jamais
        « absent ». (b) Réserve MAJEURE de l'exec-critic (bras I3) : interpréteur figé introuvable ⇒ « interpréteur
        absent », rc 1 — jamais « installé ». MUTANTS : branche « à moitié armé » retirée ; contrôle de `py` retiré."""
        d = self.socle("i3b")
        git(d, "config", "--local", P.CLE_NOM, P.LIBELLE)
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True, True), (rc, "à moitié armé" in sortie, "--installer [--depuis <ref>]" in sortie), sortie)
        self.assertIn(f"git config --local --unset {P.CLE_NOM}", sortie)
        git(d, "config", "--local", "--unset", P.CLE_NOM)
        self.assertEqual(0, self.installer(d)[0])
        copie = next((self.commun(d) / "cadre").iterdir())
        self.armer(d, P.commande_driver(str(self.tmp / "nulle-part" / "python3"), str(copie)))
        rc, sortie = self.verifier(d)
        self.assertEqual((1, True), (rc, "interpréteur absent" in sortie), sortie)
        self.armer(d, P.commande_driver(sys.executable, str(copie)))
        self.assertEqual(0, self.verifier(d)[0], "POLARITÉ : l'interpréteur réel ⇒ installé")

    def test_I2b_echec_du_second_config_laisse_un_pilote_qui_fusionne(self) -> None:
        """N4 (passe de correction F5) : le SECOND `git config --local` rend 255 ⇒ `.driver` posé, `.name` absent,
        avertissement nommé, rc 0 ; `--verifier` dit installé ; une vraie fusion S1 sur un chemin
        merge=cadre-enregistrement rend 0, jamais 128. MUTANT : `.name` écrit d'abord ⇒ installation refusée, `.name`
        seul, `git merge` rc 128."""
        d = self.socle("i2b")
        reel, appels = P._git, []

        def git_qui_echoue(depot: str, *args: str, texte: bool = True) -> subprocess.CompletedProcess:
            if args[:2] == ("config", "--local") and len(args) == 4:
                appels.append(args[2])
                if len(appels) == 2:
                    return subprocess.CompletedProcess(["git", *args], 255, "", "erreur simulée")
            return reel(depot, *args, texte=texte)

        with mock.patch.object(P, "_git", side_effect=git_qui_echoue):
            rc, _out, err = self.installer(d)
        self.assertEqual([P.CLE_DRIVER, P.CLE_NOM, P.CLE_INDEX_DRIVER, P.CLE_INDEX_NOM], appels, "ordre, index compris")
        self.assertEqual(0, rc, err)
        self.assertIn("AVERTISSEMENT", err)
        cles = git(d, "config", "--local", "--get-regexp", r"^merge\.").stdout
        self.assertEqual([P.CLE_DRIVER, P.CLE_INDEX_DRIVER, P.CLE_INDEX_NOM], [c.split()[0] for c in cles.splitlines()])
        self.assertEqual(0, self.verifier(d)[0])
        self.s1(d)
        m = git(d, "merge", "--no-edit", "b", check=False)
        self.assertNotEqual(128, m.returncode, m.stdout + m.stderr)
        self.assertEqual(0, m.returncode, m.stdout + m.stderr)

    def test_I6c_commits_locaux_non_pousses_refuses_sans_depuis(self) -> None:
        """Avis sécurité (S-01M4Q1QSWN4GC5ZTS37KSCMV11), passe de correction F5 : sur la branche par défaut, sans
        `--depuis`, un commit LOCAL absent d'origin/<défaut> ⇒ refus nommé ; `--depuis HEAD` l'assume. Contrôle : clone
        frais (HEAD == origin/main) ⇒ installé. MUTANT : contrôle de l'amont retiré."""
        o = self.socle("i6c-origine")
        c = self.clone(o, "i6c-clone")
        self.assertEqual(0, self.installer(c)[0], "contrôle : HEAD == origin/main")
        (c / "local.txt").write_text("local\n", encoding="utf-8")
        self.commit(c, "commit local non poussé")
        rc, _, err = self.installer(c)
        self.assertEqual(2, rc, err)
        self.assertIn("NON poussés sur origin/main", err)
        self.assertEqual(0, self.installer(c, depuis="HEAD")[0], "--depuis HEAD l'assume")

    def test_I5b_interpreteur_sous_un_autre_worktree_du_depot_refuse(self) -> None:
        """Même avis : la garde d'interpréteur ne voyait que le worktree COURANT. Un interpréteur sous un worktree LIÉ
        du même dépôt ⇒ refus, rien d'écrit, base nommée. MUTANT : `_racines_du_depot` réduit à `[top]`."""
        d = self.socle("i5b")
        lie = self.tmp / "i5b-lie"
        git(d, "worktree", "add", "-q", "--detach", str(lie))
        exe = lie / "venv" / "bin" / "python"
        exe.parent.mkdir(parents=True)
        exe.symlink_to(sys.executable)
        dehors = self.tmp / "python-de-base"
        with mock.patch.object(sys, "executable", str(exe)), \
                mock.patch.object(sys, "_base_executable", str(dehors), create=True):
            rc, _, err = self.installer(d)
        self.assertEqual(2, rc, err)
        self.assertIn("sous la racine", err)
        self.assertIn(str(dehors), err)
        self.rien_ecrit(d)

    def test_I4_GIT_DIR_etranger_ignore_et_depot_nu_refuse(self) -> None:
        """I4 : `GIT_DIR` / `GIT_WORK_TREE` visant un AUTRE dépôt ⇒ l'autre intact, le bon configuré ; dépôt nu ⇒ refus
        nommé. Tue m19."""
        bon, autre = self.socle("i4-bon"), self.socle("i4-autre")
        avant = (autre / ".git" / "config").read_bytes()
        with mock.patch.dict(os.environ, {"GIT_DIR": str(autre / ".git"), "GIT_WORK_TREE": str(autre)}):
            rc, _, err = self.installer(bon)
        self.assertEqual(0, rc, err)
        self.assertEqual(avant, (autre / ".git" / "config").read_bytes())
        self.assertFalse((autre / ".git" / "cadre").exists())
        self.assertEqual(0, git(bon, "config", "--local", "--get", "merge.cadre-enregistrement.driver",
                                check=False).returncode)
        nu = self.tmp / "i4-nu.git"
        git(self.tmp, "init", "-q", "--bare", str(nu))
        rc, _, err = self.installer(nu)
        self.assertEqual(2, rc)
        self.assertIn("dépôt nu", err)

    def test_I5_interpreteur_sous_la_racine_refuse_avec_remede(self) -> None:
        """I5 (S6) : `sys.executable` sous le toplevel (apparent PUIS résolu) ⇒ refus, rien d'écrit, le message porte
        `sys._base_executable` et la commande à relancer ; base AUSSI sous la racine ⇒ dit, rien proposé. Tue m20, m31."""
        d = self.socle("i5")
        apparent = d / "venv" / "bin" / "python"
        apparent.parent.mkdir(parents=True)
        apparent.symlink_to(sys.executable)
        (d / "py-reel").write_bytes(b"")
        resolu = self.tmp / "lien-python"
        resolu.symlink_to(d / "py-reel")
        dehors = self.tmp / "python-de-base"
        for nom, exe in (("apparent", apparent), ("résolu", resolu)):
            with self.subTest(nom), mock.patch.object(sys, "executable", str(exe)), \
                    mock.patch.object(sys, "_base_executable", str(dehors), create=True):
                rc, _, err = self.installer(d)
                self.assertEqual(2, rc)
                self.assertIn("sous la racine", err)
                self.assertIn(str(dehors), err)
                self.assertIn("--installer", err)
                self.rien_ecrit(d)
        with mock.patch.object(sys, "executable", str(apparent)), \
                mock.patch.object(sys, "_base_executable", str(d / "autre-python"), create=True):
            rc, _, err = self.installer(d)
        self.assertEqual(2, rc)
        self.assertIn("sys._base_executable", err)
        self.assertNotIn("--installer", err)
        self.rien_ecrit(d)

    def test_I6_branche_par_defaut_depuis_et_octets_du_ref(self) -> None:
        """I6 : branche ≠ défaut sans `--depuis` ⇒ rc 2 ; HEAD détachée ⇒ refus ; `--depuis HEAD` ⇒ installé, branche et
        sha8 imprimés, octets == blob du ref (un diff non commité n'y entre pas). Tue m21."""
        d = self.socle("i6")
        git(d, "checkout", "-q", "-b", "autre")
        rc, _, err = self.installer(d)
        self.assertEqual(2, rc)
        self.assertIn("branche non fusionnée", err)
        self.rien_ecrit(d)
        git(d, "checkout", "-q", "--detach")
        self.assertEqual(2, self.installer(d)[0])
        self.rien_ecrit(d)
        git(d, "checkout", "-q", "autre")
        (d / SUIVI_REL).write_bytes(PILOTE.read_bytes() + b"# diff non commite\n")
        rc, out, err = self.installer(d, depuis="HEAD")
        self.assertEqual(0, rc, err)
        self.assertIn("branche=autre", out)
        self.assertIn(f"sha={git(d, 'rev-parse', 'HEAD').stdout.strip()[:8]}", out)
        self.assertEqual([PILOTE.read_bytes()], [p.read_bytes() for p in (self.commun(d) / "cadre").iterdir()])

    def test_I6b_resoudre_commit_tiret_end_of_options_et_sha_complet(self) -> None:
        """I6b (K3) : `--depuis -q` / `--output=<tmp>/x` ⇒ refus de la garde du tiret, aucun fichier ; garde contournée
        ⇒ `--end-of-options` précède le ref, refus, aucun fichier ; un blob ⇒ refus ; `git show` reçoit un sha
        COMPLET. Tue m27."""
        d = self.socle("i6b")
        for ref in ("-q", f"--output={self.tmp / 'x'}"):
            with self.subTest(ref=ref):
                rc, _, err = self.installer(d, depuis=ref)
                self.assertEqual(2, rc)
                self.assertIn("commence par un tiret", err)
                self.assertFalse((self.tmp / "x").exists())
                self.rien_ecrit(d)
        reel, appels = subprocess.run, []

        def espion(argv: list[str], *a: Any, **k: Any) -> subprocess.CompletedProcess:
            appels.append(list(argv))
            return reel(argv, *a, **k)

        ref = f"--output={self.tmp / 'y'}"
        with mock.patch.object(P, "_refus_ref", return_value=None), \
                mock.patch.object(P.subprocess, "run", side_effect=espion), self.assertRaises(P.Refus):
            P.resoudre_commit(ref, str(d))
        self.assertFalse((self.tmp / "y").exists())
        revparse = [a for a in appels if "rev-parse" in a]
        self.assertTrue(revparse)
        for argv in revparse:
            self.assertEqual("--end-of-options", argv[argv.index(f"{ref}^{{commit}}") - 1], argv)
        self.assertEqual(2, self.installer(d, depuis=f"HEAD:{SUIVI_REL.as_posix()}")[0])
        appels.clear()
        with mock.patch.object(P.subprocess, "run", side_effect=espion):
            self.assertEqual(0, self.installer(d)[0])
        montres = [a[-1] for a in appels if "show" in a]
        self.assertTrue(montres)
        for arg in montres:
            self.assertRegex(arg, r"\A([0-9a-f]{40}|[0-9a-f]{64}):")

    def test_I7_protect_paths_refuse_la_copie_controle_hors_git(self) -> None:
        """I7 (kit, K2) : JSON Write sur le chemin de la copie installée ⇒ rc 2 ; CONTRÔLE, chemin jetable sous TMPDIR
        hors de tout `.git/` ⇒ rc 0 (jamais `state_home()`). Tue m15."""
        self.exiger_kit()
        d = self.socle("i7")
        self.assertEqual(0, self.installer(d)[0])
        copie = next((self.commun(d) / "cadre").iterdir())

        def sonde(chemin: Path) -> int:
            charge = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(chemin), "content": "x"}})
            return subprocess.run([shutil.which("bash") or "bash", str(PROTECT_PATHS)], input=charge, text=True,
                                  capture_output=True, timeout=120, env=env_git(), cwd=BASE, check=False).returncode

        self.assertEqual(2, sonde(copie))
        self.assertEqual(0, sonde(self.tmp / "hors-git" / "cadre" / "fusion_enregistrement-0123456789abcdef.py"))

    def test_I8_dossier_a_pourcent_A(self) -> None:
        """I8 : clone dans un dossier dont le nom porte `%A` ⇒ `--installer` puis S1 ⇒ rc 0 (EFFET). Tue m22."""
        o = self.socle("i8-origine")
        c = self.clone(o, "i8 cl'one %A")
        rc, _, err = self.installer(c)
        self.assertEqual(0, rc, err)
        self.s1(c)
        m = git(c, "merge", "--no-edit", "b", check=False)
        self.assertEqual(0, m.returncode, m.stdout + m.stderr)

    def test_I9_merge_file_sans_histogram_refus_et_meme_absence(self) -> None:
        """I9 (D1) : un `git` factice rend 129 sur `merge-file --diff-algorithm` ⇒ `--installer` refuse, capacité
        nommée, rien d'écrit ; `sonder_git()` dit la même absence. Tue m24."""
        d = self.socle("i9")
        faux = self.tmp / "faux-bin"
        faux.mkdir()
        script = faux / "git"
        # La sous-commande `merge-file` SEULE (premier argument) : un `git config … driver` dont la VALEUR cite
        # `merge-file --diff-algorithm` passe au vrai git.
        script.write_text(f"#!/bin/sh\nVRAI={shlex.quote(shutil.which('git') or 'git')}\n"
                          'if [ "$1" = merge-file ]; then\n  case "$*" in\n    *--diff-algorithm*)\n'
                          '      echo "error: unknown option" >&2\n      exit 129\n      ;;\n  esac\nfi\n'
                          'exec "$VRAI" "$@"\n', encoding="utf-8")
        script.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{faux}{os.pathsep}{os.environ.get('PATH', '')}"}):
            rc, _, err = self.installer(d)
            res = P.sonder_git()
        self.assertEqual(2, rc)
        self.assertIn("git ≥ 2.44 requis", err)
        self.assertIn("merge-file --diff-algorithm=histogram", err)
        self.rien_ecrit(d)
        self.assertNotEqual("tout présent", res["verdict"])
        self.assertIn("merge-file --diff-algorithm=histogram", P.raison_sonde(res))

    def test_I9b_placeholders_non_developpes_refus_et_meme_absence(self) -> None:
        """I9b : `_GABARIT_SONDE` à placeholders non développés ⇒ même refus, même absence. Tue m26."""
        d = self.socle("i9b")
        self.assertEqual(1, P._GABARIT_SONDE.count("%S %X %Y"))
        with mock.patch.object(P, "_GABARIT_SONDE", P._GABARIT_SONDE.replace("%S %X %Y", "%%S %%X %%Y")):
            rc, _, err = self.installer(d)
            res = P.sonder_git()
        self.assertEqual(2, rc)
        self.assertIn("git ≥ 2.44 requis", err)
        self.assertIn("%S %X %Y", err)
        self.rien_ecrit(d)
        self.assertTrue(res["%S %X %Y"].startswith("absent"), res)


class DurcissementF5Tests(_Banc):
    """Avis sécurité de la fusion (S-01M4Q1QSWN4GC5ZTS37KSCMV11), passe de correction F5 — témoins sans dépôt."""

    def test_sonde_des_labels_hostile_relue_octet_pour_octet(self) -> None:
        """La sonde citait une branche bénigne (`b`) : un git qui ne cite pas `%Y` passait. MUTANTS : `_BRANCHE_SONDE`
        bénigne ; `_labels_lus` qui ne compare que `HEAD`."""
        self.assertTrue(set("';$") <= set(P._BRANCHE_SONDE), P._BRANCHE_SONDE)
        valide = subprocess.run(["git", "check-ref-format", "--branch", P._BRANCHE_SONDE], capture_output=True,
                                text=True, timeout=60, env=env_git(), check=False)
        self.assertEqual(0, valide.returncode, valide.stderr)
        self.assertTrue(P._labels_lus("abcd|HEAD|" + P._BRANCHE_SONDE))
        for lu in ("abcd|HEAD|b", "abcd|HEAD|b'", "abcd|HEAD|" + P._BRANCHE_SONDE.replace("'", ""), None):
            with self.subTest(lu=lu):
                self.assertFalse(P._labels_lus(lu))

    def test_ligne_copie_divergente_bornee(self) -> None:
        """Lecture sans borne du fichier suivi : tailles différentes ⇒ divergente SANS rien lire ; même taille ⇒
        comparée ; au-delà de `PLAFOND` ⇒ ni lue ni dite. MUTANT : la lecture intégrale d'avant (`read_bytes`)."""
        racine = self.tmp / "lcd"
        suivi = racine / SUIVI_REL
        suivi.parent.mkdir(parents=True)
        soi = self.tmp / "soi.py"
        soi.write_bytes(b"x" * 10)
        suivi.write_bytes(b"y" * 20)
        interdit = AssertionError("lu alors que les tailles suffisent")
        with mock.patch.object(Path, "read_bytes", side_effect=interdit), mock.patch("builtins.open", side_effect=interdit):
            self.assertEqual(P.DIVERGENCE, P.ligne_copie_divergente(racine, soi))
        suivi.write_bytes(b"x" * 10)
        self.assertIsNone(P.ligne_copie_divergente(racine, soi))
        suivi.write_bytes(b"x" * 9 + b"z")
        self.assertEqual(P.DIVERGENCE, P.ligne_copie_divergente(racine, soi))
        with mock.patch.object(P, "PLAFOND", 4):
            self.assertIsNone(P.ligne_copie_divergente(racine, soi))

    def test_poser_copie_retire_un_temporaire_orphelin_jamais_un_frais(self) -> None:
        """Temporaire laissé sur SIGKILL : un `.copie-*` plus vieux que `_AGE_ORPHELIN` est retiré à la pose suivante ;
        un frais (appel concurrent vivant) reste. MUTANT : aucun nettoyage."""
        dossier = self.tmp / "cadre"
        dossier.mkdir(mode=0o700)
        vieux, frais = dossier / ".copie-vieux", dossier / ".copie-frais"
        for f in (vieux, frais):
            f.write_bytes(b"x")
        avant = time.time() - 2 * P._AGE_ORPHELIN
        os.utime(vieux, (avant, avant))
        P._poser_copie(dossier, b"contenu\n")
        self.assertFalse(vieux.exists(), "orphelin laissé")
        self.assertTrue(frais.exists(), "un temporaire frais n'est jamais retiré")


class SondeAuKitTests(_Banc):
    def test_libelle_de_saut_fidele_au_verdict(self) -> None:
        """Passe de correction F5 (réserve de l'exec-critic) : « impossible » n'est jamais dit « capacité absente ».
        MUTANT : `libelle_saut` rend « capacité git absente » quel que soit le verdict."""
        impossible = {P.CAP_HISTOGRAM: "présent", P.CAP_LABELS: "impossible (commit base rc=128)",
                      P.CAP_CHEMINS: "impossible (commit base rc=128)", "verdict": "impossible"}
        self.assertNotIn("capacité git absente", libelle_saut(impossible))
        self.assertIn("sonde git impossible", libelle_saut(impossible))
        absent = dict(impossible, **{P.CAP_LABELS: "absent (lu=None)", "verdict": "absent"})
        self.assertIn("capacité git absente", libelle_saut(absent))

    def test_I9c_au_kit_git_recent_la_sonde_dit_tout_present(self) -> None:
        """I9c (E1, S3, S4) : au kit, `git --version` ≥ 2.44 ou illisible ⇒ `sonder_git()` DOIT dire « tout présent »
        — (a) sous l'environnement du banc, (b) sous un dossier temporaire à espace, apostrophe ET `%A` passé en
        paramètre — sinon ÉCHEC nommant l'étape, jamais un saut. Tue m29 et m30."""
        self.exiger_kit()
        version = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=60, env=env_git(),
                                 check=False).stdout
        lu = re.match(r"\Agit version ([0-9]+)\.([0-9]+)", version)
        if lu and (int(lu.group(1)), int(lu.group(2))) < (2, 44):
            return  # absence VRAIE : les témoins qui exécutent git ont sauté pour une cause réelle
        self.assertEqual("tout présent", SONDE.get("verdict"),
                         f"{version.strip()!r} et pourtant sonder_git() : {P.raison_sonde(SONDE)}")
        hostile = self.tmp / "h o'te %A"
        hostile.mkdir()
        res = P.sonder_git(dossier=str(hostile))
        self.assertEqual("tout présent", res["verdict"], P.raison_sonde(res))


if __name__ == "__main__":
    unittest.main()
