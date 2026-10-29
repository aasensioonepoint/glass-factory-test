#!/usr/bin/env bash
# Tests for .githooks/post-merge and .githooks/post-commit.
# Run: bash .githooks/post-merge.test.sh
#
# Directive read by core-scripts/run-bash-tests.sh (T-00000427):
# requires: git python3
#
# REQUIRED, not auto-skipped : chaque cas joue un VRAI `git merge` (ou commit,
# cherry-pick, rebase) dans un dépôt mktemp où `core.hooksPath` vise les hooks
# SOUS TEST, avec HOME et GIT_CONFIG_GLOBAL jetables. Le pilote de fusion est posé,
# quand un cas l'exige, par `_poser_copie` + `commande_driver` du
# fusion_enregistrement.py du kit (jamais par `--installer`, qui exige un dépôt
# poussé). Un python3 < 3.11 rend le banc ROUGE, jamais vert en silence.
# T-01M5F354YPRRFCRYBG03VHGTH1 (lot C de T-01M5DBEZMXN95Y31363NXXJ30F).

set -u

# T-00001088 : purge de l environnement git herite AVANT toute commande git (noms = conftest.py::GIT_REDIRECTIONS ; filet .agents/evals/test_bash_suites_git_env.py)
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT

HERE="$(cd "$(dirname "$0")" && pwd)"
KIT="$(cd "$HERE/.." && pwd)"
PILOTE_SRC="$KIT/.agents/bin/fusion_enregistrement.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
mkdir -p "$HOME"
: > "$TMP/gitconfig"
export GIT_CONFIG_GLOBAL="$TMP/gitconfig"
export GIT_CONFIG_NOSYSTEM=1
export GIT_EDITOR=true
export GIT_MERGE_AUTOEDIT=no

fail() { echo "FAIL: $1" >&2; exit 1; }

PY="$(command -v python3)" || fail "python3 introuvable"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || fail "python3 < 3.11 : le pilote de fusion ne s'importe pas, le banc ne prouverait rien"
[ -f "$PILOTE_SRC" ] || fail "pilote source absent : $PILOTE_SRC"

MARQUE='ALERTE pilote de fusion'
CLE='merge.cadre-enregistrement.driver'
CAS=0

# Un dépôt neuf : hooks sous test, pilote suivi, un chemin couvert, un non couvert.
depot() {
  local d="$1"
  git init -q -b main "$d" || fail "git init $d"
  git -C "$d" config user.email "banc@example.invalid"
  git -C "$d" config user.name "Banc"
  git -C "$d" config commit.gpgsign false
  mkdir -p "$d/.githooks" "$d/.agents/bin" "$d/rec"
  cp "$HERE/post-merge" "$HERE/post-commit" "$d/.githooks/"
  chmod +x "$d/.githooks/post-merge" "$d/.githooks/post-commit"
  cp "$PILOTE_SRC" "$d/.agents/bin/fusion_enregistrement.py"
  printf '/rec/*.json merge=cadre-enregistrement\n' > "$d/.gitattributes"
  printf '{"a": 1}\n' > "$d/rec/a.json"
  printf 'un\n' > "$d/autre.txt"
  git -C "$d" add -A
  git -C "$d" commit -q -m base
  git -C "$d" config core.hooksPath .githooks
}

ecrire_commit() {  # depot fichier contenu message
  printf '%s\n' "$3" > "$1/$2"
  git -C "$1" add -- "$2"
  git -C "$1" commit -q -m "$4"
}

compte() { printf '%s' "$1" | grep -c "$MARQUE"; }

POSE='import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("fe_banc", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
octets = Path(sys.argv[1]).read_bytes()
copie, _ = m._poser_copie(Path(sys.argv[2]), octets)
chemin = str(copie)
if sys.argv[3] == "antislash":
    dossier = Path(str(copie.parent.parent) + "\\" + copie.parent.name)
    dossier.mkdir(mode=0o700, exist_ok=True)
    (dossier / copie.name).write_bytes(octets)
    chemin = str(dossier) + "/" + copie.name
print(m.commande_driver(sys.executable, chemin))'

installer_pilote() {  # depot forme(normale|antislash)
  local v
  v="$("$PY" -I -B -c "$POSE" "$1/.agents/bin/fusion_enregistrement.py" "$1/.git/cadre" "$2")" \
    || fail "pose du pilote ($2)"
  git -C "$1" config --local "$CLE" "$v"
}

reussi() { CAS=$((CAS + 1)); echo "ok ::$1"; }

# Une branche b qui change le chemin couvert, main qui change l'autre.
diverger() {
  git -C "$1" checkout -q -b b
  ecrire_commit "$1" rec/a.json '{"a": 2}' "b: rec"
  git -C "$1" checkout -q main
  ecrire_commit "$1" autre.txt 'deux' "main: autre"
}

# --- ::fusion_vraie
R="$TMP/fusion_vraie"; depot "$R"; diverger "$R"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::fusion_vraie merge rc≠0 : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::fusion_vraie : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "absent" || fail "::fusion_vraie : l'alerte ne dit pas « absent » — $OUT"
printf '%s' "$OUT" | grep -Fq -- "--installer (hors de la branche par défaut : --depuis <ref relue> ;" \
  || fail "::fusion_vraie : le remède ne dit pas --depuis hors de la branche par défaut — $OUT"
[ -z "$(git -C "$R" status --porcelain)" ] || fail "::fusion_vraie : le hook a écrit dans l'arbre"
reussi fusion_vraie

# --- ::pilote_installe (contrôle positif : pilote valide, aucune alerte)
R="$TMP/pilote_installe"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::pilote_installe merge : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::pilote_installe : alerte sur un pilote valide — $OUT"
reussi pilote_installe

# --- ::fast_forward
R="$TMP/fast_forward"; depot "$R"
git -C "$R" checkout -q -b b; ecrire_commit "$R" rec/a.json '{"a": 3}' "b: rec"; git -C "$R" checkout -q main
OUT="$(git -C "$R" merge --ff-only b 2>&1)" || fail "::fast_forward merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::fast_forward : une alerte attendue — $OUT"
reussi fast_forward

# --- ::squash
R="$TMP/squash"; depot "$R"; diverger "$R"
OUT="$(git -C "$R" merge --squash b 2>&1)" || fail "::squash merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::squash : une alerte attendue au merge --squash — $OUT"
OUT="$(git -C "$R" commit -q -m squash 2>&1)" || fail "::squash commit : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::squash : le commit à un parent a re-signalé — $OUT"
reussi squash

# Un conflit sur le chemin couvert (pilote absent : fusion texte, marqueurs).
conflit() {
  git -C "$1" checkout -q -b b
  ecrire_commit "$1" rec/a.json '{"a": "b"}' "b: rec"
  git -C "$1" checkout -q main
  ecrire_commit "$1" rec/a.json '{"a": "main"}' "main: rec"
  OUT="$(git -C "$1" merge b 2>&1)" && fail "$2 : le conflit attendu n'a pas eu lieu — $OUT"
  [ "$(compte "$OUT")" -eq 0 ] || fail "$2 : post-merge a parlé sur une fusion en conflit — $OUT"
  printf '{"a": "fusion"}\n' > "$1/rec/a.json"
  git -C "$1" add rec/a.json
}

# --- ::conflit_commit
R="$TMP/conflit_commit"; depot "$R"; conflit "$R" "::conflit_commit"
OUT="$(git -C "$R" commit --no-edit 2>&1)" || fail "::conflit_commit commit : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::conflit_commit : UNE alerte attendue (post-commit) — $OUT"
reussi conflit_commit

# --- ::conflit_continue
R="$TMP/conflit_continue"; depot "$R"; conflit "$R" "::conflit_continue"
OUT="$(git -C "$R" merge --continue 2>&1)" || fail "::conflit_continue : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::conflit_continue : UNE alerte attendue (post-commit) — $OUT"
reussi conflit_continue

# --- ::cherry_pick_rebase (silence BORNÉ : commits à un parent)
R="$TMP/cherry_pick_rebase"; depot "$R"; diverger "$R"
OUT="$(git -C "$R" cherry-pick b 2>&1)" || fail "::cherry_pick_rebase cherry-pick : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::cherry_pick_rebase : cherry-pick signalé (borne écrite : non signalé) — $OUT"
git -C "$R" checkout -q -b c 'main~2'
ecrire_commit "$R" rec/a.json '{"a": "c"}' "c: rec"
OUT="$(git -C "$R" rebase -X theirs main 2>&1)" || fail "::cherry_pick_rebase rebase : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::cherry_pick_rebase : rebase signalé (borne écrite : non signalé) — $OUT"
reussi cherry_pick_rebase

# --- ::revert (silence BORNÉ et écrit en tête : un revert est un commit à un parent)
R="$TMP/revert"; depot "$R"
ecrire_commit "$R" rec/a.json '{"a": "x"}' "X: rec"
ecrire_commit "$R" autre.txt 'y' "Y: autre"
OUT="$(git -C "$R" revert --no-edit 'HEAD~1' 2>&1)" || fail "::revert revert : $OUT"
[ "$(git -C "$R" show --format= --name-only HEAD)" = "rec/a.json" ] || fail "::revert : le revert ne touche pas le chemin couvert"
[ "$(compte "$OUT")" -eq 0 ] || fail "::revert : revert signalé (borne écrite : non signalé) — $OUT"
grep -q 'revert (mesuré' "$HERE/post-merge" || fail "::revert : la borne « revert » n'est pas écrite en tête de post-merge"
reussi revert

# --- ::amend_fusion (borne écrite : l'amend d'une fusion est RE-signalé, une alerte en plus)
R="$TMP/amend_fusion"; depot "$R"; diverger "$R"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::amend_fusion merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::amend_fusion : une alerte attendue à la fusion — $OUT"
OUT="$(git -C "$R" commit --amend --no-edit 2>&1)" || fail "::amend_fusion amend : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::amend_fusion : l'amend d'une fusion n'est pas re-signalé (borne écrite) — $OUT"
reussi amend_fusion

# --- ::hors_couverts
R="$TMP/hors_couverts"; depot "$R"
git -C "$R" checkout -q -b b; ecrire_commit "$R" autre.txt 'b' "b: autre"; git -C "$R" checkout -q main
ecrire_commit "$R" t.txt 't' "main: t"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::hors_couverts merge : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::hors_couverts : alerte sans chemin couvert — $OUT"
reussi hors_couverts

# --- ::sans_hookspath (hooks posés dans .git/hooks, core.hooksPath absent : silence)
R="$TMP/sans_hookspath"; depot "$R"; diverger "$R"
git -C "$R" config --unset core.hooksPath
mkdir -p "$R/.git/hooks"
cp "$R/.githooks/post-merge" "$R/.githooks/post-commit" "$R/.git/hooks/"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::sans_hookspath merge : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::sans_hookspath : alerte sans core.hooksPath — $OUT"
reussi sans_hookspath

# --- ::worktree_autre_arbre (hooksPath absolu vers l'arbre principal ; pilote NON installé)
R="$TMP/worktree_autre_arbre"; depot "$R"
git -C "$R" config core.hooksPath "$R/.githooks"
git -C "$R" checkout -q -b b; ecrire_commit "$R" rec/a.json '{"a": "wt"}' "b: rec"; git -C "$R" checkout -q main
git -C "$R" worktree add -q -b w "$TMP/wt" main 2>/dev/null || fail "::worktree_autre_arbre worktree add"
ecrire_commit "$TMP/wt" t.txt 'w' "w: t"
OUT="$(git -C "$TMP/wt" merge --no-ff -m fusion b 2>&1)" || fail "::worktree_autre_arbre merge : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::worktree_autre_arbre : alerte depuis un autre arbre — $OUT"
reussi worktree_autre_arbre

# --- ::hookspath_symlien (actif : même dossier atteint par un lien symbolique)
R="$TMP/hookspath_symlien"; depot "$R"; diverger "$R"
ln -s "$R" "$TMP/lien" || fail "::hookspath_symlien ln -s"
git -C "$R" config core.hooksPath "$TMP/lien/.githooks"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::hookspath_symlien merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::hookspath_symlien : une alerte attendue — $OUT"
reussi hookspath_symlien

# --- ::copie_antislash (copie entre apostrophes, séparateur `\` : normalisée, aucune alerte)
R="$TMP/copie_antislash"; depot "$R"; installer_pilote "$R" antislash; diverger "$R"
case "$(git -C "$R" config --local --get "$CLE")" in
  *"\\cadre/"*) ;;
  *) fail "::copie_antislash : la valeur posée ne porte pas de séparateur antislash" ;;
esac
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::copie_antislash merge : $OUT"
[ "$(compte "$OUT")" -eq 0 ] || fail "::copie_antislash : alerte sur une copie valide à antislash — $OUT"
reussi copie_antislash

# --- ::copie_absente
R="$TMP/copie_absente"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
rm -f "$R"/.git/cadre/fusion_enregistrement-*.py
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::copie_absente merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::copie_absente : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "copie absente" || fail "::copie_absente : l'alerte ne dit pas « copie absente » — $OUT"
rm -rf "$R/.git/cadre"  # dossier entier supprimé : même mot que `--verifier`
OUT="$( cd "$R" && bash .githooks/post-merge 0 2>&1 )"
[ "$(compte "$OUT")" -eq 1 ] || fail "::copie_absente (.git/cadre supprimé) : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "copie absente" || fail "::copie_absente (.git/cadre supprimé) : l'alerte ne dit pas « copie absente » — $OUT"
reussi copie_absente

# --- ::copie_symlien (copie remplacée par un lien : jamais suivi, jamais exécuté)
R="$TMP/copie_symlien"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
printf 'import pathlib\npathlib.Path(%s).touch()\n' "'$TMP/S2'" > "$TMP/cible_lien.py"
for f in "$R"/.git/cadre/fusion_enregistrement-*.py; do
  chmod u+w "$f"; rm -f "$f"; ln -s "$TMP/cible_lien.py" "$f"
done
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::copie_symlien merge : $OUT"
[ ! -e "$TMP/S2" ] || fail "::copie_symlien : la cible du lien a été EXÉCUTÉE ($TMP/S2 existe)"
[ "$(compte "$OUT")" -eq 1 ] || fail "::copie_symlien : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "lien symbolique" || fail "::copie_symlien : l'alerte ne nomme pas le lien — $OUT"
printf '%s' "$OUT" | grep -q "supprimer le lien d'abord" || fail "::copie_symlien : l'alerte ne dit pas le geste — $OUT"
reussi copie_symlien

# --- ::nom_echappement (nom couvert portant ESC et CR : jamais affichés bruts dans l'alerte)
R="$TMP/nom_echappement"; depot "$R"
ESC="$(printf '\033')"
CR="$(printf '\r')"
git -C "$R" checkout -q -b b; ecrire_commit "$R" "rec/e${ESC}x${CR}y.json" '{"e": 1}' "b: rec esc"; git -C "$R" checkout -q main
ecrire_commit "$R" t.txt 't' "main: t"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::nom_echappement merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::nom_echappement : une alerte attendue — $OUT"
LIGNE="$(printf '%s' "$OUT" | grep "$MARQUE")"
case "$LIGNE" in
  *"$ESC"*) fail "::nom_echappement : l'alerte affiche un octet ESC brut" ;;
  *"$CR"*) fail "::nom_echappement : l'alerte affiche un octet CR brut" ;;
  *"rec/exy.json"*) ;;
  *) fail "::nom_echappement : l'alerte ne cite pas le nom nettoyé — $LIGNE" ;;
esac
reussi nom_echappement

# --- ::alerte_controle (copie de la config portant ESC : le motif de l'alerte est filtré aussi)
R="$TMP/alerte_controle"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
V="$(git -C "$R" config --local --get "$CLE")"
V_PY="${V%% -I -B *}"
V_APRES="${V#* -I -B }"
git -C "$R" config --local "$CLE" "$V_PY -I -B '$TMP/e${ESC}x.py' ${V_APRES#* }"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::alerte_controle merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::alerte_controle : une alerte attendue — $OUT"
LIGNE="$(printf '%s' "$OUT" | grep "$MARQUE")"
case "$LIGNE" in
  *"$ESC"*) fail "::alerte_controle : l'alerte affiche un octet ESC brut venu de la config" ;;
  *"copie absente"*"$TMP/ex.py"*) ;;
  *) fail "::alerte_controle : l'alerte ne cite pas la copie nettoyée — $LIGNE" ;;
esac
reussi alerte_controle

# --- ::cdpath_exporte (CDPATH exporté pendant la fusion : le hook parle quand même)
R="$TMP/cdpath_exporte"; depot "$R"; diverger "$R"
OUT="$(CDPATH=".:$HOME" git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::cdpath_exporte merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::cdpath_exporte : une alerte attendue sous CDPATH exporté — $OUT"
reussi cdpath_exporte

# --- ::rebase_r (borne écrite : fusion recréée sans conflit muette à l'écran, après conflit signalée)
R="$TMP/rebase_r"; depot "$R"
# Le stderr du hook, que git avale pendant le rebase, est JOURNALISÉ dans un fichier :
# il prouve que post-commit a tourné sur la fusion recréée (K12). L'enveloppe est
# COMMITÉE avant la divergence : un arbre sale bloquerait le rebase.
cp "$R/.githooks/post-commit" "$R/.githooks/post-commit.reel"
printf '%s\n' '#!/usr/bin/env bash' 'bash "$(dirname -- "$0")/post-commit.reel" 2>> "${RR_LOG:-/dev/null}"' > "$R/.githooks/post-commit"
git -C "$R" add -A .githooks; git -C "$R" commit -q -m "banc: post-commit journalisé"
diverger "$R"
git -C "$R" merge -q --no-ff -m fusion b >/dev/null 2>&1 || fail "::rebase_r fusion initiale"
git -C "$R" checkout -q -b n 'main~2'; ecrire_commit "$R" t.txt 'n' "n: t"; git -C "$R" checkout -q main
: > "$TMP/rr.log"
OUT="$(RR_LOG="$TMP/rr.log" git -C "$R" rebase -r n 2>&1)" || fail "::rebase_r rebase -r sans conflit : $OUT"
[ "$(git -C "$R" rev-list --merges --count n..HEAD)" -eq 1 ] || fail "::rebase_r : la fusion n'a pas été recréée"
[ "$(compte "$OUT")" -eq 0 ] || fail "::rebase_r sans conflit : alerte affichée (borne écrite : non signalée à l'écran) — $OUT"
[ "$(compte "$(cat "$TMP/rr.log")")" -eq 1 ] || fail "::rebase_r sans conflit : post-commit n'a pas alerté au journal — $(cat "$TMP/rr.log")"
R="$TMP/rebase_r_conflit"; depot "$R"; conflit "$R" "::rebase_r_conflit"
git -C "$R" commit -q --no-edit >/dev/null 2>&1 || fail "::rebase_r_conflit commit de la fusion"
git -C "$R" checkout -q -b n 'main~2'; ecrire_commit "$R" t.txt 'n' "n: t"; git -C "$R" checkout -q main
OUT="$(git -C "$R" rebase -r n 2>&1)" && fail "::rebase_r_conflit : le conflit attendu à la recréation n'a pas eu lieu — $OUT"
printf '{"a": "fusion"}\n' > "$R/rec/a.json"
git -C "$R" add rec/a.json
OUT="$(git -C "$R" rebase --continue 2>&1)" || fail "::rebase_r_conflit rebase --continue : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::rebase_r_conflit : UNE alerte attendue après --continue — $OUT"
reussi rebase_r

# --- ::copie_alteree (la forme passe, c'est verifier(racine) de la copie qui dit « altérée »)
R="$TMP/copie_alteree"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
for f in "$R"/.git/cadre/fusion_enregistrement-*.py; do
  chmod u+w "$f"; printf '# altere\n' >> "$f"
done
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::copie_alteree merge : $OUT"
[ "$(compte "$OUT")" -eq 1 ] || fail "::copie_alteree : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "altérée" || fail "::copie_alteree : l'alerte ne relaie pas le verdict « altérée » — $OUT"
reussi copie_alteree

# --- ::driver_injecte (`$(touch S)` dans la valeur : jamais exécuté, alerte « forme inconnue »)
R="$TMP/driver_injecte"; depot "$R"; installer_pilote "$R" normale; diverger "$R"
V="$(git -C "$R" config --local --get "$CLE")"
git -C "$R" config --local "$CLE" "\$(touch $TMP/S) ${V#* }"
OUT="$(git -C "$R" merge --no-ff -m fusion b 2>&1)" || fail "::driver_injecte merge : $OUT"
[ ! -e "$TMP/S" ] || fail "::driver_injecte : la valeur driver a été EXÉCUTÉE ($TMP/S existe)"
[ "$(compte "$OUT")" -eq 1 ] || fail "::driver_injecte : une alerte attendue — $OUT"
printf '%s' "$OUT" | grep -q "forme inconnue" || fail "::driver_injecte : l'alerte ne dit pas « forme inconnue » — $OUT"
( cd "$R" && bash .githooks/post-merge 0 >/dev/null 2>&1 ); RC=$?
[ "$RC" -eq 0 ] || fail "::driver_injecte : le hook ne rend pas 0 (rc=$RC)"
[ ! -e "$TMP/S" ] || fail "::driver_injecte : exécuté à l'appel direct"
reussi driver_injecte

# --- ::mode_100755 (git ignore en silence un hook non exécutable)
for h in post-merge post-commit; do
  L="$(git -C "$KIT" ls-files -s -- ".githooks/$h")"
  case "$L" in
    "100755 "*) ;;
    *) fail "::mode_100755 : .githooks/$h n'est pas 100755 à l'index — « $L »" ;;
  esac
done
reussi mode_100755

[ "$CAS" -eq 23 ] || fail "$CAS cas joués sur 23 attendus"
echo "PASS: post-merge ($CAS/23)"
