#!/usr/bin/env bash
# ============================================================================
# LE BANC DE core-scripts/doctor.sh (T-00001001, BK-343) — peut-il encore rougir ?
#
# Le suffixe `.test.sh` EST l'inscription : core-scripts/run-bash-tests.sh le
# découvre, et ce runner est une étape de la CI et de core-scripts/verify.sh.
# Aucune entrée de manifeste n'est nécessaire.
#
# CE QUE CHAQUE CAS TIENT (critères d'acceptation de T-00001001) :
#   critère 1 — le doctor liste chaque outil manquant avec sa version attendue,
#               lues dans l'inventaire, sans liste codée en dur : cas 13 (grep
#               du code de doctor.sh) et cas 14 (une ligne ABSENT par outil,
#               avec la version de la colonne `version`) ;
#   critère 3 — l'en-tête de doctor.sh borne son périmètre et renvoie à
#               `cadre doctor` : cas 15 ;
#   le reste suit le plan T-00000529 (volet b) : cas 1-7, 10-12, plus le cas 16
#   (mauvaise version, qui ne change jamais le code de retour ; version non
#   mesurée, rc de `--version` rapporté ; version rapportée sans caractère de
#   contrôle, contrainte `>=` ou textuelle), le cas 17 (la sonde ne résout ni
#   builtin, ni mot-clé, ni fonction, ni fichier non exécutable seul), le
#   cas 18 (DOCTOR_PROBE_PATH non posé : la sonde lit le PATH de l'appelant),
#   le cas 19 (mode de sonde `module:` : un binaire du même nom ne prouve rien ;
#   son vocabulaire est tenu au cas 4) et le cas 20 (mode `module:` : un
#   interpréteur qui ne répond pas à `--version` est sauté, comme la porte le
#   saute), et le cas 21 (T-01M5VYNMZPG8G0JZG48HV4K0PN : `doctor: modules` et
#   `doctor: hors classe B ici`, sur un arbre copié SANS marqueur du kit).
#
# ADOPTER-SAFE. Ce banc VOYAGE (polarité TAKE de core-scripts/). Il ne lit que
# des fichiers qui voyagent avec lui — doctor.sh, l'inventaire,
# check-ci-parity.sh — et n'asserte RIEN sur le ci.yml ni le verify.sh réels :
# un adoptant réécrit son ci.yml (plan T-00000529, R6). Les seaux du canal apt
# se jouent sur des workflows-FIXTURES que ce banc écrit lui-même.
# CAPACITÉ DÉPLACÉE, NOMMÉE : « la ligne apt du ci.yml RÉEL gagne un paquet non
# inventorié » ne rougit PAS ici. Elle rougit dans core-scripts/doctor-parity.test.sh
# (cas 10), en mode KIT seulement, contre une liste fermée du seau 3 ({jq}) ;
# sur un arbre adoptant, rien ne l'asserte.
#
# AUCUN OUTIL INVENTORIÉ N'EST EXÉCUTÉ : la sonde du doctor passe par
# DOCTOR_PROBE_PATH, qui ne contient que des bouchons écrits ici, nommés par
# l'inventaire lui-même (aucun nom d'outil dans ce banc hors des cas qui en
# fabriquent un faux). UNE EXCEPTION, NOMMÉE : le cas 21 exécute un
# interpréteur RÉEL, celui d'un `-m venv --without-pip` créé dans $TMP depuis
# le premier python3|python du poste qui est >= 3.9 (plan
# T-01M5VYNMZPG8G0JZG48HV4K0PN, C13) — un bouchon ne dirait rien de la
# découverte des modules. Aucun poste sans un tel python : FAIL nommé.
#
# Exit : 0 tous les cas passent · 1 au moins un cas échoue.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

DOCTOR="$ROOT/core-scripts/doctor.sh"
INV="$ROOT/core-scripts/tool-inventory.tsv"
PARITY_REF="$ROOT/core-scripts/check-ci-parity.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

US=$'\037'
_pipe='|'
_ge='>='

pass=0
fail=0
ok() { echo "--- PASS $1"; pass=$((pass + 1)); }
ko() { echo "--- FAIL $1"; fail=$((fail + 1)); }
montre() { sed 's/^/      /' "$1"; }

# --- l'inventaire, lu par NOM de colonne, comme le doctor --------------------
# Champs : tool, nature, os, class, version, apt, cost, ci_pin (séparateur US).
inv_rows() {
  awk -F'\t' -v us="$US" '
    { sub(/\r$/, "") }
    /^#/ { next }
    !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
    /^[[:space:]]*$/ { next }
    { print $c["tool"] us $c["nature"] us $c["os"] us $c["class"] us $c["version"] us $c["apt"] us $c["cost"] us $c["ci_pin"] }
  ' "$1"
}
ROWS="$(inv_rows "$INV")"
N_ROWS="$(printf '%s\n' "$ROWS" | grep -c .)"
N_OUTILS="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "outil"' | grep -c .)"
N_COND="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "condition"' | grep -c .)"
if [ "$N_OUTILS" -lt 30 ]; then
  ko "socle : l'inventaire rend $N_OUTILS lignes outil (< 30) — tout le banc serait vacant"
  echo "doctor.test.sh: $pass passed, $fail failed"
  exit 1
fi

os_vaut() { # os_vaut <cellule os> <os> : rc 0 si la ligne vaut pour cet os
  [ "$1" = "any" ] && return 0
  case ",$1," in
    *",$2,"*)
      return 0
      ;;
  esac
  return 1
}

stub() { # stub <dir> <nom> <ligne rendue par --version> [rc, défaut 0] : rc 1, rien d'écrit, si <nom> porte `/` ou est vide
  case "$2" in
    */*|"")
      printf 'stub: nom refusé « %s » (barre oblique ou vide : écrirait hors de %s)\n' "$2" "$1" >&2
      return 1
      ;;
  esac
  mkdir -p "$1"
  printf '#!/bin/sh\necho "%s"\nexit %s\n' "$3" "${4:-0}" > "$1/$2"
  chmod +x "$1/$2"
}

stub_all() { # stub_all <dir> <os> <first|last> [classe] : un bouchon par ligne outil de la plateforme
  local tool nature os klass alias
  mkdir -p "$1"
  while IFS="$US" read -r tool nature os klass _; do
    [ "$nature" = "outil" ] || continue
    os_vaut "$os" "$2" || continue
    [ -n "${4:-}" ] && [ "$klass" != "$4" ] && continue
    if [ "$3" = "last" ]; then
      alias="${tool##*"$_pipe"}"
    else
      alias="${tool%%"$_pipe"*}"
    fi
    stub "$1" "$alias" "x 99.0.0 GNU" || ko "stub_all : bouchon refusé pour « $alias » ($tool)"
  done <<< "$ROWS"
}

# Témoin du refus de stub() : un nom à barre oblique ne crée RIEN sous <dir>.
# `$TMP/sx/a/` existe d'avance : sans la garde, l'écriture RÉUSSIRAIT — le
# témoin ne doit pas passer par l'échec accidentel d'un répertoire absent.
mkdir -p "$TMP/sx/a"
if stub "$TMP/sx" "a/b" "x" 2>/dev/null || [ -e "$TMP/sx/a/b" ]; then
  ko "stub : un nom à barre oblique (a/b) a été accepté"
else
  ok "stub : nom à barre oblique refusé, rc 1, rien écrit"
fi

run_doc() { # run_doc <sortie> <os> <probe-path> [args…] : rc du doctor
  local out="$1" os="$2" pp="$3"
  shift 3
  env "DOCTOR_OS=$os" "DOCTOR_PROBE_PATH=$pp" bash "$DOCTOR" "$@" > "$out" 2>&1
}

resume() { # resume <sortie> : « présents N N/A absents » lus sur la ligne de résumé
  sed -n 's/^doctor: \([0-9][0-9]*\)\/\([0-9][0-9]*\) présents, \([0-9][0-9]*\) N\/A, \([0-9][0-9]*\) absents.*$/\1 \2 \3 \4/p' "$1"
}

ligne_de() { # ligne_de <sortie> <statut> <outil> : la ligne du rapport, vide si absente
  awk -v s="$2" -v t="$3" '
    index($0, s) && (index($0, " " t " ") || substr($0, length($0) - length(t)) == " " t) { print; exit }
  ' "$1"
}

# ---------------------------------------------------------------------------
# CAS 1 — témoin positif : tout présent sous linux, rc 0, n + k + absents == N
# ---------------------------------------------------------------------------
stub_all "$TMP/b1" linux first
run_doc "$TMP/o1" linux "$TMP/b1"; rc=$?
r="$(resume "$TMP/o1")"
read -r r_p r_n r_k r_a <<< "${r:-x x x x}"
if [ "$rc" -eq 0 ] && [ "$r_n" = "$N_OUTILS" ] && [ "$r_a" = "0" ] \
   && [ $((r_p + r_k + r_a)) -eq "$N_OUTILS" ] && ! grep -q "MAUVAISE VERSION" "$TMP/o1" \
   && grep -q "mauvaise version=aucune, $N_COND conditions non sondées" "$TMP/o1"; then
  ok "cas 1 : tout présent (linux) — rc 0, $r_p présents + $r_k N/A == $N_OUTILS lignes outil, $N_COND conditions"
else
  ko "cas 1 : témoin positif (rc=$rc, résumé « $r », N outils attendu $N_OUTILS)"
  montre "$TMP/o1"
fi

# ---------------------------------------------------------------------------
# CAS 1bis — alias et plateforme : windows, DERNIER alias bouchonné
# ---------------------------------------------------------------------------
stub_all "$TMP/b1b" windows last
run_doc "$TMP/o1b" windows "$TMP/b1b"; rc=$?
bad=""
n_alias=0
n_na=0
while IFS="$US" read -r tool nature os _; do
  [ "$nature" = "outil" ] || continue
  if os_vaut "$os" windows; then
    case "$tool" in
      *"$_pipe"*)
        n_alias=$((n_alias + 1))
        last="${tool##*"$_pipe"}"
        [ -n "$(ligne_de "$TMP/o1b" "PRESENT ($last)" "$tool")" ] || bad="$bad alias:$tool"
        ;;
    esac
  else
    n_na=$((n_na + 1))
    [ -n "$(ligne_de "$TMP/o1b" "N/A (plateforme $os)" "$tool")" ] || bad="$bad na:$tool"
  fi
done <<< "$ROWS"
if [ "$rc" -eq 0 ] && [ -z "$bad" ] && [ "$n_alias" -ge 1 ] && [ "$n_na" -ge 1 ]; then
  ok "cas 1bis : windows — $n_alias lignes à alias PRESENT (dernier alias), $n_na lignes N/A nommant leur plateforme, rc 0"
else
  ko "cas 1bis : alias/plateforme (rc=$rc, alias=$n_alias, na=$n_na, manquants :$bad)"
  montre "$TMP/o1b"
fi
stub "$TMP/ubin" uname "Haiku"
env DOCTOR_OS= "PATH=$TMP/ubin:$PATH" "DOCTOR_PROBE_PATH=$TMP/b1" bash "$DOCTOR" > "$TMP/o1c" 2>&1
if grep -q "os inconnu (Haiku) — toutes les plateformes sondées" "$TMP/o1c"; then
  ok "cas 1bis : uname inconnu — ligne « os inconnu », jamais un N/A muet"
else
  ko "cas 1bis : uname Haiku sans ligne « os inconnu »"
  montre "$TMP/o1c"
fi

# ---------------------------------------------------------------------------
# CAS 2 — un optionnel absent : rc 0, ABSENT (optionnel), coût cité
# ---------------------------------------------------------------------------
cible=""
cout=""
while IFS="$US" read -r tool nature os klass _ _ cost _; do
  if [ "$nature" != "outil" ] || [ "$klass" != "A" ] || ! os_vaut "$os" linux; then
    continue
  fi
  case "$tool" in
    *"$_pipe"*)
      continue
      ;;
  esac
  cible="$tool"
  cout="$cost"
  break
done <<< "$ROWS"
stub_all "$TMP/b2" linux first
rm -f "$TMP/b2/$cible"
run_doc "$TMP/o2" linux "$TMP/b2"; rc=$?
l="$(ligne_de "$TMP/o2" "ABSENT (optionnel)" "$cible")"
if [ -n "$cible" ] && [ "$rc" -eq 0 ] && [ -n "$l" ] && printf '%s' "$l" | grep -qF -- "coût : $cout"; then
  ok "cas 2 : $cible absent (classe A) — rc 0, ABSENT (optionnel), coût cité"
else
  ko "cas 2 : optionnel absent ($cible, rc=$rc)"
  montre "$TMP/o2"
fi

# ---------------------------------------------------------------------------
# CAS 3 — un outil de classe B absent : rc 1, nommé
# ---------------------------------------------------------------------------
cibleb=""
while IFS="$US" read -r tool nature os klass _; do
  if [ "$nature" != "outil" ] || [ "$klass" != "B" ] || ! os_vaut "$os" linux; then
    continue
  fi
  cibleb="$tool"
  break
done <<< "$ROWS"
stub_all "$TMP/b3" linux first
alts3="${cibleb//$_pipe/ }"
for a in $alts3; do
  rm -f "$TMP/b3/$a"
done
run_doc "$TMP/o3" linux "$TMP/b3"; rc=$?
if [ -n "$cibleb" ] && [ "$rc" -eq 1 ] && [ -n "$(ligne_de "$TMP/o3" "ABSENT (requis)" "$cibleb")" ] \
   && grep -qF "B manquants=$cibleb," "$TMP/o3"; then
  ok "cas 3 : $cibleb absent (classe B) — rc 1, ABSENT (requis), nommé au résumé"
else
  ko "cas 3 : classe B absente ($cibleb, rc=$rc)"
  montre "$TMP/o3"
fi

# ---------------------------------------------------------------------------
# CAS 4 — inventaire malformé : rc 1, ligne ET colonne nommées
# ---------------------------------------------------------------------------
# mute_col <col> <valeur> <sortie> : copie du TSV réel, la cellule <col> de la
# PREMIÈRE ligne de données remplacée (colonne trouvée par NOM).
mute_col() {
  awk -F'\t' -v OFS='\t' -v cn="$1" -v val="$2" '
    /^#/ { print; next }
    !h { h = 1; for (i = 1; i <= NF; i++) if ($i == cn) k = i; print; next }
    !done && NF > 1 { $k = val; done = 1 }
    { print }
  ' "$INV" > "$3"
}
expect_inv() { # expect_inv <tsv> <motif littéral> <libellé>
  local rc
  # Sonde VIDE : si une validation régressait, le doctor sonderait au lieu de
  # refuser — il ne doit alors exécuter aucun outil réel (`--version`).
  mkdir -p "$TMP/vide4"
  env "DOCTOR_PROBE_PATH=$TMP/vide4" bash "$DOCTOR" --inventory "$1" > "$TMP/o4" 2>&1; rc=$?
  if [ "$rc" -eq 1 ] && grep -qF -- "$2" "$TMP/o4"; then
    ok "cas 4 : $3 — rc 1, « $2 »"
  else
    ko "cas 4 : $3 (rc=$rc, motif « $2 » attendu)"
    montre "$TMP/o4"
  fi
}
L1="$(awk '/^#/ { next } !h { h = 1; next } { print NR; exit }' "$INV")"
grep -E '^#|^tool' "$INV" > "$TMP/i_entete"
expect_inv "$TMP/i_entete" "inventaire vide" "en-tête seul"
awk -F'\t' -v OFS='\t' '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) if ($i == "version") $i = "versio"; print; next } { print }' "$INV" > "$TMP/i_col"
expect_inv "$TMP/i_col" "colonne requise absente de la ligne de colonnes : version" "colonne version absente"
awk -F'\t' -v OFS='\t' -v l="$L1" 'NR == l { s = $1; for (i = 2; i < NF; i++) s = s OFS $i; print s; next } { print }' "$INV" > "$TMP/i_nf"
# Le nombre de colonnes est LU sur la ligne de colonnes de l'inventaire, jamais écrit ici.
NC_INV="$(awk -F'\t' '/^#/ { next } { print NF; exit }' "$INV")"
NC_MOINS=$((NC_INV - 1))
expect_inv "$TMP/i_nf" "ligne $L1 : $NC_MOINS champs, $NC_INV attendus" "une colonne de moins ($NC_INV colonnes lues)"
mute_col brew "" "$TMP/i_vide"
expect_inv "$TMP/i_vide" "ligne $L1, colonne brew : champ vide" "champ vide dans brew (deux tabulations)"
mute_col cost "SKIP sans objet" "$TMP/i_skip"
expect_inv "$TMP/i_skip" "ligne $L1, colonne cost : ouvre par SKIP" "cost ouvrant par SKIP"
mute_col class "C" "$TMP/i_classe"
expect_inv "$TMP/i_classe" "ligne $L1, colonne class : C hors vocabulaire" "classe C refusée"
# La forme du jeton `tool` (avis sécurité S-00004475) : ni chemin, ni option, ni glob.
mute_col tool "a/b" "$TMP/i_tool_slash"
expect_inv "$TMP/i_tool_slash" "ligne $L1, colonne tool : a/b hors forme" "jeton tool à barre oblique"
mute_col tool "-n" "$TMP/i_tool_opt"
expect_inv "$TMP/i_tool_opt" "ligne $L1, colonne tool : -n hors forme" "jeton tool ouvrant par -"
mute_col tool "x*" "$TMP/i_tool_glob"
expect_inv "$TMP/i_tool_glob" "ligne $L1, colonne tool : x* hors forme" "jeton tool à glob"
# Le mode de sonde (constat 1 de la passe de correction du lot 0) : vocabulaire fermé, colonne requise.
mute_col mode_sonde "nom" "$TMP/i_mode_voc"
expect_inv "$TMP/i_mode_voc" "ligne $L1, colonne mode_sonde : nom hors vocabulaire" "mode_sonde hors vocabulaire"
mute_col mode_sonde "module:a/b" "$TMP/i_mode_forme"
expect_inv "$TMP/i_mode_forme" "ligne $L1, colonne mode_sonde : module:a/b hors vocabulaire" "interpréteur à barre oblique"
L_ALT="$(awk -F'\t' '/^#/ { next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next } $c["nature"] == "outil" && $c["tool"] ~ /[|]/ { print NR; exit }' "$INV")"
awk -F'\t' -v OFS='\t' -v l="$L_ALT" '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next } NR == l { $c["mode_sonde"] = "module:interp-t4" } { print }' "$INV" > "$TMP/i_mode_alt"
expect_inv "$TMP/i_mode_alt" "ligne $L_ALT, colonne mode_sonde : module:interp-t4 sur le jeton a alternatives" "mode module sur un jeton à alternatives (ligne $L_ALT)"
awk -F'\t' -v OFS='\t' '/^#/ { print; next } !h { h = 1; for (i = 1; i <= NF; i++) if ($i == "mode_sonde") $i = "mode_sond"; print; next } { print }' "$INV" > "$TMP/i_mode_col"
expect_inv "$TMP/i_mode_col" "colonne requise absente de la ligne de colonnes : mode_sonde" "colonne mode_sonde absente"

# ---------------------------------------------------------------------------
# CAS 5 — usage : rc 2
# ---------------------------------------------------------------------------
for argv in "--frobnicate" "--ci" "--ci --list"; do
  # shellcheck disable=SC2086
  bash "$DOCTOR" $argv > "$TMP/o5" 2>&1; rc=$?
  if [ "$rc" -eq 2 ]; then
    ok "cas 5 : « $argv » — rc 2"
  else
    ko "cas 5 : « $argv » (rc=$rc, attendu 2)"
    montre "$TMP/o5"
  fi
done

# ---------------------------------------------------------------------------
# CAS 6 — seaux du canal apt, sur des FIXTURES (jamais le ci.yml réel)
# ---------------------------------------------------------------------------
# P1 = premier paquet apt de l'inventaire, T1 son outil ; tous les AUTRES
# paquets inventoriés vont dans RUNNER_PREINSTALLED de la porte-fixture.
APTS="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "outil" && $6 != "-" && !($6 in s) { s[$6] = 1; print $6 }')"
P1="$(printf '%s\n' "$APTS" | sed -n 1p)"
T1="$(printf '%s\n' "$ROWS" | awk -F"$US" -v p="$P1" '$6 == p { print $1; exit }')"
AUTRES="$(printf '%s\n' "$APTS" | sed 1d | tr '\n' ' ')"
P2="$(printf '%s\n' "$APTS" | sed -n 2p)"
AUTRES_SANS_P2="$(printf '%s\n' "$APTS" | sed '1,2d' | tr '\n' ' ')"
mkdir -p "$TMP/ci"
{
  printf 'jobs:\n  tests:\n    steps:\n      - run: |\n'
  printf '          sudo apt-get install -y %s paquet-hors-inventaire-t1001\n' "$P1"
} > "$TMP/ci/ci.yml"
printf '    RUNNER_PREINSTALLED="%s runner-hors-inventaire-t1001"  # fixture\n' "$AUTRES" > "$TMP/ci/verify.sh"
printf '    RUNNER_PREINSTALLED="%s"  # fixture\n' "$AUTRES_SANS_P2" > "$TMP/ci/verify2.sh"
stub_all "$TMP/b6" linux first
run_doc "$TMP/o6" linux "$TMP/b6" --ci "$TMP/ci/ci.yml" --verify "$TMP/ci/verify.sh"; rc=$?
s1="$(sed -n 's/^  seau 1 — installés par la ligne apt de la CI ET inventoriés ://p' "$TMP/o6")"
s2="$(sed -n 's/^  seau 2 — paquets inventoriés que ni la ligne apt ni le runner ne fournissent ://p' "$TMP/o6")"
s3="$(sed -n 's/^  seau 3 — installés par la ligne apt, NON inventoriés ://p' "$TMP/o6")"
s4="$(sed -n 's/^  préinstallés runner (RUNNER_PREINSTALLED), non inventoriés ://p' "$TMP/o6")"
if [ -n "$P1" ] && [ -n "$P2" ] && [ "$rc" -eq 0 ] && [ "$s1" = " $P1 ($T1)" ] && [ "$s2" = " aucun" ] \
   && [ "$s3" = " paquet-hors-inventaire-t1001" ] && [ "$s4" = " runner-hors-inventaire-t1001" ]; then
  ok "cas 6 : seaux sur fixture — seau 1 « $P1 ($T1) », seau 3 exactement le paquet hors inventaire, runner hors inventaire nommé"
else
  ko "cas 6 : seaux (rc=$rc, s1=« $s1 », s2=« $s2 », s3=« $s3 », runner=« $s4 »)"
  montre "$TMP/o6"
fi
run_doc "$TMP/o6b" linux "$TMP/b6" --ci "$TMP/ci/ci.yml" --verify "$TMP/ci/verify2.sh"
s2="$(sed -n 's/^  seau 2 — paquets inventoriés que ni la ligne apt ni le runner ne fournissent ://p' "$TMP/o6b")"
case "$s2" in
  *" $P2 ("*)
    ok "cas 6 : un paquet inventorié retiré du runner tombe au seau 2 ($P2)"
    ;;
  *)
    ko "cas 6 : $P2 retiré du runner absent du seau 2 (« $s2 »)"
    montre "$TMP/o6b"
    ;;
esac
# Porte SANS ligne RUNNER_PREINSTALLED (S-00004538, C2) — sa seule mention est
# une ligne commentée, que le doctor ôte — puis porte absente : les préinstallés
# runner sont INCONNUS, le seau 2 n'est jamais calculé contre un runner vide.
printf '#!/usr/bin/env bash\n# RUNNER_PREINSTALLED="%s"  commentaire, jamais lu\necho porte sans runner\n' "$AUTRES" > "$TMP/ci/verify3.sh"
nd6=0
for v6 in "$TMP/ci/verify3.sh" "$TMP/ci/porte-absente-t1001.sh"; do
  run_doc "$TMP/o6c" linux "$TMP/b6" --ci "$TMP/ci/ci.yml" --verify "$v6"; rc=$?
  s2="$(sed -n 's/^  seau 2 — //p' "$TMP/o6c")"
  s4="$(sed -n 's/^  préinstallés runner//p' "$TMP/o6c")"
  if [ "$rc" -eq 0 ] && [ "$s2" = "non dérivable : préinstallés runner inconnus (porte absente ou sans ligne RUNNER_PREINSTALLED)" ] \
     && [ "$s4" = " : non dérivable (porte absente ou sans ligne RUNNER_PREINSTALLED)" ]; then
    nd6=$((nd6 + 1))
  else
    ko "cas 6 : porte $v6 sans ligne RUNNER_PREINSTALLED (rc=$rc, seau 2 « $s2 », runner « $s4 »)"
    montre "$TMP/o6c"
  fi
done
[ "$nd6" -eq 2 ] && ok "cas 6 : porte sans ligne RUNNER_PREINSTALLED (ligne commentée seule), puis absente — seau 2 et préinstallés runner « non dérivable », rc 0"
# La ligne des épinglés cite une ligne apt ET ci_pin : un filtre qui n'y
# admettrait que les lignes sans apt (`$8 == "-"` côté doctor) la perdrait.
# Témoin ponctuel : l'inventaire n'a aujourd'hui qu'une telle ligne.
PIN_APT="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "outil" && $6 != "-" && $8 != "-" { print $1; exit }')"
pins="$(sed -n 's/^  épinglés par la colonne ci_pin, apt ou non (déclaré, non dérivé ; colonne brew non citée) ://p' "$TMP/o6")"
if [ -z "$PIN_APT" ]; then
  ko "cas 6 : épinglés — témoin vacant (aucune ligne apt ET ci_pin dans l'inventaire)"
else
  case " $pins " in
    *" $PIN_APT "*)
      ok "cas 6 : la ligne des épinglés cite $PIN_APT (apt ET ci_pin)"
      ;;
    *)
      ko "cas 6 : épinglés « $pins » sans $PIN_APT (apt ET ci_pin)"
      montre "$TMP/o6"
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# CAS 7 — appariement par PAQUET, et workflow sans ligne apt
# ---------------------------------------------------------------------------
# PX : un paquet dont le nom DIFFÈRE de celui de son outil — l'appariement par
# nom d'outil le rendrait « non inventorié ».
PX="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "outil" && $6 != "-" && $6 != $1 { print $6; exit }')"
TX="$(printf '%s\n' "$ROWS" | awk -F"$US" -v p="$PX" '$6 == p { print $1; exit }')"
printf 'steps:\n  - run: |\n      sudo apt-get install -y %s\n' "$PX" > "$TMP/ci/ci7.yml"
run_doc "$TMP/o7" linux "$TMP/b6" --ci "$TMP/ci/ci7.yml" --verify "$TMP/ci/verify.sh"; rc=$?
s1="$(sed -n 's/^  seau 1 — installés par la ligne apt de la CI ET inventoriés ://p' "$TMP/o7")"
s3="$(sed -n 's/^  seau 3 — installés par la ligne apt, NON inventoriés ://p' "$TMP/o7")"
if [ -n "$PX" ] && [ "$rc" -eq 0 ] && [ "$s1" = " $PX ($TX)" ] && [ "$s3" = " aucun" ]; then
  ok "cas 7 : $PX ≠ $TX apparié par la colonne apt (seau 1), seau 3 vide"
else
  ko "cas 7 : appariement par paquet (PX=$PX, rc=$rc, s1=« $s1 », s3=« $s3 »)"
  montre "$TMP/o7"
fi
printf 'steps:\n  - run: echo pas de ligne apt\n' > "$TMP/ci/sans_apt.yml"
run_doc "$TMP/o7b" linux "$TMP/b6" --ci "$TMP/ci/sans_apt.yml"; rc=$?
if [ "$rc" -eq 1 ] && grep -q "CI : non dérivable (aucune ligne apt-get install -y dans" "$TMP/o7b"; then
  ok "cas 7 : --ci explicite sans ligne apt — rc 1"
else
  ko "cas 7 : --ci explicite sans ligne apt (rc=$rc, attendu 1)"
  montre "$TMP/o7b"
fi
# Le défaut (pas de --ci) se joue sur une COPIE de doctor.sh posée dans un arbre
# dont le workflow n'a pas de ligne apt — l'arbre d'un adoptant qui l'a réécrit.
mkdir -p "$TMP/arbre/core-scripts" "$TMP/arbre/.github/workflows"
cp "$DOCTOR" "$TMP/arbre/core-scripts/doctor.sh"
cp "$TMP/ci/sans_apt.yml" "$TMP/arbre/.github/workflows/ci.yml"
env DOCTOR_OS=linux "DOCTOR_PROBE_PATH=$TMP/b6" bash "$TMP/arbre/core-scripts/doctor.sh" --inventory "$INV" > "$TMP/o7c" 2>&1; rc=$?
rm -f "$TMP/arbre/.github/workflows/ci.yml"
env DOCTOR_OS=linux "DOCTOR_PROBE_PATH=$TMP/b6" bash "$TMP/arbre/core-scripts/doctor.sh" --inventory "$INV" > "$TMP/o7d" 2>&1; rc2=$?
if [ "$rc" -eq 0 ] && grep -q "CI : non dérivable (aucune ligne apt-get install -y dans" "$TMP/o7c" \
   && [ "$rc2" -eq 0 ] && grep -q "CI : non dérivable (.* absent)" "$TMP/o7d"; then
  ok "cas 7 : workflow par défaut sans ligne apt, puis absent — rc 0, « non dérivable »"
else
  ko "cas 7 : défaut sans ligne apt (rc=$rc puis $rc2, attendu 0 et 0)"
  montre "$TMP/o7c"
  montre "$TMP/o7d"
fi
# Les DÉFAUTS de --ci et de --verify (S-00004538, C2 ; mutant D2 de plan-critic,
# S-00004518) : sans option, la copie lit le ci.yml et la porte de SON arbre.
cp "$TMP/ci/ci.yml" "$TMP/arbre/.github/workflows/ci.yml"
cp "$TMP/ci/verify.sh" "$TMP/arbre/core-scripts/verify.sh"
env DOCTOR_OS=linux "DOCTOR_PROBE_PATH=$TMP/b6" bash "$TMP/arbre/core-scripts/doctor.sh" --inventory "$INV" > "$TMP/o7e" 2>&1; rc=$?
s1="$(sed -n 's/^  seau 1 — installés par la ligne apt de la CI ET inventoriés ://p' "$TMP/o7e")"
s2="$(sed -n 's/^  seau 2 — paquets inventoriés que ni la ligne apt ni le runner ne fournissent ://p' "$TMP/o7e")"
s3="$(sed -n 's/^  seau 3 — installés par la ligne apt, NON inventoriés ://p' "$TMP/o7e")"
s4="$(sed -n 's/^  préinstallés runner (RUNNER_PREINSTALLED), non inventoriés ://p' "$TMP/o7e")"
if [ "$rc" -eq 0 ] && [ "$s1" = " $P1 ($T1)" ] && [ "$s2" = " aucun" ] \
   && [ "$s3" = " paquet-hors-inventaire-t1001" ] && [ "$s4" = " runner-hors-inventaire-t1001" ]; then
  ok "cas 7 : défauts — sans --ci ni --verify, .github/workflows/ci.yml et core-scripts/verify.sh de l'arbre sont lus (seaux 1-3 et runner)"
else
  ko "cas 7 : défauts de --ci et --verify (rc=$rc, s1=« $s1 », s2=« $s2 », s3=« $s3 », runner=« $s4 »)"
  montre "$TMP/o7e"
fi

# ---------------------------------------------------------------------------
# CAS 10 — aucune ligne du rapport n'ouvre par SKIP (relevé du runner)
# ---------------------------------------------------------------------------
stub_all "$TMP/b10" linux first B
run_doc "$TMP/o10a" linux "$TMP/b10"; rca=$?
mkdir -p "$TMP/vide"
run_doc "$TMP/o10b" linux "$TMP/vide"; rcb=$?
na="$(grep -cE '^[[:space:]]*SKIP|^[[:space:]]*ok:.*\[SKIP' "$TMP/o10a")"
nb="$(grep -cE '^[[:space:]]*SKIP|^[[:space:]]*ok:.*\[SKIP' "$TMP/o10b")"
if [ "$rca" -eq 0 ] && [ "$rcb" -eq 1 ] && [ "$na" -eq 0 ] && [ "$nb" -eq 0 ] \
   && grep -q "ABSENT (optionnel)" "$TMP/o10a" && grep -q "ABSENT (requis)" "$TMP/o10b"; then
  ok "cas 10 : tous les A absents (rc 0) puis tout absent (rc 1) — zéro ligne SKIP en tête"
else
  ko "cas 10 : (rc=$rca puis $rcb, lignes SKIP=$na puis $nb)"
fi

# ---------------------------------------------------------------------------
# CAS 11 — --list ne sonde rien
# ---------------------------------------------------------------------------
run_doc "$TMP/o11" linux "$TMP/vide" --list; rc=$?
nl="$(grep -c '^  ' "$TMP/o11")"
if [ "$rc" -eq 0 ] && [ "$nl" -eq "$N_ROWS" ] && ! grep -qE 'PRESENT|ABSENT' "$TMP/o11"; then
  ok "cas 11 : --list — rc 0, $nl lignes == $N_ROWS lignes de données, aucun verdict de sonde"
else
  ko "cas 11 : --list (rc=$rc, $nl lignes, attendu $N_ROWS)"
  montre "$TMP/o11"
fi

# ---------------------------------------------------------------------------
# CAS 12 — parité à l'octet des trois `sed` avec check-ci-parity.sh
# ---------------------------------------------------------------------------
# Une ancre par `sed`, en OCTETS sans apostrophe. Pour chaque fichier : (1) une
# seule ligne la porte ; (2) extraction de l'expression entre apostrophes,
# jamais `grep -o` (il rendrait l'ancre des deux côtés) ; (3) l'extrait est non
# vide, CONTIENT l'ancre et en DIFFÈRE ; (4) seulement alors, comparaison.
for A in '(sudo[[:space:]]+)?apt-get[[:space:]]+install' 'RUNNER_PREINSTALLED="(' 's/^[[:space:]]*#.*$//'; do
  okA=1
  e_ref=""
  e_doc=""
  for F in "$PARITY_REF" "$DOCTOR"; do
    n="$(grep -c -F -- "$A" "$F")"
    if [ "$n" -ne 1 ]; then
      ko "cas 12 : ancre « $A » portée par $n lignes de $F (attendu 1)"
      okA=0
      continue
    fi
    e="$(grep -F -- "$A" "$F" | sed "s/^[^']*//; s/'[^']*\$//")"
    case "$e" in
      *"$A"*)
        ;;
      *)
        ko "cas 12 : extraction vacueuse dans $F (« $e » ne contient pas « $A »)"
        okA=0
        continue
        ;;
    esac
    if [ -z "$e" ] || [ "$e" = "$A" ]; then
      ko "cas 12 : extraction vacueuse dans $F (« $e »)"
      okA=0
      continue
    fi
    if [ "$F" = "$DOCTOR" ]; then
      e_doc="$e"
    else
      e_ref="$e"
    fi
  done
  if [ "$okA" -eq 1 ]; then
    if [ "$e_ref" = "$e_doc" ]; then
      ok "cas 12 : « $A » — même expression dans check-ci-parity.sh et doctor.sh"
    else
      ko "cas 12 : « $A » diverge"
      printf '      check-ci-parity.sh : %s\n      doctor.sh          : %s\n' "$e_ref" "$e_doc"
    fi
  fi
done

# ---------------------------------------------------------------------------
# CAS 13 — CRITÈRE 1 : aucune liste d'outils codée en dur dans doctor.sh
# ---------------------------------------------------------------------------
# Le code (lignes de commentaire ôtées) ne nomme AUCUN jeton de l'inventaire,
# alias compris. UNE exception, nommée : le lecteur du TSV, que doctor.sh
# EXÉCUTE lui-même (plan T-00000529, R7) — il est aussi une ligne de
# l'inventaire. Son occurrence prouve que le grep MORD sur un jeton présent.
# L'exception est bornée à sa forme de COMMANDE : chaque occurrence du mot doit
# être un appel `awk -…` (en tête de ligne, après `|`, `(` ou `$(`). Comptées
# par OCCURRENCE, pas par ligne : un `awk` nu dans une chaîne ou une
# affectation (mutant m1b de l'exec-critic, S-00004476) rougit, même posé sur la
# ligne d'un vrai appel.
LECTEUR='awk'
grep -vE '^[[:space:]]*#' "$DOCTOR" > "$TMP/code"
jetons="$(printf '%s\n' "$ROWS" | awk -F"$US" '$2 == "outil" { n = split($1, a, "|"); for (i = 1; i <= n; i++) print a[i] }' | sort -u)"
nj="$(printf '%s\n' "$jetons" | grep -c .)"
cites=""
while IFS= read -r j; do
  [ "$j" = "$LECTEUR" ] && continue
  if [ "$(grep -c -w -F -- "$j" "$TMP/code")" -ne 0 ]; then
    cites="$cites $j"
  fi
done <<< "$jetons"
nlect="$(grep -o -w -F -- "$LECTEUR" "$TMP/code" | grep -c .)"
nlect_cmd="$(grep -o -E '(^|[|(]|[$][(])[[:space:]]*'"$LECTEUR"'[[:space:]]+-' "$TMP/code" | grep -c .)"
if [ "$nj" -ge 30 ] && [ "$nlect" -ge 1 ] && [ "$nlect" -eq "$nlect_cmd" ] && [ -z "$cites" ]; then
  ok "cas 13 : critère 1 — $nj jetons de l'inventaire, aucun écrit dans le code de doctor.sh (le grep mord : $LECTEUR, $nlect occurrences, toutes des commandes)"
else
  ko "cas 13 : critère 1 — jetons de l'inventaire écrits dans le code de doctor.sh :${cites:- aucun} (jetons=$nj, $LECTEUR=$nlect occurrences dont $nlect_cmd commandes)"
  for j in $cites $LECTEUR; do
    grep -n -w -F -- "$j" "$TMP/code" | sed 's/^/      /'
  done
fi

# ---------------------------------------------------------------------------
# CAS 14 — CRITÈRE 1 : chaque outil manquant, avec SA version attendue
# ---------------------------------------------------------------------------
run_doc "$TMP/o14" linux "$TMP/vide"
manque=""
nv=0
nc14=0
while IFS="$US" read -r tool nature os _ version _ _ cipin; do
  if [ "$nature" != "outil" ] || ! os_vaut "$os" linux; then
    continue
  fi
  nc14=$((nc14 + 1))
  att="$version"
  if [ "$version" = "-" ]; then
    att="aucune contrainte écrite"
  else
    nv=$((nv + 1))
  fi
  l="$(grep -F -- " $tool — version attendue : $att" "$TMP/o14" | grep -F "ABSENT" | sed -n 1p)"
  if [ -z "$l" ]; then
    manque="$manque $tool"
    continue
  fi
  if [ "$cipin" != "-" ] && ! printf '%s' "$l" | grep -qF -- "pin CI : $cipin"; then
    manque="$manque $tool(pin)"
  fi
done <<< "$ROWS"
if [ "$nc14" -ge 30 ] && [ "$nv" -ge 1 ] && [ -z "$manque" ]; then
  ok "cas 14 : critère 1 — $nc14 outils manquants listés, chacun avec la version de l'inventaire ($nv contraintes écrites)"
else
  ko "cas 14 : critère 1 — lignes ABSENT sans leur version attendue :${manque:- aucune} ($nc14 vérifiées, $nv contraintes)"
  montre "$TMP/o14"
fi

# ---------------------------------------------------------------------------
# CAS 15 — CRITÈRE 3 : l'en-tête borne le périmètre et renvoie à `cadre doctor`
# ---------------------------------------------------------------------------
entete="$(awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^#[[:space:]]*/, ""); printf "%s ", $0 }' "$DOCTOR")"
manque=""
for frag in "PÉRIMÈTRE — BORNÉ À L'INVENTAIRE" "core-scripts/tool-inventory.tsv" \
            "les outils du poste de développement et de la CI DU KIT, et eux seuls" \
            "CE N'EST PAS LE DOCTOR DE L'ADOPTANT" "relèvent de \`cadre doctor\`"; do
  case "$entete" in
    *"$frag"*)
      ;;
    *)
      manque="$manque [$frag]"
      ;;
  esac
done
if [ -z "$manque" ]; then
  ok "cas 15 : critère 3 — l'en-tête borne le périmètre au poste et à la CI du kit et renvoie à \`cadre doctor\`"
else
  ko "cas 15 : critère 3 — fragments absents de l'en-tête :$manque"
fi

# ---------------------------------------------------------------------------
# CAS 16 — MAUVAISE VERSION : rapportée, ne change JAMAIS le code de retour
# ---------------------------------------------------------------------------
vge=""
vtxt=""
while IFS="$US" read -r tool nature os _ version _; do
  if [ "$nature" != "outil" ] || [ "$version" = "-" ] || ! os_vaut "$os" linux; then
    continue
  fi
  case "$version" in
    ">="*)
      [ -z "$vge" ] && vge="$tool" && vge_c="$version"
      ;;
    *)
      [ -z "$vtxt" ] && vtxt="$tool" && vtxt_c="$version"
      ;;
  esac
done <<< "$ROWS"
if [ -z "$vge" ] || [ -z "$vtxt" ]; then
  ko "cas 16 : l'inventaire n'a plus de contrainte >= ($vge) ou textuelle ($vtxt) — cas vacant"
else
  stub_all "$TMP/b16" linux first
  stub "$TMP/b16" "${vge%%"$_pipe"*}" "x 1.0"
  stub "$TMP/b16" "${vtxt%%"$_pipe"*}" "x 99.0.0 autre"
  run_doc "$TMP/o16" linux "$TMP/b16"; rc=$?
  lg="$(ligne_de "$TMP/o16" "MAUVAISE VERSION" "$vge")"
  lt="$(ligne_de "$TMP/o16" "MAUVAISE VERSION" "$vtxt")"
  if [ "$rc" -eq 0 ] && [ -n "$lg" ] && printf '%s' "$lg" | grep -qF -- "version 1.0, attendue $vge_c" \
     && [ -n "$lt" ] && printf '%s' "$lt" | grep -qF -- "attendue $vtxt_c"; then
    ok "cas 16 : $vge (1.0 < ${vge_c#"$_ge"}) et $vtxt (sans « $vtxt_c ») en MAUVAISE VERSION — rc 0 inchangé"
  else
    ko "cas 16 : mauvaise version (rc=$rc)"
    montre "$TMP/o16"
  fi
  # `--version` rend rc 3 sans numéro : le rc et la 1re ligne sont RAPPORTÉS, jamais jetés.
  stub "$TMP/b16" "${vge%%"$_pipe"*}" "aucun numero ici" 3
  run_doc "$TMP/o16b" linux "$TMP/b16"
  l="$(ligne_de "$TMP/o16b" "PRESENT" "$vge")"
  if [ -n "$l" ] && printf '%s' "$l" | grep -qF "version non mesurée (--version rc 3 : aucun numero ici)" && [ -z "$(ligne_de "$TMP/o16b" "MAUVAISE VERSION" "$vge")" ]; then
    ok "cas 16 : aucun numéro lisible, --version rc 3 — PRESENT, « version non mesurée » avec rc et 1re ligne, jamais un rouge"
  else
    ko "cas 16 : version illisible mal rapportée"
    montre "$TMP/o16b"
  fi
  # La 1re ligne rapportée perd ses caractères de contrôle (S-00004490) : ESC et
  # CR d'une sortie `--version` n'atteignent jamais le rapport.
  esc16=$'\033'
  cr16=$'\r'
  stub "$TMP/b16" "${vge%%"$_pipe"*}" "${esc16}[31mrouge${esc16}[0m${cr16}" 3
  run_doc "$TMP/o16c" linux "$TMP/b16"
  l="$(ligne_de "$TMP/o16c" "PRESENT" "$vge")"
  if [ -n "$l" ] && printf '%s' "$l" | grep -qF "version non mesurée (--version rc 3 : [31mrouge[0m)" \
     && ! grep -q "$esc16" "$TMP/o16c" && ! grep -q "$cr16" "$TMP/o16c"; then
    ok "cas 16 : 1re ligne de --version sans ESC ni CR dans le rapport (S-00004490)"
  else
    ko "cas 16 : caractère de contrôle de --version recopié dans le rapport"
    montre "$TMP/o16c"
  fi
  # Contrainte TEXTUELLE (S-00004538, C1) : la version rapportée sur la ligne
  # PRESENT comme sur la ligne MAUVAISE VERSION est la 1re ligne de --version,
  # sans OSC (ESC ] … BEL), sans CSI (ESC [ … m), sans CR. Le témoin d'avant
  # passait par la branche `>=` (rc 3, 1re ligne déjà filtrée) : il ne lisait
  # pas la version d'une contrainte textuelle.
  bel16=$'\007'
  stub "$TMP/b16" "${vtxt%%"$_pipe"*}" "${esc16}]0;titre${bel16}${esc16}[31mx 9.9 ${vtxt_c}${esc16}[0m${cr16}"
  run_doc "$TMP/o16d" linux "$TMP/b16"; rcd=$?
  stub "$TMP/b16" "${vtxt%%"$_pipe"*}" "${esc16}]0;titre${bel16}${esc16}[31mx 9.9 autre${esc16}[0m${cr16}"
  run_doc "$TMP/o16e" linux "$TMP/b16"; rce=$?
  lp="$(ligne_de "$TMP/o16d" "PRESENT" "$vtxt")"
  lm="$(ligne_de "$TMP/o16e" "MAUVAISE VERSION" "$vtxt")"
  nctl=0
  for f16 in "$TMP/o16d" "$TMP/o16e"; do
    for c16 in "$esc16" "$bel16" "$cr16"; do
      n16="$(LC_ALL=C grep -c "$c16" "$f16")"
      nctl=$((nctl + n16))
    done
  done
  if [ "$rcd" -eq 0 ] && [ "$rce" -eq 0 ] && [ "$nctl" -eq 0 ] \
     && printf '%s' "$lp" | grep -qF -- "version ]0;titre[31mx 9.9 ${vtxt_c}[0m, attendue $vtxt_c" \
     && printf '%s' "$lm" | grep -qF -- "version ]0;titre[31mx 9.9 autre[0m, attendue $vtxt_c"; then
    ok "cas 16 : contrainte textuelle ($vtxt) — PRESENT puis MAUVAISE VERSION, version rapportée sans ESC, BEL ni CR (S-00004538)"
  else
    ko "cas 16 : contrainte textuelle — caractère de contrôle ou version perdue dans le rapport (rc=$rcd/$rce, lignes portant ESC, BEL ou CR=$nctl)"
    montre "$TMP/o16d"
    montre "$TMP/o16e"
  fi
fi

# ---------------------------------------------------------------------------
# CAS 17 — la sonde cherche un fichier EXÉCUTABLE dans le PATH : ni builtin,
# ni mot-clé, ni fonction, ni fichier non exécutable seul
# ---------------------------------------------------------------------------
# Les quatre premières lignes de données deviennent `printf` (builtin), `if`
# (mot-clé), une fonction de doctor.sh et `nonexec-t1001`, classe B, os any,
# contrainte `-` (rien n'est exécuté). La sonde ne contient qu'un fichier
# `#!/bin/sh` en mode 644 nommé `nonexec-t1001`, AUCUN exécutable. Une sonde
# qui résout les builtins et les fonctions (`command -v`, la sonde d'avant) les
# dirait PRESENT ; `type -P` sans `[ -x ]` dirait PRESENT le fichier 644, faute
# d'exécutable du nom dans le PATH (relevé bash 5.3.15 et /bin/bash 3.2.57).
FN17='dr_probe'
NX17='nonexec-t1001'
if ! grep -q "^$FN17() " "$DOCTOR"; then
  ko "cas 17 : $FN17 n'est plus une fonction de doctor.sh — témoin de fonction vacant"
else
  awk -F'\t' -v OFS='\t' -v fn="$FN17" -v nx="$NX17" '
    /^#/ { print; next }
    !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
    NF > 1 && k < 4 { k++; $c["tool"] = (k == 1 ? "printf" : (k == 2 ? "if" : (k == 3 ? fn : nx))); $c["class"] = "B"; $c["os"] = "any"; $c["version"] = "-"; $c["mode_sonde"] = "-" }
    { print }
  ' "$INV" > "$TMP/i17"
  mkdir -p "$TMP/sonde17"
  printf '#!/bin/sh\nexit 0\n' > "$TMP/sonde17/$NX17"
  chmod 644 "$TMP/sonde17/$NX17"
  run_doc "$TMP/o17" linux "$TMP/sonde17" --inventory "$TMP/i17"; rc=$?
  manque=""
  for t in printf if "$FN17" "$NX17"; do
    [ -n "$(ligne_de "$TMP/o17" "ABSENT (requis)" "$t")" ] || manque="$manque $t"
  done
  if [ "$rc" -eq 1 ] && [ -z "$manque" ]; then
    ok "cas 17 : printf (builtin), if (mot-clé), $FN17 (fonction), $NX17 (fichier 644 seul) — ABSENT (requis) sous une sonde sans exécutable, rc 1"
  else
    ko "cas 17 : sonde qui résout un builtin, un mot-clé, une fonction ou un non-exécutable (rc=$rc, non ABSENT :${manque:- aucun})"
    montre "$TMP/o17"
  fi
  # Témoin de caractérisation de l'en-tête : le 644 placé AVANT un exécutable du
  # même nom est sauté, l'exécutable plus loin est PRESENT, son chemin rapporté.
  stub "$TMP/exe17" "$NX17" "x 1.0"
  run_doc "$TMP/o17b" linux "$TMP/sonde17:$TMP/exe17" --inventory "$TMP/i17"
  l="$(ligne_de "$TMP/o17b" "PRESENT" "$NX17")"
  case "$l" in
    *" — $TMP/exe17/$NX17")
      ok "cas 17 : $NX17 en 644 masqué par un exécutable plus loin dans le PATH — PRESENT, chemin de l'exécutable"
      ;;
    *)
      ko "cas 17 : non-exécutable masqué mal rapporté (« $l »)"
      montre "$TMP/o17b"
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# CAS 18 — DOCTOR_PROBE_PATH non posé : la sonde lit le PATH de l'appelant
# ---------------------------------------------------------------------------
# (S-00004538, C3 ; mutant D4 de plan-critic, S-00004518.) Tous les cas
# précédents posent DOCTOR_PROBE_PATH : un repli `${DOCTOR_PROBE_PATH:-}`, qui
# laisse la sonde sans PATH, les passerait tous. Inventaire-fixture d'UNE ligne
# outil, `repli-t1001`, classe B, os any, contrainte `-` : rien n'est exécuté et
# aucun outil réel n'est sondé ; canal apt sur les fixtures du cas 6.
NX18='repli-t1001'
awk -F'\t' -v OFS='\t' -v t="$NX18" '
  /^#/ { print; next }
  !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
  NF > 1 && !k { k = 1; $c["tool"] = t; $c["nature"] = "outil"; $c["class"] = "B"; $c["os"] = "any"; $c["version"] = "-"; $c["ci_pin"] = "-"; $c["mode_sonde"] = "-"; print }
' "$INV" > "$TMP/i18"
stub "$TMP/b18" "$NX18" "x 1.0"
env -u DOCTOR_PROBE_PATH DOCTOR_OS=linux "PATH=$TMP/b18:$PATH" bash "$DOCTOR" --inventory "$TMP/i18" \
  --ci "$TMP/ci/ci.yml" --verify "$TMP/ci/verify.sh" > "$TMP/o18" 2>&1; rc=$?
r="$(resume "$TMP/o18")"
l="$(ligne_de "$TMP/o18" "PRESENT" "$NX18")"
case "$l" in
  *" $NX18 — $TMP/b18/$NX18")
    l18=1
    ;;
  *)
    l18=0
    ;;
esac
if [ "$rc" -eq 0 ] && [ "$r" = "1 1 0 0" ] && [ "$l18" -eq 1 ]; then
  ok "cas 18 : DOCTOR_PROBE_PATH non posé — $NX18, sur le PATH de l'appelant seulement, PRESENT (son chemin), rc 0"
else
  ko "cas 18 : repli de la sonde sur le PATH de l'appelant (rc=$rc, résumé « $r », ligne « $l »)"
  montre "$TMP/o18"
fi

# ---------------------------------------------------------------------------
# CAS 19 — mode de sonde `module:` : le binaire du même nom ne prouve rien
# ---------------------------------------------------------------------------
# (Constat 1 de la passe de correction du lot 0 : un bouchon `pytest` sur le
# PATH rendait « PRESENT » alors que `python3 -m pytest` échouait.) Inventaire-
# fixture de DEUX lignes outil, classe B, os any, mode
# `module:absent-t19|interp-t19` : la 1re alternative n'existe pas, la 2e est
# l'interpréteur-bouchon, qui répond à `--version` (rc 0, la règle de la porte,
# cas 20) et ne connaît un module que si `lib-<module>` est posé à côté de lui.
# Aucun outil réel n'est sondé ni exécuté.
#   (a) binaires `mod-t19` et `modv-t19` sur la sonde, AUCUN module : ABSENT
#       (requis) tous deux, rc 1, la ligne cite l'interpréteur, son rc et sa
#       1re ligne. MUTANT : la colonne ignorée (`type -P` seul) → PRESENT → rouge ;
#   (b) modules posés, binaires retirés : PRESENT par `<interpréteur> -m <outil>`,
#       la version de `modv-t19` (>=2.0) lue dans la sortie de la sonde, rc 0 ;
#   (c) aucun interpréteur : ABSENT, « aucun interpréteur » nommé, rc 1.
NX19='mod-t19'
NV19='modv-t19'
IP19='interp-t19'
awk -F'\t' -v OFS='\t' -v m="$NX19" -v v="$NV19" -v ip="$IP19" '
  /^#/ { print; next }
  !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
  NF > 1 && k < 2 { k++; $c["tool"] = (k == 1 ? m : v); $c["nature"] = "outil"; $c["class"] = "B"; $c["os"] = "any"; $c["version"] = (k == 1 ? "-" : ">=2.0"); $c["ci_pin"] = "-"; $c["mode_sonde"] = "module:absent-t19|" ip; print }
' "$INV" > "$TMP/i19"
interp_stub() { # interp_stub <dir> <nom> : interpréteur-bouchon — `--version` rc 0 ; `-m <module> --version` rc 0 si `lib-<module>` est posé à côté
  mkdir -p "$1"
  printf '#!/bin/sh\nd=$(dirname "$0")\nif [ "$1" = "--version" ]; then echo "interp 3.12.0"; exit 0; fi\nif [ "$1" = "-m" ] && [ "$3" = "--version" ] && [ -e "$d/lib-$2" ]; then echo "$2 2.5.0"; exit 0; fi\necho "No module named $2" >&2\nexit 1\n' > "$1/$2"
  chmod +x "$1/$2"
}
interp_stub "$TMP/b19" "$IP19"
stub "$TMP/b19" "$NX19" "x 9.9.9"
stub "$TMP/b19" "$NV19" "x 9.9.9"
doc19() { # doc19 <sortie> <sonde> : rc du doctor sur l'inventaire-fixture
  run_doc "$1" linux "$2" --inventory "$TMP/i19" --ci "$TMP/ci/ci.yml" --verify "$TMP/ci/verify.sh"
}
doc19 "$TMP/o19a" "$TMP/b19"; rc=$?
la="$(ligne_de "$TMP/o19a" "ABSENT (requis)" "$NX19")"
lb="$(ligne_de "$TMP/o19a" "ABSENT (requis)" "$NV19")"
if [ "$rc" -eq 1 ] && [ -n "$la" ] && [ -n "$lb" ] \
   && printf '%s' "$la" | grep -qF -- "sonde module : $TMP/b19/$IP19 -m $NX19 --version, rc 1 : No module named $NX19"; then
  ok "cas 19a : binaires $NX19 et $NV19 sur la sonde, aucun module — ABSENT (requis), rc 1, interpréteur et rc cités"
else
  ko "cas 19a : un binaire du même nom passe pour le module (rc=$rc)"
  montre "$TMP/o19a"
fi
rm -f "$TMP/b19/$NX19" "$TMP/b19/$NV19"
: > "$TMP/b19/lib-$NX19"
: > "$TMP/b19/lib-$NV19"
doc19 "$TMP/o19b" "$TMP/b19"; rc=$?
la="$(grep -F "PRESENT" "$TMP/o19b" | grep -F " $NX19 — " | sed -n 1p)"
lb="$(grep -F "PRESENT" "$TMP/o19b" | grep -F " $NV19 — " | sed -n 1p)"
case "$la" in
  *" $NX19 — $TMP/b19/$IP19 -m $NX19")
    l19=1
    ;;
  *)
    l19=0
    ;;
esac
if [ "$rc" -eq 0 ] && [ "$l19" -eq 1 ] && printf '%s' "$lb" | grep -qF -- "-m $NV19 — version 2.5.0, attendue >=2.0"; then
  ok "cas 19b : modules posés, binaires absents — PRESENT par l'interpréteur (2e alternative), version lue dans la sortie de la sonde, rc 0"
else
  ko "cas 19b : module présent mal rapporté (rc=$rc, « $la » / « $lb »)"
  montre "$TMP/o19b"
fi
mkdir -p "$TMP/b19c"
stub "$TMP/b19c" "$NX19" "x 9.9.9"
doc19 "$TMP/o19c" "$TMP/b19c"; rc=$?
la="$(ligne_de "$TMP/o19c" "ABSENT (requis)" "$NX19")"
if [ "$rc" -eq 1 ] && printf '%s' "$la" | grep -qF -- "sonde module : aucun interpréteur absent-t19|$IP19 qui réponde à --version dans le PATH de la sonde"; then
  ok "cas 19c : aucun interpréteur — ABSENT (requis), nommé, rc 1, même avec le binaire $NX19"
else
  ko "cas 19c : interpréteur absent mal rapporté (rc=$rc, « $la »)"
  montre "$TMP/o19c"
fi

# ---------------------------------------------------------------------------
# CAS 20 — mode `module:` : l'interpréteur qui ne répond pas à `--version` est sauté
# ---------------------------------------------------------------------------
# (Constat T2/C2 de la revue de clôture du lot 0.) La porte
# (core-scripts/run-pytest-shards.sh, boucle `for c in python3 python py`) prend
# le PREMIER interpréteur qui répond rc 0 à `--version`. Sous Git Bash, `python3`
# peut être le bouchon du Microsoft Store, qui sort en rc 9 : la porte le saute
# et prend `python`. Inventaire-fixture d'UNE ligne outil, `pytest`, classe B,
# os any, mode `module:python3|python|py` (celui de l'inventaire réel) ; la sonde
# ne contient que des bouchons écrits ici, aucun interpréteur réel n'est exécuté.
#   (a) `python3` bouchon rc 9 (à tout argument) + `python` interpréteur-bouchon
#       avec `lib-pytest` : PRESENT par `python -m pytest`, rc 0.
#       MUTANT : la sonde retient le premier trouvé par nom (`dr_probe` seul) →
#       `python3 -m pytest --version`, rc 9 → ABSENT (requis), rc 1 → rouge ;
#   (b) `python` retiré : ABSENT (requis), rc 1, la note dit qu'aucun interpréteur
#       ne RÉPOND à `--version` — jamais « aucun interpréteur » quand `python3`
#       est sur la sonde.
awk -F'\t' -v OFS='\t' '
  /^#/ { print; next }
  !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; print; next }
  NF > 1 && !k { k = 1; $c["tool"] = "pytest"; $c["nature"] = "outil"; $c["class"] = "B"; $c["os"] = "any"; $c["version"] = "-"; $c["ci_pin"] = "-"; $c["mode_sonde"] = "module:python3|python|py"; print }
' "$INV" > "$TMP/i20"
stub "$TMP/b20" python3 "Python est introuvable ; exécutez sans argument pour l'installer depuis le Microsoft Store" 9
interp_stub "$TMP/b20" python
: > "$TMP/b20/lib-pytest"
doc20() { # doc20 <sortie> : rc du doctor sur l'inventaire-fixture, sonde $TMP/b20
  run_doc "$1" linux "$TMP/b20" --inventory "$TMP/i20" --ci "$TMP/ci/ci.yml" --verify "$TMP/ci/verify.sh"
}
doc20 "$TMP/o20a"; rc=$?
r="$(resume "$TMP/o20a")"
la="$(ligne_de "$TMP/o20a" "PRESENT" "pytest")"
case "$la" in
  *" pytest — $TMP/b20/python -m pytest")
    l20=1
    ;;
  *)
    l20=0
    ;;
esac
if [ "$rc" -eq 0 ] && [ "$r" = "1 1 0 0" ] && [ "$l20" -eq 1 ]; then
  ok "cas 20a : python3 rc 9 à --version, python répond — PRESENT par python -m pytest, rc 0 (la règle de la porte)"
else
  ko "cas 20a : interpréteur muet retenu (rc=$rc, résumé « $r », ligne « $la »)"
  montre "$TMP/o20a"
fi
rm -f "$TMP/b20/python"
doc20 "$TMP/o20b"; rc=$?
la="$(ligne_de "$TMP/o20b" "ABSENT (requis)" "pytest")"
if [ "$rc" -eq 1 ] && printf '%s' "$la" | grep -qF -- "sonde module : aucun interpréteur python3|python|py qui réponde à --version dans le PATH de la sonde"; then
  ok "cas 20b : seul python3 (rc 9) sur la sonde — ABSENT (requis), rc 1, « aucun interpréteur … qui réponde à --version »"
else
  ko "cas 20b : interpréteur muet seul mal rapporté (rc=$rc, « $la »)"
  montre "$TMP/o20b"
fi

# ---------------------------------------------------------------------------
# CAS 21 — LES MODULES DU PROJET (en-tête de doctor.sh) : hors du kit, l'outil
# de classe B en mode `module:` n'est exigé qu'avec un module de sa famille
# ---------------------------------------------------------------------------
# (T-01M5VYNMZPG8G0JZG48HV4K0PN, étape 1 ; constats C1, C12, C13, C14.) Arbre
# COPIÉ dans $TMP SANS .agents/IS_THE_KIT : doctor.sh et module_discovery.py,
# l'inventaire réel par --inventory. Sonde : bouchons des lignes B, SAUF la
# ligne en mode `module:` (à l'inventaire du 2026-10-26 : pytest) et ses
# alternatives d'interpréteur, que fournit un venv RÉEL sans pip (C13) — il
# répond à `--version`, il n'a pas le module. Chaque sous-cas asserte d'abord la
# ligne ABSENT de l'outil et SA section, puis `B manquants`.
#   (a) sans manifeste : `modules : aucun`, `hors classe B ici : <outil>`,
#       ABSENT (optionnel) en classe A, B manquants=aucun, rc 0 ; les deux
#       lignes AVANT le résumé, sans « présents, » (C12) : le dernier
#       `^doctor: .* présents, ` (setup.sh) est le résumé, la dernière ligne.
#       MUTANT : la classe effective ignorée → ABSENT (requis) → rouge ;
#   (b) pyproject.toml à la racine : `modules : python`, ABSENT (requis) en
#       classe B, B manquants=<outil>, rc 1. MUTANT : condition de famille
#       retirée (hors B dès qu'on est hors du kit) → rouge ;
#   (c) module_discovery.py absent : `modules : illisible`, classe B gardée.
#       MUTANT : illisible lu comme « aucun » → rouge ;
#   (d) marqueur du kit posé : `modules : aucun`, aucune ligne hors B, classe B
#       gardée. MUTANT : marqueur ignoré → rouge ;
#   (e) DOCTOR_DISCOVERY_DELAI=1 et une découverte-bouchon qui dort 12 s :
#       `modules : illisible`, « au-delà de la borne de 1 s », classe B gardée,
#       en moins de 10 s (C14). MUTANT : borne retirée (join sans délai) → la
#       découverte rend « aucun » après 12 s → rouge ;
#   (f) package.json et main.tf : `modules : npm,iac`, hors B. MUTANT : `iac`
#       jamais ajouté → rouge ;
#   (g) un json.py qui lève posé dans .agents/security, package.json :
#       `modules : npm`, rc 0 — la stdlib n'est pas masquée. MUTANT :
#       `sys.path.append(dossier)` → `sys.path.insert(0, dossier)` → le json.py
#       posé est importé par module_discovery → `modules : illisible` → rouge.
section_de() { # section_de <sortie> <outil> : B ou A, la section où l'outil est rapporté ; vide sinon
  awk -v t="$2" '
    /^Classe B — / { s = "B"; next }
    /^Classe A — / { s = "A"; next }
    /^Conditions — / { s = "" }
    s != "" && index($0, " " t " — ") { print s; exit }
  ' "$1"
}
MOD21="$(awk -F'\t' -v us="$US" '
  { sub(/\r$/, "") }
  /^#/ { next }
  !h { h = 1; for (i = 1; i <= NF; i++) c[$i] = i; next }
  $c["nature"] == "outil" && $c["class"] == "B" && $c["mode_sonde"] != "-" { m = $c["mode_sonde"]; sub(/^module:/, "", m); print $c["tool"] us m; exit }
' "$INV")"
T21="${MOD21%%"$US"*}"
ALTS21="${MOD21#*"$US"}"
PY21=""
for c21 in python3 python; do
  p21="$(command -v "$c21" 2>/dev/null)" || continue
  if "$p21" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    PY21="$p21"
    break
  fi
done
V21=""
if [ -n "$PY21" ] && "$PY21" -m venv --without-pip "$TMP/v21" >/dev/null 2>&1; then
  for d21 in "$TMP/v21/bin" "$TMP/v21/Scripts"; do
    [ -d "$d21" ] && V21="$d21"
  done
fi
if [ -z "$T21" ] || [ -z "$ALTS21" ] || [ "$T21" = "$MOD21" ]; then
  ko "cas 21 : aucune ligne outil de classe B en mode module: dans l'inventaire réel — le cas serait vacant"
elif [ -z "$V21" ]; then
  ko "cas 21 : aucun python3|python >= 3.9 sur ce poste qui crée un venv (« $PY21 ») — le cas exige un interpréteur réel (C13)"
else
  stub_all "$TMP/b21" linux first B
  rm -f "$TMP/b21/$T21"
  for a21 in ${ALTS21//$_pipe/ }; do
    rm -f "$TMP/b21/$a21"
  done
  A21="$TMP/a21"
  mkdir -p "$A21/core-scripts" "$A21/.agents/security"
  cp "$DOCTOR" "$A21/core-scripts/doctor.sh"
  cp "$ROOT/.agents/security/module_discovery.py" "$A21/.agents/security/module_discovery.py"
  doc21() { # doc21 <sortie> [VAR=valeur…] : rc du doctor de l'arbre copié, sonde bouchons + venv
    local out="$1"
    shift
    env "DOCTOR_OS=linux" "DOCTOR_PROBE_PATH=$TMP/b21:$V21" "$@" bash "$A21/core-scripts/doctor.sh" --inventory "$INV" > "$out" 2>&1
  }
  garde21() { # garde21 <sortie> <attendu : B|A> : la ligne ABSENT de l'outil, dans SA section, sondée par le venv
    local etat sec
    etat="ABSENT (requis)"
    [ "$2" = "A" ] && etat="ABSENT (optionnel)"
    sec="$(section_de "$1" "$T21")"
    [ "$sec" = "$2" ] && [ -n "$(ligne_de "$1" "$etat" "$T21")" ] \
      && grep -F -- " $T21 — " "$1" | grep -qF -- "$V21/"
  }
  b_manq21() { sed -n 's/^doctor: .*(B manquants=\([^,]*\), A manquants=.*$/\1/p' "$1"; }

  doc21 "$TMP/o21a"; rc=$?
  dern="$(grep '^doctor: .* présents, ' "$TMP/o21a" | sed -n '$p')"
  if garde21 "$TMP/o21a" A && [ "$(b_manq21 "$TMP/o21a")" = "aucun" ] && [ "$rc" -eq 0 ] \
     && grep -qx 'doctor: modules : aucun' "$TMP/o21a" \
     && grep -q "^doctor: hors classe B ici : $T21 — " "$TMP/o21a" \
     && [ "$(grep -E '^doctor: (modules|hors classe B ici) ' "$TMP/o21a" | grep -c 'présents, ')" -eq 0 ] \
     && [ -n "$dern" ] && [ "$(tail -n 1 "$TMP/o21a")" = "$dern" ]; then
    ok "cas 21a : hors du kit, sans manifeste — $T21 ABSENT (optionnel) en classe A, modules : aucun, hors classe B ici, B manquants=aucun, rc 0, le résumé reste la dernière ligne"
  else
    ko "cas 21a : hors du kit sans module, $T21 exigé ou lignes mal placées (rc=$rc, B manquants=« $(b_manq21 "$TMP/o21a") »)"
    montre "$TMP/o21a"
  fi

  printf '[project]\nname = "t21"\n' > "$A21/pyproject.toml"
  doc21 "$TMP/o21b"; rc=$?
  rm -f "$A21/pyproject.toml"
  if garde21 "$TMP/o21b" B && [ "$(b_manq21 "$TMP/o21b")" = "$T21" ] && [ "$rc" -eq 1 ] \
     && grep -qx 'doctor: modules : python' "$TMP/o21b" && ! grep -q '^doctor: hors classe B ici' "$TMP/o21b"; then
    ok "cas 21b : pyproject.toml — modules : python, $T21 ABSENT (requis) en classe B, B manquants=$T21, rc 1"
  else
    ko "cas 21b : un module python ne garde pas $T21 en classe B (rc=$rc, B manquants=« $(b_manq21 "$TMP/o21b") »)"
    montre "$TMP/o21b"
  fi

  mv "$A21/.agents/security/module_discovery.py" "$TMP/md21.py"
  doc21 "$TMP/o21c"; rc=$?
  mv "$TMP/md21.py" "$A21/.agents/security/module_discovery.py"
  if garde21 "$TMP/o21c" B && [ "$(b_manq21 "$TMP/o21c")" = "$T21" ] && [ "$rc" -eq 1 ] \
     && grep -qx 'doctor: modules : illisible' "$TMP/o21c" && ! grep -q '^doctor: hors classe B ici' "$TMP/o21c"; then
    ok "cas 21c : découverte absente — modules : illisible, $T21 reste en classe B (fail-closed), rc 1"
  else
    ko "cas 21c : découverte illisible lue comme lisible (rc=$rc, B manquants=« $(b_manq21 "$TMP/o21c") »)"
    montre "$TMP/o21c"
  fi

  : > "$A21/.agents/IS_THE_KIT"
  doc21 "$TMP/o21d"; rc=$?
  rm -f "$A21/.agents/IS_THE_KIT"
  if garde21 "$TMP/o21d" B && [ "$(b_manq21 "$TMP/o21d")" = "$T21" ] && [ "$rc" -eq 1 ] \
     && grep -qx 'doctor: modules : aucun' "$TMP/o21d" && ! grep -q '^doctor: hors classe B ici' "$TMP/o21d"; then
    ok "cas 21d : marqueur du kit posé — classes de l'inventaire inchangées, $T21 en classe B, rc 1"
  else
    ko "cas 21d : le marqueur du kit ne garde pas la classe B (rc=$rc, B manquants=« $(b_manq21 "$TMP/o21d") »)"
    montre "$TMP/o21d"
  fi

  A21E="$TMP/a21e"
  mkdir -p "$A21E/core-scripts" "$A21E/.agents/security"
  cp "$DOCTOR" "$A21E/core-scripts/doctor.sh"
  printf '%s\n' 'import time' 'FAMILIES = {}' 'def discover(racine):' '    time.sleep(12)' '    return {}' > "$A21E/.agents/security/module_discovery.py"
  t0=$SECONDS
  env "DOCTOR_OS=linux" "DOCTOR_PROBE_PATH=$TMP/b21:$V21" "DOCTOR_DISCOVERY_DELAI=1" bash "$A21E/core-scripts/doctor.sh" --inventory "$INV" > "$TMP/o21e" 2>&1; rc=$?
  duree=$((SECONDS - t0))
  if garde21 "$TMP/o21e" B && [ "$(b_manq21 "$TMP/o21e")" = "$T21" ] && [ "$rc" -eq 1 ] && [ "$duree" -lt 10 ] \
     && grep -qx 'doctor: modules : illisible' "$TMP/o21e" && grep -qF 'au-delà de la borne de 1 s' "$TMP/o21e"; then
    ok "cas 21e : découverte qui dort 12 s, borne 1 s — illisible en ${duree} s, $T21 reste en classe B, rc 1"
  else
    ko "cas 21e : la borne de la découverte ne tient pas (rc=$rc, ${duree} s, B manquants=« $(b_manq21 "$TMP/o21e") »)"
    montre "$TMP/o21e"
  fi

  printf '{}\n' > "$A21/package.json"
  : > "$A21/main.tf"
  doc21 "$TMP/o21f"; rc=$?
  rm -f "$A21/package.json" "$A21/main.tf"
  if garde21 "$TMP/o21f" A && [ "$(b_manq21 "$TMP/o21f")" = "aucun" ] && [ "$rc" -eq 0 ] \
     && grep -qx 'doctor: modules : npm,iac' "$TMP/o21f" && grep -q "^doctor: hors classe B ici : $T21 — " "$TMP/o21f"; then
    ok "cas 21f : package.json et main.tf — modules : npm,iac, $T21 hors classe B, rc 0"
  else
    ko "cas 21f : familles npm et iac mal rapportées (rc=$rc, « $(grep '^doctor: modules' "$TMP/o21f") »)"
    montre "$TMP/o21f"
  fi

  printf '%s\n' 'raise RuntimeError("json.py pose dans .agents/security")' > "$A21/.agents/security/json.py"
  printf '{}\n' > "$A21/package.json"
  doc21 "$TMP/o21g"; rc=$?
  rm -f "$A21/.agents/security/json.py" "$A21/package.json"
  if garde21 "$TMP/o21g" A && [ "$(b_manq21 "$TMP/o21g")" = "aucun" ] && [ "$rc" -eq 0 ] \
     && grep -qx 'doctor: modules : npm' "$TMP/o21g"; then
    ok "cas 21g : un json.py posé dans .agents/security ne masque pas la bibliothèque standard — modules : npm, $T21 hors classe B, rc 0"
  else
    ko "cas 21g : un json.py voisin de module_discovery.py masque la bibliothèque standard (rc=$rc, « $(grep '^doctor: modules' "$TMP/o21g") »)"
    montre "$TMP/o21g"
  fi
fi

echo
echo "doctor.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
