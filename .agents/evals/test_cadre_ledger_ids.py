#!/usr/bin/env python3
"""BANC DE L'ULID STDLIB — longueur (26), tri temporel, unicité. Étape C, T-012.

Aucun paquet ULID (`dependencies` VIDE = contrat stdlib seule) : ces témoins
prouvent que l'implémentation `time` + `secrets` tient les trois propriétés que
la spec attend d'un identifiant globalement stable.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# Le paquet `cadre` de CETTE racine, où qu'il vive, chargé par chemin (vendor_paths) :
# aucun `src` inséré en tête de sys.path (T-01M5BXTPQE, lot H).
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_ledger_ids_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")

from cadre.ledger import ids  # noqa: E402


class UlidTests(unittest.TestCase):
    def test_longueur_26(self):
        u = ids.nouvel_ulid()
        self.assertEqual(len(u), 26, "ULID de longueur inattendue : " + repr(u))
        self.assertTrue(
            set(u) <= set(ids.ALPHABET),
            "caractère hors alphabet Crockford : " + repr(u),
        )

    def test_tri_lexicographique_croissant_dans_le_temps(self):
        # Horodatages STRICTEMENT croissants → préfixes temps STRICTEMENT
        # croissants, donc ULID triés lexicographiquement.
        ms = [1_000, 1_000_000, 2_000_000_000, 900_000_000_000]
        us = [ids.nouvel_ulid(m) for m in ms]
        self.assertEqual(us, sorted(us),
                         "l'ordre lexicographique des ULID ne suit pas le temps")
        # UTILISABLE : deux horodatages distincts rendent deux préfixes distincts
        # (sinon le tri serait porté par l'aléa, pas par le temps).
        prefixes = {u[:10] for u in us}
        self.assertEqual(len(prefixes), len(ms),
                         "deux horodatages distincts rendent le même préfixe temps")

    def test_unicite_sur_un_tirage_non_vide(self):
        n = 5_000
        tirage = {ids.nouvel_ulid() for _ in range(n)}
        self.assertGreater(n, 0, "tirage vide — le banc ne mesure rien")
        self.assertEqual(len(tirage), n, "collision d'ULID sur un tirage de " + str(n))


#: Milliseconde FIGÉE du banc — HORS de toute horloge réelle (2020-09-13), pour
#: ne jamais rencontrer l'état laissé par un autre banc du même processus.
_MS_FIGEE = 1_600_000_000_000
_MAX_ALEA = (1 << 80) - 1


def _tirage_decroissant(depuis: int = 1 << 79):
    """Aléa DÉCROISSANT à greffer sur `secrets.randbits` : sur l'ULID non
    monotone (aléa neuf à chaque appel), deux ULID de même ms sortent alors
    DÉCROISSANTS de façon DÉTERMINISTE — sans la greffe, l'ancien code ne rougit
    qu'une fois sur deux. Part de 2^79 : parti de 2^80-1, le « +1 » du code
    monotone déclencherait légitimement le dépassement."""
    return iter(range(depuis, -1, -1))


class UlidMonotoneTests(unittest.TestCase):
    """T-00000689 — monotonie DANS la milliseconde, par copie chargée du module.

    Huit témoins : (a) ms figée, 1 000 ULID strictement croissants ; (b) même ms
    EXPLICITE ; (c) dépassement → OverflowError ; (d) autre pid → tirage neuf ;
    (e) recul d'horloge → préfixe VRAI et tirage neuf ; (f) même pid, même ms →
    aléa + 1 ; (g) le verrou est pris à chaque émission ; (h) l'horloge est lue
    SOUS le verrou.
    """

    def setUp(self):
        # État PARTAGÉ du module remis à zéro pour CHAQUE témoin, restauré après :
        # aucun ordre d'exécution ne fait fuiter (pid, ms, aléa) d'un témoin à
        # l'autre ni vers un autre banc. `create=True` : sur l'ancien `ids.py`
        # (sans `_etat`) les témoins (a)/(b) doivent rougir PAR ASSERTION, pas
        # mourir ici en AttributeError.
        greffe = mock.patch.object(ids, "_etat", None, create=True)
        greffe.start()
        self.addCleanup(greffe.stop)

    def test_meme_ms_figee_strictement_croissants(self):
        n = 1_000
        decroissant = _tirage_decroissant()

        def tirage(k):
            self.assertEqual(k, 80, "largeur d'aléa inattendue")
            return next(decroissant)

        with mock.patch.object(ids.time, "time", return_value=_MS_FIGEE / 1000), \
                mock.patch.object(ids.secrets, "randbits", side_effect=tirage):
            us = [ids.nouvel_ulid() for _ in range(n)]
        prefixe = ids._encoder(_MS_FIGEE, ids._CAR_TEMPS)
        self.assertEqual({u[:10] for u in us}, {prefixe}, "ms non figée")
        self.assertEqual(len(set(us)), n, "collision d'ULID dans la même ms")
        self.assertTrue(all(a < b for a, b in zip(us, us[1:])),
                        "ULID non STRICTEMENT croissants dans une même ms")

    def test_meme_ms_explicite_croissant_aussi(self):
        # Greffe EXPLICITE du tirage décroissant (réserve S-00002262) : sans elle
        # l'ancien code ne rougirait qu'une fois sur deux.
        decroissant = _tirage_decroissant()
        with mock.patch.object(ids.secrets, "randbits",
                               side_effect=lambda k: next(decroissant)):
            a = ids.nouvel_ulid(_MS_FIGEE + 7)
            b = ids.nouvel_ulid(_MS_FIGEE + 7)
        self.assertEqual(a[:10], b[:10], "ms explicite non partagée")
        self.assertLess(a, b, "deux ULID de même ms explicite non croissants")

    def test_depassement_leve_au_lieu_de_reboucler(self):
        # À la borne, l'aléa maximal est encore ÉMIS ; un cran au-delà LÈVE —
        # jamais un rebouclage silencieux (2^80 tronqué = 000…0, ULID PLUS PETIT).
        etat, alea = ids._suivant((1, 5, _MAX_ALEA - 1), 1, 5, lambda: 0)
        self.assertEqual(alea, _MAX_ALEA)
        with self.assertRaises(OverflowError):
            ids._suivant(etat, 1, 5, lambda: 0)

    def test_autre_pid_tire_neuf(self):
        etat, alea = ids._suivant((1, 5, 7), 2, 5, lambda: 42)
        self.assertEqual((etat, alea), ((2, 5, 42), 42),
                         "un fils de fork reprendrait l'aléa du père : collision")

    def test_recul_d_horloge_prefixe_vrai_et_tirage_neuf(self):
        # Réserve S-00002262 : une ms ANTÉRIEURE à la dernière émise, jouée via
        # `nouvel_ulid`. Le préfixe temps est la ms DONNÉE — une pince
        # `max(ms, dernier_ms)` rougit ici — et l'aléa est un tirage NEUF, pas
        # « précédent + 1 » — retirer `and etat[1] == ms` rougit ici.
        decroissant = _tirage_decroissant()
        with mock.patch.object(ids.secrets, "randbits",
                               side_effect=lambda k: next(decroissant)):
            ids.nouvel_ulid(_MS_FIGEE)
            recule = ids.nouvel_ulid(_MS_FIGEE - 1)
        self.assertEqual(recule[:10], ids._encoder(_MS_FIGEE - 1, ids._CAR_TEMPS),
                         "le préfixe temps n'est pas la ms donnée (pince ?)")
        self.assertEqual(recule[10:], ids._encoder((1 << 79) - 1, ids._CAR_ALEA),
                         "l'aléa après recul d'horloge n'est pas un tirage neuf")
        # Même règle vers l'AVANT : autre ms → tirage neuf.
        _etat, alea = ids._suivant((1, 5, 7), 1, 6, lambda: 42)
        self.assertEqual(alea, 42)

    def test_meme_pid_meme_ms_incremente(self):
        tirer = mock.Mock(return_value=42)
        etat, alea = ids._suivant((1, 5, 7), 1, 5, tirer)
        self.assertEqual((etat, alea), ((1, 5, 8), 8))
        tirer.assert_not_called()

    def test_le_verrou_est_pris_a_chaque_emission(self):
        entrees = []

        class Espion:
            def __enter__(self):
                entrees.append("in")

            def __exit__(self, *exc):
                return False

        with mock.patch.object(ids, "_VERROU", Espion()):
            for _ in range(3):
                ids.nouvel_ulid()
        self.assertEqual(len(entrees), 3, "émission hors verrou")

    def test_horloge_lue_sous_verrou(self):
        # Binôme de clôture (BLOQUANT, mesuré) : l'horloge lue AVANT le verrou
        # laisse un thread préempté entre la lecture et `with _VERROU:` émettre,
        # à la même ms, un ULID PLUS PETIT qu'un ULID déjà émis. Le verrou est un
        # VRAI `threading.Lock`, pour que `locked()` dise l'état réel au moment
        # où `time.time` est appelé.
        verrou = threading.Lock()

        def horloge():
            self.assertTrue(verrou.locked(), "horloge lue HORS verrou")
            return _MS_FIGEE / 1000

        espion = mock.Mock(side_effect=horloge)
        with mock.patch.object(ids, "_VERROU", verrou), \
                mock.patch.object(ids.time, "time", espion):
            u = ids.nouvel_ulid()
        # NON-VACUITÉ : l'horloge a bien été consultée (une ms explicite ou un
        # chemin qui ne lit plus `time.time` rendrait l'assertion muette).
        espion.assert_called_once()
        self.assertEqual(u[:10], ids._encoder(_MS_FIGEE, ids._CAR_TEMPS),
                         "la ms émise n'est pas celle lue sous le verrou")


if __name__ == "__main__":
    unittest.main()
