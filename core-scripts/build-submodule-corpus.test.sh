#!/usr/bin/env bash
# core-scripts/build-submodule-corpus.test.sh — T-00000303
#
# Prouve que le constructeur NE PEUT PLUS ANNONCER UN SUCCÈS QU'IL N'A PAS EU.
# Auto-découvert par core-scripts/run-bash-tests.sh (find *.test.sh racine-possédée).
#
# Directives lues par core-scripts/run-bash-tests.sh (T-00000427) :
# requires: git
# optional: awk
#
# `git` est REQUIS : les six cas construisent des dépôts, y ajoutent des
# sous-modules et RECOMPTENT le résultat — sans git la suite ne prouve rien, et
# son ancien `exit 0` se lisait comme un succès. Le runner refuse désormais de la
# jouer et le dit en rouge ; l'auto-esquive `command -v git` a donc été retirée.
#
# `awk` est OPTIONNEL et son repli `exit 0` est CONSERVÉ, délibérément. Rien dans
# ce dépôt n'établit qu'awk est présent sur la jambe windows-latest (Git Bash) —
# `grep awk .github/workflows/` rend 0 occurrence — donc l'exiger ferait rougir
# `ci.yml:226` sur un fait NON MESURÉ. Le repli sûr : sans awk le runner annonce
# l'optionnel absent, la suite joue, tombe sur son repli et sort 0 ; c'est
# annoncé et compté, jamais rouge. Un UNKNOWN se borne, il ne se tranche pas.
#
# Six cas, dont les NOMS portent leur borne (L-00000190) :
#   (a) nominal C1 : rc 0, dernière ligne stdout = CORPUS=, puis RECOMPTAGE
#       INDÉPENDANT (git submodule status --recursive dans le corpus → 2 sous-
#       modules initialisés) ;
#   (b) contrôle négatif — commande sabotée : le shim fait échouer `submodule add`
#       → rc ≠ 0 ET stdout ne contient PAS CORPUS= ;
#   (c) contrôle négatif — succès menteur : le shim rend `submodule update`
#       (le --recursive de la baseline) exit 0 SANS RIEN FAIRE → rc ≠ 0, et le
#       message d'échec NOMME le contrôle de complétude, pas un code de retour.
#       C'EST (c) QUI PROUVE QUE LE CONTRÔLE MESURE AU LIEU DE TIRER.
#   (d) assertion de détectabilité, bras rc=0 : un shim `gitleaks` qui exit 0
#       (« 0 finding ») fait DIE le constructeur → rc ≠ 0 ET pas de CORPUS= ;
#   (e) assertion de détectabilité, bras « autre rc » : un shim `gitleaks` qui
#       exit 7 (erreur) NE bloque PAS → rc global 0, CORPUS= présent, et stderr
#       porte « corpus non défendu » (non-fail-open PROUVÉ — sans (e) cette
#       branche ne serait exercée par aucun cas) ;
#   (f) anti-dérive DÉTERMINISTE (aucun gitleaks requis) : le jeton `body="…"` du
#       constructeur est octet-pour-octet celui de la suite déterministe
#       `.agents/security/gitleaks-scan.test.sh`.
#
# Deux familles de shim préposées au PATH. Le shim `git` (make_shim) n'intercepte
# QUE `submodule add`/`submodule update` et TRANSFÈRE le reste à REAL_GIT (argv
# intact, rc propagé, contrat de transfert). Le shim `gitleaks` (make_gitleaks_shim,
# cas d/e) IMPOSE un code de retour et n'appelle jamais le vrai binaire. Dans les
# deux cas le marqueur est posé À L'APPEL : marqueur absent ⇒ la suite REFUSE de
# conclure (L-00000186), car un rc pourrait alors venir d'ailleurs que du shim.
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/build-submodule-corpus.sh"
[ -f "$SCRIPT" ] || { echo "FAIL: $SCRIPT introuvable"; exit 1; }
command -v awk >/dev/null 2>&1 || { echo "SKIP: no awk"; exit 0; }

# REAL_GIT résolu en chemin ABSOLU AVANT toute préposition du shim au PATH —
# sinon le shim se rappellerait lui-même à l'infini.
REAL_GIT="$(command -v git)"
case "$REAL_GIT" in
  /*) : ;;
  *)  REAL_GIT="$(cd "$(dirname "$REAL_GIT")" && pwd)/$(basename "$REAL_GIT")" ;;
esac
export REAL_GIT

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/corpus-test.XXXXXX")" || { echo "FAIL: mktemp"; exit 1; }
CORPORA=()
cleanup() {
  local c
  for c in "${CORPORA[@]:-}"; do [ -n "$c" ] && [ -d "$c" ] && rm -rf "$c"; done
  rm -rf "$TMPROOT"
  return 0
}
trap cleanup EXIT

pass=0; fail=0
ok() { echo "  ok  — $1"; pass=$((pass + 1)); }
ko() { echo "  KO  — $1" >&2; fail=$((fail + 1)); }

# --- le shim : un `git` qui intercepte submodule add/update, transfère le reste -
# Le sous-commande n'est JAMAIS $1 : $GIT s'expanse en `git -c k=v … [-C chemin]
# <sous-commande>`. Le filtre saute les paires `-c <k=v>` ET `-C <chemin>` jusqu'au
# premier jeton non-option, qui est le sous-commande apparié. Le no-op de update
# est verrouillé sur --recursive : il ne vise QUE l'appel de la baseline (ligne
# `submodule update -q --init --recursive`), jamais un update interne éventuel.
make_shim() {  # $1 = répertoire qui portera le shim
  local d="$1"
  mkdir -p "$d"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'args=("$@"); i=0; n=${#args[@]}; sub=""; subarg=""\n'
    printf 'while [ "$i" -lt "$n" ]; do t="${args[$i]}"\n'
    printf '  case "$t" in\n'
    printf '    -c|-C) i=$((i + 2)); continue ;;\n'
    printf '    -*)    i=$((i + 1)); continue ;;\n'
    printf '    *)     sub="$t"; subarg="${args[$((i + 1))]:-}"; break ;;\n'
    printf '  esac\n'
    printf 'done\n'
    printf 'if [ "$sub" = submodule ] && [ "$subarg" = add ]; then\n'
    printf '  printf "submodule-add\\n" >> "$SHIM_MARKER"\n'
    printf '  [ "${SHIM_FAIL_SUBMODULE_ADD:-0}" = 1 ] && exit 3\n'
    printf 'fi\n'
    printf 'if [ "$sub" = submodule ] && [ "$subarg" = update ]; then\n'
    printf '  printf "submodule-update\\n" >> "$SHIM_MARKER"\n'
    printf '  if [ "${SHIM_NOOP_SUBMODULE_UPDATE:-0}" = 1 ]; then\n'
    printf '    for a in "$@"; do [ "$a" = --recursive ] && exit 0; done\n'
    printf '  fi\n'
    printf 'fi\n'
    printf 'exec "$REAL_GIT" "$@"\n'
  } > "$d/git"
  chmod +x "$d/git"
}

# --- le shim gitleaks : impose un code de retour, n'appelle jamais le vrai binaire
# make_shim ne fabrique que des `git` ; les cas (d)/(e) écrivent leur propre
# `gitleaks` pour piloter le CANAL DE RETOUR de l'assertion de détectabilité du
# constructeur. Il POSE un marqueur À L'APPEL puis exit avec le code demandé —
# marqueur absent ⇒ REFUS de conclure (L-00000186). Il ne scanne rien : le but est
# le rc, pas la mesure.
make_gitleaks_shim() {  # $1 = répertoire porteur ; $2 = code de sortie imposé
  local d="$1" code="$2"
  mkdir -p "$d"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'printf "gitleaks\\n" >> "$SHIM_MARKER"\n'
    printf 'exit %s\n' "$code"
  } > "$d/gitleaks"
  chmod +x "$d/gitleaks"
}

# --- (a) nominal C1 : rc 0, CORPUS= en dernière ligne, recomptage indépendant ---
test_a_nominal_c1_two_initialized_submodules() {
  local out rc last corpus status n
  out="$(bash "$SCRIPT" C1 2>/dev/null)"; rc=$?
  if [ "$rc" -ne 0 ]; then ko "(a) nominal C1 : rc=$rc, attendu 0"; return; fi
  last="$(printf '%s\n' "$out" | tail -n1)"
  case "$last" in
    CORPUS=*) : ;;
    *) ko "(a) dernière ligne stdout n'est pas CORPUS= : '$last'"; return ;;
  esac
  corpus="${last#CORPUS=}"
  CORPORA+=("$corpus")
  [ -d "$corpus" ] || { ko "(a) corpus inexistant : $corpus"; return; }
  # RECOMPTAGE INDÉPENDANT — recalculé ici, jamais relu du constructeur.
  status="$("$REAL_GIT" -C "$corpus" submodule status --recursive)" \
    || { ko "(a) submodule status --recursive a échoué dans le corpus"; return; }
  n="$(printf '%s\n' "$status" | awk 'NF{c++} END{print c + 0}')"
  [ "$n" -eq 2 ] || { ko "(a) attendu 2 sous-modules, recompté $n"; return; }
  if printf '%s\n' "$status" | grep -qE '^[-+U]'; then
    ko "(a) au moins un sous-module non initialisé au recomptage : $status"; return
  fi
  ok "(a) nominal C1 : CORPUS=, 2 sous-modules initialisés (recomptés indépendamment)"
}

# --- (b) commande sabotée : submodule add échoue → rc≠0 ET pas de CORPUS= -------
test_b_sabotaged_submodule_add_no_corpus() {
  local shimdir marker out rc
  shimdir="$TMPROOT/shim_b"; marker="$TMPROOT/marker_b"; : > "$marker"
  make_shim "$shimdir"
  out="$(SHIM_MARKER="$marker" SHIM_FAIL_SUBMODULE_ADD=1 \
         PATH="$shimdir:$PATH" bash "$SCRIPT" C1 2>/dev/null)"; rc=$?
  # CONTRÔLE POSITIF : le sous-commande CIBLÉ a bien été apparié.
  if ! grep -q '^submodule-add$' "$marker"; then
    ko "(b) REFUS DE CONCLURE — marqueur 'submodule add' absent : le shim n'a pas apparié (L-00000186)"; return
  fi
  [ "$rc" -ne 0 ] || { ko "(b) rc=0 alors que submodule add est saboté"; return; }
  case "$out" in
    *CORPUS=*) ko "(b) CORPUS= imprimé malgré l'échec de submodule add"; return ;;
  esac
  ok "(b) commande sabotée : rc=${rc}≠0 et aucun CORPUS= (marqueur présent)"
}

# --- (c) succès menteur : update no-op → rc≠0 nommé par le contrôle de complétude
test_c_lying_success_update_noop_named_by_completeness_control() {
  local shimdir marker errfile out rc err
  shimdir="$TMPROOT/shim_c"; marker="$TMPROOT/marker_c"; errfile="$TMPROOT/err_c"
  : > "$marker"
  make_shim "$shimdir"
  out="$(SHIM_MARKER="$marker" SHIM_NOOP_SUBMODULE_UPDATE=1 \
         PATH="$shimdir:$PATH" bash "$SCRIPT" C1 2>"$errfile")"; rc=$?
  err="$(cat "$errfile")"
  # CONTRÔLE POSITIF : le `submodule update` ciblé a bien été apparié.
  if ! grep -q '^submodule-update$' "$marker"; then
    ko "(c) REFUS DE CONCLURE — marqueur 'submodule update' absent : le shim n'a pas apparié (L-00000186)"; return
  fi
  [ "$rc" -ne 0 ] || { ko "(c) rc=0 : le succès menteur a passé — le contrôle ne MESURE pas"; return; }
  case "$out" in
    *CORPUS=*) ko "(c) CORPUS= imprimé sur un corpus incomplet"; return ;;
  esac
  # Le message d'échec NOMME le contrôle de complétude, pas un code de retour.
  case "$err" in
    *"contrôle de complétude"*) : ;;
    *) ko "(c) l'échec n'invoque pas le contrôle de complétude : $err"; return ;;
  esac
  ok "(c) succès menteur : rc=${rc}≠0, échec nommé par le contrôle de complétude (preuve qu'il MESURE)"
}

# --- (d) assertion détectabilité, bras rc=0 : gitleaks aveugle → die, pas de CORPUS=
test_d_gitleaks_blind_exit0_dies_no_corpus() {
  local shimdir marker out rc
  shimdir="$TMPROOT/shim_gd"; marker="$TMPROOT/marker_gd"; : > "$marker"
  make_gitleaks_shim "$shimdir" 0
  out="$(SHIM_MARKER="$marker" PATH="$shimdir:$PATH" bash "$SCRIPT" C1 2>/dev/null)"; rc=$?
  # CONTRÔLE POSITIF : le shim gitleaks a bien été appelé.
  if ! grep -q '^gitleaks$' "$marker"; then
    ko "(d) REFUS DE CONCLURE — marqueur 'gitleaks' absent : le shim n'a pas été appelé (L-00000186)"; return
  fi
  [ "$rc" -ne 0 ] || { ko "(d) rc=0 alors que gitleaks ne détecte rien (bras rc=0 → die attendu)"; return; }
  case "$out" in
    *CORPUS=*) ko "(d) CORPUS= imprimé alors que le jeton n'est pas détecté"; return ;;
  esac
  ok "(d) gitleaks aveugle (exit 0) : rc=${rc}≠0 et aucun CORPUS= (marqueur présent)"
}

# --- (e) assertion détectabilité, bras « autre rc » : gitleaks en erreur → non-fail-open
test_e_gitleaks_error_exit7_not_fail_open() {
  local shimdir marker errfile out rc err last corpus
  shimdir="$TMPROOT/shim_ge"; marker="$TMPROOT/marker_ge"; errfile="$TMPROOT/err_ge"
  : > "$marker"
  make_gitleaks_shim "$shimdir" 7
  out="$(SHIM_MARKER="$marker" PATH="$shimdir:$PATH" bash "$SCRIPT" C1 2>"$errfile")"; rc=$?
  err="$(cat "$errfile")"
  # CONTRÔLE POSITIF : le shim gitleaks a bien été appelé.
  if ! grep -q '^gitleaks$' "$marker"; then
    ko "(e) REFUS DE CONCLURE — marqueur 'gitleaks' absent : le shim n'a pas été appelé (L-00000186)"; return
  fi
  [ "$rc" -eq 0 ] || { ko "(e) rc=${rc}≠0 : une erreur gitleaks (rc=7) ne doit PAS bloquer le build (fail-open interdit ⇒ ici non-blocage)"; return; }
  case "$out" in
    *CORPUS=*) : ;;
    *) ko "(e) CORPUS= absent : le build aurait dû aboutir malgré l'erreur gitleaks"; return ;;
  esac
  case "$err" in
    *"corpus non défendu"*) : ;;
    *) ko "(e) stderr n'annonce pas « corpus non défendu » sur erreur gitleaks : $err"; return ;;
  esac
  last="$(printf '%s\n' "$out" | tail -n1)"; corpus="${last#CORPUS=}"
  CORPORA+=("$corpus")
  ok "(e) gitleaks en erreur (exit 7) : rc=0, CORPUS= présent, « corpus non défendu » dit (non-fail-open)"
}

# --- (f) anti-dérive DÉTERMINISTE : jeton du générateur == jeton de la suite ------
test_f_token_no_drift_from_deterministic_suite() {
  local ref_file gen ref
  ref_file="$HERE/../.agents/security/gitleaks-scan.test.sh"
  [ -f "$ref_file" ] || { ko "(f) suite de référence introuvable : $ref_file"; return; }
  gen="$(grep -oE 'body="[A-Z2-7]+"' "$SCRIPT" | head -n1)"
  ref="$(grep -oE 'body="[A-Z2-7]+"' "$ref_file" | head -n1)"
  [ -n "$gen" ] || { ko "(f) ligne body=\"…\" introuvable dans le générateur"; return; }
  [ -n "$ref" ] || { ko "(f) ligne body=\"…\" introuvable dans gitleaks-scan.test.sh"; return; }
  [ "$gen" = "$ref" ] || { ko "(f) DÉRIVE du jeton : générateur=$gen ≠ suite=$ref"; return; }
  ok "(f) anti-dérive : body= identique au jeton vérifié-détectable de la suite déterministe"
}

echo "== build-submodule-corpus.test.sh =="
test_a_nominal_c1_two_initialized_submodules
test_b_sabotaged_submodule_add_no_corpus
test_c_lying_success_update_noop_named_by_completeness_control
test_d_gitleaks_blind_exit0_dies_no_corpus
test_e_gitleaks_error_exit7_not_fail_open
test_f_token_no_drift_from_deterministic_suite
echo
echo "TOTAL: $((pass + fail)) cas — $pass ok, $fail KO"
[ "$fail" -eq 0 ] || exit 1
exit 0
