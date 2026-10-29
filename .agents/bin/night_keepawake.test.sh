#!/usr/bin/env bash
# .agents/bin/night_keepawake.test.sh — banc du cycle de vie de la veilleuse (T-00000410).
# Run: bash .agents/bin/night_keepawake.test.sh   (ou "$(brew --prefix)/bin/bash" .../night_keepawake.test.sh)
# Découvert par core-scripts/run-bash-tests.sh (motif *.test.sh, profondeur libre).
#
# CE QUE CE BANC MESURE, ET CE QU'IL NE MESURE PAS. Il mesure, sur des STUBS bash, le
# détachement du processus (start rend la main tout de suite, pid vivant, stop le tue et
# retire le pid), le silence d'écriture des modes de lecture (--probe / --check-prompt /
# start --dry-run ne créent AUCUN répertoire), la validation de --minutes, le refus DEGRADED
# quand l'outil anti-veille manque, et le contrôle de prompt. Il NE MESURE PAS le kill du pid
# MSYS d'un powershell.exe enfant sous Windows : le stub s'appelle `pwsh` et se contente de
# dormir, aucun vrai P/Invoke ne tourne ici — la mesure sur un poste Windows réel est le
# résidu R6. Le banc tourne sur stubs bash : ce qu'il prouve du détachement vaut pour un
# processus fils POSIX, pas pour la sémantique de `taskkill //PID` sous MSYS.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/night_keepawake.sh"
RUNNER="${BASH:-$(command -v bash)}"
PASS=0
fail() { echo "FAIL: $1"; exit 1; }
ok()   { PASS=$((PASS + 1)); echo "ok  $1"; }

# La ligne porteuse doit être BYTE-IDENTIQUE au script et aux deux surfaces (garde d).
WAKEUP_LINE="RÉVEIL ARMÉ : à chaque frontière de tour, au plus 30 min après le tick précédent — un appel d'outil en vol n'est pas interrompu"

STUBS="$(mktemp -d)"
for t in caffeinate systemd-inhibit pwsh; do
  printf '#!/usr/bin/env bash\nsleep 300\n' > "$STUBS/$t"
  chmod +x "$STUBS/$t"
done

# mktemp -d crée le parent ; on vise un SOUS-répertoire ABSENT que seul un start réel doit
# matérialiser — sa présence est donc le témoin d'une écriture. Chaque cas qui asserte
# l'absence part d'un chemin VIERGE (fresh_absent), pour qu'un start réel d'un cas antérieur
# ne pollue pas le témoin.
fresh_absent() { echo "$(mktemp -d)/state/absent"; }

# Sonde d'hôte, mesurée UNE fois sur notre propre pid (vivant par construction) : le `ps`
# minimal de MSYS / Git-Bash refuse `-o` et rend du vide. Les deux cas qui dépendent de
# l'identification par ligne de commande — (1) et (8) — assertent alors le REFUS FERMÉ du
# script au lieu du kill. La borne est ANNONCÉE dans le libellé du `ok`, jamais sautée en
# silence : un `ok` muet sur un hôte dégradé se relit comme une couverture qu'on n'a pas.
PS_MUET=0
[ -n "$(ps -o args= -p "$$" 2>/dev/null || true)" ] || PS_MUET=1
STATE="$(fresh_absent)"
trap 'if [ -f "$STATE/keepawake.pid" ]; then kill "$(cat "$STATE/keepawake.pid" 2>/dev/null)" 2>/dev/null || true; fi' EXIT

# --- (1) détachement : start rend la main tout de suite, pid vivant, stop le tue -------------
t0=$SECONDS
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" PATH="$STUBS:$PATH" \
        "$RUNNER" "$SCRIPT" start --minutes 1 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(1) start rc=$RC : $OUT"
[ $((SECONDS - t0)) -lt 5 ] || fail "(1) start n'a pas rendu la main en < 5 s"
[ -f "$STATE/keepawake.pid" ] || fail "(1) start n'a pas écrit le pid"
PID=$(cat "$STATE/keepawake.pid")
kill -0 "$PID" 2>/dev/null || fail "(1) le processus détaché n'est pas vivant (pid=$PID)"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
if [ "$PS_MUET" = 1 ]; then
  # Hôte où `ps -o args=` est muet : le seul comportement correct est le refus FERMÉ —
  # rien tué (l'identité n'est pas prouvable, donc le pid recyclé reste possible) et
  # pidfile CONSERVÉ, seule trace de ce qu'il reste à terminer à la main.
  [ "$RC" = 4 ] || fail "(1) hôte à ps muet : rc=$RC attendu 4 : $OUT"
  case "$OUT" in
    *"ps ne sait pas décrire"*) : ;; *) fail "(1) hôte à ps muet : message nommé absent : $OUT" ;;
  esac
  kill -0 "$PID" 2>/dev/null || fail "(1) hôte à ps muet : le processus devait SURVIVRE au refus (pid=$PID)"
  [ -e "$STATE/keepawake.pid" ] || fail "(1) hôte à ps muet : le pidfile devait être CONSERVÉ"
  kill "$PID" 2>/dev/null || true; rm -f "$STATE/keepawake.pid"
  ok "(1) BORNE ANNONCÉE (ps muet, MSYS/Git-Bash) : start détache, stop REFUSE rc 4, ne tue rien, conserve le pidfile — le kill lui-même n'est PAS mesuré sur cet hôte"
else
  [ "$RC" = 0 ] || fail "(1) stop rc=$RC : $OUT"
  kill -0 "$PID" 2>/dev/null && fail "(1) le processus survit au stop (pid=$PID)"
  [ -e "$STATE/keepawake.pid" ] && fail "(1) stop n'a pas retiré le fichier pid"
  ok "(1) détachement : start rend en < 5 s, pid vivant, stop le tue et retire le pid"
fi

# --- (2) start --dry-run n'écrit rien --------------------------------------------------------
STATE2="$(fresh_absent)"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE2" PATH="$STUBS:$PATH" \
        "$RUNNER" "$SCRIPT" start --minutes 5 --dry-run 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(2) start --dry-run rc=$RC : $OUT"
[ -e "$STATE2" ] && fail "(2) start --dry-run a créé le répertoire d'état"
ok "(2) start --dry-run : rc 0, répertoire d'état ABSENT"

# --- (3) --probe et --check-prompt n'écrivent rien -------------------------------------------
STATE3="$(fresh_absent)"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE3" PATH="$STUBS:$PATH" \
        "$RUNNER" "$SCRIPT" --probe --minutes 30 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(3) --probe rc=$RC : $OUT"
PROMPT_OK="$STUBS/prompt_ok.md"
printf 'entête\n%s\nsuite\n' "$WAKEUP_LINE" > "$PROMPT_OK"
NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE3" "$RUNNER" "$SCRIPT" --check-prompt "$PROMPT_OK" >/dev/null 2>&1
[ -e "$STATE3" ] && fail "(3) --probe/--check-prompt ont créé le répertoire d'état"
ok "(3) --probe et --check-prompt : répertoire d'état ABSENT"

# --- (4) --minutes hors 1..1440 -> rc 2 nommé ------------------------------------------------
for m in abc 0 1441; do
  OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" PATH="$STUBS:$PATH" \
          "$RUNNER" "$SCRIPT" --probe --minutes "$m" 2>&1); RC=$?
  [ "$RC" = 2 ] || fail "(4) --minutes $m : rc=$RC attendu 2 : $OUT"
  case "$OUT" in
    *"--minutes hors 1..1440"*) : ;; *) fail "(4) --minutes $m : message absent : $OUT" ;;
  esac
done
ok "(4) --minutes abc|0|1441 : rc 2 avec message nommé"

# --- (5) contrôle négatif : outil absent -> rc 3 + ligne DEGRADED ----------------------------
STATE5="$(fresh_absent)"
# PATH = un répertoire VIDE (mktemp), jamais un PATH nu : `/usr/bin:/bin` rendrait ce contrôle
# hôte-dépendant (Ubuntu porte /usr/bin/systemd-inhibit → rc 0 → rouge sur la jambe ubuntu).
EMPTY_PATH="$(mktemp -d)"
OUT=$(NIGHT_KEEPAWAKE_OS=linux NIGHT_KEEPAWAKE_STATE_DIR="$STATE5" PATH="$EMPTY_PATH" \
        "$RUNNER" "$SCRIPT" --probe --minutes 30 2>&1); RC=$?
[ "$RC" = 3 ] || fail "(5) outil absent : rc=$RC attendu 3 : $OUT"
case "$OUT" in
  *"COVERAGE DEGRADED — anti-veille indisponible (linux)"*) : ;;
  *) fail "(5) ligne DEGRADED absente : $OUT" ;;
esac
case "$OUT" in
  *"ne tirera pas pendant une veille"*) : ;; *) fail "(5) l'honnêteté de couverture manque : $OUT" ;;
esac
[ -e "$STATE5" ] && fail "(5) le refus DEGRADED a écrit le répertoire d'état"
ok "(5) contrôle négatif : outil absent -> rc 3 + DEGRADED, rien écrit"

# --- (6) --check-prompt : rc 0 avec la ligne, rc 1 + message nommé sans -----------------------
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt "$PROMPT_OK" 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(6) prompt avec consigne : rc=$RC attendu 0 : $OUT"
PROMPT_BAD="$STUBS/prompt_bad.md"
printf 'entête\naucune consigne de réveil ici\n' > "$PROMPT_BAD"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt "$PROMPT_BAD" 2>&1); RC=$?
[ "$RC" = 1 ] || fail "(6) prompt sans consigne : rc=$RC attendu 1 : $OUT"
case "$OUT" in
  *"night: prompt résolu sans consigne de réveil"*) : ;;
  *) fail "(6) message nommé absent : $OUT" ;;
esac
ok "(6) --check-prompt : rc 0 avec la ligne, rc 1 + « night: prompt résolu sans consigne de réveil » sans"

# --- (7) stop : pidfile invalide (0) -> refus rc 4, JAMAIS kill 0, fichier retiré --------------
# `kill 0` signale TOUT le groupe de processus (orchestrateur compris) : un pidfile corrompu
# doit produire un refus NOMMÉ, jamais un kill.
STATE7="$(mktemp -d)/state"; mkdir -p "$STATE7"; echo 0 > "$STATE7/keepawake.pid"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE7" "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 4 ] || fail "(7) pidfile 0 : rc=$RC attendu 4 : $OUT"
case "$OUT" in
  *"pidfile invalide"*) : ;; *) fail "(7) message nommé absent : $OUT" ;;
esac
[ -e "$STATE7/keepawake.pid" ] && fail "(7) le pidfile invalide n'a pas été retiré"
ok "(7) stop : pidfile 0 -> rc 4 nommé, rien tué, fichier retiré"

# --- (8) stop : pid d'un processus ÉTRANGER (sleep nu) -> NON tué, rc 4, fichier retiré --------
# Le trou du pid recyclé : après un crash sans stop, le pid du fichier peut désigner n'importe
# quel processus de l'uid. `stop` lit `ps -o args=` et refuse tout ce qui n'est pas un anti-veille.
STATE8="$(mktemp -d)/state"; mkdir -p "$STATE8"
sleep 60 & FOREIGN=$!
echo "$FOREIGN" > "$STATE8/keepawake.pid"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE8" "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 4 ] || fail "(8) pid étranger : rc=$RC attendu 4 : $OUT"
kill -0 "$FOREIGN" 2>/dev/null || fail "(8) le processus étranger a été TUÉ (pid=$FOREIGN)"
if [ "$PS_MUET" = 1 ]; then
  # Même garantie (le pid étranger n'est PAS tué), atteinte par l'autre refus : ici c'est
  # la sonde de capacité qui ferme, pas l'identification. On l'assert explicitement plutôt
  # que d'accepter n'importe quel rc 4 — sinon l'arm passerait pour la mauvaise raison.
  case "$OUT" in
    *"ps ne sait pas décrire"*) : ;; *) fail "(8) hôte à ps muet : message nommé absent : $OUT" ;;
  esac
  [ -e "$STATE8/keepawake.pid" ] || fail "(8) hôte à ps muet : le pidfile devait être CONSERVÉ"
  rm -f "$STATE8/keepawake.pid"
  kill "$FOREIGN" 2>/dev/null || true
  ok "(8) BORNE ANNONCÉE (ps muet) : pid étranger non tué — fermé par « vivant mais indescriptible », PAS par l'identification par ligne de commande"
else
  case "$OUT" in
    *"ne désigne pas un anti-veille"*) : ;; *) fail "(8) message nommé absent : $OUT" ;;
  esac
  [ -e "$STATE8/keepawake.pid" ] && fail "(8) le pidfile étranger n'a pas été retiré"
  kill "$FOREIGN" 2>/dev/null || true
  ok "(8) stop : pid étranger (sleep nu) -> non tué, rc 4 nommé, fichier retiré"
fi

# --- (9) stop : pid VIVANT mais INDESCRIPTIBLE -> rc 4, rien tué, pidfile CONSERVÉ ------------
# L'angle mort nommé par l'exec-critic @ 3ef7b79 : sur un hôte SAIN, aucun arm ne prenait cette
# branche — elle n'était donc assertée en CI que par la jambe windows-latest, et la casser
# serait passé vert deux fois sur trois. Ici on la FORCE sur n'importe quel hôte, avec un `ps`
# factice muet en tête de PATH, le processus étant bel et bien VIVANT.
# C'est aussi l'arm du discriminant : une implémentation qui déduirait la mort du silence de
# `ps` (au lieu de la demander à `kill -0` SUR LE PID VISÉ) retirerait le pidfile et sortirait 0
# -> les trois assertions ci-dessous rougissent d'un coup.
STATE9="$(mktemp -d)/state"; mkdir -p "$STATE9"
MUTE="$(mktemp -d)"; printf '#!/bin/sh\nexit 1\n' > "$MUTE/ps"; chmod +x "$MUTE/ps"
sleep 60 & ALIVE=$!
echo "$ALIVE" > "$STATE9/keepawake.pid"
OUT=$(PATH="$MUTE:$PATH" NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE9" \
        "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 4 ] || fail "(9) vivant + ps muet : rc=$RC attendu 4 : $OUT"
case "$OUT" in
  *"ps ne sait pas décrire"*) : ;; *) fail "(9) message nommé absent : $OUT" ;;
esac
kill -0 "$ALIVE" 2>/dev/null || fail "(9) le processus VIVANT a été tué alors que son identité n'était pas prouvée"
[ -e "$STATE9/keepawake.pid" ] || fail "(9) le pidfile devait être CONSERVÉ (seule trace du pid à terminer)"
kill "$ALIVE" 2>/dev/null || true
ok "(9) stop : pid VIVANT mais indescriptible -> rc 4 nommé, rien tué, pidfile CONSERVÉ (forcé sur TOUT hôte)"

# --- (10) stop : lecture ps ENTRE CROCHETS -> indescriptible, PAS un intrus ------------------
# LE CAS QUE LA PORTE A TROUVÉ, LE 2026-09-12, dans sa jambe conteneur : `ps -o args=` a rendu
# `[nohup]`. Sous Linux, des crochets veulent dire que `/proc/<pid>/cmdline` est VIDE — le
# processus est vivant mais pas encore, ou plus, descriptible. `mode_start` enregistrant le pid
# de `nohup` AVANT son `exec`, la fenêtre existe.
#
# CE QUE LE SCRIPT EN FAISAIT ÉTAIT L'INVERSE DE SA PROPRE DOCTRINE. `[nohup]` ne ressemble à
# aucun anti-veille connu, donc la lecture tombait dans la branche « ce n'est pas un
# anti-veille » — qui RETIRE le pidfile. Or le pidfile est la SEULE trace de ce qu'il reste à
# terminer à la main : le retirer sans avoir prouvé l'identité laisse l'anti-veille en vie et
# plus personne pour savoir quel pid tuer. Un fail-open sur la trace de désarmement.
#
# On force la lecture entre crochets par un `ps` factice, comme le cas (9) force le silence.
# La distinction avec le cas (8) est le fond de ce test : un intrus DESCRIPTIBLE (un `sleep`
# nu) reste refusé pidfile RETIRÉ, un indescriptible est refusé pidfile CONSERVÉ.
STATE10="$(mktemp -d)/state"; mkdir -p "$STATE10"
CROCHETS="$(mktemp -d)"; printf '#!/bin/sh\necho "[nohup]"\n' > "$CROCHETS/ps"; chmod +x "$CROCHETS/ps"
sleep 60 & ALIVE10=$!
echo "$ALIVE10" > "$STATE10/keepawake.pid"
OUT=$(PATH="$CROCHETS:$PATH" NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE10" \
        "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 4 ] || fail "(10) lecture entre crochets : rc=$RC attendu 4 : $OUT"
case "$OUT" in
  *"ps ne sait pas décrire"*) : ;;
  *) fail "(10) une lecture entre crochets doit être dite INDESCRIPTIBLE, pas « ne désigne pas un anti-veille » : $OUT" ;;
esac
kill -0 "$ALIVE10" 2>/dev/null || fail "(10) le processus VIVANT a été tué alors que son identité n'était pas prouvée"
[ -e "$STATE10/keepawake.pid" ] || fail "(10) le pidfile devait être CONSERVÉ — c'est le fail-open corrigé"
kill "$ALIVE10" 2>/dev/null || true
ok "(10) stop : lecture ps entre crochets -> indescriptible, rc 4, rien tué, pidfile CONSERVÉ"

# --- (11) un ZOMBIE Linux rend `[nohup] <defunct>` — les crochets ne FERMENT pas -------------
# Le cas (10) force `[nohup]`, forme close. Un zombie Linux rend `[nohup] <defunct>` : un motif
# qui exigerait le crochet FERMANT ne mordrait pas dessus, et le fail-open corrigé au cas (10)
# reviendrait par la porte de derrière, sur la forme la PLUS probable en conteneur. Le motif
# porte donc sur le crochet OUVRANT seul.
STATE12="$(mktemp -d)/state"; mkdir -p "$STATE12"
DEFUNCT="$(mktemp -d)"; printf '#!/bin/sh\necho "[nohup] <defunct>"\n' > "$DEFUNCT/ps"; chmod +x "$DEFUNCT/ps"
sleep 60 & ALIVE12=$!
echo "$ALIVE12" > "$STATE12/keepawake.pid"
OUT=$(PATH="$DEFUNCT:$PATH" NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE12" \
        "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 4 ] || fail "(11) zombie : rc=$RC attendu 4 : $OUT"
case "$OUT" in
  *"ps ne sait pas décrire"*) : ;;
  *) fail "(11) un zombie doit être dit INDESCRIPTIBLE, pas « ne désigne pas un anti-veille » : $OUT" ;;
esac
[ -e "$STATE12/keepawake.pid" ] || fail "(11) le pidfile devait être CONSERVÉ"
kill "$ALIVE12" 2>/dev/null || true
ok "(11) stop : zombie « [nohup] <defunct> » -> indescriptible, rc 4, pidfile CONSERVÉ"

# --- (12) LA BOUCLE DE RÉESSAI SERT — et sans ce cas elle est du code mort -------------------
# LE CAS QUE LA REVUE DE CLÔTURE A RÉCLAMÉ, et elle avait raison : les cas (10) et (11) posent
# un `ps` qui rend TOUJOURS la même chose, donc ils exercent la BRANCHE et jamais la BOUCLE.
# Mesuré par mutation hors dépôt : boucle supprimée, branche conservée -> le banc restait vert.
# Une moitié du correctif n'était donc prouvée par rien. Ici le `ps` factice compte ses appels
# et devient descriptible au second : seule une implémentation qui RELIT peut désarmer.
STATE13="$(mktemp -d)/state"; mkdir -p "$STATE13"
FLAKY="$(mktemp -d)"
{
  printf '#!/bin/sh\n'
  printf 'C="%s/n"\n' "$FLAKY"
  printf 'N=$(cat "$C" 2>/dev/null || echo 0); N=$((N+1)); echo "$N" > "$C"\n'
  printf 'if [ "$N" -ge 2 ]; then echo "/usr/bin/caffeinate -dims -t 60"; else echo "[nohup]"; fi\n'
} > "$FLAKY/ps"
chmod +x "$FLAKY/ps"
sleep 60 & ALIVE13=$!
echo "$ALIVE13" > "$STATE13/keepawake.pid"
OUT=$(PATH="$FLAKY:$PATH" NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE13" \
        "$RUNNER" "$SCRIPT" stop 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(12) la 2e lecture décrit l'anti-veille, le stop doit réussir : rc=$RC : $OUT"
[ -e "$STATE13/keepawake.pid" ] && fail "(12) pidfile devait être retiré après un désarmement réussi"
kill "$ALIVE13" 2>/dev/null || true
ok "(12) stop : 1re lecture entre crochets, 2e descriptible -> désarmé (la BOUCLE de réessai SERT)"

# --- (13) --check-prompt --headless (T-00001044) ---------------------------------------------
# En headless chaque tour est un `claude -p` neuf : `kill -0 "$(cat …)"` y est refusé (mesuré),
# et `night_keepawake.sh start|stop` n'est pas dans l'allowlist — la boucle externe imprimée
# détient l'anti-veille. Le prompt headless OMET donc ces gestes, et l'option le VÉRIFIE :
# porteuse exigée, geste de réveil refusé. Le mode surveillé reste inchangé (il accepte le
# bloc complet). Rouge sur l'ancien script : `--headless` y est un argument inconnu (rc 2).
HEADLESS_LINE="- les agents en vol, horodatés ; l'anti-veille est tenue par la boucle externe imprimée — ce tour ne la vérifie ni ne la ré-arme."
PROMPT_HL="$STUBS/prompt_headless.md"
printf 'entête\n%s\n- `date`\n%s\n' "$WAKEUP_LINE" "$HEADLESS_LINE" > "$PROMPT_HL"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt --headless "$PROMPT_HL" 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(13) prompt headless sans geste de réveil : rc=$RC attendu 0 : $OUT"
PROMPT_FULL="$STUBS/prompt_full.md"
printf '%s\n%s\n- `kill -0 "$(cat .agents/state/local/night/keepawake.pid)"` sur le pid\n' "$WAKEUP_LINE" "$HEADLESS_LINE" > "$PROMPT_FULL"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt --headless "$PROMPT_FULL" 2>&1); RC=$?
[ "$RC" = 1 ] || fail "(13) prompt headless porteur de kill -0 : rc=$RC attendu 1 : $OUT"
case "$OUT" in
  *"geste de réveil (« kill -0 »)"*) : ;;
  *) fail "(13) refus headless non nommé : $OUT" ;;
esac
for g in "bash .agents/bin/night_keepawake.sh start --minutes 30" "bash .agents/bin/night_keepawake.sh stop"; do
  printf '%s\n%s\n- `%s`\n' "$WAKEUP_LINE" "$HEADLESS_LINE" "$g" > "$PROMPT_FULL"
  OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
          "$RUNNER" "$SCRIPT" --check-prompt --headless "$PROMPT_FULL" 2>&1); RC=$?
  [ "$RC" = 1 ] || fail "(13) prompt headless porteur de « $g » : rc=$RC attendu 1 : $OUT"
done
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt --headless "$PROMPT_BAD" 2>&1); RC=$?
[ "$RC" = 1 ] || fail "(13) prompt headless SANS porteuse : rc=$RC attendu 1 : $OUT"
case "$OUT" in
  *"night: prompt résolu sans consigne de réveil"*) : ;;
  *) fail "(13) headless sans porteuse : message nommé absent : $OUT" ;;
esac
printf '%s\n- `kill -0 "$(cat x.pid)"`\n' "$WAKEUP_LINE" > "$PROMPT_FULL"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt "$PROMPT_FULL" 2>&1); RC=$?
[ "$RC" = 0 ] || fail "(13) le mode SURVEILLÉ doit accepter le bloc complet : rc=$RC : $OUT"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --probe --minutes 30 --headless 2>&1); RC=$?
[ "$RC" = 2 ] || fail "(13) --headless hors --check-prompt : rc=$RC attendu 2 : $OUT"
ok "(13) --check-prompt --headless : porteuse exigée, kill -0 / start / stop refusés (rc 1), surveillé inchangé, --headless ailleurs rc 2"

# --- (14) --check-prompt --headless EXIGE la ligne de remplacement (T-00001044, Opus T6) ------
# Sans elle, un prompt qui a simplement PERDU la ligne du pid passerait pour un prompt headless.
# La ligne est BYTE-IDENTIQUE au script et aux deux surfaces (garde d, comme la porteuse).
printf 'entête\n%s\n- `date`\n' "$WAKEUP_LINE" > "$PROMPT_FULL"
OUT=$(NIGHT_KEEPAWAKE_OS=darwin NIGHT_KEEPAWAKE_STATE_DIR="$STATE" \
        "$RUNNER" "$SCRIPT" --check-prompt --headless "$PROMPT_FULL" 2>&1); RC=$?
[ "$RC" = 1 ] || fail "(14) prompt headless SANS ligne de remplacement : rc=$RC attendu 1 : $OUT"
case "$OUT" in
  *"sans la ligne de remplacement"*) : ;;
  *) fail "(14) refus non nommé : $OUT" ;;
esac
for surf in "$HERE/../../.claude/commands/night.md" "$HERE/../skills/night/SKILL.md"; do
  grep -qF -- "$HEADLESS_LINE" "$surf" || fail "(14) ligne de remplacement absente de $surf"
done
grep -qF -- "$HEADLESS_LINE" "$SCRIPT" || fail "(14) ligne de remplacement absente du script"
ok "(14) --check-prompt --headless : ligne de remplacement exigée (rc 1 nommé), byte-identique script + 2 surfaces"

echo "PASS $PASS/14 — night_keepawake.sh"
