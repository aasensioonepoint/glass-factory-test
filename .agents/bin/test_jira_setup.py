#!/usr/bin/env python3
"""Banc de `jira_setup.py` et de la jambe « board : local ou Jira » de `setup_projet.py`
(T-01M5FQ7F3TDYQAMKQQ8Q30DDSG, annexe W1-W12, réserves C15 et C16 de critic-3).

AUCUN banc ne touche le vrai trousseau ni le vrai presse-papiers : HOME isolé, `_lancer` (le
seul site subprocess de jira_setup) simulé EN PROCESSUS, et W9 (pty) tue l'enfant après
l'invite « site », avant tout appel à security ou pbpaste. Le faux Jira écoute 127.0.0.1.

Mutants et le témoin qui les rougit : contrôle d'agent retiré -> W1 ; argv non filtré -> W2 ;
saisie conditionnée à --changer-jeton -> W3b ; présence sondée avant les invites -> ordre (C13) ;
borne e-mail ou jeton retirée -> W5b ; `finally` de l'env retiré -> W6b ; 0600 perdu -> W7 ;
GET /mypermissions retiré -> W4 ; défaut Jira -> W10 ; `capture=True` sur la jambe -> W9 ;
`or ""` retiré de `_executer` -> W12 (C15) ; `_verifier` à rc 0 forcé ou statut perdu -> W4b, W3c ;
garde d'agent de la jambe retirée -> W10b ; rc de security ignoré ou sortie non caviardée -> W3d ;
`kill` au lieu de `killpg` sur le groupe -> W9 (C16).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN))
import jira_setup  # noqa: E402
import tracabilite_jira  # noqa: E402

JETON = "AbCdEf0123456789_tok=+/.-" * 2
EMAIL = "pilote@example.com"
SITE = "https://exemple.atlassian.net"
_PURGE = (*tracabilite_jira.AGENT_CALLER_MARKERS, "JIRA_API_TOKEN", "CADRE_JIRA_SITE",
          "CADRE_JIRA_EMAIL")


def _setup_projet():
    spec = importlib.util.spec_from_file_location("_banc_jira_setup_projet", BIN / "setup_projet.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Tty(io.StringIO):
    def __init__(self, texte: str = "", tty: bool = True) -> None:
        super().__init__(texte)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _Isole(unittest.TestCase):
    """HOME jetable, marqueurs d'agent et variables Jira retirés, macOS simulé."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="banc-jira-setup-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {k: v for k, v in os.environ.items() if k not in _PURGE}
        env["HOME"] = str(self.tmp)
        pile = contextlib.ExitStack()
        self.addCleanup(pile.close)
        pile.enter_context(mock.patch.dict(os.environ, env, clear=True))
        pile.enter_context(mock.patch.object(sys, "platform", "darwin"))
        self.pile = pile
        self.evenements: list[tuple] = []
        self.present_rc = 44
        self.presse = JETON

    def _faux_lancer(self, argv, entree=None):
        self.evenements.append(("lancer", tuple(argv), entree))
        if argv[:2] == [jira_setup.SECURITY, "find-generic-password"]:
            return subprocess.CompletedProcess(argv, self.present_rc, "", "")
        if argv == [jira_setup.SECURITY, "-i"]:
            self.present_rc = 0
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv == [jira_setup.PBPASTE]:
            return subprocess.CompletedProcess(argv, 0, self.presse, "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def _configurer(self, reponses, *, tty=True, changer=False, verif=(0, 200)):
        reponses = list(reponses)
        verifs = list(verif) if isinstance(verif, list) else [verif]

        def faux_input(invite=""):
            self.evenements.append(("input", invite))
            if not reponses:
                raise EOFError
            return reponses.pop(0)

        def faux_getpass(invite=""):
            self.evenements.append(("getpass", invite))
            if not reponses:
                raise EOFError
            return reponses.pop(0)

        def faux_verifier():
            self.evenements.append(("verifier",))
            return verifs.pop(0) if len(verifs) > 1 else verifs[0]

        flux = io.StringIO()
        # verif=None : le VRAI `_verifier` joue (contre le faux Jira posé par l'appelant).
        simule = (contextlib.nullcontext() if verif is None else
                  mock.patch.object(jira_setup, "_verifier", faux_verifier))
        with mock.patch.object(jira_setup, "_lancer", self._faux_lancer), \
                mock.patch("builtins.input", faux_input), \
                mock.patch.object(jira_setup.getpass, "getpass", faux_getpass), simule, \
                mock.patch.object(sys, "stdin", _Tty("", tty)), contextlib.redirect_stdout(flux):
            rc = jira_setup.configurer(changer)
        return rc, flux.getvalue()

    def _lances(self, *argv):
        return [e for e in self.evenements if e[0] == "lancer" and e[1][:len(argv)] == argv]

    def _config(self):
        return jira_setup._chemin_config()


class ConfigurerTests(_Isole):
    def test_W1_refus_sous_agent_hook_host_seul(self):
        os.environ["AGENTS_HOOK_HOST"] = "codex"
        rc, out = self._configurer([SITE, "PROJ", EMAIL])
        self.assertEqual(rc, 2, out)
        self.assertIn(jira_setup.COMMANDE, out)
        self.assertEqual(self.evenements, [], "rien demandé, rien lancé sous agent")
        self.assertFalse(self._config().exists())

    def test_W2_argv_qui_annonce_un_jeton(self):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(jira_setup, "_lancer", self._faux_lancer), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = jira_setup.main(["configurer", "--token=SECRET-ZZ"])
        self.assertEqual(rc, 2)
        self.assertNotIn("SECRET-ZZ", err.getvalue() + out.getvalue())
        self.assertEqual(self.evenements, [])

    def test_W8_stdin_non_terminal(self):
        rc, out = self._configurer([SITE, "PROJ", EMAIL], tty=False)
        self.assertEqual((rc, jira_setup.COMMANDE in out, self.evenements), (2, True, []), out)

    def test_ordre_invites_avant_trousseau(self):
        """C13 : le premier appel externe vient APRÈS les trois invites."""
        rc, out = self._configurer([SITE, "proj", EMAIL, ""])
        self.assertEqual(rc, 0, out)
        sortes = [e[0] for e in self.evenements]
        self.assertEqual(sortes[:3], ["input"] * 3, sortes)
        self.assertIn("site", self.evenements[0][1])
        self.assertGreater(sortes.index("lancer"), 2)
        # L'attente du jeton copié passe par getpass : un jeton collé là n'est jamais affiché.
        self.assertIn(("getpass", "Jeton copié ? Appuyez sur Entrée : "), self.evenements)
        self.assertFalse(any(e[0] == "input" and "Jeton" in e[1] for e in self.evenements))

    def test_W3_jeton_present_aucune_saisie(self):
        self.present_rc = 0
        rc, out = self._configurer([SITE, "PROJ", EMAIL])
        self.assertEqual(rc, 0, out)
        self.assertEqual((self._lances(jira_setup.PBPASTE), self._lances(jira_setup.SECURITY, "-i")),
                         ([], []))
        self.assertEqual([e for e in self.evenements if e[0] == "verifier"], [("verifier",)])

    def test_W3_jeton_present_401_puis_remplacement(self):
        self.present_rc = 0
        rc, out = self._configurer([SITE, "PROJ", EMAIL, "o", ""], verif=[(1, 401), (0, 200)])
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self._lances(jira_setup.SECURITY, "-i")), 1)

    def test_W3b_jeton_absent_saisie_directe(self):
        self.present_rc = 44
        rc, out = self._configurer([SITE, "PROJ", EMAIL, ""])
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self._lances(jira_setup.PBPASTE)), 1)
        ecrits = self._lances(jira_setup.SECURITY, "-i")
        self.assertEqual(len(ecrits), 1)
        self.assertEqual(ecrits[0][1], (jira_setup.SECURITY, "-i"))
        self.assertEqual(ecrits[0][2], f"add-generic-password -U -s cadre-jira -a {EMAIL} -w {JETON}\n")
        self.assertFalse(any(JETON in a for e in self.evenements if e[0] == "lancer" for a in e[1]),
                         "jeton dans un argv")
        self.assertNotIn(JETON, out)
        self.assertEqual(self._lances(jira_setup.PBCOPY)[-1][2], "", "presse-papiers non vidé")

    def test_W3b_changer_jeton_present(self):
        self.present_rc = 0
        rc, out = self._configurer([SITE, "PROJ", EMAIL, ""], changer=True)
        self.assertEqual((rc, len(self._lances(jira_setup.SECURITY, "-i"))), (0, 1), out)

    def test_W5b_bornes_avant_tout_appel(self):
        rc, out = self._configurer([SITE, "PROJ", "a" * 243 + "@example.com"])  # 255 car.
        self.assertEqual((rc, self.evenements[3:]), (2, []), out)
        self.assertFalse(self._config().exists())
        self.evenements.clear()
        self.presse = "A" * 1025
        rc, out = self._configurer([SITE, "PROJ", EMAIL, ""])
        self.assertEqual((rc, self._lances(jira_setup.SECURITY, "-i")), (1, []), out)
        self.assertEqual(len(self._lances(jira_setup.PBCOPY)), 1, "presse-papiers vidé au refus")
        self.presse = "A" * 1024
        self.evenements.clear()
        rc, out = self._configurer([SITE, "PROJ", EMAIL, ""])
        self.assertEqual((rc, len(self._lances(jira_setup.SECURITY, "-i"))), (0, 1), out)

    def test_W6b_env_restaure_et_source_du_jeton(self):
        avant = dict(os.environ)
        with self.assertRaises(jira_setup.Refus):
            jira_setup.valider("https://exemple.example.org", "PROJ", EMAIL)
        self.assertEqual(dict(os.environ), avant, "env de validation non restauré (échec)")
        self.assertEqual(jira_setup.valider("exemple.atlassian.net", "PROJ", EMAIL)[0], SITE)
        self.assertEqual(dict(os.environ), avant, "env de validation non restauré (succès)")
        jira_setup._ecrire_config({"site": SITE, "email": EMAIL, "project": "PROJ"})
        os.environ["JIRA_API_TOKEN"] = "x" * 20
        flux = io.StringIO()
        with mock.patch.object(jira_setup, "_lancer", self._faux_lancer), contextlib.redirect_stdout(flux):
            self.assertEqual(jira_setup.etat(), 0)
        self.assertIn("jeton : environnement", flux.getvalue())
        self.assertNotIn("x" * 20, flux.getvalue())
        self.assertEqual(self.evenements, [], "etat ne consulte jamais le trousseau")

    def test_W7_jira_json_0600_trois_cles(self):
        rc, out = self._configurer([SITE, "proj", EMAIL, ""])
        self.assertEqual(rc, 0, out)
        chemin = self._config()
        self.assertEqual(stat.S_IMODE(chemin.stat().st_mode), 0o600)
        self.assertEqual(json.loads(chemin.read_text(encoding="utf-8")),
                         {"site": SITE, "email": EMAIL, "project": "PROJ"})
        self.assertNotIn(JETON, chemin.read_text(encoding="utf-8"))
        self.assertEqual(sorted(p.name for p in chemin.parent.iterdir()), ["jira.json"])

    def test_W11_hors_macos(self):
        with mock.patch.object(sys, "platform", "linux"):
            rc, out = self._configurer([SITE, "PROJ", EMAIL])
        self.assertEqual((rc, self._lances()), (1, []), out)
        self.assertIn("JIRA_API_TOKEN", out)


class _FauxJira:
    """`statuts` : préfixe de chemin -> statuts successifs (le dernier se répète) ; `refuses` :
    droits rendus sans permission."""

    def __init__(self, statuts: dict[str, list[int]] | None = None, refuses: tuple = ()) -> None:
        self.appels: list[tuple[str, str]] = []
        self.statuts = statuts or {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 — silence
                pass

            def _repondre(self):
                owner.appels.append((self.command, self.path))
                corps = {"accountId": "a"}
                if self.path.startswith("/rest/api/3/mypermissions"):
                    corps = {"permissions": {d: {"havePermission": d not in refuses}
                                             for d in jira_setup.DROITS}}
                statut = 200
                for prefixe, suite in owner.statuts.items():
                    if self.path.startswith(prefixe):
                        statut = suite.pop(0) if len(suite) > 1 else suite[0]
                donnees = json.dumps(corps).encode("utf-8")
                self.send_response(statut)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(donnees)))
                self.end_headers()
                self.wfile.write(donnees)

            do_GET = do_PUT = do_POST = do_DELETE = _repondre

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.site = f"http://127.0.0.1:{self.server.server_address[1]}"


class VerifierTests(_Isole):
    def test_W4_trois_get_aucune_ecriture(self):
        faux = _FauxJira()
        self.addCleanup(faux.server.server_close)
        self.addCleanup(faux.server.shutdown)
        jira_setup._ecrire_config({"site": faux.site, "email": EMAIL, "project": "PROJ"})
        os.environ["JIRA_API_TOKEN"] = "jeton-de-banc-local"
        flux = io.StringIO()
        with contextlib.redirect_stdout(flux):
            rc = jira_setup.verifier()
        self.assertEqual(rc, 0, flux.getvalue())
        self.assertEqual([m for m, _ in faux.appels], ["GET"] * 3, faux.appels)
        self.assertTrue(faux.appels[2][1].startswith("/rest/api/3/mypermissions?projectKey=PROJ"))
        self.assertEqual(flux.getvalue().count("jira: droit "), len(jira_setup.DROITS))
        self.assertNotIn("jeton-de-banc-local", flux.getvalue())

    def _vrai_verifier(self, **faux_kw):
        faux = _FauxJira(**faux_kw)
        self.addCleanup(faux.server.server_close)
        self.addCleanup(faux.server.shutdown)
        jira_setup._ecrire_config({"site": faux.site, "email": EMAIL, "project": "PROJ"})
        os.environ["JIRA_API_TOKEN"] = "jeton-de-banc-local"
        flux = io.StringIO()
        with contextlib.redirect_stdout(flux):
            resultat = jira_setup._verifier()
        return resultat, flux.getvalue(), faux

    def test_W4b_vrai_verifier_rc_et_statut(self):
        """Constat 1 de l'exec-critic : le rc et le statut de /myself RENDUS par le vrai `_verifier`."""
        cas = (({"statuts": {"/rest/api/3/myself": [401]}}, (1, 401), 1),
               ({"statuts": {"/rest/api/3/myself": [403]}}, (1, 403), 1),
               ({"statuts": {"/rest/api/3/project/": [404]}}, (1, 200), 3),
               ({"refuses": ("ASSIGN_ISSUES",)}, (1, 200), 3),
               ({}, (0, 200), 3))
        for kw, attendu, get in cas:
            with self.subTest(cas=kw):
                resultat, out, faux = self._vrai_verifier(**kw)
                self.assertEqual(resultat, attendu, out)
                self.assertEqual([m for m, _ in faux.appels], ["GET"] * get, faux.appels)
        self.assertIn("droit ASSIGN_ISSUES : non", self._vrai_verifier(refuses=("ASSIGN_ISSUES",))[1])

    def test_W3c_configurer_401_puis_remplacement_vrai_verifier(self):
        """Jeton présent, /myself répond 401 puis 200 : l'invite [o/N] paraît, « o » joue la saisie
        (simulée) puis re-vérifie. Le site configuré pointe vers le faux Jira par `_jira_config`."""
        faux = _FauxJira(statuts={"/rest/api/3/myself": [401, 200]})
        self.addCleanup(faux.server.server_close)
        self.addCleanup(faux.server.shutdown)
        self.present_rc = 0
        # keychain=False : la validation (site Atlassian) ; sinon : la lecture du `_verifier`.
        with mock.patch.object(jira_setup.tasks, "_jira_config",
                               lambda keychain=True: (faux.site, True, "Basic eDp5") if keychain
                               else (SITE, False, "Basic eDp5")):
            rc, out = self._configurer([SITE, "PROJ", EMAIL, "o", ""], verif=None)
        self.assertEqual(rc, 0, out)
        invites = [e[1] for e in self.evenements if e[0] == "input"]
        self.assertTrue(any("[o/N]" in i and "401" in i for i in invites), invites)
        self.assertEqual(len(self._lances(jira_setup.SECURITY, "-i")), 1, "saisie de remplacement")
        self.assertEqual([p for _, p in faux.appels].count("/rest/api/3/myself"), 2, faux.appels)

    def _saisie_security(self, rc):
        def lancer(argv, entree=None):
            if argv == [jira_setup.SECURITY, "-i"]:
                self.evenements.append(("lancer", tuple(argv), entree))
                return subprocess.CompletedProcess(argv, rc, "", f"erreur {JETON}")
            return self._faux_lancer(argv, entree)
        self.present_rc = 0
        flux = io.StringIO()
        with mock.patch.object(jira_setup, "_lancer", lancer), \
                mock.patch.object(jira_setup.getpass, "getpass", lambda *_: ""), \
                contextlib.redirect_stdout(flux):
            ok = jira_setup._saisir_jeton(EMAIL)
        self.assertNotIn(JETON, flux.getvalue(), "sortie de security non caviardée")
        return ok, flux.getvalue()

    def test_W3d_security_i_rc_decide_et_stderr_dit(self):
        """rc ≠ 0 (mesuré sur un échec interne) => échec ; rc 0 + stderr (non mesuré) => dit, pas un échec."""
        ok, sortie = self._saisie_security(1)
        self.assertFalse(ok)
        self.assertIn("écriture au trousseau échouée (rc 1)", sortie)
        ok, sortie = self._saisie_security(0)
        self.assertTrue(ok)
        self.assertIn("security a écrit un message malgré le succès", sortie)

    def test_W4_aucun_transport_dans_le_source(self):
        source = (BIN / "jira_setup.py").read_text(encoding="utf-8")
        for interdit in ("appel(", "urllib", "http.client", "import tasks_jira"):
            self.assertFalse(interdit in source, f"{interdit!r} dans jira_setup.py")

    def test_marqueurs_agent_egaux(self):
        self.assertEqual(_setup_projet()._MARQUEURS_AGENT, tracabilite_jira.AGENT_CALLER_MARKERS)


class JambeSetupTests(_Isole):
    def _jambe(self, stdin, *, dry=False):
        sp = _setup_projet()
        rapport, flux, appels = sp.Rapport(dry), io.StringIO(), []
        with mock.patch.object(sp, "_script", lambda *a, **k: appels.append((a, k)) or sp.Sortie(0, "", "")), \
                mock.patch.object(sys, "stdin", stdin), contextlib.redirect_stdout(flux):
            sp._board_local_ou_jira(self.tmp, rapport)
        return flux.getvalue(), appels, rapport

    def test_W10_defaut_local(self):
        for reponse in ("\n", "x\n", "l\n", ""):
            with self.subTest(reponse=reponse):
                out, appels, _ = self._jambe(_Tty(reponse))
                self.assertEqual(appels, [], out)
                self.assertIn("board : local ou Jira : sans objet — local (défaut)", out)
        out, appels, _ = self._jambe(_Tty("J\n"))
        self.assertEqual(appels, [((self.tmp, "jira_setup.py", "configurer"),
                                   {"stdin": None, "capture": False})], out)
        for stdin, dry in ((_Tty("j\n"), True), (_Tty("j\n", tty=False), False)):
            out, appels, _ = self._jambe(stdin, dry=dry)
            self.assertEqual((appels, "[L/j]" in out, "à créer" in out), ([], False, False), out)

    def test_W10b_jambe_sous_agent_ne_lance_rien(self):
        """Constat 2 : sous un marqueur d'agent, au terminal, « j » ne lance PAS configurer."""
        for marqueur in tracabilite_jira.AGENT_CALLER_MARKERS:
            with self.subTest(marqueur=marqueur), mock.patch.dict(os.environ, {marqueur: "1"}):
                out, appels, rapport = self._jambe(_Tty("j\n"))
                self.assertEqual((appels, "[L/j]" in out), ([], False), out)
                self.assertIn("board : local ou Jira : sans objet", out)
                self.assertIn("jira_setup.py configurer, au terminal du pilote", out)

    def test_W12_executer_sans_capture_rend_des_str(self):
        """C15 : l'aide elle-même, puisque la jambe ne lit que rc."""
        sp = _setup_projet()
        sortie = sp._executer([sys.executable, "-c", "import sys; sys.exit(2)"], self.tmp, capture=False)
        self.assertEqual((type(sortie.stdout), type(sortie.stderr)), (str, str))
        self.assertEqual(sortie.raison(), "rc 2")

    def test_W12_configurer_rc2_degrade_jambes_suivantes(self):
        sp = _setup_projet()
        (self.tmp / ".agents" / "bin").mkdir(parents=True)
        (self.tmp / ".agents" / "bin" / "jira_setup.py").write_text("import sys\nsys.exit(2)\n",
                                                                    encoding="utf-8")
        vues: list[str] = []
        suivantes = ("_index", "_lire_ancienne", "_specs", "_dire_ancienne", "_graphe", "_hooks_git",
                     "_bilan", "_sondes", "_commit")
        flux = io.StringIO()
        with contextlib.ExitStack() as pile:
            pile.enter_context(mock.patch.object(sp, "_racine", lambda _r: self.tmp))
            pile.enter_context(mock.patch.object(sp, "_suivis", lambda _r: set()))
            pile.enter_context(mock.patch.object(sp, "_charger", lambda _r: None))
            pile.enter_context(mock.patch.object(sp, "_identite_et_board", lambda *a: True))
            pile.enter_context(mock.patch.object(sp, "_stores", lambda *a: None))
            for nom in suivantes:
                pile.enter_context(mock.patch.object(sp, nom, lambda *a, _n=nom: vues.append(_n)))
            pile.enter_context(mock.patch.object(sys, "stdin", _Tty("j\n")))
            pile.enter_context(contextlib.redirect_stdout(flux))
            rc = sp.main(["--root", str(self.tmp)])
        self.assertIn("board : local ou Jira : dégradé — jira_setup.py configurer rc=2", flux.getvalue())
        self.assertEqual(vues, list(suivantes))
        self.assertEqual(rc, 0, "jambe non créatrice : jamais le code de sortie")


_ENFANT = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import setup_projet
setup_projet._board_local_ou_jira(Path(sys.argv[2]), setup_projet.Rapport(False))
"""


@unittest.skipIf(os.name != "posix", "SAUT ANNONCÉ — pty POSIX requis pour W9")
class InviteSousPtyTests(_Isole):
    def test_W9_invite_site_visible_puis_groupe_tue(self):
        """C1 + C16 : l'invite « site » du petit-enfant se lit au maître ; l'enfant, chef de sa
        session, est tué par killpg AVANT toute réponse ; aucun petit-enfant ne survit."""
        import pty  # noqa: PLC0415
        racine = self.tmp / "r"
        (racine / ".agents").mkdir(parents=True)
        (racine / ".agents" / "bin").symlink_to(BIN, target_is_directory=True)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("PYTHONPATH", None)
        maitre, esclave = pty.openpty()
        p = subprocess.Popen([sys.executable, "-c", _ENFANT, str(BIN), str(racine)], env=env,
                             cwd=str(racine), stdin=esclave, stdout=esclave, stderr=esclave,
                             close_fds=True, start_new_session=True)
        os.close(esclave)
        sortie, repondu, fin = b"", False, time.monotonic() + 30
        try:
            while b"site Jira Cloud" not in sortie and time.monotonic() < fin:
                if not repondu and b"[L/j]" in sortie:
                    os.write(maitre, b"j\n")
                    repondu = True
                if not select.select([maitre], [], [], 1)[0]:
                    continue
                try:
                    bloc = os.read(maitre, 4096)
                except OSError:
                    break
                if not bloc:
                    break
                sortie += bloc
            # Petits-enfants relevés AVANT le kill ; jugés morts AVANT la fermeture du maître
            # (fermé, il enverrait EOF/SIGHUP et le petit-enfant sortirait seul : témoin vide).
            petits = _membres_du_groupe(p.pid) - {p.pid}
            self.addCleanup(_tuer, petits)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, 9)
            p.wait(timeout=30)
            vivants, fin = set(petits), time.monotonic() + 5
            while vivants and time.monotonic() < fin:
                vivants = {pid for pid in vivants if _vivant(pid)}
                time.sleep(0.05)
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, 9)
            p.wait(timeout=30)
            os.close(maitre)
        self.assertIn(b"site Jira Cloud", sortie, sortie.decode("utf-8", "replace"))
        self.assertTrue(petits, "aucun petit-enfant relevé : le témoin de survie passerait à vide")
        self.assertEqual(vivants, set(), "un petit-enfant de jira_setup survit au kill de l'enfant")
        self.assertFalse(jira_setup._chemin_config().exists())


class AliasAnglais(unittest.TestCase):
    """Lot J de T-01M5QC86XN : nom anglais en tête, ancien nom français accepté, même effet.

    Mutants et le témoin qui les rougit : `set_defaults(verbe="etat")` retiré sur `status` -> le
    verbe aboutit dans `configurer` (test_jira_verbes) ; `dest` omis sur `--change-token` ->
    AttributeError sur `changer_jeton` ; alias `bilan`/`tache`/`pr-corps` ou `set_defaults` retiré
    -> mauvaise répartition (test_tracabilite_verbes) ; `--all` (ou tout autre nom de la liste
    fermée) retiré -> rc 2 (test_tracabilite_jira_drapeaux) ; `dest` omis -> attribut ancien absent ;
    `--scope` sans `dest=portee` -> portée perdue (test_retro_scope).
    """

    def test_jira_verbes(self):
        appels: list[tuple] = []
        with mock.patch.object(jira_setup, "etat", lambda: appels.append(("etat",)) or 0), \
                mock.patch.object(jira_setup, "verifier", lambda: appels.append(("verifier",)) or 0), \
                mock.patch.object(jira_setup, "configurer",
                                  lambda changer: appels.append(("configurer", changer)) or 0):
            for argv, attendu in ((["status"], ("etat",)), (["etat"], ("etat",)),
                                  (["verify"], ("verifier",)), (["verifier"], ("verifier",)),
                                  (["configure"], ("configurer", False)),
                                  (["configurer"], ("configurer", False)),
                                  (["configure", "--change-token"], ("configurer", True)),
                                  (["configurer", "--changer-jeton"], ("configurer", True))):
                with self.subTest(argv=argv):
                    appels.clear()
                    self.assertEqual(jira_setup.main(argv), 0)
                    self.assertEqual(appels, [attendu])
        aide = jira_setup._parseur().format_help()
        self.assertLess(aide.index("status"), aide.index("etat"), aide)

    def test_tracabilite_verbes(self):
        import tracabilite
        appels: list[tuple] = []
        with mock.patch.object(tracabilite, "cmd_bilan", lambda r, n, d: appels.append(("bilan", d)) or 0), \
                mock.patch.object(tracabilite, "cmd_tache", lambda r, t, pr: appels.append(("tache", t, pr)) or 0), \
                mock.patch.object(tracabilite, "cmd_pr_corps", lambda r, b: appels.append(("pr-corps", b)) or 0):
            for argv, attendu in ((["summary", "--since", "R"], ("bilan", "R")),
                                  (["bilan", "--depuis", "R"], ("bilan", "R")),
                                  (["task", "T-00000001", "--pr"], ("tache", "T-00000001", True)),
                                  (["tache", "T-00000001"], ("tache", "T-00000001", False)),
                                  (["pr-body", "--base", "B"], ("pr-corps", "B")),
                                  (["pr-corps", "--base", "B"], ("pr-corps", "B"))):
                with self.subTest(argv=argv):
                    appels.clear()
                    self.assertEqual(tracabilite.main(argv), 0)
                    self.assertEqual(appels, [attendu])

    def test_tracabilite_jira_drapeaux(self):
        attendu = {"chantier": "w", "etat": "done", "tout": True, "limite": 2, "envoyer": True, "projet": "P"}
        anglais = ["--workstream", "w", "--state", "done", "--all", "--limit", "2", "--send", "--project", "P"]
        ancien = ["--chantier", "w", "--etat", "done", "--tout", "--limite", "2", "--envoyer", "--projet", "P"]
        for argv in (anglais, ancien):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                ns = vars(tracabilite_jira._parseur().parse_args(argv))
                self.assertEqual({k: ns.get(k) for k in attendu}, attendu)

    def test_retro_scope(self):
        import retro
        for drapeau in ("--scope", "--portee"):
            with self.subTest(drapeau=drapeau):
                ns = retro.build_parser().parse_args(
                    ["add", "--cause", retro.CAUSES[0], "--text", "x", drapeau, "universelle"])
                self.assertEqual(ns.portee, "universelle")

    @staticmethod
    def _options(parseur, dest: str) -> list[str]:
        """`option_strings` de l'action `dest`, cherchée dans le parseur et ses sous-parseurs."""
        import argparse
        for action in parseur._actions:
            if action.dest == dest and action.option_strings:
                return action.option_strings
            if isinstance(action, argparse._SubParsersAction):
                for sous in action.choices.values():
                    trouve = AliasAnglais._options(sous, dest)
                    if trouve:
                        return trouve
        return []

    def test_l_anglais_vient_en_tete_de_chaque_paire(self):
        """Mutant « ancien nom en tête » (paire inversée) : l'effet reste le même, seul l'ordre rougit."""
        import retro
        import tracabilite
        for parseur, paires in (
                (tracabilite_jira._parseur(), (("chantier", "--workstream", "--chantier"),
                                               ("etat", "--state", "--etat"), ("tout", "--all", "--tout"),
                                               ("limite", "--limit", "--limite"), ("envoyer", "--send", "--envoyer"),
                                               ("projet", "--project", "--projet"))),
                (retro.build_parser(), (("portee", "--scope", "--portee"),)),
                (jira_setup._parseur(), (("changer_jeton", "--change-token", "--changer-jeton"),))):
            for dest, anglais, ancien in paires:
                with self.subTest(dest=dest):
                    self.assertEqual(self._options(parseur, dest), [anglais, ancien])
        self.assertTrue(retro.build_parser().format_help().isascii(), "aide de retro.py non ASCII")
        for aide, paires in ((jira_setup._parseur().format_help(),
                              (("status", "etat"), ("verify", "verifier"), ("configure", "configurer"))),
                             (tracabilite._parseur().format_help(),
                              (("summary", "bilan"), ("task", "tache"), ("pr-body", "pr-corps")))):
            # la liste `{…}` de l'usage, jamais la description (« Links task… » précède tout verbe)
            choix = aide[aide.index("{") + 1:aide.index("}")].split(",")
            for anglais, ancien in paires:
                with self.subTest(verbe=anglais):
                    self.assertLess(choix.index(anglais), choix.index(ancien), aide)


def _membres_du_groupe(pgid: int) -> set[int]:
    sortie = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True,
                            timeout=30, check=True).stdout
    return {int(pid) for pid, groupe in (ligne.split() for ligne in sortie.splitlines() if ligne.strip())
            if int(groupe) == pgid}


def _vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    etat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
                          timeout=30, check=False).stdout.strip()
    return bool(etat) and not etat.startswith("Z")


def _tuer(pids: set[int]) -> None:
    for pid in pids:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, 9)


if __name__ == "__main__":
    unittest.main()
