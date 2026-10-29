"""T-00000805 — un INSERT refusé ne laisse aucun journal d'attente, et le rejeu n'exporte que
ce que la base porte (ligne RENDUE par l'écrivain, ou ligne de la BASE). Chaque témoin nomme son MUTANT.
Bac : CADRE_PROJECT_ROOT ET CADRE_STATE_DIR sur un tempfile, `project_root=` explicite,
`_email_git` greffé. Aucune liaison ROOT à __file__, aucun skipTest (test_adopting_gate)."""

import datetime
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, redirect_stderr
from pathlib import Path
from unittest import mock

import agentic_v3.db.event_store as es
from agentic_v3.db import run_export
from agentic_v3.db.event_store import EventStore, RunStep


class _CurseurQuiRefuse:
    """Vrai curseur ; l'INSERT de l'événement lève `exc`."""

    def __init__(self, vrai, exc):
        self._v, self._exc = vrai, exc

    def execute(self, sql, *a):
        if "events_ledger" in sql and "INSERT" in sql:
            raise self._exc
        return self._v.execute(sql, *a)

    def __getattr__(self, nom):
        return getattr(self._v, nom)


class _Conn:
    """Vraie connexion ; `sur_commit` / `sur_select` interceptent, le reste délègue."""

    def __init__(self, vraie, sur_commit=None, select_leve=None, insert_leve=None):
        self._v, self._sc, self._sl, self._il = vraie, sur_commit, select_leve, insert_leve

    def cursor(self):
        c = self._v.cursor()
        return _CurseurQuiRefuse(c, self._il) if self._il else c

    def commit(self):
        if self._sc:
            self._sc()
        return self._v.commit()

    def execute(self, sql, *a):
        if self._sl and sql.lstrip().startswith("SELECT"):
            raise self._sl
        return self._v.execute(sql, *a)

    def __getattr__(self, nom):
        return getattr(self._v, nom)


class TestJournalOrphelin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        (base / "projet").mkdir()
        self.racine, self.state = base / "projet", base / "state"
        env = mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(self.racine),
                                           "CADRE_STATE_DIR": str(self.state)})
        env.start(); self.addCleanup(env.stop); self.addCleanup(self._tmp.cleanup)
        mail = mock.patch.object(run_export, "_email_git", return_value="banc@test")
        mail.start(); self.addCleanup(mail.stop)
        self.db = self.state / "v3.db"
        self.db.parent.mkdir(parents=True, exist_ok=True)

    def _store(self):
        return EventStore(self.db, project_root=self.racine)

    def _base(self):
        c = sqlite3.connect(str(self.db))
        try:
            return c.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0]
        finally:
            c.close()

    def _exportees(self):
        r = self.racine / "runs"
        return [json.loads(l) for p in (sorted(r.rglob("*.jsonl")) if r.exists() else [])
                for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _export(self):
        return len(self._exportees())

    def _journal_herite(self, task, op):
        """Journal EN ATTENTE d'un ULID commité (export coupé) : rend (ulid, chemin, contenu)."""
        s, u = self._store(), run_export.nouvel_ulid()
        with mock.patch.object(run_export, "ajouter_a_l_export", side_effect=RuntimeError("arret")):
            with self.assertRaises(RuntimeError):
                s.append_event(task, "dev", "TASK_CREATED", {"req_id": "A"}, operation_id=op, ulid=u)
        (j,) = self._journaux()
        return u, j, json.loads(j.read_text(encoding="utf-8"))

    def _journaux(self):
        return run_export.lister_journaux_attente(depuis=self.racine)

    def _ligne(self, task, op, ulid=None):
        return {"task_id": task, "agent_role": "dev", "event_type": "TASK_CREATED",
                "payload_json": json.dumps({"req_id": "R"}), "created_at": "2026-09-28 10:00:00",
                "operation_id": op, "event_kind": "TASK_CREATED", "attempt": 0,
                "ulid": ulid or run_export.nouvel_ulid(), "predecesseur_ulid": None}

    def _construire_en_capturant(self, **patch_es):
        err = io.StringIO()
        with redirect_stderr(err), ExitStack() as pile:
            if patch_es:
                pile.enter_context(mock.patch.multiple(es, **patch_es))
            self._store()
        return err.getvalue()

    # T1 — le skip vivant ne laisse rien. MUTANT : journal écrit AVANT l'INSERT (ordre de HEAD)
    # => 1 journal après le skip, et 2 lignes d'export après la construction suivante.
    def test_T1_le_skip_d_un_pas_deja_applique_ne_laisse_aucun_journal(self):
        s = self._store()
        pas = RunStep("op1", "T-1", "dev", "TASK_CREATED", {"req_id": "R"})
        self.assertTrue(s.apply_run_step(pas))
        self.assertFalse(s.apply_run_step(pas))
        self.assertEqual(self._journaux(), [])
        self._store()
        self.assertEqual((self._base(), self._export()), (1, 1))

    # T2 — TOUTE exception de l'INSERT (contrainte, verrou, interruption) : 0 journal, 0 .tmp.
    # MUTANT : ordre de HEAD => le journal existe.
    def test_T2_aucun_journal_quelle_que_soit_l_exception_de_l_INSERT(self):
        s = self._store()
        for exc in (sqlite3.IntegrityError("UNIQUE constraint failed"),
                    sqlite3.OperationalError("database is locked"), KeyboardInterrupt()):
            conn = es.get_db_connection(self.db)
            try:
                with self.assertRaises(type(exc)):
                    s._ecrire_evenement(_CurseurQuiRefuse(conn.cursor(), exc), "T-2", "dev",
                                        "TASK_CREATED", "{}", operation_id="op2",
                                        event_kind="TASK_CREATED", attempt=0)
            finally:
                conn.close()
            self.assertEqual(self._journaux(), [], type(exc).__name__)
            dossier = run_export.journal_attente(run_export.nouvel_ulid(), depuis=self.racine).parent
            self.assertEqual(list(dossier.glob("*.tmp")) if dossier.is_dir() else [], [])

    # T3 — le journal EN ATTENTE d'un ULID déjà commité survit à une reprise du même pas, INTACT
    # (Critique B C1). MUTANTS : (i) ordre de HEAD => contenu ÉCRASÉ par le payload divergent ;
    # (ii) effacement du journal sur échec de l'INSERT => export 0 à jamais.
    def test_T3_le_journal_en_attente_d_un_ulid_commite_survit_a_la_reprise(self):
        u = run_export.nouvel_ulid()
        s = self._store()
        pas = RunStep("op3", "T-3", "dev", "TASK_CREATED", {"req_id": "R"}, ulid=u)
        with mock.patch.object(run_export, "ajouter_a_l_export", side_effect=RuntimeError("arret")):
            with self.assertRaises(RuntimeError):
                s.apply_run_step(pas)
        (j,) = self._journaux()
        avant = j.read_bytes()
        self.assertFalse(s.apply_run_step(pas))
        divergent = RunStep("op3", "T-3", "dev", "TASK_CREATED", {"req_id": "AUTRE"}, ulid=u)
        with self.assertRaises(ValueError):
            s.apply_run_step(divergent)
        self.assertEqual(self._journaux(), [j])
        self.assertEqual(j.read_bytes(), avant, "le journal en attente a été réécrit")
        self._store()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))

    # T4 — le journal existe à l'instant du COMMIT (invariant décidé le 2026-09-17).
    # MUTANT : journal jamais écrit par l'écrivain (ou écrit après le commit) => vus == [False].
    def test_T4_le_journal_existe_au_moment_du_commit(self):
        s = self._store()
        vus = []
        vrai = es.get_db_connection
        with mock.patch.object(es, "get_db_connection", side_effect=lambda p: _Conn(
                vrai(p), sur_commit=lambda: vus.append(bool(self._journaux())))):
            s.append_event("T-4", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op4")
        self.assertEqual(vus, [True])
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))

    # T5 — la forme de l'ULID est validée AVANT l'INSERT : identité déjà présente + ULID de 27
    # caractères => RunExportError, jamais un skip. MUTANT : retirer la validation préalable => False.
    def test_T5_ulid_hors_forme_leve_avant_l_INSERT(self):
        s = self._store()
        s.apply_run_step(RunStep("op5", "T-5", "dev", "TASK_CREATED", {"req_id": "R"}))
        with self.assertRaises(run_export.RunExportError):
            s.apply_run_step(RunStep("op5", "T-5", "dev", "TASK_CREATED", {"req_id": "R"},
                                     ulid="0" * 27))

    # T6 — REJEU d'un journal dont l'identité est prise sous un autre ULID (ULID ABSENT de la base) :
    # NON exporté, CONSERVÉ, annoncé (ULID + identité + base consultée, orphelin POSSIBLE, S-00003233),
    # à chaque construction. MUTANTS : `except IntegrityError` nu (HEAD) => export +1 ; effacer le
    # journal refusé => rouge (S-00003179, S-00003209) ; base non nommée => rouge.
    def test_T6_journal_refuse_par_la_base_n_est_pas_exporte_et_reste_annonce(self):
        s = self._store()
        s.append_event("T-6", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op6")
        orphelin = self._ligne("T-6", "op6")
        j = run_export.ecrire_journal_attente(orphelin, depuis=self.racine)
        for _ in range(2):
            err = self._construire_en_capturant()
            self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, [j]))
            self.assertIn("REFUSE par la base (ULID absent", err)
            self.assertIn(f"ULID absent de {self.db} : orphelin POSSIBLE", err)
            self.assertIn("T-00000825", err)
            self.assertIn(f"ulid={orphelin['ulid']}", err)
            self.assertIn("op6", err)

    # T7 — REJEU légitime : l'ULID est en base, l'export manque => export 1, journal effacé.
    # MUTANT : la preuve inversée (tout IntegrityError = refusé) => export 0.
    def test_T7_journal_deja_applique_est_exporte_puis_efface(self):
        s = self._store()
        with mock.patch.object(run_export, "ajouter_a_l_export", side_effect=RuntimeError("arret")):
            with self.assertRaises(RuntimeError):
                s.append_event("T-7", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op7")
        self.assertEqual((self._base(), self._export(), len(self._journaux())), (1, 0, 1))
        self._store()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))

    # T8 — un SELECT qui lève = « echec base », jamais « echec export » ; journal conservé.
    # MUTANT : SELECT hors du try => l'except extérieur annonce « echec export ».
    def test_T8_select_de_preuve_qui_leve_s_annonce_echec_base(self):
        s = self._store()
        s.append_event("T-8", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op8")
        j = run_export.ecrire_journal_attente(self._ligne("T-8", "op8"), depuis=self.racine)
        vrai = es.get_db_connection
        err = self._construire_en_capturant(get_db_connection=lambda p: _Conn(
            vrai(p), select_leve=sqlite3.OperationalError("database is locked")))
        self.assertIn("echec base", err)
        self.assertNotIn("echec export", err)
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, [j]))

    # T9 — journal au NOM valide, ULID de 27 caractères DANS le contenu : refus DÉFINITIF (S-00003233
    # (d)), 0 base, 0 export, conservé, annoncé par son PROPRE libellé — jamais « echec base », qui
    # promet un rejeu — ULID hors forme affiché en `repr`. MUTANTS : garde `ulid_bien_forme` du rejeu
    # retirée => `_valider_ulid` lève dans l'écrivain, « echec base » ; ULID affiché brut => rouge.
    def test_T9_ulid_hors_forme_dans_le_contenu_d_un_journal_du_rejeu(self):
        self._store()
        j = run_export.ecrire_journal_attente(self._ligne("T-9", "op9"), depuis=self.racine)
        contenu = json.loads(j.read_text(encoding="utf-8")); contenu["ulid"] = "0" * 27
        j.write_text(json.dumps(contenu), encoding="utf-8")
        for _ in range(2):
            err = self._construire_en_capturant()
            self.assertEqual((self._base(), self._export(), self._journaux()), (0, 0, [j]))
            self.assertIn("journal d'attente REFUSE (ULID hors forme, definitif, jamais rejoue)", err)
            self.assertIn(f"ulid={'0' * 27!r}", err)
            self.assertNotIn("echec base", err)

    # T10 — deux constructions lâchées ensemble (barrière `pret_i` puis `go`, jamais un seuil de
    # temps) : K légitimes + M orphelins d'identité => export = M + K exactement, M journaux
    # conservés, rc 0 x2. Il ne garde QUE « pas de double export », pas l'entrelacement.
    # MUTANT : `except IntegrityError` nu => export = M + K + M.
    def test_T10_deux_processus_sur_K_legitimes_et_M_orphelins(self):
        K = M = 6
        s = self._store()
        for i in range(M):
            s.append_event(f"T-M{i}", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id=f"opM{i}")
        for i in range(M):
            run_export.ecrire_journal_attente(self._ligne(f"T-M{i}", f"opM{i}"), depuis=self.racine)
        for i in range(K):
            run_export.ecrire_journal_attente(self._ligne(f"T-K{i}", f"opK{i}"), depuis=self.racine)
        self.assertEqual((self._base(), self._export(), len(self._journaux())), (M, M, M + K))
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        boot = ("import os,sys,time; sys.path.insert(0, sys.argv[1]); from agentic_v3.db import run_export; "
                "run_export._email_git = lambda depuis=None: 'banc@test'; "
                "from agentic_v3.db.event_store import EventStore; from pathlib import Path; "
                "open(sys.argv[4], 'w').close(); fin = time.time() + 60\n"
                "while not os.path.exists(sys.argv[5]) and time.time() < fin: time.sleep(0.001)\n"
                "EventStore(Path(sys.argv[2]), project_root=Path(sys.argv[3]))")
        depot = str(Path(run_export.__file__).resolve().parents[2])
        prets, go = [self.state / f"pret_{i}" for i in range(2)], self.state / "go"
        procs = [subprocess.Popen([sys.executable, "-B", "-c", boot, depot, str(self.db),
                                   str(self.racine), str(prets[i]), str(go)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for i in range(2)]
        try:
            fin = time.time() + 60
            while not all(p.exists() for p in prets) and time.time() < fin:
                time.sleep(0.005)
            self.assertTrue(all(p.exists() for p in prets), "barrière : un processus n'est jamais prêt")
            go.touch()
            for p in procs:
                _o, e = p.communicate(timeout=90)
                self.assertEqual(p.returncode, 0, e)
        finally:
            for p in procs:
                if p.poll() is None:
                    p.kill(); p.communicate()
        self.assertEqual((self._base(), self._export(), len(self._journaux())), (M + K, M + K, M))

    # T11 — journal HÉRITÉ de l'ordre d'avant ce lot : en attente d'un ULID commité, puis RÉÉCRIT
    # (payload divergent) par un INSERT refusé. L'ULID est en base, elle fait foi (S-00003209) : SA
    # ligne est exportée, annoncée, journal effacé — jamais REFUSE. MUTANTS : J (preuve par l'ULID
    # seul, `SELECT 1`) => le contenu du JOURNAL (`B-DIVERGE`) exporté ; ancien refus => export 0.
    def test_T11_journal_herite_au_contenu_divergent_exporte_la_ligne_de_la_base(self):
        u, j, contenu = self._journal_herite("T-11", "op11")
        contenu["payload_json"] = json.dumps({"req_id": "B-DIVERGE"})
        j.write_text(json.dumps(contenu), encoding="utf-8")
        err = self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
        (exportee,) = self._exportees()
        self.assertEqual((exportee["ulid"], json.loads(exportee["payload_json"])), (u, {"req_id": "A"}))
        self.assertIn("journal divergent de la base, ligne de la BASE", err)
        self.assertIn(f"ulid={u}", err)
        self.assertNotIn("REFUSE", err)

    # T12 — une OperationalError (`database is locked`) à l'INSERT du rejeu n'est PAS un refus :
    # « echec base », jamais « REFUSE », journal conservé. MUTANT N5 : `isinstance(exc,
    # sqlite3.IntegrityError)` -> `True` => le SELECT ne trouve pas l'ULID et annonce REFUSE.
    def test_T12_verrou_au_rejeu_s_annonce_echec_base_jamais_refuse(self):
        self._store()
        j = run_export.ecrire_journal_attente(self._ligne("T-12", "op12"), depuis=self.racine)
        vrai = es.get_db_connection
        err = self._construire_en_capturant(get_db_connection=lambda p: _Conn(
            vrai(p), insert_leve=sqlite3.OperationalError("database is locked")))
        self.assertIn("echec base", err)
        self.assertNotIn("REFUSE", err)
        self.assertEqual((self._base(), self._export(), self._journaux()), (0, 0, [j]))

    # T13 — recette de T11, UNE colonne divergente à la fois (hors `payload_json`, déjà T11, et
    # `ulid`, la clé) : la ligne de la BASE est exportée (valeur d'AVANT la divergence), annoncée,
    # journal effacé. Cas le plus probable d'un journal hérité : SEUL `created_at` diffère (même pas
    # repris une seconde plus tard). `operation_id` / `event_kind` changés donnent une identité NEUVE,
    # mais l'INSERT du rejeu est REFUSÉ quand même : `uq_events_ulid` rejette d'abord l'ULID déjà
    # commité (mesuré, jamais un INSERT réussi). Bac NEUF par colonne (racine ET état) : base et
    # export d'une colonne fausseraient les comptes de la suivante. MUTANTS : X1 (preuve bornée à
    # `payload_json`) => 8 colonnes rouges ; X3 (`created_at` retiré du SELECT) => `created_at` rouge.
    def test_T13_journal_herite_divergent_sur_une_seule_colonne_exporte_la_base(self):
        def seconde_plus_tard(c):
            t = datetime.datetime.strptime(c["created_at"], "%Y-%m-%d %H:%M:%S")
            return (t + datetime.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        divergences = {"task_id": lambda c: c["task_id"] + "-AUTRE",
                       "agent_role": lambda c: "reviewer", "event_type": lambda c: "TASK_UPDATED",
                       "created_at": seconde_plus_tard,
                       "operation_id": lambda c: c["operation_id"] + "-AUTRE",
                       "event_kind": lambda c: c["event_kind"] + "-AUTRE",
                       "attempt": lambda c: c["attempt"] + 1,
                       "predecesseur_ulid": lambda c: run_export.nouvel_ulid()}
        self._store()  # borne l'énumération : toute colonne stockée hors clés a son témoin
        cx = sqlite3.connect(str(self.db))
        try:
            colonnes = {r[1] for r in cx.execute("PRAGMA table_info(events_ledger)")}
        finally:
            cx.close()
        self.assertEqual(set(divergences), colonnes - {"event_id", "ulid", "payload_json"})
        for col, diverger in divergences.items():
            base = Path(self._tmp.name) / f"bac_{col}"
            (base / "projet").mkdir(parents=True)
            self.racine, self.state = base / "projet", base / "state"
            self.db = self.state / "v3.db"
            self.state.mkdir()
            with self.subTest(colonne=col), mock.patch.dict(os.environ, {
                    "CADRE_PROJECT_ROOT": str(self.racine), "CADRE_STATE_DIR": str(self.state)}):
                u, j, contenu = self._journal_herite("T-13", "op13")
                avant = contenu[col]
                contenu[col] = diverger(contenu)
                j.write_text(json.dumps(contenu), encoding="utf-8")
                err = self._construire_en_capturant()
                self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
                (exportee,) = self._exportees()
                self.assertEqual((exportee["ulid"], exportee[col]), (u, avant))
                self.assertIn("journal divergent de la base", err)
                self.assertNotIn("REFUSE", err)

    # T14 — recette de T11, `predecesseur_ulid` = la CHAÎNE "None" au journal, NULL en base : NULL ≠
    # "None", donc divergent, et la ligne de la BASE est exportée (`predecesseur_ulid` null). MUTANT :
    # `str()` nu dans la comparaison => « mêmes colonnes », le journal exporté porte "None".
    def test_T14_null_en_base_n_egale_pas_la_chaine_None_du_journal(self):
        u, j, contenu = self._journal_herite("T-14", "op14")
        self.assertIsNone(contenu["predecesseur_ulid"])
        contenu["predecesseur_ulid"] = "None"
        j.write_text(json.dumps(contenu), encoding="utf-8")
        err = self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
        (exportee,) = self._exportees()
        self.assertEqual((exportee["ulid"], exportee["predecesseur_ulid"]), (u, None))
        self.assertIn("journal divergent de la base", err)

    # T15 — `assurer_marqueur_partition` (jusqu'à 3 appels git) n'est JAMAIS appelé transaction
    # ouverte là où l'écrivain l'ouvre lui-même : `append_event` (donc `apply_run_step`) et le rejeu.
    # HORS PORTÉE, écrit plutôt que tu : `consume_board_intent`, `enqueue_board_command` et
    # `ack_board_command_with_event` appellent l'écrivain SOUS leur `BEGIN IMMEDIATE` — le marqueur y
    # reste sous verrou (chemin rapide : un `stat` quand le constructeur l'a posé). Base explicite :
    # le constructeur ne marque pas, l'appel est réel. MUTANT : ancien appel sous verrou (validation
    # seule avant l'INSERT, `ecrire_journal_attente` sans `prepare=True` après) => un appel ouvert.
    def test_T15_le_marqueur_n_est_jamais_pose_transaction_ouverte_hors_board(self):
        s, conns, vus = self._store(), [], []
        vraie_conn, vrai_marqueur = es.get_db_connection, run_export.assurer_marqueur_partition

        def ouverte(c):
            try:
                return c.in_transaction
            except sqlite3.ProgrammingError:  # connexion déjà fermée
                return False

        def espion(*a, **k):
            vus.append(any(ouverte(c) for c in conns))
            return vrai_marqueur(*a, **k)

        with ExitStack() as pile:
            pile.enter_context(mock.patch.object(
                es, "get_db_connection", side_effect=lambda p: conns.append(vraie_conn(p)) or conns[-1]))
            pile.enter_context(mock.patch.object(run_export, "assurer_marqueur_partition", side_effect=espion))
            s.append_event("T-15", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="op15")
            ecrits = len(vus)
            with mock.patch.object(run_export, "ajouter_a_l_export", side_effect=RuntimeError("arret")):
                with self.assertRaises(RuntimeError):
                    s.apply_run_step(RunStep("op15b", "T-15", "dev", "TASK_CREATED", {"req_id": "R"}))
            self._store()  # rejeu du journal laissé par l'export coupé
        self.assertGreater(ecrits, 0, "append_event n'a jamais appelé le marqueur : témoin inerte")
        self.assertEqual(vus, [False] * len(vus))
        self.assertEqual((self._base(), self._export(), self._journaux()), (2, 2, []))

    # T16 — un `operation_id` portant un `\n` (journal hostile) ne produit qu'UNE ligne stderr : les
    # champs du journal affichés passent par `repr` (S-00003209, point 4). Recette de T6 (ULID absent).
    # MUTANT : `operation_id` sans `!r` => deux lignes.
    def test_T16_un_saut_de_ligne_du_journal_ne_fait_qu_une_ligne_stderr(self):
        op = "op16\nevent_store: FAUSSE LIGNE"
        s = self._store()
        s.append_event("T-16", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id=op)
        j = run_export.ecrire_journal_attente(self._ligne("T-16", op), depuis=self.racine)
        err = self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, [j]))
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertIn(repr(op), err)

    # T17 — rejeu RÉUSSI (ULID absent de la base) d'un journal sans `created_at`, `attempt` = "0" et
    # une clé en trop : l'export porte la ligne RENDUE par l'écrivain (S-00003233 (a)) — `created_at`
    # et `attempt` de la BASE, pas la clé en trop. MUTANT : ligne rendue jetée => journal brut exporté.
    def test_T17_rejeu_reussi_exporte_la_ligne_rendue_par_l_ecrivain(self):
        self._store()
        contenu = self._ligne("T-17", "op17")
        del contenu["created_at"]
        contenu.update(attempt="0", cle_en_trop="X")
        run_export.ecrire_journal_attente(contenu, depuis=self.racine)
        self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
        cx = sqlite3.connect(str(self.db))
        try:
            cree, essai = cx.execute("SELECT created_at, attempt FROM events_ledger WHERE ulid=?",
                                     (contenu["ulid"],)).fetchone()
        finally:
            cx.close()
        self.assertIsNotNone(cree)
        (exportee,) = self._exportees()
        self.assertEqual((exportee.get("created_at"), exportee["attempt"]), (cree, essai))
        self.assertIsInstance(exportee["attempt"], int)
        self.assertNotIn("cle_en_trop", exportee)

    # T18 — recette de T11, `ajouter_a_l_export` en panne au rejeu : l'annonce « divergent » ne sort
    # qu'APRÈS un export RÉUSSI (S-00003233 (b)) — absente ici, « echec export » annoncé, journal
    # conservé. MUTANT : annonce imprimée avant l'export => « divergent » sur stderr.
    def test_T18_l_annonce_divergent_attend_un_export_reussi(self):
        _u, j, contenu = self._journal_herite("T-18", "op18")
        contenu["payload_json"] = json.dumps({"req_id": "B-DIVERGE"})
        j.write_text(json.dumps(contenu), encoding="utf-8")
        with mock.patch.object(run_export, "ajouter_a_l_export", side_effect=RuntimeError("panne")):
            err = self._construire_en_capturant()
        self.assertIn("echec export", err)
        self.assertNotIn("divergent", err)
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 0, [j]))

    # T19 — recette de T11, valeurs IDENTIQUES mais une clé en trop au journal : divergent par
    # l'ENSEMBLE des clés (S-00003233 (b)), annoncé, ligne de la BASE exportée sans la clé.
    # MUTANT : comparaison des clés retirée => aucune annonce.
    def test_T19_une_cle_en_trop_au_journal_est_une_divergence(self):
        _u, j, contenu = self._journal_herite("T-19", "op19")
        contenu["cle_en_trop"] = "X"
        j.write_text(json.dumps(contenu), encoding="utf-8")
        err = self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
        (exportee,) = self._exportees()
        self.assertNotIn("cle_en_trop", exportee)
        self.assertIn("journal divergent de la base", err)

    # T20 — recette de T11, `attempt` = "0" (chaîne) au journal, 0 en base : ÉGAUX par affinité, donc
    # aucune annonce, mais la ligne exportée est TOUJOURS celle de la BASE (S-00003233 (b)), `attempt`
    # entier. MUTANT : ligne de la BASE seulement si divergent => le journal exporté porte "0".
    def test_T20_ulid_en_base_exporte_toujours_la_ligne_de_la_base(self):
        u, j, contenu = self._journal_herite("T-20", "op20")
        contenu["attempt"] = "0"
        j.write_text(json.dumps(contenu), encoding="utf-8")
        err = self._construire_en_capturant()
        self.assertEqual((self._base(), self._export(), self._journaux()), (1, 1, []))
        (exportee,) = self._exportees()
        self.assertEqual((exportee["ulid"], exportee["attempt"]), (u, 0))
        self.assertIsInstance(exportee["attempt"], int)
        self.assertNotIn("divergent", err)


if __name__ == "__main__":
    unittest.main()
