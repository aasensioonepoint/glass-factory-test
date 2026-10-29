#!/usr/bin/env bash
# Discover and run every *.test.sh in the repo, aggregate the results.
#
# Companion to `run-pytest-shards.sh` (pytest's bare collection: the *.py suites). Together they
# are the whole test surface of this scaffolding repo. Designed for both the
# ubuntu-latest CI runner and a local Git-Bash dev box on Windows.
#
# Exit code: 0 iff every discovered suite exited 0. Serial path (CADRE_GATE_JOBS=1, one suite, --only):
# fail-fast is OFF on purpose, all suites run. Parallel path (T-00001122): fail-fast `prio` stops LAUNCHING
# after a red priority phase and says so (NOT RUN) ; a VERDICT red (never a hang) is replayed ALONE first.
#
# `--only <suite>` (T-00001044) : run ONE suite, and only if it is among the
# suites THIS runner discovers (`path/x.test.sh` or `./path/x.test.sh`) — same
# watchdog, same 127 sensor, same summary. Anything else is refused rc 2: the
# flag selects inside the discovered set, it never runs an arbitrary script.
# Why: a night dev checks ITS suite in headless, where the full run would blow
# the turn's timeout. Any other argument is refused rc 2 too (none existed).
set -euo pipefail

ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        echo "run-bash-tests: --only exige le chemin d'une suite découverte" >&2
        exit 2
      fi
      ONLY="$2"
      shift 2
      ;;
    *)
      echo "run-bash-tests: argument inconnu « $1 » — attendu : aucun, ou --only <suite>" >&2
      exit 2
      ;;
  esac
done

# Repo root = parent of this script's directory, resolved so it works from any cwd.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"
# Table de durees (T-01M4WTYT8M) : lue ici dans une variable NON exportee, puis RETIREE de l'environnement AVANT
# tout fils (git check-ignore, sonde 127, suites, enfants --only, export de CADRE_STATE_DIR plus bas) : aucun banc
# imbrique n'ecrit la table vivante. Servie au seul mode parallele (ordre), jamais au verdict.
RBT_DUR_DIR="${CADRE_GATE_DURATIONS_DIR:-$ROOT/.agents/state/local/porte-durees}"
unset CADRE_GATE_DURATIONS_DIR
# CADRE_GATE_ROUGES_OUT (T-01M5QBFKM444FB53RM2J1NBB4X) — canal de SORTIE vers verify.sh, meme patron : lu ici, RETIRE
# avant tout fils (les enfants `--only` du mode parallele ne l'heritent pas). Y sont ecrites, une par ligne, les suites
# JOUEES dont le verdict FINAL est rouge (fail, pendue, dependance manquante ; une rouge-puis-verte au rejeu seul et une
# NOT RUN n'y sont jamais) ; rien sur un vert ; tmp + mv ; un echec d'ecriture ne change jamais le rc.
RBT_ROUGES_OUT="${CADRE_GATE_ROUGES_OUT:-}"
unset CADRE_GATE_ROUGES_OUT
# CADRE_GATE_JOBS_BASH (T-01M60XKFK7MPKZWNHH326ZMW3M) — jobs de la JAMBE bash, poses par verify.sh quand ses deux
# jambes tournent ensemble ; meme patron : lue ici, RETIREE avant tout fils (aucune suite, aucun enfant `--only`, aucun
# banc imbrique ne l'herite). Non vide, elle PRIME sur CADRE_GATE_JOBS ; validee plus bas comme elle (entier <= 64,
# sinon rc 2, `auto` compris) ; vide = absente.
RBT_JOBS_BASH="${CADRE_GATE_JOBS_BASH:-}"
unset CADRE_GATE_JOBS_BASH
_rbt_rouges_ecrire() {  # _rbt_rouges_ecrire <suite>... : jamais un rc non nul (set -e)
  local _tmp
  [ -n "$RBT_ROUGES_OUT" ] || return 0
  [ "$#" -gt 0 ] || return 0
  _tmp="$RBT_ROUGES_OUT.tmp.$$"
  if printf '%s\n' "$@" > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$RBT_ROUGES_OUT" 2>/dev/null; then
    return 0
  fi
  rm -f "$_tmp" 2>/dev/null || true
  return 0
}

# A NESTED CHECKOUT IS A DIFFERENT TREE, AND ITS SUITES ARE NOT OURS (T-00000198).
#
# `verify.sh` already knew this hazard and solved it for its own frozen clone by
# placing it OUTSIDE the repo ("a nested copy would double every suite",
# verify.sh:93) — but nothing stopped a checkout appearing INSIDE. Measured on
# this repo: a stray `.worktrees/t175-board-v3-verify/` left over from 7 Aug, not
# even registered in `git worktree list`, carried a week-old copy of every suite.
# `find` swept all 16 of them back in — 32 suites discovered where 16 exist — and
# one stale copy failed against its own root, producing
# `VERIFY FAILED — do not push` while the tree under test was entirely green.
#
# That is a FALSE RED, the mirror of the false green this repo hunts everywhere,
# and it is worse than noise: `verify.sh` promises to run CI's SCOPE (its bare form
# under CADRE_GATE_JOBS=1), while CI starts from a clean checkout and will never see
# such a directory.
#
# The discriminator is ownership, not a name: a nested checkout — stray worktree,
# manual clone, vendored copy — carries its OWN `.git`, so anything beneath one
# belongs to another tree. Excluding `.worktrees/` by name would fix this one
# case and leave the class open.
#
# node_modules IS PRUNED AT EVERY DEPTH, NOT ONLY AT THE ROOT (T-00000264).
# The ownership rule above cannot cover it: an npm package carries no `.git`, so a
# `*.test.sh` shipped inside some dependency under `.agents/ui-src/node_modules/`
# would be swept into discovery and run against this tree. The interface gate's
# own `npm ci` (T-00000193/264) creates exactly such a tree, which is why pruning
# only `./node_modules` at the root was a latent false red. `-name node_modules
# -type d -prune` prunes any directory of that name wherever it sits.
NESTED=(); while IFS= read -r _line; do NESTED+=("$_line"); done < <(
  find . \
    -path ./.git -prune -o \
    -name node_modules -type d -prune -o \
    -name .git -print 2>/dev/null | sed 's|/\.git$||' | LC_ALL=C sort -u
)

# Collect suites deterministically (sorted), skipping VCS/vendor dirs.
FOUND=(); while IFS= read -r _line; do FOUND+=("$_line"); done < <(
  find . \
    -path ./.git -prune -o \
    -name node_modules -type d -prune -o \
    -name '*.test.sh' -type f -print | LC_ALL=C sort
)

SUITES=()
FOREIGN=()
# ${arr[@]+…} : bash 3.2 + `set -u` traite l'expansion d'un tableau VIDE comme
# « unbound variable » (corrigé en 4.4) ; un checkout CI propre n'a AUCUN
# checkout imbriqué, NESTED y est légitimement vide — garde 3.2-sûre des deux
# tableaux de découverte (mesuré sur macos-latest : mort ligne 62 avant toute suite).
for candidate in ${FOUND[@]+"${FOUND[@]}"}; do
  owned=1
  for nest in ${NESTED[@]+"${NESTED[@]}"}; do
    case "$candidate" in
      "$nest"/*) owned=0; break ;;
    esac
  done
  if [ "$owned" -eq 1 ]; then SUITES+=("$candidate"); else FOREIGN+=("$candidate"); fi
done

# T-00001188 : LA PORTE REFUSE UNE SUITE NON SUIVIE SOUS UN CHEMIN GIT-IGNORÉ.
# `find` découvre aussi ce que git ne montre pas : un `evil.test.sh` posé sous
# `.agents/state/local/` (ignoré) était JOUÉ par la porte sans qu'aucun diff ni
# `git status` ne le montre. Décision pilote (S-01M4N7Q58FJ1SJ9W6TKYY446Y2) : aucun
# intérêt légitime à une suite non suivie sous un dossier ignoré — refus rc 2,
# nommé, AVANT `--only` (qui ne peut donc pas l'élire), et AUCUNE suite lancée.
# `check-ignore` SANS `--no-index` : une suite SUIVIE (`git add -f`) sous un
# dossier ignoré n'est pas rapportée et reste jouée. Environnement git hérité
# purgé (mêmes 10 noms que conftest.py::GIT_REDIRECTIONS) : un `GIT_DIR` hostile
# ne fait pas lire l'index d'un autre dépôt. rc 0 = au moins une ignorée → refus ;
# rc 1 = aucune → suite normale ; tout autre rc → refus fail-closed nommé.
# Arbre sans `.git` : garde INACTIVE, ANNONCÉE (jamais muette). `.git` présent et
# git absent du PATH : REFUS rc 2 fail-closed (avis sécu A1 de T-00001188). Les
# noms refusés s'écrivent QUOTÉS (`printf %q`, avis A3) : un caractère de contrôle
# d'un nom de fichier n'atteint jamais le terminal brut. Zéro suite propre (toutes
# FOREIGN) : rien à juger, git non appelé.
# BORNES : un `.sh` ignoré SOURCÉ ou exécuté par une suite SUIVIE n'est pas vu
# (k) ; `check-ignore` n'a pas de délai propre ; les suites sous un checkout
# imbriqué restent FOREIGN, jamais lancées (inchangé). Banc :
# .agents/evals/test_runner_ignored_exec_1188.py (B1-B6, V6, V10).
_g1188=""
if [ "${#SUITES[@]}" -gt 0 ]; then
  if [ ! -e "$ROOT/.git" ]; then
    _g1188="pas de .git"
  elif ! command -v git >/dev/null 2>&1; then
    echo "T-00001188 : porte REFUSÉE — \`.git\` présent mais git absent du PATH : la garde ne peut pas lister les suites ignorées (fail-closed) ; remède : installer git ou le mettre au PATH" >&2
    exit 2
  else
    _rc1188=0
    _ign1188=$(
      unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
        GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
        GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
      printf '%s\0' ${SUITES[@]+"${SUITES[@]}"} \
        | git -c core.fsmonitor=false -c core.untrackedCache=false -c core.hooksPath=/dev/null check-ignore -z --stdin \
        | tr '\0' '\n'
      exit "${PIPESTATUS[1]}"
    ) || _rc1188=$?
    if [ "$_rc1188" -eq 0 ]; then
      echo "T-00001188 : porte REFUSÉE — suite(s) non suivie(s) sous un chemin git-ignoré :" >&2
      printf '%s\n' "$_ign1188" | while IFS= read -r _l; do printf '  - %q\n' "$_l" >&2; done
      echo "  remède : supprimer le fichier ou le sortir de l'arbre (une suite qui doit vivre là se SUIT)" >&2
      exit 2
    elif [ "$_rc1188" -ne 1 ]; then
      echo "T-00001188 : porte REFUSÉE — git check-ignore rc=$_rc1188 (fail-closed) ; remèdes : safe.directory, ou \`.git\` fichier de worktree pointant hors du conteneur" >&2
      exit 2
    fi
  fi
  if [ -n "$_g1188" ]; then echo "T-00001188 : garde suites ignorées INACTIVE ($_g1188)" >&2; fi
fi

# `--only` selects INSIDE the discovered set, compared as `./<path>` — the form
# `find .` yields. Not discovered (typo, foreign checkout, arbitrary script) → rc 2.
if [ -n "$ONLY" ]; then
  _want="./${ONLY#./}"
  _hit=""
  for s in ${SUITES[@]+"${SUITES[@]}"}; do
    if [ "$s" = "$_want" ]; then _hit="$s"; break; fi
  done
  if [ -z "$_hit" ]; then
    echo "run-bash-tests: --only « $ONLY » n'est pas une suite découverte de cet arbre — refusé (aucun script arbitraire)" >&2
    exit 2
  fi
  SUITES=("$_hit")
  FOREIGN=()
  echo "Only: $_hit (--only)"
fi

if [ "${#SUITES[@]}" -eq 0 ]; then
  # ZÉRO SUITE N'EST PLUS UN ÉCHEC — DÉCISION PILOTE DU 2026-09-14, ET ELLE A UN
  # MOTIF MESURÉ. Ce script est classé CONTRAT, donc il VOYAGE ; `pytest.ini`
  # aussi, et il épingle `testpaths` sur les répertoires du KIT. Chez un adoptant
  # qui n'a écrit aucune suite, la découverte rend zéro et cet `exit 1` l'accueillait
  # par un échec qu'il n'a pas causé — un défaut de l'outil.
  #
  # C'EST UNE PRÉVENTION, PAS UNE MESURE, et la nuance vient du binôme : elle
  # portait « faisait rougir », au passé mesuré. FAUX aujourd'hui — 43 des 44
  # suites `*.test.sh` VOYAGENT, donc sur le canal template la découverte n'est
  # JAMAIS vide. Le cas zéro n'existe que sur le canal `wheel + cadre init`, qui
  # n'existe pas encore (`cadre init` n'est qu'un nom réservé). On ferme un
  # défaut avant qu'il morde ; on ne prétend pas l'avoir vu mordre.
  #
  # CE QUI NE CHANGE PAS, ET C'EST LA MOITIÉ QUI COMPTE : la rédaction d'avant
  # portait « an empty perimeter passing silently is the emptiest false green
  # there is », et elle avait raison. L'objection visait le SILENCE, pas le code
  # retour. La sortie est donc bruyante, sur stderr, et nomme ce qui n'est PAS
  # prouvé — jamais un `exit 0` muet. C'est la forme « COVERAGE DEGRADED » que ce
  # dépôt emploie déjà partout où une couverture manque sans que rien soit cassé.
  #
  # ET LE VRAI FILET EST AILLEURS, PARCE QU'IL NE DOIT PAS VOYAGER : si le KIT
  # lui-même perdait ses suites, ce chemin rendrait vert un dépôt cassé. C'est
  # `.agents/evals/test_bash_suites_discovery.py` qui l'interdit — il exige que
  # CE dépôt en découvre plusieurs, et il se saute hors du kit. La garde est donc
  # passée du script, qui voyage, au banc, qui ne voyage pas : c'est là qu'elle
  # dit la vérité pour les deux arbres au lieu d'un seul.
  # DEUX CAS SE CACHAIENT DERRIÈRE UN SEUL MESSAGE, et le binôme l'a mesuré :
  # un arbre qui ne porte AUCUNE suite, et un arbre qui en porte plusieurs mais
  # dont TOUTES sont écartées comme étrangères (checkout imbriqué). Le second
  # recevait « un projet sans suite bash est légitime » — faux, et il masquait
  # exactement le défaut que la prune de T-00000193/264 existe pour rendre
  # visible. Le bloc « Skipped … nested checkout » vit PLUS BAS, donc après ce
  # retour anticipé : il ne pouvait pas les distinguer.
  if [ "${#FOREIGN[@]}" -ne 0 ]; then
    echo "COVERAGE DEGRADED: ${#FOREIGN[@]} suite(s) TROUVÉE(S) sur le disque et TOUTES écartées comme étrangères (checkout imbriqué) — ce n'est PAS un arbre sans suite bash." >&2
    for s in "${FOREIGN[@]}"; do echo "    - $s" >&2; done
    echo "  checkout(s) imbriqué(s) : ${NESTED[*]}" >&2
    echo "  Si ces suites sont les tiennes, c'est la PRUNE qui se trompe d'arbre, pas toi." >&2
    exit 0
  fi
  echo "COVERAGE DEGRADED: aucune suite *.test.sh découverte sous $ROOT — la jambe bash ne prouve RIEN sur cet arbre." >&2
  echo "  Ce n'est pas un échec : un projet sans suite bash est légitime. Mais la couverture bash de cette porte est NULLE," >&2
  echo "  et aucun vert obtenu ici ne dit quoi que ce soit sur du shell. Écris une suite \`*.test.sh\` pour qu'elle compte." >&2
  exit 0
fi

echo "Discovered ${#SUITES[@]} bash test suite(s):"
for s in "${SUITES[@]}"; do echo "  - $s"; done
# A bound applied is a bound ANNOUNCED — a silent skip reads as full coverage.
if [ "${#FOREIGN[@]}" -ne 0 ]; then
  echo
  echo "Skipped ${#FOREIGN[@]} suite(s) belonging to a nested checkout (not this tree):"
  for s in "${FOREIGN[@]}"; do echo "  - $s"; done
  echo "  nested checkout(s): ${NESTED[*]}"
fi
echo

# A GATE THAT NEVER RETURNS A VERDICT IS WORSE THAN A RED ONE (T-00000160).
#
# Measured twice in one night, at DIFFERENT steps (semgrep on one project,
# events-wiring PART 2+3 here): the aggregation produced no output for 74
# minutes with its processes still alive. That is not slowness — something was
# WAITING, and a gate that hangs teaches everyone to stop trusting it, then to
# stop running it. So every suite runs under a watchdog that kills it and NAMES
# it, and the run always ends with a verdict.
#
# `timeout` was MEASURED on this repo's Git Bash box before being relied on: it
# puts the child in its own process group and signals the GROUP, so a suite that
# spawned background grandchildren leaves none behind (probe: grandchild
# `sleep 31337` backgrounded by a hung suite, 0 survivors after the kill). That
# matters because AGENTS.md's own lesson is that stopping a task stops the
# process it LAUNCHED, not the tree below it — `--foreground` would reintroduce
# exactly that hole, which is why it is not used here.
SUITE_TIMEOUT="${BASH_TEST_TIMEOUT:-900}"
KILL_GRACE="${BASH_TEST_KILL_GRACE:-15}"
# Named rather than hardcoded for ONE reason: it is what makes the degraded path
# below testable. Hiding `timeout` from a fixture would mean stripping PATH down
# to nothing, which breaks `find`/`sed` too and proves only that the runner needs
# a PATH. A degradation nobody can exercise is a degradation nobody has checked.
TIMEOUT_BIN="${BASH_TEST_TIMEOUT_BIN:-timeout}"

if command -v "$TIMEOUT_BIN" >/dev/null 2>&1; then
  WATCHDOG=1
  echo "Watchdog: ${SUITE_TIMEOUT}s per suite (SIGKILL ${KILL_GRACE}s later)."
else
  # Never silently. A watchdog that vanishes without a word is indistinguishable
  # from one that never fired — the same failure mode this whole file is about.
  WATCHDOG=0
  echo "COVERAGE DEGRADED: '$TIMEOUT_BIN' is absent — suites run WITHOUT a watchdog," >&2
  echo "  so a hung suite will hang this run exactly as before T-00000160." >&2
fi

# A SUITE CAN EXIT 0 WITHOUT HAVING PROVEN ANYTHING, AND THIS RUNNER JUDGED ONLY
# THE rc (T-00000427).
#
# TWO DISTINCT BLINDNESSES, CLOSED BY TWO DIFFERENT MECHANISMS. Conflating them
# was the defect of the first attempt at this fix, so they are kept apart here.
#
# (K1) THE SWALLOWED 127 — a command that does not exist, actually EXECUTED by a
# suite running `set -u` without `-e`: bash writes "command not found" on stderr,
# the 127 is absorbed by the next `|| true` (or simply never tested), and the
# suite exits 0. MEASURED on this repo: a fixture whose ONLY command was absent
# produced `--- PASS ./mine.test.sh (0s)`, `1 passed / 0 failed`,
# `All bash suites passed.` and rc=0. `command_not_found_handle` is the only hook
# bash offers to observe a lookup failure from OUTSIDE the suite, so the sensor
# below is exported into every suite.
#
# (K2) THE AUTO-SKIP — `command -v <tool> || { echo SKIP; exit 0; }`. MEASURED:
# `command -v` is a BUILTIN, so it NEVER reaches `command_not_found_handle` — the
# K1 sensor is STRUCTURALLY blind to it, and no amount of tuning would fix that.
# 16 of this repo's 33 suites print a SKIP. It is closed instead by READING the
# captured output: a suite that exits 0 after announcing a SKIP stops being a
# bare PASS. That is plain text, so it still works on the bash 3.2 where the K1
# sensor degrades — which is precisely why the two are not one mechanism.
#
# `tee` is checked HERE rather than met mid-run, and the reason is specific: the
# capture below pipes into it, so an absent `tee` would fire the K1 sensor inside
# the RUNNER'S OWN subshell and stamp `MISSING DEP (cmd: tee)` on all 33 suites —
# a false red with no escape hatch, the exact hazard `# allows-missing:` exists to
# prevent. One named refusal beats 33 misattributed ones.
if ! command -v tee >/dev/null 2>&1; then
  echo "'tee' is absent — this runner captures each suite's output in order to" >&2
  echo "  judge it (T-00000427). Without it no verdict here can be trusted, so it" >&2
  echo "  refuses to run rather than return one." >&2
  exit 1
fi

# ASSIGNED UNCONDITIONALLY, NEVER INHERITED — and that is not a style preference.
# `run-bash-tests.test.sh` launches NESTED copies of this runner. Under a
# `${RBT_MISSING_LOG:-…}` the child would append to its PARENT's log, the parent
# would then attribute the child fixture's deliberate failure to
# `run-bash-tests.test.sh` itself, and the OUTER run would go red over a suite
# that passed. That is the false red this file has banned since :29-31.
RBT_MISSING_LOG="$(mktemp)"
RBT_OUT="$(mktemp)"
export RBT_MISSING_LOG

# T-00000650, BLOQUANT 3 (binôme de clôture) — ISOLATION DE L'ÉTAT MACHINE POUR LES
# BANCS SHELL, l'analogue de la fixture de session de `conftest.py` pour les *.py.
# Depuis la bascule « état machine hors dépôt », un banc `*.test.sh` qui appelle
# `tasks.py` (donc `replay_sync` -> `BoardBridge` -> `EventStore`) crée une
# partition SOUS la VRAIE `state_home()` de la machine, et rien ne la nettoie.
# MESURÉ : la suite bash complète, jouée sous une `state_home()` jetable, y crée 5
# partitions. On pose `CADRE_STATE_DIR` vers un temp DÉDIÉ quand l'appelant ne l'a
# PAS déjà posé, et on le nettoie à la sortie ; une valeur déjà posée est RESPECTÉE
# (le runner nesté de `run-bash-tests.test.sh` hérite ainsi de la partition du père
# et n'en crée pas une seconde). Emplacement CHOISI : ce runner plutôt que la porte
# `verify.sh` proposée — il couvre AUSSI un `bash run-bash-tests.sh` autonome et
# l'adoptant, sans toucher au script de la porte.
RBT_STATE_DIR=""
if [ -z "${CADRE_STATE_DIR:-}" ]; then
  RBT_STATE_DIR="$(mktemp -d)"
  export CADRE_STATE_DIR="$RBT_STATE_DIR"
fi
trap 'rm -f "$RBT_MISSING_LOG" "$RBT_OUT"; rm -rf "$RBT_STATE_DIR" 2>/dev/null || true' EXIT

# The stderr line is REPRODUCED, not dropped: defining this handler SUPPRESSES
# bash's own "command not found" message, and a sensor that silences the very
# diagnostic it reports on would trade one blindness for another. The log path is
# read defensively — a suite free to `unset` it must not make the handler itself
# die under `set -u`. That is a READ guard, not the inheritance banned above.
command_not_found_handle() {
  printf '%s\n' "${1:-?}" >>"${RBT_MISSING_LOG:-/dev/null}"
  printf 'bash: %s: command not found\n' "${1:-?}" >&2
  return 127
}
export -f command_not_found_handle

# MEASURED BEFORE BEING RELIED ON, exactly as `timeout` was above.
# `command_not_found_handle` arrived in bash 4.0 and macOS ships /bin/bash 3.2.57
# (measured: rc 127, empty log). The probe goes through the SAME `bash` that will
# run the suites, so it measures the interpreter that actually matters rather
# than the one interpreting this line.
: >"$RBT_MISSING_LOG"
bash -c 'rbt-probe-absent-cmd-t427' >/dev/null 2>&1 || true
if [ -s "$RBT_MISSING_LOG" ]; then
  MISSING_DETECT=1
else
  MISSING_DETECT=0
  echo "COVERAGE DEGRADED: swallowed-127 detection unavailable" >&2
  echo "  (this bash has no command_not_found_handle — pre-4.0, e.g. macOS /bin/bash 3.2)," >&2
  echo "  so a suite that RUNS an absent command can still exit 0 unseen." >&2
  echo "  The SKIP survey stays ACTIVE: it reads captured text and needs no sensor." >&2
fi
: >"$RBT_MISSING_LOG"
echo

# Header directives, read from a suite's first 20 lines:
#   # requires: <cmd> …        absent -> MISSING DEP, suite NOT run, run is RED
#   # optional: <cmd> …        absent -> announced and counted, run stays GREEN
#   # allows-missing: <cmd> …  this suite may legitimately EXECUTE that absent
#                              command (PATH-stripped probes); the sensor does
#                              not blame it for one.
#
# Writing a `# allows-missing:` list for a PATH-stripped probe: ONE criterion
# decides which commands go in a stub link versus this declaration. A command
# a DECISION of the script under test depends on (a measurement) must be
# LINKED in the stub, so the probe still exercises the real branch; a command
# with only an EFFECT nothing branches on (telemetry, cleanup) is DECLARED
# here instead. Declaring a measurement would make the probe blind in
# silence — see `.agents/security/semgrep-scan.test.sh` (`wc`, linked, feeds
# a guard predicate) versus `bash`/`rm` (declared, pure effects) for the
# worked example.
suite_directive() {
  sed -n '1,20p' "$1" 2>/dev/null \
    | sed -n "s/^[[:space:]]*#[[:space:]]*$2:[[:space:]]*//p" \
    | tr '\n' ' '
}

# =============================================================================================
# MODE PARALLELE (T-00001122), insere APRES `suite_directive()` (donc APRES le chien de garde, le
# capteur 127, `tee`, la partition d'etat et le `trap` de sortie du pere : l'en-tete du pere EST
# l'en-tete serie) et AVANT `passed=0`. Chaque suite tourne comme un enfant `run-bash-tests.sh
# --only <suite>` : MEME watchdog, MEME capteur 127, MEME releve de SKIP — le jugement d'une suite
# n'est pas recopie. Le pere ordonne, borne, relit le resume de CHAQUE enfant, REJOUE seules les
# suites rouges de VERDICT (`fail` ; jamais une pendue ni une dependance manquante), plafonne, et
# rend le MEME bloc de resume que le chemin serie, octet pour octet (listes en ordre de decouverte).
# Actif seulement si --only est absent ET jobs > 1 ET >= 2 suites ; sinon le chemin serie est INTACT.
# Reglages (les memes que run-pytest-shards.sh) : CADRE_GATE_JOBS (auto|N ; 1 = serie ; auto vaut 1
# sous Git Bash, NON mesure ; CADRE_GATE_JOBS_BASH=N, posee par verify.sh, prime), CADRE_GATE_BASE (HEAD~1), CADRE_GATE_FAIL_FAST (prio|all|0),
# CADRE_GATE_REPLAY (3 : rouges rejoues seuls, plafond sur tout le run ; 0 = jamais).
# CADRE_GATE_DURATIONS_DIR (T-01M4WTYT8M ; defaut $ROOT/.agents/state/local/porte-durees) : table `bash.tsv`
# (`# v1`, puis `suite<TAB>secondes`) qui pondere l'ORDRE de la file, jamais le verdict ; sans table, l'ordre
# par octets d'avant, a l'identique. Ecrite apres le run : suites jouees ET vertes en passe 1, fusion, rien
# n'est efface. Prioritaires en plus : les morceaux de safe-bash (`.claude/hooks/safe-bash-*.test.sh`) quand
# `.claude/hooks/safe-bash.sh` change — liste FERMEE, jamais un prefixe general (la phase prio est une barriere).
if [ -z "$ONLY" ]; then
  RBT_JOBS="${CADRE_GATE_JOBS:-auto}"
  RBT_JOBS_VAR="CADRE_GATE_JOBS"
  if [ -n "$RBT_JOBS_BASH" ]; then
    RBT_JOBS="$RBT_JOBS_BASH"
    RBT_JOBS_VAR="CADRE_GATE_JOBS_BASH"
    if [ "$RBT_JOBS" = "auto" ]; then
      echo "run-bash-tests: CADRE_GATE_JOBS_BASH=« auto » refuse — attendu un entier (au plus 64)" >&2
      exit 2
    fi
  fi
  RBT_FF="${CADRE_GATE_FAIL_FAST:-prio}"
  RBT_REPLAY="${CADRE_GATE_REPLAY:-3}"
  _rbt_uint() {
    case "$1" in
      ''|*[!0-9]*) return 1 ;;
    esac
    return 0
  }
  if [ "$RBT_JOBS" = "auto" ]; then
    RBT_JOBS=1
    case "$(uname -s 2>/dev/null || true)" in
      MINGW*|MSYS*|CYGWIN*) : ;;
      *)
        _n=""
        if command -v getconf >/dev/null 2>&1; then _n="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"; fi
        if ! _rbt_uint "$_n" && command -v nproc >/dev/null 2>&1; then _n="$(nproc 2>/dev/null || true)"; fi
        if ! _rbt_uint "$_n" && command -v sysctl >/dev/null 2>&1; then _n="$(sysctl -n hw.ncpu 2>/dev/null || true)"; fi
        if ! _rbt_uint "$_n"; then _n=1; fi
        RBT_JOBS=$(( _n / 2 ))
        if [ "$RBT_JOBS" -gt 8 ]; then RBT_JOBS=8; fi
        if [ "$RBT_JOBS" -lt 1 ]; then RBT_JOBS=1; fi
        ;;
    esac
  fi
  if ! _rbt_uint "$RBT_JOBS"; then
    echo "run-bash-tests: $RBT_JOBS_VAR=« $RBT_JOBS » n'est ni auto ni un entier" >&2
    exit 2
  fi
  # borne haute : 20 chiffres faisaient echouer `[ -gt 1 ]` et la porte repassait en SERIE sans le dire
  if [ "${#RBT_JOBS}" -gt 2 ] || [ "$RBT_JOBS" -gt 64 ]; then
    echo "run-bash-tests: $RBT_JOBS_VAR=« $RBT_JOBS » hors borne (au plus 64)" >&2
    exit 2
  fi
  case "$RBT_FF" in
    prio|all|0) : ;;
    *)
      echo "run-bash-tests: CADRE_GATE_FAIL_FAST=« $RBT_FF » attendu prio|all|0" >&2
      exit 2 ;;
  esac
  if ! _rbt_uint "$RBT_REPLAY"; then
    echo "run-bash-tests: CADRE_GATE_REPLAY=« $RBT_REPLAY » n'est pas un entier" >&2
    exit 2
  fi
fi
if [ -z "$ONLY" ] && [ "$RBT_JOBS" -gt 1 ] && [ "${#SUITES[@]}" -gt 1 ]; then
  _par="$(mktemp -d)"
  _par_cleanup() {
    local pf
    for pf in "$_par"/*.pid; do
      [ -f "$pf" ] || continue
      kill "$(cat "$pf")" 2>/dev/null || true
    done
    rm -rf "$_par"
    rm -f "$RBT_MISSING_LOG" "$RBT_OUT"
    rm -rf "$RBT_STATE_DIR" 2>/dev/null || true
  }
  _par_signal() {
    echo "run-bash-tests: INTERROMPU — aucun verdict vert possible" >&2
    _par_cleanup
    trap - EXIT
    exit "$1"
  }
  trap _par_cleanup EXIT
  trap '_par_signal 130' INT
  trap '_par_signal 143' TERM
  # --- ordre : suites LIEES aux changements BASE..HEAD d'abord (phase prioritaire), puis taille decroissante
  _base="${CADRE_GATE_BASE:-HEAD~1}"
  : > "$_par/changed"
  if git rev-parse -q --verify "$_base^{commit}" >/dev/null 2>&1; then
    git diff --name-only "$_base" HEAD > "$_par/changed" 2>/dev/null || : > "$_par/changed"
  fi
  : > "$_par/prio"
  : > "$_par/rest.b"
  _idx=0
  for s in "${SUITES[@]}"; do
    _rel="${s#./}"
    _stem="${_rel%.test.sh}"
    # C7 (T-01M4WTYT8M) : un morceau de safe-bash est prioritaire quand safe-bash.sh change — liste FERMEE
    _fam=""
    case "$_rel" in
      .claude/hooks/safe-bash-*.test.sh) _fam=".claude/hooks/safe-bash.sh" ;;
    esac
    if awk -v a="$_rel" -v b="$_stem.sh" -v c="$_stem.py" -v d="$_stem" -v e="$_fam" \
         '$0 == a || $0 == b || $0 == c || $0 == d || (e != "" && $0 == e) {f = 1} END {exit !f}' "$_par/changed"; then
      echo "$_idx" >> "$_par/prio"
    else
      printf '%s\t%s\t%s\n' "$(wc -c < "$s" | tr -d ' ')" "$_idx" "$s" >> "$_par/rest.b"
    fi
    _idx=$((_idx + 1))
  done
  # poids de la file (T-01M4WTYT8M) : suite connue -> ses secondes (en ms) ; inconnue -> octets x somme(s)/somme(octets)
  # des connues ; aucune connue -> les OCTETS, l'ordre d'avant a l'identique. Lue seulement si fichier ordinaire lisible.
  _dur_tsv="$RBT_DUR_DIR/bash.tsv"
  _dur_rd="$_dur_tsv"
  if [ ! -f "$_dur_tsv" ] || [ ! -r "$_dur_tsv" ]; then _dur_rd=/dev/null; fi
  awk -F '\t' -v TBL="$_dur_rd" -v WF="$_par/weights" '
    BEGIN {
      while ((getline l < TBL) > 0) {
        if (l ~ /^#/ || l == "") continue
        nt = split(l, t, "\t")
        if (nt == 2 && t[1] != "" && t[2] ~ /^[0-9]+(\.[0-9]+)?$/) ts[t[1]] = t[2] + 0
        else bad++
      }
    }
    { b[NR] = $1; ix[NR] = $2; s[NR] = $3; if ($3 in ts) { kn++; ss += ts[$3]; sb += $1 } }
    END {
      dur = (kn > 0 && sb > 0)
      for (i = 1; i <= NR; i++) {
        w = b[i]
        if (dur && (s[i] in ts)) w = int(ts[s[i]] * 1000)
        else if (dur) { w = int(b[i] * ss * 1000 / sb); unk++ }
        print w, ix[i]
      }
      print dur + 0, kn + 0, unk + 0, bad + 0 > WF
    }' "$_par/rest.b" > "$_par/rest.w"
  LC_ALL=C sort -k1,1nr -k2,2n "$_par/rest.w" | awk '{print $2}' > "$_par/rest"
  _nprio="$(awk 'END {print NR}' "$_par/prio")"
  if git rev-parse -q --verify "$_base^{commit}" >/dev/null 2>&1; then
    _basemsg="$_nprio suite(s) first (changed since $_base)"
  else
    _basemsg="base « $_base » unresolvable — no priority phase, every suite is played"
  fi
  read -r _wdur _wkn _wunk _wbad < "$_par/weights"
  if [ "$_wdur" -eq 1 ]; then
    _wmsg="weights=durations ($_wkn known in $_dur_tsv, $_wunk estimated from bytes)"
  else
    _wmsg="weights=bytes (no known duration in $_dur_tsv)"
  fi
  cat "$_par/prio" "$_par/rest" > "$_par/queue"
  _qhead=""
  _qn=0
  while IFS= read -r _i; do
    if [ "$_qn" -ge 3 ]; then break; fi
    if [ -n "$_qhead" ]; then _qhead="$_qhead, "; fi
    _qhead="$_qhead${SUITES[$_i]}"
    _qn=$((_qn + 1))
  done < "$_par/queue"
  # CADRE_GATE_JOBS_BASH refuses `auto` (above): its label shows the value read, never `auto|N`.
  if [ "$RBT_JOBS_VAR" = "CADRE_GATE_JOBS_BASH" ]; then _jlabel="CADRE_GATE_JOBS_BASH=$RBT_JOBS"; else _jlabel="CADRE_GATE_JOBS=auto|N"; fi
  echo "Parallel: $RBT_JOBS jobs ($_jlabel), fail-fast=$RBT_FF, replay<=$RBT_REPLAY — each suite runs as \`run-bash-tests.sh --only\`; $_basemsg; $_wmsg; queue head: $_qhead."
  if [ "$_wbad" -gt 0 ]; then
    echo "Parallel: $_wbad unreadable line(s) in $_dur_tsv — ignored, kept as they are"
  fi
  echo
  _p_t0="$(date +%s)"
  : > "$_par/durations"
  _ST=(); _DET=(); _SKP=(); _FIRST=()
  _done=0; _stop=0; _running=0; _nrep=0
  _footer_first() {  # _footer_first <regex d'en-tete> <sortie d'enfant> : 1re entree `  - ...` de la liste, lue APRES le dernier resume
    awk -v h="$1" '{ l[NR] = $0 } /^Bash test summary: / { s = NR }
         END { for (i = s + 1; i <= NR; i++) {
                 if (l[i] ~ h) { on = 1; continue }
                 if (on && l[i] ~ /^  - /) { sub(/^  - /, "", l[i]); print l[i]; exit }
                 if (on) on = 0
               } }' "$2"
  }
  _launch() {  # _launch <idx> <passe 1|2>
    local i="$1" pass="$2" d
    date +%s > "$_par/$i.t0"
    d="$CADRE_STATE_DIR/rbt-par-$i-$pass"
    mkdir -p "$d"
    CADRE_STATE_DIR="$d" bash "$HERE/run-bash-tests.sh" --only "${SUITES[$i]}" < /dev/null > "$_par/$i.out" 2>&1 &
    echo "$!" > "$_par/$i.pid"
    echo "$pass" > "$_par/$i.pass"
  }
  _judge() {  # _judge <idx> : rejoue le CORPS de l'enfant, relit SON resume et SES listes
    local i="$1" o="$_par/$1.out" s rc line p f h m k pass dt
    s="${SUITES[$i]}"; rc="$(cat "$_par/$i.rc")"; pass="$(cat "$_par/$i.pass")"
    dt=$(( $(cat "$_par/$i.t1") - $(cat "$_par/$i.t0") ))
    # le corps de l'enfant : de `=== RUN` a la DERNIERE ligne de verdict (+ la ligne vide) ; en-tete et pied
    # REPLIES (le pere a deja imprime les siens) ; un enfant SANS verdict est rejoue EN ENTIER
    awk '{ l[NR] = $0 }
         /^=== RUN  / { if (!r) r = NR }
         /^--- (PASS|FAIL|TIMEOUT|MISSING DEP) / { v = NR }
         END {
           if (!r || !v) { for (i = 1; i <= NR; i++) print l[i]; exit }
           e = v + 1; if (e > NR || l[e] != "") e = v
           for (i = r; i <= e; i++) print l[i]
         }' "$o"
    line="$(awk '/^Bash test summary: / {l = $0} END {print l}' "$o")"
    p="$(printf '%s' "$line" | sed -n 's/^Bash test summary: \([0-9][0-9]*\) passed.*/\1/p')"
    f="$(printf '%s' "$line" | sed -n 's/.* \([0-9][0-9]*\) failed.*/\1/p')"
    h="$(printf '%s' "$line" | sed -n 's/.* \([0-9][0-9]*\) timed out.*/\1/p')"
    m="$(printf '%s' "$line" | sed -n 's/.* \([0-9][0-9]*\) missing dep.*/\1/p')"
    k="$(printf '%s' "$line" | sed -n 's/.* \([0-9][0-9]*\) skipping.*/\1/p')"
    _DET[$i]=""; _SKP[$i]=""
    if [ -z "$p" ] || [ -z "$f" ] || [ -z "$h" ] || [ -z "$m" ]; then
      echo "--- FAIL $s (child left no summary, rc=$rc — interrupted or broken)"
      _ST[$i]="fail"; _DET[$i]=""
    elif [ "$p" -eq 1 ] && [ "$rc" -ne 0 ]; then
      # le dernier resume peut etre celui d'un runner IMBRIQUE imprime par la suite, l'enfant tue ensuite
      echo "--- FAIL $s (child summary says passed but child rc=$rc — summary not trusted)"
      _ST[$i]="fail"
    elif [ "$p" -eq 1 ]; then
      _ST[$i]="pass"
      if [ "${k:-0}" -ne 0 ]; then
        _SKP[$i]="$(_footer_first '^Announced a SKIP' "$o")"
      fi
    elif [ "$h" -eq 1 ]; then
      _ST[$i]="hung"
      _DET[$i]="$(_footer_first '^Timed out ' "$o")"
    elif [ "$m" -eq 1 ]; then
      _ST[$i]="missing"
      _DET[$i]="$(_footer_first '^Missing dependency' "$o")"
    else
      _ST[$i]="fail"
    fi
    if [ "$pass" -eq 1 ]; then
      _done=$((_done + 1))
      _FIRST[$i]="${_ST[$i]}"
      echo "$dt $s" >> "$_par/durations"
      echo "$dt" > "$_par/$i.dt1"   # duree de PASSE 1 (un rejeu reecrit .t0/.t1, jamais .dt1) : seule source de la table
    fi
  }
  _reap() {
    local pf j pid
    _running=0
    for pf in "$_par"/*.pid; do
      [ -f "$pf" ] || continue
      j="$(basename "$pf" .pid)"
      pid="$(cat "$pf")"
      if kill -0 "$pid" 2>/dev/null; then _running=$((_running + 1)); continue; fi
      set +e
      wait "$pid" 2>/dev/null
      echo "$?" > "$_par/$j.rc"
      set -e
      date +%s > "$_par/$j.t1"
      rm -f "$pf"
      _judge "$j"
    done
  }
  _any_red() {
    local i
    for i in ${_ST[@]+"${!_ST[@]}"}; do
      if [ "${_ST[$i]}" != "pass" ]; then return 0; fi
    done
    return 1
  }
  _run_list() {  # _run_list <fichier d'indices> <stop_si_rouge 0|1> ; une suite deja lancee n'est jamais relancee
    local i
    while IFS= read -r i; do
      if [ -z "$i" ] || [ -f "$_par/$i.pass" ]; then continue; fi
      while :; do
        _reap
        if [ "$2" -eq 1 ] && _any_red; then _stop=1; break 2; fi
        if [ "$_running" -lt "$RBT_JOBS" ]; then break; fi
        sleep 0.2
      done
      _launch "$i" 1
    done < "$1"
    while :; do _reap; if [ "$_running" -eq 0 ]; then break; fi; sleep 0.2; done
  }
  _settle() {  # rejoue SEULES les suites rouges de VERDICT (L-00000234) : jamais `hung`/`missing`, jamais deux fois
    local i n=0 list=""
    if [ "$RBT_REPLAY" -le 0 ]; then return 0; fi
    for i in ${_ST[@]+"${!_ST[@]}"}; do
      if [ "${_ST[$i]}" = "fail" ] && [ "$(cat "$_par/$i.pass")" = "1" ]; then list="$list $i"; n=$((n + 1)); fi
    done
    if [ "$n" -eq 0 ]; then return 0; fi
    if [ "$n" -gt $(( RBT_REPLAY - _nrep )) ]; then
      echo "Parallel: $n red suite(s) > CADRE_GATE_REPLAY=$RBT_REPLAY ($_nrep already replayed) — no replay (a red of that size is not a contention accident)"
      echo
      return 0
    fi
    for i in $list; do
      echo "Parallel: replaying ${SUITES[$i]} ALONE (red under the pool, $RBT_JOBS jobs) — same command, jobs=1"
      _nrep=$((_nrep + 1)); _launch "$i" 2
      while :; do _reap; if [ "$_running" -eq 0 ]; then break; fi; sleep 0.2; done
    done
  }
  _run_phase() {  # _run_phase <indices> : un rouge RATTRAPE par son rejeu seul ne laisse pas la file coupee
    while :; do
      _stop=0; _run_list "$1" "$_stop_red"; _settle
      if [ "$_stop" -eq 0 ] || _any_red; then return 0; fi
    done
  }
  _stop_red=0
  if [ "$RBT_FF" = "all" ]; then _stop_red=1; fi
  if [ "$_nprio" -gt 0 ]; then
    _run_phase "$_par/prio"
    if [ "$RBT_FF" != "0" ] && _any_red; then _stop=1; fi
  fi
  if [ "$_stop" -eq 0 ]; then _run_phase "$_par/rest"; fi
  _p_t1="$(date +%s)"
  # --- table de durees (T-01M4WTYT8M) : suites JOUEES et VERTES en passe 1 (jamais un rejeu) ; FUSION avec la table
  # existante (rien n'est efface ni elague, une ligne illisible est gardee telle quelle) ; tmp + mv dans le meme
  # dossier. Un echec d'ecriture est annonce, le rc ne change pas (set -e : chaque pas est garde). Hors
  # interruption : _par_signal sort avant d'arriver ici. Imprime AVANT le bloc de resume (identique au serie).
  : > "$_par/dur.new"
  : > "$_par/dur.bad"
  for _i in ${_FIRST[@]+"${!_FIRST[@]}"}; do
    if [ "${_FIRST[$_i]}" = "pass" ] && [ -f "$_par/$_i.dt1" ]; then
      printf '%s\t%s\n' "${SUITES[$_i]}" "$(cat "$_par/$_i.dt1")" >> "$_par/dur.new"
    fi
  done
  _dtmp="$RBT_DUR_DIR/.bash.tsv.$$"
  _dok=1
  if [ -e "$_dur_tsv" ] && [ "$_dur_rd" = /dev/null ]; then _dok=0; fi
  if [ "$_dok" -eq 1 ]; then mkdir -p "$RBT_DUR_DIR" 2>/dev/null || _dok=0; fi
  if [ "$_dok" -eq 1 ]; then
    { echo "# v1" \
      && awk -v NEW="$_par/dur.new" -v TBL="$_dur_rd" -v BAD="$_par/dur.bad" '
           BEGIN {
             while ((getline l < NEW) > 0) { split(l, t, "\t"); nw[t[1]] = l }
             while ((getline l < TBL) > 0) {
               if (l ~ /^#/ || l == "") continue
               nt = split(l, t, "\t")
               if (nt == 2 && t[1] != "" && t[2] ~ /^[0-9]+(\.[0-9]+)?$/) { if (!(t[1] in nw)) old[t[1]] = l }
               else print l > BAD
             }
             for (k in old) print old[k]
             for (k in nw) print nw[k]
           }' | LC_ALL=C sort \
      && cat "$_par/dur.bad"; } > "$_dtmp" 2>/dev/null || _dok=0
  fi
  if [ "$_dok" -eq 1 ]; then mv -f "$_dtmp" "$_dur_tsv" 2>/dev/null || _dok=0; fi
  if [ "$_dok" -eq 1 ]; then
    echo "Parallel: durations table $_dur_tsv updated ($(awk 'END {print NR}' "$_par/dur.new") suite(s) played and green in pass 1; order only, never the verdict)"
  else
    rm -f "$_dtmp" 2>/dev/null || true
    echo "Parallel: durations table NOT written ($_dur_tsv) — the next gate's order suffers, this verdict is unchanged"
  fi
  # --- totaux et listes, en ORDRE DE DECOUVERTE (le bloc de resume est celui du chemin serie)
  passed=0; failed=0; hung=0; missing=0; skipping=0
  FAILED_SUITES=(); HUNG_SUITES=(); MISSING_SUITES=(); SKIPPING_SUITES=(); _REPLAYED=(); _ROUGES=()
  _idx=0
  for s in "${SUITES[@]}"; do
    if [ -n "${_ST[$_idx]+x}" ]; then
      case "${_ST[$_idx]}" in
        pass)
          passed=$((passed + 1))
          if [ -n "${_SKP[$_idx]}" ]; then skipping=$((skipping + 1)); SKIPPING_SUITES+=("${_SKP[$_idx]}"); fi
          if [ "${_FIRST[$_idx]}" != "pass" ]; then _REPLAYED+=("$s"); fi ;;
        hung) hung=$((hung + 1)); HUNG_SUITES+=("${_DET[$_idx]:-$s}"); _ROUGES+=("$s") ;;
        missing) missing=$((missing + 1)); MISSING_SUITES+=("${_DET[$_idx]:-$s}"); _ROUGES+=("$s") ;;
        *) failed=$((failed + 1)); FAILED_SUITES+=("$s"); _ROUGES+=("$s") ;;
      esac
    fi
    _idx=$((_idx + 1))
  done
  _notrun=$(( ${#SUITES[@]} - _done ))
  if [ "${#_REPLAYED[@]}" -ne 0 ]; then
    echo "RED UNDER THE POOL, GREEN WHEN REPLAYED ALONE — contention OR intermittent defect, NOT established: name them, open a follow-up (L-00000234):"
    for s in ${_REPLAYED[@]+"${_REPLAYED[@]}"}; do echo "  - $s"; done
    echo
  fi
  echo "Parallel: ${_done}/${#SUITES[@]} suite(s) played in $(( _p_t1 - _p_t0 ))s under $RBT_JOBS jobs; slowest: $(LC_ALL=C sort -rn "$_par/durations" | awk 'NR <= 5 {printf "%s%s %ss", (NR > 1 ? ", " : ""), $2, $1}')"
  echo "================================================================"
  echo "Bash test summary: $passed passed / $failed failed / $hung timed out (of ${#SUITES[@]}) / $missing missing dep / $skipping skipping"
  if [ "$_notrun" -ne 0 ]; then
    echo "NOT RUN (fail-fast=$RBT_FF; CADRE_GATE_FAIL_FAST=0 runs all): $_notrun suite(s) — the failure list is NOT complete"
  fi
  if [ "$hung" -ne 0 ]; then
    echo "Timed out (killed at ${SUITE_TIMEOUT}s — raise with BASH_TEST_TIMEOUT):"
    for s in "${HUNG_SUITES[@]}"; do echo "  - $s"; done
  fi
  if [ "$missing" -ne 0 ]; then
    echo "Missing dependency (the suite could not run what it meant to run):"
    for s in "${MISSING_SUITES[@]}"; do echo "  - $s"; done
  fi
  if [ "$skipping" -ne 0 ]; then
    echo "Announced a SKIP or a missing optional tool (green, but NOT full coverage):"
    for s in "${SKIPPING_SUITES[@]}"; do echo "  - $s"; done
  fi
  if [ "$failed" -ne 0 ]; then
    echo "Failed suites:"
    for s in "${FAILED_SUITES[@]}"; do echo "  - $s"; done
  fi
  if [ "$MISSING_DETECT" -eq 0 ]; then
    echo "COVERAGE DEGRADED: swallowed-127 detection was unavailable for this run" >&2
    echo "  — a suite that RAN an absent command would not have been caught." >&2
  fi
  if [ "$failed" -ne 0 ] || [ "$hung" -ne 0 ] || [ "$missing" -ne 0 ] || [ "$_notrun" -ne 0 ]; then
    _rbt_rouges_ecrire ${_ROUGES[@]+"${_ROUGES[@]}"}
    exit 1
  fi
  echo "All bash suites passed."
  if [ "$skipping" -ne 0 ]; then
    echo "  ($skipping of them announced a SKIP or a missing optional tool — green is not coverage.)"
  fi
  exit 0
fi
# --- fin du mode parallele ----------------------------------------------------------------

passed=0
failed=0
hung=0
missing=0
skipping=0
FAILED_SUITES=()
HUNG_SUITES=()
MISSING_SUITES=()
SKIPPING_SUITES=()
ROUGES_SUITES=()   # les chemins NUS des suites rouges (fail, pendue, dependance manquante), pour CADRE_GATE_ROUGES_OUT

for suite in "${SUITES[@]}"; do
  echo "=== RUN  $suite"
  started=$SECONDS
  rc=0

  requires="$(suite_directive "$suite" 'requires')"
  optional="$(suite_directive "$suite" 'optional')"
  allows="$(suite_directive "$suite" 'allows-missing')"

  # A REQUIRED TOOL IS CHECKED BEFORE THE SUITE RUNS. The whole point of
  # `# requires:` is that WITHOUT that tool the suite proves nothing, so running
  # it to watch it auto-skip would reinstate the same blindness one layer down.
  req_absent=""
  for _c in $requires; do
    if ! command -v "$_c" >/dev/null 2>&1; then req_absent="$req_absent $_c"; fi
  done
  if [ -n "$req_absent" ]; then
    echo "--- MISSING DEP $suite (requires:$req_absent — not run)"
    missing=$((missing + 1))
    MISSING_SUITES+=("$suite (requires:$req_absent)")
    ROUGES_SUITES+=("$suite")
    echo
    continue
  fi

  opt_absent=""
  for _c in $optional; do
    if ! command -v "$_c" >/dev/null 2>&1; then opt_absent="$opt_absent $_c"; fi
  done

  # THE OUTPUT IS CAPTURED **AND** STREAMED — not either/or. Buffering it would
  # make a 900 s suite read exactly like the hang T-00000160 was written about.
  # En mode parallele, le flux d'un enfant est differe a sa fin (_judge le rejoue) ;
  # le chien de garde reste la seule borne (binome 7+8, T6).
  #
  # `set +e` … `rc=${PIPESTATUS[0]}` … `set -e` is spelled out rather than
  # shortened to `|| true`, and that is load-bearing: `|| true` would OVERWRITE
  # PIPESTATUS with the status of `true` and hand back rc=0 for EVERY suite — a
  # perfect false green manufactured by the very line meant to prevent one.
  : >"$RBT_MISSING_LOG"
  set +e
  if [ "$WATCHDOG" -eq 1 ]; then
    "$TIMEOUT_BIN" --kill-after="$KILL_GRACE" "$SUITE_TIMEOUT" bash "$suite" 2>&1 | tee "$RBT_OUT"
    rc=${PIPESTATUS[0]}
  else
    bash "$suite" 2>&1 | tee "$RBT_OUT"
    rc=${PIPESTATUS[0]}
  fi
  set -e
  elapsed=$((SECONDS - started))

  # What the sensor caught, minus the names this suite DECLARED it may invoke.
  miss_names=""
  if [ -s "$RBT_MISSING_LOG" ]; then
    while IFS= read -r _m; do
      if [ -z "$_m" ]; then continue; fi
      _allowed=0
      for _a in $allows; do
        if [ "$_m" = "$_a" ]; then _allowed=1; break; fi
      done
      if [ "$_allowed" -eq 1 ]; then continue; fi
      case " $miss_names " in
        *" $_m "*) : ;;
        *) miss_names="$miss_names $_m" ;;
      esac
    done < <(LC_ALL=C sort -u "$RBT_MISSING_LOG")
  fi

  # 124 = the TERM deadline fired, 137 = the SIGKILL escalation was needed. Both
  # are also reachable by a suite that kills itself, so the elapsed time has to
  # agree before we blame the watchdog — a run attributed to a timeout it did not
  # cause would send the reader hunting for a hang that never happened.
  if [ -n "$miss_names" ] || { [ "$rc" -eq 127 ] && [ -z "$allows" ]; }; then
    # RED. A suite that could not resolve what it meant to execute has proven
    # nothing, whatever its exit code claims. The bare `rc=127` arm keeps the
    # verdict reachable on bash 3.2, where the sensor logs nothing — but it
    # stands down for a suite carrying `# allows-missing:`, whose 127 may be the
    # declared one propagating out.
    if [ -n "$miss_names" ]; then
      echo "--- MISSING DEP $suite (cmd:$miss_names, ${elapsed}s)"
      MISSING_SUITES+=("$suite (cmd:$miss_names)")
    else
      echo "--- MISSING DEP $suite (exit 127, ${elapsed}s)"
      MISSING_SUITES+=("$suite (exit 127)")
    fi
    missing=$((missing + 1))
    ROUGES_SUITES+=("$suite")
  elif [ "$rc" -eq 0 ]; then
    # GREEN, BUT SAID. `command -v` never trips the sensor, so the only evidence
    # an auto-SKIP leaves is the line the suite printed about it. Anchored at the
    # start of a line so a SKIP the suite MENTIONS is not counted as one it TOOK.
    note=""
    n_skip="$(grep -acE '^[[:space:]]*SKIP|^[[:space:]]*ok:.*\[SKIP' "$RBT_OUT" 2>/dev/null || true)"
    if [ -z "$n_skip" ]; then n_skip=0; fi
    if [ "$n_skip" -gt 0 ]; then
      first="$(grep -am1 -E '^[[:space:]]*SKIP|^[[:space:]]*ok:.*\[SKIP' "$RBT_OUT" 2>/dev/null \
               | sed 's/^[[:space:]]*//')"
      note=" — $n_skip SKIP annoncé(s) : $first"
    fi
    if [ -n "$opt_absent" ]; then
      note="$note — optional absent:$opt_absent"
    fi
    echo "--- PASS $suite (${elapsed}s)$note"
    passed=$((passed + 1))
    if [ -n "$note" ]; then
      skipping=$((skipping + 1))
      SKIPPING_SUITES+=("$suite$note")
    fi
  elif [ "$WATCHDOG" -eq 1 ] && { [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; } \
       && [ "$elapsed" -ge "$SUITE_TIMEOUT" ]; then
    echo "--- TIMEOUT $suite (killed after ${elapsed}s, limit ${SUITE_TIMEOUT}s)"
    hung=$((hung + 1))
    HUNG_SUITES+=("$suite (${elapsed}s)")
    ROUGES_SUITES+=("$suite")
  else
    echo "--- FAIL $suite (exit $rc, ${elapsed}s)"
    failed=$((failed + 1))
    FAILED_SUITES+=("$suite")
    ROUGES_SUITES+=("$suite")
  fi
  echo
done

echo "================================================================"
# The two new counters are appended AFTER `(of N)` on purpose: this line is
# grep'd as a SUBSTRING by run-bash-tests.test.sh:121 and :155, both of which
# stop at `(of N)`. Extending to the right leaves those assertions intact.
echo "Bash test summary: $passed passed / $failed failed / $hung timed out (of ${#SUITES[@]}) / $missing missing dep / $skipping skipping"
if [ "$hung" -ne 0 ]; then
  echo "Timed out (killed at ${SUITE_TIMEOUT}s — raise with BASH_TEST_TIMEOUT):"
  for s in "${HUNG_SUITES[@]}"; do echo "  - $s"; done
fi
if [ "$missing" -ne 0 ]; then
  echo "Missing dependency (the suite could not run what it meant to run):"
  for s in "${MISSING_SUITES[@]}"; do echo "  - $s"; done
fi
if [ "$skipping" -ne 0 ]; then
  echo "Announced a SKIP or a missing optional tool (green, but NOT full coverage):"
  for s in "${SKIPPING_SUITES[@]}"; do echo "  - $s"; done
fi
if [ "$failed" -ne 0 ]; then
  echo "Failed suites:"
  for s in "${FAILED_SUITES[@]}"; do echo "  - $s"; done
fi
# Repeated at the summary, where people actually look: an announcement made 33
# suites ago has scrolled away, and a degradation nobody sees is not announced.
if [ "$MISSING_DETECT" -eq 0 ]; then
  echo "COVERAGE DEGRADED: swallowed-127 detection was unavailable for this run" >&2
  echo "  — a suite that RAN an absent command would not have been caught." >&2
fi
if [ "$failed" -ne 0 ] || [ "$hung" -ne 0 ] || [ "$missing" -ne 0 ]; then
  _rbt_rouges_ecrire ${ROUGES_SUITES[@]+"${ROUGES_SUITES[@]}"}
  exit 1
fi
echo "All bash suites passed."
# On its OWN line, leaving `All bash suites passed.` byte-identical: it is the
# string CI logs and T-00000408's gate criterion are read against.
if [ "$skipping" -ne 0 ]; then
  echo "  ($skipping of them announced a SKIP or a missing optional tool — green is not coverage.)"
fi
