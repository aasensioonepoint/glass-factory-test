#!/usr/bin/env python3
"""Banc de `cadre.ledger.anciennes_bases` — le lecteur d'une ANCIENNE base V3.

T-01M534ZNXKKP91XZRV5M5WBAYX, étape 6, réserve C14 du plan-critic. Le lecteur
REÇOIT une connexion déjà ouverte (`lire_specs(conn)`) : c'est le setup
(`.agents/bin/setup_projet.py`) qui ouvre la base par
`store.connect(<absolu>, lecture_seule=True)` après un `os.stat`. Le paquet
`ledger/` ne porte donc aucun `connect` hors de `store.py`
(`test_cadre_ledger_purete`), et le SQL reste sous `src/cadre/ledger/`
(`test_cadre_sql_locality`, dette à 9/9).

Témoins, chacun nommant la mutation qui le rougit :
  * `test_lit_sans_annexe` — la base du banc est en WAL (octets 18-19 = 2,
    asserté) ; l'ouverture `lecture_seule` + `lire_specs` rend les lignes, et
    l'empreinte comme la liste du répertoire sont IDENTIQUES avant et après.
    Rougit si `lire_specs` écrit (un PRAGMA d'écriture, une table), ou si
    `store.connect(lecture_seule=True)` perd `immutable=1`. Son contrôle
    (`test_le_controle_mode_ro_cree_des_annexes`) prouve que la propriété peut
    échouer : `mode=ro` seul, sur la même base, CRÉE `-shm`/`-wal`.
  * `test_wal_ignore_dit` — la BORNE qui justifie le `os.stat` du `-wal` côté
    setup : avec un `-wal` non rabattu, `immutable` ne voit PAS ses trames.
  * `test_trois_etats` — table absente -> `None`, table vide -> `[]`.
  * `test_normaliser_chemin` et `test_bilan` — fonctions pures.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, où qu'il vive, chargé par chemin (vendor_paths) :
# aucun `src` inséré en tête de sys.path (T-01M5BXTPQE, lot H).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ledger_anciennes_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import anciennes_bases as ab  # noqa: E402
from cadre.ledger import store  # noqa: E402

#: L'ANCIENNE forme de la table : clé (req_id, version), avant T-00001223.
_DDL_ANCIENNE = (
    "CREATE TABLE spec_requirements (req_id TEXT NOT NULL, version INTEGER NOT "
    "NULL DEFAULT 1, file_path TEXT NOT NULL, section_title TEXT NOT NULL, "
    "content_markdown TEXT NOT NULL, tags_json TEXT NOT NULL, "
    "PRIMARY KEY (req_id, version))"
)
_INSERT = ("INSERT INTO spec_requirements (req_id, version, file_path, "
           "section_title, content_markdown, tags_json) VALUES (?, ?, ?, ?, ?, '[]')")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _ecrire_base(chemin: Path, lignes, *, wal: bool = True) -> None:
    conn = sqlite3.connect(str(chemin))
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_DDL_ANCIENNE)
        conn.executemany(_INSERT, lignes)
        conn.commit()
    finally:
        conn.close()


_LIGNES = [
    ("R1", 1, "docs/specs/a.md", "A", "texte a v1"),
    ("R1", 2, "docs/specs/a.md", "A", "texte a v2"),
    ("R2", 1, "specs\\b.md", "B", "texte b"),
]


class LecteurTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="anciennes-bases-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _base(self, nom: str = "legacy.db", lignes=None, wal: bool = True) -> Path:
        dossier = self.tmp / nom.split(".")[0]
        dossier.mkdir()
        chemin = dossier / nom
        _ecrire_base(chemin, _LIGNES if lignes is None else lignes, wal=wal)
        return chemin

    def test_lit_sans_annexe(self):
        p = self._base()
        self.assertEqual(p.read_bytes()[18:20], b"\x02\x02",
                         "la base du banc doit être en WAL, sinon le témoin ne peut pas rougir")
        avant = (_sha(p), sorted(x.name for x in p.parent.iterdir()))
        conn = store.connect(p.resolve(), lecture_seule=True)
        try:
            lignes = ab.lire_specs(conn)
        finally:
            conn.close()
        apres = (_sha(p), sorted(x.name for x in p.parent.iterdir()))
        self.assertEqual(avant, apres, "la lecture a touché la base ou laissé un annexe")
        self.assertEqual(avant[1], ["legacy.db"])
        self.assertEqual(
            sorted((x.file_path, x.req_id, x.version) for x in lignes),
            [("docs/specs/a.md", "R1", 1), ("docs/specs/a.md", "R1", 2),
             ("specs\\b.md", "R2", 1)])
        par_cle = {(x.req_id, x.version): x.empreinte for x in lignes}
        self.assertEqual(par_cle[("R1", 1)], hashlib.sha256(b"texte a v1").hexdigest())
        self.assertEqual(par_cle[("R2", 1)], hashlib.sha256(b"texte b").hexdigest())

    def test_le_controle_mode_ro_cree_des_annexes(self):
        """CONTRÔLE de non-vacuité du témoin ci-dessus (mutation M10 du plan) :
        `mode=ro` sans `immutable` CRÉE des annexes sur la même base en WAL."""
        p = self._base()
        conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            ab.lire_specs(conn)
        finally:
            conn.close()
        noms = sorted(x.name for x in p.parent.iterdir())
        self.assertNotEqual(noms, ["legacy.db"],
                            "mode=ro n'a créé aucun annexe : le témoin ne prouve plus rien")

    def test_wal_ignore_dit(self):
        """BORNE : un `-wal` NON rabattu est invisible à `immutable=1`. C'est
        pourquoi le setup juge la taille du `-wal` (os.stat) et rend `dégradé`
        quand il n'est pas vide — et pourquoi un `-wal` déjà rabattu mais non
        vide donne un `dégradé` par excès (réserve C17 : DITE, pas corrigée)."""
        src = self.tmp / "src"
        src.mkdir()
        base = src / "v.db"
        ecrivain = sqlite3.connect(str(base))
        try:
            ecrivain.execute("PRAGMA journal_mode=WAL")
            ecrivain.execute(_DDL_ANCIENNE)
            ecrivain.execute(_INSERT, ("R1", 1, "a.md", "A", "un"))
            ecrivain.commit()
            ecrivain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            ecrivain.execute("PRAGMA wal_autocheckpoint=0")
            ecrivain.execute(_INSERT, ("R2", 1, "a.md", "B", "deux"))
            ecrivain.commit()
            copie = self.tmp / "copie"
            copie.mkdir()
            shutil.copy2(base, copie / "v.db")
            shutil.copy2(src / "v.db-wal", copie / "v.db-wal")
        finally:
            ecrivain.close()
        self.assertGreater((copie / "v.db-wal").stat().st_size, 0)
        conn = store.connect((copie / "v.db").resolve(), lecture_seule=True)
        try:
            vus = ab.lire_specs(conn)
        finally:
            conn.close()
        self.assertEqual([x.req_id for x in vus], ["R1"],
                         "immutable a lu les trames du -wal : la borne a changé, "
                         "le jugement du -wal côté setup est à revoir")

    def test_trois_etats(self):
        vide = self.tmp / "vide.db"
        conn = sqlite3.connect(str(vide))
        conn.execute("CREATE TABLE autre (x)")
        conn.commit()
        conn.close()
        lecteur = store.connect(vide.resolve(), lecture_seule=True)
        try:
            self.assertIsNone(ab.lire_specs(lecteur), "table absente : None, jamais []")
        finally:
            lecteur.close()
        p = self._base("zero.db", lignes=[])
        lecteur = store.connect(p.resolve(), lecture_seule=True)
        try:
            self.assertEqual(ab.lire_specs(lecteur), [])
        finally:
            lecteur.close()


class FonctionsPuresTests(unittest.TestCase):
    def test_normaliser_chemin(self):
        cas = {
            "docs\\specs\\a.md": "docs/specs/a.md",
            "./specs/b.md": "specs/b.md",
            "specs/c.md": "specs/c.md",
            "../x.md": None,
            "a/../b.md": None,
            "/abs/x.md": None,
            "C:/x.md": None,
            "C:\\x.md": None,
            "": None,
            ".": None,
        }
        for brut, attendu in cas.items():
            with self.subTest(brut=brut):
                self.assertEqual(ab.normaliser_chemin(brut), attendu)

    def test_bilan(self):
        h = ab.empreinte
        anciennes = [
            ab.LigneSpec("docs\\a.md", "R1", 1, h("v1")),
            ab.LigneSpec("docs\\a.md", "R1", 2, h("v2")),
            ab.LigneSpec("docs/a.md", "R2", 1, h("b")),
            ab.LigneSpec("docs/parti.md", "R3", 1, h("c")),
            ab.LigneSpec("../hors.md", "R4", 1, h("d")),
        ]
        nouvelles = [
            ab.LigneSpec("docs/a.md", "R1", 1, h("v2")),
            ab.LigneSpec("docs/a.md", "R2", 1, h("b modifié")),
        ]
        b = ab.bilan(anciennes, nouvelles)
        self.assertEqual(
            (b.lignes, b.cles, b.identiques, b.changees, b.sans_source,
             b.versions_perdues, b.hors_depot),
            (5, 3, 1, 1, 1, 1, 1))
        self.assertEqual(b.retrouvees, 2)
        self.assertEqual(ab.chemins(anciennes), ["docs/a.md", "docs/parti.md"])


if __name__ == "__main__":
    unittest.main()
