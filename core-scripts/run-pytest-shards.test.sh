#!/usr/bin/env bash
# requires: git
# Banc de core-scripts/run-pytest-shards.sh (T-00001122).
#
# Chaque cas construit un DEPOT JOUET sous $TMP qui porte une COPIE du runner a
# `<jouet>/core-scripts/run-pytest-shards.sh` (le runner resout sa racine depuis son propre
# dossier : une copie EST une fixture complete, aucun chemin du depot hote). Ce que l'on mesure,
# SUR DES JOUETS : que la porte ne peut PAS rendre vert ce que `python -m pytest` nu rendrait
# rouge — et que chaque garde NOMMEE dans les tables de mutants de T-00001122, DEFAUTS de
# production compris (jobs derives des coeurs, tranches par defaut : S24d-g, S27, joues SANS
# aucun CADRE_GATE_*), a un temoin capable de rougir. Hors de ce banc : Git Bash (auto = 1,
# NON mesure), le conteneur, un runner CI, et l'arbre reel (la porte locale le joue).
#
# NON-VACUITE : une fixture qui ne s'est pas mise en place (deux unites vivantes, pgrep) est un
# KO nomme, jamais un ok silencieux (L-00000161, L-00000186).
set -uo pipefail
# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RUNNER="$ROOT/core-scripts/run-pytest-shards.sh"
[ -f "$ROOT/.agents/bin/kit-portable.sh" ] && . "$ROOT/.agents/bin/kit-portable.sh"

PYBIN=""
for c in python3 python py; do
  if "$c" --version >/dev/null 2>&1; then PYBIN="$(command -v "$c")"; break; fi
done
if [ -z "$PYBIN" ] || ! "$PYBIN" -c 'import pytest' >/dev/null 2>&1; then
  echo "SKIP: pytest (ou python) absent — le runner n'a rien a juger ici"
  exit 0
fi
[ -f "$RUNNER" ] || { echo "KO: runner absent ($RUNNER)"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
passed=0
failed=0
ok() { echo "  ok: $1"; passed=$((passed + 1)); }
ko() { echo "  KO: $1"; failed=$((failed + 1)); }

is_win() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
  esac
  return 1
}
mk_toy() {  # mk_toy <nom> -> chemin ; depot git jouet, runner COPIE dedans
  local d="$TMP/$1"
  mkdir -p "$d/core-scripts" "$d/t"
  cp "$RUNNER" "$d/core-scripts/run-pytest-shards.sh"
  printf '[pytest]\ntestpaths = t\n' > "$d/pytest.ini"
  ( cd "$d" && git init -q . )
  printf '%s\n' "$d"
}
commit() {  # commit <jouet> <message>
  ( cd "$1" && git add -A && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
      git -c core.hooksPath=/dev/null commit -q -m "$2" )
}
wtf() { cat > "$1/t/$2"; }   # wtf <jouet> <fichier sous t/> < corps (heredoc a delimiteur quote)
green() {                    # green <jouet> <fichier> : 2 tests verts
  wtf "$1" "$2" <<'PYEOF'
def test_a():
    pass


def test_b():
    pass
PYEOF
}
cores_shim() {  # cores_shim <dossier> <n> : getconf, nproc et sysctl repondent n (aucun CADRE_GATE_* : le DEFAUT decide)
  local c
  mkdir -p "$1"
  for c in getconf nproc sysctl; do printf '#!/bin/sh\necho %s\n' "$2" > "$1/$c"; chmod +x "$1/$c"; done
}
busy_victim() {  # busy_victim <jouet> : la victime ROUGIT si elle voit BUSY ; BUSY tient jusqu'a ce qu'elle l'ait VU
  # Poignee de main bornee plutot qu'une fenetre d'horloge : le rouge sous le pool ne depend pas
  # de l'ecart de demarrage de deux processus (un runner CI lent n'a aucun rejeu sous JOBS=1).
  wtf "$1" test_a_busy.py <<'PYEOF'
import os
import time


def test_hold():
    p = os.environ["BUSY"]
    open(p, "w").close()
    for _ in range(200):
        if os.path.exists(p + ".seen"):
            break
        time.sleep(0.1)
    os.remove(p)
    open(p + ".done", "w").close()


def test_x1():
    pass


def test_x2():
    pass
PYEOF
  wtf "$1" test_b_victim.py <<'PYEOF'
import os
import time


def test_victim():
    p = os.environ["BUSY"]
    for _ in range(100):
        if os.path.exists(p) or os.path.exists(p + ".done"):
            break
        time.sleep(0.1)
    busy = os.path.exists(p)
    if busy:
        open(p + ".seen", "w").close()
    assert not busy


def test_v2():
    pass
PYEOF
}
OUT=""
RC=0
rps() {  # rps <jouet> [VAR=val ...] [-- <arguments du runner>] : joue la COPIE du runner ; sortie fusionnee dans $OUT, rc dans $RC
  local d="$1"; shift
  OUT="$TMP/out.$RANDOM$RANDOM"
  # T-01M4WTYT8M : la table de durees du chemin PAR DEFAUT est effacee avant CHAQUE appel (sinon elle persiste
  # d'un appel a l'autre sur un meme jouet et change l'ordre des cas d'avant) ; un cas qui SEME une table ou la
  # GARDE d'un appel a l'autre passe un CADRE_GATE_DURATIONS_DIR explicite (S30-S33).
  rm -rf "$d/.agents/state/local/porte-durees"
  ( cd "$d" \
    && unset CADRE_GATE_JOBS CADRE_GATE_BASE CADRE_GATE_FAIL_FAST CADRE_GATE_FILE_TIMEOUT CADRE_GATE_CHUNK CADRE_GATE_REPLAY CADRE_GATE_TIMEOUT_BIN PYTEST_ADDOPTS PYTEST_PLUGINS CADRE_STATE_DIR CADRE_GATE_DURATIONS_DIR CADRE_GATE_ROUGES_OUT
    while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do export "${1%%=*}=${1#*=}"; shift; done
    [ "$#" -eq 0 ] || shift
    timeout 90 bash core-scripts/run-pytest-shards.sh "$@" ) > "$OUT" 2>&1
  RC=$?
}
has() { grep -qF -- "$1" "$OUT"; }
cnt() { local n; n="$(grep -cF -- "$1" "$OUT")"; printf '%s' "${n:-0}"; }
tget() { awk -F '\t' -v k="$2" -v c="$3" '$1 == k {v = $c} END {print v}' "$1" 2>/dev/null; }   # tget <table> <fichier> <colonne>
DEF_TB=".agents/state/local/porte-durees/pytest.tsv"   # chemin PAR DEFAUT de la table, relatif au jouet
bare_rc() { ( cd "$1" && "$PYBIN" -m pytest -q -p no:cacheprovider >/dev/null 2>&1; echo $? ); }

SEL="${RPS_SCENARIOS:-}"   # vide = TOUS les cas ; "S14 S22" = ceux-la seulement (ergonomie des mutants — la porte joue tout)
want() {  # want <S..> [<S..>] : vrai si le cas est selectionne
  [ -z "$SEL" ] && return 0
  local w
  for w in "$@"; do
    case " $SEL " in
      *" $w "*) return 0 ;;
    esac
  done
  return 1
}
[ -z "$SEL" ] || echo "SKIP: RPS_SCENARIOS=« $SEL » — sous-ensemble des cas, ce vert n'est PAS la couverture complete"

if want S1; then
echo "=== S1. UN JOUET VERT : verdict VERT, la phase prioritaire joue EN PREMIER"
D="$(mk_toy s1)"
for k in 1 2 3 4; do green "$D" "test_m$k.py"; done
commit "$D" base
wtf "$D" test_m3.py <<'PYEOF'
def test_a():
    pass


def test_b():
    pass


def test_c():
    pass
PYEOF
commit "$D" second
rps "$D" CADRE_GATE_JOBS=3 CADRE_GATE_REPLAY=0
[ "$RC" -eq 0 ] && ok "S1 rc 0" || ko "S1 rc $RC"
has "pytest shards: VERT — 4/4 unites" && ok "S1 verdict VERT 4/4" || ko "S1 pas de ligne VERT 4/4"
has "phase prioritaire — 1 unite" && ok "S1 une unite prioritaire (le fichier change)" || ko "S1 phase prioritaire absente"
[ "$(awk '/^--- \[/ {print $4; exit}' "$OUT")" = "t/test_m3.py" ] \
  && ok "S1 la PREMIERE unite jugee est le fichier change" || ko "S1 la phase prioritaire ne passe pas en premier"
fi

if want S1b; then
echo "=== S1b. UN SOURCE CHANGE (foo.py) rend PRIORITAIRE son test test_foo.py"
D="$(mk_toy s1b)"
printf 'X = 1\n' > "$D/foo.py"
green "$D" test_foo.py
green "$D" test_bar.py
green "$D" test_baz.py
commit "$D" base
printf 'X = 2\n' > "$D/foo.py"
commit "$D" second
rps "$D" CADRE_GATE_JOBS=3 CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "phase prioritaire — 1 unite" && [ "$(awk '/^--- \[/ {print $4; exit}' "$OUT")" = "t/test_foo.py" ]; } && ok "S1b foo.py change -> test_foo.py joue en premier" || ko "S1b la correspondance source -> test_<stem>.py est perdue"
fi

if want S2 S3; then
echo "=== S2/S3. ROUGE en phase prioritaire : l'echec rapide coupe et le DIT ; FAIL_FAST=0 joue tout"
D="$(mk_toy s2)"
wtf "$D" test_m1.py <<'PYEOF'
def test_a():
    pass


def test_b():
    pass


def test_c():
    pass


def test_d():
    pass
PYEOF
cp "$D/t/test_m1.py" "$D/t/test_m2.py"
wtf "$D" test_m3.py <<'PYEOF'
def test_a():
    pass
PYEOF
commit "$D" base
wtf "$D" test_m3.py <<'PYEOF'
def test_a():
    assert 0
PYEOF
commit "$D" red
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0
[ "$RC" -eq 1 ] && ok "S2 rc 1" || ko "S2 rc $RC"
{ has "1/3 unites jouees" && has "NON JOUEE(S)"; } && ok "S2 1/3 jouees, les 2 autres NON JOUEES annoncees" || ko "S2 l'echec rapide n'a pas coupe (ou n'a pas annonce)"
has "pytest shards: ROUGE" && ok "S2 ligne ROUGE" || ko "S2 pas de ligne ROUGE"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0
{ [ "$RC" -eq 1 ] && has "3/3 unites jouees"; } && ok "S3 FAIL_FAST=0 : tout est joue, rc 1" || ko "S3 rc $RC / pas 3/3"
has "=== t/test_m3.py (rc=1" && ok "S3 la sortie COMPLETE de l'unite rouge est rejouee" || ko "S3 sortie de l'unite rouge absente"
fi

if want S4; then
echo "=== S4. UNE UNITE TUEE -9 EN COURS DE ROUTE : ROUGE, jamais vert"
D="$(mk_toy s4)"
green "$D" test_ok.py
wtf "$D" test_die.py <<'PYEOF'
import os


def test_die():
    os.kill(os.getpid(), 9)
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 1 ] && has "FAIL(rc=137) t/test_die.py"; } && ok "S4 FAIL(rc=137) nomme, rc 1" || ko "S4 rc $RC, unite tuee non nommee"
fi

if want S5; then
echo "=== S5. TERM puis INT : rc 143 / 130, AUCUN survivant, scenario non NUL (>= 2 unites vivantes au signal)"
if is_win; then
  echo "SKIP: signaux vers un runner sous Git Bash — NON mesure (le runner y est nu par defaut)"
elif ! command -v pgrep >/dev/null 2>&1; then
  echo "SKIP: pgrep absent — la recherche de survivants est impossible"
else
  cat > "$TMP/drive.py" <<'PYEOF'
import os, signal, subprocess, sys, time
toy, sig, marks, out = sys.argv[1:5]
env = dict(os.environ, CADRE_GATE_JOBS="3", CADRE_GATE_REPLAY="0", CADRE_GATE_BASE="none", MARKS=marks)
with open(out, "w") as fh:
    p = subprocess.Popen(["bash", "core-scripts/run-pytest-shards.sh"], cwd=toy, env=env, stdout=fh,
                         stderr=subprocess.STDOUT, preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    t0 = time.time()
    while time.time() - t0 < 40 and len(os.listdir(marks)) < 2:
        time.sleep(0.1)
    live = len(os.listdir(marks))
    os.kill(p.pid, getattr(signal, sig))
    rc = p.wait(timeout=40)
print(rc, live)
PYEOF
  for SIG in TERM INT; do
    D="$(mk_toy "s5$SIG")"
    mkdir -p "$D/marks"
    for k in 1 2 3 4; do
      wtf "$D" "test_hold_$$_$k.py" <<PYEOF
import os
import time


def test_h():
    open(os.path.join(os.environ["MARKS"], "$k"), "w").close()
    time.sleep(30)
PYEOF
    done
    commit "$D" base
    read -r SRC SLIVE < <("$PYBIN" "$TMP/drive.py" "$D" "SIG$SIG" "$D/marks" "$TMP/s5$SIG.out" 2>/dev/null)
    SURV=1
    for _w in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      SURV="$(pgrep -f "test_hold_$$_" | awk 'END {print NR}')"
      [ "${SURV:-1}" -eq 0 ] && break
      sleep 0.25
    done
    WANT=143; [ "$SIG" = "INT" ] && WANT=130
    [ "${SLIVE:-0}" -ge 2 ] && ok "S5 $SIG : ${SLIVE} unites vivantes au signal (scenario non nul)" || ko "S5 $SIG : scenario NUL (${SLIVE:-0} unite vivante)"
    [ "${SRC:-x}" = "$WANT" ] && ok "S5 $SIG : rc $WANT" || ko "S5 $SIG : rc ${SRC:-?} (attendu $WANT)"
    [ "${SURV:-1}" -eq 0 ] && ok "S5 $SIG : 0 survivant (poll 5 s)" || ko "S5 $SIG : ${SURV} survivant(s) 5 s apres le signal — le nettoyage ne tue plus"
    grep -qF "INTERROMPU" "$TMP/s5$SIG.out" && ok "S5 $SIG : INTERROMPU annonce" || ko "S5 $SIG : pas de ligne INTERROMPU"
  done
fi
fi

if want S6 S7; then
echo "=== S6/S7. COLLECTE CASSEE -> rc 2 sans rien lancer ; COLLECTE VIDE -> rc 5 (semantique nue)"
D="$(mk_toy s6)"
green "$D" test_ok.py
printf 'import nexistepas\n' > "$D/t/test_broken.py"
commit "$D" base
rps "$D" CADRE_GATE_JOBS=3
BARE="$(bare_rc "$D")"
{ [ "$RC" -eq "$BARE" ] && [ "$RC" -eq 2 ]; } && ok "S6 rc 2 = rc de pytest nu" || ko "S6 rc $RC (nu : $BARE)"
{ [ "$(cnt '--- [')" -eq 0 ] && has "rien n'est lance"; } && ok "S6 aucune unite lancee" || ko "S6 des unites ont ete lancees malgre la collecte cassee"
D="$(mk_toy s7)"
mkdir -p "$D/t2"
printf '[pytest]\ntestpaths = t2\n' > "$D/pytest.ini"
commit "$D" base
rps "$D" CADRE_GATE_JOBS=3
BARE="$(bare_rc "$D")"
{ [ "$RC" -eq "$BARE" ] && [ "$RC" -eq 5 ]; } && ok "S7 rc 5 = rc de pytest nu (collecte vide)" || ko "S7 rc $RC (nu : $BARE)"
fi

if want S8; then
echo "=== S8. UN TEST PENDU : TIMEOUT nomme, la porte REND un verdict"
if ! type -P timeout >/dev/null 2>&1; then
  echo "SKIP: timeout GNU absent — le chien de garde du runner serait lui-meme degrade (S21 le couvre)"
else
  D="$(mk_toy s8)"
  green "$D" test_ok.py
  wtf "$D" test_hang.py <<'PYEOF'
import time


def test_hang():
    time.sleep(20)
PYEOF
  commit "$D" base
  rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_FILE_TIMEOUT=3 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
  { [ "$RC" -eq 1 ] && has "TIMEOUT(tue apres"; } && ok "S8 TIMEOUT nomme, rc 1" || ko "S8 rc $RC, pas de TIMEOUT nomme (le timeout 90 du banc a pu tuer le runner)"
fi
fi

if want S9; then
echo "=== S9. UN ITEM ESCAMOTE A L'EXECUTION (observes < collectes) : ROUGE"
D="$(mk_toy s9)"
wtf "$D" test_m1.py <<'PYEOF'
def test_a():
    pass


def test_b():
    pass


def test_c():
    pass
PYEOF
green "$D" test_m2.py
wtf "$D" conftest.py <<'PYEOF'
def pytest_collection_modifyitems(config, items):
    if not config.option.collectonly and items and items[-1].path.name == "test_m1.py":
        del items[-1]
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 1 ] && has "FAIL(observes 2 < collectes 3)"; } && ok "S9 observes 2 < collectes 3 : ROUGE" || ko "S9 rc $RC, l'item escamote est passe"
fi

if want S10; then
echo "=== S10. LA BORNE DU POOL : jamais plus de JOBS unites vivantes (et exactement 2 ici : le pool joue)"
# Fenetre de 4 s par unite : ce banc tourne aussi sur la jambe CI BLOQUANTE (macOS), ou rien n'est
# rejoue (CADRE_GATE_JOBS=1 y est epingle) — un ecart de demarrage de deux pythons ne doit pas rougir.
D="$(mk_toy s10)"
for k in 1 2 3 4 5; do
  wtf "$D" "test_c$k.py" <<'PYEOF'
import os
import time


def test_x():
    p = os.environ["SONDE"]
    open(p, "a").write("+ %f\n" % time.time())
    time.sleep(4)
    open(p, "a").write("- %f\n" % time.time())
PYEOF
done
commit "$D" base
: > "$TMP/sonde.txt"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "SONDE=$TMP/sonde.txt"
MX="$(LC_ALL=C sort -k2,2n "$TMP/sonde.txt" | awk '{if ($1 == "+") c++; else c--; if (c > m) m = c} END {print m + 0}')"
{ [ "$RC" -eq 0 ] && [ "$MX" -eq 2 ]; } && ok "S10 concurrence max observee = $MX (JOBS=2)" || ko "S10 rc $RC, concurrence max $MX (attendu 2)"
fi

if want S11 S12; then
echo "=== S11/S12. TRANCHES : ids exotiques (espaces, crochets, virgule, unicode), couverture EXACTE ; une tranche rouge est NOMMEE"
if is_win; then
  echo "SKIP: S11/S12 — sous Git Bash les tranches sont ETEINTES par conception (S20 couvre ce chemin)"
else
D="$(mk_toy s11)"
wtf "$D" test_par.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", ["a b", " lead", "trail ", "x,y", "[br]", "q'uote", "d\"q", "é", "k"])
def test_p(n):
    assert n
PYEOF
green "$D" test_one.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=3 CADRE_GATE_CHUNK=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "1 fichier(s) coupe(s) en tranches de <= 2 tests" && has "11 passed"; } && ok "S11 tranches C=2, ids exotiques : VERT, 11 passed = TOUT ce qui est collecte" || ko "S11 rc $RC ou pas de tranches ($(grep -F 'unites (' "$OUT"))"
wtf "$D" test_par.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", ["a b", "c d", "e", "f", "", "h i", "j", "k", "l"])
def test_p(n):
    assert n
PYEOF
commit "$D" red
rps "$D" CADRE_GATE_JOBS=3 CADRE_GATE_CHUNK=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0
{ [ "$RC" -eq 1 ] && grep -F 'FAIL(' "$OUT" | grep -qF 'tranche'; } && ok "S12 la tranche rouge est NOMMEE (fichier + tranche)" || ko "S12 rc $RC, tranche rouge non nommee"
fi
fi

if want S13; then
echo "=== S13. UN PROCESSUS QUI SORT rc 0 SANS RESUME PYTEST (os._exit) : ROUGE, avec SON diagnostic"
D="$(mk_toy s13)"
wtf "$D" test_exit.py <<'PYEOF'
import os


def test_a():
    pass


def test_b():
    os._exit(0)


def test_c():
    pass
PYEOF
green "$D" test_ok.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 1 ] && has "FAIL(rc 0 sans resume pytest)"; } && ok "S13 rc 0 sans resume : ROUGE, diagnostic exact" || ko "S13 rc $RC / diagnostic absent ($(grep -F 't/test_exit.py' "$OUT" | sed -n '1p'))"
fi

if want S14; then
echo "=== S14. LA FILE N'EST PAS MANGEE PAR UN FILS QUI LIT LE STDIN (capture coupee : PYTEST_ADDOPTS=-s)"
# pytest capture fd 0 par defaut : le defaut ne se voit QU'AVEC -s. L'unite la plus lourde passe la
# premiere (poids decroissant) et lit stdin jusqu'a EOF : sans `< /dev/null` elle avale le reste de la file.
D="$(mk_toy s14)"
wtf "$D" test_a_cat.py <<'PYEOF'
import sys


def test_cat():
    sys.stdin.read()


def test_b():
    pass


def test_c():
    pass


def test_d():
    pass
PYEOF
for k in 1 2 3; do green "$D" "test_z$k.py"; done
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none PYTEST_ADDOPTS=-s
[ "$RC" -eq 0 ] && ok "S14 rc 0" || ko "S14 rc $RC (la file a ete mangee ?)"
[ "$(grep -cE '^--- \[[0-9]+/4\] PASS' "$OUT")" -eq 4 ] && ok "S14 les 4 unites sont JOUEES et PASS" || ko "S14 $(grep -cE '^--- \[[0-9]+/4\] PASS' "$OUT") unite(s) PASS sur 4"
has "pytest shards: VERT — 4/4 unites" && ok "S14 4/4 unites" || ko "S14 la ligne finale ne dit pas 4/4"
fi

if want S15; then
echo "=== S15. L'ETAT MACHINE : ABSENT chez l'enfant quand l'appelant ne l'a pas pose ; un SOUS-DOSSIER s'il l'a pose ; jamais VIDE"
D="$(mk_toy s15)"
wtf "$D" test_probe.py <<'PYEOF'
import os


def test_probe():
    open(os.environ["PROBE"], "a").write(repr(os.environ.get("CADRE_STATE_DIR")) + "\n")
PYEOF
green "$D" test_ok.py
commit "$D" base
: > "$TMP/probe.txt"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none "PROBE=$TMP/probe.txt"
{ [ "$RC" -eq 0 ] && [ "$(cat "$TMP/probe.txt")" = "None" ]; } && ok "S15 CADRE_STATE_DIR absent chez l'appelant : ABSENT chez l'enfant" || ko "S15 absent -> '$(cat "$TMP/probe.txt")' (attendu None)"
: > "$TMP/probe.txt"; mkdir -p "$TMP/st"; : > "$TMP/st/a-moi.txt"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none "PROBE=$TMP/probe.txt" "CADRE_STATE_DIR=$TMP/st"
case "$(cat "$TMP/probe.txt")" in
  *"$TMP/st/pytest-shard-"*) ok "S15 pose chez l'appelant : un SOUS-DOSSIER par unite" ;;
  *) ko "S15 pose -> '$(cat "$TMP/probe.txt")' (attendu un sous-dossier de $TMP/st)" ;;
esac
# binome 7+8 (T7) : ces sous-dossiers ne SURVIVENT PAS au run (168 par run, mesure, sous la partition reelle
# d'un appelant) ; le contenu PROPRE de l'appelant, lui, reste.
_left="$(find "$TMP/st" -maxdepth 1 -name 'pytest-shard-*' | awk 'END {print NR}')"
{ [ "$_left" -eq 0 ] && [ -f "$TMP/st/a-moi.txt" ]; } && ok "S15 apres le run : 0 pytest-shard-* laisse, le fichier de l'appelant intact" \
  || ko "S15 apres le run : $_left pytest-shard-* laisse(s), a-moi.txt $([ -f "$TMP/st/a-moi.txt" ] && echo present || echo PERDU)"
fi

if want S16; then
echo "=== S16. CADRE_GATE_JOBS=1 = LA COMMANDE NUE : meme stdout (hors duree), meme rc, aucune ligne du runner"
norm() { sed -E 's/ in [0-9]+\.[0-9]+s( \([0-9:]+\))?$//'; }
D="$(mk_toy s16)"
green "$D" test_ok.py
wtf "$D" test_bad.py <<'PYEOF'
def test_bad():
    assert 0
PYEOF
commit "$D" base
( cd "$D" && "$PYBIN" -m pytest -q > "$TMP/s16.bare" 2>/dev/null; echo $? > "$TMP/s16.bare.rc" )
( cd "$D" && CADRE_GATE_JOBS=1 bash core-scripts/run-pytest-shards.sh > "$TMP/s16.run" 2>/dev/null; echo $? > "$TMP/s16.run.rc" )
[ "$(cat "$TMP/s16.bare.rc")" = "$(cat "$TMP/s16.run.rc")" ] && [ "$(cat "$TMP/s16.run.rc")" = "1" ] && ok "S16 rc identique a pytest nu (1)" || ko "S16 rc $(cat "$TMP/s16.run.rc") / nu $(cat "$TMP/s16.bare.rc")"
[ "$(norm < "$TMP/s16.bare")" = "$(norm < "$TMP/s16.run")" ] && ok "S16 stdout identique a pytest nu (hors duree)" || ko "S16 stdout different de pytest nu"
grep -qF "pytest shards:" "$TMP/s16.run" && ko "S16 le chemin nu imprime une ligne du runner" || ok "S16 aucune ligne 'pytest shards:' sur stdout"
fi

if want S17; then
echo "=== S17. UN REGLAGE INVALIDE est REFUSE rc 2 (jamais ignore), rien n'est lance"
D="$(mk_toy s17)"
green "$D" test_ok.py
commit "$D" base
for SET in CADRE_GATE_JOBS=x CADRE_GATE_FAIL_FAST=y CADRE_GATE_CHUNK=z CADRE_GATE_REPLAY=-1 CADRE_GATE_FILE_TIMEOUT=abc \
           CADRE_GATE_JOBS=99999999999999999999 CADRE_GATE_JOBS=99; do
  rps "$D" "$SET"
  { [ "$RC" -eq 2 ] && [ "$(cnt '--- [')" -eq 0 ] && has "${SET%%=*}"; } && ok "S17 $SET : rc 2, nomme" || ko "S17 $SET : rc $RC"
done
# binome 7+8 (F4/T5) : 20 chiffres passaient `is_uint` puis `[ -lt ]` rendait « nombre entier attendu » -> file
# en attente SANS FIN ; 99 lancait 99 pytest. Borne JOBS <= 64 (2 chiffres) ; la borne elle-meme est ACCEPTEE.
rps "$D" CADRE_GATE_JOBS=64 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "— 64 jobs"; } && ok "S17 CADRE_GATE_JOBS=64 (la borne) : accepte, rc 0" || ko "S17 CADRE_GATE_JOBS=64 : rc $RC"
fi

if want S18; then
echo "=== S18. LA LIGNE AGREGEE = celle de pytest nu, CLE PAR CLE (passed, failed, skipped, xfailed, xpassed, subtests)"
keys() {
  awk '{ for (k = 1; k < NF; k++) {
           w = $k; gsub(/,/, "", w); nx = $(k + 1); gsub(/,/, "", nx)
           if (w ~ /^[0-9]+$/) {
             if (nx == "subtests") { s = $(k + 2); gsub(/,/, "", s); print "subtests " s "=" w }
             else if (nx ~ /^(passed|failed|skipped|xfailed|xpassed)$/) print nx "=" w
           } } }' | LC_ALL=C sort | tr '\n' ' '
}
D="$(mk_toy s18)"
wtf "$D" test_mix.py <<'PYEOF'
import pytest


def test_ok1():
    pass


def test_ok2():
    pass


@pytest.mark.skip(reason="x")
def test_skip():
    pass


@pytest.mark.xfail
def test_xf():
    assert 0


@pytest.mark.xfail
def test_xp():
    pass


def test_sub(subtests):
    for i in range(3):
        with subtests.test(i=i):
            assert True


def test_fail():
    assert 0
PYEOF
green "$D" test_ok.py
commit "$D" base
BARE_LINE="$( cd "$D" && "$PYBIN" -m pytest -q -p no:cacheprovider 2>&1 | awk '/ in [0-9.]+s/ {l = $0} END {print l}' )"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_BASE=none CADRE_GATE_CHUNK=0
RUN_LINE="$(grep -F "somme des resumes" "$OUT" | sed -n '1p')"
KB="$(printf '%s\n' "$BARE_LINE" | keys)"; KR="$(printf '%s\n' "$RUN_LINE" | keys)"
case "$KB" in
  *"failed=1"*"subtests passed=3"*) ok "S18 non-vacuite : la ligne nue porte failed=1 et 3 subtests passed ($KB)" ;;
  *) ko "S18 la fixture ne produit pas les cles attendues ($BARE_LINE)" ;;
esac
[ "$KB" = "$KR" ] && ok "S18 cles identiques a pytest nu ($KR)" || ko "S18 cles differentes : nu [$KB] runner [$KR]"
fi

if want S19; then
echo "=== S19. UN ITEM HORS fichier.py:: (doctest-glob) : ROUGE, rien lance ; un addopts -q ou -v (format illisible) : ROUGE nomme"
D="$(mk_toy s19)"
printf '[pytest]\ntestpaths = t\naddopts = --doctest-glob=*.txt\n' > "$D/pytest.ini"
green "$D" test_ok.py
printf '>>> 1 + 1\n3\n' > "$D/t/n.txt"
commit "$D" base
BARE="$(bare_rc "$D")"
rps "$D" CADRE_GATE_JOBS=3
{ [ "$BARE" -eq 1 ] && [ "$RC" -ne 0 ] && has "ne se laisse pas lire" && [ "$(cnt '--- [')" -eq 0 ]; } \
  && ok "S19 doctest faux : pytest nu rc 1, le runner ROUGE rc $RC, rien lance" || ko "S19 nu $BARE, runner rc $RC (un doctest faux est passe VERT ?)"
has "CADRE_GATE_JOBS=1" && ok "S19 le message nomme le remede" || ko "S19 le message ne nomme pas le remede"
printf '[pytest]\ntestpaths = t\naddopts = -q\n' > "$D/pytest.ini"
rm -f "$D/t/n.txt"
rps "$D" CADRE_GATE_JOBS=3
{ [ "$RC" -eq 1 ] && has "ne se laisse pas lire" && has "addopts -q/-v"; } && ok "S19b addopts -q (format -qq illisible) : ROUGE, le message nomme -q/-v, pas un faux vert" || ko "S19b rc $RC"
printf '[pytest]\ntestpaths = t\naddopts = -v\n' > "$D/pytest.ini"
rps "$D" CADRE_GATE_JOBS=3
{ [ "$RC" -eq 1 ] && has "ne se laisse pas lire" && has "addopts -q/-v" && [ "$(cnt '--- [')" -eq 0 ]; } && ok "S19c addopts -v (format arbre) : ROUGE nomme, rien lance" || ko "S19c rc $RC"
fi

if want S20; then
echo "=== S20. pytest < 8.2 (pas de @fichier) : tranches DESACTIVEES et ANNONCEES, unites = fichiers entiers"
mkdir -p "$TMP/shim20"
printf '#!/usr/bin/env bash\nif [ "${1:-}" = "-m" ] && [ "${2:-}" = "pytest" ] && [ "${3:-}" = "--version" ]; then echo "pytest 8.1.1"; exit 0; fi\nexec "%s" "$@"\n' "$PYBIN" > "$TMP/shim20/python3"
chmod +x "$TMP/shim20/python3"
D="$(mk_toy s20)"
wtf "$D" test_par.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", list("abcdefghi"))
def test_p(n):
    assert n
PYEOF
green "$D" test_one.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=3 CADRE_GATE_CHUNK=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "PATH=$TMP/shim20:$PATH"
{ [ "$RC" -eq 0 ] && has "tranches DESACTIVEES" && has "0 fichier(s) coupe(s)"; } && ok "S20 pytest 8.1 : pas de tranche, annonce, VERT" || ko "S20 rc $RC ($(grep -F 'unites (' "$OUT"))"
fi

if want S21; then
echo "=== S21. PAS DE CHIEN DE GARDE (timeout absent) : COVERAGE DEGRADED au DEBUT ET au BILAN, nomme, le run n'est pas bloque"
D="$(mk_toy s21)"
green "$D" test_ok.py
green "$D" test_ok2.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_TIMEOUT_BIN=no-such-timeout-binary
{ [ "$RC" -eq 0 ] && [ "$(cnt 'COVERAGE DEGRADED')" -eq 2 ] && has "no-such-timeout-binary"; } && ok "S21 COVERAGE DEGRADED x2 (debut + bilan), binaire nomme, rc 0" || ko "S21 rc $RC, $(cnt 'COVERAGE DEGRADED') annonce(s)"
fi

if want S22; then
echo "=== S22. FAIL_FAST=all : le 1er rouge n'importe ou arrete de LANCER ; les unites en vol finissent"
D="$(mk_toy s22)"
wtf "$D" test_a_slow.py <<'PYEOF'
import time


def test_a1():
    time.sleep(2)


def test_a2():
    pass


def test_a3():
    pass


def test_a4():
    pass
PYEOF
wtf "$D" test_b_red.py <<'PYEOF'
def test_b1():
    pass


def test_b2():
    pass


def test_b3():
    assert 0
PYEOF
for k in c d e; do wtf "$D" "test_$k.py" <<'PYEOF'
def test_x():
    pass
PYEOF
done
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=all
{ [ "$RC" -eq 1 ] && has "2/5 unites jouees" && has "NON JOUEE(S)"; } && ok "S22 all : 2/5 jouees (a lente + b rouge), 3 NON JOUEES annoncees" || ko "S22 rc $RC ($(grep -F 'unites jouees' "$OUT"))"
fi

if want S22bis; then
echo "=== S22bis. FAIL_FAST=all x REJEU : un rouge RATTRAPE par son rejeu seul ne laisse pas la file coupee"
D="$(mk_toy s22bis)"
busy_victim "$D"
for k in c d e; do wtf "$D" "test_$k.py" <<'PYEOF'
def test_x():
    pass
PYEOF
done
commit "$D" base
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_FAIL_FAST=all "BUSY=$TMP/busy"
{ [ "$RC" -eq 0 ] && has "rejeu SEUL" && has "VERT — 5/5 unites" && has "REJOUEES SEULES" && ! has "NON JOUEE"; } \
  && ok "S22bis all x rejeu : le rouge rattrape, la file REPREND, 5/5 jouees, VERT annonce" || ko "S22bis rc $RC ($(grep -E 'unites jouees|pytest shards:' "$OUT" | tr '\n' '|'))"
fi

if want S23; then
echo "=== S23. REJEU SEUL d'un rouge sous le pool (L-00000234, le reflexe devient mecanique) : borne, annonce, jamais muet"
D="$(mk_toy s23)"
busy_victim "$D"
commit "$D" base
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none "BUSY=$TMP/busy"
{ [ "$RC" -eq 0 ] && has "rejeu SEUL" && has "ROUGE SOUS LE POOL, VERT REJOUE SEUL" && has "REJOUEES SEULES"; } \
  && ok "S23a un rouge sous le pool est REJOUE seul : VERT, ANNONCE (ligne, section, ligne finale)" || ko "S23a rc $RC (pas de rejeu / pas d'annonce) $(grep -F 'victim' "$OUT" | sed -n '1,3p')"
has "contention OU defaut intermittent, NON etabli" && ok "S23a la section n'affirme pas la cause (contention OU defaut intermittent)" || ko "S23a la section affirme une cause non etablie"
rm -f "$TMP/busy" "$TMP/busy.done" "$TMP/busy.seen"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "BUSY=$TMP/busy"
{ [ "$RC" -eq 1 ] && ! has "rejeu SEUL" && ! has "aucun rejeu"; } && ok "S23b CADRE_GATE_REPLAY=0 : le meme rouge reste ROUGE, aucun rejeu, aucun bruit" || ko "S23b rc $RC"
D="$(mk_toy s23c)"
green "$D" test_ok.py
wtf "$D" test_bad.py <<'PYEOF'
def test_bad():
    assert 0
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none
{ [ "$RC" -eq 1 ] && has "rejeu SEUL" && ! has "REJOUEES SEULES"; } && ok "S23c un rouge DETERMINISTE reste rouge apres rejeu" || ko "S23c rc $RC"
wtf "$D" test_bad2.py <<'PYEOF'
def test_bad2():
    assert 0
PYEOF
commit "$D" two
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=1
{ [ "$RC" -eq 1 ] && has "aucun rejeu" && ! has "rejeu SEUL de"; } && ok "S23d 2 rouges > CADRE_GATE_REPLAY=1 : aucun rejeu, ROUGE" || ko "S23d rc $RC"
if type -P timeout >/dev/null 2>&1; then
  D="$(mk_toy s23e)"
  green "$D" test_ok.py
  wtf "$D" test_hang.py <<'PYEOF'
import time


def test_hang():
    time.sleep(20)
PYEOF
  commit "$D" base
  rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_FILE_TIMEOUT=3
  { [ "$RC" -eq 1 ] && has "TIMEOUT(tue apres" && ! has "rejeu SEUL"; } && ok "S23e un TIMEOUT n'est JAMAIS rejoue (rejeu actif par defaut) : ROUGE en un seul budget" || ko "S23e rc $RC ($(grep -E 'TIMEOUT|rejeu' "$OUT" | tr '\n' '|'))"
else
  echo "SKIP: S23e — timeout GNU absent, pas de TIMEOUT a produire (S21 couvre l'annonce)"
fi
for V in f g; do
  D="$(mk_toy "s23$V")"
  green "$D" test_m1.py
  printf 'def test_r():\n    assert 0\n' > "$D/t/test_red.py"
  if [ "$V" = "g" ]; then printf 'def test_r2():\n    assert 0\n' > "$D/t/test_red2.py"; fi
  commit "$D" base
  printf 'def test_r():\n    assert 0  # changed\n' > "$D/t/test_red.py"
  commit "$D" second
  if [ "$V" = "f" ]; then
    rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0
    { [ "$RC" -eq 1 ] && [ "$(cnt 'rejeu SEUL de')" -eq 1 ]; } && ok "S23f un rouge deja rejoue (phase prioritaire) n'est PAS rejoue une 2e fois a la phase suivante" || ko "S23f rc $RC, $(cnt 'rejeu SEUL de') rejeu(x) (attendu 1)"
  else
    rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_REPLAY=1
    { [ "$RC" -eq 1 ] && [ "$(cnt 'rejeu SEUL de')" -eq 1 ] && has "aucun rejeu"; } && ok "S23g le plafond CADRE_GATE_REPLAY=1 vaut pour TOUT le run (prioritaire + reste)" || ko "S23g rc $RC, $(cnt 'rejeu SEUL de') rejeu(x) (attendu 1, puis aucun rejeu)"
  fi
done
fi

if want S24; then
echo "=== S24. auto A UN COEUR / REPONSE ILLISIBLE / GIT BASH : chemin NU ; auto PAR DEFAUT (aucun CADRE_GATE_*) : coeurs/2 bornes a 12"
D="$(mk_toy s24)"
green "$D" test_ok.py
green "$D" test_ok2.py
commit "$D" base
mkdir -p "$TMP/shim24a" "$TMP/shim24b" "$TMP/shim24c"
for c in getconf nproc sysctl; do printf '#!/bin/sh\necho 1\n' > "$TMP/shim24a/$c"; chmod +x "$TMP/shim24a/$c"; done
printf '#!/bin/sh\necho undefined\n' > "$TMP/shim24b/getconf"
printf '#!/bin/sh\necho garbage\n' > "$TMP/shim24b/nproc"
printf '#!/bin/sh\necho x\n' > "$TMP/shim24b/sysctl"
printf '#!/bin/sh\necho MINGW64_NT-10.0\n' > "$TMP/shim24c/uname"
chmod +x "$TMP/shim24b/getconf" "$TMP/shim24b/nproc" "$TMP/shim24b/sysctl" "$TMP/shim24c/uname"
for V in a b c; do
  rps "$D" CADRE_GATE_REPLAY=0 "PATH=$TMP/shim24$V:$PATH"
  { [ "$RC" -eq 0 ] && has "1 job — commande nue" && ! has "pytest shards:"; } && ok "S24$V auto -> chemin nu (rc 0, pas de ligne 'pytest shards:')" || ko "S24$V rc $RC ($(sed -n '1,3p' "$OUT" | tr '\n' '|'))"
done
if is_win; then
  echo "SKIP: S24d-g — sous Git Bash auto vaut 1 par conception (S24c le couvre)"
else
  # borne auto 12 (T-01M60XKFK7MPKZWNHH326ZMW3M) : S24f amende 40 -> 12 (etait 8), S24g 18 -> 9 (hote du pilote), S24d garde 16 -> 8
  for V in d:16:8 e:6:3 f:40:12 g:18:9; do
    _id="${V%%:*}"; _rest="${V#*:}"; _nc="${_rest%%:*}"; _nj="${_rest#*:}"
    cores_shim "$TMP/shim24$_id" "$_nc"
    rps "$D" "PATH=$TMP/shim24$_id:$PATH"
    { [ "$RC" -eq 0 ] && has "— $_nj jobs, echec rapide=prio, rejeu seul<=3" && has "pytest shards: VERT" && has "($_nj jobs)"; } \
      && ok "S24$_id DEFAUT (aucun CADRE_GATE_*) : $_nc coeurs -> $_nj jobs, pool joue, VERT" || ko "S24$_id rc $RC, $_nc coeurs ($(grep -F 'tests collectes' "$OUT" | sed -n '1p'))"
  done
fi
fi

if want S25; then
echo "=== S25. UNE BASE INTROUVABLE : annoncee, aucune phase prioritaire, TOUT est joue"
D="$(mk_toy s25)"
green "$D" test_ok.py
green "$D" test_ok2.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=sha-qui-n-existe-pas CADRE_GATE_REPLAY=0
{ [ "$RC" -eq 0 ] && has "introuvable" && has "2/2 unites"; } && ok "S25 base introuvable annoncee, 2/2 jouees" || ko "S25 rc $RC"
fi

if want S26; then
echo "=== S26. UN AVERTISSEMENT DE COLLECTE n'est pas un id (temoin positif du bloc d'ids) : VERT"
D="$(mk_toy s26)"
green "$D" test_ok.py
wtf "$D" test_warn.py <<'PYEOF'
class TestFoo:
    def __init__(self):
        pass

    def test_x(self):
        pass


def test_ok():
    pass
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "= bilan de pytest"; } && ok "S26 collecte avec avertissement : bloc d'ids lu, total = bilan de pytest, VERT" || ko "S26 rc $RC"
fi

if want S27; then
echo "=== S27. LES TRANCHES PAR DEFAUT (aucun CADRE_GATE_*) : un fichier de 250 tests est COUPE en tranches de <= 100"
if is_win; then
  echo "SKIP: S27 — sous Git Bash les tranches sont ETEINTES par conception (S20 couvre ce chemin)"
else
  D="$(mk_toy s27)"
  wtf "$D" test_big.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", range(250))
def test_p(n):
    assert n >= 0
PYEOF
  green "$D" test_ok.py
  commit "$D" base
  cores_shim "$TMP/shim27" 16
  rps "$D" "PATH=$TMP/shim27:$PATH"
  { [ "$RC" -eq 0 ] && has "pytest: 4 unites (1 fichier(s) coupe(s) en tranches de <= 100 tests)" && has "VERT — 4/4 unites" && has "252 passed"; } \
    && ok "S27 DEFAUT : 250 tests -> 3 tranches de <= 100 (+ 1 fichier), 252 passed = tout ce qui est collecte" || ko "S27 rc $RC ($(grep -F 'unites (' "$OUT"))"
fi
fi

if want S28; then
echo "=== S28. L'AVERTISSEMENT D'UNE UNITE VERTE est IMPRIME (son bloc 'warnings summary'), pas seulement compte"
# binome 7+8 (A F7) : la porte n'imprimait que la sortie des unites ROUGES ; un avertissement (canal de la rampe
# CroissanceToleree de T-952) ne restait qu'un « 1 warning » anonyme dans la ligne agregee.
D="$(mk_toy s28)"
green "$D" test_ok.py
wtf "$D" test_warn.py <<'PYEOF'
import warnings


def test_w():
    warnings.warn(UserWarning("TEMOIN-S28-avertissement-d-une-unite-verte"))
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_REPLAY=0 CADRE_GATE_BASE=none
{ [ "$RC" -eq 0 ] && has "TEMOIN-S28-avertissement-d-une-unite-verte" && has "warnings summary"; } \
  && ok "S28 unite verte avec avertissement : le TEXTE de l'avertissement est imprime, rc 0" || ko "S28 rc $RC, avertissement absent de la sortie"
[ "$(cnt 'TEMOIN-S28')" -le 2 ] && ok "S28 le bloc est imprime une fois (message + ligne source), jamais duplique" || ko "S28 $(cnt 'TEMOIN-S28') occurrences"
fi

# --- T-01M4WTYT8M : la TABLE DE DUREES (ordre et coupe, jamais le verdict) ------------------------------------
if want S29; then
echo "=== S29. SANS TABLE : poids = nombre de tests (l'ordre d'avant) ; apres un vert, pytest.tsv au chemin PAR DEFAUT, une ligne par fichier"
D="$(mk_toy s29)"
green "$D" test_a.py
green "$D" test_b.py
wtf "$D" test_c.py <<'PYEOF'
def test_x():
    pass
PYEOF
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0
TB="$D/$DEF_TB"
{ [ "$RC" -eq 0 ] && has "pytest: poids = nombre de tests (aucune table : " && has "; tete de file : t/test_"; } \
  && ok "S29 sans table : poids = nombre de tests, ANNONCE avec la tete de file" || ko "S29 rc $RC ($(grep -F 'poids' "$OUT"))"
{ [ -f "$TB" ] && [ "$(sed -n '1p' "$TB")" = "# v1" ] && [ "$(awk -F '\t' 'NR > 1 && NF == 3' "$TB" | awk 'END {print NR}')" -eq 3 ] \
  && [ "$(tget "$TB" t/test_a.py 2)" = "2" ] && [ "$(tget "$TB" t/test_c.py 2)" = "1" ] && has "table de durees $TB mise a jour (3 fichier(s)"; } \
  && ok "S29 apres un vert : pytest.tsv au chemin PAR DEFAUT, en-tete # v1, 3 lignes fichier<TAB>tests<TAB>secondes" \
  || ko "S29 table : $(tr '\t\n' '>|' < "$TB" 2>/dev/null || echo ABSENTE)"
fi

if want S30; then
echo "=== S30. UNE TABLE SEMEE (lent = 50 s pour 2 tests, nombreux = 1 s pour 6) : la tete de file est t/test_lent.py"
D="$(mk_toy s30)"
green "$D" test_lent.py
wtf "$D" test_nombreux.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", range(6))
def test_p(n):
    assert n >= 0
PYEOF
commit "$D" base
mkdir -p "$TMP/dur-s30"
printf '# v1\nt/test_lent.py\t2\t50\nt/test_nombreux.py\t6\t1\n' > "$TMP/dur-s30/pytest.tsv"
# CADRE_GATE_CHUNK=0 : t/test_lent.py (50 > 51/2) serait sinon COUPE en 2 (S31 couvre la coupe) — ici, l'ORDRE seul
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_CHUNK=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s30"
{ [ "$RC" -eq 0 ] && has "poids = durees mesurees ($TMP/dur-s30/pytest.tsv, 2 connus) ; tete de file : t/test_lent.py, t/test_nombreux.py"; } \
  && ok "S30 table semee : poids = durees mesurees, t/test_lent.py (2 tests) passe AVANT t/test_nombreux.py (6 tests)" || ko "S30 rc $RC ($(grep -F 'poids' "$OUT"))"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_CHUNK=0
{ [ "$RC" -eq 0 ] && has "poids = nombre de tests (aucune table : " && has "tete de file : t/test_nombreux.py, t/test_lent.py"; } \
  && ok "S30 non-vacuite : sans la table, le meme jouet met t/test_nombreux.py en tete (poids par compte)" || ko "S30 sans table : rc $RC ($(grep -F 'poids' "$OUT"))"
fi

if want S31; then
echo "=== S31. COUPE PAR DUREE : un fichier qui bornerait seul la jambe (estimation > somme/JOBS) est coupe au 2e passage ; CADRE_GATE_CHUNK=0 l'eteint"
if is_win; then
  echo "SKIP: S31 — sous Git Bash les tranches sont ETEINTES par conception (S20 couvre ce chemin)"
else
  D="$(mk_toy s31)"
  wtf "$D" test_dom.py <<'PYEOF'
import time

import pytest


@pytest.mark.parametrize("n", range(8))
def test_d(n):
    time.sleep(0.5)
PYEOF
  wtf "$D" test_small.py <<'PYEOF'
def test_s():
    pass
PYEOF
  commit "$D" base
  rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s31"
  { [ "$RC" -eq 0 ] && has "pytest: 2 unites (0 fichier(s) coupe(s)" && has "poids = nombre de tests (aucune table"; } \
    && ok "S31 1er passage (aucune table) : 0 fichier coupe, poids par compte" || ko "S31 1er passage rc $RC ($(grep -F 'unites (' "$OUT"))"
  rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s31"
  { [ "$RC" -eq 0 ] && has "pytest: 3 unites (1 fichier(s) coupe(s)" && has "1 fichier(s) coupe(s) PAR DUREE" && has "9 passed" && has "VERT — 3/3 unites"; } \
    && ok "S31 2e passage : t/test_dom.py coupe PAR DUREE en 2 tranches, VERT, 9 passed = tout ce qui est collecte" || ko "S31 2e passage rc $RC ($(grep -E 'unites \(|PAR DUREE|poids' "$OUT" | tr '\n' '|'))"
  rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_CHUNK=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s31"
  { [ "$RC" -eq 0 ] && has "poids = durees mesurees" && has "pytest: 2 unites (0 fichier(s) coupe(s)" && ! has "PAR DUREE" && has "9 passed"; } \
    && ok "S31 CADRE_GATE_CHUNK=0 : la table est lue (poids = durees) mais AUCUNE coupe" || ko "S31 CHUNK=0 rc $RC ($(grep -E 'unites \(|PAR DUREE|poids' "$OUT" | tr '\n' '|'))"
fi
fi

if want S32; then
echo "=== S32. LA FUSION : ligne illisible comptee ET gardee, fichier neuf estime, entree disparue conservee, entree d'un fichier ROUGE non reecrite"
D="$(mk_toy s32)"
green "$D" test_known.py
green "$D" test_new.py
wtf "$D" test_red.py <<'PYEOF'
def test_r():
    assert 0
PYEOF
commit "$D" base
mkdir -p "$TMP/dur-s32"
printf '# v1\nceci-n-est-pas-une-ligne\nt/gone.py\t3\t7\nt/test_known.py\t9\t5\nt/test_red.py\t1\t99\n' > "$TMP/dur-s32/pytest.tsv"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s32"
TB="$TMP/dur-s32/pytest.tsv"
{ [ "$RC" -eq 1 ] && has "pytest shards: ROUGE"; } && ok "S32 rc 1 : t/test_red.py rouge, la table ne touche JAMAIS le verdict" || ko "S32 rc $RC"
has "1 ligne(s) illisible(s) dans $TB" && ok "S32 la ligne illisible est COMPTEE et annoncee" || ko "S32 ligne illisible non annoncee ($(grep -F 'illisible' "$OUT"))"
has "1 fichier(s) sans duree (estimes" && ok "S32 t/test_new.py (absent de la table) est ESTIME et annonce" || ko "S32 fichier neuf non annonce ($(grep -F 'sans duree' "$OUT"))"
[ "$(tget "$TB" t/gone.py 3)" = "7" ] && ok "S32 t/gone.py (fichier disparu) CONSERVE : la fusion n'efface rien" || ko "S32 t/gone.py : « $(tget "$TB" t/gone.py 3) » (attendu 7)"
[ "$(tget "$TB" t/test_red.py 3)" = "99" ] && ok "S32 l'entree du fichier ROUGE n'est PAS reecrite (99 garde)" || ko "S32 t/test_red.py reecrit : « $(tget "$TB" t/test_red.py 3) »"
{ [ "$(tget "$TB" t/test_known.py 2)" = "2" ] && [ "$(tget "$TB" t/test_new.py 2)" = "2" ]; } \
  && ok "S32 les fichiers VERTS sont (re)ecrits : t/test_known.py 9 -> 2 tests, t/test_new.py ajoute" || ko "S32 known=$(tget "$TB" t/test_known.py 2) new=$(tget "$TB" t/test_new.py 2)"
{ grep -qxF "ceci-n-est-pas-une-ligne" "$TB" && [ "$(sed -n '1p' "$TB")" = "# v1" ] && [ "$(grep -c '^# v1$' "$TB")" -eq 1 ]; } \
  && ok "S32 la ligne illisible est GARDEE telle quelle, un seul en-tete # v1" || ko "S32 table : $(tr '\t\n' '>|' < "$TB")"
fi

if want S33; then
echo "=== S33. CADRE_GATE_DURATIONS_DIR est LUE PUIS RETIREE : absente chez chaque unite (pool) ET sous l'exec nu (JOBS=1) ; la table va au dossier demande"
D="$(mk_toy s33)"
wtf "$D" test_env.py <<'PYEOF'
import os


def test_absent():
    assert "CADRE_GATE_DURATIONS_DIR" not in os.environ
PYEOF
green "$D" test_ok.py
commit "$D" base
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s33"
{ [ "$RC" -eq 0 ] && [ "$(tget "$TMP/dur-s33/pytest.tsv" t/test_env.py 2)" = "1" ] && [ ! -e "$D/.agents/state/local/porte-durees" ]; } \
  && ok "S33 pool : variable ABSENTE chez l'unite (VERT) ; table ecrite sous le dossier DEMANDE, rien au chemin par defaut" || ko "S33 pool rc $RC ($(grep -E 'FAIL|table' "$OUT" | tr '\n' '|'))"
rps "$D" CADRE_GATE_JOBS=1 "CADRE_GATE_DURATIONS_DIR=$TMP/dur-s33"
{ [ "$RC" -eq 0 ] && has "1 job — commande nue"; } && ok "S33 chemin nu (JOBS=1) : variable ABSENTE sous l'exec pytest (VERT)" || ko "S33 chemin nu rc $RC ($(grep -E 'assert|passed|failed' "$OUT" | tr '\n' '|'))"
fi

# --- T-01M5QBFKM444FB53RM2J1NBB4X : `--only` et le canal CADRE_GATE_ROUGES_OUT (le rejeu des rouges de verify.sh) ----
if want S34; then
echo "=== S34. --only RESTREINT la collecte, refuse un chemin non admis ou sans test, ne prend jamais l'exec nu ; CADRE_GATE_ROUGES_OUT recoit les rouges JOUEES et n'atteint aucun fils"
D="$(mk_toy s34)"
wtf "$D" test_a.py <<'PYEOF'
def test_r1():
    assert 0


def test_r2():
    assert 0
PYEOF
green "$D" test_b.py
wtf "$D" test_c.py <<'PYEOF'
import os


def test_mark():
    open(os.environ["S34_MARK"], "w").close()
PYEOF
wtf "$D" test_env.py <<'PYEOF'
import os


def test_absent():
    assert "CADRE_GATE_ROUGES_OUT" not in os.environ
PYEOF
commit "$D" base
#   (a) MUTANT : chemins --only non passes a la collecte -> t/test_c.py est joue, S34_MARK existe -> KO.
rm -f "$TMP/s34-mark" "$TMP/s34-rouges"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 "S34_MARK=$TMP/s34-mark" "CADRE_GATE_ROUGES_OUT=$TMP/s34-rouges" -- --only t/test_a.py
{ [ "$RC" -eq 1 ] && [ ! -e "$TMP/s34-mark" ] && grep -qE '^--- \[1/1\] FAIL\(rc=1\) t/test_a\.py' "$OUT"; } \
  && ok "S34a --only t/test_a.py : rc 1, une seule unite jouee, t/test_c.py JAMAIS lance" || ko "S34a rc $RC mark=$([ -e "$TMP/s34-mark" ] && echo present || echo absent) ($(grep -E '^--- ' "$OUT" | tr '\n' '|'))"
[ "$(cat "$TMP/s34-rouges" 2>/dev/null)" = "t/test_a.py" ] \
  && ok "S34a CADRE_GATE_ROUGES_OUT = t/test_a.py, une ligne" || ko "S34a liste des rouges : « $(tr '\n' '|' < "$TMP/s34-rouges" 2>/dev/null) »"
#   (b) MUTANT : validation retiree -> le message nomme n'apparait plus -> KO.
for _bad in -x.py ../a.py /abs/t.py 't/a b.py' t/test_b.sh; do
  rps "$D" CADRE_GATE_JOBS=2 -- --only "$_bad"
  { [ "$RC" -eq 2 ] && has "n'est pas un chemin de test .py admis — refusé"; } \
    && ok "S34b --only « $_bad » refuse rc 2, nomme" || ko "S34b --only « $_bad » rc $RC ($(tail -n 2 "$OUT" | tr '\n' '|'))"
done
rps "$D" CADRE_GATE_JOBS=2 -- --only t/nope.py
{ [ "$RC" -eq 2 ] && has "ne collecte aucun test — refusé"; } && ok "S34b --only t/nope.py (absent) : rc 2, ne collecte aucun test" || ko "S34b nope rc $RC ($(tail -n 2 "$OUT" | tr '\n' '|'))"
rps "$D" CADRE_GATE_JOBS=2 -- --only t/test_b.py --only t/nope.py
{ [ "$RC" -eq 2 ] && has "ne collecte aucun test — refusé"; } && ok "S34b un chemin sur deux absent : rc 2" || ko "S34b partiel rc $RC ($(tail -n 2 "$OUT" | tr '\n' '|'))"
#   fichier EXISTANT sans aucun test : pytest le collecte rc 0 (zero id) ; seule la boucle « chaque chemin liste est
#   collecte » le refuse. MUTANT : boucle retiree -> rc 0, t/test_b.py seul joue -> KO.
printf 'X = 1\n' > "$D/t/test_empty.py"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none -- --only t/test_b.py --only t/test_empty.py
rm -f "$D/t/test_empty.py"
{ [ "$RC" -eq 2 ] && has "--only « t/test_empty.py » ne collecte aucun test — refusé"; } \
  && ok "S34b un fichier existant SANS test parmi deux : rc 2, nomme (chaque chemin liste est collecte)" || ko "S34b fichier vide rc $RC ($(tail -n 2 "$OUT" | tr '\n' '|'))"
rps "$D" CADRE_GATE_JOBS=2 -- --bogus
[ "$RC" -eq 2 ] && ok "S34b argument inconnu : rc 2" || ko "S34b argument inconnu rc $RC"
#   (c) MUTANT : garde JOBS<=1 retiree -> la ligne « commande nue » apparait -> KO.
rps "$D" CADRE_GATE_JOBS=1 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 -- --only t/test_b.py
{ [ "$RC" -eq 0 ] && ! has "commande nue" && grep -qE '^--- \[1/1\] PASS t/test_b\.py' "$OUT"; } \
  && ok "S34c CADRE_GATE_JOBS=1 --only : pool d'un job, jamais l'exec nu" || ko "S34c rc $RC ($(grep -E 'commande nue|^--- ' "$OUT" | tr '\n' '|'))"
#   (d) vert -> aucun fichier ; MUTANT : unset deplace apres le lancement -> t/test_env.py rougit -> KO.
rm -f "$TMP/s34-rouges"
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_ROUGES_OUT=$TMP/s34-rouges" -- --only t/test_b.py --only t/test_env.py
{ [ "$RC" -eq 0 ] && [ ! -e "$TMP/s34-rouges" ]; } \
  && ok "S34d vert : aucun fichier ; le fils ne voit PAS CADRE_GATE_ROUGES_OUT" || ko "S34d rc $RC fichier=$([ -e "$TMP/s34-rouges" ] && echo present || echo absent) ($(grep -E 'assert|^--- ' "$OUT" | tr '\n' '|'))"
#   (e) dossier de sortie absent -> le rc reste celui du verdict (1).
rps "$D" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 "CADRE_GATE_ROUGES_OUT=$TMP/s34-nodir/x" -- --only t/test_a.py
{ [ "$RC" -eq 1 ] && [ ! -e "$TMP/s34-nodir" ]; } && ok "S34e sortie impossible a ecrire : rc 1 inchange" || ko "S34e rc $RC"
#   (f) deux tranches d'un meme fichier rouge -> UNE ligne.
D2="$(mk_toy s34f)"
wtf "$D2" test_big.py <<'PYEOF'
import pytest


@pytest.mark.parametrize("n", range(4))
def test_r(n):
    assert 0
PYEOF
commit "$D2" base
rm -f "$TMP/s34f-rouges"
rps "$D2" CADRE_GATE_JOBS=2 CADRE_GATE_BASE=none CADRE_GATE_REPLAY=0 CADRE_GATE_FAIL_FAST=0 CADRE_GATE_CHUNK=2 "CADRE_GATE_ROUGES_OUT=$TMP/s34f-rouges"
{ [ "$RC" -eq 1 ] && has "pytest: 2 unites (1 fichier(s) coupe(s)" && [ "$(cat "$TMP/s34f-rouges" 2>/dev/null)" = "t/test_big.py" ]; } \
  && ok "S34f deux tranches rouges d'un fichier : une seule ligne t/test_big.py" || ko "S34f rc $RC ($(grep -F 'unites (' "$OUT")) liste « $(tr '\n' '|' < "$TMP/s34f-rouges" 2>/dev/null) »"
fi

echo
echo "================================================================"
echo "run-pytest-shards: $passed passed / $failed failed"
[ "$failed" -eq 0 ] || exit 1
echo "Verdict: sur ces jouets, la porte ne rend pas vert ce que pytest nu rend rouge ; chaque garde nommee (defauts compris) a un temoin qui rougit."
