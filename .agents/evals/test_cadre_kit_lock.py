"""`.agents/kit.lock` et `cadre.kitlock` — les deux opérandes du lockstep.

Ce banc prouve les OPÉRANDES, jamais la comparaison : la règle qui confronte le
fichier au noyau installé n'est pas livrée. Il tient quatre propriétés.

* Le fichier commité est EXACTEMENT le rendu du noyau (T1) — tout bump de
  `__version__` ou de `__version_contrat__` exige de le régénérer, et c'est ce
  banc qui le rappelle.
* La version de contrat du noyau égale celle du verrou `contract.lock.json`
  (T2) — c'est l'UNIQUE témoin de parité entre la constante et le verrou.
* L'écriture est idempotente et la lecture fait l'aller-retour (T3, T4).
* Le refus n'est pas dégradé : format inconnu, clé manquante, clé inconnue,
  version de contrat non SemVer, version de kit vide lèvent `KitLockIllisible`,
  jamais une valeur par défaut (T5) ; une lecture impossible aussi, seul un
  fichier ABSENT rend `None` ; et `ecrire` ne pose jamais ce que `parser`
  refuserait.

T1, T2 et la parité avec `pyproject.toml` sont KIT-ONLY : chez un adoptant, le
fichier porte les valeurs que `cadre init` y aura réécrites, et ni le verrou ni
le manifeste ne l'engagent. Les autres voyagent : elles n'écrivent que dans un
répertoire temporaire, par `Workspace`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# `cadre` là où la règle de `vendor_paths` le désigne (vendor d'abord, `src` sinon),
# chargé par chemin : aucune entrée neuve en tête de `sys.path`.
_SPEC_VP = importlib.util.spec_from_file_location(
    "_kit_lock_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
VENDOR = importlib.util.module_from_spec(_SPEC_VP)
sys.modules[_SPEC_VP.name] = VENDOR
_SPEC_VP.loader.exec_module(VENDOR)
VENDOR.charger_paquet(ROOT, "cadre")

import cadre  # noqa: E402
from cadre import kitlock  # noqa: E402
from cadre.workspace import Workspace  # noqa: E402

# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT) ;
# son absence EST le signal « arbre adoptant », où T1 et T2 sautent.
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()


class KitLockTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.atelier = Workspace(self._tmp.name)

    def test_cadre_charge_est_celui_que_vendor_paths_designe(self):
        """Arbre « les deux » : le paquet vendor, jamais `src/cadre` mis en tête."""
        attendu, _origine = VENDOR.verifier_charge(ROOT, "cadre")
        self.assertEqual(attendu, Path(kitlock.__file__).resolve().parent)

    # -- KIT-ONLY ----------------------------------------------------------

    @unittest.skipUnless(EST_LE_KIT, "adopting-tree")
    def test_le_fichier_commite_est_exactement_le_rendu_du_noyau(self):
        commite = Workspace(ROOT).read_bytes(kitlock.RELATIF)
        attendu = kitlock.rendre(kitlock.attendu()).encode("utf-8")
        self.assertEqual(
            commite, attendu,
            f"{kitlock.RELATIF} ne correspond plus au noyau : régénère-le par "
            "`kitlock.ecrire(Workspace(<racine>), kitlock.attendu())` après tout "
            "bump de `__version__` ou de `__version_contrat__`.",
        )

    @unittest.skipUnless(EST_LE_KIT, "adopting-tree")
    def test_la_version_de_contrat_du_noyau_egale_celle_du_verrou(self):
        verrou = json.loads(Workspace(ROOT).read_text("contract.lock.json"))
        self.assertEqual(
            cadre.__version_contrat__, verrou["version_contrat"],
            "`cadre.__version_contrat__` et le champ `version_contrat` de "
            "`contract.lock.json` divergent : l'un a bougé sans l'autre.",
        )

    @unittest.skipUnless(EST_LE_KIT, "adopting-tree")
    def test_la_version_du_noyau_egale_celle_de_pyproject(self):
        manifeste = tomllib.loads(Workspace(ROOT).read_text("pyproject.toml"))
        self.assertEqual(
            cadre.__version__, manifeste["project"]["version"],
            "`cadre.__version__` et `version` de `pyproject.toml` divergent : "
            "`version_kit` du fichier commité ne dirait plus la version du "
            "paquet construit.",
        )

    # -- voyageuses --------------------------------------------------------

    def test_ecrire_deux_fois_rend_des_octets_identiques(self):
        lock = kitlock.attendu()
        kitlock.ecrire(self.atelier, lock)
        premier = self.atelier.read_bytes(kitlock.RELATIF)
        kitlock.ecrire(self.atelier, lock)
        second = self.atelier.read_bytes(kitlock.RELATIF)
        self.assertEqual(premier, second, "deux écritures des mêmes valeurs divergent")
        # L'aller-retour ferme la porte à un champ ajouté par `rendre` qui serait
        # constant d'une écriture à l'autre : `parser` refuse toute clé inconnue.
        self.assertEqual(kitlock.parser(second.decode("utf-8")), lock)

    def test_lire_rend_None_sans_fichier_puis_le_lock_ecrit(self):
        self.assertIsNone(kitlock.lire(self.atelier))
        lock = kitlock.KitLock(version_kit="9.9.9", version_contrat="0.1.0")
        kitlock.ecrire(self.atelier, lock)
        self.assertEqual(kitlock.lire(self.atelier), lock)

    def test_un_format_inconnu_une_cle_manquante_ou_une_cle_inconnue_est_refuse(self):
        valide = {"version_contrat": "0.1.0", "version_format": 1,
                  "version_kit": "0.1.0.dev0"}
        # Non-vacuité : l'objet de référence est accepté, donc chaque refus
        # ci-dessous tient à la seule altération qu'il porte.
        self.assertEqual(kitlock.parser(json.dumps(valide)),
                         kitlock.KitLock("0.1.0.dev0", "0.1.0", 1))
        sans_version_kit = {k: v for k, v in valide.items() if k != "version_kit"}
        illisible, inconnu = kitlock.KitLockIllisible, kitlock.KitLockFormatInconnu
        cas = {
            "format inconnu": ({**valide, "version_format": 2}, inconnu),
            # Un format 2 RÉALISTE porte une clé que le format 1 ignore : il doit
            # sortir « format inconnu », jamais « clé inconnue » — le premier
            # dit « mets le noyau à jour », le second « répare le fichier ».
            "format 2 réaliste avec 4e clé":
                ({**valide, "version_format": 2, "hotes": []}, inconnu),
            "clé manquante": (sans_version_kit, illisible),
            "clé inconnue": ({**valide, "hotes": []}, illisible),
            "version_contrat vide": ({**valide, "version_contrat": ""}, illisible),
            "version_contrat non SemVer":
                ({**valide, "version_contrat": "banana"}, illisible),
            "version_kit vide": ({**valide, "version_kit": ""}, illisible),
        }
        for nom, (objet, attendue) in cas.items():
            with self.subTest(cas=nom):
                with self.assertRaises(attendue) as ctx:
                    kitlock.parser(json.dumps(objet))
                if attendue is inconnu:
                    # Le remède nomme la distribution et la forme épinglée (T-00000796).
                    self.assertIn("cadre-kit", str(ctx.exception))
                    self.assertIn("README du kit, § Install the core", str(ctx.exception))

    def test_lire_refuse_un_contenu_non_utf8_ou_un_repertoire(self):
        # Seul un fichier ABSENT rend `None` : tout autre échec de lecture est
        # un refus, jamais une exception brute ni un « pas de verrou ».
        self.atelier.write_bytes(kitlock.RELATIF, b"\xff\xfe{\x00")
        with self.subTest(cas="contenu non UTF-8"):
            with self.assertRaises(kitlock.KitLockIllisible):
                kitlock.lire(self.atelier)
        autre = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(autre.cleanup)
        atelier = Workspace(autre.name)
        atelier.write_bytes(kitlock.RELATIF + "/dedans", b"")
        with self.subTest(cas="répertoire"):
            with self.assertRaises(kitlock.KitLockIllisible):
                kitlock.lire(atelier)

    def test_lire_refuse_un_lien_qui_sort_de_la_racine(self):
        dehors = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dehors.cleanup)
        cible = Workspace(dehors.name).write_text(
            "kit.lock", kitlock.rendre(kitlock.attendu()))
        lien = self.atelier.racine / ".agents" / "kit.lock"
        lien.parent.mkdir(parents=True)
        try:
            os.symlink(cible, lien)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"lien symbolique impossible ici : {exc}")
        with self.assertRaises(kitlock.KitLockIllisible):
            kitlock.lire(self.atelier)

    def test_ecrire_refuse_un_lock_mal_forme_sans_rien_ecrire(self):
        mal_forme = kitlock.KitLock(version_kit="0.1.0.dev0", version_contrat="banana")
        with self.assertRaises(kitlock.KitLockIllisible):
            kitlock.ecrire(self.atelier, mal_forme)
        self.assertFalse(self.atelier.exists(kitlock.RELATIF),
                         "`ecrire` a posé un fichier que `parser` refuse")

    def test_attendu_porte_les_deux_versions_du_paquet(self):
        lock = kitlock.attendu()
        self.assertEqual(lock.version_kit, cadre.__version__)
        self.assertEqual(lock.version_contrat, cadre.__version_contrat__)
        self.assertEqual(lock.version_format, kitlock.VERSION_FORMAT)
        self.assertEqual(kitlock.VERSION_FORMAT, 1)


if __name__ == "__main__":
    unittest.main()
