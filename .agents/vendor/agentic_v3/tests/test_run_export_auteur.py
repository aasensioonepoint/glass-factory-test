"""T-00000697 — `<auteur>` compose un segment du chemin d'export `runs/<auteur>/<copie>/<AAAA-MM>.jsonl` :
sa FORME est validée comme celle de `<copie>`, refus NOMMÉ (« auteur hors forme »), sur les trois entrées
qui reçoivent `auteur=` — `chemin_export` (donc `ajouter_a_l_export`), `backfill_historique` AVANT
l'UPDATE commité, `re_exporter_frappees` AVANT de lire `runs/<auteur>/`. Chaque témoin nomme son MUTANT.
Bac : CADRE_PROJECT_ROOT ET CADRE_STATE_DIR sur un tempfile, `_email_git` greffé. Aucune liaison ROOT à
__file__, aucun skipTest (test_adopting_gate)."""

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentic_v3.db import run_export
from agentic_v3.db.run_export import RunExportError
from agentic_v3.db.schema import create_tables

#: ULID valide dont l'horodatage de tête décode 2016-07 (mesuré par `_mois_de_ulid`).
_ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
#: Remontée hors de `runs/`, séparateur, vide (`runs/` + `""` + `c` = `runs/c` : un niveau disparaît).
_HOSTILES = ("../x", "a/b", "")
_REFUS = r"auteur hors forme \(segment de chemin unique attendu\)"


class TestAuteurHorsFormeRefuse(unittest.TestCase):
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
        create_tables(self.db)

    def _inserer(self, n, *, frappee):
        cx = sqlite3.connect(str(self.db))
        try:
            for i in range(n):
                cx.execute(
                    "INSERT INTO events_ledger (task_id,agent_role,event_type,payload_json,"
                    "created_at,operation_id,event_kind,attempt,ulid,predecesseur_ulid) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"T-{i}", "run", "TASK_CREATED", "{}", f"2026-08-01 00:00:0{i}", f"op{i}",
                     "TASK_CREATED", 0, run_export.nouvel_ulid() if frappee else None, None),
                )
            cx.commit()
        finally:
            cx.close()

    def _nulles(self):
        cx = sqlite3.connect(str(self.db))
        try:
            return cx.execute("SELECT COUNT(*) FROM events_ledger WHERE ulid IS NULL").fetchone()[0]
        finally:
            cx.close()

    def _rien_hors_de_runs(self):
        # `runs/../x` = `<racine>/x` : la seule cible d'écriture HORS de `runs/` que les hostiles ouvrent.
        self.assertFalse((self.racine / "x").exists(), "une écriture a fui hors de runs/")

    # MUTANT : retirer `_valider_copie(auteur_effectif, "auteur")` de `chemin_export` => le chemin est
    # composé (`runs/../x/…` sort de `runs/`), aucune levée ; `ajouter_a_l_export` y écrit.
    def test_chemin_export_et_l_ajout_refusent_un_auteur_hors_forme_nommement(self):
        for hostile in _HOSTILES:
            with self.subTest(auteur=hostile):
                with self.assertRaisesRegex(RunExportError, _REFUS) as ctx:
                    run_export.chemin_export(_ULID, depuis=self.racine, copie="c", auteur=hostile)
                self.assertIn(repr(hostile), str(ctx.exception))
                with self.assertRaisesRegex(RunExportError, _REFUS):
                    run_export.ajouter_a_l_export({"ulid": _ULID, "task_id": "T"},
                                                  depuis=self.racine, copie="c", auteur=hostile)
        self._rien_hors_de_runs()

    # Garde-fou du témoin : la validation n'écarte pas la forme NOMINALE (`sha256(email)[:16]`), ni
    # passée par `auteur=`, ni résolue par `auteur_courant()`. MUTANT : un refus trop large => rouge.
    def test_une_empreinte_sha256_16_est_acceptee(self):
        empreinte = run_export.empreinte_auteur("banc@test")
        self.assertEqual(empreinte, hashlib.sha256(b"banc@test").hexdigest()[:16])
        for auteur in (empreinte, None):
            chemin = run_export.chemin_export(_ULID, depuis=self.racine, copie="c", auteur=auteur)
            self.assertEqual(chemin.parts[-4:], ("runs", empreinte, "c", "2016-07.jsonl"))

    # MUTANT : retirer la validation en tête de `backfill_historique` => l'UPDATE des ULID est COMMITÉ
    # puis l'export écrit sous `<racine>/x/` (aucune levée) ; avec la SEULE garde de `chemin_export`,
    # le refus tombe APRÈS le commit (lignes frappées hors du texte, la perte T1) => `_nulles` rougit.
    def test_backfill_historique_refuse_avant_de_frapper_la_base(self):
        self._inserer(2, frappee=False)
        for hostile in _HOSTILES:
            with self.subTest(auteur=hostile):
                with self.assertRaisesRegex(RunExportError, _REFUS):
                    run_export.backfill_historique(base=self.db, depuis=self.racine, auteur=hostile)
                self.assertEqual(self._nulles(), 2, "des ULID ont été frappés avant le refus")
        self._rien_hors_de_runs()

    # MUTANT : retirer la validation en tête de `re_exporter_frappees` (la garde de `chemin_export`
    # restant seule) => `runs/<auteur>/` est LU — `runs/../x/` hors de `runs/` — AVANT tout refus :
    # l'espion de `_lignes_du_texte_sous` rougit, et le refus levé n'est plus celui de l'auteur.
    def test_re_exporter_frappees_refuse_avant_de_lire_runs_auteur(self):
        self._inserer(1, frappee=True)
        espion = mock.patch.object(run_export, "_lignes_du_texte_sous",
                                   wraps=run_export._lignes_du_texte_sous)
        for hostile in _HOSTILES:
            with self.subTest(auteur=hostile), espion as lu:
                with self.assertRaises(RunExportError) as ctx:
                    run_export.re_exporter_frappees(base=self.db, depuis=self.racine, auteur=hostile)
                self.assertEqual(lu.call_args_list, [], "runs/ lu avant le refus de l'auteur")
                self.assertRegex(str(ctx.exception), _REFUS)
        self._rien_hors_de_runs()

    # Épingle des docstrings : le refus de FORME est HORS des blocs `refus_nomme`, AVANT l'ouverture du
    # store. MUTANT : valider APRÈS l'ouverture => un store non SQLite lève `StoreV3Refuse` d'abord.
    # Contrôle : auteur résolu (`None`) => `StoreV3Refuse` — le faux store est bien refusable.
    def test_le_refus_de_forme_precede_l_ouverture_du_store(self):
        from agentic_v3.db.refus_store import StoreV3Refuse

        faux = self.state / "pas-sqlite.db"
        faux.write_bytes(b"pas une base sqlite " * 64)
        for nom in ("backfill_historique", "re_exporter_frappees"):
            with self.subTest(chemin=nom):
                with self.assertRaisesRegex(RunExportError, _REFUS):
                    getattr(run_export, nom)(base=faux, depuis=self.racine, auteur="../x")
                with self.assertRaises(StoreV3Refuse):
                    getattr(run_export, nom)(base=faux, depuis=self.racine, auteur=None)


if __name__ == "__main__":
    unittest.main()
