"""RECENSEMENT BORNÉ DES PARCOURS D'ARBRE (T-00001073) — il empêche d'OUBLIER, il
n'empêche pas de TRICHER.

POURQUOI IL EXISTE. Un worktree lié, un clone posé sous `.claude/worktrees/` est
une COPIE ENTIÈRE du dépôt sous sa propre racine. Tout filet qui parcourt
l'arbre sur le disque (`os.walk`, `rglob`, `find .`) la lisait comme du code du
dépôt : la porte rougissait sur la branche d'un autre agent, ou — pire — un
plancher restait vert en comptant les fichiers du worktree. Quatre parcours ont
été corrigés ensemble (même BLOC de détection, une garde d'index par fichier),
deux autres suivent la règle NESTED du runner. Le prochain parcours écrit dans
un banc n'aurait rien de tout cela : ce recensement le fait rougir tant qu'il
n'est pas CLASSÉ.

CE QU'IL TIENT, et chaque ligne est une assertion :
  1. CANDIDATS == CLÉS. Tout fichier du PÉRIMÈTRE dont une ligne porte un idiome
     de parcours (`REGEX_PARCOURS`) est une clé de `CLASSES`, et toute clé est
     encore candidate — une classe morte se retire, elle ne s'accumule pas.
  2. PARTITION. Tout `.py`/`.sh` SUIVI est dans le périmètre ou sous une entrée
     de `PERIMETRE_EXCLU` (chacune avec sa raison, chacune couvrant encore au
     moins un fichier) : un nouveau répertoire de code rougit ici au lieu de
     sortir du recensement en silence.
  3. Le BLOC `_checkout_imbrique` est IDENTIQUE (empreinte) dans chaque
     fichier `elague:bloc` (`FICHIERS_BLOC`) ; le jeton de garde est dans chacun ;
     la garde texte M est identique entre modload et ce fichier (les gardes A
     d'automode, C de check-stale et S de module_discovery — T-00001083, où le
     doute BALAYE au lieu de lever — diffèrent VOLONTAIREMENT : jeton seul) ; le motif
     `-name .git -print` est dans le runner ET dans son miroir.
  4. Tout traversant connu est NOMMÉ au board, et sa tâche n'est pas close
     (aucun depuis T-00001083 : la classe reste permise, la liste est vide).
  5. `testpaths` n'expose pas `.claude` (ni la racine entière) : pytest y
     collecterait les bancs d'une autre branche.
  6. Chaque idiome de `IDIOMES_NON_DETECTES` échappe VRAIMENT à la regex.

CE QU'IL NE TIENT PAS — LES BORNES, ÉCRITES (L-00000187) :
  * la regex est un FILET À MAILLES : `IDIOMES_NON_DETECTES` énumère des parcours
    qu'elle ne voit pas, et cette liste n'est pas close ;
  * le périmètre est celui des BANCS et des GARDES ; le code de production sous
    `PERIMETRE_EXCLU` (dont `.agents/bin/build_index.py`, le paquet cadre à
    `src/cadre/` ou `.agents/vendor/cadre/`) n'est
    pas recensé ;
  * une CLASSE est une DÉCLARATION : rien ici ne prouve qu'un fichier classé
    `fixture` ne parcourt jamais la racine. Le recensement force la question,
    il ne la tranche pas.

adopting-tree: KIT-ONLY par prédicat — au chargement, SEULE l'existence de
`.agents/IS_THE_KIT` est lue ; le board est lu DANS un test. Copié sans eux, ce
fichier se collecte sans erreur et SAUTE.
"""
from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
# adopting-tree: marque du kit (strip: .agents/IS_THE_KIT), seule son EXISTENCE est lue au chargement
_KIT = ROOT / ".agents" / "IS_THE_KIT"

# --- LE PÉRIMÈTRE : les BANCS et les GARDES ------------------------------------
def emplacements(racine, lieux):
    """Les `lieux` (ancien, vendor) qui portent un paquet (`__init__.py`) sous `racine`."""
    return tuple(d for d in lieux if Path(racine, d, "__init__.py").is_file())


MOTEUR_LIEUX = ("agentic_v3", ".agents/vendor/agentic_v3")
MOTEUR_DIRS = emplacements(ROOT, MOTEUR_LIEUX)
# Le paquet `cadre` à ses deux emplacements (T-01M5BXTPQE3JZV3KZA6WD9P5XC) : une entrée par
# emplacement PRÉSENT, jamais une entrée morte quand l'autre est seul.
PAQUET_CADRE_LIEUX = ("src/cadre", ".agents/vendor/cadre")
DOSSIERS_PERIMETRE = (".agents/evals", "agentic_v3/tests", ".agents/vendor/agentic_v3/tests", "core-scripts", ".codex/hooks",
                      ".gemini/hooks", ".claude/hooks", ".agents/security")
GLOBS_PERIMETRE = ((".agents/bin", "test_*.py"), (".codex", "*test_*.py"), (".gemini", "*test_*.py"))
SKIP_NOMS = {".git", "node_modules", "__pycache__", ".worktrees", "dist", "build"}
# Les STORES d'état ne portent pas de code ; aucun `.py`/`.sh` n'y est suivi, et la
# partition rougirait le jour où l'un y entrerait.
SAUTE_REL = (".agents/state/",)

# Tout `.py`/`.sh` SUIVI hors du périmètre doit tomber sous l'une de ces entrées.
EXCLU_FIXE = {
    ".agents/bin/": "code de production du kit (CLI, ponts) ; ses bancs test_*.py SONT dans le perimetre",
    ".agents/pyrun.sh": "lanceur python des hooks",
    ".claude/ci/": "scripts de CI de l'hote Claude Code",
    ".claude/statusline.sh": "barre d'etat de l'hote",
    "conftest.py": "configuration pytest de session",
    "docs/": "prose et prototypes de conception, jamais executes par la porte",
    "scripts/release.sh": "outillage de release du kit (T-00000991), lit git ls-files sans parcourir le disque ; "
                          "son banc .agents/evals/test_release_script.py EST dans le perimetre",
}


def perimetre_exclu(racine):
    """`EXCLU_FIXE` plus une entrée par emplacement PRÉSENT du paquet cadre et du moteur V3."""
    exclu = dict(EXCLU_FIXE)
    for lieu in emplacements(racine, PAQUET_CADRE_LIEUX):
        exclu[f"{lieu}/"] = "paquet cadre (production)"
    for moteur in emplacements(racine, MOTEUR_LIEUX):
        exclu[f"{moteur}/"] = "moteur V3 ; ses bancs tests/ SONT dans le perimetre"
    return exclu


PERIMETRE_EXCLU = perimetre_exclu(ROOT)

# --- LA REGEX : un filet à mailles, bornée par IDIOMES_NON_DETECTES -------------
REGEX_PARCOURS = re.compile(
    r"rglob\(|os\.walk\(|\.glob\([\"']\*\*|glob\.glob\(|(^|[^a-zA-Z_.-])find +(\.|\"?\$)"
    r"|(?<!ast)\.walk\(|glob\.iglob\(|\.glob\(f?[\"']\*\*|grep +-[a-zA-Z]*[rR]|(^|[ (])rg +|find +-[LH] +"
    r"|os\.scandir\(|copytree\(")

# Parcours que la regex NE VOIT PAS — la borne écrite. Chaque exemple est
# asserté NON détecté : le jour où la regex s'élargit, cette liste doit suivre.
IDIOMES_NON_DETECTES = {
    "os.fwalk": "for r, d, f, fd in os.fwalk(racine):",
    "os.listdir recursif": "for nom in os.listdir(dossier):",
    "Path.iterdir recursif": "for p in dossier.iterdir():",
    "walk importe nu": "for r, d, f in walk(racine):",
    "find en liste d'arguments": 'subprocess.run(["find", ".", "-name", "x"])',
    "globstar bash": "for f in **/*.sh; do :; done",
    "Path.glob non recursif": 'Path(racine).glob("*/x.py")',
}

# --- LES CLASSES ---------------------------------------------------------------
# Chaque classe DÉCLARE d'où part le parcours :
#   elague:bloc                  — bloc `_checkout_imbrique` + garde d'index
#   elague:-name .git -print     — règle NESTED du runner (et son miroir)
#   traversant-connu:<T-id>      — parcourt la racine SANS élagage, tâche ouverte au board
#   fixture                      — un arbre que le banc a CONSTRUIT (jetable)
#   sous-arbre                   — un dossier NOMMÉ, jamais la racine du dépôt
#   suivis                       — une copie construite depuis git (suivis, diff)
#   donnee                       — l'idiome est du TEXTE (commentaire, vecteur, fixture)
CLASSES_PERMISES = ("elague:bloc", "elague:-name .git -print", "traversant-connu:",
                    "fixture", "sous-arbre", "suivis", "donnee")
FICHIERS_BLOC = (
    ".agents/evals/test_modload_registration.py",
    ".agents/evals/test_automode_doctrine.py",
    "core-scripts/check-stale-justification.sh",
    ".agents/evals/test_repo_walk_census.py",
    ".agents/security/module_discovery.py",
)
FICHIERS_GIT_PRINT = ("core-scripts/run-bash-tests.sh", ".agents/evals/test_bash_suites_discovery.py")
CLASSES = {
    ".agents/evals/test_modload_registration.py": ("elague:bloc", "filet modload"),
    ".agents/evals/test_automode_doctrine.py": ("elague:bloc", "filet automode (garde A)"),
    "core-scripts/check-stale-justification.sh": ("elague:bloc", "garde de la porte (garde C)"),
    ".agents/evals/test_repo_walk_census.py": ("elague:bloc", "ce recensement (garde M)"),
    "core-scripts/run-bash-tests.sh": ("elague:-name .git -print", "decouverte des suites"),
    ".agents/evals/test_bash_suites_discovery.py": ("elague:-name .git -print", "miroir du runner"),
    ".agents/security/module_discovery.py": ("elague:bloc", "discover() de la SCA (garde S, T-00001083)"),
    ".agents/bin/build_index.test.sh": ("fixture", "grep -r sous $TMP"),
    ".agents/bin/codex-dev.test.sh": ("fixture", "find -name PWNED sous $TMP jetable (mktemp -d), jamais la racine"),
    ".agents/bin/test_cadrage_plan.py": ("fixture", "rglob de b.d jetable (mkdtemp cadrage-)"),
    ".agents/bin/test_etat_lecture.py": ("fixture", "empreinte d'une racine jetable (T5)"),
    ".agents/bin/test_event_store.py": ("fixture", "rglob d'exports jetables"),
    ".agents/bin/test_migrate_layout.py": ("fixture", "rglob de self.root jetable"),
    ".agents/bin/test_otel_receiver.py": ("fixture", "rglob de tmp_path"),
    ".agents/bin/test_porte_adoptant.py": ("fixture", "rglob de self.tmp jetable (mkdtemp)"),
    ".agents/bin/test_plan_preflight.py": ("fixture", "rglob de self.racine jetable (TemporaryDirectory, faire_racine) : sentinelles"),
    "core-scripts/run-pytest-shards.test.sh": ("fixture", "find -maxdepth 1 sous $TMP/st jetable (S15)"),
    "core-scripts/feuille_de_route.test.sh": ("fixture", "find sous $TMP/ro jetable (mktemp -d), temoin (k) lecture seule (:288, :291)"),
    ".agents/bin/test_skills_github_fallback.py": ("fixture", "empreinte d'un arbre jetable"),
    ".agents/bin/test_ledger_enregistrement.py": ("sous-arbre", "copytree de .agents/state/memory/entries (W13), rglob d'un magasin jetable (tmp)"),
    ".agents/bin/test_setup_projet.py": ("fixture", "rglob d'arbres adoptants et d'etats poste jetables (mkdtemp), .git exclu"),
    ".agents/bin/test_setup_projet_deny.py": ("fixture", "rglob de self.racine sous un mkdtemp jetable (empreinte avant/apres), .git exclu"),
    ".agents/bin/test_etat_projection.py": ("fixture", "os.walk d'une racine jetable (TemporaryDirectory : projet et tmp), aucun fichier SQLite sous elle (:831)"),
    ".agents/bin/test_specs.py": ("fixture", "racine jetable (tmp)"),
    ".agents/bin/test_sync_template.py": ("fixture", "depot jetable"),
    ".agents/bin/test_tasks.py": ("fixture", "etat jetable"),
    ".agents/bin/test_tasks_acteur.py": ("fixture", "rglob/glob de l'etat poste jetable (self.etat, etat-adoptant/projets)"),
    ".agents/bin/test_tasks_fournee.py": ("fixture", "rglob de self.d jetable (mkdtemp fournee-), Banc.racine"),
    ".agents/bin/test_tasks_sessions.py": ("fixture", "rglob de self.d jetable (mkdtemp sessions-), Banc.arbre (S10)"),
    ".agents/bin/test_tasks_pont_v3_deverse.py": ("fixture", "copytree d'une racine jetable"),
    ".agents/bin/test_vendor_scope.py": ("fixture", "rglob de self.racine jetable (mkdtemp vendor-scope-)"),
    ".agents/bin/test_vendor_setup.py": ("sous-arbre", "copytree de .agents/bin et du dossier cadre résolu vers des arbres jetables"),
    ".agents/bin/test_tasks_retour.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin A)"),
    ".agents/evals/test_plan_cible_guard.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin B)"),
    ".agents/evals/test_cadre_ledger.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin H)"),
    ".agents/evals/test_cadre_roster.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin K)"),
    ".agents/evals/test_surface_kit.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin O)"),
    ".agents/bin/test_sync_template_vendor.py": ("sous-arbre", "copytree/rglob du dossier cadre résolu vers un kit jetable (témoin T)"),
    ".agents/evals/events-wiring.test.sh": ("fixture", "glob d'un dossier d'evenements jetable"),
    ".agents/evals/test_adopting_gate.py": ("fixture", "copytree d'arbres reconstruits (:665, :824)"),
    ".agents/evals/test_bascule_lecteurs.py": ("fixture", "copytree de gabarits jetables (tempfile), jamais la racine"),
    ".agents/evals/test_cadre_init.py": ("fixture", "rglob de self._base jetable (mkdtemp t968-) et de ses sous-dossiers (:945, :1044)"),
    ".agents/evals/test_cadre_init_surfaces.py": ("fixture", "os.walk de la racine temoin, spool jetable"),
    ".agents/evals/test_cadre_prefix_install.py": ("fixture", "os.walk d'un prefixe d'installation jetable (mkdtemp), jamais la racine"),
    ".agents/evals/test_cadre_workspace_executor.py": ("fixture", "Workspace.walk d'un atelier jetable"),
    ".agents/evals/test_index_machine.py": ("fixture", "racines jetables"),
    ".agents/evals/test_protect_paths_hardening.py": ("fixture", "dossier d'evenements jetable"),
    ".agents/security/gitleaks-scan.test.sh": ("fixture", "glob d'un dossier d'evenements jetable"),
    ".agents/security/gitleaks-scan-index.test.sh": ("fixture", "glob d'un TMPDIR de banc jetable (moitie scindee de gitleaks-scan.test.sh)"),
    ".agents/security/sca-python.test.sh": ("fixture", "find sous un arbre de banc"),
    ".agents/security/semgrep-scan.test.sh": ("fixture", "find -maxdepth 1 d'un dossier de marques"),
    ".agents/security/semgrep-scan-git.test.sh": ("fixture", "glob d'un TMPDIR de banc jetable (moitie scindee de semgrep-scan.test.sh)"),
    ".claude/hooks/context-retro.test.sh": ("fixture", "find -maxdepth 1 d'un dossier de marques"),
    ".claude/hooks/stop-reindex.test.sh": ("fixture", "find sous $TMP"),
    "agentic_v3/tests/test_board_bridge.py": ("fixture", "runs/ d'une racine de test"),
    "agentic_v3/tests/test_cli_zero_arg_construction.py": ("fixture", "etat jetable"),
    "agentic_v3/tests/test_ecart_runs_vers_base.py": ("fixture", "runs/ d'une racine jetable (T63, rglob *.jsonl)"),
    "agentic_v3/tests/test_journal_attente_orphelin.py": ("fixture", "racine jetable"),
    "agentic_v3/tests/test_ouvreurs_refus_store.py": ("fixture", "runs/ jetable"),
    "agentic_v3/tests/test_run_export.py": ("fixture", "runs/ jetable"),
    "agentic_v3/tests/test_run_export_partition.py": ("fixture", "racine jetable, copytree jetable"),
    ".agents/bin/test_dashboard.py": ("sous-arbre", ".agents/ui-src"),
    ".agents/bin/test_dashboard_routes_etat.py": ("sous-arbre", "copytree de .agents/state/memory/entries reels vers une racine jetable (parite reelle, :633)"),
    ".agents/bin/test_tasks_decoupe.py": ("sous-arbre", "copytree de agentic_v3 et src/cadre"),
    ".agents/evals/test_cadre_cli_installed.py": ("sous-arbre", "copytree de src/cadre"),
    ".agents/evals/test_cadre_cmd_tasks_wheel.py": ("fixture", "rglob du projet et du _moteur d'un venv jetables (mkdtemp t962w-)"),
    ".agents/evals/test_cadre_cmd_tasks.py": ("sous-arbre",".agents/state/board du kit (instantane avant/apres), src/cadre (aucun import de _moteur), projet jetable (mkdtemp)"),
    ".agents/evals/test_cadre_ledger_purete.py": ("sous-arbre", "src/cadre/ledger"),
    ".agents/evals/test_cadre_ledger_stores.py": ("sous-arbre", "src/cadre et dossiers de spool"),
    ".agents/evals/test_cadre_run_resume.py": ("sous-arbre", "copytree du paquet V3 résolu vers un kit jetable"),
    ".agents/evals/test_cadre_no_inprocess_load.py": ("sous-arbre", "src/cadre"),
    ".agents/evals/test_cadre_package.py": ("sous-arbre", "src/cadre"),
    ".agents/evals/test_cadre_state_partition.py": ("sous-arbre", "paquet cadre"),
    ".agents/evals/test_codex_model_alignment.py": ("sous-arbre", "copytree des dossiers d'hotes"),
    ".agents/evals/test_contract_diff.py": ("sous-arbre", "src/cadre"),
    ".agents/evals/test_skills_index.py": ("sous-arbre", ".agents/skills"),
    ".agents/evals/test_juges_sans_fable.py": ("sous-arbre", "rglob de .agents/adopter-seed (GRAINES_DIR) ou d'un depot jouet jetable (tmp_path), jamais la racine"),
    ".agents/security/sca-scan.sh": ("sous-arbre", "find -maxdepth sous un module decouvert"),
    ".claude/hooks/stop-reindex.sh": ("sous-arbre", "src/ et lib/"),
    ".codex/hooks/stale_index.py": ("sous-arbre", "WATCH_DIRS"),
    ".gemini/hooks/stale_index.py": ("sous-arbre", "WATCH_DIRS"),
    "core-scripts/cadre.test.sh": ("sous-arbre", "find bornes sous .claude/commands et .agents/skills"),
    "core-scripts/doctor-parity.test.sh": ("sous-arbre", "find sous six dossiers nommes (.agents core-scripts .claude/hooks .codex .gemini .githooks), .agents/state elague, jamais la racine"),
    "core-scripts/measure_shell_write_fp.py": ("sous-arbre", "dossiers de transcripts passes en argument"),
    "core-scripts/setup.sh": ("sous-arbre", "find -maxdepth 1 sous le dossier des hooks Git (rev-parse --git-path hooks), jamais la racine"),
    ".agents/security/gitleaks-scan.sh": ("suivis", "grep -r d'une copie de staging construite depuis git"),
    ".agents/evals/test_docs_only_route_contract.py": ("donnee", "texte d'un mutant"),
    ".agents/evals/test_docs_only_runner_exec_816.py": ("donnee", "texte d'un mutant"),
    ".agents/evals/test_guard_decision_parity.py": ("donnee", "vecteurs de commande"),
    # T-01M52X1W3WPKCWX1DC36NMKJB6 (2026-10-19) : la garde IaC cite `grep -r x ~/.config` dans son docstring.
    ".codex/hooks/iac_guard.py": ("donnee", "exemple grep -r dans le docstring de la garde IaC"),
    ".gemini/hooks/iac_guard.py": ("donnee", "jumeau genere de la garde IaC, meme docstring"),
    ".agents/security/sca-watch.test.sh": ("donnee", "commentaire"),
    ".claude/hooks/safe-bash.sh": ("donnee", "commentaires"),
    ".claude/hooks/safe-bash.test.sh": ("donnee", "vecteurs de commande"),
    ".claude/hooks/safe-bash-em-z.test.sh": ("fixture", "glob d'un dossier d'evenements jetable (z7) ; `uv python find` (z26) lu comme un find"),
    ".claude/hooks/safe-bash-t-y.test.sh": ("donnee", "vecteurs de commande"),
    ".codex/hooks/safe_bash.py": ("donnee", "commentaires et messages"),
    ".codex/hooks/test_guard_hooks.py": ("donnee", "vecteurs de commande"),
    ".codex/hooks/test_safe_bash_lot.py": ("donnee", "vecteurs de commande passes au hook (T-01M5D6XV3J)"),
    ".gemini/hooks/safe_bash.py": ("donnee", "commentaires et messages"),
    ".gemini/hooks/test_gemini_hooks.py": ("donnee", "vecteurs de commande"),
    "core-scripts/apply-mode.test.sh": ("donnee", "commentaire"),
    "core-scripts/build-submodule-corpus.sh": ("donnee", "message d'erreur"),
    "core-scripts/check-ci-parity.test.sh": ("donnee", "find dans un heredoc de fixture"),
    "core-scripts/check-workflow-pins.test.sh": ("donnee", "find dans un heredoc de fixture"),
}
for _ancien in tuple(CLASSES):
    if _ancien.startswith("agentic_v3/tests/"):
        _classe = CLASSES.pop(_ancien)
        for _moteur in MOTEUR_DIRS:
            CLASSES[f"{_moteur}/{_ancien.removeprefix('agentic_v3/')}"] = _classe

# Les jetons sont ASSEMBLÉS : écrits en clair ici, ils rendraient ce fichier
# porteur de son propre jeton et le mutant « jeton retiré » resterait vert.
JETON_GARDE = "# garde d'index (T-" + "00001073)"
JETON_GIT_PRINT = "-name .git " + "-print"
_BLOC_RE = re.compile(r"# checkout imbrique : debut \(T-00001073\)\n.*?# checkout imbrique : fin \(T-00001073\)\n", re.S)
_GARDE_M_RE = re.compile(r"# garde d'index \(T-00001073\) : debut\n.*?# garde d'index \(T-00001073\) : fin\n", re.S)


# --- CHECKOUTS IMBRIQUÉS (T-00001073) : ce recensement parcourt avec le bloc ----
# checkout imbrique : debut (T-00001073)
def _checkout_imbrique(chemin):
    marqueur = os.path.join(chemin, ".git")
    if os.path.isdir(marqueur):
        return True
    if not os.path.isfile(marqueur):
        return False
    try:
        with open(marqueur, encoding="utf-8", errors="replace") as fh:
            ligne = fh.readline(4096)
    except OSError:
        return False
    m = re.match(r"gitdir:\s*(.+?)\s*$", ligne)
    return bool(m and re.search(r"/worktrees/[^/]+/?$", m.group(1).replace("\\", "/")))
# checkout imbrique : fin (T-00001073)


# Garde texte M, IDENTIQUE à celle de test_modload_registration.py (empreinte) :
# la requête d'index neutralise `core.fsmonitor` et `core.hooksPath` du dépôt
# interrogé, chaque appel git est borné à 60 s et `TimeoutExpired` remonte
# (S-00003664 ; bornes détaillées dans modload).
# garde d'index (T-00001073) : debut
_GARDE_CONSERVE = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
_GARDE_HORS_DEPOT = "not a git repository (or any"


def _garde_env():
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
    e["LC_ALL"] = "C"
    e["LANGUAGE"] = ""
    return e


def _garde_mode(racine):
    p = subprocess.run(["git", "-C", racine, "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
    if p.returncode == 0 and p.stdout.strip() == "true":
        return "git"
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        return "none"
    raise RuntimeError(
        f"garde d'index : git ne sait pas dire si {racine} est un depot (rc={p.returncode}, "
        f"stdout={p.stdout.strip()!r}, stderr={p.stderr.strip()!r}) — ce n est PAS lu comme "
        "« hors depot » : un checkout imbrique y serait elague en silence")


def _enregistre(chemin, mode):
    if mode == "none":
        return False
    p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                        "-C", os.path.dirname(chemin), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(chemin)],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
    if p.returncode == 0:
        return bool(p.stdout.strip())
    if p.returncode == 128 and _GARDE_HORS_DEPOT in p.stderr.lower():
        raise RuntimeError(
            f"garde d'index : decouverte BLOQUEE sur {chemin} sous une racine git "
            f"({p.stderr.strip()!r}) — plafond ou point de montage, jamais « non enregistre »")
    raise RuntimeError(
        f"garde d'index : git ne sait pas dire si {chemin} est enregistre (rc={p.returncode}, "
        f"stderr={p.stderr.strip()!r}) — ni elague ni balaye en silence")


def _elague(chemin, racine, etat):
    if not _checkout_imbrique(chemin):
        return False
    if "mode" not in etat:
        etat["mode"] = _garde_mode(racine)
    return not _enregistre(chemin, etat["mode"])
# garde d'index (T-00001073) : fin


# --- LES FONCTIONS DU RECENSEMENT (pures : racine et textes en paramètres) ------
def _marche(racine, top, etat):
    debut = racine if top == "." else os.path.join(racine, top)
    if not os.path.isdir(debut):
        return
    for dirpath, dirnames, filenames in os.walk(debut):
        rel_dir = os.path.relpath(dirpath, racine).replace(os.sep, "/")
        prefixe = "" if rel_dir == "." else rel_dir + "/"
        if prefixe.startswith(SAUTE_REL):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_NOMS
                       and not _elague(os.path.join(dirpath, d), racine, etat)]
        for nom in filenames:
            yield prefixe + nom


def perimetre(racine):
    """Les bancs et les gardes, énumérés SUR LE DISQUE (un banc neuf non encore
    suivi compte), en n'entrant dans aucun checkout imbriqué non enregistré."""
    racine = os.fspath(racine)
    etat = {}
    vus = set()
    for d in DOSSIERS_PERIMETRE:
        vus.update(r for r in _marche(racine, d, etat) if r.endswith((".py", ".sh")))
    for d, motif in GLOBS_PERIMETRE:
        top = os.path.join(racine, d)
        if os.path.isdir(top):
            vus.update(f"{d}/{n}" for n in os.listdir(top)
                       if fnmatch.fnmatchcase(n, motif) and os.path.isfile(os.path.join(top, n)))
    vus.update(r for r in _marche(racine, ".", etat) if fnmatch.fnmatchcase(r.rsplit("/", 1)[-1], "*.test.sh"))
    return vus


def candidats(racine, fichiers):
    out = set()
    for rel in fichiers:
        try:
            texte = Path(racine, rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(REGEX_PARCOURS.search(l) for l in texte.split("\n")):
            out.add(rel)
    return out


def ecarts_classes(cands, classes):
    """(candidats NON classés, clés qui ne sont plus candidates)."""
    return sorted(set(cands) - set(classes)), sorted(set(classes) - set(cands))


def hors_partition(suivis, perim, exclu):
    def couvert(t):
        return any(t == e or (e.endswith("/") and t.startswith(e)) for e in exclu)
    return sorted(t for t in suivis if t.endswith((".py", ".sh")) and t not in perim and not couvert(t))


def exclusions_mortes(suivis, perim, exclu):
    hors = [t for t in suivis if t.endswith((".py", ".sh")) and t not in perim]
    return sorted(e for e in exclu if not any(t == e or (e.endswith("/") and t.startswith(e)) for t in hors))


def empreinte_bloc(texte):
    blocs = _BLOC_RE.findall(texte)
    return hashlib.sha256(blocs[0].encode("utf-8")).hexdigest() if len(blocs) == 1 else None


def empreinte_garde_m(texte):
    gardes = _GARDE_M_RE.findall(texte)
    return hashlib.sha256(gardes[0].encode("utf-8")).hexdigest() if len(gardes) == 1 else None


def blocs_divergents(textes):
    """{fichier: empreinte} si un bloc manque, est double ou diffère ; {} sinon."""
    empreintes = {rel: empreinte_bloc(t) for rel, t in textes.items()}
    if None in empreintes.values() or len(set(empreintes.values())) > 1:
        return empreintes
    return {}


def jeton_absent(textes, jeton):
    return sorted(rel for rel, t in textes.items() if jeton not in t)


def traversants_fautifs(classes, etats):
    """Chaque `traversant-connu:<id>` doit nommer une tâche PRÉSENTE au board et
    NON close — sinon la dette n'est plus portée par personne."""
    fautes = []
    for rel, (classe, _raison) in sorted(classes.items()):
        if classe.startswith("traversant-connu:"):
            tid = classe.split(":", 1)[1]
            if tid not in etats:
                fautes.append(f"{rel} : {tid} ABSENTE du board")
            elif etats[tid] == "done":
                fautes.append(f"{rel} : {tid} est CLOSE — reclasser ce fichier")
    return fautes


def testpaths_exposes(texte_ini):
    """Les `testpaths` qui feraient collecter pytest DANS un worktree lié."""
    chemins, dedans = [], False
    for ligne in texte_ini.splitlines():
        if re.match(r"^testpaths\s*=", ligne):
            dedans = True
            chemins.extend(ligne.split("=", 1)[1].split())
            continue
        if dedans:
            if ligne[:1] in (" ", "\t") and ligne.strip() and not ligne.strip().startswith("#"):
                chemins.extend(ligne.split())
            elif ligne.strip():
                dedans = False
    return sorted(p for p in chemins if p.rstrip("/") in (".", ".claude") or p.startswith(".claude/"))


def _suivis(racine):
    p = subprocess.run(["git", "-C", os.fspath(racine), "ls-files", "-z"],
                       capture_output=True, text=True, env=_garde_env())
    if p.returncode != 0:
        raise RuntimeError(f"git ls-files a echoue (rc={p.returncode}) : {p.stderr.strip()!r}")
    return [t for t in p.stdout.split("\0") if t]


def _texte(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@unittest.skipUnless(_KIT.exists(), "recensement du kit : saute hors du kit (pas de .agents/IS_THE_KIT)")
class RecensementDesParcoursTests(unittest.TestCase):
    """Le recensement joué sur l'ARBRE RÉEL."""

    @classmethod
    def setUpClass(cls):
        cls.perim = perimetre(ROOT)
        cls.cands = candidats(ROOT, cls.perim)

    def test_le_perimetre_n_est_pas_vide(self):
        self.assertIn("core-scripts/check-stale-justification.sh", self.perim, "perimetre ampute")
        self.assertIn(".agents/evals/test_repo_walk_census.py", self.cands,
                      "le recensement ne se voit pas lui-meme : la regex ne mord plus")

    def test_chaque_emplacement_present_du_moteur_est_recense(self):
        self.assertTrue(MOTEUR_DIRS, "aucun emplacement du moteur n'est present")
        for moteur in MOTEUR_DIRS:
            banc = f"{moteur}/tests/test_run_export.py"
            self.assertIn(banc, self.perim, f"banc V3 non parcouru : {banc}")
            self.assertIn(f"{moteur}/", PERIMETRE_EXCLU)

    def test_tout_candidat_est_classe_et_toute_cle_est_candidate(self):
        non_classes, mortes = ecarts_classes(self.cands, CLASSES)
        self.assertEqual(
            ([], []), (non_classes, mortes),
            "PARCOURS NON CLASSE (premier terme) : un banc ou une garde parcourt l'arbre "
            "sans etre recense. Elague-le (bloc + garde, ou regle NESTED) ou classe-le avec "
            "sa raison. CLE MORTE (second terme) : le fichier ne parcourt plus, retire-le.")

    def test_les_classes_sont_permises_et_les_familles_sont_exactes(self):
        hors = sorted(r for r, (c, _r) in CLASSES.items()
                      if not any(c == p or (p.endswith(":") and c.startswith(p)) for p in CLASSES_PERMISES))
        self.assertEqual([], hors, "classe inconnue")
        self.assertEqual(sorted(FICHIERS_BLOC), sorted(r for r, (c, _x) in CLASSES.items() if c == "elague:bloc"))
        self.assertEqual(sorted(FICHIERS_GIT_PRINT),
                         sorted(r for r, (c, _x) in CLASSES.items() if c == "elague:-name .git -print"))

    def test_partition_des_fichiers_suivis(self):
        suivis = _suivis(ROOT)
        self.assertEqual([], hors_partition(suivis, self.perim, PERIMETRE_EXCLU),
                         "fichier SUIVI ni dans le perimetre ni sous une exclusion ecrite")
        self.assertEqual([], exclusions_mortes(suivis, self.perim, PERIMETRE_EXCLU),
                         "exclusion qui ne couvre plus aucun fichier : retire-la")

    def test_le_bloc_est_identique_dans_chaque_parcours(self):
        self.assertEqual({}, blocs_divergents({rel: _texte(rel) for rel in FICHIERS_BLOC}),
                         "bloc absent, double ou DIVERGENT")

    def test_le_jeton_de_garde_est_dans_chaque_parcours_et_la_garde_M_est_partagee(self):
        self.assertEqual([], jeton_absent({rel: _texte(rel) for rel in FICHIERS_BLOC}, JETON_GARDE))
        m = {rel: empreinte_garde_m(_texte(rel)) for rel in
             (".agents/evals/test_modload_registration.py", ".agents/evals/test_repo_walk_census.py")}
        self.assertNotIn(None, m.values(), f"garde M absente ou double : {m}")
        self.assertEqual(1, len(set(m.values())), f"garde M DIVERGENTE : {m}")

    def test_le_motif_nested_est_dans_le_runner_et_dans_son_miroir(self):
        # adopting-tree: le miroir est kit-only (strip: .agents/evals/test_bash_suites_discovery.py)
        miroir = ROOT / ".agents" / "evals" / "test_bash_suites_discovery.py"
        textes = {FICHIERS_GIT_PRINT[0]: _texte(FICHIERS_GIT_PRINT[0]),
                  FICHIERS_GIT_PRINT[1]: miroir.read_text(encoding="utf-8")}
        self.assertEqual([], jeton_absent(textes, JETON_GIT_PRINT))

    def test_le_traversant_connu_est_ouvert_au_board(self):
        # adopting-tree: board du kit (strip: .agents/state/), lu DANS le test, jamais au chargement — dans SA forme
        # (`TASKS.json` OU `board/tasks/`) par `lire_board_brut` de la façade (T-01M4KKMY43ZKCW1YD2Y8JX9MKH)
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location("census_traversant_tasks", ROOT / ".agents" / "bin" / "tasks.py")
        facade = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = facade
        spec.loader.exec_module(facade)
        etats = {t["id"]: t.get("state") for t in facade.lire_board_brut(str(ROOT)).get("tasks", [])}
        self.assertEqual([], traversants_fautifs(CLASSES, etats))

    def test_testpaths_n_expose_pas_les_worktrees(self):
        self.assertEqual([], testpaths_exposes((ROOT / "pytest.ini").read_text(encoding="utf-8")))

    def test_les_idiomes_non_detectes_echappent_vraiment_a_la_regex(self):
        self.assertTrue(IDIOMES_NON_DETECTES, "la borne doit etre ECRITE")
        vus = sorted(n for n, ex in IDIOMES_NON_DETECTES.items() if REGEX_PARCOURS.search(ex))
        self.assertEqual([], vus, "idiome desormais DETECTE : retire-le de la borne")


@unittest.skipUnless(_KIT.exists(), "recensement du kit : saute hors du kit (pas de .agents/IS_THE_KIT)")
class LeRecensementMordTests(unittest.TestCase):
    """MUTANTS AUTO-TESTÉS : chaque juge ci-dessus, rejoué sur une entrée altérée,
    doit rendre ROUGE — et la borne écrite doit rester VERTE."""

    def _racine_jetable(self):
        racine = tempfile.mkdtemp(prefix="t1073-recensement-")
        self.addCleanup(shutil.rmtree, racine, ignore_errors=True)
        return racine

    def _ecrire(self, racine, rel, texte):
        chemin = Path(racine, rel)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte, encoding="utf-8")

    def test_un_rglob_ou_un_Path_walk_neuf_rougit(self):
        for texte in ("for p in ROOT.rglob('*.py'):\n    pass\n", "for d, s, f in ROOT.walk():\n    pass\n"):
            racine = self._racine_jetable()
            self._ecrire(racine, ".agents/evals/test_nouveau.py", texte)
            non_classes, _mortes = ecarts_classes(candidats(racine, perimetre(racine)), {})
            self.assertEqual([".agents/evals/test_nouveau.py"], non_classes)

    def test_un_bloc_altere_rougit(self):
        textes = {rel: _texte(rel) for rel in FICHIERS_BLOC}
        self.assertEqual({}, blocs_divergents(textes), "base non verte : le mutant ne prouverait rien")
        cible = FICHIERS_BLOC[2]
        textes[cible] = textes[cible].replace("/worktrees/[^/]+/?$", "/worktrees/", 1)
        self.assertIn(cible, blocs_divergents(textes))

    def test_un_jeton_de_garde_retire_rougit(self):
        textes = {rel: _texte(rel) for rel in FICHIERS_BLOC}
        self.assertEqual([], jeton_absent(textes, JETON_GARDE), "base non verte")
        cible = FICHIERS_BLOC[1]
        textes[cible] = textes[cible].replace(JETON_GARDE, "# garde (retiree)")
        self.assertEqual([cible], jeton_absent(textes, JETON_GARDE))

    def test_un_jeton_git_print_retire_rougit(self):
        textes = {rel: _texte(rel) for rel in FICHIERS_GIT_PRINT}
        self.assertEqual([], jeton_absent(textes, JETON_GIT_PRINT), "base non verte")
        for cible in FICHIERS_GIT_PRINT:
            mute = dict(textes)
            mute[cible] = mute[cible].replace(JETON_GIT_PRINT, "-name .git -prune")
            self.assertEqual([cible], jeton_absent(mute, JETON_GIT_PRINT))

    def test_un_id_absent_ou_clos_rougit(self):
        # Classe SYNTHÉTIQUE : depuis T-00001083 aucun traversant n'est au registre,
        # et le juge doit mordre quand même le jour où l'un y revient.
        tid = "T-" + "00000001"
        classes = {"x.py": ("traversant-connu:" + tid, "temoin")}
        self.assertTrue(traversants_fautifs(classes, {}))
        self.assertTrue(traversants_fautifs(classes, {tid: "done"}))
        self.assertEqual([], traversants_fautifs(classes, {tid: "pending"}))

    def test_claude_dans_testpaths_rougit(self):
        self.assertEqual([".claude"], testpaths_exposes("[pytest]\ntestpaths =\n    .agents\n    .claude\n"))
        self.assertEqual([], testpaths_exposes("[pytest]\ntestpaths =\n    .agents\n    agentic_v3\n"))

    def test_un_fichier_suivi_hors_partition_rougit(self):
        self.assertEqual(["tools/neuf.py"], hors_partition(["tools/neuf.py", ".agents/bin/x.py"], set(), PERIMETRE_EXCLU))

    def test_vendor_seul_p(self):
        """Le paquet cadre au seul emplacement vendor : couvert par la partition, aucune
        entrée morte, et classé DÉLÉGUÉ par la grammaire du shim (alias, une seule règle).
        MUTANTS : retirer `.agents/vendor/cadre` de `PAQUET_CADRE_LIEUX` (hors partition),
        ou l'alias de `shim_grammar.chemin_delegue` (managed vendor jugé shim) → rouge."""
        racine = self._racine_jetable()
        suivis = [".agents/vendor/cadre/__init__.py", ".agents/vendor/cadre/ledger/ids.py",
                  ".agents/vendor/cadre/managed.py", ".agents/bin/x.py"]
        for rel in suivis:
            self._ecrire(racine, rel, "# cadre.managed\nx = 1\n")
        exclu = perimetre_exclu(racine)
        self.assertIn(".agents/vendor/cadre/", exclu)
        self.assertNotIn("src/cadre/", exclu, "entrée de l'emplacement absent : elle serait morte")
        self.assertEqual([], hors_partition(suivis, set(), exclu))
        self.assertEqual([], [e for e in exclusions_mortes(suivis, set(), exclu)
                              if "cadre" in e], "entrée cadre morte en vendor seul")
        spec = importlib.util.spec_from_file_location(
            "_census_shim_grammar", Path(__file__).resolve().parent / "shim_grammar.py")
        grammaire = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = grammaire  # ses @dataclass relisent leur module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(grammaire)
        for rel in suivis[:3]:
            with self.subTest(rel=rel):
                self.assertEqual("délégué", grammaire.exclusion(rel))
                self.assertFalse(grammaire.est_un_shim_marque(rel, "# cadre.managed\nx = 1\n"))
        self.assertTrue(grammaire.est_un_shim_marque(".agents/vendor/cadrex/m.py", "# cadre.managed\n"))

    def test_la_borne_un_idiome_non_detecte_reste_VERT(self):
        """Ce n'est pas un défaut du test : c'est la maille, écrite et mesurée."""
        racine = self._racine_jetable()
        self._ecrire(racine, ".agents/evals/test_listdir.py",
                     "def tout(d):\n    for nom in os.listdir(d):\n        pass\n")
        self.assertEqual(([], []), ecarts_classes(candidats(racine, perimetre(racine)), {}))

    def test_le_recensement_n_entre_pas_dans_un_worktree_mais_lit_un_sous_module(self):
        racine = self._racine_jetable()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
        vide = os.path.join(racine, "vide.gitconfig")
        Path(vide).write_text("", encoding="utf-8")
        env.update(GIT_CONFIG_GLOBAL=vide, GIT_CONFIG_SYSTEM=vide)

        def git(*args, cwd=None):
            argv = ["git"] + (["-C", cwd] if cwd else []) + ["-c", "protocol.file.allow=always", *args]
            subprocess.run(argv, check=True, capture_output=True, text=True, env=env)

        src, k = os.path.join(racine, "src"), os.path.join(racine, "k")
        for d in (src, k):
            git("init", "-q", "-b", "main", d)
            git("config", "user.email", "t@t", cwd=d)
            git("config", "user.name", "t", cwd=d)
        self._ecrire(src, "s.test.sh", "find . -type f\n")
        git("add", "-A", cwd=src)
        git("commit", "-q", "-m", "s", cwd=src)
        self._ecrire(k, "README", "k\n")
        git("add", "-A", cwd=k)
        git("commit", "-q", "-m", "k", cwd=k)
        git("submodule", "add", "-q", src, "vendor/sub", cwd=k)
        git("worktree", "add", "-q", "--detach", ".claude/worktrees/w1", "HEAD", cwd=k)
        self._ecrire(k, ".claude/worktrees/w1/w.test.sh", "find . -type f\n")
        perim = perimetre(k)
        self.assertIn("vendor/sub/s.test.sh", perim, "un sous-module ENREGISTRE doit etre lu")
        self.assertNotIn(".claude/worktrees/w1/w.test.sh", perim, "un worktree lie ne doit pas etre lu")

    @unittest.skipIf(os.name == "nt", "SKIP : script `core.fsmonitor` en sh non mesure sous Windows")
    def test_la_garde_M_n_execute_jamais_la_config_du_depot_interroge(self):
        """S-00003664 — la copie M de CE fichier. CONTRÔLE POSITIF : le MÊME
        `ls-files -s` sans les deux `-c`, sous le MÊME environnement, fait naître le
        marqueur ; sinon le zéro qui suit ne prouve rien. Config posée APRÈS la
        construction (la construction l'exécuterait)."""
        racine = self._racine_jetable()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in _GARDE_CONSERVE}
        vide = os.path.join(racine, "vide.gitconfig")
        Path(vide).write_text("", encoding="utf-8")
        env.update(GIT_CONFIG_GLOBAL=vide, GIT_CONFIG_SYSTEM=vide)

        def git(*args, cwd):
            subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True, env=env)

        k = os.path.join(racine, "k")
        os.makedirs(k)
        git("init", "-q", "-b", "main", cwd=k)
        git("config", "user.email", "t@t", cwd=k)
        git("config", "user.name", "t", cwd=k)
        self._ecrire(k, "README", "k\n")
        git("add", "-A", cwd=k)
        git("commit", "-q", "-m", "k", cwd=k)
        cand = os.path.join(k, "vendor", "emb")
        os.makedirs(os.path.join(cand, ".git"))
        marque, script = os.path.join(racine, "fsm.marque"), os.path.join(racine, "fsm.sh")
        self._ecrire(racine, "fsm.sh", f'#!/bin/sh\necho "fsmonitor $*" >> "{marque}"\nexit 1\n')
        os.chmod(script, 0o755)
        git("config", "core.fsmonitor", script, cwd=k)
        subprocess.run(["git", "-C", os.path.dirname(cand), "ls-files", "-s", "--",
                        ":(literal)" + os.path.basename(cand)],
                       capture_output=True, text=True, env=_garde_env(), timeout=60)
        self.assertTrue(os.path.exists(marque),
                        "CONTROLE POSITIF : un ls-files -s NU n execute pas core.fsmonitor — le temoin ne mesure rien")
        os.remove(marque)
        self.assertTrue(_elague(cand, k, {}), "PRECONDITION : un `.git` vide non suivi est elague")
        self.assertFalse(os.path.exists(marque), "la garde M a EXECUTE le core.fsmonitor du depot interroge")

    def test_la_garde_M_leve_sur_git_sans_reponse_et_chaque_appel_porte_60_s(self):
        """S-00003664 : les DEUX appels git de la garde M (mode, puis index) portent
        `timeout=60` ; passé ce délai, `subprocess.TimeoutExpired` REMONTE."""
        racine = self._racine_jetable()
        cand = os.path.join(racine, "vendor", "emb")
        os.makedirs(os.path.join(cand, ".git"))
        delais = []

        def faux(argv, *a, **kw):
            delais.append(("ls-files" if "ls-files" in argv else "rev-parse", kw.get("timeout")))
            if "ls-files" in argv:
                raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        with mock.patch.object(subprocess, "run", faux):
            with self.assertRaises(subprocess.TimeoutExpired):
                _elague(cand, racine, {})
        self.assertEqual([("rev-parse", 60), ("ls-files", 60)], delais)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
