"""Bancs de la porte de push de l'ADOPTANT — T-00001183 (S-00004119), shard A.

Chaque témoin nomme son mutant dans sa docstring (« MUTANT <id> ») ; les
mutants porteurs sont REJOUÉS par le banc lui-même (`MutantsDurablesTests`) :
copie de la source, substitution textuelle, garde « mutation sans effet »,
scénario rejoué sur la copie, rouge asserté.

HERMÉTISME : tout git (fixtures et porte) tourne sous `GIT_CONFIG_GLOBAL` en
chemin ABSOLU (un relatif est ignoré en silence après `git -C`, réserve C1 du
critique) et `GIT_CONFIG_NOSYSTEM=1`, identité par `-c`. Le PATH de la porte
est fait de bouchons Python (gitleaks, semgrep, npm, pnpm, yarn) et de liens vers git,
bash et sh : un scanner « absent » l'est vraiment. Seul le témoin de fuite
réelle appelle le vrai gitleaks, et il saute EN LE DISANT s'il manque.

Les arbres sont des répertoires temporaires : aucune référence ancrée sur la
racine réelle au marqueur du kit ni à l'état local (étage A, témoin plus bas).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PORTE = ROOT / ".agents" / "bin" / "porte_adoptant.py"
DECOUVERTE = ROOT / ".agents" / "security" / "module_discovery.py"
RESULTAT = (".agents", "state", "local", "PORTE_RESULT")
MARQUEUR = (".agents", "IS_THE_KIT")
DEROGATIONS = ("CADRE_GARDES_DEGRADEES", "CADRE_SANS_MODULE", "CADRE_SANS_TEST")
GITLEAKS_REEL = shutil.which("gitleaks")
SEMGREP_REEL = shutil.which("semgrep")
REGLE_EVAL = ("rules:\n- id: banc-eval\n  pattern: eval(...)\n  message: eval du banc\n"
              "  languages: [python]\n  severity: ERROR\n")
ID = ("-c", "user.name=banc", "-c", "user.email=banc@test", "-c", "init.defaultBranch=main",
      "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always")
PYPROJECT_KIT = '[project]\nname = "cadre-kit"\ndependencies = []\n'
PYPROJECT_PROJET = '[project]\nname = "projet"\ndependencies = ["requests"]\n'
TEST_VERT = "def test_vert():\n    assert True\n"
MODULE_PY = {"requirements.txt": "", "test_ok.py": TEST_VERT}
MODULE_NPM = {"package.json": json.dumps({"name": "web", "scripts": {"test": "t"}}),
              "package-lock.json": "{}\n"}
VERROU_NPM = "{}\n"
SCRIPT_PROJET = "scripts/verify-projet.sh"
AVERT = "build et tests non vérifiés par le kit : ajoutez scripts/verify-projet.sh"
MODULE_PHP = {"composer.json": "{}\n", "src/App.php": "<?php\n"}  # aucune famille connue
AVERT_PHP = AVERT + " — manifeste(s) hors table : composer.json"  # les deux messages, UNE valeur
AVERT_HORS = ("manifeste(s) hors table ({}) : build et tests de cette partie non vérifiés par le kit : "
              "ajoutez scripts/verify-projet.sh")
# Dépôts MIXTES du binôme c4f3 ter : fable (le test PHP échouerait, npm racine vert) et opus.
MIXTE_FABLE = {"composer.json": "{}\n", "tests/ExampleTest.php": "<?php throw new Exception('ko');\n",
               "package.json": json.dumps({"scripts": {"test": "echo"}}), "package-lock.json": "{}\n"}
MIXTE_OPUS = {"go.mod": "module x\n", "tools/requirements.txt": "", "tools/test_ok.py": TEST_VERT}
ELAGUES = {"node_modules/x/composer.json": "{}\n", ".agents/y/go.mod": "", "build/Gemfile": ""}
REGLE_EVAL_SH = ("rules:\n- id: banc-eval-sh\n  pattern: eval \"$...ARGS\"\n  message: eval du banc\n"
                 "  languages: [bash]\n  severity: ERROR\n")
# Heredoc en CONDITION de `if` : tree-sitter-bash ne lit pas le fichier en entier
# (PartialParsing, rc 0 — mesuré sur semgrep 1.175.0), et l'`eval` y est invisible.
HEREDOC_SH = '#!/usr/bin/env bash\ncmd="$1"\nif cat <<EOF\nx\nEOF\nthen\n  :\nfi\neval "$cmd"\n'
ERREUR_PARTIELLE = json.dumps([{"type": ["PartialParsing", []], "path": "heredoc.sh", "level": "warn"}])


def charger(chemin: Path = PORTE):
    spec = importlib.util.spec_from_file_location("porte_adoptant_banc", str(chemin))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


porte_adoptant = charger()


def jeton_de_fuite() -> str:
    """Un jeton `ghp_` + 36 alphanumériques tiré À L'EXÉCUTION : aucun littéral
    dans ce fichier, que le gitleaks du dépôt lirait."""
    tirage = random.Random(1183)
    return "ghp_" + "".join(tirage.choice(string.ascii_letters + string.digits) for _ in range(36))


def bouchon_source(nom: str) -> str:
    return (f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "journal = os.environ.get('BANC_JOURNAL')\n"
            "if journal:\n"
            "    with open(journal, 'a', encoding='utf-8') as fh:\n"
            f"        fh.write(json.dumps({{'outil': {nom!r}, 'argv': sys.argv[1:], "
            "'cwd': os.getcwd()}) + '\\n')\n"
            # Le rapport JSON de semgrep : `errors` tirées de BANC_SEMGREP_ERREURS ;
            # BANC_SANS_RAPPORT = un scanner qui n'écrit pas son rapport.
            "for a in sys.argv[1:]:\n"
            "    if a.startswith('--json-output=') and not os.environ.get('BANC_SANS_RAPPORT'):\n"
            "        with open(a.split('=', 1)[1], 'w', encoding='utf-8') as fh:\n"
            "            fh.write(json.dumps({'results': [], 'errors': json.loads("
            "os.environ.get('BANC_SEMGREP_ERREURS', '[]'))}))\n"
            f"sys.exit(int(os.environ.get('BANC_RC_{nom.upper()}', '0')))\n")


class _Banc(unittest.TestCase):
    """Un dossier jetable par test : sources des sous-modules, arbre adoptant,
    bouchons, journal des appels."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="porte-banc-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("", encoding="utf-8")
        self.bouchons = self.tmp / "bouchons"
        self.outils = self.tmp / "outils"
        self.sources = self.tmp / "sources"
        for dossier in (self.bouchons, self.outils, self.sources):
            dossier.mkdir()
        # T-01M4JC50S6CTJ5HJ697929E6NB : `uname` et `security` rejoignent le PATH hermétique — le semgrep
        # RÉEL (1.172.0, Homebrew macOS) lance `uname -s` puis `security find-certificate`
        # à son démarrage pour son magasin X509 (ca-certs) et meurt rc 2 sans eux
        # (« run ['uname' '-s']: No such file or directory »). `security` n'existe que
        # sur macOS : absent ailleurs, rien n'est lié (mesuré macOS ; Linux assumé).
        for nom in ("git", "bash", "sh", "uname", "security"):
            cible = shutil.which(nom)
            if cible:
                os.symlink(cible, self.outils / nom)
        self.journal = self.tmp / "journal.jsonl"
        self.bouchon("gitleaks")
        self.bouchon("semgrep")

    # --- outillage -----------------------------------------------------------
    def bouchon(self, nom: str) -> None:
        chemin = self.bouchons / nom
        chemin.write_text(bouchon_source(nom), encoding="utf-8")
        chemin.chmod(0o755)

    def env(self, hermetique: bool = True, **extra: str) -> dict[str, str]:
        """PATH hermétique pour la PORTE (bouchons + git, bash, sh) ; les git de
        fixture gardent le PATH du poste (`git submodule` est un script qui
        appelle sed, basename, uname), la config git restant jetable."""
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "BANC_")) and k not in DEROGATIONS
               and k not in ("CADRE_SEMGREP_BASE", "PORTE_ADOPTANT_EN_COURS")}
        env.update(GIT_CONFIG_GLOBAL=str(self.gitconfig), GIT_CONFIG_NOSYSTEM="1",
                   BANC_JOURNAL=str(self.journal))
        if hermetique:
            env["PATH"] = os.pathsep.join([str(self.bouchons), str(self.outils)])
        env.update(extra)
        return env

    def git(self, depot: Path, *args: str) -> str:
        p = subprocess.run(["git", *ID, "-C", str(depot), *args], env=self.env(False),
                           capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(p.returncode, 0, f"git {args} : {p.stderr}")
        return p.stdout

    @staticmethod
    def ecrire(racine: Path, fichiers: dict) -> None:
        for rel, texte in fichiers.items():
            if texte is None:
                continue
            chemin = racine / rel
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(texte, encoding="utf-8")

    def depot(self, chemin: Path, fichiers: dict, executables=()) -> Path:
        chemin.mkdir(parents=True, exist_ok=True)
        self.git(chemin, "init", "-q")
        self.ecrire(chemin, fichiers)
        self.git(chemin, "add", "-A")
        for rel in executables:
            self.git(chemin, "update-index", "--chmod=+x", "--", rel)
        self.git(chemin, "commit", "-q", "-m", "init")
        return chemin

    def adoptant(self, fichiers: dict | None = None, executables=(), pre_push_x: bool = True) -> Path:
        base = {
            ".agents/security/module_discovery.py": DECOUVERTE.read_text(encoding="utf-8"),
            ".agents/security/semgrep.yml": "rules: []\n",
            ".githooks/pre-push": "#!/usr/bin/env bash\nexit 0\n",
            "pyproject.toml": PYPROJECT_KIT,
        }
        base.update(fichiers or {})
        x = (".githooks/pre-push",) if pre_push_x else ()
        return self.depot(self.tmp / "adoptant", base, x + tuple(executables))

    def sous_module(self, arbre: Path, chemin: str, fichiers: dict,
                    imbrique: tuple[str, dict] | None = None) -> None:
        source = self.depot(self.sources / chemin.replace("/", "__"), fichiers)
        if imbrique is not None:
            sous = self.depot(self.sources / (chemin + "__" + imbrique[0]), imbrique[1])
            self.git(source, "submodule", "add", "-q", str(sous), imbrique[0])
            self.git(source, "commit", "-q", "-m", "imbrique")
        self.git(arbre, "submodule", "add", "-q", str(source), chemin)
        self.git(arbre, "submodule", "update", "--init", "--recursive", "-q")
        self.git(arbre, "commit", "-q", "-m", f"sous-module {chemin}")

    def lancer(self, arbre: Path, *args: str, porte: Path = PORTE, **env: str):
        p = subprocess.run([sys.executable, str(porte), "--root", str(arbre), *args],
                           env=self.env(**env), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600,
                           cwd=str(self.tmp), check=False)
        return p.returncode, p.stdout + p.stderr, self.resultat(arbre)

    @staticmethod
    def resultat(arbre: Path) -> dict | None:
        chemin = arbre.joinpath(*RESULTAT)
        if not chemin.is_file():
            return None
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        return dict(ligne.split("=", 1) for ligne in lignes if "=" in ligne)

    def appels(self, outil: str) -> list[dict]:
        if not self.journal.is_file():
            return []
        lignes = self.journal.read_text(encoding="utf-8").splitlines()
        return [a for a in (json.loads(x) for x in lignes) if a["outil"] == outil]

    def nominal(self) -> Path:
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        self.sous_module(arbre, "m2", MODULE_PY, imbrique=("m3", MODULE_PY))
        return arbre


# =============================================================================
class ContratTests(_Banc):
    """Le contrat A↔B : rc, règle de porte, canal PORTE_RESULT, `--liste`."""

    def test_nominal_vert_et_canal_de_retour(self):
        """MUTANT C-SHA (sha= vide ou d'un autre arbre), C-MOD (modules= non trié,
        sans le module imbriqué), C-REC (récursion des sous-modules retirée : les
        gardes ne voient plus m2/m3)."""
        arbre = self.nominal()
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(res["sha"], self.git(arbre, "rev-parse", "HEAD").strip())
        self.assertEqual(res["verdict"], "OK")
        self.assertEqual(res["modules"], "m1,m2,m2/m3")
        self.assertEqual([k for k in res if k.startswith("derogation_")], [])
        self.assertIn("porte : ADOPTANT", sortie)
        self.assertIn("écarté : ./pyproject.toml — distribution cadre-kit", sortie)
        self.assertIn("=== PORTE ADOPTANT OK", sortie)
        racines = {Path(a["cwd"]).resolve() for a in self.appels("semgrep")}
        self.assertEqual(racines, {arbre, arbre / "m1", arbre / "m2", arbre / "m2" / "m3"})
        self.assertEqual(len(self.appels("gitleaks")), 4)

    def test_un_resultat_perime_ne_survit_a_aucun_refus(self):
        """MUTANT C-PERIME (suppression déplacée après la validation des
        dérogations ou la règle) : un `verdict=OK` périmé survit à un rc 2."""
        arbre = self.adoptant()
        perime = arbre.joinpath(*RESULTAT)
        for env, extra in (({"CADRE_SANS_TEST": "\x01\x02"}, {}),
                           ({}, {".agents/IS_THE_KIT": ""})):
            self.ecrire(arbre, extra)
            perime.parent.mkdir(parents=True, exist_ok=True)
            perime.write_text("sha=x\nverdict=OK\nmodules=m1\n", encoding="utf-8")
            rc, sortie, res = self.lancer(arbre, **env)
            self.assertEqual(rc, 2, sortie)
            self.assertIsNone(res, sortie)

    def test_regle_au_marqueur_seul(self):
        """MUTANT C-REGLE (règle lue sur le nom du pyproject, ou marqueur ignoré) :
        un arbre `cadre-kit` sans marqueur cesse d'être adoptant, ou le kit l'est."""
        arbre = self.adoptant({".agents/IS_THE_KIT": "", "pyproject.toml": PYPROJECT_PROJET})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual((rc, res), (2, None), sortie)
        self.assertIn("porte : KIT", sortie)
        self.assertEqual(self.appels("gitleaks"), [])
        shutil.rmtree(arbre)
        arbre = self.adoptant({".agents/security/module_discovery.py": None})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 2, sortie)
        self.assertIn("porte : AUCUNE", sortie)
        shutil.rmtree(arbre)
        arbre = self.adoptant(MODULE_NPM | {"pyproject.toml": PYPROJECT_KIT})
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("porte : ADOPTANT (.agents/IS_THE_KIT absent", sortie)

    def test_liste_n_execute_rien(self):
        """MUTANT C-LISTE (`--liste` retombe dans la porte) : scanners appelés,
        pytest joué, PORTE_RESULT écrit."""
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        rc, sortie, res = self.lancer(arbre, "--liste")
        self.assertEqual(rc, 0, sortie)
        self.assertIn("gardé : m1 [python]", sortie)
        self.assertIn("écarté : ./pyproject.toml", sortie)
        self.assertIsNone(res)
        self.assertFalse(self.journal.exists(), "un scanner a été appelé sous --liste")
        self.assertNotIn("passed", sortie)

    def test_cle_de_derogation_ecrite_seulement_si_appliquee(self):
        """MUTANT C-CLE (clé écrite dès que la variable est posée) : le pre-push
        imprimerait une dérogation qui n'a rien couvert."""
        arbre = self.nominal()
        rc, sortie, res = self.lancer(arbre, CADRE_SANS_TEST="raison", CADRE_SANS_MODULE="raison",
                                      CADRE_GARDES_DEGRADEES="raison")
        self.assertEqual(rc, 0, sortie)
        self.assertEqual([k for k in res if k.startswith("derogation_")], [])

    def test_refus_d_usage_rc_2(self):
        """MUTANT C-USAGE (raison vide ou drapeau acceptée) : une dérogation
        muette passerait pour une raison."""
        arbre = self.adoptant()
        self.assertEqual(self.lancer(self.tmp / "absent")[0], 2)
        self.assertEqual(self.lancer(arbre, "--inconnu")[0], 2)
        for valeur in ("1", "oui", "", "\x01\t"):
            rc, sortie, res = self.lancer(arbre, CADRE_SANS_MODULE=valeur)
            self.assertEqual((rc, res), (2, None), f"{valeur!r} : {sortie}")


# =============================================================================
class SousModulesTests(_Banc):
    """Les gitlinks de l'index : jamais un « aucun module » silencieux."""

    def test_gitlink_non_peuple_nomme_et_rouge(self):
        """MUTANT S-NP (ligne retirée ; rejoué par MutantsDurablesTests) : la porte
        rend « aucun module » sans nommer la cause."""
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        self.git(arbre, "submodule", "deinit", "-f", "-q", "m1")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("sous-module non peuplé : m1", sortie)
        self.assertEqual(res["verdict"], "ECHEC")

    def test_gitlink_sans_entree_gitmodules(self):
        """MUTANT S-GM (sous-modules lus dans `.gitmodules` ou par `submodule
        status`) : un dépôt embarqué par erreur échappe à la porte."""
        arbre = self.adoptant(MODULE_NPM)
        self.bouchon("npm")
        sha = self.git(arbre, "rev-parse", "HEAD").strip()
        self.git(arbre, "update-index", "--add", "--cacheinfo", f"160000,{sha},emb")
        self.git(arbre, "commit", "-q", "-m", "gitlink sans .gitmodules")
        self.assertFalse((arbre / ".gitmodules").exists())
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("sous-module non peuplé : emb", sortie)

    def test_sous_module_desaligne(self):
        """MUTANT S-HEAD (HEAD du module non comparé au gitlink)."""
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        self.git(arbre / "m1", "commit", "-q", "--allow-empty", "-m", "dérive")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("sous-module désaligné : m1", sortie)

    def test_sous_module_modifie(self):
        """MUTANT S-ETAT (modifications suivies du module ignorées)."""
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        (arbre / "m1" / "test_ok.py").write_text(TEST_VERT + "\n", encoding="utf-8")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("sous-module modifié : m1", sortie)


# =============================================================================
class ModulesTests(_Banc):
    """Découverte, dépôt propriétaire, racine `cadre-kit`, défauts ROUGES."""

    def test_manifeste_dans_un_sous_module_garde_et_construit(self):
        """MUTANT M-LS (filtre par le seul `ls-files` du superprojet ; rejoué par
        MutantsDurablesTests) : le gitlink cache le manifeste, « aucun module »."""
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("gardé : m1 [python]", sortie)
        self.assertIn("1 passed", sortie)
        self.assertEqual(res["modules"], "m1")

    def test_manifeste_non_suivi_ecarte(self):
        """MUTANT M-SUIVI (filtre de suivi retiré) : `.next/standalone` devient un
        module et npm y tourne."""
        arbre = self.adoptant({"web/" + k: v for k, v in MODULE_NPM.items()})
        self.bouchon("npm")
        self.ecrire(arbre, {"web/.next/standalone/package.json": "{}"})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("écarté : web/.next/standalone [npm] — manifeste non suivi", sortie)
        self.assertEqual(res["modules"], "web")
        self.assertEqual({Path(a["cwd"]).resolve() for a in self.appels("npm")}, {arbre / "web"})

    def test_racine_cadre_kit_ecartee_racine_a_dependances_gardee(self):
        """MUTANT M-KIT (exclusion retirée, ou décidée sur le nom seul) : la racine
        du kit devient un module, ou une vraie racine `cadre-kit` est perdue."""
        for pyproject, attendu in ((PYPROJECT_KIT, False), (PYPROJECT_PROJET, True),
                                   (PYPROJECT_KIT.replace("[]", '["x"]'), True)):
            arbre = self.adoptant({"pyproject.toml": pyproject, "test_r.py": TEST_VERT})
            rc, sortie, _res = self.lancer(arbre, "--liste")
            self.assertEqual(rc, 0, sortie)
            self.assertEqual("gardé : . [python]" in sortie, attendu, sortie)
            self.assertEqual("écarté : ./pyproject.toml" in sortie, not attendu, sortie)
            shutil.rmtree(arbre)

    def test_outillage_du_kit_sous_agents_jamais_un_module(self):
        """Le kit privé de son marqueur (PLAN_DRIFT, décision de l'orchestrateur) :
        `.agents/ui-src` est découvert (`AGENTS_KEEP`) mais n'est JAMAIS un module
        du projet — aucun module : vert AVEC avertissement (S-00004278), npm jamais
        lancé. MUTANT M-AGENTS (exclusion retirée ; rejoué par MutantsDurablesTests) :
        ui-src gardé, npm joué, `modules=.agents/ui-src`."""
        arbre = self.adoptant({".agents/ui-src/package.json": MODULE_NPM["package.json"],
                               ".agents/ui-src/package-lock.json": VERROU_NPM})
        self.bouchon("npm")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("écarté : .agents/ui-src — outillage du kit", sortie)
        self.assertEqual((res["verdict"], res["modules"], res["avertissement"]), ("OK", "", AVERT))
        self.assertEqual(self.appels("npm"), [])

    def test_sans_module_ni_script_vert_et_avertissement(self):
        """S-00004278 (3) : un adoptant PHP (composer.json seul, aucune famille connue),
        sans script : VERT, avertissement imprimé ET écrit au résultat — fusionné avec le
        manifeste hors table en UNE valeur (binôme c4f3 ter) ; CADRE_SANS_MODULE lue, sans
        objet, sans clé. MUTANT M-AVERT (avertissement tu), M-AUCUN (le rouge d'avant
        rétabli) et H-FUSION (composer.json tu) : rejoués par MutantsDurablesTests."""
        arbre = self.adoptant(MODULE_PHP)
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual((res["verdict"], res["modules"], res["avertissement"]), ("OK", "", AVERT_PHP))
        self.assertIn(f"AVERTISSEMENT : aucun module de famille connue (npm, python, java, swift) ni "
                      f"script du projet — {AVERT}", sortie)
        self.assertIn(f"avertissement : {AVERT_PHP}\n", sortie)
        rc, sortie, res = self.lancer(arbre, CADRE_SANS_MODULE="dépôt PHP")
        self.assertEqual(rc, 0, sortie)
        self.assertEqual([k for k in res if k.startswith("derogation_")], [])
        self.assertIn("CADRE_SANS_MODULE posée : sans objet (S-00004278)", sortie)

    def test_sans_module_les_gardes_bloquent(self):
        """S-00004278 : sans module, les gardes jugent SEULES et restent bloquantes — un
        secret ou un finding semgrep neuf est ROUGE. MUTANT M-GARDES (gardes sautées sans
        module ; rejoué)."""
        arbre = self.adoptant(MODULE_PHP)
        for variable, code, vu in (("BANC_RC_GITLEAKS", "7", "gitleaks : TROUVAILLE sur racine"),
                                   ("BANC_RC_SEMGREP", "1", "semgrep : TROUVAILLE sur racine")):
            rc, sortie, res = self.lancer(arbre, **{variable: code})
            self.assertEqual((rc, res["verdict"]), (1, "ECHEC"), sortie)
            self.assertIn(vu, sortie)

    def test_module_sans_test_rouge_puis_sortie_tracee(self):
        """MUTANT M-RC5 (pytest rc 5 non bloquant) ; MUTANT M-NPMTEST (script
        `test` absent non bloquant) ; MUTANT M-ASCII (filtre ASCII des raisons) : la
        raison accentuée arrive tronquée."""
        arbre = self.adoptant({"web/package.json": json.dumps({"scripts": {"build": "b"}}),
                               "web/package-lock.json": VERROU_NPM,
                               "py/requirements.txt": "", "py/vide.py": "X = 1\n"})
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("module sans test : web [npm]", sortie)
        self.assertIn("module sans test : py [python] — pytest rc 5", sortie)
        rc, sortie, res = self.lancer(arbre, CADRE_SANS_TEST="prototype, été\t")
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(res["derogation_test"], "prototype, été")

    def test_test_casse_rouge(self):
        """MUTANT M-RC (rc de pytest ignoré)."""
        arbre = self.adoptant({"py/requirements.txt": "",
                               "py/test_ko.py": "def test_ko():\n    assert False\n"})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("pytest a échoué sur py", sortie)
        self.assertEqual(res["verdict"], "ECHEC")

    def test_chaine_d_outils_absente_et_enveloppe_java(self):
        """MUTANT M-OUTIL (outil absent non bloquant) ; MUTANT M-JAVA (src/test des
        repliés ignoré, ou enveloppe absente tolérée)."""
        arbre = self.adoptant({"jv/build.gradle": "", "jv/gradlew": "exit 0\n",
                               "jv/src/test/T.java": "", "nu/build.gradle": "",
                               "jr/build.gradle": "", "jr/gradlew": "exit 0\n",
                               "jr/lib/build.gradle": "", "jr/lib/src/test/T.java": "",
                               "web/package.json": MODULE_NPM["package.json"],
                               "web/package-lock.json": VERROU_NPM},
                              executables=("jv/gradlew", "jr/gradlew"))
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("$ sh ./gradlew build --no-daemon", sortie)
        self.assertNotIn("sur jv", sortie)
        self.assertNotIn("module sans test : jv", sortie)
        self.assertIn("gardé : jr [java]", sortie)
        self.assertNotIn("gardé : jr/lib", sortie)
        self.assertNotIn("module sans test : jr", sortie)
        self.assertIn("gradlew absent de nu", sortie)
        self.assertIn("npm absent du PATH : module web", sortie)


# =============================================================================
SCRIPT_SOURCE = ("#!/usr/bin/env bash\n"
                 "[ -f .agents/security/module_discovery.py ] || exit 8\n"
                 "[ -z \"${GIT_DIR+x}\" ] || exit 9\n"
                 "exit \"${BANC_SCRIPT_RC:-0}\"\n")


class GestionnairesTests(_Banc):
    """npm : le VERROU choisit le gestionnaire et son install (décision S-00004250, 1)."""

    def racine_npm(self, *verrous: str) -> Path:
        fichiers = {"package.json": json.dumps({"name": "r", "scripts": {"test": "t"}})}
        fichiers.update({v: "x\n" for v in verrous})
        return self.adoptant(fichiers)

    def test_pnpm_choisi_par_son_verrou(self):
        """MUTANT V-PNPM (pnpm-lock.yaml lu comme un verrou npm ; rejoué par
        MutantsDurablesTests) : `npm ci` sur un projet pnpm, l'EUSAGE de lavande."""
        arbre = self.racine_npm("pnpm-lock.yaml")
        self.bouchon("pnpm")
        self.bouchon("npm")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual([a["argv"] for a in self.appels("pnpm")], [["install", "--frozen-lockfile"], ["run", "test"]])
        self.assertEqual(self.appels("npm"), [])
        self.assertEqual(res["modules"], ".")

    def test_yarn_et_npm_choisis_par_leur_verrou(self):
        """MUTANT V-TABLE (une ligne de la table retirée ou permutée)."""
        for verrou, outil, install in (("yarn.lock", "yarn", ["install", "--frozen-lockfile"]),
                                       ("package-lock.json", "npm", ["ci"]),
                                       ("npm-shrinkwrap.json", "npm", ["ci"])):
            with self.subTest(verrou=verrou):
                self.journal.unlink(missing_ok=True)
                arbre = self.racine_npm(verrou)
                for nom in ("pnpm", "yarn", "npm"):
                    self.bouchon(nom)
                rc, sortie, _res = self.lancer(arbre)
                self.assertEqual(rc, 0, sortie)
                self.assertEqual([a["argv"] for a in self.appels(outil)], [install, ["run", "test"]])
                autres = [a for nom in ("pnpm", "yarn", "npm") if nom != outil for a in self.appels(nom)]
                self.assertEqual(autres, [])
                shutil.rmtree(arbre)

    def test_aucun_lockfile_rouge_nomme(self):
        """MUTANT V-SANS (repli sur `npm install` sans verrou ; rejoué)."""
        arbre = self.racine_npm()
        self.bouchon("npm")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("aucun lockfile : la porte n'installe pas sans verrou — module .", sortie)
        self.assertEqual(self.appels("npm"), [])
        self.assertEqual(res["verdict"], "ECHEC")

    def test_gestionnaire_absent_rouge_nomme(self):
        """MUTANT V-ABSENT (gestionnaire absent remplacé par npm)."""
        arbre = self.racine_npm("pnpm-lock.yaml")
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("pnpm absent du PATH : module . non construit (verrou pnpm-lock.yaml)", sortie)
        self.assertEqual(self.appels("npm"), [])

    def test_plusieurs_verrous_precedence_imprimee_et_echec_nomme(self):
        """La précédence est DITE ; l'échec de l'install nomme son gestionnaire."""
        arbre = self.racine_npm("pnpm-lock.yaml", "package-lock.json")
        self.bouchon("pnpm")
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre, BANC_RC_PNPM="1")
        self.assertEqual(rc, 1, sortie)
        self.assertIn("plusieurs verrous dans . (pnpm-lock.yaml, package-lock.json) : pnpm-lock.yaml retenu "
                      "(précédence pnpm, yarn, npm)", sortie)
        self.assertIn("pnpm install --frozen-lockfile a échoué sur . (rc 1)", sortie)
        self.assertEqual(self.appels("npm"), [])


SCRIPT_REENTRANT = ("#!/usr/bin/env bash\n"
                    "n=\"${BANC_PROFONDEUR:-0}\"\n"
                    "if [ \"$n\" -ge 2 ]; then echo \"BANC RECURSION $n\"; exit 0; fi\n"
                    "BANC_PROFONDEUR=$((n + 1)) exec \"$BANC_PYTHON\" \"$BANC_PORTE\" --root \"$(pwd)\"\n")


class ScriptDuProjetTests(_Banc):
    """`scripts/verify-projet.sh`, suivi par git : il fait foi pour TOUT le dépôt
    (S-00004250, 1 ; portée S-00004278)."""

    def test_script_suivi_fait_foi_et_remplace_la_sequence(self):
        """MUTANT S-SCRIPT (script ignoré : la séquence par défaut joue et VERDIT ;
        rejoué par MutantsDurablesTests)."""
        arbre = self.adoptant(MODULE_NPM | {SCRIPT_PROJET: SCRIPT_SOURCE})
        self.bouchon("npm")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("script du projet : scripts/verify-projet.sh (suivi par git) — il fait foi pour "
                      "TOUT le dépôt (S-00004278)", sortie)  # fable T3 : plus « le module racine »
        self.assertIn("=== script du projet — il fait foi pour TOUT le dépôt, aucune séquence par défaut "
                      "(modules découverts : . [npm])", sortie)
        self.assertEqual(self.appels("npm"), [])
        self.assertEqual(res["modules"], ".")
        rc, sortie, res = self.lancer(arbre, BANC_SCRIPT_RC="3")
        self.assertEqual(rc, 1, sortie)
        self.assertIn("scripts/verify-projet.sh a échoué sur . (rc 3)", sortie)
        self.assertEqual(res["verdict"], "ECHEC")

    def test_script_sans_manifeste_fait_foi_jamais_aucun_module(self):
        """Aucun manifeste : le script fait foi pour TOUT le dépôt (`modules=.`), jamais « aucun module »."""
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertNotIn("aucun module", sortie)
        self.assertEqual(res["modules"], ".")
        rc, sortie, _res = self.lancer(arbre, "--liste")
        self.assertEqual(rc, 0, sortie)
        self.assertIn("script du projet : scripts/verify-projet.sh", sortie)
        self.assertNotIn("aucun module gardé", sortie)

    def test_script_fait_foi_pour_tout_le_depot(self):
        """S-00004278 (1) : script + module npm IMBRIQUÉ cassé (sans verrou) : seul le
        script joue, vert ; les gardes restent jouées et bloquantes. MUTANT S-PORTEE (la
        séquence par défaut joue aussi après le script ; rejoué) : « aucun lockfile », ROUGE."""
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE, "web/package.json": MODULE_NPM["package.json"]})
        self.bouchon("npm")
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("gardé : web [npm] — couvert par scripts/verify-projet.sh", sortie)
        self.assertIn("(modules découverts : web [npm])", sortie)
        self.assertEqual((self.appels("npm"), res["modules"]), ([], "."))
        self.assertNotIn("avertissement", res)
        self.assertTrue(self.appels("semgrep"), "les gardes n'ont pas joué")
        rc, sortie, _res = self.lancer(arbre, BANC_RC_SEMGREP="1")
        self.assertEqual(rc, 1, sortie)
        self.assertIn("semgrep : TROUVAILLE sur racine", sortie)

    def test_script_non_suivi_ecarte_sequence_par_defaut(self):
        """MUTANT S-SUIVI (script non suivi exécuté ; rejoué) : il sort 7, la porte rougirait —
        avec un module (2) comme sans module (3, vert + avertissement)."""
        arbre = self.adoptant(MODULE_NPM)
        self.ecrire(arbre, {SCRIPT_PROJET: "#!/usr/bin/env bash\nexit 7\n"})
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("écarté : scripts/verify-projet.sh — non suivi par git", sortie)
        self.assertEqual([a["argv"][0] for a in self.appels("npm")], ["ci", "run"])
        shutil.rmtree(arbre)
        arbre = self.adoptant(MODULE_PHP)
        self.ecrire(arbre, {SCRIPT_PROJET: "#!/usr/bin/env bash\nexit 7\n"})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual((rc, res["avertissement"]), (0, AVERT_PHP), sortie)

    def test_reentrance_rouge_nommee(self):
        """fable F4 : un script qui rappelle la porte ne boucle pas — la porte imbriquée
        rend ROUGE, nommée. MUTANT R-GARDE (garde retirée ; rejoué) : la récursion n'est
        arrêtée que par le compteur du banc (« BANC RECURSION 2 »)."""
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_REENTRANT})
        rc, sortie, _res = self.lancer(arbre, BANC_PYTHON=sys.executable, BANC_PORTE=str(PORTE))
        self.assertEqual(rc, 1, sortie)
        self.assertIn("ROUGE : réentrance — la porte adoptant tourne déjà (PORTE_ADOPTANT_EN_COURS", sortie)
        self.assertIn("scripts/verify-projet.sh a échoué sur . (rc 1)", sortie)
        self.assertNotIn("BANC RECURSION", sortie)

    def test_cwd_racine_et_environnement_purge(self):
        """MUTANT S-ENV (environnement hérité : `GIT_DIR` atteint le script, sortie 9 ;
        rejoué) ; MUTANT S-CWD (cwd hors de la racine : sortie 8)."""
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE})
        rc, sortie, _res = self.lancer(arbre, GIT_DIR=str(self.tmp / "ailleurs"))
        self.assertEqual(rc, 0, sortie)


class HorsTableTests(_Banc):
    """Dépôt MIXTE (binôme c4f3 ter, fable et opus) : un manifeste SUIVI hors de la table
    est NOMMÉ dans l'avertissement, sans script ; jamais un refus, aucun rc ne change."""

    def test_depot_mixte_vert_et_avertissement_nomme(self):
        """fable : `gardé : . [npm]`, le test PHP jamais joué ; opus : seul `tools` python
        gardé. VERT, le manifeste NOMMÉ au résultat, imprimé, et sous `--liste`. MUTANT
        H-TU (détection vidée ; rejoué) : vert SANS avertissement, le défaut mesuré."""
        self.bouchon("npm")
        for fichiers, nom, modules in ((MIXTE_FABLE, "composer.json", "."), (MIXTE_OPUS, "go.mod", "tools")):
            arbre = self.adoptant(fichiers)
            rc, sortie, res = self.lancer(arbre)
            attendu = AVERT_HORS.format(nom)
            self.assertEqual((rc, res["verdict"], res["modules"], res.get("avertissement")),
                             (0, "OK", modules, attendu), sortie)
            self.assertIn(f"avertissement : {attendu}\n", sortie)
            self.assertIn(attendu, self.lancer(arbre, "--liste")[1])
            shutil.rmtree(arbre)

    def test_script_suivi_js_pur_non_suivi_elague_aucun_avertissement(self):
        """Script SUIVI (il fait foi ; MUTANT H-SCRIPT), adoptant JS pur, manifeste NON
        suivi (MUTANT H-SUIVI : `-c -o`), manifestes sous node_modules, .agents, build
        (MUTANT H-ELAGUE : élagage retiré) : aucun avertissement. Mutants rejoués."""
        self.bouchon("npm")
        for fichiers, apres in ((MIXTE_FABLE | {SCRIPT_PROJET: SCRIPT_SOURCE}, {}), (MODULE_NPM, {}),
                                (MODULE_NPM, {"composer.json": "{}\n"}), (MODULE_NPM | ELAGUES, {})):
            arbre = self.adoptant(fichiers)
            self.ecrire(arbre, apres)
            rc, sortie, res = self.lancer(arbre)
            self.assertEqual((rc, res.get("avertissement")), (0, None), sortie)
            self.assertNotIn("hors table", self.lancer(arbre, "--liste")[1])
            shutil.rmtree(arbre)

    def test_sous_module_lu_par_son_index_et_liste_bornee(self):
        """Un sous-module peuplé est lu par SON index (MUTANT H-SOUS : racine seule) ; 12
        manifestes : 10 nommés, le reste compté, la borne DITE (MUTANT H-BORNE). Rejoués."""
        arbre = self.adoptant({f"s{i:02d}/Cargo.toml": "" for i in range(11)})
        self.sous_module(arbre, "m1", MODULE_PY | {"composer.json": "{}\n"})
        rc, sortie, res = self.lancer(arbre)
        noms = ", ".join(["m1/composer.json"] + [f"s{i:02d}/Cargo.toml" for i in range(9)])
        attendu = AVERT_HORS.format(noms + " … (+2 ; borne : 10 noms)")
        self.assertEqual((rc, res["modules"], res.get("avertissement")), (0, "m1", attendu), sortie)


# =============================================================================
class PytestTests(_Banc):
    """La config pytest PROPRE du module, `-c`, `--confcutdir`, `--ignore`."""

    def test_C1a_b_test_seul_sous_le_pytest_ini_du_kit(self):
        """MUTANT P-C (`-c` retiré) : le pytest.ini du kit l'emporte, `b_test.py`
        n'est pas collecté, rc 5."""
        arbre = self.adoptant({"pytest.ini": "[pytest]\npython_files = test_*.py\n",
                               "py/requirements.txt": "", "py/b_test.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("1 passed", sortie)

    def test_C1b_module_racine_ne_joue_pas_la_plomberie_du_kit(self):
        """MUTANT P-C (`-c` retiré : `testpaths` du pytest.ini du kit) ; MUTANT P-V3
        (`agentic_v3` retiré de norecursedirs)."""
        rouge = "def test_rouge():\n    assert False\n"
        arbre = self.adoptant({
            "pyproject.toml": PYPROJECT_PROJET, "test_racine.py": TEST_VERT,
            "pytest.ini": "[pytest]\ntestpaths = .agents agentic_v3\n",
            ".agents/evals/test_plomberie.py": rouge, "agentic_v3/test_v3.py": rouge,
            ".agents/vendor/agentic_v3/test_v3.py": rouge})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("gardé : . [python]", sortie)
        self.assertIn("1 passed", sortie)

    def test_C1b_vendor_seul_n_est_pas_collecte(self):
        """Le moteur déplacé sous `.agents/` reste hors des tests adoptants."""
        rouge = "def test_rouge():\n    assert False\n"
        arbre = self.adoptant({
            "pyproject.toml": PYPROJECT_PROJET, "test_racine.py": TEST_VERT,
            ".agents/vendor/agentic_v3/test_v3.py": rouge})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("1 passed", sortie)

    def test_C1c_modules_freres_non_collectes(self):
        """MUTANT P-IGNORE (`--ignore` des modules descendants retiré) : la racine
        collecte `m1/test_meme.py`, « import file mismatch », rc 2."""
        arbre = self.adoptant({"pyproject.toml": PYPROJECT_PROJET, "test_meme.py": TEST_VERT,
                               "m1/requirements.txt": "", "m1/test_meme.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(sortie.count("1 passed"), 2, sortie)

    def test_C1d_tox_avant_un_pyproject_sans_section(self):
        """MUTANT P-PYPROJECT (pyproject retenu sans section pytest) : `check_x.py`
        n'est pas collecté, rc 5."""
        arbre = self.adoptant({"py/tox.ini": "[pytest]\npython_files = check_*.py\n",
                               "py/pyproject.toml": '[project]\nname = "py"\n',
                               "py/check_x.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("config pytest : py/tox.ini", sortie)
        self.assertIn("1 passed", sortie)

    def test_C1e_conftest_de_la_racine_invisible_au_module(self):
        """MUTANT P-CONFCUT (`--confcutdir` retiré) : le conftest racine piégé est
        chargé, le test du module échoue."""
        piege = ("import pytest\n\n\n" "@pytest.fixture(autouse=True)\ndef _piege():\n"
                 "    raise RuntimeError('conftest racine visible')\n")
        arbre = self.adoptant({"conftest.py": piege, "py/requirements.txt": "",
                               "py/test_ok.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("1 passed", sortie)

    def test_C1f_pytest_ini_cache_et_pytest_toml(self):
        """MUTANT P-GEN (ini généré à la place de la config propre) : rc 5."""
        arbre = self.adoptant({
            "a/requirements.txt": "", "a/.pytest.ini": "[pytest]\npython_files = check_*.py\n",
            "a/check_a.py": TEST_VERT, "b/requirements.txt": "",
            "b/pytest.toml": '[pytest]\npython_files = ["check_*.py"]\n', "b/check_b.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("config pytest : a/.pytest.ini", sortie)
        self.assertIn("config pytest : b/pytest.toml", sortie)

    def test_C1g_parite_avec_locate_config_sur_les_sept_rangs(self):
        """API PRIVÉE de pytest : si elle disparaît, ce témoin ROUGIT, il ne saute
        jamais. MUTANT P-RANG (`.pytest.ini` retiré de la table) : divergence."""
        from _pytest.config.findpaths import locate_config
        contenus = {"pytest.toml": "[pytest]\n", ".pytest.toml": "[pytest]\n",
                    "pytest.ini": "[pytest]\n", ".pytest.ini": "[pytest]\n",
                    "pyproject.toml": "[tool.pytest.ini_options]\n", "tox.ini": "[pytest]\n",
                    "setup.cfg": "[tool:pytest]\n"}
        rangs = porte_adoptant.RANGS_PYTEST
        self.assertEqual(sorted(rangs), sorted(contenus))
        for i, nom in enumerate(rangs):
            dossier = self.tmp / f"rang{i}"
            self.ecrire(dossier, {n: contenus[n] for n in rangs[i:]})
            try:
                attendu = locate_config(dossier, [dossier])[1]
            except TypeError:  # pytest < 8.1 : locate_config(args)
                attendu = locate_config([dossier])[1]
            self.assertEqual(attendu.name, nom)
            self.assertEqual(porte_adoptant.config_pytest_propre(dossier, False).name, nom)
        racine = self.tmp / "racine"
        self.ecrire(racine, {"pytest.ini": "[pytest]\n", "tox.ini": "[pytest]\n"})
        self.assertEqual(porte_adoptant.config_pytest_propre(racine, True).name, "tox.ini")

    def test_conftest_du_kit_et_borne_imprimes(self):
        """MUTANT P-CONFTEST (ligne `conftest` retirée) ; MUTANT P-BORNE (borne C5
        retirée) : un périmètre non clos se lirait comme complet."""
        conftest = ("import pytest\n\n\n" "@pytest.fixture(autouse=True)\ndef a():\n    yield\n\n\n"
                    "@pytest.fixture(autouse=True)\ndef b():\n    yield\n")
        arbre = self.adoptant({"pyproject.toml": PYPROJECT_PROJET, "conftest.py": conftest,
                               "test_racine.py": TEST_VERT})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("conftest.py du kit chargé (2 fixtures autouse)", sortie)
        self.assertIn("node_modules/", sortie)
        self.assertIn("liste non close", sortie)

    def test_pytest_absent_rouge_nomme(self):
        """MUTANT P-ABSENT (pytest absent toléré)."""
        porte = porte_adoptant.Porte(self.tmp, {})
        (self.tmp / "m").mkdir()
        with mock.patch.object(porte_adoptant.importlib.util, "find_spec", return_value=None):
            issue = porte_adoptant.jouer_python(porte, Path("m"), [], self.tmp)
        self.assertEqual(issue, "rouge")
        self.assertIn("pytest absent", porte.refus[0])


# =============================================================================
class GardesTests(_Banc):
    """gitleaks et semgrep : une table par scanner, la dérogation ne couvre jamais
    une trouvaille."""

    def setUp(self) -> None:
        super().setUp()
        self.bouchon("npm")
        self.arbre = self.adoptant(MODULE_NPM | {".gitleaks.toml": "title = 'banc'\n"})

    def test_argv_gitleaks_porte_exit_code_7(self):
        """Ne saute JAMAIS. MUTANT G-EXIT (`--exit-code 7` retiré ; rejoué par
        MutantsDurablesTests) : une fuite rendrait rc 1, lue comme une erreur."""
        rc, sortie, _res = self.lancer(self.arbre)
        self.assertEqual(rc, 0, sortie)
        argv = self.appels("gitleaks")[0]["argv"]
        self.assertEqual(argv[:2], ["dir", str(self.arbre)])
        self.assertIn("--redact", argv)
        self.assertIn("--no-banner", argv)
        self.assertEqual(argv[argv.index("--exit-code") + 1], "7")
        self.assertEqual(argv[argv.index("--config") + 1], str(self.arbre / ".gitleaks.toml"))

    def test_argv_semgrep(self):
        """MUTANT G-SEP (`--` retiré devant les cibles) ; MUTANT G-ERR (`--error`
        retiré : une trouvaille rendrait rc 0)."""
        self.lancer(self.arbre)
        appel = self.appels("semgrep")[0]
        argv = appel["argv"]
        self.assertEqual(argv[argv.index("--config") + 1],
                         str(self.arbre / ".agents" / "security" / "semgrep.yml"))
        self.assertIn("--error", argv)
        self.assertEqual(argv[-2:], ["--", "."])
        self.assertEqual(Path(appel["cwd"]).resolve(), self.arbre)

    def test_une_table_par_scanner(self):
        """MUTANT G-TABLE (table fusionnée « 7 ou 1 = trouvaille ») : une config
        corrompue se lirait comme une fuite, et l'inverse."""
        cas = (("BANC_RC_GITLEAKS", "7", "gitleaks : TROUVAILLE", "gitleaks en ERREUR"),
               ("BANC_RC_GITLEAKS", "1", "gitleaks en ERREUR, rc 1", "gitleaks : TROUVAILLE"),
               ("BANC_RC_SEMGREP", "1", "semgrep : TROUVAILLE", "semgrep en ERREUR"),
               ("BANC_RC_SEMGREP", "7", "semgrep en ERREUR, rc 7", "semgrep : TROUVAILLE"))
        for variable, code, vu, jamais in cas:
            rc, sortie, _res = self.lancer(self.arbre, **{variable: code})
            self.assertEqual(rc, 1, sortie)
            self.assertIn(vu, sortie)
            self.assertNotIn(jamais, sortie)

    def test_derogation_couvre_l_erreur_jamais_la_trouvaille(self):
        """MUTANT G-DEROG (la dérogation couvre une trouvaille ; rejoué par
        MutantsDurablesTests)."""
        rc, sortie, res = self.lancer(self.arbre, BANC_RC_GITLEAKS="1",
                                      CADRE_GARDES_DEGRADEES="banc sans scanner")
        self.assertEqual(rc, 0, sortie)
        self.assertIn("COVERAGE DEGRADED — gitleaks en ERREUR, rc 1", sortie)
        self.assertEqual(res["derogation_gardes"], "banc sans scanner")
        rc, sortie, res = self.lancer(self.arbre, BANC_RC_SEMGREP="1",
                                      CADRE_GARDES_DEGRADEES="banc sans scanner")
        self.assertEqual(rc, 1, sortie)
        self.assertNotIn("derogation_gardes", res)

    def test_scanner_absent_rouge_puis_degrade(self):
        """MUTANT G-ABSENT (scanner absent toléré par défaut)."""
        (self.bouchons / "gitleaks").unlink()
        self.assertIsNone(shutil.which("gitleaks", path=self.env()["PATH"]))
        rc, sortie, _res = self.lancer(self.arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("gitleaks absent du PATH", sortie)
        rc, sortie, res = self.lancer(self.arbre, CADRE_GARDES_DEGRADEES="poste sans gitleaks")
        self.assertEqual(rc, 0, sortie)
        self.assertIn("COVERAGE DEGRADED — gitleaks absent du PATH", sortie)
        self.assertEqual(res["derogation_gardes"], "poste sans gitleaks")

    def test_lecture_partielle_refus_nomme_puis_derogee(self):
        """fable F2 : un fichier que semgrep n'a lu qu'EN PARTIE (rc 0, `errors` du rapport
        JSON) est un REFUS nommé, couvert par CADRE_GARDES_DEGRADEES ; un rapport absent
        aussi ; au-delà de 10 noms, la borne est dite. MUTANT L-ERREURS (`erreurs = []` ;
        rejoué par MutantsDurablesTests)."""
        rc, sortie, res = self.lancer(self.arbre, BANC_SEMGREP_ERREURS=ERREUR_PARTIELLE)
        self.assertEqual((rc, res["verdict"]), (1, "ECHEC"), sortie)
        self.assertIn("semgrep : propre (racine)", sortie)
        self.assertIn("ROUGE : COVERAGE DEGRADED — semgrep n'a pas lu en entier 1 fichier(s) : heredoc.sh "
                      "(racine) — un fichier lu en partie est un refus, pas un propre", sortie)
        rc, sortie, res = self.lancer(self.arbre, BANC_SEMGREP_ERREURS=ERREUR_PARTIELLE,
                                      CADRE_GARDES_DEGRADEES="heredoc hérité, ticket ouvert")
        self.assertEqual((rc, res["derogation_gardes"]), (0, "heredoc hérité, ticket ouvert"), sortie)
        rc, sortie, _res = self.lancer(self.arbre, BANC_SANS_RAPPORT="1")
        self.assertEqual(rc, 1, sortie)
        self.assertIn("semgrep n'a pas écrit de rapport JSON lisible", sortie)
        douze = json.dumps([{"path": f"f{i:02}.sh"} for i in range(12)] + [{"type": "Timeout"}])
        rc, sortie, _res = self.lancer(self.arbre, BANC_SEMGREP_ERREURS=douze)
        self.assertIn("n'a pas lu en entier 13 fichier(s) : <sans chemin : Timeout>, f00.sh", sortie)
        self.assertIn("… (+3 ; borne appliquée : 10 noms imprimés)", sortie)

    @unittest.skipUnless(SEMGREP_REEL, "SAUT ANNONCÉ : semgrep absent du PATH — la lecture partielle "
                         "réelle n'est pas rejouée ; le témoin au bouchon, lui, tourne")
    def test_lecture_partielle_reelle_heredoc(self):
        """Le vrai scanner, un heredoc en condition de `if` NEUF sur une branche de travail :
        rc 0 de semgrep, et la porte ROUGE nommée — jamais « propre » seul."""
        rc, sortie, _res = self.lancer(self.arbre_heredoc_reel())
        self.assertEqual(rc, 1, sortie)
        self.assertIn("COVERAGE DEGRADED — semgrep n'a pas lu en entier 1 fichier(s) : heredoc.sh", sortie)

    def arbre_heredoc_reel(self) -> Path:
        shutil.rmtree(self.arbre)
        arbre = self.adoptant(MODULE_NPM | {".agents/security/semgrep.yml": REGLE_EVAL_SH})
        (self.bouchons / "semgrep").unlink()
        os.symlink(SEMGREP_REEL, self.outils / "semgrep")
        self.git(arbre, "switch", "-q", "-c", "travail")
        self.ecrire(arbre, {"heredoc.sh": HEREDOC_SH})
        self.git(arbre, "add", "heredoc.sh")
        self.git(arbre, "commit", "-q", "-m", "heredoc")
        return arbre

    @unittest.skipUnless(GITLEAKS_REEL, "SAUT ANNONCÉ : gitleaks absent du PATH — la fuite "
                         "réelle n'est pas rejouée ; le témoin d'argv, lui, tourne")
    def test_fuite_reelle_reste_rouge_sous_derogation(self):
        """MUTANT G-EXIT : sans le drapeau la fuite rend rc 1, « erreur »,
        dérogée, VERT — ce témoin rougit (rejoué par MutantsDurablesTests)."""
        self.preparer_fuite()
        rc, sortie, res = self.lancer(self.arbre, CADRE_GARDES_DEGRADEES="banc")
        self.assertEqual(rc, 1, sortie)
        self.assertIn("gitleaks : TROUVAILLE", sortie)
        self.assertNotIn("gitleaks en ERREUR", sortie)
        self.assertNotIn("derogation_gardes", res)

    def preparer_fuite(self) -> None:
        (self.bouchons / "gitleaks").unlink()
        os.symlink(GITLEAKS_REEL, self.outils / "gitleaks")
        (self.arbre / ".gitleaks.toml").unlink()
        self.ecrire(self.arbre, {"secrets.env": f"GITHUB_TOKEN={jeton_de_fuite()}\n"})


# =============================================================================
class BaseSemgrepTests(_Banc):
    """semgrep `--baseline-commit <merge-base HEAD <branche par défaut>>` : seul le
    NEUF bloque (décision pilote S-00004250, 2)."""

    def setUp(self) -> None:
        super().setUp()
        self.bouchon("npm")

    def baseline(self) -> str | None:
        argv = self.appels("semgrep")[0]["argv"]
        return argv[argv.index("--baseline-commit") + 1] if "--baseline-commit" in argv else None

    def commit(self, arbre: Path, nom: str, texte: str = "x\n") -> str:
        self.ecrire(arbre, {nom: texte})
        self.git(arbre, "add", "--", nom)
        self.git(arbre, "commit", "-q", "-m", nom)
        return self.git(arbre, "rev-parse", "HEAD").strip()

    def test_branche_de_travail_base_merge_base(self):
        """MUTANT B-BASE (drapeau retiré : scan complet, l'existant bloque ; rejoué)."""
        arbre = self.adoptant(MODULE_NPM)
        principal = self.git(arbre, "rev-parse", "HEAD").strip()
        self.git(arbre, "switch", "-q", "-c", "travail")
        self.commit(arbre, "neuf.txt")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(self.baseline(), principal)
        self.assertIn("semgrep : seul le neuf bloque — base = merge-base HEAD refs/heads/main = "
                      f"{principal[:12]} (racine)", sortie)

    def test_sur_la_branche_par_defaut_base_head_parent(self):
        """MUTANT B-HEAD (base == HEAD gardée : semgrep ne verrait RIEN ; rejoué)."""
        arbre = self.adoptant(MODULE_NPM)
        avant = self.git(arbre, "rev-parse", "HEAD").strip()
        self.commit(arbre, "neuf.txt")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(self.baseline(), avant)
        self.assertIn(f"HEAD est sur ou derrière refs/heads/main : base = HEAD^1 = {avant[:12]}", sortie)

    def test_origin_head_d_abord_puis_suivi_distant_puis_local(self):
        """MUTANT B-ORIGIN (origin/HEAD ignoré ; rejoué) ; MUTANT B-LOCAL (la branche
        locale avant le suivi distant : une base trop récente). `origin/HEAD` pointe la
        branche PAR DÉFAUT du distant (`trunk`, hors main/master), comme un `git clone`
        la pose ; HEAD est sur une branche de TRAVAIL — jamais l'inverse (fable F1)."""
        arbre = self.adoptant(MODULE_NPM)
        c0 = self.git(arbre, "rev-parse", "HEAD").strip()
        self.git(arbre, "branch", "-m", "main", "travail")
        self.commit(arbre, "un.txt")
        self.commit(arbre, "deux.txt")
        self.git(arbre, "update-ref", "refs/remotes/origin/trunk", c0)
        self.git(arbre, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(self.baseline(), c0, "origin/HEAD n'est pas lu d'abord")
        self.assertIn("merge-base HEAD refs/remotes/origin/trunk", sortie)
        self.git(arbre, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        # origin/main EN RETARD sur une main locale : la locale lue d'abord donnerait HEAD^1.
        self.git(arbre, "branch", "main", "HEAD")
        self.git(arbre, "update-ref", "refs/remotes/origin/main", c0)
        self.journal.unlink()
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(self.baseline(), c0, "la branche locale passe avant le suivi distant")
        self.assertIn("merge-base HEAD refs/remotes/origin/main", sortie)

    def test_aucune_base_scan_complet_et_dit(self):
        """MUTANT B-DIT (le scan complet n'est pas dit)."""
        arbre = self.adoptant(MODULE_NPM)
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIsNone(self.baseline())
        self.assertIn("semgrep : scan COMPLET, aucune base calculable — HEAD est sur ou derrière "
                      "refs/heads/main et n'a pas de parent (racine)", sortie)
        self.git(arbre, "branch", "-m", "main", "autre")
        self.journal.unlink()
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIsNone(self.baseline())
        self.assertIn("aucune branche par défaut résolue", sortie)

    def baseline_de(self, dossier: Path) -> str | None:
        argv = next(a["argv"] for a in self.appels("semgrep") if Path(a["cwd"]).resolve() == dossier)
        return argv[argv.index("--baseline-commit") + 1] if "--baseline-commit" in argv else None

    def sous_module_en_retard(self) -> tuple[Path, list[str]]:
        """Un sous-module ÉPINGLÉ en retard de la branche principale de son distant
        (forme CI) : gitlink s0 à la base de la racine, s2 sur la branche de travail,
        `origin/main` du module à s3. Rend (arbre, [s0, s1, s2, s3])."""
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM)
        self.sous_module(arbre, "m1", {"a.txt": "0\n"})
        source = self.sources / "m1"
        shas = [self.git(source, "rev-parse", "HEAD").strip()]
        for i in (1, 2, 3):
            shas.append(self.commit(source, "a.txt", f"{i}\n"))
        self.git(arbre / "m1", "fetch", "-q", "origin")
        self.git(arbre / "m1", "switch", "-q", "--detach", shas[2])
        self.git(arbre, "switch", "-q", "-c", "travail")
        self.git(arbre, "add", "m1")
        self.git(arbre, "commit", "-q", "-m", "m1 épinglé à s2")
        return arbre, shas

    def test_sous_module_en_retard_base_au_gitlink_de_la_base(self):
        """opus T2 : la base d'un sous-module est SON gitlink à la base du dépôt parent
        (s0) — jamais HEAD^1 (s1) lu contre un `origin/main` en avance. MUTANT B-GITLINK
        (dérivation retirée ; rejoué) : s1, et « HEAD est sur ou derrière »."""
        arbre, shas = self.sous_module_en_retard()
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(self.baseline_de(arbre / "m1"), shas[0])
        self.assertIn(f"base = gitlink à la base du dépôt parent = {shas[0][:12]} (m1)", sortie)

    @unittest.skipUnless(SEMGREP_REEL, "SAUT ANNONCÉ : semgrep absent du PATH — l'existant et le neuf "
                         "ne sont pas rejoués sur le vrai scanner ; les témoins d'argv, eux, tournent")
    def test_semgrep_reel_existant_vert_neuf_rouge(self):
        """Le vrai scanner : une trouvaille PRÉEXISTANTE sur la branche par défaut → vert ;
        une trouvaille AJOUTÉE sur la branche de travail → ROUGE."""
        arbre = self.adoptant(MODULE_NPM | {".agents/security/semgrep.yml": REGLE_EVAL,
                                            "vieux.py": 'eval("1")\n'})
        (self.bouchons / "semgrep").unlink()
        os.symlink(SEMGREP_REEL, self.outils / "semgrep")
        self.git(arbre, "switch", "-q", "-c", "travail")
        self.commit(arbre, "propre.py", "x = 1\n")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 0, sortie)
        self.assertIn("semgrep : propre (racine)", sortie)
        self.commit(arbre, "neuf.py", 'eval("2")\n')
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("semgrep : TROUVAILLE sur racine (rc 1)", sortie)


# =============================================================================
class SansShellTests(_Banc):
    """Aucune valeur n'est re-parsée comme du shell."""

    def test_chemins_pieges_refuses_sans_execution(self):
        """MUTANT N-NOM (contrôle du nom retiré) : npm tourne dans les dossiers
        pièges. Aucun fichier PWNED, jamais."""
        pieges = ("a;touch PWNED", "b$(touch PWNED)", "c\nd", "e\tf")
        arbre = self.adoptant({f"{n}/package.json": "{}" for n in pieges} | MODULE_NPM)
        self.bouchon("npm")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertEqual(sortie.count("ROUGE : chemin de module refusé"), len(pieges), sortie)
        self.assertEqual({Path(a["cwd"]).resolve() for a in self.appels("npm")}, {arbre})
        self.assertEqual(list(self.tmp.rglob("PWNED")), [])

    def test_aucun_shell_dans_la_source(self):
        """MUTANT N-SHELL (`shell=True`, `os.system`, une commande en chaîne)."""
        arbre = ast.parse(PORTE.read_text(encoding="utf-8"))
        appels = 0
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.keyword):
                self.assertNotEqual(noeud.arg, "shell", ast.unparse(noeud))
            if not isinstance(noeud, ast.Call):
                continue
            nom = ast.unparse(noeud.func)
            self.assertNotIn(nom, ("os.system", "os.popen", "subprocess.getoutput",
                                   "subprocess.getstatusoutput"))
            if nom.startswith("subprocess."):
                appels += 1
                premier = noeud.args[0] if noeud.args else None
                self.assertNotIsInstance(premier, (ast.Constant, ast.JoinedStr, ast.BinOp),
                                         ast.unparse(noeud))
        self.assertGreaterEqual(appels, 3)


# =============================================================================
class IntegriteTests(_Banc):
    """Intégrité courte du kit : registres JSON, scripts cités, `bash -n`, mode."""

    def setUp(self) -> None:
        super().setUp()
        self.bouchon("npm")

    def test_registre_illisible(self):
        """MUTANT I-JSON (registre illisible ignoré)."""
        arbre = self.adoptant(MODULE_NPM | {".codex/hooks.json": "{pas du json"})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("registre de hooks illisible (JSON) : .codex/hooks.json", sortie)

    def test_script_cite_absent_lu_dans_les_hooks_seulement(self):
        """MUTANT I-CITE (motif qui refuse un `/` devant le chemin : la forme
        `"$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh"` échappe) ; MUTANT I-HOOKS (tout
        le JSON lu : une permission devient une citation)."""
        claude = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command":
                  'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/absent.sh"'}]}]},
                  "permissions": {"allow": ["Bash(python3 .agents/bin/fantome.py)"]}}
        agents = {"hooks": {"X": [{"command":
                  'bash "$(git rev-parse --show-toplevel)/.agents/present.sh"'}]}}
        arbre = self.adoptant(MODULE_NPM | {".claude/settings.json": json.dumps(claude),
                                            ".agents/hooks.json": json.dumps(agents),
                                            ".agents/present.sh": "echo ok\n"})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("script cité absent : .claude/hooks/absent.sh", sortie)
        self.assertNotIn("script cité absent : .agents/present.sh", sortie)
        self.assertNotIn("fantome.py", sortie)
        self.assertIn("2 script(s) cité(s)", sortie)

    def test_bash_invalide_et_fichier_non_shell_ignore(self):
        """MUTANT I-BASHN (`bash -n` retiré) ; MUTANT I-SHFILTRE (tout fichier de
        `.githooks/` lu par `bash -n` : une note en prose rougirait la porte)."""
        arbre = self.adoptant(MODULE_NPM | {".githooks/commit-msg": "#!/usr/bin/env bash\nif then\n",
                                            ".githooks/LISEZMOI.md": "Lisez ( ceci\n"})
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("syntaxe bash invalide : .githooks/commit-msg", sortie)
        self.assertNotIn("LISEZMOI", sortie)

    def test_pre_push_non_executable(self):
        """MUTANT I-MODE (mode 100755 non vérifié)."""
        arbre = self.adoptant(MODULE_NPM, pre_push_x=False)
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("n'est pas exécutable dans l'index (mode 100644)", sortie)


# =============================================================================
class AssainissementTests(unittest.TestCase):
    """C7 : la raison est assainie À LA SOURCE, l'accent survit."""

    def test_accent_intact_controles_retires_borne(self):
        """MUTANT A-ASCII (filtre ASCII) ; MUTANT A-BORNE (borne retirée)."""
        assainir = porte_adoptant.assainir
        self.assertEqual(assainir("raison é\tà\x01\u202e\udcff\u2028"), "raison éà")
        self.assertEqual(len(assainir("é" * 300)), 200)

    def test_raison_vide_ou_drapeau_refusee(self):
        """MUTANT A-VIDE (raison vide acceptée) ; MUTANT A-DRAPEAU (« 1 » accepté)."""
        lire = porte_adoptant.lire_derogations
        for valeur in ("\x01\x02", "", "1", "Oui", " true "):
            raisons, refus = lire({"CADRE_SANS_TEST": valeur})
            self.assertEqual((raisons, len(refus)), ({}, 1), repr(valeur))
        raisons, refus = lire({"CADRE_GARDES_DEGRADEES": " banc sans scanner "})
        self.assertEqual((raisons, refus), ({"CADRE_GARDES_DEGRADEES": "banc sans scanner"}, []))


# =============================================================================
def references_ancrees(texte: str) -> list[str]:
    """Les lignes où la racine RÉELLE (`ROOT`) désigne le marqueur du kit ou
    l'état local — même normalisation que l'étage A du kit."""
    cibles = ("/.agents/" + "IS_THE_KIT", "/.agents/" + "state")
    fautes = []
    for ligne in texte.splitlines():
        for m in re.finditer(r"\bROOT\b", ligne):
            queue = re.sub(r"[\"'\s}]+", "", ligne[m.end():]).replace(",", "/").replace("\\", "/")
            if re.sub(r"/{2,}", "/", queue).startswith(cibles):
                fautes.append(ligne.strip())
    return fautes


class EtageATests(unittest.TestCase):
    """Ce fichier voyage : aucune référence ancrée sur la racine réelle au
    marqueur ni à l'état local (les arbres sont temporaires)."""

    def test_aucune_reference_ancree(self):
        """MUTANT E-ANCRE (une référence ajoutée) : le témoin la nomme."""
        self.assertEqual(references_ancrees(Path(__file__).read_text(encoding="utf-8")), [])
        synthese = "x = " + "ROOT" + ' / ".agents" / "IS_' + 'THE_KIT"'
        self.assertEqual(len(references_ancrees(synthese)), 1)


# =============================================================================
class MutantsDurablesTests(_Banc):
    """Les mutants porteurs, rejoués à chaque passage : le scénario est VERT
    sur la source et ROUGE sur la copie mutée (et l'inverse pour les mutants qui
    VERDISSENT un défaut)."""

    def muter(self, ancien: str, nouveau: str) -> Path:
        source = PORTE.read_text(encoding="utf-8")
        self.assertEqual(source.count(ancien), 1, f"ancre du mutant introuvable : {ancien!r}")
        mutee = source.replace(ancien, nouveau)
        self.assertNotEqual(mutee, source, "mutation sans effet")
        chemin = self.tmp / "porte_mutee.py"
        chemin.write_text(mutee, encoding="utf-8")
        return chemin

    def test_G_EXIT_drapeau_exit_code_retire(self):
        mutant = self.muter('"--no-banner", "--exit-code", "7"]', '"--no-banner"]')
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM)
        for porte, attendu in ((PORTE, True), (mutant, False)):
            self.journal.unlink(missing_ok=True)
            self.lancer(arbre, porte=porte)
            argv = self.appels("gitleaks")[0]["argv"]
            self.assertEqual("--exit-code" in argv and argv[argv.index("--exit-code") + 1] == "7",
                             attendu)
        if GITLEAKS_REEL:
            (self.bouchons / "gitleaks").unlink()
            os.symlink(GITLEAKS_REEL, self.outils / "gitleaks")
            self.ecrire(arbre, {"secrets.env": f"GITHUB_TOKEN={jeton_de_fuite()}\n"})
            self.assertEqual(self.lancer(arbre, CADRE_GARDES_DEGRADEES="banc")[0], 1)
            rc, sortie, _res = self.lancer(arbre, porte=mutant, CADRE_GARDES_DEGRADEES="banc")
            self.assertEqual(rc, 0, "le mutant G-EXIT devait verdir une fuite réelle : " + sortie)

    def test_S_NP_ligne_non_peuple_retiree(self):
        mutant = self.muter('porte.rouge(f"sous-module non peuplé : ',
                            '(lambda *_: None)(f"sous-module non peuplé : ')
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        self.git(arbre, "submodule", "deinit", "-f", "-q", "m1")
        rc, sortie, _res = self.lancer(arbre)
        self.assertEqual(rc, 1)
        self.assertIn("sous-module non peuplé : m1", sortie)
        # Sans la ligne, plus rien ne bloque : « aucun module » n'est plus qu'un
        # avertissement (S-00004278) — le mutant VERDIT un gitlink vide.
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 0, "le mutant S-NP devait verdir un gitlink non peuplé : " + sortie)
        self.assertIn("AVERTISSEMENT : aucun module", sortie)
        self.assertNotIn("sous-module non peuplé", sortie)

    def test_G_DEROG_derogation_couvrant_une_trouvaille(self):
        mutant = self.muter('    if issue == "trouvaille":\n',
                            '    if issue == "trouvaille" and not porte.deroger('
                            '"CADRE_GARDES_DEGRADEES", "trouvaille"):\n')
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM)
        env = {"BANC_RC_GITLEAKS": "7", "CADRE_GARDES_DEGRADEES": "banc"}
        self.assertEqual(self.lancer(arbre, **env)[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant, **env)
        self.assertEqual(rc, 0, "le mutant G-DEROG devait verdir une trouvaille : " + sortie)

    def test_M_AGENTS_exclusion_de_l_outillage_retiree(self):
        mutant = self.muter('if rel.parts[:1] == (".agents",):', "if False:")
        self.bouchon("npm")
        arbre = self.adoptant({".agents/ui-src/package.json": MODULE_NPM["package.json"],
                               ".agents/ui-src/package-lock.json": VERROU_NPM})
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual((rc, res["modules"], self.appels("npm")), (0, "", []), sortie)
        rc, sortie, res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 0, sortie)
        self.assertEqual(res["modules"], ".agents/ui-src", "le mutant M-AGENTS devait garder ui-src")
        self.assertTrue(self.appels("npm"), "le mutant M-AGENTS devait jouer npm dans ui-src")

    def test_M_LS_filtre_par_le_seul_superprojet(self):
        mutant = self.muter("if any(suivi(dossier, n) for n in manifestes):",
                            "if any(suivi(porte.racine, (rel / n).as_posix()) for n in manifestes):")
        arbre = self.adoptant()
        self.sous_module(arbre, "m1", MODULE_PY)
        rc, sortie, res = self.lancer(arbre)
        self.assertEqual((rc, res["modules"]), (0, "m1"), sortie)
        self.assertIn("gardé : m1 [python]", sortie)
        # S-00004278 : sans module, le mutant ne rougit plus — il perd m1 et AVERTIT.
        rc, sortie, res = self.lancer(arbre, porte=mutant)
        self.assertEqual((rc, res["modules"], res.get("avertissement")), (0, "", AVERT), sortie)
        self.assertNotIn("gardé : m1", sortie)

    def test_V_PNPM_verrou_pnpm_lu_comme_npm(self):
        mutant = self.muter('    ("pnpm-lock.yaml", "pnpm", ("install", "--frozen-lockfile")),\n',
                            '    ("pnpm-lock.yaml", "npm", ("ci",)),\n')
        self.bouchon("pnpm")
        self.bouchon("npm")
        arbre = self.adoptant({"package.json": MODULE_NPM["package.json"], "pnpm-lock.yaml": "x\n"})
        for porte, outil, absent in ((PORTE, "pnpm", "npm"), (mutant, "npm", "pnpm")):
            self.journal.unlink(missing_ok=True)
            rc, sortie, _res = self.lancer(arbre, porte=porte)
            self.assertEqual(rc, 0, sortie)
            self.assertTrue(self.appels(outil), f"{outil} non appelé : {sortie}")
            self.assertEqual(self.appels(absent), [], sortie)

    def test_V_SANS_repli_sans_verrou(self):
        mutant = self.muter("    if not verrous:\n",
                            '    verrous = verrous or [("package.json", "npm", ("install",))]\n    if not verrous:\n')
        self.bouchon("npm")
        arbre = self.adoptant({"package.json": MODULE_NPM["package.json"]})
        self.assertEqual(self.lancer(arbre)[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 0, "le mutant V-SANS devait verdir un module sans verrou : " + sortie)

    def test_S_SCRIPT_script_du_projet_ignore(self):
        mutant = self.muter("    if script is not None:\n", "    if False:\n")
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM | {SCRIPT_PROJET: SCRIPT_SOURCE})
        self.assertEqual(self.lancer(arbre, BANC_SCRIPT_RC="3")[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant, BANC_SCRIPT_RC="3")
        self.assertEqual(rc, 0, "le mutant S-SCRIPT devait verdir malgré le script rouge : " + sortie)

    def test_S_SUIVI_script_non_suivi_execute(self):
        mutant = self.muter("    if not suivi(porte.racine, nom):\n", "    if False:\n")
        self.bouchon("npm")
        for fichiers in (MODULE_NPM, MODULE_PHP):  # (2) séquence par défaut, (3) avertissement
            arbre = self.adoptant(fichiers)
            self.ecrire(arbre, {SCRIPT_PROJET: "#!/usr/bin/env bash\nexit 7\n"})
            self.assertEqual(self.lancer(arbre)[0], 0)
            rc, sortie, _res = self.lancer(arbre, porte=mutant)
            self.assertEqual(rc, 1, "le mutant S-SUIVI devait lancer le script non suivi : " + sortie)
            shutil.rmtree(arbre)

    def test_S_ENV_environnement_herite(self):
        mutant = self.muter("env=env_enfant() if env is None else env,",
                            "env=None,")
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE})
        env = {"GIT_DIR": str(self.tmp / "ailleurs")}
        self.assertEqual(self.lancer(arbre, **env)[0], 0)
        rc, sortie, _res = self.lancer(arbre, porte=mutant, **env)
        self.assertEqual(rc, 1, "le mutant S-ENV devait laisser GIT_DIR atteindre le script : " + sortie)
        self.assertIn("(rc 9)", sortie)

    def test_V_TABLE_ligne_yarn_retiree(self):
        mutant = self.muter('    ("yarn.lock", "yarn", ("install", "--frozen-lockfile")),\n', "")
        self.bouchon("yarn")
        arbre = self.adoptant({"package.json": MODULE_NPM["package.json"], "yarn.lock": "x\n"})
        self.assertEqual(self.lancer(arbre)[0], 0)
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("aucun lockfile", sortie)

    def test_V_ABSENT_repli_sur_npm(self):
        mutant = self.muter("    gestionnaire = shutil.which(nom)\n",
                            '    gestionnaire = shutil.which(nom) or shutil.which("npm")\n')
        self.bouchon("npm")
        arbre = self.adoptant({"package.json": MODULE_NPM["package.json"], "pnpm-lock.yaml": "x\n"})
        self.assertEqual(self.lancer(arbre)[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 0, "le mutant V-ABSENT devait construire un projet pnpm par npm : " + sortie)

    def test_S_CWD_script_hors_de_la_racine(self):
        mutant = self.muter("    rc, motif = executer([bash, nom], porte.racine, BORNE_COMMANDE_S)\n",
                            "    rc, motif = executer([bash, str(porte.racine / nom)], porte.racine.parent, "
                            "BORNE_COMMANDE_S)\n")
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE})
        self.assertEqual(self.lancer(arbre)[0], 0)
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 1, sortie)
        self.assertIn("(rc 8)", sortie)

    def test_B_LOCAL_branche_locale_d_abord(self):
        mutant = self.muter('REFS_DEFAUT = ("refs/remotes/origin/main", "refs/remotes/origin/master",\n'
                            '               "refs/heads/main", "refs/heads/master")\n',
                            'REFS_DEFAUT = ("refs/heads/main", "refs/heads/master",\n'
                            '               "refs/remotes/origin/main", "refs/remotes/origin/master")\n')
        arbre, shas = self.arbre_a_trois_commits()
        self.git(arbre, "update-ref", "refs/remotes/origin/main", shas[0])
        self.assertEqual(self.baseline_sous(PORTE, arbre), shas[0])
        self.assertEqual(self.baseline_sous(mutant, arbre), shas[1], "le mutant B-LOCAL devait lire la locale d'abord")

    def test_B_DIT_scan_complet_tu(self):
        mutant = self.muter('            print(f"semgrep : scan COMPLET, aucune base calculable',
                            '            (lambda *_a, **_k: None)(f"semgrep : scan COMPLET, aucune base calculable')
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM)
        self.assertIn("semgrep : scan COMPLET", self.lancer(arbre)[1])
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 0, sortie)
        self.assertNotIn("semgrep : scan COMPLET", sortie, "le mutant B-DIT devait taire le scan complet")

    def baseline_sous(self, porte: Path, arbre: Path, dossier: Path | None = None, **env: str) -> str | None:
        self.journal.unlink(missing_ok=True)
        rc, self.sortie, _res = self.lancer(arbre, porte=porte, **env)
        self.assertEqual(rc, 0, self.sortie)
        cible = (dossier or arbre).resolve()
        argv = next(a["argv"] for a in self.appels("semgrep") if Path(a["cwd"]).resolve() == cible)
        return argv[argv.index("--baseline-commit") + 1] if "--baseline-commit" in argv else None

    def arbre_a_trois_commits(self) -> tuple[Path, list[str]]:
        self.bouchon("npm")
        arbre = self.adoptant(MODULE_NPM)
        shas = [self.git(arbre, "rev-parse", "HEAD").strip()]
        for nom in ("un.txt", "deux.txt"):
            self.ecrire(arbre, {nom: "x\n"})
            self.git(arbre, "add", "--", nom)
            self.git(arbre, "commit", "-q", "-m", nom)
            shas.append(self.git(arbre, "rev-parse", "HEAD").strip())
        return arbre, shas

    def test_B_BASE_drapeau_retire(self):
        mutant = self.muter('            argv += ["--baseline-commit", base]\n', "            pass\n")
        arbre, shas = self.arbre_a_trois_commits()
        self.assertEqual(self.baseline_sous(PORTE, arbre), shas[1])
        self.assertIsNone(self.baseline_sous(mutant, arbre), "le mutant B-BASE devait rendre un scan complet")

    def test_B_HEAD_base_egale_a_head_gardee(self):
        mutant = self.muter("        if base != tete:\n", "        if True:\n")
        arbre, shas = self.arbre_a_trois_commits()
        self.assertEqual(self.baseline_sous(PORTE, arbre), shas[1])
        self.assertEqual(self.baseline_sous(mutant, arbre), shas[2], "le mutant B-HEAD devait passer HEAD en base")

    def test_B_ORIGIN_origin_head_ignore(self):
        """origin/HEAD SUR la branche par défaut du distant (`trunk`), HEAD sur une branche
        de travail : sans origin/HEAD, aucune autre ref ne résout — scan complet."""
        mutant = self.muter('    refs = [r for r in (_sortie(git(depot, "symbolic-ref", "-q", '
                            '"refs/remotes/origin/HEAD")),) if r]\n', "    refs = []\n")
        arbre, shas = self.arbre_a_trois_commits()
        self.git(arbre, "branch", "-m", "main", "travail")
        self.git(arbre, "update-ref", "refs/remotes/origin/trunk", shas[0])
        self.git(arbre, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertEqual(self.baseline_sous(PORTE, arbre), shas[0])
        self.assertIsNone(self.baseline_sous(mutant, arbre), "le mutant B-ORIGIN devait ignorer origin/HEAD")

    def test_B_IMPOSEE_base_imposee_valide_ou_repli_dit(self):
        """opus T2 / S-00004276 : `CADRE_SEMGREP_BASE` (verify.sh --at, base de PR, `before`
        d'un push) est la base de la racine si c'est un sha de 40 hex ANCÊTRE de HEAD ;
        égale à HEAD : HEAD^1 ; sinon repli `base_semgrep` (ici HEAD^1 : HEAD est sur main),
        refus NOMMÉ. MUTANT B-IMPOSEE (base imposée ignorée) ; MUTANT B-ANCETRE (contrôle
        d'ascendance retiré : un `before` d'avant force-push deviendrait la base)."""
        ignoree = self.muter("            base, dit = base_imposee(dossier, imposee)\n",
                             "            base, dit = base_semgrep(dossier)\n")
        arbre, shas = self.arbre_a_trois_commits()
        self.git(arbre, "switch", "-q", "-c", "autre", shas[0])
        etranger = self.commit_vide(arbre, "hors de HEAD")
        self.git(arbre, "switch", "-q", "main")
        pas_ici = "1234567890abcdef" * 2 + "12345678"
        for valeur, base, dit in (
                (shas[0], shas[0], f"base imposée par CADRE_SEMGREP_BASE = {shas[0][:12]} (racine)"),
                (shas[2], shas[1], f"CADRE_SEMGREP_BASE = HEAD : base = HEAD^1 = {shas[1][:12]}"),
                ("0" * 40, shas[1], "CADRE_SEMGREP_BASE refusée (0000…0 : création de branche"),
                ("HEAD~2", shas[1], "CADRE_SEMGREP_BASE refusée (pas un sha de 40 hex) ; repli : HEAD est"),
                (pas_ici, shas[1], f"refusée ({pas_ici[:12]} absent de l'historique (force-push"),
                (etranger, shas[1], f"refusée ({etranger[:12]} n'est pas un ancêtre de HEAD")):
            with self.subTest(valeur=valeur):
                self.assertEqual(self.baseline_sous(PORTE, arbre, CADRE_SEMGREP_BASE=valeur), base)
                self.assertIn(dit, self.sortie)
        self.assertEqual(self.baseline_sous(ignoree, arbre, CADRE_SEMGREP_BASE=shas[0]), shas[1],
                         "le mutant B-IMPOSEE devait ignorer la base imposée")
        ancetre = self.muter("    elif not _est_ancetre(depot, valeur):\n", "    elif False:\n")
        self.assertEqual(self.baseline_sous(ancetre, arbre, CADRE_SEMGREP_BASE=etranger), etranger,
                         "le mutant B-ANCETRE devait accepter une base hors de l'historique de HEAD")

    def commit_vide(self, arbre: Path, message: str) -> str:
        self.git(arbre, "commit", "-q", "--allow-empty", "-m", message)
        return self.git(arbre, "rev-parse", "HEAD").strip()

    def test_B_GITLINK_derivation_retiree(self):
        mutant = self.muter("            base, dit = base_sous_module(porte, rel, parent, bases.get(parent))\n",
                            "            base, dit = base_semgrep(porte.racine / rel)\n")
        arbre, shas = BaseSemgrepTests.sous_module_en_retard(self)
        self.assertEqual(self.baseline_sous(PORTE, arbre, arbre / "m1"), shas[0])
        self.assertEqual(self.baseline_sous(mutant, arbre, arbre / "m1"), shas[1],
                         "le mutant B-GITLINK devait juger le seul HEAD^1 du module")
        self.assertIn("HEAD est sur ou derrière refs/remotes/origin/main : base = HEAD^1", self.sortie)

    def commit(self, arbre: Path, nom: str, texte: str = "x\n") -> str:
        return BaseSemgrepTests.commit(self, arbre, nom, texte)

    def test_L_ERREURS_lecture_partielle_avalee(self):
        mutant = self.muter("    erreurs = erreurs_de_lecture(rapport)\n", "    erreurs = []\n")
        self.bouchon("npm")
        arbre = self.arbre = self.adoptant(MODULE_NPM)
        self.assertEqual(self.lancer(arbre, BANC_SEMGREP_ERREURS=ERREUR_PARTIELLE)[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant, BANC_SEMGREP_ERREURS=ERREUR_PARTIELLE)
        self.assertEqual(rc, 0, "le mutant L-ERREURS devait avaler la lecture partielle : " + sortie)
        if SEMGREP_REEL:
            arbre = GardesTests.arbre_heredoc_reel(self)
            self.assertEqual(self.lancer(arbre)[0], 1)
            rc, sortie, _res = self.lancer(arbre, porte=mutant)
            self.assertEqual(rc, 0, "sur le vrai semgrep, le mutant L-ERREURS devait verdir : " + sortie)
            self.assertIn("semgrep : propre (racine)", sortie)

    def test_S_PORTEE_sequence_par_defaut_apres_le_script(self):
        mutant = self.muter("        jouer_script_projet(porte)\n        return\n", "        jouer_script_projet(porte)\n")
        self.bouchon("npm")
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_SOURCE, "web/package.json": MODULE_NPM["package.json"]})
        self.assertEqual(self.lancer(arbre)[0], 0)
        rc, sortie, _res = self.lancer(arbre, porte=mutant)
        self.assertEqual(rc, 1, "le mutant S-PORTEE devait jouer web sans verrou : " + sortie)
        self.assertIn("aucun lockfile", sortie)

    def test_H_mutants_du_depot_mixte(self):
        """Binôme c4f3 ter : sur son scénario, chaque mutant rend VERT mais un AUTRE
        avertissement que la source (valeurs exactes : HorsTableTests, ModulesTests)."""
        self.bouchon("npm")
        sous = lambda arbre: self.sous_module(arbre, "m1", MODULE_PY | {"composer.json": "{}\n"})  # noqa: E731
        cas = {"H-TU": ("    hors_table = manifestes_hors_table(porte, peuples, decouverte.PRUNE)\n",
                        "    hors_table = []\n", MIXTE_OPUS, None),
               "H-SCRIPT": ("        jouer_script_projet(porte)\n        return\n", "        jouer_script_projet"
                            "(porte)\n        porte.avertissement = AVERTISSEMENT_HORS_TABLE\n        return\n",
                            MIXTE_FABLE | {SCRIPT_PROJET: SCRIPT_SOURCE}, None),
               "H-SUIVI": ('"ls-files", "-z", "--", *motifs)', '"ls-files", "-z", "-c", "-o", "--", *motifs)',
                           MODULE_NPM, lambda arbre: self.ecrire(arbre, {"composer.json": "{}\n"})),
               "H-ELAGUE": ("            if chemin and not set(rel.parts[:-1]) & set(elagues):\n",
                            "            if chemin:\n", MODULE_NPM | ELAGUES, None),
               "H-SOUS": ('    for depot in [Path(".")] + peuples:\n', '    for depot in [Path(".")]:\n',
                          MODULE_NPM, sous),
               "H-BORNE": ("    if len(noms) > BORNE_HORS_TABLE:\n", "    if False:\n",
                           {f"s{i:02d}/Cargo.toml": "" for i in range(12)}, None),
               "H-FUSION": ('            porte.avertissement += f" — manifeste(s) hors table : {hors}"\n',
                            "            pass\n", MODULE_PHP, None)}
        for nom, (ancre, nouveau, fichiers, apres) in cas.items():
            with self.subTest(mutant=nom):
                mutant = self.muter(ancre, nouveau)
                arbre = self.adoptant(fichiers)
                if apres is not None:
                    apres(arbre)
                vus = [self.lancer(arbre, porte=porte) for porte in (PORTE, mutant)]
                self.assertEqual([rc for rc, _s, _r in vus], [0, 0], vus[1][1])
                self.assertNotEqual(vus[0][2].get("avertissement"), vus[1][2].get("avertissement"),
                                    f"le mutant {nom} devait changer l'avertissement")
                shutil.rmtree(arbre)
                shutil.rmtree(self.sources / "m1", ignore_errors=True)

    def test_M_AVERT_M_AUCUN_avertissement(self):
        arbre = self.adoptant({"src/App.php": "<?php\n"})  # sans manifeste hors table : AVERT seul
        tu = self.muter("        porte.avertissement = AVERTISSEMENT_SANS_MODULE\n", "        pass\n")
        rc, _sortie, res = self.lancer(arbre, porte=tu)
        self.assertEqual(rc, 0)
        self.assertNotIn("avertissement", res, "le mutant M-AVERT devait taire l'avertissement au résultat")
        rouge = self.muter("        porte.avertissement = AVERTISSEMENT_SANS_MODULE\n",
                           "        porte.rouge(AVERTISSEMENT_SANS_MODULE)\n")
        self.assertEqual(self.lancer(arbre, porte=rouge)[0], 1, "le mutant M-AUCUN devait rougir")

    def test_M_GARDES_gardes_sautees_sans_module(self):
        mutant = self.muter("    jouer_gardes(porte, peuples)\n",
                            "    (jouer_gardes(porte, peuples) if gardes or script else None)\n")
        arbre = self.adoptant(MODULE_PHP)
        self.assertEqual(self.lancer(arbre, BANC_RC_SEMGREP="1")[0], 1)
        rc, sortie, _res = self.lancer(arbre, porte=mutant, BANC_RC_SEMGREP="1")
        self.assertEqual(rc, 0, "le mutant M-GARDES devait verdir un finding neuf : " + sortie)

    def test_R_GARDE_reentrance(self):
        mutant = self.muter("        if GARDE_REENTRANCE in os.environ:\n", "        if False:\n")
        arbre = self.adoptant({SCRIPT_PROJET: SCRIPT_REENTRANT})
        rc, sortie, _res = self.lancer(arbre, porte=mutant, BANC_PYTHON=sys.executable, BANC_PORTE=str(mutant))
        self.assertIn("BANC RECURSION 2", sortie, "le mutant R-GARDE devait boucler jusqu'au compteur du banc")
        self.assertNotIn("ROUGE : réentrance", sortie)


if __name__ == "__main__":
    unittest.main()
