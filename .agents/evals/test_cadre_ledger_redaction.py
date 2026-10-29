#!/usr/bin/env python3
"""BANC DE RÉDACTION DES SECRETS — `check_secret_redaction` (`T-00000641`).

Étape D (point 7) de T-012, bloquant B-C4 du plan LOT-2 phase 2, invariant
« aucun secret au ledger » (spec §3). Un secret reconnu est rédigé À
L'ÉCRITURE — il n'entre pas dans le magasin — plutôt que retiré après coup (un
magasin append-only ne se nettoie pas).

CE BANC EST L'IMPLÉMENTATION DÉCLARÉE de `check_secret_redaction` (statut `actif`).
Il n'appelle PAS gitleaks : la forme des faux secrets a été mesurée UNE FOIS par
P-H1 (`gitleaks` 8.30.1 les détecte : `aws-access-token`, `github-pat`,
`private-key`) puis FIGÉE ici. Il n'opère que sur un magasin en FICHIER
TEMPORAIRE RÉEL et sur le paquet `cadre.ledger`, qui voyage — aucun `skip`, ni sur
ce poste ni sur un arbre adoptant (il ne lit ni spec, ni plan, ni état), pour ne
pas « tourner mais sauter » (faute que `test_checks_manifest.py` refuse).

COUVERTURE ÉLARGIE PAR `T-00000641` : ce banc couvre désormais le magasin de
leçons ET le store du RUN — les octets du `.db` V3 (`events_ledger`, projections
`code_diff`/`current_assignee`, `board_sync_outbox.last_error`) après checkpoint
WAL. La BORNE « borné au ledger » n'est PLUS vraie. Restent NON couverts :
`board_sync_outbox.payload_json` (laissé EN CLAIR, arbitrage étape 4) et la clé
SECRÈTE AWS 40 car. (voir `redaction.py`).

LA PREUVE EST LUE SUR LE FICHIER, PAS PAR L'API. On relit les OCTETS BRUTS du
`.db` (plus le `-wal` après checkpoint) et on exige l'ABSENCE de la chaîne
secrète : la preuve est que le secret n'est nulle part dans le magasin, pas
qu'une requête ne le rend pas. La PRÉSENCE du marqueur prouve la NON-VACUITÉ — la
leçon est bien écrite, donc l'absence du secret n'est pas vraie par vide.

LES FAUX SECRETS SONT CONSTRUITS PAR CONCATÉNATION pour que le `gitleaks` du dépôt
(pre-commit / SAST) ne bloque pas CE fichier : à l'exécution ils ont la FORME
exacte d'un secret (concaténation reconstituée), mais dans le TEXTE du source les
jetons sont coupés (`"AKIA" + "…"`) et gitleaks n'y voit rien. Vérifié par P-H1.
"""

from __future__ import annotations

import importlib.util
import json
import random
import re
import string
import sys
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

_RESOLVEUR_SPEC = importlib.util.spec_from_file_location(
    "_redaction_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
_RESOLVEUR = sys.modules[_RESOLVEUR_SPEC.name] = importlib.util.module_from_spec(_RESOLVEUR_SPEC)
_RESOLVEUR_SPEC.loader.exec_module(_RESOLVEUR)
# Le paquet `cadre` de l'arbre (`.agents/vendor/cadre`, sinon `src/cadre`), par chemin (S-01M5RJX5SB C9).
_RESOLVEUR.charger_paquet(ROOT, "cadre")
_RESOLVEUR.charger_paquet(ROOT, "agentic_v3")

from cadre.ledger import lessons, redaction, schema, store, version  # noqa: E402

# T-00000641 : le store du RUN (V3) est désormais couvert par ce banc — il charge
# `redaction.py` PAR CHEMIN (objet module DISTINCT de `cadre.ledger.redaction`).
from agentic_v3.db import event_store as v3store  # noqa: E402
from agentic_v3.db import run_export as v3run  # noqa: E402
from agentic_v3.db.event_store import EventStore  # noqa: E402
from agentic_v3.db.schema import get_db_connection  # noqa: E402
from agentic_v3.models.events import EventType  # noqa: E402
import pytest  # noqa: E402


def test_vendor_prefere_quand_les_deux_emplacements_existent():
    """Le store V3 exercé vient de la résolution canonique, y compris en dual."""
    paquet = v3run._vendor_paths().dossier_paquet(ROOT, "agentic_v3")
    assert paquet is not None, "paquet V3 absent : témoin non armé"
    assert Path(v3run.__file__).resolve().parents[1] == paquet


@pytest.fixture(autouse=True)
def _isolation_export_run(tmp_path, monkeypatch, request):
    """T-00000650 : le store du RUN (V3) écrit son export sous une racine de TEST
    (`CADRE_PROJECT_ROOT`) et sa base sous `CADRE_STATE_DIR`, auteur FIXÉ — aucun
    secret ne peut fuir sous le dépôt réel, et la jambe conteneur (root, sans
    `git config user.email`) ne refuse pas l'export. La greffe passe par la PORTE
    UNIQUE (L-00000500) pour rester franchissable — sinon elle éteint le témoin
    d'aval du vrai git."""
    from conftest import greffe_email_git_franchissable

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CADRE_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("CADRE_STATE_DIR", str(tmp_path / "state"))
    greffe_email_git_franchissable(monkeypatch, request, v3run)


@pytest.mark.email_git_reel
def test_la_greffe_email_git_est_franchissable_ici():
    """TÉMOIN (L-00000500) — sous le marqueur `email_git_reel`, la fixture autouse
    `_isolation_export_run` SAUTE sa greffe et le VRAI `_email_git` reste en place
    (def -> `__name__ == "_email_git"`, la greffe étant un `<lambda>`). MUTATION
    (greffe non franchissable) : l'objet devient le `<lambda>` et rougit."""
    assert v3run._email_git.__name__ == "_email_git", (
        "greffe NON franchie : la porte unique n'a pas sauté sous email_git_reel"
    )


T = dict(tenant_id="t", project_id="p")

# FAUX SECRETS de forme réaliste, NON VALIDES, mesurés par P-H1 (gitleaks 8.30.1,
# 2026-09-17). Construits par CONCATÉNATION : la valeur À L'EXÉCUTION est un jeton
# contigu que `redaction` reconnaît, mais le TEXTE du source est coupé pour ne pas
# déclencher le gitleaks du dépôt.
FAUX_AWS = "AKIA" + "Z3XYQ7WNRT4KLMND"                    # aws-access-token
FAUX_GHP = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # github-pat
FAUX_PEM = (
    "-----BEGIN PRIVATE " + "KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDF" + "AKEfakefake\n"
    "fakefakefakefakefakefakefakefakefakefakefakefakefake" + "fake0000\n"
    "-----END PRIVATE " + "KEY-----"
)
FAUX_SECRETS = (FAUX_AWS, FAUX_GHP, FAUX_PEM)


class _StoreReelMixin(unittest.TestCase):
    def _store_reel(self):
        """Un store sur FICHIER RÉEL, schéma garanti (jamais `:memory:`, perdu
        avant lecture des octets). Nettoyage enregistré. Rend `(chemin, conn)` —
        le chemin est indispensable pour relire le fichier."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "lecons.db"
        conn = store.connect(chemin)
        self.addCleanup(conn.close)
        version.garantir_schema(conn)
        return chemin, conn

    def _octets_du_store(self, chemin: Path, conn) -> bytes:
        """Les octets BRUTS du magasin : le `.db` PLUS son `-wal` après checkpoint.
        Le checkpoint (`TRUNCATE`) rapatrie le WAL dans le `.db` s'il existe ; en
        mode journal `delete` (le défaut ici) c'est un no-op inoffensif. On lit
        ENSUITE les deux fichiers pour ne dépendre d'aucun mode de journalisation."""
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
        octets = chemin.read_bytes()
        wal = chemin.with_name(chemin.name + "-wal")
        if wal.exists():
            octets += wal.read_bytes()
        return octets

    def _assert_secret_absent(self, octets: bytes, secret: str) -> None:
        """LA FONCTION D'ASSERTION, isolée pour être le point du contrôle négatif :
        rédaction neutralisée, c'est ELLE qui doit rougir."""
        self.assertNotIn(
            secret.encode("utf-8"), octets,
            "un secret brut est présent dans les octets du magasin : la rédaction "
            "à l'écriture n'a pas mordu",
        )

    def _store_v3(self):
        """Un store du RUN (V3) sur FICHIER RÉEL — schéma créé par `EventStore`.
        Rend `(chemin, store)` ; le chemin sert à relire les octets."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        chemin = Path(tmp.name) / "v3.db"
        return chemin, EventStore(db_path=chemin)

    def _octets_du_store_v3(self, chemin: Path) -> bytes:
        """Octets BRUTS du `.db` V3 PLUS son `-wal` (schema.py:44 = WAL) après un
        `wal_checkpoint(TRUNCATE)` — la preuve est lue sur le FICHIER."""
        conn = get_db_connection(chemin)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
        octets = chemin.read_bytes()
        for suffixe in ("-wal", "-shm"):
            annexe = chemin.with_name(chemin.name + suffixe)
            if annexe.exists():
                octets += annexe.read_bytes()
        return octets


class RedactionAuLedgerTests(_StoreReelMixin):
    def test_un_faux_secret_injecte_est_absent_du_ledger(self):
        """LE TÉMOIN. Une leçon dont le `contenu` ET la `forme_generalisee`
        portent les trois faux secrets est écrite, puis relue SUR LE FICHIER :
        aucune chaîne secrète ne s'y trouve, et le marqueur y est (population non
        vide, donc l'absence n'est pas triviale)."""
        chemin, conn = self._store_reel()
        contenu = (
            f"contexte projet : la clé AWS {FAUX_AWS}, le jeton GitHub {FAUX_GHP}, "
            f"et une clé privée :\n{FAUX_PEM}"
        )
        forme = (
            f"forme générique — jeton {FAUX_GHP}, clé {FAUX_AWS}, bloc PEM :\n"
            f"{FAUX_PEM}"
        )
        loc, gen = lessons.ecrire_lecon(
            conn, contenu=contenu, cle_sujet="secrets", forme_generalisee=forme, **T)

        # NON-VACUITÉ : les DEUX enregistrements (locale + généralisée) existent.
        n = conn.execute("SELECT COUNT(*) FROM " + schema.TABLE).fetchone()[0]
        self.assertEqual(n, 2, "les deux enregistrements ne sont pas écrits")
        self.assertIsNotNone(gen, "la forme généralisée n'a pas été écrite")

        octets = self._octets_du_store(chemin, conn)

        # (1) ABSENCE de chaque forme secrète des octets bruts du magasin.
        for secret in FAUX_SECRETS:
            self._assert_secret_absent(octets, secret)

        # (2) PRÉSENCE du marqueur — la leçon EST peuplée, l'absence n'est pas
        # vraie par vacuité. `[SECRET R` est le préfixe ASCII du marqueur.
        self.assertIn(
            b"[SECRET R", octets,
            "aucun marqueur de rédaction dans le magasin : la leçon est-elle vide, "
            "ou la rédaction n'a-t-elle rien écrit ?",
        )

        # (3) L'API rend du texte RÉDIGÉ, jamais le secret brut, et le marqueur
        # NOMME la famille retirée.
        rloc = lessons.lire_lecon(conn, loc)
        self.assertNotIn(FAUX_AWS, rloc["contenu"])
        self.assertNotIn(FAUX_GHP, rloc["contenu"])
        self.assertIn("[SECRET RÉDIGÉ:aws_access_key]", rloc["contenu"])
        self.assertIn("[SECRET RÉDIGÉ:github_token]", rloc["contenu"])
        self.assertIn("[SECRET RÉDIGÉ:private_key]", rloc["contenu"])
        rgen = lessons.lire_lecon(conn, gen)
        for secret in FAUX_SECRETS:
            self.assertNotIn(secret, rgen["contenu"])

    def test_hash_contenu_porte_sur_le_texte_REDIGE(self):
        """Le hash stocké est l'empreinte du texte RÉDIGÉ, pas du brut : sinon le
        magasin porterait une valeur DÉRIVÉE du secret et l'invariant
        `hash_contenu == sha256(contenu stocké)` casserait."""
        import hashlib
        chemin, conn = self._store_reel()
        loc, _ = lessons.ecrire_lecon(
            conn, contenu=f"clé {FAUX_AWS}", cle_sujet="h", **T)
        row = lessons.lire_lecon(conn, loc)
        attendu = hashlib.sha256(row["contenu"].encode("utf-8")).hexdigest()
        self.assertEqual(row["hash_contenu"], attendu,
                         "le hash ne correspond pas au contenu RÉDIGÉ stocké")
        self.assertNotIn(FAUX_AWS, row["contenu"])

    def test_le_temoin_PEUT_echouer_quand_la_redaction_est_neutralisee(self):
        """CONTRÔLE NÉGATIF. Rédaction neutralisée (monkeypatch : `rediger` rend
        son entrée telle quelle), le secret ENTRE dans le magasin — et la fonction
        d'assertion `_assert_secret_absent` ROUGIT. Sans ce contrôle, le témoin
        passerait sur une implémentation qui ne fait RIEN (le piège nommé de ce
        check)."""
        chemin, conn = self._store_reel()
        with mock.patch.object(redaction, "rediger", lambda texte: texte):
            lessons.ecrire_lecon(
                conn, contenu=f"clé AWS en clair {FAUX_AWS}", cle_sujet="nu", **T)
        octets = self._octets_du_store(chemin, conn)

        # Preuve de fumée : sans rédaction, le secret EST dans les octets.
        self.assertIn(FAUX_AWS.encode("utf-8"), octets,
                      "la neutralisation n'a pas laissé passer le secret — le "
                      "contrôle négatif ne mesure rien")
        # Et la fonction d'assertion du témoin sait alors ÉCHOUER.
        with self.assertRaises(AssertionError):
            self._assert_secret_absent(octets, FAUX_AWS)

    def test_C6_un_secret_dans_une_metadonnee_est_REFUSE_et_rien_n_entre(self):
        """C6 — les champs de MÉTADONNÉE ne sont PAS rédigés (clés/énumérations) ;
        un secret reconnu dans l'un d'eux (ici `reference_accord`) lève `ValueError`
        NOMMANT le champ, AVANT tout insert — et RIEN n'entre au store."""
        chemin, conn = self._store_reel()
        with self.assertRaises(ValueError) as ctx:
            lessons.ecrire_lecon(
                conn, contenu="contexte anodin", cle_sujet="s",
                reference_accord="accord " + FAUX_AWS, **T)
        self.assertIn("reference_accord", str(ctx.exception),
                      "le ValueError ne nomme pas le champ fautif")
        n = conn.execute("SELECT COUNT(*) FROM " + schema.TABLE).fetchone()[0]
        self.assertEqual(n, 0, "une leçon est entrée au store malgré le refus")
        # et le secret n'est nulle part dans les octets du magasin.
        octets = self._octets_du_store(chemin, conn)
        self._assert_secret_absent(octets, FAUX_AWS)


class RedactionAuStoreDuRunTests(_StoreReelMixin):
    """T-00000641 — le store du RUN (V3) rédige À L'ÉCRITURE. La preuve est lue sur
    les OCTETS du `.db` (P1-P5). Le module de rédaction est chargé PAR CHEMIN."""

    def test_append_event_redige_le_payload_du_ledger(self):
        """T1 — les trois faux secrets dans `code_diff` et un champ libre ; relus
        sur les octets du `.db` : aucune chaîne secrète, marqueur présent."""
        chemin, store = self._store_v3()
        store.append_event(
            "T-1", "dev-multi", EventType.CODE_GENERATED,
            {"code_diff": f"diff {FAUX_AWS}\n{FAUX_PEM}", "note": FAUX_GHP},
        )
        octets = self._octets_du_store_v3(chemin)
        for secret in FAUX_SECRETS:
            self._assert_secret_absent(octets, secret)
        self.assertIn(b"[SECRET R", octets, "aucun marqueur : population vide ?")

    def test_la_projection_code_diff_est_redigee(self):
        """T2 — la COLONNE `code_diff` de la projection est rédigée (site distinct
        de l'events_ledger : ledger propre, projection qui fuit → T2 seul rougit)."""
        chemin, store = self._store_v3()
        store.append_event(
            "T-2", "dev-multi", EventType.CODE_GENERATED, {"code_diff": f"patch {FAUX_AWS}"})
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_AWS)
        proj = store.get_task_projection("T-2")
        self.assertIsNotNone(proj)
        self.assertNotIn(FAUX_AWS, proj["code_diff"])
        self.assertIn("[SECRET R", proj["code_diff"])

    def test_la_BRANCHE_D_ECHEC_du_pont_redige_l_intent(self):
        """T3 — branche d'échec `{"applied": False}` : le `json.dumps({"intent":
        ...})` du BOARD_COMMAND_FAILED est rédigé. Secret dans `after["title"]`."""
        chemin, store = self._store_v3()
        intent = {
            "operation_id": "op-fail",
            "event_kind": EventType.BOARD_RUNNING_REPLACED.value,
            "affected_task_ids": ["T-0001"],
            "before": None,
            "after": {"id": "T-0001", "title": FAUX_GHP},
            "revision_sha256": "0" * 64,
            "attempt": 0,
        }
        effect = store.consume_board_intent(intent)
        self.assertFalse(effect.get("applied", False))
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_GHP)
        conn = get_db_connection(chemin)
        n = conn.execute(
            "SELECT COUNT(*) FROM events_ledger WHERE event_type=?",
            (EventType.BOARD_COMMAND_FAILED.value,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(n, 1, "l'événement d'échec n'est pas écrit (vacuité)")

    def test_current_assignee_de_la_projection_est_redige(self):
        """T4 — intent APPLIQUÉ : `current_assignee` = owner rédigé (`:351`)."""
        chemin, store = self._store_v3()
        intent = {
            "operation_id": "op-proj",
            "event_kind": EventType.BOARD_TASK_OBSERVED.value,
            "affected_task_ids": ["T-0002"],
            "before": None,
            "after": {"id": "T-0002", "state": "pending", "owner": FAUX_AWS},
            "revision_sha256": "0" * 64,
            "attempt": 0,
        }
        effect = store.consume_board_intent(intent)
        self.assertTrue(effect.get("applied", False))
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_AWS)
        proj = store.get_task_projection(effect["v3_task_id"])
        self.assertNotIn(FAUX_AWS, proj["current_assignee"])

    def test_l_outbox_reste_EN_CLAIR_et_le_ledger_est_redige(self):
        """T5 — arbitrage MESURÉ : l'events_ledger est rédigé, mais
        `board_sync_outbox.payload_json` reste EN CLAIR (option 1, étape 4)."""
        chemin, store = self._store_v3()
        store.enqueue_board_command(
            "op-enq", EventType.BOARD_COMMAND_REQUESTED,
            {"board_task_id": "T-3", "note": FAUX_AWS},
        )
        conn = get_db_connection(chemin)
        led = conn.execute(
            "SELECT payload_json FROM events_ledger WHERE operation_id=?", ("op-enq",)
        ).fetchone()["payload_json"]
        out = conn.execute(
            "SELECT payload_json FROM board_sync_outbox WHERE operation_id=?", ("op-enq",)
        ).fetchone()["payload_json"]
        conn.close()
        self.assertNotIn(FAUX_AWS, led, "l'events_ledger n'est pas rédigé")
        self.assertIn(FAUX_AWS, out, "l'outbox devait rester EN CLAIR (option 1)")

    def test_l_effect_json_de_l_inbox_est_redige(self):
        """A-T2 — `board_sync_inbox.effect_json` passe par la MÊME rédaction que le
        ledger (une seule forme pour les deux colonnes ET le retour). `effect` est
        une énumération CLOSE sans secret aujourd'hui ; on FORCE un secret dedans
        (monkeypatch de `_reduce_board_intent`) pour prouver que le chemin d'écriture
        le rédige — sinon le `resume` (surface qui voyage) affirme une couverture de
        `board_sync_inbox` que rien ne tient."""
        chemin, store = self._store_v3()
        effet_secret = {"applied": True, "action": "projected", "v3_task_id": f"V3:{FAUX_AWS}"}
        intent = {
            "operation_id": "op-eff",
            "event_kind": EventType.BOARD_TASK_OBSERVED.value,
            "affected_task_ids": ["T-0007"],
            "before": None,
            "after": {"id": "T-0007", "state": "pending"},
            "revision_sha256": "0" * 64,
            "attempt": 0,
        }
        with mock.patch.object(EventStore, "_reduce_board_intent",
                               lambda self, cursor, i: dict(effet_secret)):
            retour = store.consume_board_intent(intent)
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_AWS)       # effect_json rédigé
        self.assertNotIn(FAUX_AWS, str(retour))            # le RETOUR aussi

    def test_l_evenement_d_ACK_est_redige(self):
        """T6 — l'événement d'ACK (`_insert_board_ack_event`, `:714`) est rédigé."""
        chemin, store = self._store_v3()
        store.enqueue_board_command(
            "op-ack", EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": "T-4"})
        claim = store.claim_board_command("worker")
        self.assertIsNotNone(claim)
        store.ack_board_command_with_event(
            "op-ack", claim["lease_token"], {"board_task_id": "T-4", "note": FAUX_GHP})
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_GHP)
        conn = get_db_connection(chemin)
        n = conn.execute(
            "SELECT COUNT(*) FROM events_ledger WHERE event_type=?",
            (EventType.BOARD_COMMAND_ACKED.value,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(n, 1, "l'événement d'ACK n'est pas écrit (vacuité)")

    def test_release_board_command_redige_last_error(self):
        """T11 — `release_board_command` rédige `last_error` (qui embarque
        str(exc)) ; `attempt` incrémenté interdit un vert par UPDATE à vide."""
        chemin, store = self._store_v3()
        store.enqueue_board_command(
            "op-rel", EventType.BOARD_COMMAND_REQUESTED, {"board_task_id": "T-5"})
        claim = store.claim_board_command("worker")
        exc = ValueError(f"validation failed on {FAUX_AWS}")
        ok = store.release_board_command("op-rel", claim["lease_token"], str(exc))
        self.assertTrue(ok, "le release n'a pas mis à jour la ligne")
        conn = get_db_connection(chemin)
        row = conn.execute(
            "SELECT last_error, attempt FROM board_sync_outbox WHERE operation_id=?",
            ("op-rel",),
        ).fetchone()
        conn.close()
        self.assertNotIn("AKIA", row["last_error"])
        self.assertEqual(int(row["attempt"]), 1)

    def test_le_rejeu_d_un_intent_portant_un_secret_ne_leve_pas_mismatch(self):
        """T12 — rejeu du MÊME intent (secret dans `after["title"]`) : le second
        appel rend l'effet du premier, aucun `operation identity mismatch` (C9)."""
        chemin, store = self._store_v3()
        intent = {
            "operation_id": "op-replay",
            "event_kind": EventType.BOARD_RUNNING_REPLACED.value,
            "affected_task_ids": ["T-0009"],
            "before": None,
            "after": {"id": "T-0009", "title": FAUX_GHP},
            "revision_sha256": "0" * 64,
            "attempt": 0,
        }
        first = store.consume_board_intent(intent)
        second = store.consume_board_intent(intent)  # ne doit PAS lever
        self.assertEqual(first, second)

    def test_le_controle_negatif_V3_rougit_quand_la_redaction_est_neutralisee(self):
        """T9 (V3) — contrôle négatif sur le module chargé PAR CHEMIN (objet
        DISTINCT de `cadre.ledger.redaction`) : mémoïsation FORCÉE, puis `rediger`
        neutralisé. Le secret ENTRE, et `_assert_secret_absent` sait ROUGIR."""
        chemin, store = self._store_v3()
        red = v3store._redaction()  # force la mémoïsation du module PAR CHEMIN
        with mock.patch.object(red, "rediger", lambda texte: texte):
            store.append_event(
                "T-neg", "dev", EventType.CODE_GENERATED, {"code_diff": f"clair {FAUX_AWS}"})
        octets = self._octets_du_store_v3(chemin)
        self.assertIn(FAUX_AWS.encode("utf-8"), octets,
                      "la neutralisation n'a rien laissé passer — le contrôle ne mesure rien")
        with self.assertRaises(AssertionError):
            self._assert_secret_absent(octets, FAUX_AWS)

    def test_la_branche_1_utilise_le_PAQUET_quand_il_est_importable(self):
        """S-00001655 — branche (1) : quand `cadre.ledger.redaction` EST importable,
        `_redaction()` rend l'OBJET PAQUET, jamais un chargement par chemin. EXERCÉ
        ICI via `src/` sur `sys.path` (ce banc l'insère en tête de fichier) — la
        résolution d'import est ÉQUIVALENTE à un paquet, mais ce n'est PAS une
        installation éditable `pip` (prérequis de phase 3, ABSENT au 2026-09-20).
        On ne prétend donc PAS tester `pip install` ; on prouve que la branche (1)
        est PRÉFÉRÉE et rend le module paquet."""
        import cadre.ledger.redaction as pkg  # importable ici : src sur sys.path (:43)
        chemin, store = self._store_v3()
        with mock.patch.object(v3store, "_REDACTION", None):
            self.assertIs(v3store._redaction(), pkg,
                          "branche (1) : le module rendu doit être l'objet paquet")

    def test_sans_module_de_redaction_le_store_du_RUN_refuse_d_ecrire(self):
        """T16 — posture FAIL-CLOSED : sans module de rédaction, toute écriture V3
        LÈVE un RuntimeError nommant le chemin, et RIEN n'entre au ledger. Restaure
        LES DEUX globals (module importé normalement — B-C2)."""
        chemin, store = self._store_v3()
        absent = chemin.parent / "no_such_redaction.py"
        # S-00001655 : fail-closed exige que les DEUX branches échouent — branche
        # (1) (paquet) mockée pour lever (sinon `cadre` sur `sys.path` la ferait
        # réussir ici), branche (2) (chemin) sur un fichier ABSENT.
        with mock.patch.object(v3store, "_importer_redaction_paquet",
                               side_effect=ModuleNotFoundError("cadre absent")), \
             mock.patch.object(v3store, "_CHEMIN_REDACTION", absent), \
             mock.patch.object(v3store, "_REDACTION", None):
            with self.assertRaises(RuntimeError) as ctx:
                store.append_event("T-x", "dev", EventType.CODE_GENERATED, {"code_diff": "x"})
        self.assertIn(str(absent), str(ctx.exception),
                      "le message ne nomme pas le chemin manquant")
        conn = get_db_connection(chemin)
        n = conn.execute("SELECT COUNT(*) FROM events_ledger").fetchone()[0]
        conn.close()
        self.assertEqual(n, 0, "un événement est entré malgré le refus")


# FAUX SECRETS supplémentaires (N1), toujours par CONCATÉNATION pour ne pas armer
# le gitleaks du dépôt : à l'exécution la valeur a la FORME d'un secret.
FAUX_GHP_PAT = "github_pat_" + "1A2b3C4d5E6f7G8h9I0j1K"       # >= 22 après le préfixe
FAUX_GLPAT = "glpat-" + "aZ09_-aZ09_-aZ09_-aa"                # glpat- + 20
FAUX_JWT = "eyJ" + "abc12345" + "." + "payload01" + "." + "sig012345"
FAUX_SK_PROJ = "sk-proj-" + "abcdefghij0123456789"           # sk-proj- + 20
FAUX_PEM_TRONQUE = (
    "-----BEGIN RSA PRIVATE " + "KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDF" + "AKEtronque\n"
    "fakefakefakefakefakefakefakefakefakefakefakefakefake" + "sansfin00\n"
)  # AUCUN marqueur END : clé coupée, doit tout de même être reconnue.

#: T-00001144 — un jeton par famille dont la tête a changé, plus AWS (tête inchangée),
#: CONCATÉNÉS (gitleaks) ; `(type, jeton)`.
JETONS_1144 = (
    ("aws_access_key", FAUX_AWS),
    ("github_token", FAUX_GHP),
    ("github_token", "github" + "_pat_" + "11ABCDEFG0123456789abcdef"),
    ("gitlab_token", "gl" + "pat-" + "aZ09bY18cX27dW36eV45"),
    ("jwt", "ey" + "J" + "hbGciOiJ" + "." + "eyJzdWIiOi" + "." + "c2lnbmF0dXJl"),
    ("slack_token", "xo" + "xb-" + "1234567890ab"),
    ("google_api_key", "AI" + "za" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"),
    ("openai_key", "sk-" + "proj-" + "abcdefghij0123456789KLMN"),
)
#: Les OUVERTURES des trois familles dont la QUEUE a changé (`_QUEUE` de `redaction.py`) ;
#: `github_pat_`, de même type que `gh?_`, admet `_` dans son corps et n'en est pas.
QUEUE_1144 = ("gh" + "p_", "xo" + "xb-", "AI" + "za")


def _jwt_a1(n: int) -> str:
    """Suite de départs `-eyJ` sans point : QUADRATIQUE au motif nu (T-00001143)."""
    return "ey" + "J" + ("a" * 8 + "-ey" + "J") * (n // 12)


def _jwt_a1_souligne(n: int) -> str:
    """La même suite liée par `_` : rougit le mutant dont la `suite` oublie `_`."""
    return "ey" + "J" + ("a" * 8 + "_ey" + "J") * (n // 12)


def _jwt_a5_9cf(n: int) -> str:
    """1 022 départs `-eyJ` puis un segment et une charge sans fin, précédés de 9 jetons
    coupés par un `Cf` (la passe projection rejoue les motifs à chaque substitution)."""
    neuf = " ".join("gh" + "p_" + "B" * 20 + chr(0x200B) + "B" * 20 for _ in range(9))
    return neuf + " " + ("-ey" + "J") * 1022 + "a" * 8 + "." + "b" * n


#: Pièces des deux générateurs d'équivalence, `(pièces, nombre max de pièces)` : celui du
#: critique de plan (r2 : départs nus et collés, points, séparateurs, un `Cf`) et celui du
#: planner (annexe § 3, plus dense en jwt).
_PIECES_JWT = (
    (("ey" + "J", "ey" + "J", "ey" + "Jey" + "J", "-ey" + "J", "_ey" + "J", ".ey" + "J", "xey" + "J",
      "1ey" + "J", "a" * 3, "a" * 7, "a" * 8, "b" * 9, "c" * 30, "-", "_", ".", "..", "-.", "_.", " ",
      chr(0x200B), "Z9", "AB", "é", "=", "/", "+"), 60),
    (("ey" + "J", "ey" + "J", "aaaa", "a" * 8, "b" * 9, "-", "_", ".", ".", "x", " ", "Z9", "-ey" + "J",
      "_ey" + "J", "1"), 40),
)
#: Textes FIXES qui rougissent les mutants de `_MotifLineaire` (départ nu, suite avec `.`,
#: `pos` oublié) : chacun MESURÉ rouge sur son mutant.
_TEXTES_JWT_FIXES = (
    "1ey" + "J-ey" + "J" + "a" * 8 + "." + "b" * 8 + "." + "c" * 8,
    "ey" + "Jaaa." + "ey" + "J" + "b" * 8 + "." + "c" * 8 + "." + "d" * 8,
    "ey" + "J" + "a" * 8 + ".ey" + "J" + "b" * 8 + "." + "c" * 8 + "." + "d" * 8,
    "b" * 9 + "_ey" + "J" + "a" * 8 + "." + "b" * 8 + "." + "c" * 8,
)


class MotifsFormesTests(unittest.TestCase):
    """N1 — les FORMES de secrets reconnues, leurs faux positifs et l'absence de
    ReDoS. Tests de FONCTION PURE (`rediger`/`contient_secret`), sans store."""

    def test_les_nouvelles_formes_sont_reconnues_et_redigees(self):
        for etiquette, secret in (
            ("github_pat", FAUX_GHP_PAT), ("glpat", FAUX_GLPAT), ("jwt", FAUX_JWT),
            ("sk-proj", FAUX_SK_PROJ), ("pem tronqué", FAUX_PEM_TRONQUE),
        ):
            with self.subTest(forme=etiquette):
                self.assertTrue(redaction.contient_secret(secret),
                                f"forme non reconnue : {etiquette}")
                redige = redaction.rediger("avant " + secret + " après")
                self.assertNotIn(secret, redige,
                                 f"le secret {etiquette} n'a pas été rédigé")
                self.assertIn("[SECRET R", redige, "aucun marqueur posé")

    def test_un_secret_AWS_colle_a_du_texte_est_reconnu(self):
        """Bornes lookaround : la clé d'accès AWS mord même COLLÉE à du texte."""
        colle = "prefixe" + FAUX_AWS + "suffixe"
        self.assertTrue(redaction.contient_secret(colle),
                        "AWS collé à du texte non reconnu (bornes \\b trop strictes)")
        self.assertNotIn(FAUX_AWS, redaction.rediger(colle))

    def test_task_ABC_n_est_PAS_un_faux_positif(self):
        """`task-ABC…` contient `sk-ABC…` mais n'a pas de frontière avant le `s` :
        il NE doit PAS matcher (faux positif nommé du check)."""
        innocent = "task-ABCDEFGHIJKLMNOPQRSTUVWX est une simple étiquette"
        self.assertFalse(redaction.contient_secret(innocent),
                         "`task-…` matche `sk-…` — faux positif")
        self.assertEqual(redaction.rediger(innocent), innocent,
                         "un texte innocent a été rédigé")

    def test_la_cle_SECRETE_aws_40_car_n_est_PAS_couverte(self):
        """BORNE ÉCRITE : la clé SECRÈTE AWS (40 car. base64, sans préfixe fixe)
        n'est PAS reconnue — indiscernable d'un base64 quelconque. On le PROUVE
        pour que la borne du docstring ne soit pas qu'une affirmation."""
        cle_secrete = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # 40 car.
        self.assertEqual(len(cle_secrete), 40)
        self.assertFalse(redaction.contient_secret(cle_secrete),
                         "la clé secrète AWS 40 car. est reconnue — la borne "
                         "'NON couverte' du docstring est fausse")

    def test_aucun_ReDoS_sur_100Ko_adversarial(self):
        """Aucun motif n'a de quantificateur imbriqué. Sur 100 Ko adversarial —
        dont un PEM ouvert SANS END (le cas du `[\\s\\S]*?…\\Z`) — `rediger` finit
        en < 1 s. Un motif catastrophique ferait exploser ce temps."""
        adversariaux = (
            "-----BEGIN PRIVATE " + "KEY-----\n" + "A" * 100_000,  # PEM sans END
            "sk-" + "a" * 100_000,
            "AKIA" * 25_000,
            "eyJ" + "a" * 100_000,
        )
        for i, texte in enumerate(adversariaux):
            with self.subTest(cas=i):
                debut = time.perf_counter()
                redaction.rediger(texte)
                ecoule = time.perf_counter() - debut
                self.assertLess(ecoule, 1.0,
                                f"rédaction lente ({ecoule:.3f}s) — ReDoS possible")

    # --- T-00001144 : le souligné autour d'un jeton --------------------------------------

    def test_T1144_foo_souligne_devant_un_jeton_le_redige_ENTIER(self):
        """ROUGE à 645846e8 pour sept familles (`\\b` tenait `_` pour un caractère de mot) ;
        rouge à tout mutant qui remet `\\b` en tête."""
        for type_, jeton in JETONS_1144:
            with self.subTest(famille=type_, jeton=jeton[:5]):
                self.assertEqual(redaction.rediger("foo_" + jeton + " fin"),
                                 "foo_[SECRET RÉDIGÉ:" + type_ + "] fin")

    def test_T1144_un_jeton_suivi_de_souligne_suite_est_redige(self):
        """Queue `_QUEUE` : ROUGE à 645846e8 et au mutant queue `\\b` pour `gh?_`, `xox?-`,
        `AIza` ; les autres familles avalent `_suite` dans leur corps, aucun jeton ne reste."""
        for type_, jeton in JETONS_1144:
            with self.subTest(famille=type_, jeton=jeton[:5]):
                redige = redaction.rediger("k=" + jeton + "_suite fin")
                self.assertNotIn(jeton, redige)
                if jeton.startswith(QUEUE_1144):
                    self.assertEqual(redige, "k=[SECRET RÉDIGÉ:" + type_ + "]_suite fin")
        self.assertEqual(redaction.rediger(FAUX_GHP + "_" + "xo" + "xb-" + "1" * 10),
                         MARQUEUR_GH + "_[SECRET RÉDIGÉ:slack_token]")

    def test_T1144_un_alphanumerique_colle_devant_un_jeton_le_laisse(self):
        """La tête refuse un ALPHANUMÉRIQUE (chiffres compris) devant l'ouverture : `ab1`
        n'est pas une frontière. ROUGE au mutant de tête sans chiffres `(?<![A-Za-z])`."""
        for type_, jeton in JETONS_1144:
            with self.subTest(famille=type_, jeton=jeton[:5]):
                self.assertEqual(redaction.rediger("ab1" + jeton), "ab1" + jeton)
                self.assertFalse(redaction.contient_secret("ab1" + jeton))

    def test_T1144_un_corps_fini_par_ghu_est_redige(self):
        """Le garde de queue ne mord QUE devant `_` : un corps qui finit par `ghu` reste un
        jeton. ROUGE au mutant de queue `(?<!gh[posur])(?<!github)` sans condition."""
        for texte in ("gh" + "s_" + "A" * 33 + "ghu", "x " + "gh" + "s_" + "A" * 33 + "ghu" + " y"):
            with self.subTest(texte=texte[:6]):
                self.assertNotIn("A" * 20, redaction.rediger(texte))

    def test_T1144_le_garde_de_queue_tient_un_jeton_gh_soude_par_la_projection(self):
        """Un jeton, un `Cf` seul, un `ghs_` lui-même coupé : dans la projection, le corps du
        premier avale l'ouverture `ghs` du second. ROUGE au mutant « sans garde »
        (`(?:\\b|(?![0-9A-Za-z]))`), qui laissait `_<16><U+200E><20>` en clair."""
        texte = "gh" + "s_" + "F" * 36 + chr(0x202E) + "gh" + "s_" + "d" * 16 + chr(0x200E) + "e" * 20
        self.assertEqual(redaction.rediger(texte), MARQUEUR_GH + chr(0x202E) + MARQUEUR_GH)

    def test_github_pat_suivi_d_une_lettre_non_ASCII_est_redige(self):
        """Queue `(?![0-9A-Za-z_])` de `github_pat_` (avis LOW de la revue de sécurité) : le
        `\\b` d'avant, Unicode, tenait `é` pour un caractère de mot. ROUGE à 645846e8 et au
        mutant queue `\\b` : le jeton sortait ENTIER en clair."""
        jeton = "github" + "_pat_" + "11ABCDEFG0123456789abcdef"
        for suite in ("é fin", "ñ", "日本"):
            with self.subTest(suite=suite):
                self.assertEqual(redaction.rediger("k=" + jeton + suite), "k=" + MARQUEUR_GH + suite)

    def test_T1144_google_fini_par_tiret_et_glpat_fini_par_tiret(self):
        """`AIza<34>-hello` : ROUGE au garde de queue du plan r2 (`(?![0-9A-Za-z]|…)` sans
        `\\b`) ; `glpat-<19>-` puis ` fin` : ROUGE à 645846e8 (queue `\\b` après un `-`)."""
        self.assertEqual(redaction.rediger("k=" + "AI" + "za" + "Q" * 34 + "-hello"),
                         "k=[SECRET RÉDIGÉ:google_api_key]hello")
        self.assertEqual(redaction.rediger("k=" + "gl" + "pat-" + "Q" * 19 + "-" + " fin"),
                         "k=[SECRET RÉDIGÉ:gitlab_token] fin")

    # --- T-00001143 : jwt linéaire, sans borne de longueur -------------------------------

    def test_T1143_un_jwt_est_redige_quelle_que_soit_sa_longueur(self):
        """AUCUNE borne : en-têtes de 4 096, 4 097 et 100 000, charge de 100 000. ROUGE à un
        en-tête borné `{8,4096}` (4 097, 100 000) ou plus court (4 096)."""
        for etiquette, jeton in (
                *((f"en-tête {n}", "ey" + "J" + "h" * n + "." + "p" * 40 + "." + "s" * 43)
                  for n in (4096, 4097, 100_000)),
                ("charge 100000", "ey" + "J" + "h" * 30 + "." + "p" * 100_000 + "." + "s" * 342)):
            with self.subTest(jeton=etiquette):
                self.assertEqual(redaction.rediger("a " + jeton + " b"), "a [SECRET RÉDIGÉ:jwt] b")

    def test_T1143_le_jwt_est_lineaire_sur_240_et_480_Ko(self):
        """Minimum de 3 essais ; < 1,5 s à 480 Ko et un doublement de taille qui ne
        quadruple pas le temps. ROUGE à 645846e8 (`a1` : 3,3 s puis 13 s), au mutant « sans
        saut » (a1) et au mutant dont la `suite` oublie `_` (`_eyJ` : 3,3 s puis 14 s)."""
        for nom, fabrique in (("a1", _jwt_a1), ("a5+9Cf", _jwt_a5_9cf), ("_eyJ", _jwt_a1_souligne)):
            temps = []
            for n in (240_000, 480_000):
                texte, meilleur = fabrique(n), float("inf")
                for _ in range(3):
                    debut = time.perf_counter()
                    redaction.rediger(texte)
                    meilleur = min(meilleur, time.perf_counter() - debut)
                temps.append(meilleur)
            with self.subTest(suite=nom, t240=round(temps[0], 3), t480=round(temps[1], 3)):
                self.assertLess(temps[1], 1.5, "jwt lent à 480 Ko")
                self.assertLess(temps[1], 3 * temps[0] + 0.02, "le doublement quadruple le temps")

    def test_T1143_le_jwt_lineaire_rend_les_correspondances_du_motif_nu(self):
        """`_MotifLineaire` contre `re.compile(son pattern)` : `finditer`, `search` et `sub`
        identiques sur 2 x 20 000 textes tirés (graine fixe) et sur les textes FIXES qui
        rougissent les mutants « départ nu », « suite avec `.` » et « `pos` oublié ». Le
        mutant « saut + 1 » est ÉQUIVALENT (le caractère sauté n'est pas dans S)."""
        jwt = dict(redaction.MOTIFS)["jwt"]
        nu = re.compile(jwt.pattern)
        rng = random.Random(1143)
        textes = list(_TEXTES_JWT_FIXES) + ["".join(rng.choice(pieces) for _ in range(rng.randint(1, n)))
                                            for pieces, n in _PIECES_JWT for _ in range(20_000)]
        ecarts, portes = [], 0
        for texte in textes:
            attendu = [m.span() for m in nu.finditer(texte)]
            portes += bool(attendu)
            trouve, premier = jwt.search(texte), nu.search(texte)
            if ([m.span() for m in jwt.finditer(texte)] != attendu
                    or (trouve and trouve.span()) != (premier and premier.span())
                    or jwt.sub(lambda _m: "[X]", texte) != nu.sub(lambda _m: "[X]", texte)):
                ecarts.append(texte)
        self.assertEqual(ecarts[:3], [], f"{len(ecarts)} écart(s) au motif nu")
        self.assertGreater(portes, 1000, "population vide : presque aucun texte ne porte de jwt")


FAUX_GHP_B = "ghp_" + "B" * 36                    # 2e jeton de la MÊME famille
MARQUEUR_GH = "[SECRET RÉDIGÉ:github_token]"


class ClesDeDictTests(_StoreReelMixin):
    """T-00001131 — `rediger_arbre` rédige AUSSI les CLÉS de dict, même règle que
    les feuilles. Mesuré sur la BASE 645846e8 : `emit("scan.sca", status={"ghp_…":
    "x"})` écrivait le jeton EN CLAIR au day-file, la clé n'étant jamais rédigée."""

    def test_une_cle_imbriquee_portant_un_token_est_redigee(self):
        redige = redaction.rediger_arbre({"status": {FAUX_GHP: "x", "npm": ("ok", 1)}})
        self.assertNotIn(FAUX_GHP, json.dumps(redige, ensure_ascii=False))
        self.assertEqual(redige, {"status": {MARQUEUR_GH: "x", "npm": ("ok", 1)}})

    def test_une_cle_tuple_reste_un_tuple_hashable_et_le_reste_intact(self):
        redige = redaction.rediger_arbre({(FAUX_GHP, 1): "t", 7: "n", None: "z"})
        self.assertEqual(redige, {(MARQUEUR_GH, 1): "t", 7: "n", None: "z"})
        cle = next(iter(redige))
        self.assertIs(type(cle), tuple, "une clé tuple n'est plus un tuple")
        hash(cle)  # lève si la clé rédigée n'est plus hashable

    def test_collision_de_cles_garde_le_plus_grand_repr_quel_que_soit_l_ordre(self):
        """Choix ÉCRIT au docstring de `rediger_arbre` : deux clés rédigées en un même marqueur
        FUSIONNENT, la valeur de la clé d'ORIGINE de plus grand `repr` reste. Le cas INVERSÉ
        (binôme F2, critic-opus F2) est ROUGE à la BASE 63f63f35, qui gardait la DERNIÈRE."""
        for i, arbre in enumerate(({FAUX_GHP: 1, FAUX_GHP_B: 2}, {MARQUEUR_GH: 1, FAUX_GHP: 2},
                                   {FAUX_GHP_B: 2, FAUX_GHP: 1})):
            with self.subTest(cas=i):
                redige = redaction.rediger_arbre(arbre)
                self.assertEqual(redige, {MARQUEUR_GH: 2})
                self.assertNotIn("ghp_", repr(redige))

    def test_un_arbre_sans_secret_garde_ses_octets(self):
        arbre = {"é": ["a", ("b", 2)], "k": {"x": None, "3": True}, "": 0.5}
        attendu = json.dumps(arbre, ensure_ascii=False, sort_keys=True)
        self.assertEqual(
            json.dumps(redaction.rediger_arbre(arbre), ensure_ascii=False, sort_keys=True),
            attendu, "la rédaction d'un arbre SANS secret n'est plus l'identité")

    def test_une_cle_portant_un_token_n_atteint_pas_les_octets_du_store_V3(self):
        chemin, store = self._store_v3()
        store.append_event("T-k", "dev-multi", EventType.CODE_GENERATED,
                           {"code_diff": "d", "status": {FAUX_GHP: "x"}})
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, FAUX_GHP)
        self.assertIn(MARQUEUR_GH.encode("utf-8"), octets, "aucun marqueur : population vide ?")


ZWSP, ZWJ, BOM, WJ = chr(0x200B), chr(0x200D), chr(0xFEFF), chr(0x2060)


def _coupe(secret: str, cf: str, i: int | None = None) -> str:
    """`secret` coupé par le caractère de format `cf` (au milieu par défaut)."""
    i = len(secret) // 2 if i is None else i
    return secret[:i] + cf + secret[i:]


_CF_FUZZ = (ZWSP, ZWJ, BOM, WJ, chr(0x202E), chr(0x00AD), chr(0x2061))
_SEP_FUZZ = (" ", "\n", ", ", "=", "/", "\t", ": ", ZWSP + " ", " " + WJ)
_AN = string.ascii_letters + string.digits
#: Ouvertures de `MOTIFS` qu'un corps tiré ne doit pas porter (un jeton dans le jeton).
_OUVERTURES = ("AK" + "IA", "ASIA", "AROA", "AIDA", "ey" + "J", "AI" + "za", "sk-", "gh" + "p_",
               "gh" + "o_", "gh" + "s_", "gh" + "u_", "gh" + "r_", "github", "gl" + "pat", "xo" + "x")


def _jeton_fuzz(rng: random.Random) -> str:
    """Un jeton d'une famille hors PEM (son corps lazy jusqu'à `\\Z` avale la suite), corps
    tiré dans l'ALPHABET RÉEL de sa famille (`T-00001130` r4) : `gh?_` `[0-9A-Za-z]`,
    `github_pat_` `+_`, `glpat-`, `eyJ`, `AIza`, `sk-` `+_-`, `xox?-` `+-`, AWS `[0-9A-Z]`."""
    def a(n: int, m: int = 0, c: str = _AN) -> str:
        while True:
            s = "".join(rng.choices(c, k=rng.randint(n, m or n)))
            if not any(o in s for o in _OUVERTURES):
                return s
    return rng.choice((
        lambda: "AK" + "IA" + a(16, c=string.ascii_uppercase + string.digits),
        lambda: "gh" + rng.choice("posur") + "_" + a(36, 44), lambda: "github" + "_pat_" + a(22, 30, _AN + "_"),
        lambda: "gl" + "pat-" + a(20, 28, _AN + "_-"),
        lambda: "ey" + "J" + a(8, 12, _AN + "_-") + "." + a(8, 12, _AN + "_-") + "." + a(8, 14, _AN + "_-"),
        lambda: "xo" + "x" + rng.choice("baprs") + "-" + a(10, 18, _AN + "-"), lambda: "AI" + "za" + a(35, c=_AN + "_-"),
        lambda: "sk-" + rng.choice(("", "proj-", "ant-api03-", "svcacct-")) + a(20, 30, _AN + "_-")))()


def _cas_fuzz(rng: random.Random) -> tuple[str, list[str]]:
    """DOMAINE du fuzz : 1 à 4 jetons, chacun coupé par 0 à 2 `Cf` STRICTEMENT intérieurs
    (préfixe compris), séparés par un séparateur NON-mot qui n'est pas qu'un `Cf`, ou COLLÉS
    derrière une clé AWS s'ils ouvrent en minuscule. Le domaine EXCLU ici (`Cf` seul, `Cf-`,
    rien, `_`) est joué, bornes comprises, par le corpus du banc frère
    `test_cadre_ledger_redaction_cf` : il cachait la régression de 0dc39b67 (S-00004005)."""
    purs, morceaux = [], [rng.choice(("", "Key ", "token="))]
    for k in range(rng.randint(1, 4)):
        j = _jeton_fuzz(rng)
        if k and not (purs[-1][:4] == "AK" + "IA" and j[0].islower() and rng.random() < 0.5):
            morceaux.append(rng.choice(_SEP_FUZZ))
        purs.append(j)
        for _ in range(rng.randint(0, 2)):
            i = rng.randint(1, len(j) - 1)
            j = j[:i] + rng.choice(_CF_FUZZ) + j[i:]
        morceaux.append(j)
    return "".join(morceaux), purs


class CaracteresDeFormatTests(_StoreReelMixin):
    """T-00001130 — un caractère de FORMAT (catégorie Unicode `Cf`) glissé dans un
    jeton défaisait les motifs. Mesuré sur la BASE 645846e8 : `emit("hook.deny", …,
    path="ghp_"+"A"*18+U+200B+"A"*18)` écrivait le jeton en clair au day-file. Témoins de
    d4542c09, rendus par le plan r4 avec la rédaction à travers les `Cf`."""

    def test_un_token_coupe_par_U200B_U200D_UFEFF_est_redige(self):
        for cf in (ZWSP, ZWJ, BOM):
            coupe = "gh" + "p_" + "A" * 18 + cf + "A" * 18
            with self.subTest(cf=f"U+{ord(cf):04X}"):
                self.assertTrue(redaction.contient_secret(coupe), "jeton coupé non reconnu")
                redige = redaction.rediger("avant " + coupe + " après")
                self.assertEqual(redige, "avant " + MARQUEUR_GH + " après",
                                 "jeton en clair, ou Cf réinjecté dans la valeur rédigée")
                self.assertEqual(redaction.rediger(redige), redige, "plus idempotent")

    def test_chaque_famille_de_MOTIFS_coupee_par_un_Cf_est_redigee(self):
        for type_, secret, i in (
            ("aws_access_key", FAUX_AWS, None), ("github_token", FAUX_GHP, None),
            ("github_token", FAUX_GHP_PAT, None), ("gitlab_token", FAUX_GLPAT, None),
            ("jwt", FAUX_JWT, None), ("openai_key", FAUX_SK_PROJ, None),
            ("slack_token", "xo" + "xb-" + "0123456789abc", None),
            ("google_api_key", "AI" + "za" + "B" * 35, None),
            ("private_key", FAUX_PEM, len("-----BEGIN PRIV")),  # coupé dans l'EN-TÊTE
        ):
            with self.subTest(forme=secret[:6]):
                coupe = _coupe(secret, WJ, i)
                self.assertTrue(redaction.contient_secret(coupe), "jeton coupé non reconnu")
                self.assertEqual(redaction.rediger(coupe), "[SECRET RÉDIGÉ:" + type_ + "]")

    def test_un_Cf_HORS_d_un_secret_est_garde(self):
        """Choix MESURÉ : les Cf ne sont retirés que DANS l'empan d'un secret. Un texte
        sain (emoji composé par ZWJ, BOM, marque bidi, trait d'union conditionnel) ressort
        à l'identique, et un Cf qui BORDE un jeton reste hors du marqueur."""
        for texte in ("famille " + "\U0001F468" + ZWJ + "\U0001F469" + ZWJ + "\U0001F467",
                      BOM + "texte précédé d'un BOM", "שלום" + chr(0x200F) + " abc",
                      "coupure" + chr(0x00AD) + "douce"):
            with self.subTest(texte=texte[:8]):
                self.assertFalse(redaction.contient_secret(texte))
                self.assertEqual(redaction.rediger(texte), texte, "texte sain abîmé")
        borde = "x" + ZWSP + FAUX_GHP + ZWJ + "y"
        self.assertEqual(redaction.rediger(borde), "x" + ZWSP + MARQUEUR_GH + ZWJ + "y")

    def test_C6_un_secret_coupe_par_un_Cf_en_metadonnee_est_REFUSE(self):
        chemin, conn = self._store_reel()
        with self.assertRaises(ValueError):
            lessons.ecrire_lecon(conn, contenu="anodin", cle_sujet="s",
                                 reference_accord="accord " + _coupe(FAUX_AWS, ZWSP), **T)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM " + schema.TABLE).fetchone()[0], 0)

    def test_un_token_coupe_n_atteint_pas_les_octets_du_store_V3(self):
        coupe = _coupe(FAUX_GHP, BOM)
        chemin, store = self._store_v3()
        store.append_event("T-cf", "dev-multi", EventType.CODE_GENERATED, {"code_diff": "d " + coupe})
        octets = self._octets_du_store_v3(chemin)
        self._assert_secret_absent(octets, coupe)
        self._assert_secret_absent(octets, coupe[:len(FAUX_GHP) // 2])  # moitié, hors échappement
        self.assertIn(MARQUEUR_GH.encode("utf-8"), octets, "aucun marqueur : population vide ?")

    def test_BORNES_a_b_c_ne_sont_PAS_couvertes(self):
        """BORNES ÉCRITES (a), (b), (c1), (c2), (c3) du docstring, PROUVÉES : un invisible
        hors `Cf` ou un `Cc` dans un jeton, `a<Cf>` devant un jeton lui-même coupé (coupé APRÈS
        sa longueur minimale, sa QUEUE), deux jetons collés, collés par `_`, un jeton de
        longueur fixe collé à un alphanumérique, restent en clair. Ce témoin rougit le jour
        où une borne tombe — mettre alors le docstring à jour."""
        for i, texte in enumerate((
                "a" + ZWSP + "gh" + "p_" + "A" * 18 + ZWSP + "A" * 18,
                "Q" + ZWSP + "AK" + ZWSP + "IA" + "Z3XYQ7WNRT4KLMND",
                *("gh" + "p_" + "A" * 18 + chr(c) + "A" * 18
                  for c in (0x34F, 0xFE0F, 0x115F, 0x3164, 0x2800, 0x7F, 0x85, 0x9F)),  # borne (a)
                FAUX_AWS + "AI" + "za" + "B" * 35,  # borne (c1) : deux jetons collés, aucun pris
                *("k=" + "AI" + "za" + "Q" * 35 + s for s in ("x", "9", "hello")),  # borne (c3)
                "k=" + FAUX_AWS + "9")):  # borne (c3)
            with self.subTest(cas=i):
                self.assertFalse(redaction.contient_secret(texte))
                self.assertEqual(redaction.rediger(texte), texte)
        self.assertEqual(redaction.rediger("x" + ZWSP + "gh" + "p_" + "A" * 36 + ZWSP + "A" * 10),
                         "x" + ZWSP + MARQUEUR_GH + ZWSP + "A" * 10)
        self.assertEqual(redaction.rediger("gh" + "p_" + "A" * 36 + "xo" + "xb-" + "1" * 10),
                         MARQUEUR_GH + "-" + "1" * 10)  # borne (c1) : la queue du collé reste
        self.assertEqual(redaction.rediger("k=" + FAUX_JWT + "_" + "ey" + "J" + "zyx98765.payload02.sig543210"),
                         "k=[SECRET RÉDIGÉ:jwt].payload02.sig543210")  # borne (c2)

    def test_aucun_ReDoS_a_travers_les_Cf_sur_100Ko(self):
        for i, texte in enumerate(("gh" + "p_" + ("A" + ZWSP) * 50_000, ZWSP * 100_000,
                                   "é" * 100_000, ("AK" + "IA" + ZWSP) * 20_000)):
            with self.subTest(cas=i):
                debut = time.perf_counter()
                redaction.rediger(texte)
                ecoule = time.perf_counter() - debut
                self.assertLess(ecoule, 1.0, f"rédaction lente ({ecoule:.3f}s)")

    def test_un_Cf_APRES_la_longueur_minimale_ne_laisse_pas_la_QUEUE(self):
        """Binôme F2 (S-00004001, critic-opus F1 i) — la passe brute, jouée D'ABORD, prenait
        le préfixe de longueur minimale et laissait la QUEUE en clair (BASE 63f63f35 : 70
        car. de `sk-ant-…`, `BBBBBBBBBB` de `glpat-…`). La projection passe EN PREMIER."""
        for type_, texte in (
            ("openai_key", "sk-" + "ant-api03-" + "Zq9-_" * 5 + ZWSP + "Zq9-_" * 14),
            ("gitlab_token", "gl" + "pat-" + "A" * 20 + ZWSP + "B" * 10),
            ("github_token", "gh" + "p_" + "A" * 36 + ZWJ + "B" * 10),
            ("github_token", "github" + "_pat_" + "A" * 22 + BOM + "B" * 10),
            ("slack_token", "xo" + "xb-" + "1" * 10 + WJ + "2" * 10),
            ("jwt", "ey" + "J" + "a" * 8 + "." + "b" * 8 + "." + "c" * 8 + ZWSP + "d" * 10),
        ):
            with self.subTest(forme=texte[:6]):
                self.assertEqual(redaction.rediger("Key " + texte),
                                 "Key [SECRET RÉDIGÉ:" + type_ + "]")

    def test_un_jeton_COLLE_derriere_un_jeton_coupe_est_redige_au_PREMIER_appel(self):
        """Binôme F2 (critic-opus F1 ii) — la BASE 63f63f35 laissait en clair le jeton collé
        derrière une clé AWS coupée (le `break` de la passe projection sautait les motifs
        suivants) et ne le rédigeait qu'au SECOND appel : idempotence perdue."""
        aws, slack = "[SECRET RÉDIGÉ:aws_access_key]", "[SECRET RÉDIGÉ:slack_token]"
        for texte, attendu in (
            ("AK" + "IA" + "ABCDEFGHIJKLMN" + chr(0x202E) + "OPxo" + "xb-1111111111", aws + slack),
            (_coupe(FAUX_AWS, ZWSP) + "gh" + "p_" + "C" * 36, aws + MARQUEUR_GH),
        ):
            with self.subTest(texte=texte[:4]):
                redige = redaction.rediger(texte)
                self.assertEqual(redige, attendu)
                self.assertEqual(redaction.rediger(redige), redige, "plus idempotent")

    def test_FUZZ_point_fixe_meme_portee_et_aucun_fragment_de_10_car(self):
        """Binôme F2 (critic-opus F1) — fuzz DÉTERMINISTE (graine fixe) sur le domaine de
        `_cas_fuzz`, corps à ALPHABETS RÉELS : `rediger` rend un point fixe, `contient_secret`
        a sa portée (vrai à l'entrée, faux à la sortie) et la sortie, privée de ses `Cf`, ne
        porte aucune fenêtre de 10 car. d'un jeton. ROUGE à la BASE 63f63f35."""
        rng = random.Random(20261003)
        for n in range(800):
            texte, purs = _cas_fuzz(rng)
            r = redaction.rediger(texte)
            plat = "".join(c for c in r if unicodedata.category(c) != "Cf")
            with self.subTest(cas=n, texte=texte):
                self.assertEqual(redaction.rediger(r), r, "plus idempotent")
                self.assertTrue(redaction.contient_secret(texte))
                self.assertFalse(redaction.contient_secret(r), "portée de contient_secret")
                self.assertEqual([j for j in purs for i in range(len(j) - 9)
                                  if j[i:i + 10] in plat], [], "fragment en clair")


if __name__ == "__main__":
    unittest.main()
