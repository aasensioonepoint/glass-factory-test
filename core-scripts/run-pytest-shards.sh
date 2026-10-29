#!/usr/bin/env bash
# run-pytest-shards.sh — la jambe python de la porte : la collecte NUE de pytest, jouee en
# UNITES paralleles (un fichier entier, ou une tranche contigue d'un gros fichier), tirees
# d'une file par un pool borne. Le perimetre est celui de `python -m pytest` NU (pytest.ini
# decide) : il est LU par `--collect-only`, jamais recalcule ici (T-00001122).
#
# VERT seulement si TOUT tient (le verdict d'un fichier ne se lit JAMAIS sur le seul rc) :
#   (V1)  la collecte nue rend rc 0 ; sinon on rend SON rc (2 erreur, 5 vide : semantique nue
#         inchangee) sans rien lancer ;
#   (V1b) le TOTAL des lignes `fichier.py::id` de la collecte egale celui que pytest annonce
#         lui-meme (`N tests collected`) ; sinon ROUGE rc 1, rien lance : un item que le motif
#         ne voit pas (doctest-glob, collecteur de plugin, un addopts -q/-v qui change le format)
#         ne serait jamais joue — la couverture n'est pas crue sur parole, elle est rapprochee
#         du compte de l'OUTIL ;
#   (V2)  les unites couvrent EXACTEMENT les ids collectes (cmp des listes triees) ;
#   (V3)  chaque unite rend rc 0 ;
#   (V4)  observes >= attendus par unite (un resume absent compte 0 : il rougit) ;
#   (V5)  toutes les unites ont ete jouees — echec rapide, chien de garde ou interruption
#         => ROUGE, jamais vert.
# rc : 0 vert ; 1 rouge ; 5 collecte vide (semantique nue) ; 2 collecte en erreur ou reglage
#      invalide ; 130/143 interrompu.
#
# Reglages (tous optionnels) :
#   CADRE_GATE_JOBS          auto | N <= 64 (au-dela : rc 2). auto = coeurs/2 bornes a [1,12] (12 des 24 coeurs, 9 sur 18) ; 1 ou 0 = `python -m pytest -q`
#                            NU (interrupteur de retour) ; auto vaut 1 sous Git Bash (NON mesure).
#   CADRE_GATE_BASE          defaut HEAD~1 : les fichiers changes BASE..HEAD sont joues D'ABORD.
#   CADRE_GATE_FAIL_FAST     prio (defaut) : un rouge de la phase prioritaire arrete de LANCER ;
#                            all : tout rouge arrete de lancer ; 0 : tout est joue.
#   CADRE_GATE_FILE_TIMEOUT  defaut 1800 (s) par unite (chien de garde ; `timeout` absent => annonce).
#   CADRE_GATE_CHUNK         taille de tranche (defaut max(100, total/(4*jobs))) ; 0 = jamais couper.
#   CADRE_GATE_REPLAY        defaut 3 : jusqu'a N unites rouges de VERDICT sous le pool sont REJOUEES
#                            SEULES avant le verdict (plafond sur tout le run) ; 0 = jamais. Un TIMEOUT
#                            n'est JAMAIS rejoue (un test pendu rejoue couterait un second budget
#                            entier, et un pendu n'est presque jamais un accident de charge). Un rouge
#                            rattrape par son rejeu ne coupe pas la file (FAIL_FAST=all) : elle reprend.
#   CADRE_GATE_TIMEOUT_BIN   (couture du coureur appele SEUL, ses bancs) defaut `timeout` ; verify.sh la PURGE a
#                            son entree (un faux qui imprime un resume creditait un PASS sans jouer, mesure).
#   CADRE_GATE_DURATIONS_DIR defaut $ROOT/.agents/state/local/porte-durees : table `pytest.tsv`
#                            (`# v1`, puis `fichier<TAB>tests<TAB>secondes`), lue pour l'ORDRE (poids =
#                            duree estimee) et la COUPE d'un fichier qui bornerait seul la jambe, JAMAIS
#                            pour le verdict ; ecrite apres le run (fichiers joues ET verts en passe 1,
#                            fusion, rien n'est efface). Lue puis RETIREE de l'environnement avant tout fils.
#   CADRE_GATE_ROUGES_OUT    (canal de SORTIE vers verify.sh, T-01M5QBFKM444FB53RM2J1NBB4X) : fichier ou ecrire,
#                            un chemin par ligne, les fichiers des unites JOUEES restees rouges (une NON JOUEE n'y
#                            est jamais) ; rien sur un vert ; tmp + mv ; un echec d'ecriture ne change jamais le rc.
#                            Lue puis RETIREE de l'environnement avant tout fils (patron de DUR_DIR).
# Argument (optionnel, repetable) : `--only <fichier.py>` — la collecte est RESTREINTE a ces fichiers (chemin
# relatif `[A-Za-z0-9_./-]`, ni `-` ni `/` en tete, ni `..`, fini par `.py` ; sinon rc 2), chaque fichier liste
# doit etre collecte (sinon rc 2), et le pool juge toujours : JOBS <= 1 y vaut un pool d'UN job, jamais l'exec nu.
# Tout autre argument : rc 2.
# Un VERT avec rejeu n'est PAS un vert simple : la ligne finale le dit (REJOUEES SEULES) — rouge
# sous le pool, vert seul : contention OU defaut intermittent, NON etabli.
set -u
only_ok() {  # only_ok <chemin> : 0 si c'est un chemin de test .py admis par --only
  case "$1" in
    -*|/*|*..*) return 1 ;;
  esac
  case "$1" in
    *[!A-Za-z0-9_./-]*) return 1 ;;
  esac
  case "$1" in
    *.py) return 0 ;;
  esac
  return 1
}
ONLY_PY=()
NONLY=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --only)
      if [ "$#" -lt 2 ] || ! only_ok "$2"; then
        echo "run-pytest-shards: --only « ${2:-} » n'est pas un chemin de test .py admis — refusé" >&2
        exit 2
      fi
      ONLY_PY+=("${2#./}")
      NONLY=$((NONLY + 1))
      shift 2 ;;
    *)
      echo "run-pytest-shards: argument inconnu « $1 » — attendu : aucun, ou --only <fichier.py> (répétable)" >&2
      exit 2 ;;
  esac
done
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 2
# Canal de sortie vers verify.sh : lu ici, RETIRE de l'environnement avant tout fils (aucune unite ne l'herite).
ROUGES_OUT="${CADRE_GATE_ROUGES_OUT:-}"
unset CADRE_GATE_ROUGES_OUT
# Table de durees (T-01M4WTYT8M) : lue ici dans une variable NON exportee, puis RETIREE de l'environnement
# AVANT tout fils (sonde python, `exec pytest` du chemin nu, unites) : aucun banc imbrique n'ecrit la table vivante.
DUR_DIR="${CADRE_GATE_DURATIONS_DIR:-$ROOT/.agents/state/local/porte-durees}"
unset CADRE_GATE_DURATIONS_DIR
DUR_TSV="$DUR_DIR/pytest.tsv"
# lue seulement si c'est un fichier ordinaire LISIBLE (sinon /dev/null : un chemin bizarre ne fait jamais tomber awk,
# donc jamais la couverture (V2)) ; une table presente mais illisible n'est jamais ecrasee (rien n'est efface)
DUR_RD="$DUR_TSV"
if [ ! -f "$DUR_TSV" ] || [ ! -r "$DUR_TSV" ]; then DUR_RD=/dev/null; fi

PY=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "run-pytest-shards: no python interpreter on PATH" >&2; exit 2; fi

is_uint() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
  esac
  return 0
}

IS_WIN=0
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) IS_WIN=1 ;;
esac

ncpu_online() {
  local n=""
  if command -v getconf >/dev/null 2>&1; then n="$(getconf _NPROCESSORS_ONLN 2>/dev/null)"; fi
  if ! is_uint "$n" && command -v nproc >/dev/null 2>&1; then n="$(nproc 2>/dev/null)"; fi
  if ! is_uint "$n" && command -v sysctl >/dev/null 2>&1; then n="$(sysctl -n hw.ncpu 2>/dev/null)"; fi
  if ! is_uint "$n"; then n=1; fi
  if [ "$n" -lt 1 ]; then n=1; fi
  printf '%s' "$n"
}

JOBS="${CADRE_GATE_JOBS:-auto}"
if [ "$JOBS" = "auto" ]; then
  if [ "$IS_WIN" -eq 1 ]; then
    JOBS=1
  else
    _n="$(ncpu_online)"
    JOBS=$(( _n / 2 ))
    if [ "$JOBS" -gt 12 ]; then JOBS=12; fi
    if [ "$JOBS" -lt 1 ]; then JOBS=1; fi
  fi
fi
FF="${CADRE_GATE_FAIL_FAST:-prio}"
FILE_TIMEOUT="${CADRE_GATE_FILE_TIMEOUT:-1800}"
REPLAY="${CADRE_GATE_REPLAY:-3}"
CHUNK="${CADRE_GATE_CHUNK:-}"
for _v in "JOBS=$JOBS" "FILE_TIMEOUT=$FILE_TIMEOUT" "REPLAY=$REPLAY"; do
  if ! is_uint "${_v#*=}"; then
    echo "run-pytest-shards: CADRE_GATE_${_v%%=*}=« ${_v#*=} » n'est pas un entier (ou auto pour JOBS)" >&2
    exit 2
  fi
done
# borne haute : 20 chiffres passaient is_uint puis faisaient echouer `[ -lt ]` (file en attente SANS FIN)
if [ "${#JOBS}" -gt 2 ] || [ "$JOBS" -gt 64 ]; then
  echo "run-pytest-shards: CADRE_GATE_JOBS=« $JOBS » hors borne (au plus 64)" >&2
  exit 2
fi
if [ -n "$CHUNK" ] && ! is_uint "$CHUNK"; then
  echo "run-pytest-shards: CADRE_GATE_CHUNK=« $CHUNK » n'est pas un entier" >&2
  exit 2
fi
case "$FF" in
  prio|all|0) : ;;
  *)
    echo "run-pytest-shards: CADRE_GATE_FAIL_FAST=« $FF » attendu prio|all|0" >&2
    exit 2 ;;
esac
if [ "$JOBS" -le 1 ] && [ "$NONLY" -gt 0 ]; then
  # --only : le pool juge toujours (attribution `--- [i/N]`, resume rapproche) — jamais l'exec nu
  JOBS=1
elif [ "$JOBS" -le 1 ]; then
  echo "pytest: 1 job — commande nue d'origine (python -m pytest -q), aucun decoupage" >&2
  exec "$PY" -m pytest -q
fi

TIMEOUT_BIN="${CADRE_GATE_TIMEOUT_BIN:-timeout}"
if command -v "$TIMEOUT_BIN" >/dev/null 2>&1; then
  WATCHDOG=1
else
  WATCHDOG=0
  echo "COVERAGE DEGRADED: '$TIMEOUT_BIN' absent — unites de test SANS chien de garde (un test pendu pend la porte)" >&2
fi

WORK="$(mktemp -d)" || exit 2
cleanup() {
  local pf
  for pf in "$WORK"/r.*.pid; do
    [ -f "$pf" ] || continue
    kill "$(cat "$pf")" 2>/dev/null
  done
  # les sous-dossiers par unite (launch) poses sous l'etat d'un APPELANT ne survivent pas au run (binome 7+8, T7) ;
  # seuls ceux-la : le reste de son etat n'est jamais touche
  if [ -n "${CADRE_STATE_DIR:-}" ] && [ -f "$WORK/units.txt" ]; then
    awk '{print $3}' "$WORK/units.txt" | while IFS= read -r _u; do
      rm -rf "$CADRE_STATE_DIR/pytest-shard-$_u-1" "$CADRE_STATE_DIR/pytest-shard-$_u-2"
    done
  fi
  rm -rf "$WORK"
}
on_signal() {
  echo "run-pytest-shards: INTERROMPU — aucun verdict vert possible" >&2
  cleanup
  trap - EXIT
  exit "$1"
}
trap 'on_signal 130' INT
trap 'on_signal 143' TERM
trap cleanup EXIT

T0="$(date +%s)"
# --- (V1) collecte nue : stdout (les ids) et stderr (le bruit) SEPARES
"$PY" -m pytest --collect-only -q -p no:cacheprovider ${ONLY_PY[@]+"${ONLY_PY[@]}"} > "$WORK/collect.out" 2> "$WORK/collect.err"
rc0=$?
if [ "$NONLY" -gt 0 ] && { [ "$rc0" -eq 4 ] || [ "$rc0" -eq 5 ]; }; then
  cat "$WORK/collect.out" "$WORK/collect.err"
  echo "run-pytest-shards: --only « ${ONLY_PY[*]} » ne collecte aucun test — refusé" >&2
  exit 2
fi
if [ "$rc0" -ne 0 ]; then
  cat "$WORK/collect.out" "$WORK/collect.err"
  echo "run-pytest-shards: la collecte nue rend rc=$rc0 — rien n'est lance"
  exit "$rc0"
fi
# --- (V1b) le total des ids `fichier.py::id` lus est celui que pytest ANNONCE (`N tests collected`)
sed -n '/^[^[:space:]:][^:]*\.py::/p' "$WORK/collect.out" > "$WORK/nodeids.txt"
TOTAL="$(awk 'END {print NR}' "$WORK/nodeids.txt")"
SUMN="$(awk '/^[0-9]+(\/[0-9]+)? tests? collected/ {split($1, a, "/"); n = a[1]} END {print n + 0}' "$WORK/collect.out")"
if [ "$TOTAL" -eq 0 ] || [ "$SUMN" -ne "$TOTAL" ]; then
  cat "$WORK/collect.out" "$WORK/collect.err"
  echo "run-pytest-shards: la collecte ne se laisse pas lire comme des ids fichier.py::id — $TOTAL id(s) lus, bilan de pytest $SUMN : ROUGE, rien n'est lance (un item hors fichier.py:: — doctest-glob, collecteur de plugin — ou un addopts -q/-v de pytest.ini qui change le format ne serait jamais joue ; CADRE_GATE_JOBS=1 rend la commande nue)"
  exit 1
fi
sed -n 's/^\([^:]*\.py\)::.*$/\1/p' "$WORK/nodeids.txt" | LC_ALL=C sort | uniq -c \
  | awk '{print $2, $1}' > "$WORK/expected.txt"
NFILES="$(awk 'END {print NR}' "$WORK/expected.txt")"
# --only : CHAQUE fichier liste doit etre collecte (un chemin qui ne rend aucun id n'est jamais compte joue)
for _o in ${ONLY_PY[@]+"${ONLY_PY[@]}"}; do
  if ! awk -v f="$_o" '$1 == f {h = 1} END {exit !h}' "$WORK/expected.txt"; then
    echo "run-pytest-shards: --only « $_o » ne collecte aucun test — refusé" >&2
    exit 2
  fi
done
echo "pytest: $TOTAL tests collectes dans $NFILES fichiers (= bilan de pytest, collecte nue, pytest.ini) — $JOBS jobs, echec rapide=$FF, rejeu seul<=$REPLAY, chien de garde=${FILE_TIMEOUT}s/unite"

# --- phase prioritaire : fichiers changes BASE..HEAD
BASE="${CADRE_GATE_BASE:-HEAD~1}"
: > "$WORK/changed.txt"
if git rev-parse -q --verify "$BASE^{commit}" >/dev/null 2>&1; then
  git diff --name-only "$BASE" HEAD > "$WORK/changed.txt" 2>/dev/null || : > "$WORK/changed.txt"
  echo "pytest: base de priorite $BASE ($(awk 'END {print NR}' "$WORK/changed.txt") fichier(s) change(s))"
else
  echo "pytest: base de priorite « $BASE » introuvable — pas de phase prioritaire (tout est joue quand meme)"
fi
# prioritaire : le fichier de test a change, ou il s'appelle test_<stem>.py pour un <stem>.py|.sh change
awk 'FILENAME == ARGV[1] {
       n = split($0, seg, "/"); b = seg[n]
       ch[$0] = 1
       if (b ~ /\.(py|sh)$/) { sub(/\.(py|sh)$/, "", b); st["test_" b ".py"] = 1 }
       next
     }
     {
       n = split($1, seg, "/"); b = seg[n]
       if (($1 in ch) || (b in st)) print $1
     }' "$WORK/changed.txt" "$WORK/expected.txt" > "$WORK/prio.txt"

# --- tranches : `@fichier` exige pytest >= 8.2 ; Git Bash : jamais (argv natif, NON mesure)
PYV="$("$PY" -m pytest --version 2>&1 | sed -n 's/^pytest \([0-9][0-9]*\)\.\([0-9][0-9]*\).*$/\1 \2/p' | sed -n '1p')"
CAN_CHUNK=0
if [ "$IS_WIN" -eq 0 ] && [ -n "$PYV" ]; then
  set -- $PYV
  if [ "$1" -gt 8 ] || { [ "$1" -eq 8 ] && [ "$2" -ge 2 ]; }; then CAN_CHUNK=1; fi
fi
if [ "$CAN_CHUNK" -eq 0 ]; then
  CHUNK=0
  echo "pytest: tranches DESACTIVEES (pytest « ${PYV:-illisible} » < 8.2, ou Git Bash) — unites = fichiers entiers, le plus gros fichier borne la duree"
elif [ -z "$CHUNK" ]; then
  CHUNK=$(( TOTAL / 4 / JOBS ))
  if [ "$CHUNK" -lt 100 ]; then CHUNK=100; fi
fi
# units.txt : "<prio 0|1> <poids> <id> <attendus> <fichier>" ; u.<id>.ids : ids couverts ; u.<id>.args : arguments
# Poids (T-01M4WTYT8M) : sans table, ou sans aucun fichier connu, le NOMBRE DE TESTS de l'unite (ordre et
# unites identiques a avant la table). Avec : la duree ESTIMEE du fichier, en ms entieres — connu : s x n / n_mesure
# (absorbe les tests ajoutes) ; inconnu : n x moyenne s/test des connus — puis estim x m / n par unite. Une ligne
# de table illisible est ignoree ET comptee. Coupe PAR DUREE (C > 0 : ni pytest < 8.2, ni CADRE_GATE_CHUNK=0) :
# un fichier dont l'estimation depasse somme/JOBS (il bornerait seul la jambe) recoit
# k = max(k_compte, plafond(estim x JOBS / somme)) tranches, k <= n. La table ne touche que l'ORDRE et le NOMBRE
# de tranches : la couverture reste prouvee par (V2). weights.txt : "<mode 0|1> <connus> <estimes> <illisibles> <coupes>".
awk -v C="$CHUNK" -v W="$WORK" -v PRIO="$WORK/prio.txt" -v TBL="$DUR_RD" -v J="$JOBS" '
  BEGIN {
    while ((getline l < PRIO) > 0) pr[l] = 1
    while ((getline l < TBL) > 0) {
      if (l ~ /^#/ || l == "") continue
      nt = split(l, t, "\t")
      if (nt == 3 && t[1] ~ /\.py$/ && t[2] ~ /^[1-9][0-9]*$/ && t[3] ~ /^[0-9]+(\.[0-9]+)?$/) { ts[t[1]] = t[3] + 0; tn[t[1]] = t[2] + 0 }
      else bad++
    }
  }
  { f = $0; sub(/::.*/, "", f); if (!(f in n)) ord[++nf] = f; n[f]++; id[f, n[f]] = $0 }
  END {
    for (x = 1; x <= nf; x++) { f = ord[x]; if (f in ts) { kn++; ss += ts[f]; sn += tn[f] } }
    dur = (kn > 0 && sn > 0)
    if (dur) for (x = 1; x <= nf; x++) {
      f = ord[x]
      if (f in ts) est[f] = ts[f] * 1000 * n[f] / tn[f]
      else { est[f] = n[f] * ss * 1000 / sn; unk++ }
      se += est[f]
    }
    u = 0
    for (x = 1; x <= nf; x++) {
      f = ord[x]; k = 1
      if (C > 0 && n[f] > C) k = int((n[f] + C - 1) / C)
      if (dur && C > 0 && se > 0 && est[f] * J > se) {
        kd = est[f] * J / se
        if (kd > int(kd)) kd = int(kd) + 1; else kd = int(kd)
        if (kd > n[f]) kd = n[f]
        if (kd > k) { k = kd; cut++ }
      }
      for (j = 0; j < k; j++) {
        u++; lo = int(j * n[f] / k) + 1; hi = int((j + 1) * n[f] / k); m = hi - lo + 1
        for (q = lo; q <= hi; q++) print id[f, q] > (W "/u." u ".ids")
        close(W "/u." u ".ids")
        if (k == 1) print f > (W "/u." u ".args"); else for (q = lo; q <= hi; q++) print id[f, q] > (W "/u." u ".args")
        close(W "/u." u ".args")
        w = m
        if (dur) w = int(est[f] * m / n[f])
        print ((f in pr) ? 1 : 0), w, u, m, f
      }
    }
    print dur + 0, kn + 0, unk + 0, bad + 0, cut + 0 > (W "/weights.txt")
  }' "$WORK/nodeids.txt" > "$WORK/units.txt"
NUNITS="$(awk 'END {print NR}' "$WORK/units.txt")"
NCHUNKED="$(awk '{c[$5]++} END {for (f in c) if (c[f] > 1) k++; print k + 0}' "$WORK/units.txt")"
echo "pytest: $NUNITS unites ($NCHUNKED fichier(s) coupe(s) en tranches de <= $CHUNK tests)"
awk '$1 == 1 {print $2, $3}' "$WORK/units.txt" | LC_ALL=C sort -k1,1 -rn | awk '{print $2}' > "$WORK/prio.q"
awk '$1 == 0 {print $2, $3}' "$WORK/units.txt" | LC_ALL=C sort -k1,1 -rn | awk '{print $2}' > "$WORK/rest.q"
# l'ordre rendu OBSERVABLE : le mode de poids, et les 3 premieres unites de la file (phase prioritaire comprise)
read -r W_DUR W_KN W_UNK W_BAD W_CUT < "$WORK/weights.txt"
QHEAD="$(cat "$WORK/prio.q" "$WORK/rest.q" | awk -v U="$WORK/units.txt" '
  BEGIN { while ((getline l < U) > 0) { split(l, a, " "); f[a[3]] = a[5] } }
  NR <= 3 { printf "%s%s", (NR > 1 ? ", " : ""), f[$1] }')"
if [ "$W_DUR" -eq 1 ]; then
  echo "pytest: poids = durees mesurees ($DUR_TSV, $W_KN connus) ; tete de file : $QHEAD"
  if [ "$W_UNK" -gt 0 ]; then echo "pytest: $W_UNK fichier(s) sans duree (estimes : tests x moyenne s/test des fichiers connus)"; fi
  if [ "$W_CUT" -gt 0 ]; then echo "pytest: $W_CUT fichier(s) coupe(s) PAR DUREE (estimation > somme/$JOBS jobs : il bornerait seul la jambe)"; fi
elif [ -f "$DUR_TSV" ]; then
  echo "pytest: poids = nombre de tests (aucun fichier connu dans $DUR_TSV) ; tete de file : $QHEAD"
else
  echo "pytest: poids = nombre de tests (aucune table : $DUR_TSV) ; tete de file : $QHEAD"
fi
if [ "$W_BAD" -gt 0 ]; then echo "pytest: $W_BAD ligne(s) illisible(s) dans $DUR_TSV — ignoree(s), conservee(s) telles quelles"; fi

# --- (V2) les unites couvrent EXACTEMENT les ids collectes, et la file porte TOUTES les unites
cat "$WORK"/u.*.ids | LC_ALL=C sort > "$WORK/cover.sorted"
LC_ALL=C sort "$WORK/nodeids.txt" > "$WORK/nodeids.sorted"
if ! cmp -s "$WORK/cover.sorted" "$WORK/nodeids.sorted" \
   || [ "$(awk 'END {print NR}' "$WORK/nodeids.sorted")" -ne "$TOTAL" ] \
   || [ "$(cat "$WORK/prio.q" "$WORK/rest.q" | awk 'END {print NR}')" -ne "$NUNITS" ]; then
  echo "run-pytest-shards: les unites ne couvrent PAS exactement la collecte — ROUGE (V2)"
  comm -3 "$WORK/cover.sorted" "$WORK/nodeids.sorted" | sed -n '1,20p'
  exit 1
fi

launch() {  # launch <id d'unite> <passe 1|2>
  local u="$1" pass="$2" r a sd
  r="$WORK/r.$u"
  if [ "$pass" -eq 1 ]; then
    awk -v u="$u" '$3 == u {print $5}' "$WORK/units.txt" > "$r.f"
    awk -v u="$u" '$3 == u {print $4}' "$WORK/units.txt" > "$r.n"
    if [ "$(awk 'END {print NR}' "$WORK/u.$u.args")" -ne 1 ] || [ "$(cat "$WORK/u.$u.args")" != "$(cat "$r.f")" ]; then
      echo "tranche $(cat "$r.n") tests" > "$r.tr"
    fi
  fi
  if [ -f "$r.tr" ]; then a="@$WORK/u.$u.args"; else a="$(cat "$r.f")"; fi
  echo "$pass" > "$r.pass"
  date +%s > "$r.t0"
  set -- "$PY" -m pytest -q -p no:cacheprovider "$a"
  if [ "$WATCHDOG" -eq 1 ]; then set -- "$TIMEOUT_BIN" --kill-after=15 "$FILE_TIMEOUT" "$@"; fi
  # Etat machine : une valeur posee par l'appelant est RESPECTEE, chaque unite y recoit son
  # sous-dossier (aucun partage entre processus concurrents) ; absente, conftest.py isole
  # deja chaque session. Jamais une valeur VIDE exportee. `< /dev/null` : un fils lance depuis
  # la boucle `while read` HERITE de son stdin et MANGE la file (mesure bash 3.2 et 5.3).
  sd="${CADRE_STATE_DIR:-}"
  if [ -n "$sd" ]; then
    mkdir -p "$sd/pytest-shard-$u-$pass"
    CADRE_STATE_DIR="$sd/pytest-shard-$u-$pass" "$@" < /dev/null > "$r.o" 2>&1 &
  else
    "$@" < /dev/null > "$r.o" 2>&1 &
  fi
  echo "$!" > "$r.pid"
}
DONE=0
judge() {  # judge <r.u> : ecrit .v (PASS ou le motif), imprime la ligne
  local r="$1" f rc exp obs line dt verdict pass tag
  f="$(cat "$r.f")"
  rc="$(cat "$r.rc")"
  pass="$(cat "$r.pass")"
  dt=$(( $(cat "$r.t1") - $(cat "$r.t0") ))
  exp="$(cat "$r.n")"
  if [ -f "$r.tr" ]; then f="$f [$(cat "$r.tr")]"; fi
  line="$(awk '/ in [0-9.]+s/ {l = $0} END {print l}' "$r.o")"
  obs="$(printf '%s\n' "$line" | awk '{
      s = 0
      for (k = 2; k <= NF; k++) {
        w = $k; gsub(/,/, "", w)
        if ((w == "passed" || w == "failed" || w == "skipped" || w == "xfailed" || w == "xpassed" || w == "error" || w == "errors") && $(k-1) ~ /^[0-9]+$/) s += $(k-1)
      }
      print s }')"
  verdict="PASS"
  if [ "$rc" -ne 0 ]; then verdict="FAIL(rc=$rc)"; fi
  if [ "$WATCHDOG" -eq 1 ] && { [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; } && [ "$dt" -ge "$FILE_TIMEOUT" ]; then
    verdict="TIMEOUT(tue apres ${dt}s, limite ${FILE_TIMEOUT}s)"
  fi
  if [ "$verdict" = "PASS" ] && [ -z "$line" ]; then verdict="FAIL(rc 0 sans resume pytest)"; fi
  if [ "$verdict" = "PASS" ] && [ "${obs:-0}" -lt "$exp" ]; then verdict="FAIL(observes ${obs:-0} < collectes $exp)"; fi
  echo "$verdict" > "$r.v"
  if [ "$pass" -eq 1 ]; then
    DONE=$((DONE + 1))
    tag="[$DONE/$NUNITS]"
    echo "$dt $f" >> "$WORK/durations.txt"
    cp "$r.v" "$r.v1"
    echo "$dt" > "$r.dt1"   # duree de PASSE 1 (un rejeu reecrit .t0/.t1, jamais .dt1) : seule source de la table
  else
    tag="[rejeu seul]"
  fi
  echo "--- $tag $verdict $f ($exp tests, obs ${obs:-0}, ${dt}s)"
  # une unite VERTE n'a jamais sa sortie imprimee : son bloc d'avertissements l'est (rampe CroissanceToleree,
  # binome 7+8 F7) ; une rouge est imprimee EN ENTIER plus bas
  if [ "$verdict" = "PASS" ]; then sed -n '/^=* warnings summary =*$/,/^-- Docs:/p' "$r.o"; fi
}
RUNNING=0
reap() {  # juge chaque processus termine ; RUNNING = nombre encore vivant
  local pf r p
  RUNNING=0
  for pf in "$WORK"/r.*.pid; do
    [ -f "$pf" ] || continue
    r="${pf%.pid}"
    p="$(cat "$pf")"
    if kill -0 "$p" 2>/dev/null; then
      RUNNING=$((RUNNING + 1))
    else
      wait "$p" 2>/dev/null
      echo "$?" > "$r.rc"
      date +%s > "$r.t1"
      rm -f "$pf"
      judge "$r"
    fi
  done
}
count_red() {
  local f n=0
  for f in "$WORK"/r.*.v; do
    [ -f "$f" ] || continue
    if [ "$(cat "$f")" != "PASS" ]; then n=$((n + 1)); fi
  done
  echo "$n"
}
STOP=0
run_queue() {  # run_queue <liste> <stop_si_rouge 0|1> ; une unite deja lancee n'est jamais relancee
  local u
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    if [ -f "$WORK/r.$u.pass" ]; then continue; fi
    while :; do
      reap
      # le rouge se relit APRES l'attente d'un creneau : un rouge juge pendant l'attente doit couper
      if [ "$2" -eq 1 ] && [ "$(count_red)" -ne 0 ]; then STOP=1; break 2; fi
      if [ "$RUNNING" -lt "$JOBS" ]; then break; fi
      sleep 0.2
    done
    launch "$u" 1
  done < "$1"
  while :; do
    reap
    if [ "$RUNNING" -eq 0 ]; then break; fi
    sleep 0.2
  done
}
NREPLAYED=0
settle() {  # rejoue SEULES les unites rouges de VERDICT (L-00000234) : jamais un TIMEOUT, jamais deux fois
  local f u n=0 list="" left
  if [ "$REPLAY" -le 0 ]; then return 0; fi
  for f in "$WORK"/r.*.v; do
    [ -f "$f" ] || continue
    u="${f%.v}"; u="${u##*/r.}"
    if [ -f "$WORK/r.$u.o1" ]; then continue; fi
    case "$(cat "$f")" in
      PASS|TIMEOUT*) : ;;
      *) list="$list $u"; n=$((n + 1)) ;;
    esac
  done
  if [ "$n" -eq 0 ]; then return 0; fi
  left=$(( REPLAY - NREPLAYED ))
  if [ "$n" -gt "$left" ]; then
    echo "pytest: $n unite(s) rouge(s) > $left rejeu(x) restant(s) sur CADRE_GATE_REPLAY=$REPLAY — aucun rejeu (un rouge de cette ampleur n'est pas un accident de contention)"
    return 0
  fi
  for u in $list; do
    echo "pytest: rejeu SEUL de l'unite $u (rouge sous le pool, $JOBS jobs) — jobs=1, meme commande"
    mv "$WORK/r.$u.o" "$WORK/r.$u.o1"
    NREPLAYED=$((NREPLAYED + 1))
    launch "$u" 2
    while :; do
      reap
      if [ "$RUNNING" -eq 0 ]; then break; fi
      sleep 0.2
    done
  done
}
run_phase() {  # run_phase <liste> : un rouge RATTRAPE par son rejeu seul ne laisse pas la file coupee
  while :; do
    STOP=0
    run_queue "$1" "$STOP_ON_RED"
    settle
    if [ "$STOP" -eq 0 ] || [ "$(count_red)" -ne 0 ]; then return 0; fi
  done
}

NPRIO="$(awk 'END {print NR}' "$WORK/prio.q")"
STOP_ON_RED=0
if [ "$FF" = "all" ]; then STOP_ON_RED=1; fi
if [ "$NPRIO" -gt 0 ]; then
  echo "pytest: phase prioritaire — $NPRIO unite(s) liee(s) aux changements"
  run_phase "$WORK/prio.q"
  echo "pytest: phase prioritaire terminee en $(( $(date +%s) - T0 ))s ($([ "$(count_red)" -eq 0 ] && echo verte || echo ROUGE))"
  if [ "$(count_red)" -ne 0 ] && [ "$FF" != "0" ]; then STOP=1; fi
fi
if [ "$STOP" -eq 0 ]; then
  run_phase "$WORK/rest.q"
fi

# rouges_ecrire — le canal vers verify.sh (CADRE_GATE_ROUGES_OUT, lu en tete) : les fichiers des unites JOUEES
# dont le verdict FINAL est rouge (un rouge rattrape par son rejeu seul n'y est pas ; deux tranches d'un fichier
# = une ligne) ; tmp + mv dans le meme dossier ; rien si la liste est vide ; un echec n'est JAMAIS un rc.
rouges_ecrire() {
  local _f _tmp
  [ -n "$ROUGES_OUT" ] || return 0
  for _f in "$WORK"/r.*.v; do
    [ -f "$_f" ] || continue
    if [ "$(cat "$_f")" != "PASS" ]; then cat "${_f%.v}.f"; fi
  done | LC_ALL=C sort -u > "$WORK/rouges.lst" 2>/dev/null || return 0
  [ -s "$WORK/rouges.lst" ] || return 0
  _tmp="$ROUGES_OUT.tmp.$$"
  if cp "$WORK/rouges.lst" "$_tmp" 2>/dev/null && mv -f "$_tmp" "$ROUGES_OUT" 2>/dev/null; then
    return 0
  fi
  rm -f "$_tmp" 2>/dev/null
  return 0
}
T1="$(date +%s)"
JOUES="$DONE"
NRED="$(count_red)"
# --- les unites rouges qui le sont RESTEES : sortie COMPLETE ; les rouges rattrapes : la 1re sortie, GARDEE
REPLAYED=""
for _f in "$WORK"/r.*.v1; do
  [ -f "$_f" ] || continue
  _r="${_f%.v1}"
  if [ "$(cat "$_f")" != "PASS" ] && [ "$(cat "$_r.v")" = "PASS" ]; then REPLAYED="$REPLAYED $_r"; fi
done
if [ "$NRED" -ne 0 ]; then
  echo
  echo "================ sorties des unites ROUGES ================"
  for _f in "$WORK"/r.*.v; do
    [ -f "$_f" ] || continue
    _r="${_f%.v}"
    if [ "$(cat "$_f")" != "PASS" ]; then
      echo "=== $(cat "$_r.f") (rc=$(cat "$_r.rc"), $(cat "$_r.v"))"
      cat "$_r.o"
    fi
  done
fi
if [ -n "$REPLAYED" ]; then
  echo
  echo "================ ROUGE SOUS LE POOL, VERT REJOUE SEUL — contention OU defaut intermittent, NON etabli : a NOMMER, suivi a ouvrir (L-00000234) ================"
  for _r in $REPLAYED; do
    echo "=== $(cat "$_r.f") : 1er passage $(cat "$_r.v1"), rejeu seul PASS ; sortie du 1er passage :"
    cat "$_r.o1"
  done
fi
echo
echo "pytest: les 5 unites les plus lentes (s, sous $JOBS jobs) :"
LC_ALL=C sort -rn "$WORK/durations.txt" | awk 'NR <= 5 {print "  " $1 "s " $2}'
# --- table de durees (T-01M4WTYT8M) : seuls les fichiers dont TOUTES les unites ont ete jouees ET vertes en
# passe 1 (jamais un rejeu) ; somme de leurs durees ; FUSION avec la table existante (rien n'est efface ni
# elague, une ligne illisible est gardee telle quelle) ; tmp + mv dans le meme dossier. Un echec d'ecriture est
# annonce, le rc ne change pas. Hors interruption : on_signal sort avant d'arriver ici.
: > "$WORK/dur.new"
: > "$WORK/dur.bad"
awk -v W="$WORK" '
  { u = $3; f = $5; nu[f]++; nt[f] += $4; v = ""; d = ""
    if ((getline v < (W "/r." u ".v1")) > 0 && v == "PASS" && (getline d < (W "/r." u ".dt1")) > 0) { ok[f]++; s[f] += d }
    close(W "/r." u ".v1"); close(W "/r." u ".dt1") }
  END { for (f in nu) if (ok[f] == nu[f]) printf "%s\t%d\t%d\n", f, nt[f], s[f] }' "$WORK/units.txt" > "$WORK/dur.new"
DUR_TMP="$DUR_DIR/.pytest.tsv.$$"
_dok=1
if [ -e "$DUR_TSV" ] && [ "$DUR_RD" = /dev/null ]; then _dok=0; fi
if [ "$_dok" -eq 1 ]; then mkdir -p "$DUR_DIR" 2>/dev/null || _dok=0; fi
if [ "$_dok" -eq 1 ]; then
  # sous-shell a pipefail : un awk en echec n'est jamais masque par le rc de sort (table tronquee = NON ecrite)
  ( set -o pipefail
    echo "# v1" \
    && awk -v NEW="$WORK/dur.new" -v TBL="$DUR_RD" -v BAD="$WORK/dur.bad" '
         BEGIN {
           while ((getline l < NEW) > 0) { split(l, t, "\t"); nw[t[1]] = l }
           while ((getline l < TBL) > 0) {
             if (l ~ /^#/ || l == "") continue
             nt = split(l, t, "\t")
             if (nt == 3 && t[1] ~ /\.py$/ && t[2] ~ /^[1-9][0-9]*$/ && t[3] ~ /^[0-9]+(\.[0-9]+)?$/) { if (!(t[1] in nw)) old[t[1]] = l }
             else print l > BAD
           }
           for (k in old) print old[k]
           for (k in nw) print nw[k]
         }' | LC_ALL=C sort \
    && cat "$WORK/dur.bad" ) > "$DUR_TMP" 2>/dev/null || _dok=0
fi
if [ "$_dok" -eq 1 ]; then mv -f "$DUR_TMP" "$DUR_TSV" 2>/dev/null || _dok=0; fi
if [ "$_dok" -eq 1 ]; then
  echo "pytest: table de durees $DUR_TSV mise a jour ($(awk 'END {print NR}' "$WORK/dur.new") fichier(s) joue(s) et vert(s) en passe 1 ; l'ordre et la coupe seulement, jamais le verdict)"
else
  rm -f "$DUR_TMP" 2>/dev/null
  echo "pytest: table de durees NON ecrite ($DUR_TSV) — l'ordre de la prochaine porte en patit, le verdict de celle-ci est inchange"
fi
if [ "$JOUES" -ne "$NUNITS" ]; then
  echo "pytest: $JOUES/$NUNITS unites jouees — $(( NUNITS - JOUES )) NON JOUEE(S) (echec rapide, CADRE_GATE_FAIL_FAST=0 pour tout jouer) : la liste des echecs n'est PAS complete"
  NRED=$((NRED + 1))
fi
if [ "$WATCHDOG" -eq 0 ]; then
  echo "COVERAGE DEGRADED: aucun chien de garde par unite sur ce run ('$TIMEOUT_BIN' absent)" >&2
fi
# --- ligne AGREGEE au format de pytest, sommee CLE PAR CLE sur les resumes finaux des unites
AGG="$(for _f in "$WORK"/r.*.o; do [ -f "$_f" ] && awk '/ in [0-9.]+s/ {l = $0} END {print l}' "$_f"; done | awk '
  { for (k = 1; k <= NF; k++) {
      w = $k; gsub(/,/, "", w)
      if (w ~ /^[0-9]+$/) {
        nx = $(k + 1); gsub(/,/, "", nx)
        if (nx == "subtests") { key = "subtests " $(k + 2); gsub(/,/, "", key); s[key] += w }
        else if (nx ~ /^(passed|failed|skipped|deselected|xfailed|xpassed|warnings?|errors?)$/) s[nx] += w
      } } }
  END { n = split("failed passed skipped deselected xfailed xpassed warnings warning errors error", o, " ")
        for (q = 1; q <= n; q++) if (o[q] in s) printf "%s%d %s", (c++ ? ", " : ""), s[o[q]], o[q]
        if ("subtests passed" in s) printf "%s%d subtests passed", (c++ ? ", " : ""), s["subtests passed"]
        if ("subtests failed" in s) printf "%s%d subtests failed", (c++ ? ", " : ""), s["subtests failed"]
        if ("subtests skipped" in s) printf "%s%d subtests skipped", (c++ ? ", " : ""), s["subtests skipped"]
        printf "\n" }')"
echo "pytest: ${AGG:-aucun resume} in $(( T1 - T0 ))s (somme des resumes d'unites, format de pytest)"
if [ "$NRED" -ne 0 ]; then
  rouges_ecrire
  echo "pytest shards: ROUGE — $JOUES/$NUNITS unites jouees, $TOTAL tests collectes, $(( T1 - T0 ))s ($JOBS jobs)"
  exit 1
fi
if [ -n "$REPLAYED" ]; then
  echo "pytest shards: VERT — $JOUES/$NUNITS unites ($NFILES fichiers), $TOTAL tests collectes, $(( T1 - T0 ))s ($JOBS jobs), DONT $(echo $REPLAYED | awk '{print NF}') unite(s) rouge(s) sous le pool et vertes REJOUEES SEULES (voir plus haut)"
else
  echo "pytest shards: VERT — $JOUES/$NUNITS unites ($NFILES fichiers), $TOTAL tests collectes, $(( T1 - T0 ))s ($JOBS jobs)"
fi
exit 0
