from __future__ import annotations

import importlib.util
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest import mock


TASKS_PATH = Path(__file__).with_name("tasks.py")
SPEC = importlib.util.spec_from_file_location("tasks_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tasks
SPEC.loader.exec_module(tasks)
tasks._RESOLVEUR_V3.charger_paquet(Path(__file__).resolve().parents[2], "agentic_v3")

def _id_rendu(message: str) -> str:
    """The id ``new_task`` RETURNED (``TASKS: <id> → pending``), never a
    PREDICTED one: under the ``P-<ULID>`` allocator (T-00000726, C2) no value is
    guessable, so a bench that creates and then targets a task captures it
    (R-BANCS rule (i))."""
    trouve = re.fullmatch(r"TASKS: (\S+) → pending", message)
    assert trouve, f"unexpected `new` message: {message!r}"
    return trouve.group(1)


class BoardSyncStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        self.store.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_store(self, data: dict[str, Any]) -> None:
        self.store.write_text(json.dumps(data), encoding="utf-8")

    def read_store(self) -> dict[str, Any]:  # T-00001058 : TASKS.json BRUT, son `sync_outbox` lue par la VUE (O2)
        return {**json.loads(self.store.read_text(encoding="utf-8")), "sync_outbox": tasks.load(str(self.root)).get("sync_outbox", [])}

    @staticmethod
    def legacy_task(task_id: str = "T-001", state: str = "pending") -> dict[str, Any]:
        return {
            "id": task_id,
            "state": state,
            "task": "Legacy task",
            "owner": "planner",
            "stage": "",
            "updated": "2026-08-07",
        }

    def test_legacy_store_gets_sync_defaults_without_changing_read_surfaces(self) -> None:
        self.write_store({"next_id": 2, "tasks": [self.legacy_task()]})

        data = tasks.load(self.root)

        self.assertEqual([], data["sync_outbox"])
        self.assertEqual({}, data["sync_correlations"])
        self.assertIn("T-001", tasks.render_list(str(self.root)))
        self.assertEqual("no active task · ⏸1 ✓0", tasks.statusline(str(self.root)))
        self.assertNotIn("sync_", tasks.render_list(str(self.root)))

    def test_sync_extensions_are_validated(self) -> None:
        invalid_values = (
            ("sync_outbox", {}),
            ("sync_correlations", []),
        )
        for key, value in invalid_values:
            with self.subTest(key=key):
                data = {"next_id": 1, "tasks": [], "sync_outbox": [], "sync_correlations": {}}
                data[key] = value
                self.write_store(data)
                with self.assertRaisesRegex(tasks.BoardError, key):
                    tasks.load(self.root)

    def test_outbox_revision_hash_is_validated(self) -> None:
        tasks.new_task(str(self.root), "Hash", "")
        data = self.read_store()
        data["sync_outbox"][0]["revision_sha256"] = "f" * 64
        self.write_store(data)

        with self.assertRaisesRegex(tasks.BoardError, "revision_sha256"):
            tasks.load(self.root)

    def test_new_creates_correlation_and_canonical_outbox_intent_atomically(self) -> None:
        tasks.new_task(str(self.root), "Bridge me", "dev-multi")

        data = self.read_store()
        task = data["tasks"][0]
        event = data["sync_outbox"][0]
        operation_id = event["operation_id"]
        self.assertEqual(
            {"board_task_id": task["id"], "tombstoned": False},
            data["sync_correlations"][operation_id],
        )
        self.assertEqual("BOARD_TASK_OBSERVED", event["event_kind"])
        self.assertEqual([task["id"]], event["affected_task_ids"])
        self.assertIsNone(event["before"])
        self.assertEqual(task, event["after"])
        self.assertEqual(0, event["attempt"])
        self.assertIsNone(event["lease"])
        canonical = json.dumps(
            {"before": None, "after": task},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), event["revision_sha256"])

    def test_drain_sync_outbox_annonce_le_fail_closed_et_ne_l_avale_pas(self) -> None:
        """B-1 (L-00000136) — un consumer qui LÈVE (store V3 fail-closed, sans
        rédaction) ne doit PAS être avalé en silence : le bail est relâché, un
        message part sur STDERR, et le drain s'arrête. Sans ce correctif, `tasks.py`
        rendait rc 0 et un journal vide sans un mot chez un adoptant hors clone."""
        from contextlib import redirect_stderr

        tasks.new_task(str(self.root), "Bridge me", "dev-multi")

        def _consumer_fail_closed(_intent: dict) -> bool:
            raise RuntimeError(
                "redaction indisponible (paquet ET chemin), ecriture V3 refusee"
            )

        err = io.StringIO()
        with redirect_stderr(err):
            drained = tasks.drain_sync_outbox(str(self.root), _consumer_fail_closed)

        self.assertEqual(0, drained, "un fail-closed ne doit ACQuitter aucun intent")
        self.assertIn("miroir V3 arrete", err.getvalue(),
                      "le fail-closed a été avalé EN SILENCE (aucun mot sur stderr)")
        intent = self.read_store()["sync_outbox"][0]
        self.assertIsNone(intent["lease"], "le bail n'a pas été relâché")
        self.assertEqual(1, intent["attempt"], "l'attempt n'a pas été incrémenté")

    def test_drain_sync_outbox_nomme_la_VRAIE_cause_de_l_export_refuse(self) -> None:
        """MAJEUR (binôme, opus T1 / fable), AMENDÉ PAR F2 — `drain_sync_outbox` NOMME
        la cause d'un `RunExportError` qui REMONTE jusqu'à lui, dans un message dont
        l'énumération est OUVERTE (« ... ou E/S »).

        Un `git user.email` absent est normalement RATTRAPÉ en amont par
        `event_store.py::_flush_export` (il n'attrape QUE `AuteurIndisponible` :
        événement commité en base, journal d'attente conservé, export différé) et le
        drain VIDE alors l'outbox (témoin d'intégration
        `test_sans_auteur_git_le_drain_vide_l_outbox_...`). Ce banc-ci exerce la
        branche OUVERTE du message, sur un consumer FABRIQUÉ qui lève une copie
        réservée DIRECTEMENT. Le drain relâche le bail, N'ACQUITTE PAS
        (`drained == 0`) et NOMME la cause.

        CORRECTION D'UNE PRÉMISSE (T-00000695/696, MESURÉ le 23/09) : cette docstring
        disait la copie réservée « cause FATALE qui remonte réellement ». FAUX par le
        vrai chemin : `tasks.py new` sur un dépôt dont la copie vaut `backfill` rend
        rc=0 et n'imprime QUE « event_store: ajout a l'export differe (echec export,
        …) » — `_flush_export` l'attrape dans sa BOUCLE, le drain ne la voit jamais.
        La seule cause mesurée qui remonte jusqu'au drain est la PANNE
        d'infrastructure ; elle a sa branche et son témoin
        (`test_drain_sync_outbox_nomme_la_PANNE_d_infrastructure_et_l_export_BLOQUE`).

        NON VACANT : le consumer factice lève le message ACCENTUÉ de run_export
        (« copie réservée »), donc `assertIn('copie reservee')` — SANS accent — ne peut
        matcher QUE le message codé en dur de `tasks.py`, jamais l'`{exc}` recopié ;
        retirer « copie reservee » du message le fait rougir. F2 : l'ancien
        `assertNotIn('user.email')` est RETIRÉ — l'énumération ouverte NOMME désormais
        « git user.email absent » (défensivement, cause POSSIBLE d'un report), et le
        verrouiller ABSENT refuserait la correction juste (faute T1 en image miroir).
        F9 : locator par NOM de symbole, pas par plage de lignes périmable."""
        from contextlib import redirect_stderr
        from agentic_v3.db.run_export import RunExportError

        tasks.new_task(str(self.root), "Bridge me", "dev-multi")

        def _consumer_export_refuse(_intent: dict) -> bool:
            # Cause FABRIQUÉE (copie réservée) — par le vrai chemin, `_flush_export`
            # l'attrape dans sa boucle (mesuré, voir la docstring). Message accentué
            # VERBATIM de run_copie.py::lire_copie_disque, relevé par identifiant_de_copie
            # (refus de la copie réservée).
            raise RunExportError(
                "copie réservée « backfill » lue comme identité de copie normale : "
                "refus (décision pilote S-00001594)."
            )

        err = io.StringIO()
        with redirect_stderr(err):
            drained = tasks.drain_sync_outbox(str(self.root), _consumer_export_refuse)
        sortie = err.getvalue()

        self.assertEqual(0, drained, "un export refusé ne doit ACQuitter aucun intent")
        self.assertNotIn(
            "suspendue", sortie,
            "RIEN n'est suspendu — l'événement est en base, seul l'export est différé",
        )
        self.assertNotIn(
            "redaction indisponible", sortie,
            "la cause « rédaction » est FAUSSE : c'est un refus d'export",
        )
        # F2 : l'`assertNotIn("user.email", …)` a été RETIRÉ ici — l'énumération OUVERTE
        # du message NOMME désormais « git user.email absent » (défensif), et le
        # verrouiller absent aurait refusé la correction juste (faute T1 en image miroir).
        # La non-vacuité reste tenue par l'`assertIn("copie reservee")` ci-dessous, dont
        # la propriété d'accent (« réservée » ≠ « reservee ») épingle le message CODÉ EN
        # DUR, jamais l'`{exc}` recopié.
        self.assertIn("DIFFERE", sortie, "l'export versionné est DIFFÉRÉ, dis-le")
        self.assertIn(
            "base", sortie, "l'événement EST écrit en base — le message doit le dire"
        )
        self.assertIn(
            "copie reservee", sortie,
            "la cause (copie réservée) doit être nommée dans l'énumération OUVERTE",
        )

    def test_drain_sync_outbox_nomme_la_PANNE_d_infrastructure_et_l_export_BLOQUE(self) -> None:
        """T-00000695/696, constat du binôme — le message du CHEMIN D'ÉCRITURE.
        Une `PanneInfrastructure` (git config illisible, git absent, timeout) est la
        SEULE cause mesurée qui remonte de `_flush_export` jusqu'au drain. Son
        message nommait EN TÊTE « git user.email absent » — rattrapé en amont, donc
        inatteignable ici — et ne disait jamais PANNE ni BLOQUÉ, là où le chemin de
        CONSTRUCTION (`_rejouer_journaux_attente`) les dit.

        On lit le PRÉFIXE CODÉ EN DUR, jamais l'`{exc}` recopié : l'exception porte
        elle-même « panne » en minuscules et « PAS un auteur absent ». MUTATION
        (retirer la branche `_est_panne_infrastructure` du drain) : la panne retombe
        dans le message ouvert « DIFFERE (… git user.email absent) » — ni PANNE ni
        BLOQUE dans le préfixe, et cet assert rougit."""
        from contextlib import redirect_stderr

        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:  # inoffensif : agentic_v3 déjà fixé par charger_paquet (ligne 31)
            sys.path.insert(0, str(repo))
        from agentic_v3.db.run_export import (
            AuteurIndisponible, PanneInfrastructure, RunExportError,
        )

        self.assertTrue(issubclass(PanneInfrastructure, RunExportError))
        self.assertFalse(issubclass(PanneInfrastructure, AuteurIndisponible))

        tasks.new_task(str(self.root), "Bridge me", "dev-multi")
        panne = PanneInfrastructure(
            "git config user.email a ÉCHOUÉ (code=128, timeout=False) : "
            "'fatal: bad config line 8 in file .git/config' — dépôt cassé ou git "
            "indisponible, PAS un auteur absent (panne d'infrastructure, non reportable)."
        )

        def _consumer_panne(_intent: dict) -> bool:
            raise panne

        err = io.StringIO()
        with redirect_stderr(err):
            drained = tasks.drain_sync_outbox(str(self.root), _consumer_panne)
        sortie = err.getvalue()
        self.assertIn(str(panne), sortie, "la cause réelle reste jointe")
        prefixe = sortie.split(str(panne), 1)[0]

        self.assertEqual(0, drained, "une panne ne doit ACQuitter aucun intent")
        self.assertIn("PANNE", prefixe, f"la panne se NOMME PANNE : {prefixe!r}")
        self.assertIn("BLOQUE", prefixe, f"l'export est dit BLOQUÉ : {prefixe!r}")
        self.assertNotIn(
            "user.email absent", prefixe,
            "« git user.email absent » est rattrapé en amont : le nommer ici ment",
        )
        intent = self.read_store()["sync_outbox"][0]
        self.assertIsNone(intent["lease"], "le bail doit être relâché")

    def test_couture_executor_introuvable_le_drain_dit_PANNE_et_BLOQUE(self) -> None:
        """T-00000695/696 (exec-critic, MAJEUR) — la couture `cadre.executor`
        INTROUVABLE, par le VRAI chemin d'écriture : le consumer appelle
        `EventStore._flush_export`, qui résout l'auteur par `run_export._email_git`
        et n'attrape QUE `AuteurIndisponible`. Deux variantes, mesurées avant
        correction : la branche défensive de `_cadre` (`RunExportError` NU → le
        drain disait « DIFFERE … conserve pour rejeu ») et le repli par chemin sur
        un fichier absent (`FileNotFoundError` → « echec inattendu du consumer »).
        Ni l'une ni l'autre ne disait PANNE.

        MUTATION (retirer l'enveloppe autour de `_cadre("executor")` dans
        `_email_git`) : chaque variante retombe dans son ancien message, sans
        PANNE ni BLOQUE dans le préfixe — rouge sur les deux."""
        from contextlib import ExitStack, redirect_stderr

        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        # Importés AVANT toute couture : `patch.dict(sys.modules)` retire à la
        # sortie ce qui a été importé pendant le bloc, et un module réimporté
        # ensuite porterait d'AUTRES classes (isinstance faux ailleurs).
        from agentic_v3.db import run_export
        from agentic_v3.db.event_store import EventStore

        reel = run_export._cadre

        def cadre_defensif(nom: str) -> Any:
            if nom == "executor":
                raise run_export.RunExportError("module cadre.executor introuvable (banc)")
            return reel(nom)

        def couture_defensive() -> ExitStack:
            pile = ExitStack()
            pile.enter_context(mock.patch.object(run_export, "_cadre", side_effect=cadre_defensif))
            return pile

        def couture_fichier_absent() -> ExitStack:
            pile = ExitStack()
            # `cadre.executor` masqué AUSSI : déjà en cache dans la porte complète,
            # il était rendu sans consulter `cadre` (rouge @ 1bc9933).
            pile.enter_context(mock.patch.dict(sys.modules, {"cadre": None, "cadre.executor": None}))
            pile.enter_context(mock.patch.dict(run_export._MODULES_CADRE))
            run_export._MODULES_CADRE.pop("executor", None)
            pile.enter_context(mock.patch.object(
                run_export, "_SRC_CADRE", Path(tempfile.gettempdir()) / "cadre-absent-banc"))
            return pile

        for nom, couture in (
            ("branche défensive de _cadre", couture_defensive),
            ("paquet absent + repli par chemin absent", couture_fichier_absent),
        ):
            with self.subTest(variante=nom):
                self.store.unlink(missing_ok=True)
                tasks.new_task(str(self.root), "Bridge me", "dev-multi")

                def _consumer_flush(_intent: dict) -> bool:
                    EventStore._flush_export([("journal-banc", {})], self.root)
                    return True

                err = io.StringIO()
                with couture(), redirect_stderr(err):
                    drained = tasks.drain_sync_outbox(str(self.root), _consumer_flush)
                sortie = err.getvalue()
                self.assertIn("cadre.executor", sortie, "la couture en cause reste nommée")
                prefixe = sortie.split("couture cadre.executor", 1)[0]
                self.assertEqual(0, drained, "une panne ne doit ACQuitter aucun intent")
                self.assertIn("PANNE", prefixe, f"la panne se NOMME PANNE : {sortie!r}")
                self.assertIn("BLOQUE", prefixe, f"l'export est dit BLOQUÉ : {sortie!r}")
                self.assertNotIn("DIFFERE", prefixe, "une panne n'est pas un report")
                self.assertNotIn("echec inattendu", prefixe, "la panne a un NOM, pas « inattendu »")
                intent = self.read_store()["sync_outbox"][0]
                self.assertIsNone(intent["lease"], "le bail doit être relâché")

    def test_drain_sync_outbox_nomme_l_echec_inattendu_du_consumer(self) -> None:
        """MOYEN voisin (binôme, fable) — un échec NON-`RuntimeError` du consumer
        (OSError disque plein, p.ex.) ne doit pas DISPARAÎTRE. Avant ce correctif,
        `except Exception: confirmed = False` avalait TOUT signal (0 mot mesuré sur
        mutation OSError). Le comportement de RETOUR ne change pas — `confirmed`
        reste False, l'intent n'est PAS acquitté (`drained == 0`) et son bail est
        relâché pour un rejeu — mais la cause est NOMMÉE sur stderr. MUTATION (code
        fautif) : retirer le `print` de la branche `except Exception` -> stderr vide
        -> l'`assertIn` ci-dessous rougit."""
        from contextlib import redirect_stderr

        tasks.new_task(str(self.root), "Bridge me", "dev-multi")

        def _consumer_os_error(_intent: dict) -> bool:
            raise OSError(28, "No space left on device")

        err = io.StringIO()
        with redirect_stderr(err):
            drained = tasks.drain_sync_outbox(str(self.root), _consumer_os_error)
        sortie = err.getvalue()

        self.assertEqual(0, drained, "un échec inattendu ne doit ACQuitter aucun intent")
        self.assertNotEqual(
            "", sortie.strip(),
            "l'échec inattendu a été avalé EN SILENCE (aucun mot sur stderr)",
        )
        self.assertIn(
            "No space left on device", sortie,
            "la cause EXACTE de l'échec inattendu doit être nommée",
        )
        intent = self.read_store()["sync_outbox"][0]
        self.assertIsNone(intent["lease"], "le bail n'a pas été relâché")

    def test_retitle_preserves_existing_correlation_and_unknown_fields(self) -> None:
        tasks.new_task(str(self.root), "Before", "dev-multi")
        data = self.read_store()
        task_id = data["tasks"][0]["id"]
        create_operation_id = data["sync_outbox"][0]["operation_id"]
        data["future_top_level"] = {"keep": True}
        data["tasks"][0]["future_task_field"] = 42
        self.write_store(data)

        tasks.retitle_task(str(self.root), task_id, "After")

        updated = self.read_store()
        self.assertEqual({"keep": True}, updated["future_top_level"])
        self.assertEqual(42, updated["tasks"][0]["future_task_field"])
        self.assertEqual(
            {"board_task_id": task_id, "tombstoned": False},
            updated["sync_correlations"][create_operation_id],
        )
        self.assertEqual("Before", updated["sync_outbox"][-1]["before"]["task"])
        self.assertEqual("After", updated["sync_outbox"][-1]["after"]["task"])

    def test_all_mutators_emit_expected_board_intents(self) -> None:
        tasks.new_task(str(self.root), "Initial", "planner")
        task_id = self.read_store()["tasks"][0]["id"]

        def latest() -> dict[str, Any]:
            return self.read_store()["sync_outbox"][-1]

        self.assertEqual((None, "pending"), (latest()["before"], latest()["after"]["state"]))
        tasks.set_state(str(self.root), task_id, "running", "planner")
        self.assertEqual(("pending", "running"), (latest()["before"]["state"], latest()["after"]["state"]))
        tasks.stage_task(str(self.root), task_id, "dev-multi")
        self.assertEqual(("planner", "dev-multi"), (latest()["before"]["stage"], latest()["after"]["stage"]))
        tasks.block_task(str(self.root), task_id, "waiting")
        self.assertEqual(("running", "blocked"), (latest()["before"]["state"], latest()["after"]["state"]))
        tasks.unblock_task(str(self.root), task_id)
        self.assertEqual(("blocked", "pending"), (latest()["before"]["state"], latest()["after"]["state"]))
        tasks.retitle_task(str(self.root), task_id, "Renamed")
        self.assertEqual(("Initial", "Renamed"), (latest()["before"]["task"], latest()["after"]["task"]))
        tasks.reassign_task(str(self.root), task_id, "dev-multi")
        self.assertEqual(("planner", "dev-multi"), (latest()["before"]["owner"], latest()["after"]["owner"]))
        before_regroup = latest()["operation_id"]
        tasks.regroup_task(str(self.root), task_id, "refonte auth")
        self.assertNotEqual(before_regroup, latest()["operation_id"])
        self.assertEqual(task_id, latest()["after"]["id"])
        tasks.set_state(str(self.root), task_id, "done", stage="clos par le banc")
        self.assertEqual(("pending", "done"), (latest()["before"]["state"], latest()["after"]["state"]))
        tasks.purge_tasks(str(self.root))
        self.assertEqual(("done", None), (latest()["before"]["state"], latest()["after"]))
        self.assertTrue(all(event["event_kind"] == "BOARD_TASK_OBSERVED" for event in self.read_store()["sync_outbox"]))

    def test_regroup_emits_board_intent_like_reassign(self) -> None:
        """`regroup` is a write verb, so it owes the bridge the same intent
        `reassign` owes it — measured against reassign's own intent rather than
        against a hand-written expectation, which is what makes this test notice
        a divergence introduced on either side.

        The intent records the GESTURE, not the value: `SYNC_SNAPSHOT_FIELDS` is
        frozen (widening it invalidates every intent already in a store), so the
        assertion is on the intent's shape and on the TASK carrying the new
        chantier — never on a `chantier` key inside the snapshot.
        """
        self.write_store({"next_id": 2, "tasks": [self.legacy_task("T-001", "running")]})

        tasks.reassign_task(str(self.root), "T-001", "dev-mono")
        reassign_intent = self.read_store()["sync_outbox"][-1]
        tasks.regroup_task(str(self.root), "T-001", "refonte auth")
        data = self.read_store()
        regroup_intent = data["sync_outbox"][-1]
        task = data["tasks"][0]

        self.assertEqual(reassign_intent["event_kind"], regroup_intent["event_kind"])
        self.assertEqual(reassign_intent["affected_task_ids"], regroup_intent["affected_task_ids"])
        self.assertEqual(0, regroup_intent["attempt"])
        self.assertIsNone(regroup_intent["lease"])
        self.assertEqual(
            {"board_task_id": "T-001", "tombstoned": False},
            data["sync_correlations"][regroup_intent["operation_id"]],
        )
        self.assertEqual(
            set(tasks.SYNC_SNAPSHOT_FIELDS), set(regroup_intent["after"])
        )
        self.assertEqual(
            tasks.revision_sha256(regroup_intent["before"], regroup_intent["after"]),
            regroup_intent["revision_sha256"],
        )
        # the value lands on the task, `state` is untouched, `updated` stamped
        self.assertEqual("refonte auth", task["chantier"])
        self.assertEqual("running", task["state"])
        self.assertEqual(date.today().isoformat(), task["updated"])
        # and the store still loads — the intent is canonical, not merely present
        self.assertEqual("refonte auth", tasks.load(self.root)["tasks"][0]["chantier"])

        # "" un-groups: the key goes, so "no chantier" keeps ONE stored shape.
        tasks.regroup_task(str(self.root), "T-001", "")
        ungrouped = self.read_store()["tasks"][0]
        self.assertNotIn("chantier", ungrouped)
        self.assertEqual("running", ungrouped["state"])

    def test_chantier_reads_treat_absent_and_empty_as_the_same_ungrouped_task(self) -> None:
        """The back-compat contract, asserted on a LEGACY entry that has no
        `chantier` key at all: it must filter, group and render as ungrouped
        rather than crash a read surface the SessionStart hooks consume."""
        self.write_store(
            {
                "next_id": 3,
                "tasks": [
                    self.legacy_task("T-001", "pending"),
                    {**self.legacy_task("T-002", "pending"), "chantier": "auth"},
                ],
            }
        )
        data = tasks.load(self.root)

        self.assertEqual("", tasks.chantier_of(data["tasks"][0]))
        self.assertEqual(
            ["T-001"], [t["id"] for t in tasks.filter_tasks(data, chantier="")]
        )
        self.assertEqual(
            ["T-002"], [t["id"] for t in tasks.filter_tasks(data, chantier="auth")]
        )
        self.assertEqual([], tasks.filter_tasks(data, chantier="jamais vu"))
        self.assertEqual(
            ["auth", tasks.NO_CHANTIER],
            [name for name, _ in tasks.group_by_chantier(tasks.sorted_tasks(data["tasks"]))],
        )
        grouped = tasks.render_list(str(self.root), group=True)
        self.assertIn("### auth (1)", grouped)
        self.assertIn(f"### {tasks.NO_CHANTIER} (1)", grouped)
        self.assertLess(grouped.index("### auth"), grouped.index(f"### {tasks.NO_CHANTIER}"))

    def test_group_refuses_the_combinations_that_have_no_meaning(self) -> None:
        """`--group --task` and `--group --chantier` are refused, not ignored.
        Non-vacuity is proved in the same test by the ALLOWED combination
        (`--group --state`) and by bare `--group`, which must both answer."""
        tasks.new_task(str(self.root), "Grouped", "planner", "auth")

        with self.assertRaisesRegex(tasks.BoardError, "--group does not combine with --task"):
            tasks.render_list(str(self.root), task="T-00000001", group=True)
        with self.assertRaisesRegex(tasks.BoardError, "--group does not combine with --chantier"):
            tasks.render_list(str(self.root), chantier="auth", group=True)
        self.assertIn("### auth (1)", tasks.render_list(str(self.root), group=True))
        self.assertIn(
            "### auth (1)", tasks.render_list(str(self.root), state="pending", group=True)
        )

    def blocked_by_fixture(self) -> tuple[str, str, str]:
        """T-1 blocker, T-2 blocked on it, T-3 free — the shape the inverse read
        (`list --blocked-by T-1` → T-2 only) needs.

        LITERAL LEGACY IDS, WRITTEN AS AN INPUT FIXTURE rather than allocated by
        `new`: the short forms `T-1` / `1` these tests resolve are a property of
        a LEGACY id, which stays valid after the switch to `P-<ULID>`
        (T-00000726) although no new task will ever carry one (R-BANCS (iv))."""
        blocker, dependent, free = "T-00000001", "T-00000002", "T-00000003"
        self.write_store({"tasks": [self.legacy_task(tid) for tid in (blocker, dependent, free)]})
        tasks.block_task(str(self.root), dependent, "", blocker)
        return blocker, dependent, free

    def test_blocked_by_returns_the_tasks_waiting_on_one_id_and_composes_with_state(self) -> None:
        """The INVERSE of a `blocked_on` link (T-00000185): who waits on T-MMM.
        Short forms resolve like `--task`, and the filter intersects `--state`
        exactly as `--chantier` does — nothing here is a new code path."""
        blocker, dependent, _free = self.blocked_by_fixture()
        data = tasks.load(self.root)

        # short form T-1 / 1 both resolve to the blocker, and only the dependent waits
        self.assertEqual([dependent], [t["id"] for t in tasks.filter_tasks(data, blocked_by="T-1")])
        self.assertEqual([dependent], [t["id"] for t in tasks.filter_tasks(data, blocked_by="1")])
        self.assertEqual([dependent], [t["id"] for t in tasks.filter_tasks(data, blocked_by=blocker)])
        # composes with --state (intersection): the dependent is blocked, so it stays;
        # asking for the pending ones that wait on the blocker matches nothing.
        self.assertEqual(
            [dependent], [t["id"] for t in tasks.filter_tasks(data, state="blocked", blocked_by=blocker)]
        )
        self.assertEqual([], tasks.filter_tasks(data, state="pending", blocked_by=blocker))
        # the rendered filter echoes the reference the caller used, not the resolved id
        rendered = tasks.render_list(str(self.root), blocked_by="T-1")
        self.assertIn("filter: blocked-by=T-1", rendered)
        self.assertIn(dependent, rendered)

    def test_blocked_by_refuses_unknown_id_and_empty_but_matches_done_blocker_to_nothing(self) -> None:
        """Three distinct behaviours the plan pins apart. An UNKNOWN id is a loud
        refusal (never an empty result that would read as "nobody waits"); ``""``
        is refused with its OWN message (unlike `--chantier`, an empty value has
        no meaning here); a ``done`` blocker matches nothing legitimately, because
        `done` already purged the links — an announced absence, not a refusal."""
        blocker, _dependent, _free = self.blocked_by_fixture()
        data = tasks.load(self.root)

        with self.assertRaisesRegex(tasks.BoardError, "unknown task id"):
            tasks.filter_tasks(data, blocked_by="T-99999999")
        with self.assertRaisesRegex(tasks.BoardError, "unknown task id"):
            tasks.render_list(str(self.root), blocked_by="T-99999999")
        with self.assertRaisesRegex(tasks.BoardError, 'empty value has no meaning'):
            tasks.filter_tasks(data, blocked_by="")
        with self.assertRaisesRegex(tasks.BoardError, 'empty value has no meaning'):
            tasks.render_list(str(self.root), blocked_by="")

        # closing the blocker purges the link, so the inverse read is now an
        # ANNOUNCED absence (exit 0, a worded "no task matching"), not a refusal.
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")
        rendered = tasks.render_list(str(self.root), blocked_by=blocker)
        self.assertIn("no task matching blocked-by=", rendered)

    def test_blocked_by_refuses_group_in_render_and_at_the_cli_boundary(self) -> None:
        """`--group --blocked-by` is refused in BOTH places, same doubling as
        `--task`/`--chantier` (T-00000184): a BoardError in `render_list` for the
        programmatic callers, and a usage error (exit 2) at the argparse matrix
        for the CLI. Non-vacuity: the bare `--blocked-by` read still answers."""
        blocker, dependent, _free = self.blocked_by_fixture()

        with self.assertRaisesRegex(tasks.BoardError, "--group does not combine with --blocked-by"):
            tasks.render_list(str(self.root), blocked_by="T-1", group=True)
        # the CLI matrix exits 2 with the named remedy before any read runs
        with self.assertRaises(SystemExit) as caught:
            tasks.main(["--root", str(self.root), "list", "--group", "--blocked-by", "T-1"])
        self.assertEqual(2, caught.exception.code)
        # non-vacuity: the allowed read answers, and names the waiting task
        self.assertIn(dependent, tasks.render_list(str(self.root), blocked_by="T-1"))

    def test_blocked_by_json_empty_is_a_list_and_the_absence_lands_on_stderr(self) -> None:
        """`--json` stays machine-parseable — `[]` on stdout for an empty match —
        while the absence is announced on stderr, exactly like `--chantier`. A
        `done` blocker is the natural empty case (its links were purged)."""
        blocker, _dependent, _free = self.blocked_by_fixture()
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), "list", "--json", "--blocked-by", blocker])
        self.assertEqual(0, rc)
        self.assertEqual([], json.loads(out.getvalue()))
        self.assertIn("no task matching blocked-by=", err.getvalue())

    def test_bare_render_list_is_unchanged_when_blocked_by_is_absent(self) -> None:
        """The load-bearing contract: adding `--blocked-by` must not route the
        bare `render_list(root)` through the filter path. With no filter it is the
        board, header `## TASK BOARD` and no `filter:` scope — byte-identical to
        the same call without the new parameter existing."""
        self.blocked_by_fixture()
        bare = tasks.render_list(str(self.root))
        self.assertEqual(bare, tasks.render_list(str(self.root), blocked_by=None))
        self.assertTrue(bare.startswith("## TASK BOARD"))
        self.assertNotIn("filter:", bare)

    def test_new_writes_the_chantier_key_only_when_it_carries_a_value(self) -> None:
        sans = _id_rendu(tasks.new_task(str(self.root), "Sans", "planner"))
        avec = _id_rendu(tasks.new_task(str(self.root), "Avec", "planner", "auth"))

        stored = {t["id"]: t for t in self.read_store()["tasks"]}
        self.assertNotIn("chantier", stored[sans])
        self.assertEqual("auth", stored[avec]["chantier"])
        # the field is NOT a table column: the generated view must not move.
        self.assertNotIn("chantier", tasks.render_list(str(self.root)))
        self.assertIn("chantier", tasks.format_detail(stored[avec]))

    def test_a_non_string_chantier_fails_loudly_instead_of_breaking_a_read(self) -> None:
        task = self.legacy_task()
        task["chantier"] = ["auth"]
        self.write_store({"next_id": 2, "tasks": [task]})

        with self.assertRaisesRegex(tasks.BoardError, "non-string chantier"):
            tasks.load(self.root)

    def three_tasks(self) -> tuple[str, str, str]:
        """T-1 blocker, T-2 and T-3 candidates — the shape every link test needs."""
        for title in ("blocker", "dependent", "other"):
            tasks.new_task(str(self.root), title, "dev-mono")
        return tuple(task["id"] for task in self.read_store()["tasks"])  # type: ignore[return-value]

    def test_done_releases_tasks_blocked_on_it_and_emits_intents(self) -> None:
        """Closing a blocker frees its dependents in the SAME command — and the
        release reaches V3 even when the `done` itself is suppressed.

        The suppressed half is the substantive one: `suppress_sync` silences the
        command the bridge is applying, and a release is NOT that command's
        effect but a side effect on ANOTHER task. Suppressed there too, V3 would
        keep projecting a blocked task the board has already freed.
        """
        blocker, dependent, other = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.block_task(str(self.root), other, "waiting pilot too", blocker)
        before_outbox = len(self.read_store()["sync_outbox"])

        message = tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        data = self.read_store()
        by_id = {task["id"]: task for task in data["tasks"]}
        # the first line is the consumer contract and does NOT move; the releases
        # are added under it, one loud line each.
        self.assertEqual(f"TASKS: {blocker} → done", message.splitlines()[0])
        self.assertEqual(
            {
                f"TASKS: {dependent} → pending (was blocked on {blocker})",
                f"TASKS: {other} → pending (was blocked on {blocker})",
            },
            set(message.splitlines()[1:]),
        )
        for task_id in (dependent, other):
            self.assertEqual("pending", by_id[task_id]["state"])
            self.assertEqual("", by_id[task_id]["stage"])
            self.assertNotIn("blocked_on", by_id[task_id])
        released_intents = [
            event
            for event in data["sync_outbox"][before_outbox:]
            if event["after"] and event["after"]["state"] == "pending"
        ]
        self.assertEqual(
            {dependent, other}, {event["after"]["id"] for event in released_intents}
        )
        self.assertTrue(all(event["before"]["state"] == "blocked" for event in released_intents))
        # a released task lands PENDING, never running: the invariant holds even
        # when two tasks are freed at once.
        self.assertEqual([], [task for task in data["tasks"] if task["state"] == "running"])

        # ...and the same release under V3 suppression still reaches the outbox.
        tasks.block_task(str(self.root), other, "", dependent)
        suppressed_from = len(self.read_store()["sync_outbox"])
        with tasks.suppress_sync("v3-op-done"):
            tasks.set_state(str(self.root), dependent, "done", stage="clos par le banc")
        emitted = self.read_store()["sync_outbox"][suppressed_from:]
        self.assertEqual(
            [(other, "blocked", "pending")],
            [(event["after"]["id"], event["before"]["state"], event["after"]["state"]) for event in emitted],
        )

    # --- LE MOTIF EST OBLIGATOIRE SUR LES DEUX VERBES TERMINAUX -------------

    def test_done_EXIGE_un_motif(self) -> None:
        """`done` était le seul verbe terminal sans explication : le board
        affirmait « c'est fini » sans jamais dire au nom de quoi. Mesuré le
        2026-09-12 sur deux clôtures dont la justification a dû être
        reconstituée contre le dépôt — pour découvrir qu'elle n'existait pas."""
        blocker, _, _ = self.three_tasks()
        for vide in (None, "", "   "):
            with self.subTest(motif=repr(vide)):
                with self.assertRaises(tasks.BoardError):
                    tasks.set_state(str(self.root), blocker, "done", stage=vide)
        # LE REFUS N'A RIEN ÉCRIT.
        self.assertEqual(
            "pending", {i["id"]: i for i in self.read_store()["tasks"]}[blocker]["state"]
        )

    def test_le_motif_de_cloture_RESTE_LISIBLE_dans_stage(self) -> None:
        """Il remplace l'étape en vol plutôt que de s'ajouter à côté : une tâche
        close n'a plus d'étape, donc le champ est libre — et tout relevé
        existant l'affiche déjà, sans qu'aucun consommateur change."""
        blocker, _, _ = self.three_tasks()
        tasks.stage_running_task  # le champ est celui que `stage` pilote
        tasks.set_state(str(self.root), blocker, "done", stage="porte verte @ abc1234")
        ferme = {i["id"]: i for i in self.read_store()["tasks"]}[blocker]
        self.assertEqual("done", ferme["state"])
        self.assertEqual("porte verte @ abc1234", ferme["stage"])

    def test_la_garde_de_cloture_tient_AUSSI_hors_CLI(self) -> None:
        """ELLE VIT DANS `set_state`, PAS DANS `argparse`, et c'est le point. La
        CLI n'est pas le seul chemin vers `done` : le pont V3 et le tableau de
        bord ferment aussi. Une exigence posée au parseur seul aurait laissé deux
        portes ouvertes, et une règle contournable par une autre porte n'en est
        pas une. Ce test appelle la FONCTION, jamais la ligne de commande."""
        blocker, _, _ = self.three_tasks()
        with self.assertRaises(tasks.BoardError) as pris:
            tasks.set_state(str(self.root), blocker, "done")
        self.assertIn("--raison", str(pris.exception))

    def test_block_MUET_est_refuse_mais_un_LIEN_suffit(self) -> None:
        """UN BLOCAGE DIT TOUJOURS POURQUOI — la prose n'étant pas la seule façon
        de le dire. Exiger une note EN PLUS d'un lien machine ferait taper
        « bloqué » comme remplissage, ce qui est pire qu'un lien. Le refus ne
        vise donc que le cas réellement MUET : ni note, ni lien, ni étape en vol
        préservée — une ligne bloquée dont la colonne motif est vide, que rien ne
        distingue d'une ligne en attente."""
        blocker, dependent, other = self.three_tasks()
        with self.assertRaises(tasks.BoardError):
            tasks.block_task(str(self.root), dependent, "", "")
        self.assertEqual(
            "pending", {i["id"]: i for i in self.read_store()["tasks"]}[dependent]["state"]
        )
        # LE LIEN SEUL SUFFIT — il dit sur QUOI la tâche attend.
        tasks.block_task(str(self.root), dependent, "", blocker)
        remis = {i["id"]: i for i in self.read_store()["tasks"]}[dependent]
        self.assertEqual("blocked", remis["state"])
        self.assertEqual(f"on {blocker}", remis["stage"])
        # ET LA NOTE SEULE AUSSI.
        tasks.block_task(str(self.root), other, "attend une decision pilote", "")
        self.assertEqual(
            "attend une decision pilote",
            {i["id"]: i for i in self.read_store()["tasks"]}[other]["stage"],
        )

    def test_une_etape_en_vol_PRESERVEE_vaut_explication(self) -> None:
        """La troisième source, et elle existait déjà : `block` sans note
        PRÉSERVE l'étape en cours plutôt que de l'effacer (T-00000103). Une
        tâche bloquée en plein `security-code-review` garde donc cette mention,
        qui explique la ligne — le refus ne doit pas la traiter comme muette."""
        _, _, other = self.three_tasks()
        tasks.set_state(str(self.root), other, "running", stage="security-code-review")
        tasks.block_task(str(self.root), other, "", "")
        bloquee = {i["id"]: i for i in self.read_store()["tasks"]}[other]
        self.assertEqual("blocked", bloquee["state"])
        self.assertEqual("security-code-review", bloquee["stage"])

    # --- `reopen` — L'INVERSE DE `done`, ET IL MANQUAIT ---------------------
    #
    # Le board avait cinq portes d'entrée dans `done` et aucune sortie. Mesuré le
    # 2026-09-12 sur T-00000560 et T-00000561 : deux tâches closes dont le
    # livrable n'existait dans AUCUN commit et qu'aucune revue n'avait relues. Le
    # seul recours était d'écrire au journal que la clôture était fausse en
    # laissant le board affirmer le contraire — un état qu'on ne peut pas
    # corriger n'est plus un état, c'est une affirmation gravée.

    def test_reopen_ramene_une_tache_close_vers_pending(self) -> None:
        """Le cas nominal, et la raison ATTERRIT dans `stage` — à la place même
        où `block` écrit la sienne, donc lisible par tout relevé existant sans
        qu'aucun consommateur change."""
        blocker, _, _ = self.three_tasks()
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        sortie = tasks.reopen_task(str(self.root), blocker, "livrable jamais committe")

        task = {item["id"]: item for item in self.read_store()["tasks"]}[blocker]
        self.assertEqual("pending", task["state"])
        self.assertEqual("livrable jamais committe", task["stage"])
        self.assertIn("rouverte", sortie)

    def test_reopen_EXIGE_une_raison(self) -> None:
        """Rouvrir est une affirmation sur une clôture que quelqu'un a
        prononcée. Sans motif écrit c'est un mouvement de board invisible, et
        rien au journal ne dira jamais pourquoi l'état a changé."""
        blocker, _, _ = self.three_tasks()
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")
        for vide in ("", "   ", "\t\n"):
            with self.subTest(raison=repr(vide)):
                with self.assertRaises(tasks.BoardError):
                    tasks.reopen_task(str(self.root), blocker, vide)
        # ET LE REFUS N'A RIEN ÉCRIT — un refus qui laisse une trace partielle
        # serait pire que pas de refus.
        task = {item["id"]: item for item in self.read_store()["tasks"]}[blocker]
        self.assertEqual("done", task["state"])

    def test_reopen_REFUSE_tout_etat_de_depart_autre_que_done(self) -> None:
        """STRICT, comme `unblock`. Le cas dangereux est `running` : rétrograder
        la tâche active en silence est exactement ce que l'invariant du board
        existe pour empêcher. Chaque autre état a déjà son verbe, et le refus le
        NOMME plutôt que de le laisser deviner."""
        blocker, dependent, other = self.three_tasks()
        tasks.set_state(str(self.root), other, "running")
        tasks.block_task(str(self.root), dependent, "en attente", "")
        for tid, etat in ((blocker, "pending"), (dependent, "blocked"), (other, "running")):
            with self.subTest(etat=etat):
                with self.assertRaises(tasks.BoardError) as pris:
                    tasks.reopen_task(str(self.root), tid, "peu importe")
                self.assertIn(etat, str(pris.exception))
                self.assertEqual(
                    etat,
                    {i["id"]: i for i in self.read_store()["tasks"]}[tid]["state"],
                )

    def test_la_cloture_MEMORISE_ce_qu_elle_libere(self) -> None:
        """LA PIÈCE QUI MANQUAIT. `done` effaçait le `blocked_on` de ce qu'il
        libérait, donc le lien n'existait plus NULLE PART et aucune réouverture
        ne pouvait le rétablir. Il est désormais consigné sur la tâche QUI FERME
        — pas sur celles qu'elle libère : un marqueur posé sur une tâche tierce
        lui survivrait et la re-bloquerait un jour sur un motif périmé."""
        blocker, dependent, other = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.block_task(str(self.root), other, "", blocker)

        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        ferme = {i["id"]: i for i in self.read_store()["tasks"]}[blocker]
        self.assertEqual([dependent, other], ferme["released_on_done"])

    def test_la_memoire_de_cloture_ne_survit_a_AUCUNE_transition(self) -> None:
        """Même discipline que `blocked_on`, et pour la même raison : une liste
        laissée derrière ferait rétablir, à la prochaine réouverture, des liens
        qu'une AUTRE clôture avait libérés."""
        blocker, dependent, _ = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")
        self.assertIn("released_on_done", {i["id"]: i for i in self.read_store()["tasks"]}[blocker])

        tasks.set_state(str(self.root), blocker, "running")

        self.assertNotIn(
            "released_on_done", {i["id"]: i for i in self.read_store()["tasks"]}[blocker]
        )

    def test_reopen_RETABLIT_les_liens_que_la_cloture_avait_liberes(self) -> None:
        """La symétrie, et elle est le DÉFAUT — même raison que la libération
        automatique de `done` : un geste qui exigerait une seconde commande est
        un geste que personne ne fait."""
        blocker, dependent, _ = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        sortie = tasks.reopen_task(str(self.root), blocker, "clôture prononcée à tort")

        remis = {i["id"]: i for i in self.read_store()["tasks"]}[dependent]
        self.assertEqual("blocked", remis["state"])
        self.assertEqual(blocker, remis["blocked_on"])
        self.assertIn("lien retabli", sortie)
        # LA MÉMOIRE EST CONSOMMÉE : la laisser ferait rétablir deux fois au
        # prochain cycle.
        self.assertNotIn(
            "released_on_done", {i["id"]: i for i in self.read_store()["tasks"]}[blocker]
        )

    def test_reopen_NE_PIETINE_PAS_un_etat_plus_recent(self) -> None:
        """LA GARDE QUI REND LE RÉTABLISSEMENT SÛR. Entre la clôture et la
        réouverture, une tâche libérée a pu être démarrée, close, ou bloquée
        pour une autre raison. Lui remettre l'ancien lien écraserait un état plus
        récent et plus vrai. Ce qui n'est pas rétabli est DIT, avec son motif —
        un rétablissement partiel silencieux serait pire que pas de
        rétablissement du tout."""
        blocker, dependent, other = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.block_task(str(self.root), other, "", blocker)
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")
        tasks.set_state(str(self.root), other, "running")   # état plus récent

        sortie = tasks.reopen_task(str(self.root), blocker, "reprise")

        par_id = {i["id"]: i for i in self.read_store()["tasks"]}
        self.assertEqual("blocked", par_id[dependent]["state"])   # rétabli
        self.assertEqual("running", par_id[other]["state"])       # intact
        self.assertNotIn("blocked_on", par_id[other])
        self.assertIn("NON retabli", sortie)
        self.assertIn(other, sortie)

    def test_sans_rebloquer_laisse_les_liens_libres_ET_LE_DIT(self) -> None:
        """L'échappement, pour la réouverture dont la dépendance n'a plus lieu
        d'être. Il ne se prend pas en silence : le nombre de liens laissés
        libres est annoncé, sinon l'écart entre les deux modes serait invisible
        au relevé."""
        blocker, dependent, _ = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        sortie = tasks.reopen_task(str(self.root), blocker, "reprise", rebloquer=False)

        self.assertEqual(
            "pending", {i["id"]: i for i in self.read_store()["tasks"]}[dependent]["state"]
        )
        self.assertIn("sans-rebloquer", sortie)
        self.assertIn(dependent, sortie)

    def test_une_cloture_sans_liberation_le_dit_aussi(self) -> None:
        """Le cas vide est une réponse valide qu'il faut quand même écrire : un
        silence se relit « il y avait des liens et je les ai perdus »."""
        blocker, _, _ = self.three_tasks()
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        sortie = tasks.reopen_task(str(self.root), blocker, "reprise")

        self.assertIn("n'avait libere aucune tache", sortie)

    def test_reopen_SIGNALE_les_taches_ordonnees_derriere(self) -> None:
        """`depends_on` SURVIT à la clôture, contrairement à `blocked_on`. Ces
        tâches-là sont encore ordonnées derrière celle qu'on rouvre, et leur
        pilote a le droit de le savoir — sans qu'aucun état change ; leur `start`
        est refusé tant qu'elle n'est pas re-close (S-01M4Z5VMP5E9YN8T6EMDTBAF0T)."""
        blocker, dependent, other = self.three_tasks()
        tasks.set_depends(str(self.root), dependent, [blocker], motif="amont livre ce que aval consomme")
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        sortie = tasks.reopen_task(str(self.root), blocker, "reprise")

        self.assertIn(dependent, sortie)
        self.assertNotIn(other, sortie)
        # AUCUN état n'a bougé chez la dépendante — l'avertissement est un DIRE,
        # pas une transition déguisée.
        self.assertEqual(
            "pending", {i["id"]: i for i in self.read_store()["tasks"]}[dependent]["state"]
        )

    def test_unblock_clears_blocked_on(self) -> None:
        """`unblock` is the manual form of the release, so it drops the same
        link — a machine link outliving the blocked state would arm a release on
        a task nobody is waiting for."""
        blocker, dependent, _ = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)
        self.assertEqual(blocker, self.read_store()["tasks"][1]["blocked_on"])

        tasks.unblock_task(str(self.root), dependent)

        task = {item["id"]: item for item in self.read_store()["tasks"]}[dependent]
        self.assertEqual("pending", task["state"])
        self.assertNotIn("blocked_on", task)
        # and the blocker's closure then releases NOTHING
        self.assertEqual(
            f"TASKS: {blocker} → done",
            tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc"),
        )

    def test_block_on_unknown_or_done_or_self_refuses(self) -> None:
        """Three loud refusals. Each one is a link that could never be released,
        so it is refused at the gesture rather than discovered later as a task
        that stays red for no visible reason."""
        blocker, dependent, _ = self.three_tasks()
        tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc")

        with self.assertRaisesRegex(tasks.BoardError, "unknown task id"):
            tasks.block_task(str(self.root), dependent, "", "T-99999999")
        with self.assertRaisesRegex(tasks.BoardError, "blocked on itself"):
            tasks.block_task(str(self.root), dependent, "", dependent)
        with self.assertRaisesRegex(tasks.BoardError, "already done"):
            tasks.block_task(str(self.root), dependent, "", blocker)
        # a write verb never resolves a short form: `--on 1` must not reach T-1
        with self.assertRaisesRegex(tasks.BoardError, "unknown task id"):
            tasks.block_task(str(self.root), dependent, "", "1")
        # nothing was written by any refusal
        self.assertTrue(
            all("blocked_on" not in task for task in self.read_store()["tasks"])
        )

    def test_leaving_blocked_state_always_clears_blocked_on(self) -> None:
        """The C2 invariant, on the THREE doors out of `blocked`: `start`,
        `done`, and `set_state` to `pending`. A link left behind would
        let the OLD blocker's closure release a task re-blocked for an unrelated
        reason — the one failure mode a machine link must not have.
        """
        blocker, dependent, other = self.three_tasks()

        # (a) start: blocked → running
        tasks.block_task(str(self.root), dependent, "", blocker)
        tasks.set_state(str(self.root), dependent, "running")
        by_id = {task["id"]: task for task in self.read_store()["tasks"]}
        self.assertNotIn("blocked_on", by_id[dependent])
        # re-blocked for a HUMAN reason, the old blocker's closure must not free it
        tasks.block_task(str(self.root), dependent, "waiting pilot decision")
        self.assertNotIn("blocked_on", self.read_store()["tasks"][1])
        self.assertEqual(
            f"TASKS: {blocker} → done",
            tasks.set_state(str(self.root), blocker, "done", stage="clos par le banc"),
        )
        self.assertEqual("blocked", self.read_store()["tasks"][1]["state"])

        # (b) done: blocked → done
        tasks.block_task(str(self.root), other, "", dependent)
        tasks.set_state(str(self.root), other, "done", stage="clos par le banc")
        self.assertNotIn("blocked_on", self.read_store()["tasks"][2])

        # (c) the explicit exit from `running` (no `start` demotes since
        # T-01M5F7286N1EYGXAXA5244X86B), on a store that carries the link on a RUNNING
        # task — a shape only a hand-written or historical store can produce,
        # which is exactly why the pop cannot live in the blocked branch alone.
        self.write_store({"next_id": 3, "tasks": [dict(self.legacy_task("T-001", "running"), blocked_on="T-002"),
                                                  self.legacy_task("T-002", "pending")]})
        tasks.set_state(str(self.root), "T-002", "running")
        self.assertEqual("running", self.read_store()["tasks"][0]["state"])
        tasks.set_state(str(self.root), "T-001", "pending")
        self.assertNotIn("blocked_on", self.read_store()["tasks"][0])

    def test_blocked_on_is_validated_as_an_id_but_may_dangle(self) -> None:
        """Presence validation only. A store whose blocker was deleted long ago
        must keep LOADING — this is the read surface the SessionStart hooks
        consume — while a structurally broken value fails loudly."""
        for bad in ("", None, ["T-001"]):
            with self.subTest(blocked_on=bad):
                task = dict(self.legacy_task("T-001", "blocked"), blocked_on=bad)
                self.write_store({"next_id": 2, "tasks": [task]})
                with self.assertRaisesRegex(tasks.BoardError, "blocked_on"):
                    tasks.load(self.root)

        dangling = dict(self.legacy_task("T-001", "blocked"), blocked_on="T-999")
        self.write_store({"next_id": 2, "tasks": [dangling]})
        self.assertEqual("T-999", tasks.load(self.root)["tasks"][0]["blocked_on"])
        self.assertIn("T-001", tasks.render_list(str(self.root)))

    def test_deleting_a_blocker_keeps_dependents_blocked_and_says_so(self) -> None:
        """A deleted blocker was not ACCOMPLISHED: releasing its dependents would
        claim work was finished when a row was merely erased. Only the dangling
        link goes, and it goes with a warning — a dependency dropped in silence
        is a dependency nobody re-declares."""
        blocker, dependent, _ = self.three_tasks()
        tasks.block_task(str(self.root), dependent, "", blocker)

        message = tasks.delete_task(str(self.root), blocker)

        task = {item["id"]: item for item in self.read_store()["tasks"]}[dependent]
        self.assertEqual(f"TASKS: {blocker} deleted", message.splitlines()[0])
        self.assertEqual(
            [f"warning: {dependent} was blocked on deleted {blocker} — still blocked"],
            message.splitlines()[1:],
        )
        self.assertEqual("blocked", task["state"])
        self.assertNotIn("blocked_on", task)

    def test_delete_and_purge_leave_tombstones_and_delete_events(self) -> None:
        tasks.new_task(str(self.root), "Delete", "")
        first = self.read_store()["tasks"][0]["id"]
        tasks.delete_task(str(self.root), first)
        tasks.new_task(str(self.root), "Purge", "")
        second = self.read_store()["tasks"][0]["id"]
        tasks.set_state(str(self.root), second, "done", stage="clos par le banc")

        tasks.purge_tasks(str(self.root))

        data = self.read_store()
        self.assertEqual([], data["tasks"])
        for task_id in (first, second):
            correlations = [
                value
                for value in data["sync_correlations"].values()
                if value["board_task_id"] == task_id
            ]
            self.assertTrue(correlations)
            self.assertTrue(all(value["tombstoned"] for value in correlations))
            matching = [event for event in data["sync_outbox"] if task_id in event["affected_task_ids"]]
            self.assertIsNone(matching[-1]["after"])

    def test_claim_is_bounded_by_lease_and_expired_lease_is_replayable(self) -> None:
        tasks.new_task(str(self.root), "Lease", "")

        first = tasks.claim_sync_event(str(self.root), "worker-a", now=100.0, lease_seconds=10.0)
        hidden = tasks.claim_sync_event(str(self.root), "worker-b", now=109.0, lease_seconds=10.0)
        replayed = tasks.claim_sync_event(str(self.root), "worker-b", now=111.0, lease_seconds=10.0)

        self.assertIsNotNone(first)
        self.assertIsNone(hidden)
        self.assertEqual(first["operation_id"], replayed["operation_id"])
        self.assertEqual("worker-b", replayed["lease"]["owner"])
        self.assertNotEqual(first["lease"]["token"], replayed["lease"]["token"])

    def test_fifo_head_lease_prevents_later_intent_projection(self) -> None:
        tasks.new_task(str(self.root), "First", "")
        tasks.new_task(str(self.root), "Second", "")
        operation_ids = [event["operation_id"] for event in self.read_store()["sync_outbox"]]
        first = tasks.claim_sync_event(str(self.root), "worker-a", now=100.0, lease_seconds=10.0)
        blocked = tasks.claim_sync_event(str(self.root), "worker-b", now=101.0, lease_seconds=10.0)
        replayed = tasks.claim_sync_event(str(self.root), "worker-b", now=111.0, lease_seconds=10.0)
        self.assertEqual(operation_ids[0], first["operation_id"])
        self.assertIsNone(blocked)
        self.assertEqual(operation_ids[0], replayed["operation_id"])
        self.assertTrue(tasks.ack_sync_event(str(self.root), replayed["operation_id"], replayed["lease"]["token"]))
        second = tasks.claim_sync_event(str(self.root), "worker-b", now=112.0)
        self.assertEqual(operation_ids[1], second["operation_id"])

    def test_dashboard_reader_ignores_sync_extensions_and_refreshes_on_bookkeeping(self) -> None:
        readers_path = TASKS_PATH.with_name("dashboard_readers.py")
        readers_spec = importlib.util.spec_from_file_location("dashboard_readers_under_test", readers_path)
        assert readers_spec is not None and readers_spec.loader is not None
        readers = importlib.util.module_from_spec(readers_spec)
        sys.modules[readers_spec.name] = readers
        readers_spec.loader.exec_module(readers)
        tasks.new_task(str(self.root), "Visible", "planner")
        rendered_before = tasks.render_list(str(self.root))
        fingerprint_before = readers.snapshot_fingerprint(self.root, None, None)
        claimed = tasks.claim_sync_event(str(self.root), "dashboard-test")
        assert claimed is not None
        rendered_after = tasks.render_list(str(self.root))
        fingerprint_after = readers.snapshot_fingerprint(self.root, None, None)
        self.assertEqual(rendered_before, rendered_after)
        self.assertNotIn("sync_outbox", rendered_after)
        self.assertNotEqual(fingerprint_before, fingerprint_after)

    def test_ack_only_removes_event_owned_by_same_lease(self) -> None:
        tasks.new_task(str(self.root), "ACK", "")
        event = tasks.claim_sync_event(str(self.root), "worker-a", now=100.0, lease_seconds=10.0)
        assert event is not None

        self.assertFalse(tasks.ack_sync_event(str(self.root), event["operation_id"], "wrong-token"))
        self.assertTrue(
            tasks.ack_sync_event(str(self.root), event["operation_id"], event["lease"]["token"])
        )
        self.assertEqual([], self.read_store()["sync_outbox"])

    def test_board_lock_is_persistent_only_in_gitignored_local_state(self) -> None:
        local_lock = self.root / ".agents" / "state" / "local" / "TASKS.lock"
        tracked_surface_lock = self.store.with_suffix(".lock")

        with tasks.board_lock(self.root):
            self.assertTrue(local_lock.is_file())
            self.assertFalse(tracked_surface_lock.exists())

        self.assertTrue(local_lock.is_file())
        self.assertFalse(tracked_surface_lock.exists())

    def test_commit_guard_refuses_before_replace_and_preserves_board(self) -> None:
        tasks.new_task(str(self.root), "Before guarded save", "dev-multi")
        before = self.store.read_bytes()
        task_id = self.read_store()["tasks"][0]["id"]
        replace_reached = False

        def observe_replace(src: str | Path, target: str | Path) -> None:
            nonlocal replace_reached
            replace_reached = True

        guard_commit = getattr(
            tasks,
            "guard_board_commit",
            lambda callback: nullcontext(),
        )
        refusal = None
        with mock.patch.object(
            tasks.os, "replace", side_effect=observe_replace
        ):
            try:
                with guard_commit(lambda: False):
                    tasks.retitle_task(str(self.root), task_id, "Must not persist")
            except tasks.BoardError as exc:
                refusal = str(exc)

        self.assertEqual(
            (False, before, True),
            (replace_reached, self.store.read_bytes(), refusal is not None),
        )

    def test_commit_guard_is_rechecked_after_replace_retry(self) -> None:
        tasks.new_task(str(self.root), "Before retry", "dev-multi")
        before = self.store.read_bytes()
        task_id = self.read_store()["tasks"][0]["id"]
        lease_alive = True
        replace_attempts = 0
        original_replace = tasks.os.replace

        def sharing_violation_then_replace(src: str | Path, target: str | Path) -> None:
            nonlocal replace_attempts
            replace_attempts += 1
            if replace_attempts == 1:
                raise PermissionError("target is temporarily open")
            original_replace(src, target)

        def expire_lease(_: float) -> None:
            nonlocal lease_alive
            lease_alive = False

        refusal = None
        with mock.patch.object(
            tasks.os, "replace", side_effect=sharing_violation_then_replace
        ), mock.patch.object(tasks.time, "sleep", side_effect=expire_lease):
            try:
                with tasks.guard_board_commit(lambda: lease_alive):
                    tasks.retitle_task(str(self.root), task_id, "Must not persist")
            except tasks.BoardError as exc:
                refusal = str(exc)

        self.assertEqual(
            (1, before, True),
            (replace_attempts, self.store.read_bytes(), refusal is not None),
        )

    def test_create_correlation_survives_retitle_queued_before_first_drain(self) -> None:
        tasks.new_task(str(self.root), "Before", "")
        data = self.read_store()
        task_id = data["tasks"][0]["id"]
        create_operation_id = data["sync_outbox"][0]["operation_id"]
        tasks.retitle_task(str(self.root), task_id, "After")

        create = tasks.claim_sync_event(str(self.root), "worker")
        assert create is not None
        tasks.ack_sync_event(
            str(self.root), create["operation_id"], create["lease"]["token"]
        )
        retitle = tasks.claim_sync_event(str(self.root), "worker")
        assert retitle is not None
        tasks.ack_sync_event(
            str(self.root), retitle["operation_id"], retitle["lease"]["token"]
        )

        self.assertEqual(
            {create_operation_id},
            set(self.read_store()["sync_correlations"]),
        )

    def test_two_drainers_deliver_one_intent_once_without_holding_board_lock(self) -> None:
        tasks.new_task(str(self.root), "Concurrent", "")
        entered = threading.Event()
        release = threading.Event()
        deliveries: list[str] = []
        results: list[int] = []

        def consumer(intent: dict[str, Any]) -> bool:
            deliveries.append(intent["operation_id"])
            entered.set()
            self.assertTrue(release.wait(timeout=2.0))
            # A board read from inside the callback proves the process lock is free.
            tasks.load(self.root)
            return True

        first = threading.Thread(
            target=lambda: results.append(tasks.drain_sync_outbox(self.root, consumer)),
            daemon=True,
        )
        first.start()
        self.assertTrue(entered.wait(timeout=2.0))
        second = threading.Thread(
            target=lambda: results.append(tasks.drain_sync_outbox(self.root, consumer)),
            daemon=True,
        )
        second.start()
        second.join(timeout=2.0)
        release.set()
        first.join(timeout=2.0)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(1, len(deliveries))
        self.assertCountEqual([0, 1], results)
        self.assertEqual([], self.read_store()["sync_outbox"])

    def test_replay_sync_is_strict_noop_without_project_local_agentic_v3(self) -> None:
        fake_script = self.root / ".agents" / "bin" / "tasks.py"
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text("# test location\n", encoding="utf-8")
        package = types.ModuleType("agentic_v3")
        reconciliation = types.ModuleType("agentic_v3.reconciliation")
        board_bridge = types.ModuleType("agentic_v3.reconciliation.board_bridge")

        class ExplodingBridge:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise AssertionError("global agentic_v3 must not be imported")

        board_bridge.BoardBridge = ExplodingBridge
        fake_modules = {
            "agentic_v3": package,
            "agentic_v3.reconciliation": reconciliation,
            "agentic_v3.reconciliation.board_bridge": board_bridge,
        }
        with mock.patch.object(tasks, "__file__", str(fake_script)), mock.patch.dict(
            sys.modules, fake_modules
        ):
            self.assertEqual(0, tasks.replay_sync(self.root))


class ReplaySyncRacineNonResolueTests(unittest.TestCase):
    """CONSTAT 4 (revue) : dans `replay_sync`, une racine non résoluble fait lever
    `CadrePathError` dans `BoardBridge` (via `DEFAULT_DB_PATH(root)`). Le `return 0`
    était MUET — indistinguable de « rien à drainer ». Il ANNONCE désormais sur
    stderr (forme de `:1069-1082`), et la sélection se fait par TYPE RÉEL, plus par
    une comparaison de CHAÎNE qui laissait passer un homonyme."""

    def test_une_racine_non_resolue_est_annoncee_sur_stderr_et_saute_le_miroir(self) -> None:
        # Vraie CadrePathError levée par le VRAI BoardBridge (racine hors git, hors
        # $CADRE_PROJECT_ROOT, sans ancêtre `.agents/`). MUTATION (code fautif) :
        # `return 0` silencieux -> stderr vide, assertTrue(strip) tombe.
        from contextlib import redirect_stderr

        bad = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bad, ignore_errors=True)
        err = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            with redirect_stderr(err):
                n = tasks.replay_sync(str(bad))
        self.assertEqual(0, n, "un miroir sauté rend 0")
        self.assertTrue(
            err.getvalue().strip(),
            "le saut du miroir ne doit plus être SILENCIEUX (CONSTAT 4)",
        )
        self.assertIn("miroir V3", err.getvalue())

    def test_un_homonyme_de_CadrePathError_n_est_PLUS_avale(self) -> None:
        # CONSTAT 4, second point : la comparaison de CHAÎNE avalait TOUTE exception
        # NOMMÉE `CadrePathError`, homonyme compris — une config réellement cassée
        # passait pour une racine non résolue. Le contrôle de TYPE RÉEL ne laisse
        # passer que la vraie classe. MUTATION (code fautif) : la comparaison de
        # nom avale l'homonyme -> pas de levée, assertRaises tombe.
        class CadrePathError(Exception):  # homonyme, PAS la classe de `cadre.paths`
            pass

        class HomonymeBridge:
            def __init__(self, *a: Any, **k: Any) -> None:
                raise CadrePathError("config cassée qui se fait passer pour une racine")

        with mock.patch(
            "agentic_v3.reconciliation.board_bridge.BoardBridge", HomonymeBridge
        ):
            with self.assertRaises(CadrePathError):
                tasks.replay_sync(str(Path(tempfile.mkdtemp())))


class StaleRunningWarningTests(unittest.TestCase):
    """The clock is injected everywhere here: no assertion may depend on the day
    the suite happens to run (CONVENTIONS_python.md), and a threshold test read
    off ``date.today()`` is exactly the kind that goes red at midnight."""

    TODAY = date(2026, 8, 14)

    @staticmethod
    def task(state: str, updated: Any, task_id: str = "T-00000183") -> dict[str, Any]:
        return {
            "id": task_id,
            "state": state,
            "task": "Chien de garde",
            "owner": "dev-mono",
            "stage": "dev-mono",
            "updated": updated,
        }

    def test_stale_running_warning_fires_after_threshold_and_names_the_task(self) -> None:
        stale = (self.TODAY - timedelta(days=tasks.STALE_RUNNING_DAYS)).isoformat()
        board = [
            self.task("running", stale),
            self.task("pending", "2026-01-01", task_id="T-00000184"),
        ]

        warning = tasks.stale_running_warning(board, self.TODAY)

        self.assertIsNotNone(warning)
        assert warning is not None  # narrows the Optional for the checker
        self.assertIn("T-00000183", warning)
        self.assertIn(f"{tasks.STALE_RUNNING_DAYS} jours", warning)
        self.assertIn(stale, warning)
        # The pending row must not be mistaken for the subject of the alert.
        self.assertNotIn("T-00000184", warning)
        # The day AFTER the threshold still warns, with the real count.
        later = tasks.stale_running_warning(board, self.TODAY + timedelta(days=2))
        assert later is not None
        self.assertIn(f"{tasks.STALE_RUNNING_DAYS + 2} jours", later)

    def test_no_running_or_fresh_running_yields_no_warning(self) -> None:
        fresh = (self.TODAY - timedelta(days=tasks.STALE_RUNNING_DAYS - 1)).isoformat()
        cases = {
            "empty board": [],
            "nothing running": [self.task("blocked", "2020-01-01")],
            # One day short of the threshold is the boundary that must stay silent.
            "running just under the threshold": [self.task("running", fresh)],
            "running updated today": [self.task("running", self.TODAY.isoformat())],
        }
        for label, board in cases.items():
            with self.subTest(case=label):
                self.assertIsNone(tasks.stale_running_warning(board, self.TODAY))

    def test_unparseable_updated_warns_instead_of_raising(self) -> None:
        # This runs inside SessionStart hooks, where session-start.sh reads any
        # non-zero exit as a broken board: an unreadable stamp must SPEAK.
        for bad in ("", "hier", "2026-13-45", None, 20260101):
            with self.subTest(updated=bad):
                warning = tasks.stale_running_warning([self.task("running", bad)], self.TODAY)
                assert warning is not None
                self.assertIn("T-00000183", warning)
                self.assertIn("lisible", warning)

    def test_bare_render_list_carries_the_alert_and_json_never_does(self) -> None:
        # The wiring, not the helper: the alert must be line 2 of the bare list
        # and absent from every other read surface.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            store = root / ".agents" / "state" / "board" / "TASKS.json"
            store.parent.mkdir(parents=True)
            stale = (date.today() - timedelta(days=tasks.STALE_RUNNING_DAYS + 1)).isoformat()
            store.write_text(
                json.dumps({"next_id": 2, "tasks": [self.task("running", stale)]}),
                encoding="utf-8",
            )

            lines = tasks.render_list(str(root)).splitlines()

            self.assertEqual("## TASK BOARD", lines[0])
            self.assertIn("RUNNING STALE", lines[1])
            self.assertTrue(lines[2].startswith("| id "), lines[2])
            self.assertNotIn("RUNNING STALE", tasks.render_list(str(root), state="running"))
            self.assertNotIn("RUNNING STALE", tasks.statusline(str(root)))
            self.assertNotIn(
                "RUNNING STALE",
                json.dumps(tasks.sorted_tasks(tasks.load(root)["tasks"])),
            )


class WritesetAdmissionTests(unittest.TestCase):
    """The admission predicate, case by case AND clause by clause.

    A refusal that does not NAME its failing clause blocks its own diagnosis, so
    every case below pins the pairing, not just the rejection. The clause names
    come from ``tasks.WRITESET_CLAUSES``: a renamed clause fails here rather than
    silently loosening the message contract.
    """

    # Each entry is (path, the clause that must refuse it). AMENDMENT C22: in
    # Python `"".split("/")` yields `[""]`, so depending on how the split is
    # written `""` and `/` can fail by "non-empty-segment" instead of
    # "at-least-one-segment". The implementation FIXES the evaluation order (an
    # empty remainder yields ZERO segments, checked first), so the factual clause
    # is at-least-one-segment — and this table still accepts either for those two
    # inputs, so the test pins a message the implementation cannot contradict.
    MUST_REFUSE = (
        ("", ("at-least-one-segment", "non-empty-segment")),
        ("/", ("at-least-one-segment", "non-empty-segment")),
        ("C:\\repo\\src\\a", ("no-colon",)),
        ("/src/a", ("non-empty-segment",)),
        ("\\\\srv\\share", ("non-empty-segment",)),
        ("src/a/../b", ("no-dot-segment",)),
        ("src//a", ("non-empty-segment",)),
        ("src/\\a", ("non-empty-segment",)),
        ("docs//", ("non-empty-segment",)),
        ("src/a.", ("no-trailing-dot-or-space",)),
        ("src/a ", ("no-trailing-dot-or-space",)),
        ("src/a:flux", ("no-colon",)),
        ("src/con", ("no-win32-device-name",)),
        ("src/con.txt", ("no-win32-device-name",)),
        # THE CLOSED LIST IS SYMMETRIC (T-00000188 review, MEDIUM d). `lpt¹` was
        # admitted while `com¹` was refused, on one and the same stated reason —
        # `casefold()` does not fold the superscripts down to digits. And a space
        # before the extension slipped through both clauses: Win32 strips it, so
        # `con .txt` reaches the device `con.txt` reaches.
        ("src/lpt¹", ("no-win32-device-name",)),
        ("src/com¹", ("no-win32-device-name",)),
        ("src/lpt³.md", ("no-win32-device-name",)),
        ("src/con .txt", ("no-win32-device-name",)),
        ("src/CON .TXT", ("no-win32-device-name",)),
    )

    # `lpt10` and `con man/` matter here: the widening must refuse the device
    # names and NOTHING ELSE — a clause that swallows real paths is a worse bug
    # than the hole it closes.
    MUST_ADMIT = ("docs/", "src/a", "src/ab", "Documentation/", "a", "x/y/z.py",
                  "src/carbon", "com10", "src/auth/login.jsx", "src/lpt10",
                  "src/con man/x")

    # THE DOMAIN the two properties are checked over: every named case above,
    # PLUS the degenerate inputs a transformation is most likely to break — the
    # empty string, a bare `/`, one segment, one character — PLUS a few unicode
    # shapes where casefold and NFC actually disagree.
    DOMAIN = tuple(p for p, _ in MUST_REFUSE) + MUST_ADMIT + (
        "", "/", "a", "z", " ", ".", "//", "a/", "a//", "///",
        "Straße/", "STRASSE/", "e\u0301cran/", "\u00e9cran/", "\u0130stanbul/x",
    )

    @staticmethod
    def clause_of(refusal: str) -> str | None:
        for clause in tasks.WRITESET_CLAUSES:
            if f"clause {clause}:" in refusal:
                return clause
        return None

    def test_every_must_refuse_case_is_refused_and_names_its_clause(self) -> None:
        for path, allowed in self.MUST_REFUSE:
            with self.subTest(path=path):
                refusal = tasks.writeset_path_refusal(path)
                self.assertIsNotNone(refusal, f"{path!r} was admitted")
                assert refusal is not None
                self.assertIn(
                    self.clause_of(refusal), allowed,
                    f"{path!r} refused by an unexpected clause: {refusal}",
                )
                # The diagnostic names the faulty path AND shows a canonical
                # form: a guard that blocks without either is unusable.
                self.assertIn(repr(path), refusal)
                self.assertIn(tasks.WRITESET_CANONICAL_EXAMPLE, refusal)

    def test_every_must_admit_case_is_admitted_verbatim_after_the_fold(self) -> None:
        for path in self.MUST_ADMIT:
            with self.subTest(path=path):
                self.assertIsNone(tasks.writeset_path_refusal(path))
                self.assertEqual(path.replace("\\", "/"), tasks.admitted_writeset_path(path))

    def test_property_a_canonicalisation_is_idempotent_on_its_domain(self) -> None:
        """PROPERTY (a): canonicalising twice equals canonicalising once.

        Checked over the ADMITTED domain and the degenerate inputs — the domain
        the function is DEFINED on. It is deliberately NOT claimed over refused
        strings: `docs//` canonicalises to `docs/` then to `docs`, because
        removing ONE trailing separator does not absorb two. That is the C21
        discipline measured rather than asserted — a TRANSFORMATION remaps the
        domain — and the answer is admission first, not a wider transformation.
        """
        domain = [p for p in self.DOMAIN
                  if tasks.writeset_path_refusal(p) is None] + ["", "/", "a", "z"]
        self.assertGreater(len(domain), 8, "the property must be checked on a real domain")
        for path in domain:
            with self.subTest(path=path):
                once = tasks.canonical_writeset_path(path)
                self.assertEqual(once, tasks.canonical_writeset_path(once))

    def test_property_b_an_admitted_path_is_the_join_of_its_segments(self) -> None:
        """PROPERTY (b): an admitted path equals the `/` join of its segments,
        suffixed by AT MOST ONE final `/`. Checked over the WHOLE domain,
        degenerate cases included, because the decomposition is what every other
        clause reasons about."""
        for path in self.DOMAIN:
            with self.subTest(path=path):
                folded = tasks.fold_writeset_path(path)
                segments, trailing = tasks.split_writeset_path(folded)
                self.assertEqual(folded, "/".join(segments) + ("/" if trailing else ""))
                self.assertLessEqual(folded.count("/") - max(len(segments) - 1, 0), 1)

    def test_zero_segments_is_a_refusal_never_a_vacuous_truth(self) -> None:
        """The empty string and a bare `/` yield ZERO segments, so "each segment
        is valid" would be VACUOUSLY true — the failure mode five critic rounds
        were spent on."""
        for path in ("", "/"):
            segments, _ = tasks.split_writeset_path(tasks.fold_writeset_path(path))
            self.assertEqual([], segments)
            self.assertIsNotNone(tasks.writeset_path_refusal(path))

    def test_overlap_is_tested_at_a_segment_boundary_and_casefolded(self) -> None:
        cases = (
            (["src/a/"], ["src/a/b.py"], True),    # a directory covers its files
            (["src/A/"], ["src/a/b.py"], True),    # the NTFS case
            (["src/a"], ["src/ab"], False),        # NOT a string prefix match
            (["docs/"], ["Documentation/"], False),
            (["e\u0301cran/"], ["\u00e9cran/x"], True),   # NFC before comparison
        )
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                self.assertEqual(expected, tasks.writeset_paths_overlap(left, right) is not None)
                # Symmetric: the order of the two writesets never decides.
                self.assertEqual(expected, tasks.writeset_paths_overlap(right, left) is not None)


class ParallelGroupTests(unittest.TestCase):
    """The declaration verb, the refusals, and the loosened invariant."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        store.parent.mkdir(parents=True)
        self.store = store

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def board(self, *writesets: list[str]) -> list[str]:
        ids = []
        for i, paths in enumerate(writesets, start=1):
            tid = _id_rendu(tasks.new_task(str(self.root), f"tache {i}", "dev-mono"))
            ids.append(tid)
            if paths:
                tasks.set_writeset(str(self.root), tid, paths)
        return ids

    def test_disjoint_writesets_declare_a_group_and_two_tasks_run(self) -> None:
        a, b = self.board(["src/a/", "docs/a.md"], ["src/b/", "docs/b.md"])
        message = tasks.declare_parallel_group(str(self.root), [a, b])
        self.assertIn("PG-0001", message)
        # The proof is stated for what it IS, in the message the pilot reads.
        self.assertIn("DECLARED", message)

        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")

        data = tasks.load(self.root)  # `load` accepts the two running tasks
        self.assertEqual([a, b], [t["id"] for t in tasks.running_tasks(data["tasks"])])
        self.assertEqual(a, tasks.focus_task(data["tasks"])["id"])
        self.assertIn("∥2", tasks.statusline(str(self.root)))
        self.assertIn(f"▶ {a}", tasks.statusline(str(self.root)))

    def test_the_focus_is_the_first_in_store_order_whatever_the_start_order(self) -> None:
        """FOCUS RULE, PINNED: first running task in STORE order (creation
        order) — not the last started, not the first sorted. A future sort must
        not move the focus in silence."""
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), b, "running")   # the YOUNGER one first
        tasks.set_state(str(self.root), a, "running")
        self.assertEqual(a, tasks.focus_task(tasks.load(self.root)["tasks"])["id"])

    def test_overlapping_writesets_refuse_the_group_and_name_both_paths(self) -> None:
        for left, right in ((["src/a/"], ["src/a/b.py"]), (["src/A/"], ["src/a/b.py"])):
            with self.subTest(left=left, right=right):
                self.setUp()
                a, b = self.board(left, right)
                with self.assertRaises(tasks.BoardError) as caught:
                    tasks.declare_parallel_group(str(self.root), [a, b])
                message = str(caught.exception)
                self.assertIn(left[0], message)
                self.assertIn(right[0], message)
                self.assertIn("not disjoint", message)
                self.assertEqual("", tasks.parallel_group_of(tasks.load(self.root)["tasks"][0]))

    def test_a_blocked_on_between_members_refuses_the_group(self) -> None:
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.block_task(str(self.root), b, blocked_on=a)
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        self.assertIn("behind that task", str(caught.exception))

    def test_a_member_without_a_writeset_is_refused_as_a_vacuous_proof(self) -> None:
        a, b = self.board(["src/a/"], [])
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        self.assertIn("vacuously true", str(caught.exception))

    def test_a_group_of_one_or_a_task_twice_is_refused(self) -> None:
        a, _b = self.board(["src/a/"], ["src/b/"])
        with self.assertRaises(tasks.BoardError):
            tasks.declare_parallel_group(str(self.root), [a])
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, a])
        self.assertIn("listed twice", str(caught.exception))

    def test_two_running_tasks_without_a_group_load(self) -> None:
        """T-01M5F7286N1EYGXAXA5244X86B (S-01M5DBTHME): several running tasks WITHOUT a group are a
        legitimate board — read, listed and written; the single-group refusal of T-00000188 is retired."""
        a, b = self.board(["src/a/"], ["src/b/"])
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        for task in payload["tasks"]:
            task["state"] = "running"
        self.store.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual([a, b], [t["id"] for t in tasks.running_tasks(tasks.load(self.root)["tasks"])])
        tasks.save(self.root, tasks.load(self.root))
        self.assertIn("∥2", tasks.statusline(str(self.root)))
        tasks.render_list(str(self.root))

    def test_starting_outside_the_group_keeps_the_members(self) -> None:
        a, b = self.board(["src/a/"], ["src/b/"])
        outsider = _id_rendu(tasks.new_task(str(self.root), "hors groupe", "dev-mono"))
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")
        tasks.set_state(str(self.root), outsider, "running")
        data = tasks.load(self.root)
        self.assertEqual([a, b, outsider], [t["id"] for t in tasks.running_tasks(data["tasks"])])
        self.assertEqual("PG-0001", tasks.parallel_group_of(tasks.find(data, a)))

    def test_stage_accepts_any_member_of_the_running_group(self) -> None:
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")

        tasks.stage_running_task(str(self.root), b, "documenter")

        self.assertEqual("documenter", tasks.find(tasks.load(self.root), b)["stage"])
        # A task that is NOT running is still refused, which is the point.
        with self.assertRaises(tasks.BoardError):
            tasks.stage_running_task(str(self.root), "T-00000003", "documenter")

    def test_stale_warning_names_every_running_member(self) -> None:
        today = date(2026, 8, 14)
        stale = (today - timedelta(days=tasks.STALE_RUNNING_DAYS + 1)).isoformat()
        board = [
            {"id": "T-1", "state": "running", "task": "a", "updated": stale,
             "parallel_group": "PG-0001"},
            {"id": "T-2", "state": "running", "task": "b", "updated": stale,
             "parallel_group": "PG-0001"},
        ]
        warning = tasks.stale_running_warning(board, today)
        assert warning is not None
        self.assertIn("T-1", warning)
        self.assertIn("T-2", warning)
        self.assertEqual(2, len(warning.splitlines()))

    def test_a_second_group_over_a_running_member_is_a_legitimate_board(self) -> None:
        """THE T-00000188 HIGH FINDING, INVERTED BY T-01M5F7286N1EYGXAXA5244X86B. `parallel T-1 T-2` ·
        `start` both · `parallel T-1 T-3` moves T-1 into PG-0002 and leaves T-2 running in PG-0001: a
        board every surface still reads (list, statusline), never an unreadable one."""
        a, b = self.board(["src/a/"], ["src/b/"])
        c = _id_rendu(tasks.new_task(str(self.root), "la troisieme", "dev-mono"))
        tasks.set_writeset(str(self.root), c, ["src/c/"])
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")
        self.assertIn("PG-0002 declared", tasks.declare_parallel_group(str(self.root), [a, c]))
        data = tasks.load(self.root)
        self.assertEqual([a, b], [t["id"] for t in tasks.running_tasks(data["tasks"])])
        self.assertEqual(("PG-0002", "PG-0001"), tuple(tasks.parallel_group_of(tasks.find(data, x)) for x in (a, b)))
        self.assertIn("∥2", tasks.statusline(str(self.root)))
        self.assertNotIn("board malformed", tasks.statusline(str(self.root)))
        tasks.render_list(str(self.root))

    def test_an_inadmissible_stored_path_counts_as_an_overlap(self) -> None:
        """"An impossible proof VALUES AS AN OVERLAP" — applied, not just
        declared. A stored `docs//` canonicalises to segments ['docs', ''],
        which compares unequal to `docs` and used to report a FALSE disjunction.
        """
        self.assertIsNotNone(tasks.writeset_paths_overlap(["docs//"], ["docs/a.py"]))
        # …even against a path it shares nothing with: the proof is impossible,
        # so the answer is "overlap", never "disjoint".
        self.assertIsNotNone(tasks.writeset_paths_overlap(["docs//"], ["src/zzz"]))
        self.assertIsNotNone(tasks.writeset_paths_overlap(["C:/x"], ["src/zzz"]))
        # A genuinely disjoint, admissible pair is still disjoint.
        self.assertIsNone(tasks.writeset_paths_overlap(["docs/"], ["src/zzz"]))

    def test_writing_a_writeset_retracts_the_group_it_proved(self) -> None:
        """MEDIUM (b): `--clear` used to empty the declaration and leave the
        group alive — the vacuity `parallel` refuses, re-introduced afterwards.
        Both branches drop the group now, and SAY it; on a LIVE group the drop is
        no longer refused (T-01M5F7286N1EYGXAXA5244X86B): both members keep running."""
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")
        self.assertIn("PG-0001 dropped", tasks.set_writeset(str(self.root), a, [], clear=True))
        data = tasks.load(self.root)
        self.assertEqual(("", "PG-0001"), tuple(tasks.parallel_group_of(tasks.find(data, x)) for x in (a, b)))
        self.assertEqual([a, b], [t["id"] for t in tasks.running_tasks(data["tasks"])])

    def test_refining_a_writeset_on_a_live_member_explains_itself(self) -> None:
        """The MOTIVATING case, not a corner one: adding a GENERATED output to a
        writeset is exactly what `set_writeset`'s docstring recommends; while the
        group runs it now PASSES and says the dropped group and the re-declaration."""
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.declare_parallel_group(str(self.root), [a, b])
        tasks.set_state(str(self.root), a, "running")
        tasks.set_state(str(self.root), b, "running")
        message = tasks.set_writeset(str(self.root), a, ["src/a/", ".agents/ui/"])
        self.assertIn("declared group PG-0001 dropped", message)
        self.assertIn("re-declare", message)
        task = tasks.find(tasks.load(self.root), a)
        self.assertEqual(["src/a/", ".agents/ui/"], tasks.writeset_of(task))
        self.assertEqual("", tasks.parallel_group_of(task))
        self.assertNotIn("dropped", tasks.set_writeset(str(self.root), a, [], clear=True))  # nothing left to drop
        # A REWRITE of the other member retracts ITS group too: the proof was computed on the old paths.
        tasks.set_state(str(self.root), b, "blocked")
        self.assertIn("PG-0001 dropped", tasks.set_writeset(str(self.root), b, ["src/b2/"]))
        self.assertEqual("", tasks.parallel_group_of(tasks.find(tasks.load(self.root), b)))

    def test_a_done_task_cannot_join_a_parallel_group(self) -> None:
        """MEDIUM (c): `parallel` was blind to state — the same blindness that
        made the HIGH possible. A closed task will never run beside another."""
        a, b = self.board(["src/a/"], ["src/b/"])
        tasks.set_state(str(self.root), b, "done", stage="clos par le banc")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        self.assertIn("is done", str(caught.exception))

    def test_writeset_refuses_a_bad_path_without_writing_anything(self) -> None:
        (a,) = self.board(["src/a/"])[:1]
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_writeset(str(self.root), a, ["src/b/", "C:\\evil"])
        self.assertIn("no-colon", str(caught.exception))
        self.assertEqual(["src/a/"], tasks.writeset_of(tasks.find(tasks.load(self.root), a)))

    def test_writeset_folds_separators_rewrites_and_clears(self) -> None:
        (a,) = self.board(["src/a/"])[:1]
        tasks.set_writeset(str(self.root), a, ["src\\b\\", "src/b/"])
        # The fold is the first transformation, and the duplicate collapses.
        self.assertEqual(["src/b/"], tasks.writeset_of(tasks.find(tasks.load(self.root), a)))
        tasks.set_writeset(str(self.root), a, [], clear=True)
        self.assertNotIn("writeset", tasks.find(tasks.load(self.root), a))


class DependsOnTests(unittest.TestCase):
    """``depends_on`` — an ORDER, never a STATE (T-00000530).

    Each test is named after the DEFECT it closes rather than the behaviour it
    describes, because most of them exist to stop a future reader "fixing" the
    asymmetry with ``blocked_on`` by symmetry.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        self.store.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def board(self, count: int) -> list[str]:
        return [
            _id_rendu(tasks.new_task(str(self.root), f"tache {i}", "dev-mono"))
            for i in range(1, count + 1)
        ]

    def read(self, tid: str) -> dict[str, Any]:
        return tasks.find(tasks.load(str(self.root)), tid)

    # --- shape -----------------------------------------------------------

    def test_depends_on_shape_is_validated_but_the_referent_may_dangle(self) -> None:
        """Form is checked at load; EXISTENCE is not. A read surface the
        SessionStart hooks consume cannot start refusing history."""
        (seule,) = self.board(1)
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        raw["tasks"][0]["depends_on"] = ["T-00009999"]  # never existed
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(
            tasks.find(tasks.load(str(self.root)), seule)["depends_on"],
            ["T-00009999"],
        )
        for bad in ("T-1", ["", "T-00000001"], [3], {"a": 1}):
            raw["tasks"][0]["depends_on"] = bad
            self.store.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(tasks.BoardError) as caught:
                tasks.load(str(self.root))
            self.assertIn("invalid depends_on", str(caught.exception))

    def test_absent_and_empty_depends_on_are_the_same_task(self) -> None:
        """ONE stored shape for "no dependency": the key is dropped, never
        written as ``[]`` — same rule as chantier, writeset and blocked_on."""
        a, b = self.board(2)
        self.assertEqual(tasks.depends_on_of(self.read(a)), [])
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_depends(str(self.root), b, [], clear=True)
        self.assertNotIn("depends_on", self.read(b))

    def test_a_hand_edited_cycle_still_LOADS(self) -> None:
        """THE point of putting the guard in the verb: a guard placed in
        ``load`` would refuse ``list``, ``done`` AND the ``depends --clear``
        that repairs the cycle."""
        a, b = self.board(2)
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        for task in raw["tasks"]:
            task["depends_on"] = [b] if task["id"] == a else [a]
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        tasks.load(str(self.root))  # must not raise
        self.assertIn("TASK BOARD", tasks.render_list(str(self.root)))
        # And the remedy runs on that very board.
        tasks.set_depends(str(self.root), a, [], clear=True)
        self.assertNotIn("depends_on", self.read(a))

    # --- refusals --------------------------------------------------------

    def test_self_unknown_and_clear_with_ids_refuse_and_write_nothing(self) -> None:
        a, b = self.board(2)
        before = self.store.read_text(encoding="utf-8")
        for args, needle in (
            (([a],), "cannot depend on itself"),
            ((["T-00009999"],), "unknown"),
        ):
            with self.assertRaises(tasks.BoardError) as caught:
                tasks.set_depends(str(self.root), a, *args, motif="amont livre ce que aval consomme")
            self.assertIn(needle, str(caught.exception).lower())
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), b, [a], clear=True)
        self.assertIn("takes no id", str(caught.exception))
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), b, [])
        self.assertIn("at least one task id", str(caught.exception))
        self.assertEqual(self.store.read_text(encoding="utf-8"), before)

    def test_a_cycle_is_refused_and_the_refusal_names_the_WHOLE_path(self) -> None:
        """Three nodes, not two: a refusal that only caught the direct pair
        would let ``a -> b -> c -> a`` through."""
        a, b, c = self.board(3)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_depends(str(self.root), c, [b], motif="amont livre ce que aval consomme")
        before = self.store.read_text(encoding="utf-8")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), a, [c], motif="amont livre ce que aval consomme")
        message = str(caught.exception)
        for tid in (a, b, c):
            self.assertIn(tid, message)
        self.assertIn("cycle", message)
        self.assertIn("--retirer", message)  # a remedy that drops ONE edge (T-00000765), not `--clear`
        self.assertEqual(self.store.read_text(encoding="utf-8"), before)

    def test_duplicate_ids_are_deduped_AND_the_message_says_so(self) -> None:
        """A silent deduplication reads as a faithful record of what was asked."""
        a, b = self.board(2)
        message = tasks.set_depends(str(self.root), b, [a, a, a], motif="amont livre ce que aval consomme")
        self.assertEqual(self.read(b)["depends_on"], [a])
        self.assertIn("2 duplicate ids dropped", message)

    # --- the asymmetry with blocked_on -----------------------------------

    def test_depends_on_SURVIVES_start_block_unblock_and_done(self) -> None:
        """The negative twin of ``blocked_on``'s "always cleared on exit".
        Persistence is an ABSENCE of code in ``set_state``, so it is pinned
        HERE — this is the test that stops the ``pop`` being added by symmetry.
        ``a`` is closed first: ``start`` refuses an open upstream (S-01M4Z5VMP5E9YN8T6EMDTBAF0T)."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        for verb in (
            lambda: tasks.set_state(str(self.root), b, "running"),
            lambda: tasks.block_task(str(self.root), b, note="attente"),
            lambda: tasks.set_state(str(self.root), b, "pending"),
            lambda: tasks.set_state(str(self.root), b, "done", stage="clos par le banc"),
        ):
            verb()
            self.assertEqual(
                self.read(b).get("depends_on"), [a], "depends_on must survive every state transition",
            )

    def test_closing_a_dependency_leaves_the_dependent_pending_and_KEEPS_the_edge(
        self,
    ) -> None:
        """``blocked_on`` releases on ``done``; ``depends_on`` does not, and
        does not erase either — satisfaction is COMPUTED, never cleared."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        self.assertEqual(self.read(b)["state"], "pending")
        self.assertEqual(self.read(b)["depends_on"], [a])

    def test_a_done_task_is_an_ADMISSIBLE_dependency(self) -> None:
        """Where the symmetry with ``block --on`` breaks on purpose: a done
        dependency is a SATISFIED one, which is what puts its dependent in
        wave 1. ``block --on`` refuses the same thing, and that is correct
        for IT — the contrast is asserted here so neither drifts."""
        a, b = self.board(2)
        tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")  # must not raise
        self.assertEqual(self.read(b)["depends_on"], [a])
        with self.assertRaises(tasks.BoardError):
            tasks.block_task(str(self.root), b, blocked_on=a)

    # --- parallel --------------------------------------------------------

    def test_parallel_refuses_two_members_linked_directly_or_through_a_chain(
        self,
    ) -> None:
        a, b, c = self.board(3)
        for tid, paths in ((a, ["src/a/"]), (b, ["src/b/"]), (c, ["src/c/"])):
            tasks.set_writeset(str(self.root), tid, paths)
        tasks.set_depends(str(self.root), a, [b], motif="amont livre ce que aval consomme")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        self.assertIn("not parallel with it", str(caught.exception))
        # THE CHAIN: a -> b -> c, so a and c are not parallel either.
        tasks.set_depends(str(self.root), b, [c], motif="amont livre ce que aval consomme")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, c])
        message = str(caught.exception)
        self.assertIn("through", message)
        self.assertIn(b, message)  # the intermediate is NAMED

    # --- dangling links --------------------------------------------------

    def test_delete_clears_the_dangling_edge_and_says_it_frees_NOTHING(self) -> None:
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        message = tasks.delete_task(str(self.root), a)
        self.assertNotIn("depends_on", self.read(b))
        # BELT on the ELSE branch of `_clear_dangling_blocked_on`: this test is
        # the only pre-existing one that traverses the total-retrait via delete,
        # and it asserted nothing on the motif — a `pop` dropped there would go
        # unseen. (The dedicated coverage is banc (4).)
        self.assertNotIn("depends_motif", self.read(b))
        self.assertIn("NOT released", message)
        self.assertEqual(self.read(b)["state"], "pending")

    # --- reads -----------------------------------------------------------

    def test_the_inverse_read_refuses_empty_and_unknown_and_group(self) -> None:
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        data = tasks.load(str(self.root))
        self.assertEqual(
            [t["id"] for t in tasks.filter_tasks(data, depends_on=a)], [b]
        )
        for bad in ("", "T-00009999"):
            with self.assertRaises(tasks.BoardError):
                tasks.filter_tasks(data, depends_on=bad)
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.render_list(str(self.root), group=True, depends_on=a)
        self.assertIn("--depends-on", str(caught.exception))

    def test_the_inverse_read_of_a_DONE_task_is_not_empty(self) -> None:
        """The difference with ``--blocked-by``, and the morning-retrospective
        read: closure purges blocked_on links, it does NOT purge these."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        self.assertEqual(
            [t["id"] for t in tasks.filter_tasks(tasks.load(str(self.root)), depends_on=a)],
            [b],
        )

    def test_bare_render_list_is_byte_identical_with_a_depends_on_on_the_board(
        self,
    ) -> None:
        """THE contract the SessionStart hooks of three hosts consume."""
        a, b = self.board(2)
        before = tasks.render_list(str(self.root))
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        self.assertEqual(tasks.render_list(str(self.root)), before)

    def test_format_detail_prints_depends_on_without_a_code_change(self) -> None:
        """Obtained for free by ``format_detail``'s "every key outside FIELDS"
        rule — and a behaviour obtained for free is the first to break in
        silence, so it is pinned."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        detail = tasks.format_detail(self.read(b))
        self.assertIn("depends_on", detail)
        self.assertIn(a, detail)

    def test_depends_emits_a_board_intent_like_regroup(self) -> None:
        """Measured against ``regroup``'s intent rather than a hand-written
        expectation, so the two cannot drift apart."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        outbox = tasks.load(str(self.root)).get("sync_outbox", [])
        self.assertTrue(outbox, "a mutating verb must enqueue a sync intent")

    # --- the motif, required at the write, never judged --------------------

    def test_depends_REFUSES_a_declaration_without_a_motif_and_writes_nothing(self) -> None:
        """Five refusals, each catching a distinct site. Remove the raise → all
        fall; keep only `not motif` → the multiline two fall; drop the `.strip()`
        normalisation → the whitespace-only two ("   ", "\\t") pass and this test
        goes red (M9); test only `\\n` → the `\\r` one falls. Nothing is written
        on any of them."""
        a, b = self.board(2)
        before = self.store.read_text(encoding="utf-8")
        for bad_motif in ("", "   ", "\t", "deux\nlignes", "retour\rchariot"):
            with self.assertRaises(tasks.BoardError) as caught:
                tasks.set_depends(str(self.root), b, [a], motif=bad_motif)
            self.assertIn("--motif", str(caught.exception))
        self.assertEqual(self.store.read_text(encoding="utf-8"), before)

    def test_a_repeated_motif_maps_ONE_reason_PER_EDGE_in_id_order(self) -> None:
        """The ticket's deliverable (B-T1): N motifs pair one-to-one with the ids
        in order, so the reader never reports on A a reason that belongs to B.
        Mutation: revert to `{dep: motif for dep in wanted}` → both edges carry
        the last motif and this test goes red."""
        a, b, c = self.board(3)
        tasks.set_depends(
            str(self.root), c, [a, b],
            motif=["A livre le schema", "B livre le lecteur"],
        )
        stored = self.read(c)["depends_motif"]
        self.assertEqual(stored[a], "A livre le schema")
        self.assertEqual(stored[b], "B livre le lecteur")

    def test_a_single_motif_still_applies_to_EVERY_edge(self) -> None:
        """One --motif stays uniform — the pre-T-00000645 behaviour is preserved
        as the len==1 branch."""
        a, b, c = self.board(3)
        tasks.set_depends(str(self.root), c, [a, b], motif="une seule raison")
        stored = self.read(c)["depends_motif"]
        self.assertEqual(stored[a], "une seule raison")
        self.assertEqual(stored[b], "une seule raison")

    def test_a_motif_count_that_is_neither_one_nor_per_edge_is_REFUSED(self) -> None:
        """Any other count is refused, the message NAMES the expected and the
        received counts, and nothing is written."""
        a, b, c = self.board(3)
        before = self.store.read_text(encoding="utf-8")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), c, [a, b], motif=["un", "deux", "trois"])
        message = str(caught.exception)
        self.assertIn("2", message)   # expected: one per id, two ids
        self.assertIn("3", message)   # received
        self.assertEqual(self.store.read_text(encoding="utf-8"), before)

    def test_a_bad_motif_at_ANY_position_is_refused_and_the_position_is_NAMED(self) -> None:
        """The A-C2 line-boundary bound runs per motif inside the B-C1 loop, so a
        U+2028 at position 2 (which the old `\\n`/`\\r` pair let through) is
        refused and the message names that position. Nothing is written."""
        a, b, c = self.board(3)
        before = self.store.read_text(encoding="utf-8")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), c, [a, b], motif=["ok", "avant apres"])
        message = str(caught.exception)
        self.assertIn("motif #2", message)   # the faulty position is named
        self.assertIn("U+2028", message)     # the broadened bound is named
        self.assertEqual(self.store.read_text(encoding="utf-8"), before)

    def test_clear_with_a_motif_is_REFUSED_rather_than_swallowed(self) -> None:
        """--clear removes the whole declaration, so a --motif alongside it has no
        edge to motivate: refuse it loudly instead of eating it (B-C7). Mutation:
        drop the `if clear and any(motifs)` guard → the call returns rc 0 and this
        test goes red."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.set_depends(str(self.root), b, [], clear=True, motif="x")
        message = str(caught.exception)
        self.assertIn("--clear", message)
        self.assertIn("--motif", message)

    def test_the_motif_refusal_comes_BEFORE_the_unknown_TASK_id_the_unknown_dep_and_the_cycle(
        self,
    ) -> None:
        """The motif is an ARGUMENT check, so it fires before any store lookup.
        Mutation: place control (3) anywhere after `find(data, tid)` → the first
        call surfaces "unknown" and this test goes red."""
        a, b, c = self.board(3)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_depends(str(self.root), c, [b], motif="amont livre ce que aval consomme")
        for tid, deps in (("T-00009999", [a]), (b, ["T-00009999"]), (a, [c])):
            with self.assertRaises(tasks.BoardError) as caught:
                tasks.set_depends(str(self.root), tid, deps)  # NO motif
            message = str(caught.exception)
            self.assertIn("--motif", message)
            self.assertNotIn("unknown", message.lower())
            self.assertNotIn("cycle", message)

    def test_a_missing_motif_TAKES_NO_LOCK_and_LOADS_NOTHING(self) -> None:
        from contextlib import contextmanager
        a, b = self.board(2)            # la fixture appelle load() — d'où la remise à zéro plus bas
        real_lock, real_load = tasks.board_lock, tasks.load
        calls = {"lock": 0, "load": 0}

        @contextmanager
        def counting_lock(*args, **kw):          # args, PAS *a : `a` est la fixture
            calls["lock"] += 1
            with real_lock(*args, **kw):
                yield

        def counting_load(*args, **kw):
            calls["load"] += 1
            return real_load(*args, **kw)

        with mock.patch.object(tasks, "board_lock", counting_lock), mock.patch.object(
            tasks, "load", counting_load
        ):
            calls["lock"] = calls["load"] = 0    # APRÈS l'entrée des patches, AVANT l'appel
            with self.assertRaises(tasks.BoardError):
                tasks.set_depends(str(self.root), b, [a])
        self.assertEqual(calls, {"lock": 0, "load": 0})

    def test_clear_and_full_retrait_drop_the_WHOLE_motif_dict(self) -> None:
        """TWO total-retrait sites, DIFFERENT triggers, one assertion each:
        (a) the clear path of set_depends; (b) the else branch of
        _clear_dangling_blocked_on reached by delete on the LAST dependency."""
        a, b = self.board(2)
        # (a) clear path
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.set_depends(str(self.root), b, [], clear=True)
        self.assertNotIn("depends_motif", self.read(b))
        # (b) else branch of _clear_dangling_blocked_on, via delete — NOT --clear
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        tasks.delete_task(str(self.root), a)
        self.assertNotIn("depends_motif", self.read(b))

    def test_a_partial_purge_KEEPS_only_the_remaining_motif_key(self) -> None:
        """A partial purge REDUCES the dict to the surviving edges. Mutation:
        drop the filtering → the vanished key survives and this test goes red."""
        a, b, c = self.board(3)
        tasks.set_depends(str(self.root), b, [a, c], motif="raison partagee")
        tasks.delete_task(str(self.root), a)
        self.assertEqual(self.read(b)["depends_on"], [c])
        self.assertEqual(self.read(b)["depends_motif"], {c: "raison partagee"})

    def test_a_legacy_edge_without_motif_still_LOADS_and_is_reported_as_such(self) -> None:
        """A depends_on with no depends_motif is the form the board carries
        today; it must load, and depends-show must name it. Mutation: require
        depends_motif at load → load raises and this test goes red."""
        a, b = self.board(2)
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        for task in raw["tasks"]:
            if task["id"] == b:
                task["depends_on"] = [a]  # legacy edge, NO depends_motif
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        tasks.load(str(self.root))  # must not raise
        report = tasks.render_depends_show(str(self.root), b)
        self.assertIn("SANS MOTIF (héritée)", report)

    def test_a_STRICT_SUBSET_of_keys_in_depends_motif_is_ACCEPTED_at_load(self) -> None:
        """Piège 2 transposed to the dict. Mutation: require EQUALITY of keys →
        this strict-subset store fails to load and the test goes red."""
        a, b, c = self.board(3)
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        for task in raw["tasks"]:
            if task["id"] == b:
                task["depends_on"] = [a, c]
                task["depends_motif"] = {a: "raison amont"}  # strict subset
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        tasks.load(str(self.root))  # must not raise
        self.assertEqual(self.read(b)["depends_motif"], {a: "raison amont"})

    def test_an_invalid_motif_dict_SHAPE_is_refused_at_load(self) -> None:
        """ONE muted site (the load validation), SIX cases each reddening on its
        own: accept a scalar → 1st; accept an empty value → 2nd; drop `.strip()`
        so a whitespace-only "   " loads → 3rd (A-C1, load bound = write bound);
        test NEITHER \\n nor \\r → 4th AND 5th; test only \\n → 5th alone; drop
        `issubset` so a key OUTSIDE depends_on loads → 6th (M14). Each goes red on
        its own."""
        a, b = self.board(2)
        raw = json.loads(self.store.read_text(encoding="utf-8"))

        def _set_motif(value: Any) -> None:
            for task in raw["tasks"]:
                if task["id"] == b:
                    task["depends_on"] = [a]
                    task["depends_motif"] = value
            self.store.write_text(json.dumps(raw), encoding="utf-8")

        for bad in (
            "scalaire",
            {a: ""},
            {a: "   "},
            {a: "deux\nlignes"},
            {a: "retour\rchariot"},
            {"T-00009999": "orpheline"},
        ):
            _set_motif(bad)
            with self.assertRaises(tasks.BoardError) as caught:
                tasks.load(str(self.root))
            self.assertIn("invalid depends_motif", str(caught.exception))

    def test_depends_show_reports_satisfied_WAITING_dangling_and_motiveless_and_EXITS_ZERO(
        self,
    ) -> None:
        """FOUR surfaces, FOUR assertions: the three classes, the motiveless
        fallback, and exit 0. Each mutation reddens a different assertion."""
        a, b, c, d = self.board(4)
        tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        for task in raw["tasks"]:
            if task["id"] == d:
                task["depends_on"] = [a, b, "T-00009999"]
                task["depends_motif"] = {a: "amont livre ce que aval consomme"}
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        report = tasks.render_depends_show(str(self.root), d)
        self.assertIn("SATISFAITE", report)            # a is done
        self.assertIn("EN ATTENTE", report)            # b exists and is pending
        self.assertIn("PENDOUILLANTE", report)         # T-00009999 is absent
        self.assertIn("SANS MOTIF (héritée)", report)  # b carries no motif
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), "depends-show", d])
        self.assertEqual(0, rc)

    def test_depends_show_TOLERATES_a_short_form_subject_like_every_reader(self) -> None:
        """A-C6/B-C5: depends-show is a READER, so it resolves `T-2`/`2` like
        `list` does, instead of the exact-only `find` that made it the one reader
        to refuse a short form. The "never raise" rule is about each edge's
        REFERENT, not the subject. Mutation: revert to `find(data, tid)` → the
        short call raises and this test goes red.

        LEGACY IDS WRITTEN AS AN INPUT FIXTURE, never allocated: a short form is
        a property of a legacy id, and no task allocated after the switch to
        `P-<ULID>` (T-00000726) has one — deriving it from an allocated id
        (`numeric_id(b)`) would cut a ULID into a number (R-BANCS (ii))."""
        a, b = "T-00000001", "T-00000002"
        self.store.write_text(json.dumps({"tasks": [
            {"id": tid, "state": "pending", "task": f"tache {tid}", "owner": "dev-mono",
             "stage": "", "updated": "2026-10-01"}
            for tid in (a, b)
        ]}), encoding="utf-8")
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        report = tasks.render_depends_show(str(self.root), "2")
        self.assertIn(b, report)
        self.assertIn(a, report)

    def test_done_WARNS_on_an_unsatisfied_dependency_and_changes_NO_state(self) -> None:
        """A DIRE, not a transition. Mutation PROPER to this bench: drop the
        added line in set_state (NOT turning it into a raise — that reddens
        test_depends_on_SURVIVES instead)."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        message = tasks.set_state(str(self.root), b, "done", stage="clos par le banc")
        self.assertIn("non satisfaite", message)
        self.assertIn(a, message)
        self.assertEqual(self.read(a)["state"], "pending")  # no state changed
        self.assertEqual(self.read(b)["state"], "done")     # it WAS closed, not refused

    def test_format_detail_renders_the_motif_dict_WITHOUT_a_python_repr(self) -> None:
        """Modelled on test_format_detail_prints_depends_on. Mutation: remove the
        dict branch of cell → a Python repr `{'T-...': ...}` reappears."""
        a, b = self.board(2)
        tasks.set_depends(str(self.root), b, [a], motif="amont livre ce que aval consomme")
        detail = tasks.format_detail(self.read(b))
        self.assertIn("depends_motif", detail)
        self.assertIn(f"{a} → amont livre ce que aval consomme", detail)
        self.assertNotIn("{'", detail)

    def test_parallel_refusal_names_clear_and_shows_NO_bare_depends_command(self) -> None:
        """The chain refusal must name a `--retirer` remedy (T-00000765: drop ONE
        edge, never `--clear`) and NOT carry a bare recopiable `tasks.py depends …`.
        Mutation: revert to the origin message."""
        a, b = self.board(2)
        for tid, paths in ((a, ["src/a/"]), (b, ["src/b/"])):
            tasks.set_writeset(str(self.root), tid, paths)
        tasks.set_depends(str(self.root), a, [b], motif="amont livre ce que aval consomme")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        message = str(caught.exception)
        self.assertIn(f"--retirer {b}", message)
        self.assertNotIn("tasks.py depends …", message)

    def test_parallel_chain_refusal_RE_STATES_the_surviving_edges_not_a_blanket_clear(
        self,
    ) -> None:
        """A-C4, amended by T-00000765: when chain[0] carries edges beyond the one
        that clashes, the remedy drops THAT edge with `--retirer <b>` and names the
        survivors — replayed, `c` and its motif survive. Mutation: revert to the
        bare `--clear` message → the surviving id vanishes from the remedy and
        this test goes red."""
        a, b, c = self.board(3)
        for tid, paths in ((a, ["src/a/"]), (b, ["src/b/"]), (c, ["src/c/"])):
            tasks.set_writeset(str(self.root), tid, paths)
        # a is behind BOTH b and c; grouping [a, b] must NOT erase the a→c edge.
        tasks.set_depends(str(self.root), a, [b, c], motif="amont livre ce que aval consomme")
        with self.assertRaises(tasks.BoardError) as caught:
            tasks.declare_parallel_group(str(self.root), [a, b])
        message = str(caught.exception)
        self.assertIn(c, message)                  # the surviving edge is named
        self.assertIn(f"--retirer {b}", message)   # the remedy drops ONE edge
        self.assertNotIn("--clear", message)       # never the destructive blanket here
        tasks.set_depends(str(self.root), a, [], retirer=b)  # replayed: c and its motif survive
        self.assertEqual(self.read(a)["depends_on"], [c])
        self.assertEqual(self.read(a)["depends_motif"], {c: "amont livre ce que aval consomme"})

    def test_a_partial_purge_of_a_motifless_edge_creates_no_depends_motif_key(self) -> None:
        """The defect B-C1 closed: a nude comprehension CREATES the key it should
        only reduce. b has depends_on=[a, c] and NO depends_motif (legacy). After
        `delete a`, no depends_motif key may appear. Mutation: drop the
        `if filtre: … else: pop` guard → b gains a `depends_motif: {}` from
        nothing and this test goes red."""
        a, b, c = self.board(3)
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        for task in raw["tasks"]:
            if task["id"] == b:
                task["depends_on"] = [a, c]  # legacy edge, NO depends_motif
        self.store.write_text(json.dumps(raw), encoding="utf-8")
        tasks.delete_task(str(self.root), a)
        self.assertNotIn("depends_motif", self.read(b))

    def test_done_on_a_task_WITHOUT_depends_on_adds_NO_warning_line(self) -> None:
        """The OTHER side of the done warning. Mutation: emit the line
        unconditionally (with "0 dépendance(s) non satisfaite(s)") → this reddens
        while test_done_WARNS stays green, which is why both are needed."""
        (a,) = self.board(1)
        message = tasks.set_state(str(self.root), a, "done", stage="clos par le banc")
        self.assertNotIn("non satisfaite", message)


class CommitStoresLockLegTests(unittest.TestCase):
    """The LOCK leg of the post-done commit (T-00000189, volet 1) — one arm per
    property the shell suite cannot reach from python. The verb has three legs;
    this is the one that never had an arm."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        (self.root / ".agents" / "bin").mkdir(parents=True)
        # A real section script so the resolved path exists; it prints a token.
        (self.root / ".agents" / "bin" / "post-task-done-index.sh").write_text(
            "#!/usr/bin/env bash\nprintf committed\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_launches_resolved_bash_never_the_bare_string(self) -> None:
        import shutil

        real = shutil.which("bash")
        if not real:
            self.skipTest("no bash on PATH (precedent test_dashboard.py:5773-5793)")
        captured: dict[str, Any] = {}

        class _R:
            stdout = "committed"
            returncode = 0

        def spy(argv, **kw):
            captured["argv"] = argv
            return _R()

        with mock.patch("subprocess.run", spy):
            tok = tasks.commit_stores(str(self.root))
        argv = captured["argv"]
        self.assertEqual(argv[0], real)  # the RESOLVED bash, L-00000166
        self.assertNotEqual(argv[0], "bash")  # never the bare string
        self.assertNotIn("system32", argv[0].replace("\\", "/").lower())
        # the root comes from the ARGUMENT, never the current directory
        self.assertEqual(argv[2], "--commit-section")
        self.assertEqual(argv[3], str(self.root))
        self.assertTrue(argv[1].endswith("post-task-done-index.sh"))
        self.assertEqual(tok, "committed")

    def test_which_none_degrades_to_bash_introuvable(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            tok = tasks.commit_stores(str(self.root))
        self.assertEqual(tok, "bash-introuvable")

    def test_system32_resolution_is_rejected(self) -> None:
        with mock.patch("shutil.which", return_value=r"C:\Windows\System32\bash.exe"):
            tok = tasks.commit_stores(str(self.root))
        self.assertEqual(tok, "bash-introuvable")

    def test_lock_timeout_yields_locked_out(self) -> None:
        from contextlib import contextmanager

        @contextmanager
        def raiser(*a, **k):
            raise tasks.BoardError("held past the bound")
            yield  # unreachable, keeps this a generator for @contextmanager

        with mock.patch("shutil.which", return_value="/usr/bin/bash"), mock.patch.object(
            tasks, "board_lock", raiser
        ):
            tok = tasks.commit_stores(str(self.root))
        self.assertEqual(tok, "locked-out")

    def test_the_verb_exits_zero_on_every_issue(self) -> None:
        rc = tasks.main(["--root", str(self.root), "commit-stores"])
        self.assertEqual(rc, 0)

    def test_exiger_turns_a_failure_token_into_a_nonzero_exit(self) -> None:
        """T-00001044 — the night's closing chains `commit-stores --exiger &&
        commit-run-exports --exiger && verify.sh` because `claude -p` refuses the
        old `tok=$(...); case ... esac` form in headless. Same semantics as
        `commit-run-exports --exiger`: rc 1 on any token but `committed`/`nothing`,
        and rc 0 WITHOUT the flag on the very same tokens (the `done` hook path).
        On the old CLI the flag is unknown: argparse exits 2 — red, not skipped."""
        jetons = [
            ("committed", 0),
            ("nothing", 0),
            ("failed", 1),
            ("locked-out", 1),
            ("bash-introuvable", 1),
            ("busy:MERGE_HEAD", 1),
            ("", 1),
        ]
        for jeton, attendu in jetons:
            with self.subTest(jeton=jeton), mock.patch.object(
                tasks, "commit_stores", lambda root, lock_timeout=None, _j=jeton: _j
            ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                try:
                    rc = tasks.main(["--root", str(self.root), "commit-stores", "--exiger"])
                except SystemExit as exc:  # old CLI: `--exiger` unknown to argparse
                    self.fail(f"--exiger refused by argparse (exit {exc.code})")
                self.assertEqual(rc, attendu, f"--exiger on {jeton!r} must exit {attendu}")
                self.assertEqual(out.getvalue().strip(), jeton, "the token is still printed")
                self.assertEqual(
                    tasks.main(["--root", str(self.root), "commit-stores"]),
                    0,
                    f"the done-hook path must exit 0 on {jeton!r}",
                )

    def test_name_isolates_two_distinct_locks(self) -> None:
        r = str(self.root)
        self.assertNotEqual(tasks.lock_path(r, "X.lock"), tasks.lock_path(r, "Y.lock"))
        self.assertEqual(tasks.lock_path(r).name, "TASKS.lock")  # default unchanged
        self.assertEqual(
            tasks.lock_path(r, tasks.POST_TASK_DONE_LOCK).name, "POST_TASK_DONE.lock"
        )
        # two different names are held at once WITHOUT deadlock
        with tasks.board_lock(r, name="X.lock"):
            with tasks.board_lock(r, name="Y.lock"):
                pass

    def test_default_timeout_is_read_in_the_body(self) -> None:
        import inspect

        default = inspect.signature(tasks.board_lock).parameters["timeout_seconds"].default
        self.assertIsNone(default)  # moved out of the signature, into the body

    def test_normalize_root_translates_msys_and_no_ops_native(self) -> None:
        import os

        native = str(self.root)
        self.assertEqual(tasks.normalize_root(native), native)  # no-op, portable
        if os.name != "nt" or native[1:2] != ":":
            self.skipTest("MSYS /c/ translation is a Windows concern")
        msys = "/" + native[0].lower() + native[2:].replace("\\", "/")
        got = tasks.normalize_root(msys)
        self.assertEqual(
            tasks.lock_path(got, tasks.POST_TASK_DONE_LOCK).resolve(),
            tasks.lock_path(native, tasks.POST_TASK_DONE_LOCK).resolve(),
        )
        self.assertNotEqual(got, msys)  # non-vacuity: the translation branch ran


class CommitRunExportsIsNotMutatingTests(unittest.TestCase):
    """`commit-run-exports` (T-00000677, correctif T3 du binôme) must stay OUT of
    the `mutating` set. Committing run exports is not a board mutation, and a V3
    replay around it would write NEW events into `runs/` — the very files the verb
    has just committed, so a night's closing would never converge.

    The shell arm in `tasks.test.sh` reads the same literal; this is the canonical
    python home, next to the other legs of the post-done commit verb.

    THE TRAP THIS TEST CLOSES: an `assertNotIn` alone is VACANT — it passes just as
    well when the verb does not exist at all. So the verb's EXISTENCE is asserted
    first, and the `mutating` block's non-vacuity right after."""

    def setUp(self) -> None:
        self.source = TASKS_PATH.read_text(encoding="utf-8")
        # A throwaway root for the exit-code arm: the verb is stubbed, so nothing
        # under it is ever written — but `--root` must point somewhere real.
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _mutating_block(self) -> str:
        debut = self.source.index("mutating = args.cmd in {")
        bloc = self.source[debut:]
        return bloc[: bloc.index("} and not")]

    def test_the_verb_exists_at_all(self) -> None:
        # Guards the vacuity of the test below: a removed verb must not read as
        # "correctly excluded".
        self.assertIn('"commit-run-exports"', self.source)

    def test_commit_run_exports_is_absent_from_the_mutating_set(self) -> None:
        bloc = self._mutating_block()
        self.assertIn('"done"', bloc)  # non-vacuity: the block really was captured
        self.assertNotIn('"commit-run-exports"', bloc)

    def test_commit_stores_is_absent_from_the_mutating_set(self) -> None:
        """T-00000724 — the SIBLING verb `commit-stores` is out of `mutating` for
        the same reason (a V3 replay around the stores commit would dirty `runs/`
        again), and the doctrine says « the two `commit-*` verbs are OUT » — until
        this case only one of the two was pinned. Same trap, same order: the
        verb's existence first (an absent verb must not read as « correctly
        excluded »), the block's non-vacuity next, the absence last."""
        self.assertIn('"commit-stores"', self.source)
        bloc = self._mutating_block()
        self.assertIn('"done"', bloc)
        self.assertNotIn('"commit-stores"', bloc)

    def test_exiger_turns_a_failure_token_into_a_nonzero_exit(self) -> None:
        """T-00000677 B1 — `--exiger` is what makes "a failure PREVENTS the push"
        a MECHANISM instead of prose: the token becomes an EXIT CODE, so the
        night chains the gate with `&&`. The closure pair measured the earlier
        state — the verb exited 0 whatever it returned, and the only witness
        checked the SENTENCE in night.md, not the effect (L-00000111).

        This arm asserts the EFFECT, and its second assertion is what keeps it
        honest: the `done` hook passes no `--exiger`, so its "always exit 0"
        contract must hold on the very same tokens. A test that only checked the
        non-zero side would pass just as well if the flag were made mandatory."""
        jetons = [
            ("committed", 0),
            ("nothing", 0),
            ("failed", 1),
            ("locked-out", 1),
            ("bash-introuvable", 1),
            ("busy:MERGE_HEAD", 1),
        ]
        origine = tasks.commit_run_exports
        try:
            for jeton, attendu in jetons:
                with self.subTest(jeton=jeton):
                    tasks.commit_run_exports = (
                        lambda root, lock_timeout=None, _j=jeton: _j
                    )
                    self.assertEqual(
                        tasks.main(["--root", str(self.root), "commit-run-exports", "--exiger"]),
                        attendu,
                        f"--exiger on {jeton!r} must exit {attendu}",
                    )
                    self.assertEqual(
                        tasks.main(["--root", str(self.root), "commit-run-exports"]),
                        0,
                        f"the done-hook path must exit 0 on {jeton!r}",
                    )
        finally:
            tasks.commit_run_exports = origine


def _jointure_board_v3(mapping_rows, correlations, events_tasks, *, exclure_tombes):
    """La jointure `events_ledger ⋈ sync_correlations` rapportée à
    `task_board_mapping`, PAR `board_task_id` (T-00000677, témoins 11a/11b).

    Deux constats MESURÉS le 2026-09-21 sur la base réelle, écrits ICI plutôt que
    contournés — la jointure NAÏVE par `operation_id` ne tient PAS :
      * `create_operation_id` (mapping) et la clé de `sync_correlations` PEUVENT
        différer : T-00000573 avait son événement sous l'op de CRÉATION `d6c40430`
        et sa corrélation board sous une op de DELTA `a1eceddf` (sans événement),
        RÉALIGNÉE sur `d6c40430` par T-00001060 (S-00003372). La jointure reste par
        `board_task_id`, la présence d'un événement par `events_ledger.task_id`,
        JAMAIS par l'égalité des op : une autre tâche peut porter le même écart.
      * la pierre tombale est EFFECTIVE si le lien V3 OU une corrélation la porte
        (comme `BoardBridge._board_state`). `task_board_mapping` (RÉFÉRENCE) est
        pris VIVANT (`tombstoned=0`) ; la jointure exclut les corrélations mortes.

    `exclure_tombes=False` est la MUTATION du témoin : la jointure regagne les
    entrées mortes présentes en base et diverge de la référence vivante."""
    reference = {
        m["board_task_id"] for m in mapping_rows
        if int(m["tombstoned"]) == 0 and m["board_task_id"] in events_tasks
    }
    jointure = {
        v["board_task_id"] for v in correlations.values()
        if v.get("board_task_id") in events_tasks
        and not (exclure_tombes and v.get("tombstoned"))
    }
    return reference, jointure


class BackfillJointureFabriqueeTests(unittest.TestCase):
    """Témoin 11b (T-00000677) — base FABRIQUÉE sous `tempfile`, PERMANENT, sans
    garde `T650_JAMBE_DE_LOT` ni non-vacuité `BoardBridge` (fixture synthétique) :
      (1) `task_projections` reconstruites depuis les exports == celles de la source ;
      (2) `events_ledger ⋈ sync_correlations` (pierres tombales EXCLUES) rejoint
          EXACTEMENT `task_board_mapping` (vivant).
    MUTATION (celle du plan) : joindre `sync_correlations` SANS exclure les pierres
    tombales — la jointure gagne l'entrée morte et diverge de `task_board_mapping`."""

    @staticmethod
    def _projections(db: Path) -> dict:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            return {
                r["task_id"]: (r["status"], r["retry_count"], r["is_blocked"])
                for r in conn.execute(
                    "SELECT task_id,status,retry_count,is_blocked FROM task_projections"
                )
            }
        finally:
            conn.close()

    def test_task_board_mapping_rejoint_les_exports_base_fabriquee_permanent(self):
        from agentic_v3.db.event_store import EventStore
        from agentic_v3.db import run_export as rx

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "proj").mkdir()
        (root / "state").mkdir()
        env = mock.patch.dict(os.environ, {
            "CADRE_PROJECT_ROOT": str(root / "proj"),
            "CADRE_STATE_DIR": str(root / "state"),
        })
        env.start()
        self.addCleanup(env.stop)
        mail = mock.patch.object(rx, "_email_git", return_value="banc@test")
        mail.start()
        self.addCleanup(mail.stop)

        source = root / "state" / "source.db"
        store = EventStore(source)  # project_root -> CADRE_PROJECT_ROOT
        # (a) trafic RUN : projections + exports (TASK_CREATED -> PENDING).
        for i in range(3):
            store.append_event(
                f"T-R{i}", "run", "TASK_CREATED", {"req_id": f"R{i}"},
                operation_id=f"reel-{i}",
            )
        # (b) tâches BOARD : mapping + corrélations + événements HISTORIQUES
        #     (ulid NULL), dont UNE pierre tombale (T-B4) — l'entrée morte.
        correlations: dict = {}
        conn = sqlite3.connect(str(source))
        for i, (board, tomb) in enumerate([("T-B1", 0), ("T-B2", 0), ("T-B3", 0), ("T-B4", 1)]):
            op = f"create-{board}"
            conn.execute(
                "INSERT INTO task_board_mapping "
                "(board_task_id,v3_task_id,create_operation_id,tombstoned) "
                "VALUES (?,?,?,?)",
                (board, f"V3:{board}", op, tomb),
            )
            correlations[op] = {"board_task_id": board, "tombstoned": bool(tomb)}
            conn.execute(
                "INSERT INTO events_ledger (task_id,agent_role,event_type,"
                "payload_json,created_at,operation_id,event_kind,attempt) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (board, "BoardBridge", "BOARD_TASK_OBSERVED", "{}",
                 f"2026-08-0{i + 1} 00:00:00", op, "BOARD_TASK_OBSERVED", 0),
            )
        conn.commit()
        conn.close()
        # (c) backfill : frappe + exporte les historiques (BOARD ne projette pas).
        rx.backfill_historique(base=source)

        # (1) reconstruction des projections == source.
        proj_src = self._projections(source)
        self.assertEqual(len(proj_src), 3, "les 3 TASK_CREATED du trafic run")
        cible = root / "state" / "reconstruit.db"
        EventStore(cible).reconstruire_depuis_exports(rx.project_root())
        self.assertEqual(
            self._projections(cible), proj_src,
            "les task_projections reconstruites divergent de la source",
        )

        # (2) events_ledger ⋈ sync_correlations (tombes exclues) == mapping vivant.
        conn = sqlite3.connect(str(source))
        conn.row_factory = sqlite3.Row
        mapping_rows = list(
            conn.execute("SELECT board_task_id,tombstoned FROM task_board_mapping")
        )
        events_tasks = {
            r[0] for r in conn.execute("SELECT DISTINCT task_id FROM events_ledger")
        }
        conn.close()
        reference, jointure = _jointure_board_v3(
            mapping_rows, correlations, events_tasks, exclure_tombes=True
        )
        self.assertEqual(
            jointure, reference,
            "events⋈correlations (tombes exclues) != task_board_mapping vivant",
        )
        self.assertEqual(reference, {"T-B1", "T-B2", "T-B3"}, "population attendue")
        # MUTATION intégrée : sans exclure les tombes, la jointure gagne T-B4 mort.
        _, jointure_mut = _jointure_board_v3(
            mapping_rows, correlations, events_tasks, exclure_tombes=False
        )
        self.assertNotEqual(
            jointure_mut, reference,
            "la jointure DOIT exclure les pierres tombales (sinon T-B4 morte entre)",
        )
        self.assertIn("T-B4", jointure_mut, "la mutation regagne bien l'entrée morte")


class BackfillJointureReelleTests(unittest.TestCase):
    """Témoin 11a (T-00000677, ARMÉ par `T650_JAMBE_DE_LOT=1`, UNE fois, sur la
    COPIE de 1a passée par `T650_COPIE`) — la PREUVE porteuse, après trafic réel.

    AMENDEMENT DATÉ 2026-09-21, écrit ICI plutôt que contourné (leçon : un contrat
    du plan que le code ne tient plus s'AMENDE, jamais un témoin rétréci en silence).
    Le plan écrivait « task_projections reconstruites depuis les exports == celles de
    la copie ». MESURÉ FAUX sur la base réelle : `reconstruire_depuis_exports` ne
    rejoue QUE les projections d'événements de RUN (`_apply_projection` :
    TASK_CREATED/CODE_GENERATED/CRITIC_VERDICT/TEST_RUN), et le trafic V3 de CE dépôt
    est EXCLUSIVEMENT du board (BOARD_TASK_OBSERVED/BOARD_RUNNING_REPLACED, qui ne
    projettent PAS par cette voie — borne écrite dans la docstring de la fonction).
    La copie porte 574 `task_projections` (issues de `_reduce_board_intent`) que la
    reconstruction ne reproduit pas (0). L'égalité est donc INAPPLICABLE ; les
    assertions QUI TIENNENT et qui portent la preuve sont conservées et renforcées :
      * la JOINTURE `events_ledger ⋈ sync_correlations` (tombes exclues) rejoint
        EXACTEMENT `task_board_mapping` VIVANT de la copie — la correspondance
        board↔V3 est intacte après backfill ;
      * NON-VACUITÉ : l'ensemble comparé CONTIENT ≥ 1 ligne `agent_role='BoardBridge'`
        à `ulid` non NULL (précondition 2 : le trafic réel EST dans la jointure) ;
      * la reconstruction depuis le `runs/` RÉEL COUVRE tous les board_task_id de la
        référence (leurs événements survivent au backfill) — la fidélité fine des
        lignes est prouvée à part par le témoin 10a (mêmes operation_id, même compte).

    Le plan avait déjà prévu la branche PÉRIMÈTRE DÉGRADÉ « si l'égalité ne tient
    pas » ; ici l'égalité PORTEUSE (la jointure) TIENT — c'est l'égalité des
    projections, inapplicable au trafic board, qui est remplacée.

    T-00000691 (2026-09-26) : la borne ci-dessus est LEVÉE dans le code — les
    projections board et les liens (`task_board_mapping`, projections `BOARD:*`,
    `board_sync_inbox`) SONT rebâties, en une transaction, et d'office à
    l'ouverture d'une base vide. Ce témoin n'en change aucune assertion : il reste
    la preuve de la JOINTURE après backfill ; l'égalité des tables reconstruites est
    portée par les témoins T3/T12 de `agentic_v3/tests/test_run_export.py` et par
    les critères C-P/C-C du plan de T-00000691."""

    ROOT = Path(__file__).resolve().parents[2]

    @unittest.skipUnless(
        os.environ.get("T650_JAMBE_DE_LOT") == "1",
        "jambe de lot non armee : store du run hors depot",
    )
    def test_task_board_mapping_rejoint_les_exports_apres_trafic_reel(self):
        copie = Path(os.environ["T650_COPIE"])
        # adopting-tree: preuve ARMEE sur la base REELLE — elle DOIT lire le board reel du depot (sync_correlations), sinon la jointure ne prouve rien ; jamais jouee chez un adoptant (skipUnless T650_JAMBE_DE_LOT)
        # La forme PRÉSENTE du board (monolithe OU enregistrements) par `lire_board_brut`, le lecteur du module
        # tasks (T-00000727) : sur un board en dossier, `sync_correlations` est la PROJECTION des `sync_operations`
        # de chaque enregistrement (T-01M4KKMY43ZKCW1YD2Y8JX9MKH), jamais une table lue d'un fichier. Avant, ce
        # témoin lisait `TASKS.json` en octets : sur le kit basculé il levait `FileNotFoundError` (mesuré).
        board = tasks.lire_board_brut(str(self.ROOT))
        correlations = board.get("sync_correlations", {})

        conn = sqlite3.connect(str(copie))
        conn.row_factory = sqlite3.Row
        mapping_rows = list(
            conn.execute("SELECT board_task_id,tombstoned FROM task_board_mapping")
        )
        events_tasks = {
            r[0] for r in conn.execute("SELECT DISTINCT task_id FROM events_ledger")
        }
        conn.close()
        # NON-VACUITÉ FIDÈLE À LA PRÉCONDITION 2 : le trafic RÉEL, PAS le backfill.
        # Après 1a, TOUTE ligne de la copie porte un ulid — « ulid non NULL » ne
        # distingue plus le réel du reconstruit. Le trafic réel est isolable par sa
        # <copie> d'export (≠ « backfill ») : ce sont les lignes écrites par
        # l'écrivain unifié, JAMAIS frappées a posteriori.
        taches_trafic_reel = set()
        # adopting-tree: preuve ARMEE — elle DOIT lire le runs/ REEL du depot pour isoler le trafic reel du backfill ; jamais jouee chez un adoptant (skipUnless T650_JAMBE_DE_LOT)
        for chemin in (self.ROOT / "runs").glob("*/*/*.jsonl"):
            if chemin.parent.name == "backfill":
                continue
            for brute in chemin.read_text(encoding="utf-8").splitlines():
                brute = brute.strip()
                if not brute:
                    continue
                obj = json.loads(brute)
                if obj.get("ulid") and obj.get("task_id"):
                    taches_trafic_reel.add(obj["task_id"])

        reference, jointure = _jointure_board_v3(
            mapping_rows, correlations, events_tasks, exclure_tombes=True
        )
        # (2) events_ledger ⋈ sync_correlations (tombes exclues) == mapping vivant.
        self.assertEqual(
            jointure, reference,
            f"jointure {len(jointure)} != mapping vivant {len(reference)} "
            f"(diff : {sorted((jointure ^ reference))[:5]})",
        )
        # non-vacuité : ≥ 1 tâche de TRAFIC RÉEL (écrite par l'écrivain unifié,
        # <copie> ≠ backfill) DANS la jointure vivante — la précondition 2.
        reel_dans_jointure = taches_trafic_reel & jointure
        self.assertTrue(
            reel_dans_jointure,
            "aucune tâche de trafic réel (écrivain unifié, hors backfill) dans la "
            "jointure — le trafic réel (précondition 2) n'est pas prouvé présent",
        )
        # MUTATION : sans exclure les tombes, la jointure regagne les entrées mortes.
        _, jointure_mut = _jointure_board_v3(
            mapping_rows, correlations, events_tasks, exclure_tombes=False
        )
        self.assertNotEqual(
            jointure_mut, reference,
            "la jointure DOIT exclure les pierres tombales",
        )

        # (3) la reconstruction depuis le runs/ RÉEL couvre tous les board de la réf.
        dossier = Path(tempfile.mkdtemp(prefix="cadre_11a_")).resolve()
        self.addCleanup(shutil.rmtree, dossier, ignore_errors=True)
        cible = dossier / "reconstruit.db"
        from agentic_v3.db.event_store import EventStore

        EventStore(cible, project_root=self.ROOT).reconstruire_depuis_exports(self.ROOT)
        conn = sqlite3.connect(str(cible))
        rec_tasks = {r[0] for r in conn.execute("SELECT DISTINCT task_id FROM events_ledger")}
        conn.close()
        manquants = reference - rec_tasks
        self.assertEqual(
            manquants, set(),
            f"des board_task_id de la référence manquent à la reconstruction : "
            f"{sorted(manquants)[:5]}",
        )


# La classe qui exerçait le verbe de commit du store V3 figé (T-00000438) a été
# RETIRÉE par T-00000677 avec ce verbe, sa fonction, sa sous-commande et le store
# figé lui-même. Le témoin de retrait ci-dessous atteste qu'aucun de ces noms ne
# subsiste dans les surfaces éditables — il construit ses motifs par CONCATÉNATION
# pour ne pas se matcher lui-même.


class VerbeStoreV3RetireTests(unittest.TestCase):
    """Témoin 14 (T-00000677) — le verbe de commit du store V3 figé, sa fonction et
    toutes ses surfaces ÉDITABLES sont retirés. `git grep` des DEUX formes ne rend
    plus, par ÉGALITÉ D'ENSEMBLES, que les surfaces NOMMÉES ET NON ÉDITÉES (docs
    historiques + l'état de chantier `PLAN-ETAT-DETAIL.md`).

    AMENDEMENT DATÉ 2026-09-21, écrit plutôt que contourné (leçon : un contrat du
    plan que le code ne tient plus s'AMENDE, jamais un témoin rétréci en silence) :
      * les MOTIFS sont construits par CONCATÉNATION — un banc qui grep un littéral
        le CONTIENT, donc se matcherait lui-même sans cette précaution ;
      * `runs/` est EXCLU au même titre que les quatre magasins d'état : depuis le
        commit des exports (T-00000677), `runs/**/*.jsonl` sérialise des
        observations board dont le texte de tâche CITE le verbe « par
        construction ». Ce n'est PAS le `:!.agents/` que le plan interdit (qui
        masquerait les surfaces surveillées) — c'est un magasin d'état de plus ;
      * l'ensemble attendu N'EST PAS les « sept » du plan : la réalité MESURÉE en
        porte HUIT en forme tiret (le plan omettait `T-00000643-plan.md` et
        `PLAN-ETAT-DETAIL.md`) et CINQ en forme symbole. Les deux formes n'ont pas
        le même ensemble : la forme SYMBOLE (à underscores) ne vit que dans les
        plans qui la citent."""

    ROOT = Path(__file__).resolve().parents[2]
    EXCLUSIONS = (
        ".",
        ":(exclude).agents/state/board/",
        ":(exclude).agents/state/specs/",
        ":(exclude).agents/state/memory/",
        ":(exclude).agents/state/index/",
        ":(exclude)runs/", ":(exclude)docs/interne/roadmap/",  # roadmap : titres du board recopiés en donnée
    )

    def _grep(self, motif: str) -> set:
        r = subprocess.run(
            ["git", "-C", str(self.ROOT), "grep", "-l", "-F", motif, "--",
             *self.EXCLUSIONS],
            capture_output=True, text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        return {ligne for ligne in r.stdout.splitlines() if ligne}

    def test_le_verbe_du_store_v3_et_ses_surfaces_sont_retires(self):
        tiret = "commit-event" + "-store"
        symbole = "commit_event" + "_store"
        attendu_tiret = {
            "PLAN-ETAT-DETAIL.md",
            "docs/PROMPT-refonte-packaging-cadre.md",
            "docs/interne/chantier/arcs/PLAN-T-00000585-approuve.md",
            "docs/tasks/T-00000438-plan.md",
            "docs/tasks/T-00000643-plan.md",
            "docs/tasks/T-00000650-plan.md",
            "docs/tasks/T-00000651-plan.md",
            "docs/tasks/T-00000677-plan.md",
        }
        attendu_symbole = {
            "docs/tasks/T-00000438-plan.md",
            "docs/tasks/T-00000645-plan.md",
            "docs/tasks/T-00000650-plan.md",
            "docs/tasks/T-00000651-plan.md",
            "docs/tasks/T-00000677-plan.md",
        }
        # AMENDÉ LE 2026-09-22 SUR UN BLOQUANT MESURÉ DU BINÔME (`S-00001809`), et
        # ce n'est pas un relâchement — c'est la sortie d'un PIÈGE CIRCULAIRE.
        # La première rédaction exigeait une ÉGALITÉ d'ensembles sur un `git grep`
        # de l'ARBRE VIVANT, dont certains membres sont des surfaces de PROSE
        # MUTABLE que la doctrine OBLIGE à écrire (`affirmation-guard` mord sur
        # `PLAN-ETAT.md` et sur le fichier de reprise). Résultat mesuré : écrire
        # l'état rendait CE témoin rouge, donc la porte de clôture rouge, alors
        # que ne pas l'écrire était refusé par l'autre garde. Un vert obtenu
        # `--at HEAD` ne disait rien de l'arbre.
        # CE QUI MORD DÉSORMAIS, et c'est PLUS FORT que l'égalité précédente :
        # une surface qui S'EXÉCUTE ne cite le verbe NULLE PART — zéro toléré,
        # sans liste à tenir à jour. La PROSE est BORNÉE par inclusion : elle
        # peut en citer moins, jamais un fichier de plus que l'ensemble nommé,
        # augmenté des trois surfaces d'état de chantier dont l'écriture est DUE,
        # et des fichiers de reprise de lot (`docs/interne/chantier/lots/*`),
        # DUS eux aussi : sans ce filtre, le piège circulaire décrit plus haut
        # reviendrait le jour où une reprise citerait le verbe retiré (binôme de
        # fin E-24, constat de `critic-opus` ; 0 occurrence au moment du filtre).
        etat_de_chantier = {
            "PLAN-ETAT.md",
            "PLAN-ETAT-DETAIL.md",
            "docs/interne/chantier/reprises/prompt_de_reprise_et_planification.md",
        }
        for forme, attendu in ((tiret, attendu_tiret), (symbole, attendu_symbole)):
            hits = self._grep(forme)
            self.assertEqual(
                {f for f in hits if not f.endswith(".md")}, set(),
                f"une surface qui S'EXÉCUTE cite encore le verbe ({forme})",
            )
            self.assertLessEqual(
                {f for f in hits
                 if not fnmatch.fnmatchcase(f, "docs/interne/chantier/lots/*")},
                attendu | etat_de_chantier,
                f"une surface de PROSE non nommée cite le verbe ({forme})",
            )
        # La fonction n'existe plus dans le module (nom construit par concat).
        self.assertFalse(
            hasattr(tasks, "commit_event" + "_store"),
            "la fonction du verbe subsiste dans tasks.py",
        )


class EtapePreserveeTests(unittest.TestCase):
    """UNE ÉTAPE PRÉSERVÉE SURVIT AUX TROIS SORTIES DE `blocked` (T-00000578).

    LE DÉFAUT. `block --on` SANS note PRÉSERVE l'étape en vol (T-00000103) — et
    les trois sorties de `blocked` la détruisaient ensuite. Mesuré le
    2026-09-13 : étape `security-code-review`, puis `unblock`, `start`, ou la
    libération au `done` du bloqueur — le champ ressortait VIDE dans les trois
    cas, donc la tâche reprenait sans sa place dans le pipeline.

    POURQUOI CE N'ÉTAIT PAS UN SIMPLE RETRAIT. Sur ces chemins `stage` porte
    DEUX choses selon comment on est entré dans `blocked` : une ÉTAPE préservée,
    qu'il faut garder, ou un MOTIF de blocage, qu'il faut effacer — sinon
    « on T-B » reste affiché comme étape d'une tâche qui n'est plus bloquée.
    Les distinguer exige un marqueur machine, `stage_kept`, TRANSITOIRE : posé
    par `block` quand il préserve, retiré à la sortie de `blocked`.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _id(message: str) -> str:
        """`new_task` rend un MESSAGE, pas un identifiant — d'où cette extraction
        plutôt qu'un id littéral, qui casserait au premier changement de format.
        La classe couvre l'ancien format ET `T-<ULID>` (T-00000726) : `\\d+` seul
        capturerait `T-01` d'un ULID en silence."""
        trouve = re.search(r"(T-[0-9A-HJKMNP-TV-Z]+)", message)
        assert trouve, f"aucun identifiant dans : {message!r}"
        return trouve.group(1)

    def _bloquee_avec_etape(self, etape="security-code-review"):
        a = self._id(tasks.new_task(str(self.root), "tache A", ""))
        b = self._id(tasks.new_task(str(self.root), "bloqueur B", ""))
        tasks.set_state(str(self.root), a, "running")
        tasks.stage_task(str(self.root), a, etape)
        tasks.block_task(str(self.root), a, "", b)
        return a, b

    def _champ(self, tid, cle="stage"):
        d = json.loads(
            (self.root / ".agents/state/board/TASKS.json").read_text(encoding="utf-8")
        )
        ts = d["tasks"] if isinstance(d, dict) else d
        return next(t for t in ts if t["id"] == tid).get(cle, "")

    def test_unblock_garde_l_etape_preservee(self):
        a, _ = self._bloquee_avec_etape()
        tasks.unblock_task(str(self.root), a)
        self.assertEqual(self._champ(a), "security-code-review")

    def test_start_garde_l_etape_preservee(self):
        a, _ = self._bloquee_avec_etape()
        tasks.set_state(str(self.root), a, "running")
        self.assertEqual(self._champ(a), "security-code-review")

    def test_la_liberation_au_done_garde_l_etape_preservee(self):
        a, b = self._bloquee_avec_etape()
        tasks.set_state(str(self.root), b, "running")
        tasks.set_state(str(self.root), b, "done", "fini", sans_binome="banc")
        self.assertEqual(self._champ(a), "security-code-review")

    def test_CONTROLE_NEGATIF_un_MOTIF_est_toujours_efface(self):
        """L'autre moitié, et sans elle la correction serait une régression :
        un blocage AVEC note écrit un MOTIF dans le même champ, et le laisser
        survivre afficherait « attente pilote » comme étape d'une tâche qui
        tourne — exactement ce que `T-00000577` avait réparé."""
        a = self._id(tasks.new_task(str(self.root), "tache A", ""))
        tasks.set_state(str(self.root), a, "running")
        tasks.stage_task(str(self.root), a, "security-code-review")
        tasks.block_task(str(self.root), a, "attente decision pilote")
        self.assertEqual(self._champ(a), "attente decision pilote")
        tasks.unblock_task(str(self.root), a)
        self.assertEqual(self._champ(a), "", "un motif a survécu comme étape")

    def test_CONTROLE_NEGATIF_le_lien_on_seul_est_efface(self):
        """`block --on` sur une tâche SANS étape écrit « on T-B » : c'est un
        motif, pas une étape, et il doit partir."""
        a = self._id(tasks.new_task(str(self.root), "tache A", ""))
        b = self._id(tasks.new_task(str(self.root), "bloqueur B", ""))
        tasks.block_task(str(self.root), a, "", b)
        self.assertEqual(self._champ(a), f"on {b}")
        tasks.unblock_task(str(self.root), a)
        self.assertEqual(self._champ(a), "")

    def test_le_marqueur_ne_SURVIT_pas_a_la_sortie(self):
        """TRANSITOIRE : le laisser vivre ferait qu'un blocage ULTÉRIEUR, avec
        motif celui-là, croirait devoir préserver une étape qui n'existe plus."""
        a, _ = self._bloquee_avec_etape()
        self.assertTrue(self._champ(a, "stage_kept"), "le marqueur n'a pas été posé")
        tasks.unblock_task(str(self.root), a)
        self.assertEqual(
            self._champ(a, "stage_kept"), "", "le marqueur a survécu à la sortie"
        )


class V3BridgeDegradedModeTests(unittest.TestCase):
    """MODE DÉGRADÉ VISIBLE du pont V3 (T-012, corrections du binôme A+B).

    Un store V3 écrit par un binaire PLUS RÉCENT (`user_version` > SCHEMA_VERSION)
    fait lever `create_tables` (SchemaVersionError) au drain de `replay_sync` —
    via BoardBridge → EventStore → create_tables. Le verbe DOIT quand même écrire
    le board, rendre `rc=0`, et le refus du pont est ANNONCÉ sur stderr : jamais un
    silence, jamais une panne franche."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        # `self.root` est NICHÉE sous la TemporaryDirectory (pas égale à `tmp`) pour
        # que le répertoire d'état — son SIBLING — vive AUSSI dans le tmp et parte
        # avec `tmp.cleanup()`, jamais un dossier laissé HORS du tmp à ramasser à la
        # main (binôme opus T7). `self.root` porte `.agents/`, donc reste résolue
        # comme racine de dépôt ; `base` ne porte rien, donc n'est jamais confondue.
        base = Path(self.tmp.name)
        self.root = base / "repo"
        board_dir = self.root / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        (board_dir / "TASKS.json").write_text(
            json.dumps(
                {"next_id": 1, "tasks": [], "sync_outbox": [], "sync_correlations": {}}
            ),
            encoding="utf-8",
        )
        # T-00000650 : la base du run vit sous `state_project()` (hors dépôt). On
        # force `CADRE_STATE_DIR` sur la fixture — JAMAIS `CADRE_PROJECT_ROOT`, que
        # `cadre.paths.project_root` lit AVANT `depuis` et qui écraserait la racine
        # de tous les bancs. `project_root(depuis=self.root)` résout `self.root` par
        # la branche « ancêtre portant .agents/ » (setUp l'a créé).
        self._state_dir = base / "state"
        env = mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(self._state_dir)})
        env.start()
        self.addCleanup(env.stop)
        # Pas de rmtree manuel : `_state_dir` vit DANS le tmp, `tmp.cleanup()`
        # (tearDown) le ramasse avec le reste.
        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
            self.addCleanup(sys.path.remove, str(repo))
        from agentic_v3.db.schema import SCHEMA_VERSION, DEFAULT_DB_PATH
        self.SCHEMA_VERSION = SCHEMA_VERSION
        # Un store V3 « du futur » à DEFAULT_DB_PATH(self.root) : user_version =
        # SCHEMA_VERSION + 1 (le pont V3 ouvre CE chemin, plus `.agents/state/`).
        self.v3 = DEFAULT_DB_PATH(self.root)
        self.v3.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.v3))
        # PRAGMA sans paramètre lié ; SCHEMA_VERSION+1 est un int du binaire.
        # nosemgrep: agents.security.python-sql-injection-string-format
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _v3_version(self) -> int:
        conn = sqlite3.connect(str(self.v3))
        try:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            conn.close()

    def test_un_store_V3_du_futur_est_REFUSE_le_board_ecrit_et_le_refus_ANNONCE(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), "new", "sonde"])

        self.assertEqual(0, rc, f"le verbe a échoué au lieu de dégrader: {err.getvalue()!r}")
        # Le board a bien été écrit MALGRÉ le refus du pont.
        board = json.loads((self.root / ".agents/state/board/TASKS.json").read_text())
        self.assertEqual(1, len(board["tasks"]), f"la tâche n'a pas été écrite: {board}")
        self.assertEqual("sonde", board["tasks"][0]["task"])
        # Le refus est VISIBLE sur stderr, dans la forme attendue.
        self.assertIn("pont V3 REFUSÉ", err.getvalue())
        self.assertIn("board écrit sans relecture V3", err.getvalue())
        # Le store futur n'a PAS été redescendu par la tentative de drain.
        self.assertEqual(self.SCHEMA_VERSION + 1, self._v3_version())

    def test_le_banc_ne_salit_pas_son_environnement(self) -> None:
        """NIT (binôme, opus T7) : le banc ne laisse RIEN hors de sa
        `TemporaryDirectory`. Le répertoire d'état (`_state_dir`) et la racine
        (`self.root`) vivent tous deux DANS le tmp — donc ramassés par
        `tmp.cleanup()`, jamais un sibling à `rmtree` à la main. `sys.path`, lui, est
        restauré par `addCleanup` (prouvé hors-tour, le cleanup s'exécutant après ce
        banc). MUTATION : replacer `_state_dir` sur `base.parent / (base.name +
        '_state')` -> l'`assertEqual` du parent rougit."""
        tmp_racine = Path(self.tmp.name).resolve()
        self.assertEqual(
            tmp_racine, self._state_dir.resolve().parent,
            f"_state_dir doit vivre DANS la TemporaryDirectory : {self._state_dir}",
        )
        self.assertEqual(
            tmp_racine, self.root.resolve().parent,
            f"self.root doit être nichée sous la TemporaryDirectory : {self.root}",
        )


class ReplaySyncNonFuiteTests(unittest.TestCase):
    """Témoin 19 : `replay_sync` n'écrit JAMAIS sous le dépôt — la base du run vit
    sous `state_project()` (T-00000650). Le pont (donc `create_tables`) est
    construit AVANT le drain, donc le témoin est robuste à un drain qui REFUSE
    l'intent."""

    def test_replay_sync_n_ecrit_jamais_sous_le_depot(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        racine = Path(tmp.name)
        board_dir = racine / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        after = {
            "id": "T-00000001", "state": "pending", "task": "x",
            "owner": "", "stage": "", "updated": "2026-08-07",
        }
        intent = {
            "operation_id": "op-19",
            "event_kind": "BOARD_TASK_OBSERVED",
            "affected_task_ids": ["T-00000001"],
            "before": None,
            "after": after,
            "revision_sha256": tasks.revision_sha256(None, after),
            "attempt": 0,
            "lease": None,
        }
        (board_dir / "TASKS.json").write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [],
                    "sync_outbox": [intent],
                    "sync_correlations": {
                        "op-19": {"board_task_id": "T-00000001", "tombstoned": False}
                    },
                }
            ),
            encoding="utf-8",
        )
        state_dir = racine.parent / (racine.name + "_state")
        self.addCleanup(shutil.rmtree, state_dir, ignore_errors=True)
        env = mock.patch.dict(
            os.environ,
            {"CADRE_PROJECT_ROOT": str(racine), "CADRE_STATE_DIR": str(state_dir)},
        )
        env.start()
        self.addCleanup(env.stop)

        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from agentic_v3.db import run_export
        from agentic_v3.db.schema import DEFAULT_DB_PATH

        etat = racine / ".agents" / "state"
        avant = set(etat.rglob("*"))
        with mock.patch.object(run_export, "_email_git", return_value="banc@test"):
            tasks.replay_sync(racine)
        apres = set(etat.rglob("*"))
        # ÉCART NOMMÉ AU PLAN : le drain écrit LÉGITIMEMENT la vue `TASKS.md` et le
        # verrou `TASKS.lock` du board sous `.agents/state/local/`. Ce que le témoin
        # tient est le PROPRE du lot : AUCUN store `.db` du run n'apparaît sous le
        # dépôt — la base du run est partie sous `state_project()`.
        db_apparus = {p for p in (apres - avant) if p.suffix in {".db", ".db-wal", ".db-shm"}}
        self.assertEqual(db_apparus, set(), f"un store .db du run est apparu sous .agents/state/ : {db_apparus}")
        self.assertFalse(
            (etat / "v3_event_store.db").exists(),
            "le store V3 a été (re)créé sous .agents/state/",
        )
        self.assertTrue(
            DEFAULT_DB_PATH(racine).is_file(),
            "la base du run n'existe pas sous state_project()/run/",
        )

    def test_sans_auteur_git_le_drain_vide_l_outbox_et_tient_la_propriete_du_board(self) -> None:
        """TÉMOIN DE RÉGRESSION (T-00000650, ajouté 2026-09-21) — L'EFFET, au niveau
        BOARD. Il RELIE explicitement le comportement d'export sur auteur absent à
        la propriété que le banc `tasks.test.sh` tient (« un champ changé = UNE
        ligne du store ») : ce lien manquait à la suite Python — le seul banc
        d'intégration de `replay_sync` (`..._n_ecrit_jamais_sous_le_depot`) mocke un
        email PRÉSENT, et le banc de `drain_sync_outbox` n'injecte qu'un consumer
        MOCK — et c'est par ce trou que la régression est passée en CI. Sans `git
        user.email`, un `replay_sync` doit DRAINER l'outbox jusqu'à VIDE : le miroir
        board→V3 réussit, seul l'export versionné est différé (journal conservé). Un
        outbox résiduel rouvrirait sa file à CHAQUE transition et gonflerait le diff
        du board (mesuré : 45 lignes au lieu de ≤ 4). MUTATION (code fautif
        d'origine) : `_flush_export` re-propage RunExportError -> `drain_sync_outbox`
        relâche -> l'outbox N'est PAS vidé -> l'`assertEqual` ci-dessous rougit."""
        from contextlib import redirect_stderr

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        racine = Path(tmp.name)
        board_dir = racine / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        after = {
            "id": "T-00000001", "state": "pending", "task": "x",
            "owner": "", "stage": "", "updated": "2026-08-07",
        }
        intent = {
            "operation_id": "op-sans-auteur",
            "event_kind": "BOARD_TASK_OBSERVED",
            "affected_task_ids": ["T-00000001"],
            "before": None,
            "after": after,
            "revision_sha256": tasks.revision_sha256(None, after),
            "attempt": 0,
            "lease": None,
        }
        (board_dir / "TASKS.json").write_text(
            json.dumps(
                {
                    "next_id": 2,
                    "tasks": [after],
                    "sync_outbox": [intent],
                    "sync_correlations": {
                        "op-sans-auteur": {"board_task_id": "T-00000001", "tombstoned": False}
                    },
                }
            ),
            encoding="utf-8",
        )
        state_dir = racine.parent / (racine.name + "_state")
        self.addCleanup(shutil.rmtree, state_dir, ignore_errors=True)
        env = mock.patch.dict(
            os.environ,
            {"CADRE_PROJECT_ROOT": str(racine), "CADRE_STATE_DIR": str(state_dir)},
        )
        env.start()
        self.addCleanup(env.stop)

        repo = Path(__file__).resolve().parents[2]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from agentic_v3.db import run_export

        err = io.StringIO()
        with mock.patch.object(run_export, "_email_git", return_value=""):
            with redirect_stderr(err):
                tasks.replay_sync(racine)

        outbox = tasks.load(str(racine)).get("sync_outbox", [])
        self.assertEqual(
            [], outbox,
            "sans auteur git, le drain doit VIDER l'outbox (miroir réussi, export "
            f"différé) — c'est la propriété du board. Résiduel: {outbox}",
        )
        self.assertIn(
            "journaux d'attente conserves", err.getvalue(),
            "le report d'export différé doit être annoncé, jamais avalé",
        )
        self.assertTrue(
            run_export.lister_journaux_attente(depuis=racine),
            "l'export différé conserve son journal d'attente pour un rejeu ultérieur",
        )


class PanneAnnonceeUneFoisParCommandeTests(unittest.TestCase):
    """T-00000695/696, constat du binôme : pendant une panne d'infrastructure,
    `_replay_v3()` imprimait l'annonce de CONSTRUCTION « PANNE … export BLOQUE »
    DEUX fois par commande — `main` draine avant ET après la commande, et chaque
    drain reconstruisait un `BoardBridge`, donc un `EventStore`, donc un rejeu.
    MESURÉ avant correctif, dépôt au `.git/config` cassé : `new #2` et `new #3`
    portaient chacun DEUX lignes `event_store: PANNE`.

    PAR LE VRAI CANAL : `tasks.py` en SOUS-PROCESSUS, sur un dépôt jetable dont le
    `.git/config` est réellement cassé (git rend 128 AVEC stderr — précondition
    VÉRIFIÉE, sans quoi le témoin ne mesurerait rien), état machine isolé par
    `CADRE_STATE_DIR`. MUTATION (`_replay_v3` sans `pont_commande`) : deux lignes
    au lieu d'une à la deuxième commande, et l'`assertEqual` rougit.

    ENVIRONNEMENT SANS `GIT_DIR` (critic-opus T1, T-00000695/696) : ce banc se
    lance aussi par `unittest.main()`, sans le filet de `conftest.py`. Lancé depuis
    un hook git, il héritait de `GIT_DIR` — et `git -C` n'y change rien : mesuré,
    `git init`/`commit` créaient un commit `init` DANS LE DÉPÔT HÔTE (la config
    cassée, écrite par chemin direct, échouait faute de `depot/.git`). Liste
    recopiée de `conftest.py::GIT_REDIRECTIONS`."""

    GIT_REDIRECTIONS = (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
        "GIT_PREFIX", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    )
    #: Injections `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>`, retirées par préfixe.
    GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")

    def test_une_commande_n_annonce_la_panne_qu_une_fois_et_la_nomme_sur_les_deux_chemins(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git absent : la panne mesurée est celle de `git config`")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        depot = base / "depot"
        depot.mkdir()
        etat = base / "etat"
        sans_git = {k: v for k, v in os.environ.items()
                    if k not in self.GIT_REDIRECTIONS
                    and not k.startswith(self.GIT_CONFIG_PREFIXES)}

        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(depot), *args], capture_output=True, text=True,
                env=sans_git,
            )

        git("init", "-q")
        git("-c", "user.email=a@b.c", "-c", "user.name=a",
            "commit", "-q", "--allow-empty", "-m", "init")
        with open(depot / ".git" / "config", "a", encoding="utf-8") as fh:
            fh.write("[casse\n")
        pre = git("config", "user.email")
        self.assertEqual(
            128, pre.returncode,
            f"précondition : un .git/config cassé fait rendre 128 (reçu {pre.returncode})",
        )
        self.assertTrue(pre.stderr.strip(), "précondition : la panne PARLE (stderr)")

        env = dict(sans_git)
        env.pop("CADRE_PROJECT_ROOT", None)
        env["CADRE_STATE_DIR"] = str(etat)

        def commande(titre: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-B", str(TASKS_PATH), "--root", str(depot),
                 "new", titre],
                capture_output=True, text=True, env=env, timeout=120,
            )

        premiere = commande("t1")
        self.assertEqual(0, premiere.returncode, premiere.stderr)
        deuxieme = commande("t2")
        self.assertEqual(
            0, deuxieme.returncode,
            f"la panne ne tue pas le board (S-00001859) : {deuxieme.stderr}",
        )
        lignes = deuxieme.stderr.splitlines()
        construction = [l for l in lignes if l.startswith("event_store: PANNE")]
        ecriture = [l for l in lignes if l.startswith("tasks.py: miroir V3 — PANNE")]
        self.assertEqual(
            1, len(construction),
            f"UNE annonce de construction par commande, reçu {len(construction)} :\n"
            + deuxieme.stderr,
        )
        self.assertEqual(
            1, len(ecriture),
            "le chemin d'ÉCRITURE nomme lui aussi la PANNE, une fois :\n"
            + deuxieme.stderr,
        )
        self.assertIn("BLOQUE", ecriture[0])
        self.assertNotIn(
            "DIFFERE (", deuxieme.stderr,
            "la panne ne retombe plus dans le message « DIFFERE (…) » ouvert",
        )


class SaveTrieLesClesTests(unittest.TestCase):
    """`save()` sérialise à clés triées, et deux cycles save/load sont idempotents.

    Fixture SYNTHÉTIQUE, jamais les données du dépôt : le témoin voyage tel quel
    chez un adoptant. Elle porte TOUTES les clés que `load()` pose par
    `setdefault` (`next_id`, `sync_outbox`, `sync_correlations`) — sur une
    fixture incomplète, `setdefault` APPEND la clé en fin de dict et l'égalité
    d'octets tomberait entre les deux cycles AVEC le bon code. Et UN
    enregistrement est construit avec ses clés dans un ordre NON alphabétique :
    sans `sort_keys`, `json.dumps` conserve l'ordre d'insertion, donc l'égalité
    d'octets et l'égalité d'ids resteraient vertes avec ou sans la propriété —
    seule l'assertion de tri tombe, et c'est elle qui porte le témoin.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_est_idempotent_et_trie_les_cles_sur_un_store_synthetique(self) -> None:
        # Clés de racine ET de l'enregistrement T-00000002 insérées HORS ordre.
        fixture: dict[str, Any] = {
            "tasks": [
                {
                    "id": "T-00000001",
                    "state": "done",
                    "task": "a",
                    "owner": "dev-mono",
                    "stage": "",
                    "updated": "2026-01-01",
                },
                {
                    "task": "b",
                    "id": "T-00000002",
                    "updated": "2026-01-02",
                    "state": "pending",
                    "stage": "",
                    "owner": "",
                },
            ],
            "sync_correlations": {},
            "next_id": 3,
            "sync_outbox": [],
        }
        store = tasks.store_path(self.root)

        tasks.save(self.root, fixture)
        premier = store.read_text(encoding="utf-8")
        relu = tasks.load(self.root)
        tasks.save(self.root, relu)
        second = store.read_text(encoding="utf-8")

        self.assertEqual(premier, second, "deux cycles save()/load() divergent en octets")
        depuis_octets = json.loads(second)
        # LISTE ordonnée, jamais un ensemble : l'ordre d'une liste porte du sens
        # (`sync_outbox[0]` est la tête d'une file FIFO), et un `save()` qui la
        # retrierait resterait vert sur un ensemble d'ids.
        self.assertEqual(
            ["T-00000001", "T-00000002"],
            [t["id"] for t in depuis_octets["tasks"]],
            "sort_keys ne doit jamais retrier une liste",
        )
        # Le tri se lit depuis les OCTETS du fichier, jamais depuis le dict que
        # `load()` rend — c'est la seule assertion qui tombe sans `sort_keys`.
        self.assertEqual(list(depuis_octets), sorted(depuis_octets))
        rec = next(t for t in depuis_octets["tasks"] if t["id"] == "T-00000002")
        self.assertEqual(list(rec), sorted(rec))


class SessionBoardTests(unittest.TestCase):
    """`list --session` (T-00000834): the SessionStart view bounds the pending
    rows, never running/blocked, announces the cut, and leaves the bare list's
    byte-for-byte contract alone."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        self.store.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def board(self, pending: int, updated: str | None = None) -> None:
        today = updated or date.today().isoformat()
        rows = [
            {"id": "T-00000001", "state": "running", "task": "en cours", "owner": "dev-mono", "stage": "", "updated": today},
            {"id": "T-00000002", "state": "blocked", "task": "attend", "owner": "planner", "stage": "", "updated": today},
            {"id": "T-00000003", "state": "done", "task": "close", "owner": "dev-mono", "stage": "", "updated": today},
        ]
        rows += [
            {"id": f"T-{n:08d}", "state": "pending", "task": f"p{n}", "owner": "dev-mono", "stage": "", "updated": today}
            for n in range(10, 10 + pending)
        ]
        self.store.write_text(json.dumps({"next_id": 10 + pending, "tasks": rows}), encoding="utf-8")

    def ids(self, text: str) -> list[str]:
        # Old AND `T-<ULID>` ids (T-00000726), padded to the column width.
        return re.findall(r"\| (T-[0-9A-HJKMNP-TV-Z]+) *\|", text)

    def test_pending_bounded_to_the_newest_and_the_cut_is_announced(self) -> None:
        self.board(pending=tasks.SESSION_MAX_PENDING + 5)
        out = tasks.render_session_board(str(self.root))
        shown = self.ids(out)
        newest = [f"T-{n:08d}" for n in range(10 + tasks.SESSION_MAX_PENDING + 4, 14, -1)]
        self.assertEqual(shown[:2], ["T-00000001", "T-00000002"])
        self.assertEqual(shown[2:-1], newest)
        self.assertEqual(shown[-1], "T-00000003")
        self.assertIn("(+5 less recently updated pending not shown", out.splitlines()[-1])
        self.assertIn("tasks.py list --state pending", out)

    def test_a_pending_touched_recently_beats_a_higher_id(self) -> None:
        # T-00000805 stopped mid-way TODAY must not sink under backlog filed after it.
        self.board(pending=tasks.SESSION_MAX_PENDING + 3, updated="2026-01-01")
        data = json.loads(self.store.read_text(encoding="utf-8"))
        for row in data["tasks"]:
            if row["id"] == "T-00000010":
                row["updated"] = date.today().isoformat()
        self.store.write_text(json.dumps(data), encoding="utf-8")
        shown = self.ids(tasks.render_session_board(str(self.root)))
        self.assertIn("T-00000010", shown)
        self.assertNotIn("T-00000011", shown)

    def test_under_the_cap_it_is_the_bare_list_exactly(self) -> None:
        self.board(pending=3)
        self.assertEqual(tasks.render_session_board(str(self.root)), tasks.render_list(str(self.root)))

    def test_running_and_blocked_are_never_cut(self) -> None:
        self.board(pending=4)
        out = tasks.render_session_board(str(self.root), max_pending=0)
        self.assertEqual(self.ids(out), ["T-00000001", "T-00000002", "T-00000003"])
        self.assertIn("(+4 less recently updated pending not shown", out)

    def test_stale_running_alert_rides_the_session_view(self) -> None:
        stale = (date.today() - timedelta(days=tasks.STALE_RUNNING_DAYS + 1)).isoformat()
        self.board(pending=1, updated=stale)
        lines = tasks.render_session_board(str(self.root)).splitlines()
        self.assertEqual("## TASK BOARD", lines[0])
        self.assertIn("RUNNING STALE", lines[1])

    def test_empty_board_says_so(self) -> None:
        self.store.write_text(json.dumps({"next_id": 1, "tasks": []}), encoding="utf-8")
        self.assertIn("empty", tasks.render_session_board(str(self.root)))

    def test_cli_session_prints_the_view_and_refuses_any_other_flag(self) -> None:
        self.board(pending=tasks.SESSION_MAX_PENDING + 1)
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            self.assertEqual(tasks.main(["--root", str(self.root), "list", "--session"]), 0)
        self.assertIn("(+1 less recently updated pending not shown", buf.getvalue())
        for extra in (["--json"], ["--state", "pending"], ["--group"], ["--task", "T-1"]):
            with self.subTest(extra=extra), mock.patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    tasks.main(["--root", str(self.root), "list", "--session", *extra])
                self.assertEqual(caught.exception.code, 2)


class BinomePurgeVerbTests(unittest.TestCase):
    """`tasks.py binome-purge T-NNN` (T-00000842).

    The morning path of `/night` must drop a task's DIRECT closing-pair traces
    before its pair runs — `binome_preuve` never expires them — and the `rm` it
    prescribed is refused by `safe-bash.sh`. The verb purges THIS task's traces
    only, says what it removed (or that there was none), exits 0, and refuses an
    unknown id with the board's usual `unknown task id` at rc 2. It is not a board
    mutator: the store is left byte-identical.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        (self.root / ".agents" / "state" / "board").mkdir(parents=True)
        self.traces = self.root / tasks.BINOME_TRACES
        self.traces.mkdir(parents=True)
        tasks.new_task(str(self.root), "livrée la nuit", "dev-mono")
        tasks.new_task(str(self.root), "voisine", "dev-mono")
        store = json.loads(
            (self.root / ".agents" / "state" / "board" / "TASKS.json").read_text(encoding="utf-8")
        )
        self.a, self.b = (t["id"] for t in store["tasks"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def trace(self, tid: str, critique: str) -> Path:
        path = self.traces / f"{tid}.{critique}.json"
        path.write_text(json.dumps({"at": "2026-09-29T02:00:00Z"}), encoding="utf-8")
        return path

    def run_verb(self, tid: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), "binome-purge", tid])
        return rc, out.getvalue(), err.getvalue()

    def test_purges_present_traces_and_names_them(self) -> None:
        opus, fable = self.trace(self.a, "critic-opus"), self.trace(self.a, "critic-fable")
        rc, out, _err = self.run_verb(self.a)
        self.assertEqual(0, rc)
        self.assertFalse(opus.exists() or fable.exists())
        self.assertIn("purged", out)
        self.assertIn("critic-opus", out)
        self.assertIn("critic-fable", out)
        self.assertEqual({}, tasks.binome_trace(str(self.root), self.a))

    def test_no_trace_is_said_and_still_rc_0(self) -> None:
        rc, out, _err = self.run_verb(self.a)
        self.assertEqual(0, rc)
        self.assertIn("aucune trace", out)

    def test_unknown_id_is_refused_rc_2_and_purges_nothing(self) -> None:
        kept = self.trace(self.a, "critic-opus")
        rc, _out, err = self.run_verb("T-99999999")
        self.assertEqual(2, rc)
        self.assertIn("unknown task id", err)
        self.assertTrue(kept.exists())

    def test_other_tasks_traces_are_untouched_and_the_board_is_not_written(self) -> None:
        self.trace(self.a, "critic-opus")
        voisine = [self.trace(self.b, c) for c in ("critic-opus", "critic-fable")]
        store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        before = store.read_bytes()
        rc, _out, _err = self.run_verb(self.a)
        self.assertEqual(0, rc)
        self.assertTrue(all(p.exists() for p in voisine))
        self.assertEqual(2, len(tasks.binome_trace(str(self.root), self.b)))
        self.assertEqual(before, store.read_bytes())

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "read-only directory is not enforced for root or on Windows")
    def test_an_undeletable_trace_is_a_refusal_never_aucune_trace(self) -> None:
        # Revue critic-opus T-00000842, mesuré : `chmod 555` sur le dossier des
        # traces rendait « aucune trace », rc 0, et `done` passait ensuite sans
        # le binôme du matin. Une trace qu'on n'a pas pu retirer est un REFUS.
        opus = self.trace(self.a, "critic-opus")
        os.chmod(self.traces, 0o555)
        try:
            rc, out, err = self.run_verb(self.a)
        finally:
            os.chmod(self.traces, 0o755)
        self.assertEqual(2, rc)
        self.assertIn("NON effacées", err)
        self.assertNotIn("aucune trace", out)
        self.assertTrue(opus.exists())

    def test_purging_a_running_slot_says_its_subtasks_lose_the_borrow(self) -> None:
        tasks.main(["--root", str(self.root), "start", self.a])
        self.trace(self.a, "critic-opus")
        rc, _out, err = self.run_verb(self.a)
        self.assertEqual(0, rc)
        self.assertIn("lose the borrowed proof", err)


# Fixed ULID bodies (26 Crockford symbols), in TIME order: U_ALLDIG < U_LETTER <
# U_DIGIT < U_DONE1 < U_DONE2. U_LETTER ends in a LETTER (`numeric_id` raises on
# it); U_DIGIT ends in `2` (`numeric_id` would read 2); U_ALLDIG is all digits.
U_ALLDIG = "01234567890123456789012345"
U_LETTER = "01M3250V003HCPQKTZ8ENYF4VM"
U_DIGIT = "01M3253WN0W4D0K2S3759WV6M2"
U_DONE1 = "01M40BDBH7EWBZDZFE0PT5MWT0"
U_DONE2 = "01M40BDBH7EWBZDZFE0PT5MWT1"


class LectureUlidTests(unittest.TestCase):
    """A MIXED board (legacy ids + ``T-<ULID>``) READS like a legacy one
    (T-00000726, slice T-00001038, steps 2 (i)-(v) and (iii-e)).

    These boards are INPUT fixtures written by hand — what a reader meets after
    the C2 switch-over or a merge. Witness (iv) left with the numeric allocator
    at C2; (i)-(iii) and (iii-e) are RED on the
    code before this slice (`numeric_id` raises on ``T-<U_LETTER>`` and reads 2
    in ``T-<U_DIGIT>``); (v) is green there and stays so — it pins the order of
    the ULID ``continue`` in ``load``, BELOW the exact-id duplicate check
    (mutant M36)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.store = self.root / ".agents" / "state" / "board" / "TASKS.json"
        self.store.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def row(tid: str, state: str = "pending", updated: str = "2026-10-01", **extra: Any) -> dict[str, Any]:
        task = {"id": tid, "state": state, "task": f"tache {tid[-4:]}", "owner": "dev-multi",
                "stage": "", "updated": updated}
        task.update(extra)
        return task

    def write(self, rows: list[dict[str, Any]], **root_keys: Any) -> None:
        self.store.write_text(json.dumps({"tasks": rows, **root_keys}), encoding="utf-8")

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = tasks.main(["--root", str(self.root), *argv])
        return rc, out.getvalue(), err.getvalue()

    @staticmethod
    def id_cells(text: str) -> list[str]:
        """The id column of every task row of a rendered table, as SHOWN. Until
        C2 widens ``WIDTHS["id"]`` a ULID is shown cut (``T-01M3250…``), so the
        expectation goes through ``shown`` rather than a regex on full ids."""
        rows = [line for line in text.splitlines() if line.startswith("| T-")]
        return [row.split("|")[1].strip() for row in rows]

    @staticmethod
    def shown(ids: list[str]) -> list[str]:
        return [tasks.fit(tid, tasks.WIDTHS["id"]).strip() for tid in ids]

    def mixed_board(self) -> None:
        """Every state holds legacy ids AND ULIDs, written in a SHUFFLED order."""
        self.write([
            self.row("T-00000003", "done"),
            self.row(f"T-{U_LETTER}"),
            self.row("T-00000001", "blocked"),
            self.row(f"T-{U_DONE1}", "done"),
            self.row("T-00000010"),
            self.row("T-00000004", "running"),
            self.row(f"T-{U_ALLDIG}", "blocked"),
            self.row("T-00000009", "done"),
            self.row(f"T-{U_DIGIT}"),
            self.row("T-00000007", "done"),
            self.row("T-00000002"),
            self.row(f"T-{U_DONE2}", "done"),
        ])

    # ULIDs first, newest first, then legacy ids from the highest down — in EACH state.
    EXPECTED = [
        "T-00000004",
        f"T-{U_ALLDIG}", "T-00000001",
        f"T-{U_DIGIT}", f"T-{U_LETTER}", "T-00000010", "T-00000002",
        f"T-{U_DONE2}", f"T-{U_DONE1}", "T-00000009", "T-00000007", "T-00000003",
    ]

    def test_i_a_ULID_never_collides_numerically_with_a_legacy_id(self) -> None:
        self.write([self.row("T-00000002"), self.row(f"T-{U_DIGIT}")])
        self.assertEqual(["T-00000002", f"T-{U_DIGIT}"], [t["id"] for t in tasks.load(self.root)["tasks"]])
        self.write([self.row(f"T-{U_LETTER}")])
        self.assertEqual([f"T-{U_LETTER}"], [t["id"] for t in tasks.load(self.root)["tasks"]])
        # Control: two LEGACY ids of one value still collide.
        self.write([self.row("T-002"), self.row("T-00000002")])
        with self.assertRaisesRegex(tasks.BoardError, "numeric id collision"):
            tasks.load(self.root)

    def test_ii_a_short_form_resolves_to_a_legacy_id_only(self) -> None:
        self.write([self.row(f"T-{U_LETTER}"), self.row(f"T-{U_DIGIT}"), self.row("T-00000002")])
        data = tasks.load(self.root)
        self.assertEqual("T-00000002", tasks.resolve_id(data, "2"))
        self.assertEqual("T-00000002", tasks.resolve_id(data, "T-2"))
        self.assertEqual(f"T-{U_DIGIT}", tasks.resolve_id(data, f"T-{U_DIGIT}"))
        # Without a legacy 2, `2` NEVER lands on the ULID whose body ends in 2.
        self.write([self.row(f"T-{U_DIGIT}")])
        with self.assertRaisesRegex(tasks.BoardError, "unknown task id: 2"):
            tasks.resolve_id(tasks.load(self.root), "2")

    def test_iii_sorted_tasks_puts_ULIDs_first_newest_first_in_each_state(self) -> None:
        self.mixed_board()
        data = tasks.load(self.root)
        self.assertEqual(self.EXPECTED, [t["id"] for t in tasks.sorted_tasks(data["tasks"], cap_done=False)])
        capped = [t["id"] for t in tasks.sorted_tasks(data["tasks"])]
        self.assertEqual(self.EXPECTED[: 7 + tasks.MAX_DONE_SHOWN], capped)

    def test_iii_the_session_board_reads_the_same_order_and_cuts_by_sort_key(self) -> None:
        self.mixed_board()
        self.assertEqual(
            self.shown(self.EXPECTED[: 7 + tasks.MAX_DONE_SHOWN]),
            self.id_cells(tasks.render_session_board(str(self.root))),
        )
        # Same `updated` everywhere: the cut keeps the two NEWEST pending by sort_key.
        kept = self.id_cells(tasks.render_session_board(str(self.root), max_pending=2))
        self.assertEqual(
            self.shown(["T-00000004", f"T-{U_ALLDIG}", "T-00000001", f"T-{U_DIGIT}", f"T-{U_LETTER}"]),
            kept[:5],
        )

    def test_iii_e_list_epic_on_a_mixed_board_keeps_the_same_order(self) -> None:
        self.write(
            [
                self.row("T-00000002", epic="E-01"),
                self.row("T-00000010"),
                self.row(f"T-{U_DIGIT}", "done", epic="E-01"),
                self.row(f"T-{U_LETTER}", epic="E-01"),
            ],
            epics=[{"id": "E-01", "titre": "epic du banc"}],
        )
        expected = [f"T-{U_LETTER}", "T-00000002", f"T-{U_DIGIT}"]
        rc, out, err = self.cli("list", "--epic", "E-01", "--json")
        self.assertEqual(0, rc, err)
        self.assertEqual(expected, [t["id"] for t in json.loads(out)])
        rc, out, err = self.cli("list", "--epic", "E-01")
        self.assertEqual(0, rc, err)
        self.assertEqual(self.shown(expected), self.id_cells(out))

    def test_v_a_ULID_listed_twice_is_a_duplicate_never_skipped(self) -> None:
        self.write([self.row(f"T-{U_LETTER}"), self.row(f"T-{U_LETTER}", "done")])
        with self.assertRaisesRegex(tasks.BoardError, f"duplicate task id T-{U_LETTER}"):
            tasks.load(self.root)
        rc, _out, err = self.cli("list")
        self.assertEqual(2, rc)
        self.assertIn("duplicate task id", err)


class FocusCloneLectureTests(unittest.TestCase):
    """LES LECTEURS DU FOCUS ET DE LA PORTÉE (T-01M5F7286N1EYGXAXA5244X86B, lot A), en unité : la
    racine principale résolue SANS git (``racine_principale``) et la FORME des deux JSON locaux. Les
    témoins de bout en bout (start, focus, review-scope, worktree, remède) vivent dans
    ``test_tasks_sessions.py``, avec leurs mutants : ce fichier est à son plafond de longueur."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self.tmp.name)
        (self.base / "principal" / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (self.base / "wt").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def pointer(self, gitdir: str, commondir: str | None = "../..") -> Path:
        """Un ``.git`` FICHIER de worktree vers ``gitdir`` ; ``commondir`` absent = sous-module."""
        (self.base / "wt" / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        cible = (self.base / "wt" / gitdir) if not Path(gitdir).is_absolute() else Path(gitdir)
        (cible / "gitdir").write_text(str(self.base / "wt" / ".git") + "\n", encoding="utf-8")  # lien retour
        if commondir is not None:
            (cible / "commondir").write_text(commondir + "\n", encoding="utf-8")
        return self.base / "wt"

    def test_main_root_is_read_through_commondir_absolute_or_relative(self) -> None:
        principal = (self.base / "principal").resolve()
        gitdir = self.base / "principal" / ".git" / "worktrees" / "wt"
        self.assertEqual(principal, tasks.racine_principale(self.pointer(str(gitdir))).resolve())
        self.assertEqual(principal, tasks.racine_principale(self.pointer("../principal/.git/worktrees/wt")).resolve())
        self.assertEqual(principal / ".agents" / "state" / "local" / "focus.json",
                         tasks.chemin_focus(self.base / "wt").resolve())

    def test_no_worktree_pointer_keeps_the_root_itself(self) -> None:
        """Hors Git, un ``.git`` DOSSIER, un pointeur sans ``commondir`` (sous-module) ou illisible :
        la racine passée, jamais une autre — une racine jetable ne vise jamais le vrai dépôt."""
        wt = self.base / "wt"
        self.assertEqual(Path(tasks.normalize_root(wt)), tasks.racine_principale(wt))
        self.assertEqual(Path(tasks.normalize_root(self.base / "principal")), tasks.racine_principale(self.base / "principal"))
        gitdir = str(self.base / "principal" / ".git" / "worktrees" / "wt")
        self.assertEqual(Path(tasks.normalize_root(wt)), tasks.racine_principale(self.pointer(gitdir, None)))
        (wt / ".git").write_text("pas un pointeur\n", encoding="utf-8")
        self.assertEqual(Path(tasks.normalize_root(wt)), tasks.racine_principale(wt))

    def test_local_json_absent_reads_none_and_a_bad_shape_is_refused(self) -> None:
        racine = self.base / "wt"
        self.assertIsNone(tasks.lire_focus(racine))
        self.assertIsNone(tasks.lire_portee(racine))
        self.assertIsNone(tasks.consommer_portee(racine, "T-1"))
        local = racine / ".agents" / "state" / "local"
        local.mkdir(parents=True, exist_ok=True)  # le verrou de la portée l'a déjà créé
        for nom, contenu in (("focus.json", '{"task_id": 7, "updated_at": "x"}'),
                             ("review-scope.json", '{"focus": "T-1", "members": "T-1", "consumed": [],'
                                                   ' "declared_at": "x"}'),
                             ("review-scope.json", '{"focus": "T-1", "members": [1], "consumed": [],'
                                                   ' "declared_at": "x"}'),
                             ("focus.json", "{pas du json")):
            with self.subTest(nom=nom, contenu=contenu):
                (local / nom).write_text(contenu, encoding="utf-8")
                lecteur = tasks.lire_focus if nom == "focus.json" else tasks.lire_portee
                with self.assertRaisesRegex(tasks.BoardError, f"{re.escape(nom)} hors forme"):
                    lecteur(racine)

    def test_consumption_is_said_once_and_ignores_a_non_member(self) -> None:
        racine = self.base / "wt"
        tasks.ecrire_json_local(tasks.chemin_portee(racine), {"focus": "T-1", "members": ["T-1", "T-2"],
                                                              "consumed": [], "declared_at": "x"})
        self.assertIsNone(tasks.consommer_portee(racine, "T-9"))
        self.assertIn("T-2 consommé (1/2, focus T-1)", tasks.consommer_portee(racine, "T-2") or "")
        self.assertIsNone(tasks.consommer_portee(racine, "T-2"))
        self.assertEqual(["T-2"], tasks.lire_portee(racine)["consumed"])
        self.assertEqual([], [p.name for p in tasks.chemin_portee(racine).parent.iterdir() if p.suffix == ".tmp"])

    def test_remedy_names_focus_then_scope_and_goes_silent_with_a_focus(self) -> None:
        """C39 en unité : sans focus.json le remède nomme `focus` PUIS `review-scope` ; une tâche non
        running nomme `<T running>` et s'inscrit elle-même dans la liste ; focus posé, silence."""
        racine = self.base / "wt"
        texte = tasks.remede_focus_absent(str(racine), {"id": "T-2", "state": "pending"})
        self.assertIn("`tasks.py focus <T running>`, puis `tasks.py review-scope <T running> T-2", texte)
        self.assertLess(texte.index("focus <T"), texte.index("review-scope"))
        tasks.poser_focus(racine, "T-1")
        self.assertEqual("", tasks.remede_focus_absent(str(racine), {"id": "T-2", "state": "running"}))


if __name__ == "__main__":
    unittest.main()
