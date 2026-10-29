#!/usr/bin/env python3
"""T-00000962 (BK-157) — `cadre tasks` depuis la WHEEL installée : le moteur embarqué.

POURQUOI CE BANC. `test_cadre_cmd_tasks.py` délègue par `python -m cadre.cli`
avec `PYTHONPATH=src` : le moteur lancé y est TOUJOURS celui de l'arbre source
du kit. Chez un adoptant, `cadre` vient d'une wheel installée hors de toute
source, et le moteur lancé est la copie que la wheel embarque sous
`cadre/_moteur/` (force-include de `pyproject.toml`). Rien d'autre ne le
mesure : une partie oubliée, un frère chargé ailleurs qu'à côté du moteur, ou
un canal qui viserait le projet ne se verraient qu'à l'installation, chez
quelqu'un d'autre.

CE QU'IL MESURE (`MoteurEmbarqueTests`) — une wheel bâtie depuis CET arbre
(`batir_wheel`), installée dans un venv JETABLE (`installer_et_sonder`), puis
un projet neuf hors dépôt (`git init` + `<venv>/cadre init`) :
  (a) `cadre tasks list|new|start|done --raison` depuis un SOUS-DOSSIER du
      projet, code 0 ×4, board né sous la racine du projet ;
  (b) le projet ne porte ni `.py` ni `.agents/bin` ;
  (c) `<purelib>/cadre/_moteur` inchangé (hors `__pycache__`) ;
  (d) une wheel amputée de `cadre/_moteur/tasks.py` sort en 2 en nommant le
      chemin cherché, sans traceback ;
  (e) les frères chargés PARESSEUSEMENT (`plan_cible`, `plan_depends`,
      `plan_lots`, `specs`, `record_id`, `tracabilite_jira`, `etat_lecture`,
      `ledger`, `task_chrono`) le sont sous `<purelib>/cadre/_moteur`, chaque frère
      sondé étant au force-include du manifeste,
      par les chargeurs du moteur lui-même, et `parents[2]` du moteur embarqué
      vaut `<purelib>` — calibré par une wheel amputée de `specs.py` ;
  (f) CANARI ÉVÉNEMENTS : un `events.py` témoin posé dans le PROJET n'est
      jamais exécuté, outbox portée au-delà du seuil (200) par 205 vrais
      `new` dans un seul processus puis un verbe sous `AGENTS_EVENTS_DIR`
      jetable ; stderr « agentic_v3 absent de <purelib> » ; contrôle positif :
      le même témoin posé sous `<purelib>/.agents/bin/` EST exécuté ;
  (g) CANARI COMMIT : `commit-stores` et `commit-run-exports` lancent le
      `post-task-done-index.sh` du PROJET avec `--commit-section <racine>`
      (`run-exports` en plus pour le second) et relaient sa DERNIÈRE ligne ;
      script retiré : `failed`, code 0 (décision pilote S-01M51E99DY03JJB6XZFK2JF57K) ;
  (h) CANARI MOTEUR : un `<projet>/.agents/bin/tasks.py` piégé (il écrit un
      témoin s'il est exécuté) n'est JAMAIS lancé par `cadre tasks list`.

L'ENVIRONNEMENT des commandes `cadre` : la liste blanche de
`test_cadre_cli_installed.py` (`env_uv`) — ni `PYTHONPATH`, ni `CADRE_*`, ni
`GIT_*`, ni `AGENTS_*` hérités —, plus `HOME`, `CADRE_STATE_DIR` et
`CADRE_CONFIG_HOME` jetables, `GIT_CEILING_DIRECTORIES` à la racine jetable et
git sans configuration globale ni système. Le BUILD garde le `HOME` réel : c'est
lui qui mène uv à son cache chaud (`batir_wheel`).

SAUTS ANNONCÉS, ceux du banc frère `test_cadre_pkg_root.py` : uv absent, projet
adoptant (marqueur `.agents/IS_THE_KIT` absent — ce banc VOYAGE et y saute),
puis au build cache uv non inscriptible, backend non résolvable, délai dépassé.
En plus, (g) seul : aucun bash utilisable (absent, ou relais WSL de System32,
que le moteur refuse aussi). git absent : ERREUR, jamais un saut. COUVERTURE :
un poste au cache uv chaud ; la CI n'installe pas uv et y SAUTE.

CE QU'IL NE MESURE PAS : le miroir V3 — `agentic_v3` n'est pas dans la wheel ;
la tâche qui l'y fait entrer est T-00000887, et le jour où il est posé sous
`<purelib>`, (f) rougit, ce qui est voulu ;
le régime armé de l'adoptant (aucune garde semée par `cadre init`) ; Windows ;
une installation depuis un index (`--offline`).
"""

from __future__ import annotations

import hashlib
import json
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

# IMPORTÉS TELS QUELS — des noms seuls, jamais une classe de test :
# `python_classes = *Tests` la ferait collecter une seconde fois ici.
from test_cadre_cli_installed import DELAI_CLI, EST_LE_KIT, SAUT_ADOPTANT  # noqa: E402
from test_cadre_pkg_root import (  # noqa: E402
    amputer,
    batir_wheel,
    env_uv,
    installer_et_sonder,
)

UV = shutil.which("uv")
GIT = shutil.which("git")
BASH = shutil.which("bash")

SAUT_UV = ("SAUT ANNONCE : `uv` absent du PATH, la wheel ne peut pas etre batie "
           "ici — `cadre tasks` depuis le moteur embarque n'est PAS mesure par "
           "cette execution")
SAUT_BASH = ("SAUT ANNONCE : aucun bash utilisable (absent, ou relais WSL de "
             "System32) — le relais de post-task-done-index.sh par commit-stores "
             "n'est PAS mesure par cette execution")
SANS_GIT = ("git absent du PATH : un projet adoptant est un `git init` reel — "
            "ECHEC, jamais un saut")

#: Le moteur dans la wheel, relatif au site-packages (force-include de `pyproject.toml`).
MOTEUR_DANS_LA_WHEEL = ("cadre", "_moteur")

ID_TACHE = re.compile(r"\bT-[0-9A-Z]{8,26}\b")


def freres_paresseux() -> tuple[str, ...]:
    """Les frères que le moteur charge PARESSEUSEMENT, au premier verbe qui en a
    besoin : chaque source force-include du manifeste qui n'est pas une partie
    `tasks*` (au relevé : `agent_chrono`, `plan_cible`, `plan_depends`, `plan_lots`,
    `record_id`, `specs`, `vendor_paths` — ce dernier chargé, lui, dès la façade ;
    `tracabilite_jira`, `etat_lecture`, `ledger` après intégration Jira). DÉRIVÉE du manifeste (revue de clôture de T-00000962, T8) : un frère
    ajouté à la wheel sans chargeur dans `SONDE_FRERES` rougit (e) en « absent ».
    Lue à l'APPEL, jamais à l'import : `defauts_du_moteur` ne sert que derrière
    `EST_LE_KIT`."""
    # adopting-tree: le manifeste ne voyage pas (strip: pyproject.toml) ; lu derrière
    # EST_LE_KIT seulement (MoteurEmbarqueTests), jamais à l'import du banc.
    manifeste = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    forces = manifeste["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    return tuple(sorted(Path(k).stem for k in forces if not Path(k).name.startswith("tasks")))


#: Le seuil de l'outbox de synchronisation (`tasks_deversement._SYNC_OUTBOX_SEUIL`)
#: et le nombre de verbes qui le dépassent dans (f).
SEUIL_OUTBOX = 200
VERBES_AU_DELA = SEUIL_OUTBOX + 5

_CONFIG_GIT = ("-c", "user.name=banc", "-c", "user.email=banc@exemple.invalid",
               "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}",
               "-c", "init.defaultBranch=main")

#: (e) LA SONDE, jouée par l'interpréteur du venv sous `-I`, moteur embarqué en
#: tête de `sys.path` comme quand il est lancé en script. Elle RAPPORTE le
#: `__file__` de chaque frère tel que LES CHARGEURS DU MOTEUR le rendent
#: (`plan_cible_module`, `plan_depends_module`, l'`import plan_lots` de
#: `tasks_fournee`, `_specs_module` de `plan_cible`, `record_id_module`,
#: `agent_chrono_module` de `specs`, `task_chrono_module` de la façade, le résolveur `_RESOLVEUR_V3` que
#: `tasks_sync` charge au chargement de la façade — `None` s'il est absent ou
#: incomplet), `null`
#: quand le chargeur échoue ; le verdict est rendu ici par `defauts_du_moteur`.
SONDE_FRERES = """\
import json, sys, sysconfig
from pathlib import Path
moteur = Path(sys.argv[1])
sys.path.insert(0, str(moteur))
import tasks
rapport = {"purelib": sysconfig.get_paths()["purelib"],
           "parents2": str(Path(tasks.__file__).resolve().parents[2]),
           "modules": {}, "erreurs": {}}
def charge(nom, chargeur):
    try:
        rapport["modules"][nom] = getattr(chargeur(), "__file__", None)
    except Exception as exc:
        rapport["modules"][nom] = None
        rapport["erreurs"][nom] = type(exc).__name__ + ": " + str(exc)
charge("plan_cible", tasks.plan_cible_module)
charge("plan_depends", tasks.plan_depends_module)
charge("plan_lots", lambda: __import__("plan_lots"))
charge("specs", lambda: tasks.plan_cible_module()._specs_module())
charge("record_id", tasks.record_id_module)
charge("agent_chrono", lambda: tasks.plan_cible_module()._specs_module().agent_chrono_module())
charge("vendor_paths", lambda: tasks._RESOLVEUR_V3)
charge("tracabilite_jira", tasks._jira_transport)
charge("etat_lecture", lambda: __import__("etat_lecture"))
charge("ledger", lambda: __import__("etat_lecture")._proprietaire("ledger"))
charge("task_chrono", tasks.task_chrono_module)
print(json.dumps(rapport))
"""

#: (f) N VRAIS verbes mutants (`new`) dans UN processus : `main(argv)` du moteur
#: embarqué, bouclée — 205 sous-processus `cadre` coûteraient des minutes.
BOUCLE_DE_VERBES = """\
import contextlib, io, json, sys
moteur, racine, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, moteur)
import tasks
codes = []
for i in range(n):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        codes.append(tasks.main(["--root", racine, "new", "boucle %d" % i]))
print(json.dumps({"n": len(codes), "codes": sorted(set(codes))}))
"""

#: (f) Le témoin : un `events.py` qui, s'il est EXÉCUTÉ, écrit son fichier.
CANARI_EVENEMENTS = ("import pathlib\n"
                     "pathlib.Path({temoin!r}).write_text('execute', encoding='utf-8')\n\n\n"
                     "def emit(*args, **kwargs):\n"
                     "    return None\n")

#: (h) Le `tasks.py` piégé du projet : MUET (sa sortie ne peut pas passer pour
#: celle du moteur), il n'écrit que son témoin s'il est EXÉCUTÉ.
CANARI_MOTEUR = ("import pathlib\n"
                 "pathlib.Path({temoin!r}).write_text('execute', encoding='utf-8')\n")

#: (g) Le `post-task-done-index.sh` témoin : ses arguments vont au journal nommé
#: par la VARIABLE `CANARI_PTDI_JOURNAL` (aucune valeur interpolée dans le
#: script), puis une ligne de bruit, puis la dernière ligne, qui compte ses
#: arguments — 2 pour `commit-stores`, 3 pour `commit-run-exports`.
CANARI_PTDI = ('#!/usr/bin/env bash\n'
               'printf \'%s\\n\' "$*" >> "$CANARI_PTDI_JOURNAL"\n'
               'echo "ligne de bruit"\n'
               'echo "CANARI-PTDI-$#"\n')


def _executable_du_venv(venv: Path, nom: str) -> Path:
    """`<venv>/bin/<nom>`, ou `<venv>/Scripts/<nom>.exe` sous Windows."""
    windows = venv / "Scripts" / f"{nom}.exe"
    return windows if windows.is_file() else venv / "bin" / nom


def _empreintes(dossier: Path) -> dict[str, str]:
    """`{chemin relatif: sha256}` des fichiers de `dossier`, `__pycache__` exclu."""
    return {p.relative_to(dossier).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(dossier.rglob("*"))
            if p.is_file() and "__pycache__" not in p.relative_to(dossier).parts}


def defauts_du_moteur(rapport: dict) -> list[str]:
    """Le VERDICT de (e) : un défaut par frère absent ou chargé hors de
    `<purelib>/cadre/_moteur`, et un si `parents[2]` du moteur n'est pas
    `<purelib>`. Liste vide = vert ; une sonde amputée rougit, elle ne passe pas.
    Un frère SONDÉ que le manifeste n'embarque pas (`task_chrono` avant son force-include,
    T-01M5HST80E30DFMV3S7WM68Q7N) est un défaut aussi : le moteur le chargerait, la wheel ne l'a pas."""
    purelib = Path(rapport.get("purelib") or "/nulle-part").resolve()
    attendu = purelib.joinpath(*MOTEUR_DANS_LA_WHEEL)
    freres = freres_paresseux()
    trouves = [f"{nom}: sondé, absent du force-include du manifeste"
               for nom in sorted(rapport.get("modules", {})) if nom not in freres]
    for nom in freres:
        vu = rapport.get("modules", {}).get(nom)
        if vu is None:
            trouves.append(f"{nom}: absent")
        elif Path(vu).resolve() != attendu / f"{nom}.py":
            trouves.append(f"{nom}: charge hors de {attendu} ({vu})")
    if Path(rapport.get("parents2") or "/nulle-part").resolve() != purelib:
        trouves.append(f"parents[2] du moteur != purelib ({rapport.get('parents2')})")
    return trouves


@unittest.skipIf(UV is None, SAUT_UV)
@unittest.skipUnless(EST_LE_KIT, SAUT_ADOPTANT)
class MoteurEmbarqueTests(unittest.TestCase):
    """`cadre tasks` servi par le moteur que la wheel embarque, dans un venv jetable."""

    @classmethod
    def setUpClass(cls):
        if GIT is None:
            raise AssertionError(SANS_GIT)
        cls.base = Path(tempfile.mkdtemp(prefix="t962w-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.base, ignore_errors=True)
        if cls.base.is_relative_to(ROOT):
            raise AssertionError(f"TMPDIR est sous le depot ({cls.base}) : « hors de "
                                 "toute source » ne discriminerait plus")
        cls.roue = batir_wheel(cls.base / "wheel")
        cls.venv, cls.purelib = cls._installer(cls.roue, cls.base / "venv")
        cls.moteur = cls.purelib.joinpath(*MOTEUR_DANS_LA_WHEEL)

    @staticmethod
    def _installer(roue: Path, venv: Path) -> tuple[Path, Path]:
        rapport = installer_et_sonder(roue, venv, [])
        return venv, Path(rapport["purelib"]).resolve()

    def setUp(self):
        self.ici = Path(tempfile.mkdtemp(prefix="cas-", dir=self.base))
        (self.ici / "home").mkdir()

    def _env(self, **en_plus: str) -> dict[str, str]:
        env = env_uv() | {
            "HOME": str(self.ici / "home"),
            "CADRE_STATE_DIR": str(self.ici / "etat"),
            "CADRE_CONFIG_HOME": str(self.ici / "conf"),
            "GIT_CEILING_DIRECTORIES": str(self.base),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        return env | en_plus

    def _lancer(self, argv: list[str], cwd: Path, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(argv, cwd=str(cwd), env=self._env(**env), capture_output=True,
                              encoding="utf-8", errors="replace", timeout=DELAI_CLI,
                              check=False)

    def _cadre(self, cwd: Path, *args: str, venv: Path | None = None,
               **env: str) -> subprocess.CompletedProcess:
        binaire = _executable_du_venv(venv or self.venv, "cadre")
        return self._lancer([str(binaire), *args], cwd, **env)

    def _projet(self, nom: str = "projet") -> Path:
        """`git init` puis `cadre init` (celui de la wheel), hors de tout dépôt."""
        projet = self.ici / nom
        projet.mkdir()
        r = self._lancer([GIT, *_CONFIG_GIT, "init", "-q"], projet)
        self.assertEqual(r.returncode, 0, r.stderr)
        # L'identité du projet jetable, PERSISTÉE : `-c` ne vaut que pour `init`, et sans auteur
        # `start` n'écrit aucun `start_actor` (doctrine S-01M5HH8QMC : un auteur inconnu ne possède rien).
        for cle, valeur in (("user.name", "banc"), ("user.email", "banc@exemple.invalid")):
            r = self._lancer([GIT, "config", cle, valeur], projet)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = self._cadre(projet, "init")
        self.assertEqual(r.returncode, 0, f"cadre init : {r.stdout}{r.stderr}")
        return projet

    def _amputee(self, membre: str) -> tuple[Path, Path]:
        """Venv jetable d'une copie de la wheel SANS `membre` (ni sa ligne de RECORD)."""
        nom = Path(membre).stem
        roue = self.ici / f"sans-{nom}" / self.roue.name
        amputer(self.roue, roue, membre)
        return self._installer(roue, self.ici / f"venv-sans-{nom}")

    # -- (a) (b) (c) ----------------------------------------------------------

    def test_a_list_new_start_done_depuis_un_sous_dossier_du_projet(self):
        """(a) code 0 ×4 depuis un sous-dossier, board sous la racine ; (b) ni `.py`
        ni `.agents/bin` au projet ; (c) le moteur installé n'est pas modifié.
        MUTATION : force-include retiré du manifeste → aucun moteur → rouge."""
        projet = self._projet()
        sous = projet / "sous" / "rep"
        sous.mkdir(parents=True)
        avant = _empreintes(self.moteur)
        self.assertIn("tasks.py", avant, f"aucun moteur embarque sous {self.moteur}")

        r = self._cadre(sous, "tasks", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("TASK BOARD", r.stdout)
        r = self._cadre(sous, "tasks", "new", "sonde T-962 : moteur embarque")
        self.assertEqual(r.returncode, 0, r.stderr)
        trouve = ID_TACHE.search(r.stdout)
        self.assertIsNotNone(trouve, f"aucun identifiant dans la sortie de new : {r.stdout!r}")
        tid = trouve.group(0)
        r = self._cadre(sous, "tasks", "start", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        # T-01M5DBFK3XKKM2VHQM5RE4TP6K : sans V3 dans la wheel, la copie est le tirage de repli (16 hex).
        # MUTATIONS : V3 rendu obligatoire, ou jeton non conforme → rouge.
        vue = self._cadre(sous, "tasks", "list", "--task", tid, "--json")
        self.assertEqual(vue.returncode, 0, vue.stderr)
        copie = (json.loads(vue.stdout)[0].get("start_actor") or {}).get("copie") or ""
        self.assertRegex(copie, r"\A[0-9a-f]{16}\Z", r.stderr)
        r = self._cadre(sous, "tasks", "done", tid, "--raison", "banc T-962 wheel")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._cadre(sous, "tasks", "list", "--task", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"state\s*:\s*\S*\s*done")

        self.assertTrue((projet / ".agents" / "state" / "board").is_dir(),
                        "le board n'est pas sous la racine du projet")
        self.assertFalse((projet / "sous" / ".agents").exists(),
                         "le board est ne sous le repertoire courant : `--root` n'a pas ete passe")
        self.assertFalse((projet / ".agents" / "bin").exists(), "un .agents/bin chez l'adoptant")
        py = [str(p.relative_to(projet)) for p in projet.rglob("*.py")
              if ".git" not in p.relative_to(projet).parts]
        self.assertEqual(py, [], "un .py est apparu chez l'adoptant")
        self.assertEqual(_empreintes(self.moteur), avant, "le moteur installe a ete modifie")

    # -- (d) ------------------------------------------------------------------

    def test_d_une_wheel_sans_moteur_sort_en_2_en_nommant_le_chemin(self):
        """Wheel amputée de `cadre/_moteur/tasks.py` : refus en 2 qui nomme le
        chemin embarqué cherché, rien sur stdout, aucune trace."""
        venv, purelib = self._amputee("/".join((*MOTEUR_DANS_LA_WHEEL, "tasks.py")))
        projet = self._projet()
        r = self._cadre(projet, "tasks", "list", venv=venv)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn(str(purelib.joinpath(*MOTEUR_DANS_LA_WHEEL, "tasks.py")), r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # -- (e) ------------------------------------------------------------------

    def _sonder(self, venv: Path, moteur: Path) -> dict:
        dehors = self.ici / "dehors"
        dehors.mkdir(exist_ok=True)
        r = self._lancer([str(_executable_du_venv(venv, "python")), "-I", "-c", SONDE_FRERES,
                          str(moteur)], dehors)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_e_les_freres_paresseux_se_chargent_depuis_le_paquet_installe(self):
        """Chaque frère chargé par les chargeurs du moteur l'est sous
        `<purelib>/cadre/_moteur`, et `parents[2]` du moteur vaut `<purelib>`.
        CALIBRATION : wheel amputée de `agent_chrono.py`, frère FEUILLE (aucun autre
        ne le charge ; amputer `specs.py` emporterait aussi `agent_chrono`, chargé
        par lui) → le verdict nomme `agent_chrono`, seul.
        MUTATION : `specs.py` retiré du moteur → rouge ; après intégration Jira,
        `tracabilite_jira.py` retiré → frère absent, même si son fichier voyage."""
        rapport = self._sonder(self.venv, self.moteur)
        self.assertEqual(defauts_du_moteur(rapport), [], rapport.get("erreurs"))
        venv, purelib = self._amputee("/".join((*MOTEUR_DANS_LA_WHEEL, "agent_chrono.py")))
        ampute = self._sonder(venv, purelib.joinpath(*MOTEUR_DANS_LA_WHEEL))
        self.assertEqual(defauts_du_moteur(ampute), ["agent_chrono: absent"],
                         "calibration : la sonde ne voit pas un frere manquant")

    # -- (f) ------------------------------------------------------------------

    def test_f_l_events_py_du_projet_n_est_jamais_execute(self):
        """L'outbox franchit le seuil, le déversement signale une dégradation sous
        `AGENTS_EVENTS_DIR` : le moteur charge `events.py` sous `parents[2]`, le
        site-packages — celui du projet n'est JAMAIS exécuté. Contrôle positif :
        posé sous `<purelib>/.agents/bin/`, le même témoin l'est.
        MUTATION : `repository_root` = racine du projet dans le moteur → rouge."""
        projet = self._projet()
        temoin_projet = self.ici / "temoin-projet"
        canari = projet / ".agents" / "bin" / "events.py"
        canari.parent.mkdir(parents=True)
        canari.write_text(CANARI_EVENEMENTS.format(temoin=str(temoin_projet)), encoding="utf-8")

        python = _executable_du_venv(self.venv, "python")
        r = self._lancer([str(python), "-I", "-c", BOUCLE_DE_VERBES, str(self.moteur),
                          str(projet), str(VERBES_AU_DELA)], projet)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"n": VERBES_AU_DELA, "codes": [0]}, r.stderr)

        evenements = self.ici / "evenements"
        r = self._cadre(projet, "tasks", "new", "negatif", AGENTS_EVENTS_DIR=str(evenements))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"agentic_v3 absent de {self.purelib}", r.stderr,
                      "le deversement au-dela du seuil n'a pas eu lieu : le canal n'est pas exerce")
        self.assertFalse(temoin_projet.exists(), "l'events.py du PROJET a ete execute")

        temoin_purelib = self.ici / "temoin-purelib"
        positif = self.purelib / ".agents" / "bin" / "events.py"
        positif.parent.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.purelib / ".agents", ignore_errors=True)
        positif.write_text(CANARI_EVENEMENTS.format(temoin=str(temoin_purelib)), encoding="utf-8")
        r = self._cadre(projet, "tasks", "new", "positif", AGENTS_EVENTS_DIR=str(evenements))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(temoin_purelib.exists(),
                        "controle positif : l'events.py sous <purelib> n'est pas execute — "
                        "le temoin du projet ne prouverait rien")
        self.assertFalse(temoin_projet.exists(), "l'events.py du PROJET a ete execute")

    # -- (g) ------------------------------------------------------------------

    def test_g_commit_stores_relaie_la_derniere_ligne_du_script_du_projet(self):
        """Option 1 (S-01M51E99DY03JJB6XZFK2JF57K) : les deux verbes lancent le
        `post-task-done-index.sh` du PROJET et en relaient la dernière ligne ;
        script retiré : `failed`, code 0.
        MUTATION : repli `failed` changé, ou canari muet → rouge."""
        if BASH is None or "system32" in BASH.replace("\\", "/").lower():
            self.skipTest(SAUT_BASH)
        projet = self._projet()
        journal = self.ici / "ptdi-arguments"
        script = projet / ".agents" / "bin" / "post-task-done-index.sh"
        script.parent.mkdir(parents=True)
        script.write_bytes(CANARI_PTDI.encode("utf-8"))

        r = self._cadre(projet, "tasks", "commit-stores", CANARI_PTDI_JOURNAL=str(journal))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1:], ["CANARI-PTDI-2"], r.stdout)
        r = self._cadre(projet, "tasks", "commit-run-exports", CANARI_PTDI_JOURNAL=str(journal))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1:], ["CANARI-PTDI-3"], r.stdout)
        self.assertEqual(journal.read_text(encoding="utf-8").splitlines(),
                         [f"--commit-section {projet}", f"--commit-section {projet} run-exports"])

        script.unlink()
        r = self._cadre(projet, "tasks", "commit-stores", CANARI_PTDI_JOURNAL=str(journal))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1:], ["failed"], r.stdout)

    # -- (h) ------------------------------------------------------------------

    def test_h_le_tasks_py_du_projet_n_est_jamais_execute(self):
        """Le moteur lancé est celui de la wheel : un `tasks.py` piégé posé dans
        le projet n'écrit jamais son témoin, et le board répond quand même.
        MUTATION : `moteur` qui préfère le `tasks.py` du projet → rouge."""
        projet = self._projet()
        temoin = self.ici / "temoin-tasks-projet"
        piege = projet / ".agents" / "bin" / "tasks.py"
        piege.parent.mkdir(parents=True)
        piege.write_text(CANARI_MOTEUR.format(temoin=str(temoin)), encoding="utf-8")
        r = self._cadre(projet, "tasks", "list")
        self.assertFalse(temoin.exists(), "le tasks.py du PROJET a ete execute")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("TASK BOARD", r.stdout)


if __name__ == "__main__":
    unittest.main()
