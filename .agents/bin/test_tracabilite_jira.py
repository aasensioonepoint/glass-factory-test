#!/usr/bin/env python3
"""BANC de `tracabilite_jira.py` (T-01M5A113J9NF1BQ9KSTJHNWT9H) — témoins J1-J11 de l'annexe § F du plan D3.

AUCUN vrai Jira : chaque envoi vise un serveur BOUCHON (`http.server` en fil, sur 127.0.0.1, port libre), et les
jambes en processus remplacent l'ouverture réseau par un piège qui lève. Le board est JETABLE (`tasks.py --root`
sur un dossier temporaire, `CADRE_STATE_DIR`, `AGENTS_EVENTS_DIR` et `HOME` jetables), commité dans un dépôt git
jetable pour que J10 relise « rien d'écrit » par `git status --ignored`.

Jeton de banc : `jeton-de-banc-0001`, jamais en forme de credential ; adresses en `example.invalid`.
Chaque jambe réseau tourne dans un environnement NETTOYÉ des marqueurs d'agent (tuple de référence :
`skills_github_fallback.AGENT_CALLER_MARKERS`) et des variables de proxy.

BORNES NOMMÉES : J10 relit la racine jetable (git, fichiers ignorés compris), `HOME` et le dossier courant du
processus ; il ne relit ni le reste du disque ni l'intérieur des dossiers d'état machine jetables (premier niveau
seul). J11 saute, en le DISANT, si `/usr/bin/python3` manque ou est ≥ 3.11.
"""

from __future__ import annotations

import argparse
import base64
import csv
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent
OUTIL = BIN / "tracabilite_jira.py"
TASKS = BIN / "tasks.py"
JETON = "jeton-de-banc-0001"
EMAIL = "pilote@example.invalid"
PROJET = "BANC"
PROXYS = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module  # une dataclass relit son module dans sys.modules à l'exécution
    spec.loader.exec_module(module)
    return module


tj = _charger("tracabilite_jira_banc", OUTIL)
sgf = _charger("skills_github_fallback_banc", BIN / "skills_github_fallback.py")


# --------------------------------------------------------------------------- bouchon HTTP
class Bouchon:
    """Un faux Jira : `jira` (recherche par label, création), `401` (renvoie l'en-tête reçu), `302` (vers `cible`)."""

    def __init__(self, mode: str = "jira", cible: str = "") -> None:
        self.mode, self.cible = mode, cible
        self.requetes: list[tuple[str, str, dict, bytes]] = []
        self.cles: dict[str, str] = {}
        bouchon = self

        class Gestion(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002 — silence
                pass

            def _repondre(self, code: int, donnees: dict, entetes: dict | None = None) -> None:
                corps = json.dumps(donnees).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                for k, v in (entetes or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(corps)

            def _traiter(self, methode: str) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(n) if n else b""
                bouchon.requetes.append((methode, self.path, dict(self.headers), corps))
                if bouchon.mode == "401":
                    recu = self.headers.get("Authorization", "")
                    decode = base64.b64decode(recu.split(" ", 1)[-1]).decode("utf-8", "replace")
                    self._repondre(401, {"errorMessages": [f"recu {recu}", f"decode {decode}"]})
                elif bouchon.mode == "302":
                    self._repondre(302, {}, {"Location": bouchon.cible + self.path})
                elif methode == "GET" and self.path.startswith("/rest/api/3/search/jql?"):
                    jql = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)["jql"][0]
                    label = re.search(r'labels = "([^"]+)"', jql).group(1)
                    issues = [{"key": bouchon.cles[label]}] if label in bouchon.cles else []
                    self._repondre(200, {"issues": issues, "isLast": True})
                elif methode == "POST" and self.path == "/rest/api/3/issue":
                    champs = json.loads(corps.decode("utf-8"))["fields"]
                    cle = f"{PROJET}-{len(bouchon.cles) + 1}"
                    bouchon.cles[champs["labels"][0]] = cle
                    self._repondre(201, {"id": "1", "key": cle})
                else:
                    self._repondre(404, {"errorMessages": ["inconnu"]})

            def do_GET(self) -> None:  # noqa: N802
                self._traiter("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._traiter("POST")

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        self.url = f"http://127.0.0.1:{self.serveur.server_address[1]}"
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        self.fil.start()

    def posts(self) -> int:
        return sum(1 for r in self.requetes if r[0] == "POST")

    def arreter(self) -> None:
        self.serveur.shutdown()
        self.serveur.server_close()


# --------------------------------------------------------------------------- board et environnement jetables
class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.root, cls.home, cls.cwd = base / "racine", base / "home", base / "cwd"
        cls.etat, cls.events = base / "etat", base / "events"
        for d in (cls.root, cls.home, cls.cwd, cls.etat, cls.events):
            d.mkdir()
        cls.env = cls.env_propre()
        cls._tasks("epic-new", "E-01", "Epopee de banc")
        cls.tache_a = cls._nouvelle('Titre, avec "guillemets"', "--chantier", "ch-a", "--epic", "E-01")
        cls.tache_b = cls._nouvelle("Seconde tache", "--chantier", "ch-b")
        git = ["git", "-C", str(cls.root), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
               "-c", "user.name=banc", "-c", "user.email=banc@example.invalid", "-c", "commit.gpgsign=false"]
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "chore: board de banc"]):
            subprocess.run(git + argv, check=True, capture_output=True, text=True, timeout=60, env=cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def env_propre(cls, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items()
               if k not in sgf.AGENT_CALLER_MARKERS and k.lower() not in PROXYS and k != "JIRA_API_TOKEN"}
        env.update(HOME=str(cls.home), CADRE_STATE_DIR=str(cls.etat), AGENTS_EVENTS_DIR=str(cls.events),
                   NO_PROXY="127.0.0.1,localhost", PYTHONDONTWRITEBYTECODE="1")
        env.update(extra)
        return env

    @classmethod
    def _tasks(cls, *argv: str) -> str:
        r = subprocess.run([sys.executable, str(TASKS), "--root", str(cls.root), *argv], capture_output=True,
                           text=True, timeout=60, env=cls.env, check=True)
        return r.stdout + r.stderr

    @classmethod
    def _nouvelle(cls, titre: str, *argv: str) -> str:
        return re.search(r"(T-[0-9A-Z]+) → pending", cls._tasks("new", titre, *argv)).group(1)

    def lancer(self, *argv: str, env: dict | None = None, python: str = sys.executable):
        return subprocess.run([python, str(OUTIL), "--root", str(self.root), *argv], capture_output=True,
                              text=True, timeout=60, env=self.env if env is None else env, cwd=str(self.cwd),
                              stdin=subprocess.DEVNULL)

    def envoi(self, url: str, *argv: str, env: dict | None = None):
        return self.lancer("--envoyer", "--task", self.tache_a, "--url", url, "--projet", PROJET,
                           "--email", EMAIL, *argv, env=self.env_propre(JIRA_API_TOKEN=JETON) if env is None else env)

    def bouchon(self, *a: str) -> Bouchon:
        b = Bouchon(*a)
        self.addCleanup(b.arreter)
        return b


class TestTracabiliteJira(_Base):
    def test_tache_importee_exclue_avant_limite(self):
        taches = [{"id": self.tache_a, "task": "importée", "jira_key": "BANC-1"},
                  {"id": self.tache_b, "task": "locale"}]
        args = argparse.Namespace(tout=True, task=[], epic=None, chantier=None, etat=None, limite=1)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            retenues = tj.selectionner(taches, args)
        self.assertEqual([t["id"] for t in retenues], [self.tache_b])
        self.assertIn("1 tâche(s) importée(s) exclue(s)", err.getvalue())
        self.assertNotIn("limite 1", err.getvalue())

    def test_J1_un_jeton_en_argument_est_refuse_sans_echo(self):
        for argv in (["--token", JETON], [f"--token={JETON}"], ["--jeton", JETON], [f"--jeton={JETON}"],
                     [f"--tokn={JETON}"], ["--tout", "--TOKEN", JETON]):
            with self.subTest(argv=argv[-1][:8]):
                r = self.lancer(*argv)
                self.assertEqual(r.returncode, 2)
                self.assertNotIn(JETON, r.stdout + r.stderr)
                self.assertIn("jamais en argument", r.stderr.lower())

    def test_J1b_une_erreur_d_usage_ne_fait_jamais_echo_d_argv(self):
        for argv in (["--tout", f"--inconnu={JETON}"], ["--tout", "--limite", JETON], ["--tout", JETON]):
            with self.subTest(n=len(argv)):
                r = self.lancer(*argv)
                self.assertEqual(r.returncode, 2)
                self.assertNotIn(JETON, r.stdout + r.stderr)
                self.assertIn("non réimprimé", r.stderr)

    def test_J2_un_401_qui_renvoie_l_en_tete_ne_fait_fuir_ni_jeton_ni_base64(self):
        b = self.bouchon("401")
        r = self.envoi(b.url)
        b64 = base64.b64encode(f"{EMAIL}:{JETON}".encode()).decode()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("échec 401", r.stdout)
        self.assertEqual(b.requetes[0][2].get("Authorization"), f"Basic {b64}")  # le jeton est bien parti
        for flux in (r.stdout, r.stderr):
            for secret in (JETON, b64, base64.b64encode(JETON.encode()).decode()):
                self.assertNotIn(secret, flux)

    def test_J3_idempotence_par_label_un_seul_post(self):
        b = self.bouchon()
        r1, r2 = self.envoi(b.url), self.envoi(b.url)
        self.assertEqual((r1.returncode, r2.returncode), (0, 0), r1.stderr + r2.stderr)
        self.assertIn(f"jira: {self.tache_a} → {PROJET}-1 (créée)", r1.stdout)
        self.assertIn(f"jira: {self.tache_a} → {PROJET}-1 (déjà là)", r2.stdout)
        self.assertEqual(b.posts(), 1)

    def test_J3b_detail_serveur_et_id_hors_forme_filtres_avant_impression_et_jql(self):
        corps = json.dumps({"errorMessages": ["x\x1b[31my\x9bz"]}).encode("utf-8")
        self.assertEqual(tj.detail_erreur(corps, []), "x?[31my?z")
        mauvais = 'T-001" OR project != "X\x1b[2J'
        args = tj._parseur().parse_args(["--tout", "--envoyer", "--url", "http://127.0.0.1:9", "--projet", PROJET,
                                         "--email", EMAIL])
        appels: list[str] = []

        def faux_appel(methode, url, auth, local, corps=None):  # noqa: ANN001
            appels.append(urllib.parse.unquote_plus(url))
            return 200, json.dumps({"issues": [{"key": "BANC-\x1b9"}]}).encode("utf-8")

        sortie = io.StringIO()
        with mock.patch.dict(os.environ, {"JIRA_API_TOKEN": JETON}), \
                mock.patch.object(tj, "agent_appelant", return_value=""), \
                mock.patch.object(tj, "appel", side_effect=faux_appel), mock.patch("sys.stdout", sortie):
            rc = tj.envoyer([{"id": mauvais, "task": "x"}, {"id": self.tache_a, "task": "y"}], args)
        self.assertEqual(rc, 1)
        self.assertEqual(len(appels), 1, appels)
        self.assertIn(f'labels = "{self.tache_a}"', appels[0])
        self.assertIn('jira: T-001" OR project != "X?[2J → sauté (id hors forme', sortie.getvalue())
        self.assertIn(f"jira: {self.tache_a} → BANC-?9 (déjà là)", sortie.getvalue())
        self.assertNotRegex(sortie.getvalue(), r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

    def test_J4_http_hors_boucle_locale_refuse_avant_tout_appel(self):
        for url in ("http://jira.example.invalid", "http://localhost.example.invalid",
                    "http://127.0.0.1.example.invalid"):
            with self.subTest(url=url):
                rc, ouvrir, saisie = self._en_processus("--envoyer", "--task", self.tache_a, "--url", url,
                                                        "--projet", PROJET, "--email", EMAIL)
                self.assertEqual(rc, 2)
                ouvrir.assert_not_called()
                saisie.assert_not_called()
        for url in ("http://127.0.0.1:9", "http://localhost:9", "https://site.example.invalid"):
            self.assertTrue(tj.base_url(url)[0].startswith(url.split(":")[0]))  # contrôle : admis

    def test_J5_une_redirection_n_est_jamais_suivie(self):
        seconde = self.bouchon()
        premiere = self.bouchon("302", seconde.url)
        r = self.envoi(premiere.url)
        self.assertEqual(r.returncode, 1)
        self.assertIn("échec 302", r.stdout)
        self.assertEqual(len(premiere.requetes), 1)
        self.assertEqual(seconde.requetes, [])

    def test_J6_envoyer_refuse_sous_marqueur_d_agent(self):
        self.assertEqual(tj.AGENT_CALLER_MARKERS, sgf.AGENT_CALLER_MARKERS)
        b = self.bouchon()
        for marqueur in sgf.AGENT_CALLER_MARKERS:
            with self.subTest(marqueur=marqueur):
                r = self.envoi(b.url, env=self.env_propre(JIRA_API_TOKEN=JETON, **{marqueur: "1"}))
                self.assertEqual(r.returncode, 2)
                self.assertIn("contexte d'agent", r.stderr)
        self.assertEqual(b.requetes, [])
        apercu = self.lancer("--tout", env=self.env_propre(CLAUDECODE="1"))
        self.assertEqual(apercu.returncode, 0, apercu.stderr)

    def test_J6b_les_deux_lecteurs_lisent_les_marqueurs_copilot(self):
        """Copilot CLI pose COPILOT_AGENT_SESSION_ID et COPILOT_CLI dans le shell de l'agent (mesuré,
        1.0.96) : `agent_appelant` et `_agent_caller` lisent CHACUN des deux, seul. Mutant : un marqueur
        retiré des deux tuples => rouge ici (retiré d'un seul : J6 rouge, égalité)."""
        for marqueur in ("COPILOT_AGENT_SESSION_ID", "COPILOT_CLI"):
            with self.subTest(marqueur=marqueur):
                env = {marqueur: "1"}
                self.assertEqual(tj.agent_appelant(env), marqueur)
                self.assertEqual(sgf._agent_caller(env), marqueur)
                vide = {marqueur: "  "}
                self.assertEqual(tj.agent_appelant(vide), "")
                self.assertEqual(sgf._agent_caller(vide), "")

    def test_J7_description_adf_version_1(self):
        r = self.lancer("--task", self.tache_a)
        self.assertEqual(r.returncode, 0, r.stderr)
        desc = json.loads(r.stdout)[0]["fields"]["description"]
        self.assertIsInstance(desc, dict)
        self.assertEqual((desc["type"], desc["version"]), ("doc", 1))
        self.assertTrue(desc["content"] and all(p["type"] == "paragraph" for p in desc["content"]))
        self.assertIn(self.tache_a, json.dumps(desc))

    def test_J8_le_defaut_est_l_apercu_sans_reseau_ni_saisie(self):
        rc, ouvrir, saisie = self._en_processus("--tout", jeton=False)
        self.assertEqual(rc, 0)
        ouvrir.assert_not_called()
        saisie.assert_not_called()

    def test_J9_csv_relu_a_l_identique_un_label_par_colonne(self):
        taches = [{"id": "T-00000001", "task": 'Titre, avec "guillemets"\net saut', "state": "pending",
                   "epic": "E-01", "chantier": "ch", "depends_on": ["T-00000002"]},
                  {"id": "T-00000002", "task": "Simple", "state": "done"}]
        chemin = Path(self._tmp.name) / "export.csv"
        with open(chemin, "w", newline="", encoding="utf-8") as flux:
            tj.ecrire_csv(taches, "Task", flux)
        with open(chemin, newline="", encoding="utf-8") as flux:
            lignes = list(csv.reader(flux))
        self.assertEqual(lignes[0], ["Summary", "Issue Type", "Description", "Labels", "Labels"])
        self.assertEqual(lignes[1], ['[T-00000001] Titre, avec "guillemets" et saut', "Task",
                                     "\n".join(tj.lignes_description(taches[0])), "T-00000001", "E-01"])
        self.assertIn('Titre : Titre, avec "guillemets"\net saut', lignes[1][2])
        self.assertEqual(lignes[2][3:], ["T-00000002", ""])
        r = self.lancer("--tout", "--csv", "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(l[3] for l in list(csv.reader(io.StringIO(r.stdout)))[1:]),
                         sorted([self.tache_a, self.tache_b]))

    def test_J10_rien_d_ecrit_apres_un_envoi(self):
        avant = {d: sorted(os.listdir(d)) for d in (self.etat, self.events)}
        b = self.bouchon()
        r = self.envoi(b.url)
        self.assertEqual(r.returncode, 0, r.stderr)
        statut = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain", "--ignored",
                                 "--untracked-files=all"], capture_output=True, text=True, timeout=60, check=True)
        self.assertEqual(statut.stdout, "")
        self.assertEqual((os.listdir(self.home), os.listdir(self.cwd)), ([], []))
        self.assertEqual({d: sorted(os.listdir(d)) for d in (self.etat, self.events)}, avant)
        for motif in (JETON, b.url, PROJET):
            g = subprocess.run(["git", "-C", str(self.root), "grep", "-l", "-F", "-e", motif],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(g.returncode, 1, f"{motif!r} écrit dans {g.stdout}")

    def test_J11_interpreteur_anterieur_a_3_11_sans_traceback(self):
        ancien = "/usr/bin/python3"
        if not Path(ancien).exists():
            self.skipTest(f"{ancien} absent : J11 non joué")
        v = subprocess.run([ancien, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
                           capture_output=True, text=True, timeout=60)
        if v.stdout.strip() != "True":
            self.skipTest(f"{ancien} n'est pas antérieur à 3.11 : J11 non joué")
        for argv in (["--help"], ["--tout"]):
            with self.subTest(argv=argv):
                r = self.lancer(*argv, python=ancien)
                self.assertNotIn("Traceback", r.stderr)
                self.assertTrue(r.returncode == 0 or (r.returncode == 1 and "board illisible" in r.stderr),
                                (r.returncode, r.stderr[-300:]))

    def test_board_illisible_dit_sans_traceback(self):
        casse = Path(self._tmp.name) / "casse"
        (casse / ".agents" / "state" / "board").mkdir(parents=True, exist_ok=True)
        (casse / ".agents" / "state" / "board" / "TASKS.json").write_text("{pas du json", encoding="utf-8")
        r = subprocess.run([sys.executable, str(OUTIL), "--root", str(casse), "--tout"], capture_output=True,
                           text=True, timeout=60, env=self.env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 1)
        self.assertIn("board illisible (Python", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # ------------------------------------------------------------------- en processus
    def _en_processus(self, *argv: str, jeton: bool = True):
        env = self.env_propre(**({"JIRA_API_TOKEN": JETON} if jeton else {}))
        piege = AssertionError("appel interdit")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(tj, "_ouvrir", side_effect=piege) as ouvrir, \
                mock.patch("getpass.getpass", side_effect=piege) as saisie, \
                mock.patch("builtins.input", side_effect=piege), \
                mock.patch("sys.stdin", io.StringIO("")), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            rc = tj.main(["--root", str(self.root), *argv])
        return rc, ouvrir, saisie


if __name__ == "__main__":
    unittest.main()
