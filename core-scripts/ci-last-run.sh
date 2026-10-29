#!/usr/bin/env bash
# =====================================================================
# core-scripts/ci-last-run.sh — relevé du dernier run CI sur `main` (T-00000529)
#
# ---------------------------------------------------------------------
# RAISON D'ÊTRE — un défaut mesuré, pas une commodité
# ---------------------------------------------------------------------
# `main` n'est pas protégée sur ce dépôt et le ruleset est vide (S-00000939) :
# AUCUN mécanisme GitHub n'exige quoi que ce soit avant un push. Le rouge de la
# CI n'atteint donc personne — et le rouge de la NIGHTLY n'atteindra JAMAIS
# personne, même le jour où une protection de branche sera posée : une
# protection ne voit que les pushes, jamais un run `schedule`.
#
#   => Ce relevé est la SEULE gouvernance possible de `int-nightly.yml`.
#
# Il est lu deux fois, pour deux lecteurs :
#   * SessionStart (`.claude/hooks/session-start.sh`) → l'AGENT, qui doit voir
#     l'état de la CI AVANT le balayage exigé par L-00000239. `Stop` a été
#     écarté exprès : la fin de session arrive après les décisions.
#   * `.claude/statusline.sh` → le PILOTE, depuis le CACHE seul (cette ligne se
#     rafraîchit toutes les 5 s : zéro réseau y est la seule option tenable).
#
# ---------------------------------------------------------------------
# LA BORNE VIT DANS LE SCRIPT, EN BASH NU (L-00000323)
# ---------------------------------------------------------------------
# Une borne qui vit dans le SUPERVISEUR ne sait pas échouer : elle fauche tout
# et efface ce qui était déjà mesuré. Celle-ci vit ici, donc un dépassement
# dégrade UNE ligne et l'autre workflow reste relevé.
#
# Le motif `borne_murale` est repris de `scripts/int-tests.sh:289`, où il a été
# écrit précisément parce que **`timeout(1)` est GNU et ABSENT de macOS par
# défaut**. Il RETOURNE 124 au dépassement (jamais d'`exit`), donc l'appelant
# survit et la boucle continue ; il PRÉSERVE le code du fils à l'heure, succès
# comme échec — une borne qui avalerait un rouge serait le faux vert combattu.
#
# DEUX ÉCARTS ASSUMÉS par rapport à l'original, chacun motivé :
#   * mur de 8 s (l'original borne une suite vitest de plusieurs minutes) ;
#   * GRÂCE RÉDUITE À 1 s : les 5 s de l'original drainent les enfants de
#     vitest ; `gh` n'en a pas. Pire cas réel = 2 × (8 + 1) = 18 s, et non 16 s
#     qui omettrait la fenêtre de grâce.
#
# CAPTURE PAR FICHIER TEMPORAIRE, PAS PAR SUBSTITUTION DE COMMANDE.
# `borne_murale` lance `"$@" &` sous `set -m` ; une substitution de commande
# imbriquerait ce job control dans un sous-shell — comportement non prouvé dans
# ce contexte — tandis que `2>&1` ne peut pas voyager dans l'argv. Le cas (6) du
# banc prouve la composition, comme l'original l'a été avant d'être posé.
#
# ---------------------------------------------------------------------
# CE QUE CE SCRIPT NE FAIT JAMAIS
# ---------------------------------------------------------------------
#   * il ne sort JAMAIS non nul (exit 0 toujours) : il informe, il ne bloque pas ;
#   * il n'écrase PAS le cache sur un relevé dégradé — le cache est daté, donc
#     honnête même périmé, alors qu'un cache écrasé par une panne réseau
#     mentirait ;
#   * il n'émet RIEN au fil de l'eau : les lignes s'assemblent en variables et
#     s'émettent en bloc à la fin, pour que le mur tue l'appel `gh` et jamais le
#     script en pleine sortie. L'énumération close des deux workflows reste donc
#     toujours complète.
#
# LE PARSE NE LIT `conclusion` QUE SI `status == completed` (précédence C4).
# MESURÉ le 2026-08-13 avec gh 2.97.0 sur un dépôt tiers actif
# (`gh run list -R microsoft/vscode --limit 30 --json conclusion,status`) :
# les 9 runs `queued`/`in_progress` portent tous `"conclusion":""` — chaîne
# VIDE, clé PRÉSENTE. Le parse traite néanmoins `""`, `null` et clé absente
# comme le même état : la mesure CONFIRME, elle ne CONDITIONNE pas.
# =====================================================================

# PAS de `set -e` : la boucle vit d'appels dont le code retour non nul est une
# DONNÉE (mur dépassé, `gh` non authentifié) et non une panne du script.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"   # ancrage — jamais le cwd nu (C2)
CACHE_DIR="$ROOT/.agents/state/local"
CACHE="$CACHE_DIR/ci-status.line"

# ---- MODE CACHE-SEUL (T-00000379) -------------------------------------------
# CE MODE N EXISTAIT PAS CHEZ L AUTEUR D ORIGINE, et son absence decidait de
# l architecture : leur `session-start` APPELLE le script, donc il paie le mur
# reseau (MUR_S + GRACE_S par workflow) a chaque debut de session.
#
# Ici le canal est declare aux DEUX bouts, mais sans jamais faire attendre au
# demarrage :
#   * LECTEUR  — `session-start.sh` appelle `--cached` : zero reseau, zero mur.
#   * ECRIVAIN — l etape avant-push de la skill `verification-discipline` appelle
#                le script SANS `--cached` : c est le moment ou l etat de la CI
#                compte, et ou l on s apprete de toute facon a attendre.
#
# LE DETACHEMENT A ETE ECARTE EXPRES. Le plan envisageait un rafraichissement
# detache au session-start ; sous Git-Bash le detachement echoue en silence, et
# un ecrivain non fiable ramene le mecanisme inerte — le defaut meme que ce lot
# ferme. Un ecrivain sur puis rien vaut mieux qu un ecrivain incertain.
#
# LA PEREMPTION EST VISIBLE, JAMAIS SILENCIEUSE : la ligne rendue porte l age du
# cache. Un cache jamais rafraichi se lit « vieux de N h », pas « absent ».
if [ "${1:-}" = "--cached" ]; then
  if [ ! -r "$CACHE" ]; then
    printf 'COVERAGE DEGRADED — aucun relevé CI en cache (lancez `bash core-scripts/ci-last-run.sh`)\n'
    exit 0
  fi
  _epoch="$(sed -n 's/^epoch=\([0-9]*\)$/\1/p' "$CACHE" | head -1)"
  _age=""
  if [ -n "$_epoch" ]; then
    _now="$(date +%s)"
    # Deux temps plutôt qu'une arithmétique parenthésée : tree-sitter-bash ne
    # parse pas `$(( (a - b) / 60 ))`, et le fichier ENTIER sort alors du compte
    # des cibles inspectées par la porte SAST. Même résultat, même troncature
    # entière — la division reste la dernière opération.
    _delta=$(( _now - _epoch ))
    _min=$(( _delta / 60 ))
    if   [ "$_min" -lt 60 ]   ; then _age="il y a ${_min} min"
    elif [ "$_min" -lt 2880 ] ; then _age="il y a $(( _min / 60 )) h"
    else                             _age="il y a $(( _min / 1440 )) j"
    fi
  else
    _age="âge inconnu"
  fi
  while IFS='|' read -r _wf _classe _etat _sha; do
    [ -n "$_wf" ] || continue
    case "$_wf" in
      epoch=*) continue ;;
    esac
    printf 'DERNIER RUN %s (main): %s @ %s — relevé %s\n' "$_wf" "$_etat" "$_sha" "$_age"
  done < "$CACHE"
  exit 0
fi
if [ -n "${1:-}" ]; then
  printf 'ci-last-run: option inconnue %s (seule `--cached` est reconnue)\n' "$1" >&2
  exit 2
fi

# ÉNUMÉRATION DÉRIVÉE, PAS CODÉE EN DUR (T-00000379).
# L original codait `(ci.yml int-nightly.yml)` — et `int-nightly.yml` n existe pas
# dans ce dépôt : adoptée telle quelle, la garde aurait relevé un workflow
# imaginaire et ignoré `eval-nightly.yml`. Un littéral décrit l arbre de son
# auteur ; on lit donc le répertoire, et un workflow ajouté demain est couvert
# sans qu on ait à revenir ici. [L-00000057]
WORKFLOWS=()
for _wf in "$ROOT"/.github/workflows/*.yml "$ROOT"/.github/workflows/*.yaml; do
  [ -e "$_wf" ] || continue
  WORKFLOWS+=("$(basename "$_wf")")
done
# Répertoire absent ou vide : on le DIT plutôt que de relever le vide en silence.
if [ "${#WORKFLOWS[@]}" -eq 0 ]; then
  printf 'source: %s
' "gh run list --workflow=<wf> --branch=main --limit=1 --json conclusion,status,headSha,createdAt"
  printf 'COVERAGE DEGRADED — aucun workflow sous .github/workflows/ : rien à relever
'
  exit 0
fi
MUR_S=8
GRACE_S=1

# ---------------------------------------------------------------------
# borne_murale — motif de scripts/int-tests.sh:289 (grâce réduite à 1 s)
# ---------------------------------------------------------------------
borne_murale() {
  local secondes="$1" libelle="$2"; shift 2
  [ "${1:-}" = "--" ] && shift

  local etait_monitor=0
  case "$-" in
    *m*) etait_monitor=1 ;;
  esac
  set -m
  "$@" &
  local pid=$!
  [ "$etait_monitor" -eq 1 ] || set +m

  local reste="$secondes"
  while [ "$reste" -gt 0 ]; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
    reste=$((reste - 1))
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "ci-last-run: MUR DÉPASSÉ après ${secondes}s — ${libelle}" >&2
    kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    local grace="$GRACE_S"
    while [ "$grace" -gt 0 ] && kill -0 "$pid" 2>/dev/null; do sleep 1; grace=$((grace - 1)); done
    kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    return 124
  fi

  wait "$pid"
}

# ---------------------------------------------------------------------
# json_champ — extraction d'une valeur de chaîne, SANS tube (L-00000325)
# ---------------------------------------------------------------------
# `"cle":null` et une clé ABSENTE ne matchent pas le motif `"cle":"` et rendent
# donc la chaîne vide — exactement comme `"cle":""`. Les trois formes sont un
# seul et même état, par construction.
json_champ() {
  local blob="$1" cle="$2" reste
  case "$blob" in
    *"\"$cle\":\""*) ;;
    *) printf '%s' ''; return 0 ;;
  esac
  reste="${blob#*\"$cle\":\"}"
  printf '%s' "${reste%%\"*}"
}

SORTIE=""
ajoute() { SORTIE="$SORTIE$1"$'\n'; }

CACHE_TXT=""
DEGRADE=0

CMD_MODELE='gh run list --workflow=<wf> --branch=main --limit=1 --json conclusion,status,headSha,createdAt'
ajoute "source: $CMD_MODELE"

if ! command -v gh >/dev/null 2>&1; then
  # Contrôle négatif du mécanisme : la garde sait DIRE qu'elle n'a rien mesuré.
  for wf in "${WORKFLOWS[@]}"; do
    ajoute "COVERAGE DEGRADED — $wf : dernier run inconnu (gh absent)"
  done
  printf '%s' "$SORTIE"
  exit 0
fi

TMP="$(mktemp 2>/dev/null)" || TMP="${TMPDIR:-/tmp}/ci-last-run.$$"
trap 'rm -f "$TMP"' EXIT

for wf in "${WORKFLOWS[@]}"; do
  borne_murale "$MUR_S" "$wf" -- \
    gh run list --workflow="$wf" --branch=main --limit=1 \
       --json conclusion,status,headSha,createdAt >"$TMP" 2>&1
  rc=$?
  out="$(cat "$TMP" 2>/dev/null)"

  if [ "$rc" -eq 124 ]; then
    ajoute "COVERAGE DEGRADED — $wf : dernier run inconnu (mur ${MUR_S} s)"
    DEGRADE=1
    continue
  fi
  if [ "$rc" -ne 0 ]; then
    # Motif = PREMIÈRE ligne capturée (stdout+stderr fusionnés, C5) : couvre
    # `gh` non authentifié, dépôt inconnu, workflow inexistant — et rien ne fuit
    # en brut, la sortie complète n'est jamais réémise.
    motif="${out%%$'\n'*}"
    [ -n "$motif" ] || motif="gh code $rc"
    ajoute "COVERAGE DEGRADED — $wf : dernier run inconnu (${motif:0:120})"
    DEGRADE=1
    continue
  fi

  blob="${out//$'\n'/ }"
  if [ "${blob// /}" = "[]" ]; then
    # UN FAIT, PAS UNE DÉGRADATION : c'est l'état initial GARANTI d'une nightly
    # neuve, et il doit être visible sans être rouge.
    ajoute "DERNIER RUN $wf (main): aucun run"
    CACHE_TXT="$CACHE_TXT$wf|absent|aucun run|"$'\n'
    continue
  fi

  statut="$(json_champ "$blob" status)"
  sha="$(json_champ "$blob" headSha)"
  cree="$(json_champ "$blob" createdAt)"

  case "$statut" in
    completed)
      # `conclusion` n'est lue QU'ICI — jamais avant `status` (précédence C4).
      concl="$(json_champ "$blob" conclusion)"
      case "$concl" in
        success) etat="success"; classe=ok ;;
        '')      etat="conclusion absente"; classe=ko ;;
        # `cancelled` EST un rouge (L-00000323) : une annulation efface le rouge
        # d'étapes réellement échouées avant elle.
        *)       etat="$concl"; classe=ko ;;
      esac
      ;;
    '')
      ajoute "COVERAGE DEGRADED — $wf : dernier run inconnu (statut illisible)"
      DEGRADE=1
      continue
      ;;
    *)
      etat="en cours"; classe=vif ;;
  esac

  ajoute "DERNIER RUN $wf (main): $etat @ ${sha:0:7} — ${cree:-date inconnue}"
  CACHE_TXT="$CACHE_TXT$wf|$classe|$etat|${sha:0:7}"$'\n'
done

if [ "$DEGRADE" -eq 0 ] && [ -n "$CACHE_TXT" ]; then
  mkdir -p "$CACHE_DIR" 2>/dev/null
  { printf 'epoch=%s\n' "$(date +%s)"; printf '%s' "$CACHE_TXT"; } >"$CACHE" 2>/dev/null || true
fi

printf '%s' "$SORTIE"
exit 0
