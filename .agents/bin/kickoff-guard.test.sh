#!/usr/bin/env bash
# Tests des COQUILLES du garde de kickoff (T-00000243).
# Run: bash .agents/bin/kickoff-guard.test.sh
#
# CE QUE CETTE SUITE MESURE, ET CE QU'ELLE NE MESURE PAS. Elle mesure ce que le
# garde EMET — code de sortie, stdout, stderr — dans les DEUX formes du contrat
# par hote, plus le cas du marqueur ABSENT. Elle ne mesure PAS, et ne peut pas
# mesurer, ce que l'hote FAIT de cette emission : que Codex / Copilot / Gemini
# ARRETENT vraiment l'outil sur une enveloppe `deny` a rc 0 est une hypothese
# qu'aucun artefact de ce depot n'a jamais verifiee. Si l'enveloppe est
# indicative quelque part, `protect-paths` y est fail-open depuis T-00000031 et
# ce garde herite du trou — pas pire que la base livree, pas meilleur.
#
# Le faux depot est monte dans un repertoire temporaire parce que le garde
# resout sa racine depuis SON PROPRE emplacement (`parents[2]`), et parce que le
# depot REEL est livre DESARME : y armer une tache pour un test le rendrait
# arme, ce que la section 2 de la conception interdit.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYRUN="$ROOT/.agents/pyrun.sh"
PASS=0
fail() { echo "FAIL: $1"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/.agents/bin" "$TMP/.agents/state/board" "$TMP/.agents/state/specs" "$TMP/.agents/state/gates"
cp "$HERE"/*.py "$TMP/.agents/bin/"
GUARD="$TMP/.agents/bin/kickoff_guard.py"

board() { printf '%s' "$1" > "$TMP/.agents/state/board/TASKS.json"; }
journal() { printf '%s' "$1" > "$TMP/.agents/state/specs/SPECS.json"; }
arm() { printf '%s\n' "$1" > "$TMP/.agents/state/gates/KICKOFF_REQUIRED"; }
disarm() { rm -f "$TMP/.agents/state/gates/KICKOFF_REQUIRED"; }

EDIT_SRC='{"tool_name":"Edit","tool_input":{"file_path":"src/a.py"}}'
READ_SRC='{"tool_name":"Read","tool_input":{"file_path":"src/a.py"}}'

PENDING='{"next_id":2,"tasks":[{"id":"T-1","state":"pending","task":"armed but not started","writeset":["src/"]}]}'
RUNNING='{"next_id":2,"tasks":[{"id":"T-1","state":"running","task":"armed and started","writeset":["src/"]}]}'
NO_PLAN='{"next_id":1,"entries":[]}'
WITH_PLAN='{"next_id":2,"entries":[{"id":"S-00000001","task":"T-1","kind":"plan","title":"plan","text":"","files":[],"date":"2026-08-20"}]}'

# $1 payload · $2 host marker ("" = absent) · $3 expected rc · $4 stdout rule
# (empty|envelope) · $5 stderr rule (empty|nonempty) · $6 label
check() {
  set +e
  if [ -z "$2" ]; then
    unset AGENTS_HOOK_HOST
    OUT=$(printf '%s' "$1" | bash "$PYRUN" "$GUARD" 2>"$TMP/err")
  else
    OUT=$(printf '%s' "$1" | AGENTS_HOOK_HOST="$2" bash "$PYRUN" "$GUARD" 2>"$TMP/err")
  fi
  RC=$?
  set -e
  ERR=$(cat "$TMP/err")
  [ "$RC" -eq "$3" ] || fail "$6 (expected exit $3, got $RC; stdout: $OUT; stderr: $ERR)"
  case "$4" in
    empty) [ -z "$OUT" ] || fail "$6 (expected EMPTY stdout, got: $OUT)";;
    envelope)
      case "$OUT" in
        *'"permissionDecision":"deny"'*) : ;;
        *) fail "$6 (expected a deny envelope on stdout, got: $OUT)";;
      esac
      case "$OUT" in
        *'"hookEventName":"PreToolUse"'*) : ;;
        *) fail "$6 (envelope carries no hookEventName: $OUT)";;
      esac;;
  esac
  case "$5" in
    empty) [ -z "$ERR" ] || fail "$6 (expected EMPTY stderr, got: $ERR)";;
    nonempty) [ -n "$ERR" ] || fail "$6 (expected a non-empty stderr)";;
  esac
  PASS=$((PASS + 1))
}

# --- LA POLARITE : rien d'arme, rien ne change -------------------------------
# Pas un refus, pas un avertissement, pas un octet. C'est la condition pour que
# le mecanisme voyage vers la branche template sans casser le premier jour de
# chaque projet adoptant.
disarm
board "$PENDING"; journal "$NO_PLAN"
check "$EDIT_SRC" "claude" 0 empty empty "disarmed repo: claude sees nothing"
check "$EDIT_SRC" "codex"  0 empty empty "disarmed repo: codex sees nothing"
check "$EDIT_SRC" ""       0 empty empty "disarmed repo: no marker, still nothing"

# Le depot REEL est livre desarme, et cette suite le verifie sur place.
[ -f "$ROOT/.agents/state/gates/KICKOFF_REQUIRED" ] \
  && fail "the kit must ship DISARMED: .agents/state/gates/KICKOFF_REQUIRED is committed"
PASS=$((PASS + 1))

# --- CONTRAT DE REFUS, FORME 1/2 : Claude Code = stderr + exit 2 -------------
arm "T-1"
board "$PENDING"; journal "$WITH_PLAN"
check "$EDIT_SRC" "claude" 2 empty nonempty "claude: stderr + exit 2"

# --- CONTRAT DE REFUS, FORME 2/2 : enveloppe + exit 0 ------------------------
# Le SEUL canal que Codex / Copilot / Gemini aient jamais execute : aucun hook de
# ces trois hotes dans ce depot n'a jamais sorti un code non nul, donc un rc 2
# pourrait s'y lire comme un PLANTAGE et echouer OUVERT.
check "$EDIT_SRC" "codex"   0 envelope empty "codex: envelope + exit 0"
check "$EDIT_SRC" "copilot" 0 envelope empty "copilot: envelope + exit 0"
check "$EDIT_SRC" "gemini"  0 envelope empty "gemini: envelope + exit 0"

# --- LE CAS MARQUEUR ABSENT / INCONNU : LES DEUX canaux, puis exit 2 ---------
# Apres le cablage de T-00000243, aucun chemin ENREGISTRE n'y tombe : ce defaut
# ne gouverne plus que les invocations manuelles (celle-ci, precisement) et les
# provisionnements anterieurs — qui, eux, ne portent aucun enregistrement
# invoquant ce module, donc n'executent pas le garde du tout.
check "$EDIT_SRC" ""            2 envelope nonempty "no marker: BOTH channels + exit 2"
check "$EDIT_SRC" "antigravity" 2 envelope nonempty "unknown marker: BOTH channels + exit 2"

# --- LE GARDE N'A PAS MANDAT SUR UNE LECTURE ---------------------------------
# Copilot enregistre son preToolUse SANS matcher, donc le hook tire sur TOUS les
# outils : c'est le filtre de forme d'ecriture du module qui borne la portee.
check "$READ_SRC" "claude" 0 empty empty "armed repo: a Read still passes"
check "$READ_SRC" "codex"  0 empty empty "armed repo: a Read still passes (codex)"

# --- UNE ECRITURE CONFORME PASSE, EN SILENCE ---------------------------------
board "$RUNNING"; journal "$WITH_PLAN"
check "$EDIT_SRC" "claude" 0 empty empty "running + plan + in writeset: passes"
check "$EDIT_SRC" "codex"  0 empty empty "running + plan + in writeset: passes (codex)"

# --- LE FOCUS DU CLONE (T-01M5F728WZ89DF8PV79SDWEFE4) -------------------------
# Plusieurs running : le parent T-10 (focalise), ses lots T-11 (src/) et T-12
# (lib/), et T-20 (docs/), le running d'un COLLEGUE. Le faux depot n'est PAS un
# depot Git (aucun `git init`) : le focus se lit sous sa propre racine, repli
# hors Git, sans sous-processus.
[ -e "$TMP/.git" ] && fail "the focus fixture must stay OUTSIDE Git"
FOURNEE='{"next_id":21,"tasks":[
 {"id":"T-10","state":"running","task":"parent","writeset":["docs/tasks/T-10-plan.md"],"fournee":{"lots":["T-11","T-12"],"plan":"docs/tasks/T-10-plan.md"}},
 {"id":"T-11","state":"running","task":"lot A","writeset":["src/"],"fournee":{"parent":"T-10","lot":"A","plan":"docs/tasks/T-10-plan.md"}},
 {"id":"T-12","state":"running","task":"lot B","writeset":["lib/"],"fournee":{"parent":"T-10","lot":"B","plan":"docs/tasks/T-10-plan.md"}},
 {"id":"T-20","state":"running","task":"a colleague","writeset":["docs/x/"]}]}'
PLANS='{"next_id":5,"entries":[
 {"id":"S-00000001","task":"T-10","kind":"plan","title":"p","text":"","files":[],"date":"2026-10-21"},
 {"id":"S-00000002","task":"T-11","kind":"plan","title":"p","text":"","files":[],"date":"2026-10-21"},
 {"id":"S-00000003","task":"T-12","kind":"plan","title":"p","text":"","files":[],"date":"2026-10-21"},
 {"id":"S-00000004","task":"T-20","kind":"plan","title":"p","text":"","files":[],"date":"2026-10-21"}]}'
EDIT_PLAN='{"tool_name":"Edit","tool_input":{"file_path":"docs/tasks/T-10-plan.md"}}'
EDIT_LIB='{"tool_name":"Edit","tool_input":{"file_path":"lib/b.py"}}'
EDIT_FOREIGN='{"tool_name":"Edit","tool_input":{"file_path":"docs/x/y.md"}}'
arm "T-10
T-11
T-12
T-20"
board "$FOURNEE"; journal "$PLANS"
# Sans focus, DEUX familles en vol (T-10, T-20) : refus focus-missing — 7407b2fee
# refusait ce board entier, la garde ne le laisse jamais passer.
check "$EDIT_FOREIGN" "claude" 2 empty nonempty "no focus, two families: focus-missing"
case "$ERR" in
  *focus*T-20*) : ;;
  *) fail "the focus-missing refusal names the focus remedy: $ERR";;
esac
PASS=$((PASS + 1))
# UNE seule famille (la fournee seule) sans focus : l'ancienne regle, inchangee.
SOLO='{"next_id":21,"tasks":[
 {"id":"T-10","state":"running","task":"parent","writeset":["docs/tasks/T-10-plan.md"],"fournee":{"lots":["T-11"],"plan":"docs/tasks/T-10-plan.md"}},
 {"id":"T-11","state":"running","task":"lot A","writeset":["src/"],"fournee":{"parent":"T-10","lot":"A","plan":"docs/tasks/T-10-plan.md"}}]}'
board "$SOLO"
check "$EDIT_SRC" "claude" 0 empty empty "no focus, one family: the old rule stands"
board "$FOURNEE"
mkdir -p "$TMP/.agents/state/local"
printf '%s' '{"task_id":"T-10","updated_at":"2026-10-21T00:00:00Z"}' > "$TMP/.agents/state/local/focus.json"
check "$EDIT_PLAN"    "claude" 0 empty empty    "focus T-10: the focused parent is admitted"
check "$EDIT_SRC"     "claude" 0 empty empty    "focus T-10: its lot T-11 is admitted"
check "$EDIT_LIB"     "codex"  0 empty empty    "focus T-10: its lot T-12 is admitted (codex)"
check "$EDIT_FOREIGN" "claude" 2 empty nonempty "focus T-10: a colleague's running cannot cover"
case "$ERR" in
  *T-20*) : ;;
  *) fail "the foreign refusal names T-20: $ERR";;
esac
PASS=$((PASS + 1))
check "$EDIT_FOREIGN" "codex"  0 envelope empty "focus T-10: foreign refused through the envelope"
rm -f "$TMP/.agents/state/local/focus.json"
arm "T-1"

# --- UN CHEMIN HORS DE TOUT WRITESET ARME PASSE ------------------------------
board "$PENDING"; journal "$WITH_PLAN"
check '{"tool_name":"Edit","tool_input":{"file_path":"docs/x.md"}}' "claude" 0 empty empty \
  "path outside every armed writeset: passes"

# --- TRAVERSEE DE REPERTOIRE (securite classe 1, HIGH) -----------------------
# Le writeset arme est `src/`, la tache n'est PAS `running`. Un `..` ne doit pas
# faire passer une ecriture qui atterrit REELLEMENT dedans : cote entrees de
# writeset, `..` etait deja refuse et comptait comme COUVRANT ; cote chemin
# ecrit, il produisait l'effet inverse — non-couverture, donc passage silencieux.
# La forme relative est la plus probable en pratique (`*** Add File:`).
board "$PENDING"; journal "$WITH_PLAN"
TRAVERSAL='{"tool_name":"Edit","tool_input":{"file_path":"src/other/../a.py"}}'
TRAVERSAL_WIN='{"tool_name":"Edit","tool_input":{"file_path":"src\\other\\..\\a.py"}}'
TRAVERSAL_PATCH='{"tool_name":"apply_patch","tool_input":{"command":"*** Add File: src/other/../a.py\n"}}'
ESCAPES='{"tool_name":"Edit","tool_input":{"file_path":"../../etc/passwd"}}'
check "$TRAVERSAL"       "claude" 2 empty    nonempty "relative traversal into the writeset: refused"
check "$TRAVERSAL"       "codex"  0 envelope empty    "relative traversal: refused through the envelope too"
check "$TRAVERSAL_WIN"   "claude" 2 empty    nonempty "windows form of the same bypass: refused"
check "$TRAVERSAL_PATCH" "claude" 2 empty    nonempty "apply_patch marker carrying a traversal: refused"
check "$ESCAPES"         "claude" 2 empty    nonempty "path escaping above the root: refused, never silent"

# NON-REGRESSION : le correctif ne change RIEN pour un depot desarme.
disarm
check "$TRAVERSAL" "claude" 0 empty empty "disarmed repo: a traversal is still silent"
check "$ESCAPES"   "claude" 0 empty empty "disarmed repo: an escaping path is still silent"
check "$ESCAPES"   "codex"  0 empty empty "disarmed repo: still silent on codex too"
arm "T-1"

# --- STDIN VIDE OU ILLISIBLE NE COINCE JAMAIS UN TOUR ------------------------
check "" "claude" 0 empty empty "empty stdin never wedges a turn"
check "not json at all" "claude" 0 empty empty "non-JSON stdin never wedges a turn"

echo "PASS: kickoff-guard ($PASS/$PASS)"
