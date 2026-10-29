"""test_vendor_bridge.py — témoin de la phase B de T-01M5BXTGX5YN8XEXTG1PP7A5ZX.

Les outils du board trouvent `agentic_v3` et `cadre` par le RÉSOLVEUR
`vendor_paths.py`, plus par des chemins en dur. Arbres JETABLES (copie des
fichiers de `.agents/bin`, jamais un lien : `Path(__file__).resolve()` suivrait
un lien jusqu'au dépôt), faux paquet `agentic_v3` dont le `BoardBridge` écrit
sa provenance (`<origine du paquet>/<origine du module du pont>`) dans un
fichier témoin. CLI en SOUS-PROCESSUS ; le `sys.path` et `sys.modules` du
processus pytest ne sont touchés que sous `mock.patch`.

CE QUE CE BANC TIENT :
  B1  ancien seul   `agentic_v3/`                  → pont « ancien/ancien » ;
  B2  neuf seul     `.agents/vendor/agentic_v3`    → pont « vendor/vendor » ;
  B3  les deux      → « vendor/vendor » ;
  B4  les deux, RACINE SUR `sys.path` (`PYTHONPATH`, devant la bibliothèque
      standard — la place du rootdir pytest ; réserve C10) → « vendor/vendor »
      EXACTEMENT (chargement par chemin exact), jamais l'ancien ni un refus ;
  B5  V3 absent des deux lieux → aucun pont, rc 0, l'intent RESTE dans l'outbox ;
  B6  résolveur absent (copie partielle de `.agents/bin`) → aucun pont, même
      si l'ancien `agentic_v3/` existe ; l'outbox est gardée ;
  B6bis résolveur VIDE, PARTIEL (un nom de son API manque), TRONQUÉ en
      pleine instruction (`SyntaxError`) ou qui LÈVE à l'exécution
      (`RuntimeError` en tête) = ABSENT : `new` et `list` rendent 0
      sans trace, aucun pont, outbox gardée, la ligne de déversement nomme les
      manques ou « illisible » ; côté `cadre`, repli `src/cadre` ;
  B7  EN PROCESSUS, `agentic_v3` DÉJÀ importé (réserve C15) : sous pytest, le
      conftest racine et les bancs importent `agentic_v3` par `sys.path`, où le
      rootdir précède tout — dans un arbre « les deux », c'est l'ANCIEN qui est
      en cache. Comportement DIT : le pont est REFUSÉ par `ProvenanceRefusee`
      (annonce `TASKS: pont V3 REFUSÉ (ProvenanceRefusee …)`), aucun module du
      pont n'est exécuté, le verbe rend 0 et son intent reste dans l'outbox ;
      `replay-sync` rend 1 sur la même annonce ;
  B8  EN PROCESSUS, le paquet du kit lui-même (même arbre) : ACCEPTÉ — le pont
      rendu vient du dossier que le résolveur désigne, et le parent du paquet
      est placé sur `sys.path` par l'API (`amorcer_cli`), une fois, jamais en
      tête ; `None` dans `sys.modules` (paquet masqué) = ABSENT, jamais refusé ;
  B9  au déversement sans pont, la ligne DIT la cause quand ce n'est pas le
      cas nominal, sous `TASKS: agentic_v3 non chargé dans` : résolveur absent,
      paquet incomplet (sans cause, `absent de`, sa forme d'avant, tenue par
      `test_tasks_sync_sans_v3.py` S3) ;
  B10 EN PROCESSUS, l'`__init__` du vendor lève → rc 0, intent gardé, et
      `agentic_v3` n'est PAS laissé à moitié chargé dans `sys.modules` ;
  C1  `cadre` : `record_id._IDS_PATH`, `event_store._SRC_CADRE`,
      `migrate_index_to_db._CHEMIN_CADRE_PATHS` / `_SRC_CADRE` suivent le
      résolveur — neuf seul et les deux → `.agents/vendor/cadre`, ancien seul
      → `src/cadre` ; et `new` alloue un id avec le générateur du vendor seul ;
  F1  résolveur illisible (tronqué, qui lève) : trois lignes stderr préfixées, une par producteur ;
      incomplet (vide, partiel) : zéro ;
  F2  copie étrangère inscrite, résolveur attendu qui lève : la copie d'avant est rendue ;
  F3  copie étrangère inscrite sous `_cadre_vendor_paths_bin` : aucun des trois producteurs ne la croit.

MUTANTS (rejoués à la main, voir le rapport de la phase B) : sans chargement
exact ni `verifier_charge` → B4 et B7 rouges ; sans `verifier_charge` → B7
rouge ; présence testée sur l'ancien lieu seul → B2 rouge ; outbox acquittée
sans pont → B5 rouge ; garde du résolveur absent retirée → B6 rouge ; cause
retirée de la ligne → B9 rouge ; `amorcer_cli` retiré, ou garde du paquet
masqué retirée → B8 rouge ; `_dossier_cadre` réduit à `src/cadre` → C1 rouge ;
import par `sys.path` rattrapé par `verifier_charge` → B4 rouge ; contrôle
d'API ou `try` du résolveur illisible retiré d'un des quatre producteurs →
B6bis rouge ; `except Exception` réduit à `except SyntaxError` autour du
chargement du résolveur → B6bis « leve » rouge ; parent placé par `append` → B8 rouge ; `pop` du paquet
retiré quand son `__init__` lève → B10 rouge.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _resolveur_du_depot():
    spec = importlib.util.spec_from_file_location("vendor_paths_banc_bridge", HERE / "vendor_paths.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Les sources de `cadre` copiées dans les arbres jetables : là où le résolveur du dépôt les trouve (le banc suit
#: un déplacement vers `.agents/vendor/cadre`) ; `src/cadre` sur une base sans résolveur (transplantation).
SOURCE_CADRE = (_resolveur_du_depot().dossier_paquet(REPO, "cadre") if (HERE / "vendor_paths.py").is_file()
                else None) or REPO / "src" / "cadre"

#: La clôture de `tasks.py` (pyproject, force-include) plus `events.py`, `kickoff_guard.py` et le résolveur.
COPIES = ("tasks*.py", "events.py", "record_id.py", "vendor_paths.py", "plan_cible.py", "plan_depends.py",
          "plan_trace.py", "plan_lots.py", "specs.py", "kickoff_guard.py", "agent_chrono.py")
#: Les producteurs dont le repli PAR CHEMIN vers `cadre` suit le résolveur (C1).
COPIES_CADRE = ("event_store.py", "events.py", "otel_receiver.py", "migrate_index_to_db.py", "build_index.py",
                "record_id.py", "vendor_paths.py")

PONT = (
    "import os\n"
    "from pathlib import Path\n"
    "from agentic_v3 import ORIGINE\n"
    "ORIGINE_PONT = {origine!r}\n"
    "\n"
    "\n"
    "class BoardBridge:\n"
    "    def __init__(self, project_root=None, **_):\n"
    "        with Path(os.environ['BANC_V3_TEMOIN']).open('a', encoding='utf-8') as f:\n"
    "            f.write(ORIGINE + '/' + ORIGINE_PONT + '\\n')\n"
    "\n"
    "    def consume_board_intent(self, intent):\n"
    "        return True\n"
)

#: Sonde : la taille de l'outbox du projet argv[2], lue par le `tasks.py` argv[1].
OUTBOX = "\n".join((
    "import importlib.util, sys",
    "spec = importlib.util.spec_from_file_location('tasks_sonde_outbox', sys.argv[1])",
    "module = importlib.util.module_from_spec(spec)",
    "sys.modules[spec.name] = module",
    "spec.loader.exec_module(module)",
    "print(len(module.load(sys.argv[2])['sync_outbox']))",
))

#: Sonde : les chemins du repli `cadre` des trois producteurs du dossier argv[1].
CADRE = "\n".join((
    "import importlib.util, json, sys",
    "from pathlib import Path",
    "def charger(nom, fichier):",
    "    spec = importlib.util.spec_from_file_location(nom, Path(sys.argv[1]) / fichier)",
    "    module = importlib.util.module_from_spec(spec)",
    "    sys.modules[spec.name] = module",
    "    spec.loader.exec_module(module)",
    "    return module",
    "r = charger('sonde_record_id', 'record_id.py')",
    "e = charger('sonde_event_store', 'event_store.py')",
    "m = charger('sonde_migrate', 'migrate_index_to_db.py')",
    "print(json.dumps({'ids': str(r._IDS_PATH), 'store': str(e._SRC_CADRE),",
    "                  'paths': str(m._CHEMIN_CADRE_PATHS), 'index': str(m._SRC_CADRE)}))",
))

#: Les producteurs qui DISENT un résolveur illisible (S-01M5CAG0HC), préfixe de leur ligne stderr.
DISENT = ("record_id", "event_store", "migrate_index_to_db")

#: Sonde : une copie ÉTRANGÈRE du résolveur (fichier argv[3], API complète, `dossier_paquet` vers argv[3]) DÉJÀ
#: inscrite sous le nom partagé, puis le producteur argv[2] du dossier argv[1] ; rend son dossier `cadre`
#: (attribut argv[4]) et si la copie étrangère est toujours celle de `sys.modules`.
ETRANGERE = "\n".join((
    "import importlib.util, json, sys, types",
    "from pathlib import Path",
    "etr = types.ModuleType('_cadre_vendor_paths_bin')",
    "etr.__file__ = str(Path(sys.argv[3]) / 'vendor_paths.py')",
    "for nom in ('resoudre', 'exiger', 'amorcer_cli', 'verifier_charge', 'ProvenanceRefusee'):",
    "    setattr(etr, nom, None)",
    "etr.dossier_paquet = lambda racine, paquet: Path(sys.argv[3]) / paquet",
    "sys.modules['_cadre_vendor_paths_bin'] = etr",
    "spec = importlib.util.spec_from_file_location('sonde_producteur', Path(sys.argv[1]) / sys.argv[2])",
    "module = importlib.util.module_from_spec(spec)",
    "sys.modules[spec.name] = module",
    "spec.loader.exec_module(module)",
    "print(json.dumps({'dossier': str(getattr(module, sys.argv[4])),",
    "                  'etrangere': sys.modules.get('_cadre_vendor_paths_bin') is etr}))",
))


def _faux_v3(dossier: Path, origine: str) -> Path:
    (dossier / "reconciliation").mkdir(parents=True)
    (dossier / "__init__.py").write_text(f"ORIGINE = {origine!r}\n", encoding="utf-8")
    (dossier / "reconciliation" / "__init__.py").write_text("", encoding="utf-8")
    (dossier / "reconciliation" / "board_bridge.py").write_text(PONT.format(origine=origine), encoding="utf-8")
    return dossier


def _cadre(dossier: Path) -> Path:
    """Un paquet `cadre` minimal : `__init__.py` (le résolveur l'exige), `paths.py`, et le générateur d'ids."""
    (dossier / "ledger").mkdir(parents=True)
    (dossier / "__init__.py").write_text("", encoding="utf-8")
    (dossier / "ledger" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(SOURCE_CADRE / "ledger" / "ids.py", dossier / "ledger" / "ids.py")
    shutil.copy2(SOURCE_CADRE / "paths.py", dossier / "paths.py")
    return dossier


#: L'API du résolveur que les quatre producteurs exigent, dans l'ordre où leur cause la nomme.
API_RESOLVEUR = ("resoudre", "exiger", "dossier_paquet", "amorcer_cli", "verifier_charge", "ProvenanceRefusee")


def _amputer_resolveur(kit: Path, variante: str) -> None:
    """`vide` : `vendor_paths.py` sans contenu ; `partiel` : `verifier_charge` renommé (le reste de l'API tient) ;
    `tronque` : coupé en pleine instruction, dans la signature de `verifier_charge` (`SyntaxError` à l'exécution) ;
    `leve` : intact, mais une `RuntimeError` levée en tête, juste APRÈS `from __future__ …` (posée avant, elle
    rendrait une `SyntaxError` de compilation : l'import `__future__` doit ouvrir le fichier — mesuré)."""
    resolveur = kit / ".agents" / "bin" / "vendor_paths.py"
    if variante == "vide":
        resolveur.write_text("", encoding="utf-8")
        return
    texte = resolveur.read_text(encoding="utf-8")
    if variante == "leve":
        futur = "from __future__ import annotations\n"
        assert texte.count(futur) == 1, "ancre du résolveur qui lève introuvable"
        resolveur.write_text(texte.replace(futur, futur + "raise RuntimeError('x')\n"), encoding="utf-8")
        return
    assert texte.count("def verifier_charge(") == 1, "ancre du résolveur partiel introuvable"
    if variante == "tronque":
        resolveur.write_text(texte[:texte.index("def verifier_charge(")] + "def verifier_charge(racine,\n",
                             encoding="utf-8")
        return
    resolveur.write_text(texte.replace("def verifier_charge(", "def _verifier_charge_retire("), encoding="utf-8")


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Arbres(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="vendor_bridge_")
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()  # macOS : /var → /private/var, comme `Path(__file__).resolve()`
        self.temoin = self.base / "temoin.txt"
        maison = self.base / "maison"
        maison.mkdir()
        (maison / ".gitconfig").write_text("[user]\n\tname = banc\n\temail = banc@exemple.invalid\n",
                                           encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("CLAUDE_PROJECT_DIR", "CADRE_PROJECT_ROOT", "PYTHONPATH")
                    and not k.startswith("GIT_")}
        self.env.update(HOME=str(maison), XDG_CONFIG_HOME=str(maison / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                        CADRE_STATE_DIR=str(self.base / "etat"), AGENTS_EVENTS_DIR=str(self.base / "events"),
                        BANC_V3_TEMOIN=str(self.temoin))
        self.projet = self.base / "projet"
        for sous in ("board", "gates", "specs"):
            (self.projet / ".agents" / "state" / sous).mkdir(parents=True)

    def kit(self, nom: str, *, ancien: bool, vendor: bool, resolveur: bool = True,
            copies: tuple[str, ...] = COPIES) -> Path:
        kit = self.base / nom
        bin_ = kit / ".agents" / "bin"
        bin_.mkdir(parents=True)
        for motif in copies:
            for fichier in HERE.glob(motif):
                if not fichier.name.startswith("test_"):
                    shutil.copy2(fichier, bin_ / fichier.name)
        if not resolveur:
            (bin_ / "vendor_paths.py").unlink(missing_ok=True)
        _cadre(kit / "src" / "cadre")
        if ancien:
            _faux_v3(kit / "agentic_v3", "ancien")
        if vendor:
            _faux_v3(kit / ".agents" / "vendor" / "agentic_v3", "vendor")
        return kit

    def tasks(self, kit: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(kit / ".agents" / "bin" / "tasks.py"),
                               "--root", str(self.projet), *args],
                              capture_output=True, text=True, timeout=180, env=env or self.env)

    def outbox(self, kit: Path) -> int:
        fait = subprocess.run([sys.executable, "-B", "-c", OUTBOX, str(kit / ".agents" / "bin" / "tasks.py"),
                               str(self.projet)], capture_output=True, text=True, timeout=120, env=self.env)
        self.assertEqual(0, fait.returncode, fait.stderr)
        return int(fait.stdout.strip())

    def ponts(self) -> list[str]:
        return self.temoin.read_text(encoding="utf-8").split() if self.temoin.exists() else []


class PontParLeResolveurTests(_Arbres):
    def test_ancien_seul(self) -> None:
        kit = self.kit("kit", ancien=True, vendor=False)
        fait = self.tasks(kit, "new", "b1")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual(["ancien/ancien"], self.ponts())
        self.assertEqual(0, self.outbox(kit), "le pont a acquitté l'intent")

    def test_neuf_seul(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=True)
        fait = self.tasks(kit, "new", "b2")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual(["vendor/vendor"], self.ponts(), fait.stderr)
        self.assertEqual(0, self.outbox(kit))

    def test_les_deux_le_vendor_gagne(self) -> None:
        kit = self.kit("kit", ancien=True, vendor=True)
        fait = self.tasks(kit, "new", "b3")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual(["vendor/vendor"], self.ponts(), fait.stderr)

    def test_les_deux_racine_sur_path(self) -> None:
        """C10 : la racine DEVANT la bibliothèque standard porte l'ancien `agentic_v3` ; le paquet, pas encore
        chargé, l'est par CHEMIN EXACT : le pont vient du vendor, jamais de l'ancien, jamais un refus (un import
        par `sys.path`, rattrapé par `verifier_charge`, finirait en `ProvenanceRefusee` : rouge ici)."""
        kit = self.kit("kit", ancien=True, vendor=True)
        fait = self.tasks(kit, "new", "b4", env={**self.env, "PYTHONPATH": str(kit)})
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertNotIn("ancien/ancien", self.ponts(), "l'ancien V3 a gagné")
        self.assertEqual(["vendor/vendor"], self.ponts(), fait.stderr)  # chargement EXACT : jamais un refus ici

    def test_v3_absent_l_outbox_est_gardee(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=False)
        fait = self.tasks(kit, "new", "b5")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual([], self.ponts())
        self.assertEqual(1, self.outbox(kit), "sans V3, l'intent reste dans l'outbox")
        rejeu = self.tasks(kit, "replay-sync")
        self.assertEqual(0, rejeu.returncode, rejeu.stderr)
        self.assertIn("replayed 0", rejeu.stdout)
        self.assertEqual(1, self.outbox(kit))

    def test_resolveur_absent_aucun_pont_l_outbox_est_gardee(self) -> None:
        kit = self.kit("kit", ancien=True, vendor=True, resolveur=False)
        self.assertFalse((kit / ".agents" / "bin" / "vendor_paths.py").exists())
        fait = self.tasks(kit, "new", "b6")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertEqual([], self.ponts(), "sans résolveur, aucun arbre n'est choisi au hasard")
        self.assertEqual(1, self.outbox(kit))

    def _resolveur_ampute_le_verbe_passe(self, variante: str) -> None:
        kit = self.kit(f"kit-{variante}", ancien=True, vendor=True)
        _amputer_resolveur(kit, variante)
        fait = self.tasks(kit, "new", f"b6bis-{variante}")
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.assertNotIn("Traceback", fait.stderr)
        self.assertEqual([], self.ponts(), "un résolveur incomplet a choisi un arbre")
        self.assertEqual(1, self.outbox(kit), "le refus du pont garde l'intent")
        liste = self.tasks(kit, "list")
        self.assertEqual(0, liste.returncode, liste.stderr)
        self.assertNotIn("Traceback", liste.stderr)

    def test_resolveur_vide_aucun_pont_le_verbe_passe(self) -> None:
        self._resolveur_ampute_le_verbe_passe("vide")

    def test_resolveur_partiel_aucun_pont_le_verbe_passe(self) -> None:
        self._resolveur_ampute_le_verbe_passe("partiel")

    def test_resolveur_tronque_aucun_pont_le_verbe_passe(self) -> None:
        self._resolveur_ampute_le_verbe_passe("tronque")

    def test_resolveur_qui_leve_aucun_pont_le_verbe_passe(self) -> None:
        self._resolveur_ampute_le_verbe_passe("leve")


class PontEnProcessusTests(_Arbres):
    """C15 — `agentic_v3` est DÉJÀ dans `sys.modules` quand le pont est demandé."""

    def _main(self, module, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = module.main(["--root", str(self.projet), *args])
        return rc, out.getvalue(), err.getvalue()

    def test_ancien_deja_importe_dans_un_arbre_les_deux_est_refuse_et_nomme(self) -> None:
        kit = self.kit("kit", ancien=True, vendor=True)
        propre = {k: v for k, v in sys.modules.items() if k != "agentic_v3" and not k.startswith("agentic_v3.")}
        env = {k: v for k, v in self.env.items() if k in ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM",
                                                           "CADRE_STATE_DIR", "AGENTS_EVENTS_DIR", "BANC_V3_TEMOIN")}
        with mock.patch.dict(sys.modules, propre, clear=True), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.dict(os.environ, env):
            os.environ.pop("CADRE_PROJECT_ROOT", None)  # restauré par `mock.patch.dict`
            ancien = importlib.util.spec_from_file_location(
                "agentic_v3", kit / "agentic_v3" / "__init__.py",
                submodule_search_locations=[str(kit / "agentic_v3")])
            paquet = importlib.util.module_from_spec(ancien)
            sys.modules["agentic_v3"] = paquet  # ce que le rootdir pytest sur `sys.path` aurait chargé
            ancien.loader.exec_module(paquet)
            tasks = _charger("tasks_banc_vendor_bridge_c15", kit / ".agents" / "bin" / "tasks.py")
            rc, _out, err = self._main(tasks, "new", "b7")
            self.assertEqual(0, rc, err)
            self.assertIn("ProvenanceRefusee", err)
            self.assertIn("TASKS: pont V3 REFUSÉ", err)
            self.assertNotIn("agentic_v3.reconciliation.board_bridge", sys.modules,
                             "un module du pont a été exécuté avant le contrôle de provenance")
            self.assertEqual(1, len(tasks.load(str(self.projet))["sync_outbox"]), "le refus garde l'intent")
            rc, _out, err = self._main(tasks, "replay-sync")
            self.assertEqual(1, rc, err)
            self.assertIn("ProvenanceRefusee", err)
        self.assertEqual([], self.ponts(), "un pont de l'ancien arbre a été construit")

    def test_le_paquet_du_kit_est_accepte(self) -> None:
        """Le cas nominal sous pytest : le paquet du kit (chargé par le conftest, ou ici par chemin exact s'il ne
        l'est pas encore) est celui que le résolveur désigne pour la racine du kit — accepté."""
        tasks = _charger("tasks_banc_vendor_bridge_kit", HERE / "tasks.py")
        attendu = tasks._RESOLVEUR_V3.dossier_paquet(REPO, "agentic_v3")
        parent = os.path.realpath(attendu.parent)
        sans_parent = [e for e in sys.path if not e or os.path.realpath(e) != parent]
        with mock.patch.object(sys, "path", sans_parent):
            pont = tasks._importer_pont_v3(REPO)
            places = [i for i, e in enumerate(sys.path) if e and os.path.realpath(e) == parent]
            sites = [i for i, e in enumerate(sys.path)
                     if os.path.basename(os.path.normpath(e)) in ("site-packages", "dist-packages")]
            if places and sites:  # devant `site-packages` : jamais ajouté EN QUEUE
                self.assertLess(places[0], sites[0], "le parent est derrière site-packages : un append")
        self.assertEqual(1, len(places), "le parent du paquet n'est pas placé sur sys.path par l'API")
        self.assertGreater(places[0], 0, "le parent est en tête de sys.path : un insert(0) à la main")
        self.assertEqual(attendu.resolve(), Path(sys.modules["agentic_v3"].__file__).resolve().parent)
        self.assertTrue(Path(sys.modules[pont.__module__].__file__).resolve().is_relative_to(attendu.resolve()))

    def test_un_paquet_masque_par_none_est_absent_pas_refuse(self) -> None:
        """`None` dans `sys.modules` (un banc qui masque le paquet) : comme l'import qu'il remplace, c'est un
        `agentic_v3` ABSENT — aucun pont, aucune annonce de refus — jamais une `ProvenanceRefusee`."""
        tasks = _charger("tasks_banc_vendor_bridge_masque", HERE / "tasks.py")
        err = io.StringIO()
        with mock.patch.dict(sys.modules, {"agentic_v3": None}), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.dict(os.environ, {"CADRE_STATE_DIR": str(self.base / "etat"),
                                             "AGENTS_EVENTS_DIR": str(self.base / "events")}), redirect_stderr(err):
            self.assertEqual(0, tasks.replay_sync(str(self.projet)))
        self.assertNotIn("ProvenanceRefusee", err.getvalue())
        self.assertNotIn("REFUSÉ", err.getvalue())

    def test_un_init_qui_leve_ne_laisse_pas_le_paquet_a_moitie_charge(self) -> None:
        """B10 — l'`__init__` du vendor lève (un sous-module absent : `ModuleNotFoundError` au nom du paquet, donc
        « paquet incomplet ») : le verbe rend 0, l'intent reste, et `agentic_v3` n'est PAS laissé dans
        `sys.modules` — sinon le drain d'après le verbe bâtirait un pont sur un paquet à moitié exécuté."""
        kit = self.kit("kit-init", ancien=False, vendor=True)
        (kit / ".agents" / "vendor" / "agentic_v3" / "__init__.py").write_text(
            "ORIGINE = 'vendor'\nimport agentic_v3.manquant  # l'__init__ lève\n", encoding="utf-8")
        propre = {k: v for k, v in sys.modules.items() if k != "agentic_v3" and not k.startswith("agentic_v3.")}
        env = {k: v for k, v in self.env.items() if k in ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM",
                                                           "CADRE_STATE_DIR", "AGENTS_EVENTS_DIR", "BANC_V3_TEMOIN")}
        with mock.patch.dict(sys.modules, propre, clear=True), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.dict(os.environ, env):
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            tasks = _charger("tasks_banc_vendor_bridge_init", kit / ".agents" / "bin" / "tasks.py")
            rc, _out, err = self._main(tasks, "new", "b10")
            self.assertEqual(0, rc, err)
            self.assertNotIn("agentic_v3", sys.modules, "un __init__ qui lève a laissé le paquet à moitié chargé")
            self.assertEqual(1, len(tasks.load(str(self.projet))["sync_outbox"]), "l'intent reste dans l'outbox")
        self.assertEqual([], self.ponts(), "un pont a été bâti sur un paquet à moitié exécuté")


class CauseDiteTests(_Arbres):
    """B6/B9 — au déversement sans pont (seuil abaissé à 0 : le premier intent déborde), la ligne
    `TASKS: agentic_v3 non chargé dans <racine> (<cause>)` DIT pourquoi : résolveur absent, incomplet ou
    illisible, ou paquet incomplet — jamais `absent de`, réservé aux deux emplacements vides (S3 de
    `test_tasks_sync_sans_v3.py`). Mutant : le libellé `absent` rendu à la ligne avec cause → rouge."""

    def _lignes(self, kit: Path) -> list[str]:
        """Les lignes de déversement sans pont ; chacune DOIT porter le libellé « non chargé » avec sa cause."""
        lignes = [ligne for ligne in self._deverser(kit).splitlines() if ligne.startswith("TASKS: agentic_v3 ")
                  and "aucun pont ne se construit" in ligne]
        self.assertTrue(lignes, "aucune ligne de déversement sans pont")
        for ligne in lignes:
            self.assertTrue(ligne.startswith("TASKS: agentic_v3 non chargé dans "), ligne)
        return lignes

    def _deverser(self, kit: Path) -> str:
        propre = {k: v for k, v in sys.modules.items() if k != "agentic_v3" and not k.startswith("agentic_v3.")}
        env = {k: v for k, v in self.env.items() if k in ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM",
                                                           "CADRE_STATE_DIR", "AGENTS_EVENTS_DIR", "BANC_V3_TEMOIN")}
        err = io.StringIO()
        with mock.patch.dict(sys.modules, propre, clear=True), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.dict(os.environ, env):
            os.environ.pop("CADRE_PROJECT_ROOT", None)
            tasks = _charger(f"tasks_banc_vendor_bridge_{kit.name}", kit / ".agents" / "bin" / "tasks.py")
            with mock.patch.object(tasks, "_SYNC_OUTBOX_SEUIL", 0), redirect_stdout(io.StringIO()), \
                    redirect_stderr(err):
                self.assertEqual(0, tasks.main(["--root", str(self.projet), "new", "b9"]))
        self.assertEqual([], self.ponts())
        return err.getvalue()

    def test_resolveur_absent_est_dit(self) -> None:
        kit = self.kit("kit-sans-resolveur", ancien=True, vendor=False, resolveur=False)
        self.assertIn("(résolveur vendor_paths.py absent de ", self._lignes(kit)[-1])

    def test_paquet_incomplet_est_dit(self) -> None:
        kit = self.kit("kit-incomplet", ancien=False, vendor=True)
        (kit / ".agents" / "vendor" / "agentic_v3" / "reconciliation" / "board_bridge.py").unlink()
        self.assertIn("(paquet incomplet : ", self._lignes(kit)[-1])

    def test_resolveur_vide_ou_partiel_est_dit(self) -> None:
        """B6bis — un résolveur incomplet compte comme ABSENT, et la ligne nomme ce qui lui manque."""
        for variante, cause in (("vide", "incomplet : " + ", ".join(API_RESOLVEUR)),
                                ("partiel", "incomplet : verifier_charge"), ("tronque", "illisible : SyntaxError"),
                                ("leve", "illisible : RuntimeError")):
            with self.subTest(variante=variante):
                kit = self.kit(f"kit-{variante}", ancien=True, vendor=True)
                _amputer_resolveur(kit, variante)
                self.assertIn(f"(résolveur vendor_paths.py {cause})", self._lignes(kit)[-1])


class CadreParLeResolveurTests(_Arbres):
    def _chemins(self, kit: Path) -> dict[str, str]:
        fait = subprocess.run([sys.executable, "-B", "-c", CADRE, str(kit / ".agents" / "bin")],
                              capture_output=True, text=True, timeout=120, env=self.env)
        self.assertEqual(0, fait.returncode, fait.stderr)
        self.stderr = fait.stderr
        return json.loads(fait.stdout)

    def _attendus(self, dossier: Path) -> dict[str, str]:
        return {"ids": str(dossier / "ledger" / "ids.py"), "store": str(dossier),
                "paths": str(dossier / "paths.py"), "index": str(dossier)}

    def test_ancien_seul(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=False, copies=COPIES_CADRE)
        self.assertEqual(self._attendus(kit / "src" / "cadre"), self._chemins(kit))

    def test_neuf_seul_et_new_alloue_avec_le_generateur_du_vendor(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=False, copies=COPIES_CADRE + COPIES)
        neuf = kit / ".agents" / "vendor" / "cadre"
        neuf.parent.mkdir(parents=True)
        (kit / "src" / "cadre").rename(neuf)
        self.assertFalse((kit / "src" / "cadre").exists(), "précondition : aucun ancien générateur")
        self.assertEqual(self._attendus(neuf), self._chemins(kit))
        fait = self.tasks(kit, "new", "c1")
        self.assertEqual(0, fait.returncode, fait.stderr)

    def test_les_deux_le_vendor_gagne(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=False, copies=COPIES_CADRE)
        neuf = _cadre(kit / ".agents" / "vendor" / "cadre")
        self.assertEqual(self._attendus(neuf), self._chemins(kit))

    def test_resolveur_vide_ou_partiel_repli_src_cadre(self) -> None:
        """B6bis côté `cadre` — résolveur incomplet = ABSENT : les trois producteurs se chargent (aucun
        `AttributeError`, `SyntaxError` ni `RuntimeError`) et replient sur `src/cadre`, même quand
        `.agents/vendor/cadre` existe. F1 : illisible (tronqué, qui lève) le DIT, une ligne stderr par producteur
        (trois) ; incomplet (vide, partiel) reste muet (zéro). Mutant : la ligne retirée d'un producteur → rouge."""
        for variante, exception in (("vide", None), ("partiel", None), ("tronque", "SyntaxError"),
                                    ("leve", "RuntimeError")):
            with self.subTest(variante=variante):
                kit = self.kit(f"kit-{variante}", ancien=False, vendor=False, copies=COPIES_CADRE)
                _cadre(kit / ".agents" / "vendor" / "cadre")
                _amputer_resolveur(kit, variante)
                self.assertEqual(self._attendus(kit / "src" / "cadre"), self._chemins(kit))
                resolveur = kit / ".agents" / "bin" / "vendor_paths.py"
                dites = [ligne for ligne in self.stderr.splitlines() if ligne.startswith(
                    tuple(f"{p}: résolveur {resolveur} illisible ({exception}: " for p in DISENT))
                    and ligne.endswith(") — repli sur src/cadre")] if exception else []
                self.assertEqual(sorted(DISENT) if exception else [], sorted(d.split(":", 1)[0] for d in dites),
                                 self.stderr)
                self.assertEqual(len(dites), sum("illisible" in ligne for ligne in self.stderr.splitlines()),
                                 self.stderr)


class CopieEtrangereTests(_Arbres):
    """F2/F3 — une copie ÉTRANGÈRE du résolveur (un autre arbre, un autre appelant du processus) est DÉJÀ inscrite
    sous `_cadre_vendor_paths_bin` : les trois producteurs ne la croient pas, elle ne vient pas du fichier ATTENDU
    (F3) ; et quand le résolveur attendu lève à l'exécution, la copie d'avant est RENDUE — jamais le nom retiré,
    jamais une copie à moitié exécutée (F2). Mutants : relecture sans contrôle du fichier (`if module is None:`)
    → F3 rouge ; `_executer` (ou la branche de `record_id`) qui retire au lieu de rendre `existant` → F2 rouge."""

    PRODUCTEURS = (("record_id.py", "_IDS_PATH"), ("event_store.py", "_SRC_CADRE"),
                   ("migrate_index_to_db.py", "_SRC_CADRE"))

    def _sonder(self, kit: Path) -> dict[str, dict]:
        vus = {}
        for fichier, attribut in self.PRODUCTEURS:
            fait = subprocess.run([sys.executable, "-B", "-c", ETRANGERE, str(kit / ".agents" / "bin"), fichier,
                                   str(self.base / "etranger"), attribut],
                                  capture_output=True, text=True, timeout=120, env=self.env)
            self.assertEqual(0, fait.returncode, fait.stderr)
            vus[fichier] = json.loads(fait.stdout.strip().splitlines()[-1])
        return vus

    def test_f3_copie_etrangere_non_crue(self) -> None:
        kit = self.kit("kit", ancien=False, vendor=False, copies=COPIES_CADRE)
        neuf = _cadre(kit / ".agents" / "vendor" / "cadre")
        for fichier, vu in self._sonder(kit).items():
            with self.subTest(producteur=fichier):
                self.assertTrue(Path(vu["dossier"]).is_relative_to(neuf), f"copie étrangère crue : {vu}")
                self.assertFalse(vu["etrangere"], "la copie étrangère est restée inscrite")

    def test_f2_resolveur_qui_leve_rend_la_copie_d_avant(self) -> None:
        kit = self.kit("kit-tronque", ancien=False, vendor=False, copies=COPIES_CADRE)
        _cadre(kit / ".agents" / "vendor" / "cadre")
        _amputer_resolveur(kit, "tronque")
        for fichier, vu in self._sonder(kit).items():
            with self.subTest(producteur=fichier):
                self.assertTrue(Path(vu["dossier"]).is_relative_to(kit / "src" / "cadre"), vu)
                self.assertTrue(vu["etrangere"], "la copie d'avant n'est pas rendue après un exec raté")


if __name__ == "__main__":
    unittest.main()
