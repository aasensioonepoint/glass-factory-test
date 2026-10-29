#!/usr/bin/env python3
"""T-00000962 (BK-157) — `cadre tasks` délègue au moteur du board.

CE QUE LE BANC TIENT. Critères du board : `cadre tasks list|new|start|done`
fonctionne dans un projet initialisé SANS `.agents/bin` ; les codes de sortie
suivent l'interface décidée (S-01M4JPBTF82G4PW7DDDYRSVZC1, BK-156 § 6-7 :
`0` succès, `1` réponse négative d'un contrôle, `2` erreur ou refus) ; « même
verbe, mêmes arguments, mêmes flux, même code de sortie que `tasks.py --root
<racine du projet> <verbe> …` », la racine venant de `cadre`, jamais de `--root`
ni de `CLAUDE_PROJECT_DIR`.

DEUX ÉTAGES.
  * Par la CLI RÉELLE, en sous-processus (`python -m cadre.cli`, `PYTHONPATH`
    = le parent du paquet du kit, `.agents/vendor/` ou `src/` — `vendor_paths`) : un projet neuf (`git init` puis `cadre init`) qui ne
    porte aucun `.agents/bin`, lancé depuis un SOUS-RÉPERTOIRE du projet — le
    moteur prend `.` par défaut, donc une délégation qui oublierait `--root`
    écrirait le board dans le sous-répertoire et rougirait ici.
  * En processus, avec un exécuteur FACTICE injecté : le passage des codes
    0/1/2, la conversion en 2 de tout autre code (expiration, exécutable absent,
    signal) et d'un traceback du moteur, les refus d'avant lancement (moteur
    absent, arbre qui n'est pas le kit, `--root` en tête), et l'ORDRE de
    résolution du moteur : embarqué dans le paquet (`<paquet>/_moteur/`)
    d'abord, puis l'arbre source du kit marqué, sinon refus en 2 — jamais le
    `.agents/bin/tasks.py` du projet, ni préféré ni en repli.
Et sans lancer quoi que ce soit, `FermetureDuMoteurTests` : les clés
force-include de `pyproject.toml` sont EXACTEMENT la clôture transitive des
moteurs de `MOTEURS` (imports et noms de fichier frères, `events.py` et
`conftest.py` exclus), chacune copiée sous `cadre/_moteur/`, toutes au sdist.

BORNES, dites : la wheel elle-même — construction, installation, verbes réels
depuis le paquet installé — est mesurée par `test_cadre_cmd_tasks_wheel.py`,
pas ici. Les gardes (`.agents/state/gates/`) sont ABSENTES du projet neuf : le
régime armé de l'adoptant n'est pas mesuré par ce banc. Témoin de non-écriture
du kit : sha256 de chaque fichier de `.agents/state/board/` du kit et de sa vue
`.agents/state/local/TASKS.md`, avant et après.

CE BANC VOYAGE (aucun `strip:`). Chez un adoptant, sans le marqueur
`.agents/IS_THE_KIT` : `DelegationReelleTests` (moteur réel du kit) et
`FermetureDuMoteurTests` (manifeste du kit, qui ne voyage pas) SAUTENT, en
l'annonçant ; `CodesEtRefusTests` tourne, chaque cas qui va jusqu'au lancement
recevant un kit FACTICE (`kit=`), jamais la résolution par défaut — qui y
refuserait en 2 pour une autre cause et rendrait le cas vert à vide. git
absent : `DelegationReelleTests` est en ERREUR, jamais un saut.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Le paquet où qu'il vive (`.agents/vendor/cadre`, sinon `src/cadre`) : chargé par
# `vendor_paths.py`, lui-même chargé PAR CHEMIN (patron v3prep) ; `sys.path` intact.
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_cmd_tasks_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
PKG = _VENDOR.charger_paquet(ROOT, "cadre")
PKG_DIR = Path(PKG.__file__).resolve().parent

from cadre import cli  # noqa: E402
from cadre import commandes_adoptant as ca  # noqa: E402
from cadre.executor import Resultat  # noqa: E402
from cadre.paths import vider_cache_racine  # noqa: E402

# IMPORTÉS TELS QUELS — des noms seuls, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_cli_installed import EST_LE_KIT, SAUT_ADOPTANT  # noqa: E402

GIT = shutil.which("git")
SANS_GIT = "git absent du PATH : un projet neuf est un `git init` réel"
DELAI = 120
_CONFIG_GIT = ("-c", "user.name=banc", "-c", "user.email=banc@exemple.invalid",
               "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}",
               "-c", "init.defaultBranch=main")
_PREFIXES_PURGES = ("GIT_", "CADRE_", "AGENTS_EVENTS_")
_NOMS_PURGES = ("AGENTS_OTEL_DIR", "CLAUDE_PROJECT_DIR", "PYTHONPATH")
ID_TACHE = re.compile(r"\bT-[0-9A-Z]{8,26}\b")


def _env_purge() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(_PREFIXES_PURGES) and k not in _NOMS_PURGES}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _instantane_du_kit() -> dict[str, str]:
    """`{chemin: sha256}` du board du KIT et de sa vue `TASKS.md`. Le CONTENU,
    pas le `mtime` : la porte joue les bancs en parallèle, et le reste de
    `.agents/state/local/` (verrous, caches des hooks) bouge légitimement."""
    # adopting-tree: le board du kit ne voyage pas (strip: .agents/state/) ; seule DelegationReelleTests, kit-only, appelle cet instantané
    fichiers = sorted(p for p in (ROOT / ".agents" / "state" / "board").rglob("*") if p.is_file())
    fichiers += [p for p in [ROOT / ".agents" / "state" / "local" / "TASKS.md"] if p.is_file()]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in fichiers}


class _Banc(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="t962-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.etat = self.base / "etat"
        self.etat.mkdir()

    def _env(self, **en_plus: str) -> dict[str, str]:
        env = _env_purge()
        env["PYTHONPATH"] = str(PKG_DIR.parent)
        env["CADRE_STATE_DIR"] = str(self.etat)
        env["CADRE_CONFIG_HOME"] = str(self.base / "conf")
        env["GIT_CEILING_DIRECTORIES"] = str(self.base)
        env.update(en_plus)
        return env

    def _cadre(self, cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "cadre.cli", *args], cwd=cwd,
                              env=self._env(**env), capture_output=True, text=True,
                              timeout=DELAI, check=False)

    def _projet_initialise(self) -> Path:
        projet = self.base / "projet"
        projet.mkdir()
        r = subprocess.run([GIT, *_CONFIG_GIT, "init", "-q"], cwd=projet, env=_env_purge(),
                           capture_output=True, timeout=DELAI, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._cadre(projet, "init")
        self.assertEqual(r.returncode, 0, f"cadre init : {r.stderr}")
        self.assertFalse((projet / ".agents" / "bin").exists(),
                         "le projet initialisé porte un .agents/bin : le critère ne se mesure plus")
        return projet


@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class DelegationReelleTests(_Banc):
    """Par la CLI réelle, moteur réel du kit, projet adoptant sans `.agents/bin`.

    git absent : ERREUR, jamais un saut — un projet neuf est un `git init` réel,
    et un saut ici rendrait la porte verte sans qu'aucune délégation ait tourné."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if GIT is None:
            raise AssertionError(SANS_GIT)

    def test_list_new_start_done_dans_un_projet_sans_agents_bin(self):
        projet = self._projet_initialise()
        sous = projet / "sous" / "rep"
        sous.mkdir(parents=True)
        kit_avant = _instantane_du_kit()

        r = self._cadre(sous, "tasks", "list")
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stderr)
        self.assertIn("TASK BOARD", r.stdout)

        r = self._cadre(sous, "tasks", "new", "sonde T-962 : délégation")
        self.assertEqual(r.returncode, 0, r.stderr)
        trouve = ID_TACHE.search(r.stdout)
        self.assertIsNotNone(trouve, f"aucun identifiant dans la sortie de new : {r.stdout!r}")
        tid = trouve.group(0)
        self.assertIn("pending", r.stdout)

        r = self._cadre(sous, "tasks", "start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("running", r.stdout)

        r = self._cadre(sous, "tasks", "done", tid, "--raison", "banc T-962")
        self.assertEqual(r.returncode, 0, r.stderr)

        r = self._cadre(sous, "tasks", "list", "--task", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"state\s*:\s*\S*\s*done")
        self.assertIn("banc T-962", r.stdout)

        board = projet / ".agents" / "state" / "board"
        self.assertTrue(board.is_dir(), "le board n'est pas sous la racine du projet")
        self.assertFalse((projet / "sous" / ".agents").exists(),
                         "le board est né sous le répertoire courant : `--root` n'a pas été passé")
        self.assertFalse((projet / ".agents" / "bin").exists())
        py = [str(p.relative_to(projet)) for p in projet.rglob("*.py")
              if ".git" not in p.relative_to(projet).parts]
        self.assertEqual(py, [], "un .py est apparu chez l'adoptant")
        self.assertEqual(_instantane_du_kit(), kit_avant, "le board du KIT a bougé")

    def test_la_sortie_est_celle_du_moteur_lance_directement(self):
        """Parité : mêmes octets, même code, sur le même store."""
        projet = self._projet_initialise()
        self.assertEqual(self._cadre(projet, "tasks", "new", "parité").returncode, 0)
        moteur = ROOT / ".agents" / "bin" / "tasks.py"
        for verbe in (["list"], ["list", "--state", "pending"], ["list", "--json"]):
            with self.subTest(verbe=verbe):
                via_cadre = self._cadre(projet, "tasks", *verbe)
                direct = subprocess.run(
                    [sys.executable, str(moteur), "--root", str(projet), *verbe],
                    cwd=projet, env=self._env(), capture_output=True, text=True,
                    timeout=DELAI, check=False)
                self.assertEqual(
                    (via_cadre.returncode, via_cadre.stdout, via_cadre.stderr),
                    (direct.returncode, direct.stdout, direct.stderr))

    def test_un_identifiant_inconnu_sort_en_2_sur_stderr(self):
        projet = self._projet_initialise()
        r = self._cadre(projet, "tasks", "start", "T-99999999")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "", "un refus doit aller sur stderr, pas sur stdout")
        self.assertIn("T-99999999", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_une_faute_d_usage_sort_en_2(self):
        projet = self._projet_initialise()
        for argv in (["list", "--zz-inconnu"], ["start"], ["zz-verbe"]):
            with self.subTest(argv=argv):
                r = self._cadre(projet, "tasks", *argv)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertEqual(r.stdout, "")
                self.assertIn("usage:", r.stderr, "l'usage doit être celui du moteur")
                self.assertNotIn("RÉSERVÉ", r.stderr)

    def test_un_root_en_tete_est_refuse_avant_tout_lancement(self):
        """Mesuré : un second `--root` AVANT le verbe, ou son abréviation, l'emporte
        dans le moteur. La racine vient de `cadre` : la tentative sort en 2."""
        projet = self._projet_initialise()
        autre = self.base / "autre"
        autre.mkdir()
        for argv in (["--root", str(autre), "list"], [f"--root={autre}", "list"],
                     ["--ro", str(autre), "list"], ["--statusline", "--root", str(autre)]):
            with self.subTest(argv=argv):
                r = self._cadre(projet, "tasks", *argv)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("--root", r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertEqual(list(autre.iterdir()), [], "la racine détournée a été écrite")

    def test_la_racine_suit_CADRE_PROJECT_ROOT(self):
        projet = self._projet_initialise()
        ailleurs = self.base / "ailleurs"
        ailleurs.mkdir()
        r = self._cadre(ailleurs, "tasks", "new", "racine forcée", CADRE_PROJECT_ROOT=str(projet))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((projet / ".agents" / "state" / "board").is_dir())
        self.assertEqual(list(ailleurs.iterdir()), [])

    def test_hors_de_tout_projet_le_refus_sort_en_2_sans_trace(self):
        dehors = self.base / "dehors"
        dehors.mkdir()
        r = self._cadre(dehors, "tasks", "list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cadre tasks : racine de projet introuvable", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(list(dehors.iterdir()), [])

    def test_cadre_tasks_nu_rend_l_aide_du_moteur_en_0(self):
        """Comme `tasks.py` nu (BK-156 § 3.6) : l'aide, sur stdout, en 0."""
        projet = self._projet_initialise()
        r = self._cadre(projet, "tasks")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("usage:"), r.stdout[:200])
        self.assertNotIn("RÉSERVÉ", r.stderr)

    def _env_cp1252(self, projet: Path) -> dict[str, str]:
        """Un environnement où stdio est cp1252 STRICT — un pipe sous Windows hors
        mode UTF-8 —, simulé par `PYTHONIOENCODING=cp1252` et `PYTHONUTF8=0`, qui
        l'emportent sur le `PYTHONUTF8=1` de la CI. La garde VÉRIFIE que la
        simulation mord : sinon les témoins qui l'utilisent ne peuvent pas rougir."""
        env = self._env(PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        garde = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.stdout.encoding, sys.stdout.errors)"],
            cwd=projet, env=env, capture_output=True, timeout=DELAI, check=False)
        self.assertEqual(garde.stdout.split(), [b"cp1252", b"strict"],
                         "simulation INERTE : stdout n'est pas cp1252 strict, le témoin ne peut pas rougir")
        return env

    def test_statusline_sur_un_pipe_cp1252_sort_en_0_avec_les_octets_du_moteur(self):
        """BOUT EN BOUT, PAR `cli.main` (T-01M523WZN8WD6YB9RQJJD594ZE).

        `LocalExecutor` décode la sortie du moteur en UTF-8 ; si `cadre` la
        recopie ensuite sur un stdout cp1252 STRICT — un pipe sous Windows hors
        mode UTF-8 —, le glyphe ⏸ de `--statusline` lève `UnicodeEncodeError`
        hors de tout handler : traceback et rc 1, le code que l'interface
        réserve au contrôle négatif. Simulé par `PYTHONIOENCODING=cp1252` et
        `PYTHONUTF8=0`, qui l'emportent sur le `PYTHONUTF8=1` de la CI ; la garde
        vérifie que la simulation mord. Attendu : rc 0 et les MÊMES octets que le
        moteur lancé directement, qui écrit en UTF-8 (`force_utf8_stdio`)."""
        projet = self._projet_initialise()
        self.assertEqual(self._cadre(projet, "tasks", "new", "sonde cp1252").returncode, 0)
        env = self._env_cp1252(projet)

        via_cadre = subprocess.run(
            [sys.executable, "-m", "cadre.cli", "tasks", "--statusline"],
            cwd=projet, env=env, capture_output=True, timeout=DELAI, check=False)
        erreur = via_cadre.stderr.decode("utf-8", errors="replace")
        self.assertNotIn("Traceback", erreur)
        self.assertEqual(via_cadre.returncode, 0, erreur)
        self.assertIn("⏸1".encode("utf-8"), via_cadre.stdout)

        moteur = ROOT / ".agents" / "bin" / "tasks.py"
        direct = subprocess.run(
            [sys.executable, str(moteur), "--root", str(projet), "--statusline"],
            cwd=projet, env=env, capture_output=True, timeout=DELAI, check=False)
        self.assertEqual((via_cadre.returncode, via_cadre.stdout, via_cadre.stderr),
                         (direct.returncode, direct.stdout, direct.stderr))

    def test_une_erreur_d_usage_accentuee_sort_en_UTF8_des_le_premier_octet(self):
        """LES ERREURS D'ARGPARSE DU MOTEUR SORTENT AVANT `force_utf8_stdio`
        (tasks.py : `parse_args` puis `force_utf8_stdio`), donc dans l'encodage
        de SES flux. Sur un pipe cp1252, `--state été` sortait en cp1252
        (`\\xe9t\\xe9`) et `cadre`, qui décode en UTF-8, le rendait en U+FFFD.
        `deleguer` passe `PYTHONIOENCODING=utf-8` au moteur : attendu, rc 2 et
        les MÊMES octets que le moteur lancé directement en UTF-8 dès son
        premier octet. Le moteur lancé en cp1252 garde, lui, ses erreurs
        d'argparse en cp1252 : la parité vaut avec le moteur en UTF-8."""
        projet = self._projet_initialise()
        env = self._env_cp1252(projet)
        verbe = ["list", "--state", "été"]

        via_cadre = subprocess.run(
            [sys.executable, "-m", "cadre.cli", "tasks", *verbe],
            cwd=projet, env=env, capture_output=True, timeout=DELAI, check=False)
        self.assertEqual(via_cadre.returncode, 2, via_cadre.stderr)
        self.assertNotIn("�".encode("utf-8"), via_cadre.stderr,
                         "l'erreur d'argparse du moteur a été décodée dans le mauvais encodage")
        self.assertIn("été".encode("utf-8"), via_cadre.stderr)

        moteur = ROOT / ".agents" / "bin" / "tasks.py"
        direct = subprocess.run(
            [sys.executable, str(moteur), "--root", str(projet), *verbe],
            cwd=projet, env={**env, "PYTHONIOENCODING": "utf-8"}, capture_output=True,
            timeout=DELAI, check=False)
        self.assertEqual((via_cadre.returncode, via_cadre.stdout, via_cadre.stderr),
                         (direct.returncode, direct.stdout, direct.stderr))


class _ExecuteurFactice:
    def __init__(self, code: int = 0, stdout: str = "", stderr: str = "",
                 expire: bool = False) -> None:
        self.reponse = (code, stdout, stderr, expire)
        self.appels: list[dict] = []

    def run(self, argv, *, cwd=None, env=None, timeout=None) -> Resultat:
        self.appels.append({"argv": list(argv), "cwd": cwd, "env": env})
        code, out, err, expire = self.reponse
        return Resultat(argv=tuple(argv), code=code, stdout=out, stderr=err, expire=expire)


class CodesEtRefusTests(unittest.TestCase):
    """En processus : l'interface des codes, sans moteur réel."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="t962u-")).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.projet = self.base / "projet"
        (self.projet / ".agents").mkdir(parents=True)
        ancienne = os.environ.get("CADRE_PROJECT_ROOT")
        os.environ["CADRE_PROJECT_ROOT"] = str(self.projet)
        self.addCleanup(self._restaurer, ancienne)
        vider_cache_racine()

    @staticmethod
    def _restaurer(ancienne):
        if ancienne is None:
            os.environ.pop("CADRE_PROJECT_ROOT", None)
        else:
            os.environ["CADRE_PROJECT_ROOT"] = ancienne

    def _appel(self, argv, executeur, **kw) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ca.cadre_tasks(argv, executeur=executeur, **kw)
        return rc, out.getvalue(), err.getvalue()

    def _kit_factice(self, *, marqueur: bool = True, moteur: bool = True) -> Path:
        kit = self.base / "kit"
        (kit / ".agents" / "bin").mkdir(parents=True, exist_ok=True)
        if marqueur:
            (kit / ".agents" / "IS_THE_KIT").write_text("", encoding="utf-8")
        if moteur:
            (kit / ".agents" / "bin" / "tasks.py").write_text("", encoding="utf-8")
        return kit

    def _paquet_factice(self, *, moteur: bool = True) -> Path:
        """Une racine de paquet comme celle de la wheel : `<paquet>/_moteur/tasks.py`."""
        paquet = self.base / "paquet"
        (paquet / ca.DOSSIER_EMBARQUE).mkdir(parents=True, exist_ok=True)
        if moteur:
            (paquet / ca.DOSSIER_EMBARQUE / "tasks.py").write_text("", encoding="utf-8")
        return paquet

    def test_la_commande_lancee_porte_le_moteur_du_kit_et_la_racine_de_cadre(self):
        kit = self._kit_factice()
        ex = _ExecuteurFactice()
        rc, _, _ = self._appel(["list", "--state", "pending"], ex, kit=kit)
        self.assertEqual(rc, 0)
        (appel,) = ex.appels
        self.assertEqual(appel["argv"][0], sys.executable)
        self.assertEqual(Path(appel["argv"][1]), (kit / ".agents" / "bin" / "tasks.py").resolve())
        self.assertEqual(appel["argv"][2:], ["--root", str(self.projet), "list", "--state", "pending"])
        self.assertIsNone(appel["cwd"], "le répertoire courant de l'appelant est gardé")
        self.assertEqual(appel["env"], {"CLAUDE_PROJECT_DIR": str(self.projet),
                                        "PYTHONIOENCODING": "utf-8"})

    def test_le_relais_ecrit_en_UTF8_sur_des_flux_cp1252(self):
        """`_flux_comme_le_moteur`, EN PROCESSUS — sans lui, seul un banc de bout
        en bout réservé au kit l'exerçait. Des flux cp1252 STRICTS (un pipe sous
        Windows hors mode UTF-8) : la sortie du moteur, décodée en UTF-8, en
        sort en UTF-8, octet pour octet, sans `UnicodeEncodeError`.
        MUTATION : appel à `_flux_comme_le_moteur` retiré → `UnicodeEncodeError` → rouge."""
        kit = self._kit_factice()
        ex = _ExecuteurFactice(stdout="⏸1 ✓0\n", stderr="été ⏸\n")
        octets_out, octets_err = io.BytesIO(), io.BytesIO()
        out = io.TextIOWrapper(octets_out, encoding="cp1252", newline="\n")
        err = io.TextIOWrapper(octets_err, encoding="cp1252", newline="\n")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ca.cadre_tasks(["--statusline"], executeur=ex, kit=kit)
        out.flush()
        err.flush()
        self.assertEqual(rc, 0)
        self.assertEqual(octets_out.getvalue(), "⏸1 ✓0\n".encode("utf-8"))
        self.assertEqual(octets_err.getvalue(), "été ⏸\n".encode("utf-8"))

    def test_un_refus_de_cadre_tasks_sort_aussi_en_UTF8(self):
        """Les refus de `deleguer` (ici `--root` en tête) parlent la même langue
        que le moteur qu'ils remplacent : UTF-8 sur un stderr cp1252, pas
        `refus\\xe9` en code page locale à côté d'un `été` en UTF-8.
        MUTATION : `_flux_comme_le_moteur` appelé dans `_restituer` seul → rouge."""
        octets_err = io.BytesIO()
        err = io.TextIOWrapper(octets_err, encoding="cp1252", newline="\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = ca.cadre_tasks(["--root", "/x", "list"], executeur=_ExecuteurFactice(),
                                kit=self._kit_factice())
        err.flush()
        self.assertEqual(rc, 2)
        self.assertIn("refusé".encode("utf-8"), octets_err.getvalue())

    def test_le_moteur_embarque_dans_le_paquet_gagne_sur_le_kit(self):
        """Ordre de résolution (1) : le moteur de la wheel, `<paquet>/_moteur/`,
        est lancé même quand un kit marqué est là.
        MUTATION : ordre inversé (kit d'abord) → le kit gagne → rouge."""
        paquet = self._paquet_factice()
        for marqueur in (True, False):
            with self.subTest(kit_marque=marqueur):
                ex = _ExecuteurFactice()
                rc, _, err = self._appel(["list"], ex, kit=self._kit_factice(marqueur=marqueur),
                                         paquet=paquet)
                self.assertEqual(rc, 0, err)
                (appel,) = ex.appels
                self.assertEqual(Path(appel["argv"][1]),
                                 (paquet / ca.DOSSIER_EMBARQUE / "tasks.py").resolve())
                self.assertEqual(appel["argv"][2:4], ["--root", str(self.projet)])

    def test_sans_moteur_embarque_le_kit_marque_est_lance(self):
        """Ordre de résolution (2) : paquet sans `_moteur/tasks.py` → le kit marqué."""
        kit = self._kit_factice()
        ex = _ExecuteurFactice()
        rc, _, err = self._appel(["list"], ex, kit=kit, paquet=self._paquet_factice(moteur=False))
        self.assertEqual(rc, 0, err)
        self.assertEqual(Path(ex.appels[0]["argv"][1]),
                         (kit / ".agents" / "bin" / "tasks.py").resolve())

    def test_ni_paquet_ni_kit_sort_en_2_nommant_les_deux_chemins(self):
        """Ordre de résolution (3) : rien n'est lancé, et le refus nomme le chemin
        embarqué ET le chemin du kit cherchés."""
        paquet = self._paquet_factice(moteur=False)
        kit = self._kit_factice(marqueur=False)
        ex = _ExecuteurFactice()
        rc, out, err = self._appel(["list"], ex, kit=kit, paquet=paquet)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn(str(paquet / ca.DOSSIER_EMBARQUE / "tasks.py"), err)
        self.assertIn(str(kit / ".agents" / "bin" / "tasks.py"), err)
        self.assertIn("IS_THE_KIT", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(ex.appels, [])

    def test_le_tasks_py_du_projet_n_est_jamais_lance(self):
        """Le moteur vient du paquet ou du kit, JAMAIS du projet : un
        `<projet>/.agents/bin/tasks.py` — celui d'un adoptant, peut-être piégé —
        n'est ni préféré au moteur embarqué, ni pris en repli quand rien d'autre
        ne répond. MUTATION : `moteur` qui consulte la racine du projet (avant
        le paquet, ou en dernier recours) → rouge."""
        piege = self.projet / ".agents" / "bin" / "tasks.py"
        piege.parent.mkdir(parents=True)
        piege.write_text("raise SystemExit('piege : tasks.py du projet')\n", encoding="utf-8")
        vide = self.base / "paquet-vide"
        vide.mkdir()
        ex = _ExecuteurFactice()
        rc, out, err = self._appel(["list"], ex, kit=self._kit_factice(marqueur=False), paquet=vide)
        self.assertEqual((rc, out), (2, ""), "le tasks.py du projet a servi de repli")
        self.assertEqual(ex.appels, [])
        self.assertNotIn(str(piege), err)
        paquet = self._paquet_factice()
        ex = _ExecuteurFactice()
        rc, _, err = self._appel(["list"], ex, kit=self._kit_factice(), paquet=paquet)
        self.assertEqual(rc, 0, err)
        self.assertEqual(Path(ex.appels[0]["argv"][1]),
                         (paquet / ca.DOSSIER_EMBARQUE / "tasks.py").resolve(),
                         "le tasks.py du projet a ete prefere au moteur embarque")

    def test_les_codes_0_1_2_et_les_flux_passent_tels_quels(self):
        for code in (0, 1, 2):
            with self.subTest(code=code):
                ex = _ExecuteurFactice(code, stdout="SORTIE\n", stderr="ERREUR\n")
                self.assertEqual(self._appel(["list"], ex, kit=self._kit_factice()),
                                 (code, "SORTIE\n", "ERREUR\n"))

    def test_tout_autre_code_devient_2_avec_sa_cause(self):
        for code, expire in ((124, True), (127, False), (126, False), (3, False), (-9, False)):
            with self.subTest(code=code):
                ex = _ExecuteurFactice(code, stderr="cadre: motif de l'exécuteur\n", expire=expire)
                rc, out, err = self._appel(["list"], ex, kit=self._kit_factice())
                self.assertEqual(rc, 2)
                self.assertEqual(out, "")
                self.assertIn("cadre tasks", err)
                self.assertIn("motif de l'exécuteur", err)

    def test_une_expiration_devient_2_quel_que_soit_le_code(self):
        """`expire` l'emporte sur le code : une borne dépassée sort en 2 avec sa
        cause, même quand l'exécuteur rapporte 0, 1 ou 2.
        MUTATION : `expire` ignoré → le code 0/1/2 passe tel quel → rouge."""
        for code in (0, 1, 2, 124):
            with self.subTest(code=code):
                ex = _ExecuteurFactice(code, stdout="", stderr="partiel\n", expire=True)
                rc, out, err = self._appel(["list"], ex, kit=self._kit_factice())
                self.assertEqual(rc, 2)
                self.assertEqual(out, "")
                self.assertIn("dépassé sa borne", err)
                self.assertIn("partiel", err)

    def test_un_traceback_du_moteur_devient_2_sans_la_trace(self):
        trace = ("avant\nTraceback (most recent call last):\n  File \"tasks.py\", line 1\n"
                 "    raise\nRuntimeError: board illisible\n")
        rc, out, err = self._appel(["list"], _ExecuteurFactice(1, stdout="", stderr=trace),
                                   kit=self._kit_factice())
        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", err)
        self.assertNotIn('File "tasks.py"', err)
        self.assertIn("avant", err)
        self.assertIn("RuntimeError: board illisible", err)

    def test_un_moteur_absent_sort_en_2_sans_lancer(self):
        kit = self._kit_factice(moteur=False)
        ex = _ExecuteurFactice()
        rc, out, err = self._appel(["list"], ex, kit=kit)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn(str(kit / ".agents" / "bin" / "tasks.py"), err)
        self.assertEqual(ex.appels, [])

    def test_un_arbre_qui_n_est_pas_le_kit_n_est_jamais_lance(self):
        """Sans le marqueur du kit, le `tasks.py` trouvé peut être celui d'un
        adoptant : il n'est pas exécuté."""
        kit = self._kit_factice(marqueur=False)
        ex = _ExecuteurFactice()
        rc, _, err = self._appel(["list"], ex, kit=kit)
        self.assertEqual(rc, 2)
        self.assertIn("IS_THE_KIT", err)
        self.assertEqual(ex.appels, [])

    def test_un_root_en_tete_sort_en_2_sans_lancer(self):
        for argv in (["--root", "x", "list"], ["--root=x", "list"], ["--r", "x"],
                     ["--statusline", "--roo", "x"]):
            with self.subTest(argv=argv):
                ex = _ExecuteurFactice()
                rc, _, err = self._appel(argv, ex)
                self.assertEqual(rc, 2)
                self.assertIn("--root", err)
                self.assertEqual(ex.appels, [])

    def test_un_root_apres_le_verbe_est_laisse_au_moteur(self):
        """Après le verbe, le moteur le refuse lui-même en 2 (mesuré) : `cadre`
        ne le juge pas, et une valeur qui ressemble à `--root` reste un argument."""
        ex = _ExecuteurFactice()
        rc, _, _ = self._appel(["new", "--root"], ex, kit=self._kit_factice())
        self.assertEqual(rc, 0)
        self.assertEqual(ex.appels[0]["argv"][-2:], ["new", "--root"])

    def test_un_octet_nul_est_refuse_en_2_par_l_executeur_reel(self):
        """Le refus vient de l'EXÉCUTEUR (`ExecutionRefusee`), pas de la résolution
        du moteur : sans le kit factice ni l'assertion « octet nul », ce cas resterait
        vert chez un adoptant, où `moteur` refuse en 2 pour une autre cause."""
        rc, out, err = self._appel(["new", "a\x00b"], None, kit=self._kit_factice())
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("cadre tasks", err)
        self.assertIn("octet nul", err)
        self.assertNotIn("Traceback", err)


#: Frères que la clôture du moteur N'EMBARQUE PAS : `events.py` est cherché sous
#: `parents[2]` du moteur (`replay_sync`), jamais à côté de lui ; `conftest.py`
#: est de la configuration pytest.
HORS_CLOTURE = frozenset({"events.py", "conftest.py"})

#: Une chaîne qui EST un nom de fichier frère nu (`"specs.py"`), jamais une
#: chaîne-chemin (`".agents/bin/x.py"`, les gardes de `tasks_direct.py`) : le
#: basename de TOUTE chaîne rend 32 fichiers au lieu de 22 (mesuré, plan r7, C38).
_NOM_DE_FICHIER_FRERE = re.compile(r"[A-Za-z_]\w*\.py")

#: Les chargeurs PAR NOM DE MODULE (`importlib.import_module("x")`, `__import__("x")`) :
#: leur premier argument littéral désigne un frère que ni `import` ni une chaîne
#: `"x.py"` ne nomment (revue de clôture de T-00000962, T2).
_CHARGEURS_PAR_NOM = frozenset({"import_module", "__import__"})

#: La fin d'un nom de fichier CALCULÉ dans une f-string (`f"{nom}.py"`,
#: `f"{base}_x.py"`) : la clôture ne sait pas le résoudre, le banc le REFUSE.
_SUFFIXE_CALCULE = re.compile(r"\w*\.py")


def _nom_appele(f: ast.expr) -> str | None:
    """Le nom de la fonction appelée : `import_module` pour `importlib.import_module`
    comme pour `import_module` importé nu ; None pour un appel calculé."""
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)


def _freres_cites(chemin: Path) -> set[str]:
    """Les fichiers FRÈRES de `chemin` qu'il importe (import absolu), charge par nom
    de module (`importlib.import_module`, `__import__`, premier argument littéral)
    ou nomme par une chaîne qui est un nom de fichier nu ; seuls comptent ceux qui
    existent dans son dossier (un `import json` ne désigne aucun frère). Un nom de
    fichier frère CALCULÉ dans une f-string lève AssertionError : la clôture ne le
    résout pas, il s'écrit en littéral."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms: set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms |= {a.name.split(".")[0] + ".py" for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            noms.add(n.module.split(".")[0] + ".py")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and _NOM_DE_FICHIER_FRERE.fullmatch(n.value):
            noms.add(n.value)
        elif (isinstance(n, ast.Call) and _nom_appele(n.func) in _CHARGEURS_PAR_NOM and n.args
              and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
            noms.add(n.args[0].value.split(".")[0] + ".py")
        elif isinstance(n, ast.JoinedStr) and any(
                isinstance(n.values[i], ast.Constant) and isinstance(n.values[i].value, str)
                and _SUFFIXE_CALCULE.fullmatch(n.values[i].value)
                and isinstance(n.values[i - 1], ast.FormattedValue)
                for i in range(1, len(n.values))):
            raise AssertionError(f"{chemin.name}:{n.lineno} : nom de fichier frère CALCULÉ — "
                                 "la clôture ne le résout pas ; écris le nom en littéral")
    return {nom for nom in noms if (chemin.parent / nom).is_file()}


def fermeture_du_moteur(racines: list[Path], *, transitive: bool = True) -> set[Path]:
    """Les fichiers que le moteur peut charger depuis `racines`, racines comprises,
    `HORS_CLOTURE` exclu. `transitive=False` (calibration) : les racines et leurs
    frères DIRECTS seulement."""
    racines = [r.resolve() for r in racines]
    vus: set[Path] = set()
    pile = list(racines)
    while pile:
        fichier = pile.pop()
        if fichier in vus:
            continue
        vus.add(fichier)
        if transitive or fichier in racines:
            pile += [fichier.parent / nom for nom in _freres_cites(fichier) - HORS_CLOTURE]
    return vus


@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class FermetureDuMoteurTests(unittest.TestCase):
    """La wheel embarque le moteur ENTIER, rien de plus : les clés force-include
    de `pyproject.toml` sont la clôture des moteurs de `MOTEURS`, recalculée ici.

    Sans moteur lancé ni wheel bâtie : une partie oubliée ne se verrait sinon qu'à
    l'installation, chez l'adoptant, au premier verbe qui la charge (les frères
    `plan_*`, `specs`, `record_id` sont chargés PARESSEUSEMENT). Une commande
    ajoutée à `MOTEURS` (T-00000963 : ledger, specs) fait rougir l'égalité tant
    que le manifeste ne porte pas sa clôture."""

    @staticmethod
    def _manifeste() -> dict:
        """Le `pyproject.toml` du kit, chargé — SEUL site de lecture de ce banc."""
        # adopting-tree: le manifeste ne voyage pas (strip: pyproject.toml)
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    @staticmethod
    def _racines() -> list[Path]:
        return [ROOT / relatif for relatif in ca.MOTEURS.values()]

    def _cible_de_la_wheel(self) -> dict[str, str]:
        hatch = self._manifeste().get("tool", {}).get("hatch", {}).get("build", {})
        return dict(hatch.get("targets", {}).get("wheel", {}).get("force-include", {}))

    def test_les_cles_force_include_sont_la_cloture(self):
        """Égalité EXACTE : une clé manquante est un moteur cassé chez l'adoptant,
        une clé en trop un fichier embarqué que rien ne charge. Chaque clé est
        copiée sous `cadre/_moteur/<nom>` — là où `moteur` la cherche.
        MUTATIONS : une partie retirée du manifeste, ou une commande ajoutée à
        `MOTEURS` sans sa clôture → rouge."""
        forces = self._cible_de_la_wheel()
        fermee = fermeture_du_moteur(self._racines())
        attendues = {p.relative_to(ROOT).as_posix() for p in fermee}
        self.assertEqual(set(forces), attendues,
                         "les cles force-include ne sont pas la cloture du moteur")
        for source, cible in forces.items():
            with self.subTest(source=source):
                self.assertEqual(cible, f"cadre/{ca.DOSSIER_EMBARQUE}/{Path(source).name}")

    def test_le_sdist_porte_chaque_source_embarquee(self):
        """Une wheel bâtie DEPUIS le sdist (chemin par défaut de `uv build`) doit
        y trouver chaque source qu'elle force à inclure.
        MUTATION : sources retirées de `sdist.include` → rouge."""
        sdist = (self._manifeste().get("tool", {}).get("hatch", {}).get("build", {})
                 .get("targets", {}).get("sdist", {}).get("include", []))
        manquantes = sorted(set(self._cible_de_la_wheel()) - set(sdist))
        self.assertEqual(manquantes, [], "sources embarquees absentes du sdist")

    def test_la_calibration_non_transitive_oublie_un_frere(self):
        """La transitivité PORTE : sans elle, la clôture perd au moins un frère
        (mesuré le 2026-10-16 : 21 fichiers au lieu de 22, `specs.py`, chargé par
        `plan_cible` et non par `tasks.py`). Une clôture calculée à plat rendrait
        l'égalité verte sur un moteur incomplet."""
        fermee = fermeture_du_moteur(self._racines())
        directe = fermeture_du_moteur(self._racines(), transitive=False)
        self.assertTrue(directe < fermee,
                        f"la variante directe ne perd rien : {sorted(p.name for p in directe)}")

    def test_cadre_n_importe_pas_le_moteur_et_l_arbre_source_n_en_porte_pas(self):
        """Le moteur est des DONNÉES du paquet, lancées en sous-processus : aucun
        module du paquet `cadre` ne l'importe (sinon l'`exec` des parties entre dans le
        processus de `cadre`), et l'arbre source n'a pas de `_moteur/` — la wheel
        le crée, une copie posée là masquerait le kit en mode source."""
        paquet = PKG_DIR
        self.assertFalse((paquet / ca.DOSSIER_EMBARQUE).exists(),
                         f"{paquet}/_moteur existe : le mode source lancerait cette copie")
        fautifs = []
        for module in sorted(paquet.rglob("*.py")):
            for n in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Import):
                    noms = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom):  # `from cadre import _moteur` compris
                    noms = [n.module or "", *(a.name for a in n.names)]
                else:
                    continue
                if any(ca.DOSSIER_EMBARQUE in nom.split(".") for nom in noms):
                    fautifs.append(f"{module.relative_to(ROOT)}:{n.lineno}")
        self.assertEqual(fautifs, [], "un module de cadre importe le moteur embarque")


class FrontiereDuContratTests(unittest.TestCase):
    """La bascule réservé -> public appartient à T-00000797 : ici, le nom reste
    RÉSERVÉ au verrou et dans `RESERVEES` (patron de `cadre init`)."""

    def test_tasks_reste_reserve_et_n_est_pas_implementee(self):
        self.assertEqual(cli.RESERVEES.get("tasks"), "4")
        self.assertNotIn("tasks", cli.IMPLEMENTEES)

    def test_main_achemine_tasks_vers_la_delegation(self):
        vu = []
        original = ca.cadre_tasks
        ca.cadre_tasks = lambda argv, **kw: vu.append(list(argv)) or 7
        try:
            self.assertEqual(cli.main(["tasks", "--", "list", "-x"]), 7)
        finally:
            ca.cadre_tasks = original
        self.assertEqual(vu, [["--", "list", "-x"]], "les arguments doivent passer verbatim")


if __name__ == "__main__":
    unittest.main()
