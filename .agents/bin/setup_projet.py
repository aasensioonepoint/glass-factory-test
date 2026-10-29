#!/usr/bin/env python3
"""setup_projet.py — la commande SETUP d'un projet adoptant : idempotente, hors ligne.

T-01M534ZNXKKP91XZRV5M5WBAYX (plan r3). Après une copie ou une sync du kit (canal
template), un adoptant doit enchaîner une douzaine de gestes avant que son
board, ses stores, son index et ses specs soient lisibles. Ce script les
ORCHESTRE — il appelle les producteurs existants, il n'en réécrit aucun — et
dit, UNE LIGNE PAR JAMBE, ce qu'il a fait :

    setup: <jambe> : <état> — <détail, raison ou remède>

`<état>` est fermé : `créé` | `déjà là` | `sans objet` | `dégradé` ; sous
`--dry-run`, rien n'est créé, donc `créé` y devient `à créer` ; chaque jambe y
SONDE en lecture ce que ferait le passage réel (`user.name`, `--stale-check`,
`--verify`, la base V3 du poste en `immutable`, `generate --stdout`), et aucun
bytecode n'est écrit (`sys.dont_write_bytecode`, PYTHONDONTWRITEBYTECODE pour
les enfants). BORNE : une spec déjà synchronisée puis modifiée y est dite
`déjà là` (le texte n'est pas reparsé sans écrire). Code de
sortie : 2 = refus avant toute jambe (hors git, sous-répertoire, marqueur du
kit, `$CADRE_PROJECT_ROOT` divergent, arbre sans paquet `cadre`) ; 1 = au moins
une jambe CRÉATRICE dégradée ; 0 sinon. Les jambes de LECTURE (ancienne base,
sondes) disent `dégradé` sans toucher au code de sortie (décision pilote
S-01M535047REKNFGFR1HE7DKGKQ).

LES JAMBES, dans l'ordre :
  1. identité (`project_init.py --name`, toujours `--name` : le nom vient de
     `--name` ou du nom de la racine, le setup n'attend aucune saisie) ou,
     présente, `--ensure-stores` ; le board a sa ligne.
     OBLIGATOIRE : une identité dégradée ARRÊTE le setup. Dette nommée : cette
     orchestration reste hors du paquet `cadre` (T-00000665, T-00000622 ;
     T-00000756 la reprendra dans `cadre init`) ;
  1b. board local ou Jira (T-01M5FQ7F3TDYQAMKQQ8Q30DDSG) : `[L/j]` sur un terminal seul,
     hors `--dry-run` et agent, défaut local ; sur j/J, `jira_setup.py configurer` hérite du
     terminal (`capture=False`), rc ≠ 0 = `dégradé` non créatrice ; sinon `sans objet` + remède ;
  2. stores machine : `chemins_des_stores` sondés, puis `initialiser` ;
  3. index : `build_index.py --root R --if-stale`, puis
     `migrate_index_to_db.py --root R --resync` (jamais `--apply`, refusé une
     fois l'étape 2 faite) et `--verify` ;
  4. ancienne base `.agents/state/v3_event_store.db` (suivie ou non), LUE
     seulement : `os.stat`, puis `store.connect(<absolu>, lecture_seule=True)`
     et `cadre.ledger.anciennes_bases.lire_specs` ; un `-wal` non vide à côté
     -> `dégradé` (immutable ignore ses trames ; un `-wal` déjà rabattu mais
     non vide donne ce dégradé par excès : borne DITE, C17) ;
  5. specs V3 : `agentic_v3 sync-spec` (amorce `-c` constante, parent d'import
     `.agents/vendor` s'il porte le paquet, sinon R) sur `docs/specs/*.md`,
     `specs/*.md` (non récursif) et les chemins de l'ancienne base, restreints
     à `git ls-files` (`\\` -> `/`, ni `..` ni absolu) ; `créé N` / `déjà là`
     par le compte de `spec_requirements` avant/après, jamais par UP-TO-DATE
     (qu'imprime aussi le premier passage) ; tout rc ≠ 0 = dégradé, ARRÊT au
     premier 3/4/5. Le rapport COMPTE ses exclusions : fichiers non suivis
     ignorés, `.md` suivis des sous-répertoires de `specs/` et `docs/specs/`
     (scan récursif : angle mort D, proposé NON), `docs/*.md` (C16) ;
  6. graphe des specs : `specs_graph.py --root R generate` (`rien à publier` ->
     `sans objet`) ;
  7. hooks git (T-01M5DJHCNK6ZX1XEG8XY0A8JR3), AVANT le bilan : contrôles (dépôt,
     `.githooks/`, valeur effective de `core.hooksPath`, hooks actifs hors `*.sample`)
     puis, sur un terminal seul, hors `--dry-run` et hors agent (`_MARQUEURS_AGENT`), la question [o/N] ;
     `o`/`oui` posent `core.hooksPath=.githooks` en config locale. Hooks actifs, valeur
     étrangère, `.githooks/` absent ou lecture échouée : diagnostic, ni question ni
     écriture, et aucune ligne du passage ne propose la commande d'activation ;
     secrets, en LECTURE (T-00001103, `_secrets`) : les noms de `git ls-files -o`
     jugés au lexique FERMÉ de `.codex/hooks/protect_paths.py`, contenu jamais
     ouvert ; un nom sans refus `Read(…)` dans `.claude/settings.json` ou
     `.claude/settings.local.json` -> `dégradé` et des lignes `secrets: proposé`
     à poser par le pilote, rien écrit, sans toucher au code de sortie ;
     bilan vérifié, en LECTURE (T-01M54GEA4BNFC7QDJVK6P53Y4B) :
     `setup_bilan.py --root R` (`--sans-ecrire` sous `--dry-run`), joué AVANT les
     sondes pour que le snapshot lise le bilan du passage ; ses lignes `bilan:`
     sont relayées ; sans KO -> `déjà là` ; KO, plantage ou contrat non écrit
     (relayé) -> `dégradé`, jamais `créé`, sans toucher au code de sortie ;
     sondes en LECTURE : sections du snapshot du dashboard (pas sous
     `--dry-run`), démons d'autres racines, portes posées, `core.hooksPath` —
     DITS (l'activation relève de la jambe hooks git) ; la fusion par champ est PROPOSÉE
     (`_pilote_fusion` : question [o/N] sur un terminal seul, python ≥ 3.11) ; un démon non vivant
     et un `core.hooksPath` non posé à côté d'un `.githooks/` sont `dégradé`,
     comme le KO que le bilan leur donne, sans toucher au code de sortie — et
     la ligne fixe « le dashboard ne lit aucune table V3 (F2) ». La dernière
     ligne, `setup: résumé rc=<n>`, compte les jambes du setup ; le verdict du
     bilan vérifié est sa propre ligne `bilan: … — exit <n>` ;
  8. `--commit` (opt-in, angle mort B) : `tasks.py --root R commit-stores --exiger`.

SORTIE : `replay-sync`. Mesuré sur un clone (mutation M7) : sans lui, la
projection V3 rend `total_tasks` identique, reconstruite depuis `runs/` au
premier EventStore. La jambe ne rougissait aucun témoin : elle n'est pas jouée.

LE CODE VIENT DE LA RACINE. Producteurs (`R/.agents/bin/…`), `agentic_v3`
(`R/.agents/vendor`, sinon R ; le vendor gagne si les deux existent) et `cadre` (`R/.agents/vendor`, sinon `R/src`) sont ceux de l'arbre ciblé, jamais d'un autre :
une racine sans eux est un arbre incomplet, refusé. Chaque enfant reçoit `R`
EXPLICITEMENT (`--root R`, ou cwd = R pour `project_init.py` et `sync-spec`),
stdin fermé (sauf `fusion_enregistrement.py --installer`, sur le « oui » du pilote, et
`jira_setup.py configurer`, sur son « j », qui hérite aussi de stdout et stderr). AUCUN littéral SQL ici (check_sql_locality) : le SQL vit sous
`.agents/vendor/cadre/ledger/`. Aucun module réseau importé (témoin AST du banc).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CREE, DEJA, SANS_OBJET, DEGRADE, A_CREER = "créé", "déjà là", "sans objet", "dégradé", "à créer"
#: Les producteurs que ce script peut lancer — liste FERMÉE (témoin AST du banc).
PRODUCTEURS = frozenset({"project_init.py", "build_index.py", "migrate_index_to_db.py",
                         "specs_graph.py", "tasks.py", "dashboard_daemon.py",
                         "fusion_enregistrement.py", "setup_bilan.py", "jira_setup.py"})
_ANCIENNE_BASE = Path(".agents") / "state" / "v3_event_store.db"
_IDENTITE = Path(".agents") / "state" / "project.json"
_SPECS_DIRS = ("docs/specs/", "specs/")
#: Remède d'une section dégradée du snapshot (annexe § 4) ; une autre se dit par sa raison.
_REMEDES = {
    "security": "aucun verdict SCA encore : /audit ($audit hors Claude Code)",
    "canal_b": "attribution OTEL absente : python3 .agents/bin/project_init.py "
               "--print-otel-env, à coller par le pilote",
    "views.governance": "trace vide, normale avant la première session de l'hôte",
}
_DELAI_S = 900


@dataclass(frozen=True)
class Sortie:
    rc: int
    stdout: str
    stderr: str

    def raison(self) -> str:
        texte = (self.stderr.strip() or self.stdout.strip()).splitlines()
        return texte[-1] if texte else f"rc {self.rc}"


class Refus(Exception):
    """Un refus AVANT toute jambe : rc 2, cause et remède dans le message."""


class Rapport:
    """Imprime chaque jambe AU MOMENT où elle est jugée (une interruption ne
    perd que la jambe en vol) et retient le code de sortie."""

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.etats: list[str] = []
        self.rc = 0

    def jambe(self, nom: str, etat: str, detail: str = "", *, creatrice: bool = True) -> str:
        if self.dry_run and etat == CREE:
            etat = A_CREER
        self.etats.append(etat)
        if etat == DEGRADE and creatrice:
            self.rc = 1
        print(f"setup: {nom} : {etat}" + (f" — {detail}" if detail else ""), flush=True)
        return etat

    def bilan(self) -> None:
        compte = {e: self.etats.count(e) for e in (CREE, A_CREER, DEJA, SANS_OBJET, DEGRADE)}
        print("setup: résumé rc=%d — " % self.rc
              + ", ".join(f"{n} {e}" for e, n in compte.items() if n), flush=True)


# --- lancer --------------------------------------------------------------------

def _executer(argv: list[str], racine: Path, *, delai: int = _DELAI_S,
              stdin: int | None = subprocess.DEVNULL, capture: bool = True) -> Sortie:
    """Le SEUL site `subprocess` : liste d'arguments, jamais de shell, stdin
    fermé (`stdin=None` : le terminal hérité, pour `--installer` et
    `jira_setup.py configurer` SEULS), cwd = racine, délai borné, rc lu.
    `capture=False` (jambe Jira SEULE) : stdout et stderr hérités, pour que les
    invites de l'enfant s'affichent ; ils reviennent alors `""`, jamais None
    (`raison()` lirait None : C12)."""
    try:
        p = subprocess.run(argv, cwd=str(racine), stdin=stdin,
                           capture_output=capture, text=True, encoding="utf-8",
                           errors="replace", timeout=delai, check=False)
    except subprocess.TimeoutExpired:
        return Sortie(124, "", f"délai de {delai} s dépassé : {' '.join(argv[1:4])}")
    except OSError as exc:
        return Sortie(127, "", f"{type(exc).__name__}: {exc}")
    return Sortie(p.returncode, p.stdout or "", p.stderr or "")


def _script(racine: Path, nom: str, *args: str,
            stdin: int | None = subprocess.DEVNULL, capture: bool = True) -> Sortie:
    if nom not in PRODUCTEURS:
        raise ValueError(f"producteur hors liste fermée : {nom}")
    chemin = racine / ".agents" / "bin" / nom
    if not chemin.is_file():
        return Sortie(127, "", f"{nom} absent de {chemin.parent} : resynchroniser le kit")
    return _executer([sys.executable, str(chemin), *args], racine, stdin=stdin, capture=capture)


#: Amorce CONSTANTE de sync-spec : le parent d'import arrive en argv[1] (jamais
#: interpolé dans le code), passe en TÊTE de sys.path, puis `agentic_v3` tourne
#: comme `-m` — le moteur du vendor gagne donc même sur un `agentic_v3/` resté
#: à la racine (cwd = R, présent aussi dans sys.path).
_AMORCE_V3 = ("import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
              "runpy.run_module('agentic_v3', run_name='__main__', alter_sys=True)")


def _parent_v3(racine: Path) -> Path:
    """Le parent d'import de `agentic_v3` : `.agents/vendor` s'il porte le
    paquet, sinon la racine (arbre d'avant le déplacement, T-01M5BXTMT1)."""
    vendor = racine / ".agents" / "vendor"
    return vendor if (vendor / "agentic_v3" / "__init__.py").is_file() else racine


def _sync_spec(racine: Path, rel: str) -> Sortie:
    # `--` : un chemin qui commence par `-` n'est jamais lu comme une option
    # (accepté par l'argparse de sync-spec : mesuré 3.14.7, et 3.9.6 en isolé).
    return _executer([sys.executable, "-c", _AMORCE_V3, str(_parent_v3(racine)),
                      "sync-spec", "--", rel], racine)


def _git(racine: Path, *args: str) -> Sortie:
    return _executer(["git", "-C", str(racine), *args], racine, delai=60)


# --- préconditions -------------------------------------------------------------

def _racine(demandee: str | None) -> Path:
    racine = Path(demandee or os.getcwd()).resolve()
    if not racine.is_dir():
        raise Refus(f"racine {racine} absente ou pas un répertoire")
    haut = _git(racine, "rev-parse", "--show-toplevel")
    if haut.rc != 0:
        raise Refus(f"{racine} n'est pas dans un dépôt git : `git init` d'abord, le "
                    "setup s'installe dans un projet, il ne le crée pas")
    toplevel = Path(haut.stdout.strip()).resolve()
    if toplevel != racine:
        raise Refus(f"{racine} est un sous-répertoire du dépôt {toplevel} : relancer "
                    f"avec --root {toplevel}")
    if (racine / ".agents" / "IS_THE_KIT").exists():
        raise Refus(f"{racine} porte .agents/IS_THE_KIT : c'est le KIT, pas un projet "
                    "adoptant — le setup ne s'y joue jamais")
    forcee = os.environ.get("CADRE_PROJECT_ROOT")
    if forcee and Path(forcee).expanduser().resolve() != racine:
        raise Refus(f"$CADRE_PROJECT_ROOT={forcee} diverge de la racine {racine} : les "
                    "stores iraient ailleurs — retirer la variable ou viser sa racine")
    if _parent_cadre(racine) is None:
        raise Refus(f"{racine} : ni .agents/vendor/cadre ni src/cadre ne portent __init__.py — "
                    "arbre incomplet, resynchroniser le kit")
    return racine


def _parent_cadre(racine: Path) -> Path | None:
    """Le parent d'import de `cadre` sous `racine` : la règle de
    `vendor_paths.parent_import` RECOPIÉE (la liste d'imports de ce fichier est
    fermée, M4 du banc) — `.agents/vendor` s'il porte `cadre/__init__.py`, sinon
    `src`, sinon None. Équivalence tenue par `test_vendor_setup.py`."""
    for parent in (racine / ".agents" / "vendor", racine / "src"):
        if (parent / "cadre" / "__init__.py").is_file():
            return parent
    return None


def _charger(racine: Path) -> None:
    """Le code de la RACINE, pas d'un autre arbre : `cadre` et les modules de
    `.agents/bin/` lus en processus (chemins des stores, forme du board).
    `.agents/bin` est RETIRÉ de `sys.path` puis inséré en tête (réserve C14 de
    T-01M5BXTGX5YN8XEXTG1PP7A5ZX). `cadre` n'entre PLUS par `sys.path`
    (S-01M5CJ820Y, T-01M5BXTRP8GKS7DMDQCTKK88DZ) : le résolveur frère
    `R/.agents/bin/vendor_paths.py`, chargé par chemin, charge le paquet EXACT
    de la racine (`charger_paquet` : `.agents/vendor/cadre`, sinon `src/cadre`)
    et vérifie sa provenance — ni un `cadre` installé (`.pth`, `PYTHONPATH`)
    ne gagne, ni le `src/` de l'adoptant ne passe devant la stdlib."""
    cible = str(racine / ".agents" / "bin")
    sys.path[:] = [entree for entree in sys.path if entree != cible]
    sys.path.insert(0, cible)
    _resolveur(racine).charger_paquet(racine, "cadre")


def _resolveur(racine: Path):
    """`R/.agents/bin/vendor_paths.py` chargé PAR CHEMIN, sous un nom privé : un
    `vendor_paths` d'un autre arbre déjà importé n'est jamais celui qui résout."""
    chemin = racine / ".agents" / "bin" / "vendor_paths.py"
    spec = importlib.util.spec_from_file_location("_setup_projet_vendor_paths", chemin)
    if not chemin.is_file() or spec is None or spec.loader is None:
        raise Refus(f"{chemin} absent : arbre incomplet, resynchroniser le kit")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # enregistré AVANT exec_module (T-00000134)
    spec.loader.exec_module(module)
    return module


def _suivis(racine: Path) -> set[str]:
    sortie = _git(racine, "ls-files", "-z")
    if sortie.rc != 0:
        raise Refus(f"git ls-files a échoué ({sortie.raison()})")
    return {p for p in sortie.stdout.split("\0") if p}


def _amorcage_detache_vivant(racine: Path) -> int | None:
    """pid de l'amorçage détaché (`amorcage_auto.py`) encore en vol, sinon None. Deux setups
    concurrents se disputent `.maintenance.lock` et échouent tous les deux (TOCTOU, R2) ; le
    run lancé PAR l'amorçage (pid = soi ou parent) passe. POSIX seul : sous Windows,
    `os.kill(pid, 0)` termine le processus."""
    if os.name != "posix":
        return None
    try:
        rec = json.loads((racine / ".agents" / "state" / "local" / "amorcage.json")
                         .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or rec.get("rc") is not None:
        return None
    pid = rec.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 \
            or pid in (os.getpid(), os.getppid()):
        return None
    try:
        os.kill(pid, 0)
    except PermissionError:
        return pid  # vivant, sous un autre utilisateur
    except OSError:  # ProcessLookupError compris : mort, l'état est périmé
        return None
    return pid


# --- 1. identité et board ------------------------------------------------------

def _forme_board(racine: Path) -> str:
    import etat_lecture  # noqa: PLC0415 — module de la racine, chargé par `_charger`

    try:
        return etat_lecture.forme(racine, "board")
    except (etat_lecture.EtatError, OSError, ValueError) as exc:
        return f"illisible ({exc})"


def _identite_et_board(racine: Path, nom: str, rapport: Rapport) -> bool:
    """Rend False si l'identité est dégradée : le setup s'ARRÊTE alors."""
    presente = (racine / _IDENTITE).exists()
    board_avant = _forme_board(racine)
    if rapport.dry_run:
        if not presente and not _git(racine, "config", "user.name").stdout.strip():
            # Le passage réel refuserait ici (project_init : user.name vide) et s'arrêterait.
            rapport.jambe("identité", DEGRADE, "git user.name est vide : l'identité ne "
                          "serait pas créée — remède : git config user.name \"Ton Nom\"")
            return False
        rapport.jambe("identité", DEJA if presente else CREE,
                      ".agents/state/project.json" + ("" if presente else f" ({nom})"))
        rapport.jambe("board", DEJA if board_avant != "absent" else CREE, f"forme {board_avant}")
        return True
    if presente:
        rapport.jambe("identité", DEJA, ".agents/state/project.json — jamais réécrite")
        sortie = _script(racine, "project_init.py", "--ensure-stores")
    else:
        sortie = _script(racine, "project_init.py", "--name", nom)
        if sortie.rc != 0 or not (racine / _IDENTITE).exists():
            remede = sortie.raison()
            if "user.name" in remede:
                remede += " — remède : git config user.name \"Ton Nom\""
            rapport.jambe("identité", DEGRADE, remede)
            return False
        rapport.jambe("identité", CREE, f".agents/state/project.json ({nom}) — le dashboard "
                                        "affiche le nom du répertoire, pas ce champ")
    if sortie.rc != 0:
        rapport.jambe("board", DEGRADE, sortie.raison())
    elif "board cree" in sortie.stdout:
        rapport.jambe("board", CREE, f"forme {_forme_board(racine)}")
    else:
        rapport.jambe("board", DEJA, f"forme {board_avant} — inchangé")
    return True


# --- 1b. board local ou Jira ---------------------------------------------------

#: Recopie de `tracabilite_jira.AGENT_CALLER_MARKERS` (liste d'imports fermée) ; égalité tenue
#: par `test_jira_setup.py`.
_MARQUEURS_AGENT = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AGENTS_HOOK_HOST",
                    "COPILOT_AGENT_SESSION_ID", "COPILOT_CLI")
QUESTION_JIRA = "Board : local ou Jira ? [L/j]"
_JIRA_REMEDE = "Jira : python3 .agents/bin/jira_setup.py configurer, au terminal du pilote"


def _board_local_ou_jira(racine: Path, rapport: Rapport) -> None:
    """Décision pilote S-01M5FQ7YS37N3HV9BQ1B32S0HQ. Défaut LOCAL : Entrée ou toute réponse
    autre que j/J. Sur j/J, `jira_setup.py configurer` hérite du terminal (stdin, stdout,
    stderr : ses invites s'affichent) ; seul son rc est lu, rc ≠ 0 = `dégradé` NON créatrice,
    les jambes suivantes jouent. `--dry-run`, agent ou stdin non terminal : rien demandé."""
    nom = "board : local ou Jira"
    if rapport.dry_run:
        rapport.jambe(nom, SANS_OBJET, f"non proposé sous --dry-run — {_JIRA_REMEDE}", creatrice=False)
        return
    if any((os.environ.get(m) or "").strip() for m in _MARQUEURS_AGENT) or sys.stdin is None \
            or not sys.stdin.isatty():
        rapport.jambe(nom, SANS_OBJET, f"stdin n'est pas un terminal (ou agent) : local — "
                                       f"{_JIRA_REMEDE}", creatrice=False)
        return
    print(QUESTION_JIRA + " ", end="", flush=True)
    reponse = sys.stdin.readline()
    if not reponse.endswith("\n"):
        print(flush=True)
    if reponse.strip() not in ("j", "J"):
        rapport.jambe(nom, SANS_OBJET, f"local (défaut) — {_JIRA_REMEDE}", creatrice=False)
        return
    sortie = _script(racine, "jira_setup.py", "configurer", stdin=None, capture=False)
    if sortie.rc == 0:
        rapport.jambe(nom, CREE, "Jira configuré et vérifié (jira_setup.py configurer)",
                      creatrice=False)
    else:
        rapport.jambe(nom, DEGRADE, f"jira_setup.py configurer rc={sortie.rc} — board local ; "
                                    f"{_JIRA_REMEDE}", creatrice=False)


# --- 2. stores machine ---------------------------------------------------------

def _stores(racine: Path, rapport: Rapport):
    """Rend les chemins des trois stores (`StoresCrees`), None s'ils sont refusés."""
    from cadre.init import initialiser  # noqa: PLC0415 — `cadre` de la racine
    from cadre.ledger.stores import chemins_des_stores  # noqa: PLC0415
    from cadre.paths import CadrePathError  # noqa: PLC0415

    noms = (("store v3", "v3_event_store"), ("store events", "events"), ("store index", "index"))
    try:
        chemins = chemins_des_stores(racine)
    except (CadrePathError, OSError, ValueError) as exc:
        for nom, _ in noms:
            rapport.jambe(nom, DEGRADE, f"chemins refusés : {exc}")
        return None
    avant = {cle: getattr(chemins, cle).exists() for _, cle in noms}
    erreur = None
    if not rapport.dry_run:
        try:
            initialiser(racine)
        except (CadrePathError, OSError, ValueError) as exc:
            erreur = f"{type(exc).__name__}: {exc}"
    for nom, cle in noms:
        chemin = getattr(chemins, cle)
        if avant[cle]:
            rapport.jambe(nom, DEJA, str(chemin))
        elif erreur is not None or (not rapport.dry_run and not chemin.exists()):
            rapport.jambe(nom, DEGRADE, erreur or f"{chemin} absent après initialiser")
        else:
            rapport.jambe(nom, CREE, str(chemin))
    return chemins


# --- 3. index ------------------------------------------------------------------

def _index(racine: Path, rapport: Rapport, index_db: Path | None) -> None:
    r = str(racine)
    if rapport.dry_run:
        sonde = _script(racine, "build_index.py", "--root", r, "--stale-check")
        courant = "INDEX CURRENT" in sonde.stdout
        rapport.jambe("index (fichiers)", DEJA if courant else CREE,
                      sonde.stdout.strip().splitlines()[0] if sonde.stdout.strip() else sonde.raison())
        if index_db is None or not index_db.exists():
            rapport.jambe("index.db", CREE, "absent : --resync puis --verify le créeraient")
        elif not courant:
            rapport.jambe("index.db", CREE, "--resync suivrait la reconstruction de l'index")
        else:
            # `--verify` LIT seulement (mode rollback-journal, aucun annexe).
            verif = _script(racine, "migrate_index_to_db.py", "--root", r, "--verify")
            if verif.rc == 0:
                rapport.jambe("index.db", DEJA, "--verify OK : --resync n'écrirait rien")
            else:
                rapport.jambe("index.db", CREE, "--verify : " + verif.raison()
                              + " — --resync le remettrait à niveau")
        return
    construit = _script(racine, "build_index.py", "--root", r, "--if-stale")
    if construit.rc != 0:
        rapport.jambe("index (fichiers)", DEGRADE, construit.raison())
    elif "INDEX CURRENT" in construit.stdout:
        rapport.jambe("index (fichiers)", DEJA, "INDEX CURRENT")
    else:
        rapport.jambe("index (fichiers)", CREE, ".agents/state/index/ (build_index.py)")
    resync = _script(racine, "migrate_index_to_db.py", "--root", r, "--resync")
    if resync.rc != 0:
        rapport.jambe("index.db", DEGRADE, "--resync : " + resync.raison())
        return
    verif = _script(racine, "migrate_index_to_db.py", "--root", r, "--verify")
    if verif.rc != 0:
        rapport.jambe("index.db", DEGRADE, "--verify : " + verif.raison())
    elif "unchanged" in resync.stdout:
        rapport.jambe("index.db", DEJA, "--resync unchanged, --verify OK")
    else:
        rapport.jambe("index.db", CREE, "--resync, --verify OK")


# --- 4. ancienne base ----------------------------------------------------------

@dataclass
class Ancienne:
    """L'état de l'ancienne base : `lignes` None tant qu'elle n'est pas lue."""

    etat: str
    detail: str
    suivie: bool = False
    lignes: list | None = None


def _ouvrir_ancienne(chemin: Path):
    """`mode=ro&immutable=1` : ni `-shm` ni `-wal` créés, aucun octet bougé."""
    from cadre.ledger import store  # noqa: PLC0415

    return store.connect(chemin, lecture_seule=True)


def _lire_ancienne(racine: Path, suivis: set[str]) -> Ancienne:
    from cadre.ledger import anciennes_bases  # noqa: PLC0415

    chemin = racine / _ANCIENNE_BASE
    suivie = _ANCIENNE_BASE.as_posix() in suivis
    try:
        os.stat(chemin)
    except FileNotFoundError:
        return Ancienne(SANS_OBJET, "aucune ancienne base .agents/state/v3_event_store.db")
    except OSError as exc:
        return Ancienne(DEGRADE, f"illisible : {exc}", suivie)
    try:
        wal = os.stat(str(chemin) + "-wal").st_size
    except FileNotFoundError:
        wal = 0
    if wal > 0:
        return Ancienne(DEGRADE, f"-wal non vide ({wal} o) à côté : lecture peut-être "
                                 "incomplète (immutable ignore ses trames ; un -wal déjà "
                                 "rabattu donne ce dégradé par excès) — non lue, jamais "
                                 "rabattue ici", suivie)
    import sqlite3  # noqa: PLC0415 — la classe d'erreur seulement, aucun appel SQL ici

    try:
        conn = _ouvrir_ancienne(chemin)
        try:
            lignes = anciennes_bases.lire_specs(conn)
        finally:
            conn.close()
    except (sqlite3.Error, ValueError) as exc:
        return Ancienne(DEGRADE, f"illisible : {type(exc).__name__}: {exc}", suivie)
    if lignes is None:
        return Ancienne(SANS_OBJET, "ancienne base sans table spec_requirements", suivie)
    return Ancienne(DEJA, "", suivie, lignes)


def _dire_ancienne(ancienne: Ancienne, nouvelles: list | None, rapport: Rapport) -> None:
    from cadre.ledger import anciennes_bases  # noqa: PLC0415

    if ancienne.lignes is None:
        rapport.jambe("ancienne base", ancienne.etat, ancienne.detail, creatrice=False)
        return
    if nouvelles is None:
        rapport.jambe("ancienne base", DEGRADE, "base V3 du poste illisible : bilan impossible",
                      creatrice=False)
        return
    b = anciennes_bases.bilan(ancienne.lignes, nouvelles)
    detail = (f"{b.lignes} lignes, suivie : {'oui' if ancienne.suivie else 'non'} — "
              f"retrouvées {b.retrouvees} ({b.identiques} identiques, {b.changees} "
              f"changées), sans source {b.sans_source}, versions perdues "
              f"{b.versions_perdues}, hors dépôt {b.hors_depot} ; jamais copiée, "
              "réécrite ni effacée — l'historique et les sections sans fichier relèvent de F1")
    if rapport.dry_run:
        detail += " — bilan contre la base du poste AVANT rejeu (--dry-run)"
    perte = b.sans_source or b.versions_perdues or b.hors_depot or b.changees
    rapport.jambe("ancienne base", DEGRADE if perte else DEJA, detail, creatrice=False)


# --- 5. specs V3 ---------------------------------------------------------------

def _directe(rel: str, prefixe: str) -> bool:
    reste = rel[len(prefixe):]
    return rel.startswith(prefixe) and rel.endswith(".md") and "/" not in reste


def _sous_un_lien(racine: Path, rel: str) -> bool:
    """Vrai si `rel` ou l'un de ses répertoires parents, sous `racine`, est un
    lien symbolique : sync-spec lirait alors un fichier hors du chemin suivi."""
    courant = racine
    for partie in rel.split("/"):
        courant = courant / partie
        if courant.is_symlink():
            return True
    return False


def _lignes_du_poste(base_v3: Path | None, *, lecture_seule: bool = False) -> list | None:
    """Les lignes de la base V3 du poste. Connexion ordinaire (elle lit le WAL) ;
    `lecture_seule` sous --dry-run (`immutable` : rien d'écrit, ni annexe ni
    rabattement du WAL, mais des trames non rabattues restent invisibles)."""
    if base_v3 is None:
        return None
    if not base_v3.exists():
        return []
    import sqlite3  # noqa: PLC0415 — la classe d'erreur seulement

    from cadre.ledger import anciennes_bases, store  # noqa: PLC0415

    try:
        conn = store.connect(base_v3, lecture_seule=lecture_seule)
        try:
            return anciennes_bases.lire_specs(conn) or []
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _specs(racine: Path, suivis: set[str], ancienne: Ancienne, base_v3: Path | None,
           rapport: Rapport) -> list | None:
    from cadre.ledger import anciennes_bases  # noqa: PLC0415

    sur_disque = {p.relative_to(racine).as_posix() for d in _SPECS_DIRS
                  if (racine / d).is_dir() for p in (racine / d).glob("*.md")}
    candidats = {p for p in suivis for d in _SPECS_DIRS if _directe(p, d)}
    non_suivis = {p for p in sur_disque if p not in suivis}
    refuses = {p for p in candidats if _sous_un_lien(racine, p)}
    for p in anciennes_bases.chemins(ancienne.lignes or []):
        # Une DONNÉE d'une base suivie : seul un `.md` sous `_SPECS_DIRS`, sans
        # lien symbolique sur le chemin, est admis (avis sécurité LOW 1).
        if not (p.endswith(".md") and p.startswith(_SPECS_DIRS)) or _sous_un_lien(racine, p):
            refuses.add(p)
        elif p in suivis:
            candidats.add(p)
        elif (racine / p).is_file():
            non_suivis.add(p)
    candidats -= refuses
    docs_md = sum(1 for p in suivis if _directe(p, "docs/"))
    # Angle mort D (scan récursif : proposé NON) — les specs rangées plus bas sont COMPTÉES.
    profondes = sum(1 for p in suivis if p.endswith(".md") and p not in candidats
                    and any(p.startswith(d) and not _directe(p, d) for d in _SPECS_DIRS))
    exclusions = (f"{len(non_suivis)} non suivi(s) ignoré(s) · {len(refuses)} refusé(s) (hors "
                  f"specs/, non .md ou lien symbolique) · sous-répertoires de specs/ non "
                  f"scannés : {profondes} · docs/*.md non scanné : {docs_md} fichier(s)")
    if not candidats:
        rapport.jambe("specs V3", SANS_OBJET, "aucune spec suivie (docs/specs/*.md, specs/*.md, "
                                              "ancienne base) — " + exclusions)
        return _lignes_du_poste(base_v3, lecture_seule=rapport.dry_run)
    if rapport.dry_run:
        poste = _lignes_du_poste(base_v3, lecture_seule=True)
        if poste is None:
            rapport.jambe("specs V3", CREE, f"{len(candidats)} fichier(s) ; base du poste "
                                            f"illisible, compte non sondé — {exclusions}")
            return None
        connus = set(anciennes_bases.chemins(poste))
        jamais = sorted(c for c in candidats if c not in connus)
        if jamais:
            rapport.jambe("specs V3", CREE, f"{len(jamais)} fichier(s) jamais synchronisé(s) sur "
                                            f"{len(candidats)} — {exclusions}")
        else:
            rapport.jambe("specs V3", DEJA, f"{len(poste)} section(s) au poste pour les "
                          f"{len(candidats)} fichier(s) ; un fichier modifié depuis donnerait une "
                          f"version neuve, non sondé sous --dry-run — {exclusions}")
        return poste
    avant = _lignes_du_poste(base_v3)
    echecs: list[str] = []
    joues = 0
    for rel in sorted(candidats):
        sortie = _sync_spec(racine, rel)
        joues += 1
        if sortie.rc != 0:
            echecs.append(f"{rel} rc {sortie.rc} ({sortie.raison()})")
            if sortie.rc in (3, 4, 5):
                break
    apres = _lignes_du_poste(base_v3)
    if echecs:
        reste = len(candidats) - joues
        rapport.jambe("specs V3", DEGRADE, "; ".join(echecs) + (f" — ARRÊT, {reste} fichier(s) "
                                                              "non joué(s)" if reste else "")
                      + " — " + exclusions)
    elif avant is None or apres is None:
        rapport.jambe("specs V3", DEGRADE, "base V3 du poste illisible : compte impossible — "
                      + exclusions)
    elif len(apres) > len(avant):
        rapport.jambe("specs V3", CREE, f"{len(apres) - len(avant)} section(s), "
                                        f"{len(candidats)} fichier(s) — {exclusions}")
    else:
        rapport.jambe("specs V3", DEJA, f"{len(apres)} section(s), {len(candidats)} "
                                        f"fichier(s) — {exclusions}")
    return apres


# --- 6. graphe des specs -------------------------------------------------------

def _graphe_a_blanc(racine: Path, rapport: Rapport) -> None:
    """--dry-run : `generate --stdout` (n'écrit rien) comparé à l'artefact publié,
    `generated_at` mis à part — la règle d'idempotence de `generate` lui-même."""
    import specs_graph  # noqa: PLC0415 — module de la racine, pour le chemin de l'artefact

    a_blanc = _script(racine, "specs_graph.py", "--root", str(racine), "generate", "--stdout")
    etat = _script(racine, "specs_graph.py", "--root", str(racine), "status")
    ligne = etat.stdout.strip().splitlines()[0] if etat.stdout.strip() else etat.raison()
    if a_blanc.rc != 0 or etat.rc != 0:
        rapport.jambe("graphe des specs", DEGRADE, a_blanc.raison() if a_blanc.rc else ligne)
        return
    if a_blanc.stdout.strip().startswith("SPECS_GRAPH: rien à publier"):
        rapport.jambe("graphe des specs", SANS_OBJET, "rien à publier (aucune tâche, aucune entrée)")
        return
    if "manuelle" in ligne:
        rapport.jambe("graphe des specs", DEJA, ligne)
        return
    try:
        nouveau = json.loads(a_blanc.stdout)
        publie = json.loads(specs_graph.artifact_path(racine).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        publie = nouveau = None
    if isinstance(nouveau, dict) and isinstance(publie, dict):
        nouveau.pop("generated_at", None)
        publie.pop("generated_at", None)
        if nouveau == publie:
            rapport.jambe("graphe des specs", DEJA, ligne)
            return
    rapport.jambe("graphe des specs", CREE, ligne)


def _graphe(racine: Path, rapport: Rapport) -> None:
    if rapport.dry_run:
        _graphe_a_blanc(racine, rapport)
        return
    sortie = _script(racine, "specs_graph.py", "--root", str(racine), "generate")
    ligne = sortie.stdout.strip().splitlines()[0] if sortie.stdout.strip() else sortie.raison()
    if sortie.rc != 0:
        rapport.jambe("graphe des specs", DEGRADE, ligne)
    elif "rien à publier" in ligne:
        rapport.jambe("graphe des specs", SANS_OBJET, "rien à publier (aucune tâche, aucune entrée)")
    elif any(m in ligne for m in ("inchangé", "manuelle", "généré par le kit")):
        rapport.jambe("graphe des specs", DEJA, ligne)
    else:
        rapport.jambe("graphe des specs", CREE, ligne)


# --- 7. bilan vérifié et sondes en lecture -------------------------------------

def _bilan(racine: Path, rapport: Rapport) -> None:
    """`setup_bilan.py` : ses lignes `bilan:` relayées, une jambe de LECTURE."""
    args = ("--root", str(racine)) + (("--sans-ecrire",) if rapport.dry_run else ())
    sortie = _script(racine, "setup_bilan.py", *args)
    lignes = [ligne for ligne in sortie.stdout.splitlines() if ligne.startswith("bilan: ")]
    # Contrat non écrit (stderr) : le snapshot lirait un bilan d'avant — relayé, dégradé.
    non_ecrit = [ligne for ligne in sortie.stderr.splitlines()
                 if ligne.startswith("bilan: contrat non écrit")]
    for ligne in lignes + non_ecrit:
        print(ligne, flush=True)
    resume = lignes[-1][len("bilan: "):] if lignes and lignes[-1].startswith("bilan: OK=") else ""
    if non_ecrit:
        rapport.jambe("bilan vérifié", DEGRADE, f"{resume} — {non_ecrit[-1][len('bilan: '):]}",
                      creatrice=False)
    elif sortie.rc == 0 and resume:
        rapport.jambe("bilan vérifié", DEJA, resume, creatrice=False)
    else:
        rapport.jambe("bilan vérifié", DEGRADE, (resume if sortie.rc == 1 and resume
                                                 else sortie.raison())
                      + " — remède de chaque KO ci-dessus ; rejouer : python3 "
                        ".agents/bin/setup_bilan.py", creatrice=False)


def _sonde_snapshot(racine: Path) -> int:
    """Mode interne `--sonde-snapshot` : les statuts des sections, en JSON."""
    _charger(racine)
    import dashboard  # noqa: PLC0415 — module de la racine

    s = dashboard.build_snapshot(racine)
    statuts: dict[str, list] = {}
    for cle, valeur in s.items():
        if isinstance(valeur, dict) and "status" in valeur:
            statuts[cle] = [valeur["status"], valeur.get("reason")]
    for cle, valeur in (s.get("views") or {}).items():
        if isinstance(valeur, dict) and "status" in valeur:
            statuts["views." + cle] = [valeur["status"], valeur.get("reason")]
    print(json.dumps(statuts, ensure_ascii=False))
    return 0


_SANS_ALERTE = ("sans core.hooksPath → .githooks, aucune alerte de fusion (activation proposée "
                "par le setup sur un terminal, ou : `git config core.hooksPath .githooks`)")
#: Hooks actifs, valeur étrangère ou lecture échouée : la commande contournerait le refus.
_SANS_ALERTE_PRUDENTE = ("sans core.hooksPath → .githooks, aucune alerte de fusion (activation "
                         "non proposée : voir la jambe hooks git)")

#: La question et les messages FIGÉS de l'annexe de T-01M5DJHCNK6ZX1XEG8XY0A8JR3, mot pour mot
#: ceux de `core-scripts/setup.sh` et `setup.ps1`.
QUESTION_HOOKS = ("Activer les hooks de ce dépôt (tous ses worktrees liés partagent ce réglage) "
                  "dans .githooks ? core.hooksPath remplace les "
                  "hooks de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; "
                  "commit-msg refuse certains sujets ; Git exécute les hooks de l’arbre courant. "
                  "[o/N]")
HOOKS_REFUS = "Hooks non activés dans ce clone ; configuration inchangée."
HOOKS_POSES = "Hooks activés dans ce dépôt (worktrees liés compris) : core.hooksPath=.githooks."
HOOKS_DEJA = "Hooks déjà activés dans ce clone ; configuration inchangée."
HOOKS_SANS_DOSSIER = ".githooks/ absent : hooks non proposés ; configuration inchangée."
_INCHANGE = "hooks non proposés ; configuration inchangée."
#: L'issue de la jambe `hooks git`, lue par `_sondes` et `_pilote_fusion`.
ACTIF, HOOKS_ACTIFS, ABSENT, ETRANGER, ECHEC, NON_POSE = (
    "actif", "hooks actifs", "absent", "étranger", "échec", "non posé")


def _vise_githooks(racine: Path, valeur: str) -> bool:
    return valeur == ".githooks" or (racine / valeur).resolve() == (racine / ".githooks").resolve()


def _sans_controle(valeur: str) -> str:
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in valeur)


def _remede_hooks_actifs(noms: list[str], repertoire: str) -> str:
    """Le texte de `setup_bilan.remede_hooks_actifs` (parité tenue par le banc) : deux voies
    d'intégration ; `pre-push` déjà là : chaîner les deux, jamais une copie par-dessus."""
    chaine = ("pre-push y existe déjà : chaîner les deux pre-push, jamais copier celui du kit "
              "par-dessus" if "pre-push" in noms else "chaîner les noms communs")
    return (f"hooks actifs dans {_sans_controle(repertoire)} "
            f"({', '.join(_sans_controle(n) for n in noms)}) : intégrer ces hooks dans "
            f".githooks/ en chaînant les noms communs, ou intégrer les hooks du kit dans "
            f"{_sans_controle(repertoire)} sans changer core.hooksPath — {chaine}")


def _hooks_git(racine: Path, rapport: Rapport) -> str:
    """Jambe `hooks git` (T-01M5DJHCNK6ZX1XEG8XY0A8JR3, décision S-01M5F3MZGDJ0TBS2WRDHW5G33K),
    jouée AVANT `_bilan`. Contrôles avant toute question : le dépôt, `.githooks/`, la valeur
    EFFECTIVE de `core.hooksPath` (posée vide, Git lit `./` : étrangère), puis les entrées hors
    `*.sample` (liens compris) sous `--git-path hooks`, un chemin relatif joint à la RACINE,
    jamais au cwd. Hooks actifs, `.githooks/` absent, valeur étrangère ou lecture échouée :
    diagnostic, ni question ni écriture. Sinon la question [o/N], sur un terminal seul, hors
    `--dry-run` et hors agent (`_MARQUEURS_AGENT`) ; seuls `o` et `oui` exacts posent
    `core.hooksPath=.githooks` en config LOCALE. Aucun hook copié ni supprimé. Jambe de LECTURE : le code de sortie n'en
    dépend jamais. Rend son issue (ACTIF, HOOKS_ACTIFS, ABSENT, ETRANGER, ECHEC, NON_POSE)."""
    def dire(etat: str, detail: str, issue: str) -> str:
        rapport.jambe("hooks git", etat, detail, creatrice=False)
        return issue

    depot = _git(racine, "rev-parse", "--git-dir")
    if depot.rc != 0:
        return dire(DEGRADE, f"lecture git échouée ({depot.raison()}) : {_INCHANGE}", ECHEC)
    if not (racine / ".githooks").is_dir():
        return dire(SANS_OBJET, HOOKS_SANS_DOSSIER, ABSENT)
    if (racine / ".githooks").is_symlink() and not (racine / ".githooks").resolve().is_relative_to(racine.resolve()):
        return dire(DEGRADE, f".githooks/ hors de cette racine : {_INCHANGE}", ETRANGER)
    lu = _git(racine, "config", "core.hooksPath")
    if lu.rc not in (0, 1):
        return dire(DEGRADE, f"lecture de core.hooksPath échouée ({lu.raison()}) : {_INCHANGE}",
                    ECHEC)
    if lu.rc == 0:
        valeur = lu.stdout.strip()
        if valeur and _vise_githooks(racine, valeur):
            return dire(DEJA, HOOKS_DEJA, ACTIF)
        return dire(DEGRADE, f"core.hooksPath = {_sans_controle(valeur) or '(vide)'}, valeur étrangère conservée "
                             f": {_INCHANGE}", ETRANGER)
    chemin = _git(racine, "rev-parse", "--git-path", "hooks")
    if chemin.rc != 0 or not chemin.stdout.strip():
        return dire(DEGRADE, f"inventaire des hooks échoué (git rev-parse --git-path hooks : "
                             f"{chemin.raison()}) : {_INCHANGE}", ECHEC)
    repertoire = Path(chemin.stdout.strip())
    if not repertoire.is_absolute():
        repertoire = racine / repertoire
    try:
        noms = sorted(p.name for p in repertoire.iterdir() if not p.name.endswith(".sample"))
    except FileNotFoundError:
        noms = []
    except OSError as exc:
        return dire(DEGRADE, f"inventaire de {repertoire} échoué ({type(exc).__name__}) : "
                             f"{_INCHANGE}", ECHEC)
    if noms:
        return dire(DEGRADE, "aucune question, configuration et hooks inchangés — remède : "
                    + _remede_hooks_actifs(noms, str(repertoire)), HOOKS_ACTIFS)
    if rapport.dry_run:
        return dire(SANS_OBJET, f"non proposé sous --dry-run ; {HOOKS_REFUS}", NON_POSE)
    if any((os.environ.get(m) or "").strip() for m in _MARQUEURS_AGENT) or sys.stdin is None \
            or not sys.stdin.isatty():
        return dire(SANS_OBJET, f"stdin n'est pas un terminal (ou agent) : non proposé ; "
                                f"{HOOKS_REFUS}", NON_POSE)
    print(QUESTION_HOOKS + " ", end="", flush=True)
    reponse = sys.stdin.readline()
    if not reponse.endswith("\n"):
        print(flush=True)
    if reponse.rstrip("\r\n") not in ("o", "oui"):  # exacte, sensible à la casse
        return dire(SANS_OBJET, HOOKS_REFUS, NON_POSE)
    pose = _git(racine, "config", "--local", "core.hooksPath", ".githooks")
    if pose.rc != 0:
        return dire(DEGRADE, f"écriture de core.hooksPath refusée ({pose.raison()})", ECHEC)
    return dire(CREE, HOOKS_POSES, ACTIF)


#: Lexique FERMÉ, recopié jeton pour jeton de `.codex/hooks/protect_paths.py` (SECRET_NAMES,
#: SECRET_EXTENSIONS) ; parité tenue par test_setup_projet_deny.py.
_NOMS_SENSIBLES = (".env", "credentials", "credential", "secret", "private-key", "private_key",
                   "id_rsa")
_EXTENSIONS_SENSIBLES = (".pem", ".key", ".p12", ".pfx", ".crt")
_PROPOSES_MAX = 20


def _sensible(rel: str) -> bool:
    """Le NOM seul, minusculisé, par sous-chaîne comme la garde (faux positifs DITS)."""
    bas = rel.lower()
    return any(j in bas for j in _NOMS_SENSIBLES) or bas.endswith(_EXTENSIONS_SENSIBLES)


def _motif_couvre(parties: list[str], motif: list[str]) -> bool:
    """`motif` (segments d'une règle `Read(./…)`) couvre `parties` ou l'un de ses
    répertoires ancêtres ; `**` vaut zéro segment ou plus, un segment se juge par
    `Path.match`. BORNE : approximation du matcher de Claude Code, jamais lui."""
    if not motif:
        return True
    if motif[0] == "**":
        return any(_motif_couvre(parties[i:], motif[1:]) for i in range(len(parties) + 1))
    return bool(parties) and Path(parties[0]).match(motif[0]) \
        and _motif_couvre(parties[1:], motif[1:])


def _refus_de_lecture(racine: Path) -> tuple[list[list[str]], list[str]]:
    """Les règles `Read(…)` relatives à la racine (`./x` ou `x`) des deux réglages Claude ;
    `/…` et `~…` ignorées. Seul `permissions.deny` est lu, aucune autre valeur n'est rendue."""
    motifs: list[list[str]] = []
    illisibles: list[str] = []
    for nom in ("settings.json", "settings.local.json"):
        chemin = racine / ".claude" / nom
        if not chemin.is_file():
            continue
        try:
            refus = json.loads(chemin.read_text(encoding="utf-8")).get("permissions", {}).get("deny", [])
            if not isinstance(refus, list):
                raise ValueError
        except (OSError, ValueError, AttributeError):
            illisibles.append(f".claude/{nom}")
            continue
        for regle in refus:
            if isinstance(regle, str) and regle.startswith("Read(") and regle.endswith(")") \
                    and not regle[5:].startswith(("/", "~")):
                segments = [s for s in regle[5:-1].split("/") if s not in ("", ".")]
                if segments:
                    motifs.append(segments)
    return motifs, illisibles


def _secrets(racine: Path, rapport: Rapport) -> None:
    """Jambe `secrets` (T-00001103), en LECTURE, jouée après `_hooks_git` : les fichiers NON
    SUIVIS (`git ls-files -o`, ignorés compris) dont le NOM porte un jeton du lexique fermé ;
    leur contenu n'est JAMAIS ouvert. Chacun sans règle `Read(…)` qui le couvre -> `dégradé`
    et une ligne `secrets: proposé "Read(./…)"` (JSON, ASCII) pour `permissions.deny` de
    `.claude/settings.local.json`, à poser par le pilote : rien n'est écrit. Au plus
    `_PROPOSES_MAX` lignes, le reste compté. Le code de sortie n'en dépend jamais."""
    def dire(etat: str, detail: str) -> None:
        rapport.jambe("secrets", etat, detail, creatrice=False)

    lu = _git(racine, "ls-files", "-o", "-z")
    if lu.rc != 0:
        return dire(DEGRADE, f"inventaire des fichiers non suivis échoué ({lu.raison()}) ; "
                             "rien écrit")
    noms = sorted({n for n in lu.stdout.split("\0") if n and _sensible(n)})
    if not noms:
        return dire(SANS_OBJET, "aucun fichier non suivi au nom de secret (lexique de la garde "
                                "des chemins) ; contenu jamais ouvert")
    motifs, illisibles = _refus_de_lecture(racine)
    nus = [n for n in noms if not any(_motif_couvre(n.split("/"), m) for m in motifs)]
    lecture = f" ; illisible(s), règles ignorées : {', '.join(illisibles)}" if illisibles else ""
    if not nus:
        return dire(DEJA, f"{len(noms)} fichier(s) non suivi(s) au nom de secret, tous sous un "
                          f"refus Read(…) ; contenu jamais ouvert{lecture}")
    dire(DEGRADE, f"{len(nus)} sur {len(noms)} fichier(s) non suivi(s) au nom de secret sans "
                  "refus de lecture — lignes proposées ci-dessous pour permissions.deny de "
                  ".claude/settings.local.json, à poser par le pilote ; rien écrit, contenu "
                  f"jamais ouvert ; lexique par sous-chaîne : faux positifs possibles{lecture}")
    for nom in nus[:_PROPOSES_MAX]:
        print("secrets: proposé " + json.dumps(f"Read(./{nom})"), flush=True)
    if len(nus) > _PROPOSES_MAX:
        print(f"secrets: {len(nus) - _PROPOSES_MAX} autre(s) non affiché(s) "
              f"(borne de {_PROPOSES_MAX} lignes)", flush=True)


def _pilote_fusion(racine: Path, rapport: Rapport, hooks: str = NON_POSE) -> None:
    """Opt-in du pilote de fusion (T-01M5F354TSM1S816112DGWNFZN, S-01M54HY9NCJP1NKKG53CN6CBV5) :
    `--verifier` ; non installé ET stdin terminal -> la question [o/N] ; seuls `o`/`oui`
    lancent `--installer` (terminal hérité, SEUL appel qui ne ferme pas stdin) puis
    `--verifier`. Jamais `--depuis` (adoptant), jamais `core.hooksPath` ni `.git/hooks`
    écrits ; `--dry-run`, agent (`_MARQUEURS_AGENT`), non-terminal : rien demandé, rien armé, DIT.
    Sous python < 3.11, le pilote ne s'importe pas (3.9.6 mesuré) : dégradé dit, rien
    proposé. Jambe de LECTURE : le code de sortie n'en dépend jamais. `hooks` : l'issue de
    `_hooks_git` ; hors NON_POSE et ACTIF, l'alerte tait la commande d'activation."""
    remede = f"{shlex.quote(sys.executable)} .agents/bin/fusion_enregistrement.py --installer"
    alerte = (_SANS_ALERTE if hooks == NON_POSE else
              "core.hooksPath → .githooks : alertes de fusion actives" if hooks == ACTIF else
              _SANS_ALERTE_PRUDENTE)
    if sys.version_info < (3, 11):
        version = ".".join(str(n) for n in sys.version_info[:2])
        rapport.jambe("fusion par champ", DEGRADE, f"pilote non proposé : python ≥ 3.11 absent "
                      f"({sys.executable} est {version}) — rien armé", creatrice=False)
        return
    fusion = _script(racine, "fusion_enregistrement.py", "--verifier")
    lignes = (fusion.stdout.strip() or fusion.raison()).splitlines()
    detail = lignes[-1]
    # Revue de clôture T-01M54GECXD (T1) : la ligne `index : …` (avant la dernière) n'entre pas dans le rc du board ;
    # un index non armé est DIT dégradé, sinon le setup dirait vert.
    index = next((ligne for ligne in lignes[:-1] if ligne.startswith("index : ")), None)
    if index and not index.startswith("index : installé"):
        rapport.jambe("fusion de l'index", DEGRADE, index, creatrice=False)
    if fusion.rc == 0:
        rapport.jambe("fusion par champ", DEJA, detail, creatrice=False)
        return
    print(f"fusion par champ : vérificateur rc={fusion.rc} — {detail}", flush=True)
    if rapport.dry_run:
        rapport.jambe("fusion par champ", SANS_OBJET, "non proposé sous --dry-run, rien armé",
                      creatrice=False)
        return
    if any((os.environ.get(m) or "").strip() for m in _MARQUEURS_AGENT) or sys.stdin is None \
            or not sys.stdin.isatty():
        rapport.jambe("fusion par champ", SANS_OBJET, "stdin n'est pas un terminal (ou "
                      f"agent) : non proposé, rien armé — remède : {remede} ; {alerte}",
                      creatrice=False)
        return
    print("Installer le pilote de fusion dans ce clone ? [o/N] ", end="", flush=True)
    reponse = sys.stdin.readline()
    if not reponse.endswith("\n"):
        print(flush=True)
    if reponse.rstrip("\r\n") not in ("o", "oui"):  # exacte, sensible à la casse (S-01M5F6TDQ9)
        rapport.jambe("fusion par champ", SANS_OBJET, f"non armé (réponse : non) — remède : "
                      f"{remede} ; {alerte}", creatrice=False)
        return
    pose = _script(racine, "fusion_enregistrement.py", "--installer", stdin=None)
    for ligne in pose.stdout.splitlines():
        print(f"fusion par champ : {ligne}", flush=True)
    for ligne in pose.stderr.splitlines():
        print(f"fusion par champ : {ligne}", flush=True)
    verifie = _script(racine, "fusion_enregistrement.py", "--verifier")
    lignes = (verifie.stdout.strip() or verifie.raison()).splitlines()
    apres = lignes[-1]
    index = next((ligne for ligne in lignes[:-1] if ligne.startswith("index : ")), None)
    if index and not index.startswith("index : installé"):
        rapport.jambe("fusion de l'index", DEGRADE, index, creatrice=False)
    if pose.rc == 0 and verifie.rc == 0:
        rapport.jambe("fusion par champ", CREE, apres, creatrice=False)
        return
    rapport.jambe("fusion par champ", DEGRADE, f"installation rc={pose.rc} ({pose.raison()}) ; "
                  f"vérificateur rc={verifie.rc} — {apres}", creatrice=False)


def _sondes(racine: Path, rapport: Rapport, hooks_issue: str = NON_POSE) -> None:
    portes = sorted(p.name for p in (racine / ".agents" / "state" / "gates").glob("*")
                    if p.is_file()) if (racine / ".agents" / "state" / "gates").is_dir() else []
    rapport.jambe("portes", DEJA if portes else SANS_OBJET,
                  ", ".join(portes) if portes else "aucune porte posée", creatrice=False)
    if rapport.dry_run:
        rapport.jambe("snapshot", SANS_OBJET, "non sondé sous --dry-run", creatrice=False)
    else:
        sortie = _executer([sys.executable, str(Path(__file__).resolve()), "--sonde-snapshot",
                            "--root", str(racine)], racine)
        try:
            statuts = json.loads(sortie.stdout) if sortie.rc == 0 else None
        except ValueError:
            statuts = None
        if not isinstance(statuts, dict):
            rapport.jambe("snapshot", DEGRADE, sortie.raison(), creatrice=False)
        else:
            ok = sorted(k for k, (st, _) in statuts.items() if st == "ok")
            rapport.jambe("snapshot", DEJA, "ok : " + ", ".join(ok), creatrice=False)
            for cle, (st, raison) in sorted(statuts.items()):
                if st != "ok":
                    rapport.jambe(f"snapshot {cle}", DEGRADE,
                                  f"{st} — {_REMEDES.get(cle, raison or '?')}", creatrice=False)
    demon = _script(racine, "dashboard_daemon.py", "--root", str(racine), "--status")
    try:
        etat_demon = json.loads(demon.stdout) if demon.rc == 0 else None
    except ValueError:
        etat_demon = None
    if not isinstance(etat_demon, dict):
        rapport.jambe("démon", DEGRADE, demon.raison(), creatrice=False)
    else:
        autres = sorted({d.get("root") for d in etat_demon.get("demons_du_poste") or []
                         if isinstance(d, dict) and d.get("root") != str(racine)} - {None})
        # Le NOMBRE seul : les racines des autres projets du poste ne sortent pas d'ici.
        rapport.jambe("démon", DEJA if etat_demon.get("status") == "alive" else DEGRADE,
                      f"démon de cette racine : {etat_demon.get('status')} ; "
                      f"{len(autres)} démon(s) d'autres racines sur le poste", creatrice=False)
    _pilote_fusion(racine, rapport, hooks_issue)
    hooks = _git(racine, "config", "core.hooksPath").stdout.strip()
    if hooks:
        rapport.jambe("core.hooksPath", DEJA, _sans_controle(hooks), creatrice=False)
    elif (racine / ".githooks").is_dir() and hooks_issue not in (NON_POSE, ACTIF):
        # C15 : après un refus (hooks actifs, valeur étrangère, lecture échouée), jamais la
        # commande qui le contournerait.
        rapport.jambe("core.hooksPath", DEGRADE, f"non armé ({hooks_issue}) — voir la jambe "
                                                    "hooks git ; configuration inchangée",
                      creatrice=False)
    elif (racine / ".githooks").is_dir():
        rapport.jambe("core.hooksPath", DEGRADE, "non armé — geste du pilote : git config "
                                                    "core.hooksPath .githooks", creatrice=False)
    else:
        rapport.jambe("core.hooksPath", SANS_OBJET, "aucun .githooks/", creatrice=False)
    rapport.jambe("dashboard", SANS_OBJET, "le dashboard ne lit aucune table V3 (F2) : les "
                                           "specs synchronisées n'y apparaissent pas encore",
                  creatrice=False)


# --- 8. commit -----------------------------------------------------------------

def _commit(racine: Path, demande: bool, rapport: Rapport) -> None:
    if not demande:
        rapport.jambe("commit des stores", SANS_OBJET, "opt-in --commit : rien committé")
        return
    if rapport.dry_run:
        rapport.jambe("commit des stores", CREE, "commit-stores --exiger, non joué sous --dry-run")
        return
    sortie = _script(racine, "tasks.py", "--root", str(racine), "commit-stores", "--exiger")
    jeton = sortie.stdout.strip().splitlines()[-1] if sortie.stdout.strip() else ""
    if sortie.rc != 0:
        rapport.jambe("commit des stores", DEGRADE, jeton or sortie.raison())
    elif jeton == "nothing":
        rapport.jambe("commit des stores", DEJA, "nothing")
    else:
        rapport.jambe("commit des stores", CREE, jeton)


# --- entrée --------------------------------------------------------------------

def _analyseur() -> argparse.ArgumentParser:
    a = argparse.ArgumentParser(
        prog="setup_projet.py",
        description="Set up an adopting project after a kit copy or sync: identity, "
                    "board, machine stores, index, V3 specs, specs graph. Idempotent, "
                    "offline; one line per leg (created | already there | n/a | degraded).")
    a.add_argument("--root", help="project root, passed explicitly to every child "
                                  "(default: the current directory, which must be the git top level)")
    a.add_argument("--dry-run", action="store_true",
                   help="say what each leg would do; write nothing")
    a.add_argument("--name", help="project name stored at identity creation "
                                  "(default: the root directory basename)")
    a.add_argument("--commit", action="store_true",
                   help="opt-in: commit the state stores (tasks.py commit-stores --exiger)")
    a.add_argument("--sonde-snapshot", action="store_true", help=argparse.SUPPRESS)
    return a


def main(argv: list[str] | None = None) -> int:
    args = _analyseur().parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if args.sonde_snapshot:
        return _sonde_snapshot(Path(args.root).resolve())
    if args.dry_run:
        # AVANT tout import de la racine : ni ce processus ni ses enfants (qui
        # héritent d'os.environ) n'écrivent de `__pycache__/` sous la racine.
        sys.dont_write_bytecode = True
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        racine = _racine(args.root)
        suivis = _suivis(racine)
        _charger(racine)  # résolveur absent, `cadre` illisible ou d'un autre arbre : refus nommé, rc 2
    except (Refus, ImportError) as refus:
        print(f"setup: REFUS — {refus}", file=sys.stderr)
        return 2
    pid = None if args.dry_run else _amorcage_detache_vivant(racine)
    if pid is not None:
        print(f"setup: REFUS — amorçage détaché en cours (pid {pid}) — attendre « amorçage : fin » "
              "dans .agents/state/local/amorcage.log", file=sys.stderr)
        return 2
    rapport = Rapport(args.dry_run)
    nom = (args.name or racine.name).strip() or racine.name
    if not _identite_et_board(racine, nom, rapport):
        print("setup: arrêt — l'identité est obligatoire : aucune autre jambe n'est jouée",
              flush=True)
        rapport.bilan()
        return rapport.rc
    _board_local_ou_jira(racine, rapport)
    chemins = _stores(racine, rapport)
    base_v3 = chemins.v3_event_store if chemins is not None else None
    _index(racine, rapport, chemins.index if chemins is not None else None)
    ancienne = _lire_ancienne(racine, suivis)
    nouvelles = _specs(racine, suivis, ancienne, base_v3, rapport)
    _dire_ancienne(ancienne, nouvelles, rapport)
    _graphe(racine, rapport)
    hooks_issue = _hooks_git(racine, rapport)  # AVANT le bilan : il lit l'état de CE passage
    _secrets(racine, rapport)
    _bilan(racine, rapport)
    _sondes(racine, rapport, hooks_issue)
    _commit(racine, args.commit, rapport)
    rapport.bilan()
    return rapport.rc


if __name__ == "__main__":
    raise SystemExit(main())
