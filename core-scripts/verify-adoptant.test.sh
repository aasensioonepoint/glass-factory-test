#!/usr/bin/env bash
# Banc de la porte de push de l'ADOPTANT, côté core-scripts/verify.sh
# (T-00001183, décision pilote S-00004119 ; plan rév. 7, étape 7).
# Run: bash core-scripts/verify-adoptant.test.sh
#
# Directive lue par core-scripts/run-bash-tests.sh (T-00000427) :
# requires: git python3
#
# CE QUE CE BANC PROUVE. En mode adoptant, `verify.sh --at <sha>` PEUPLE les
# sous-modules du clone gelé DEPUIS L'ARBRE VIVANT, au sha du gitlink, jamais
# par le réseau (`peupler_sous_modules`, `peupler_et_verifier`), puis délègue à
# `.agents/bin/porte_adoptant.py`, dont le canal de retour (`PORTE_RESULT`) fait
# le tampon `porte=adoptant`. Sur le kit, rien ne bouge : trois `step`, cinq
# clés, aucun appel `git submodule`.
#
# FIXTURE SYNTHÉTIQUE DE LA FORME D'EC-CRM-MULTI (le banc voyage, il ne lit
# aucun projet réel) : un superprojet `name = "cadre-kit"`, `dependencies = []`,
# `module_discovery.py` copié, SANS `.agents/IS_THE_KIT` ; deux sous-modules m1
# et m2, m2 portant m3 imbriqué (profondeur 2) ; tout `.gitmodules` sur
# `https://invalid.invalid/…`, donc injoignable. Deux formes, le motif de
# `verify.test.sh` : (bouchon) l'interne de `--at` RAPPORTE l'arbre peuplé
# (`discover`, `submodule status --recursive`) et rend un PORTE_RESULT vert ;
# (e2e) l'interne est le vrai `verify.sh` + le vrai `porte_adoptant.py`, et le
# banc n'asserte JAMAIS sur le seul rc : il lit `PORTE_RESULT` et le tampon.
# La fixture ne porte pas `.agents/security/semgrep.yml`, si bien que chaque
# run e2e pose `CADRE_GARDES_DEGRADEES` (raison accentuée) : la dérogation
# couvre toujours un refus réel, et sa clé est donc toujours écrite.
#
# HERMÉTIQUE. Tout `GIT_*` hérité est purgé ; `GIT_CONFIG_GLOBAL` est un
# fichier JETABLE en chemin ABSOLU (un chemin relatif est ignoré en silence
# après `git -C`, réserve S-00004193) et `GIT_CONFIG_NOSYSTEM=1` ; HOME et
# XDG_CONFIG_HOME sont jetables ; `LC_ALL=C`. Sans cela le verdict dépendrait
# du poste (un `submodule.recurse=true` global, réglage courant, rougit la
# forme rév. 5 du peuplement — mesuré). Les bras S3c, S8 posent LEUR fichier,
# à l'appel. `GIT_ALLOW_PROTOCOL` n'est JAMAIS exporté ici : il ne vit qu'en
# préfixe des commandes de fixture (`gfile`), sinon S3b ne mesurerait rien.
#
# CHAQUE BRAS EST VERT AU TIP ET ROUGE SOUS SON MUTANT. Un bras est une
# fonction qui rend 0 ou 1 ; `vert` exige 0 sur le vrai script, `rouge` exige
# 1 sur une COPIE mutée (`core-scripts/verify-mutant.sh` de la fixture — la
# copie doit vivre là : verify.sh dérive son arbre de BASH_SOURCE/..), et la
# copie doit DIFFÉRER de l'original (`cmp`), sinon « mutation sans effet ».
# Une mutation remplace une sous-chaîne EXACTE dont le compte est asserté :
# si verify.sh change, le mutant refuse de naître au lieu de mordre à vide.
#
# CLONE NEUF OU RÉEMPLOYÉ, PAR BRAS (plan, C4) : un clone déjà peuplé rend
# VERTS les mutants « peuplement retiré », « URL non réécrite », « récursion
# retirée » (mesuré). Clone NEUF : S1, S2, S3, S3b, S3c, S6, K5 (S5 : les
# deux). Réemploi PAR CONSTRUCTION : S4, S5b, S7, S8, S9 — un `--at`
# préparatoire peuple le clone, puis le gitlink avance, un bump NEUF par
# passage, et la précondition (l'objet ABSENT du clone) est assertée avant.
# Le tip passe d'abord, le mutant ensuite : un mutant rouge peut laisser le
# clone dans un état cassé (un rebase interrompu, mesuré par le planner).
#
# BORNES, NOMMÉES. Mesuré sur git 2.55.0 / macOS (bash 5 et /bin/bash 3.2).
# Linux et les gits plus anciens : non mesurés ici (angle mort 12). Git Bash /
# Windows : non mesuré — ce banc n'est pas déclaré vert là tant qu'il n'y a
# pas tourné (angle mort 13). S3b fait une VRAIE résolution DNS de
# `invalid.invalid` (domaine réservé, jamais résolu) : c'est la preuve que
# l'env est la ceinture qui ferme https.
set -uo pipefail

# --- environnement CONSTRUIT, jamais hérité ----------------------------------
# Purge PAR PRÉFIXE (patron de check-stale-justification.test.sh) : une liste
# de noms se périme. Elle précède tout `git`.
for _v in $(compgen -e); do
  case "$_v" in
    GIT_*) unset "$_v" ;;
  esac
done
unset CADRE_GARDES_DEGRADEES CADRE_SANS_MODULE CADRE_SANS_TEST CADRE_SEMGREP_BASE \
  PORTE_ADOPTANT_EN_COURS VERIFY_WORKTREE_DIR VERIFY_STUB_OUT BANC_DEROGATION BANC_DOCKER_TRACE \
  BANC_SEMGREP_TRACE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/.." && pwd)"
REAL_VERIFY="$HERE/verify.sh"
REAL_HOOK="$KIT/.githooks/pre-push"
REAL_PORTE="$KIT/.agents/bin/porte_adoptant.py"
REAL_DISCOVERY="$KIT/.agents/security/module_discovery.py"
for _f in "$REAL_VERIFY" "$REAL_HOOK" "$REAL_PORTE" "$REAL_DISCOVERY"; do
  [ -f "$_f" ] || { echo "FAIL: $_f introuvable — le banc n'a pas de sujet" >&2; exit 1; }
done

fail() { echo "FAIL: $*" >&2; exit 1; }

PY=python3
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "python3 >= 3.11 requis (porte_adoptant.py lit tomllib) — la porte e2e rougirait pour une AUTRE raison"
"$PY" -c 'import pytest' 2>/dev/null \
  || fail "pytest absent de python3 — la porte e2e rougirait pour une AUTRE raison"

TMP="$(mktemp -d)" || fail "mktemp"
TMP="$(cd "$TMP" && pwd -P)" || fail "mktemp illisible"
[ -n "$TMP" ] || fail "mktemp vide"
# Garde BASHPID : un enfant forké peut jouer ce trap hérité (mesuré sous Git
# Bash, verify.test.sh) ; sous bash 3.2, sans BASHPID, la garde se dégrade en
# inerte, jamais en fausse.
TMP_OWNER="${BASHPID:-$$}"
nettoyer() {
  if [ "${BASHPID:-$$}" = "$TMP_OWNER" ]; then rm -rf "$TMP"; fi
  return 0
}
trap nettoyer EXIT

export HOME="$TMP/_home" XDG_CONFIG_HOME="$TMP/_xdg"
mkdir -p "$HOME" "$XDG_CONFIG_HOME" || fail "HOME jetable"
G_VIDE="$TMP/gitconfig-vide"
: > "$G_VIDE"
export GIT_CONFIG_GLOBAL="$G_VIDE" GIT_CONFIG_NOSYSTEM=1
export LC_ALL=C

# --- outillage du banc -------------------------------------------------------
NBRAS=0
NMUT=0
RAISON_ECHEC=""
SORTIE=""
RC=0
STUB_OUT="$TMP/bouchon-sortie.txt"

# Identité des fixtures par `-c`, jamais par la config du poste.
gc() { git -c user.name=banc -c user.email=banc@banc.invalid -c init.defaultBranch=main "$@"; }
# Un git de FIXTURE autorisé à cloner un chemin local. L'env n'est posé QU'ICI,
# par `env` (jamais en préfixe d'une fonction, dont la portée varie selon le
# mode de bash).
gfile() {
  env GIT_ALLOW_PROTOCOL=file git -c user.name=banc -c user.email=banc@banc.invalid \
    -c protocol.file.allow=always "$@"
}
faire() { "$@" || fail "fixture : $*"; }
raison() { RAISON_ECHEC="$*"; return 1; }
contient() { grep -qF -- "$1" <<< "$SORTIE"; }
champ() { sed -n "s/^$2=//p" "$1" 2>/dev/null; }

vert() {  # vert <id> <bras...> — le bras doit TENIR sur le vrai script
  local id="$1"
  shift
  RAISON_ECHEC=""
  if "$@"; then
    NBRAS=$((NBRAS + 1))
    echo "ok: $id"
  else
    printf '%s\n' "$SORTIE" | sed 's/^/    | /' >&2
    fail "$id : $RAISON_ECHEC"
  fi
}
rouge() {  # rouge <id> <bras...> — le bras doit TOMBER sous le mutant
  local id="$1"
  shift
  RAISON_ECHEC=""
  if "$@"; then
    printf '%s\n' "$SORTIE" | sed 's/^/    | /' >&2
    fail "$id : MUTANT SURVIVANT — le bras reste vert"
  fi
  NMUT=$((NMUT + 1))
  echo "ok: $id — mutant tué ($RAISON_ECHEC)"
}

# lancer <script> <wt> <GIT_CONFIG_GLOBAL> [VAR=valeur]... -- <arguments>...
# Le seul site de lancement de `verify.sh --at`. `VERIFY_INNER=0` y est posé :
# sous la porte, ce banc hérite du `VERIFY_INNER=1` de l'exécution déléguée, et
# chaque run lancé ici est un run INDÉPENDANT (verify.test.sh, en-tête).
lancer() {
  local script="$1" wt="$2" a
  local envs=("GIT_CONFIG_GLOBAL=$3")
  shift 3
  while [ "$#" -gt 0 ]; do
    a="$1"
    shift
    [ "$a" = "--" ] && break
    envs+=("$a")
  done
  rm -f "$STUB_OUT"
  SORTIE="$(env "${envs[@]}" VERIFY_INNER=0 VERIFY_WORKTREE_DIR="$wt" VERIFY_STUB_OUT="$STUB_OUT" \
    bash "$script" "$@" 2>&1)"
  RC=$?
}

# Les mutations : une sous-chaîne EXACTE, un compte asserté, par triplets.
MUTER="$TMP/muter.py"
cat > "$MUTER" <<'PY'
import sys

source, mutant, paires = sys.argv[1], sys.argv[2], sys.argv[3:]
if not paires or len(paires) % 3:
    sys.exit("usage : muter.py <source> <mutant> (<ancien> <nouveau> <compte>)...")
with open(source, encoding="utf-8", newline="") as fh:
    texte = fh.read()
for i in range(0, len(paires), 3):
    ancien, nouveau, attendu = paires[i], paires[i + 1], int(paires[i + 2])
    vu = texte.count(ancien)
    if vu != attendu:
        sys.exit(f"motif vu {vu} fois, attendu {attendu} : {ancien!r}")
    texte = texte.replace(ancien, nouveau)
with open(mutant, "w", encoding="utf-8", newline="") as fh:
    fh.write(texte)
PY
muter() {  # muter <source> <mutant> (<ancien> <nouveau> <compte>)...
  local src="$1" dst="$2"
  "$PY" "$MUTER" "$@" || fail "mutant $dst : motif introuvable — la source a changé, le mutant ne mordrait plus"
  if cmp -s "$src" "$dst"; then fail "mutation sans effet : $dst est identique à $src"; fi
  chmod +x "$dst"
}

# --- fixture : sources des modules ------------------------------------------
module_py() {  # module_py <dossier> <nom> — un module python minimal, un test vert
  mkdir -p "$1" || return 1
  printf '[project]\nname = "%s"\nversion = "0.0.0"\n' "$2" > "$1/pyproject.toml"
  printf 'def test_%s():\n    assert True\n' "$2" > "$1/test_$2.py"
}
SRC="$TMP/src"
faire module_py "$SRC/m3" m3
faire gc init -q "$SRC/m3"
faire gc -C "$SRC/m3" add -A
faire gc -C "$SRC/m3" commit -qm "m3 : module"
A3="$(git -C "$SRC/m3" rev-parse HEAD)"

# m1 : X0 (le module), X1 (ajoute div.txt « a ») — S9 bâtira des fils de X0.
faire module_py "$SRC/m1" m1
faire gc init -q "$SRC/m1"
faire gc -C "$SRC/m1" add -A
faire gc -C "$SRC/m1" commit -qm "m1 : module"
X0="$(git -C "$SRC/m1" rev-parse HEAD)"
printf 'a\n' > "$SRC/m1/div.txt"
faire gc -C "$SRC/m1" add -A
faire gc -C "$SRC/m1" commit -qm "m1 : div a"
X1="$(git -C "$SRC/m1" rev-parse HEAD)"

faire module_py "$SRC/m2" m2
faire gc init -q "$SRC/m2"
faire gc -C "$SRC/m2" add -A
faire gfile -C "$SRC/m2" submodule add -q "$SRC/m3" m3
faire gc -C "$SRC/m2" config -f .gitmodules submodule.m3.url https://invalid.invalid/m3.git
faire gc -C "$SRC/m2" add .gitmodules
faire gc -C "$SRC/m2" commit -qm "m2 : module, m3 imbriqué"
A2="$(git -C "$SRC/m2" rev-parse HEAD)"

# --- fixture : l'interne bouchon ---------------------------------------------
BOUCHON="$TMP/interne-bouchon.sh"
cat > "$BOUCHON" <<'BOUCHON'
#!/usr/bin/env bash
# Interne BOUCHON de verify-adoptant.test.sh. Il ne juge rien : il RAPPORTE
# l'arbre que l'extérieur lui a préparé (DISCOVER=, STATUS=) et rend, pour CE
# sha, le PORTE_RESULT vert que l'extérieur exige en mode adoptant —
# BANC_DEROGATION, si posée, y entre telle quelle (octets de contrôle compris).
set -uo pipefail
BOUCHON_TOP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOUCHON_SHA="$(git -C "$BOUCHON_TOP" rev-parse HEAD)"
{
  echo "HEAD=$BOUCHON_SHA"
  echo "ARGS=$*"
  git -C "$BOUCHON_TOP" submodule status --recursive | sed 's/^/STATUS=/'
  python3 - "$BOUCHON_TOP" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "banc_discovery", sys.argv[1] + "/.agents/security/module_discovery.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for rel in sorted(p.as_posix() for p in module.discover(sys.argv[1])):
    print("DISCOVER=" + rel)
PY
} > "${VERIFY_STUB_OUT:-/dev/null}"
mkdir -p "$BOUCHON_TOP/.agents/state/local"
{
  echo "sha=$BOUCHON_SHA"
  echo "verdict=OK"
  echo "modules="
  if [ -n "${BANC_DEROGATION:-}" ]; then
    printf 'derogation_gardes=%s\n' "$BANC_DEROGATION"
  fi
} > "$BOUCHON_TOP/.agents/state/local/PORTE_RESULT"
echo "BOUCHON RAN"
BOUCHON

# --- fixture : le superprojet VIVANT (adoptant) ------------------------------
LIVE="$TMP/live"
MUTANT="$LIVE/core-scripts/verify-mutant.sh"
STAMP="$LIVE/.agents/state/local/VERIFY_STAMP"
faire mkdir -p "$LIVE/.agents/security" "$LIVE/.agents/bin" "$LIVE/.githooks" "$LIVE/core-scripts"
faire gc init -q "$LIVE"
faire cp "$REAL_DISCOVERY" "$LIVE/.agents/security/module_discovery.py"
faire cp "$REAL_PORTE" "$LIVE/.agents/bin/porte_adoptant.py"
faire cp "$REAL_HOOK" "$LIVE/.githooks/pre-push"
faire cp "$BOUCHON" "$LIVE/core-scripts/verify.sh"
printf '[project]\nname = "cadre-kit"\nversion = "0.0.0"\ndependencies = []\n' > "$LIVE/pyproject.toml"
printf '/.agents/state/local/\n/core-scripts/verify-mutant.sh\n/.hooks-mutant/\n' > "$LIVE/.gitignore"
faire gc -C "$LIVE" add -A
# 100755 DANS L'INDEX : l'intégrité courte de la porte le lit là (porte_adoptant.py).
faire gc -C "$LIVE" update-index --chmod=+x .githooks/pre-push
faire gfile -C "$LIVE" submodule add -q "$SRC/m1" m1
faire gfile -C "$LIVE" submodule add -q "$SRC/m2" m2
faire gc -C "$LIVE" config -f .gitmodules submodule.m1.url https://invalid.invalid/m1.git
faire gc -C "$LIVE" config -f .gitmodules submodule.m2.url https://invalid.invalid/m2.git
faire gc -C "$LIVE" add .gitmodules
faire gc -C "$LIVE" commit -qm "fixture : superprojet adoptant, interne bouchon"
C_STUB="$(git -C "$LIVE" rev-parse HEAD)"
# m3, imbriqué, initialisé dans le vivant : l'URL locale AVANT l'update, sinon
# `init` recopierait l'URL injoignable de `.gitmodules`.
faire gc -C "$LIVE/m2" submodule init -q
faire gc -C "$LIVE/m2" config submodule.m3.url "$SRC/m3"
faire gfile -C "$LIVE/m2" submodule update -q
# Le commit suivant porte le VRAI script : l'extérieur de chaque `--at` est la
# copie de l'arbre de travail, donc le code livré.
faire cp "$REAL_VERIFY" "$LIVE/core-scripts/verify.sh"
faire gc -C "$LIVE" add core-scripts/verify.sh
faire gc -C "$LIVE" commit -qm "fixture : le vrai verify.sh"
C_REAL="$(git -C "$LIVE" rev-parse HEAD)"

# vivant_sain — le vivant porte m1, m2, m2/m3, tous au gitlink. Asserté après
# chaque geste qui le touche (S5, S5b) : un vivant mal restauré ferait mentir
# tous les bras suivants.
vivant_sain() {
  local etat
  etat="$(git -C "$LIVE" submodule status --recursive)" || fail "vivant : submodule status illisible"
  [ "$(grep -c '' <<< "$etat")" -eq 3 ] || fail "vivant : trois modules attendus : $etat"
  if grep -q '^[^ ]' <<< "$etat"; then fail "vivant : un module n'est pas au gitlink : $etat"; fi
}
vivant_sain

# --- les vérifications partagées --------------------------------------------
# bouchon_a_vu <sha m1> <sha m2> <sha m3> — l'interne a tourné sur un arbre
# PEUPLÉ : discover rend la racine et les trois modules, et `submodule status
# --recursive` n'a que des lignes « espace », chacune au sha attendu.
bouchon_a_vu() {
  local d
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ -f "$STUB_OUT" ] || { raison "l'interne n'a pas tourné"; return 1; }
  d="$(sed -n 's/^DISCOVER=//p' "$STUB_OUT" | tr '\n' ' ')"
  [ "$d" = ". m1 m2 m2/m3 " ] || { raison "discover rend « $d », attendu « . m1 m2 m2/m3 »"; return 1; }
  [ "$(grep -c '^STATUS=' "$STUB_OUT")" -eq 3 ] || { raison "trois lignes de statut attendues"; return 1; }
  if grep -q '^STATUS=[^ ]' "$STUB_OUT"; then
    raison "un module hors gitlink : $(grep '^STATUS=[^ ]' "$STUB_OUT" | tr '\n' ' ')"
    return 1
  fi
  grep -qE "^STATUS= $1 m1( |\$)" "$STUB_OUT" || { raison "m1 n'est pas à $1"; return 1; }
  grep -qE "^STATUS= $2 m2( |\$)" "$STUB_OUT" || { raison "m2 n'est pas à $2"; return 1; }
  grep -qE "^STATUS= $3 m2/m3( |\$)" "$STUB_OUT" || { raison "m2/m3 n'est pas à $3"; return 1; }
}
# refus_avant_interne <ligne attendue> — rc 1, la ligne de la FONCTION, l'interne
# jamais lancé, et le tampon semé intact (le refus sort AU-DESSUS du tampon).
refus_avant_interne() {
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1"; return 1; }
  contient "$1" || { raison "la ligne « $1 » manque"; return 1; }
  [ ! -f "$STUB_OUT" ] || { raison "l'interne a tourné malgré le refus"; return 1; }
  if contient "frozen checkout @"; then raison "l'interne a été annoncé"; return 1; fi
  cmp -s "$STAMP" "$TMP/tampon-seme" || { raison "le tampon a bougé"; return 1; }
}
semer_tampon() {
  mkdir -p "$(dirname "$STAMP")" || fail "tampon"
  printf 'sha=%s\nmode=frozen\nlinux=0\nhost=banc\nat=banc\n' \
    0123456789abcdef0123456789abcdef01234567 > "$STAMP"
  cp "$STAMP" "$TMP/tampon-seme" || fail "tampon"
}
# commit_super <base> <branche|-> (<chemin> <sha>)... — un commit du superprojet
# vivant dont seuls les gitlinks bougent, bâti sans toucher HEAD, l'index ni
# l'arbre de travail ; « - » = détaché (aucune ref : le clone ne peut pas le voir).
commit_super() {
  local base="$1" branche="$2" idx="$TMP/index-super" arbre c
  shift 2
  rm -f "$idx"
  GIT_INDEX_FILE="$idx" git -C "$LIVE" read-tree "$base" || return 1
  while [ "$#" -gt 1 ]; do
    GIT_INDEX_FILE="$idx" git -C "$LIVE" update-index --cacheinfo "160000,$2,$1" || return 1
    shift 2
  done
  arbre="$(GIT_INDEX_FILE="$idx" git -C "$LIVE" write-tree)" || return 1
  c="$(gc -C "$LIVE" commit-tree "$arbre" -p "$base" -m "banc : gitlinks")" || return 1
  if [ "$branche" != "-" ]; then
    gc -C "$LIVE" branch -f "$branche" "$c" >/dev/null || return 1
  fi
  printf '%s' "$c"
}
# avancer_module <dépôt vivant> — un commit neuf sur la branche du module.
avancer_module() {
  gc -C "$1" commit -q --allow-empty -m "banc : module avancé" || return 1
  git -C "$1" rev-parse HEAD
}
# absent_du_clone <dépôt> <sha> — LA précondition des bras à réemploi.
absent_du_clone() {
  if git -C "$1" cat-file -e "$2^{commit}" 2>/dev/null; then
    fail "précondition : $2 est déjà dans $1 — le bras ne mesurerait rien"
  fi
}
# trace_detach <trace> <compte> — non-vacuité PUIS le compte exact des
# `checkout --detach` (le format GIT_TRACE de git 2.55 : un format changé
# rougit ici au lieu de compter à vide).
trace_detach() {
  local n
  [ -s "$1" ] || { raison "trace vide ($1)"; return 1; }
  n="$(grep -cE 'built-in: git (clone|checkout)' "$1")"
  [ "${n:-0}" -ge 1 ] || { raison "non-vacuité : aucune ligne clone/checkout dans la trace"; return 1; }
  n="$(grep -c 'built-in: git checkout --detach' "$1")"
  [ "${n:-0}" -eq "$2" ] || { raison "$n ligne(s) « checkout --detach », attendu $2"; return 1; }
}
preparer() {  # preparer <wt> — le `--at` préparatoire du vrai script : clone peuplé
  lancer "$REAL_VERIFY_LIVE" "$1" "$G_VIDE" -- --at "$C_STUB"
  bouchon_a_vu "$X1" "$A2" "$A3" || fail "préparation de $1 : $RAISON_ECHEC"
}
REAL_VERIFY_LIVE="$LIVE/core-scripts/verify.sh"
RAISON_ACCENT="banc sans règles semgrep — dérogation accentuée, été"
FONCTION_ECHEC="--at: git submodule update a échoué dans"

echo "=== K : le chemin du kit, inchangé"
# K3 — les trois `step` du kit, mot pour mot, en colonne 0.
for _l in 'step "python -m pytest (CI scope, shards)" bash core-scripts/run-pytest-shards.sh' \
  'step "bash core-scripts/run-bash-tests.sh" bash core-scripts/run-bash-tests.sh' \
  'step "bash .agents/security/shellcheck-scan.sh" bash .agents/security/shellcheck-scan.sh'; do
  grep -qxF -- "$_l" "$REAL_VERIFY" || fail "K3 : la ligne du kit manque, mot pour mot : $_l"
done
NBRAS=$((NBRAS + 1))
echo "ok: K3 trois step du kit mot pour mot"

# La fixture KIT : le marqueur ET module_discovery.py (les DEUX termes de la
# règle), trois jambes bouchonnées qui disent leur nom.
KITF="$TMP/kitf"
faire mkdir -p "$KITF/.agents/security" "$KITF/core-scripts" "$KITF/.githooks"
faire gc init -q "$KITF"
: > "$KITF/.agents/IS_THE_KIT"
faire cp "$REAL_DISCOVERY" "$KITF/.agents/security/module_discovery.py"
faire cp "$REAL_HOOK" "$KITF/.githooks/pre-push"
printf '#!/usr/bin/env bash\necho "JAMBE pytest"\n' > "$KITF/core-scripts/run-pytest-shards.sh"
printf '#!/usr/bin/env bash\necho "JAMBE bash"\n' > "$KITF/core-scripts/run-bash-tests.sh"
printf '#!/usr/bin/env bash\necho "JAMBE shellcheck"\n' > "$KITF/.agents/security/shellcheck-scan.sh"
# L'interne bouchon du kit n'appelle AUCUN git : K5 compte les appels
# `submodule` de toute la trace, interne compris.
printf '#!/usr/bin/env bash\necho "BOUCHON KIT"\n' > "$KITF/core-scripts/verify.sh"
printf '/.agents/state/local/\n/core-scripts/verify-mutant.sh\n/.hooks-mutant/\n' > "$KITF/.gitignore"
faire gc -C "$KITF" add -A
faire gc -C "$KITF" update-index --chmod=+x .githooks/pre-push
faire gc -C "$KITF" commit -qm "fixture kit : interne bouchon"
K_STUB="$(git -C "$KITF" rev-parse HEAD)"
faire cp "$REAL_VERIFY" "$KITF/core-scripts/verify.sh"
faire gc -C "$KITF" add -A
faire gc -C "$KITF" commit -qm "fixture kit : le vrai verify.sh"
K_REAL="$(git -C "$KITF" rev-parse HEAD)"
KSTAMP="$KITF/.agents/state/local/VERIFY_STAMP"
KMUT="$KITF/core-scripts/verify-mutant.sh"

# K2 — un arbre à IS_THE_KIT (et module_discovery) joue les trois jambes du
# kit, DANS L'ORDRE, et son tampon garde ses CINQ clés, sans `porte=`.
bras_k2() {  # <script>
  local jambes cles
  rm -f "$KSTAMP"
  SORTIE="$(env VERIFY_INNER=0 bash "$1" 2>&1)"
  RC=$?
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  contient "porte: kit" || { raison "la porte n'est pas annoncée kit"; return 1; }
  jambes="$(grep '^JAMBE ' <<< "$SORTIE" | tr '\n' ' ')"
  [ "$jambes" = "JAMBE pytest JAMBE bash JAMBE shellcheck " ] \
    || { raison "jambes « $jambes », attendu pytest, bash, shellcheck dans l'ordre"; return 1; }
  [ -f "$KSTAMP" ] || { raison "aucun tampon"; return 1; }
  cles="$(sed 's/=.*//' "$KSTAMP" | tr '\n' ' ')"
  [ "$cles" = "sha mode linux host at " ] || { raison "clés du tampon « $cles »"; return 1; }
  [ "$(champ "$KSTAMP" sha)" = "$K_REAL" ] || { raison "sha du tampon"; return 1; }
  [ "$(champ "$KSTAMP" mode)" = "live" ] || { raison "mode du tampon"; return 1; }
}
vert "K2 kit : trois jambes dans l'ordre, cinq clés" bras_k2 "$KITF/core-scripts/verify.sh"
muter "$REAL_VERIFY" "$KMUT" 'if [ ! -f "$1/.agents/IS_THE_KIT" ]' 'if [ -f "$1/.agents/IS_THE_KIT" ]' 1
rouge "K2 sous « règle inversée »" bras_k2 "$KMUT"

# K5 — no-op du kit : sans `.gitmodules`, ZÉRO appel `git submodule` dans toute
# la trace, et le run a bien atteint la branche `--at` (non-vacuité). JAMAIS le
# mot `submodule` nu : `--no-recurse-submodules` figure désormais dans la trace.
MOTIF_SUBMODULE='submodule--helper|git-submodule|git submodule'
bras_k5() {  # <script> <wt neuf>
  local t n
  t="$TMP/trace-k5-$(basename "$2")"
  [ ! -e "$2" ] || { raison "K5 exige un clone NEUF"; return 1; }
  lancer "$1" "$2" "$G_VIDE" GIT_TRACE="$t" -- --at "$K_STUB"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  contient "BOUCHON KIT" || { raison "l'interne n'a pas tourné"; return 1; }
  n="$(grep -cE 'built-in: git (clone|checkout)' "$t")"
  [ "${n:-0}" -ge 1 ] || { raison "non-vacuité : aucune ligne clone/checkout"; return 1; }
  n="$(grep -cE "$MOTIF_SUBMODULE" "$t")"
  [ "${n:-0}" -eq 0 ] || { raison "$n appel(s) git submodule sur le kit"; return 1; }
}
vert "K5 kit : aucun appel submodule sous --at" bras_k5 "$KITF/core-scripts/verify.sh" "$TMP/wt-k5"
muter "$REAL_VERIFY" "$KMUT" '  [ -d "$wt/.git/modules" ] || return 0' '  : no-op du kit retiré par le mutant' 1
rouge "K5 sous « no-op du kit retiré »" bras_k5 "$KMUT" "$TMP/wt-k5m"

# K4 — le pre-push du KIT accepte un tampon sans `porte=`.
faire git init -q --bare "$TMP/remote-kit.git"
faire gc -C "$KITF" remote add e2e "$TMP/remote-kit.git"
faire gc -C "$KITF" config core.hooksPath .githooks
bras_k4() {  # <ref distante>
  printf 'sha=%s\nmode=frozen\nlinux=0\nhost=banc\nat=banc\n' "$K_REAL" > "$KSTAMP"
  SORTIE="$(git -C "$KITF" push e2e "HEAD:refs/heads/$1" 2>&1)"
  RC=$?
  [ "$RC" -eq 0 ] || { raison "push refusé, rc $RC"; return 1; }
  # Le hook a PARLÉ : un push accepté sans hook exécuté ne prouverait rien.
  contient "container leg: NOT covered" || { raison "le hook du kit n'a pas parlé"; return 1; }
  [ "$(git -C "$TMP/remote-kit.git" rev-parse "refs/heads/$1")" = "$K_REAL" ] \
    || { raison "le push accepté n'a pas atteint le dépôt distant"; return 1; }
}
vert "K4 pre-push du kit : tampon sans porte= accepté" bras_k4 travail
faire mkdir -p "$KITF/.hooks-mutant"
muter "$REAL_HOOK" "$KITF/.hooks-mutant/pre-push" \
  'if [ ! -f "$ROOT/.agents/IS_THE_KIT" ] && [ -f "$ROOT/.agents/security/module_discovery.py" ]; then' \
  'if [ -f "$ROOT/.agents/security/module_discovery.py" ]; then' 1
faire gc -C "$KITF" config core.hooksPath .hooks-mutant
rouge "K4 sous « terme IS_THE_KIT retiré du hook »" bras_k4 travail-mutant
# Le refus vient du hook MUTÉ (il lit le kit comme un adoptant), pas d'un
# refspec ni d'un hook absent.
contient "carries no porte=adoptant" || fail "K4 : le mutant n'a pas rougi par le hook muté"
faire gc -C "$KITF" config core.hooksPath .githooks

echo "=== S1 : nominal, clone NEUF"
# S1, forme bouchon : m1, m2, m2/m3 au gitlink ; sa trace est le témoin
# POSITIF de K5 (le motif voit).
bras_s1() {  # <script> <wt neuf>
  [ ! -e "$2" ] || { raison "S1 exige un clone NEUF"; return 1; }
  lancer "$1" "$2" "$G_VIDE" GIT_TRACE="$TMP/trace-$(basename "$2")" -- --at "$C_STUB"
  bouchon_a_vu "$X1" "$A2" "$A3"
}
vert "S1 (bouchon) m1, m2, m2/m3 au gitlink" bras_s1 "$REAL_VERIFY_LIVE" "$TMP/wt-s1s"
_n="$(grep -cE "$MOTIF_SUBMODULE" "$TMP/trace-wt-s1s")"
[ "${_n:-0}" -ge 1 ] || fail "K5 témoin positif : le motif ne voit rien sur la trace de S1"
NBRAS=$((NBRAS + 1))
echo "ok: K5 témoin positif — $_n ligne(s) du motif sur la trace de S1"

# S1, forme e2e : le vrai interne et la vraie porte ; PORTE_RESULT puis le
# tampon, jamais le seul rc. La raison accentuée arrive INTACTE au tampon.
porte_e2e_verte() {  # <wt>
  local res="$1/.agents/state/local/PORTE_RESULT"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ -f "$res" ] || { raison "aucun PORTE_RESULT dans $1"; return 1; }
  [ "$(champ "$res" verdict)" = "OK" ] || { raison "verdict « $(champ "$res" verdict) »"; return 1; }
  [ "$(champ "$res" sha)" = "$C_REAL" ] || { raison "PORTE_RESULT nomme un autre sha"; return 1; }
  [ "$(champ "$res" modules)" = "m1,m2,m2/m3" ] || { raison "modules « $(champ "$res" modules) »"; return 1; }
  [ "$(champ "$res" derogation_gardes)" = "$RAISON_ACCENT" ] || { raison "dérogation du PORTE_RESULT"; return 1; }
  [ "$(champ "$STAMP" sha)" = "$C_REAL" ] || { raison "tampon : sha"; return 1; }
  [ "$(champ "$STAMP" mode)" = "frozen" ] || { raison "tampon : mode"; return 1; }
  [ "$(champ "$STAMP" linux)" = "0" ] || { raison "tampon : linux=$(champ "$STAMP" linux)"; return 1; }
  [ "$(champ "$STAMP" porte)" = "adoptant" ] || { raison "tampon : porte"; return 1; }
  [ "$(champ "$STAMP" derogation_gardes)" = "$RAISON_ACCENT" ] \
    || { raison "tampon : la raison accentuée n'est pas intacte"; return 1; }
}
bras_s1_e2e() {  # <script> <wt neuf>
  [ ! -e "$2" ] || { raison "S1 exige un clone NEUF"; return 1; }
  rm -f "$STAMP"
  lancer "$1" "$2" "$G_VIDE" CADRE_GARDES_DEGRADEES="$RAISON_ACCENT" -- --at "$C_REAL"
  porte_e2e_verte "$2"
}
vert "S1 (e2e) porte verte, modules=m1,m2,m2/m3, tampon porte=adoptant" \
  bras_s1_e2e "$REAL_VERIFY_LIVE" "$TMP/wt-s1e"

echo "=== pre-push de l'adoptant"
# Le hook du VIVANT, câblé par le geste documenté. PA1 lit le tampon que le
# vrai `stamp_write` vient d'écrire en S1 (e2e) : le canal, bout à bout — un
# champ renommé d'un côté rougit ici, jamais dans un banc qui fabrique ses
# tampons. PA2 et PA3 fabriquent le leur, comme pre-push.test.sh.
faire git init -q --bare "$TMP/remote.git"
faire gc -C "$LIVE" remote add e2e "$TMP/remote.git"
faire gc -C "$LIVE" config core.hooksPath .githooks
pousser() {  # pousser <ref distante>
  SORTIE="$(git -C "$LIVE" push e2e "HEAD:refs/heads/$1" 2>&1)"
  RC=$?
}
bras_pa1() {
  pousser travail
  [ "$RC" -eq 0 ] || { raison "push refusé, rc $RC"; return 1; }
  contient "accepted (porte adoptant)" || { raison "acceptation adoptant non annoncée"; return 1; }
  contient "TRACED DEROGATION in this verdict — derogation_gardes: $RAISON_ACCENT" \
    || { raison "la dérogation n'est pas imprimée intacte"; return 1; }
}
vert "PA1 tampon RÉEL de S1 accepté, dérogation imprimée intacte" bras_pa1
bras_pa2() {  # <ref distante> — un tampon du KIT (sans porte=) est refusé chez l'adoptant
  printf 'sha=%s\nmode=frozen\nlinux=1\nhost=banc\nat=banc\n' "$C_REAL" > "$STAMP"
  pousser "$1"
  [ "$RC" -ne 0 ] || { raison "un tampon du kit a passé la porte adoptant"; return 1; }
  contient "carries no porte=adoptant" || { raison "le refus ne nomme pas porte=adoptant"; return 1; }
}
vert "PA2 tampon du kit refusé chez l'adoptant" bras_pa2 travail2
faire mkdir -p "$LIVE/.hooks-mutant"
muter "$REAL_HOOK" "$LIVE/.hooks-mutant/pre-push" \
  '    if [ "$stamp_porte" != "adoptant" ]; then' '    if false; then' 1
faire gc -C "$LIVE" config core.hooksPath .hooks-mutant
rouge "PA2 sous « exigence porte=adoptant retirée du hook »" bras_pa2 travail2m
# L'acceptation vient du hook MUTÉ, qui a parlé — pas d'un hook non exécuté.
contient "accepted (porte adoptant)" || fail "PA2 : l'acceptation ne vient pas du hook muté"
faire gc -C "$LIVE" config core.hooksPath .githooks
bras_pa3() {  # requireLinux est SANS OBJET chez l'adoptant
  printf 'sha=%s\nmode=frozen\nlinux=0\nhost=banc\nat=banc\nporte=adoptant\n' "$C_REAL" > "$STAMP"
  pousser travail3
  [ "$RC" -eq 0 ] || { raison "requireLinux a refusé un verdict adoptant, rc $RC"; return 1; }
  contient "verify.requireLinux not applied" || { raison "requireLinux sans objet non annoncé"; return 1; }
}
faire gc -C "$LIVE" config --bool verify.requireLinux true
vert "PA3 requireLinux sans objet chez l'adoptant" bras_pa3
faire gc -C "$LIVE" config --unset verify.requireLinux

echo "=== K-linux, porte absente, dérogation vidée"
# `--at <sha> --linux` en adoptant : `linux=0` au tampon, et docker n'est
# JAMAIS appelé (un bouchon `docker` en tête du PATH note chaque appel).
SHIM_DOCKER="$TMP/shim-docker"
faire mkdir -p "$SHIM_DOCKER"
cat > "$SHIM_DOCKER/docker" <<'DOCKER'
#!/usr/bin/env bash
echo "docker $*" >> "${BANC_DOCKER_TRACE:-/dev/null}"
exit 1
DOCKER
chmod +x "$SHIM_DOCKER/docker"
[ "$(PATH="$SHIM_DOCKER:$PATH"; command -v docker)" = "$SHIM_DOCKER/docker" ] \
  || fail "K-linux : le bouchon docker n'est pas en tête du PATH — le bras ne verrait rien"
bras_klinux() {  # <script> — sur le clone de S1 (e2e), réemployé
  rm -f "$STAMP" "$TMP/docker-appels"
  lancer "$1" "$TMP/wt-s1e" "$G_VIDE" PATH="$SHIM_DOCKER:$PATH" BANC_DOCKER_TRACE="$TMP/docker-appels" \
    CADRE_GARDES_DEGRADEES="$RAISON_ACCENT" -- --at "$C_REAL" --linux
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ ! -e "$TMP/docker-appels" ] || { raison "docker appelé : $(cat "$TMP/docker-appels")"; return 1; }
  contient "linux replay: no object in adoptant mode" || { raison "la jambe conteneur n'est pas dite sans objet"; return 1; }
  [ "$(champ "$STAMP" porte)" = "adoptant" ] || { raison "tampon : porte"; return 1; }
  [ "$(champ "$STAMP" linux)" = "0" ] || { raison "tampon : linux=$(champ "$STAMP" linux) sous --linux"; return 1; }
}
vert "K-linux --at --linux en adoptant : linux=0, docker jamais appelé" bras_klinux "$REAL_VERIFY_LIVE"
muter "$REAL_VERIFY" "$MUTANT" '    STAMP_LINUX=0' '    : linux recopié par le mutant' 1
rouge "K-linux sous « \$LINUX recopié au tampon »" bras_klinux "$MUTANT"

# Porte absente : `porte_adoptant.py` retiré du commit → ROUGE nommé, jamais
# un repli sur la suite du kit ; le vert précédent est effacé.
_idx="$TMP/index-sans-porte"
rm -f "$_idx"
faire env GIT_INDEX_FILE="$_idx" git -C "$LIVE" read-tree "$C_REAL"
faire env GIT_INDEX_FILE="$_idx" git -C "$LIVE" update-index --force-remove .agents/bin/porte_adoptant.py
_arbre="$(env GIT_INDEX_FILE="$_idx" git -C "$LIVE" write-tree)" || fail "fixture : arbre sans porte"
C_ABS="$(gc -C "$LIVE" commit-tree "$_arbre" -p "$C_REAL" -m "banc : porte retirée")" || fail "fixture : commit sans porte"
faire gc -C "$LIVE" branch -f sans-porte "$C_ABS"
bras_kabs() {  # <commit sans porte> — le message vient du verify.sh INTERNE de ce commit
  semer_tampon
  lancer "$REAL_VERIFY_LIVE" "$TMP/wt-s1e" "$G_VIDE" CADRE_GARDES_DEGRADEES="$RAISON_ACCENT" -- --at "$1"
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1"; return 1; }
  contient ".agents/bin/porte_adoptant.py is ABSENT" || { raison "l'absence de la porte n'est pas nommée"; return 1; }
  contient "remède : synchroniser .agents/bin/porte_adoptant.py avec core-scripts/verify.sh (même commit du kit)" \
    || { raison "le remède de la porte absente n'est pas imprimé"; return 1; }
  [ ! -e "$STAMP" ] || { raison "un tampon survit à un rouge"; return 1; }
}
vert "K porte absente : ROUGE nommé, remède imprimé, tampon effacé" bras_kabs "$C_ABS"
# Mutant (binôme c4f3 fable F3) : un commit dont le verify.sh INTERNE a perdu le remède.
_sans_remede="$TMP/verify-sans-remede.sh"
muter "$REAL_VERIFY" "$_sans_remede" '    echo "    remède : synchroniser' '    : "    remède : synchroniser' 1
_blob="$(git -C "$LIVE" hash-object -w "$_sans_remede")" || fail "fixture : blob sans remède"
_mode="$(git -C "$LIVE" ls-tree "$C_ABS" core-scripts/verify.sh | cut -d' ' -f1)"
[ -n "$_mode" ] || fail "fixture : mode de core-scripts/verify.sh illisible à C_ABS"
rm -f "$_idx"
faire env GIT_INDEX_FILE="$_idx" git -C "$LIVE" read-tree "$C_ABS"
faire env GIT_INDEX_FILE="$_idx" git -C "$LIVE" update-index --cacheinfo "$_mode,$_blob,core-scripts/verify.sh"
_arbre="$(env GIT_INDEX_FILE="$_idx" git -C "$LIVE" write-tree)" || fail "fixture : arbre sans remède"
C_ABS_MUT="$(gc -C "$LIVE" commit-tree "$_arbre" -p "$C_ABS" -m "banc : porte retirée, remède retiré")" \
  || fail "fixture : commit sans remède"
faire gc -C "$LIVE" branch -f sans-porte-sans-remede "$C_ABS_MUT"
rouge "K porte absente sous « remède retiré »" bras_kabs "$C_ABS_MUT"

# Dérogation VIDÉE par l'assainissement de `porte_lire` : ROUGE. La vraie
# porte ne peut pas l'écrire (elle retire déjà toute la catégorie Cc, un
# surensemble de `tr -d '\000-\037\177'`) : le PORTE_RESULT vient du bouchon.
CTRL="$(printf '\001\002')"
bras_kvide() {  # <script> — sur le clone de S1 (bouchon), réemployé
  semer_tampon
  lancer "$1" "$TMP/wt-s1s" "$G_VIDE" BANC_DEROGATION="$CTRL" -- --at "$C_STUB"
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1"; return 1; }
  contient "EMPTY reason after sanitising" || { raison "la dérogation vide n'est pas nommée"; return 1; }
  [ ! -e "$STAMP" ] || { raison "un tampon survit à une dérogation vide"; return 1; }
  # La 6e colonne du journal de porte nomme l'étape rouge (T-01M5PVWF7H) : ici
  # le canal de retour refusé par l'extérieur, jamais `?`.
  local _journal="$LIVE/.agents/state/local/porte-chrono.tsv" _etape
  [ -f "$_journal" ] || { raison "aucun journal de porte écrit"; return 1; }
  _etape="$(sed -n '$p' "$_journal" | cut -f6)"
  [ "$_etape" = "porte adoptant (PORTE_RESULT)" ] \
    || { raison "6e colonne « $_etape », attendu « porte adoptant (PORTE_RESULT) »"; return 1; }
}
vert "K dérogation vidée par l'assainissement : ROUGE" bras_kvide "$REAL_VERIFY_LIVE"
muter "$REAL_VERIFY" "$MUTANT" '  if [ -n "$vides" ]; then' '  if false; then' 1
rouge "K dérogation vidée sous « refus des clés vides retiré »" bras_kvide "$MUTANT"
muter "$REAL_VERIFY" "$MUTANT" 'rc=1; noter_rouge "porte adoptant (PORTE_RESULT)"; }' 'rc=1; }' 1
rouge "K dérogation vidée sous « étape PORTE_RESULT non notée »" bras_kvide "$MUTANT"

echo "=== S2, S3, S3b, S6 : mutants du peuplement, clones NEUFS"
muter "$REAL_VERIFY" "$MUTANT" '  peupler_et_verifier "$WT" "$ROOT" || exit 1' '  : peuplement retiré par le mutant' 1
rouge "S1 (bouchon) sous « peuplement retiré »" bras_s1 "$MUTANT" "$TMP/wt-s2s"
_d="$(sed -n 's/^DISCOVER=//p' "$STUB_OUT" | tr '\n' ' ')"
[ "$_d" = ". " ] || fail "S2 (bouchon) : discover rend « $_d », attendu la racine seule"
rouge "S1 (e2e) sous « peuplement retiré »" bras_s1_e2e "$MUTANT" "$TMP/wt-s2e"
_res="$TMP/wt-s2e/.agents/state/local/PORTE_RESULT"
[ "$(champ "$_res" verdict)" = "ECHEC" ] || fail "S2 (e2e) : verdict « $(champ "$_res" verdict) », attendu ECHEC"
grep -qx 'modules=' "$_res" || fail "S2 (e2e) : modules= devrait être vide : $(champ "$_res" modules)"
# S-00004278 : « aucun module » n'est plus qu'un AVERTISSEMENT — l'ECHEC vient du
# gitlink au dossier vide, nommé.
contient "AVERTISSEMENT : aucun module de famille connue" || fail "S2 (e2e) : l'absence de module n'est pas dite"
contient "sous-module non peuplé" || fail "S2 (e2e) : le gitlink au dossier vide n'est pas nommé"
NBRAS=$((NBRAS + 1))
echo "ok: S2 le mutant rougit pour SA raison — racine seule (bouchon), gitlink vide + ECHEC (e2e)"

# S3 — l'URL de `.gitmodules` n'est jamais lue : non réécrite, elle devient un
# refus de PROTOCOLE (la ligne de la fonction + `transport 'https' not
# allowed`, sous LC_ALL=C), jamais un accès réseau.
muter "$REAL_VERIFY" "$MUTANT" '    git -C "$wt" config "submodule.$nom.url" "$src" \' '    true \' 1
rouge "S1 (bouchon) sous « URL non réécrite »" bras_s1 "$MUTANT" "$TMP/wt-s3"
refus_https() {
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1"; return 1; }
  contient "$FONCTION_ECHEC" || { raison "la ligne de la fonction manque"; return 1; }
  contient "transport 'https' not allowed" || { raison "pas de refus de PROTOCOLE https"; return 1; }
}
vert "S3 URL non réécrite : refus de protocole https, jamais le réseau" refus_https
# S3b — l'env retiré AUSSI : l'assertion de S3 rougit. C'est la preuve que
# l'env est la ceinture qui ferme https (le `-c protocol.file.allow` ne le fait
# pas). Proxies neutralisés : la seule sortie est la résolution DNS.
muter "$REAL_VERIFY" "$MUTANT" '    git -C "$wt" config "submodule.$nom.url" "$src" \' '    true \' 1 \
  "GIT_ALLOW_PROTOCOL='file' git -C \"\$wt\" -c" 'git -C "$wt" -c' 1
bras_s3b() {
  lancer "$MUTANT" "$TMP/wt-s3b" "$G_VIDE" no_proxy='*' NO_PROXY='*' -- --at "$C_STUB"
  refus_https
}
rouge "S3 sous « URL non réécrite + GIT_ALLOW_PROTOCOL retiré »" bras_s3b
contient "Could not resolve host" || fail "S3b : la sortie n'est pas la résolution réseau attendue"
echo "    relevé S3b : $(grep -m1 'Could not resolve host' <<< "$SORTIE")"

# S6 — la récursion retirée : m2/m3 reste vide, la ligne de défense le voit.
muter "$REAL_VERIFY" "$MUTANT" '      peupler_sous_modules "$wt/$chemin" "$vivant/$chemin" || return 1' \
  '      : récursion retirée par le mutant' 1
rouge "S1 (bouchon) sous « récursion retirée »" bras_s1 "$MUTANT" "$TMP/wt-s6"
[ "$RC" -eq 1 ] || fail "S6 : rc $RC, attendu 1"
contient "ligne de défense" || fail "S6 : la ligne de défense n'a pas parlé"
grep -qE "^-$A3 m2/m3" <<< "$SORTIE" || fail "S6 : la ligne « - m2/m3 » manque"
NBRAS=$((NBRAS + 1))
echo "ok: S6 récursion retirée → ligne « - m2/m3 » de la ligne de défense"

echo "=== S3c : niveau FONCTION, protocol.file.allow=never global"
# Sous `never` global, `--at` échoue AVANT le peuplement (clone et fetch du
# superprojet, préexistant, mesuré) : le bras se joue sur les deux fonctions
# EXTRAITES de verify.sh (sed entre `^nom()` et `^}`), SOURCÉES depuis un
# fichier — jamais `eval`. Les mutants à UNE seule ceinture restent verts sur
# git 2.55 (mesuré) : ils ne sont pas des bras.
EXTRAIT="$TMP/peupler-extrait.sh"
sed -n -e '/^peupler_sous_modules()/,/^}/p' -e '/^peupler_et_verifier()/,/^}/p' "$REAL_VERIFY" > "$EXTRAIT"
[ -s "$EXTRAIT" ] || fail "S3c : l'extrait est vide — les fonctions ont changé de nom"
grep -q '^peupler_sous_modules() {' "$EXTRAIT" || fail "S3c : peupler_sous_modules absente de l'extrait"
grep -q '^peupler_et_verifier() {' "$EXTRAIT" || fail "S3c : peupler_et_verifier absente de l'extrait"
grep -qF 'submodule update -q --checkout --force --no-recommend-shallow' "$EXTRAIT" \
  || fail "S3c : la ligne submodule update manque à l'extrait"
G_NEVER="$TMP/gitconfig-file-never"
printf '[protocol "file"]\n\tallow = never\n' > "$G_NEVER"
bras_s3c() {  # <extrait> <wt neuf>
  local etat
  [ ! -e "$2" ] || { raison "S3c exige un clone NEUF"; return 1; }
  git clone -q "$LIVE" "$2" || { raison "clone de fixture"; return 1; }
  # Le fichier sourcé est l'extrait que ce banc vient d'écrire : son chemin est
  # variable par construction, la directive le dit à l'analyseur.
  # shellcheck source=/dev/null
  SORTIE="$( { . "$1" && export GIT_CONFIG_GLOBAL="$G_NEVER" && peupler_et_verifier "$2" "$LIVE"; } 2>&1 )"
  RC=$?
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  etat="$(git -C "$2" submodule status --recursive)"
  [ "$(grep -c '' <<< "$etat")" -eq 3 ] || { raison "trois modules attendus : $etat"; return 1; }
  if grep -q '^[^ ]' <<< "$etat"; then raison "un module hors gitlink : $etat"; return 1; fi
}
vert "S3c les deux ceintures file tiennent sous never global" bras_s3c "$EXTRAIT" "$TMP/wt-s3c"
muter "$EXTRAIT" "$TMP/peupler-extrait-mutant.sh" \
  "GIT_ALLOW_PROTOCOL='file' git -C \"\$wt\" -c submodule.recurse=false -c protocol.file.allow=always submodule update" \
  'git -C "$wt" -c submodule.recurse=false submodule update' 1
rouge "S3c sous « env ET -c retirés »" bras_s3c "$TMP/peupler-extrait-mutant.sh" "$TMP/wt-s3cm"
contient "transport 'file' not allowed" || fail "S3c : le mutant n'a pas rougi par le protocole file"

echo "=== S10 : sous-module à espace dans le nom ou le chemin, niveau FONCTION"
# binôme c4f3 (opus F6) : `submodule.<nom>.path <chemin>` est découpé à la
# PREMIÈRE espace ; un nom à espace y devenait un chemin faux et un remède faux.
# Refus nommé AVANT le découpage. Un dépôt jetable, aucun gitlink : seul le
# `.gitmodules` est lu.
bras_s10() {  # <extrait> <wt neuf> <nom> <chemin>
  [ ! -e "$2" ] || { raison "S10 exige un dépôt NEUF"; return 1; }
  gc init -q "$2" || { raison "fixture S10"; return 1; }
  printf '[submodule "%s"]\n\tpath = %s\n\turl = https://invalid.invalid/x.git\n' "$3" "$4" > "$2/.gitmodules"
  # shellcheck source=/dev/null
  SORTIE="$( { . "$1" && peupler_sous_modules "$2" "$TMP/vivant-s10"; } 2>&1 )"
  RC=$?
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1"; return 1; }
  contient "sous-module à espace dans le nom ou le chemin" || { raison "le refus n'est pas nommé"; return 1; }
  contient "non pris en charge" || { raison "« non pris en charge » manque"; return 1; }
  if contient "remède : git -C"; then raison "un remède faux est imprimé"; return 1; fi
}
vert "S10 nom et chemin à espace : refus nommé, aucun remède faux" bras_s10 "$EXTRAIT" "$TMP/wt-s10a" "a b" "a b"
vert "S10 chemin seul à espace : refus nommé" bras_s10 "$EXTRAIT" "$TMP/wt-s10b" "ab" "a b"
muter "$REAL_VERIFY" "$TMP/verify-s10-mutant.sh" "      *\" \"*\" \"*)" '      __jamais__)' 1
sed -n -e '/^peupler_sous_modules()/,/^}/p' -e '/^peupler_et_verifier()/,/^}/p' \
  "$TMP/verify-s10-mutant.sh" > "$TMP/peupler-extrait-s10m.sh"
[ -s "$TMP/peupler-extrait-s10m.sh" ] || fail "S10 : l'extrait du mutant est vide"
rouge "S10 sous « refus retiré »" bras_s10 "$TMP/peupler-extrait-s10m.sh" "$TMP/wt-s10m" "a b" "a b"
contient "remède : git -C" || fail "S10 : sans le refus, le remède faux devait reparaître"

echo "=== S5, S5b : module non initialisé dans le vivant"
faire gc -C "$LIVE" submodule deinit -q -f m2
[ -d "$LIVE/m2" ] && [ -z "$(ls -A "$LIVE/m2")" ] || fail "S5 : m2 n'est pas vidé dans le vivant"
S5_LIGNE="--at: sous-module 'm2' non initialisé dans l'arbre vivant ($LIVE/m2) — remède : git -C '$LIVE' submodule update --init -- 'm2'"
bras_s5() {  # <script> <wt> <ligne attendue>
  semer_tampon
  lancer "$1" "$2" "$G_VIDE" -- --at "$C_STUB"
  refus_avant_interne "$3"
}
vert "S5 refus nommé, clone NEUF" bras_s5 "$REAL_VERIFY_LIVE" "$TMP/wt-s5" "$S5_LIGNE"
vert "S5 refus nommé, clone RÉEMPLOYÉ" bras_s5 "$REAL_VERIFY_LIVE" "$TMP/wt-s1s" "$S5_LIGNE"
muter "$REAL_VERIFY" "$MUTANT" \
  '    if ! prefixe="$(git -C "$src" rev-parse --show-prefix 2>/dev/null)" || [ -n "$prefixe" ]; then' \
  '    if false; then' 1
rouge "S5 sous « précondition retirée »" bras_s5 "$MUTANT" "$TMP/wt-s5m" "$S5_LIGNE"
# Restauration : l'URL locale AVANT l'update (celle de .gitmodules est
# injoignable par construction), puis m3 depuis le gitdir conservé.
faire gc -C "$LIVE" config submodule.m2.url "$SRC/m2"
faire gfile -C "$LIVE" submodule update -q --init -- m2
faire gfile -C "$LIVE/m2" submodule update -q --init
vivant_sain

# S5b — m3 IMBRIQUÉ dé-initialisé, sur un clone RÉEMPLOYÉ où m2/m3 est déjà
# peuplé : le refus tombe à la précondition, le clone périmé ne le masque pas,
# et le remède est ENRACINÉ au module parent (sans `-C` il échoue à profondeur 2,
# mesuré).
[ -z "$(git -C "$TMP/wt-s1s/m2/m3" rev-parse --show-prefix 2>/dev/null)" ] \
  && [ "$(git -C "$TMP/wt-s1s/m2/m3" rev-parse HEAD 2>/dev/null)" = "$A3" ] \
  || fail "S5b précondition : m2/m3 n'est pas peuplé dans le clone réemployé"
faire gc -C "$LIVE/m2" submodule deinit -q -f m3
S5B_LIGNE="--at: sous-module 'm3' non initialisé dans l'arbre vivant ($LIVE/m2/m3) — remède : git -C '$LIVE/m2' submodule update --init -- 'm3'"
vert "S5b refus nommé, remède enraciné au parent" bras_s5 "$REAL_VERIFY_LIVE" "$TMP/wt-s1s" "$S5B_LIGNE"
rouge "S5b sous « précondition retirée »" bras_s5 "$MUTANT" "$TMP/wt-s1s" "$S5B_LIGNE"
# Le remède imprimé, rejoué tel quel depuis le parent (l'URL locale d'abord).
faire gc -C "$LIVE/m2" config submodule.m3.url "$SRC/m3"
faire gfile -C "$LIVE/m2" submodule update -q --init -- m3
vivant_sain

echo "=== S4 : gitlink absent du module vivant, clone RÉEMPLOYÉ"
preparer "$TMP/wt-s4"
bras_s4() {  # <script> <commit>
  semer_tampon
  lancer "$1" "$TMP/wt-s4" "$G_VIDE" -- --at "$2"
  refus_avant_interne "$FONCTION_ECHEC"
}
S4A="$(commit_super "$C_STUB" s4-a m1 4444444444444444444444444444444444444444)" || fail "fixture S4"
absent_du_clone "$TMP/wt-s4" "$S4A"
vert "S4 refus nommé par la fonction, interne jamais lancé" bras_s4 "$REAL_VERIFY_LIVE" "$S4A"
# Le mutant joue un commit que CE clone n'a jamais vu : le fetch on-demand ne
# récurse que sur des commits NOUVELLEMENT rapportés qui déplacent un gitlink.
S4B="$(commit_super "$C_STUB" s4-b m1 5555555555555555555555555555555555555555)" || fail "fixture S4"
absent_du_clone "$TMP/wt-s4" "$S4B"
muter "$REAL_VERIFY" "$MUTANT" 'fetch -q --no-recurse-submodules origin \' 'fetch -q origin \' 1
rouge "S4 sous « --no-recurse-submodules retiré du fetch »" bras_s4 "$MUTANT" "$S4B"
contient "--at: git fetch failed" || fail "S4 : le mutant n'a pas rougi par le fetch récursif"

echo "=== S7 : réemploi — gitlink déplacé, dépôt périmé et artefact plantés"
preparer "$TMP/wt-s7"
bras_s7() {  # <script> <étiquette>
  local n s
  n="$(avancer_module "$LIVE/m1")" || { raison "fixture S7"; return 1; }
  s="$(commit_super "$C_STUB" "s7-$2" m1 "$n")" || { raison "fixture S7"; return 1; }
  faire gc init -q "$TMP/wt-s7/m2/perime"
  faire gc -C "$TMP/wt-s7/m2/perime" commit -q --allow-empty -m perime
  faire mkdir -p "$TMP/wt-s7/m1/build"
  printf 'x\n' > "$TMP/wt-s7/m1/build/artefact.bin"
  lancer "$1" "$TMP/wt-s7" "$G_VIDE" -- --at "$s"
  bouchon_a_vu "$n" "$A2" "$A3" || return 1
  [ ! -e "$TMP/wt-s7/m2/perime" ] || { raison "le dépôt périmé imbriqué a survécu"; return 1; }
  [ ! -e "$TMP/wt-s7/m1/build/artefact.bin" ] || { raison "l'artefact a survécu"; return 1; }
}
vert "S7 dépôt périmé et artefact supprimés, m1 au gitlink déplacé" bras_s7 "$REAL_VERIFY_LIVE" tip
muter "$REAL_VERIFY" "$MUTANT" "'git clean -ffdxq'" "'git clean -fdxq'" 1
rouge "S7 sous « clean -ffdx → -fdx dans les modules »" bras_s7 "$MUTANT" mutant

echo "=== S8 : submodule.recurse=true global, clone RÉEMPLOYÉ"
G_RECURSE="$TMP/gitconfig-recurse"
printf '[submodule]\n\trecurse = true\n' > "$G_RECURSE"
# S8a — gitlink AVANCÉ sur une branche, vers un commit de m1 présent dans le
# vivant et ABSENT du clone (un recul vers un sha présent laisserait le mutant
# vert, mesuré). Un bump NEUF par passage.
preparer "$TMP/wt-s8a"
bras_s8a() {  # <script> <étiquette>
  local n s t="$TMP/trace-s8a-$2"
  n="$(avancer_module "$LIVE/m1")" || { raison "fixture S8a"; return 1; }
  s="$(commit_super "$C_STUB" "s8a-$2" m1 "$n")" || { raison "fixture S8a"; return 1; }
  absent_du_clone "$TMP/wt-s8a/m1" "$n"
  lancer "$1" "$TMP/wt-s8a" "$G_RECURSE" GIT_TRACE="$t" -- --at "$s"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ "$(git -C "$TMP/wt-s8a/m1" rev-parse HEAD)" = "$n" ] || { raison "m1 n'est pas au gitlink"; return 1; }
  trace_detach "$t" 1
}
vert "S8a gitlink avancé, sha absent du clone : vert, UNE ligne --detach" bras_s8a "$REAL_VERIFY_LIVE" tip
muter "$REAL_VERIFY" "$MUTANT" \
  'if ! git -C "$WT" checkout --detach -q --no-recurse-submodules -f "$SHA" 2>/dev/null; then' \
  'if ! git -C "$WT" checkout --detach -q -f "$SHA" 2>/dev/null; then' 1
rouge "S8a sous « drapeau retiré du PREMIER checkout »" bras_s8a "$MUTANT" premier
[ "$RC" -eq 0 ] && [ "$(grep -c 'built-in: git checkout --detach' "$TMP/trace-s8a-premier")" -eq 2 ] \
  || fail "S8a : le premier drapeau retiré devait rendre rc 0 et DEUX lignes (le repli guérit)"
muter "$REAL_VERIFY" "$MUTANT" 'checkout --detach -q --no-recurse-submodules -f "$SHA"' 'checkout --detach -q -f "$SHA"' 2
rouge "S8a sous « drapeau retiré des DEUX checkout »" bras_s8a "$MUTANT" deux
[ "$RC" -eq 1 ] && contient "cannot checkout new HEAD" \
  || fail "S8a : les deux drapeaux retirés devaient rougir par « cannot checkout new HEAD »"

# S8b — commit de superprojet DÉTACHÉ du vivant (aucune ref, inconnu du clone) :
# le premier checkout échoue légitimement, le repli `fetch <sha>` puis le
# second checkout passent — DEUX lignes, et le second drapeau est le seul
# rempart.
preparer "$TMP/wt-s8b"
bras_s8b() {  # <script> <étiquette>
  local n s t="$TMP/trace-s8b-$2"
  n="$(avancer_module "$LIVE/m1")" || { raison "fixture S8b"; return 1; }
  s="$(commit_super "$C_STUB" - m1 "$n")" || { raison "fixture S8b"; return 1; }
  absent_du_clone "$TMP/wt-s8b" "$s"
  absent_du_clone "$TMP/wt-s8b/m1" "$n"
  lancer "$1" "$TMP/wt-s8b" "$G_RECURSE" GIT_TRACE="$t" -- --at "$s"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ "$(git -C "$TMP/wt-s8b/m1" rev-parse HEAD)" = "$n" ] || { raison "m1 n'est pas au gitlink"; return 1; }
  trace_detach "$t" 2
}
vert "S8b commit détaché : vert, DEUX lignes --detach (repli légitime)" bras_s8b "$REAL_VERIFY_LIVE" tip
muter "$REAL_VERIFY" "$MUTANT" \
  '    git -C "$WT" checkout --detach -q --no-recurse-submodules -f "$SHA" \' \
  '    git -C "$WT" checkout --detach -q -f "$SHA" \' 1
rouge "S8b sous « drapeau retiré du SECOND checkout »" bras_s8b "$MUTANT" second
[ "$RC" -eq 1 ] || fail "S8b : le second drapeau retiré devait rendre rc 1"

# S8c — bump IMBRIQUÉ sous `[submodule] recurse = true` PUIS
# `[fetch] recurseSubmodules = false`, DANS CET ORDRE. L'ordre est une
# CONDITION DU TÉMOIN (plan rév. 7, C1-it6, mesuré sur git 2.55) : le mutant
# « -c submodule.recurse=false retiré » reste VERT sous l'ordre inverse, sous
# `submodule.recurse=true` seul et sous `fetch.recurseSubmodules=false` seul —
# dans les deux premiers le fetch enfant de m2 récurse à la demande et apporte
# l'objet de m3, dans le troisième le checkout enfant ne récurse pas. Le piège
# exige un fetch enfant qui NE récurse PAS et un checkout enfant qui récurse.
G_PAIRE="$TMP/gitconfig-recurse-puis-fetch"
printf '[submodule]\n\trecurse = true\n[fetch]\n\trecurseSubmodules = false\n' > "$G_PAIRE"
preparer "$TMP/wt-s8c"
bras_s8c() {  # <script> <étiquette>
  local n3 n2 s t="$TMP/trace-s8c-$2"
  n3="$(avancer_module "$LIVE/m2/m3")" || { raison "fixture S8c"; return 1; }
  faire gc -C "$LIVE/m2" add m3
  faire gc -C "$LIVE/m2" commit -qm "banc : m3 avancé"
  n2="$(git -C "$LIVE/m2" rev-parse HEAD)"
  s="$(commit_super "$C_STUB" "s8c-$2" m2 "$n2")" || { raison "fixture S8c"; return 1; }
  absent_du_clone "$TMP/wt-s8c/m2" "$n2"
  absent_du_clone "$TMP/wt-s8c/m2/m3" "$n3"
  lancer "$1" "$TMP/wt-s8c" "$G_PAIRE" GIT_TRACE="$t" -- --at "$s"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ "$(git -C "$TMP/wt-s8c/m2/m3" rev-parse HEAD)" = "$n3" ] || { raison "m2/m3 n'est pas au gitlink"; return 1; }
  trace_detach "$t" 1
}
vert "S8c bump imbriqué : vert, m2/m3 au gitlink, UNE ligne --detach" bras_s8c "$REAL_VERIFY_LIVE" tip
muter "$REAL_VERIFY" "$MUTANT" '-c submodule.recurse=false -c protocol.file.allow=always submodule update' \
  '-c protocol.file.allow=always submodule update' 1
rouge "S8c sous « -c submodule.recurse=false retiré »" bras_s8c "$MUTANT" mutant
[ "$RC" -eq 1 ] && contient "$FONCTION_ECHEC" && contient "cannot checkout new HEAD" \
  || fail "S8c : le mutant devait rougir par la fonction et « cannot checkout new HEAD »"

echo "=== S9, S9b : submodule.m1.update=rebase|none, gitlink DIVERGENT, clone RÉEMPLOYÉ"
# Un fils de X0 dans le m1 VIVANT, sur sa branche (le clone, lui, est à X1) :
# div.txt y prend un autre contenu, si bien qu'un rebase CONFLICTE.
divergent() {  # <contenu> — imprime le sha
  local idx="$TMP/index-m1" blob arbre c
  rm -f "$idx"
  blob="$(printf '%s\n' "$1" | git -C "$LIVE/m1" hash-object -w --stdin)" || return 1
  GIT_INDEX_FILE="$idx" git -C "$LIVE/m1" read-tree "$X0" || return 1
  GIT_INDEX_FILE="$idx" git -C "$LIVE/m1" update-index --add --cacheinfo "100644,$blob,div.txt" || return 1
  arbre="$(GIT_INDEX_FILE="$idx" git -C "$LIVE/m1" write-tree)" || return 1
  c="$(gc -C "$LIVE/m1" commit-tree "$arbre" -p "$X0" -m "banc : divergent $1")" || return 1
  gc -C "$LIVE/m1" branch -f "div-$1" "$c" >/dev/null || return 1
  printf '%s' "$c"
}
# L'identité est fournie en env à ces appels (la purge de tête l'a retirée) :
# l'échec du mutant est le rebase, jamais un crash d'identité.
ID_ENV=(GIT_AUTHOR_NAME=banc GIT_AUTHOR_EMAIL=banc@banc.invalid
  GIT_COMMITTER_NAME=banc GIT_COMMITTER_EMAIL=banc@banc.invalid)
bras_s9() {  # <script> <mode update> <contenu> <wt>
  local d s
  d="$(divergent "$3")" || { raison "fixture S9"; return 1; }
  s="$(commit_super "$C_STUB" "s9-$3" m1 "$d")" || { raison "fixture S9"; return 1; }
  absent_du_clone "$4/m1" "$d"
  faire git -C "$4" config submodule.m1.update "$2"
  lancer "$1" "$4" "$G_VIDE" "${ID_ENV[@]}" -- --at "$s"
  [ "$RC" -eq 0 ] || { raison "rc $RC, attendu 0"; return 1; }
  [ "$(git -C "$4/m1" rev-parse HEAD)" = "$d" ] || { raison "m1 n'est pas au gitlink divergent"; return 1; }
}
preparer "$TMP/wt-s9"
vert "S9 update=rebase, gitlink divergent : m1 au gitlink" bras_s9 "$REAL_VERIFY_LIVE" rebase b "$TMP/wt-s9"
muter "$REAL_VERIFY" "$MUTANT" 'submodule update -q --checkout --force' 'submodule update -q --force' 1
rouge "S9 sous « --checkout retiré »" bras_s9 "$MUTANT" rebase c "$TMP/wt-s9"
# Réserve S-00004193 : le rebase rougit par CONFLIT, pas par la ligne `+sha` —
# rc 1 asserté seul.
[ "$RC" -eq 1 ] || fail "S9 : sous le mutant, rc $RC — attendu 1"
preparer "$TMP/wt-s9b"
vert "S9b update=none, gitlink divergent : m1 au gitlink" bras_s9 "$REAL_VERIFY_LIVE" none d "$TMP/wt-s9b"
rouge "S9b sous « --checkout retiré »" bras_s9 "$MUTANT" none e "$TMP/wt-s9b"
[ "$RC" -eq 1 ] || fail "S9b : sous le mutant, rc $RC — attendu 1"

echo "=== F1 : base semgrep sous --at, calculée sur le VIVANT (binôme c4f3 bis, fable F1 / opus T2)"
# Mesuré avant correctif : dans le clone, `origin/HEAD` nomme la branche que le
# vivant avait extraite, la base tombait à HEAD^1, et un `eval` au commit 1/2
# d'une branche passait la porte. Fixture SANS sous-module, à elle : main (base),
# puis `feat` — commit 1 ajoute a.sh (eval), commit 2 ajoute b.txt. Un bouchon
# semgrep NOTE sa base (« aucune » = scan complet) et rend une trouvaille quand un
# fichier NEUF depuis cette base porte `eval "`. Deux ceintures, un bras chacune :
# F1b, la base passée par CADRE_SEMGREP_BASE ; F1c, `origin/HEAD` retiré du clone ;
# F1a, les deux ensemble. Clones NEUFS partout.
LIVE_F1="$TMP/live-f1"
F1MUT="$LIVE_F1/core-scripts/verify-mutant.sh"
F1_OUTILS="$TMP/outils-f1"
faire mkdir -p "$LIVE_F1/.agents/security" "$LIVE_F1/.agents/bin" "$LIVE_F1/.githooks" \
  "$LIVE_F1/core-scripts" "$F1_OUTILS"
faire gc init -q "$LIVE_F1"
faire cp "$REAL_DISCOVERY" "$LIVE_F1/.agents/security/module_discovery.py"
faire cp "$REAL_PORTE" "$LIVE_F1/.agents/bin/porte_adoptant.py"
faire cp "$REAL_HOOK" "$LIVE_F1/.githooks/pre-push"
faire cp "$REAL_VERIFY" "$LIVE_F1/core-scripts/verify.sh"
printf 'rules: []\n' > "$LIVE_F1/.agents/security/semgrep.yml"
printf '[project]\nname = "cadre-kit"\nversion = "0.0.0"\ndependencies = []\n' > "$LIVE_F1/pyproject.toml"
printf '/.agents/state/local/\n/core-scripts/verify-mutant.sh\n/.hooks-mutant/\n' > "$LIVE_F1/.gitignore"
faire gc -C "$LIVE_F1" add -A
faire gc -C "$LIVE_F1" update-index --chmod=+x .githooks/pre-push
faire gc -C "$LIVE_F1" commit -qm "fixture F1 : adoptant, main"
F1_MAIN="$(git -C "$LIVE_F1" rev-parse HEAD)"
faire gc -C "$LIVE_F1" switch -q -c feat
printf '#!/usr/bin/env bash\nx="$1"\neval "$x"\n' > "$LIVE_F1/a.sh"
faire gc -C "$LIVE_F1" add a.sh
faire gc -C "$LIVE_F1" commit -qm "feat 1/2 : eval"
F1_C1="$(git -C "$LIVE_F1" rev-parse HEAD)"
printf 'y\n' > "$LIVE_F1/b.txt"
faire gc -C "$LIVE_F1" add b.txt
faire gc -C "$LIVE_F1" commit -qm "feat 2/2"
F1_TIP="$(git -C "$LIVE_F1" rev-parse HEAD)"
printf '#!/usr/bin/env bash\nexit 0\n' > "$F1_OUTILS/gitleaks"
cat > "$F1_OUTILS/semgrep" <<'SEMGREP'
#!/usr/bin/env bash
# Bouchon semgrep du bras F1 : il note sa base, écrit un rapport JSON sans
# erreur, et trouve `eval "` dans un fichier NEUF depuis la base.
base="" rapport="" prec=""
for a in "$@"; do
  case "$a" in
    --json-output=*) rapport="${a#--json-output=}" ;;
  esac
  if [ "$prec" = "--baseline-commit" ]; then base="$a"; fi
  prec="$a"
done
echo "${base:-aucune}" >> "${BANC_SEMGREP_TRACE:-/dev/null}"
if [ -n "$rapport" ]; then printf '{"results": [], "errors": []}\n' > "$rapport"; fi
if [ -n "$base" ]; then
  neufs="$(git diff --name-only "$base" HEAD)"
else
  neufs="$(git ls-files)"
fi
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if grep -qF 'eval "' "$f" 2>/dev/null; then echo "BOUCHON SEMGREP : trouvaille dans $f"; exit 1; fi
done <<< "$neufs"
exit 0
SEMGREP
chmod +x "$F1_OUTILS/gitleaks" "$F1_OUTILS/semgrep" || fail "fixture F1 : bouchons"

# bras_f1 <script> <wt neuf> <base attendue | aucune> — la base que semgrep a REÇUE,
# et la trouvaille au commit 1/2 qui rend la porte ROUGE.
bras_f1() {
  local t vu
  t="$TMP/semgrep-$(basename "$2")"
  [ ! -e "$2" ] || { raison "F1 exige un clone NEUF"; return 1; }
  rm -f "$t"
  lancer "$1" "$2" "$G_VIDE" PATH="$F1_OUTILS:$PATH" BANC_SEMGREP_TRACE="$t" -- --at "$F1_TIP"
  [ -s "$t" ] || { raison "le bouchon semgrep n'a pas tourné"; return 1; }
  vu="$(cat "$t")"
  [ "$vu" = "$3" ] || { raison "base reçue par semgrep « $vu », attendu « $3 »"; return 1; }
  [ "$RC" -eq 1 ] || { raison "rc $RC, attendu 1 — l'eval du commit 1/2 a passé la porte"; return 1; }
  contient "semgrep : TROUVAILLE sur racine" || { raison "la trouvaille n'est pas nommée"; return 1; }
}
f1_trace() { cat "$TMP/semgrep-$1" 2>/dev/null; }

vert "F1a vivant sur feat, eval au commit 1/2 : base = main du VIVANT, ROUGE" \
  bras_f1 "$LIVE_F1/core-scripts/verify.sh" "$TMP/wt-f1a" "$F1_MAIN"
contient "semgrep base (live tree): $F1_MAIN" || fail "F1a : la base du vivant n'est pas annoncée"
contient "base imposée par CADRE_SEMGREP_BASE = ${F1_MAIN:0:12}" || fail "F1a : la porte ne dit pas la base imposée"
muter "$REAL_VERIFY" "$F1MUT" 'CADRE_SEMGREP_BASE="$SEMGREP_BASE" VERIFY_INNER=1' 'VERIFY_INNER=1' 2 \
  '    git -C "$WT" symbolic-ref --delete refs/remotes/origin/HEAD 2>/dev/null || :' '    :' 1
rouge "F1a sous « base vivante ET retrait d'origin/HEAD ôtés »" bras_f1 "$F1MUT" "$TMP/wt-f1am" "$F1_MAIN"
[ "$(f1_trace wt-f1am)" = "$F1_C1" ] && [ "$RC" -eq 0 ] \
  || fail "F1a : le mutant devait rejouer le défaut MESURÉ (base HEAD^1, porte verte)"

# F1b — le vivant n'a plus de `main` locale, seulement `origin/main` : le clone
# n'en sait rien, seule la base passée par verify.sh la porte.
faire gc -C "$LIVE_F1" update-ref refs/remotes/origin/main "$F1_MAIN"
faire gc -C "$LIVE_F1" branch -q -D main
vert "F1b base = origin/main du vivant, que le clone ignore" \
  bras_f1 "$LIVE_F1/core-scripts/verify.sh" "$TMP/wt-f1b" "$F1_MAIN"
muter "$REAL_VERIFY" "$F1MUT" 'CADRE_SEMGREP_BASE="$SEMGREP_BASE" VERIFY_INNER=1' 'VERIFY_INNER=1' 2
rouge "F1b sous « base vivante ôtée »" bras_f1 "$F1MUT" "$TMP/wt-f1bm" "$F1_MAIN"
[ "$(f1_trace wt-f1bm)" = "aucune" ] || fail "F1b : sans la base vivante, le clone devait tomber au scan complet"

# F1c — aucune branche par défaut nulle part : scan COMPLET, dit — jamais le
# HEAD^1 que l'`origin/HEAD` du clone (= feat) donnerait.
faire gc -C "$LIVE_F1" update-ref -d refs/remotes/origin/main
vert "F1c aucune branche par défaut : scan complet dit, jamais HEAD^1" \
  bras_f1 "$LIVE_F1/core-scripts/verify.sh" "$TMP/wt-f1c" aucune
contient "semgrep base (live tree): none" || fail "F1c : l'absence de base vivante n'est pas dite"
contient "semgrep : scan COMPLET" || fail "F1c : le scan complet n'est pas dit"
muter "$REAL_VERIFY" "$F1MUT" '    git -C "$WT" symbolic-ref --delete refs/remotes/origin/HEAD 2>/dev/null || :' '    :' 1
rouge "F1c sous « origin/HEAD du clone gardé »" bras_f1 "$F1MUT" "$TMP/wt-f1cm" aucune
[ "$(f1_trace wt-f1cm)" = "$F1_C1" ] || fail "F1c : le mutant devait retomber sur HEAD^1"

echo "=== PA4 : l'avertissement de la porte atteint le PUSH (S-00004278)"
# F1_MAIN n'a ni script du projet ni module de famille connue : la vraie porte
# rend VERT avec `avertissement=` ; `porte_lire` le recopie au tampon, et le vrai
# pre-push l'IMPRIME — une sortie, jamais un refus : le push passe (rc 0).
AVERT="build et tests non vérifiés par le kit : ajoutez scripts/verify-projet.sh"
F1_STAMP="$LIVE_F1/.agents/state/local/VERIFY_STAMP"
faire git init -q --bare "$TMP/remote-f1.git"
faire gc -C "$LIVE_F1" remote add e2e "$TMP/remote-f1.git"
faire gc -C "$LIVE_F1" config core.hooksPath .githooks
bras_pa4() {  # <script> <wt> <ref distante>
  rm -f "$F1_STAMP"
  lancer "$1" "$2" "$G_VIDE" PATH="$F1_OUTILS:$PATH" -- --at "$F1_MAIN"
  [ "$RC" -eq 0 ] || { raison "verify --at rc $RC, attendu 0 (sans module : vert + avertissement)"; return 1; }
  [ "$(champ "$F1_STAMP" avertissement)" = "$AVERT" ] \
    || { raison "tampon : avertissement « $(champ "$F1_STAMP" avertissement) »"; return 1; }
  SORTIE="$(git -C "$LIVE_F1" push e2e "$F1_MAIN:refs/heads/$3" 2>&1)"
  RC=$?
  [ "$RC" -eq 0 ] || { raison "push refusé, rc $RC — l'avertissement ne change aucun rc"; return 1; }
  contient "accepted (porte adoptant)" || { raison "le pre-push adoptant n'a pas parlé"; return 1; }
  contient "pre-push: WARNING in this verdict — $AVERT" || { raison "l'avertissement n'est pas imprimé au push"; return 1; }
}
vert "PA4 sans module : avertissement au tampon PUIS imprimé au push, push accepté" \
  bras_pa4 "$LIVE_F1/core-scripts/verify.sh" "$TMP/wt-pa4" pa4
muter "$REAL_VERIFY" "$F1MUT" '      avertissement=*)' '      __avertissement_ignore=*)' 1
rouge "PA4 sous « avertissement non recopié au tampon (porte_lire) »" bras_pa4 "$F1MUT" "$TMP/wt-pa4" pa4m
faire mkdir -p "$LIVE_F1/.hooks-mutant"
muter "$REAL_HOOK" "$LIVE_F1/.hooks-mutant/pre-push" \
  '      echo "pre-push: WARNING in this verdict — $_avert" >&2' '      : avertissement tu par le mutant' 1
faire gc -C "$LIVE_F1" config core.hooksPath .hooks-mutant
rouge "PA4 sous « avertissement non imprimé par le pre-push »" bras_pa4 "$LIVE_F1/core-scripts/verify.sh" "$TMP/wt-pa4" pa4h
contient "accepted (porte adoptant)" || fail "PA4 : le mutant du hook devait accepter le push, en silence"
faire gc -C "$LIVE_F1" config core.hooksPath .githooks

echo "PASS: verify-adoptant ($NBRAS bras verts, $NMUT mutants tués, ${SECONDS}s)"
