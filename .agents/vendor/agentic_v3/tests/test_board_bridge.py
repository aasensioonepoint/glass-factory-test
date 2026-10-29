from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import pytest

from agentic_v3.db.event_store import EventStore
from agentic_v3.db.schema import create_tables, get_db_connection
from agentic_v3.models.events import EventType


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """T-00000650 : tout banc qui construit `EventStore`/`BoardBridge` sans racine
    explicite écrit son export sous une racine de TEST (`CADRE_PROJECT_ROOT`) et sa
    base machine sous `CADRE_STATE_DIR` — jamais sous le dépôt réel ni le
    `state_home()` réel. L'auteur est FIXÉ : la jambe conteneur tourne en root sans
    `git config user.email` global, et sans cet ancrage l'export serait refusé.

    F3 (binôme, L-00000500) : cette greffe de `_email_git` protège la racine réelle,
    mais elle reste FRANCHISSABLE — sans quoi une fixture d'AMONT ÉTEINT en silence tout
    témoin d'AVAL du vrai git (c'est EXACTEMENT ce qui a laissé passer F1). Deux portes
    équivalentes : la variable d'environnement `AGENTS_BANC_EMAIL_GIT_REEL` (opt-in
    externe/CI/sous-processus) et le marqueur `email_git_reel` (opt-in PAR TEST, lu ici
    via `request` — donc INDÉPENDANT de l'ordre des fixtures : un env posé DANS le corps
    du test arriverait APRÈS cette fixture autouse et serait trop tard).

    PORTE UNIQUE (T-00000695/696) : ces deux portes vivaient ici en COPIE de
    `conftest.py::greffe_email_git_franchissable` — même logique, second exemplaire,
    donc une dérive possible sans un rouge. Elles passent désormais par la porte."""
    from conftest import greffe_email_git_franchissable
    from agentic_v3.db import run_export

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, run_export)


@pytest.mark.email_git_reel
def test_f3_la_greffe_de_email_git_est_franchissable_et_le_vrai_rend_vide(
    tmp_path, monkeypatch
) -> None:
    """F3 (binôme, L-00000500) + F1 — PROUVE que la greffe est FRANCHISSABLE : sous le
    marqueur `email_git_reel` (ou `AGENTS_BANC_EMAIL_GIT_REEL`), la fixture d'isolation
    SAUTE sa greffe, donc le VRAI `_email_git` tourne. Git privé d'identité (global et
    system nullés, HOME neuf) sur un cwd sans user.email rend rc=1 vide -> F1 -> "". Sans
    la franchissabilité (F3), la greffe l'ÉTEINDRAIT — c'est le témoin d'aval que
    L-00000500 décrit. MUTATION (greffe NON franchissable) : `_email_git` rend
    « banc@test » et l'assert « "" » rougit ; MUTATION (F1 retirée) : le vrai `_email_git`
    LÈVE une `PanneInfrastructure` (sous-classe de `RunExportError`, jamais une
    `AuteurIndisponible`) et l'assert rougit aussi."""
    from agentic_v3.db import run_export

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    home = tmp_path / "home_neuf"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # G4 (T-00000695/696) : ÉPINGLE l'hypothèse d'environnement. `_email_git` lance
    # `git config user.email` avec cwd = CADRE_PROJECT_ROOT (= tmp_path/proj). Si un
    # dépôt git ANCÊTRE traîne AU-DESSUS de tmp_path (répertoire jetable partagé du
    # runner), git le REMONTE et peut rendre rc=0 + un email de dépôt — le verdict du
    # témoin dépendrait alors de ce qu'un AUTRE agent a laissé (le critique a mesuré le
    # MÊME geste rendre rc=0 puis rc=128 selon l'ancêtre). `GIT_CEILING_DIRECTORIES`
    # interdit à git de remonter au-dessus de tmp_path : clé bien ABSENTE, rc=1 muet,
    # quoi qu'il y ait plus haut.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    # CADRE_PROJECT_ROOT (posé par la fixture) = tmp_path/proj, PAS un dépôt git : la
    # greffe étant franchie, le VRAI `_email_git` y voit une clé ABSENTE et rend "".
    assert run_export._email_git() == "", (
        "greffe franchie + F1 : clé absente -> '' — « banc@test » signalerait une greffe "
        "NON franchie, une levée signalerait F1 absente"
    )
    with pytest.raises(run_export.AuteurIndisponible):
        run_export.empreinte_auteur(run_export._email_git())


BUSINESS_FIELDS = ("id", "state", "task", "owner", "stage", "updated")

# Generous ceiling (seconds) for THREAD-SYNCHRONISATION barriers only: the wait
# for a worker thread to REACH its slow mutation, or to finish. These measure
# scheduling latency, not any property of the lease machinery, so a fixed 2 s
# tripped under load (T-00000176: mutation_started.wait timed out at l.1215 on a
# loaded run while the worker had not yet been scheduled into set_state). This is
# a patience bound, not a threshold: the lease TTLs (lease_seconds=…) and the
# timing that PROVES renewal (the 0.05 s lease against the 0.06 s window) are
# unchanged, so a broken heartbeat still lets the competing worker reclaim, and a
# genuinely hung worker still fails at this deadline.
_THREAD_SYNC_TIMEOUT = 30.0


class BoardBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "v3.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def snapshot(task_id: str, state: str, *, title: str = "Task", stage: str = "") -> dict[str, str]:
        return {
            "id": task_id,
            "state": state,
            "task": title,
            "owner": "dev-multi",
            "stage": stage,
            "updated": "2026-08-07",
        }

    def intent(
        self,
        operation_id: str,
        *,
        before: dict[str, str] | None,
        after: dict[str, str] | None,
        event_kind: str = "BOARD_TASK_OBSERVED",
        attempt: int = 0,
    ) -> dict[str, object]:
        task_id = (after or before or {})["id"]
        return {
            "operation_id": operation_id,
            "event_kind": event_kind,
            "affected_task_ids": [task_id],
            "before": before,
            "after": after,
            "revision_sha256": "0" * 64,
            "attempt": attempt,
            "lease": {"owner": "test", "token": "lease", "expires_at": 1.0},
        }

    def file_intent(
        self,
        operation_id: str,
        *,
        before: dict[str, str] | None,
        after: dict[str, str] | None,
    ) -> dict[str, object]:
        intent = self.intent(operation_id, before=before, after=after)
        canonical = json.dumps(
            {"before": before, "after": after},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        intent["revision_sha256"] = hashlib.sha256(canonical).hexdigest()
        intent["lease"] = None
        return intent

    def _racine_export(self) -> Path:
        """La racine d'export EFFECTIVE = `CADRE_PROJECT_ROOT` de la fixture (l'env
        prime sur la racine passée au constructeur, par construction de
        `cadre.paths.project_root`)."""
        from agentic_v3.db import run_export

        return run_export.project_root()

    def _lignes_export(self) -> list[dict]:
        """Toutes les lignes des exports `runs/*/*/*.jsonl` sous la racine de test."""
        runs = self._racine_export() / "runs"
        lignes: list[dict] = []
        if runs.is_dir():
            for chemin in sorted(runs.rglob("*.jsonl")):
                for brute in chemin.read_text(encoding="utf-8").splitlines():
                    brute = brute.strip()
                    if brute:
                        lignes.append(json.loads(brute))
        return lignes

    def _lignes_export_pour(self, operation_id: str) -> list[dict]:
        return [l for l in self._lignes_export() if l.get("operation_id") == operation_id]

    def test_un_intent_board_produit_une_ligne_dans_l_export_verse(self) -> None:
        # Témoin 16 : un intent board écrit une ligne d'export portant l'operation_id,
        # un ulid non vide et la clé `agent_role` = "BoardBridge" (que la
        # précondition 2 de la sœur greppe). MUTATION : laisser consume_board_intent
        # sur son INSERT brut d'origine -> l'export reste vide.
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000042", "running", stage="dev")
        op = "op-export-16"
        bridge.consume_board_intent(self.intent(op, before=None, after=after))
        lignes = self._lignes_export_pour(op)
        self.assertTrue(lignes, "aucune ligne dans l'export pour cet intent")
        ligne = lignes[0]
        self.assertTrue(ligne.get("ulid"), "ulid vide dans la ligne d'export")
        self.assertEqual(ligne.get("agent_role"), "BoardBridge",
                         "la clé agent_role attendue = BoardBridge")

    def test_auteur_absent_defere_l_export_sans_faire_echouer_le_miroir(self) -> None:
        """TÉMOIN DE RÉGRESSION (T-00000650, ajouté 2026-09-21) — LA CAUSE.
        Sans `git user.email`, l'export versionné ne peut pas nommer son auteur —
        mais le miroir board→V3 (db + inbox) est DÉJÀ commité. Coupler cet échec
        d'export au succès du miroir (RunExportError propagé par `_flush_export`)
        faisait relâcher l'intent côté `tasks.py`, qui rouvrait sa file à chaque
        transition (banc `tasks.test.sh` : 45 lignes réécrites au lieu de ≤ 4). Ce
        témoin exerce le VRAI `consume_board_intent` sans auteur — là où le banc de
        `drain_sync_outbox` (`test_tasks.py`) n'injecte qu'un consumer MOCK, donc ne
        voyait JAMAIS cette voie : c'est précisément le trou par lequel la régression
        est passée. Le miroir doit RÉUSSIR, l'événement être commité en base,
        l'export être DIFFÉRÉ (aucune ligne, journal d'attente CONSERVÉ pour rejeu),
        symétrique de `_rejouer_journaux_attente`. MUTATION (code fautif d'origine) :
        re-propager `RunExportError` depuis `_flush_export` — `consume_board_intent`
        lève alors, et l'`assertTrue` ci-dessous rougit."""
        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000077", "running", stage="dev")
        op = "op-auteur-absent"
        with mock.patch.object(run_export, "_email_git", return_value=""):
            self.assertTrue(
                bridge.consume_board_intent(self.intent(op, before=None, after=after)),
                "un auteur absent ne doit PAS faire échouer le miroir board→V3",
            )
            journaux_conserves = run_export.lister_journaux_attente(
                depuis=bridge.event_store.project_root
            )
        conn = get_db_connection(self.db_path)
        try:
            en_base = conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE operation_id=?", (op,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, en_base, "l'événement doit être commité en base")
        self.assertEqual(
            [], self._lignes_export_pour(op),
            "aucune ligne ne doit être exportée tant que l'auteur manque",
        )
        self.assertTrue(
            journaux_conserves,
            "le journal d'attente doit être conservé pour un rejeu ultérieur",
        )

    def test_echec_d_export_dans_la_boucle_defere_sans_faire_echouer_le_miroir(self) -> None:
        """A1 (S-00001805 fable 1) — TÉMOIN JUMEAU de l'auteur absent, côté BOUCLE.
        L'auteur est RÉSOLU (fixture `banc@test`) ; c'est `ajouter_a_l_export` qui
        échoue APRÈS le commit — `OSError(28)` « No space left on device ». Le miroir
        board→V3 (db + inbox) est DÉJÀ commité : propager rejouerait la régression
        45 lignes. Le miroir doit RÉUSSIR, l'événement être en base, l'export DIFFÉRÉ
        (aucune ligne), le journal d'attente CONSERVÉ pour rejeu. MUTATION (retirer
        le `try/except (RunExportError, OSError)` de la boucle de `_flush_export`) :
        l'OSError remonte, `consume_board_intent` lève, l'`assertTrue` rougit."""
        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000078", "running", stage="dev")
        op = "op-oserror-boucle"
        with mock.patch.object(
            run_export,
            "ajouter_a_l_export",
            side_effect=OSError(28, "No space left on device"),
        ):
            self.assertTrue(
                bridge.consume_board_intent(self.intent(op, before=None, after=after)),
                "un echec d'export dans la boucle ne doit PAS faire echouer le miroir",
            )
            journaux_conserves = run_export.lister_journaux_attente(
                depuis=bridge.event_store.project_root
            )
        conn = get_db_connection(self.db_path)
        try:
            en_base = conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE operation_id=?", (op,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, en_base, "l'événement doit être commité en base")
        self.assertEqual(
            [], self._lignes_export_pour(op),
            "aucune ligne ne doit être exportée quand l'ajout échoue",
        )
        self.assertTrue(
            journaux_conserves,
            "le journal d'attente doit être conservé pour un rejeu ultérieur",
        )

    def test_panne_infra_remonte_fail_closed_tandis_qu_auteur_absent_est_differe(self) -> None:
        """A2 (S-00001806 T4) — la RÉSOLUTION de l'auteur distingue DEUX cas par le
        TYPE. Un `RunExportError` NU (panne d'infra : « module cadre.executor
        introuvable ») REMONTE fail-closed — une panne PERMANENTE ne se déguise pas
        en report temporaire. Un `AuteurIndisponible` (git user.email absent) est
        DIFFÉRÉ, journal conservé. Les DEUX bras, sinon le témoin ne prouve que la
        moitié. MUTATION (élargir le `except` de `_flush_export` à `RunExportError`) :
        le bras infra ne lève plus, l'`assertRaises` rougit."""
        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)

        # Le type PORTE la distinction : une panne d'infra n'est PAS une AuteurIndisponible.
        self.assertNotIsInstance(
            run_export.RunExportError("x"), run_export.AuteurIndisponible
        )
        self.assertIsInstance(
            run_export.AuteurIndisponible("y"), run_export.RunExportError
        )

        # Bras 1 — panne d'infra : RunExportError NU -> remonte fail-closed.
        after = self.snapshot("T-00000079", "running", stage="dev")
        op_infra = "op-infra-nue"
        with mock.patch.object(
            run_export,
            "auteur_courant",
            side_effect=run_export.RunExportError("module cadre.executor introuvable"),
        ):
            with self.assertRaisesRegex(run_export.RunExportError, "cadre.executor"):
                bridge.consume_board_intent(
                    self.intent(op_infra, before=None, after=after)
                )

        # Bras 2 — auteur absent : AuteurIndisponible -> différé, journal conservé.
        after2 = self.snapshot("T-00000080", "running", stage="dev")
        op_absent = "op-auteur-absent-typed"
        with mock.patch.object(
            run_export,
            "auteur_courant",
            side_effect=run_export.AuteurIndisponible("git user.email absent"),
        ):
            self.assertTrue(
                bridge.consume_board_intent(
                    self.intent(op_absent, before=None, after=after2)
                ),
                "un auteur absent (AuteurIndisponible) ne doit PAS faire echouer le miroir",
            )
            journaux_conserves = run_export.lister_journaux_attente(
                depuis=bridge.event_store.project_root
            )
        self.assertEqual(
            [], self._lignes_export_pour(op_absent),
            "aucune ligne exportée tant que l'auteur manque",
        )
        self.assertTrue(
            journaux_conserves,
            "le journal d'attente doit être conservé (report temporaire)",
        )
        # Fail-closed ne rembobine pas le miroir : le bras infra a laissé son
        # événement commité en base (le commit précède `_flush_export`).
        conn = get_db_connection(self.db_path)
        try:
            en_base_infra = conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE operation_id=?", (op_infra,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, en_base_infra, "le miroir du bras infra reste commité en base")

    def test_journal_differe_est_rattrape_a_la_reconstruction_du_store(self) -> None:
        """A4 (S-00001806 T6) — le BRAS DE CONVERGENCE. Les témoins d'auteur absent
        et d'OSError prouvent que le journal est CONSERVÉ, jamais qu'il RATTRAPE.
        Ici : un export d'abord DIFFÉRÉ (OSError dans la boucle), puis une SECONDE
        passe en conditions SAINES — la reconstruction du store à sa prochaine
        construction (`_rejouer_journaux_attente`, base idempotente par ULID) — doit
        RATTRAPER : la ligne finit exportée, le journal disparaît. MUTATION (effacer
        le journal sur échec au lieu de le conserver) : rien à rattraper, l'export
        reste vide, l'`assertEqual(1, len(lignes))` rougit."""
        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000081", "running", stage="dev")
        op = "op-convergence"
        # Passe 1 — export différé (OSError disque plein), journal conservé.
        with mock.patch.object(
            run_export,
            "ajouter_a_l_export",
            side_effect=OSError(28, "No space left on device"),
        ):
            self.assertTrue(
                bridge.consume_board_intent(self.intent(op, before=None, after=after))
            )
        self.assertEqual(
            [], self._lignes_export_pour(op), "l'export doit être différé en passe 1"
        )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=bridge.event_store.project_root),
            "le journal doit être conservé après la passe 1",
        )
        # Passe 2 — conditions saines : une NOUVELLE construction du store rejoue le
        # journal d'attente conservé et exporte la ligne (idempotent par ULID).
        bridge2 = BoardBridge(self.db_path, self.root)
        lignes = self._lignes_export_pour(op)
        self.assertEqual(
            1, len(lignes), "la passe 2 doit RATTRAPER : la ligne finit exportée"
        )
        self.assertEqual("BoardBridge", lignes[0].get("agent_role"))
        self.assertEqual(
            [],
            run_export.lister_journaux_attente(depuis=bridge2.event_store.project_root),
            "le journal doit disparaître après rattrapage",
        )

    def test_reconstruction_du_store_survit_a_une_panne_infra_en_annoncant_PANNE(self) -> None:
        """A2, SECOND site (`_rejouer_journaux_attente`) — RÉÉCRIT par G1 (T-00000695/
        696), qui BORNE S-00001806 T4 au chemin où il a un sens. AVANT : la CONSTRUCTION
        du store REMONTAIT fail-closed sur une panne d'infra (`RunExportError` NU). Cela
        TUAIT `tasks.py new #2` dans un dépôt au `.git/config` illisible (mesuré) et
        rendait le dépôt IRRÉPARABLE par son propre outil, puisque TOUTE commande de
        board CONSTRUIT le store. Le chemin de CONSTRUCTION ATTRAPE désormais la panne :
        la construction SURVIT, l'annonce est DISTINCTE (« PANNE … BLOQUÉ »), jamais
        « auteur absent » — la distinction que T4 exige TIENT, seule la mort du board
        part. Le chemin d'ÉCRITURE (`_flush_export`), lui, PROPAGE toujours : c'est
        `test_panne_infra_remonte_fail_closed_tandis_qu_auteur_absent_est_differe` qui
        le prouve, et il reste vert. MUTATION (retirer l'`except RunExportError` de
        `_rejouer_journaux_attente`) : la construction relève et TUE la commande de
        board suivante — au lieu d'un store, une exception, et l'`assertIsNotNone`
        rougit."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000082", "running", stage="dev")
        op = "op-reconstruction-infra"
        with mock.patch.object(
            run_export, "auteur_courant",
            side_effect=run_export.AuteurIndisponible("git user.email absent"),
        ):
            self.assertTrue(
                bridge.consume_board_intent(self.intent(op, before=None, after=after))
            )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=bridge.event_store.project_root),
            "un journal doit être conservé pour la reconstruction",
        )
        # Reconstruction pendant une panne d'infra -> SURVIT et annonce PANNE/BLOQUÉ.
        err = io.StringIO()
        with mock.patch.object(
            run_export, "auteur_courant",
            side_effect=run_export.RunExportError("module cadre.executor introuvable"),
        ):
            with redirect_stderr(err):
                reconstruit_infra = BoardBridge(self.db_path, self.root)
        self.assertIsNotNone(
            reconstruit_infra.event_store,
            "la construction du store SURVIT à une panne d'infra (board réparable)",
        )
        sortie = err.getvalue()
        self.assertIn("PANNE", sortie, "la panne est annoncée DISTINCTEMENT")
        self.assertIn("BLOQUE", sortie, "l'export est annoncé BLOQUÉ jusqu'à réparation")
        self.assertNotIn(
            "auteur d'export indisponible", sortie,
            "une panne ne se déguise PAS en « auteur absent » (S-00001806 T4 préservé)",
        )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=bridge.event_store.project_root),
            "le journal reste CONSERVÉ : la panne BLOQUE l'export, elle ne détruit rien",
        )
        # Contre-épreuve : AuteurIndisponible laisse aussi la reconstruction RÉUSSIR.
        with mock.patch.object(
            run_export, "auteur_courant",
            side_effect=run_export.AuteurIndisponible("git user.email absent"),
        ):
            reconstruit = BoardBridge(self.db_path, self.root)
        self.assertIsNotNone(reconstruit.event_store)

    @pytest.mark.email_git_reel
    def test_reconstruction_survit_a_la_couture_executor_introuvable(self) -> None:
        """T-00000695/696 (exec-critic, MAJEUR) — la couture `cadre.executor`
        INTROUVABLE par son chemin RÉALISTE : paquet absent ET fichier de repli
        absent. Le repli par chemin lève alors `FileNotFoundError`, que
        `_rejouer_journaux_attente` n'attrapait pas (il n'attrape que
        `RunExportError`) : la construction du store MOURAIT, sans un mot sur
        stderr — mesuré sur clone, « MEURT FileNotFoundError ». Le témoin
        ci-dessus ne le voyait pas : il simule la panne par un `RunExportError`
        posé sur `auteur_courant`, c'est-à-dire la forme déjà attrapée.

        `email_git_reel` : le VRAI `_email_git` doit tourner, sinon la greffe de
        la fixture rend une adresse et la couture n'est jamais atteinte.
        MUTATION (retirer l'enveloppe autour de `_cadre("executor")` dans
        `run_export._email_git`) : `FileNotFoundError` sort de `BoardBridge(...)`,
        rouge."""
        import io
        import sys
        from contextlib import ExitStack, redirect_stderr

        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        after = self.snapshot("T-00000082", "running", stage="dev")
        with mock.patch.object(
            run_export, "auteur_courant",
            side_effect=run_export.AuteurIndisponible("git user.email absent"),
        ):
            self.assertTrue(bridge.consume_board_intent(
                self.intent("op-couture-introuvable", before=None, after=after)))
        racine = bridge.event_store.project_root
        self.assertTrue(run_export.lister_journaux_attente(depuis=racine),
                        "un journal doit attendre la reconstruction")

        couture = ExitStack()
        # `cadre.executor` masqué AUSSI : déjà en cache dans la porte complète,
        # il était rendu sans consulter `cadre` (rouge @ 1bc9933).
        couture.enter_context(mock.patch.dict(sys.modules, {"cadre": None, "cadre.executor": None}))
        couture.enter_context(mock.patch.dict(run_export._MODULES_CADRE))
        run_export._MODULES_CADRE.pop("executor", None)
        couture.enter_context(mock.patch.object(
            run_export, "_SRC_CADRE", Path(tempfile.gettempdir()) / "cadre-absent-banc"))
        err = io.StringIO()
        with couture, redirect_stderr(err):
            reconstruit = BoardBridge(self.db_path, self.root)
        self.assertIsNotNone(reconstruit.event_store, "la construction SURVIT")
        sortie = err.getvalue()
        self.assertIn("PANNE", sortie, sortie)
        self.assertIn("BLOQUE", sortie, sortie)
        self.assertIn("cadre.executor", sortie, "la couture en cause est NOMMÉE")
        self.assertTrue(run_export.lister_journaux_attente(depuis=racine),
                        "le journal reste CONSERVÉ : la panne ne détruit rien")

    def test_le_message_de_report_annonce_l_arriere_total_pas_le_lot(self) -> None:
        """A3 (S-00001806 C5) — le message de report annonce l'ARRIÉRÉ TOTAL, pas la
        taille du LOT courant. On CONSERVE deux journaux, puis un TROISIÈME report :
        son lot vaut 1, mais l'arriéré vaut 3. Le message doit dire « 3 journaux »,
        jamais « 1 journaux » — un opérateur qui lit « 1 » alors que 3 attendent
        conclut l'inverse de la vérité. MUTATION (`len(journaux)` au lieu de
        `lister_journaux_attente`) : le message dit « 1 journaux », l'assertion
        rougit."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        taches = ["T-00000090", "T-00000091", "T-00000092"]
        with mock.patch.object(
            run_export, "auteur_courant",
            side_effect=run_export.AuteurIndisponible("git user.email absent"),
        ):
            for i in range(2):
                bridge.consume_board_intent(
                    self.intent(
                        f"op-arriere-{i}", before=None,
                        after=self.snapshot(taches[i], "running", stage="dev"),
                    )
                )
            # 2 journaux déjà conservés ; ce 3e report a un LOT de 1, un ARRIÉRÉ de 3.
            capture = io.StringIO()
            with redirect_stderr(capture):
                bridge.consume_board_intent(
                    self.intent(
                        "op-arriere-2", before=None,
                        after=self.snapshot(taches[2], "running", stage="dev"),
                    )
                )
        message = capture.getvalue()
        self.assertIn("3 journaux d'attente conserves", message)
        self.assertNotIn("1 journaux d'attente conserves", message)

    def test_l_outbox_et_l_ack_produisent_leurs_lignes_dans_l_export(self) -> None:
        # Témoin 16 bis : enqueue puis claim/ack produisent UNE ligne
        # BOARD_COMMAND_REQUESTED et UNE ligne BOARD_COMMAND_ACKED, chacune avec un
        # ulid. MUTATION : laisser _insert_board_ack_event sur son INSERT brut ->
        # la ligne ACKED manque.
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        store = bridge.event_store
        op = "op-cmd-16b"
        payload = {"board_task_id": "T-00000043"}
        store.enqueue_board_command(op, "BOARD_TASK_OBSERVED", payload)
        claimed = store.claim_board_command("owner-16b")
        self.assertIsNotNone(claimed, "aucune commande à réclamer")
        self.assertTrue(
            store.ack_board_command_with_event(op, claimed["lease_token"], payload),
            "l'ack a échoué",
        )
        kinds = {l.get("event_kind") for l in self._lignes_export()}
        self.assertIn(EventType.BOARD_COMMAND_REQUESTED.value, kinds)
        self.assertIn(EventType.BOARD_COMMAND_ACKED.value, kinds)
        for ligne in self._lignes_export():
            self.assertTrue(ligne.get("ulid"), f"ulid vide : {ligne}")

    def write_board_backlog(self, operation_id: str = "board-create") -> Path:
        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        task = self.snapshot("T-00000001", "pending")
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [task],
                    "sync_outbox": [
                        self.file_intent(operation_id, before=None, after=task)
                    ],
                    "sync_correlations": {
                        operation_id: {
                            "board_task_id": task["id"],
                            "tombstoned": False,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return board_path

    def test_schema_has_operation_identity_inbox_outbox_and_attempt_uniqueness(self) -> None:
        create_tables(self.db_path)
        conn = get_db_connection(self.db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            self.assertTrue({"board_sync_inbox", "board_sync_outbox", "task_board_mapping"} <= tables)
            ledger_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(events_ledger)").fetchall()
            }
            self.assertTrue({"operation_id", "event_kind", "attempt"} <= ledger_columns)
            outbox_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(board_sync_outbox)").fetchall()
            }
            self.assertTrue(
                {"lease_owner", "lease_token", "lease_expires_at"} <= outbox_columns
            )
            indexes = {
                row[1] for row in conn.execute("PRAGMA index_list(events_ledger)").fetchall()
            }
            self.assertIn("uq_events_operation_attempt", indexes)
        finally:
            conn.close()

    def test_required_board_event_types_are_closed_enum_members(self) -> None:
        required = {
            "BOARD_TASK_OBSERVED",
            "BOARD_COMMAND_REQUESTED",
            "BOARD_COMMAND_ACKED",
            "BOARD_COMMAND_FAILED",
            "BOARD_RUNNING_REPLACED",
        }
        self.assertTrue(required <= {member.value for member in EventType})

    def test_append_event_rolls_back_ledger_when_projection_fails(self) -> None:
        store = EventStore(self.db_path)
        with mock.patch.object(store, "_apply_projection", side_effect=RuntimeError("projector failed")):
            with self.assertRaisesRegex(RuntimeError, "projector failed"):
                store.append_event("T-1", "test", EventType.TASK_CREATED, {"req_id": "R-1"})

        conn = get_db_connection(self.db_path)
        try:
            self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0])
        finally:
            conn.close()

    def test_board_intent_is_idempotent_and_reducer_applies_once(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        intent = self.intent(
            "op-create",
            before=None,
            after=self.snapshot("T-00000001", "pending"),
        )

        self.assertTrue(bridge.consume_board_intent(intent))
        self.assertTrue(bridge.consume_board_intent(intent))

        link = bridge.event_store.get_board_link("T-00000001")
        self.assertIsNotNone(link)
        projection = bridge.event_store.get_task_projection(link["v3_task_id"])
        self.assertEqual("PENDING", projection["status"])
        conn = get_db_connection(self.db_path)
        try:
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM events_ledger WHERE operation_id='op-create'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM board_sync_inbox WHERE operation_id='op-create'"
                ).fetchone()[0],
            )
        finally:
            conn.close()

    def test_board_intent_operation_identity_rejects_changed_kind_payload_or_task(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        original = self.intent(
            "stable-board-operation",
            before=None,
            after=self.snapshot("T-00000001", "pending"),
        )
        self.assertTrue(bridge.consume_board_intent(original))
        self.assertTrue(bridge.consume_board_intent(original))
        variants = {
            "kind": {**original, "event_kind": "BOARD_RUNNING_REPLACED"},
            "payload": {
                **original,
                "after": self.snapshot("T-00000001", "pending", title="Changed"),
            },
            "task": {
                **original,
                "affected_task_ids": ["T-00000002"],
                "after": self.snapshot("T-00000002", "pending"),
            },
        }
        for label, variant in variants.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "operation identity"
            ):
                bridge.consume_board_intent(variant)

    def test_board_command_operation_identity_rejects_changed_kind_payload_or_task(self) -> None:
        store = EventStore(self.db_path)
        payload = {"board_task_id": "T-00000001", "status": "PENDING"}
        self.assertTrue(
            store.enqueue_board_command(
                "stable-v3-operation", EventType.BOARD_COMMAND_REQUESTED, payload
            )
        )
        self.assertFalse(
            store.enqueue_board_command(
                "stable-v3-operation", EventType.BOARD_COMMAND_REQUESTED, payload
            )
        )
        variants = {
            "kind": (EventType.BOARD_COMMAND_FAILED, payload),
            "payload": (
                EventType.BOARD_COMMAND_REQUESTED,
                {"board_task_id": "T-00000001", "status": "COMPLETED"},
            ),
            "task": (
                EventType.BOARD_COMMAND_REQUESTED,
                {"board_task_id": "T-00000002", "status": "PENDING"},
            ),
        }
        for label, (kind, changed_payload) in variants.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "operation identity"
            ):
                store.enqueue_board_command(
                    "stable-v3-operation", kind, changed_payload
                )

    def test_start_metadata_and_delete_reuse_link_then_tombstone_it(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        pending = self.snapshot("T-00000001", "pending", title="Before")
        running = self.snapshot("T-00000001", "running", title="Before", stage="dev-multi")
        renamed = self.snapshot("T-00000001", "running", title="After", stage="dev-multi")
        for intent in (
            self.intent("op-create", before=None, after=pending),
            self.intent("op-start", before=pending, after=running),
            self.intent("op-retitle", before=running, after=renamed),
            self.intent("op-delete", before=renamed, after=None),
        ):
            self.assertTrue(bridge.consume_board_intent(intent))

        link = bridge.event_store.get_board_link("T-00000001")
        projection = bridge.event_store.get_task_projection(link["v3_task_id"])
        self.assertEqual("IN_DEV", projection["status"])
        self.assertEqual("dev-multi", projection["current_assignee"])
        self.assertEqual(1, link["tombstoned"])

    def test_running_replaced_cannot_move_terminal_projection_to_pending(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        pending = self.snapshot("T-00000001", "pending")
        done = self.snapshot("T-00000001", "done")
        replaced = self.snapshot("T-00000001", "pending")
        bridge.consume_board_intent(self.intent("op-create", before=None, after=pending))
        bridge.consume_board_intent(self.intent("op-done", before=pending, after=done))
        bridge.consume_board_intent(
            self.intent(
                "op-replaced",
                before=done,
                after=replaced,
                event_kind="BOARD_RUNNING_REPLACED",
            )
        )

        link = bridge.event_store.get_board_link("T-00000001")
        projection = bridge.event_store.get_task_projection(link["v3_task_id"])
        self.assertEqual("COMPLETED", projection["status"])
        events = bridge.event_store.get_task_events("T-00000001")
        self.assertEqual("BOARD_COMMAND_FAILED", events[-1]["event_type"])

    def test_failed_suit_sa_cause_par_ulid_dans_la_meme_milliseconde(self) -> None:
        """T-00000689 — les deux INSERT d'un même `consume_board_intent` (la cause,
        puis son BOARD_COMMAND_FAILED) partagent la ms : l'ULID du FAILED doit être
        PLUS GRAND que celui de sa cause. Aléa 80 bits DÉCROISSANT forcé : sur
        l'ULID non monotone, le FAILED sort AVANT sa cause, de façon DÉTERMINISTE.
        Prouve aussi que la couture mémoïsée `_cadre("ledger.ids")` porte l'état
        d'un appel à l'autre : c'est l'objet qu'elle REND qui est greffé, quelle
        que soit sa branche (paquet installé ou chargement par chemin), donc ce
        témoin passe SEUL, sans `src/` sur le chemin."""
        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        ids = run_export._cadre("ledger.ids")
        bridge = BoardBridge(self.db_path, self.root)
        pending = self.snapshot("T-00000001", "pending")
        done = self.snapshot("T-00000001", "done")
        bridge.consume_board_intent(self.intent("op-create", before=None, after=pending))
        bridge.consume_board_intent(self.intent("op-done", before=pending, after=done))
        vrai_randbits = ids.secrets.randbits
        decroissant = iter(range(1 << 79, 0, -(1 << 60)))
        fige = time.time()
        # `_etat` remis à zéro EN PREMIER (`create=True` : absent sur l'ancien
        # `ids.py`) pour que le premier tirage sous la greffe soit toujours un
        # tirage NEUF — sinon, si l'émission précédente partage la ms figée, le
        # « + 1 » reprend son aléa et le témoin perd sa rougeur DÉTERMINISTE sur
        # l'ancien code.
        with mock.patch.object(ids, "_etat", None, create=True), \
                mock.patch.object(ids.time, "time", return_value=fige), \
                mock.patch.object(
                    ids.secrets, "randbits",
                    side_effect=lambda k: next(decroissant) if k == 80 else vrai_randbits(k),
                ):
            bridge.consume_board_intent(
                self.intent(
                    "op-replaced",
                    before=done,
                    after=self.snapshot("T-00000001", "pending"),
                    event_kind="BOARD_RUNNING_REPLACED",
                )
            )
        events = [
            e for e in bridge.event_store.get_task_events("T-00000001")
            if e["operation_id"] == "op-replaced"
        ]
        self.assertEqual(
            [e["event_type"] for e in events],
            ["BOARD_RUNNING_REPLACED", "BOARD_COMMAND_FAILED"],
        )
        cause, echec = events
        self.assertEqual(cause["ulid"][:10], echec["ulid"][:10], "ms non partagée")
        self.assertLess(cause["ulid"], echec["ulid"],
                        "le FAILED trie AVANT sa cause par ULID")

    def test_matrix_has_all_54_deterministic_cells(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        columns = ("pending", "running", "blocked", "done", "ABSENT_NEVER_LINKED", "TOMBSTONED")
        expected = {
            "PENDING": ("N", "E", "U", "E", "NR", "NR"),
            "IN_DEV": ("E", "Sdev", "E", "E", "NR", "NR"),
            "IN_CRITIC": ("E", "Scritic", "E", "E", "NR", "NR"),
            "IN_TEST": ("E", "Stest", "E", "E", "NR", "NR"),
            "COMPLETED": ("D", "D", "D", "N", "NR", "NR"),
            "BLOCKED": ("B", "B", "B", "E", "NR", "NR"),
            "BLOCKED_WAITING_DEPENDENCY": ("B", "B", "B", "E", "NR", "NR"),
            "BLOCKED_WAITING_HUMAN_DECISION": ("B", "B", "B", "E", "NR", "NR"),
            "OUTDATED_REQUIRES_REFACTOR": (
                "B+DELTA",
                "B+DELTA",
                "B+DELTA",
                "B+DELTA",
                "NR",
                "NR",
            ),
        }
        observed = {
            status: tuple(BoardBridge.decide_action(status, board_state) for board_state in columns)
            for status in expected
        }
        self.assertEqual(54, sum(len(row) for row in observed.values()))
        self.assertEqual(expected, observed)
        self.assertEqual(
            "CREATE",
            BoardBridge.decide_action("PENDING", "ABSENT_NEVER_LINKED", create_authorized=True),
        )
        self.assertEqual(
            "DELTA",
            BoardBridge.decide_action(
                "OUTDATED_REQUIRES_REFACTOR", "TOMBSTONED", delta_authorized=True
            ),
        )
        self.assertEqual(
            "N",
            BoardBridge.decide_action("BLOCKED", "blocked", block_note_convergent=True),
        )

    def test_v3_to_board_unblock_is_scoped_and_does_not_reenter_outbox(self) -> None:
        """The suppression covers the command's OWN effect — and only that.

        What is pinned here: a v3→board apply does not re-enter the very
        transition V3 just ordered, which is already an event on its side and
        would loop. What is NOT pinned, deliberately since T-00000182: that a
        bridge apply enters NOTHING at all. A `done` that releases tasks blocked
        ON it produces effects on OTHER tasks the bridge never asked about, and
        those DO enter the outbox — see
        `test_bridge_done_on_blocker_emits_release_intents_despite_suppression`.
        This fixture has one task and no `blocked_on`, so the empty outbox below
        measures the scoped suppression, never the absence of side effects.
        """
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        tasks_v0 = [self.snapshot("T-00000001", "blocked", stage="waiting")]
        board_path.write_text(
            json.dumps({"next_id": 2, "tasks": tasks_v0, "sync_outbox": [], "sync_correlations": {}}),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)

        result = bridge.reconcile_v3_to_board(
            "T-00000001", "PENDING", operation_id="v3-op-unblock"
        )

        self.assertEqual("U", result)
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])
        self.assertEqual([], bridge._tasks_module().load(self.root)["sync_outbox"])  # la VUE (T-00001058, O2)

    def test_epic_survit_a_la_reconciliation_v3(self) -> None:
        """T-00001043: the optional `epic` field and the root `epics` registry are
        keys the V3 snapshot does not carry (`SYNC_SNAPSHOT_FIELDS` is frozen), so a
        bridge apply must leave them exactly where they were. MUTANT: the unblock
        path rebuilding the task from the snapshot fields only drops `epic`, red."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        registre = [{"id": "E-01", "titre": "Durcir le board", "exclusive": True}]
        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "epics": registre,
                    "tasks": [
                        dict(self.snapshot("T-00000001", "blocked", stage="waiting"), epic="E-01")
                    ],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)

        result = bridge.reconcile_v3_to_board(
            "T-00000001", "PENDING", operation_id="v3-op-unblock-epic"
        )

        self.assertEqual("U", result)
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])
        self.assertEqual("E-01", board["tasks"][0]["epic"])
        self.assertEqual(registre, board["epics"])

    def test_bridge_done_on_blocker_emits_release_intents_despite_suppression(self) -> None:
        """A release is a side effect on ANOTHER task, so V3 must hear about it.

        The bridge applies its `done` under `tasks.suppress_sync`, which silences
        the intent for the task V3 itself ordered closed. The tasks freed by that
        closure were never part of the command: suppressed too, V3 would keep
        projecting a blocked task the board has already returned to `pending`,
        and nothing downstream would ever correct it.
        """
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 3,
                    "tasks": [
                        self.snapshot("T-00000001", "running", stage="dev-multi"),
                        dict(
                            self.snapshot("T-00000002", "blocked", stage="on T-00000001"),
                            blocked_on="T-00000001",
                        ),
                    ],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)

        result = bridge.reconcile_v3_to_board(
            "T-00000001", "COMPLETED", operation_id="v3-op-done"
        )

        self.assertEqual("D", result)
        board = json.loads(board_path.read_text(encoding="utf-8"))
        tasks_by_id = {task["id"]: task for task in board["tasks"]}
        self.assertEqual("done", tasks_by_id["T-00000001"]["state"])
        self.assertEqual("pending", tasks_by_id["T-00000002"]["state"])
        self.assertNotIn("blocked_on", tasks_by_id["T-00000002"])
        # exactly the release, and nothing for the suppressed command itself
        self.assertEqual(
            [("T-00000002", "blocked", "pending")],
            [
                (intent["after"]["id"], intent["before"]["state"], intent["after"]["state"])
                for intent in bridge._tasks_module().load(self.root)["sync_outbox"]  # la VUE (T-00001058, O2)
            ],
        )
        # the snapshots keep the frozen business shape — `blocked_on` never enters.
        # Compared as the SET of field names, never as a tuple: `after` is re-read
        # from the store, whose save() writes keys SORTED (sort_keys=True), so the
        # text order is the serializer's and says nothing about the business shape.
        self.assertEqual(sorted(BUSINESS_FIELDS), sorted(bridge._tasks_module().load(self.root)["sync_outbox"][0]["after"]))

    def test_pont_v3_ferme_encore_arme(self) -> None:
        """MUTANT : `sans_cible=` retire de la cloture du pont (board_bridge:349).

        Le pont V3 ferme une tache d'un chantier ARME sans plan approuve : il
        n'a ni plan a relire ni etape a annoter, donc il DEROGE via `sans_cible=`.
        Sans cette derogation, la garde de cible (T-00000654) refuserait la
        cloture fail-closed, et `sync-spec` echouerait sur ce statut terminal —
        exactement la panne que la derogation au binome avait deja evitee.
        """
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        gate = self.root / ".agents" / "state" / "gates" / "PLAN_CIBLE_REQUIRED"
        gate.parent.mkdir(parents=True)
        gate.write_text("spec=docs/spec.md\nchantier=refonte-packaging\n",
                        encoding="utf-8")

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [
                        dict(
                            self.snapshot("T-00000001", "running", stage="dev-multi"),
                            chantier="refonte-packaging",
                        ),
                    ],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)

        result = bridge.reconcile_v3_to_board(
            "T-00000001", "COMPLETED", operation_id="v3-op-cible"
        )

        self.assertEqual("D", result)
        board = json.loads(board_path.read_text(encoding="utf-8"))
        tasks_by_id = {task["id"]: task for task in board["tasks"]}
        self.assertEqual("done", tasks_by_id["T-00000001"]["state"])

    # DEUX TESTS ONT ETE RETIRES ICI AVEC LEUR SUJET (T-012, le 2026-09-12) :
    # `test_orchestrator_block_transition_is_delivered_to_board` et
    # `test_changed_orchestrator_target_supersedes_stale_divergent_command`.
    #
    # Ils n'eprouvaient PAS `BoardBridge` : ils eprouvaient
    # `OrchestratorNodes.evaluate_dependency_and_human_block` et `_sync_board`,
    # dans `agentic_v3/orchestrator/nodes.py`, module RETIRE. Mesure du
    # 2026-09-12 : aucune surface du depot ne citait `run-task`, seul chemin vers
    # ce FSM, et le module violait « aucun acces disque depuis la logique
    # d'orchestration » en instanciant `EventStore` et `LessonsStore`.
    #
    # CE N'EST PAS UN TROU DE COUVERTURE, ET C'EST VERIFIE PLUTOT QU'AFFIRME.
    # Les deux proprietes que ces tests protegeaient — une transition qui atteint
    # le board, et une commande perimee superseded sans ack — sont eprouvees sur
    # `BoardBridge` DIRECTEMENT par les tests qui suivent dans ce meme fichier :
    # `is_board_command_acked` y est sollicite a 13 endroits, et 19 tests portent
    # sur la supersession, l'outbox et les acquittements. Ce qui disparait avec
    # les deux tests ci-dessus, c'est la traversee par un FSM que rien
    # n'invoquait — pas la garantie.
    #
    # Le stage `v3:WAITING_HUMAN` qu'ils asseraient etait pose par `nodes.py`.
    # L'equivalent vivant est `tasks.py block`, et la chaine d'orchestration
    # reste en prose dans `/kickoff` (decision D1 de la refonte packaging).


    def test_board_save_before_sqlite_effect_replays_from_file_outbox(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        tasks = bridge._tasks_module()
        tasks.new_task(str(self.root), "Crash before SQLite", "dev-multi")
        self.assertEqual(1, len(tasks.load(self.root)["sync_outbox"]))

        self.assertEqual(1, tasks.drain_sync_outbox(self.root, bridge.consume_board_intent))

        task_id = tasks.load(self.root)["tasks"][0]["id"]
        self.assertIsNotNone(bridge.event_store.get_board_link(task_id))
        self.assertEqual([], tasks.load(self.root)["sync_outbox"])

    def test_sqlite_effect_before_board_ack_replays_without_second_reducer_effect(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        tasks = bridge._tasks_module()
        tasks.new_task(str(self.root), "Before", "dev-multi")
        tasks.drain_sync_outbox(self.root, bridge.consume_board_intent)
        task_id = tasks.load(self.root)["tasks"][0]["id"]
        tasks.retitle_task(str(self.root), task_id, "After")
        claimed = tasks.claim_sync_event(str(self.root), "crashed-worker", now=100.0, lease_seconds=10.0)
        assert claimed is not None
        self.assertTrue(bridge.consume_board_intent(claimed))

        replayed = tasks.claim_sync_event(str(self.root), "replay-worker", now=111.0)
        assert replayed is not None
        self.assertTrue(bridge.consume_board_intent(replayed))
        self.assertTrue(
            tasks.ack_sync_event(
                str(self.root), replayed["operation_id"], replayed["lease"]["token"]
            )
        )

        conn = get_db_connection(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE operation_id=?",
                (claimed["operation_id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(1, count)
        self.assertEqual([], tasks.load(self.root)["sync_outbox"])

    def test_sqlite_command_before_board_effect_replays_from_sqlite_outbox(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        tasks_v0 = [self.snapshot("T-00000001", "pending")]
        board = {"next_id": 2, "tasks": tasks_v0, "sync_outbox": [], "sync_correlations": {}}
        board_path.write_text(json.dumps(board), encoding="utf-8")
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "v3-op-done",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )

        self.assertEqual(1, bridge.drain_board_commands())

        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("done", board["tasks"][0]["state"])
        self.assertEqual([], bridge.event_store.pending_board_commands())

    def test_board_effect_before_sqlite_ack_is_reread_without_duplicate_mutation(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "blocked", stage="waiting")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "v3-op-unblock",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "PENDING"},
        )
        self.assertEqual(
            "U",
            bridge.reconcile_v3_to_board(
                "T-00000001", "PENDING", operation_id="v3-op-unblock"
            ),
        )

        self.assertEqual(1, bridge.drain_board_commands())

        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])
        self.assertEqual([], bridge._tasks_module().load(self.root)["sync_outbox"])  # la VUE (T-00001058, O2)
        self.assertEqual([], bridge.event_store.pending_board_commands())

    def test_divergence_is_failed_and_left_pending_for_explicit_delta(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        original = self.snapshot("T-00000001", "pending")
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [original],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "v3-op-divergence",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "IN_DEV"},
        )

        self.assertEqual(0, bridge.drain_board_commands())

        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual(original, board["tasks"][0])
        self.assertEqual(1, len(bridge.event_store.pending_board_commands()))
        events = bridge.event_store.get_task_events("T-00000001")
        self.assertEqual("BOARD_COMMAND_FAILED", events[-1]["event_type"])

    def test_create_retitle_crash_before_ack_replays_without_duplicate(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        payload = {
            "board_task_id": "T-AUTHORIZED-CREATE",
            "status": "PENDING",
            "create_authorized": True,
            "create_title": "Created once",
            "create_owner": "dev-multi",
            "v3_task_id": "V3-CREATE-1",
        }
        bridge.event_store.enqueue_board_command(
            "v3-create-op", EventType.BOARD_COMMAND_REQUESTED, payload
        )
        self.assertEqual(
            "CREATE",
            bridge.reconcile_v3_to_board(operation_id="v3-create-op", **payload),
        )
        self.assertFalse(bridge.event_store.is_board_command_acked("v3-create-op"))
        tasks = bridge._tasks_module()
        data = tasks.load(self.root)
        created_id = data["tasks"][0]["id"]
        with tasks.suppress_sync("retitle-during-crash"):
            tasks.retitle_task(str(self.root), created_id, "Retitled before replay")

        # Simulated crash: no SQLite ACK. Replaying the same command must find
        # the operation correlation instead of allocating another board id.
        self.assertEqual(1, bridge.drain_board_commands())
        self.assertTrue(bridge.event_store.is_board_command_acked("v3-create-op"))

        replayed = tasks.load(self.root)
        self.assertEqual(1, len(replayed["tasks"]))
        self.assertEqual(created_id, replayed["sync_correlations"]["v3-create-op"]["board_task_id"])
        link = bridge.event_store.get_board_link(created_id)
        self.assertEqual("V3-CREATE-1", link["v3_task_id"])
        self.assertEqual("v3-create-op", link["create_operation_id"])

    def test_distinct_create_operation_recovers_creator_identity_after_crash(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        payload = {
            "board_task_id": "T-AUTHORIZED-CREATE",
            "status": "PENDING",
            "create_authorized": True,
            "create_title": "Created once across retries",
            "create_owner": "dev-multi",
            "v3_task_id": "V3-CREATE-STABLE",
        }
        with mock.patch.object(
            bridge.event_store,
            "link_board_task",
            side_effect=RuntimeError("crash before SQLite finalization"),
        ):
            with self.assertRaisesRegex(RuntimeError, "crash before SQLite finalization"):
                bridge.reconcile_v3_to_board(operation_id="create-attempt-1", **payload)

        tasks = bridge._tasks_module()
        after_crash = tasks.load(self.root)
        self.assertEqual(1, len(after_crash["tasks"]))
        created_id = after_crash["tasks"][0]["id"]

        self.assertEqual(
            "CREATE",
            bridge.reconcile_v3_to_board(operation_id="create-attempt-2", **payload),
        )

        recovered = tasks.load(self.root)
        self.assertEqual(1, len(recovered["tasks"]))
        self.assertEqual(
            created_id,
            recovered["sync_correlations"]["create-attempt-1"]["board_task_id"],
        )
        self.assertEqual(
            created_id,
            recovered["sync_correlations"]["create-attempt-2"]["board_task_id"],
        )
        link = bridge.event_store.get_board_link(created_id)
        self.assertEqual("V3-CREATE-STABLE", link["v3_task_id"])
        self.assertEqual("create-attempt-1", link["create_operation_id"])

    def test_delta_replay_links_exactly_one_task(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        payload = {
            "board_task_id": "T-DELETED-ORIGINAL",
            "status": "OUTDATED_REQUIRES_REFACTOR",
            "delta_authorized": True,
            "delta_title": "One delta",
            "delta_owner": "dev-multi",
            "delta_v3_task_id": "V3-DELTA-1",
        }

        for _ in range(2):
            self.assertEqual(
                "DELTA",
                bridge.reconcile_v3_to_board(operation_id="v3-delta-op", **payload),
            )

        tasks = bridge._tasks_module()
        data = tasks.load(self.root)
        self.assertEqual(1, len(data["tasks"]))
        delta_id = data["tasks"][0]["id"]
        self.assertEqual(delta_id, data["sync_correlations"]["v3-delta-op"]["board_task_id"])
        self.assertEqual("V3-DELTA-1", bridge.event_store.get_board_link(delta_id)["v3_task_id"])

    def test_distinct_delta_operations_converge_on_one_v3_identity(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        payload = {
            "board_task_id": "T-DELETED-ORIGINAL",
            "status": "OUTDATED_REQUIRES_REFACTOR",
            "delta_authorized": True,
            "delta_title": "One stable delta",
            "delta_owner": "dev-multi",
            "delta_v3_task_id": "V3-DELTA-STABLE",
        }
        self.assertEqual(
            "DELTA",
            bridge.reconcile_v3_to_board(operation_id="delta-attempt-1", **payload),
        )
        second_error = None
        second_result = None
        try:
            second_result = bridge.reconcile_v3_to_board(
                operation_id="delta-attempt-2", **payload
            )
        except Exception as exc:  # captured so RED reports the observable state too
            second_error = type(exc).__name__

        tasks = bridge._tasks_module()
        data = tasks.load(self.root)
        correlations = data["sync_correlations"]
        task_ids = [task["id"] for task in data["tasks"]]
        correlated_ids = {
            correlations[operation_id]["board_task_id"]
            for operation_id in ("delta-attempt-1", "delta-attempt-2")
        }
        self.assertEqual(
            (None, "DELTA", 1, 1),
            (second_error, second_result, len(task_ids), len(correlated_ids)),
        )

    def test_request_verdict_is_for_current_operation_not_old_ack(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "old-noop",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "PENDING"},
        )

        delivered = bridge.request_v3_to_board(
            "current-divergence", "T-00000001", "IN_DEV"
        )

        self.assertFalse(delivered)
        self.assertTrue(bridge.event_store.is_board_command_acked("old-noop"))
        self.assertFalse(bridge.event_store.is_board_command_acked("current-divergence"))

    def test_bootstrap_drains_file_backlog_before_first_v3_command(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.write_board_backlog()
        self.assertFalse(self.db_path.exists())

        bridge = BoardBridge(self.db_path, self.root)
        delivered = bridge.request_v3_to_board(
            "v3-after-bootstrap", "T-00000001", "PENDING"
        )

        self.assertTrue(delivered)
        self.assertEqual([], bridge._tasks_module().load(self.root)["sync_outbox"])  # la VUE (T-00001058, O2)
        events = bridge.event_store.get_task_events("T-00000001")
        self.assertLess(
            next(i for i, event in enumerate(events) if event["operation_id"] == "board-create"),
            next(
                i
                for i, event in enumerate(events)
                if event["operation_id"] == "v3-after-bootstrap"
            ),
        )

    def test_existing_db_backlog_drains_before_v3_command(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        EventStore(self.db_path)
        board_path = self.write_board_backlog("board-create-existing-db")

        bridge = BoardBridge(self.db_path, self.root)
        delivered = bridge.request_v3_to_board(
            "v3-after-existing-db-backlog", "T-00000001", "PENDING"
        )

        self.assertTrue(delivered)
        self.assertEqual([], bridge._tasks_module().load(self.root)["sync_outbox"])  # la VUE (T-00001058, O2)
        events = bridge.event_store.get_task_events("T-00000001")
        self.assertLess(
            next(
                i
                for i, event in enumerate(events)
                if event["operation_id"] == "board-create-existing-db"
            ),
            next(
                i
                for i, event in enumerate(events)
                if event["operation_id"] == "v3-after-existing-db-backlog"
            ),
        )

    def test_v3_command_is_refused_while_board_backlog_is_not_drainable(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.write_board_backlog("stuck-board-intent")
        bridge = BoardBridge(self.db_path, self.root)

        with mock.patch.object(bridge, "consume_board_intent", return_value=False):
            delivered = bridge.request_v3_to_board(
                "must-not-enqueue", "T-00000001", "PENDING"
            )

        self.assertFalse(delivered)
        self.assertEqual(
            "stuck-board-intent",
            bridge._tasks_module().load(self.root)["sync_outbox"][0][
                "operation_id"
            ],
        )
        conn = get_db_connection(self.db_path)
        try:
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM board_sync_outbox WHERE operation_id=?",
                    ("must-not-enqueue",),
                ).fetchone()[0],
            )
        finally:
            conn.close()

    def test_running_replaced_without_projection_is_failed(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        bridge = BoardBridge(self.db_path, self.root)
        running = self.snapshot("T-UNLINKED", "running", stage="dev-multi")
        pending = self.snapshot("T-UNLINKED", "pending")

        self.assertTrue(
            bridge.consume_board_intent(
                self.intent(
                    "replace-without-projection",
                    before=running,
                    after=pending,
                    event_kind="BOARD_RUNNING_REPLACED",
                )
            )
        )

        self.assertIsNone(bridge.event_store.get_board_link("T-UNLINKED"))
        events = bridge.event_store.get_task_events("T-UNLINKED")
        self.assertEqual("BOARD_COMMAND_FAILED", events[-1]["event_type"])

    def test_sqlite_ack_and_ack_event_roll_back_together(self) -> None:
        store = EventStore(self.db_path)
        store.enqueue_board_command(
            "ack-boundary",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-1", "status": "PENDING"},
        )
        claimed = store.claim_board_command("worker", now=100.0, lease_seconds=10.0)
        assert claimed is not None
        with mock.patch.object(
            store,
            "_insert_board_ack_event",
            side_effect=RuntimeError("crash at ACK boundary"),
        ):
            with self.assertRaisesRegex(RuntimeError, "ACK boundary"):
                store.ack_board_command_with_event(
                    "ack-boundary",
                    claimed["lease_token"],
                    {"board_task_id": "T-1", "status": "PENDING"},
                    now=100.0,
                )

        self.assertFalse(store.is_board_command_acked("ack-boundary"))
        events = store.get_task_events("T-1")
        self.assertFalse(any(event["event_type"] == "BOARD_COMMAND_ACKED" for event in events))

    def test_two_sqlite_drainers_claim_one_command_once(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        first = BoardBridge(self.db_path, self.root)
        second = BoardBridge(self.db_path, self.root)
        first.event_store.enqueue_board_command(
            "concurrent-command",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        rendezvous = threading.Barrier(2)
        calls: list[str] = []
        results: list[int] = []

        def wrap(bridge: BoardBridge):
            original = bridge.reconcile_v3_to_board

            def coordinated(*args: object, **kwargs: object) -> str:
                calls.append(str(kwargs.get("operation_id")))
                try:
                    rendezvous.wait(timeout=0.5)
                except threading.BrokenBarrierError:
                    pass
                return original(*args, **kwargs)

            return coordinated

        with mock.patch.object(first, "reconcile_v3_to_board", side_effect=wrap(first)), mock.patch.object(
            second, "reconcile_v3_to_board", side_effect=wrap(second)
        ):
            threads = [
                threading.Thread(target=lambda b=bridge: results.append(b.drain_board_commands()))
                for bridge in (first, second)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3.0)

        self.assertEqual(1, len(calls))
        self.assertEqual(1, sum(results))
        self.assertTrue(first.event_store.is_board_command_acked("concurrent-command"))
        events = first.event_store.get_task_events("T-00000001")
        self.assertEqual(
            1,
            sum(event["event_type"] == "BOARD_COMMAND_ACKED" for event in events),
        )

    def test_sqlite_fifo_head_lease_blocks_later_command_until_expired_or_released(self) -> None:
        store = EventStore(self.db_path)
        for operation_id, task_id in (("fifo-head", "T-1"), ("fifo-tail", "T-2")):
            store.enqueue_board_command(
                operation_id,
                EventType.BOARD_COMMAND_REQUESTED,
                {"board_task_id": task_id, "status": "PENDING"},
            )
        head = store.claim_board_command("worker-a", now=100.0, lease_seconds=10.0)
        self.assertEqual("fifo-head", head["operation_id"])
        self.assertIsNone(store.claim_board_command("worker-b", now=101.0))
        expired = store.claim_board_command("worker-b", now=111.0, lease_seconds=10.0)
        self.assertEqual("fifo-head", expired["operation_id"])
        self.assertTrue(
            store.release_board_command("fifo-head", expired["lease_token"], "retry head")
        )
        released = store.claim_board_command("worker-c", now=112.0)
        self.assertEqual("fifo-head", released["operation_id"])
        self.assertTrue(
            store.ack_board_command_with_event(
                "fifo-head",
                released["lease_token"],
                {"board_task_id": "T-1", "status": "PENDING"},
                now=112.0,
            )
        )
        tail = store.claim_board_command("worker-c", now=113.0)
        self.assertEqual("fifo-tail", tail["operation_id"])

    def test_expired_sqlite_lease_cannot_mutate_or_ack(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "expired-worker",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        claimed = bridge.event_store.claim_board_command(
            "worker", now=100.0, lease_seconds=1.0
        )
        self.assertFalse(
            bridge.event_store.is_board_command_active(
                "expired-worker", claimed["lease_token"], now=102.0
            )
        )
        self.assertEqual(
            "CANCELLED",
            bridge.reconcile_v3_to_board(
                "T-00000001",
                "COMPLETED",
                operation_id="expired-worker",
                delivery_lease_token=claimed["lease_token"],
            ),
        )
        self.assertFalse(
            bridge.event_store.ack_board_command_with_event(
                "expired-worker",
                claimed["lease_token"],
                {"board_task_id": "T-00000001", "status": "COMPLETED"},
                now=102.0,
            )
        )
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])

    def test_renew_board_command_lease_rejects_already_expired_lease(self) -> None:
        store = EventStore(self.db_path)
        store.enqueue_board_command(
            "expired-renewal",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-1", "status": "PENDING"},
        )
        claimed = store.claim_board_command(
            "worker", now=100.0, lease_seconds=1.0
        )

        self.assertFalse(
            store.renew_board_command_lease(
                "expired-renewal", claimed["lease_token"], lease_seconds=30.0
            )
        )

    def test_mutating_lease_operations_sample_clock_after_write_lock(self) -> None:
        store = EventStore(self.db_path)
        store.enqueue_board_command(
            "clock-order",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-1", "status": "PENDING"},
        )
        real_time = time.time

        def invoke_after_begin(callback: object) -> object:
            state = {"begun": False}

            class RecordingConnection:
                def __init__(self, connection: sqlite3.Connection) -> None:
                    self.connection = connection

                def execute(self, statement: str, *args: object) -> sqlite3.Cursor:
                    cursor = self.connection.execute(statement, *args)
                    if statement.strip().upper() == "BEGIN IMMEDIATE":
                        state["begun"] = True
                    return cursor

                def __getattr__(self, name: str) -> object:
                    return getattr(self.connection, name)

            def clock() -> float:
                self.assertTrue(state["begun"])
                return real_time()

            with mock.patch(
                "agentic_v3.db.event_store.get_db_connection",
                side_effect=lambda path: RecordingConnection(get_db_connection(path)),
            ), mock.patch("agentic_v3.db.event_store.time.time", side_effect=clock):
                return callback()  # type: ignore[operator]

        claimed = invoke_after_begin(lambda: store.claim_board_command("worker"))
        self.assertIsInstance(claimed, dict)
        lease_token = claimed["lease_token"]  # type: ignore[index]
        self.assertTrue(
            invoke_after_begin(
                lambda: store.renew_board_command_lease("clock-order", lease_token)
            )
        )
        self.assertTrue(
            invoke_after_begin(
                lambda: store.ack_board_command_with_event(
                    "clock-order",
                    lease_token,
                    {"board_task_id": "T-1", "status": "PENDING"},
                )
            )
        )

    def test_reconcile_renews_lease_across_slow_board_mutation_and_blocks_reclaim(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "slow-board-effect",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        # Time is DRIVEN from this test alone: no wall-clock TTL decides the
        # verdict, so an eight-burner saturation can no longer starve the
        # initial :183 renew into a false reclaim (SYM-313 flake, 1 red out of
        # 12 under load, T-00000273). The fake clock is anchored +3600 s ahead
        # of real time; every real-clock guard in the store (renew :627, active
        # :713, ack :719) is thereby trivially satisfied and the delivery lease
        # expires ONLY when this test calls clock_advance(). Same algebra as the
        # heartbeat test below (SYM-314): renew_board_command_lease carries no
        # now= seam, so short_renew COMPENSATES — it asks the real store for a
        # lease whose real expiry lands on clock.now + _FAKE_RENEW_TTL. renew
        # holds a single time.time() (in renew_board_command_lease) serving both
        # its guard and its expiry, so the wrapper's algebra is exact to the
        # delta between two adjacent reads, and a machine freeze only pushes the
        # fake expiry LATER — the harmless direction.
        #
        # NO advance_mark here, and the absence is STRUCTURAL, not an oversight
        # (L-00000223). SYM-314 needs one because its verdict rides on a renewal
        # that must have happened AFTER the advance; this test does not. Two TTLs
        # order the whole property: the delivery lease is claimed at
        # _FAKE_CLAIM_TTL = 10 s, reconcile's FIRST act renews it (:183), and the
        # advance of 15 s steps PAST that original expiry but never past the
        # renewed one. Because EVERY compensated renewal — the four sites
        # :183 / :197 / :213 / :262, all covered by this single instance patch —
        # writes an expiry >= anchor + _FAKE_RENEW_TTL (600 s) > anchor + 15, the
        # competitor's claim is refused under any interleaving. A pre-advance
        # expiry left BEHIND the reclaim instant — the L-00000223 defect — is
        # structurally impossible here, which is exactly what dispenses with the
        # mark.
        _FAKE_CLAIM_TTL = 10.0
        _FAKE_RENEW_TTL = 600.0

        clock_lock = threading.Lock()
        fake_now = [time.time() + 3600.0]

        def clock_now() -> float:
            with clock_lock:
                return fake_now[0]

        def clock_advance(seconds: float) -> None:
            with clock_lock:
                fake_now[0] += seconds

        claimed = bridge.event_store.claim_board_command(
            "slow-worker", now=clock_now(), lease_seconds=_FAKE_CLAIM_TTL
        )
        tasks = bridge._tasks_module()
        original_set_state = tasks.set_state
        original_renew = bridge.event_store.renew_board_command_lease
        mutation_started = threading.Event()
        release_mutation = threading.Event()
        result: list[str] = []

        def short_renew(
            operation_id: str,
            lease_token: str,
            lease_seconds: float = 30.0,
        ) -> bool:
            compensated = (clock_now() + _FAKE_RENEW_TTL) - time.time()
            return original_renew(
                operation_id, lease_token, lease_seconds=compensated
            )

        def delayed_set_state(*args: object, **kwargs: object) -> str:
            mutation_started.set()
            release_mutation.wait(timeout=_THREAD_SYNC_TIMEOUT)
            return original_set_state(*args, **kwargs)

        with mock.patch.object(
            bridge.event_store,
            "renew_board_command_lease",
            side_effect=short_renew,
        ), mock.patch.object(tasks, "set_state", side_effect=delayed_set_state):
            worker = threading.Thread(
                target=lambda: result.append(
                    bridge.reconcile_v3_to_board(
                        "T-00000001",
                        "COMPLETED",
                        operation_id="slow-board-effect",
                        delivery_lease_token=claimed["lease_token"],
                    )
                )
            )
            worker.start()
            self.assertTrue(mutation_started.wait(timeout=_THREAD_SYNC_TIMEOUT))
            # Advance past the original _FAKE_CLAIM_TTL (10 s) expiry but NOT past
            # the renewed _FAKE_RENEW_TTL (600 s) one: 10 < 15 < 600. The :183
            # renew has already fired synchronously before set_state was reached,
            # so the delivery lease now expires at anchor + 600.
            #
            # Falsification (kept honest by the § Tests non-vacuity arm): set
            # _FAKE_RENEW_TTL below 15 and this assertion goes red — the renewed
            # expiry then sits BEHIND the reclaim instant and the competitor
            # claims. That arm is DETERMINISTIC only because delivery_lease_seconds
            # stays at its 30 s default: the heartbeat interval is lease / 3 = 10 s
            # of REAL time (board_bridge.py:192), so the background heartbeat
            # (:197) cannot fire a second, compensating renewal between this
            # advance and the reclaim — the reconcile is parked in set_state. Drop
            # that default (force a sub-second delivery lease) and the heartbeat
            # could re-extend the lease and mask the falsification.
            clock_advance(15.0)
            # try/finally, not two plain statements: if the assertion below goes
            # red, the worker is STILL parked in release_mutation.wait() and the
            # non-daemon thread would outlive the failing test by up to
            # _THREAD_SYNC_TIMEOUT before landing a real board mutation — after
            # the patches have been restored. A failing test must not leave a
            # write in flight behind it.
            try:
                self.assertIsNone(
                    bridge.event_store.claim_board_command(
                        "competing-worker", now=clock_now()
                    )
                )
            finally:
                release_mutation.set()
                worker.join(timeout=_THREAD_SYNC_TIMEOUT)

        self.assertFalse(worker.is_alive())
        self.assertEqual(["D"], result)
        # ack goes through the real (unpatched) renew guard against WALL time
        # (in renew_board_command_lease); the final :262 renew left the real expiry at
        # roughly anchor + 600 ~= real + 4200 s, so it passes.
        self.assertTrue(
            bridge.event_store.ack_board_command_with_event(
                "slow-board-effect",
                claimed["lease_token"],
                {"board_task_id": "T-00000001", "status": "COMPLETED"},
            )
        )
        self.assertTrue(
            bridge.event_store.is_board_command_acked("slow-board-effect")
        )
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("done", board["tasks"][0]["state"])

    def test_heartbeat_keeps_renewed_lease_alive_past_expiry_during_mutation(self) -> None:
        import agentic_v3.reconciliation.board_bridge as board_bridge_module
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        competitor = EventStore(self.db_path)
        bridge.event_store.enqueue_board_command(
            "heartbeat-long-effect",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        tasks = bridge._tasks_module()
        original_claim = bridge.event_store.claim_board_command
        original_renew = bridge.event_store.renew_board_command_lease
        original_ack = bridge.event_store.ack_board_command_with_event
        original_reconcile = bridge.reconcile_v3_to_board
        original_set_state = tasks.set_state

        # Time is DRIVEN from this test alone: no wall-clock TTL decides the
        # verdict, so an eight-burner saturation can no longer starve the
        # heartbeat into a false reclaim (SYM-314 flake, T-00000261). The fake
        # clock is anchored +3600 s ahead of real time; every real-clock guard
        # in the store is thereby trivially satisfied and the lease expires
        # ONLY when this test calls clock_advance(). renew_board_command_lease
        # carries no now= seam, so short_renew COMPENSATES: it asks the real
        # store for a lease whose real expiry lands on clock.now + _FAKE_TTL.
        # renew holds a single time.time() (in renew_board_command_lease) serving
        # both its guard and its expiry, so the wrapper's algebra is exact to
        # the delta between two adjacent reads, and a machine freeze only pushes
        # the fake expiry LATER — the harmless direction.
        _FAKE_TTL = 10.0
        # Real heartbeat cadence forced onto reconcile through its EXISTING
        # delivery_lease_seconds parameter (board_bridge.py:157): without it
        # drain would derive ~3610 s from the fake expiry (:526-528), the
        # interval would collapse to ~1203 s (:192) and the heartbeat would
        # sleep past the test. 0.06 s keeps the production cadence machinery
        # (:182/:192/:194-207) genuinely exercised at speed.
        _FORCED_DELIVERY_LEASE = 0.06

        clock_lock = threading.Lock()
        fake_now = [time.time() + 3600.0]
        # Fake instant the advance landed on, published UNDER THE SAME LOCK as
        # the clock itself. A renewal is "post-advance" only if the instant it
        # READ is at or after that mark — testing an Event set beside the clock
        # would signal a renewal that read the clock BEFORE the advance and
        # merely returned after it, whose expiry (t0+_FAKE_TTL) then sits BEHIND
        # the competitor's claim instant and lets the reclaim through. Measured:
        # 1 red out of 12 under eight-burner saturation.
        advance_mark: list[float | None] = [None]

        def clock_read() -> tuple[float, float | None]:
            with clock_lock:
                return fake_now[0], advance_mark[0]

        def clock_now() -> float:
            with clock_lock:
                return fake_now[0]

        def clock_advance(seconds: float) -> None:
            with clock_lock:
                fake_now[0] += seconds
                advance_mark[0] = fake_now[0]

        renewed_post_advance = threading.Event()
        mutation_started = threading.Event()
        release_mutation = threading.Event()
        heartbeat_alive_at_ack: list[bool] = []
        heartbeat_intervals: list[float] = []
        result: list[int] = []

        # Cadence capture WITHOUT any wall-clock measurement: it records the
        # argument handed to stop_heartbeat.wait(), never elapsed time. Only
        # board_bridge's own Events are recording; threading.Thread is delegated
        # to the real module, so the heartbeat thread's internal Events stay
        # real and the sole positive-timeout wait observed is the heartbeat's.
        real_threading = board_bridge_module.threading

        class _RecordingEvent(real_threading.Event):
            def wait(self, timeout=None):  # type: ignore[override]
                if timeout is not None and timeout > 0:
                    heartbeat_intervals.append(float(timeout))
                return super().wait(timeout)

        class _RecordingThreading:
            Event = _RecordingEvent

            def __getattr__(self, name: str):
                return getattr(real_threading, name)

        def short_claim(owner: str, **kwargs: object):
            return original_claim(
                owner, now=clock_now(), lease_seconds=_FAKE_TTL, **kwargs
            )

        def short_renew(
            operation_id: str,
            lease_token: str,
            lease_seconds: float = 30.0,
        ) -> bool:
            at, mark = clock_read()
            compensated = (at + _FAKE_TTL) - time.time()
            renewed = original_renew(
                operation_id, lease_token, lease_seconds=compensated
            )
            if renewed and mark is not None and at >= mark:
                renewed_post_advance.set()
            return renewed

        def short_reconcile(*args: object, **kwargs: object) -> str:
            kwargs["delivery_lease_seconds"] = _FORCED_DELIVERY_LEASE
            return original_reconcile(*args, **kwargs)

        def delayed_set_state(*args: object, **kwargs: object) -> str:
            mutation_started.set()
            release_mutation.wait(timeout=_THREAD_SYNC_TIMEOUT)
            return original_set_state(*args, **kwargs)

        def ack_after_heartbeat(*args: object, **kwargs: object) -> bool:
            heartbeat_alive_at_ack.append(
                any(
                    thread.name == "board-lease-heartbeat-heartbeat-long-effect"
                    for thread in threading.enumerate()
                )
            )
            return original_ack(*args, **kwargs)

        with mock.patch.object(
            board_bridge_module, "threading", _RecordingThreading()
        ), mock.patch.object(
            bridge, "reconcile_v3_to_board", side_effect=short_reconcile
        ), mock.patch.object(
            bridge.event_store, "claim_board_command", side_effect=short_claim
        ), mock.patch.object(
            bridge.event_store, "renew_board_command_lease", side_effect=short_renew
        ), mock.patch.object(
            bridge.event_store,
            "ack_board_command_with_event",
            side_effect=ack_after_heartbeat,
        ), mock.patch.object(tasks, "set_state", side_effect=delayed_set_state):
            worker = threading.Thread(
                target=lambda: result.append(bridge.drain_board_commands())
            )
            worker.start()
            self.assertTrue(mutation_started.wait(timeout=_THREAD_SYNC_TIMEOUT))
            # Advance the fake clock past the initial t0+_FAKE_TTL expiry, then
            # WAIT for a heartbeat renewal that happened AFTER the advance. This
            # is what makes the advance load-bearing: skip it (or break renewal)
            # and no post-advance renewal is ever signalled — red by construction.
            clock_advance(15.0)
            self.assertTrue(
                renewed_post_advance.wait(timeout=_THREAD_SYNC_TIMEOUT)
            )
            reclaimed = competitor.claim_board_command(
                "competing-worker", now=clock_now(), lease_seconds=0.06
            )
            release_mutation.set()
            worker.join(timeout=_THREAD_SYNC_TIMEOUT)

        self.assertFalse(worker.is_alive())
        self.assertIsNone(reclaimed)
        self.assertEqual([1], result)
        self.assertEqual([False], heartbeat_alive_at_ack)
        self.assertTrue(
            bridge.event_store.is_board_command_acked("heartbeat-long-effect")
        )
        # Cadence pin (T-00000261 C1): the heartbeat interval stays strictly
        # below the lease it defends. Deterministic — it inspects the argument
        # handed to wait(), never elapsed time — so a regression of the :192
        # formula from lease/3 to lease*3 (which the fake-clock decoupling would
        # otherwise let pass green) fails here instead of shipping silently.
        self.assertTrue(heartbeat_intervals)
        self.assertTrue(
            all(interval < _FORCED_DELIVERY_LEASE for interval in heartbeat_intervals),
            msg=f"heartbeat cadence regressed: {heartbeat_intervals}",
        )

    def test_heartbeat_failure_fences_ack_after_mutation(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        bridge.event_store.enqueue_board_command(
            "heartbeat-fence",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        tasks = bridge._tasks_module()
        original_claim = bridge.event_store.claim_board_command
        original_renew = bridge.event_store.renew_board_command_lease
        original_set_state = tasks.set_state
        renew_calls = 0
        mutation_started = threading.Event()

        def short_claim(owner: str, **kwargs: object):
            return original_claim(owner, lease_seconds=0.2, **kwargs)

        def fail_second_renewal(
            operation_id: str,
            lease_token: str,
            lease_seconds: float = 30.0,
        ) -> bool:
            nonlocal renew_calls
            renew_calls += 1
            if renew_calls == 1:
                return original_renew(operation_id, lease_token, lease_seconds=0.2)
            return False

        def delayed_set_state(*args: object, **kwargs: object) -> str:
            mutation_started.set()
            time.sleep(0.12)
            return original_set_state(*args, **kwargs)

        with mock.patch.object(
            bridge.event_store, "claim_board_command", side_effect=short_claim
        ), mock.patch.object(
            bridge.event_store,
            "renew_board_command_lease",
            side_effect=fail_second_renewal,
        ), mock.patch.object(tasks, "set_state", side_effect=delayed_set_state):
            result = bridge.drain_board_commands()

        self.assertTrue(mutation_started.is_set())
        self.assertGreaterEqual(renew_calls, 2)
        self.assertEqual(0, result)
        self.assertFalse(bridge.event_store.is_board_command_acked("heartbeat-fence"))
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])

    def test_final_renewal_closes_delayed_ack_reclaim_window(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        competitor = EventStore(self.db_path)
        bridge.event_store.enqueue_board_command(
            "delayed-ack",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "COMPLETED"},
        )
        tasks = bridge._tasks_module()
        original_claim = bridge.event_store.claim_board_command
        original_renew = bridge.event_store.renew_board_command_lease
        original_ack = bridge.event_store.ack_board_command_with_event
        original_set_state = tasks.set_state
        original_join = threading.Thread.join
        delivery_renewal_phases: list[str] = []
        mutation_started = threading.Event()
        heartbeat_joined = threading.Event()
        ack_started = threading.Event()
        reclaim_finished = threading.Event()
        reclaimed: list[object] = []
        result: list[int] = []

        def short_claim(owner: str, **kwargs: object):
            return original_claim(owner, lease_seconds=0.3, **kwargs)

        def renewal_windows(
            operation_id: str,
            lease_token: str,
            lease_seconds: float = 30.0,
        ) -> bool:
            is_heartbeat = threading.current_thread().name.startswith(
                "board-lease-heartbeat-"
            )
            if is_heartbeat:
                phase = "heartbeat"
            elif not mutation_started.is_set():
                phase = "initial"
            elif heartbeat_joined.is_set():
                phase = "final"
            else:
                phase = "guard"
            if not is_heartbeat:
                delivery_renewal_phases.append(phase)
            renewed_seconds = 1.2 if phase == "final" else 0.3
            return original_renew(
                operation_id,
                lease_token,
                lease_seconds=renewed_seconds,
            )

        def delayed_set_state(*args: object, **kwargs: object) -> str:
            mutation_started.set()
            time.sleep(0.5)
            return original_set_state(*args, **kwargs)

        def observe_heartbeat_join(
            thread: threading.Thread,
            timeout: float | None = None,
        ) -> None:
            original_join(thread, timeout=timeout)
            if thread.name == "board-lease-heartbeat-delayed-ack":
                heartbeat_joined.set()

        def delayed_ack(*args: object, **kwargs: object) -> bool:
            ack_started.set()
            self.assertTrue(reclaim_finished.wait(timeout=2.0))
            return original_ack(*args, **kwargs)

        def attempt_reclaim() -> None:
            self.assertTrue(ack_started.wait(timeout=2.0))
            time.sleep(0.4)
            reclaimed.append(
                competitor.claim_board_command("competing-worker", lease_seconds=0.3)
            )
            reclaim_finished.set()

        with mock.patch.object(
            threading.Thread, "join", new=observe_heartbeat_join
        ), mock.patch.object(
            bridge.event_store, "claim_board_command", side_effect=short_claim
        ), mock.patch.object(
            bridge.event_store,
            "renew_board_command_lease",
            side_effect=renewal_windows,
        ), mock.patch.object(
            bridge.event_store,
            "ack_board_command_with_event",
            side_effect=delayed_ack,
        ), mock.patch.object(tasks, "set_state", side_effect=delayed_set_state):
            competitor_thread = threading.Thread(target=attempt_reclaim)
            worker = threading.Thread(
                target=lambda: result.append(bridge.drain_board_commands())
            )
            competitor_thread.start()
            worker.start()
            worker.join(timeout=5.0)
            competitor_thread.join(timeout=5.0)

        self.assertFalse(worker.is_alive())
        self.assertFalse(competitor_thread.is_alive())
        self.assertEqual([None], reclaimed)
        self.assertTrue(heartbeat_joined.is_set())
        self.assertEqual("initial", delivery_renewal_phases[0])
        self.assertEqual("final", delivery_renewal_phases[-1])
        # The lease is renewed across three ORDERED epochs — initial (before the
        # mutation starts), guard (mutation in flight, heartbeat still alive) and
        # final (after the heartbeat is joined). HOW MANY renewals land in each
        # epoch is timing-dependent: a slower runner renews more times before the
        # mutation begins — windows-latest observed 3 "initial" where ubuntu sees
        # 1 (the false red this replaces). So assert each epoch's PRESENCE and the
        # strict initial -> guard -> final ORDER, never the per-epoch counts.
        self.assertGreaterEqual(delivery_renewal_phases.count("guard"), 1)
        phase_rank = {"initial": 0, "guard": 1, "final": 2}
        phase_ranks = [phase_rank[phase] for phase in delivery_renewal_phases]
        self.assertEqual(
            phase_ranks,
            sorted(phase_ranks),
            delivery_renewal_phases,
        )
        self.assertEqual([1], result)
        self.assertTrue(bridge.event_store.is_board_command_acked("delayed-ack"))

    def test_stage_with_two_running(self) -> None:
        """T-01M5F728RH : la SECONDE de deux running, acquittée par APPARTENANCE ; bras neufs, sans subTest."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        # PAS de subTest : sous pytest 9, un subTest rouge laisse le nœud parent PASSED.
        for status, stage in (("IN_DEV", "dev"), ("IN_CRITIC", "plan-critic"), ("IN_TEST", "test")):
            root = self.root / status
            board_path = root / ".agents" / "state" / "board" / "TASKS.json"
            board_path.parent.mkdir(parents=True)
            running = [self.snapshot(t, "running", stage="dev-multi") for t in ("T-00000001", "T-00000002")]
            board = {"next_id": 3, "tasks": running, "sync_outbox": [], "sync_correlations": {}}
            board_path.write_text(json.dumps(board), encoding="utf-8")
            bridge, op = BoardBridge(root / "v3.db", root), f"two-running-{status}"
            payload = {"board_task_id": "T-00000002", "status": status}
            bridge.event_store.enqueue_board_command(op, EventType.BOARD_COMMAND_REQUESTED, payload)
            self.assertEqual(1, bridge.drain_board_commands(), status)
            self.assertTrue(bridge.event_store.is_board_command_acked(op), status)
            lus = json.loads(board_path.read_text(encoding="utf-8"))["tasks"]
            vus = [(t["id"], t["state"], t["stage"]) for t in lus]
            attendu = [("T-00000001", "running", "dev-multi"), ("T-00000002", "running", stage)]
            self.assertEqual(attendu, vus, status)

    def test_stage_race_to_pending_is_not_acked(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        tasks_v0 = [self.snapshot("T-00000001", "running", stage="dev-multi")]
        board = {"next_id": 2, "tasks": tasks_v0, "sync_outbox": [], "sync_correlations": {}}
        board_path.write_text(json.dumps(board), encoding="utf-8")
        bridge = BoardBridge(self.db_path, self.root)
        tasks = bridge._tasks_module()
        bridge.event_store.enqueue_board_command(
            "stage-race",
            EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-00000001", "status": "IN_DEV"},
        )
        claimed = threading.Event()
        result: list[int] = []
        original_claim = bridge.event_store.claim_board_command

        def announce_claim(*args: object, **kwargs: object):
            command = original_claim(*args, **kwargs)
            if command is not None:
                claimed.set()
            return command

        with tasks.board_lock(self.root), mock.patch.object(
            bridge.event_store, "claim_board_command", side_effect=announce_claim
        ):
            thread = threading.Thread(target=lambda: result.append(bridge.drain_board_commands()))
            thread.start()
            self.assertTrue(claimed.wait(timeout=2.0))
            data = tasks.load(self.root)
            data["tasks"][0].update(state="pending", stage="")
            tasks.save(self.root, data)
        thread.join(timeout=3.0)

        self.assertEqual([0], result)
        self.assertFalse(bridge.event_store.is_board_command_acked("stage-race"))
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("pending", board["tasks"][0]["state"])
        self.assertEqual("", board["tasks"][0]["stage"])

    def test_block_race_to_done_is_divergent_and_not_acked(self) -> None:
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        board_path = self.root / ".agents" / "state" / "board" / "TASKS.json"
        board_path.parent.mkdir(parents=True)
        board_path.write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [self.snapshot("T-00000001", "pending")],
                    "sync_outbox": [],
                    "sync_correlations": {},
                }
            ),
            encoding="utf-8",
        )
        bridge = BoardBridge(self.db_path, self.root)
        tasks = bridge._tasks_module()
        bridge.event_store.enqueue_board_command(
            "block-race",
            EventType.BOARD_COMMAND_REQUESTED,
            {
                "board_task_id": "T-00000001",
                "status": "BLOCKED_WAITING_HUMAN_DECISION",
            },
        )
        claimed = threading.Event()
        result: list[int] = []
        original_claim = bridge.event_store.claim_board_command

        def announce_claim(*args: object, **kwargs: object):
            command = original_claim(*args, **kwargs)
            if command is not None:
                claimed.set()
            return command

        with tasks.board_lock(self.root), mock.patch.object(
            bridge.event_store, "claim_board_command", side_effect=announce_claim
        ):
            thread = threading.Thread(target=lambda: result.append(bridge.drain_board_commands()))
            thread.start()
            self.assertTrue(claimed.wait(timeout=2.0))
            data = tasks.load(self.root)
            data["tasks"][0].update(state="done", stage="")
            tasks.save(self.root, data)
        thread.join(timeout=3.0)

        self.assertEqual([0], result)
        self.assertFalse(bridge.event_store.is_board_command_acked("block-race"))
        board = json.loads(board_path.read_text(encoding="utf-8"))
        self.assertEqual("done", board["tasks"][0]["state"])
        self.assertEqual("", board["tasks"][0]["stage"])

    # T-00001055 (S-00003347 M1) — une seconde CRÉATION (`before=None`) d'un id déjà
    # lié, sous un AUTRE operation_id, est REFUSÉE et NOMMÉE. W1, W4, W6, W8 prouvent
    # le défaut (rouges sur le réducteur d'avant la garde) ; W2, W3, W5, W7 fixent ce
    # que la garde ne doit PAS changer (verts avant comme après).

    def test_c6_seconde_creation_sous_autre_operation_refusee_et_nommee(self) -> None:
        """W1 (T-00001055) — DRAIN VIF, refus lisible aux TROIS endroits : deux
        créations du MÊME id sous op-A puis op-B. op-B est REFUSÉE (`applied=False`,
        `creation-collision`, l'effet nomme `board_task_id` et le créateur op-A), lien
        et projection restent à op-A, UN `BOARD_COMMAND_FAILED` est écrit ET exporté
        (relu ici comme le relit `git grep --untracked -n creation-collision -- runs/`), et UNE
        ligne stderr nomme l'id et les deux opérations. Rejeu d'op-B : même effet,
        aucune seconde ligne, toujours un FAILED. Bras hostile : `\\n` et `\\x1b` dans
        l'id et les opérations — `!r` garde UNE ligne, sans octet de contrôle brut.
        MUTATIONS : garde retirée (op-B adoptée, owner banc-B) ; ligne stderr retirée ;
        ligne aussi au rejeu dédupliqué ; `'{…}'` au lieu de `!r` ; effet sans
        `board_task_id`."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        failed = EventType.BOARD_COMMAND_FAILED.value

        def nb_failed(operation_id: str) -> int:
            with closing(get_db_connection(self.db_path)) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM events_ledger WHERE operation_id=? AND event_type=?",
                    (operation_id, failed),
                ).fetchone()[0]

        bras = (
            ("nominal", "T-00009101", "op-A", "op-B"),
            ("hostile", "T-\n\x1b[31mX", "op-A\n\x1b[0m", "op-B\n\x1b[0m"),
        )
        # Boucle simple, PAS de subTest : sous pytest 9, un subTest rouge laisse le
        # nœud parent marqué PASSED. Le bras est nommé dans chaque message.
        for nom, tid, op_a, op_b in bras:
            cree_a = {**self.snapshot(tid, "pending"), "owner": "banc-A"}
            cree_b = {**self.snapshot(tid, "pending"), "owner": "banc-B"}
            err = io.StringIO()
            with redirect_stderr(err):
                store.consume_board_intent(self.intent(op_a, before=None, after=cree_a))
                effet = store.consume_board_intent(self.intent(op_b, before=None, after=cree_b))
            self.assertEqual("creation-collision", effet.get("action"), (nom, effet))
            self.assertIs(False, effet["applied"], nom)
            self.assertEqual(op_a, effet["create_operation_id"], nom)
            self.assertEqual(tid, effet["board_task_id"], nom)
            lien = store.get_board_link(tid)
            self.assertEqual(op_a, lien["create_operation_id"], nom)
            # critique B : l'effet exporté désigne la projection du LIEN (celle d'op-A),
            # pas une `BOARD:<op-B>` qui n'existe pas. MUTATION : `v3_task_id` du perdant.
            self.assertEqual(lien["v3_task_id"], effet["v3_task_id"], nom)
            self.assertEqual(
                "banc-A",
                store.get_task_projection(lien["v3_task_id"])["current_assignee"],
                nom,
            )
            self.assertEqual((0, 1), (nb_failed(op_a), nb_failed(op_b)), nom)
            lignes = [l for l in err.getvalue().splitlines() if "creation refusee" in l]
            self.assertEqual(1, len(lignes), (nom, err.getvalue()))
            for ident in (tid, op_a, op_b):
                self.assertIn(repr(ident), lignes[0], nom)
            self.assertNotIn("\x1b", err.getvalue(), nom)
            # LECTURE (réserve S-00003434) : le refus est EXPORTÉ sous runs/.
            refus = [
                json.loads(l["payload_json"])
                for l in self._lignes_export_pour(op_b)
                if l.get("event_type") == failed
            ]
            self.assertEqual(1, len(refus), (nom, refus))
            self.assertEqual(
                ("creation-collision", op_a, tid, op_b),
                (
                    refus[0]["effect"]["action"],
                    refus[0]["effect"]["create_operation_id"],
                    refus[0]["effect"]["board_task_id"],
                    refus[0]["intent"]["operation_id"],
                ),
                nom,
            )
            err_rejeu = io.StringIO()
            with redirect_stderr(err_rejeu):
                rejeu = store.consume_board_intent(self.intent(op_b, before=None, after=cree_b))
            self.assertEqual(effet, rejeu, nom)
            self.assertNotIn("creation refusee", err_rejeu.getvalue(), nom)
            self.assertEqual(1, nb_failed(op_b), nom)

    def test_delta_sous_autre_operation_reste_projete(self) -> None:
        """W2 (T-00001055) — l'adoption d'un lien existant par un DELTA
        (`before≠None`) sous un autre operation_id reste VOULUE : c'est toute mise à
        jour du board. Le résidu M6 (delta de la lignée d'une création refusée) n'est
        PAS épinglé : un témoin qui passerait par le défaut le défendrait. MUTATION :
        garde sans `before is None` -> le delta est refusé, ce témoin rougit."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009102"
        cree = {**self.snapshot(tid, "pending"), "owner": "banc-A"}
        demarre = {**self.snapshot(tid, "running", stage="dev"), "owner": "banc-B"}
        store.consume_board_intent(self.intent("op-1", before=None, after=cree))
        effet = store.consume_board_intent(self.intent("op-2", before=cree, after=demarre))
        self.assertEqual((True, "projected"), (effet["applied"], effet["action"]), effet)
        lien = store.get_board_link(tid)
        self.assertEqual("op-1", lien["create_operation_id"])
        self.assertEqual(
            "banc-B", store.get_task_projection(lien["v3_task_id"])["current_assignee"]
        )
        with closing(get_db_connection(self.db_path)) as conn:
            self.assertEqual(
                0,
                conn.execute(
                    "SELECT COUNT(*) FROM events_ledger WHERE event_type=?",
                    (EventType.BOARD_COMMAND_FAILED.value,),
                ).fetchone()[0],
            )

    def test_premier_intent_vu_before_non_none_cree_le_lien(self) -> None:
        """W3 (T-00001055) — jumeau des 59 liens de runs/ (S-00003378) : le PREMIER
        intent vu d'un id porte `before≠None` et CRÉE le lien, créateur = cette
        opération. MUTATION : règle rejetée « exiger before=None pour créer un lien »
        -> aucun lien, ce témoin rougit."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009103"
        effet = store.consume_board_intent(
            self.intent(
                "op-premier-vu",
                before=self.snapshot(tid, "pending"),
                after=self.snapshot(tid, "running", stage="dev"),
            )
        )
        self.assertEqual((True, "projected"), (effet["applied"], effet["action"]), effet)
        lien = store.get_board_link(tid)
        self.assertIsNotNone(lien)
        self.assertEqual("op-premier-vu", lien["create_operation_id"])

    def test_c6_reconstruction_rend_le_meme_refus_que_le_drain(self) -> None:
        """W4 (T-00001055) — RECONSTRUCTION après un refus VIF, refus lisible à DEUX
        endroits : le FAILED rejoué depuis l'export (apparié, donc ni `faux_failed` ni
        `echecs_sans_failed`) et l'effet d'inbox, IDENTIQUE à l'effet vif. Aucune
        ligne « creation refusee » ici : la ligne est celle du drain. MUTATIONS : garde
        retirée (owner banc-B) ; ligne stderr à la reconstruction ; garde dans
        `consume_board_intent` au lieu du réducteur."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009104"
        store.consume_board_intent(
            self.intent(
                "op-A", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-A"}
            )
        )
        effet_vif = store.consume_board_intent(
            self.intent(
                "op-B", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-B"}
            )
        )
        base = self.root / "rebatie.db"
        rebatie = EventStore(base, project_root=self._racine_export())
        err = io.StringIO()
        with redirect_stderr(err):
            resume = rebatie.reconstruire_depuis_exports(racine=self._racine_export())
        with closing(get_db_connection(base)) as conn:
            effet_rebati = json.loads(
                conn.execute(
                    "SELECT effect_json FROM board_sync_inbox WHERE operation_id=?", ("op-B",)
                ).fetchone()["effect_json"]
            )
            failed_rebatis = conn.execute(
                "SELECT COUNT(*) FROM events_ledger WHERE operation_id=? AND event_type=?",
                ("op-B", EventType.BOARD_COMMAND_FAILED.value),
            ).fetchone()[0]
        self.assertEqual("creation-collision", effet_rebati.get("action"), effet_rebati)
        self.assertEqual(effet_vif, effet_rebati)
        self.assertEqual(
            (0, 0, 0),
            (resume["pont_ecartes"], resume["faux_failed"], resume["echecs_sans_failed"]),
            resume,
        )
        lien = rebatie.get_board_link(tid)
        self.assertEqual("op-A", lien["create_operation_id"])
        self.assertEqual(
            "banc-A", rebatie.get_task_projection(lien["v3_task_id"])["current_assignee"]
        )
        self.assertEqual(1, failed_rebatis)
        self.assertNotIn("creation refusee", err.getvalue())

    def test_creation_sur_lien_tombe_reste_never_resurrect(self) -> None:
        """W5 (T-00001055) — une création sous une opération neuve sur un lien
        TOMBÉ reste `never-resurrect` (T-00001060 compte sur ce nom), sans ligne
        « creation refusee ». MUTATIONS : garde AVANT `never-resurrect` ; ligne
        stderr imprimée aussi pour `never-resurrect`."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009105"
        cree = self.snapshot(tid, "pending")
        store.consume_board_intent(self.intent("op-cree", before=None, after=cree))
        store.consume_board_intent(self.intent("op-supprime", before=cree, after=None))
        err = io.StringIO()
        with redirect_stderr(err):
            effet = store.consume_board_intent(self.intent("op-recree", before=None, after=cree))
        self.assertEqual((False, "never-resurrect"), (effet["applied"], effet["action"]), effet)
        self.assertNotIn("creation refusee", err.getvalue())

    def test_c6_deux_createurs_fusionnes_sans_failed_comptent_un_echec_sans_failed(
        self,
    ) -> None:
        """W6 (T-00001055) — CLONES FUSIONNÉS : chemin de production des clones dont
        les exports se rejoignent (une outbox non drainée et fusionnée passe, elle,
        par W1). Deux bases, un export : chaque clone crée le même id sous sa propre
        opération, aucun ne voit de collision, aucun FAILED n'est écrit. La
        reconstruction de l'export fusionné garde le lien du plus petit ULID, refuse
        la seconde création et la COMPTE : `echecs_sans_failed=1` dans l'annonce, un
        compteur ANONYME — seul l'effet d'inbox nomme les deux opérations. MUTATIONS :
        garde retirée (compte 0) ; garde dans `consume_board_intent`."""
        import io
        from contextlib import redirect_stderr

        tid = "T-00009106"
        clone_a = EventStore(self.root / "clone-a.db", project_root=self._racine_export())
        clone_b = EventStore(self.root / "clone-b.db", project_root=self._racine_export())
        effet_a = clone_a.consume_board_intent(
            self.intent(
                "op-A", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-A"}
            )
        )
        effet_b = clone_b.consume_board_intent(
            self.intent(
                "op-B", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-B"}
            )
        )
        self.assertEqual((True, True), (effet_a["applied"], effet_b["applied"]))
        base = self.root / "fusion.db"
        fusion = EventStore(base, project_root=self._racine_export())
        err = io.StringIO()
        with redirect_stderr(err):
            resume = fusion.reconstruire_depuis_exports(racine=self._racine_export())
        self.assertEqual(1, resume["echecs_sans_failed"], resume)
        self.assertEqual((0, 0), (resume["faux_failed"], resume["pont_ecartes"]), resume)
        lien = fusion.get_board_link(tid)
        self.assertEqual("op-A", lien["create_operation_id"])
        self.assertEqual(
            "banc-A", fusion.get_task_projection(lien["v3_task_id"])["current_assignee"]
        )
        self.assertIn("echecs_sans_failed=1", err.getvalue())
        with closing(get_db_connection(base)) as conn:
            effet = json.loads(
                conn.execute(
                    "SELECT effect_json FROM board_sync_inbox WHERE operation_id=?", ("op-B",)
                ).fetchone()["effect_json"]
            )
        self.assertEqual(
            ("creation-collision", "op-A", tid),
            (effet["action"], effet["create_operation_id"], effet["board_task_id"]),
        )

    def test_meme_operation_dans_le_reducteur_n_est_pas_une_collision(self) -> None:
        """W7 (T-00001055) — appel DIRECT du réducteur avec le MÊME operation_id que
        le créateur : `projected`. L'amont déduplique par l'inbox, mais une
        réinjection de créations (T-00001058) passe par le réducteur : la propriété
        se tient là. MUTATION : garde sans `!= operation_id` -> refus, ce témoin
        rougit."""
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009107"
        store.consume_board_intent(
            self.intent("op-createur", before=None, after=self.snapshot(tid, "pending"))
        )
        with closing(get_db_connection(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                effet = store._reduce_board_intent(
                    cursor,
                    self.intent(
                        "op-createur",
                        before=None,
                        after=self.snapshot(tid, "running", stage="dev"),
                    ),
                )
            finally:
                conn.rollback()
        self.assertEqual((True, "projected"), (effet["applied"], effet["action"]), effet)

    def test_c6_le_refus_est_nomme_meme_quand_l_export_leve_apres_le_commit(self) -> None:
        """W8 (T-00001055) — DRAIN VIF dont l'export LÈVE après le commit (panne
        d'infra, `RunExportError` nu : fail-closed). L'événement et son FAILED sont
        commités ; le rejeu passera par la branche dédupliquée, qui n'imprime rien :
        la ligne doit donc partir AVANT `_flush_export`. MUTATIONS : garde retirée ;
        ligne stderr retirée ; ligne APRÈS `_flush_export`."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.db import run_export
        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009108"
        store.consume_board_intent(
            self.intent(
                "op-A", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-A"}
            )
        )
        err = io.StringIO()
        with redirect_stderr(err), mock.patch.object(
            run_export,
            "auteur_courant",
            side_effect=run_export.RunExportError("panne infra simulee"),
        ):
            with self.assertRaises(run_export.RunExportError):
                store.consume_board_intent(
                    self.intent(
                        "op-B",
                        before=None,
                        after={**self.snapshot(tid, "pending"), "owner": "banc-B"},
                    )
                )
        self.assertIn("creation refusee", err.getvalue())
        self.assertIn(repr("op-B"), err.getvalue())
        with closing(get_db_connection(self.db_path)) as conn:
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM events_ledger WHERE operation_id=? AND event_type=?",
                    ("op-B", EventType.BOARD_COMMAND_FAILED.value),
                ).fetchone()[0],
            )

    def test_c6_aucune_ligne_de_refus_si_la_transaction_est_annulee(self) -> None:
        """W9 (T-00001055, critique B) — la ligne dit « BOARD_COMMAND_FAILED ecrit » : elle ne
        part qu'APRÈS le commit. Le second `_ecrire_evenement` (le FAILED) lève : tout est
        annulé, et stderr ne dit PAS « creation refusee ». MUTATION : ligne imprimée dans le
        `try`, avant le commit."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid = "T-00009109"
        store.consume_board_intent(
            self.intent(
                "op-A", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-A"}
            )
        )
        reel, appels = store._ecrire_evenement, []

        def ecrire(*args, **kwargs):
            appels.append(1)
            if len(appels) == 2:  # 1er appel : l'intent ; 2e : le FAILED
                raise sqlite3.OperationalError("disque plein simule")
            return reel(*args, **kwargs)

        err = io.StringIO()
        with redirect_stderr(err), mock.patch.object(store, "_ecrire_evenement", side_effect=ecrire):
            with self.assertRaises(sqlite3.OperationalError):
                store.consume_board_intent(
                    self.intent(
                        "op-B",
                        before=None,
                        after={**self.snapshot(tid, "pending"), "owner": "banc-B"},
                    )
                )
        self.assertEqual(2, len(appels))
        self.assertNotIn("creation refusee", err.getvalue())
        with closing(get_db_connection(self.db_path)) as conn:
            for table in ("events_ledger", "board_sync_inbox"):
                self.assertEqual(
                    0,
                    conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE operation_id=?", ("op-B",)
                    ).fetchone()[0],
                    table,
                )

    def test_c6_la_ligne_de_refus_nomme_l_id_de_l_effet(self) -> None:
        """A-C3 (T-00001055, critique A) — la ligne stderr nomme l'id que NOMME l'effet
        (`board_task_id`, lu dans le snapshot), pas `affected_task_ids[0]`. Les
        producteurs réels (`tasks_sync.enqueue_sync_intent`, `BOARD_RUNNING_REPLACED`
        de `tasks_etats`) mettent cet id en tête : W1 et W8 ne distinguent donc pas les
        deux lectures, seul un intent où elles divergent le fait. MUTATION : la ligne
        imprime `task_id` (`affected_task_ids[0]`) au lieu de `effect_board_id`."""
        import io
        from contextlib import redirect_stderr

        from agentic_v3.reconciliation.board_bridge import BoardBridge

        store = BoardBridge(self.db_path, self.root).event_store
        tid, autre = "T-00009110", "T-00009199"
        store.consume_board_intent(
            self.intent(
                "op-A", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-A"}
            )
        )
        intent_b = self.intent(
            "op-B", before=None, after={**self.snapshot(tid, "pending"), "owner": "banc-B"}
        )
        intent_b["affected_task_ids"] = [autre, tid]
        err = io.StringIO()
        with redirect_stderr(err):
            effet = store.consume_board_intent(intent_b)
        self.assertEqual(
            ("creation-collision", tid), (effet["action"], effet["board_task_id"]), effet
        )
        lignes = [l for l in err.getvalue().splitlines() if "creation refusee" in l]
        self.assertEqual(1, len(lignes), err.getvalue())
        self.assertIn(f"— {tid!r} deja cree par {'op-A'!r}", lignes[0])
        self.assertNotIn(repr(autre), lignes[0])


if __name__ == "__main__":
    # FAIL-CLOSED HORS PYTEST (T-00000695, 23/09). Ce banc tire son isolation de
    # FIXTURES pytest (`_isolation_export_run`, la greffe `_email_git`, la racine
    # tmp) : sous `unittest.main` il n'en a AUCUNE, et ses tests qui passent
    # écrivent dans le `runs/` SUIVI du dépôt courant — mesuré, 24 évènements
    # synthétiques ajoutés à l'export versionné du kit. Le filet
    # `_refuser_ecriture_de_banc_sous_racine_reelle` ne s'arme que sous
    # `PYTEST_CURRENT_TEST`, donc il n'y voit rien. Refuser vaut mieux que
    # polluer. Borne : `python -m unittest <module>` n'exécute pas ce bloc.
    import sys

    sys.stderr.write(
        "test_board_bridge.py : lance-le par pytest "
        "(python3 -B -m pytest agentic_v3/tests/test_board_bridge.py) — "
        "hors pytest, ses fixtures d'isolation manquent et il écrirait dans "
        "le runs/ suivi du dépôt courant.\n"
    )
    sys.exit(2)
