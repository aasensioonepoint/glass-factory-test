"""Témoin B de T-01M54GECXDCHQF3R18H995B76C (lot T-01M5X914FD) : UN SYM-ID PORTÉ
PAR DEUX LIGNES VIVANTES APRÈS UNE FUSION NE PERD PLUS L'UNE D'ELLES EN SILENCE.

Mesure M5 de l'annexe, rejouée sur un dépôt temporaire : la branche B crée un
module NEUF `zz/` (un shard `SYMBOLS_zz.md` que B seule a créé, que git prend
sans pilote) pendant que A ajoute ta1/ta2 dans `scripts/`. Les deux côtés
allouent les MÊMES ids. Résolution « nous » partout, sauf ce que B seule a
créé ; puis `--if-stale`. Avant le correctif, `load_existing` faisait
`by_id[sym["id"]] = sym` : le shard `zz` lu en dernier écrasait ta1/ta2, qui
QUITTAIENT l'index, et `--stale-check` répondait `INDEX CURRENT`.

Ce qui est asserté : ta1/ta2 (ligne d'un fichier cité par la ToC) gardent leurs
ids ; zb1/zb2 reçoivent des ids AU-DESSUS du plafond et sont nommés sur stderr ;
le canal `perdants` porte les perdantes jusqu'à `reconcile`, qui les rescanne
même quand leur fichier est HORS du scope (un canal coupé => zb* disparaissent).

Backend de repli forcé (`ctags_binary` → None) : le témoin est le même sur un
poste avec universal-ctags et sur la CI ubuntu sans ctags.
"""
import contextlib
import io
import unittest
from unittest import mock

import build_index as bi
from test_build_index_atomic import _Case

TA = "scripts/t_a.py"
ZB = "zz/z_b.py"
SEUIL = ("--threshold", "1")  # force le découpage en shards, comme le kit
SHARD_ZZ = f"{bi.STATE_INDEX_REL}/SYMBOLS_zz.md"


class CollisionApresFusionTests(_Case):

    def setUp(self):
        super().setUp()
        repli = mock.patch.object(bi, "ctags_binary", return_value=None)
        repli.start()
        self.addCleanup(repli.stop)

    def _par_nom(self) -> dict:
        return {(path, name): i for (path, name, _kind), i in self.ids().items()}

    def _fusion_m5(self):
        """Construit l'état M5 ; rend (ids de « nous », ids de B, plafond)."""
        self.git_init()
        self.build(*SEUIL)
        self.commit("base index")
        self._git("checkout", "-qb", "b")
        self.write_sources({ZB: "def zb1():\n    return 1\n\n\ndef zb2():\n    return 2\n"})
        self.commit("zz")
        self.build(*SEUIL)
        self.commit("index b")
        cote_b = self._par_nom()
        self._git("checkout", "-q", "-")
        self.write_sources({TA: "def ta1():\n    return 1\n\n\ndef ta2():\n    return 2\n"})
        self.commit("ta")
        self.build(*SEUIL)
        self.commit("index a")
        nous = self._par_nom()
        # Prémisse de M5 : les deux côtés ont alloué les MÊMES ids.
        self.assertEqual({nous[(TA, "ta1")], nous[(TA, "ta2")]},
                         {cote_b[(ZB, "zb1")], cote_b[(ZB, "zb2")]},
                         "pas de collision d'ids : le scénario M5 n'est pas reproduit")
        # Résolution « nous » : tout vient de A, sauf ce que B seule a créé.
        self._git("checkout", "b", "--", ZB, SHARD_ZZ)
        self.commit("fusion nous")
        return nous, cote_b, max([*nous.values(), *cote_b.values()])

    def test_m5_ta_garde_ses_ids_zb_recoit_des_ids_neufs_nommes(self):
        nous, _cote_b, plafond = self._fusion_m5()
        self.build("--if-stale", *SEUIL)
        err = self.derniere_err
        apres = self._par_nom()
        for nom in ("ta1", "ta2"):
            self.assertIn((TA, nom), apres, f"{TA} absent : {nom} perdu en silence (M5)")
            self.assertEqual(nous[(TA, nom)], apres[(TA, nom)],
                             f"{nom} a perdu l'identité de « nous »")
        for nom in ("zb1", "zb2"):
            self.assertIn((ZB, nom), apres, f"{ZB} {nom} absent de l'index")
            self.assertGreater(apres[(ZB, nom)], plafond,
                               f"{nom} n'a pas reçu un id au-dessus du plafond")
            self.assertIn(f"collision — {ZB} {nom}", err, f"{nom} n'est pas nommé sur stderr")
        self.assertIn("INDEX CURRENT", self.build("--stale-check", *SEUIL))

    def test_canal_perdants_porte_les_perdantes_jusqu_a_reconcile(self):
        _nous, cote_b, plafond = self._fusion_m5()
        perdants = []
        _by_key, by_id, _max = bi.load_existing(self.root, perdants)
        self.assertEqual({(ZB, "zb1"), (ZB, "zb2")}, {(p["path"], p["name"]) for p in perdants})
        self.assertTrue(all(by_id[p["id"]]["path"] == TA for p in perdants))
        self.assertEqual(3, len(bi.load_existing(self.root)), "signature des appelants changée")
        # Scope VIDE : seul le canal `perdants` peut faire rescanner zz/z_b.py.
        symbols, delta = bi.reconcile(self.root, [], None, bi.CTAGS_KINDS)
        vivants = {(s["path"], s["name"]): s["id"] for s in symbols if not s.get("deleted")}
        for nom in ("zb1", "zb2"):
            self.assertIn((ZB, nom), vivants, f"canal coupé : {nom} perdu hors scope")
            self.assertGreater(vivants[(ZB, nom)], plafond)
            self.assertIn(vivants[(ZB, nom)], delta["added"])
        self.assertNotIn(cote_b[(ZB, "zb1")], {vivants[(ZB, n)] for n in ("zb1", "zb2")})

    def test_vivante_l_emporte_sur_une_tombstone_lue_apres_elle(self):
        """Revue de clôture (règle `load_existing` : vivante > tombstone, à citation ÉGALE) : deux shards cités ;
        une tombstone d'identité autre, lue APRÈS (`SYMBOLS_zz.md`), sur l'id de ta1 ⇒ ta1 garde l'id, la tombstone
        est écartée (« dropped », jamais « rescanned »), rien au canal `perdants`.
        MUTANT : `keep = cited_id[sym["id"]] and not cited` ⇒ la tombstone écrase ta1, rouge."""
        self.git_init()
        self.write_sources({TA: "def ta1():\n    return 1\n", ZB: "def zb1():\n    return 1\n"})
        self.commit("sources")
        self.build(*SEUIL)
        n = self._par_nom()[(TA, "ta1")]
        shard = self.root / SHARD_ZZ
        self.assertIn("SYMBOLS_zz.md", (self.root / bi.STATE_INDEX_REL / bi.MAIN_NAME).read_text(encoding="utf-8"),
                      "prémisse : le shard zz est cité par la ToC")
        shard.write_text(shard.read_text(encoding="utf-8") + f"{bi.sid(n)}  DELETED  fantome  function\n",
                         encoding="utf-8")
        perdants, err = [], io.StringIO()
        with contextlib.redirect_stderr(err):
            _by_key, by_id, _max = bi.load_existing(self.root, perdants)
        self.assertEqual((TA, "ta1", False), (by_id[n].get("path"), by_id[n]["name"], by_id[n]["deleted"]))
        self.assertEqual([], perdants)
        self.assertIn(f"{bi.sid(n)} collision — DELETED fantome (function) loses the id, dropped", err.getvalue())


if __name__ == "__main__":
    unittest.main()
