"""Parité du refus de store V3 : ouvreurs (`classer_refus`) contre pont (`replay_sync`).

T-00001005 (BK-408, critère 1) : « les quatre ouvreurs appliquent le même refus
nommé que tasks_sync.py ». Deux copies du classement vivent dans le dépôt —
`agentic_v3/db/refus_store.py::classer_refus` pour les ouvreurs, et la sienne
dans `replay_sync` (`.agents/bin/tasks_sync.py`), que T-00001004 garde (décision
pilote S-00003324, 3c). Ce fichier est le SEUL endroit où les deux arbres
coexistent : un test de `agentic_v3/tests/` voyage avec le paquet et ne peut pas
nommer `.agents/bin/`.

LES DEUX SENS, SUR LA TABLE CI-DESSOUS. Direct, toujours : tout type que
`replay_sync` AVALE à la construction du pont (il rend sans lever) est CLASSÉ par
`classer_refus` — l'ouvreur refuse au moins ce que le pont refuse. Inverse, quand
`tasks` expose `_annonce_refus_construction` (les branches (5)-(8) de
T-00001004) : l'ensemble des entrées de la table que `classer_refus` classe est
ÉGAL à l'ensemble que le pont avale (critic-opus T3). Sans cette fonction (arbre
antérieur à T-00001004), seul le sens direct est asserté. Une classe ajoutée plus
tard à l'un des deux classeurs hors de la table ci-dessous échappe à ce témoin
(borne dite, pas cachée).

LIBELLÉS (T-00001078) : les ensembles ne voient pas le TEXTE. Pour les six
entrées des quatre causes neuves (`PermissionError`, `NotADirectoryError`,
`FileExistsError`, codes 8, 1544 et 11), `_annonce_refus_construction` rend MOT
POUR MOT « <verdict> (<cause>) » de `classer_refus` : les deux côtés recopient ces
libellés à la main, ce témoin rougit si l'un dérive. Les autres libellés ne sont
pas comparés ici (borne dite).

Méthode : `BoardBridge` patché au module (`side_effect=exc`, un appel asserté),
`tasks.replay_sync(root, pont_commande={})` sur un mémo NEUF par type (un mémo
réutilisé rendrait 0 sans construire), classes prises À LA COUTURE de
`run_export`, jamais par `import cadre…`. Codes SQLite posés à la main :
SYNTHÉTIQUES. Contrôle positif : les quatre types avalés au relevé M5 du plan
(HEAD 08d1b889), PLUS les sept avalés depuis T-00001056 (relevé T-00001078), le sont
encore, sinon ce banc ne mesurerait rien.

Bac : racine, `CADRE_STATE_DIR` et `AGENTS_EVENTS_DIR` dans une
`TemporaryDirectory` ; `CADRE_PROJECT_ROOT` retiré le temps du test.
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
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ouvreurs_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "agentic_v3")


def test_provenance_v3_en_processus():
    attendu = _VENDOR.exiger(ROOT, "agentic_v3")
    assert Path(sys.modules["agentic_v3"].__file__).resolve().parent == attendu.resolve()


TASKS_PATH = ROOT / ".agents" / "bin" / "tasks.py"
SPEC = importlib.util.spec_from_file_location("tasks_parite_refus_v3_under_test", TASKS_PATH)
assert SPEC is not None and SPEC.loader is not None
tasks = importlib.util.module_from_spec(SPEC)
sys.modules["tasks_parite_refus_v3_under_test"] = tasks
SPEC.loader.exec_module(tasks)

#: Avalés par `replay_sync` au relevé M5 du plan (HEAD 08d1b889) : contrôle positif.
AVALES_AU_RELEVE = frozenset({"CadrePathError", "SchemaVersionError", "EmplacementRefuse",
                              "PanneInfrastructure"})

#: Avalés DEPUIS T-00001056 (relevé T-00001078, base 1e1e6738) : SECOND contrôle positif — une
#: régression du pont ne RÉTRÉCIT plus le banc en silence (sans lui, retirer une classe du pont ET
#: de `classer_refus` laisserait les deux ensembles égaux et le banc vert).
AVALES_T1056 = frozenset({"PermissionError", "NotADirectoryError", "FileExistsError",
                          "READONLY_8", "READONLY_DIRECTORY_1544", "CORRUPT_11",
                          "CORRUPT_267"})

#: T-00001078 : les six entrées de la table dont le LIBELLÉ est comparé à celui du pont.
LIBELLES_DU_PONT_T1078 = ("PermissionError", "NotADirectoryError", "FileExistsError",
                          "READONLY_8", "READONLY_DIRECTORY_1544", "CORRUPT_11")


class PariteOuvreursPontV3Tests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "repo"
        board_dir = self.root / ".agents" / "state" / "board"
        board_dir.mkdir(parents=True)
        (board_dir / "TASKS.json").write_text(
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
        from agentic_v3.db import run_export, schema
        from agentic_v3.db.refus_store import classer_refus
        from agentic_v3.reconciliation import board_bridge

        self.run_export, self.schema = run_export, schema
        self.classer_refus, self.board_bridge = classer_refus, board_bridge

    def _table(self) -> dict[str, BaseException]:
        """Les huit types de l'ensemble, plus 517 ; depuis T-00001078 les cinq causes du pont
        (`PermissionError`, `NotADirectoryError`, `FileExistsError`, codes 8, 1544, 11, 267) ;
        et les NÉGATIFS hors ensemble des deux côtés (`RuntimeError`, `ValueError`,
        `FileNotFoundError`, `IsADirectoryError`, `OSError` 28, codes 19, 14, 10, et
        l'étendu 1032 READONLY_DBMOVED — primaire 8, mais base déplacée ou supprimée sous
        la connexion, jamais « lecture seule » : binôme de fin de la fournée 3)."""
        store_mod, workspace_mod = self.run_export._couture_ledger_store()

        def sqlite_code(classe: type, code: int) -> BaseException:
            exc = classe(f"erreur SQLite fabriquée, code {code}")
            exc.sqlite_errorcode = code  # SYNTHÉTIQUE
            return exc

        return {
            "CadrePathError": self.run_export._cadre("paths").CadrePathError("racine (parité)"),
            "SchemaVersionError": self.schema.SchemaVersionError("version (parité)"),
            "EmplacementRefuse": store_mod.EmplacementRefuse("emplacement (parité)"),
            "OuvertureImpossible": store_mod.OuvertureImpossible("ouverture (parité)"),
            "HorsRacine": workspace_mod.HorsRacine("hors racine (parité)"),
            "NOTADB_26": sqlite_code(sqlite3.DatabaseError, 26),
            "BUSY_5": sqlite_code(sqlite3.OperationalError, 5),
            "PanneInfrastructure": self.run_export.PanneInfrastructure("panne (parité)"),
            "BUSY_517": sqlite_code(sqlite3.OperationalError, 517),
            "PermissionError": PermissionError(13, "Permission denied (parité)"),
            "NotADirectoryError": NotADirectoryError(20, "Not a directory (parité)"),
            "FileExistsError": FileExistsError(17, "File exists (parité)"),
            "READONLY_8": sqlite_code(sqlite3.OperationalError, 8),
            "READONLY_DIRECTORY_1544": sqlite_code(sqlite3.OperationalError, 1544),
            "CORRUPT_11": sqlite_code(sqlite3.DatabaseError, 11),
            "CORRUPT_267": sqlite_code(sqlite3.DatabaseError, 267),
            "READONLY_DBMOVED_1032": sqlite_code(sqlite3.OperationalError, 1032),
            "FileNotFoundError": FileNotFoundError(2, "No such file (parité)"),
            "IsADirectoryError": IsADirectoryError(21, "Is a directory (parité)"),
            "OSError_28": OSError(28, "No space left on device (parité)"),
            "CONSTRAINT_19": sqlite_code(sqlite3.IntegrityError, 19),
            "CANTOPEN_14": sqlite_code(sqlite3.OperationalError, 14),
            "IOERR_10": sqlite_code(sqlite3.OperationalError, 10),
            "RuntimeError": RuntimeError("hors ensemble (parité)"),
            "ValueError": ValueError("hors ensemble (parité)"),
        }

    def _avale(self, nom: str, exc: BaseException) -> bool:
        """Vrai si `replay_sync` rend sans lever quand la construction du pont lève
        `exc` ; une levée doit être `exc` lui-même."""
        pont = mock.Mock(side_effect=exc)
        with mock.patch.object(self.board_bridge, "BoardBridge", pont), \
                mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            try:
                tasks.replay_sync(self.root, pont_commande={})
                avale = True
            except BaseException as leve:  # noqa: BLE001 - toute levée est examinée
                self.assertIs(leve, exc, f"{nom} : une autre levée que l'injectée remonte")
                avale = False
        self.assertEqual(pont.call_count, 1, f"{nom} : BoardBridge n'a pas été construit une fois")
        return avale

    def test_tout_type_avale_par_replay_sync_est_classe_par_classer_refus(self) -> None:
        table = self._table()
        avales = set()
        for nom, exc in table.items():
            with self.subTest(type=nom):
                if self._avale(nom, exc):
                    avales.add(nom)
                    self.assertIsNotNone(
                        self.classer_refus(exc),
                        f"{nom} : replay_sync l'avale, classer_refus ne le classe pas — "
                        "l'ouvreur refuserait MOINS que le pont",
                    )
        self.assertLessEqual(
            AVALES_AU_RELEVE | AVALES_T1056, avales,
            f"contrôle positif : avalés {sorted(avales)}, attendu au moins "
            f"{sorted(AVALES_AU_RELEVE | AVALES_T1056)}",
        )
        if hasattr(tasks, "_annonce_refus_construction"):
            classes = {nom for nom, exc in table.items() if self.classer_refus(exc) is not None}
            self.assertEqual(
                classes, avales,
                "sens inverse : classer_refus et replay_sync divergent — "
                f"classés seuls {sorted(classes - avales)}, avalés seuls {sorted(avales - classes)}",
            )

    def test_libelles_des_quatre_causes_neuves_egaux_au_pont(self) -> None:
        """T-00001078 (réserve B-C4) : sur les six entrées des quatre causes neuves,
        `_annonce_refus_construction(exc)` vaut `f"{verdict} ({cause})"` de
        `classer_refus(exc)` — la parité de LIBELLÉ, que les ensembles ne voient pas."""
        if not hasattr(tasks, "_annonce_refus_construction"):
            self.skipTest("arbre antérieur à T-00001004 : `_annonce_refus_construction` absente")
        table = self._table()
        for nom in LIBELLES_DU_PONT_T1078:
            with self.subTest(type=nom):
                classe = self.classer_refus(table[nom])
                self.assertIsNotNone(classe, f"{nom} : classer_refus ne le classe pas")
                verdict, cause = classe
                self.assertEqual(
                    tasks._annonce_refus_construction(table[nom]), f"{verdict} ({cause})",
                    f"{nom} : le libellé de classer_refus diverge de celui du pont",
                )


if __name__ == "__main__":
    unittest.main()
