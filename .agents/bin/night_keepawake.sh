#!/usr/bin/env bash
# .agents/bin/night_keepawake.sh — veilleuse anti-veille portable pour /night (T-00000410).
#
# Modes :
#   --probe --minutes N              lecture seule : imprime "<os> · <commande> · <limites>", rc 0
#   start   --minutes N [--dry-run]  détache un processus anti-veille OS pour N minutes
#   stop                             tue le processus détaché et retire son fichier pid
#   --check-prompt <fichier>         rc 0 si le prompt résolu PORTE la consigne de réveil
#   --check-prompt --headless <f>    idem, ET rc 1 si le prompt tape un geste de réveil
#                                    (`kill -0`, `night_keepawake.sh start|stop`) — en headless
#                                    la boucle externe détient l'anti-veille (T-00001044)
#
# Codes de sortie : 0 ok · 1 prompt sans consigne · 2 argument invalide · 3 anti-veille
# indisponible · 4 stop REFUSÉ sans rien tuer (pidfile invalide, pid vivant mais indescriptible,
# ou pid qui ne désigne pas un anti-veille) — dans les deux derniers cas le pidfile est CONSERVÉ.
#
# CE QUE LA VEILLEUSE FAIT, ET CE QU'ELLE NE FAIT PAS. Elle empêche l'OS de dormir pendant N
# minutes ; elle N'interrompt PAS un appel d'outil en vol, elle NE tire PAS pendant une veille
# machine déjà entamée, et elle NE survit PAS à la session qui l'a lancée sans un ré-armement au
# tick. Le tick de /night ré-arme à chaque frontière de tour (`kill -0` sur le pid, re-`start`
# s'il est mort). Voir .claude/commands/night.md § « Réveil armé — le tick de tour ».
#
# ROOT est dérivé de $0, jamais un chemin en dur ; aucun `sudo` ; `command -v` seul décide si
# l'outil anti-veille existe. NIGHT_KEEPAWAKE_OS surcharge la détection (banc 3 OS) ;
# NIGHT_KEEPAWAKE_STATE_DIR surcharge le répertoire d'état (le pid n'est écrit QUE par un `start` réel).

set -euo pipefail

# --- Ligne porteuse — BYTE-IDENTIQUE dans night.md, SKILL.md et ici (garde d) ----------------
WAKEUP_LINE="RÉVEIL ARMÉ : à chaque frontière de tour, au plus 30 min après le tick précédent — un appel d'outil en vol n'est pas interrompu"
# Ligne de remplacement de la variante headless — BYTE-IDENTIQUE au bloc `text` de night.md et
# SKILL.md (§ Réveil armé, variante headless) ; exigée par `--check-prompt --headless`.
HEADLESS_LINE="- les agents en vol, horodatés ; l'anti-veille est tenue par la boucle externe imprimée — ce tour ne la vérifie ni ne la ré-arme."

# Racine résolue en BUILTINS seuls (`cd`, `pwd`, expansion de paramètre) — pas `dirname` :
# le contrôle négatif « outil absent » tourne avec un PATH vide, et un script qui a besoin
# d'un binaire externe pour trouver sa racine y mourrait avant de dire « anti-veille indisponible ».
case "$0" in
  */*) SCRIPT_DIR="$(cd "${0%/*}" && pwd)" ;;
  *)   SCRIPT_DIR="$(pwd)" ;;
esac
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_DIR="${NIGHT_KEEPAWAKE_STATE_DIR:-$ROOT/.agents/state/local/night}"
PID_FILE="$STATE_DIR/keepawake.pid"

die_arg() { echo "night: $1" >&2; exit 2; }

detect_os() {
  local raw="${NIGHT_KEEPAWAKE_OS:-}"
  [ -n "$raw" ] || raw="$(uname -s 2>/dev/null || echo unknown)"
  case "$raw" in
    darwin|Darwin*)               echo darwin ;;
    linux|Linux*)                 echo linux ;;
    windows|MINGW*|MSYS*|CYGWIN*) echo windows ;;
    *)                            echo "$raw" ;;
  esac
}

degraded() {
  # $1 os · $2 ce qui manque — rc 3, message fixe attendu par le banc et les cas python.
  echo "COVERAGE DEGRADED — anti-veille indisponible ($1) : $2 — le réveil ne tirera pas pendant une veille ; recommandation : régler la veille OS pour la nuit, ou --headless pour borner le coût d'un tour muet" >&2
  exit 3
}

# Résout la commande OS dans COMMAND (tableau) + LIMITS (chaîne) ; rc 3 via degraded() si
# l'outil requis est absent. $1 os · $2 secondes.
resolve() {
  local os="$1" secs="$2"
  case "$os" in
    darwin)
      command -v caffeinate >/dev/null 2>&1 || degraded darwin "caffeinate introuvable"
      COMMAND=(caffeinate -dims -t "$secs")
      LIMITS="caffeinate -s ne tient que sur secteur ; ne traverse pas une veille déjà entamée"
      ;;
    linux)
      command -v systemd-inhibit >/dev/null 2>&1 \
        || degraded linux "systemd-inhibit introuvable (logind requis ; WSL2 sans systemd non couvert)"
      COMMAND=(systemd-inhibit --what=idle:sleep:handle-lid-switch --who=night --mode=block sleep "$secs")
      LIMITS="repli --what=idle:sleep si polkit refuse handle-lid-switch (capot fermé non couvert) ; logind requis (WSL2 sans systemd -> rc 3)"
      ;;
    windows)
      local shell=""
      if command -v pwsh >/dev/null 2>&1; then shell="pwsh"
      elif command -v powershell.exe >/dev/null 2>&1; then shell="powershell.exe"
      else degraded windows "pwsh/powershell.exe introuvable"; fi
      local ps="Add-Type -Namespace Win -Name Power -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint esFlags);'; [Win.Power]::SetThreadExecutionState(0x80000003); Start-Sleep -Seconds $secs"
      COMMAND=("$shell" -NoProfile -NonInteractive -Command "$ps")
      LIMITS="SetThreadExecutionState(0x80000003) ne couvre ni la stratégie capot ni l'hibernation forcée (powercfg /requests exige l'élévation : non utilisé)"
      ;;
    *)
      degraded "$os" "OS non reconnu par uname -s"
      ;;
  esac
}

validate_minutes() {
  case "$MINUTES" in
    ''|*[!0-9]*) die_arg "--minutes hors 1..1440 : « ${MINUTES:-∅} »" ;;
  esac
  if [ "$MINUTES" -lt 1 ] || [ "$MINUTES" -gt 1440 ]; then
    die_arg "--minutes hors 1..1440 : « $MINUTES »"
  fi
}

mode_probe() {
  validate_minutes
  local os secs
  os="$(detect_os)"
  secs=$((MINUTES * 60))
  resolve "$os" "$secs"           # exit 3 si l'outil est absent — probe ne masque pas l'indisponibilité
  echo "$os · ${COMMAND[*]} · $LIMITS"
  exit 0
}

mode_start() {
  validate_minutes
  local os secs pid
  os="$(detect_os)"
  secs=$((MINUTES * 60))
  resolve "$os" "$secs"           # exit 3 avant toute écriture si l'outil est absent
  if [ "$DRY" = "1" ]; then
    echo "start --dry-run ($os) : ${COMMAND[*]} — aucun réveil armé, aucun fichier écrit"
    exit 0
  fi
  mkdir -p "$STATE_DIR" || { echo "night: impossible de créer $STATE_DIR — réveil non armé" >&2; exit 2; }
  nohup "${COMMAND[@]}" </dev/null >/dev/null 2>&1 &
  pid=$!
  disown 2>/dev/null || true
  # `set -e` : on VÉRIFIE que l'enfant a démarré avant d'annoncer « réveil armé »,
  # et on n'écrit le pid que si l'écriture réussit.
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "night: l'anti-veille n'a pas démarré (${COMMAND[*]}) — réveil non armé" >&2
    exit 3
  fi
  echo "$pid" > "$PID_FILE" || { echo "night: impossible d'écrire $PID_FILE" >&2; kill "$pid" 2>/dev/null || true; exit 2; }
  echo "réveil armé ($os) pid=$pid pour $MINUTES min — ${COMMAND[*]}"
  exit 0
}

mode_stop() {
  if [ ! -f "$PID_FILE" ]; then
    echo "réveil désarmé (aucun pid actif)"
    exit 0
  fi
  local pid ident
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  # Un pid tuable est un entier > 1. On ne fait JAMAIS `kill 0` (0 = TOUT le groupe
  # de processus, orchestrateur compris) ni `kill -1` (tous les process de l'uid) :
  # un pidfile vide, `0`, négatif ou non numérique est un refus NOMMÉ, jamais un kill.
  if ! [[ "$pid" =~ ^[0-9]+$ ]] || [ "$pid" -le 1 ]; then
    rm -f "$PID_FILE"
    echo "night: pidfile invalide (« ${pid:-∅} ») — rien tué (jamais kill 0/-1), fichier retiré" >&2
    exit 4
  fi
  # Identité : le pid doit désigner un anti-veille que NOUS avons armé, pas un pid
  # recyclé. On lit la LIGNE DE COMMANDE (`ps -o args=`) et non `ps -o comm=` : `comm`
  # est fragile au timing d'exec (le vrai caffeinate rend `/usr/bin/caffeinate`, mais un
  # stub via `#!/usr/bin/env bash` traverse env->bash->cmd), alors que la ligne de
  # commande contient TOUJOURS le jeton de l'outil (chemin ou argv[0]). DÉVIATION ASSUMÉE
  # de la consigne (T-00000410 fix) : `ps -o args=` plutôt que `ps -o comm=`, et `sleep`
  # NU est HORS de la liste — c'est le trou du pid recyclé, et aucun anti-veille de
  # production n'est un `sleep` nu (le pid enregistré est caffeinate / systemd-inhibit /
  # pwsh) — de sorte qu'un `sleep` étranger est REFUSÉ, ce que le cas négatif du banc exige.
  # VIVACITÉ D'ABORD, IDENTITÉ ENSUITE — et la vivacité se demande AU PID VISÉ (T-00000410,
  # CI windows-latest du 2026-09-03, run 33772369551 ; puis exec-critic @ 3ef7b79).
  # `ps -o args=` n'existe pas partout : le `ps` minimal de MSYS / Git-Bash refuse `-o` et
  # rend du VIDE — indiscernable, en l'état, d'un processus mort. Le script concluait donc
  # « pid déjà mort », retirait le pidfile et NE TUAIT RIEN : sur Windows l'anti-veille
  # devenait INDÉSARMABLE, et la machine restait éveillée sans qu'on sache quel pid terminer.
  # Une première correction sondait NOTRE PROPRE pid — mais c'est un témoin FAVORABLE, choisi
  # pour être toujours descriptible : sur un hôte où `ps` décrit notre pid et reste opaque
  # pour le pid VISÉ, le défaut se reproduisait verbatim. Le bon discriminant est `kill -0`,
  # builtin POSIX qui ne dépend d'aucun `ps` et qui répond SUR LE PID VISÉ : rc non nul =
  # mort (pidfile périmé, on retire, rien à tuer) ; rc 0 = vivant, et l'on n'a alors plus
  # qu'une question d'IDENTITÉ. Un vivant indescriptible est un refus FERMÉ — rien tué
  # (l'identité n'est pas prouvée, donc le pid recyclé reste possible) et **pidfile CONSERVÉ**,
  # seule trace de ce qu'il reste à terminer à la main. Borne ANNONCÉE, jamais un
  # désarmement silencieux.
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "réveil désarmé (pid=$pid déjà mort)"
    exit 0
  fi
  # LECTURE RÉESSAYÉE SUR UNE FENÊTRE BORNÉE, et la borne est le point. Sous Linux,
  # `ps -o args=` rend la ligne de commande VIDE tant que `/proc/<pid>/cmdline` ne
  # l'est pas encore — ce que `ps` affiche alors comme le `comm` ENTRE CROCHETS.
  # `mode_start` enregistre `$!`, c'est-à-dire le pid de `nohup` AVANT son `exec` :
  # il existe donc une fenêtre où le pid est vivant et pas encore descriptible.
  # HONNÊTETÉ SUR CE QUI EST MESURÉ : cette fenêtre n'a PAS été reproduite — 500
  # sondes en conteneur, à vide puis sous charge, ont rendu 500 lectures correctes.
  # Elle est en revanche OBSERVÉE une fois, dans la jambe conteneur de la porte du
  # 2026-09-12 : `comm=[nohup]`, sur une machine qui portait une autre charge au
  # même instant. Trois lectures espacées valent donc mieux qu'une, et elles ne
  # coûtent rien au cas nominal, qui répond du premier coup.
  ident=""
  for essai in 1 2 3; do
    ident="$(ps -o args= -p "$pid" 2>/dev/null || true)"
    case "$ident" in
      "" | \[*) [ "$essai" = 3 ] || sleep "${NIGHT_PS_RETRY_DELAY:-0.2}" ;;
      *) break ;;
    esac
  done
  # UNE LECTURE ENTRE CROCHETS EST UN INDESCRIPTIBLE, PAS UN INTRUS, et les deux ne
  # se traitent pas pareil. Sans cette branche, `[nohup]` tombait dans le `*)`
  # ci-dessous — « ce n'est pas un anti-veille » — qui RETIRE le pidfile. C'est
  # l'inverse de la doctrine que ce bloc énonce quinze lignes plus haut : quand
  # l'identité n'est PAS prouvée, on ne tue rien ET on CONSERVE le pidfile, seule
  # trace de ce qu'il reste à terminer à la main. Le retirer là est un fail-open
  # sur la trace de désarmement — l'anti-veille survit, et plus rien ne dit quel
  # pid terminer. Le cas de l'intrus DESCRIPTIBLE (un `sleep` nu, cas 8 du banc)
  # garde son traitement : lui est identifié, et identifié comme n'étant pas des
  # nôtres.
  case "$ident" in
    "" | \[*)
      echo "night: pid=$pid est VIVANT mais ps ne sait pas décrire ce processus (« ${ident:-∅} ») — NON tué (identité non prouvée), pidfile CONSERVÉ ; termine-le à la main puis relance stop" >&2
      exit 4
      ;;
  esac
  case "$ident" in
    *caffeinate*|*systemd-inhibit*|*pwsh*|*powershell*|*SetThreadExecutionState*)
      kill "$pid" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "réveil désarmé (pid=$pid, comm=$ident)"
      exit 0
      ;;
    *)
      rm -f "$PID_FILE"
      echo "night: pidfile ne désigne pas un anti-veille (comm=$ident) — non tué, fichier retiré" >&2
      exit 4
      ;;
  esac
}

mode_check() {
  # Builtins seuls (garde C12) : ni grep ni cat. Écrit RIEN.
  # `--headless` (T-00001044) : la ligne porteuse reste EXIGÉE, et le prompt ne doit taper
  # AUCUN geste de réveil — `kill -0`, `night_keepawake.sh start|stop`. En headless chaque
  # tour est un `claude -p` neuf dont l'allowlist ne les porte pas (refus « Contains … »,
  # mesuré) ; l'anti-veille est détenue par la boucle externe imprimée (`start` avant la
  # boucle, `trap … stop` EXIT). Il exige aussi la ligne de remplacement HEADLESS_LINE : sans
  # elle, un prompt qui a simplement PERDU la ligne du pid passerait pour un prompt headless.
  # Le mode surveillé (sans `--headless`) est inchangé.
  local found=1 found_h=1 geste="" line
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" == *"$WAKEUP_LINE"* ]]; then found=0; fi
    if [[ "$line" == *"$HEADLESS_LINE"* ]]; then found_h=0; fi
    if [ "$HEADLESS" = 1 ] && [ -z "$geste" ]; then
      case "$line" in
        *"kill -0"*) geste="kill -0" ;;
        *"night_keepawake.sh start"*) geste="night_keepawake.sh start" ;;
        *"night_keepawake.sh stop"*) geste="night_keepawake.sh stop" ;;
      esac
    fi
  done < "$PROMPT_FILE"
  if [ "$found" != "0" ]; then
    echo "night: prompt résolu sans consigne de réveil" >&2
    exit 1
  fi
  if [ "$HEADLESS" = 1 ] && [ "$found_h" != "0" ]; then
    echo "night: prompt headless sans la ligne de remplacement de la variante headless (§ Réveil armé)" >&2
    exit 1
  fi
  if [ -n "$geste" ]; then
    echo "night: prompt headless porteur d'un geste de réveil (« $geste ») — refusé par l'allowlist headless ; la boucle externe détient l'anti-veille" >&2
    exit 1
  fi
  exit 0
}

# --- Analyse des arguments -------------------------------------------------------------------
MODE=""
MINUTES=""
DRY=0
PROMPT_FILE=""
HEADLESS=0

case "${1:-}" in
  --probe)        MODE=probe;  shift ;;
  start)          MODE=start;  shift ;;
  stop)           MODE=stop;   shift ;;
  --check-prompt)
    MODE=check; shift
    # `--headless` n'est reconnu QU'ICI, juste après `--check-prompt` : ailleurs il tombe
    # dans « argument inconnu » (rc 2). Option explicite, jamais un relâchement du mode surveillé.
    if [ "${1:-}" = "--headless" ]; then HEADLESS=1; shift; fi
    PROMPT_FILE="${1:-}"
    [ -n "$PROMPT_FILE" ] || die_arg "--check-prompt exige un chemin de fichier"
    [ -f "$PROMPT_FILE" ] || die_arg "--check-prompt : fichier introuvable « $PROMPT_FILE »"
    shift
    ;;
  "")             die_arg "aucun mode — attendu --probe | start | stop | --check-prompt" ;;
  *)              die_arg "argument inconnu « ${1} » — attendu --probe | start | stop | --check-prompt" ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --minutes) shift; MINUTES="${1:-}"; [ -n "$MINUTES" ] || die_arg "--minutes exige une valeur"; shift ;;
    --dry-run) DRY=1; shift ;;
    *)         die_arg "argument inconnu « $1 »" ;;
  esac
done

case "$MODE" in
  probe) mode_probe ;;
  start) mode_start ;;
  stop)  mode_stop ;;
  check) mode_check ;;
esac
