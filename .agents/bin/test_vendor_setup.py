"""test_vendor_setup.py — témoin de la phase D de T-01M5BXTGX5YN8XEXTG1PP7A5ZX.

Les trois CLI du kit (`project_init.py`, `setup_projet.py`, `dashboard.py`)
exécutent le `cadre` de LEUR racine : un `cadre` installé — ici un faux, posé
par un `.pth` dans un venv JETABLE, qui sort 97 à l'import — ne gagne jamais.
Les deux conftest, eux, AJOUTENT EN QUEUE : le `cadre` de l'adoptant garde la
priorité dans les bancs.

  D1, D2 et D5 tournent sur DEUX dispositions, deux copies jetables de
  `.agents/bin` et du paquet de l'arbre (`vendor_paths.exiger`) : l'ancienne
  (sous `src/cadre`, sans `.agents/vendor`) et « `.agents/vendor/cadre` seul »
  (sans `src/`) — le kit lui-même vit sous `.agents/vendor/cadre` depuis
  T-01M5BXTRP8GKS7DMDQCTKK88DZ. Chaque jambe juge la provenance EXACTE.
  D1  `test_cadre_installe_ne_gagne_pas` : venv + `.pth` ; les trois CLI chargent
      le `cadre` que le résolveur désigne sous leur racine. Mutant : la CLI passe
      à `append` (`amorcer_conftest`) → le faux gagne, rouge.
  D2  `test_parent_deja_en_queue_remonte` (réserve C14) : le parent est DÉJÀ sur
      `sys.path`, en queue derrière le `.pth` ; les trois CLI chargent le paquet
      par chemin exact (`charger_paquet`, `setup_projet._charger` compris). Mutant
      `_charger` rendu à `import cadre` par `sys.path` → rouge.
  D5  `test_cadre_pythonpath_ne_gagne_pas` : un second faux `cadre` (sortie 98)
      porté par `PYTHONPATH` ; les trois CLI chargent par chemin exact. Deux
      jambes pour `setup_projet` : `_charger`
      seul, et la sonde `--sonde-snapshot` (`_charger`, PUIS `import dashboard`,
      qui ne doit pas redescendre le parent). Mutant : une CLI revient à
      `amorcer_cli` (derrière la stdlib, donc derrière `PYTHONPATH`) → rouge.
  D3  `test_parent_cadre_suit_le_resolveur` : la règle RECOPIÉE dans
      `setup_projet._parent_cadre` (liste d'imports fermée, M4 de
      `test_setup_projet.py`) rend le parent de `vendor_paths.parent_import`
      sur cinq arbres (ancien, neuf, les deux, neuf sans `__init__`, absent).
  D4  `test_conftest_laisse_gagner_l_adoptant` : chaque conftest, seul dans un
      arbre jetable, AJOUTE le parent du kit (non-vacuité) DERRIÈRE le `cadre`
      de l'adoptant (`site.addsitedir`). Mutant `amorcer_cli` → rouge.
  D6  `test_src_de_l_adoptant_ne_masque_pas_la_stdlib` : arbre façon adoptant
      (ancienne disposition) dont le `src/` porte aussi `token.py`, `argparse.py`,
      `tempfile.py`, `ast.py`, `base64.py` (sortie 95) ; le VRAI `--help` de
      `project_init.py` et de `dashboard.py` rend 0, et après `setup_projet._charger`
      `import base64` lit la stdlib (S-01M5CJ820Y). Mutants : tête absolue dans
      `charger_paquet` ; `_charger` d'avant (`src/` en tête) → rc 95.
  D7  `test_cadre_deja_charge_ailleurs_refuse` : un `cadre` d'un autre arbre est
      déjà dans `sys.modules` (appelant en processus) ; `project_init`,
      `dashboard` et la sonde de `setup_projet` refusent par `ProvenanceRefusee`.
      Mutant : `verifier_charge` retiré de `charger_paquet`.
  D8  `test_charger_paquet_enregistre_avant_exec` : un paquet dont l'`__init__`
      importe `cadre.sous`, faux `cadre` sur `PYTHONPATH` ; le vrai gagne.
      Mutant : `sys.modules` enregistré APRÈS `exec_module`.
  D9  `test_init_qui_leve_ne_laisse_ni_paquet_ni_sous_module` : l'`__init__`
      importe `cadre.sous` puis lève quand `CASSE=1` ; après l'échec, ni `cadre`
      ni `cadre.sous` ne restent dans `sys.modules`, et le 2e appel (`CASSE=0`)
      charge proprement. Mutant : retrait de `sys.modules` supprimé → rouge.
  D10 `test_charger_paquet_ne_touche_pas_sys_path` : `charger_paquet` laisse
      `sys.path` intact, et un `src/msvcrt.py` (sortie 95) de l'adoptant ne
      gagne ni le `--help` de `project_init.py` ni celui de `dashboard.py`.
      Non-vacuité : au rang d'`amorcer_cli`, ce `src/` gagne `import msvcrt`
      (POSIX ; sous Windows `msvcrt` est intégré, la jambe est sautée et dite).
      Mutant : `amorcer_cli` rétabli dans `charger_paquet` → rouge. BORNE MESURÉE :
      après le chargement de `cadre`, le `--help` de `dashboard.py` n'importe que
      des modules standard, résolus avant un `src/` placé derrière la stdlib —
      aucun module qu'il importe ne peut être empoisonné. Chaque CLI est donc
      aussi relevée EN PROCESSUS : `src/` absent de `sys.path` après son `--help`.

  D11 `test_sync_spec_v3_neuf_gagne` : `_sync_spec` lance l'`agentic_v3` de
      `.agents/vendor` (seul, ou à côté d'un `agentic_v3/` racine) ; l'ancien seul
      reste servi. Mutant : argv rendu à `-m agentic_v3` → rouge.
  D12 `DoctrineV3Tests` : dans AGENTS.md, copilot-instructions.md et QUICK-SETUP.md,
      CHAQUE span qui contient `-m agentic_v3` porte `PYTHONPATH=.agents/vendor` et
      `-P`, ou SA phrase dit « at the root » ; AGENTS.md cite
      `.agents/vendor/agentic_v3/`. Mutants D (QUICK-SETUP « Use `python3 -m
      agentic_v3` ») et E (AGENTS.md réduit à `python -m agentic_v3 sync-spec`) rejoués
      en sous-tests → rouges.
  D13 `test_aucune_surface_ne_place_le_moteur_a_la_racine` : copilot-instructions.md
      sans « (`agentic_v3/`) », les deux usage.html sans `<code>agentic_v3/</code>`,
      QUICK-SETUP avec `git rm -r agentic_v3` puis le dossier résiduel. Mutant : ces
      quatre fichiers rendus à e4947a589 → rouge. QUICK-SETUP cite aussi
      `.agents/vendor/agentic_v3/`.
  D12bis `test_bornes_de_phrase_et_blocs_clos` : une phrase close par `.)` ou
      `.**`, un titre Markdown, un bloc `~~~` ou indenté ne laissent pas un
      « at the root » voisin couvrir une prescription fautive.

BORNES : D12 lit « at the root » en MOT NU, sans lire la négation : une phrase
qui le nie (« never at the root », « not at the root ») couvre encore son span ;
seule la relecture voit ce cas.
La CLI `setup_projet.py` est exercée par `_charger`, pas par `main` la CLI `setup_projet.py` est exercée par `_charger`, pas par `main`
(qui refuse l'arbre du kit) ; `dashboard.py` par le canal réel de `events.py`
(`_importer_redaction_paquet`), pas par son serveur.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FAUX = "CADRE-INSTALLE"
FAUX_PP = "CADRE-PYTHONPATH"
STDLIB = "STDLIB-MASQUEE"
MASQUES = ("token", "argparse", "tempfile", "ast")  # D6 : modules standard, posés dans le `src/` de l'adoptant
HORS_STDLIB = "msvcrt"  # D10 : absent de la stdlib POSIX, donc trouvé dans `src/` dès que `src/` est sur sys.path
MASQUE_SETUP = "base64"  # D6 : module standard importé APRÈS `setup_projet._charger` (S-01M5CJ820Y)
# Jambe -> fichier de la CLI. `setup_projet` : `_charger` SEUL (C14) ; `setup_sonde` : la séquence de
# `--sonde-snapshot`, `_charger` PUIS `import dashboard` (qui ne doit pas redescendre le parent).
CLIS = {"project_init": "project_init.py", "setup_projet": "setup_projet.py",
        "setup_sonde": "setup_projet.py", "dashboard": "dashboard.py"}


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


VP = _charger("vendor_paths_banc_setup", HERE / "vendor_paths.py")


def _env() -> dict[str, str]:
    """L'environnement sans `PYTHON*` ni `PYTEST*` : rien ne s'insère devant la stdlib."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# Charge la CLI par son canal, puis rend le fichier du `cadre` qu'elle a importé.
# `parent` != "-" : posé EN QUEUE de sys.path AVANT la CLI (réserve C14).
# `cache` != "-" : un `cadre` de ce dossier est DÉJÀ importé avant la CLI (D7).
_SONDE = r'''
import importlib.util, runpy, sys
from pathlib import Path
cli, fichier, racine, parent, cache = sys.argv[1:6]
if parent != "-":
    sys.path.append(parent)
if cache != "-":
    sys.path.insert(0, cache)
    import cadre
    sys.path.remove(cache)
if cli == "project_init":
    sys.argv = [fichier, "--help"]
    try:
        runpy.run_path(fichier, run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise
    module = sys.modules["cadre"]
else:
    spec = importlib.util.spec_from_file_location("sonde_" + cli, fichier)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if cli.startswith("setup_"):
        mod._charger(Path(racine))
        if cli == "setup_sonde":
            import dashboard
        import cadre as module
    else:
        module = mod._events_mod._importer_redaction_paquet()
print("CADRE=" + str(Path(module.__file__).resolve()))
'''


# D10 : le `--help` RÉEL de la CLI argv[1], joué en processus, puis `src/` (argv[2]) cherché dans `sys.path`.
_APRES_HELP = r'''
import os, runpy, sys
fichier, src = sys.argv[1], os.path.realpath(sys.argv[2])
sys.argv = [fichier, "--help"]
try:
    runpy.run_path(fichier, run_name="__main__")
except SystemExit as exc:
    if exc.code not in (0, None):
        raise
print("SRC_SUR_PATH=" + str(src in [os.path.realpath(e) for e in sys.path if e]))
'''


def _faux(dossier: Path, marque: str, code: int) -> None:
    """Un faux paquet `cadre` sous `dossier`, qui crie `marque` et sort `code` à l'import."""
    (dossier / "cadre").mkdir(parents=True)
    (dossier / "cadre" / "__init__.py").write_text(
        f"import sys\nsys.stderr.write({marque!r} + '\\n')\nraise SystemExit({code})\n", encoding="utf-8")


class CliTests(unittest.TestCase):
    """D1, D2, D5 à D8 : un venv jetable dont le `.pth` porte un faux `cadre`, un second
    faux sur `PYTHONPATH`, et deux dispositions (ancienne, `.agents/vendor` seul)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="vendor_setup_")
        base = Path(cls._tmp.name).resolve()
        cls.base = base
        vendor = base / "arbre_vendor"
        shutil.copytree(HERE, vendor / ".agents" / "bin",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "conftest.py"))
        shutil.copytree(VP.exiger(REPO, "cadre"), vendor / ".agents" / "vendor" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__"))
        ancien = base / "arbre_ancien"
        shutil.copytree(HERE, ancien / ".agents" / "bin",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "conftest.py"))
        shutil.copytree(VP.exiger(REPO, "cadre"), ancien / "src" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__"))
        cls.racines = {"ancienne": ancien, "vendor seul": vendor}
        _faux(base / "pythonpath", FAUX_PP, 98)
        # D6 : arbre façon adoptant, ancienne disposition, son code dans `src/` à côté de `src/cadre`.
        adoptant = base / "arbre_adoptant"
        shutil.copytree(HERE, adoptant / ".agents" / "bin",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "conftest.py"))
        shutil.copytree(VP.exiger(REPO, "cadre"), adoptant / "src" / "cadre",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for nom in (*MASQUES, HORS_STDLIB, MASQUE_SETUP):
            (adoptant / "src" / f"{nom}.py").write_text(
                f"import sys\nsys.stderr.write({STDLIB!r} + ':{nom}\\n')\nraise SystemExit(95)\n",
                encoding="utf-8")
        cls.adoptant = adoptant
        # D7 : un `cadre` d'un AUTRE arbre, importable sans bruit.
        (base / "cache" / "cadre").mkdir(parents=True)
        (base / "cache" / "cadre" / "__init__.py").write_text('ORIGINE = "autre-arbre"\n', encoding="utf-8")
        # D8 : un paquet dont l'`__init__` importe un sous-module par son nom absolu.
        sous = base / "arbre_sous" / ".agents" / "vendor" / "cadre"
        sous.mkdir(parents=True)
        (sous / "__init__.py").write_text("from cadre import sous\nORIGINE = 'kit:' + sous.NOM\n",
                                          encoding="utf-8")
        (sous / "sous.py").write_text("NOM = 'sous'\n", encoding="utf-8")
        # D9 : le même, mais son `__init__` lève APRÈS avoir importé `cadre.sous` quand `CASSE=1`.
        casse = base / "arbre_casse" / ".agents" / "vendor" / "cadre"
        casse.mkdir(parents=True)
        (casse / "__init__.py").write_text(
            "import os\nfrom cadre import sous\nif os.environ.get('CASSE') == '1':\n"
            "    raise RuntimeError('CASSE')\nORIGINE = 'kit:' + sous.NOM\n", encoding="utf-8")
        (casse / "sous.py").write_text("NOM = 'sous'\n", encoding="utf-8")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(base / "venv")],
                       check=True, capture_output=True, timeout=120, env=_env())
        bindir = "Scripts" if os.name == "nt" else "bin"
        cls.py = base / "venv" / bindir / ("python.exe" if os.name == "nt" else "python")
        site = subprocess.run([str(cls.py), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                              check=True, capture_output=True, text=True, timeout=60, env=_env(),
                              cwd=base).stdout.strip()
        _faux(base / "faux", FAUX, 97)
        (Path(site) / "cadre_installe.pth").write_text(str(base / "faux") + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _env_pp(self, pythonpath: bool) -> dict[str, str]:
        env = _env()
        if pythonpath:
            env["PYTHONPATH"] = str(self.base / "pythonpath")
        return env

    def _lancer(self, racine: Path, cli: str, parent: str = "-", cache: str = "-",
                pythonpath: bool = False) -> subprocess.CompletedProcess:
        fichier = racine / ".agents" / "bin" / CLIS[cli]
        return subprocess.run([str(self.py), "-c", _SONDE, cli, str(fichier), str(racine), parent, cache],
                              capture_output=True, text=True, timeout=120, env=self._env_pp(pythonpath),
                              cwd=self.base)

    def _kit_gagne(self, racine: Path, cli: str, parent: str, pythonpath: bool = False) -> None:
        p = self._lancer(racine, cli, parent, pythonpath=pythonpath)
        sortie = p.stdout + p.stderr
        for marque in (FAUX, FAUX_PP):
            self.assertNotIn(marque, p.stderr, f"{cli} : le faux cadre {marque} a gagné\n{sortie}")
        self.assertEqual(p.returncode, 0, sortie)
        lignes = [ligne[len("CADRE="):] for ligne in p.stdout.splitlines() if ligne.startswith("CADRE=")]
        self.assertEqual(len(lignes), 1, sortie)
        attendu = VP.exiger(racine, "cadre").resolve()
        self.assertTrue(Path(lignes[0]).is_relative_to(attendu),
                        f"{cli} : cadre chargé depuis {lignes[0]}, attendu sous {attendu}")

    def _matrice(self, mode: str) -> None:
        for disposition, racine in self.racines.items():
            parent = str(VP.parent_import(racine, "cadre")) if mode == "queue" else "-"
            for cli in CLIS:
                with self.subTest(disposition=disposition, cli=cli):
                    self._kit_gagne(racine, cli, parent, pythonpath=mode == "pythonpath")

    def test_sync_spec_v3_neuf_gagne(self) -> None:
        """D11 : `setup_projet._sync_spec`, par son canal réel (`_executer`, cwd = R), lance
        l'`agentic_v3` de `.agents/vendor` — seul, et même quand un `agentic_v3/` reste à la
        racine ; l'ancien seul reste servi. Mutant : argv rendu à `-m agentic_v3` → rouge."""
        setup = _charger("setup_projet_banc_v3", HERE / "setup_projet.py")
        arbres = {"neuf seul": ((".agents/vendor", "neuf"),), "ancien seul": ((".", "ancien"),),
                  "les deux": ((".agents/vendor", "neuf"), (".", "ancien"))}
        attendus = {"neuf seul": "neuf", "ancien seul": "ancien", "les deux": "neuf"}
        for nom, lieux in arbres.items():
            racine = self.base / "v3" / nom.replace(" ", "_")
            for parent, marque in lieux:
                paquet = racine / parent / "agentic_v3"
                paquet.mkdir(parents=True)
                (paquet / "__init__.py").write_text("", encoding="utf-8")
                (paquet / "__main__.py").write_text(f"import sys\nprint({marque!r}, sys.argv[1:])\n",
                                                    encoding="utf-8")
            with self.subTest(arbre=nom):
                sortie = setup._sync_spec(racine, "docs/specs/a.md")
                self.assertEqual((sortie.rc, sortie.stdout.strip()),
                                 (0, f"{attendus[nom]} ['sync-spec', '--', 'docs/specs/a.md']"), sortie.stderr)

    def test_les_faux_cadres_sont_vivants(self) -> None:
        """Non-vacuité : sans CLI, le `.pth` (97) puis `PYTHONPATH` (98) rendent un faux
        `cadre` ; la disposition « vendor seul » n'a pas de `src/`."""
        for pythonpath, attendu in ((False, (97, FAUX)), (True, (98, FAUX_PP))):
            p = subprocess.run([str(self.py), "-c", "import cadre"], capture_output=True, text=True,
                               timeout=60, env=self._env_pp(pythonpath), cwd=self.base)
            self.assertEqual((p.returncode, attendu[1] in p.stderr), (attendu[0], True), p.stdout + p.stderr)
        self.assertEqual(VP.provenance(self.racines["vendor seul"], "cadre"), "vendor")
        self.assertFalse((self.racines["vendor seul"] / "src").exists())
        self.assertEqual(VP.provenance(self.racines["ancienne"], "cadre"), "ancien")
        self.assertFalse((self.racines["ancienne"] / ".agents" / "vendor").exists())

    def test_cadre_installe_ne_gagne_pas(self) -> None:
        self._matrice("pth")

    def test_parent_deja_en_queue_remonte(self) -> None:
        self._matrice("queue")

    def test_cadre_pythonpath_ne_gagne_pas(self) -> None:
        self._matrice("pythonpath")

    def test_src_de_l_adoptant_ne_masque_pas_la_stdlib(self) -> None:
        """D6 : le VRAI `--help`, sur un arbre dont `src/` porte des modules aux noms
        de la bibliothèque standard ; non-vacuité : `src/` en tête, ils tournent."""
        p = subprocess.run([str(self.py), "-c", "import token"], capture_output=True, text=True, timeout=60,
                           env=dict(_env(), PYTHONPATH=str(self.adoptant / "src")), cwd=self.base)
        self.assertEqual((p.returncode, STDLIB in p.stderr), (95, True), p.stdout + p.stderr)
        for cli in ("project_init", "dashboard"):
            with self.subTest(cli=cli):
                p = subprocess.run([str(self.py), str(self.adoptant / ".agents" / "bin" / CLIS[cli]), "--help"],
                                   capture_output=True, text=True, timeout=120, env=_env(), cwd=self.base)
                self.assertNotIn(STDLIB, p.stderr, f"{cli} : la stdlib est masquée par src/\n{p.stderr}")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        code = ("import importlib.util, sys\nfrom pathlib import Path\n"
                "s = importlib.util.spec_from_file_location('sonde_setup_d6', sys.argv[1])\n"
                "m = sys.modules[s.name] = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
                "m._charger(Path(sys.argv[2]))\n"
                f"sys.modules.pop({MASQUE_SETUP!r}, None)\nimport {MASQUE_SETUP}, cadre\n"
                f"print('STDLIB=' + {MASQUE_SETUP}.__file__)\nprint('CADRE=' + cadre.__file__)\n")
        p = subprocess.run([str(self.py), "-c", code, str(self.adoptant / ".agents" / "bin" / "setup_projet.py"),
                            str(self.adoptant)], capture_output=True, text=True, timeout=120, env=_env(), cwd=self.base)
        self.assertNotIn(STDLIB, p.stderr, f"setup_projet._charger : src/ masque la stdlib\n{p.stderr}")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        lignes = dict(ligne.split("=", 1) for ligne in p.stdout.splitlines() if "=" in ligne)
        self.assertFalse(Path(lignes["STDLIB"]).resolve().is_relative_to(self.adoptant.resolve()), p.stdout)
        self.assertTrue(Path(lignes["CADRE"]).resolve().is_relative_to(VP.exiger(self.adoptant, "cadre").resolve()))

    def test_cadre_deja_charge_ailleurs_refuse(self) -> None:
        """D7 : un `cadre` d'un autre arbre DÉJÀ importé → `ProvenanceRefusee`, nommée."""
        for disposition, racine in self.racines.items():
            for cli in ("project_init", "dashboard", "setup_sonde"):
                with self.subTest(disposition=disposition, cli=cli):
                    p = self._lancer(racine, cli, cache=str(self.base / "cache"))
                    self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
                    self.assertIn("ProvenanceRefusee", p.stderr, p.stdout + p.stderr)
                    self.assertNotIn("CADRE=", p.stdout, p.stdout + p.stderr)

    def test_charger_paquet_enregistre_avant_exec(self) -> None:
        """D8 : l'`__init__` importe `cadre.sous` ; faux `cadre` sur `PYTHONPATH` (98)."""
        code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('vp_d8', sys.argv[1]); "
                "vp = importlib.util.module_from_spec(s); sys.modules[s.name] = vp; s.loader.exec_module(vp); "
                "print('ORIGINE=' + vp.charger_paquet(sys.argv[2], 'cadre').ORIGINE)")
        p = subprocess.run([str(self.py), "-c", code, str(HERE / "vendor_paths.py"), str(self.base / "arbre_sous")],
                           capture_output=True, text=True, timeout=60, env=self._env_pp(True), cwd=self.base)
        self.assertNotIn(FAUX_PP, p.stderr, p.stdout + p.stderr)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "ORIGINE=kit:sous"), p.stdout + p.stderr)

    def _vp(self, corps: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        """`corps` exécuté sous le venv avec `vp` = le résolveur de `HERE`, chargé par chemin."""
        code = ("import importlib.util, os, sys\n"
                "s = importlib.util.spec_from_file_location('vp_sonde', sys.argv[1])\n"
                "vp = importlib.util.module_from_spec(s)\nsys.modules[s.name] = vp\ns.loader.exec_module(vp)\n" + corps)
        return subprocess.run([str(self.py), "-c", code, str(HERE / "vendor_paths.py"), *args],
                              capture_output=True, text=True, timeout=60, env=env or _env(), cwd=self.base)

    def test_init_qui_leve_ne_laisse_ni_paquet_ni_sous_module(self) -> None:
        """D9 : l'`__init__` importe `cadre.sous`, puis lève sous `CASSE=1` ; rien ne reste, le 2e appel charge."""
        p = self._vp("os.environ['CASSE'] = '1'\n"
                     "try:\n    vp.charger_paquet(sys.argv[2], 'cadre')\n    print('LEVE=non')\n"
                     "except RuntimeError:\n    print('LEVE=oui')\n"
                     "print('RESTE=' + ','.join(sorted(n for n in sys.modules if n == 'cadre' or n.startswith('cadre.'))))\n"
                     "os.environ['CASSE'] = '0'\n"
                     "print('ORIGINE=' + vp.charger_paquet(sys.argv[2], 'cadre').ORIGINE)\n",
                     str(self.base / "arbre_casse"))
        self.assertEqual((p.returncode, p.stdout.splitlines()), (0, ["LEVE=oui", "RESTE=", "ORIGINE=kit:sous"]),
                         p.stdout + p.stderr)

    def test_charger_paquet_ne_touche_pas_sys_path(self) -> None:
        """D10 : `sys.path` intact ; le `src/msvcrt.py` de l'adoptant ne gagne pas les `--help` réels."""
        p = self._vp("avant = list(sys.path)\nvp.charger_paquet(sys.argv[2], 'cadre')\n"
                     "print('INTACT=' + str(sys.path == avant))\n", str(self.adoptant))
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "INTACT=True"), p.stdout + p.stderr)
        if os.name == "nt":
            print(f"\nD10 non-vacuité SAUTÉE : `{HORS_STDLIB}` est intégré sous Windows, `src/` ne peut le masquer")
        else:  # non-vacuité : au rang d'`amorcer_cli`, ce `src/` gagne un module absent de la stdlib
            p = self._vp(f"vp.amorcer_cli(sys.argv[2], ('cadre',))\nimport {HORS_STDLIB}\n", str(self.adoptant))
            self.assertEqual((p.returncode, STDLIB in p.stderr), (95, True), p.stdout + p.stderr)
        for cli in ("project_init", "dashboard"):
            with self.subTest(cli=cli):
                fichier = str(self.adoptant / ".agents" / "bin" / CLIS[cli])
                p = subprocess.run([str(self.py), fichier, "--help"],
                                   capture_output=True, text=True, timeout=120, env=_env(), cwd=self.base)
                self.assertNotIn(STDLIB, p.stderr, f"{cli} : `src/{HORS_STDLIB}.py` a gagné\n{p.stderr}")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                # La jambe qui DISTINGUE pour `dashboard` (aucun de ses imports n'est empoisonnable, voir BORNE) :
                # `sys.path` relevé APRÈS le `--help` réel, joué en processus par `runpy`.
                p = subprocess.run([str(self.py), "-c", _APRES_HELP, fichier, str(self.adoptant / "src")],
                                   capture_output=True, text=True, timeout=120, env=_env(), cwd=self.base)
                self.assertEqual((p.returncode, p.stdout.strip().splitlines()[-1:]), (0, ["SRC_SUR_PATH=False"]),
                                 f"{cli} : `src/` est entré sur sys.path\n{p.stdout}{p.stderr}")


class ParentCadreTests(unittest.TestCase):
    """D3 : la règle recopiée dans `setup_projet` suit celle du résolveur."""

    def test_parent_cadre_suit_le_resolveur(self) -> None:
        setup = _charger("setup_projet_banc_vendor", HERE / "setup_projet.py")
        with tempfile.TemporaryDirectory(prefix="vendor_setup_d3_") as tmp:
            arbres = {"ancien": ("src",), "neuf": (".agents/vendor",), "les deux": ("src", ".agents/vendor"),
                      "neuf sans init": ("src", ".agents/vendor:vide"), "absent": ()}
            for nom, lieux in arbres.items():
                racine = (Path(tmp) / nom.replace(" ", "_")).resolve()
                for lieu in lieux:
                    dossier, _, vide = lieu.partition(":")
                    paquet = racine / dossier / "cadre"
                    paquet.mkdir(parents=True)
                    if not vide:
                        (paquet / "__init__.py").write_text("", encoding="utf-8")
                racine.mkdir(exist_ok=True)
                with self.subTest(arbre=nom):
                    self.assertEqual(setup._parent_cadre(racine), VP.parent_import(racine, "cadre"))
            self.assertEqual(setup._parent_cadre((Path(tmp) / "les_deux").resolve()),
                             (Path(tmp) / "les_deux" / ".agents" / "vendor").resolve(), "le neuf gagne")


_TEST_SONDE = '''
import os, sys

def test_sonde():
    import cadre
    chemins = [os.path.realpath(p) for p in sys.path if p]
    assert os.path.realpath({src!r}) in chemins, "le conftest n'a rien ajouté : témoin vide"
    assert cadre.ORIGINE == "adoptant", "le cadre du kit a gagné : " + cadre.ORIGINE
'''


class ConftestTests(unittest.TestCase):
    """D4 : chaque conftest, seul, ajoute EN QUEUE ; le `cadre` de l'adoptant gagne."""

    def _arbre(self, tmp: Path, conftest: str) -> Path:
        racine = tmp / "arbre"
        bin_ = racine / ".agents" / "bin"
        bin_.mkdir(parents=True)
        (racine / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        (racine / "src" / "cadre").mkdir(parents=True)
        (racine / "src" / "cadre" / "__init__.py").write_text('ORIGINE = "kit"\n', encoding="utf-8")
        shutil.copy(HERE / "vendor_paths.py", bin_ / "vendor_paths.py")
        if conftest == "racine":
            shutil.copy(REPO / "conftest.py", racine / "conftest.py")
            sonde = racine / "test_sonde_vendor.py"
        else:
            shutil.copy(HERE / "conftest.py", bin_ / "conftest.py")
            sonde = bin_ / "test_sonde_vendor.py"
        sonde.write_text(_TEST_SONDE.format(src=str(racine / "src")), encoding="utf-8")
        adoptant = tmp / "adoptant" / "cadre"
        adoptant.mkdir(parents=True)
        (adoptant / "__init__.py").write_text('ORIGINE = "adoptant"\n', encoding="utf-8")
        (tmp / "site").mkdir()
        (tmp / "site" / "cadre_adoptant.pth").write_text(str(tmp / "adoptant") + "\n", encoding="utf-8")
        return sonde

    def test_conftest_laisse_gagner_l_adoptant(self) -> None:
        code = "import site, sys; site.addsitedir(sys.argv[1]); import pytest; sys.exit(pytest.main(sys.argv[2:]))"
        for conftest in ("racine", "bin"):
            with self.subTest(conftest=conftest), tempfile.TemporaryDirectory(prefix="vendor_setup_d4_") as tmp:
                base = Path(tmp).resolve()
                sonde = self._arbre(base, conftest)
                p = subprocess.run([sys.executable, "-c", code, str(base / "site"), "-q", "-p", "no:cacheprovider",
                                    str(sonde)], capture_output=True, text=True, timeout=300, env=_env(),
                                   cwd=base / "arbre")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn("1 passed", p.stdout, p.stdout + p.stderr)


#: D12 : les surfaces de doctrine qui peuvent prescrire le moteur V3 (T-01M5BXTMT1, réserve C9).
DOCTRINE_V3 = ("AGENTS.md", ".github/copilot-instructions.md", "QUICK-SETUP.md")
#: D13 : surface -> forme racine qu'elle ne doit plus porter (le moteur vit sous `.agents/vendor/`).
RACINE_V3 = {".github/copilot-instructions.md": "(`agentic_v3/`)", "docs/usage.html": "<code>agentic_v3/</code>",
             ".agents/adopter-docs/docs/usage.html": "<code>agentic_v3/</code>"}
CLE_V3 = "-m agentic_v3"
# Bloc clos : ``` ou ~~~, indenté ou non, fermé par la MÊME clôture (\1).
_FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1", re.M | re.S)
_SPAN = re.compile(r"`[^`]+`")
# Fin de phrase (lue sur le texte MASQUÉ) : ponctuation, suivie des fermants `)]"'”»*_` puis d'un
# blanc ; paragraphe ; nouvel item de liste ; avant un titre Markdown ; et le titre seul fait phrase.
_FIN = re.compile(r"[.!?;][)\]\"'”»*_]*\s+|\n\s*\n|\n\s*(?:[-*]|\d+\.)\s|\n(?=[ \t]*#{1,6}\s)|^[ \t]*#{1,6}\s[^\n]*\n",
                  re.M)
_TIRET_P = re.compile(r"(?:^|\s)-P(?:\s|$)")


def _prescriptions(texte: str) -> list[tuple[str, str]]:
    """(span, phrase) de chaque `-m agentic_v3` : span backtické, ligne de bloc clos (span = phrase =
    la ligne), ou occurrence nue en prose (span vide : elle ne porte jamais la forme vendor)."""
    rendu: list[tuple[str, str]] = []
    masque = list(texte)
    for m in _FENCE.finditer(texte):
        rendu += [(ligne, ligne) for ligne in m.group(0).splitlines() if CLE_V3 in ligne]
        masque[m.start():m.end()] = "x" * (m.end() - m.start())
    spans = list(_SPAN.finditer("".join(masque)))
    for m in spans:
        masque[m.start():m.end()] = "x" * (m.end() - m.start())
    masque_s = "".join(masque)
    bornes = [0] + [f.end() for f in _FIN.finditer(masque_s)] + [len(texte)]

    def phrase(pos: int) -> str:
        debut = max(b for b in bornes if b <= pos)
        fin = min(b for b in bornes if b > pos)
        return texte[debut:fin]

    rendu += [(m.group(0), phrase(m.start())) for m in spans if CLE_V3 in m.group(0)]
    nue = masque_s.find(CLE_V3)
    while nue != -1:
        rendu.append(("", phrase(nue)))
        nue = masque_s.find(CLE_V3, nue + 1)
    return rendu


def _fautes_v3(texte: str) -> list[str]:
    """Les prescriptions sans la forme vendor (`PYTHONPATH=.agents/vendor` ET `-P` dans le span)
    dont la phrase ne dit pas non plus « at the root »."""
    return [f"{span or '(prose)'} | {phr.strip()[:200]}" for span, phr in _prescriptions(texte)
            if not ("PYTHONPATH=.agents/vendor" in span and _TIRET_P.search(span.strip("`")))
            and "at the root" not in phr]


class DoctrineV3Tests(unittest.TestCase):
    """D12 : chaque span qui prescrit `python -m agentic_v3` porte la forme vendor
    (`PYTHONPATH=.agents/vendor` et `-P`), ou SA phrase dit « at the root » ; AGENTS.md
    cite l'emplacement `.agents/vendor/agentic_v3/`. Mutants D (QUICK-SETUP) et E (AGENTS.md)
    rejoués en sous-tests. D13 : plus aucune surface ne place le moteur à la racine, et
    QUICK-SETUP fait retirer la copie racine (`git rm -r agentic_v3`) puis son dossier résiduel."""

    def _lire(self, rel: str) -> str | None:
        chemin = REPO / rel
        if not chemin.is_file():
            print(f"D12/D13 : {rel} absent de cet arbre, surface sautée")
            return None
        return chemin.read_text(encoding="utf-8")

    def test_python_m_agentic_v3_porte_la_forme_vendor(self) -> None:
        vus = 0
        for rel in DOCTRINE_V3:
            texte = self._lire(rel)
            if texte is None:
                continue
            vus += len(_prescriptions(texte))
            with self.subTest(fichier=rel):
                self.assertEqual(_fautes_v3(texte), [], f"{rel} : `python -m agentic_v3` sans la forme vendor")
        self.assertGreater(vus, 0, "aucune prescription relevée : le témoin passerait à vide")

    def test_mutants_d_et_e_rougissent(self) -> None:
        mutants = {"D": ("QUICK-SETUP.md", "Use `PYTHONPATH=.agents/vendor python3 -P -m agentic_v3`",
                         "Use `python3 -m agentic_v3`"),
                   "E": ("AGENTS.md", "`PYTHONPATH=.agents/vendor python -P -m agentic_v3 sync-spec` (Python ≥ 3.11; "
                         "`python -m agentic_v3 sync-spec` only while the engine sits at the root)",
                         "`python -m agentic_v3 sync-spec`")}
        for nom, (rel, avant, apres) in mutants.items():
            texte = self._lire(rel)
            if texte is None:
                continue
            with self.subTest(mutant=nom, fichier=rel):
                self.assertTrue(avant in texte, f"mutant {nom} : texte d'origine introuvable, mutant à vide")
                self.assertEqual(_fautes_v3(texte), [])
                self.assertNotEqual(_fautes_v3(texte.replace(avant, apres)), [], f"mutant {nom} survivant")

    def test_bornes_de_phrase_et_blocs_clos(self) -> None:
        """Chaque cas cache sa faute derrière un « at the root » VOISIN tant que la phrase ou
        le bloc est mal coupé : il doit être relevé."""
        cas = {"fermant après le point": "Copy it at the root (see below.) Then run `python -m agentic_v3` now.\n",
               "gras après le point": "Copy it **at the root.** Then run `python -m agentic_v3` now.\n",
               "titre avant la ligne": "## Copy at the root\n`python -m agentic_v3` runs it\n",
               "titre après la ligne": "`python -m agentic_v3` runs it\n## Copy at the root\n",
               "bloc ~~~": "The engine sits at the root here:\n~~~\npython -m agentic_v3\n~~~\n",
               "bloc indenté": "The engine sits at the root here:\n  ```\n  python -m agentic_v3\n  ```\n"}
        for nom, texte in cas.items():
            with self.subTest(cas=nom):
                self.assertNotEqual(_fautes_v3(texte), [], f"{nom} : faute masquée par la phrase voisine")

    def test_aucune_surface_ne_place_le_moteur_a_la_racine(self) -> None:
        for rel, forme in RACINE_V3.items():
            texte = self._lire(rel)
            if texte is not None:
                with self.subTest(fichier=rel):
                    self.assertFalse(forme in texte, f"{rel} place encore le moteur à la racine : {forme}")
        texte = self._lire("QUICK-SETUP.md")
        if texte is not None:
            self.assertTrue("(`git rm -r agentic_v3`)" in texte, "QUICK-SETUP ne fait plus retirer la copie racine")
            self.assertTrue("leftover `agentic_v3/` directory" in texte, "QUICK-SETUP oublie le dossier résiduel")
            self.assertIn(".agents/vendor/agentic_v3/", texte, "QUICK-SETUP ne cite plus l'emplacement vendor")

    def test_agents_md_cite_le_vendor(self) -> None:
        agents = REPO / "AGENTS.md"
        if not agents.is_file():
            self.skipTest("AGENTS.md absent de cet arbre")
        texte = agents.read_text(encoding="utf-8")
        self.assertTrue("`.agents/vendor/agentic_v3/`" in texte, "AGENTS.md ne cite pas le vendor")
        self.assertFalse("(`agentic_v3/`)" in texte, "AGENTS.md place encore le moteur à la racine")


if __name__ == "__main__":
    unittest.main()
