#!/usr/bin/env python3
"""BANC DE CE QUE LE NOM D'UN STORE DÉSIGNE APRÈS UN REFUS — `cadre.ledger.store`.

T-00001179, défaut mesuré S-00004110. `_designe_encore(ident, apres)` jugeait
« le nom désigne encore le fichier » sur `(dev, ino)` seul, plus « pas un lien ».
Sous Linux le noyau RECYCLE l'inode libéré : `unlink` puis `mkdir` au même nom
rend un répertoire de MÊME `(dev, ino)`, `st_nlink=2` (mesuré, conteneur
python:3.12-slim). Le refus disait alors « le même fichier, qui porte désormais
2 liens physiques » au lieu de « un autre fichier », et `_ce_qui_reste`
affirmait que « le fichier vide créé reste en place ». Sur darwin (APFS)
l'inode n'est pas réutilisé : le banc d'intégration
`test_cadre_ledger_stores.py` (cas « un autre fichier ») y reste vert et ne
VOIT pas le défaut.

CE QUE CE BANC TIENT, SUR TOUT HÔTE. Les `Identite` sont construites À LA MAIN :
le recyclage d'inode y est POSÉ, jamais attendu du noyau. Il juge les trois
aides (`_designe_encore`, `_ce_que_le_nom_designe`, `_ce_qui_reste`), puis le
chemin réel `ouvrir_sans_suivre` avec un `Workspace` simulé et un `connecter`
que SQLite refuse. Aucun fichier n'est créé ni lu. Chaque refus attendu a son
témoin NON VIDE : le même jeu d'aides dit aussi « le même fichier » et « reste
en place » quand c'est vrai.

CE QU'IL NE TIENT PAS — RÉSIDU NOMMÉ, décision pilote : un fichier RÉGULIER
recréé par un tiers sur un inode recyclé reste INDISCERNABLE par `(dev, ino)`.
`test_un_regulier_de_meme_inode_reste_le_meme_fichier_residu_nomme` l'ÉCRIT
comme une borne, pas comme une garantie.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: Le paquet `cadre` que `vendor_paths` désigne (vendor d'abord, puis `src/cadre`), chargé PAR CHEMIN sans
#: toucher `sys.path` (patron v3prep, S-01M5BXT85VP4JBBMXVXR9STP5F).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_store_identite_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import store  # noqa: E402
from cadre.workspace import Identite  # noqa: E402

#: Un chemin ABSOLU sur tout hôte (`_uri_absolue` refuse un relatif) ; rien n'y
#: est créé ni lu.
CHEMIN = Path(tempfile.gettempdir()) / "t1179" / "store.db"
REL = "store.db"
DEV, INO = 41, 1179


def _identite(*, est_lien: bool = False, est_regulier: bool = True,
              nliens: int = 1, ino: int = INO) -> Identite:
    return Identite(chemin=CHEMIN, dev=DEV, ino=ino, est_lien=est_lien,
                    est_regulier=est_regulier, nliens=nliens)


#: Le store tel qu'il naît exclusif : régulier, un seul lien physique.
STORE = _identite()

#: Des NON-réguliers qui ont repris le `(dev, ino)` du store. Le répertoire est
#: le cas mesuré de S-00004110 (`st_nlink=2`, comme tout répertoire vide) ; le
#: tube garde `nliens=1` — sur la base il passait pour « le même fichier » nu.
NON_REGULIERS_RECYCLES = {
    "répertoire": _identite(est_regulier=False, nliens=2),
    "tube": _identite(est_regulier=False, nliens=1),
}

#: Un lien symbolique tel que `lstat` le rend : ni régulier, ses propres liens.
LIEN = _identite(est_lien=True, est_regulier=False)

RESTE = "le fichier vide créé reste en place"
REMPLACE = "le fichier vide créé a été retiré ou remplacé par un tiers"


class DesigneEncoreTests(unittest.TestCase):
    def test_un_non_regulier_qui_reprend_l_inode_ne_designe_pas_le_store(self):
        for nom, apres in NON_REGULIERS_RECYCLES.items():
            with self.subTest(nom=nom):
                self.assertEqual((apres.dev, apres.ino), (STORE.dev, STORE.ino),
                                 "banc non armé : l'inode n'est pas recyclé")
                self.assertFalse(store._designe_encore(STORE, apres))

    def test_le_meme_fichier_regulier_designe_encore(self):
        """Témoin NON VIDE : l'aide sait dire Vrai, nliens changé ou non."""
        self.assertTrue(store._designe_encore(STORE, STORE))
        self.assertTrue(store._designe_encore(STORE, _identite(nliens=2)))

    def test_un_lien_rien_ou_un_autre_inode_ne_designent_pas_le_store(self):
        self.assertFalse(store._designe_encore(STORE, LIEN))
        self.assertFalse(store._designe_encore(STORE, None))
        self.assertFalse(store._designe_encore(STORE, _identite(ino=INO + 1)))


class CeQueLeNomDesigneTests(unittest.TestCase):
    def test_un_non_regulier_qui_reprend_l_inode_est_un_autre_fichier(self):
        for nom, apres in NON_REGULIERS_RECYCLES.items():
            with self.subTest(nom=nom):
                self.assertEqual(store._ce_que_le_nom_designe(STORE, apres),
                                 "un autre fichier")

    def test_un_regulier_de_meme_inode_reste_le_meme_fichier_residu_nomme(self):
        """RÉSIDU NOMMÉ : un régulier de même `(dev, ino)` passe pour le même
        fichier — un tiers qui le recrée sur un inode recyclé n'est pas vu."""
        self.assertEqual(
            store._ce_que_le_nom_designe(STORE, _identite(nliens=2)),
            "le même fichier, qui porte désormais 2 liens physiques")
        self.assertEqual(store._ce_que_le_nom_designe(STORE, STORE),
                         "le même fichier")

    def test_un_lien_symbolique_et_rien(self):
        self.assertEqual(store._ce_que_le_nom_designe(STORE, LIEN),
                         "un lien symbolique")
        self.assertEqual(store._ce_que_le_nom_designe(STORE, None), "rien")


class CeQuiResteTests(unittest.TestCase):
    def test_un_non_regulier_recycle_ne_dit_pas_reste_en_place(self):
        for nom, apres in NON_REGULIERS_RECYCLES.items():
            with self.subTest(nom=nom):
                reste = store._ce_qui_reste(True, STORE, apres)
                self.assertNotIn("reste en place", reste)
                self.assertIn(REMPLACE, reste)

    def test_le_meme_fichier_reste_en_place(self):
        """Témoin NON VIDE : l'aide sait dire « reste en place »."""
        self.assertIn(RESTE, store._ce_qui_reste(True, STORE, STORE))

    def test_rien_ou_un_lien_et_la_verification(self):
        self.assertIn(REMPLACE, store._ce_qui_reste(True, STORE, None))
        self.assertIn(REMPLACE, store._ce_qui_reste(True, STORE, LIEN))
        self.assertEqual(store._ce_qui_reste(False, STORE, None), "rien écrit")


class _WorkspaceSimule:
    """Le `Workspace` reçu, réduit aux deux méthodes qu'`ouvrir_sans_suivre`
    appelle : le store naît exclusif (`STORE`), puis le nom désigne `apres`."""

    def __init__(self, apres):
        self.apres = apres
        self.appels: list[tuple[str, str]] = []

    def creer_fichier_exclusif(self, rel, *, mode):
        self.appels.append(("creer", rel))
        return STORE

    def identite(self, rel):
        self.appels.append(("identite", rel))
        return self.apres


def _refuse(uri):
    raise sqlite3.OperationalError("unable to open database file")


class OuvrirSansSuivreTests(unittest.TestCase):
    """Le chemin réel : SQLite refuse d'ouvrir, et le refus dit ce que le nom
    désigne — ici sans dépendre du noyau pour recycler l'inode."""

    def _ouvrir(self, apres):
        ws = _WorkspaceSimule(apres)
        return ws, lambda: store.ouvrir_sans_suivre(ws, REL, creer=True,
                                                    connecter=_refuse)

    def test_un_non_regulier_recycle_est_un_refus_d_emplacement(self):
        for nom, apres in NON_REGULIERS_RECYCLES.items():
            with self.subTest(nom=nom):
                ws, ouvrir = self._ouvrir(apres)
                with self.assertRaises(store.EmplacementRefuse) as ctx:
                    ouvrir()
                message = str(ctx.exception)
                self.assertEqual(ws.appels, [("creer", REL), ("identite", REL)],
                                 "banc non armé")
                self.assertIsInstance(ctx.exception.__cause__, sqlite3.OperationalError)
                self.assertIn("le nom désigne un autre fichier — ", message)
                self.assertNotIn("reste en place", message)
                self.assertIn(REMPLACE, message)

    def test_le_meme_fichier_est_une_panne_d_acces(self):
        """Témoin NON VIDE : le même chemin dit « le même fichier » et « reste
        en place » quand le nom désigne encore le store."""
        _, ouvrir = self._ouvrir(STORE)
        with self.assertRaises(store.OuvertureImpossible) as ctx:
            ouvrir()
        message = str(ctx.exception)
        self.assertIn("le nom désigne le même fichier — ", message)
        self.assertIn(RESTE, message)


if __name__ == "__main__":
    unittest.main()
