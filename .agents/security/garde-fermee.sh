#!/usr/bin/env bash
# garde-fermee.sh — lance une garde PreToolUse et echoue FERMEE
# (T-01M5CH9FA8BDDM33QKDBAZG42S, portee S-01M5CHM21A : jambes `command` POSIX de
# `.codex/hooks.json` ; T-01M5MCXKHQS4BME9Z9VVSWD6VT, S-01M5MCXYH5 : jambes `bash`
# preToolUse de `.github/hooks/agent-guardrails.json`).
#
# usage : garde-fermee.sh --echeance=N <script> [args...]   (payload sur stdin)
# `--echeance=N` est OBLIGATOIRE (N entier, en secondes) : absente, c'est un refus.
#
# Le script nomme est lance par `bash -p`, le payload lui est rendu a l'octet :
# l'entree standard du lanceur, dupliquee en fd 3 et passee au job de fond (qui
# lirait /dev/null sans redirection explicite), jamais copiee sur disque — le
# contenu d'un Write n'y laisse aucune trace. Repertoire temporaire (sorties de
# la garde) : $TMPDIR, sinon /tmp ; seuls les deux impossibles valent refus.
# Contrat de sortie, selon AGENTS_HOOK_HOST (defaut : claude) :
#   - garde sortie en rc 0 : sa sortie et ses diagnostics transmis, rc 0 ;
#   - hote `claude`, garde sortie en rc 2 : sortie, diagnostics et rc 2 transmis
#     a l'octet (le canal de refus mesure de Claude Code) ;
#   - tout le reste — rc 1, rc 2 hors `claude` (jamais mesure sur Codex,
#     kickoff_guard.py:917-923), plantage, echeance depassee, echeance invalide,
#     entree standard fermee, repertoire temporaire impossible, aucune garde
#     nommee — est un REFUS :
#     enveloppe `permissionDecision: deny` a rc 0 hors `claude` (sous `copilot`,
#     a la racine ET imbriquee : Copilot ignore l'imbriquee seule), `BLOCKED:` sur
#     stderr a rc 2 sous `claude`. Les raisons sont des chaines FIXES.
# A l'echeance : TERM, puis KILL apres 1 s de grace (une garde sourde a TERM ne
# retient pas l'hote). Le chien de garde dort par `sleep & wait`, et son trap tue
# son `sleep` : aucun `sleep` orphelin apres une garde rapide.
# Borne : un lanceur ABSENT donne `bash` rc 127, que l'hote lit comme un accord.
set -uo pipefail

hote=${AGENTS_HOOK_HOST-claude}
echeance=''
case "${1-}" in
  --echeance=*) echeance=${1#--echeance=}; shift ;;
esac

refuser() {
  case "$hote" in
    claude)
      printf 'BLOCKED: garde-fermee: %s, refus par defaut\n' "$1" >&2
      exit 2 ;;
    copilot)
      # Copilot CLI ignore le refus IMBRIQUE seul (mesure M3, 1.0.96,
      # T-01M5MCXKHQS4BME9Z9VVSWD6VT) : le refus est porte a la racine ET imbrique.
      printf '{"permissionDecision":"deny","permissionDecisionReason":"garde-fermee: %s, refus par defaut","hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"garde-fermee: %s, refus par defaut"}}\n' "$1" "$1"
      exit 0 ;;
    *)
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"garde-fermee: %s, refus par defaut"}}\n' "$1"
      exit 0 ;;
  esac
}

[ "$#" -ge 1 ] || refuser "aucune garde nommee"
case "$echeance" in
  ''|*[!0-9]*) refuser "echeance invalide" ;;
esac

exec 3<&0 || refuser "lecture du payload impossible"
racine_tmp=${TMPDIR:-/tmp}
d=$(mktemp -d "$racine_tmp/garde-fermee.XXXXXX" 2>/dev/null) || d=$(mktemp -d /tmp/garde-fermee.XXXXXX) || refuser "repertoire temporaire impossible"
trap 'rm -rf "$d"' EXIT

bash -p "$@" <&3 3<&- > "$d/out" 2> "$d/err" &
enfant=$!
(
  # `s` vide avant le trap : un TERM arrive avant le premier `sleep` ne vise
  # jamais un pid herite (la garde), seulement le `sleep` de ce chien de garde.
  s=''
  trap 'kill "$s" 2> /dev/null; wait "$s" 2> /dev/null; exit 0' TERM
  sleep "$echeance" &
  s=$!
  wait "$s"
  : > "$d/expire"
  kill -TERM "$enfant" 2> /dev/null
  sleep 1 &
  s=$!
  wait "$s"
  kill -KILL "$enfant" 2> /dev/null
) < /dev/null 3<&- > /dev/null 2>&1 &
veille=$!
wait "$enfant" 2> /dev/null
rc=$?
kill -TERM "$veille" 2> /dev/null
wait "$veille" 2> /dev/null

[ -e "$d/expire" ] && refuser "delai depasse"
case "$rc:$hote" in
  0:*|2:claude)
    cat "$d/out"
    cat "$d/err" >&2
    exit "$rc" ;;
esac
cat "$d/err" >&2
refuser "garde sortie en echec"
