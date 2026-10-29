"""Témoins run par auteur : l'unité sans email git n'écrit rien ; en intégration, append_event garde
journal et base jusqu'à convergence (amendement CONSTAT 3 du plan, décision pilote 2026-09-21 : TestEmpreinteEtCopie)."""

import inspect
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

from agentic_v3.db import run_export
from agentic_v3.db.run_export import RESERVE_BACKFILL, RunExportError, ajouter_a_l_export, chemin_export, empreinte_auteur, identifiant_de_copie
from agentic_v3.db.schema import create_tables

#: La racine RÉELLE du dépôt (ancien emplacement ou vendor), ancrée sur `__file__` — sert au témoin 17 (non-fuite).
#: `test_adopting_gate` balaye ce fichier par cette liaison `\bROOT\b` ; le seul site nommant un chemin
#: `strip:` (`runs/`) porte son marqueur `# adopting-tree:` en fenêtre.
ROOT = Path(__file__).resolve().parents[4] if Path(__file__).resolve().parents[2].name == "vendor" else Path(__file__).resolve().parents[2]


def test_import_sans_resolveur_repli_src_cadre(tmp_path):  # arbre partiel sans .agents/bin/vendor_paths.py : rc 0
    shutil.copytree(Path(run_export.__file__).resolve().parents[1], tmp_path / "agentic_v3", ignore=shutil.ignore_patterns("__pycache__"))
    p = subprocess.run([sys.executable, "-I", "-B", "-c", "import sys; sys.path.insert(0, sys.argv[1]); from agentic_v3.db import run_export as r; print(r._SRC_CADRE)", str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert (p.returncode, p.stdout.strip()) == (0, str(tmp_path.resolve() / "src" / "cadre")), p.stderr


def test_racine_vendor_seul(tmp_path):
    from agentic_v3.db import event_store
    from agentic_v3.reconciliation import board_bridge
    module = Path(run_export.__file__).resolve()
    racine = module.parents[4] if module.parents[2].name == "vendor" else module.parents[2]
    cadre = racine / ".agents/vendor/cadre"
    if not (cadre / "__init__.py").is_file():
        cadre = racine / "src/cadre"
    assert run_export._racine_reelle() == racine == ROOT
    assert run_export._SRC_CADRE == cadre
    assert event_store._CHEMIN_REDACTION == cadre / "ledger/redaction.py"
    with mock.patch.object(run_export, "_vendor_paths") as resolver:
        resolver.return_value.dossier_paquet.return_value = tmp_path / "cadre-vendor"
        assert run_export._dossier_cadre() == tmp_path / "cadre-vendor"
        resolver.return_value.dossier_paquet.assert_called_once_with(racine, "cadre")
    bridge = object.__new__(board_bridge.BoardBridge)
    bridge.project_root = tmp_path
    bridge._tasks_module_cache = None
    with mock.patch.object(board_bridge.importlib.util, "spec_from_file_location",
                           side_effect=ValueError("capture")) as charger:
        with pytest.raises(ValueError, match="capture"):
            bridge._tasks_module()
    assert Path(charger.call_args.args[1]) == racine / ".agents/bin/tasks.py"

# Faux secrets non valides (gitleaks 8.30.1), concaténés pour rester hors alerte.
FAUX_AWS = "AKIA" + "Z3XYQ7WNRT4KLMND"

# Un ULID valide (Crockford base32) dont l'horodatage de tête décode un mois réel.
_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"

#: Redirections git filtrées par __main__ et _env_sans_git pour les subprocess.
#: Sous unittest -m, __main__ ne tourne pas : seules les sondes qui appellent
#: _env_sans_git tiennent. Sans filtre, GIT_DIR peut viser le dépôt hôte.
#: Liste recopiée de conftest.py pour les lancements directs sans conftest.
#: Un hook git peut injecter ces variables (T-00000695/696).
_GIT_REDIRECTIONS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
)
_GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _git_herite(nom: str) -> bool:
    return nom in _GIT_REDIRECTIONS or nom.startswith(_GIT_CONFIG_PREFIXES)


def _env_sans_git() -> dict:
    """Copie de l'environnement du processus SANS les variables `_git_herite`."""
    return {k: v for k, v in os.environ.items() if not _git_herite(k)}


class _PartitionFixture(unittest.TestCase):
    """Pose `CADRE_PROJECT_ROOT` ET `CADRE_STATE_DIR` sur un `tempfile` isolé —
    aucune variable `ROOT` liée à `__file__`, donc `test_adopting_gate` ne
    balaye pas ce fichier pour ces bancs (seul le témoin 17 nomme le runs/ réel)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        racine = Path(self._tmp.name)
        (racine / "projet").mkdir()
        self.racine = racine / "projet"
        self.state = racine / "state"
        self._env = mock.patch.dict(
            os.environ,
            {
                "CADRE_PROJECT_ROOT": str(self.racine),
                "CADRE_STATE_DIR": str(self.state),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.addCleanup(self._tmp.cleanup)

    def _runs(self) -> Path:
        return self.racine / "runs"

    def _db(self) -> Path:
        db = self.state / "v3.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        return db

    def _compter(self, db: Path) -> int:
        conn = sqlite3.connect(str(db))
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0])
        finally:
            conn.close()

    def _texte_export(self) -> str:
        if not self._runs().exists():
            return ""
        return "".join(
            p.read_text(encoding="utf-8") for p in sorted(self._runs().rglob("*.jsonl"))
        )

    def _lignes_export(self) -> int:
        return len([l for l in self._texte_export().splitlines() if l.strip()])


class TestEmpreinteEtCopie(_PartitionFixture):
    def test_un_email_git_absent_leve_a_l_unite_et_le_chemin_integration_DIFFERE(self) -> None:
        """CONSTAT 3 — AMENDEMENT DU CONTRAT DU PLAN, INSCRIT PLUTÔT QUE CONTOURNÉ.

        Le plan (étape 1) prescrivait « adresse git absente => aucune écriture
        d'aucune sorte, ni journal, ni base, ni export ». C'est VRAI du bras UNITÉ
        (`ajouter_a_l_export` refuse AVANT d'écrire) mais MESURÉ FAUX du chemin
        d'INTÉGRATION : `append_event` écrit le journal d'attente PUIS insère et
        `commit()` en base, et ce n'est qu'À L'EXPORT que l'auteur (git email) est
        requis. Base et journal sont déjà écrits (`export=0 journal_attente=1
        lignes_base=1`), et l'export est DIFFÉRÉ. Rien n'est perdu : le journal est
        CONSERVÉ, rejoué, et l'export se COMPLÈTE dès qu'une adresse existe. Ce
        témoin asserte cette vérité mesurée et REMPLACE la clause « aucune écriture ».

        SECOND AMENDEMENT, DATÉ 2026-09-21, ET CE N'EST PAS UN ROGNAGE DE TEST. Le
        bras d'INTÉGRATION assertait auparavant que `append_event` LÈVE
        `RunExportError` sur auteur absent. Il ne lève PLUS : il DIFFÈRE (base
        écrite, journal conservé, export vide, aucune exception), SYMÉTRIQUE de
        `_rejouer_journaux_attente` qui différait déjà sans lever. MOTIF, une
        propriété du BOARD mesurée : la levée remontait à `drain_sync_outbox`, qui
        prenait le miroir board→V3 RÉUSSI (le `commit()` est déjà passé) pour un
        échec, relâchait l'intent, et sa file se rouvrait à CHAQUE transition. Le
        banc `tasks.test.sh` (propriété « un champ changé = UNE ligne du store »)
        MESURAIT alors 45 lignes réécrites pour un seul `stage` au lieu de ≤ 4 ; avec
        le report en NON FATAL, 2. Les bras UNITÉ (lève), base-écrite,
        journal-conservé et convergence-au-rejeu sont INCHANGÉS et restent verts :
        SEULE la question « le miroir échoue-t-il quand l'export est différé ? » a
        changé de réponse — de « oui (lève) » à « non (diffère) ». C'est un
        CHANGEMENT DE COMPORTEMENT assumé (décision pilote du 2026-09-21, option
        export-layer ; T-00000693 devient sans objet dans son option B), pas un test
        affaibli pour verdir une correction.
        """
        # (1) Bras UNITÉ, conservé : refus nommé, aucun octet sous runs/.
        with self.assertRaises(RunExportError) as ctx:
            empreinte_auteur("")
        self.assertIn("user.email", str(ctx.exception))
        with mock.patch.object(run_export, "_email_git", return_value=""):
            with self.assertRaises(RunExportError):
                ajouter_a_l_export({"ulid": _ULID, "task_id": "T-X", "agent_role": "A"})
        self.assertFalse(
            any(self._runs().rglob("*")),
            "bras unité : aucun octet sous runs/ après un refus de `ajouter_a_l_export`",
        )

        # (2) Chemin d'INTÉGRATION, vérité MESURÉE (amendée 2026-09-21) : adresse
        #     absente => l'export est DIFFÉRÉ SANS LEVER — base ÉCRITE, journal
        #     CONSERVÉ, export VIDE, AUCUNE exception. Le miroir board→V3 réussit ;
        #     seul l'export versionné attend un auteur. MUTATION (code fautif
        #     d'origine) : re-propager RunExportError depuis `_flush_export` — alors
        #     `append_event` lève ici et l'appel nu ci-dessous rougit.
        from agentic_v3.db.event_store import EventStore

        db = self._db()
        err = io.StringIO()
        with mock.patch.object(run_export, "_email_git", return_value=""):
            store = EventStore(db, project_root=self.racine)
            with redirect_stderr(err):
                store.append_event(
                    "T-INT", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="opint"
                )
            self.assertEqual(self._compter(db), 1, "la base porte l'événement committé")
            self.assertEqual(self._lignes_export(), 0, "export VIDE tant que l'auteur manque")
            self.assertTrue(
                run_export.lister_journaux_attente(depuis=self.racine),
                "le journal est CONSERVÉ (ni la base ni le journal ne sont perdus)",
            )
        # L'export différé est ANNONCÉ, jamais avalé en silence (borne L-00000136).
        self.assertIn(
            "journaux d'attente conserves", err.getvalue(),
            "le report d'export doit être annoncé sur stderr, pas silencieux",
        )
        # (3) CONVERGENCE : dès qu'une adresse existe, le rejeu au redémarrage
        #     COMPLÈTE l'export et efface le journal.
        with mock.patch.object(run_export, "_email_git", return_value="a@b.c"):
            EventStore(db, project_root=self.racine)  # redémarrage -> rejoue le journal
        self.assertEqual(self._lignes_export(), 1, "l'export se complète au rejeu sous auteur")
        self.assertFalse(
            run_export.lister_journaux_attente(depuis=self.racine),
            "le journal est effacé après convergence",
        )

    def test_deux_auteurs_deux_dossiers_et_une_copie_sans_information_machine(self) -> None:
        # Témoin 2 : casse et espaces normalisés (MUTATION a : retirer
        # .strip().lower()) ; deux tirages de copie diffèrent et ne portent
        # aucune information machine (MUTATION b : semer sur platform.node()).
        self.assertEqual(empreinte_auteur("A@B.C "), empreinte_auteur("a@b.c"))
        self.assertNotEqual(empreinte_auteur("a@b.c"), empreinte_auteur("d@e.f"))

        copie1 = identifiant_de_copie()
        # Un second poste : nouvelle partition, nouveau tirage.
        self.state.rename(self.state.with_name("state2"))
        with mock.patch.dict(
            os.environ, {"CADRE_STATE_DIR": str(self.state.with_name("state2b"))}
        ):
            copie2 = identifiant_de_copie()
        self.assertNotEqual(copie1, copie2)
        for copie in (copie1, copie2):
            self.assertEqual(len(copie), 16)
            import getpass
            import platform

            for interdit in (platform.node(), getpass.getuser(), str(Path.home())):
                if interdit:
                    self.assertNotIn(interdit, copie)

    def test_la_valeur_backfill_de_copie_est_RESERVEE(self) -> None:
        # Témoin 15 (bras unité) : identifiant_de_copie refuse une copie
        # « backfill » lue sur disque ; une écriture normale sous copie=backfill
        # est refusée SANS écrire un octet ; seule la porte backfill() l'accepte.
        chemin_copie = self.state / "projets"
        # identifiant_de_copie refuse d'ACCEPTER backfill lu sur disque.
        fichier = run_export._fichier_copie()
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(RESERVE_BACKFILL + "\n", encoding="utf-8")
        with self.assertRaises(RunExportError):
            identifiant_de_copie()

        # Voie normale refusée AVANT toute résolution d'auteur, aucun octet.
        with self.assertRaises(RunExportError):
            chemin_export(_ULID, copie=RESERVE_BACKFILL)
        with mock.patch.object(run_export, "_email_git", return_value="a@b.c"):
            with self.assertRaises(RunExportError):
                ajouter_a_l_export({"ulid": _ULID}, copie=RESERVE_BACKFILL)
        self.assertFalse(any(self._runs().rglob("*")) if self._runs().exists() else False)

        # La porte backfill() accepte la valeur réservée.
        with mock.patch.object(run_export, "_email_git", return_value="a@b.c"):
            ecrit = run_export.backfill({"ulid": _ULID, "task_id": "T"})
        self.assertTrue(ecrit.is_file())
        self.assertEqual(ecrit.parent.name, RESERVE_BACKFILL)
        self.assertTrue(str(chemin_copie))  # partition sous state_project


class TestLigneExport(_PartitionFixture):
    def test_la_ligne_exportee_est_deterministe_et_la_migration_idempotente(self) -> None:
        # Témoin 5 : la ligne est json.dumps(sort_keys=True) (MUTATION : retirer
        # sort_keys=True) et un même ULID n'apparaît qu'une fois (idempotence).
        ligne = {"ulid": _ULID, "task_id": "T-Z", "agent_role": "A", "attempt": 0}
        with mock.patch.object(run_export, "_email_git", return_value="a@b.c"):
            chemin = ajouter_a_l_export(dict(ligne), copie="c1")
            ajouter_a_l_export(dict(ligne), copie="c1")  # rejeu -> pas de doublon
        lignes = [
            l for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        self.assertEqual(len(lignes), 1, "un ULID déjà exporté ne se duplique pas")
        attendu = json.dumps(ligne, sort_keys=True, ensure_ascii=False)
        self.assertEqual(lignes[0], attendu, "clés triées, déterministe")


class TestBackfillHistorique(_PartitionFixture):
    """Témoins 20 et 15b (T-00000677) : le backfill de l'historique FRAPPE un ULID
    par ligne `ulid IS NULL`, l'ÉCRIT en base, et pose la borne S-00001594 EN TÊTE
    de CHAQUE fichier de mois. Base FABRIQUÉE sous `tempfile` — aucun site nommant
    le `runs/` réel."""

    def _fabriquer_historique(self):
        """Une base avec des lignes `ulid IS NULL` sur DEUX mois (fixture ≥ 2 mois,
        exigée par le témoin 15b), dont deux lignes de la MÊME seconde (départage
        monotone) et deux lignes d'une MÊME tâche (chaîne `predecesseur_ulid`)."""
        db = self._db()
        create_tables(db)
        conn = sqlite3.connect(str(db))
        lignes = [
            ("T-A", "2026-08-01 00:00:00"),  # T-A, aout, même seconde que la suivante
            ("T-A", "2026-08-01 00:00:00"),  # T-A, aout, MÊME seconde -> départage
            ("T-B", "2026-08-02 09:00:00"),  # T-B, aout
            ("T-A", "2026-09-15 12:00:00"),  # T-A, septembre (deuxième mois)
            ("T-B", "2026-09-15 12:00:01"),  # T-B, septembre
        ]
        for i, (task, created_at) in enumerate(lignes, start=1):
            conn.execute(
                "INSERT INTO events_ledger "
                "(task_id,agent_role,event_type,payload_json,created_at,"
                "operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
                (task, "BoardBridge", "BOARD_TASK_OBSERVED", "{}", created_at,
                 f"op{i}", "BOARD_TASK_OBSERVED", 0),
            )
        conn.commit()
        conn.close()
        return db

    def _ulids_base(self, db) -> dict:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            return {
                r["event_id"]: r["ulid"]
                for r in conn.execute("SELECT event_id, ulid FROM events_ledger")
            }
        finally:
            conn.close()

    def _fichiers_backfill(self):
        return sorted(self._runs().rglob("backfill/*.jsonl")) if self._runs().exists() else []

    def test_le_backfill_frappe_un_ulid_par_ligne_historique_et_l_ecrit_en_base(self):
        # Témoin 20 : après backfill, AUCUNE ligne NULL en base et chaque ligne du
        # texte porte l'ULID de SA ligne en base (fusion par ULID de l'étape 5 de
        # T-00000650). MUTATION : exporter sans UPDATE -> la base garde ses NULL, la
        # fusion par ULID ne retrouve pas l'historique -> nul_apres != 0.
        db = self._fabriquer_historique()
        avant = sqlite3.connect(str(db))
        n_null_avant = avant.execute(
            "SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL"
        ).fetchone()[0]
        avant.close()
        self.assertEqual(n_null_avant, 5, "la fixture doit poser 5 lignes historiques")

        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            res = run_export.backfill_historique(base=db, depuis=self.racine)

        base_ulids = self._ulids_base(db)
        self.assertEqual(
            sum(1 for u in base_ulids.values() if u is None), 0,
            "une ligne historique garde un ulid NULL après le backfill",
        )
        self.assertEqual(res["nul_apres"], 0)
        self.assertEqual(res["frappees"], 5)

        texte_ulids = set()
        for fichier in self._fichiers_backfill():
            for brute in fichier.read_text(encoding="utf-8").splitlines():
                brute = brute.strip()
                if not brute:
                    continue
                obj = json.loads(brute)
                if "ulid" in obj:  # ignore la ligne borne (une clé, pas d'ulid)
                    texte_ulids.add(obj["ulid"])
        self.assertEqual(
            texte_ulids, set(base_ulids.values()),
            "un ULID du texte n'est pas en base (ou l'inverse) — la fusion par ULID "
            "de l'étape 5 ne retrouverait pas l'historique",
        )

    def test_le_backfill_ecrit_sa_borne_en_tete(self):
        # Témoin 15b : pour TOUT fichier de mois produit, la PREMIÈRE ligne est
        # l'objet {"borne": …} nommant S-00001594. Fixture à ≥ 2 mois, sans quoi on
        # ne distingue pas « borne sur le premier fichier » de « borne sur CHAQUE
        # fichier ». MUTATION : n'écrire la borne que dans le premier fichier produit
        # -> le second commence par une ligne d'événement, l'assertion rougit.
        db = self._fabriquer_historique()
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            run_export.backfill_historique(base=db, depuis=self.racine)

        fichiers = self._fichiers_backfill()
        self.assertGreaterEqual(
            len(fichiers), 2,
            "fixture à ≥ 2 mois (sinon borne-sur-le-premier == borne-sur-chaque)",
        )
        for fichier in fichiers:
            lignes = [
                l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()
            ]
            premiere = json.loads(lignes[0])
            self.assertIsInstance(premiere, dict)
            self.assertIn(
                "borne", premiere, f"{fichier.name} : première ligne pas une borne"
            )
            self.assertIn(
                "S-00001594", lignes[0],
                f"{fichier.name} : la borne ne nomme pas la décision S-00001594",
            )
            # La borne n'a PAS d'ulid : reconstruire_depuis_exports l'ignore.
            self.assertNotIn("ulid", premiere)


class _IntegrationFixture(_PartitionFixture):
    """Fixtures avec auteur FIXÉ (jambe conteneur en root sans git email)."""

    def setUp(self) -> None:
        super().setUp()
        mail = mock.patch.object(run_export, "_email_git", return_value="banc@test")
        mail.start()
        self.addCleanup(mail.stop)

    def _store(self):
        from agentic_v3.db.event_store import EventStore

        return EventStore(self._db(), project_root=self.racine)


class TestOrdreEtReprise(_IntegrationFixture):
    def test_l_ordre_d_ecriture_survit_a_un_arret_entre_la_base_et_l_export(self) -> None:
        # Témoin 3 : arrêt injecté ENTRE le commit base et l'ajout export laisse le
        # journal ; au redémarrage il est rejoué, l'export porte l'événement UNE
        # fois. MUTATION : effacer le journal AVANT d'ajouter à l'export.
        db = self._db()
        store = self._store()
        with mock.patch.object(
            run_export, "ajouter_a_l_export", side_effect=RuntimeError("arrêt")
        ):
            with self.assertRaises(RuntimeError):
                store.append_event("T-3", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op3")
        self.assertEqual(self._compter(db), 1, "la base porte l'événement committé")
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=self.racine),
            "le journal doit SURVIVRE à l'arrêt",
        )
        # Redémarrage : nouvel EventStore -> _rejouer_journaux_attente.
        self._store()
        self.assertEqual(self._compter(db), 1, "le rejeu ne duplique pas dans la base")
        self.assertEqual(self._lignes_export(), 1, "l'export porte l'événement exactement une fois")
        self.assertFalse(
            run_export.lister_journaux_attente(depuis=self.racine),
            "le journal est effacé après rejeu",
        )

    def test_une_transaction_ANNULEE_ne_laisse_aucune_ligne_dans_l_export(self) -> None:
        # Témoin 3 bis. Bras (b) : échec de projection dans append_event ;
        # bras (a) : échec de réduction dans consume_board_intent APRÈS l'INSERT.
        from agentic_v3.db.event_store import EventStore

        db = self._db()
        store = self._store()
        # Bras (b) — MUTATION : ne pas effacer le journal dans la branche rollback.
        with mock.patch.object(EventStore, "_apply_projection", side_effect=RuntimeError("proj")):
            with self.assertRaises(RuntimeError):
                store.append_event("T-3B", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op3b")
        self.assertEqual(self._compter(db), 0, "la base ne porte AUCUNE ligne annulée")
        self.assertEqual(self._lignes_export(), 0, "l'export ne porte AUCUNE ligne annulée")
        self.assertFalse(run_export.lister_journaux_attente(depuis=self.racine), "aucun journal ne subsiste")

        # Bras (a) — intent sans `before` ni `after` : _reduce_board_intent lève
        # APRÈS l'INSERT (mutation (a) : remettre l'ajout export dans la txn).
        intent = {
            "operation_id": "op3a",
            "event_kind": "BOARD_STATE_MALFORMED",
            "affected_task_ids": ["T-3A"],
            "attempt": 0,
        }
        with self.assertRaises(Exception):
            store.consume_board_intent(intent)
        self.assertEqual(self._compter(db), 0)
        self.assertEqual(self._lignes_export(), 0)
        self.assertFalse(run_export.lister_journaux_attente(depuis=self.racine))

    def test_un_echec_reel_au_rejeu_n_exporte_ni_n_efface_le_journal(self) -> None:
        # CONSTAT 2 (trouvé par les DEUX revues) : dans `_rejouer_journaux_attente`,
        # un échec NON idempotent de l'INSERT (contention de verrou WAL :
        # `database is locked`, banale puisque hooks et mode nuit appellent
        # `tasks.py`) faisait QUAND MÊME l'export PUIS l'effacement du journal.
        # L'événement partait dans le TEXTE QUI FAIT AUTORITÉ, absent de la base,
        # sans un octet sur stderr, et le journal qui aurait permis le rattrapage
        # était détruit. Ce témoin couvre le CHEMIN DE REJEU (que le témoin 3 bis,
        # sur le chemin vivant, ne couvre pas). MUTATION (code fautif) : export=1,
        # journal effacé. Après correction : export=0, journal conservé.
        from agentic_v3.db.event_store import EventStore

        db = self._db()
        store = self._store()  # aucun journal en attente à la construction
        ligne = {
            "ulid": run_export.nouvel_ulid(), "predecesseur_ulid": None,
            "task_id": "T-2C", "agent_role": "run", "event_type": "TASK_CREATED",
            "event_kind": "TASK_CREATED", "attempt": 0, "operation_id": "op2c",
            "payload_json": "{}", "created_at": "2026-06-01 00:00:00",
        }
        run_export.ecrire_journal_attente(ligne, depuis=self.racine)  # jamais appliqué
        with mock.patch.object(
            EventStore, "_ecrire_evenement",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            store._rejouer_journaux_attente()
        self.assertEqual(self._compter(db), 0, "l'INSERT a échoué : rien en base")
        self.assertEqual(
            self._lignes_export(), 0,
            "un échec RÉEL ne doit RIEN publier dans le texte qui fait autorité",
        )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=self.racine),
            "le journal doit SURVIVRE à un échec réel, pour un rejeu ultérieur",
        )

    def test_un_journal_d_attente_corrompu_est_ANNONCE_a_chaque_rejeu(self) -> None:
        # critic-fable T3 (T-00000695/696) : un journal d'attente TRONQUÉ (`{`) était
        # ignoré MUET à chaque rejeu, et COMPTÉ dans les « N journaux conservés ». Il
        # est désormais annoncé sur stderr — chemin ET exception, UNE ligne par rejeu —
        # et CONSERVÉ (jamais effacé en silence). MUTATION (`continue` nu) : stderr
        # vide, rouge.
        store = self._store()  # aucun journal en attente à la construction
        chemin = run_export.journal_attente(run_export.nouvel_ulid(), depuis=self.racine)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("{", encoding="utf-8")
        for rejeu in (1, 2):
            err = io.StringIO()
            with redirect_stderr(err):
                store._rejouer_journaux_attente()
            sortie = err.getvalue()
            self.assertEqual(1, sortie.count(str(chemin)), f"rejeu {rejeu} : {sortie!r}")
            self.assertIn("ILLISIBLE", sortie)
            self.assertIn("JSONDecodeError", sortie)
            self.assertIn("COMPTE dans les journaux conserves", sortie)
            self.assertIn("a retirer a la main", sortie)
        self.assertTrue(chemin.is_file(), "le journal corrompu est CONSERVÉ, pas effacé")

    def test_toute_forme_illisible_est_annoncee_jamais_mortelle(self) -> None:
        # exec-critic (passes post-binôme T-00000695/696, et T-00000718) : quatre
        # formes faisaient LEVER le rejeu — donc mourir toute commande de board en
        # rc 1 (mesuré sur `tasks.py new`). Chacune est désormais annoncée comme le
        # `{` tronqué : UNE ligne, l'exception NOMMÉE, journal CONSERVÉ. MUTATIONS :
        # retirer `ValueError` de l'`except` — `\xff` lève, rouge ; retirer la
        # validation de forme — `[]` et `null` lèvent `AttributeError`, rouge ;
        # retirer `RecursionError` — l'imbrication lève, rouge.
        store = self._store()  # aucun journal en attente à la construction
        formes = (
            ("octet non UTF-8", b'{"ulid": "x\xff"}', "UnicodeDecodeError"),
            ("JSON non-objet []", b"[]", "forme inattendue : list"),
            ("JSON non-objet null", b"null", "forme inattendue : NoneType"),
            ("imbrication profonde", b"[" * 200000, "RecursionError"),
        )
        for nom, octets, cause in formes:
            with self.subTest(forme=nom):
                chemin = run_export.journal_attente(run_export.nouvel_ulid(), depuis=self.racine)
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_bytes(octets)
                try:
                    err = io.StringIO()
                    with redirect_stderr(err):
                        store._rejouer_journaux_attente()   # ne LÈVE plus
                    sortie = err.getvalue()
                    self.assertEqual(1, sortie.count(str(chemin)), sortie)
                    self.assertIn("ILLISIBLE", sortie)
                    self.assertIn(cause, sortie)
                    self.assertTrue(chemin.is_file(), "CONSERVÉ, jamais effacé en silence")
                finally:
                    chemin.unlink(missing_ok=True)

    def test_un_rejeu_du_journal_d_attente_ne_duplique_pas_par_ULID(self) -> None:
        # Témoin 4 : rejouer DEUX fois le MÊME journal ne duplique ni la base
        # (contrainte ULID) ni l'export (relecture du .jsonl). MUTATION : ne
        # dédupliquer que côté base sans contrôler l'ULID à l'ajout du texte.
        db = self._db()
        store = self._store()
        ligne = {
            "ulid": run_export.nouvel_ulid(),
            "predecesseur_ulid": None,
            "task_id": "T-4",
            "agent_role": "run",
            "event_type": "TASK_CREATED",
            "event_kind": "TASK_CREATED",
            "attempt": 0,
            "operation_id": "op4",
            "payload_json": "{}",
            "created_at": "2026-06-01 00:00:00",
        }
        run_export.ecrire_journal_attente(ligne, depuis=self.racine)
        store._rejouer_journaux_attente()
        run_export.ecrire_journal_attente(ligne, depuis=self.racine)  # re-sème le MÊME journal
        store._rejouer_journaux_attente()
        self.assertEqual(self._compter(db), 1, "la base ne duplique pas (ULID unique)")
        self.assertEqual(self._lignes_export(), 1, "l'export ne duplique pas par ULID")

    def test_F6_un_effacement_refuse_apres_export_ne_propage_pas(self) -> None:
        # F6 (binôme, C4) : dans `_flush_export`, l'effacement du journal est DANS le
        # `try`. `effacer_journal_attente` n'absorbe que FileNotFoundError ; une partition
        # en lecture seule ou un journal tenu par un rejeu concurrent (PermissionError,
        # OSError) ne doit PAS PROPAGER — l'export a RÉUSSI, seul l'effacement échoue, et
        # le rejeu retraitera le journal (idempotent par ULID). MUTATION (effacement HORS
        # du try) : la PermissionError propage -> `append_event` LÈVE -> l'appel nu
        # ci-dessous rougit (au lieu de rendre l'event_id).
        db = self._db()
        store = self._store()
        err = io.StringIO()
        with mock.patch.object(
            run_export, "effacer_journal_attente",
            side_effect=PermissionError("partition en lecture seule"),
        ):
            with redirect_stderr(err):
                event_id = store.append_event(
                    "T-F6", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="opf6"
                )
        self.assertIsInstance(event_id, int, "append_event rend l'event_id, ne LÈVE pas")
        self.assertEqual(self._compter(db), 1, "l'événement est commité en base")
        self.assertEqual(self._lignes_export(), 1, "l'export a RÉUSSI (une ligne)")
        # B1 (binôme, 3e tour) : `assertIn("journaux conserves")` était présent dans
        # LES DEUX branches du `cause = (… if exporte else …)`, donc il ne
        # distinguait RIEN — le correctif G3 était décoratif, et réintroduire
        # « echec export » après un export RÉUSSI laissait la porte VERTE.
        # Mesuré : `git grep "export REUSSI" -- '*.py'` rendait DEUX hits, tous
        # deux dans `event_store.py`, ZÉRO dans les bancs.
        sortie = err.getvalue()
        self.assertIn(
            "export REUSSI, effacement du journal refuse", sortie,
            "G3 : la cause annoncée est l'EFFACEMENT, pas l'export",
        )
        self.assertNotIn(
            "(echec export", sortie,
            "G3 : un export RÉUSSI ne s'annonce JAMAIS « echec export »",
        )

    def test_F8_l_echec_d_export_au_rejeu_annonce_l_arriere(self) -> None:
        # F8 (binôme) : la branche `except Exception` de `_rejouer_journaux_attente`
        # (échec d'AJOUT à l'export APRÈS l'écriture en base) doit annoncer l'ARRIÉRÉ
        # TOTAL, comme les DEUX sites de `_flush_export` — deux surfaces qui voyagent
        # ensemble doivent dire la même chose. MUTATION (retirer le compte `restant` de
        # cette branche) : le message ne porte plus le nombre de journaux conservés et le
        # `re.search` du compte rougit.
        db = self._db()
        store = self._store()  # aucun journal en attente à la construction
        ligne = {
            "ulid": run_export.nouvel_ulid(), "predecesseur_ulid": None,
            "task_id": "T-F8", "agent_role": "run", "event_type": "TASK_CREATED",
            "event_kind": "TASK_CREATED", "attempt": 0, "operation_id": "opf8",
            "payload_json": "{}", "created_at": "2026-06-01 00:00:00",
        }
        run_export.ecrire_journal_attente(ligne, depuis=self.racine)
        err = io.StringIO()
        with mock.patch.object(
            run_export, "ajouter_a_l_export",
            side_effect=RuntimeError("panne d'export au rejeu"),
        ):
            with redirect_stderr(err):
                store._rejouer_journaux_attente()  # base OK, ajout export en échec
        sortie = err.getvalue()
        self.assertEqual(self._compter(db), 1, "l'INSERT a réussi (base porte l'événement)")
        m = re.search(r"echec export, (\d+) journaux conserves", sortie)
        self.assertIsNotNone(m, "F8 : le compte de l'arriéré doit figurer dans le message")
        self.assertGreaterEqual(
            int(m.group(1)), 1, "au moins le journal en échec est compté dans l'arriéré"
        )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=self.racine),
            "le journal est CONSERVÉ après un échec d'export (rejeu ultérieur)",
        )


class TestSecretEtEcrivainUnique(_IntegrationFixture):
    def test_aucun_secret_ne_part_dans_le_TEXTE_VERSIONNE(self) -> None:
        # Témoin 8 : le secret est rédigé AVANT l'export versionné (irréversible
        # une fois dans git). MUTATION : rédiger avant le json.dumps sans rédiger
        # la ligne d'export.
        store = self._store()
        store.append_event(
            "T-8", "dev", "CODE_GENERATED", {"code_diff": FAUX_AWS}, operation_id="op8"
        )
        texte = self._texte_export()
        self.assertNotIn(FAUX_AWS, texte, "un secret brut est parti dans le texte VERSIONNÉ")
        self.assertIn("[SECRET", texte, "le marqueur de rédaction est absent")

    def test_un_seul_site_insere_dans_events_ledger(self) -> None:
        # Témoin 18 : filet à portée FICHIER. MUTATION : réintroduire un INSERT
        # brut dans un des cinq sites -> le compte passe à 2.
        import agentic_v3.db.event_store as es

        source = inspect.getsource(es)
        self.assertEqual(
            source.count("INSERT INTO events_ledger"), 1,
            "un écrivain brut a été réintroduit dans event_store.py",
        )


class TestNonFuite(_IntegrationFixture):
    def _liste_partitions_reelles(self) -> set:
        """MAJEUR 8 (binôme) : la LISTE des partitions sous la VRAIE
        `state_home()/projets` — STABLE pendant une session, une neuve signale une
        vraie fuite. Remplace le relevé de l'ARBRE ENTIER de `state_home()`, mesuré
        FLOTTANT : cette tâche a augmenté l'écriture continue (un journal d'attente
        naît et meurt à chaque appel de l'outil de board), donc un before/after
        ensembliste rougissait sans qu'aucune fuite n'existe."""
        env = {k: v for k, v in os.environ.items()}
        env.pop("CADRE_STATE_DIR", None)
        env.pop("XDG_STATE_HOME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            projets = run_export._paths().state_home() / "projets"
            return {p.name for p in projets.iterdir()} if projets.is_dir() else set()

    def test_append_event_n_ecrit_rien_hors_de_la_racine_de_test(self) -> None:
        # Témoin 17 : append_event sous racine de TEST n'écrit RIEN hors de la racine
        # de test — ni sous une partition machine AUTRE que celle du banc, ni sous le
        # runs/ RÉEL du dépôt. MAJEUR 8 : on relève la LISTE des partitions (stable)
        # et une SONDE CIBLÉE sur le dossier d'exports RÉEL, plus l'arbre entier qui
        # FLOTTE. Détection conservée, fausse alerte latente éliminée.
        # adopting-tree: temoin de non-fuite — il DOIT nommer le runs/ reel du depot, sinon il ne teste plus rien
        runs_reel = ROOT / "runs"
        auteur = run_export.auteur_courant(depuis=self.racine)
        copie = run_export.identifiant_de_copie(depuis=self.racine)
        sonde_reelle = runs_reel / auteur / copie  # là où un export FUITÉ atterrirait
        avant_sonde = set(sonde_reelle.rglob("*")) if sonde_reelle.exists() else set()
        avant_partitions = self._liste_partitions_reelles()

        store = self._store()
        store.append_event("T-FUITE", "dev", "TASK_CREATED", {"req_id": "R"}, operation_id="opf")

        # (1) La LISTE des partitions machine n'a pas gagné d'entrée -> aucune fuite
        #     sous une partition AUTRE que celle du banc.
        self.assertEqual(
            avant_partitions, self._liste_partitions_reelles(),
            "une partition machine neuve est apparue — fuite hors de la racine de test",
        )
        # (2) Sonde ciblée : aucun export du banc n'apparaît sous le runs/ RÉEL.
        apres_sonde = set(sonde_reelle.rglob("*")) if sonde_reelle.exists() else set()
        self.assertEqual(
            avant_sonde, apres_sonde,
            "un export du banc est apparu sous le runs/ RÉEL du dépôt",
        )
        # Preuve positive : l'export EST bien sous la racine de test.
        self.assertEqual(self._lignes_export(), 1)


class TestIdentifiantHostileNeComposeAucunChemin(_IntegrationFixture):
    """CONSTAT 1 (revue sécurité) : `journal_attente` fabrique un composant de chemin
    depuis l'`ulid`. Un composant ABSOLU ou porteur de `..` écraserait le préfixe —
    `Path('/base/run/attente') / '/etc/x'` rend `/etc/x` — et livrerait une écriture
    (`ecrire_journal_attente`) ou une suppression (`effacer_journal_attente`) HORS de
    la partition d'attente. Ce n'est PAS le seul tel site (MAJEUR 5 du binôme) :
    `chemin_export` compose depuis `<copie>` et est couvert par
    `TestCopieHostileNeComposePasDeChemin`."""

    def test_un_ulid_hors_forme_est_refuse_avant_de_composer_un_chemin(self) -> None:
        # MUTATION : retirer `_valider_ulid` de `journal_attente` -> le chemin
        # absolu compose et l'assertRaises tombe (aucune levée).
        sonde = Path(self._tmp.name) / "SONDE_HORS_PARTITION"
        cible_absolue = str(sonde)  # composant absolu -> écrase le préfixe
        cible_dotdot = "../" * 8 + sonde.name  # remonte hors partition
        for hostile in (cible_absolue, cible_dotdot, "/etc/cron.d/evil", "a" * 25, "a" * 27):
            with self.assertRaises(RunExportError):
                run_export.journal_attente(hostile, depuis=self.racine)
            with self.assertRaises(RunExportError):
                run_export.ecrire_journal_attente(
                    {"ulid": hostile, "task_id": "T"}, depuis=self.racine
                )
        # Rien n'a été écrit hors de la partition, sous aucune des deux graphies.
        self.assertFalse(sonde.with_suffix(".json").exists())
        self.assertFalse((sonde.parent / (sonde.name + ".json")).exists())

    def test_une_ligne_hostile_d_un_export_est_sautee_sans_ecrire_ni_effacer(self) -> None:
        # CONSTAT 1, chemin de reconstruction : un `.jsonl` d'export est VERSIONNÉ
        # et FUSIONNABLE entre contributeurs. Une ligne dont l'`ulid` est un chemin
        # absolu doit être SAUTÉE (comptée), jamais suivie jusqu'à
        # _ecrire_evenement (écriture arbitraire du journal) ni effacer_journal_attente
        # (suppression arbitraire). MUTATION : retirer le filtre de forme dans
        # reconstruire_depuis_exports -> l'ulid hostile atteint l'écrivain.
        store = self._store()
        sonde = Path(self._tmp.name) / "SONDE_RECONSTRUCTION"
        valide = run_export.nouvel_ulid()
        dossier = self.racine / "runs" / "auteurX" / "copieX"
        dossier.mkdir(parents=True)
        lignes = [
            json.dumps({"ulid": str(sonde), "task_id": "T-H", "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}",
                        "operation_id": "opH", "event_kind": "TASK_CREATED",
                        "attempt": 0, "predecesseur_ulid": None,
                        "created_at": "2026-06-01 00:00:00"}),
            json.dumps({"ulid": valide, "task_id": "T-OK", "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}",
                        "operation_id": "opOK", "event_kind": "TASK_CREATED",
                        "attempt": 0, "predecesseur_ulid": None,
                        "created_at": "2026-06-01 00:00:00"}),
        ]
        (dossier / "2026-06.jsonl").write_text("\n".join(lignes) + "\n", encoding="utf-8")

        res = store.reconstruire_depuis_exports()

        # La ligne hostile est comptée comme ignorée, la valide appliquée.
        self.assertEqual(res["applied"], 1, "seule la ligne valide doit s'appliquer")
        self.assertGreaterEqual(res.get("ignores", 0), 1, "la ligne hostile doit être comptée")
        # Aucun octet écrit ni effacé hors de la partition à cause de l'ulid hostile.
        self.assertFalse(sonde.with_suffix(".json").exists())
        self.assertFalse((sonde.parent / (sonde.name + ".json")).exists())
        self.assertEqual(self._compter(self._db()), 1, "seule la ligne valide est en base")


class TestReconstructionNeCorrompsPasLAttribution(_IntegrationFixture):
    """BLOQUANT 1 & 2 (binôme de clôture) — la reconstruction lit l'export d'un
    AUTRE contributeur (B) sans corrompre l'attribution et sans qu'une seule ligne
    hostile nie tout l'historique."""

    def _ecrire_export_B(self, ulid: str, **champs) -> None:
        dossier = self.racine / "runs" / "auteurB" / "copieB"
        dossier.mkdir(parents=True, exist_ok=True)
        ligne = {
            "ulid": ulid, "task_id": "T-B", "agent_role": "run",
            "event_type": "TASK_CREATED", "payload_json": "{}",
            "operation_id": "opB", "event_kind": "TASK_CREATED",
            "attempt": 0, "predecesseur_ulid": None,
            "created_at": "2026-06-01 00:00:00",
        }
        ligne.update(champs)
        (dossier / f"{run_export._mois_de_ulid(ulid)}.jsonl").write_text(
            json.dumps(ligne) + "\n", encoding="utf-8")

    def test_la_reconstruction_n_ecrit_AUCUN_journal_d_attente(self) -> None:
        # BLOQUANT 1(a) : la reconstruction LIT depuis l'export, elle n'a rien à
        # exporter -> AUCUN journal ne doit naître. Un journal résiduel ressusciterait
        # l'événement de B sous l'auteur COURANT (A) au redémarrage. MUTATION :
        # retirer `journaliser=False`.
        store = self._store()
        self._ecrire_export_B(run_export.nouvel_ulid())
        with mock.patch.object(
            run_export, "ecrire_journal_attente",
            wraps=run_export.ecrire_journal_attente,
        ) as spy:
            store.reconstruire_depuis_exports()
        self.assertEqual(
            spy.call_count, 0,
            "la reconstruction a écrit un journal d'attente (résurrection possible)",
        )

    def test_un_echec_base_n_est_ni_muet_ni_fatal_et_ne_laisse_pas_de_journal(self) -> None:
        # BLOQUANT 1(b) + BLOQUANT 2 : un échec EN BASE (verrou occupé) — AVANT :
        # l'exception propage (DoS de l'historique) et le journal écrit à :174 SURVIT
        # (effacement hors branche d'erreur). APRÈS : ni fatal, annoncé, et un journal
        # PRÉEXISTANT effacé par le filet N.
        # RÉ-EXPRIMÉ par S-00002561 (3), passe 3 de T-00000691 : une `OperationalError`
        # est une panne SYSTÈME — elle n'est plus « comptée à part » ligne à ligne
        # (ce comptage laissait commiter une base PARTIELLE, jamais plus reconstruite,
        # S-00002560) : elle AVORTE le lot, cause annoncée. Les trois propriétés que
        # ce témoin défend TIENNENT : aucune levée, annonce, aucun journal survivant.
        # Le comptage par ligne d'une erreur de DONNÉE est tenu par T48c.
        store = self._store()
        ulid = run_export.nouvel_ulid()
        self._ecrire_export_B(ulid)
        run_export.ecrire_journal_attente(
            {"ulid": ulid, "task_id": "T-vieux"}, depuis=self.racine
        )
        self.assertTrue(run_export.lister_journaux_attente(depuis=self.racine))
        err = io.StringIO()
        with mock.patch.object(
            type(store), "_apply_projection",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            with redirect_stderr(err):
                res = store.reconstruire_depuis_exports()  # ne DOIT PAS lever
        self.assertEqual(res["avortee"], 1, "une panne SYSTÈME avorte le lot")
        self.assertIn("reconstruction AVORTEE, rien ecrit (OperationalError: database is locked)",
                      err.getvalue(), "l'échec en base doit être ANNONCÉ, avec SA cause")
        self.assertFalse(
            run_export.lister_journaux_attente(depuis=self.racine),
            "un journal a survécu à l'échec (résurrection possible au redémarrage)",
        )

    def test_une_ligne_bien_formee_mais_absurde_ne_bloque_pas_l_historique(self) -> None:
        # BLOQUANT 2 : deux lignes, la première (ulid VALIDE en forme, task_id ABSENT)
        # trie EN TÊTE. AVANT : zéro ligne appliquée sur deux (KeyError propagé, DoS).
        # APRÈS : la ligne hors forme est comptée et sautée, la valide s'applique.
        store = self._store()
        dossier = self.racine / "runs" / "auteurB" / "copieB"
        dossier.mkdir(parents=True)
        absurde = "0" * 26  # forme ULID valide, trie en tête ; task_id ABSENT
        valide = run_export.nouvel_ulid()
        lignes = [
            json.dumps({"ulid": absurde, "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}"}),
            json.dumps({"ulid": valide, "task_id": "T-OK", "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}", "attempt": 0}),
        ]
        (dossier / f"{run_export._mois_de_ulid(valide)}.jsonl").write_text(
            "\n".join(lignes) + "\n", encoding="utf-8"
        )
        res = store.reconstruire_depuis_exports()  # ne DOIT PAS lever
        self.assertEqual(res["applied"], 1, "la valide doit s'appliquer malgré l'absurde")
        self.assertEqual(res["malformes"], 1, "la ligne hors forme doit être comptée")
        self.assertEqual(self._compter(self._db()), 1)

    def test_la_reconstruction_annonce_son_decompte_quand_elle_ecarte(self) -> None:
        # MAJEUR 6 : le décompte n'avait aucune surface où être lu (valeur de retour,
        # seul appelant = banc). On l'ANNONCE sur stderr quand il y a des écarts, pour
        # qu'une reconstruction qui écarte soit discernable d'une propre. MUTATION :
        # retirer l'annonce finale.
        store = self._store()
        dossier = self.racine / "runs" / "auteurB" / "copieB"
        dossier.mkdir(parents=True)
        hostile = "/tmp/HOSTILE_ULID"  # ulid présent mais HORS FORME -> ignoré, pas de crash
        valide = run_export.nouvel_ulid()
        lignes = [
            json.dumps({"ulid": hostile, "task_id": "T-H", "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}"}),
            json.dumps({"ulid": valide, "task_id": "T-OK", "agent_role": "run",
                        "event_type": "TASK_CREATED", "payload_json": "{}", "attempt": 0}),
        ]
        (dossier / "2026-06.jsonl").write_text("\n".join(lignes) + "\n", encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err):
            res = store.reconstruire_depuis_exports()
        self.assertEqual(res["ignores"], 1)
        self.assertEqual(res["applied"], 1)
        self.assertIn(
            "reconstruction terminee", err.getvalue(),
            "une reconstruction qui écarte des lignes doit l'ANNONCER",
        )


class TestRejeuJournauxResoutAuteurUneFois(_IntegrationFixture):
    """MAJEUR 4 (binôme) — le rejeu des journaux d'attente résout l'auteur UNE fois
    et n'avale plus un échec d'export en silence."""

    def _creer_deux_journaux(self) -> None:
        store = self._store()
        with mock.patch.object(
            run_export, "ajouter_a_l_export", side_effect=RuntimeError("arrêt export")
        ):
            for i in range(2):
                with self.assertRaises(RuntimeError):
                    store.append_event(
                        f"T-{i}", "run", "TASK_CREATED", {"req_id": str(i)},
                        operation_id=f"op{i}",
                    )
        self.assertEqual(
            len(run_export.lister_journaux_attente(depuis=self.racine)), 2,
            "deux journaux doivent survivre à l'arrêt d'export",
        )

    def test_l_auteur_est_resolu_UNE_seule_fois_pour_N_journaux(self) -> None:
        # MAJEUR 4 : `git config user.email` partait par journal (mesuré 4,41 s pour
        # 300). Résolu UNE fois avant la boucle, passé à chaque ajout. MUTATION :
        # re-dériver l'auteur dans la boucle.
        self._creer_deux_journaux()
        with mock.patch.object(
            run_export, "_email_git", return_value="banc@test"
        ) as spy:
            self._store()  # reconstruit -> _rejouer_journaux_attente
        self.assertEqual(
            spy.call_count, 1,
            f"auteur résolu {spy.call_count} fois pour 2 journaux (1 attendu)",
        )
        self.assertFalse(
            run_export.lister_journaux_attente(depuis=self.racine),
            "les deux journaux devraient être rejoués puis effacés",
        )

    def test_auteur_absent_conserve_les_journaux_et_l_annonce(self) -> None:
        # MAJEUR 4 : auteur indisponible -> ANNONCER le nombre de journaux conservés
        # et SORTIR, au lieu de boucler et d'avaler le refus en SILENCE (ancien
        # `except Exception: continue`). MUTATION : retirer l'annonce.
        self._creer_deux_journaux()
        err = io.StringIO()
        with mock.patch.object(run_export, "_email_git", return_value=""):
            with redirect_stderr(err):
                self._store()
        sortie = err.getvalue()
        self.assertIn("2 journaux", sortie, "le nombre de journaux conservés doit être annoncé")
        self.assertIn("conserves", sortie)
        self.assertEqual(
            len(run_export.lister_journaux_attente(depuis=self.racine)), 2,
            "les journaux doivent être CONSERVÉS quand l'auteur manque",
        )


class TestCopieHostileNeComposePasDeChemin(_IntegrationFixture):
    """MAJEUR 5 (binôme) — `<copie>` est un SECOND identifiant qui compose un
    composant de chemin (lu sur disque ou passé par mot-clé public). Une valeur
    hostile écrivait HORS du dossier d'exports et HORS du dépôt."""

    def test_une_copie_hostile_est_refusee_avant_de_composer_un_chemin(self) -> None:
        # MUTATION : retirer `_valider_copie` de `chemin_export`.
        cible_hors = self.racine.parent / "EVIL_COPIE"
        for hostile in ("../" * 6 + "EVIL_COPIE", "/tmp/EVIL_COPIE", "a/b", "..", ""):
            with self.assertRaises(RunExportError):
                run_export.chemin_export(_ULID, depuis=self.racine, copie=hostile)
            with self.assertRaises(RunExportError):
                run_export.ajouter_a_l_export(
                    {"ulid": _ULID, "task_id": "T"}, depuis=self.racine, copie=hostile
                )
        self.assertFalse(cible_hors.exists(), "une écriture a fui hors du dossier d'exports")

    def test_une_copie_hostile_LUE_SUR_DISQUE_est_refusee(self) -> None:
        # La copie lue depuis `state_project()/run/copie` (voie normale) est aussi
        # contrôlée — seule la valeur réservée `backfill` l'était jusqu'ici.
        fichier = run_export._fichier_copie(depuis=self.racine)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text("../" * 6 + "EVIL_DISQUE\n", encoding="utf-8")
        with self.assertRaises(RunExportError):
            run_export.chemin_export(_ULID, depuis=self.racine)


class TestReExportReparePerteDeDonnees(_PartitionFixture):
    """CORRECTIF 1 — T1 (S-00001809), la PERTE DE DONNÉES la plus grave. L'UPDATE des
    ULID est commité AVANT la boucle d'export, sans journal d'attente : une
    interruption laisse des lignes FRAPPÉES hors du texte, qu'un rejeu NOMINAL ne
    retrouve JAMAIS. `re_exporter_frappees` (CLI `backfill --re-exporter`) répare."""

    _CHAMPS = (
        "task_id", "agent_role", "event_type", "payload_json", "created_at",
        "operation_id", "event_kind", "attempt", "predecesseur_ulid",
    )

    def _fabriquer_4_un_mois(self):
        """4 lignes `ulid IS NULL`, TOUTES en août (un seul fichier de mois, comme le
        constat : 3 lignes dont 1 borne == 2 événements après interruption au 3e)."""
        db = self._db()
        create_tables(db)
        conn = sqlite3.connect(str(db))
        for i, (task, created_at) in enumerate([
            ("T-A", "2026-08-01 00:00:00"),
            ("T-A", "2026-08-01 00:00:01"),
            ("T-B", "2026-08-01 00:00:02"),
            ("T-B", "2026-08-01 00:00:03"),
        ], start=1):
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
                (task, "BoardBridge", "BOARD_TASK_OBSERVED", "{}", created_at,
                 f"op{i}", "BOARD_TASK_OBSERVED", 0),
            )
        conn.commit()
        conn.close()
        return db

    def _compter_null(self, db) -> int:
        conn = sqlite3.connect(str(db))
        try:
            return int(conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL").fetchone()[0])
        finally:
            conn.close()

    def _evenements_texte(self) -> int:
        """Compte les lignes PORTEUSES d'ulid (la borne, une clé `borne`, est exclue)."""
        n = 0
        if not self._runs().exists():
            return 0
        for fichier in sorted(self._runs().rglob("*.jsonl")):
            for brute in fichier.read_text(encoding="utf-8").splitlines():
                brute = brute.strip()
                if brute and "ulid" in json.loads(brute):
                    n += 1
        return n

    def _texte_par_ulid(self) -> dict:
        out = {}
        if not self._runs().exists():
            return out
        for fichier in sorted(self._runs().rglob("*.jsonl")):
            for brute in fichier.read_text(encoding="utf-8").splitlines():
                brute = brute.strip()
                if not brute:
                    continue
                obj = json.loads(brute)
                if "ulid" not in obj:
                    continue
                out[obj["ulid"]] = {c: obj.get(c) for c in self._CHAMPS}
        return out

    def _base_par_ulid(self, db) -> dict:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            return {
                r["ulid"]: {c: r[c] for c in self._CHAMPS}
                for r in conn.execute(
                    "SELECT * FROM events_ledger WHERE ulid IS NOT NULL")
            }
        finally:
            conn.close()

    def test_une_interruption_perd_des_lignes_et_re_exporter_les_recupere(self):
        # Interruption AU 3e export : ajouter_a_l_export lève à sa 3e invocation (les
        # 2 premières appellent la VRAIE). MUTATION (fix retiré) : supprimer
        # re_exporter_frappees -> (d) re_exportees != 2 et le texte reste à 2.
        db = self._fabriquer_4_un_mois()
        reel = run_export.ajouter_a_l_export
        compteur = {"n": 0}

        def _interrompt(*a, **k):
            compteur["n"] += 1
            if compteur["n"] == 3:
                raise RuntimeError("interruption au 3e export")
            return reel(*a, **k)

        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            with mock.patch.object(
                run_export, "ajouter_a_l_export", side_effect=_interrompt
            ):
                with self.assertRaises(RuntimeError):
                    run_export.backfill_historique(base=db, depuis=self.racine)

            # (a) l'UPDATE est commité AVANT la boucle -> AUCUNE ligne NULL en base.
            self.assertEqual(self._compter_null(db), 0, "UPDATE commité avant l'export")
            # (b) 2 événements sur 4 seulement dans le texte.
            self.assertEqual(self._evenements_texte(), 2, "2 événements sur 4 dans le texte")

            # (c) LE DÉFAUT, ÉPINGLÉ : le rejeu NOMINAL rend frappees 0 et n'ajoute RIEN.
            res_rejeu = run_export.backfill_historique(base=db, depuis=self.racine)
            self.assertEqual(res_rejeu["frappees"], 0, "rejeu nominal : rien à frapper")
            self.assertEqual(self._evenements_texte(), 2, "rejeu nominal : AUCUN signal")

            # (d) --re-exporter récupère les 2 manquantes ; le texte porte alors les 4.
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
            self.assertEqual(res["mode"], "re-exporter")
            self.assertEqual(res["candidates"], 4)
            self.assertEqual(res["manquantes"], 2)
            self.assertEqual(res["re_exportees"], 2, "les 2 lignes hors texte re-exportées")
            self.assertEqual(self._evenements_texte(), 4, "le texte porte désormais les 4")

            # PIÈGE DE MÉTHODE : égalité PAR CONTENU (9 champs par ULID), JAMAIS par
            # sha256 (ajouter_a_l_export dédoublonne par ULID avant comparaison).
            self.assertEqual(
                self._texte_par_ulid(), self._base_par_ulid(db),
                "chaque ULID du texte porte les 9 champs de sa ligne en base",
            )

            # (e) IDEMPOTENCE : un second --re-exporter rend 0 et ne change RIEN.
            avant = self._texte_par_ulid()
            res2 = run_export.re_exporter_frappees(base=db, depuis=self.racine)
            self.assertEqual(res2["re_exportees"], 0, "second re-export : idempotent")
            self.assertEqual(self._texte_par_ulid(), avant, "contenu inchangé (par contenu)")

    def test_re_export_balaye_TOUTES_les_copies_pas_la_seule_backfill(self):
        # Une ligne DÉJÀ exportée sous la copie VIVANTE ne doit JAMAIS être réécrite
        # sous backfill (doublon irréparable en AJOUT SEUL). MUTATION : borner le scan
        # de _ulids_deja_dans_le_texte à `runs/<auteur>/backfill/*.jsonl` -> la ligne
        # vivante est jugée manquante et re-exportée -> re_exportees == 1, doublon.
        db = self._db()
        create_tables(db)
        ulid = run_export.nouvel_ulid(
            run_export._ms_de_created_at("2026-08-01 00:00:00")
        )
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt,ulid,predecesseur_ulid) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("T-V", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "opv",
             "TASK_CREATED", 0, ulid, None),
        )
        conn.commit()
        conn.close()
        ligne = {
            "ulid": ulid, "task_id": "T-V", "agent_role": "run",
            "event_type": "TASK_CREATED", "payload_json": "{}",
            "created_at": "2026-08-01 00:00:00", "operation_id": "opv",
            "event_kind": "TASK_CREATED", "attempt": 0, "predecesseur_ulid": None,
        }
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            # la MÊME ligne est DÉJÀ exportée sous la copie VIVANTE (pas backfill).
            run_export.ajouter_a_l_export(dict(ligne), depuis=self.racine, copie="vivante")
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertEqual(
            res["re_exportees"], 0,
            "une ligne déjà sous la copie vivante ne doit PAS être re-exportée",
        )
        self.assertEqual(
            sorted(self._runs().rglob("backfill/*.jsonl")), [],
            "aucun fichier backfill ne doit naître pour une ligne déjà exportée",
        )

    def test_re_export_tolere_un_octet_invalide_sous_une_copie_VIVANTE(self):
        # PÉRIMÈTRE (A1, binôme) : ce témoin n'exerce QUE le chemin
        # `_ulids_deja_dans_le_texte` — l'octet est sous une copie VIVANTE, et le fichier
        # backfill n'existe pas encore (`_ecrire_borne_en_tete` prend `not exists` et
        # `_ulid_deja_exporte` rend False sans rien lire). Le chemin backfill-lu-en-tête
        # est couvert par `test_..._dans_le_fichier_BACKFILL_lu_en_tete`. Ici : un octet
        # INVALIDE (fusion merge=union) ne doit PAS avorter la réparation. MUTATION (fix
        # retiré : open sans errors=) -> UnicodeDecodeError remonte, l'appel lève.
        db = self._db()
        create_tables(db)
        ulid = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt,ulid,predecesseur_ulid) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("T-U", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "opu",
             "TASK_CREATED", 0, ulid, None),
        )
        conn.commit()
        conn.close()
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            auteur = run_export.auteur_courant(depuis=self.racine)
            # Un fichier d'export porteur d'un OCTET INVALIDE (hors UTF-8).
            pollue = self.racine / "runs" / auteur / "vivante" / "2026-08.jsonl"
            pollue.parent.mkdir(parents=True)
            pollue.write_bytes(b'{"ulid": "ZZZ"}\n\xff\xfe octet invalide\n')
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        # La réparation ABOUTIT malgré l'octet invalide : la ligne frappée absente du
        # texte est re-exportée (au lieu d'un avortement avant tout export).
        self.assertEqual(res["mode"], "re-exporter")
        self.assertEqual(res["candidates"], 1)
        self.assertEqual(
            res["re_exportees"], 1,
            "la réparation doit ABOUTIR malgré l'octet invalide (errors=replace)",
        )

    def _inserer_frappee(self, db, ulid, *, task_id="T-A", op="opa"):
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt,ulid,predecesseur_ulid) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (task_id, "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", op,
             "TASK_CREATED", 0, ulid, None),
        )
        conn.commit()
        conn.close()

    def test_re_export_tolere_un_octet_invalide_dans_le_fichier_BACKFILL_lu_en_tete(self):
        # A1 (les DEUX critiques) — la tolérance d'encodage doit être sur le CHEMIN, pas
        # au seul site que le témoin regardait. Ici l'octet invalide est dans le fichier
        # `backfill/<mois>.jsonl` DÉJÀ POURVU DE SA BORNE, que `_ecrire_borne_en_tete`
        # (lecture EN TÊTE) ET `_ulid_deja_exporte` relisent pendant le ré-export.
        # MUTATION (fix retiré) : `_ecrire_borne_en_tete` lit en UTF-8 STRICT ->
        # UnicodeDecodeError NON attrapée -> re_exporter_frappees AVORTE avant tout
        # export -> l'appel lève (rc 1 hors énumération). Corrigé (lecture binaire /
        # errors=replace) -> la réparation ABOUTIT, re_exportees == 1.
        db = self._db()
        create_tables(db)
        ulid = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        self._inserer_frappee(db, ulid, task_id="T-B", op="opb")
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            auteur = run_export.auteur_courant(depuis=self.racine)
            # Le fichier backfill EXISTE, porte SA borne EN TÊTE, PUIS un octet invalide.
            f = self.racine / "runs" / auteur / "backfill" / "2026-08.jsonl"
            f.parent.mkdir(parents=True)
            borne = json.dumps(
                {"borne": run_export.BORNE_BACKFILL}, sort_keys=True, ensure_ascii=False
            )
            f.write_bytes(borne.encode("utf-8") + b"\n\xff\xfe octet invalide\n")
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertEqual(res["mode"], "re-exporter")
        self.assertEqual(res["candidates"], 1)
        self.assertEqual(
            res["re_exportees"], 1,
            "la réparation doit ABOUTIR malgré l'octet dans le fichier backfill lu en tête",
        )
        lignes = [
            l for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()
        ]
        self.assertEqual(sum(1 for l in lignes if '"borne"' in l), 1, "borne non doublée")

    def test_re_export_deduplique_ENTRE_auteurs_pas_le_seul_courant(self):
        # A2 (les DEUX critiques) — le magasin voyage par git ENTRE auteurs
        # (events_ledger n'a PAS de colonne auteur, schema.py). Une ligne exportée sous
        # un AUTRE auteur est DÉJÀ dans le texte partagé -> jamais re-exportée (doublon
        # irréparable en ajout seul), COMPTÉE `sous_autre_auteur`. MUTATION (fix retiré :
        # scan borné à runs/<auteur courant>/*/*.jsonl) -> la ligne de l'autre auteur est
        # jugée manquante et RE-EXPORTÉE -> re_exportees == 1 (doublon), l'== 0 rougit.
        db = self._db()
        create_tables(db)
        u_autre = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        u_courant = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-02 00:00:00"))
        self._inserer_frappee(db, u_autre, task_id="T-A", op="opa")
        self._inserer_frappee(db, u_courant, task_id="T-B", op="opb")
        ligne_autre = {
            "ulid": u_autre, "task_id": "T-A", "agent_role": "run",
            "event_type": "TASK_CREATED", "payload_json": "{}",
            "created_at": "2026-08-01 00:00:00", "operation_id": "opa",
            "event_kind": "TASK_CREATED", "attempt": 0, "predecesseur_ulid": None,
        }
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            courant = run_export.auteur_courant(depuis=self.racine)
            autre = "0" * 16  # empreinte d'un contributeur DISTINCT du courant
            self.assertNotEqual(autre, courant)
            f_autre = self.racine / "runs" / autre / "vivante" / "2026-08.jsonl"
            f_autre.parent.mkdir(parents=True)
            f_autre.write_text(
                json.dumps(ligne_autre, sort_keys=True) + "\n", encoding="utf-8"
            )
            # L'auteur COURANT a DÉJÀ exporté SA propre ligne (donc pas de refus A2).
            ligne_courant = dict(ligne_autre, ulid=u_courant, task_id="T-B", operation_id="opb")
            run_export.ajouter_a_l_export(ligne_courant, depuis=self.racine, copie="vivante")
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertEqual(
            res["re_exportees"], 0,
            "une ligne sous un AUTRE auteur ne doit PAS être re-exportée (doublon)",
        )
        self.assertEqual(res["sous_autre_auteur"], 1, "la ligne de l'autre auteur est comptée")
        self.assertEqual(
            sorted(self._runs().rglob("backfill/*.jsonl")), [],
            "aucun fichier backfill ne doit naître pour une ligne déjà sous un autre auteur",
        )

    def test_re_export_refuse_de_forger_un_auteur_neuf(self):
        # A2 (refus de fable) — des lignes frappées en base mais AUCUN export sous
        # l'auteur courant => une réparation ne crée JAMAIS un auteur (user.email a
        # probablement changé). REFUS nommé, plutôt que de forger un dossier d'auteur
        # neuf. MUTATION (fix retiré : aucun refus) -> re_exporter tourne et EXPORTE sous
        # un auteur neuf -> assertRaises tombe (aucune levée).
        db = self._db()
        create_tables(db)
        u = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        self._inserer_frappee(db, u, task_id="T-A", op="opa")
        # La ligne existe SOUS UN AUTRE auteur ; l'auteur courant n'a RIEN exporté.
        autre = "ffffffffffffffff"
        f_autre = self.racine / "runs" / autre / "vivante" / "2026-08.jsonl"
        f_autre.parent.mkdir(parents=True)
        f_autre.write_text(json.dumps({"ulid": u, "task_id": "T-A"}) + "\n", encoding="utf-8")
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            with self.assertRaises(RunExportError) as ctx:
                run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertIn("user.email", str(ctx.exception))
        self.assertIn("auteur courant", str(ctx.exception))
        self.assertEqual(
            sorted(self._runs().rglob("backfill/*.jsonl")), [], "aucun export forgé sous un auteur neuf"
        )

    def test_une_ligne_presente_mais_DIVERGENTE_est_comptee_pas_reparee(self):
        # A3 (opus) — la jointure porte sur la PRÉSENCE de l'ulid. Une ligne présente au
        # BON ulid mais dont un champ (task_id) DIVERGE de la base n'est PAS réparée (le
        # magasin est en ajout seul) — mais elle est COMPTÉE et NOMMÉE, jamais passée
        # sous silence. MUTATION (fix retiré : jointure par set sans comparaison de
        # contenu) -> pas de clé "divergentes" -> KeyError, et la divergence reste
        # invisible (0 manquante, exit propre — le silence que T1 devait supprimer).
        db = self._db()
        create_tables(db)
        u = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        self._inserer_frappee(db, u, task_id="T-BASE", op="opd")
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            # Le texte de l'auteur COURANT porte le MÊME ulid mais un task_id FAUX.
            run_export.ajouter_a_l_export({
                "ulid": u, "task_id": "T-FAUX", "agent_role": "run",
                "event_type": "TASK_CREATED", "payload_json": "{}",
                "created_at": "2026-08-01 00:00:00", "operation_id": "opd",
                "event_kind": "TASK_CREATED", "attempt": 0, "predecesseur_ulid": None,
            }, depuis=self.racine, copie="vivante")
            res = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertEqual(res["divergentes"], 1, "la ligne divergente doit être COMPTÉE")
        self.assertIn(u, res["divergentes_ulid"], "l'ulid divergent doit être NOMMÉ")
        self.assertEqual(res["manquantes"], 0, "présente : pas manquante (ajout seul)")
        self.assertEqual(res["re_exportees"], 0, "une ligne présente n'est jamais réparée")
        # Le texte porte ENCORE le task_id FAUX : divergence SIGNALÉE, jamais corrigée.
        self.assertIn("T-FAUX", self._texte_export(), "le texte n'est pas réécrit (ajout seul)")
        self.assertNotIn("T-BASE", self._texte_export(), "aucune réparation silencieuse")

    def test_la_garde_de_LF_referme_la_ligne_dechiree_et_restaure_l_idempotence(self):
        # A5 (les DEUX critiques), AMENDÉ PAR F4 (binôme de CE lot) — avant la garde de
        # LF, une ligne DÉCHIRÉE (dernier enregistrement sans LF final) faisait FUSIONNER
        # l'ajout suivant : ligne illisible, ULID re-exporté à chaque passe, idempotence
        # FAUSSE (mesuré). Ce lot EST T-00000695/T-00000696 et F4 ajoute la garde à
        # `ajouter_a_l_export`, qui RÉPARE le LF (un octet, sous le verrou) AVANT
        # d'ajouter. Ce témoin prouve désormais que l'idempotence est RESTAURÉE : la
        # première passe referme la ligne déchirée et pose l'ajout sur sa PROPRE ligne
        # (deux lignes lisibles), la seconde n'exporte RIEN. MUTATION (garde F4 retirée
        # de ajouter_a_l_export) : l'ajout fusionne -> r2 re-exporte encore (1) et
        # l'assertion « r2 == 0 » rougit, et les deux lignes ne sont plus lisibles.
        db = self._db()
        create_tables(db)
        u = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
        self._inserer_frappee(db, u, task_id="T-X", op="opx")
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            auteur = run_export.auteur_courant(depuis=self.racine)
            f = self.racine / "runs" / auteur / "backfill" / "2026-08.jsonl"
            f.parent.mkdir(parents=True)
            borne = json.dumps(
                {"borne": run_export.BORNE_BACKFILL}, sort_keys=True, ensure_ascii=False
            )
            autre = run_export.nouvel_ulid(run_export._ms_de_created_at("2026-08-01 00:00:00"))
            torn = json.dumps({"ulid": autre, "task_id": "T-TORN"}, sort_keys=True)
            f.write_text(borne + "\n" + torn, encoding="utf-8")  # PAS de LF final -> déchirée
            r1 = run_export.re_exporter_frappees(base=db, depuis=self.racine)
            r2 = run_export.re_exporter_frappees(base=db, depuis=self.racine)
        self.assertEqual(r1["re_exportees"], 1, "la ligne frappée est d'abord exportée")
        self.assertEqual(
            r2["re_exportees"], 0,
            "garde de LF (F4) : la ligne déchirée est REFERMÉE -> ré-export IDEMPOTENT",
        )
        # Les DEUX lignes sont désormais lisibles et distinctes (aucune fusion).
        self.assertTrue(
            run_export._ulid_deja_exporte(f, autre),
            "la ligne préexistante (déchirée puis refermée) reste lisible",
        )
        self.assertTrue(
            run_export._ulid_deja_exporte(f, u),
            "l'ajout est tombé sur sa PROPRE ligne, lisible",
        )
        doc = (run_export.re_exporter_frappees.__doc__ or "").lower().replace("é", "e")
        self.assertIn("dechiree", doc, "la docstring doit NOMMER la ligne « déchirée »")
        self.assertIn(
            "t-00000695", doc, "la docstring doit citer la garde de LF (T-00000695/696)"
        )


class TestCliContratDeRefus(unittest.TestCase):
    """CORRECTIF 2 (grave 2, S-00001808) + 5a (T12) : la CLI NE frappe PAS la base
    vivante par défaut et refuse avec des codes DISTINCTS (3/4/5). `_cli` retourne
    l'entier ; argparse (2) lève SystemExit. Les refus vont sur STDERR, stdout reste
    du JSON pur quand la commande réussit."""

    def _cli(self, argv):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = run_export._cli(argv)
        return rc, err.getvalue()

    def test_exit_3_backfill_sans_base_designee(self):
        # MUTATION : retirer le refus (base=None accepté par défaut) -> rc != 3.
        rc, err = self._cli(["backfill"])
        self.assertEqual(rc, 3)
        self.assertIn("--base", err)  # le message NOMME le remède
        self.assertIn("--base-vivante", err)

    def test_exit_4_base_inexistante_et_non_creee(self):
        # MUTATION : retirer le contrôle d'existence CLI -> la garde bibliothèque lève
        # (RunExportError se propage), rc != 4.
        with tempfile.TemporaryDirectory() as tmp:
            manque = Path(tmp) / "absent.db"
            rc, err = self._cli(["backfill", "--base", str(manque)])
            self.assertEqual(rc, 4)
            self.assertIn(str(manque), err)  # le chemin est nommé
            self.assertFalse(manque.exists(), "le refus ne doit PAS créer la base")

    def test_exit_4_base_est_un_repertoire(self):
        # A4 (fable) : `--base <répertoire>` passait `.exists()` (vrai) puis
        # sqlite3.connect levait OperationalError NON attrapée -> rc 1, HORS énumération
        # (2–6). MUTATION (fix retiré : `.exists()` au lieu de `.is_file()`) -> l'appel
        # lève OperationalError au lieu de rendre 4. Corrigé : `.is_file()` -> rc 4.
        with tempfile.TemporaryDirectory() as tmp:
            repertoire = Path(tmp) / "un_repertoire"
            repertoire.mkdir()
            rc, err = self._cli(["backfill", "--base", str(repertoire)])
        self.assertEqual(rc, 4)
        self.assertIn(str(repertoire), err)  # le chemin fautif est nommé
        self.assertIn("fichier", err.lower())  # « n'est pas un fichier de base »

    def test_exit_5_base_et_base_vivante_exclusifs(self):
        # MUTATION : retirer le contrôle d'exclusivité -> proceeds, rc != 5.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "b.db"
            db.write_bytes(b"")  # existe (pour ne pas capter l'exit 4)
            rc, err = self._cli(["backfill", "--base", str(db), "--base-vivante"])
        self.assertEqual(rc, 5)
        self.assertIn("exclusif", err.lower())

    def test_exit_5_re_exporter_et_appliquer_depuis_exclusifs(self):
        # M1 (exec-critic sur da699e8) : --re-exporter (réparation) et --appliquer-depuis
        # (jambe 1b) sont deux MODES exclusifs. AVANT : --re-exporter AVALAIT
        # --appliquer-depuis en SILENCE -> rc 0, JSON sain, option abandonnée sans un mot.
        # Les DEUX chemins existent, pour que le refus ne soit PAS un exit 4 déguisé.
        # project_root est PINGLÉ sur un tempfile et l'auteur mocké : SANS le refus, la
        # mutation exécute re_exporter_frappees, qui NE DOIT PAS toucher le runs/ RÉEL.
        # MUTATION (fix retiré) : retirer le refus d'exclusivité de mode -> --re-exporter
        # tourne (rc 0 sur base vide), --appliquer-depuis est abandonné -> rc != 5.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "projet").mkdir()
            base = Path(tmp) / "base.db"
            create_tables(base)   # base RÉELLE (table présente), aucune ligne
            copie = Path(tmp) / "copie.db"
            create_tables(copie)  # copie 1a RÉELLE — les DEUX existent
            env = {
                "CADRE_PROJECT_ROOT": str(Path(tmp) / "projet"),
                "CADRE_STATE_DIR": str(Path(tmp) / "state"),
            }
            err = io.StringIO()
            with mock.patch.dict(os.environ, env):
                with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
                    with redirect_stderr(err):
                        rc = run_export._cli([
                            "backfill", "--base", str(base),
                            "--re-exporter", "--appliquer-depuis", str(copie),
                        ])
            err = err.getvalue()
        self.assertEqual(rc, 5)
        self.assertIn("--re-exporter", err)       # les DEUX options sont NOMMÉES
        self.assertIn("--appliquer-depuis", err)

    def test_exit_2_est_le_defaut_argparse(self):
        # Le code 2 est le défaut d'argparse (usage) — commande inconnue -> SystemExit(2).
        # Non vacant : une commande VALIDE (mesure) ne lève PAS SystemExit (contraste).
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stderr(io.StringIO()):
                run_export._cli(["commande-inconnue"])
        self.assertEqual(ctx.exception.code, 2)

    def test_mesure_reste_sans_option_stdout_json_pur_rc_0(self):
        # `mesure` reste sans option et rend 0 ; stdout est du JSON PUR.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "projet").mkdir()
            env = {
                "CADRE_PROJECT_ROOT": str(Path(tmp) / "projet"),
                "CADRE_STATE_DIR": str(Path(tmp) / "state"),
            }
            with mock.patch.dict(os.environ, env):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run_export._cli(["mesure"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())  # JSON pur, parsable
        self.assertIn("octets_total", data)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (R3 de T-00000759)")
    def test_exit_6_base_ou_copie_lien_vers_une_base_reelle_t770(self):
        """F2 (T-00000770) — `--base` OU `--appliquer-depuis` = un LIEN vers une
        base V3 RÉELLE distincte, tenue ouverte (base + `-wal` + `-shm`) : rc 6,
        stderr « refus de la bibliothèque : refus d'ouverture : … lien
        symbolique », les trois fichiers tiers inchangés. `.is_file()` suit le
        lien, donc la garde rc 4 le laisse passer : c'est `_ouvrir_base_sqlite`
        qui refuse. BASE SUIVAIT le lien et frappait la base tierce. Mord : Mg."""
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp).resolve()
            (racine / "projet").mkdir()
            dehors = racine / "dehors"
            dehors.mkdir()
            tierce = dehors / "tierce.db"
            create_tables(tierce)
            tenue = sqlite3.connect(str(tierce))
            try:
                tenue.execute("PRAGMA journal_mode=WAL")
                tenue.execute(
                    "INSERT INTO events_ledger (task_id, agent_role, event_type, "
                    "payload_json) VALUES ('T-1', 'banc', 'banc', '{}')")
                tenue.commit()
                trois = [tierce, Path(str(tierce) + "-wal"), Path(str(tierce) + "-shm")]
                self.assertTrue(all(p.exists() for p in trois), "banc non armé")
                avant = [p.read_bytes() for p in trois]
                lien = racine / "lien.db"
                os.symlink(tierce, lien)
                base = racine / "base.db"
                create_tables(base)
                env = {"CADRE_PROJECT_ROOT": str(racine / "projet"),
                       "CADRE_STATE_DIR": str(racine / "state")}
                for argv in (["backfill", "--base", str(lien)],
                             ["backfill", "--base", str(base), "--appliquer-depuis", str(lien)]):
                    with self.subTest(argv=argv[1:]):
                        err = io.StringIO()
                        with mock.patch.dict(os.environ, env), \
                                mock.patch.object(run_export, "_email_git",
                                                  return_value="banc@test"), \
                                redirect_stderr(err), redirect_stdout(io.StringIO()):
                            rc = run_export._cli(argv)
                        self.assertEqual(rc, 6, err.getvalue())
                        self.assertIn("refus de la bibliothèque : refus d'ouverture :",
                                      err.getvalue())
                        self.assertIn("lien symbolique", err.getvalue())
                        self.assertEqual([p.read_bytes() for p in trois], avant,
                                         "la base tierce a été écrite")
            finally:
                tenue.close()


class TestCliFermeSonEnumerationAuBord(unittest.TestCase):
    """M2 (exec-critic sur da699e8) — le contrat de codes se DISAIT clos (0/2/3/4/5)
    et ne l'était pas : les gardes bibliothèque (auteur indisponible, T12b created_at,
    T12a base) levaient `RunExportError` sans `except` au bord CLI -> traceback brut,
    rc 1, HORS énumération. `_cli` ferme l'énumération AU BORD : code 6, message sur
    STDERR sans traceback, et le `except` n'attrape QUE `RunExportError`."""

    def _env(self, tmp):
        (Path(tmp) / "projet").mkdir()
        return {
            "CADRE_PROJECT_ROOT": str(Path(tmp) / "projet"),
            "CADRE_STATE_DIR": str(Path(tmp) / "state"),
        }

    def test_code_6_quand_l_auteur_est_indisponible(self):
        # M2, chemin MESURÉ par le pilote : auteur indisponible (git user.email vide)
        # -> empreinte_auteur lève RunExportError DANS backfill_historique, AVANT toute
        # écriture. Sans except au bord -> traceback rc 1 ; avec -> code 6, stderr, pas
        # de traceback. MUTATION (fix retiré) : retirer l'except RunExportError de _cli
        # -> RunExportError se propage hors de _cli -> le test rougit (exception, pas rc 6).
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hist.db"
            create_tables(db)
            err = io.StringIO()
            with mock.patch.dict(os.environ, self._env(tmp)):
                with mock.patch.object(run_export, "_email_git", return_value=""):
                    with redirect_stderr(err):
                        rc = run_export._cli(["backfill", "--base", str(db)])
        self.assertEqual(rc, 6, "une garde bibliothèque doit sortir en code 6 (énuméré)")
        self.assertIn("user.email", err.getvalue(), "le message de refus nomme la cause")
        self.assertNotIn("Traceback", err.getvalue(), "aucun traceback ne doit fuiter")

    def test_code_6_quand_created_at_est_hors_forme(self):
        # M2, SECOND chemin distinct : created_at hors forme -> _ms_de_created_at lève
        # RunExportError (T12b) dans _frapper_triplets, AVANT tout UPDATE/export. Même
        # sortie : code 6, stderr, pas de traceback. MUTATION identique (except retiré).
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hist.db"
            create_tables(db)
            conn = sqlite3.connect(str(db))
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
                ("T-BAD", "run", "TASK_CREATED", "{}", "pas une date", "opbad",
                 "TASK_CREATED", 0),
            )
            conn.commit()
            conn.close()
            err = io.StringIO()
            with mock.patch.dict(os.environ, self._env(tmp)):
                with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
                    with redirect_stderr(err):
                        rc = run_export._cli(["backfill", "--base", str(db)])
        self.assertEqual(rc, 6)
        self.assertIn("created_at", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_une_panne_d_infrastructure_n_est_PAS_deguisee_en_code_6(self):
        # BORNE (leçon binôme T-650) : le `except` n'attrape QUE RunExportError. Une
        # panne d'infrastructure (OperationalError) NE doit PAS ressortir en refus
        # code 6 — elle se PROPAGE. MUTATION (except trop large : `except Exception`) ->
        # l'OperationalError deviendrait un code 6 et assertRaises tomberait.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hist.db"
            create_tables(db)
            with mock.patch.dict(os.environ, self._env(tmp)):
                with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
                    with mock.patch.object(
                        run_export, "backfill_historique",
                        side_effect=sqlite3.OperationalError("database is locked"),
                    ):
                        with self.assertRaises(sqlite3.OperationalError):
                            run_export._cli(["backfill", "--base", str(db)])

    def test_une_PanneInfrastructure_n_est_PAS_deguisee_en_code_6(self):
        # critic-opus T6 (T-00000695/696) : `PanneInfrastructure` EST une
        # `RunExportError`, donc le handler du code 6 la déguisait en REFUS alors que
        # le contrat de `_cli` range la panne HORS énumération (rc 1, traceback).
        # MUTATION (retirer `except PanneInfrastructure: raise`) : rc 6 rendu,
        # `assertRaises` tombe, rouge.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hist.db"
            create_tables(db)
            panne = run_export.PanneInfrastructure("git config user.email a ÉCHOUÉ (banc)")
            with mock.patch.dict(os.environ, self._env(tmp)):
                with mock.patch.object(run_export, "_email_git", side_effect=panne):
                    with self.assertRaises(run_export.PanneInfrastructure):
                        run_export._cli(["backfill", "--base", str(db)])

    def test_code_de_sortie_1_sur_git_absent_par_le_vrai_canal(self):
        # Le CODE DE SORTIE réel, en sous-processus : `git` ABSENT du PATH ->
        # l'exécuteur rend 127 -> `PanneInfrastructure` -> rc 1 avec traceback,
        # jamais le 6 d'un refus. Précondition MESURÉE : git introuvable sous ce PATH.
        # MUTATION (retirer `except PanneInfrastructure: raise`) : rc 6, rouge.
        import shutil

        module = str(Path(run_export.__file__).resolve())
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "hist.db"
            create_tables(db)
            vide = Path(tmp) / "bin-vide"
            vide.mkdir()
            self.assertIsNone(shutil.which("git", path=str(vide)), "précondition : pas de git")
            env = _env_sans_git()
            env.update(self._env(tmp))
            env["PATH"] = str(vide)
            r = subprocess.run(
                [sys.executable, "-B", module, "backfill", "--base", str(db)],
                capture_output=True, text=True, env=env, timeout=120,
            )
        self.assertEqual(1, r.returncode, f"rc={r.returncode}\n{r.stderr}")
        self.assertIn("PanneInfrastructure", r.stderr)
        self.assertIn("code=127", r.stderr, "la cause mesurée : git absent")
        self.assertNotIn("refus de la bibliothèque", r.stderr, "pas déguisée en refus")


class TestCliFormeDocumentee(unittest.TestCase):
    """La CLI directe backfill charge le paquet V3 exact ; sans amorçage, rc non nul."""

    MODULE = str(Path(run_export.__file__).resolve())
    PARENT_IMPORT = Path(run_export.__file__).resolve().parents[1].parent

    def _base_env(self, tmp):
        projet = Path(tmp) / "projet"
        projet.mkdir()
        state = Path(tmp) / "state"
        # git identity LOCALE : `git config user.email` répond de façon déterministe.
        # `env=_env_sans_git()` (exec-critic, passes post-binôme) : sans lui, un
        # `GIT_DIR` hérité faisait écrire ce `config` dans le dépôt HÔTE — mesuré,
        # son `user.email` devenait `doc@banc.test`.
        sans_git = _env_sans_git()
        subprocess.run(["git", "init", "-q", str(projet)], check=True, env=sans_git)
        subprocess.run(
            ["git", "-C", str(projet), "config", "user.email", "doc@banc.test"],
            check=True, env=sans_git,
        )
        db = Path(tmp) / "hist.db"
        create_tables(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
            ("T-C3", "run", "TASK_CREATED", "{}", "2026-08-01 00:00:00", "opc3",
             "TASK_CREATED", 0),
        )
        conn.commit()
        conn.close()
        env = _env_sans_git()
        env["CADRE_PROJECT_ROOT"] = str(projet)
        env["CADRE_STATE_DIR"] = str(state)
        return env, db

    def test_forme_documentee_directe_backfill_et_mesure(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, db = self._base_env(tmp)
            # backfill : forme documentée, EXIGE l'import agentic_v3.db.schema.
            r_bf = subprocess.run(
                [sys.executable, "-B", self.MODULE, "backfill", "--base", str(db)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(
                r_bf.returncode, 0,
                f"backfill direct-script: rc={r_bf.returncode}\n{r_bf.stderr}",
            )
            data = json.loads(r_bf.stdout)  # stdout JSON pur
            self.assertEqual(data["frappees"], 1)
            # mesure : forme documentée aussi.
            r_m = subprocess.run(
                [sys.executable, "-B", self.MODULE, "mesure"],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(r_m.returncode, 0, r_m.stderr)
            json.loads(r_m.stdout)

    def test_forme_m_marche_avec_un_RuntimeWarning_tolere(self):
        # Témoin conservé de la forme -m (RuntimeWarning runpy TOLÉRÉ, jamais filtré) :
        # rc 0 et stdout JSON pur malgré l'avertissement sur stderr.
        with tempfile.TemporaryDirectory() as tmp:
            env, _db = self._base_env(tmp)
            r = subprocess.run(
                [sys.executable, "-B", "-m", "agentic_v3.db.run_export", "mesure"],
                capture_output=True, text=True, env=env, cwd=str(self.PARENT_IMPORT),
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            json.loads(r.stdout)


class TestBorneEnTete(_PartitionFixture):
    """CORRECTIF 4 — T10 (S-00001809 / S-00001808 MOYEN 6) : sur un fichier EXISTANT
    dont la 1re ligne n'est pas une borne, la borne est posée EN TÊTE par réécriture
    atomique, JAMAIS appendue en queue. Les octets préexistants sont INCHANGÉS."""

    def test_la_borne_est_posee_EN_TETE_octet_pour_octet(self):
        # MUTATION : revenir à `open(chemin, "a")` -> la borne atterrit en ligne 3,
        # l'assertion « ligne 1 = borne » rougit.
        fichier = self.racine / "runs" / "auteurX" / "backfill" / "2026-08.jsonl"
        fichier.parent.mkdir(parents=True)
        e1 = json.dumps({"ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "task_id": "T-1"}, sort_keys=True)
        e2 = json.dumps({"ulid": "01ARZ3NDEKTSV4RRFFQ69G5FB0", "task_id": "T-2"}, sort_keys=True)
        original = e1 + "\n" + e2 + "\n"
        fichier.write_text(original, encoding="utf-8")

        run_export._ecrire_borne_en_tete(fichier)

        lignes = fichier.read_text(encoding="utf-8").splitlines()
        self.assertIn("borne", json.loads(lignes[0]), "ligne 1 doit être la borne")
        self.assertEqual(lignes[1], e1, "ligne 2 = 1er événement INCHANGÉ")
        self.assertEqual(lignes[2], e2, "ligne 3 = 2e événement INCHANGÉ")
        # Les octets préexistants suivent la borne, EXACTEMENT (aucun retrait/mod).
        self.assertTrue(
            fichier.read_text(encoding="utf-8").endswith(original),
            "le contenu préexistant doit suivre la borne, octet pour octet",
        )
        # Idempotent : un second appel ne double PAS la borne.
        run_export._ecrire_borne_en_tete(fichier)
        lignes2 = [l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(
            sum(1 for l in lignes2 if "borne" in json.loads(l)), 1,
            "la borne ne doit pas être doublée",
        )

    def test_un_echec_de_replace_ne_laisse_aucun_temporaire_sous_runs(self):
        # m4 (exec-critic sur da699e8) : le `.tmp` de réécriture atterrit SOUS runs/
        # (versionné). Un échec de CE processus entre l'écriture et l'os.replace ne doit
        # laisser AUCUN temporaire (git add -- runs le capterait), et l'original reste
        # intact octet pour octet. La branche de réécriture n'est atteinte que sur un
        # fichier EXISTANT dont la 1re ligne n'est PAS une borne (on la fabrique ici).
        # MUTATION (fix retiré : plus de try/finally) : le .tmp survit à l'os.replace
        # qui lève -> l'assertion « aucun .borne.tmp » rougit.
        fichier = self.racine / "runs" / "auteurX" / "backfill" / "2026-08.jsonl"
        fichier.parent.mkdir(parents=True)
        e1 = json.dumps({"ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "task_id": "T-1"}, sort_keys=True)
        original = e1 + "\n"  # 1re ligne = événement, PAS une borne -> branche réécriture
        fichier.write_text(original, encoding="utf-8")
        octets_avant = fichier.read_bytes()

        with mock.patch.object(run_export.os, "replace", side_effect=OSError("replace KO")):
            with self.assertRaises(OSError):
                run_export._ecrire_borne_en_tete(fichier)

        # (1) AUCUN temporaire ne subsiste sous runs/ (git add -- runs le capterait).
        residus = list(fichier.parent.glob("*.borne.tmp"))
        self.assertEqual(residus, [], "un temporaire .borne.tmp a survécu sous runs/")
        # (2) le fichier d'origine est INTACT, octet pour octet.
        self.assertEqual(fichier.read_bytes(), octets_avant, "l'original doit rester intact")

    def test_le_verrou_est_tenu_pendant_le_read_replace_de_la_borne(self):
        # F5 (binôme) : `_ecrire_borne_en_tete` lit puis os.replace le MÊME fichier de
        # mois qu'appende `ajouter_a_l_export`. Hors verrou, un append d'un AUTRE écrivain
        # ENTRE son read et son replace serait PERDU (pire qu'un doublon en ajout seul).
        # Ce témoin prouve que le verrou d'export est DÉTENU pendant la section
        # read->replace : au moment PRÉCIS de l'os.replace, une acquisition NON BLOQUANTE
        # du MÊME verrou sur un FD FRAIS ÉCHOUE (contention cross-FD, mesurée errno 35).
        # MUTATION (retirer `with _verrou_export` de `_ecrire_borne_en_tete`) :
        # l'acquisition réussit -> l'assertion « verrou tenu » rougit.
        if os.name == "nt":
            self.skipTest("flock POSIX : contention cross-FD non portée telle quelle sous nt")
        import fcntl
        fichier = self.racine / "runs" / "auteurX" / "backfill" / "2026-08.jsonl"
        fichier.parent.mkdir(parents=True)
        e1 = json.dumps({"ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "task_id": "T-1"}, sort_keys=True)
        fichier.write_text(e1 + "\n", encoding="utf-8")  # 1re ligne = événement -> réécriture
        observe: dict = {}
        vrai_replace = run_export.os.replace

        def replace_espion(src, dst):
            lock_path = run_export._fichier_verrou_export(depuis=self.racine)
            fd = os.open(str(lock_path), os.O_RDWR)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    observe["verrou_tenu"] = False  # a acquis -> verrou NON tenu (mutation)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    observe["verrou_tenu"] = True   # refusé -> verrou TENU (fix en place)
            finally:
                os.close(fd)
            return vrai_replace(src, dst)

        with mock.patch.object(run_export.os, "replace", side_effect=replace_espion):
            run_export._ecrire_borne_en_tete(fichier, depuis=self.racine)
        self.assertTrue(
            observe.get("verrou_tenu"),
            "le verrou d'export doit être DÉTENU pendant le read->replace de la borne",
        )
        lignes = [l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertIn("borne", json.loads(lignes[0]), "la borne est bien posée en tête")


class TestGardeLfALajout(_PartitionFixture):
    """F4 (binôme, promesse de `re_exporter_frappees` / L-00000111) : `ajouter_a_l_export`
    RÉPARE en AJOUT SEUL (un octet) le LF terminal d'un enregistrement DÉCHIRÉ avant
    d'ajouter, sans quoi l'ajout FUSIONNE avec la ligne déchirée — 0 ligne lisible sur 2
    et un doublon irréparable au rejeu (mesuré)."""

    def test_un_ajout_referme_la_ligne_dechiree_et_reste_lisible(self) -> None:
        # MUTATION (garde F4 retirée) : l'ajout se COLLE à la ligne déchirée -> la ligne
        # fusionnée est illisible -> `_ulid_deja_exporte` rend False sur les DEUX ulids et
        # les assertions ci-dessous rougissent (0 lisible sur 2).
        u1 = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        u2 = "01ARZ3NDEKTSV4RRFFQ69G5FB0"
        fichier = run_export.chemin_export(
            u2, depuis=self.racine, copie="course", auteur="0000000000000000"
        )
        fichier.parent.mkdir(parents=True, exist_ok=True)
        torn = json.dumps({"ulid": u1, "task_id": "T-TORN"}, sort_keys=True)
        fichier.write_text(torn, encoding="utf-8")  # PAS de LF final -> ligne déchirée
        run_export.ajouter_a_l_export(
            {"ulid": u2, "task_id": "T-NEW", "agent_role": "run"},
            depuis=self.racine, copie="course", auteur="0000000000000000",
        )
        # DEUX lignes JSON lisibles et distinctes (aucune fusion) : la garde a réparé le LF.
        lignes = [l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lignes), 2, "deux lignes distinctes attendues (LF réparé)")
        self.assertTrue(run_export._ulid_deja_exporte(fichier, u1), "u1 (déchiré) reste lisible")
        self.assertTrue(run_export._ulid_deja_exporte(fichier, u2), "u2 (ajouté) est lisible")


class TestGardesEntree(_PartitionFixture):
    """CORRECTIF 5 — T12 (S-00001809), deux entrées non gardées côté bibliothèque
    (RunExportError). (a) base inexistante ; (b) created_at NULL/hors forme."""

    def test_backfill_refuse_une_base_inexistante_sans_la_creer(self):
        # (a) sqlite3.connect CRÉERAIT une base vide de 0 octet. MUTATION : retirer la
        # garde d'existence -> le fichier est créé, puis 'no such table' plus loin.
        manque = self.state / "base_absente.db"
        self.assertFalse(manque.exists())
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            with self.assertRaises(RunExportError) as ctx:
                run_export.backfill_historique(base=manque, depuis=self.racine)
        self.assertIn(str(manque), str(ctx.exception))  # le chemin est nommé
        self.assertFalse(manque.exists(), "le refus ne doit PAS créer une base vide")

    def test_created_at_hors_forme_leve_RunExportError_nommant_event_id(self):
        # (b) MUTATION : retirer la garde de _ms_de_created_at -> strptime lève un
        # ValueError NU (non RunExportError) -> assertRaises(RunExportError) rougit.
        db = self._db()
        create_tables(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
            "created_at,operation_id,event_kind,attempt) VALUES (?,?,?,?,?,?,?,?)",
            ("T-BAD", "run", "TASK_CREATED", "{}", "pas une date", "opbad",
             "TASK_CREATED", 0),
        )
        conn.commit()
        conn.close()
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            with self.assertRaises(RunExportError) as ctx:
                run_export.backfill_historique(base=db, depuis=self.racine)
        msg = str(ctx.exception)
        self.assertIn("created_at", msg)
        self.assertIn("pas une date", msg, "la valeur fautive doit être nommée")
        self.assertIn("event_id", msg, "l'event_id doit être nommé pour retrouver la ligne")


# T-00000690 : pause posée APRÈS une relecture qui trouve l'ulid ABSENT, donc entre le
# « check » et l'« act » de `ajouter_a_l_export`. 26bbb135 (T-691) a rétréci cette
# fenêtre à deux syscalls sur un descripteur unique ; sans cette aide la course sans
# verrou n'est plus vue qu'occasionnellement. Remède à un faux rouge du témoin : 0.005.
_ELARGISSEMENT_S = 0.002


def _worker_ajout_concurrent(
    root: str, ulids_json: str, depart_ts: str, frappe_out: str, mode: str
) -> None:
    """Point d'entrée SUBPROCESS du témoin de course (T2, S-00001806). Écrit
    CHAQUE ulid de `ulids_json` dans l'export sous un auteur/copie FIXES (aucun
    git, aucune résolution de copie sur disque), après avoir attendu `depart_ts`
    pour que les DEUX processus frappent le fichier CONCURREMMENT.

    T-00000690 — la fenêtre check-then-act est ÉLARGIE en enveloppant, PAR NOM, la
    relecture `run_export._ulid_dans_descripteur` : un retour « absent » compte
    (`elargis`) puis dort `_ELARGISSEMENT_S`. `mode` vaut `verrou` (produit tel quel)
    ou `sans-verrou` (`_verrou_export` remplacé par un no-op DANS ce sous-processus).
    `frappe_out` reçoit, APRÈS la boucle, `{"frappe": <sortie de barrière>,
    "elargis": <n>}`."""
    import contextlib as _contextlib
    import json as _json
    import time as _time
    from pathlib import Path as _Path
    from unittest import mock as _mock

    from agentic_v3.db import run_export as _re

    if mode not in ("verrou", "sans-verrou"):
        raise ValueError(f"mode {mode!r} inconnu (attendu : verrou | sans-verrou)")
    nom = "_ulid_dans_descripteur"
    relire = getattr(_re, nom, None)
    if not callable(relire):
        # Sans ce nom, l'élargissement ne serait posé NULLE PART et la course redeviendrait
        # non falsifiable EN SILENCE : on refuse en nommant ce qui manque.
        raise RuntimeError(
            f"run_export.{nom} introuvable : l'élargissement de la fenêtre check-then-act "
            "l'enveloppe PAR NOM (T-00000690) — ré-enveloppe la relecture de "
            "`ajouter_a_l_export` sous son nouveau nom, sinon la course n'est plus falsifiable"
        )
    elargis = 0

    def _relire_puis_elargir(fd: int, ulid: str) -> bool:
        nonlocal elargis
        present = relire(fd, ulid)
        if not present:
            elargis += 1
            _time.sleep(_ELARGISSEMENT_S)
        return present

    ulids = _json.loads(_Path(ulids_json).read_text(encoding="utf-8"))
    cible = float(depart_ts)
    with _contextlib.ExitStack() as pile:
        # Patchs posés AVANT la barrière : sa sortie enchaîne directement sur la boucle.
        pile.enter_context(_mock.patch.object(_re, nom, _relire_puis_elargir))
        if mode == "sans-verrou":
            pile.enter_context(_mock.patch.object(
                _re, "_verrou_export", lambda **k: _contextlib.nullcontext()
            ))
        while _time.time() < cible:  # top commun -> les deux entrent dans la boucle ensemble
            pass
        # F7 : instant de FRAPPE = sortie de barrière, capturé AVANT la boucle et écrit
        # APRÈS elle (aucune écriture de fichier dans la fenêtre de course). Le témoin
        # asserte que les deux workers l'ont franchie à < 0,05 s l'un de l'autre : sans
        # cette barrière TENUE, la course n'a pas lieu et le vert ne prouve rien.
        frappe = _time.time()
        for ulid in ulids:
            _re.ajouter_a_l_export(
                {
                    "ulid": ulid, "task_id": "T-C", "agent_role": "run",
                    "event_type": "TASK_CREATED", "payload_json": "{}",
                    "created_at": "2026-08-01 00:00:00", "operation_id": "opc",
                    "event_kind": "TASK_CREATED", "attempt": 0,
                    "predecesseur_ulid": None,
                },
                depuis=root, copie="course", auteur="0000000000000000",
            )
    # Écrit par pathlib (safe-bash compare par NOM).
    _Path(frappe_out).write_text(
        _json.dumps({"frappe": frappe, "elargis": elargis}), encoding="utf-8"
    )


class TestVerrouExportContreDoublon(_PartitionFixture):
    """CORRECTIF A — T2 (S-00001806) : le check-then-act de `ajouter_a_l_export`,
    sous rejeu CONCURRENT, écrit un DOUBLON dans le magasin en AJOUT SEUL
    (irréparable par `git revert`). Le verrou `_verrou_export` le sérialise.

    Forme reprise de S-00001806 : 2 processus, N ulids communs. Sans verrou et SANS
    aide, la fenêtre check-then-act — rétrécie à deux syscalls sur un descripteur
    unique par 26bbb135 (T-691) — ne produit plus qu'un doublon occasionnel : mesuré
    (T-00000690 rév.3) ≈ 10 % par exécution sous cette invocation pytest (9/90),
    ≈ 33 % par appel direct de l'ouvrier hors pytest (37/111), écart non attribué ;
    le « ~2/3 » d'origine précède 26bbb135. Un vert isolé ne prouve donc pas le
    verrou : `test_le_temoin_rougit_sans_verrou` élargit la fenêtre (2 ms) et prouve
    qu'une course SANS verrou est vue. Avec verrou : EXACTEMENT N lignes.

    Fermeture (T-00000690) : 9e7597b7 a fermé S-00001806. Le verrou vit DANS
    `ajouter_a_l_export`, donc tout appelant (pytest, appel direct, `replay-sync`) est
    couvert de la même façon ; aucune exécution sous verrou réel n'a produit de
    doublon (contrôle positif 0/5, S-00002651 ; D4 rév.1 0/10 sous élargissement,
    plan 0adedd0a:25). Les 37/111 hors pytest comptent, en 5e observation, le bras
    « nu » du banc H-sqlite (8/30) : ce n'est pas un échantillon de plus. Via
    `replay-sync`, 0/21 : non distinguable du taux pytest (p ≈ 0,20) ; l'hypothèse
    « un pas intercalé entre deux exports désynchronise les rejoueurs » est soutenue
    (H-sqlite 8/30 → 1/30), son mécanisme n'est pas prouvé. Sous élargissement, le
    `with` de `ajouter_a_l_export` neutralisé côté produit rougit le test historique
    5/5 (P1e, plan 98f09d0a:21)."""

    _N = 60

    def _lancer_course(self, *, mode: str = "verrou") -> int:
        ulids = [
            run_export.nouvel_ulid(
                run_export._ms_de_created_at("2026-08-01 00:00:00")
            )
            for _ in range(self._N)
        ]
        # ulids distincts, tous en août -> UN seul fichier de mois (contention max).
        self.assertEqual(len(set(ulids)), self._N)
        ulids_json = self.state / "ulids.json"
        ulids_json.parent.mkdir(parents=True, exist_ok=True)
        ulids_json.write_text(json.dumps(ulids), encoding="utf-8")
        env = dict(os.environ)
        env["CADRE_PROJECT_ROOT"] = str(self.racine)
        env["CADRE_STATE_DIR"] = str(self.state)
        boot = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from agentic_v3.tests.test_run_export import "
            "_worker_ajout_concurrent as w; "
            "w(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])"
        )
        parent_import = str(Path(run_export.__file__).resolve().parents[1].parent)  # en tête : la copie résolue gagne sur le cwd
        depart = repr(time.time() + 0.4)
        frappes = [self.state / f"frappe_{i}.txt" for i in range(2)]
        procs = [
            subprocess.Popen(
                [sys.executable, "-B", "-c", boot, parent_import,
                 str(self.racine), str(ulids_json), depart, str(frappes[i]), mode],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(2)
        ]
        try:
            for p in procs:
                _out, err = p.communicate(timeout=90)
                self.assertEqual(p.returncode, 0, f"worker rc={p.returncode}\n{err}")
        finally:
            # F5 (binôme, T-00000690) : un ouvrier en échec (rc≠0) ou en timeout ne doit
            # pas laisser l'autre VIVANT, écrivant après le nettoyage du dossier temporaire
            # (`communicate(timeout=)` ne tue pas le processus qu'il abandonne).
            for q in procs:
                if q.poll() is None:
                    q.kill()
                    q.communicate()
        # F7 : la barrière a-t-elle TENU ? Sans preuve que les deux frappes sont
        # SIMULTANÉES, un vert « aucun doublon » peut venir d'une absence de course (les
        # deux processus démarrés l'un après l'autre) et ne prouve alors RIEN. On asserte
        # l'écart des deux instants de frappe < 0,05 s (marge mesurée ~4x aujourd'hui).
        rapports = [json.loads(f.read_text(encoding="utf-8")) for f in frappes]
        t0, t1 = (float(r["frappe"]) for r in rapports)
        ecart = abs(t0 - t1)
        self.assertLess(
            ecart, 0.05,
            f"barrière NON tenue (écart {ecart:.4f}s >= 0,05s) : les deux processus n'ont "
            "pas frappé ensemble, la course n'a pas eu lieu et le vert « aucun doublon » "
            "ne prouve RIEN (relève depart_ts ou allège la charge machine)",
        )
        # T-00000690 : l'élargissement a-t-il été APPLIQUÉ ? Chaque ulid écrit l'a été
        # après une relecture « absent » par l'enveloppe, donc la somme vaut AU MOINS N
        # (sous verrou elle vaut N : attendu, non asserté). En dessous, l'enveloppe n'est
        # plus sur le chemin de `ajouter_a_l_export` et la course n'est plus élargie.
        elargis = sum(int(r["elargis"]) for r in rapports)
        self.assertGreaterEqual(
            elargis, self._N,
            f"élargissement NON appliqué ({elargis} relectures « absent » élargies pour "
            f"{self._N} ulids) : l'enveloppe de `_ulid_dans_descripteur` n'est plus sur le "
            "chemin de `ajouter_a_l_export` — la fenêtre de course n'est plus élargie",
        )
        return elargis

    def _ulids_du_texte(self) -> list:
        out: list = []
        for fichier in sorted(self._runs().rglob("*.jsonl")):
            for brute in fichier.read_text(encoding="utf-8").splitlines():
                brute = brute.strip()
                if brute:
                    out.append(json.loads(brute)["ulid"])
        return out

    def test_deux_processus_concurrents_ne_creent_aucun_doublon(self) -> None:
        # GREEN (verrou en place) : EXACTEMENT N lignes, chaque ulid UNE fois.
        # MUTATION (verrou no-op) : sans élargissement vue ≈ 1 fois sur 10 (rév.3) — la
        # détection repose sur l'élargissement et le témoin ci-dessous.
        # MUTATION côté produit, élargissement actif : `with _verrou_export(depuis=depuis):`
        # DANS `ajouter_a_l_export` (le même `with` existe ailleurs) -> `nullcontext()` :
        # ROUGE ici 5/5 sur le compte de lignes (120 != 60), le témoin restant vert.
        self._lancer_course()
        ulids = self._ulids_du_texte()
        self.assertEqual(
            len(ulids), self._N,
            f"{len(ulids)} lignes pour {self._N} ulids — un doublon a été écrit "
            "(course non verrouillée)",
        )
        self.assertEqual(
            len(set(ulids)), self._N, "un ulid apparaît plusieurs fois dans l'export"
        )

    def test_le_temoin_rougit_sans_verrou(self) -> None:
        # T-00000690 — SENSIBILITÉ du filet. Même course, `_verrou_export` remplacé par un
        # no-op DANS les sous-processus, fenêtre élargie de `_ELARGISSEMENT_S` : un doublon
        # DOIT apparaître, sinon le vert du test ci-dessus ne prouve pas le verrou. Borne :
        # il prouve la fenêtre ÉLARGIE ; celle de production n'est démontrée que par les
        # mesures sans aide (docstring de la classe).
        # Régime, mesuré avant commit (2026-09-27, darwin, poste local, charge 1,9-4,6) :
        # ×30 vert, 0 faux rouge. CI et `verify.sh --linux` NON mesurés.
        # MUTATIONS : `_ELARGISSEMENT_S = 0` -> ROUGE ici 17/20 avant commit, 2/5 sur
        # l'archive 8d48294d, soit 19/25 (comptes OBSERVÉS, lots dispersés, pas une borne
        # i.i.d. ; critique B : ≈ 53 %) ; compteur `elargis` figé à 0 -> ROUGE sur la somme >= N
        # de `_lancer_course`, dans les deux tests ; `_ulid_dans_descripteur` renommé côté
        # produit -> rc 1 des ouvriers, message nommant ce nom.
        self._lancer_course(mode="sans-verrou")
        ulids = self._ulids_du_texte()
        self.assertGreater(
            len(ulids), self._N,
            f"{len(ulids)} lignes pour {self._N} ulids SANS verrou : aucune course vue, "
            "barrière pourtant tenue. Deux causes : (1) faux rouge de charge — "
            f"l'élargissement de {_ELARGISSEMENT_S} s n'a pas suffi à croiser les deux "
            "processus : passe `_ELARGISSEMENT_S` à 0.005, ne retire JAMAIS ce témoin ; "
            "(2) le no-op n'est plus sur le chemin — `ajouter_a_l_export` ne prend plus "
            "le verrou par le nom `_verrou_export`, et ce témoin ne prouve plus rien.",
        )


class TestVerrouExportReentrance(_PartitionFixture):
    """H2 (T-00000695/696) — la RÉENTRANCE de `_verrou_export` n'avait AUCUN témoin
    (constat du binôme). Elle a été MESURÉE avant d'être épinglée (macOS, `flock`,
    le 2026-09-23) : une seconde acquisition dans le MÊME thread rend la main en
    ~1 ms ; pendant elle ET après sa sortie, un descripteur FRAIS ne peut pas
    prendre le verrou ; un AUTRE thread du même processus attend puis lève
    `RunExportError` ; après la sortie de l'externe, le verrou est LIBRE et
    l'ensemble des chemins tenus est vide.

    QUATRE PROPRIÉTÉS, et chacune a sa mutation qui la fait rougir :
      (1) réentrance même thread — MUTATION : retirer le `if cle in tenus: yield;
          return` → l'interne tente un second `flock` et lève au délai ;
      (2) l'interne NE LIBÈRE PAS ce que tient l'externe — ni le `flock` (sonde
          par descripteur frais), ni la clé du thread. MUTATION rejouée : un
          `tenus.discard(cle)` dans la branche réentrante → le `flock` reste tenu
          par l'externe, mais la clé est perdue et l'`assertIn` rougit : la
          prochaine acquisition de ce thread reverrouillerait sur un second
          descripteur et s'auto-bloquerait jusqu'au délai ;
      (3) la réentrance est PAR THREAD, pas par processus — MUTATION : remplacer
          `threading.local()` par un objet partagé → l'autre thread passe au lieu
          d'attendre, et deux écrivains entrent ensemble ;
      (4) la sortie de l'externe LIBÈRE — MUTATION : oublier le `tenus.discard`
          du `finally` → la clé reste « tenue » et la prochaine acquisition de ce
          thread sauterait le verrou INTER-processus.
    La sonde est un descripteur FRAIS en `LOCK_NB`, comme le témoin F5 de
    `_ecrire_borne_en_tete` : la contention `flock` est par description de
    fichier ouverte, donc elle mord même dans le processus courant."""

    def setUp(self) -> None:
        super().setUp()
        if os.name == "nt":
            self.skipTest("flock POSIX : contention cross-FD non portée telle quelle sous nt")
        # Délai COURT : une réentrance cassée doit rougir vite, pas au bout de 30 s.
        patch = mock.patch.object(run_export, "_VERROU_TIMEOUT_S", 0.5)
        patch.start()
        self.addCleanup(patch.stop)

    def _tenu_par_un_autre_descripteur(self) -> bool:
        import fcntl

        chemin = run_export._fichier_verrou_export(depuis=self.racine)
        fd = os.open(str(chemin), os.O_RDWR)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    def test_reentrant_dans_le_thread_sans_rien_liberer_et_serialise_entre_threads(self) -> None:
        import threading

        cle = os.path.abspath(str(run_export._fichier_verrou_export(depuis=self.racine)))
        with run_export._verrou_export(depuis=self.racine):
            self.assertTrue(self._tenu_par_un_autre_descripteur(), "l'externe tient le verrou")
            t0 = time.monotonic()
            with run_export._verrou_export(depuis=self.racine):          # (1)
                duree = time.monotonic() - t0
                self.assertTrue(self._tenu_par_un_autre_descripteur(),
                                "pendant l'interne, le verrou reste tenu")
            self.assertLess(duree, 0.25, f"l'interne a ATTENDU {duree:.2f}s : non réentrant")
            self.assertTrue(                                             # (2)
                self._tenu_par_un_autre_descripteur(),
                "la sortie de l'INTERNE a libéré le verrou que l'EXTERNE croit tenir",
            )
            self.assertIn(cle, run_export._verrous_tenus.chemins)

            issue: dict = {}

            def autre_thread() -> None:                                  # (3)
                try:
                    with run_export._verrou_export(depuis=self.racine):
                        issue["r"] = "entré"
                except run_export.RunExportError:
                    issue["r"] = "refusé au délai"

            fil = threading.Thread(target=autre_thread)
            fil.start()
            fil.join(timeout=10)
            self.assertFalse(fil.is_alive(), "l'autre thread n'a pas rendu la main")
            self.assertEqual(
                "refusé au délai", issue.get("r"),
                "un AUTRE thread est entré pendant que celui-ci tenait le verrou : la "
                "réentrance a fui hors du thread",
            )
        self.assertFalse(self._tenu_par_un_autre_descripteur(),       # (4)
                         "la sortie de l'EXTERNE doit libérer le verrou")
        self.assertNotIn(cle, run_export._verrous_tenus.chemins,
                         "la clé ne doit plus être tenue après la sortie de l'externe")


class TestAuteurIndisponibleEtPanneGit(_PartitionFixture):
    """CORRECTIF B — fable (2) + opus T4 : « auteur absent » (REPORTABLE) et
    « panne git » (non reportable) sont désormais DISTINCTS. `AuteurIndisponible`
    sous-classe `RunExportError` ; `_email_git` NOMME le code + stderr d'un git
    cassé au lieu de masquer la cause derrière « user.email absent »."""

    def _resultat(self, code: int, stderr: str = "", expire: bool = False):
        # `Resultat` via la MÊME couture d'import que run_export (`cadre` n'est pas
        # un paquet top-level sur le sys.path du banc — chargé par chemin).
        Resultat = run_export._cadre("executor").Resultat
        return Resultat(
            argv=("git", "config", "user.email"),
            code=code, stdout="", stderr=stderr, expire=expire,
        )

    def _seam_executor(self, res):
        """Remplace la couture `_cadre` pour rendre un exécuteur factice sur
        « executor », en DÉLÉGUANT « paths »/reste au vrai `_cadre`."""
        reel = run_export._cadre

        def faux(nom):
            if nom == "executor":
                class _Mod:
                    def LocalExecutor(_self):
                        class _Exec:
                            def run(_s, *a, **k):
                                return res
                        return _Exec()
                return _Mod()
            return reel(nom)

        return mock.patch.object(run_export, "_cadre", side_effect=faux)

    def test_email_vide_leve_AuteurIndisponible_sous_classe_de_RunExportError(self) -> None:
        # MUTATION : `empreinte_auteur` lève `RunExportError` nu -> assertRaises
        # (AuteurIndisponible) ne l'attrape pas, l'exception se propage, rouge.
        with self.assertRaises(run_export.AuteurIndisponible):
            run_export.empreinte_auteur("")
        # isinstance : aucun banc attrapant RunExportError ne casse (le contrat).
        self.assertTrue(issubclass(run_export.AuteurIndisponible, RunExportError))
        self.assertIsInstance(run_export.AuteurIndisponible(), RunExportError)
        self.assertIn("AuteurIndisponible", run_export.__all__)
        doc = (run_export.AuteurIndisponible.__doc__ or "").lower()
        self.assertIn("reportable", doc, "le contrat (REPORTABLE) doit être écrit")

    def test_git_absent_code_127_nomme_la_cause_reelle(self) -> None:
        # MUTATION : `_email_git` rend '' sur non-ok -> empreinte_auteur('') lève
        # « user.email absent » (cause MASQUÉE), le message ne porte plus '127'.
        res = self._resultat(127, stderr="git: command not found")
        with self._seam_executor(res):
            with self.assertRaises(RunExportError) as ctx:
                run_export._email_git(depuis=self.racine)
        msg = str(ctx.exception)
        self.assertIn("127", msg, "le message doit NOMMER le code de retour réel")
        self.assertIn("command not found", msg, "le stderr réel doit être nommé")
        self.assertNotIsInstance(
            ctx.exception, run_export.AuteurIndisponible,
            "une panne d'infra n'est PAS reportable (pas une AuteurIndisponible)",
        )
        # T-00000695/696 : le TYPE porte la panne jusqu'au drain, qui ne voit qu'un
        # `RunExportError` et doit la NOMMER sans la prêter aux autres causes.
        # MUTATION (`raise RunExportError(` dans `_email_git`) : cet assert rougit.
        self.assertIsInstance(ctx.exception, run_export.PanneInfrastructure)
        self.assertIn("PanneInfrastructure", run_export.__all__)

    def test_depot_corrompu_code_128_nomme_la_cause_reelle(self) -> None:
        res = self._resultat(128, stderr="fatal: not a git repository")
        with self._seam_executor(res):
            with self.assertRaises(RunExportError) as ctx:
                run_export._email_git(depuis=self.racine)
        msg = str(ctx.exception)
        self.assertIn("128", msg)
        self.assertIn("not a git repository", msg)
        self.assertNotIsInstance(ctx.exception, run_export.AuteurIndisponible)

    def test_timeout_code_124_est_nomme(self) -> None:
        res = self._resultat(124, stderr="", expire=True)
        with self._seam_executor(res):
            with self.assertRaises(RunExportError) as ctx:
                run_export._email_git(depuis=self.racine)
        msg = str(ctx.exception)
        self.assertIn("124", msg)
        self.assertIn("timeout=True", msg, "le timeout doit être nommé")
        self.assertNotIsInstance(ctx.exception, run_export.AuteurIndisponible)

    def test_email_ok_mais_vide_reste_traite_par_empreinte_auteur(self) -> None:
        # L'email VIDE (git OK, stdout '') n'est PAS une panne : `_email_git` rend
        # '' et c'est `empreinte_auteur` qui lève `AuteurIndisponible` (chemin
        # INCHANGÉ). MUTATION (empreinte n'est plus appelée / lève autre chose) :
        # l'un des deux asserts rougit.
        res = self._resultat(0, stderr="")  # ok, stdout=""
        with self._seam_executor(res):
            rendu = run_export._email_git(depuis=self.racine)
        self.assertEqual(rendu, "", "git OK mais vide -> '' laissé à empreinte_auteur")
        with self.assertRaises(run_export.AuteurIndisponible):
            run_export.empreinte_auteur(rendu)

    def test_F1_cle_non_definie_rc1_vide_rend_chaine_vide_puis_defere(self) -> None:
        # F1 (BLOQUANT, binôme + bissection critic-fable, mesuré 2026-09-22) : `git
        # config user.email` sur une clé NON DÉFINIE rend rc=1 avec stdout ET stderr
        # VIDES — cas NOMINAL « auteur absent », REPORTABLE. `_email_git` doit rendre ""
        # (chemin « vide traité par empreinte_auteur »), et `empreinte_auteur("")` lever
        # `AuteurIndisponible` (report, PAS panne). MUTATION (code fautif d'origine, `if
        # not resultat.ok` NU sans le filtre F1) : `_email_git` LÈVE une
        # `PanneInfrastructure` (sous-classe de `RunExportError`, jamais une
        # `AuteurIndisponible`) -> le premier assert rougit, `empreinte_auteur` n'est jamais atteinte (c'est
        # exactement la régression F1 qui tuait `tasks.py` sans identité git).
        res = self._resultat(1, stderr="")  # rc=1, stdout="", stderr="" -> clé absente
        with self._seam_executor(res):
            rendu = run_export._email_git(depuis=self.racine)
        self.assertEqual(rendu, "", "clé absente (rc=1, vide) -> '' laissé à empreinte_auteur")
        with self.assertRaises(run_export.AuteurIndisponible):
            run_export.empreinte_auteur(rendu)
        # BORNE : un rc=1 AVEC stderr (vraie erreur git) N'est PAS le cas nominal ->
        # il LÈVE encore (le filtre F1 ne mange que le cas vide).
        with self._seam_executor(self._resultat(1, stderr="error: something")):
            with self.assertRaises(RunExportError) as ctx:
                run_export._email_git(depuis=self.racine)
        self.assertNotIsInstance(
            ctx.exception, run_export.AuteurIndisponible,
            "rc=1 AVEC stderr = erreur git, pas un auteur absent",
        )

    def test_couture_executor_introuvable_leve_PanneInfrastructure(self) -> None:
        """T-00000695/696 (exec-critic, MAJEUR) — la couture `cadre.executor`
        INTROUVABLE est une panne, pas un refus d'export ordinaire. DEUX variantes,
        les deux mesurées avant correction :
          · `_cadre` lève son `RunExportError` défensif (branche `spec is None`)
            -> sortait NU, et le drain disait « DIFFÉRÉ … conservé pour rejeu » ;
          · paquet `cadre` absent ET fichier de repli absent -> le repli PAR
            CHEMIN lève `FileNotFoundError` -> sortait NU aussi, ni `RunExportError`
            ni panne : « échec inattendu » au drain, construction du store tuée.
        MUTATION (retirer l'enveloppe `try/except` autour de `_cadre("executor")`
        dans `_email_git`) : les deux variantes lèvent leur exception d'origine,
        `assertRaises(PanneInfrastructure)` ne l'attrape pas, rouge."""
        reel = run_export._cadre

        def cadre_defensif(nom):
            if nom == "executor":
                raise RunExportError("module cadre.executor introuvable (banc)")
            return reel(nom)

        def cadre_import_error(nom):
            if nom == "executor":
                raise ImportError("dépendance du repli par chemin absente (banc)")
            return reel(nom)

        variantes = {
            "branche défensive de _cadre": (
                lambda: mock.patch.object(run_export, "_cadre", side_effect=cadre_defensif),
                RunExportError,
            ),
            "paquet absent + repli par chemin absent": (
                lambda: _couture_executor_absente(),
                FileNotFoundError,
            ),
            "ImportError au chargement": (
                lambda: mock.patch.object(run_export, "_cadre", side_effect=cadre_import_error),
                ImportError,
            ),
        }
        for nom, (couture, cause_attendue) in variantes.items():
            with self.subTest(variante=nom):
                with couture():
                    with self.assertRaises(run_export.PanneInfrastructure) as ctx:
                        run_export._email_git(depuis=self.racine)
                self.assertNotIsInstance(
                    ctx.exception, run_export.AuteurIndisponible,
                    "une couture introuvable n'est PAS un auteur absent (reportable)",
                )
                self.assertIn("couture cadre.executor INTROUVABLE", str(ctx.exception),
                              "la couture est NOMMÉE, et dite INTROUVABLE")
                self.assertIsInstance(
                    ctx.exception.__cause__, cause_attendue,
                    "la cause d'origine reste CHAÎNÉE (`from exc`)",
                )

    def test_couture_executor_en_ERREUR_n_est_pas_dite_introuvable(self) -> None:
        """exec-critic (T-00000695/696, second tour) — un `except Exception` unique
        étiquetait « INTROUVABLE » une erreur de programmation d'un module TROUVÉ :
        il envoyait chercher un fichier présent. Deux variantes : un module sans
        `LocalExecutor` (`AttributeError`), un exécuteur dont le constructeur lève
        (`TypeError`). Elles restent une `PanneInfrastructure` — git n'a pas pu être
        lancé — mais le message dit « en ERREUR (<type>) », cause chaînée.
        MUTATION (clause unique `except Exception` étiquetée INTROUVABLE) : « en
        ERREUR » absent, rouge."""
        reel = run_export._cadre

        class _SansExecuteur:
            pass

        class _ExecuteurQuiLeve:
            class LocalExecutor:
                def __init__(self) -> None:
                    raise TypeError("constructeur cassé (banc)")

        variantes = (
            ("module sans LocalExecutor", _SansExecuteur, AttributeError),
            ("constructeur qui lève", _ExecuteurQuiLeve, TypeError),
        )
        for nom, module, cause in variantes:
            def faux(n, _m=module):
                return _m if n == "executor" else reel(n)

            with self.subTest(variante=nom):
                with mock.patch.object(run_export, "_cadre", side_effect=faux):
                    with self.assertRaises(run_export.PanneInfrastructure) as ctx:
                        run_export._email_git(depuis=self.racine)
                message = str(ctx.exception)
                self.assertIn(f"couture cadre.executor en ERREUR ({cause.__name__}", message)
                self.assertNotIn("INTROUVABLE", message, "un module TROUVÉ n'est pas introuvable")
                self.assertIsInstance(ctx.exception.__cause__, cause, "cause CHAÎNÉE")


def _couture_executor_absente():
    """`cadre.executor` introuvable PAR LES DEUX BRANCHES de `_cadre` : le paquet
    installé est masqué (`sys.modules["cadre"] = None` fait échouer l'import), le
    repli par chemin pointe sur un dossier qui n'existe pas, et le mémo ne porte
    plus `executor`. Tout est restauré à la sortie (`ExitStack` de `patch`)."""
    from contextlib import ExitStack

    pile = ExitStack()
    # `cadre.executor` masqué AUSSI : déjà chargé par un test antérieur (porte
    # complète), `import_module` le rendait depuis le cache sans consulter
    # `cadre` — la couture restait PRÉSENTE, git tournait, rouge @ 1bc9933.
    pile.enter_context(mock.patch.dict(sys.modules, {"cadre": None, "cadre.executor": None}))
    pile.enter_context(mock.patch.dict(run_export._MODULES_CADRE))
    run_export._MODULES_CADRE.pop("executor", None)
    pile.enter_context(
        mock.patch.object(run_export, "_SRC_CADRE", Path(tempfile.gettempdir()) / "cadre-absent-banc")
    )
    return pile


def _couture_ledger_store_absente():
    """`cadre.ledger.store` (et `cadre.workspace`) introuvables par les DEUX
    branches de `_cadre` — patron de `_couture_executor_absente` : paquet masqué
    dans `sys.modules`, repli par chemin pointé sur un dossier VIDE, mémo sans ces
    deux entrées. Tout est restauré à la sortie (T-00000770, A-C1)."""
    from contextlib import ExitStack

    pile = ExitStack()
    pile.enter_context(mock.patch.dict(sys.modules, {
        "cadre": None, "cadre.ledger": None, "cadre.ledger.store": None,
        "cadre.workspace": None}))
    pile.enter_context(mock.patch.dict(run_export._MODULES_CADRE))
    run_export._MODULES_CADRE.pop("ledger.store", None)
    run_export._MODULES_CADRE.pop("workspace", None)
    pile.enter_context(
        mock.patch.object(run_export, "_SRC_CADRE", Path(tempfile.gettempdir()) / "cadre-absent-banc")
    )
    return pile


#: La sonde de F3 (T-00000770) : `run_export` sous `-I`, `cadre` et `cadre.*` REFUSÉS par un chercheur en tête
#: de `sys.meta_path` (le parent vendor les exposerait) : `_cadre` passe par son repli PAR CHEMIN.
_SONDE_F3 = r'''
import importlib.util, json, os, sqlite3, sys
from pathlib import Path
class _SansCadre:
    def find_spec(nom, *_):
        if nom.split(".")[0] == "cadre": raise ModuleNotFoundError(f"cadre refusé par la sonde F3 : {nom}", name=nom)
sys.meta_path.insert(0, _SansCadre); sys.path.append(sys.argv[1])
try: import cadre; arme = False
except ModuleNotFoundError: arme = True
from agentic_v3.db import run_export as r
d = Path(sys.argv[2]).resolve()
tiers = d / "tiers.db"
c = sqlite3.connect(str(tiers))
c.execute("CREATE TABLE t(x)")
c.commit()
c.close()
os.symlink(tiers, d / "lien.db")
st, wsm = r._cadre("ledger.store"), r._cadre("workspace")
rapport = {"arme": arme, "fichiers": [st.__file__, wsm.__file__]}
try:
    st.ouvrir_sans_suivre(wsm.Workspace(d), "lien.db", creer=False)
    rapport["primitive"] = None
except ValueError as exc:
    rapport["primitive"] = str(exc)
try:
    r._ouvrir_base_sqlite(d / "lien.db")
    rapport["site"] = None
except r.RunExportError as exc:
    rapport["site"] = str(exc)
print(json.dumps(rapport))
'''


#: Sonde de F2 (T-00000770) : un `cadre` PÉRIMÉ (`ledger.store` sans primitive) en tête de `sys.path`, le paquet de
#: l'arbre complet — retente PAR CHEMIN ; si cette copie échoue aussi, `PanneInfrastructure` nomme le périmé.
_SONDE_F2_PERIME = r'''
import json, sqlite3, sys
from pathlib import Path
faux, racine, d = (Path(a) for a in sys.argv[1:4])
sys.path.insert(0, str(faux))
import cadre.ledger.store as perime
arme = hasattr(perime, "connect") and not hasattr(perime, "ouvrir_sans_suivre")
sys.path.append(str(racine))
from agentic_v3.db import run_export as r
c = sqlite3.connect(str(d / "base.db")); c.execute("CREATE TABLE t(x)"); c.commit(); c.close()
rapport = {"arme": arme, "perime": [perime.__name__, perime.__file__]}
try:
    r._ouvrir_base_sqlite(d / "base.db").close()
    rapport["ok"] = [True, r._MODULES_CADRE["ledger.store"].__file__]
except r.RunExportError as exc:
    rapport["ok"] = [False, f"{type(exc).__name__}: {exc}"]
r._MODULES_CADRE.pop("ledger.store", None)
r._SRC_CADRE = d / "vide"
try:
    r._ouvrir_base_sqlite(d / "base.db").close()
    rapport["echec"] = None
except r.PanneInfrastructure as exc:
    rapport["echec"] = str(exc)
print(json.dumps(rapport))
'''


class TestCouturePerimeeT770(unittest.TestCase):
    """F2 (T-00000770) : un `cadre` installé PÉRIMÉ ne coupe pas la couture quand le paquet de l'arbre est là."""

    def test_un_paquet_cadre_perime_est_rattrape_par_la_copie_par_chemin_t770(self) -> None:
        """F2 — un paquet `cadre` installé antérieur à T-00000770 (sans la
        primitive) ne coupe pas `_ouvrir_base_sqlite` quand le paquet de l'arbre est
        là : la couture retente PAR CHEMIN et ouvre par la copie de
        `<_SRC_CADRE>/ledger/store.py`. Si cette copie échoue AUSSI :
        `PanneInfrastructure` qui nomme le module périmé, son `__name__` ET son
        `__file__`. Rouge avant F2. Mord : repli retiré."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp).resolve()
            ledger = t / "faux" / "cadre" / "ledger"
            ledger.mkdir(parents=True)
            (ledger.parent / "__init__.py").write_text("", encoding="utf-8")
            (ledger / "__init__.py").write_text("", encoding="utf-8")
            (ledger / "store.py").write_text(
                "import sqlite3\n\n\ndef connect(chemin, **_):\n"
                "    return sqlite3.connect(str(chemin))\n", encoding="utf-8")
            d = t / "d"
            d.mkdir()
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "CADRE_STATE_DIR": str(t / "state"),
                   "CADRE_PROJECT_ROOT": str(t / "racine"),
                   "AGENTS_EVENTS_DIR": str(t / "events")}
            fini = subprocess.run(
                [sys.executable, "-I", "-c", _SONDE_F2_PERIME, str(t / "faux"), str(TestCliFormeDocumentee.PARENT_IMPORT), str(d)],
                cwd=str(d), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        rapport = json.loads(fini.stdout.strip().splitlines()[-1])
        self.assertTrue(rapport["arme"], "banc non armé : le paquet périmé n'est pas importé")
        ouvert, detail = rapport["ok"]
        self.assertTrue(ouvert, detail)
        self.assertEqual(detail, str(run_export._SRC_CADRE / "ledger" / "store.py"))
        nom_perime, fichier_perime = rapport["perime"]
        self.assertIsNotNone(rapport["echec"], "_ouvrir_base_sqlite a ouvert sans primitive")
        self.assertIn(nom_perime, rapport["echec"])
        self.assertIn(fichier_perime, rapport["echec"])


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent (R3 de T-00000759)")
class TestCoutureLedgerStoreT770(unittest.TestCase):
    """T-00000770 — `_ouvrir_base_sqlite` et `agentic_v3.db.schema` ouvrent par la
    primitive de `cadre.ledger.store`, résolue par la couture `_cadre` (paquet,
    puis chemin) ; une couture INTROUVABLE est une `PanneInfrastructure` qui la
    nomme, jamais un refus de lien ni une création."""

    def test_couture_ledger_store_introuvable_leve_PanneInfrastructure_t770(self) -> None:
        """A-C1 — couture introuvable par les deux branches : `create_tables`,
        `get_db_connection` et `_ouvrir_base_sqlite` lèvent `PanneInfrastructure`
        nommant `cadre.ledger.store`, et `create_tables` ne crée rien. Rouge sur
        BASE (aucune couture : `create_tables` créait le store)."""
        from agentic_v3.db import schema  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp).resolve()
            existant = d / "existant.db"
            create_tables(existant)
            neuf = d / "neuf.db"
            with _couture_ledger_store_absente():
                for nom, appel in (("create_tables", lambda: create_tables(neuf)),
                                   ("get_db_connection",
                                    lambda: schema.get_db_connection(existant)),
                                   ("_ouvrir_base_sqlite",
                                    lambda: run_export._ouvrir_base_sqlite(existant))):
                    with self.subTest(site=nom):
                        with self.assertRaises(run_export.PanneInfrastructure) as ctx:
                            appel()
                        self.assertIn("cadre.ledger.store", str(ctx.exception))
            self.assertFalse(neuf.exists(), "create_tables a créé le store sans couture")

    def test_la_couture_par_chemin_refuse_un_lien_hors_paquet_t770(self) -> None:
        """F3 — dans un enfant `sys.executable -I` où `cadre` est INTROUVABLE
        (armement asserté), `_cadre("ledger.store")` et `_cadre("workspace")`
        chargés PAR CHEMIN depuis `_SRC_CADRE` : la primitive refuse un lien
        (« lien symbolique »), et `_ouvrir_base_sqlite` le traduit en
        `RunExportError` « refus d'ouverture : … ». BASE : `ouvrir_sans_suivre`
        absent (`AttributeError`)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp).resolve()
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                   "CADRE_STATE_DIR": str(d / "state"),
                   "CADRE_PROJECT_ROOT": str(d / "racine"),
                   "AGENTS_EVENTS_DIR": str(d / "events")}
            fini = subprocess.run([sys.executable, "-I", "-c", _SONDE_F3, str(TestCliFormeDocumentee.PARENT_IMPORT), str(d)],
                                  cwd=str(d), env=env, capture_output=True, text=True,
                                  timeout=120)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        rapport = json.loads(fini.stdout.strip().splitlines()[-1])
        self.assertTrue(rapport["arme"], "banc non armé : `cadre` importable dans l'enfant")
        self.assertEqual([Path(f).name for f in rapport["fichiers"]],
                         ["store.py", "workspace.py"])
        self.assertIsNotNone(rapport["primitive"], "la primitive a suivi le lien")
        self.assertIn("lien symbolique", rapport["primitive"])
        self.assertIsNotNone(rapport["site"], "_ouvrir_base_sqlite a suivi le lien")
        self.assertIn("refus d'ouverture :", rapport["site"])
        self.assertIn("lien symbolique", rapport["site"])


class TestFiletBancNecritPasSousRacineReelle(unittest.TestCase):
    """CORRECTIF C — T-00000696 : `run_export.py` REFUSE LUI-MÊME d'écrire un
    export sous le `runs/` RÉEL quand il est exercé depuis un banc. Trois
    propriétés (refus sous racine réelle depuis un banc ; passage sous un
    `CADRE_PROJECT_ROOT` jetable ; passage en PRODUCTION sous la racine réelle),
    chacune tenue par un témoin — les trois forment la matrice de mutation."""

    def _ligne(self):
        return {
            "ulid": _ULID, "task_id": "T", "agent_role": "run",
            "event_type": "TASK_CREATED", "payload_json": "{}",
            "created_at": "2026-06-01 00:00:00", "operation_id": "opc",
            "event_kind": "TASK_CREATED", "attempt": 0, "predecesseur_ulid": None,
        }

    def test_un_banc_refuse_d_ecrire_sous_le_runs_REEL(self) -> None:
        # SÉCURITÉ DU TÉMOIN (critic-opus T7, T-00000695/696) : la version précédente
        # visait le VRAI `runs/` et ne comptait que sur le filet pour ne rien y
        # écrire — filet muté, elle y aurait écrit (constat du critique, non rejoué
        # ici : le rejouer, c'était écrire dans la surface versionnée). La
        # « racine réelle » est désormais un tmpdir (`_racine_reelle` greffée, ET
        # `CADRE_PROJECT_ROOT` dessus) : le chemin exercé est le même, la vraie
        # surface n'est jamais visée. Que la greffe porte sur la BONNE fonction est
        # tenu par le témoin suivant. MUTATION (garde retirée de
        # `ajouter_a_l_export`) : l'écriture aboutit sous le faux réel, rouge.
        with tempfile.TemporaryDirectory() as tmp:
            faux_reel = Path(tmp) / "depot"
            faux_reel.mkdir()
            auteur = "0000000000000000"
            copie = "filet-c-refuse"
            cible = faux_reel / "runs" / auteur / copie
            with mock.patch.dict(os.environ):
                os.environ["CADRE_PROJECT_ROOT"] = str(faux_reel)
                os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "state")
                os.environ["PYTEST_CURRENT_TEST"] = "banc::refuse"  # signal de banc explicite
                with mock.patch.object(run_export, "_racine_reelle", return_value=faux_reel):
                    with self.assertRaises(RunExportError) as ctx:
                        run_export.ajouter_a_l_export(
                            self._ligne(), depuis=faux_reel, copie=copie, auteur=auteur
                        )
            self.assertIn("CADRE_PROJECT_ROOT", str(ctx.exception), "le remède est nommé")
            self.assertFalse(cible.exists(), "aucun dossier créé sous le runs/ « réel »")

    def test_la_racine_reelle_greffee_ailleurs_est_bien_celle_du_depot(self) -> None:
        # Ce que les témoins voisins greffent : sans ce témoin, une `_racine_reelle`
        # qui dériverait (autre `parents[n]`) laisserait la greffe prouver un filet
        # qui ne protège pas le vrai dépôt.
        module = Path(run_export.__file__).resolve()
        attendu = module.parents[4] if module.parents[2].name == "vendor" else module.parents[2]
        self.assertEqual(run_export._racine_reelle(), attendu)

    def test_un_banc_LAISSE_PASSER_sous_un_CADRE_PROJECT_ROOT_jetable(self) -> None:
        # Sous banc mais redirigé vers un tmpdir -> l'écriture aboutit.
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp) / "projet"
            racine.mkdir()
            with mock.patch.dict(os.environ):
                os.environ["CADRE_PROJECT_ROOT"] = str(racine)
                os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "state")
                os.environ["PYTEST_CURRENT_TEST"] = "banc::tmpdir"
                chemin = run_export.ajouter_a_l_export(
                    self._ligne(), depuis=racine, copie="jetable",
                    auteur="0000000000000000",
                )
            self.assertTrue(chemin.is_file(), "une écriture redirigée doit aboutir")
            # sous la racine jetable (comparaison RÉSOLUE : /var -> /private/var sur macOS).
            self.assertTrue(chemin.resolve().is_relative_to(racine.resolve()))

    def test_la_PRODUCTION_hors_banc_passe_sous_la_racine_reelle(self) -> None:
        # LE PLUS IMPORTANT : hors banc (PYTEST_CURRENT_TEST absent), l'écriture
        # sous la racine réelle PASSE — un filet qui bloquerait la production
        # serait pire que le trou. `_racine_reelle` est pointée sur un tmpdir pour
        # ne pas toucher la VRAIE surface tout en exerçant EXACTEMENT ce chemin.
        # MUTATION (garde mord aussi hors banc) : l'écriture est refusée, rouge.
        with tempfile.TemporaryDirectory() as tmp:
            faux_reel = Path(tmp) / "depot"
            faux_reel.mkdir()
            with mock.patch.dict(os.environ):
                os.environ.pop("PYTEST_CURRENT_TEST", None)  # PRODUCTION : pas de banc
                os.environ["CADRE_PROJECT_ROOT"] = str(faux_reel)
                os.environ["CADRE_STATE_DIR"] = str(Path(tmp) / "state")
                with mock.patch.object(run_export, "_racine_reelle", return_value=faux_reel):
                    self.assertFalse(run_export._exercice_depuis_un_banc())
                    chemin = run_export.ajouter_a_l_export(
                        self._ligne(), depuis=faux_reel, copie="prod",
                        auteur="0000000000000000",
                    )
            self.assertTrue(
                chemin.is_file(),
                "une écriture de PRODUCTION sous la racine réelle doit PASSER",
            )


class TestF1SansIdentiteGitBoutEnBout(unittest.TestCase):
    """F1 (BLOQUANT) — bras SANS AUCUNE COUTURE, en SOUS-PROCESSUS. C'est le SEUL
    canal qui aurait rougi : dans un dépôt JETABLE SANS `git user.email` (global et
    system nullés, HOME neuf), `tasks.py new` doit réussir DEUX fois de suite (rc 0),
    les deux tâches créées. À HEAD (avant F1) le 2e `new` partait en Traceback
    `RunExportError` remonté depuis `EventStore.__init__ -> _rejouer_journaux_attente`
    et la tâche n'était PAS créée — mesuré par l'orchestrateur (deux fois) et bissecté
    par critic-fable (rc=1 à HEAD, rc=0 à 9eeb1f4). Aucune écriture ne touche le dépôt
    du kit : tout est ancré sous `CADRE_PROJECT_ROOT` = tmpdir jetable."""

    def test_deux_new_de_suite_sans_git_email_reussissent(self) -> None:
        depot_kit = run_export._racine_depot()
        tasks_py = depot_kit / ".agents" / "bin" / "tasks.py"
        self.assertTrue(tasks_py.is_file(), "tasks.py introuvable dans le dépôt du kit")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            proj = base / "proj"; proj.mkdir()
            state = base / "state"; state.mkdir()
            home = base / "home"; home.mkdir()  # pas de ~/.gitconfig hérité
            env = _env_sans_git()  # `git init` HONORE `GIT_DIR` : jamais hérité ici
            # B2 (binôme, 3e tour) : ce `pop` DÉSARMAIT le filet de T-00000696 dans
            # un sous-processus qui écrit POUR DE VRAI et qui, étant un autre
            # processus, ne peut pas greffer `_racine_reelle`. Il était inutile —
            # le filet laisse passer toute écriture redirigée par
            # `CADRE_PROJECT_ROOT`, ce qu'un témoin voisin prouve — et il retirait
            # la seule protection restante si cette redirection venait à sauter.
            # C'est la contamination que T-696 a payée, réintroduite par le témoin
            # qui la corrigeait. Le filet reste ARMÉ.
            env["PYTEST_CURRENT_TEST"] = "banc::F1-sous-processus"
            env.pop("CLAUDE_PROJECT_DIR", None)
            env.update({
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                "HOME": str(home),
                "CADRE_PROJECT_ROOT": str(proj),
                "CADRE_STATE_DIR": str(state),
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            subprocess.run(
                ["git", "init", "-q", str(proj)], env=env, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            # Pré-condition : la clé est ABSENTE (rc=1, stdout ET stderr VIDES) — c'est
            # EXACTEMENT le cas nominal que F1 route vers le report, pas la panne.
            precond = subprocess.run(
                ["git", "config", "user.email"], cwd=str(proj), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(precond.returncode, 1, "pré-condition : user.email ABSENT")
            self.assertEqual(precond.stdout.strip(), "")
            self.assertEqual(precond.stderr.strip(), "")

            def _new(titre: str):
                return subprocess.run(
                    [sys.executable, "-B", str(tasks_py), "--root", str(proj),
                     "new", titre, "--owner", "dev-multi"],
                    env=env, cwd=str(proj),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )

            r1 = _new("Tache F1 un")
            r2 = _new("Tache F1 deux")
            self.assertEqual(
                r1.returncode, 0, f"1er `new` rc={r1.returncode}\nSTDERR:\n{r1.stderr}"
            )
            self.assertEqual(
                r2.returncode, 0, f"2e `new` rc={r2.returncode}\nSTDERR:\n{r2.stderr}"
            )
            # MUTATION (F1 retirée) : le 2e `new` remonte un Traceback (mesuré).
            self.assertNotIn(
                "Traceback", r1.stderr + r2.stderr,
                "aucune exception non rattrapée ne doit remonter (régression F1)",
            )
            # Les deux tâches sont au board du dépôt JETABLE (jamais celui du kit).
            board = proj / ".agents" / "state" / "board" / "TASKS.json"
            self.assertTrue(board.is_file(), "le board du dépôt jetable doit exister")
            taches = json.loads(board.read_text(encoding="utf-8"))["tasks"]
            titres = [t.get("task") for t in taches]
            self.assertIn("Tache F1 un", titres, "1re tâche créée")
            self.assertIn("Tache F1 deux", titres, "2e tâche créée (celle que HEAD perdait)")


# --- T-00000691 : la reconstruction depuis runs/ rebâtit AUSSI le pont board, en
# UNE transaction, se déclenche SEULE à l'ouverture d'une base vide, CONTIENT ce
# qu'elle lit, tient trois filets (S, R, N) et REFUSE d'écrire tant qu'une
# reconstruction due n'est pas faite. Chaque témoin nomme la mutation qui le rougit.

#: Les clés que le résumé porte TOUJOURS (§ 2 point 1 du plan). Passe de revue
#: (S-00002519) : `failed_v3_vers_board` (FAILED d'une commande V3 → board, normal,
#: séparé des anomalies) — UN ajout, aucune clé retirée. Une `OperationalError` au
#: rejeu d'un intent n'a PAS de compteur : c'est une panne système, elle AVORTE
#: (addendum exec-critic, témoin T36).
_CLES_RESUME_691 = {
    "applied", "total", "ignores", "malformes", "echecs", "lignes_illisibles",
    "fichiers_illisibles", "fichiers_trop_gros", "avortee", "differee",
    "saute_non_vide", "pont_intents", "pont_ecartes", "pont_deja_vus",
    "pont_remplaces", "pont_non_rebati", "faux_failed", "echecs_sans_failed",
    "failed_hors_intent", "auteurs_rejoues", "failed_v3_vers_board", "divergentes", "divergentes_ulid",
}

#: Les quatre tables que la reconstruction doit rendre ÉGALES (mêmes requêtes que
#: les critères C-P / C-C du plan).
_TABLES_691 = {
    "events": "SELECT ulid,task_id,event_type,payload_json,operation_id,event_kind,attempt FROM events_ledger",
    "mapping": "SELECT board_task_id,v3_task_id,create_operation_id,tombstoned FROM task_board_mapping",
    "projections": "SELECT task_id,req_id,spec_version,status,current_assignee,code_diff,retry_count,is_blocked FROM task_projections",
    "inbox": "SELECT operation_id,event_kind,attempt,payload_json,effect_json FROM board_sync_inbox",
}


def _pont_en_panne(store, cursor, redaction):
    """Greffe de `_rebatir_pont` : lève APRÈS avoir effacé (le pire moment)."""
    cursor.execute("DELETE FROM board_sync_inbox")
    cursor.execute("DELETE FROM task_board_mapping WHERE v3_task_id GLOB 'BOARD:*'")
    raise RuntimeError("pont greffe en panne")


class _ReconstructionFixture(_IntegrationFixture):
    """Base des témoins T-00000691. `_base_defaut()` est EXACTEMENT la base que
    `EventStore(project_root=racine)` ouvre (partition marquable) — le seul
    déclencheur de la reconstruction d'office."""

    def _es(self):
        import agentic_v3.db.event_store as es

        return es

    def _base_defaut(self) -> Path:
        return Path(run_export.state_project(self.racine)) / "run" / "v3_event_store.db"

    def _ouvrir_defaut(self):
        """`(store, stderr)` de la construction au chemin par défaut."""
        err = io.StringIO()
        with redirect_stderr(err):
            store = self._es().EventStore(project_root=self.racine)
        return store, err.getvalue()

    def _store_explicite(self, nom: str):
        base = self.state / nom
        base.parent.mkdir(parents=True, exist_ok=True)
        return self._es().EventStore(base, project_root=self.racine)

    def _espionner_reconstruire(self):
        """`(patch, resumes)` : chaque résumé rendu par `_reconstruire` est retenu."""
        es = self._es()
        vrai = es.EventStore._reconstruire
        resumes: list = []

        def espion(store, *args, **kwargs):
            resume = vrai(store, *args, **kwargs)
            resumes.append(resume)
            return resume

        return mock.patch.object(es.EventStore, "_reconstruire", espion), resumes

    @staticmethod
    def _snap(task_id: str, state: str, stage: str = "") -> dict:
        return {"id": task_id, "state": state, "task": "Tache", "owner": "dev-multi",
                "stage": stage, "updated": "2026-09-26"}

    @staticmethod
    def _intent(op: str, *, before, after, kind: str = "BOARD_TASK_OBSERVED",
                attempt: int = 0) -> dict:
        task_id = (after or before or {})["id"]
        return {"operation_id": op, "event_kind": kind, "affected_task_ids": [task_id],
                "before": before, "after": after, "revision_sha256": "0" * 64,
                "attempt": attempt}

    def _intent_remplace(self) -> dict:
        return self._intent(
            "op-remplace", before=self._snap("T-1", "running", "dev"),
            after=self._snap("T-1", "pending"), kind="BOARD_RUNNING_REPLACED",
        )

    def _peupler_A(self):
        """Store A EXPLICITE : T-1 créée en cours (`running`), exportée sous runs/."""
        a = self._store_explicite("a.db")
        a.consume_board_intent(
            self._intent("op-cree", before=None, after=self._snap("T-1", "running", "dev"))
        )
        return a

    @staticmethod
    def _ligne(ulid: str, *, task_id: str = "T-R", event_type: str = "TASK_CREATED",
               payload=None, op=None, agent_role: str = "run", attempt=0) -> dict:
        if isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = json.dumps(
                {"req_id": "R"} if payload is None else payload,
                ensure_ascii=False, sort_keys=True,
            )
        return {"ulid": ulid, "task_id": task_id, "agent_role": agent_role,
                "event_type": event_type, "payload_json": payload_json,
                "operation_id": op or f"op-{ulid}", "event_kind": event_type,
                "attempt": attempt, "predecesseur_ulid": None,
                "created_at": "2026-09-26 00:00:00"}

    def _ligne_intent(self, ulid: str, intent: dict) -> dict:
        return self._ligne(
            ulid, task_id=intent["affected_task_ids"][0], event_type=intent["event_kind"],
            payload=json.dumps(intent, ensure_ascii=False, sort_keys=True),
            op=intent["operation_id"], agent_role="BoardBridge",
            attempt=intent.get("attempt", 0),
        )

    def _ecrire_runs(self, lignes, *, auteur: str = "auteurB", copie: str = "copieB") -> Path:
        dossier = self.racine / "runs" / auteur / copie
        dossier.mkdir(parents=True, exist_ok=True)
        fichier = dossier / f"{run_export._mois_de_ulid(lignes[0]['ulid'])}.jsonl"
        with fichier.open("a", encoding="utf-8") as fh:
            for ligne in lignes:
                fh.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return fichier

    @staticmethod
    def _ulids(n: int) -> list:
        return [run_export.nouvel_ulid() for _ in range(n)]

    def _tables(self, db: Path) -> dict:
        conn = sqlite3.connect(str(db))
        try:
            return {k: set(conn.execute(q).fetchall()) for k, q in _TABLES_691.items()}
        finally:
            conn.close()

    def _scalaire(self, db: Path, requete: str, params=()):
        conn = sqlite3.connect(str(db))
        try:
            return conn.execute(requete, params).fetchone()[0]
        finally:
            conn.close()

    def _compter_type(self, db: Path, event_type: str) -> int:
        return int(self._scalaire(
            db, "SELECT COUNT(*) FROM events_ledger WHERE event_type=?", (event_type,)
        ))

    def _journaux(self) -> list:
        return run_export.lister_journaux_attente(depuis=self.racine)

    @staticmethod
    def _canon(chemin) -> Path:
        """Graphie comparable d'un chemin SANS résoudre son DERNIER composant — un
        lien reste le lien. Seul le parent est résolu (`/var` → `/private/var` sous
        macOS : la racine de `runs/` passe par `cadre.paths`, qui la canonise)."""
        p = Path(os.fsdecode(chemin))
        return Path(os.path.realpath(p.parent)) / p.name

    def _espionner_ouvertures(self, leve_sur=None):
        """`(patch, ouverts)` : chaque `os.open` du PROCESSUS (la lecture vit dans
        `run_export` depuis la passe 3) est retenu sous sa forme `_canon`, puis
        délégué. `leve_sur` (chemin) lève `AssertionError` AU LIEU d'ouvrir — un
        FIFO bloquerait."""
        vrai = os.open
        ouverts: list = []
        cible = self._canon(leve_sur) if leve_sur is not None else None
        canon = self._canon

        def espion(chemin, *args, **kwargs):
            if not isinstance(chemin, int):
                vu = canon(chemin)
                ouverts.append(vu)
                if cible is not None and vu == cible:
                    raise AssertionError(f"{chemin} a été OUVERT")
            return vrai(chemin, *args, **kwargs)

        return mock.patch.object(os, "open", espion), ouverts

    def _ecrire_fichier_export(self, chemin: Path, lignes) -> Path:
        """Écrit `lignes` (objets) en JSONL à `chemin` — hors `runs/` si voulu."""
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lignes),
            encoding="utf-8",
        )
        return chemin

    def _ulid_en_base(self, db: Path, ulid: str) -> bool:
        return bool(self._scalaire(
            db, "SELECT COUNT(*) FROM events_ledger WHERE ulid=?", (ulid,)))

    def _dehors(self, nom: str) -> Path:
        """Un dossier HORS de la racine du projet (le « secret » d'un attaquant)."""
        chemin = Path(self._tmp.name) / nom
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin


class TestReconstructionRebatitLePont(_ReconstructionFixture):
    """Phase 2 : le pont board (liens, projections `BOARD:*`, inbox) est reprojeté
    depuis les intents, par ordre ULID, dans la MÊME transaction."""

    def test_T1_clone_reconstruit_puis_running_replaced_applique_sans_FAILED(self) -> None:
        # M1 : sans `_rebatir_pont` → aucun lien → `replacement-without-link` → 1 FAILED.
        self._peupler_A()
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["avortee"], 0)
        effet = b.consume_board_intent(self._intent_remplace())
        self.assertTrue(effet["applied"], effet)
        self.assertEqual(self._compter_type(self.state / "b.db", "BOARD_COMMAND_FAILED"), 0)
        self.assertNotIn("BOARD_COMMAND_FAILED", self._texte_export(), "un FAILED a été EXPORTÉ")

    def test_T2_un_intent_deja_reconstruit_rend_l_effet_de_l_inbox(self) -> None:
        # M2 : sans l'insertion dans l'inbox → le rejeu réécrit l'événement →
        # `IntegrityError` sur l'identité durable.
        self._peupler_A()
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        avant = self._compter(self.state / "b.db")
        effet = b.consume_board_intent(
            self._intent("op-cree", before=None, after=self._snap("T-1", "running", "dev"))
        )
        self.assertTrue(effet["applied"])
        self.assertEqual(effet["v3_task_id"], "BOARD:op-cree")
        self.assertEqual(self._compter(self.state / "b.db"), avant, "événements inchangés")

    def test_T3_base_NON_vide_reconstruite_egale_base_vide_reconstruite(self) -> None:
        # M3 : sans les trois DELETE → la dérive de A survit (inbox déjà vue).
        # M3b (critic-fable, S-00002518) : `_reduce_board_intent` SAUTÉ au rejeu → A
        # et B rebâties restent ÉGALES ENTRE ELLES (toutes deux sans lien ni
        # projection board) ; seule la comparaison au VIVANT, capturé AVANT la
        # dérive, rougit.
        a = self._peupler_A()
        a.consume_board_intent(self._intent(
            "op-t2", before=None, after=self._snap("T-2", "pending")))
        base_a = self.state / "a.db"
        vivant = self._tables(base_a)
        self.assertTrue(vivant["mapping"] and vivant["inbox"],
                        "non-vacuité : le vivant porte un pont")
        conn = sqlite3.connect(str(base_a))
        conn.execute("UPDATE task_projections SET status='BLOCKED' WHERE task_id GLOB 'BOARD:*'")
        conn.commit()
        conn.close()
        with redirect_stderr(io.StringIO()):
            res_a = a.reconstruire_depuis_exports()
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        self.assertGreater(res_a["pont_remplaces"], 0)
        self.assertEqual(self._tables(base_a), self._tables(self.state / "b.db"))
        self.assertEqual(self._tables(base_a), vivant, "rebâti ≠ vivant d'avant la dérive")

    def test_T4_un_second_appel_a_applied_0_rebatit_encore_le_pont(self) -> None:
        # M4 : appel du pont conditionné à `applied` → second appel ne rebâtit rien.
        self._peupler_A()
        b = self._store_explicite("b.db")
        base_b = self.state / "b.db"
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        premier = self._tables(base_b)
        # Non-vacuité : sans pont rebâti, deux tables vides seraient « égales ».
        self.assertTrue(premier["mapping"] and premier["inbox"], premier)
        conn = sqlite3.connect(str(base_b))
        for requete in (
            "DELETE FROM board_sync_inbox",
            "DELETE FROM task_board_mapping",
            "DELETE FROM task_projections",
        ):
            conn.execute(requete)
        conn.commit()
        conn.close()
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["applied"], 0)
        self.assertEqual(self._tables(base_b), premier)

    def test_T5_un_lien_V3_reserve_puis_lie_survit(self) -> None:
        # M5 : effacer TOUT le mapping → le lien V3:x disparaît.
        self._peupler_A()
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        b.reserve_board_identity("V3:x", "op-lien")
        b.link_board_task("T-9", "V3:x", "op-lien")
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        lien = b.get_board_link("T-9")
        self.assertIsNotNone(lien)
        self.assertEqual(lien["v3_task_id"], "V3:x")

    def test_T6_FAILED_apparie_par_identite_jamais_par_adjacence(self) -> None:
        # M6 : apparier un FAILED à l'intent qui le PRÉCÈDE par ULID → le FAILED de
        # op-x (trié AVANT sa cause) est perdu, celui de op-drain est pris pour op-z.
        t0 = int(time.time() * 1000)
        u_failed, u_x, u_z, u_drain = (run_export.nouvel_ulid(t0 + i) for i in range(4))
        cause = self._intent("op-x", before=None, after=self._snap("T-6", "pending"))
        sans_lien = self._intent("op-z", before=self._snap("T-6z", "running"),
                                 after=self._snap("T-6z", "pending"),
                                 kind="BOARD_RUNNING_REPLACED")
        drain = self._intent("op-drain", before=None, after=self._snap("T-6d", "pending"))
        echec = {"applied": False, "action": "replacement-without-link"}
        self._ecrire_runs([
            self._ligne(u_failed, task_id="T-6", event_type="BOARD_COMMAND_FAILED",
                        agent_role="BoardBridge", op="op-x",
                        payload={"intent": cause, "effect": echec}),
            self._ligne_intent(u_x, cause),
            self._ligne_intent(u_z, sans_lien),
            self._ligne(u_drain, task_id="T-6d", event_type="BOARD_COMMAND_FAILED",
                        agent_role="BoardBridge", op="op-drain",
                        payload={"intent": drain, "effect": echec}),
        ])
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["faux_failed"], 1, res)
        self.assertEqual(res["failed_hors_intent"], 1, res)
        self.assertEqual(res["echecs_sans_failed"], 1, res)

    def test_T7_intents_hors_forme_ecartes_sans_levee(self) -> None:
        # M7 : sans SAVEPOINT/except par intent → une levée avorte tout le lot.
        u = self._ulids(6)
        valide = self._intent("op-ok", before=None, after=self._snap("T-7", "pending"))
        commun = {"task_id": "T-7x", "event_type": "BOARD_TASK_OBSERVED",
                  "agent_role": "BoardBridge"}
        self._ecrire_runs([
            self._ligne(u[0], op="op-vide", payload="{}", **commun),
            self._ligne(u[1], op="op-div", payload=json.dumps(
                {**valide, "operation_id": "autre"}, sort_keys=True), **commun),
            self._ligne_intent(u[2], self._intent(
                "op-etat", before=None, after=self._snap("T-7e", "etat-inconnu"))),
            self._ligne(u[3], op="op-pasjson", payload="pas du json", **commun),
            self._ligne(u[4], op="op-liste", payload="[]", **commun),
            self._ligne_intent(u[5], valide),
        ])
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["avortee"], 0, res)
        self.assertEqual(res["pont_intents"], 6, res)
        self.assertEqual(res["pont_ecartes"], 5, res)
        self.assertIsNotNone(b.get_board_link("T-7"), "l'intent valide est rebâti")
        self.assertIsNone(b.get_board_link("T-7e"), "le savepoint défait l'intent écarté")

    def test_T7b_meme_operation_deux_attempts_est_deja_vu(self) -> None:
        # M7b : le second attempt compté en `pont_ecartes`.
        u0, u1 = self._ulids(2)
        base = self._intent("op-d", before=None, after=self._snap("T-7b", "pending"))
        self._ecrire_runs([
            self._ligne_intent(u0, base),
            self._ligne_intent(u1, {**base, "attempt": 1}),
        ])
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["pont_deja_vus"], 1, res)
        self.assertEqual(res["pont_ecartes"], 0, res)

    def test_T7c_un_FAILED_illisible_est_hors_intent_sans_avorter(self) -> None:
        # M7c : retirer l'except autour du FAILED → `avortee=1`.
        u0, u1 = self._ulids(2)
        valide = self._intent("op-f", before=None, after=self._snap("T-7c", "pending"))
        self._ecrire_runs([
            self._ligne_intent(u0, valide),
            self._ligne(u1, task_id="T-7c", event_type="BOARD_COMMAND_FAILED",
                        agent_role="BoardBridge", op="op-f", payload="pas du json"),
        ])
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["avortee"], 0, res)
        self.assertEqual(res["failed_hors_intent"], 1, res)

    def test_T8a_un_intent_sans_ulid_laisse_le_pont_intact(self) -> None:
        # M8a : sans le contrôle d'ULID NULL → le pont est effacé/rebâti malgré tout.
        b = self._store_explicite("b.db")
        b.consume_board_intent(self._intent("op-n", before=None, after=self._snap("T-8", "pending")))
        base_b = self.state / "b.db"
        conn = sqlite3.connect(str(base_b))
        conn.execute("UPDATE events_ledger SET ulid=NULL WHERE operation_id='op-n'")
        conn.commit()
        conn.close()
        err = io.StringIO()
        with redirect_stderr(err):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["pont_non_rebati"], 1, res)
        self.assertEqual(res["pont_intents"], 0, res)
        self.assertIsNotNone(b.get_board_link("T-8"))
        self.assertIn("pont board NON rebati", err.getvalue())

    def test_T8b_redaction_en_panne_en_appel_explicite(self) -> None:
        # M8b : pont rebâti malgré la rédaction absente → liens effacés, non refaits.
        b = self._store_explicite("b.db")
        b.consume_board_intent(self._intent("op-r", before=None, after=self._snap("T-8b", "pending")))
        u = self._ulids(1)[0]
        self._ecrire_runs([self._ligne(u, task_id="T-8r")])
        es = self._es()
        err = io.StringIO()
        with mock.patch.object(es, "_redaction", side_effect=RuntimeError("redaction greffee")), \
                redirect_stderr(err):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["avortee"], 0, res)
        self.assertEqual(res["pont_non_rebati"], 1, res)
        self.assertEqual(res["applied"], 1, "les événements SONT écrits en appel explicite")
        self.assertIsNotNone(b.get_board_link("T-8b"), "le lien existant reste intact")
        self.assertIn("redaction indisponible", err.getvalue())

    def test_T9_l_effet_reprojete_est_redige_avant_l_inbox(self) -> None:
        # M9 : sans `rediger_arbre` sur l'effet → le secret atteint `effect_json`.
        # BORNE ÉCRITE : les colonnes d'IDENTITÉ (`operation_id`, `v3_task_id`) restent
        # BRUTES par conception (T-00000641) — c'est l'effet ÉCRIT qui est jugé ici.
        u = self._ulids(1)[0]
        intent = self._intent("op-" + FAUX_AWS, before=None, after=self._snap("T-9", "pending"))
        self._ecrire_runs([self._ligne_intent(u, intent)])
        b = self._store_explicite("b.db")
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["pont_intents"], 1, res)
        self.assertEqual(res["pont_ecartes"], 0, res)
        effet = self._scalaire(self.state / "b.db", "SELECT effect_json FROM board_sync_inbox")
        self.assertNotIn(FAUX_AWS, effet)
        self.assertIn("[SECRET", effet)

    def test_T10_les_kinds_d_intent_sont_BOARD_moins_BOARD_COMMAND(self) -> None:
        # M10 : retirer BOARD_RUNNING_REPLACED de `_KINDS_INTENT_BOARD`.
        from agentic_v3.models.events import EventType

        attendu = {e.value for e in EventType
                   if e.value.startswith("BOARD_") and not e.value.startswith("BOARD_COMMAND_")}
        self.assertEqual(set(self._es()._KINDS_INTENT_BOARD), attendu)
        self.assertTrue(attendu, "non-vacuité")

    def test_T11_la_couture_cadre_rend_une_copie_UNIQUE(self) -> None:
        # M11 : sans `sys.modules.get` → la seconde résolution exécute une 2e copie.
        nom_module = "_cadre_ledger_ids_v3"
        with mock.patch.dict(run_export._MODULES_CADRE, clear=True), \
                mock.patch.dict(sys.modules), \
                mock.patch.object(run_export.importlib, "import_module",
                                  side_effect=ImportError("paquet absent (greffe)")):
            sys.modules.pop(nom_module, None)
            a = run_export._cadre("ledger.ids")
            run_export._MODULES_CADRE.clear()  # une autre copie de run_export : mémo vide
            b = run_export._cadre("ledger.ids")
        self.assertIs(a, b)
        self.assertEqual(a.__name__, nom_module, "la branche PAR CHEMIN a bien été prise")

    def test_T12_trois_tables_peuplees_et_une_projection_de_run_exacte(self) -> None:
        # M12a : sans `_apply_projection` en phase 1 → COUNT 0. M12b : sans le DELETE
        # du mapping OU de l'inbox → la ligne fantôme survit.
        self.assertIn("se rebâtissent depuis runs/", "\n".join(run_export._LIGNES_REPRISE))
        a = self._peupler_A()
        a.append_event("T-run", "agent-x", "TASK_CREATED", {"req_id": "REQ-12"}, operation_id="op12")
        b = self._store_explicite("b.db")
        base_b = self.state / "b.db"
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        for requete in (
            "SELECT COUNT(*) FROM task_board_mapping",
            "SELECT COUNT(*) FROM task_projections WHERE task_id GLOB 'BOARD:*'",
            "SELECT COUNT(*) FROM board_sync_inbox",
        ):
            self.assertGreaterEqual(self._scalaire(base_b, requete), 1, requete)
        conn = sqlite3.connect(str(base_b))
        ligne = conn.execute(
            "SELECT COUNT(*), status, current_assignee FROM task_projections WHERE task_id=?",
            ("T-run",),
        ).fetchone()
        self.assertEqual(tuple(ligne), (1, "PENDING", "agent-x"))
        conn.execute("INSERT INTO task_board_mapping (board_task_id, v3_task_id, "
                     "create_operation_id, tombstoned) VALUES ('T-f', 'BOARD:fantome', 'op-f', 0)")
        conn.execute("INSERT INTO board_sync_inbox (operation_id, event_kind, attempt, "
                     "payload_json, effect_json) VALUES ('op-f', 'BOARD_TASK_OBSERVED', 0, '{}', '{}')")
        conn.execute("INSERT INTO task_projections (task_id, req_id, status) "
                     "VALUES ('BOARD:fantome', 'T-f', 'PENDING')")
        conn.commit()
        conn.close()
        with redirect_stderr(io.StringIO()):
            b.reconstruire_depuis_exports()
        for requete in (
            "SELECT COUNT(*) FROM task_board_mapping WHERE board_task_id='T-f'",
            "SELECT COUNT(*) FROM board_sync_inbox WHERE operation_id='op-f'",
            "SELECT COUNT(*) FROM task_projections WHERE task_id='BOARD:fantome'",
        ):
            self.assertEqual(self._scalaire(base_b, requete), 0, requete)

    def test_T20_une_seule_connexion_pour_tout_le_lot(self) -> None:
        # M20 : une connexion PAR LIGNE → 50 appels.
        self._ecrire_runs([self._ligne(u) for u in self._ulids(50)])
        b = self._store_explicite("b.db")
        es = self._es()
        with mock.patch.object(es, "get_db_connection", wraps=es.get_db_connection) as espion, \
                redirect_stderr(io.StringIO()):
            res = b._reconstruire(None, si_vide=False)
        self.assertEqual(res["applied"], 50)
        self.assertEqual(espion.call_count, 1)

    def test_T25_echec_explicite_sur_base_non_vide_ne_bloque_pas(self) -> None:
        # M25 : lever le drapeau sur l'échec EXPLICITE → `append_event` refusé.
        a = self._peupler_A()
        base_a = self.state / "a.db"
        avant = self._tables(base_a)
        es = self._es()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne), \
                redirect_stderr(io.StringIO()):
            res = a.reconstruire_depuis_exports()
        self.assertEqual(res["avortee"], 1)
        self.assertEqual(self._tables(base_a), avant, "base inchangée")
        self.assertFalse(a._reconstruction_bloquee)
        a.append_event("T-25", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op25")


class TestReconstructionAutomatiqueALOuverture(_ReconstructionFixture):
    """S-00002372 : une base VIDE au chemin par défaut se reconstruit d'elle-même,
    pont compris ; tant qu'une reconstruction due n'est pas commitée, l'instance
    n'écrit RIEN."""

    def test_T13_BoardBridge_sur_base_vide_rebatit_puis_applique(self) -> None:
        # M13 : sans l'appel dans `__init__` → pas de lien → FAILED.
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        self._peupler_A()
        err = io.StringIO()
        with redirect_stderr(err):
            bridge = BoardBridge(project_root=self.racine)
        self.assertEqual(bridge.db_path, self._base_defaut())
        self.assertEqual(err.getvalue().count("reconstruite depuis runs/"), 1, err.getvalue())
        self.assertTrue(bridge.consume_board_intent(self._intent_remplace()))
        effet = json.loads(self._scalaire(
            bridge.db_path, "SELECT effect_json FROM board_sync_inbox WHERE operation_id='op-remplace'"))
        self.assertTrue(effet["applied"], effet)
        self.assertEqual(self._compter_type(bridge.db_path, "BOARD_COMMAND_FAILED"), 0)

    def test_T14_une_annonce_a_la_premiere_construction_rien_a_la_seconde(self) -> None:
        # M14 : sans sonde ni re-vérification → la seconde reconstruit encore.
        self._peupler_A()
        _, err1 = self._ouvrir_defaut()
        _, err2 = self._ouvrir_defaut()
        self.assertEqual(err1.count("reconstruite depuis runs/"), 1, err1)
        self.assertNotIn("reconstruite", err2)

    def test_T14c_une_sonde_en_echec_ne_leve_pas_et_bloque_l_ecriture(self) -> None:
        # M14c : retirer l'except du filet S → `EventStore()` lève.
        # M14d : ne pas lever le drapeau dans cet except → `append_event` réussit.
        self._peupler_A()
        base = self._base_defaut()
        es = self._es()
        with mock.patch.object(es.EventStore, "_reconstruction_due",
                               side_effect=OSError("sonde greffee")):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever
        self.assertIn("reconstruction automatique non tentee : OSError: sonde greffee", err)
        self.assertEqual(self._compter(base), 0)
        with self.assertRaises(es.ReconstructionAvorteeError) as cm:
            store.append_event("T-14c", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op14c")
        self.assertIn("NON TENTEE", str(cm.exception))
        self.assertEqual(self._journaux(), [], "aucun journal orphelin")
        self.assertEqual(self._compter(base), 0)
        _, err2 = self._ouvrir_defaut()
        self.assertEqual(err2.count("reconstruite depuis runs/"), 1, err2)
        self.assertGreater(self._compter(base), 0)

    def test_T15_une_base_EXPLICITE_reste_vide(self) -> None:
        # M15 : sans la porte `partition is not None` → la base explicite se remplit.
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)])
        err = io.StringIO()
        with redirect_stderr(err):
            self._store()
        self.assertEqual(self._compter(self._db()), 0)
        self.assertNotIn("reconstruite", err.getvalue())

    def test_T16_une_base_non_vide_est_sauvegardee_puis_completee(self) -> None:
        store, _ = self._ouvrir_defaut()  # pas encore de runs/ : rien de dû
        store.append_event("T-16", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op16")
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)])
        _, err = self._ouvrir_defaut()
        self.assertEqual(self._compter(self._base_defaut()), 3)
        self.assertIn("synchro V3 appliquee", err)
        copies = list((self._base_defaut().parent / "v3-auto-sync" / "backups").glob("*.db"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(self._compter(copies[0]), 1)
    def test_T17_une_base_remplie_sous_le_verrou_est_sautee_sans_bloquer(self) -> None:
        # M17 : ignorer `si_vide` sous le verrou → reconstruit par-dessus.
        # M17b : lever le drapeau sur `saute_non_vide` → `append_event` refusé.
        import threading
        store, _ = self._ouvrir_defaut()  # base créée, vide, runs/ absent
        base = self._base_defaut()
        self._ecrire_runs([self._ligne(u) for u in self._ulids(3)])
        tenu, erreurs = threading.Event(), []

        def tenir() -> None:
            try:
                conn = sqlite3.connect(str(base), timeout=30)
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO events_ledger (task_id, agent_role, event_type, "
                    "payload_json, ulid) VALUES ('T-17', 'run', 'TASK_CREATED', '{}', ?)",
                    (run_export.nouvel_ulid(),),
                )
                tenu.set()
                time.sleep(0.3)
                conn.commit()
                conn.close()
            except Exception as exc:  # pragma: no cover - rapporté ci-dessous
                erreurs.append(exc)
                tenu.set()

        fil = threading.Thread(target=tenir)
        fil.start()
        self.assertTrue(tenu.wait(30))
        patch, resumes = self._espionner_reconstruire()
        err = io.StringIO()
        with patch, redirect_stderr(err):
            store._reconstruire_si_vide()
        fil.join(30)
        self.assertEqual(erreurs, [])
        self.assertEqual(len(resumes), 1, "la sonde n'a pas vu la base vide (fenêtre manquée)")
        self.assertEqual(resumes[0]["saute_non_vide"], 1, resumes[0])
        self.assertEqual(set(resumes[0]), _CLES_RESUME_691)
        self.assertNotIn("AVORTEE", err.getvalue())
        self.assertFalse(store._reconstruction_bloquee)
        store.append_event("T-17b", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op17")
        self.assertEqual(self._compter(base), 2)

    def test_T18_reconstruction_AVANT_le_rejeu_des_journaux(self) -> None:
        # M18 : reconstruire APRÈS le rejeu → la base n'est plus vide, rien de runs/.
        u1, u2, ul = self._ulids(3)
        l1 = self._ligne(u1, task_id="T-18a")
        self._ecrire_runs([l1, self._ligne(u2, task_id="T-18b")])
        run_export.ecrire_journal_attente(self._ligne(ul, task_id="T-18L"), depuis=self.racine)
        run_export.ecrire_journal_attente(l1, depuis=self.racine)
        self._ouvrir_defaut()
        self.assertEqual(self._compter(self._base_defaut()), 3, "runs/ (2) + journal local (1)")
        self.assertEqual(self._journaux(), [])
        banc = self.racine / "runs" / run_export.auteur_courant(depuis=self.racine)
        texte_banc = "".join(p.read_text(encoding="utf-8") for p in banc.rglob("*.jsonl"))
        self.assertIn(ul, texte_banc, "le journal local est exporté")
        self.assertNotIn(u1, texte_banc, "l'événement de runs/ n'est PAS ré-exporté sous l'auteur courant")

    def test_T18b_un_effacement_refuse_au_nettoyage_ne_leve_pas(self) -> None:
        # M18b : retirer l'except du filet N → `PermissionError` sort d'`EventStore()`.
        a = self._store_explicite("a.db")
        a.append_event("T-18c", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op18c")
        ligne = json.loads(self._texte_export().splitlines()[0])
        journal = run_export.ecrire_journal_attente(ligne, depuis=self.racine)
        lignes_avant = self._lignes_export()
        vrai = run_export.effacer_journal_attente

        def refuser(chemin) -> None:
            if Path(chemin) == Path(journal):
                raise PermissionError("greffe")
            vrai(chemin)

        with mock.patch.object(run_export, "effacer_journal_attente", side_effect=refuser):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever
        self.assertEqual(err.count("reconstruite depuis runs/"), 1, err)
        self.assertEqual(self._compter(self._base_defaut()), 1)
        self.assertIn("nettoyage des journaux differe, a retirer a la main :", err)
        self.assertIn(str(journal), err)
        self.assertIn("PermissionError", err)
        self.assertTrue(Path(journal).exists(), "le journal reste sur disque")
        self.assertEqual(self._lignes_export(), lignes_avant, "export idempotent (même auteur)")
        self.assertFalse(store._reconstruction_bloquee)
        store.append_event("T-18d", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op18d")

    def test_T19_redaction_en_panne_a_l_ouverture_differe_tout(self) -> None:
        # M19 : résolution APRÈS la phase 1 → AVORTEE au lieu de DIFFEREE.
        # M19b : pas de drapeau sur DIFFÉRÉE → le journal est rejoué, la base se remplit.
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)])
        ul = self._ulids(1)[0]
        run_export.ecrire_journal_attente(self._ligne(ul, task_id="T-19L"), depuis=self.racine)
        es = self._es()
        with mock.patch.object(es, "_redaction", side_effect=RuntimeError("redaction greffee absente")):
            store, err = self._ouvrir_defaut()
        self.assertEqual(self._compter(self._base_defaut()), 0)
        self.assertIn("DIFFEREE", err)
        self.assertNotIn("AVORTEE", err)
        self.assertIn("rejeu differe", err)
        self.assertEqual(len(self._journaux()), 1, "journal CONSERVÉ")
        with self.assertRaises(es.ReconstructionAvorteeError) as cm:
            store.append_event("T-19", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op19")
        self.assertIn("DIFFEREE", str(cm.exception))

    def test_T21_supprimer_la_base_re_arme_la_reconstruction(self) -> None:
        # M21 (procédure) : garder le `-wal` — mesuré à part, voir le rapport de campagne.
        self._peupler_A()
        base = self._base_defaut()
        self._ouvrir_defaut()
        premier = self._tables(base)
        self.assertTrue(premier["events"])
        for suffixe in ("", "-wal", "-shm"):
            Path(str(base) + suffixe).unlink(missing_ok=True)
        _, err = self._ouvrir_defaut()
        self.assertEqual(err.count("reconstruite depuis runs/"), 1, err)
        self.assertEqual(self._tables(base), premier)

    def test_T22_les_auteurs_rejoues_sont_TOUS_nommes(self) -> None:
        # M22 : n'accumuler que le DERNIER auteur.
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurA", copie="copieA")
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)], auteur="auteurB", copie="copieB")
        patch, resumes = self._espionner_reconstruire()
        with patch:
            _, err = self._ouvrir_defaut()
        self.assertEqual(resumes[0]["auteurs_rejoues"], ["auteurA", "auteurB"])
        self.assertIn("auteurs_rejoues=auteurA,auteurB", err)

    def test_T8c_avortement_a_l_ouverture_rien_ecrit_et_ecriture_refusee(self) -> None:
        # M8c : sans filet R → `EventStore()` lève. M8c' : commit avant le pont → base
        # non vide. M8c'' : remède « relancer ». M8c''' : sans garde dans
        # `_ecrire_evenement`. M8c4 : sans garde dans `reserve`/`link`.
        self._peupler_A()
        base = self._base_defaut()
        lignes_avant = self._lignes_export()
        es = self._es()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever
        self.assertIn("reconstruction AVORTEE, rien ecrit (RuntimeError: pont greffe en panne)", err)
        self.assertIn("tasks.py replay-sync", err)
        self.assertIn("v3_event_store.db*", err)
        self.assertNotIn("relancer", err)
        self.assertEqual(self._compter(base), 0, "base VIDE")
        refus = (
            lambda: store.append_event("T-8c", "run", "TASK_CREATED", {"req_id": "R"},
                                       operation_id="op8c"),
            lambda: store.consume_board_intent(self._intent_remplace()),
            lambda: store.reserve_board_identity("V3:y", "op-y"),
            lambda: store.link_board_task("T-y", "V3:y", "op-y"),
        )
        for appel in refus:
            with self.assertRaises(es.ReconstructionAvorteeError):
                appel()
        self.assertEqual(self._compter(base), 0)
        self.assertEqual(self._scalaire(base, "SELECT COUNT(*) FROM board_identity_reservations"), 0)
        self.assertEqual(self._journaux(), [])
        self.assertEqual(self._lignes_export(), lignes_avant, "rien exporté")
        _, err2 = self._ouvrir_defaut()
        self.assertEqual(err2.count("reconstruite depuis runs/"), 1, err2)
        self.assertGreater(self._compter(base), 0)

    def test_T8e_un_rollback_qui_leve_reste_contenu(self) -> None:
        # M8e : retirer le `suppress` autour du `rollback` → l'erreur sort de l'except.
        self._peupler_A()
        es = self._es()
        vrai = es.get_db_connection

        class _RollbackEnPanne:
            def __init__(self, conn):
                self._conn = conn

            def __getattr__(self, nom):
                return getattr(self._conn, nom)

            def rollback(self):
                raise sqlite3.OperationalError("disk I/O error")

        patch, resumes = self._espionner_reconstruire()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne), \
                mock.patch.object(es, "get_db_connection",
                                  lambda *a, **k: _RollbackEnPanne(vrai(*a, **k))), patch:
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever
        self.assertEqual(resumes[0]["avortee"], 1)
        self.assertEqual(self._compter(self._base_defaut()), 0)
        self.assertTrue(store._reconstruction_bloquee)

    def test_T8d_journal_preexistant_conserve_puis_rejoue_apres_succes(self) -> None:
        # M8d : sans la branche anticipée du rejeu → « echec base » sur chaque journal.
        self._peupler_A()
        lignes_runs = self._lignes_export()
        ul = self._ulids(1)[0]
        run_export.ecrire_journal_attente(self._ligne(ul, task_id="T-8d"), depuis=self.racine)
        es = self._es()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne):
            _, err = self._ouvrir_defaut()
        self.assertEqual(len(self._journaux()), 1)
        self.assertIn("rejeu differe", err)
        self.assertNotIn("echec base", err)
        self.assertEqual(self._compter(self._base_defaut()), 0)
        self._ouvrir_defaut()
        self.assertEqual(self._compter(self._base_defaut()), lignes_runs + 1)
        self.assertEqual(self._journaux(), [])

    def test_T24_sync_spec_une_ligne_code_3_jamais_de_traceback(self) -> None:
        # M24 : sans l'except dans `cli.main` → `ReconstructionAvorteeError` remonte.
        from agentic_v3 import cli

        self._peupler_A()
        spec = self.racine / "spec.md"
        spec.write_text("# Titre [REQ-T24]\ncontenu v2\n", encoding="utf-8")
        base = self._base_defaut()
        create_tables(base)
        conn = sqlite3.connect(str(base))
        conn.execute(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES ('REQ-T24', 1, ?, 'Titre [REQ-T24]', "
            "'# Titre [REQ-T24]\nancien', '[]')",
            (str(spec),),
        )
        conn.commit()
        conn.close()
        es = self._es()
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne), \
                mock.patch.object(sys, "argv", ["agentic_v3", "sync-spec", str(spec)]), \
                redirect_stderr(err), redirect_stdout(out), \
                self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertEqual(cm.exception.code, 3)
        lignes = [l for l in err.getvalue().splitlines() if l.startswith("agentic_v3 sync-spec:")]
        self.assertEqual(len(lignes), 1, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue() + out.getvalue())


class TestReconstructionContenue(_ReconstructionFixture):
    """La lecture de runs/ est CONTENUE : fichier trop gros, fichier illisible,
    ligne illisible — sautés, comptés, nommés ; toute autre levée est absorbée
    par le filet R (AVORTEE), jamais sortie d'`EventStore.__init__`."""

    def test_T23_octet_hostile_entier_demesure_infini_et_dossier(self) -> None:
        # M23 : `read_text(encoding="utf-8")` → avortée. M23b : sans `OverflowError`
        # → avortée. M23c : `errors="replace"` → ligne ALTÉRÉE insérée.
        u_ok, u_ff, u_big, u_inf = self._ulids(4)
        dossier = self.racine / "runs" / "a" / "c"
        dossier.mkdir(parents=True)
        fichier_b = dossier / f"{run_export._mois_de_ulid(u_ok)}.jsonl"
        lignes = [
            json.dumps(self._ligne(u_ok, task_id="T-23")).encode("utf-8"),
            json.dumps(self._ligne(u_ff, payload="XX_OCTET_XX")).encode("utf-8")
            .replace(b"XX_OCTET_XX", b"\xff"),
            json.dumps(self._ligne(u_big)).replace('"attempt": 0', '"attempt": ' + "9" * 5000)
            .encode("utf-8"),
            json.dumps(self._ligne(u_inf)).replace('"attempt": 0', '"attempt": 1e400')
            .encode("utf-8"),
        ]
        fichier_b.write_bytes(b"\n".join(lignes) + b"\n")
        (dossier / "1999-01.jsonl").mkdir()  # C : un DOSSIER au nom d'export
        patch, resumes = self._espionner_reconstruire()
        with patch:
            store, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["applied"], 1, res)
        self.assertEqual(res["lignes_illisibles"], 2, res)
        self.assertEqual(res["malformes"], 1, res)
        self.assertEqual(res["fichiers_illisibles"], 1, res)
        self.assertFalse(store._reconstruction_bloquee)
        self.assertIn(f"runs/a/c/{fichier_b.name}", err)
        self.assertIn("runs/a/c/1999-01.jsonl", err)
        self.assertIn("remede : corriger ou retirer la ligne", err)
        self.assertIn("lignes_illisibles=2", err)
        store.append_event("T-23b", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op23")

    def test_T23b_un_fichier_trop_gros_est_saute_SANS_etre_lu(self) -> None:
        # M23d : borne énorme → le fichier est ouvert. Passe de revue (S-00002519) :
        # la lecture passe par `os.open` + fd, plus par `Path.read_bytes` — l'espion
        # suit la primitive, et sa non-vacuité le prouve.
        normal = self._ecrire_runs([self._ligne(u) for u in self._ulids(1)])
        gros = self.racine / "runs" / "z" / "z" / "2099-01.jsonl"
        gros.parent.mkdir(parents=True)
        with gros.open("wb") as fh:
            fh.truncate(65 * 1024 * 1024)  # creux : 65 MiB déclarés, rien écrit
        espion, ouverts = self._espionner_ouvertures()
        patch, resumes = self._espionner_reconstruire()
        with patch, espion:
            _, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["fichiers_trop_gros"], 1, res)
        self.assertEqual(res["applied"], 1, res)
        self.assertIn(self._canon(normal), ouverts, "non-vacuité : l'espion voit les ouvertures")
        self.assertNotIn(self._canon(gros), ouverts, "le fichier trop gros a été OUVERT")
        self.assertIn("runs/z/z/2099-01.jsonl", err)

    def test_T23c_une_MemoryError_de_lecture_est_absorbee_par_le_filet_R(self) -> None:
        # M23e : sortir la lecture du filet R → `EventStore()` lève.
        # BORNE : une `MemoryError` GREFFÉE prouve le filet, pas le comportement sous
        # vraie pénurie — un OOM-kill noyau n'est attrapable par personne.
        import types

        self._ecrire_runs([self._ligne(u, task_id="MARQUEUR_MEMOIRE") for u in self._ulids(1)])
        es = self._es()

        def charger(texte, *args, **kwargs):
            if isinstance(texte, str) and "MARQUEUR_MEMOIRE" in texte:
                raise MemoryError("greffe")
            return json.loads(texte, *args, **kwargs)

        faux = types.SimpleNamespace(loads=charger, dumps=json.dumps,
                                     JSONDecodeError=json.JSONDecodeError)
        patch, resumes = self._espionner_reconstruire()
        with patch, mock.patch.object(es, "json", faux):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever
        self.assertEqual(resumes[0]["avortee"], 1)
        self.assertIn("AVORTEE", err)
        self.assertIn("rien ecrit (MemoryError", err)
        self.assertEqual(self._compter(self._base_defaut()), 0)
        self.assertTrue(store._reconstruction_bloquee)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO POSIX")
    def test_T23d_un_FIFO_au_nom_d_export_n_est_jamais_lu(self) -> None:
        # MUTATION : retirer le contrôle `S_ISREG` du `lstat` → le FIFO est ouvert (ici
        # l'espion lève au lieu d'ouvrir) → avortée. Sans l'espion, `O_NONBLOCK`
        # empêcherait le blocage et le `fstat` le refuserait — mais l'ouverture même
        # d'un non-régulier est ce que le contrôle interdit.
        normal = self._ecrire_runs([self._ligne(u) for u in self._ulids(1)])
        fifo = self.racine / "runs" / "f" / "f" / "2026-07.jsonl"
        fifo.parent.mkdir(parents=True)
        os.mkfifo(fifo)
        espion, ouverts = self._espionner_ouvertures(leve_sur=fifo)
        patch, resumes = self._espionner_reconstruire()
        with patch, espion:
            _, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["fichiers_illisibles"], 1, res)
        self.assertEqual(res["applied"], 1, res)
        self.assertIn(self._canon(normal), ouverts, "non-vacuité : l'espion voit les ouvertures")
        self.assertIn("runs/f/f/2026-07.jsonl", err)


_POSIX_NON_ROOT = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0


class TestAucunLienSuiviSousRuns(_ReconstructionFixture):
    """S-00002509 (HIGH classe 1) + S-00002518 F3/F4 : `runs/` est VERSIONNÉ et
    FUSIONNABLE ; un lien qui y entre par une fusion ne doit JAMAIS être suivi — ni
    à la lecture, ni à l'énumération — et un dossier illisible ne doit jamais être
    avalé en silence. HEAD c6af0253 (`Path.glob` + `stat` + `read_bytes`) rougit
    chacun de ces témoins."""

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "liens POSIX")
    def test_T26_un_fichier_lien_vers_un_secret_n_est_jamais_ouvert(self) -> None:
        # M26 : lecture par chemin qui suit le lien (`stat` + `read_bytes`, HEAD) →
        # la ligne du « secret » entre en base. M26b : retirer le refus des liens
        # de `_parcourir_runs` ET le `lstat` préalable → `O_NOFOLLOW` seul reste,
        # le lien est compté mais `os.open` est APPELÉ sur lui (espion) → rouge.
        u_ok, u_secret = self._ulids(2)
        normal = self._ecrire_runs([self._ligne(u_ok, task_id="T-26")])
        secret = self._ecrire_fichier_export(
            self._dehors("home/.ssh") / "id_rsa", [self._ligne(u_secret, task_id="T-SECRET")]
        )
        lien = normal.parent / "1999-01.jsonl"
        os.symlink(secret, lien)
        espion, ouverts = self._espionner_ouvertures()
        patch, resumes = self._espionner_reconstruire()
        with patch, espion:
            _, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["applied"], 1, res)
        self.assertEqual(res["fichiers_illisibles"], 1, res)
        self.assertFalse(self._ulid_en_base(self._base_defaut(), u_secret), "le SECRET est en base")
        self.assertIn(self._canon(normal), ouverts, "non-vacuité : l'espion voit les ouvertures")
        self.assertNotIn(self._canon(lien), ouverts, "le LIEN a été ouvert")
        self.assertNotIn(self._canon(secret), ouverts, "la CIBLE du lien a été ouverte")
        self.assertIn("runs/auteurB/copieB/1999-01.jsonl", err)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "liens POSIX")
    def test_T27_un_auteur_ou_une_copie_lien_n_est_jamais_enumere(self) -> None:
        # M27 : `Path.glob("runs/*/*/*.jsonl")` (HEAD) traverse un dossier-lien →
        # les deux lignes du dehors entrent en base. M27b : descendre dans un
        # `DirEntry` lien (`is_dir()` qui suit) → idem.
        u_ok, u_auteur, u_copie = self._ulids(3)
        self._ecrire_runs([self._ligne(u_ok, task_id="T-27")])
        mois = run_export._mois_de_ulid(u_auteur)
        dehors_a = self._dehors("dehors_auteur")
        f_auteur = self._ecrire_fichier_export(
            dehors_a / "c" / f"{mois}.jsonl", [self._ligne(u_auteur, task_id="T-AUTEUR")])
        dehors_c = self._dehors("dehors_copie")
        f_copie = self._ecrire_fichier_export(
            dehors_c / f"{mois}.jsonl", [self._ligne(u_copie, task_id="T-COPIE")])
        os.symlink(dehors_a, self.racine / "runs" / "auteurLien")
        os.symlink(dehors_c, self.racine / "runs" / "auteurB" / "copieLien")
        espion, ouverts = self._espionner_ouvertures()
        patch, resumes = self._espionner_reconstruire()
        with patch, espion:
            _, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["applied"], 1, res)
        self.assertEqual(res["fichiers_illisibles"], 2, res)
        base = self._base_defaut()
        self.assertFalse(self._ulid_en_base(base, u_auteur), "auteur-lien ÉNUMÉRÉ")
        self.assertFalse(self._ulid_en_base(base, u_copie), "copie-lien ÉNUMÉRÉE")
        self.assertNotIn(self._canon(f_auteur), ouverts)
        self.assertNotIn(self._canon(f_copie), ouverts)
        self.assertIn("runs/auteurLien", err)
        self.assertIn("runs/auteurB/copieLien", err)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "liens POSIX")
    def test_T27b_runs_lui_meme_lien_est_refuse_et_nomme(self) -> None:
        # M27c : `lstat` de `runs/` remplacé par un `is_dir()` qui suit → le dehors
        # est lu, sa ligne entre en base.
        u = self._ulids(1)[0]
        dehors = self._dehors("runs_dehors")
        self._ecrire_fichier_export(
            dehors / "a" / "c" / f"{run_export._mois_de_ulid(u)}.jsonl", [self._ligne(u)])
        os.symlink(dehors, self.racine / "runs")
        patch, resumes = self._espionner_reconstruire()
        with patch:
            _, err = self._ouvrir_defaut()
        self.assertEqual(len(resumes), 1, "un lien refusé rend la reconstruction DUE (annoncée)")
        res = resumes[0]
        self.assertEqual(res["applied"], 0, res)
        self.assertEqual(res["fichiers_illisibles"], 1, res)
        self.assertFalse(self._ulid_en_base(self._base_defaut(), u))
        self.assertIn("fichiers illisibles ou refuses (1) : runs", err)

    @unittest.skipUnless(_POSIX_NON_ROOT, "droits POSIX, hors root")
    def test_T28_un_dossier_auteur_illisible_est_compte_et_nomme(self) -> None:
        # M28 : avaler l'`OSError` du `scandir` (comme le glob de HEAD) → compté 0,
        # rien nommé : le contenu de `runs/b/` perdu SANS UN MOT.
        u_ok, u_ferme = self._ulids(2)
        self._ecrire_runs([self._ligne(u_ok, task_id="T-28")], auteur="a", copie="c")
        ferme = self._ecrire_runs(
            [self._ligne(u_ferme, task_id="T-28b")], auteur="b", copie="c").parent.parent
        os.chmod(ferme, 0)
        self.addCleanup(os.chmod, ferme, 0o755)
        patch, resumes = self._espionner_reconstruire()
        with patch:
            store, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["applied"], 1, res)
        self.assertEqual(res["fichiers_illisibles"], 1, res)
        self.assertIn("runs/b", err)
        self.assertIn("perdu pour ce clone jusqu'au remede", err)
        self.assertFalse(store._reconstruction_bloquee)

    @unittest.skipUnless(_POSIX_NON_ROOT, "droits POSIX, hors root")
    def test_T28b_la_sonde_ne_certifie_rien_sur_un_dossier_illisible(self) -> None:
        # M28b : la sonde avale l'`OSError` quand rien d'autre n'est trouvé (glob de
        # HEAD) → « rien de dû », l'écriture passe, la base devient non vide et
        # `runs/b/` n'est JAMAIS reconstruit.
        ferme = self._ecrire_runs(
            [self._ligne(u) for u in self._ulids(2)], auteur="b", copie="c").parent.parent
        os.chmod(ferme, 0)
        self.addCleanup(os.chmod, ferme, 0o755)
        store, err = self._ouvrir_defaut()  # ne DOIT PAS lever (filet S)
        self.assertIn("reconstruction automatique non tentee : PermissionError", err)
        es = self._es()
        with self.assertRaises(es.ReconstructionAvorteeError):
            store.append_event("T-28c", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op28c")
        self.assertEqual(self._compter(self._base_defaut()), 0)


@unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "liens POSIX")
class TestEcrivainSansLienSousRuns(_ReconstructionFixture):
    """S-00002557 (HAUTE classe 1, critic-opus round 2) + S-00002550 : l'ÉCRIVAIN
    suivait les liens — un `runs/<auteur>/<copie>/<mois>.jsonl` fusionné, lien vers
    un fichier de la victime (`.bashrc`), y recevait une ligne JSON (mesuré). Aucun
    lien sous runs/ n'est suivi en ÉCRITURE non plus (runs/, auteur, copie,
    fichier), un lien PHYSIQUE (st_nlink > 1) est refusé en lecture ET en écriture,
    et `mesurer_runs` ne suit plus rien. HEAD 27867dac rougit chacun."""

    _AUTEUR, _COPIE = "auteurA", "copieA"

    def _ajouter(self, ulid: str, racine: Path = None):
        return run_export.ajouter_a_l_export(
            self._ligne(ulid), depuis=racine or self.racine,
            copie=self._COPIE, auteur=self._AUTEUR,
        )

    def test_T41_l_ecrivain_refuse_un_fichier_lien_vers_la_victime(self) -> None:
        # M41 : `open(chemin, "a")` qui suit le lien (HEAD) → la victime reçoit une
        # ligne JSON. M41b : `_ouvrir_export_sans_lien` sans `O_NOFOLLOW` ET sans le
        # `lstat` du fichier dans `_preparer_dossiers_export` → idem.
        u = self._ulids(1)[0]
        victime = self._dehors("home") / ".bashrc"
        victime.write_bytes(b"# profil de la victime\n")
        dossier = self.racine / "runs" / self._AUTEUR / self._COPIE
        dossier.mkdir(parents=True)
        os.symlink(victime, dossier / f"{run_export._mois_de_ulid(u)}.jsonl")
        with self.assertRaises(RunExportError) as cm:
            self._ajouter(u)
        self.assertEqual(victime.read_bytes(), b"# profil de la victime\n", "la VICTIME a été écrite")
        self.assertIn("lien symbolique", str(cm.exception))

    def test_T42_l_ecrivain_refuse_runs_auteur_ou_copie_lien(self) -> None:
        # M42 : `chemin.parent.mkdir(parents=True)` + `open` par chemin (HEAD) →
        # le dossier et le fichier d'export naissent DANS la cible du lien. M42b :
        # `_preparer_dossiers_export` qui teste `is_dir()` (suit) au lieu du `lstat`.
        u = self._ulids(1)[0]
        for niveau in ("runs", "auteur", "copie"):
            with self.subTest(niveau=niveau):
                racine = Path(self._tmp.name) / f"proj_{niveau}"
                racine.mkdir()
                dehors = self._dehors(f"cible_{niveau}")
                runs = racine / "runs"
                if niveau == "runs":
                    os.symlink(dehors, runs)
                elif niveau == "auteur":
                    runs.mkdir()
                    os.symlink(dehors, runs / self._AUTEUR)
                else:
                    (runs / self._AUTEUR).mkdir(parents=True)
                    os.symlink(dehors, runs / self._AUTEUR / self._COPIE)
                with mock.patch.dict(os.environ, {"CADRE_PROJECT_ROOT": str(racine)}):
                    with self.assertRaises(RunExportError) as cm:
                        self._ajouter(u, racine)
                self.assertEqual(list(dehors.rglob("*")), [], "écrit DANS la cible du lien")
                self.assertIn("lien symbolique", str(cm.exception))

    def test_T43_un_lien_physique_est_refuse_en_ecriture_et_en_lecture(self) -> None:
        # S-00002550 (cohérence T-759). M43 : sans le contrôle `st_nlink > 1` à
        # l'écriture → la ligne entre dans le fichier PARTAGÉ avec le dehors. M43b :
        # sans lui à la lecture → le « secret » lié physiquement entre en base.
        u_ok, u_secret, u_neuf = self._ulids(3)
        self._ecrire_runs([self._ligne(u_ok, task_id="T-43")], auteur="auteurZ", copie="copieZ")
        secret = self._ecrire_fichier_export(
            self._dehors("partage") / "secret.jsonl", [self._ligne(u_secret, task_id="T-SECRET")])
        octets_secret = secret.read_bytes()
        dossier = self.racine / "runs" / self._AUTEUR / self._COPIE
        dossier.mkdir(parents=True)
        lien = dossier / f"{run_export._mois_de_ulid(u_neuf)}.jsonl"
        os.link(secret, lien)
        with self.assertRaises(RunExportError) as cm:
            self._ajouter(u_neuf)
        self.assertIn("lien physique", str(cm.exception))
        self.assertEqual(secret.read_bytes(), octets_secret, "fichier PARTAGÉ écrit")
        patch, resumes = self._espionner_reconstruire()
        with patch:
            _, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual((res["applied"], res["fichiers_illisibles"]), (1, 1), res)
        self.assertFalse(self._ulid_en_base(self._base_defaut(), u_secret), "lien physique LU")
        self.assertIn(f"runs/{self._AUTEUR}/{self._COPIE}/{lien.name}", err)

    def test_T44_la_verification_est_rejouee_sous_le_verrou(self) -> None:
        # M44 : ne vérifier les composants qu'AVANT le verrou → une copie basculée en
        # lien ENTRE la vérification et l'ouverture (O_NOFOLLOW ne protège que le
        # dernier composant) → le fichier naît dans la cible.
        from contextlib import contextmanager

        u = self._ulids(1)[0]
        dehors = self._dehors("bascule")
        vrai = run_export._verrou_export
        copie = self.racine / "runs" / self._AUTEUR / self._COPIE

        @contextmanager
        def verrou_puis_bascule(*, depuis=None):
            with vrai(depuis=depuis):
                if copie.is_dir() and not copie.is_symlink():
                    os.rmdir(copie)
                    os.symlink(dehors, copie)
                yield

        with mock.patch.object(run_export, "_verrou_export", verrou_puis_bascule):
            with self.assertRaises(RunExportError):
                self._ajouter(u)
        self.assertEqual(list(dehors.rglob("*")), [], "écrit dans la cible basculée")

    def test_T45_mesurer_runs_ne_suit_aucun_lien(self) -> None:
        # M45 : `racine.glob("*/*/*.jsonl")` + `stat()` (HEAD) → octets et lignes
        # des cibles COMPTÉS (et lus). Les refus sont NOMMÉS, jamais tus.
        # TROIS cibles DISTINCTES (un seul nom chacune) : une cible partagée aurait
        # st_nlink > 1 et serait refusée par ce seul contrôle, masquant un retour au
        # glob qui traverse le dossier-lien (raisonné à l'écriture du témoin, non
        # mesuré ; avec trois cibles, M45 rougit — mesuré).
        legit = self._ecrire_runs([self._ligne(u) for u in self._ulids(2)])
        dehors = self._dehors("mesure")
        self._ecrire_fichier_export(
            dehors / "c" / "2026-09.jsonl", [self._ligne(u) for u in self._ulids(5)])
        cible_lien = self._ecrire_fichier_export(
            self._dehors("mesure_f") / "f.jsonl", [self._ligne(u) for u in self._ulids(3)])
        cible_physique = self._ecrire_fichier_export(
            self._dehors("mesure_h") / "h.jsonl", [self._ligne(u) for u in self._ulids(4)])
        os.symlink(dehors, self.racine / "runs" / "auteurLien")
        os.symlink(cible_lien, legit.parent / "1999-01.jsonl")
        os.link(cible_physique, legit.parent / "1998-01.jsonl")
        m = run_export.mesurer_runs(depuis=self.racine)
        self.assertEqual(m["octets_total"], legit.stat().st_size, m)
        self.assertEqual(m["lignes_total"], 2, m)
        self.assertEqual(sorted(m["chemins_refuses"]), sorted([
            "runs/auteurLien", "runs/auteurB/copieB/1998-01.jsonl",
            "runs/auteurB/copieB/1999-01.jsonl",
        ]), m)

    def _mois_existant(self, premiere: dict) -> Path:
        """`runs/auteurX/backfill/2026-08.jsonl` dont la 1re ligne n'est PAS une borne
        (branche de réécriture de `_ecrire_borne_en_tete`)."""
        fichier = self.racine / "runs" / "auteurX" / "backfill" / "2026-08.jsonl"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(premiere, sort_keys=True) + "\n", encoding="utf-8")
        return fichier

    def test_T52_la_borne_ne_recopie_jamais_la_cible_d_un_lien_dans_runs(self) -> None:
        # Second écrivain, même classe. M52 : `read_bytes` qui suit (27867dac) → la
        # cible (`id_rsa`) est RECOPIÉE sous la borne et le lien REMPLACÉ par un
        # fichier versionné qui la porte : exfiltration par le prochain commit.
        secret = self._dehors("ssh") / "id_rsa"
        secret.write_bytes(b"-----BEGIN SECRET-----\n")
        fichier = self.racine / "runs" / "auteurX" / "backfill" / "2026-08.jsonl"
        fichier.parent.mkdir(parents=True)
        os.symlink(secret, fichier)
        with self.assertRaises(RunExportError):
            run_export._ecrire_borne_en_tete(fichier)
        self.assertTrue(fichier.is_symlink(), "le lien a été REMPLACÉ par un fichier")
        for p in (self.racine / "runs").rglob("*"):
            if p.is_file() and not p.is_symlink():
                self.assertNotIn(b"SECRET", p.read_bytes(), f"secret recopié dans {p}")

    def test_T52b_un_lien_au_nom_de_temporaire_n_est_jamais_ecrit(self) -> None:
        # M52b : temporaire au nom PRÉVISIBLE `<mois>.jsonl.borne.tmp` écrit par
        # `write_bytes` (27867dac) → un lien posé d'avance à ce nom fait ÉCRASER la
        # victime par la borne + le contenu du mois.
        victime = self._dehors("home2") / ".profile"
        victime.write_bytes(b"# victime\n")
        fichier = self._mois_existant({"ulid": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "task_id": "T-1"})
        os.symlink(victime, fichier.with_name(fichier.name + ".borne.tmp"))
        run_export._ecrire_borne_en_tete(fichier)
        self.assertEqual(victime.read_bytes(), b"# victime\n", "victime écrasée")
        premiere = fichier.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("borne", json.loads(premiere), "la borne est posée EN TÊTE")

    def test_T53_le_texte_deja_exporte_ne_se_lit_pas_a_travers_un_lien(self) -> None:
        # M53 : `_lignes_du_texte_sous` par `glob` + `open` (27867dac) → les ULID d'un
        # dossier-auteur LIÉ et d'un fichier LIÉ passent pour « déjà exportés ».
        u_ok, u_dir, u_fic = self._ulids(3)
        self._ecrire_runs([self._ligne(u_ok)])
        dehors = self._dehors("texte")
        self._ecrire_fichier_export(dehors / "c" / "2026-09.jsonl", [self._ligne(u_dir)])
        cible = self._ecrire_fichier_export(
            self._dehors("texte_f") / "f.jsonl", [self._ligne(u_fic)])
        os.symlink(dehors, self.racine / "runs" / "auteurLien")
        os.symlink(cible, self.racine / "runs" / "auteurB" / "copieB" / "1999-01.jsonl")
        err = io.StringIO()
        with redirect_stderr(err):
            presents = run_export._lignes_du_texte_sous(self.racine / "runs", "*/*/*.jsonl")
        self.assertIn(u_ok, presents)
        self.assertNotIn(u_dir, presents, "lu à travers un dossier-lien")
        self.assertNotIn(u_fic, presents, "lu à travers un fichier-lien")
        self.assertIn("SAUTÉ", err.getvalue())


class TestRacineRunsMonorepo(_ReconstructionFixture):
    """S-00002518 F1 : l'écrivain exporte sous `project_root(depuis=…)/runs/` (la
    racine GIT) ; la sonde et la lecture doivent chercher au MÊME endroit."""

    def test_T29_agents_sous_apps_foo_runs_a_la_racine_git(self) -> None:
        # M29 : sonde/lecture sous `self.project_root` BRUT (HEAD) → `apps/foo/runs/`
        # n'existe pas → rien de dû, base vide, reconstruction INERTE.
        subprocess.run(
            ["git", "init", "-q", str(self.racine)], env=_env_sans_git(), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        foo = self.racine / "apps" / "foo"
        (foo / ".agents").mkdir(parents=True)
        self._ecrire_runs([self._ligne(u) for u in self._ulids(3)])
        err = io.StringIO()
        with mock.patch.dict(os.environ):
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            self.assertEqual(
                Path(run_export.project_root(depuis=foo)).resolve(), self.racine.resolve(),
                "pré-condition : la racine git EST au-dessus de apps/foo",
            )
            with redirect_stderr(err):
                store = self._es().EventStore(project_root=foo)
        self.assertEqual(err.getvalue().count("reconstruite depuis runs/"), 1, err.getvalue())
        self.assertEqual(self._compter(store.db_path), 3)


class TestSyncSpecAucuneVersionSansEvenement(_ReconstructionFixture):
    """S-00002518 F2 : `sync-spec` commitait la version PUIS l'événement ; un
    événement refusé laissait une version SANS `SPEC_MUTATED`, que le sync suivant
    voyait « UP-TO-DATE » — perdu définitivement. Voisin de T24 (même CLI)."""

    _SPEC_V1 = "# Titre [REQ-S]\nancien"

    def _spec_v2(self) -> Path:
        spec = self.racine / "spec.md"
        spec.write_text("# Titre [REQ-S]\ncontenu v2\n", encoding="utf-8")
        return spec

    def _poser_v1(self, db: Path, spec: Path) -> None:
        create_tables(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
            "content_markdown, tags_json) VALUES ('REQ-S', 1, ?, 'Titre [REQ-S]', ?, '[]')",
            (str(spec), self._SPEC_V1),
        )
        conn.commit()
        conn.close()

    def _versions(self, db: Path) -> list:
        conn = sqlite3.connect(str(db))
        try:
            return [r[0] for r in conn.execute(
                "SELECT version FROM spec_requirements WHERE req_id='REQ-S' ORDER BY version")]
        finally:
            conn.close()

    def _mutations(self, db: Path) -> list:
        conn = sqlite3.connect(str(db))
        try:
            return sorted(json.loads(r[0])["version"] for r in conn.execute(
                "SELECT payload_json FROM events_ledger WHERE event_type='SPEC_MUTATED'"))
        finally:
            conn.close()

    def _cli_sync(self, spec: Path):
        from agentic_v3 import cli

        err, out = io.StringIO(), io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", ["agentic_v3", "sync-spec", str(spec)]), \
                redirect_stderr(err), redirect_stdout(out):
            try:
                cli.main()
            except SystemExit as exc:
                code = exc.code
        return code, err.getvalue()

    def test_T30_sync_spec_bloque_n_ecrit_aucune_version(self) -> None:
        # Scénario F2 rejoué : à HEAD, la v2 est commitée puis l'événement refusé
        # (code 3) ; au sync suivant la v2 est « UP-TO-DATE », SPEC_MUTATED JAMAIS émis.
        # M30 : retirer `exiger_ecriture_permise()` avant la v2 → la v2 est ÉCRITE sur
        # l'instance bloquée (la compensation la défait ensuite, d'où la greffe :
        # sans elle les deux couches se masquent et M30 survivait — mesuré).
        from agentic_v3.ingestion.parse_specs import SpecParser

        self._peupler_A()
        spec = self._spec_v2()
        base = self._base_defaut()
        self._poser_v1(base, spec)
        es = self._es()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne), \
                mock.patch.object(SpecParser, "_compenser_version", side_effect=AssertionError(
                    "compensation sollicitée : une version a été ÉCRITE sur instance bloquée")):
            code, err = self._cli_sync(spec)
        self.assertEqual(code, 3, err)
        self.assertEqual(self._versions(base), [1], "une version écrite sur instance BLOQUÉE")
        code2, err2 = self._cli_sync(spec)  # reconstruction réussie cette fois
        self.assertIn(code2, (0, None), err2)
        self.assertEqual(self._versions(base), [1, 2])
        self.assertEqual(self._mutations(base), [2], "aucune version sans son SPEC_MUTATED")

    def test_T31_append_event_qui_leve_avant_commit_defait_la_version(self) -> None:
        # M31 : sans la compensation → la v2 reste SANS SPEC_MUTATED ; le sync
        # suivant la voit « UP-TO-DATE ».
        from agentic_v3.ingestion.parse_specs import SpecParser

        db = self.state / "spec.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        spec = self._spec_v2()
        self._poser_v1(db, spec)
        parser = SpecParser(db)  # base EXPLICITE : aucune reconstruction d'office
        es = self._es()
        with mock.patch.object(es.EventStore, "append_event",
                               side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertRaises(sqlite3.OperationalError):
                parser.process_and_sync_spec(spec)
        self.assertEqual(self._versions(db), [1], "version laissée SANS événement")
        with redirect_stderr(io.StringIO()):
            parser.process_and_sync_spec(spec)
        self.assertEqual(self._versions(db), [1, 2])
        self.assertEqual(self._mutations(db), [2])

    def test_T32_evenement_commite_puis_export_en_panne_garde_la_version(self) -> None:
        # M32 : compensation INCONDITIONNELLE → la v2 est effacée alors que son
        # SPEC_MUTATED est commité (événement sans version, puis un SECOND
        # SPEC_MUTATED v2 au sync suivant). VERT à HEAD par construction (HEAD ne
        # compense rien) : ce témoin borne la compensation, il ne la motive pas.
        from agentic_v3.ingestion.parse_specs import SpecParser

        db = self.state / "spec.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        spec = self._spec_v2()
        self._poser_v1(db, spec)
        parser = SpecParser(db)
        es = self._es()
        with mock.patch.object(es.EventStore, "_flush_export",
                               side_effect=run_export.PanneInfrastructure("greffe")):
            with self.assertRaises(run_export.PanneInfrastructure):
                parser.process_and_sync_spec(spec)
        self.assertEqual(self._versions(db), [1, 2], "version effacée, événement commité")
        self.assertEqual(self._mutations(db), [2])
        with redirect_stderr(io.StringIO()):
            parser.process_and_sync_spec(spec)
        self.assertEqual(self._mutations(db), [2], "un second SPEC_MUTATED v2")

    def test_T46_l_ulid_est_tire_avant_tout_commit(self) -> None:
        # S-00002557 (MAJEURE). M46 : tirer l'ULID APRÈS le commit de la version et
        # HORS du `try` compensé (27867dac) → un tirage qui lève (couture `ids`
        # absente) laisse la v2 SANS SPEC_MUTATED.
        from agentic_v3.ingestion import parse_specs

        db = self.state / "spec.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        spec = self._spec_v2()
        self._poser_v1(db, spec)
        parser = parse_specs.SpecParser(db)
        with mock.patch.object(parse_specs.run_export, "nouvel_ulid",
                               side_effect=RunExportError("couture ids absente (banc)")):
            with self.assertRaises(RunExportError):
                parser.process_and_sync_spec(spec)
        self.assertEqual(self._versions(db), [1], "version commitée avant le tirage d'ULID")

    def test_T47_la_compensation_garde_une_version_sous_une_posterieure(self) -> None:
        # S-00002557 (FAIBLE). M47 : DELETE sans `NOT EXISTS (… version > ?)` → un
        # sync CONCURRENT a posé la v3 (son diff part de la v2) ; effacer la v2 laisse
        # l'historique troué sous la v3.
        from agentic_v3.ingestion.parse_specs import SpecParser

        db = self.state / "spec.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        spec = self._spec_v2()
        self._poser_v1(db, spec)
        parser = SpecParser(db)
        es = self._es()

        def v3_concurrente_puis_echec(*args, **kwargs):
            conn = sqlite3.connect(str(db))
            conn.execute(
                "INSERT INTO spec_requirements (req_id, version, file_path, section_title, "
                "content_markdown, tags_json) VALUES ('REQ-S', 3, ?, 'Titre [REQ-S]', "
                "'v3 concurrente', '[]')", (str(spec),))
            conn.commit()
            conn.close()
            raise sqlite3.OperationalError("database is locked")

        err = io.StringIO()
        with mock.patch.object(es.EventStore, "append_event", side_effect=v3_concurrente_puis_echec), \
                redirect_stderr(err):
            with self.assertRaises(sqlite3.OperationalError):
                parser.process_and_sync_spec(spec)
        self.assertEqual(self._versions(db), [1, 2, 3], "v2 effacée sous la v3")
        self.assertIn("version conservée sous une version postérieure", err.getvalue())


class TestPasseDeRevueAnnoncesEtCompteurs(_ReconstructionFixture):
    """S-00002518 F5 / F7 et fable, S-00002510 avis L : ce qui est dit, et dans
    quel compteur."""

    def test_T33_base_trouvee_incomplete_sous_le_verrou_est_annoncee(self) -> None:
        # M33 : `saute_non_vide` muet (HEAD) → une session concurrente qui a écrit
        # pendant l'ouverture laisse la base SANS l'historique de runs/, sans un mot.
        store, _ = self._ouvrir_defaut()  # pas de runs/ : rien de dû
        base = self._base_defaut()
        conn = sqlite3.connect(str(base))
        conn.execute(
            "INSERT INTO events_ledger (task_id, agent_role, event_type, payload_json, ulid) "
            "VALUES ('T-33', 'run', 'TASK_CREATED', '{}', ?)", (run_export.nouvel_ulid(),))
        conn.commit()
        conn.close()
        lignes = [self._ligne(u) for u in self._ulids(3)]
        self._ecrire_runs(lignes)
        err = io.StringIO()
        with redirect_stderr(err):
            res = store._reconstruire(None, si_vide=True)
        self.assertEqual(res["saute_non_vide"], 1, res)
        self.assertEqual(set(res), _CLES_RESUME_691)
        texte = err.getvalue()
        self.assertIn("reconstruction NON faite", texte)
        self.assertIn("3 evenements de runs/ absents", texte)
        self.assertIn("arreter les autres sessions", texte)
        self.assertIn("v3_event_store.db*", texte)
        self.assertIn("tasks.py replay-sync", texte)
        self.assertNotIn("AVORTEE", texte)
        self.assertFalse(store._reconstruction_bloquee)
        # Base qui porte TOUT ce que runs/ porte : muette (la session concurrente a
        # elle-même reconstruit).
        conn = sqlite3.connect(str(base))
        for l in lignes:
            conn.execute(
                "INSERT INTO events_ledger (task_id, agent_role, event_type, payload_json, ulid) "
                "VALUES (?, ?, ?, ?, ?)",
                (l["task_id"], l["agent_role"], l["event_type"], l["payload_json"], l["ulid"]))
        conn.commit()
        conn.close()
        err2 = io.StringIO()
        with redirect_stderr(err2):
            store._reconstruire(None, si_vide=True)
        self.assertEqual(err2.getvalue(), "", "une base complète reste MUETTE")

    def test_T34_un_journal_disparu_entre_listage_et_lecture_est_tu(self) -> None:
        # M34 : sans `except FileNotFoundError: continue` → « journal d'attente
        # ILLISIBLE … a retirer a la main » sur un journal qu'un rejeu CONCURRENT
        # vient d'effacer (fausse alarme, S-00002518 F7).
        fantome = run_export.journal_attente(self._ulids(1)[0], depuis=self.racine)
        self.assertFalse(Path(fantome).exists())
        err = io.StringIO()
        with mock.patch.object(run_export, "lister_journaux_attente", return_value=[fantome]), \
                mock.patch.object(run_export, "auteur_courant", return_value="0" * 16), \
                redirect_stderr(err):
            self._store_explicite("t34.db")
        self.assertNotIn("ILLISIBLE", err.getvalue())

    def test_T35_un_FAILED_V3_vers_board_n_est_pas_une_anomalie(self) -> None:
        # M35 : ranger le FAILED sans `intent` dans `failed_hors_intent` (HEAD) → un
        # échec NORMAL du drain V3 → board se lit comme une anomalie.
        u_int, u_v3, u_ill = self._ulids(3)
        intent = self._intent("op-35", before=None, after=self._snap("T-35", "pending"))
        self._ecrire_runs([
            self._ligne_intent(u_int, intent),
            self._ligne(u_v3, task_id="T-35", event_type="BOARD_COMMAND_FAILED",
                        payload={"board_task_id": "T-35", "error": "divergence"},
                        op="op-v3", agent_role="BoardBridge"),
            self._ligne(u_ill, task_id="T-35", event_type="BOARD_COMMAND_FAILED",
                        payload="pas du json", op="op-ill", agent_role="BoardBridge"),
        ])
        b = self._store_explicite("b.db")
        err = io.StringIO()
        with redirect_stderr(err):
            res = b.reconstruire_depuis_exports()
        self.assertEqual(res["failed_v3_vers_board"], 1, res)
        self.assertEqual(res["failed_hors_intent"], 1, res)  # l'illisible, seul
        self.assertIn("failed_v3_vers_board=1", err.getvalue())

    def test_T36_une_panne_systeme_du_pont_avorte_et_se_retente(self) -> None:
        # Addendum exec-critic (MAJEUR) + avis L de S-00002509. M36 : `except
        # Exception` unique par intent (HEAD) → chaque intent « écarté », le commit
        # enregistre événements + pont VIDE, base non vide : JAMAIS retentée.
        self._peupler_A()
        base = self._base_defaut()
        es = self._es()

        def reduire_en_panne(store, cursor, intent):
            raise sqlite3.OperationalError("disk I/O error")

        with mock.patch.object(es.EventStore, "_reduce_board_intent", reduire_en_panne):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever (filet R)
        self.assertIn("reconstruction AVORTEE, rien ecrit (OperationalError: disk I/O error)", err)
        self.assertTrue(store._reconstruction_bloquee, "drapeau LEVÉ")
        self.assertEqual(self._compter(base), 0, "rien commité")
        _, err2 = self._ouvrir_defaut()  # panne disparue : retentée, réussie
        self.assertEqual(err2.count("reconstruite depuis runs/"), 1, err2)
        self.assertGreater(self._compter(base), 0)
        self.assertEqual(
            self._scalaire(base, "SELECT COUNT(*) FROM task_board_mapping"), 1,
            "pont rebâti à la seconde ouverture")

    def test_T36b_une_erreur_SQLite_de_DONNEE_reste_un_ecart(self) -> None:
        # Borne de l'addendum, MESURÉE : `after.owner` = objet ⇒ `ProgrammingError`.
        # M36b : relever TOUTE `sqlite3.Error` (lecture littérale de l'addendum) →
        # UNE ligne fusionnée avorte chaque reconstruction, à chaque ouverture.
        u_hostile, u_ok = self._ulids(2)
        snap = {**self._snap("T-36h", "pending"), "owner": {"objet": "hostile"}}
        hostile = self._intent("op-hostile", before=None, after=snap)
        valide = self._intent("op-valide", before=None, after=self._snap("T-36v", "pending"))
        self._ecrire_runs([self._ligne_intent(u_hostile, hostile),
                           self._ligne_intent(u_ok, valide)])
        patch, resumes = self._espionner_reconstruire()
        with patch:
            store, err = self._ouvrir_defaut()
        res = resumes[0]
        self.assertEqual(res["avortee"], 0, err)
        self.assertEqual(res["pont_ecartes"], 1, res)
        self.assertIn("ProgrammingError", err)
        self.assertFalse(store._reconstruction_bloquee)
        self.assertIsNotNone(store.get_board_link("T-36v"), "l'intent valide est rebâti")

    def test_T37_le_filet_N_garde_le_journal_d_une_ligne_non_entree(self) -> None:
        # Moitié « garde » de R2 (addendum exec-critic). M37 : ajouter l'ULID à
        # `entres` AVANT le contrôle de forme → le journal d'une ligne HORS FORME est
        # effacé, la seule trace réparable par le rejeu disparaît.
        u_ok, u_hf = self._ulids(2)
        hors_forme = {**self._ligne(u_hf, task_id="T-37hf"), "attempt": "beaucoup"}
        self._ecrire_runs([self._ligne(u_ok, task_id="T-37"), hors_forme])
        b = self._store_explicite("b.db")  # AVANT les journaux : pas de rejeu
        j_ok = run_export.ecrire_journal_attente(self._ligne(u_ok, task_id="T-37"),
                                                 depuis=self.racine)
        j_hf = run_export.ecrire_journal_attente(hors_forme, depuis=self.racine)
        with redirect_stderr(io.StringIO()):
            res = b.reconstruire_depuis_exports()
        self.assertEqual((res["applied"], res["malformes"]), (1, 1), res)
        self.assertFalse(Path(j_ok).exists(), "journal d'une ligne ENTRÉE : nettoyé")
        self.assertTrue(Path(j_hf).exists(), "journal d'une ligne HORS FORME : GARDÉ")

    def test_T38_la_sonde_lit_la_base_AVANT_de_parcourir_runs(self) -> None:
        # Addendum exec-critic. M38 : parcourir runs/ AVANT le SELECT → une base
        # PEUPLÉE dépend de runs/ (un dossier illisible bloquerait ses écritures).
        store, _ = self._ouvrir_defaut()
        store.append_event("T-38", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op38")
        es = self._es()
        with mock.patch.object(es, "_parcourir_runs", side_effect=AssertionError("runs/ parcouru")), \
                mock.patch.object(es.EventStore, "_racine_runs",
                                  side_effect=AssertionError("racine résolue")):
            self.assertFalse(store._reconstruction_due())

    def test_T39_un_listage_des_journaux_en_echec_au_filet_N_ne_leve_pas(self) -> None:
        # Addendum exec-critic. M39 : retirer l'`except` autour du listage de
        # `_nettoyer_journaux` → l'`OSError` sort de `reconstruire_depuis_exports`.
        self._ecrire_runs([self._ligne(u) for u in self._ulids(2)])
        b = self._store_explicite("b.db")
        err = io.StringIO()
        with mock.patch.object(run_export, "lister_journaux_attente",
                               side_effect=OSError("listage greffe")), redirect_stderr(err):
            res = b.reconstruire_depuis_exports()
        self.assertEqual((res["avortee"], res["applied"]), (0, 2), res)
        self.assertIn("nettoyage des journaux differe, a retirer a la main : run/attente (listage)",
                      err.getvalue())
        self.assertIn("OSError: listage greffe", err.getvalue())

    def test_T40_consume_board_intent_refuse_avant_d_ouvrir_la_base(self) -> None:
        # Addendum exec-critic (4). M40 : garde seulement dans `_ecrire_evenement`
        # → `BEGIN IMMEDIATE` pris (verrou d'écriture) avant le refus.
        self._peupler_A()
        es = self._es()
        with mock.patch.object(es.EventStore, "_rebatir_pont", _pont_en_panne):
            store, _ = self._ouvrir_defaut()
        self.assertTrue(store._reconstruction_bloquee)
        with mock.patch.object(es, "get_db_connection",
                               side_effect=AssertionError("base ouverte")):
            with self.assertRaises(es.ReconstructionAvorteeError):
                store.consume_board_intent(self._intent_remplace())


class TestPasseDeRevue2(_ReconstructionFixture):
    """S-00002561 : phase 1 classée panne/donnée (S-00002560), remède du dossier
    illisible seul, doublons d'identité, et « rien reconstruit » (S-00002557)."""

    def _greffer_ecriture(self, cible: str, effet):
        """Greffe `_ecrire_evenement` : `effet(cursor)` pour la ligne `cible`."""
        es = self._es()
        vrai = es.EventStore._ecrire_evenement

        def ecrire(store, cursor, *args, **kwargs):
            if kwargs.get("ulid") == cible:
                effet(cursor)
            return vrai(store, cursor, *args, **kwargs)

        return mock.patch.object(es.EventStore, "_ecrire_evenement", ecrire)

    def test_T48_disque_plein_en_phase_1_avorte_avec_SA_vraie_cause(self) -> None:
        # M48 : phase 1 sans classement (27867dac) → `ROLLBACK TO SAVEPOINT` sur une
        # transaction que SQLite a DÉJÀ défaite (SQLITE_FULL) lève « no such
        # savepoint », qui masque « database or disk is full ». M48r : remède (c)
        # sans « disque plein ».
        u = self._ulids(3)
        self._ecrire_runs([self._ligne(x) for x in u])

        def plein(cursor):
            cursor.execute("ROLLBACK")  # ce que SQLite fait de lui-même sur SQLITE_FULL
            raise sqlite3.OperationalError("database or disk is full")

        with self._greffer_ecriture(u[1], plein):
            store, err = self._ouvrir_defaut()  # ne DOIT PAS lever (filet R)
        self.assertIn(
            "reconstruction AVORTEE, rien ecrit (OperationalError: database or disk is full)", err)
        self.assertNotIn("no such savepoint", err)
        self.assertIn("disque plein", err)
        self.assertEqual(self._compter(self._base_defaut()), 0)
        self.assertTrue(store._reconstruction_bloquee)

    def test_T48b_une_panne_systeme_sur_UNE_ligne_ne_commite_pas_une_base_partielle(self) -> None:
        # S-00002560. M48b : `except Exception` de phase 1 qui compte `echecs` → la
        # base PARTIELLE (2/3) est commitée, NON vide : jamais plus reconstruite.
        u = self._ulids(3)
        self._ecrire_runs([self._ligne(x) for x in u])

        def corrompue(cursor):
            raise sqlite3.DatabaseError("database disk image is malformed")

        with self._greffer_ecriture(u[1], corrompue):
            store, err = self._ouvrir_defaut()
        self.assertIn("AVORTEE", err)
        self.assertEqual(self._compter(self._base_defaut()), 0, "base PARTIELLE commitée")
        self.assertTrue(store._reconstruction_bloquee)

    def test_T48c_une_erreur_de_DONNEE_en_phase_1_reste_un_echec_de_ligne(self) -> None:
        # S-00002547 maintenu. VERT à 27867dac par construction ; M48c : classer
        # TOUTE `sqlite3.Error` en panne → une ligne fusionnée avorte tout.
        u = self._ulids(3)
        self._ecrire_runs([self._ligne(x) for x in u])

        def donnee(cursor):
            raise sqlite3.ProgrammingError("Error binding parameter 1: type 'dict' is not supported")

        patch, resumes = self._espionner_reconstruire()
        with self._greffer_ecriture(u[1], donnee), patch:
            store, err = self._ouvrir_defaut()
        self.assertEqual((resumes[0]["avortee"], resumes[0]["echecs"], resumes[0]["applied"]),
                         (0, 1, 2), err)
        self.assertFalse(store._reconstruction_bloquee)

    @unittest.skipUnless(_POSIX_NON_ROOT, "droits POSIX, hors root")
    def test_T49_seul_dossier_illisible_le_remede_dit_rendre_lisible(self) -> None:
        # S-00002557 (MOYENNE). M49 : remède générique « replay-sync / supprimer la
        # base » — ni l'un ni l'autre ne répare un dossier illisible.
        ferme = self._ecrire_runs([self._ligne(u) for u in self._ulids(1)],
                                  auteur="b", copie="c").parent.parent
        os.chmod(ferme, 0)
        self.addCleanup(os.chmod, ferme, 0o755)
        store, err = self._ouvrir_defaut()
        attendu = "runs/b (chmod u+rx) ou le retirer de runs/"
        self.assertIn("rendre lisible", err)
        self.assertIn(attendu, err)
        with self.assertRaises(self._es().ReconstructionAvorteeError) as cm:
            store.append_event("T-49", "run", "TASK_CREATED", {"req_id": "R"}, operation_id="op49")
        self.assertIn(attendu, str(cm.exception), "le refus d'écriture porte le MÊME remède")

    def test_T50_saute_non_vide_ignore_un_doublon_d_identite(self) -> None:
        # S-00002557 (FAIBLE). M50 : ne comparer que les ULID → la ligne d'un autre
        # contributeur à la MÊME identité (operation_id, event_kind, attempt), que la
        # reconstruction rejetterait (index unique), est dite « absente » : fausse alerte.
        store, _ = self._ouvrir_defaut()
        base = self._base_defaut()
        u1, u2 = self._ulids(2)
        l1, l2 = self._ligne(u1, op="op-X"), self._ligne(u2, op="op-X")
        conn = sqlite3.connect(str(base))
        conn.execute(
            "INSERT INTO events_ledger (task_id, agent_role, event_type, payload_json, "
            "operation_id, event_kind, attempt, ulid) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (l1["task_id"], l1["agent_role"], l1["event_type"], l1["payload_json"],
             l1["operation_id"], l1["event_kind"], l1["attempt"], u1))
        conn.commit()
        conn.close()
        self._ecrire_runs([l1])
        self._ecrire_runs([l2], auteur="autreAuteur", copie="autreCopie")
        err = io.StringIO()
        with redirect_stderr(err):
            res = store._reconstruire(None, si_vide=True)
        self.assertEqual(res["saute_non_vide"], 1, res)
        self.assertEqual(err.getvalue(), "", "doublon d'identité annoncé comme absent")

    def test_T51_zero_evenement_lisible_se_dit_rien_reconstruit(self) -> None:
        # S-00002560. M51 : « reconstruite depuis runs/ … 0/1 » répétée à chaque
        # ouverture — se lit comme un succès alors que la base reste VIDE.
        self._ecrire_runs([{**self._ligne(self._ulids(1)[0]), "attempt": "beaucoup"}])
        _, err = self._ouvrir_defaut()
        self.assertIn("RIEN reconstruit", err)
        self.assertIn("re-sondee a la prochaine ouverture", err)
        self.assertNotIn("reconstruite depuis runs/", err)
        self.assertEqual(self._compter(self._base_defaut()), 0)
        _, err2 = self._ouvrir_defaut()
        self.assertIn("RIEN reconstruit", err2, "re-sondée : dit à nouveau")


if __name__ == "__main__":
    # HORS pytest, le filet de `conftest.py` n'est pas chargé : on retire ici les
    # mêmes variables, pour TOUS les sous-processus et appels git du banc.
    for _nom in [_n for _n in os.environ if _git_herite(_n)]:
        del os.environ[_nom]
    unittest.main()
