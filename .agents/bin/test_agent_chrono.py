"""Tests for agent_chrono.py — journal start/stop, durée, jetons estimés, relevé (T-01M55Z3ZCS34CDR2EQN1CEBHR7).

Racines temporaires (jamais le journal réel), horloge INJECTÉE partout (`now_ms`), import direct
(pytest met le dossier de ce fichier sur sys.path). Le format écrit est relu par `specs` : les
deux moitiés du contrat (`chrono:` écrit ici, lu là) sont liées par un aller-retour.
"""
import calendar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import agent_chrono
import specs

HERE = Path(__file__).resolve().parent
T0 = 1_791_000_000_000  # epoch ms fixé : aucune assertion ne dépend de l'heure


def transcript(chemin: Path, *usages: dict, bruit: bool = True) -> Path:
    lignes = []
    for u in usages:
        if bruit:
            lignes.append("pas du json")
            lignes.append(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}))
        lignes.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "usage": u}}))
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


DERNIER_TOUR = {"input_tokens": 2, "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 200_000, "output_tokens": 600}


class AgentChronoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.tr = transcript(self.root / "agent.jsonl",
                             {"input_tokens": 5, "cache_read_input_tokens": 99_999, "output_tokens": 50}, DERNIER_TOUR)

    def tearDown(self):
        self._tmp.cleanup()

    def journal(self) -> list:
        chemin = self.root / agent_chrono.JOURNAL_REL
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []

    def charge(self, aid="a95a44662445a70c8", agent="plan-critic", **extra):
        return {"agent_id": aid, "agent_type": agent, "agent_transcript_path": str(self.tr), **extra}

    def cycle(self, aid="a95a44662445a70c8", agent="plan-critic", duree_ms=192_000):
        self.assertTrue(agent_chrono.marquer_debut(self.root, self.charge(aid, agent), now_ms=T0))
        chrono = agent_chrono.chrono_de(self.root, self.charge(aid, agent), now_ms=T0 + duree_ms)
        self.assertTrue(agent_chrono.noter_fin(self.root, chrono, now_ms=T0 + duree_ms))
        return chrono

    # -- start + stop du même aid ------------------------------------------------

    def test_start_puis_stop_du_meme_aid_donne_duree_et_jetons(self):
        chrono = self.cycle()
        somme = sum(DERNIER_TOUR.values())
        self.assertEqual(chrono, {"aid": "a95a44662445a70c8", "agent": "plan-critic",
                                  "duration_ms": 192_000, "tokens": somme})
        self.assertEqual(self.journal(), [
            {"ev": "start", "aid": "a95a44662445a70c8", "agent": "plan-critic", "ts": T0},
            {"ev": "stop", "aid": "a95a44662445a70c8", "agent": "plan-critic", "ts": T0 + 192_000,
             "duration_ms": 192_000, "tokens": somme},
        ])
        self.assertEqual(agent_chrono.resoudre(self.root, "a95a44662445a70c8", "plan-critic"), (192, somme))

    def test_la_graphie_camelcase_est_lue(self):
        charge = {"agentId": "af8e4d9a-0536-414f-9d0f-9eea7fda1a67", "agentType": "planner",
                  "agentTranscriptPath": str(self.tr)}
        agent_chrono.marquer_debut(self.root, charge, now_ms=T0)
        chrono = agent_chrono.chrono_de(self.root, charge, now_ms=T0 + 5000)
        self.assertEqual((chrono["agent"], chrono["duration_ms"]), ("planner", 5000))

    def test_une_reprise_repart_de_son_dernier_depart(self):
        agent_chrono.marquer_debut(self.root, self.charge(), now_ms=T0)
        agent_chrono.marquer_debut(self.root, self.charge(), now_ms=T0 + 60_000)
        chrono = agent_chrono.chrono_de(self.root, self.charge(), now_ms=T0 + 90_000)
        self.assertEqual(chrono["duration_ms"], 30_000)

    def test_sans_depart_la_cle_duree_est_absente_jamais_zero(self):
        chrono = agent_chrono.chrono_de(self.root, self.charge(), now_ms=T0)
        self.assertNotIn("duration_ms", chrono)
        self.assertIn("tokens", chrono)
        agent_chrono.noter_fin(self.root, chrono, now_ms=T0)
        self.assertNotIn("duration_ms", self.journal()[-1])

    def test_un_depart_de_plus_de_sept_jours_ou_futur_ne_donne_pas_de_duree(self):
        agent_chrono.marquer_debut(self.root, self.charge(), now_ms=T0)
        trop_tard = agent_chrono.chrono_de(self.root, self.charge(), now_ms=T0 + agent_chrono.DUREE_MAX_MS + 1)
        avant = agent_chrono.chrono_de(self.root, self.charge(), now_ms=T0 - 1)
        self.assertNotIn("duration_ms", trop_tard)
        self.assertNotIn("duration_ms", avant)

    def test_aid_hors_forme_n_ecrit_ni_ne_lit_rien(self):
        for aid in ("../x", "a" * 65, "", None, 7):
            with self.subTest(aid=aid):
                self.assertFalse(agent_chrono.marquer_debut(self.root, self.charge(aid), now_ms=T0))
                self.assertEqual(agent_chrono.chrono_de(self.root, self.charge(aid), now_ms=T0), {})
        self.assertFalse(agent_chrono.noter_fin(self.root, {}, now_ms=T0))
        self.assertEqual(self.journal(), [])

    def test_un_stop_sans_agent_type_prend_le_nom_de_son_depart(self):
        # exec-critic : le filtre ne lisait que la charge du stop ; un départ NOMMÉ perdait sa fin et
        # `resoudre` disait « fin jamais relevée ». Le nom vient du départ du même aid.
        agent_chrono.marquer_debut(self.root, self.charge("p-nomme", "planner"), now_ms=T0)
        chrono = agent_chrono.chrono_de(self.root, {"agent_id": "p-nomme", "agent_transcript_path": str(self.tr)},
                                        now_ms=T0 + 60_000)
        self.assertEqual((chrono["agent"], chrono["duration_ms"]), ("planner", 60_000))
        self.assertTrue(agent_chrono.noter_fin(self.root, chrono, now_ms=T0 + 60_000))
        self.assertEqual(self.journal()[-1]["agent"], "planner")
        self.assertEqual(agent_chrono.resoudre(self.root, "p-nomme", "planner"), (60, sum(DERNIER_TOUR.values())))

    def test_une_reprise_sans_nouveau_depart_n_ecrit_pas_l_attente(self):
        # Sonde du 2026-10-19 : départ, stop à 60 s, stop à 690 s sans départ → 690 s écrits.
        agent_chrono.marquer_debut(self.root, self.charge("p-repris", "planner"), now_ms=T0)
        for fin in (60_000, 690_000):
            agent_chrono.noter_fin(self.root, agent_chrono.chrono_de(self.root, self.charge("p-repris", "planner"),
                                                                     now_ms=T0 + fin), now_ms=T0 + fin)
        self.assertEqual(self.journal()[1]["duration_ms"], 60_000)
        self.assertNotIn("duration_ms", self.journal()[2])
        with self.assertRaises(agent_chrono.ChronoErreur) as cm:
            agent_chrono.resoudre(self.root, "p-repris", "planner")
        self.assertIn("reprise sans nouveau départ", str(cm.exception))
        agent_chrono.marquer_debut(self.root, self.charge("p-repris", "planner"), now_ms=T0 + 700_000)
        chrono = agent_chrono.chrono_de(self.root, self.charge("p-repris", "planner"), now_ms=T0 + 730_000)
        agent_chrono.noter_fin(self.root, chrono, now_ms=T0 + 730_000)
        self.assertEqual(self.journal()[-1]["duration_ms"], 30_000, "une reprise AVEC départ garde sa durée")

    def test_un_stop_sans_agent_type_n_ecrit_rien_et_n_est_pas_releve(self):
        # Mesuré sur le journal live (2026-10-19, 13:02-14:10) : 155 stops sur 165 sans agent_type, ni départ,
        # ni transcript d'agent — agents internes de l'hôte. Irrésolubles (aucun rôle), ils rendaient une
        # ligne « ? » au relevé ; canal A et RUN_LOG les écartaient déjà (`if agent`).
        for charge in ({"agent_id": "a17de5be90c0f22b5"}, self.charge("a17de5be90c0f22b5", agent="  ")):
            with self.subTest(charge=charge):
                chrono = agent_chrono.chrono_de(self.root, charge, now_ms=T0)
                self.assertFalse(agent_chrono.noter_fin(self.root, chrono, now_ms=T0))
        self.assertEqual(self.journal(), [])
        chemin = self.root / agent_chrono.JOURNAL_REL  # un journal écrit avant ce filtre
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text('{"ev": "stop", "aid": "a17de5be90c0f22b5", "agent": "", "ts": %d}\n' % T0, encoding="utf-8")
        self.cycle("p1", "planner", 60_000)
        self.assertEqual(list(agent_chrono.releve_etapes(self.root)["agents"]), ["planner"])

    def test_les_fonctions_de_hook_ne_levent_jamais(self):
        bloque = self.root / "fichier"
        bloque.write_text("x", encoding="utf-8")  # un FICHIER là où le dossier d'état est attendu
        self.assertFalse(agent_chrono.marquer_debut(bloque, self.charge(), now_ms=T0))
        self.assertFalse(agent_chrono.noter_fin(bloque, {"aid": "a1"}, now_ms=T0))
        self.assertEqual(agent_chrono.chrono_de(self.root, "pas un dict", now_ms=T0), {})
        self.assertEqual(agent_chrono.lire_journal(bloque), [])

    # -- jetons du transcript d'agent -------------------------------------------

    def test_jetons_du_dernier_tour_jamais_une_somme_par_tour(self):
        self.assertEqual(agent_chrono.jetons_transcript(self.tr), sum(DERNIER_TOUR.values()))

    def test_jetons_inconnus_rendent_none(self):
        vide = self.root / "vide.jsonl"
        vide.write_text("", encoding="utf-8")
        sans_usage = transcript(self.root / "s.jsonl", {"input_tokens": True}, bruit=False)
        zero = transcript(self.root / "z.jsonl", {"output_tokens": 0}, bruit=False)
        for chemin in (None, "", str(self.root / "absent.jsonl"), vide, sans_usage, zero):
            with self.subTest(chemin=chemin):
                self.assertIsNone(agent_chrono.jetons_transcript(chemin))

    def test_la_queue_bornee_ignore_la_ligne_coupee(self):
        with mock.patch.object(agent_chrono, "QUEUE_TRANSCRIPT", len(self.tr.read_bytes()) - 5):
            self.assertEqual(agent_chrono.jetons_transcript(self.tr), sum(DERNIER_TOUR.values()))

    # -- résolution et show -------------------------------------------------------

    def test_chaque_cause_nomme_l_aid(self):
        agent_chrono.marquer_debut(self.root, self.charge("debut-seul"), now_ms=T0)
        agent_chrono.noter_fin(self.root, {"aid": "sans-duree", "agent": "planner", "tokens": 9}, now_ms=T0)
        agent_chrono.noter_fin(self.root, {"aid": "sans-jetons", "agent": "planner", "duration_ms": 9}, now_ms=T0)
        self.cycle("un-dev", "dev-multi")
        cas = {("inconnu", None): "inconnu du journal", ("debut-seul", None): "sans stop",
               ("sans-duree", None): "sans durée", ("sans-jetons", None): "sans jetons",
               ("un-dev", "planner"): "pas un planner", ("../x", None): "hors forme"}
        for (aid, role), cause in cas.items():
            with self.subTest(aid=aid), self.assertRaises(agent_chrono.ChronoErreur) as cm:
                agent_chrono.resoudre(self.root, aid, role)
            self.assertIn(aid, str(cm.exception))
            self.assertIn(cause, str(cm.exception))

    def test_un_journal_illisible_n_est_jamais_lu_aid_inconnu(self):
        (self.root / agent_chrono.JOURNAL_REL).mkdir(parents=True)  # un DOSSIER à la place du journal
        with self.assertRaises(agent_chrono.ChronoErreur) as cm:
            agent_chrono.resoudre(self.root, "a95a44662445a70c8")
        self.assertIn("illisible", str(cm.exception))
        self.assertNotIn("inconnu", str(cm.exception))
        self.assertEqual(agent_chrono.lire_journal(self.root), [], "un hook, lui, ne lève jamais")

    def test_show_imprime_duree_et_jetons_rc_1_sinon(self):
        self.cycle()
        cli = [sys.executable, "-B", str(HERE / "agent_chrono.py"), "--root", str(self.root), "show"]
        ok = subprocess.run([*cli, "a95a44662445a70c8"], capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "3m12s/201.6k"), ok.stderr)
        ko = subprocess.run([*cli, "inconnu"], capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual((ko.returncode, ko.stdout), (1, ""))
        self.assertIn("inconnu", ko.stderr)

    def test_formats_relus_par_specs(self):
        for sec in (1, 45, 192, 3600, 3723, 86_399):
            self.assertEqual(specs.parse_duree(agent_chrono.fmt_duree(sec)), sec)
        for n, attendu in ((850, "850"), (216_000, "216k"), (201_602, "201.6k"), (1_200_000, "1.2M")):
            self.assertEqual(agent_chrono.fmt_jetons(n), attendu)
            self.assertAlmostEqual(specs.parse_jetons(attendu), n, delta=50_000 if n >= 1_000_000 else 50)

    def test_champ_chrono_aller_retour_avec_specs(self):
        self.cycle("aid-planner", "planner", 47 * 60_000)
        self.cycle("aid-critique", "plan-critic", 192_000)
        champ, causes = agent_chrono.champ_chrono(self.root, {"planner": "aid-planner", "plan-critic": "aid-critique"})
        self.assertEqual(causes, [])
        self.assertEqual(champ, "chrono: planner=47m00s/201.6k plan-critic=3m12s/201.6k")
        self.assertEqual(specs.lire_chrono(champ), {"planner": (2820, 201_600), "plan-critic": (192, 201_600)})
        champ, causes = agent_chrono.champ_chrono(self.root, {"planner": "aid-planner", "plan-critic": "fantome"})
        self.assertIsNone(champ)
        self.assertEqual(len(causes), 1)
        self.assertIn("fantome", causes[0])

    def test_paires_chrono_exige_les_deux_roles_une_fois(self):
        self.assertEqual(agent_chrono.paires_chrono(["planner=a1", "plan-critic=b2"]),
                         {"planner": "a1", "plan-critic": "b2"})
        for valeurs in (["planner=a1"], ["planner=a1", "planner=a2", "plan-critic=b"], ["dev=a", "planner=b"],
                        ["planner", "plan-critic=b"], ["planner=", "plan-critic=b"]):
            with self.subTest(valeurs=valeurs), self.assertRaises(ValueError) as cm:
                agent_chrono.paires_chrono(valeurs)
            self.assertIn("--chrono-aid", str(cm.exception))

    def test_un_role_route_hors_claude_code_passe_sa_valeur_mesuree(self):
        lire = specs.lire_valeur_chrono
        self.assertEqual(agent_chrono.paires_chrono(["planner=12m30s/45.2k", "plan-critic=b2"], lire),
                         {"planner": (750, 45_200), "plan-critic": "b2"})
        self.assertEqual(agent_chrono.paires_chrono(["planner=12m", "plan-critic=b2"], lire)["planner"], "12m",
                         "la forme d'un aid est un aid : une valeur porte toujours `/`")
        for valeurs in (["planner=344s/0", "plan-critic=b2"], ["planner=0s/12k", "plan-critic=b2"],
                        ["planner=12m/x", "plan-critic=b2"], ["planner=a1", "plan-critic=../x"]):
            with self.subTest(valeurs=valeurs), self.assertRaises(ValueError) as cm:
                agent_chrono.paires_chrono(valeurs, lire)
            self.assertIn("jamais 0", str(cm.exception))
        with self.assertRaises(ValueError):  # sans lecteur, une valeur n'est jamais acceptée
            agent_chrono.paires_chrono(["planner=12m30s/45.2k", "plan-critic=b2"])
        self.cycle("aid-critique", "plan-critic", 192_000)
        champ, causes = agent_chrono.champ_chrono(self.root, {"planner": (750, 45_200), "plan-critic": "aid-critique"})
        self.assertEqual((champ, causes), ("chrono: planner=12m30s/45.2k plan-critic=3m12s/201.6k", []))
        self.assertEqual(specs.lire_chrono(champ), {"planner": (750, 45_200), "plan-critic": (192, 201_600)})

    # -- relevé par étape ---------------------------------------------------------

    def test_releve_par_agent_et_par_porte(self):
        self.cycle("p1", "planner", 60_000)
        self.cycle("p2", "planner", 180_000)
        agent_chrono.noter_fin(self.root, {"aid": "d1", "agent": "dev-multi"}, now_ms=T0)
        # Les trois modes que verify.sh écrit ; mélangées, les vertes auraient UNE médiane (900).
        (self.root / agent_chrono.PORTE_REL).write_text(
            "2026-10-19T10:00:00Z\t600\tabc1234\tlive\t0\n2026-10-19T11:00:00Z\t300\tabc1234\tfrozen\t1\n"
            "ligne cassée\n2026-10-19T12:00:00Z\t900\tdef5678\tfrozen\t0\n"
            "2026-10-19T13:00:00Z\t1200\tdef5678\tfrozen-linux\t0\n"
            # 6 colonnes (T-01M5PVWF7H) : une verte (`-`) et une rouge notée à son étape. Lues
            # TOUTES LES DEUX, à côté des lignes à 5 colonnes d'avant : un lecteur resté à
            # `len != 5` les jetterait (vertes 3, rouges 1, aucune clé `pytest`).
            "2026-10-19T14:00:00Z\t700\tghi9012\tlive\t0\t-\n"
            "2026-10-19T15:00:00Z\t400\tghi9012\tfrozen\t1\tpytest\n", encoding="utf-8")
        releve = agent_chrono.releve_etapes(self.root)
        self.assertEqual(releve["agents"]["planner"], {"stops": 2, "mesures": 2, "duree_mediane": 120,
                                                       "duree_p90": 180, "jetons_mediane": 201_602})
        self.assertEqual(releve["agents"]["dev-multi"], {"stops": 1, "mesures": 0})
        self.assertEqual(releve["portes"], {"vertes": 4, "rouges": 2, "modes": {
            "frozen": {"vertes": 1, "rouges": 2, "duree_mediane": 900, "duree_p90": 900},
            "frozen-linux": {"vertes": 1, "rouges": 0, "duree_mediane": 1200, "duree_p90": 1200},
            "live": {"vertes": 2, "rouges": 0, "duree_mediane": 650, "duree_p90": 700}},
            "rouges_par_etape": {"non noté": 1, "pytest": 1}})
        texte = agent_chrono.render_etapes(releve)
        self.assertIn("4 vertes, 2 rouges", texte)
        self.assertIn("frozen-linux : 1 vertes, 0 rouges ; durée médiane 20m00s", texte)
        self.assertIn("rouges par étape (6e colonne ; « non noté » : ligne à 5 colonnes) : non noté 1, pytest 1", texte)
        self.assertNotIn(" 0s", texte, "une étape sans mesure n'a jamais de durée nulle")
        vide = agent_chrono.releve_etapes(self.root / "nulle-part")
        self.assertEqual(vide, {"agents": {}, "portes": {"vertes": 0, "rouges": 0, "modes": {},
                                                         "rouges_par_etape": {}}})
        self.assertNotIn("rouges par étape", agent_chrono.render_etapes(vide))

    @unittest.skipUnless(hasattr(time, "tzset"), "fuseau non forçable (time.tzset absent) : --depuis non joué")
    def test_depuis_un_seul_jour_local_pour_specs_agents_et_portes(self):
        # Le MÊME instant, 2026-10-19T23:30:00Z (01:30 le 20 à Paris), écrit dans les TROIS sources :
        # l'entrée SPECS datée de son jour LOCAL (comme `date.today()`), le stop (epoch ms), la porte
        # (ISO UTC). `specs.py chrono --etapes --depuis` les compte ensemble ou pas du tout.
        instant_ms = calendar.timegm((2026, 10, 19, 23, 30, 0)) * 1000
        for chemin in (specs.store_path(self.root), specs.view_path(self.root)):
            chemin.parent.mkdir(parents=True, exist_ok=True)
        specs.add_entry(self.root, "T-00000001", "verdict", "plan-critic GO (iteration 1/8)", "plan=x.md")
        data = specs.load(self.root)
        data["entries"][0]["date"] = "2026-10-20"
        specs.save(self.root, data)
        agent_chrono.noter_fin(self.root, {"aid": "p1", "agent": "planner", "duration_ms": 60_000}, now_ms=instant_ms)
        (self.root / agent_chrono.PORTE_REL).write_text("2026-10-19T23:30:00Z\t600\tabc1234\tfrozen\t0\n",
                                                        encoding="utf-8")

        def compte(depuis):
            run = subprocess.run([sys.executable, "-B", str(HERE / "specs.py"), "--root", str(self.root), "chrono",
                                  "--etapes", "--json", "--depuis", depuis], capture_output=True, text=True,
                                 timeout=60, check=False, env={**os.environ, "TZ": "Europe/Paris"})
            self.assertEqual(run.returncode, 0, run.stderr)
            sortie = json.loads(run.stdout)
            agents = sortie["etapes"]["agents"]
            return (sortie["ensemble"]["tours"], agents.get("planner", {}).get("stops", 0),
                    sortie["etapes"]["portes"]["vertes"])

        self.assertEqual(compte("2026-10-20"), (1, 1, 1), "un instant compté par une source, pas par les autres")
        self.assertEqual(compte("2026-10-21"), (0, 0, 0))

    @unittest.skipUnless(shutil.which("git"), "git absent : racine_commune non jouée")
    def test_racine_commune_meme_regle_que_l_ecrivain_verify_sh(self):
        # Les configurations où l'écrivain (core-scripts/verify.sh, bloc CHRONO_ROOT) a été mesuré ;
        # core-scripts/verify.test.sh (arm 11a) joue écrivain ET lecteur sur les mêmes.
        r = self.root
        hors = r / "hors-git"
        hors.mkdir()
        sans_git = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

        def git(cwd, *args):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "protocol.file.allow=always",
                            *args], cwd=cwd, env=sans_git, check=True, capture_output=True)

        git(r, "init", "-q", "depot")
        git(r / "depot", "commit", "-q", "--allow-empty", "-m", "x")
        git(r / "depot", "worktree", "add", "-q", "--detach", str(r / "lie"))
        git(r, "init", "-q", "super")
        git(r / "super", "submodule", "add", "-q", str(r / "depot"), "sub")
        git(r / "super" / "sub", "worktree", "add", "-q", "--detach", str(r / "sublie"))
        git(r, "clone", "-q", "--separate-git-dir", str(r / "gitsep"), str(r / "depot"), "sep")
        git(r / "sep", "worktree", "add", "-q", "--detach", str(r / "seplie"))
        attendu = {"depot": "depot", "lie": "depot", "super/sub": "super/sub", "sublie": "super/sub",
                   "sep": "sep", "seplie": "seplie"}  # seplie : git n'enregistre pas le principal (borne dite)
        with mock.patch.dict(os.environ, sans_git, clear=True):
            for depuis, vers in attendu.items():
                with self.subTest(depuis=depuis):
                    self.assertEqual(agent_chrono.racine_commune(r / depuis).resolve(), (r / vers).resolve())
            self.assertEqual(agent_chrono.racine_commune(hors), hors)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW absent : lien non refusable ici")
    def test_un_journal_lien_symbolique_n_est_pas_suivi(self):
        cible = self.root / "ailleurs.txt"
        cible.write_text("intact\n", encoding="utf-8")
        journal = self.root / agent_chrono.JOURNAL_REL
        journal.parent.mkdir(parents=True)
        journal.symlink_to(cible)
        self.assertFalse(agent_chrono.marquer_debut(self.root, self.charge(), now_ms=T0))
        self.assertEqual(cible.read_text(encoding="utf-8"), "intact\n")


class PlanTraceChargeTests(unittest.TestCase):
    """`plan_trace.py` en sous-processus : la charge porte aid/durée quand le module répond, et
    reste EXACTEMENT `{at, sha, role}` quand il manque ou lève (chargeur ET appel sous `try`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def jouer(self, module: str | None) -> dict:
        kit = self.base / f"kit-{module}"
        (kit / ".agents" / "bin").mkdir(parents=True)
        shutil.copy2(HERE / "plan_trace.py", kit / ".agents" / "bin" / "plan_trace.py")
        if module == "vrai":
            shutil.copy2(HERE / "agent_chrono.py", kit / ".agents" / "bin" / "agent_chrono.py")
        elif module == "leve":
            (kit / ".agents" / "bin" / "agent_chrono.py").write_text("raise RuntimeError('cassé')\n", encoding="utf-8")
        racine = self.base / f"etat-{module}"
        agent_chrono.marquer_debut(racine, {"agent_id": "aid-critique", "agent_type": "plan-critic"},
                                   now_ms=agent_chrono._maintenant_ms() - 4000)
        charge = {"hook_event_name": "SubagentStop", "agent_type": "plan-critic", "agent_id": "aid-critique"}
        run = subprocess.run([sys.executable, "-B", str(kit / ".agents" / "bin" / "plan_trace.py")],
                             input=json.dumps(charge), capture_output=True, text=True, timeout=60, check=False,
                             env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(racine)})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((kit / ".agents" / "bin" / "__pycache__").exists(), "le chargeur a écrit un .pyc")
        return json.loads((racine / ".agents" / "state" / "local" / "plan" / "plan-critic.json").read_text(encoding="utf-8"))

    def test_module_present_la_charge_porte_aid_et_duree(self):
        charge = self.jouer("vrai")
        self.assertEqual(charge["aid"], "aid-critique")
        self.assertGreaterEqual(charge["duration_ms"], 4000)
        self.assertEqual(charge["role"], "reviewer")

    def test_module_absent_ou_qui_leve_la_charge_reste_exacte(self):
        for module in ("absent", "leve"):
            with self.subTest(module=module):
                self.assertEqual(set(self.jouer(module)), {"at", "sha", "role"})


if __name__ == "__main__":
    unittest.main()
