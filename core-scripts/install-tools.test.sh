#!/usr/bin/env bash
# ============================================================================
# core-scripts/install-tools.test.sh — prouve core-scripts/install-tools.sh
# (BK-344) SANS RIEN INSTALLER ET SANS RÉSEAU.
#
# Tout se joue sous un dossier jetable (mktemp -d) : un inventaire-FIXTURE, un
# ci.yml-FIXTURE (et son fichier d'exigences `-r`), des archives `file://`
# fabriquées ici, et un BOUCHON d'interpréteur posé seul dans
# INSTALL_TOOLS_PROBE_PATH : `-I -m venv` crée un faux venv dont l'interpréteur
# journalise ses arguments (pip n'est jamais lancé, le fichier d'exigences est
# copié) ; le reste passe au vrai interpréteur (téléchargement `file://`,
# empreintes). Le doctor, avant et après --appliquer, lit l'inventaire-FIXTURE.
# Les marqueurs d'agent sont ôtés (`env -u`) pour chaque appel, sauf en I2.
# Auto-découvert par core-scripts/run-bash-tests.sh (glob *.test.sh).
#
# CAS (témoins I1-I10 de l'annexe de la tâche), chacun tenu par un mutant rouge :
#   I1  défaut = --plan : préfixe absent, bouchon jamais appelé ; les lignes sans
#       épingle (k6, terraform de la fixture) dites « aucun épinglage ».
#   I2  marqueur d'agent + --appliquer : rc 7, rien écrit, pour CHAQUE marqueur ;
#       la liste == AGENT_CALLER_MARKERS de .agents/bin/skills_github_fallback.py.
#   I3  curl-sha256 heureux : binaire sous <préfixe>/bin, reçu, doctor rc 0 ; 2e
#       passe : « déjà installé » (gitleaks, pytest, semgrep), aucun téléchargement,
#       toujours 2 venvs au journal ; le bouchon refuse `-m venv` sans `-I`.
#   I4  sha256 faux : rc 1, rien sous <préfixe>/bin.
#   I5  archive à membre `../gitleaks`, puis à membre lien : refus, rien posé.
#   I6  pip-hash : drapeaux == ceux de .github/workflows/ci.yml (réel), et le
#       fichier passé porte `pytest==9.1.1 --hash=`.
#   I7  darwin/arm64 face au seul asset linux_x64 : dit, rien téléchargé.
#   I8  épingle absente des sources : « épinglage introuvable », rc 1, aucun pip ;
#       I8bis : le job qui la pose absent du workflow, même verdict, en --plan.
#   I9  le code (commentaires ôtés) ne nomme aucun outil de l'inventaire RÉEL
#       (sauf l'appel `awk -…`, comme le cas 13 de doctor.test.sh), et ne porte
#       aucune forme de sonde balayée par doctor-parity.test.sh.
#   I10 Windows : rc 2 ; deux sources d'exigences => deux venvs distincts.
#   I11 pip-hash sur linux/arm64 (job ubuntu x64), puis job en CPython 2.7 :
#       « non installable ici », raison nommée, jamais « à installer ».
#   I12 venv sans bin/semgrep : ÉCHEC nommé du lien, rc 1, aucun reçu.
#   I13 --prefix /usr, puis un préfixe à `..`, puis à `:` : rc 2 nommé ;
#       --hors-home admet /usr.
#   I14 préfixe à espace et apostrophe : la ligne `export PATH=…`, sourcée, rend
#       le PATH attendu.
#   I15 inventaire à classe X : le doctor ne dit pas semgrep PRESENT => rc 1.
#   I16 venv d'outil CLI hors PATH (lien sous bin/) ; venv d'outil MODULE sans
#       pytest devant le pytest de l'utilisateur => « masqué : pytest », rc 1.
#   I17 reçu juste, version dérivée dans le venv => « à installer ».
#   I18 verrou déjà posé => rc 1, rien fait. I19 venv qui est un lien => refus.
#   I20 inventaire réel : `python3|python|py` dit une fois aux non installés.
#   HOME vaut le dossier jetable pour chaque appel de `lance`.
#
# Exit : 0 tous les cas passent · 1 au moins un échoue.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SUT="$ROOT/core-scripts/install-tools.sh"
INV_REEL="$ROOT/core-scripts/tool-inventory.tsv"
CI_REEL="$ROOT/.github/workflows/ci.yml"
FALLBACK="$ROOT/.agents/bin/skills_github_fallback.py"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok() { echo "--- PASS $1"; pass=$((pass + 1)); }
ko() { echo "--- FAIL $1"; fail=$((fail + 1)); }
montre() { sed 's/^/      /' "$1"; }

REEL=""
for c in python3 python; do
  p="$(type -P "$c" 2>/dev/null)" || continue
  if "$p" --version >/dev/null 2>&1; then
    REEL="$p"
    break
  fi
done
if [ -z "$REEL" ]; then
  ko "aucun interpréteur réel : le banc ne peut fabriquer ses fixtures"
  echo "install-tools.test.sh: $pass passed, $fail failed"
  exit 1
fi

# --- le bouchon d'interpréteur et son faux venv ----------------------------
# L'interpréteur du faux venv : `-I -m pip install … -r <f>` copie <f> en
# <venv>/installe.txt (ce que le venv « porte ») ; `-I -c … <dist>` rend la version
# de <dist> lue dans installe.txt (importlib.metadata simulé) ; `-m pytest` ne
# répond que si le venv porte pytest ; tout autre appel : rc 0.
cat > "$TMP/vpy" <<'EOF'
#!/bin/sh
printf 'vpy %s\n' "$*" >> "$IT_JOURNAL"
d="$(dirname "$0")/.."
if [ "$1" = "-I" ] && [ "$2" = "-m" ] && [ "$3" = "pip" ]; then
  for a in "$@"; do r="$a"; done
  cp "$r" "$d/installe.txt" || exit 1
  exit 0
fi
if [ "$1" = "-I" ] && [ "$2" = "-c" ]; then
  sed -n "s/^$4==\([^ ;]*\).*\$/\1/p" "$d/installe.txt" 2>/dev/null
  exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
  grep -q '^pytest==' "$d/installe.txt" 2>/dev/null || exit 1
  echo 'pytest 9.1.1 (venv)'
fi
exit 0
EOF
chmod +x "$TMP/vpy"
mkdir -p "$TMP/sonde"
# L'interpréteur de sonde : `-I -m venv` seul crée le faux venv (bin/python3 + le
# point d'entrée bin/semgrep, sauf sous IT_SANS_SEMGREP=1, cas I12) ; `-m venv`
# sans `-I` est journalisé et refusé (rc 1) : retirer `-I` fait rougir I3.
# `-m pytest` : le pytest « de l'utilisateur », toujours présent (cas I16) ; tout
# autre `-m` : absent. Le reste passe au vrai interpréteur.
cat > "$TMP/sonde/python3" <<'EOF'
#!/bin/sh
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
  printf 'venv-sans-I %s\n' "$*" >> "$IT_JOURNAL"
  exit 1
fi
if [ "$1" = "-I" ] && [ "$2" = "-m" ] && [ "$3" = "venv" ]; then
  for a in "$@"; do d="$a"; done
  printf 'venv %s\n' "$d" >> "$IT_JOURNAL"
  mkdir -p "$d/bin" || exit 1
  cp "$IT_VPY" "$d/bin/python3" || exit 1
  if [ "${IT_SANS_SEMGREP:-0}" != "1" ]; then cp "$IT_VPY" "$d/bin/semgrep" || exit 1; fi
  exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
  echo 'pytest 9.0.0 (utilisateur)'
  exit 0
fi
if [ "$1" = "-m" ]; then
  exit 1
fi
exec "$IT_REEL" "$@"
EOF
chmod +x "$TMP/sonde/python3"
export IT_VPY="$TMP/vpy"
export IT_REEL="$REEL"
PYV_REEL="$("$REEL" -I -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

# --- les archives file:// ----------------------------------------------------
ARCH_PY='
import hashlib, io, sys, tarfile
mode, out = sys.argv[1], sys.argv[2]
def add(tf, name, data=None, link=None):
    ti = tarfile.TarInfo(name)
    if link is not None:
        ti.type = tarfile.SYMTYPE
        ti.linkname = link
        tf.addfile(ti)
    else:
        ti.size = len(data)
        ti.mode = 0o755
        tf.addfile(ti, io.BytesIO(data))
with tarfile.open(out, "w:gz") as tf:
    if mode == "bon":
        add(tf, "gitleaks", b"#!/bin/sh\necho faux-t1003\n")
    elif mode == "remonte":
        add(tf, "../gitleaks", b"#!/bin/sh\necho remonte\n")
    else:
        add(tf, "autre", b"#!/bin/sh\necho autre\n")
        add(tf, "gitleaks", link="autre")
with open(out, "rb") as f:
    print(hashlib.sha256(f.read()).hexdigest())
'
ASSET='gitleaks_8.30.1_linux_x64.tar.gz'
for m in bon remonte lien; do
  mkdir -p "$TMP/a_$m"
  "$REEL" -I -c "$ARCH_PY" "$m" "$TMP/a_$m/$ASSET" > "$TMP/a_$m/sha" || ko "fixture d'archive $m"
done
SHA_BON="$(sed -n 1p "$TMP/a_bon/sha")"
SHA_FAUX="0000000000000000000000000000000000000000000000000000000000000000"
H1='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
H2='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
H3='cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'

# --- l'inventaire-fixture (toutes les colonnes que lit le doctor) -------------
T="$(printf '\t')"
{
  printf '%s\n' '# inventaire-fixture de install-tools.test.sh'
  printf '%s\n' "tool${T}nature${T}os${T}class${T}version${T}version_src${T}ci_pin${T}apt${T}brew${T}windows${T}cost${T}probe${T}skips${T}mode_sonde"
  printf '%s\n' "pytest${T}outil${T}any${T}B${T}-${T}-${T}9.1.1@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}module:python3"
  printf '%s\n' "gitleaks${T}outil${T}any${T}A${T}-${T}-${T}8.30.1@curl-sha256(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-"
  printf '%s\n' "semgrep${T}outil${T}any${T}A${T}-${T}-${T}1.175.0@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-"
  printf '%s\n' "k6${T}outil${T}any${T}A${T}-${T}-${T}-${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-"
  printf '%s\n' "terraform${T}outil${T}any${T}A${T}-${T}-${T}-${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-"
} > "$TMP/inv.tsv"
# Variantes : I16a (semgrep, CLI, AVANT pytest), I16b (un outil MODULE épinglé
# dans gardes, pytest non épinglé : « celui de l'utilisateur »), I15 (classe X).
L_PYTEST="pytest${T}outil${T}any${T}B${T}-${T}-${T}9.1.1@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}module:python3"
L_SEMGREP="semgrep${T}outil${T}any${T}A${T}-${T}-${T}1.175.0@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-"
L_ENTETE="$(sed -n 2p "$TMP/inv.tsv")"
printf '%s\n' "$L_ENTETE" "$L_SEMGREP" "$L_PYTEST" > "$TMP/inv_f1.tsv"
printf '%s\n' "$L_ENTETE" \
  "outilmod${T}outil${T}any${T}A${T}-${T}-${T}1.0.0@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}module:python3" \
  "pytest${T}outil${T}any${T}B${T}-${T}-${T}-${T}-${T}-${T}-${T}fixture${T}-${T}-${T}module:python3" > "$TMP/inv_masque.tsv"
printf '%s\n' "$L_ENTETE" "$L_PYTEST" \
  "semgrep${T}outil${T}any${T}X${T}-${T}-${T}1.175.0@pip-hash(tests)${T}-${T}-${T}-${T}fixture${T}-${T}-${T}-" > "$TMP/inv_x.tsv"

# racine <dir> <url> <sha> <avec_pytest 0|1> [<version python du job>] : ci.yml-fixture
# et son -r ; version par défaut : celle de l'interpréteur réel (que le bouchon relaie).
racine() {
  mkdir -p "$1/.github/workflows" "$1/.agents/security"
  printf '%s\n' "semgrep==1.175.0 --hash=sha256:$H3" "pygments==2.21.0 --hash=sha256:$H3" \
    "outilmod==1.0.0 --hash=sha256:$H3" > "$1/.agents/security/gardes.txt"
  {
    printf '%s\n' 'jobs:' '  tests:' '    strategy:' '      matrix:' '        os: [ubuntu-latest, macos-latest]' \
      '    runs-on: ${{ matrix.os }}' '    steps:' '      - uses: actions/setup-python@v0' '        with:' \
      "          python-version: \"${5:-$PYV_REEL}\"" '      - name: deps' '        run: |' \
      "          cat > \"\$REQ\" <<'EOF'"
    if [ "$4" = "1" ]; then
      printf '%s\n' "          pytest==9.1.1 --hash=sha256:$H1"
    fi
    printf '%s\n' "          pluggy==1.6.0 --hash=sha256:$H2" '          EOF' \
      '          python -m pip install --require-hashes --only-binary :all: --disable-pip-version-check -r "$REQ"' \
      '      - name: gardes' \
      '        run: python -m pip install --require-hashes --only-binary :all: --disable-pip-version-check -r .agents/security/gardes.txt' \
      '      - name: Install gitleaks' '        run: |' \
      "          curl -fsSL -o \"\$RUNNER_TEMP/g.tar.gz\" $2" \
      "          echo \"$3  \$RUNNER_TEMP/g.tar.gz\" | sha256sum -c -"
  } > "$1/.github/workflows/ci.yml"
}

# lance <cas> <os> <arch> <args…> : sortie dans $TMP/<cas>.out, rc dans RC ;
# journal du bouchon : $TMP/<cas>.journal ; marqueurs d'agent ôtés.
lance() {
  local cas="$1" os="$2" arch="$3"
  shift 3
  env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u AGENTS_HOOK_HOST -u COPILOT_AGENT_SESSION_ID -u COPILOT_CLI \
    "HOME=$TMP" "IT_JOURNAL=$TMP/$cas.journal" "INSTALL_TOOLS_OS=$os" "INSTALL_TOOLS_ARCH=$arch" \
    "INSTALL_TOOLS_PROBE_PATH=$TMP/sonde" \
    "$BASH" "$SUT" --inventory "$TMP/inv.tsv" "$@" > "$TMP/$cas.out" 2>&1
  RC=$?
}

racine "$TMP/r_bon" "file://$TMP/a_bon/$ASSET" "$SHA_BON" 1

# ---------------------------------------------------------------------------
# I1 — défaut = --plan : rien écrit, aucun appel au bouchon de venv
# ---------------------------------------------------------------------------
lance i1 linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p1"
if [ "$RC" -eq 0 ] && [ ! -e "$TMP/p1" ] && [ ! -e "$TMP/i1.journal" ] \
  && grep -q '^install-tools: mode plan' "$TMP/i1.out" \
  && grep '^install-tools: aucun épinglage' "$TMP/i1.out" | grep -qw k6 \
  && grep '^install-tools: aucun épinglage' "$TMP/i1.out" | grep -qw terraform \
  && ! grep -q 'téléchargement :' "$TMP/i1.out"; then
  ok "I1 : défaut --plan — préfixe absent, bouchon jamais appelé, k6 et terraform dits « aucun épinglage »"
else
  ko "I1 : défaut --plan (rc=$RC, préfixe non vide ou bouchon appelé ou ligne absente)"
  montre "$TMP/i1.out"
fi

# ---------------------------------------------------------------------------
# I2 — marqueur d'agent + --appliquer : rc 7, rien écrit ; liste == fallback
# ---------------------------------------------------------------------------
LISTE_SUT="$(sed -n "s/^MARQUEURS='\(.*\)'\$/\1/p" "$SUT")"
LISTE_REF="$(sed -n '/^AGENT_CALLER_MARKERS = (/,/^)/p' "$FALLBACK" | sed -n 's/^[[:space:]]*"\([A-Z_]*\)",.*$/\1/p' | tr '\n' ' ' | sed 's/ $//')"
if [ -n "$LISTE_REF" ] && [ "$LISTE_SUT" = "$LISTE_REF" ]; then
  ok "I2 : marqueurs == AGENT_CALLER_MARKERS ($LISTE_REF)"
else
  ko "I2 : marqueurs « $LISTE_SUT » ≠ AGENT_CALLER_MARKERS « $LISTE_REF »"
fi
n2=0
bad2=""
for mk in $LISTE_REF; do
  n2=$((n2 + 1))
  env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u AGENTS_HOOK_HOST -u COPILOT_AGENT_SESSION_ID -u COPILOT_CLI \
    "$mk=1" "IT_JOURNAL=$TMP/i2.journal" INSTALL_TOOLS_OS=linux INSTALL_TOOLS_ARCH=x64 \
    "INSTALL_TOOLS_PROBE_PATH=$TMP/sonde" \
    "$BASH" "$SUT" --appliquer --inventory "$TMP/inv.tsv" --ci "$TMP/r_bon/.github/workflows/ci.yml" \
    --prefix "$TMP/p2" > "$TMP/i2.out" 2>&1
  r2=$?
  if [ "$r2" -ne 7 ] || [ -e "$TMP/p2" ] || [ -e "$TMP/i2.journal" ] || ! grep -q "$mk est pose" "$TMP/i2.out"; then
    bad2="$bad2 $mk(rc=$r2)"
  fi
done
if [ "$n2" -ge 1 ] && [ -z "$bad2" ]; then
  ok "I2 : chacun des $n2 marqueurs + --appliquer — rc 7, rien écrit, marqueur nommé"
else
  ko "I2 : garde d'agent :${bad2:- aucun marqueur lu}"
  montre "$TMP/i2.out"
fi

# ---------------------------------------------------------------------------
# I3 — curl-sha256 heureux, puis idempotence (I6 et I10 lisent ce journal)
# ---------------------------------------------------------------------------
lance i3 linux x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p3"
rc3a=$RC
cp "$TMP/i3.out" "$TMP/i3a.out"
ntel1="$(grep -c 'téléchargement :' "$TMP/i3a.out")"
lance i3 linux x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p3"
rc3b=$RC
ntel2="$(grep -c 'téléchargement :' "$TMP/i3.out")"
if [ "$rc3a" -eq 0 ] && [ "$ntel1" -eq 1 ] && [ -x "$TMP/p3/bin/gitleaks" ] && [ ! -L "$TMP/p3/bin/gitleaks" ] \
  && grep -q 'faux-t1003' "$TMP/p3/bin/gitleaks" && grep -qF "8.30.1@curl-sha256 $SHA_BON" "$TMP/p3/recus/gitleaks" \
  && grep -qF 'install-tools: doctor (re-sonde sous ce PATH, rc 0)' "$TMP/i3a.out" \
  && ! grep -q 'pas PRESENT sous ce PATH\|masqué' "$TMP/i3a.out" \
  && [ -L "$TMP/p3/bin/semgrep" ] && [ -x "$TMP/p3/bin/semgrep" ] && [ ! -e "$TMP/p3/.verrou" ] \
  && grep -qF "export PATH=$TMP/p3/bin:$TMP/p3/venvs/ci-yml/bin:\"\$PATH\"" "$TMP/i3a.out"; then
  ok "I3 : curl-sha256 — binaire posé, reçu écrit, semgrep lié sous bin/, venv gardes hors PATH, doctor vert (rc 0), verrou retiré"
else
  ko "I3 : curl-sha256 (rc=$rc3a, téléchargements=$ntel1)"
  montre "$TMP/i3a.out"
fi
nvenv3="$(grep -c '^venv ' "$TMP/i3.journal")"
if [ "$rc3b" -eq 0 ] && [ "$ntel2" -eq 0 ] && grep -q 'gitleaks 8.30.1 : déjà installé' "$TMP/i3.out" \
  && grep -q 'pytest 9.1.1 : déjà installé' "$TMP/i3.out" && grep -q 'semgrep 1.175.0 : déjà installé' "$TMP/i3.out" \
  && [ "$nvenv3" -eq 2 ]; then
  ok "I3 : relance — « déjà installé », aucun téléchargement, aucun venv refait"
else
  ko "I3 : relance non idempotente (rc=$rc3b, téléchargements=$ntel2, venvs créés sur les deux passes=$nvenv3)"
  montre "$TMP/i3.out"
fi

# ---------------------------------------------------------------------------
# I4 — sha256 faux : rc 1, rien sous bin que le lien semgrep (outil CLI pip-hash)
# ---------------------------------------------------------------------------
racine "$TMP/r_faux" "file://$TMP/a_bon/$ASSET" "$SHA_FAUX" 1
lance i4 linux x64 --appliquer --ci "$TMP/r_faux/.github/workflows/ci.yml" --prefix "$TMP/p4"
if [ "$RC" -eq 1 ] && [ "$(ls -A "$TMP/p4/bin" 2>/dev/null)" = "semgrep" ] && [ -L "$TMP/p4/bin/semgrep" ] \
  && [ ! -e "$TMP/p4/recus/gitleaks" ] && grep -q 'rien n est ecrit' "$TMP/i4.out"; then
  ok "I4 : sha256 faux — rc 1, rien sous <préfixe>/bin hors du lien semgrep, aucun reçu gitleaks"
else
  ko "I4 : sha256 faux (rc=$RC)"
  montre "$TMP/i4.out"
  ls -la "$TMP/p4/bin" 2>&1 | sed 's/^/      /'
fi

# ---------------------------------------------------------------------------
# I5 — membre `../gitleaks`, puis membre lien : refus, rien posé
# ---------------------------------------------------------------------------
for m in remonte lien; do
  racine "$TMP/r_$m" "file://$TMP/a_$m/$ASSET" "$(sed -n 1p "$TMP/a_$m/sha")" 1
  lance "i5$m" linux x64 --appliquer --ci "$TMP/r_$m/.github/workflows/ci.yml" --prefix "$TMP/p5$m/x"
  if [ "$RC" -eq 1 ] && [ ! -e "$TMP/p5$m/x/bin/gitleaks" ] && [ ! -L "$TMP/p5$m/x/bin/gitleaks" ] \
    && [ ! -e "$TMP/p5$m/x/gitleaks" ] && [ ! -e "$TMP/p5$m/gitleaks" ] && [ ! -e "$TMP/p5$m/x/bin/autre" ]; then
    ok "I5 : archive « $m » — refus, rc 1, rien posé"
  else
    ko "I5 : archive « $m » (rc=$RC)"
    montre "$TMP/i5$m.out"
  fi
done

# ---------------------------------------------------------------------------
# I6 — pip-hash : drapeaux de ci.yml (réel), fichier qui porte l'épingle
# ---------------------------------------------------------------------------
DRAP_CI="$(grep -E 'pip install .* -r ' "$CI_REEL" | sed 's/^.*pip install \(.*\) -r .*$/\1/' | sort -u)"
DRAP_J="$(sed -n 's/^vpy -I -m pip install \(.*\) -r .*$/\1/p' "$TMP/i3.journal" | sort -u)"
F6="$(grep '^vpy -I -m pip install .*pytest\|^vpy -I -m pip install .*ci-yml' "$TMP/i3.journal" | sed -n '1s/^.* -r //p')"
n_ci="$(printf '%s\n' "$DRAP_CI" | grep -c .)"
if [ "$n_ci" -eq 1 ] && [ "$DRAP_J" = "$DRAP_CI" ] && [ -n "$F6" ] && grep -qF "pytest==9.1.1 --hash=sha256:$H1" "$F6"; then
  ok "I6 : pip-hash — drapeaux « $DRAP_CI » == ci.yml réel ; $F6 porte pytest==9.1.1 haché"
else
  ko "I6 : pip-hash — drapeaux du journal « $DRAP_J » / ci.yml « $DRAP_CI » ($n_ci formes) ; fichier « $F6 »"
  montre "$TMP/i3.journal"
fi

# ---------------------------------------------------------------------------
# I7 — darwin/arm64 face au seul asset linux_x64 : dit, rien téléchargé
# ---------------------------------------------------------------------------
lance i7 darwin arm64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p7"
if grep -q "gitleaks 8.30.1 : pas d'artefact épinglé pour darwin/arm64" "$TMP/i7.out" \
  && ! grep -q 'téléchargement :' "$TMP/i7.out" && [ ! -e "$TMP/p7/bin/gitleaks" ] && [ "$RC" -eq 0 ]; then
  ok "I7 : darwin/arm64 — pas d'artefact épinglé, rien téléchargé, rc 0"
else
  ko "I7 : filtre de plateforme (rc=$RC)"
  montre "$TMP/i7.out"
fi

# ---------------------------------------------------------------------------
# I8 — épingle introuvable : rc 1, dit, jamais un pip sans hash
# ---------------------------------------------------------------------------
racine "$TMP/r_sans" "file://$TMP/a_bon/$ASSET" "$SHA_BON" 0
lance i8 linux x64 --appliquer --ci "$TMP/r_sans/.github/workflows/ci.yml" --prefix "$TMP/p8"
if [ "$RC" -eq 1 ] && grep -q 'pytest 9.1.1 : épinglage introuvable' "$TMP/i8.out" \
  && ! grep -q 'pytest==' "$TMP/i8.journal" 2>/dev/null && [ ! -e "$TMP/p8/recus/pytest" ]; then
  ok "I8 : épingle absente des sources — « épinglage introuvable », rc 1, aucun pip pour elle"
else
  ko "I8 : épingle introuvable (rc=$RC)"
  montre "$TMP/i8.out"
  [ -f "$TMP/i8.journal" ] && montre "$TMP/i8.journal"
fi
# I8bis — le job de l'épingle absent du workflow : introuvable aussi, rc 1, même en --plan.
mkdir -p "$TMP/r_vide/.github/workflows"
printf '%s\n' 'name: vide' > "$TMP/r_vide/.github/workflows/ci.yml"
lance i8b linux x64 --ci "$TMP/r_vide/.github/workflows/ci.yml" --prefix "$TMP/p8b"
if [ "$RC" -eq 1 ] && grep -q 'pytest 9.1.1 : épinglage introuvable (job tests' "$TMP/i8b.out" && [ ! -e "$TMP/p8b" ]; then
  ok "I8bis : job de l'épingle absent du workflow — « épinglage introuvable », rc 1, rien écrit"
else
  ko "I8bis : job absent (rc=$RC)"
  montre "$TMP/i8b.out"
fi

# ---------------------------------------------------------------------------
# I9 — aucun outil de l'inventaire RÉEL nommé dans le code ; aucune forme sondée
# ---------------------------------------------------------------------------
LECTEUR='awk'
grep -vE '^[[:space:]]*#' "$SUT" > "$TMP/code9"
jetons="$(awk -F'\t' '/^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["nature"] == "outil" { n = split($c["tool"], a, "|"); for (i = 1; i <= n; i++) print a[i] }' "$INV_REEL" | sort -u)"
nj="$(printf '%s\n' "$jetons" | grep -c .)"
cites=""
while IFS= read -r j; do
  [ "$j" = "$LECTEUR" ] && continue
  if [ "$(grep -c -w -F -- "$j" "$TMP/code9")" -ne 0 ]; then
    cites="$cites $j"
  fi
done <<< "$jetons"
nlect="$(grep -o -w -F -- "$LECTEUR" "$TMP/code9" | grep -c .)"
nlect_cmd="$(grep -o -E '(^|[|(]|[$][(])[[:space:]]*'"$LECTEUR"'[[:space:]]+-' "$TMP/code9" | grep -c .)"
formes="$(grep -n -E '(^|[^A-Za-z0-9_])command[[:space:]]+-v|(^|[^A-Za-z0-9_])have[[:space:]]*[(]' "$TMP/code9")"
if [ "$nj" -ge 30 ] && [ -z "$cites" ] && [ "$nlect" -ge 1 ] && [ "$nlect" -eq "$nlect_cmd" ] && [ -z "$formes" ]; then
  ok "I9 : $nj jetons de l'inventaire, aucun dans le code ($LECTEUR : $nlect occurrences, toutes des commandes) ; aucune forme sondée"
else
  ko "I9 : jetons cités :${cites:- aucun} ; $LECTEUR=$nlect dont $nlect_cmd commandes ; formes : ${formes:-aucune}"
fi

# ---------------------------------------------------------------------------
# I10 — Windows : rc 2 ; deux sources => deux venvs
# ---------------------------------------------------------------------------
lance i10 windows x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p10"
rc10=$RC
lance i10b windows x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p10"
if [ "$rc10" -eq 2 ] && [ "$RC" -eq 2 ] && [ ! -e "$TMP/p10" ] && grep -q 'Windows' "$TMP/i10.out"; then
  ok "I10 : Windows — rc 2 en --plan comme en --appliquer, rien écrit"
else
  ko "I10 : Windows (rc plan=$rc10, appliquer=$RC)"
  montre "$TMP/i10.out"
fi
venvs="$(sed -n 's/^venv //p' "$TMP/i3.journal")"
nv="$(printf '%s\n' "$venvs" | grep -c .)"
if [ "$nv" -eq 2 ] && printf '%s\n' "$venvs" | grep -q '/venvs/ci-yml$' && printf '%s\n' "$venvs" | grep -q '/venvs/gardes$'; then
  ok "I10 : deux sources d'exigences — deux venvs distincts (ci-yml, gardes), chacun créé une seule fois"
else
  ko "I10 : venvs créés ($nv) : $venvs"
  montre "$TMP/i3.journal"
fi

# ---------------------------------------------------------------------------
# I11 — pip-hash hors de l'architecture ou de la version Python du job : NON, raison nommée
# ---------------------------------------------------------------------------
lance i11 linux arm64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p11"
if [ "$RC" -eq 0 ] && grep -q 'semgrep 1.175.0 : non installable ici — fermeture pip-hash résolue par le job tests pour : linux/x64 darwin/arm64, pas pour linux/arm64' "$TMP/i11.out" \
  && ! grep -q 'semgrep 1.175.0 : à installer' "$TMP/i11.out" && grep -q 'non installés=.*semgrep' "$TMP/i11.out" && [ ! -e "$TMP/p11" ]; then
  ok "I11 : linux/arm64 face à un job ubuntu x64 — semgrep « non installable ici », raison nommée, jamais « à installer »"
else
  ko "I11 : architecture du job (rc=$RC)"
  montre "$TMP/i11.out"
fi
racine "$TMP/r_py" "file://$TMP/a_bon/$ASSET" "$SHA_BON" 1 "2.7"
lance i11b linux x64 --ci "$TMP/r_py/.github/workflows/ci.yml" --prefix "$TMP/p11b"
if [ "$RC" -eq 0 ] && grep -q "semgrep 1.175.0 : non installable ici — fermeture pip-hash résolue par le job tests pour CPython 2.7, interpréteur $PYV_REEL" "$TMP/i11b.out" \
  && ! grep -q 'semgrep 1.175.0 : à installer' "$TMP/i11b.out"; then
  ok "I11 : job épinglé pour CPython 2.7, interpréteur $PYV_REEL — semgrep « non installable ici », raison nommée"
else
  ko "I11 : version Python du job (rc=$RC)"
  montre "$TMP/i11b.out"
fi

# ---------------------------------------------------------------------------
# I12 — venv sans point d'entrée bin/semgrep : ÉCHEC nommé, rc 1, aucun reçu
# ---------------------------------------------------------------------------
export IT_SANS_SEMGREP=1
lance i12 linux x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p12"
unset IT_SANS_SEMGREP
if [ "$RC" -eq 1 ] && grep -q "semgrep 1.175.0 : ÉCHEC — point d'entrée .*/venvs/gardes/bin/semgrep absent" "$TMP/i12.out" \
  && [ ! -e "$TMP/p12/recus/semgrep" ] && grep -q 'exit 1$' "$TMP/i12.out"; then
  ok "I12 : venv sans point d'entrée semgrep — ÉCHEC nommé, rc 1, aucun reçu"
else
  ko "I12 : doctor qui contredit l'installation (rc=$RC)"
  montre "$TMP/i12.out"
fi

# ---------------------------------------------------------------------------
# I13 — préfixe hors de HOME : refusé (rc 2) sans --hors-home ; `..` refusé
# ---------------------------------------------------------------------------
lance i13 linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix /usr
rc13=$RC
lance i13b linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/../usr"
rc13b=$RC
lance i13d linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/a:b"
rc13d=$RC
lance i13c linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix /usr --hors-home
if [ "$rc13" -eq 2 ] && grep -q 'prefix hors de HOME' "$TMP/i13.out" && grep -q -- '--hors-home pour l admettre' "$TMP/i13.out" \
  && [ "$rc13b" -eq 2 ] && grep -q 'sans . ni ..' "$TMP/i13b.out" \
  && [ "$rc13d" -eq 2 ] && grep -q 'sans deux-points' "$TMP/i13d.out" \
  && [ "$RC" -eq 0 ] && grep -q '^install-tools: mode plan .* préfixe /usr ' "$TMP/i13c.out"; then
  ok "I13 : --prefix /usr — rc 2, refus nommé ; « .. » et « : » refusés ; --hors-home l'admet (--plan, rc 0)"
else
  ko "I13 : préfixe hors de HOME (rc /usr=$rc13, ..=$rc13b, :=$rc13d, --hors-home=$RC)"
  montre "$TMP/i13d.out"
  montre "$TMP/i13.out"
  montre "$TMP/i13b.out"
  montre "$TMP/i13c.out"
fi

# ---------------------------------------------------------------------------
# I14 — la ligne `export PATH=…` est citée pour le shell : espace et apostrophe
# ---------------------------------------------------------------------------
P14="$TMP/a b/l'outil"
lance i14 linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$P14"
sed -n 's/^  export PATH=/export PATH=/p' "$TMP/i14.out" > "$TMP/i14.sh"
vu14="$(env -i PATH=/sentinelle "$BASH" -c '. "$1" && printf "%s\n" "$PATH"' _ "$TMP/i14.sh" 2>&1)"
if [ "$RC" -eq 0 ] && [ "$(grep -c . "$TMP/i14.sh")" -eq 1 ] && [ "${vu14%%:*}" = "$P14/bin" ] \
  && [ "${vu14##*:}" = "/sentinelle" ] && printf '%s\n' "$vu14" | grep -qF ":$P14/venvs/ci-yml/bin:"; then
  ok "I14 : préfixe à espace et apostrophe — la ligne PATH imprimée, sourcée, rend <préfixe>/bin en tête et le PATH d'origine en queue"
else
  ko "I14 : ligne PATH (rc=$RC) — sourcée : « $vu14 »"
  montre "$TMP/i14.out"
fi

# ---------------------------------------------------------------------------
# I15 — doctor qui ne dit PRESENT aucun outil posé (classe X) : rc 1, preuve positive
# ---------------------------------------------------------------------------
lance i15 linux x64 --appliquer --inventory "$TMP/inv_x.tsv" --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p15"
if [ "$RC" -eq 1 ] && grep -q 'semgrep 1.175.0 : installé' "$TMP/i15.out" \
  && grep -q 'pas PRESENT sous ce PATH :.*semgrep' "$TMP/i15.out"; then
  ok "I15 : inventaire à classe X — le doctor ne dit pas semgrep PRESENT, l'installeur rend rc 1 et le nomme"
else
  ko "I15 : verdict du doctor lu par l'absence de lignes ABSENT (rc=$RC)"
  montre "$TMP/i15.out"
fi

# ---------------------------------------------------------------------------
# I16 — le PATH imprimé ne masque pas le pytest de l'utilisateur
# ---------------------------------------------------------------------------
# a) semgrep (CLI, venv gardes sans pytest) AVANT pytest : seul le venv de pytest au PATH.
lance i16 linux x64 --appliquer --inventory "$TMP/inv_f1.tsv" --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p16"
if [ "$RC" -eq 0 ] && ! grep -q 'venvs/gardes/bin' "$TMP/i16.out" && [ -L "$TMP/p16/bin/semgrep" ] \
  && ! grep -q 'pas PRESENT\|masqué' "$TMP/i16.out"; then
  ok "I16 : venv CLI (semgrep, sans pytest) avant pytest — hors PATH, lié sous bin/, rc 0"
else
  ko "I16 : venv d'outil CLI mis au PATH (rc=$RC)"
  montre "$TMP/i16.out"
fi
# b) un outil MODULE dans un venv sans pytest, pytest de l'utilisateur présent avant : masqué, rc 1.
lance i16b linux x64 --appliquer --inventory "$TMP/inv_masque.tsv" --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p16b"
if [ "$RC" -eq 1 ] && grep -q 'outilmod 1.0.0 : installé' "$TMP/i16b.out" \
  && grep -q 'PRESENT avant, plus PRESENT sous ce PATH (masqué) : pytest — exit 1' "$TMP/i16b.out"; then
  ok "I16 : venv module sans pytest devant le pytest de l'utilisateur — « masqué : pytest », rc 1"
else
  ko "I16 : filet avant/après du doctor (rc=$RC)"
  montre "$TMP/i16b.out"
fi

# ---------------------------------------------------------------------------
# I17 — reçu juste, version du venv dérivée : « à installer » (le reçu seul ne suffit pas)
# ---------------------------------------------------------------------------
sed 's/^semgrep==1.175.0 /semgrep==1.174.0 /' "$TMP/p3/venvs/gardes/installe.txt" > "$TMP/i17.txt"
cp "$TMP/i17.txt" "$TMP/p3/venvs/gardes/installe.txt"
lance i17 linux x64 --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p3"
if [ "$RC" -eq 0 ] && grep -q 'semgrep 1.175.0 : à installer' "$TMP/i17.out" \
  && grep -q 'pytest 9.1.1 : déjà installé' "$TMP/i17.out" && grep -q '^semgrep==1.174.0 ' "$TMP/p3/venvs/gardes/installe.txt"; then
  ok "I17 : venv qui porte semgrep 1.174.0 sous un reçu 1.175.0 — « à installer », pytest intact"
else
  ko "I17 : version installée non relue (rc=$RC)"
  montre "$TMP/i17.out"
fi

# ---------------------------------------------------------------------------
# I18 — verrou déjà posé : rc 1, rien fait, verrou laissé
# ---------------------------------------------------------------------------
mkdir -p "$TMP/p18/.verrou"
lance i18 linux x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p18"
if [ "$RC" -eq 1 ] && grep -q 'verrou .*deja pose' "$TMP/i18.out" && [ -d "$TMP/p18/.verrou" ] \
  && [ ! -e "$TMP/p18/venvs" ] && [ ! -e "$TMP/p18/bin" ] && [ ! -e "$TMP/i18.journal" ]; then
  ok "I18 : verrou déjà posé — rc 1, rien installé, verrou laissé en place"
else
  ko "I18 : verrou (rc=$RC)"
  montre "$TMP/i18.out"
fi

# ---------------------------------------------------------------------------
# I19 — venv qui est un lien : refus avant tout venv --clear, la cible intacte
# ---------------------------------------------------------------------------
mkdir -p "$TMP/p19/venvs" "$TMP/cible19"
printf '%s\n' garde > "$TMP/cible19/garde"
ln -s "$TMP/cible19" "$TMP/p19/venvs/ci-yml"
lance i19 linux x64 --appliquer --ci "$TMP/r_bon/.github/workflows/ci.yml" --prefix "$TMP/p19"
if [ "$RC" -eq 1 ] && grep -q 'pytest 9.1.1 : ÉCHEC — .*est un lien' "$TMP/i19.out" && [ -f "$TMP/cible19/garde" ] \
  && ! grep -q 'venvs/ci-yml$' "$TMP/i19.journal" 2>/dev/null; then
  ok "I19 : venv lien — refus nommé avant --clear, rc 1, la cible du lien intacte"
else
  ko "I19 : venv lien (rc=$RC)"
  montre "$TMP/i19.out"
fi

# ---------------------------------------------------------------------------
# I20 — inventaire RÉEL : un outil à trois pins non installables n'est dit qu'une fois
# ---------------------------------------------------------------------------
lance i20 linux x64 --inventory "$INV_REEL" --ci "$CI_REEL" --prefix "$TMP/p20"
n20="$(sed -n 's/^install-tools: plan : .* non installés=\(.*\) échecs=.*$/\1/p' "$TMP/i20.out" | tr ' ' '\n' | grep -c -x -F 'python3|python|py')"
if [ "$n20" -eq 1 ]; then
  ok "I20 : inventaire réel — python3|python|py dit une seule fois aux non installés"
else
  ko "I20 : python3|python|py dit $n20 fois"
  montre "$TMP/i20.out"
fi

echo
echo "install-tools.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
