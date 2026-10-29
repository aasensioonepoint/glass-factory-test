#!/usr/bin/env bash
# safe-bash-ew-eo.test.sh — TROISIÈME des quatre morceaux de la suite
# de .claude/hooks/safe-bash.sh (scission T-01M4WTYT8M),
# coupe à la bannière « (ew)(ef)(en) ».
# Sections : (ew)(ef)(en)(gp)(fp)(kr)(ct)(eo), git derrière une enveloppe
#   prouvée (T-00001102 + T-00001090).
# Les arms sont ceux d'origine, dans l'ordre d'origine : aucun retiré, aucun
# affaibli. La carte des mutants (quel mutant tue quel arm), le mode d'emploi de
# SAFE_BASH_HOOK et la liste des quatre morceaux vivent UNE fois, en tête de
# safe-bash.test.sh. Le prologue ci-dessous est recopié octet pour octet dans les
# quatre morceaux ; (split0) de safe-bash.test.sh compare les copies.
# >>> safe-bash-prologue
# PROLOGUE COMMUN des quatre suites .claude/hooks/safe-bash*.test.sh
# (T-01M4WTYT8M) : le MÊME, octet pour octet, dans chacune ; (split0) de
# safe-bash.test.sh compare les quatre copies. Le modifier ici, c'est le
# modifier dans les QUATRE fichiers.
set -u
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${SAFE_BASH_HOOK:-$HERE/safe-bash.sh}"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
if [ -z "$PY" ]; then echo "SKIP: ${0##*/} needs python to build the payloads"; exit 0; fi
# REAL_PY : l'interpréteur RÉSOLU, que les cales des sections (n)(s)(x)(z)
# exécutent derrière leur filtre. Au prologue (T-01M4WTYT8M) : trois des quatre
# morceaux l'emploient, et aucun ne lit l'état qu'un autre a construit.
REAL_PY="$(command -v "$PY")"
# Events from the guard's own emit calls must never land in the real store.
EVTMP="$(mktemp -d)"
export AGENTS_EVENTS_DIR="$EVTMP"
OUTF="$EVTMP/stdout"; ERRF="$EVTMP/stderr"

PASS=0; FAIL=0

# json_payload <command> — la forme PreToolUse réelle.
# WINDOWS (fait mesuré, et la raison pour laquelle ces deux variables sont là) :
# sous Git Bash / MSYS, argv passé à un binaire natif (python.exe) subit une
# TRADUCTION DE CHEMIN — `/bin/rm secrets.txt` arrivait à python comme
# `C:/Program Files/Git/usr/bin/rm secrets.txt`. La suite mesurait alors une
# charge utile réécrite par le shell, pas celle qu'elle décrit : l'arm (h9)
# passait en vert sans que le garde ait jamais vu un `/bin/rm`. Les deux
# variables neutralisent la conversion ; sur Linux (CI) elles sont inertes.
json_payload() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    "$PY" -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$1"
}

check() { # check <expected_exit> <label> <command-string>
  expected="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_deny_msg() { # check_deny_msg <motif> <label> <command-string>
  # REFUSÉ, ET POUR LA BONNE RAISON. Le code de sortie seul ne suffit pas
  # (L-00000161) : ce garde porte PLUSIEURS motifs distincts — rm-rf-root,
  # git-wipe-unscoped, git-output-write, git-grep-pager-exec,
  # git-subcommand-hidden, rg-absent-silent-failure, redirect-write-guarded,
  # rm-mv-bypass-checkpoint, depuis T-00000784 redirect-stage-broken et, depuis
  # T-00001090, git-branch-force-delete — donc
  # un arm satisfait par le mauvais d'entre eux serait un faux vert ; c'est
  # exactement ce que la matrice de parité assert de son côté avec ses `motive`.
  # Le compte a été porté de TROIS à CINQ (T-00000227), puis le CHIFFRE a été
  # RETIRÉ (T-00000784, L-00000187) : il était de nouveau périmé — huit règles
  # `deny` quand il en disait cinq — DANS le helper même dont la thèse est « un
  # code de sortie n'est pas un motif ». La liste se relève par grep des
  # `deny <règle>` et du `rule=` de l'étage redirection de safe-bash.sh ; elle
  # n'est close par aucun chiffre.
  motive="$1"; label="$2"; cmd="$3"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  msg="$(cat "$ERRF")"
  case "$msg" in
    *"$motive"*) if [ "$got" -eq 2 ]; then PASS=$((PASS+1)); echo "PASS: $label"; return; fi;;
  esac
  FAIL=$((FAIL+1))
  echo "FAIL: $label (expected exit 2 carrying <$motive>, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
}

check_silent() { # check_silent <label> <command-string> — laissé passer ET sans
  # un mot sur aucune des deux sorties. C'est l'assertion qui attrape le défaut
  # de T-00000146 : le garde ne doit pas seulement laisser passer une commande
  # qui MENTIONNE une suppression, il ne doit pas non plus la commenter.
  label="$1"; cmd="$2"
  printf '%s' "$(json_payload "$cmd")" | bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

# check_path <PATH> <expected_exit> <label> <command-string>
# Même contrat que `check`, mais joue le hook sous un PATH imposé — la garde
# `rg` se comporte différemment selon que l'outil résout ou non, et un test qui
# hériterait du PATH du poste basculerait de vert à rouge le jour d'une
# installation de ripgrep. Les deux branches sont donc FORCÉES, pas observées.
# La charge utile est sérialisée AVANT la substitution de PATH : c'est le garde
# qu'on déplace, pas le harnais.
check_path() {
  forced_path="$1"; expected="$2"; label="$3"; cmd="$4"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  if [ "$got" -eq "$expected" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit $expected, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
  fi
}

check_silent_path() { # check_silent_path <PATH> <label> <command-string>
  forced_path="$1"; label="$2"; cmd="$3"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$got" -eq 0 ] && [ -z "$noise" ]; then
    PASS=$((PASS+1)); echo "PASS: $label"
  else
    FAIL=$((FAIL+1)); echo "FAIL: $label (expected exit 0 and no output, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")> stdout=<$(tr '\n' ' ' < "$OUTF")>"
  fi
}

assert() { # assert <rc 0=ok> <label>
  if [ "$1" -eq 0 ]; then PASS=$((PASS+1)); echo "PASS: $2"; else FAIL=$((FAIL+1)); echo "FAIL: $2"; fi
}
# <<< safe-bash-prologue

# =============================================================================
# (ew)(ef)(en)(gp)(ct)(eo)(em)(bd) T-00001102 + T-00001090 (rév. 2) — git DERRIÈRE une enveloppe PROUVÉE ; `git branch -D wt/*`.
# Témoins ROUGES à BASE (de307018) : (ew) ×0, (ef) ×0, (eo) valeurs ×28 et sans-valeur, (em), (bd) ×26 ; VERTS avant ET après : (en), (gp), (ct).
# Chaque témoin est tenu sur les TROIS hôtes par la parité (build_matrix) ; ici seulement l'hôte Claude (awk + passe embarquée).
# =============================================================================
check_silent "(ew1) incident T-1102" 'cd /tmp/crm && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE git mv scripts/deploy-azure.test.sh .agents/evals/deploy-azure.test.sh && git status --short'
check_silent "(ew2) env -u GIT_DIR git mv a.txt b.txt" 'env -u GIT_DIR git mv a.txt b.txt'
check_silent "(ew3) env git mv a.txt b.txt" 'env git mv a.txt b.txt'
check_silent "(ew4) env -i git mv a.txt b.txt" 'env -i git mv a.txt b.txt'
check_silent "(ew5) env FOO=1 git mv a.txt b.txt" 'env FOO=1 git mv a.txt b.txt'
check_silent "(ew6) command git mv a.txt b.txt" 'command git mv a.txt b.txt'
check_silent "(ew7) nohup git mv a.txt b.txt" 'nohup git mv a.txt b.txt'
check_silent "(ew8) time git mv a.txt b.txt" 'time git mv a.txt b.txt'
check_silent "(ew9) sudo git rm -q docs/x.md" 'sudo git rm -q docs/x.md'
check_silent "(ew10) passe embarquée (rm /tmp : ALLOW Claude seul)" 'env -u GIT_DIR git mv a.txt b.txt && rm -rf /tmp/zz'
check_silent "(ew11) A-C2 imbrication en table" 'sudo env -u GIT_DIR git mv a.txt b.txt'
check_silent "(ew12) A-C2" 'env -u GIT_DIR sudo git mv a.txt b.txt'
check_silent "(ew13) option longue à valeur séparée" 'sudo --user deploy git mv a.txt b.txt'
check_silent "(ew14) valeur citée (atomique)" 'env -u "$X" git mv a.txt b.txt'
check_silent "(ew15) env -C /tmp git mv a.txt b.txt" 'env -C /tmp git mv a.txt b.txt'
check_silent "(ew16) doas -u x git mv a.txt b.txt" 'doas -u x git mv a.txt b.txt'
check_silent "(ew17) deux options à valeur" 'sudo -u deploy -g staff git rm -q docs/x.md'
check_silent "(ew18) fin d'options" 'sudo -- git mv a.txt b.txt'
check_silent "(ew19) option globale de git AVANT la sous-commande" 'sudo git -C x mv a.txt b.txt'
check_silent "(ew20) -c a valeur séparée" 'env -u X git -c core.x=1 rm -q docs/y'
check_silent "(ew21) option globale sans valeur" 'sudo git --no-pager mv a.txt b.txt'
check_silent "(ew22) assignation à valeur citée" 'env FOO="a b" git mv a.txt b.txt'
check_silent "(ew23) chemins absolus" '/usr/bin/sudo -u x /usr/bin/git mv a.txt b.txt'
check_deny_msg "unscoped" "(ef1) env -u GIT_DIR git reset --hard" 'env -u GIT_DIR git reset --hard'
check_deny_msg "unscoped" "(ef2) env -u GIT_DIR git restore ." 'env -u GIT_DIR git restore .'
check_deny_msg "unscoped" "(ef3) env -C /tmp git restore ." 'env -C /tmp git restore .'
check_deny_msg "unscoped" "(ef4) sudo -u x git reset --hard" 'sudo -u x git reset --hard'
check_deny_msg "unscoped" "(ef5) doas -u x git restore ." 'doas -u x git restore .'
check_deny_msg "--output" "(ef6) env -u GIT_DIR git show --output=f HEAD" 'env -u GIT_DIR git show --output=f HEAD'
check_deny_msg "unscoped" "(ef7) A-C1 expansion non citée" 'sudo -u $U git reset --hard'
check_deny_msg "unscoped" "(ef8) A-C1" 'env -u $X git reset --hard'
check_deny_msg "unscoped" "(ef9) A-C1 option longue" 'sudo --user x git reset --hard'
check_deny_msg "unscoped" "(ef10) A-C1 longue + expansion" 'sudo --user $U git reset --hard'
check_deny_msg "unscoped" "(ef11) A-C1" 'sudo -g grp git reset --hard'
check_deny_msg "unscoped" "(ef12) A-C2" 'sudo env -u GIT_DIR git reset --hard'
check_deny_msg "unscoped" "(ef13) A-C2" 'env -u GIT_DIR sudo git reset --hard'
check_deny_msg "unscoped" "(ef14) valeur = substitution" 'sudo -u $(id -un) git reset --hard'
check_deny_msg "unscoped" "(ef15) commande = expansion" 'sudo $X git reset --hard'
check_deny_msg "unscoped" "(ef16) abréviation d'option longue" 'sudo --us x git reset --hard'
check_deny_msg "unscoped" "(ef17) grappe courte hors table" 'sudo -nu root git reset --hard'
check_deny_msg "unscoped" "(ef18) fin d'options" 'sudo -u x -- git reset --hard'
check_deny_msg "unscoped" "(ef19) option inconnue" 'sudo --foo git reset --hard'
check_deny_msg "unscoped" "(ef20) option inconnue + valeur (git = 2e candidat)" 'sudo --foo bar git reset --hard'
check_deny_msg "unscoped" "(ef21) -h hors table (aide OU hote)" 'sudo -h host git reset --hard'
check_deny_msg "unscoped" "(ef22) -S hors table, charge NON citee" 'env -S git reset --hard'
check_deny_msg "unscoped" "(ef23) deux valeurs a expansion" 'sudo -u $U -g $G git reset --hard'
check_deny_msg "unscoped" "(ef24) --opt=val inconnue" 'sudo -E --foo=bar git reset --hard'
check_deny_msg "unscoped" "(ef25) doas + expansion" 'doas -u $U git restore .'
check_deny_msg "unscoped" "(ef29) mot d'option CITÉ (opaque : ambigu, git jugé)" 'sudo "-u" x git reset --hard'
check_deny_msg "unscoped" "(ef30) chemins absolus" '/usr/bin/env -u X /usr/bin/git reset --hard'
check_deny_msg "unscoped" "(ef31) antislash (alias)" '\sudo -u x git reset --hard'
check_deny_msg "unscoped" "(ef26) valeur citée" 'sudo -u "$U" git reset --hard'
check_deny_msg "unscoped" "(ef27) env -u GIT_DIR git clean -fd" 'env -u GIT_DIR git clean -fd'
check_deny_msg "unscoped" "(ef28) env -u GIT_DIR git stash" 'env -u GIT_DIR git stash'
check_silent "(gp1) KNOWN GAP: timeout 5 git reset --hard" 'timeout 5 git reset --hard'
check_silent "(gp2) KNOWN GAP: nice -n 5 git reset --hard" 'nice -n 5 git reset --hard'
# (gp3) BASCULÉ par T-01M5D6XS2S (étape 4) : `xargs` en tête ouvre une fenêtre
# lue (git jugé, opérandes du tube larges) ; gp1, gp2, gp4-gp6 (timeout, nice,
# ionice) restent des trous S1 nommés.
check_deny_msg "unscoped" "(gp3) T-01M5D6XS2S : xargs -n 1 git restore . lu et refusé" 'xargs -n 1 git restore .'
check_silent "(gp4) KNOWN GAP: ionice -c 3 git restore ." 'ionice -c 3 git restore .'
check_silent "(gp5) KNOWN GAP: sudo timeout 5 git reset --hard" 'sudo timeout 5 git reset --hard'
check_silent "(gp6) KNOWN GAP: timeout 5 sudo -u x git reset --hard" 'timeout 5 sudo -u x git reset --hard'
check_silent "(gp7) KNOWN GAP: timeout 5 git branch -D wt/T-1" 'timeout 5 git branch -D wt/T-1'
check_silent "(gp8) KNOWN GAP: env -v git reset --hard" 'env -v git reset --hard'
check_silent "(gp9) KNOWN GAP: env -v rm -rf src/x" 'env -v rm -rf src/x'
check_silent "(gp10) KNOWN GAP (résidu réserve (1)) : option APRÈS la substitution, la lecture s'arrête à la substitution" 'git branch $(cat f) -D'
check_deny_msg "checkpoint" "(en1) env -u git rm -rf src/x" 'env -u git rm -rf src/x'
check_deny_msg "checkpoint" "(en2) env -C git rm -rf src/x" 'env -C git rm -rf src/x'
check_deny_msg "checkpoint" "(en3) sudo -u git rm -rf src/x" 'sudo -u git rm -rf src/x'
check_deny_msg "checkpoint" "(en4) env -X git rm -rf src/x" 'env -X git rm -rf src/x'
check_deny_msg "checkpoint" "(en5) env -u X git rm -rf src/x" 'env -u $X git rm -rf src/x'
check_deny_msg "checkpoint" "(en6) env git mv a.txt b.txt; rm -rf src/x" 'env git mv a.txt b.txt; rm -rf src/x'
check_deny_msg "checkpoint" "(en7) xargs git mv a.txt" 'xargs git mv a.txt'
check_deny_msg "checkpoint" "(en8) KNOWN FP gardé" 'sudo docker rm container'
check_deny_msg "checkpoint" "(en9a) KNOWN FP gardé (hors table)" 'timeout 60 git mv a.txt b.txt'
check_deny_msg "checkpoint" "(en9b) KNOWN FP gardé (hors table)" 'nice -n 5 git mv a.txt b.txt'
check_deny_msg "checkpoint" "(en10) critique" 'env -u $X type rm -rf src/x'
check_deny_msg "checkpoint" "(en11) critique" 'env -u $X which rm'
check_deny_msg "checkpoint" "(en12) critique" 'sudo --user git rm -rf src/x'
check_deny_msg "checkpoint" "(en13) sonde -v après valeur" 'sudo -u root -v rm -rf src/x'
check_deny_msg "checkpoint" "(en14) valeur = rm" 'env -u rm git status'
check_deny_msg "checkpoint" "(en15) imbriquée, valeur git" 'sudo env -u git rm -rf src/x'
check_deny_msg "checkpoint" "(en16) fermeture ne survit pas au séparateur" 'sudo git rm -rf src/x; rm -rf src/y'
check_deny_msg "checkpoint" "(en17) sudo git status && rm -rf src/x" 'sudo git status && rm -rf src/x'
check_deny_msg "checkpoint" "(en18) rm en fenêtre ambiguë" 'sudo -u $U rm -rf src/x'
check_deny_msg "checkpoint" "(en19) assignation à expansion : pas de fermeture" 'env FOO=$X git rm -rf src/x'
check_deny_msg "checkpoint" "(en20) sudo -E git rm -rf src/x && rm -rf src/z" 'sudo -E git rm -rf src/x && rm -rf src/z'
check_deny_msg "checkpoint" "(en21) git LANCE rm : l'exemption ne couvre que git rm|mv" 'sudo git submodule foreach rm -rf src/x'
check_deny_msg "checkpoint" "(en22) env -u X git bisect run rm -rf src/x" 'env -u X git bisect run rm -rf src/x'
check_deny_msg "checkpoint" "(en23) sudo git rebase -x rm -rf src/x" 'sudo git rebase -x rm -rf src/x'
check_deny_msg "checkpoint" "(en24) KNOWN FP gardé : rm mot ordinaire, pas sous-commande" 'sudo git commit -m rm'
check_deny_msg "checkpoint" "(en25) KNOWN FP gardé" 'sudo git mv a.txt rm'
check 2 "(en26) sous-commande cachée : pas d'exemption (refusée par git-subcommand-hidden)" 'sudo git $s rm -rf src/x'
check_deny_msg "subcommand" "(fp1) KNOWN FP borné : git lu comme commande, expansion à la place de la sous-commande" 'sudo -u $U apt install git $P'
check_deny_msg "subcommand" "(fp2) KNOWN FP borné" 'sudo --foo apt install git $P'
check_deny_msg "checkpoint" "(en28) KNOWN FP gardé : option citée = ambiguë, pas de preuve" 'sudo "-u" x git mv a.txt b.txt'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'xargs sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'nice sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'exec sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'watch sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'parallel sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'setsid sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'stdbuf sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'ionice sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'eval sudo git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'xargs env git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'nice env -u X git rm -q docs/x'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'sudo xargs git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'sudo nice git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'env -u X nice git mv a b'
check_deny_msg "checkpoint" "(en27) chaîne hors tables" 'sudo -u x timeout 5 git mv a b'
check_silent "(kr1) KNOWN RELAXATION : {} coupe la chaîne, sudo git mv devient un segment prouvé (git mv, bénin)" 'xargs -I{} sudo git mv {} b'
check_silent "(ct1) control: git mv a.txt b.txt passes" 'git mv a.txt b.txt'
check_silent "(ct2) control: GIT_TRACE=0 git mv a.txt b.txt passes" 'GIT_TRACE=0 git mv a.txt b.txt'
check_silent "(ct3) control: git status passes" 'git status'
check_silent "(ct4) control: sudo apt install git passes" 'sudo apt install git'
check_silent "(ct5) control: timeout 60 git fetch passes" 'timeout 60 git fetch'
check_silent "(ct6) control: nice -n 5 git status passes" 'nice -n 5 git status'
check_silent "(ct7) control: env -u GIT_DIR git status passes" 'env -u GIT_DIR git status'
check_silent "(ct8) control: sudo -u deploy git log --oneline passes" 'sudo -u deploy git log --oneline'
check_silent "(ct9) control: command -v git passes" 'command -v git'
check_silent "(ct10) control: env -u GIT_DIR git restore src/foo.ts passes" 'env -u GIT_DIR git restore src/foo.ts'
check_silent "(ct11) control: sudo -u U git status passes" 'sudo -u $U git status'
check_silent "(ct12) control: sudo --foo git status passes" 'sudo --foo git status'
check_silent "(ct13) control: xargs -n 1 git status passes" 'xargs -n 1 git status'
check_silent "(ct14) control: time git status passes" 'time git status'
check_silent "(ct15) control: nohup git fetch passes" 'nohup git fetch'
check_silent "(ct16) control: sudo -u U apt install git passes" 'sudo -u $U apt install git'
check_silent "(ct17) control: sudo -u x git reset --soft HEAD~1 passes" 'sudo -u x git reset --soft HEAD~1'
check_silent "(ct18) control: env -u GIT_DIR git clean -n passes" 'env -u GIT_DIR git clean -n'
check_silent "(ct19) control: sudo git stash list passes" 'sudo git stash list'

# (eo) UNE PREUVE PAR OPTION de chaque table (A-C6, mutant M4 généralisé) : une option À VALEUR consomme le mot suivant, donc
# `git` n'y est qu'une valeur et le rm qui suit reste refusé ; une option SANS valeur laisse git en position de commande.
eo_n=0
for eo_opt in -u -C -P -a --unset --chdir --argv0; do
  eo_n=$((eo_n+1))
  check_deny_msg "checkpoint" "(eo$eo_n) env $eo_opt takes a value: git is that value, rm stays refused" "env $eo_opt git rm -rf src/x"
  check_deny_msg "unscoped" "(eo$eo_n-b) env $eo_opt takes a value: the false negative is closed" "env $eo_opt v git reset --hard"
  check_silent "(eo$eo_n-c) env $eo_opt v: the false positive is lifted" "env $eo_opt v git mv a.txt b.txt"
done
for eo_opt in - -i -0 --ignore-environment --null --debug --list-signal-handling --block-signal --default-signal --ignore-signal --; do
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) env $eo_opt takes no value: git stays the command" "env $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) env $eo_opt: the lift ends at the separator" "env $eo_opt git rm -rf src/x && rm -rf src/y"
done
for eo_opt in -C -D -g -p -R -T -U -u -r -t --close-from --chdir --group --prompt --chroot --command-timeout --other-user --user --role --type; do
  eo_n=$((eo_n+1))
  check_deny_msg "checkpoint" "(eo$eo_n) sudo $eo_opt takes a value: git is that value, rm stays refused" "sudo $eo_opt git rm -rf src/x"
  check_deny_msg "unscoped" "(eo$eo_n-b) sudo $eo_opt takes a value: the false negative is closed" "sudo $eo_opt v git reset --hard"
  check_silent "(eo$eo_n-c) sudo $eo_opt v: the false positive is lifted" "sudo $eo_opt v git mv a.txt b.txt"
done
for eo_opt in -A -B -b -E -H -k -N -n -P -S -i -s --askpass --bell --background --preserve-env --set-home --reset-timestamp --login --non-interactive --preserve-groups --stdin --shell --no-update --; do
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) sudo $eo_opt takes no value: git stays the command" "sudo $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) sudo $eo_opt: the lift ends at the separator" "sudo $eo_opt git rm -rf src/x && rm -rf src/y"
done
for eo_opt in -C -u; do
  eo_n=$((eo_n+1))
  check_deny_msg "checkpoint" "(eo$eo_n) doas $eo_opt takes a value: git is that value, rm stays refused" "doas $eo_opt git rm -rf src/x"
  check_deny_msg "unscoped" "(eo$eo_n-b) doas $eo_opt takes a value: the false negative is closed" "doas $eo_opt v git reset --hard"
  check_silent "(eo$eo_n-c) doas $eo_opt v: the false positive is lifted" "doas $eo_opt v git mv a.txt b.txt"
done
for eo_opt in -L -n -s --; do
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) doas $eo_opt takes no value: git stays the command" "doas $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) doas $eo_opt: the lift ends at the separator" "doas $eo_opt git rm -rf src/x && rm -rf src/y"
done
for eo_opt in -p --; do
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) command $eo_opt takes no value: git stays the command" "command $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) command $eo_opt: the lift ends at the separator" "command $eo_opt git rm -rf src/x && rm -rf src/y"
done
eo_opt=--
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) nohup $eo_opt takes no value: git stays the command" "nohup $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) nohup $eo_opt: the lift ends at the separator" "nohup $eo_opt git rm -rf src/x && rm -rf src/y"
for eo_opt in -p --; do
  eo_n=$((eo_n+1))
  check_silent "(eo$eo_n) time $eo_opt takes no value: git stays the command" "time $eo_opt git mv a.txt b.txt"
  check_deny_msg "checkpoint" "(eo$eo_n-b) time $eo_opt: the lift ends at the separator" "time $eo_opt git rm -rf src/x && rm -rf src/y"
done

echo "----------------------------------------"
echo "safe-bash-ew-eo.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
