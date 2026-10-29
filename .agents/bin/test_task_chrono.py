#!/usr/bin/env python3
"""Témoin du moteur `task_chrono.py` (T-01M5HST80E30DFMV3S7WM68Q7N, lot B) : horloge injectée,
tailles distinctes, historique vide, double fin, lots parallèles, reprise idempotente, écart total
rendu seulement sur un périmètre mesuré. Tout se joue sous un dossier jetable hors git."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ICI = Path(__file__).resolve().parent
_NOM = "_banc_task_chrono"


def charger():
    spec = importlib.util.spec_from_file_location(_NOM, ICI / "task_chrono.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NOM] = module
    spec.loader.exec_module(module)
    return module


tc = charger()
TAILLE_3 = {"fichiers": 3, "lots": 1}
TAILLE_5 = {"fichiers": 5, "lots": 1}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="task-chrono-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def pas(self, tid, etape, phase, ts, **kw):
        return tc.etape(self.base, tid, etape, phase, now_ms=ts, **kw)

    def fermer(self, tid, ts):
        """Le jalon `done` : la seule fin qui clôt un cycle."""
        self.pas(tid, "done", "begin", ts)
        return self.pas(tid, "done", "end", ts)

    def cycle_clos(self, tid, etape, duree_s, taille, t0=0):
        """Un cycle CLOS de `tid` : `etape` de `duree_s`, la revue de clôture, puis le `done`."""
        self.pas(tid, etape, "begin", t0, taille=taille)
        self.pas(tid, etape, "end", t0 + duree_s * 1000)
        self.pas(tid, "cloture", "begin", t0 + duree_s * 1000)
        self.pas(tid, "cloture", "end", t0 + duree_s * 1000 + 1000)
        self.fermer(tid, t0 + duree_s * 1000 + 1000)


class HorlogeEtJournal(Base):
    def test_horloge_injectee_donne_la_duree_et_les_instants(self):
        self.pas("T-1", "dev", "begin", 1_000, taille=TAILLE_3)
        sortie = self.pas("T-1", "dev", "end", 61_000)
        self.assertIn("fin en 1m00s", sortie)
        lignes = [json.loads(l) for l in tc.chemin_journal(self.base, "T-1").read_text().splitlines()]
        self.assertEqual([l["ts"] for l in lignes if l["ev"] == "etape"], [1_000, 61_000])
        self.assertEqual(tc.bilan(self.base, "T-1", now_ms=99_000)["etapes"][0]["reel_s"], 60)

    def test_begin_idempotent_reprend_le_cycle_ouvert(self):
        self.assertEqual(tc.commencer(self.base, "T-1", 0), (1, True))
        self.assertEqual(tc.commencer(self.base, "T-1", 5), (1, False))
        evs = [json.loads(l)["ev"] for l in tc.chemin_journal(self.base, "T-1").read_text().splitlines()]
        self.assertEqual(evs, ["cycle"])

    def test_cycle_clos_puis_begin_ouvre_le_suivant(self):
        self.cycle_clos("T-1", "dev", 10, TAILLE_3)
        self.assertEqual(tc.commencer(self.base, "T-1", 50_000), (2, True))

    def test_debut_repris_sans_seconde_ligne(self):
        self.pas("T-1", "dev", "begin", 0, taille=TAILLE_3)
        self.assertIn("reprise", self.pas("T-1", "dev", "begin", 9_000, taille=TAILLE_3))
        c = tc.cycles(tc.lire(self.base, "T-1"))[1]
        self.assertEqual(c["etapes"][("dev", "", 1)]["debut"], 0)

    def test_nouvelle_tentative_apres_une_fin(self):
        self.pas("T-1", "correction", "begin", 0)
        self.pas("T-1", "correction", "end", 1_000)
        self.assertIn("tentative 2", self.pas("T-1", "correction", "begin", 2_000))

    def test_double_fin_ignoree_la_premiere_fait_foi(self):
        self.pas("T-1", "dev", "begin", 0)
        self.pas("T-1", "dev", "end", 10_000)
        self.assertIn("déjà finie", self.pas("T-1", "dev", "end", 90_000))
        self.assertEqual(tc.bilan(self.base, "T-1", now_ms=100_000)["etapes"][0]["reel_s"], 10)

    def test_deux_fins_ecrites_en_parallele_la_premiere_fait_foi(self):
        self.pas("T-1", "dev", "begin", 0)
        for ts in (10_000, 90_000):  # deux écrivains concurrents : chacun a vu l'étape ouverte
            tc._noter(self.base, "T-1", {"ev": "etape", "cycle": 1, "etape": "dev", "lot": None, "tentative": 1,
                                         "phase": "end", "ts": ts})
        self.assertEqual(tc.cycles(tc.lire(self.base, "T-1"))[1]["etapes"][("dev", "", 1)]["fin"], 10_000)

    def test_fin_sans_debut_refusee(self):
        with self.assertRaisesRegex(tc.ChronoErreur, "sans début"):
            self.pas("T-1", "porte", "end", 0)

    def test_etape_hors_liste_refusee(self):
        with self.assertRaisesRegex(tc.ChronoErreur, "hors liste fermée"):
            self.pas("T-1", "sieste", "begin", 0)


class Estimation(Base):
    def test_historique_vide_rend_inconnu(self):
        self.assertEqual(tc.estimer(self.base, "dev", TAILLE_3), {"source": "inconnu", "n": 0})

    def test_tailles_distinctes_ne_se_melangent_pas(self):
        self.cycle_clos("T-31", "dev", 100, TAILLE_3)
        self.cycle_clos("T-32", "dev", 300, TAILLE_3)
        self.cycle_clos("T-33", "dev", 900, TAILLE_5)
        est = tc.estimer(self.base, "dev", TAILLE_3)
        self.assertEqual((est["source"], est["n"], est["mediane_s"], est["p90_s"]), ("historique", 2, 200, 300))
        self.assertEqual(tc.estimer(self.base, "dev", TAILLE_5)["mediane_s"], 900)
        self.assertEqual(tc.estimer(self.base, "dev", {"fichiers": 7, "lots": 1})["source"], "inconnu")
        self.assertEqual(tc.estimer(self.base, "dev", {"fichiers": None, "lots": 0})["source"], "inconnu")

    def test_cycle_ouvert_hors_historique(self):
        self.pas("T-3", "dev", "begin", 0, taille=TAILLE_3)
        self.pas("T-3", "dev", "end", 50_000)
        self.assertEqual(tc.estimer(self.base, "dev", TAILLE_3)["source"], "inconnu")

    def test_repli_par_role_puis_attente_humaine(self):
        journal = self.base / ".agents" / "state" / "local" / "agent-chrono.jsonl"
        journal.parent.mkdir(parents=True)
        journal.write_text("".join(json.dumps({"ev": "stop", "aid": f"a{i}", "agent": "dev-multi", "ts": i,
                                               "duration_ms": d}) + "\n" for i, d in enumerate((60_000, 120_000))))
        est = tc.estimer(self.base, "dev", TAILLE_3)
        self.assertEqual((est["source"], est["n"], est["mediane_s"]), ("rôle dev-multi", 2, 90))
        self.assertEqual(tc.estimer(self.base, "attente-pilote", TAILLE_3)["source"], "attente humaine")

    def test_juges_jamais_estimes_par_le_role_exec_critic(self):
        """`juges` est une fenêtre (juges, intégration, documenter) : la médiane d'exec-critic ne l'estime pas."""
        journal = self.base / ".agents" / "state" / "local" / "agent-chrono.jsonl"
        journal.parent.mkdir(parents=True)
        journal.write_text("".join(json.dumps({"ev": "stop", "aid": f"a{i}", "agent": "exec-critic", "ts": i,
                                               "duration_ms": d}) + "\n" for i, d in enumerate((60_000, 120_000))))
        self.assertEqual(tc.estimer(self.base, "juges", TAILLE_3), {"source": "inconnu", "n": 0})

    def test_estimation_figee_au_depart(self):
        self.cycle_clos("T-3", "dev", 100, TAILLE_3)
        self.pas("T-1", "dev", "begin", 0, taille=TAILLE_3)
        self.cycle_clos("T-3", "dev", 900, TAILLE_3, t0=10_000_000)
        e = tc.cycles(tc.lire(self.base, "T-1"))[1]["etapes"][("dev", "", 1)]
        self.assertEqual(e["estimation"]["mediane_s"], 100)


class Totaux(Base):
    def test_lots_paralleles_jamais_additionnes(self):
        for lot in ("T-41", "T-42"):
            self.cycle_clos("T-3" + lot[-1], "dev", 100, TAILLE_3)
        for lot in ("T-41", "T-42"):
            self.pas("T-1", "dev", "begin", 0, lot=lot, taille=TAILLE_3)
        for lot, fin in (("T-41", 100_000), ("T-42", 120_000)):
            self.pas("T-1", "dev", "end", fin, lot=lot)
        self.pas("T-1", "cloture", "begin", 120_000)
        self.pas("T-1", "cloture", "end", 120_000)
        self.fermer("T-1", 120_000)
        b = tc.bilan(self.base, "T-1", now_ms=500_000)
        self.assertEqual(b["total"]["reel_s"], 120)
        self.assertIn("ecart_s", [l for l in b["etapes"] if l["lot"] == "T-42"][0])
        self.assertNotIn("ecart_s", b["total"], "clôture sans estimation : périmètre non mesuré")
        self.assertEqual(b["total"]["estime_s"], 100)

    def test_ecart_total_seulement_si_tout_est_mesure(self):
        self.cycle_clos("T-3", "dev", 100, TAILLE_3)
        self.pas("T-1", "attente-pilote", "begin", 0)
        self.pas("T-1", "attente-pilote", "end", 3_600_000)
        self.pas("T-1", "dev", "begin", 3_600_000, taille=TAILLE_3)
        ouvert = tc.bilan(self.base, "T-1", now_ms=3_650_000)
        self.assertNotIn("ecart_s", ouvert["total"])
        self.assertTrue(any("sans fin" in r for r in ouvert["incomplet"]))
        self.pas("T-1", "dev", "end", 3_730_000)
        self.pas("T-1", "cloture", "begin", 3_730_000, taille=TAILLE_3)
        self.pas("T-1", "cloture", "end", 3_731_000)
        self.fermer("T-1", 3_731_000)
        self.assertNotIn("ecart_s", tc.bilan(self.base, "T-1")["total"], "clôture sans estimation")
        self.cycle_clos("T-3", "cloture", 1, TAILLE_3, t0=9_000_000)
        self.pas("T-2", "dev", "begin", 0, taille=TAILLE_3)
        self.pas("T-2", "dev", "end", 130_000)
        self.pas("T-2", "cloture", "begin", 130_000, taille=TAILLE_3)
        self.pas("T-2", "cloture", "end", 131_000)
        self.assertNotIn("ecart_s", tc.bilan(self.base, "T-2")["total"], "sans le done, le cycle reste ouvert")
        self.fermer("T-2", 131_000)
        b = tc.bilan(self.base, "T-2")
        self.assertEqual(b["total"]["ecart_s"], b["total"]["reel_s"] - b["total"]["estime_s"])
        self.assertIn("écart", tc.rendre(b).splitlines()[-2])

    def test_etape_sans_fin_visible_dans_un_cycle_clos(self):
        self.pas("T-1", "juges", "begin", 0)
        self.pas("T-1", "cloture", "begin", 1_000)
        self.pas("T-1", "cloture", "end", 2_000)
        self.fermer("T-1", 2_000)
        statuts = {l["etape"]: l["statut"] for l in tc.bilan(self.base, "T-1")["etapes"]}
        self.assertEqual(statuts["juges"], "incomplète")


class CycleEntier(Base):
    """B1/M5/M6/m8 de la passe de correction : l'ordre d'AGENTS.md, le cycle courant seul, la colonne
    lot, une ligne hors schéma."""

    ORDRE = ("cadrage", "planification", "dev", "juges", "fusion", "integration", "cloture", "correction", "porte")

    def test_cycle_entier_dans_l_ordre_agents_se_ferme_une_fois(self):
        for i, nom in enumerate(self.ORDRE):  # historique : un cycle clos de même taille par étape
            self.cycle_clos(f"T-3{i}", nom, 10, TAILLE_3, t0=i * 100_000)
        ts = 10_000_000
        for nom in self.ORDRE:
            self.pas("T-1", nom, "begin", ts, taille=TAILLE_3)
            ts += 20_000
            self.pas("T-1", nom, "end", ts)
            self.assertIsNotNone(tc.cycle_ouvert(tc.lire(self.base, "T-1")), f"{nom} ne clôt pas le cycle")
        self.assertIn("fin en 0s", self.fermer("T-1", ts))
        evs = [json.loads(l) for l in tc.chemin_journal(self.base, "T-1").read_text().splitlines()]
        self.assertEqual([e["cycle"] for e in evs if e["ev"] == "cycle"], [1], "un seul cycle, aucun orphelin")
        b = tc.bilan(self.base, "T-1")
        self.assertTrue(b["clos"])
        self.assertEqual(b["total"]["ecart_s"], b["total"]["reel_s"] - b["total"]["estime_s"], b["incomplet"])
        self.assertEqual(b["total"]["estime_s"], 10 * len(self.ORDRE))
        self.assertEqual([l["estimation"]["source"] for l in b["etapes"] if l["etape"] == "done"], ["jalon"])

    def test_fin_sans_debut_au_cycle_courant_ne_ferme_pas_un_cycle_clos(self):
        self.pas("T-1", "juges", "begin", 0)
        self.fermer("T-1", 1_000)
        self.assertEqual(tc.commencer(self.base, "T-1", 2_000), (2, True))
        with self.assertRaisesRegex(tc.ChronoErreur, "sans début"):
            self.pas("T-1", "juges", "end", 3_000)
        c1 = tc.cycles(tc.lire(self.base, "T-1"))[1]
        self.assertNotIn("fin", c1["etapes"][("juges", "", 1)], "le début orphelin du cycle 1 reste sans fin")

    def test_colonne_lot_rend_la_fin_de_l_id(self):
        lots = ("T-01M5JKBXHYY8F374DNSMPPFQ1V", "T-01M5JKBXXY9SXDT8AW3XXB4PQJ")
        for lot in lots:
            self.pas("T-1", "dev", "begin", 0, lot=lot)
        lignes = tc.rendre(tc.bilan(self.base, "T-1", now_ms=1_000)).splitlines()
        for lot in lots:
            self.assertEqual(sum(f" {lot[-8:]} " in l for l in lignes), 1, lignes)
        self.assertFalse(any("T-01M5" in l for l in lignes), lignes)

    def test_ligne_hors_schema_ignoree_jamais_une_trace(self):
        self.pas("T-1", "dev", "begin", 0)
        base = {"ev": "etape", "cycle": 1, "etape": "dev", "tentative": 2, "phase": "begin", "ts": 5}
        for mutee in ({"lot": 7}, {"lot": None, "estimation": "x"}, {"lot": None, "taille": [1]},
                      {"lot": None, "estimation": {"source": "h", "n": 1, "mediane_s": "1", "p90_s": 1}},
                      {"lot": None, "etape": 3}):
            tc._noter(self.base, "T-1", dict(base, **mutee))
        self.assertEqual(len(tc.lire(self.base, "T-1")), 2, "cycle + début valide seulement")
        self.assertIn("CHRONO T-1 cycle 1", tc.rendre(tc.bilan(self.base, "T-1", now_ms=9_000)))


class Actions(Base):
    def data(self):
        return {"tasks": [{"id": "T-5", "writeset": ["a"]},
                          {"id": "T-4", "writeset": ["b", "c"], "fournee": {"parent": "T-5", "lot": "B"}}]}

    def test_taille_de_tache_et_de_lot(self):
        self.assertEqual(tc.taille_de(self.data(), "T-5"), {"fichiers": 3, "lots": 1})
        self.assertEqual(tc.taille_de(self.data(), "T-5", "T-4"), {"fichiers": 2, "lots": 1})
        self.assertEqual(tc.taille_de({"tasks": [{"id": "T-7"}]}, "T-7"), {"fichiers": None, "lots": 0})

    def test_options_validees_par_action(self):
        cas = [("step", {"etape_nom": "dev"}, "--phase"), ("estimate", {}, "--etape"),
               ("begin", {"lot": "T-4"}, "hors de cette action"), ("show", {"phase": "end"}, "hors de cette action"),
               ("show", {"watch": True, "en_json": True}, "ne se combinent pas"), ("zz", {}, "hors estimate")]
        for action, kw, motif in cas:
            with self.subTest(action=action, kw=kw), self.assertRaisesRegex(tc.ChronoErreur, motif):
                tc.executer(self.base, self.data(), "T-5", action, **kw)

    def test_show_watch_s_arrete_au_cycle_clos(self):
        self.pas("T-5", "dev", "begin", 0)
        cadres, sommes = [], []

        def dormir(s):
            sommes.append(s)
            self.pas("T-5", "cloture", "begin", 1_000)
            self.pas("T-5", "cloture", "end", 2_000)
            self.fermer("T-5", 2_000)

        tc.regarder(self.base, "T-5", ecrire=cadres.append, dormir=dormir, max_tours=5, horloge=lambda: 5_000)
        self.assertEqual((len(cadres), sommes), (2, [tc.INTERVALLE_WATCH_S]), "s'arrête au cycle clos, pas au plafond")
        self.assertIn("— clos", cadres[-1])

    def test_show_json_et_sans_cycle(self):
        self.assertIn("aucun cycle", tc.executer(self.base, self.data(), "T-5", "show"))
        tc.executer(self.base, self.data(), "T-5", "begin")
        self.assertEqual(json.loads(tc.executer(self.base, self.data(), "T-5", "show", en_json=True))["cycle"], 1)


class JalonsDuVerbe(Base):
    """T-01M5KKFBCXXEVYR8GJPYFEH3C8 lot A : les jalons que `tasks.py` pose lui-même (W1-W4, W8, W-C3)."""

    def board(self):
        return {"tasks": [{"id": "T-6", "writeset": ["a"], "state": "running"},
                          {"id": "T-5", "writeset": ["p"], "state": "running"},
                          {"id": "T-41", "writeset": ["b"], "state": "running", "fournee": {"parent": "T-5", "lot": "A"}},
                          {"id": "T-42", "writeset": ["c"], "state": "running", "fournee": {"parent": "T-5", "lot": "B"}},
                          {"id": "T-43", "writeset": ["d"], "state": "pending", "fournee": {"parent": "T-5", "lot": "C"}}]}

    def jalons(self, verbe, tids, ts):
        """Le board relu APRÈS le verbe abouti : un `done` y a rendu ses tâches `done`."""
        board = self.board()
        if verbe == "done":
            for t in board["tasks"]:
                if t["id"] in tids:
                    t["state"] = "done"
        return tc.jalons_du_verbe(self.base, board, verbe, tids, now_ms=ts)

    def cles(self, tid, n=1):
        return set(tc.cycles(tc.lire(self.base, tid))[n]["etapes"])

    def test_w1_start_ouvre_le_cycle_et_le_dev_une_seule_fois(self):
        self.assertEqual(self.jalons("start", ["T-6"], 0), [])
        self.jalons("start", ["T-6"], 5_000)  # reprise : la tentative ouverte est réutilisée
        self.assertEqual(self.cles("T-6"), {("dev", "", 1)})
        self.pas("T-6", "dev", "end", 10_000)  # le lanceur la ferme
        self.jalons("start", ["T-6"], 20_000)  # finie, jamais rouverte
        self.assertEqual(self.cles("T-6"), {("dev", "", 1)})
        evs = [json.loads(l) for l in tc.chemin_journal(self.base, "T-6").read_text().splitlines()]
        self.assertEqual([e["cycle"] for e in evs if e["ev"] == "cycle"], [1])
        self.assertEqual(evs[1]["taille"], {"fichiers": 1, "lots": 0})

    def test_w2_wc3_fournee_ouvre_le_dev_des_lots_running_jamais_un_dev_parent(self):
        self.jalons("fournee", ["T-5"], 0)
        self.assertEqual(self.cles("T-5"), {("dev", "T-41", 1), ("dev", "T-42", 1)})
        self.jalons("start", ["T-5"], 1_000)  # reprise du parent : aucun dev sans lot (C3)
        self.assertNotIn(("dev", "", 1), self.cles("T-5"))
        self.jalons("start", ["T-43"], 2_000)  # un lot démarré seul joue au journal du parent
        self.assertIn(("dev", "T-43", 1), self.cles("T-5"))
        self.assertFalse(tc.chemin_journal(self.base, "T-43").exists())

    def test_w4_retour_ferme_le_dev_et_ouvre_la_fusion_une_fois(self):
        self.jalons("fournee", ["T-5"], 0)
        self.jalons("retour", ["T-41"], 60_000)
        c = tc.cycles(tc.lire(self.base, "T-5"))[1]["etapes"]
        self.assertEqual(c[("dev", "T-41", 1)]["fin"], 60_000)
        self.assertNotIn("fin", c[("dev", "T-42", 1)])
        self.assertIn(("fusion", "T-41", 1), c)
        self.jalons("retour", ["T-41"], 90_000)
        self.assertEqual(sum(k[0] == "fusion" for k in self.cles("T-5")), 1)
        self.jalons("retour", ["T-6"], 0)  # sans cycle ouvert : rien d'écrit
        self.assertFalse(tc.chemin_journal(self.base, "T-6").exists())

    def test_w3_done_pose_le_jalon_et_nomme_les_etapes_sans_fin(self):
        self.jalons("fournee", ["T-5"], 0)
        self.jalons("retour", ["T-41"], 60_000)
        self.assertEqual(self.jalons("done", ["T-41"], 70_000), [], "le done d'un lot ne pose rien")
        self.assertFalse(tc.bilan(self.base, "T-5", now_ms=70_000)["clos"])
        avis = self.jalons("done", ["T-5"], 100_000)
        self.assertEqual(len(avis), 1, avis)
        self.assertTrue(avis[0].endswith("clos avec 2 étape(s) sans fin, bornée(s) au done : "
                                         "dev lot T-42, fusion lot T-41"), avis)
        self.assertTrue(tc.bilan(self.base, "T-5")["clos"])

    def test_w3_avis_nomme_cinq_etapes_puis_plus_n(self):
        for i, nom in enumerate(("cadrage", "planification", "dev", "juges", "fusion", "integration", "cloture")):
            self.pas("T-6", nom, "begin", i * 1_000)
        avis = self.jalons("done", ["T-6"], 10_000)[0]
        self.assertIn("7 étape(s) sans fin", avis)
        self.assertTrue(avis.endswith("cadrage, planification, dev, juges, fusion (+2)"), avis)

    def test_w8_done_sans_cycle_dit_et_n_ecrit_rien_puis_jalon_apres_cloture_ignore(self):
        avis = self.jalons("done", ["T-6"], 0)
        self.assertIn("aucun cycle", avis[0])
        self.assertFalse(tc.chemin_journal(self.base, "T-6").exists())
        self.jalons("start", ["T-6"], 0)
        self.pas("T-6", "dev", "end", 1_000)
        self.assertEqual(self.jalons("done", ["T-6"], 2_000), [], "rien sans fin : aucun avis")
        avant = tc.chemin_journal(self.base, "T-6").read_text()
        self.assertEqual(self.jalons("done", ["T-6"], 3_000), [])
        self.assertIn("déjà clos", self.pas("T-6", "done", "begin", 4_000))  # le lanceur, après tasks.py done
        self.assertIn("déjà finie", self.pas("T-6", "done", "end", 4_000))
        self.assertEqual(tc.chemin_journal(self.base, "T-6").read_text(), avant, "aucun cycle fantôme")

    def test_verbe_hors_liste_refuse(self):
        with self.assertRaisesRegex(tc.ChronoErreur, "hors start"):
            self.jalons("stage", ["T-6"], 0)

    def test_f2_done_repris_par_une_fournee_intercalee_ne_clot_pas(self):
        """F2 de la clôture : `done T-5`, puis une `fournee T-5` intercalée avant que le chrono relise le
        board — la tâche y est `running` : le jalon n'est pas posé, le cycle repris reste OUVERT.
        MUTANT qui le rougit : le contrôle de l'état retiré de `jalons_du_verbe`."""
        self.jalons("fournee", ["T-5"], 0)
        avis = tc.jalons_du_verbe(self.base, self.board(), "done", ["T-5"], now_ms=1_000)
        self.assertEqual(avis, ["CHRONO: avis T-5 — reprise depuis le done, jalon non posé"])
        b = tc.bilan(self.base, "T-5", now_ms=2_000)
        self.assertEqual((b["cycle"], b["clos"]), (1, False))
        self.assertNotIn(("done", "", 1), self.cles("T-5"))


class CycleClosBorne(Base):
    """W12 (C1, C11) : un cycle clos ne grandit plus — total ET chaque étape, au done, +1 h, +1 j."""

    def instantanes(self, tid, fin_done):
        return [tc.bilan(self.base, tid, now_ms=fin_done + d) for d in (0, 3_600_000, 86_400_000)]

    def test_w12_cycle_avec_retour(self):
        data = {"tasks": [{"id": "T-6", "writeset": ["a"], "state": "running"}]}
        tc.jalons_du_verbe(self.base, data, "start", ["T-6"], now_ms=0)
        tc.jalons_du_verbe(self.base, data, "retour", ["T-6"], now_ms=600_000)
        data["tasks"][0]["state"] = "done"
        tc.jalons_du_verbe(self.base, data, "done", ["T-6"], now_ms=900_000)
        b0, b1, b2 = self.instantanes("T-6", 900_000)
        self.assertEqual(b0["total"]["reel_s"], 900)
        for b in (b1, b2):
            self.assertEqual(b["total"], b0["total"])
            self.assertEqual([(l["etape"], l["reel_s"]) for l in b["etapes"]],
                             [(l["etape"], l["reel_s"]) for l in b0["etapes"]])
        self.assertEqual({l["etape"]: l["reel_s"] for l in b0["etapes"]}, {"dev": 600, "fusion": 300, "done": 0})
        self.assertEqual(tc.historique(self.base, "fusion", {"fichiers": 1, "lots": 0}), [], "aucune fin fictive")

    def test_w12_directe_sans_retour(self):
        data = {"tasks": [{"id": "T-6", "writeset": ["a"], "state": "running"}]}
        tc.jalons_du_verbe(self.base, data, "start", ["T-6"], now_ms=0)
        data["tasks"][0]["state"] = "done"
        tc.jalons_du_verbe(self.base, data, "done", ["T-6"], now_ms=900_000)
        b0, b1, _b2 = self.instantanes("T-6", 900_000)
        self.assertEqual([(l["etape"], l["statut"], l["reel_s"]) for l in b1["etapes"]],
                         [("dev", "incomplète", 900), ("done", "finie", 0)])
        self.assertEqual(b1["total"], b0["total"])


class LigneDEtat(Base):
    """W6-W7 au moteur : le suffixe de `--statusline`, borné, et '' quand il n'y a rien à dire."""

    def test_w7_pire_cas_tient_dans_la_borne(self):
        self.assertEqual(len(" · ⏱ attente-pilote 99h59/~99h59 +9"), 35)
        for nom in tc.ETAPES:
            for duree in (0, 99 * 3600 + 59 * 60 + 59, 1000 * 86_400):
                for mediane in (None, duree):
                    for autres in (0, 9, 50):
                        s = tc.suffixe(nom, duree, mediane, autres)
                        self.assertLessEqual(len(s), tc.SUFFIXE_MAX, s)
        self.assertTrue(tc.suffixe("dev", 0, None, 50).endswith(" +9"), "N plafonné à 9")
        self.assertEqual(tc.duree_compacte(123 * 3600 + 59 * 60 + 59), "5j")
        self.assertEqual([tc.duree_compacte(s) for s in (59, 60, 3599, 3600, 99 * 3600 + 3540)],
                         ["59s", "1m", "59m", "1h00", "99h59"])

    def test_w6_suffixe_de_l_etape_ouverte_la_plus_recente(self):
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=0), "", "journal absent")
        self.cycle_clos("T-3", "dev", 300, TAILLE_3)
        self.pas("T-1", "dev", "begin", 0, lot="T-41", taille=TAILLE_3)
        self.pas("T-1", "juges", "begin", 60_000, lot="T-42")
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=180_000), " · ⏱ juges 2m/? +1")
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", lot="T-41", now_ms=180_000), " · ⏱ dev 3m/~5m")
        self.pas("T-1", "juges", "end", 200_000, lot="T-42")
        self.pas("T-1", "dev", "end", 200_000, lot="T-41")
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=300_000), "", "aucune étape ouverte")
        self.pas("T-1", "porte", "begin", 300_000)
        self.fermer("T-1", 400_000)
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=500_000), "", "cycle clos")

    def test_w6_lecture_bornee_a_la_fin_du_journal_et_erreur_muette(self):
        chemin = tc.chemin_journal(self.base, "T-1")
        chemin.parent.mkdir(parents=True)
        chemin.write_text("x" * (tc.LECTURE_MAX + 10) + "\n", encoding="utf-8")
        self.pas("T-1", "dev", "begin", 0)
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=5_000), " · ⏱ dev 5s/?")
        chemin.unlink()
        chemin.mkdir()  # un répertoire à la place du journal : erreur, jamais une levée
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=5_000), "")


class ParentClos(Base):
    """Passe de correction, point 3 : le start d'un lot après le done du parent n'ouvre pas de cycle 2
    fantôme au journal du parent ; une reprise du parent lui-même (start après reopen) en ouvre un."""

    def board(self, etat_parent):
        return {"tasks": [{"id": "T-5", "writeset": ["p"], "state": etat_parent},
                          {"id": "T-41", "writeset": ["b"], "state": "running", "fournee": {"parent": "T-5", "lot": "A"}}]}

    def test_lot_apres_le_done_du_parent_n_ouvre_rien(self):
        tc.jalons_du_verbe(self.base, self.board("running"), "fournee", ["T-5"], now_ms=0)
        tc.jalons_du_verbe(self.base, self.board("done"), "done", ["T-5"], now_ms=1_000)
        avant = tc.chemin_journal(self.base, "T-5").read_bytes()
        tc.jalons_du_verbe(self.base, self.board("done"), "start", ["T-41"], now_ms=2_000)
        self.assertEqual(tc.chemin_journal(self.base, "T-5").read_bytes(), avant, "aucun cycle fantôme")
        tc.jalons_du_verbe(self.base, self.board("running"), "start", ["T-5"], now_ms=3_000)
        self.assertEqual(sorted(tc.cycles(tc.lire(self.base, "T-5"))), [1, 2], "la reprise du parent ouvre le cycle 2")

    def test_lot_apres_le_done_d_un_parent_sans_journal_n_en_cree_pas(self):
        tc.jalons_du_verbe(self.base, self.board("done"), "start", ["T-41"], now_ms=2_000)
        self.assertFalse(tc.chemin_journal(self.base, "T-5").exists(), "journal git-ignoré absent : rien de créé")


class Durcissement(Base):
    """Passes de correction : ni FIFO ni lien suivis, lecture bornée, id revalidé, journal filtré à la source."""

    def journal(self, tid="T-1"):
        chemin = tc.chemin_journal(self.base, tid)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        return chemin

    @unittest.skipUnless(hasattr(os, "mkfifo"), "SAUT ANNONCE : pas de FIFO sur cet hôte")
    def test_fifo_refusee_sans_bloquer(self):
        os.mkfifo(self.journal())
        with self.assertRaisesRegex(tc.ChronoErreur, "pas un fichier régulier"):
            tc.lire(self.base, "T-1")
        with self.assertRaises(tc.ChronoErreur):
            tc._noter(self.base, "T-1", {"ev": "cycle", "cycle": 1, "ts": 0})
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=0), "")
        # une FIFO dont un lecteur est ouvert accepterait l'écriture : seul `S_ISREG` la refuse
        lecteur = os.open(str(self.journal()), os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, lecteur)
        with self.assertRaisesRegex(tc.ChronoErreur, "pas un fichier régulier"):
            tc._noter(self.base, "T-1", {"ev": "cycle", "cycle": 1, "ts": 0})
        self.assertEqual(os.read(lecteur, 4096), b"", "rien n'a traversé la FIFO")

    def test_dossier_du_journal_lien_refuse(self):
        ailleurs = self.base / "ailleurs"
        ailleurs.mkdir()
        dossier = self.base / tc.JOURNAL_DIR_REL
        dossier.parent.mkdir(parents=True)
        dossier.symlink_to(ailleurs, target_is_directory=True)
        with self.assertRaisesRegex(tc.ChronoErreur, "lien symbolique"):
            tc._noter(self.base, "T-1", {"ev": "cycle", "cycle": 1, "ts": 0})
        self.assertEqual(list(ailleurs.iterdir()), [], "rien d'écrit à travers le lien")
        (ailleurs / "T-1.jsonl").write_text(json.dumps({"ev": "cycle", "cycle": 1, "ts": 0}) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(tc.ChronoErreur, "lien symbolique"):
            tc.lire(self.base, "T-1")
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=0), "")

    def test_lien_symbolique_jamais_suivi(self):
        vrai = self.base / "ailleurs.jsonl"
        vrai.write_text(json.dumps({"ev": "cycle", "cycle": 1, "ts": 0}) + "\n", encoding="utf-8")
        self.journal().symlink_to(vrai)
        with self.assertRaisesRegex(tc.ChronoErreur, "illisible"):
            tc.lire(self.base, "T-1")
        self.assertEqual(tc.suffixe_statusline(self.base, "T-1", now_ms=0), "")

    def test_lecture_bornee(self):
        self.journal().write_bytes(b" " * (tc.LIRE_MAX + 1))
        with self.assertRaisesRegex(tc.ChronoErreur, "au-delà de"):
            tc.lire(self.base, "T-1")

    def test_octets_fournis_aucune_ouverture(self):
        """`octets=` (lecteur du dashboard, lecture déjà contrôlée) : ni `os.open` ni `_lire_octets`."""
        octets = (json.dumps({"ev": "cycle", "cycle": 3, "ts": 0}) + "\n").encode()

        def interdit(*_a, **_k):
            raise AssertionError("le chemin a été ouvert")

        with mock.patch.object(tc.os, "open", interdit), mock.patch.object(tc, "_lire_octets", interdit):
            self.assertEqual([l["cycle"] for l in tc.lire(self.base, "T-1", octets)], [3])
            self.assertEqual(tc.bilan(self.base, "T-1", now_ms=0, octets=octets)["cycle"], 3)

    def test_f1_octets_sous_un_dossier_lien_refuses(self):
        """F1 de la clôture : `octets=` ne saute plus `_dossier_sur` ni l'id. MUTANT qui le rougit :
        `lire` revenu à `_analyser(octets…)` sans `chemin_journal` ni `_octets_admis`."""
        ailleurs = self.base / "ailleurs"
        ailleurs.mkdir()
        dossier = self.base / tc.JOURNAL_DIR_REL
        dossier.parent.mkdir(parents=True)
        dossier.symlink_to(ailleurs, target_is_directory=True)
        octets = (json.dumps({"ev": "cycle", "cycle": 1, "ts": 0}) + "\n").encode()
        with self.assertRaisesRegex(tc.ChronoErreur, "lien symbolique"):
            tc.lire(self.base, "T-1", octets)
        with self.assertRaisesRegex(tc.ChronoErreur, "lien symbolique"):
            tc.bilan(self.base, "T-1", now_ms=0, octets=octets)
        with self.assertRaisesRegex(tc.ChronoErreur, "lien symbolique"):
            tc.lire_brut(self.base, "T-1")
        with self.assertRaisesRegex(tc.ChronoErreur, "hors des formes"):
            tc.lire(self.base, "../x", octets)

    def test_f1_octets_au_dela_de_lire_max_ou_hors_type_refuses(self):
        """F1 : 2,1 Mio passés en `octets` sont refusés comme la lecture du fichier ; un `str` aussi."""
        trop = b" " * int(2.1 * 1024 * 1024)
        for appel in (lambda o: tc.lire(self.base, "T-1", o), lambda o: tc.bilan(self.base, "T-1", now_ms=0, octets=o)):
            with self.assertRaisesRegex(tc.ChronoErreur, "au-delà de"):
                appel(trop)
            with self.assertRaisesRegex(tc.ChronoErreur, "ni bytes ni bytearray"):
                appel('{"ev": "cycle", "cycle": 1, "ts": 0}\n')
        self.assertEqual(tc.lire(self.base, "T-1", bytearray(b"")), [])

    def test_f1_lire_brut_absent_vide_puis_contenu(self):
        self.assertEqual(tc.lire_brut(self.base, "T-1"), b"")
        self.pas("T-1", "dev", "begin", 0)
        brut = tc.lire_brut(self.base, "T-1")
        self.assertEqual(brut, tc.chemin_journal(self.base, "T-1").read_bytes())
        self.assertEqual(tc.lire(self.base, "T-1", brut), tc.lire(self.base, "T-1"))

    def test_estimation_avec_mediane_exige_les_quatre_cles(self):
        """Réserve exec (:215) : une médiane sans p90, sans n ou sans source est rejetée. MUTANT qui le
        rougit : la dernière ligne de `_ligne_valide` réduite à `return True`."""
        complete = {"source": "historique", "n": 1, "mediane_s": 60, "p90_s": 60}
        ligne = {"ev": "etape", "cycle": 1, "ts": 0, "etape": "dev", "lot": None}
        self.assertTrue(tc._ligne_valide(dict(ligne, estimation=complete)))
        for cle in ("source", "n", "p90_s"):
            with self.subTest(sans=cle):
                est = {k: v for k, v in complete.items() if k != cle}
                self.assertFalse(tc._ligne_valide(dict(ligne, estimation=est)))

    def test_tentative_booleenne_refusee_a_la_relecture(self):
        """Réserve exec (:248) : `tentative: true` n'est pas la tentative 1. MUTANT qui le rougit :
        `isinstance(…, int)` rétabli dans `cycles`."""
        lignes = [{"ev": "cycle", "cycle": 1, "ts": 0},
                  {"ev": "etape", "cycle": 1, "etape": "dev", "lot": None, "tentative": True, "phase": "begin", "ts": 0}]
        self.assertEqual(tc.cycles(lignes)[1]["etapes"], {})

    def test_ligne_cycle_champs_valides(self):
        """Réserve exec : une ligne `ev=cycle` voit ses champs validés — cycle entier ≥ 1, tid à la forme
        du board. MUTANT qui le rougit : le contrôle `cycle < 1` ou celui du `tid` retiré."""
        for mutee in ({"cycle": 0}, {"cycle": -3}, {"cycle": True}, {"cycle": "1"}, {"tid": "../x"}, {"tid": 7}):
            with self.subTest(mutee=mutee):
                self.assertFalse(tc._ligne_valide(dict({"ev": "cycle", "cycle": 1, "ts": 0}, **mutee)))
        self.assertTrue(tc._ligne_valide({"ev": "cycle", "tid": "T-1", "cycle": 1, "ts": 0}))

    def test_id_hors_formes_du_board_refuse(self):
        for tid in ("../x", "T-1/../../y", "T-", "T-1.jsonl", "x"):
            with self.subTest(tid=tid), self.assertRaisesRegex(tc.ChronoErreur, "hors des formes"):
                tc.chemin_journal(self.base, tid)
        self.assertEqual(tc.suffixe_statusline(self.base, "../x", now_ms=0), "")
        tc.chemin_journal(self.base, "T-01M5JKBXHYY8F374DNSMPPFQ1V")  # un ULID passe

    def test_esc_injecte_ne_ressort_nulle_part(self):
        """Point 1 de la passe 3 : étape, lot et source d'estimation filtrés DANS `_ligne_valide`."""
        esc = "\x1b]0;x\x07"
        est_ok = {"source": "historique", "n": 1, "mediane_s": 60, "p90_s": 60}
        injectees = [{"etape": "\x1b[2Jpirate", "lot": None, "estimation": est_ok},
                     {"etape": "juges", "lot": esc, "estimation": est_ok},
                     {"etape": "fusion", "lot": None, "estimation": dict(est_ok, source="historique" + esc)},
                     {"etape": "porte", "lot": None, "estimation": {"source": "x" * 300, "n": 0}}]
        lignes = [{"ev": "cycle", "cycle": 1, "ts": 0}]
        lignes += [dict(l, ev="etape", cycle=1, tentative=1, phase="begin", ts=0) for l in injectees]
        lignes.append({"ev": "etape", "cycle": 1, "etape": "dev", "lot": None, "tentative": 1, "phase": "begin",
                       "ts": 0, "estimation": est_ok})
        self.journal().write_text("".join(json.dumps(l) + "\n" for l in lignes), encoding="utf-8")
        self.assertEqual([e[0] for e in tc.cycles(tc.lire(self.base, "T-1"))[1]["etapes"]], ["dev"], "seule la saine")
        sorties = [tc.suffixe_statusline(self.base, "T-1", now_ms=5_000),
                   tc.rendre(tc.bilan(self.base, "T-1", now_ms=9_000))]
        sorties += tc.jalons_du_verbe(self.base, {"tasks": [{"id": "T-1", "state": "done"}]}, "done", ["T-1"],
                                      now_ms=9_000)
        self.assertEqual(len(sorties), 3, sorties)
        for sortie in sorties:
            self.assertFalse(any(ord(c) < 32 and c != "\n" for c in sortie), repr(sortie))
            self.assertNotIn("pirate", sortie)
        with self.assertRaisesRegex(tc.ChronoErreur, "hors des formes"):
            tc.etape(self.base, "T-1", "dev", "begin", lot=esc, now_ms=0)

    def porte_tsv(self, *modes):
        """`porte-chrono.tsv` au format de verify.sh (iso, durée, sha, mode, rc) : une porte verte par mode."""
        chemin = self.base / ".agents" / "state" / "local" / "porte-chrono.tsv"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("".join(f"2026-10-23T00:00:00Z\t60\tabc\t{m}\t0\n" for m in modes), encoding="utf-8")

    def test_sources_derivees_de_l_ecrivain_sont_admises(self):
        """Les sources que `estimer` peut écrire, PRODUITES par l'écrivain réel : chaque rôle de
        ROLES_DE_L_ETAPE, chaque mode de porte de verify.sh, le repli `?` d'agent_chrono et un mode hors
        grammaire ; chacune doit passer `_ligne_valide`, sinon le begin serait perdu à la relecture."""
        journal = self.base / ".agents" / "state" / "local" / "agent-chrono.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        # UN journal par couple étape/rôle, ce rôle seul mesuré : chaque rôle de chaque étape est PRODUIT par
        # l'écrivain, pas seulement le plus mesuré de l'étape.
        couples = [(e, r) for e, rs in tc.ROLES_DE_L_ETAPE.items() for r in rs]
        sources = set()
        for etape_nom, role in couples:
            journal.write_text(json.dumps({"ev": "stop", "aid": "a0", "agent": role, "ts": 0, "duration_ms": 60_000})
                               + "\n", encoding="utf-8")
            source = tc._repli_par_role(self.base, etape_nom)["source"]
            self.assertEqual(source, f"rôle {role}", (etape_nom, role))
            sources.add(source)
        self.assertEqual(sources, {f"rôle {r}" for _e, r in couples}, "chaque rôle de ROLES_DE_L_ETAPE couvert")
        for mode in ("live", "frozen", "frozen-linux", "", "Mode Bizarre\x9b"):
            self.porte_tsv(mode)
            sources.add(tc.estimer(self.base, "porte", None)["source"])
        sources |= {tc.estimer(self.base, e, None)["source"] for e in ("attente-pilote", "done")}
        sources |= {"historique", "inconnu"}
        self.assertTrue({"porte live", "porte frozen", "porte frozen-linux", "porte ?"} <= sources, sources)
        for source in sorted(sources):
            with self.subTest(source=source):
                self.assertTrue(tc._ligne_valide({"ev": "etape", "cycle": 1, "ts": 0, "etape": "dev", "lot": None,
                                                  "estimation": {"source": source, "n": 0}}))

    def test_porte_mode_vide_begin_puis_end(self):
        self.porte_tsv("")  # agent_chrono rend le mode `?`
        self.assertIn("porte ?", self.pas("T-1", "porte", "begin", 0))
        self.assertIn("fin en 1m00s", self.pas("T-1", "porte", "end", 60_000))

    def test_c1_injecte_ne_ressort_pas_du_json(self):
        c1 = "\x9b2J"
        est = {"source": "historique", "n": 1, "mediane_s": 60, "p90_s": 60, "note": c1}
        lignes = [{"ev": "cycle", "cycle": 1, "ts": 0},
                  {"ev": "etape", "cycle": 1, "etape": "dev", "lot": None, "tentative": 1, "phase": "begin", "ts": 0,
                   "estimation": est},
                  {"ev": "etape", "cycle": 1, "etape": "juges", "lot": None, "tentative": 1, "phase": "begin", "ts": 0,
                   "estimation": dict(est, source="historique" + c1)},
                  {"ev": "etape", "cycle": 1, "etape": "porte", "lot": None, "tentative": 1, "phase": "begin", "ts": 0,
                   "estimation": {"source": "inconnu", "n": c1}}]
        self.journal().write_text("".join(json.dumps(l) + "\n" for l in lignes), encoding="utf-8")
        sortie = tc.executer(self.base, {"tasks": []}, "T-1", "show", en_json=True)
        self.assertNotIn(c1, sortie)
        self.assertNotIn("\\u009b", sortie)
        b = json.loads(sortie)
        self.assertEqual([(l["etape"], sorted(l["estimation"])) for l in b["etapes"]],
                         [("dev", ["mediane_s", "n", "p90_s", "source"])])


T0 = 1_700_000_000_000
TIP_A, TIP_B, SHA_X = "a" * 40, "b" * 40, "c" * 40


def iso(ms):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


class QueueApresLeDev(Base):
    """T-01M5PVWHM8KRNRF960PTBV4FE7 lot A, au moteur : `review-scope` relève `juges` et ouvre `cloture` ;
    le `done` complète `cloture`, `porte` et `correction` (A1-A5 de l'annexe r2/r3, réserves C18, C19, C21).
    `git` injecté : le filtre par sha réel est jugé par la CLI (test_tasks_chrono, A3c/W4d)."""

    def board(self, tip=TIP_A, etat="running"):
        t6 = {"id": "T-6", "writeset": ["a"], "state": etat}
        if tip:
            t6["retour"] = {"tip": tip}
        return {"tasks": [t6, {"id": "T-5", "writeset": ["p"], "state": etat, "retour": {"tip": TIP_A}},
                          {"id": "T-41", "writeset": ["b"], "state": "running", "fournee": {"parent": "T-5", "lot": "A"},
                           "retour": {"tip": TIP_B}}]}

    def portes_tsv(self, *lignes):
        chemin = self.base / ".agents" / "state" / "local" / "porte-chrono.tsv"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("".join("\t".join(map(str, l)) + "\n" for l in lignes), encoding="utf-8")

    def scope(self, tids, ts, board=None):
        return tc.jalons_du_verbe(self.base, board or self.board(), "review-scope", tids, now_ms=ts)

    def done(self, tid, ts, traces=None, git=None, board=None):
        board = board or self.board(etat="done")
        appels = []

        def git_espion(*a):
            appels.append(a)
            return (git or (lambda *_: ""))(*a)

        cands = tc.portes_a_mesurer(self.base, board, "done", [tid], traces or (lambda _t: {}), now_ms=ts)
        portes, avis = tc.portes_premesurees(cands, git_espion)
        avis += tc.jalons_du_verbe(self.base, board, "done", [tid], now_ms=ts, portes=portes)
        return avis, appels

    def mesures(self, tid, etape_nom):
        c = tc.cycles(tc.lire(self.base, tid))
        c = c[max(c)]
        return sorted((e["debut"], e.get("fin")) for e in c["etapes"].values() if e["etape"] == etape_nom)

    def jusqu_a_la_cloture(self, fin_cloture=None):
        """T-6 : dev [T0, T0+60 s], review-scope à T0+100 s, clôture finie à `fin_cloture` si donnée."""
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        self.pas("T-6", "dev", "end", T0 + 60_000)
        self.assertEqual(self.scope(["T-6"], T0 + 100_000), [])
        if fin_cloture is not None:
            self.pas("T-6", "cloture", "end", fin_cloture)

    def test_a1_review_scope_releve_juges_et_ouvre_la_cloture(self):
        self.jusqu_a_la_cloture()
        self.assertEqual(self.mesures("T-6", "juges"), [(T0 + 60_000, T0 + 100_000)])
        self.assertEqual(self.mesures("T-6", "cloture"), [(T0 + 100_000, None)])

    def test_a1b_sans_fin_de_dev_ni_de_fusion_aucun_juges_un_avis(self):
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        avis = self.scope(["T-6"], T0 + 100_000)
        self.assertEqual(avis, ["CHRONO: avis T-6 cycle 1 — juges non relevé : aucune fin de dev ni de fusion"])
        self.assertEqual(self.mesures("T-6", "juges"), [])
        self.assertEqual(self.mesures("T-6", "cloture"), [(T0 + 100_000, None)])

    def test_a1c_fusion_ouverte_juges_ecrits_et_avis_chevauche(self):
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        tc.jalons_du_verbe(self.base, self.board(), "retour", ["T-6"], now_ms=T0 + 60_000)
        avis = self.scope(["T-6"], T0 + 100_000)
        self.assertEqual(self.mesures("T-6", "juges"), [(T0 + 60_000, T0 + 100_000)])
        self.assertEqual(len(avis), 1, avis)
        self.assertIn("chevauche : fusion", avis[0])

    def test_a1d_sans_cycle_ou_parent_clos_rien_d_ecrit(self):
        self.assertEqual(self.scope(["T-6"], T0), [])
        self.assertFalse(tc.chemin_journal(self.base, "T-6").exists())
        clos = self.board()
        for t in clos["tasks"]:
            if t["id"] == "T-5":
                t["state"] = "done"
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        self.pas("T-5", "dev", "end", T0 + 60_000, lot="T-41")
        tc.jalons_du_verbe(self.base, clos, "done", ["T-5"], now_ms=T0 + 70_000)
        avant = tc.chemin_journal(self.base, "T-5").read_bytes()
        self.assertEqual(self.scope(["T-41"], T0 + 100_000, board=clos), [])
        self.assertEqual(tc.chemin_journal(self.base, "T-5").read_bytes(), avant, "aucun cycle fantôme")

    def test_a1e_juges_d_un_lot_deja_au_journal_aucune_cle_juges_sans_lot(self):
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        self.pas("T-5", "dev", "end", T0 + 60_000, lot="T-41")
        self.pas("T-5", "juges", "begin", T0 + 60_000, lot="T-41")
        self.scope(["T-41", "T-5"], T0 + 100_000)
        cles = set(tc.cycles(tc.lire(self.base, "T-5"))[1]["etapes"])
        self.assertNotIn(("juges", "", 1), cles)
        self.assertIn(("cloture", "", 1), cles, "une seule cloture par journal, au parent")
        self.assertEqual(sum(k[0] == "cloture" for k in cles), 1)

    def test_a1f_dev_encore_ouvert_avis_ni_juges_ni_cloture(self):
        """C1 (S-01M5RW1HJE) : dev t1 fini, dev t2 ouvert : avis, aucune clé juges ni cloture ; le
        review-scope suivant, dev fini, les relève."""
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        self.pas("T-6", "dev", "end", T0 + 60_000)
        self.pas("T-6", "dev", "begin", T0 + 70_000)
        avis = self.scope(["T-6"], T0 + 100_000)
        self.assertEqual(avis, ["CHRONO: avis T-6 cycle 1 — dev encore ouvert (1) : ni juges ni clôture relevés"])
        cles = set(tc.cycles(tc.lire(self.base, "T-6"))[1]["etapes"])
        self.assertFalse(any(k[0] in ("juges", "cloture") for k in cles), cles)
        self.pas("T-6", "dev", "end", T0 + 120_000)
        self.assertEqual(self.scope(["T-6"], T0 + 150_000), [])
        self.assertEqual(self.mesures("T-6", "juges"), [(T0 + 120_000, T0 + 150_000)])

    def test_a1g_lot_au_dev_ouvert_aucune_fin_avis_sans_ecrire(self):
        """C1 : un lot dont le dev tourne, sans aucune fin au cycle : même avis, rien d'écrit."""
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        avis = self.scope(["T-41", "T-5"], T0 + 100_000)
        self.assertEqual(avis, ["CHRONO: avis T-5 cycle 1 — dev encore ouvert (1) : ni juges ni clôture relevés"])
        self.assertEqual((self.mesures("T-5", "juges"), self.mesures("T-5", "cloture")), ([], []))

    def test_a1h_fusion_de_correction_du_parent_n_avance_pas_juges(self):
        """C2 : lots fusionnés, puis fusion du parent (lot None) : juges part de la dernière fin de LOT."""
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        tc.jalons_du_verbe(self.base, self.board(), "retour", ["T-41"], now_ms=T0 + 60_000)
        self.pas("T-5", "fusion", "end", T0 + 80_000, lot="T-41")
        self.pas("T-5", "fusion", "begin", T0 + 90_000)
        self.pas("T-5", "fusion", "end", T0 + 95_000)
        self.assertEqual(self.scope(["T-41", "T-5"], T0 + 100_000), [])
        self.assertEqual(self.mesures("T-5", "juges"), [(T0 + 80_000, T0 + 100_000)])

    def test_a1i_sans_lot_un_retour_de_correction_n_ouvre_pas_de_fusion_t2(self):
        """C2, lecture du critique INFIRMÉE : sans lot, le `retour` d'une passe de correction n'ouvre pas de
        fusion t2 (`_retour` n'en ouvre qu'une, à la 1re) ; juges part de la fin de la fusion t1."""
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        tc.jalons_du_verbe(self.base, self.board(), "retour", ["T-6"], now_ms=T0 + 60_000)
        self.pas("T-6", "fusion", "end", T0 + 70_000)
        tc.jalons_du_verbe(self.base, self.board(), "retour", ["T-6"], now_ms=T0 + 90_000)
        cles = set(tc.cycles(tc.lire(self.base, "T-6"))[1]["etapes"])
        self.assertEqual(sorted(k for k in cles if k[0] == "fusion"), [("fusion", "", 1)])
        self.assertEqual(self.scope(["T-6"], T0 + 100_000), [])
        self.assertEqual(self.mesures("T-6", "juges"), [(T0 + 70_000, T0 + 100_000)])

    def test_a1j_fusion_t2_du_lanceur_n_avance_pas_juges(self):
        """C2 : une fusion de tentative 2 posée par le lanceur ne décale pas le début de juges."""
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        tc.jalons_du_verbe(self.base, self.board(), "retour", ["T-6"], now_ms=T0 + 60_000)
        self.pas("T-6", "fusion", "end", T0 + 70_000)
        self.pas("T-6", "fusion", "begin", T0 + 80_000, tentative=2)
        self.pas("T-6", "fusion", "end", T0 + 90_000, tentative=2)
        self.assertEqual(self.scope(["T-6"], T0 + 100_000), [])
        self.assertEqual(self.mesures("T-6", "juges"), [(T0 + 70_000, T0 + 100_000)])

    def test_a2_cloture_finie_au_plus_grand_at_des_traces(self):
        self.jusqu_a_la_cloture()
        traces = {"critic-opus": {"at": iso(T0 + 150_000)}, "critic-fable": {"at": iso(T0 + 200_000)}}
        avis, appels = self.done("T-6", T0 + 300_000, traces=lambda t: traces if t == "T-6" else {})
        self.assertEqual(self.mesures("T-6", "cloture"), [(T0 + 100_000, T0 + 200_000)])
        self.assertEqual((avis, appels), ([], []), "aucune ligne de porte : aucun git, aucun avis")

    def test_a2b_trace_d_un_cycle_anterieur_ignoree(self):
        self.jusqu_a_la_cloture()
        traces = {"critic-opus": {"at": iso(T0 + 50_000)}}
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0))
        avis, appels = self.done("T-6", T0 + 300_000, traces=lambda _t: traces)
        self.assertEqual(self.mesures("T-6", "cloture"), [(T0 + 100_000, None)])
        self.assertEqual(avis[0], "CHRONO: avis T-6 cycle 1 — clôture sans fin relevée (ni fin au journal, ni trace "
                                  "de revue dans sa fenêtre) : ni porte ni correction")
        self.assertEqual((self.mesures("T-6", "porte"), appels), ([], []))

    def test_a3_portes_figees_apres_la_cloture_et_correction(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 1), (iso(T0 + 250_000), 5, SHA_X, "live", 0),
                        (iso(T0 + 260_000), 20, SHA_X, "frozen", 0))
        avis, appels = self.done("T-6", T0 + 400_000)
        self.assertEqual(avis, [])
        self.assertEqual(self.mesures("T-6", "porte"), [(T0 + 210_000, T0 + 240_000), (T0 + 260_000, T0 + 280_000)])
        self.assertEqual(self.mesures("T-6", "correction"), [(T0 + 200_000, T0 + 210_000)])
        self.assertEqual(appels, [("rev-list", "-n", "1", f"{SHA_X}..{TIP_A}")], "un git par (sha, pointe)")
        self.assertTrue(tc.bilan(self.base, "T-6")["clos"])

    def test_a3b_hors_de_la_fenetre_ignorees(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 150_000), 30, SHA_X, "frozen", 0), (iso(T0 + 500_000), 30, SHA_X, "frozen", 0))
        avis, appels = self.done("T-6", T0 + 400_000)
        self.assertEqual((avis, appels, self.mesures("T-6", "porte"), self.mesures("T-6", "correction")),
                         ([], [], [], []))

    def test_a3d_aucune_pointe_lignes_comptees_avec_avis(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0))
        avis, appels = self.done("T-6", T0 + 400_000, board=self.board(tip=None, etat="done"))
        self.assertEqual(avis, ["CHRONO: avis T-6 — porte non filtrée par sha : aucune pointe relevée "
                                "(1 ligne(s) comptée(s))"])
        self.assertEqual((appels, len(self.mesures("T-6", "porte"))), ([], 1))

    def test_a3e_cloture_ouverte_sans_trace_ni_porte_ni_correction(self):
        self.jusqu_a_la_cloture()
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0))
        avis, appels = self.done("T-6", T0 + 400_000)
        self.assertIn("clôture sans fin relevée", avis[0])
        self.assertEqual((appels, self.mesures("T-6", "porte"), self.mesures("T-6", "correction")), ([], [], []))

    def test_a3f_cinq_ou_six_colonnes_jamais_sept(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0, "-"),
                        (iso(T0 + 260_000), 20, SHA_X, "frozen", 1, "pytest"),
                        (iso(T0 + 300_000), 20, SHA_X, "frozen", 0, "-", "septième"))
        self.done("T-6", T0 + 400_000)
        self.assertEqual(self.mesures("T-6", "porte"), [(T0 + 210_000, T0 + 240_000), (T0 + 260_000, T0 + 280_000)])

    def test_a3g_frozen_linux_comptee_live_ignoree(self):
        """Réserve C18 : le lecteur accepte chaque mode figé que la porte écrit (`--linux` : frozen-linux)."""
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen-linux", 0), (iso(T0 + 260_000), 20, SHA_X, "live", 0))
        self.done("T-6", T0 + 400_000)
        self.assertEqual(self.mesures("T-6", "porte"), [(T0 + 210_000, T0 + 240_000)])

    def test_a3h_porte_dans_la_seconde_de_fin_de_cloture_comptee(self):
        """Le début de porte est ISO à la seconde : une porte lancée dans la seconde où la clôture finit
        (fin à X.400, porte à X) est comptée ; celle de la seconde d'avant ne l'est pas."""
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_400)
        self.portes_tsv((iso(T0 + 199_000), 10, SHA_X, "frozen", 0), (iso(T0 + 200_000), 30, SHA_X, "frozen", 0))
        avis, _appels = self.done("T-6", T0 + 400_000)
        self.assertEqual(avis, [])
        self.assertEqual(self.mesures("T-6", "porte"), [(T0 + 200_000, T0 + 230_000)])
        self.assertEqual(len(self.mesures("T-6", "correction")), 1, "la correction suit la porte retenue")

    def test_a3i_duree_hors_ascii_ignoree_sans_lever(self):
        """`"²".isdigit()` vaut vrai et `int("²")` lève : une durée hors chiffres ASCII est ignorée."""
        self.portes_tsv((iso(T0), "²", SHA_X, "frozen", 0), (iso(T0 + 1_000), 30, SHA_X, "frozen", 0))
        self.assertEqual([l["duree_s"] for l in tc.portes_du_journal(self.base)], [30])

    def test_a4_porte_deja_relevee_par_step_inchangee(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.pas("T-6", "porte", "begin", T0 + 205_000)
        self.pas("T-6", "porte", "end", T0 + 235_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0), (iso(T0 + 260_000), 20, SHA_X, "frozen", 0))
        self.done("T-6", T0 + 400_000)
        self.assertEqual(self.mesures("T-6", "porte"), [(T0 + 205_000, T0 + 235_000)])
        self.assertEqual(self.mesures("T-6", "correction"), [(T0 + 200_000, T0 + 205_000)])

    def test_c19_toutes_les_pointes_contenues_sinon_avis_hors_pointes(self):
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        self.pas("T-5", "dev", "end", T0 + 60_000, lot="T-41")
        self.scope(["T-5"], T0 + 100_000)
        self.pas("T-5", "cloture", "end", T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0))
        avis, appels = self.done("T-5", T0 + 400_000, git=lambda *a: "" if a[-1].endswith(TIP_A) else "x" * 40)
        self.assertEqual(avis, ["CHRONO: avis T-5 — porte non relevée : 1 ligne(s) dans la fenêtre, hors pointes"])
        self.assertEqual({a[-1].split("..")[1] for a in appels}, {TIP_A, TIP_B}, "la pointe du lot est relevée")
        self.assertEqual(self.mesures("T-5", "porte"), [])

    def test_c21_done_d_un_lot_aucun_candidat_aucun_git(self):
        tc.jalons_du_verbe(self.base, self.board(), "fournee", ["T-5"], now_ms=T0)
        self.pas("T-5", "dev", "end", T0 + 60_000, lot="T-41")
        self.scope(["T-41"], T0 + 100_000)
        self.pas("T-41", "cloture", "begin", T0 + 100_000)  # un journal propre au lot, même errant : jamais lu
        lot_clos = self.board()
        lot_clos["tasks"][2]["state"] = "done"
        traces = lambda _t: {"critic-opus": {"at": iso(T0 + 150_000)}}  # noqa: E731
        self.assertEqual(tc.portes_a_mesurer(self.base, lot_clos, "done", ["T-41"], traces, now_ms=T0 + 300_000), [])

    def test_w4e_panne_git_avis_aucune_porte_jalon_pose(self):
        self.jusqu_a_la_cloture(fin_cloture=T0 + 200_000)
        self.portes_tsv((iso(T0 + 210_000), 30, SHA_X, "frozen", 0))

        def panne(*a):
            raise RuntimeError("x")

        avis, _appels = self.done("T-6", T0 + 400_000, git=panne)
        self.assertEqual(avis, ["CHRONO: avis T-6 — porte non filtrée (1 ligne(s) exclue(s), git en panne) : "
                                "RuntimeError: x"])
        self.assertEqual(self.mesures("T-6", "porte"), [])
        self.assertTrue(tc.bilan(self.base, "T-6")["clos"], "le jalon done est posé")

    def test_piege2_ni_cloture_ni_trace_silence_et_aucun_git(self):
        tc.jalons_du_verbe(self.base, self.board(), "start", ["T-6"], now_ms=T0)
        self.pas("T-6", "dev", "end", T0 + 60_000)
        self.portes_tsv((iso(T0 + 70_000), 30, SHA_X, "frozen", 0))
        self.assertEqual(tc.portes_a_mesurer(self.base, self.board(etat="done"), "done", ["T-6"], lambda _t: {},
                                             now_ms=T0 + 400_000), [])
        self.assertEqual(self.done("T-6", T0 + 400_000), ([], []))
        self.assertEqual(self.mesures("T-6", "porte"), [])


class JalonsDePlanification(Base):
    """T-01M5VZF47T9RT1YM9KC67HCQPP : `plan_preflight.py` → « plan-soumis », `plan_pool.py check` READY →
    « plan-pret » ; idempotents, aucune écriture après le départ du dev, toute panne en avis."""

    def board(self, etat="pending", lots=False):
        taches = [{"id": "T-7", "state": etat}]
        if lots:
            taches.append({"id": "T-71", "state": "pending", "fournee": {"parent": "T-7"}})
        return {"tasks": taches}

    def jalon(self, quoi, ts, tid="T-7", data=None):
        return tc.jalon_de_planification(self.base, data or self.board(), tid, quoi, now_ms=ts)

    def lignes(self, tid="T-7"):
        return [(l["etape"], l["phase"]) for l in tc.lire(self.base, tid) if l["ev"] == "etape"]

    def test_plan_soumis_cree_le_cycle_et_ouvre_une_seule_fois(self):
        # kills « commencer retiré » (cycle absent → rien) et « garde planification ouverte retirée » (2 lignes)
        self.assertEqual(self.jalon("plan-soumis", 1_000), [])
        self.assertEqual(self.jalon("plan-soumis", 2_000), [])
        self.assertEqual([l["ev"] for l in tc.lire(self.base, "T-7")].count("cycle"), 1)
        self.assertEqual(self.lignes(), [("planification", "begin")])

    def test_plan_pret_ferme_et_ouvre_attente_pilote_une_seule_fois(self):
        # kills « fin de planification retirée » et « garde attente-pilote existante retirée »
        self.jalon("plan-soumis", 0)
        self.assertEqual(self.jalon("plan-pret", 60_000), [])
        self.assertEqual(self.jalon("plan-pret", 90_000), [])
        self.assertEqual(self.lignes(), [("planification", "begin"), ("planification", "end"),
                                         ("attente-pilote", "begin")])
        self.assertEqual(tc.bilan(self.base, "T-7", now_ms=99_000)["etapes"][0]["reel_s"], 60)
        # un nouveau préflight après le check READY : attente-pilote est postérieure, rien
        self.jalon("plan-soumis", 95_000)
        self.assertEqual(len(self.lignes()), 3)
        # kills « garde attente-pilote existante retirée » : le lanceur l'a finie, un check rejoué ne la rouvre pas
        self.pas("T-7", "attente-pilote", "end", 96_000)
        self.jalon("plan-pret", 97_000)
        self.assertEqual(self.lignes()[3:], [("attente-pilote", "end")])

    def test_apres_un_dev_ouvert_ni_l_un_ni_l_autre_n_ecrit(self):
        # kills « garde étape postérieure retirée » sur chacun des deux jalons
        tc.jalons_du_verbe(self.base, self.board("running"), "start", ["T-7"], now_ms=0)
        self.jalon("plan-soumis", 1_000)
        self.jalon("plan-pret", 2_000)
        self.assertEqual(self.lignes(), [("dev", "begin")])

    def test_plan_pret_sans_cycle_ouvert_n_en_ouvre_pas(self):
        self.assertEqual(self.jalon("plan-pret", 0), [])
        self.assertEqual(tc.lire(self.base, "T-7"), [])

    def test_un_lot_et_une_tache_close_n_ecrivent_rien(self):
        self.jalon("plan-soumis", 0, tid="T-71", data=self.board(lots=True))
        self.jalon("plan-soumis", 0, data=self.board("done"))
        self.assertEqual((tc.lire(self.base, "T-71"), tc.lire(self.base, "T-7")), ([], []))

    def test_le_depart_du_dev_ferme_l_attente_pilote(self):
        # kills « fermeture d'attente-pilote retirée de _ouvrir_dev »
        self.jalon("plan-soumis", 0)
        self.jalon("plan-pret", 10_000)
        tc.jalons_du_verbe(self.base, self.board("running"), "start", ["T-7"], now_ms=70_000)
        c = tc.cycles(tc.lire(self.base, "T-7"))[1]
        self.assertEqual(c["etapes"][("attente-pilote", "", 1)]["fin"], 70_000)

    def test_le_depart_du_dev_ferme_la_planification_sans_check(self):
        # kills « fermeture de planification retirée de _ouvrir_dev » (/kickoff : préflight → GO → start)
        self.jalon("plan-soumis", 0)
        tc.jalons_du_verbe(self.base, self.board("running"), "start", ["T-7"], now_ms=70_000)
        c = tc.cycles(tc.lire(self.base, "T-7"))[1]
        self.assertEqual(c["etapes"][("planification", "", 1)]["fin"], 70_000)

    def test_panne_d_ecriture_rend_un_avis_jamais_une_exception(self):
        # kills « try/except retiré » : l'exception remonterait
        with mock.patch.object(tc.os, "write", side_effect=OSError(28, "disque plein")):
            avis = self.jalon("plan-soumis", 0)
        self.assertEqual(len(avis), 1)
        self.assertTrue(avis[0].startswith("CHRONO: avis T-7 — jalon plan-soumis non relevé"), avis)
        self.assertIn("disque plein", avis[0])
        self.assertTrue(self.jalon("plan-inconnu", 0)[0].startswith("CHRONO: avis T-7"))

    def test_racine_jetable_ou_banc_n_ecrit_rien(self):
        # kills « garde AGENTS_EVENTS_DIR retirée » et « garde dossier temporaire retirée »
        self.assertIsNone(tc.racine_de_jalon(self.base, env={"AGENTS_EVENTS_DIR": "/x"}, temporaires=()))
        self.assertIsNone(tc.racine_de_jalon(self.base / "sous", env={}, temporaires=(str(self.base),)))
        self.assertIsNone(tc.racine_de_jalon(self.base, env={}))  # défaut : dossier temporaire du système
        self.assertEqual(tc.racine_de_jalon(self.base, env={}, temporaires=()), self.base.resolve())


def _module(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


class BranchementDesJalons(Base):
    """Les appelants : `plan_preflight.jalon_chrono` (plan-soumis) et `plan_pool` (`check` READY → plan-pret),
    stdout intact, panne en avis stderr. La racine jetable est contournée par `racine_de_jalon` simulée."""

    BOARD = {"tasks": [{"id": "T-7", "state": "pending"}]}

    def setUp(self) -> None:
        super().setUp()
        self.preflight = _module("_banc_chrono_plan_preflight", ICI / "plan_preflight.py")
        self.pool = _module("_banc_chrono_plan_pool", ICI.parents[1] / "core-scripts" / "plan_pool.py")
        patch = mock.patch.object(tc, "racine_de_jalon", return_value=self.base)
        patch.start()
        self.addCleanup(patch.stop)

    def facade(self, load=None):
        return mock.Mock(task_chrono_module=lambda: tc, load=load or (lambda _r: self.BOARD))

    def capturer(self, fn, *a, **kw):
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn(*a, **kw)
        return out.getvalue(), err.getvalue()

    def lignes(self):
        return [(l["etape"], l["phase"]) for l in tc.lire(self.base, "T-7") if l["ev"] == "etape"]

    def test_preflight_ouvre_la_planification_sans_rien_dire(self):
        # kills « appel jalon_chrono retiré » / « quoi=plan-pret » dans plan_preflight
        self.assertEqual(self.capturer(self.preflight.jalon_chrono, self.base, "T-7", self.facade()), ("", ""))
        self.assertEqual(self.lignes(), [("planification", "begin")])

    def test_main_du_preflight_joue_le_jalon_au_rc_0_ou_1_seulement(self):
        # kills « appel retiré de main » et « garde rc in (0, 1) retirée »
        (self.base / "plan.md").write_text("plan\n", encoding="utf-8")
        for rc, attendu in ((0, 1), (1, 1), (2, 0)):
            with self.subTest(rc=rc), mock.patch.object(self.preflight, "preflight", return_value=[]), \
                    mock.patch.object(self.preflight, "rapport", return_value=(rc, "RAPPORT")), \
                    mock.patch.object(self.preflight, "jalon_chrono") as jalon:
                rendu = []
                out, _err = self.capturer(lambda: rendu.append(self.preflight.main(
                    ["--plan", "plan.md", "--task", "T-7", "--root", str(self.base)])))
                self.assertEqual((rendu, out.strip()), ([rc], "RAPPORT"))
                self.assertEqual(jalon.call_count, attendu)
                if attendu:
                    self.assertEqual(jalon.call_args.args[:2], (self.base.resolve(), "T-7"))

    def test_preflight_panne_en_avis_stderr_jamais_stdout(self):
        def casse(_r):
            raise OSError("board illisible")
        out, err = self.capturer(self.preflight.jalon_chrono, self.base, "T-7", self.facade(casse))
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("CHRONO: avis T-7 — planification non relevée"), err)

    def test_pool_jalon_ferme_la_planification_et_ouvre_l_attente(self):
        self.capturer(self.preflight.jalon_chrono, self.base, "T-7", self.facade())
        with mock.patch.object(self.pool, "load_board", return_value=self.BOARD["tasks"]):
            self.assertEqual(self.capturer(self.pool.jalon_chrono, self.base, "T-7", charger=lambda: tc), ("", ""))
        self.assertEqual(self.lignes(), [("planification", "begin"), ("planification", "end"),
                                         ("attente-pilote", "begin")])

    def test_pool_frere_absent_en_avis_stderr(self):
        out, err = self.capturer(self.pool.jalon_chrono, self.base, "T-7",
                                 charger=lambda: self.pool.charger_task_chrono(self.base / "absent.py"))
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("CHRONO: avis T-7 — attente-pilote non relevée (FileNotFoundError"), err)

    def test_check_ne_joue_le_jalon_qu_au_ready(self):
        # kills « garde v.code == READY retirée » et « appel retiré de cmd_check »
        for code, attendu in (("READY", 1), ("STALE", 0), ("PLAN_SANS_VERDICT", 0)):
            with self.subTest(code=code), \
                    mock.patch.object(self.pool, "load_board", return_value=[{"id": "T-7", "state": "pending"}]), \
                    mock.patch.object(self.pool, "load_specs", return_value=[]), \
                    mock.patch.object(self.pool, "classify", return_value=self.pool.Verdict("T-7", code)), \
                    mock.patch.object(self.pool, "jalon_chrono") as jalon:
                out, _err = self.capturer(self.pool.cmd_check, self.base, "T-7", False)
                self.assertEqual(jalon.call_count, attendu)
                self.assertTrue(out.startswith(f"T-7 {code}"), out)


class PlanPretAuGoDePlanning(unittest.TestCase):
    """La finalisation de /planning joue `plan_pool.py check` APRÈS le traçage du verdict : sans lui,
    l'attente du pilote est comptée en `planification` (exec-critic, T-01M5VZF47T9RT1YM9KC67HCQPP)."""

    def test_check_prescrit_apres_le_verdict_final(self):
        # kills « check retiré de la finalisation » et « check placé avant le verdict »
        texte = (ICI.parents[1] / ".agents" / "skills" / "planning" / "SKILL.md").read_text(encoding="utf-8")
        verdict = texte.index("puis **tracer le verdict** porteur de l'empreinte")
        paragraphe = texte[verdict:texte.index("\n\n", verdict)]
        self.assertIn("jouer `python core-scripts/plan_pool.py check T-NNNNNNNN`", paragraphe)
        self.assertIn("`plan-pret`", paragraphe)
        self.assertIn("`/night` sans ce check", paragraphe)
        self.assertIn("procédure deux comptes", texte)


class OrdreDoctrine(unittest.TestCase):
    """W13 (C8) : `ETAPES` suit l'ordre que kickoff.md recopie d'AGENTS.md."""

    def test_w13_etapes_dans_l_ordre_de_kickoff(self):
        texte = (ICI.parents[1] / ".claude" / "commands" / "kickoff.md").read_text(encoding="utf-8")
        debut = texte.index("dans l'ordre d'AGENTS.md")
        passage = texte[debut:texte.index("`done`", debut) + len("`done`")]
        cites = [m for m in re.findall(r"`([a-z-]+)`", passage) if m in tc.ETAPES]
        self.assertEqual(cites, list(tc.ETAPES))


if __name__ == "__main__":
    unittest.main()
