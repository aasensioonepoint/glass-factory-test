#!/usr/bin/env bash
# requires: git
# Banc du MODE PARALLELE de core-scripts/run-bash-tests.sh (T-00001122).
#
# Suite DECOUVERTE a part (`*.test.sh`) : le banc existant `run-bash-tests.test.sh` prouve l'ancien contrat
# sur le chemin SERIE, epingle (CADRE_GATE_JOBS=1, binome 7+8 F8 : sa forme dependait des coeurs) ; celui-ci
# ne couvre que ce que le mode parallele AJOUTE, et P12 prouve le meme bloc de resume dans les deux modes. Chaque cas bati un arbre factice portant une COPIE du runner (il resout
# sa racine depuis son propre dossier), joue le chemin parallele, et compare au chemin serie. Les DEFAUTS de
# production (jobs derives des coeurs, ordre par taille) sont joues SANS aucun CADRE_GATE_* (P13d-f, P21).
# Hors de ce banc : Git Bash (auto = 1, NON mesure), le conteneur, un runner CI, l'arbre reel.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RUNNER="$ROOT/core-scripts/run-bash-tests.sh"
[ -f "$ROOT/.agents/bin/kit-portable.sh" ] && . "$ROOT/.agents/bin/kit-portable.sh"
[ -f "$RUNNER" ] || { echo "KO: runner absent ($RUNNER)"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

SEL="${RBT_PAR_ARMS:-}"   # vide = TOUS les cas ; "P12 P16" = ceux-la seulement (ergonomie des mutants — la porte joue tout)
want() {
  [ -z "$SEL" ] && return 0
  local w
  for w in "$@"; do
    case " $SEL " in
      *" $w "*) return 0 ;;
    esac
  done
  return 1
}
[ -z "$SEL" ] || echo "SKIP: RBT_PAR_ARMS=« $SEL » — sous-ensemble des cas, ce vert n'est PAS la couverture complete"

make_tree() {  # make_tree <nom> -> chemin ; copie du runner
  local tree="$TMP/$1"
  mkdir -p "$tree/core-scripts"
  cp "$RUNNER" "$tree/core-scripts/run-bash-tests.sh"
  echo "$tree"
}
make_suite() {  # make_suite <chemin> [pass|fail|skip]
  mkdir -p "$(dirname "$1")"
  case "${2:-pass}" in
    fail) printf '#!/usr/bin/env bash\necho "fixture suite: deliberately red"\nexit 1\n' > "$1" ;;
    skip) printf '#!/usr/bin/env bash\necho "SKIP: nothing to prove here"\nexit 0\n' > "$1" ;;
    *)    printf '#!/usr/bin/env bash\necho "fixture suite: green"\nexit 0\n' > "$1" ;;
  esac
}
pad() {  # pad <suite> : rend le fichier GROS (le pere trie par taille decroissante)
  local i=0
  while [ "$i" -lt 120 ]; do printf '# padding padding padding padding padding padding padding padding\n' >> "$1"; i=$((i + 1)); done
}
cores_shim() {  # cores_shim <dossier> <n> : getconf, nproc et sysctl repondent n (aucun CADRE_GATE_* : le DEFAUT decide)
  local c
  mkdir -p "$1"
  for c in getconf nproc sysctl; do printf '#!/bin/sh\necho %s\n' "$2" > "$1/$c"; chmod +x "$1/$c"; done
}
busy_victim_tree() {  # busy_victim_tree <arbre> : la victime ROUGIT si elle voit BUSY ; BUSY tient jusqu'a ce qu'elle l'ait VU
  # Poignee de main bornee plutot qu'une fenetre d'horloge (le rouge sous le pool ne depend pas de l'ecart
  # de demarrage de deux enfants). busy est la plus grosse suite (jouee d'abord), victim la deuxieme.
  printf '#!/usr/bin/env bash\n: > "$BUSY"\ni=0\nwhile [ "$i" -lt 200 ] && [ ! -e "$BUSY.seen" ]; do sleep 0.1; i=$((i + 1)); done\nrm -f "$BUSY"\n: > "$BUSY.done"\nexit 0\n' > "$1/busy.test.sh"
  pad "$1/busy.test.sh"; pad "$1/busy.test.sh"
  printf '#!/usr/bin/env bash\ni=0\nwhile [ "$i" -lt 100 ]; do\n  if [ -e "$BUSY" ] || [ -e "$BUSY.done" ]; then break; fi\n  sleep 0.1; i=$((i + 1))\ndone\nif [ -e "$BUSY" ]; then : > "$BUSY.seen"; exit 1; fi\nexit 0\n' > "$1/victim.test.sh"
  pad "$1/victim.test.sh"
}
OUT=""
RC=0
rbt() {  # rbt <arbre> [VAR=val ...] : joue la COPIE du runner ; sortie fusionnee dans $OUT, rc dans $RC
  local tree="$1"; shift
  OUT="$TMP/out.$RANDOM$RANDOM"
  # T-01M4WTYT8M : la table de durees du chemin PAR DEFAUT est effacee avant CHAQUE appel (sinon elle persiste
  # d'un appel a l'autre sur un meme arbre et change l'ordre des cas d'avant : P16a/b, P16c/d) ; un cas qui SEME
  # une table ou la GARDE d'un appel a l'autre passe un CADRE_GATE_DURATIONS_DIR explicite (P23-P26).
  rm -rf "$tree/.agents/state/local/porte-durees"
  ( cd "$tree" \
    && unset CADRE_GATE_JOBS CADRE_GATE_JOBS_BASH CADRE_GATE_BASE CADRE_GATE_FAIL_FAST CADRE_GATE_REPLAY BASH_TEST_TIMEOUT BASH_TEST_KILL_GRACE BASH_TEST_TIMEOUT_BIN CADRE_STATE_DIR CADRE_GATE_DURATIONS_DIR CADRE_GATE_ROUGES_OUT
    for _kv in "$@"; do export "${_kv%%=*}=${_kv#*=}"; done
    timeout 120 bash core-scripts/run-bash-tests.sh ) > "$OUT" 2>&1
  RC=$?
}
tget() { awk -F '\t' -v k="$2" -v c="$3" '$1 == k {v = $c} END {print v}' "$1" 2>/dev/null; }   # tget <table> <suite> <colonne>
gcommit() {  # gcommit <arbre> <message> : depot git jouet (init au besoin), tout est suivi
  ( cd "$1" && { [ -d .git ] || git init -q .; } && git add -A \
    && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t git -c core.hooksPath=/dev/null commit -q -m "$2" )
}
has() { grep -qF -- "$1" "$OUT"; }
cntre() { local n; n="$(grep -c -- "$1" "$OUT")"; printf '%s' "${n:-0}"; }
is_win() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  return 1
}
SENSOR=0
SENSOR_PROBE="$(mktemp)"
( RBT_MISSING_LOG="$SENSOR_PROBE"; export RBT_MISSING_LOG
  command_not_found_handle() { printf '%s\n' "$1" >>"$RBT_MISSING_LOG"; return 127; }
  export -f command_not_found_handle
  bash -c 'rbt-sensor-probe-par' >/dev/null 2>&1 ) || true
[ -s "$SENSOR_PROBE" ] && SENSOR=1
rm -f "$SENSOR_PROBE"

if want P1; then
echo "=== P1. TROIS SUITES VERTES en parallele : le MEME resume que le serie, une ligne Parallel:"
T="$(make_tree p1)"
for k in a b c; do make_suite "$T/$k.test.sh" pass; done
rbt "$T" CADRE_GATE_JOBS=3 CADRE_GATE_BASE=none
[ "$RC" -eq 0 ] && ok "P1 rc 0" || ko "P1 rc $RC"
has "Bash test summary: 3 passed / 0 failed / 0 timed out (of 3) / 0 missing dep / 0 skipping" && ok "P1 resume exact" || ko "P1 resume: $(grep 'Bash test summary' "$OUT")"
has "Parallel: 3 jobs" && ok "P1 la ligne 'Parallel: 3 jobs' est la" || ko "P1 pas de ligne Parallel (le chemin parallele n'a pas tourne ?)"
has "All bash suites passed." && ok "P1 'All bash suites passed.' present" || ko "P1 phrase finale absente"
fi

if want P2; then
echo "=== P2. UNE SUITE ROUGE : listee, comptee, rc 1 (le jugement de l'enfant est repris tel quel)"
T="$(make_tree p2)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" fail
make_suite "$T/c.test.sh" pass
rbt "$T" CADRE_GATE_JOBS=3 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
[ "$RC" -eq 1 ] && ok "P2 rc 1" || ko "P2 rc $RC"
has "Bash test summary: 2 passed / 1 failed / 0 timed out (of 3)" && ok "P2 resume 2 passed / 1 failed" || ko "P2 resume: $(grep 'Bash test summary' "$OUT")"
{ has "Failed suites:" && has "  - ./b.test.sh"; } && ok "P2 la suite rouge est LISTEE" || ko "P2 la suite rouge n'est pas listee"
fi

if want P3; then
echo "=== P3. UN 127 AVALE dans une suite : MISSING DEP, rc 1 (le capteur de l'enfant joue)"
if [ "$SENSOR" -eq 1 ]; then
  T="$(make_tree p3)"
  make_suite "$T/a.test.sh" pass
  printf '#!/usr/bin/env bash\nno-such-cmd-par-t1122 2>/dev/null || true\nexit 0\n' > "$T/b.test.sh"
  rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
  { [ "$RC" -eq 1 ] && has "/ 1 missing dep" && has "--- MISSING DEP ./b.test.sh"; } && ok "P3 127 avale => MISSING DEP, rc 1" || ko "P3 rc $RC ($(grep -E 'MISSING|summary' "$OUT" | tr '\n' '|'))"
  has "no-such-cmd-par-t1122" && ok "P3 la commande manquante est NOMMEE" || ko "P3 commande non nommee"
else
  echo "SKIP: pas de command_not_found_handle sur ce bash (pre-4.0) — P3 non jouable"
fi
fi

if want P4; then
echo "=== P4. UN SKIP ANNONCE est vert MAIS DIT et compte (1 skipping, entree listee)"
T="$(make_tree p4)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" skip
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "/ 1 skipping" && has "Announced a SKIP or a missing optional tool" && has "  - ./b.test.sh — 1 SKIP annoncé(s) : SKIP: nothing to prove here"; } && ok "P4 SKIP compte, liste, entree identique au serie" || ko "P4 rc $RC ($(grep -E 'skipping|SKIP' "$OUT" | tr '\n' '|'))"
fi

if want P5; then
echo "=== P5. UN ENFANT TUE (le runner enfant, pas la suite) : 'child left no summary', rc 1"
if is_win || ! command -v ps >/dev/null 2>&1; then
  echo "SKIP: ps/kill du grand-parent non fiables ici (Git Bash ou ps absent) — P5 non jouable"
else
  T="$(make_tree p5)"
  make_suite "$T/a.test.sh" pass
  printf '#!/usr/bin/env bash\nkill -9 "$(ps -o ppid= -p "$PPID" | tr -d " ")"\nsleep 5\n' > "$T/b.test.sh"
  rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
  { [ "$RC" -eq 1 ] && has "child left no summary"; } && ok "P5 enfant tue => 'child left no summary', rc 1" || ko "P5 rc $RC ($(grep -E 'FAIL|summary' "$OUT" | tr '\n' '|'))"
  has "  - ./b.test.sh" && ok "P5 la suite de l'enfant tue est LISTEE en echec" || ko "P5 la suite n'est pas listee"
fi
fi

if want P6; then
echo "=== P6. LA BORNE DU POOL : jamais plus de JOBS suites vivantes, et exactement 2 ici (le pool joue)"
# Fenetre de 4 s par suite : ce banc tourne aussi sur la jambe CI BLOQUANTE (macOS), ou rien n'est rejoue
# (CADRE_GATE_JOBS=1 y est epingle) — un ecart de demarrage de deux enfants ne doit pas rougir.
T="$(make_tree p6)"
for k in 1 2 3 4 5; do
  printf '#!/usr/bin/env bash\necho "+ $(date +%%s.%%N 2>/dev/null || date +%%s)" >> "$SONDE"\nsleep 4\necho "- $(date +%%s.%%N 2>/dev/null || date +%%s)" >> "$SONDE"\n' > "$T/c$k.test.sh"
done
: > "$TMP/sonde.txt"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none "SONDE=$TMP/sonde.txt"
MX="$(LC_ALL=C sort -k2,2n "$TMP/sonde.txt" | awk '{if ($1 == "+") c++; else c--; if (c > m) m = c} END {print m + 0}')"
{ [ "$RC" -eq 0 ] && [ "$MX" -eq 2 ]; } && ok "P6 concurrence max observee = $MX (JOBS=2)" || ko "P6 rc $RC, concurrence max $MX (attendu 2) — horodatage: $(sed -n '1,2p' "$TMP/sonde.txt" | tr '\n' ' ')"
fi

if want P7; then
echo "=== P7. CADRE_GATE_JOBS=1 = le chemin SERIE d'origine : aucune ligne Parallel:, les suites jouees dans l'ordre"
T="$(make_tree p7)"
for k in a b c; do make_suite "$T/$k.test.sh" pass; done
rbt "$T" CADRE_GATE_JOBS=1
{ [ "$RC" -eq 0 ] && ! has "Parallel:" && has "=== RUN  ./a.test.sh" && has "Bash test summary: 3 passed"; } && ok "P7 serie intact (JOBS=1)" || ko "P7 rc $RC / une ligne Parallel: est apparue"
fi

if want P8; then
echo "=== P8. UNE SUITE LIEE AUX CHANGEMENTS ROUGE : l'echec rapide coupe et le DIT (NOT RUN), rc 1"
T="$(make_tree p8)"
printf '#!/usr/bin/env bash\nexit 1\n' > "$T/a_red.test.sh"
make_suite "$T/b.test.sh" pass; pad "$T/b.test.sh"
make_suite "$T/c.test.sh" pass; pad "$T/c.test.sh"
( cd "$T" && git init -q . && git add -A && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t git -c core.hooksPath=/dev/null commit -q -m base \
  && printf '#!/usr/bin/env bash\nexit 1 # changed\n' > a_red.test.sh && git add -A && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t git -c core.hooksPath=/dev/null commit -q -m second )
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 1 ] && has "Bash test summary: 0 passed / 1 failed / 0 timed out (of 3)" && has "NOT RUN (fail-fast=prio; CADRE_GATE_FAIL_FAST=0 runs all): 2 suite(s)"; } && ok "P8 rouge prioritaire : 2 suites NOT RUN annoncees, rc 1" || ko "P8 rc $RC ($(grep -E 'summary|NOT RUN' "$OUT" | tr '\n' '|'))"
has "1 suite(s) first (changed since HEAD~1)" && ok "P8 la phase prioritaire est NOMMEE" || ko "P8 phase prioritaire non annoncee"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0
{ [ "$RC" -eq 1 ] && has "Bash test summary: 2 passed / 1 failed / 0 timed out (of 3)" && ! has "NOT RUN"; } && ok "P8 FAIL_FAST=0 : tout est joue, rien NOT RUN" || ko "P8 FAIL_FAST=0 rc $RC"
fi

if want P9; then
echo "=== P9. UNE SUITE PENDUE : TIMEOUT compte dans SA colonne, listee, le reste joue"
if ! type -P timeout >/dev/null 2>&1; then
  echo "SKIP: timeout GNU absent — l'enfant n'aurait pas de chien de garde (P14 couvre l'annonce)"
else
  T="$(make_tree p9)"
  make_suite "$T/a.test.sh" pass
  printf '#!/usr/bin/env bash\nsleep 60\n' > "$T/hang.test.sh"
  rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 BASH_TEST_TIMEOUT=2 BASH_TEST_KILL_GRACE=1
  { [ "$RC" -eq 1 ] && has "1 passed / 0 failed / 1 timed out" && has "Timed out (killed at 2s — raise with BASH_TEST_TIMEOUT):" && has "  - ./hang.test.sh"; } && ok "P9 TIMEOUT dans sa colonne, en-tete du serie, listee" || ko "P9 rc $RC ($(grep -E 'summary|Timed' "$OUT" | tr '\n' '|'))"
fi
fi

if want P10; then
echo "=== P10. UNE SUITE QUI LIT LE STDIN ne mange pas la file (le defaut trouve a la mesure en rev1)"
T="$(make_tree p10)"
printf '#!/usr/bin/env bash\ncat > /dev/null\nexit 0\n' > "$T/a_cat.test.sh"; pad "$T/a_cat.test.sh"
for k in 1 2 3; do make_suite "$T/z$k.test.sh" pass; done
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "Bash test summary: 4 passed / 0 failed / 0 timed out (of 4)" && ! has "NOT RUN"; } && ok "P10 les 4 suites sont JOUEES malgre le cat" || ko "P10 rc $RC ($(grep -E 'summary|NOT RUN' "$OUT" | tr '\n' '|'))"
fi

if want P11 P17; then
echo "=== P11/P17. EXACTEMENT UNE ligne 'Bash test summary:', UN en-tete 'Discovered', UN bloc 'Skipped … nested checkout' (les en-tetes et pieds des enfants sont REPLIES)"
T="$(make_tree p11)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" fail
make_suite "$T/c.test.sh" pass
mkdir -p "$T/vendor/clone/.git"
make_suite "$T/vendor/clone/foreign.test.sh" fail
rbt "$T" CADRE_GATE_JOBS=3 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$(cntre '^Bash test summary:')" -eq 1 ] && [ "$(cntre '^Discovered ')" -eq 1 ] && [ "$(cntre '^Skipped 1 suite(s) belonging to a nested checkout')" -eq 1 ] && [ "$(cntre '^All bash suites passed\.')" -eq 0 ]; } \
  && ok "P11 1 resume, 1 Discovered, 1 Skipped nested, pas de faux 'All passed'" || ko "P11 resume=$(cntre '^Bash test summary:') Discovered=$(cntre '^Discovered ') Skipped=$(cntre '^Skipped 1')"
[ "$(cntre '^=== RUN  ')" -eq 3 ] && ok "P11 les 3 corps d'enfant sont rejoues (=== RUN x3)" || ko "P11 === RUN : $(cntre '^=== RUN  ')"
fi

if want P12; then
echo "=== P12. LE BLOC DE RESUME EST IDENTIQUE octet pour octet, serie contre parallele, sur un arbre MIXTE"
# vert, 2 rouges dont le PREMIER (a_) est le plus LENT (l'ordre de fin differe de l'ordre de decouverte),
# SKIP, optional absent, pendue, requires absent, 127 avale, checkout imbrique rouge.
T="$(make_tree p12)"
printf '#!/usr/bin/env bash\nsleep 1.5\nexit 1\n' > "$T/a_slow_red.test.sh"
make_suite "$T/b_fast_red.test.sh" fail
make_suite "$T/c_green.test.sh" pass
make_suite "$T/d_skip.test.sh" skip
printf '#!/usr/bin/env bash\n# optional: no-such-opt-par-t1122\necho "fixture suite: green"\nexit 0\n' > "$T/g_opt.test.sh"
printf '#!/usr/bin/env bash\n# requires: no-such-tool-par-t1122\nexit 0\n' > "$T/f_req.test.sh"
if type -P timeout >/dev/null 2>&1; then printf '#!/usr/bin/env bash\nsleep 60\n' > "$T/e_hung.test.sh"; fi
if [ "$SENSOR" -eq 1 ]; then printf '#!/usr/bin/env bash\nno-such-cmd-par-t1122 2>/dev/null || true\nexit 0\n' > "$T/h_127.test.sh"; fi
mkdir -p "$T/vendor/clone/.git"
make_suite "$T/vendor/clone/foreign.test.sh" fail
rbt "$T" CADRE_GATE_JOBS=1 BASH_TEST_TIMEOUT=2 BASH_TEST_KILL_GRACE=1
RC_S="$RC"; cp "$OUT" "$TMP/p12.serial"
rbt "$T" CADRE_GATE_JOBS=4 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 BASH_TEST_TIMEOUT=2 BASH_TEST_KILL_GRACE=1
RC_P="$RC"; cp "$OUT" "$TMP/p12.par"
blk() { sed -n '/^================================================================$/,$p' "$1" | sed -E 's/\([0-9]+s\)/(Ns)/g'; }
BS="$(blk "$TMP/p12.serial")"; BP="$(blk "$TMP/p12.par" | awk '!/^Parallel:/')"
[ -n "$BS" ] && ok "P12 non-vacuite : le bloc serie n'est pas vide ($(printf '%s\n' "$BS" | awk 'END {print NR}') lignes)" || ko "P12 bloc serie VIDE"
[ "$RC_S" = "$RC_P" ] && [ "$RC_S" = "1" ] && ok "P12 meme rc (1)" || ko "P12 rc serie $RC_S, parallele $RC_P"
if [ "$BS" = "$BP" ]; then ok "P12 le bloc de resume est IDENTIQUE octet pour octet"; else ko "P12 blocs differents"; diff <(printf '%s\n' "$BS") <(printf '%s\n' "$BP") | sed 's/^/      /' | sed -n '1,30p'; fi
fi

if want P13; then
echo "=== P13. auto A UN COEUR / ILLISIBLE / GIT BASH : chemin SERIE (A-C1) ; auto PAR DEFAUT (aucun CADRE_GATE_*) : coeurs/2 bornes a 8"
T="$(make_tree p13)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" pass
mkdir -p "$TMP/sh13a" "$TMP/sh13b" "$TMP/sh13c"
for c in getconf nproc sysctl; do printf '#!/bin/sh\necho 1\n' > "$TMP/sh13a/$c"; chmod +x "$TMP/sh13a/$c"; done
printf '#!/bin/sh\necho undefined\n' > "$TMP/sh13b/getconf"
printf '#!/bin/sh\necho garbage\n' > "$TMP/sh13b/nproc"
printf '#!/bin/sh\necho x\n' > "$TMP/sh13b/sysctl"
printf '#!/bin/sh\necho MINGW64_NT-10.0\n' > "$TMP/sh13c/uname"
chmod +x "$TMP/sh13b/getconf" "$TMP/sh13b/nproc" "$TMP/sh13b/sysctl" "$TMP/sh13c/uname"
for V in a b c; do
  rbt "$T" "PATH=$TMP/sh13$V:$PATH"
  { [ "$RC" -eq 0 ] && ! has "Parallel:" && [ "$(cntre '^Bash test summary:')" -eq 1 ] && has "Bash test summary: 2 passed"; } && ok "P13$V auto -> serie (rc 0, un seul resume, pas de Parallel:)" || ko "P13$V rc $RC ($(sed -n '1,4p' "$OUT" | tr '\n' '|'))"
done
if is_win; then
  echo "SKIP: P13d-f — sous Git Bash auto vaut 1 par conception (P13c le couvre)"
else
  for V in d:16:8 e:6:3 f:40:8; do
    _id="${V%%:*}"; _rest="${V#*:}"; _nc="${_rest%%:*}"; _nj="${_rest#*:}"
    cores_shim "$TMP/sh13$_id" "$_nc"
    rbt "$T" "PATH=$TMP/sh13$_id:$PATH"
    { [ "$RC" -eq 0 ] && has "Parallel: $_nj jobs (CADRE_GATE_JOBS=auto|N), fail-fast=prio, replay<=3" && has "Bash test summary: 2 passed"; } \
      && ok "P13$_id DEFAUT (aucun CADRE_GATE_*) : $_nc coeurs -> $_nj jobs, chemin parallele, rc 0" || ko "P13$_id rc $RC, $_nc coeurs ($(grep -F 'Parallel:' "$OUT" | sed -n '1p'))"
  done
fi
fi

if want P14; then
echo "=== P14. PAS DE CHIEN DE GARDE, en PARALLELE : COVERAGE DEGRADED annonce, binaire NOMME, le run n'est pas bloque"
T="$(make_tree p14)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" pass
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none BASH_TEST_TIMEOUT_BIN=no-such-timeout-binary
{ [ "$RC" -eq 0 ] && has "Parallel: 2 jobs" && has "COVERAGE DEGRADED" && has "no-such-timeout-binary"; } && ok "P14 parallele + watchdog absent : annonce, binaire nomme, rc 0" || ko "P14 rc $RC ($(grep -c 'COVERAGE DEGRADED' "$OUT") annonce(s))"
fi

if want P15; then
echo "=== P15. UN REGLAGE INVALIDE est REFUSE rc 2 (jamais ignore)"
T="$(make_tree p15)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" pass
for SET in CADRE_GATE_JOBS=x CADRE_GATE_FAIL_FAST=y CADRE_GATE_REPLAY=z CADRE_GATE_JOBS=99999999999999999999 CADRE_GATE_JOBS=99; do
  rbt "$T" "$SET"
  { [ "$RC" -eq 2 ] && has "${SET%%=*}" && ! has "=== RUN"; } && ok "P15 $SET : rc 2, nomme, rien lance" || ko "P15 $SET : rc $RC"
done
# binome 7+8 (F4/T5) : 20 chiffres faisaient echouer `[ -gt 1 ]` -> la porte repassait en SERIE sans le dire ;
# 99 lancait 99 enfants. Borne JOBS <= 64 (2 chiffres) ; la borne elle-meme est ACCEPTEE.
rbt "$T" CADRE_GATE_JOBS=64 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "Parallel: 64 jobs"; } && ok "P15 CADRE_GATE_JOBS=64 (la borne) : accepte, chemin parallele, rc 0" || ko "P15 CADRE_GATE_JOBS=64 : rc $RC"
fi

if want P16; then
echo "=== P16. REJEU SEUL d'un rouge sous le pool (L-00000234) : borne, annonce, jamais muet ; une PENDUE n'est jamais rejouee"
T="$(make_tree p16)"
busy_victim_tree "$T"
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none "BUSY=$TMP/busy"
{ [ "$RC" -eq 0 ] && has "replaying ./victim.test.sh ALONE" && has "RED UNDER THE POOL, GREEN WHEN REPLAYED ALONE" && has "Bash test summary: 2 passed / 0 failed / 0 timed out (of 2)"; } \
  && ok "P16a un rouge sous le pool est REJOUE seul : VERT, ANNONCE, resume 2 passed" || ko "P16a rc $RC ($(grep -E 'replay|REPLAYED|summary' "$OUT" | tr '\n' '|'))"
has "contention OR intermittent defect, NOT established" && ok "P16a la section n'affirme pas la cause (contention OR intermittent)" || ko "P16a la section affirme une cause non etablie"
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "BUSY=$TMP/busy"
{ [ "$RC" -eq 1 ] && ! has "replaying" && ! has "no replay"; } && ok "P16b CADRE_GATE_REPLAY=0 : le meme rouge reste ROUGE, aucun rejeu, aucun bruit" || ko "P16b rc $RC"
T="$(make_tree p16c)"
make_suite "$T/a.test.sh" pass
make_suite "$T/bad.test.sh" fail
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none
{ [ "$RC" -eq 1 ] && has "replaying ./bad.test.sh ALONE" && ! has "GREEN WHEN REPLAYED ALONE"; } && ok "P16c un rouge DETERMINISTE reste rouge apres rejeu" || ko "P16c rc $RC"
make_suite "$T/bad2.test.sh" fail
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=1
{ [ "$RC" -eq 1 ] && has "no replay" && ! has "replaying"; } && ok "P16d 2 rouges > CADRE_GATE_REPLAY=1 : aucun rejeu, ROUGE" || ko "P16d rc $RC"
if type -P timeout >/dev/null 2>&1; then
  T="$(make_tree p16e)"
  make_suite "$T/a.test.sh" pass
  printf '#!/usr/bin/env bash\nsleep 60\n' > "$T/hang.test.sh"
  rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none BASH_TEST_TIMEOUT=2 BASH_TEST_KILL_GRACE=1
  { [ "$RC" -eq 1 ] && has "1 passed / 0 failed / 1 timed out" && ! has "replaying"; } && ok "P16e une suite PENDUE n'est JAMAIS rejouee (rejeu actif par defaut) : ROUGE en un seul budget" || ko "P16e rc $RC ($(grep -E 'replay|summary' "$OUT" | tr '\n' '|'))"
else
  echo "SKIP: P16e — timeout GNU absent, pas de suite pendue a produire (P14 couvre l'annonce)"
fi
for V in f g; do
  T="$(make_tree "p16$V")"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$T/a_red.test.sh"
  make_suite "$T/b.test.sh" pass
  if [ "$V" = "g" ]; then make_suite "$T/d_red.test.sh" fail; fi
  ( cd "$T" && git init -q . && git add -A && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t git -c core.hooksPath=/dev/null commit -q -m base \
    && printf '#!/usr/bin/env bash\nexit 1 # changed\n' > a_red.test.sh && git add -A && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t git -c core.hooksPath=/dev/null commit -q -m second )
  if [ "$V" = "f" ]; then
    rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0
    { [ "$RC" -eq 1 ] && [ "$(cntre '^Parallel: replaying ')" -eq 1 ]; } && ok "P16f une suite deja rejouee (phase prioritaire) n'est PAS rejouee une 2e fois a la phase suivante" || ko "P16f rc $RC, $(cntre '^Parallel: replaying ') rejeu(x) (attendu 1)"
  else
    rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_REPLAY=1
    { [ "$RC" -eq 1 ] && [ "$(cntre '^Parallel: replaying ')" -eq 1 ] && has "no replay"; } && ok "P16g le plafond CADRE_GATE_REPLAY=1 vaut pour TOUT le run (prioritaire + reste)" || ko "P16g rc $RC, $(cntre '^Parallel: replaying ') rejeu(x) (attendu 1, puis no replay)"
  fi
done
fi

if want P18; then
echo "=== P18. LE BLOC PARALLELE VIT APRES LE CHIEN DE GARDE ET LE CAPTEUR 127 (placement : l'en-tete du pere EST l'en-tete serie)"
L_WD="$(awk '/^if command -v "\$TIMEOUT_BIN"/ {print NR; exit}' "$RUNNER")"
L_SENSOR="$(awk '/^[[:space:]]*MISSING_DETECT=/ {print NR; exit}' "$RUNNER")"
L_PAR="$(awk '/_par="\$\(mktemp -d\)"/ {print NR; exit}' "$RUNNER")"
if [ -n "$L_WD" ] && [ -n "$L_SENSOR" ] && [ -n "$L_PAR" ] && [ "$L_PAR" -gt "$L_WD" ] && [ "$L_PAR" -gt "$L_SENSOR" ]; then
  ok "P18 bloc parallele (l.$L_PAR) apres le watchdog (l.$L_WD) et le capteur (l.$L_SENSOR)"
else
  ko "P18 placement : watchdog l.${L_WD:-?}, capteur l.${L_SENSOR:-?}, bloc l.${L_PAR:-?}"
fi
fi

if want P19; then
echo "=== P19. CHAQUE ENFANT A SA PARTITION d'etat (CADRE_STATE_DIR) : aucune collision de fichier a nom fixe"
T="$(make_tree p19)"
for k in 1 2 3; do
  printf '#!/usr/bin/env bash\necho "$$" > "$CADRE_STATE_DIR/probe"\nsleep 1\n[ "$(cat "$CADRE_STATE_DIR/probe")" = "$$" ] || { echo "collision on shared state dir"; exit 1; }\n' > "$T/s$k.test.sh"
done
rbt "$T" CADRE_GATE_JOBS=3 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "3 passed / 0 failed"; } && ok "P19 3 enfants simultanes, 0 collision d'etat" || ko "P19 rc $RC ($(grep -c collision "$OUT") collision(s))"
fi

if want P20; then
echo "=== P20. FAIL_FAST=all x REJEU : un rouge RATTRAPE par son rejeu seul ne laisse pas la file coupee"
T="$(make_tree p20)"
busy_victim_tree "$T"
for k in 1 2 3; do make_suite "$T/s$k.test.sh" pass; done
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_FAIL_FAST=all "BUSY=$TMP/busy"
{ [ "$RC" -eq 0 ] && has "replaying ./victim.test.sh ALONE" && has "GREEN WHEN REPLAYED ALONE" && has "Bash test summary: 5 passed / 0 failed / 0 timed out (of 5)" && ! has "NOT RUN"; } \
  && ok "P20 all x rejeu : le rouge rattrape, la file REPREND, 5/5 jouees, rc 0" || ko "P20 rc $RC ($(grep -E 'summary|NOT RUN|replay' "$OUT" | tr '\n' '|'))"
fi

if want P21; then
echo "=== P21. L'ORDRE PAR DEFAUT (aucun CADRE_GATE_*) : la plus GROSSE suite part d'abord, la plus petite en dernier"
if is_win; then
  echo "SKIP: P21 — sous Git Bash auto vaut 1 (serie) par conception"
else
  T="$(make_tree p21)"
  for k in big mid small; do printf '#!/usr/bin/env bash\necho %s >> "$SONDE"\nsleep 1\nexit 0\n' "$k" > "$T/$k.test.sh"; done
  pad "$T/big.test.sh"; pad "$T/big.test.sh"; pad "$T/mid.test.sh"
  cores_shim "$TMP/sh21" 4
  : > "$TMP/sonde21.txt"
  rbt "$T" "PATH=$TMP/sh21:$PATH" "SONDE=$TMP/sonde21.txt"
  { [ "$RC" -eq 0 ] && has "Parallel: 2 jobs" && [ "$(awk 'END {print $0}' "$TMP/sonde21.txt")" = "small" ]; } \
    && ok "P21 taille decroissante : big et mid d'abord (2 jobs), small en DERNIER" || ko "P21 rc $RC, ordre de depart : $(tr '\n' ' ' < "$TMP/sonde21.txt")"
fi
fi

if want P22; then
echo "=== P22. UN ENFANT TUE APRES UN FAUX RESUME 'passed' (runner imbrique) : le rc de l'enfant l'emporte, FAIL, rc 1"
# binome 7+8 (A F6 / B T2) : _judge lisait le DERNIER resume de l'enfant sans regarder son rc. Une suite qui
# imprime un resume d'un runner imbrique, puis un enfant tue -9 (OOM) avant le sien : la suite passait VERTE.
if is_win || ! command -v ps >/dev/null 2>&1; then
  echo "SKIP: ps/kill du grand-parent non fiables ici (Git Bash ou ps absent) — P22 non jouable"
else
  T="$(make_tree p22)"
  make_suite "$T/a.test.sh" pass
  printf '#!/usr/bin/env bash\necho "Bash test summary: 1 passed / 0 failed / 0 timed out (of 1) / 0 missing dep / 0 skipping"\nsleep 1\nkill -9 "$(ps -o ppid= -p "$PPID" | tr -d " ")"\nsleep 5\n' > "$T/b.test.sh"
  rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
  { [ "$RC" -eq 1 ] && has "summary says passed but child rc=137"; } && ok "P22 faux resume 'passed' + enfant tue -9 => FAIL nomme (rc 137), rc 1" || ko "P22 rc $RC ($(grep -E 'FAIL|summary' "$OUT" | tr '\n' '|'))"
  # lue DANS la section « Failed suites: » : l'en-tete « Discovered » liste deja TOUTES les suites
  sed -n '/^Failed suites:/,/^$/p' "$OUT" | grep -qxF "  - ./b.test.sh" && ok "P22 la suite est LISTEE sous 'Failed suites:'" || ko "P22 la suite n'est pas listee sous 'Failed suites:'"
fi
fi

# --- T-01M4WTYT8M : la TABLE DE DUREES (ordre de la file, jamais le verdict) et la prio des morceaux de safe-bash ------
if want P23; then
echo "=== P23. SANS TABLE : weights=bytes (l'ordre d'avant) ; bash.tsv au chemin PAR DEFAUT porte les suites VERTES en passe 1 ; FUSION sans effacement"
T="$(make_tree p23)"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" pass
make_suite "$T/c.test.sh" fail
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0
TB="$T/.agents/state/local/porte-durees/bash.tsv"
{ [ "$RC" -eq 1 ] && has "; weights=bytes (no known duration in " && has "; queue head: ./"; } \
  && ok "P23 sans table : weights=bytes, tete de file ANNONCEE, rc 1 (la rouge : la table ne touche pas le verdict)" || ko "P23 rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
{ [ -f "$TB" ] && [ "$(sed -n '1p' "$TB")" = "# v1" ] && [ "$(awk 'END {print NR}' "$TB")" -eq 3 ] \
  && [ -n "$(tget "$TB" ./a.test.sh 2)" ] && [ -n "$(tget "$TB" ./b.test.sh 2)" ] && [ -z "$(tget "$TB" ./c.test.sh 2)" ]; } \
  && ok "P23 bash.tsv au chemin PAR DEFAUT : # v1 + les 2 suites vertes en passe 1, la rouge ABSENTE" || ko "P23 table : $(tr '\t\n' '>|' < "$TB" 2>/dev/null || echo ABSENTE)"
mkdir -p "$TMP/dur-p23"
printf '# v1\nillisible sans tabulation\n./gone.test.sh\t7\n./c.test.sh\t99\n./a.test.sh\t42\n' > "$TMP/dur-p23/bash.tsv"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-p23"
TB="$TMP/dur-p23/bash.tsv"
{ [ "$RC" -eq 1 ] && has "Parallel: 1 unreadable line(s) in $TB"; } && ok "P23 la ligne illisible est COMPTEE et annoncee" || ko "P23 rc $RC ($(grep -F 'unreadable' "$OUT"))"
{ [ "$(tget "$TB" ./gone.test.sh 2)" = "7" ] && [ "$(tget "$TB" ./c.test.sh 2)" = "99" ]; } \
  && ok "P23 fusion : ./gone.test.sh CONSERVE, la suite ROUGE ./c.test.sh n'est PAS reecrite (99 garde)" || ko "P23 gone=$(tget "$TB" ./gone.test.sh 2) c=$(tget "$TB" ./c.test.sh 2)"
{ [ -n "$(tget "$TB" ./a.test.sh 2)" ] && [ "$(tget "$TB" ./a.test.sh 2)" != "42" ] && grep -qxF "illisible sans tabulation" "$TB" && [ "$(grep -c '^# v1$' "$TB")" -eq 1 ]; } \
  && ok "P23 la suite verte est REECRITE (42 remplace), la ligne illisible GARDEE telle quelle, un seul en-tete" || ko "P23 table : $(tr '\t\n' '>|' < "$TB")"
fi

if want P24; then
echo "=== P24. UNE TABLE SEMEE (lente = 50 s, la plus PETITE suite) : la tete de file est ./lente.test.sh ; une suite inconnue est estimee par ses octets"
T="$(make_tree p24)"
make_suite "$T/big.test.sh" pass; pad "$T/big.test.sh"; pad "$T/big.test.sh"
make_suite "$T/mid.test.sh" pass; pad "$T/mid.test.sh"
make_suite "$T/lente.test.sh" pass
mkdir -p "$TMP/dur-p24"
printf '# v1\n./lente.test.sh\t50\n./big.test.sh\t1\n' > "$TMP/dur-p24/bash.tsv"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-p24"
{ [ "$RC" -eq 0 ] && has "; weights=durations (2 known in $TMP/dur-p24/bash.tsv, 1 estimated from bytes); queue head: ./lente.test.sh, ./mid.test.sh, ./big.test.sh."; } \
  && ok "P24 table semee : weights=durations, ./lente.test.sh en TETE, ./mid.test.sh (inconnue) estimee par ses octets" || ko "P24 rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "; weights=bytes (no known duration in " && has "queue head: ./big.test.sh, ./mid.test.sh, ./lente.test.sh."; } \
  && ok "P24 non-vacuite : sans la table, le meme arbre met ./lente.test.sh en DERNIER (octets)" || ko "P24 sans table : rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
fi

if want P25; then
echo "=== P25. safe-bash.sh change : ses MORCEAUX safe-bash-*.test.sh passent en phase prioritaire (liste FERMEE) ; foo.sh change : foo-part2.test.sh NE l'est PAS"
T="$(make_tree p25)"
mkdir -p "$T/.claude/hooks"
printf '#!/usr/bin/env bash\nexit 0\n' > "$T/.claude/hooks/safe-bash.sh"
make_suite "$T/.claude/hooks/safe-bash.test.sh" pass
make_suite "$T/.claude/hooks/safe-bash-t-y.test.sh" pass
make_suite "$T/.claude/hooks/safe-bash-em-z.test.sh" pass
printf '#!/usr/bin/env bash\nexit 0\n' > "$T/foo.sh"
make_suite "$T/foo-part2.test.sh" pass
make_suite "$T/z.test.sh" pass
gcommit "$T" base
printf '#!/usr/bin/env bash\nexit 0 # changed\n' > "$T/.claude/hooks/safe-bash.sh"
gcommit "$T" second
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "; 3 suite(s) first (changed since HEAD~1);"; } \
  && ok "P25 safe-bash.sh change : safe-bash.test.sh + ses 2 morceaux = 3 suites prioritaires" || ko "P25 rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
printf '#!/usr/bin/env bash\nexit 0 # foo changed\n' > "$T/foo.sh"
gcommit "$T" third
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "; 0 suite(s) first (changed since HEAD~1);"; } \
  && ok "P25 foo.sh change : foo-part2.test.sh N'EST PAS prioritaire (aucun prefixe general : la phase prio est une barriere)" || ko "P25 foo : rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
fi

if want P26; then
echo "=== P26. CADRE_GATE_DURATIONS_DIR est LUE PUIS RETIREE : absente chez chaque suite (parallele ET serie) ; la table va au dossier demande"
T="$(make_tree p26)"
printf '#!/usr/bin/env bash\nif [ -n "${CADRE_GATE_DURATIONS_DIR+x}" ]; then echo "CADRE_GATE_DURATIONS_DIR leaked into the suite"; exit 1; fi\nexit 0\n' > "$T/env.test.sh"
make_suite "$T/ok.test.sh" pass
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-p26"
{ [ "$RC" -eq 0 ] && has "Parallel: 2 jobs" && [ -n "$(tget "$TMP/dur-p26/bash.tsv" ./env.test.sh 2)" ] && [ ! -e "$T/.agents/state/local/porte-durees" ]; } \
  && ok "P26 parallele : variable ABSENTE chez la suite (VERT) ; table ecrite sous le dossier DEMANDE, rien au chemin par defaut" || ko "P26 parallele rc $RC ($(grep -E 'leaked|durations table' "$OUT" | tr '\n' '|'))"
rbt "$T" CADRE_GATE_JOBS=1 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-p26"
{ [ "$RC" -eq 0 ] && ! has "Parallel:" && has "Bash test summary: 2 passed"; } && ok "P26 serie (JOBS=1) : variable ABSENTE chez la suite (VERT)" || ko "P26 serie rc $RC ($(grep -E 'leaked|summary' "$OUT" | tr '\n' '|'))"
fi

if want P27; then
echo "=== P27. CADRE_GATE_ROUGES_OUT (T-01M5QBFKM444FB53RM2J1NBB4X) : les suites JOUEES restees rouges (fail, pendue) y sont listees, une rouge-puis-verte au rejeu seul NON ; l'enfant --only ne la voit pas ; vert -> aucun fichier"
if ! type -P timeout >/dev/null 2>&1; then
  echo "SKIP: timeout GNU absent — la suite pendue n'aurait pas de chien de garde (P14 couvre l'annonce)"
else
  T="$(make_tree p27)"
  make_suite "$T/a.test.sh" pass
  make_suite "$T/b.test.sh" fail
  printf '#!/usr/bin/env bash\nsleep 60\n' > "$T/hang.test.sh"
  # rouge au 1er passage, verte au rejeu seul : MUTANT « lister _FIRST != pass » -> elle apparait -> KO
  printf '#!/usr/bin/env bash\nif [ -e "$P27_FLAKE" ]; then exit 0; fi\n: > "$P27_FLAKE"\nexit 1\n' > "$T/flake.test.sh"
  # MUTANT « unset CADRE_GATE_ROUGES_OUT retire » -> l'enfant la voit, env.test.sh rougit -> KO
  printf '#!/usr/bin/env bash\nif [ -n "${CADRE_GATE_ROUGES_OUT+x}" ]; then echo "CADRE_GATE_ROUGES_OUT leaked into the suite"; exit 1; fi\nexit 0\n' > "$T/env.test.sh"
  rm -f "$TMP/p27-flake" "$TMP/p27-rouges"
  rbt "$T" CADRE_GATE_JOBS=3 CADRE_GATE_BASE=none CADRE_GATE_FAIL_FAST=0 BASH_TEST_TIMEOUT=2 BASH_TEST_KILL_GRACE=1 "P27_FLAKE=$TMP/p27-flake" "CADRE_GATE_ROUGES_OUT=$TMP/p27-rouges"
  _l="$(tr '\n' '|' < "$TMP/p27-rouges" 2>/dev/null)"
  { [ "$RC" -eq 1 ] && has "Parallel: 3 jobs" && [ "$_l" = "./b.test.sh|./hang.test.sh|" ]; } \
    && ok "P27 liste = ./b.test.sh et ./hang.test.sh ; ./flake.test.sh (verte au rejeu) et ./env.test.sh (verte) absentes" || ko "P27 rc $RC liste « $_l » ($(grep -E 'summary|leaked|replaying' "$OUT" | tr '\n' '|'))"
  T2="$(make_tree p27b)"
  make_suite "$T2/a.test.sh" pass
  make_suite "$T2/b.test.sh" pass
  rm -f "$TMP/p27b-rouges"
  rbt "$T2" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none "CADRE_GATE_ROUGES_OUT=$TMP/p27b-rouges"
  { [ "$RC" -eq 0 ] && [ ! -e "$TMP/p27b-rouges" ]; } && ok "P27 vert : aucun fichier" || ko "P27 vert rc $RC"
  make_suite "$T2/c.test.sh" fail
  rm -f "$TMP/p27c-rouges"
  ( cd "$T2" && unset CADRE_GATE_JOBS CADRE_STATE_DIR CADRE_GATE_DURATIONS_DIR && CADRE_GATE_ROUGES_OUT="$TMP/p27c-rouges" timeout 60 bash core-scripts/run-bash-tests.sh --only ./c.test.sh ) > "$TMP/p27c.out" 2>&1
  _rc=$?
  { [ "$_rc" -eq 1 ] && [ "$(cat "$TMP/p27c-rouges" 2>/dev/null)" = "./c.test.sh" ]; } \
    && ok "P27 chemin serie (--only) : la suite rouge est ecrite, une ligne" || ko "P27 serie rc $_rc liste « $(tr '\n' '|' < "$TMP/p27c-rouges" 2>/dev/null) »"
fi
fi

if want P28; then
echo "=== P28. CADRE_GATE_JOBS_BASH (T-01M60XKFK7MPKZWNHH326ZMW3M) : PRIME sur CADRE_GATE_JOBS, LUE PUIS RETIREE (absente chez chaque suite), validee (entier <= 64, sinon rc 2) ; vide = absente"
T="$(make_tree p28)"
printf '#!/usr/bin/env bash\nif [ -n "${CADRE_GATE_JOBS_BASH+x}" ]; then echo "CADRE_GATE_JOBS_BASH leaked into the suite"; exit 1; fi\nexit 0\n' > "$T/env.test.sh"
make_suite "$T/a.test.sh" pass
make_suite "$T/b.test.sh" pass
rbt "$T" CADRE_GATE_JOBS=1 CADRE_GATE_JOBS_BASH=3 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "Parallel: 3 jobs" && has "Bash test summary: 3 passed / 0 failed"; } \
  && ok "P28 JOBS_BASH=3 prime sur JOBS=1 : chemin parallele a 3 jobs ; variable ABSENTE chez la suite (VERT)" || ko "P28 prime rc $RC ($(grep -E 'Parallel: |leaked|summary' "$OUT" | tr '\n' '|'))"
rbt "$T" CADRE_GATE_JOBS=4 CADRE_GATE_JOBS_BASH=1 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && ! has "Parallel:" && has "Bash test summary: 3 passed / 0 failed"; } \
  && ok "P28 JOBS_BASH=1 prime sur JOBS=4 : chemin SERIE ; variable ABSENTE chez la suite (VERT)" || ko "P28 serie rc $RC ($(grep -E 'Parallel: |leaked|summary' "$OUT" | tr '\n' '|'))"
rbt "$T" CADRE_GATE_JOBS=2 CADRE_GATE_JOBS_BASH= CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "Parallel: 2 jobs"; } && ok "P28 JOBS_BASH vide = absente : CADRE_GATE_JOBS=2 decide" || ko "P28 vide rc $RC ($(grep -F 'Parallel: ' "$OUT" | sed -n '1p'))"
for SET in CADRE_GATE_JOBS_BASH=x CADRE_GATE_JOBS_BASH=auto CADRE_GATE_JOBS_BASH=65 CADRE_GATE_JOBS_BASH=99999999999999999999; do
  rbt "$T" CADRE_GATE_JOBS=2 "$SET"
  { [ "$RC" -eq 2 ] && has "CADRE_GATE_JOBS_BASH=" && ! has "=== RUN"; } && ok "P28 $SET : rc 2, nomme, rien lance" || ko "P28 $SET : rc $RC"
done
rbt "$T" CADRE_GATE_JOBS=1 CADRE_GATE_JOBS_BASH=64 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "Parallel: 64 jobs"; } && ok "P28 JOBS_BASH=64 (la borne) : accepte, chemin parallele, rc 0" || ko "P28 JOBS_BASH=64 : rc $RC"
fi

echo
echo "================================================================"
echo "run-bash-tests-parallel: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Parallel mode, on these toys: same verdict, same summary block, a verdict red is replayed alone before it is believed, nothing is swallowed."
