"""Tests for specs.py — le champ `chrono:` d'un verdict de boucle, sa PRÉSENCE et sa casse.

Banc FRÈRE de test_specs.py (qui touche sa borne de 1 600 lignes), même style : racines
temporaires (jamais le SPECS suivi), import direct (pytest met le dossier de ce fichier sur
sys.path). Revue de clôture critic-opus du lot e47f77cc..bbf26b6f, deux mineurs :

  (a) un champ chrono n'est PRÉSENT que sur `chrono:` suivi d'un rôle (`planner=` ou
      `plan-critic=`). MESURÉ avant : `re.search(r"chrono\\s*:")` prenait une prose (« chrono:
      non mesuré (Codex) ») pour un champ, et la refusait ILLISIBLE même `CHRONO_REQUIRED`
      désarmé — une règle désarmée qui mord. Armé, la même prose reste refusée, comme ABSENTE ;
  (b) la durée se lit sans casse, comme le reste du champ (`_CHRONO_RE` est déjà IGNORECASE) :
      MESURÉ avant, `3M12S` passait le motif du champ puis échouait au parseur de durée.

LE TOUR D'UN LOT (T-01M54GE4K9EZRRQFD9TAVNWYKM, lot L) : `lot <K> : plan-critic <VERDICT> (iteration n/N)`
est un verdict de boucle — chrono exigé sous marqueur, champ illisible refusé, `--sans-chrono` admis, tour
compté par `chrono` à sa tâche. Ne le sont PAS : `lot A : plan-critic-opus`, une clé hors
`[A-Z][A-Z0-9]{0,3}`, un `lot A :` qui n'ouvre pas le titre, un kind autre que `verdict`.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import specs


def make_root(tmp_path: Path) -> Path:
    specs.store_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    specs.view_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    return tmp_path


class _RacineChrono(unittest.TestCase):
    """Racine temporaire, marqueur et CLI — partagés, aucun test ici."""
    T = "T-00000001"
    # Le marqueur est ÉCRIT EN DUR, jamais relu depuis `specs` (L-00000057, comme test_specs).
    MARQUEUR = Path(".agents/state/gates/CHRONO_REQUIRED")

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _arme(self):
        (self.root / self.MARQUEUR).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.MARQUEUR).write_text("", encoding="utf-8")

    def _cli(self, *args):
        return subprocess.run([sys.executable, str(Path(specs.__file__).resolve()), "--root", str(self.root), *args],
                              capture_output=True, text=True)


class SpecsChronoPresenceTests(_RacineChrono):
    PROSES = ("chrono: non mesuré (Codex)", "plan=x.md ; le chrono: à relever au prochain tour",
              "CHRONO: hôte muet")

    def test_une_prose_n_est_pas_un_champ_sans_marqueur(self):
        for texte in self.PROSES:
            with self.subTest(texte=texte):
                specs.add_entry(self.root, self.T, "verdict", "plan-critic GO", texte)
        cp = self._cli("add", "plan-critic NO_GO", "--task", self.T, "--kind", "verdict", "--text", self.PROSES[0])
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual([e["text"] for e in specs.load(self.root)["entries"]], [*self.PROSES, self.PROSES[0]])

    def test_une_prose_reste_refusee_sous_marqueur_comme_absente(self):
        self._arme()
        for texte in self.PROSES:
            with self.subTest(texte=texte), self.assertRaises(specs.SpecsError) as cm:
                specs.add_entry(self.root, self.T, "verdict", "plan-critic GO", texte)
            self.assertEqual(str(cm.exception), specs.REFUS_CHRONO_ABSENT)
        self.assertEqual(specs.load(self.root)["entries"], [], "un refus n'écrit rien")

    def test_un_champ_present_mais_illisible_reste_refuse_sans_marqueur(self):
        # Le rétrécissement de la présence ne doit rien lâcher d'un champ qui NOMME un rôle.
        for texte in ("chrono: planner=vite/beaucoup plan-critic=1m/1k", "chrono: plan-critic=1m/1k",
                      "CHRONO:  Planner=3x/1k plan-critic=1m/1k", "x ; chrono:planner=1m/1.2.3k plan-critic=1m/1k"):
            with self.subTest(texte=texte), self.assertRaises(specs.SpecsError) as cm:
                specs.add_entry(self.root, self.T, "verdict", "plan-critic GO", texte)
            self.assertEqual(str(cm.exception), specs.REFUS_CHRONO_ILLISIBLE)

    def test_la_duree_se_lit_sans_casse(self):
        self.assertEqual([specs.parse_duree(d) for d in ("3M12S", "1H2M", "45S", "7MIN", "7Min", "3m12S")],
                         [192, 3720, 45, 420, 420, 192])
        self.assertEqual([specs.parse_duree(d) for d in ("3X", "M", "1H2H")], [None] * 3)
        texte = "plan=x.md ; chrono: planner=3M12S/45.2K plan-critic=1M/12000"
        self.assertEqual(specs.lire_chrono(texte), {"planner": (192, 45200), "plan-critic": (60, 12000)})
        self._arme()
        specs.add_entry(self.root, self.T, "verdict", "plan-critic GO (iteration 1/8)", texte)
        self.assertEqual([e["text"] for e in specs.load(self.root)["entries"]], [texte])

    def test_un_role_a_zero_n_est_pas_une_mesure(self):
        # critic-opus T2 : `planner=344s/0` était lu (344, 0) et compté MESURÉ — 26 verdicts du kit.
        for texte in ("chrono: planner=344s/0 plan-critic=1082s/216k", "chrono: planner=0s/12k plan-critic=1m/1k",
                      "chrono: planner=1m/1k plan-critic=0:00/1k"):
            with self.subTest(texte=texte):
                self.assertIsNone(specs.lire_chrono(texte))
        self.assertIn("jamais `0`", specs.FORMAT_CHRONO)
        self._arme()
        cp = self._cli("add", "plan-critic GO", "--task", self.T, "--kind", "verdict",
                       "--text", "chrono: planner=344s/0 plan-critic=1082s/216k")
        self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertIn(specs.REFUS_CHRONO_ILLISIBLE, cp.stderr)
        self.assertEqual(specs.load(self.root)["entries"], [], "un refus n'écrit rien")


class SpecsChronoAidTests(_RacineChrono):
    """`--chrono-aid planner=<aid> --chrono-aid plan-critic=<aid>` (T-01M55Z3ZCS34CDR2EQN1CEBHR7) : le
    champ s'écrit DEPUIS le journal. Le journal est écrit EN DUR ici (forme du contrat), jamais par le
    module sous test : un format qui dériverait des deux côtés à la fois ne passerait pas vert."""
    JOURNAL = Path(".agents/state/local/agent-chrono.jsonl")
    AIDS = ("--chrono-aid", "planner=ap1", "--chrono-aid", "plan-critic=ac1")

    def _journal(self, *lignes):
        (self.root / self.JOURNAL).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.JOURNAL).write_text("".join(json.dumps(l) + "\n" for l in lignes), encoding="utf-8")

    def _deux_stops(self):
        self._journal({"ev": "start", "aid": "ap1", "agent": "planner", "ts": 1},
                      {"ev": "stop", "aid": "ap1", "agent": "planner", "ts": 2, "duration_ms": 2_820_000, "tokens": 308_000},
                      {"ev": "stop", "aid": "ac1", "agent": "plan-critic", "ts": 3, "duration_ms": 192_000, "tokens": 216_000})

    def _add(self, *extra, texte="plan=x.md"):
        return self._cli("add", "plan-critic GO (iteration 1/8)", "--task", self.T, "--kind", "verdict",
                         "--text", texte, *extra)

    def test_les_deux_aids_resolus_ecrivent_le_champ_relu(self):
        self._deux_stops()
        self._arme()
        cp = self._add(*self.AIDS)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        (texte,) = [e["text"] for e in specs.load(self.root)["entries"]]
        self.assertEqual(texte, "plan=x.md ; chrono: planner=47m00s/308k plan-critic=3m12s/216k")
        self.assertEqual(specs.lire_chrono(texte), {"planner": (2820, 308_000), "plan-critic": (192, 216_000)})

    def test_un_role_route_hors_claude_code_passe_sa_valeur_a_cote_d_un_aid(self):
        # critic-opus T3 : planner Codex + critique Claude n'avaient que la saisie entière ou --sans-chrono.
        self._deux_stops()
        self._arme()
        cp = self._add("--chrono-aid", "planner=12m30s/45.2k", "--chrono-aid", "plan-critic=ac1")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        (texte,) = [e["text"] for e in specs.load(self.root)["entries"]]
        self.assertEqual(texte, "plan=x.md ; chrono: planner=12m30s/45.2k plan-critic=3m12s/216k")
        for valeur in ("planner=344s/0", "planner=12m/beaucoup"):
            with self.subTest(valeur=valeur):
                cp = self._add("--chrono-aid", valeur, "--chrono-aid", "plan-critic=ac1")
                self.assertEqual(cp.returncode, 2, cp.stderr)
                self.assertIn("jamais 0", cp.stderr)
        self.assertEqual(len(specs.load(self.root)["entries"]), 1, "un refus n'écrit rien")

    def test_aid_inconnu_arme_rc_2_nomme_l_aid_et_la_sortie_rien_ecrit(self):
        self._journal({"ev": "stop", "aid": "ap1", "agent": "planner", "ts": 2, "duration_ms": 9000, "tokens": 9},
                      {"ev": "stop", "aid": "ac1", "agent": "plan-critic", "ts": 3, "tokens": 9})  # sans durée
        self._arme()
        for aids, nomme in ((("--chrono-aid", "planner=fantome", "--chrono-aid", "plan-critic=ap1"), "fantome"),
                            (self.AIDS, "ac1")):
            with self.subTest(nomme=nomme):
                cp = self._add(*aids)
                self.assertEqual(cp.returncode, 2, cp.stderr)
                self.assertIn(nomme, cp.stderr)
                self.assertIn("--sans-chrono", cp.stderr)
                self.assertIn("Relance après la fin de l'agent", cp.stderr)
        self.assertEqual(specs.load(self.root)["entries"], [], "un refus n'écrit rien")
        self.assertFalse(any("0s/0" in e["text"] for e in specs.load(self.root)["entries"]))

    def test_roles_inverses_arme_rc_2_remede_propre_jamais_relancer(self):
        self._deux_stops()
        self._arme()
        cp = self._add("--chrono-aid", "planner=ac1", "--chrono-aid", "plan-critic=ap1")
        self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertIn("planner=<aid du planner> plan-critic=<aid du critique>", cp.stderr)
        self.assertNotIn("Relance après la fin", cp.stderr, "les deux agents sont finis : relancer ne résout rien")
        self.assertEqual(specs.load(self.root)["entries"], [])

    def test_aid_inconnu_non_arme_rc_0_avertit_et_ecrit_sans_chrono(self):
        cp = self._add("--chrono-aid", "planner=fantome", "--chrono-aid", "plan-critic=spectre")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("AVERTISSEMENT", cp.stderr)
        self.assertIn("fantome", cp.stderr)
        self.assertIn("spectre", cp.stderr)
        self.assertEqual([e["text"] for e in specs.load(self.root)["entries"]], ["plan=x.md"])

    def test_double_champ_et_formes_refusees_rc_2(self):
        self._deux_stops()
        cas = {
            "chrono déjà au texte": self._add(*self.AIDS, texte="chrono: planner=1m/1k plan-critic=1m/1k"),
            "avec --sans-chrono": self._add(*self.AIDS, "--sans-chrono", "hôte muet"),
            "un seul rôle": self._add("--chrono-aid", "planner=ap1"),
            "rôle inconnu": self._add("--chrono-aid", "dev=ap1", "--chrono-aid", "plan-critic=ac1"),
            "verdict hors boucle": self._cli("add", "security-code-review CLEAN", "--task", self.T,
                                             "--kind", "verdict", *self.AIDS),
        }
        for nom, cp in cas.items():
            with self.subTest(cas=nom):
                self.assertEqual(cp.returncode, 2, cp.stderr)
                self.assertIn("--chrono-aid", cp.stderr)
        self.assertEqual(specs.load(self.root)["entries"], [])

    def test_chrono_nu_inchange_etapes_en_plus(self):
        self._deux_stops()
        nu, etapes = self._cli("chrono"), self._cli("chrono", "--etapes")
        self.assertEqual((nu.returncode, etapes.returncode), (0, 0), nu.stderr + etapes.stderr)
        self.assertNotIn("durées par agent", nu.stdout)
        self.assertTrue(etapes.stdout.startswith(nu.stdout.rstrip("\n")), "--etapes AJOUTE, ne remplace pas")
        self.assertIn("plan-critic", etapes.stdout.split("durées par agent")[1])
        self.assertNotIn("etapes", json.loads(self._cli("chrono", "--json").stdout))
        agents = json.loads(self._cli("chrono", "--etapes", "--json").stdout)["etapes"]["agents"]
        self.assertEqual(agents["planner"]["duree_mediane"], 2820)

    def test_etapes_avec_task_le_dit_sur_stderr(self):
        # critic-opus T6 : `--task T --etapes` imprimait le journal ENTIER sous l'en-tête de la tâche, sans le dire.
        self._deux_stops()
        avec = self._cli("chrono", "--task", self.T, "--etapes")
        self.assertEqual(avec.returncode, 0, avec.stderr)
        self.assertIn("AVERTISSEMENT — --etapes relève le journal ENTIER", avec.stderr)
        for args in (("chrono", "--etapes"), ("chrono", "--task", self.T)):
            with self.subTest(args=args):
                self.assertNotIn("AVERTISSEMENT", self._cli(*args).stderr)

    def test_depuis_hors_forme_rc_2_lisible_avec_et_sans_etapes(self):
        # `date.fromisoformat` admet `20261020` depuis Python 3.11 : sans --etapes un 0 tours muet, avec,
        # un traceback d'agent_chrono. La forme est AAAA-MM-JJ et rien d'autre : `strptime` seul admet
        # `2026-10-5`, que SPECS compare en chaîne et agents/portes en instant — trois sources divergentes.
        self._deux_stops()
        for depuis in ("20261020", "2026-W43-2", "2026-13-01", "2026-10-5", "2026-1-05", " 2026-10-05"):
            for etapes in ((), ("--etapes",)):
                with self.subTest(depuis=depuis, etapes=etapes):
                    cp = self._cli("chrono", *etapes, "--depuis", depuis)
                    self.assertEqual(cp.returncode, 2, cp.stdout + cp.stderr)
                    self.assertIn("AAAA-MM-JJ", cp.stderr)
                    self.assertNotIn("Traceback", cp.stderr)
        self.assertEqual(self._cli("chrono", "--etapes", "--depuis", "2026-10-20").returncode, 0)


class SpecsChronoTourDeLotTests(unittest.TestCase):
    T = "T-00000001"
    MARQUEUR = Path(".agents/state/gates/CHRONO_REQUIRED")  # écrit en dur (L-00000057)
    CH = "plan=docs/tasks/T-00000001-lot-A-plan.md ; chrono: planner=2m/10k plan-critic=1m/5k"
    LOT = ("lot A : plan-critic NO_GO (iteration 1/2)", "lot B12 : plan-critic GO (iteration 2/2)",
           "  LOT C: plan-critic GO_AVEC_RESERVES", "lot D :plan-critic GO")
    HORS = ("lot A : plan-critic-opus GO", "lot AB12C : plan-critic GO", "lot : plan-critic GO",
            "note lot A : plan-critic GO", "lot A : Plan @ abc1234 - lot A", "lot A plan-critic GO",
            "lot A : plan-critics GO")

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _arme(self):
        (self.root / self.MARQUEUR).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.MARQUEUR).write_text("", encoding="utf-8")

    def _cli(self, *args):
        return subprocess.run([sys.executable, str(Path(specs.__file__).resolve()), "--root", str(self.root), *args],
                              capture_output=True, text=True)

    def test_le_tour_de_lot_est_un_verdict_de_boucle(self):
        for titre in self.LOT:
            with self.subTest(titre=titre):
                self.assertTrue(specs.est_verdict_de_boucle("verdict", titre))
                self.assertFalse(specs.est_verdict_de_boucle("plan", titre))
        for titre in self.HORS:
            with self.subTest(titre=titre):
                self.assertFalse(specs.est_verdict_de_boucle("verdict", titre))

    def test_sous_marqueur_le_tour_de_lot_sans_chrono_est_refuse(self):
        self._arme()
        with self.assertRaises(specs.SpecsError) as cm:
            specs.add_entry(self.root, self.T, "verdict", self.LOT[0], "plan=docs/tasks/x.md")
        self.assertEqual(str(cm.exception), specs.REFUS_CHRONO_ABSENT)
        self.assertIn("lot <K> : plan-critic", str(cm.exception))
        self.assertEqual(specs.load(self.root)["entries"], [], "un refus n'écrit rien")
        specs.add_entry(self.root, self.T, "verdict", self.LOT[0], self.CH)
        self.assertEqual([e["title"] for e in specs.load(self.root)["entries"]], [self.LOT[0]])

    def test_hors_boucle_le_meme_titre_mal_forme_reste_libre_sous_marqueur(self):
        self._arme()
        for titre in self.HORS:
            with self.subTest(titre=titre):
                specs.add_entry(self.root, self.T, "verdict", titre, "sans chrono")
        specs.add_entry(self.root, self.T, "plan", self.LOT[0], "kind plan : pas un tour")
        self.assertEqual(len(specs.load(self.root)["entries"]), len(self.HORS) + 1)

    def test_champ_illisible_refuse_sur_un_tour_de_lot_meme_sans_marqueur(self):
        with self.assertRaises(specs.SpecsError) as cm:
            specs.add_entry(self.root, self.T, "verdict", self.LOT[1], "chrono: planner=vite/1k plan-critic=1m/1k")
        self.assertEqual(str(cm.exception), specs.REFUS_CHRONO_ILLISIBLE)

    def test_sans_chrono_admis_sur_un_tour_de_lot_et_visible(self):
        self._arme()
        cp = self._cli("add", self.LOT[0], "--task", self.T, "--kind", "verdict", "--text", "plan=x.md",
                       "--sans-chrono", "hôte muet (Codex)")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("[SANS CHRONO : hôte muet (Codex)]", specs.load(self.root)["entries"][0]["text"])

    def test_sans_chrono_hors_boucle_refuse_et_le_message_nomme_les_deux_formes(self):
        with self.assertRaises(specs.SpecsError) as cm:
            specs.add_entry(self.root, self.T, "verdict", self.HORS[0], "x", sans_chrono="hors boucle")
        self.assertIn("ne vaut que pour un verdict titré `plan-critic …` ou `lot <K> : plan-critic …`",
                      str(cm.exception))

    def test_chrono_compte_les_tours_de_lot_a_leur_tache(self):
        specs.add_entry(self.root, self.T, "verdict", "plan-critic GO (iteration 1/2)",
                        "chrono: planner=4m/20k plan-critic=2m/10k")
        specs.add_entry(self.root, self.T, "verdict", self.LOT[0], self.CH)
        specs.add_entry(self.root, self.T, "verdict", self.LOT[1], "plan=x.md", sans_chrono="hôte muet")
        specs.add_entry(self.root, self.T, "verdict", self.HORS[0], self.CH)  # pas un tour
        releve = specs.chrono_releve(specs.load(self.root)["entries"], task=self.T)
        self.assertEqual(releve["taches"][self.T], {"tours": 3, "mesures": 2, "duree": 540, "jetons": 45000})
        self.assertEqual(releve["ensemble"]["non_mesures"], 1)


class AliasAnglais(_RacineChrono):
    """T-01M5QC86XNEJ5NEX6DGZJ0AJZ5, lot G : nom anglais en tête, ancien nom français GARDÉ en alias,
    `dest` ancien EXPLICITE — sinon argparse dérive `dest` de l'anglais et `args.sans_chrono` (…)
    n'existe plus (annexe § B2). Chaque paire anglais/ancien doit poser la MÊME valeur au même champ."""
    PAIRES_ADD = (("--without-target", "--sans-cible", "sans_cible"),
                  ("--without-deps", "--sans-dependances", "sans_dependances"),
                  ("--without-chrono", "--sans-chrono", "sans_chrono"))

    def _main_en_place(self, cible, *argv):
        """`specs.main` en processus, `cible` remplacée par un enregistreur : lit ce que l'argv a posé."""
        from unittest import mock
        with mock.patch.object(specs, cible) as rec, mock.patch.object(specs, "force_utf8_stdio"), \
                mock.patch.object(specs, "avertissement_de_forme", return_value=""):
            rec.return_value = [] if cible == "migrate_store" else "ok"
            rc = specs.main(["--root", str(self.root), *argv])
        self.assertEqual(rc, 0)
        return rec.call_args

    def test_chaque_drapeau_d_add_pose_le_dest_ancien_sous_ses_deux_noms(self):
        for anglais, ancien, dest in self.PAIRES_ADD:
            for nom in (anglais, ancien):
                with self.subTest(nom=nom):
                    appel = self._main_en_place("add_entry", "add", "t", "--task", self.T, "--kind", "verdict",
                                                nom, "pourquoi")
                    self.assertEqual(appel.kwargs[dest], "pourquoi")

    def test_unmigrated_readers_pose_le_dest_ancien_sous_ses_deux_noms(self):
        for nom in ("--unmigrated-readers", "--lecteurs-non-migres"):
            with self.subTest(nom=nom):
                self.assertEqual(self._main_en_place("migrate_store", "migrate", nom, "pourquoi").args[2], "pourquoi")

    def test_without_chrono_sous_marqueur_admis_et_visible(self):
        self._arme()
        cp = self._cli("add", "plan-critic GO (iteration 1/8)", "--task", self.T, "--kind", "verdict",
                       "--text", "plan=x.md", "--without-chrono", "hôte muet (Codex)")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("[SANS CHRONO : hôte muet (Codex)]", specs.load(self.root)["entries"][0]["text"])

    def test_since_et_steps_valent_depuis_et_etapes(self):
        specs.add_entry(self.root, self.T, "verdict", "plan-critic GO (iteration 1/2)",
                        "chrono: planner=4m/20k plan-critic=2m/10k")
        for anglais, ancien in ((("--since", "2026-01-01"), ("--depuis", "2026-01-01")),
                                (("--steps",), ("--etapes",)), (("--since", "2999-01-01"), ("--depuis", "2999-01-01"))):
            with self.subTest(anglais=anglais):
                a, b = self._cli("chrono", "--json", *anglais), self._cli("chrono", "--json", *ancien)
                self.assertEqual((a.returncode, a.stdout), (0, b.stdout), a.stderr)
        self.assertEqual(json.loads(self._cli("chrono", "--json", "--since", "2999-01-01").stdout)["taches"], {})
        cp = self._cli("chrono", "--since", "20261020")
        self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertIn("AAAA-MM-JJ", cp.stderr)
        aide = self._cli("chrono", "--help").stdout
        self.assertLess(aide.index("--since"), aide.index("--depuis"), "le nom anglais vient en tête")

    def test_aides_imprimables_sous_un_terminal_ascii(self):
        """L'aide s'imprime AVANT `force_utf8_stdio` : un caractère non ASCII y lève UnicodeEncodeError."""
        import os
        env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHON_COLORS": "0", "NO_COLOR": "1"}
        env.pop("FORCE_COLOR", None)
        for verbe in ([], ["add"], ["migrate"], ["chrono"], ["list"], ["render"]):
            with self.subTest(verbe=verbe):
                cp = subprocess.run([sys.executable, str(Path(specs.__file__).resolve()), "--root", str(self.root),
                                     *verbe, "--help"], capture_output=True, text=True, env=env)
                self.assertEqual(cp.returncode, 0, cp.stderr)
                self.assertTrue(cp.stdout.isascii())
                # T-01M5QC86XN : metavars en anglais ; un nom francais qui revient rougit ici.
                for ancien in ("POURQUOI", "AAAA-MM-JJ"):
                    self.assertNotIn(ancien, cp.stdout)
        for verbe, nouveau in ((["add"], "WHY"), (["chrono"], "YYYY-MM-DD"), (["migrate"], "WHY")):
            cp = subprocess.run([sys.executable, str(Path(specs.__file__).resolve()), "--root", str(self.root),
                                 *verbe, "--help"], capture_output=True, text=True, env=env)
            self.assertIn(nouveau, cp.stdout, verbe)


if __name__ == "__main__":
    unittest.main()
