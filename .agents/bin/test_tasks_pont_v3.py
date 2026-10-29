"""Pont V3 refusé ou en panne : le verbe écrit quand même le board (T-00000782, T-00001004,
T-00001056 ; T-00000792 pour `start`, `stage`, `writeset`, `depends`, `done` et `reopen`).

Un lien à l'emplacement du store V3 (`DEFAULT_DB_PATH(root)`), ou une couture
`cadre.ledger.store` indisponible, faisait lever la CONSTRUCTION du pont
(`BoardBridge` -> `EventStore` -> `create_tables`) avant tout verbe mutant : rc 1,
trace Python, board gelé — mesuré en bac jetable, `tasks 0`, `outbox 0`. T-00001004
a mesuré le même gel sur quatre causes de plus : `OuvertureImpossible` (T8), un
store non SQLite (T7), un verrou tenu (T9) et `HorsRacine` (T10, par injection :
injoignable par le vrai canal). Il a mesuré aussi un `replay-sync` qui rendait 0 sur
une racine non résolue (T11). Ces témoins tiennent la doctrine « refuser le pont
plutôt que le verbe » (`replay_sync`) sur ces causes. Ils ne l'étendent ni à toute
`ValueError`, ni à toute erreur SQLite, ni à toute `OSError` (T4, T4b), ne masquent
pas une panne d'écriture du board (T6), et ne mémorisent pas le saut d'une racine nue
sur un verbe mutant (T12). T-00001056 a mesuré le même gel sur les causes d'état
machine et de store qui restaient : partition d'état ou `run/` non inscriptible (T13,
T15, `PermissionError`), un fichier à leur place (T14, `NotADirectoryError`,
`FileExistsError`), dossier du store en lecture seule (T16, code 1544) et store
corrompu (T17, code 11) ; T4b les injecte aussi, pour l'hôte root où les `chmod`
sautent. Au DRAIN, le pont construit, un verrou d'écrivain WAL et un fichier de store
en lecture seule sont NOMMÉS sans changer le code de sortie (T18), et aucun des cinq
sites n'imprime un message d'exception brut (T19).

T-00000792 (f) étend ces témoins, jusque-là bornés à `new` et `replay-sync`, aux
verbes mutants qui ABOUTISSENT : `start`, `stage`, `writeset`, `depends --add`, `done`
et `reopen` sous un refus par le vrai canal, un lien au store (F1), et `start`,
`depends`, `done` sous une PANNE par le vrai canal, la couture masquée (F2). Il ne
couvre pas les autres verbes du littéral `mutating`. (k) épingle l'`isinstance`
d'`EmplacementRefuse` à DEUX copies de `cadre.ledger.store`, par chemin et paquet,
et le croisement des deux (K1). Références du titre de la tâche, relocalisées PAR
NOM, jamais par ligne : `tasks.py:1111` -> `tasks_sync.py::drain_sync_outbox` (repli
« echec inattendu du consumer », `EmplacementRefuse` y est nommé REFUSÉ, T22 de
`test_tasks_pont_v3_annonce.py`) ; `tasks.py:4257` -> le commentaire de
`tasks_sync.py::replay_sync`, « `isinstance` VRAI mesuré (… copie par chemin ET
`PYTHONPATH=src`) » ; `test_tasks.py:3350` ->
`test_tasks.py::PanneAnnonceeUneFoisParCommandeTests`.

Bac : `CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR` nichés dans la `TemporaryDirectory`,
JAMAIS `CADRE_PROJECT_ROOT` dans ce processus (`cadre.paths.project_root` le lit
AVANT `depuis` et écraserait la racine de tous les bancs — précédent
`V3BridgeDegradedModeTests`) ; l'ambiant est retiré le temps du test.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest import mock

TASKS_PATH = Path(__file__).with_name("tasks.py")
SPEC = importlib.util.spec_from_file_location("tasks_pont_v3_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)

REPO = Path(__file__).resolve().parents[2]
tasks._RESOLVEUR_V3.charger_paquet(REPO, "agentic_v3")
#: Annexes qu'SQLite ouvre à côté d'un store : aucune ne doit naître d'un refus.
ANNEXES = ("-wal", "-shm", "-journal")


class PontV3RefuseNeGelePasLeBoardTests(unittest.TestCase):
    """T1-T6 du plan T-00000782, plus le témoin R4 (`pont_commande=None`) ; T4b et
    T7-T12 du plan T-00001004 ; T13-T19 du plan T-00001056, qui amende T4b ; F1, F2
    (f : `start`, `stage`, `writeset`, `depends`, `done`, `reopen`) et K1 (k :
    `isinstance` à deux copies) du plan T-00000792."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "repo"
        board_dir = self.root / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        self.board = board_dir / "TASKS.json"
        self.board.write_text(
            json.dumps({"next_id": 1, "tasks": [], "sync_outbox": [], "sync_correlations": {}}),
            encoding="utf-8",
        )
        env = mock.patch.dict(os.environ, {
            "CADRE_STATE_DIR": str(base / "state"),
            "AGENTS_EVENTS_DIR": str(base / "events"),
        })
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADRE_PROJECT_ROOT", None)  # restauré par `env.stop`
        # REPO en tête inoffensif : agentic_v3 déjà fixé par charger_paquet (ligne 66).
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
            self.addCleanup(sys.path.remove, str(REPO))
        from agentic_v3.db import run_export
        from agentic_v3.db.schema import DEFAULT_DB_PATH
        from agentic_v3.reconciliation import board_bridge

        self.run_export, self.board_bridge = run_export, board_bridge
        # `DEFAULT_DB_PATH` mémoïse `cadre.paths` AVANT toute couture masquée (T3) :
        # `BoardBridge.__init__` le résout avant d'atteindre `create_tables`.
        self.store = DEFAULT_DB_PATH(self.root)
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.cible = base / "cible.db"
        conn = sqlite3.connect(str(self.cible))
        conn.execute("CREATE TABLE t(x)")
        conn.commit()
        conn.close()
        self.octets = self.cible.read_bytes()

    # -- outillage --------------------------------------------------------------

    def _poser_lien(self) -> None:
        """Lien symbolique à l'emplacement du store — posé par les SEULS témoins qui
        en ont besoin : un hôte sans lien symbolique (Windows sans privilège) ne
        saute que ceux-là, et T3/T4, qui n'en posent pas, y tournent quand même."""
        try:
            os.symlink(self.cible, self.store)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")

    def _main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), *args])
        return rc, out.getvalue(), err.getvalue()

    def _board(self) -> dict[str, Any]:
        """TASKS.json BRUT, son `sync_outbox` lue par la VUE (T-00001058, O2 : un fichier par intent) — emprunté par
        `test_tasks_pont_v3_annonce`, `_deverse`, `_drain` et `test_tasks_sync_sans_v3`."""
        return {**json.loads(self.board.read_text(encoding="utf-8")),
                "sync_outbox": tasks.load(str(self.root))["sync_outbox"]}

    @staticmethod
    def _lignes(err: str, motif: str) -> list[str]:
        return [ligne for ligne in err.splitlines() if motif in ligne]

    def _cible_intacte(self, *, lien_symbolique: bool = True) -> None:
        self.assertEqual(self.octets, self.cible.read_bytes(), "la cible du lien a été écrite")
        if lien_symbolique:
            self.assertTrue(self.store.is_symlink(), "le lien a été retiré ou remplacé")
        for chemin in (self.store, self.cible):
            for suffixe in ANNEXES:
                annexe = chemin.with_name(chemin.name + suffixe)
                self.assertFalse(annexe.exists(), f"annexe née d'un refus : {annexe}")

    def _couture_ledger_store_absente(self) -> ExitStack:
        """`cadre.ledger.store` et `cadre.workspace` introuvables par les DEUX
        branches de `_cadre` — patron `_couture_ledger_store_absente` de
        `agentic_v3/tests/test_run_export.py` : paquet masqué dans `sys.modules`,
        repli par chemin pointé sur un dossier absent, mémo sans ces deux entrées.
        `cadre.paths`, déjà mémoïsé par `setUp`, reste servi. Tout est restauré."""
        pile = ExitStack()
        pile.enter_context(mock.patch.dict(sys.modules, {
            "cadre": None, "cadre.ledger": None, "cadre.ledger.store": None,
            "cadre.workspace": None}))
        pile.enter_context(mock.patch.dict(self.run_export._MODULES_CADRE))
        self.run_export._MODULES_CADRE.pop("ledger.store", None)
        self.run_export._MODULES_CADRE.pop("workspace", None)
        pile.enter_context(mock.patch.object(
            self.run_export, "_SRC_CADRE", Path(self.tmp.name) / "cadre-absent-banc"))
        return pile

    def _main_sous(self, racine: Path, *args: str) -> tuple[int, str, str]:
        """`_main` sous une AUTRE racine que celle du montage (T11, T12)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(racine), *args])
        return rc, out.getvalue(), err.getvalue()

    def _exiger_sqlite_errorcode(self) -> None:
        """Le classeur lit `sqlite_errorcode`, que Python porte depuis 3.11 (plancher
        du kit). Si une VRAIE erreur SQLite n'a pas de code -> `skipTest` nommé,
        jamais un vert creux (réserve 5 de S-00003284)."""
        conn = sqlite3.connect(":memory:")
        code = None
        try:
            conn.execute("SELECT x FROM table_absente")
        except sqlite3.Error as exc:
            code = getattr(exc, "sqlite_errorcode", None)
        finally:
            conn.close()
        if code is None:
            self.skipTest("sqlite_errorcode absent (Python < 3.11) : code SQLite illisible")

    def _poser_store(self) -> None:
        """Un store SQLite RÉGULIER, valide, à l'emplacement du store (T8, T9)."""
        conn = sqlite3.connect(str(self.store))
        try:
            conn.execute("CREATE TABLE t(x)")
            conn.commit()
        finally:
            conn.close()

    def _racine_nue(self) -> Path:
        """Racine SANS `.agents/`, hors git, sans `$CADRE_PROJECT_ROOT` (retiré par
        `setUp`). PRÉCONDITION : `DEFAULT_DB_PATH(nue)` lève la VRAIE
        `CadrePathError`, celle de la couture. Sinon `skipTest`, jamais un vert creux."""
        nue = Path(self.tmp.name) / "nue"
        nue.mkdir()
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        try:
            DEFAULT_DB_PATH(nue)
        except self.run_export._cadre("paths").CadrePathError:
            return nue
        raise unittest.SkipTest(f"précondition : {nue} se résout (git ou ancêtre .agents/ ?)")

    # -- témoins ----------------------------------------------------------------

    def test_T1_lien_au_store_le_verbe_ecrit_le_board_et_annonce_UNE_fois(self) -> None:
        """MUTATIONS : retirer le rattrapage d'`EmplacementRefuse` -> rc 1 / trace ;
        retirer la sentinelle `refus` -> DEUX annonces (avant ET après le verbe)."""
        self._poser_lien()
        rc, _out, err = self._main("new", "sonde")
        self.assertEqual(0, rc, f"le verbe a échoué au lieu de refuser le pont : {err!r}")
        board = self._board()
        self.assertEqual(["sonde"], [t["task"] for t in board["tasks"]])
        self.assertGreaterEqual(
            len(board.get("sync_outbox", [])), 1,
            "l'événement board doit être DIFFÉRÉ dans l'outbox, jamais perdu")
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), f"UNE annonce par commande attendue :\n{err}")
        self.assertIn("emplacement du store refusé", refus[0])
        self.assertIn("board écrit sans relecture V3", refus[0])
        self.assertIn("lien symbolique", refus[0], "la cause exacte ({exc}) est jointe")
        self._cible_intacte()

    def test_T1_second_nom_physique_meme_refus(self) -> None:
        """Un second nom PHYSIQUE (lien dur) est refusé comme un lien symbolique :
        c'est la même classe, prise par la même couture."""
        try:
            os.link(self.cible, self.store)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien physique impossible ici : {exc}")
        rc, _out, err = self._main("new", "sonde")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, "pont V3 REFUSÉ")), err)
        self.assertEqual(1, len(self._board()["tasks"]))
        self._cible_intacte(lien_symbolique=False)
        self.assertEqual(2, os.stat(self.store).st_nlink, "le second nom a été touché")

    def test_T2_lien_retire_replay_sync_rejoue_l_evenement_differe(self) -> None:
        """L'événement différé par le refus n'est pas perdu : lien retiré, le verbe
        `replay-sync` le rejoue (outbox vide, ligne `board_sync_inbox` présente).
        `_email_git` est greffé comme dans `ReplaySyncNonFuiteTests` (R9) : aucun
        `user.email` ambiant n'entre dans le verdict."""
        self._poser_lien()
        rc, _out, err = self._main("new", "sonde")
        self.assertEqual(0, rc, err)
        differes = {i["operation_id"] for i in self._board().get("sync_outbox", [])}
        self.assertTrue(differes, "précondition : un intent différé dans l'outbox")
        self.store.unlink()
        with mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, out, err = self._main("replay-sync")
        self.assertEqual(0, rc, err)
        self.assertEqual([], self._board().get("sync_outbox", []), err)
        self.assertIn(f"replayed {len(differes)} sync intent(s)", out)
        conn = sqlite3.connect(str(self.store))
        try:
            inbox = {r[0] for r in conn.execute("SELECT operation_id FROM board_sync_inbox")}
        finally:
            conn.close()
        self.assertLessEqual(differes, inbox, f"intents non rejoués : {differes - inbox}")

    def test_T3_couture_ledger_store_absente_PANNE_annoncee_le_board_ecrit(self) -> None:
        """PAR LE VRAI CANAL (R2) : la couture est réellement introuvable, donc
        `create_tables` lève `PanneInfrastructure` ET le classifieur
        d'`EmplacementRefuse` — qui passe par la même couture — doit retomber sur
        « aucune classe » sans lever. MUTATIONS : classifieur sans son `try` ->
        la panne remonte du handler ; branche PANNE retirée -> rc 1. Aucun lien :
        le canal mesuré est la couture, et le témoin tourne sur tout hôte."""
        with self._couture_ledger_store_absente():
            rc, _out, err = self._main("new", "sonde")
        self.assertEqual(0, rc, f"la panne a gelé le verbe : {err!r}")
        panne = self._lignes(err, "pont V3 en PANNE")
        self.assertEqual(1, len(panne), f"UNE annonce par commande attendue :\n{err}")
        self.assertIn("BLOQU", panne[0])
        self.assertIn("cadre.ledger.store", panne[0], "la cause exacte ({exc}) est jointe")
        board = self._board()
        self.assertEqual(["sonde"], [t["task"] for t in board["tasks"]])
        self.assertGreaterEqual(len(board.get("sync_outbox", [])), 1)
        self.assertFalse(self.store.exists(), "aucun store créé sans la primitive")

    def test_T4_une_ValueError_hors_classe_REMONTE_deux_bras(self) -> None:
        """Garde-fou, vert AVANT et APRÈS le correctif : le rattrapage n'avale pas
        toute `ValueError`. Bras 1, `ValueError` nue (celle de `get_db_connection`
        sur un store absent) — MUTATION `except ValueError` -> rougit. Bras 2,
        classe LOCALE nommée `EmplacementRefuse` — MUTATION comparaison par NOM
        (précédent `ReplaySyncRacineNonResolueTests`) -> rougit."""

        class EmplacementRefuse(ValueError):
            """Homonyme local : même nom, AUTRE classe que celle de la couture."""

        for bras, exc in (("ValueError nue", ValueError("store absent")),
                          ("homonyme local", EmplacementRefuse("homonyme"))):
            with self.subTest(bras=bras):
                pont: dict[str, Any] = {}
                with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=exc):
                    with self.assertRaises(ValueError) as ctx:
                        tasks.replay_sync(self.root, pont_commande=pont)
                self.assertIs(exc, ctx.exception)
                self.assertNotIn("refus", pont, "une levée non classée n'est pas mémorisée")

    def test_T4b_une_erreur_SQLite_hors_codes_REMONTE_un_code_etendu_est_refuse(self) -> None:
        """Bras 3 et suivants de T4 (réserve 3 de S-00003284), hors `ValueError`, donc
        `assertRaises(type(exc))`. REMONTENT, sans mémo : « database is locked »
        FABRIQUÉ, sans `sqlite_errorcode` (mesuré : un homonyme construit à la main n'a
        pas de code) — MUTATION sélection par MESSAGE -> rougit ; `IntegrityError`
        SQLITE_CONSTRAINT_UNIQUE (2067, primaire 19), doublon au rejeu — MUTATION
        élargissement `primaire in (11, 19)` -> rougit ; `OSError` ENOSPC, hors des
        trois classes refusées — MUTATION `isinstance(exc, OSError)` large -> rougit.
        REFUSÉS, refus mémorisé, UNE ligne qui nomme la cause : code ÉTENDU 261
        (SQLITE_BUSY_RECOVERY = 5 | 1 << 8 ; MUTATION masque `& 0xFF` retiré ->
        rougit) ; depuis T-00001056, SQLITE_CORRUPT (11), SQLITE_READONLY (8) et
        l'étendu 1544 (READONLY_DIRECTORY, primaire 8). PIÈGE 2 du plan T-00001056 :
        jusque-là, les bras 11 et 8 épinglaient « REMONTE » (`assertNotIn("refus",
        pont)`), une vacuité que ce plan AMENDE ici, nommée. Puis, PAR INJECTION, donc
        sur tout hôte, root compris (la jambe Docker de la porte tourne en root, où les
        `chmod` de T8, T13, T15 et T16 sautent) : `PermissionError`,
        `NotADirectoryError`, `FileExistsError` et `OuvertureImpossible` de la couture
        (ancien libellé « droits ou CANTOPEN » -> rougit)."""
        verrou_fabrique = sqlite3.OperationalError("database is locked")
        self.assertIsNone(getattr(verrou_fabrique, "sqlite_errorcode", None),
                          "précondition : un homonyme fabriqué n'a pas de code")
        corrompu = sqlite3.DatabaseError("database disk image is malformed")
        corrompu.sqlite_errorcode = 11  # type: ignore[attr-defined]
        lecture_seule = sqlite3.OperationalError("attempt to write a readonly database")
        lecture_seule.sqlite_errorcode = 8  # type: ignore[attr-defined]
        doublon = sqlite3.IntegrityError("UNIQUE constraint failed: events_ledger.ulid")
        doublon.sqlite_errorcode = 2067  # type: ignore[attr-defined]
        disque_plein = OSError(28, "No space left on device")  # OSError hors des trois classes
        for bras, exc in (("verrou fabriqué sans code", verrou_fabrique),
                          ("IntegrityError SQLITE_CONSTRAINT_UNIQUE", doublon),
                          ("OSError ENOSPC hors classes", disque_plein)):
            with self.subTest(bras=bras):
                pont: dict[str, Any] = {}
                with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=exc):
                    with self.assertRaises(type(exc)) as ctx:
                        tasks.replay_sync(self.root, pont_commande=pont)
                self.assertIs(exc, ctx.exception)
                self.assertNotIn("refus", pont, "une levée non classée n'est pas mémorisée")
        etendu = sqlite3.OperationalError("database is locked (recovery)")
        etendu.sqlite_errorcode = 261  # type: ignore[attr-defined]
        repertoire_ro = sqlite3.OperationalError("attempt to write a readonly database")
        repertoire_ro.sqlite_errorcode = 1544  # type: ignore[attr-defined]
        ouverture = self.run_export._couture_ledger_store()[0].OuvertureImpossible(
            "le nom désigne le même fichier (banc)")
        for bras, exc, cause in (
                ("code étendu 261", etendu, "store verrouillé"),
                ("SQLITE_CORRUPT", corrompu, "store corrompu"),
                ("SQLITE_READONLY", lecture_seule, "store en lecture seule"),
                ("READONLY_DIRECTORY 1544", repertoire_ro, "store en lecture seule"),
                ("PermissionError injectée", PermissionError(13, "Permission denied"),
                 "état machine non inscriptible"),
                ("NotADirectoryError injectée", NotADirectoryError(20, "Not a directory"),
                 "chemin d'état occupé par un fichier"),
                ("FileExistsError injectée", FileExistsError(17, "File exists"),
                 "chemin d'état occupé par un fichier"),
                ("OuvertureImpossible injectée", ouverture, "emplacement inchangé")):
            with self.subTest(bras=bras):
                pont = {}
                err = io.StringIO()
                with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=exc), \
                        mock.patch("sys.stderr", err):
                    self.assertEqual(0, tasks.replay_sync(self.root, pont_commande=pont))
                self.assertTrue(pont.get("refus"), "un refus classé est mémorisé")
                refus = self._lignes(err.getvalue(), "pont V3 REFUSÉ")
                self.assertEqual(1, len(refus), err.getvalue())
                self.assertIn(cause, refus[0])

    def test_T5_replay_sync_explicite_rend_1_annonce_sans_trace(self) -> None:
        """Le verbe EXPLICITE `replay-sync` échoue (rc 1) sur un refus, annoncé en
        UNE ligne, sans trace Python (avant : exception non rattrapée, rc 1). Ce
        verbe n'écrit AUCUN board : l'annonce ne le prétend pas (exec-critic, passe
        2). MUTATION : clé `explicite` ignorée -> « board écrit » revient, rougit."""
        self._poser_lien()
        rc, _out, err = self._main("replay-sync")
        self.assertEqual(1, rc, err)
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertNotIn("board écrit", err)
        self.assertIn("rien n'est rejoué, événements conservés dans l'outbox", refus[0])
        self.assertNotIn("Traceback", err)
        self._cible_intacte()

    def test_R4_sans_pont_commande_le_refus_est_annonce_sans_memo(self) -> None:
        """Cinq appelants directs passent `pont_commande=None` (R4) : le refus y est
        annoncé à CHAQUE appel, rend 0, et ne lit ni n'écrit aucun mémo. MUTATION :
        la garde `is not None` retirée en lecture OU en écriture -> AttributeError."""
        self._poser_lien()
        for appel in (1, 2):
            err = io.StringIO()
            with mock.patch("sys.stderr", err):
                self.assertEqual(0, tasks.replay_sync(self.root), f"appel {appel}")
            self.assertEqual(1, len(self._lignes(err.getvalue(), "pont V3 REFUSÉ")),
                             f"appel {appel} : {err.getvalue()!r}")
        self._cible_intacte()

    def test_T6_board_corrompu_la_panne_d_ecriture_n_est_pas_masquee(self) -> None:
        """Le rattrapage entoure la SEULE construction du pont : un board illisible
        reste une `BoardError`, rc 2. MUTATION : `try` élargi au verbe -> rc 0/1."""
        self._poser_lien()
        self.board.write_text("{pas du json", encoding="utf-8")
        rc, _out, err = self._main("new", "sonde")
        self.assertEqual(2, rc, err)
        self.assertIn("is not valid JSON", err)
        # T-00001007 (g) : le verbe refusé n'a rien écrit, l'annonce ne le prétend plus.
        self.assertNotIn("board écrit", err)
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertIn("verbe refusé — board NON écrit", refus[0])
        self._cible_intacte()

    # -- T-00001004 : quatre causes de plus, et la racine non résolue -----------

    def _refus_un_board_ecrit(self, rc: int, err: str, cause: str) -> None:
        """Forme commune de T7 à T10 : rc 0, board écrit, intent DIFFÉRÉ dans
        l'outbox, UNE annonce par commande, qui nomme sa cause."""
        self.assertEqual(0, rc, f"le verbe a échoué au lieu de refuser le pont : {err!r}")
        board = self._board()
        self.assertEqual(["sonde"], [t["task"] for t in board["tasks"]])
        self.assertGreaterEqual(
            len(board.get("sync_outbox", [])), 1,
            "l'événement board doit être DIFFÉRÉ dans l'outbox, jamais perdu")
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), f"UNE annonce par commande attendue :\n{err}")
        self.assertIn(cause, refus[0])
        self.assertIn("board écrit sans relecture V3", refus[0])
        self.assertNotIn("Traceback", err)

    def test_T7_store_non_SQLite_le_verbe_ecrit_le_board_et_annonce_UNE_fois(self) -> None:
        """PAR LE VRAI CANAL : des octets non SQLite au store font lever
        `sqlite3.DatabaseError` code 26 (SQLITE_NOTADB) à la construction (mesuré,
        `schema.create_tables`). Le store refusé n'est ni écrit ni flanqué d'annexe.
        MUTATION : bras NOTADB retiré du classeur -> la levée remonte de `main`."""
        self._exiger_sqlite_errorcode()
        octets = b"ceci n'est pas une base SQLite\n" * 64
        self.store.write_bytes(octets)
        rc, _out, err = self._main("new", "sonde")
        self._refus_un_board_ecrit(rc, err, "store non SQLite")
        self.assertEqual(octets, self.store.read_bytes(), "le store refusé a été écrit")
        self._cible_intacte(lien_symbolique=False)

    def test_T8_store_sans_droits_OuvertureImpossible_le_verbe_ecrit_le_board(self) -> None:
        """PAR LE VRAI CANAL : un store RÉGULIER en `chmod 0` fait lever
        `OuvertureImpossible` de la couture (emplacement INCHANGÉ, `store.py`), mesuré.
        Son `sqlite_errorcode` est ABSENT : la CLASSE est le seul discriminant. Root
        ouvre tout, et un hôte sans `geteuid` n'est pas POSIX : `skipTest`. MUTATIONS :
        bras `OuvertureImpossible` retiré -> la levée remonte de `main` ; libellé
        antérieur à T-00001056 (« droits ou CANTOPEN ») -> rougit."""
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None:
            self.skipTest("os.geteuid absent (hôte non POSIX) : chmod 0 n'y refuse rien")
        if geteuid() == 0:
            self.skipTest("root : chmod 0 ne refuse pas l'ouverture")
        self._poser_store()
        os.chmod(self.store, 0)
        self.addCleanup(os.chmod, self.store, 0o600)
        rc, _out, err = self._main("new", "sonde")
        self._refus_un_board_ecrit(rc, err, "ouverture impossible")
        self.assertIn("emplacement inchangé", self._lignes(err, "pont V3 REFUSÉ")[0])
        self._cible_intacte(lien_symbolique=False)

    def test_T9_store_verrouille_refus_apres_l_attente_le_verbe_ecrit_le_board(self) -> None:
        """PAR LE VRAI CANAL : un verrou RÉEL tenu (`locking_mode=EXCLUSIVE` + `BEGIN
        EXCLUSIVE`) fait lever `sqlite3.OperationalError` code 5 (SQLITE_BUSY) à la
        construction (mesuré). L'attente de 30 s de `schema._connexion_nue` est ramenée
        à 50 ms par patch, et elle n'est PAS raccourcie en production (README).
        PRÉCONDITION (réserve 8) : une sonde à 50 ms prouve qu'aucune lecture du store
        ne passe sous le verrou (code 5), sinon `skipTest`. Aucune assertion ne lit le
        store tant que le verrou est tenu. MUTATION : bras BUSY retiré -> remonte."""
        self._exiger_sqlite_errorcode()
        self._poser_store()
        verrou = sqlite3.connect(str(self.store), isolation_level=None)
        self.addCleanup(verrou.close)
        verrou.execute("PRAGMA locking_mode=EXCLUSIVE")
        verrou.execute("BEGIN EXCLUSIVE")
        self.addCleanup(verrou.rollback)  # LIFO : relâché avant la fermeture
        sonde = sqlite3.connect(str(self.store), timeout=0.05)
        code = None
        try:
            sonde.execute("PRAGMA user_version").fetchone()
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", None)
        finally:
            sonde.close()
        if not isinstance(code, int) or code & 0xFF != 5:
            self.skipTest(f"précondition : verrou non obtenu (code {code!r})")
        from agentic_v3.db import schema

        with mock.patch.object(schema, "_connexion_nue",
                               lambda uri: sqlite3.connect(uri, uri=True, timeout=0.05)):
            rc, _out, err = self._main("new", "sonde")
        self._refus_un_board_ecrit(rc, err, "store verrouillé")

    def test_T10_HorsRacine_de_la_couture_refuse_le_pont_par_injection(self) -> None:
        """INJECTION de la VRAIE classe de couture (`cadre.workspace.HorsRacine`, prise
        par `_couture_ledger_store`). Le vrai canal ne l'atteint pas à la
        construction : sur une feuille lien vers l'extérieur,
        `Workspace(parent).identite(...)` rend `Identite(est_lien=True)`, donc
        `EmplacementRefuse`, jamais `HorsRacine` (`_feuille` ne résout que le parent,
        `src/cadre/workspace.py`). C'est mesuré au plan T-00001004. MUTATION : bras
        `HorsRacine` retiré -> la `ValueError` remonte de `main`."""
        hors_racine = self.run_export._couture_ledger_store()[1].HorsRacine
        exc = hors_racine("store hors de la racine du workspace (banc)")
        with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=exc):
            rc, _out, err = self._main("new", "sonde")
        self._refus_un_board_ecrit(rc, err, "store hors racine")

    def test_T11_replay_sync_sur_racine_nue_rend_1_sans_replayed_0(self) -> None:
        """Point (j) de T-00000792 : `replay-sync` EXPLICITE sur une racine non
        résolue rendait 0 et affichait « replayed 0 sync intent(s) » (mesuré au plan
        T-00001004). Il annonce désormais le saut en UNE ligne, MÉMORISE le refus et
        rend 1, sans trace. L'annonce ne promet aucun board (réserve 7). MUTATION :
        `refus` non posé dans la branche `CadrePathError` -> rc 0, « replayed 0 »."""
        nue = self._racine_nue()
        rc, out, err = self._main_sous(nue, "replay-sync")
        self.assertEqual(1, rc, f"stdout={out!r} stderr={err!r}")
        saut = self._lignes(err, "miroir V3 saute")
        self.assertEqual(1, len(saut), err)
        self.assertIn("rien n'est rejoué, aucun board sous cette racine", saut[0])
        self.assertNotIn("replayed", out)
        self.assertNotIn("board écrit", err)
        self.assertNotIn("Traceback", err)

    def test_T12_new_sur_racine_nue_saute_UNE_fois_puis_miroite(self) -> None:
        """Défaut de l'étape 3, lecture ÉTROITE de (d) (décision pilote S-00003321) :
        sur un verbe MUTANT le saut n'est PAS mémorisé. Le verbe crée `.agents/`, le
        second drain résout la racine et miroite, et l'outbox reste vide. `_email_git`
        est greffé comme dans T2 : aucun `user.email` ambiant n'entre dans le verdict.
        MUTATION : (d) littéral, `refus` mémorisé aussi sur verbe mutant -> l'outbox
        garde l'intent."""
        nue = self._racine_nue()
        with mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, _out, err = self._main_sous(nue, "new", "sonde")
        self.assertEqual(0, rc, err)
        self.assertEqual(1, len(self._lignes(err, "miroir V3 saute")), err)
        board = json.loads(
            (nue / ".agents" / "state" / "board" / "TASKS.json").read_text(encoding="utf-8"))
        self.assertEqual(["sonde"], [t["task"] for t in board["tasks"]])
        self.assertEqual([], tasks.load(str(nue))["sync_outbox"], err)  # la VUE (O2), jamais le JSON brut

    # -- T-00001056 : causes d'état machine et de store, drain nommé, aplatissement --

    def _posix_non_root(self) -> None:
        """Un `chmod` ne refuse rien sous root ni hors POSIX : `skipTest` nommé,
        jamais un vert creux (R8). T4b injecte les mêmes classes sur tout hôte."""
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None or geteuid() == 0:
            self.skipTest("chmod sans effet ici (hôte non POSIX ou root)")

    def _chmod(self, chemin: Path, mode: int) -> None:
        os.chmod(chemin, mode)
        self.addCleanup(os.chmod, chemin, 0o700)

    def _sous_etat(self, etat: Path) -> tuple[int, str, str]:
        """`new sonde` sous un AUTRE `CADRE_STATE_DIR` que celui du montage."""
        with mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(etat)}):
            return self._main("new", "sonde")

    def _amorcer_store(self) -> None:
        """Un store V3 RÉEL, écrit par un pont sain (`_email_git` greffé comme en T2) :
        tâche `amorce` miroitée, outbox vide."""
        with mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, _out, err = self._main("new", "amorce")
        self.assertEqual(0, rc, err)
        self.assertEqual([], self._board().get("sync_outbox", []),
                         f"précondition : pont sain {err!r}")

    def _refus_apres_amorce(self, rc: int, err: str, cause: str) -> None:
        """Forme de T16 et T17 : celle de `_refus_un_board_ecrit`, après `amorce`."""
        self.assertEqual(0, rc, f"le verbe a gelé : {err!r}")
        board = self._board()
        self.assertEqual(["amorce", "sonde"], [t["task"] for t in board["tasks"]])
        self.assertGreaterEqual(len(board.get("sync_outbox", [])), 1)
        refus = self._lignes(err, "pont V3 REFUSÉ")
        self.assertEqual(1, len(refus), err)
        self.assertIn(cause, refus[0])
        self.assertNotIn("Traceback", err)

    def _drain_direct(self, exc: BaseException) -> str:
        """`drain_sync_outbox` appelé DIRECTEMENT avec un consumer FABRIQUÉ qui lève
        `exc` (patron des drains de `test_tasks.py`) : aucun store, tout hôte. Un intent
        est mis en attente par `new_task` si l'outbox est vide. Rien n'est acquitté.
        Rend le stderr entier."""
        if not self._board().get("sync_outbox"):
            tasks.new_task(str(self.root), "drain direct", "dev-multi")

        def _consumer(_intent: dict[str, Any]) -> bool:
            raise exc

        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(0, tasks.drain_sync_outbox(str(self.root), _consumer))
        return err.getvalue()

    def test_T13_partition_d_etat_non_creable_PermissionError(self) -> None:
        """VRAI CANAL : `CADRE_STATE_DIR` neuf en 0o500, le `mkdir` de la partition
        lève `PermissionError` (`schema.create_tables`), mesuré. MUTATION : bras
        `PermissionError` retiré -> remonte (T4b le témoigne sous root)."""
        self._posix_non_root()
        etat = Path(self.tmp.name) / "etat-ro"
        etat.mkdir()
        self._chmod(etat, 0o500)
        rc, _out, err = self._sous_etat(etat)
        self._refus_un_board_ecrit(rc, err, "état machine non inscriptible")

    def test_T14_chemin_d_etat_occupe_par_un_fichier(self) -> None:
        """VRAI CANAL, deux formes : `CADRE_STATE_DIR` est un fichier
        (`NotADirectoryError`) ; `run/` est un fichier (`FileExistsError`, cause
        absente du board, mesurée au plan). MUTATION : l'une des deux classes retirée
        -> remonte."""
        for forme in ("etat-fichier", "run-fichier"):
            with self.subTest(forme=forme):
                self.board.write_text(json.dumps(
                    {"next_id": 1, "tasks": [], "sync_outbox": [], "sync_correlations": {}}),
                    encoding="utf-8")
                etat = Path(self.tmp.name) / forme
                if forme == "etat-fichier":
                    etat.write_text("x", encoding="utf-8")
                else:
                    from agentic_v3.db.schema import DEFAULT_DB_PATH

                    with mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(etat)}):
                        run = DEFAULT_DB_PATH(self.root).parent
                    run.parent.mkdir(parents=True)
                    run.write_text("x", encoding="utf-8")
                rc, _out, err = self._sous_etat(etat)
                self._refus_un_board_ecrit(rc, err, "chemin d'état occupé par un fichier")

    def test_T15_dossier_run_non_inscriptible_avant_le_store(self) -> None:
        """VRAI CANAL : `run/` du montage en 0o500, sans store — la création exclusive
        du store lève `PermissionError` (`cadre/workspace.py`), mesuré. MUTATION : bras
        `PermissionError` retiré -> remonte."""
        self._posix_non_root()
        self.assertFalse(self.store.exists(), "précondition : aucun store")
        self._chmod(self.store.parent, 0o500)
        rc, _out, err = self._main("new", "sonde")
        self._refus_un_board_ecrit(rc, err, "état machine non inscriptible")

    def test_T16_dossier_du_store_en_lecture_seule_READONLY_DIRECTORY(self) -> None:
        """VRAI CANAL : store V3 réel, `run/` en 0o500 -> `OperationalError` 1544
        (primaire 8) à la construction, mesuré. MUTATION : bras 8 retiré -> remonte."""
        self._posix_non_root()
        self._exiger_sqlite_errorcode()
        self._amorcer_store()
        self._chmod(self.store.parent, 0o500)
        rc, _out, err = self._main("new", "sonde")
        self._refus_apres_amorce(rc, err, "store en lecture seule")

    def test_T17_store_corrompu_refuse_sans_l_ecrire(self) -> None:
        """VRAI CANAL : store V3 réel dont les octets 100 à 4096 sont écrasés ->
        `DatabaseError` 11 à la construction, mesuré. Le store refusé n'est pas
        réécrit. MUTATION : bras 11 retiré -> remonte."""
        self._exiger_sqlite_errorcode()
        self._amorcer_store()
        octets = bytearray(self.store.read_bytes())
        octets[100:4096] = b"\xff" * (4096 - 100)
        self.store.write_bytes(bytes(octets))
        rc, _out, err = self._main("new", "sonde")
        self._refus_apres_amorce(rc, err, "store corrompu")
        self.assertEqual(bytes(octets), self.store.read_bytes(), "le store refusé a été écrit")

    def test_T18_echec_au_drain_verrou_et_lecture_seule_NOMMES(self) -> None:
        """AU DRAIN, le pont construit : la ligne nomme la cause au lieu d'« echec
        inattendu du consumer ». rc 1 sous `replay-sync` et une attente par commande : T-00001053 (W4, W9).
        (1) ARMS FACTICES, drain direct, sur TOUT hôte (root compris) : code étendu
        517 (SQLITE_BUSY_SNAPSHOT, primaire 5) -> « store verrouille par un autre
        ecrivain » (MUTATION masque `& 0xFF` retiré -> rougit) ; code 8 -> « store en
        lecture seule » (MUTATION code 8 retiré -> rougit) ; `OSError` portant
        `sqlite_errorcode = 5`, homonyme hors classe -> « echec inattendu du consumer »
        (MUTATION garde `isinstance(…, DatabaseError)` retirée -> rougit). (2) VRAI
        CANAL : verrou d'écrivain WAL tenu, attente ramenée à 50 ms -> rc 0, intent
        gardé, ligne nommée (MUTATION nommage retiré -> rougit). (3) VRAI CANAL, POSIX
        non-root : FICHIER de store en 0o400 -> « store en lecture seule »."""
        etendu = sqlite3.OperationalError("database is locked (snapshot)")
        etendu.sqlite_errorcode = 517  # type: ignore[attr-defined]
        lecture_seule = sqlite3.OperationalError("attempt to write a readonly database")
        lecture_seule.sqlite_errorcode = 8  # type: ignore[attr-defined]
        homonyme = OSError("verrou d'un autre ordre")
        homonyme.sqlite_errorcode = 5  # type: ignore[attr-defined]
        for bras, exc, attendu, absent in (
                ("code étendu 517", etendu, "store verrouille par un autre ecrivain",
                 "echec inattendu"),
                ("code 8", lecture_seule, "store en lecture seule", "echec inattendu"),
                ("homonyme OSError code 5", homonyme, "echec inattendu du consumer",
                 "store verrouille")):
            with self.subTest(bras=bras):
                lignes = self._lignes(self._drain_direct(exc), "miroir V3")
                self.assertEqual(1, len(lignes), lignes)
                self.assertIn(f"miroir V3 — {attendu}", lignes[0])
                self.assertNotIn(absent, lignes[0])
        self._exiger_sqlite_errorcode()
        self._amorcer_store()
        from agentic_v3.db import schema

        verrou = sqlite3.connect(str(self.store), isolation_level=None)
        self.addCleanup(verrou.close)
        verrou.execute("BEGIN IMMEDIATE")
        verrou.execute("CREATE TABLE IF NOT EXISTS banc_verrou(x)")
        with mock.patch.object(schema, "_connexion_nue",
                               lambda uri: sqlite3.connect(uri, uri=True, timeout=0.05)), \
                mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, _out, err = self._main("new", "sonde")
        verrou.rollback()
        self.assertEqual(0, rc, err)
        self.assertTrue(
            self._lignes(err, "miroir V3 — store verrouille par un autre ecrivain"), err)
        self.assertNotIn("echec inattendu", err)
        self.assertGreaterEqual(len(self._board().get("sync_outbox", [])), 1)
        self._posix_non_root()
        self._chmod(self.store, 0o400)
        with mock.patch.object(self.run_export, "_email_git", return_value="banc@test"):
            rc, _out, err = self._main("new", "sonde2")
        self.assertEqual(0, rc, err)
        self.assertTrue(self._lignes(err, "miroir V3 — store en lecture seule"), err)
        self.assertNotIn("echec inattendu", err)
        self.assertGreaterEqual(len(self._board().get("sync_outbox", [])), 1)

    def _une_ligne_aplatie(self, err: str) -> None:
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x9b", err)
        lignes = [ligne for ligne in err.splitlines() if "V3" in ligne]
        self.assertEqual(1, len(lignes), err)
        self.assertIn("a?[31mb c?d", lignes[0])

    def test_T19_message_aplati_sur_une_ligne_sans_controle(self) -> None:
        """S-00003357 : aucun des CINQ sites n'imprime `{exc}` brut. Message piégé
        (ESC, saut de ligne, C1) -> UNE ligne V3, aucun caractère de contrôle, le
        message aplati `a?[31mb c?d`. Construction, classes RÉELLES de couture :
        `HorsRacine` par `new` (queue commune), `CadrePathError` par `replay-sync`
        (saut). Drain direct, un consumer fabriqué par site de la branche
        `RuntimeError`, sur tout hôte : `PanneInfrastructure`, `RunExportError`,
        `RuntimeError`. MUTATIONS : `_aplatir_exc` identité, ou l'un des cinq sites
        ramené à `{exc}` -> rougit."""
        piege = "a\x1b[31mb\nc\x9bd"
        hors_racine = self.run_export._couture_ledger_store()[1].HorsRacine(piege)
        racine = self.run_export._cadre("paths").CadrePathError(piege)
        for nom, exc, argv in (("queue commune", hors_racine, ("new", "sonde")),
                               ("saut CadrePathError", racine, ("replay-sync",))):
            with self.subTest(site=nom):
                with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=exc):
                    _rc, _out, err = self._main(*argv)
                self._une_ligne_aplatie(err)
        for nom, exc in (("drain PanneInfrastructure", self.run_export.PanneInfrastructure(piege)),
                         ("drain RunExportError", self.run_export.RunExportError(piege)),
                         ("drain RuntimeError", RuntimeError(piege))):
            with self.subTest(site=nom):
                self._une_ligne_aplatie(self._drain_direct(exc))

    # -- T-00000792 (f) : les verbes mutants qui ABOUTISSENT, autres que `new` ----

    def _operations(self) -> set[str]:
        return {i["operation_id"] for i in self._board().get("sync_outbox", [])}

    def _tache(self, tid: str) -> dict[str, Any]:
        return next(t for t in self._board()["tasks"] if t["id"] == tid)

    def _deux_taches(self) -> tuple[str, str]:
        """`new a` puis `new b` : les ids lus au board, jamais devinés."""
        for titre in ("a", "b"):
            rc, _out, err = self._main("new", titre)
            self.assertEqual(0, rc, err)
        a, b = (t["id"] for t in self._board()["tasks"])
        return a, b

    @staticmethod
    def _verbes(a: str, b: str) -> list[tuple[tuple[str, ...], str, Any]]:
        """`(argv, champ, attendu)` : le verbe et l'effet qu'il doit laisser au board."""
        return [
            (("start", a), "state", "running"),
            (("stage", a, "etape-banc"), "stage", "etape-banc"),
            (("writeset", a, "src/banc.py"), "writeset", ["src/banc.py"]),
            (("depends", a, b, "--add", "--motif", "banc"), "depends_on", [b]),
            (("done", a, "--raison", "banc"), "state", "done"),
            (("reopen", a, "--raison", "banc"), "state", "pending"),
        ]

    def _verbe_abouti(self, argv: tuple[str, ...], champ: str, attendu: Any, tid: str,
                      motif: str, cause: str) -> None:
        """Forme commune de F1 et F2 : rc 0, effet au board, UNE ligne `pont V3` dite
        APRÈS le verbe (`_annoncer_refus_pont`), outbox STRICTEMENT croissante."""
        avant = self._operations()
        rc, _out, err = self._main(*argv)
        self.assertEqual(0, rc, f"{argv[0]} : le verbe a échoué au lieu de refuser le pont : {err!r}")
        self.assertEqual(attendu, self._tache(tid).get(champ), f"{argv[0]} : effet absent du board")
        pont = self._lignes(err, "pont V3")
        self.assertEqual(1, len(pont), f"{argv[0]} : UNE annonce par commande attendue :\n{err}")
        self.assertIn(motif, pont[0], argv[0])
        self.assertIn(cause, pont[0], argv[0])
        apres = self._operations()
        self.assertTrue(avant < apres, f"{argv[0]} : outbox non croissante ({len(avant)} -> {len(apres)})")

    def test_F1_verbes_mutants_par_le_chemin_de_refus_lien(self) -> None:
        """PAR LE VRAI CANAL (un lien à l'emplacement du store, `EmplacementRefuse`) :
        `start`, `stage`, `writeset`, `depends --add`, `done` et `reopen` ABOUTISSENT
        (rc 0, effet au board) et disent UNE fois « pont V3 REFUSÉ … board écrit sans
        relecture V3 », l'événement DIFFÉRÉ dans l'outbox. Le verbe REFUSÉ
        (`start T-99999`) est T20 de `test_tasks_pont_v3_annonce.py`, pas doublé ici.
        Contrôle de non-vacuité : `depends-show`, hors `mutating`, ne dit RIEN ; et le
        seuil de déversement (`_SYNC_OUTBOX_SEUIL`) dépasse les 8 intents écrits, sans
        quoi la croissance de l'outbox serait mesurée sur une file qu'on rogne.
        MUTATIONS : retirer l'un des six verbes du littéral `mutating` de `main` ->
        F1[ce verbe] rougit (0 annonce) ; ajouter `"depends-show"` à ce littéral -> le
        contrôle rougit ; `pont_commande["refus"] = True` retiré de `replay_sync` -> DEUX
        annonces, les six rougissent ; branche `isinstance(exc, refus_emplacement)`
        retirée -> la levée remonte, F1 en ERREUR."""
        self.assertGreater(tasks._SYNC_OUTBOX_SEUIL, 8, "précondition : aucun déversement")
        self._poser_lien()
        a, b = self._deux_taches()
        for argv, champ, attendu in self._verbes(a, b):
            with self.subTest(verbe=argv[0]):
                self._verbe_abouti(argv, champ, attendu, a,
                                   "pont V3 REFUSÉ (emplacement du store refusé",
                                   "board écrit sans relecture V3")
        with self.subTest(verbe="depends-show (contrôle)"):
            rc, _out, err = self._main("depends-show", a)
            self.assertEqual(0, rc, err)
            self.assertEqual([], self._lignes(err, "pont V3"), "un verbe non mutant a construit le pont")
        self._cible_intacte()

    def test_F2_verbes_mutants_par_le_chemin_de_PANNE(self) -> None:
        """PAR LE VRAI CANAL (couture `cadre.ledger.store` introuvable, patron T3) :
        `start`, `depends --add` et `done` ABOUTISSENT et disent UNE fois « pont V3 en
        PANNE ». TOUT tourne sous le masque, `new a` et `new b` compris : aucun store ne
        naît, jamais. Aucun lien : ce témoin tourne sur tout hôte, et couvre (f) même là
        où F1 saute. MUTATIONS : retirer `start`, `depends` ou `done` du littéral
        `mutating` -> F2[ce verbe] rougit ; branche `_est_panne_infrastructure` retirée
        de `replay_sync` -> la panne remonte, F2 en ERREUR."""
        self.assertGreater(tasks._SYNC_OUTBOX_SEUIL, 8, "précondition : aucun déversement")
        with self._couture_ledger_store_absente():
            a, b = self._deux_taches()
            for argv, champ, attendu in self._verbes(a, b):
                if argv[0] not in ("start", "depends", "done"):
                    continue
                with self.subTest(verbe=argv[0]):
                    self._verbe_abouti(argv, champ, attendu, a,
                                       "pont V3 en PANNE", "board écrit, intents conservés dans l'outbox")
        self.assertFalse(self.store.exists(), "aucun store créé sans la primitive")

    # -- T-00000792 (k) : l'`isinstance` d'`EmplacementRefuse` à DEUX copies -------
    # Seule `EmplacementRefuse` est épinglée à deux copies. `OuvertureImpossible` et
    # `HorsRacine` passent par la même couture (`_annonce_refus_construction`) sans
    # témoin à deux copies : une borne, pas une promesse.

    @staticmethod
    def _cles_cadre() -> dict[str, Any]:
        return {k: v for k, v in sys.modules.items() if k == "cadre" or k.startswith("cadre.")}

    def _montage_copie(self, copie: str) -> ExitStack:
        """Une copie de `cadre.ledger.store` derrière la couture, sous `patch.dict` de
        `sys.modules` ET de `run_export._MODULES_CADRE` (entrées `ledger.store` et
        `workspace` vidées) : tout est restauré à la sortie du `with`. `chemin` : le
        paquet est masqué (`None`), la couture répond par la branche (2) de `_cadre`,
        `_cadre_ledger_store_v3`. `paquet` : `src/` en tête de `sys.path` (retiré par
        `addCleanup`), clés `cadre*` RETIRÉES, la couture répond par la branche (1),
        `cadre.ledger.store`. Les préconditions se posent DANS le `with`."""
        pile = ExitStack()
        pile.enter_context(mock.patch.dict(sys.modules))
        pile.enter_context(mock.patch.dict(self.run_export._MODULES_CADRE))
        self.run_export._MODULES_CADRE.pop("ledger.store", None)
        self.run_export._MODULES_CADRE.pop("workspace", None)
        if copie == "chemin":
            sys.modules.update(dict.fromkeys(("cadre", "cadre.ledger", "cadre.ledger.store",
                                              "cadre.workspace")))
        else:
            src = str(REPO / "src")
            sys.path.insert(0, src)
            self.addCleanup(sys.path.remove, src)
            for cle in list(self._cles_cadre()):
                del sys.modules[cle]
        return pile

    def _exiger_paquet(self) -> None:
        """Branche (1) ÉQUIVALENTE à un paquet (`src/` sur `sys.path`), PAS une
        installation `pip` : `pip install` reste NON MESURÉ (patron de
        `test_cadre_ledger_redaction.py`). Introuvable -> `skipTest`, jamais un vert creux."""
        try:
            spec = importlib.util.find_spec("cadre.ledger.store")
        except ImportError:
            spec = None
        if spec is None:
            self.skipTest("précondition : `cadre.ledger.store` introuvable comme paquet depuis src/")

    def _store_de_la_couture(self) -> Any:
        return self.run_export._couture_ledger_store()[0]

    def test_vendor_seul_K1(self) -> None:
        """Le pont importe le paquet choisi, même lorsque les deux copies existent.

        Une provenance étrangère déjà chargée doit être refusée explicitement.
        """
        choisi = tasks._RESOLVEUR_V3.exiger(REPO, "agentic_v3").resolve()
        charge = Path(self.run_export.__file__).resolve().parents[1]
        self.assertEqual(choisi, charge, "le banc doit exercer le moteur choisi par le résolveur")
        paquet = sys.modules["agentic_v3"]
        with mock.patch.object(paquet, "__file__", str(REPO / "autre" / "__init__.py")):
            with self.assertRaises(tasks._RESOLVEUR_V3.ProvenanceRefusee):
                tasks._importer_pont_v3(REPO)

    def _refus_emplacement_un_board_ecrit(self, rc: int, err: str, titre: str) -> None:
        self.assertEqual(0, rc, f"la levée a remonté au lieu de refuser le pont : {err!r}")
        pont = self._lignes(err, "pont V3")
        self.assertEqual(1, len(pont), f"UNE annonce par commande attendue :\n{err}")
        self.assertIn("pont V3 REFUSÉ (emplacement du store refusé", pont[0])
        self.assertIn("board écrit sans relecture V3", pont[0])
        self.assertEqual([titre], [t["task"] for t in self._board()["tasks"]])

    def test_K1_isinstance_EmplacementRefuse_copie_chemin(self) -> None:
        """Copie PAR CHEMIN (branche (2) de `_cadre`, paquet masqué) : la classe que
        lève `create_tables` et celle que `_classe_emplacement_refuse` rend sont le
        MÊME objet-classe — rc 0, UNE annonce, board écrit. Commentaire relocalisé PAR
        NOM : `replay_sync` (`tasks_sync.py`), « `isinstance` VRAI mesuré (… copie par
        chemin ET `PYTHONPATH=src`) ». MUTATIONS : `_classe_emplacement_refuse` qui
        prend la classe par `importlib.import_module("cadre.ledger.store")` -> `()`,
        la levée remonte, K1 chemin en ERREUR ; même effet si la branche
        `isinstance(exc, refus_emplacement)` est retirée ; `refus` non mémorisé -> DEUX
        annonces."""
        self._poser_lien()
        cles = self._cles_cadre()
        with self._montage_copie("chemin"):
            self.assertEqual("_cadre_ledger_store_v3", self._store_de_la_couture().__name__,
                             "précondition : la couture répond par la copie par chemin")
            rc, _out, err = self._main("new", "sonde")
        self.assertEqual(cles, self._cles_cadre(), "fuite de `cadre*` dans sys.modules")
        self._refus_emplacement_un_board_ecrit(rc, err, "sonde")
        self._cible_intacte()

    def test_K1_isinstance_EmplacementRefuse_copie_paquet(self) -> None:
        """Copie PAQUET (branche (1) de `_cadre`, `src/` sur `sys.path`, l'équivalent
        de `PYTHONPATH=src`) : même attendu que la copie par chemin. MUTATIONS :
        `_classe_emplacement_refuse` qui prend la classe par
        `run_export._charger_par_chemin("ledger.store")` (l'AUTRE copie) -> la levée du
        paquet remonte, K1 paquet en ERREUR ; branche `isinstance` retirée -> idem ;
        `refus` non mémorisé -> DEUX annonces."""
        self._poser_lien()
        cles = self._cles_cadre()
        with self._montage_copie("paquet"):
            self._exiger_paquet()
            self.assertEqual("cadre.ledger.store", self._store_de_la_couture().__name__,
                             "précondition : la couture répond par le paquet")
            rc, _out, err = self._main("new", "sonde")
        self.assertEqual(cles, self._cles_cadre(), "fuite de `cadre*` dans sys.modules")
        self._refus_emplacement_un_board_ecrit(rc, err, "sonde")
        self._cible_intacte()

    def test_K1_isinstance_EmplacementRefuse_copies_croisees(self) -> None:
        """Le témoin DISCRIMINE : sous le montage paquet, `BoardBridge` lève
        l'`EmplacementRefuse` de l'AUTRE copie (par chemin) -> `isinstance` FAUX, la
        levée REMONTE de `main`, aucune annonce, board inchangé ; la classe de la MÊME
        copie (contrôle) -> rc 0, UNE annonce. Par injection : aucun lien requis.
        MUTATIONS : `_classe_emplacement_refuse` qui prend la classe par
        `_charger_par_chemin("ledger.store")` -> la classe étrangère est avalée,
        `assertRaises` rougit ; branche `isinstance` retirée -> le contrôle remonte."""
        cles = self._cles_cadre()
        with self._montage_copie("paquet"):
            self._exiger_paquet()
            paquet = self._store_de_la_couture()
            self.assertEqual("cadre.ledger.store", paquet.__name__,
                             "précondition : la couture répond par le paquet")
            chemin = self.run_export._charger_par_chemin("ledger.store")
            self.assertEqual("_cadre_ledger_store_v3", chemin.__name__)
            self.assertIsNot(paquet.EmplacementRefuse, chemin.EmplacementRefuse,
                             "précondition : deux copies, deux objets-classes")
            octets = self.board.read_bytes()
            err = io.StringIO()
            etrangere = chemin.EmplacementRefuse("banc : classe de l'autre copie")
            with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=etrangere), \
                    mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", err), \
                    self.assertRaises(chemin.EmplacementRefuse):
                tasks.main(["--root", str(self.root), "new", "croise"])
            self.assertEqual([], self._lignes(err.getvalue(), "pont V3"), err.getvalue())
            self.assertEqual(octets, self.board.read_bytes(), "le board a été écrit malgré la levée")
            meme = paquet.EmplacementRefuse("banc : classe de la même copie")
            with mock.patch.object(self.board_bridge, "BoardBridge", side_effect=meme):
                rc, _out, err_controle = self._main("new", "controle")
        self.assertEqual(cles, self._cles_cadre(), "fuite de `cadre*` dans sys.modules")
        self._refus_emplacement_un_board_ecrit(rc, err_controle, "controle")


if __name__ == "__main__":
    unittest.main()
