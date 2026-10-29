#!/usr/bin/env bash
# Banc de `affirmation-guard.sh` (T-00000602).
#
# CE QU'IL PROUVE, ET POURQUOI LES DEUX SENS SONT OBLIGATOIRES. Une garde dont
# on n'éprouve que le REFUS peut refuser TOUT — elle serait alors désarmée dans
# la semaine, ce qui est le mode de défaillance mesuré sur ce dépôt. Chaque
# témoin de refus a donc son CONTRÔLE NÉGATIF : le même arbre, la condition
# levée, et la garde doit rendre ZÉRO OCTET.
#
# L'arbre de fixture est un dépôt git JETABLE sous TMPDIR : le banc ne lit ni
# n'écrit jamais l'arbre réel. C'est la discipline « un banc ne voyage pas plus
# loin que son sujet ».
set -u

# `GIT_DIR` L'EMPORTE SUR `git -C` ET SUR LE CWD (critic-opus T1, T-00000695/696).
# Ce banc est ramassé par `core-scripts/run-bash-tests.sh`, appelé par
# `verify.sh`, lui-même appelable DEPUIS UN HOOK GIT — et git y exporte GIT_DIR.
# Sans ce nettoyage, `batir` commiterait dans le dépôt HÔTE. Même classe, même
# remède que `.githooks/commit-msg.test.sh:23-30`, liste de `conftest.py`.
# Plus les INJECTIONS de configuration : `git -c` exporte GIT_CONFIG_PARAMETERS à
# ses hooks, et GIT_CONFIG_COUNT + GIT_CONFIG_KEY_<n>/GIT_CONFIG_VALUE_<n> posent
# une clé au-dessus de la config locale du dépôt jetable (un `user.email`, par
# exemple). Les deux dernières se retirent par préfixe ; si `compgen` manquait,
# la boucle ne ferait rien, et sans GIT_CONFIG_COUNT git ne les lit pas.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE GIT_PREFIX \
  GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
for _git_var in $(compgen -e 2>/dev/null); do
  case "$_git_var" in
    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*)
      unset "$_git_var"
      ;;
  esac
done

RACINE_REELLE="$(cd "$(dirname "$0")/../.." && pwd)"
GARDE="$RACINE_REELLE/.claude/hooks/affirmation-guard.sh"
PASSES=0
ECHECS=0

echo "=== RUN  affirmation-guard.test.sh"

if [ ! -f "$GARDE" ]; then
  echo "FAIL: garde introuvable: $GARDE"
  exit 1
fi

py() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}
PY="$(py)" || { echo "SKIP: pas de python3 — la garde est advisory sans lui"; exit 0; }

# --- construction d'un arbre de fixture --------------------------------------
# $1 = chemin, $2 = forme du board (`dossier` : un fichier par enregistrement,
# T-00001012 ; défaut : le monolithe). Crée un dépôt git minimal, commité, avec
# board et PLAN-ETAT.
batir() {
  fixture="$1"
  forme="${2:-monolithe}"
  rm -rf "$fixture"
  mkdir -p "$fixture/.agents/state/gates"
  mkdir -p "$fixture/.agents/state/local/binome"
  mkdir -p "$fixture/.agents/state/board"
  (
    cd "$fixture" || exit 1
    git init -q .
    git config user.email banc@local
    git config user.name banc
    printf 'plan initial\n' > PLAN-ETAT.md
    printf 'detail initial\n' > PLAN-ETAT-DETAIL.md
    printf 'doctrine initiale\n' > AGENTS.md
    printf 'detail initial\n' > README-CLAUDE.md
    if [ "$forme" = "dossier" ]; then
      mkdir -p .agents/state/board/tasks
      printf '{"format": 1, "id": "T-001", "record": {"id": "T-001", "task": "a", "state": "pending"}, "sync_operations": []}\n' \
        > .agents/state/board/tasks/T-001.json
    else
      printf '{"tasks":[{"id":"T-001","task":"a","state":"pending"}]}\n' \
        > .agents/state/board/TASKS.json
    fi
    git add -A
    git commit -qm init
  ) || return 1
  # LE TAMPON PORTE UN SHA, et c'est ce qui ancre le DIFF. Sans lui, le banc
  # n'éprouvait que l'ancrage sur HEAD — c'est-à-dire précisément le défaut.
  fixture_sha="$(git -C "$fixture" rev-parse HEAD 2>/dev/null)"
  # `mode=frozen` MANQUAIT, et le filtre neuf l'a revele : un vrai tampon porte
  # TOUJOURS son mode (`core-scripts/verify.sh:127-131`), et la garde n'ancre
  # plus que sur un verdict FROZEN — la forme nue ecrit `live` avec le sha de
  # HEAD, ce qui la rendait aveugle. La fixture modelait donc un tampon qui
  # n'existe pas, et trois temoins ancres dessus mesuraient autre chose que ce
  # qu'ils annonçaient.
  {
    printf 'sha=%s\n' "$fixture_sha"
    printf 'mode=frozen\n'
    printf 'linux=1\n'
    printf 'at=2026-09-13T15:00:00Z\n'
  } > "$fixture/.agents/state/local/VERIFY_STAMP"
  # LE JOURNAL EST ÉCRIT AVEC LE TAMPON, comme `verify.sh::stamp_write` le fait
  # à CHAQUE porte — et il porte DEUX cycles. La fixture le supprimait : depuis
  # S-00001884 (D1), la fenêtre des critiques se lit comme
  # `tasks.py::cycle_precedent`, sur le JOURNAL SEUL, et moins de deux cycles =
  # PAS de borne (fenêtre de 12 h). Sans journal, les traces datées du
  # 2026-09-13 tombaient hors des 12 h et les cas 4 et 14 mesuraient l'ÂGE de la
  # fixture, plus la garde. Le cycle précédent est à 14:30 : les traces de 16:00
  # comptent, celles de 14:00 non — le cas 5 garde son sens.
  printf 'at=%s\tsha=%s\tmode=frozen\n' \
    "2026-09-13T14:30:00Z" "1111111111111111111111111111111111111111" \
    > "$fixture/.agents/state/local/VERIFY_STAMP.log"
  printf 'at=%s\tsha=%s\tmode=frozen\n' \
    "2026-09-13T15:00:00Z" "$fixture_sha" \
    >> "$fixture/.agents/state/local/VERIFY_STAMP.log"
  return 0
}

armer() { touch "$1/.agents/state/gates/AFFIRMATION_REQUIRED"; }

# $1 = fixture, $2 = nom de def, $3 = horodatage ISO
tracer() {
  printf '{"at": "%s", "sha": "abc1234"}\n' "$3" \
    > "$1/.agents/state/local/binome/T-012.$2.json"
}

salir_plan() { printf 'affirmation neuve\n' >> "$1/PLAN-ETAT.md"; }

# $1 = fixture. Ajoute une tâche NEUVE au board.
ajouter_tache() {
  printf '{"tasks":[{"id":"T-001","task":"a","state":"pending"},{"id":"T-999","task":"neuve","state":"pending"}]}\n' \
    > "$1/.agents/state/board/TASKS.json"
}

# FORME DOSSIER (T-00001012) — `board/tasks/<id>.json`, l'enveloppe de
# T-00001008 : `record` est la tâche, ou `null` pour une TOMBE.
# $1 = fixture, $2 = id, $3 = record (JSON, ou null).
poser_enregistrement() {
  mkdir -p "$1/.agents/state/board/tasks"
  printf '{"format": 1, "id": "%s", "record": %s, "sync_operations": []}\n' "$2" "$3" \
    > "$1/.agents/state/board/tasks/$2.json"
}

# $1 = fixture. La MIGRATION non commitée : monolithe supprimé, T-001 en dossier.
migrer_board() {
  rm -f "$1/.agents/state/board/TASKS.json"
  poser_enregistrement "$1" T-001 '{"id": "T-001", "task": "a", "state": "pending"}'
}

# $1 = fixture. Modifie une tâche EXISTANTE sans en ajouter.
restager_tache() {
  printf '{"tasks":[{"id":"T-001","task":"a","state":"pending","stage":"avance"}]}\n' \
    > "$1/.agents/state/board/TASKS.json"
}

# TÉMOIN DE CHARGE (T-01M55NVDW71B5BN8D5RTNTF67A). CAUSE : bash 3.2 applique l'expansion
# d'accolades `{A,B}` à une charge JSON en ligne entre guillemets doubles DANS un "$(…)"
# en argument ; la garde reçoit `"k":1`, pas un objet, et le verdict lu est faux. La charge
# va à python par STDIN, jamais interpolée dans le code `-c`. Hors objet JSON : consignée
# dans $CHARGES_NON_JSON, marqueur CHARGE-NON-JSON sur stdout, rc 1 (attendre_refus, cas 18).
# PORTÉE : 0a et 18 ne voient l'éclatement que sous bash 3.2 ; 0c, textuel, sous tout bash.
# BORNE : 17l'-désarmée-prof pipe sa charge sans `jouer`, hors témoin (forme printf, saine).
charge_valide() {
  if printf '%s' "$1" | "$PY" -c 'import json,sys; sys.exit(0 if isinstance(json.load(sys.stdin), dict) else 1)' 2>/dev/null; then
    return 0
  fi
  printf '%s\n' "$1" >> "$CHARGES_NON_JSON"
  printf 'CHARGE-NON-JSON: %s' "$1"
  return 1
}

jouer() {
  fixture="$1"
  charge="$2"
  charge_valide "$charge" || return 0
  printf '%s' "$charge" | bash "$GARDE" "$fixture" 2>/dev/null
}

# $1 = fixture, $2 = marqueur d'hôte (AGENTS_HOOK_HOST), $3 = charge.
jouer_hote() {
  charge_valide "$3" || return 0
  printf '%s' "$3" | AGENTS_HOOK_HOST="$2" bash "$GARDE" "$1" 2>/dev/null
}

# $1 = sessionId, $2 = transcriptPath. Forme de la charge `agentStop` Copilot (P4).
charge_copilot() {
  printf '{"sessionId":"%s","timestamp":1791811229849,"cwd":"/depot","transcriptPath":"%s","stopReason":"end_turn","stop_hook_active":false}' "$1" "$2"
}

# $1 = session_id, $2 = transcript_path (défaut : $TP_P4). Forme MESURÉE du `Stop` de
# `.claude/settings.json` exécuté par Copilot (P4, 2026-10-13, Copilot CLI 1.0.95) :
# copiée de `rt/copilot-via-claude/P4/Stop-081646-60919.json` (sous-agent) et
# `Stop-081652-61445.json` (racine), home -> /home/user, identifiants -> SID_RACINE /
# SID_SOUS_AGENT. Les deux charges ne diffèrent que par `session_id` et `timestamp` ;
# l'horodatage gardé est celui du sous-agent, la garde ne le lit pas.
charge_registre_claude_copilot() {
  printf '{"hook_event_name":"Stop","session_id":"%s","timestamp":"2026-10-13T06:16:44.740Z","cwd":"/home/user/.local/state/cadre/semaine/clones/rt-copilot","transcript_path":"%s","stop_reason":"end_turn","stop_hook_active":false}' "$1" "${2:-$TP_P4}"
}

# $1 = libellé, $2 = sortie observée
attendre_silence() {
  if [ -z "$2" ]; then
    echo "  PASS  $1"
    PASSES=$((PASSES + 1))
  else
    echo "  FAIL  $1 — attendu ZÉRO octet, obtenu: $2"
    ECHECS=$((ECHECS + 1))
  fi
}

# $1 = libellé, $2 = sortie observée, $3 = fragment attendu dans la raison
attendre_refus() {
  case "$2" in
    CHARGE-NON-JSON:*)
      echo "  FAIL  $1 — $2"
      ECHECS=$((ECHECS + 1))
      return
      ;;
  esac
  verdict="$(printf '%s' "$2" | "$PY" -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.stdout.write("PAS-DU-JSON"); raise SystemExit
sys.stdout.write(d.get("decision", "SANS-DECISION"))
' 2>/dev/null)"
  if [ "$verdict" != "block" ]; then
    echo "  FAIL  $1 — attendu decision=block, obtenu: ${verdict:-VIDE}"
    ECHECS=$((ECHECS + 1))
    return
  fi
  if printf '%s' "$2" | grep -q -- "$3"; then
    echo "  PASS  $1"
    PASSES=$((PASSES + 1))
  else
    echo "  FAIL  $1 — refus émis mais sans le fragment « $3 »"
    ECHECS=$((ECHECS + 1))
  fi
}

BASE="${TMPDIR:-/tmp}/affirmation-guard-banc"
rm -rf "$BASE"
mkdir -p "$BASE"
CHARGES_NON_JSON="$BASE/charges-non-json"
: > "$CHARGES_NON_JSON"

# =============================================================================
echo "--- 0. TÉMOIN DE CHARGE : il sait refuser ET laisser passer"
# =============================================================================
# 0a / 0a' / 0b — chacun en sous-shell, à journal propre : celui du banc reste vide.
_auto="$(CHARGES_NON_JSON="$BASE/autotest-1"; charge_valide '"sessionId":"x"')"; _rc=$?
if [ "$_rc" -eq 1 ] && [ "$_auto" = 'CHARGE-NON-JSON: "sessionId":"x"' ] && [ -s "$BASE/autotest-1" ]; then
  echo "  PASS  0a charge éclatée => marqueur, rc 1, consignée"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  0a charge éclatée non vue (rc=$_rc, sortie=$_auto)"
  ECHECS=$((ECHECS + 1))
fi
# 0a' — du JSON qui n'est pas un OBJET est refusé aussi. Mutant tué : `isinstance` retiré.
_auto="$(CHARGES_NON_JSON="$BASE/autotest-3"; charge_valide '[]')"; _rc=$?
if [ "$_rc" -eq 1 ] && [ "$_auto" = 'CHARGE-NON-JSON: []' ] && [ -s "$BASE/autotest-3" ]; then
  echo "  PASS  0a' JSON non objet => marqueur, rc 1, consignée"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  0a' JSON non objet accepté (rc=$_rc, sortie=$_auto)"
  ECHECS=$((ECHECS + 1))
fi
_auto="$(CHARGES_NON_JSON="$BASE/autotest-2"; charge_valide '{}')"; _rc=$?
if [ "$_rc" -eq 0 ] && [ -z "$_auto" ] && [ ! -e "$BASE/autotest-2" ]; then
  echo "  PASS  0b objet JSON => rien, rc 0"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  0b objet JSON refusé (rc=$_rc, sortie=$_auto)"
  ECHECS=$((ECHECS + 1))
fi
# 0c — contrôle TEXTUEL, jouable sous tout bash : aucune ligne hors commentaire ne porte
# un appel `jouer`/`jouer_hote` ET un guillemet échappé — forme compacte, JSON à espaces,
# espace en tête, affectation dans le "$(…)", quatre formes mesurées éclatées sous 3.2.
# BORNE : une ligne qui porterait les deux sans charge en ligne rougirait à tort ; aucune
# ici — une charge à guillemets échappés se pose en variable de niveau script (CHARGE_17D).
MOTIF_CHARGE_EN_LIGNE='(^|[^_[:alnum:]])jouer(_hote)?([^_[:alnum:]]|$).*[\\]"|[\\]".*[^_[:alnum:]]jouer(_hote)?([^_[:alnum:]]|$)'
charges_en_ligne() {
  grep -n -E "$MOTIF_CHARGE_EN_LIGNE" "$1" | grep -v -E '^[0-9]+:[[:space:]]*#'
}
_en_ligne=""
[ -f "$0" ] && _en_ligne="$(charges_en_ligne "$0")"
if [ ! -f "$0" ]; then
  echo "  FAIL  0c banc illisible par lui-même ($0)"
  ECHECS=$((ECHECS + 1))
elif [ -z "$_en_ligne" ]; then
  echo "  PASS  0c aucune charge JSON en ligne entre guillemets doubles"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  0c charge(s) JSON en ligne, éclatées sous bash 3.2 :"
  printf '%s\n' "$_en_ligne" | sed 's/^/        /'
  ECHECS=$((ECHECS + 1))
fi
# 0c' — CONTRÔLE POSITIF permanent de 0c : le MÊME motif, nourri des quatre formes
# (antislash écrit en octal, jamais en clair ici), d'une ligne saine et d'une ligne
# commentée, voit les lignes 1 à 4 et elles seules. Mutant tué : le motif muté.
_temoin_0c="$BASE/0c-temoin.txt"
printf '  "$(jouer "$FIX" "{\134"a\134":1,\134"b\134":2}")"\n' > "$_temoin_0c"
printf '  "$(jouer "$FIX" "{ \134"a\134": 1, \134"b\134": 2 }")"\n' >> "$_temoin_0c"
printf '  "$(jouer_hote "$FIX" copilot " {\134"a\134":1,\134"b\134":2}")"\n' >> "$_temoin_0c"
printf '  "$(C="{\134"a\134":1,\134"b\134":2}"; jouer "$FIX" "$C")"\n' >> "$_temoin_0c"
printf '  "$(jouer "$FIX" "$CHARGE_17D")"\n' >> "$_temoin_0c"
printf '# "$(jouer "$FIX" "{\134"a\134":1,\134"b\134":2}")"\n' >> "$_temoin_0c"
_vues="$(charges_en_ligne "$_temoin_0c" | cut -d: -f1 | tr '\n' ' ')"
if [ "$_vues" = "1 2 3 4 " ]; then
  echo "  PASS  0c' le motif de 0c voit les quatre formes éclatées, ni la saine ni le commentaire"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  0c' motif de 0c aveugle — lignes vues : [$_vues], attendu [1 2 3 4 ]"
  ECHECS=$((ECHECS + 1))
fi

# =============================================================================
echo "--- 1. DÉSARMÉE : l'absence du marqueur EST le régime de référence"
# =============================================================================
FIX="$BASE/f1"
batir "$FIX" || { echo "FAIL: fixture"; exit 1; }
salir_plan "$FIX"
# CONTRÔLE ARMÉ APPARIÉ (constat du binôme, 22/09) : le MÊME arbre, armé, est
# REFUSÉ. Sans lui, une garde qui ne refuserait plus rien laisserait le silence
# ci-dessous vert — un témoin qui ne peut pas rougir.
armer "$FIX"
attendre_refus "contrôle : le même arbre ARMÉ => block" "$(jouer "$FIX" '{}')" "PLAN-ETAT.md"
rm -f "$FIX/.agents/state/gates/AFFIRMATION_REQUIRED"
attendre_silence "désarmée + PLAN-ETAT sale => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 2. ARMÉE mais rien de touché — CONTRÔLE NÉGATIF"
# =============================================================================
FIX="$BASE/f2"
batir "$FIX" || exit 1
armer "$FIX"
attendre_silence "armée + arbre propre => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 3. TÉMOIN : PLAN-ETAT sale, aucune trace => REFUS"
# =============================================================================
FIX="$BASE/f3"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
attendre_refus "PLAN-ETAT sale + 0 critique => block" "$(jouer "$FIX" '{}')" "PLAN-ETAT.md"

# =============================================================================
echo "--- 3bis. TÉMOIN : PLAN-ETAT-DETAIL sale, aucune trace => REFUS"
# =============================================================================
# SANS CE TÉMOIN, LE CORRECTIF ANTI-ÉCHAPPATOIRE EST DÉCORATIF. Le split du
# 2026-09-14 a sorti la file, les décisions closes et les points ouverts de
# `PLAN-ETAT.md` : si la garde ne regardait que l'ancien nom, tout l'état
# durable s'écrivait désormais hors de son champ. Relevé par le binôme :
# revenir à `PLAN_ETAT = "PLAN-ETAT.md"` laissait TOUS les arms verts.
FIX="$BASE/f3bis"
batir "$FIX" || exit 1
armer "$FIX"
printf 'affirmation neuve\n' >> "$FIX/PLAN-ETAT-DETAIL.md"
attendre_refus "PLAN-ETAT-DETAIL sale + 0 critique => block" \
  "$(jouer "$FIX" '{}')" "PLAN-ETAT-DETAIL.md"

# =============================================================================
echo "--- 4. CONTRÔLE NÉGATIF du 3 : deux critiques POSTÉRIEURS au tampon"
# =============================================================================
FIX="$BASE/f4"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
tracer "$FIX" critic-opus 2026-09-13T16:00:00Z
tracer "$FIX" critic-fable 2026-09-13T16:01:00Z
attendre_silence "même arbre + 2 critiques frais => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 5. L'ANCRAGE MORD : deux critiques ANTÉRIEURS au tampon => REFUS"
# =============================================================================
FIX="$BASE/f5"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
tracer "$FIX" critic-opus 2026-09-13T14:00:00Z
tracer "$FIX" critic-fable 2026-09-13T14:01:00Z
attendre_refus "2 critiques mais avant la porte => block" "$(jouer "$FIX" '{}')" "porte verte"

# =============================================================================
echo "--- 6. UN critique (BINOME_MIN, S-00004500) suffit : zéro octet"
# =============================================================================
# INVERSÉ PAR T-00001226 : la paire est abandonnée par décision pilote. Le refus à
# ZÉRO critique reste éprouvé par le cas 3 ; ce cas-ci rougit si le hook exige 2.
FIX="$BASE/f6"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
tracer "$FIX" critic-opus 2026-09-13T16:00:00Z
attendre_silence "1 seul critique frais => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 7. BOARD : une tâche AJOUTÉE mord"
# =============================================================================
FIX="$BASE/f7"
batir "$FIX" || exit 1
armer "$FIX"
ajouter_tache "$FIX"
attendre_refus "tâche ajoutée => block" "$(jouer "$FIX" '{}')" "T-999"

# =============================================================================
echo "--- 8. CONTRÔLE NÉGATIF du 7 : un stage NE mord PAS"
# =============================================================================
FIX="$BASE/f8"
batir "$FIX" || exit 1
armer "$FIX"
restager_tache "$FIX"
attendre_silence "board modifié sans id neuf => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 9. DOCTRINE : AGENTS.md mord"
# =============================================================================
FIX="$BASE/f9"
batir "$FIX" || exit 1
armer "$FIX"
printf 'regle neuve\n' >> "$FIX/AGENTS.md"
attendre_refus "AGENTS.md sale => block" "$(jouer "$FIX" '{}')" "AGENTS.md"

# =============================================================================
echo "--- 9bis. DOCTRINE : README-CLAUDE.md mord (T-00000838)"
# =============================================================================
# Le détail de CLAUDE.md y a déménagé : LISTÉ ne suffit pas, il doit MORDRE.
FIX="$BASE/f9bis"
batir "$FIX" || exit 1
armer "$FIX"
printf 'detail neuf\n' >> "$FIX/README-CLAUDE.md"
attendre_refus "README-CLAUDE.md sale => block" "$(jouer "$FIX" '{}')" "README-CLAUDE.md"

# =============================================================================
echo "--- 10. BOUCLE : un Stop déjà bloqué ne se rebloque pas"
# =============================================================================
FIX="$BASE/f10"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
# CONTRÔLE ARMÉ APPARIÉ : la MÊME charge sans `stop_hook_active` est REFUSÉE.
attendre_refus "contrôle : même arbre, stop_hook_active=false => block" \
  "$(jouer "$FIX" '{"stop_hook_active":false}')" "PLAN-ETAT.md"
attendre_silence "stop_hook_active=true => zéro octet" \
  "$(jouer "$FIX" '{"stop_hook_active":true}')"

# =============================================================================
echo "--- 11. SORTIE TRACÉE : consommée UNE fois, et JOURNALISÉE"
# =============================================================================
FIX="$BASE/f11"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
printf 'doublon evident\n' > "$FIX/.agents/state/gates/AFFIRMATION_SANS_BINOME"
attendre_silence "sortie présente => zéro octet" "$(jouer "$FIX" '{}')"

if [ -f "$FIX/.agents/state/gates/AFFIRMATION_SANS_BINOME" ]; then
  echo "  FAIL  la sortie n'a pas été CONSOMMÉE"
  ECHECS=$((ECHECS + 1))
else
  echo "  PASS  la sortie est consommée"
  PASSES=$((PASSES + 1))
fi

if grep -q "doublon evident" "$FIX/.agents/state/local/affirmation-sorties.log" 2>/dev/null; then
  echo "  PASS  la raison est JOURNALISÉE, donc visible pour toujours"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  la raison n'est pas journalisée — la sortie serait muette"
  ECHECS=$((ECHECS + 1))
fi

echo "--- 11bis. et elle ne vaut QU'UNE fois : le tour suivant refuse"
attendre_refus "sortie déjà consommée => block" "$(jouer "$FIX" '{}')" "PLAN-ETAT.md"

# =============================================================================
echo "--- 12. LE COMMIT NE DÉSARME PAS LA GARDE — le défaut le plus grave"
# =============================================================================
# Trouvé par le binôme de clôture. La garde comparait à HEAD : un tour qui
# écrivait PLAN-ETAT PUIS commitait ne montrait plus rien, donc elle se taisait.
# C'était un FAUX VERT — pire qu'une garde absente. Elle s'ancre désormais sur le
# SHA du tampon, donc le commit ne l'aveugle plus.
FIX="$BASE/f12"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
attendre_refus "avant le commit => block" "$(jouer "$FIX" '{}')" "PLAN-ETAT.md"
(
  cd "$FIX" || exit 1
  git add -A
  git commit -qm "une affirmation commitee"
) >/dev/null 2>&1
attendre_refus "APRÈS le commit => block AUSSI" "$(jouer "$FIX" '{}')" "PLAN-ETAT.md"

echo "--- 12bis. et une tâche ajoutée PUIS commitée mord encore"
FIX="$BASE/f12b"
batir "$FIX" || exit 1
armer "$FIX"
ajouter_tache "$FIX"
(
  cd "$FIX" || exit 1
  git add -A
  git commit -qm "board commite"
) >/dev/null 2>&1
attendre_refus "tâche ajoutée puis commitée => block" "$(jouer "$FIX" '{}')" "T-999"

# =============================================================================
echo "--- 13. VOCABULAIRE CLOS : un nom hors liste ne compte pas"
# =============================================================================
FIX="$BASE/f13"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
tracer "$FIX" critic-maison 2026-09-13T16:01:00Z
attendre_refus "critic-maison seul ne compte pas => block" "$(jouer "$FIX" '{}')" "REVUE CRITIQUE"

# =============================================================================
echo "--- 14. SANS SLOT running, LE REPLI _sans-slot SATISFAIT LA GARDE"
# =============================================================================
# T-00000603 (2), relevé du binôme de clôture. CETTE GARDE MORD SUR `tasks.py
# new`, un geste qui PRÉCÈDE tout `start` — donc sur une session neuve, aucune
# tâche ne tourne, et `binome-trace.sh` sortait sans rien écrire. Le binôme était
# lancé, il tournait pour de vrai, et la garde rebloquait « 0 critique » : la
# seule issue devenait la dérogation À CHAQUE FOIS, c'est-à-dire une garde
# DÉCORATIVE. Masqué jusqu'ici parce qu'un chantier se trouvait être `running`.
#
# Le traceur écrit désormais sous `_sans-slot`, qui n'est PAS un identifiant de
# tâche : cette garde-ci le voit (elle relève tous les `*.<critique>.json` et ne
# lit que le dernier segment), et `tasks.py done` ne le voit jamais.
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
printf '{"at": "2026-09-13T16:00:00Z", "sha": "abc1234"}\n' \
  > "$FIX/.agents/state/local/binome/_sans-slot.critic-opus.json"
SORTIE_SANS_SLOT="$(jouer "$FIX" '{}')"
if printf '%s' "$SORTIE_SANS_SLOT" | grep -q '"block"'; then
  echo "  FAIL  la garde refuse un critique tracé hors slot — elle reste décorative"
  ECHECS=$((ECHECS + 1))
else
  echo "  PASS  un critique hors slot suffit (BINOME_MIN) : la garde n'est plus décorative"
  PASSES=$((PASSES + 1))
fi
# CONTRÔLE NÉGATIF : AUCUN critique du vocabulaire hors slot ne suffit toujours pas.
# Sans lui, le cas ci-dessus passerait avec une garde qui aurait cessé de compter.
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
printf '{"at": "2026-09-13T16:00:00Z", "sha": "abc1234"}\n' \
  > "$FIX/.agents/state/local/binome/_sans-slot.critic-maison.json"
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  PASS  zéro critique du vocabulaire hors slot est toujours refusé"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  le repli a fait sauter le compte des critiques"
  ECHECS=$((ECHECS + 1))
fi

# =============================================================================
echo "--- 14bis. SANS TAMPON, UNE VIEILLE TRACE NE VAUT PLUS PREUVE"
# =============================================================================
# LE TROU LE PLUS GRAVE DE CE LOT, trouvé par le binôme et MESURÉ par lui :
# `critiques_depuis` faisait `if borne is None or quand > borne`. Or `borne` vaut
# None quand `VERIFY_STAMP` est ABSENT — l'état PAR DÉFAUT d'un dépôt adoptant,
# ce fichier étant git-ignoré. Toute trace comptait donc, quel que soit son âge :
# deux traces datées de 2020 faisaient passer la garde sans un octet de refus,
# EN PERMANENCE, chez tout adoptant.
#
# CE N'EST PAS LE REPLI `_sans-slot` QUI L'A CRÉÉ — le trou vaut pour n'importe
# quelle trace, y compris un `T-….critic-opus.json` oublié. On mesure donc les
# DEUX, sinon le témoin ne dirait rien de la classe qu'on a corrigée.
# « SANS TAMPON » = ni `VERIFY_STAMP` ni son journal : c'est l'état de
# l'adoptant (les deux sont git-ignorés), et `batir` écrit désormais les deux.
batir "$FIX" || exit 1
rm -f "$FIX/.agents/state/local/VERIFY_STAMP" "$FIX/.agents/state/local/VERIFY_STAMP.log"
armer "$FIX"
salir_plan "$FIX"
tracer "$FIX" critic-opus 2020-01-01T10:00:00Z
tracer "$FIX" critic-fable 2020-01-01T10:01:00Z
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  PASS  sans tampon, deux traces de 2020 sont REFUSÉES"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  la garde est désarmée à vie sur un dépôt sans tampon"
  ECHECS=$((ECHECS + 1))
fi
# MÊME CAS SOUS LE NOM RÉSERVÉ : le repli ne doit pas être un raccourci.
batir "$FIX" || exit 1
rm -f "$FIX/.agents/state/local/VERIFY_STAMP" "$FIX/.agents/state/local/VERIFY_STAMP.log"
armer "$FIX"
salir_plan "$FIX"
printf '{"at": "2020-01-01T10:00:00Z", "sha": "abc1234"}\n' \
  > "$FIX/.agents/state/local/binome/_sans-slot.critic-opus.json"
printf '{"at": "2020-01-01T10:01:00Z", "sha": "abc1234"}\n' \
  > "$FIX/.agents/state/local/binome/_sans-slot.critic-fable.json"
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  PASS  le repli _sans-slot périmé est REFUSÉ comme les autres"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  le repli _sans-slot est une preuve immortelle"
  ECHECS=$((ECHECS + 1))
fi
# CONTRÔLE NÉGATIF — sans lui, une garde qui refuse TOUT passerait les deux cas
# ci-dessus, et la fenêtre de 12 h serait indistinguable d'un refus permanent.
batir "$FIX" || exit 1
rm -f "$FIX/.agents/state/local/VERIFY_STAMP" "$FIX/.agents/state/local/VERIFY_STAMP.log"
armer "$FIX"
salir_plan "$FIX"
_MAINTENANT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
tracer "$FIX" critic-opus "$_MAINTENANT"
tracer "$FIX" critic-fable "$_MAINTENANT"
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  FAIL  sans tampon, une revue DE MAINTENANT est refusée — garde inutilisable"
  ECHECS=$((ECHECS + 1))
else
  echo "  PASS  sans tampon, une revue fraîche passe : c'est une fenêtre, pas un mur"
  PASSES=$((PASSES + 1))
fi

# =============================================================================
echo "--- 14quater. UN TAMPON EN MODE LIVE NE DOIT PAS DÉSARMER LA GARDE"
# =============================================================================
# LE FAUX VERT LE PLUS GRAVE DE CE LOT, trouvé par le binôme. La forme NUE de
# `verify.sh` mesure l'arbre vivant et écrit `sha=$HEAD_FULL` + `mode=live` — un
# verdict que `.githooks/pre-push` refuse déjà. Cette garde ne lisait que `sha=`
# et `at=`, donc après une forme nue son ancrage redevenait HEAD : le tour
# commite, `git diff HEAD` ne montre plus rien, et la garde se tait SANS avoir
# compté un seul critique. C'est mot pour mot l'état aveugle que sa propre
# docstring dit avoir fermé. `tasks.py` filtrait déjà ce mode pour sa borne : les
# deux moitiés du même design ne lisaient pas le même tampon.
batir "$FIX" || exit 1
armer "$FIX"
# LE JOURNAL PORTE LE DERNIER VERDICT HONNÊTE — c'est ce sur quoi la garde doit
# retomber. `stamp_write` y écrit TOUS les verdicts avec leur mode, donc le
# repli filtre `frozen` comme le fait déjà `tasks.py` pour sa propre borne.
_SHA_ANCRE="$( cd "$FIX" && git rev-parse HEAD )"
printf 'at=%s\tsha=%s\tmode=frozen\n' "2026-09-14T00:00:00Z" "$_SHA_ANCRE" \
  > "$FIX/.agents/state/local/VERIFY_STAMP.log"
salir_plan "$FIX"
( cd "$FIX" && git add -A >/dev/null 2>&1 \
  && git -c user.email=b@b -c user.name=b commit -qm "ecriture commitee" >/dev/null 2>&1 )
_SHA_LIVE="$( cd "$FIX" && git rev-parse HEAD )"
{ printf 'sha=%s\n' "$_SHA_LIVE"; printf 'mode=live\n'; printf 'linux=1\n'
  printf 'at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; } \
  > "$FIX/.agents/state/local/VERIFY_STAMP"
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  PASS  un tampon mode=live ne devient pas l'ancrage — la garde mord encore"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  la forme nue de verify.sh DÉSARME la garde : faux vert"
  ECHECS=$((ECHECS + 1))
fi
# CONTRÔLE NÉGATIF : le MÊME tampon en `frozen` sur le MÊME sha doit, lui, servir
# d'ancrage — sinon on aurait juste rendu la garde sourde à tout tampon.
{ printf 'sha=%s\n' "$_SHA_LIVE"; printf 'mode=frozen\n'; printf 'linux=1\n'
  printf 'at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; } \
  > "$FIX/.agents/state/local/VERIFY_STAMP"
if printf '%s' "$(jouer "$FIX" '{}')" | grep -q '"block"'; then
  echo "  FAIL  un tampon frozen sur le commit courant devrait rendre le diff VIDE"
  ECHECS=$((ECHECS + 1))
else
  echo "  PASS  un tampon frozen sert bien d'ancrage — le filtre n'a pas rendu sourd"
  PASSES=$((PASSES + 1))
fi

# =============================================================================
echo "--- 14ter. LA COUVERTURE ANNONCÉE EST CELLE QUI VOYAGE"
# =============================================================================
# Relevé du binôme : la liste des surfaces de doctrine en compte SEPT, dont TROIS
# sont `strip:` dans `.template-exclude` — donc absentes de tout dépôt adoptant.
# Pas de faux positif (un fichier qui n'existe pas ne change jamais), mais une
# couverture ANNONCÉE que le code ne tient pas là où il voyage. Ce témoin lie la
# déclaration de la garde à `.template-exclude`, les deux seules surfaces qui
# décident : si l'une bouge sans l'autre, il rougit.
_HOOK="$(dirname "$0")/affirmation-guard.sh"
_EXCL="$(dirname "$0")/../../.template-exclude"
_VOYAGENT=0
_ABSENTES=0
for _s in "AGENTS.md" "CLAUDE.md" "GEMINI.md" "README-CLAUDE.md" \
          "docs/PROMPT-refonte-packaging-cadre.md" \
          "docs/interne/classification.md" \
          ".agents/evals/classification_rules.py"; do
  grep -q "\"$_s\"" "$_HOOK" || { echo "  FAIL  $_s a quitté la liste"; ECHECS=$((ECHECS + 1)); }
  # `strip:` COUVRE un chemin exact OU un répertoire qui le préfixe. On construit
  # la liste des préfixes candidats plutôt que d'écrire un `case` en ligne : le
  # `case` collé est l'une des HUIT formes de bash valide que le parseur du SAST
  # ne lit pas, et UN seul site retire le fichier ENTIER du compte des cibles
  # inspectées — la porte annonce alors « clean » sur ce qu'elle n'a pas lu.
  # Mesuré à l'instant : c'est ce qui a rougi la porte sur ce banc même.
  _COUVERT=0
  _REP="$_s"
  while [ "$_REP" != "." ] && [ "$_REP" != "/" ] && [ -n "$_REP" ]; do
    grep -q "^strip: $_REP\$" "$_EXCL" && _COUVERT=1
    grep -q "^strip: $_REP/\$" "$_EXCL" && _COUVERT=1
    _SUIV="$(dirname "$_REP")"
    [ "$_SUIV" = "$_REP" ] && break
    _REP="$_SUIV"
  done
  if [ "$_COUVERT" -eq 1 ]
  then _ABSENTES=$((_ABSENTES + 1))
  else _VOYAGENT=$((_VOYAGENT + 1))
  fi
done
_DIT="$(grep -c '^SURFACES_QUI_VOYAGENT = '"$_VOYAGENT"'$' "$_HOOK")"
if [ "$_ABSENTES" -eq 3 ] && [ "$_VOYAGENT" -eq 4 ] && [ "$_DIT" -eq 1 ]; then
  echo "  PASS  7 surfaces déclarées, 4 qui voyagent, et la garde le DIT"
  PASSES=$((PASSES + 1))
else
  echo "  FAIL  voyagent=$_VOYAGENT absentes=$_ABSENTES déclaré=$_DIT — la couverture annoncée ment"
  ECHECS=$((ECHECS + 1))
fi

# =============================================================================
echo "--- 16. FORMES DU BOARD (T-00001012) : une tâche AJOUTÉE mord sous les deux"
# =============================================================================
# Un board passé en un fichier par enregistrement (`board/tasks/<id>.json`,
# domicile S-01M4N1G4VXD01A3W54Y9FR9856) doit mordre comme le monolithe, y
# compris la forme MIXTE du commit de migration. L'union porte sur les ENTRÉES
# (ids du monolithe ∪ noms du dossier, à l'arbre comme à la BASE), puis
# `arbre − base`. A1, A2, A4 et A5 sont ROUGES à la base ; A3 et A6 sont des
# CONTRÔLES verts à la base.
# A1 — dossier → dossier. Mutant tué : M-dossier-ignoré.
FIX="$BASE/fa1"
batir "$FIX" dossier || exit 1
armer "$FIX"
poser_enregistrement "$FIX" T-999 '{"id": "T-999", "task": "neuve", "state": "pending"}'
attendre_refus "A1 board en dossier + T-999.json non suivi => block" "$(jouer "$FIX" '{}')" "T-999"
# A2 — MIXTE : BASE monolithe {T-001}, arbre migré + T-999. Mutant tué :
# M-mono-seul (le dossier n'est lu que si le monolithe manque à la BASE aussi).
FIX="$BASE/fa2"
batir "$FIX" || exit 1
armer "$FIX"
migrer_board "$FIX"
poser_enregistrement "$FIX" T-999 '{"id": "T-999", "task": "neuve", "state": "pending"}'
attendre_refus "A2 migration + T-999 => block" "$(jouer "$FIX" '{}')" "T-999"
# A3 — CONTRÔLE : migration SANS ajout, une TOMBE (`record: null`) comprise.
# Mutant tué : M-tombe-comptée.
FIX="$BASE/fa3"
batir "$FIX" || exit 1
armer "$FIX"
migrer_board "$FIX"
poser_enregistrement "$FIX" T-177 null
attendre_silence "A3 migration sans ajout + tombe T-177 => zéro octet" "$(jouer "$FIX" '{}')"
# A4 — DEUX FORMES : monolithe inchangé + `tasks/T-999.json`. Mutant tué :
# M-union-absente (le monolithe présent fait taire le dossier).
FIX="$BASE/fa4"
batir "$FIX" || exit 1
armer "$FIX"
poser_enregistrement "$FIX" T-999 '{"id": "T-999", "task": "neuve", "state": "pending"}'
attendre_refus "A4 monolithe inchangé + T-999.json => block" "$(jouer "$FIX" '{}')" "T-999"
# A5 — un candidat ILLISIBLE compte (fermeture prudente). Mutant tué :
# M-illisible-sauté.
FIX="$BASE/fa5"
batir "$FIX" || exit 1
armer "$FIX"
migrer_board "$FIX"
printf '{' > "$FIX/.agents/state/board/tasks/T-998.json"
attendre_refus "A5 migration + T-998.json illisible => block" "$(jouer "$FIX" '{}')" "T-998"
# A6 — CONTRÔLE : des noms POINTÉS seuls (le temporaire d'une écriture atomique ;
# `.T-996.json` porte le suffixe, sans quoi le filtre de point ne serait pas
# éprouvé). Mutant tué : M-point-compté.
FIX="$BASE/fa6"
batir "$FIX" || exit 1
armer "$FIX"
mkdir -p "$FIX/.agents/state/board/tasks"
printf '{}\n' > "$FIX/.agents/state/board/tasks/.T-997.json.tmp"
printf '{}\n' > "$FIX/.agents/state/board/tasks/.T-996.json"
attendre_silence "A6 noms pointés seuls => zéro octet" "$(jouer "$FIX" '{}')"
# A7 — K1 (exec-critic T-00001012) : BASE = le dernier vert, monolithe {T-001} ;
# la migration ET l'ajout de T-999 sont COMMITÉS après lui (le hook de `done`
# commite les magasins à chaque `done`). `BASE:tasks/` manque alors que
# `BASE:TASKS.json` y est : le dossier est NÉ après BASE et s'y lit VIDE, jamais
# à HEAD, où T-999 est déjà. Rouge avant le correctif (repli HEAD : silence).
# Mutant tué : ag-base-dossier-lu-a-head.
FIX="$BASE/fa7"
batir "$FIX" || exit 1
armer "$FIX"
migrer_board "$FIX"
poser_enregistrement "$FIX" T-999 '{"id": "T-999", "task": "neuve", "state": "pending"}'
git -C "$FIX" add -A -- .agents/state/board && git -C "$FIX" commit -qm "migration + T-999" || exit 1
attendre_refus "A7 migration + T-999 COMMITÉS après le dernier vert => block" "$(jouer "$FIX" '{}')" "T-999"
# A7c — CONTRÔLE : la même migration commitée SANS ajout => zéro octet (T-001
# est au monolithe de BASE). Mutant tué : un dossier né après BASE compté en entier.
FIX="$BASE/fa7c"
batir "$FIX" || exit 1
armer "$FIX"
migrer_board "$FIX"
git -C "$FIX" add -A -- .agents/state/board && git -C "$FIX" commit -qm "migration" || exit 1
attendre_silence "A7c migration commitée sans ajout => zéro octet" "$(jouer "$FIX" '{}')"

# =============================================================================
echo "--- 17. COPILOT : l'agentStop d'un SOUS-AGENT passe, celui de la racine refuse"
# =============================================================================
# Canari P4 (2026-10-12, alignement des hôtes, lot L2) : Copilot émet `agentStop`
# AUSSI à la fin de chaque sous-agent. La charge porte alors le `sessionId` du
# sous-agent, mais le `transcriptPath` de la session RACINE
# (`…/session-state/<id racine>/events.jsonl`). Chaque cas garde l'arbre SALE et
# SANS critique : seul le discriminant décide entre le refus et le silence.
SID_RACINE="412fbc8b-fdbe-4a0f-837e-085056ae4429"
SID_SOUS_AGENT="af8e4d9a-0536-414f-9d0f-9eea7fda1a67"
TP_P4="/home/user/.copilot/session-state/$SID_RACINE/events.jsonl"
FIX="$BASE/f17"
batir "$FIX" || exit 1
armer "$FIX"
salir_plan "$FIX"
attendre_silence "17a copilot, sous-agent (sessionId ≠ dossier du transcript) => zéro octet" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_SOUS_AGENT" "$TP_P4")")"
# 17b — CONTRÔLE APPARIÉ : la session racine, même arbre. Mutant tué : la
# comparaison inversée (la racine passerait, le sous-agent serait bloqué).
attendre_refus "17b copilot, racine (sessionId = dossier du transcript) => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_RACINE" "$TP_P4")")" "PLAN-ETAT.md"
# 17c — PORTÉE : la même charge sous un autre hôte est refusée. Mutant tué : le
# test du marqueur `copilot` retiré.
attendre_refus "17c même charge de sous-agent, hôte codex => block" \
  "$(jouer_hote "$FIX" codex "$(charge_copilot "$SID_SOUS_AGENT" "$TP_P4")")" "PLAN-ETAT.md"
# 17d — CHAMP ABSENT : sans `transcriptPath`, comportement d'avant (refus).
CHARGE_17D="{\"sessionId\":\"$SID_SOUS_AGENT\",\"stop_hook_active\":false}"
attendre_refus "17d copilot, sessionId sans transcriptPath => block" \
  "$(jouer_hote "$FIX" copilot "$CHARGE_17D")" "PLAN-ETAT.md"
# 17e — AUTRE DISPOSITION du transcript (parent qui n'a pas la forme d'un
# identifiant de session) : rien n'est déduit, refus. Mutant tué : le test de
# forme retiré (une disposition plate désarmerait la garde racine).
attendre_refus "17e copilot, transcript sans dossier de session => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_SOUS_AGENT" "/home/user/.copilot/session-state/events.jsonl")")" "PLAN-ETAT.md"
# 17f — SÉPARATEUR WINDOWS (DÉDUIT, jamais mesuré sur un hôte) : lu aussi.
TP_WIN='C:\\Users\\user\\.copilot\\session-state\\412fbc8b-fdbe-4a0f-837e-085056ae4429\\events.jsonl'
attendre_silence "17f copilot, sous-agent, chemin Windows => zéro octet" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_SOUS_AGENT" "$TP_WIN")")"
attendre_refus "17f' copilot, racine, chemin Windows => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_RACINE" "$TP_WIN")")" "PLAN-ETAT.md"
# 17g — INVERSÉ (P4, 2026-10-13). Le `Stop` de `.claude/settings.json` exécuté par
# Copilot est MESURÉ en snake_case (17l ci-dessous) ; l'ancien filtre camelCase,
# jamais vu sur ce registre, est retiré. Une charge camelCase sans marqueur d'hôte
# (la forme `agentStop` hors de sa jambe) est donc JUGÉE, même avec un transcript
# Copilot. Mutant tué (ME) : le bras camelCase remis.
attendre_refus "17g charge camelCase, marqueur absent => block (bras camelCase retiré)" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_copilot "$SID_RACINE" "$TP_P4")")" "PLAN-ETAT.md"
# 17h — CONTRÔLE APPARIÉ : la charge Claude (snake_case) sans marqueur reste
# jugée. Mutant tué : le filtre élargi à toute charge sans marqueur.
attendre_refus "17h charge Claude sans marqueur => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" '{"session_id":"abc","transcript_path":"/x/t.jsonl","stop_hook_active":false}')" "PLAN-ETAT.md"
# 17h' — une charge qui porte `session_id` ET `sessionId` reste jugée. Mutant
# tué : le bras camelCase remis sans son test `"session_id" not in charge`.
CHARGE_17H2="{\"session_id\":\"abc\",\"sessionId\":\"$SID_RACINE\",\"transcript_path\":\"/x/t.jsonl\",\"stop_hook_active\":false}"
attendre_refus "17h' charge aux deux graphies sans marqueur => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$CHARGE_17H2")" "PLAN-ETAT.md"
# 17i — transcript d'UN SEUL morceau : aucun dossier parent, refus. Mutant tué
# (XA1) : la garde de longueur retirée (IndexError, stdout vide = silence).
attendre_refus "17i copilot, transcript d'un seul morceau => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_SOUS_AGENT" "events.jsonl")")" "PLAN-ETAT.md"
# 17j — `sessionId` VIDE sous un dossier de session : refus. Mutant tué (XA2) :
# le test de chaîne vide retiré (la chaîne vide diffère du dossier).
attendre_refus "17j copilot, sessionId vide => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "" "$TP_P4")")" "PLAN-ETAT.md"
# 17k — dossier parent qui COMMENCE par un identifiant de session mais n'en est
# pas un : refus. Mutant tué (XA3) : l'ancre `\Z` de la forme retirée.
attendre_refus "17k copilot, dossier <uuid>-copie => block" \
  "$(jouer_hote "$FIX" copilot "$(charge_copilot "$SID_SOUS_AGENT" "/home/user/.copilot/session-state/$SID_RACINE-copie/events.jsonl")")" "PLAN-ETAT.md"

# --- 17l à 17q'' : le `Stop` de `.claude/settings.json` exécuté par Copilot ------
# MESURÉ (P4, 2026-10-13, Copilot CLI 1.0.95, macOS) : il tire DEUX fois (fin du
# sous-agent, puis racine), charge snake_case SANS marqueur d'hôte, transcript sous
# `~/.copilot/session-state/<id racine>/events.jsonl`. Cette jambe se tait en fin de
# sous-agent ; à la racine, SEULEMENT si `.github/hooks/agent-guardrails.json` câble
# la garde sur `agentStop` (17l', 17l'-nu, 17l'-nul). Même arbre SALE et SANS
# critique : seul le discriminant décide entre le refus et le silence.
# 17l / 17l' — les deux charges MESURÉES. Mutant tué (MA) : le prédicat qui rend False.
attendre_silence "17l registre Claude sous Copilot, Stop du SOUS-AGENT (P4 mesuré) => zéro octet" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_SOUS_AGENT")")"
mkdir -p "$FIX/.github/hooks"
printf '{"version":1,"hooks":{"agentStop":[{"type":"command","bash":"AGENTS_HOOK_HOST=copilot bash .claude/hooks/affirmation-guard.sh \\"$PWD\\""}]}}' \
  > "$FIX/.github/hooks/agent-guardrails.json"
attendre_silence "17l' registre Claude sous Copilot, RACINE, jambe agentStop câblée => zéro octet" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")"
rm -rf "$FIX/.github"
# 17l'-nu — MÊME charge racine, SANS `.github/hooks/` : la jambe du registre Claude est
# alors la SEULE à juger la racine sous Copilot. Mutant tué : `_jambe_native_enregistree`
# qui rend True (retour de la borne « sans .github/hooks/, plus de garde »).
attendre_refus "17l'-nu registre Claude sous Copilot, RACINE, SANS jambe agentStop => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
# 17l'-nul — registre natif PRÉSENT, `agentStop` à `null` : sa lecture ne doit pas
# PLANTER (le crochet `_refus_de_panne` n'est posé qu'APRÈS l'armement : un plantage
# ici rend zéro octet, garde muette) ; aucune jambe câblée => la racine est jugée.
mkdir -p "$FIX/.github/hooks"
printf '{"version":1,"hooks":{"agentStop":null}}' > "$FIX/.github/hooks/agent-guardrails.json"
attendre_refus "17l'-nul registre Claude sous Copilot, RACINE, agentStop null => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
rm -rf "$FIX/.github"
# 17l'-prof — registre natif imbriqué PROFOND (400 Ko, sous la borne) : `json.loads`
# lève RecursionError AVANT `_refus_de_panne` ; elle doit rendre False, jamais planter
# (security-code-review, HIGH classe 1). Attendu : la racine est jugée.
mkdir -p "$FIX/.github/hooks"
"$PY" -c 'import sys
with open(sys.argv[1], "w") as fh:
    fh.write("[" * 200000 + "]" * 200000)
' "$FIX/.github/hooks/agent-guardrails.json"
attendre_refus "17l'-prof registre Claude sous Copilot, RACINE, registre natif imbriqué profond => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
# 17l'-désarmée-prof — MÊME registre, garde DÉSARMÉE : le marqueur est testé AVANT
# `copilot_par_le_registre_claude`, désarmée elle ne LIT pas le registre. Relevé sur
# stdout ET stderr : ni octet ni trace (79c44cc3 y écrivait la trace RecursionError).
rm -f "$FIX/.agents/state/gates/AFFIRMATION_REQUIRED"
attendre_silence "17l'-désarmée-prof garde DÉSARMÉE, registre natif imbriqué profond => ni octet ni trace stderr" \
  "$(unset AGENTS_HOOK_HOST; charge_registre_claude_copilot "$SID_RACINE" | bash "$GARDE" "$FIX" 2>&1)"
armer "$FIX"
rm -rf "$FIX/.github"
# 17l'-gros — registre natif VALIDE qui câble la garde, mais de plus de 1 Mo : la
# lecture est BORNÉE, un registre hors borne vaut « non câblé ». Mutant tué : la
# borne retirée (le fichier serait lu en entier et la racine tue).
mkdir -p "$FIX/.github/hooks"
"$PY" -c 'import json, sys
jambe = {"type": "command", "bash": "AGENTS_HOOK_HOST=copilot bash .claude/hooks/affirmation-guard.sh \"$PWD\""}
with open(sys.argv[1], "w") as fh:
    json.dump({"version": 1, "bourre": "x" * 1100000, "hooks": {"agentStop": [jambe]}}, fh)
' "$FIX/.github/hooks/agent-guardrails.json"
attendre_refus "17l'-gros registre Claude sous Copilot, RACINE, registre natif câblé > 1 Mo => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
rm -rf "$FIX/.github"
# 17l'-espaces — registre câblé VALIDE suivi de 1,1 Mo d'ESPACES : tronqué à la borne,
# il resterait du JSON VALIDE et câblé ; seule la comparaison de longueur le refuse.
# Mutant tué : `if len(brut) > _REGISTRE_NATIF_MAX` retiré (17l'-gros, lui, devient du
# JSON invalide une fois tronqué et ne le voit pas).
mkdir -p "$FIX/.github/hooks"
"$PY" -c 'import json, sys
jambe = {"type": "command", "bash": "AGENTS_HOOK_HOST=copilot bash .claude/hooks/affirmation-guard.sh \"$PWD\""}
with open(sys.argv[1], "w") as fh:
    json.dump({"version": 1, "hooks": {"agentStop": [jambe]}}, fh)
    fh.write(" " * 1100000)
' "$FIX/.github/hooks/agent-guardrails.json"
attendre_refus "17l'-espaces registre Claude sous Copilot, RACINE, registre câblé + 1,1 Mo d'espaces => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
rm -rf "$FIX/.github"
# 17l'-fifo — un FIFO à la place du registre natif : `open()` y bloquerait sans fin
# (la garde, tuée au délai de l'hôte, serait MUETTE) ; un fichier RÉGULIER est exigé.
# Sauté, et DIT, sous Windows (FIFO MSYS face à un Python natif : NON MESURÉ) ou sans
# `mkfifo`. DÉBLOQUEUR : une régression (FIFO ouvert) ROUGIT au lieu de figer — après
# 10 s, un écrivain lui livre un registre CÂBLÉ, la garde lit « câblé » et se tait.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) FIFO_JOUABLE=0 ;;
  *) FIFO_JOUABLE=1 ;;
esac
mkdir -p "$FIX/.github/hooks"
if [ "$FIFO_JOUABLE" -eq 1 ] && mkfifo "$FIX/.github/hooks/agent-guardrails.json" 2>/dev/null; then
  ( sleep 10; printf '%s' '{"hooks":{"agentStop":[{"bash":"affirmation-guard.sh"}]}}' > "$FIX/.github/hooks/agent-guardrails.json" ) </dev/null >/dev/null 2>&1 &
  DEBLOQUEUR=$!
  attendre_refus "17l'-fifo registre Claude sous Copilot, RACINE, registre natif FIFO => block" \
    "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE")")" "PLAN-ETAT.md"
  kill "$DEBLOQUEUR" 2>/dev/null; wait "$DEBLOQUEUR" 2>/dev/null
else
  echo "  SKIP  17l'-fifo — FIFO non jouable sur cet hôte (Windows ou mkfifo absent)"
fi
rm -rf "$FIX/.github"
# 17l'' — séparateur Windows (DÉDUIT, jamais mesuré sur un hôte) : lu aussi.
attendre_silence "17l'' registre Claude sous Copilot, chemin Windows => zéro octet" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_SOUS_AGENT" "$TP_WIN")")"
# 17m — la charge `Stop` Codex MESURÉE (X1, 2026-10-12, `rt/codex/X1/Stop-140349-93563.json`),
# home -> /home/user, model -> gpt-6-sol, `last_assistant_message` abrégé (la garde ne lit
# ni l'un ni l'autre), jouée
# SANS marqueur : un transcript `~/.codex/sessions/…` n'est jamais pris pour Copilot.
CHARGE_CODEX_X1='{"session_id":"01a12fff-13e9-7311-87d6-2bddb11e8d81","turn_id":"01a12fff-1477-7fe3-bd9b-ac93d3ce22d1","transcript_path":"/home/user/.codex/sessions/2026/10/12/rollout-2026-10-12T14-03-28-01a12fff-13e9-7311-87d6-2bddb11e8d81.jsonl","cwd":"/home/user/.local/state/cadre/semaine/clones/rt-codex","hook_event_name":"Stop","model":"gpt-6-sol","permission_mode":"bypassPermissions","stop_hook_active":false,"last_assistant_message":"COVERAGE DEGRADED — restitution directe, sous-agent interdit."}'
attendre_refus "17m charge Codex X1 mesurée, marqueur absent => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$CHARGE_CODEX_X1")" "PLAN-ETAT.md"
# 17m' — la forme Claude Code (transcript `~/.claude/projects/<slug>/<uuid>.jsonl`,
# `permission_mode`) : la garde racine sous Claude n'est jamais affaiblie.
CHARGE_17M2="{\"session_id\":\"$SID_RACINE\",\"transcript_path\":\"/home/user/.claude/projects/-depot/$SID_RACINE.jsonl\",\"cwd\":\"/depot\",\"hook_event_name\":\"Stop\",\"permission_mode\":\"default\",\"stop_hook_active\":false}"
attendre_refus "17m' forme Claude Code (~/.claude/projects, permission_mode) => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$CHARGE_17M2")" "PLAN-ETAT.md"
# 17m'' — dossier de config Claude RELOCALISÉ (`CLAUDE_CONFIG_DIR`, cinq sur ce poste),
# avec `timestamp` et SANS `permission_mode`. Mutant tué (MD) : le bras négatif
# « hors /.claude/projects/ + timestamp + sans permission_mode » remis.
attendre_refus "17m'' config Claude relocalisée (~/.claude-work), timestamp, sans permission_mode => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE" "/home/user/.claude-work/projects/-depot/$SID_RACINE.jsonl")")" "PLAN-ETAT.md"
# 17n — slug de projet Claude qui CONTIENT « copilot-session-state ». Mutant tué (MB) :
# la paire de segments remplacée par une sous-chaîne du chemin.
attendre_refus "17n slug Claude contenant copilot-session-state => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE" "/home/user/.claude/projects/-depot-copilot-session-state/$SID_RACINE.jsonl")")" "PLAN-ETAT.md"
# 17o — la charge P4 du sous-agent sous un AUTRE marqueur d'hôte. Mutant tué (MC) : le
# test `AGENTS_HOOK_HOST` retiré.
attendre_refus "17o charge P4 du sous-agent, hôte codex => block" \
  "$(jouer_hote "$FIX" codex "$(charge_registre_claude_copilot "$SID_SOUS_AGENT")")" "PLAN-ETAT.md"
# 17p — état Copilot RELOCALISÉ (`COPILOT_HOME` / `--config-dir`, honorés par Copilot
# 1.0.95 ; forme DÉDUITE) : la fin `session-state/<UUID>/events.jsonl` suffit.
attendre_silence "17p état Copilot relocalisé (session-state/<uuid>/events.jsonl) => zéro octet" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_SOUS_AGENT" "/srv/cophome/session-state/$SID_RACINE/events.jsonl")")"
# 17q / 17q' / 17q'' — un SEUL des deux segments, ou les deux NON consécutifs, ou une
# fin qui n'est pas `session-state/<UUID>/events.jsonl` : refus. Mutants tués : MF
# (`"session-state" in morceaux`), MG (`".copilot" in morceaux`), MH (paire non consécutive).
attendre_refus "17q session-state sans .copilot, transcript Claude => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE" "/home/user/session-state/.claude/projects/-depot/$SID_RACINE.jsonl")")" "PLAN-ETAT.md"
attendre_refus "17q' .copilot sans session-state, transcript Claude => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE" "/home/user/.copilot/.claude/projects/-depot/$SID_RACINE.jsonl")")" "PLAN-ETAT.md"
attendre_refus "17q'' .copilot et session-state NON consécutifs => block" \
  "$(unset AGENTS_HOOK_HOST; jouer "$FIX" "$(charge_registre_claude_copilot "$SID_RACINE" "/home/user/.copilot/x/session-state/$SID_RACINE.jsonl")")" "PLAN-ETAT.md"

# =============================================================================
echo "--- 18. AUCUNE CHARGE NON JSON N'A ÉTÉ JOUÉE"
# =============================================================================
# Ferme les sites hors `attendre_*` (`grep -q '"block"'`, cas 14 à 14quater) où le
# marqueur CHARGE-NON-JSON serait avalé : toute charge refusée par `jouer` est consignée.
if [ -s "$CHARGES_NON_JSON" ]; then
  echo "  FAIL  18 charge(s) non JSON — la garde n'a pas été jouée pour :"
  sed 's/^/        /' "$CHARGES_NON_JSON"
  ECHECS=$((ECHECS + 1))
else
  echo "  PASS  18 toute charge jouée était un objet JSON"
  PASSES=$((PASSES + 1))
fi

# =============================================================================
echo "--- 15. NON-VACUITÉ : la garde sait refuser ET laisser passer"
# =============================================================================
# Si tous les cas rendaient la même chose, le banc serait vert sans rien prouver.
if [ "$PASSES" -ge 12 ] && [ "$ECHECS" -eq 0 ]; then
  echo "  PASS  les deux sens sont éprouvés (refus ET silence)"
  PASSES=$((PASSES + 1))
fi

echo "================================================================"
echo "affirmation-guard: $PASSES passed / $ECHECS failed"
[ "$ECHECS" -eq 0 ] || exit 1
exit 0
