"""Arrêt vérifié du démon et relevé des démons du poste (T-00000613).

Deux défauts mesurés le 2026-10-02 sur un démon jetable : `--stop` sur un pid
qui survit à SIGTERM rendait `stopped`, rc 0, et RETIRAIT le verrou — le
suivant `acquire_lock` admettait alors un second démon, injoignable à tout
`--stop` ultérieur ; et `--status` ne voyait qu'UNE racine, alors que plusieurs
démons pouvaient vivre sur le poste, aucun au registre machine.

Fichier séparé de `test_dashboard_daemon.py` (898 lignes) : règle (relevée à 1600 par S-00004034) des 800
lignes par `.py` (S-00002684). Les faux démons sont des enfants de ce banc,
chacun dans sa propre session, récoltés par un fil dédié (un enfant mort non
récolté est un zombie que `kill(pid, 0)` voit vivant) et tués par SIGKILL de
leur GROUPE au tearDown (un enveloppeur emporte son enfant).

LA MORT SE JUGE PAR LE PID, JAMAIS PAR LE PING : un faux démon MUET (SIGTERM
ferme son serveur, le processus dort encore) sépare les deux sondes — sonder le
ping rendrait `stopped` sur un pid vivant, le défaut du ticket.

LE RELEVÉ EST PROUVÉ DEUX FOIS, jamais par `isinstance` : (1) sur un `ps`
SIMULÉ, où chaque grandeur et chaque forme est exacte et où rien ne dépend de
l'OS ni des autres démons du poste ; (2) sur un VRAI `ps` et de VRAIS processus
(POSIX), qui seul prouve l'unité réelle de `ps` et le format réel d'une ligne.
Il est couplé aux DEUX lanceurs RÉELS — `spawn_detached` et le `Popen` du hook
`.claude/hooks/session-start.sh` (Claude Code), qui ne passe pas par lui : une
dérive de l'un ou de l'autre rougit ici avant de rendre le relevé aveugle en
silence. Il compte un RUN du démon, jamais un enveloppeur ni un outil qui cite
la commande.

Les chemins simulés n'emploient que des comptes génériques (`/Users/me`) :
`test_template_hygiene` refuse tout autre compte dans un fichier qui voyage.
Sans `ps` (hôte POSIX minimal), les témoins à VRAI `ps` rougissent : refus
fermé, comme le témoin RSS voisin ; la porte `--linux` installe `procps`. Un
interpréteur dont le chemin porte une espace, ou qui ne s'appelle pas
`python*` (PyPy), rougit le témoin à vrai `ps` par construction : le relevé ne
le reconnaît pas (sous-comptage nommé dans `_demon_argv`). Les témoins couplés
aux lanceurs construisent leur ligne avec un interpréteur FIXE, pour ne pas en
dépendre.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


daemon = _load("_test_dashboard_daemon_arret", "dashboard_daemon.py")
# Les valeurs de PRODUCTION, lues avant que `_Base` ne les abaisse.
_ATTENTE_DE_PRODUCTION = getattr(daemon, "_STOP_WAIT_SECONDS", None)
_SONDAGE_DE_PRODUCTION = getattr(daemon, "_STOP_POLL_SECONDS", None)

# Faux démon : sert /api/ping (200 pour le bon jeton) et imprime son port.
# `ignore` : SIGTERM ignoré. `muet` : SIGTERM ferme le serveur, le processus VIT.
_FAUX_DEMON = (
    "import http.server,signal,sys,threading\n"
    "T=sys.argv[1]\n"
    "if sys.argv[2]=='ignore': signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "if sys.argv[2]=='muet': signal.signal(signal.SIGTERM, lambda *a: (s.shutdown(), s.server_close()))\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        ok=self.path=='/api/ping' and self.headers.get('Authorization')=='Bearer '+T\n"
    "        self.send_response(200 if ok else 401); self.end_headers()\n"
    "    def log_message(self,*a): pass\n"
    "s=http.server.HTTPServer(('127.0.0.1',0),H)\n"
    "print(s.server_address[1],flush=True)\n"
    "threading.Thread(target=s.serve_forever,args=(0.05,),daemon=True).start()\n"
    "threading.Event().wait()\n"
)
# Un dormeur dont l'interpréteur est CHARGÉ avant qu'on lise son RSS : sans cette
# barrière, `ps` lit l'instant de l'exec (32 768 octets mesurés) et la grandeur flotte.
_DORMEUR = "import sys,time; print(1, flush=True); time.sleep(60)\n"


def _main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = daemon.main(argv)
    return rc, (json.loads(out.getvalue()) if out.getvalue().strip() else None), err.getvalue()


def _ps(stdout=b"", returncode=0, raises=None, calls=None):
    """Un `subprocess.run` qui rend un `ps` SIMULÉ et note l'argv et les kwargs."""
    def run(argv, **kw):
        if calls is not None:
            calls.append((argv, kw))
        if raises is not None:
            raise raises
        return types.SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


def _ps_releve(stdout):
    """Le `ps -A` du relevé est SIMULÉ ; tout autre appel (le RSS du verrou) échoue."""
    def run(argv, **kw):
        if "-A" in argv:
            return types.SimpleNamespace(stdout=stdout, returncode=0)
        raise FileNotFoundError(argv[0])
    return run


def _ligne(pid, rss_kio, args):
    return f"{pid:>6} {rss_kio:>8} {args}\n".encode()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name) / "projet"
        self.root.mkdir()
        self._enfants = []
        if _ATTENTE_DE_PRODUCTION is not None:
            daemon._STOP_WAIT_SECONDS = 1.0

    def tearDown(self):
        for p in self._enfants:
            with contextlib.suppress(OSError):
                os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=10)
        if _ATTENTE_DE_PRODUCTION is not None:
            daemon._STOP_WAIT_SECONDS = _ATTENTE_DE_PRODUCTION
        self._tmp.cleanup()

    def _enfant(self, argv, stdout=None):
        p = subprocess.Popen(argv, stdout=stdout, text=True, start_new_session=True)
        self._enfants.append(p)
        threading.Thread(target=p.wait, daemon=True).start()
        return p

    def _script(self, nom, source):
        chemin = Path(self._tmp.name) / nom
        chemin.write_text(source, encoding="utf-8")
        return chemin

    def _faux_demon(self, mode, code=None):
        token = f"jeton-{mode}"
        p = self._enfant([sys.executable, str(self._script("faux.py", _FAUX_DEMON)), token, mode],
                         stdout=subprocess.PIPE)
        port = int(p.stdout.readline())
        lock = {"pid": p.pid, "port": port, "token": token}
        if code is not None:
            lock["code"] = code
        daemon.write_lock(self.root, lock)
        self.assertEqual(daemon.daemon_status(self.root)[0], "alive", "étalonnage : le faux démon répond")
        return p, lock


@unittest.skipIf(os.name == "nt", "SIGTERM ignorable : POSIX seulement (sous Windows, TerminateProcess)")
class ArretVerifieTests(_Base):
    def test_stop_sur_un_pid_qui_SURVIT_garde_le_verrou(self):
        """Le défaut du ticket : rc 0, `stopped`, verrou retiré, second démon admis."""
        p, lock = self._faux_demon("ignore")
        rc, out, err = _main(["--stop", "--root", str(self.root)])
        self.assertIsNone(p.poll(), "étalonnage : le faux démon a bien survécu")
        self.assertEqual(rc, 2, out)
        self.assertEqual(out["status"], "still-running", out)
        self.assertEqual((out["pid"], out["lock"]), (p.pid, "kept"), out)
        self.assertEqual(out["waited_seconds"], daemon._STOP_WAIT_SECONDS, "la borne est LUE à l'appel")
        self.assertIn(f"pid {p.pid} survived SIGTERM", err, "la ligne stderr nomme le pid : c'est le canal que le pilote lit")
        self.assertIn("KEPT", err)
        self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"], "le verrou est GARDÉ")
        self.assertFalse(daemon.acquire_lock(self.root, {"pid": 1, "port": 0, "token": "second"}),
                         "aucun second démon n'est admis tant que le premier vit")

    def test_stop_sur_un_pid_qui_MEURT_libere_le_verrou(self):
        """Sous la borne de PRODUCTION : ce cas rend dès que le pid disparaît, et une
        borne de banc abaissée en ferait un témoin d'horloge sous charge."""
        p, _lock = self._faux_demon("default")
        with mock.patch.object(daemon, "_STOP_WAIT_SECONDS", _ATTENTE_DE_PRODUCTION):
            rc, out, _err = _main(["--stop", "--root", str(self.root)])
        self.assertEqual((rc, out["status"], out["pid"]), (0, "stopped", p.pid))
        self.assertFalse(daemon.lock_path(self.root).exists())
        self.assertFalse(daemon.pid_alive(p.pid))

    def test_stop_juge_la_mort_par_le_pid_et_non_par_le_ping(self):
        """Un démon VIVANT mais MUET après SIGTERM : sonder le ping rendrait `stopped`
        et relâcherait le verrou d'un pid vivant. Seule la sonde du pid le garde."""
        p, lock = self._faux_demon("muet")
        rc, out, _err = _main(["--stop", "--root", str(self.root)])
        self.assertIsNone(p.poll(), "étalonnage : le faux démon a bien survécu")
        self.assertEqual((rc, out["status"], out["pid"], out.get("lock")), (2, "still-running", p.pid, "kept"), out)
        self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"], "le verrou est GARDÉ")
        self.assertEqual(daemon.daemon_status(self.root)[0], "stale",
                         "étalonnage : le faux démon est bien devenu MUET (pid vivant, ping silencieux)")

    def test_un_refus_de_kill_est_rapporte_et_le_verrou_est_garde(self):
        """`os.kill` refuse SIGTERM (EPERM) : l'erreur est RAPPORTÉE, jamais avalée."""
        p, lock = self._faux_demon("ignore")
        reel = os.kill

        def refuse(pid, sig):
            if sig == signal.SIGTERM:
                raise PermissionError("denied")
            return reel(pid, sig)
        with mock.patch.object(daemon.os, "kill", refuse):
            rc, out, _err = _main(["--stop", "--root", str(self.root)])
        self.assertEqual((rc, out["status"]), (2, "still-running"), out)
        self.assertTrue(out["kill_error"].startswith("PermissionError"), out)
        self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"])

    def test_dash_ne_relance_pas_par_dessus_un_perime_qui_survit(self):
        _p, lock = self._faux_demon("ignore", code="empreinte-perimee")
        lances = []
        with mock.patch.object(daemon, "spawn_detached", lambda root: lances.append(root) or False):
            rc, _out, err = _main(["--dash", "--root", str(self.root)])
        self.assertEqual(rc, 2)
        self.assertEqual(lances, [], "aucun second démon lancé")
        self.assertIn("KEPT", err)
        self.assertEqual(daemon.read_lock(self.root)["token"], lock["token"], "le verrou est GARDÉ")


class BornesEtPremissesTests(unittest.TestCase):
    """Ce que les autres témoins ne lisent pas : la valeur de PRODUCTION des bornes
    (`_Base` les abaisse) et la prémisse « aucun handler SIGTERM » qui rend vraie la
    docstring de `stop_and_release` et la disparition mesurée en 1-13 ms. Tous OS."""

    def test_les_bornes_de_production_sont_dans_leur_plage(self):
        self.assertIsNotNone(_ATTENTE_DE_PRODUCTION, "la borne d'attente existe")
        self.assertTrue(2.0 <= _ATTENTE_DE_PRODUCTION <= 30.0,
                        f"{_ATTENTE_DE_PRODUCTION} s : trop court rend `still-running` sur un démon sain, "
                        "trop long fige `--stop`")
        self.assertTrue(0.0 < _SONDAGE_DE_PRODUCTION <= 1.0, f"pause de sondage {_SONDAGE_DE_PRODUCTION} s")

    def test_aucun_handler_SIGTERM_dans_le_demon_ni_dans_ce_qu_il_charge(self):
        """Témoin de TEXTE seul, borné : il voit `.signal(` et `add_signal_handler(`, et
        deux graphies lui restent INVISIBLES — `from signal import signal as s` puis
        `s(...)`, et `getattr(signal, "signal")(...)`."""
        charge = re.compile(r'_load_sibling\(\s*"[^"]+"\s*,\s*"([^"/\\]+\.py)"\s*\)')
        handler = re.compile(r"(?:\.signal|add_signal_handler)\(\s*([^,)]*)")
        vus, a_lire, poses = set(), ["dashboard_daemon.py"], []
        while a_lire:
            nom = a_lire.pop()
            if nom in vus or not (HERE / nom).is_file():
                continue
            vus.add(nom)
            texte = (HERE / nom).read_text(encoding="utf-8")
            a_lire += charge.findall(texte)
            for n, ligne in enumerate(texte.splitlines(), 1):
                poses += [(nom, n, m.group(1).strip()) for m in handler.finditer(ligne)]
        self.assertIn("dashboard.py", vus, f"fermeture de chargement dérivée : {sorted(vus)}")
        fautifs = [p for p in poses if "SIGTERM" in p[2] or not re.fullmatch(r"signal\.SIG[A-Z0-9]+", p[2])]
        self.assertEqual(fautifs, [], "un handler SIGTERM (ou non lisible) rend fausse la docstring de stop_and_release")


class ReleveSurPsSimuleTests(unittest.TestCase):
    """Le relevé sur un `ps` SIMULÉ : chaque forme, chaque grandeur, EXACTES. Tous OS."""

    PY = "/usr/bin/python3"
    K = "/Users/me/k/.agents/bin/dashboard_daemon.py"

    def _releve(self, *lignes):
        with mock.patch.object(daemon.subprocess, "run", _ps(b"".join(lignes))):
            return daemon._demons_du_poste()

    def test_les_formes_de_lancement_que_main_accepte_sont_vues(self):
        """`main()` accepte `--idle-hours` et `--root` dans n'importe quel ordre, et `--root=X`."""
        py, k = self.PY, self.K
        formes = {
            "canonique": (f"{py} {k} --daemon --root /k", "/k"),
            "idle apres": (f"{py} {k} --daemon --root /k --idle-hours 8", "/k"),
            "idle avant": (f"{py} {k} --idle-hours 8 --daemon --root /k", "/k"),
            "root avant": (f"{py} {k} --root /k --daemon", "/k"),
            "root=": (f"{py} {k} --root=/k --daemon", "/k"),
            "sans root": (f"{py} {k} --daemon", None),
            "root a espaces": (f"{py} {k} --daemon --root /autre projet/x", "/autre projet/x"),
            "script a espaces": (f"{py} /Users/me b/k/.agents/bin/dashboard_daemon.py --daemon --root /Users/me b/k",
                                 "/Users/me b/k"),
            "script relatif": ("python3 .agents/bin/dashboard_daemon.py --daemon --root /k", "/k"),
            "windows": (r"C:\py\python.exe C:\k\.agents\bin\dashboard_daemon.py --daemon --root C:\k", r"C:\k"),
            "python framework macOS": ("/opt/py/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/"
                                       f"Python {k} --daemon --root /k", "/k"),
            "python3.12 -u": (f"/usr/local/bin/python3.12 -u {k} --daemon --root /k", "/k"),
            "python3.14t": (f"/usr/local/bin/python3.14t {k} --daemon --root /k", "/k"),
            "option -X a valeur": (f"{py} -X dev {k} --daemon --root /k", "/k"),
            "option -W a valeur": (f"{py} -W ignore {k} --daemon --root /k", "/k"),
            "option -Xdev collee": (f"{py} -Xdev {k} --daemon --root /k", "/k"),
            "racine longue": (f"{py} {k} --daemon --root /{'r' * 120}/{'s' * 120}", f"/{'r' * 120}/{'s' * 120}"),
        }
        for nom, (args, racine) in formes.items():
            with self.subTest(forme=nom):
                self.assertEqual(self._releve(_ligne(4242, 2048, args)),
                                 [{"pid": 4242, "rss_octets": 2048 * 1024, "root": racine}])

    def test_ce_qui_n_est_pas_un_run_du_demon_n_est_pas_compte(self):
        """Appels brefs du même fichier, enveloppeurs, outils qui CITENT la commande, voisins."""
        py, k = self.PY, self.K
        for nom, args in {
            "status": f"{py} {k} --status --root /k",
            "stop": f"{py} {k} --stop --root /k",
            "ensure": f"{py} {k} --ensure --root /k",
            "dash": f"{py} {k} --dash --root /k",
            "pytest qui nomme le banc": f"{py} -m pytest .agents/bin/test_dashboard_daemon.py --daemon",
            "banc voisin": f"{py} /Users/me/k/.agents/bin/test_dashboard_daemon.py --daemon --root /k",
            "suffixe .bak": f"{py} {k}.bak --daemon --root /k",
            "drapeau voisin": f"{py} {k} --daemon-x --root /k",
            "-m qui nomme le script": f"{py} -m dashboard_daemon.py --daemon",
            "-c qui nomme le script": f"{py} -c dashboard_daemon.py --daemon",
            "outil python qui cite le chemin": f"{py} /usr/local/bin/outil {k} --daemon --root /k",
            "outil relatif qui cite le script": f"{py} outil dashboard_daemon.py --daemon",
            "programme .py qui cite le script": f"{py} /Users/me/outil.py dashboard_daemon.py --daemon",
            "grep -n": f"/usr/bin/grep -n daemon {k}",
            "grep qui cite la forme": "grep -n dashboard_daemon.py --daemon notes.txt",
            "pgrep -lf": "pgrep -lf dashboard_daemon.py --daemon",
            "editeur": f"vim {k} --daemon",
            "tail du log": "tail -f /tmp/dashboard_daemon.py --daemon.log",
            "zsh -c": f"/bin/zsh -c eval '{py} {k} --daemon --root /k'",
            "bash -c": f"bash -c while true; do {py} {k} --daemon --root /k; done",
            "timeout": f"timeout 3600 {py} {k} --daemon --root /k",
            "caffeinate": f"caffeinate -i {py} {k} --daemon --root /k",
            "uv run": f"uv run {py} {k} --daemon --root /k",
        }.items():
            with self.subTest(ligne=nom):
                self.assertEqual(self._releve(_ligne(7, 100, args)), [])

    def test_deux_demons_sont_rendus_et_la_grandeur_est_exacte(self):
        """Octets BRUTS : 2048 Kio = 2 097 152, ni 2048 (Kio), ni 2 048 000 (décimal), ni 0.
        Une ligne tronquée (deux champs) est sautée, jamais une exception."""
        a = f"{self.PY} {self.K} --daemon --root /a"
        b = f"{self.PY} /o/.agents/bin/dashboard_daemon.py --daemon --root /b"
        vus = self._releve(_ligne(1, 10, "/sbin/launchd"), _ligne(11, 2048, a), b"    77      12\n",
                           _ligne(2, 5, "/bin/zsh"), _ligne(22, 4096, b))
        self.assertEqual(vus, [{"pid": 11, "rss_octets": 2_097_152, "root": "/a"},
                               {"pid": 22, "rss_octets": 4_194_304, "root": "/b"}])

    def test_un_ps_illisible_rend_None_jamais_une_liste_vide(self):
        un_demon = _ligne(11, 2048, f"{self.PY} {self.K} --daemon --root /a")
        for nom, faux in {
            "absent": _ps(raises=FileNotFoundError("ps")),
            "delai": _ps(raises=subprocess.TimeoutExpired("ps", 5)),
            "muet": _ps(b"", 0),
            "blanc": _ps(b"  \n \n", 0),
            "rc non nul": _ps(un_demon, 1),
        }.items():
            with self.subTest(ps=nom), mock.patch.object(daemon.subprocess, "run", faux):
                self.assertIsNone(daemon._demons_du_poste())

    def test_ps_est_lu_sur_toute_la_machine_sans_troncature_et_borne(self):
        appels = []
        with mock.patch.object(daemon.subprocess, "run", _ps(b"", 0, calls=appels)):
            daemon._demons_du_poste()
        argv, kw = appels[0]
        self.assertIn("-A", argv, "sans -A, `ps` ne voit que la session courante")
        self.assertIn("-ww", argv, "sans -ww, `ps` tronque la ligne et la racine se perd")
        self.assertIsInstance(kw.get("timeout"), (int, float), "un `ps` qui pend ne doit pas pendre `--status`")
        self.assertLessEqual(kw["timeout"], 10, "un délai de `ps` plus long fige `--status`, commande manuelle")

    def test_la_forme_que_LANCE_spawn_detached_est_vue_par_le_releve(self):
        """Couplage au lanceur RÉEL : une dérive de `spawn_detached` rougit ici. La ligne
        est construite avec l'interpréteur FIXE du banc, pas celui qui le fait tourner."""
        vus, racine = [], Path("/un projet/k")
        with mock.patch.object(daemon.subprocess, "Popen", lambda argv, **kw: vus.append(argv) or types.SimpleNamespace(pid=0)):
            self.assertTrue(daemon.spawn_detached(racine))
        ligne = " ".join([self.PY] + [str(mot) for mot in vus[0][1:]])
        self.assertEqual(self._releve(_ligne(4242, 2048, ligne)),
                         [{"pid": 4242, "rss_octets": 2048 * 1024, "root": str(racine)}], ligne)

    def test_la_forme_que_LANCE_le_hook_de_session_est_vue_par_le_releve(self):
        """Second lanceur RÉEL (Claude Code) : `.claude/hooks/session-start.sh` lance le démon
        par son PROPRE `Popen`, sans `spawn_detached`. Ses arguments sont LUS dans le hook (le
        script que nomme `_daemon`, puis les littéraux) : une dérive de ce lanceur rougit ici."""
        source = (HERE.parent.parent / ".claude" / "hooks" / "session-start.sh").read_text(encoding="utf-8")
        bloc = re.search(r"<< 'PYEOF'\n(.*?)\nPYEOF\n", source, re.S)
        self.assertIsNotNone(bloc, "le bloc Python du hook a changé de forme : relire son lanceur")
        arbre = ast.parse(bloc.group(1))
        noms = {n.targets[0].id: n.value for n in ast.walk(arbre)
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        lancements = [n.args[0] for n in ast.walk(arbre)
                      if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "Popen"
                      and n.args and isinstance(n.args[0], ast.List)]
        self.assertEqual(len(lancements), 1, "le hook lance le démon par UN Popen")
        racine = "/un projet/k"

        def valeur(noeud):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                return noeud.value
            if ast.unparse(noeud) == "sys.executable":
                return self.PY
            if isinstance(noeud, ast.Name) and noeud.id == "_root":
                return racine
            if isinstance(noeud, ast.Name) and noeud.id in noms:
                return valeur(noms[noeud.id])
            if isinstance(noeud, ast.Call) and ast.unparse(noeud.func) == "os.path.join":
                return "/".join(valeur(a) for a in noeud.args)
            self.fail(f"argument du lanceur du hook non lu : {ast.unparse(noeud)}")

        ligne = " ".join(valeur(mot) for mot in lancements[0].elts)
        self.assertEqual(self._releve(_ligne(4242, 2048, ligne)),
                         [{"pid": 4242, "rss_octets": 2048 * 1024, "root": racine}], ligne)


@unittest.skipIf(os.name == "nt", "pas de `ps` sous Windows : le champ y vaut None (témoin simulé ci-dessus)")
class ReleveSurVraiPsTests(_Base):
    def _dormeur(self, *argv):
        p = self._enfant(list(argv), stdout=subprocess.PIPE)
        p.stdout.readline()
        return p

    def test_un_vrai_ps_rend_trois_demons_d_autres_projets_et_pas_l_enveloppeur(self):
        a, b, c = (Path(self._tmp.name) / f"projet {x}" for x in "abc")
        script = str(self._script("dashboard_daemon.py", _DORMEUR))
        pa = self._dormeur(sys.executable, script, "--daemon", "--root", str(a))
        pb = self._dormeur(sys.executable, script, "--idle-hours", "8", "--daemon", "--root", str(b))
        # Un enveloppeur qui RESTE parent (une commande suit) : deux processus, un seul démon.
        pc = self._dormeur("/bin/sh", "-c", '"$@"; :', "sh", sys.executable, script, "--daemon", "--root", str(c))
        rc, out, _err = _main(["--status", "--root", str(self.root)])
        self.assertEqual(rc, 0)
        par_racine = {}
        for d in out["demons_du_poste"]:
            par_racine.setdefault(d["root"], []).append(d)
        self.assertEqual([d["pid"] for d in par_racine.get(str(a), [])], [pa.pid])
        self.assertEqual([d["pid"] for d in par_racine.get(str(b), [])], [pb.pid])
        enfant = par_racine.get(str(c), [])
        self.assertEqual(len(enfant), 1, f"l'enfant Python compté UNE fois : {enfant}")
        self.assertNotEqual(enfant[0]["pid"], pc.pid, "l'enveloppeur `sh` n'est pas un démon")
        for d in (par_racine[str(a)][0], par_racine[str(b)][0], enfant[0]):
            self.assertGreater(d["rss_octets"], 1_000_000, "un interpréteur Python pèse plus d'un Mo")
            self.assertLess(d["rss_octets"], 1_000_000_000, "…et moins d'un Go : l'unité est l'octet")


@unittest.skipIf(os.name == "nt", "faux démons POSIX")
class EtalonnageDuReleveTests(_Base):
    """`demons_du_poste_etalon` : le relevé est étalonné sur le SEUL démon que `--status`
    peut garantir, et ce démon (son pid) est à l'écran. `ps` SIMULÉ : le verdict ne
    dépend ni de l'ordre de `ps` ni des autres démons du poste."""

    def _status(self, ps):
        with mock.patch.object(daemon.subprocess, "run", ps):
            rc, out, _err = _main(["--status", "--root", str(self.root)])
        self.assertEqual(rc, 0)
        return out

    @staticmethod
    def _autre(pid, racine):
        return _ligne(pid, 2048, f"/usr/bin/python3 /o/.agents/bin/dashboard_daemon.py --daemon --root {racine}")

    def test_VU_quand_le_demon_interroge_est_dans_le_releve(self):
        p, _lock = self._faux_demon("default")
        out = self._status(_ps_releve(self._autre(11, "/autre") + self._autre(p.pid, self.root)))
        self.assertEqual([d["pid"] for d in out["demons_du_poste"]], [11, p.pid])
        self.assertEqual(out["demons_du_poste_etalon"], {"pid": p.pid, "vu": True})

    def test_PAS_VU_quand_le_demon_interroge_manque_au_releve(self):
        """Lisible mais sans LUI : un autre pid de la MÊME racine, ou aucun démon du tout."""
        p, _lock = self._faux_demon("default")
        for nom, sortie in {
            "meme racine, autre pid": self._autre(11, self.root),
            "aucun demon": _ligne(1, 10, "/sbin/launchd"),
        }.items():
            with self.subTest(releve=nom):
                out = self._status(_ps_releve(sortie))
                self.assertIsInstance(out["demons_du_poste"], list)
                self.assertEqual(out["demons_du_poste_etalon"], {"pid": p.pid, "vu": False})

    def test_rien_a_etalonner_rend_null_jamais_faux(self):
        releve = _ps_releve(self._autre(11, "/autre"))
        self.assertIsNone(self._status(releve)["demons_du_poste_etalon"], "aucun verrou")
        mort = subprocess.Popen([sys.executable, "-c", "pass"])
        mort.wait()
        daemon.write_lock(self.root, {"pid": mort.pid, "port": 1, "token": "t"})
        out = self._status(releve)
        self.assertEqual(out["status"], "stale")
        self.assertIsNone(out["demons_du_poste_etalon"], "verrou périmé : pas un démon vivant à étalonner")
        self.assertEqual([d["pid"] for d in out["demons_du_poste"]], [11])
        self._faux_demon("default")
        out = self._status(_ps(raises=FileNotFoundError("ps")))
        self.assertIsNone(out["demons_du_poste"])
        self.assertIsNone(out["demons_du_poste_etalon"], "`ps` illisible : rien à étalonner")


if __name__ == "__main__":
    unittest.main()
