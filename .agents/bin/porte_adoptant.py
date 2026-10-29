#!/usr/bin/env python3
"""Porte de push de l'ADOPTANT (T-00001183, décision pilote S-00004119).

Chez un projet adoptant, ce sont le build et les tests DU PROJET et de ses
sous-modules qui font foi — jamais la suite du kit. `verify.sh` appelle ce
script en mode adoptant ; la CI l'appelle dans le job `adoptant`.

APPEL (contrat partagé entre les shards du plan, figé) :
    "$PY" .agents/bin/porte_adoptant.py [--liste] [--root <dir>]
    rc 0 = vert, 1 = rouge, 2 = usage (argument, arbre qui n'est pas un
    adoptant, dérogation vide). `--liste` n'exécute rien : il imprime les
    modules gardés et les écartés, avec la raison.

RÈGLE DE PORTE, la même aux trois endroits (verify.sh, pre-push, ci.yml) :
mode ADOPTANT si et seulement si `.agents/IS_THE_KIT` est ABSENT et
`.agents/security/module_discovery.py` est PRÉSENT. Le nom du pyproject n'y
entre jamais. Ce script imprime sa décision et refuse (rc 2) un autre arbre.

CANAL DE RETOUR : `<racine>/.agents/state/local/PORTE_RESULT`, supprimé AVANT
toute autre chose (un `OK` périmé ne survit jamais à un refus), écrit à la fin
par fichier temporaire + `os.replace`. Clés : `sha=`, `verdict=OK|ECHEC`,
`modules=` (chemins POSIX relatifs, triés, séparés par des virgules — sûr :
un chemin hors `[A-Za-z0-9._/@+-]` est refusé, la virgule n'y est jamais),
`derogation_gardes=` / `derogation_test=` — chacune écrite SEULEMENT quand la
dérogation a couvert un refus réel, jamais vide — et `avertissement=`, écrite
SEULEMENT quand la porte sait qu'elle n'a pas vérifié build et tests de tout le
dépôt (ci-dessous) : UNE valeur, sur UNE ligne.

SORTIES TRACÉES, raison NON VIDE (jamais un drapeau `=1`) :
  CADRE_GARDES_DEGRADEES  scanner ABSENT ou en ERREUR, fichier que semgrep
                          n'a lu qu'EN PARTIE, ou énumération git en échec des
                          fichiers suivis sous `.agents/vendor/` — jamais une
                          trouvaille ;
  CADRE_SANS_TEST         un module sans test.
Chaque raison est assainie à la source (contrôles retirés, 200 points de code
au plus) ; vide après assainissement = refus rc 2. `CADRE_SANS_MODULE` est
encore lue et validée de même, mais SANS OBJET depuis S-00004278 : « aucun
module » n'est plus un refus, et `derogation_module=` n'est plus jamais écrite
(le pre-push la lit encore : la clé reste dans sa liste fermée).

LE SCRIPT DU PROJET (décisions pilote S-00004250, 1, et S-00004278, portée) : si
`scripts/verify-projet.sh` existe à la racine ET est SUIVI par git, il fait foi
pour TOUT le dépôt : la porte l'exécute (`bash scripts/verify-projet.sh`, cwd la
racine, environnement de la porte, `GIT_*` retirés) et SON rc fait foi (0 =
vert) ; elle ne joue AUCUNE séquence par défaut, ni pour la racine ni pour un
module imbriqué ou un sous-module. Les gardes restent jouées et bloquantes.
Présent mais non suivi : écarté, nommé, comme absent. Un script qui rappelle
verify.sh ou la porte ne boucle pas : la garde `PORTE_ADOPTANT_EN_COURS`, posée
par `main()` et héritée par les enfants, rend la porte imbriquée ROUGE, nommée.

SANS SCRIPT : la séquence par défaut des familles connues (npm, python, java,
swift) ; AUCUN module de famille connue : la porte NE BLOQUE PAS — les gardes
seules jugent, et un avertissement nommé est imprimé et écrit au résultat
(`avertissement=build et tests non vérifiés par le kit : ajoutez
scripts/verify-projet.sh`). Une famille connue en ÉCHEC reste ROUGE. DÉPÔT
MIXTE (binôme c4f3 ter) : un manifeste SUIVI d'un écosystème hors de la table
(`MANIFESTES_HORS_TABLE`, liste fermée : composer.json, go.mod, Gemfile,
Cargo.toml, mix.exs, *.csproj, *.sln, build.sbt), trouvé par `git ls-files` à la
racine et dans chaque sous-module peuplé, hors des dossiers que la découverte
élague (`PRUNE` : node_modules, .agents, build…), est NOMMÉ dans l'avertissement
(10 noms au plus, le reste compté) même quand des familles connues sont jouées ;
sans module connu, les deux messages font UNE valeur. Information seule : aucun
rc ne change. Avec le script suivi : aucun avertissement, le script fait foi.

SÉQUENCE PAR DÉFAUT, npm : l'install est choisi par le VERROU du module —
`pnpm-lock.yaml` → `pnpm install --frozen-lockfile` ; `yarn.lock` → `yarn
install` choisi par l'EN-TÊTE du verrou (décision 3A) : `--frozen-lockfile` pour
un verrou v1 ou d'en-tête non reconnu (refusée quand le package.json ajoute une
dépendance ou change une plage ; Yarn 1 tolère une entrée en excès),
`--immutable` pour un verrou Berry (`__metadata:` en colonne 0), le
`# yarn lockfile v1` l'emportant ; ROUGE nommé si le yarn.lock est illisible
(avant install) ou modifié par l'install, qu'elle réussisse ou échoue —
ferme le VERT silencieux de x2 ; borne : contrôle a posteriori (install déjà jouée) ;
`package-lock.json` / `npm-shrinkwrap.json` → `npm ci`
(précédence dans cet ordre quand plusieurs coexistent, imprimée) ; aucun verrou
→ ROUGE nommé (« aucun lockfile : la porte n'installe pas sans verrou »). Les
scripts `lint`, `test`, `build` se jouent par `<gestionnaire> run <s>` ; un
gestionnaire absent du PATH est ROUGE nommé.

SAST, SEUL LE NEUF BLOQUE (décisions pilote S-00004250, 2, et S-00004276) :
semgrep tourne avec `--baseline-commit <base>` ; seules les trouvailles AJOUTÉES
depuis la base bloquent, l'existant est une dette du projet. Base de la RACINE :
celle IMPOSÉE par `CADRE_SEMGREP_BASE` — `verify.sh --at` la calcule sur l'arbre
VIVANT, la CI y met la base de la PR ou, sur un push, `github.event.before` —
acceptée SEULEMENT si c'est un sha de 40 hex ANCÊTRE de HEAD ; sinon (absente,
0000…0 d'une création de branche, absente de l'historique, pas un ancêtre) la
base calculée ici (`base_semgrep`), et le repli est DIT. Base d'un SOUS-MODULE :
son gitlink à la base de son dépôt parent (ce que le changement jugé y a fait
entrer) ; repli `base_semgrep` du module, dit. BORNE (opus N3, décision pilote
S-00004290 : gardée) : un sous-module AJOUTÉ par le changement n'a pas de gitlink à la
base, le repli juge alors le plus souvent son seul dernier commit (HEAD^1), et
un finding de ses commits antérieurs PASSE. Aucune base calculable : scan
complet, dit. Le rapport JSON de semgrep est LU : un fichier dont semgrep
SIGNALE la lecture partielle (`errors`, `PartialParsing` compris, rc 0, mesuré)
est un REFUS nommé, jamais un propre ; ce qu'il récupère SANS le dire passe
(mesuré, semgrep 1.175.0 : JS `function (` ou `const y = ;` seul → `errors: []`,
scanné, rc 0). gitleaks, lui, lit toujours l'arbre entier.

CE QUE LA PORTE NE FAIT PAS : elle ne PEUPLE aucun sous-module (`verify.sh
--at` le fait, depuis l'arbre vivant) ; elle NOMME un gitlink au dossier vide
(« sous-module non peuplé ») et rend ROUGE. Elle n'installe une dépendance que
par le verrou d'un module npm (python, java, swift : rien), et ne joue aucun
`test_*.py` du kit. Elle ne construit ni ne teste un dépôt sans script et sans
module de famille connue, ni la partie hors table d'un dépôt mixte : elle le
DIT (avertissement), sans bloquer — et ne voit pas un écosystème absent de la
liste fermée, ni un manifeste non suivi.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

# --- constantes du contrat ----------------------------------------------------
MARQUEUR_KIT = (".agents", "IS_THE_KIT")
DECOUVERTE = (".agents", "security", "module_discovery.py")
RESULTAT = (".agents", "state", "local", "PORTE_RESULT")
SEMGREP_CONFIG = (".agents", "security", "semgrep.yml")
SCRIPT_PROJET = ("scripts", "verify-projet.sh")
# Canal de la base imposée (verify.sh --at, CI) et garde de réentrance (env hérité).
BASE_IMPOSEE = "CADRE_SEMGREP_BASE"
GARDE_REENTRANCE = "PORTE_ADOPTANT_EN_COURS"
AVERTISSEMENT_SANS_MODULE = ("build et tests non vérifiés par le kit : ajoutez "
                             "scripts/verify-projet.sh")
# Dépôt mixte (binôme c4f3 ter) : écosystèmes HORS de la table fermée, liste FERMÉE,
# cherchés parmi les fichiers SUIVIS pour AVERTIR — jamais pour refuser.
MANIFESTES_HORS_TABLE = ("composer.json", "go.mod", "Gemfile", "Cargo.toml", "mix.exs",
                         "*.csproj", "*.sln", "build.sbt")
AVERTISSEMENT_HORS_TABLE = ("manifeste(s) hors table ({}) : build et tests de cette partie non "
                            "vérifiés par le kit : ajoutez scripts/verify-projet.sh")
BORNE_HORS_TABLE = 10  # manifestes nommés au plus dans l'avertissement, le reste compté
# Le verrou choisit le gestionnaire et son install ; l'ORDRE est la précédence
# quand plusieurs verrous coexistent dans un même module (imprimée).
VERROUS_NPM = (
    ("pnpm-lock.yaml", "pnpm", ("install", "--frozen-lockfile")),
    ("yarn.lock", "yarn", ("install", "--frozen-lockfile")),
    ("package-lock.json", "npm", ("ci",)),
    ("npm-shrinkwrap.json", "npm", ("ci",)),
)
# Module Angular (T-01M5DFN4GRJMVQ4QZ1D88D6TXG, S-01M5E5FA5Z) : `angular.json` + script `test`
# qui lance `ng test`. Son test reçoit `--watch=false` (karma watche par défaut, vitest dès
# qu'il croit à un TTY) et `CI=true` au seul processus de test. argv mesurée (annexe C2) :
# npm ne passe le drapeau au script qu'après `--` ; pnpm et yarn (1 et Berry) le passent nu,
# et y transmettraient `--` tel quel. Borne : pnpm 6 et antérieurs non mesurés.
# `ng test`, son alias `ng t` et `ng run <app>:test` (revue de clôture, trou ng).
NG_TEST = re.compile(r"(?<![\w-])ng\s+(?:test|t|run\s+\S+:test)(?![\w-])")
WATCH_ACTIF = re.compile(r"(?<![\w-])--watch(?:=true)?(?![\w=-])(?!\s+false\b)")
WATCH_COUPE = re.compile(r"(?<![\w-])(?:--watch(?:=|\s+)false|--no-watch)(?![\w-])")
# Opérateurs de liste du shell (M1) : le drapeau ajouté en queue n'atteint que le DERNIER
# segment ; `2>&1` et `&>` ne coupent pas. Borne : une chaîne entre guillemets n'est pas lue.
CHAINE = re.compile(r"\|\||&&|;|\|&?|(?<![<>&])&(?![>&])|\n")
SANS_WATCH = {"npm": ("--", "--watch=false"), "pnpm": ("--watch=false",),
              "yarn": ("--watch=false",)}
DEROGATIONS = (
    ("CADRE_GARDES_DEGRADEES", "derogation_gardes"),
    ("CADRE_SANS_MODULE", "derogation_module"),
    ("CADRE_SANS_TEST", "derogation_test"),
)
BORNE_RAISON = 200
# « jamais `=1` » (plan rév. 2) : une raison réduite à un drapeau n'en est pas une.
JETONS_DRAPEAU = frozenset({"1", "0", "true", "false", "yes", "no", "y", "n",
                            "oui", "non", "on", "off", "vrai", "faux"})
# Catégories Unicode retirées d'une raison : contrôles C0/DEL/C1 (Cc), formats
# invisibles dont les inversions bidi (Cf), substituts isolés que `os.environ`
# fabrique d'un octet invalide et qui feraient lever l'écriture UTF-8 (Cs),
# séparateurs de ligne et de paragraphe que `splitlines` couperait (Zl, Zp).
CATEGORIES_RETIREES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
NOM_SUR = re.compile(r"[A-Za-z0-9._/@+-]+")

# --- bornes de temps (une ligne imprimée chaque fois qu'une borne mord) ------
BORNE_GIT_S = 120
BORNE_SCANNER_S = 1800
BORNE_COMMANDE_S = 7200

# Environnement des enfants : les variables par lesquelles git se laisse
# désigner un autre dépôt sont retirées (un `pre-push` exporte `GIT_DIR`).
# Précédent du kit (`module_discovery._garde_git`, `conftest.py`) : les trois
# EMPLACEMENTS de configuration sont gardés, parce que les bancs les posent.
GIT_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")

# --- précédence pytest, bornée au dossier du module (findpaths.locate_config) -
RANGS_PYTEST = ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini",
                "pyproject.toml", "tox.ini", "setup.cfg")
NORECURSE_DEFAUTS = ("*.egg", ".*", "_darcs", "build", "CVS", "dist",
                     "node_modules", "venv", "{arch}")
NORECURSE_KIT = ("agentic_v3",)

# --- gardes : un rc par scanner, une trouvaille n'est jamais une erreur ------
SANS_TEST = "sans test : "
TABLE_GITLEAKS = {0: "propre", 7: "trouvaille"}
TABLE_SEMGREP = {0: "propre", 1: "trouvaille"}

BORNE_C5 = (
    "borne des gardes — hors périmètre par défaut, AU MOINS : gitleaks "
    "`node_modules/`, `venv/lib/` et son allowlist par défaut, mode `dir` (pas "
    "l'historique) ; semgrep `node_modules/`, `vendor/`, `tests/`, `build/`, "
    "`dist/` (`.semgrepignore` par défaut) SAUF `.agents/vendor/`, dont chaque "
    "fichier suivi présent sur disque est scanné en entier, `tests/` compris "
    "(cible explicite ; liens symboliques et fichiers non suivis hors cible ; "
    "argv borné par le système, compte de cibles imprimé), et, sous "
    "`--baseline-commit`, tout ce qui n'est pas NEUF depuis la base (l'existant, "
    "les fichiers non suivis) ; liste non close"
)
VENDOR = ".agents/vendor"  # scanné en cible explicite : `-- .` l'ignore (vendor/)

# --- SAST : seul le neuf bloque (décision pilote S-00004250, 2) ---------------
# Sans base imposée (racine) ni gitlink de base (sous-module), la base de semgrep
# est `git merge-base HEAD <branche par défaut>`, résolue par dépôt dans CET
# ordre : `origin/HEAD` résolu, puis les refs de suivi distantes, puis les
# branches locales (une locale en avance sur le distant donnerait une base trop
# récente). HEAD SUR ou DERRIÈRE la branche par défaut (merge-base == HEAD) : la
# base est HEAD^1 — sinon semgrep ne verrait rien. Aucune base calculable : scan
# COMPLET, et la porte le DIT. Dans le clone de `verify.sh --at`, `origin` est
# l'arbre vivant : son `origin/HEAD` y nommerait la branche que le vivant avait
# extraite (mesuré : base = HEAD^1, un `eval` au commit 1/2 passait) — d'où la
# base imposée, calculée sur le vivant (binôme c4f3 bis, fable F1 / opus T2).
REFS_DEFAUT = ("refs/remotes/origin/main", "refs/remotes/origin/master",
               "refs/heads/main", "refs/heads/master")
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA_NUL = "0" * 40
BORNE_NOMS = 10  # fichiers nommés au plus dans un refus de lecture partielle

# --- intégrité courte du kit --------------------------------------------------
REGISTRES_HOOKS = (".claude/settings.json", ".codex/hooks.json", ".agents/hooks.json",
                   ".kimi-code/hooks.json")
REGISTRES_HOOKS_GLOB = (".github/hooks", "*.json")
CITE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:\.claude|\.codex|\.gemini|\.agents|\.github|\.kimi-code"
    r"|\.githooks|core-scripts)/[A-Za-z0-9_./-]+\.(?:sh|py))"
)


class Porte:
    """Le compte rendu d'un passage : refus, dérogations appliquées, modules."""

    def __init__(self, racine: Path, raisons: dict[str, str]) -> None:
        self.racine = racine
        self.raisons = raisons  # variable d'environnement -> raison assainie
        self.refus: list[str] = []
        self.appliquees: dict[str, str] = {}
        self.modules: list[str] = []
        self.avertissement = ""

    def rouge(self, message: str) -> None:
        self.refus.append(message)
        print(f"ROUGE : {message}", flush=True)

    def deroger(self, variable: str, message: str) -> bool:
        """Vrai si `variable` couvre ce refus ; la clé est alors notée."""
        if variable not in self.raisons:
            return False
        cle = dict(DEROGATIONS)[variable]
        self.appliquees[cle] = self.raisons[variable]
        print(f"{message} — dérogé par {variable} « {self.raisons[variable]} »", flush=True)
        return True


# --- environnement et sous-processus -----------------------------------------
def env_enfant() -> dict[str, str]:
    """L'environnement de la porte, `GIT_*` retirés (sauf les trois emplacements
    de configuration, `GIT_CONSERVE`) — rien d'autre n'est retiré ICI. Purgé quand
    `verify.sh` lance cette porte (il retire à l'entrée les cinq réglages de sa
    liste fermée avant de l'appeler) ; NON purgé quand la CI l'appelle
    directement (`.github/workflows/ci.yml`) : borne écrite dans
    verification-discipline. `PORTE_ADOPTANT_EN_COURS` y passe, voulu (réentrance)."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith("GIT_") or k in GIT_CONSERVE}


def git(depot: Path, *args: str) -> subprocess.CompletedProcess | None:
    """git en lecture, fsmonitor et hooks neutralisés ; None si git ne répond pas."""
    try:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
             "-C", str(depot), *args],
            capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
            env=env_enfant(), timeout=BORNE_GIT_S, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        print(f"borne appliquée : git {' '.join(args)} interrompu après {BORNE_GIT_S} s")
        return None
    except OSError:
        return None


def executer(argv: list[str], cwd: Path, borne: int,
             env: dict[str, str] | None = None) -> tuple[int | None, str]:
    """Lance une commande de la table fermée, sortie héritée. (rc, motif) ;
    rc None quand elle n'a pas pu tourner (motif « absent » ou « borne »).
    `env` : l'environnement de CET appel seul (défaut `env_enfant()`)."""
    print(f"$ {shlex.join(argv)}    (dans {cwd})", flush=True)
    sys.stderr.flush()
    try:
        p = subprocess.run(argv, cwd=str(cwd), env=env_enfant() if env is None else env,
                           timeout=borne, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        print(f"borne appliquée : {argv[0]} interrompu après {borne} s", flush=True)
        return None, "borne"
    except OSError as exc:
        print(f"{argv[0]} n'a pas pu être lancé : {exc}", flush=True)
        return None, "absent"
    sys.stdout.flush()
    return p.returncode, ""


# --- dérogations ----------------------------------------------------------------
def assainir(valeur: str) -> str:
    propre = "".join(c for c in valeur
                     if unicodedata.category(c) not in CATEGORIES_RETIREES)
    return propre.strip()[:BORNE_RAISON].strip()


def lire_derogations(environ) -> tuple[dict[str, str], list[str]]:
    """(raisons assainies par variable, refus d'usage). Une variable posée dont
    la raison est vide après assainissement, ou réduite à un drapeau, est un
    refus d'usage — jamais une dérogation muette."""
    raisons: dict[str, str] = {}
    refus: list[str] = []
    for variable, _cle in DEROGATIONS:
        if variable not in environ:
            continue
        raison = assainir(environ[variable])
        if not raison:
            refus.append(f"{variable} est posée mais sa raison est vide après "
                         "assainissement — écris POURQUOI, en clair")
        elif raison.casefold() in JETONS_DRAPEAU:
            refus.append(f"{variable}=« {raison} » est un drapeau, pas une raison — "
                         "écris POURQUOI, en clair")
        else:
            raisons[variable] = raison
    return raisons, refus


# --- règle de porte -----------------------------------------------------------
def decision(racine: Path) -> str:
    """'adoptant', 'kit' ou 'aucune' — la règle à deux termes, rien d'autre."""
    if racine.joinpath(*MARQUEUR_KIT).is_file():
        return "kit"
    if racine.joinpath(*DECOUVERTE).is_file():
        return "adoptant"
    return "aucune"


def dire_decision(racine: Path, verdict: str) -> None:
    marqueur = "présent" if racine.joinpath(*MARQUEUR_KIT).is_file() else "absent"
    decouverte = "présent" if racine.joinpath(*DECOUVERTE).is_file() else "absent"
    print(f"porte : {verdict.upper()} (.agents/IS_THE_KIT {marqueur}, "
          f".agents/security/module_discovery.py {decouverte})", flush=True)


# --- sous-modules -------------------------------------------------------------
def inspecter_sous_modules(porte: Porte) -> list[Path]:
    """Les gitlinks de l'INDEX (mode 160000), récursivement — pas `.gitmodules` :
    un gitlink sans entrée `.gitmodules` (dépôt embarqué par erreur) doit être
    nommé aussi. Rend les racines peuplées, relatives à la porte ; chaque défaut
    est un refus nommé, jamais un « aucun module » silencieux."""
    peuples: list[Path] = []

    def visiter(depot_rel: Path) -> None:
        p = git(porte.racine / depot_rel, "ls-files", "-s", "-z")
        if p is None or p.returncode != 0:
            porte.rouge(f"index illisible : {depot_rel.as_posix()}")
            return
        for entree in p.stdout.split("\0"):
            meta, _, chemin = entree.partition("\t")
            champs = meta.split(" ")
            if len(champs) != 3 or champs[0] != "160000":
                continue
            rel = depot_rel / chemin
            nom = rel.as_posix()
            if not NOM_SUR.fullmatch(nom):
                porte.rouge(f"chemin de sous-module refusé (hors [A-Za-z0-9._/@+-]) : {nom!r}")
                continue
            dossier = porte.racine / rel
            prefixe = git(dossier, "rev-parse", "--show-prefix") if dossier.is_dir() else None
            if prefixe is None or prefixe.returncode != 0 or prefixe.stdout.strip():
                porte.rouge(f"sous-module non peuplé : {nom} — gitlink {champs[1][:12]} sans "
                            "checkout ; sous `--at`, verify.sh le peuple depuis l'arbre vivant")
                continue
            head = git(dossier, "rev-parse", "HEAD")
            vu = head.stdout.strip() if head is not None and head.returncode == 0 else "?"
            if vu != champs[1]:
                porte.rouge(f"sous-module désaligné : {nom} — HEAD {vu[:12]} ≠ gitlink "
                            f"{champs[1][:12]}")
            etat = git(dossier, "status", "--porcelain", "--untracked-files=no",
                       "--ignore-submodules=all")
            if etat is None or etat.returncode != 0:
                porte.rouge(f"état illisible du sous-module : {nom}")
            elif etat.stdout.strip():
                porte.rouge(f"sous-module modifié : {nom} — modifications suivies non commitées")
            peuples.append(rel)
            visiter(rel)

    visiter(Path("."))
    return peuples


# --- modules ------------------------------------------------------------------
def charger_decouverte(racine: Path):
    spec = importlib.util.spec_from_file_location(
        "porte_adoptant_module_discovery", str(racine.joinpath(*DECOUVERTE)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def pyproject_du_kit(chemin: Path) -> bool:
    """Le pyproject voyagé du kit : distribution `cadre-kit` sans dépendance."""
    import tomllib
    try:
        donnees = tomllib.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    projet = donnees.get("project")
    if not isinstance(projet, dict):
        return False
    nom = re.sub(r"[-_.]+", "-", str(projet.get("name", ""))).lower()
    return nom == "cadre-kit" and not projet.get("dependencies")


def suivi(dossier: Path, nom: str) -> bool:
    """Suivi dans le dépôt PROPRIÉTAIRE : `-C` sur le dossier du module atteint
    le sous-module qui le contient, que le superprojet ne voit que par gitlink."""
    p = git(dossier, "ls-files", "--error-unmatch", "--", ":(literal)" + nom)
    return p is not None and p.returncode == 0


def modules_gardes(porte: Porte, decouverte) -> tuple[dict[Path, dict], list[tuple[str, str]]]:
    """(gardés : rel -> {"familles", "replies"}, écartés : (nom, raison)).

    Tout module sous `.agents/` est écarté : c'est l'outillage du kit, jamais un
    module du projet. `discover` y garde `.agents/ui-src` (`AGENTS_KEEP`, voulu
    pour le SCA du kit) ; sans cette exclusion, un kit privé de son marqueur
    verdirait sur les seuls tests d'ui-src au lieu de rendre « aucun module »
    (PLAN_DRIFT mesuré, décision de l'orchestrateur sur T-00001183)."""
    gardes: dict[Path, dict] = {}
    ecartes: list[tuple[str, str]] = []
    trouves = decouverte.discover(porte.racine)
    for rel in sorted(trouves, key=lambda p: (len(p.parts), p.as_posix())):
        nom = rel.as_posix()
        if not NOM_SUR.fullmatch(nom):
            porte.rouge(f"chemin de module refusé (hors [A-Za-z0-9._/@+-]) : {nom!r}")
            continue
        if rel.parts[:1] == (".agents",):
            ecartes.append((nom, "outillage du kit sous .agents/, jamais un module du projet"))
            continue
        dossier = porte.racine / rel
        familles = set()
        for famille in sorted(trouves[rel]["families"]):
            manifestes = sorted(n for n in decouverte.FAMILIES[famille]
                                if (dossier / n).is_file())
            if (rel == Path(".") and famille == "python" and "pyproject.toml" in manifestes
                    and pyproject_du_kit(dossier / "pyproject.toml")):
                manifestes.remove("pyproject.toml")
                ecartes.append(("./pyproject.toml", "distribution cadre-kit sans dépendance : "
                                "le pyproject du kit, pas un manifeste du projet"))
            if not manifestes:
                continue
            if any(suivi(dossier, n) for n in manifestes):
                familles.add(famille)
            else:
                ecartes.append((f"{nom} [{famille}]", "manifeste non suivi par git ("
                                + ", ".join(manifestes) + ")"))
        if familles:
            gardes[rel] = {"familles": familles, "replies": set(trouves[rel]["folded"])}
    return gardes, ecartes


def manifestes_hors_table(porte: Porte, peuples: list[Path], elagues) -> list[str]:
    """Les manifestes SUIVIS d'un écosystème hors de la table fermée, à la racine et
    dans chaque sous-module peuplé (chacun par SON index), hors des dossiers que la
    découverte élague (`elagues` = son `PRUNE` : node_modules, .agents — le kit —,
    build, dist, target…). Information seule : un index illisible est déjà un refus
    d'`inspecter_sous_modules`, il ne dit rien ici."""
    motifs = [":(glob)**/" + m for m in MANIFESTES_HORS_TABLE]
    trouves: set[str] = set()
    for depot in [Path(".")] + peuples:
        p = git(porte.racine / depot, "ls-files", "-z", "--", *motifs)
        for chemin in (p.stdout.split("\0") if p is not None and p.returncode == 0 else ()):
            rel = depot / chemin
            if chemin and not set(rel.parts[:-1]) & set(elagues):
                # un nom, pas une raison : contrôles retirés (une ligne), jamais tronqué
                trouves.add("".join(c for c in rel.as_posix()
                                    if unicodedata.category(c) not in CATEGORIES_RETIREES))
    return sorted(trouves)


def nommer_hors_table(noms: list[str]) -> str:
    """La liste bornée : `BORNE_HORS_TABLE` noms, le reste compté et la borne DITE."""
    vus = ", ".join(noms[:BORNE_HORS_TABLE])
    if len(noms) > BORNE_HORS_TABLE:
        vus += f" … (+{len(noms) - BORNE_HORS_TABLE} ; borne : {BORNE_HORS_TABLE} noms)"
    return vus


# --- commandes, table fermée --------------------------------------------------
def config_pytest_propre(dossier: Path, racine_du_depot: bool) -> Path | None:
    """La config propre du module selon la précédence de pytest (7 rangs),
    bornée à SON dossier. Au module racine, `pytest.ini` est le fichier du kit,
    jamais la config du projet."""
    for nom in RANGS_PYTEST:
        if racine_du_depot and nom == "pytest.ini":
            continue
        chemin = dossier / nom
        if chemin.is_file() and _porte_une_config(chemin):
            return chemin
    return None


def _porte_une_config(chemin: Path) -> bool:
    nom = chemin.name
    if nom in ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini"):
        return True  # toujours source de configuration, même vide (findpaths)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    if nom == "pyproject.toml":
        import tomllib
        try:
            outil = tomllib.loads(texte).get("tool", {})
        except ValueError:
            return False
        pytest_ = outil.get("pytest") if isinstance(outil, dict) else None
        if not isinstance(pytest_, dict):
            return False
        return any(k != "ini_options" for k in pytest_) or "ini_options" in pytest_
    section = "pytest" if nom == "tox.ini" else "tool:pytest"
    for ligne in texte.splitlines():
        ligne = ligne.rstrip()
        if ligne.startswith("[") and ligne.endswith("]") and ligne[1:-1].strip() == section:
            return True
    return False


def compter_autouse(conftest: Path) -> int:
    try:
        arbre = ast.parse(conftest.read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError):
        return -1
    total = 0
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in noeud.decorator_list:
                if isinstance(deco, ast.Call) and any(
                        k.arg == "autouse" and isinstance(k.value, ast.Constant)
                        and k.value.value is True for k in deco.keywords):
                    total += 1
    return total


def jouer_python(porte: Porte, rel: Path, ignores: list[Path], tmp: Path) -> str:
    dossier = porte.racine / rel
    if importlib.util.find_spec("pytest") is None:
        porte.rouge(f"pytest absent de {sys.executable} : module {rel.as_posix()} non testé "
                    "(la porte n'installe aucune dépendance)")
        return "rouge"
    racine_du_depot = rel == Path(".")
    config = config_pytest_propre(dossier, racine_du_depot)
    if config is None:
        config = tmp / f"pytest-{len(list(tmp.iterdir()))}.ini"
        config.write_text("[pytest]\nnorecursedirs = "
                          + " ".join(NORECURSE_DEFAUTS + NORECURSE_KIT) + "\n",
                          encoding="utf-8", newline="\n")
        print(f"config pytest : ini généré ({config.name}, norecursedirs = défauts + "
              + ", ".join(NORECURSE_KIT) + ")")
    else:
        print(f"config pytest : {config.relative_to(porte.racine).as_posix()}")
    if racine_du_depot and (porte.racine / "conftest.py").is_file():
        n = compter_autouse(porte.racine / "conftest.py")
        compte = f"{n} fixtures autouse" if n >= 0 else "fixtures autouse illisibles"
        print(f"conftest.py du kit chargé ({compte}) : il s'applique aux tests du module racine")
    argv = [sys.executable, "-m", "pytest", "-c", str(config), "--rootdir", str(dossier),
            "--confcutdir", str(dossier), "-p", "no:cacheprovider"]
    for ignore in ignores:
        argv += ["--ignore", str(porte.racine / ignore)]
    rc, motif = executer(argv, dossier, BORNE_COMMANDE_S)
    if rc == 0:
        return "vert"
    if rc == 5:
        return SANS_TEST + "pytest rc 5, aucun test collecté"
    porte.rouge(f"pytest a échoué sur {rel.as_posix()} ({motif or f'rc {rc}'})")
    return "rouge"


def lire_octets(chemin: Path) -> bytes | None:
    """Les octets du fichier, ou None s'il ne se lit pas (le ROUGE est à l'appelant)."""
    try:
        return chemin.read_bytes()
    except OSError:
        return None


def install_yarn(octets: bytes, defaut: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
    """L'install yarn ET la forme imprimée, d'après l'EN-TÊTE du verrou (décision 3A).

    Aucune E/S : l'appelant lit les octets. Les 4096 premiers OCTETS sont
    décodés avec remplacement (un caractère coupé à la borne ne lève rien).
    `# yarn lockfile v1` sur une ligne (espaces de bord ignorés) → Yarn 1, le
    défaut de la table (`--frozen-lockfile`), et il l'emporte quel que soit
    l'ordre ; `__metadata:` en colonne 0 → Berry, `--immutable` ; sinon le
    défaut, « en-tête non reconnu »."""
    tete = octets[:4096].decode("utf-8", errors="replace")
    lignes = tete.splitlines()
    v1 = any(ligne.strip() == "# yarn lockfile v1" for ligne in lignes)
    berry = any(ligne.startswith("__metadata:") for ligne in lignes)
    if v1:
        return defaut, "Yarn 1"
    if berry:
        return ("install", "--immutable"), "Berry"
    return defaut, "en-tête non reconnu"


def jouer_npm(porte: Porte, rel: Path) -> str:
    """Le VERROU d'abord (il décide du gestionnaire), le gestionnaire ensuite."""
    dossier = porte.racine / rel
    verrous = [(f, nom, install) for f, nom, install in VERROUS_NPM if (dossier / f).is_file()]
    if not verrous:
        porte.rouge(f"aucun lockfile : la porte n'installe pas sans verrou — module {rel.as_posix()} "
                    "(pnpm-lock.yaml, yarn.lock, package-lock.json ou npm-shrinkwrap.json)")
        return "rouge"
    fichier, nom, install = verrous[0]
    if len(verrous) > 1:
        print(f"plusieurs verrous dans {rel.as_posix()} ({', '.join(v[0] for v in verrous)}) : "
              f"{fichier} retenu (précédence pnpm, yarn, npm)", flush=True)
    gestionnaire = shutil.which(nom)
    if gestionnaire is None:
        porte.rouge(f"{nom} absent du PATH : module {rel.as_posix()} non construit (verrou {fichier})")
        return "rouge"
    avant = None
    if fichier == "yarn.lock":
        avant = lire_octets(dossier / fichier)
        if avant is None:
            porte.rouge(f"yarn.lock illisible : module {rel.as_posix()}")
            return "rouge"
        install, forme = install_yarn(avant, install)
        print(f"yarn.lock de {rel.as_posix()} : {forme} → yarn {' '.join(install)}", flush=True)
    try:
        scripts = json.loads((dossier / "package.json").read_text(encoding="utf-8")).get("scripts")
    except (OSError, ValueError, AttributeError):
        porte.rouge(f"package.json illisible : {rel.as_posix()}")
        return "rouge"
    scripts = scripts if isinstance(scripts, dict) else {}
    test = scripts.get("test")
    angular = ((dossier / "angular.json").is_file() and isinstance(test, str)
               and NG_TEST.search(test) is not None)
    if angular and WATCH_ACTIF.search(test):
        porte.rouge(f"module Angular {rel.as_posix()} : le script `test` ({assainir(test)}) met "
                    "`ng test` en mode watch, la porte ne finirait jamais — retirez `--watch`")
        return "rouge"
    queue, lance = queue_watch(test, nom) if angular else ((), "")
    if queue is None:
        porte.rouge(f"module Angular {rel.as_posix()} : le script `test` ({assainir(test)}) est une "
                    "chaîne où `ng test` n'est pas le dernier segment ; la porte ne réécrit pas une "
                    "chaîne et `--watch=false` posé en queue n'atteindrait pas `ng test` — posez "
                    "`--watch=false` juste après `ng test` dans le script")
        return "rouge"
    etapes = [([gestionnaire, *install], None)]
    for s in ("lint", "test", "build"):
        if s not in scripts:
            continue
        if s == "test" and angular:
            print(f"module Angular {rel.as_posix()} : {' '.join([nom, 'run', s, *queue])} "
                  f"(script lancé : {assainir(lance)}), CI=true", flush=True)
            etapes.append(([gestionnaire, "run", s, *queue], {**env_enfant(), "CI": "true"}))
        else:
            etapes.append(([gestionnaire, "run", s], None))
    for rang, (argv, env) in enumerate(etapes):
        rc, motif = executer(argv, dossier, BORNE_COMMANDE_S, env)
        if rang == 0 and fichier == "yarn.lock":
            # ferme le VERT silencieux de x2 ; borne : contrôle a posteriori (install déjà jouée)
            # AVANT le rc : Yarn 1 sauve le verrou PUIS joue install/postinstall/prepare
            apres = lire_octets(dossier / fichier)
            if apres is None or avant != apres:
                echec = f" ; l'install a AUSSI échoué ({motif or f'rc {rc}'})" if rc != 0 else ""
                porte.rouge(f"yarn install a modifié yarn.lock : module {rel.as_posix()} "
                            "(gestionnaire et verrou d'âges différents : nommez Yarn 2+ par le "
                            "champ packageManager du package.json ; l'install a déjà réécrit "
                            f"yarn.lock : restaurez-le (git -C {shlex.quote(dossier.as_posix())} "
                            f"checkout -- yarn.lock)){echec}")
                return "rouge"
        if rc != 0:
            indice = indice_karma(dossier) if angular and env is not None else ""
            porte.rouge(f"{nom} {' '.join(argv[1:])} a échoué sur {rel.as_posix()} "
                        f"({motif or f'rc {rc}'}){indice}")
            return "rouge"
    return "vert" if "test" in scripts else SANS_TEST + "aucun script `test` dans package.json"


def queue_watch(test: str, nom: str) -> tuple[tuple[str, ...] | None, str]:
    """M1 : le gestionnaire colle sa queue à la FIN du script, donc au dernier segment de la
    chaîne. Rend (queue, script réellement lancé) ; (), sans queue, quand chaque `ng test` coupe
    déjà son watch hors du dernier segment ; None quand un `ng test` sans `--watch=false` n'est
    pas le dernier segment — la porte refuse alors de réécrire la chaîne."""
    segments = CHAINE.split(test)
    if any(NG_TEST.search(s) and not WATCH_COUPE.search(s) for s in segments[:-1]):
        return None, test
    if NG_TEST.search(segments[-1]):
        return SANS_WATCH[nom], f"{test} --watch=false"
    return (), test


def indice_karma(dossier: Path) -> str:
    """Réserve C9 : sans option `browsers`, karma lance le Chrome FENÊTRÉ de sa configuration
    par défaut (@angular/build 22.2.4, karma-config.js:64), qui ne démarre pas sans écran.
    Réserve C5 : une option `karmaConfig` (builder karma) ou `runnerConfig` (builder unit-test,
    runner karma) choisit ses navigateurs elle-même ; l'indice nomme
    alors ce fichier. Borne : seules les `options` de la cible `test` sont lues, jamais ses
    `configurations`. Chaîne vide si aucun projet karma n'est concerné ou si `angular.json`
    ne se lit pas."""
    try:
        projets = json.loads((dossier / "angular.json").read_text(encoding="utf-8")).get("projects")
    except (OSError, ValueError, AttributeError):
        return ""
    for nom, projet in sorted(projets.items()) if isinstance(projets, dict) else ():
        cibles = (projet.get("architect") or projet.get("targets")) if isinstance(projet, dict) else None
        cible = cibles.get("test") if isinstance(cibles, dict) else None
        if not isinstance(cible, dict):
            continue
        options = cible.get("options") if isinstance(cible.get("options"), dict) else {}
        builder = str(cible.get("builder", ""))
        karma = builder.endswith(":karma") or (builder.endswith(":unit-test")
                                               and options.get("runner") == "karma")
        if not karma or "browsers" in options:
            continue
        # m4 : `runnerConfig` est la clé du builder unit-test (runner karma), `karmaConfig` du builder karma
        config = next((options[c] for c in ("karmaConfig", "runnerConfig")
                       if isinstance(options.get(c), str)), None)
        if config is not None:
            return (f" — projet {assainir(nom)} : karma lit ses navigateurs dans "
                    f"{assainir(config)} ; un Chrome fenêtré n'y démarre pas "
                    "sans écran (choisissez ChromeHeadless)")
        return (f" — projet {assainir(nom)} : builder karma sans option `browsers`, donc le Chrome "
                "fenêtré par défaut, qui ne démarre pas sans écran (posez \"browsers\": "
                "\"ChromeHeadless\")")
    return ""


def jouer_java(porte: Porte, rel: Path, replies: set) -> str:
    dossier = porte.racine / rel
    if (dossier / "build.gradle").is_file() or (dossier / "build.gradle.kts").is_file():
        enveloppe, argv = "gradlew", ["sh", "./gradlew", "build", "--no-daemon"]
    else:
        enveloppe, argv = "mvnw", ["sh", "./mvnw", "-B", "verify"]
    if not (dossier / enveloppe).is_file():
        porte.rouge(f"{enveloppe} absent de {rel.as_posix()} : la table fermée ne lance que "
                    "l'enveloppe du projet")
        return "rouge"
    rc, motif = executer(argv, dossier, BORNE_COMMANDE_S)
    if rc != 0:
        porte.rouge(f"{enveloppe} a échoué sur {rel.as_posix()} ({motif or f'rc {rc}'})")
        return "rouge"
    sources = [dossier] + [porte.racine / r for r in sorted(replies)]
    if any((s / "src" / "test").is_dir() for s in sources):
        return "vert"
    return SANS_TEST + "aucun src/test dans le module ni ses repliés"


def jouer_swift(porte: Porte, rel: Path) -> str:
    dossier = porte.racine / rel
    if not (dossier / "Package.swift").is_file():
        porte.rouge(f"swift sans Package.swift sur {rel.as_posix()} : aucune commande dans la "
                    "table fermée (swift build, swift test)")
        return "rouge"
    swift = shutil.which("swift")
    if swift is None:
        porte.rouge(f"swift absent du PATH : module {rel.as_posix()} non construit")
        return "rouge"
    rc, motif = executer([swift, "build"], dossier, BORNE_COMMANDE_S)
    if rc != 0:
        porte.rouge(f"swift build a échoué sur {rel.as_posix()} ({motif or f'rc {rc}'})")
        return "rouge"
    if not (dossier / "Tests").is_dir():
        return SANS_TEST + "aucun dossier Tests"
    rc, motif = executer([swift, "test"], dossier, BORNE_COMMANDE_S)
    if rc != 0:
        porte.rouge(f"swift test a échoué sur {rel.as_posix()} ({motif or f'rc {rc}'})")
        return "rouge"
    return "vert"


def script_du_projet(porte: Porte) -> Path | None:
    """`scripts/verify-projet.sh` s'il existe ET est suivi par git ; présent mais
    non suivi : écarté, NOMMÉ, et `None` (la séquence par défaut joue)."""
    nom = "/".join(SCRIPT_PROJET)
    chemin = porte.racine.joinpath(*SCRIPT_PROJET)
    if not chemin.is_file():
        return None
    if not suivi(porte.racine, nom):
        print(f"écarté : {nom} — non suivi par git : la séquence par défaut joue", flush=True)
        return None
    print(f"script du projet : {nom} (suivi par git) — il fait foi pour TOUT le dépôt (S-00004278)",
          flush=True)
    return chemin


def jouer_script_projet(porte: Porte) -> None:
    """`bash scripts/verify-projet.sh`, cwd la racine, environnement de la porte
    (`GIT_*` retirés, `env_enfant`) : SON rc fait foi."""
    nom = "/".join(SCRIPT_PROJET)
    bash = shutil.which("bash")
    if bash is None:
        porte.rouge(f"bash absent du PATH : {nom} non lancé")
        return
    rc, motif = executer([bash, nom], porte.racine, BORNE_COMMANDE_S)
    if rc != 0:
        porte.rouge(f"{nom} a échoué sur . ({motif or f'rc {rc}'})")


def jouer_modules(porte: Porte, gardes: dict[Path, dict], peuples: list[Path],
                  script: Path | None = None, hors_table: list[str] | None = None) -> None:
    """S-00004278 : le script du projet fait foi pour TOUT le dépôt ; sans lui, la
    séquence par défaut des familles connues ; sans lui ni module, un avertissement ;
    sans lui, un manifeste hors table est NOMMÉ dans l'avertissement (binôme c4f3 ter,
    dépôt mixte). Un avertissement ne change aucun rc."""
    if script is not None:
        couverts = ", ".join(f"{r.as_posix()} [{', '.join(sorted(gardes[r]['familles']))}]"
                             for r in sorted(gardes)) or "aucun"
        print(f"\n=== script du projet — il fait foi pour TOUT le dépôt, aucune séquence par défaut "
              f"(modules découverts : {couverts})", flush=True)
        jouer_script_projet(porte)
        return
    hors = nommer_hors_table(hors_table or [])
    if not gardes:
        porte.avertissement = AVERTISSEMENT_SANS_MODULE
        if hors:  # UNE valeur, UNE ligne : `porte_lire` ne recopie qu'une ligne
            porte.avertissement += f" — manifeste(s) hors table : {hors}"
        print("\nAVERTISSEMENT : aucun module de famille connue (npm, python, java, swift) ni script "
              f"du projet — {AVERTISSEMENT_SANS_MODULE} ; les gardes seules jugent, la porte ne "
              "bloque pas", flush=True)
        if "CADRE_SANS_MODULE" in porte.raisons:
            print("CADRE_SANS_MODULE posée : sans objet (S-00004278), « aucun module » n'est plus "
                  "un refus — aucune clé écrite", flush=True)
        return
    if hors:
        porte.avertissement = AVERTISSEMENT_HORS_TABLE.format(hors)
        print(f"\nAVERTISSEMENT : {porte.avertissement} — les familles connues jouent leur séquence, "
              "la porte ne bloque pas pour la partie hors table", flush=True)
    tmp = Path(tempfile.mkdtemp(prefix="porte-adoptant-"))
    try:
        for rel in sorted(gardes, key=lambda p: (len(p.parts), p.as_posix())):
            nom = rel.as_posix()
            descendants = [d for d in list(gardes) + peuples
                           if d != rel and (rel == Path(".") or rel in d.parents)]
            for famille in sorted(gardes[rel]["familles"]):
                print(f"\n=== module {nom} [{famille}]", flush=True)
                if famille == "python":
                    issue = jouer_python(porte, rel, sorted(set(descendants)), tmp)
                elif famille == "npm":
                    issue = jouer_npm(porte, rel)
                elif famille == "java":
                    issue = jouer_java(porte, rel, gardes[rel]["replies"])
                elif famille == "swift":
                    issue = jouer_swift(porte, rel)
                else:
                    porte.rouge(f"famille {famille} sans commande dans la table fermée : {nom}")
                    continue
                if issue.startswith(SANS_TEST):
                    message = f"module sans test : {nom} [{famille}] — {issue[len(SANS_TEST):]}"
                    if not porte.deroger("CADRE_SANS_TEST", message):
                        porte.rouge(message + " — sortie tracée : CADRE_SANS_TEST=\"<pourquoi>\"")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- gardes -------------------------------------------------------------------
def garde(porte: Porte, nom: str, argv: list[str], cwd: Path, table: dict[int, str],
          ou: str) -> str:
    """Rend l'issue : « propre », « trouvaille » ou « erreur »."""
    exe = shutil.which(argv[0])
    if exe is None:
        rc, motif = None, "absent du PATH"
    else:
        rc, motif = executer([exe] + argv[1:], cwd, BORNE_SCANNER_S)
        motif = {"borne": f"interrompu par la borne de {BORNE_SCANNER_S} s",
                 "absent": "non lancé"}.get(motif, motif)
    issue = table.get(rc, "erreur") if rc is not None else "erreur"
    if issue == "propre":
        print(f"{nom} : propre ({ou})", flush=True)
        return issue
    if issue == "trouvaille":
        porte.rouge(f"{nom} : TROUVAILLE sur {ou} (rc {rc}) — aucune dérogation ne couvre "
                    "une trouvaille")
        return issue
    cause = motif if rc is None else f"en ERREUR, rc {rc} — ce n'est pas une trouvaille"
    message = f"COVERAGE DEGRADED — {nom} {cause} ({ou})"
    if not porte.deroger("CADRE_GARDES_DEGRADEES", message):
        porte.rouge(f"{nom} {cause} ({ou}) — sortie tracée : CADRE_GARDES_DEGRADEES=\"<pourquoi>\"")
    return issue


def _sortie(p: subprocess.CompletedProcess | None) -> str:
    return p.stdout.strip() if p is not None and p.returncode == 0 else ""


def base_semgrep(depot: Path) -> tuple[str | None, str]:
    """(sha de base ou None, ce qui a été décidé, en clair) pour `depot`."""
    tete = _sortie(git(depot, "rev-parse", "--verify", "-q", "HEAD^{commit}"))
    if not tete:
        return None, "HEAD illisible"
    refs = [r for r in (_sortie(git(depot, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")),) if r]
    refs += [r for r in REFS_DEFAUT if r not in refs]
    raison = ("aucune branche par défaut résolue (origin/HEAD, origin/main, origin/master, main, "
              "master)")
    for ref in refs:
        if not _sortie(git(depot, "rev-parse", "--verify", "-q", ref + "^{commit}")):
            continue
        base = _sortie(git(depot, "merge-base", "HEAD", ref))
        if not base:
            raison = f"aucune base commune entre HEAD et {ref} (historique tronqué ?)"
            continue
        if base != tete:
            return base, f"base = merge-base HEAD {ref} = {base[:12]}"
        parent = _sortie(git(depot, "rev-parse", "--verify", "-q", "HEAD^1^{commit}"))
        if not parent:
            return None, f"HEAD est sur ou derrière {ref} et n'a pas de parent"
        return parent, (f"HEAD est sur ou derrière {ref} : base = HEAD^1 = {parent[:12]} (seul le "
                        "dernier commit est jugé)")
    return None, raison


def _est_ancetre(depot: Path, base: str) -> bool:
    p = git(depot, "merge-base", "--is-ancestor", base, "HEAD")
    return p is not None and p.returncode == 0


def base_imposee(depot: Path, valeur: str) -> tuple[str | None, str]:
    """La base de la RACINE. `valeur` (`CADRE_SEMGREP_BASE`) n'est acceptée que si
    c'est un sha de 40 hex, présent, ANCÊTRE de HEAD ; égale à HEAD, la règle de
    HEAD^1 s'applique. Vide : `base_semgrep`. Refusée : `base_semgrep`, et le
    refus est DIT (création de branche, force-push, valeur malformée)."""
    if not valeur:
        return base_semgrep(depot)
    if valeur == SHA_NUL:
        motif = "0000…0 : création de branche, aucun commit avant le push"
    elif not SHA40.fullmatch(valeur):
        motif = "pas un sha de 40 hex"
    elif not _sortie(git(depot, "rev-parse", "--verify", "-q", valeur + "^{commit}")):
        motif = f"{valeur[:12]} absent de l'historique (force-push ? historique tronqué ?)"
    elif not _est_ancetre(depot, valeur):
        motif = f"{valeur[:12]} n'est pas un ancêtre de HEAD (force-push ?)"
    else:
        tete = _sortie(git(depot, "rev-parse", "--verify", "-q", "HEAD^{commit}"))
        if valeur != tete:
            return valeur, f"base imposée par {BASE_IMPOSEE} = {valeur[:12]}"
        parent = _sortie(git(depot, "rev-parse", "--verify", "-q", "HEAD^1^{commit}"))
        if not parent:
            return None, f"base imposée par {BASE_IMPOSEE} = HEAD, qui n'a pas de parent"
        return parent, (f"base imposée par {BASE_IMPOSEE} = HEAD : base = HEAD^1 = {parent[:12]} "
                        "(seul le dernier commit est jugé)")
    base, dit = base_semgrep(depot)
    return base, f"{BASE_IMPOSEE} refusée ({motif}) ; repli : {dit}"


def base_sous_module(porte: Porte, rel: Path, parent: Path,
                     base_parent: str | None) -> tuple[str | None, str]:
    """La base d'un sous-module peuplé : SON gitlink à la base du dépôt parent — ce
    que le changement jugé a fait entrer dans le module. Repli `base_semgrep` du
    module, dit : parent sans base, gitlink absent à la base (module ajouté depuis),
    ou gitlink absent du module ou qui n'est pas un ancêtre de son HEAD.

    BORNE NOMMÉE, NON CORRIGÉE (opus N3, décision pilote S-00004290 : gardée) : un sous-module
    AJOUTÉ par le changement jugé n'a pas de gitlink à la base ; le repli prend sa
    merge-base avec SA branche par défaut, le plus souvent HEAD^1 (son HEAD est sur
    elle) — mesuré : base = le commit 1 de 2 qui porte le motif, donc un finding de
    ses commits ANTÉRIEURS au dernier passe, alors que tout le module est neuf."""
    dossier = porte.racine / rel
    if base_parent is None:
        motif = "le dépôt parent n'a pas de base"
    else:
        chemin = rel.relative_to(parent).as_posix()
        lien = _sortie(git(porte.racine / parent, "rev-parse", "--verify", "-q",
                           f"{base_parent}:{chemin}"))
        if not lien:
            motif = f"aucun gitlink {chemin} à la base {base_parent[:12]} du parent (module ajouté ?)"
        elif not _sortie(git(dossier, "rev-parse", "--verify", "-q", lien + "^{commit}")):
            motif = f"gitlink {lien[:12]} de la base absent du module"
        elif not _est_ancetre(dossier, lien):
            motif = f"gitlink {lien[:12]} de la base n'est pas un ancêtre du HEAD du module"
        else:
            tete = _sortie(git(dossier, "rev-parse", "--verify", "-q", "HEAD^{commit}"))
            suite = " — gitlink inchangé, rien de neuf dans ce module" if lien == tete else ""
            return lien, f"base = gitlink à la base du dépôt parent = {lien[:12]}{suite}"
    base, dit = base_semgrep(dossier)
    return base, f"{motif} ; repli : {dit}"


def erreurs_de_lecture(rapport: Path) -> list[str] | None:
    """Les fichiers dont semgrep SIGNALE la lecture partielle : les `errors` de son
    rapport JSON, `PartialParsing` compris (niveau `warn`, rc 0 — mesuré : un `eval`
    y devient invisible). Ce qu'il récupère sans le signaler n'y est pas (mesuré :
    JS invalide → `errors: []`). None : rapport absent ou illisible."""
    try:
        donnees = json.loads(rapport.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    erreurs = donnees.get("errors") if isinstance(donnees, dict) else None
    if not isinstance(erreurs, list):
        return None
    noms: set[str] = set()
    for erreur in erreurs:
        fiche = erreur if isinstance(erreur, dict) else {}
        chemin = assainir(fiche["path"]) if isinstance(fiche.get("path"), str) else ""
        sorte = fiche.get("type")
        sorte = sorte[0] if isinstance(sorte, list) and sorte else sorte
        noms.add(chemin or f"<sans chemin : {assainir(str(sorte or '?'))}>")
    return sorted(noms)


def lecture_entiere(porte: Porte, rapport: Path, ou: str) -> None:
    """Un fichier dont semgrep SIGNALE la lecture partielle est un REFUS, pas un propre."""
    erreurs = erreurs_de_lecture(rapport)
    if erreurs is None:
        cause = "n'a pas écrit de rapport JSON lisible : sa lecture entière n'est pas prouvée"
    elif not erreurs:
        return
    else:
        vus = ", ".join(erreurs[:BORNE_NOMS])
        if len(erreurs) > BORNE_NOMS:
            vus += f" … (+{len(erreurs) - BORNE_NOMS} ; borne appliquée : {BORNE_NOMS} noms imprimés)"
        cause = f"n'a pas lu en entier {len(erreurs)} fichier(s) : {vus}"
    message = f"COVERAGE DEGRADED — semgrep {cause} ({ou})"
    if not porte.deroger("CADRE_GARDES_DEGRADEES", message):
        porte.rouge(f"{message} — un fichier lu en partie est un refus, pas un propre ; sortie "
                    "tracée : CADRE_GARDES_DEGRADEES=\"<pourquoi>\"")


def cibles_vendor(dossier: Path) -> list[str] | None:
    """Les fichiers SUIVIS sous `.agents/vendor/` de `dossier`, `tests/` compris,
    présents sur disque et non liens symboliques, triés ; None si git ne les
    énumère pas. `-- .` ne les atteint pas (`vendor/` du `.semgrepignore` par
    défaut, mesuré sur semgrep 1.175.0) ; une cible explicite, si."""
    p = git(dossier, "ls-files", "-z", "--", VENDOR)
    if p is None or p.returncode != 0:
        return None
    return sorted(rel for rel in p.stdout.split("\0")
                  if rel and not (dossier / rel).is_symlink() and (dossier / rel).is_file())


def jouer_semgrep(porte: Porte, argv: list[str], dossier: Path, ou: str) -> None:
    """semgrep, puis SON rapport JSON (`--json-output`, fichier jetable) : le rc et la
    sortie texte restent ceux d'avant (mesuré, semgrep 1.175.0, avec `--quiet` et
    `--baseline-commit`). Cibles : `.` puis les fichiers de `cibles_vendor` ; s'ils
    ne sont pas énumérés, COVERAGE DEGRADED (rouge sauf dérogation) et semgrep
    tourne ENCORE sur `-- .` seul."""
    cibles = cibles_vendor(dossier)
    if cibles is None:
        alerte = f"COVERAGE DEGRADED — semgrep : fichiers suivis sous {VENDOR}/ non énumérés ({ou})"
        if not porte.deroger("CADRE_GARDES_DEGRADEES", alerte):
            porte.rouge(f"{alerte} — semgrep tourne encore sur `-- .` seul ; sortie tracée : "
                        "CADRE_GARDES_DEGRADEES=\"<pourquoi>\"")
        cibles = []
    print(f"semgrep : {len(cibles)} fichier(s) suivi(s) sous {VENDOR}/ en cible explicite ({ou})",
          flush=True)
    fd, nom = tempfile.mkstemp(prefix="porte-semgrep-", suffix=".json")
    os.close(fd)
    rapport = Path(nom)
    try:
        issue = garde(porte, "semgrep", argv + [f"--json-output={rapport}", "--", "."] + cibles,
                      dossier, TABLE_SEMGREP, ou)
        if issue in ("propre", "trouvaille"):
            lecture_entiere(porte, rapport, ou)
    finally:
        rapport.unlink(missing_ok=True)


def jouer_gardes(porte: Porte, peuples: list[Path]) -> None:
    semgrep_cfg = porte.racine.joinpath(*SEMGREP_CONFIG)
    config_kit = porte.racine / ".gitleaks.toml"
    imposee = os.environ.get(BASE_IMPOSEE, "")
    bases: dict[Path, str | None] = {}
    for rel in [Path(".")] + peuples:
        dossier = porte.racine / rel
        ou = "racine" if rel == Path(".") else rel.as_posix()
        print(f"\n=== gardes : {ou}", flush=True)
        argv = ["gitleaks", "dir", str(dossier), "--redact", "--no-banner", "--exit-code", "7"]
        propre = dossier / ".gitleaks.toml"
        config = propre if propre.is_file() else config_kit if config_kit.is_file() else None
        if config is not None:
            argv += ["--config", str(config)]
        garde(porte, "gitleaks", argv, dossier, TABLE_GITLEAKS, ou)
        if not semgrep_cfg.is_file():
            message = f"COVERAGE DEGRADED — semgrep sans règles ({'/'.join(SEMGREP_CONFIG)} absent) ({ou})"
            if not porte.deroger("CADRE_GARDES_DEGRADEES", message):
                porte.rouge(f"semgrep sans règles : {'/'.join(SEMGREP_CONFIG)} absent ({ou})")
            continue
        argv = ["semgrep", "--config", str(semgrep_cfg), "--error", "--metrics=off",
                "--disable-version-check", "--quiet"]
        if rel == Path("."):
            base, dit = base_imposee(dossier, imposee)
        else:  # le dépôt parent le plus proche : déjà jugé, l'ordre des peuplés est préfixe
            parent = next((p for p in rel.parents if p in bases), Path("."))
            base, dit = base_sous_module(porte, rel, parent, bases.get(parent))
        bases[rel] = base
        if base is not None:
            argv += ["--baseline-commit", base]
            print(f"semgrep : seul le neuf bloque — {dit} ({ou})", flush=True)
        else:
            print(f"semgrep : scan COMPLET, aucune base calculable — {dit} ({ou})", flush=True)
        jouer_semgrep(porte, argv, dossier, ou)


# --- intégrité courte du kit --------------------------------------------------
def _chaines(valeur) -> list[str]:
    if isinstance(valeur, str):
        return [valeur]
    if isinstance(valeur, dict):
        return [c for v in valeur.values() for c in _chaines(v)]
    if isinstance(valeur, list):
        return [c for v in valeur for c in _chaines(v)]
    return []


def _est_du_shell(chemin: Path) -> bool:
    """`.sh`, ou une première ligne `#!` qui nomme bash ou sh."""
    if chemin.suffix == ".sh":
        return True
    try:
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            premiere = fh.readline(256)
    except OSError:
        return False
    return premiere.startswith("#!") and re.search(r"\b(?:bash|sh)\b", premiere) is not None


def jouer_integrite(porte: Porte) -> None:
    print("\n=== intégrité courte du kit", flush=True)
    racine = porte.racine
    registres = [r for r in REGISTRES_HOOKS if (racine / r).is_file()]
    dossier_glob = racine / REGISTRES_HOOKS_GLOB[0]
    if dossier_glob.is_dir():
        registres += sorted(p.relative_to(racine).as_posix()
                            for p in dossier_glob.glob(REGISTRES_HOOKS_GLOB[1]) if p.is_file())
    cites: dict[str, str] = {}
    for registre in registres:
        try:
            donnees = json.loads((racine / registre).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            porte.rouge(f"registre de hooks illisible (JSON) : {registre}")
            continue
        hooks = donnees.get("hooks") if isinstance(donnees, dict) else None
        for chaine in _chaines(hooks):
            for chemin in CITE_RE.findall(chaine):
                cites.setdefault(chemin, registre)
    for chemin, registre in sorted(cites.items()):
        if not (racine / chemin).is_file():
            porte.rouge(f"script cité absent : {chemin} (cité par {registre})")
    bash = shutil.which("bash")
    a_lire = sorted(c for c in cites if c.endswith(".sh") and (racine / c).is_file())
    githooks = racine / ".githooks"
    if githooks.is_dir():
        a_lire += sorted(p.relative_to(racine).as_posix() for p in githooks.iterdir()
                         if p.is_file() and _est_du_shell(p))
    if bash is None and a_lire:
        porte.rouge("bash absent du PATH : `bash -n` des hooks impossible")
        a_lire = []
    for chemin in a_lire:
        try:
            p = subprocess.run([bash, "-n", str(racine / chemin)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               env=env_enfant(), timeout=BORNE_GIT_S, check=False)
        except (OSError, subprocess.TimeoutExpired):
            porte.rouge(f"`bash -n` n'a pas pu lire {chemin}")
            continue
        if p.returncode != 0:
            porte.rouge(f"syntaxe bash invalide : {chemin} ({p.stderr.strip()[:200]})")
    mode = git(racine, "ls-files", "-s", "--", ".githooks/pre-push")
    champs = mode.stdout.split(" ") if mode is not None and mode.returncode == 0 else []
    if not champs or not champs[0]:
        porte.rouge("`.githooks/pre-push` absent de l'index")
    elif champs[0] != "100755":
        porte.rouge(f"`.githooks/pre-push` n'est pas exécutable dans l'index (mode {champs[0]})")
    print(f"intégrité courte : {len(registres)} registre(s), {len(cites)} script(s) cité(s), "
          f"{len(a_lire)} fichier(s) bash lus ; aucun test_*.py du kit joué", flush=True)


# --- résultat -----------------------------------------------------------------
def ecrire_resultat(chemin: Path, sha: str, verdict: str, modules: list[str],
                    appliquees: dict[str, str], avertissement: str = "") -> None:
    lignes = [f"sha={sha}", f"verdict={verdict}", f"modules={','.join(modules)}"]
    lignes += [f"{cle}={appliquees[cle]}" for _v, cle in DEROGATIONS if cle in appliquees]
    if avertissement:
        lignes.append(f"avertissement={avertissement}")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), prefix=".PORTE_RESULT.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lignes) + "\n")
    for essai in range(6):  # Windows : un lecteur concurrent fait échouer os.replace
        try:
            os.replace(tmp, chemin)
            return
        except PermissionError:
            if essai == 5:
                raise
            time.sleep(0.05 * 2 ** essai)


def sha_de_larbre(porte: Porte) -> str:
    haut = git(porte.racine, "rev-parse", "--show-toplevel")
    if haut is None or haut.returncode != 0 or Path(haut.stdout.strip()).resolve() != porte.racine:
        porte.rouge(f"{porte.racine} n'est pas la racine d'un dépôt git")
        return ""
    tete = git(porte.racine, "rev-parse", "HEAD")
    if tete is None or tete.returncode != 0:
        porte.rouge("aucun commit : HEAD illisible")
        return ""
    return tete.stdout.strip()


def jouer(racine: Path, raisons: dict[str, str], resultat: Path) -> int:
    porte = Porte(racine, raisons)
    sha = sha_de_larbre(porte)
    print("\n=== sous-modules", flush=True)
    peuples = inspecter_sous_modules(porte)
    print(f"sous-modules peuplés : {', '.join(p.as_posix() for p in peuples) or 'aucun'}")
    print("\n=== modules", flush=True)
    decouverte = charger_decouverte(racine)
    gardes, ecartes = modules_gardes(porte, decouverte)
    for nom, raison in ecartes:
        print(f"écarté : {nom} — {raison}")
    script = script_du_projet(porte)
    hors_table = manifestes_hors_table(porte, peuples, decouverte.PRUNE)
    # Le script fait foi pour TOUT le dépôt (S-00004278) : le module jugé est `.`.
    porte.modules = ["."] if script is not None else sorted(p.as_posix() for p in gardes)
    couvert = f" — couvert par {'/'.join(SCRIPT_PROJET)}" if script is not None else ""
    for rel in sorted(gardes):
        print(f"gardé : {rel.as_posix()} [{', '.join(sorted(gardes[rel]['familles']))}]{couvert}")
    jouer_gardes(porte, peuples)
    jouer_modules(porte, gardes, peuples, script, hors_table)
    jouer_integrite(porte)
    verdict = "ECHEC" if porte.refus else "OK"
    print(f"\n=== PORTE ADOPTANT {verdict}")
    print(f"modules : {', '.join(porte.modules) or 'aucun'}")
    print("dérogations : " + ("; ".join(f"{c} « {r} »" for c, r in porte.appliquees.items())
                              or "aucune"))
    if porte.avertissement:
        print(f"avertissement : {porte.avertissement}")
    for refus in porte.refus:
        print(f"  - {refus}")
    print(BORNE_C5, flush=True)
    ecrire_resultat(resultat, sha, verdict, porte.modules, porte.appliquees, porte.avertissement)
    return 1 if porte.refus else 0


def lister(racine: Path) -> int:
    porte = Porte(racine, {})
    peuples = inspecter_sous_modules(porte)
    print(f"sous-modules peuplés : {', '.join(p.as_posix() for p in peuples) or 'aucun'}")
    decouverte = charger_decouverte(racine)
    gardes, ecartes = modules_gardes(porte, decouverte)
    for rel in sorted(gardes):
        print(f"gardé : {rel.as_posix()} [{', '.join(sorted(gardes[rel]['familles']))}]")
    for nom, raison in ecartes:
        print(f"écarté : {nom} — {raison}")
    script = script_du_projet(porte)
    if script is not None and gardes:
        print("modules couverts par le script du projet : aucune séquence par défaut ne jouera")
    if not gardes and script is None:
        print(f"aucun module gardé — {AVERTISSEMENT_SANS_MODULE}")
    hors = nommer_hors_table(manifestes_hors_table(porte, peuples, decouverte.PRUNE))
    if hors and script is None:
        print(AVERTISSEMENT_HORS_TABLE.format(hors))
    return 0


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(errors="backslashreplace")
    analyseur = argparse.ArgumentParser(
        description="The ADOPTER's push gate (T-00001183, pilot decision S-00004119).")
    # T-01M5QC86XN : nom anglais en tête, ancien nom gardé en alias, `dest` ancien explicite.
    analyseur.add_argument("--list", "--liste", dest="liste", action="store_true",
                           help="print the kept and excluded modules, run nothing (alias: --liste)")
    analyseur.add_argument("--root", help="root of the tree to judge (default: the script's own)")
    args = analyseur.parse_args(argv)
    racine = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    if not racine.is_dir():
        print(f"usage : --root {args.root!r} n'est pas un dossier", file=sys.stderr)
        return 2
    resultat = racine.joinpath(*RESULTAT)
    if not args.liste:
        try:  # AVANT tout le reste : un OK périmé ne survit à aucun refus
            resultat.unlink()
        except FileNotFoundError:
            pass
        # Réentrance (binôme c4f3 bis, fable F4) : un scripts/verify-projet.sh qui
        # rappelle verify.sh ou la porte bouclerait. La garde est posée ici et
        # héritée par chaque enfant (`env_enfant` ne retire que `GIT_*`).
        if GARDE_REENTRANCE in os.environ:
            print(f"ROUGE : réentrance — la porte adoptant tourne déjà ({GARDE_REENTRANCE} hérité "
                  "de la porte appelante) : un scripts/verify-projet.sh qui rappelle verify.sh ou "
                  "la porte bouclerait ; il ne doit jouer que le build et les tests du projet",
                  flush=True)
            return 1
        os.environ[GARDE_REENTRANCE] = str(os.getpid())
    if sys.version_info < (3, 11):
        print("ROUGE : Python >= 3.11 requis par la porte adoptant (tomllib) ; trouvé "
              + sys.version.split()[0], flush=True)
        return 1
    verdict = decision(racine)
    dire_decision(racine, verdict)
    if verdict != "adoptant":
        print("refus : cet arbre n'est pas un adoptant — la porte du kit est "
              "core-scripts/verify.sh (règle : .agents/IS_THE_KIT absent ET "
              ".agents/security/module_discovery.py présent)", file=sys.stderr)
        return 2
    if args.liste:
        return lister(racine)
    raisons, refus = lire_derogations(os.environ)
    for message in refus:
        print(f"usage : {message}", file=sys.stderr)
    if refus:
        return 2
    return jouer(racine, raisons, resultat)


if __name__ == "__main__":
    sys.exit(main())
