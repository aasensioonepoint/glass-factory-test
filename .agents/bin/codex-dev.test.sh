#!/usr/bin/env bash
# Banc de codex-dev.sh (T-01M5PTFPBDBXE3KMZNHP5DE31A, lot A). Run: bash .agents/bin/codex-dev.test.sh
# requires: git
#
# Depot jetable (mktemp -d), worktrees reels, `codex` STUB en tete de PATH qui consigne argv, stdin et env.
# Nominal = argv exact. Chaque refus asserte : rc 3, `codex-dev: REFUS — ` sur stderr, stub NON appele, PWNED absent.
set -uo pipefail
for _v in $(compgen -e); do
  case "$_v" in
    GIT_*) unset "$_v" ;;
  esac
done
HERE="$(cd "$(dirname "$0")" && pwd)"
LANCEUR="$HERE/codex-dev.sh"
command -v git >/dev/null 2>&1 || { echo "SKIP: no git"; exit 0; }

TMP="$(mktemp -d)"
V=""
trap 'rm -rf "$TMP"; [ -z "$V" ] || rm -rf "$V"' EXIT
TMP="$(cd -P "$TMP" && pwd -P)"
R="$TMP/repo"
STUB="$TMP/stub"
OUT="$TMP/out"
mkdir -p "$R/.agents/bin" "$R/.codex/agents" "$STUB" "$OUT"

fail() {
  echo "FAIL: $1"
  [ -f "$OUT/e" ] && sed 's/^/  stderr: /' "$OUT/e"
  exit 1
}
N=0
ok() {
  N=$((N + 1))
}

# Le stub consigne argv (un par ligne), stdin et env dans $OUT.
printf '%s\n' '#!/usr/bin/env bash' \
  "printf '%s\\n' \"\$@\" > '$OUT/argv'" \
  "cat > '$OUT/stdin'" \
  "env > '$OUT/env'" > "$STUB/codex"
chmod +x "$STUB/codex"

cp "$LANCEUR" "$R/.agents/bin/codex-dev.sh"
printf '{"hooks":{}}\n' > "$R/.codex/hooks.json"
printf 'name = "a"\n' > "$R/.codex/agents/a.toml"
printf '.codex/agents/x.toml\n.claude/worktrees/\n' > "$R/.gitignore"
git -C "$R" init -q
git -C "$R" config user.email t@t
git -C "$R" config user.name t
git -C "$R" add -A
git -C "$R" commit -qm init
for _w in w1 wh wi wc ws wa wr wg wn; do
  git -C "$R" worktree add -q -b "$_w" "$R/.claude/worktrees/$_w"
done
M="$TMP/mandat.md"
printf 'mandat du dev\nligne 2\n' > "$M"

# run_l <cwd> <args…> : lance `bash .agents/bin/codex-dev.sh` depuis <cwd>, stub en tete de PATH.
RC=0
run_l() {
  local _cwd="$1"
  shift
  rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env" "$OUT/o" "$OUT/e"
  (cd "$_cwd" && PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh "$@") > "$OUT/o" 2> "$OUT/e"
  RC=$?
}
sans_pwned() {
  [ -z "$(find "$TMP" -name PWNED -print)" ] || fail "$1 : PWNED cree"
}
# refus <nom> <cause attendue> <args…> : la CAUSE est assertee, pour qu'un controle ne couvre jamais un autre.
refus() {
  local _nom="$1"
  local _cause="$2"
  shift 2
  run_l "$R" "$@"
  verifie_refus "$_nom" "$_cause"
}
verifie_refus() {
  [ "$RC" -eq 3 ] || fail "$1 : rc $RC, attendu 3"
  grep -q '^codex-dev: REFUS — ' "$OUT/e" || fail "$1 : ligne de refus absente"
  grep -qF -- "$2" "$OUT/e" || fail "$1 : cause attendue « $2 » absente"
  [ ! -e "$OUT/argv" ] || fail "$1 : stub appele"
  sans_pwned "$1"
  ok
}

W1="$R/.claude/worktrees/w1"
NOM=(--worktree w1 --model gpt-5.5 --mandat "$M")

# --- nominaux ---
run_l "$R" --worktree w1 --model gpt-5.5 --effort high --mandat "$M"
[ "$RC" -eq 0 ] || fail "nominal : rc $RC"
printf '%s\n' exec -C "$W1" -s workspace-write -c sandbox_workspace_write.network_access=false \
  -c 'sandbox_workspace_write.writable_roots=[]' -m gpt-5.5 -c 'model_reasoning_effort="high"' - > "$OUT/attendu"
cmp -s "$OUT/attendu" "$OUT/argv" || fail "nominal : argv inexact"
cmp -s "$M" "$OUT/stdin" || fail "nominal : stdin different du mandat"
ok

run_l "$R" "${NOM[@]}"
[ "$RC" -eq 0 ] || fail "nominal sans effort : rc $RC"
printf '%s\n' exec -C "$W1" -s workspace-write -c sandbox_workspace_write.network_access=false \
  -c 'sandbox_workspace_write.writable_roots=[]' -m gpt-5.5 - > "$OUT/attendu"
cmp -s "$OUT/attendu" "$OUT/argv" || fail "nominal sans effort : argv inexact"
ok

(cd "$R" && GIT_DIR="$TMP/nulle" GIT_WORK_TREE="$TMP" CODEX_HOME="$TMP/ch" CDPATH="$TMP" ENV="$TMP/e.sh" \
  PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh "${NOM[@]}") > "$OUT/o" 2> "$OUT/e"
RC=$?
[ "$RC" -eq 0 ] || fail "env hostile : rc $RC"
cmp -s "$OUT/attendu" "$OUT/argv" || fail "env hostile : argv inexact"
! grep -qE '^(GIT_[A-Za-z0-9_]*|CODEX_HOME|ENV|CDPATH|BASH_ENV)=' "$OUT/env" || fail "env hostile : variable transmise au stub"
ok

run_l "$R" "${NOM[@]}" --dry-run
[ "$RC" -eq 0 ] || fail "dry-run : rc $RC"
[ ! -e "$OUT/argv" ] || fail "dry-run : stub appele"
grep -q "^codex exec -C .*-s workspace-write .*-m gpt-5.5 - < " "$OUT/o" || fail "dry-run : argv non imprime"
ok

run_l "$R" --help
[ "$RC" -eq 0 ] || fail "help : rc $RC"
[ ! -e "$OUT/argv" ] || fail "help : stub appele"
grep -q '^usage: ' "$OUT/o" || fail "help : usage absent"
ok

# --- refus de grammaire (etape 3) ---
HG="argument hors grammaire"
DBL="option en double"
refus "aucun argument" "aucun argument"
refus "-s" "$HG : -s" "${NOM[@]}" -s danger-full-access
refus "-c" "$HG : -c" "${NOM[@]}" -c x=y
refus "--add-dir" "$HG : --add-dir" "${NOM[@]}" --add-dir /
refus "--dangerously" "$HG : --dangerously" "${NOM[@]}" --dangerously-bypass-approvals-and-sandbox
refus "-C" "$HG : -C" "${NOM[@]}" -C /
refus "-p" "$HG : -p" "${NOM[@]}" -p profil
refus "--" "$HG : --" "${NOM[@]}" --
refus "--x=y" "$HG : --model=gpt-5.5" --worktree w1 --model=gpt-5.5 --mandat "$M"
refus "doublon --worktree" "$DBL : --worktree" "${NOM[@]}" --worktree w1
refus "doublon --model" "$DBL : --model" "${NOM[@]}" --model autre
refus "doublon --effort" "$DBL : --effort" "${NOM[@]}" --effort low --effort high
refus "doublon --mandat" "$DBL : --mandat" "${NOM[@]}" --mandat "$M"
refus "doublon --dry-run" "$DBL : --dry-run" "${NOM[@]}" --dry-run --dry-run
refus "positionnel" "$HG : extra" "${NOM[@]}" extra
refus "--model en dernier" "valeur manquante pour --model" --worktree w1 --mandat "$M" --model
refus "--worktree --model x" "valeur de --worktree commencant par" --worktree --model x --mandat "$M"
refus "--help --dry-run" "--help se joue seul" --help --dry-run
refus "--help combine" "--help se joue seul" "${NOM[@]}" --help
refus "valeur vide" "valeur vide pour --worktree" --worktree "" --model gpt-5.5 --mandat "$M"
refus "effort hors liste" "--effort hors liste" "${NOM[@]}" --effort extreme
refus "--worktree manquant" "--worktree manquant" --model gpt-5.5 --mandat "$M"
refus "--model manquant" "--model manquant" --worktree w1 --mandat "$M"
refus "--mandat manquant" "--mandat manquant" --worktree w1 --model gpt-5.5

# --- refus de motif et de cible (etape 4) ---
refus "worktree .." "nom de worktree hors motif" --worktree ../w1 --model gpt-5.5 --mandat "$M"
refus "worktree a..b" "nom de worktree avec" --worktree a..b --model gpt-5.5 --mandat "$M"
refus "worktree .cache" "nom de worktree hors motif" --worktree .cache --model gpt-5.5 --mandat "$M"
refus "worktree avec /" "nom de worktree hors motif" --worktree w1/x --model gpt-5.5 --mandat "$M"
refus "model .." "modele avec" --worktree w1 --model gpt..5 --mandat "$M"
refus "worktree x\$(touch PWNED)" "nom de worktree hors motif" --worktree 'x$(touch PWNED)' --model gpt-5.5 --mandat "$M"
refus "model x\$(touch PWNED)" "modele hors motif" --worktree w1 --model 'x$(touch PWNED)' --mandat "$M"
refus "mandat x\$(touch PWNED)" "mandat absent" --worktree w1 --model gpt-5.5 --mandat 'x$(touch PWNED)'
refus "worktree absent" "worktree absent" --worktree absent --model gpt-5.5 --mandat "$M"
refus "mandat absent" "mandat absent" --worktree w1 --model gpt-5.5 --mandat "$TMP/absent.md"
mkdir -p "$TMP/mandat-rep"
refus "mandat repertoire" "pas un fichier regulier" --worktree w1 --model gpt-5.5 --mandat "$TMP/mandat-rep"
ln -s "$M" "$TMP/mandat-lien.md"
refus "mandat lien" "le mandat est un lien" --worktree w1 --model gpt-5.5 --mandat "$TMP/mandat-lien.md"

# Mandat hors des zones admises : un fichier systeme, atteint en direct, par `..`, ou par un repertoire en lien.
HZ="mandat hors des zones admises"
if [ -f /etc/hosts ] && [ -r /etc/hosts ]; then
  refus "mandat /etc/hosts" "$HZ" --worktree w1 --model gpt-5.5 --mandat /etc/hosts
  refus "mandat par .." "$HZ" --worktree w1 --model gpt-5.5 --mandat "$TMP/../../../../../../../../etc/hosts"
  ln -s /etc "$TMP/etc-lien"
  refus "mandat sous un repertoire lien" "$HZ" --worktree w1 --model gpt-5.5 --mandat "$TMP/etc-lien/hosts"
else
  echo "SKIP-BRAS: /etc/hosts absent ou illisible — bras « mandat hors zone » non joues"
fi
# Mandat sous <racine>/docs/tasks/, $TMPDIR ecarte : admis par la zone docs/tasks (seule, hors /tmp sur macOS).
mkdir -p "$R/docs/tasks" "$TMP/tmpdir-vide"
printf 'mandat docs/tasks\n' > "$R/docs/tasks/m.md"
rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
(cd "$R" && TMPDIR="$TMP/tmpdir-vide" PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh --worktree w1 --model gpt-5.5 \
  --mandat "$R/docs/tasks/m.md") > "$OUT/o" 2> "$OUT/e"
RC=$?
[ "$RC" -eq 0 ] || fail "mandat sous docs/tasks : rc $RC"
cmp -s "$R/docs/tasks/m.md" "$OUT/stdin" || fail "mandat sous docs/tasks : stdin different"
ok
case "$R" in
  /tmp/*|/private/tmp/*) : ;;
  *)
    printf 'hors zone\n' > "$R/hors.md"
    rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
    (cd "$R" && TMPDIR="$TMP/tmpdir-vide" PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh --worktree w1 --model gpt-5.5 \
      --mandat "$R/hors.md") > "$OUT/o" 2> "$OUT/e"
    RC=$?
    verifie_refus "mandat a la racine, TMPDIR ecarte" "$HZ"
    ;;
esac
# Meme paire hors de /tmp (sous Linux $R y est, et le bras hors zone ci-dessus est saute) : clone sous /var/tmp.
if V="$(mktemp -d /var/tmp/codex-dev-test.XXXXXX 2>/dev/null)"; then
  V="$(cd -P "$V" && pwd -P)"
  RV="$V/repo"
  git clone -q "$R" "$RV"
  git -C "$RV" worktree add -q -b wv "$RV/.claude/worktrees/wv"
  mkdir -p "$RV/docs/tasks" "$V/tmpdir-vide"
  printf 'mandat docs/tasks hors /tmp\n' > "$RV/docs/tasks/m.md"
  rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
  (cd "$RV" && TMPDIR="$V/tmpdir-vide" PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh --worktree wv --model gpt-5.5 \
    --mandat "$RV/docs/tasks/m.md") > "$OUT/o" 2> "$OUT/e"
  RC=$?
  [ "$RC" -eq 0 ] || fail "mandat sous docs/tasks hors /tmp : rc $RC"
  cmp -s "$RV/docs/tasks/m.md" "$OUT/stdin" || fail "mandat sous docs/tasks hors /tmp : stdin different"
  ok
  printf 'hors zone\n' > "$RV/hors.md"
  rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
  (cd "$RV" && TMPDIR="$V/tmpdir-vide" PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh --worktree wv --model gpt-5.5 \
    --mandat "$RV/hors.md") > "$OUT/o" 2> "$OUT/e"
  RC=$?
  verifie_refus "mandat a la racine hors /tmp, TMPDIR ecarte" "$HZ"
else
  V=""
  echo "SKIP-BRAS: /var/tmp non inscriptible — bras « zone hors /tmp » non joues"
fi

# Fonctions exportees (BASH_FUNC_git%%, BASH_FUNC_dirname%%) : jamais prises par le lanceur.
rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
(
  PWNED_AT="$TMP/PWNED"
  export PWNED_AT
  git() {
    : > "$PWNED_AT"
    command git "$@"
  }
  dirname() {
    : > "$PWNED_AT"
    command dirname "$@"
  }
  export -f git dirname
  cd "$R" && PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh "${NOM[@]}"
) > "$OUT/o" 2> "$OUT/e"
RC=$?
[ "$RC" -eq 0 ] || fail "fonction exportee git : rc $RC"
cmp -s "$OUT/attendu" "$OUT/argv" || fail "fonction exportee git : argv inexact"
sans_pwned "fonction exportee git"
ok

# Fonction exportee `read` qui rend 1 : la boucle des marqueurs sortirait sans lire, l'ecart skip-worktree passerait.
WR="$R/.claude/worktrees/wr"
printf '{"hooks":{"r":1}}\n' > "$WR/.codex/hooks.json"
git -C "$WR" update-index --skip-worktree .codex/hooks.json
rm -f "$OUT/argv" "$OUT/stdin" "$OUT/env"
(
  PWNED_AT="$TMP/PWNED"
  export PWNED_AT
  read() {
    : > "$PWNED_AT"
    return 1
  }
  export -f read
  cd "$R" && PATH="$STUB:$PATH" bash .agents/bin/codex-dev.sh --worktree wr --model gpt-5.5 --mandat "$M"
) > "$OUT/o" 2> "$OUT/e"
RC=$?
verifie_refus "fonction exportee read" "skip-worktree ou assume-unchanged"

ln -s "$W1" "$R/.claude/worktrees/lien"
refus "worktree lien" "la cible est un lien" --worktree lien --model gpt-5.5 --mandat "$M"
mkdir -p "$R/.claude/worktrees/plat"
refus "dossier plat" "pas la racine d'un worktree" --worktree plat --model gpt-5.5 --mandat "$M"

O="$TMP/autre"
mkdir -p "$O"
git -C "$O" init -q
git -C "$O" config user.email t@t
git -C "$O" config user.name t
printf 'x\n' > "$O/f"
git -C "$O" add f
git -C "$O" commit -qm init
git -C "$O" worktree add -q -b etranger "$R/.claude/worktrees/etranger"
refus "worktree etranger" "common-dir different" --worktree etranger --model gpt-5.5 --mandat "$M"

git clone -q "$R" "$R/.claude/worktrees/imbrique"
refus "clone imbrique" "pas un worktree lie" --worktree imbrique --model gpt-5.5 --mandat "$M"

# Lanceur copie dans un worktree, lance depuis ce worktree : racine non principale.
run_l "$W1" "${NOM[@]}"
verifie_refus "lanceur copie dans un worktree" "racine non principale"
# Meme copie, cible = un vrai worktree de la racine niche sous ce worktree : common-dir identique a celui de la
# racine, git-dir different — seul le controle « racine principale » le refuse.
git -C "$R" worktree add -q -b wx "$W1/.claude/worktrees/wx"
run_l "$W1" --worktree wx --model gpt-5.5 --mandat "$M"
verifie_refus "lanceur copie, cible worktree de la racine" "racine non principale"

# Lanceur copie hors de la racine de son depot (sous-dossier) : refuse.
mkdir -p "$R/sous/.agents/bin"
cp "$LANCEUR" "$R/sous/.agents/bin/codex-dev.sh"
run_l "$R/sous" "${NOM[@]}"
verifie_refus "lanceur dans un sous-dossier" "pas a la racine de son depot"

# Parent de la cible en lien (.claude/worktrees -> ailleurs) : chemin reel different, refuse.
R2="$TMP/repo2"
mkdir -p "$R2/.agents/bin" "$R2/.claude" "$TMP/ailleurs"
cp "$LANCEUR" "$R2/.agents/bin/codex-dev.sh"
git -C "$R2" init -q
git -C "$R2" config user.email t@t
git -C "$R2" config user.name t
git -C "$R2" add .agents
git -C "$R2" commit -qm init
ln -s "$TMP/ailleurs" "$R2/.claude/worktrees"
git -C "$R2" worktree add -q -b w "$TMP/ailleurs/w"
run_l "$R2" --worktree w --model gpt-5.5 --mandat "$M"
verifie_refus "parent de la cible en lien" "chemin reel de la cible"

printf '{"hooks":{"x":1}}\n' > "$R/.claude/worktrees/wh/.codex/hooks.json"
refus ".codex/hooks.json modifie" ".codex/ de la cible differe" --worktree wh --model gpt-5.5 --mandat "$M"

printf 'name = "x"\n' > "$R/.claude/worktrees/wi/.codex/agents/x.toml"
git -C "$R/.claude/worktrees/wi" check-ignore -q .codex/agents/x.toml || fail "preparation : x.toml non ignore"
refus ".codex/agents/x.toml non suivi ignore" "non suivis (ignores compris), dont .codex/agents/x.toml — remede" --worktree wi --model gpt-5.5 --mandat "$M"

printf '{"hooks":{"y":1}}\n' > "$R/.claude/worktrees/wc/.codex/hooks.json"
git -C "$R/.claude/worktrees/wc" commit -qam "codex modifie"
[ -z "$(git -C "$R/.claude/worktrees/wc" status --porcelain)" ] || fail "preparation : wc non propre"
refus ".codex modifie commite dans le worktree" ".codex/ de la cible differe" --worktree wc --model gpt-5.5 --mandat "$M"

# skip-worktree / assume-unchanged : l'ecart serait invisible au diff, le marqueur le refuse.
printf '{"hooks":{"s":1}}\n' > "$R/.claude/worktrees/ws/.codex/hooks.json"
git -C "$R/.claude/worktrees/ws" update-index --skip-worktree .codex/hooks.json
git -C "$R/.claude/worktrees/ws" diff --quiet HEAD -- .codex || fail "preparation : skip-worktree visible au diff"
refus ".codex skip-worktree" "skip-worktree ou assume-unchanged" --worktree ws --model gpt-5.5 --mandat "$M"
printf '{"hooks":{"a":1}}\n' > "$R/.claude/worktrees/wa/.codex/hooks.json"
git -C "$R/.claude/worktrees/wa" update-index --assume-unchanged .codex/hooks.json
git -C "$R/.claude/worktrees/wa" diff --quiet HEAD -- .codex || fail "preparation : assume-unchanged visible au diff"
refus ".codex assume-unchanged" "skip-worktree ou assume-unchanged" --worktree wa --model gpt-5.5 --mandat "$M"

# git-dir deplace dans le worktree (copie de <common-dir>/worktrees/wg) : son index, forgeable, masquerait l'ecart.
WG="$R/.claude/worktrees/wg"
cp -R "$R/.git/worktrees/wg" "$WG/.gitdir-local"
printf '%s\n' "$R/.git" > "$WG/.gitdir-local/commondir"
printf 'gitdir: %s\n' "$WG/.gitdir-local" > "$WG/.git"
[ "$(git -C "$WG" rev-parse --path-format=absolute --git-dir)" = "$WG/.gitdir-local" ] || fail "preparation : git-dir de wg non deplace"
refus "git-dir dans le worktree" "git-dir de la cible hors de" --worktree wg --model gpt-5.5 --mandat "$M"
# git-dir niche SOUS un autre <common-dir>/worktrees/<id> : prefixe admis, profondeur refusee.
WN="$R/.claude/worktrees/wn"
cp -R "$R/.git/worktrees/wn" "$R/.git/worktrees/wg/niche"
printf '%s\n' "$R/.git" > "$R/.git/worktrees/wg/niche/commondir"
printf 'gitdir: %s\n' "$R/.git/worktrees/wg/niche" > "$WN/.git"
[ "$(git -C "$WN" rev-parse --path-format=absolute --git-dir)" = "$R/.git/worktrees/wg/niche" ] || fail "preparation : git-dir de wn non niche"
refus "git-dir niche sous worktrees/<id>" "git-dir de la cible hors de" --worktree wn --model gpt-5.5 --mandat "$M"

# Temoin positif apres tous les refus : w1 reste admis (aucun refus par effet de bord).
run_l "$R" "${NOM[@]}"
[ "$RC" -eq 0 ] || fail "nominal final : rc $RC"
ok

sans_pwned "fin"
echo "PASS: codex-dev ($N cas)"
