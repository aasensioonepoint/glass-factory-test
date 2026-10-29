#!/usr/bin/env bash
# safe-bash-em-z.test.sh — QUATRIÈME des quatre morceaux de la suite
# de .claude/hooks/safe-bash.sh (scission T-01M4WTYT8M),
# coupe au commentaire « (em) les MÊMES garanties ».
# Sections : (em) modes de commande, (bd)(bc) `git branch -D`,
#   puis (z) T-00000784, l'étage redirection planté.
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

# (em) les MÊMES garanties dans chaque MODE de commande (L-00000474) : sous-shell, if, &&, substitution, accolades, boucle, pipe, tube, backtick, redirection.
check_deny_msg "unscoped" "(em1) mode: (sudo -u x git reset --hard)" '(sudo -u x git reset --hard)'
check_deny_msg "unscoped" "(em2) mode: echo (sudo -u x git reset --hard)" 'echo $(sudo -u x git reset --hard)'
check_deny_msg "unscoped" "(em3) mode: if true; then sudo -u x git reset --hard; fi" 'if true; then sudo -u x git reset --hard; fi'
check_deny_msg "unscoped" "(em4) mode: true && sudo -u U git reset --hard" 'true && sudo -u $U git reset --hard'
check_deny_msg "unscoped" "(em5) mode: { sudo -u x git reset --hard; }" '{ sudo -u x git reset --hard; }'
check_deny_msg "unscoped" "(em6) mode: for f in a; do env -u X git reset --hard; done" 'for f in a; do env -u X git reset --hard; done'
check_deny_msg "unscoped" "(em7) mode: echo hi / sudo -u x git reset --hard" $'echo hi\nsudo -u x git reset --hard'
check_deny_msg "unscoped" "(em8) mode: sudo -u x git reset --hard | cat" 'sudo -u x git reset --hard | cat'
check_deny_msg "unscoped" "(em9) mode: cat x | sudo -u U git reset --hard" 'cat x | sudo -u $U git reset --hard'
check_deny_msg "unscoped" "(em10) mode: sudo -u x git reset --hard" '`sudo -u x git reset --hard`'
check_deny_msg "unscoped" "(em11) mode: cat <(sudo -u x git reset --hard)" 'cat <(sudo -u x git reset --hard)'
check_deny_msg "unscoped" "(em12) mode: FOO=1 sudo -u x git reset --hard" 'FOO=1 sudo -u x git reset --hard'
check_deny_msg "unscoped" "(em13) mode: sudo -u x git reset --hard 2>/dev/null" 'sudo -u x git reset --hard 2>/dev/null'
check_deny_msg "unscoped" "(em14) mode: sudo -u x git reset --hard # note" 'sudo -u x git reset --hard # note'
check_deny_msg "unscoped" "(em15) mode: ! sudo -u x git reset --hard" '! sudo -u x git reset --hard'
check_deny_msg "unscoped" "(em16) mode: then sudo -u x git reset --hard" 'then sudo -u x git reset --hard'
check_deny_msg "unscoped" "(em17) mode: cd /tmp && env -u GIT_DIR git restore ." 'cd /tmp && env -u GIT_DIR git restore .'
check_deny_msg "unscoped" "(em18) mode: sudo -u x git -C /y reset --hard" 'sudo -u x git -C /y reset --hard'
check_deny_msg "unscoped" "(em19) mode: SUDO=x; sudo -u SUDO git reset --hard" 'SUDO=x; sudo -u $SUDO git reset --hard'
check_silent "(em20) mode: (sudo git mv a b)" '(sudo git mv a b)'
check_silent "(em21) mode: if true; then sudo git mv a b; fi" 'if true; then sudo git mv a b; fi'
check_silent "(em22) mode: true && sudo git mv a b" 'true && sudo git mv a b'
check_silent "(em23) mode: echo (sudo git mv a b)" 'echo $(sudo git mv a b)'
check_silent "(em24) mode: { env -u X git mv a b; }" '{ env -u X git mv a b; }'
check_silent "(em25) mode: echo hi / sudo git mv a b" $'echo hi\nsudo git mv a b'
check_silent "(em26) mode: sudo git mv a b | cat" 'sudo git mv a b | cat'
check_silent "(em27) mode: sudo git mv a b" '`sudo git mv a b`'
check_silent "(em28) mode: FOO=1 sudo git mv a b" 'FOO=1 sudo git mv a b'
check_silent "(em29) mode: sudo git mv a b 2>/dev/null" 'sudo git mv a b 2>/dev/null'
check_silent "(em30) mode: ! env git mv a b" '! env git mv a b'
check_silent "(em31) mode: sudo -u x git mv a b # note" 'sudo -u x git mv a b # note'
check_deny_msg "checkpoint" "(em32) mode: (sudo -u git rm -rf src/x)" '(sudo -u git rm -rf src/x)'
check_deny_msg "checkpoint" "(em33) mode: if true; then sudo docker rm c; fi" 'if true; then sudo docker rm c; fi'
check_deny_msg "checkpoint" "(em34) mode: true && env -u X git rm -rf src/x" 'true && env -u $X git rm -rf src/x'
check_deny_msg "checkpoint" "(em35) mode: echo (sudo -u git rm -rf src/x)" 'echo $(sudo -u git rm -rf src/x)'
check_deny_msg "checkpoint" "(em36) mode: sudo git mv a b; rm -rf src/x" 'sudo git mv a b; rm -rf src/x'
check_deny_msg "checkpoint" "(em37) mode: sudo git mv a b / rm -rf src/x" $'sudo git mv a b\nrm -rf src/x'
check_deny_msg "checkpoint" "(em38) mode: sudo git mv a b | xargs rm" 'sudo git mv a b | xargs rm'
check_deny_msg "checkpoint" "(em39) mode: sudo git status (rm -rf src/x)" 'sudo git status $(rm -rf src/x)'
check_deny_msg "checkpoint" "(em40) mode: sudo git status rm -rf src/x" 'sudo git status `rm -rf src/x`'
check_deny_msg "checkpoint" "(em41) mode: sudo git status > /dev/null; rm -rf src/x" 'sudo git status > /dev/null; rm -rf src/x'
check_deny_msg "checkpoint" "(em42) mode: sudo -u x git mv a b && sudo rm -rf src/x" 'sudo -u x git mv a b && sudo rm -rf src/x'
check_silent "(em43) mode: sudo git submodule status" 'sudo git submodule status'
check_silent "(em44) mode: git status; env git rm -q docs/x" 'git status; env git rm -q docs/x'
check_silent "(em45) mode: git mv a b; sudo git mv c d" 'git mv a b; sudo git mv c d'
check_silent "(em46) mode: git rm a; sudo git rm b" 'git rm a; sudo git rm b'
check_silent "(em47) mode: git log || nohup git -C x rm -r d" 'git log || nohup git -C x rm -r d'
check_deny_msg "unscoped" "(em48) mode: git status; sudo -u U git reset --hard" 'git status; sudo -u $U git reset --hard'
check_deny_msg "unscoped" "(em49) mode: git log; env -u X git reset --hard" 'git log; env -u X git reset --hard'
check_deny_msg "unscoped" "(em50) mode: git branch -a && sudo --foo bar git restore ." 'git branch -a && sudo --foo bar git restore .'
check_deny_msg "checkpoint" "(em51) mode: git status; sudo -u git rm -rf src/x" 'git status; sudo -u git rm -rf src/x'
check_deny_msg "checkpoint" "(em52) mode: git log; env git mv a b; rm -rf src/x" 'git log; env git mv a b; rm -rf src/x'

# (bd) T-00001090 : `git branch -D wt/*` — chaque graphie que git accepte (mesuré, git 2.55) ; contrôles verts avant et après.
check_deny_msg "git branch -D" "(bd1) git branch -D wt/T-00001090" 'git branch -D wt/T-00001090'
check_deny_msg "git branch -D" "(bd2) git branch -d -f wt/T-1" 'git branch -d -f wt/T-1'
check_deny_msg "git branch -D" "(bd3) git branch -df wt/T-1" 'git branch -df wt/T-1'
check_deny_msg "git branch -D" "(bd4) git branch -fd wt/T-1" 'git branch -fd wt/T-1'
check_deny_msg "git branch -D" "(bd5) git branch --delete --force wt/T-1" 'git branch --delete --force wt/T-1'
check_deny_msg "git branch -D" "(bd6) git branch --del --forc wt/T-1" 'git branch --del --forc wt/T-1'
check_deny_msg "git branch -D" "(bd7) git branch -f --delete wt/T-1" 'git branch -f --delete wt/T-1'
check_deny_msg "git branch -D" "(bd8) option après l'opérande" 'git branch wt/T-1 -D'
check_deny_msg "git branch -D" "(bd9) git branch -D -- wt/T-1" 'git branch -D -- wt/T-1'
check_deny_msg "git branch -D" "(bd10) casse (APFS)" 'git branch -D WT/T-1'
check_deny_msg "git branch -D" "(bd11) git branch -D 'wt/T-1'" 'git branch -D '"'"'wt/T-1'"'"''
check_deny_msg "git branch -D" "(bd12) grappe" 'git branch -Dq wt/T-1'
check_deny_msg "git branch -D" "(bd13) un seul opérande wt/ suffit" 'git branch -D main wt/T-1'
check_deny_msg "git branch -D" "(bd14) expansion citée" 'git branch -D "$b"'
check_deny_msg "git branch -D" "(bd15) expansion non citée" 'git branch -D $b'
check_deny_msg "git branch -D" "(bd16) git -C /x branch -D wt/T-1" 'git -C /x branch -D wt/T-1'
check_deny_msg "git branch -D" "(bd17) enveloppe prouvée" 'env -u GIT_DIR git branch -D wt/T-1'
check_deny_msg "git branch -D" "(bd18) A-C3 antislash" 'git branch -D wt\/T-1'
check_deny_msg "git branch -D" "(bd19) A-C3 segment cité collé à droite" 'git branch -D "wt"/T-1'
check_deny_msg "git branch -D" "(bd20) A-C3 segment cité au milieu" 'git branch -D w"t"/T-1'
check_deny_msg "git branch -D" "(bd21) A-C3 segment cité collé à gauche" 'git branch -D wt/'"'"'T-1'"'"''
check_deny_msg "git branch -D" "(bd22) git branch -D wt/T-1" 'git branch -D "wt/T-1"'
check_deny_msg "git branch -D" "(bd23) enveloppe ambiguë" 'sudo -u $U git branch -D wt/T-1'
check_deny_msg "git branch -D" "(bd25) git branch --delete --no-force --force wt/T-1" 'git branch --delete --no-force --force wt/T-1'
check_deny_msg "git branch -D" "(bd26) --d abrège --delete" 'git branch --d --force wt/T-1'
check_deny_msg "git branch -D" "(bd27) deux opérandes" 'git branch -D wt/T-1 wt/T-2 && git status'
check_deny_msg "git branch -D" "(bd28) réserve (1) : substitution NON citée en opérande, comptée comme expansion" 'git branch -D $(cat f)'
check_deny_msg "git branch -D" "(bd29) réserve (1) : backtick en opérande" 'git branch -D `cat f`'
check_deny_msg "git branch -D" "(bd30) réserve (1) : la liste par substitution, graphie honnête du nettoyage en masse" 'git branch -D $(git branch --list '"'"'wt/*'"'"')'
# Binôme fournée 2 : `@{-1}` (la branche précédente, mesuré : supprime wt/T-1, rc 0) et un mot coupé par une accolade comptent wt/.
check_deny_msg "git branch -D" "(bd31) @{-1} : git résout la branche précédente" 'git branch -D @{-1}'
check_deny_msg "git branch -D" "(bd32) @{…} cité" 'git branch -D "@{-1}"'
check_deny_msg "git branch -D" "(bd33) développement d accolades" 'git branch -D {wt/T-1,x}'
check_deny_msg "(fail-closed false positive)" "(bd34) -D -r wt/x : faux positif NOMMÉ (--sort -r fait de -r une valeur)" 'git branch -D -r wt/T-1'
check_deny_msg "bounded, not closed." "(bd35) la liste Not covered se dit bornée, non close" 'git branch -D wt/T-1'
check_deny_msg "Not read, bounded and not closed" "(bd36) le refus d effacement nomme ses bornes" 'git reset --hard'
# (bd37)(bd38) faux positifs NOMMÉS (binôme bis fournée 2) : déjà refusés avant
# que le message les nomme, donc le motif est la phrase de leur clause, jamais
# « fail-closed false positive » que (bd34) porte déjà et qui resterait vert.
# Passe quater (L-00000187) : la clause décrit le MÉCANISME (arrêt au premier
# `{`/`}` hors guillemets), plus une énumération de formes ; motifs alignés.
check_deny_msg "one in a comment or a redirect target counts" "(bd37) faux positif NOMMÉ : accolade dans un commentaire" 'git branch -D feat-old # cleanup {x}'
# (bd38) BASCULÉ par T-01M5D6XS2S (étape 3) : la liste est développée
# (`-D feat-a feat-b`), aucune wt/ — le faux positif disparaît ; la phrase du
# faux positif reste vraie pour une coupe (`feat }`, `# {x}`), épinglée par (bd38b).
check_silent "(bd38) T-01M5D6XS2S : expansion d accolades d un nom non-wt, développée, laissée passer" 'git branch -D {feat-a,feat-b}'
check_deny_msg "a fail-closed false positive for a non-wt name" "(bd38b) faux positif NOMMÉ : une accolade de coupe après -D" 'git branch -D feat }'
# (bf) T-01M5GFV9CE : développer ne vaut que si l étage 1.5 lit le segment comme
# bash. Sur develop (lot T-01M5D6XS2S), ces formes passaient rc 0 : la liste
# développée effaçait la coupe `{` qui comptait wt/. Le segment non fiable est
# recopié tel qu écrit et l étage 2 s y coupe au `{`. Motif : la phrase de la
# règle au refus de la garde 7 (absente du hook d avant, donc rouge contre lui).
check_deny_msg "a character outside a closed set" "(bf1) {a,b} puis \\; wt/x" 'git branch -D {a,b} \; wt/x'
check_deny_msg "a character outside a closed set" "(bf2) {a,b} puis \\| wt/x" 'git branch -D {a,b} \| wt/x'
check_deny_msg "a character outside a closed set" "(bf3) {a,b} puis antislash-retour wt/x" $'git branch -D {a,b} \\\nwt/x'
check_deny_msg "a character outside a closed set" "(bf4) {a,b} puis <(echo) wt/x" 'git branch -D {a,b} <(echo) wt/x'
check_deny_msg "a character outside a closed set" "(bf5) {a,b} puis >(cat) wt/x" 'git branch -D {a,b} >(cat) wt/x'
check_deny_msg "a character outside a closed set" "(bf6) {a,b} puis w?/x" 'git branch -D {a,b} w?/x'
check_deny_msg "a character outside a closed set" "(bf7) {a,b} puis [w]t/x" 'git branch -D {a,b} [w]t/x'
check_deny_msg "a character outside a closed set" "(bf8) séquence de lettres hors [A-Za-z] : {V..a..6}wt/x" 'git branch -D {V..a..6}wt/x'
check_deny_msg "a character outside a closed set" "(bf9) {a,b} puis \"w antislash-retour t/x\" cité sur deux lignes" $'git branch -D {a,b} "w\\\nt/x"'
check_deny_msg "a character outside a closed set" "(bf10) faux positif NOMMÉ : + dans une séquence entière" 'git branch -D {+1..2}'
check_deny_msg "unscoped" "(bf11) la copie change @@ en _ : la table de END reste prouvée" 'echo {x,y} "a" *; git reset "--hard"'
# (bf12) la table passe par STDIN, jamais par l environnement ni argv : une
# charge de 1,1 Mo (construite par python, argv ne la porterait pas) reste jugée.
"$PY" -c 'import json, os, signal, subprocess, sys
cmd = "echo {a,b}; python3 -c \"x=" + chr(39) + "y" * 1100000 + chr(39) + "\"; git reset --hard"
p = subprocess.Popen(["bash", sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
try:
    err = p.communicate(json.dumps({"tool_input": {"command": cmd}}).encode(), timeout=60)[1]
    rc = p.returncode
except subprocess.TimeoutExpired:
    if hasattr(os, "killpg"):
        os.killpg(p.pid, signal.SIGKILL)
    else:
        p.kill()
    p.wait()
    rc, err = 99, b""
sys.exit(0 if rc == 2 and b"unscoped" in err else 1)' "$HOOK"
assert $? "(bf12) echo {a,b}; python3 -c 1.1 MB; git reset --hard : refused, exit 2, unscoped"
check_deny_msg "a character outside a closed set" "(bf13) {a,b} puis w*/x" 'git branch -D {a,b} w*/x'
check_deny_msg "a character outside a closed set" "(bf14) préfixe sudo recopié" 'sudo git branch -D {a,b} \; wt/x'
check_deny_msg "a character outside a closed set" "(bf15) préfixe then recopié" 'if true; then git branch -D {a,b} \; wt/x; fi'
check_silent "(bf1n) segment fiable : redirection" 'git branch -D {a,b} 2>/dev/null'
check_silent "(bf2n) segment fiable : commentaire" 'git branch -D {a,b} # done'
check_silent "(bf3n) segment fiable : citation entre apostrophes, table prouvée" 'git branch -D {a,b} '"'"'x y'"'"''
check_silent "(bf4n) seul le segment non fiable est recopié" 'echo {x,y} *; git branch -D {feat-a,feat-b}'
check_silent "(bf5n) la copie garde la table de END prouvée" 'echo {x,y} "a" *; git checkout -- "src/x"'
# (bf18)(bf6n) revue de clôture S-01M5HSF6QW (mutant M14) : l index des
# citations avance d un segment à l autre ; sinon la citation d un segment est
# jugée avec la ligne de table d un autre.
check_deny_msg "a character outside a closed set" "(bf18) index QB : citation d un autre segment" $'echo \'ok\'; git branch -D {a,b} "w\\\nt/x"'
check_silent "(bf6n) index QB : citation non fiable d un autre segment" 'echo "a(b)"; git branch -D {a,b} '"'"'x y'"'"''
# (bf7n)(bf8n) revue de clôture, T3 : la copie colle `_` à ses voisins ; un
# ` _ ` détaché laissait un pathspec `/` lu non scopé (develop rendait 0).
check_silent "(bf7n) copie : la citation reste collée à son pathspec (restore)" 'git restore "$d"/{a,b}.py'
check_silent "(bf8n) copie : la citation reste collée à son pathspec (checkout --)" 'git checkout -- "src (v2)"/{a,b}.py'
# (bf16) SAFE ne tient que les lettres ASCII : une lettre accentuée rend le segment non fiable.
check_deny_msg "ASCII letters" "(bf16) lettre hors ASCII dans le segment : refusé, la phrase dit ASCII" 'git branch -D {a,b} é'
# (bf17) coût BORNÉ du rattachement mot -> segment (passe de correction,
# exec-critic S-01M5HKSBBT) : 1100 mots d accolades (1024 développés, le
# plafond) et 200 000 segments, environ 400 Ko, contre le MÊME texte sans
# accolade, dans le même run. Les deux bras ALTERNENT (contrôle, accolades,
# trois fois : un pic de charge touche les deux) et chacun garde le minimum de
# ses trois mesures. Borne RELATIVE, comme (sc7c) : accolades < 2 x contrôle
# + 0,5 s. Mesuré en paires alternées (revue de clôture S-01M5HSF6QW, T4) :
# 1,52 s contre 1,24 s ; le balayage de tous les segments par mot (max sur
# enumerate, mutant Mcost) faisait 5,40 s contre 1,32 s, donc rouge.
"$PY" -c 'import json, subprocess, sys, time
def run(word):
    cmd = "echo " + word * 1100 + "x;" * 200000 + " git reset --hard"
    t = time.monotonic()
    p = subprocess.run(["bash", sys.argv[1]], input=json.dumps({"tool_input": {"command": cmd}}).encode(), capture_output=True, timeout=120)
    return time.monotonic() - t, p.returncode == 2 and b"unscoped" in p.stderr
pairs = [(run("a "), run("{a..a} ")) for _ in range(3)]
ctl = [p[0] for p in pairs]
brc = [p[1] for p in pairs]
c = min(x[0] for x in ctl)
b = min(x[0] for x in brc)
print("bf17: control %.2fs braces %.2fs" % (c, b))
sys.exit(0 if all(x[1] for x in ctl + brc) and b < 2 * c + 0.5 else 1)' "$HOOK"
assert $? "(bf17) 1100 brace words x 200000 segments: judged (exit 2, unscoped) in under 2x the same text without braces + 0.5 s"
check_deny_msg "passes unread" "(bd39) le trou d accolade est dit au refus (phrase épinglée)" 'git branch -D wt/T-1'
# (bd40) faux positif de CLAUDE SEUL (awk : bglue sur un segment cité collé à
# un mot) ; les jumeaux python lisent le mot à travers ses guillemets et laissent
# passer — DIVERGENCE 10 de test_guard_decision_parity.py.
check_deny_msg "glued to a quoted span" "(bd40) faux positif Claude seul : mot collé à un segment cité" 'git branch -D feat-"old"'
# (bd41)-(bd43) le mécanisme, forme par forme : l antislash ne protège pas
# l accolade, une cible de redirection non plus, et -d avec -f lu avant la coupe suffit.
check_deny_msg "git branch -D" "(bd41) accolade derrière un antislash" 'git branch -D feat\{x\}'
check_deny_msg "git branch -D" "(bd42) accolade dans une cible de redirection" 'git branch -D feat >{x}'
check_deny_msg "git branch -D" "(bd43) -d puis -f lus avant la coupe" 'git branch -d -f feat {x}'
# (bd44)(bc28) l accolade d une expansion de paramètre n est PAS une coupe (le mot
# est lu comme expansion, -D après lui est lu) ; une accolade nue qui la suit, si.
check_deny_msg "git branch -D" "(bd44) expansion de paramètre puis -D : lu, refusé" 'git branch ${x} -D feat'
# (bd45)-(bd55) passe sexies de la fournée 2, TEXTE SEUL (aucune décision ne
# bouge ; les corrections sont celles de T-00001202) : une phrase nouvelle du
# refus = un témoin sur `git branch -D wt/T-1`. Chaque motif est ABSENT du hook
# de c9512cfc : rejoué contre lui (SAFE_BASH_HOOK), ce sont eux qui rougissent.
check_deny_msg "an unescaped newline" "(bd45) fin de commande : un retour NON échappé" 'git branch -D wt/T-1'
check_deny_msg "a backslash-newline is NOT joined" "(bd46) continuation antislash-retour non jointe, nommée" 'git branch -D wt/T-1'
check_deny_msg "gap carried by T-00001198" "(bd47) la continuation : son porteur au board" 'git branch -D wt/T-1'
check_deny_msg 'a `-D` read in a trailing comment' "(bd48) un -D de commentaire est lu, nommé" 'git branch -D wt/T-1'
check_deny_msg 'holds a `$` or a backtick, even one bash does not expand' "(bd49) ce que compte un dollar ou un backtick" 'git branch -D wt/T-1'
check_deny_msg 'ends at its first `}`: `${x:-{y}}` cuts there' "(bd50) une expansion de paramètre finit à sa première accolade fermante" 'git branch -D wt/T-1'
check_deny_msg "The delete option is not read as bash reads it" "(bd51) la lecture de l option, trou nommé" 'git branch -D wt/T-1'
check_deny_msg "gap carried by T-00001202" "(bd52) la lecture de l option : son porteur au board" 'git branch -D wt/T-1'
check_deny_msg 'once the command holds a literal `@@` anywhere' "(bd53) @@ littéral, faux positif Claude seul, nommé" 'git branch -D wt/T-1'
check_deny_msg 'even with a literal `@@` in the command' "(bd54) @@ littéral : l option citée reste non lue, nommé" 'git branch -D wt/T-1'
check_deny_msg "on the Codex and Gemini hosts only" "(bd55) option collée derrière une expansion citée : trou des seuls hôtes python" 'git branch -D wt/T-1'
# (bd56)-(bd62) les formes refusées que ces phrases nomment, telles que mesurées
# sur c9512cfc (décisions inchangées) : -D de commentaire, dollar jamais
# développé, @@ littéral (Claude seul), option collée derrière "$b" (Claude seul).
check_deny_msg 'a `-D` read in a trailing comment' "(bd56) -D dans un commentaire, lu" 'git branch wt/x # -D'
check_deny_msg 'holds a `$` or a backtick' "(bd57) dollar entre apostrophes" 'git branch -D '"'"'$b'"'"''
check_deny_msg 'holds a `$` or a backtick' "(bd58) dollar échappé" 'git branch -D \$b'
check_deny_msg 'holds a `$` or a backtick' "(bd59) dollar dans un commentaire" 'git branch -D feat # $HOME'
check_deny_msg 'once the command holds a literal `@@` anywhere' "(bd60) Claude seul : @@ littéral parmi les mots" 'git branch -D feat # @@'
check_deny_msg 'once the command holds a literal `@@` anywhere' "(bd61) Claude seul : @@ ailleurs, mot cité compté" 'echo @@; git branch -D '"'"'feat'"'"''
check_deny_msg "on the Codex and Gemini hosts only" "(bd62) Claude seul : option collée derrière une expansion citée, lue" 'git branch "$b"-D wt/T-1'
check_silent "(bc1) control: git branch -d wt/T-1" 'git branch -d wt/T-1'
check_silent "(bc2) control: git branch -D worktree-agent-abc" 'git branch -D worktree-agent-abc'
check_silent "(bc3) control: git branch -D other" 'git branch -D other'
check_silent "(bc4) control: git branch --list 'wt/*'" 'git branch --list '"'"'wt/*'"'"''
check_silent "(bc5) control: git branch --delete --for wt/x" 'git branch --delete --for wt/x'
check_silent "(bc6) control: git branch -d wt/T-1 && git branch -a" 'git branch -d wt/T-1 && git branch -a'
check_silent "(bc7) control: git branch" 'git branch'
check_silent "(bc8) control: git branch -vv" 'git branch -vv'
check_silent "(bc9) control: git branch -m wt/old wt/new" 'git branch -m wt/old wt/new'
check_silent "(bc10) control: git branch wt/T-9" 'git branch wt/T-9'
check_silent "(bc11) control: git commit -m git branch -D wt/x" 'git commit -m "git branch -D wt/x"'
check_silent "(bc12) control: git branch -D foo/wt/x" 'git branch -D foo/wt/x'
check_silent "(bc13) control: git branch -d -r origin/wt/x" 'git branch -d -r origin/wt/x'
check_silent "(bc14) control: git branch --delete wt/T-1" 'git branch --delete wt/T-1'
check_silent "(bc15) control: git branch -a --list wt/*" 'git branch -a --list wt/*'
check_silent "(bc16) control (réserve (1)) : git branch -d par substitution, sans force" 'git branch -d $(cat f)'
check_silent "(bc17) control: git branch -d @{-1}, sans force" 'git branch -d @{-1}'
check_silent "(bc18) control: git stash drop stash@{0}" 'git stash drop stash@{0}'
check_silent "(bc19) control: git show HEAD@{1}" 'git show HEAD@{1}'
# (bc20) TROU NOMMÉ au refus, porté par T-00001196 : vert tant que la forme
# passe, rouge le jour où elle est lue (le message doit alors la retirer).
# (bc20)-(bc22) BASCULÉS par T-01M5D6XS2S (étape 3) : une liste d accolades est
# développée comme bash la développe avant que la garde lise les mots, et le
# message ne les nomme plus comme trous ; (bc23) reste un trou (`{x}` n est
# pas une liste, la coupe y est gardée — annexe C12).
check_deny_msg "git branch -D" "(bc20) T-01M5D6XS2S : option derrière une accolade, développée et lue" 'git branch {-D,} wt/T-1'
check_deny_msg "git branch -D" "(bc21) T-01M5D6XS2S : option coupée par l accolade, développée et lue" 'git branch -{D,} wt/T-1'
check_deny_msg "git branch -D" "(bc22) T-01M5D6XS2S : accolade avant l option, développée et lue" 'git branch {x,} -D wt/T-1'
check_silent "(bc23) trou NOMMÉ : wt/ lu, option après l accolade, non lue" 'git branch wt/T-1 {x} -D'
# (bc24)-(bc27) les bornes du mécanisme : une accolade citée n est pas lue, une
# accolade après la fin de la commande (séparateur, `)` fermante) non plus, et une
# moitié seule de la suppression forcée lue avant la coupe ne suffit pas.
check_silent "(bc24) accolade citée, non lue" 'git branch -D "feat{x}"'
check_silent "(bc25) accolade après && : commande suivante" 'git branch -D feat && echo {x}'
check_silent "(bc26) -d seul lu avant la coupe" 'git branch -d feat {--force,}'
check_silent "(bc27) accolade après la ) fermante d un sous-shell" '(git branch -D feat)>{x}'
check_silent "(bc28) accolade nue après une expansion de paramètre : coupe, -D non lu" 'git branch ${x}{y} -D feat'
# (bc29)-(bc41) TROUS NOMMÉS au refus par la passe sexies, mesurés sur c9512cfc
# (bash efface la wt/ dans chacune) : verts tant que la forme passe, rouges le
# jour où T-00001198, T-00001196 ou T-00001202 la lit — le message doit alors
# la retirer. Ils ne rougissent PAS contre la base : ils épinglent une décision.
check_silent "(bc29) T-00001198 : antislash-retour avant l opérande" "$(printf 'git branch -D \\\nwt/T-1')"
check_silent "(bc30) T-00001198 : antislash-retour avant l accolade" "$(printf 'git branch -D feat \\\n{wt/x,y}')"
check_silent "(bc31) T-00001196 : l expansion de paramètre finit à sa première accolade fermante" 'git branch ${x:-{y}} -D wt/T-1'
check_silent "(bc32) T-00001202, Claude seul : option citée" 'git branch '"'"'-D'"'"' wt/T-1'
check_silent "(bc33) T-00001202, Claude seul : option citée, @@ littéral" 'git branch '"'"'-D'"'"' wt/T-1 # @@'
check_silent "(bc34) T-00001202, Claude seul : option collée à un segment cité" 'git branch -"D" wt/T-1'
check_silent "(bc35) T-00001202, Claude seul : force citée" 'git branch -d '"'"'-f'"'"' wt/T-1'
check_silent "(bc36) T-00001202, Claude seul : option derrière un antislash" 'git branch \-D wt/T-1'
# (bc37) BASCULÉ par T-01M5D6XS2S (étape 1) : une citation ANSI-C entière est
# décodée comme bash la décode, donc l option est lue et la wt/ protégée ; le
# message ne nomme plus cette forme comme un trou de l hôte Claude.
check_deny_msg "git branch -D" "(bc37) T-01M5D6XS2S : option en dollar-apostrophe, décodée et lue" 'git branch $'"'"'-D'"'"' wt/T-1'
check_silent "(bc38) T-00001202 : option collée derrière une expansion" 'git branch $b-D wt/T-1'
check_silent "(bc39) T-00001202 : option collée derrière une expansion entre accolades" 'git branch ${b}-D wt/T-1'
check_silent "(bc40) T-00001202 : -- pris pour valeur de --sort" 'git branch --sort -- -D wt/T-1'
check_silent "(bc41) T-00001202 : -- pris pour valeur de --format" 'git branch --format -- -D wt/T-1'

# =============================================================================
# (z) T-00000784 — L'ÉTAGE REDIRECTION PLANTÉ, PYTHON PRÉSENT, REFUSE (exit 2).
#   Décisions pilote S-00002848 (refuser toute redirection tant que l'étage est
#   planté ; message clair ; réparation dans le message ET dans la doc) et
#   S-00002849 (deux parcours, équipe du kit / adoptant par uv ; les verbes
#   `cadre` sont RÉSERVÉS, jamais cités comme une commande existante). Avant ce
#   correctif, un étage redirection qui plantait (rc non nul, ou rc 0 sans rien
#   imprimer) prenait degraded() : exit 0, et une écriture vers un fichier suivi
#   ou protégé partait sans que rien ne la juge. L'ABSENCE de python reste la
#   posture dégradée (z10) : c'est la PANNE d'un juge présent qui refuse, jamais
#   son absence.
#   Cales sur le modèle de (n5)/(s6), clé `load_protected` — deux occurrences,
#   toutes deux dans le SEUL programme de l'étage redirection (relevé à HEAD et à
#   347889ea) :
#     REDSTUB  — le programme de l'étage sort 9 (un plantage) ;
#     REDEMPTY — il avale son entrée et sort 0 sans rien imprimer (sortie muette).
#   NON-VACUITÉ MESURÉE contre les copies `git show 347889ea:` de safe-bash.sh ET
#   de protect-paths.sh côte à côte (SAFE_BASH_HOOK), section entière avec la
#   passe 4 : 380 passed, 42 failed. ROUGES : (z1)(z2)(z3), (z4a)-(z4j), (z5),
#   (z6)(z6b)(z6b2), (z7a)-(z7c), (z9a)(z9), (z11b) — les arms z1, z2, z3, z4,
#   z5, z6, z6b, z7, z9, z9a du plan plus (z11b), 23 lignes à la passe 1
#   (376/23) — puis (z12)-(z19), (z18b), (z21), (z22), (z23)(z23b), (z24)(z24b),
#   (z25)(z25b), (z26-3.11)(z26-3.12). VERTS : les CONTRÔLES (z8)(z8b)(z8b2)
#   (z10)(z11)(z20-ctl)(z20)(z20b), (z26) sous le python par défaut (3.14, dont
#   `Path.resolve()` ne lève pas sur une boucle), et les 371 arms antérieurs.
#   Après les quatre passes : 422 passed, 0 failed.
# =============================================================================
REDSTUB="$EVTMP/redirfail"; mkdir -p "$REDSTUB"
REDEMPTY="$EVTMP/redirempty"; mkdir -p "$REDEMPTY"
for c in python3 python py; do
  cat > "$REDSTUB/$c" <<EOSTUB3
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *load_protected*) exit 9;;
esac
exec "$REAL_PY" "\$@"
EOSTUB3
  cat > "$REDEMPTY/$c" <<EOSTUB4
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *load_protected*) cat >/dev/null; exit 0;;
esac
exec "$REAL_PY" "\$@"
EOSTUB4
  chmod +x "$REDSTUB/$c" "$REDEMPTY/$c"
done
# LE MOTIF DE LA SECTION est la première ligne du refus, PROPRE à
# redirect_stage_down — jamais le seul nom de règle : le message de la garde 4
# cite lui aussi `(rule redirect-stage-broken)` (sa phrase sur l'étage planté),
# donc un refus de la garde 4 satisferait un motif réduit au nom (mesuré, passe
# 2 : (z18) vert à tort sur e69aa011, (z20) rouge à tort).
Z_MOTIVE='BLOCKED: safe-bash — the redirect stage crashed'

# check_deny_msg_path <PATH> <motif> <label> <command-string> — check_deny_msg
# sous un PATH imposé (la cale). Le MOTIF est asserté, pas seulement le rc 2 :
# `rm -rf AGENTS.md` est AUSSI refusé par la garde rm/mv, donc un mutant qui
# ignorerait le plantage resterait vert sur le seul code de sortie.
check_deny_msg_path() {
  forced_path="$1"; motive="$2"; label="$3"; cmd="$4"
  payload="$(json_payload "$cmd")"
  printf '%s' "$payload" | PATH="$forced_path" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  got=$?
  msg="$(cat "$ERRF")"
  case "$msg" in
    *"$motive"*) if [ "$got" -eq 2 ]; then PASS=$((PASS+1)); echo "PASS: $label"; return; fi;;
  esac
  FAIL=$((FAIL+1))
  echo "FAIL: $label (expected exit 2 carrying <$motive>, got $got) cmd=<$cmd> stderr=<$(tr '\n' ' ' < "$ERRF")>"
}

# (z1)-(z3) : toute commande portant un `>` hors guillemets est refusée par la
# règle de l'étage — une écriture gardée (z1)(z2) comme une duplication de
# descripteur (z3, coût ACCEPTÉ par le pilote et épinglé ici pour être mesuré).
check_deny_msg_path "$REDSTUB:$PATH" "$Z_MOTIVE" \
  "(z1) redirect stage down: rm -rf AGENTS.md 2>/dev/null refused by the stage rule" 'rm -rf AGENTS.md 2>/dev/null'
check_deny_msg_path "$REDSTUB:$PATH" "$Z_MOTIVE" \
  "(z2) redirect stage down: a write to an arming marker refused" 'echo x > .agents/state/gates/KICKOFF_REQUIRED'
check_deny_msg_path "$REDSTUB:$PATH" "$Z_MOTIVE" \
  "(z3) redirect stage down: ls 2>&1 refused too (accepted cost, S-00002848)" 'ls 2>&1'

# (z4) LE MESSAGE. Capturé une fois, sur une cible HORS dépôt qui passe
# d'ordinaire ((t6)) : le refus ne vient donc QUE de la panne. Chaque sous-assert
# exige d'abord le refus redirect-stage-broken (rc 2 + la première ligne propre
# $Z_MOTIVE + le nom de règle), sinon un stderr vide ou dégradé satisferait les
# asserts d'absence.
Z_PROBE_PROG='import os, re, sys, subprocess, posixpath; from pathlib import Path; print("stdlib ok")'
Z_DOLLAR='  $ '
Z4_ERRF="$EVTMP/z4.stderr"
printf '%s' "$(json_payload 'echo x > /tmp/z784-z4')" | PATH="$REDSTUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$Z4_ERRF"
Z4_RC=$?
Z4_ERR="$(cat "$Z4_ERRF")"; Z4_OUT="$(cat "$OUTF")"
z4_is_refusal() {
  [ "$Z4_RC" -eq 2 ] || return 1
  case "$Z4_ERR" in
    *"$Z_MOTIVE"*"(rule redirect-stage-broken)"*) return 0;;
  esac
  return 1
}
z4_has() { # z4_has <sous-chaîne> — 0 si le refus porte la sous-chaîne
  z4_is_refusal || return 1
  case "$Z4_ERR" in
    *"$1"*) return 0;;
  esac
  return 1
}
z4_line() { # z4_line <ligne exacte> — 0 si le refus porte cette LIGNE entière
  z4_is_refusal || return 1
  grep -Fxq -- "$1" "$Z4_ERRF"
}
if z4_has "the redirect stage crashed"; then r=0; else r=1; fi
assert "$r" "(z4a) the refusal names the crashed redirect stage (rc $Z4_RC)"
if z4_has "outside quotes and outside a quoted-delimiter heredoc body"; then r=0; else r=1; fi
assert "$r" "(z4b) the refusal states the > rule precisely (outside quotes and quoted-delimiter heredoc bodies)"
if z4_line "${Z_DOLLAR}git diff --stat HEAD -- .claude/hooks/safe-bash.sh .claude/hooks/protect-paths.sh"; then r=0; else r=1; fi
assert "$r" "(z4c) remedy line 1: git diff --stat of the stage and its sibling"
if z4_line "${Z_DOLLAR}git checkout HEAD -- .claude/hooks/safe-bash.sh"; then r=0; else r=1; fi
assert "$r" "(z4d) remedy line 2: restore safe-bash.sh from HEAD"
if z4_line "${Z_DOLLAR}git checkout HEAD -- .claude/hooks/protect-paths.sh"; then r=0; else r=1; fi
assert "$r" "(z4e) remedy line 3: restore protect-paths.sh from HEAD"
if z4_line "${Z_DOLLAR}git ls-files --error-unmatch .claude/hooks/safe-bash.sh"; then r=0; else r=1; fi
assert "$r" "(z4f) remedy line 4: git ls-files --error-unmatch tests that this copy is tracked"
# R3 : l'interpréteur est DÉVELOPPÉ, jamais un `$PY` littéral. Sous REDSTUB le
# garde résout `python3` — le premier shim du PATH, qui relaie au vrai
# interpréteur —, donc la ligne attendue est EXACTE.
if z4_line "${Z_DOLLAR}\"python3\" -c '$Z_PROBE_PROG'"; then r=0; else r=1; fi
assert "$r" "(z4g) remedy line 5: the stdlib probe with the RESOLVED interpreter (\"python3\"), never a literal \$PY"
if z4_has "RESERVED" && z4_has "not shipped" && ! printf '%s' "$Z4_ERR" | grep -Eq '[Pp]hase ?[0-9]'; then r=0; else r=1; fi
assert "$r" "(z4h) the adopter path calls the cadre verbs RESERVED, not shipped, and cites no phase number"
if z4_has "traceback printed above, if any, is the cause; none → run the probe below"; then r=0; else r=1; fi
assert "$r" "(z4i) the refusal points at the Python traceback first, the probe second (R4)"
# R6 : aucun motif d'une AUTRE règle — la matrice de parité assert ses rangs
# par ces sous-chaînes (test_guard_decision_parity.py, MOTIVE_*), donc un
# refus redirect-stage-broken qui en porterait une satisferait un rang d'une
# autre règle : un faux vert importé.
z4_motive_hits=""
for zm in "checkpoint" "redirects a write" "unscoped" "--output" "open-files-in-pager" \
  "come from a pipe" "where git reads its subcommand" "refusing catastrophic rm" \
  "does not resolve on this machine"; do
  case "$Z4_ERR" in
    *"$zm"*) z4_motive_hits="$z4_motive_hits <$zm>";;
  esac
done
if z4_is_refusal && [ -z "$z4_motive_hits" ]; then r=0; else r=1; fi
assert "$r" "(z4j) the refusal carries none of the other rules' MOTIVE_* substrings (hits:${z4_motive_hits:- none})"

# (z5) Un REFUS, pas une dégradation : rien sur stdout (pas de systemMessage)
# et aucun COVERAGE DEGRADED (précédent 119f81e5 ; la matrice de parité lève
# sur ce mot, test_guard_decision_parity.py).
if z4_is_refusal && [ -z "$Z4_OUT" ]; then
  case "$Z4_ERR$Z4_OUT" in
    *"COVERAGE DEGRADED"*) r=1;;
    *) r=0;;
  esac
else
  r=1
fi
assert "$r" "(z5) a refusal, not a degradation: empty stdout and no COVERAGE DEGRADED (stdout=<$Z4_OUT>)"

# (z6)(z6b) LA SECONDE BRANCHE : rc 0 mais RIEN imprimé sur une commande non
# vide. La cause dite est la sortie muette ; jamais « exited $ » ni un code
# vide interpolé (« exited  ») dans la PHRASE DE CAUSE — les lignes `  $ ` du
# corps, elles, sont légitimes.
check_deny_msg_path "$REDEMPTY:$PATH" "$Z_MOTIVE" \
  "(z6) redirect stage silent (rc 0, no output): echo x > README.md refused" 'echo x > README.md'
Z6_ERRF="$EVTMP/z6.stderr"; cp "$ERRF" "$Z6_ERRF"
Z_CAUSE='BLOCKED: safe-bash — the redirect stage crashed: '
z6_cause="$(grep -F -- "$Z_CAUSE" "$Z6_ERRF")"
z4_cause="$(grep -F -- "$Z_CAUSE" "$Z4_ERRF")"
case "$z6_cause" in
  *"printed nothing"*"silent exit"*) r=0;;
  *) r=1;;
esac
assert "$r" "(z6b) the silent-exit cause says 'printed nothing … silent exit' (cause=<$z6_cause>)"
if [ -n "$z6_cause" ] && [ -n "$z4_cause" ]; then
  case "$z6_cause$z4_cause" in
    *'exited $'*|*'exited  '*) r=1;;
    *) r=0;;
  esac
else
  r=1
fi
assert "$r" "(z6b2) neither cause phrase interpolates an empty or literal exit code (z4=<$z4_cause>)"

# (z7) LE CONTRAT T-00000018 : le refus est tracé `hook.deny` par empreinte
# (cmd_sha256, cmd_len), jamais `path` ni un fragment de la commande. Dossier
# d'événements PROPRE à l'arm : le dossier de la suite reçoit les refus des
# autres arms, son dernier enregistrement ne serait pas forcément celui-ci.
Z7_EV="$EVTMP/z7ev"; mkdir -p "$Z7_EV"
Z7_CMD='echo z784-distinct-marker > /tmp/z784-z7-target'
printf '%s' "$(json_payload "$Z7_CMD")" | AGENTS_EVENTS_DIR="$Z7_EV" PATH="$REDSTUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
Z7_REC="$("$PY" -c 'import glob, json, os, sys
recs = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl"))):
    for line in open(f, encoding="utf-8"):
        if line.strip():
            recs.append(line.strip())
print(recs[-1] if recs else "")' "$Z7_EV" 2>/dev/null)"
z7_check() { # z7_check <a|b|c> — une propriété de l'enregistrement, OK/KO
  "$PY" -c 'import json, sys
which, rec, cmd = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    r = json.loads(rec)
    d = r.get("data", {})
except Exception:
    print("KO"); sys.exit(0)
ok = r.get("kind") == "hook.deny" and d.get("guard") == "safe-bash" and d.get("rule") == "redirect-stage-broken"
if which == "b":
    sha = str(d.get("cmd_sha256", ""))
    ok = ok and len(sha) == 64 and all(ch in "0123456789abcdef" for ch in sha)
    try:
        ok = ok and int(d.get("cmd_len", -1)) == len(cmd)
    except Exception:
        ok = False
elif which == "c":
    ok = ok and "path" not in d and "z784-distinct-marker" not in rec and "z784-z7-target" not in rec
print("OK" if ok else "KO")' "$1" "$Z7_REC" "$Z7_CMD" 2>/dev/null
}
if [ "$(z7_check a)" = "OK" ]; then r=0; else r=1; fi
assert "$r" "(z7a) hook.deny guard=safe-bash rule=redirect-stage-broken is recorded (rec=<$Z7_REC>)"
if [ "$(z7_check b)" = "OK" ]; then r=0; else r=1; fi
assert "$r" "(z7b) the record carries cmd_sha256 (64 hex) and cmd_len = length of the command"
if [ "$(z7_check c)" = "OK" ]; then r=0; else r=1; fi
assert "$r" "(z7c) the record carries no path and no fragment of the command (T-00000018)"

# (z8)(z8b) LES CONTRÔLES : la panne ne mord que sur un `>` hors guillemets.
# Sans `>`, l'étage n'est même pas ouvert ; un `>` CITÉ est neutralisé par
# l'étage 1 (SCRUBBED) avant le test, donc il ne déclenche rien non plus.
check_silent_path "$REDSTUB:$PATH" "(z8) control: ls (no >) passes silently while the stage is down" 'ls'
check_silent_path "$REDSTUB:$PATH" "(z8b) control: echo \"a > b\" (quoted >) passes silently while the stage is down" 'echo "a > b"'
check_silent_path "$REDSTUB:$PATH" "(z8b2) control: git commit -m 'x > y' (quoted >) passes silently while the stage is down" "git commit -m 'x > y'"

# (z9a)(z9) LE REMÈDE NE S'AUTO-VERROUILLE PAS (R1). Les lignes `  $ ` sont LUES
# dans le stderr RÉEL capturé par (z4) — jamais recopiées ici —, comptées, puis
# rejouées chacune SOUS LA MÊME CALE : chacune doit passer en silence, sinon
# l'agent bloqué ne pourrait pas taper sa propre réparation. Une extraction
# VIDE est un échec, jamais un vert par zéro itération.
Z9_N=0; Z9_BAD=""
while IFS= read -r zl; do
  case "$zl" in
    "$Z_DOLLAR"*) ;;
    *) continue;;
  esac
  Z9_N=$((Z9_N+1))
  # `${zl#????}` retire EXACTEMENT les quatre caractères du préfixe `  $ `,
  # déjà vérifié par le case ci-dessus.
  zc="${zl#????}"
  printf '%s' "$(json_payload "$zc")" | PATH="$REDSTUB:$PATH" bash "$HOOK" >"$EVTMP/z9.out" 2>"$EVTMP/z9.err"
  zrc=$?
  znoise="$(tr -d '[:space:]' < "$EVTMP/z9.err")$(tr -d '[:space:]' < "$EVTMP/z9.out")"
  if [ "$zrc" -ne 0 ] || [ -n "$znoise" ]; then Z9_BAD="$Z9_BAD [rc=$zrc] $zc;"; fi
done < "$Z4_ERRF"
if [ "$Z9_N" -eq 5 ]; then r=0; else r=1; fi
assert "$r" "(z9a) the refusal carries EXACTLY 5 remedy lines prefixed '  \$ ' (got $Z9_N)"
if [ "$Z9_N" -gt 0 ] && [ -z "$Z9_BAD" ]; then r=0; else r=1; fi
assert "$r" "(z9) every remedy line read from the real stderr passes silently under the same stub (lines=$Z9_N bad=<$Z9_BAD>)"

# (z10) emprunte le shim « python absent » de la section (j), qui vit dans
# safe-bash.test.sh : recréé ici à l'identique (T-01M4WTYT8M). Un morceau ne lit
# jamais l'état qu'un autre a construit ; sans ces deux lignes, STUB est sans
# liaison sous `set -u` et (z10) rougit.
STUB="$EVTMP/nopy"; mkdir -p "$STUB"
for c in python3 python py; do printf '#!/bin/sh\nexit 127\n' > "$STUB/$c"; chmod +x "$STUB/$c"; done
# (z10) L'ABSENCE de python est INCHANGÉE : le shim (j) qui échoue à tout,
# une commande portant un `>` — exit 0 et COVERAGE DEGRADED, jamais le refus.
printf '%s' "$(json_payload 'echo x > README.md')" | PATH="$STUB:$PATH" bash "$HOOK" >"$OUTF" 2>"$ERRF"
Z10_RC=$?; Z10_ERR="$(cat "$ERRF")"
case "$Z10_ERR" in
  *"$Z_MOTIVE"*) r=1;;
  *"COVERAGE DEGRADED"*) if [ "$Z10_RC" -eq 0 ]; then r=0; else r=1; fi;;
  *) r=1;;
esac
assert "$r" "(z10) python ABSENT stays degraded: exit 0 + COVERAGE DEGRADED, never the stage refusal (got $Z10_RC)"

# (z11) NON-VACUITÉ DE LA SONDE, sans cale : sur un arbre sain elle imprime
# `stdlib ok` — sinon la ligne 5 du remède accuserait la stdlib à tort. Même
# programme que celui que (z4g) lit dans le refus. Le masquage qu'elle vise,
# mesuré (python 3.14.7) : un `pathlib.py` ORDINAIRE dans le cwd fait échouer
# la sonde par une ImportError BRUYANTE, rc 1 — c'est la branche rc non nul de
# l'étage, qui refuse aussi ; un `pathlib.py` qui fait lui-même `sys.exit(0)`
# la fait sortir 0 SANS la phrase — c'est la branche « exited 0 but printed
# nothing », mesurée par (z11b).
z11_out="$(cd "$CLAUDE_PROJECT_DIR" && "$REAL_PY" -c "$Z_PROBE_PROG" 2>&1)"
if [ "$z11_out" = "stdlib ok" ]; then r=0; else r=1; fi
assert "$r" "(z11) the stdlib probe prints 'stdlib ok' on a healthy tree (got <$z11_out>)"
# (z11b) LA SECONDE BRANCHE ATTEINTE SANS CALE : un module masquant qui sort 0
# lui-même, dans le cwd du garde. L'étage importe `pathlib`, le masque sort 0
# sans rien imprimer, donc refus « printed nothing ». Cible HORS dépôt ((t6)
# la laisse passer d'ordinaire). PYTHONSAFEPATH vidé : cette variable, si
# l'environnement la pose, retirerait le cwd de sys.path et l'arm mesurerait
# autre chose. T-00000789 (remède `-I`/`-P` au masquage) RETOURNERA cet arm, à
# dessein : le masque n'atteindra plus l'étage.
Z11B_DIR="$EVTMP/z11b-mask"; mkdir -p "$Z11B_DIR"
printf 'import sys\nsys.exit(0)\n' > "$Z11B_DIR/pathlib.py"
Z11B_PAYLOAD="$(json_payload 'echo x > /tmp/z784-z11b')"
(cd "$Z11B_DIR" && printf '%s' "$Z11B_PAYLOAD" | PYTHONSAFEPATH='' bash "$HOOK" >"$OUTF" 2>"$ERRF")
Z11B_RC=$?; Z11B_ERR="$(cat "$ERRF")"
case "$Z11B_ERR" in
  *"$Z_MOTIVE"*"printed nothing"*)
    if [ "$Z11B_RC" -eq 2 ]; then r=0; else r=1; fi;;
  *) r=1;;
esac
assert "$r" "(z11b) a shadowing module that exits 0 itself reaches the silent-exit branch: refused (got $Z11B_RC)"

# =============================================================================
# (z12)-(z22) T-00000784, PASSE 2 — exec-critic NO_GO @ e69aa011, reproduit par
#   l'orchestrateur. Trois défauts de la passe 1, et les arms qui les tiennent :
#   (a) LA SENTINELLE N'ÉTAIT PAS VALIDÉE : toute première ligne autre que
#       `DEGRADED` se lisait `OK` — un module masquant qui IMPRIME puis sort 0
#       faisait passer `> KICKOFF_REQUIRED` rc 0, sans un mot (z16)(z17) ;
#   (b) LE BRUIT DÉCALAIT LA LECTURE : un `subprocess.py` qui imprime à l'import
#       faisait lire `debug` comme sentinelle et `OK` comme cible refusée — un
#       refus sous la mauvaise règle, avec une cible FABRIQUÉE `( (OK, ))` (z18),
#       et un bruit FINAL ajoutait lui aussi une cible (z19) ;
#   (c) L'ERREXIT HÉRITÉ : `REDIR=$(…); REDIR_RC=$?` sortait avec le code du juge
#       (9) sous un `set -e` venu de BASH_ENV ou de SHELLOPTS — ni 0 ni 2, donc
#       une erreur non bloquante (z12)(z13) ; un trap ERR ou EXIT hérité rendait
#       rc 0 (z14)(z15) ; les captures awk et rm/mv avaient la même forme
#       (z21)(z22).
#   (z20)(z20b) sont les CONTRÔLES de la grammaire fermée : une sortie en CRLF
#   (python en mode texte sous Windows) doit se lire comme en LF.
#   ROUGE D'ABORD, MESURÉ contre la copie de e69aa011 (SAFE_BASH_HOOK) : 402
#   passed, 11 failed — (z12)-(z19), (z18b), (z21), (z22) ; verts, les contrôles
#   (z20-ctl)(z20)(z20b) et les 399 arms de la passe 1. (z23)(z23b), ajoutés
#   ensuite, MESURÉS contre 10ed6894 (lecteur rm/mv non encore fermé) : 413
#   passed, 2 failed — eux deux, rc 0.
# =============================================================================
ZB_ERREXIT="$EVTMP/bashenv-errexit";   printf 'set -e\n' > "$ZB_ERREXIT"
ZB_ERRTRAP="$EVTMP/bashenv-errtrap";   printf 'trap "exit 0" ERR\n' > "$ZB_ERRTRAP"
ZB_EXITTRAP="$EVTMP/bashenv-exittrap"; printf 'trap "exit 0" EXIT\n' > "$ZB_EXITTRAP"
GARBSTUB="$EVTMP/redirgarbage"; TAILSTUB="$EVTMP/redirtail"; CRLFSTUB="$EVTMP/redircrlf"
RMMVSTUB="$EVTMP/rmmvfail"; AWKSTUB="$EVTMP/awkfail"
mkdir -p "$GARBSTUB" "$TAILSTUB" "$CRLFSTUB" "$RMMVSTUB" "$AWKSTUB"
for c in python3 python py; do
  cat > "$GARBSTUB/$c" <<EOSTUB5
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *load_protected*) cat >/dev/null; echo garbage; exit 0;;
esac
exec "$REAL_PY" "\$@"
EOSTUB5
  cat > "$TAILSTUB/$c" <<EOSTUB6
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *load_protected*) "$REAL_PY" "\$@"; rc=\$?; echo OK; exit \$rc;;
esac
exec "$REAL_PY" "\$@"
EOSTUB6
  cat > "$CRLFSTUB/$c" <<EOSTUB7
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *load_protected*) "$REAL_PY" "\$@" | awk '{ printf "%s\\r\\n", \$0 }'; exit 0;;
esac
exec "$REAL_PY" "\$@"
EOSTUB7
  cat > "$RMMVSTUB/$c" <<EOSTUB8
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *RMMV_REPO*) exit 9;;
esac
exec "$REAL_PY" "\$@"
EOSTUB8
  chmod +x "$GARBSTUB/$c" "$TAILSTUB/$c" "$CRLFSTUB/$c" "$RMMVSTUB/$c"
done
printf '#!/bin/sh\nexit 9\n' > "$AWKSTUB/awk"; chmod +x "$AWKSTUB/awk"

# z_run <command-string> [NAME=VALUE…] — joue le garde sous `env` (SHELLOPTS
# est en lecture seule dans le harnais : un préfixe d'affectation y échouerait),
# rc dans z_rc, stderr dans z_err.
z_run() {
  zr_payload="$(json_payload "$1")"; shift
  printf '%s' "$zr_payload" | env "$@" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  z_rc=$?
  z_err="$(cat "$ERRF")"
}
z_refused() { # z_refused <sous-chaîne> — 0 si rc 2 ET stderr porte la sous-chaîne
  [ "$z_rc" -eq 2 ] || return 1
  case "$z_err" in
    *"$1"*) return 0;;
  esac
  return 1
}

# (z12)(z13)(z14) L'ÉTAGE PLANTÉ SOUS UN ÉTAT DE SHELL HÉRITÉ refuse quand même.
z_run 'echo x > /tmp/z784-z12' PATH="$REDSTUB:$PATH" BASH_ENV="$ZB_ERREXIT"
if z_refused "$Z_MOTIVE"; then r=0; else r=1; fi
assert "$r" "(z12) errexit inherited through BASH_ENV: a crashed stage is still refused, rc 2 (got $z_rc)"
z_run 'echo x > /tmp/z784-z13' PATH="$REDSTUB:$PATH" SHELLOPTS=errexit
if z_refused "$Z_MOTIVE"; then r=0; else r=1; fi
assert "$r" "(z13) errexit inherited through SHELLOPTS: a crashed stage is still refused, rc 2 (got $z_rc)"
z_run 'echo x > /tmp/z784-z14' PATH="$REDSTUB:$PATH" BASH_ENV="$ZB_ERRTRAP"
if z_refused "$Z_MOTIVE"; then r=0; else r=1; fi
assert "$r" "(z14) an ERR trap inherited through BASH_ENV does not turn the crash into rc 0 (got $z_rc)"
# (z15) Un trap EXIT hérité réécrivait le code de sortie de TOUT refus : ici la
# garde 4 sur un fichier suivi, sans aucune panne.
z_run 'echo x > AGENTS.md' BASH_ENV="$ZB_EXITTRAP"
if z_refused "redirects a write"; then r=0; else r=1; fi
assert "$r" "(z15) an EXIT trap inherited through BASH_ENV does not rewrite a refusal into rc 0 (got $z_rc)"

# (z16)(z17) LA SENTINELLE EST UN ENSEMBLE FERMÉ {OK, DEGRADED}. (z16) sans cale,
# le cas reproduit : un `pathlib.py` qui imprime puis sort 0 dans le cwd du garde.
Z16_DIR="$EVTMP/z16-mask"; mkdir -p "$Z16_DIR"
printf 'import sys\nprint("hello from a scratch script")\nsys.exit(0)\n' > "$Z16_DIR/pathlib.py"
Z16_PAYLOAD="$(json_payload 'echo x > .agents/state/gates/KICKOFF_REQUIRED')"
(cd "$Z16_DIR" && printf '%s' "$Z16_PAYLOAD" | PYTHONSAFEPATH='' bash "$HOOK" >"$OUTF" 2>"$ERRF")
z_rc=$?; z_err="$(cat "$ERRF")"
if z_refused "$Z_MOTIVE" && z_refused "sentinel line is missing or malformed"; then r=0; else r=1; fi
assert "$r" "(z16) a shadowing module that PRINTS then exits 0: malformed sentinel, refused (got $z_rc)"
z_run 'echo x > .agents/state/gates/KICKOFF_REQUIRED' PATH="$GARBSTUB:$PATH"
if z_refused "$Z_MOTIVE" && z_refused "sentinel line is missing or malformed"; then r=0; else r=1; fi
assert "$r" "(z17) a judge that prints garbage and exits 0: malformed sentinel, refused (got $z_rc)"

# (z18) LE BRUIT À L'IMPORT : jamais une cible fabriquée, jamais la mauvaise
# règle. Les deux asserts NÉGATIFS tiennent le demi-correctif qui refuserait
# bien mais listerait AUSSI le déchet sous redirect-write-guarded.
Z18_DIR="$EVTMP/z18-mask"; mkdir -p "$Z18_DIR"
printf 'print("debug")\n' > "$Z18_DIR/subprocess.py"
Z18_PAYLOAD="$(json_payload 'echo x > AGENTS.md')"
(cd "$Z18_DIR" && printf '%s' "$Z18_PAYLOAD" | PYTHONSAFEPATH='' bash "$HOOK" >"$OUTF" 2>"$ERRF")
z_rc=$?; z_err="$(cat "$ERRF")"
if z_refused "$Z_MOTIVE"; then r=0; else r=1; fi
assert "$r" "(z18) a module that prints at import: refused as redirect-stage-broken (got $z_rc)"
case "$z_err" in
  *"(OK, "*|*"redirects a write"*) r=1;;
  *) if [ "$z_rc" -eq 2 ]; then r=0; else r=1; fi;;
esac
assert "$r" "(z18b) ... and never a fabricated target nor the redirect-write-guarded rule"

# (z19) LE BRUIT FINAL (un `print` à la sortie) sur une cible BÉNIGNE : le bruit
# seul fait passer d'un laisser-passer à un refus, jamais l'inverse.
z_run 'echo x > /tmp/z784-z19' PATH="$TAILSTUB:$PATH"
if z_refused "$Z_MOTIVE" && z_refused "outside its output grammar"; then r=0; else r=1; fi
assert "$r" "(z19) a stray line AFTER the judge's own output: outside the grammar, refused (got $z_rc)"

# (z20)(z20b) CONTRÔLES CRLF. Non-vacuité de la cale d'abord : ses lignes
# finissent VRAIMENT par un retour chariot.
Z_CR="$(printf '\r')"
z20_probe="$(printf '' | "$CRLFSTUB/python3" -c 'print("load_protected")')"
case "$z20_probe" in
  *"$Z_CR") r=0;;
  *) r=1;;
esac
assert "$r" "(z20-ctl) the CRLF stub really terminates its lines with CR"
z_run 'echo x > AGENTS.md' PATH="$CRLFSTUB:$PATH"
if z_refused "redirects a write"; then
  case "$z_err" in
    *"$Z_MOTIVE"*) r=1;;
    *) r=0;;
  esac
else
  r=1
fi
assert "$r" "(z20) control: CRLF output still judged — a tracked target refused by guard 4, never as a crash (got $z_rc)"
check_silent_path "$CRLFSTUB:$PATH" "(z20b) control: CRLF output, a target outside the repository passes silently" 'echo x > /tmp/z784-z20b'

# (z21) La passe rm/mv PLANTÉE sous errexit hérité garde son refus propre
# (fail-closed, T-00000762) au lieu de sortir 9 — `rm -rf src/x` partait.
z_run 'rm -rf src/x' PATH="$RMMVSTUB:$PATH" BASH_ENV="$ZB_ERREXIT"
if z_refused "per-operand pass did not answer (exit 9"; then r=0; else r=1; fi
assert "$r" "(z21) errexit inherited: a crashed rm/mv pass still refuses with its own reason (got $z_rc)"
# (z22) L'étage awk PLANTÉ sous errexit hérité garde sa posture CONÇUE —
# annoncé, exit 0 — au lieu d'un rc 9 muet. Ce n'est PAS un refus neuf : T-784
# ne fait refuser que l'étage redirection ; l'asymétrie est la portée décidée.
z_run 'ls' PATH="$AWKSTUB:$PATH" BASH_ENV="$ZB_ERREXIT"
case "$z_err" in
  *"COVERAGE DEGRADED"*"recognition stage (awk) failed"*) if [ "$z_rc" -eq 0 ]; then r=0; else r=1; fi;;
  *) r=1;;
esac
assert "$r" "(z22) errexit inherited: a crashed awk stage stays ANNOUNCED with exit 0, not a silent rc 9 (got $z_rc)"

# (z23)(z23b) LA MÊME CLASSE QUE (z19), SUR LA PASSE rm/mv — relevée pendant la
# passe 2, dans le même fichier : son lecteur gardait le DERNIER état lu, donc
# une ligne `OK` parasite APRÈS ses lignes DENY (un module masquant qui imprime
# à la sortie de l'interpréteur) faisait passer `rm -rf src/x` rc 0, sans un mot
# (mesuré sur 10ed6894). Sa sortie est désormais une grammaire fermée elle
# aussi : `OK` ou `NONE` SEULS, ou des lignes `DENY` ; tout le reste refuse,
# sous le motif fail-closed de la passe. (z23b) : un bruit sur une passe qui
# laisserait passer AJOUTE un refus — jamais l'inverse.
RMTAILSTUB="$EVTMP/rmmvtail"; mkdir -p "$RMTAILSTUB"
for c in python3 python py; do
  cat > "$RMTAILSTUB/$c" <<EOSTUB9
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *RMMV_REPO*) "$REAL_PY" "\$@"; rc=\$?; echo OK; exit \$rc;;
esac
exec "$REAL_PY" "\$@"
EOSTUB9
  chmod +x "$RMTAILSTUB/$c"
done
z_run 'rm -rf src/x' PATH="$RMTAILSTUB:$PATH"
if z_refused "per-operand pass did not answer"; then r=0; else r=1; fi
assert "$r" "(z23) a stray OK after the rm/mv pass's DENY lines never turns the refusal into a pass (got $z_rc)"
z_run 'rm -rf /tmp/z784-z23b' PATH="$RMTAILSTUB:$PATH"
if z_refused "per-operand pass did not answer"; then r=0; else r=1; fi
assert "$r" "(z23b) a stray line after an rm/mv pass that would allow: outside the grammar, refused (got $z_rc)"

# =============================================================================
# (z24)-(z25) T-00000784, PASSE 3 — exec-critic GO_AVEC_RESERVES @ a342b9bd.
# (z24)(z24b) LA PASSE rm/mv EN CRLF (python en mode texte sous Windows). Le
#   retrait du retour chariot de la passe 2 LAISSE PASSER ce qui était refusé à
#   tort : sans lui, `OK\r` se lisait « pas de sentinelle », donc toute commande
#   rm/mv reconnue était refusée sous Windows, liste blanche comprise. Voulu, et
#   épinglé ici dans les deux sens : (z24) la liste blanche passe, (z24b) un
#   opérande hors liste reste refusé PAR OPÉRANDE, son chemin lu sans `\r`.
#   Rouges contre 10ed6894 (lecteur rm/mv sans retrait), verts depuis ef7ea035 :
#   MESURÉ, 413 passed, 6 failed sur 10ed6894 — (z23)(z23b)(z24)(z24b)(z25)
#   (z25b) ; 417 passed, 2 failed sur a342b9bd — (z25)(z25b), rc 0.
# (z25)(z25b) `REDIR` N'ÉTAIT PAS INITIALISÉ avant le `case` qui le pose à
#   `__SKIP__` : exporté par l'environnement, `REDIR=__SKIP__` sautait tout
#   l'étage redirection — un marqueur d'armement et un fichier suivi passaient
#   rc 0 (mesuré sur a342b9bd, et déjà à 347889ea).
# =============================================================================
RMCRLFSTUB="$EVTMP/rmmvcrlf"; mkdir -p "$RMCRLFSTUB"
for c in python3 python py; do
  cat > "$RMCRLFSTUB/$c" <<EOSTUB10
#!/bin/sh
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
case "\$*" in
  *RMMV_REPO*) "$REAL_PY" "\$@" | awk '{ printf "%s\\r\\n", \$0 }'; exit 0;;
esac
exec "$REAL_PY" "\$@"
EOSTUB10
  chmod +x "$RMCRLFSTUB/$c"
done
check_silent_path "$RMCRLFSTUB:$PATH" "(z24) rm/mv pass in CRLF: an allowlisted operand passes silently" 'rm -rf /tmp/z784-z24'
z_run 'rm -rf src/x' PATH="$RMCRLFSTUB:$PATH"
if z_refused "src/x (outside)"; then
  case "$z_err" in
    *"did not answer"*) r=1;;
    *) r=0;;
  esac
else
  r=1
fi
assert "$r" "(z24b) rm/mv pass in CRLF: an operand outside the list is still refused by operand, path read without CR (got $z_rc)"
z_run 'echo x > .agents/state/gates/KICKOFF_REQUIRED' REDIR=__SKIP__
if z_refused "redirects a write"; then r=0; else r=1; fi
assert "$r" "(z25) REDIR=__SKIP__ exported by the environment no longer skips the redirect stage: arming marker refused (got $z_rc)"
z_run 'echo x > AGENTS.md' REDIR=__SKIP__
if z_refused "redirects a write"; then r=0; else r=1; fi
assert "$r" "(z25b) REDIR=__SKIP__ exported: a tracked target is still refused (got $z_rc)"

# (z26) T-00000784, PASSE 4 — binôme de clôture @ 33761009, F1 (critic-opus),
#   reproduit par l'orchestrateur. `normalize()` n'attrapait que `OSError` ; sous
#   CPython <= 3.12, `Path.resolve()` lève `RuntimeError` sur une boucle de liens
#   (mesuré : 3.9, 3.11, 3.12 lèvent ; 3.13, 3.14 non ; `os.path.realpath` ne lève
#   sur aucune). Le juge plantait donc pour CETTE commande, et le refus affirmait
#   une panne durable. Dépôt JETABLE (racine du garde), `ln -s loop loop`,
#   `echo x > loop` : laissé passer en silence, jamais `redirect-stage-broken`,
#   sous le python par défaut ET sous 3.11 / 3.12 quand ils sont trouvés
#   (`uv python find`, repli `python3.X` ; version VÉRIFIÉE avant de jouer,
#   sinon SKIP-BOUND annoncé — jamais un vert par défaut). Rouge sous 3.11 et
#   3.12 sur 33761009, vert sous 3.14 dès avant le correctif : MESURÉ, 420
#   passed, 2 failed — (z26-3.11)(z26-3.12), rc 2, traceback pathlib.
Z26_REPO="$EVTMP/z26-repo"; mkdir -p "$Z26_REPO"
git -C "$Z26_REPO" init -q >/dev/null 2>&1
ln -s loop "$Z26_REPO/loop"
Z26_PAYLOAD="$(json_payload 'echo x > loop')"
z26_play() { # z26_play <label> <PATH>
  printf '%s' "$Z26_PAYLOAD" | CLAUDE_PROJECT_DIR="$Z26_REPO" PATH="$2" bash "$HOOK" >"$OUTF" 2>"$ERRF"
  z26_rc=$?
  z26_noise="$(tr -d '[:space:]' < "$ERRF")$(tr -d '[:space:]' < "$OUTF")"
  if [ "$z26_rc" -eq 0 ] && [ -z "$z26_noise" ]; then r=0; else r=1; fi
  assert "$r" "$1 (got $z26_rc, stderr=<$(tr '\n' ' ' < "$ERRF" | cut -c1-160)>)"
}
z26_play "(z26) symlink-loop target under the default python: allowed silently, never redirect-stage-broken" "$PATH"
for z26_v in 3.11 3.12; do
  z26_py=""
  if command -v uv >/dev/null 2>&1; then
    z26_py="$(uv python find "$z26_v" 2>/dev/null)" || z26_py=""
  fi
  if [ -z "$z26_py" ] && command -v "python$z26_v" >/dev/null 2>&1; then
    z26_py="$(command -v "python$z26_v")"
  fi
  z26_got=""
  if [ -n "$z26_py" ]; then
    z26_got="$("$z26_py" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
  fi
  if [ "$z26_got" != "$z26_v" ]; then
    echo "SKIP-BOUND: (z26-$z26_v) no CPython $z26_v found (uv python find, python$z26_v) — the symlink-loop arm is NOT measured under $z26_v on this machine."
    continue
  fi
  z26_dir="$EVTMP/z26-py$z26_v"; mkdir -p "$z26_dir"
  ln -sf "$z26_py" "$z26_dir/python3"; ln -sf "$z26_py" "$z26_dir/python"
  z26_play "(z26-$z26_v) symlink-loop target under CPython $z26_v: allowed silently, never redirect-stage-broken" "$z26_dir:$PATH"
done

# (z27) La marche `dq_open_at` de la table REPREND où l appel précédent s est arrêté
# (revue de sécurité de l intégration, M1 : coût quadratique). Témoins de la REPRISE :
# deux substitutions citées dans une même commande, et une après un `;`. Mutant
# `stack, i = [""], etat["i"]` (reprendre l offset sans la pile) : z27 et z27b rougissent
# (mesuré par la revue de clôture) ; z27c tient le refus d une substitution NON citée.
check 0 "(z27) resumed dq walk: two quoted substitutions pass" 'git commit -m "$(date)" -m "$(date)"'
check 0 "(z27b) resumed dq walk across ;" 'echo "$(true)"; git commit -m "$(date)"'
check 2 "(z27c) quoted then UNQUOTED substitution refused" 'git commit -m "$(date)" $(echo --no-verify)'

echo "----------------------------------------"
echo "safe-bash-em-z.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
