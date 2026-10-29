"""T-00000801 — INVOCATION DURCIE DES HOOKS BASH CLAUDE ET DU CAPTEUR statusLine.

CE QUE CE FILET TIENT. Chaque commande de hook de `.claude/settings.json`, et la
commande `statusLine`, s'ouvre par un PRÉFIXE fixe (`PREFIX` ci-dessous) :
(1) la racine n'est convertie par `cygpath -u` que si elle a une forme Windows
(`C:…`, un antislash) — l'ancienne forme appelait `cygpath` TOUJOURS, donc un
`cygpath` du PATH ou une fonction exportée de ce nom choisissait la racine ;
(2) GIT_DIR et GIT_WORK_TREE sont RECOPIÉS dans `_CADRE_GIT_DIR` /
`_CADRE_GIT_WORK_TREE` (absents si la variable l'était, vides si elle l'était,
une valeur ambiante de ces deux noms retirée d'abord) — seul
`post-task-done-index.sh` les relit, pour commiter au bon dépôt (S-00003226) ;
(3) BASH_ENV, ENV, CDPATH, GLOBIGNORE et HUIT des dix variables de
`conftest.py::GIT_REDIRECTIONS` (LUES par `ast`, jamais recopiées) sont retirées
— `GIT_CONFIG_PARAMETERS` et `GIT_CONFIG_COUNT` aussi, mais le préfixe n'en rend aux
hooks que les entrées `safe.directory`, LUES PAR GIT (S-00003224, amendée par
S-00003821) ; (4) `exec bash -p` remplace
l'enveloppe : `exec` ne passe pas par une fonction `bash` exportée, `-p` refuse
au bash du hook BASH_ENV, les fonctions exportées, SHELLOPTS et BASHOPTS — et
CDPATH sous bash >= 4 seulement (bash 3.2 -p le suit, mesuré : c'est l'`unset`
qui le ferme). SHELLOPTS et BASHOPTS restent HORS de l'`unset` : ils sont en
lecture seule sous bash, et les y mettre écrit sur stderr ou tue l'enveloppe
(mutants M1a/M1b, tués ici).

A' (S-00003742), amendée par S-00003821. Rendre ces deux noms tels quels aux gardes rouvrait, pour tout appel git de garde
NON blindé, l'exécution de `core.fsmonitor` / `core.hooksPath` portés par l'environnement (mesuré) : le préfixe n'en rend donc
QUE les entrées `safe.directory` (option (ii), `FILTRE_LIT`, lu PAR GIT) et le blindage des appels git reste une règle d'APPEL
(`-c core.fsmonitor=false -c core.hooksPath=/dev/null`) pour les canaux que le préfixe ne couvre pas (GIT_CONFIG_GLOBAL,
GIT_CONFIG_SYSTEM, XDG_CONFIG_HOME et HOME : au moins ces quatre). Ce filet tient le préfixe, ses noms, le filtre `safe.directory`
(`violations_config`, mutants F1–F8, F11, F17), ce que son EXÉCUTION consomme (`violations_lecture` : ni stdin, ni
fichier de config hors P/C, ni include — FIFO-détecteur, mutants F12–F18, it. 8 B-C1 ; table des gardes en annexe) et la preuve de bout en bout que P et C ne portent plus aucune clé exécutable jusqu'à un
hook (`test_config_canary_stops_at_prefix`, témoin positif : la forme sans filtre l'écrit) ; le blindage des appels git du hook
de commit d'état et la couture préfixe → hook sont dans `test_post_task_done_git_shield.py`.

LES ÉTAGES. T1 lit TOUTES les commandes (sans compte figé) et exige la forme
exacte ; T2 rejoue les deux jambes gardes (7 refus + un `ls`) sous 19 vecteurs
d'environnement et trois enveloppes POSIX (/bin/sh, le premier bash>=4 du PATH
lié sous le nom `sh`, /bin/dash) ; T2b fait armer le capteur de la ligne
d'état ; T2c rend le rejeu insensible à la locale ; T3 sonde le préfixe (noms
retirés, un mutant par nom, racine) ; T4 prouve que les vecteurs PARLENT sur
l'ancienne forme (témoins de canal) ; T5 épingle les résidus NOMMÉS — ils
rougissent le jour où ils se ferment, et c'est voulu : le SKILL les déclare
ouverts ; xtrace+PS4 excepté, dont l'épingle (T4, T5) suit une SONDE
d'exécution, car bash 5.2.37 IGNORE un PS4 importé sous euid 0 (mesuré ; les
autres versions n'y sont pas mesurées, T-00001180) ; T6 tue
des mutants du préfixe, des jambes et du filet lui-même (F11 rejoué sous les
seules enveloppes qui importent une fonction exportée, sondées ; le juge
xtrace+PS4 sur une table pure, `test_xtrace_judge_table`) ; T7
tient la promesse écrite dans `guardrails/SKILL.md`.

L'ENVIRONNEMENT DE REJEU EST CONSTRUIT PAR LISTE BLANCHE (PATH, HOME, TMPDIR, et
ce que le banc pose lui-même), jamais purgé par liste noire : une variable
ambiante inconnue ne peut pas changer une cellule. `LC_ALL=C` y est FORCÉ — une
locale invalide héritée fait écrire bash sur stderr avant `BLOCKED` (le refus
tient, rc 2, mais le message n'est plus en tête).

ENVELOPPES ABSENTES. Sous nt, le module saute EN PREMIER (dette CI Windows
T-00000744). Ailleurs, dans le dépôt du kit ET sous `CI=true`, l'absence de
bash>=4 est un ÉCHEC NOMMÉ ; l'absence de /bin/dash est un avertissement puis un
saut, sa présence sur l'image macOS de la CI n'étant pas mesurée. Hors de ce
cas, toute absence avertit (en nommant les mutants non tués) puis saute.

OVERRIDE. `HOOK_HARDENING_SETTINGS=<chemin>` fait lire un candidat au lieu du
fichier vivant (préparation hors dépôt) ; il est annoncé par un avertissement et
REFUSÉ sous `CI=true` s'il ne désigne pas le fichier vivant.

BORNES, écrites plutôt que supposées : mesuré sur darwin (/bin/sh = bash 3.2,
bash 5.3 lié `sh`, /bin/dash) ; Linux lu, dash et bash-en-sh mesurés par proxy,
sauf T4, T5 et T6, rejoués le 2026-10-04 dans python:3.12-slim (bash 5.2.37,
/bin/sh = dash) en euid 0 et 65534 — le fichier entier en euid 0 seul (T-00001180) ;
`bash.exe -c` (Git Bash) approché par bash>=4 sous son propre nom. Une quote
échappée dans une commande est tuée par `sh -n`, pas par la règle textuelle.
"""
from __future__ import annotations

import os

import pytest

if os.name == "nt":
    pytest.skip("filet POSIX : aucune enveloppe /bin/sh, dash ni bash-en-sh sous nt "
                "(dette CI Windows T-00000744)", allow_module_level=True)

import ast  # noqa: E402
import concurrent.futures as cf  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import warnings  # noqa: E402
from dataclasses import dataclass, replace  # noqa: E402
from pathlib import Path  # noqa: E402

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_kit import jambe_jugee  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REGLAGES_VIVANTS = ROOT / ".claude" / "settings.json"
SKILL = ROOT / ".agents" / "skills" / "guardrails" / "SKILL.md"

# adopting-tree: le marqueur d'identité du kit ne voyage pas (strip: .agents/IS_THE_KIT)
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()


#: Repli ÉCRIT : un arbre adoptant peut porter un conftest.py sans
#: GIT_REDIRECTIONS, ou aucun ; le filet s'y lit alors sur ce littéral, annoncé.
NOMS_GIT_REPLI = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                  "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX")
#: FILTRÉS (S-00003821) : le préfixe les retire et n'en rend que les entrées `safe.directory` (`FILTRE_LIT`).
NOMS_FILTRES = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")


def _noms_git() -> tuple[str, ...]:
    try:
        arbre = ast.parse((ROOT / "conftest.py").read_text(encoding="utf-8"))
        for noeud in arbre.body:
            if isinstance(noeud, ast.Assign) and any(
                    isinstance(c, ast.Name) and c.id == "GIT_REDIRECTIONS" for c in noeud.targets):
                return tuple(n for n in ast.literal_eval(noeud.value) if not n.startswith("GIT_CONFIG_"))
        cause = "conftest.py ne porte pas GIT_REDIRECTIONS"
    except (OSError, SyntaxError, ValueError) as exc:
        cause = f"conftest.py illisible ({type(exc).__name__})"
    warnings.warn(f"{cause} : noms git lus sur le repli littéral NOMS_GIT_REPLI")
    return NOMS_GIT_REPLI


NOMS_SHELL = ("BASH_ENV", "ENV", "CDPATH", "GLOBIGNORE")
NOMS_GIT = _noms_git()
NOMS_RETIRES = NOMS_SHELL + NOMS_GIT
CASE_RACINE = (r'case $CLAUDE_PROJECT_DIR in ?:*|*\\*) _d=$(cygpath -u "$CLAUDE_PROJECT_DIR" '
               r'2>/dev/null) && CLAUDE_PROJECT_DIR=$_d ;; esac; ')
#: S-00003226 : copie AVANT l'unset ; `+x` distingue absent et vide.
COPIE_GIT = ('unset _CADRE_GIT_DIR _CADRE_GIT_WORK_TREE; '
             'case ${GIT_DIR+x} in x) _CADRE_GIT_DIR=$GIT_DIR; export _CADRE_GIT_DIR ;; esac; '
             'case ${GIT_WORK_TREE+x} in x) _CADRE_GIT_WORK_TREE=$GIT_WORK_TREE; export _CADRE_GIT_WORK_TREE ;; esac; ')


#: S-00003821 (option ii) : ce que le préfixe fait de GIT_CONFIG_PARAMETERS / GIT_CONFIG_COUNT. Il retire les deux
#: noms et ne rend aux hooks que les entrées `safe.directory` de portée `command`, LUES PAR GIT (blindé : `-c`), puis
#: reconstruites dans un GIT_CONFIG_PARAMETERS neuf (apostrophe échappée : la valeur n'est jamais relue par le shell).
#: Sans l'un ni l'autre nom, rien ne se lance. git absent, `--show-scope` inconnu ou canal illisible : sortie vide.
#: Rév. 9 (it. 8 : B-C1, A-C1/B-C2) — le filtre ne CONSOMME rien d'autre que P et C : stdin fermé (`</dev/null`) ; `env -i`
#: (binôme fournée 9, F1) : git ne reçoit QUE PATH, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, P et C (clés et valeurs 0..7)
#: — ni `GIT_CONFIG`, ni `GIT_TRACE*` (un FIFO de trace PENDAIT la jambe), ni HOME ; `-C /` ; ÉCRAN : `GIT_CONFIG_COUNT` hors 0-8, ou
#: « include » (toute casse) dans P ou une clé GIT_CONFIG_KEY_0..7, et git n'est PAS lancé (les deux noms partent) ; env, sed et tr par
#: `exec` — une fonction exportée de ces noms (ni de git) ne les remplace pas sous enveloppe POSIX. Tenu par `violations_config`, `violations_lecture`.
FILTRE_LIT = (
    r"""_s=; case ${GIT_CONFIG_PARAMETERS+x}${GIT_CONFIG_COUNT+x} in ?*) case ${GIT_CONFIG_COUNT-0}:${GIT_CONFIG_PARAMETERS-}${GIT_CONFIG_KEY_0-}${GIT_CONFIG_KEY_1-}${GIT_CONFIG_KEY_2-}${GIT_CONFIG_KEY_3-}${GIT_CONFIG_KEY_4-}${GIT_CONFIG_KEY_5-}${GIT_CONFIG_KEY_6-}${GIT_CONFIG_KEY_7-} in [0-8]:*[Ii][Nn][Cc][Ll][Uu][Dd][Ee]*) ;; """
    r"""[0-8]:*) _s=$( (exec env -i PATH="$PATH" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null ${GIT_CONFIG_PARAMETERS+"GIT_CONFIG_PARAMETERS=$GIT_CONFIG_PARAMETERS"} ${GIT_CONFIG_COUNT+"GIT_CONFIG_COUNT=$GIT_CONFIG_COUNT"} ${GIT_CONFIG_KEY_0+"GIT_CONFIG_KEY_0=$GIT_CONFIG_KEY_0"} ${GIT_CONFIG_VALUE_0+"GIT_CONFIG_VALUE_0=$GIT_CONFIG_VALUE_0"} ${GIT_CONFIG_KEY_1+"GIT_CONFIG_KEY_1=$GIT_CONFIG_KEY_1"} ${GIT_CONFIG_VALUE_1+"GIT_CONFIG_VALUE_1=$GIT_CONFIG_VALUE_1"} ${GIT_CONFIG_KEY_2+"GIT_CONFIG_KEY_2=$GIT_CONFIG_KEY_2"} ${GIT_CONFIG_VALUE_2+"GIT_CONFIG_VALUE_2=$GIT_CONFIG_VALUE_2"} ${GIT_CONFIG_KEY_3+"GIT_CONFIG_KEY_3=$GIT_CONFIG_KEY_3"} ${GIT_CONFIG_VALUE_3+"GIT_CONFIG_VALUE_3=$GIT_CONFIG_VALUE_3"} ${GIT_CONFIG_KEY_4+"GIT_CONFIG_KEY_4=$GIT_CONFIG_KEY_4"} ${GIT_CONFIG_VALUE_4+"GIT_CONFIG_VALUE_4=$GIT_CONFIG_VALUE_4"} ${GIT_CONFIG_KEY_5+"GIT_CONFIG_KEY_5=$GIT_CONFIG_KEY_5"} ${GIT_CONFIG_VALUE_5+"GIT_CONFIG_VALUE_5=$GIT_CONFIG_VALUE_5"} ${GIT_CONFIG_KEY_6+"GIT_CONFIG_KEY_6=$GIT_CONFIG_KEY_6"} ${GIT_CONFIG_VALUE_6+"GIT_CONFIG_VALUE_6=$GIT_CONFIG_VALUE_6"} ${GIT_CONFIG_KEY_7+"GIT_CONFIG_KEY_7=$GIT_CONFIG_KEY_7"} ${GIT_CONFIG_VALUE_7+"GIT_CONFIG_VALUE_7=$GIT_CONFIG_VALUE_7"} git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C / config --show-scope --get-all safe.directory </dev/null 2>/dev/null) | exec sed -n "s/'/'\\\\''/g; """
    r"""s/^command[[:blank:]]\(.*\)\$/'safe.directory=\1' /p" | exec tr -d '\n') ;; esac ;; esac; unset GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT; """
    r"""case $_s in ?*) GIT_CONFIG_PARAMETERS=$_s; export GIT_CONFIG_PARAMETERS ;; esac; """)


def faire_prefixe(noms=NOMS_RETIRES, case=CASE_RACINE, copie=COPIE_GIT, filtre=FILTRE_LIT) -> str:
    return case + "export CLAUDE_PROJECT_DIR; " + copie + "unset " + " ".join(noms) + "; " + filtre


PREFIX = faire_prefixe()
#: Le littéral figé : si `GIT_REDIRECTIONS` gagne un nom, `PREFIX` s'en écarte et
#: T1 rougit — réglages, SKILL et ce littéral se mettent à jour ensemble.
PREFIX_LITTERAL = (
    r'case $CLAUDE_PROJECT_DIR in ?:*|*\\*) _d=$(cygpath -u "$CLAUDE_PROJECT_DIR" 2>/dev/null) '
    r'&& CLAUDE_PROJECT_DIR=$_d ;; esac; export CLAUDE_PROJECT_DIR; '
    r'unset _CADRE_GIT_DIR _CADRE_GIT_WORK_TREE; '
    r'case ${GIT_DIR+x} in x) _CADRE_GIT_DIR=$GIT_DIR; export _CADRE_GIT_DIR ;; esac; '
    r'case ${GIT_WORK_TREE+x} in x) _CADRE_GIT_WORK_TREE=$GIT_WORK_TREE; export _CADRE_GIT_WORK_TREE ;; esac; '
    r'unset BASH_ENV ENV CDPATH GLOBIGNORE GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY '
    r'GIT_COMMON_DIR GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX; ' + FILTRE_LIT)
#: Ce qui suit le préfixe : des affectations d'une liste CLOSE, `exec bash -p`, un
#: script sous la racine sans `..`, puis des chemins sous la racine ou des options.
#: Appliquée par `fullmatch` : un `\n` final ne passe pas.
REGLE_RESTE = re.compile(
    r'^(?:(?:AGENTS_HOOK_HOST|SCA_CHANGED_ONLY)=[A-Za-z0-9_.-]+ )*exec bash -p '
    r'"\$CLAUDE_PROJECT_DIR/(?![^"]*\.\.)[^"$\x60 ]+"'
    r'(?: (?:"\$CLAUDE_PROJECT_DIR/(?![^"]*\.\.)[^"$\x60 ]+"|--[a-z-]+(?:=[A-Za-z0-9_.-]+)?))*$')
QUEUE_LIGNE = 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/statusline.sh"'

#: Les jambes d'AVANT (forme de 745aaa85), embarquées en littéral : un arbre
#: adoptant n'a pas ce commit. Elles ne servent qu'aux témoins de canal (T4).
AVANT = 'export CLAUDE_PROJECT_DIR="$(cygpath -u "$CLAUDE_PROJECT_DIR" 2>/dev/null || printf %s "$CLAUDE_PROJECT_DIR")"; '
JAMBES_AVANT = {
    "safe-bash": AVANT + 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/safe-bash.sh"',
    "protect-paths": AVANT + 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/protect-paths.sh"',
    "statusline": AVANT + 'bash "$CLAUDE_PROJECT_DIR/.claude/statusline.sh"',
}

TITRE_SKILL = "Invocation durcie des hooks Claude (T-00000801)"
PHRASE_33 = (
    "Those can only be closed from the invocation itself: T-00000801 closes them under a POSIX "
    "`/bin/sh -c` envelope (macOS: read and measured in shell; Linux: dash and bash-as-sh "
    "measured by darwin proxy, then replayed 2026-10-04 in python:3.12-slim under euid 0 "
    "(`test_hook_env_hardening.py` whole, its gitleaks leg skipped: gitleaks absent) and 65534 "
    "(its T4–T6 only) — no Claude Code run on a Linux host), except the SHELLOPTS whose effect "
    "precedes the first command when /bin/sh is bash (noexec; xtrace with a command-substitution "
    "PS4 — non-zero euid only for bash 5.2.37, which ignores an imported PS4 as root; other bash "
    "versions as root not measured, T-00001180) and the GIT_* triggers outside its eight names; "
    "under Git Bash's non-POSIX `bash.exe -c` "
    "(Windows) BASH_ENV, those SHELLOPTS and the exported functions `exec`, `unset` and `export` "
    "stay open (`exit`, `bash`, `printf` and `cygpath` are closed there, measured by proxy). See "
    "« Invocation durcie des hooks Claude (T-00000801) ».")
#: T-00001180, A-1 (S-00004134) : la portée euid 0 au site FRANÇAIS (le bloc du préfixe), qu'aucun test n'épinglait ; l'anglais
#: est dans PHRASE_33. Bornée à la mesure de 5b9e8369 : bash 5.2.37 seul en euid 0, le filet entier en euid 0, T4–T6 en 65534.
PHRASES_EUID = (
    "rc −9 ×7 mesuré en euid non nul ; fermé en euid 0 pour bash 5.2.37, qui y ignore un PS4 importé ; autres versions de "
    "bash en euid 0 non mesurées, T-00001180)",
    "puis rejoués le 2026-10-04 en python:3.12-slim, en euid 0 (filet entier, jambe gitleaks sautée : gitleaks absent) et 65534 "
    "(T4–T6 seuls ; le dash de Debian y rend 137, il attend sa dernière commande) ; aucun hôte Claude Code Linux mesuré")
PHRASE_CASE = (
    "la forme `case … in <clause>` sur une ligne est admise dans les jambes JSON (hors population "
    "du SAST, contrôlée par `sh -n` par enveloppe), jamais dans un `.sh`")
#: F1 (S-00003225) : trois ancres de la puce « layout nu », et une phrase INTERDITE.
PHRASES_NU = (
    "les gardes ne voient plus le dépôt, comme dans le même layout SANS export",
    "T-00000804 laisse ce cas à rc 0",
    "`safe-bash` laisse passer `echo x > AGENTS.md` (rc 2 → 0",
    "seul `.agents/bin/post-task-done-index.sh` retrouve GIT_DIR et GIT_WORK_TREE (S-00003226)",
    "mais aucun hook ni `core.fsmonitor` de ce dépôt ne s'exécute",
    "`filter.<nom>.clean` et `gpg.program` portés par SA config s'exécutent encore")
#: A' (S-00003742) : la règle d'APPEL, le fait que la liste des blindés se DÉRIVE (jamais une énumération qui pourrit), la BORNE
#: du relevé de la fenêtre (« au moins », énuméré sur les commandes, sur DEUX états d'index et SIX canaux : B-C1, it. 6 et 7) et la
#: décision (ii) (S-00003821) : le préfixe ne rend aux hooks de P et C que les entrées `safe.directory`.
PHRASES_BLINDAGE = (
    "CHAQUE appel git d'un hook se blinde au site d'appel par `-c core.fsmonitor=false -c core.hooksPath=/dev/null`",
    "la liste se DÉRIVE, elle ne se tient pas ici",
    "Relevé « au moins », non clos, mesuré le 2026-10-03 AVANT tout blindage, en ÉNUMÉRANT les 34 commandes",
    "sur DEUX états d'index (propre, périmé) et SIX canaux d'environnement",
    "un hook absent de la liste dérivée reste exposé",
    "le préfixe ne rend aux hooks que leurs entrées `safe.directory`",
    "au moins ces quatre canaux, mesurés avec témoin",
    "filtre ne lit QUE ces deux canaux",
    "git, sed et tr du filtre sont lancés par `exec`")
PHRASE_INTERDITE = "les gardes à l'écriture" + " tiennent"  # coupée À DESSEIN : T-00000804 1(c) grep le littéral entier
#: Puces du relevé NON CLOS que T7 exige (leur retrait se lirait « fermé »).
NON_CLOS_EPINGLES = (
    "- `CLAUDE_CODE_SHELL_PREFIX`, qui enveloppe la jambe ENTIÈRE avant le préfixe",
    "- `LD_PRELOAD`/`LD_AUDIT` (Linux)",
    "- les clés git qui EXÉCUTENT du code, portées par")

REFUS_SAFE_BASH = ("rm AGENTS.md", "git restore .", "echo x > AGENTS.md", "git show --output=f HEAD")
REFUS_PROTECT = (".agents/state/gates/BINOME_REQUIRED", ".mcp.json", ".git/config")
TETES_REFUS = ("BLOCKED", "WARNING by hook")
CHARGE_LIGNE = json.dumps({"session_id": "filet-801", "context_window": {"used_percentage": 95},
                           "model": {"display_name": "M"}, "cost": {"total_cost_usd": 0}})
ENVELOPPES_POSIX = ("sh", "bash-sh", "dash")
VECTEURS_T2 = ("aucun", "b-DEBUG", "errexit-SHELLOPTS", "errexit-BASH_ENV", "onecmd",
               "BASH_FUNC_exit", "BASH_FUNC_cygpath", "BASH_FUNC_printf", "BASH_FUNC_bash",
               "BASH_FUNC_exec", "BASH_FUNC_unset", "BASH_FUNC_export", "GIT_DIR",
               "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
               "include-stdin-P", "include-stdin-C")  # rév. 9 : it. 8, B-C1
VECTEURS_T2B = ("aucun", "b-DEBUG", "onecmd", "BASH_FUNC_export")
#: S-00003224 : un safe.directory légitime passé par l'environnement doit
#: atteindre le git des gardes. Propriétaire étranger SIMULÉ par le bouton de
#: test de git (GIT_TEST_ASSUME_DIFFERENT_OWNER) ; témoin « étranger seul ».
VECTEURS_SAFE = ("safe.directory-COUNT", "safe.directory-PARAMETERS",  # rév. 9 : + fonctions exportées (A-C1/B-C2)
                 "safe.directory-BASH_FUNC_git", "safe.directory-BASH_FUNC_sed", "safe.directory-BASH_FUNC_tr")
#: S-00003723 : l'AIGUILLE du stderr de la jambe redirection de safe-bash. `(git-tracked,` : git a RÉPONDU et le fichier est
#: suivi. Son ABSENCE = git muet (la redirection passe avant T-00000804, est refusée `(git-unanswered,` après). Le RC n'est
#: JAMAIS lu : étalonné sur le rc, le témoin deviendrait un saut annoncé partout, car après T-00000804 « propriétaire
#: étranger seul » et « avec safe.directory » rendent TOUS DEUX rc 2.
AIGUILLE_REPOND = "(git-tracked,"
NOEXEC = {"SHELLOPTS": "noexec"}
XTRACE_PS4 = {"SHELLOPTS": "xtrace", "PS4": "$(kill -9 $$)+ "}
PERDUES = {
    "sh": "rejeu T2/T2b/T3 sous /bin/sh non joué",
    "bash-sh": "M1a, M1b, M3 non tués ; résidus T5 bash-en-sh non épinglés",
    "dash": "résidus T5 dash et témoin T4 xtrace+PS4 non joués",
    "bash-np": "résidus T5 non posix (proxy bash.exe -c) non épinglés",
}


# ---------------------------------------------------------------------------
# RÉGLAGES LUS, ET LEUR TEXTE
# ---------------------------------------------------------------------------
def choix_reglages(env) -> tuple[Path, list[str]]:
    brut = env.get("HOOK_HARDENING_SETTINGS")
    if not brut:
        return REGLAGES_VIVANTS, []
    chemin = Path(brut)
    if env.get("CI") == "true" and chemin.resolve() != REGLAGES_VIVANTS.resolve():
        return chemin, [f"CI=true : HOOK_HARDENING_SETTINGS={brut} remplace {REGLAGES_VIVANTS} — refusé"]
    return chemin, []


def jambes_hooks(doc) -> list[tuple[str, dict]]:
    """Hors du kit, les jambes du kit seules (T-01M54MWW5GH, S-01M550PYWS) : une jambe
    AJOUTÉE par l'adoptant n'est plus jugée par le préfixe durci, à sa charge."""
    return [(ev, h) for ev, blocs in doc.get("hooks", {}).items()
            for bloc in blocs for h in bloc.get("hooks", [])
            if jambe_jugee(str(h.get("command", "")))]


def jambes_gardes(doc) -> dict[str, str]:
    j: dict[str, str] = {}
    for _, h in jambes_hooks(doc):
        c = h.get("command", "")
        for cle in ("safe-bash", "protect-paths"):
            if f'/.claude/hooks/{cle}.sh"' in c:
                j.setdefault(cle, c)
    j["statusline"] = doc.get("statusLine", {}).get("command", "")
    return j


def violations_texte(doc, prefixe=PREFIX) -> list[str]:
    v: list[str] = []
    jambes = jambes_hooks(doc)
    cmds = [h.get("command", "") for _, h in jambes]
    for cle in ("safe-bash", "protect-paths"):
        if not any(f'/.claude/hooks/{cle}.sh"' in c for c in cmds):
            v.append(f"aucune jambe {cle} : la règle serait vraie à vide")
    for ev, h in jambes:
        c = h.get("command", "")
        if h.get("shell") != "bash":
            v.append(f"{ev} : shell={h.get('shell')!r} au lieu de 'bash' — {c[-70:]}")
        if not c.startswith(prefixe):
            v.append(f"{ev} : préfixe absent ou altéré — {c[:90]}")
        elif not REGLE_RESTE.fullmatch(c[len(prefixe):]):
            v.append(f"{ev} : reste hors règle — {c[len(prefixe):]!r}")
    ligne = doc.get("statusLine", {})
    if "shell" in ligne:
        v.append("statusLine porte une clé `shell` (elle n'en a pas)")
    if ligne.get("command") != prefixe + QUEUE_LIGNE:
        v.append(f"statusLine.command hors forme — {ligne.get('command', '')[:90]}")
    return v


def toutes_commandes(doc) -> list[str]:
    return [h.get("command", "") for _, h in jambes_hooks(doc)] + [doc.get("statusLine", {}).get("command", "")]


def violations_sh_n(a0: str, cmds) -> list[str]:
    v = []
    for c in cmds:
        p = subprocess.run([a0, "-n", "-c", c], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            v.append(f"{a0} -n : rc {p.returncode} — {p.stderr.strip()[:80]} — {c[-60:]}")
    return v


# ---------------------------------------------------------------------------
# ENVELOPPES
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Enveloppe:
    nom: str
    argv0: str | None
    absence: str | None = None
    fatale: bool = False


def _majeure_bash(chemin: str) -> int:
    try:
        p = subprocess.run([chemin, "-c", 'printf %s "${BASH_VERSINFO[0]}"'], capture_output=True,
                           text=True, timeout=10, env={"PATH": "/usr/bin:/bin"})
    except OSError:
        return 0
    return int(p.stdout) if p.stdout.isdigit() else 0


def decouvrir(path: str, dash: str, est_le_kit: bool, ci: bool, lien_dir: Path | None) -> dict:
    """Fonction à paramètres : `test_missing_envelope_fails_under_ci` joue ses deux
    branches sans rien écrire sous la racine réelle (`lien_dir=None`)."""
    exige = ci and est_le_kit
    bash4 = next((c for c in (os.path.join(d, "bash") for d in path.split(os.pathsep) if d)
                  if os.path.isfile(c) and os.access(c, os.X_OK) and _majeure_bash(c) >= 4), None)
    env = {"sh": Enveloppe("sh", "/bin/sh") if os.access("/bin/sh", os.X_OK)
           else Enveloppe("sh", None, "/bin/sh absent", fatale=exige)}
    if bash4 is None:
        for nom in ("bash-sh", "bash-np"):
            env[nom] = Enveloppe(nom, None, "aucun bash>=4 sur le PATH", fatale=exige)
    else:
        lien = None
        if lien_dir is not None:
            lien = str(lien_dir / "sh")
            os.symlink(bash4, lien)
        env["bash-sh"] = Enveloppe("bash-sh", lien, None if lien else "lien non posé")
        env["bash-np"] = Enveloppe("bash-np", bash4)
    env["dash"] = (Enveloppe("dash", dash) if os.path.isfile(dash) and os.access(dash, os.X_OK)
                   else Enveloppe("dash", None, f"{dash} absent", fatale=False))
    return env


def violations_absence(decouvrir_fn) -> list[str]:
    v = []
    rien = dict(path="/nonexistent", dash="/nonexistent/dash", lien_dir=None)
    e = decouvrir_fn(est_le_kit=True, ci=True, **rien)
    for nom in ("bash-sh", "bash-np"):
        if not e[nom].fatale:
            v.append(f"CI+kit : {nom} absent n'est pas un échec nommé")
    if e["dash"].fatale:
        v.append("CI+kit : dash absent ne doit pas échouer (présence non mesurée sur l'image macOS)")
    for ci, kit in ((False, True), (True, False), (False, False)):
        if any(x.fatale for x in decouvrir_fn(est_le_kit=kit, ci=ci, **rien).values()):
            v.append(f"ci={ci} kit={kit} : une absence est fatale hors CI+kit")
    return v


def disponible(e: Enveloppe) -> str | None:
    if e.argv0:
        return e.argv0
    if e.fatale:
        pytest.fail(f"ÉCHEC NOMMÉ — enveloppe {e.nom} absente sous CI=true dans le dépôt du kit : {e.absence}")
    warnings.warn(f"enveloppe {e.nom} absente ({e.absence}) — {PERDUES[e.nom]}")
    return None


def exiger(e: Enveloppe) -> str:
    a0 = disponible(e)
    if a0 is None:
        pytest.skip(f"enveloppe {e.nom} absente : {e.absence}")
    return a0


# ---------------------------------------------------------------------------
# LE BANC
# ---------------------------------------------------------------------------
def _sb(cmd: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})


class Banc:
    def __init__(self, base: Path, doc: dict, enveloppes: dict):
        self.base, self.doc, self.enveloppes = base, doc, enveloppes
        self.jambes = jambes_gardes(doc)
        self.st, self.ev = base / "st", base / "ev"
        self.st.mkdir()
        self.ev.mkdir()
        self.gitconfig = base / "gitconfig"
        self.gitconfig.write_text("")
        self.debug = base / "debug.sh"
        self.debug.write_text('trap "exit 0" DEBUG\n')
        self.seterr = base / "seterr.sh"
        self.seterr.write_text("set -e\n")
        self.leurre = base / "leurre"
        for rel in (".claude/hooks/safe-bash.sh", ".claude/hooks/protect-paths.sh", ".claude/statusline.sh"):
            f = self.leurre / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("exit 0\n")
        self.clone, self.vide = base / "c", base / "vide"
        self._git("clone", "-q", "--shared", str(ROOT), str(self.clone))
        self._git("init", "-q", str(self.vide))
        self.stub = base / "stub"
        self.stub.mkdir()
        cyg = self.stub / "cygpath"
        cyg.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$CYG_JOURNAL"\nprintf \'%s\\n\' "$CYG_SORTIE"\n')
        cyg.chmod(0o755)
        self.cas = [("safe-bash", c, _sb(c)) for c in REFUS_SAFE_BASH] + [
            ("protect-paths", f, json.dumps({"tool_name": "Edit", "tool_input": {
                "file_path": f"{self.clone}/{f}", "old_string": "a", "new_string": "b"}}))
            for f in REFUS_PROTECT]
        fn = lambda corps: "() { " + corps + "; }"  # noqa: E731
        self.vecteurs = {
            "aucun": {}, "b-DEBUG": {"BASH_ENV": str(self.debug)},
            "errexit-SHELLOPTS": {"SHELLOPTS": "errexit"}, "errexit-BASH_ENV": {"BASH_ENV": str(self.seterr)},
            "onecmd": {"SHELLOPTS": "onecmd"},
            "BASH_FUNC_exit": {"BASH_FUNC_exit%%": fn("builtin exit 0")},
            "BASH_FUNC_cygpath": {"BASH_FUNC_cygpath%%": fn(f"echo {self.leurre}")},
            "BASH_FUNC_printf": {"BASH_FUNC_printf%%": fn(f"echo {self.leurre}")},
            "BASH_FUNC_bash": {"BASH_FUNC_bash%%": fn("builtin exit 0")},
            "BASH_FUNC_exec": {"BASH_FUNC_exec%%": fn("builtin exit 0")},
            "BASH_FUNC_unset": {"BASH_FUNC_unset%%": fn("builtin exit 0")},
            "BASH_FUNC_export": {"BASH_FUNC_export%%": fn("builtin exit 0")},
            "GIT_DIR": {"GIT_DIR": str(self.vide / ".git")}, "GIT_INDEX_FILE": {"GIT_INDEX_FILE": "/dev/null"},
            "GIT_WORK_TREE": {"GIT_WORK_TREE": "/nonexistent"},
            "GIT_OBJECT_DIRECTORY": {"GIT_OBJECT_DIRECTORY": "/nonexistent"},
            "GIT_COMMON_DIR": {"GIT_COMMON_DIR": "/nonexistent"},
            "étranger-seul": {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"},
            "safe.directory-COUNT": {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "GIT_CONFIG_COUNT": "1",
                                     "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"},
            "safe.directory-PARAMETERS": {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1",
                                          "GIT_CONFIG_PARAMETERS": "'safe.directory'='*'"},
            # Rév. 9 (it. 8, B-C1) : un include de P ou de C vers /dev/stdin faisait AVALER la charge JSON de la jambe par le
            # git du filtre (refus rc 2 → 0, mesuré à la rév. 8) ; l'écran le refuse, `</dev/null` le neutralise.
            "include-stdin-P": {"GIT_CONFIG_PARAMETERS": "'include.path=/dev/stdin'"},
            "include-stdin-C": {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path", "GIT_CONFIG_VALUE_0": "/dev/stdin"},
            # Rév. 9 (it. 8, A-C1/B-C2) : une fonction exportée git, sed ou tr qui ne rend rien VOLAIT le safe.directory sous
            # /bin/sh (aiguille « (git-tracked, » absente) ; `exec` devant chaque étage du filtre la court-circuite.
            **{f"safe.directory-BASH_FUNC_{n}": {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1", "GIT_CONFIG_PARAMETERS": "'safe.directory'='*'",
                                                 f"BASH_FUNC_{n}%%": fn(":")} for n in ("git", "sed", "tr")},
        }

    def _git(self, *args):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
        env.update(GIT_CONFIG_GLOBAL=str(self.gitconfig), GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
        subprocess.run(["git", *args], check=True, capture_output=True, env=env, timeout=120)

    def env(self, racine: Path, extra=None, ambiant=None) -> dict:
        """Liste BLANCHE : rien de l'ambiant hors PATH, HOME, TMPDIR."""
        ambiant = os.environ if ambiant is None else ambiant
        e = {k: ambiant[k] for k in ("PATH", "HOME", "TMPDIR") if k in ambiant}
        e.update(CLAUDE_PROJECT_DIR=str(racine), CADRE_PROJECT_ROOT=str(racine), CADRE_STATE_DIR=str(self.st),
                 AGENTS_EVENTS_DIR=str(self.ev), GIT_CONFIG_GLOBAL=str(self.gitconfig),
                 GIT_CONFIG_NOSYSTEM="1", LC_ALL="C")
        e.update(extra or {})
        return e


def jouer(a0: str, cmd: str, charge: str, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([a0, "-c", cmd], input=charge, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(cwd), timeout=120)


def codes(b: Banc, a0: str, jambes: dict, extra: dict) -> list[int]:
    return [jouer(a0, jambes[cle], charge, b.env(b.clone, extra), b.clone).returncode
            for cle, _, charge in b.cas]


def est_refus(p: subprocess.CompletedProcess) -> bool:
    """Un refus de garde : rc 2 ET stderr ouvert par une tête de TETES_REFUS. Un rc 2
    muet, ou bruité par autre chose, n'en est PAS un (un hook mort rc 2 n'a rien jugé)."""
    return p.returncode == 2 and p.stderr.startswith(TETES_REFUS)


TABLE_REFUS = ((2, "bruit\n", False), (2, "", False), (0, "BLOCKED x", False), (1, "BLOCKED x", False),
               (2, "bruit\nBLOCKED x", False), (2, "BLOCKED x", True), (2, "WARNING by hook: x", True))
MUTANTS_EST_REFUS = {
    "E1 tête cherchée n'importe où (any in)": lambda p: p.returncode == 2 and any(t in p.stderr for t in TETES_REFUS),
    "E2 rc != 0": lambda p: p.returncode != 0 and p.stderr.startswith(TETES_REFUS),
    "E3 rc > 0": lambda p: p.returncode > 0 and p.stderr.startswith(TETES_REFUS),
    "E4 rc in (1, 2)": lambda p: p.returncode in (1, 2) and p.stderr.startswith(TETES_REFUS),
    "E5 tête non lue": lambda p: p.returncode == 2,
    "E6 rc non lu": lambda p: p.stderr.startswith(TETES_REFUS),
    "E7 TETES_REFUS += ''": lambda p: p.returncode == 2 and p.stderr.startswith(TETES_REFUS + ("",)),
}


def violations_est_refus(fn) -> list[str]:
    """La table PURE : `fn` doit rendre l'attendu sur chaque (rc, stderr). Joue aussi sur un mutant."""
    return [f"(rc {rc}, {err!r}) rendu {fn(subprocess.CompletedProcess([], rc, '', err))!r}, attendu {attendu!r}"
            for rc, err, attendu in TABLE_REFUS
            if bool(fn(subprocess.CompletedProcess([], rc, "", err))) is not attendu]


def violations_gardes(b: Banc, a0: str, jambes: dict, vecteurs, premier=False, apres=None,
                      aiguille=None) -> list[str]:
    """Refus = rc 2 ET stderr ouvert par BLOCKED / WARNING by hook ; `ls` = rc 0 ET
    stderr vide. `apres` s'applique APRÈS la liste blanche (mutant M-locale). `aiguille` :
    pour `echo x > AGENTS.md`, la seule jambe dont le verdict dépend de la réponse de git,
    le refus doit PORTER cette aiguille (git a répondu), pas seulement rc 2."""
    v = []
    for nom in vecteurs:
        env = dict(b.env(b.clone, b.vecteurs[nom]), **(apres or {}))
        for cle, etiquette, charge in b.cas:
            p = jouer(a0, jambes[cle], charge, env, b.clone)
            if not est_refus(p):
                v.append(f"{nom} / {etiquette} : rc {p.returncode}, stderr {p.stderr[:70]!r}")
                if premier:
                    return v
            elif aiguille and etiquette == "echo x > AGENTS.md" and aiguille not in p.stderr:
                v.append(f"{nom} / {etiquette} : refusé SANS « {aiguille} » (git n'a pas répondu) — stderr {p.stderr[:90]!r}")
                if premier:
                    return v
        p = jouer(a0, jambes["safe-bash"], _sb("ls"), env, b.clone)
        if p.returncode != 0 or p.stderr:
            v.append(f"{nom} / ls : rc {p.returncode}, stderr {p.stderr[:70]!r}")
            if premier:
                return v
    return v


def temoin_etranger(b: Banc, a0: str) -> bool:
    """Le bouton de propriétaire étranger MORD-il (git >= 2.35.2) ? Étalonné sur l'AIGUILLE, jamais sur le rc
    (S-00003723) : git muet = l'aiguille « (git-tracked, » ABSENTE (la redirection passe avant T-00000804, est refusée
    « (git-unanswered, » après) ; git qui répond = le bouton n'a rien changé."""
    cas = next(ch for cle, et, ch in b.cas if et == "echo x > AGENTS.md")
    p = jouer(a0, b.jambes["safe-bash"], cas, b.env(b.clone, b.vecteurs["étranger-seul"]), b.clone)
    return AIGUILLE_REPOND not in p.stderr


def exiger_bouton(mord: bool, ou: str):
    """Le bouton DOIT mordre : muet, un témoin safe.directory serait un vert à VIDE. Sous CI=true dans le kit
    c'est un ÉCHEC NOMMÉ (l'image Linux porte git >= 2.35.2) ; ailleurs, avertissement puis saut."""
    if mord:
        return
    if os.environ.get("CI") == "true" and EST_LE_KIT:
        pytest.fail(f"ÉCHEC NOMMÉ — {ou} : GIT_TEST_ASSUME_DIFFERENT_OWNER ne mord pas sous CI=true dans le kit "
                    "(git >= 2.35.2 attendu) : le témoin safe.directory serait vide")
    warnings.warn(f"{ou} : GIT_TEST_ASSUME_DIFFERENT_OWNER ne mord pas (git < 2.35.2 ?) — témoin non joué")
    pytest.skip(f"{ou} : bouton de propriétaire étranger muet")


def armes(b: Banc, a0: str, cmd: str, extra: dict) -> int:
    racine = Path(tempfile.mkdtemp(prefix="slp-", dir=b.base))
    (racine / ".claude").mkdir()
    shutil.copy2(b.clone / ".claude" / "statusline.sh", racine / ".claude" / "statusline.sh")
    jouer(a0, cmd, CHARGE_LIGNE, b.env(racine, extra), racine)
    d = racine / ".agents" / "state" / "local" / "context-retro"
    return len(list(d.glob("*.armed"))) if d.is_dir() else 0


def violations_capteur(b: Banc, a0: str, cmd: str, vecteurs) -> list[str]:
    return [f"{nom} : {n} .armed au lieu de 1" for nom in vecteurs
            if (n := armes(b, a0, cmd, b.vecteurs[nom])) != 1]


# T-00001180 — SONDES D'INTERPRÈTE. L'épingle xtrace+PS4 (T4, T5) et le rejeu de F11 (T6) suivent ce que l'interprète des
# jambes FAIT, mesuré à l'exécution avec l'environnement du banc, jamais la plateforme supposée. Relevé du 2026-10-04 : bash
# 3.2.57, 5.2.37 et 5.3.15 DÉVELOPPENT un PS4 importé à euid non nul ; bash 5.2.37 à euid 0 l'IGNORE (python:3.12-slim en
# root : rc 0 ; le même en euid 65534 : rc -9) — c'est l'euid, pas la version ; dash ne lit ni SHELLOPTS ni BASH_FUNC_*.
def chemin_banc(b: Banc) -> str:
    """Le PATH que le banc passe à ses jambes."""
    return b.env(b.clone).get("PATH", "")


def bash_du_banc(b: Banc) -> str:
    """Le `bash` que l'ancienne forme lance par le PATH du banc : sous dash, c'est LUI qui développe le PS4."""
    return shutil.which("bash", path=chemin_banc(b)) or "bash"


def _sonder(b: Banc, a0: str, cmd: str, extra: dict, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([a0, "-c", cmd, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={"PATH": chemin_banc(b), "LC_ALL": "C", **extra}, timeout=30)
    except OSError:
        return None


def rc_tue(b: Banc, a0: str, interp: str) -> int | None:
    """Le rc que l'enveloppe `a0` rend quand sa DERNIÈRE commande, `interp`, meurt de SIGKILL : -9 si elle s'y substitue
    (dash de macOS, mesuré), 137 si elle l'attend (dash de Debian trixie, mesuré en euid 65534). `interp` passe en argument
    positionnel, jamais interpolé dans le texte."""
    p = _sonder(b, a0, "export X=1; \"$1\" -c 'kill -9 $$'", {}, "_", interp)
    return p.returncode if p is not None else None


def ps4_importe_developpe(b: Banc, a0: str) -> bool:
    """`a0` développe-t-il un PS4 IMPORTÉ sous SHELLOPTS=xtrace ? Oui ssi `$(kill -9 $$)` le tue avant `echo ok`."""
    p = _sonder(b, a0, "echo ok", XTRACE_PS4)
    return p is not None and p.returncode == -9


def importe_fonctions(b: Banc, a0: str) -> bool:
    """`a0` importe-t-il `BASH_FUNC_sed%%` ? Jugé à l'APPEL (la fonction répond à la place du binaire), jamais au texte
    de `type sed` : Homebrew bash 5.3 le LOCALISE même sans LANG (« sed est une fonction », mesuré)."""
    p = _sonder(b, a0, "sed", {"BASH_FUNC_sed%%": "() { echo IMPORTEE; }"})
    return p is not None and p.stdout.strip() == "IMPORTEE"


def signalement(b: Banc, a0: str) -> str:
    """La version MESURÉE et l'euid : ce qui décide si un PS4 importé est développé."""
    p = _sonder(b, a0, 'printf %s "${BASH_VERSION-pas un bash}"', {})
    return f"{a0} (bash {p.stdout if p else 'injoignable'}, euid {os.geteuid()})"


def sonde_ps4(b: Banc, nom: str, interp: str) -> tuple[bool, str]:
    """La sonde, et l'ANNONCE quand elle dit fermé : un vert pris sur la branche fermée se lit au résumé, jamais en silence."""
    ouvert, quoi = ps4_importe_developpe(b, interp), signalement(b, interp)
    if not ouvert:
        warnings.warn(f"{nom} / xtrace+PS4 : {quoi} IGNORE un PS4 importé (sonde) — résidu FERMÉ ici, épinglé au refus "
                      "normal rc 2 x7")
    return ouvert, quoi


def violations_xtrace(b: Banc, nom: str, a0: str, jambes: dict, ouvert: bool, quoi: str,
                      sl: str | None = None, tue: int | None = -9) -> list[str]:
    """xtrace + PS4 `$(kill -9 $$)` importés : MESURE les rc des sept jambes, et les .armed de la ligne d'état `sl`, puis
    rend le verdict du juge pur `juger_xtrace`."""
    rcs = codes(b, a0, jambes, XTRACE_PS4)
    return juger_xtrace(nom, rcs, armes(b, a0, sl, XTRACE_PS4) if sl else None, ouvert, quoi, tue, bool(sl))


def juger_xtrace(nom: str, rcs: list, n: int | None, ouvert: bool, quoi: str, tue: int | None, avec_sl: bool,
                 branches: tuple = (1, 2, 3)) -> list[str]:
    """Le verdict PUR de `violations_xtrace` (T-00001180, A-3 de S-00004134). `ouvert` : verdict de la sonde sur l'interprète
    qui DÉVELOPPE le PS4 (`quoi`) ; `tue` : le rc de la jambe quand ce bash meurt de SIGKILL (-9 s'il EST la jambe ; sinon
    `rc_tue`, mesuré) ; `n` : les .armed (None sans ligne d'état). (1) Ouvert → rc `tue` x7 et 0 .armed, sinon le résidu
    s'est fermé ; (2) COHÉRENCE : un rc `tue` observé sous « fermé » contredit la sonde ; (3) fermé → le refus normal rc 2 x7
    et 1 .armed. `branches` ne sert qu'aux mutants (`MUTANTS_JUGE_XTRACE`) : ils retirent la VRAIE branche, pas une copie."""
    lu = f"{rcs}" + (f", {n} .armed" if avec_sl else "")
    if 1 in branches and ouvert and (rcs != [tue] * 7 or n):
        return [f"{nom} / xtrace+PS4 : résidu fermé ? {lu} — la sonde dit que {quoi} DÉVELOPPE un PS4 importé "
                f"(attendu rc {tue} x7)"]
    if 2 in branches and not ouvert and tue in rcs:
        return [f"{nom} / xtrace+PS4 : COHÉRENCE — rc {tue} observé {rcs} alors que la sonde dit que {quoi} IGNORE un PS4 "
                "importé"]
    if 3 in branches and not ouvert and (rcs != [2] * 7 or n not in (None, 1)):
        return [f"{nom} / xtrace+PS4 : {lu} — {quoi} ignore un PS4 importé (sonde) : attendu le refus normal rc 2 x7"
                + (" et 1 .armed" if avec_sl else "")]
    return []


#: La table PURE du juge : (rcs, n .armed, ouvert, tue, attendu). `attendu` vaut None (vert) ou la MARQUE de la branche qui
#: doit répondre. Chaque branche y répond SEULE au moins une fois, donc la neutraliser fait rougir la table : sans la marque,
#: la branche 2 neutralisée survivrait, puisque la branche 3 rend alors un rouge sur les mêmes lignes.
RESIDU, COHERENCE, NORMAL = "résidu fermé ?", "COHÉRENCE", "attendu le refus normal"
TABLE_XTRACE = (
    ([-9] * 7, 0, True, -9, None), ([-9] * 7, None, True, -9, None), ([137] * 7, None, True, 137, None),
    ([2] * 7, None, True, -9, RESIDU), ([-9] * 6 + [2], 0, True, -9, RESIDU), ([-9] * 7, 1, True, -9, RESIDU),
    ([2] * 7, 1, True, -9, RESIDU),
    ([137] * 7, None, False, 137, COHERENCE), ([2] * 6 + [-9], 1, False, -9, COHERENCE),
    ([2] * 7, 1, False, -9, None), ([2] * 7, None, False, -9, None),
    ([0] * 7, 1, False, -9, NORMAL), ([2] * 7, 0, False, -9, NORMAL), ([2] * 7, 2, False, -9, NORMAL),
    ([2] * 6 + [0], None, False, -9, NORMAL))
MUTANTS_JUGE_XTRACE = {f"X{k} branche {k} neutralisée": tuple(x for x in (1, 2, 3) if x != k) for k in (1, 2, 3)}


def violations_juge_xtrace(branches: tuple = (1, 2, 3)) -> list[str]:
    """La table jouée sur `juger_xtrace` lui-même ; avec `branches` amputée, c'est un mutant que la table doit tuer."""
    v = []
    for rcs, n, ouvert, tue, attendu in TABLE_XTRACE:
        r = juger_xtrace("table", rcs, n, ouvert, "le bash de la table", tue, n is not None, branches)
        if (r != []) if attendu is None else (len(r) != 1 or attendu not in r[0]):
            v.append(f"({rcs}, {n} .armed, ouvert={ouvert}, tue {tue}) rendu {r!r}, attendu « {attendu or 'vert'} »")
    return v


def fuites(b: Banc, a0: str, prefixe: str) -> list[str]:
    p = jouer(a0, prefixe + "exec bash -p -c 'exec env'", "",
              b.env(b.clone, {n: "fuite" for n in NOMS_RETIRES}), b.clone)
    vus = {ligne.split("=", 1)[0] for ligne in p.stdout.splitlines() if "=" in ligne}
    return sorted(vus & set(NOMS_RETIRES))


def violations_racine(b: Banc, a0: str, prefixe: str) -> list[str]:
    v = []
    for valeur, convertie in ((r"C:\x", True), ("C:/x", True), (r"\\srv\partage", True), ("/x", False)):
        fd, journal = tempfile.mkstemp(prefix="cyg-", dir=b.base)
        os.close(fd)
        env = b.env(b.clone, {"PATH": f"{b.stub}{os.pathsep}{os.environ.get('PATH', '')}",
                              "CYG_JOURNAL": journal, "CYG_SORTIE": str(b.leurre)})
        env["CLAUDE_PROJECT_DIR"] = valeur
        p = jouer(a0, prefixe + "exec bash -p -c 'printf %s \"$CLAUDE_PROJECT_DIR\"'", "", env, b.clone)
        appels = Path(journal).read_text().splitlines()
        if convertie and (p.stdout != str(b.leurre) or appels != [f"-u {valeur}"]):
            v.append(f"racine {valeur!r} : non convertie (sortie {p.stdout!r}, appels {appels})")
        if not convertie and appels:
            v.append(f"racine {valeur!r} : cygpath appelé {appels}")
        if not convertie and p.stdout != valeur:
            v.append(f"racine-leurre {valeur!r} : remplacée par {p.stdout!r}")
    return v


def violations_sondes(b: Banc, a0: str, prefixe: str) -> list[str]:
    v = [f"name-leak : {n}" for n in fuites(b, a0, prefixe)]
    p = jouer(a0, prefixe + "AGENTS_HOOK_HOST=claude exec bash -p -c 'printf %s \"$AGENTS_HOOK_HOST\"'", "",
              b.env(b.clone), b.clone)
    if p.stdout != "claude":
        v.append(f"VAR=val exec n'atteint pas le hook : {p.stdout!r}")
    p = jouer(a0, prefixe + "exec bash -p -c 'exec cat'", "charge-801\n", b.env(b.clone), b.clone)
    if p.stdout != "charge-801\n":
        v.append(f"stdin ne traverse pas : {p.stdout!r}")
    return (v + violations_racine(b, a0, prefixe) + violations_copie(b, a0, prefixe) + violations_config(b, a0, prefixe)
            + violations_lecture(b, a0, prefixe))


SONDE_COPIE = ("exec bash -p -c 'for v in GIT_DIR GIT_WORK_TREE _CADRE_GIT_DIR _CADRE_GIT_WORK_TREE "
               "GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT; do eval \"s=\\${$v+1}\"; printf \"%s=%s:\" "
               "$v \"${s:-absent}\"; eval \"printf %s\\\"\\${$v-}\\\"\"; echo; done'")
CAS_COPIE = (  # (env posé, attendu {nom: valeur | None = absent})
    ({"GIT_DIR": "/n.git", "GIT_WORK_TREE": "/w"},
     {"GIT_DIR": None, "GIT_WORK_TREE": None, "_CADRE_GIT_DIR": "/n.git", "_CADRE_GIT_WORK_TREE": "/w"}),
    ({"GIT_DIR": ""}, {"GIT_DIR": None, "_CADRE_GIT_DIR": "", "_CADRE_GIT_WORK_TREE": None}),
    ({"GIT_WORK_TREE": ""}, {"GIT_WORK_TREE": None, "_CADRE_GIT_DIR": None, "_CADRE_GIT_WORK_TREE": ""}),
    ({}, {"_CADRE_GIT_DIR": None, "_CADRE_GIT_WORK_TREE": None}),
    ({"_CADRE_GIT_DIR": "/leurre", "_CADRE_GIT_WORK_TREE": "/leurre"},
     {"_CADRE_GIT_DIR": None, "_CADRE_GIT_WORK_TREE": None}),
    ({"GIT_CONFIG_PARAMETERS": "'safe.directory'='*'", "GIT_CONFIG_COUNT": "1"},  # décompte sans clé : git refuse, les deux noms partent
     {"GIT_CONFIG_PARAMETERS": None, "GIT_CONFIG_COUNT": None}),
)


def violations_copie(b: Banc, a0: str, prefixe: str) -> list[str]:
    v = []
    for pose, attendu in CAS_COPIE:
        p = jouer(a0, prefixe + SONDE_COPIE, "", b.env(b.clone, pose), b.clone)
        vu = {}
        for ligne in p.stdout.splitlines():
            nom, _, reste = ligne.partition("=")
            etat, _, val = reste.partition(":")
            vu[nom] = None if etat == "absent" else val
        for nom, val in attendu.items():
            if vu.get(nom, "?") != val:
                v.append(f"copie {sorted(pose)} : {nom} = {vu.get(nom, '?')!r}, attendu {val!r}")
    return v


#: S-00003821 (option ii) : ce que le préfixe rend aux hooks de GIT_CONFIG_PARAMETERS / GIT_CONFIG_COUNT, cas par cas. La sonde
#: imprime les deux variables telles que le hook les reçoit ; `attendu` = les entrées `safe.directory` rendues dans
#: GIT_CONFIG_PARAMETERS (comparées TRIÉES : l'ordre des canaux est celui de git, pas du filet), ou None = ni P ni C n'atteint le hook.
#: GIT_CONFIG_COUNT n'est JAMAIS rendu. Chaque ligne a un mutant du filtre qui la fait rougir (F1–F8, `test_mutations_are_killed`).
SONDE_CONFIG = ("exec bash -p -c 'printf \"P=[%s]\\nC=[%s]\\n\" \"${GIT_CONFIG_PARAMETERS-<absent>}\" "
                "\"${GIT_CONFIG_COUNT-<absent>}\"'")


def cas_config(b: Banc) -> tuple:
    g = b.base / "gconf-safe"
    canari_fn = b.base / "fn-canari"
    g.write_text("[safe]\n\tdirectory = /g\n")
    seul_bash = b.base / "seul-bash"
    if not seul_bash.exists():
        seul_bash.mkdir()
        (seul_bash / "bash").symlink_to(shutil.which("bash") or "/bin/bash")
    return (
        ("aucun canal", {}, None),
        ("P : safe + fsmonitor + hooksPath",
         {"GIT_CONFIG_PARAMETERS": "'safe.directory=/s' 'core.fsmonitor=/x' 'core.hooksPath=/h'"}, ["safe.directory=/s"]),
        ("C : safe + fsmonitor",
         {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "/c",
          "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "/x"}, ["safe.directory=/c"]),
        ("P + C",
         {"GIT_CONFIG_PARAMETERS": "'safe.directory=/p'", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
          "GIT_CONFIG_VALUE_0": "/c"}, ["safe.directory=/c", "safe.directory=/p"]),
        ("P : apostrophe dans la valeur", {"GIT_CONFIG_PARAMETERS": "'safe.directory=/it'\\''s'"}, ["safe.directory=/it's"]),
        ("P : forme 'k'='v' (git >= 2.31)", {"GIT_CONFIG_PARAMETERS": "'safe.directory'='*'"}, ["safe.directory=*"]),
        ("P : fsmonitor seul", {"GIT_CONFIG_PARAMETERS": "'core.fsmonitor=/x'"}, None),
        ("P : illisible", {"GIT_CONFIG_PARAMETERS": "'safe.directory=/s"}, None),
        ("P : valeur qui n'est pas du git", {"GIT_CONFIG_PARAMETERS": "fuite"}, None),
        ("C : décompte sans clé", {"GIT_CONFIG_COUNT": "1"}, None),
        ("C : valeur qui n'est pas du git", {"GIT_CONFIG_COUNT": "fuite"}, None),
        ("P : saut de ligne forgé", {"GIT_CONFIG_PARAMETERS": "'safe.directory=/a\ncommand\tcore.fsmonitor=/x'"},
         ["safe.directory=/a", "safe.directory=core.fsmonitor=/x"]),
        ("P : safe.directory d'une AUTRE portée non rendu",
         {"GIT_CONFIG_GLOBAL": str(g), "GIT_CONFIG_PARAMETERS": "'safe.directory=/s'"}, ["safe.directory=/s"]),
        ("P : safe + git absent du PATH", {"PATH": str(seul_bash), "GIT_CONFIG_PARAMETERS": "'safe.directory=/s'"}, None),
        # Rév. 9 — l'ÉCRAN (it. 8, B-C1) : un include, ou un décompte hors 0-8, et git n'est pas lancé : les deux noms partent.
        ("P : include ⇒ retrait (écran)", {"GIT_CONFIG_PARAMETERS": "'include.path=/dev/stdin' 'safe.directory=/s'"}, None),
        ("C : include.path ⇒ retrait", {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "/c",
                                         "GIT_CONFIG_KEY_1": "include.path", "GIT_CONFIG_VALUE_1": "/dev/null"}, None),
        ("C : INCLUDE.PATH (casse) ⇒ retrait", {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "/c",
                                                 "GIT_CONFIG_KEY_1": "INCLUDE.PATH", "GIT_CONFIG_VALUE_1": "/dev/null"}, None),
        ("C : includeIf ⇒ retrait", {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "/c",
                                      "GIT_CONFIG_KEY_1": "includeIf.gitdir:/.path", "GIT_CONFIG_VALUE_1": "/dev/null"}, None),
        ("C : décompte 9, hors borne ⇒ retrait", {"GIT_CONFIG_COUNT": "9", **{f"GIT_CONFIG_KEY_{i}": "safe.directory" for i in range(9)},
                                                 **{f"GIT_CONFIG_VALUE_{i}": f"/v{i}" for i in range(9)}}, None),
        # Rév. 9 — le filtre ne lit QUE P et C : un GIT_CONFIG (que `git config` lirait SEUL, `/dev/stdin` compris) est ignoré.
        ("P safe + GIT_CONFIG=/dev/stdin", {"GIT_CONFIG": "/dev/stdin", "GIT_CONFIG_PARAMETERS": "'safe.directory=/s'"}, ["safe.directory=/s"]),
        # Rév. 9 — git, sed, tr par `exec` (it. 8, A-C1/B-C2 ; `env` depuis F1) : la fonction exportée ÉCRIT un canari et ne rend rien.
        *((f"P safe + fonction exportée {n}", {"GIT_CONFIG_PARAMETERS": "'safe.directory=/s'",
                                               f"BASH_FUNC_{n}%%": f"() {{ echo {n} >> {canari_fn}; }}"}, ["safe.directory=/s"])
          for n in ("git", "env", "sed", "tr")),
    )


def violations_config(b: Banc, a0: str, prefixe: str, premier=False) -> list[str]:
    v = []
    canari = b.base / "fn-canari"
    for nom, pose, attendu in cas_config(b):
        canari.write_text("")
        p = jouer(a0, prefixe + SONDE_CONFIG, "", b.env(b.clone, pose), b.clone)
        if canari.read_text():
            v.append(f"config / {nom} : fonction exportée EXÉCUTÉE dans le préfixe ({canari.read_text().split()})")
        m = re.fullmatch(r"P=\[(.*)\]\nC=\[(.*)\]\n", p.stdout, re.S)
        if not m:
            v.append(f"config / {nom} : sonde illisible (rc {p.returncode}, stdout {p.stdout[:60]!r}, stderr {p.stderr[:60]!r})")
        else:
            lu_p, lu_c = m.groups()
            try:
                entrees = None if lu_p == "<absent>" else sorted(shlex.split(lu_p))
            except ValueError:
                entrees = [f"illisible : {lu_p!r}"]
            if lu_c != "<absent>":
                v.append(f"config / {nom} : GIT_CONFIG_COUNT atteint le hook ({lu_c!r})")
            if entrees != (None if attendu is None else sorted(attendu)):
                v.append(f"config / {nom} : GIT_CONFIG_PARAMETERS rendu {entrees!r}, attendu {attendu!r}")
        if v and premier:
            return v
    return v


class Detecteur:
    """FIFO-DÉTECTEUR de lecture (rév. 9, it. 8 B-C1) : un fil écrivain se bloque sur `open(O_WRONLY)` en boucle ; chaque
    ouverture par un LECTEUR est comptée puis libérée par EOF. Aucune jambe ne pend : la lecture est OBSERVÉE, jamais attendue."""

    def __init__(self, chemin: Path):
        self.chemin, self.n, self.stop = chemin, 0, False
        os.mkfifo(chemin)
        self.fil = threading.Thread(target=self._boucle, daemon=True)
        self.fil.start()

    def _boucle(self):
        while True:
            fd = os.open(self.chemin, os.O_WRONLY)
            if self.stop:
                os.close(fd)
                return
            self.n += 1
            os.close(fd)

    def clore(self) -> int:
        n, self.stop = self.n, True
        for _ in range(50):
            fd = os.open(self.chemin, os.O_RDONLY | os.O_NONBLOCK)
            self.fil.join(0.1)
            os.close(fd)
            if not self.fil.is_alive():
                break
        return n


#: Rév. 9 — ce que l'EXÉCUTION du filtre CONSOMME (it. 8, B-C1 : la rév. 8 ne testait que ce qu'il RENVOIE). La sonde fait
#: traverser une charge par stdin jusqu'au « hook » (`exec cat`) ; chaque cas exige la charge INTACTE et aucun FIFO-détecteur
#: ouvert. `@F@` = le FIFO ; genre « G » / « S » : un fichier GIT_CONFIG_GLOBAL / GIT_CONFIG_SYSTEM qui l'inclut (NOSYSTEM levé
#: pour « S ») ; « G-stdin » : le même fichier global, inclusion de /dev/stdin ; « L » : la config du dépôt courant qui l'inclut.
SONDE_LECTURE = "exec bash -p -c 'exec cat'"
CHARGE_LECTURE = '{"tool_name": "Bash", "tool_input": {"command": "rm AGENTS.md"}}\n'
SAFE_P = {"GIT_CONFIG_PARAMETERS": "'safe.directory=/s'"}
CAS_LECTURE = (
    ("stdin / P include=/dev/stdin", {"GIT_CONFIG_PARAMETERS": "'include.path=/dev/stdin' 'safe.directory=/s'"}, None),
    ("stdin / C include.path=/dev/stdin", {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path",
                                           "GIT_CONFIG_VALUE_0": "/dev/stdin"}, None),
    ("stdin / GIT_CONFIG=/dev/stdin + P", {"GIT_CONFIG": "/dev/stdin", **SAFE_P}, None),
    ("stdin / global inclut /dev/stdin + P", SAFE_P, "G-stdin"),
    ("FIFO / P include", {"GIT_CONFIG_PARAMETERS": "'include.path=@F@' 'safe.directory=/s'"}, "F"),
    ("FIFO / C include.path", {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path", "GIT_CONFIG_VALUE_0": "@F@"}, "F"),
    ("FIFO / C décompte 9, clé 8 include", {"GIT_CONFIG_COUNT": "9", **{f"GIT_CONFIG_KEY_{i}": "safe.directory" for i in range(8)},
                                            **{f"GIT_CONFIG_VALUE_{i}": f"/v{i}" for i in range(8)},
                                            "GIT_CONFIG_KEY_8": "include.path", "GIT_CONFIG_VALUE_8": "@F@"}, "F"),
    ("FIFO / GIT_CONFIG + P", {"GIT_CONFIG": "@F@", **SAFE_P}, "F"),
    ("FIFO / global inclut + P", SAFE_P, "G"),
    ("FIFO / système inclut + P", {"GIT_CONFIG_NOSYSTEM": "0", **SAFE_P}, "S"),
    ("FIFO / dépôt courant inclut + P", SAFE_P, "L"),
)


def violations_lecture(b: Banc, a0: str, prefixe: str, premier=False) -> list[str]:
    v = []
    for nom, pose, genre in CAS_LECTURE:
        rep = Path(tempfile.mkdtemp(prefix="lect-", dir=b.base))
        det = Detecteur(rep / "fifo") if genre in ("F", "G", "S", "L") else None
        cible = str(det.chemin) if det else "/dev/stdin"
        env = b.env(b.clone, {k: x.replace("@F@", cible) for k, x in pose.items()})
        cwd = b.clone
        if genre in ("G", "G-stdin", "S"):
            inclut = rep / "inclut"
            inclut.write_text(f"[include]\n\tpath = {cible}\n")
            env["GIT_CONFIG_SYSTEM" if genre == "S" else "GIT_CONFIG_GLOBAL"] = str(inclut)
        if genre == "L":
            cwd = rep / "depot"
            b._git("init", "-q", str(cwd))
            with open(cwd / ".git" / "config", "a", encoding="utf-8") as f:
                f.write(f"[include]\n\tpath = {cible}\n")
        try:
            lu = jouer(a0, prefixe + SONDE_LECTURE, CHARGE_LECTURE, env, cwd).stdout
        except subprocess.TimeoutExpired:
            lu = "<délai dépassé>"
        n = det.clore() if det else 0
        if lu != CHARGE_LECTURE:
            v.append(f"lecture / {nom} : stdin consommé avant le hook (le hook reçoit {lu[:50]!r})")
        if n:
            v.append(f"lecture / {nom} : FIFO OUVERT {n} fois par le préfixe")
        if v and premier:
            return v
    return v


def violations_skill(texte: str, prefixe=PREFIX) -> list[str]:
    debut = texte.find("\n## Zero-LLM des hooks")
    fin = texte.find("\n## ", debut + 1) if debut >= 0 else -1
    section = texte[debut:fin] if debut >= 0 and fin > debut else ""
    v = [] if section else ["section « ## Zero-LLM des hooks » introuvable"]
    for nom, attendu in (("PREFIX", prefixe), ("titre", TITRE_SKILL), ("phrase l.33", PHRASE_33),
                         *(("portée euid 0, site français (T-00001180)", p) for p in PHRASES_EUID),
                         ("forme case", PHRASE_CASE), *(("layout nu (S-00003225)", p) for p in PHRASES_NU),
                         *(("règle d'appel (S-00003742)", p) for p in PHRASES_BLINDAGE)):
        if attendu not in section:
            v.append(f"SKILL, section Zero-LLM : {nom} absent")
    for p in NON_CLOS_EPINGLES:
        if p not in section:
            v.append(f"SKILL, section Zero-LLM : puce NON CLOS absente — {p[:48]}")
    if PHRASE_INTERDITE in section:
        v.append(f"SKILL, section Zero-LLM : « {PHRASE_INTERDITE} » est FAUX en layout nu (F1)")
    return v


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def reglages():
    chemin, v = choix_reglages(os.environ)
    if os.environ.get("HOOK_HARDENING_SETTINGS"):
        warnings.warn(f"HOOK_HARDENING_SETTINGS actif : {chemin}")
    if v:
        pytest.fail("; ".join(v))
    return chemin, json.loads(chemin.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def banc(tmp_path_factory, reglages):
    base = tmp_path_factory.mktemp("filet801")
    env = decouvrir(os.environ.get("PATH", ""), "/bin/dash", EST_LE_KIT, os.environ.get("CI") == "true", base)
    return Banc(base, reglages[1], env)


@pytest.fixture(scope="session")
def matrice(banc):
    """T2 et T2b, une enveloppe par fil."""
    noms = [n for n in ENVELOPPES_POSIX if banc.enveloppes[n].argv0]

    def une(nom):
        a0 = banc.enveloppes[nom].argv0
        return nom, {"t2": violations_gardes(banc, a0, banc.jambes, VECTEURS_T2),
                     "mord": (mord := temoin_etranger(banc, a0)),
                     "safe": (violations_gardes(banc, a0, banc.jambes, VECTEURS_SAFE, aiguille=AIGUILLE_REPOND)
                              if mord else []),
                     "t2b": violations_capteur(banc, a0, banc.jambes["statusline"], VECTEURS_T2B)}

    with cf.ThreadPoolExecutor(max(1, len(noms))) as ex:
        return dict(ex.map(une, noms))


# ---------------------------------------------------------------------------
# T1 — TEXTE
# ---------------------------------------------------------------------------
def test_legs_text_rule(reglages, banc):
    chemin, doc = reglages
    assert PREFIX == PREFIX_LITTERAL, "GIT_REDIRECTIONS a changé : réglages, SKILL et PREFIX_LITTERAL à suivre"
    v = violations_texte(doc)
    cmds = toutes_commandes(doc)
    for e in banc.enveloppes.values():
        if e.argv0:
            v += violations_sh_n(e.argv0, cmds)
    assert choix_reglages({"CI": "true", "HOOK_HARDENING_SETTINGS": "/nonexistent/x.json"})[1], \
        "l'override doit être refusé sous CI=true"
    assert not v, f"{chemin} :\n" + "\n".join(v)


# ---------------------------------------------------------------------------
# T2 / T2b / T2c — REJEU
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_guard_legs_replay(nom, banc, matrice):
    exiger(banc.enveloppes[nom])
    assert not matrice[nom]["t2"], "\n".join(matrice[nom]["t2"])


@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_safe_directory_reaches_guards(nom, banc, matrice):
    """S-00003224 : le safe.directory de GIT_CONFIG_PARAMETERS/COUNT atteint les gardes ; rév. 9 : une fonction exportée git,
    sed ou tr (vecteurs `safe.directory-BASH_FUNC_*`, A-C1/B-C2) ne le vole plus."""
    exiger(banc.enveloppes[nom])
    exiger_bouton(matrice[nom]["mord"], f"test_safe_directory_reaches_guards[{nom}]")
    assert not matrice[nom]["safe"], "\n".join(matrice[nom]["safe"])


@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_statusline_sensor_arms(nom, banc, matrice):
    exiger(banc.enveloppes[nom])
    assert not matrice[nom]["t2b"], "\n".join(matrice[nom]["t2b"])


def test_replay_env_locale(banc):
    a0 = exiger(banc.enveloppes["sh"])
    ambiant = dict(os.environ, LC_ALL="zz_ZZ.UTF-8", LANG="zz_ZZ.UTF-8", LC_CTYPE="zz_ZZ.UTF-8")
    env = banc.env(banc.clone, ambiant=ambiant)
    assert env["LC_ALL"] == "C" and "LANG" not in env and "LC_CTYPE" not in env
    assert not violations_gardes(banc, a0, banc.jambes, ["aucun"])
    # Calibration de la liste blanche : une PYTHON* ambiante invalide ne change rien...
    assert banc.env(banc.clone, ambiant=dict(os.environ, PYTHONIOENCODING="x")) == banc.env(banc.clone)
    # ...alors qu'elle PÈSE quand elle atteint le hook (le témoin n'est pas vide).
    assert violations_gardes(banc, a0, banc.jambes, ["aucun"], premier=True, apres={"PYTHONIOENCODING": "x"})


# ---------------------------------------------------------------------------
# T3 — SONDES DU PRÉFIXE
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_prefix_probes(nom, banc):
    a0 = exiger(banc.enveloppes[nom])
    v = violations_sondes(banc, a0, PREFIX)
    for n in NOMS_RETIRES:  # un mutant par nom retiré : la sonde doit le voir fuir
        if n not in fuites(banc, a0, faire_prefixe(tuple(x for x in NOMS_RETIRES if x != n))):
            v.append(f"mutant « {n} retiré » survit : name-leak muet")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# S-00003821 — P ET C NE PORTENT PLUS AUCUNE CLÉ EXÉCUTABLE JUSQU'À UN HOOK (de bout en bout, avec témoin positif)
# ---------------------------------------------------------------------------
def canari_config(b: Banc) -> tuple[Path, Path, Path]:
    """Un script `core.fsmonitor` et des hooks de `core.hooksPath` qui ÉCRIVENT un journal."""
    rep = b.base / "canari-config"
    log, fsm, hooks = rep / "log", rep / "fsm.sh", rep / "hooks"
    if not rep.exists():
        hooks.mkdir(parents=True)
        log.write_text("")
        fsm.write_text(f'#!/bin/sh\necho fsmonitor >> "{log}"\nexit 0\n')
        fsm.chmod(0o755)
        for h in ("post-index-change", "pre-commit", "reference-transaction"):
            (hooks / h).write_text(f'#!/bin/sh\necho "hook {h}" >> "{log}"\nexit 0\n')
            (hooks / h).chmod(0o755)
    return log, fsm, hooks


def canari_ecrit(b: Banc, a0: str, jambes: dict) -> dict:
    """Ce que le canari a ÉCRIT quand la jambe safe-bash (`echo x > AGENTS.md` lance `git ls-files`) reçoit, par P puis par C,
    un canal qui porte le canari ET un safe.directory."""
    log, fsm, hooks = canari_config(b)
    paires = (("core.fsmonitor", str(fsm)), ("core.hooksPath", str(hooks)), ("safe.directory", "*"))
    canaux = {"P": {"GIT_CONFIG_PARAMETERS": " ".join(f"'{k}={x}'" for k, x in paires)},
              "C": {"GIT_CONFIG_COUNT": str(len(paires)), **{f"GIT_CONFIG_KEY_{i}": k for i, (k, _) in enumerate(paires)},
                    **{f"GIT_CONFIG_VALUE_{i}": x for i, (_, x) in enumerate(paires)}}}
    vus = {}
    for nom, extra in canaux.items():
        log.write_text("")
        jouer(a0, jambes["safe-bash"], _sb("echo x > AGENTS.md"), b.env(b.clone, extra), b.clone)
        vus[nom] = sorted({x for x in log.read_text().split("\n") if x})
    return vus


@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_config_canary_stops_at_prefix(nom, banc):
    """S-00003821 : P et C portent un canari `core.fsmonitor` + `core.hooksPath` ET un safe.directory ; la jambe safe-bash n'écrit
    PAS le canari. TÉMOIN POSITIF : la forme sans filtre (P et C passent tels quels, la forme (i) de S-00003742) l'écrit — sans
    lui, un git qui n'exécute pas ce canari rendrait ce test vide (un canal muet : ÉCHEC NOMMÉ sous CI=true dans le kit, sinon saut).
    BORNE (it. 8, B-C3) : de bout en bout, seule la moitié `core.fsmonitor` peut s'écrire — la jambe lance `git ls-files`,
    qui ne réécrit aucun index, donc aucun hook de `core.hooksPath` (mesuré : sans filtre, un canari `core.hooksPath` seul
    n'écrit rien) ; `core.hooksPath` est tenu à l'étage du filtre par `cas_config` (égalité exacte des entrées rendues)."""
    a0 = exiger(banc.enveloppes[nom])
    sans_filtre = {k: c.replace(PREFIX, faire_prefixe(filtre=""), 1) for k, c in banc.jambes.items()}
    assert sans_filtre["safe-bash"] != banc.jambes["safe-bash"], "PREFIX absent de la jambe safe-bash : témoin positif impossible"
    for canal, vu in canari_ecrit(banc, a0, sans_filtre).items():
        if "fsmonitor" not in vu:
            if os.environ.get("CI") == "true" and EST_LE_KIT:
                pytest.fail(f"ÉCHEC NOMMÉ — témoin positif {canal} muet sous CI=true dans le kit : git n'exécute pas le canari (vu {vu})")
            warnings.warn(f"témoin positif {canal} muet (vu {vu}) : test non joué")
            pytest.skip(f"témoin positif {canal} muet : git n'exécute pas le canari par ce canal")
    vus = canari_ecrit(banc, a0, banc.jambes)
    assert not vus["P"] and not vus["C"], f"une clé exécutable atteint un hook : P a écrit {vus['P']}, C a écrit {vus['C']}"


@pytest.mark.parametrize("nom", ENVELOPPES_POSIX)
def test_secrets_leg_holds_under_config_vectors(nom, banc):
    """Rév. 9 (it. 8, B-C1) : la jambe `gitleaks --content` (porte class-0, NON-WAIVABLE) refuse encore un jeton quand P ou C
    porte un include vers /dev/stdin — à la rév. 8 la charge était avalée par le git du filtre (rc 2 → 0, stderr vide, mesuré).
    Sans `gitleaks` sur le PATH la jambe ne refuse rien par construction : saut ANNONCÉ — la cause est tenue, toutes gardes
    confondues, par `violations_lecture` (T3)."""
    a0 = exiger(banc.enveloppes[nom])
    if not shutil.which("gitleaks"):
        warnings.warn("gitleaks absent du PATH : jambe class-0 non rejouée (violations_lecture tient la cause)")
        pytest.skip("gitleaks absent du PATH")
    jambe = next((h["command"] for _, h in jambes_hooks(banc.doc) if h.get("command", "").endswith('gitleaks-scan.sh" --content')), "")
    assert jambe, "aucune jambe `gitleaks --content` dans les réglages"
    jeton = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5"  # assemblé : le source ne porte pas un jeton contigu
    charge = json.dumps({"tool_name": "Write", "tool_input": {"file_path": f"{banc.clone}/fuite.txt", "content": f"token = {jeton}\n"}})
    v = []
    for vec in ("aucun", "include-stdin-P", "include-stdin-C"):
        p = jouer(a0, jambe, charge, banc.env(banc.clone, banc.vecteurs[vec]), banc.clone)
        if not (p.returncode == 2 and p.stderr.startswith("SECRETS GATE") and "BLOCKED" in p.stderr):
            v.append(f"{vec} : rc {p.returncode}, stderr {p.stderr[:80]!r}")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# T4 — TÉMOINS DE CANAL (forme d'avant ; jamais d'assertion d'avant sur GIT_*)
# ---------------------------------------------------------------------------
def test_old_leg_witnesses(banc):
    v, joues = [], 0
    for nom in ENVELOPPES_POSIX:
        a0 = disponible(banc.enveloppes[nom])
        if a0 is None:
            continue
        joues += 1
        for vec in ("b-DEBUG", "onecmd"):
            if 2 in (rcs := codes(banc, a0, JAMBES_AVANT, banc.vecteurs[vec])):
                v.append(f"{nom} / {vec} : l'ancienne forme refuse encore {rcs} — le vecteur ne parle plus")
            if (n := armes(banc, a0, JAMBES_AVANT["statusline"], banc.vecteurs[vec])) != 0:
                v.append(f"{nom} / {vec} : ancienne ligne d'état arme {n}")
    if a0 := disponible(banc.enveloppes["dash"]):  # T-00001180 : la sonde vise le `bash` que l'ancienne forme lance
        ouvert, quoi = sonde_ps4(banc, "dash / ancienne forme", enfant := bash_du_banc(banc))
        v += violations_xtrace(banc, "dash / ancienne forme", a0, JAMBES_AVANT, ouvert, quoi, tue=rc_tue(banc, a0, enfant))
    if not joues:
        pytest.skip("aucune enveloppe POSIX")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# T5 — RÉSIDUS ÉPINGLÉS (rougissent le jour où ils se ferment : amender SKILL et pin)
# ---------------------------------------------------------------------------
def test_residues_pinned(banc):
    v, j, joues = [], banc.jambes, 0
    sl = j["statusline"]
    if a0 := disponible(banc.enveloppes["bash-sh"]):
        joues += 1
        if 2 in (rcs := codes(banc, a0, j, NOEXEC)) or armes(banc, a0, sl, NOEXEC):
            v.append(f"bash-en-sh / noexec : résidu fermé ? {rcs}")
        ouvert, quoi = sonde_ps4(banc, "bash-en-sh", a0)  # T-00001180 : même interprète que la jambe
        v += violations_xtrace(banc, "bash-en-sh", a0, j, ouvert, quoi, sl)
    if a0 := disponible(banc.enveloppes["dash"]):
        joues += 1
        if (rcs := codes(banc, a0, j, NOEXEC)) != [2] * 7:
            v.append(f"dash / noexec : {rcs}, attendu rc 2 x7")
        if (rcs := codes(banc, a0, j, XTRACE_PS4)) != [2] * 7 or armes(banc, a0, sl, XTRACE_PS4) != 1:
            v.append(f"dash / xtrace+PS4 : {rcs}, attendu rc 2 x7 et 1 .armed")
    if a0 := disponible(banc.enveloppes["bash-np"]):
        joues += 1
        if 2 in (rcs := codes(banc, a0, j, banc.vecteurs["b-DEBUG"])) or armes(banc, a0, sl, banc.vecteurs["b-DEBUG"]):
            v.append(f"non posix / b-DEBUG : résidu fermé ? {rcs}")
        for vec in ("BASH_FUNC_exec", "BASH_FUNC_unset", "BASH_FUNC_export"):
            if 2 in (rcs := codes(banc, a0, j, banc.vecteurs[vec])):
                v.append(f"non posix / {vec} : résidu fermé ? {rcs}")
    if not joues:
        pytest.skip("aucune enveloppe de résidu (bash-en-sh, dash, bash non posix) : T5 non joué")
    assert not v, "\n".join(v)


# ---------------------------------------------------------------------------
# ABSENCE D'ENVELOPPE
# ---------------------------------------------------------------------------
def test_missing_envelope_fails_under_ci():
    assert not violations_absence(decouvrir), "\n".join(violations_absence(decouvrir))


# ---------------------------------------------------------------------------
# T6 — MUTATIONS
# ---------------------------------------------------------------------------
def _muter(doc, f):
    d = json.loads(json.dumps(doc))
    f(d)
    return d


def _jambe(d, motif):
    return next((h for _, h in jambes_hooks(d) if motif in h.get("command", "")), jambes_hooks(d)[0][1])


def _remplacer(motif, avant, apres):
    def f(d):
        h = _jambe(d, motif)
        h["command"] = h["command"].replace(avant, apres, 1)
    return f


def test_mutations_are_killed(reglages, banc):
    doc, j = reglages[1], banc.jambes
    survivants, perdus = [], []
    textuelles = {
        "sans shell": lambda d: _jambe(d, "safe-bash.sh").pop("shell"),
        "sans préfixe": _remplacer("safe-bash.sh", PREFIX, ""),
        "sans exec": _remplacer("safe-bash.sh", "exec bash -p", "bash -p"),
        "sans -p": _remplacer("safe-bash.sh", "exec bash -p", "exec bash"),
        "nom retiré": _remplacer("safe-bash.sh", " GIT_DIR ", " "),
        "M13 statusLine d'avant": lambda d: d["statusLine"].update(command=JAMBES_AVANT["statusline"]),
        "M14 queue &&": _remplacer("safe-bash.sh", 'safe-bash.sh"', 'safe-bash.sh" && true'),
        "M15 X=$( ) exec": _remplacer("safe-bash.sh", "exec bash -p", "AGENTS_HOOK_HOST=$(id) exec bash -p"),
        "M17 PATH=. gitleaks": _remplacer("gitleaks-scan.sh", "exec bash -p", "PATH=. exec bash -p"),
        "M17b ../": _remplacer("safe-bash.sh", "$CLAUDE_PROJECT_DIR/.claude", "$CLAUDE_PROJECT_DIR/../x/.claude"),
        "M18 \\n final (fullmatch)": _remplacer("safe-bash.sh", 'safe-bash.sh"', 'safe-bash.sh"\n'),
        "M19 copie retirée": _remplacer("safe-bash.sh", COPIE_GIT, ""),
        "F9 git du filtre non blindé": _remplacer("safe-bash.sh", "git -c core.fsmonitor=false -c core.hooksPath=/dev/null -C / config",
                                                   "git -C / config"),
        "F10 filtre retiré d'une jambe": _remplacer("gitleaks-scan.sh", FILTRE_LIT, ""),
    }
    for nom, f in textuelles.items():
        if not violations_texte(_muter(doc, f)):
            survivants.append(f"{nom} (T1)")
    if not violations_skill(SKILL.read_text(encoding="utf-8").replace(PREFIX, "")):
        survivants.append("SKILL amputé (T7)")
    if not violations_skill(SKILL.read_text(encoding="utf-8").replace(
            PHRASES_NU[0], PHRASES_NU[0] + " ; " + PHRASE_INTERDITE)):
        survivants.append(f"SKILL réaffirme « {PHRASE_INTERDITE} » (T7)")
    for p in NON_CLOS_EPINGLES:
        if not violations_skill(SKILL.read_text(encoding="utf-8").replace(p, "")):
            survivants.append(f"SKILL sans la puce NON CLOS « {p[:40]} » (T7)")
    for p in PHRASES_NU[1:] + PHRASES_BLINDAGE + (PHRASE_33,) + PHRASES_EUID:
        if not violations_skill(SKILL.read_text(encoding="utf-8").replace(p, "")):
            survivants.append(f"SKILL sans l'ancre « {p[:40]} » (T7)")
    # M20 — la tête de refus est LUE : table PURE jouée sur est_refus lui-même (l'ancien témoin était tué par
    # le `ls` de la jambe fausse, jamais par TETES_REFUS), et sept mutants de est_refus que la table doit tuer.
    survivants += [f"M20 est_refus : {x}" for x in violations_est_refus(est_refus)]
    for nom, fn in MUTANTS_EST_REFUS.items():
        if not violations_est_refus(fn):
            survivants.append(f"M20 {nom} survit à la table")
    if not violations_absence(lambda **kw: {k: replace(e, fatale=False) for k, e in decouvrir(**kw).items()}):
        survivants.append("M-absence (découverte qui saute sous CI et kit)")

    def avec(prefixe):
        return {k: c.replace(PREFIX, prefixe, 1) for k, c in j.items()}

    m12 = PREFIX.replace(" esac;", "")
    for cle, e in banc.enveloppes.items():
        if e.argv0 and not violations_sh_n(e.argv0, [avec(m12)["safe-bash"]]):
            survivants.append(f"M12 esac retiré ({cle}, sh -n)")
    racines = {"M7 cygpath||printf": AVANT + "unset " + " ".join(NOMS_RETIRES) + "; ",
               "M9 sans ?:*": faire_prefixe(case=CASE_RACINE.replace("?:*|", "")),
               "M10 sans *\\\\*": faire_prefixe(case=CASE_RACINE.replace("|*\\\\*", ""))}
    posix = {n: banc.enveloppes[n].argv0 for n in ENVELOPPES_POSIX if banc.enveloppes[n].argv0}
    posix0 = {n: banc.enveloppes[n].argv0 for n in ENVELOPPES_POSIX if banc.enveloppes[n].argv0}
    copies = {"M19 copie retirée": faire_prefixe(copie=""),
              "M19b pré-unset _CADRE retiré": faire_prefixe(copie=COPIE_GIT.replace("unset _CADRE_GIT_DIR _CADRE_GIT_WORK_TREE; ", "")),
              "M19c +x -> :+x (vide perdu)": faire_prefixe(copie=COPIE_GIT.replace("+x}", ":+x}")),
              "M19d +x -> :+x sur GIT_WORK_TREE seul": faire_prefixe(
                  copie=COPIE_GIT.replace("${GIT_WORK_TREE+x}", "${GIT_WORK_TREE:+x}"))}
    for nom, pre in copies.items():
        for env_nom, a0 in posix0.items():
            if not violations_copie(banc, a0, pre):
                survivants.append(f"{nom} ({env_nom})")
    F = FILTRE_LIT

    def filtre_sans(a, b=""):
        assert F.count(a) == 1, f"ancre du filtre : {F.count(a)} occurrence(s) de {a[:50]!r}"
        return F.replace(a, b, 1)

    filtres = {"F1 filtre absent (P et C passent tels quels : la forme (i))": faire_prefixe(filtre=""),
               "F2 noms retirés sans rendre le safe.directory (la forme d'avant T-801)":
                   faire_prefixe(NOMS_RETIRES + NOMS_FILTRES, filtre=""),
               "F3 unset des deux noms omis": faire_prefixe(filtre=filtre_sans("unset GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT; ")),
               "F4 GIT_CONFIG_COUNT ne déclenche pas le filtre": faire_prefixe(filtre=filtre_sans("${GIT_CONFIG_COUNT+x}")),
               "F5 toutes les portées rendues, pas seulement `command` (+ GIT_CONFIG_GLOBAL hérité : seul, équivalent depuis la rév. 9)":
                   faire_prefixe(filtre=filtre_sans("^command[[:blank:]]", "^[a-z]*[[:blank:]]").replace(
                       "GIT_CONFIG_GLOBAL=/dev/null ", '${GIT_CONFIG_GLOBAL+"GIT_CONFIG_GLOBAL=$GIT_CONFIG_GLOBAL"} ', 1)),
               "F6 apostrophe non échappée": faire_prefixe(filtre=filtre_sans(r"s/'/'\\\\''/g; ")),
               "F7 P reconstruit mais non exporté": faire_prefixe(filtre=filtre_sans("; export GIT_CONFIG_PARAMETERS")),
               "F8 --show-scope retiré": faire_prefixe(filtre=filtre_sans("--show-scope "))}
    for nom, pre in filtres.items():
        for env_nom, a0 in posix0.items():
            if not violations_config(banc, a0, pre, premier=True):
                survivants.append(f"{nom} ({env_nom})")

    def filtre_avec(*paires):
        g = F
        for a, b_ in paires:
            assert g.count(a) == 1, f"ancre du filtre : {g.count(a)} occurrence(s) de {a[:50]!r}"
            g = g.replace(a, b_, 1)
        return faire_prefixe(filtre=g)

    # Rév. 9 — F11 : `exec` retiré des trois étages (A-C1/B-C2). dash n'importe aucune fonction exportée : F11 y est ÉQUIVALENT
    # (écrit, mesuré `<A>/out/sonde9.out`). T-00001180 : /bin/sh n'est rejoué que s'il IMPORTE (sonde `importe_fonctions` ;
    # sous Linux c'est dash, mesuré) — sinon F11 y est imprimé, jamais compté survivant. bash-en-sh est TOUJOURS rejoué, et
    # une sonde qui l'y dirait muet est CONTREDITE (bash importe BASH_FUNC_* en mode sh : 3.2, 5.2.37, 5.3.15 mesurés).
    sans_exec = filtre_avec(("(exec env -i ", "(env -i "), ("| exec sed", "| sed"), ("| exec tr", "| tr"))
    for env_nom in ("sh", "bash-sh"):
        if not (a0 := posix0.get(env_nom)):
            continue
        if not (importe := importe_fonctions(banc, a0)) and env_nom == "bash-sh":
            survivants.append(f"sonde importe_fonctions contredite : bash-en-sh ({a0}) dit sans import de fonction")
        if not importe and env_nom != "bash-sh":
            perdus.append(f"F11 sous {env_nom} ({a0}) : aucune fonction exportée importée (sonde) — ÉQUIVALENT, non rejoué")
        elif not violations_config(banc, a0, sans_exec, premier=True):
            survivants.append(f"F11 exec retiré de env, sed et tr ({env_nom})")
    # T-00001180 — les sondes PS4 peuvent ROUGIR : leur verdict INVERSÉ doit faire rougir l'épingle qu'elles gouvernent
    # (inversée « ouvert » : rc de mort `tue` attendu, rc 2 observé ; inversée « fermé » : le rc de mort observé la contredit).
    cas_ps4 = []
    if d := posix0.get("dash"):
        cas_ps4.append(("dash / ancienne forme", d, enfant := bash_du_banc(banc), JAMBES_AVANT, None, rc_tue(banc, d, enfant)))
    if bs := posix0.get("bash-sh"):
        cas_ps4.append(("bash-en-sh", bs, bs, j, j["statusline"], -9))
    for nom, a0, interp, jambes, sl, tue in cas_ps4:
        if not violations_xtrace(banc, nom, a0, jambes, not ps4_importe_developpe(banc, interp), "sonde INVERSÉE", sl, tue):
            survivants.append(f"sonde PS4 inversée ({nom}) : l'épingle xtrace+PS4 ne rougit pas")
    # Rév. 9 — F12–F18 : ce que l'EXÉCUTION du filtre consomme (B-C1) ; chacun doit faire rougir `violations_lecture`.
    ecran = "[0-8]:*[Ii][Nn][Cc][Ll][Uu][Dd][Ee]*) ;; "
    lectures = {"F12 écran include retiré": filtre_avec((ecran, "")),
                "F13 écran retiré ET stdin ouvert": filtre_avec((ecran, ""), (" </dev/null", "")),
                "F14 env sans -i (environnement hérité : GIT_CONFIG, GIT_TRACE*, HOME…)": filtre_avec(("(exec env -i ", "(exec env ")),
                "F15 GIT_CONFIG_GLOBAL hérité (=/dev/null retiré SEUL : ÉQUIVALENT sous env -i, HOME non transmis, mesuré)": filtre_avec(("GIT_CONFIG_GLOBAL=/dev/null ", '${GIT_CONFIG_GLOBAL+"GIT_CONFIG_GLOBAL=$GIT_CONFIG_GLOBAL"} ')),
                "F16 -C / retiré (config du dépôt lue)": filtre_avec((" -C / config", " config")),
                "F17 décompte non borné ET clé 8 transmise (chacun SEUL : ÉQUIVALENT, env -i s'arrête à 7)": filtre_avec(("[0-8]:*) _s=", "*) _s="), ('${GIT_CONFIG_VALUE_7+"GIT_CONFIG_VALUE_7=$GIT_CONFIG_VALUE_7"} ', '${GIT_CONFIG_VALUE_7+"GIT_CONFIG_VALUE_7=$GIT_CONFIG_VALUE_7"} ${GIT_CONFIG_KEY_8+"GIT_CONFIG_KEY_8=$GIT_CONFIG_KEY_8"} ${GIT_CONFIG_VALUE_8+"GIT_CONFIG_VALUE_8=$GIT_CONFIG_VALUE_8"} ')),
                "F18 config système héritée (NOSYSTEM=1 retiré SEUL : /etc/gitconfig réel lu, hors banc)": filtre_avec(("GIT_CONFIG_NOSYSTEM=1 ", '${GIT_CONFIG_NOSYSTEM+"GIT_CONFIG_NOSYSTEM=$GIT_CONFIG_NOSYSTEM"} ${GIT_CONFIG_SYSTEM+"GIT_CONFIG_SYSTEM=$GIT_CONFIG_SYSTEM"} '))}
    for nom, pre in lectures.items():
        for env_nom, a0 in posix0.items():
            if not violations_lecture(banc, a0, pre, premier=True):
                survivants.append(f"{nom} ({env_nom})")
    # Contrôle : `</dev/null` TIENT SEUL — l'écran retiré, aucun cas stdin n'est consommé (sinon F13 serait F12).
    for env_nom, a0 in posix0.items():
        if any("stdin consommé" in x for x in violations_lecture(banc, a0, lectures["F12 écran include retiré"])):
            survivants.append(f"contrôle F12 : sans l'écran, `</dev/null` ne garde plus stdin ({env_nom})")
    for nom, pre in racines.items():
        for env_nom, a0 in posix.items():
            if not violations_racine(banc, a0, pre):
                survivants.append(f"{nom} ({env_nom})")
    sans_p = {k: c.replace("exec bash -p", "exec bash", 1) for k, c in j.items()}
    for env_nom, a0 in posix.items():
        if not violations_gardes(banc, a0, sans_p, ["onecmd", "BASH_FUNC_exit"], premier=True):
            survivants.append(f"M2 sans -p ({env_nom})")
    if bsh := banc.enveloppes["bash-sh"].argv0:
        for nom, extra in (("M1a SHELLOPTS dans l'unset", "SHELLOPTS"), ("M1b BASHOPTS dans l'unset", "BASHOPTS")):
            mut = avec(faire_prefixe(NOMS_RETIRES + (extra,)))
            if not violations_gardes(banc, bsh, mut, ["aucun"], premier=True):
                survivants.append(f"{nom} (bash-en-sh)")
        sans_exec = {k: c.replace("exec bash -p", "bash -p", 1) for k, c in j.items()}
        if not violations_gardes(banc, bsh, sans_exec, ["BASH_FUNC_bash"], premier=True):
            survivants.append("M3 sans exec (bash-en-sh, BASH_FUNC_bash)")
        if not violations_gardes(banc, bsh, j, ["aucun"], premier=True, apres={"LC_ALL": "zz_ZZ.UTF-8"}):
            survivants.append("M-locale (LC_ALL=C non forcé, zz_ZZ hérité)")
        if violations_capteur(banc, bsh, JAMBES_AVANT["statusline"], ["b-DEBUG"]) == []:
            survivants.append("M13 statusLine d'avant (T2b)")
    else:
        perdus.append("M1a, M1b, M3, M-locale, M13/T2b : bash-en-sh absent")
    if perdus:
        warnings.warn("mutants non joués — " + "; ".join(perdus))
    assert not survivants, "mutants survivants :\n" + "\n".join(survivants)


def test_xtrace_judge_table():
    """T-00001180, A-3 (S-00004134) : le juge xtrace+PS4 tenu SANS banc, branche par branche. Avant, aucun mutant ne faisait
    rougir la branche 3 (fermé, rc anormaux). Sur macOS la sonde dit « ouvert » partout (mesuré : aucun avertissement de
    fermeture), donc les branches 2 et 3 n'y étaient jamais jouées."""
    v = violations_juge_xtrace()
    v += [f"{nom} survit à la table" for nom, garde in MUTANTS_JUGE_XTRACE.items() if not violations_juge_xtrace(garde)]
    assert not v, "\n".join(v)


def test_dropping_config_names_loses_safe_directory(banc):
    """M11 (à part, B-C5) : retirer GIT_CONFIG_PARAMETERS / GIT_CONFIG_COUNT SANS en rendre le safe.directory (la forme de HEAD
    avant T-801) refait perdre le safe.directory légitime — `echo x > AGENTS.md` repasse, SANS l'aiguille « (git-tracked, »."""
    a0 = exiger(banc.enveloppes["sh"])
    exiger_bouton(temoin_etranger(banc, a0), "M11")
    mut = {k: c.replace(PREFIX, faire_prefixe(NOMS_RETIRES + NOMS_FILTRES, filtre=""), 1) for k, c in banc.jambes.items()}
    survivants = [vec for vec in VECTEURS_SAFE
                  if not violations_gardes(banc, a0, mut, [vec], premier=True, aiguille=AIGUILLE_REPOND)]
    assert not survivants, f"M11 survit : {survivants}"


# ---------------------------------------------------------------------------
# T7 — LA PROMESSE ÉCRITE
# ---------------------------------------------------------------------------
def test_skill_carries_prefix(reglages):
    chemin, doc = reglages
    prefixe_lu = doc.get("statusLine", {}).get("command", "")[:len(PREFIX)]
    v = violations_skill(SKILL.read_text(encoding="utf-8"), prefixe_lu)
    assert not v, f"réglages lus : {chemin}\n" + "\n".join(v)


# W-C (jambes Claude qui échouent fermées, test_wc1 à test_wc5) : déplacé dans
# `test_hook_closed_legs.py`, qui importe d'ici ses aides.



