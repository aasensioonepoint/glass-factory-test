"""FILET SOUS LA PORTE de la migration de l'epic (T-00001043) : `board_epics.py`, joué par le VRAI `tasks.py --root`.

Le module vit sous `docs/interne/`, que `strip: docs/interne/` retire à l'adoptant : hors du kit, les cas sautent ;
DANS le kit (`.agents/IS_THE_KIT`), son absence est un ÉCHEC, jamais un saut (contrôle positif : une coquille de
chemin ne désarme pas le filet en silence). Le module est stdlib : aucun yaml ici, le registre est un objet
synthétique ; `board_import.py` (qui importe PyYAML, absent de l'interpréteur de la porte) n'est jamais exécuté.

Chaque cas construit un board synthétique par `json.dump` sous un dossier jetable, avec HOME (portant un
`.gitconfig`), XDG_*, TMPDIR, CADRE_STATE_DIR, CADRE_CONFIG_HOME et AGENTS_EVENTS_DIR jetables ; GIT_*,
CLAUDE_PROJECT_DIR et CADRE_PROJECT_ROOT retirés. Le board : un importé à pointeur `[exclusive]`, un importé `done`
sans pointeur, une SUITE sans `[BK-]`, un multi-ligne, et une tâche hors epic.
"""
import contextlib
import copy
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

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: docs/interne/ est strip: (.template-exclude), l'outil n'existe pas chez l'adoptant
MODULE = ROOT / "docs" / "interne" / "chantier" / "backlog" / "tools" / "board_epics.py"  # adopting-tree: idem
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()  # adopting-tree: le marqueur du kit ne voyage pas
POINTEUR_NEUF = "Référence : docs/interne/chantier/backlog/backlog.yaml."  # littéral : jamais lu dans l'outil

REGISTRE = [
    {"id": "E-01", "objectif": "Epic une, exclusive", "vague": 1, "priorite": "P0", "exclusive": True,
     "risque": "un risque d'une ligne"},
    {"id": "E-02", "objectif": "Epic deux", "vague": 2, "priorite": None, "exclusive": False, "risque": ""},
]
T_PTR, T_DONE, T_SUITE, T_MULTI, T_HORS = "T-00000001", "T-00000002", "T-00000003", "T-00000004", "T-00000005"
TITRES = {
    T_PTR: "[E-01][BK-001][P1][exclusive] Importé à pointeur — une description. Référence : plan/backlog.yaml.",
    T_DONE: "[E-02][BK-002][P2] Importé clos — sans pointeur.",
    T_SUITE: "[E-02][P1] Une suite créée hors yaml, sans référence BK.",
    T_MULTI: "[E-01][BK-003][exclusive] Première ligne\nseconde ligne, gardée octet pour octet. Référence : "
             "plan/backlog.yaml.",
    T_HORS: "[P0][doctrine] Hors epic, jamais touchée.",
}


def _charger():
    spec = importlib.util.spec_from_file_location("board_epics_sous_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # enregistré AVANT exec_module (test_modload_registration)
    spec.loader.exec_module(mod)
    return mod


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _environnement(tmp):
    """os.environ patché vers des dossiers jetables sous `tmp` ; rend le patcher (à arrêter)."""
    env = mock.patch.dict(os.environ)
    env.start()
    for k in [k for k in os.environ if k.startswith("GIT_") or k in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT")]:
        del os.environ[k]
    for k, d in {"HOME": "home", "XDG_STATE_HOME": "xdg/state", "XDG_DATA_HOME": "xdg/data",
                 "XDG_CONFIG_HOME": "xdg/config", "XDG_CACHE_HOME": "xdg/cache", "TMPDIR": "tmp",
                 "CADRE_STATE_DIR": "cadre-state", "CADRE_CONFIG_HOME": "cadre-config",
                 "AGENTS_EVENTS_DIR": "events"}.items():
        (tmp / d).mkdir(parents=True, exist_ok=True)
        os.environ[k] = str(tmp / d)
    (tmp / "home/.gitconfig").write_text("[user]\n\temail = filet@example.invalid\n\tname = filet\n")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _ecrire_board(root):
    (root / ".agents/state/board").mkdir(parents=True)
    taches = [{"id": tid, "task": titre, "owner": "dev-mono", "chantier": "refonte-packaging",
               "state": "done" if tid == T_DONE else "pending", "stage": "", "updated": "2026-09-30"}
              for tid, titre in TITRES.items()]
    path = root / ".agents/state/board/TASKS.json"
    path.write_text(json.dumps({"next_id": 6, "tasks": taches}, ensure_ascii=False, indent=2))
    return path


def _appel(be, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = be.main(list(args), copy.deepcopy(REGISTRE))
    return rc, out.getvalue()


LOCAL = Path(".agents/state/local/backlog-import")
OCTETS_MIGRES = (".agents/state/board/TASKS.json", f"{LOCAL}/titres-avant-epic.json", f"{LOCAL}/titres-avant-epic.sha256")


@unittest.skipUnless(EST_LE_KIT, "hors du kit (pas de .agents/IS_THE_KIT) : le module ne voyage pas")
class BacklogBoardEpicsPresenceTests(unittest.TestCase):
    """CONTRÔLE POSITIF, HORS du saut indexé sur le module : dans le kit, un module absent (coquille de chemin
    comprise) est un ÉCHEC, jamais « 12 skipped »."""

    def test_module_present_dans_le_kit(self):
        self.assertTrue(MODULE.is_file(), f"{MODULE} absent dans le kit : le filet sauterait en silence")
        self.assertEqual(_charger().REPO, ROOT)  # PLAN.parents[3], jamais docs/interne


@unittest.skipUnless(MODULE.is_file(), "board_epics.py absent (arbre adoptant) : le filet n'a pas de sujet")
class BacklogBoardEpicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """UNE migration réelle par classe (durée du filet) ; chaque cas repart d'une copie de ses octets."""
        cls.gabarit = Path(tempfile.mkdtemp(prefix="board-epics-gabarit-"))
        env = _environnement(cls.gabarit)
        try:
            board = _ecrire_board(cls.gabarit / "root")
            shutil.copy2(board, cls.gabarit / "avant.TASKS.json")
            cls.rc_gabarit, out = _appel(_charger(), "epics", "--root", str(cls.gabarit / "root"),
                                         "--avant", str(cls.gabarit / "avant.TASKS.json"))
            cls.sortie_gabarit = out
        finally:
            env.stop()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.gabarit, True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="board-epics-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(_environnement(self.tmp).stop)
        self.be = _charger()
        self.root = self.tmp / "root"
        self.board_path = _ecrire_board(self.root)
        self.avant = self.tmp / "avant.TASKS.json"
        shutil.copy2(self.board_path, self.avant)

    def _main(self, *args):
        return _appel(self.be, *args)

    def _main_err(self, *args, registre=None):
        """(rc, stdout, stderr) : un Refus part sur stderr, que `_appel` jette ; `registre` remplace REGISTRE."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.be.main(list(args), copy.deepcopy(REGISTRE if registre is None else registre))
        return rc, out.getvalue(), err.getvalue()

    def _board(self):
        return {t["id"]: t for t in json.loads(self.board_path.read_text(encoding="utf-8"))["tasks"]}

    def _migre(self):
        """L'état migré du gabarit (une migration RÉELLE, rc 0), recopié octet pour octet ; rend son bilan."""
        self.assertEqual(self.rc_gabarit, 0, self.sortie_gabarit)
        for rel in OCTETS_MIGRES:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.gabarit / "root" / rel, self.root / rel)
        return json.loads(self.sortie_gabarit.strip().splitlines()[-1])

    def _snap(self):
        return self.root / LOCAL / "titres-avant-epic.json"

    def test_dry_run_comptes(self):
        avant = _sha(self.board_path)
        rc, out = self._main("epics", "--dry-run", "--root", str(self.root))
        self.assertEqual(rc, 0)
        r = json.loads(out)
        self.assertEqual((r["candidats"], r["importes"], r["suites_hors_yaml"]), (4, 3, 1))
        self.assertEqual(r["suites"], [T_SUITE])
        self.assertEqual(r["par_etat"], {"done": 1, "pending": 3})
        self.assertEqual(r["par_epic"], {"E-01": 2, "E-02": 2})
        self.assertEqual((r["pointeurs"], r["multi_ligne"], r["epic_deja_posee"]), (2, [T_MULTI], []))
        self.assertEqual(_sha(self.board_path), avant)
        self.assertFalse((self.root / ".agents/state/local").exists())

    def test_dry_run_compte_les_intents_o2_en_fichiers(self):
        """T-00001058 (O2) : les intents en attente ne vivent plus dans TASKS.json mais en fichiers
        `sync_outbox/<ordre:20>-<operation_id>.json` ; le relevé les compte (glob NON récursif, forme exacte, un
        `operation_id` une fois), un `.json` d'une autre forme n'est pas compté. ROUGE avant : lecture brute, 0."""
        dossier = self.root / ".agents/state/board/sync_outbox"
        dossier.mkdir(parents=True)
        for nom in (f"{1:020d}-op-1.json", f"{2:020d}-op-2.json", f"{3:020d}-op-2.json", "pas-un-intent.json"):
            (dossier / nom).write_text("{}\n", encoding="utf-8")
        rc, out = self._main("epics", "--dry-run", "--root", str(self.root))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["sync_outbox"], 2)
        self.assertFalse((self.root / ".agents/state/local").exists())

    def test_epics_puis_verify_0(self):
        bilan = self._migre()
        self.assertEqual(bilan["par_geste"], {"epic-new": 2, "epic": 4, "retitle": 4})
        self.assertEqual(bilan["stderr"].get("autre", 0), 0)
        b = self._board()
        self.assertEqual({t: b[t].get("epic") for t in TITRES},
                         {T_PTR: "E-01", T_DONE: "E-02", T_SUITE: "E-02", T_MULTI: "E-01", T_HORS: None})
        self.assertTrue(b[T_PTR]["task"].startswith("[BK-001][P1][exclusive] "))
        self.assertTrue(b[T_PTR]["task"].endswith(POINTEUR_NEUF))
        self.assertTrue((MODULE.parents[1] / "backlog.yaml").is_file())  # le pointeur neuf vise un fichier réel
        self.assertEqual(b[T_HORS]["task"], TITRES[T_HORS])
        self.assertEqual(self._main("epics-verify", "--root", str(self.root), "--avant", str(self.avant))[0], 0)

    def test_deuxieme_passe_sans_ecriture(self):
        self._migre()
        b0, s0 = _sha(self.board_path), _sha(self._snap())
        rc, out = self._main("epics", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["par_geste"], {"epic-new": 2})
        self.assertEqual((_sha(self.board_path), _sha(self._snap())), (b0, s0))

    def test_rollback_ancre_puis_verify_rollback_0(self):
        self._migre()
        rc, out = self._main("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self._main("epics-verify", "--rollback", "--root", str(self.root),
                                    "--avant", str(self.avant))[0], 0)
        avant = {t["id"]: t for t in json.loads(self.avant.read_text(encoding="utf-8"))["tasks"]}
        apres = self._board()
        for tid in TITRES:
            self.assertEqual({k: v for k, v in apres[tid].items() if k != "updated"},
                             {k: v for k, v in avant[tid].items() if k != "updated"}, tid)
        self.assertEqual([e["id"] for e in json.loads(self.board_path.read_text())["epics"]], ["E-01", "E-02"])

    def test_multi_ligne_octet_pour_octet(self):
        self._migre()
        self.assertEqual(self._board()[T_MULTI]["task"],
                         TITRES[T_MULTI][len("[E-01]"):].replace("Référence : plan/backlog.yaml.", POINTEUR_NEUF))
        self._main("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(self._board()[T_MULTI]["task"].encode("utf-8"), TITRES[T_MULTI].encode("utf-8"))

    def test_classer_liste_blanche(self):
        """B-C6 : la forme RÉELLE d'un bloc sœur (en-tête, lignes à deux espaces, `    mkdir -p`) et la ligne
        `event_store: … journaux d'attente conserves …` sont ôtées et NOMMÉES ; tout autre texte est `autre`."""
        soeur = ("PARTITION D'ÉTAT APPARENTÉE — be71c1e557046258 (racine : /x/kit (ABSENT du disque))\n"
                 "  partition courante : 2ad3050842c1f65c (racine : /y/root)\n  jambes tenues :\n"
                 "    - J2 même historique git (commit racine commun)\n  acquitter (geste du pilote, tait ce signal) :\n"
                 "    mkdir -p /z/acquittements && touch /z/acquittements/be71c1e557046258\n")
        attente = ("event_store: 3 journaux d'attente conserves pour rejeu ulterieur (auteur d'export indisponible : "
                   "git config user.email vide)\n")
        warn = self.be.avertissement_attendu(T_PTR, TITRES[T_PTR], "E-01")
        self.assertEqual(self.be.classer("")[0], "vide")
        self.assertEqual(self.be.classer(soeur + soeur), ("v3", ["PARTITION D'ÉTAT APPARENTÉE be71c1e557046258"] * 2))
        self.assertEqual(self.be.classer(soeur + warn + attente, warn)[0], "v3+already")
        self.assertEqual(self.be.classer(attente)[0], "v3")
        for autre in ("TASKS: pont V3 refusé, board écrit — x\n",
                      "event_store: journal d'attente REFUSE (ULID hors forme, definitif, jamais rejoue)\n",
                      soeur + "texte libre\n", warn):  # le dernier : avertissement NON attendu pour ce geste
            self.assertEqual(self.be.classer(autre)[0], "autre", autre[:40])

    def _refus_sans_geste(self, *args):
        avant = _sha(self.board_path)
        rc, _ = self._main(*args)
        self.assertEqual(rc, 2)
        self.assertEqual(_sha(self.board_path), avant)

    def test_refus_sans_root(self):
        self._refus_sans_geste("epics", "--avant", str(self.avant))
        self._refus_sans_geste("epics", "--root", str(self.root))  # --avant absent
        self.assertFalse(self._snap().exists())

    def test_refus_root_vide(self):
        # cwd = une racine qui PORTE un board : `--root ""` résolu sur le cwd y trouverait un board à écrire ; seul le
        # refus EXPLICITE de la valeur vide l'arrête (mutant « valeur vide acceptée » : rouge ici, mesuré)
        with contextlib.chdir(self.root):
            self._refus_sans_geste("epics", "--root", "", "--avant", str(self.avant))
        self.assertFalse(self._snap().exists())
        self._refus_sans_geste("epics", "--root", str(self.tmp / "home"), "--avant", str(self.avant))

    def test_refus_epic_deja_posee(self):
        data = json.loads(self.board_path.read_text(encoding="utf-8"))
        data["tasks"][1]["epic"] = "E-02"
        self.board_path.write_text(json.dumps(data, ensure_ascii=False))
        shutil.copy2(self.board_path, self.avant)
        self._refus_sans_geste("epics", "--root", str(self.root), "--avant", str(self.avant))
        self.assertFalse(self._snap().exists())

    def test_refus_board_diverge_de_la_preimage(self):
        data = json.loads(self.board_path.read_text(encoding="utf-8"))
        data["tasks"][2]["task"] = "[E-02][P1] Retitrée par un tiers après la pré-image."
        self.board_path.write_text(json.dumps(data, ensure_ascii=False))
        self._refus_sans_geste("epics", "--root", str(self.root), "--avant", str(self.avant))
        self.assertFalse(self._snap().exists())

    def test_refus_instantane_reconstruit(self):
        self._migre()
        b = self._board()  # l'instantané RECONSTRUIT depuis le board migré : « 0 écart » circulaire sans ancre
        faux = {tid: {"task": b[tid]["task"], "epic": None} for tid in sorted(b) if b[tid].get("epic")}
        self._snap().write_text(json.dumps(faux, ensure_ascii=False, indent=1), encoding="utf-8")
        self._snap().with_suffix(".sha256").write_text(f"{_sha(self._snap())}  titres-avant-epic.json\n")
        self._refus_sans_geste("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(self._main("epics-verify", "--rollback", "--root", str(self.root),
                                    "--avant", str(self.avant))[0], 1)

    def test_refus_candidat_hors_instantane(self):
        self._migre()
        data = json.loads(self.board_path.read_text(encoding="utf-8"))
        data["tasks"].append({"id": "T-00000006", "task": "[E-02][P2] Retardataire créé après l'instantané.",
                              "owner": "dev-mono", "chantier": "refonte-packaging", "state": "pending",
                              "stage": "", "updated": "2026-10-01"})
        data["next_id"] = 7
        self.board_path.write_text(json.dumps(data, ensure_ascii=False))
        self._refus_sans_geste("epics", "--root", str(self.root), "--avant", str(self.avant))

    def _tasks_py(self, *args):
        """Une édition LÉGITIME, par le VRAI `tasks.py --root` (jamais le JSON à la main)."""
        p = subprocess.run([sys.executable, str(self.be.REPO / ".agents/bin/tasks.py"), "--root", str(self.root),
                            *args], capture_output=True, text=True, cwd=str(self.root))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_reprise_et_rollback_n_ecrasent_pas_une_edition_posterieure(self):
        """C2 (critic-opus, trouvaille 2) : après la migration, `retitle` d'une tâche et `epic` changée d'une autre ;
        `epics-rollback`, puis `epics` sur un état refait : rc ≠ 0, titre et epic INTACTS. Mesuré avant la garde :
        rc 0, titre rendu à l'instantané, epic retirée ou ramenée. MUTANTS garde ôtée de `migrer` ou de `rollback` :
        rouge ici."""
        rescopee = "[BK-001][P1][exclusive] Rescopée APRÈS la migration."
        for mode in ("epics-rollback", "epics"):
            with self.subTest(mode=mode):
                self._migre()
                self._tasks_py("retitle", T_PTR, rescopee)
                self._tasks_py("epic", T_DONE, "E-01")
                rc, out = self._main(mode, "--root", str(self.root), "--avant", str(self.avant))
                self.assertNotEqual(rc, 0, out)
                self.assertIn("modifié après migration", out)
                b = self._board()
                self.assertEqual((b[T_PTR]["task"], b[T_PTR].get("epic")), (rescopee, "E-01"))
                self.assertEqual((b[T_DONE]["task"], b[T_DONE].get("epic")), (TITRES[T_DONE][len("[E-02]"):], "E-01"))

    def test_la_garde_laisse_passer_le_demi_etat_et_un_rollback_rejoue(self):
        """La garde C2 n'arrête QUE l'édition postérieure. Le DEMI-ÉTAT d'un STOP (`epic` posée, titre encore préfixé
        — écrit dans le JSON : R10 refuse de le fabriquer par `retitle`) se reprend à rc 0 ; un rollback REJOUÉ passe
        à rc 0 sans geste de tâche. MUTANTS garde trop stricte (demi-état refusé, epic nulle refusée au rollback) :
        rouge ici."""
        self._migre()
        data = json.loads(self.board_path.read_text(encoding="utf-8"))
        for t in data["tasks"]:
            if t["id"] == T_PTR:
                t["task"] = TITRES[T_PTR]  # `epic` E-01 gardée : le demi-état que nomme le bilan d'un STOP
        self.board_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        rc, out = self._main("epics", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["par_geste"], {"epic-new": 2, "retitle": 1})
        self.assertTrue(self._board()[T_PTR]["task"].startswith("[BK-001][P1][exclusive] "))
        for passe, gestes in ((1, {"epic --retirer": 4, "retitle": 4}), (2, {})):
            rc, out = self._main("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))
            self.assertEqual(rc, 0, out)
            self.assertEqual(json.loads(out.strip().splitlines()[-1])["par_geste"], gestes, f"passe {passe}")
        self.assertEqual(self._board()[T_PTR]["task"], TITRES[T_PTR])

    def test_reprise_ne_repose_pas_une_epic_retiree_apres_migration(self):
        """Binôme bis (opus 1, fable 1) : `epics` n'admet que les TROIS états qu'il produit — (titre de l'instantané,
        epic nulle), (titre de l'instantané, E-NN), (forme migrée, E-NN). `epic T --retirer` APRÈS la migration donne
        (forme migrée, epic nulle) : STOP (rc 3, garde) après les seuls `epic-new`, epic restée nulle. Mesuré avant :
        rc 0, epic reposée. `epics-rollback` reste juste sur cet état : titre de la pré-image, epic nulle, puis
        `epics-verify --rollback` 0. MUTANT garde en produit cartésien (titre × epic) : rouge ici."""
        self._migre()
        self._tasks_py("epic", T_PTR, "--retirer")
        rc, out = self._main("epics", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 3, out)
        self.assertIn("modifié après migration", out)
        bilan = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(bilan["par_geste"], {"epic-new": 2})
        self.assertEqual((bilan["stop"]["geste"], bilan["stop"]["cible"]), ("garde", T_PTR))
        self.assertIsNone(self._board()[T_PTR].get("epic"))
        rc, out = self._main("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 0, out)
        self.assertEqual((self._board()[T_PTR]["task"], self._board()[T_PTR].get("epic")), (TITRES[T_PTR], None))
        self.assertEqual(self._main("epics-verify", "--rollback", "--root", str(self.root),
                                    "--avant", str(self.avant))[0], 0)

    def test_instantane_perdu_recree_depuis_la_preimage(self):
        """fable-1 : l'instantané vit sous un seau git-ignoré (`git clean -xfd` l'emporte) et le rollback l'exige.
        `epics-instantane` le recrée depuis la PRÉ-IMAGE : octets ÉGAUX à l'original, `epics-verify` 0, puis rollback
        et `epics-verify --rollback` 0. MUTANT instantané dérivé du board migré (0 candidat) : rouge ici."""
        self._migre()
        original = self._snap().read_bytes()
        for f in (self._snap(), self._snap().with_suffix(".sha256")):
            f.unlink()
        rc, out = self._main("epics-instantane", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["ecarts_preimage"], 0)
        self.assertEqual(self._snap().read_bytes(), original)
        self.assertEqual(self._main("epics-verify", "--root", str(self.root), "--avant", str(self.avant))[0], 0)
        self.assertEqual(self._main("epics-rollback", "--root", str(self.root), "--avant", str(self.avant))[0], 0)
        self.assertEqual(self._main("epics-verify", "--rollback", "--root", str(self.root),
                                    "--avant", str(self.avant))[0], 0)

    def test_instantane_jamais_reecrit_ni_vide(self):
        """`epics-instantane` refuse (rc 2, rien d'écrit) un instantané OU une empreinte déjà là, et une pré-image
        sans candidat (le board migré passé pour `--avant` donnerait un instantané vide : rollback muet). MUTANTS
        contrôle d'existence ôté, contrôle « 0 candidat » ôté : rouge ici."""
        self._migre()
        snap, sha = self._snap(), self._snap().with_suffix(".sha256")
        octets = {snap: snap.read_bytes(), sha: sha.read_bytes()}
        self._refus_sans_geste("epics-instantane", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual({f: f.read_bytes() for f in octets}, octets)
        snap.unlink()  # l'empreinte seule reste : un demi-instantané ne se complète pas en silence
        self._refus_sans_geste("epics-instantane", "--root", str(self.root), "--avant", str(self.avant))
        self.assertFalse(snap.exists())
        sha.unlink()
        migre = self.tmp / "migre.TASKS.json"
        shutil.copy2(self.board_path, migre)
        self._refus_sans_geste("epics-instantane", "--root", str(self.root), "--avant", str(migre))
        self.assertFalse(snap.exists() or sha.exists())

    def test_demi_instantane_refuse_avec_son_remede(self):
        """Binôme bis (opus 5) : une empreinte VIDE (disque plein entre les deux écritures) levait IndexError dans
        `epics`, `epics-rollback` et `epics-verify` ; vide, ≠ sha256 ou absente, aucun mode ne nommait le remède.
        Désormais `epics` et `epics-rollback` refusent (rc 2, aucun geste), `epics-verify` (lecture seule) rend son
        écart (rc 1), et chacun nomme le remède — sortir les deux fichiers du seau, puis `epics-instantane` — qui,
        suivi à la lettre, rend un instantané vérifié. MUTANT `not champs` ôté : rouge ici (IndexError)."""
        self._migre()
        snap, sha = self._snap(), self._snap().with_suffix(".sha256")
        for cas, contenu in (("vide", ""), ("≠ sha256", "0" * 64 + "  titres-avant-epic.json\n"), ("absente", None)):
            with self.subTest(empreinte=cas):
                if contenu is None:
                    sha.unlink()
                else:
                    sha.write_text(contenu, encoding="utf-8")
                b0 = _sha(self.board_path)
                for mode, rc_attendu in (("epics", 2), ("epics-rollback", 2), ("epics-verify", 1)):
                    rc, out, err = self._main_err(mode, "--root", str(self.root), "--avant", str(self.avant))
                    self.assertEqual(rc, rc_attendu, (mode, out, err))
                    self.assertIn("sortir les deux fichiers du seau", out + err, mode)
                    self.assertIn("`epics-instantane", out + err, mode)
                self.assertEqual(_sha(self.board_path), b0)
        snap.unlink()  # le remède, à la lettre
        self.assertEqual(self._main("epics-instantane", "--root", str(self.root), "--avant", str(self.avant))[0], 0)
        self.assertEqual(self._main("epics-verify", "--root", str(self.root), "--avant", str(self.avant))[0], 0)

    def test_instantane_refuse_un_registre_yaml_autre_que_celui_du_board(self):
        """Binôme bis (fable 4) : « mêmes candidats » suppose le registre yaml égal à celui de la migration. Une epic
        retirée du yaml donnait un instantané plus court, `ecarts_preimage` 0, rc 0 : rollback muet sur ses tâches.
        Désormais, ids du yaml ≠ ids du registre `epics` du board : refus rc 2, rien d'écrit. Board sans registre
        (instantané perdu avant tout `epic-new`) : refus qui nomme `epics`, dont le 1er passage l'écrit. MUTANT
        contrôle ôté : rouge ici."""
        snap, sha = self._snap(), self._snap().with_suffix(".sha256")
        b0 = _sha(self.board_path)  # board d'avant la migration : aucun registre `epics`
        rc, out, err = self._main_err("epics-instantane", "--root", str(self.root), "--avant", str(self.avant))
        self.assertEqual(rc, 2, (out, err))
        self.assertIn("relancer `epics`", err)
        self.assertEqual(_sha(self.board_path), b0)
        self.assertFalse(snap.exists() or sha.exists())
        self._migre()
        snap.unlink()
        sha.unlink()
        e03 = {"id": "E-03", "objectif": "Epic trois", "vague": 3, "priorite": None, "exclusive": False, "risque": ""}
        for nom, registre in (("epic retirée du yaml", REGISTRE[:1]), ("epic ajoutée au yaml", REGISTRE + [e03])):
            with self.subTest(registre=nom):
                b0 = _sha(self.board_path)
                rc, out, err = self._main_err("epics-instantane", "--root", str(self.root), "--avant", str(self.avant),
                                              registre=registre)
                self.assertEqual(rc, 2, (out, err))
                self.assertIn("registre yaml ≠ registre `epics` du board", err)
                self.assertEqual(_sha(self.board_path), b0)
                self.assertFalse(snap.exists() or sha.exists())


if __name__ == "__main__":
    unittest.main()
