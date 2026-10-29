#!/usr/bin/env bash
# requires: git
# Banc de `core-scripts/verify.sh --rouges` et de la purge d'entree (T-01M5QBFKM444FB53RM2J1NBB4X, decision
# pilote S-01M5QBG09B3R1NDJPZATE7NCDT). Run: bash core-scripts/verify-rouges.test.sh
#
# CE QUI EST SOUS TEST EST LE verify.sh LIVRE, copie dans des depots jouets sous $TMP (il resout sa racine depuis
# son propre dossier) :
#   - REPO  (R1-R7b) : coureurs BOUCHONS qui tracent argv et ${CADRE_GATE_ROUGES_OUT:-ABSENT}, rouges ou verts
#                      par fichier-bascule, et ecrivent leur rouge dans le canal quand il est pose ;
#   - REPO8 (R8, R8b): le VRAI run-bash-tests.sh, bout a bout sous `--at` ; R8b a un verify.sh INTERIEUR bouchon
#                      qui pose une liste piegee (lien, 65 Kio, sha etranger) dans SON clone ;
#   - FX / FX2 (R9, R9b, R9c, R10) : les VRAIS run-pytest-shards.sh et run-bash-tests.sh ; FX rouge en pytest
#                      seulement (tests/test_a.py), FX2 rouge en bash seulement (./zz-rouge.test.sh).
# R9b joue la porte COMPLETE vivante sous CHACUN des cinq reglages purges, seul herite, et exige VERIFY FAILED et
# la ligne `verify.sh: réglage purgé à l'entrée : <NOM>` ; R9c les rejoue sous `--rouges` et exige REJEU ROUGE.
# Chaque lancement de verify.sh passe par `rv`, qui BATIT son environnement (VERIFY_INNER=0, FAIL_FAST=0, table
# de durees jetable, les reglages purges retires) et ne l'herite jamais (verify.test.sh, en-tete).
# MUTANTS (copie hors depot, chacun rougit le bras nomme) : prefixe CADRE_GATE_ROUGES_OUT retire de step() -> R1 ;
# l'accumulateur ecrit ETAPE_ROUGE -> R1 ; `continue` sur les entrees bash -> R2 ; stamp_write au rejeu -> R3/R4 ;
# rejeu via step() -> R3 ; ROUGES_SEUL herite -> R5 ; effacement d'entree retire -> R5/R8 ; effacement deplace au
# verdict -> R5b ; unset retire -> R6 ; IMPOSSIBLE compte joue -> R7 ; refus inner/adoptant retires -> R7b ;
# relecture $WT retiree -> R8 ; [ ! -L ], borne 64 Kio, comparaison sha= retires -> R8b ; pytest nu au lieu du
# coureur -> R9 ; une variable retiree de la purge -> R9b/R9c ; releve SKIP ignore -> R10 ; test du verrou --at
# retire de la branche « liste absente » -> R7c ; branche « collecte en erreur » retiree -> R10d.
# HORS DE CE BANC : la jambe --linux (docker), Git Bash, la porte adoptant jouee (seul son refus de --rouges l'est),
# les reglages NON purges (PATH, PYTHONPATH, ENV, fonctions exportees BASH_FUNC_*, conftest de l'arbre).
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/.." && pwd)"
REAL_VERIFY="$HERE/verify.sh"
REAL_RPS="$HERE/run-pytest-shards.sh"
REAL_RBT="$HERE/run-bash-tests.sh"
HOOK="$KIT/.githooks/pre-push"
for _f in "$REAL_VERIFY" "$REAL_RPS" "$REAL_RBT" "$HOOK"; do
  [ -f "$_f" ] || { echo "KO: $_f absent"; exit 1; }
done
PYBIN=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PYBIN="$c"; break; fi
done
HAS_PYTEST=0
if [ -n "$PYBIN" ] && "$PYBIN" -c 'import pytest' >/dev/null 2>&1; then HAS_PYTEST=1; fi

TMP="$(mktemp -d)"
TMP_OWNER="${BASHPID:-$$}"
cleanup() {
  if [ "${BASHPID:-$$}" = "$TMP_OWNER" ]; then rm -rf "$TMP"; fi
  return 0
}
trap cleanup EXIT
passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }
TAB="$(printf '\t')"
TO=()
if command -v timeout >/dev/null 2>&1; then TO=(timeout 300); fi

OUT=""
RC=0
# rv <depot> [VAR=val ...] [-- <arguments de verify.sh>] : verify.sh LIVRE du depot, environnement BATI ; $OUT, $RC.
rv() {
  local d="$1"
  shift
  local -a envs=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  [ "$#" -eq 0 ] || shift
  OUT="$TMP/out.$RANDOM$RANDOM"
  ( cd "$d" && env -u BASH_ENV -u BASH_TEST_TIMEOUT_BIN -u CADRE_GATE_TIMEOUT_BIN -u PYTEST_ADDOPTS -u PYTEST_PLUGINS \
      -u CADRE_GATE_ROUGES_OUT -u ROUGES_SEUL -u CADRE_GATE_JOBS -u CADRE_GATE_REPLAY -u CADRE_GATE_CHUNK -u CADRE_GATE_BASE \
      -u CADRE_SEMGREP_BASE -u VERIFY_WORKTREE_DIR VERIFY_INNER=0 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_DURATIONS_DIR="$TMP/durees" \
      ${envs[@]+"${envs[@]}"} ${TO[@]+"${TO[@]}"} bash core-scripts/verify.sh "$@" ) > "$OUT" 2>&1
  RC=$?
}
has() { grep -qF -- "$1" "$OUT"; }
mkrepo() {  # mkrepo <nom> -> chemin : depot git jouet, verify.sh LIVRE, le seau local git-ignore
  local d="$TMP/$1"
  mkdir -p "$d/core-scripts" "$d/.agents/security"
  git -C "$d" init -q
  git -C "$d" config user.email t@t
  git -C "$d" config user.name t
  git -C "$d" config core.autocrlf false
  git -C "$d" config core.hooksPath /dev/null
  cp "$REAL_VERIFY" "$d/core-scripts/verify.sh"
  printf '/.agents/state/local/\n' > "$d/.gitignore"
  printf '#!/usr/bin/env bash\n[ -z "${RV_SC_MARK:-}" ] || : > "$RV_SC_MARK"\nexit 0\n' > "$d/.agents/security/shellcheck-scan.sh"
  printf '%s\n' "$d"
}
commit_all() { git -C "$1" add -A && git -C "$1" commit -qm "$2"; }
seed() {  # seed <depot> <sha> <entree>... : une liste PORTE_ROUGES ecrite a la main
  local d="$1" s="$2" e
  shift 2
  mkdir -p "$d/.agents/state/local"
  { printf '# porte-rouges v1\nsha=%s\nmode=live\nat=fixture\n' "$s"
    for e in "$@"; do printf '%s\n' "$e"; done
  } > "$d/.agents/state/local/PORTE_ROUGES"
}
entrees() { grep -v -e '^#' -e '^sha=' -e '^mode=' -e '^at=' "$1" 2>/dev/null; }   # entrees <liste>

# ============================================================== REPO : coureurs bouchons
REPO="$(mkrepo repo)"
cat > "$REPO/core-scripts/run-pytest-shards.sh" <<'STUBPY'
#!/usr/bin/env bash
printf '%s\n' "ARGS=$*" "OUT=${CADRE_GATE_ROUGES_OUT:-ABSENT}" >> "$RV_TRACE_PY"
if [ -e "$RV_PY_KILL" ]; then kill -TERM "$PPID"; sleep 3; exit 1; fi
if [ -e "$RV_PY_RED" ]; then
  [ -z "${CADRE_GATE_ROUGES_OUT:-}" ] || printf 'tests/test_a.py\n' > "$CADRE_GATE_ROUGES_OUT"
  echo "--- [1/1] FAIL(rc=1) tests/test_a.py (bouchon)"
  exit 1
fi
echo "pytest: 2 passed in 0s (bouchon)"
exit 0
STUBPY
cat > "$REPO/core-scripts/run-bash-tests.sh" <<'STUBSH'
#!/usr/bin/env bash
printf '%s\n' "ARGS=$*" "OUT=${CADRE_GATE_ROUGES_OUT:-ABSENT}" >> "$RV_TRACE_SH"
if [ -e "$RV_SH_RED" ]; then
  [ -z "${CADRE_GATE_ROUGES_OUT:-}" ] || printf './x.test.sh\n' > "$CADRE_GATE_ROUGES_OUT"
  echo "Bash test summary: 0 passed / 1 failed / 0 timed out (of 1) / 0 missing dep / 0 skipping"
  exit 1
fi
echo "Bash test summary: 1 passed / 0 failed / 0 timed out (of 1) / 0 missing dep / 0 skipping"
exit 0
STUBSH
commit_all "$REPO" base
SHA_R="$(git -C "$REPO" rev-parse HEAD)"
LIST="$REPO/.agents/state/local/PORTE_ROUGES"
STAMP="$REPO/.agents/state/local/VERIFY_STAMP"
CHRONO="$REPO/.agents/state/local/porte-chrono.tsv"
export RV_TRACE_PY="$TMP/trace-py" RV_TRACE_SH="$TMP/trace-sh" RV_SC_MARK="$TMP/sc-mark"
export RV_PY_RED="$TMP/py-red" RV_SH_RED="$TMP/sh-red" RV_PY_KILL="$TMP/py-kill"
reset_traces() { rm -f "$RV_TRACE_PY" "$RV_TRACE_SH" "$RV_SC_MARK"; }

echo "=== R1. porte vivante ROUGE : PORTE_ROUGES = sha HEAD, mode live, une entree par coureur ; 6e colonne = 1re etape"
: > "$RV_PY_RED"; : > "$RV_SH_RED"; reset_traces
rv "$REPO"
{ [ "$RC" -eq 1 ] && has "VERIFY FAILED"; } && ok "R1 porte rouge rc 1" || ko "R1 rc $RC"
if [ "$(sed -n 's/^sha=//p' "$LIST" 2>/dev/null)" = "$SHA_R" ] && [ "$(sed -n 's/^mode=//p' "$LIST")" = "live" ] \
   && [ "$(entrees "$LIST" | tr '\n' '|')" = "pytest${TAB}tests/test_a.py|bash${TAB}./x.test.sh|" ]; then
  ok "R1 liste = pytest tests/test_a.py, bash ./x.test.sh, sha HEAD, mode live"
else
  ko "R1: liste sans entrée de coureur ($(tr '\t\n' '>|' < "$LIST" 2>/dev/null))"
fi
[ "$(tail -n 1 "$CHRONO" 2>/dev/null | cut -f6)" = "python -m pytest (CI scope, shards)" ] \
  && ok "R1 6e colonne du journal = la 1re etape rouge (ETAPE_ROUGE intact)" || ko "R1: 6e colonne déplacée ($(tail -n 1 "$CHRONO" 2>/dev/null | tr '\t' '>'))"

echo "=== R2/R3. --rouges, bascules vertes : REJEU VERT par les coureurs, shellcheck non rejoue ; aucun tampon, aucune ligne de journal"
rm -f "$RV_PY_RED" "$RV_SH_RED"; reset_traces
printf 'sha=%s\nmode=frozen\nlinux=0\nhost=fixture\nat=fixture\n' "$SHA_R" > "$STAMP"
printf 'at=fixture\tsha=%s\tmode=frozen\n' "$SHA_R" > "$STAMP.log"
cp "$STAMP" "$TMP/stamp.avant"; cp "$STAMP.log" "$TMP/stamplog.avant"; cp "$CHRONO" "$TMP/chrono.avant"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 0 ] && has "REJEU VERT @" && ! has "VERIFY OK"; } && ok "R2 rc 0, REJEU VERT, aucun VERIFY OK" || ko "R2 rc $RC ($(grep -E 'REJEU|VERIFY' "$OUT" | tr '\n' '|'))"
grep -qxF "ARGS=--only tests/test_a.py" "$RV_TRACE_PY" 2>/dev/null && ok "R2 le coureur pytest a recu --only tests/test_a.py" || ko "R2 pytest : $(tr '\n' '|' < "$RV_TRACE_PY" 2>/dev/null)"
grep -qxF "ARGS=--only ./x.test.sh" "$RV_TRACE_SH" 2>/dev/null && ok "R2 le coureur bash a recu --only ./x.test.sh" || ko "R2: suite rouge non rejouée ($(tr '\n' '|' < "$RV_TRACE_SH" 2>/dev/null))"
[ ! -e "$RV_SC_MARK" ] && ok "R2 shellcheck (vert a la porte) NON rejoue" || ko "R2 shellcheck rejoue"
{ cmp -s "$STAMP" "$TMP/stamp.avant" && cmp -s "$STAMP.log" "$TMP/stamplog.avant"; } && ok "R3 VERIFY_STAMP et son journal intacts octet pour octet" || ko "R3: tampon écrit"
cmp -s "$CHRONO" "$TMP/chrono.avant" && ok "R3 porte-chrono.tsv inchange" || ko "R3: ligne de journal"

echo "=== R4. apres un rejeu vert, la garde de push refuse toujours (aucun tampon pour ce sha)"
rm -f "$STAMP" "$STAMP.log"
rv "$REPO" -- --rouges
_z="0000000000000000000000000000000000000000"
_hook_out="$( cd "$REPO" && printf 'refs/heads/x %s refs/heads/x %s\n' "$SHA_R" "$_z" | bash "$HOOK" origin /dev/null 2>&1 )"
_hook_rc=$?
{ [ "$RC" -eq 0 ] && [ "$_hook_rc" -ne 0 ] && printf '%s' "$_hook_out" | grep -qF "nothing here says"; } \
  && ok "R4 pre-push refuse (rc $_hook_rc) : « nothing here says »" || ko "R4: push accepté (rejeu rc $RC, hook rc $_hook_rc : $_hook_out)"

echo "=== R5. porte COMPLETE verte sous ROUGES_SEUL=1 et CADRE_GATE_ROUGES_OUT empoisonne exportes : tout est joue, liste effacee"
seed "$REPO" "$SHA_R" "bash${TAB}./x.test.sh"
reset_traces
rv "$REPO" ROUGES_SEUL=1 "CADRE_GATE_ROUGES_OUT=$TMP/poison"
{ [ "$RC" -eq 0 ] && has "VERIFY OK" && [ -e "$RV_TRACE_PY" ] && [ -e "$RV_TRACE_SH" ] && [ -e "$RV_SC_MARK" ]; } \
  && ok "R5 trois etapes jouees, VERIFY OK" || ko "R5: porte complète non jouée (rc $RC ; $(grep -E 'REJEU|VERIFY|purgé' "$OUT" | tr '\n' '|'))"
[ ! -e "$LIST" ] && ok "R5 PORTE_ROUGES efface a l'entree" || ko "R5: liste survivante"
{ [ ! -e "$TMP/poison" ] && ! grep -qF "OUT=$TMP/poison" "$RV_TRACE_PY" "$RV_TRACE_SH" 2>/dev/null; } && ok "R5 la valeur heritee n'atteint aucun coureur" || ko "R5 poison atteint"
{ has "verify.sh: réglage purgé à l'entrée : ROUGES_SEUL" && has "verify.sh: réglage purgé à l'entrée : CADRE_GATE_ROUGES_OUT"; } \
  && ok "R5 la purge est DITE (une ligne par reglage pose)" || ko "R5 purge muette"

echo "=== R5b. porte tuee avant son verdict : la liste ANCIENNE (sha ancetre) ne survit pas"
git -C "$REPO" commit -q --allow-empty -m second
SHA_R2="$(git -C "$REPO" rev-parse HEAD)"
seed "$REPO" "$SHA_R" "bash${TAB}./x.test.sh"
: > "$RV_PY_KILL"
{ rv "$REPO"; } 2>/dev/null   # le shell du banc annonce la mort par signal du sous-shell : bruit, pas un verdict
rm -f "$RV_PY_KILL"
_rc_kill="$RC"
rv "$REPO" -- --rouges
{ [ "$_rc_kill" -ne 0 ] && [ "$RC" -eq 2 ] && has "--rouges: aucune porte rouge mémorisée"; } \
  && ok "R5b porte tuee (rc $_rc_kill) puis --rouges : rc 2, aucune porte rouge memorisee" || ko "R5b: liste périmée rejouée (porte rc $_rc_kill, rejeu rc $RC)"

echo "=== R6. sous --rouges, un CADRE_GATE_ROUGES_OUT herite n'atteint aucun fils"
seed "$REPO" "$SHA_R2" "pytest${TAB}tests/test_a.py" "bash${TAB}./x.test.sh"
reset_traces
rv "$REPO" "CADRE_GATE_ROUGES_OUT=$TMP/poison" -- --rouges
{ [ "$RC" -eq 0 ] && grep -qxF "OUT=ABSENT" "$RV_TRACE_PY" && grep -qxF "OUT=ABSENT" "$RV_TRACE_SH"; } \
  && ok "R6 les coureurs tracent ABSENT" || ko "R6: variable héritée atteint un fils (rc $RC ; $(cat "$RV_TRACE_PY" "$RV_TRACE_SH" 2>/dev/null | tr '\n' '|'))"

echo "=== R7. aucun credit : etape sans coureur, liste absente, vide, hors lignee, --at/--linux, chemins non admis"
seed "$REPO" "$SHA_R2" "etape${TAB}linux replay" "pytest${TAB}tests/test_a.py" "bash${TAB}./x.test.sh"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "REJEU INCOMPLET @" && has "--- REJEU IMPOSSIBLE étape linux replay" && ! has "REJEU VERT"; } \
  && ok "R7 etape linux replay + entrees vertes : rc 2 REJEU INCOMPLET" || ko "R7: crédit sans jouer (rc $RC ; $(grep -E 'REJEU' "$OUT" | tr '\n' '|'))"
seed "$REPO" "$SHA_R2" "etape${TAB}?"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "REJEU INCOMPLET @"; } && ok "R7 etape ? : rc 2 REJEU INCOMPLET" || ko "R7: crédit sans jouer (etape ?, rc $RC)"
rm -f "$LIST"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: aucune porte rouge mémorisée"; } && ok "R7 liste absente : rc 2" || ko "R7 absente rc $RC"
#   R7c : liste absente PENDANT une porte --at (son verrou existe) -> attendre son verdict, jamais une seconde porte.
#   MUTANT : test du verrou retire -> « aucune porte rouge mémorisée » -> KO.
mkdir "$TMP/repo-verify.lock"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: une porte --at tient $TMP/repo-verify.lock et a effacé la liste — attends son verdict" && ! has "joue la porte complète"; } \
  && ok "R7c verrou par defaut <racine>-verify.lock : rc 2, attends son verdict" || ko "R7c: verrou --at ignoré (rc $RC ; $(cat "$OUT" | tr '\n' '|'))"
rmdir "$TMP/repo-verify.lock"
mkdir "$TMP/wt7.lock"
rv "$REPO" "VERIFY_WORKTREE_DIR=$TMP/wt7" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: une porte --at tient $TMP/wt7.lock et a effacé la liste — attends son verdict"; } \
  && ok "R7c verrou VERIFY_WORKTREE_DIR.lock : rc 2, attends son verdict" || ko "R7c: verrou VERIFY_WORKTREE_DIR ignoré (rc $RC)"
rmdir "$TMP/wt7.lock"
seed "$REPO" "$SHA_R2"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: liste vide"; } && ok "R7 en-tete seul : rc 2 liste vide" || ko "R7 vide rc $RC"
_orph="$(git -C "$REPO" commit-tree "$(git -C "$REPO" rev-parse 'HEAD^{tree}')" -m orphelin)"
seed "$REPO" "$_orph" "bash${TAB}./x.test.sh"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: porte d'une autre lignée"; } && ok "R7 sha hors lignee : rc 2" || ko "R7 lignee rc $RC"
seed "$REPO" "--help" "bash${TAB}./x.test.sh"
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: porte d'une autre lignée"; } && ok "R7 sha non hexadecimal : rc 2" || ko "R7 sha option rc $RC"
rv "$REPO" -- --rouges --at HEAD
{ [ "$RC" -eq 2 ] && has "--rouges est seul"; } && ok "R7 --rouges --at HEAD : rc 2" || ko "R7 --at rc $RC"
rv "$REPO" -- --linux --rouges
{ [ "$RC" -eq 2 ] && has "--rouges est seul"; } && ok "R7 --rouges --linux : rc 2" || ko "R7 --linux rc $RC"
seed "$REPO" "$SHA_R2" "pytest${TAB}-x.py" "pytest${TAB}../a.py"
reset_traces
rv "$REPO" -- --rouges
{ [ "$RC" -eq 2 ] && [ ! -e "$RV_TRACE_PY" ] && [ "$(grep -c -- '--- REJEU IMPOSSIBLE pytest' "$OUT")" -eq 2 ]; } \
  && ok "R7 -x.py et ../a.py refuses SANS appel du coureur" || ko "R7 chemins rc $RC trace=$([ -e "$RV_TRACE_PY" ] && echo appele || echo absent)"

echo "=== R7b. --rouges refuse sous VERIFY_INNER=1 et en porte adoptant"
seed "$REPO" "$SHA_R2" "bash${TAB}./x.test.sh"
rv "$REPO" VERIFY_INNER=1 -- --rouges
{ [ "$RC" -eq 2 ] && has "--rouges: refusé sous VERIFY_INNER=1"; } && ok "R7b inner : rc 2" || ko "R7b: inner (rc $RC)"
: > "$REPO/.agents/security/module_discovery.py"
rv "$REPO" -- --rouges
rm -f "$REPO/.agents/security/module_discovery.py"
{ [ "$RC" -eq 2 ] && has "--rouges: sans objet en porte adoptant"; } && ok "R7b adoptant : rc 2" || ko "R7b: adoptant (rc $RC)"

# ============================================================== REPO8 : le VRAI run-bash-tests.sh sous --at
echo "=== R8. bout a bout sous --at, vrai run-bash-tests.sh : la liste du clone revient au vivant, puis un --at vert l'efface"
REPO8="$(mkrepo repo8)"
cp "$REAL_RBT" "$REPO8/core-scripts/run-bash-tests.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$REPO8/core-scripts/run-pytest-shards.sh"
printf '#!/usr/bin/env bash\necho r-rouge\nexit 1\n' > "$REPO8/r.test.sh"
commit_all "$REPO8" rouge
SHA8A="$(git -C "$REPO8" rev-parse HEAD)"
printf '#!/usr/bin/env bash\nexit 0\n' > "$REPO8/r.test.sh"
commit_all "$REPO8" vert
SHA8B="$(git -C "$REPO8" rev-parse HEAD)"
LIST8="$REPO8/.agents/state/local/PORTE_ROUGES"
rv "$REPO8" "VERIFY_WORKTREE_DIR=$TMP/wt8" -- --at "$SHA8A"
if [ "$RC" -eq 1 ] && [ "$(sed -n 's/^sha=//p' "$LIST8" 2>/dev/null)" = "$SHA8A" ] && [ "$(sed -n 's/^mode=//p' "$LIST8")" = "frozen" ] \
   && [ "$(entrees "$LIST8" | tr '\n' '|')" = "bash${TAB}./r.test.sh|" ]; then
  ok "R8 --at rouge : liste vivante sha=<SHA>, mode=frozen, bash ./r.test.sh"
else
  ko "R8: liste perdue au travers de --at (rc $RC ; $(tr '\t\n' '>|' < "$LIST8" 2>/dev/null))"
fi
rv "$REPO8" "VERIFY_WORKTREE_DIR=$TMP/wt8" -- --at "$SHA8B"
{ [ "$RC" -eq 0 ] && [ ! -e "$LIST8" ]; } && ok "R8 --at vert : liste effacee" || ko "R8: liste survivante (rc $RC)"

echo "=== R8b. relecture du clone : un lien, 65 Kio, un sha etranger donnent « etape ? » seul"
cat > "$TMP/inner.sh" <<'INNER'
#!/usr/bin/env bash
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$(git -C "$R" rev-parse HEAD)"
L="$R/.agents/state/local"
mkdir -p "$L"
T="$(printf '\t')"
bon() { printf '# porte-rouges v1\nsha=%s\nmode=live\nat=x\nbash%s./r.test.sh\n' "$1" "$T"; }
if [ "$RV_INNER" = "lien" ]; then
  bon "$S" > "$L/vrai"
  ln -s "$L/vrai" "$L/PORTE_ROUGES"
elif [ "$RV_INNER" = "gros" ]; then
  { bon "$S"; i=0; while [ "$i" -lt 1200 ]; do printf 'at=padding padding padding padding padding padding padding\n'; i=$((i + 1)); done; } > "$L/PORTE_ROUGES"
elif [ "$RV_INNER" = "etranger" ]; then
  bon 0000000000000000000000000000000000000000 > "$L/PORTE_ROUGES"
else
  bon "$S" > "$L/PORTE_ROUGES"
fi
exit 1
INNER
_blob="$(git -C "$REPO8" hash-object -w "$TMP/inner.sh")"
GIT_INDEX_FILE="$TMP/idx8" git -C "$REPO8" read-tree "$SHA8B"
GIT_INDEX_FILE="$TMP/idx8" git -C "$REPO8" update-index --add --cacheinfo "100755,$_blob,core-scripts/verify.sh"
SHA8C="$(git -C "$REPO8" commit-tree "$(GIT_INDEX_FILE="$TMP/idx8" git -C "$REPO8" write-tree)" -p "$SHA8B" -m interieur)"
for _m in temoin lien gros etranger; do
  rm -f "$LIST8"
  rv "$REPO8" "VERIFY_WORKTREE_DIR=$TMP/wt8" "RV_INNER=$_m" -- --at "$SHA8C"
  _e="$(entrees "$LIST8" | tr '\n' '|')"
  if [ "$_m" = "temoin" ]; then
    { [ "$RC" -eq 1 ] && [ "$_e" = "bash${TAB}./r.test.sh|" ]; } && ok "R8b temoin : la liste valide du clone est relue" || ko "R8b temoin rc $RC « $_e »"
  else
    { [ "$RC" -eq 1 ] && [ "$_e" = "etape${TAB}?|" ]; } && ok "R8b $_m : etape ? seule" || ko "R8b: $_m crédité (« $_e »)"
  fi
done

# ============================================================== FX / FX2 : les VRAIS coureurs
if [ "$HAS_PYTEST" -eq 0 ]; then
  echo "SKIP: pytest absent — R9, R9b, R9c et R10 (vrais coureurs) NON joues : ce vert n'est PAS la couverture complete"
else
mkfx() {  # mkfx <nom> <pytest rouge 0|1> <bash rouge 0|1>
  local d
  d="$(mkrepo "$1")"
  cp "$REAL_RPS" "$d/core-scripts/run-pytest-shards.sh"
  cp "$REAL_RBT" "$d/core-scripts/run-bash-tests.sh"
  mkdir -p "$d/tests"
  printf '[pytest]\ntestpaths = tests\n' > "$d/pytest.ini"
  printf 'def test_c():\n    pass\n' > "$d/tests/test_c.py"
  printf 'import pytest\n\n\n%spytest.mark.skip(reason="R10b")\ndef test_s():\n    pass\n' '@' > "$d/tests/test_s.py"
  if [ "$2" -eq 1 ]; then printf 'def test_a1():\n    assert False\n\n\ndef test_a2():\n    assert False\n' > "$d/tests/test_a.py"; fi
  printf 'import pytest\n\n\n%spytest.hookimpl(tryfirst=True)\ndef pytest_pyfunc_call(pyfuncitem):\n    return True\n' '@' > "$d/credit.py"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/zz-vert.test.sh"
  if [ "$3" -eq 1 ]; then
    printf '#!/usr/bin/env bash\necho rouge-joue\nexit 1\n' > "$d/zz-rouge.test.sh"
    printf '#!/usr/bin/env bash\necho "SKIP: rien a prouver ici"\nexit 0\n' > "$d/zz-skip.test.sh"
  fi
  commit_all "$d" base
  printf '%s\n' "$d"
}
FX="$(mkfx fx 1 0)"
FX2="$(mkfx fx2 0 1)"
SHA_FX="$(git -C "$FX" rev-parse HEAD)"
SHA_FX2="$(git -C "$FX2" rev-parse HEAD)"
printf '#!/usr/bin/env bash\necho "99 passed in 0.01s"\nexit 0\n' > "$TMP/faux-timeout"
chmod +x "$TMP/faux-timeout"
printf 'case "$0" in\n  *.test.sh) exit 0 ;;\nesac\n' > "$TMP/bash-env"

echo "=== R9. attribution par le coureur : --rouges sur pytest tests/test_a.py rend REJEU ROUGE et la ligne --- [i/N] du pool"
seed "$FX" "$SHA_FX" "pytest${TAB}tests/test_a.py"
rv "$FX" -- --rouges
{ [ "$RC" -eq 1 ] && has "REJEU ROUGE @" && grep -qE '^--- \[[0-9]+/[0-9]+\] FAIL\(rc=1\) tests/test_a\.py' "$OUT"; } \
  && ok "R9 rc 1, REJEU ROUGE, attribution --- [i/N] FAIL(rc=1) tests/test_a.py" || ko "R9: pytest rejoué hors coureur (rc $RC ; $(grep -E 'REJEU|^--- ' "$OUT" | tr '\n' '|'))"

echo "=== R9b. porte COMPLETE vivante, un reglage purge herite seul par bras : VERIFY FAILED et la purge dite"
r9b() {  # r9b <depot> <NOM> <ligne FAIL attendue> <VAR=val>...
  local d="$1" nom="$2" attendu="$3"
  shift 3
  rv "$d" "$@"
  { [ "$RC" -eq 1 ] && has "VERIFY FAILED" && has "$attendu"; } \
    && ok "R9b $nom : VERIFY FAILED, « $attendu »" || ko "R9b: porte complète créditée sans jouer ($nom ; rc $RC ; $(grep -E '^--- |VERIFY|purgé' "$OUT" | tr '\n' '|'))"
  has "verify.sh: réglage purgé à l'entrée : $nom" && ok "R9b $nom : la purge est dite sur stderr" || ko "R9b: purge muette ($nom)"
}
r9b "$FX2" BASH_TEST_TIMEOUT_BIN "--- FAIL bash core-scripts/run-bash-tests.sh (exit 1)" BASH_TEST_TIMEOUT_BIN=true
r9b "$FX2" BASH_ENV "--- FAIL bash core-scripts/run-bash-tests.sh (exit 1)" "BASH_ENV=$TMP/bash-env"
r9b "$FX" PYTEST_ADDOPTS "--- FAIL python -m pytest (CI scope, shards) (exit 1)" PYTEST_ADDOPTS=--co CADRE_GATE_JOBS=1
r9b "$FX" PYTEST_PLUGINS "--- FAIL python -m pytest (CI scope, shards) (exit 1)" PYTEST_PLUGINS=credit CADRE_GATE_JOBS=2
r9b "$FX" CADRE_GATE_TIMEOUT_BIN "--- FAIL python -m pytest (CI scope, shards) (exit 1)" "CADRE_GATE_TIMEOUT_BIN=$TMP/faux-timeout" CADRE_GATE_JOBS=2

echo "=== R9c. --rouges, les memes cinq reglages, un par bras : REJEU ROUGE"
r9c() {  # r9c <depot> <sha> <entree> <NOM> <VAR=val>...
  local d="$1" s="$2" e="$3" nom="$4"
  shift 4
  seed "$d" "$s" "$e"
  rv "$d" "$@" -- --rouges
  { [ "$RC" -eq 1 ] && has "REJEU ROUGE @"; } && ok "R9c $nom : REJEU ROUGE" || ko "R9c: rejeu crédité sans jouer ($nom ; rc $RC ; $(grep -E 'REJEU' "$OUT" | tr '\n' '|'))"
}
r9c "$FX2" "$SHA_FX2" "bash${TAB}./zz-rouge.test.sh" BASH_TEST_TIMEOUT_BIN BASH_TEST_TIMEOUT_BIN=true
r9c "$FX2" "$SHA_FX2" "bash${TAB}./zz-rouge.test.sh" BASH_ENV "BASH_ENV=$TMP/bash-env"
r9c "$FX" "$SHA_FX" "pytest${TAB}tests/test_a.py" PYTEST_ADDOPTS "PYTEST_ADDOPTS=-p credit"
r9c "$FX" "$SHA_FX" "pytest${TAB}tests/test_a.py" PYTEST_PLUGINS PYTEST_PLUGINS=credit
r9c "$FX" "$SHA_FX" "pytest${TAB}tests/test_a.py" CADRE_GATE_TIMEOUT_BIN "CADRE_GATE_TIMEOUT_BIN=$TMP/faux-timeout"

echo "=== R10. une suite qui annonce un SKIP n'est jamais creditee : REJEU IMPOSSIBLE, rc 2"
seed "$FX2" "$SHA_FX2" "bash${TAB}./zz-skip.test.sh"
rv "$FX2" -- --rouges
{ [ "$RC" -eq 2 ] && has "--- REJEU IMPOSSIBLE ./zz-skip.test.sh (SKIP annoncé" && has "REJEU INCOMPLET @"; } \
  && ok "R10 SKIP : rc 2, REJEU IMPOSSIBLE" || ko "R10: SKIP crédité (rc $RC ; $(grep -E 'REJEU' "$OUT" | tr '\n' '|'))"

echo "=== R10b. un fichier pytest dont TOUS les tests sont sautes n'est jamais credite : REJEU IMPOSSIBLE, rc 2"
#   MUTANT : garde « au moins un passed » retiree -> rc 0 REJEU VERT -> KO.
seed "$FX" "$SHA_FX" "pytest${TAB}tests/test_s.py"
rv "$FX" -- --rouges
{ [ "$RC" -eq 2 ] && has "--- REJEU IMPOSSIBLE pytest (1 fichier(s)) (aucun test joué" && has "REJEU INCOMPLET @" && has "1 skipped"; } \
  && ok "R10b tout saute : rc 2, REJEU IMPOSSIBLE" || ko "R10b: pytest tout sauté crédité (rc $RC ; $(grep -E 'REJEU|^pytest: ' "$OUT" | tr '\n' '|'))"

echo "=== R10c. BORNE EPINGLEE : la garde juge le TOTAL d'un appel du coureur — un fichier tout saute a cote d'un fichier qui passe EST credite"
#   Ce bras CHANGE le jour ou le jugement passe par fichier (attendre alors REJEU INCOMPLET rc 2) : jamais l'inverse en silence.
seed "$FX" "$SHA_FX" "pytest${TAB}tests/test_c.py" "pytest${TAB}tests/test_s.py"
rv "$FX" -- --rouges
{ [ "$RC" -eq 0 ] && has "REJEU VERT @" && has "1 passed, 1 skipped"; } \
  && ok "R10c borne : test_c.py (passe) + test_s.py (tout saute) -> REJEU VERT 2/2, credite" || ko "R10c: la borne a bougé (rc $RC ; $(grep -E 'REJEU|^pytest: ' "$OUT" | tr '\n' '|')) — mettre le bras et SKILL.md a jour"

echo "=== R10d. une collecte pytest en erreur (import casse) est un ROUGE joue : REJEU ROUGE, rc 1, jamais IMPOSSIBLE"
#   MUTANT : branche « collecte en erreur » retiree -> rc 2 REJEU INCOMPLET -> KO.
printf 'import module_absent_r10d\n\n\ndef test_b():\n    pass\n' > "$FX/tests/test_b.py"
seed "$FX" "$SHA_FX" "pytest${TAB}tests/test_b.py"
rv "$FX" -- --rouges
{ [ "$RC" -eq 1 ] && has "--- REJEU FAIL pytest (1 fichier(s)) (collecte en erreur, exit 2)" && has "REJEU ROUGE @" && ! has "REJEU IMPOSSIBLE"; } \
  && ok "R10d import casse : rc 1, REJEU ROUGE" || ko "R10d: collecte en erreur non jugée rouge (rc $RC ; $(grep -E 'REJEU|collecte' "$OUT" | tr '\n' '|'))"
rm -f "$FX/tests/test_b.py"
fi

echo
echo "================================================================"
echo "verify-rouges: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "PASS: verify --rouges — rejeu par les coureurs, sans tampon ni credit ; porte complete purgee des cinq reglages mesures."
